// 운행 중 재매칭.
//
// 사진은 한 번만 찍지만 주변 화물은 계속 바뀐다. 트럭이 움직이면 회랑도 같이 움직여서
// 출발할 때는 없던 화물이 도중에 잡힌다. 그래서 목적지에 닿을 때까지 주기적으로 다시
// 계산한다.
//
// 사진을 다시 찍지는 않는다. 빈 공간(CBM)은 상차/하차를 하지 않는 한 그대로이므로,
// 첫 분석 결과를 그대로 재사용하고 **위치만** 갱신해 매칭을 다시 돌린다.
import { matchingBase, visionBase } from "./api";

/** 목적지 반경 이 거리 안이면 도착으로 본다. GPS 오차가 100m대라 그보다 넉넉히 잡는다. */
export const ARRIVAL_RADIUS_KM = 0.3;

export function haversineKm(a, b) {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const la1 = (a.lat * Math.PI) / 180;
  const la2 = (b.lat * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

/**
 * 첫 분석 결과로 재매칭용 이벤트를 만든다.
 *
 * 새 event_id를 매번 발급하는 이유: matching은 event_id로 중복 처리를 막는다(5.8).
 * 같은 값을 재사용하면 두 번째부터 "중복"으로 무시된다. 사진은 그대로이므로 photo_id는
 * 유지하고, 결과 문서를 덮어써서 화면이 항상 최신을 보게 한다.
 */
export function rematchEvent(vision) {
  return {
    schema: "space-geometry.v3",
    event_id: `rematch-${vision.photo_id}-${Date.now()}`,
    truck_id: vision.truck_id,
    photo_id: vision.photo_id,
    captured_at: vision.captured_at,
    estimated_free_cbm: vision.estimated_free_cbm,
    usable_free_cbm: vision.usable_free_cbm,
    unknown_cbm: vision.unknown_cbm,
    quality_score: vision.quality_score,
    quality_status: vision.quality_status,
  };
}

/** 운행 중 위치 갱신. 실패해도 재매칭 자체는 진행한다(직전 위치로 계산된다). */
export async function pushTruckLocation(truckId, position) {
  if (!position) return false;
  try {
    const res = await fetch(`${visionBase()}/v1/trucks/${encodeURIComponent(truckId)}/location`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lat: position.lat, lng: position.lng }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** 매칭을 다시 돌린다. 실패하면 null — 다음 주기에 다시 시도한다. */
export async function runRematch(vision) {
  try {
    const res = await fetch(`${matchingBase()}/v1/match`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rematchEvent(vision)),
    });
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}
