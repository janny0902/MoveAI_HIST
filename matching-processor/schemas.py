from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class QualityStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    LIMITED = "LIMITED"
    REJECTED = "REJECTED"


class ModelVersions(BaseModel):
    detector: str
    depth: str
    geometry: str


class SpaceGeometryReadyEvent(BaseModel):
    """2.2 통신 계약. vision-processor/schemas.py와 동일 스키마를 수신 측에서 다시 정의한다.
    1.3: Matching은 이 필드들만 볼 수 있고 원본 이미지/depth map/point cloud에 접근하지 않는다."""

    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(default="space-geometry.v3", alias="schema")
    event_id: str
    truck_id: str
    photo_id: str
    captured_at: str
    estimated_free_cbm: float
    usable_free_cbm: float
    unknown_cbm: float
    quality_score: float
    quality_status: QualityStatus
    model_versions: Optional[ModelVersions] = None


class TruckState(BaseModel):
    """4.2 + 경로 정보. 위치/목적지가 없으면 M2 경로 회랑을 만들 수 없어 can_load=false로 끝난다."""

    truck_id: str
    max_payload_kg: float
    # 적재함 총 체적. 사진 없이 매칭할 때 잔여 체적의 출발점이 된다 —
    # 빈 차 기준이면 이 값이 그대로 실을 수 있는 공간이다.
    cargo_capacity_cbm: Optional[float] = None
    # 적재함 치수. 파렛트를 몇 장 깔 수 있는지는 부피가 아니라 바닥 크기가 정한다.
    cargo_width_m: Optional[float] = None
    cargo_length_m: Optional[float] = None
    cargo_height_m: Optional[float] = None
    current_loaded_weight_kg: Optional[float] = None
    reserved_added_weight_kg: float = 0.0
    current_lat: Optional[float] = None
    current_lng: Optional[float] = None
    destination_lat: Optional[float] = None
    destination_lng: Optional[float] = None


class Cargo(BaseModel):
    cargo_id: str
    volume_cbm: float
    weight_kg: float
    pickup_lat: float
    pickup_lng: float
    delivery_lat: Optional[float] = None
    delivery_lng: Optional[float] = None
    revenue_krw: float = 0.0
    freight_krw: float = 0.0
    # "DECLARED"(화주사 신고) 또는 "ESTIMATED"(체적 x 밀도 추정). 운송장 체적 파일에는
    # 중량 컬럼이 없어 추정으로 채운다.
    weight_source: str = "DECLARED"
    # 박스 구성. 그룹 카드가 박스타입별 건수를 세는 근거다.
    box_types: List[str] = []
    box_count: int = 1
    # 어디로 받으러 가야 하는지. 결과 화면이 상차 계획을 그리는 데 쓴다.
    pickup_address: Optional[str] = None
    # 출발/도착 작업터미널. 결과를 이 쌍으로 묶어 보여주므로 둘 다 화물에 실어 나른다.
    origin_terminal_code: Optional[str] = None
    origin_terminal_name: Optional[str] = None
    destination_terminal_code: Optional[str] = None
    destination_terminal_name: Optional[str] = None
    # Firestore에 timestampValue로 들어 있어 클라이언트가 datetime을 돌려준다.
    # ISO 문자열로 들어오는 경우도 있어 pydantic이 양쪽을 모두 파싱하도록 datetime으로 둔다.
    ready_at: Optional[datetime] = None
    deadline_at: Optional[datetime] = None
    # M4 결과가 채워진다.
    detour_seconds: Optional[int] = None


class CargoRegistration(BaseModel):
    """화주사가 등록하는 운송장 한 건.

    체적과 중량이 매칭 판정의 근거이므로 필수다(설계서 4.2 표: 없으면 해당 후보 제외).
    상차 좌표가 있어야 M2 경로 회랑에 들어온다.
    """

    cargo_id: str
    volume_cbm: float
    weight_kg: float
    pickup_lat: float
    pickup_lng: float
    pickup_address: Optional[str] = None
    delivery_lat: Optional[float] = None
    delivery_lng: Optional[float] = None
    delivery_address: Optional[str] = None
    revenue_krw: Optional[float] = None
    cargo_type: Optional[str] = None
    shipper_id: Optional[str] = None
    ready_at: Optional[datetime] = None
    deadline_at: Optional[datetime] = None
    status: str = "WAITING"


class CargoBatch(BaseModel):
    cargos: List[CargoRegistration]


