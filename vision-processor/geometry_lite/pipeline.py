import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import open3d as o3d

import config
from model_clients.owlvit_client import OwlBox

from .camera import Intrinsics
from .cargo_points import extract_cargo_points
from .plane_fit import PlaneType, classify_planes, detect_structural_planes
from .point_cloud import depth_outlier_ratio, depth_to_camera_points
from .truck_frame import build_truck_frame, transform_to_truck_frame
from .voxel_cbm import classify_and_compute_cbm

GEOMETRY_LITE_VERSION = "geometry-lite-v1"
logger = logging.getLogger("vision-processor")

MIN_STRUCTURAL_PLANES = 2


@dataclass
class GeometryLiteResult:
    quality_status: str  # ACCEPTED / LIMITED / REJECTED
    quality_score: float
    estimated_free_cbm: float
    usable_free_cbm: float
    unknown_cbm: float
    structural_plane_count: int
    scale_correction_ratio: float
    plane_residual_avg: float
    observed_voxel_ratio: float
    owl_coverage_ratio: float
    depth_outlier_ratio: float
    voxel_edge_m: float
    safety_factor: float
    # 결과 설명(XAI)용 중간값. 적재함 전체 = 짐 + 빈 공간 + 미관측 이라는 분해를
    # 화면이 그대로 보여줄 수 있어야 사용자가 숫자의 출처를 확인할 수 있다.
    occupied_cbm: float = 0.0
    observed_free_cbm: float = 0.0
    failure_reason: Optional[str] = None


def _reject(
    reason: str, safety_factor: float, voxel_edge_m: float, depth_outlier: float = 1.0
) -> GeometryLiteResult:
    """4.10/5.8: 구조 평면 부족, pose/scale 정합 실패 등은 Fail-closed로 즉시 종료한다."""
    return GeometryLiteResult(
        quality_status="REJECTED",
        quality_score=0.0,
        estimated_free_cbm=0.0,
        usable_free_cbm=0.0,
        unknown_cbm=0.0,
        structural_plane_count=0,
        scale_correction_ratio=0.0,
        plane_residual_avg=0.0,
        observed_voxel_ratio=0.0,
        owl_coverage_ratio=0.0,
        depth_outlier_ratio=depth_outlier,
        voxel_edge_m=voxel_edge_m,
        safety_factor=safety_factor,
        failure_reason=reason,
    )


def _compute_quality_score(
    intrinsics_confidence: float,
    structural_plane_count: int,
    plane_residual_avg: float,
    scale_residual: float,
    observed_voxel_ratio: float,
    owl_coverage_ratio: float,
    depth_outlier_ratio_value: float,
    blur_score: float,
    exposure_score: float,
) -> float:
    """4.10이 나열한 8개 항목을 모두 가중합해 0-1 품질점수를 만든다.
    blur/exposure, intrinsic 신뢰도, 구조 평면 수, RANSAC residual, W/H 정합 오차,
    depth outlier 비율, 관측 voxel 비율, OWL coverage."""
    plane_score = min(1.0, structural_plane_count / 3.0)
    residual_score = float(np.clip(1.0 - plane_residual_avg / 0.10, 0.0, 1.0))
    scale_score = float(np.clip(1.0 - scale_residual / 1.0, 0.0, 1.0))
    # outlier 비율은 낮을수록 좋으므로 점수로 뒤집는다.
    depth_score = float(np.clip(1.0 - depth_outlier_ratio_value, 0.0, 1.0))

    weights = {
        "blur": 0.13,
        "exposure": 0.05,
        "intrinsics": 0.13,
        "plane": 0.13,
        "residual": 0.13,
        "scale": 0.09,
        "depth_outlier": 0.10,
        "observed_voxel": 0.14,
        "owl_coverage": 0.10,
    }
    score = (
        weights["blur"] * blur_score
        + weights["exposure"] * exposure_score
        + weights["intrinsics"] * intrinsics_confidence
        + weights["plane"] * plane_score
        + weights["residual"] * residual_score
        + weights["scale"] * scale_score
        + weights["depth_outlier"] * depth_score
        + weights["observed_voxel"] * observed_voxel_ratio
        + weights["owl_coverage"] * owl_coverage_ratio
    )
    return float(np.clip(score, 0.0, 1.0))


