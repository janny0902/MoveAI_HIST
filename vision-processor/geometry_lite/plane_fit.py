from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import numpy as np
import open3d as o3d

import config


class PlaneType(str, Enum):
    FLOOR = "FLOOR"
    WALL = "WALL"
    CEILING = "CEILING"
    UNKNOWN = "UNKNOWN"


@dataclass
class Plane:
    normal: np.ndarray  # (3,) 단위 normal, 카메라 좌표계
    d: float  # normal . x + d = 0
    inlier_indices: np.ndarray  # 원본 point cloud 기준 인덱스
    inlier_count: int
    residual: float  # RANSAC inlier 평균 residual(m)
    plane_type: PlaneType = PlaneType.UNKNOWN


def detect_structural_planes(
    pcd: o3d.geometry.PointCloud,
    max_planes: int = 5,
    distance_threshold: float = 0.03,
    ransac_n: int = 3,
    num_iterations: int = 1000,
    min_inlier_ratio: float = 0.03,
) -> List[Plane]:
    """4.5 단계 1: 가장 넓은 평면 후보를 Open3D RANSAC(segment_plane)으로 반복 추출한다."""
    total_points = len(pcd.points)
    if total_points == 0:
        return []

    remaining = pcd
    remaining_idx = np.arange(total_points)
    planes: List[Plane] = []

    for _ in range(max_planes):
        if len(remaining.points) < ransac_n * 5:
            break
        model, inliers = remaining.segment_plane(
            distance_threshold=distance_threshold, ransac_n=ransac_n, num_iterations=num_iterations
        )
        if len(inliers) < total_points * min_inlier_ratio:
            break

        a, b, c, d = model
        normal = np.array([a, b, c])
        norm_len = np.linalg.norm(normal)
        normal = normal / norm_len
        d = d / norm_len

        inlier_pts = np.asarray(remaining.points)[inliers]
        residual = float(np.mean(np.abs(inlier_pts @ normal + d)))

        planes.append(
            Plane(
                normal=normal,
                d=float(d),
                inlier_indices=remaining_idx[inliers],
                inlier_count=len(inliers),
                residual=residual,
            )
        )

        remaining_idx = np.delete(remaining_idx, inliers)
        remaining = remaining.select_by_index(inliers, invert=True)

    return planes


def classify_planes(planes: List[Plane], camera_up_hint: Optional[np.ndarray] = None) -> List[Plane]:
    """4.5 단계 2-4: 서로 약 90도로 직교하는 normal 조합에서 바닥/벽/천장을 선택한다.
    카메라는 통상 화물칸을 정면에서 촬영하므로 이미지 좌표계 기준 -y(위쪽)에 가까운
    normal을 가진 평면을 바닥으로 근사한다."""
    if not planes:
        return planes
    if camera_up_hint is None:
        camera_up_hint = np.array([0.0, -1.0, 0.0])

    floor = max(planes, key=lambda p: np.dot(p.normal, camera_up_hint))
    floor.plane_type = PlaneType.FLOOR

    ceiling_candidates = [p for p in planes if p is not floor and np.dot(p.normal, floor.normal) < -0.7]
    if ceiling_candidates:
        max(ceiling_candidates, key=lambda p: p.inlier_count).plane_type = PlaneType.CEILING

    # 바닥 normal과 이 각도 이상 벌어지면 벽으로 본다. 정면에서 반듯하게 찍으면 90도지만,
    # 비스듬히 찍거나 depth가 거칠면 크게 벗어난다. 70도로 고정해 두니 벽이 뻔히 보이는
    # 사진에서도 벽을 못 찾아 분석이 통째로 중단됐다.
    wall_angle = getattr(config, "PLANE_WALL_ANGLE_DEG", 55.0)
    for p in planes:
        if p.plane_type == PlaneType.UNKNOWN:
            angle_deg = np.degrees(np.arccos(np.clip(abs(np.dot(p.normal, floor.normal)), -1.0, 1.0)))
            if angle_deg >= wall_angle:
                p.plane_type = PlaneType.WALL

    return planes
