// 현재 위치. 촬영 화면이 사진을 올리기 **전에** 보여준다.
//
// 왜 미리 보여주는가: 상차 후보는 트럭의 현재 위치를 중심으로 한 경로 회랑에서 고른다
// (matching-processor M2). 위치가 틀리면 엉뚱한 지역의 화물이 추천되고, 위치가 없으면
// 추천 자체가 중단된다. 그런데 지금까지는 분석을 시작한 뒤에야 위치를 잡아서, 기사는
// 결과가 나온 다음에나 위치 문제를 알 수 있었다. 찍기 전에 확인시킨다.
//
// T-트럭커 같은 호스트 앱에 얹을 때는 이 모듈만 갈아끼우면 된다 — 앱이 이미 갖고 있는
// 위치를 넘겨받는 형태로 바꿔도 화면은 그대로다.
import { matchingBase, visionBase } from "./api";

/**
 * 위치를 계속 따라간다. 정지 상태에서도 GPS가 흔들려 좌표가 조금씩 바뀌므로
 * watchPosition으로 최신값을 유지한다.
 * @param onUpdate {(state: {position, accuracy, reason}) => void}
 * @returns 구독 해제 함수
 */
export function watchLocation(onUpdate) {
  if (!navigator.geolocation) {
    onUpdate({ position: null, accuracy: null, reason: "이 브라우저는 위치를 지원하지 않습니다." });
    return () => {};
  }
  // HTTPS(또는 localhost)가 아니면 브라우저가 권한 팝업조차 띄우지 않는다.
  if (!window.isSecureContext) {
    onUpdate({ position: null, accuracy: null, reason: "보안 연결(HTTPS)이 아니라 위치를 쓸 수 없습니다." });
    return () => {};
  }

  const id = navigator.geolocation.watchPosition(
    (p) =>
      onUpdate({
        position: { lat: p.coords.latitude, lng: p.coords.longitude },
        accuracy: p.coords.accuracy,
        reason: null,
      }),
    (err) =>
      onUpdate({
        position: null,
        accuracy: null,
        reason:
          {
            1: "위치 권한이 거부됐습니다. 브라우저 설정에서 허용해 주세요.",
            2: "위치를 확인할 수 없습니다.",
            3: "위치 확인이 시간 내에 끝나지 않았습니다.",
          }[err.code] || "위치를 가져오지 못했습니다.",
      }),
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 }
  );
  return () => navigator.geolocation.clearWatch(id);
}

/** 좌표 -> 주소. 실패해도 화면을 막지 않는다(좌표만 보여준다). */
export async function reverseGeocode({ lat, lng }) {
  try {
    const res = await fetch(`${visionBase()}/v1/reverse-geocode?lat=${lat}&lng=${lng}`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    const body = await res.json();
    return body.address || null;
  } catch {
    return null;
  }
}

/**
 * 현재 위치 -> 목적지 주행 경로. 지도에 선으로 그린다.
 *
 * 경로를 못 받으면 아무것도 그리지 않는다. 직선으로 대신 그리면 실제 도로처럼 보여
 * 거리를 오해하게 된다.
 * @returns {{distance_m, duration_s, path: [lng,lat][]} | null}
 */
export async function fetchRoute(origin, dest) {
  if (!origin || !dest || !matchingBase()) return null;
  const q = new URLSearchParams({
    origin_lat: origin.lat, origin_lng: origin.lng,
    dest_lat: dest.lat, dest_lng: dest.lng,
  });
  try {
    const res = await fetch(`${matchingBase()}/v1/route?${q}`, { cache: "no-store" });
    if (!res.ok) return null;
    const body = await res.json();
    return body.path?.length ? body : null;
  } catch {
    return null;
  }
}

/** "12.4km · 34분" */
export function routeText(route) {
  if (!route) return null;
  const km = route.distance_m != null ? `${(route.distance_m / 1000).toFixed(1)}km` : null;
  const min = route.duration_s != null ? `${Math.round(route.duration_s / 60)}분` : null;
  return [km, min].filter(Boolean).join(" · ") || null;
}

/** "37.58839, 127.01039" — 주소를 못 받았을 때 대신 보여줄 값. */
export function coordText(position) {
  if (!position) return null;
  return `${position.lat.toFixed(5)}, ${position.lng.toFixed(5)}`;
}

/** 정확도 표시. 값이 크면 실내/도심이라 신뢰도가 낮다는 뜻이다. */
export function accuracyText(accuracy) {
  if (accuracy == null) return null;
  return accuracy >= 1000
    ? `오차 약 ${(accuracy / 1000).toFixed(1)}km`
    : `오차 약 ${Math.round(accuracy)}m`;
}
