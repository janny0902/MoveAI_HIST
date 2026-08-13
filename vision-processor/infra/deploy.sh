#!/usr/bin/env bash
# vision-processor를 Cloud Run에 배포한다.
# 리소스 설정은 infra/config.sh에 고정돼 있다 — gcloud run deploy를 직접 치지 말 것.
# (직접 치면 --memory/--concurrency가 빠져 4Gi/동시성 80 기본값으로 되돌아가 OOM 난다.)
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
# --format 문자열에 따옴표를 중첩하면 Windows의 gcloud.cmd가 인자를 깨뜨린다. 탭 구분 값만 받는다.
$GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT_ID" \
  --format='value(status.latestReadyRevisionName,spec.template.spec.containers[0].resources.limits.memory,spec.template.spec.containers[0].resources.limits.cpu,spec.template.spec.containerConcurrency)' \
  | tr -d '\r' | awk -F'\t' '{printf "  revision=%s memory=%s cpu=%s concurrency=%s\n", $1, $2, $3, $4}'

echo
echo "설정이 config.sh와 맞는지 확인하려면: ./infra/verify.sh"
