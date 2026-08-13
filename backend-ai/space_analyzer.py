"""Residual space analyzer — bootstrap stub.

Full pipeline (Depth Anything → YOLO-seg → 3d packing) lands in later phase.
Bootstrap returns a deterministic OpenCV-style placeholder so upload flow can wire up.
"""

from __future__ import annotations

from typing import Any


def analyze_image(image_bytes: bytes, filename: str = "upload.jpg") -> dict[str, Any]:
    logs = [
        "[1/3] depth: bootstrap stub (Depth Anything not loaded yet)",
        "[2/3] seg: bootstrap stub (YOLO-seg not loaded yet)",
        "[3/3] pack: volume-fusion placeholder",
        f"filename={filename}, bytes={len(image_bytes)}",
    ]
    # Deterministic mid-load placeholder — never random fill for demo honesty.
    remaining = 72.0
    occupied = 28.0
    return {
        "remaining_volume_percent": remaining,
        "occupied_volume_percent": occupied,
        "floor_empty_percent": 70.0,
        "height_utilization_percent": 30.0,
        "status": "여유공간 충분",
        "guide": "초기 구축 단계입니다. 공간 분석 엔진은 다음 단계에서 연결됩니다.",
        "reasoning": "bootstrap stub — OpenCV/Depth/YOLO not yet wired",
        "engine": "depth=stub | seg=stub | pack=volume-fusion",
        "pipeline": ["depth-anything", "yolov8-seg", "3d-packing"],
        "space_pipeline": ["depth-anything", "yolov8-seg", "3d-packing"],
        "logs": logs,
        "filename": filename,
    }
