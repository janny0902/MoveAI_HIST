"""화주사 체적 측정기가 내보내는 운송장 CSV의 컬럼 계약.

실제 파일(`ai 학습 체적2.csv`)의 컬럼은 17개이고 순서가 고정돼 있다.

    A 운송장번호      B 박스타입     C 박스 가로    D 박스 세로    E 박스 높이
    F 상위좌측X       G 상위좌측Y    H 상위우측X    I 상위우측Y
    J 하위좌측X좌표   K 하위좌측Y    L 하위우측X    M 추론하위우측Y
    N 출발작업터미널  O 상품코드     P 상품명       Q 생성일시
    R 도착작업터미널(선택 — 파일에 없으면 적재 시 배정)

    301636574396,C,610.0000,317.0000,317.0000,720.0,57.9,1636.5,323.2,
    616.1,543.8,1496.0,782.1,001,Box,박스,2026-08-04 08:57:29

이 포맷을 읽을 때 반드시 알아야 하는 것 여섯:

1. **헤더 행이 없다.** 첫 줄부터 데이터다. 헤더가 있다고 가정하면 첫 운송장이 통째로
   사라진다. 컬럼 순서로 매핑한다(cargo_ingest.parse_csv가 판별).
2. **체적 컬럼이 없다.** 가로·세로·높이(mm)에서 계산한다. mm³ / 1e9 = m³(CBM).
3. **중량 컬럼이 없다.** 매칭의 적재중량 제약에 필요하므로 상품코드별 밀도로 추정하고,
   문서에 weight_source="ESTIMATED"를 남긴다. 실측이 아님을 결과까지 끌고 간다.
4. **좌표 컬럼이 없다.** 위치 단서는 출발작업터미널 코드뿐이다. terminals 컬렉션에 등록된
   터미널만 좌표로 풀 수 있고, 미등록 터미널의 행은 사유를 남기고 버린다.
   도착작업터미널은 측정기가 알지 못하므로 파일에 없으면 적재 시점에 배정한다.
5. **미측정 행이 섞여 있다.** 박스타입 NULL · 치수 전부 0 · 상품코드 no_pic(사진 없음)
   또는 Multi(복합화물). 데이터 손상이 아니라 측정기가 값을 못 낸 것이라 따로 센다.
6. **운송장번호가 유일하다는 보장이 없다.** 한 운송장에 박스가 여러 개면 행도 여러 개다.
   운송장 단위로 합산해야 체적이 맞는다(합산은 유일한 파일에서는 무해한 no-op).
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import config

# 한국 표준시. zoneinfo를 쓰지 않는 이유는 slim 이미지에 tzdata가 없을 수 있어서다.
# KST는 서머타임이 없으므로 고정 오프셋으로 충분하다.
KST = timezone(timedelta(hours=9))

# 정규화된 헤더 이름 -> 내부 필드명. 순서가 곧 컬럼 순서(A~Q)다.
COLUMN_ORDER: Tuple[Tuple[str, str], ...] = (
    ("운송장번호", "waybill_no"),
    ("박스타입", "box_type"),
    ("박스가로", "box_width_mm"),
    ("박스세로", "box_depth_mm"),
    ("박스높이", "box_height_mm"),
    ("상위좌측X", "tl_x"),
    ("상위좌측Y", "tl_y"),
    ("상위우측X", "tr_x"),
    ("상위우측Y", "tr_y"),
    ("하위좌측X", "bl_x"),
    ("하위좌측Y", "bl_y"),
    ("하위우측X", "br_x"),
    ("하위우측Y", "br_y"),
    ("출발작업터미널", "origin_terminal_code"),
    ("상품코드", "product_code"),
    ("상품명", "product_name"),
    ("생성일시", "source_created_at"),
)

# 18번째 컬럼(선택). 측정기 파일에는 없다 — 측정기는 상차지만 안다. 파일에 있으면 쓰고,
# 없으면 적재 시점에 등록 터미널 중에서 배정한다(cargo_ingest.assign_destination).
# 필수로 만들지 않는 이유: 기존 17컬럼 파일이 그대로 통과해야 한다.
OPTIONAL_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("도착작업터미널", "destination_terminal_code"),
)

# 예전 파일·폼이 쓰던 이름. '작업터미널'은 출발지를 뜻했으므로 그쪽으로 붙인다.
LEGACY_HEADERS: Dict[str, str] = {
    "작업터미널": "origin_terminal_code",
    "terminal_code": "origin_terminal_code",
}

HEADER_TO_FIELD: Dict[str, str] = {
    **{k: v for k, v in COLUMN_ORDER},
    **{k: v for k, v in OPTIONAL_COLUMNS},
    **LEGACY_HEADERS,
}
FIELD_NAMES = frozenset(
    [v for _, v in COLUMN_ORDER] + [v for _, v in OPTIONAL_COLUMNS]
)
EXPECTED_COLUMN_COUNT = len(COLUMN_ORDER)
# 도착터미널까지 실린 파일. 위치 매핑에서 이 길이도 받아준다.
EXTENDED_COLUMN_COUNT = len(COLUMN_ORDER) + len(OPTIONAL_COLUMNS)

# 치수 3종. 순서가 곧 가로·세로·높이다.
DIM_FIELDS = ("box_width_mm", "box_depth_mm", "box_height_mm")

# 이 넷이 없으면 그 행으로는 아무것도 못 만든다.
REQUIRED_FIELDS = ("waybill_no",) + DIM_FIELDS

# 8자리 코너 좌표. 체적 산출 근거라 감사용으로만 보관한다(기본은 저장 안 함).
CORNER_FIELDS = ("tl_x", "tl_y", "tr_x", "tr_y", "bl_x", "bl_y", "br_x", "br_y")

# 측정 실패 행의 사유. 손상된 행과 구분해서 세려고 상수로 둔다 — 실제 파일에서 치수가
# 전부 0인 행은 상품코드가 no_pic(사진 없음)이나 Multi(복합화물)다. 파일이 잘못된 게
# 아니라 그 운송장을 측정하지 못한 것이므로, 오류 목록을 이걸로 채우지 않는다.
UNMEASURED = "미측정 — 치수가 모두 0 (상품코드 no_pic/Multi)"

_WS = re.compile(r"\s+")
_SCIENTIFIC = re.compile(r"^\d+(\.\d+)?[eE][+-]?\d+$")


def normalize_header(raw: str) -> str:
    """헤더 표기 흔들림을 흡수한다.

    "박스 가로"의 공백, "하위좌측X좌표"의 접미사, "추론하위우측Y"의 접두사가 파일마다
    붙었다 떨어졌다 한다. 컬럼 뜻은 같으므로 셋 다 지우고 비교한다.
    """
    h = _WS.sub("", (raw or "").strip())
    h = h.lstrip("﻿")
    if h.startswith("추론"):
        h = h[2:]
    if h.endswith("좌표"):
        h = h[:-2]
    return h


def detect(fieldnames: Sequence[str]) -> bool:
    """이 파일이 운송장 체적 포맷인가.

    운송장번호와 박스 치수가 함께 있으면 이 포맷으로 본다. 영문 필드명(cargo_id,
    volume_cbm...)으로 된 자체 포맷과 구분하기 위한 판정이다.
    """
    normalized = {normalize_header(f) for f in fieldnames or ()}
    return "운송장번호" in normalized and "박스가로" in normalized


def map_row(row: dict, positional: bool = False) -> dict:
    """원본 행의 키를 내부 필드명으로 바꾼다.

    positional=True면 헤더 이름을 믿지 않고 **순서**로 매핑한다. 실제 측정기 CSV에는
    헤더 행이 아예 없으므로 이쪽이 기본 경로다. 컬럼 수가 17일 때만 쓴다.

    이름 매핑은 한글 헤더와 내부 필드명을 모두 받는다. 웹 폼(POST /v1/waybills)이
    내부 필드명으로 JSON을 보내는데, 그 경로가 파일 적재와 **같은 파서**를 타야
    두 경로의 결과 문서가 갈라지지 않는다.
    """
    if positional:
        values = list(row.values())
        order = COLUMN_ORDER + OPTIONAL_COLUMNS
        return {field: values[i] for i, (_, field) in enumerate(order) if i < len(values)}

    mapped: dict = {}
    for key, value in row.items():
        field = HEADER_TO_FIELD.get(normalize_header(key))
        if field is None and key in FIELD_NAMES:
            field = key
        if field is None:
            continue
        # 같은 필드에 두 이름이 들어올 수 있다 — 폼이 origin_terminal_code와 옛
        # terminal_code를 함께 보내는 경우다. 빈 값이 채워진 값을 덮으면 출발지가
        # 통째로 사라지므로, 이미 값이 있으면 빈 값으로는 덮지 않는다.
        if field in mapped and (value is None or str(value).strip() == ""):
            continue
        mapped[field] = value
    return mapped


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_waybill_no(value) -> Tuple[Optional[str], Optional[str]]:
    """운송장번호를 문자열로. 지수 표기는 값이 이미 깨진 것이라 거부한다.

    운송장번호는 11자리 숫자다. Excel에서 '일반' 서식으로 저장하면 3.01637E+11로
    바뀌어 뒤 자리가 사라진다. 이걸 그대로 받으면 서로 다른 운송장이 한 문서로
    합쳐지므로, 조용히 넘기지 않고 행을 버리며 사유를 알려 준다.
    """
    text = str(value if value is not None else "").strip()
    if not text:
        return None, "운송장번호 없음"
    if _SCIENTIFIC.match(text):
        return None, f"운송장번호가 지수 표기({text})입니다 — 엑셀에서 텍스트 서식으로 저장하세요"
    if text.endswith(".0"):  # csv로 내릴 때 붙는 소수점 꼬리
        text = text[:-2]
    return text, None


def normalize_terminal_code(value) -> str:
    """작업터미널 코드. '001'의 앞자리 0이 살아 있는 형태를 정본으로 삼는다."""
    text = str(value if value is not None else "").strip()
    if not text:
        return ""
    if text.endswith(".0"):
        text = text[:-2]
    # 숫자만이면 3자리로 맞춘다. 엑셀이 001을 1로 바꿔 놓는 일이 잦다.
    return text.zfill(3) if text.isdigit() and len(text) < 3 else text


def parse_source_datetime(value) -> Optional[datetime]:
    """생성일시. 타임존이 없는 '2026-08-04 08:57:29' 형태이고 실제 의미는 KST다.

    UTC로 읽으면 9시간 밀린다. 마감시각 계산에 그대로 반영되므로 조용히 틀리면 안 된다.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=KST)
    text = str(value).strip().replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=KST)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)


