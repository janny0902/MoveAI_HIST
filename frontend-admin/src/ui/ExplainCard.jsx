// [교체 가능] 결과가 어떻게 나왔는지 푸는 카드 (XAI).
//
// 화물 관리자는 최적화 이론을 모른다. 숫자만 보면 "왜 1,743건인가", "왜 100%인가"에
// 답이 없고, 답이 없으면 그 숫자를 믿고 배차하지 못한다.
//
// 그리고 어디까지가 AI인지 분명히 적는다. 단순 곱셈까지 AI라고 부르면 정작 진짜
// 판단을 맡긴 부분(조합 최적화)이 묻히고, 나중에 결과가 틀렸을 때 무엇을 의심해야
// 할지 알 수 없게 된다. 단계마다 계산 방식을 라벨로 붙인다.
//
// 규칙 하나: 여기서 값을 다시 계산하지 않는다. 모든 숫자는 서버 응답 그대로다.
import { useState } from "react";

const n = (v, d = 2) => (v == null ? "-" : Number(v).toFixed(d));

// 계산 방식 라벨. 무엇이 AI이고 무엇이 산수인지 한 단어로 구분한다.
const KIND = {
  math: { label: "단순 계산", cls: "kind-math" },
  stat: { label: "통계 추정", cls: "kind-stat" },
  ai: { label: "AI · 조합 최적화", cls: "kind-ai" },
  off: { label: "이번엔 미사용", cls: "kind-off" },
};

