CREATE TABLE IF NOT EXISTS rev_data.rq_eqp_own (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "설비보유" DOUBLE,
    PRIMARY KEY (revision_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS rev_data.rq_eqp_lent (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "설비대여평가" DOUBLE,
    PRIMARY KEY (revision_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS rev_data.rq_eqp_avbl (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "가용대수" DOUBLE,
    PRIMARY KEY (revision_id, source_row_no)
);

INSERT INTO rev_data.rq_eqp_own
SELECT r.revision_id, q.source_row_no, q."생산계획년월", q."공정", q."설비보유"
FROM app_meta.scenario_revision r
JOIN app_meta.dataset d ON d.scenario_id = r.scenario_id
JOIN ref_data.rq_eqp_own q ON q.dataset_id = d.dataset_id;

INSERT INTO rev_data.rq_eqp_lent
SELECT r.revision_id, q.source_row_no, q."생산계획년월", q."공정", q."설비대여평가"
FROM app_meta.scenario_revision r
JOIN app_meta.dataset d ON d.scenario_id = r.scenario_id
JOIN ref_data.rq_eqp_lent q ON q.dataset_id = d.dataset_id;

INSERT INTO rev_data.rq_eqp_avbl
SELECT r.revision_id, q.source_row_no, q."생산계획년월", q."공정", q."가용대수"
FROM app_meta.scenario_revision r
JOIN app_meta.dataset d ON d.scenario_id = r.scenario_id
JOIN ref_data.rq_eqp_avbl q ON q.dataset_id = d.dataset_id;
