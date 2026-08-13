import { useCallback, useEffect, useRef, useState } from "react";

import { ARRIVAL_RADIUS_KM, haversineKm, pushTruckLocation, runRematch } from "./rematch";
import { parseExif } from "./exif";
import { buildIntrinsics, resizeToJpeg } from "./image";
import {
  getPosition,
  pollMatchingResult,
  pollVisionResult,
  requestUploadUrl,
  uploadToSignedUrl,
} from "./api";

const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 180000;

// 운행 중 재매칭 주기. 실서비스에서는 더 길어야 하지만(카카오 길찾기 호출이 후보 수에
// 비례한다) 시연에서 변화를 눈으로 봐야 해서 1분으로 둔다.
const REMATCH_INTERVAL_MS = 60000;

// UI가 진행 상황을 그릴 때 쓰는 단계 정의. 순서가 곧 파이프라인 순서다.
//
// etaSeconds는 화면이 "몇 초쯤 더 기다리면 되는지"를 말하기 위한 값이다. AI 공간 분석은
// 60-105초 걸리는데(VIS-09) 그동안 화면에 아무 변화가 없어 고장난 것처럼 보인다.
// 실측 범위의 중간값을 쓰고, 넘어가면 "조금 더 걸리고 있습니다"로 바꾼다 — 남은 시간을
// 0으로 표시해 놓고 계속 도는 것이 제일 나쁘다.
export const STEPS = [
  { key: "exif", label: "사진 정보 읽기" },
  { key: "resize", label: "1024px로 축소" },
  { key: "url", label: "업로드 주소 발급" },
  { key: "upload", label: "업로드" },
  { key: "vision", label: "AI 공간 분석", etaSeconds: 90 },
  { key: "matching", label: "적재 가능 화물 조합", etaSeconds: 10 },
];

/**
 * 촬영부터 결과까지의 전 과정을 관리한다.
 * UI를 새로 만들더라도 이 훅의 인터페이스만 지키면 백엔드 계약은 그대로 유지된다.
 */
export function useAnalysis() {
  const [steps, setSteps] = useState({});
  const [preview, setPreview] = useState(null);
  const [vision, setVision] = useState(null);
  const [matching, setMatching] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  // 위치를 못 받은 이유. 조용히 넘어가면 왜 목적지 계산이 안 되는지 알 수 없다.
  const [gpsNotice, setGpsNotice] = useState(null);
  const previewUrlRef = useRef(null);

  // 지금 도는 단계가 언제 시작됐는지. 화면이 경과/남은 시간을 세는 근거다.
  const [stepStartedAt, setStepStartedAt] = useState(null);

  // 운행 중 재매칭. 사진은 다시 찍지 않고 위치만 갱신해 다시 계산한다.
  const [tracking, setTracking] = useState(null);
  const timerRef = useRef(null);
  const visionRef = useRef(null);
  // 최신 위치/목적지는 화면(LocationCard)이 계속 갱신한다. state로 잡으면 인터벌이
  // 매번 재생성되므로 ref로 읽는다.
  const liveRef = useRef({ position: null, destination: null });

  const setLive = useCallback((position, destination) => {
    liveRef.current = { position, destination };
  }, []);

  const stopTracking = useCallback((reason = "stopped") => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setTracking((t) => (t ? { ...t, active: false, endReason: reason } : t));
  }, []);

  // 컴포넌트가 사라질 때 타이머를 반드시 정리한다. 남으면 화면이 없는데도 계속 매칭을 돈다.
  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current); }, []);

  const startTracking = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    setTracking({ active: true, count: 0, lastAt: Date.now(), endReason: null });

    timerRef.current = setInterval(async () => {
      const vision = visionRef.current;
      const { position, destination } = liveRef.current;
      if (!vision) return;

      // 도착했으면 멈춘다. 내려서 하차하는 중에 계속 추천해 봐야 의미가 없다.
      if (position && destination && haversineKm(position, destination) <= ARRIVAL_RADIUS_KM) {
        stopTracking("arrived");
        return;
      }

      if (position) await pushTruckLocation(vision.truck_id, position);
      const result = await runRematch(vision);
      if (result) setMatching(result);
      setTracking((t) =>
        t && t.active ? { ...t, count: t.count + 1, lastAt: Date.now() } : t
      );
    }, REMATCH_INTERVAL_MS);
  }, [stopTracking]);

  /**
   * 서버에 남은 운행을 이어받는다. 사진을 다시 올리지 않고 직전 분석 결과를 그대로 쓴다.
   * 하차하지 않는 한 빈 공간은 그대로이므로, 위치만 갱신하며 매칭을 다시 돌리면 된다.
   */
  const resume = useCallback((visionResult, matchingResult) => {
    if (!visionResult) return;
    setVision(visionResult);
    setMatching(matchingResult || null);
    // 이어받은 운행은 이미 끝난 단계들이다. 진행 목록을 전부 완료로 채운다.
    setSteps(Object.fromEntries(STEPS.map((s) => [s.key, "done"])));
    setStepStartedAt(null);
    visionRef.current = visionResult;
    startTracking();
  }, [startTracking]);

  const mark = useCallback((key, state) => {
    setSteps((prev) => ({ ...prev, [key]: state }));
    setStepStartedAt(state === "active" ? Date.now() : null);
  }, []);

  const analyze = useCallback(
    /**
     * @param knownGps 촬영 화면이 이미 잡아 둔 위치 {position, reason}. 넘기면 다시 묻지
     *   않는다 — 화면에 보여준 좌표와 실제로 분석에 쓴 좌표가 달라지면 안 되기 때문이다.
     */
    async (file, truckId, destination = null, knownGps = null) => {
      if (!file) return;
      // 새로 찍으면 이전 운행의 재매칭은 멈춘다.
      stopTracking("restarted");
      if (!truckId?.trim()) {
        setError("차량 번호를 입력해 주세요.");
        return;
      }

      setBusy(true);
      setSteps({});
      setVision(null);
      setMatching(null);
      setError(null);
      setGpsNotice(null);

      let currentStep = "exif";
      try {
        // 2.1: 리사이즈하면 EXIF가 사라지므로 원본에서 먼저 읽는다.
        mark("exif", "active");
        const exif = parseExif(await file.arrayBuffer());
        const { position: gps, reason: gpsReason } =
          knownGps?.position ? knownGps : await getPosition();
        if (gpsReason) setGpsNotice(gpsReason);
        mark("exif", "done");

        currentStep = "resize";
        mark("resize", "active");
        const resized = await resizeToJpeg(file, exif.orientation || 1);
        if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = URL.createObjectURL(resized.blob);
        setPreview(previewUrlRef.current);
        const intrinsics = buildIntrinsics(exif, resized);
        mark("resize", "done");

        currentStep = "url";
        mark("url", "active");
        const { photo_id, upload_url } = await requestUploadUrl({
          truckId: truckId.trim(),
          intrinsics,
          gps,
          destination,
        });
        mark("url", "done");

        currentStep = "upload";
        mark("upload", "active");
        await uploadToSignedUrl(upload_url, resized.blob);
        mark("upload", "done");

        const deadline = Date.now() + POLL_TIMEOUT_MS;
        const pollOpts = { intervalMs: POLL_INTERVAL_MS, deadline };

        currentStep = "vision";
        mark("vision", "active");
        const visionResult = await pollVisionResult(photo_id, pollOpts);
        if (!visionResult) throw new Error("분석 결과를 기다리다 시간이 초과됐습니다.");
        setVision(visionResult);
        mark("vision", "done");

        currentStep = "matching";
        mark("matching", "active");
        const matchingResult = await pollMatchingResult(photo_id, pollOpts);
        setMatching(matchingResult);
        mark("matching", matchingResult ? "done" : "fail");

        // 여기서부터는 목적지에 닿을 때까지(또는 기사가 멈출 때까지) 주기적으로 다시
        // 계산한다. 품질이 REJECT면 빈 공간 수치 자체를 믿을 수 없으므로 돌리지 않는다.
        if (matchingResult && visionResult.quality_status !== "REJECTED") {
          visionRef.current = visionResult;
          startTracking();
        }
      } catch (err) {
        mark(currentStep, "fail");
        // fetch가 CORS/네트워크로 실패하면 "Failed to fetch"만 던져 원인을 알 수 없다.
        // 어느 단계에서 끊겼는지 함께 알려 준다.
        const raw = err?.message || String(err);
        setError(
          raw === "Failed to fetch"
            ? `서버에 연결하지 못했습니다 (${currentStep} 단계). 백엔드 주소와 CORS 설정을 확인해 주세요.`
            : raw
        );
      } finally {
        setBusy(false);
      }
    },
    [mark, startTracking, stopTracking]
  );

  return {
    analyze, steps, stepStartedAt, preview, vision, matching, error, busy, gpsNotice,
    tracking, stopTracking, setLive, resume,
  };
}

