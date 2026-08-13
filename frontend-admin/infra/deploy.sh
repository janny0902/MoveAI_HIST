#!/usr/bin/env bash
# frontend를 Cloud Run에 배포한다.
# 백엔드(vision/matching) 배포와 완전히 독립적이다 — UI만 고치면 이것만 돌리면 되고,
# Depth 가중치를 굽는 vision 이미지를 다시 빌드하지 않는다.
#
#   ./infra/deploy.sh
set -euo pipefail

cd "$(dirname "$0")/.."
source infra/config.sh

if [[ -z "$VISION_BASE_URL" ]]; then
  echo "VISION_BASE_URL을 찾을 수 없다. vision-processor를 먼저 배포하거나 환경변수로 지정한다." >&2
  exit 1
fi

echo "== 배포 =="
echo "  service : $SERVICE ($REGION)"
echo "  vision   : $VISION_BASE_URL"
echo "  matching : ${MATCHING_BASE_URL:-<미설정>}"
echo

# 정적 서빙 전용 SA. 역할을 주지 않아 프론트가 백엔드 데이터에 직접 닿지 못한다.
if ! $GCLOUD iam service-accounts describe "$SERVICE_ACCOUNT" --project "$PROJECT_ID" >/dev/null 2>&1; then
  $GCLOUD iam service-accounts create "${SERVICE_ACCOUNT%%@*}" \
    --display-name=frontend-runtime --project "$PROJECT_ID"
fi

$GCLOUD run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --service-account "$SERVICE_ACCOUNT" \
  --allow-unauthenticated \
  --memory "$MEMORY" \
  --cpu "$CPU" \
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
echo "이 주소를 vision/matching의 CORS 허용 목록에 넣어야 한다:"
echo "  cd ../vision-processor && CORS_ALLOW_ORIGINS=<위 url> ./infra/deploy.sh"
