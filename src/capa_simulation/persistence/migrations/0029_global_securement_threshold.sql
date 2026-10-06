-- Purpose: 시나리오와 독립된 공용 확보율 판정 기준(기본 확보·경고 기준과 월별 예외)을 저장한다.

-- 값은 비율이다(110% 기준을 반 칸 낮춘 109.5% 는 1.095). 헤더 한 행이 기본값을 갖고, 월별 표는
-- 그 달에만 다른 기준을 둔다. 월별 칸이 NULL 이면 그 달 그 항목은 기본값을 따른다.
CREATE TABLE IF NOT EXISTS app_meta.global_securement_threshold (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    version INTEGER NOT NULL CHECK (version > 0),
    source VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    "기본 확보 기준" DOUBLE NOT NULL CHECK ("기본 확보 기준" > 0),
    "기본 경고 기준" DOUBLE NOT NULL CHECK ("기본 경고 기준" > 0)
);

-- 두 칸이 다 비면 기본값과 같으므로 행을 두지 않는다.
CREATE TABLE IF NOT EXISTS app_meta.global_securement_threshold_month (
    profile_id INTEGER NOT NULL CHECK (profile_id = 1),
    "생산계획년월" INTEGER NOT NULL CHECK ("생산계획년월" % 100 BETWEEN 1 AND 12),
    "확보 기준" DOUBLE CHECK ("확보 기준" IS NULL OR "확보 기준" > 0),
    "경고 기준" DOUBLE CHECK ("경고 기준" IS NULL OR "경고 기준" > 0),
    CHECK ("확보 기준" IS NOT NULL OR "경고 기준" IS NOT NULL),
    PRIMARY KEY (profile_id, "생산계획년월")
);
