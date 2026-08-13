#!/usr/bin/env bash
# 선택: CSV import 대신 db-dumps/moveaidb.dump 로 빠른 복원
# 사용: 스택 기동 후  (또는 db만 healthy 일 때)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DUMP="${1:-$ROOT/db-dumps/moveaidb.dump}"

if [[ ! -f "$DUMP" ]]; then
  echo "dump 없음: $DUMP"
  exit 1
fi

docker cp "$DUMP" mvp-moveai-db:/tmp/moveaidb.dump
docker exec mvp-moveai-db psql -U moveaiuser -d moveaidb -v ON_ERROR_STOP=1 \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO moveaiuser; GRANT ALL ON SCHEMA public TO public;"
docker exec mvp-moveai-db pg_restore -U moveaiuser -d moveaidb --no-owner --role=moveaiuser /tmp/moveaidb.dump
echo "[restore] OK — volumetric/OD/trucks 등 MoveAI 스냅샷 반영"
docker exec mvp-moveai-db psql -U moveaiuser -d moveaidb -c \
  "SELECT 'volumetric_cargo' t, COUNT(*) c FROM volumetric_cargo
   UNION ALL SELECT 'trucks', COUNT(*) FROM trucks
   UNION ALL SELECT 'cargo_requests', COUNT(*) FROM cargo_requests;"
