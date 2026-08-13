from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from space_analyzer import analyze_image
from utils import TRUCK_CAPACITY_M3, credentials_present, csv_exists

app = FastAPI(title="moveAI backend-ai", version="0.1.0-bootstrap")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BriefingRequest(BaseModel):
    profit: float = 0
    extra_distance: float = 0
    extra_time: float = 0
    esg: float = 0


@app.get("/ai/health")
def health() -> dict[str, Any]:
    project = os.getenv("GCP_PROJECT_ID", "")
    vertex = "connected" if credentials_present() else "pending_credentials"
    briefing = "gemini-2.5-flash" if credentials_present() else "fallback"
    return {
        "status": "ok",
        "vertex_ai": vertex,
        "project": project,
        "space_engine": "depth-anything → yolov8-seg → 3d-packing",
        "briefing_engine": briefing,
        "csv_exists": csv_exists(),
        "phase": "bootstrap",
    }


@app.get("/ai/cargo-pool")
def cargo_pool() -> dict[str, Any]:
    return {
        "cargo_pool": [],
        "truck_capacity_m3": TRUCK_CAPACITY_M3,
        "truck_spec": {"capacity_tons": 11, "capacity_m3": TRUCK_CAPACITY_M3},
        "message": "volumetric CSV import not wired yet",
    }


@app.post("/ai/generate-briefing")
def generate_briefing(body: BriefingRequest) -> dict[str, str]:
    text = (
        f"예상 순이익 {int(body.profit):,}원, 우회 {body.extra_distance:.1f}km"
        f"({int(body.extra_time)}분), ESG {body.esg:.1f}kg 절감 효과가 있습니다."
    )
    return {"briefing": text, "source": "fallback"}


@app.post("/ai/analyze-image")
async def analyze(file: UploadFile = File(...)) -> dict[str, Any]:
    raw = await file.read()
    name = file.filename or "upload.jpg"
    return analyze_image(raw, name)
