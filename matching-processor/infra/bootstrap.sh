#!/usr/bin/env bash
# matching-processor가 돌기 위해 필요한 GCP 리소스/권한을 만든다. 멱등.
# Cloud Run 서비스가 이미 있어야 push 구독을 만들 수 있다(없으면 그 단계만 건너뛴다).
#
#   ./infra/bootstrap.sh
set -euo pipefail

cd "$(dirname "$0")/.."
source infra/config.sh

echo "== 대상 =="
echo "  project : $PROJECT_ID ($PROJECT_NUMBER)"
echo "  runtime SA : $SERVICE_ACCOUNT"
echo

echo "== API 활성화 =="
$GCLOUD services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  pubsub.googleapis.com \
  firestore.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project "$PROJECT_ID"

echo "== 서비스 계정 =="
if $GCLOUD iam service-accounts describe "$SERVICE_ACCOUNT" --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "  이미 있음: $SERVICE_ACCOUNT"
else
  $GCLOUD iam service-accounts create "${SERVICE_ACCOUNT%%@*}" \
    --display-name=matching-processor-runtime --project "$PROJECT_ID"
fi

# Firestore만. storage 권한은 의도적으로 부여하지 않는다 — 설계서 1.3/5.9의
# "Matching은 이미지와 depth map을 읽지 않는다"를 IAM 수준에서 강제한다.
echo "  + roles/datastore.user (storage 권한은 의도적으로 없음)"
$GCLOUD projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role=roles/datastore.user --condition=None --quiet >/dev/null

# ---------------------------------------------------------------------------
# M2 회랑 조회용 복합색인
#   pending_cargos에 geohash 필드가 없어(10만 건) 위경도 박스 다중 부등호로 조회한다.
#   부등호가 걸리는 모든 필드가 색인에 있어야 한다.
# ---------------------------------------------------------------------------
echo "== Firestore 복합색인 =="
if $GCLOUD firestore indexes composite list --project "$PROJECT_ID" \
     --format='value(fields)' 2>/dev/null | tr -d '\r' | grep -q "pickup_lng"; then
  echo "  이미 있음: ${CARGOS_COLLECTION}(status, pickup_lat, pickup_lng)"
else
  $GCLOUD firestore indexes composite create \
    --collection-group="$CARGOS_COLLECTION" \
    --field-config=field-path=status,order=ascending \
    --field-config=field-path=pickup_lat,order=ascending \
    --field-config=field-path=pickup_lng,order=ascending \
    --project "$PROJECT_ID" --async
  echo "  생성 요청함(빌드에 시간이 걸린다). 완료 전에는 조회가 FAILED_PRECONDITION으로 실패한다."
fi

# ---------------------------------------------------------------------------
# M1: space-geometry-ready push 구독
# ---------------------------------------------------------------------------
echo "== Pub/Sub push 구독 =="
if ! $GCLOUD pubsub topics describe "$TOPIC" --project "$PROJECT_ID" >/dev/null 2>&1; then
  $GCLOUD pubsub topics create "$TOPIC" --project "$PROJECT_ID"
fi

SERVICE_URL="$($GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT_ID" \
  --format='value(status.url)' 2>/dev/null | tr -d '\r')"

if [[ -z "$SERVICE_URL" ]]; then
  echo "  건너뜀: Cloud Run '$SERVICE'가 아직 없다. ./infra/deploy.sh 후 다시 실행한다."
elif $GCLOUD pubsub subscriptions describe "$SUBSCRIPTION" --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "  이미 있음: $SUBSCRIPTION -> $SERVICE_URL"
else
  $GCLOUD projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${PUSH_SA}" --role=roles/run.invoker --condition=None --quiet >/dev/null
  $GCLOUD pubsub subscriptions create "$SUBSCRIPTION" \
    --topic="$TOPIC" \
    --push-endpoint="$SERVICE_URL/" \
    --push-auth-service-account="$PUSH_SA" \
    --ack-deadline=120 \
    --project "$PROJECT_ID"
fi

# ---------------------------------------------------------------------------
# 운송장 대량 적재 (CSV/JSONL -> GCS -> Eventarc -> matching)
# ---------------------------------------------------------------------------
echo "== 운송장 적재 버킷 =="
if $GCLOUD storage buckets describe "gs://${CARGO_INGEST_BUCKET}" --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "  이미 있음: gs://${CARGO_INGEST_BUCKET}"
else
  $GCLOUD storage buckets create "gs://${CARGO_INGEST_BUCKET}" \
    --location "$REGION" --uniform-bucket-level-access --project "$PROJECT_ID"
fi

# 읽기 권한을 이 버킷에만 준다. 프로젝트 전체 storage 역할을 주면 사진 버킷까지 열려
# 설계서 1.3/5.9의 경계가 무너진다.
echo "  + roles/storage.objectViewer (이 버킷에만)"
$GCLOUD storage buckets add-iam-policy-binding "gs://${CARGO_INGEST_BUCKET}" \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role=roles/storage.objectViewer --project "$PROJECT_ID" >/dev/null

echo "== 운송장 적재 트리거 =="
GCS_AGENT="$($GCLOUD storage service-agent --project "$PROJECT_ID" | tr -d '[:space:]')"
$GCLOUD projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${GCS_AGENT}" \
  --role=roles/pubsub.publisher --condition=None --quiet >/dev/null

if $GCLOUD eventarc triggers describe "$CARGO_TRIGGER" --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "  이미 있음: $CARGO_TRIGGER"
elif [[ -z "$SERVICE_URL" ]]; then
  echo "  건너뜀: Cloud Run '$SERVICE'가 아직 없다."
else
  # MSYS2_ARG_CONV_EXCL: Git Bash는 "/v1/..."처럼 슬래시로 시작하는 인자를 Windows 경로로
  # 바꿔 "C:/Program Files/Git/v1/events/cargo-file"을 보낸다. 이 인자만 변환에서 제외한다.
  # MSYS_NO_PATHCONV=1로 전체를 끄면 gcloud.cmd 내부의 경로 해석까지 깨진다.
  # "//v1/..."로 이스케이프하는 방법도 이 환경에서는 슬래시가 그대로 남아 실패했다.
  MSYS2_ARG_CONV_EXCL='/v1/events/cargo-file' \
  $GCLOUD eventarc triggers create "$CARGO_TRIGGER" \
    --location "$REGION" \
    --destination-run-service "$SERVICE" \
    --destination-run-region "$REGION" \
    --destination-run-path "/v1/events/cargo-file" \
    --event-filters "type=google.cloud.storage.object.v1.finalized" \
    --event-filters "bucket=${CARGO_INGEST_BUCKET}" \
    --service-account "$PUSH_SA" \
    --project "$PROJECT_ID"
fi

# ---------------------------------------------------------------------------
# 만료 운송장 자동 정리 (Firestore TTL)
# ---------------------------------------------------------------------------
echo "== 운송장 TTL =="
echo "  ${CARGOS_COLLECTION}.${CARGO_TTL_FIELD} 기준 자동 삭제"
$GCLOUD firestore fields ttls update "$CARGO_TTL_FIELD" \
  --collection-group="$CARGOS_COLLECTION" --enable-ttl \
  --project "$PROJECT_ID" --async --quiet 2>&1 | tail -1 || \
  echo "  (이미 설정돼 있거나 권한이 필요할 수 있다)"

echo
echo "완료. 다음: ./infra/deploy.sh"
