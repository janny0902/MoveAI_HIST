// 결과 설명(XAI). 숫자가 어떻게 나왔는지를 사람이 검산할 수 있는 형태로 풀어쓴다.
//
// 왜 필요한가: 화면이 "2.72 CBM, 1건 가능"만 보여주면 사용자는 두 가지를 할 수 없다.
//   1. 값이 맞는지 확인 — 사진에는 공간이 많이 남아 보이는데 왜 1건인지 알 수 없다.
//   2. 값이 틀렸을 때 원인 지목 — 차량 제원이 틀린 건지, 사진이 나쁜 건지, 중량이
//      걸린 건지 구분할 수 없다.
// 그래서 최종값이 아니라 **감산 과정**을 그대로 보여준다. 각 단계는 앞 단계에서
// 무엇을 얼마나 뺐는지와 그 이유를 함께 갖는다.
//
// 이 파일은 계산을 새로 하지 않는다. 백엔드가 낸 값을 배열로 늘어놓을 뿐이다.
// 여기서 CBM을 다시 계산하면 화면과 저장값이 갈라진다.

/** 택배 상자 1개를 40 × 30 × 30 cm로 본다. 부피를 감으로 잡기 위한 환산 기준. */
const PARCEL_CBM = 0.4 * 0.3 * 0.3;

export const CBM_GLOSSARY = {
  term: "CBM",
  short: "부피를 세는 단위 (m³)",
  full:
    "CBM은 Cubic Meter, 우리말로 '세제곱미터'입니다. 1 CBM은 가로·세로·높이가 " +
    "각각 1미터인 정육면체의 부피이고, 택배 상자(40×30×30cm)로 치면 약 27개 분량입니다. " +
    "화물칸에 짐이 얼마나 들어가는지를 무게가 아니라 부피로 재는 단위라고 보면 됩니다.",
};

/** 0.72 -> "택배 상자 약 20개" */
export function parcelText(cbm) {
  if (cbm == null) return null;
  const n = Math.round(Number(cbm) / PARCEL_CBM);
  return n > 0 ? `택배 상자 약 ${n}개` : "택배 상자 1개도 어려운 크기";
}

const n2 = (v) => (v == null ? null : Number(v).toFixed(2));

/**
 * 공간이 줄어드는 과정을 단계 배열로 만든다.
 * 각 단계: { label, value, unit, delta, why }
 *   value = 그 단계까지 남은 값, delta = 이 단계에서 뺀 양(음수), why = 뺀 이유.
 */
function spaceSteps(vision, matching) {
  const steps = [];
  const push = (label, value, delta, why) =>
    steps.push({ label, value, unit: "CBM", delta, why });

  if (vision.capacity_cbm != null) {
    push(
      "적재함 전체",
      vision.capacity_cbm,
      null,
      `등록된 적재함 치수 ${n2(vision.cargo_width_m)} × ${n2(vision.cargo_length_m)} × ` +
      `${n2(vision.cargo_height_m)} m를 곱한 값입니다. 사진 한 장으로는 절대 크기를 알 수 없어, ` +
      "이 치수를 자 삼아 사진 속 거리를 실제 미터로 환산합니다. 그래서 등록 제원과 다른 차량을 " +
      "찍으면 아래 숫자가 전부 어긋납니다."
    );
  }

  if (vision.occupied_cbm != null) {
    push(
      "이미 실린 짐",
      vision.occupied_cbm,
      -vision.occupied_cbm,
      "사진에서 짐으로 인식된 부분이 차지한 부피입니다."
    );
  }

  if (vision.unknown_cbm != null && vision.unknown_cbm > 0) {
    push(
      "가려져서 못 본 공간",
      vision.unknown_cbm,
      -vision.unknown_cbm,
      "짐 뒤나 사각지대라 카메라에 안 잡힌 부분입니다. 비어 있을 수도 있지만 확인이 안 되므로 " +
      "'쓸 수 있다'고 세지 않습니다. 잘못 세면 실제로 안 들어가는 화물을 배차하게 됩니다."
    );
  }

  if (vision.observed_free_cbm != null) {
    push(
      "사진에서 빈 공간으로 확인된 부피",
      vision.observed_free_cbm,
      null,
      "여기까지가 카메라가 실제로 '비어 있다'고 관측한 양입니다."
    );
  }

  if (vision.usable_free_cbm != null) {
    const pct = vision.safety_factor != null
      ? `${Math.round((1 - vision.safety_factor) * 100)}%`
      : "일부";
    push(
      "안전 여유를 뺀 실제 사용 가능 공간",
      vision.usable_free_cbm,
      vision.observed_free_cbm != null
        ? vision.usable_free_cbm - vision.observed_free_cbm
        : null,
      `빈 공간이라고 해서 그 부피를 100% 채울 수는 없습니다. 상자 모양이 제각각이고 통로도 ` +
      `있어야 해서 ${pct}를 미리 뺍니다.`
    );
  }

  // Matching이 실제로 쓴 값이 Vision의 값보다 작을 수 있다(품질 LIMITED 추가 감액).
  // 이 단계를 감추면 표의 '사용 가능 공간'과 '상차 후 남는 공간'의 뺄셈이 맞지 않아
  // 사용자가 화면을 신뢰할 수 없게 된다.
  const effective = matching?.usable_free_cbm;
  if (effective != null && vision.usable_free_cbm != null && effective < vision.usable_free_cbm - 0.001) {
    const cut = Math.round((1 - effective / vision.usable_free_cbm) * 100);
    push(
      "사진 품질이 낮아 한 번 더 줄인 값",
      effective,
      effective - vision.usable_free_cbm,
      `품질 판정이 LIMITED라 ${cut}%를 추가로 뺐습니다. 화물칸 전체가 프레임에 들어오게 ` +
      "다시 찍으면 이 감액이 사라집니다."
    );
  }

  return steps;
}

