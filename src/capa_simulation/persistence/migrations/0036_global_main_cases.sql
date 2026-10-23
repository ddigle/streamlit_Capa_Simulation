-- Purpose: HOME 주요 Case(Case1·Case2)로 지정한 시나리오·리비전을 시나리오와 독립된 공용 프로필로 저장한다.

CREATE TABLE IF NOT EXISTS app_meta.global_main_cases (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    case1_scenario_id VARCHAR,
    case1_revision_id VARCHAR,
    case2_scenario_id VARCHAR,
    case2_revision_id VARCHAR,
    version INTEGER NOT NULL CHECK (version > 0),
    source VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    CHECK (case1_revision_id IS NULL OR case1_scenario_id IS NOT NULL),
    CHECK (case2_revision_id IS NULL OR case2_scenario_id IS NOT NULL)
);
