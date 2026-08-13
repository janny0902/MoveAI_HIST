// 차량 기준 매칭. 사진 경로(useAnalysis)를 대신한다.
//
// 왜 별도 훅인가: useAnalysis는 촬영→EXIF→리사이즈→업로드→vision 폴링→matching 폴링의
// 6단계 파이프라인이고, 그 절반이 사진에만 필요한 단계다. 사진을 받지 않기로 한 이상
// 같은 훅에 분기를 넣으면 안 쓰는 경로가 계속 남아 무엇이 실제로 도는지 흐려진다.
//
// 여기서는 요청 한 번이 곧 결과다. 서버가 계산을 마치고 응답하므로 폴링이 없다.
import { useCallback, useRef, useState } from "react";

import { matchByTruck } from "./api";
import { pushTruckLocation } from "./rematch";

export function useTruckMatch() {
  const [matching, setMatching] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [ranAt, setRanAt] = useState(null);

  // 갱신 버튼을 연타하면 요청이 겹친다. 늦게 온 응답이 최신 결과를 덮어쓰지 않도록
  // 순번을 매겨 마지막 요청의 응답만 반영한다.
  const seqRef = useRef(0);

  /**
   * @param truckId 차량 번호
   * @param position 현재 위치. 있으면 매칭 전에 서버 좌표를 갱신한다 — 회랑이 현재
   *                 위치를 기준으로 잡히므로, 위치가 낡으면 엉뚱한 지역 화물이 잡힌다.
   */
  const run = useCallback(async (truckId, position, candidateLimit, palletized) => {
    const seq = ++seqRef.current;
    setBusy(true);
    setError(null);
    try {
      // 위치 갱신은 실패해도 매칭을 막지 않는다. 직전 좌표로 계산되고, 그 사실은
      // 결과의 회랑 반경 안에서 드러난다.
      if (position) await pushTruckLocation(truckId, position);
      const result = await matchByTruck(truckId, candidateLimit, palletized);
      if (seq !== seqRef.current) return null;
      setMatching(result);
      setRanAt(new Date());
      return result;
    } catch (e) {
      if (seq === seqRef.current) setError(e.message || "매칭에 실패했습니다.");
      return null;
    } finally {
      if (seq === seqRef.current) setBusy(false);
    }
  }, []);

  /** 차량을 바꾸면 이전 차량의 결과는 무효다. 남겨두면 다른 차의 숫자를 보게 된다. */
  const reset = useCallback(() => {
    seqRef.current++;
    setMatching(null);
    setError(null);
    setRanAt(null);
    setBusy(false);
  }, []);

  return { matching, busy, error, ranAt, run, reset };
}
