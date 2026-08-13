# 빈 프로젝트에서 전체 재현하기

이 저장소와 이 문서만으로 새 GCP 프로젝트에 동일한 환경을 구축하는 순서다.
**순서가 중요하다.** Eventarc 트리거는 Cloud Run 서비스가 있어야 만들 수 있고, Firestore 색인은
빌드에 수 분이 걸리며, 프론트 CORS는 프론트 주소가 정해진 뒤에야 백엔드에 넣을 수 있다.

전체 소요: 빌드 대기를 포함해 약 60-90분. 이 중 Vision 이미지 빌드가 15분씩 두 번, OWL-ViT
Endpoint 배포가 15-20분을 차지한다.

---

## 0. 사전 준비

로컬에 필요한 것:

| 도구 | 버전 | 비고 |
|---|---|---|
| Google Cloud SDK | 최신 | Windows는 [ENV-01](01-environment.md#env-01-windows-git-bash에서-gcloud-셸-래퍼가-깨진다) 확인 |
| Git | 최신 | `.sh`가 LF로 체크아웃돼야 한다([ENV-08](01-environment.md#env-08-sh가-crlf로-체크아웃되면-shebang이-깨진다)) |
| Node.js | 18 이상 | 프론트 로컬 개발에만 필요. 배포는 컨테이너가 빌드한다 |
| bash | Git Bash 또는 POSIX 셸 | infra 스크립트가 bash다 |

Python은 로컬에 없어도 된다. 백엔드 검증은 컨테이너 빌드/배포로 한다([ENV-06](01-environment.md#env-06-로컬에-실행-가능한-python이-없다)).

```bash
git clone <repo> && cd MoveAI
gcloud auth login
gcloud auth application-default login
```

---

## 1. 프로젝트와 전역 설정

```bash
export PROJECT_ID=<새-프로젝트-ID>
export REGION=asia-northeast3

gcloud config set project "$PROJECT_ID"

# ADC에 quota project를 지정하지 않으면 Vertex Model Garden 조회가 막힌다(ENV-04).
gcloud auth application-default set-quota-project "$PROJECT_ID"
gcloud config set billing/quota_project "$PROJECT_ID"
```

`billing/quota_project`를 설정하면 Resource Manager API가 필요해진다([ENV-05](01-environment.md#env-05-billingquota_project-설정의-부작용)).
아래 API 활성화에 포함돼 있다.

프로젝트 ID가 `moveai-504903`이 아니면 아래 파일들의 기본값을 바꾸거나 환경변수로 덮어쓴다.

- `vision-processor/config.py`, `matching-processor/config.py`
- `vision-processor/infra/config.sh`, `matching-processor/infra/config.sh`, `frontend/infra/config.sh`

세 `infra/config.sh` 모두 `GCP_PROJECT` 환경변수를 먼저 읽으므로, `export GCP_PROJECT=$PROJECT_ID`
만 해 두면 스크립트는 그대로 쓸 수 있다.

---

## 2. API 활성화

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  eventarc.googleapis.com \
  pubsub.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com \
  iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com \
  cloudquotas.googleapis.com \
  --project "$PROJECT_ID"
```

`cloudquotas.googleapis.com`이 없으면 OWL-ViT 배포 명령이 대화형 프롬프트를 띄우고 실패한다
([GCP-10](02-gcp-infra.md#gcp-10-model-garden-배포에-cloud-quotas-api가-필요하다)).

---

## 3. Firestore 데이터베이스

```bash
gcloud firestore databases create --location="$REGION" --type=firestore-native --project "$PROJECT_ID"
```

Native 모드여야 한다. Datastore 모드에서는 사용 중인 쿼리 형태가 동작하지 않는다.

컬렉션과 필드 스펙, 시드 방법은 [09-data-model.md](09-data-model.md)에 있다.
**최소한 `trucks`에 차량 1대는 있어야** Vision이 422로 중단되지 않는다.

---

## 4. Vertex AI OWL-ViT Endpoint

가장 오래 걸리므로 먼저 시작해 두고 다음 단계를 병행한다.

```bash
gcloud ai model-garden models deploy \
  --model=google/owlvit-base-patch32@owlvit-base-patch32 \
  --region="$REGION" --project="$PROJECT_ID" \
  --machine-type=g2-standard-8 \
  --accelerator-type=NVIDIA_L4 --accelerator-count=1 \
  --endpoint-display-name=owlvit-endpoint \
  --accept-eula --asynchronous
```

- 설계서가 지정한 `jax-owl-vit-v2`는 배포할 수 없다. 이유는 [03-ai-models.md](03-ai-models.md#model-01-jax-owl-vit-v2는-배포-경로가-없다).
- `INTERNAL`로 즉시 실패하면 재시도한다. 첫 시도가 그렇게 죽고 두 번째에 성공한 사례가 있다([GCP-11](02-gcp-infra.md#gcp-11-l4-배포가-internal로-즉시-실패할-수-있다)).
- L4 쿼터가 리전당 1이라 동시에 두 개는 못 띄운다.

완료 후 식별자 두 개를 확보한다.

```bash
gcloud ai endpoints list --region="$REGION" --project="$PROJECT_ID" \
  --format='value(name)'
gcloud ai endpoints describe <ENDPOINT_ID> --region="$REGION" --project="$PROJECT_ID" \
  --format='value(dedicatedEndpointEnabled,dedicatedEndpointDns)'
```

`vision-processor/infra/config.sh`의 `OWLVIT_ENDPOINT_ID`와 `OWLVIT_DEDICATED_DNS` 기본값을
새 값으로 바꾼다. Model Garden이 만드는 Endpoint는 dedicated라 전용 DNS로 호출해야 한다
([MODEL-07](03-ai-models.md#model-07-dedicated-endpoint는-전용-dns로-호출해야-한다)).

---

## 5. Vision 백엔드

```bash
cd vision-processor
./infra/bootstrap.sh     # SA/IAM/버킷/토픽/lifecycle/CORS. 트리거는 서비스가 없어 건너뛴다
./infra/deploy.sh        # 약 15분. Depth 가중치를 이미지에 굽는다
./infra/bootstrap.sh     # 이제 Eventarc 트리거까지 생성
./infra/verify.sh        # 전 항목 OK여야 한다
```

`bootstrap.sh`가 하는 일과 각 IAM 역할이 필요한 이유는 [02-gcp-infra.md](02-gcp-infra.md)에 있다.
특히 **런타임 SA가 자기 자신에 대해 `tokenCreator`를 가져야** signed URL이 발급된다
([GCP-06](02-gcp-infra.md#gcp-06-signed-url-발급에-자기-자신에-대한-tokencreator가-필요하다)).

---

## 6. Matching 백엔드

```bash
cd ../matching-processor
./infra/deploy.sh        # 약 3분
./infra/bootstrap.sh     # SA/IAM/복합색인/push 구독
```

복합색인은 생성 요청만 하고 즉시 반환한다. **빌드가 끝나기 전에는 후보 조회가
`FAILED_PRECONDITION`으로 실패**하고, matching이 `cargo_index_missing`으로 fail-closed된다
([GCP-13](02-gcp-infra.md#gcp-13-firestore-다중-부등호는-복합색인이-필요하고-빌드에-시간이-걸린다)).

```bash
# READY가 될 때까지 확인
gcloud firestore indexes composite list --project "$PROJECT_ID" --format='value(state)'
```

10만 건 기준 수 분이 걸린다.

---

## 7. 프론트엔드

```bash
cd ../frontend
./infra/deploy.sh        # 백엔드 주소를 자동으로 찾아 주입한다
```

배포 후 출력된 URL을 백엔드 CORS에 반영한다. 프론트 주소가 정해져야 하므로 이 순서다.

```bash
cd ../vision-processor && ./infra/deploy.sh      # CORS_ALLOW_ORIGINS 자동 반영
cd ../matching-processor && ./infra/deploy.sh
```

두 `infra/config.sh`가 `frontend` 서비스 URL을 자동으로 찾아 `CORS_ALLOW_ORIGINS`에 넣는다.
못 찾으면 `*`로 두는데, 운영에서는 명시하는 편이 낫다.

---

## 8. 동작 확인

### 8.1 Vision 단독

```bash
gcloud storage cp <테스트사진>.jpg gs://truck-vision-${PROJECT_ID}/E2E_TEST_001.jpg
```

버킷 최상단에 올리면 `photos/{truck_id}/` 규칙을 벗어나므로 `DEFAULT_TRUCK_ID`로 처리된다.
그 값이 `trucks`에 실재해야 한다([VIS-02](04-vision-processor.md#vis-02-truck_id-복원-우선순위)).

```bash
curl -s https://<vision-url>/v1/results/E2E_TEST_001
```

기대: `usable_free_cbm`, `quality_status`, `result_uri`, `model_versions`가 채워진 JSON.

### 8.2 Matching 연결

```bash
curl -s https://<matching-url>/v1/results/E2E_TEST_001
```

`can_load`가 나오면 Pub/Sub 구독까지 연결된 것이다. 404면 구독이 없거나
`space-geometry-ready` 발행이 실패한 것이다.

`truck_position_or_destination_unknown`이 나오면 목적지가 없어서다. 시연용으로 넣으려면:

```bash
cd matching-processor && ./infra/seed_truck_position.sh T-000001
```

### 8.3 프론트엔드

```bash
curl -s https://<frontend-url>/config.js
```

두 백엔드 URL이 채워져 있어야 한다. 그다음 휴대폰 브라우저로 접속해 촬영 → 결과까지 확인한다.

### 8.4 전체 점검

```bash
cd vision-processor && ./infra/verify.sh
```

---

## 9. 마무리

시연이 끝나면 상시 과금되는 것을 정리한다. [07-operations.md](07-operations.md#시연-후-정리)를 참조한다.

```bash
# Cloud Run min-instances 되돌리기
cd vision-processor && MIN_INSTANCES=0 ./infra/deploy.sh
# OWL-ViT Endpoint undeploy (L4가 시간당 과금된다)
```

---

## 재현 시 자주 막히는 지점

| 증상 | 원인 | 문서 |
|---|---|---|
| `gcloud`가 `Python`만 출력하고 종료 | Windows 셸 래퍼 깨짐 | [ENV-01](01-environment.md) |
| `--format`/`--filter`가 통째로 안 먹힘 | cmd.exe 인용부호 | [ENV-02](01-environment.md), [ENV-03](01-environment.md) |
| Cloud Run이 메모리 초과로 죽음 | 4Gi 부족 | [GCP-01](02-gcp-infra.md) |
| 이벤트가 재시도로 쌓이며 OOM | 동시성 80 | [GCP-02](02-gcp-infra.md) |
| GCS 다운로드 403 | 자기 자신 impersonate | [GCP-06](02-gcp-infra.md) |
| OWL-ViT 탐지 0건 | 프롬프트 템플릿 | [MODEL-05](03-ai-models.md) |
| 박스 좌표가 엉뚱함 | 절대 픽셀인데 스케일 곱함 | [MODEL-04](03-ai-models.md) |
| matching이 계속 `cargo_index_missing` | 색인 빌드 중 | [GCP-13](02-gcp-infra.md) |
| 브라우저 업로드가 preflight에서 막힘 | 버킷 CORS | [GCP-05](02-gcp-infra.md) |
