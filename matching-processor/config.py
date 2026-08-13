import json
import os


def _json_env(name: str, default: dict) -> dict:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return default
    return parsed if isinstance(parsed, dict) else default


PROJECT_ID = os.getenv("GCP_PROJECT", "moveai-504903")
LOCATION = os.getenv("GCP_LOCATION", "asia-northeast3")

TRUCKS_COLLECTION = os.getenv("FIRESTORE_TRUCKS_COLLECTION", "trucks")
CARGOS_COLLECTION = os.getenv("FIRESTORE_CARGOS_COLLECTION", "pending_cargos")
RESULTS_COLLECTION = os.getenv("FIRESTORE_MATCHING_RESULTS_COLLECTION", "matching_results")
# 5.8: Pub/Sub 중복 수신을 event_id로 걸러내기 위한 처리 기록.
PROCESSED_EVENTS_COLLECTION = os.getenv("FIRESTORE_PROCESSED_EVENTS_COLLECTION", "processed_events")

# M3: 1차 필터 후 솔버로 넘길 후보 수.
#
# 설계서 5.4는 Top 10-20을 말하는데, 그 근거는 후보마다 길찾기를 부르는 비용이었다.
# 지금은 **상차지 단위로 묶어** 호출하므로(routes_client.compute_detours) 호출 수가
# 후보 수가 아니라 지점 수에 비례한다. 같은 터미널의 운송장 200건도 호출 2번이다.
#
# 20으로 두면 매칭이 막힌다. 수수료가 운임의 1%면 소포 한 건은 75원인데 상차지
# 고정비(우회 + 품질 위험)는 만 원대라, 70건 이상 실어야 이익이 난다. 후보가 20건이면
# 공간이 아무리 남아도 손익분기를 넘을 수 없다.
MAX_ROUTE_CANDIDATES = int(os.getenv("MAX_ROUTE_CANDIDATES", "200"))
# 길찾기를 부를 상차지 수 상한. 호출은 2N+1회다. 이게 진짜 비용 축이라
# 후보 수가 아니라 여기를 조인다 - 지점 89곳까지 늘렸다가 카카오 rate limit에 걸려
# 매칭이 통째로 실패했다(routes_api_failed).
MAX_ROUTE_STOPS = int(os.getenv("MAX_ROUTE_STOPS", "12"))
# M2: 경로 회랑 반경(km). 이 박스를 벗어난 상차지는 Firestore 쿼리 단계에서 제외한다.
CORRIDOR_RADIUS_KM = float(os.getenv("CORRIDOR_RADIUS_KM", "30"))
# M2 쿼리 상한. pending_cargos가 10만 건 규모라 무제한 조회를 허용하지 않는다.
# 차량 기준 매칭에서는 이 값이 **기본값**이고, 화면이 요청으로 바꿀 수 있다.
MAX_CANDIDATE_FETCH = int(os.getenv("MAX_CANDIDATE_FETCH", "500"))
# 화면이 올릴 수 있는 상한. 여기까지만 허용한다 — 후보를 무제한으로 늘리면 Firestore
# 읽기 비용과 솔버 시간이 같이 늘어나고, 요청 하나가 컨테이너를 오래 붙잡는다.
CANDIDATE_FETCH_MAX = int(os.getenv("CANDIDATE_FETCH_MAX", "100000"))
# 이 수를 넘으면 CP-SAT를 아예 시도하지 않고 그리디로 간다. **0이면 제한 없음** —
# 후보가 몇 건이든 최적화를 돌린다.
#
# 기본을 0으로 두는 이유: 이 화면의 결과는 "AI가 고른 조합"이어야 한다. 규칙 기반으로
# 떨어지면 결과는 유효해도 최적해가 아니고, 화면도 그렇게 밝혀야 한다. 시간이 더
# 걸리더라도 최적화를 먼저 돌린다. 그리디는 솔버가 실제로 실패했을 때만 쓰는
# 안전망이지, 미리 포기하는 경로가 아니다.
SOLVER_MAX_CANDIDATES = int(os.getenv("SOLVER_MAX_CANDIDATES", "0"))

