from dataclasses import dataclass
from typing import List

import numpy as np
import open3d as o3d

import config
from model_clients.owlvit_client import OwlBox


@dataclass
class CargoPointResult:
    points_truck: np.ndarray  # Nx3, 트럭 좌표계, 화물로 판정된 점
    source_mask: np.ndarray  # 원본 점 배열 기준 boolean mask (voxel_cbm에서 free점과 분리하는데 사용)
    owl_coverage_ratio: float  # 화물 점 중 OWL box에서 나온 비율(품질점수 입력)


def _points_in_owl_boxes(
    pixel_uv: np.ndarray,
    owl_boxes: List[OwlBox],
    min_score: float,
    max_area_ratio: float = 1.0,
) -> np.ndarray:
    """OWL 박스(2D 사각형) 안에 픽셀이 들어오는 점의 mask.

    화면을 크게 덮는 박스는 버린다. 택배 상자 하나가 프레임의 절반을 차지할 수는 없고,
    그런 검출은 대개 배경(건물 벽, 옆 차량, 간판)을 통째로 잡은 것이다. 그 박스를 그대로
    쓰면 그 안에 들어오는 적재함 표면까지 화물로 끌려 들어간다.
    """
    mask = np.zeros(len(pixel_uv), dtype=bool)
    if len(pixel_uv) == 0:
        return mask

    # 이미지 크기를 픽셀 좌표 범위로 근사한다. OwlBox와 pixel_uv가 같은 좌표계다.
    frame_area = float(pixel_uv[:, 0].max() * pixel_uv[:, 1].max()) or 1.0

    for box in owl_boxes:
        if box.score < min_score:
            continue
        area = max(0.0, box.xmax - box.xmin) * max(0.0, box.ymax - box.ymin)
        if area / frame_area > max_area_ratio:
            continue
        mask |= (
            (pixel_uv[:, 0] >= box.xmin)
            & (pixel_uv[:, 0] <= box.xmax)
            & (pixel_uv[:, 1] >= box.ymin)
            & (pixel_uv[:, 1] <= box.ymax)
        )
    return mask


def _cluster_non_plane_points(
    points_truck: np.ndarray,
    candidate_mask: np.ndarray,
    eps: float = 0.08,
    min_points: int = 20,
    min_cluster_size: int = 60,
) -> np.ndarray:
    """4.7: 평면에 속하지 않는 점 중 DBSCAN cluster(noise 아님 + 최소 크기 이상)만 화물 후보로 채택."""
    idx = np.nonzero(candidate_mask)[0]
    if len(idx) < min_points:
        return np.zeros(len(points_truck), dtype=bool)

    sub_pcd = o3d.geometry.PointCloud()
    sub_pcd.points = o3d.utility.Vector3dVector(points_truck[idx])
    labels = np.array(sub_pcd.cluster_dbscan(eps=eps, min_points=min_points, print_progress=False))

    keep = np.zeros(len(points_truck), dtype=bool)
    for label in set(labels.tolist()):
        if label == -1:
            continue  # RANSAC/DBSCAN noise
        cluster_idx = idx[labels == label]
        if len(cluster_idx) >= min_cluster_size:
            keep[cluster_idx] = True
    return keep


def extract_cargo_points(
    points_truck: np.ndarray,
    pixel_uv: np.ndarray,
    owl_boxes: List[OwlBox],
    plane_inlier_mask: np.ndarray,
    truck_width_m: float,
    truck_length_m: float,
    truck_height_m: float,
    owl_min_score: float = None,
) -> CargoPointResult:
    """4.7: cargo_points = depth_points_inside_owl_boxes UNION clustered_non_plane_points_inside_truck

    단, **구조 평면에 속한 점은 어느 경로로도 화물이 되지 않는다.** 바닥·벽·천장은
    화물이 아니다. OWL 박스는 2D 사각형이라 배경에서 잡힌 박스가 화면을 넓게 덮으면
    그 안에 들어오는 적재함 바닥까지 함께 끌어온다 - 빈 적재함일수록 바닥이 크게 보여
    유령 화물이 커진다. 실제로 빈 11톤 차량에서 7.5CBM이 화물로 잡혔다.
    """
    if owl_min_score is None:
        owl_min_score = config.OWL_MIN_SCORE

    in_bounds = (
        (points_truck[:, 0] >= 0) & (points_truck[:, 0] <= truck_width_m)
        & (points_truck[:, 1] >= 0) & (points_truck[:, 1] <= truck_length_m)
        & (points_truck[:, 2] >= 0) & (points_truck[:, 2] <= truck_height_m)
    )
    non_plane = ~plane_inlier_mask & in_bounds

    owl_mask = (
        _points_in_owl_boxes(pixel_uv, owl_boxes, owl_min_score, config.OWL_MAX_BOX_AREA_RATIO)
        & non_plane  # in_bounds + 평면 제외. 클러스터 경로와 같은 조건을 쓴다.
    )
    cluster_mask = _cluster_non_plane_points(points_truck, non_plane)

    cargo_mask = owl_mask | cluster_mask
    owl_coverage_ratio = float(owl_mask.sum() / cargo_mask.sum()) if cargo_mask.sum() > 0 else 0.0

    return CargoPointResult(
        points_truck=points_truck[cargo_mask],
        source_mask=cargo_mask,
        owl_coverage_ratio=owl_coverage_ratio,
    )