def parse_box(row: dict, positional: bool = False) -> Tuple[Optional[dict], Optional[str]]:
    """행 하나 = 박스 하나. (박스, 오류사유)를 돌려준다."""
    mapped = map_row(row, positional=positional)

    waybill_no, reason = _to_waybill_no(mapped.get("waybill_no"))
    if waybill_no is None:
        return None, reason

    raw_dims = [_to_float(mapped.get(f)) for f in DIM_FIELDS]

    # 미측정 행. 실제 파일에서 치수가 셋 다 정확히 0인 행은 박스타입이 NULL이고
    # 상품코드가 no_pic(사진 없음)/Multi(복합화물)다. 손상이 아니라 측정 자체가
    # 안 된 것이라, 오류로 세면 정상 파일이 불량으로 보인다. 따로 분류한다.
    if all(v == 0 for v in raw_dims):
        return None, UNMEASURED

    dims = {}
    for field, v in zip(DIM_FIELDS, raw_dims):
        if v is None or v <= 0:
            return None, f"{field} 없음/0 이하"
        if v > config.MAX_BOX_DIM_MM:
            return None, f"{field}={v}mm — 허용 한계 {config.MAX_BOX_DIM_MM}mm 초과"
        dims[field] = v

    # mm³ -> m³. 측정기가 주는 값은 외곽 치수라 그대로 체적(CBM)이 된다.
    volume_cbm = dims["box_width_mm"] * dims["box_depth_mm"] * dims["box_height_mm"] / 1e9
    if volume_cbm > config.MAX_BOX_CBM:
        return None, f"박스 체적 {volume_cbm:.3f}CBM — 허용 한계 {config.MAX_BOX_CBM}CBM 초과"

    box = {
        "waybill_no": waybill_no,
        "volume_cbm": volume_cbm,
        "box_type": str(mapped.get("box_type") or "").strip() or None,
        "origin_terminal_code": normalize_terminal_code(mapped.get("origin_terminal_code")),
        # 파일에 없으면 빈 문자열. 적재 단계에서 배정한다.
        "destination_terminal_code": normalize_terminal_code(
            mapped.get("destination_terminal_code")
        ),
        "product_code": str(mapped.get("product_code") or "").strip() or None,
        "product_name": str(mapped.get("product_name") or "").strip() or None,
        "source_created_at": parse_source_datetime(mapped.get("source_created_at")),
        **{k: round(v, 1) for k, v in dims.items()},
    }

    # 실제 파일은 세로와 높이가 **모든 행에서** 같다(317/317, 331/331, 360/360...).
    # 측정기가 2D 쿼드에서 두 변만 내고 세 번째 축을 복제했을 가능성이 있고, 그렇다면
    # 체적이 전부 틀린다. 계산은 컬럼이 말하는 대로 하되(추측으로 값을 바꾸지 않는다),
    # 몇 행이 그런지 세어 적재 로그에 올린다. 화주사가 확인해야 할 항목이다.
    box["_depth_eq_height"] = dims["box_depth_mm"] == dims["box_height_mm"]

    if config.INGEST_KEEP_CORNERS:
        corners = {f: _to_float(mapped.get(f)) for f in CORNER_FIELDS}
        if any(v is not None for v in corners.values()):
            box["corners"] = corners

    return box, None


