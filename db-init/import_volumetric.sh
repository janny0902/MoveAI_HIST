#!/bin/sh
set -eu
# pipefail is bash-only; keep POSIX for alpine ash
set -o pipefail 2>/dev/null || true

echo "[db-import] waiting for postgres..."
until pg_isready -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE" >/dev/null 2>&1; do
  sleep 1
done

CSV_DIR="/data/volumetric"
if [ ! -d "$CSV_DIR" ]; then
  echo "[db-import] Volumetric data dir missing ??skip CSV import"
  exit 0
fi

# Prefer common filenames; skip quietly if absent
CSV=""
for candidate in \
  "$CSV_DIR/origin 泥댁쟻.csv" \
  "$CSV_DIR/origin.csv" \
  "$CSV_DIR/volumetric.csv"
do
  if [ -f "$candidate" ]; then
    CSV="$candidate"
    break
  fi
done

if [ -z "$CSV" ]; then
  echo "[db-import] no volumetric CSV found ??schema only (OK for bootstrap)"
  exit 0
fi

echo "[db-import] found CSV: $CSV"
if [ -f /scripts/build_volumetric_groups.sh ]; then
  sh /scripts/build_volumetric_groups.sh "$CSV" || {
    echo "[db-import] group build failed (non-fatal for bootstrap)"
    exit 0
  }
fi

echo "[db-import] done"
