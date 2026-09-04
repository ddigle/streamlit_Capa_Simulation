CREATE TABLE IF NOT EXISTS rev_data.rq_chip_qty (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "구분_Chip" DOUBLE,
    "Net Die" DOUBLE,
    PRIMARY KEY (revision_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS rev_data.rq_chip_eq (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "구분_Chip" DOUBLE,
    "구분_EQ" DOUBLE,
    PRIMARY KEY (revision_id, source_row_no)
);

INSERT INTO rev_data.rq_chip_qty
SELECT r.revision_id, q.source_row_no, q."제품정보", q."Stack", q."WF 구분",
       q."구분_Chip", q."Net Die"
FROM app_meta.scenario_revision r
JOIN app_meta.dataset d ON d.scenario_id = r.scenario_id
JOIN ref_data.rq_chip_qty q ON q.dataset_id = d.dataset_id;

INSERT INTO rev_data.rq_chip_eq
SELECT r.revision_id, e.source_row_no, e."제품정보", e."Stack", e."WF 구분",
       e."구분_Chip", e."구분_EQ"
FROM app_meta.scenario_revision r
JOIN app_meta.dataset d ON d.scenario_id = r.scenario_id
JOIN ref_data.rq_chip_eq e ON e.dataset_id = d.dataset_id;

CREATE TABLE IF NOT EXISTS app_meta.revision_virtual_product (
    revision_id VARCHAR NOT NULL,
    "제품정보" VARCHAR NOT NULL,
    "Stack" VARCHAR NOT NULL,
    source_product VARCHAR NOT NULL,
    source_stack VARCHAR NOT NULL,
    note VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (revision_id, "제품정보", "Stack")
);