def estimate_weight_kg(
    volume_cbm: float, product_code: Optional[str], box_type: Optional[str] = None
) -> Tuple[float, str]:
    """박스 하나의 추정 중량과 그 근거를 돌려준다. 반환값은 (kg, 근거).

    원본에 중량 컬럼이 없는데 적재중량 제약(4.2)은 중량을 요구한다.

    1순위는 **박스타입**이다. 규격박스는 크기별로 담기는 무게가 대체로 정해져 있어,
    부피×밀도보다 실제에 가깝다. 특히 부피가 큰데 가벼운 화물(폴리백, 완충재 채운 박스)에서
    밀도 추정은 크게 빗나간다.

    타입이 없거나 표에 없으면 상품코드별 평균 밀도로 떨어진다. 어느 쪽이든 추정이므로
    문서에 weight_source="ESTIMATED"와 근거(weight_basis)를 함께 남긴다.
    """
    key = (box_type or "").strip().upper()
    weight = config.CARGO_WEIGHT_BY_BOX_TYPE.get(key)
    if weight is not None:
        return float(weight), "BOX_TYPE"

    density_key = (product_code or "").strip().upper()
    density = config.CARGO_DENSITY_BY_PRODUCT.get(density_key, config.CARGO_DENSITY_DEFAULT)
    return volume_cbm * density, "DENSITY"


