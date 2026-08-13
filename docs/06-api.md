# 06 — 인터페이스 명세 (OpenAPI 스타일)

> SpringDoc 미사용 MVP. 이 문서가 **스웨거 대체 SSOT**다.  
> Base (외부): `http://localhost:20100`  
> Spring 직접(호스트): `http://localhost:21808` · FastAPI: `http://localhost:21800`  
> 컨테이너 내부: `http://backend-spring:8080` / `http://backend-ai:8000`

---

## 1. 라우팅

| Prefix | 업스트림 |
|--------|----------|
| `/` | frontend |
| `/api/*` | Spring Boot |
| `/ai/*` | FastAPI |

---

## 2. FastAPI

### GET `/ai/health`
**Response**
```json
{
  "status": "ok",
  "vertex_ai": "connected|pending_credentials",
  "project": "string",
  "space_engine": "depth-anything → yolov8-seg → 3d-packing",
  "briefing_engine": "gemini-2.5-flash|fallback",
  "csv_exists": true
}
```

### GET `/ai/cargo-pool`
CSV 기반 샘플 풀 (최대 30).  
**Response**: `{ cargo_pool[], truck_capacity_m3, truck_spec }`

### POST `/ai/generate-briefing`
**Body**
```json
{ "profit": 120000, "extra_distance": 15.2, "extra_time": 25, "esg": 96.0 }
```
**Response**
```json
{ "briefing": "string", "source": "gemini|fallback" }
```

### POST `/ai/analyze-image`
`multipart/form-data`: `file` (image)  
**Response**: [05-ai-spec.md](05-ai-spec.md) 출력 스키마 + `filename`, `space_pipeline`

---

## 3. Spring — Health

### GET `/api/health`
→ `"Backend Spring Boot is running!"`

---

## 4. Spring — Drivers (`/api/drivers`)

### POST `/api/drivers/login`
```json
{ "phone": "010...", "truckNumber": "12가3456", "driverName": "optional" }
```
**Response**: truckView + `isNew`, `needProfile`, `needRoute`, `message`

### GET `/api/drivers/{id}`
truckView + flags

### POST `/api/drivers/{id}/profile`
```json
{
  "driverName": "김기사",
  "capacityTons": 11,
  "capacityM3": 50,
  "vehicleType": "윙바디",
  "remainingVolumePercent": 100
}
```

### POST `/api/drivers/{id}/route`
```json
{ "originCode": "200", "destinationCode": "001" }
```

### GET `/api/drivers/`
`{ drivers[], count }`

**truckView 필드**: `truckId`, `driverName`, `phone`, `truckNumber`, `capacityTons`, `capacityM3`, `vehicleType`, `profileCompleted`, `originCode`, `originName`, `destinationCode`, `destinationName`, `remainingVolumePercent`, `occupiedVolumePercent`, `status`

---

## 5. Spring — Load

### POST `/api/load/upload`
`multipart`: `file`, `truckId` (default 1)  
내부적으로 FastAPI analyze 호출.

**Response**
```json
{
  "historyId": 1,
  "remainingVolumePercent": 70.5,
  "occupiedVolumePercent": 29.5,
  "status": "string",
  "verifyStatus": "MATCHED|OVERLOAD_SUSPECTED|UNDERLOAD_SUSPECTED|NO_EXPECTED",
  "expectedAddedFillPercent": null,
  "baselineOccupiedPercent": null,
  "guide": "string",
  "engine": "string",
  "pipeline": ["depth-anything", "yolov8-seg", "3d-packing"],
  "logs": ["string"]
}
```

---

## 6. Spring — Dispatch (`/api/dispatch`)

### GET `/api/dispatch/stations`
```json
{ "stations": [{ "code": "BUSAN", "name": "부산", "address": "...", "lat": 0, "lng": 0 }] }
```

### GET `/api/dispatch/cargo-groups`
적재율 그룹 목록 (5/10/30/50/90).  
`{ groups[], truck_capacity_m3, truck_spec }`

### GET `/api/dispatch/cargo-groups/{id}/items`
그룹 상세 + cargo_pool

### GET `/api/dispatch/cargo-pool?limit=&source=`
원본 체적 샘플

### POST `/api/dispatch/propose`
```json
{
  "originCode": "GIMCHEON",
  "destinationCode": "SEOUL",
  "viaCodes": [],
  "groupId": 3,
  "selectedCargo": [],
  "fee": 150000
}
```
**Response (요약)**: requestId, fillPercent, fee, netProfit, esg, briefing, eligibleDrivers/Count, logs, matched 여부 등

