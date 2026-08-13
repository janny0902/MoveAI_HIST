# moveAI

간선 택배 트럭의 **잔여 공간**을 사진으로 읽고, **같은 방향 복화**를 제안·수락하는 웹앱입니다.

해커톤 제출 저장소: [janny0902/MoveAI_HIST](https://github.com/janny0902/MoveAI_HIST)

접속: `http://localhost:20100` · GCP `http://EXTERNAL_IP:20100`  
(기존 시연 스택 `30100`과 **동시 기동** — 이 저장소는 **20100만** 사용)

---

## 한 줄 시나리오

부산→서울 11톤 기사가 상차 사진을 올리면 적재율을 계산하고, 운행 중 20km 안·같은 목적지 물량을 토스트로 알려 줍니다. 수락하면 계획 적재에 더하고, 지금 출도착은 유지한 채 **최종 도착 앞**에 경유를 넣습니다.

---

## 구성

```
:20100 frontend nginx (게이트웨이, hist-moveai-nginx 없음)
  /        Vue3 기사 앱
  /admin   → frontend-admin
  /api     → Spring (:21808)
  /ai      → FastAPI (:21800)
           PostgreSQL (:21432)
네트워크: moveainetwork-hist (30100의 moveainetwork 와 분리)
```

| 역할 | 기술 |
|------|------|
| 기사 UI | Vue 3 |
| 관리자 UI | Vue 3 (`/admin`) |
| 도메인 API | Spring Boot |
| 공간 AI | FastAPI · Depth Anything · OpenCV · Gemini Vision · YOLO-seg |
| 지도 | 카카오맵 JS + REST 길찾기 |
| 실행 | Docker Compose · 포트 **20100** |

---

## 기사 앱 (현재 시연)

1. 로그인 → 차량 프로필 → 출도착 터미널 (부산 200 → 서울 001)
2. **배차목록**: 터미널 핀 · 장바구니 · LLM 최적배차 · 배차 확정
3. **운행**: 카카오 내비 · 하단 출도착 · 상차 사진(계획+실측) · 지도 `>` 로 경로 20km 전진
4. 반경 20km · **같은 도착 권역**(서울 001/008, 부산 200/201) · **계획 잔여**에 들어가는 물량만 토스트+핀
5. 토스트 **수락**: 기존 운행 유지, 경유는 최종 도착 앞에만 추가, 내비 재계산
6. **정산**: 건별 수입·유류비·순이익·ESG

시연 리셋은 관리자/시연 API로 공차·PENDING 물량을 되돌립니다.

---

## 공간 분석

상차 사진 → `POST /api/load/upload` → FastAPI `space_analyzer`

- 깊이: Depth Anything V2 (바닥 기준) + OpenCV 폴백
- 영역: YOLO-seg + OpenCV (박스 vs 철벽/녹벽)
- 보조: Gemini Vision JSON (잘림·재시도 파싱)
- 결과: 적재율% · 잔여% · 처리 과정 로그

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

## 실행

```bash
cp .env.example .env
# VITE_KAKAO_JS_KEY, KAKAO_REST_KEY 입력
docker compose up -d --build
```

카카오 콘솔 Web 도메인에 `http://localhost:20100` 을 등록합니다.

---

## 요구 스택 (RFP)

Vue3 · Spring Boot · FastAPI · PostgreSQL · Nginx · Docker Compose · 포트 **20100** · 네트워크 `moveainetwork-hist`
