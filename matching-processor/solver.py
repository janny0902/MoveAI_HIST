import logging
from dataclasses import dataclass, field
from typing import List, Optional

from ortools.sat.python import cp_model

import config
from geo import haversine_km
from schemas import Cargo, PickupStop, SelectedCargo

logger = logging.getLogger("matching-processor")

# 5.2: CP-SAT는 정수만 다루므로 CBM -> liter, 시간 -> 초, 중량 -> kg로 변환한다.
LITER_PER_CBM = 1000


@dataclass
class SolveResult:
    status: str  # OPTIMAL / FEASIBLE / INFEASIBLE / UNKNOWN / MODEL_INVALID
    selected: List[SelectedCargo]
    selected_volume_cbm: float
    pickup_stops: List[PickupStop] = field(default_factory=list)
    added_revenue_krw: float = 0.0
    added_detour_seconds: int = 0
    # 목적함수를 풀어 쓴 값. "왜 이익이 나는가"의 근거다.
    fill_reward_krw: float = 0.0
    detour_cost_krw: float = 0.0
    risk_cost_krw: float = 0.0
    net_gain_krw: float = 0.0
    breakeven_cargo_count: Optional[int] = None


def _order_pickups(selected: List[Cargo], start_lat: float, start_lng: float) -> List[Cargo]:
    """선택된 상차지의 방문 순서를 현재 위치에서 시작하는 최근접 이웃으로 정한다.

    설계서 5.2가 나열한 in/out flow 제약과 subtour 제거를 갖춘 완전한 VRP는 구현하지 않았다
    (8시간 MVP 범위 밖). 따라서 pickup_order는 최적 경로가 아니라 실행 가능한 방문 순서다.
    """
    remaining = list(selected)
    ordered: List[Cargo] = []
    lat, lng = start_lat, start_lng
    while remaining:
        nxt = min(remaining, key=lambda c: haversine_km(lat, lng, c.pickup_lat, c.pickup_lng))
        ordered.append(nxt)
        remaining.remove(nxt)
        lat, lng = nxt.pickup_lat, nxt.pickup_lng
    return ordered


