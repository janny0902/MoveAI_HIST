// [교체 가능] 표현 계층.
// 계약: 차량을 고르면 onTruckIdChange(id), 갱신 버튼을 누르면 onRun()을 호출한다.
//
// 사진을 받지 않는다. 적재된 박스를 0으로 보므로 실을 수 있는 공간은 등록 적재함 체적
// 그 자체이고, 그 값은 차량을 고르는 순간 이미 정해진다. 그래서 화면이 하는 일은
// "어느 차인가"를 받는 것뿐이다.
import { useEffect, useState } from "react";

import { dimsText, fetchTruckList, fetchTruckSpec, modelText, truckOptionText } from "../lib/truck";

/** 제원이 어디서 온 값인지 한 줄로. 제원 템플릿 ID가 그 출처를 가리킨다. */
function specSource(spec) {
  if (!spec) return null;
  const parts = ["제조사 공개 제원"];
  if (spec.spec_template_id) parts.push(spec.spec_template_id);
  if (spec.registered_year) parts.push(`${spec.registered_year}년식`);
  return `제원 출처 · ${parts.join(" · ")}`;
}

// 고를 수 있는 후보 수. 서버 상한을 넘는 값은 화면에서 아예 빼서, 눌러 놓고 잘리는
// 일이 없게 한다.
const CANDIDATE_OPTIONS = [500, 1000, 2000, 5000, 10000, 20000, 50000, 100000];

// 후보 수별 실측 소요시간(초). T-000004 · 파렛트 기준으로 잰 값이다.
// 사이 값은 선형 보간한다. 정확한 예측이 아니라 "얼마나 기다려야 하나"의 눈금이다.
const ELAPSED_SAMPLES = [
  [500, 3], [2000, 5], [5000, 12], [10000, 20],
  [20000, 32], [50000, 48], [100000, 75],
];

/** 후보 수 -> 예상 소요(초). 표 밖이면 양 끝 값을 쓴다. */
function estimateSeconds(candidates) {
  const n = Number(candidates) || 10000;
  if (n <= ELAPSED_SAMPLES[0][0]) return ELAPSED_SAMPLES[0][1];
  const last = ELAPSED_SAMPLES[ELAPSED_SAMPLES.length - 1];
  if (n >= last[0]) return last[1];
  for (let i = 1; i < ELAPSED_SAMPLES.length; i += 1) {
    const [x1, y1] = ELAPSED_SAMPLES[i - 1];
    const [x2, y2] = ELAPSED_SAMPLES[i];
    if (n <= x2) return Math.round(y1 + ((n - x1) / (x2 - x1)) * (y2 - y1));
  }
  return last[1];
}

/**
 * 계산이 도는 동안 흐른 시간(초).
 *
 * 진행률 막대를 쓰지 않는 이유: 서버가 진행 상황을 알려주지 않아 막대를 그리면 그 움직임이
 * 곧 거짓말이 된다. 흐른 시간은 실제로 아는 값이다.
 */
