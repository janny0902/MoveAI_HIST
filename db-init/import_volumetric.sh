#!/bin/bash
# CSV 체적(물품) → PostgreSQL volumetric_cargo 만 적재
# 기사/트럭 정보는 이관하지 않음
set -euo pipefail

DB_HOST="${DB_HOST:-}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-moveaidb}"
DB_USER="${POSTGRES_USER:-moveaiuser}"
export PGPASSWORD="${POSTGRES_PASSWORD:-moveaipass}"
DATA_DIR="${VOLUMETRIC_DATA_DIR:-/data/volumetric}"

PSQL_OPTS=(-v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME")
if [ -n "$DB_HOST" ]; then
  PSQL_OPTS+=(-h "$DB_HOST" -p "$DB_PORT")
fi

echo "[import] target db=${DB_NAME} host=${DB_HOST:-socket} data_dir=${DATA_DIR}"

if [ -n "$DB_HOST" ]; then
  for i in $(seq 1 60); do
    if pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

psql "${PSQL_OPTS[@]}" <<'SQL'
CREATE TABLE IF NOT EXISTS volumetric_cargo (
    id BIGSERIAL PRIMARY KEY,
    cargo_id VARCHAR(64) NOT NULL,
    cargo_type VARCHAR(16),
    width_mm DOUBLE PRECISION NOT NULL,
    length_mm DOUBLE PRECISION NOT NULL,
    height_mm DOUBLE PRECISION NOT NULL,
    volume_cm3 DOUBLE PRECISION NOT NULL,
    volume_m3 DOUBLE PRECISION NOT NULL,
    depot_code VARCHAR(32),
    scanned_at TIMESTAMP,
    source_file VARCHAR(64) NOT NULL DEFAULT 'origin',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_volumetric_cargo_id_source UNIQUE (cargo_id, source_file)
);
CREATE INDEX IF NOT EXISTS idx_volumetric_cargo_type ON volumetric_cargo (cargo_type);
CREATE INDEX IF NOT EXISTS idx_volumetric_cargo_volume ON volumetric_cargo (volume_m3);

CREATE TABLE IF NOT EXISTS volumetric_cargo_staging (
    cargo_id TEXT,
    cargo_type TEXT,
    width_mm DOUBLE PRECISION,
    length_mm DOUBLE PRECISION,
    height_mm DOUBLE PRECISION,
    depot_code TEXT,
    scanned_at TEXT
);
SQL

import_one() {
  local csv_path="$1"
  local source_tag="$2"
  local normalized="/tmp/volumetric_${source_tag}.csv"

  if [ ! -f "$csv_path" ]; then
    echo "[import] skip missing: $csv_path"
    return 0
  fi

  echo "[import] normalize+load: $csv_path -> source=$source_tag"

  awk -F',' 'BEGIN{OFS=","} {
    gsub(/\r$/,"");
    if (NF >= 7 && $6 !~ /^[0-9]+\.[0-9]+$/) {
      print $1,$2,$3,$4,$5,$6,$7
    } else if (NF >= 5) {
      print $1,$2,$3,$4,$5,"",""
    }
  }' "$csv_path" > "$normalized"

  lines=$(wc -l < "$normalized" | tr -d ' ')
  echo "[import] normalized rows: $lines"

  psql "${PSQL_OPTS[@]}" <<SQL
TRUNCATE volumetric_cargo_staging;
\copy volumetric_cargo_staging (cargo_id, cargo_type, width_mm, length_mm, height_mm, depot_code, scanned_at) FROM '$normalized' WITH (FORMAT csv)
INSERT INTO volumetric_cargo (
    cargo_id, cargo_type, width_mm, length_mm, height_mm,
    volume_cm3, volume_m3, depot_code, scanned_at, source_file
)
SELECT
    cargo_id,
    cargo_type,
    width_mm,
    length_mm,
    height_mm,
    (width_mm * length_mm * height_mm) / 1000.0,
    (width_mm * length_mm * height_mm) / 1000000000.0,
    NULLIF(depot_code, ''),
    CASE
      WHEN scanned_at ~ '^[0-9]{4}-' THEN scanned_at::timestamp
      ELSE NULL
    END,
    '$source_tag'
FROM volumetric_cargo_staging
WHERE cargo_id IS NOT NULL
  AND width_mm IS NOT NULL
  AND length_mm IS NOT NULL
  AND height_mm IS NOT NULL
ON CONFLICT (cargo_id, source_file) DO NOTHING;
TRUNCATE volumetric_cargo_staging;
SQL

  rm -f "$normalized"
  echo "[import] done: $source_tag"
}

shopt -s nullglob
csv_files=("$DATA_DIR"/*.csv)
if [ ${#csv_files[@]} -eq 0 ]; then
  echo "[import] ERROR: no csv in $DATA_DIR"
  ls -la "$DATA_DIR" || true
  exit 1
fi

for csv_path in "${csv_files[@]}"; do
  base="$(basename "$csv_path")"
  case "$base" in
    origin*) source_tag="origin" ;;
    ai*) source_tag="ai_train" ;;
    *) source_tag="${base%.csv}" ;;
  esac
  import_one "$csv_path" "$source_tag"
done

psql "${PSQL_OPTS[@]}" -c \
  "SELECT source_file, COUNT(*) AS cnt, ROUND(SUM(volume_m3)::numeric, 2) AS total_m3 FROM volumetric_cargo GROUP BY source_file ORDER BY source_file;"

echo "[import] volumetric_cargo (products only) finished."

if [ -f /build_volumetric_groups.sh ]; then
  bash /build_volumetric_groups.sh
elif [ -f "$(dirname "$0")/build_volumetric_groups.sh" ]; then
  bash "$(dirname "$0")/build_volumetric_groups.sh"
fi
