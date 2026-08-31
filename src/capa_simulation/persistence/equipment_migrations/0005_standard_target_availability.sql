CREATE TABLE IF NOT EXISTS equipment_ops.standard_target_weekly_availability (
    process_name VARCHAR NOT NULL,
    weeknum VARCHAR NOT NULL,
    available_count DOUBLE NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (process_name, weeknum)
);
