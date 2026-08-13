from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class QualityStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    LIMITED = "LIMITED"
    REJECTED = "REJECTED"


class TruckSpec(BaseModel):
    """4.2 입력 데이터"""

    truck_id: str
    cargo_width_m: float
    cargo_length_m: float
    cargo_height_m: float
    max_payload_kg: float
    current_loaded_weight_kg: Optional[float] = None


class ProcessPhotoRequest(BaseModel):
    photo_id: str
    truck_id: str
    object_uri: str
    native_intrinsics: Optional[dict] = None


class ModelVersions(BaseModel):
    detector: str
    depth: str
    geometry: str


class SpaceGeometryReadyEvent(BaseModel):
    """2.2: Vision -> Matching 파이프라인 경계. 이 스키마 외 원본 이미지, OWL box 전체,
    depth map, point cloud는 이벤트에 포함하지 않는다."""

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
    model_versions: ModelVersions