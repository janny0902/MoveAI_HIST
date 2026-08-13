#!/usr/bin/env bash
# vision-processor가 돌기 위해 필요한 GCP 리소스/권한을 만든다.
# 여러 번 실행해도 안전하다(이미 있으면 건너뛴다). 배포는 deploy.sh가 담당한다.
#
#   ./infra/bootstrap.sh
set -euo pipefail

cd "$(dirname "$0")/.."
source infra/config.sh

echo "== 대상 =="
echo "  project : $PROJECT_ID ($PROJECT_NUMBER)"
echo "  region  : $REGION"
echo "  runtime SA : $SERVICE_ACCOUNT"
echo

# ---------------------------------------------------------------------------
# 1. API
# ---------------------------------------------------------------------------
echo "== API 활성화 =="
$GCLOUD services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  eventarc.googleapis.com \
  pubsub.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com \
  iamcredentials.googleapis.com \
  --project "$PROJECT_ID"

# ---------------------------------------------------------------------------
# 2. 런타임 서비스 계정
# ---------------------------------------------------------------------------
echo "== 서비스 계정 =="
if $GCLOUD iam service-accounts describe "$SERVICE_ACCOUNT" --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "  이미 있음: $SERVICE_ACCOUNT"
else
  $GCLOUD iam service-accounts create "${SERVICE_ACCOUNT%%@*}" \
    --display-name "vision-processor runtime" --project "$PROJECT_ID"
fi

# ---------------------------------------------------------------------------
# 3. 런타임 SA 권한
#    add-iam-policy-binding은 멱등이라 재실행해도 중복 부여되지 않는다.
# ---------------------------------------------------------------------------
echo "== 런타임 SA 권한 =="
for role in \
  roles/storage.objectAdmin \
  roles/datastore.user \
  roles/pubsub.publisher \
  roles/aiplatform.user
do
  echo "  + $role"
  $GCLOUD projects add-iam-policy-binding "$PROJECT_ID" \
    --member "serviceAccount:${SERVICE_ACCOUNT}" \
    --role "$role" --condition=None --quiet >/dev/null
done

# V4 signed URL은 서명 키가 필요한데 메타데이터 서버 ADC에는 개인키가 없다.
# storage_client._signing_client()가 IAM signBlob으로 대신 서명하려면
# 런타임 SA가 자기 자신에 대해 tokenCreator를 가져야 한다.
echo "  + roles/iam.serviceAccountTokenCreator (자기 자신에 대해, signed URL 발급용)"
$GCLOUD iam service-accounts add-iam-policy-binding "$SERVICE_ACCOUNT" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/iam.serviceAccountTokenCreator \
  --project "$PROJECT_ID" --quiet >/dev/null

# ---------------------------------------------------------------------------
# 4. Eventarc 경로 권한
# ---------------------------------------------------------------------------
echo "== Eventarc 권한 =="
# GCS -> Eventarc는 Cloud Storage 서비스 에이전트가 Pub/Sub에 publish해서 동작한다.
GCS_AGENT="$($GCLOUD storage service-agent --project "$PROJECT_ID" | tr -d '[:space:]')"
echo "  + roles/pubsub.publisher -> $GCS_AGENT"
$GCLOUD projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${GCS_AGENT}" \
  --role roles/pubsub.publisher --condition=None --quiet >/dev/null

for role in roles/eventarc.eventReceiver roles/run.invoker; do
  echo "  + $role -> $TRIGGER_SA"
  $GCLOUD projects add-iam-policy-binding "$PROJECT_ID" \
    --member "serviceAccount:${TRIGGER_SA}" \
    --role "$role" --condition=None --quiet >/dev/null
done

# ---------------------------------------------------------------------------
# 5. 버킷 / 토픽
# ---------------------------------------------------------------------------
echo "== 버킷 / 토픽 =="
if $GCLOUD storage buckets describe "gs://${BUCKET}" --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "  이미 있음: gs://${BUCKET}"
else
  $GCLOUD storage buckets create "gs://${BUCKET}" \
    --location "$REGION" --uniform-bucket-level-access --project "$PROJECT_ID"
fi

if $GCLOUD pubsub topics describe "$TOPIC" --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "  이미 있음: $TOPIC"
else
  $GCLOUD pubsub topics create "$TOPIC" --project "$PROJECT_ID"
fi

# 5.1: 원본과 중간 결과에 lifecycle rule을 적용한다. 시연용 사진을 무기한 쌓아 두지 않는다.
echo "  lifecycle: ${BUCKET_LIFECYCLE_DAYS}일 후 삭제"
LIFECYCLE_FILE="$(mktemp)"
cat > "$LIFECYCLE_FILE" <<JSON
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": ${BUCKET_LIFECYCLE_DAYS}}}]}
JSON
$GCLOUD storage buckets update "gs://${BUCKET}" \
  --lifecycle-file="$LIFECYCLE_FILE" --project "$PROJECT_ID" >/dev/null
rm -f "$LIFECYCLE_FILE"

# D1: PWA가 브라우저에서 Signed URL로 GCS에 직접 PUT하려면 버킷 CORS가 열려 있어야 한다.
# 열지 않으면 preflight에서 막혀 업로드가 통째로 실패한다.
echo "  CORS: PUT 허용"
CORS_FILE="$(mktemp)"
cat > "$CORS_FILE" <<'JSON'
[{"origin": ["*"], "method": ["PUT", "GET", "HEAD"],
  "responseHeader": ["Content-Type", "x-goog-resumable"], "maxAgeSeconds": 3600}]
JSON
$GCLOUD storage buckets update "gs://${BUCKET}" \
  --cors-file="$CORS_FILE" --project "$PROJECT_ID" >/dev/null
rm -f "$CORS_FILE"

# ---------------------------------------------------------------------------
# 6. Eventarc 트리거
#    Cloud Run 서비스가 먼저 있어야 만들 수 있다. 없으면 안내만 하고 넘어간다.
# ---------------------------------------------------------------------------
echo "== Eventarc 트리거 =="
if $GCLOUD eventarc triggers describe "$TRIGGER" --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "  이미 있음: $TRIGGER"
elif ! $GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "  건너뜀: Cloud Run 서비스 '$SERVICE'가 아직 없다. ./infra/deploy.sh 실행 후 이 스크립트를 다시 돌린다."
else
  $GCLOUD eventarc triggers create "$TRIGGER" \
    --location "$REGION" \
    --destination-run-service "$SERVICE" \
    --destination-run-region "$REGION" \
    --destination-run-path "/" \
    --event-filters "type=google.cloud.storage.object.v1.finalized" \
    --event-filters "bucket=${BUCKET}" \
    --service-account "$TRIGGER_SA" \
    --project "$PROJECT_ID"
fi

echo
echo "완료. 다음: ./infra/deploy.sh"