def run_geometry_lite(
    depth_m: np.ndarray,
    K: Intrinsics,
    owl_boxes: List[OwlBox],
    truck_width_m: float,
    truck_length_m: float,
    truck_height_m: float,
    blur_score: float,
    exposure_score: float,
    safety_factor: float = 0.70,
    voxel_edge_m: float = 0.20,
    depth_type: str = "z_depth",
) -> GeometryLiteResult:
    """V4+V5: depth map + OWL boxes + 트럭 제원 -> plane/truck pose/20cm voxel -> CBM/품질점수."""
    # 4.10 입력. 화물칸 대각선의 2배를 넘는 depth는 문 밖 배경으로 보고 outlier로 센다.
    max_plausible_m = 2.0 * float(
        np.sqrt(truck_width_m**2 + truck_length_m**2 + truck_height_m**2)
    )
    outlier_ratio = depth_outlier_ratio(depth_m, max_plausible_m)

    points_camera, pixel_uv = depth_to_camera_points(depth_m, K, depth_type=depth_type)
    if len(points_camera) == 0:
        return _reject("no_valid_depth_points", safety_factor, voxel_edge_m, outlier_ratio)

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points_camera)

    planes = detect_structural_planes(
        pcd,
        distance_threshold=config.PLANE_DISTANCE_THRESHOLD_M,
        min_inlier_ratio=config.PLANE_MIN_INLIER_RATIO,
    )
    planes = classify_planes(planes)
    structural_plane_count = sum(1 for p in planes if p.plane_type != PlaneType.UNKNOWN)

    if structural_plane_count < MIN_STRUCTURAL_PLANES:
        # 거부 사유를 "평면이 부족하다"로만 남기면 왜 부족했는지 알 수 없다. RANSAC이
        # 평면을 아예 못 찾은 것과, 찾았는데 벽으로 분류되지 않은 것은 고칠 곳이 다르다.
        logger.warning(
            "구조 평면 부족: 검출 %d개 중 분류 %d개 (필요 %d) — normal=%s, inlier=%s",
            len(planes), structural_plane_count, MIN_STRUCTURAL_PLANES,
            [np.round(p.normal, 2).tolist() for p in planes],
            [p.inlier_count for p in planes],
        )
        return _reject("insufficient_structural_planes", safety_factor, voxel_edge_m, outlier_ratio)

    frame = build_truck_frame(planes, points_camera, truck_width_m, truck_height_m)
    if frame is None:
        logger.warning("적재함 기준면 실패: 분류된 평면 %d개", structural_plane_count)
        return _reject("truck_frame_failed", safety_factor, voxel_edge_m, outlier_ratio)

    # 사진에서 잰 적재함이 등록 제원과 배 이상 어긋나면, 적재함이 아닌 것에 평면을 맞춘
    # 것이다(차체 외곽, 주변 건물, 또는 아예 다른 차량). 이 상태로 계속 가면 빈 적재함에
    # 유령 화물이 5CBM 잡히는 식으로 조용히 틀린 답이 나온다. 그 구간만 끊는다.
    if not (config.SCALE_MIN <= frame.scale <= config.SCALE_MAX):
        logger.warning(
            "적재함 크기 불일치: scale=%.3f (허용 %.2f~%.2f) — 등록 제원 %.2fx%.2fm",
            frame.scale, config.SCALE_MIN, config.SCALE_MAX, truck_width_m, truck_height_m,
        )
        return _reject("scale_mismatch", safety_factor, voxel_edge_m, outlier_ratio)

    # 조금 어긋난 정도면 답은 준다. 화물칸이 일부만 보이거나 비스듬히 찍히면 치수 추정이
    # 흔들리는데, 그걸 이유로 판정을 거부할 필요는 없다. 대신 품질을 깎아 LIMITED로
    # 내려보내고, 추가 안전계수가 붙게 한다.
    scale_uncertain = not (config.SCALE_WARN_MIN <= frame.scale <= config.SCALE_WARN_MAX)
    if scale_uncertain:
        logger.info(
            "적재함 크기 추정이 흔들린다: scale=%.3f — 계산은 하되 품질을 낮춘다", frame.scale
        )

    points_truck = transform_to_truck_frame(points_camera, frame)

    plane_inlier_mask = np.zeros(len(points_camera), dtype=bool)
    for p in planes:
        if p.plane_type != PlaneType.UNKNOWN:
            plane_inlier_mask[p.inlier_indices] = True

    cargo_result = extract_cargo_points(
        points_truck, pixel_uv, owl_boxes, plane_inlier_mask,
        truck_width_m, truck_length_m, truck_height_m,
    )

    free_mask = ~plane_inlier_mask & ~cargo_result.source_mask
    free_points_truck = points_truck[free_mask]

    cbm_result = classify_and_compute_cbm(
        cargo_points_truck=cargo_result.points_truck,
        free_points_truck=free_points_truck,
        width_m=truck_width_m, length_m=truck_length_m, height_m=truck_height_m,
        safety_factor=safety_factor, voxel_edge_m=voxel_edge_m,
    )

    plane_residual_avg = float(np.mean([p.residual for p in planes])) if planes else 1.0

    quality_score = _compute_quality_score(
        intrinsics_confidence=K.confidence,
        structural_plane_count=structural_plane_count,
        plane_residual_avg=plane_residual_avg,
        scale_residual=frame.scale_residual,
        observed_voxel_ratio=cbm_result.observed_voxel_ratio,
        owl_coverage_ratio=cargo_result.owl_coverage_ratio,
        depth_outlier_ratio_value=outlier_ratio,
        blur_score=blur_score,
        exposure_score=exposure_score,
    )

    # scale 편차 페널티는 **초점거리를 신뢰할 수 있을 때만** 의미가 있다.
    #
    # EXIF가 없어 기본 초점거리를 쓴 사진은 scale이 1에서 벗어나는 게 당연하고, 그 사실은
    # 이미 intrinsics_confidence(가중치 0.13)와 scale_residual(0.09)로 두 번 반영돼 있다.
    # 여기서 또 곱하면 같은 사실로 세 번 깎인다. 실제로 멀쩡히 계산된 사진이
    # 0.647 -> 0.485로 떨어져 문턱(0.50)을 0.015 차이로 못 넘고 REJECTED가 됐다.
    #
    # 초점거리를 아는데도 상자가 배 이상 어긋났다면 그건 새로운 정보다. 그때만 깎는다.
    if scale_uncertain and K.confidence >= config.SCALE_PENALTY_MIN_INTRINSICS_CONFIDENCE:
        quality_score *= config.SCALE_WARN_QUALITY_FACTOR

    if quality_score >= config.QUALITY_ACCEPT_THRESHOLD:
        status = "ACCEPTED"
    elif quality_score >= config.QUALITY_LIMITED_THRESHOLD:
        status = "LIMITED"
    else:
        status = "REJECTED"

    return GeometryLiteResult(
        quality_status=status,
        quality_score=round(quality_score, 3),
        estimated_free_cbm=cbm_result.estimated_free_cbm,
        usable_free_cbm=cbm_result.usable_free_cbm,
        unknown_cbm=cbm_result.unknown_cbm,
        structural_plane_count=structural_plane_count,
        scale_correction_ratio=round(frame.scale, 4),
        plane_residual_avg=round(plane_residual_avg, 4),
        observed_voxel_ratio=cbm_result.observed_voxel_ratio,
        owl_coverage_ratio=round(cargo_result.owl_coverage_ratio, 3),
        depth_outlier_ratio=round(outlier_ratio, 4),
        voxel_edge_m=voxel_edge_m,
        safety_factor=safety_factor,
        occupied_cbm=cbm_result.occupied_cbm,
        observed_free_cbm=cbm_result.observed_free_cbm,
    )
