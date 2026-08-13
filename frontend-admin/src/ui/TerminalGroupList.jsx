// [교체 가능] 표현 계층. 추가 상차 가능 운송장을 출발-도착 터미널 묶음으로 보여준다.
//
// 낱건 목록을 쓰지 않는 이유: 기사가 정하는 것은 "이 운송장을 실을까"가 아니라 "이
// 터미널에 들를까"다. 200건을 한 줄씩 늘어놓으면 들를 곳이 몇 군데인지조차 읽히지 않는다.
//
// 집계는 서버(matching-processor의 _group_by_terminal)가 만든 값을 그대로 쓴다.
// 여기서 다시 세면 화면과 저장값이 갈라진다 — UI_CONTRACT의 "체적·중량을 화면에서
// 계산하지 않는다"와 같은 이유다.

import { haversineKm } from "../lib/rematch";
import MultiSelect from "./MultiSelect";

/** "A 3 · C 12" — 건수 내림차순은 서버가 이미 정렬해 둔 순서를 따른다. */
function boxTypeText(counts) {
  const entries = Object.entries(counts || {});
  if (entries.length === 0) return null;
  return entries.map(([type, n]) => `${type} ${n}`).join(" · ");
}

/** 그룹에서 실제로 등장하는 터미널만 뽑는다. 122곳을 다 늘어놓으면 고를 수가 없다. */
function optionsFrom(groups, codeKey, nameKey) {
  const seen = new Map();
  for (const g of groups) {
    const code = g[codeKey];
    if (code && !seen.has(code)) seen.set(code, g[nameKey] || code);
  }
  return [...seen.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

export default function TerminalGroupList({
  groups, allGroups, position,
  originFilter = [], destFilter = [], onOriginChange, onDestChange, onClear,
}) {
  const source = allGroups || groups;
  if (!source || source.length === 0) return null;

  const totalCargo = groups.reduce((s, g) => s + (g.cargo_count || 0), 0);
  const origins = optionsFrom(source, "origin_terminal_code", "origin_terminal_name");
  const dests = optionsFrom(source, "destination_terminal_code", "destination_terminal_name");
  const filtered = originFilter.length > 0 || destFilter.length > 0;

  // 기준 위치가 있으면 가까운 상차지부터 보여준다. 관리자가 먼저 묻는 것은 "어디부터
  // 들르게 할까"라, 건수 순으로 늘어놓으면 지도상 반대편 묶음이 맨 위에 온다.
  // 좌표가 없는 묶음은 거리를 지어내지 않고 뒤로 보낸다.
  const withDistance = groups.map((g) => ({
    g,
    km: position && g.origin_lat != null && g.origin_lng != null
      ? haversineKm(position, { lat: g.origin_lat, lng: g.origin_lng })
      : null,
  }));

  const sorted = position
    ? [...withDistance].sort((a, b) => {
        if (a.km == null && b.km == null) return b.g.cargo_count - a.g.cargo_count;
        if (a.km == null) return 1;
        if (b.km == null) return -1;
        return a.km - b.km || b.g.cargo_count - a.g.cargo_count;
      })
    : withDistance;

  return (
    <section className="card">
      <h2>추가 상차 가능 운송장</h2>

      {/* 묶음을 고르면 적재 그림과 적재율이 그 묶음만으로 다시 그려진다. 관리자가
          실제로 하는 일이 "어느 구간을 태울지 고르는 것"이라, 고른 결과가 차에 얼마나
          차는지 바로 보여야 한다. */}
      <div className="grid-2">
        <MultiSelect
          id="groupOrigin"
          label="출발지 터미널"
          options={origins}
          value={originFilter}
          onChange={onOriginChange}
        />
        <MultiSelect
          id="groupDest"
          label="도착지 터미널"
          options={dests}
          value={destFilter}
          onChange={onDestChange}
        />
      </div>
      <p className="spec-line muted">
        아무것도 고르지 않으면 전체입니다.
        {filtered && (
          <button type="button" className="btn text inline" onClick={onClear}>
            전체 선택 해제
          </button>
        )}
      </p>

      <p className="spec-line muted">
        {filtered
          ? `선택한 구간 ${groups.length}개 묶음 · 운송장 ${totalCargo}건 (전체 ${source.length}개 묶음 중)`
          : `출발 · 도착 작업터미널 기준 ${groups.length}개 묶음 · 운송장 ${totalCargo}건`}
        {position && " · 기준 위치에서 가까운 상차지 순"}
      </p>

      {groups.length === 0 && (
        <p className="hint">고른 구간에 해당하는 묶음이 없습니다.</p>
      )}

      <ul className="group-list">
        {sorted.map(({ g, km }) => (
          <li
            key={`${g.origin_terminal_code}-${g.destination_terminal_code}`}
            className="group-item"
          >
            <div className="group-route">
              <b>{g.origin_terminal_name || g.origin_terminal_code || "출발지 미상"}</b>
              <span className="group-arrow" aria-label="에서">→</span>
              <b>{g.destination_terminal_name || g.destination_terminal_code || "도착지 미상"}</b>
              {km != null && (
                <span className="group-km">{km < 1 ? "1km 이내" : `${km.toFixed(1)}km`}</span>
              )}
            </div>

            <div className="group-codes muted">
              {g.origin_terminal_code} → {g.destination_terminal_code}
            </div>

            <div className="group-counts">
              {/* 운송장 건수와 박스 개수를 나란히 둔다. 한 운송장에 박스가 여럿이라
                  둘이 다르고, 차에 실리는 것은 박스 쪽이다. */}
              <span className="group-count-main">운송장 {g.cargo_count}건</span>
              <span className="muted">박스 {g.box_count}개</span>
            </div>

            {boxTypeText(g.box_type_counts) && (
              <div className="group-boxtypes">
                박스타입 · {boxTypeText(g.box_type_counts)}
              </div>
            )}

            <div className="group-metrics muted">
              {g.volume_cbm} CBM · {g.weight_kg}kg
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