# ---------------------------------------------------------------------------
# 파렛트 적재
# ---------------------------------------------------------------------------
# 현장에서 자주 나는 계산 착오가 "화물만 재고 파렛트를 빼먹는 것"이다. 파렛트에 실으면
# 바닥 높이(깔판 두께)만큼 적재 높이가 줄고, 파렛트 규격이 적재함 치수로 나누어떨어지지
# 않아 남는 폭이 통째로 죽는다. 둘을 넣지 않으면 실제보다 CBM이 크게 잡혀,
# 다 실린다고 계산해 놓고 현장에서 남는다.
#
# T-11(1100x1100mm)은 국내 표준 파렛트다. 깔판 높이 144mm.
PALLET_WIDTH_M = float(os.getenv("PALLET_WIDTH_M", "1.1"))
PALLET_LENGTH_M = float(os.getenv("PALLET_LENGTH_M", "1.1"))
PALLET_BASE_HEIGHT_M = float(os.getenv("PALLET_BASE_HEIGHT_M", "0.144"))
# 파렛트 위에 쌓은 소포 사이의 빈틈. 규격이 제각각인 소포는 파렛트를 꽉 채우지 못한다.
# 0.85 = 파렛트 위 공간의 85%만 화물이 차지한다고 본다.
PALLET_STACK_EFFICIENCY = float(os.getenv("PALLET_STACK_EFFICIENCY", "0.85"))
# 회랑 박스를 위도 밴드로 쪼개 조회한다. 복합색인이 pickup_lat 순이라 박스 전체에 limit을
# 걸면 남쪽 가장자리만 뽑혀 반경 필터에서 전멸한다. 밴드마다 limit을 나눠 고르게 뽑는다.
CORRIDOR_LAT_BANDS = int(os.getenv("CORRIDOR_LAT_BANDS", "5"))

# 운송장 적재. 잘못된 행이 많아도 응답이 비대해지지 않도록 보고 개수를 제한한다.
INGEST_MAX_REPORTED_ERRORS = int(os.getenv("INGEST_MAX_REPORTED_ERRORS", "20"))
# 벌크 API 한 번에 받을 수 있는 건수. Firestore 일괄 쓰기 상한과 맞춘다.
INGEST_MAX_BATCH = int(os.getenv("INGEST_MAX_BATCH", "500"))
# 파일 적재용 버킷. 사진 버킷과 분리한다 — matching은 사진 버킷에 접근 권한이 없다(1.3).
CARGO_INGEST_BUCKET = os.getenv("CARGO_INGEST_BUCKET", f"cargo-ingest-{PROJECT_ID}")
# 한 파일에서 처리할 최대 행 수. 이보다 크면 파일을 나눠 올린다.
#
# 운송장 단위로 합산하려면 파일 전체를 메모리에 올려야 하고, Eventarc가 부르는
# Cloud Run 요청은 TIMEOUT(120s) 안에 끝나야 한다. 인스턴스가 1Gi/1CPU라 5만 행이
# 메모리(약 150MB)와 시간(병렬 커밋으로 10초 내외) 양쪽에서 안전한 상한이다.
# 수백만 건은 이 크기로 잘라 올린다 — 파일마다 Cloud Run 인스턴스가 따로 붙어 병렬로 처리된다.
INGEST_MAX_ROWS_PER_FILE = int(os.getenv("INGEST_MAX_ROWS_PER_FILE", "50000"))
# Firestore 일괄 쓰기를 동시에 몇 개 던질지. 순차로 하면 5만 행에 100번 왕복이라 느리다.
INGEST_MAX_PARALLEL_BATCHES = int(os.getenv("INGEST_MAX_PARALLEL_BATCHES", "4"))

# ---------------------------------------------------------------------------
# 운송장 체적 포맷 (17컬럼 CSV). 컬럼 정의는 waybill_schema를 보라.
# ---------------------------------------------------------------------------
# 박스 치수 sanity. 측정기 오류로 들어온 값이 체적을 오염시키지 않게 한다.
MAX_BOX_DIM_MM = float(os.getenv("MAX_BOX_DIM_MM", "5000"))
MAX_BOX_CBM = float(os.getenv("MAX_BOX_CBM", "30"))

# 원본에 중량 컬럼이 없다. **박스타입**으로 추정하는 것이 1순위다.
#
# 실제 파일의 타입별 치수를 한진택배 규격박스에 크기순으로 대응시킨 표다.
#
#   타입  파일상 대표 부피   대응 규격   대표 중량
#   S     약  12 L          2호         2.0 kg
#   A     약  30 L          4호         5.0 kg
#   B     약  50 L          5호         8.0 kg
#   C     약  80 L          5~6호      12.0 kg
#   D     약 150 L          6호        18.0 kg
#   E     약 250 L          6호 초과   25.0 kg
#
# **이 무게는 실측이 아니다.** 규격박스 크기에 통상적인 택배 중량을 얹어 잡은 값이고,
# 화주사의 실제 타입별 평균 중량표를 받으면 통째로 교체해야 한다. 그래서 문서에는
# weight_source="ESTIMATED"와 weight_basis="BOX_TYPE"이 함께 붙는다.
CARGO_WEIGHT_BY_BOX_TYPE = _json_env(
    "CARGO_WEIGHT_BY_BOX_TYPE",
    {"S": 2.0, "A": 5.0, "B": 8.0, "C": 12.0, "D": 18.0, "E": 25.0},
)