def freight_krw(box_type: Optional[str]) -> float:
    """박스 하나의 운임. 한진택배 규격 요금(세변의 합 기준)에 타입을 대응시킨 표다.

    원본에 운임 컬럼이 없는데, 운임이 0이면 솔버가 소포를 절대 고르지 않는다 -
    우회 비용을 상쇄할 항이 없기 때문이다. 공표 요금 수준의 근사치이지 계약 단가가
    아니므로, 화주사 정산표를 받으면 CARGO_FREIGHT_BY_BOX_TYPE을 교체해야 한다.
    """
    key = (box_type or "").strip().upper()
    return float(config.CARGO_FREIGHT_BY_BOX_TYPE.get(key, config.CARGO_FREIGHT_DEFAULT))


def aggregate(boxes: List[dict]) -> Dict[str, dict]:
    """박스 행들을 운송장 단위로 합친다.

    합산하지 않으면 같은 운송장의 마지막 박스만 남아(문서 ID가 같다) 체적이 실제보다
    작게 들어간다. 운송장 하나가 곧 매칭 후보 하나이므로 합계가 맞아야 한다.

    한 운송장의 박스가 서로 다른 파일에 나뉘어 있으면 이 함수로는 합쳐지지 않는다.
    파일을 나눌 때는 운송장 단위로 끊어야 한다(docs/05 참조).
    """
    groups: Dict[str, dict] = {}
    for box in boxes:
        no = box["waybill_no"]
        g = groups.get(no)
        if g is None:
            g = groups[no] = {
                "waybill_no": no,
                "volume_cbm": 0.0,
                # 중량은 박스마다 따로 잡아 더한다. 한 운송장에 타입이 섞이면
                # (A 하나 + C 하나) 합계 부피로 한 번에 계산하는 것과 값이 달라진다.
                "weight_kg": 0.0,
                "weight_bases": set(),
                # 운임도 박스 단위다. 타입이 섞이면 박스마다 등급이 다르다.
                "freight_krw": 0.0,
                "box_count": 0,
                "box_types": set(),
                "origin_terminal_codes": set(),
                "destination_terminal_codes": set(),
                "product_codes": set(),
                "product_names": set(),
                "source_created_at": None,
                "boxes": [],
            }
        g["volume_cbm"] += box["volume_cbm"]
        weight, basis = estimate_weight_kg(
            box["volume_cbm"], box.get("product_code"), box.get("box_type")
        )
        g["weight_kg"] += weight
        g["weight_bases"].add(basis)
        g["freight_krw"] += freight_krw(box.get("box_type"))
        g["box_count"] += 1
        for key, target in (
            ("box_type", "box_types"),
            ("origin_terminal_code", "origin_terminal_codes"),
            ("destination_terminal_code", "destination_terminal_codes"),
            ("product_code", "product_codes"),
            ("product_name", "product_names"),
        ):
            if box.get(key):
                g[target].add(box[key])
        created = box.get("source_created_at")
        if created and (g["source_created_at"] is None or created > g["source_created_at"]):
            # 여러 박스가 다른 시각에 측정됐으면 마지막 측정이 그 운송장의 준비 시점이다.
            g["source_created_at"] = created
        if config.INGEST_KEEP_BOX_DETAIL:
            g["boxes"].append(
                {k: box[k] for k in ("box_type", "box_width_mm", "box_depth_mm", "box_height_mm", "volume_cbm")
                 if k in box}
            )
    return groups