/** 화물을 고른 뒤 무엇이 얼마나 남았는지. 공간과 중량 두 축을 나란히 본다. */
function budgets(vision, matching) {
  if (!matching) return [];
  const selected = matching.selected_cargos || [];
  const usedCbm = selected.reduce((s, c) => s + (c.volume_cbm || 0), 0);
  const usedKg = selected.reduce((s, c) => s + (c.weight_kg || 0), 0);

  const out = [];
  if (matching.usable_free_cbm != null) {
    out.push({
      axis: "공간",
      limit: matching.usable_free_cbm,
      used: usedCbm,
      left: matching.final_free_cbm != null ? matching.final_free_cbm : matching.usable_free_cbm - usedCbm,
      unit: "CBM",
    });
  }
  if (matching.remaining_weight_kg != null) {
    out.push({
      axis: "중량",
      limit: matching.remaining_weight_kg,
      used: usedKg,
      left: matching.remaining_weight_kg - usedKg,
      unit: "kg",
      note:
        vision.max_payload_kg != null && vision.current_loaded_weight_kg != null
          ? `최대 적재 ${vision.max_payload_kg}kg − 현재 실린 ${vision.current_loaded_weight_kg}kg`
          : null,
    });
  }
  return out;
}

/**
 * "왜 이 결과인가"를 문장으로. 둘 중 어느 제약이 먼저 막았는지 짚는다.
 * 어느 쪽이 걸렸는지 모르면 사용자는 사진을 다시 찍어야 할지, 짐을 덜어야 할지 모른다.
 */
function verdictReasons(matching, budgetList) {
  if (!matching) return [];
  const reasons = [];
  const count = (matching.selected_cargos || []).length;

  // 한 건도 못 실은 경우와 실은 뒤 더 못 실은 경우는 원인 문장이 달라야 한다.
  // 0건인데 "0.00CBM를 썼고 ...만 남아 다음 후보가 안 들어갔다"고 하면 앞뒤가 맞지 않는다.
  if (!matching.can_load) {
    const space = budgetList.find((b) => b.axis === "공간");
    reasons.push(
      `주변 대기 화물 ${matching.candidate_count}건을 검토했지만 한 건도 싣지 못했습니다. ` +
      (space
        ? `남은 공간이 ${round(space.limit)}CBM(${parcelText(space.limit)})뿐이라, ` +
          "이보다 작은 화물이 주변에 없었습니다."
        : "공간이나 중량 한도를 넘지 않는 화물이 없었습니다.")
    );
    return reasons;
  }

  // "왜 실을 수 있는가"는 세 가지가 동시에 성립했다는 뜻이다. 그 셋을 숫자로 말한다.
  const space = budgetList.find((b) => b.axis === "공간");
  const weight = budgetList.find((b) => b.axis === "중량");
  reasons.push(
    `주변 대기 화물 ${matching.candidate_count}건 중 ${count}건을 골랐습니다. ` +
    (space ? `남은 공간 ${round(space.limit)}CBM에 ${round(space.used)}CBM이 들어가고, ` : "") +
    (weight ? `남은 중량 ${round(weight.limit)}kg에 ${round(weight.used)}kg이 들어가며, ` : "") +
    "돌아가는 시간을 감안해도 운임이 남는 조합입니다."
  );

  // 남은 여유가 적은 쪽이 다음 화물을 막은 축이다.
  const tight = [...budgetList]
    .filter((b) => b.limit > 0)
    .sort((a, b) => a.left / a.limit - b.left / b.limit)[0];
  if (tight) {
    reasons.push(
      `여기서 더 싣지 못한 이유는 ${tight.axis}입니다. ${tight.axis} 한도 ` +
      `${round(tight.limit)}${tight.unit} 중 ${round(tight.used)}${tight.unit}를 써서 ` +
      `${round(tight.left)}${tight.unit}가 남았고, 다음 후보가 여기에 들어가지 않았습니다.`
    );
  }
  return reasons;
}

const round = (v) => (v == null ? "-" : Number(v).toFixed(Math.abs(v) >= 100 ? 0 : 2));

/** 화면이 그대로 렌더할 수 있는 설명 묶음. vision이 없으면 null. */
export function explainResult(vision, matching) {
  if (!vision) return null;
  const budgetList = budgets(vision, matching);
  return {
    glossary: CBM_GLOSSARY,
    steps: spaceSteps(vision, matching),
    budgets: budgetList,
    reasons: verdictReasons(matching, budgetList),
  };
}
