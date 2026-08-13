// 화주사 운송장 등록. matching-processor가 pending_cargos를 소유한다.
//
// 이 화면은 **건당 등록·보정용**이다. 수십만~수백만 건은 체적 측정기가 내보낸 17컬럼 CSV를
// GCS 적재 버킷에 올리는 경로를 쓴다(docs/05-matching-processor.md MAT-10). 웹 폼으로
// 그 규모를 넣을 수 없다.
//
// 두 경로는 중량 출처가 다르다. 여기서 넣은 값은 weight_source="DECLARED", 파일 적재분은
// 체적×밀도 추정이라 "ESTIMATED"다. 원본 운송장 파일에 중량 컬럼이 없기 때문이다.
import { matchingBase } from "./api";

/** 등록 한 건. 체적·중량·상차좌표가 매칭 판정의 근거라 필수다. */
export async function registerCargo(cargo) {
  const res = await fetch(`${matchingBase()}/v1/cargos`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cargo),
  });
  if (!res.ok) {
    let detail = `등록 실패 (${res.status})`;
    try {
      const body = await res.json();
      if (body.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch { /* JSON이 아니면 기본 메시지 */ }
    throw new Error(detail);
  }
  return res.json();
}

/** 화면에서 만든 값을 백엔드 필드명으로 바꾼다. 서버 스키마와 1:1로 맞춘다. */
export function toCargoPayload({ cargoId, volumeCbm, weightKg, pickup, delivery, deadlineAt, revenueKrw }) {
  return {
    cargo_id: cargoId.trim(),
    volume_cbm: Number(volumeCbm),
    weight_kg: Number(weightKg),
    pickup_lat: pickup.lat,
    pickup_lng: pickup.lng,
    pickup_address: pickup.address,
    delivery_lat: delivery ? delivery.lat : null,
    delivery_lng: delivery ? delivery.lng : null,
    delivery_address: delivery ? delivery.address : null,
    revenue_krw: revenueKrw ? Number(revenueKrw) : null,
    // datetime-local은 타임존이 없는 문자열을 준다. 서버가 UTC로 간주하지 않도록
    // 브라우저 타임존 기준 ISO로 바꿔 보낸다.
    deadline_at: deadlineAt ? new Date(deadlineAt).toISOString() : null,
    status: "WAITING",
  };
}
