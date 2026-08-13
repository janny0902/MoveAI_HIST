# 참고용 — 다른 개발자 MoveAI 작업분

> 원본: https://github.com/KimYeounHong97/MoveAI.git  
> 로컬 경로: `reference/KimYeounHong97-MoveAI/`  
> 목적: **병합이 아니라 참고**. 우리 MVP(`d:\moveAI`)와 대조하며 가져올 아이디어·코드만 고른다.

---

## 폴더 구조 (원본 그대로)

```
reference/
├── README.md                          ← 이 파일 (대응표·읽는 순서)
└── KimYeounHong97-MoveAI/
    ├── Markdown.md                    ★ 설계서 v3.1 (가장 먼저)
    ├── README.md                      원본 저장소 소개
    ├── docs/                          제약·인프라·데이터 모델
    │   ├── 00-new-project-setup.md
    │   ├── 01-environment.md
    │   ├── 02-gcp-infra.md
    │   ├── 03-ai-models.md            ★ Depth / OWL-ViT 계약
    │   ├── 04-vision-processor.md
    │   ├── 05-matching-processor.md
    │   ├── 06-frontend.md
    │   ├── 07-operations.md
    │   ├── 08-open-issues.md
    │   └── 09-data-model.md
    ├── vision-processor/              ★ 잔여공간 (Cloud Run)
    │   ├── model_clients/             Depth + OWL-ViT
    │   ├── geometry_lite/             포인트클라우드·CBM
    │   └── infra/
    ├── matching-processor/            ★ 화물 조합 (OR-Tools CP-SAT)
    │   ├── solver.py
    │   └── infra/
    ├── frontend/                      React PWA 촬영 앱
    │   └── UI_CONTRACT.md
    └── tools/                         시드·운송장 생성 스크립트
```

---

## 우리 프로젝트 ↔ 참고 저장소 대응

| 우리 (`moveAI`) | 참고 (`KimYeounHong97`) | 참고할 때 |
|-----------------|-------------------------|-----------|
| `backend-ai/space_analyzer.py` | `vision-processor/` | Depth Metric Indoor, Geometry Lite(CBM), OWL-ViT |
| Depth Anything V2 Small (상대) | `model_clients/depth_model.py` | **Metric Indoor** + revision 고정 |
| YOLOv8n-Seg | `model_clients/owlvit_client.py` | 개방어휘 탐지(OWL-ViT) 대안 |
| py3dbp 융합 | `geometry_lite/` | voxel CBM·평면 피팅 등 정밀 체적 |
| Spring 배차 + 규칙 매칭 | `matching-processor/solver.py` | **OR-Tools CP-SAT** 화물 조합 |
| Vue 기사 앱 | `frontend/` | 촬영 PWA, `UI_CONTRACT.md` |
| `ARCHITECTURE.md` | `Markdown.md` + `docs/` | 설계·제약 ID 체계 |
| Docker Compose 로컬 | `*/infra/*.sh` | Cloud Run / Eventarc / Pub/Sub 배포 |

### 아키텍처 차이 (한눈에)

| | 우리 MVP | 참고 저장소 |
|--|----------|-------------|
| 진입 | Nginx :30100 | Cloud Run PWA |
| 비전 | FastAPI 컨테이너 내 3단 | GCS → Eventarc → vision-processor |
| 매칭 | Spring + DB + 경로유사 | Pub/Sub → matching (Firestore + CP-SAT) |
| Depth | Depth-Anything-V2-**Small** | Depth-Anything-V2-**Metric-Indoor-Small** + SHA 고정 |
| Seg/Detect | YOLOv8n-Seg (+ OpenCV 융합) | **OWL-ViT** Vertex Endpoint |
| Pack | py3dbp | Geometry Lite → CBM 후 CP-SAT |

---

## 추천 읽는 순서

1. `KimYeounHong97-MoveAI/README.md` — 전체 그림  
2. `KimYeounHong97-MoveAI/Markdown.md` — 설계서  
3. `docs/03-ai-models.md` — 모델 실측 계약  
4. `vision-processor/model_clients/depth_model.py` — Depth 구현  
5. `vision-processor/geometry_lite/pipeline.py` — CBM 파이프라인  
6. `matching-processor/solver.py` — CP-SAT 목적함수  
7. `docs/08-open-issues.md` — 남은 이슈 (우회시간·목적지 시드 등)

우리 쪽 현재 구조는 루트 `ARCHITECTURE.md` 및 **`docs/`** 와 같이 본다.
(에이전트 재현용 SSOT: `docs/README.md`)

---

## 가져오면 좋은 후보 (우선순위)

1. **Depth Metric Indoor + revision 고정** — 재현성·실측 m 단위  
2. **geometry_lite** — 상대깊이 %보다 CBM 산출에 유리  
3. **matching CP-SAT** — 복수 화물 조합·우회 비용 목적함수  
4. **docs 제약 ID 형식** — 운영/디버깅 문서화  
5. OWL-ViT — Vertex GPU Endpoint 비용 있음 → 시연 후 정리 필요 (`docs/07`)

---

## 주의

- 이 폴더는 **참고용 스냅샷**이다. upstream 갱신이 필요하면 원본 git에서 다시 clone 후 `reference/KimYeounHong97-MoveAI`만 교체한다.  
- 참고 쪽 `frontend`는 React, 우리는 Vue — UI를 통째로 덮어쓰지 말고 계약(`UI_CONTRACT.md`)·플로우만 참고.  
- GCP Eventarc/Firestore 전제는 우리 Docker Compose MVP와 다르다. 로컬 이식 시 인터페이스만 맞출 것.
