# 08 — 프론트엔드 UX (기사)

파일: `frontend/src/App.vue`, `frontend/src/components/CargoFillView.vue`.

---

## 1. 스택

Vue 3 + Vite + axios. 빌드 시 `VITE_KAKAO_JS_KEY`. nginx 정적 서빙.

---

## 2. 상태

```
gate: login → profile → route → app
app.tab: cargo | drive | ledger
```

하단 3탭은 `gate === 'app'` 에서 항상 보인다.

---

## 3. 탭

### 배차목록 `cargo`
터미널 지도 · 그룹 리스트 · 장바구니 독 · 최적배차 · 배차 확정.

### 운행 `drive`
- 지도 + 내비 오버레이 + `>` 20km
- 출도착 독 (출발지=현재 정차, 도착지=다음 스톱)
- 상차 사진 · CargoFillView (계획+실측)
- 복화 토스트 (수락)

### 정산 `ledger`
건별 + 합계.

---

## 4. 운행 중 복화 (핵심)

| 함수 | 역할 |
|------|------|
| `tripDestCode()` | 도착 스톱 코드 (stop-/via- 제외) |
| `simRemainingPercent()` | `100 − max(계획, 실측)` |
| `fetchNearbyLoadable` | `GET /api/dispatch/nearby-loadable` |
| `stepDriverAlongRoute` | 경로 20km 보간 |
| `insertAcceptedStopIntoTrip` | 계획 적재 합산, 경유는 **마지막 도착 앞** |
| `restitchTripRoute` | 도로 polyline만 재계산 |

`>` 는 `stopIndex`를 올리지 않는다. 그래서 경유를 `stopIndex+1`에 끼우면 부산→김천→부산이 된다. **도착(마지막) 앞**에만 붙인다.

---

## 5. 지도

1. `tab === 'drive'` 일 때만 Map 생성
2. `relayout` + ResizeObserver
3. 시연 핀: 기사 🚛, 인근 터미널 이름+fill%

---

## 6. 세션

```
sessionStorage moveai_session
localStorage moveai_active_trip_{truckId}
```

시연 epoch가 바뀌면 trip storage를 지운다.
