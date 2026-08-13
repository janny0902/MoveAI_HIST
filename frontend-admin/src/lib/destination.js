// 목적지 관리.
//
// Matching M2 경로 회랑은 트럭의 현재 위치와 **목적지**가 둘 다 있어야 만들 수 있다.
// 목적지가 비면 can_load=false(truck_position_or_destination_unknown)로 끝나므로,
// 기사가 지정하지 않으면 기본 목적지를 쓴다.
//
// 기본 목적지의 정본은 서버 설정(vision-processor/config.py)이다. 여기에 주소를 복제해
// 두면 양쪽이 어긋나므로, 서버에서 받아 온 값을 쓰고 아래 상수는 서버 응답을 못 받았을
// 때만 쓰는 최후 폴백이다.
import { visionBase } from "./api";

/** 서버를 못 부를 때만 쓰는 폴백. 서버 값(GET /v1/defaults)이 우선한다. */
export const FALLBACK_DEFAULT_DESTINATION = {
  address: "서울특별시 마포구 마포대로 34 (물류산업진흥재단)",
  lat: 37.5416713,
  lng: 126.9493505,
};

/** 서버가 들고 있는 기본 목적지와 주소 검색 사용 가능 여부를 가져온다. */
export async function fetchDefaults() {
  try {
    const res = await fetch(`${visionBase()}/v1/defaults`, { cache: "no-store" });
    if (!res.ok) throw new Error(String(res.status));
    const data = await res.json();
    return {
      defaultDestination: data.default_destination || FALLBACK_DEFAULT_DESTINATION,
      geocodingEnabled: Boolean(data.geocoding_enabled),
    };
  } catch {
    return { defaultDestination: FALLBACK_DEFAULT_DESTINATION, geocodingEnabled: false };
  }
}

/**
 * 주소로 목적지 후보를 검색한다.
 * 서버가 Geocoding API를 대신 호출한다(브라우저에 API 키를 노출하지 않기 위해).
 * @returns {Promise<Array<{address: string, lat: number, lng: number}>>}
 */
export async function searchAddress(query) {
  const res = await fetch(`${visionBase()}/v1/geocode?q=${encodeURIComponent(query)}`, {
    cache: "no-store",
  });
  if (res.status === 503) {
    throw new Error("주소 검색이 아직 설정되지 않았습니다. 기본 목적지를 사용해 주세요.");
  }
  if (!res.ok) {
    let detail = `검색 실패 (${res.status})`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch { /* 본문이 JSON이 아니면 기본 메시지를 쓴다 */ }
    throw new Error(detail);
  }
  const data = await res.json();
  return data.results || [];
}
