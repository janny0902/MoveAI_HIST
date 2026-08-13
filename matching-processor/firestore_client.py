import json
import logging
from typing import List, Optional

from google.cloud import firestore

import config
from schemas import Cargo, MatchingResult, TruckState

logger = logging.getLogger("matching-processor")

_db: Optional[firestore.Client] = None


def _client() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(project=config.PROJECT_ID)
    return _db


def get_truck_state(truck_id: str) -> Optional[TruckState]:
    doc = _client().collection(config.TRUCKS_COLLECTION).document(truck_id).get()
    if not doc.exists:
        return None
    d = doc.to_dict()
    if d.get("max_payload_kg") is None:
        return None
    return TruckState(
        truck_id=truck_id,
        max_payload_kg=d["max_payload_kg"],
        cargo_capacity_cbm=d.get("cargo_capacity_cbm"),
        cargo_width_m=d.get("cargo_width_m"),
        cargo_length_m=d.get("cargo_length_m"),
        cargo_height_m=d.get("cargo_height_m"),
        current_loaded_weight_kg=d.get("current_loaded_weight_kg"),
        reserved_added_weight_kg=d.get("reserved_added_weight_kg") or 0.0,
        current_lat=d.get("current_lat"),
        current_lng=d.get("current_lng"),
        destination_lat=d.get("destination_lat"),
        destination_lng=d.get("destination_lng"),
    )


def _to_cargo(doc) -> Optional[Cargo]:
    d = doc.to_dict()
    if d.get("volume_cbm") is None or d.get("weight_kg") is None:
        # 4.2 표: 후보 화물 CBM/중량이 없으면 해당 후보만 제외한다.
        return None
    return Cargo(
        cargo_id=d.get("cargo_id") or doc.id,
        volume_cbm=d["volume_cbm"],
        weight_kg=d["weight_kg"],
        pickup_lat=d["pickup_lat"],
        pickup_lng=d["pickup_lng"],
        delivery_lat=d.get("delivery_lat"),
        delivery_lng=d.get("delivery_lng"),
        revenue_krw=d.get("revenue_krw") or 0.0,
        freight_krw=d.get("freight_krw") or 0.0,
        weight_source=d.get("weight_source") or "DECLARED",
        box_types=d.get("box_types") or [],
        box_count=d.get("box_count") or 1,
        # 결과 화면이 "어디서 받는지"를 말할 수 있어야 한다.
        pickup_address=d.get("pickup_address"),
        # 구 문서는 terminal_code/terminal_name에 출발지가 들어 있다. 마이그레이션 전
        # 문서가 섞여 있어도 상차지를 잃지 않도록 옛 이름을 대체 경로로 읽는다.
        origin_terminal_code=d.get("origin_terminal_code") or d.get("terminal_code"),
        origin_terminal_name=d.get("origin_terminal_name") or d.get("terminal_name"),
        destination_terminal_code=d.get("destination_terminal_code"),
        destination_terminal_name=d.get("destination_terminal_name"),
        ready_at=d.get("ready_at"),
        deadline_at=d.get("deadline_at"),
    )


