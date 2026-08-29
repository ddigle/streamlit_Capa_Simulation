CREATE TABLE IF NOT EXISTS app_meta.official_release (
    official_release_id VARCHAR PRIMARY KEY,
    release_no BIGINT NOT NULL UNIQUE CHECK (release_no > 0),
    scenario_id VARCHAR NOT NULL,
    revision_id VARCHAR NOT NULL,
    release_name VARCHAR NOT NULL,
    note VARCHAR,
    published_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE INDEX IF NOT EXISTS official_release_revision_idx
    ON app_meta.official_release (revision_id);
