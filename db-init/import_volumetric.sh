#!/bin/sh
# Always exit 0 so compose stack can start without CSV.
set -eu

echo "[db-import] waiting for postgres..."
i=0
while [ "$i" -lt 60 ]; do
  if pg_isready -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE" >/dev/null 2>&1; then
    break
  fi
  i=$((i + 1))
  sleep 1
done

if ! pg_isready -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE" >/dev/null 2>&1; then
  echo "[db-import] postgres not ready — skip (non-fatal)"
  exit 0
fi

CSV_DIR="/data/volumetric"
if [ ! -d "$CSV_DIR" ]; then
  echo "[db-import] volumetric dir missing — skip"
  exit 0
fi

CSV=""
for candidate in \
  "$CSV_DIR/origin.csv" \
  "$CSV_DIR/volumetric.csv"
do
  if [ -f "$candidate" ]; then
    CSV="$candidate"
    break
  fi
done

# Korean filename (origin 체적.csv) — match any *체적*.csv / *.csv
if [ -z "$CSV" ]; then
  for candidate in "$CSV_DIR"/*.csv; do
    if [ -f "$candidate" ]; then
      CSV="$candidate"
      break
    fi
  done
fi

if [ -z "$CSV" ]; then
  echo "[db-import] no CSV — schema only OK"
  exit 0
fi

echo "[db-import] found CSV: $CSV"
if [ -f /scripts/build_volumetric_groups.sh ]; then
  sh /scripts/build_volumetric_groups.sh "$CSV" || echo "[db-import] group build skipped"
fi

echo "[db-import] done"
exit 0