class WaybillBox(BaseModel):
    """운송장 체적 파일의 한 행 = 박스 하나.

    필드 구성이 17컬럼 CSV와 일부러 같다. 웹 폼과 파일 적재가 같은 파서를 타야
    두 경로의 결과 문서가 갈라지지 않기 때문이다(cargo_ingest.ingest_waybill_rows).
    체적·중량·좌표는 여기 없다 — 원본에 없는 값이라 서버가 치수·상품코드·터미널에서
    만들어낸다. 클라이언트가 계산해 보내면 그 규칙이 두 곳에 생긴다.
    """

    waybill_no: str
    box_type: Optional[str] = None
    box_width_mm: float = Field(gt=0, description="가로(mm)")
    box_depth_mm: float = Field(gt=0, description="세로(mm)")
    box_height_mm: float = Field(gt=0, description="높이(mm)")
    # 옛 폼이 보내던 terminal_code도 출발지로 받는다. 두 이름이 같이 오면 명시적인
    # origin_terminal_code가 이긴다.
    origin_terminal_code: Optional[str] = None
    terminal_code: Optional[str] = None
    # 비우면 서버가 등록 터미널 중에서 배정한다. 측정기 CSV에 없는 값이라 필수로 두면
    # 파일 적재 경로와 폼 경로의 요구사항이 갈라진다.
    destination_terminal_code: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    # 없으면 서버가 수신 시각(KST)을 쓴다. 상차 마감은 여기에 WAYBILL_VALID_HOURS를 더한 값이다.
    source_created_at: Optional[datetime] = None


class WaybillBatch(BaseModel):
    """박스 여러 개. 같은 운송장번호가 여러 행이면 서버가 합산한다."""

    boxes: List[WaybillBox]


class TerminalRegistration(BaseModel):
    """작업터미널 코드 -> 좌표.

    운송장 체적 파일에는 좌표가 없고 작업터미널 코드만 있다. 이 표가 없으면 그 파일의
    행은 전부 상차지를 못 정해 버려진다. 파일 적재의 선행 데이터다.
    """

    terminal_code: str
    lat: float
    lng: float
    name: Optional[str] = None
    address: Optional[str] = None


class PickupStop(BaseModel):
    """상차지 한 곳. 기사가 실제로 움직이는 단위다.

    화물 목록만 주면 "이걸 어디서 받지?"에 답할 수 없다. 같은 터미널의 운송장 20건은
    한 번 들르는 일이므로, 지점 단위로 묶어 들이는 시간과 버는 돈을 함께 보여준다.
    """

    terminal_code: Optional[str] = None
    terminal_name: Optional[str] = None
    address: Optional[str] = None
    lat: float
    lng: float
    cargo_count: int
    volume_cbm: float
    weight_kg: float
    revenue_krw: float
    freight_krw: float = 0.0
    # 이 지점에 들르느라 늘어나는 주행 시간. 목적지까지 직행 대비 증가분이다.
    detour_seconds: Optional[int] = None


class SelectedCargo(BaseModel):
    cargo_id: str
    volume_cbm: float
    weight_kg: float
    pickup_order: int
    revenue_krw: float = 0.0
    freight_krw: float = 0.0
    # 상차지(=출발 작업터미널). 이름은 옛것을 유지한다 — 결과 화면이 "어디서 받는지"로
    # 읽는 필드라 origin_으로 바꾸면 계약만 흔들리고 뜻은 그대로다.
    terminal_code: Optional[str] = None
    terminal_name: Optional[str] = None
    # 도착 작업터미널. 결과를 출발-도착 쌍으로 묶는 그룹 키의 나머지 절반이다.
    destination_terminal_code: Optional[str] = None
    destination_terminal_name: Optional[str] = None
    box_types: List[str] = []
    box_count: int = 1
    pickup_address: Optional[str] = None
    # 상차지 좌표. 그룹을 "내 위치에서 가까운 순"으로 정렬하는 근거다.
    pickup_lat: Optional[float] = None
    pickup_lng: Optional[float] = None
    # 파일 적재분은 중량이 추정치다(원본에 중량 컬럼이 없다). 실측과 섞지 않기 위해
    # 결과까지 표시를 끌고 온다 — 설계서 5.8의 "추정을 실측으로 제시하지 않는다".
    weight_source: str = "DECLARED"


