#!/usr/bin/env bash
# matching-processor 인프라 설정 단일 출처. bootstrap.sh / deploy.sh가 source한다.

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

# 로컬 비밀값(API 키 등). git에 올리지 않는다 — .gitignore 참조.
_secrets="$(dirname "${BASH_SOURCE[0]}")/.env.local"
[[ -f "$_secrets" ]] && source "$_secrets"

PROJECT_ID="${GCP_PROJECT:-moveai-504903}"
REGION="${GCP_LOCATION:-asia-northeast3}"
SERVICE="${SERVICE:-matching-processor}"

# 아래 CORS 오리진 계산과 push SA가 모두 쓰므로 여기서 먼저 구한다.
PROJECT_NUMBER="$($GCLOUD projects describe "$PROJECT_ID" --format='value(projectNumber)' | tr -d '[:space:]')"

# 1.3/5.9 경계 강제: 이 SA에는 storage 권한을 주지 않는다. Matching이 원본 이미지나
# depth map을 읽으려 해도 IAM에서 막힌다.
SERVICE_ACCOUNT="${MATCHING_SA_EMAIL:-matching-sa@${PROJECT_ID}.iam.gserviceaccount.com}"

TOPIC="${SPACE_GEOMETRY_TOPIC:-space-geometry-ready}"
SUBSCRIPTION="${SUBSCRIPTION:-space-geometry-ready-matching}"
CARGOS_COLLECTION="${FIRESTORE_CARGOS_COLLECTION:-pending_cargos}"

# 운송장 대량 적재용 버킷. 사진 버킷과 분리한다 — matching-sa는 사진 버킷에 접근 권한이
# 없어야 하고(1.3/5.9), 이 버킷에만 읽기 권한을 버킷 단위로 준다.
CARGO_INGEST_BUCKET="${CARGO_INGEST_BUCKET:-cargo-ingest-${PROJECT_ID}}"
CARGO_TRIGGER="${CARGO_TRIGGER:-cargo-ingest-trigger}"
# 만료된 운송장을 Firestore TTL로 자동 정리한다. 안 지우면 색인만 비대해진다.
CARGO_TTL_FIELD="${CARGO_TTL_FIELD:-deadline_at}"

# ---------------------------------------------------------------------------
# Cloud Run 리소스 설정 — 아래 값을 임의로 낮추지 말 것
# ---------------------------------------------------------------------------
# 원래 1Gi/1CPU/120s였다. "CP-SAT는 후보 20건 규모라 가볍다"는 전제였는데, 화면이
# 차량 기준 매칭에서 후보를 1만 건까지 올리면서(frontend-admin App.jsx 기본값 10000)
# 그 전제가 깨졌다. 1만 건이면 Firestore 조회 + CP-SAT에 20초가 걸린다 — 120초
# 타임아웃 안에는 들어오지만 1CPU로는 솔버가 병렬 탐색을 못 해 훨씬 느려진다.
#
# 아래는 실제 운영 중인 리비전의 값이다. 이 파일이 1Gi/1CPU로 남아 있던 동안
# deploy.sh를 돌렸다면 서비스가 8배 축소됐을 것이다.
MEMORY="${MEMORY:-8Gi}"
CPU="${CPU:-8}"
# 후보 1만 건 매칭이 20초대다. 여유를 크게 둔다.
TIMEOUT="${TIMEOUT:-900s}"
# Vision과 달리 요청당 메모리가 작아 한 인스턴스가 여러 요청을 받아도 된다(기본값 유지).
CONCURRENCY="${CONCURRENCY:-80}"
# 최초 클릭의 콜드 스타트를 없앤다. 시연이 끝나면 0으로 되돌린다 —
# MIN_INSTANCES=0 ./infra/deploy.sh (8Gi/8CPU를 상시 켜두는 비용이다).
#
# 이 값은 --min-instances 없이 gcloud run deploy를 치면 조용히 0으로 돌아간다.
# 실제로 그렇게 어긋나 있었다(2026-08-11에 1로 되돌림).
MIN_INSTANCES="${MIN_INSTANCES:-1}"

# Cloud Run에 설정할 환경변수 전체 집합(deploy.sh가 --set-env-vars로 넘긴다).
# KAKAO_REST_API_KEY가 비면 M4가 직선거리 추정으로 degrade하고 결과에 route_source로 남는다.
# 프론트엔드가 브라우저에서 결과를 직접 조회하므로 그 오리진을 CORS로 허용한다.
# Cloud Run 서비스에는 접속 가능한 URL이 두 개(hash 형식, project-number 형식) 있고
# 둘 다 동작한다. 하나만 허용하면 다른 주소로 들어왔을 때 preflight에서 막힌다.
FRONTEND_URL="${FRONTEND_URL:-$($GCLOUD run services describe frontend \
  --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)' 2>/dev/null | tr -d '[:space:]')}"
FRONTEND_URL_ALT="https://frontend-${PROJECT_NUMBER}.${REGION}.run.app"

if [[ -n "$FRONTEND_URL" && "$FRONTEND_URL" != "$FRONTEND_URL_ALT" ]]; then
  _default_origins="${FRONTEND_URL};${FRONTEND_URL_ALT}"
else
  _default_origins="${FRONTEND_URL:-*}"
fi
CORS_ALLOW_ORIGINS="${CORS_ALLOW_ORIGINS:-$_default_origins}"

KAKAO_REST_API_KEY="${KAKAO_REST_API_KEY:-}"

# 운송장 유효시간(생성일시 + N시간 = 상차 마감). 운영 기본값은 72시간이다.
#
# 시연용으로 720시간(30일)을 쓴다. 화주사가 준 샘플 파일의 생성일시가 며칠 지난
# 값이라, 72시간이면 전 건이 만료로 걸러져 후보가 하나도 남지 않는다. 실데이터를
# 실시간으로 받기 시작하면 72로 되돌려야 한다.
WAYBILL_VALID_HOURS="${WAYBILL_VALID_HOURS:-720}"

ENV_VARS="${ENV_VARS:-CORRIDOR_RADIUS_KM=30,KAKAO_REST_API_KEY=${KAKAO_REST_API_KEY},MAX_ROUTE_CANDIDATES=200,MAX_ROUTE_STOPS=12,CARGO_INGEST_BUCKET=${CARGO_INGEST_BUCKET},CORS_ALLOW_ORIGINS=${CORS_ALLOW_ORIGINS},WAYBILL_VALID_HOURS=${WAYBILL_VALID_HOURS}}"

# Pub/Sub push 인증에 쓰는 SA. push 대상 Cloud Run을 호출할 권한이 필요하다.
PUSH_SA="${PUSH_SA:-${PROJECT_NUMBER}-compute@developer.gserviceaccount.com}"
