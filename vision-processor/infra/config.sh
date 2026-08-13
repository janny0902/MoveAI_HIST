#!/usr/bin/env bash
# vision-processor 인프라 설정 단일 출처(single source of truth).
# bootstrap.sh / deploy.sh가 이 파일을 source한다. 직접 실행하지 않는다.
#
# 각 값은 환경변수로 덮어쓸 수 있다:  MEMORY=16Gi ./deploy.sh

# Windows(Git Bash)에서는 Cloud SDK의 bin/gcloud 셸 래퍼가 Python을 못 찾고 깨진다.
# 실제로 동작하는 실행 파일을 골라 $GCLOUD로 쓴다. Linux/macOS에서는 그냥 gcloud가 잡힌다.
if [[ -z "${GCLOUD:-}" ]]; then
  if gcloud version >/dev/null 2>&1; then
    GCLOUD=gcloud
  elif gcloud.cmd version >/dev/null 2>&1; then
    GCLOUD=gcloud.cmd
  else
    echo "gcloud를 찾을 수 없다. Cloud SDK 설치 후 PATH를 확인한다." >&2
    exit 1
  fi
fi

# 로컬 비밀값(API 키 등). git에 올리지 않는다 — .gitignore 참조.
_secrets="$(dirname "${BASH_SOURCE[0]}")/.env.local"
[[ -f "$_secrets" ]] && source "$_secrets"

PROJECT_ID="${GCP_PROJECT:-moveai-504903}"
REGION="${GCP_LOCATION:-asia-northeast3}"
SERVICE="${SERVICE:-vision-processor}"

# 아래 CORS 오리진 계산과 Eventarc SA가 모두 쓰므로 여기서 먼저 구한다.
PROJECT_NUMBER="$($GCLOUD projects describe "$PROJECT_ID" --format='value(projectNumber)' | tr -d '[:space:]')"

SERVICE_ACCOUNT="${VISION_SA_EMAIL:-vision-sa@${PROJECT_ID}.iam.gserviceaccount.com}"
BUCKET="${VISION_BUCKET:-truck-vision-${PROJECT_ID}}"
TOPIC="${SPACE_GEOMETRY_TOPIC:-space-geometry-ready}"
TRIGGER="${TRIGGER:-vision-gcs-trigger}"

# ---------------------------------------------------------------------------
# Cloud Run 리소스 설정 — 아래 값을 임의로 낮추지 말 것
# ---------------------------------------------------------------------------
# MEMORY: 4Gi에서 "Memory limit of 4096 MiB exceeded with 4109 MiB used"로 컨테이너가
#   종료됐다. torch + transformers(Depth-Anything V2) + open3d가 동시에 상주한다.
# CONCURRENCY: 기본값 80이면 Eventarc 재시도가 한 인스턴스에 몰려 위 한도를 곧바로 넘긴다.
#   이미지 1장당 인스턴스 1개로 고정한다.
MEMORY="${MEMORY:-8Gi}"
CPU="${CPU:-4}"
CONCURRENCY="${CONCURRENCY:-1}"
TIMEOUT="${TIMEOUT:-300s}"
# 5.4: 시연 시간에는 min-instances=1로 콜드 스타트를 없앤다.
# 시연이 끝나면 0으로 되돌린다(5.5) — MIN_INSTANCES=0 ./infra/deploy.sh
#
# 이 값은 --min-instances 없이 gcloud run deploy를 치면 조용히 0으로 돌아간다.
# 실제로 그렇게 어긋나 있었다(2026-08-11에 1로 되돌림). 배포 명령을 손으로 칠 거면
# docs/09-ops.md 8.2의 명령을 그대로 쓸 것 — 거기에 --min-instances가 들어 있다.
# 어긋났는지는 ./infra/verify.sh가 minInstances 항목으로 잡아낸다.
MIN_INSTANCES="${MIN_INSTANCES:-1}"

# 5.1: 원본과 중간 결과에 적용할 lifecycle. 지난 일수 기준으로 삭제한다.
BUCKET_LIFECYCLE_DAYS="${BUCKET_LIFECYCLE_DAYS:-7}"

# OWL-ViT Endpoint (3.1). 비우면 geometry-only로 degrade하고 품질점수에서 0.10을 잃는다.
# Model Garden deploy가 만드는 Endpoint는 dedicated라 전용 DNS로 호출해야 한다.
OWLVIT_ENDPOINT_ID="${OWLVIT_ENDPOINT_ID:-mg-endpoint-b5f65ecd-9f9f-4b2f-ac10-2201d1c7b1ba}"
OWLVIT_DEDICATED_DNS="${OWLVIT_DEDICATED_DNS:-mg-endpoint-b5f65ecd-9f9f-4b2f-ac10-2201d1c7b1ba.asia-northeast3-91742102060.prediction.vertexai.goog}"

# 프론트엔드가 브라우저에서 직접 호출하므로 그 오리진을 CORS로 허용해야 한다.
#
# 주의: Cloud Run 서비스에는 접속 가능한 URL이 두 개 있다.
#   https://<svc>-<hash>.<region>.run.app          <- status.url이 돌려주는 값
#   https://<svc>-<project-number>.<region>.run.app
# 둘 다 정상 동작하므로 사용자가 어느 쪽으로 들어오는지 알 수 없다. status.url 하나만
# 허용하면 다른 주소로 접속했을 때 preflight에서 막혀 "Failed to fetch"가 난다. 둘 다 넣는다.
FRONTEND_URL="${FRONTEND_URL:-$($GCLOUD run services describe frontend \
  --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)' 2>/dev/null | tr -d '[:space:]')}"
FRONTEND_URL_ALT="https://frontend-${PROJECT_NUMBER}.${REGION}.run.app"

if [[ -n "$FRONTEND_URL" && "$FRONTEND_URL" != "$FRONTEND_URL_ALT" ]]; then
  _default_origins="${FRONTEND_URL};${FRONTEND_URL_ALT}"
else
  _default_origins="${FRONTEND_URL:-*}"
fi
CORS_ALLOW_ORIGINS="${CORS_ALLOW_ORIGINS:-$_default_origins}"

# Cloud Run에 설정할 환경변수 전체 집합.
# deploy.sh가 --set-env-vars로 넘기므로 여기 없는 값은 배포 시 제거된다.
KAKAO_REST_API_KEY="${KAKAO_REST_API_KEY:-}"

ENV_VARS="${ENV_VARS:-OMP_NUM_THREADS=4,KAKAO_REST_API_KEY=${KAKAO_REST_API_KEY},OWLVIT_ENDPOINT_ID=${OWLVIT_ENDPOINT_ID},OWLVIT_DEDICATED_DNS=${OWLVIT_DEDICATED_DNS},CORS_ALLOW_ORIGINS=${CORS_ALLOW_ORIGINS}}"

# Eventarc 트리거가 사용하는 SA. 현재는 Compute 기본 SA를 그대로 쓴다.
TRIGGER_SA="${TRIGGER_SA:-${PROJECT_NUMBER}-compute@developer.gserviceaccount.com}"
