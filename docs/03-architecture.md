# 03 — 아키텍처

---

## 1. 논리 구성

```
브라우저 :20100
    → Nginx
         /        → frontend (Vue3)
         /admin/  → frontend-admin (React)
         /api     → backend-spring :8080
         /ai      → backend-ai :8000
                    ↓
         PostgreSQL ← db-import(oneshot CSV)
```

Spring이 FastAPI를 **내부 URL**로 호출한다.

- `http://backend-ai:8000/ai/analyze-image`
- `http://backend-ai:8000/ai/generate-briefing`

카카오 REST는 Spring → `apis.map.kakao.com` / directions.

---

## 2. 컨테이너

| Service | Container | 호스트 포트 | 역할 |
|---------|-----------|-------------|------|
| frontend | hist-moveai-frontend | **20100** | 기사 Vue + 게이트웨이(`/api`,`/ai`,`/admin`) |
| frontend-admin | hist-moveai-frontend-admin | (내부) | 관리자 React |
| backend-spring | hist-moveai-backend-spring | **21808** | 도메인 API |
| backend-ai | hist-moveai-backend-ai | **21800** | 공간 AI + Gemini |
| db | hist-moveai-db | **21432** | Postgres 15 |
| db-import | hist-moveai-db-import | — | 기동 시 CSV 적재 후 exit |

네트워크 이름: **`moveainetwork-hist`** (기존 30100의 `moveainetwork`와 분리, DNS 충돌·502 방지).

---

## 3. 핵심 시퀀스

### 3.1 잔여공간

```
UI 파일선택
 → POST /api/load/upload (multipart)
 → Spring → POST /ai/analyze-image
 → space_analyzer: Depth + OpenCV + Gemini/YOLO 융합 + pack
 → trucks.remaining_volume_percent 갱신
 → load_history INSERT
 → logs[] → UI 처리과정
```

### 3.2 복화 제안

```
시연 모달 / 외부
 → POST /api/dispatch/propose
 → 체적 합산·fill%·여유 기사 필터·경로 유사
 → (optional) Gemini briefing
 → cargo_requests PENDING
 → 기사 cargo-feed 폴링으로 노출
```

### 3.3 수락 (목록/장바구니)

```
POST /api/dispatch/{id}/accept 또는 accept-batch
 → ASSIGNED
 → 장바구니 확정 시 preview 경로로 운행 시작
```

### 3.4 운행 중 인근 수락

```
> 20km 또는 운행 시작
 → GET /nearby-loadable (반경·도착권역·계획잔여)
 → 토스트 수락
 → accept (remainingPercent + fillPercent)
 → 계획 적재 합산, 경유를 최종 도착 앞에 삽입
 → POST /restitch-route
```

---

## 4. 책임 경계

| 컴포넌트 | 함 | 안 함 |
|----------|----|------|
| Vue | UX, 세션스토리지, 맵 SDK, 로그 표시 | 비즈니스 계산 |
| Spring | 배차·정산·내비·업로드 오케스트레이션 | 딥러닝 추론 |
| FastAPI | 이미지 3단·브리핑·CSV 풀 | 배차 트랜잭션 |
| Postgres | 상태·이력·체적 | — |

---

## 5. 보안·자격증명 (MVP)

- Kakao 키: `.env` → compose build/env
- GCP ADC: 호스트 `%APPDATA%/gcloud/...` 를 AI 컨테이너에 마운트
- CORS: Spring `/api/**` `*`, FastAPI `*`
- 인증: MVP는 전화+트럭번호 로그인(세션스토리지). JWT 없음.
