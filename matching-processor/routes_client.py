import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

import requests

import config
from geo import detour_seconds_via
from schemas import Cargo, TruckState

logger = logging.getLogger("matching-processor")

# 카카오모빌리티 길찾기(단일 목적지).
#
# 다중 목적지 API(/v1/destinations/directions)를 먼저 시도했으나 쓸 수 없었다.
# 그 API의 radius는 도로 스냅 반경이 아니라 **길찾기 반경**이고 상한이 10km라,
# 목적지가 그보다 멀면 result_code 304 "목적지가 설정한 길 찾기 반경 범위를 벗어남"으로
# 거부된다. 회랑 반경이 30km이고 최종 목적지는 수백 km일 수 있어 전혀 맞지 않는다.
# 단일 길찾기는 거리 제한이 없어(대전->서울 180km 정상 응답) 이쪽을 병렬로 호출한다.
KAKAO_DIRECTIONS_URL = "https://apis-navi.kakaomobility.com/v1/directions"

# 결과에 기록할 우회시간 출처. 추정치를 실측처럼 보이게 하지 않기 위해 항상 남긴다.
SOURCE_KAKAO = "KAKAO_NAVI"
SOURCE_HAVERSINE = "HAVERSINE_FALLBACK"


class RoutesApiError(Exception):
    pass


def _duration(origin: Tuple[float, float], dest: Tuple[float, float]) -> Optional[int]:
    """한 구간의 주행 소요시간(초). 경로를 못 찾으면 None.

    좌표는 (lat, lng)로 받아 카카오가 요구하는 "경도,위도" 순서로 바꾼다.
    이 순서를 뒤집으면 엉뚱한 곳으로 경로를 잡는다.
    """
    resp = requests.get(
        KAKAO_DIRECTIONS_URL,
        params={
            "origin": f"{origin[1]},{origin[0]}",
            "destination": f"{dest[1]},{dest[0]}",
            "priority": "TIME",
            "summary": "true",
        },
        headers={"Authorization": f"KakaoAK {config.KAKAO_REST_API_KEY}"},
        timeout=config.ROUTES_API_TIMEOUT_S,
    )
    if resp.status_code != 200:
        raise RoutesApiError(f"{resp.status_code} {resp.text[:200]}")

    routes = resp.json().get("routes") or []
    if not routes:
        return None
    route = routes[0]
    if route.get("result_code") != 0:
        # 개별 실패(도로 없음 등)는 전체를 중단시키지 않고 해당 구간만 버린다.
        logger.warning("경로 실패: code=%s msg=%s", route.get("result_code"), route.get("result_msg"))
        return None
    return int((route.get("summary") or {}).get("duration", 0)) or None


def route_path(
    origin: Tuple[float, float], dest: Tuple[float, float]
) -> Optional[dict]:
    """지도에 그릴 실제 주행 경로. {distance_m, duration_s, path:[[lng,lat],...]}.

    `summary=false`로 불러야 구간(sections)과 도로별 vertexes가 온다. _duration()은
    소요시간만 필요해 summary=true로 부르는데, 그 응답에는 좌표가 없다.

    vertexes는 [x1,y1,x2,y2,...]로 평평하게 오는 경도·위도 배열이다. 둘씩 끊어야 한다.
    키가 없거나 경로를 못 찾으면 None을 돌려주고, 호출자는 지도에 선을 그리지 않는다 —
    직선으로 대신 그리면 실제 도로처럼 보여서 거리를 오해하게 만든다.
    """
    if not config.KAKAO_REST_API_KEY:
        return None

    resp = requests.get(
        KAKAO_DIRECTIONS_URL,
        params={
            "origin": f"{origin[1]},{origin[0]}",
            "destination": f"{dest[1]},{dest[0]}",
            "priority": "TIME",
        },
        headers={"Authorization": f"KakaoAK {config.KAKAO_REST_API_KEY}"},
        timeout=config.ROUTES_API_TIMEOUT_S,
    )
    if resp.status_code != 200:
        raise RoutesApiError(f"{resp.status_code} {resp.text[:200]}")

    routes = resp.json().get("routes") or []
    if not routes or routes[0].get("result_code") != 0:
        return None

    route = routes[0]
    path = []
    for section in route.get("sections") or []:
        for road in section.get("roads") or []:
            v = road.get("vertexes") or []
            path.extend([v[i], v[i + 1]] for i in range(0, len(v) - 1, 2))

    if not path:
        return None
    summary = route.get("summary") or {}
    return {
        "distance_m": summary.get("distance"),
        "duration_s": summary.get("duration"),
        "path": path,
    }


