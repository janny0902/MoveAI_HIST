"""Residual space analyzer — bootstrap stub.

Full pipeline (Depth Anything → YOLO-seg → 3d packing) lands in later phase.
Bootstrap returns a deterministic OpenCV-style placeholder so upload flow can wire up.
"""

from __future__ import annotations

from typing import Any


VEHICLE_PROFILES = [
    {"key": "1t", "label": "1톤", "tons": 1.0, "capacity_m3": 10.0},
    {"key": "2_5t", "label": "2.5톤", "tons": 2.5, "capacity_m3": 20.0},
    {"key": "3t", "label": "3톤", "tons": 3.0, "capacity_m3": 22.0},
    {"key": "5t", "label": "5톤", "tons": 5.0, "capacity_m3": 28.0},
    {"key": "8t", "label": "8톤", "tons": 8.0, "capacity_m3": 40.0},
    {"key": "11t", "label": "11톤", "tons": 11.0, "capacity_m3": 50.0},
    {"key": "18t", "label": "18톤", "tons": 18.0, "capacity_m3": 60.0},
    {"key": "25t", "label": "25톤", "tons": 25.0, "capacity_m3": 70.0},
]


def fill_by_vehicle(volume_m3: float) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for p in VEHICLE_PROFILES:
        cap = float(p["capacity_m3"])
        pct = round((volume_m3 / cap) * 10000.0) / 100.0 if cap > 0 else 0.0
        out[p["key"]] = {
            "label": p["label"],
            "tons": p["tons"],
            "capacityM3": cap,
            "capacity_m3": cap,
            "fillPercent": pct,
            "fill_percent": pct,
        }
    return out


def analyze_floor_cargo(image_bytes: bytes, filename: str = "") -> dict[str, Any]:
    """바닥 적재 더미 → 외접 치수(mm)·체적. 부트스트랩은 OpenCV 면적 추정."""
    import cv2
    import numpy as np

    logs = [
        "바닥 적재 더미 분석 시작",
        "파이프라인: OpenCV contour → 외접치수(mm) [bootstrap]",
        f"filename={filename}, bytes={len(image_bytes)}",
    ]
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        w_mm, d_mm, h_mm = 600, 400, 350
        logs.append("디코드 실패 — 기본 치수 사용")
        engine = "fallback-default"
    else:
        h, w = img.shape[:2]
        logs.append(f"디코드 완료: {w}x{h} px")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            c = max(contours, key=cv2.contourArea)
            x, y, bw, bh = cv2.boundingRect(c)
            # 픽셀 → mm 대략 스케일 (긴 변을 1200mm로 가정)
            scale = 1200.0 / max(bw, bh, 1)
            w_mm = int(max(200, min(2000, bw * scale)))
            d_mm = int(max(200, min(2000, bh * scale)))
            h_mm = int(max(150, min(1800, (w_mm + d_mm) * 0.35)))
            logs.append(f"외접박스 px={bw}x{bh} → mm={w_mm}x{d_mm}x{h_mm}")
            engine = "opencv-contour"
        else:
            w_mm, d_mm, h_mm = 600, 400, 350
            logs.append("컨투어 없음 — 기본 치수")
            engine = "fallback-default"

    volume_m3 = round((w_mm * d_mm * h_mm) / 1e9, 4)
    fills = fill_by_vehicle(volume_m3)
    fill11 = fills.get("11t", {}).get("fillPercent", 0)
    logs.append(f"[floor] 체적 {volume_m3} m³ · 11톤 점유 {fill11}%")
    return {
        "mode": "floor-stack",
        "box_width_mm": w_mm,
        "box_depth_mm": d_mm,
        "box_height_mm": h_mm,
        "width_mm": w_mm,
        "depth_mm": d_mm,
        "height_mm": h_mm,
        "volume_m3": volume_m3,
        "volume_cbm": volume_m3,
        "fill_percent_of_11t": fill11,
        "fill_by_vehicle": fills,
        "vehicle_profiles": VEHICLE_PROFILES,
        "engine": engine,
        "pipeline": ["opencv-contour", "floor-bbox-scale"],
        "guide": f"추정 치수 {w_mm}×{d_mm}×{h_mm} mm · {volume_m3} CBM",
        "status": "ok",
        "logs": logs,
    }


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