### POST `/api/dispatch/{id}/accept`
```json
{
  "truckId": 1,
  "skipOdAdvance": true,
  "remainingPercent": 40.0,
  "fillPercent": 25.2
}
```
`remainingPercent`가 있으면 트럭 DB 잔여 대신 계획 잔여로 과적 거부.  
**Response**: `status`=`ASSIGNED|INSUFFICIENT_SPACE|ALREADY_ASSIGNED`, navi, `stops[]`, `ledgerAdded`

### POST `/api/dispatch/accept-batch`
```json
{ "truckId": 1, "requestIds": [23, 25] }
```

### POST `/api/dispatch/preview-cart`
```json
{ "truckId": 1, "odGroupIds": [96, 98] }
```
→ `path[]`, `stops[]`, `totalKm`, `extraKm`, `durationMin`

### POST `/api/dispatch/optimal-plan`
LLM 최적배차 플랜 (기사 출도착 기준).

### GET `/api/dispatch/nearby-loadable`
Query: `truckId`, `lat`, `lng`, `radiusKm=20`, `remainingPercent`, `destinationCode`  
동일 도착 권역 · fill ≤ rem · dist ≤ radius(+0.5).  
`destinationRegion`: `SEOUL` | `BUSAN` | …

### POST `/api/dispatch/restitch-route`
```json
{ "stops": [{ "code": "200", "name": "...", "lat": 0, "lng": 0, "role": "출발" }] }
```
순서 그대로 카카오 구간을 이어 붙인다 (재정렬 없음).

### POST `/api/dispatch/demo-reset`
경부 축 OD 재시드 · 전 차량 공차 · 정산 삭제. `{ epoch }`

### GET `/api/dispatch/demo-state`
`{ epoch }`

### GET `/api/dispatch/terminals` · `/api/dispatch/terminals-with-cargo`
시연 터미널 / PENDING 있는 터미널.

### GET `/api/dispatch/groups-by-terminal`
`truckId`, `terminalCode`, `page` — 잔여 가능한 PENDING 그룹.

### POST `/api/dispatch/{id}/reject`
```json
{ "truckId": 1 }
```
→ `DISMISSED` 또는 `ALREADY_ASSIGNED` (요청 row는 PENDING 유지 가능)

### GET `/api/dispatch/cargo-feed?truckId=&sinceId=`
```json
{
  "items": [ /* cargo cards */ ],
  "notifications": [],
  "remainingVolumePercent": 70,
  "count": 0
}
```

### GET `/api/dispatch/offers?truckId=`
cargo-feed + `offers` 별칭

### GET `/api/dispatch/truck-status?truckId=`
트럭 맵핑 상태

### POST `/api/dispatch/truck/reset-empty?truckId=`
잔여 100% + load_history 삭제 (데모용)

### GET `/api/dispatch/drivers`
기사 목록

### GET `/api/dispatch/ledger?truckId=`
```json
{
  "entries": [{
    "id": 1,
    "route": "부산→김천→서울",
    "income": 150000,
    "expense": 12000,
    "netProfit": 138000,
    "esgReductionKg": 96.0
  }],
  "totalIncome": 0,
  "totalExpense": 0,
  "netProfit": 0,
  "dailyEsgKg": 0,
  "entryCount": 0
}
```

---

## 7. Cargo card (feed item) 주요 필드

`requestId`, `origin`, `destination`, `via`, `boxCount`, `totalVolumeM3`, `fillPercentOf11t`, `proposedFee`, `extraDistanceKm`, `extraFuelCost`, `netProfit`, `esgReductionKg`, `briefing`/`message`

---

## 8. 에러·HTTP

- MVP는 대체로 200 + body 내 status 코드 문자열
- RestTemplate AI 호출 read timeout: **3분** (Depth/YOLO 첫 추론)
- 프론트 업로드 axios timeout: **180초** 권장

---

## 9. (선택) SpringDoc 도입 시

에이전트가 스웨거 UI를 붙일 경우:

```gradle
implementation 'org.springdoc:springdoc-openapi-starter-webmvc-ui:2.3.0'
```

- UI: `/api/swagger-ui.html` 또는 `/swagger-ui.html` (context 주의)
- 이 문서의 path/스키마를 `@Operation`/`@Schema`로 옮기면 된다.