def _haversine_detour(truck: TruckState, c: Cargo) -> int:
    return detour_seconds_via(
        truck.current_lat, truck.current_lng,
        c.pickup_lat, c.pickup_lng,
        truck.destination_lat, truck.destination_lng,
        config.FALLBACK_AVG_SPEED_KMH,
    )


def compute_detours(truck: TruckState, cargos: List[Cargo]) -> Tuple[List[Cargo], str]:
    """M4: 후보별 우회시간(초)을 채워 반환한다. 반환값은 (cargos, route_source).

    후보 N개에 대해 2N+1번 호출한다(현재위치->상차지 N, 상차지->목적지 N, 기준선 1).
    설계서 5.4가 후보를 Top 10-20으로 제한하는 덕에 최대 41회로 묶인다. 병렬로 던진다.

    5.8 "Routes API 실패 -> 유효한 직전 cache가 없으면 신규 추천 중단"에 따라, 키가 설정된
    상태에서 호출 자체가 실패하면 RoutesApiError를 올려 호출자가 중단하게 한다.
    키가 아예 없는 경우는 '실패'가 아니라 '미구성'이므로 직선거리 추정으로 degrade한다.
    """
    if not cargos:
        return cargos, SOURCE_HAVERSINE

    if not config.KAKAO_REST_API_KEY:
        logger.warning("KAKAO_REST_API_KEY 미설정 - 직선거리 기반 우회시간 추정으로 degrade한다.")
        for c in cargos:
            c.detour_seconds = _haversine_detour(truck, c)
        return cargos, SOURCE_HAVERSINE

    here = (truck.current_lat, truck.current_lng)
    there = (truck.destination_lat, truck.destination_lng)

    # **상차지 단위로 묶어서** 호출한다.
    #
    # 작업터미널 코드가 곧 상차지라, 같은 터미널의 운송장 수백 건이 좌표 하나를 공유한다.
    # 후보마다 부르면 같은 경로를 수백 번 조회하게 되고, 그 비용 때문에 후보 수를
    # Top 20으로 묶어 두었다. 묶고 나면 호출 수가 후보 수가 아니라 **지점 수**에 비례해서,
    # 후보를 수백 건으로 늘려도 호출은 그대로다.
    #
    # 이 제약이 실제로 매칭을 막고 있었다. 수수료가 운임의 1%면 소포 한 건에 75원이라
    # 상차지 고정비(우회 + 위험 1만 원대)를 넘으려면 70건 이상이 필요한데, 후보가 20건뿐이라
    # 아무리 공간이 남아도 이익이 나지 않았다.
    unique: dict = {}
    for c in cargos:
        unique.setdefault((round(c.pickup_lat, 5), round(c.pickup_lng, 5)), None)
    points = list(unique.keys())

    legs = [(here, p) for p in points]
    legs += [(p, there) for p in points]
    legs.append((here, there))

    with ThreadPoolExecutor(max_workers=config.ROUTES_MAX_PARALLEL) as pool:
        durations = list(pool.map(lambda leg: _duration(*leg), legs))

    n = len(points)
    base_seconds = durations[-1] or 0
    by_point = {}
    for i, p in enumerate(points):
        to_pickup, from_pickup = durations[i], durations[n + i]
        by_point[p] = (
            None
            if to_pickup is None or from_pickup is None
            else max(0, to_pickup + from_pickup - base_seconds)
        )

    for c in cargos:
        detour = by_point.get((round(c.pickup_lat, 5), round(c.pickup_lng, 5)))
        # 경로를 못 구한 후보는 직선거리 추정으로 채운다. 0으로 두면 우회가 공짜인 것처럼
        # 보여 solver가 그 후보를 잘못 선택한다.
        c.detour_seconds = _haversine_detour(truck, c) if detour is None else detour

    return cargos, SOURCE_KAKAO
