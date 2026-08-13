-- 11톤(50m³) 기준 적재율 그룹 테이블
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
