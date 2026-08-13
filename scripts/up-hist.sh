#!/bin/sh
# HIST 스택만 깨끗이 재기동 (30100 mvp 스택은 건드리지 않음)
set -eu
cd "$(dirname "$0")/.."

echo "[up-hist] stop previous hist stack..."
docker compose -p moveai-hist down --remove-orphans 2>/dev/null || true

# 혹시 mvp 프로젝트로 hist 컨테이너를 올린 잔여물만 제거
for c in \
  hist-moveai-nginx hist-moveai-frontend hist-moveai-frontend-admin \
  hist-moveai-backend-spring hist-moveai-backend-ai \
  hist-moveai-db hist-moveai-db-import
do
  docker rm -f "$c" 2>/dev/null || true
done

echo "[up-hist] build & start..."
docker compose up -d --build

echo "[up-hist] status:"
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'hist-moveai|NAMES' || true

echo "[up-hist] health:"
sleep 5
curl -sS http://localhost:20100/api/health || true
echo
curl -sS http://localhost:20100/ai/health || true
echo
curl -sS -o /dev/null -w "ui:%{http_code}\n" http://localhost:20100/ || true
curl -sS -o /dev/null -w "admin:%{http_code}\n" http://localhost:20100/admin/ || true
