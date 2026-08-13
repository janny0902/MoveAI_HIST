from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from utils import load_cargo_from_csv, calculate_total_metrics, TRUCK_CAPACITY_M3_11T
from space_analyzer import analyze_truck_space, analyze_floor_cargo, fill_by_vehicle, VEHICLE_PROFILES

app = FastAPI(title="moveAI Engine (FastAPI)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "moveai-504907")
LOCATION = os.getenv("GCP_LOCATION", "us-central1")

gemini_model = None
try:
    import vertexai
    from vertexai.generative_models import GenerativeModel

    vertexai.init(project=PROJECT_ID, location=LOCATION)
    gemini_model = GenerativeModel("gemini-2.5-flash")
    print("Vertex AI Gemini 초기화 성공")
except Exception as e:
    print(f"Vertex AI 초기화 대기 (키/권한 필요): {e}")
    gemini_model = None


class CargoItem(BaseModel):
    cargo_id: str
    type: str
    width: float
    length: float
    height: float
    volume_cm3: float


@app.get("/ai/health")
def health_check():
    return {
        "status": "ok",
        "vertex_ai": "connected" if gemini_model else "pending_credentials",
        "project": PROJECT_ID,
        "space_engine": "depth-anything → yolov8-seg → 3d-packing",
        "briefing_engine": "gemini-2.5-flash" if gemini_model else "fallback",
        "csv_exists": os.path.exists(os.getenv("CSV_PATH", "/data/volumetric/origin 체적.csv")),
    }


@app.get("/ai/cargo-pool")
def get_cargo_pool():
    csv_path = os.getenv("CSV_PATH", "/data/volumetric/origin 체적.csv")
    path = csv_path if os.path.exists(csv_path) else None
    if not path:
        local = os.path.join(os.path.dirname(__file__), "..", "Volumetric data", "origin 체적.csv")
        path = local if os.path.exists(local) else csv_path

    cargo_list = load_cargo_from_csv(path, count=30)
    if not cargo_list:
        cargo_list = []
        for i in range(15):
            w, l, h = 300.0 + i, 400.0, 200.0  # mm
            vol_cm3 = (w * l * h) / 1000.0
            cargo_list.append(
                {
                    "cargo_id": f"BOX-A{100 + i}",
                    "type": "A",
                    "width": w,
                    "length": l,
                    "height": h,
                    "dim_unit": "mm",
                    "volume_cm3": vol_cm3,
                    "volume_m3": vol_cm3 / 1_000_000.0,
                }
            )
    return {
        "cargo_pool": cargo_list,
        "truck_capacity_m3": TRUCK_CAPACITY_M3_11T,
        "truck_spec": "11톤 윙바디 2.35×9.30×2.45m · 30.545m³ · 11000kg",
    }


@app.post("/ai/generate-briefing")
async def generate_briefing(data: dict):
    profit = data.get("profit", 0)
    extra_distance = data.get("extra_distance", 0)
    extra_time = data.get("extra_time", 0)
    esg = data.get("esg", 0)
    fallback = (
        f"김기사님, 경유 시 약 {extra_time}분이 추가되지만 "
        f"순이익 약 {profit:,}원과 ESG {esg}kg 절감이 가능합니다. 수락하시겠습니까?"
    )
    if not gemini_model:
        return {"briefing": fallback, "source": "fallback"}
    prompt = f"""
기사에게 복화 배차를 제안하는 짧은 한국어 메시지(2~3문장):
이익 {profit}원, 추가거리 {extra_distance}km, 추가시간 {extra_time}분, ESG {esg}kg
"""
    try:
        response = gemini_model.generate_content(prompt)
        return {"briefing": response.text, "source": "gemini"}
    except Exception:
        return {"briefing": fallback, "source": "fallback"}


@app.post("/ai/optimal-dispatch")
async def optimal_dispatch(data: dict):
    """
    후보 복화 그룹을 수익↑·추가거리↓·추가시간↓ 기준으로 순위화.
    응답: ranked_request_ids, briefing
    """
    import json
    import re

    origin = data.get("driver_origin") or "?"
    dest = data.get("driver_destination") or "?"
    candidates = data.get("candidates") or []
    # 휴리스틱 기본 순위
    ranked = sorted(
        candidates,
        key=lambda c: float(c.get("heuristicScore") or 0),
        reverse=True,
    )
    heuristic_ids = [c.get("requestId") for c in ranked if c.get("requestId") is not None]
    fallback_brief = (
        f"{origin} → {dest} 기준으로 순이익이 높고 우회·추가 시간이 적은 "
        f"복화 {min(5, len(heuristic_ids))}건을 추천합니다."
    )
    if not candidates:
        return {
            "ranked_request_ids": [],
            "rankedRequestIds": [],
            "briefing": "추천 가능한 복화가 없습니다.",
            "source": "empty",
        }

    if not gemini_model:
        return {
            "ranked_request_ids": heuristic_ids,
            "rankedRequestIds": heuristic_ids,
            "briefing": fallback_brief,
            "source": "fallback",
        }

    slim = [
        {
            "requestId": c.get("requestId"),
            "origin": c.get("origin"),
            "destination": c.get("destination"),
            "netProfit": c.get("netProfit"),
            "extraDistanceKm": c.get("extraDistanceKm"),
            "extraMinutes": c.get("extraMinutes"),
            "fillPercentOf11t": c.get("fillPercentOf11t"),
            "heuristicScore": c.get("heuristicScore"),
        }
        for c in candidates[:12]
    ]
    prompt = f"""당신은 화물 복화 배차 최적화 도우미입니다.
기사 경로: {origin} → {dest}, 잔여공간 {data.get('remaining_percent')}%.
후보(JSON):
{json.dumps(slim, ensure_ascii=False)}

목표: 순이익을 최대화하고, 추가거리(extraDistanceKm)·추가시간(extraMinutes)을 최소화하는 requestId 순서를 고르세요.
잔여공간(fillPercentOf11t 합)을 넘기지 마세요. 최대 5개.
반드시 JSON만 출력:
{{"rankedRequestIds":[숫자,...],"briefing":"기사에게 보여줄 한국어 2문장"}}
"""
    try:
        response = gemini_model.generate_content(prompt)
        text = (response.text or "").strip()
        # ```json ... ``` 제거
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
        ids = parsed.get("rankedRequestIds") or parsed.get("ranked_request_ids") or heuristic_ids
        briefing = parsed.get("briefing") or fallback_brief
        return {
            "ranked_request_ids": ids,
            "rankedRequestIds": ids,
            "briefing": briefing,
            "source": "gemini",
        }
    except Exception as e:
        return {
            "ranked_request_ids": heuristic_ids,
            "rankedRequestIds": heuristic_ids,
            "briefing": fallback_brief,
            "source": "fallback",
            "error": str(e),
        }


@app.post("/ai/analyze-image")
async def analyze_image(file: UploadFile = File(...)):
    """
    실제 이미지 기반 잔여공간 측정.
    난수/파일명 규칙 사용하지 않음.
    """
    content = await file.read()
    result = analyze_truck_space(content, file.filename or "")
    result["filename"] = file.filename
    result["vertex_endpoint"] = os.getenv("VERTEX_ENDPOINT_ID") or None
    result["space_pipeline"] = result.get("pipeline") or [
        "depth-anything",
        "yolov8-seg",
        "3d-packing",
    ]
    return result


@app.post("/ai/analyze-floor-cargo")
async def analyze_floor_cargo_api(file: UploadFile = File(...)):
    """
    바닥 적재 더미 사진 → 가로·세로·높이(mm) · 체적 · 차종별 점유율(3/5/11/18톤 등).
    운송장 그룹 등록용.
    """
    content = await file.read()
    result = analyze_floor_cargo(content, file.filename or "")
    result["filename"] = file.filename
    return result


@app.get("/ai/vehicle-fill")
def vehicle_fill(volume_m3: float = 1.0):
    """체적(m³) → 표준 차종별 점유율 미리보기."""
    vol = max(0.0, float(volume_m3))
    fills = fill_by_vehicle(vol)
    return {
        "volume_m3": round(vol, 4),
        "fill_by_vehicle": fills,
        "vehicle_profiles": VEHICLE_PROFILES,
        "fill_percent_of_11t": fills.get("11t", {}).get("fillPercent", 0),
    }
