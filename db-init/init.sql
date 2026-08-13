-- 체적(물품) 데이터 전용 스키마
-- 기사/트럭 정보는 이관 대상이 아님

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

-- 앱 배차용 최소 스키마 (시드/기사정보 INSERT 없음 — 런타임에만 사용)
CREATE TABLE IF NOT EXISTS trucks (
    id SERIAL PRIMARY KEY,
    driver_name VARCHAR(50),
    truck_number VARCHAR(20),
    capacity_tons FLOAT DEFAULT 11.0,
    current_location_lat DOUBLE PRECISION,
    current_location_lng DOUBLE PRECISION,
    status VARCHAR(20) DEFAULT 'IDLE',
    remaining_volume_percent FLOAT DEFAULT 100.0
);

CREATE TABLE IF NOT EXISTS load_history (
    id SERIAL PRIMARY KEY,
    truck_id INTEGER REFERENCES trucks(id),
    load_image_url TEXT,
    remaining_volume_percent FLOAT,
    occupied_volume_percent FLOAT,
    esg_reduction_kg FLOAT DEFAULT 0,
    income INTEGER DEFAULT 0,
    expense INTEGER DEFAULT 0,
    net_profit INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cargo_requests (
    id SERIAL PRIMARY KEY,
    origin VARCHAR(100),
    destination VARCHAR(100),
    box_count INTEGER,
    total_volume_m3 FLOAT,
    total_weight_kg FLOAT,
    proposed_fee INTEGER,
    status VARCHAR(20) DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 11톤 기준 적재율 그룹
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
