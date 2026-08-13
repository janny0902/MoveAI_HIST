from typing import Optional

from google.cloud import firestore

import config
from schemas import TruckSpec

_db: Optional[firestore.Client] = None


def _client() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(project=config.PROJECT_ID)
    return _db


def get_truck_spec(truck_id: str) -> Optional[TruckSpec]:
    """4.2: W/L/H, 최대 적재중량, 현재 적재중량. W/L/H 없으면 호출자가 분석을 중단해야 한다."""
    doc = _client().collection("trucks").document(truck_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    required = ("cargo_width_m", "cargo_length_m", "cargo_height_m", "max_payload_kg")
    if any(data.get(field) is None for field in required):
        return None
    return TruckSpec(
        truck_id=truck_id,
        cargo_width_m=data["cargo_width_m"],
        cargo_length_m=data["cargo_length_m"],
        cargo_height_m=data["cargo_height_m"],
        max_payload_kg=data["max_payload_kg"],
        current_loaded_weight_kg=data.get("current_loaded_weight_kg"),
    )


def get_truck_profile(truck_id: str) -> Optional[dict]:
    """촬영 화면에 보여줄 차량 제원. get_truck_spec과 달리 필드가 빠져도 돌려준다.

    분석은 등록된 적재함 치수에 맞춰 스케일을 정규화한다(geometry_lite/truck_frame.py).
    사진 속 차량이 이 제원과 다르면 결과가 통째로 어긋나는데, 화면에 제원이 없으면
    기사는 그 사실을 알 수 없다. 그래서 '없는 값'도 없는 채로 내려보내 화면이
    "제원 미등록"이라고 말할 수 있게 한다 — 조용히 빈칸으로 두지 않는다.
    """
    doc = _client().collection("trucks").document(truck_id).get()
    if not doc.exists:
        return None
    d = doc.to_dict() or {}

    def num(key):
        v = d.get(key)
        return float(v) if isinstance(v, (int, float)) else None

    w, l, h = num("cargo_width_m"), num("cargo_length_m"), num("cargo_height_m")
    max_kg, cur_kg = num("max_payload_kg"), num("current_loaded_weight_kg")
    return {
        "truck_id": truck_id,
        "manufacturer": d.get("manufacturer"),
        "model": d.get("model"),
        "body_type": d.get("body_type"),
        "vehicle_class": d.get("vehicle_class"),
        "cargo_width_m": w,
        "cargo_length_m": l,
        "cargo_height_m": h,
        # 문서의 cargo_capacity_cbm을 믿지 않고 치수에서 다시 계산한다. 분석이 쓰는 건
        # 치수 쪽이라, 둘이 어긋나면 화면이 분석과 다른 숫자를 말하게 된다.
        "capacity_cbm": round(w * l * h, 3) if None not in (w, l, h) else None,
        "max_payload_kg": max_kg,
        # 제원의 출처. 화면이 "이 숫자를 어디서 가져왔나"를 말할 수 있어야 한다 —
        # 합성 제원을 등록 원장처럼 보이게 두면 그걸 근거로 실제 배차를 하게 된다.
        "spec_template_id": d.get("spec_template_id"),
        "record_type": d.get("record_type"),
        "registered_year": d.get("registered_year"),
        "current_loaded_weight_kg": cur_kg,
        "available_payload_kg": (
            round(max_kg - cur_kg, 1) if None not in (max_kg, cur_kg) else None
        ),
    }


def list_truck_profiles(limit: int = 200) -> list:
    """등록된 차량 목록. 촬영 화면의 차량 선택에 쓴다.

    번호를 직접 타이핑하게 두면 등록되지 않은 번호를 넣고 왜 안 되는지 모른 채 막힌다.
    게다가 이 화면에서 골라야 하는 건 "내 차"가 아니라 **지금 찍은 차와 제원이 맞는 차**라
    (제원이 곧 측정의 자다), 목록에 적재함 크기와 중량이 함께 보여야 고를 수 있다.
    """
    docs = _client().collection("trucks").order_by("truck_id").limit(limit).stream()
    out = []
    for doc in docs:
        d = doc.to_dict() or {}

        def num(key):
            v = d.get(key)
            return float(v) if isinstance(v, (int, float)) else None

        w, l, h = num("cargo_width_m"), num("cargo_length_m"), num("cargo_height_m")
        # 치수가 없는 차량은 어차피 분석이 중단된다. 목록에 올리지 않는다.
        if None in (w, l, h):
            continue
        out.append({
            "truck_id": doc.id,
            "model": d.get("model"),
            "body_type": d.get("body_type"),
            "capacity_cbm": round(w * l * h, 3),
            "max_payload_kg": num("max_payload_kg"),
            "current_loaded_weight_kg": num("current_loaded_weight_kg"),
        })
    return out


TRUCK_SESSIONS_COLLECTION = "truck_sessions"


def save_truck_session(truck_id: str, payload: dict) -> None:
    """차량별 **가장 최근** 분석. 문서 ID가 truck_id라 항상 덮어써진다.

    vision_results를 truck_id로 조회하면 복합색인이 필요하고, 색인이 없으면 조용히
    실패한다. 차량당 최신 한 건만 알면 되므로 단일 문서로 둔다 - 색인 없이 한 번 읽기다.

    이게 필요한 이유: 재매칭 루프가 브라우저 안에만 있어서 새로고침하면 사라진다.
    한 시간 안에 찍은 이력이 있으면 화면이 그 운행을 이어받을 수 있어야 한다.
    """
    _client().collection(TRUCK_SESSIONS_COLLECTION).document(truck_id).set(payload)


def get_truck_session(truck_id: str) -> Optional[dict]:
    doc = _client().collection(TRUCK_SESSIONS_COLLECTION).document(truck_id).get()
    return doc.to_dict() if doc.exists else None


def save_vision_result(photo_id: str, payload: dict) -> None:
    _client().collection("vision_results").document(photo_id).set(payload)


def get_vision_result(photo_id: str) -> Optional[dict]:
    doc = _client().collection("vision_results").document(photo_id).get()
    return doc.to_dict() if doc.exists else None


PHOTO_CONTEXTS_COLLECTION = "photo_contexts"


def save_photo_context(photo_id: str, context: dict) -> None:
    """D1: PWA가 upload-url을 받을 때 함께 넘긴 truck_id/intrinsics를 보관한다.

    PWA는 EXIF를 읽은 뒤 1024px로 리사이즈해 업로드하는데, canvas 재인코딩 과정에서 EXIF가
    사라진다(2.1). 그래서 촬영 시점에 확보한 intrinsic을 이미지가 아니라 이 문서로 전달한다.
    """
    _client().collection(PHOTO_CONTEXTS_COLLECTION).document(photo_id).set(context)


def get_photo_context(photo_id: str) -> Optional[dict]:
    doc = _client().collection(PHOTO_CONTEXTS_COLLECTION).document(photo_id).get()
    return doc.to_dict() if doc.exists else None


def update_truck_location(
    truck_id: str,
    current_lat: Optional[float] = None,
    current_lng: Optional[float] = None,
    destination_lat: Optional[float] = None,
    destination_lng: Optional[float] = None,
    destination_address: Optional[str] = None,
) -> None:
    """D1: 촬영 시점의 트럭 위치와 목적지를 갱신한다. M2 경로 회랑이 두 값을 모두 쓴다.

    merge=True로 트럭 제원 필드를 지우지 않는다. 위치를 못 받았으면(권한 거부 등)
    그 필드는 건드리지 않아 직전 값이 남는다 — 없는 값으로 덮어써서 지우면 안 된다.
    """
    payload = {}
    if current_lat is not None and current_lng is not None:
        payload["current_lat"] = current_lat
        payload["current_lng"] = current_lng
    if destination_lat is not None and destination_lng is not None:
        payload["destination_lat"] = destination_lat
        payload["destination_lng"] = destination_lng
        payload["destination_address"] = destination_address or ""
    if not payload:
        return
    _client().collection("trucks").document(truck_id).set(payload, merge=True)


PROCESSED_PHOTOS_COLLECTION = "processed_photos"


def claim_photo(photo_id: str) -> bool:
    """2.1/5.8/5.9: photo_id를 idempotency key로 쓴다. 처음 잡았으면 True.

    create()는 문서가 이미 있으면 AlreadyExists를 던진다. 이 원자성 덕분에 Eventarc가
    같은 객체를 재전송하거나 두 인스턴스에 동시에 배달해도 파이프라인이 한 번만 돈다.
    GPU/CPU 추론을 두 번 돌리지 않는 것이 목적이므로 파이프라인 진입 전에 잡는다.
    """
    from google.api_core.exceptions import AlreadyExists

    try:
        _client().collection(PROCESSED_PHOTOS_COLLECTION).document(photo_id).create(
            {"claimed_at": firestore.SERVER_TIMESTAMP}
        )
        return True
    except AlreadyExists:
        return False


def release_photo(photo_id: str) -> None:
    """처리에 실패했으면 점유를 풀어 Eventarc 재시도가 다시 처리할 수 있게 한다.
    풀지 않으면 첫 시도가 실패한 사진은 영원히 재처리되지 않는다."""
    _client().collection(PROCESSED_PHOTOS_COLLECTION).document(photo_id).delete()