# 박스타입이 없거나 표에 없는 값이면 상품코드별 평균 밀도(kg/CBM)로 떨어진다.
CARGO_DENSITY_DEFAULT = float(os.getenv("CARGO_DENSITY_DEFAULT", "150"))
CARGO_DENSITY_BY_PRODUCT = _json_env(
    "CARGO_DENSITY_BY_PRODUCT",
    {"BOX": 150.0, "POLY": 80.0, "VINYL": 80.0, "SACK": 300.0},
)

# 박스타입별 운임(원). 원본 파일에 운임 컬럼이 없다.
#
# 한진택배 규격 요금은 **세변의 합**으로 등급이 갈린다. 실제 파일의 타입별 세변 합을
# 재서 등급에 대응시켰다.
#
#   타입  세변 합(실측 평균)   등급     운임
#   S     약  70cm            소형     5,000
#   A     약  95cm            중형     6,000
#   B     약 110cm            대형     7,500
#   C     약 130cm            특대형   9,000
#   D     약 160cm            특대형  11,000
#   E     약 190cm            초대형  13,000
#
# **공표 요금 수준의 근사치이지 계약 단가가 아니다.** 기업 계약가는 통상 이보다 낮고,
# 화주사 정산표를 받으면 교체해야 한다. 이 값이 매칭 결과를 직접 좌우한다.
CARGO_FREIGHT_BY_BOX_TYPE = _json_env(
    "CARGO_FREIGHT_BY_BOX_TYPE",
    {"S": 5000.0, "A": 6000.0, "B": 7500.0, "C": 9000.0, "D": 11000.0, "E": 13000.0},
)
CARGO_FREIGHT_DEFAULT = float(os.getenv("CARGO_FREIGHT_DEFAULT", "6000"))

# 기사 수수료. **기사는 운임이 아니라 수수료로 먹고 산다** — 건당 얼마씩 받으므로
# 물량이 늘면 수입이 그대로 늘어난다. 운행 중 추가 상차가 의미 있는 이유가 이것이다.
#
# 택배사 평균 수수료(건당). 택배 기사 수수료는 실제로 **건당 정액**이고 박스 크기와
# 거의 무관하다. 업계에서 통용되는 범위가 700~900원이라 그 평균을 기본값으로 둔다.
#
# 비율제로 계산해 봤다가 되돌린 이력을 남긴다. 운임의 1%는 건당 75원이라 정액 800원의
# 1/11 수준이고, 상차지 고정비(우회 + 품질 위험 1만 원대)를 넘으려면 70건 이상이
# 필요했다. 비율제 계약이면 DRIVER_FEE_RATE를 올리면 되고(실제 수수료율은 운임의
# 15~20% 수준이다), 둘 다 설정하면 큰 쪽을 쓴다.
DRIVER_FEE_PER_BOX_KRW = float(os.getenv("DRIVER_FEE_PER_BOX_KRW", "800"))
DRIVER_FEE_RATE = float(os.getenv("DRIVER_FEE_RATE", "0"))

# 원본에 마감시각이 없다. 생성일시 + 이 시간을 상차 마감으로 본다.
# deadline_at은 TTL 필드이기도 해서(infra/config.sh) 만료분은 Firestore가 지운다.
WAYBILL_VALID_HOURS = float(os.getenv("WAYBILL_VALID_HOURS", "72"))

# 이미 마감이 지난 운송장을 저장할지. 기본은 저장하지 않는다.
#
# 저장해 봐야 M3의 시간창 필터가 후보에서 빼고 Firestore TTL이 곧 지운다. 그런데
# written=306처럼 성공한 것처럼 보여서, 정작 "이 파일은 너무 오래됐다"는 사실이 묻힌다.
# 건너뛰고 already_expired로 따로 세면 written=0이 그대로 경고가 된다.
INGEST_SKIP_EXPIRED = os.getenv("INGEST_SKIP_EXPIRED", "true").lower() == "true"

