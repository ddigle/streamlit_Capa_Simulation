-- Purpose: 시나리오와 독립된 공용 실행 Capa 반영 프로필(년월·공정별 확보율 증감)을 저장한다.

-- 이 두 표에는 `scenario_id`·`dataset_id`·`revision_id` 를 **두지 않는다.** 그 이름이 있으면
-- `_owned_tables` 의 자동 발견이 시나리오 소유로 판정해, 시나리오 하나를 지울 때 공용
-- 프로필 행이 함께 사라진다(`global_comparison_scenario` 가 겪은 사고다).
CREATE TABLE IF NOT EXISTS app_meta.global_execution_capacity (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    version INTEGER NOT NULL CHECK (version > 0),
    source VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

-- `증감 확보율` 의 단위는 **퍼센트포인트**다. 확보율 105% 에 -10 을 넣으면 95% 가 된다.
-- 비율 곱셈이 아니므로 값 범위를 제한하지 않는다.
CREATE TABLE IF NOT EXISTS app_meta.global_execution_capacity_row (
    profile_id INTEGER NOT NULL CHECK (profile_id = 1),
    "생산계획년월" INTEGER NOT NULL CHECK ("생산계획년월" % 100 BETWEEN 1 AND 12),
    "공정" VARCHAR NOT NULL CHECK ("공정" <> ''),
    "증감 확보율" DOUBLE NOT NULL,
    "비고" VARCHAR NOT NULL DEFAULT '',
    PRIMARY KEY (profile_id, "생산계획년월", "공정")
);