function useElapsed(running) {
  const [sec, setSec] = useState(0);
  useEffect(() => {
    if (!running) { setSec(0); return; }
    const t0 = Date.now();
    setSec(0);
    const id = setInterval(() => setSec(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(id);
  }, [running]);
  return sec;
}

export default function TruckMatchCard({
  truckId, onTruckIdChange, onRun, onSpec, busy, ranAt,
  candidateLimit = "", onCandidateLimitChange, candidateLimitMax, candidateLimitUsed,
  palletized = false, onPalletizedChange,
}) {
  const [spec, setSpec] = useState(null);
  const [specState, setSpecState] = useState("idle"); // idle | loading | ok | none | error
  const [trucks, setTrucks] = useState([]);
  const [manual, setManual] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchTruckList()
      .then((list) => { if (alive) setTrucks(list); })
      .catch(() => { if (alive) setManual(true); });
    return () => { alive = false; };
  }, []);

  // 차량 번호를 직접 입력하는 동안 매 글자마다 부르지 않도록 잠깐 기다린다.
  useEffect(() => {
    const id = (truckId || "").trim();
    if (!id) { setSpec(null); setSpecState("idle"); return; }

    let alive = true;
    setSpecState("loading");
    const timer = setTimeout(() => {
      fetchTruckSpec(id)
        .then((s) => {
          if (!alive) return;
          setSpec(s);
          setSpecState(s ? "ok" : "none");
        })
        .catch(() => { if (alive) { setSpec(null); setSpecState("error"); } });
    }, 400);

    return () => { alive = false; clearTimeout(timer); };
  }, [truckId]);

  // 적재 그림이 실제 적재함 치수로 격자를 만든다. 제원을 두 번 조회하지 않도록
  // 여기서 받은 것을 그대로 올려 보낸다.
  useEffect(() => { onSpec?.(spec); }, [spec, onSpec]);

  const dims = dimsText(spec);
  const model = modelText(spec);
  const loaded = spec?.current_loaded_weight_kg;

  const elapsed = useElapsed(busy);
  const estimate = estimateSeconds(candidateLimit);
  const remaining = Math.max(0, estimate - elapsed);
  const overrun = elapsed >= estimate;
  const runningLabel = overrun
    ? `계산 중… ${elapsed}초 경과`
    : `약 ${remaining}초 남았습니다`;

  return (
    <section className="card">
      <div className="location-head">
        <label className="field-label" htmlFor="truckId">차량 번호</label>
        {trucks.length > 0 && (
          <button type="button" className="btn text" onClick={() => setManual((m) => !m)}>
            {manual ? "목록에서 고르기" : "직접 입력"}
          </button>
        )}
      </div>

      {manual || trucks.length === 0 ? (
        <input
          id="truckId"
          type="text"
          className="text-input"
          value={truckId}
          onChange={(e) => onTruckIdChange(e.target.value)}
          autoComplete="off"
          placeholder="T-000001"
        />
      ) : (
        <select
          id="truckId"
          className="text-input"
          value={truckId}
          onChange={(e) => onTruckIdChange(e.target.value)}
        >
          <option value="">선택하세요</option>
          {trucks.map((t) => (
            <option key={t.truck_id} value={t.truck_id}>{truckOptionText(t)}</option>
          ))}
        </select>
      )}

      {specState === "loading" && <p className="spec-line">제원 확인 중…</p>}
      {specState === "none" && (
        <p className="spec-line warn">등록되지 않은 차량입니다. 제원이 있어야 매칭할 수 있습니다.</p>
      )}
      {specState === "error" && (
        <p className="spec-line warn">제원을 불러오지 못했습니다.</p>
      )}

      {specState === "ok" && (
        <div className="spec-box">
          {model && <p className="spec-line">{model}</p>}
          {dims && <p className="spec-line">적재함 {dims}</p>}
          <p className="spec-line">
            적재함 체적 <b>{spec.capacity_cbm ?? spec.cargo_capacity_cbm} CBM</b>
            {" · "}최대 적재 {spec.max_payload_kg}kg
          </p>
          {/* 적재중량을 굳이 보여주는 이유: 이 값이 0이 아니면 잔여 중량이 줄어
              "왜 후보가 적지?"의 답이 여기 있다. */}
          <p className="spec-line">
            현재 적재 {loaded ?? 0}kg
            {(loaded ?? 0) === 0 && <span className="muted"> · 빈 차 기준으로 계산합니다</span>}
          </p>
          {/* 제원 출처. 합성 제원을 등록 원장처럼 보이게 두면 그걸 근거로 실제 배차를
              하게 된다. 어디서 온 숫자인지 화면이 말해야 한다. */}
          <p className="spec-line muted">{specSource(spec)}</p>
        </div>
      )}

      {/* 파렛트 적재. 켜면 깔판 높이와 바닥 자투리를 빼고 계산한다 — 화물만 재고
          파렛트를 빼먹으면 CBM이 실제보다 크게 잡혀 현장에서 남는다. */}
      <label className="checkline">
        <input type="checkbox" checked={palletized}
               onChange={(e) => onPalletizedChange(e.target.checked)} />
        <span>
          파렛트로 적재
          <span className="muted"> · 깔판 높이(144mm)와 바닥 자투리를 빼고 계산합니다</span>
        </span>
      </label>

      {/* 후보 상한. 많이 볼수록 더 많이 실리지만 조회·계산 시간이 함께 늘어난다.
          기본값은 서버가 정하고, 여기서는 그 값을 비워 두는 것으로 쓴다. */}
      <label className="field-label" htmlFor="candidateLimit">검토할 후보 수</label>
      <select id="candidateLimit" className="text-input" value={candidateLimit}
              onChange={(e) => onCandidateLimitChange(e.target.value)}>
        {CANDIDATE_OPTIONS
          .filter((n) => !candidateLimitMax || n <= candidateLimitMax)
          .map((n) => (
            <option key={n} value={n}>{n.toLocaleString()}건</option>
          ))}
      </select>
      <p className="spec-line muted">
        {candidateLimitUsed
          ? `직전 계산은 ${candidateLimitUsed.toLocaleString()}건을 검토했습니다.`
          : "많이 볼수록 더 많이 실리지만 계산이 오래 걸립니다."}
        {candidateLimitMax && ` 최대 ${candidateLimitMax.toLocaleString()}건.`}
      </p>

      <button
        type="button"
        className="btn primary block"
        onClick={onRun}
        disabled={busy || !truckId || specState === "none"}
      >
        {busy ? runningLabel : ranAt ? "매칭 갱신" : "추가 상차 가능 운송장 조회"}
      </button>

      {/* 아무 표시 없이 수십 초가 흐르면 사용자는 버튼이 먹었다고 판단하고 다시 누른다.
          남은 시간을 세어 주고, 예상을 넘기면 넘겼다고 말한다 — 끝나간다고 우기면
          그때부터는 화면을 못 믿는다. */}
      {busy && (
        <div className="run-progress">
          <div className="run-bar">
            <span className="run-bar-value"
                  style={{ width: `${Math.min(100, (elapsed / estimate) * 100)}%` }} />
          </div>
          <p className="spec-line muted">
            {overrun
              ? `예상보다 오래 걸립니다 · ${elapsed}초 경과 (후보 ${Number(candidateLimit || 10000).toLocaleString()}건)`
              : `${elapsed}초 경과 · 예상 ${estimate}초`}
          </p>
        </div>
      )}

      {ranAt && (
        // 자동 갱신을 없앴으므로 화면의 숫자가 언제 것인지 화면이 말해줘야 한다.
        <p className="spec-line muted">
          기준 시각 {ranAt.toLocaleTimeString("ko-KR")} · 갱신하려면 버튼을 누르세요
        </p>
      )}
    </section>
  );
}
