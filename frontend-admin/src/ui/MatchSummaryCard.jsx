// [교체 가능] 표현 계층. 사진 없이 돌린 매칭의 요약.
//
// ResultCard를 쓰지 않는 이유: 그 카드는 사진 품질·가려져 못 본 공간처럼 vision 응답이
// 있어야만 뜻이 있는 항목으로 짜여 있다. 사진을 받지 않는 흐름에서 그 칸들은 전부
// 빈칸이거나 "해당 없음"이 되고, 그런 표는 읽는 사람을 헷갈리게 한다.
//
// 숫자는 서버 응답을 그대로 쓴다. 화면에서 다시 계산하지 않는다(UI_CONTRACT).
import CargoFillView, { fillHue } from "./CargoFillView";

const cbm = (v) => (v === null || v === undefined ? "-" : `${Number(v).toFixed(2)} CBM`);

export default function MatchSummaryCard({ matching, spec, selection }) {
  if (!matching) return null;

  // 적재율. 빈 차에서 시작하므로 0%에서 몇 %까지 차는지가 이 화면의 핵심 숫자다.
  // 분모는 적재함 전체(usable_free_cbm), 분자는 실제로 실린 체적이다.
  //
  // 구간을 골랐으면 고른 묶음만으로 다시 센다. 전체 적재율을 그대로 두면 "부산행만
  // 태우겠다"고 골라 놓고 전 구간을 실은 그림을 보게 된다.
  const capacity = matching.usable_free_cbm || 0;
  const fullLoaded = Math.max(0, capacity - (matching.final_free_cbm ?? capacity));
  const filtering = Boolean(selection?.filtered);
  const loadedCbm = filtering ? (selection.volumeCbm || 0) : fullLoaded;
  const pickedCount = filtering
    ? (selection.cargoCount || 0)
    : (matching.selected_cargos || []).length;
  const fillPct = capacity > 0 ? (loadedCbm / capacity) * 100 : 0;
  // 100%를 넘을 수 있다. 서버가 고른 조합은 늘 용량 안이지만, 구간을 여러 개 골라
  // 합치면 그 합이 차를 넘길 수 있다 — 그때 얼마나 모자란지가 배차 판단의 핵심이다.
  const over = loadedCbm > capacity;
  const shortfall = Math.max(0, loadedCbm - capacity);

  const rows = [
    ["적재함 빈 공간", cbm(matching.usable_free_cbm)],
  ];
  // 파렛트로 계산했으면 "왜 용량이 줄었나"에 답해야 한다. 원래 체적과 잃은 양을
  // 나란히 두지 않으면 숫자가 갑자기 작아진 것으로만 보인다.
  if (matching.pallet_mode) {
    rows.push(
      ["파렛트 적재 기준", `${matching.pallet_count}장 · ${matching.pallet_spec || ""}`],
      ["파렛트로 잃는 공간", `${cbm(matching.pallet_loss_cbm)} (원래 ${cbm(matching.raw_capacity_cbm)})`],
    );
  }
  rows.push(...[
    ["실을 수 있는 남은 중량",
      matching.remaining_weight_kg != null ? `${matching.remaining_weight_kg} kg` : "-"],
    ["검토한 후보", `${matching.candidate_count}건`],
  ]);

  // 수수료·운임·우회시간·손익분기는 두지 않는다. 그건 기사에게 "갈 만한가"를 묻는
  // 숫자고, 이 화면은 관리자가 "이 차에 얼마나 실리나"를 보는 곳이다.
  if (matching.can_load) {
    rows.push(
      over
        ? ["부족한 공간", cbm(shortfall)]
        : ["상차 후 남는 공간", cbm(capacity - loadedCbm)],
      [filtering ? "고른 구간의 운송장" : "실은 운송장", `${pickedCount}건`],
      ["실리는 무게", `${Math.round(selection?.weightKg ?? matching.selected_cargos
        .reduce((s, c) => s + (c.weight_kg || 0), 0)).toLocaleString()} kg`],
    );
  }

  return (
    <section className="card">
      <h2>{matching.can_load ? "추가 상차 가능" : "추가 상차 불가"}</h2>

      <div className="fill" style={{ "--fill-hue": fillHue(fillPct) }}>
        <div className="fill-head">
          <span className="fill-label">적재율</span>
          <span className="fill-pct">
            0% <span className="fill-arrow">→</span> <b>{fillPct.toFixed(1)}%</b>
          </span>
        </div>
        <div
          className="fill-bar"
          role="img"
          aria-label={`적재율 ${fillPct.toFixed(1)}퍼센트`}
        >
          <span className="fill-bar-value" style={{ width: `${Math.min(100, fillPct)}%` }} />
        </div>
        <p className="fill-sub">
          {filtering ? "고른 구간" : "아래 묶음"}을 모두 실으면{" "}
          <b>{loadedCbm.toFixed(2)} CBM</b>이 필요합니다
          {" · "}적재함 {capacity.toFixed(2)} CBM
          {over ? (
            // 넘치면 "남는 공간"이 음수가 된다. 음수를 그대로 보여주면 읽는 사람이
            // 부호를 해석해야 하므로, 모자란 양을 그대로 말한다.
            <b className="fill-over"> · {shortfall.toFixed(2)} CBM 부족</b>
          ) : (
            <> 중 {(capacity - loadedCbm).toFixed(2)} CBM 남음</>
          )}
          {filtering && (
            <span className="muted"> · 전체를 실으면 {fullLoaded.toFixed(2)} CBM</span>
          )}
        </p>
        {over && (
          <p className="fill-over-note">
            이 차 한 대로는 다 싣지 못합니다. 구간을 줄이거나 큰 차를 배차해야 합니다
            {spec?.cargo_length_m && ` — 지금 차는 ${capacity.toFixed(2)} CBM입니다`}.
          </p>
        )}
      </div>

      <CargoFillView
        capacityCbm={capacity}
        loadedCbm={loadedCbm}
        fillPct={fillPct}
        cargoCount={pickedCount}
        cargoWidthM={spec?.cargo_width_m}
        cargoLengthM={spec?.cargo_length_m}
        cargoHeightM={spec?.cargo_height_m}
        modelLabel={[spec?.manufacturer, spec?.model].filter(Boolean).join(" ") || null}
      />


      <table className="result-table">
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label}>
              <th>{label}</th>
              <td>{value}</td>
            </tr>
          ))}
        </tbody>
      </table>

    </section>
  );
}
