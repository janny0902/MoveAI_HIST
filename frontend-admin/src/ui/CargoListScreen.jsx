// [교체 가능] 대기 운송장 목록.
//
// 매칭 후보가 0건일 때 "주변에 화물이 없는 것"과 "적재 자체가 안 된 것"을 구분할 방법이
// 없었다. 어느 터미널에 얼마나 쌓였는지 보이면 그 자리에서 판단할 수 있다.
import { useCallback, useEffect, useState } from "react";

import { fetchPendingCargos, shortTime } from "../lib/cargoList";
import { fetchTerminals } from "../lib/waybill";

export default function CargoListScreen() {
  const [terminals, setTerminals] = useState([]);
  const [terminalCode, setTerminalCode] = useState("");
  const [destinationCode, setDestinationCode] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(100);
  // 상세 목록은 접어 둔다. 100건이 늘 펼쳐져 있으면 그 위의 집계 카드가 밀려
  // 화면을 열자마자 보이는 것이 낱건 목록이 된다 — 관리자가 먼저 보는 것은 묶음이다.
  const [showList, setShowList] = useState(false);
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchTerminals().then(setTerminals).catch(() => setTerminals([]));
  }, []);

  const load = useCallback(async (code, destCode, pageNo, size) => {
    setBusy(true);
    setError(null);
    try {
      setData(await fetchPendingCargos({
        limit: size, terminalCode: code, destinationTerminalCode: destCode, page: pageNo,
      }));
    } catch (err) {
      setError(err.message || String(err));
      setData(null);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    load(terminalCode, destinationCode, page, pageSize);
  }, [load, terminalCode, destinationCode, page, pageSize]);

  // 필터를 바꾸면 1페이지로 돌아간다. 3페이지를 보던 중 필터를 좁히면 그 페이지가
  // 아예 없을 수 있고, 그러면 빈 목록이 뜬다.
  useEffect(() => { setPage(1); }, [terminalCode, destinationCode, pageSize]);

  const cargos = data?.cargos || [];

  return (
    <>
      <section className="card">
        <div className="grid-2">
          <div>
            <label className="field-label" htmlFor="filterTerminal">출발 작업터미널</label>
            <select
              id="filterTerminal"
              className="text-input"
              value={terminalCode}
              onChange={(e) => setTerminalCode(e.target.value)}
            >
              <option value="">전체</option>
              {terminals.map((t) => (
                <option key={t.terminal_code} value={t.terminal_code}>
                  {t.terminal_code} · {t.name || "이름 없음"}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="filterDestination">도착 작업터미널</label>
            <select
              id="filterDestination"
              className="text-input"
              value={destinationCode}
              onChange={(e) => setDestinationCode(e.target.value)}
            >
              <option value="">전체</option>
              {terminals.map((t) => (
                <option key={t.terminal_code} value={t.terminal_code}>
                  {t.terminal_code} · {t.name || "이름 없음"}
                </option>
              ))}
            </select>
          </div>
        </div>

        <button type="button" className="btn secondary"
                onClick={() => load(terminalCode, destinationCode, page, pageSize)} disabled={busy}>
          {busy ? "불러오는 중…" : "새로 고침"}
        </button>

        {error && <p className="dialog-error">{error}</p>}

        {data && (
          <div className="pager">
            <p className="hint">
              {data.total != null
                ? `전체 ${data.total.toLocaleString()}건 중 `
                : ""}
              {((data.page - 1) * data.limit + 1).toLocaleString()}–
              {((data.page - 1) * data.limit + cargos.length).toLocaleString()}번째
              {data.total == null && " (필터를 걸면 전체 건수는 세지 않습니다)"}
            </p>
            <div className="pager-controls">
              <button type="button" className="btn compact" disabled={busy || page <= 1}
                      onClick={() => setPage(1)}>« 처음</button>
              <button type="button" className="btn compact" disabled={busy || page <= 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}>‹ 이전</button>
              <span className="pager-page">{page} 페이지</span>
              <button type="button" className="btn compact" disabled={busy || !data.has_more}
                      onClick={() => setPage((p) => p + 1)}>다음 ›</button>
              <select className="text-input compact" value={pageSize}
                      onChange={(e) => setPageSize(Number(e.target.value))}
                      aria-label="페이지당 건수">
                {[50, 100, 200, 500].map((n) => (
                  <option key={n} value={n}>{n}건씩</option>
                ))}
              </select>
            </div>
          </div>
        )}
      </section>

      {/* 관리자가 보는 화면이라 "얼마를 번다"가 아니라 "얼마나 쌓였다"가 필요하다.
          수수료는 기사에게 제안할 때 쓰는 숫자고, 배차를 정할 때 보는 것은 물량이다. */}
      {cargos.length > 0 && (
        <section className="card earn">
          <p className="earn-lead">
            {terminalCode
              ? `${terminals.find((t) => t.terminal_code === terminalCode)?.name || terminalCode} 대기 물량`
              : "지금 대기 중인 물량"}
          </p>
          <p className="earn-amount">
            {data.total_volume_cbm.toFixed(2)}<span>CBM</span>
          </p>
          <p className="earn-sub">
            운송장 {cargos.length}건
            {data.by_route?.length > 0 && ` · 출발→도착 ${data.by_route.length}개 묶음`}
          </p>
          <p className="earn-note">
            체적은 측정기 치수(가로×세로×높이)에서 계산한 값입니다.
            차량별로 얼마나 실리는지는 '관리자 · 적재 배정' 탭에서 확인합니다.
          </p>
        </section>
      )}

      {/* 출발-도착 쌍별 집계. 기사 화면이 묶는 축과 같아서, 여기서 미리 어떤 묶음이
          쌓여 있는지 확인할 수 있다. */}
      {data?.by_route?.length > 0 && (
        <section className="card">
          <span className="field-label">출발 → 도착별 (이 목록 기준 {data.by_route.length}개 묶음)</span>
          <ul className="group-list">
            {data.by_route.slice(0, 30).map((g) => (
              <li key={`${g.origin_terminal_code}-${g.destination_terminal_code}`} className="group-item">
                <div className="group-route">
                  <b>{g.origin_terminal_name || g.origin_terminal_code}</b>
                  <span className="group-arrow">→</span>
                  <b>{g.destination_terminal_name || g.destination_terminal_code}</b>
                </div>
                <div className="group-codes muted">
                  {g.origin_terminal_code} → {g.destination_terminal_code}
                </div>
                <div className="group-counts">
                  <span className="group-count-main">운송장 {g.count}건</span>
                  <span className="muted">박스 {g.box_count}개</span>
                </div>
                <div className="group-boxtypes">
                  박스타입 · {Object.entries(g.box_type_counts || {})
                    .map(([t, n]) => `${t} ${n}`).join(" · ")}
                </div>
                <div className="group-metrics muted">{g.volume_cbm} CBM</div>
              </li>
            ))}
          </ul>
          {data.by_route.length > 30 && (
            <p className="hint">상위 30개 묶음만 표시했습니다.</p>
          )}
        </section>
      )}

      {data?.by_terminal?.length > 1 && (
        <section className="card">
          <span className="field-label">출발터미널별 (이 목록 기준)</span>
          <table className="result-table">
            <tbody>
              {data.by_terminal.map((t) => (
                <tr key={t.terminal_code}>
                  <th>{t.terminal_code} · {t.terminal_name || "이름 없음"}</th>
                  <td>
                    {t.count}건 · {t.volume_cbm.toFixed(2)} CBM
                    <b className="earn-inline"> +{Math.round(t.commission_krw).toLocaleString()}원</b>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="card">
        {cargos.length === 0 && !busy && (
          <p className="hint">
            대기 중인 운송장이 없습니다. 측정기 CSV를 적재 버킷에 올렸는지, 그 파일의
            생성일시가 너무 오래되지 않았는지 확인해 주세요.
          </p>
        )}

        {cargos.length > 0 && (
          <button type="button" className="accordion" onClick={() => setShowList((v) => !v)}
                  aria-expanded={showList}>
            <span className="accordion-caret" aria-hidden="true">{showList ? "▾" : "▸"}</span>
            <span className="accordion-title">운송장 상세 {cargos.length}건</span>
            <span className="muted">{showList ? "접기" : "펼치기"}</span>
          </button>
        )}

        <ul className="cargo-list" hidden={!showList}>
          {cargos.map((c) => (
            <li key={c.cargo_id} className="cargo-row">
              <div className="cargo-head">
                <span className="cargo-id">{c.cargo_id}</span>
                <span className="cargo-size">
                  {c.freight_krw > 0 && (
                    <>
                      <span className="cargo-freight">운임 {Math.round(c.freight_krw).toLocaleString()}원</span>
                      <b className="earn-inline"> +{Math.round(c.commission_krw).toLocaleString()}원</b>
                    </>
                  )}
                </span>
              </div>
              <div className="cargo-meta">
                {c.box_types?.length > 0 && (
                  // 중량 추정의 근거라 앞에 둔다. 규격박스 타입이 곧 대표 중량이다.
                  <span className="cargo-type">타입 {c.box_types.join(", ")}</span>
                )}
                {c.box_count != null && <span>박스 {c.box_count}개</span>}
                {c.volume_cbm != null && <span>{Number(c.volume_cbm).toFixed(3)} CBM</span>}
                {c.weight_kg != null && (
                  <span>
                    {Number(c.weight_kg).toFixed(1)} kg
                    {c.weight_source === "ESTIMATED" && " (추정)"}
                  </span>
                )}
                {c.product_code && <span>{c.product_code}</span>}
              </div>
              <div className="cargo-meta">
                <span>
                  {c.origin_terminal_code} · {c.origin_terminal_name || "출발 터미널 미상"}
                  {" → "}
                  {c.destination_terminal_code || "?"} · {c.destination_terminal_name || "도착 터미널 미상"}
                </span>
              </div>
              {c.pickup_address && <div className="cargo-addr">{c.pickup_address}</div>}
              <div className="cargo-meta">
                {c.pickup_lat != null && (
                  <span>{Number(c.pickup_lat).toFixed(4)}, {Number(c.pickup_lng).toFixed(4)}</span>
                )}
                {shortTime(c.deadline_at) && <span>마감 {shortTime(c.deadline_at)}</span>}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
