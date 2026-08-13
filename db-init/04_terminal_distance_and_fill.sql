-- 터미널 간 거리 행렬 (경유 증분 = 합산 - 직행)
CREATE TABLE IF NOT EXISTS terminal_distance_matrix (
    id BIGSERIAL PRIMARY KEY,
    origin_code VARCHAR(32) NOT NULL,
    dest_code VARCHAR(32) NOT NULL,
    distance_km DOUBLE PRECISION,
    duration_min DOUBLE PRECISION,
    source VARCHAR(32),
    updated_at TIMESTAMP,
    CONSTRAINT uk_terminal_distance_od UNIQUE (origin_code, dest_code)
);

CREATE INDEX IF NOT EXISTS idx_tdm_origin ON terminal_distance_matrix (origin_code);
CREATE INDEX IF NOT EXISTS idx_tdm_dest ON terminal_distance_matrix (dest_code);

-- cargo_od_groups.fill_by_vehicle_json 은 JPA ddl-auto=update 로 추가
