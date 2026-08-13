"""작업터미널 코드 -> 좌표 레지스트리.

운송장 체적 파일에는 좌표가 없다. 위치 단서는 작업터미널 코드('001', '200') 하나뿐이고,
M2 경로 회랑은 상차 좌표 없이는 후보를 고를 수 없다. 그래서 코드->좌표 대응표가
파이프라인의 필수 선행 데이터가 된다.

등록되지 않은 터미널의 행은 **버린다**. 임의로 서울시청 같은 좌표를 채워 넣으면 매칭이
그럴듯한 거짓 결과를 내놓는다. 설계서 5.8의 fail-closed 원칙과 같은 이유다.
"""
import json
import logging
import threading
import time
from typing import Dict, List, Optional

from google.cloud import firestore

import config

logger = logging.getLogger("matching-processor")

_lock = threading.Lock()
_cache: Optional[Dict[str, dict]] = None
_cache_at = 0.0


def _from_env() -> Dict[str, dict]:
    """TERMINAL_COORDS_JSON 환경변수로 넣은 대응표.

    Firestore보다 우선한다. 터미널이 몇 개뿐이거나 신규 프로젝트를 부트스트랩할 때
    컬렉션 없이 바로 돌리기 위한 경로다.
    형식: {"001": {"name": "서울터미널", "lat": 37.5, "lng": 127.0}}
    """
    raw = config.TERMINAL_COORDS_JSON
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("TERMINAL_COORDS_JSON 파싱 실패 — 무시한다")
        return {}
    out: Dict[str, dict] = {}
    for code, v in (data or {}).items():
        entry = _clean(code, v)
        if entry:
            out[entry["terminal_code"]] = entry
    return out


def _clean(code: str, v: dict) -> Optional[dict]:
    from waybill_schema import normalize_terminal_code

    try:
        lat = float(v["lat"])
        lng = float(v["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return None
    return {
        "terminal_code": normalize_terminal_code(code),
        "name": (v.get("name") or "").strip() or None,
        "address": (v.get("address") or "").strip() or None,
        "lat": lat,
        "lng": lng,
    }


def _load(db: firestore.Client) -> Dict[str, dict]:
    registry = dict(_from_env())
    try:
        for doc in db.collection(config.TERMINALS_COLLECTION).stream():
            entry = _clean(doc.id, doc.to_dict() or {})
            if entry and entry["terminal_code"] not in registry:
                registry[entry["terminal_code"]] = entry
    except Exception:
        # 컬렉션이 없거나 권한이 없으면 환경변수 표만으로 간다. 적재 자체를 막지는 않되,
        # 미등록 터미널의 행은 어차피 뒤에서 사유와 함께 버려진다.
        logger.exception("terminals 컬렉션 조회 실패 — 환경변수 대응표만 사용한다")
    return registry


def registry(db: firestore.Client) -> Dict[str, dict]:
    """대응표를 돌려준다. TTL 동안 캐시한다 — 적재 한 번에 수십만 번 조회된다."""
    global _cache, _cache_at
    with _lock:
        if _cache is None or (time.time() - _cache_at) > config.TERMINAL_CACHE_TTL_S:
            _cache = _load(db)
            _cache_at = time.time()
            logger.info("터미널 대응표 %d건 적재", len(_cache))
        return _cache


def invalidate() -> None:
    global _cache
    with _lock:
        _cache = None


def resolve(code: str, db: firestore.Client) -> Optional[dict]:
    return registry(db).get(code) if code else None


def upsert(entry: dict, db: firestore.Client) -> dict:
    cleaned = _clean(entry.get("terminal_code", ""), entry)
    if cleaned is None:
        raise ValueError("terminal_code / lat / lng 가 올바르지 않습니다")
    db.collection(config.TERMINALS_COLLECTION).document(cleaned["terminal_code"]).set(cleaned)
    invalidate()
    return cleaned


def list_all(db: firestore.Client) -> List[dict]:
    return sorted(registry(db).values(), key=lambda t: t["terminal_code"])