def query_corridor_cargos(lat_min: float, lat_max: float, lng_min: float, lng_max: float) -> List[Cargo]:
    """M2: 경로 회랑 박스 안의 WAITING 화물을 조회한다.

    pickup_lat/pickup_lng 두 필드에 부등호를 걸므로 Firestore 복합색인이 필요하다
    (infra/bootstrap.sh가 생성). 색인이 없으면 FAILED_PRECONDITION이 나고, 호출자가
    이를 잡아 신규 추천을 중단한다 — 조용히 전수 조회로 넘어가지 않는다.

    위도 밴드로 쪼개서 조회하는 이유:
      복합색인이 pickup_lat 오름차순이라 박스 전체에 limit을 걸면 **가장 남쪽 N건**만
      돌아온다. 후보가 조밀한 지역에서는 그 N건이 전부 박스 남단(중심에서 정남쪽 최대거리)에
      몰려, 이어지는 haversine 반경 필터에서 전멸한다. 실제로 회랑 500건이 필터 후 0건이 됐다.
      밴드마다 따로 limit을 걸면 남북으로 고르게 뽑혀 이 쏠림이 사라진다.
    """
    bands = max(1, config.CORRIDOR_LAT_BANDS)
    per_band = max(1, config.MAX_CANDIDATE_FETCH // bands)
    step = (lat_max - lat_min) / bands

    collection = _client().collection(config.CARGOS_COLLECTION)
    cargos: List[Cargo] = []
    seen = set()

    for i in range(bands):
        band_min = lat_min + step * i
        band_max = lat_min + step * (i + 1) if i < bands - 1 else lat_max
        q = (
            collection
            .where(filter=firestore.FieldFilter("status", "==", "WAITING"))
            .where(filter=firestore.FieldFilter("pickup_lat", ">=", band_min))
            .where(filter=firestore.FieldFilter("pickup_lat", "<=", band_max))
            .where(filter=firestore.FieldFilter("pickup_lng", ">=", lng_min))
            .where(filter=firestore.FieldFilter("pickup_lng", "<=", lng_max))
            .limit(per_band)
        )
        for doc in q.stream():
            if doc.id in seen:
                continue
            seen.add(doc.id)
            cargo = _to_cargo(doc)
            if cargo is not None:
                cargos.append(cargo)

    return cargos


def query_waiting_cargos(limit: int = 1000) -> List[Cargo]:
    """대기 중인 화물 전체. 위치로 거르지 않는다.

    회랑(query_corridor_cargos)은 "지금 트럭 근처"를 묻는 질문이고, 이쪽은 "이 차에
    실리는가"만 묻는다. 후자에는 트럭 위치가 필요 없다 — 실을 수 있는지는 체적과
    중량이 정하고, 어디서 받을지는 결과를 터미널로 묶어 보여주는 것으로 답한다.

    pickup_lat/lng에 부등호를 걸지 않으므로 복합색인이 필요 없다.
    """
    q = (
        _client()
        .collection(config.CARGOS_COLLECTION)
        .where(filter=firestore.FieldFilter("status", "==", "WAITING"))
        .limit(limit)
    )
    cargos: List[Cargo] = []
    for doc in q.stream():
        cargo = _to_cargo(doc)
        if cargo is not None:
            cargos.append(cargo)
    return cargos


def count_pending_cargos() -> int:
    """대기 운송장 총 건수. 목록이 20만 건 규모라 "몇 건 중 몇 번째"가 없으면
    페이지를 넘길 근거가 없다. 집계 쿼리는 문서를 읽지 않아 비용이 건수에 비례하지 않는다."""
    from google.cloud.firestore_v1 import aggregation

    q = (
        _client()
        .collection(config.CARGOS_COLLECTION)
        .where(filter=firestore.FieldFilter("status", "==", "WAITING"))
    )
    result = aggregation.AggregationQuery(q).count(alias="n").get()
    return int(result[0][0].value)


def list_pending_cargos(
    limit: int = 100,
    terminal_code: Optional[str] = None,
    destination_terminal_code: Optional[str] = None,
    offset: int = 0,
) -> List[dict]:
    """대기 중인 운송장 목록. 조회 화면이 쓴다.

    복합색인을 피하려고 **한쪽만** 쿼리로 걸고 나머지는 파이썬에서 거른다. status와
    terminal_code에 동시에 등호를 걸면 복합색인이 필요하고, 색인이 없으면
    FAILED_PRECONDITION이 난다. 조회 화면 하나 때문에 색인을 늘릴 이유는 없다.

    터미널을 지정하면 그 터미널로 쿼리하고 상태를 파이썬에서 거른다(그 터미널의 문서가
    많아야 수만 건이라 limit 안에서 끝난다). 지정하지 않으면 상태로만 쿼리한다.
    """
    collection = _client().collection(config.CARGOS_COLLECTION)
    if terminal_code:
        q = collection.where(
            filter=firestore.FieldFilter("origin_terminal_code", "==", terminal_code)
        )
    else:
        q = collection.where(filter=firestore.FieldFilter("status", "==", "WAITING"))

    # 도착지 필터는 파이썬에서 건다. 출발지와 함께 등호를 걸면 복합색인이 또 하나
    # 필요해지는데, 조회 화면 하나 때문에 색인을 늘릴 이유가 없다. 대신 거르기 전에
    # 더 많이 가져온다.
    overfetch = limit * 3 if (terminal_code or destination_terminal_code) else limit

    # 페이지 넘김. offset은 건너뛴 문서도 읽기로 세지만, 커서를 쓰려면 정렬 기준을
    # 고정해야 하고 그러면 복합색인이 또 필요하다. 조회 화면 하나에는 이쪽이 싸다.
    if offset:
        q = q.offset(offset)

    out: List[dict] = []
    for doc in q.limit(overfetch).stream():
        d = doc.to_dict() or {}
        if d.get("status") != "WAITING":
            continue
        if destination_terminal_code and d.get("destination_terminal_code") != destination_terminal_code:
            continue
        out.append({
            "cargo_id": d.get("cargo_id") or doc.id,
            "volume_cbm": d.get("volume_cbm"),
            "weight_kg": d.get("weight_kg"),
            "weight_source": d.get("weight_source") or "DECLARED",
            "weight_basis": d.get("weight_basis"),
            "box_types": d.get("box_types") or [],
            "freight_krw": d.get("freight_krw") or d.get("revenue_krw") or 0,
            "commission_krw": d.get("commission_krw") or 0,
            # 구 문서 호환: 옛 terminal_code는 출발지를 뜻했다.
            "origin_terminal_code": d.get("origin_terminal_code") or d.get("terminal_code"),
            "origin_terminal_name": d.get("origin_terminal_name") or d.get("terminal_name"),
            "destination_terminal_code": d.get("destination_terminal_code"),
            "destination_terminal_name": d.get("destination_terminal_name"),
            "pickup_address": d.get("pickup_address"),
            "pickup_lat": d.get("pickup_lat"),
            "pickup_lng": d.get("pickup_lng"),
            "box_count": d.get("box_count"),
            "product_code": d.get("product_code"),
            "ready_at": d.get("ready_at"),
            "deadline_at": d.get("deadline_at"),
        })
        if len(out) >= limit:
            break
    return out


# Firestore 문서 상한은 1,048,576바이트. 여유를 두고 이 아래로 맞춘다.
_DOC_SIZE_BUDGET = 900_000


def save_matching_result(photo_id: str, result: MatchingResult) -> None:
    """결과를 저장한다. 문서가 1MB를 넘으면 낱건 목록을 잘라 낸다.

    후보를 10만 건까지 볼 수 있게 되면서 selected_cargos가 수천 건이 됐고, 그대로 저장하니
    "size (1,080,817 bytes) exceeds the maximum allowed size of 1,048,576 bytes"로 500이 났다.
    계산은 다 끝났는데 저장에서 죽어 화면에는 아무것도 안 나왔다.

    자를 때 terminal_groups는 남긴다. 이 결과를 다시 조회하는 쪽이 보는 것은 묶음이고,
    낱건 목록은 화면에서 쓰지 않는다. 잘랐다는 사실은 selected_cargos_truncated로 남겨,
    나중에 "왜 건수가 안 맞지"를 추측하지 않게 한다.
    """
    payload = result.model_dump(mode="json")
    encoded = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    if encoded > _DOC_SIZE_BUDGET:
        kept = len(payload.get("selected_cargos") or [])
        payload["selected_cargos"] = []
        payload["selected_cargos_truncated"] = kept
        logger.info(
            "결과 문서가 %d바이트라 selected_cargos %d건을 저장에서 제외한다 (photo_id=%s)",
            encoded, kept, photo_id,
        )

    _client().collection(config.RESULTS_COLLECTION).document(photo_id).set(payload)


def get_matching_result(photo_id: str) -> Optional[dict]:
    doc = _client().collection(config.RESULTS_COLLECTION).document(photo_id).get()
    return doc.to_dict() if doc.exists else None


def claim_event(event_id: str) -> bool:
    """5.8: Pub/Sub 중복 수신 방지. 이 event_id를 처음 잡았으면 True.

    create()는 문서가 이미 있으면 AlreadyExists를 던진다. 이 원자성 덕분에
    같은 이벤트가 동시에 두 인스턴스로 배달돼도 한 번만 처리된다.
    """
    from google.api_core.exceptions import AlreadyExists

    try:
        _client().collection(config.PROCESSED_EVENTS_COLLECTION).document(event_id).create(
            {"claimed_at": firestore.SERVER_TIMESTAMP}
        )
        return True
    except AlreadyExists:
        return False


def client() -> firestore.Client:
    """cargo_ingest가 일괄 쓰기(batch)를 만들 때 쓰는 공개 핸들."""
    return _client()