def solve(
    cargos: List[Cargo],
    usable_free_cbm: float,
    remaining_weight_kg: float,
    start_lat: float,
    start_lng: float,
    geometry_risk_penalty: int = 0,
) -> SolveResult:
    """M5: 5.2의 1:N 조합 최적화. 후보가 없으면 solver를 돌리지 않고 INFEASIBLE로 끝낸다."""
    if not cargos:
        return SolveResult(status="INFEASIBLE", selected=[], selected_volume_cbm=0.0)

    model = cp_model.CpModel()
    x = [model.NewBoolVar(f"x_{i}") for i in range(len(cargos))]

    usable_free_liter = int(usable_free_cbm * LITER_PER_CBM)
    volume_liters = [int(round(c.volume_cbm * LITER_PER_CBM)) for c in cargos]
    weights = [int(round(c.weight_kg)) for c in cargos]
    detours = [int(c.detour_seconds or 0) for c in cargos]

    # 상차지가 같은 화물은 한 번만 들르면 된다.
    #
    # 이걸 구분하지 않으면 같은 터미널의 소포 20건에 우회시간을 20번 물린다. 실제로
    # 터미널 하나에 운송장 수백 건이 쌓이는 구조라(작업터미널 코드가 곧 상차지다) 그
    # 차이가 결정적이다. 건당 900초씩 물리면 MAX_DETOUR_SECONDS(3600)에 4건이면 예산이
    # 끝나고, 목적함수에서도 건당 27,000씩 깎여 소포는 절대 선택되지 않는다.
    #
    # 좌표를 5자리(약 1m)로 반올림해 묶는다. 터미널 좌표는 대응표에서 오므로 정확히 같다.
    stops: dict = {}
    stop_of = []
    for c in cargos:
        key = (round(c.pickup_lat, 5), round(c.pickup_lng, 5))
        stop_of.append(stops.setdefault(key, len(stops)))

    y = [model.NewBoolVar(f"y_{g}") for g in range(len(stops))]
    # 그 상차지의 우회시간은 거기 속한 화물 중 최댓값으로 본다(같은 지점이라 사실상 동일).
    stop_detour = [0] * len(stops)
    for i, g in enumerate(stop_of):
        stop_detour[g] = max(stop_detour[g], detours[i])
        # 화물을 실으려면 그 상차지에 들러야 한다.
        model.Add(x[i] <= y[g])
    # 아무 화물도 안 싣는 상차지에 들르지 않는다.
    for g in range(len(stops)):
        model.Add(y[g] <= sum(x[i] for i in range(len(cargos)) if stop_of[i] == g))

    # 체적 제약
    model.Add(sum(volume_liters[i] * x[i] for i in range(len(cargos))) <= usable_free_liter)
    # 중량 제약
    model.Add(sum(weights[i] * x[i] for i in range(len(cargos))) <= int(remaining_weight_kg))
    # 최대 허용 우회시간(합산 예산). 들르는 지점 기준으로 센다.
    model.Add(sum(stop_detour[g] * y[g] for g in range(len(stops))) <= config.MAX_DETOUR_SECONDS)

    # 목적함수: 운임 + 적재보상 - 우회패널티(지점당) - 기하위험패널티(지점당)
    #
    # 기하위험은 **사진 한 장의 속성**이지 화물 각각의 속성이 아니다. 화물마다 물리면
    # 많이 실을수록 벌점이 커져 방향이 거꾸로다. 실제로 LIMITED 사진에서 건당 -50,000이
    # 붙어, 운임이 없는 운송장(적재보상 1,500)은 어떤 조합도 양수가 되지 못했다.
    # 위험은 "이 사진을 믿고 상차하러 간다"는 결정에 한 번 붙는 것이므로 지점당으로 옮긴다.
    model.Maximize(
        sum(
            x[i] * (int(round(cargos[i].revenue_krw)) + config.FILL_REWARD_PER_LITER * volume_liters[i])
            for i in range(len(cargos))
        )
        - sum(
            y[g] * (config.DETOUR_PENALTY_PER_SECOND * stop_detour[g] + geometry_risk_penalty)
            for g in range(len(stops))
        )
    )

    # 목적함수 항을 그대로 남긴다. "후보는 있는데 0건 선택"이 나올 때 공간이 모자란
    # 것인지, 우회 비용이 큰 것인지, 운임이 0이라 이득이 없는 것인지 구분할 방법이
    # 이것뿐이다. 실제로 그 셋을 로그 없이 추측하다 두 번 틀렸다.
    logger.info(
        "솔버 입력: 후보 %d건 / 상차지 %d곳 / 공간 %dL / 중량 %dkg / 위험패널티 %d",
        len(cargos), len(stops), usable_free_liter, int(remaining_weight_kg), geometry_risk_penalty,
    )
    logger.info(
        "  후보 합계: 체적 %dL 중량 %dkg 운임 %d원 적재보상 %d원",
        sum(volume_liters), sum(weights),
        int(sum(c.revenue_krw for c in cargos)),
        config.FILL_REWARD_PER_LITER * sum(volume_liters),
    )
    logger.info(
        "  상차지별 우회: %s (초) -> 패널티 %s원",
        stop_detour, [d * config.DETOUR_PENALTY_PER_SECOND for d in stop_detour],
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = config.SOLVER_TIME_LIMIT_S
    status = solver.Solve(model)
    status_name = solver.StatusName(status)

    # 5.8: UNKNOWN/timeout은 신규 추천을 내지 않는다.
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveResult(status=status_name, selected=[], selected_volume_cbm=0.0)

    chosen = [cargos[i] for i in range(len(cargos)) if solver.Value(x[i]) == 1]
    if not chosen:
        # 0건이 "최적"이라는 뜻은 어떤 조합도 이득이 안 된다는 것이다. 목적값을 남겨
        # 얼마나 모자랐는지 보이게 한다.
        logger.warning(
            "0건 선택(%s): 목적값 %d — 어떤 조합도 비용을 넘지 못했다",
            status_name, int(solver.ObjectiveValue()),
        )
    ordered = _order_pickups(chosen, start_lat, start_lng)

    selected = [
        SelectedCargo(
            cargo_id=c.cargo_id,
            volume_cbm=round(c.volume_cbm, 3),
            weight_kg=round(c.weight_kg, 1),
            pickup_order=idx + 1,
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
        )
        for idx, c in enumerate(ordered)
    ]

    # 상차 계획. 기사가 실제로 움직이는 단위는 화물이 아니라 **지점**이다.
    # 방문 순서대로 묶어, 어디에 들러 무엇을 받고 얼마를 버는지 한 줄로 만든다.
    by_stop: dict = {}
    for c in ordered:
        key = (round(c.pickup_lat, 5), round(c.pickup_lng, 5))
        s = by_stop.get(key)
        if s is None:
            s = by_stop[key] = PickupStop(
                terminal_code=c.origin_terminal_code, terminal_name=c.origin_terminal_name,
                address=c.pickup_address, lat=c.pickup_lat, lng=c.pickup_lng,
                cargo_count=0, volume_cbm=0.0, weight_kg=0.0, revenue_krw=0.0, freight_krw=0.0,
                detour_seconds=c.detour_seconds,
            )
        s.cargo_count += 1
        s.volume_cbm = round(s.volume_cbm + c.volume_cbm, 3)
        s.weight_kg = round(s.weight_kg + c.weight_kg, 1)
        s.revenue_krw += c.revenue_krw
        s.freight_krw += c.freight_krw
        # 같은 지점이면 우회시간이 사실상 같다. 큰 쪽을 남긴다.
        if c.detour_seconds and (s.detour_seconds or 0) < c.detour_seconds:
            s.detour_seconds = c.detour_seconds

    stops_out = list(by_stop.values())

    # 수익 계산 내역. "왜 이익이 나는가"는 목적함수를 그대로 풀어 쓰면 답이 된다.
    #
    # 수수료가 운임의 1%라 한 건은 75원 남짓이다. 반면 상차지에 들르는 고정비(우회 시간
    # + 품질 위험)는 만 원대다. 그래서 **건수가 손익을 가른다.** 몇 건부터 이익인지를
    # 함께 내보내면, 물량이 많을수록 좋다는 구조가 숫자로 보인다.
    fee_total = sum(c.revenue_krw for c in ordered)
    fill_total = config.FILL_REWARD_PER_LITER * sum(
        int(round(c.volume_cbm * LITER_PER_CBM)) for c in ordered
    )
    detour_cost = config.DETOUR_PENALTY_PER_SECOND * sum(s.detour_seconds or 0 for s in stops_out)
    risk_cost = geometry_risk_penalty * len(stops_out)

    gain_per_cargo = (fee_total + fill_total) / len(ordered) if ordered else 0
    breakeven = (
        int(-(-(detour_cost + risk_cost) // gain_per_cargo)) if gain_per_cargo > 0 else None
    )

    return SolveResult(
        status=status_name,
        selected=selected,
        selected_volume_cbm=round(sum(c.volume_cbm for c in chosen), 3),
        pickup_stops=stops_out,
        added_revenue_krw=sum(s.revenue_krw for s in stops_out),
        # 지점마다 한 번씩만 센다. 화물 수만큼 더하면 실제보다 몇 배로 커진다.
        added_detour_seconds=sum(s.detour_seconds or 0 for s in stops_out),
        fill_reward_krw=fill_total,
        detour_cost_krw=detour_cost,
        risk_cost_krw=risk_cost,
        net_gain_krw=fee_total + fill_total - detour_cost - risk_cost,
        breakeven_cargo_count=breakeven,
    )
