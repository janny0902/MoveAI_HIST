# moveAI

간선 택배 트럭의 **잔여 공간**을 사진으로 읽고, **같은 방향 복화**를 제안·수락하는 웹앱입니다.

저장소: [janny0902/MoveAI_HIST](https://github.com/janny0902/MoveAI_HIST)

로컬/VM: `http://HOST:30100` · 기사 앱 `/` · 관리자 `/admin`

---

## 한 줄 시나리오

부산→서울 11톤 기사가 상차 사진을 올리면 적재율을 계산하고, 운행 중 20km 안·같은 목적지 물량을 토스트로 알려 줍니다. 수락하면 계획 적재에 더하고, 지금 출도착은 유지한 채 **최종 도착 앞**에 경유를 넣습니다.

---

## 구성

```
:30100 Nginx (moveainetwork)
  /        Vue3 기사 앱
  /admin   React 관리자 (적재 배정 시뮬)
  /api     Spring Boot
  /ai      FastAPI (공간 분석)
           PostgreSQL + Volumetric CSV import
```

| 역할 | 기술 |
|------|------|
| 기사 UI | Vue 3 |
| 관리자 UI | React |
| 도메인 API | Spring Boot |
| 공간 AI | FastAPI · Depth Anything · OpenCV · Gemini Vision · YOLO-seg |
| 지도 | 카카오맵 JS + REST 길찾기 |
| 실행 | Docker Compose · 포트 **30100** |

---

## 새 VM 배포 (권장)

```bash
# 1) 소스 + Volumetric data 동기화 (이 저장소 전체)
git clone https://github.com/janny0902/MoveAI_HIST.git
cd MoveAI_HIST
# Volumetric data/*.csv 가 없으면 별도 scp (약 100MB+)

# 2) 환경변수
cp .env.example .env
# VITE_KAKAO_JS_KEY, KAKAO_REST_KEY 입력
# GOOGLE_ADC_PATH=/home/USER/.config/gcloud/application_default_credentials.json

# 3) 카카오 콘솔 Web 도메인: http://EXTERNAL_IP:30100

# 4) 기동 (최초 db-import 는 CSV 규모에 따라 수분~십수분)
chmod +x scripts/up.sh
./scripts/up.sh

# 5) 확인
curl -sS http://localhost:30100/api/health
curl -sS http://localhost:30100/ai/health
```

선택: CSV import 대신 스냅샷 덤프 복원

```bash
# db-dumps/moveaidb.dump 를 올려 둔 경우
./scripts/up.sh
./scripts/restore-db-dump.sh
docker compose restart backend-spring
```

방화벽: TCP **30100** 오픈.

---

## 로컬 실행

```bash
cp .env.example .env
# 키 입력 후
docker compose up -d --build
# 또는
./scripts/up.sh
```

---

## 문서

구현 기준 SSOT는 [`docs/`](docs/README.md) 입니다.

| 문서 | 내용 |
|------|------|
| [RFP.md](RFP.md) | 원본 요구 |
| [docs/01-rfp.md](docs/01-rfp.md) | 요구 ↔ 현재 구현 |
| [docs/03-architecture.md](docs/03-architecture.md) | MSA · 컨테이너 |
| [docs/04-features.md](docs/04-features.md) | 기능·시연 규칙 |
| [docs/05-ai-spec.md](docs/05-ai-spec.md) | 공간 AI |
| [docs/06-api.md](docs/06-api.md) | API |
| [docs/08-frontend.md](docs/08-frontend.md) | 기사 UX |
| [docs/09-ops.md](docs/09-ops.md) | Docker · 환경변수 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 한 장 요약 |

---

## 요구 스택 (RFP)

Vue3 · Spring Boot · FastAPI · PostgreSQL · Nginx · Docker Compose · 포트 3만번대 · 네트워크 `moveainetwork`
