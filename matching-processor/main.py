import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from google.api_core.exceptions import FailedPrecondition

import config
import firestore_client
import cargo_ingest
import routes_client
import storage_reader
import solver
import terminals
from geo import bounding_box, haversine_km
from schemas import (
    CargoBatch,
    CargoRegistration,
    Cargo,
    MatchingResult,
    QualityStatus,
    SelectedCargo,
    SpaceGeometryReadyEvent,
    TerminalGroup,
    TerminalRegistration,
    TruckState,
    WaybillBatch,
)

app = FastAPI(title="Matching Processor")

# 프론트엔드가 별도 서비스라(1.3) 결과 조회가 브라우저에는 교차 출처가 된다.
#
# 구분자로 세미콜론을 쓴다. gcloud --set-env-vars가 쉼표로 항목을 나누고, Windows에서는
# 공백이 들어간 인자가 cmd.exe에서 깨지기 때문이다. 편의상 쉼표도 함께 받는다.
def _parse_origins(raw: str):
    return [o.strip() for o in raw.replace(",", ";").split(";") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_origins(os.getenv("CORS_ALLOW_ORIGINS", "*")),
    # 결과 조회는 GET, 화주사 운송장 등록은 POST로 들어온다.
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("matching-processor")
logger.setLevel(logging.INFO)


@app.get("/")
def health_check():
    return {"status": "ok", "service": "matching-processor"}


def _fail(
    event: SpaceGeometryReadyEvent,
    reason: str,
    solver_status: str = "NOT_RUN",
    remaining_weight_kg: Optional[float] = None,
    candidate_count: int = 0,
    route_source: str = "NONE",
) -> MatchingResult:
    """5.8 Fail-closed: 어떤 사유든 can_load=false로 끝내되 근거를 남긴다.
    5.9 비기능: 오류 시 잘못된 true를 반환하지 않는다."""
    logger.warning("can_load=false (%s) photo_id=%s", reason, event.photo_id)
    return MatchingResult(
        truck_id=event.truck_id,
        photo_id=event.photo_id,
        estimated_free_cbm=event.estimated_free_cbm,
        usable_free_cbm=event.usable_free_cbm,
        unknown_cbm=event.unknown_cbm,
        remaining_weight_kg=remaining_weight_kg,
        can_load=False,
        selected_cargos=[],
        final_free_cbm=event.usable_free_cbm,
        quality_score=event.quality_score,
        quality_status=event.quality_status,
        solver_status=solver_status,
        candidate_count=candidate_count,
        route_source=route_source,
        failure_reason=reason,
    )


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Firestore가 돌려주는 timestamp는 tz-aware지만, 시드 데이터에 naive가 섞이면
    now(utc)와 비교할 때 TypeError가 난다. naive는 UTC로 간주한다."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _prefilter(cargos: List[Cargo], truck: TruckState, radius_km: float, now: datetime) -> List[Cargo]:
    """M3: 직선거리/시간창 1차 필터 후 Top N만 남긴다(설계서 5.4: Routes API는 Top 10-20만 호출).

    박스 쿼리는 반경의 상위집합이므로 여기서 haversine으로 실제 반경을 적용한다.
    """
    scored: List[Tuple[float, Cargo]] = []
    for c in cargos:
        km = haversine_km(truck.current_lat, truck.current_lng, c.pickup_lat, c.pickup_lng)
        if km > radius_km:
            continue
        deadline = _as_utc(c.deadline_at)
        if deadline is not None and deadline <= now:
            # pickup time window를 이미 넘긴 후보는 제외한다.
            continue
        scored.append((km, c))

    scored.sort(key=lambda t: t[0])

    # 상차지 **지점 수**로 제한한다. 후보 수로 자르면 안 된다.
    #
    # 길찾기 호출은 후보가 아니라 지점에 비례한다(2N+1). 터미널 하나에 운송장 수백 건이
    # 몰리는 구조라, 후보 20건 제한은 "같은 터미널 20건"만 보게 만들어 손익분기(수수료가
    # 상차지 고정비를 넘는 건수)를 못 넘겼다.
    #
    # 반대로 후보 수만 200으로 늘렸더니 좌표가 제각각인 후보가 섞여 지점이 89곳이 됐고,
    # 길찾기 179회에서 카카오 rate limit에 걸려 매칭이 통째로 실패했다(routes_api_failed).
    # 그래서 가까운 지점 N곳만 고르고, 그 지점들의 화물은 전부 후보로 넣는다.
    picked: List[Cargo] = []
    stops: dict = {}
    for _, c in scored:
        key = (round(c.pickup_lat, 5), round(c.pickup_lng, 5))
        if key not in stops:
            if len(stops) >= config.MAX_ROUTE_STOPS:
                continue
            stops[key] = True
        picked.append(c)
        if len(picked) >= config.MAX_ROUTE_CANDIDATES:
            break
    return picked


def _run_matching(event: SpaceGeometryReadyEvent) -> MatchingResult:
    """M1-M6. 1.3: 이미지/depth map/point cloud는 읽지 않고 이벤트 필드만 사용한다."""
    now = datetime.now(timezone.utc)

    # 4.10 / 5.2: 품질 게이트를 먼저 통과해야 한다.
    if event.quality_status == QualityStatus.REJECTED:
        return _fail(event, "quality_rejected")

    truck = firestore_client.get_truck_state(event.truck_id)
    if truck is None:
        return _fail(event, "truck_spec_not_found")

    # 4.2 표 / 5.2: 현재 적재중량이 없으면 잔여중량을 계산할 수 없다.
    if truck.current_loaded_weight_kg is None:
        return _fail(event, "current_loaded_weight_unknown")

    remaining_weight_kg = max(
        0.0,
        truck.max_payload_kg - truck.current_loaded_weight_kg - truck.reserved_added_weight_kg,
    )

    if None in (truck.current_lat, truck.current_lng, truck.destination_lat, truck.destination_lng):
        # M2 경로 회랑을 만들 수 없다. 위치를 지어내지 않고 중단한다.
        return _fail(event, "truck_position_or_destination_unknown", remaining_weight_kg=remaining_weight_kg)

    # 4.10: LIMITED는 추가 안전계수를 적용한 제한 Matching.
    usable_free_cbm = event.usable_free_cbm
    geometry_risk_penalty = 0
    if event.quality_status == QualityStatus.LIMITED:
        usable_free_cbm *= config.LIMITED_EXTRA_SAFETY_FACTOR
        geometry_risk_penalty = config.GEOMETRY_RISK_PENALTY_LIMITED

    # M2: 경로 회랑 박스 안의 WAITING 화물
    lat_min, lat_max, lng_min, lng_max = bounding_box(
        truck.current_lat, truck.current_lng, config.CORRIDOR_RADIUS_KM
    )
    try:
        corridor = firestore_client.query_corridor_cargos(lat_min, lat_max, lng_min, lng_max)
    except FailedPrecondition as exc:
        # 복합색인 없음. 10만 건 전수 조회로 넘어가지 않고 중단한다.
        logger.error("Firestore 복합색인 누락으로 후보 조회 실패: %s", exc)
        return _fail(event, "cargo_index_missing", remaining_weight_kg=remaining_weight_kg)

    # M3: 1차 필터 + Top N
    candidates = _prefilter(corridor, truck, config.CORRIDOR_RADIUS_KM, now)
    logger.info(
        "후보 축소: 회랑 %d건 -> 필터 후 %d건 (photo_id=%s)", len(corridor), len(candidates), event.photo_id
    )
    if not candidates:
        return _fail(
            event, "no_candidate_cargo", solver_status="NOT_RUN", remaining_weight_kg=remaining_weight_kg
        )

    # M4: 우회시간
    try:
        candidates, route_source = routes_client.compute_detours(truck, candidates)
    except routes_client.RoutesApiError as exc:
        # 5.8: Routes API 실패 시 유효한 cache가 없으면 신규 추천을 중단한다.
        logger.error("Routes API 실패: %s", exc)
        return _fail(
            event, "routes_api_failed", remaining_weight_kg=remaining_weight_kg,
            candidate_count=len(candidates),
        )

    # M5: CP-SAT
    result = solver.solve(
        cargos=candidates,
        usable_free_cbm=usable_free_cbm,
        remaining_weight_kg=remaining_weight_kg,
        start_lat=truck.current_lat,
        start_lng=truck.current_lng,
        geometry_risk_penalty=geometry_risk_penalty,
    )

    # 5.2 Boolean 출력
    can_load = (
        event.quality_status in (QualityStatus.ACCEPTED, QualityStatus.LIMITED)
        and truck.current_loaded_weight_kg is not None
        and result.status in ("OPTIMAL", "FEASIBLE")
        and len(result.selected) > 0
    )
    final_free_cbm = max(0.0, usable_free_cbm - result.selected_volume_cbm)

    return MatchingResult(
        truck_id=event.truck_id,
        photo_id=event.photo_id,
        estimated_free_cbm=event.estimated_free_cbm,
        usable_free_cbm=round(usable_free_cbm, 3),
        unknown_cbm=event.unknown_cbm,
        remaining_weight_kg=round(remaining_weight_kg, 1),
        can_load=can_load,
        selected_cargos=result.selected,
        terminal_groups=_group_by_terminal(result.selected) if can_load else [],
        # 상차 계획과 수익. 실을 수 있다는 사실만으로는 갈지 말지 정할 수 없다.
        pickup_stops=result.pickup_stops if can_load else [],
        added_revenue_krw=result.added_revenue_krw if can_load else 0.0,
        added_detour_seconds=result.added_detour_seconds if can_load else 0,
        # added_revenue_krw가 곧 기사 수수료다(솔버가 그걸로 최적화했다). 여기서
        # 비율을 한 번 더 곱하면 이중 계산이 된다.
        added_commission_krw=result.added_revenue_krw if can_load else 0.0,
        added_freight_krw=(
            sum(s.freight_krw or 0 for s in result.pickup_stops) if can_load else 0.0
        ),
        fill_reward_krw=result.fill_reward_krw if can_load else 0.0,
        detour_cost_krw=result.detour_cost_krw if can_load else 0.0,
        risk_cost_krw=result.risk_cost_krw if can_load else 0.0,
        net_gain_krw=result.net_gain_krw if can_load else 0.0,
        breakeven_cargo_count=result.breakeven_cargo_count if can_load else None,
        final_free_cbm=round(final_free_cbm, 3),
        quality_score=event.quality_score,
        quality_status=event.quality_status,
        solver_status=result.status,
        candidate_count=len(candidates),
        route_source=route_source,
        failure_reason=None if can_load else "no_feasible_combination",
    )


def _palletized_capacity(truck: TruckState) -> Optional[dict]:
    """파렛트에 실을 때 실제로 쓸 수 있는 체적.

    현장에서 자주 나는 계산 착오가 화물만 재고 파렛트를 빼먹는 것이다. 파렛트에 실으면
    잃는 공간이 셋이다.

      1) 깔판 높이 — 파렛트 두께(144mm)만큼 쌓을 수 있는 높이가 줄어든다.
      2) 바닥 자투리 — 1.1m 규격이 적재함 폭·길이로 나누어떨어지지 않는다. 11톤 윙바디
         폭 2.35m에는 파렛트가 2장(2.2m)만 들어가고 남는 15cm는 통째로 죽는다.
      3) 파렛트 위 빈틈 — 규격이 제각각인 소포는 파렛트를 꽉 채우지 못한다.

    이 셋을 넣지 않으면 실제보다 CBM이 크게 잡혀, 다 실린다고 계산해 놓고 현장에서 남는다.

    치수를 모르면 None을 돌려준다. 파렛트가 몇 장 깔리는지는 부피가 아니라 바닥 크기가
    정하므로, 치수 없이 추정하면 그냥 지어내는 것이 된다.
    """
    w, l, h = truck.cargo_width_m, truck.cargo_length_m, truck.cargo_height_m
    if not (w and l and h):
        return None

    across = int(w // config.PALLET_WIDTH_M)
    along = int(l // config.PALLET_LENGTH_M)
    count = across * along
    stack_h = max(0.0, h - config.PALLET_BASE_HEIGHT_M)
    usable = (
        count
        * config.PALLET_WIDTH_M
        * config.PALLET_LENGTH_M
        * stack_h
        * config.PALLET_STACK_EFFICIENCY
    )
    return {
        "count": count,
        "layout": f"{across}열 x {along}줄",
        "usable_cbm": round(usable, 3),
        "stack_height_m": round(stack_h, 3),
        "spec": (
            f"{config.PALLET_WIDTH_M*1000:.0f}x{config.PALLET_LENGTH_M*1000:.0f}mm "
            f"(깔판 {config.PALLET_BASE_HEIGHT_M*1000:.0f}mm) "
            f"{count}장 {across}열x{along}줄 · 적재효율 "
            f"{config.PALLET_STACK_EFFICIENCY*100:.0f}%"
        ),
    }


def _fill_by_capacity(
    cargos: List[Cargo], free_cbm: float, remaining_weight_kg: float
) -> Tuple[List[SelectedCargo], float, float]:
    """부피·중량 제약만으로 실을 운송장을 고른다. (선택, 체적합, 중량합)

    CP-SAT를 쓰지 않는 이유: 이 경로에는 우회시간도 상차지 고정비도 없어서, 남은 것은
    "제약 두 개짜리 배낭 문제"이고 그마저도 소포라 항목 하나가 용량의 0.1%도 안 된다.
    그런 문제에서 작은 것부터 담는 그리디는 최적해에 사실상 붙는다.

    반대로 CP-SAT는 후보 4,000건에서 제한 시간(1초) 안에 해를 못 찾고 UNKNOWN을 돌려주는
    일이 있었다. 그러면 5.8 원칙에 따라 0건으로 끝나서, 화면에는 "실을 수 있는 운송장이
    없다"가 뜬다 — 공간이 53CBM 남아 있는데도. 후보 수에 따라 결과가 뒤집히는 계산은
    배차 근거로 쓸 수 없다.

    담는 순서는 **부피당 무게가 가벼운 것부터**다. 부피만 보고 작은 것부터 담으면
    중량 한도가 먼저 차서 부피가 남는다. 실제로 후보를 1만에서 10만으로 늘렸더니
    적재율이 68%에서 40%로 **떨어졌다** — 작은 소포일수록 부피당 무게가 무거워
    (박스타입 A는 0.04CBM에 5kg) 가벼운 순서가 아니라 작은 순서로 담으면 11톤 한도를
    2,283건에서 다 써 버리고 적재함은 40%만 찼다.

    후보를 늘렸는데 결과가 나빠지는 계산은 배차 근거로 쓸 수 없다. 중량이 한도에
    걸리는 구조에서는 kg/CBM이 낮은 것부터 담아야 같은 무게로 더 많은 부피를 채운다.
    """
    def density(c):
        # kg/CBM. 부피가 0이면 나눌 수 없으니 맨 뒤로 보낸다.
        return (c.weight_kg / c.volume_cbm) if c.volume_cbm > 0 else float("inf")

    order = sorted(cargos, key=lambda c: (density(c), c.volume_cbm, c.cargo_id))

    selected: List[SelectedCargo] = []
    used_cbm = 0.0
    used_kg = 0.0
    for c in order:
        if used_cbm + c.volume_cbm > free_cbm:
            # 큰 것 하나가 안 들어가도 뒤의 더 작은 것은 들어갈 수 있다. 계속 본다.
            continue
        if used_kg + c.weight_kg > remaining_weight_kg:
            continue
        used_cbm += c.volume_cbm
        used_kg += c.weight_kg
        selected.append(SelectedCargo(
            cargo_id=c.cargo_id,
            volume_cbm=round(c.volume_cbm, 3),
            weight_kg=round(c.weight_kg, 1),
            pickup_order=len(selected) + 1,
            weight_source=c.weight_source,
            revenue_krw=c.revenue_krw,
            freight_krw=c.freight_krw,
            terminal_code=c.origin_terminal_code,
            terminal_name=c.origin_terminal_name,
            destination_terminal_code=c.destination_terminal_code,
            destination_terminal_name=c.destination_terminal_name,
            box_types=c.box_types,
            box_count=c.box_count,
            pickup_address=c.pickup_address,
            pickup_lat=c.pickup_lat,
            pickup_lng=c.pickup_lng,
        ))

    return selected, round(used_cbm, 3), round(used_kg, 1)


def _group_by_terminal(selected: List[SelectedCargo]) -> List[TerminalGroup]:
    """선택된 운송장을 출발-도착 작업터미널 쌍으로 묶는다.

    기사가 판단하는 단위는 낱건이 아니라 '어느 터미널에서 실어 어디로 내리는 묶음'이다.
    200건을 낱개로 늘어놓으면 어디를 들러야 하는지 읽히지 않는다.
    """
    groups: dict = {}
    for c in selected:
        key = (c.terminal_code or "", c.destination_terminal_code or "")
        g = groups.get(key)
        if g is None:
            g = groups[key] = TerminalGroup(
                origin_terminal_code=c.terminal_code,
                origin_terminal_name=c.terminal_name,
                destination_terminal_code=c.destination_terminal_code,
                destination_terminal_name=c.destination_terminal_name,
                origin_lat=c.pickup_lat,
                origin_lng=c.pickup_lng,
                pickup_address=c.pickup_address,
                box_type_counts={},
            )
        g.cargo_count += 1
        g.box_count += c.box_count or 1
        g.volume_cbm = round(g.volume_cbm + c.volume_cbm, 3)
        g.weight_kg = round(g.weight_kg + c.weight_kg, 1)
        g.revenue_krw += c.revenue_krw or 0.0
        g.freight_krw += c.freight_krw or 0.0
        # 박스타입이 비어 있으면(측정기가 타입을 못 낸 운송장) '미상'으로 센다.
        # 조용히 빼면 타입별 합계가 건수와 어긋나 화면에서 숫자가 안 맞는다.
        for t in (c.box_types or ["미상"]):
            g.box_type_counts[t] = g.box_type_counts.get(t, 0) + 1

    for g in groups.values():
        g.box_type_counts = dict(
            sorted(g.box_type_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        )
    return sorted(groups.values(), key=lambda g: (-g.cargo_count, g.origin_terminal_code or ""))


def _extract_event(payload: dict) -> Optional[SpaceGeometryReadyEvent]:
    """Pub/Sub push({message:{data:<base64>}})와 직접 POST(본문이 곧 이벤트) 양쪽을 받는다."""
    message = payload.get("message")
    if isinstance(message, dict) and message.get("data"):
        try:
            decoded = base64.b64decode(message["data"]).decode("utf-8")
            payload = json.loads(decoded)
        except Exception:
            logger.exception("Pub/Sub message.data 디코딩 실패")
            return None
    if not isinstance(payload, dict) or not payload.get("event_id"):
        return None
    try:
        return SpaceGeometryReadyEvent(**payload)
    except Exception:
        logger.exception("SpaceGeometryReady 스키마 불일치: %s", payload)
        return None


@app.post("/")
async def pubsub_push(request: Request):
    """M1: space-geometry-ready push 구독 수신점.

    Pub/Sub는 비-2xx를 실패로 보고 재전송하므로, 처리 불가한 페이로드는 로그만 남기고
    200으로 종료해 무한 재시도를 만들지 않는다.
    """
    try:
        payload = await request.json()
    except Exception:
        logger.warning("본문이 JSON이 아님")
        return {"status": "ignored"}

    event = _extract_event(payload)
    if event is None:
        return {"status": "ignored"}

    # 5.8: event_id로 중복 처리 방지
    if not firestore_client.claim_event(event.event_id):
        logger.info("중복 이벤트 무시: event_id=%s", event.event_id)
        return {"status": "duplicate"}

    try:
        result = _run_matching(event)
        firestore_client.save_matching_result(event.photo_id, result)
        logger.info(
            "Matching 완료: photo_id=%s can_load=%s selected=%d final_free_cbm=%s solver=%s route=%s",
            result.photo_id, result.can_load, len(result.selected_cargos),
            result.final_free_cbm, result.solver_status, result.route_source,
        )
    except Exception:
        logger.exception("Matching 처리 실패: photo_id=%s", event.photo_id)

    return {"status": "success"}


@app.post("/v1/match")
def run_matching_endpoint(event: SpaceGeometryReadyEvent):
    """데모/직접 호출용. 중복 방지 없이 매번 계산한다."""
    result = _run_matching(event)
    firestore_client.save_matching_result(event.photo_id, result)
    return result


@app.post("/v1/trucks/{truck_id}/match")
def match_by_truck(
    truck_id: str,
    candidates: Optional[int] = None,
    palletized: bool = False,
):
    """사진 없이 차량 제원만으로 추가 상차분을 계산하고 출발-도착 터미널로 묶는다.

    왜 사진을 받지 않는가: 적재된 박스를 0으로 본다. 그러면 실을 수 있는 공간은 등록
    적재함 체적 그 자체이고, 사진에서 빈 공간을 추정할 이유가 사라진다.

    왜 위치로 후보를 좁히지 않는가: 여기서 묻는 것은 "이 차에 뭐가 실리나"뿐이다.
    회랑(M2)과 우회시간(M4)은 "지금 트럭 근처에서 들를 만한가"에 답하는 단계라 이
    질문에는 필요 없다. 빼고 나면 Routes API 호출도, 그 실패로 매칭이 통째로 죽는
    경로(routes_api_failed)도 함께 사라진다.

    그래서 사진 경로(_run_matching)와 다른 함수다. 판정 근거가 다르다는 사실은
    decision_scope=CBM_WEIGHT_ONLY와 route_source=NOT_COMPUTED로 결과에 남는다.
    """
    truck = firestore_client.get_truck_state(truck_id)
    if truck is None:
        raise HTTPException(status_code=404, detail=f"차량 {truck_id} 미등록")
    if truck.cargo_capacity_cbm is None:
        # 적재함 체적이 없으면 실을 공간을 지어낼 수밖에 없다. 5.8 fail-closed.
        raise HTTPException(
            status_code=422,
            detail=f"차량 {truck_id}에 cargo_capacity_cbm이 없어 잔여 체적을 정할 수 없습니다",
        )

    raw_capacity = round(truck.cargo_capacity_cbm, 3)
    free_cbm = raw_capacity
    pallet = _palletized_capacity(truck) if palletized else None
    if palletized and pallet is None:
        raise HTTPException(
            status_code=422,
            detail=f"차량 {truck_id}에 적재함 치수가 없어 파렛트 배치를 계산할 수 없습니다",
        )
    if pallet is not None:
        free_cbm = pallet["usable_cbm"]

    loaded_kg = truck.current_loaded_weight_kg or 0.0
    remaining_weight_kg = max(0.0, truck.max_payload_kg - loaded_kg - truck.reserved_added_weight_kg)

    now = datetime.now(timezone.utc)
    # 결과 저장 키. 사진이 없으므로 차량+시각으로 만든다. 매번 새 키라 갱신할 때마다
    # 이전 결과를 덮지 않고 이력이 남는다.
    photo_id = f"D-{truck_id}-{int(now.timestamp())}"

    # 위치로 후보를 좁히지 않는다. 회랑은 "지금 트럭 근처에 뭐가 있나"를 묻지만
    # 여기서 묻는 것은 "이 차에 뭐가 실리나"뿐이고, 그 답에는 트럭 위치가 필요 없다.
    # 우회시간도 계산하지 않으므로 Routes API를 부르지 않는다 — 호출 비용과 rate limit,
    # 그리고 그 실패로 매칭이 통째로 죽는 경로가 함께 사라진다.
    # 후보 상한은 화면이 고를 수 있다. 많이 볼수록 더 많이 실리지만 Firestore 읽기와
    # 솔버 시간이 함께 늘어난다. 상한을 넘기는 값은 조용히 잘라내지 않고 최대치로 맞춘다.
    limit = config.MAX_CANDIDATE_FETCH if candidates is None else candidates
    limit = max(1, min(int(limit), config.CANDIDATE_FETCH_MAX))

    candidate_cargos = firestore_client.query_waiting_cargos(limit=limit)
    logger.info(
        "차량 기준 매칭 후보: %d건 (상한 %d, 위치 필터 없음)", len(candidate_cargos), limit
    )

    # 먼저 조합 최적화를 돌린다. 우회시간이 없으므로 목적함수는 적재량 최대화만 남는다.
    #
    # 실패하면 그리디로 떨어진다. CP-SAT는 후보가 수천 건이면 제한 시간 안에 해를 못 찾고
    # UNKNOWN을 돌려주는 일이 있는데, 그때 5.8 원칙대로 0건으로 끝내면 공간이 53CBM
    # 남았는데도 "실을 수 있는 운송장이 없다"가 뜬다. 사진 경로에서 그 원칙이 옳은 이유는
    # 품질을 못 믿어서인데, 여기서는 부피와 중량뿐이라 못 믿을 것이 없다. 제한 시간을
    # 못 지킨 것을 "실을 것이 없다"로 바꿔 말하면 안 된다.
    solve_method = "CP_SAT"
    result = None
    # SOLVER_MAX_CANDIDATES=0이면 규모와 무관하게 최적화를 돌린다(기본값).
    skip_solver = (
        config.SOLVER_MAX_CANDIDATES > 0
        and len(candidate_cargos) > config.SOLVER_MAX_CANDIDATES
    )
    if skip_solver:
        logger.info(
            "후보 %d건 > 솔버 한계 %d건 — CP-SAT를 건너뛰고 그리디로 간다",
            len(candidate_cargos), config.SOLVER_MAX_CANDIDATES,
        )
    else:
        try:
            result = solver.solve(
                cargos=candidate_cargos,
                usable_free_cbm=free_cbm,
                remaining_weight_kg=remaining_weight_kg,
                start_lat=truck.current_lat if truck.current_lat is not None else 0.0,
                start_lng=truck.current_lng if truck.current_lng is not None else 0.0,
                geometry_risk_penalty=0,
            )
        except Exception:
            logger.exception("CP-SAT 실패 — 그리디로 넘어간다")
            result = None

    if result is not None and result.status in ("OPTIMAL", "FEASIBLE") and result.selected:
        selected = result.selected
        used_cbm = result.selected_volume_cbm
        used_kg = sum(c.weight_kg or 0 for c in selected)
        solve_method = result.status
    else:
        if skip_solver:
            reason = f"후보 {len(candidate_cargos)}건 > 한계 {config.SOLVER_MAX_CANDIDATES}건"
        else:
            reason = f"CP_SAT={result.status if result is not None else 'ERROR'}"
            logger.warning("CP-SAT가 해를 내지 못했다(%s) — 그리디 채우기로 대체", reason)
        selected, used_cbm, used_kg = _fill_by_capacity(
            candidate_cargos, free_cbm, remaining_weight_kg
        )
        solve_method = f"GREEDY_FILL({reason})"

    can_load = len(selected) > 0
    matching = MatchingResult(
        truck_id=truck_id,
        photo_id=photo_id,
        estimated_free_cbm=free_cbm,
        usable_free_cbm=free_cbm,
        # 사진이 없으니 '못 본 공간'도 없다. 측정을 안 한 것이지 불확실한 게 아니다.
        unknown_cbm=0.0,
        remaining_weight_kg=round(remaining_weight_kg, 1),
        can_load=can_load,
        selected_cargos=selected,
        terminal_groups=_group_by_terminal(selected) if can_load else [],
        # 수수료·운임·우회는 이 경로에서 계산하지 않는다. 화면도 쓰지 않는다.
        pickup_stops=[],
        added_revenue_krw=sum(c.revenue_krw or 0 for c in selected),
        added_detour_seconds=0,
        added_commission_krw=sum(c.revenue_krw or 0 for c in selected),
        added_freight_krw=sum(c.freight_krw or 0 for c in selected),
        fill_reward_krw=0.0,
        detour_cost_krw=0.0,
        risk_cost_krw=0.0,
        net_gain_krw=0.0,
        breakeven_cargo_count=None,
        final_free_cbm=round(max(0.0, free_cbm - used_cbm), 3),
        quality_score=1.0,
        quality_status=QualityStatus.ACCEPTED,
        # 무엇을 근거로 판정했는지 남긴다. 경로 타당성은 보지 않았다.
        decision_scope="CBM_WEIGHT_ONLY",
        # 어떤 방식으로 골랐는지 그대로 남긴다. 화면의 설명이 이 값을 보고 문장을
        # 바꾼다 — 그리디로 떨어졌는데 "최적화했다"고 말하면 설명이 거짓이 된다.
        solver_status=solve_method,
        candidate_count=len(candidate_cargos),
        candidate_limit=limit,
        candidate_limit_max=config.CANDIDATE_FETCH_MAX,
        pallet_mode=bool(pallet),
        pallet_count=pallet["count"] if pallet else None,
        pallet_spec=pallet["spec"] if pallet else None,
        raw_capacity_cbm=raw_capacity,
        pallet_loss_cbm=round(raw_capacity - free_cbm, 3) if pallet else None,
        route_source="NOT_COMPUTED",
        failure_reason=None if can_load else (
            "no_candidate_cargo" if not candidate_cargos
            else "capacity_too_small_for_any_cargo"
        ),
    )

    firestore_client.save_matching_result(photo_id, matching)
    logger.info(
        "차량 기준 매칭: truck_id=%s free_cbm=%s 후보=%d 선택=%d(%.2fCBM/%.0fkg) 그룹=%d",
        truck_id, free_cbm, len(candidate_cargos), len(matching.selected_cargos),
        used_cbm, used_kg, len(matching.terminal_groups),
    )
    return matching


@app.get("/v1/results/{photo_id}")
def get_result(photo_id: str):
    """5.3: PWA가 조회하는 최종 결과 계약."""
    result = firestore_client.get_matching_result(photo_id)
    if result is None:
        raise HTTPException(status_code=404, detail="결과 없음")
    return result


# ---------------------------------------------------------------------------
# 운송장 등록
# ---------------------------------------------------------------------------

@app.post("/v1/cargos")
def register_cargo(cargo: CargoRegistration):
    """화주사 웹 폼용. 건당 등록.

    수십만 건 규모는 이 경로로 넣지 않는다. 파일 적재나 :batch를 쓴다.
    """
    result = cargo_ingest.write_cargos([cargo.model_dump(mode="json")], firestore_client.client())
    if result["written"] == 0:
        raise HTTPException(status_code=400, detail=result["errors"] or "등록 실패")
    return {"status": "ok", "cargo_id": cargo.cargo_id}


@app.post("/v1/cargos:batch")
def register_cargos_batch(payload: CargoBatch):
    """화주사 시스템 연동용. 호출당 최대 500건(Firestore 일괄 쓰기 상한)."""
    if len(payload.cargos) > config.INGEST_MAX_BATCH:
        raise HTTPException(
            status_code=413,
            detail=f"한 번에 {config.INGEST_MAX_BATCH}건까지 보낼 수 있습니다.",
        )
    rows = [c.model_dump(mode="json") for c in payload.cargos]
    return cargo_ingest.write_cargos(rows, firestore_client.client())


@app.get("/v1/cargos")
def list_cargos(
    limit: int = 100,
    terminal_code: Optional[str] = None,
    destination_terminal_code: Optional[str] = None,
    page: int = 1,
):
    """대기 중인 운송장 목록. 조회 화면이 쓴다.

    적재가 됐는지, 어느 터미널에 얼마나 쌓였는지를 눈으로 확인할 창구가 없었다.
    Firestore 콘솔을 열지 않고도 볼 수 있어야 한다.

    terminal_code는 **출발** 작업터미널이다. 이름을 그대로 두는 이유는 이미 나가 있는
    링크와 화면이 이 이름으로 부르고 있어서다.
    """
    limit = max(1, min(limit, 500))
    page = max(1, page)
    cargos = firestore_client.list_pending_cargos(
        limit=limit,
        terminal_code=terminal_code,
        destination_terminal_code=destination_terminal_code,
        offset=(page - 1) * limit,
    )

    # 이 페이지 안에서의 출발터미널별 집계. 전체 건수가 아니라는 점을 화면에도 밝힌다.
    by_terminal: dict = {}
    for c in cargos:
        code = c.get("origin_terminal_code") or "미지정"
        g = by_terminal.setdefault(code, {
            "terminal_code": code, "terminal_name": c.get("origin_terminal_name"),
            "count": 0, "volume_cbm": 0.0, "freight_krw": 0, "commission_krw": 0,
        })
        g["count"] += 1
        g["volume_cbm"] = round(g["volume_cbm"] + (c.get("volume_cbm") or 0), 3)
        g["freight_krw"] += c.get("freight_krw") or 0
        g["commission_krw"] += c.get("commission_krw") or 0

    # 출발-도착 쌍별 집계. 기사 화면의 그룹과 같은 축이라, 조회 화면에서 미리 어떤
    # 묶음이 쌓여 있는지 볼 수 있어야 한다.
    by_route: dict = {}
    for c in cargos:
        key = (c.get("origin_terminal_code") or "미지정",
               c.get("destination_terminal_code") or "미지정")
        g = by_route.setdefault(key, {
            "origin_terminal_code": key[0],
            "origin_terminal_name": c.get("origin_terminal_name"),
            "destination_terminal_code": key[1],
            "destination_terminal_name": c.get("destination_terminal_name"),
            "count": 0, "box_count": 0, "box_type_counts": {},
            "volume_cbm": 0.0, "commission_krw": 0,
        })
        g["count"] += 1
        g["box_count"] += c.get("box_count") or 0
        g["volume_cbm"] = round(g["volume_cbm"] + (c.get("volume_cbm") or 0), 3)
        g["commission_krw"] += c.get("commission_krw") or 0
        for t in (c.get("box_types") or ["미상"]):
            g["box_type_counts"][t] = g["box_type_counts"].get(t, 0) + 1
    for g in by_route.values():
        g["box_type_counts"] = dict(
            sorted(g["box_type_counts"].items(), key=lambda kv: (-kv[1], kv[0]))
        )

    # 전체 건수는 필터가 없을 때만 정확하다. 필터를 건 총계까지 세려면 조합마다
    # 복합색인이 필요해서, 있는 그대로 필터 없음일 때만 준다.
    total = None
    if not terminal_code and not destination_terminal_code:
        try:
            total = firestore_client.count_pending_cargos()
        except Exception:
            logger.exception("대기 운송장 총계 조회 실패 — 건수 없이 응답한다")

    return {
        "cargos": cargos,
        "returned": len(cargos),
        "limit": limit,
        "page": page,
        "total": total,
        # 이번 페이지가 꽉 찼으면 다음이 있을 수 있다. 정확한 마지막 페이지 판정은
        # 필터를 파이썬에서 거르는 구조라 보장하지 않는다.
        "has_more": len(cargos) >= limit,
        "by_terminal": sorted(by_terminal.values(), key=lambda t: -t["count"]),
        "by_route": sorted(by_route.values(), key=lambda g: -g["count"]),
        # 이 목록을 다 처리하면 얼마인지. 기사에게 "왜 이걸 봐야 하는지"를 주는 숫자다.
        "total_freight_krw": sum(c.get("freight_krw") or 0 for c in cargos),
        "total_commission_krw": sum(c.get("commission_krw") or 0 for c in cargos),
        "total_volume_cbm": round(sum(c.get("volume_cbm") or 0 for c in cargos), 3),
    }


@app.post("/v1/waybills")
def register_waybills(payload: WaybillBatch):
    """체적 측정기 포맷 그대로 등록한다. 웹 폼의 건당 등록 경로.

    체적·중량·상차좌표를 받지 않는 이유는 원본 CSV에 그 컬럼이 없기 때문이다. 화면은
    측정기가 주는 값(치수·작업터미널·상품코드)만 보내고, 파생값은 파일 적재와 똑같은
    코드가 만든다.
    """
    if not payload.boxes:
        raise HTTPException(status_code=400, detail="박스가 비어 있습니다.")
    if len(payload.boxes) > config.INGEST_MAX_BATCH:
        raise HTTPException(
            status_code=413, detail=f"한 번에 {config.INGEST_MAX_BATCH}건까지 보낼 수 있습니다."
        )

    rows = [b.model_dump() for b in payload.boxes]
    result = cargo_ingest.ingest_waybill_rows(rows, firestore_client.client(), source="web-form")
    _log_ingest(result, "웹 폼")
    if result["written"] == 0:
        # 미등록 터미널이 가장 흔한 실패다. 사유를 그대로 화면에 띄운다.
        raise HTTPException(status_code=400, detail=result["errors"] or "등록 실패")
    return result


def _log_ingest(result: dict, where: str) -> None:
    """운송장 포맷은 '행'과 '운송장'이 1:1이 아니다. 박스 8행이 운송장 1건이 되기도
    해서 행 수만 보면 적재가 누락된 것처럼 보인다. 층위를 나눠 남긴다."""
    logger.info(
        "운송장 적재(%s): written=%d failed=%d", where, result["written"], result["failed"]
    )
    if result.get("format") != "WAYBILL_VOLUME_V1":
        return
    logger.info(
        "  박스 %d행 -> 운송장 %d건, 미측정 %d행, 이미 만료 %d건%s",
        result["box_rows"], result["waybills"], result["unmeasured_rows"], result["already_expired"],
        " (만료분은 저장하지 않음)" if config.INGEST_SKIP_EXPIRED else "",
    )
    if result["already_expired"] and result["written"] == 0:
        logger.warning(
            "  적재된 운송장이 없다 — 파일의 생성일시가 모두 %s시간을 넘겼다. "
            "과거 데이터로 시연하려면 WAYBILL_VALID_HOURS를 늘려야 한다.",
            config.WAYBILL_VALID_HOURS,
        )
    if result["unknown_terminals"]:
        logger.warning(
            "  좌표 미등록 작업터미널 %s — POST /v1/terminals로 등록해야 적재된다",
            result["unknown_terminals"],
        )
    # 세로와 높이가 같은 행. 전 행이 그렇다면 측정기가 축 하나를 복제했을 수 있고,
    # 그 경우 체적이 전부 틀린다. 조용히 넘기지 않는다.
    if result["depth_eq_height_rows"] and result["depth_eq_height_rows"] == result["box_rows"]:
        logger.warning(
            "  세로==높이인 행이 %d행 전부다 — 측정기가 축을 복제했는지 확인 필요 "
            "(사실이면 체적이 모두 틀린다)", result["box_rows"],
        )
    if result["errors"]:
        logger.warning("적재 중 건너뛴 행(최대 %d건): %s",
                       config.INGEST_MAX_REPORTED_ERRORS, result["errors"])


@app.post("/v1/events/cargo-file")
async def cargo_file_uploaded(request: Request):
    """주 경로. GCS에 올라온 CSV/JSONL을 Eventarc가 알려주면 적재한다.

    사진 파이프라인과 같은 구조지만 버킷이 다르다. matching은 사진 버킷에 접근 권한이
    없고(1.3/5.9), 이 적재 버킷에만 읽기 권한을 받는다.

    Eventarc는 비-2xx를 실패로 보고 재시도하므로 항상 200을 반환한다.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    bucket = payload.get("bucket")
    name = payload.get("name")
    if not bucket or not name:
        logger.warning("cargo-file 이벤트에서 bucket/name을 찾지 못함: %s", payload)
        return {"status": "ignored"}

    if not name.lower().endswith((".csv", ".jsonl", ".ndjson", ".json")):
        logger.info("적재 대상 확장자가 아니라 건너뜀: %s", name)
        return {"status": "skipped", "object": name}

    try:
        text = storage_reader.download_text(bucket, name)
        table = cargo_ingest.parse_by_name(name, text)
        result = cargo_ingest.ingest_table(table, firestore_client.client(), source=f"gs://{bucket}/{name}")
        _log_ingest(result, f"gs://{bucket}/{name}")
    except Exception:
        logger.exception("운송장 파일 적재 실패: gs://%s/%s", bucket, name)

    return {"status": "success"}


# ---------------------------------------------------------------------------
# 작업터미널 좌표 등록
# ---------------------------------------------------------------------------

@app.get("/v1/route")
def get_route(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float):
    """지도에 그릴 주행 경로. 촬영 화면이 현재 위치 -> 목적지 선을 그릴 때 쓴다.

    카카오 REST 키를 브라우저에 노출하지 않으려고 서버가 대신 부른다. 경로를 못 찾으면
    path를 비워 돌려준다 — 직선으로 대신 그리면 실제 도로처럼 보여 거리를 오해하게 된다.
    """
    try:
        result = routes_client.route_path((origin_lat, origin_lng), (dest_lat, dest_lng))
    except routes_client.RoutesApiError as exc:
        logger.warning("경로 조회 실패: %s", exc)
        return {"path": [], "reason": "경로 조회 실패"}
    if result is None:
        return {"path": [], "reason": "경로를 찾지 못했습니다"}
    return result


@app.get("/v1/terminals")
def list_terminals():
    """등록된 작업터미널. 운송장 파일 적재의 선행 데이터다."""
    return {"terminals": terminals.list_all(firestore_client.client())}


@app.post("/v1/terminals")
def register_terminal(terminal: TerminalRegistration):
    """작업터미널 코드에 좌표를 붙인다.

    운송장 체적 파일에는 좌표가 없고 작업터미널 코드만 있다. 여기 등록되지 않은
    터미널의 행은 적재되지 않는다 — 임의 좌표로 채우면 매칭이 그럴듯하게 틀린다.
    """
    try:
        saved = terminals.upsert(terminal.model_dump(), firestore_client.client())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", "terminal": saved}
