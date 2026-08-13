# 02 — PLAN / 구현 상태

초기 기록: 루트 `plan.md`, `answer.md`.  
**기준: 2026-08-13 시연 빌드.**

---

## 1. 완료

- [x] Compose · Nginx 20100 · `moveainetwork`
- [x] 기사 게이트 (로그인·프로필·터미널 출도착)
- [x] 하단 탭 배차목록 / 운행 / 정산 (항상 표시)
- [x] 터미널 핀 · 장바구니 · 배차 확정 · 카카오 도로 경로
- [x] LLM 최적배차 (담아도 장바구니 유지)
- [x] 상차 사진 → 공간 분석 · 계획+실측 적재 UI (경유 전부)
- [x] 운행 중 20km 전진(`>`) · 동일 도착 권역 토스트+핀+수락
- [x] 수락 시 계획 적재 반영 · 잔여 초과 물량 미제안
- [x] 경유는 최종 도착 앞에만 삽입 · 기존 출도착·실측 유지 · restitch
- [x] 시연 리셋 (공차 · OD 재시드 · 기사 운행/장바구니 클리어)
- [x] `/admin` 적재 배정 시뮬 (CBM/중량, 기사 디스패치와 분리)

---

## 2. 남은 과제 (Phase 4)

- [ ] Vertex에 Depth/Seg 실배포
- [ ] 컨테이너 YOLO `torchvision::nms` 불일치 해소
- [ ] 네이티브 카메라 / PWA
- [ ] GCP 운영 runbook 자동화

---

## 3. 산출물 위치

| 산출물 | 경로 |
|--------|------|
| Compose | `docker-compose.yml` |
| 공간 AI | `backend-ai/space_analyzer.py` |
| 배차·인근 | `DispatchController`, `DispatchCartService`, `OdDetourService` |
| 기사 UI | `frontend/src/App.vue`, `CargoFillView.vue` |
| 관리자 | `frontend-admin/` |
| 문서 | `README.md`, `docs/` |

---

## 4. 로컬 준비

1. `.env` — `VITE_KAKAO_JS_KEY`, `KAKAO_REST_KEY`
2. 카카오 콘솔 도메인 `http://localhost:20100`
3. `docker compose up -d --build`
4. Gemini용 ADC (브리핑·비전 융합)
