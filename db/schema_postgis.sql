-- PostgreSQL + PostGIS production schema for Smart Tourist Safety Monitoring System
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('tourist', 'authority', 'admin')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tourist_profiles (
    tourist_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    full_name TEXT NOT NULL,
    nationality TEXT NOT NULL,
    passport_or_id_number TEXT NOT NULL,
    emergency_contact_name TEXT NOT NULL,
    emergency_contact_phone TEXT NOT NULL,
    tracking_consent BOOLEAN NOT NULL DEFAULT FALSE,
    did TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Off-chain personal credential storage (never stored on the permissioned ledger)
CREATE TABLE IF NOT EXISTS credentials_offchain (
    credential_id TEXT PRIMARY KEY,
    tourist_id TEXT NOT NULL REFERENCES tourist_profiles(tourist_id) ON DELETE CASCADE,
    did TEXT NOT NULL,
    issuer_did TEXT NOT NULL,
    credential_json TEXT NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

-- Ledger anchor metadata mirror (mirrors on-chain DID, SHA-256 hash, issuer, revocation)
CREATE TABLE IF NOT EXISTS ledger_anchors (
    credential_id TEXT PRIMARY KEY,
    did TEXT NOT NULL,
    credential_hash TEXT NOT NULL,
    issuer_did TEXT NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at TIMESTAMPTZ,
    revocation_reason TEXT,
    block_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS zones (
    zone_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('safe', 'caution', 'restricted')),
    center_lat DOUBLE PRECISION,
    center_lon DOUBLE PRECISION,
    radius_m DOUBLE PRECISION,
    buffer_m DOUBLE PRECISION NOT NULL DEFAULT 25.0,
    polygon_json TEXT,
    geom GEOGRAPHY(GEOMETRY, 4326),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_zones_geom ON zones USING GIST (geom);

CREATE TABLE IF NOT EXISTS gps_observations (
    id BIGSERIAL PRIMARY KEY,
    tourist_id TEXT NOT NULL REFERENCES tourist_profiles(tourist_id) ON DELETE CASCADE,
    observed_at TIMESTAMPTZ NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    accuracy_m DOUBLE PRECISION NOT NULL DEFAULT 5.0,
    sos_active BOOLEAN NOT NULL DEFAULT FALSE,
    location GEOGRAPHY(POINT, 4326)
);

CREATE INDEX IF NOT EXISTS idx_gps_tourist_time ON gps_observations (tourist_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_gps_location ON gps_observations USING GIST (location);

CREATE TABLE IF NOT EXISTS zone_transitions (
    id BIGSERIAL PRIMARY KEY,
    tourist_id TEXT NOT NULL,
    zone_id TEXT NOT NULL REFERENCES zones(zone_id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    previous_state TEXT NOT NULL,
    new_state TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS incidents (
    alert_id TEXT PRIMARY KEY,
    tourist_id TEXT NOT NULL REFERENCES tourist_profiles(tourist_id) ON DELETE CASCADE,
    event_timestamp TIMESTAMPTZ NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('info', 'warning', 'high', 'critical')),
    reason TEXT NOT NULL,
    zone_id TEXT,
    zone_category TEXT,
    anomaly_score DOUBLE PRECISION,
    status TEXT NOT NULL CHECK (status IN ('pending', 'acknowledged', 'in_progress', 'resolved')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    in_progress_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents (status, created_at DESC);
