# 09. Firestore 데이터 모델

Native 모드 데이터베이스 하나(`(default)`)를 쓴다. 새 프로젝트를 만들 때 **`trucks`는 반드시
시드해야** 하고, `pending_cargos`가 없으면 Matching이 후보를 못 찾아 `no_candidate_cargo`로 끝난다.

## 컬렉션 개요

| 컬렉션 | 문서 ID | 쓰는 주체 | 읽는 주체 | 시드 필요 |
|---|---|---|---|---|
| `trucks` | `T-000001` | 시드, vision(위치 갱신) | vision, matching | **필요** |
| `pending_cargos` | cargo_id의 SHA1 20자 | 시드, matching(적재) | matching | **필요** |
| `terminals` | `001` | 운영자(`POST /v1/terminals`) | matching(적재) | 운송장 파일 적재 시 **필요** |
| `vision_results` | `photo_id` | vision | vision(조회 API) | 불필요 |
| `matching_results` | `photo_id` | matching | matching(조회 API) | 불필요 |
| `photo_contexts` | `photo_id` | vision(upload-url) | vision(파이프라인) | 불필요 |
| `processed_photos` | `photo_id` | vision | vision | 불필요 |
| `processed_events` | `event_id` | matching | matching | 불필요 |

---

## trucks

