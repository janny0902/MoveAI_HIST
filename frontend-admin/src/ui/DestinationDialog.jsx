// [교체 가능] 표현 계층.
// 계약: 사진을 고른 뒤 목적지를 바꿀지 묻는다.
//   - onConfirm(destination|null) 을 호출하면 분석이 시작된다. null이면 기본 목적지를 쓴다.
//   - onCancel() 은 분석을 취소한다.
// 검색·기본값 조회 로직은 src/lib/destination.js에 있다. 여기서 fetch를 직접 부르지 말 것.
import { useEffect, useRef, useState } from "react";

import { searchAddress } from "../lib/destination";

export default function DestinationDialog({ defaultDestination, geocodingEnabled, onConfirm, onCancel }) {
  const [mode, setMode] = useState("ask"); // ask | search
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (mode === "search") inputRef.current?.focus();
  }, [mode]);

  const runSearch = async (event) => {
    event.preventDefault();
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    setSearchError(null);
    setResults([]);
    try {
      const found = await searchAddress(q);
      setResults(found);
      if (!found.length) setSearchError("검색 결과가 없습니다. 다른 주소로 시도해 주세요.");
    } catch (err) {
      setSearchError(err.message || String(err));
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="목적지 확인">
      <div className="dialog">
        {mode === "ask" ? (
          <>
            <h2 className="dialog-title">목적지를 변경할까요?</h2>
            <p className="dialog-body">
              변경하지 않으면 기본 목적지로 분석합니다.
            </p>
            <p className="dialog-default">
              <span className="dialog-default-label">기본 목적지</span>
              {defaultDestination.address}
            </p>

            <button type="button" className="btn primary" onClick={() => setMode("search")}>
              목적지 변경
            </button>
            <button type="button" className="btn secondary" onClick={() => onConfirm(null)}>
              기본 목적지로 진행
            </button>
            <button type="button" className="btn text" onClick={onCancel}>
              취소
            </button>

            {!geocodingEnabled && (
              <p className="hint">
                주소 검색이 아직 설정되지 않았습니다. 기본 목적지로만 진행할 수 있습니다.
              </p>
            )}
          </>
        ) : (
          <>
            <h2 className="dialog-title">목적지 검색</h2>
            <form onSubmit={runSearch}>
              <input
                ref={inputRef}
                type="text"
                className="text-input"
                placeholder="예: 서울특별시 마포구 마포대로 34"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                enterKeyHint="search"
              />
              <button type="submit" className="btn primary" disabled={searching || !query.trim()}>
                {searching ? "검색 중…" : "검색"}
              </button>
            </form>

            {searchError && <p className="dialog-error">{searchError}</p>}

            {results.length > 0 && (
              <ul className="result-list">
                {results.map((r) => (
                  <li key={`${r.lat},${r.lng}`}>
                    <button type="button" className="result-item" onClick={() => onConfirm(r)}>
                      {r.address}
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <button type="button" className="btn text" onClick={() => setMode("ask")}>
              뒤로
            </button>
          </>
        )}
      </div>
    </div>
  );
}