# 코너 좌표 8개와 박스별 명세를 문서에 남길지. 기본은 끈다 — 수백만 문서에서
# Firestore는 모든 필드에 단일 필드 색인을 자동 생성해 쓰기 비용과 저장량이 늘어난다.
INGEST_KEEP_CORNERS = os.getenv("INGEST_KEEP_CORNERS", "false").lower() == "true"
INGEST_KEEP_BOX_DETAIL = os.getenv("INGEST_KEEP_BOX_DETAIL", "false").lower() == "true"

# 작업터미널 코드 -> 좌표. 이게 없으면 운송장 파일에서 상차지를 만들 수 없다.
TERMINALS_COLLECTION = os.getenv("FIRESTORE_TERMINALS_COLLECTION", "terminals")
TERMINAL_CACHE_TTL_S = float(os.getenv("TERMINAL_CACHE_TTL_S", "300"))
# 컬렉션 대신 환경변수로 넣는 경로. Firestore보다 우선한다.
# 예: {"001": {"name": "서울터미널", "lat": 37.5, "lng": 127.0}}
TERMINAL_COORDS_JSON = os.getenv("TERMINAL_COORDS_JSON", "")

# 5.2 목적함수 가중치. CP-SAT는 정수만 쓰므로 CBM->liter, 시간->초, 중량->kg로 변환한다.
# 목적함수 항은 전부 **원** 단위다. 서로 자릿수가 맞아야 의미가 있다.
#
# 원래 값(적재보상 20원/L, 우회 30원/초, 위험 50,000원)은 한 건이 1~2CBM인 대형 화물
# 기준이었다. 택배 소포는 건당 0.05CBM이라 그 값들로는 어떤 조합도 이득이 되지 않는다.
# 실제로 후보 20건이 전부 조건에 맞는데 0건이 선택됐다.
#
# 기사 수입의 본체는 건당 수수료이므로 적재보상은 보조 항으로 낮췄다. 우회 비용은
# 택배 기사의 시간당 기회비용(약 3만원 = 8원/초)에 맞췄다 — 30원/초는 시간당
# 108,000원이라 소포 경제에 맞지 않는다.
FILL_REWARD_PER_LITER = int(os.getenv("FILL_REWARD_PER_LITER", "2"))
DETOUR_PENALTY_PER_SECOND = int(os.getenv("DETOUR_PENALTY_PER_SECOND", "8"))
# 4.10: LIMITED 품질에서 추가로 물리는 위험 패널티(원 단위).
# 위 항들과 같은 축척으로 내렸다. 50,000원은 소포 수십 건의 수수료를 통째로 덮는다.
GEOMETRY_RISK_PENALTY_LIMITED = int(os.getenv("GEOMETRY_RISK_PENALTY_LIMITED", "5000"))

# 5.2/5.4: 탐색시간 1초 고정, FEASIBLE 허용.
SOLVER_TIME_LIMIT_S = float(os.getenv("SOLVER_TIME_LIMIT_S", "1.0"))

# 4.10: LIMITED 구간에 적용하는 추가 안전계수.
LIMITED_EXTRA_SAFETY_FACTOR = float(os.getenv("LIMITED_EXTRA_SAFETY_FACTOR", "0.80"))

# 5.2 경로/시간 제약
MAX_DETOUR_SECONDS = int(os.getenv("MAX_DETOUR_SECONDS", "3600"))

# M4: 카카오모빌리티 길찾기. 키가 없으면 직선거리 추정으로 degrade하고 결과에 출처를 남긴다.
# vision-processor의 주소 검색과 같은 REST 키를 쓴다. 다만 카카오 Local API와
# 카카오모빌리티 길찾기는 콘솔이 달라, 앱에서 두 서비스를 각각 활성화해야 한다.
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")
ROUTES_API_TIMEOUT_S = float(os.getenv("ROUTES_API_TIMEOUT_S", "10"))
# 후보 N개에 2N+1번 호출하므로 병렬로 던진다. 너무 올리면 카카오 쪽 rate limit에 걸린다.
ROUTES_MAX_PARALLEL = int(os.getenv("ROUTES_MAX_PARALLEL", "8"))
# 직선거리 -> 주행시간 환산에 쓰는 평균 속도(km/h). Routes API 미사용 시에만 쓰인다.
FALLBACK_AVG_SPEED_KMH = float(os.getenv("FALLBACK_AVG_SPEED_KMH", "45"))
