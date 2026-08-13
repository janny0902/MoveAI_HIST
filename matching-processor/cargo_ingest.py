"""운송장(대기 화물) 적재.

경로는 셋이고 전부 이 모듈의 write_docs()로 모인다.
  1) 웹 폼      POST /v1/cargos          건당. 시스템 없는 소규모 화주, 수동 보정
  2) 벌크 API   POST /v1/cargos:batch    화주사 WMS/TMS 연동. 호출당 500건
  3) 파일 적재  GCS에 CSV/JSONL 업로드   주 경로. 수십만~수백만 건

입력 포맷은 둘이다.

  * **운송장 체적 포맷** — 화주사 체적 측정기가 내보내는 17컬럼 CSV. 파일 적재의 실제
    포맷이다. 컬럼 정의와 그 한계는 waybill_schema를 보라. 체적/중량/좌표 컬럼이 없어
    각각 치수 계산 · 밀도 추정 · 터미널 대응표로 채운다.
  * **자체 포맷** — cargo_id/volume_cbm/... 영문 필드명. 웹 폼과 벌크 API가 쓴다.
    이미 좌표와 중량을 갖고 있으므로 변환이 필요 없다.

포맷은 헤더를 보고 자동 판별한다. 화주사에 "우리 필드명으로 바꿔서 올려라"를 요구하지
않기 위해서다.
"""
import csv
import hashlib
import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, NamedTuple, Optional, Sequence, Tuple

from google.cloud import firestore

import config
import terminals
import waybill_schema

logger = logging.getLogger("matching-processor")

# Firestore 일괄 쓰기 상한.
BATCH_LIMIT = 500

# 자체 포맷의 필수 필드. 하나라도 없으면 그 행만 버리고 나머지는 적재한다.
REQUIRED = ("cargo_id", "volume_cbm", "weight_kg", "pickup_lat", "pickup_lng")


def assign_destination(waybill_no: str, origin_code: str, db) -> Optional[dict]:
    """도착작업터미널을 배정한다. 좌표가 등록된 터미널 중 출발지가 아닌 곳.

    체적 측정기 파일에는 도착지가 없다. 측정기는 상차 터미널에 놓여 있어 "어디서 실리는가"만
    안다. 그런데 운송장을 출발-도착 쌍으로 묶어 보여주려면 도착지가 있어야 하므로 여기서
    채운다.

    난수 대신 **운송장번호 해시**로 고른다. random을 쓰면 같은 파일을 다시 적재할 때마다
    도착지가 바뀌어, 화면을 새로 고칠 때마다 그룹이 뒤섞인다. 해시는 재적재해도 같은
    운송장이 같은 도착지로 간다.
    """
    pool = [t for t in terminals.list_all(db) if t["terminal_code"] != origin_code]
    if not pool:
        return None
    digest = hashlib.sha1(str(waybill_no).encode("utf-8")).digest()
    return pool[int.from_bytes(digest[:8], "big") % len(pool)]


class Table(NamedTuple):
    """헤더 순서를 유지한 표. 순서를 잃으면 위치 기반 매핑을 할 수 없다."""

    fieldnames: List[str]
    rows: List[dict]


def document_id(cargo_id: str) -> str:
    """문서 ID를 cargo_id의 해시로 만든다.

    운송장 번호는 대개 순차(30493263xx, 30493264xx...)인데, Firestore는 문서 ID가
    순차면 색인 범위 한 곳에 쓰기가 몰려 핫스팟이 생긴다. 대량 적재가 초당 수백 건에서
    막힌다. 해시를 쓰면 키가 고르게 흩어져 이 병목이 사라진다.

    무작위 UUID가 아니라 해시인 이유는 **같은 운송장을 다시 올려도 같은 문서**가 되게
    하기 위해서다. 재업로드가 중복을 만들지 않는다(멱등).
    """
    return hashlib.sha1(cargo_id.encode("utf-8")).hexdigest()[:20]


# ---------------------------------------------------------------------------
# 파싱
# ---------------------------------------------------------------------------

