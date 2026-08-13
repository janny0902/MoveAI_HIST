import math
from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np

IntrinsicSource = Literal["exif", "native", "vanishing_point", "default"]


@dataclass
class Intrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int
    source: IntrinsicSource
    confidence: float  # 0-1, quality_score 입력으로 사용

    def as_matrix(self) -> np.ndarray:
        return np.array(
            [[self.fx, 0.0, self.cx], [0.0, self.fy, self.cy], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )


def _focal_mm_to_px(focal_mm: float, sensor_width_mm: float, image_width_px: int) -> float:
    return focal_mm * (image_width_px / sensor_width_mm)


def _focal_35mm_to_px(focal_35mm_equiv: float, image_width_px: int, image_height_px: int) -> float:
    diag_px = math.hypot(image_width_px, image_height_px)
    diag_35mm = math.hypot(36.0, 24.0)  # 35mm 필름 대각선(mm)
    return focal_35mm_equiv * (diag_px / diag_35mm)


def from_exif(exif: dict, image_width: int, image_height: int) -> Optional[Intrinsics]:
    """4.3 우선순위 1: EXIF의 focal length 또는 35mm equivalent focal length."""
    cx, cy = image_width / 2.0, image_height / 2.0

    focal_35mm = exif.get("FocalLengthIn35mmFilm")
    if focal_35mm:
        f_px = _focal_35mm_to_px(float(focal_35mm), image_width, image_height)
        return Intrinsics(f_px, f_px, cx, cy, image_width, image_height, source="exif", confidence=0.9)

    focal_mm = exif.get("FocalLength")
    sensor_width_mm = exif.get("SensorWidthMM")  # 대부분의 EXIF에는 없어 거의 사용되지 않는 fallback
    if focal_mm and sensor_width_mm:
        f_px = _focal_mm_to_px(float(focal_mm), float(sensor_width_mm), image_width)
        return Intrinsics(f_px, f_px, cx, cy, image_width, image_height, source="exif", confidence=0.85)

    return None


def from_native(native_intrinsics: Optional[dict], image_width: int, image_height: int) -> Optional[Intrinsics]:
    """4.3 우선순위 2: 기존 네이티브 앱이 자동 제공하는 camera intrinsic."""
    if not native_intrinsics:
        return None
    try:
        return Intrinsics(
            fx=float(native_intrinsics["fx"]),
            fy=float(native_intrinsics["fy"]),
            cx=float(native_intrinsics.get("cx", image_width / 2.0)),
            cy=float(native_intrinsics.get("cy", image_height / 2.0)),
            width=image_width,
            height=image_height,
            source="native",
            confidence=0.95,
        )
    except (KeyError, TypeError, ValueError):
        return None


def from_vanishing_point(vp_focal_px: Optional[float], image_width: int, image_height: int) -> Optional[Intrinsics]:
    """4.3 우선순위 3: 화물칸 평행선의 소실점으로 근사한 focal length(px).
    소실점 검출 자체는 이 MVP 범위 밖이며, 호출자가 별도로 계산한 focal_px만 받는다."""
    if not vp_focal_px:
        return None
    return Intrinsics(
        vp_focal_px, vp_focal_px, image_width / 2.0, image_height / 2.0,
        image_width, image_height, source="vanishing_point", confidence=0.5,
    )


DEFAULT_HFOV_DEG = 65.0  # 스마트폰 후면 카메라의 일반적인 수평 화각 근사치


def default_intrinsics(image_width: int, image_height: int) -> Intrinsics:
    """4.3 우선순위 4: 모두 실패 시 기기 기본 화각 적용, quality_score를 크게 낮춘다."""
    f_px = (image_width / 2.0) / math.tan(math.radians(DEFAULT_HFOV_DEG) / 2.0)
    return Intrinsics(
        f_px, f_px, image_width / 2.0, image_height / 2.0,
        image_width, image_height, source="default", confidence=0.2,
    )


def estimate_intrinsics(
    image_width: int,
    image_height: int,
    exif: Optional[dict] = None,
    native_intrinsics: Optional[dict] = None,
    vanishing_point_focal_px: Optional[float] = None,
) -> Intrinsics:
    """4.3 자동 확보 우선순위를 순서대로 시도한다. 기사의 수동 캘리브레이션/탭은 사용하지 않는다."""
    for candidate in (
        from_exif(exif or {}, image_width, image_height),
        from_native(native_intrinsics, image_width, image_height),
        from_vanishing_point(vanishing_point_focal_px, image_width, image_height),
    ):
        if candidate is not None:
            return candidate
    return default_intrinsics(image_width, image_height)
