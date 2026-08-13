// [교체 가능] 표현 계층. Stitch / AI Studio 산출물로 갈아끼워도 된다.
// 지켜야 할 계약: 파일을 고르면 onPhoto(file)을 호출한다. 그 외 자유.
//
// 차량 제원을 촬영 전에 보여주는 이유는 ../lib/truck.js 주석 참고 — 분석이 등록된
// 적재함 치수를 자로 삼기 때문에, 다른 차량을 찍으면 결과가 통째로 어긋난다.
import { useEffect, useRef, useState } from "react";

import { dimsText, fetchTruckList, fetchTruckSpec, modelText, truckOptionText } from "../lib/truck";

/**
 * 이 기기에서 `capture` 속성이 실제로 카메라를 여는가.
 *
 * 데스크톱 브라우저는 `<input capture>`를 **무시하고** 그냥 파일 선택창을 연다. 그래서
 * PC에서 "카메라로 촬영"을 누르면 파일 탐색기가 떴다 — 버그처럼 보이지만 표준 동작이다.
 * PC에서는 대신 getUserMedia로 웹캠 미리보기를 띄운다(WebcamDialog).
 */
function hasCamera() {
  if (typeof window === "undefined") return false;
  return (
    navigator.maxTouchPoints > 0 &&
    window.matchMedia?.("(pointer: coarse)").matches === true
  );
}

export default function CaptureCard({ truckId, onTruckIdChange, onPhoto, onWebcam, busy, preview }) {
  const cameraRef = useRef(null);
  const fileRef = useRef(null);
  const [spec, setSpec] = useState(null);
  const [specState, setSpecState] = useState("idle"); // idle | loading | ok | none | error
  const [trucks, setTrucks] = useState([]);
  const [manual, setManual] = useState(false);
  // 기기 판정은 렌더마다 바뀌지 않는다. 한 번만 계산한다.
  const [camera] = useState(hasCamera);

  // 등록 차량 목록. 실패하면 조용히 직접 입력으로 넘어간다 — 목록을 못 받았다고
  // 촬영을 막을 이유는 없다.
  useEffect(() => {
    let alive = true;
    fetchTruckList()
      .then((list) => { if (alive) setTrucks(list); })
      .catch(() => { if (alive) setManual(true); });
    return () => { alive = false; };
  }, []);

  // 차량 번호를 입력하는 동안 매 글자마다 부르지 않도록 잠깐 기다린다.
  useEffect(() => {
    const id = (truckId || "").trim();
    if (!id) { setSpec(null); setSpecState("idle"); return; }

    let alive = true;
    setSpecState("loading");
    const timer = setTimeout(() => {
      fetchTruckSpec(id)
        .then((s) => {
          if (!alive) return;
          setSpec(s);
          setSpecState(s ? "ok" : "none");
        })
        .catch(() => { if (alive) { setSpec(null); setSpecState("error"); } });
    }, 400);

    return () => { alive = false; clearTimeout(timer); };
  }, [truckId]);

  // 같은 파일을 다시 골라도 change가 뜨도록 값을 비운다.
  const handle = (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) onPhoto(file);
  };

  const dims = dimsText(spec);

  return (
    <section className="card">
      <div className="location-head">
        <label className="field-label" htmlFor="truckId">차량 번호</label>
        {trucks.length > 0 && (
          <button type="button" className="btn text" onClick={() => setManual((m) => !m)}>
            {manual ? "목록에서 고르기" : "직접 입력"}
          </button>
        )}
      </div>

      {manual || trucks.length === 0 ? (
        <input
          id="truckId"
          type="text"
          className="text-input"
          value={truckId}
          onChange={(e) => onTruckIdChange(e.target.value)}
          autoComplete="off"
          placeholder="T-000001"
        />
      ) : (
        <select
          id="truckId"
          className="text-input"
          value={trucks.some((t) => t.truck_id === truckId) ? truckId : ""}
          onChange={(e) => onTruckIdChange(e.target.value)}
        >
          {/* 저장된 번호가 목록에 없을 수도 있다(삭제됐거나 직접 입력한 값). 그 경우
              빈 항목이 선택돼, 고르지 않은 상태임이 드러난다. */}
          <option value="" disabled>차량을 고르세요</option>
          {trucks.map((t) => (
            <option key={t.truck_id} value={t.truck_id}>{truckOptionText(t)}</option>
          ))}
        </select>
      )}

      {specState === "ok" && (
        <div className="truck-spec">
          <div className="truck-spec-title">
            {modelText(spec) || spec.truck_id}
          </div>
          <dl className="truck-spec-grid">
            <div><dt>적재함</dt><dd>{dims || "치수 미등록"}</dd></div>
            <div><dt>적재함 부피</dt><dd>{spec.capacity_cbm != null ? `${spec.capacity_cbm} CBM` : "-"}</dd></div>
            <div><dt>최대 적재중량</dt><dd>{spec.max_payload_kg != null ? `${spec.max_payload_kg} kg` : "-"}</dd></div>
            <div>
              <dt>현재 실린 중량</dt>
              <dd>
                {spec.current_loaded_weight_kg != null ? `${spec.current_loaded_weight_kg} kg` : "-"}
                {spec.available_payload_kg != null && (
                  <span className="sub"> · 여유 {spec.available_payload_kg} kg</span>
                )}
              </dd>
            </div>
          </dl>
          <p className="truck-spec-warn">
            사진 속 크기는 이 제원을 기준으로 환산합니다.
            <b> 다른 차를 찍으면 결과가 맞지 않습니다.</b>
          </p>
        </div>
      )}

      {specState === "none" && (
        <p className="truck-spec-warn standalone">
          {truckId.trim()} 제원이 없습니다. 적재함 치수를 모르면 사진에서 크기를 환산할 수
          없어 분석이 중단됩니다.
        </p>
      )}

      {specState === "error" && (
        <p className="truck-spec-warn standalone">차량 제원을 불러오지 못했습니다.</p>
      )}

      <button
        type="button"
        className="btn primary"
        disabled={busy}
        // 모바일은 OS 카메라를 부르고(EXIF가 남아 초점거리가 정확하다), PC는 웹캠
        // 미리보기를 띄운다. 데스크톱 브라우저가 capture 속성을 무시하기 때문이다.
        onClick={() => (camera ? cameraRef.current?.click() : onWebcam?.())}
      >
        카메라로 촬영
      </button>
      <button
        type="button"
        className="btn secondary"
        disabled={busy}
        onClick={() => fileRef.current?.click()}
      >
        {camera ? "앨범 · 파일에서 선택" : "사진 파일 선택"}
      </button>

      {/* 2.1: OS 기본 카메라 호출은 capture=environment로 한다. */}
      <input ref={cameraRef} type="file" accept="image/*" capture="environment" hidden onChange={handle} />
      <input ref={fileRef} type="file" accept="image/*" hidden onChange={handle} />

      {preview && <img className="preview" src={preview} alt="촬영한 화물칸 사진" />}
    </section>
  );
}
