#!/usr/bin/env bash
# frontend 인프라 설정 단일 출처. deploy.sh가 source한다.

# Windows(Git Bash)에서는 Cloud SDK의 bin/gcloud 셸 래퍼가 Python을 못 찾고 깨진다.
# gcloud.cmd는 cmd.exe를 거치므로 인자에 공백이나 중첩 따옴표를 넣지 않는다.
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

# 로컬 비밀값. git에 올리지 않는다 — .gitignore의 */infra/.env.local 참조.
# 지도를 켜려면 여기에 KAKAO_JS_KEY=... 한 줄을 넣는다(카카오 개발자 콘솔의
# JavaScript 키. 길찾기/주소검색에 쓰는 REST 키와 다른 값이다).
_secrets="$(dirname "${BASH_SOURCE[0]}")/.env.local"
[[ -f "$_secrets" ]] && source "$_secrets"

PROJECT_ID="${GCP_PROJECT:-moveai-504903}"
REGION="${GCP_LOCATION:-asia-northeast3}"
SERVICE="${SERVICE:-frontend}"

# 정적 파일만 서빙하므로 GCP 리소스에 접근할 필요가 없다.
# 전용 SA에 아무 역할도 주지 않아, 프론트 컨테이너가 백엔드 데이터에 직접 닿지 못하게 한다.
SERVICE_ACCOUNT="${FRONTEND_SA_EMAIL:-frontend-sa@${PROJECT_ID}.iam.gserviceaccount.com}"

# nginx + 정적 파일이라 가볍다.
MEMORY="${MEMORY:-256Mi}"
CPU="${CPU:-1}"
TIMEOUT="${TIMEOUT:-60s}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"

# 브라우저가 직접 호출할 백엔드 주소. 배포된 서비스에서 자동으로 찾는다.
VISION_BASE_URL="${VISION_BASE_URL:-$($GCLOUD run services describe vision-processor \
  --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)' 2>/dev/null | tr -d '[:space:]')}"
MATCHING_BASE_URL="${MATCHING_BASE_URL:-$($GCLOUD run services describe matching-processor \
  --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)' 2>/dev/null | tr -d '[:space:]')}"

# 카카오 지도 JavaScript 키. 없으면 지도 없이 주소/좌표만 표시된다(선택 기능).
KAKAO_JS_KEY="${KAKAO_JS_KEY:-}"

ENV_VARS="${ENV_VARS:-VISION_BASE_URL=${VISION_BASE_URL},MATCHING_BASE_URL=${MATCHING_BASE_URL},KAKAO_JS_KEY=${KAKAO_JS_KEY}}"