문서 ID는 **`T-` + 6자리**다(`T-000001`). `DEFAULT_TRUCK_ID`가 이 형식과 달라 파이프라인이
422로 중단된 적이 있다([VIS-02](04-vision-processor.md#vis-02-truck_id-복원-우선순위)).

| 필드 | 타입 | 필수 | 용도 |
|---|---|---|---|
| `truck_id` | string | | 문서 ID와 동일 |
| `cargo_width_m` | double | **필수** | 화물칸 내부 폭 W |
| `cargo_length_m` | double | **필수** | 화물칸 내부 길이 L |
| `cargo_height_m` | double | **필수** | 화물칸 내부 높이 H |
| `max_payload_kg` | int | **필수** | 최대 적재중량 |
| `current_loaded_weight_kg` | int | 실질 필수 | 없으면 `can_load=false` |
| `current_lat` / `current_lng` | double | Matching 필수 | 프론트가 촬영 시 갱신 |
| `destination_lat` / `destination_lng` | double | Matching 필수 | 촬영 시 지정 또는 기본 목적지 자동 설정 |
| `destination_address` | string | 선택 | 표시용. 판정에는 쓰이지 않는다 |
| `reserved_added_weight_kg` | double | 선택 | 예약분 차감. 기본 0 |

W/L/H 또는 `max_payload_kg`가 없으면 `get_truck_spec`이 `None`을 반환해 Vision이 422로 중단한다
(설계서 4.2).

`cargo_capacity_cbm`은 **차량 기준 매칭(MAT-14)의 출발점**이라 이제 참고용이 아니다.
빈 차 기준이면 이 값이 그대로 실을 수 있는 공간이 된다. W/L/H는 파렛트 배치를 세는 데도
쓴다([MAT-16](05-matching-processor.md#mat-16-파렛트-적재는-용량을-29-60-깎는다)) —
치수가 없으면 파렛트 계산은 422로 거절한다.

화면이 제원 출처를 표시하므로 `spec_template_id` / `record_type` / `registered_year`도
`GET /v1/trucks/{id}` 응답에 실린다.

참고용 부가 필드(파이프라인이 쓰지 않음): `manufacturer`, `model`, `body_type`,
`vehicle_class`, `available_payload_kg`, `load_ratio`.

**현재 시드는 4대뿐이다**(`T-000001`~`T-000004`, 1/3/5/11톤). 대수가 많으면 어떤 차로
계산했는지에 따라 결과가 달라져 재현이 안 된다. 적재중량은 전부 0으로 못 박는다 —
빈 차에서 시작해야 잔여 체적이 차량 제원만으로 정해진다.
시드는 [tools/seed_trucks.py](../tools/seed_trucks.py)와
[tools/trucks_seed.csv](../tools/trucks_seed.csv)로 한다.

**예시**

```json
{
  "truck_id": "T-000001",
  "cargo_width_m": 1.61, "cargo_length_m": 3.26, "cargo_height_m": 1.6,
  "max_payload_kg": 900, "current_loaded_weight_kg": 460,
  "current_lat": 36.3879, "current_lng": 127.3823,
  "destination_lat": 37.4813, "destination_lng": 126.897
}
```

---

## pending_cargos

Matching 후보. 현재 **20만 건** 규모다.

**문서 ID는 `cargo_id`의 SHA1 앞 20자다.** 운송장 번호가 순차(30493263xx…)라 그대로 ID로 쓰면
색인 범위 한 곳에 쓰기가 몰려 대량 적재가 초당 수백 건에서 막힌다. 무작위 UUID가 아니라 해시인
이유는 같은 운송장을 다시 올려도 같은 문서가 되게 하기 위해서다(재업로드 멱등).
초기 시드분(`C-000001`)은 ID가 cargo_id 그대로라 두 형태가 섞여 있다 — 조회는 항상 `cargo_id`
필드로 한다.

| 필드 | 타입 | 필수 | 용도 |
|---|---|---|---|
| `cargo_id` | string | **필수** | 운송장번호. 문서 ID의 해시 원본 |
| `status` | string | **필수** | `"WAITING"`만 조회 대상 |
| `pickup_lat` / `pickup_lng` | double | **필수** | M2 회랑 쿼리 + M3 반경 |
| `volume_cbm` | double | **필수** | 체적 제약. 없으면 해당 후보만 제외 |
| `weight_kg` | double | **필수** | 중량 제약 |
| `delivery_lat` / `delivery_lng` | double | 선택 | |
| `revenue_krw` | number | 선택 | 목적함수. 기본 0 |
| `ready_at` | **timestamp** | 선택 | |
| `deadline_at` | **timestamp** | 선택 | 지난 후보는 M3에서 제외. **TTL 필드** — 지나면 자동 삭제 |
| `weight_source` | string | | `"DECLARED"`(화주사 신고) / `"ESTIMATED"`(체적×밀도 추정) |

**주의** `ready_at`/`deadline_at`은 문자열이 아니라 Firestore **timestamp**다
([GCP-14](02-gcp-infra.md#gcp-14-firestore-timestamp는-문자열이-아니라-datetime으로-온다)).

### 터미널 필드는 출발·도착 두 축이다

옛 `terminal_code` / `terminal_name`은 **출발지**를 뜻했다. 이름이 중립적이라 읽는 쪽마다
출발지로도 도착지로도 해석해서, `origin_` 접두사로 바로잡고 `destination_`을 새로 뒀다.
읽는 코드는 옛 이름을 출발지 대체 경로로 계속 받는다 — 마이그레이션 전후 문서가 섞여
있어도 상차지를 잃지 않는다.

**도착지는 지어내지 않는다.** 화물이 어디로 가는지는 화주사만 아는 사실이다. 등록 폼에서는
필수이고, 체적 측정기 파일에만 예외를 둔다 — 측정기는 상차 터미널에 놓여 있어 도착지 컬럼
자체가 없다. 그 경로에서 서버가 채운 값은 `destination_source="ASSIGNED"`로 표시해
신고값(`DECLARED`)과 구분한다. **`ASSIGNED`인 도착지를 사실로 쓰면 안 된다.**

배정 규칙은 운송장번호 SHA-1 해시로 등록 터미널 중 출발지가 아닌 곳을 고른다. 난수를 쓰면
같은 파일을 다시 적재할 때마다 도착지가 바뀌어 화면을 새로 고칠 때마다 그룹이 뒤섞인다.
적재 경로([cargo_ingest.assign_destination](../matching-processor/cargo_ingest.py))와
마이그레이션([tools/migrate_cargo_terminals.py](../tools/migrate_cargo_terminals.py))이
같은 규칙을 쓴다.

**운송장 체적 파일로 적재된 문서**는 아래 필드가 더 붙는다
([MAT-10](05-matching-processor.md#mat-10-운송장-체적-csv는-17컬럼이고-매칭에-필요한-값이-셋-다-없다)).

| 필드 | 타입 | 용도 |
|---|---|---|
| `ingest_format` | string | `"WAYBILL_VOLUME_V1"` |
| `ingest_source` | string | 출처 `gs://…` 경로 |
| `origin_terminal_code` / `origin_terminal_name` | string | **출발** 작업터미널. 상차 좌표의 근거 |
| `destination_terminal_code` / `destination_terminal_name` | string | **도착** 작업터미널 |
| `destination_source` | string | `"DECLARED"`(화주사 지정) / `"ASSIGNED"`(서버가 채움) |
| `delivery_address` | string | 도착터미널 주소 |
| `box_count` | int | 이 운송장의 박스 수. 체적은 전 박스 합계다 |
| `box_types` | array\<string\> | 예: `["A","B"]` |
| `product_code` / `product_name` | string | Box·Poly·Vinyl·Sack / 박스·폴리백·기타·포대 |
| `weight_density_kg_per_cbm` | double | 중량 추정에 쓴 밀도 |

이 경로의 `weight_kg`는 **추정치**다(원본에 중량 컬럼이 없다). `weight_source="ESTIMATED"`가
`SelectedCargo`까지 그대로 올라가, 결과에서 실측과 섞이지 않는다.

부가 필드: `cargo_type`, `cargo_width_m`, `cargo_length_m`, `cargo_height_m`,
`package_count`, `stackable`, `fragile`, `pickup_hub`, `delivery_hub`,
`estimated_distance_km`, `record_type`.

3축 치수가 있어도 현재는 쓰지 않는다. 설계서 5.2대로 형상 기반 3D bin packing은 범위 밖이며,
`decision_scope`가 `CBM_WEIGHT_ROUTE_FEASIBILITY`인 이유가 이것이다.

**필요 색인**

```bash
gcloud firestore indexes composite create \
  --collection-group=pending_cargos \
  --field-config=field-path=status,order=ascending \
  --field-config=field-path=pickup_lat,order=ascending \
  --field-config=field-path=pickup_lng,order=ascending
```

**TTL** — `deadline_at`을 TTL 필드로 지정해 만료 운송장을 Firestore가 자동 삭제한다.
수백만 건이 무한정 쌓이지 않게 하는 유일한 장치다.

```bash
gcloud firestore fields ttls update deadline_at \
  --collection-group=pending_cargos --enable-ttl
```

---

## terminals

작업터미널 코드 → 좌표. 운송장 체적 파일에는 좌표가 없고 작업터미널 코드만 있어서, 이 표가
파일 적재의 **선행 데이터**가 된다. 여기 없는 터미널의 운송장은 적재되지 않는다
([MAT-11](05-matching-processor.md#mat-11-미등록-작업터미널의-운송장은-버린다)).

문서 ID = 터미널 코드(`001`). 숫자만인 코드는 3자리로 zero-pad해 정규화한다 — 엑셀이 `001`을
`1`로 바꿔 놓는 일이 잦다.

| 필드 | 타입 | 필수 | 용도 |
|---|---|---|---|
| `terminal_code` | string | **필수** | 문서 ID와 동일 |
| `lat` / `lng` | double | **필수** | 적재 시 `pickup_lat`/`pickup_lng`로 복사된다 |
| `name` | string | 선택 | |
| `address` | string | 선택 | `pickup_address`로 복사된다 |

```bash
curl -X POST "$MATCH_URL/v1/terminals" -H "Content-Type: application/json" \
  -d '{"terminal_code":"001","name":"서울터미널","address":"...","lat":37.5,"lng":127.0}'
```

터미널이 몇 개뿐이면 컬렉션 대신 `TERMINAL_COORDS_JSON` 환경변수로도 넣을 수 있고, 이쪽이
Firestore보다 우선한다.

---

## vision_results

Vision이 쓴다. 문서 ID는 `photo_id`. `GET /v1/results/{photo_id}`가 그대로 돌려준다.

```json
{
  "truck_id": "T-000001",
  "photo_id": "P-cb1fd875",
  "captured_at": "2026-08-09T00:07:27.126985+00:00",
  "estimated_free_cbm": 3.664,
  "usable_free_cbm": 2.335,
  "unknown_cbm": 0.342,
  "quality_score": 0.628,
  "quality_status": "LIMITED",
  "current_loaded_weight_kg": 460.0,
  "max_payload_kg": 900.0,

  "cargo_width_m": 1.61, "cargo_length_m": 3.26, "cargo_height_m": 1.6,
  "capacity_cbm": 8.398,
  "occupied_cbm": 3.208,
  "observed_free_cbm": 3.886,
  "safety_factor": 0.7,

  "result_uri": "gs://truck-vision-.../results/P-cb1fd875.json",
  "failure_reason": null,
  "model_versions": {
    "detector": "google/owlvit-base-patch32@owlvit-base-patch32",
    "depth": "Depth-Anything-V2-Metric-Indoor-Small-hf@8078d68a9c...",
    "geometry": "geometry-lite-v1"
  }
}
```

같은 내용이 `gs://{bucket}/results/{photo_id}.json`에도 저장된다(설계서 V6).
**Firestore가 정본**이고 GCS는 사본이다. 버킷 lifecycle 7일에 걸려 사본은 삭제된다.

---

## matching_results

Matching이 쓴다. 문서 ID는 `photo_id`. 설계서 5.3 결과 계약이다.

```json
{
  "truck_id": "T-000001", "photo_id": "P-cb1fd875",
  "estimated_free_cbm": 3.664, "usable_free_cbm": 1.868, "unknown_cbm": 0.342,
  "remaining_weight_kg": 440.0,
  "can_load": true,
  "selected_cargos": [
    {"cargo_id": "C-037899", "volume_cbm": 1.304, "weight_kg": 380.0, "pickup_order": 1}
  ],
  "final_free_cbm": 0.564,
  "quality_score": 0.628, "quality_status": "LIMITED",
  "decision_scope": "CBM_WEIGHT_ROUTE_FEASIBILITY",
  "solver_status": "OPTIMAL", "candidate_count": 20,
  "route_source": "HAVERSINE_FALLBACK",
  "failure_reason": null
}
```

`usable_free_cbm`이 Vision 값과 다를 수 있다. `LIMITED`면 추가 안전계수 0.80을 곱하기 때문이다.

---

## photo_contexts

PWA가 `upload-url`을 받을 때 남기는 촬영 컨텍스트. 리사이즈로 사라질 EXIF를 대신 전달한다
([VIS-08](04-vision-processor.md#vis-08-exif는-리사이즈-전에-읽어야-한다)).

```json
{
  "truck_id": "T-000001",
  "native_intrinsics": {"fx": 900.5, "fy": 900.5, "cx": 512, "cy": 384},
  "requested_at": "2026-08-09T00:07:00+00:00"
}
```

`native_intrinsics`는 EXIF에 focal 정보가 없으면 `null`이다.

---

## processed_photos / processed_events

idempotency 점유용. 값은 `{"claimed_at": <server timestamp>}` 하나뿐이다.

- `processed_photos/{photo_id}` — Vision. 처리 실패 시 **삭제해서 재시도를 허용한다**.
- `processed_events/{event_id}` — Matching. 실패해도 삭제하지 않는다(재계산이 저렴하다).

같은 사진을 강제로 재처리하려면 `processed_photos/{photo_id}`를 지운다.

---

## 시드 방법

로컬에 Python이 없어도 REST API로 넣을 수 있다([ENV-06](01-environment.md#env-06-로컬에-실행-가능한-python이-없다)).

```bash
TOKEN=$(gcloud auth print-access-token)
BASE="https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)/documents"

curl -X PATCH "${BASE}/trucks/T-000001" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"fields":{
        "truck_id":{"stringValue":"T-000001"},
        "cargo_width_m":{"doubleValue":1.61},
        "cargo_length_m":{"doubleValue":3.26},
        "cargo_height_m":{"doubleValue":1.6},
        "max_payload_kg":{"integerValue":"900"},
        "current_loaded_weight_kg":{"integerValue":"460"}
      }}'
```

트럭 위치/목적지만 넣는 스크립트는 이미 있다.

```bash
cd matching-processor
./infra/seed_truck_position.sh T-000001 36.3879 127.3823 37.4813 126.8970
```

기존 필드를 지우지 않도록 `updateMask`로 해당 필드만 갱신한다.

---

## 대량 데이터 생성·정리 스크립트

`tools/`에 모아 뒀다. 전부 `--dry-run`이 기본이고 `--apply`를 줘야 실제로 쓴다.
삭제·교체 전에는 백업 JSON을 남긴다(`tools/*_backup.json`은 gitignore 대상).

| 스크립트 | 하는 일 |
|---|---|
| [seed_trucks.py](../tools/seed_trucks.py) | `trucks`를 CSV 한 장으로 갈아끼운다. 적재중량은 항상 0으로 강제 |
| [generate_waybills.py](../tools/generate_waybills.py) | 기존 운송장을 본떠 대량 생성. `--origin/--destination`으로 구간 고정 |
| [migrate_cargo_terminals.py](../tools/migrate_cargo_terminals.py) | `terminal_code` → 출발/도착 두 축으로 이전 |
| [prune_legacy_cargos.py](../tools/prune_legacy_cargos.py) | 출발 터미널이 없는 구 합성 화물 삭제 |

`generate_waybills.py`는 체적·중량·운임을 **서버와 같은 함수**(`waybill_schema`)로 계산한다.
여기서 규칙을 다시 쓰면 화면이 서버와 다른 숫자를 말하게 된다.

묶음 크기는 300~30,000건 사이에서 뽑아 합이 목표 건수가 되게 맞춘다. 건마다 터미널 쌍을
무작위로 뽑으면 122×121 쌍에 흩어져 그룹이 전부 한 자릿수가 된다. 출발지는 허브 12곳으로
제한하는 이유도 같다.

---

## matching_results 문서 크기

Firestore 문서 상한은 1,048,576바이트다. 후보를 10만 건까지 볼 수 있게 되면서
`selected_cargos`가 수천 건이 됐고, 그대로 저장하니 상한을 넘겨 500이 났다 —
**계산은 다 끝났는데 저장에서 죽어 화면에는 아무것도 안 나왔다.**

문서가 900,000바이트를 넘으면 `selected_cargos`를 비우고 `selected_cargos_truncated`에
원래 건수를 남긴다. `terminal_groups`는 남긴다 — 결과를 다시 조회하는 쪽이 보는 것은
묶음이고, 낱건 목록은 화면에서 쓰지 않는다.
