CREATE TABLE IF NOT EXISTS rev_data.rq_reqb (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "Area_Name" VARCHAR,
    "공정" VARCHAR,
    "양산구분" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "Capa Code" VARCHAR,
    "Customer" VARCHAR,
    "CS" VARCHAR,
    "WF 구분" VARCHAR,
    "STEP_SEQ" VARCHAR,
    "MCP_SEQ" VARCHAR,
    "소요기준" VARCHAR,
    PRIMARY KEY (revision_id, source_row_no)
);

INSERT INTO rev_data.rq_reqb
SELECT r.revision_id, q.source_row_no, q."생산계획년월", q."Area_Name", q."공정",
       q."양산구분", q."제품정보", q."Stack", q."Capa Code", q."Customer", q."CS",
       q."WF 구분", q."STEP_SEQ", q."MCP_SEQ", q."소요기준"
FROM app_meta.scenario_revision r
JOIN app_meta.dataset d ON d.scenario_id = r.scenario_id
JOIN ref_data.rq_reqb q ON q.dataset_id = d.dataset_id;
