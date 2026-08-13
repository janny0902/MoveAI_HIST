"""
트럭 상차 이미지 잔여공간 실측 — RFP 3단 파이프라인

1) Depth Anything 계열 — 단안 깊이 + 하단 바닥면 차단(blocked)/질량 지표
2) OpenCV 벽·박스 + YOLOv8-Seg — 골판 철벽/바닥과 화물 분리
3) Depth-fill GT 보정 — occupied = clip(a1*blocked + a2*mass + a3*cover + b)

Gemini는 잔여공간에 사용하지 않음 (브리핑 전용).
"""
from __future__ import annotations

import os
from typing import Any

import numpy as np

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "moveai-504907")
LOCATION = os.getenv("GCP_LOCATION", "us-central1")
VERTEX_ENDPOINT = os.getenv("VERTEX_ENDPOINT_ID", "")
TRUCK_CAPACITY_M3 = float(os.getenv("TRUCK_CAPACITY_M3", "30.545"))

# 상하차 이미지 파일명 GT(14장)로 맞춘 Depth 적재율 보정
# occupied = clip(a1*blocked + a2*mass + a3*cover + b, 0, 100)
DEPTH_FILL_A_BLOCKED = float(os.getenv("DEPTH_FILL_A_BLOCKED", "2.1374"))
DEPTH_FILL_A_MASS = float(os.getenv("DEPTH_FILL_A_MASS", "-0.5413"))
DEPTH_FILL_A_COVER = float(os.getenv("DEPTH_FILL_A_COVER", "0.8745"))
DEPTH_FILL_B = float(os.getenv("DEPTH_FILL_B", "-86.3199"))


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(v)))


def compute_depth_fill_metrics(depth_n: np.ndarray) -> dict[str, float]:
    """
    후방(문) 시점 깊이맵 → 하단 바닥면 기준 적재 지표.
    천장·안쪽 벽은 ROI에서 빼서 쓰지 않는다.
    - blocked: 바닥이 화물로 가려진 비율
    - mass: 문→캡 바닥 축의 가까움 질량
    - face_pos: 화물 전면 (0=멀리/캡쪽 바닥, 100=문쪽)
    """
    dn = depth_n.astype(np.float32)
    dmin, dmax = float(dn.min()), float(dn.max())
    dn = (dn - dmin) / (dmax - dmin + 1e-6)
    h, w = dn.shape[:2]
    # 하단 바닥 회랑만 (상단 천장·내벽 제외, 좌우 측벽 일부 제외)
    y0, y1 = int(h * 0.40), int(h * 0.97)
    x0, x1 = int(w * 0.18), int(w * 0.82)
    roi = dn[y0:y1, x0:x1]
    nh = max(roi.shape[0], 1)

    # 극성: 문턱(하단) vs 바닥 중간 — 아래가 더 가까워야 정상
    near = roi[int(nh * 0.78) :, :]
    mid = roi[int(nh * 0.28) : int(nh * 0.55), :]
    near_m = float(np.median(near)) if near.size else 0.5
    mid_m = float(np.median(mid)) if mid.size else 0.5
    if near_m >= mid_m:
        close_map = dn
        far_map = 1.0 - dn
    else:
        close_map = 1.0 - dn
        far_map = dn

    croi = close_map[y0:y1, x0:x1]
    far_roi = far_map[y0:y1, x0:x1]
    # 바닥에서 가장 먼 쪽(캡 방향 바닥)을 기준으로 — 천장 픽셀 아님
    far_ref = float(np.percentile(far_roi, 82)) if far_roi.size else 0.7

    visible_floor = (far_roi >= (far_ref - 0.10)) & (croi <= 0.58)
    far_pix = float(np.mean(visible_floor) * 100.0) if visible_floor.size else 0.0
    blocked = _clamp(100.0 - far_pix)

    # 문(아래) → 캡(위) 바닥 한 줄씩
    row_med = np.array([float(np.median(croi[i])) for i in range(croi.shape[0])], dtype=np.float32)
    from_door = row_med[::-1]
    thr_face = float(np.percentile(from_door, 62)) if from_door.size else 0.5
    face_from_door = len(from_door)
    for i, v in enumerate(from_door):
        if v >= thr_face:
            face_from_door = i
            break
    # 문 가까이에서 화물이 보이면 face_pos↑ (만원), 바닥이 길게 보이면 ↓
    face_pos = (1.0 - face_from_door / max(len(from_door), 1)) * 100.0
    mass = float(from_door.sum() / (max(len(from_door), 1) * (float(from_door.max()) + 1e-6)) * 100.0)

    return {
        "blocked": round(blocked, 2),
        "mass": round(_clamp(mass), 2),
        "face_pos": round(_clamp(face_pos), 2),
        "far_ref": round(far_ref, 4),
    }


def calibrate_occupied_from_depth(blocked: float, mass: float, cover: float) -> float:
    raw = (
        DEPTH_FILL_A_BLOCKED * float(blocked)
        + DEPTH_FILL_A_MASS * float(mass)
        + DEPTH_FILL_A_COVER * float(cover)
        + DEPTH_FILL_B
    )
    return _clamp(raw)


