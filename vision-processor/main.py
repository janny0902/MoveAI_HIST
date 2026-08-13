import base64
import io
import json
import logging
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional, Tuple

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
import firestore_client
import pubsub_publisher
import storage_client
from geometry_lite.camera import estimate_intrinsics
from geometry_lite.pipeline import GEOMETRY_LITE_VERSION, run_geometry_lite
from model_clients.depth_model import get_depth_model
from model_clients.owlvit_client import OwlVitClient
from preprocessing import JPEG_QUALITY, preprocess_image
from schemas import ModelVersions, ProcessPhotoRequest, QualityStatus, SpaceGeometryReadyEvent

app = FastAPI(title="Vision Processor")

# 프론트엔드가 별도 Cloud Run 서비스라(1.3) 브라우저에는 교차 출처가 된다.
# upload-url 발급과 결과 조회를 브라우저가 직접 호출하므로 CORS가 필요하다.
#
# 구분자로 세미콜론을 쓴다. gcloud --set-env-vars가 쉼표로 항목을 나누고, Windows에서는
# 공백이 들어간 인자가 cmd.exe에서 깨지기 때문이다. 편의상 쉼표도 함께 받는다.
def _parse_origins(raw: str):
    return [o.strip() for o in raw.replace(",", ";").split(";") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_origins(os.getenv("CORS_ALLOW_ORIGINS", "*")),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Cloud Run 기본 root logger는 WARNING이라 logger.info()가 전부 삭제된다.
# Eventarc 수신/파이프라인 진행 로그를 Cloud Logging에서 보려면 INFO로 낮춰야 한다.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("vision-processor")
logger.setLevel(logging.INFO)

_owlvit_client: OwlVitClient = None


@app.on_event("startup")
def on_startup():
    """3.2/5.4: 컨테이너 시작 시 Depth 모델을 1회 로드하고 전역 재사용한다."""
    get_depth_model()
    global _owlvit_client
    _owlvit_client = OwlVitClient(
        project=config.PROJECT_ID,
        location=config.LOCATION,
        endpoint_id=config.OWLVIT_ENDPOINT_ID,
        dedicated_dns=config.OWLVIT_DEDICATED_DNS,
    )
    logger.info(
        "OWL-ViT client 준비: enabled=%s endpoint_id=%s",
        _owlvit_client.enabled,
        config.OWLVIT_ENDPOINT_ID or "(미설정)",
    )


class UploadUrlRequest(BaseModel):
    truck_id: str
    content_type: str = "image/jpeg"
    # D1/2.1: PWA가 원본 EXIF에서 읽어 리사이즈 비율만큼 보정한 intrinsic.
    # 리사이즈된 이미지에는 EXIF가 남지 않으므로 여기로 받는다.
    native_intrinsics: Optional[dict] = None
    # D1: 촬영 위치. M2 경로 회랑의 기준점이 된다.
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    # 목적지. 기사가 촬영할 때마다 바꿀 수 있다. 셋 다 없으면 기본 목적지를 쓴다.
    destination_address: Optional[str] = None
    destination_lat: Optional[float] = None
    destination_lng: Optional[float] = None


@app.get("/")
def health_check():
    return {"status": "ok", "service": "vision-processor"}


@app.post("/")
async def eventarc_root(request: Request):
    """Eventarc가 Cloud Run 트리거 배포 시 별도 경로를 지정하지 않으면 기본적으로
    루트 경로(/)에 CloudEvent를 POST한다. GET '/'은 헬스체크 용도로 별도 유지한다.

    Eventarc는 비-2xx 응답을 실패로 간주해 계속 재시도하므로, 페이로드 형태를 예단하지
    않고 dict.get()으로만 필드를 읽는다. 파싱/파이프라인 처리 중 어떤 예외가 나더라도
    무한 재시도를 유발하지 않도록 로그만 남기고 항상 HTTP 200을 반환한다."""
    headers = {k.lower(): v for k, v in request.headers.items()}

    try:
        payload = await request.json()
    except Exception:
        raw = (await request.body()).decode("utf-8", errors="replace")
        # 본문이 비어 있어도 binary content mode 헤더만으로 처리할 수 있으므로 즉시 포기하지 않는다.
        logger.warning("Eventarc payload가 유효한 JSON이 아님 - 수신된 페이로드: %s", raw)
        payload = {}

    try:
        result = _handle_object_finalized_event(payload, headers)
        logger.info("Eventarc 이벤트 처리 완료: %s", result)
    except Exception:
        logger.exception("Eventarc 이벤트 처리 실패 - 수신된 페이로드: %s", payload)

    return {"status": "success"}


@app.post("/v1/photos/upload-url")
def get_upload_url(req: UploadUrlRequest):
    """5.3: PWA는 업로드 전에 photo_id와 Signed URL을 발급받는다.
    photo_id는 idempotency key이므로 이 시점에 확정된다(2.1)."""
    photo_id = f"P-{uuid.uuid4().hex[:8]}"
    blob_name = f"photos/{req.truck_id}/{photo_id}.jpg"
    try:
        url = storage_client.generate_upload_url(blob_name, req.content_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Signed URL 발급 실패: {str(e)}")

    # 리사이즈로 사라질 EXIF 대신 촬영 시점 컨텍스트를 여기서 넘겨받아 보관한다.
    firestore_client.save_photo_context(
        photo_id,
        {
            "truck_id": req.truck_id,
            "native_intrinsics": req.native_intrinsics,
            "requested_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    # D1: 촬영 위치를 트럭 최신 위치로 갱신하고, 목적지를 확정한다.
    # 목적지를 지정하지 않으면 기본 목적지로 설정한다. 비워 두면 M2 경로 회랑을 만들 수 없어
    # Matching이 truck_position_or_destination_unknown으로 끝나기 때문이다.
    if req.destination_lat is not None and req.destination_lng is not None:
        dest = (req.destination_lat, req.destination_lng, req.destination_address or "")
    else:
        dest = (
            config.DEFAULT_DESTINATION_LAT,
            config.DEFAULT_DESTINATION_LNG,
            config.DEFAULT_DESTINATION_ADDRESS,
        )

    try:
        firestore_client.update_truck_location(
            req.truck_id,
            current_lat=req.gps_lat,
            current_lng=req.gps_lng,
            destination_lat=dest[0],
            destination_lng=dest[1],
            destination_address=dest[2],
        )
    except Exception:
        # 위치 갱신 실패로 업로드 자체를 막지는 않는다. Matching이 fail-closed로 처리한다.
        logger.exception("트럭 위치/목적지 갱신 실패: truck_id=%s", req.truck_id)

    return {
        "photo_id": photo_id,
        "upload_url": url,
        "object_uri": f"gs://{config.BUCKET_NAME}/{blob_name}",
    }


def _process_photo(req: ProcessPhotoRequest) -> dict:
    """V1-V6: Vision 파이프라인 전체 실행. Eventarc 핸들러와 데모용 직접 호출
    엔드포인트가 이 함수를 공유한다."""
    t_start = time.perf_counter()
    truck_spec = firestore_client.get_truck_spec(req.truck_id)
    if truck_spec is None:
        # 4.2/표(반드시 사전에 확보할 데이터): W/L/H 없으면 분석 중단
        raise HTTPException(status_code=422, detail="트럭 제원(W/L/H)이 없어 분석을 중단합니다.")

    # V1: GCS 이미지 로드
    jpeg_bytes = storage_client.download_bytes(req.object_uri)

    # V2: 전처리/품질검사
    pre = preprocess_image(jpeg_bytes)
    intrinsics = estimate_intrinsics(
        image_width=pre.image.width,
        image_height=pre.image.height,
        exif=pre.exif,
        native_intrinsics=req.native_intrinsics,
    )

    buf = io.BytesIO()
    pre.image.save(buf, format="JPEG", quality=JPEG_QUALITY)
    resized_bytes = buf.getvalue()

    # V3: OWL-ViT(Vertex Endpoint)와 local Depth를 병렬 실행
    t_model_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as executor:
        depth_future = executor.submit(get_depth_model().predict_metric_depth, pre.image)
        owl_future = executor.submit(_owlvit_client.detect, resized_bytes, pre.image.width, pre.image.height)

        try:
            depth_map = depth_future.result()
        except Exception as exc:
            # 5.8: Depth 실패 -> CBM 계산 불가
            raise HTTPException(status_code=502, detail=f"Depth 추론 실패: {exc}")

        try:
            owl_boxes = owl_future.result()
            logger.info("OWL-ViT 탐지: %d개 박스", len(owl_boxes))
        except Exception:
            # 5.8: OWL-ViT timeout/오류 -> Geometry-only 후보 추출, 품질 감점(owl_coverage_ratio=0).
            # 어떤 실패도 전체 요청을 막지 않고 동일하게 degrade하되, 조용히 넘어가면
            # Endpoint가 죽은 것을 눈치채지 못하므로 반드시 남긴다.
            logger.exception("OWL-ViT 추론 실패 - geometry-only로 degrade한다")
            owl_boxes = []

    model_latency_ms = int((time.perf_counter() - t_model_start) * 1000)

    # V4 + V5: Geometry Lite, CBM/품질 계산
    t_geometry_start = time.perf_counter()
    geometry_result = run_geometry_lite(
        depth_m=depth_map,
        K=intrinsics,
        owl_boxes=owl_boxes,
        truck_width_m=truck_spec.cargo_width_m,
        truck_length_m=truck_spec.cargo_length_m,
        truck_height_m=truck_spec.cargo_height_m,
        blur_score=pre.blur_score,
        exposure_score=pre.exposure_score,
        safety_factor=config.SAFETY_FACTOR,
        voxel_edge_m=config.VOXEL_EDGE_M,
    )

    geometry_latency_ms = int((time.perf_counter() - t_geometry_start) * 1000)

    captured_at = datetime.now(timezone.utc).isoformat()
    model_versions = {
        "detector": config.OWLVIT_DETECTOR_VERSION,
        "depth": config.DEPTH_MODEL_VERSION,
        "geometry": GEOMETRY_LITE_VERSION,
    }

    # V6: 결과 저장(Firestore)
    result_payload = {
        "truck_id": req.truck_id,
        "photo_id": req.photo_id,
        "captured_at": captured_at,
        "estimated_free_cbm": geometry_result.estimated_free_cbm,
        "usable_free_cbm": geometry_result.usable_free_cbm,
        "unknown_cbm": geometry_result.unknown_cbm,
        "quality_score": geometry_result.quality_score,
        "quality_status": geometry_result.quality_status,
        # Matching Pipeline이 remaining_weight_kg를 계산할 때 사용(4.2). Vision은 값만 전달한다.
        "current_loaded_weight_kg": truck_spec.current_loaded_weight_kg,
        "max_payload_kg": truck_spec.max_payload_kg,
        # --- 결과 설명(XAI)용 ---------------------------------------------------
        # 최종 CBM만 주면 사용자는 그 숫자를 검산할 수 없고, 값이 이상해도 어디가
        # 잘못됐는지 짚지 못한다. 분해에 필요한 항을 함께 싣는다.
        # (적재함 전체 = 짐 + 사진에 보인 빈 공간 + 가려진 공간,
        #  사용 가능 = 사진에 보인 빈 공간 x 안전계수)
        # 이벤트(2.2)에는 넣지 않는다 — Matching은 이 값들을 쓰지 않는다.
        "cargo_width_m": truck_spec.cargo_width_m,
        "cargo_length_m": truck_spec.cargo_length_m,
        "cargo_height_m": truck_spec.cargo_height_m,
        "capacity_cbm": round(
            truck_spec.cargo_width_m * truck_spec.cargo_length_m * truck_spec.cargo_height_m, 3
        ),
        "occupied_cbm": geometry_result.occupied_cbm,
        "observed_free_cbm": geometry_result.observed_free_cbm,
        "safety_factor": geometry_result.safety_factor,
        "model_versions": model_versions,
        "failure_reason": geometry_result.failure_reason,
    }

    # V6: GCS 결과 저장. 이벤트에는 이 URI만 남기고 원본/depth map/point cloud는 싣지 않는다(2.2).
    # 결과는 .json이라 같은 버킷에 써도 Eventarc 핸들러의 확장자 필터에서 걸러진다.
    try:
        result_uri = storage_client.upload_json(
            config.RESULTS_BUCKET_NAME, f"results/{req.photo_id}.json", result_payload
        )
        result_payload["result_uri"] = result_uri
    except Exception:
        # 결과 사본 저장 실패로 이미 계산한 CBM을 버리지는 않는다. Firestore가 정본이다.
        logger.exception("GCS 결과 저장 실패 - Firestore 결과는 유지한다: photo_id=%s", req.photo_id)

    firestore_client.save_vision_result(req.photo_id, result_payload)

    # 차량별 최근 운행. 브라우저를 닫았다 다시 들어와도 이 운행을 이어받게 하는 근거다.
    # 재매칭 루프가 화면 안에만 있어서, 이게 없으면 새로고침 한 번에 추적이 끊긴다.
    firestore_client.save_truck_session(req.truck_id, {
        "truck_id": req.truck_id,
        "photo_id": req.photo_id,
        "captured_at": captured_at,
        "quality_status": geometry_result.quality_status,
        "failure_reason": geometry_result.failure_reason,
    })

    # V6: space-geometry-ready 이벤트 발행 (원본 이미지/box/point cloud는 포함하지 않는다)
    event = SpaceGeometryReadyEvent(
        event_id=f"evt-{uuid.uuid4().hex[:12]}",
        truck_id=req.truck_id,
        photo_id=req.photo_id,
        captured_at=captured_at,
        estimated_free_cbm=geometry_result.estimated_free_cbm,
        usable_free_cbm=geometry_result.usable_free_cbm,
        unknown_cbm=geometry_result.unknown_cbm,
        quality_score=geometry_result.quality_score,
        quality_status=QualityStatus(geometry_result.quality_status),
        model_versions=ModelVersions(**model_versions),
    )
    pubsub_publisher.publish_space_geometry_ready(event)

    # 5.6 최소 MLOps: 재현성 확인에 필요한 값만 구조화 로그 한 줄로 남긴다.
    # Cloud Logging은 stdout의 JSON을 jsonPayload로 파싱하므로 필드 단위 조회가 된다.
    print(json.dumps({
        "severity": "INFO",
        "message": "vision_result",
        "photo_id": req.photo_id,
        "truck_id": req.truck_id,
        "captured_at": captured_at,
        "detector": config.OWLVIT_DETECTOR_VERSION,
        "depth_model": config.DEPTH_MODEL_VERSION,
        "geometry_lite_version": GEOMETRY_LITE_VERSION,
        "container_revision": os.getenv("K_REVISION", ""),
        "voxel_edge_m": config.VOXEL_EDGE_M,
        "safety_factor": config.SAFETY_FACTOR,
        "intrinsics_source": intrinsics.source,
        "intrinsics_confidence": intrinsics.confidence,
        "exif_present": bool(pre.exif),
        "owl_box_count": len(owl_boxes),
        "plane_residual_avg": geometry_result.plane_residual_avg,
        "scale_correction_ratio": geometry_result.scale_correction_ratio,
        "structural_plane_count": geometry_result.structural_plane_count,
        "depth_outlier_ratio": geometry_result.depth_outlier_ratio,
        "observed_voxel_ratio": geometry_result.observed_voxel_ratio,
        "owl_coverage_ratio": geometry_result.owl_coverage_ratio,
        "estimated_free_cbm": geometry_result.estimated_free_cbm,
        "usable_free_cbm": geometry_result.usable_free_cbm,
        "unknown_cbm": geometry_result.unknown_cbm,
        "quality_score": geometry_result.quality_score,
        "quality_status": geometry_result.quality_status,
        "failure_reason": geometry_result.failure_reason,
        "model_latency_ms": model_latency_ms,
        "geometry_latency_ms": geometry_latency_ms,
        "total_latency_ms": int((time.perf_counter() - t_start) * 1000),
    }, ensure_ascii=False), flush=True)

    return result_payload


@app.post("/v1/photos/process")
def process_photo_endpoint(req: ProcessPhotoRequest):
    """데모/직접 호출용 엔드포인트. 실제 배포에서는 Eventarc가
    /v1/events/object-finalized를 통해 이 파이프라인을 트리거한다."""
    return _process_photo(req)


# GCS 객체 리소스/Pub-Sub attributes/CloudEvent가 각각 다른 키 이름을 쓴다.
_BUCKET_KEYS = ("bucket", "bucketId", "bucket_id", "bucketName")
_NAME_KEYS = ("name", "objectId", "object_id", "objectName")
# 업로더가 GCS 객체 커스텀 메타데이터로 truck_id를 심어 두면 경로와 무관하게 사용한다.
_TRUCK_ID_KEYS = ("truck_id", "truckId", "truckid", "TRUCK_ID")
_MAX_SEARCH_DEPTH = 8

# 파이프라인 대상 이미지 확장자. 그 외 객체(JSON 결과, 임시파일 등)는 무시한다.
_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")
# 경로 마지막 디렉터리가 이 이름이면 truck_id가 아니라 단순 분류 폴더로 본다.
_GENERIC_DIRS = {"photos", "photo", "images", "image", "uploads", "upload", "raw", "tmp"}
# 파일명 안에 'T-001' 형태로 truck_id가 박혀 있는 경우를 위한 폴백 패턴
_TRUCK_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{1,4}-\d{2,})(?![0-9])")


def _first_str(node: dict, keys: Tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _decode_nested(value: str):
    """Pub/Sub `message.data`(base64 JSON)나 JSON 문자열로 한 번 더 감싸인 페이로드를 푼다."""
    text = value.strip()
    if not text:
        return None
    if not text.startswith(("{", "[")):
        try:
            text = base64.b64decode(text, validate=True).decode("utf-8").strip()
        except Exception:
            return None
    if not text.startswith(("{", "[")):
        return None
    try:
        parsed = json.loads(text)
    except Exception:
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _collect_gcs_hints(node, found: dict, depth: int = 0) -> None:
    """페이로드 계층을 재귀 순회하며 bucket/name 후보를 모두 긁어모은다.

    Eventarc는 트리거 설정/전송 경로에 따라 GCS 객체 정보를 body 최상위, `data`,
    `message.data`(base64), `message.attributes`, CloudEvent `subject`/`source` 중
    어디에나 실어 보낼 수 있어 계층을 예단하지 않는다."""
    if depth > _MAX_SEARCH_DEPTH:
        return

    if isinstance(node, list):
        for item in node:
            _collect_gcs_hints(item, found, depth + 1)
        return

    if not isinstance(node, dict):
        return

    if not found.get("bucket"):
        found["bucket"] = _first_str(node, _BUCKET_KEYS)

    name = _first_str(node, _NAME_KEYS)
    if name:
        # CloudEvent 봉투의 "name"(트리거/구독 리소스 이름 등)을 객체 이름으로 오인하지 않도록,
        # GCS 객체 리소스임을 알 수 있는 형제 키가 함께 있을 때만 확정값으로 쓴다.
        is_object_node = bool(_first_str(node, _BUCKET_KEYS)) or node.get("kind") == "storage#object" or any(
            k in node for k in ("generation", "contentType", "content_type", "mediaLink", "size")
        )
        if is_object_node and not found.get("name"):
            found["name"] = name
        elif not found.get("loose_name") and "/" in name and "." in name.rsplit("/", 1)[-1]:
            # 확정은 아니지만 "photos/T-1/P-abc.jpg" 형태면 후보로 남겨 둔다.
            found["loose_name"] = name
    if not found.get("truck_id"):
        # 객체 커스텀 메타데이터(storage#object의 "metadata" dict)에 실려 오는 경우를 잡는다.
        found["truck_id"] = _first_str(node, _TRUCK_ID_KEYS)
    if not found.get("subject"):
        subject = node.get("subject")
        if isinstance(subject, str) and subject.strip():
            found["subject"] = subject.strip()
    if not found.get("source"):
        source = node.get("source")
        if isinstance(source, str) and "/buckets/" in source:
            found["source"] = source.strip()
    if not found.get("id"):
        # storage#object의 id는 "<bucket>/<object>/<generation>" 형식이다.
        obj_id = node.get("id")
        if isinstance(obj_id, str) and obj_id.count("/") >= 2:
            found["id"] = obj_id.strip()

    for key, value in node.items():
        if isinstance(value, (dict, list)):
            _collect_gcs_hints(value, found, depth + 1)
        elif isinstance(value, str) and key in ("data", "message", "body", "payload"):
            nested = _decode_nested(value)
            if nested is not None:
                _collect_gcs_hints(nested, found, depth + 1)


def _extract_gcs_event(body, headers=None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Eventarc/Pub-Sub 페이로드 형식에 관계없이 (bucket, object name, truck_id)를 추출한다.
    truck_id는 객체 커스텀 메타데이터에 실려 있을 때만 채워지고, 없으면 None이다.

    지원 형태:
    - Eventarc binary content mode: 본문이 GCS 객체 리소스({"bucket":..., "name":...})
    - CloudEvents structured 모드: {"type":..., "source":..., "subject":..., "data": {...}}
    - Pub/Sub push: {"message": {"data": "<base64 JSON>", "attributes": {"bucketId":..., "objectId":...}}}
    - 위 어느 계층에도 없으면 CloudEvent HTTP 헤더(ce-bucket/ce-subject/ce-source)로 폴백
    """
    found: dict = {}
    _collect_gcs_hints(body, found)

    bucket = found.get("bucket")
    name = found.get("name")

    if not name:
        name = found.get("loose_name")

    # subject는 "objects/photos/T-1/P-abc.jpg" 형식으로 온다.
    subject = found.get("subject")
    if not name and subject:
        name = subject.split("objects/", 1)[-1] if subject.startswith("objects/") else subject
    # source는 "//storage.googleapis.com/projects/_/buckets/<bucket>" 형식이다.
    source = found.get("source")
    if not bucket and source:
        bucket = source.split("/buckets/", 1)[-1].split("/")[0]
    # storage#object.id = "<bucket>/<object>/<generation>"
    obj_id = found.get("id")
    if obj_id and (not bucket or not name):
        head, _, _ = obj_id.rpartition("/")
        id_bucket, _, id_name = head.partition("/")
        bucket = bucket or id_bucket or None
        name = name or id_name or None

    if (not bucket or not name) and headers:
        # binary content mode에서는 본문이 비어 있고 헤더에만 정보가 실릴 수 있다.
        header_bucket = headers.get("ce-bucket") or headers.get("ce-bucketid")
        header_subject = headers.get("ce-subject")
        header_source = headers.get("ce-source") or ""
        if not bucket:
            if header_bucket:
                bucket = header_bucket
            elif "/buckets/" in header_source:
                bucket = header_source.split("/buckets/", 1)[-1].split("/")[0]
        if not name and header_subject:
            name = header_subject.split("objects/", 1)[-1] if header_subject.startswith("objects/") else header_subject

    return bucket or None, name or None, found.get("truck_id") or None


def _resolve_truck_id(parts: list, stem: str, metadata_truck_id: Optional[str]) -> Tuple[str, str]:
    """object 경로에서 truck_id를 복원한다. 반환값은 (truck_id, 출처) 이며 로그에 출처를 남긴다.

    우선순위: 객체 커스텀 메타데이터 > 상위 디렉터리명('photos/{truck_id}/...') >
    파일명에 박힌 'T-001' 형태 > config.DEFAULT_TRUCK_ID.
    버킷 최상단 업로드('20260806_xxx.jpg')는 마지막 두 단계로 흡수된다."""
    if metadata_truck_id:
        return metadata_truck_id, "object metadata"

    if len(parts) >= 2 and parts[-2].lower() not in _GENERIC_DIRS:
        return parts[-2], "경로 디렉터리"

    matched = _TRUCK_ID_PATTERN.search(stem)
    if matched:
        return matched.group(1), "파일명 패턴"

    return config.DEFAULT_TRUCK_ID, "config.DEFAULT_TRUCK_ID 기본값"


def _handle_object_finalized_event(body, headers=None) -> dict:
    """D2->D3: GCS `object.finalized` 이벤트 공통 처리 로직.

    photo_id는 확장자를 뗀 파일명, truck_id는 _resolve_truck_id()로 복원한다.
    'photos/{truck_id}/{photo_id}.jpg' 규칙(upload-url 발급 경로)뿐 아니라
    버킷 최상단에 바로 올라온 이미지도 동일하게 처리한다."""
    bucket, name, metadata_truck_id = _extract_gcs_event(body, headers)
    if not bucket or not name:
        # 어떤 계층에서도 못 찾았으면 실제 수신 구조를 그대로 남겨 눈으로 확인할 수 있게 한다.
        logger.warning("bucket/name 추출 실패 - 수신된 페이로드: %s", body)
        if headers:
            logger.warning("수신된 CloudEvent 헤더: %s", {k: v for k, v in headers.items() if k.startswith("ce-")})
        raise HTTPException(status_code=400, detail="잘못된 Eventarc/Pub-Sub payload")

    logger.info("GCS 객체 추출 성공: bucket=%s, name=%s", bucket, name)

    parts = [p for p in name.split("/") if p]
    if not parts:
        raise HTTPException(status_code=400, detail=f"예상치 못한 object 경로: {name}")

    filename = parts[-1]
    # 경로(폴더) 제약은 두지 않고 확장자로만 분석 대상을 가린다. 결과 JSON/임시파일 등이
    # 같은 버킷에 올라와도 여기서 걸러져 파이프라인이 헛돌지 않는다.
    if not filename.lower().endswith(_IMAGE_EXTENSIONS):
        logger.info("이미지 파일이 아니므로 건너뜀: %s (허용 확장자: %s)", name, ", ".join(_IMAGE_EXTENSIONS))
        return {"status": "skipped", "object": name, "reason": "not_an_image"}

    photo_id = filename.rsplit(".", 1)[0].strip()
    if not photo_id:
        raise HTTPException(status_code=400, detail=f"photo_id를 만들 수 없는 파일명: {name}")

    # D1: PWA가 upload-url 발급 때 남긴 컨텍스트가 있으면 그것이 가장 정확한 출처다.
    # 경로/파일명 추론은 PWA를 거치지 않고 버킷에 직접 올라온 사진을 위한 폴백으로 남는다.
    context = firestore_client.get_photo_context(photo_id) or {}
    native_intrinsics = context.get("native_intrinsics")
    if context.get("truck_id"):
        truck_id, truck_id_source = context["truck_id"], "PWA 업로드 컨텍스트"
    else:
        truck_id, truck_id_source = _resolve_truck_id(parts, photo_id, metadata_truck_id)
    logger.info("경로 파싱 완료: photo_id=%s, truck_id=%s (출처: %s)", photo_id, truck_id, truck_id_source)

    # 2.1/5.8/5.9: photo_id를 idempotency key로 쓴다. Eventarc 재전송이나 동시 배달로
    # 같은 사진에 대해 Depth/OWL 추론을 두 번 돌리지 않도록 파이프라인 진입 전에 잡는다.
    if not firestore_client.claim_photo(photo_id):
        logger.info("이미 처리된 photo_id이므로 건너뜀: %s", photo_id)
        return {"status": "duplicate", "photo_id": photo_id}

    req = ProcessPhotoRequest(
        photo_id=photo_id,
        truck_id=truck_id,
        object_uri=f"gs://{bucket}/{name}",
        native_intrinsics=native_intrinsics,
    )
    logger.info("AI 파이프라인 시작: photo_id=%s, truck_id=%s, uri=%s", photo_id, truck_id, req.object_uri)
    try:
        result = _process_photo(req)
    except Exception:
        # 점유를 풀지 않으면 첫 시도가 실패한 사진은 재시도해도 duplicate로 걸려 영영 처리되지 않는다.
        firestore_client.release_photo(photo_id)
        raise
    logger.info(
        "CBM 계산 완료: photo_id=%s, usable_free_cbm=%s, quality_status=%s",
        photo_id,
        result.get("usable_free_cbm"),
        result.get("quality_status"),
    )
    return {"status": "processed", "photo_id": photo_id, "quality_status": result["quality_status"]}


@app.post("/v1/events/object-finalized")
async def object_finalized(request: Request):
    """수동 테스트 또는 Eventarc 트리거를 이 경로로 명시 설정한 경우를 위한 별칭 엔드포인트.
    실제 처리 로직은 루트(/) POST 핸들러와 동일하다."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _handle_object_finalized_event(body, {k.lower(): v for k, v in request.headers.items()})


@app.get("/v1/defaults")
def get_defaults():
    """프론트가 기본 목적지를 표시할 때 쓴다. 값의 정본은 서버 설정이라
    프론트에 같은 주소를 복제해 두지 않는다."""
    return {
        "default_destination": {
            "address": config.DEFAULT_DESTINATION_ADDRESS,
            "lat": config.DEFAULT_DESTINATION_LAT,
            "lng": config.DEFAULT_DESTINATION_LNG,
        },
        "geocoding_enabled": bool(config.KAKAO_REST_API_KEY),
    }


KAKAO_LOCAL_BASE = "https://dapi.kakao.com/v2/local/search"


def _kakao_search(path: str, params: dict) -> list:
    """카카오 Local API 호출. documents[]를 그대로 돌려준다.
    좌표는 문자열로 오고 x가 경도(lng), y가 위도(lat)다 — 순서를 헷갈리기 쉬우니 주의."""
    resp = requests.get(
        f"{KAKAO_LOCAL_BASE}/{path}",
        params=params,
        headers={"Authorization": f"KakaoAK {config.KAKAO_REST_API_KEY}"},
        timeout=8,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"{resp.status_code} {resp.text[:200]}")
    return resp.json().get("documents", [])


@app.get("/v1/geocode")
def geocode(q: str):
    """목적지 검색. 카카오 Local API를 서버에서 대신 호출한다.

    브라우저에서 직접 부르지 않는 이유는 REST 키를 노출하지 않기 위해서다.
    키가 없으면 503을 반환하고, 프론트는 기본 목적지만 쓰도록 degrade한다.

    키워드 검색과 주소 검색을 모두 쓴다. 기사가 '물류산업진흥재단' 같은 장소명을 넣을 수도,
    '마포대로 34' 같은 주소를 넣을 수도 있는데 카카오는 둘을 다른 엔드포인트로 나눠 두었다.
    """
    query = (q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="검색어가 비어 있습니다.")
    if not config.KAKAO_REST_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="주소 검색이 설정되지 않았습니다. KAKAO_REST_API_KEY가 필요합니다.",
        )

    results = []
    seen = set()

    def add(address: str, x: str, y: str, place: str = ""):
        if not address or x in (None, "") or y in (None, ""):
            return
        key = (x, y)
        if key in seen:
            return
        seen.add(key)
        # x=경도, y=위도. 카카오는 문자열로 준다.
        results.append({
            "address": f"{place} · {address}" if place else address,
            "lat": float(y),
            "lng": float(x),
        })

    try:
        # 장소명 우선. 기사가 상호명을 넣는 경우가 더 흔하다.
        for d in _kakao_search("keyword.json", {"query": query, "size": 5}):
            add(
                d.get("road_address_name") or d.get("address_name", ""),
                d.get("x"), d.get("y"), d.get("place_name", ""),
            )
        for d in _kakao_search("address.json", {"query": query, "size": 5}):
            add(d.get("address_name", ""), d.get("x"), d.get("y"))
    except Exception as exc:
        logger.exception("카카오 Local API 호출 실패")
        raise HTTPException(status_code=502, detail=f"주소 검색 실패: {exc}")

    return {"results": results[:8]}


@app.get("/v1/reverse-geocode")
def reverse_geocode(lat: float, lng: float):
    """좌표 -> 주소. 촬영 화면이 "지금 여기가 어디인지"를 글로 보여줄 때 쓴다.

    브라우저 geolocation은 좌표만 준다. 기사에게 37.5883, 127.0104를 보여줘 봐야
    자기 위치가 맞는지 확인할 수 없다. 주소로 바꿔야 검증이 가능하다.

    /v1/geocode와 같은 이유로 서버가 대신 부른다 — REST 키를 브라우저에 노출하지 않는다.
    키가 없거나 실패하면 좌표만 쓰도록 프론트가 degrade하므로 500을 던지지 않는다.
    """
    if not config.KAKAO_REST_API_KEY:
        return {"address": None, "reason": "KAKAO_REST_API_KEY 미설정"}
    try:
        resp = requests.get(
            "https://dapi.kakao.com/v2/local/geo/coord2address.json",
            params={"x": lng, "y": lat},  # x=경도, y=위도. 순서를 헷갈리기 쉽다.
            headers={"Authorization": f"KakaoAK {config.KAKAO_REST_API_KEY}"},
            timeout=8,
        )
        resp.raise_for_status()
        docs = resp.json().get("documents", [])
    except Exception as exc:
        logger.warning("역지오코딩 실패 (lat=%s lng=%s): %s", lat, lng, exc)
        return {"address": None, "reason": "주소 조회 실패"}

    if not docs:
        # 바다 위나 주소 체계가 없는 곳이면 정상적으로 빈 결과가 온다.
        return {"address": None, "reason": "해당 좌표의 주소 없음"}

    d = docs[0]
    road = (d.get("road_address") or {}).get("address_name")
    jibun = (d.get("address") or {}).get("address_name")
    return {"address": road or jibun, "road_address": road, "jibun_address": jibun}


@app.get("/v1/trucks/{truck_id}/session")
def get_truck_session_endpoint(truck_id: str, within_minutes: int = 60):
    """이 차량이 최근에 찍은 운행이 아직 유효한가.

    유효하면 화면은 촬영 버튼 대신 그 운행의 결과와 재매칭 상태를 바로 보여준다.
    운행 중에 브라우저를 닫았다 다시 여는 일이 흔한데, 그때마다 다시 찍게 하면
    사진을 두 번 올리는 셈이고 앞선 추적도 끊긴다.

    기준 시각은 촬영 시각이다. 하차하지 않는 한 빈 공간은 그대로이므로 그 사이 결과를
    그대로 쓸 수 있다. 한 시간이 지나면 상·하차가 있었다고 보고 다시 찍게 한다.
    """
    session = firestore_client.get_truck_session(truck_id)
    if not session:
        return {"active": False}

    try:
        captured = datetime.fromisoformat(str(session.get("captured_at", "")).replace("Z", "+00:00"))
    except ValueError:
        return {"active": False}
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=timezone.utc)

    age_s = (datetime.now(timezone.utc) - captured).total_seconds()
    # 품질이 REJECT면 그 운행에는 쓸 수 있는 숫자가 없다. 이어받지 않고 다시 찍게 한다.
    active = age_s <= within_minutes * 60 and session.get("quality_status") != "REJECTED"
    return {**session, "active": active, "age_seconds": int(age_s)}


@app.post("/v1/trucks/{truck_id}/location")
async def update_truck_location_endpoint(truck_id: str, request: Request):
    """운행 중 트럭 위치 갱신. 재매칭 루프가 주기적으로 부른다.

    매칭은 trucks 문서의 current_lat/lng를 기준으로 회랑을 만든다. 촬영 시점 한 번만
    갱신하면 트럭이 이동해도 계속 출발지 주변 화물만 추천된다 — 목적지로 가는 도중에
    새로 잡히는 화물을 놓친다.

    merge=True라 제원이나 목적지를 지우지 않는다.
    """
    try:
        body = await request.json()
        lat, lng = float(body["lat"]), float(body["lng"])
    except Exception:
        raise HTTPException(status_code=400, detail="lat/lng가 필요합니다.")
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        raise HTTPException(status_code=400, detail="좌표 범위를 벗어났습니다.")

    firestore_client.update_truck_location(truck_id, current_lat=lat, current_lng=lng)
    return {"status": "ok", "truck_id": truck_id, "lat": lat, "lng": lng}


@app.get("/v1/trucks")
def list_trucks(limit: int = 200):
    """등록된 차량 목록. 촬영 화면이 선택 목록을 만들 때 쓴다."""
    return {"trucks": firestore_client.list_truck_profiles(limit=limit)}


@app.get("/v1/trucks/{truck_id}")
def get_truck(truck_id: str):
    """촬영 전에 화면이 보여줄 차량 제원.

    분석은 등록된 적재함 치수를 기준 스케일로 삼는다. 사진 속 차량이 이 제원과 다르면
    빈 공간 계산이 통째로 어긋나므로, 찍기 전에 확인할 수 있어야 한다.

    등록되지 않은 차량도 404가 아니라 200 + registered=false로 돌려준다. 404로 하면
    **경로가 없을 때**(구버전이 떠 있거나 배포 전)와 구분되지 않는다. 실제로 화면이
    멀쩡히 등록된 차량을 "미등록"이라고 표시한 적이 있다 — 원인은 배포가 안 끝난 것이었다.
    """
    profile = firestore_client.get_truck_profile(truck_id)
    if profile is None:
        return {"truck_id": truck_id, "registered": False}
    return {**profile, "registered": True}


@app.get("/v1/results/{photo_id}")
def get_result(photo_id: str):
    result = firestore_client.get_vision_result(photo_id)
    if result is None:
        raise HTTPException(status_code=404, detail="결과 없음")
    return result


# D1 촬영 앱은 frontend/ 디렉터리의 별도 Cloud Run 서비스로 분리했다.
# Vision은 API만 제공한다 — UI를 고칠 때 Depth 가중치를 굽는 이 이미지를 다시 빌드하지 않기 위해서다.
