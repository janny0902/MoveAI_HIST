# 07. 운영 · 배포 · 비용

## 서비스 구성

| 서비스 | 역할 | 배포 | 빌드 시간 |
|---|---|---|---|
| `vision-processor` | 이미지 → CBM. API만 제공 | `vision-processor/infra/deploy.sh` | 약 15분 |
| `matching-processor` | CBM → 화물 조합 | `matching-processor/infra/deploy.sh` | 약 3분 |
| `frontend` | D1 촬영 앱 | `frontend/infra/deploy.sh` | 약 2분 |

```
PWA → (Signed URL) → GCS → Eventarc → vision-processor
                                          ↓ Pub/Sub space-geometry-ready
                                      matching-processor → Firestore
PWA ← 결과 폴링 ← vision-processor / matching-processor
```

---

## 배포 규칙

**`gcloud run deploy`를 손으로 치지 않는다.** 플래그가 빠져 메모리 4Gi / 동시성 80 기본값으로
되돌아가고 컨테이너가 OOM으로 죽는다([GCP-01](02-gcp-infra.md#gcp-01-cloud-run-메모리-4gi로는-vision이-죽는다),
[GCP-02](02-gcp-infra.md#gcp-02-기본-동시성-80이-oom을-증폭시킨다)). 항상 `infra/deploy.sh`를 쓴다.

설정을 바꿀 때는 `infra/config.sh`만 고치고 다시 배포한다. 일회성 변경은 환경변수로 덮어쓴다.

```bash
MEMORY=16Gi ./infra/deploy.sh
MIN_INSTANCES=0 ./infra/deploy.sh
```

### 무엇을 고치면 무엇을 배포해야 하나

| 고친 곳 | 배포 대상 |
|---|---|
| `frontend/src/**` | frontend만 |
| `vision-processor/**` | vision만 |
| `matching-processor/**` | matching만 |
| 프론트 URL이 바뀜 | vision + matching(CORS 갱신) |
| OWL-ViT Endpoint 교체 | vision(`OWLVIT_ENDPOINT_ID`, `OWLVIT_DEDICATED_DNS`) |
| `tools/**` | 배포 불필요. 로컬에서 실행하는 스크립트다 |

### `.env.local`이 없는 PC에서 배포할 때

`infra/deploy.sh`는 `--set-env-vars`로 환경변수 **전체 집합**을 넘긴다. `infra/.env.local`이
없는 PC에서 그대로 돌리면 `KAKAO_REST_API_KEY`가 **빈 값으로 덮여** 우회시간이 직선거리
추정으로 떨어진다. 그 파일은 gitignore 대상이라 다른 PC로 따라오지 않는다.

키를 모르는 채 코드만 배포해야 하면 `--set-env-vars`를 빼고 직접 부른다. Cloud Run은
플래그를 주지 않은 환경변수를 **그대로 유지**한다.

```bash
gcloud run deploy matching-processor --source .   --region asia-northeast3 --project moveai-504903   --service-account matching-sa@moveai-504903.iam.gserviceaccount.com   --allow-unauthenticated --memory 8Gi --cpu 8 --timeout 900s
```

### matching-processor 리소스가 커졌다

차량 기준 매칭이 후보를 최대 10만 건까지 보고, 그 규모로 CP-SAT를 돌린다.

| 값 | 이전 | 현재 | 이유 |
|---|---|---|---|
| memory | 1Gi | **8Gi** | 후보 수만 건 규모의 솔버 모델 |
| cpu | 1 | **8** | CP-SAT 병렬 탐색 |
| timeout | 120s | **900s** | 10만 건 조회 50초 + 솔버 120초 |
| `SOLVER_TIME_LIMIT_S` | 1.0 | **120** | 1초는 후보 수천 건에서 사실상 매번 실패 |

`infra/config.sh`의 기본값은 아직 옛 값이다. **이 설정으로 배포하려면 위 플래그를 직접
주거나 config.sh를 고쳐야 한다.**

---

## 드리프트 점검

```bash
cd vision-processor && ./infra/verify.sh
```

Cloud Run 리소스(메모리/CPU/동시성/SA/min-instances), 런타임 SA 역할, Eventarc 트리거를
`config.sh`와 대조한다. 불일치가 있으면 exit 1이다. 콘솔에서 손으로 만졌거나 플래그 없는
`gcloud run deploy`를 친 뒤 확인하면 좋다.

---

## 로그 보는 법

```bash
# 구조화 로그(권장). 필드 단위 조회가 된다
gcloud logging read 'jsonPayload.message="vision_result"' --limit 5 --project "$PROJECT_ID"

# 서비스별 최근 로그
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="vision-processor"' \
  --limit 30 --freshness=15m --project "$PROJECT_ID" --format='value(timestamp,textPayload)'
```

주의: `--freshness`는 `--order=asc`와 함께 쓰면 무시된다([ENV-09](01-environment.md#env-09-gcloud-logging-read의---freshness는---orderasc에서-무시된다)).

Eventarc 핸들러가 항상 200을 반환하므로([VIS-01](04-vision-processor.md#vis-01-eventarc에는-항상-200을-반환한다))
**실패는 HTTP 상태가 아니라 로그에만 나타난다.**

---

## 비용이 발생하는 것

| 항목 | 성격 | 정리 방법 |
|---|---|---|
| **Vertex OWL-ViT Endpoint (L4 x1)** | **상시 과금.** 가장 크다 | undeploy |
| vision-processor `min-instances=1` | 상시 과금 | `MIN_INSTANCES=0`로 재배포 |
| matching-processor | 요청당 | 조치 불필요 |
| frontend | 요청당, `min-instances=0` | 조치 불필요 |
| GCS | 저장량. lifecycle 7일 | 자동 |
| Firestore | 읽기/쓰기 | 10만 건 조회를 남발하지 않도록 색인 유지 |

설계서 5.5도 "시연 종료 후 Vertex 모델을 undeploy하고 Cloud Run min instance를 0으로
되돌린다"고 명시한다.

---

## 시연 전 체크리스트

- [ ] `cd vision-processor && ./infra/verify.sh` → 전 항목 OK
- [ ] Firestore 복합색인 `READY`
- [ ] `trucks/{데모차량}`에 W/L/H, `max_payload_kg`, `current_loaded_weight_kg` 존재
- [ ] `trucks/{데모차량}`에 `destination_lat/lng` 존재 (없으면 `seed_truck_position.sh`)
- [ ] 데모 차량 주변 30km에 `status=WAITING` 화물 존재
- [ ] OWL-ViT Endpoint 배포 상태
- [ ] `curl <frontend>/config.js`에 두 백엔드 URL이 채워져 있음
- [ ] 사진 1장으로 E2E 1회 성공 (Vision 60-105초 소요)
- [ ] 시연 20-30분 전 워밍업(설계서 5.5)

## 시연 후 정리

```bash
# 1. Cloud Run min-instances 되돌리기
cd vision-processor && MIN_INSTANCES=0 ./infra/deploy.sh

# 2. OWL-ViT Endpoint undeploy (가장 큰 비용)
gcloud ai endpoints list --region="$REGION" --project="$PROJECT_ID"
gcloud ai endpoints undeploy-model <ENDPOINT_ID> \
  --deployed-model-id=<DEPLOYED_MODEL_ID> --region="$REGION" --project="$PROJECT_ID"

# 3. 테스트 오브젝트 정리(원치 않으면 lifecycle 7일에 맡겨도 된다)
gcloud storage ls gs://truck-vision-${PROJECT_ID}/
```

Endpoint를 내리면 Vision은 `owl_boxes=[]`로 degrade해 계속 동작한다(설계서 5.8).
품질점수에서 0.10을 잃을 뿐 파이프라인이 멈추지는 않는다.

---

## 장애 대응

| 증상 | 확인 순서 |
|---|---|
| 업로드해도 결과가 안 나온다 | Eventarc 트리거 존재 → GCS 서비스 에이전트 pubsub.publisher([GCP-08](02-gcp-infra.md#gcp-08-gcs-서비스-에이전트에-pubsubpublisher가-필요하다)) → vision 로그 |
| Vision 로그에 아무것도 없다 | 트리거가 발화하지 않았다. 확장자가 `.jpg/.jpeg/.png`인지 확인 |
| `duplicate`로만 끝난다 | `processed_photos/{photo_id}` 삭제 후 재시도([VIS-03](04-vision-processor.md#vis-03-photo_id-기반-idempotency)) |
| 컨테이너가 메모리로 죽는다 | `verify.sh`로 8Gi/동시성1 확인 |
| Matching 결과가 404 | Pub/Sub 구독 존재 확인([GCP-15](02-gcp-infra.md#gcp-15-pubsub-구독이-없으면-이벤트는-조용히-버려진다)) |
| `cargo_index_missing` | 색인 `READY` 대기 |
| `truck_position_or_destination_unknown` | `seed_truck_position.sh` |
| 브라우저 업로드 실패 | 버킷 CORS, 백엔드 `CORS_ALLOW_ORIGINS` |
| `quality_status`가 계속 REJECTED | OWL-ViT Endpoint 상태, `owl_box_count` 로그 확인 |
