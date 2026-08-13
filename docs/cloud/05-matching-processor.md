# 05. matching-processor 구현 제약

담당: `space-geometry-ready` 수신 → 회랑 후보 조회 → 필터 → 우회시간 → CP-SAT → 결과 저장.
설계서 D4(M1-M6)에 해당한다.

**이 서비스는 이미지·depth map·point cloud에 접근하지 않는다**(설계서 1.3). 문서상의 약속이 아니라
`matching-sa`에 storage 권한을 주지 않아 IAM으로 막는다([GCP-16](02-gcp-infra.md#gcp-16-matching-sa에-storage-권한을-주지-않는다)).

## 엔드포인트

| 메서드 | 경로 | 용도 |
|---|---|---|
| GET | `/` | 헬스체크 |
| POST | `/` | **Pub/Sub push 수신점** |
| POST | `/v1/match` | 데모용 직접 호출(중복 방지 없이 매번 계산) |
| POST | `/v1/trucks/{truck_id}/match` | **사진 없이 차량 제원만으로 계산** — [MAT-14](#mat-14-사진-없이-차량-제원만으로-매칭한다) |
| GET | `/v1/results/{photo_id}` | 결과 조회 |
| GET | `/v1/cargos` | 대기 운송장 목록 — 페이지·출발/도착 터미널 필터 |
| POST | `/v1/cargos` | 운송장 건당 등록(화주사 웹 폼) |
| POST | `/v1/cargos:batch` | 운송장 벌크 등록(호출당 500건) |
| POST | `/v1/waybills` | 체적 운송장(17컬럼) 건당 등록 |
| POST | `/v1/events/cargo-file` | **Eventarc 수신점** — 적재 버킷에 올라온 CSV/JSONL |
| GET / POST | `/v1/terminals` | 작업터미널 코드 → 좌표 등록·조회 |

`POST /v1/trucks/{truck_id}/match` 쿼리 파라미터:

| 파라미터 | 기본 | 뜻 |
|---|---|---|
| `candidates` | `MAX_CANDIDATE_FETCH` | 검토할 후보 상한. `CANDIDATE_FETCH_MAX`를 넘으면 그 값으로 맞춘다 |
| `palletized` | `false` | 파렛트 적재 기준으로 용량을 계산한다([MAT-16](#mat-16-파렛트-적재는-용량을-29-60-깎는다)) |

---

### MAT-01 M2를 Geohash 대신 위경도 박스로 구현했다

- **설계서** M2는 "Firestore Geohash 조회".
- **현실** `pending_cargos`가 10만 건인데 `geohash` 필드가 없다. 만들려면 전량 백필이 필요하다.
- **대응** Firestore가 다중 부등호 필터를 지원하므로 위경도 박스 쿼리로 같은 목적을 달성한다.

```
status == "WAITING"
  AND pickup_lat BETWEEN lat_min AND lat_max
  AND pickup_lng BETWEEN lng_min AND lng_max
```

- 복합색인 `(status, pickup_lat, pickup_lng)`이 필요하다([GCP-13](02-gcp-infra.md#gcp-13-firestore-다중-부등호는-복합색인이-필요하고-빌드에-시간이-걸린다)).
- 박스는 반경의 **상위집합**이므로 정확한 반경 판정은 M3에서 haversine으로 마무리한다.
- 색인이 없으면 `FAILED_PRECONDITION`을 그대로 올려 신규 추천을 중단한다. **10만 건 전수 조회로 조용히 넘어가지 않는다.**
- `MAX_CANDIDATE_FETCH=500`으로 쿼리 자체에도 상한을 둔다.

**적용 위치** `firestore_client.query_corridor_cargos`, `geo.bounding_box`

---

### MAT-02 M3 후보 축소

- 박스 결과에 haversine 반경(`CORRIDOR_RADIUS_KM=30`)을 적용한다.
- `deadline_at`이 이미 지난 후보를 제외한다(pickup time window).
- 거리순으로 정렬해 `MAX_ROUTE_CANDIDATES=20`만 남긴다. 설계서 5.4 "Routes API는 Top 10-20으로 제한".

**적용 위치** `main.py`의 `_prefilter`

---

### MAT-03 경로 API 미구성과 실패를 구분한다

설계서는 Google Routes API를 지정했지만 **카카오모빌리티 다중 목적지 길찾기**를 쓴다.
지도를 카카오로 통일하기로 해서, 주소 검색과 같은 REST 키 하나로 처리한다.

```
POST https://apis-navi.kakaomobility.com/v1/destinations/directions
Authorization: KakaoAK {REST_API_KEY}

{"origin": {"x": lng, "y": lat},
 "destinations": [{"key": cargo_id, "x": lng, "y": lat}, ...],   // 최대 30개
 "radius": 10000, "priority": "TIME"}

→ {"routes": [{"key": ..., "result_code": 0, "summary": {"duration": 초, "distance": m}}]}
```

**호출 3회로 순수 우회시간을 뽑는다.**

1. 현재위치 → 각 상차지
2. **목적지 → 각 상차지** (역방향)
3. 현재위치 → 목적지 (기준선)

`우회시간 = (1) + (2) - (3)`

2번이 역방향인 이유는 다중 목적지 API의 출발지가 하나뿐이기 때문이다. 상차지마다 호출하면
N번이 된다. 편도 통행 구간에서는 실제와 다를 수 있으나 후보 **순위**를 매기는 용도라
이 근사를 받아들였다.

개별 목적지가 실패하면(`result_code != 0`, 주변에 도로 없음 등) 그 후보만 직선거리 추정으로
채운다. **0으로 두면 우회가 공짜인 것처럼 보여 solver가 잘못 선택한다.**

- **설계서 5.8** "Routes API 실패 → 유효한 직전 cache가 없으면 신규 추천 중단".
- **해석** 이건 **실패**를 다루지 **미구성**을 다루지 않는다. 두 경우를 구분했다.

| 상황 | 동작 | `route_source` |
|---|---|---|
| `KAKAO_REST_API_KEY` 있음 + 성공 | 카카오 다중 목적지 길찾기 3회 호출로 순수 우회시간 산출 | `KAKAO_NAVI` |
| `KAKAO_REST_API_KEY` 있음 + 실패 | **신규 추천 중단**(fail-closed) | - |
| `KAKAO_REST_API_KEY` 없음 | 직선거리 추정으로 degrade | `HAVERSINE_FALLBACK` |

폴백을 쓸 때 결과에 `route_source`를 남겨 **추정치가 실측처럼 보이지 않게** 한다. UI도 이 값을 보고
안내 문구를 띄운다.

**현재 상태** 키가 설정돼 있지 않아 항상 `HAVERSINE_FALLBACK`이다([08-open-issues.md](08-open-issues.md)).

**적용 위치** `routes_client.py`, `geo.detour_seconds_via`

---

### MAT-04 CP-SAT 모델

설계서 5.2 구현. 정수만 다루므로 CBM→liter, 시간→초, 중량→kg으로 변환한다.

**제약**
- 체적: `sum(volume_liter_i * x_i) <= usable_free_liter`
- 중량: `sum(weight_kg_i * x_i) <= remaining_weight_kg`
- 우회시간 합산 예산: `sum(detour_seconds_i * x_i) <= MAX_DETOUR_SECONDS`(3600)

**목적함수**
```
maximize sum_i x_i * (revenue_krw_i
                      + FILL_REWARD_PER_LITER * volume_liter_i
                      - DETOUR_PENALTY_PER_SECOND * detour_seconds_i
                      - geometry_risk_penalty)
```

**탐색** `max_time_in_seconds = 1.0`, `FEASIBLE` 허용.
`OPTIMAL`/`FEASIBLE`이 아니면 빈 선택으로 끝내 설계서 5.8의 "UNKNOWN/timeout 시 신규 can_load=false"를 지킨다.

---

### MAT-05 완전한 VRP는 구현하지 않았다

설계서 5.2가 나열한 경로 제약 중 **미구현**:

- 선택 node의 in/out flow
- subtour 제거
- 최종 목적지 도착 제한시간

따라서 CP-SAT는 화물 **선택**만 최적화하고, `pickup_order`는 현재 위치에서 시작하는
**최근접 이웃 순서**다. 최적 경로가 아니며 이 순서의 총 주행시간은 보장되지 않는다.

**적용 위치** `solver.py`의 `_order_pickups`

---

### MAT-06 LIMITED 품질 처리

설계서 4.10 "0.50 <= score < 0.70 → 추가 안전계수 적용 후 제한 Matching".

- `usable_free_cbm *= LIMITED_EXTRA_SAFETY_FACTOR`(0.80)
- 목적함수에 `GEOMETRY_RISK_PENALTY_LIMITED`(50000) 부과

`REJECTED`는 solver를 돌리지 않고 즉시 `can_load=false`.

---

### MAT-07 event_id 기반 중복 처리 방지

`processed_events/{event_id}`를 `create()`로 원자적으로 잡는다. Pub/Sub는 at-least-once라
같은 이벤트가 두 번 올 수 있다(설계서 5.8).

Vision의 photo_id 점유와 달리 **실패 시 해제하지 않는다.** Matching은 재계산이 저렴하고,
`/v1/match`로 언제든 다시 돌릴 수 있기 때문이다.

**적용 위치** `firestore_client.claim_event`

---

### MAT-08 fail-closed 사유 목록

전부 `can_load=false`로 끝나며 `failure_reason`에 코드를 남긴다. 프론트가 이 코드를 문장으로 바꾼다.

| 코드 | 의미 |
|---|---|
| `quality_rejected` | `quality_status == REJECTED` |
| `truck_spec_not_found` | `trucks` 문서 없음 또는 `max_payload_kg` 없음 |
| `current_loaded_weight_unknown` | 잔여중량 계산 불가(설계서 4.2) |
| `truck_position_or_destination_unknown` | 경로 회랑을 만들 수 없다 |
| `cargo_index_missing` | Firestore 복합색인 부재 |
| `no_candidate_cargo` | 회랑/시간창 필터 후 후보 0 |
| `routes_api_failed` | Routes API 호출 실패 |
| `no_feasible_combination` | solver가 해를 못 찾음 |

**설계서 5.9** "오류 시 잘못된 true를 반환하지 않는다" — 모든 경로가 false로 수렴한다.

---

### MAT-09 트럭 위치·목적지 의존

`SpaceGeometryReady` 이벤트에는 좌표가 없다(설계서 2.2가 CBM/품질 요약만 싣는다).
Matching은 `trucks/{truck_id}`에서 읽는다.

| 필드 | 채우는 주체 | 없으면 |
|---|---|---|
| `current_lat`, `current_lng` | 프론트가 촬영 시 전송 | fail-closed |
| `destination_lat`, `destination_lng` | 촬영 시 지정하거나 **기본 목적지 자동 설정** | fail-closed |

목적지는 기사가 촬영할 때 바꿀 수 있고, 바꾸지 않으면 vision-processor가 기본 목적지로
설정한다([VIS-10](04-vision-processor.md#vis-10-목적지-지정과-주소-검색)).
운행 배차 시스템 연동은 없다.

---

### MAT-10 운송장 체적 CSV는 17컬럼이고 매칭에 필요한 값이 셋 다 없다

화주사 체적 측정기가 내보내는 실제 파일(`ai 학습 체적2.csv`)의 컬럼은 고정 17개고,
**헤더 행이 없다.** 첫 줄부터 데이터다.

```
301636574396,C,610.0000,317.0000,317.0000,720.0,57.9,1636.5,323.2,
616.1,543.8,1496.0,782.1,001,Box,박스,2026-08-04 08:57:29
```

| # | 컬럼 | 내부 필드 | 비고 |
|---|---|---|---|
| A | 운송장번호 | `waybill_no` | 12자리. 유일하다는 보장은 없다 — 박스마다 한 행 |
| B | 박스타입 | `box_type` | A / B / C / D / E / S, 미측정이면 `NULL` |
| C~E | 박스 가로·세로·높이 | `box_width_mm` `box_depth_mm` `box_height_mm` | mm. **세로와 높이가 항상 같다**(아래) |
| F~M | 상위좌측X/Y, 상위우측X/Y, 하위좌측X/Y, 하위우측X/Y | 코너 좌표 8개 | M은 "추론" 값. 기본 저장 안 함 |
| N | 작업터미널 | `terminal_code` | `001`, `112`, `200` … **유일한 위치 단서** |
| O | 상품코드 | `product_code` | Box / Poly / Vinyl / Sack / no_pic / Multi |
| P | 상품명 | `product_name` | 박스 / 폴리백 / 기타 / 포대 / 복합화물 |
| Q | 생성일시 | `source_created_at` | 타임존 없는 **KST** |

**헤더가 없다는 점이 이 포맷의 첫 함정이다.** `csv.DictReader`에 그냥 넘기면 두 가지가
예외 없이 조용히 깨진다. 첫 운송장이 헤더로 먹혀 사라지고, 세로·높이 값이 같아서
(`317.0000`이 두 번) 컬럼 이름이 중복돼 이후 모든 행의 컬럼이 밀린다. 그래서
`cargo_ingest.parse_csv()`가 첫 줄이 데이터인지 먼저 판별하고, 데이터면 순서로 매핑한다.

매칭이 요구하는 값 셋이 원본에 **없다**. 각각을 어떻게 채우는지가 이 포맷 처리의 핵심이다.

| 없는 것 | 채우는 방법 | 남는 위험 |
|---|---|---|
| 체적(CBM) | 가로×세로×높이 ÷ 1e9 | **세로==높이 문제**(아래) |
| 중량(kg) | **박스타입별 대표 중량**(`CARGO_WEIGHT_BY_BOX_TYPE`). 타입이 없으면 상품코드별 밀도 × 체적 | **추정치.** `weight_source="ESTIMATED"`와 근거(`weight_basis`)를 붙여 실측과 섞지 않는다 |
| 상차 좌표 | `terminals` 컬렉션에서 작업터미널 코드로 조회 | 미등록 터미널의 운송장은 **버린다**([MAT-11](#mat-11-미등록-작업터미널의-운송장은-버린다)) |
| 상차 마감 | 생성일시 + `WAYBILL_VALID_HOURS` | 업무 규칙 확인 필요. 만료분은 저장하지 않는다([MAT-13](#mat-13-한-파일-5만-행)) |

**세로와 높이가 모든 행에서 같다.** 310행 샘플에서 306행(치수가 있는 전 행)이 그렇다
(317/317, 331/331, 360/360…). 측정기가 2D 쿼드에서 두 변만 내고 세 번째 축을 복제했을
가능성이 있고, 사실이라면 체적이 전부 틀린다. 값을 추측으로 바꾸지 않고 컬럼이 말하는 대로
곱하되, 해당 행 수를 세어 전 행이 그러면 적재 로그에 경고를 남긴다. **화주사 확인 필요 항목이다.**

**미측정 행은 오류가 아니다.** 박스타입 `NULL` · 치수 전부 0 · 상품코드 `no_pic`(사진 없음)
또는 `Multi`(복합화물)인 행이 섞여 있다(샘플 310행 중 4행). 측정기가 값을 못 낸 것이라
`unmeasured_rows`로 따로 세고, 오류 목록(최대 20건)을 이걸로 채우지 않는다 — 그러면 진짜
문제가 묻힌다.

**운송장 단위로 합산한다.** 한 운송장에 박스가 여러 개면 행도 여러 개다. 합산하지 않으면
문서 ID가 같아 마지막 박스만 남고 체적이 실제보다 작아진다. 그래서 한 운송장의 박스는
**같은 파일 안에 있어야 한다** — 파일을 나눌 때 운송장 경계로 끊어야 한다. (샘플 파일은
운송장번호가 전부 고유해서 합산이 no-op으로 동작했다. 무해하지만 규칙은 유지한다.)

**웹 폼 등록도 같은 코드를 탄다.** `POST /v1/waybills`는 위 17컬럼과 같은 모양의 JSON을
받아 `cargo_ingest.ingest_waybill_rows()`로 넘긴다. 경로를 갈라 두면 체적 계산이나 중량
추정이 두 곳에서 달라지고, 그 차이는 조용히 데이터에 남는다.

### MAT-11 미등록 작업터미널의 운송장은 버린다

좌표가 없으면 M2 회랑에 넣을 수 없다. 서울시청 같은 기본 좌표로 채우면 매칭이 **그럴듯하게 틀린
결과**를 낸다 — 설계서 5.8의 fail-closed와 같은 이유로 행을 버리고 사유를 로그에 남긴다.

```bash
./infra/seed_terminals.sh      # 001 / 112 / 200 을 한 번에 등록
```

```bash
curl -X POST "$MATCH_URL/v1/terminals" -H "Content-Type: application/json" \
  -d '{"terminal_code":"001","name":"서울터미널","lat":37.5,"lng":127.0}'
```

> **현재 등록된 좌표는 실측이 아니다.** `infra/seed_terminals.sh`가 넣는 001/112/200은
> 개발·시연용 임시값이고, 그래서 터미널 이름에 `(임시)`가 붙어 있다 — 매칭 결과의
> `pickup_address`에 그대로 노출돼 실측과 헷갈리지 않게 하려는 것이다. 화주사에서 실제
> 터미널 주소를 받으면 그 스크립트의 좌표를 고치고 다시 실행한다.
>
> 세 코드의 거리를 일부러 다르게 잡았다(대전 ~3km / 세종 ~13km / 부산 ~250km). 기본 트럭
> 위치가 대전이고 `CORRIDOR_RADIUS_KM`이 30이라, 회랑 필터가 실제로 동작하는지 데이터로
> 확인할 수 있다.

터미널이 몇 개뿐이면 `TERMINAL_COORDS_JSON` 환경변수로도 넣을 수 있고, 이쪽이 Firestore보다
우선한다. 대응표는 인스턴스마다 `TERMINAL_CACHE_TTL_S`(300초) 동안 캐시된다 — 방금 등록한
터미널이 즉시 반영되지 않을 수 있다.

> **Git Bash에서 한글을 인자로 넘기지 말 것.** 네이티브 `curl.exe`에 한글이 든 명령행
> 인자를 주면 MSYS가 ANSI 코드페이지(CP949)로 변환해 UTF-8이 깨진다. 실제로 터미널 이름이
> `대전허브터미널(임시)` → `͹̳ ( ӽ )`로 저장됐다. 본문을 `printf ... | curl -d @-`로
> stdin에 흘리면 이 변환을 타지 않는다.

### MAT-12 인코딩은 UTF-8과 CP949 둘 다 받는다

실제 받은 파일은 UTF-8이었지만, 한국어 Windows 엑셀에서 "CSV(쉼표로 분리)"로 저장하면
CP949로 나온다. 어느 쪽이 올지 화주사 담당자의 저장 방법에 달려 있어 둘 다 받는다 —
`storage_reader.decode()`가 `utf-8-sig → cp949 → utf-16` 순으로 시도한다. UTF-8로만 읽으면
CP949 파일은 한글 상품명에서 `UnicodeDecodeError`가 나 파일 전체가 버려진다.

같은 이유로 **운송장번호는 반드시 텍스트 서식으로 저장해야 한다.** 엑셀 '일반' 서식은 12자리
숫자를 `3.01637E+11`로 바꿔 뒷자리를 지운다. 그대로 받으면 서로 다른 운송장이 한 문서로
합쳐지므로, 지수 표기가 감지되면 그 행을 버리고 사유를 알려 준다.

### MAT-13 한 파일 5만 행

인스턴스가 1Gi/1CPU이고 Eventarc 요청은 `TIMEOUT`(120s) 안에 끝나야 한다. 운송장 합산 때문에
파일 전체를 메모리에 올리므로 `INGEST_MAX_ROWS_PER_FILE`(5만)이 메모리(약 150MB)와 시간
양쪽의 안전선이다. Firestore 일괄 쓰기는 500건씩 묶어 `INGEST_MAX_PARALLEL_BATCHES`(4)개씩
동시에 커밋한다 — 순차로 하면 5만 행에 100번 왕복이라 타임아웃에 닿는다.

수백만 건은 이 크기로 잘라 올린다. 파일마다 Cloud Run 인스턴스가 따로 붙어 병렬 처리된다.

**적재 결과 읽는 법** — 행 수와 운송장 수가 1:1이 아니라 로그에 둘 다 남긴다.

실제 샘플 파일(310행)을 올렸을 때:

```
운송장 적재(gs://.../ai_volume2.csv): written=306 failed=0
  박스 306행 -> 운송장 306건, 미측정 4행, 이미 만료 306건 (만료분은 저장하지 않음)
  세로==높이인 행이 306행 전부다 — 측정기가 축을 복제했는지 확인 필요
```

| 숫자 | 뜻 |
|---|---|
| `box_rows` | 치수가 있는 박스 행 수 |
| `waybills` / `written` | 합산 후 만들어진 운송장 = 실제 저장된 후보 |
| `unmeasured_rows` | 치수 0 행. 파일 결함이 아니다 |
| `box_rows_failed` / `waybills_failed` | 진짜 실패. 사유가 `errors[]`에 최대 20건 |
| `already_expired` | 생성일시 + `WAYBILL_VALID_HOURS`가 이미 지난 건 |

**만료된 운송장은 저장하지 않는다**(`INGEST_SKIP_EXPIRED`, 기본 true). 저장해도 M3 시간창
필터가 후보에서 빼고 `deadline_at` TTL이 곧 지우는데, `written=306`처럼 성공한 것처럼 보여서
"이 파일은 너무 오래됐다"는 사실이 묻히기 때문이다. 건너뛰면 `written=0`이 그대로 경고가 된다.

> 샘플 파일의 생성일시가 며칠 지난 값이라 운영 기본값 72시간에서는 전 건이 만료로 걸러진다.
> 시연 환경은 `infra/config.sh`에서 `WAYBILL_VALID_HOURS=720`(30일)을 쓴다. 실데이터를
> 실시간으로 받기 시작하면 72로 되돌려야 한다.

---

### MAT-14 사진 없이 차량 제원만으로 매칭한다

`POST /v1/trucks/{truck_id}/match`는 사진 경로(`_run_matching`)와 **다른 함수**다.

적재된 화물을 0으로 보기로 하면서 사진을 찍을 이유가 사라졌다. 실을 수 있는 공간이
등록 적재함 체적 그 자체가 되므로, 사진에서 빈 공간을 추정하던 단계 전체가 중복이다.

위치로 후보를 좁히지도 않는다. 회랑(M2)과 우회시간(M4)은 "지금 트럭 근처에서 들를 만한가"에
답하는 단계인데, 이 경로가 묻는 것은 "이 차에 뭐가 실리나"뿐이다. 빼고 나니 Routes API 호출도,
그 실패로 매칭이 통째로 죽던 경로(`routes_api_failed`)도 사라졌다.

판정 근거가 다르다는 사실은 결과에 남긴다.

| 필드 | 값 |
|---|---|
| `decision_scope` | `CBM_WEIGHT_ONLY` |
| `route_source` | `NOT_COMPUTED` |
| `quality_status` | `ACCEPTED` (사진이 없으니 품질 게이트가 없다) |
| `unknown_cbm` | `0.0` (못 본 공간이 아니라 **측정을 안 한 것**) |

`photo_id`는 `D-{truck_id}-{epoch}` 형태로 만든다. 매번 새 키라 갱신할 때마다 이전 결과를
덮지 않고 이력이 남는다.

---

### MAT-15 후보 상한을 요청이 정한다 · 솔버가 실패하면 그리디로 떨어진다

`candidates` 쿼리 파라미터로 검토할 후보 수를 정한다. 상한은 `CANDIDATE_FETCH_MAX`(10만)이고,
넘는 값은 조용히 자르지 않고 상한으로 맞춘 뒤 `candidate_limit`으로 응답에 돌려준다.

**후보 수가 결과를 크게 좌우한다.** 대기 운송장이 20만 건인데 4천 건만 보면 특정 구간이
표본에 아예 안 들어와 "그 구간은 물량이 없다"로 보인다. 화면 기본값은 1만 건이다.

솔버가 해를 내지 못하면 그리디 채우기로 떨어진다. 이유는 이렇다.

> 후보 4,000건에서 CP-SAT가 제한 시간(당시 1초) 안에 해를 못 찾고 `UNKNOWN`을 돌려주면,
> 5.8 fail-closed 원칙대로 0건으로 끝났다. 그 결과 적재함이 53CBM 통째로 비어 있는데도
> 화면에는 "실을 수 있는 운송장이 없습니다"가 떴다. 같은 요청이 어떤 때는 `FEASIBLE`,
> 어떤 때는 `UNKNOWN`이라 결과가 뒤집혔다.
>
> fail-closed가 사진 경로에서 옳은 이유는 **품질을 못 믿기 때문**이다. 이 경로에는 부피와
> 중량밖에 없고 둘 다 확정값이라 못 믿을 것이 없다. 제한 시간을 못 지킨 것은 "실을 것이
> 없다"와 다른 사실이다.

그리디는 **부피당 무게(kg/CBM)가 낮은 것부터** 담는다. 부피가 작은 것부터 담으면 중량 한도가
먼저 차서 부피가 남는다 — 실제로 후보를 1만에서 10만으로 늘렸더니 적재율이 68%에서 40%로
**떨어졌다**. 소포는 작을수록 부피당 무겁다(A타입 0.04CBM에 5kg).

어느 쪽으로 계산했는지는 `solver_status`에 사유까지 남고(`GREEDY_FILL(CP_SAT=UNKNOWN)`),
화면 설명이 그 값을 보고 문장을 바꾼다. 그리디로 떨어졌는데 "AI 최적화가 골랐다"고 쓰면
설명이 거짓이 된다.

`SOLVER_MAX_CANDIDATES`를 0보다 크게 두면 그 수를 넘는 후보에서 CP-SAT를 아예 건너뛴다.
**기본은 0(제한 없음)** — 이 화면의 결과는 AI가 고른 조합이어야 하므로 시간이 더 걸려도
최적화를 먼저 돌린다.

---

### MAT-16 파렛트 적재는 용량을 29~60% 깎는다

`palletized=true`면 파렛트 기준으로 용량을 다시 계산한다. 현장에서 자주 나는 계산 착오가
**화물만 재고 파렛트를 빼먹는 것**이다. 잃는 공간이 셋이다.

1. **깔판 높이** — T-11 파렛트 두께 144mm만큼 쌓을 수 있는 높이가 줄어든다.
2. **바닥 자투리** — 1,100mm 규격이 적재함 폭·길이로 나누어떨어지지 않는다. 11톤 윙바디
   폭 2.35m에는 파렛트가 2장(2.2m)만 들어가고 남는 15cm는 통째로 죽는다.
3. **파렛트 위 빈틈** — 규격이 제각각인 소포는 파렛트를 꽉 채우지 못한다(`PALLET_STACK_EFFICIENCY`).

```
파렛트 수 = floor(폭 / 1.1) x floor(길이 / 1.1)
용량      = 파렛트 수 x 1.1 x 1.1 x (높이 - 0.144) x 0.85
```

| 차량 | 배치 | 원래 → 파렛트 | 손실 |
|---|---|---|---|
| 1톤 봉고Ⅲ (1.67x2.83x1.81) | 1열x2줄 = 2장 | 8.55 → 3.43 CBM | **60%** |
| 3톤 마이티 (2.10x4.90x2.10) | 1열x4줄 = 4장 | 21.61 → 8.05 CBM | **63%** |
| 5톤 파비스 (2.35x7.00x2.56) | 2열x6줄 = 12장 | 42.11 → 29.82 CBM | 29% |
| 11톤 엑시언트 (2.35x9.30x2.45) | 2열x8줄 = 16장 | 53.55 → 37.95 CBM | 29% |

1톤·3톤이 60%대를 잃는 것은 **폭이 좁아 파렛트가 1열밖에 안 들어가서**다. 작은 차를
파렛트로 쓰면 왜 손해인지가 숫자로 드러난다.

새 데이터는 필요 없다. 파렛트가 몇 장 깔리는지는 부피가 아니라 바닥 크기가 정하는데,
적재함 가로·세로·높이가 이미 `trucks` 문서에 있다. **치수가 없는 차량은 추정하지 않고
422로 거절한다** — 배치를 지어내면 그게 곧 틀린 용량이 된다.

응답에 `pallet_mode` / `pallet_count` / `pallet_spec` / `raw_capacity_cbm` / `pallet_loss_cbm`을
실어, 화면이 "왜 용량이 줄었나"에 답할 수 있게 한다.

---

### MAT-17 결과를 출발-도착 작업터미널 쌍으로 묶는다

`terminal_groups`는 선택된 운송장을 (출발터미널, 도착터미널) 쌍으로 묶은 것이다.

관리자가 정하는 것은 "이 운송장을 실을까"가 아니라 "이 터미널에 들를까"다. 1,700건을
낱개로 늘어놓으면 들를 곳이 몇 군데인지조차 읽히지 않는다.

박스타입별 건수(`box_type_counts`)를 함께 주는 이유는 규격이 곧 부피·운임 등급이라,
같은 6건이어도 A 6건과 C 6건이 전혀 다른 일이기 때문이다.

상차지 좌표(`origin_lat`/`origin_lng`)도 그룹에 싣는다. 화면이 "내 위치에서 가까운 순"으로
정렬하는데, 좌표를 안 주면 화면이 터미널 목록을 따로 받아 코드로 이어 붙여야 하고 그 사이에
둘이 어긋난다.

집계는 서버에서만 만든다. 화면이 다시 세면 저장값과 갈라진다.

---

## 주요 설정값

| 값 | 기본 | 근거 |
|---|---|---|
| `CORRIDOR_RADIUS_KM` | 30 | 경로 회랑 반경 |
| `MAX_CANDIDATE_FETCH` | 500 (배포 10000) | 후보 상한 **기본값**. 요청이 덮어쓸 수 있다 |
| `CANDIDATE_FETCH_MAX` | 100000 | 요청이 올릴 수 있는 상한 |
| `SOLVER_MAX_CANDIDATES` | 0 | 이 수를 넘으면 CP-SAT를 건너뛴다. **0 = 제한 없음** |
| `PALLET_WIDTH_M` / `PALLET_LENGTH_M` | 1.1 | T-11 표준 파렛트 |
| `PALLET_BASE_HEIGHT_M` | 0.144 | 깔판 높이 |
| `PALLET_STACK_EFFICIENCY` | 0.85 | 파렛트 위 빈틈. **가정값**([OPEN-18](08-open-issues.md#open-18-파렛트-적재-효율-085는-가정값이다)) |
| `MAX_ROUTE_CANDIDATES` | 20 | 설계서 5.4 |
| `MAX_DETOUR_SECONDS` | 3600 | 우회시간 합산 예산 |
| `SOLVER_TIME_LIMIT_S` | 1.0 (배포 120) | 1초는 후보 수천 건에서 사실상 매번 실패한다 |
| `LIMITED_EXTRA_SAFETY_FACTOR` | 0.80 | 설계서 4.10 |
| `GEOMETRY_RISK_PENALTY_LIMITED` | 50000 | 원 단위 |
| `FILL_REWARD_PER_LITER` | 20 | 튜닝값 |
| `DETOUR_PENALTY_PER_SECOND` | 30 | 튜닝값 |
| `FALLBACK_AVG_SPEED_KMH` | 45 | 직선거리→시간 환산 |
| `INGEST_MAX_ROWS_PER_FILE` | 50000 | [MAT-13](#mat-13-한-파일-5만-행) |
| `INGEST_MAX_PARALLEL_BATCHES` | 4 | 일괄 쓰기 동시 커밋 수 |
| `INGEST_MAX_BATCH` | 500 | Firestore 일괄 쓰기 상한 |
| `WAYBILL_VALID_HOURS` | 72 (시연 720) | 생성일시 → 상차 마감. **업무 규칙 확인 필요** |
| `INGEST_SKIP_EXPIRED` | true | 만료된 운송장은 저장하지 않는다 |
| `CARGO_WEIGHT_BY_BOX_TYPE` | S 2 / A 5 / B 8 / C 12 / D 18 / E 25 (kg) | **1순위 중량 근거.** 아래 참고 |
| `CARGO_DENSITY_DEFAULT` | 150 | kg/CBM. 박스타입도 상품코드도 모를 때 |
| `CARGO_DENSITY_BY_PRODUCT` | Box 150 / Poly 80 / Vinyl 80 / Sack 300 | 박스타입이 없을 때의 대체 경로 |

> **박스타입 중량은 실측이 아니다.** 파일의 타입별 대표 부피(S 약 12L … E 약 250L)를
> 한진택배 규격박스에 크기순으로 대응시켜 잡은 값이다. 부피×밀도보다 실제에 가까운
> 이유는 규격박스가 크기별로 담기는 무게가 대체로 정해져 있어서고, 특히 부피는 큰데
> 가벼운 화물(폴리백, 완충재 채운 박스)에서 밀도 추정이 크게 빗나가기 때문이다.
> 화주사의 타입별 평균 중량표를 받으면 이 표를 통째로 교체해야 한다.
>
> 중량은 **박스마다** 잡아 더한다. 한 운송장에 타입이 섞이면(A 하나 + C 하나) 합계
> 부피로 한 번에 계산하는 것과 값이 달라진다.
| `MAX_BOX_DIM_MM` | 5000 | 측정기 오류값 차단 |
| `MAX_BOX_CBM` | 30 | 박스 1개 체적 상한 |
| `TERMINAL_CACHE_TTL_S` | 300 | 터미널 대응표 캐시 |
| `TERMINAL_COORDS_JSON` | (없음) | 터미널 대응표를 환경변수로. Firestore보다 우선 |
| `INGEST_KEEP_CORNERS` | false | 코너 좌표 8개 저장 여부 |
| `INGEST_KEEP_BOX_DETAIL` | false | 박스별 명세 저장 여부 |
