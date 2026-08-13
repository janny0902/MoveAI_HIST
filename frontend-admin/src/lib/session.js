// 운행 세션 복원.
//
// 재매칭 루프는 브라우저 안에서 돈다. 그래서 기사가 화면을 닫았다 다시 열면 추적이
// 끊기고, 촬영 버튼만 덩그러니 남아 사진을 또 찍게 된다. 서버에 남은 "이 차량의 최근
// 운행"을 읽어 그 상태를 그대로 이어받는다.
//
// 사진을 다시 올리지는 않는다. 하차하지 않는 한 빈 공간은 그대로이므로 직전 분석 결과를
// 그대로 쓰고 위치만 갱신하며 매칭을 다시 돌린다.
import { matchingBase, visionBase } from "./api";

async function getJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  return res.ok ? res.json() : null;
}

/**
 * 이 차량에 이어받을 운행이 있으면 {vision, matching}을 돌려준다. 없으면 null.
 *
 * matching 결과는 없을 수도 있다(분석 직후 아직 매칭 전). 그 경우에도 vision만으로
 * 화면을 복원하고, 재매칭 루프가 첫 주기에 매칭 결과를 채운다.
 */
export async function restoreSession(truckId, withinMinutes = 60) {
  const id = (truckId || "").trim();
  if (!id || !visionBase()) return null;

  const session = await getJson(
    `${visionBase()}/v1/trucks/${encodeURIComponent(id)}/session?within_minutes=${withinMinutes}`
  );
  if (!session?.active || !session.photo_id) return null;

  const vision = await getJson(`${visionBase()}/v1/results/${session.photo_id}`);
  if (!vision) return null;

  const matching = matchingBase()
    ? await getJson(`${matchingBase()}/v1/results/${session.photo_id}`)
    : null;

  return { session, vision, matching };
}