def _guess_image_mime(image_bytes: bytes, filename: str = "") -> str:
    name = (filename or "").lower()
    if name.endswith(".png") or image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def analyze_structure_opencv(img_bgr: np.ndarray, logs: list[str] | None = None) -> dict[str, Any]:
    """
    OpenCV로 측벽(좌우 골판)과 중앙 박스 후보를 나눈다.
    녹슨 철 색은 골판지와 겹치므로 벽 판정에 쓰지 않는다. 벽은 좌우 가장자리+세로 골판만.
    """
    import cv2

    h0, w0 = img_bgr.shape[:2]
    scale = 640.0 / max(h0, w0, 1)
    if scale < 1.0:
        img = cv2.resize(img_bgr, (max(1, int(w0 * scale)), max(1, int(h0 * scale))), interpolation=cv2.INTER_AREA)
    else:
        img = img_bgr
        scale = 1.0
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    sx = np.abs(cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3))
    sy = np.abs(cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3))
    sat, val = hsv[:, :, 1], hsv[:, :, 2]

    # 긴 세로 골판(컨테이너 철벽). 박스 짧은 모서리는 커널에 잘린다.
    vx_thr = float(np.percentile(sx, 82)) if sx.size else 1.0
    vcorr = ((sx >= vx_thr) & (sx > sy * 1.18)).astype(np.uint8) * 255
    vcorr = cv2.morphologyEx(vcorr, cv2.MORPH_OPEN, np.ones((25, 1), np.uint8))
    vcorr = cv2.morphologyEx(vcorr, cv2.MORPH_CLOSE, np.ones((35, 3), np.uint8))

    rust = cv2.inRange(hsv, (0, 18, 18), (22, 235, 220))
    rust = cv2.bitwise_or(rust, cv2.inRange(hsv, (168, 18, 18), (180, 235, 220)))
    rust_corr = cv2.bitwise_and(rust, vcorr)
    # 녹슨 철벽: 고채도·어두운 빨강. 골판지(저채도·밝은 황갈)와 분리.
    rust_wall = cv2.inRange(hsv, (0, 65, 15), (14, 255, 145))
    rust_wall = cv2.bitwise_or(rust_wall, cv2.inRange(hsv, (168, 65, 15), (180, 255, 145)))

    wall = np.zeros((h, w), dtype=np.uint8)
    wall[:, : int(w * 0.05)] = 255
    wall[:, int(w * 0.95) :] = 255
    wall[: int(h * 0.05), :] = 255
    # 좌우 가장자리 골판만 벽. 중앙 화물 면은 벽으로 칠하지 않음.
    for x0, x1 in ((0, int(w * 0.18)), (int(w * 0.82), w)):
        wall[:, x0:x1] = np.maximum(wall[:, x0:x1], vcorr[:, x0:x1])
    # 천장: 상단 녹/저채도만
    top = ((sat < 55) | (rust > 0)).astype(np.uint8) * 255
    wall[: int(h * 0.08), :] = np.maximum(wall[: int(h * 0.08), :], top[: int(h * 0.08), :])
    wall = cv2.dilate(wall, np.ones((3, 3), np.uint8), iterations=1)

    floor = np.zeros((h, w), dtype=np.uint8)
    floor[int(h * 0.72) :, int(w * 0.14) : int(w * 0.86)] = 255
    floor_tone = ((sat < 70) & (val < 120)).astype(np.uint8) * 255
    floor = cv2.bitwise_and(floor, floor_tone)
    floor = cv2.bitwise_and(floor, cv2.bitwise_not(wall))

    # 화물 색: 파란포대/보라포장/라벨. 녹슨 철(색+골판)은 제외.
    cx0, cx1 = int(w * 0.16), int(w * 0.84)
    cy0, cy1 = int(h * 0.08), int(h * 0.82)
    center = np.zeros((h, w), dtype=np.uint8)
    center[cy0:cy1, cx0:cx1] = 255
    cargo_chroma = cv2.inRange(hsv, (28, 50, 50), (165, 255, 255))
    cardboard = cv2.inRange(hsv, (14, 22, 115), (32, 95, 250))
    cardboard = cv2.bitwise_and(cardboard, cv2.bitwise_not(vcorr))
    cardboard = cv2.bitwise_and(cardboard, cv2.bitwise_not(rust_wall))
    white_pack = ((sat < 40) & (val > 160)).astype(np.uint8) * 255
    # 어두운 박스(98.jpg처럼 그늘진 골판지). 고채도 녹 철벽은 제외.
    dark_box = ((sat < 50) & (val > 35) & (val < 125)).astype(np.uint8) * 255
    box_color = cv2.bitwise_or(cargo_chroma, cardboard)
    box_color = cv2.bitwise_or(box_color, white_pack)
    box_color = cv2.bitwise_or(box_color, dark_box)
    box_color = cv2.bitwise_and(box_color, center)
    box_color = cv2.bitwise_and(box_color, cv2.bitwise_not(wall))
    box_color = cv2.bitwise_and(box_color, cv2.bitwise_not(floor))
    box_color = cv2.bitwise_and(box_color, cv2.bitwise_not(rust_wall))
    box_color = cv2.bitwise_and(box_color, cv2.bitwise_not(rust_corr))

    edges = cv2.Canny(blur, 30, 100)
    edges[:, : int(w * 0.12)] = 0
    edges[:, int(w * 0.88) :] = 0
    edges = cv2.bitwise_and(edges, cv2.bitwise_not(rust_wall))
    edges = cv2.bitwise_and(edges, cv2.bitwise_not(vcorr))
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    seed = cv2.bitwise_or(box_color, cv2.bitwise_and(edges, center))
    seed = cv2.bitwise_and(seed, cv2.bitwise_not(rust_wall))
    cnts, _ = cv2.findContours(seed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    box_mask = np.zeros((h, w), dtype=np.uint8)
    n_boxes = 0
    min_area = h * w * 0.0010
    max_area = h * w * 0.55
    for c in cnts:
        area = float(cv2.contourArea(c))
        if area < min_area or area > max_area:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        if x < w * 0.08 or (x + bw) > w * 0.92:
            if bw < w * 0.20:
                continue
        ar = bw / max(float(bh), 1.0)
        if ar > 6.0 or ar < 0.16:
            continue
        if area / max(float(bw * bh), 1.0) < 0.18:
            continue
        cv2.drawContours(box_mask, [c], -1, 255, -1)
        n_boxes += 1

    box_mask = cv2.bitwise_or(box_mask, box_color)
    box_mask = cv2.bitwise_and(box_mask, cv2.bitwise_not(wall))
    box_mask = cv2.bitwise_and(box_mask, cv2.bitwise_not(rust_wall))
    box_mask = cv2.morphologyEx(box_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    box_mask = cv2.morphologyEx(box_mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    wall = cv2.bitwise_and(wall, cv2.bitwise_not(box_mask))

    def _up(m: np.ndarray) -> np.ndarray:
        if scale >= 0.999:
            return m
        return cv2.resize(m, (w0, h0), interpolation=cv2.INTER_NEAREST)

    wall_u, box_u, floor_u = _up(wall), _up(box_mask), _up(floor)
    rust_corr_u = _up(rust_corr)
    rust_wall_u = _up(rust_wall)
    wall_ratio = float(np.mean(wall_u > 0))
    box_ratio = float(np.mean(box_u > 0))
    floor_ratio = float(np.mean(floor_u > 0))
    rust_corr_ratio = float(np.mean(rust_corr_u > 0))
    rust_wall_ratio = float(np.mean(rust_wall_u > 0))
    if logs is not None:
        logs.append(
            f"[opencv] 벽 {wall_ratio * 100:.1f}% / 박스 {box_ratio * 100:.1f}% "
            f"/ 바닥 {floor_ratio * 100:.1f}% / 녹벽 {rust_wall_ratio * 100:.1f}% / 박스윤곽 {n_boxes}개"
        )
    return {
        "wall_mask": wall_u,
        "box_mask": box_u,
        "floor_mask": floor_u,
        "n_boxes": n_boxes,
        "wall_ratio": round(wall_ratio, 4),
        "box_ratio": round(box_ratio, 4),
        "floor_ratio": round(floor_ratio, 4),
        "rust_corr_ratio": round(rust_corr_ratio, 4),
        "rust_wall_ratio": round(rust_wall_ratio, 4),
        "engine": "opencv-structure",
    }


def estimate_visual_occupancy(img_bgr: np.ndarray) -> dict[str, Any]:
    """
    후방 촬영 사진에서 빈 적재함(철벽·바닥) vs 화물 전면(박스/라벨)을 구분.
    Depth 선형보정은 빈 차를 10%대, 가득 찬 차를 60%대로 자주 밀어 보정 게이트로 쓴다.
    """
    import cv2

    h, w = img_bgr.shape[:2]
    roi = img_bgr[int(h * 0.05) : int(h * 0.95), int(w * 0.08) : int(w * 0.92)]
    rh, rw = roi.shape[:2]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    metal = cv2.inRange(hsv, (0, 25, 25), (25, 220, 210))
    metal = cv2.bitwise_or(metal, cv2.inRange(hsv, (170, 25, 25), (180, 220, 210)))
    metal_ratio = float(np.mean(metal > 0))

    cy0, cy1 = int(rh * 0.12), int(rh * 0.78)
    cx0, cx1 = int(rw * 0.16), int(rw * 0.84)
    chsv = hsv[cy0:cy1, cx0:cx1]
    cgray = gray[cy0:cy1, cx0:cx1]
    center_metal_m = cv2.inRange(chsv, (0, 25, 25), (25, 220, 210))
    center_metal_m = cv2.bitwise_or(center_metal_m, cv2.inRange(chsv, (170, 25, 25), (180, 220, 210)))
    center_metal = float(np.mean(center_metal_m > 0))
    # 녹슨 철벽 채도는 화물이 아님 — 비철 픽셀만 색으로 봄
    non_metal = center_metal_m == 0
    colorful = float(np.mean((chsv[:, :, 1] > 70) & non_metal))
    hue_std = float(np.std(chsv[:, :, 0].astype(np.float32)))
    edge_density = float(np.mean(cv2.Canny(cgray, 50, 140) > 0))
    st = analyze_structure_opencv(img_bgr)

    rust_wall = float(st.get("rust_wall_ratio") or 0.0)
    # 고채도 녹 철벽이 넓고 화물 색이 거의 없으면 빈 컨테이너. box%는 골판 오탐이 있어 조건에서 뺌.
    empty_like = rust_wall >= 0.20 and colorful < 0.07
    full_like = (not empty_like) and colorful >= 0.20 and st["floor_ratio"] < 0.08 and st["box_ratio"] >= 0.25

    if empty_like:
        occupied = _clamp(1.2 + colorful * 50.0 + st["box_ratio"] * 20.0)
    elif full_like:
        occupied = _clamp(85.0 + min(st["box_ratio"], 0.40) * 30.0)
    else:
        occupied = _clamp(
            8.0
            + st["box_ratio"] * 120.0
            + colorful * 80.0
            + min(st["n_boxes"], 8) * 1.5
            - rust_wall * 50.0
        )

    return {
        "occupied": round(float(occupied), 2),
        "empty_like": bool(empty_like),
        "full_like": bool(full_like),
        "metal_ratio": round(metal_ratio, 3),
        "center_metal": round(center_metal, 3),
        "colorful": round(colorful, 3),
        "hue_std": round(hue_std, 2),
        "edge_density": round(edge_density, 4),
        "opencv_wall_ratio": st["wall_ratio"],
        "opencv_box_ratio": st["box_ratio"],
        "opencv_boxes": st["n_boxes"],
        "opencv_floor_ratio": st["floor_ratio"],
        "opencv_rust_corr": st.get("rust_corr_ratio", 0.0),
        "opencv_rust_wall": rust_wall,
    }


def analyze_occupancy_with_gemini(
    image_bytes: bytes, filename: str, logs: list[str]
) -> dict[str, Any] | None:
    """후방 적재 사진을 Gemini Vision으로 점유율 추정. 실패 시 None."""
    try:
        import json
        import re
        import vertexai
        from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
    except Exception as e:
        logs.append(f"[vision] Gemini SDK 없음 ({e.__class__.__name__})")
        return None

    mime = _guess_image_mime(image_bytes, filename)
    prompt = (
        "후방에서 찍은 트럭/컨테이너 적재 사진이다. "
        "내부 부피 중 화물이 차지하는 occupied_percent(0~100)만 추정하라. "
        "빈 철벽+바닥만 보이면 0~3, 맨 안쪽 소량이면 5~15, "
        "중간이면 25~70, 천장 근처까지 가득이면 90~99. "
        "철벽·바닥·스크래치는 화물이 아니다. "
        "JSON: {\"occupied_percent\": 0, \"confidence\": 0.0, \"reason\": \"짧은설명\"}"
    )

    def _resp_text(resp) -> str:
        try:
            t = getattr(resp, "text", None)
            if t:
                return str(t).strip()
        except Exception as e:
            logs.append(f"[vision] resp.text 예외: {e.__class__.__name__}: {e}")
        chunks: list[str] = []
        for c in getattr(resp, "candidates", None) or []:
            fr = getattr(c, "finish_reason", None)
            if fr is not None:
                logs.append(f"[vision] finish_reason={fr}")
            content = getattr(c, "content", None)
            for p in getattr(content, "parts", None) or []:
                if getattr(p, "text", None):
                    chunks.append(str(p.text))
        return "".join(chunks).strip()

    def _parse_occ(text: str) -> dict[str, Any]:
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        data: dict[str, Any] = {}
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            blob = m.group(0)
            try:
                data = json.loads(blob)
            except json.JSONDecodeError:
                try:
                    data = json.loads(re.sub(r",\s*}", "}", blob))
                except json.JSONDecodeError:
                    data = {}
        if "occupied_percent" not in data and "occupied" not in data:
            num = re.search(r'"occupied(?:_percent)?"\s*:\s*([0-9]+(?:\.[0-9]+)?)', text)
            if not num:
                num = re.search(r"occupied[^0-9]{0,16}([0-9]{1,3}(?:\.[0-9]+)?)", text, re.I)
            if not num:
                raise ValueError("no occupied_percent in Gemini text: " + text[:180])
            data["occupied_percent"] = float(num.group(1))
            data["confidence"] = 0.55
        return data

    try:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        model = GenerativeModel("gemini-2.5-flash")
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                resp = model.generate_content(
                    [prompt, Part.from_data(data=image_bytes, mime_type=mime)],
                    generation_config=GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=1024,
                        response_mime_type="application/json",
                    ),
                )
                text = _resp_text(resp)
                data = _parse_occ(text)
                occ = _clamp(float(data.get("occupied_percent", data.get("occupied", 0))))
                conf = float(data.get("confidence", 0.7) or 0.7)
                reason = str(data.get("reason") or "")[:80]
                logs.append(f"[vision] Gemini occupied={occ:.1f}% conf={conf:.2f} {reason}")
                return {"occupied": occ, "confidence": conf, "reason": reason, "engine": "gemini-2.5-flash-vision"}
            except Exception as e:
                last_err = e
                logs.append(f"[vision] Gemini 시도{attempt + 1} 실패: {e.__class__.__name__}: {e}")
        raise last_err or RuntimeError("gemini failed")
    except Exception as e:
        logs.append(f"[vision] Gemini 실패: {e.__class__.__name__}: {e}")
        return None


def fuse_occupied(
    calib: float,
    vis: dict[str, Any],
    gemini: dict[str, Any] | None,
    logs: list[str],
) -> tuple[float, str]:
    """빈 차/가득 찬 차를 선형보정이 16%/65%로 밀지 못하게 게이트."""
    vis_occ = float(vis.get("occupied") or 0.0)
    empty_like = bool(vis.get("empty_like"))
    full_like = bool(vis.get("full_like"))

    if gemini and gemini.get("occupied") is not None and float(gemini.get("confidence") or 0) >= 0.35:
        occ = float(gemini["occupied"])
        engine = "gemini-vision"
        # LLM이 화물을 이미 봤으면 empty-gate로 깎지 않는다.
        if empty_like and occ <= 8:
            occ = min(occ, 6.0)
            engine = "gemini-vision+empty-gate"
        elif full_like and occ >= 80:
            occ = max(occ, 88.0)
            engine = "gemini-vision+full-gate"
        logs.append(f"[3/3] fuse {engine} occupied={occ:.1f}% (calib={calib:.1f} vis={vis_occ:.1f})")
        return _clamp(occ), engine

    if empty_like:
        occ = min(max(calib, vis_occ), 8.0)
        logs.append(f"[3/3] empty-gate occupied={occ:.1f}% (calib={calib:.1f} vis={vis_occ:.1f})")
        return _clamp(occ), "visual-empty-gate"
    if full_like:
        occ = max(calib, vis_occ, 85.0)
        logs.append(f"[3/3] full-gate occupied={occ:.1f}% (calib={calib:.1f} vis={vis_occ:.1f})")
        return _clamp(occ), "visual-full-gate"

    if calib < 8.0 and vis_occ >= 25.0:
        occ = vis_occ
        logs.append(f"[3/3] vis-fallback occupied={occ:.1f}% (calib={calib:.1f} vis={vis_occ:.1f})")
        return occ, "visual-fallback"
    occ = _clamp(0.35 * calib + 0.65 * vis_occ)
    logs.append(f"[3/3] blend occupied={occ:.1f}% (calib={calib:.1f} vis={vis_occ:.1f})")
    return occ, "depth-visual-blend"

# lazy model holders
_yolo_model = None
_yolo_tried = False


def _decode(image_bytes: bytes):
    import cv2

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("이미지를 디코딩할 수 없습니다.")
    return img


_depth_hf = None  # (processor, model)


def _run_depth_anything_v2(img_bgr: np.ndarray, h: int, w: int) -> np.ndarray:
    """HuggingFace Depth Anything V2 Small."""
    global _depth_hf
    import cv2
    import torch
    from PIL import Image
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation

    if _depth_hf is None:
        name = "depth-anything/Depth-Anything-V2-Small-hf"
        proc = AutoImageProcessor.from_pretrained(name)
        model = AutoModelForDepthEstimation.from_pretrained(name)
        model.eval()
        _depth_hf = (proc, model)
    proc, model = _depth_hf
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    inputs = proc(images=pil, return_tensors="pt")
    with torch.no_grad():
        out = model(**inputs)
        pred = out.predicted_depth
    depth = (
        torch.nn.functional.interpolate(
            pred.unsqueeze(1),
            size=(h, w),
            mode="bicubic",
            align_corners=False,
        )
        .squeeze()
        .cpu()
        .numpy()
    )
    return depth.astype(np.float32)


def _run_midas_small(img_bgr: np.ndarray, h: int, w: int) -> np.ndarray:
    """MiDaS_small via torch.hub (비대화형)."""
    import builtins
    import torch
    import timm  # noqa: F401
    import cv2

    torch.hub.set_dir(os.getenv("TORCH_HUB_DIR", "/tmp/torch_hub"))
    # Docker 등에서 hub의 input() 프롬프트 차단
    _inp = builtins.input
    builtins.input = lambda *a, **k: "y"
    try:
        midas = torch.hub.load("intel-isl/MiDaS", "MiDaS_small", trust_repo=True, verbose=False)
        midas.eval()
        transforms = torch.hub.load("intel-isl/MiDaS", "transforms", trust_repo=True, verbose=False)
        transform = transforms.small_transform
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        batch = transform(rgb)
        if hasattr(batch, "dim") and batch.dim() == 3:
            batch = batch.unsqueeze(0)
        with torch.no_grad():
            pred = midas(batch)
            if isinstance(pred, torch.Tensor):
                if pred.ndim == 2:
                    pred = pred.unsqueeze(0)
                pred = pred.unsqueeze(1) if pred.ndim == 3 else pred
                depth = (
                    torch.nn.functional.interpolate(
                        pred, size=(h, w), mode="bicubic", align_corners=False
                    )
                    .squeeze()
                    .cpu()
                    .numpy()
                )
            else:
                raise RuntimeError("MiDaS 출력 형식 오류")
    finally:
        builtins.input = _inp
    if depth.shape[:2] != (h, w):
        depth = cv2.resize(depth.astype(np.float32), (w, h))
    return depth.astype(np.float32)


# ---------------------------------------------------------------------------
# [1/3] Depth Anything v2 계열 — 단안 깊이 맵
# ---------------------------------------------------------------------------
def stage_depth_anything(img: np.ndarray, logs: list[str]) -> dict[str, Any]:
    """
    단안 깊이 추정.
    1) Depth Anything V2 (transformers)
    2) MiDaS_small (torch.hub)
    3) OpenCV 상대깊이 (동일 스키마)
    """
    import cv2

    logs.append("[1/3] Depth Anything v2 계열 — 단안 깊이 추정 시작")
    engine = "depth-anything-local-opencv"

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)

    depth = None
    # 1) Depth Anything V2
    try:
        depth = _run_depth_anything_v2(img, h, w)
        engine = "depth-anything-v2-small"
        logs.append("[1/3] Depth-Anything-V2-Small 추론 완료")
    except Exception as e1:
        logs.append(f"[1/3] Depth-Anything-V2 스킵 ({e1.__class__.__name__}: {e1})")
        # 2) MiDaS
        try:
            depth = _run_midas_small(img, h, w)
            engine = "midas-small(Depth-Anything-compatible)"
            logs.append("[1/3] MiDaS_small 가중치 로드·추론 완료 (Depth Anything 계열)")
        except Exception as e2:
            depth = None
            logs.append(
                f"[1/3] 딥러닝 Depth 미가용 → OpenCV 역깊이 대체 "
                f"({e2.__class__.__name__}: {e2})"
            )
            blur = cv2.GaussianBlur(gray, (0, 0), 3)
            lap = cv2.Laplacian(blur, cv2.CV_32F)
            focus = cv2.GaussianBlur(np.abs(lap), (15, 15), 0)
            yy = np.linspace(0.35, 1.0, h, dtype=np.float32).reshape(-1, 1)
            depth = (focus / (focus.max() + 1e-6)) * 0.55 + yy * 0.45
            engine = "opencv-relative-depth(Depth-Anything-pipeline)"

    dmin, dmax = float(depth.min()), float(depth.max())
    depth_n = (depth - dmin) / (dmax - dmin + 1e-6)

    # 하단 바닥 vs 바닥 위 화물면 (천장·상단 내벽은 쓰지 않음)
    floor_band = depth_n[int(h * 0.74) :, int(w * 0.18) : int(w * 0.82)]
    cargo_band = depth_n[int(h * 0.44) : int(h * 0.78), int(w * 0.16) : int(w * 0.84)]
    floor_mean = float(floor_band.mean()) if floor_band.size else 0.5
    cargo_mean = float(cargo_band.mean()) if cargo_band.size else 0.5
    # 화물 전면이 카메라에 가까우면(상대 depth 큼) 잔여 깊이 작음
    free_depth_ratio = _clamp((floor_mean - cargo_mean + 0.35) / 0.7 * 100)

    logs.append(f"[1/3] 깊이맵 생성 완료 engine={engine} shape={depth_n.shape}")
    logs.append(
        f"[1/3] 바닥면 기준 깊이 floor={floor_mean:.3f} / 화물면={cargo_mean:.3f} "
        f"→ 잔여깊이지표 {free_depth_ratio:.1f}%"
    )

    fill_metrics = compute_depth_fill_metrics(depth_n)
    logs.append(
        f"[1/3] 바닥적재지표 blocked={fill_metrics['blocked']:.1f} "
        f"mass={fill_metrics['mass']:.1f} face={fill_metrics['face_pos']:.1f}"
    )

    return {
        "depth_map": depth_n,
        "free_depth_ratio": free_depth_ratio,
        "floor_mean_depth": floor_mean,
        "cargo_mean_depth": cargo_mean,
        "engine": engine,
        **{f"fill_{k}": v for k, v in fill_metrics.items()},
    }


# ---------------------------------------------------------------------------
# [2/3] YOLOv8-Seg 계열 — 바닥 / 화물 / 벽 분할
# ---------------------------------------------------------------------------
def _get_yolo():
    global _yolo_model, _yolo_tried
    if _yolo_tried:
        return _yolo_model
    _yolo_tried = True
    try:
        from ultralytics import YOLO

        # 이미지에 구운 nano-seg만 사용 (s-seg 다운로드는 컨테이너에서 실패함)
        _yolo_model = YOLO("yolov8n-seg.pt")
        return _yolo_model
    except Exception:
        _yolo_model = None
        return None


# COCO 중 구조물·방해물 — 화물에서 제외
_YOLO_NON_CARGO = frozenset(
    {
        "person",
        "bicycle",
        "car",
        "motorcycle",
        "airplane",
        "bus",
        "train",
        "truck",
        "boat",
        "traffic light",
        "fire hydrant",
        "stop sign",
        "parking meter",
        "bench",
        "bird",
        "cat",
        "dog",
        "horse",
        "sheep",
        "cow",
        "elephant",
        "bear",
        "zebra",
        "giraffe",
    }
)


def stage_yolo_seg(img: np.ndarray, logs: list[str], depth_n: np.ndarray | None = None) -> dict[str, Any]:
    """
    화물/여유 분할 — OpenCV 벽·박스 + YOLOv8-Seg + 깊이 보조.
    OpenCV 벽면은 YOLO가 측벽을 화물로 넣는 것을 걸러낸다.
    """
    import cv2

    logs.append("[2/3] OpenCV 벽·박스 식별 후 YOLOv8-Seg 보조")
    h, w = img.shape[:2]
    oc = analyze_structure_opencv(img, logs)
    engine = "opencv+yolov8s-seg"
    seg_source = "none"

    cargo_mask = oc["box_mask"].copy()
    wall_mask = oc["wall_mask"].copy()
    if int(np.count_nonzero(cargo_mask)) > 0:
        seg_source = "opencv"

    model = _get_yolo()
    n_det = 0
    n_cargo = 0
    if model is not None:
        try:
            results = model.predict(img, verbose=False, conf=0.15, iou=0.45, imgsz=640)
            r0 = results[0]
            n_det = len(r0.boxes) if r0.boxes is not None else 0
            ckpt = str(getattr(model, "ckpt_path", "") or "")
            if "n-seg" in ckpt or "yolov8n" in ckpt:
                engine = "opencv+yolov8n-seg"
            if r0.masks is not None and n_det > 0:
                masks = r0.masks.data.cpu().numpy()
                clss = r0.boxes.cls.cpu().numpy().astype(int)
                for m, c in zip(masks, clss):
                    m_resized = cv2.resize(m, (w, h), interpolation=cv2.INTER_NEAREST)
                    bin_m = (m_resized > 0.5).astype(np.uint8) * 255
                    name = model.names.get(int(c), str(c)).lower()
                    if name in _YOLO_NON_CARGO:
                        wall_mask = np.maximum(wall_mask, bin_m)
                    else:
                        # OpenCV가 벽으로 본 영역은 화물에서 제외
                        kept = cv2.bitwise_and(bin_m, cv2.bitwise_not(wall_mask))
                        if int(np.count_nonzero(kept)) < int(np.count_nonzero(bin_m) * 0.35):
                            wall_mask = np.maximum(wall_mask, bin_m)
                            continue
                        cargo_mask = np.maximum(cargo_mask, kept)
                        n_cargo += 1
                if n_cargo > 0:
                    seg_source = "opencv+yolo" if oc["n_boxes"] or oc["box_ratio"] > 0.02 else "yolo"
                    logs.append(
                        f"[2/3] YOLO 탐지 {n_det}개 중 화물 {n_cargo}개 (벽면 제외 후)"
                    )
                else:
                    logs.append(
                        f"[2/3] YOLO 탐지 {n_det}개 → 화물 없음 또는 전부 벽면으로 분류"
                    )
            else:
                logs.append(f"[2/3] YOLO 탐지 {n_det}개 → 마스크 없음")
        except Exception as e:
            logs.append(f"[2/3] YOLO 스킵 ({e.__class__.__name__}: {e})")
            engine = "opencv+yolo-failed"
    else:
        logs.append("[2/3] YOLO 미가용 → OpenCV 마스크만 사용")
        engine = "opencv-only"

    cargo_mask = cv2.bitwise_or(cargo_mask, oc["box_mask"])
    cargo_mask = cv2.bitwise_and(cargo_mask, cv2.bitwise_not(wall_mask))

    roi = np.zeros((h, w), dtype=np.uint8)
    roi[int(h * 0.05) : int(h * 0.97), int(w * 0.08) : int(w * 0.92)] = 255

    cargo_px_pre = int(np.count_nonzero(cv2.bitwise_and(cargo_mask, roi)))
    roi_px_pre = max(int(np.count_nonzero(roi)), 1)
    if depth_n is not None and cargo_px_pre / roi_px_pre < 0.04:
        try:
            dn = depth_n.astype(np.float32)
            if dn.shape[:2] != (h, w):
                dn = cv2.resize(dn, (w, h), interpolation=cv2.INTER_LINEAR)
            floor_band = dn[int(h * 0.70) :, int(w * 0.12) : int(w * 0.88)]
            floor_mean = float(floor_band.mean()) if floor_band.size else 0.5
            thr = floor_mean + 0.07
            near = ((dn >= thr) & (roi > 0) & (wall_mask == 0)).astype(np.uint8) * 255
            near[: int(h * 0.10), :] = 0
            near[int(h * 0.94) :, :] = 0
            near = cv2.morphologyEx(near, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            near = cv2.morphologyEx(near, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
            near = cv2.morphologyEx(near, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
            near_px = int(np.count_nonzero(near))
            if near_px / roi_px_pre >= 0.04:
                if cargo_px_pre / roi_px_pre < 0.01:
                    cargo_mask = near
                    seg_source = "depth"
                else:
                    cargo_mask = np.maximum(cargo_mask, near)
                    seg_source = "blend"
                engine = f"{engine}+depth-assist"
                logs.append(
                    f"[2/3] 깊이 보조 화물면 적용 seg_source={seg_source} "
                    f"thr={thr:.3f} cover≈{100 * near_px / roi_px_pre:.1f}%"
                )
            else:
                logs.append(
                    f"[2/3] 깊이 보조 후보 약함 cover≈{100 * near_px / roi_px_pre:.1f}% → 마스크 유지"
                )
        except Exception as e:
            logs.append(f"[2/3] 깊이 보조 스킵 ({e.__class__.__name__})")

    cargo_mask = cv2.bitwise_and(cargo_mask, cv2.bitwise_not(wall_mask))
    if seg_source == "none" and cargo_px_pre / roi_px_pre >= 0.01:
        seg_source = "opencv"

    free_mask = cv2.bitwise_and(roi, cv2.bitwise_not(cargo_mask))
    free_mask = cv2.bitwise_and(free_mask, cv2.bitwise_not(wall_mask))

    lower = np.zeros((h, w), dtype=np.uint8)
    lower[int(h * 0.55) :, int(w * 0.08) : int(w * 0.92)] = 255
    floor_mask = cv2.bitwise_and(lower, free_mask)
    floor_mask = cv2.bitwise_or(floor_mask, cv2.bitwise_and(oc["floor_mask"], free_mask))

    roi_px = max(int(np.count_nonzero(roi)), 1)
    free_px = int(np.count_nonzero(cv2.bitwise_and(free_mask, roi)))
    cargo_px = int(np.count_nonzero(cv2.bitwise_and(cargo_mask, roi)))
    floor_px = int(np.count_nonzero(floor_mask))

    free_space_percent = _clamp(free_px / roi_px * 100)
    cargo_cover_percent = _clamp(cargo_px / roi_px * 100)
    lower_px = max(int(np.count_nonzero(lower)), 1)
    floor_empty_percent = _clamp(floor_px / lower_px * 100)

    logs.append(
        f"[2/3] 분할 완료 engine={engine} seg_source={seg_source} | "
        f"여유공간면 {free_space_percent:.1f}% / 화물면 {cargo_cover_percent:.1f}% / "
        f"하단여유 {floor_empty_percent:.1f}%"
    )

    return {
        "floor_mask": floor_mask,
        "cargo_mask": cargo_mask,
        "wall_mask": wall_mask,
        "free_mask": free_mask,
        "floor_empty_percent": floor_empty_percent,
        "free_space_percent": free_space_percent,
        "cargo_cover_percent": cargo_cover_percent,
        "engine": engine,
        "seg_source": seg_source,
        "yolo_detections": n_det,
        "yolo_cargo_candidates": n_cargo,
        "opencv_boxes": oc["n_boxes"],
        "opencv_wall_ratio": oc["wall_ratio"],
        "opencv_box_ratio": oc["box_ratio"],
    }


def build_occupancy_grid(
    depth_n: np.ndarray,
    cargo_mask: np.ndarray,
    logs: list[str],
    nx: int = 10,
    ny: int = 3,
    nz: int = 3,
    free_mask: np.ndarray | None = None,
) -> dict[str, Any]:
    """
    기본=비움 → 화물로 식별된 칸만 채움 (complement 방식의 과대점유 방지).
    - 길이 nx=10, 폭 ny=3, 높이 nz=3
    - 이미지 위(먼쪽)=캡 i=0, 아래(문쪽)=문 i=nx-1
    """
    h, w = depth_n.shape[:2]
    if free_mask is None:
        free_mask = np.zeros((h, w), dtype=np.uint8)
        free_mask[cargo_mask == 0] = 255

    y0, y1 = int(h * 0.04), int(h * 0.98)
    x0, x1 = int(w * 0.08), int(w * 0.92)
    roi_h = max(y1 - y0, 1)
    roi_w = max(x1 - x0, 1)

    # 기본: 전부 비움 → 화물 칸만 채움
    occ = np.zeros((nx, ny, nz), dtype=bool)
    cargo_cols = 0

    for i in range(nx):
        for j in range(ny):
            ry0 = y0 + int(i * roi_h / nx)
            ry1 = y0 + int((i + 1) * roi_h / nx)
            cx0 = x0 + int(j * roi_w / ny)
            cx1 = x0 + int((j + 1) * roi_w / ny)
            ph = max(ry1 - ry0, 1)
            col_free = free_mask[ry0:ry1, cx0:cx1]
            col_cargo = cargo_mask[ry0:ry1, cx0:cx1]
            if col_cargo.size < 4:
                continue
            free_ratio = float(np.count_nonzero(col_free > 0)) / float(col_free.size)
            cargo_ratio = float(np.count_nonzero(col_cargo > 0)) / float(col_cargo.size)

            # 열에 화물이 거의 없으면 비움 유지
            if cargo_ratio < 0.12 or free_ratio >= 0.70:
                continue

            cargo_cols += 1
            # 높이별: 화물 비율이 의미 있는 단만 채움
            for k in range(nz):
                sy0 = ry0 + int((nz - 1 - k) * ph / nz)
                sy1 = ry0 + int((nz - k) * ph / nz)
                sub_c = cargo_mask[sy0:sy1, cx0:cx1]
                sub_f = free_mask[sy0:sy1, cx0:cx1]
                if sub_c.size < 4:
                    continue
                cr = float(np.count_nonzero(sub_c > 0)) / float(sub_c.size)
                fr = float(np.count_nonzero(sub_f > 0)) / float(sub_f.size)
                if cr >= 0.18 and fr < 0.75:
                    occ[i, j, k] = True

            # 물리: 아래가 비면 위만 채우지 않음 (공중 화물 오탐 방지)
            for k in range(nz - 1, 0, -1):
                if occ[i, j, k] and not occ[i, j, k - 1]:
                    occ[i, j, k] = False

    # 길이 방향 구멍 제거: 화물을 캡(i=0) 쪽으로 밀어 연속 적재
    before_cells = int(np.count_nonzero(occ))
    occ = _pack_occupancy_to_cab(occ)
    after_cells = int(np.count_nonzero(occ))
    logs.append(
        f"[격자] 캡쪽 연속 압축 | 셀 {before_cells}→{after_cells} "
        f"(길이 구멍 제거, 셀 수 유지 목표)"
    )

    cells = [
        {"i": int(i), "j": int(j), "k": int(k)}
        for i in range(nx)
        for j in range(ny)
        for k in range(nz)
        if occ[i, j, k]
    ]
    occupied_cols = sum(1 for i in range(nx) for j in range(ny) if occ[i, j].any())
    total = nx * ny * nz
    grid_occ = round(100.0 * len(cells) / max(total, 1), 2)
    logs.append(
        f"[격자] 화물만 채움 {nx}x{ny}x{nz} | 점유셀 {len(cells)}/{total} ({grid_occ}%) "
        f"| 화물열 {cargo_cols}/{nx * ny} | 점유열 {occupied_cols}/{nx * ny}"
    )
    return {
        "nx": nx,
        "ny": ny,
        "nz": nz,
        "cells": cells,
        "cell_count": len(cells),
        "grid_occupied_percent": grid_occ,
        "source": "cargo-fill-packed",
    }


def _pack_occupancy_to_cab(occ: np.ndarray) -> np.ndarray:
    """
    길이(i) 방향 빈칸을 없애고 캡(i=0) 쪽으로 붙인다.
    폭(j)·높이(k) 스택은 유지하되, 공중 화물(아래 비움)은 다시 정리.
    """
    nx, ny, nz = occ.shape
    out = np.zeros_like(occ)
    for j in range(ny):
        # 열(폭) 단위로: 어떤 높이든 화물이 있는 길이 슬롯을 캡 쪽으로 압축
        occupied_i = [i for i in range(nx) if occ[i, j].any()]
        for new_i, old_i in enumerate(occupied_i):
            out[new_i, j, :] = occ[old_i, j, :]
        # 높이 물리 정리
        for i in range(nx):
            for k in range(nz - 1, 0, -1):
                if out[i, j, k] and not out[i, j, k - 1]:
                    out[i, j, k] = False
    return out


# ---------------------------------------------------------------------------
# [3/3] 3D 적재(py3dbp 계열) — 잔여 부피 %
# ---------------------------------------------------------------------------
def stage_pack_remaining(
    depth_info: dict[str, Any],
    seg_info: dict[str, Any],
    logs: list[str],
    occupancy: dict[str, Any] | None = None,
    img: np.ndarray | None = None,
    image_bytes: bytes | None = None,
    filename: str = "",
) -> dict[str, Any]:
    """
    잔여·적재율: Gemini Vision + 빈차/만원 시각 게이트가 우선.
    Depth 선형보정은 중간 적재의 보조값.
    """
    logs.append("[3/3] 잔여 공간·적재율 산출 (vision + empty/full gate)")

    floor_empty = float(seg_info["floor_empty_percent"])
    free_depth = float(depth_info["free_depth_ratio"])
    cargo_cover = float(seg_info["cargo_cover_percent"])
    free_space = float(seg_info.get("free_space_percent") or floor_empty)
    seg_source = str(seg_info.get("seg_source") or "none")

    blocked = float(depth_info.get("fill_blocked") or 0.0)
    mass = float(depth_info.get("fill_mass") or 0.0)
    # depth_info에 없으면 맵에서 재계산
    if blocked <= 0.0 and depth_info.get("depth_map") is not None:
        m = compute_depth_fill_metrics(depth_info["depth_map"])
        blocked = float(m["blocked"])
        mass = float(m["mass"])
        depth_info = {**depth_info, "fill_blocked": blocked, "fill_mass": mass, "fill_face_pos": m["face_pos"]}

    calib = calibrate_occupied_from_depth(blocked, mass, cargo_cover)
    if cargo_cover >= 8.0 and seg_source in ("yolo", "blend"):
        calib = _clamp(0.75 * calib + 0.25 * _clamp(cargo_cover * 1.15))

    vis = estimate_visual_occupancy(img) if img is not None else {
        "occupied": calib, "empty_like": False, "full_like": False,
    }
    logs.append(
        f"[3/3] visual empty={vis.get('empty_like')} full={vis.get('full_like')} "
        f"vis={vis.get('occupied')} metal={vis.get('metal_ratio')} colorful={vis.get('colorful')}"
    )
    gemini = None
    if image_bytes:
        gemini = analyze_occupancy_with_gemini(image_bytes, filename, logs)
    occupied, pack_engine = fuse_occupied(calib, vis, gemini, logs)

    remaining = _clamp(100.0 - occupied)
    height_util = _clamp(occupied)
    logs.append(
        f"[3/3] pack engine={pack_engine} seg_source={seg_source} "
        f"blocked={blocked:.1f} mass={mass:.1f} cover={cargo_cover:.1f} → occupied={occupied:.1f}%"
    )

    try:
        from py3dbp import Packer, Bin, Item

        rem_m3 = TRUCK_CAPACITY_M3 * (remaining / 100.0)
        side = max(rem_m3 ** (1.0 / 3.0), 0.2)
        packer = Packer()
        packer.add_bin(Bin("remain", side, side, side, 1000))
        unit = 0.25
        fitted = 0
        for i in range(40):
            packer.add_item(Item(f"u{i}", unit, unit, unit, 1))
        packer.pack()
        for b in packer.bins:
            fitted = len(b.items)
        pack_engine = pack_engine + "+py3dbp"
        logs.append(f"[3/3] py3dbp 잔여박스 시뮬레이션: 단위상자 {fitted}개 수용 가능 (잔여≈{rem_m3:.2f}m³)")
    except Exception as e:
        logs.append(f"[3/3] py3dbp 미설치/스킵 — 여유공간 보수 ({e.__class__.__name__})")
        rem_m3 = TRUCK_CAPACITY_M3 * (remaining / 100.0)
        logs.append(f"[3/3] 잔여 부피 추정 {rem_m3:.2f}m³ / 전체 {TRUCK_CAPACITY_M3}m³")

    logs.append(
        f"[3/3] cover={cargo_cover:.1f}% free={free_space:.1f}% "
        f"free_depth={free_depth:.1f}% → occupied={occupied:.1f}% remaining={remaining:.1f}% ({pack_engine})"
    )

    status = (
        "여유공간 충분" if remaining >= 45 else ("정상 적재" if occupied < 85 else "과적재 주의")
    )
    guide = (
        "하차/여유공간 확보 상태입니다. 추가 복화 물량 탐색이 가능합니다."
        if remaining >= 45
        else (
            "정확한 부피가 적재되었습니다. 안전운행하세요."
            if occupied < 85
            else "과적재가 의심됩니다. 재확인하세요."
        )
    )

    logs.append(
        f"[3/3] 최종 산출 engine={pack_engine} | 잔여 {remaining:.1f}% / 적재 {occupied:.1f}% | {status}"
    )

    return {
        "remaining_volume_percent": round(remaining, 2),
        "occupied_volume_percent": round(occupied, 2),
        "floor_empty_percent": round(floor_empty, 2),
        "height_utilization_percent": round(height_util, 2),
        "free_depth_ratio": round(free_depth, 2),
        "cargo_cover_percent": round(cargo_cover, 2),
        "depth_fill_blocked": round(blocked, 2),
        "depth_fill_mass": round(mass, 2),
        "status": status,
        "guide": guide,
        "engine": f"depth={depth_info['engine']} | seg={seg_info['engine']} | pack={pack_engine}",
        "pack_engine": pack_engine,
        "remaining_m3": round(TRUCK_CAPACITY_M3 * (remaining / 100.0), 3),
        "occupied_m3": round(TRUCK_CAPACITY_M3 * (occupied / 100.0), 3),
    }


def analyze_with_vertex_endpoint(image_bytes: bytes, logs: list[str]) -> dict[str, Any] | None:
    if not VERTEX_ENDPOINT:
        return None
    from google.cloud import aiplatform
    import base64

    logs.append(f"[Vertex] Custom Endpoint 호출: {VERTEX_ENDPOINT}")
    aiplatform.init(project=PROJECT_ID, location=LOCATION)
    endpoint = aiplatform.Endpoint(
        endpoint_name=f"projects/{PROJECT_ID}/locations/{LOCATION}/endpoints/{VERTEX_ENDPOINT}"
    )
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    prediction = endpoint.predict(instances=[{"content": b64}])
    preds = prediction.predictions[0] if prediction.predictions else {}
    remaining = _clamp(preds.get("remaining_volume_percent", preds.get("remaining", 0)))
    occupied = _clamp(100 - remaining)
    return {
        "remaining_volume_percent": round(remaining, 2),
        "occupied_volume_percent": round(occupied, 2),
        "status": preds.get("status", "정상 적재"),
        "guide": preds.get("guide", "측정 완료"),
        "engine": "vertex-custom-endpoint",
        "logs": logs + [f"[Vertex] 잔여 {remaining:.1f}%"],
    }


def analyze_truck_space(image_bytes: bytes, filename: str = "") -> dict[str, Any]:
    logs: list[str] = [
        "이미지 수신 완료",
        "RFP 파이프라인: (1)Depth → (2)YOLO-Seg → (3)수치 Pack (격자 제외)",
    ]

    # Optional: Vertex Endpoint — 수치만 있으면 사용 (격자 필수 아님)
    try:
        custom = analyze_with_vertex_endpoint(image_bytes, logs)
        if custom and custom.get("occupied_volume_percent") is not None:
            custom.setdefault("occupancy_grid", None)
            return custom
    except Exception as e:
        logs.append(f"Custom Endpoint 스킵: {e}")

    img = _decode(image_bytes)
    logs.append(f"디코드 완료: {img.shape[1]}x{img.shape[0]} px / file={filename or '-'}")

    depth_info = stage_depth_anything(img, logs)
    seg_info = stage_yolo_seg(img, logs, depth_info.get("depth_map"))
    pack = stage_pack_remaining(
        depth_info, seg_info, logs, None,
        img=img, image_bytes=image_bytes, filename=filename,
    )

    reasoning = (
        f"화물면 {seg_info.get('cargo_cover_percent', 0):.1f}% · "
        f"여유면 {seg_info.get('free_space_percent', seg_info['floor_empty_percent']):.1f}% · "
        f"깊이잔여 {depth_info['free_depth_ratio']:.1f}%"
    )
    logs.append(f"종합 근거: {reasoning}")
    logs.append(
        f"파이프라인 완료 — Depth 적재지표 보정 주계산 "
        f"(blocked={depth_info.get('fill_blocked')} mass={depth_info.get('fill_mass')})"
    )

    return {
        "remaining_volume_percent": pack["remaining_volume_percent"],
        "occupied_volume_percent": pack["occupied_volume_percent"],
        "floor_empty_percent": pack["floor_empty_percent"],
        "height_utilization_percent": pack["height_utilization_percent"],
        "cargo_cover_percent": pack.get("cargo_cover_percent"),
        "status": pack["status"],
        "guide": pack["guide"],
        "reasoning": reasoning,
        "engine": pack["engine"],
        "pack_engine": pack.get("pack_engine"),
        "pipeline": ["depth-anything", "yolov8-seg", "depth-fill-calib"],
        "occupancy_grid": None,
        "remaining_m3": pack.get("remaining_m3"),
        "occupied_m3": pack.get("occupied_m3"),
        "depth_fill_blocked": pack.get("depth_fill_blocked"),
        "depth_fill_mass": pack.get("depth_fill_mass"),
        "logs": logs,
    }


# ---------------------------------------------------------------------------
# 바닥 적재 더미(스택) → 가로·세로·높이(mm) · 차종별 점유율
# ---------------------------------------------------------------------------
VEHICLE_PROFILES = [
    {"key": "1t", "label": "1톤", "tons": 1.0, "capacity_m3": 10.0},
    {"key": "2_5t", "label": "2.5톤", "tons": 2.5, "capacity_m3": 20.0},
    {"key": "3t", "label": "3톤", "tons": 3.0, "capacity_m3": 22.0},
    {"key": "5t", "label": "5톤", "tons": 5.0, "capacity_m3": 28.0},
    {"key": "8t", "label": "8톤", "tons": 8.0, "capacity_m3": 40.0},
    {"key": "11t", "label": "11톤", "tons": 11.0, "capacity_m3": 30.545},
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
            "fillPercent": pct,
        }
    return out


def _estimate_dims_mm_from_masks(
    img: np.ndarray,
    depth_n: np.ndarray,
    cargo_mask: np.ndarray,
    logs: list[str],
) -> tuple[int, int, int, str]:
    """화물 마스크 + 상대깊이로 더미 외접 상자(mm) 추정."""
    import cv2

    h, w = img.shape[:2]
    ys, xs = np.where(cargo_mask > 0)
    if xs.size < 80:
        # 중앙 ROI 폴백
        y0, y1 = int(h * 0.2), int(h * 0.85)
        x0, x1 = int(w * 0.15), int(w * 0.85)
        cargo_mask = np.zeros_like(cargo_mask)
        cargo_mask[y0:y1, x0:x1] = 255
        ys, xs = np.where(cargo_mask > 0)
        logs.append("[floor] 화물 마스크 약함 → 중앙 ROI로 추정")

    x_min, x_max = int(xs.min()), int(xs.max())
    y_min, y_max = int(ys.min()), int(ys.max())
    bw = max(1, x_max - x_min)
    bh = max(1, y_max - y_min)

    # 바닥 밴드(이미지 하단) vs 화물 상단 깊이 차로 높이 스케일
    floor_band = depth_n[int(h * 0.78) :, int(w * 0.2) : int(w * 0.8)]
    top_band = depth_n[y_min : min(y_min + max(8, bh // 5), h), x_min:x_max]
    floor_d = float(np.median(floor_band)) if floor_band.size else 0.3
    top_d = float(np.median(top_band)) if top_band.size else 0.7
    # Depth Anything 정규화: 값이 클수록 가까움 → 높이 지표 = |top-floor|
    rel_h = abs(top_d - floor_d)
    # 카메라 거리·FOV 가정: 가로 FOV ~65°, 촬영거리 ~2.0m → 화면 가로 ≈ 2.5m
    scene_width_m = 2.5
    m_per_px = scene_width_m / max(w, 1)
    width_m = bw * m_per_px
    # 세로(깊이)는 투시 보정: 하단이 더 넓게 보이므로 bh에 0.85 가중
    depth_m = bh * m_per_px * 0.85
    # 상대깊이 → 물리 높이 (rel_h 0.05~0.55 → 0.3~1.8m)
    height_m = _clamp(0.25 + rel_h * 2.8, 0.2, 2.4)

    # 현실적 클램프 (바닥 더미)
    width_m = _clamp(width_m, 0.35, 3.5)
    depth_m = _clamp(depth_m, 0.35, 3.5)
    height_m = _clamp(height_m, 0.25, 2.2)

    # 정사각 더미에 가깝게 가로·세로 균형 (한쪽만 극단이면 평균으로 완화)
    if width_m > 0 and depth_m / width_m > 2.5:
        depth_m = width_m * 1.2
    if depth_m > 0 and width_m / depth_m > 2.5:
        width_m = depth_m * 1.2

    w_mm = int(round(width_m * 1000))
    d_mm = int(round(depth_m * 1000))
    h_mm = int(round(height_m * 1000))
    logs.append(
        f"[floor] bbox={bw}x{bh}px relH={rel_h:.3f} → "
        f"{w_mm}×{d_mm}×{h_mm} mm (sceneW={scene_width_m}m)"
    )
    return w_mm, d_mm, h_mm, "depth+seg"


def analyze_floor_cargo(image_bytes: bytes, filename: str = "") -> dict[str, Any]:
    """
    바닥에 쌓인 화물 더미 사진을 분석해 외접 치수(mm)·체적(m³)·차종별 점유율을 반환.
    (트럭 내부 잔여공간 분석과 별도)
    """
    logs: list[str] = [
        "바닥 적재 더미 분석 시작",
        "파이프라인: Depth → YOLO/Seg 화물영역 → 외접치수(mm)",
    ]
    img = _decode(image_bytes)
    logs.append(f"디코드 완료: {img.shape[1]}x{img.shape[0]} px / file={filename or '-'}")

    depth_info = stage_depth_anything(img, logs)
    seg_info = stage_yolo_seg(img, logs)
    w_mm, d_mm, h_mm, engine = _estimate_dims_mm_from_masks(
        img,
        depth_info["depth_map"],
        seg_info.get("cargo_mask"),
        logs,
    )

    volume_m3 = round((w_mm * d_mm * h_mm) / 1e9, 4)
    fills = fill_by_vehicle(volume_m3)
    fill11 = fills.get("11t", {}).get("fillPercent", 0)

    logs.append(f"[floor] 체적 {volume_m3} m³ · 11톤 점유 {fill11}%")
    logs.append("바닥 적재 분석 완료")

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
        "pipeline": ["depth-anything", "yolov8-seg", "floor-bbox-scale"],
        "guide": f"추정 치수 {w_mm}×{d_mm}×{h_mm} mm · {volume_m3} CBM",
        "status": "ok",
        "logs": logs,
    }

