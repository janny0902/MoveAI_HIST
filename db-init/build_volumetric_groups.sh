#!/bin/bash
# 11톤 50m³ 기준 5/10/30/50/90% 체적 그룹 생성
# origin 물품을 겹치지 않게 채워 넣음
set -euo pipefail

DB_HOST="${DB_HOST:-}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-moveaidb}"
DB_USER="${POSTGRES_USER:-moveaiuser}"
export PGPASSWORD="${POSTGRES_PASSWORD:-moveaipass}"
CAPACITY="${TRUCK_CAPACITY_M3:-50}"

PSQL_OPTS=(-v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME")
if [ -n "$DB_HOST" ]; then
  PSQL_OPTS+=(-h "$DB_HOST" -p "$DB_PORT")
fi

echo "[groups] building fill groups for ${CAPACITY}m3 truck..."

psql "${PSQL_OPTS[@]}" <<SQL
CREATE TABLE IF NOT EXISTS volumetric_group (
    id SERIAL PRIMARY KEY,
    group_code VARCHAR(32) NOT NULL UNIQUE,
    fill_percent INTEGER NOT NULL,
    target_volume_m3 DOUBLE PRECISION NOT NULL,
    actual_volume_m3 DOUBLE PRECISION NOT NULL DEFAULT 0,
    actual_fill_percent DOUBLE PRECISION NOT NULL DEFAULT 0,
    box_count INTEGER NOT NULL DEFAULT 0,
    truck_capacity_m3 DOUBLE PRECISION NOT NULL DEFAULT 50.0,
    source_file VARCHAR(64) NOT NULL DEFAULT 'origin',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS volumetric_group_item (
    id BIGSERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES volumetric_group(id) ON DELETE CASCADE,
    volumetric_cargo_id BIGINT NOT NULL REFERENCES volumetric_cargo(id),
    cargo_id VARCHAR(64) NOT NULL,
    cargo_type VARCHAR(16),
    width_mm DOUBLE PRECISION,
    length_mm DOUBLE PRECISION,
    height_mm DOUBLE PRECISION,
    volume_cm3 DOUBLE PRECISION NOT NULL,
    volume_m3 DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vgi_group ON volumetric_group_item(group_id);
CREATE INDEX IF NOT EXISTS idx_vg_fill ON volumetric_group(fill_percent);

TRUNCATE volumetric_group_item RESTART IDENTITY;
TRUNCATE volumetric_group RESTART IDENTITY CASCADE;

DO \$\$
DECLARE
  cap CONSTANT DOUBLE PRECISION := ${CAPACITY};
  pct INTEGER;
  target DOUBLE PRECISION;
  gid INTEGER;
  acc DOUBLE PRECISION;
  cnt INTEGER;
  r RECORD;
  used_ids BIGINT[] := ARRAY[]::BIGINT[];
  targets INTEGER[] := ARRAY[5, 10, 30, 50, 90];
BEGIN
  FOREACH pct IN ARRAY targets LOOP
    target := round((cap * pct / 100.0)::numeric, 4);
    INSERT INTO volumetric_group (
      group_code, fill_percent, target_volume_m3, truck_capacity_m3, source_file
    ) VALUES (
      'FILL_' || lpad(pct::text, 2, '0'),
      pct,
      target,
      cap,
      'origin'
    ) RETURNING id INTO gid;

    acc := 0;
    cnt := 0;

    FOR r IN
      SELECT id, cargo_id, cargo_type, width_mm, length_mm, height_mm, volume_cm3, volume_m3
      FROM volumetric_cargo
      WHERE source_file = 'origin'
        AND volume_m3 > 0
        AND NOT (id = ANY(used_ids))
      ORDER BY id
    LOOP
      EXIT WHEN acc >= target;
      -- 목표를 크게 넘기지 않도록: 다음 박스를 넣어도 목표+0.2m3 이내이거나 아직 목표 미만
      IF acc > 0 AND acc + r.volume_m3 > target * 1.05 AND acc >= target * 0.98 THEN
        EXIT;
      END IF;

      INSERT INTO volumetric_group_item (
        group_id, volumetric_cargo_id, cargo_id, cargo_type,
        width_mm, length_mm, height_mm, volume_cm3, volume_m3
      ) VALUES (
        gid, r.id, r.cargo_id, r.cargo_type,
        r.width_mm, r.length_mm, r.height_mm, r.volume_cm3, r.volume_m3
      );

      used_ids := array_append(used_ids, r.id);
      acc := acc + r.volume_m3;
      cnt := cnt + 1;
    END LOOP;

    UPDATE volumetric_group
    SET actual_volume_m3 = round(acc::numeric, 4),
        actual_fill_percent = round(((acc / cap) * 100.0)::numeric, 2),
        box_count = cnt
    WHERE id = gid;
  END LOOP;
END
\$\$;

SELECT group_code, fill_percent, target_volume_m3, actual_volume_m3, actual_fill_percent, box_count
FROM volumetric_group
ORDER BY fill_percent;
SQL

echo "[groups] done."
