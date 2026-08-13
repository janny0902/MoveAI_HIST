from typing import Tuple

import numpy as np
import open3d as o3d

from .camera import Intrinsics


def depth_to_camera_points(
    depth_m: np.ndarray, K: Intrinsics, depth_type: str = "z_depth"
) -> Tuple[np.ndarray, np.ndarray]:
    """4.4: P_camera(u,v) = D(u,v) x inverse(K) x [u,v,1]^T

    체크포인트 출력이 z-depth인지 ray distance인지에 따라 unprojection 식이 달라지므로
    depth_type으로 명시적으로 고정한다. Depth Anything V2 Metric 계열은 z-depth를 출력한다.

    Returns:
        points_camera: 유효(depth>0) 픽셀만의 Nx3 카메라 좌표
        pixel_uv: 위 점들과 1:1 대응하는 Nx2 원본 픽셀 좌표(cargo_points.py의 OWL box 매칭에 사용)
    """
    h, w = depth_m.shape
    us, vs = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))

    x_norm = (us - K.cx) / K.fx
    y_norm = (vs - K.cy) / K.fy

    if depth_type == "z_depth":
        z = depth_m
    elif depth_type == "ray_distance":
        ray_norm = np.sqrt(x_norm**2 + y_norm**2 + 1.0)
        z = depth_m / ray_norm
    else:
        raise ValueError(f"unknown depth_type: {depth_type}")

    x = x_norm * z
    y = y_norm * z

    valid = depth_m > 0
    points = np.stack([x[valid], y[valid], z[valid]], axis=-1)
    pixel_uv = np.stack([us[valid], vs[valid]], axis=-1)
    return points, pixel_uv


def depth_outlier_ratio(depth_m: np.ndarray, max_plausible_m: float) -> float:
    """4.10 품질점수 입력: 신뢰할 수 없는 depth 픽셀의 비율(0-1, 낮을수록 좋음).

    세 종류를 outlier로 본다.
      1) 비유효값: NaN/inf 또는 0 이하 — unprojection 자체가 불가능하다.
      2) 물리적 범위 밖: 화물칸 안에서 나올 수 없는 거리. 문 밖 배경이 잡히면 여기 걸린다.
      3) 통계적 이상치: median에서 MAD 기준 3 스케일 이상 떨어진 값.
    MAD를 쓰는 이유는 depth map 자체가 이미 오염됐을 수 있어 표준편차가 이상치에 끌려가기 때문이다.
    """
    total = depth_m.size
    if total == 0:
        return 1.0

    invalid = ~np.isfinite(depth_m) | (depth_m <= 0)
    out_of_range = np.zeros_like(invalid)
    if max_plausible_m > 0:
        out_of_range = np.isfinite(depth_m) & (depth_m > max_plausible_m)

    outlier = invalid | out_of_range

    valid_values = depth_m[np.isfinite(depth_m) & (depth_m > 0)]
    if valid_values.size > 0:
        median = float(np.median(valid_values))
        mad = float(np.median(np.abs(valid_values - median)))
        if mad > 0:
            # 1.4826 * MAD가 정규분포에서 표준편차에 해당한다.
            threshold = 3.0 * 1.4826 * mad
            statistical = np.isfinite(depth_m) & (depth_m > 0) & (np.abs(depth_m - median) > threshold)
            outlier = outlier | statistical

    return float(np.count_nonzero(outlier) / total)


def to_open3d_point_cloud(points_camera: np.ndarray) -> o3d.geometry.PointCloud:
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points_camera)
    return pcd
