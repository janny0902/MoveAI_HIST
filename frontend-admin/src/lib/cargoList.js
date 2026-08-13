// 대기 운송장 조회.
//
// 적재가 실제로 됐는지, 어느 터미널에 얼마나 쌓였는지 눈으로 볼 창구가 없어서 Firestore
// 콘솔을 열어야 했다. 매칭 후보가 0건일 때 "화물이 없는 것"과 "적재가 안 된 것"을
// 구분하려면 이 화면이 필요하다.
import { matchingBase } from "./api";

/**
 * @param terminalCode 출발 작업터미널. 지정하면 그 터미널만.
 * @param destinationTerminalCode 도착 작업터미널. 지정하면 그 터미널로 가는 것만.
 * @param page 1부터. 서버가 offset으로 건너뛴다.
 * @returns {{cargos, returned, limit, page, total, has_more, by_terminal, by_route}}
 */
export async function fetchPendingCargos({
  limit = 100,
  terminalCode = "",
  destinationTerminalCode = "",
  page = 1,
} = {}) {
  if (!matchingBase()) throw new Error("매칭 서버 주소가 설정되지 않았습니다.");
  const q = new URLSearchParams({ limit: String(limit), page: String(page) });
  if (terminalCode) q.set("terminal_code", terminalCode);
  if (destinationTerminalCode) q.set("destination_terminal_code", destinationTerminalCode);

  const res = await fetch(`${matchingBase()}/v1/cargos?${q}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`운송장 목록을 불러오지 못했습니다 (${res.status})`);
  return res.json();
}

/** Firestore timestamp(ISO 문자열)를 "08-09 14:20"으로. 없으면 null. */
export function shortTime(value) {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