# 헤더 없는 파일에 붙이는 자리표시 컬럼명. 값이 아니라 **순서**가 의미를 갖는다.
POSITIONAL_FIELDNAMES = [f"col{i:02d}" for i in range(waybill_schema.EXPECTED_COLUMN_COUNT)]


def _is_headerless_waybill(cells: List[str]) -> bool:
    """첫 줄이 헤더가 아니라 데이터인가.

    실제 측정기 CSV에는 헤더 행이 없다(첫 줄이 곧 첫 운송장). DictReader에 그냥 넘기면
    두 가지가 조용히 깨진다.
      1. 첫 운송장이 헤더로 먹혀 사라진다.
      2. 세로와 높이 값이 같아서(317.0000이 두 번) 컬럼 이름이 중복되고, DictReader가
         그 키를 하나로 합쳐 이후 모든 행의 컬럼이 밀린다.
    둘 다 예외 없이 틀린 값을 만들므로 여기서 먼저 걸러야 한다.
    """
    if len(cells) != waybill_schema.EXPECTED_COLUMN_COUNT:
        return False
    first = (cells[0] or "").strip().lstrip("﻿")
    # 운송장번호는 12자리 숫자다. 어떤 헤더 이름도 이 모양이 될 수 없다.
    return first.isdigit() and len(first) >= 8


def _unique_headers(cells: List[str]) -> List[str]:
    """중복 헤더에 꼬리를 붙여 유일하게 만든다. 겹치면 뒤 컬럼이 앞을 덮어쓴다."""
    seen: dict = {}
    out: List[str] = []
    for i, raw in enumerate(cells):
        name = (raw or "").strip().lstrip("﻿") or f"col{i:02d}"
        if name in seen:
            seen[name] += 1
            name = f"{name}__{seen[name]}"
        else:
            seen[name] = 0
        out.append(name)
    return out


def parse_csv(text: str) -> Table:
    records = [r for r in csv.reader(io.StringIO(text)) if any((c or "").strip() for c in r)]
    if not records:
        return Table([], [])

    if _is_headerless_waybill(records[0]):
        fieldnames, data = list(POSITIONAL_FIELDNAMES), records
    else:
        fieldnames, data = _unique_headers(records[0]), records[1:]

    # dict가 삽입 순서를 지키므로 위치 기반 매핑이 그대로 성립한다. 짧은 행은 뒤쪽
    # 필드가 비고, 긴 행은 잘린다 — 어느 쪽이든 그 행만 사유와 함께 걸러진다.
    rows = [dict(zip(fieldnames, r)) for r in data]
    return Table(fieldnames, rows)


def parse_jsonl(text: str) -> Table:
    """한 줄에 JSON 하나. 대용량에서 CSV보다 타입이 명확하다."""
    rows: List[dict] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("JSONL %d행 파싱 실패", line_no)
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return Table(list(rows[0].keys()) if rows else [], rows)


def parse_by_name(name: str, text: str) -> Table:
    lowered = name.lower()
    if lowered.endswith((".jsonl", ".ndjson")):
        return parse_jsonl(text)
    if lowered.endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return Table([], [])
        rows = [r for r in (data if isinstance(data, list) else [data]) if isinstance(r, dict)]
        return Table(list(rows[0].keys()) if rows else [], rows)
    return parse_csv(text)


# ---------------------------------------------------------------------------
# 자체 포맷 (웹 폼 / 벌크 API)
# ---------------------------------------------------------------------------

