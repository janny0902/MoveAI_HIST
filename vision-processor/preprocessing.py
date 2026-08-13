import io
from dataclasses import dataclass

import numpy as np
from PIL import ExifTags, Image, ImageOps

LONG_SIDE_PX = 1024
JPEG_QUALITY = 78


@dataclass
class PreprocessResult:
    image: Image.Image
    exif: dict
    blur_score: float
    exposure_score: float
    resize_ratio: float


def _read_exif(image: Image.Image) -> dict:
    raw = image.getexif()
    if not raw:
        return {}
    return {ExifTags.TAGS.get(tag_id, tag_id): value for tag_id, value in raw.items()}


def _blur_score(gray: np.ndarray) -> float:
    """Laplacian variance 기반 blur score(0-1, 클수록 선명)."""
    from scipy.signal import convolve2d

    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float64)
    lap = convolve2d(gray, kernel, mode="valid")
    return float(np.clip(lap.var() / 500.0, 0.0, 1.0))


def _exposure_score(gray: np.ndarray) -> float:
    """과다/과소 노출(0, 255 클리핑) 비율이 낮을수록 높은 점수."""
    hist, _ = np.histogram(gray, bins=256, range=(0, 255))
    clipped_ratio = (hist[0] + hist[-1]) / gray.size
    return float(np.clip(1.0 - clipped_ratio * 4.0, 0.0, 1.0))


def preprocess_image(jpeg_bytes: bytes) -> PreprocessResult:
    """V2: EXIF 방향 정규화 -> blur/exposure 품질검사 -> 긴 변 1024px 축소.
    focal length는 resize_ratio만큼 호출자(camera.py 연계 지점)에서 동일 비율로 보정해야 한다."""
    image = Image.open(io.BytesIO(jpeg_bytes))
    exif = _read_exif(image)
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")

    gray = np.array(image.convert("L"), dtype=np.float64)
    blur_score = _blur_score(gray)
    exposure_score = _exposure_score(gray)

    long_side = max(image.width, image.height)
    resize_ratio = min(1.0, LONG_SIDE_PX / long_side)
    if resize_ratio < 1.0:
        new_size = (round(image.width * resize_ratio), round(image.height * resize_ratio))
        image = image.resize(new_size, Image.LANCZOS)

    return PreprocessResult(
        image=image,
        exif=exif,
        blur_score=blur_score,
        exposure_score=exposure_score,
        resize_ratio=resize_ratio,
    )