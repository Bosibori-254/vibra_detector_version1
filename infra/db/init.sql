-- PipeGuard TimescaleDB schema. Applied once on first container start.
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS feature_samples (
    id BIGSERIAL,
    ts TIMESTAMPTZ NOT NULL,
    site TEXT NOT NULL,
    segment TEXT NOT NULL,
    node_id TEXT NOT NULL,
    sequence BIGINT NOT NULL,
    message_id TEXT NOT NULL UNIQUE,
    late BOOLEAN NOT NULL DEFAULT FALSE,
    drift_corrected BOOLEAN NOT NULL DEFAULT FALSE,
    operating_state JSONB NOT NULL,
    features JSONB NOT NULL,
    health JSONB NOT NULL,
    PRIMARY KEY (id, ts),
    CONSTRAINT uq_node_sequence UNIQUE (node_id, sequence)
);
SELECT create_hypertable('feature_samples', 'ts', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_feature_node_ts ON feature_samples (node_id, ts DESC);

CREATE TABLE IF NOT EXISTS baselines (
    id BIGSERIAL PRIMARY KEY,
    node_id TEXT NOT NULL,
    state_key TEXT NOT NULL,
    version INT NOT NULL DEFAULT 1,
    stats JSONB NOT NULL,
    sample_count INT NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    UNIQUE (node_id, state_key)
);

CREATE TABLE IF NOT EXISTS detections (
    id BIGSERIAL,
    ts TIMESTAMPTZ NOT NULL,
    node_id TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    severity TEXT NOT NULL,
    layer_scores JSONB NOT NULL,
    state_key TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (id, ts)
);
SELECT create_hypertable('detections', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS diagnoses (
    id BIGSERIAL,
    ts TIMESTAMPTZ NOT NULL,
    node_id TEXT NOT NULL,
    segment TEXT NOT NULL,
    cause TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    evidence JSONB NOT NULL,
    severity TEXT NOT NULL,
    all_scores JSONB NOT NULL,
    PRIMARY KEY (id, ts)
);
SELECT create_hypertable('diagnoses', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS alarms (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    segment TEXT NOT NULL,
    site TEXT NOT NULL,
    priority TEXT NOT NULL,
    state TEXT NOT NULL,
    cause TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    acked_by TEXT,
    acked_at TEXT,
    cleared_at TEXT,
    shelved_until TEXT,
    escalation_count INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS actions_audit (
    id TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    node_id TEXT NOT NULL,
    segment TEXT NOT NULL,
    cause TEXT NOT NULL,
    mode TEXT NOT NULL,
    action_type TEXT NOT NULL,
    target TEXT NOT NULL,
    before DOUBLE PRECISION,
    after DOUBLE PRECISION,
    result TEXT NOT NULL,
    reason TEXT NOT NULL,
    operator TEXT NOT NULL DEFAULT 'system',
    gate_results JSONB NOT NULL,
    rollback_of TEXT,
    PRIMARY KEY (id, ts)
);
SELECT create_hypertable('actions_audit', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    site TEXT NOT NULL,
    segment TEXT NOT NULL,
    cause TEXT NOT NULL,
    severity TEXT NOT NULL,
    payload JSONB NOT NULL
);

-- Retention policies (configurable; conservative defaults).
SELECT add_retention_policy('feature_samples', INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_retention_policy('actions_audit', INTERVAL '2 years', if_not_exists => TRUE);
SELECT add_retention_policy('detections', INTERVAL '1 year', if_not_exists => TRUE);
