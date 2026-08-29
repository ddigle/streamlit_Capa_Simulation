ALTER TABLE equipment_ops.revision ADD COLUMN equipment_hash VARCHAR;
ALTER TABLE equipment_ops.revision ADD COLUMN downtime_hash VARCHAR;

CREATE TABLE equipment_ops.equipment_snapshot (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL CHECK (source_row_no > 0),
    equipment_id VARCHAR NOT NULL,
    process_name VARCHAR NOT NULL,
    classification VARCHAR NOT NULL,
    building VARCHAR,
    floor_name VARCHAR,
    x_coordinate DOUBLE,
    y_coordinate DOUBLE,
    width_value DOUBLE,
    infrastructure_complete_date DATE,
    arrival_date DATE,
    hookup_complete_date DATE,
    hardware_setup_complete_date DATE,
    qual_complete_date DATE,
    tttm_complete_date DATE,
    production_transition_date DATE,
    note VARCHAR,
    PRIMARY KEY (revision_id, source_row_no),
    UNIQUE (revision_id, equipment_id),
    FOREIGN KEY (revision_id) REFERENCES equipment_ops.revision (revision_id)
);

CREATE TABLE equipment_ops.downtime_snapshot (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL CHECK (source_row_no > 0),
    downtime_id VARCHAR NOT NULL,
    equipment_id VARCHAR NOT NULL,
    downtime_type VARCHAR NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    detail VARCHAR,
    note VARCHAR,
    PRIMARY KEY (revision_id, source_row_no),
    UNIQUE (revision_id, downtime_id),
    FOREIGN KEY (revision_id) REFERENCES equipment_ops.revision (revision_id)
);
