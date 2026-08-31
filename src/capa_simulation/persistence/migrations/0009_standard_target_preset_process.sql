CREATE TABLE IF NOT EXISTS app_meta.scenario_preset_standard_target_process (
    revision_id VARCHAR NOT NULL,
    process_name VARCHAR NOT NULL,
    display_order INTEGER NOT NULL CHECK (display_order > 0),
    PRIMARY KEY (revision_id, process_name),
    UNIQUE (revision_id, display_order)
);
