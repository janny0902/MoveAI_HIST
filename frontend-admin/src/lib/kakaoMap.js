// 카카오 지도 SDK 로더.
//
// 지도는 **선택 기능**이다. 카카오 JavaScript 키가 주입돼 있을 때만 켜지고, 없으면
// 화면은 주소/좌표 패널로 degrade한다. 키가 없다고 촬영을 막지 않는다.
//
// REST 키와 다른 키다. 카카오 개발자 콘솔에서 같은 앱의 "JavaScript 키"를 쓰고,
// 플랫폼 > Web에 프론트 도메인을 등록해야 동작한다(등록하지 않으면 SDK가 401을 낸다).
// 이 키는 도메인 제한이 걸린 공개 키라 브라우저에 노출돼도 된다 — REST 키와 달리
// 서버로 프록시할 필요가 없다.
const SDK_URL = "//dapi.kakao.com/v2/maps/sdk.js";

export const kakaoJsKey = () => (window.__APP_CONFIG__ || {}).KAKAO_JS_KEY || "";

let loading = null;

/**
 * SDK를 한 번만 싣고 kakao.maps를 돌려준다.
 * @returns {Promise<object|null>} 키가 없으면 null
 */
export function loadKakaoMaps() {
  if (!kakaoJsKey()) return Promise.resolve(null);
  if (window.kakao?.maps?.Map) return Promise.resolve(window.kakao.maps);
  if (loading) return loading;

  loading = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    // autoload=false로 두고 kakao.maps.load()를 직접 부른다. 그러지 않으면 스크립트
    // onload와 SDK 초기화 완료 시점이 달라, 바로 Map을 만들면 undefined가 난다.
    script.src = `${SDK_URL}?appkey=${encodeURIComponent(kakaoJsKey())}&autoload=false`;
    script.async = true;
    script.onload = () => window.kakao.maps.load(() => resolve(window.kakao.maps));
    script.onerror = () => reject(new Error("카카오 지도 SDK를 불러오지 못했습니다."));
    document.head.appendChild(script);
  }).catch((err) => {
    loading = null; // 다음 시도에서 다시 받을 수 있게 한다.
    throw err;
  });

  return loading;
}
