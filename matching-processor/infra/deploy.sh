#!/usr/bin/env bash
# matching-processor를 Cloud Run에 배포한다. 설정은 infra/config.sh에 고정돼 있다.
#
#   ./infra/deploy.sh
set -euo pipefail

cd "$(dirname "$0")/.."
source infra/config.sh

echo "== 배포 =="
echo "  service : $SERVICE ($REGION)"
echo "  runtime SA : $SERVICE_ACCOUNT"
echo "  memory=$MEMORY cpu=$CPU concurrency=$CONCURRENCY timeout=$TIMEOUT min-instances=$MIN_INSTANCES"
echo "  env : $ENV_VARS"
echo

$GCLOUD run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --service-account "$SERVICE_ACCOUNT" \
  --allow-unauthenticated \
  --memory "$MEMORY" \
  --cpu "$CPU" \
  --concurrency "$CONCURRENCY" \
  --timeout "$TIMEOUT" \
  --min-instances "$MIN_INSTANCES" \
  --set-env-vars "$ENV_VARS" \
  --quiet

echo
echo "== 배포 결과 =="
$GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT_ID" \
  --format='value(status.latestReadyRevisionName,status.url)' \
  | tr -d '\r' | awk -F'\t' '{printf "  revision=%s\n  url=%s\n", $1, $2}'

echo
echo "push 구독을 아직 안 만들었다면: ./infra/bootstrap.sh"
