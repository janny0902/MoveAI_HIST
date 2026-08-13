// [교체 가능] 기준 위치. 추가 상차 묶음을 이 위치에서 가까운 순으로 정렬한다.
//
// GPS만 쓰지 않는 이유: 이 화면을 보는 사람은 사무실에 앉은 관리자다. 브라우저가 잡는
// 위치는 관리자의 위치지 배차할 차의 위치가 아니다. 그래서 주소로 직접 옮길 수 있어야
// 한다 — "지금 이 차가 어디서 출발한다 치고 보자"가 실제 쓰임새다.
import { useState } from "react";

import { searchAddress } from "../lib/destination";

export default function MyLocationCard({ position, source, onChange, onUseGps, gpsAvailable }) {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState([]);

  const search = async (e) => {
    e.preventDefault();
    const q = query.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    setResults([]);
    try {
      // searchAddress는 **후보 배열**을 돌려준다. 단일 객체로 받으면 lat이 undefined가
      // 되고, 그 값이 화면까지 흘러가 렌더에서 터진다(실제로 흰 화면이 났다).
      const found = await searchAddress(q);
      const usable = (Array.isArray(found) ? found : [found]).filter(
        (r) => r && Number.isFinite(r.lat) && Number.isFinite(r.lng)
      );
      if (usable.length === 0) {
        setError("주소를 찾지 못했습니다. 도로명이나 지번으로 다시 입력해 주세요.");
        return;
      }
      // 후보가 하나면 바로 적용한다. 여러 개면 고르게 한다 — "서울시청"처럼 여러 곳이
      // 잡히는 질의에서 임의로 첫 번째를 쓰면 엉뚱한 곳을 기준으로 정렬하게 된다.
      if (usable.length === 1) {
        apply(usable[0]);
      } else {
        setResults(usable.slice(0, 5));
      }
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const apply = (r) => {
    onChange({ lat: r.lat, lng: r.lng }, r.address || query.trim());
    setOpen(false);
    setQuery("");
    setResults([]);
  };

  return (
    <section className="card">
      <div className="location-head">
        <span className="field-label">기준 위치</span>
        <button type="button" className="btn text" onClick={() => setOpen((v) => !v)}>
          {open ? "닫기" : "내 위치 변경"}
        </button>
      </div>

      {/* 좌표가 숫자인지 확인하고 쓴다. 지오코딩 응답이 조금만 달라도 여기서 터지면
          화면 전체가 사라진다 — 실제로 그렇게 흰 화면이 났다. */}
      <p className="spec-line">
        {Number.isFinite(position?.lat) && Number.isFinite(position?.lng)
          ? <>{source || "현재 위치"} · {position.lat.toFixed(4)}, {position.lng.toFixed(4)}</>
          : "위치를 확인하는 중입니다. 주소로 직접 지정할 수도 있습니다."}
      </p>
      <p className="spec-line muted">
        추가 상차 묶음을 이 위치에서 가까운 상차지 순으로 정렬합니다.
      </p>

      {open && (
        <form className="loc-edit" onSubmit={search}>
          <input
            type="text"
            className="text-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="예) 서울특별시 동대문구 장한로 145"
            autoComplete="off"
          />
          <div className="loc-actions">
            <button type="submit" className="btn secondary" disabled={busy || !query.trim()}>
              {busy ? "찾는 중…" : "이 주소로 설정"}
            </button>
            {gpsAvailable && (
              <button type="button" className="btn text" onClick={() => { onUseGps(); setOpen(false); }}>
                현재 위치로 되돌리기
              </button>
            )}
          </div>
          {error && <p className="dialog-error">{error}</p>}

          {results.length > 0 && (
            <ul className="loc-results">
              {results.map((r) => (
                <li key={`${r.lat},${r.lng}`}>
                  <button type="button" className="btn text block-left" onClick={() => apply(r)}>
                    {r.address}
                    <span className="muted"> · {r.lat.toFixed(4)}, {r.lng.toFixed(4)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </form>
      )}
    </section>
  );
}
