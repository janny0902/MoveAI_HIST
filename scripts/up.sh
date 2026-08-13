#!/usr/bin/env bash
# 새 VM / 로컬 동일: MoveAI 풀스택 기동 (포트 30100)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "[up] .env 생성됨 — VITE_KAKAO_JS_KEY / KAKAO_REST_KEY / GOOGLE_ADC_PATH 를 채우세요"
fi

mkdir -p data/cargo-photos pgdata secrets
if [[ ! -f secrets/application_default_credentials.json ]]; then
  echo '{}' > secrets/application_default_credentials.json
fi

export COMPOSE_BAKE="${COMPOSE_BAKE:-false}"
docker compose up -d --build "$@"
echo "[up] http://localhost:30100  (기사)  /admin  (관리자)"
echo "[up] health: curl -sS http://localhost:30100/api/health"
