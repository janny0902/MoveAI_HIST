// 화주사 운송장 등록. 입력 항목이 체적 측정기 CSV(17컬럼)와 **같은 모양**이다.
//
// 화면에서 체적(CBM)과 중량(kg)을 받지 않는 이유: 원본 CSV에 그 컬럼이 없다. 측정기가
// 주는 건 가로·세로·높이(mm)와 작업터미널 코드뿐이고, 체적은 치수에서 계산하고 중량은
// 상품코드별 밀도로 추정하며 상차좌표는 터미널 코드로 푼다. 그 규칙을 화면에도 두면
// 서버와 어긋날 때 조용히 다른 값이 저장된다. 계산은 서버 한 곳에서만 한다
// (matching-processor/waybill_schema.py, docs/05-matching-processor.md MAT-10).
//
// 대량 적재는 이 경로가 아니다. 수십만~수백만 건은 CSV를 GCS 적재 버킷에 올린다.
import { matchingBase } from "./api";

/** 박스타입. 실제 파일에 나오는 값 그대로다(측정기의 규격 분류). */
export const BOX_TYPES = ["A", "B", "C", "D", "E", "S"];

/**
 * 박스타입별 자동 운임(원) — matching-processor CARGO_FREIGHT_BY_BOX_TYPE 과 동일.
 * 박스 외(행낭·파렛트 등)는 화주 직접 입력.
 */
export const BOX_FREIGHT_BY_TYPE = {
  S: 5000,
  A: 6000,
  B: 7500,
  C: 9000,
  D: 11000,
  E: 13000,
};

/** 상품코드 -> 상품명 */
export const PRODUCT_CODES = [
  { code: "Box", name: "박스", autoFreight: true },
  { code: "Bag", name: "행낭", autoFreight: false },
  { code: "Pallet", name: "파렛트", autoFreight: false },
  { code: "Poly", name: "폴리백", autoFreight: false },
  { code: "Sack", name: "포대", autoFreight: false },
  { code: "Vinyl", name: "기타", autoFreight: false },
];

export function isBoxProduct(productCode) {
  return String(productCode || "").toLowerCase() === "box";
}

export function productLabel(productCode) {
  const found = PRODUCT_CODES.find((p) => p.code === productCode);
  return found ? found.name : productCode || "화물";
}

/** 박스 행 배열 → 자동 운임 합계 */
export function computeBoxFreight(boxes) {
  return (boxes || []).reduce((sum, b) => {
    const t = String(b.boxType || "A").toUpperCase();
    return sum + (BOX_FREIGHT_BY_TYPE[t] ?? BOX_FREIGHT_BY_TYPE.A);
  }, 0);
}

/** 측정기 치수(mm) -> 체적(CBM). 표시용이고, 저장값은 서버가 같은 식으로 다시 만든다. */
export function boxVolumeCbm({ boxWidthMm, boxDepthMm, boxHeightMm }) {
  const w = Number(boxWidthMm);
  const d = Number(boxDepthMm);
  const h = Number(boxHeightMm);
  if (!(w > 0 && d > 0 && h > 0)) return null;
  return (w * d * h) / 1e9;
}

/** 등록된 작업터미널. 여기 없는 코드로는 상차지를 만들 수 없어 등록이 거부된다. */
export async function fetchTerminals() {
  const res = await fetch(`${matchingBase()}/v1/terminals`, { cache: "no-store" });
  if (!res.ok) throw new Error(`작업터미널 목록을 불러오지 못했습니다 (${res.status})`);
  const body = await res.json();
  return body.terminals || [];
}

/** 화면 상태를 서버 필드명으로. CSV 컬럼명과 1:1이다. */
export function toWaybillPayload(
  { waybillNo, originTerminalCode, destinationTerminalCode, productCode, productName, createdAt },
  boxes
) {
  return {
    boxes: boxes.map((b) => ({
      waybill_no: waybillNo.trim(),
      box_type: b.boxType || null,
      box_width_mm: Number(b.boxWidthMm),
      box_depth_mm: Number(b.boxDepthMm),
      box_height_mm: Number(b.boxHeightMm),
      origin_terminal_code: originTerminalCode,
      destination_terminal_code: destinationTerminalCode || null,
      product_code: productCode || null,
      product_name: productName || null,
      source_created_at: createdAt ? new Date(createdAt).toISOString() : null,
    })),
  };
}

/**
 * 운송장 하나를 등록한다. 같은 운송장의 박스가 여러 개면 서버가 체적을 합산한다.
 * @returns 적재 결과(written/waybills/unknown_terminals...)
 */
export async function registerWaybill(payload) {
  const res = await fetch(`${matchingBase()}/v1/waybills`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = `등록 실패 (${res.status})`;
    try {
      const body = await res.json();
      if (body.detail) {
        detail =
          typeof body.detail === "string"
            ? body.detail
            : (body.detail[0]?.reason || JSON.stringify(body.detail));
      }
    } catch { /* JSON이 아니면 기본 메시지 */ }
    throw new Error(detail);
  }
  return res.json();
}

/**
 * 관리자 단건 등록 후 기사 복화(OD 그룹)에도 즉시 반영.
 */
export async function bridgeToDriverOdGroup({
  waybillNo,
  originTerminalCode,
  destinationTerminalCode,
  boxCount,
  volumeM3,
  productCode,
  productName,
  freightKrw,
  photoUrl,
}) {
  const res = await fetch("/api/dispatch/od-items", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      externalCargoId: waybillNo,
      originTerminalCode,
      destinationTerminalCode,
      boxCount: boxCount || 1,
      volumeM3: volumeM3 || 0.05,
      productCode: productCode || "Box",
      productName: productName || "박스",
      freightKrw: freightKrw != null ? Number(freightKrw) : null,
      photoUrl: photoUrl || null,
    }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`기사 OD 반영 실패 (${res.status}) ${text.slice(0, 160)}`);
  }
  return res.json();
}

/** 바닥 적재 더미 사진 → 치수(mm)·체적·차종별 점유율 (+ photoUrl 저장) */
export async function analyzeFloorCargo(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/load/analyze-floor", {
    method: "POST",
    body: fd,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`사진 분석 실패 (${res.status}) ${text.slice(0, 160)}`);
  }
  return res.json();
}

/** 사진만 업로드 (분석 없음) */
export async function uploadCargoPhoto(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/load/cargo-photo", { method: "POST", body: fd });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`사진 업로드 실패 (${res.status}) ${text.slice(0, 120)}`);
  }
  return res.json();
}

/** 체적(m³) → 차종별 점유율 */
export async function fetchFillPreview(volumeM3) {
  const res = await fetch(`/api/dispatch/fill-preview?volumeM3=${encodeURIComponent(volumeM3)}`);
  if (!res.ok) throw new Error(`점유율 조회 실패 (${res.status})`);
  return res.json();
}

export const DEMO_RESET_AT_KEY = "moveai_demo_reset_at";
export const DEMO_EPOCH_KEY = "moveai_demo_epoch";

/** 시연 데이터 초기화 (데모 물량 재시드 + 차량 공차 + 정산 비움) */
export async function resetDemoData() {
  const res = await fetch("/api/dispatch/demo-reset", { method: "POST" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`시연 초기화 실패 (${res.status}) ${text.slice(0, 160)}`);
  }
  const data = await res.json();
  try {
    localStorage.setItem(DEMO_RESET_AT_KEY, String(Date.now()));
    if (data?.epoch != null) localStorage.setItem(DEMO_EPOCH_KEY, String(data.epoch));
  } catch (_) { /* ignore */ }
  return data;
}
