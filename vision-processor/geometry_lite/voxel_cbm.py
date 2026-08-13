from dataclasses import dataclass
from enum import Enum

import numpy as np

VOXEL_EDGE_M = 0.20
VOXEL_VOLUME_M3 = VOXEL_EDGE_M**3  # 0.008


class VoxelState(str, Enum):
    FREE_VISIBLE = "FREE_VISIBLE"
    OCCUPIED = "OCCUPIED"
    STRUCTURE = "STRUCTURE"
    UNKNOWN = "UNKNOWN"


@dataclass
class VoxelCbmResult:
    estimated_free_cbm: float
    usable_free_cbm: float
    unknown_cbm: float
    occupied_cbm: float
    # 안전계수를 곱하기 **전**, 사진에 실제로 빈 공간으로 보인 부피.
    # usable_free_cbm = observed_free_cbm x safety_factor 라는 관계를 화면이 그대로
    # 설명할 수 있어야 해서 남긴다. 이 값이 없으면 사용자는 2.72라는 숫자가 어디서
    # 나왔는지 알 방법이 없다.
    observed_free_cbm: float
    observed_voxel_ratio: float  # 품질점수 입력: 전체 (x,y) column 중 관측된 column 비율
    grid_shape: tuple


def _column_top_grid(points_truck: np.ndarray, nx: int, ny: int, width_m: float, length_m: float) -> np.ndarray:
    """각 (x,y) column에서 관측된 점들의 최대 z를 기록한 2D 높이 격자. 관측 없으면 NaN."""
    grid = np.full((nx, ny), np.nan)
    if len(points_truck) == 0:
        return grid
    ix = np.clip((points_truck[:, 0] / width_m * nx).astype(int), 0, nx - 1)
    iy = np.clip((points_truck[:, 1] / length_m * ny).astype(int), 0, ny - 1)
    # NaN 초기화 격자이므로 fmax를 써야 한다. np.maximum은 NaN을 전파해 격자가 영구히 NaN으로 남는다.
    np.fmax.at(grid, (ix, iy), points_truck[:, 2])
    return grid


def _nearest_fill(grids: dict, nan_mask: np.ndarray) -> dict:
    """4.9 대표 추정값: 관측되지 않은 column을 최근접 관측 column 값으로 보간한다.
    여러 격자에 동일한 최근접 인덱스를 적용해 top height와 cargo 여부의 정합을 유지한다."""
    from scipy.ndimage import distance_transform_edt

    if not nan_mask.any() or nan_mask.all():
        return grids
    _, indices = distance_transform_edt(nan_mask, return_indices=True)
    return {key: grid[tuple(indices)] for key, grid in grids.items()}


def classify_and_compute_cbm(
    cargo_points_truck: np.ndarray,
    free_points_truck: np.ndarray,
    width_m: float,
    length_m: float,
    height_m: float,
    safety_factor: float = 0.70,
    voxel_edge_m: float = VOXEL_EDGE_M,
) -> VoxelCbmResult:
    """4.8/4.9: 20cm voxel 컬럼 분류 및 대표 추정값/보수적 사용가능값 CBM 계산.

    cargo_points_truck: 화물로 판정된 점(cargo_points.py 결과)
    free_points_truck: 화물도 구조 평면 inlier도 아닌, 카메라 ray가 표면까지 통과한 것으로
                        관측된 자유공간 점
    """
    voxel_volume = voxel_edge_m**3
    nx = max(1, int(np.ceil(width_m / voxel_edge_m)))
    ny = max(1, int(np.ceil(length_m / voxel_edge_m)))
    nz_total = max(1, int(np.ceil(height_m / voxel_edge_m)))

    cargo_top = _column_top_grid(cargo_points_truck, nx, ny, width_m, length_m)
    free_top = _column_top_grid(free_points_truck, nx, ny, width_m, length_m)

    observed_mask = ~np.isnan(cargo_top) | ~np.isnan(free_top)
    observed_voxel_ratio = float(observed_mask.sum() / (nx * ny)) if nx * ny > 0 else 0.0

    has_cargo = ~np.isnan(cargo_top)
    top_z = np.where(has_cargo, cargo_top, free_top)

    # 보수적 사용 가능값: 실제로 관측된 column만 사용(보간 없음)
    top_z_clamped = np.clip(np.nan_to_num(top_z, nan=0.0), 0.0, height_m)
    occupied_voxels_per_col = np.where(has_cargo, np.floor(top_z_clamped / voxel_edge_m), 0)
    free_visible_voxels_per_col = np.where(
        observed_mask, nz_total - np.ceil(top_z_clamped / voxel_edge_m), 0
    )
    free_visible_voxels_per_col = np.clip(free_visible_voxels_per_col, 0, nz_total)

    free_visible_voxels = int(free_visible_voxels_per_col.sum())
    occupied_voxels = int(occupied_voxels_per_col[has_cargo].sum())
    usable_free_cbm = free_visible_voxels * voxel_volume * safety_factor
    occupied_cbm = occupied_voxels * voxel_volume

    # 대표 추정값: 미관측 column을 최근접 관측 column 높이/화물여부로 보간
    is_cargo_flag = np.where(has_cargo, 1.0, np.where(~np.isnan(free_top), 0.0, np.nan))
    nan_mask = np.isnan(is_cargo_flag)
    filled = _nearest_fill({"top": top_z, "is_cargo": is_cargo_flag}, nan_mask)
    filled_top = np.clip(np.nan_to_num(filled["top"], nan=0.0), 0.0, height_m)
    filled_is_cargo = filled["is_cargo"] >= 0.5

    estimated_free_voxels_per_col = np.where(
        filled_is_cargo, nz_total - np.ceil(filled_top / voxel_edge_m), nz_total
    )
    estimated_free_voxels = int(np.clip(estimated_free_voxels_per_col, 0, nz_total).sum())
    estimated_free_cbm = estimated_free_voxels * voxel_volume

    total_cbm = width_m * length_m * height_m
    unknown_cbm = max(0.0, total_cbm - estimated_free_cbm - occupied_cbm)

    return VoxelCbmResult(
        estimated_free_cbm=round(estimated_free_cbm, 3),
        usable_free_cbm=round(usable_free_cbm, 3),
        unknown_cbm=round(unknown_cbm, 3),
        occupied_cbm=round(occupied_cbm, 3),
        observed_free_cbm=round(free_visible_voxels * voxel_volume, 3),
        observed_voxel_ratio=round(observed_voxel_ratio, 3),
        grid_shape=(nx, ny, nz_total),
    )
