# 04. vision-processor 구현 제약

담당: GCS 이미지 → OWL-ViT + Depth → Geometry Lite → CBM/품질 → Firestore/GCS 저장 + Pub/Sub 발행.
설계서 D3(V1-V6)에 해당한다.

## 엔드포인트

| 메서드 | 경로 | 용도 |
|---|---|---|
| GET | `/` | 헬스체크 |
| POST | `/` | **Eventarc 수신점.** 트리거가 기본으로 루트에 POST한다 |
| POST | `/v1/events/object-finalized` | 별칭. 수동 테스트용 |
| POST | `/v1/photos/upload-url` | Signed URL 발급 + 촬영 컨텍스트/목적지 저장 |
| POST | `/v1/photos/process` | 데모용 직접 호출 |
| GET | `/v1/results/{photo_id}` | 결과 조회 |
| GET | `/v1/defaults` | 기본 목적지, 주소 검색 사용 가능 여부 |
| GET | `/v1/geocode?q=` | 목적지 주소 검색(서버가 Geocoding API 대행) |
| GET | `/v1/reverse-geocode?lat=&lng=` | 좌표 → 주소. 촬영 화면의 현재 위치 표시용 |
| GET | `/v1/trucks` | 등록 차량 목록. 촬영 화면의 선택 목록 |
| GET | `/v1/trucks/{id}/session` | 이 차량의 최근 운행이 아직 유효한가(기본 60분) |
| POST | `/v1/trucks/{id}/location` | 운행 중 위치 갱신. 재매칭 루프가 부른다 |
| GET | `/v1/trucks/{truck_id}` | 차량 제원. 촬영 **전** 확인용([VIS-11](#vis-11-차량-제원이-곧-측정의-자다)) |

UI는 서빙하지 않는다. 프론트엔드는 별도 서비스다([06-frontend.md](06-frontend.md)).

---

### VIS-01 Eventarc에는 항상 200을 반환한다

- **원인** Eventarc는 비-2xx를 실패로 보고 계속 재시도한다. 파싱 실패나 파이프라인 예외로 5xx를 내면 무한 재시도가 된다.
- **대응** 루트 POST 핸들러는 어떤 예외가 나도 로그만 남기고 `{"status": "success"}`를 반환한다.
- **주의** 이 때문에 **실패가 HTTP 상태로 드러나지 않는다.** 반드시 로그를 봐야 한다.
- **적용 위치** `main.py`의 `eventarc_root`

---

### VIS-02 truck_id 복원 우선순위

이벤트에는 truck_id가 없다. 아래 순서로 복원하고, 어느 경로로 정해졌는지 로그에 남긴다.

1. **PWA 업로드 컨텍스트** — `photo_contexts/{photo_id}.truck_id`. 가장 정확하다
2. 객체 커스텀 메타데이터의 `truck_id`
3. 경로 상위 디렉터리 — `photos/{truck_id}/{photo_id}.jpg`
4. 파일명에 박힌 `T-000001` 패턴 — `[A-Za-z]{1,4}-\d{2,}`
5. `config.DEFAULT_TRUCK_ID`

**주의** `DEFAULT_TRUCK_ID`는 반드시 `trucks`에 실재하는 문서 ID여야 한다. 초기값이 `T-001`이었는데
실제 데이터는 `T-000001` 형식이라 파이프라인이 422로 중단됐다. 6자리다.

**적용 위치** `main.py`의 `_resolve_truck_id`, `config.py`의 `DEFAULT_TRUCK_ID`

---

### VIS-03 photo_id 기반 idempotency

- **근거** 설계서 2.1/5.8/5.9.
- **구현** `processed_photos/{photo_id}`를 `create()`로 잡는다. `create()`는 이미 있으면 `AlreadyExists`를 던지므로 원자적이다. Eventarc 재전송이나 동시 배달이 있어도 Depth/OWL 추론이 한 번만 돈다.
- **중요** **처리에 실패하면 점유를 푼다.** 풀지 않으면 첫 시도가 실패한 사진은 재시도해도 `duplicate`로 걸려 영영 처리되지 않는다.
- **확인 방법** 이미 처리된 photo_id로 이벤트를 재전송하면 `{"status":"duplicate","photo_id":...}`가 온다.
- **적용 위치** `firestore_client.claim_photo` / `release_photo`, `main.py`

---

### VIS-04 결과 JSON을 같은 버킷에 써도 안전하다

- **상황** V6가 `results/{photo_id}.json`을 원본과 같은 버킷에 쓴다. 그러면 Eventarc가 다시 발화한다.
- **왜 괜찮은가** 핸들러가 **확장자로만** 분석 대상을 가린다(`.jpg/.jpeg/.png`). `.json`은 `not_an_image`로 즉시 건너뛴다. 경로 제약을 두지 않아 유연하면서도 헛돌지 않는다.
- **GCS 저장 실패는 치명적이지 않다** — Firestore가 정본이므로 로그만 남기고 진행한다.
- **적용 위치** `main.py`의 `_IMAGE_EXTENSIONS`, `_process_photo`

---

### VIS-05 OWL-ViT 실패는 degrade하되 반드시 로그를 남긴다

- **근거** 설계서 5.8 "OWL-ViT timeout → Geometry-only 후보 추출, 품질 감점".
- **구현** 어떤 예외든 `owl_boxes = []`로 진행한다. 다만 **`logger.exception`으로 남긴다.** 초기 구현은 조용히 넘어가서 Endpoint가 죽어도 알 수 없었다.
- **증상 식별** 로그에 `OWL-ViT 탐지: N개 박스`가 없고 `owl_coverage_ratio`가 0이면 degrade 상태다.
- **적용 위치** `main.py`의 `_process_photo`

---

### VIS-06 Depth 실패는 fail-closed

- **근거** 설계서 5.8 "Depth 실패 → CBM 계산 불가".
- **구현** `HTTPException(502)`로 중단한다. OWL-ViT와 달리 degrade하지 않는다. depth 없이는 CBM 자체가 성립하지 않는다.

---

### VIS-07 5.6 구조화 로그

재현성 확인에 필요한 값을 JSON 한 줄로 stdout에 쓴다. Cloud Logging이 `jsonPayload`로 파싱해
필드 단위 조회가 된다.

```bash
gcloud logging read 'jsonPayload.message="vision_result"' --limit 5 --project "$PROJECT_ID"
```

포함 필드: `photo_id`, `truck_id`, `captured_at`, `detector`, `depth_model`,
`geometry_lite_version`, `container_revision`(K_REVISION), `voxel_edge_m`, `safety_factor`,
`intrinsics_source`, `intrinsics_confidence`, `exif_present`, `owl_box_count`,
`plane_residual_avg`, `scale_correction_ratio`, `structural_plane_count`,
`depth_outlier_ratio`, `observed_voxel_ratio`, `owl_coverage_ratio`,
`estimated_free_cbm`, `usable_free_cbm`, `unknown_cbm`, `quality_score`, `quality_status`,
`failure_reason`, `model_latency_ms`, `geometry_latency_ms`, `total_latency_ms`

**적용 위치** `main.py`의 `_process_photo` 말미

---

### VIS-08 EXIF는 리사이즈 전에 읽어야 한다

- **문제** PWA가 1024px로 축소하면 canvas 재인코딩에서 EXIF가 사라진다. 서버는 EXIF 없는 이미지를 받는다.
- **대응** PWA가 원본에서 EXIF를 읽고 리사이즈 비율로 보정한 intrinsic을 `upload-url` 요청에 실어 보낸다. 서버는 `photo_contexts/{photo_id}`에 보관했다가 파이프라인에서 `native_intrinsics`로 쓴다.
- **효과** intrinsic 신뢰도가 0.2(기본 화각) → 0.95로 올라 quality_score가 약 0.10 상승한다.
- **적용 위치** `main.py`의 `get_upload_url`, `firestore_client.save_photo_context`

---

### VIS-09 성능 특성

| 구간 | 실측 |
|---|---|
| 모델 추론(OWL-ViT + Depth 병렬) | 약 1.0초 |
| Geometry Lite | **60-104초** |
| 전체 | 60-105초 |

**geometry가 압도적으로 지배적이다.** 지연을 줄이려면 모델이 아니라 Geometry Lite부터 봐야 한다.
Open3D RANSAC 평면 검출과 voxel 분류가 주 후보다. `--timeout 300s`는 이 때문에 필요하다.

---

### VIS-10 목적지 지정과 주소 검색

기사가 촬영할 때마다 목적지를 바꿀 수 있다. `upload-url` 요청에 `destination_address`,
`destination_lat`, `destination_lng`를 함께 받아 `trucks/{truck_id}`에 기록한다.

**지정하지 않으면 기본 목적지로 설정한다.** 비워 두면 M2 경로 회랑을 만들 수 없어 Matching이
`truck_position_or_destination_unknown`으로 끝나기 때문이다. 기본값은 설정 변수다.

| 변수 | 기본값 |
|---|---|
| `DEFAULT_DESTINATION_ADDRESS` | 서울특별시 마포구 마포대로 34 (물류산업진흥재단) |
| `DEFAULT_DESTINATION_LAT` | 37.5416713 |
| `DEFAULT_DESTINATION_LNG` | 126.9493505 |

좌표는 도로 기준 근사값이다. 카카오 키가 준비되면 정확한 건물 좌표로 갱신한다.

**주소 검색**은 `GET /v1/geocode?q=`가 **카카오 Local API**를 서버에서 대신 호출한다.
브라우저에서 직접 부르지 않는 이유는 REST 키를 노출하지 않기 위해서다.
`KAKAO_REST_API_KEY`가 없으면 503을 반환하고 프론트는 기본 목적지만 쓰도록 degrade한다
([OPEN-02](08-open-issues.md#open-02-카카오-rest-api-키가-없다)).

키워드 검색과 주소 검색 **둘 다** 호출해 합친다. 기사가 '물류산업진흥재단' 같은 장소명을 넣을
수도, '마포대로 34' 같은 주소를 넣을 수도 있는데 카카오는 이를 다른 엔드포인트로 나눠 두었다.

| | 엔드포인트 | 용도 |
|---|---|---|
| 장소명 | `GET https://dapi.kakao.com/v2/local/search/keyword.json` | `place_name`, `road_address_name` |
| 주소 | `GET https://dapi.kakao.com/v2/local/search/address.json` | `address_name` |

헤더는 `Authorization: KakaoAK {REST_API_KEY}`.
**좌표는 문자열이고 `x`가 경도, `y`가 위도다.** 순서를 헷갈리기 쉬우니 주의한다.

**위치 갱신 주의** `update_truck_location`은 받은 값만 갱신한다. 위치를 못 받았으면(권한 거부 등)
그 필드를 건드리지 않아 직전 값이 남는다. 없는 값으로 덮어써서 지우면 안 된다.

**적용 위치** `main.py`의 `get_upload_url`/`geocode`/`get_defaults`, `firestore_client.update_truck_location`

---

### VIS-11 차량 제원이 곧 측정의 자다

사진 한 장으로는 절대 크기를 알 수 없다. `build_truck_frame()`이 등록된 적재함 폭·높이에
맞춰 포인트 클라우드 스케일을 정규화하는 것이 유일한 기준이다. 그래서 **사진 속 차량이
등록 제원과 다르면 CBM이 통째로 어긋난다.**

실제로 겪은 사례: `T-000001`은 기아 봉고3 1.2톤 냉동탑차(1.61 × 3.26 × 1.60 m = 8.4 CBM)로
등록돼 있는데 5톤급 윙바디 사진을 올렸다. 분석은 정상 종료했지만 결과가 8.4 CBM 차량 기준으로
나와, 사진상 텅 빈 화물칸이 "1건만 가능"으로 판정됐다. 오류가 아니라 **입력 불일치**라
파이프라인 어디서도 잡히지 않는다.

`GET /v1/trucks/{truck_id}`가 촬영 전에 제원을 내려보내고, 프론트가 촬영 버튼 위에
표시한다([FE-13](06-frontend.md#fe-13-찍기-전에-확인시켜야-하는-것-둘)). `get_truck_spec()`과
달리 필드가 빠져도 그대로 돌려준다 — 화면이 "제원 미등록"이라고 말할 수 있어야 하기 때문이다.

**등록되지 않은 차량에도 404가 아니라 200 + `registered: false`를 준다.** 404로 하면
경로가 없을 때(구버전이 떠 있거나 배포 전)와 구분되지 않는다. 실제로 멀쩡히 등록된
`T-000001`이 화면에 "등록되지 않았습니다"로 떴고, 원인은 배포가 안 끝난 것이었다.

`GET /v1/trucks`는 선택 목록용이다. 적재함 부피와 최대 중량을 함께 실어, 지금 찍은 차와
제원이 맞는 차를 고를 수 있게 한다. 치수가 없는 차량은 어차피 분석이 중단되므로 목록에서 뺀다.

### VIS-13 적재함 크기가 등록 제원과 어긋나면 숫자를 내지 않는다

`build_truck_frame`이 내는 `scale`은 "관측한 상자를 등록 제원에 맞추려면 몇 배 해야
하는가"다. Depth 모델이 미터 단위 깊이를 내므로 정상이면 1.0 근처여야 한다.

실제로 겪은 사례: **빈** 봉고 적재함을 밖에서 찍은 사진에서 4.8 CBM의 유령 화물이 잡혔다.

```
scale_correction_ratio = 0.471   # 관측 상자가 등록 제원의 2배 → 차체 외곽에 평면을 맞췄다
owl_coverage_ratio     = 0.439   # 뒤 건물·옆 차·간판을 화물로 인식
intrinsics_source      = default # EXIF 없는 이미지라 초점거리를 가정 (confidence 0.2)
```

셋 다 원인이 하나다 — **트럭 전체를 밖에서 찍었다.** 이 파이프라인은 뒷문 앞에서 적재함
안쪽을 향해 찍은 사진을 전제한다(2.1). 범위 밖 입력이라 파이프라인 어디서도 예외가 나지
않고, 그냥 조용히 틀린 CBM이 나온다.

**처음엔 `scale`로 이걸 막으려 했고, 그건 틀린 접근이었다.** 0.6~1.7로 조였더니 실제
사진이 전부 REJECT됐다. 로그의 scale이 매번 1보다 작았고(0.27 / 0.38 / 0.43 / 0.55 /
0.67) 무작위가 아니라 일관된 편향이었다.

`build_truck_frame`은 관측 상자를 **등록 제원에 맞춰 다시 스케일링**하는 함수다. 그래서
`scale`은 "초점거리를 얼마나 잘못 가정했는가"의 지표이지 "다른 물체를 쟀는가"의 지표가
아니다. EXIF 없는 사진은 초점거리가 기본값이라 1에서 벗어나는 게 정상이고, 스케일링
뒤에는 어차피 등록 제원 기준으로 정규화된다. 이 값으로 판정을 끊으면 **EXIF 없는 사진을
통째로 막는다.**

지금은 2단계다.

| 구간 | 기본값 | 동작 |
|---|---|---|
| WARN 안 | 0.70 ~ 1.50 | 그대로 계산 |
| WARN 밖 ~ REJECT 안 | 0.15 ~ 6.0 | 계산하되 품질 × `SCALE_WARN_QUALITY_FACTOR`(0.75) → LIMITED |
| REJECT 밖 | — | `scale_mismatch`. 물리적으로 말이 안 되는 값만 |

> **남은 과제.** 위 사례의 진짜 원인인 OWL 오탐(주변 건물·차량을 화물로 인식)은 이
> 게이트로 막을 수 없다. 근본 해결은 적재함 개구부 안쪽으로 화물 후보 영역을 제한하는
> 것이다. 그때까지 밖에서 찍은 사진은 여유 공간이 실제보다 **적게** 나온다.

---

### VIS-14 운행 중에도 위치를 갱신해야 한다

매칭은 `trucks` 문서의 `current_lat/lng`로 경로 회랑을 만든다. 촬영 시점 한 번만
갱신하면 트럭이 이동해도 계속 **출발지 주변** 화물만 추천된다 — 가는 길에 새로 잡히는
화물을 놓친다. `POST /v1/trucks/{id}/location`이 그 갱신 창구고, 프론트의 재매칭
루프가 주기적으로 부른다([FE-17](06-frontend.md#fe-17-사진은-한-번-매칭은-계속)).

`GET /v1/trucks/{id}/session`은 "이 차량이 최근에 찍은 운행이 아직 유효한가"를 답한다.
기준은 촬영 시각이고 기본 60분이다. 하차하지 않는 한 빈 공간은 그대로이므로 그 사이
결과를 그대로 쓸 수 있다. 품질이 REJECT면 쓸 수 있는 숫자가 없으므로 유효로 치지 않는다.

`vision_results`를 `truck_id`로 조회하지 않고 `truck_sessions/{truck_id}` 단일 문서에
쓴다. 전자는 복합색인이 필요하고 색인이 없으면 조용히 실패하는데, 차량당 최신 한 건만
알면 되므로 색인 없는 한 번 읽기로 충분하다.

---

### VIS-12 결과에 판정 근거를 함께 싣는다

최종 CBM만 주면 사용자는 값을 검산할 수 없고, 이상해도 어디가 잘못됐는지 짚지 못한다.
`result_payload`에 분해에 필요한 항을 함께 넣는다.

| 필드 | 뜻 |
|---|---|
| `cargo_width_m` `cargo_length_m` `cargo_height_m` `capacity_cbm` | 스케일 기준이 된 등록 제원 |
| `occupied_cbm` | 짐이 차지한 부피 |
| `observed_free_cbm` | 안전계수 **곱하기 전**, 사진에 빈 공간으로 보인 부피 |
| `safety_factor` | 위 값에 곱한 계수(0.70) |

관계식은 두 줄이다. 화면이 이 두 줄을 그대로 보여준다.

```
적재함 전체 = 짐 + 사진에 보인 빈 공간 + 가려진 공간
사용 가능    = 사진에 보인 빈 공간 × 안전계수
```

`observed_free_cbm`이 없으면 `usable_free_cbm`이 어디서 나온 숫자인지 알 방법이 없다
(`estimated_free_cbm`은 미관측 column을 보간한 값이라 `usable`과 곱셈 관계가 아니다).

이 필드들은 **이벤트(2.2)에는 넣지 않는다.** Matching은 쓰지 않는다.

---

## 주요 설정값

| 값 | 기본 | 근거 |
|---|---|---|
| `LONG_SIDE_PX` | 1024 | 설계서 2.1 |
| `JPEG_QUALITY` | 78 | 설계서 2.1(75-80%) |
| `VOXEL_EDGE_M` | 0.20 | 설계서 4.8 |
| `SAFETY_FACTOR` | 0.70 | 설계서 4.9. **실차 검증 전에는 올리지 않는다** |
| `QUALITY_ACCEPT_THRESHOLD` | 0.70 | 설계서 4.10 |
| `QUALITY_LIMITED_THRESHOLD` | 0.50 | 설계서 4.10 |
| `OWLVIT_MIN_SCORE` | 0.10 | [MODEL-06](03-ai-models.md#model-06-score-임계값-015는-너무-높다) |
| `MIN_STRUCTURAL_PLANES` | 2 | 설계서 4.5 |
