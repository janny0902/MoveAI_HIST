// [교체 가능] 표현 계층.
// 계약: vision / matching은 백엔드 응답 그대로다. 필드 이름을 바꾸지 말 것 —
// 백엔드 계약(설계서 5.3)과 1:1로 대응한다.
//
// 표시 규칙은 유지할 것:
//   1) LIMITED 품질과 직선거리 추정 우회시간을 반드시 밝힌다. 추정치를 실측처럼 보이면 안 된다.
//   2) 가려진 공간이 사용 가능 공간에서 제외됐다는 사실을 알린다(설계서 4.9/4.11).
//   3) 숫자만 던지지 말고 감산 과정을 함께 보인다. 문장은 ../lib/explain.js가 만든다.
import { failureText } from "../lib/useAnalysis";
import { explainResult, parcelText } from "../lib/explain";

const cbm = (v) => (v === null || v === undefined ? "-" : `${Number(v).toFixed(2)} CBM`);
const signed = (v) => (v == null ? null : `${v > 0 ? "+" : "−"}${Math.abs(v).toFixed(2)}`);

export default function ResultCard({ vision, matching }) {
  if (!vision) return null;

  const canLoad = Boolean(matching?.can_load);
  const explain = explainResult(vision, matching);

  // 판정에 실제로 쓰인 공간을 보여준다. Vision의 usable_free_cbm은 품질 추가 감액
  // 전 값이라, 그걸 표에 쓰면 "사용 가능 공간 − 실은 화물 = 남는 공간"이 맞지 않는다.
  const effectiveFree = matching?.usable_free_cbm ?? vision.usable_free_cbm;

  const rows = [
    ["판정에 쓴 사용 가능 공간", cbm(effectiveFree)],
    ["사진에서 추정한 여유 공간", cbm(vision.estimated_free_cbm)],
    ["가려져서 못 본 공간", cbm(vision.unknown_cbm)],
    ["사진 품질", `${vision.quality_status} (${Number(vision.quality_score).toFixed(2)})`],
  ];

  if (matching) {
    rows.push([
      "실을 수 있는 남은 중량",
      matching.remaining_weight_kg != null ? `${matching.remaining_weight_kg} kg` : "-",
    ]);
    (matching.selected_cargos || []).forEach((c) => {
      rows.push([
        `${c.pickup_order}. ${c.cargo_id}`,
        `${c.volume_cbm} CBM / ${c.weight_kg} kg${c.weight_source === "ESTIMATED" ? " (중량 추정)" : ""}`,
      ]);
    });
    rows.push(["상차 후 남는 공간", cbm(matching.final_free_cbm)]);
  }

  const notes = [];
  if (vision.quality_status === "LIMITED") {
    notes.push("품질이 충분하지 않아 보수적으로 계산했습니다. 화물칸 전체가 보이게 다시 찍으면 정확해집니다.");
  }
  if (matching?.route_source === "HAVERSINE_FALLBACK") {
    notes.push("우회시간은 직선거리 기반 추정치입니다.");
  }
  notes.push("가려진 공간은 직접 관측할 수 없어 사용 가능 공간에서 제외했습니다.");
  // 사진 속 화물을 "추가로 실을 후보"로 오해하는 경우가 있어 명시한다.
  notes.push("사진에 보이는 짐은 이미 실린 것으로 보고, 남은 공간에 주변 대기 운송장을 넣어 계산했습니다.");

  return (
    <section className="card">
      <p className={`verdict ${canLoad ? "ok" : "bad"}`}>
        {canLoad ? "추가 상차 가능" : "추가 상차 불가"}
      </p>
      <p className="sub">
        {canLoad
          ? `${matching.selected_cargos.length}건을 실을 수 있습니다.` +
            (effectiveFree != null ? ` (남은 공간 ${parcelText(matching.final_free_cbm)})` : "")
          : // vision의 사유가 더 구체적이다. matching은 품질 문제를 quality_rejected
            // 하나로만 알아서, 왜 그런지는 vision 쪽에만 있다.
            vision.failure_reason
            ? failureText(vision.failure_reason)
            : matching
              ? failureText(matching.failure_reason)
              : "매칭 결과를 아직 받지 못했습니다."}
      </p>

      <table className="result-table">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}>
              <th>{k}</th>
              <td>{v}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* 상차 계획. "실을 수 있다"만으로는 갈지 말지 정할 수 없다 —
          어디에 들러서, 얼마나 돌아가고, 얼마를 더 버는지가 있어야 판단이 된다. */}
      {canLoad && matching.pickup_stops?.length > 0 && (
        <div className="plan">
          <div className="plan-head">
            <span>상차 계획</span>
            <span className="plan-gain">+{Math.round(matching.added_commission_krw).toLocaleString()}원</span>
          </div>
          {matching.pickup_stops.map((s, i) => (
            <div className="plan-stop" key={`${s.lat},${s.lng}`}>
              <div className="plan-stop-head">
                <b>{i + 1}. {s.terminal_name || s.terminal_code || "상차지"}</b>
                <span>+{Math.round(s.revenue_krw).toLocaleString()}원</span>
              </div>
              {s.address && <div className="plan-addr">{s.address}</div>}
              <div className="plan-figures">
                <span>{s.cargo_count}건</span>
                <span>{s.volume_cbm.toFixed(2)} CBM</span>
                <span>{Math.round(s.weight_kg)} kg</span>
                {s.detour_seconds != null && (
                  <span>돌아가는 시간 {Math.round(s.detour_seconds / 60)}분</span>
                )}
              </div>
            </div>
          ))}
          <p className="hint">
            직행 대비 <b>{Math.round(matching.added_detour_seconds / 60)}분</b>만 더 쓰면
            수수료 <b>{Math.round(matching.added_commission_krw).toLocaleString()}원</b>을 더 받습니다.
            {matching.added_freight_krw > 0 && (
              <> (운임 {Math.round(matching.added_freight_krw).toLocaleString()}원 규모)</>
            )}{" "}
            건당 수수료로 계산한 추정치입니다.
          </p>
        </div>
      )}

      {explain && (
        <>
          {explain.reasons.length > 0 && (
            <div className="why">
              {explain.reasons.map((r) => <p key={r}>{r}</p>)}
            </div>
          )}

          {explain.budgets.length > 0 && (
            <div className="budgets">
              {explain.budgets.map((b) => {
                const pct = b.limit > 0 ? Math.min(100, Math.max(0, (b.used / b.limit) * 100)) : 0;
                return (
                  <div className="budget" key={b.axis}>
                    <div className="budget-head">
                      <span>{b.axis} 사용률</span>
                      <span>
                        {b.used.toFixed(2)} / {b.limit.toFixed(2)} {b.unit}
                        <b> ({Math.round(pct)}%)</b>
                      </span>
                    </div>
                    <div className="budget-bar"><span style={{ width: `${pct}%` }} /></div>
                    <div className="budget-foot">
                      남은 여유 {b.left.toFixed(2)} {b.unit}
                      {b.note ? ` · ${b.note}` : ""}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          <details className="explain">
            <summary>이 숫자가 나온 과정 보기</summary>
            <ol className="explain-steps">
              {explain.steps.map((s) => (
                <li key={s.label}>
                  <div className="explain-head">
                    <span className="explain-label">{s.label}</span>
                    <span className="explain-value">
                      {s.delta != null && <em>{signed(s.delta)}</em>}
                      <b>{Number(s.value).toFixed(2)} {s.unit}</b>
                    </span>
                  </div>
                  <p className="explain-why">{s.why}</p>
                  <p className="explain-scale">{parcelText(s.value)}</p>
                </li>
              ))}
            </ol>
          </details>

          <details className="explain">
            <summary>{explain.glossary.term}가 뭔가요? — {explain.glossary.short}</summary>
            <p className="explain-why">{explain.glossary.full}</p>
          </details>
        </>
      )}

      <p className="hint">{notes.join(" ")}</p>
    </section>
  );
}
