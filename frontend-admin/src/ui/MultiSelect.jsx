// [교체 가능] 검색해서 여러 개를 고르는 콤보.
//
// <select multiple>을 쓰지 않는 이유: 여러 개를 고르려면 Ctrl(⌘)을 눌러야 하고, 실수로
// 그냥 클릭하면 앞서 고른 것이 통째로 날아간다. 터미널이 100곳이 넘어 스크롤로 찾아야
// 하는데 그 와중에 선택이 초기화되면 처음부터 다시 골라야 한다.
//
// 그래서 클릭 한 번이 곧 토글이고, 검색으로 목록을 좁힌다. 고른 것은 칩으로 위에 남겨
// 목록을 닫아도 무엇을 골랐는지 보이게 한다.
import { useEffect, useMemo, useRef, useState } from "react";

/**
 * @param options [[code, name], ...]
 * @param value 고른 code 배열
 * @param onChange 새 배열을 받는다
 */
export default function MultiSelect({ id, label, options, value, onChange, placeholder }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const boxRef = useRef(null);

  // 바깥을 누르면 닫는다. 목록이 열린 채로 다른 곳을 조작하면 화면이 겹쳐 읽힌다.
  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    // 코드로도 이름으로도 찾을 수 있어야 한다. 관리자는 '305'로도 '경주'로도 부른다.
    return options.filter(([code, name]) =>
      code.toLowerCase().includes(q) || (name || "").toLowerCase().includes(q));
  }, [options, query]);

  const nameOf = useMemo(() => Object.fromEntries(options), [options]);

  const toggle = (code) => {
    onChange(value.includes(code)
      ? value.filter((c) => c !== code)
      : [...value, code]);
  };

  return (
    <div className="ms" ref={boxRef}>
      <label className="field-label" htmlFor={id}>
        {label} {value.length > 0 && <span className="ms-count">{value.length}곳</span>}
      </label>

      <button type="button" id={id} className="text-input ms-toggle"
              onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span className={value.length ? "" : "muted"}>
          {value.length === 0
            ? (placeholder || "전체")
            : `${value.length}곳 선택됨`}
        </span>
        <span className="ms-caret" aria-hidden="true">▾</span>
      </button>

      {/* 고른 것은 닫아도 보여야 한다. 칩을 눌러 바로 뺄 수 있다. */}
      {value.length > 0 && (
        <ul className="ms-chips">
          {value.map((code) => (
            <li key={code}>
              <button type="button" className="ms-chip" onClick={() => toggle(code)}
                      aria-label={`${code} 선택 해제`}>
                {code} · {nameOf[code] || code}
                <span className="ms-chip-x" aria-hidden="true">✕</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && (
        <div className="ms-panel">
          <input
            type="text"
            className="text-input ms-search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="코드 또는 이름으로 검색"
            autoComplete="off"
            autoFocus
          />

          <div className="ms-actions">
            <span className="muted">{filtered.length}곳</span>
            {value.length > 0 && (
              <button type="button" className="btn text" onClick={() => onChange([])}>
                모두 해제
              </button>
            )}
          </div>

          <ul className="ms-list">
            {filtered.length === 0 && <li className="ms-empty">검색 결과가 없습니다.</li>}
            {filtered.map(([code, name]) => {
              const on = value.includes(code);
              return (
                <li key={code}>
                  <button type="button"
                          className={on ? "ms-item on" : "ms-item"}
                          onClick={() => toggle(code)}
                          aria-pressed={on}>
                    <span className="ms-check" aria-hidden="true">{on ? "☑" : "☐"}</span>
                    <span className="ms-code">{code}</span>
                    <span className="ms-name">{name}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