def _to_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_timestamp(value) -> Optional[datetime]:
    """ISO 8601 문자열을 tz-aware datetime으로. Firestore가 timestamp로 저장한다."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def normalize(row: dict) -> Tuple[Optional[dict], Optional[str]]:
    """자체 포맷 한 건을 Firestore 문서로. 반환값은 (문서, 오류사유)."""
    cargo_id = str(row.get("cargo_id") or "").strip()
    if not cargo_id:
        return None, "cargo_id 없음"

    doc = {
        "cargo_id": cargo_id,
        "volume_cbm": _to_float(row.get("volume_cbm")),
        "weight_kg": _to_float(row.get("weight_kg")),
        "pickup_lat": _to_float(row.get("pickup_lat")),
        "pickup_lng": _to_float(row.get("pickup_lng")),
    }
    missing = [f for f in REQUIRED if doc.get(f) is None]
    if missing:
        return None, f"필수 필드 없음: {', '.join(missing)}"

    if doc["volume_cbm"] <= 0 or doc["weight_kg"] <= 0:
        return None, "volume_cbm/weight_kg는 0보다 커야 한다"
    if not (-90 <= doc["pickup_lat"] <= 90) or not (-180 <= doc["pickup_lng"] <= 180):
        return None, "pickup 좌표 범위를 벗어남"

    # 이 경로의 중량은 화주사가 직접 넣은 값이다. 파일 적재의 추정치와 구분한다.
    doc["weight_source"] = "DECLARED"

    for key in ("delivery_lat", "delivery_lng", "revenue_krw"):
        v = _to_float(row.get(key))
        if v is not None:
            doc[key] = v
    for key in ("pickup_address", "delivery_address", "cargo_type", "shipper_id"):
        v = row.get(key)
        if v:
            doc[key] = str(v).strip()
    for key in ("ready_at", "deadline_at"):
        v = _to_timestamp(row.get(key))
        if v is not None:
            doc[key] = v

    # M2가 status == "WAITING"만 조회한다.
    doc["status"] = str(row.get("status") or "WAITING").strip().upper()
    doc["registered_at"] = firestore.SERVER_TIMESTAMP
    return doc, None


# ---------------------------------------------------------------------------
# 운송장 체적 포맷 (파일 적재 주 경로)
# ---------------------------------------------------------------------------

def _uses_positional(fieldnames: Sequence[str]) -> bool:
    """이름으로 매핑할 수 없는 표인가 = 컬럼 순서로 읽어야 하는가.

    헤더 없는 CSV(col00, col01...)는 이름이 아무 뜻도 없으니 순서로 읽는다. 한글 헤더가
    붙은 파일이나 내부 필드명으로 오는 JSON은 이름으로 읽는다 — JSON은 키 순서를
    보장하지 않으므로 순서로 읽으면 안 된다.
    """
    return not any(
        waybill_schema.HEADER_TO_FIELD.get(waybill_schema.normalize_header(f))
        or f in waybill_schema.FIELD_NAMES
        for f in fieldnames or ()
    )


def _waybill_docs(table: Table, db: firestore.Client, source: Optional[str]) -> Tuple[List[dict], List[dict], dict]:
    """17컬럼 운송장 표를 Firestore 문서로. (문서들, 오류들, 통계).

    파일 적재와 웹 폼 단건 등록이 **이 함수 하나**를 공유한다. 갈라 두면 체적 계산이나
    중량 추정이 두 경로에서 달라지고, 그 차이는 조용히 데이터에 남는다.
    """
    errors: List[dict] = []
    stats = {
        "boxes": 0,
        "box_rows_failed": 0,
        "waybills_failed": 0,
        "unmeasured": 0,
        "depth_eq_height": 0,
        "expired": 0,
        "unknown_terminals": set(),
    }

    positional = _uses_positional(table.fieldnames)

    # 실패는 두 층에서 난다. 박스 행 하나가 깨진 것과, 운송장 전체가 상차지를 못 정한
    # 것은 규모가 다르다(후자는 박스 여러 개가 함께 빠진다). 따로 센다.
    def note(bucket: str, index, ident, reason):
        stats[bucket] += 1
        if len(errors) < config.INGEST_MAX_REPORTED_ERRORS:
            errors.append({"index": index, "cargo_id": ident, "reason": reason})

    boxes: List[dict] = []
    for index, row in enumerate(table.rows):
        box, reason = waybill_schema.parse_box(row, positional=positional)
        if box is None:
            # 미측정은 파일 결함이 아니다. 오류 목록에 넣으면 20건 예산을 다 먹고
            # 진짜 문제가 안 보인다. 개수만 센다.
            if reason == waybill_schema.UNMEASURED:
                stats["unmeasured"] += 1
            else:
                note("box_rows_failed", index, None, reason)
            continue
        if box.pop("_depth_eq_height", False):
            stats["depth_eq_height"] += 1
        boxes.append(box)
        stats["boxes"] += 1

    groups = waybill_schema.aggregate(boxes)
    now = datetime.now(timezone.utc)
    valid = timedelta(hours=config.WAYBILL_VALID_HOURS)

    docs: List[dict] = []
    for waybill_no, g in groups.items():
        # 한 운송장의 박스가 서로 다른 터미널에 흩어져 있으면 상차지를 하나로 정할 수
        # 없다. 임의로 고르면 엉뚱한 곳으로 배차되므로 버린다.
        codes = sorted(c for c in g["origin_terminal_codes"] if c)
        if len(codes) != 1:
            note("waybills_failed", None, waybill_no,
                 "출발작업터미널 없음" if not codes else f"한 운송장에 터미널이 여러 개: {', '.join(codes)}")
            continue

        code = codes[0]
        terminal = terminals.resolve(code, db)
        if terminal is None:
            stats["unknown_terminals"].add(code)
            note("waybills_failed", None, waybill_no,
                 f"출발작업터미널 {code} 좌표 미등록 — POST /v1/terminals로 등록하세요")
            continue

        # 도착터미널. 화물이 어디로 가는지는 화주사만 아는 사실이라 지어내지 않는다.
        #
        # 다만 체적 측정기 파일에는 이 컬럼이 자체가 없다(측정기는 상차 터미널에 놓여
        # 있어 "어디서 실리는가"만 안다). 그 경로까지 막으면 기존 파일이 전부 거부되므로
        # 배정으로 채우되, destination_source=ASSIGNED로 표시해 신고값과 구분한다.
        # 신고값이 있는 문서만 도착지를 사실로 취급할 수 있다.
        dest_codes = sorted(c for c in g["destination_terminal_codes"] if c)
        dest = terminals.resolve(dest_codes[0], db) if dest_codes else None
        dest_source = "DECLARED"
        if dest is None:
            if dest_codes:
                # 코드는 왔는데 좌표가 없다. 조용히 다른 곳으로 바꾸면 안 된다.
                stats["unknown_terminals"].add(dest_codes[0])
                note("waybills_failed", None, waybill_no,
                     f"도착작업터미널 {dest_codes[0]} 좌표 미등록 — POST /v1/terminals로 등록하세요")
                continue
            dest = assign_destination(waybill_no, code, db)
            dest_source = "ASSIGNED"
        if dest is None:
            note("waybills_failed", None, waybill_no,
                 "도착작업터미널을 정할 수 없다 — 파일에 도착터미널 컬럼을 넣거나 터미널을 2곳 이상 등록하세요")
            continue

        volume_cbm = round(g["volume_cbm"], 6)
        product_code = sorted(g["product_codes"])[0] if g["product_codes"] else None
        # 중량은 박스별로 잡아 이미 더해져 있다. 합계 부피로 한 번에 계산하면 타입이
        # 섞인 운송장에서 값이 달라진다.
        weight_kg = g["weight_kg"]
        weight_basis = "+".join(sorted(g["weight_bases"])) or "DENSITY"
        # 기사 수수료: 건당 정액과 운임 비율 중 큰 쪽. 계약 형태가 둘 다 있다.
        driver_fee = round(max(
            g["box_count"] * config.DRIVER_FEE_PER_BOX_KRW,
            g["freight_krw"] * config.DRIVER_FEE_RATE,
        ))

        created = g["source_created_at"]
        ready_at = created or now
        deadline_at = ready_at + valid
        if deadline_at <= now:
            stats["expired"] += 1
            if config.INGEST_SKIP_EXPIRED:
                # 저장해도 시간창 필터에서 빠지고 TTL이 곧 지운다. 저장하지 않으면
                # written=0이 "이 파일은 이미 마감이 지났다"는 신호가 된다.
                continue

        doc = {
            "cargo_id": waybill_no,
            "volume_cbm": volume_cbm,
            "weight_kg": round(weight_kg, 2),
            # 실측이 아니라 추정이다. 이 표시를 결과까지 끌고 가서 실측과 섞지 않는다.
            "weight_source": "ESTIMATED",
            # 무엇을 근거로 추정했는지. BOX_TYPE(규격박스 대표중량)이 1순위,
            # DENSITY(상품코드별 밀도)가 대체 경로다. 섞이면 "BOX_TYPE+DENSITY".
            "weight_basis": weight_basis,
            "pickup_lat": terminal["lat"],
            "pickup_lng": terminal["lng"],
            "pickup_address": terminal.get("address") or terminal.get("name"),
            "origin_terminal_code": code,
            "origin_terminal_name": terminal.get("name"),
            # 도착지. 좌표까지 같이 둔다 — 그룹 카드에 지도를 붙이거나 배송거리를 재려면
            # 코드만으로는 매번 terminals를 다시 조회해야 한다.
            "destination_terminal_code": dest["terminal_code"],
            "destination_terminal_name": dest.get("name"),
            # DECLARED(화주사가 지정) / ASSIGNED(측정기 파일에 없어 서버가 채움).
            # 추정을 실측처럼 제시하지 않는다는 원칙을 도착지에도 적용한다.
            "destination_source": dest_source,
            "delivery_lat": dest["lat"],
            "delivery_lng": dest["lng"],
            "delivery_address": dest.get("address") or dest.get("name"),
            # 운임(한진 규격 요금 근사)과 그중 기사 몫(수수료).

            "freight_krw": round(g["freight_krw"]),
            "commission_krw": driver_fee,
            # 솔버는 **기사 수수료**로 최적화한다. 기사는 운임이 아니라 수수료를 받고,
            # 물량이 늘면 수입이 그대로 늘어난다. 운행 중 추가 상차의 근거가 이것이다.
            "revenue_krw": driver_fee,
            "revenue_source": "DRIVER_FEE",
            "box_count": g["box_count"],
            "box_types": sorted(g["box_types"]),
            "product_code": product_code,
            "product_name": sorted(g["product_names"])[0] if g["product_names"] else None,
            "ready_at": ready_at,
            # TTL 필드다(infra/config.sh CARGO_TTL_FIELD=deadline_at). 만료된 운송장은
            # Firestore가 알아서 지운다 — 수백만 건이 무한정 쌓이지 않게 하는 장치다.
            "deadline_at": deadline_at,
            "status": "WAITING",
            "registered_at": firestore.SERVER_TIMESTAMP,
            "ingest_format": "WAYBILL_VOLUME_V1",
        }
        if source:
            doc["ingest_source"] = source
        if config.INGEST_KEEP_BOX_DETAIL and g["boxes"]:
            doc["boxes"] = g["boxes"]
        docs.append(doc)

    stats["unknown_terminals"] = sorted(stats["unknown_terminals"])
    return docs, errors, stats


# ---------------------------------------------------------------------------
# 쓰기
# ---------------------------------------------------------------------------

def write_docs(docs: List[dict], db: firestore.Client) -> int:
    """500건씩 묶어 병렬로 커밋한다.

    순차로 커밋하면 5만 건에 100번 왕복이라 Eventarc 요청 타임아웃(120s)에 닿는다.
    묶음끼리는 서로 독립이므로(문서 ID가 모두 다르다) 병렬로 던져도 안전하다.
    """
    collection = db.collection(config.CARGOS_COLLECTION)
    chunks = [docs[i:i + BATCH_LIMIT] for i in range(0, len(docs), BATCH_LIMIT)]
    if not chunks:
        return 0

    def commit(chunk: List[dict]) -> int:
        batch = db.batch()
        for doc in chunk:
            batch.set(collection.document(document_id(doc["cargo_id"])), doc)
        batch.commit()
        return len(chunk)

    if len(chunks) == 1:
        return commit(chunks[0])

    with ThreadPoolExecutor(max_workers=config.INGEST_MAX_PARALLEL_BATCHES) as pool:
        return sum(pool.map(commit, chunks))


def write_cargos(rows: Iterable[dict], db: firestore.Client) -> dict:
    """자체 포맷 행들을 적재한다. 웹 폼과 벌크 API가 쓴다."""
    docs: List[dict] = []
    errors: List[dict] = []
    for index, row in enumerate(rows):
        doc, reason = normalize(row)
        if doc is None:
            if len(errors) < config.INGEST_MAX_REPORTED_ERRORS:
                errors.append({"index": index, "cargo_id": row.get("cargo_id"), "reason": reason})
            continue
        docs.append(doc)
    written = write_docs(docs, db)
    return {"written": written, "failed": len(errors), "errors": errors, "format": "NATIVE"}


def ingest_waybill_table(table: Table, db: firestore.Client, source: Optional[str] = None) -> dict:
    """운송장 체적 표를 적재하고 무슨 일이 있었는지 돌려준다."""
    docs, errors, stats = _waybill_docs(table, db, source)
    written = write_docs(docs, db)
    return {
        "written": written,
        "failed": stats["box_rows_failed"] + stats["waybills_failed"],
        "errors": errors,
        "format": "WAYBILL_VOLUME_V1",
        "box_rows": stats["boxes"],
        "box_rows_failed": stats["box_rows_failed"],
        "waybills_failed": stats["waybills_failed"],
        "waybills": len(docs),
        "unmeasured_rows": stats["unmeasured"],
        "depth_eq_height_rows": stats["depth_eq_height"],
        "already_expired": stats["expired"],
        "unknown_terminals": stats["unknown_terminals"],
    }


def ingest_waybill_rows(rows: List[dict], db: firestore.Client, source: Optional[str] = None) -> dict:
    """내부 필드명으로 들어온 박스 행들을 적재한다. POST /v1/waybills가 쓴다.

    파일 적재와 같은 파서·같은 집계·같은 문서 형태를 쓴다. 웹 폼으로 넣은 운송장과
    파일로 넣은 운송장이 Firestore에서 구분되지 않아야 매칭이 일관된다.
    """
    return ingest_waybill_table(Table(sorted(waybill_schema.FIELD_NAMES), rows), db, source)


def looks_like_waybill(table: Table) -> bool:
    """이 표가 운송장 체적 포맷인가.

    (1) 한글 헤더가 붙어 있거나, (2) 헤더 없이 17컬럼이면 이 포맷으로 본다.
    자체 포맷(cargo_id/volume_cbm/...)과 헷갈리지 않게 cargo_id가 있으면 제외한다.
    """
    if waybill_schema.detect(table.fieldnames):
        return True
    return (
        len(table.fieldnames) == waybill_schema.EXPECTED_COLUMN_COUNT
        and "cargo_id" not in table.fieldnames
    )


def ingest_table(table: Table, db: firestore.Client, source: Optional[str] = None) -> dict:
    """파일 한 개를 적재한다. 포맷은 컬럼 구성으로 판별한다.

    한 행이 잘못됐다고 파일 전체를 버리지 않는다. 수십만 건 중 몇 건이 깨졌다고
    전부 실패시키면 화주사가 원인을 찾기 어렵다.
    """
    if len(table.rows) > config.INGEST_MAX_ROWS_PER_FILE:
        raise ValueError(
            f"{len(table.rows)}행 — 한 파일 한계 {config.INGEST_MAX_ROWS_PER_FILE}행을 넘었습니다. "
            "운송장 단위로 끊어 나눠 올리세요."
        )

    if looks_like_waybill(table):
        return ingest_waybill_table(table, db, source)

    return write_cargos(table.rows, db)
