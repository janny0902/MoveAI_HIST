from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from .plane_fit import Plane, PlaneType


@dataclass
class TruckFrame:
    rotation: np.ndarray  # 3x3, 카메라 좌표 -> 트럭 축 정렬(scale 이전)
    origin: np.ndarray  # (3,), 카메라 좌표계 기준 원점(scale 이전)
    scale: float  # s*: metric depth scale 보정값
    width_est_m: float
    height_est_m: float
    scale_residual: float  # (s*W_est-W)^2 + (s*H_est-H)^2


def _basis_from_floor(floor: Plane, wall: Optional[Plane]) -> np.ndarray:
    """바닥 normal을 z축으로, 벽 normal(있으면)을 x축 참고로 정규직교 기저를 만든다.
    반환값의 각 행이 트럭 좌표계 x/y/z 축을 카메라 좌표계로 표현한다."""
    z_axis = floor.normal / np.linalg.norm(floor.normal)

    ref = wall.normal if wall is not None else np.array([1.0, 0.0, 0.0])
    x_ref = ref - np.dot(ref, z_axis) * z_axis
    if np.linalg.norm(x_ref) < 1e-6:
        fallback = np.array([1.0, 0.0, 0.0])
        x_ref = fallback - np.dot(fallback, z_axis) * z_axis
    x_axis = x_ref / np.linalg.norm(x_ref)
    y_axis = np.cross(z_axis, x_axis)

    return np.stack([x_axis, y_axis, z_axis], axis=0)


def estimate_scale(
    width_est_m: float, height_est_m: float, known_width_m: float, known_height_m: float
) -> Tuple[float, float]:
    """4.6: s* = argmin_s [(s*W_est-W)^2 + (s*H_est-H)^2]의 폐형해(1차 최소제곱)."""
    denom = width_est_m**2 + height_est_m**2
    if denom < 1e-9:
        return 1.0, float("inf")
    s_star = (width_est_m * known_width_m + height_est_m * known_height_m) / denom
    residual = (s_star * width_est_m - known_width_m) ** 2 + (s_star * height_est_m - known_height_m) ** 2
    return float(s_star), float(residual)


def build_truck_frame(
    planes: List[Plane], points_camera: np.ndarray, known_width_m: float, known_height_m: float
) -> Optional[TruckFrame]:
    """4.5/4.6: 최소 두 개의 유효 구조 평면(바닥 + 벽 또는 천장)이 없으면 None을 반환해
    호출자가 실패로 처리하도록 한다."""
    floor = next((p for p in planes if p.plane_type == PlaneType.FLOOR), None)
    walls = [p for p in planes if p.plane_type == PlaneType.WALL]
    ceiling = next((p for p in planes if p.plane_type == PlaneType.CEILING), None)

    if floor is None or (not walls and ceiling is None):
        return None

    wall = walls[0] if walls else None
    R = _basis_from_floor(floor, wall)

    origin = points_camera.mean(axis=0)
    p_local = (points_camera - origin) @ R.T

    width_est = float(p_local[:, 0].max() - p_local[:, 0].min())
    height_est = float(p_local[:, 2].max() - p_local[:, 2].min()) if ceiling is not None else known_height_m

    s_star, residual = estimate_scale(width_est, height_est, known_width_m, known_height_m)

    return TruckFrame(
        rotation=R, origin=origin, scale=s_star,
        width_est_m=width_est, height_est_m=height_est, scale_residual=residual,
    )


def transform_to_truck_frame(points_camera: np.ndarray, frame: TruckFrame) -> np.ndarray:
    """P_truck = T_camera_to_truck x P_camera (scale 보정 포함).
    x: 좌측->우측, y: 후문->전면(상한으로만 사용), z: 바닥->천장."""
    p_local = (points_camera - frame.origin) @ frame.rotation.T
    p_scaled = p_local * frame.scale
    x = p_scaled[:, 0] - p_scaled[:, 0].min()
    y = p_scaled[:, 1] - p_scaled[:, 1].min()
    z = p_scaled[:, 2] - p_scaled[:, 2].min()
    return np.stack([x, y, z], axis=-1)
