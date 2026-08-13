// 화면에서 고른 값을 브라우저에 남긴다.
//
// 기사는 같은 차로 하루에 여러 번 찍는다. 접속할 때마다 차량 번호와 목적지를 다시
// 고르게 하면 그 자체가 오입력 기회다 — 특히 차량 번호는 틀리면 결과가 통째로 어긋난다.
//
// localStorage에 두는 이유는 이게 **기기의 선택**이지 서버가 알아야 할 상태가 아니기
// 때문이다. 트럭의 실제 위치·적재중량 같은 업무 데이터는 Firestore가 정본이고, 여기에
// 복제하지 않는다. 시크릿 모드나 저장소가 막힌 환경에서도 화면이 죽으면 안 되므로
// 모든 접근을 try로 감싼다.
const KEY = "moveai.prefs.v1";

function readAll() {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function loadPref(name, fallback = null) {
  const v = readAll()[name];
  return v === undefined || v === null ? fallback : v;
}

export function savePref(name, value) {
  try {
    const all = readAll();
    if (value === null || value === undefined) delete all[name];
    else all[name] = value;
    window.localStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    /* 저장이 막힌 환경이면 이번 세션만 유지된다. 화면을 막지는 않는다. */
  }
}
