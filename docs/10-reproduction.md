# 10 — 재현 가이드 (에이전트용)

이 문서 + 다른 `docs/*.md`만으로 **유사 소스 트리**를 생성할 때의 체크리스트.

---

## 1. 목표 디렉터리

```
moveAI/
├── .env.example
├── docker-compose.yml
├── nginx/default.conf
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.js
│   └── src/App.vue | main.js
├── backend-spring/
│   ├── build.gradle
│   └── src/main/java/com/moveai/backend/
│       ├── BackendApplication.java
│       ├── config/WebConfig.java
│       ├── controller/{Health,Driver,Load,Dispatch}Controller.java
│       ├── entity/*
│       ├── repository/*
│       └── service/{Calculation,KakaoNavi,RouteMatch}Service.java
├── backend-ai/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── space_analyzer.py
│   └── utils.py
├── db-init/
│   ├── init.sql
│   ├── import_volumetric.sh
│   └── build_volumetric_groups.sh
└── docs/   # 본 문서들
```

---

## 2. 구현 순서 (권장)

1. Compose + Nginx 라우팅 + 빈 health
2. Postgres schema + Truck/CargoRequest/LoadHistory
3. Driver login/profile/route
4. Dispatch stations/propose/accept/feed/ledger + CalculationService
5. KakaoNaviService (키 없으면 mock path)
6. FastAPI health + analyze stub → space_analyzer 3단
7. LoadController 연동 + UI 게이트/탭
8. Gemini briefing
9. db-import volumetric groups
10. 지도 relayout·처리과정 UX 폴리시

---

## 3. 완료 정의 (DoD)

- [ ] `30100`에서 로그인→프로필→OD→3탭
- [ ] propose 후 cargo-feed에 카드
- [ ] accept 후 지도 경로 (키 있을 때)
- [ ] upload 후 remaining 갱신 + `[1/3][2/3][3/3]` 로그
- [ ] ledger 합계
- [ ] `/ai/health`에 space_engine / briefing_engine
- [ ] Gemini는 브리핑만, 공간 분석 미사용

---

## 4. 테스트 커맨드 예

```bash
curl -s http://localhost:30100/ai/health
curl -s -X POST http://localhost:30100/api/drivers/login \
  -H "Content-Type: application/json" \
  -d '{"phone":"01012345678","truckNumber":"TEST100","driverName":"테스터"}'
# 이미지
curl -s -X POST http://localhost:30100/ai/analyze-image -F "file=@sample.jpg"
```

---

## 5. 하지 말 것

- 잔여공간을 Gemini Vision으로 대체
- 숨긴 DOM에서 카카오맵 초기화
- 포트를 30000대 기존 서비스와 충돌되게 설정
- 참고 저장소(`reference/`)를 그대로 덮어쓰기 (스택이 React/Firestore로 다름)

---

## 6. 문서 우선순위 (충돌 시)

1. `06-api.md` / `05-ai-spec.md` / `04-features.md`
2. `03-architecture.md`
3. 루트 `RFP.md` 원문
4. `reference/` (아이디어만)