export default function ExplainCard({ matching, spec }) {
  const [open, setOpen] = useState(false);
  if (!matching) return null;

  const capacity = matching.usable_free_cbm || 0;
  const loaded = Math.max(0, capacity - (matching.final_free_cbm ?? capacity));
  const pct = capacity > 0 ? (loaded / capacity) * 100 : 0;
  const picked = (matching.selected_cargos || []).length;
  const groups = (matching.terminal_groups || []).length;
  // 실제로 어떤 방식으로 골랐는지에 따라 설명을 바꾼다. 그리디로 떨어졌는데
  // "최적화 솔버가 골랐다"고 쓰면 설명이 거짓이 된다.
  const status = matching.solver_status || "";
  const greedy = status.startsWith("GREEDY_FILL");
  const optimal = status === "OPTIMAL";

  const steps = [
    {
      kind: "math",
      title: matching.pallet_mode
        ? "1. 적재 공간을 정한다 — 파렛트 기준"
        : "1. 적재 공간을 정한다 — 낱개 적재 기준",
      body: matching.pallet_mode ? (
        <>
          적재함 치수
          {spec?.cargo_length_m
            ? ` ${n(spec.cargo_length_m)}×${n(spec.cargo_width_m)}×${n(spec.cargo_height_m)}m`
            : ""}
          를 그대로 곱하면 {n(matching.raw_capacity_cbm)} CBM이지만, 파렛트에 실으면
          그만큼 못 씁니다.
          <br />
          <span className="xai-inline">
            ① 깔판 높이 144mm → 쌓을 수 있는 높이가 그만큼 줄어듭니다<br />
            ② 바닥 자투리 → 1,100mm 규격이 적재함 폭·길이로 나누어떨어지지 않아
            남는 폭이 통째로 죽습니다 (<b>{matching.pallet_count}장</b> 배치)<br />
            ③ 파렛트 위 빈틈 → 규격이 제각각인 소포는 파렛트를 꽉 채우지 못합니다
          </span>
          <br />
          셋을 빼면 <b>{n(capacity)} CBM</b>입니다. 차이가{" "}
          <b>{n(matching.pallet_loss_cbm)} CBM</b>인데, 이걸 빼먹으면 다 실린다고
          계산해 놓고 현장에서 남습니다.
        </>
      ) : (
        <>
          등록된 적재함 치수
          {spec?.cargo_length_m
            ? ` ${n(spec.cargo_length_m)}×${n(spec.cargo_width_m)}×${n(spec.cargo_height_m)}m`
            : ""}
          를 곱해 <b>{n(capacity)} CBM</b>을 얻습니다. 현재 적재량을 0으로 보므로 이 값이
          그대로 실을 수 있는 공간이 됩니다.
          <br />
          <span className="muted">
            파렛트를 쓰면 깔판 높이와 바닥 자투리만큼 줄어듭니다 — 위의 '파렛트로 적재'를
            켜면 그 기준으로 다시 계산합니다.
          </span>
        </>
      ),
      note: matching.pallet_mode
        ? `파렛트 배치는 나눗셈입니다(적재함 폭·길이 ÷ 1,100mm). 추정이 아니라 규격 계산입니다. 제원은 제조사 공개 제원${spec?.spec_template_id ? ` (${spec.spec_template_id})` : ""}입니다.`
        : `곱셈입니다. 추정도 학습도 들어가지 않습니다. 제원은 제조사 공개 제원${spec?.spec_template_id ? ` (${spec.spec_template_id})` : ""}입니다.`,
    },
    {
      kind: "math",
      title: "2. 운송장마다 부피를 낸다",
      body: (
        <>
          체적 측정기가 보낸 가로·세로·높이(mm)를 곱하고 10⁹으로 나눠 CBM으로 바꿉니다.
          측정기가 이미 잰 값이라 여기서도 계산은 산수입니다.
        </>
      ),
      note: "측정기 자체는 비전 기반이지만, 그 출력은 이 시스템 밖에서 이미 확정된 값입니다.",
    },
    {
      kind: "stat",
      title: "3. 무게를 추정한다",
      body: (
        <>
          원본에 <b>중량 컬럼이 없습니다.</b> 그래서 박스 규격(A~S)별 대표 중량으로
          채우고, 규격을 모르면 상품코드별 평균 밀도 × 부피로 되돌립니다. 과거 데이터에서
          뽑은 통계값을 적용하는 것이라 <b>학습 모델이 아니라 규칙 기반 추정</b>입니다.
        </>
      ),
      note: "그래서 중량은 실측이 아닙니다. 실제 무게가 추정보다 무거우면 중량 제약이 먼저 걸립니다.",
    },
    {
      kind: greedy ? "stat" : "ai",
      title: greedy
        ? "4. 실을 조합을 고른다 — 이번엔 규칙 기반으로 채웠습니다"
        : "4. 실을 조합을 고른다 — 이 단계가 AI입니다",
      body: greedy ? (
        <>
          대기 운송장 <b>{matching.candidate_count}건</b>을 <b>부피당 무게가 가벼운
          것부터</b> 차례로 담아 부피 {n(capacity)} CBM과 중량{" "}
          {matching.remaining_weight_kg}kg에 닿을 때까지 채웠습니다.
          <br />
          <span className="xai-inline">
            제약: 부피 합 ≤ {n(capacity)} CBM, 중량 합 ≤ {matching.remaining_weight_kg}kg
            <br />
            규칙: kg/CBM이 낮은 것부터 담기
          </span>
          <br />
          가벼운 것부터 담는 이유는 <b>중량이 먼저 차기 때문</b>입니다. 부피만 보고 작은
          것부터 담으면 소포가 부피당 무겁다 보니(A타입은 0.04CBM에 5kg) 중량 한도를
          먼저 써 버려 적재함이 절반도 안 찹니다.
          <br />
          <span className="muted">
            후보가 많아 최적화 솔버를 돌리지 않고 이 규칙으로 채웠습니다 —
            <b> 이론적 최적해라는 보장은 없습니다.</b>
          </span>
        </>
      ) : (
        <>
          대기 운송장 <b>{matching.candidate_count}건</b> 각각에 "싣는다/안 싣는다"를 정해야
          하는데, 가능한 경우의 수가 2<sup>{matching.candidate_count}</sup>입니다. 사람이나
          단순 정렬로는 못 푸는 크기라 <b>제약 충족 최적화 솔버(Google OR-Tools CP-SAT)</b>가
          풉니다.
          <br />
          <span className="xai-inline">
            제약: 부피 합 ≤ {n(capacity)} CBM, 중량 합 ≤ {matching.remaining_weight_kg}kg
            <br />
            목표: 실을 수 있는 양을 최대로
          </span>
          <br />
          솔버는 가지치기(branch-and-bound)로 답이 될 수 없는 조합을 통째로 잘라내며
          탐색합니다. 그리디하게 큰 것부터 담는 방식과 달리, 전체를 놓고 더 나은 조합이
          있는지를 따집니다.
        </>
      ),
      note: greedy
        ? `계산 방식 ${status} — 괄호 안이 최적화 솔버가 멈춘 이유입니다.`
        : optimal
          ? "솔버 상태 OPTIMAL — 이보다 나은 조합이 없다는 것을 증명하고 끝냈습니다."
          : `솔버 상태 ${status} — 유효한 해를 찾았지만 제한 시간 안에 "이게 최선"임을 증명하지는 못했습니다.`,
    },
    {
      kind: "math",
      title: "5. 결과를 묶는다",
      body: (
        <>
          고른 <b>{picked}건</b>을 출발·도착 작업터미널 쌍으로 묶어 <b>{groups}개</b> 그룹을
          만듭니다. 적재율은 실린 부피 {n(loaded)} ÷ 적재함 {n(capacity)} =
          {" "}<b>{pct.toFixed(1)}%</b>입니다.
        </>
      ),
      note: "기준 위치를 정하면 상차지까지의 직선거리로 다시 정렬합니다.",
    },
    {
      kind: "off",
      title: "쓰지 않은 것 — 사진 기반 공간 분석",
      body: (
        <>
          이 시스템에는 사진 한 장에서 적재함의 빈 공간을 재는 딥러닝 경로가 있습니다
          (Depth-Anything V2 깊이 추정 + OWL-ViT 물체 검출 + 포인트클라우드 복원).
          이번 계산은 <b>빈 차 기준</b>이라 추정할 빈 공간이 없어 그 경로를 타지 않았습니다.
        </>
      ),
      note: "이미 실린 화물이 있는 차를 재려면 그때 이 경로가 필요합니다.",
    },
  ];

  return (
    <section className="card xai">
      <div className="location-head">
        <span className="field-label">이 결과는 어떻게 나왔나</span>
        <button type="button" className="btn text" onClick={() => setOpen((v) => !v)}>
          {open ? "접기" : "계산 과정 보기"}
        </button>
      </div>

      <p className="xai-lead">
        측정 치수로 부피를 계산하고 규격별 대표 중량으로 무게를 추정한 뒤,
        {greedy
          ? <> <b>부피당 무게가 가벼운 것부터 채우는 규칙</b>으로 {matching.candidate_count}건
              중 부피·중량 제약에 맞는 만큼을 담았습니다.</>
          : <> <b>제약 충족 최적화 솔버(CP-SAT)</b>가 {matching.candidate_count}건 중
              부피·중량 제약을 지키면서 가장 많이 실리는 조합을 찾았습니다.</>}
      </p>
      <p className="xai-lead-sub">
        {greedy
          ? <>이번 계산에는 <b>AI 최적화가 쓰이지 않았습니다.</b> 솔버가 제한 시간 안에
              답을 내지 못해 규칙 기반으로 넘어갔습니다 — 결과는 유효하지만 최적해는
              아닙니다.</>
          : <>판단을 맡긴 단계는 <b>4번(조합 최적화)</b> 하나입니다. 나머지는 산수이거나
              규칙 기반 추정입니다.</>}
      </p>

      {open && (
        <>
          <ol className="xai-steps">
            {steps.map((s) => (
              <li key={s.title} className={KIND[s.kind].cls}>
                <p className="xai-step-title">
                  {s.title}
                  <span className="xai-kind">{KIND[s.kind].label}</span>
                </p>
                <p className="xai-step-body">{s.body}</p>
                <p className="xai-step-note">{s.note}</p>
              </li>
            ))}
          </ol>

          <table className="result-table xai-table">
            <tbody>
              <tr><th>판정 근거</th><td>{matching.decision_scope}</td></tr>
              <tr>
                <th>적재 방식</th>
                <td>{matching.pallet_mode
                  ? `파렛트 ${matching.pallet_count}장`
                  : "낱개 적재"}</td>
              </tr>
              <tr><th>선택 방식</th><td>{greedy ? "규칙 기반 채우기" : "OR-Tools CP-SAT"}</td></tr>
              <tr><th>상태</th><td>{status}</td></tr>
              <tr><th>검토한 후보</th><td>{matching.candidate_count}건</td></tr>
              <tr><th>경로 계산</th><td>{matching.route_source}</td></tr>
            </tbody>
          </table>

          <p className="xai-caveat">
            부피와 중량만 봤습니다. 상차지까지의 이동 시간, 실제 3D 적재 배치, 화물 간
            적재 순서와 하차 역순 문제는 이 계산에 들어 있지 않습니다. 화면의 상자 그림도
            적재율을 칸으로 나타낸 것이지 실제 배치가 아닙니다.
          </p>
        </>
      )}
    </section>
  );
}
