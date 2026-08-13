// 차량 제원 조회.
//
// 왜 촬영 화면에 제원을 보여줘야 하는가: 공간 분석은 등록된 적재함 치수를 기준
// 스케일로 삼는다(vision-processor/geometry_lite/truck_frame.py). 사진 한 장에서는
// 절대 크기를 알 수 없어서, 알려진 폭·높이에 맞춰 포인트 클라우드를 정규화하기
// 때문이다. 그래서 사진 속 차량이 등록 제원과 다르면 빈 공간 CBM이 통째로 어긋난다.
// 찍기 전에 "지금 이 번호는 1.2톤 냉동탑차로 등록돼 있다"를 볼 수 있어야 한다.
import { visionBase } from "./api";

/**
 * @returns 제원 객체. 등록되지 않은 차량이면 null (오류로 취급하지 않는다).
 * @throws 네트워크/서버 오류
 *
 * 404를 "미등록"으로 해석하지 않는다. 서버는 미등록 차량에도 200 + registered:false를
 * 주므로, 404는 **경로가 없다**는 뜻이다(구버전이 떠 있거나 배포 전). 실제로 이걸
 * 구분하지 않아 멀쩡히 등록된 T-000001이 화면에 "미등록"으로 떴다.
 */
export async function fetchTruckSpec(truckId) {
  const id = (truckId || "").trim();
  if (!id) return null;
  const res = await fetch(`${visionBase()}/v1/trucks/${encodeURIComponent(id)}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(
      res.status === 404
        ? "차량 제원 조회 경로를 찾을 수 없습니다. vision-processor 배포 상태를 확인하세요."
        : `차량 제원을 불러오지 못했습니다 (${res.status})`
    );
  }
  const body = await res.json();
  return body.registered === false ? null : body;
}

/**
 * 등록된 차량 목록.
 *
 * 번호를 직접 타이핑하게 두면 등록되지 않은 번호를 넣고 막힌다. 그리고 여기서 골라야
 * 하는 건 "내 차"가 아니라 지금 찍은 차와 제원이 맞는 차라, 목록에 적재함 크기와 중량이
 * 함께 보여야 한다.
 */
export async function fetchTruckList() {
  const res = await fetch(`${visionBase()}/v1/trucks`, { cache: "no-store" });
  if (!res.ok) throw new Error(`차량 목록을 불러오지 못했습니다 (${res.status})`);
  const body = await res.json();
  return body.trucks || [];
}

/** 선택 목록 한 줄. 제원으로 고를 수 있어야 하므로 부피와 중량을 함께 적는다. */
export function truckOptionText(t) {
  const parts = [t.truck_id];
  if (t.model) parts.push(t.model);
  if (t.capacity_cbm != null) parts.push(`${t.capacity_cbm} CBM`);
  if (t.max_payload_kg != null) parts.push(`${t.max_payload_kg}kg`);
  return parts.join(" · ");
}

/** "1.61 × 3.26 × 1.60 m" — 없으면 null. */
export function dimsText(spec) {
  if (!spec) return null;
  const { cargo_width_m: w, cargo_length_m: l, cargo_height_m: h } = spec;
  if ([w, l, h].some((v) => v == null)) return null;
  return `${w.toFixed(2)} × ${l.toFixed(2)} × ${h.toFixed(2)} m`;
}

/** "기아 봉고3 · 냉동탑차" 같은 한 줄. 없는 항목은 건너뛴다. */
export function modelText(spec) {
  if (!spec) return null;
  const BODY = {
    REFRIGERATED_BOX: "냉동탑차",
    BOX: "탑차",
    WING_BODY: "윙바디",
    CARGO: "카고",
    FLATBED: "평판",
  };
  return [spec.manufacturer, spec.model, BODY[spec.body_type] || spec.body_type]
    .filter(Boolean)
    .join(" · ") || null;
}
