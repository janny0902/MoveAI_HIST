# 00 — AI 에이전트 브리프

새 에이전트에게 `docs/`만 주고 현재 MVP를 이어서 만들 때의 지시서.

---

## 제품 한 줄

간선 기사가 **상차 사진으로 잔여공간을 측정**하고, 배차목록에서 복화를 담은 뒤, **운행 중 20km·같은 목적지 물량**을 수락해 경유를 끼우고 정산하는 웹앱.

## 스택 (고정)

| 계층 | 기술 |
|------|------|
| 기사 UI | Vue 3, 카카오맵 JS |
| 관리자 | React `/admin` (적재 시뮬) |
| 도메인 | Spring Boot 3, JPA, PostgreSQL |
| AI | FastAPI · Depth Anything · OpenCV · Gemini Vision 융합 · YOLO-seg |
| 인프라 | Docker Compose, Nginx, **20100**, `moveainetwork` |

## 규칙

1. 공간 분석은 Depth + OpenCV + (가능하면) Gemini/YOLO. 난수 적재율 금지.
2. 깊이는 **바닥** 기준. 철벽/녹벽을 화물로 뒤집지 말 것.
3. 운행 중 제안: 20km · 도착 권역 · **계획 잔여** 이하만.
4. 토스트 수락 경유는 **최종 도착 앞**. 기존 운행·실측을 리셋하지 말 것.
5. 하단 탭 배차목록/운행/정산은 앱에서 항상 보이게.
6. 배정은 PENDING→ASSIGNED 원자적.
7. `/admin`은 용량 시뮬이지 기사 위치 디스패치가 아님.

## 유저 플로우

```
로그인 → 프로필 → 터미널 출도착
 → 배차목록: 핀·장바구니·최적배차·확정
 → 운행: 사진(계획+실측) · 출발/도착 · > 20km
 → 토스트 수락 → 계획 합산 · 도착 앞 경유 · restitch
 → 정산
```

## 검증

- `GET /api/dispatch/nearby-loadable?truckId=1&lat=35.1362&lng=128.83&remainingPercent=100&destinationCode=001` → 부산권 터미널
- 계획 90%면 remainingPercent=10 에서 50% 물량 0건
- 수락 후 경로가 `부산 → (기존 경유) → 신규 → 서울` (뒤로 꺾지 않음)
- `POST /api/load/upload` logs에 파이프라인 단계
