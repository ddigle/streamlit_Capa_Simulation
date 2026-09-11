-- Purpose: 적재 시점 이전의 과거 구간을 시나리오와 독립된 공용 프로필로 저장한다.

CREATE TABLE IF NOT EXISTS app_meta.global_past_data (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    version INTEGER NOT NULL CHECK (version > 0),
    source VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS app_meta.global_past_month (
    profile_id INTEGER NOT NULL CHECK (profile_id = 1),
    "생산계획년월" INTEGER NOT NULL CHECK ("생산계획년월" % 100 BETWEEN 1 AND 12),
    "Density" DOUBLE NOT NULL,
    "Wafer Total" DOUBLE NOT NULL,
    PRIMARY KEY (profile_id, "생산계획년월")
);

CREATE TABLE IF NOT EXISTS app_meta.global_past_plan_detail (
    profile_id INTEGER NOT NULL CHECK (profile_id = 1),
    "생산계획년월" INTEGER NOT NULL CHECK ("생산계획년월" % 100 BETWEEN 1 AND 12),
    "제품정보" VARCHAR NOT NULL CHECK ("제품정보" <> ''),
    "Stack" VARCHAR NOT NULL,
    "Customer" VARCHAR NOT NULL,
    "생산수량" DOUBLE NOT NULL,
    PRIMARY KEY (profile_id, "생산계획년월", "제품정보", "Stack", "Customer")
);

CREATE TABLE IF NOT EXISTS app_meta.global_past_securement (
    profile_id INTEGER NOT NULL CHECK (profile_id = 1),
    "생산계획년월" INTEGER NOT NULL CHECK ("생산계획년월" % 100 BETWEEN 1 AND 12),
    "공정" VARCHAR NOT NULL CHECK ("공정" <> ''),
    "확보율" DOUBLE NOT NULL,
    PRIMARY KEY (profile_id, "생산계획년월", "공정")
);
