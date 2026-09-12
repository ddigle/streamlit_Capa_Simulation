-- Purpose: 시나리오와 독립된 공용 비교 대상(GAP 기준 시나리오·리비전) 프로필을 저장한다.

CREATE TABLE IF NOT EXISTS app_meta.global_comparison_scenario (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    scenario_id VARCHAR,
    revision_id VARCHAR,
    version INTEGER NOT NULL CHECK (version > 0),
    source VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    CHECK (revision_id IS NULL OR scenario_id IS NOT NULL)
);
