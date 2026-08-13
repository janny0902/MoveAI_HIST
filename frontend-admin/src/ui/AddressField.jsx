// [교체 가능] 표현 계층. 주소를 검색해 좌표까지 확정하는 입력 필드.
// 계약: 결과를 고르면 onChange({address, lat, lng})를 호출한다.
// 검색 로직은 src/lib/destination.js에 있다. 여기서 fetch를 직접 부르지 말 것.
import { useState } from "react";

import { searchAddress } from "../lib/destination";

export default function AddressField({ label, value, onChange, placeholder }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState(null);

  const run = async () => {
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    setError(null);
    setResults([]);
    try {
      const found = await searchAddress(q);
      setResults(found);
      if (!found.length) setError("검색 결과가 없습니다.");
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSearching(false);
    }
  };

  // form 안에 있으므로 Enter가 상위 제출을 일으키지 않도록 막는다.
  const onKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      run();
    }
  };

  return (
    <div className="address-field">
      <label className="field-label">{label}</label>

      {value ? (
        <div className="picked">
          <span>{value.address}</span>
          <button type="button" className="btn text" onClick={() => onChange(null)}>
            변경
          </button>
        </div>
      ) : (
        <>
          <div className="search-row">
            <input
              type="text"
              className="text-input"
              placeholder={placeholder}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKeyDown}
              enterKeyHint="search"
            />
            <button type="button" className="btn primary compact" onClick={run} disabled={searching || !query.trim()}>
              {searching ? "검색 중…" : "검색"}
            </button>
          </div>

          {error && <p className="dialog-error">{error}</p>}

          {results.length > 0 && (
            <ul className="result-list">
              {results.map((r) => (
                <li key={`${r.lat},${r.lng}`}>
                  <button
                    type="button"
                    className="result-item"
                    onClick={() => { onChange(r); setResults([]); setQuery(""); }}
                  >
                    {r.address}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
