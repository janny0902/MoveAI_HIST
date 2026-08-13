-- moveAI initial schema (JPA ddl-auto=update may extend columns at runtime)

CREATE TABLE IF NOT EXISTS trucks (
    id                          BIGSERIAL PRIMARY KEY,
    driver_name                 VARCHAR(100),
    phone                       VARCHAR(40),
    truck_number                VARCHAR(40),
    capacity_tons               DOUBLE PRECISION DEFAULT 11,
    capacity_m3                 DOUBLE PRECISION DEFAULT 50,
    vehicle_type                VARCHAR(60),
    profile_completed           BOOLEAN DEFAULT FALSE,
    origin_code                 VARCHAR(20),
    origin_name                 VARCHAR(100),
    destination_code            VARCHAR(20),
    destination_name            VARCHAR(100),
    current_location_lat        DOUBLE PRECISION,
    current_location_lng        DOUBLE PRECISION,
    status                      VARCHAR(40) DEFAULT 'IDLE',
    remaining_volume_percent    DOUBLE PRECISION DEFAULT 100,
    expected_added_fill_percent DOUBLE PRECISION,
    baseline_occupied_percent   DOUBLE PRECISION,
    active_request_id           BIGINT,
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_trucks_phone_truck
    ON trucks (phone, truck_number);

CREATE TABLE IF NOT EXISTS cargo_requests (
    id                    BIGSERIAL PRIMARY KEY,
    origin                VARCHAR(100),
    destination           VARCHAR(100),
    via                   VARCHAR(200),
    origin_code           VARCHAR(20),
    destination_code      VARCHAR(20),
    via_codes             VARCHAR(200),
    box_count             INTEGER DEFAULT 0,
    total_volume_m3       DOUBLE PRECISION DEFAULT 0,
    total_weight_kg       DOUBLE PRECISION DEFAULT 0,
    proposed_fee          INTEGER DEFAULT 0,
    expected_fill_percent DOUBLE PRECISION DEFAULT 0,
    assigned_truck_id     BIGINT,
    status                VARCHAR(40) DEFAULT 'PENDING',
    briefing              TEXT,
    extra_distance_km     DOUBLE PRECISION,
    extra_fuel_cost       INTEGER,
    net_profit            INTEGER,
    esg_reduction_kg      DOUBLE PRECISION,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_cargo_requests_status ON cargo_requests (status);
CREATE INDEX IF NOT EXISTS ix_cargo_requests_dest ON cargo_requests (destination_code);

CREATE TABLE IF NOT EXISTS load_history (
    id                        BIGSERIAL PRIMARY KEY,
    truck_id                  BIGINT,
    cargo_request_id          BIGINT,
    load_image_url            VARCHAR(500),
    remaining_volume_percent  DOUBLE PRECISION,
    occupied_volume_percent   DOUBLE PRECISION,
    income                    INTEGER DEFAULT 0,
    expense                   INTEGER DEFAULT 0,
    net_profit                INTEGER DEFAULT 0,
    esg_reduction_kg          DOUBLE PRECISION DEFAULT 0,
    route_summary             VARCHAR(500),
    created_at                TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_load_history_truck ON load_history (truck_id);

CREATE TABLE IF NOT EXISTS volumetric_cargo (
    id           BIGSERIAL PRIMARY KEY,
    length_mm    DOUBLE PRECISION,
    width_mm     DOUBLE PRECISION,
    height_mm    DOUBLE PRECISION,
    volume_cm3   DOUBLE PRECISION,
    volume_m3    DOUBLE PRECISION,
    depot_code   VARCHAR(20),
    source_file  VARCHAR(200),
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS volumetric_group (
    id                 BIGSERIAL PRIMARY KEY,
    fill_percent       INTEGER NOT NULL,
    target_volume_m3   DOUBLE PRECISION,
    actual_volume_m3   DOUBLE PRECISION,
    box_count          INTEGER DEFAULT 0,
    truck_capacity_m3  DOUBLE PRECISION DEFAULT 50,
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS volumetric_group_item (
    id        BIGSERIAL PRIMARY KEY,
    group_id  BIGINT NOT NULL REFERENCES volumetric_group(id) ON DELETE CASCADE,
    cargo_id  BIGINT NOT NULL REFERENCES volumetric_cargo(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_vgi_group ON volumetric_group_item (group_id);
