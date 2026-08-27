CREATE SCHEMA IF NOT EXISTS equipment_meta;
CREATE SCHEMA IF NOT EXISTS equipment_ops;

CREATE TABLE IF NOT EXISTS equipment_meta.schema_migration (
    version INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    checksum VARCHAR NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS equipment_ops.revision (
    revision_id VARCHAR PRIMARY KEY,
    revision_no INTEGER NOT NULL UNIQUE CHECK (revision_no > 0),
    note VARCHAR,
    baseline_hash VARCHAR NOT NULL,
    schedule_hash VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS equipment_ops.baseline_snapshot (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL CHECK (source_row_no > 0),
    process_name VARCHAR NOT NULL,
    classification VARCHAR NOT NULL,
    base_count DOUBLE NOT NULL CHECK (base_count >= 0),
    note VARCHAR,
    PRIMARY KEY (revision_id, source_row_no),
    UNIQUE (revision_id, process_name, classification),
    FOREIGN KEY (revision_id) REFERENCES equipment_ops.revision (revision_id)
);

CREATE TABLE IF NOT EXISTS equipment_ops.schedule_snapshot (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL CHECK (source_row_no > 0),
    equipment_id VARCHAR NOT NULL,
    process_name VARCHAR NOT NULL,
    classification VARCHAR NOT NULL,
    arrival_date DATE NOT NULL,
    setup_start_date DATE,
    setup_complete_date DATE,
    note VARCHAR,
    PRIMARY KEY (revision_id, source_row_no),
    UNIQUE (revision_id, equipment_id),
    FOREIGN KEY (revision_id) REFERENCES equipment_ops.revision (revision_id)
);
