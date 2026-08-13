// 백엔드 계약. vision-processor / matching-processor는 서로 다른 Cloud Run 서비스라(설계서 1.3)
// 주소를 각각 받는다. 두 주소는 런타임에 window.__APP_CONFIG__로 주입된다(빌드에 굽지 않는다).

const cfg = () => window.__APP_CONFIG__ || {};

export const visionBase = () => (cfg().VISION_BASE_URL || "").replace(/\/$/, "");
export const matchingBase = () => (cfg().MATCHING_BASE_URL || "").replace(/\/$/, "");

/**
 * 5.3: 업로드 전에 photo_id와 Signed URL을 발급받는다. photo_id가 idempotency key다(2.1).
 * destination을 넘기지 않으면 서버가 기본 목적지로 설정한다.
 */
export async function requestUploadUrl({ truckId, intrinsics, gps, destination }) {
  const res = await fetch(`${visionBase()}/v1/photos/upload-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      truck_id: truckId,
      content_type: "image/jpeg",
      native_intrinsics: intrinsics,
      gps_lat: gps ? gps.lat : null,
      gps_lng: gps ? gps.lng : null,
      destination_address: destination ? destination.address : null,
      destination_lat: destination ? destination.lat : null,
      destination_lng: destination ? destination.lng : null,
    }),
  });
  if (!res.ok) {
    // CORS나 네트워크 문제면 여기까지 오지 못하고 fetch가 던진다.
    throw new Error(`업로드 주소 발급 실패 (${res.status})`);
  }
  return res.json();
}

/** Signed URL로 GCS에 직접 올린다. 백엔드를 거치지 않는다(2.2 통신 방식). */
export async function uploadToSignedUrl(uploadUrl, blob) {
  const res = await fetch(uploadUrl, {
    method: "PUT",
    headers: { "Content-Type": "image/jpeg" },
    body: blob,
  });
  if (!res.ok) throw new Error(`업로드 실패 (${res.status})`);
}

/**
 * 결과가 나올 때까지 폴링한다. 아직 처리 중이면 404가 온다.
 * @returns 결과 객체, 시간 내에 안 나오면 null
 */
async function poll(url, { intervalMs, deadline, signal }) {
  while (Date.now() < deadline) {
    if (signal?.aborted) throw new DOMException("취소됨", "AbortError");
    const res = await fetch(url, { cache: "no-store", signal });
    if (res.ok) return res.json();
    if (res.status !== 404) throw new Error(`${res.status} ${await res.text()}`);
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return null;
}

/**
 * 사진 없이 차량 제원만으로 추가 상차분을 계산한다.
 *
 * 적재된 박스를 0으로 보므로 실을 수 있는 공간이 곧 등록 적재함 체적이다. 촬영·업로드·
 * depth 추정이 필요 없어 폴링도 없고, 서버가 계산을 마친 결과를 그대로 돌려준다.
 */
export async function matchByTruck(truckId, candidateLimit, palletized) {
  const id = (truckId || "").trim();
  if (!id) throw new Error("차량을 선택하세요.");
  if (!matchingBase()) throw new Error("matching-processor 주소가 설정되지 않았습니다.");
  // 후보 수를 넘기지 않으면 서버 기본값을 쓴다. 기본값을 프론트에 복제하지 않는다.
  const params = new URLSearchParams();
  if (candidateLimit) params.set("candidates", String(candidateLimit));
  if (palletized) params.set("palletized", "true");
  const q = params.toString() ? `?${params}` : "";
  const res = await fetch(
    `${matchingBase()}/v1/trucks/${encodeURIComponent(id)}/match${q}`,
    { method: "POST", headers: { "Content-Type": "application/json" } }
  );
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(
      res.status === 404
        ? `차량 ${id}이(가) 등록되어 있지 않습니다.`
        : `매칭에 실패했습니다 (${res.status}) ${detail.slice(0, 200)}`
    );
  }
  return res.json();
}

export function pollVisionResult(photoId, opts) {
  return poll(`${visionBase()}/v1/results/${photoId}`, opts);
}

export function pollMatchingResult(photoId, opts) {
  if (!matchingBase()) return Promise.resolve(null);
  return poll(`${matchingBase()}/v1/results/${photoId}`, opts);
}

/**
 * 1.2: 위치는 촬영 시점에만 확보한다. 실패해도 업로드는 진행한다.
 * 실패 사유를 함께 돌려줘 화면에 표시한다 — 조용히 null이 되면 왜 위치가 없는지 알 수 없다.
 * @returns {Promise<{position: {lat,lng}|null, reason: string|null}>}
 */
export function getPosition() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) {
      return resolve({ position: null, reason: "이 브라우저는 위치를 지원하지 않습니다." });
    }
    // HTTPS(또는 localhost)가 아니면 브라우저가 권한 팝업조차 띄우지 않는다.
    if (!window.isSecureContext) {
      return resolve({ position: null, reason: "보안 연결(HTTPS)이 아니라 위치를 쓸 수 없습니다." });
    }
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ position: { lat: p.coords.latitude, lng: p.coords.longitude }, reason: null }),
      (err) => {
        const reason = {
          1: "위치 권한이 거부됐습니다. 브라우저 설정에서 허용해 주세요.",
          2: "위치를 확인할 수 없습니다.",
          3: "위치 확인이 시간 내에 끝나지 않았습니다.",
        }[err.code] || "위치를 가져오지 못했습니다.";
        resolve({ position: null, reason });
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 }
    );
  });
}