class TerminalGroup(BaseModel):
    """출발-도착 작업터미널 한 쌍으로 묶은 추가 상차분.

    기사가 판단하는 단위는 운송장 한 건이 아니라 '어느 터미널에서 실어 어디로 내리는
    묶음'이다. 200건을 낱개로 늘어놓으면 어디를 들러야 하는지 읽히지 않는다.
    박스타입별 건수를 함께 주는 이유는 규격이 곧 부피·운임 등급이라, 같은 10건이어도
    A 10건과 E 10건이 전혀 다른 일이기 때문이다.
    """

    origin_terminal_code: Optional[str] = None
    origin_terminal_name: Optional[str] = None
    destination_terminal_code: Optional[str] = None
    destination_terminal_name: Optional[str] = None
    # 상차지 좌표. 화면이 "내 위치에서 가까운 순"으로 정렬하는 데 쓴다. 좌표를 안 주면
    # 화면이 터미널 목록을 따로 받아 코드로 이어 붙여야 하고, 그 사이에 둘이 어긋난다.
    origin_lat: Optional[float] = None
    origin_lng: Optional[float] = None
    pickup_address: Optional[str] = None
    # 운송장 건수. 박스 개수(box_count 합)와 다르다 — 한 운송장에 박스가 여럿일 수 있다.
    cargo_count: int = 0
    box_count: int = 0
    # {"A": 3, "C": 12} 형태. 정렬은 건수 내림차순으로 서버가 정한다.
    box_type_counts: dict = {}
    volume_cbm: float = 0.0
    weight_kg: float = 0.0
    revenue_krw: float = 0.0
    freight_krw: float = 0.0


class MatchingResult(BaseModel):
    """5.3 API 결과 계약."""

    truck_id: str
    photo_id: str
    estimated_free_cbm: float
    usable_free_cbm: float
    unknown_cbm: float
    remaining_weight_kg: Optional[float]
    can_load: bool
    selected_cargos: List[SelectedCargo] = []
    # 출발-도착 터미널 쌍으로 묶은 같은 내용. 낱건 목록으로는 어디를 들러야 하는지
    # 읽히지 않아서, 화면이 기본으로 보여주는 단위를 서버가 만들어 준다.
    terminal_groups: List[TerminalGroup] = []
    # 상차 계획. 어디에 들러 무엇을 받고 얼마를 버는지.
    pickup_stops: List[PickupStop] = []
    # 이번 상차로 늘어나는 운임 합계와, 그러느라 늘어나는 주행 시간 합계.
    # 둘을 나란히 줘야 기사가 "갈 만한가"를 스스로 판단할 수 있다.
    added_revenue_krw: float = 0.0
    added_detour_seconds: int = 0
    # 그중 플랫폼 몫(운임 x 수수료율). 화면이 1%를 하드코딩하지 않도록 비율도 함께 준다.
    # 기사가 받는 수수료 합계와, 그 근거가 되는 운임 합계.
    added_commission_krw: float = 0.0
    added_freight_krw: float = 0.0
    # 수익 계산 내역. "왜 이익이 나는가"를 화면이 그대로 풀어 쓸 수 있게 항을 다 준다.
    # 상차지 고정비(우회 + 품질 위험)는 건수와 무관하게 붙으므로 물량이 손익을 가른다.
    # breakeven_cargo_count가 그 분기점이다.
    fill_reward_krw: float = 0.0
    detour_cost_krw: float = 0.0
    risk_cost_krw: float = 0.0
    net_gain_krw: float = 0.0
    breakeven_cargo_count: Optional[int] = None
    final_free_cbm: float
    quality_score: float
    decision_scope: str = "CBM_WEIGHT_ROUTE_FEASIBILITY"
    # 5.6 최소 MLOps: 판정 근거를 남긴다.
    quality_status: QualityStatus
    solver_status: str
    candidate_count: int = 0
    # 이번 계산에 쓴 후보 상한과 허용 최대치. 화면이 선택지를 그릴 때 쓴다 —
    # 상한을 프론트에 하드코딩하면 서버가 바뀔 때 둘이 어긋난다.
    candidate_limit: Optional[int] = None
    candidate_limit_max: Optional[int] = None
    # 파렛트 적재로 계산했는지, 몇 장이 깔리는지, 그래서 얼마를 잃었는지.
    # "왜 용량이 줄었나"에 답할 수 있어야 관리자가 이 숫자를 믿는다.
    pallet_mode: bool = False
    pallet_count: Optional[int] = None
    pallet_spec: Optional[str] = None
    raw_capacity_cbm: Optional[float] = None
    pallet_loss_cbm: Optional[float] = None
    route_source: str = "NONE"
    failure_reason: Optional[str] = None
