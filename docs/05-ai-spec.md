# 05 — AI 명세

---

## 1. 역할 분리

| 엔진 | 용도 | 엔드포인트 |
|------|------|------------|
| Depth + OpenCV + (YOLO/Gemini) | 잔여공간·적재율 | `POST /ai/analyze-image` |
| Gemini 2.5 Flash | 복화 브리핑 · 비전 JSON 보조 | `/ai/generate-briefing`, analyze 융합 |
| (옵션) Vertex Endpoint | 통합 predict | `VERTEX_ENDPOINT_ID` |

공간 분석은 **숫자는 비전/기하**, 문구는 Gemini. 난수 적재율 금지.  
깊이 비교는 **천장 말고 바닥**. 녹슨 철벽은 화물이 아님 (`rust_wall` vs cardboard HSV).

---

## 2. 잔여공간 파이프라인 (`space_analyzer.py`)

입력: 이미지 bytes (+ filename)  
출력 JSON 필수 필드:

```json
{
  "remaining_volume_percent": 0,
  "occupied_volume_percent": 0,
  "floor_empty_percent": 0,
  "height_utilization_percent": 0,
  "status": "여유공간 충분|정상 적재|과적재 주의",
  "guide": "한국어 안내",
  "reasoning": "요약 근거",
  "engine": "depth=... | seg=... | pack=...",
  "pipeline": ["depth-anything", "yolov8-seg", "3d-packing"],
  "logs": ["...", "[1/3] ...", "[2/3] ...", "[3/3] ..."]
}
```

### [1/3] Depth

1. **Primary**: HuggingFace `depth-anything/Depth-Anything-V2-Small-hf` (transformers)
2. **Secondary**: torch.hub `MiDaS_small` (비대화형 input 패치, `TORCH_HUB_DIR`)
3. **Fallback**: OpenCV Laplacian+수직 그라데이션 상대깊이 (난수 금지)

산출: 정규화 depth map → 바닥 밴드 vs 화물 밴드 평균 → `free_depth_ratio` (%)

### [2/3] Segmentation

1. **Primary**: Ultralytics `yolov8n-seg.pt`
2. COCO 클래스 특성상 적재함 내부는 탐지 0일 수 있음 → **추론은 실행**, 마스크 없으면 OpenCV Canny 기하 분할과 융합
3. 엔진명 예: `yolov8n-seg`, `yolov8n-seg+opencv-floor`

산출: `floor_empty_percent`, `cargo_cover_percent`

### [3/3] Packing

- 융합: `remaining ≈ 0.55*floor_empty + 0.45*free_depth` (화물면 과다 시 하향)
- **py3dbp**: 잔여 m³을 정육면체 Bin으로 단위상자 packing 시뮬레이션 → 로그
- 없으면 volume-fusion 공식만

용량 상수: `TRUCK_CAPACITY_M3` 기본 50.

### Vertex Custom (옵션)

`VERTEX_ENDPOINT_ID` 비어 있지 않으면 base64 인스턴스 predict 후 동일 스키마로 조기 return.

---

## 3. 브리핑 LLM

입력:

```json
{ "profit": 0, "extra_distance": 0, "extra_time": 0, "esg": 0 }
```

- 모델: `gemini-2.5-flash` (vertexai GenerativeModel)
- 실패/미초기화: 한국어 템플릿 fallback, `source: fallback|gemini`

Spring `propose` 매칭 성공 시 호출해 `briefing` 필드에 넣음.

---

## 4. Spring 측 후처리 (업로드)

`LoadController`가 AI 결과 수신 후:

- `expectedAddedFillPercent` + `baselineOccupiedPercent` 있으면  
  기대 점유±허용으로 `OVERLOAD_SUSPECTED` / `UNDERLOAD_SUSPECTED` / `MATCHED`
- 없으면 AI `guide` 사용 (`NO_EXPECTED`)

---

## 5. 의존성 (AI 컨테이너)

- torch/torchvision (CPU wheel 권장)
- transformers, timm, ultralytics, py3dbp, opencv-python-headless
- google-cloud-aiplatform (Gemini)
- Dockerfile에서 yolov8n-seg.pt / Depth 가중치 프리패치 가능

---

## 6. 로그 계약 (UI Tail)

로그 배열에 최소 포함:

- `RFP 3단 파이프라인 시작...`
- `[1/3] ...`
- `[2/3] ...`
- `[3/3] ...`
- `파이프라인 완료 ...`

에이전트 재현 시 **이 문자열 패턴을 유지**하면 데모 설득력이 유지된다.

---

## 7. Phase 4 고도화 힌트 (참고 저장소)

- Depth **Metric Indoor** + revision SHA 고정
- Geometry Lite → 실측 CBM
- OWL-ViT Endpoint
- matching CP-SAT

자세한 대조: `reference/README.md`
