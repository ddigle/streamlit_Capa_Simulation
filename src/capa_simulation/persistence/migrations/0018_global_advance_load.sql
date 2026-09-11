-- Purpose: 시나리오와 독립된 공용 선행 투입 물량 프로필(월별 억Gb 가감분)을 저장한다.

CREATE TABLE IF NOT EXISTS app_meta.global_advance_load (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    version INTEGER NOT NULL CHECK (version > 0),
    source VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS app_meta.global_advance_load_month (
    profile_id INTEGER NOT NULL CHECK (profile_id = 1),
    "생산계획년월" INTEGER NOT NULL CHECK ("생산계획년월" % 100 BETWEEN 1 AND 12),
    "선행 물량" DOUBLE NOT NULL,
    PRIMARY KEY (profile_id, "생산계획년월")
);
