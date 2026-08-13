import math
from typing import Tuple

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 사이 대권거리(km). M3 1차 필터와 Routes API 폴백에 쓴다."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bounding_box(lat: float, lng: float, radius_km: float) -> Tuple[float, float, float, float]:
    """중심점 기준 반경을 감싸는 위경도 박스 (lat_min, lat_max, lng_min, lng_max).

    설계서 M2는 Geohash 조회를 지시하지만 pending_cargos에 geohash 필드가 없다(10만 건).
    10만 건 전수 조회 대신 Firestore 다중 부등호 쿼리로 이 박스를 서버측에서 거르고,
    정확한 반경 판정은 haversine으로 애플리케이션에서 마무리한다(박스는 반경의 상위집합).
    """
    lat_delta = radius_km / 110.574
    # 위도가 높을수록 경도 1도의 실거리가 짧아진다. cos(lat)이 0에 가까우면 전 경도를 허용한다.
    cos_lat = math.cos(math.radians(lat))
    lng_delta = 180.0 if abs(cos_lat) < 1e-6 else radius_km / (111.320 * abs(cos_lat))
    return (
        max(-90.0, lat - lat_delta),
        min(90.0, lat + lat_delta),
        max(-180.0, lng - lng_delta),
        min(180.0, lng + lng_delta),
    )


def detour_seconds_via(
    truck_lat: float,
    truck_lng: float,
    pickup_lat: float,
    pickup_lng: float,
    dest_lat: float,
    dest_lng: float,
    avg_speed_kmh: float,
) -> int:
    """Routes API를 쓸 수 없을 때의 우회시간 추정(초).

    (현재위치 -> 상차지 -> 목적지) 거리에서 (현재위치 -> 목적지) 직선거리를 뺀 값을
    평균속도로 나눈다. 실제 도로망을 반영하지 않으므로 결과에 route_source를 남겨
    이 값이 추정치임을 드러낸다.
    """
    direct = haversine_km(truck_lat, truck_lng, dest_lat, dest_lng)
    via = haversine_km(truck_lat, truck_lng, pickup_lat, pickup_lng) + haversine_km(
        pickup_lat, pickup_lng, dest_lat, dest_lng
    )
    extra_km = max(0.0, via - direct)
    return int(round(extra_km / max(1e-6, avg_speed_kmh) * 3600))
