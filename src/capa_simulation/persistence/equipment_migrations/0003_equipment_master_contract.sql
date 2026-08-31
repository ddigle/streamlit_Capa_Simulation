ALTER TABLE equipment_ops.revision
ADD COLUMN equipment_contract_version INTEGER DEFAULT 2;

UPDATE equipment_ops.revision
SET equipment_contract_version = 2
WHERE equipment_contract_version IS NULL;

CREATE TABLE equipment_ops.equipment_master_snapshot (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL CHECK (source_row_no > 0),
    equipment_id VARCHAR NOT NULL,
    process_large VARCHAR,
    process_small VARCHAR NOT NULL,
    line_type VARCHAR,
    utilization_type VARCHAR,
    business_unit VARCHAR,
    investment_basis VARCHAR,
    maker VARCHAR,
    model_name VARCHAR,
    classification_1 VARCHAR,
    classification_2 VARCHAR,
    classification_3 VARCHAR,
    building VARCHAR,
    floor_name VARCHAR,
    x_coordinate DOUBLE,
    y_coordinate DOUBLE,
    x_size DOUBLE,
    y_size DOUBLE,
    vibration_table_date DATE,
    logistics_date DATE,
    arrival_date DATE,
    qual_date DATE,
    removal_date DATE,
    relocation_date DATE,
    long_term_storage_flag VARCHAR NOT NULL,
    existing_equipment_flag VARCHAR NOT NULL,
    equipment_history VARCHAR,
    note VARCHAR,
    layout_display_flag VARCHAR NOT NULL,
    PRIMARY KEY (revision_id, source_row_no),
    UNIQUE (revision_id, equipment_id),
    FOREIGN KEY (revision_id) REFERENCES equipment_ops.revision (revision_id)
);

CREATE TABLE equipment_ops.downtime_schedule_snapshot (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL CHECK (source_row_no > 0),
    equipment_id VARCHAR NOT NULL,
    downtime_type VARCHAR NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    detail VARCHAR,
    note VARCHAR,
    PRIMARY KEY (revision_id, source_row_no),
    UNIQUE (revision_id, equipment_id, downtime_type, start_date),
    FOREIGN KEY (revision_id) REFERENCES equipment_ops.revision (revision_id)
);