/**
 * 5.8의 실패 사유 코드를 기사가 읽을 수 있는 문장으로 바꾼다.
 *
 * vision과 matching 양쪽의 코드를 함께 받는다. 품질 문제로 끊기면 matching은
 * quality_rejected만 알지만, 왜 그런지는 vision의 사유에 있다.
 */
export function failureText(reason) {
  return (
    {
      scale_mismatch:
        "사진에서 잰 적재함 크기가 등록 제원과 크게 다릅니다. 적재함 안쪽이 화면을 " +
        "가득 채우도록, 뒷문 바로 앞에서 안쪽을 향해 다시 찍어 주세요. 차량 주변 " +
        "건물이나 다른 차가 함께 찍히면 그쪽에 크기를 맞춰 버립니다.",
      no_valid_depth_points: "사진에서 거리를 읽지 못했습니다. 더 밝은 곳에서 다시 찍어 주세요.",
      insufficient_structural_planes:
        "적재함의 벽과 바닥을 찾지 못했습니다. 적재함 안쪽이 보이도록 다시 찍어 주세요.",
      truck_frame_failed: "적재함 기준면을 잡지 못했습니다. 뒷문 정면에서 다시 찍어 주세요.",
      quality_rejected: "사진 품질이 기준에 못 미쳐 판정을 중단했습니다. 다시 촬영해 주세요.",
      truck_spec_not_found: "차량 제원이 등록돼 있지 않습니다.",
      current_loaded_weight_unknown: "현재 적재중량을 알 수 없어 판정할 수 없습니다.",
      truck_position_or_destination_unknown: "위치 또는 목적지 정보가 없어 경로를 계산할 수 없습니다.",
      no_candidate_cargo: "주변에 실을 수 있는 대기 화물이 없습니다.",
      no_feasible_combination: "공간과 중량 안에 들어가는 조합이 없습니다.",
      routes_api_failed: "경로 조회에 실패해 신규 추천을 중단했습니다.",
      cargo_index_missing: "화물 검색 색인이 준비되지 않았습니다.",
    }[reason] || "조건을 만족하는 화물이 없습니다."
  );
}
