CREATE TABLE ref_data.rq_upeh_route_keyed (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "Area_Name" VARCHAR,
    "공정" VARCHAR,
    "STEP_SEQ" VARCHAR,
    "MCP_SEQ" VARCHAR,
    "양산구분" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "소요기준" VARCHAR,
    "UPEH" DOUBLE,
    "ST" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

INSERT INTO ref_data.rq_upeh_route_keyed
SELECT dataset_id, source_row_no, "생산계획년월", "Area_Name", "공정",
       NULL, NULL, "양산구분", "제품정보", "Stack", "WF 구분", "소요기준",
       "UPEH", "ST"
FROM ref_data.rq_upeh;

DROP TABLE ref_data.rq_upeh;
ALTER TABLE ref_data.rq_upeh_route_keyed RENAME TO rq_upeh;

CREATE TABLE rev_data.rq_upeh_route_keyed (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "Area_Name" VARCHAR,
    "공정" VARCHAR,
    "STEP_SEQ" VARCHAR,
    "MCP_SEQ" VARCHAR,
    "양산구분" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "소요기준" VARCHAR,
    "UPEH" DOUBLE,
    "ST" DOUBLE,
    PRIMARY KEY (revision_id, source_row_no)
);

INSERT INTO rev_data.rq_upeh_route_keyed
SELECT revision_id, source_row_no, "생산계획년월", "Area_Name", "공정",
       NULL, NULL, "양산구분", "제품정보", "Stack", "WF 구분", "소요기준",
       "UPEH", "ST"
FROM rev_data.rq_upeh;

DROP TABLE rev_data.rq_upeh;
ALTER TABLE rev_data.rq_upeh_route_keyed RENAME TO rq_upeh;

CREATE TABLE ref_data.rq_lot_ratio_route_keyed (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "Area_Name" VARCHAR,
    "공정" VARCHAR,
    "STEP_SEQ" VARCHAR,
    "MCP_SEQ" VARCHAR,
    "양산구분" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "Lot 측정률" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

INSERT INTO ref_data.rq_lot_ratio_route_keyed
SELECT dataset_id, source_row_no, "생산계획년월", NULL, "공정", NULL, NULL,
       "양산구분", "제품정보", "Stack", "WF 구분", "Lot 측정률"
FROM ref_data.rq_lot_ratio;

DROP TABLE ref_data.rq_lot_ratio;
ALTER TABLE ref_data.rq_lot_ratio_route_keyed RENAME TO rq_lot_ratio;

CREATE TABLE rev_data.rq_lot_ratio_route_keyed (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "Area_Name" VARCHAR,
    "공정" VARCHAR,
    "STEP_SEQ" VARCHAR,
    "MCP_SEQ" VARCHAR,
    "양산구분" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "Lot 측정률" DOUBLE,
    PRIMARY KEY (revision_id, source_row_no)
);

INSERT INTO rev_data.rq_lot_ratio_route_keyed
SELECT revision_id, source_row_no, "생산계획년월", NULL, "공정", NULL, NULL,
       "양산구분", "제품정보", "Stack", "WF 구분", "Lot 측정률"
FROM rev_data.rq_lot_ratio;

DROP TABLE rev_data.rq_lot_ratio;
ALTER TABLE rev_data.rq_lot_ratio_route_keyed RENAME TO rq_lot_ratio;

CREATE TABLE ref_data.rq_wf_ratio_route_keyed (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "Area_Name" VARCHAR,
    "공정" VARCHAR,
    "STEP_SEQ" VARCHAR,
    "MCP_SEQ" VARCHAR,
    "양산구분" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "WF측정률" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

INSERT INTO ref_data.rq_wf_ratio_route_keyed
SELECT dataset_id, source_row_no, "생산계획년월", NULL, "공정", NULL, NULL,
       "양산구분", "제품정보", "Stack", "WF 구분", "WF측정률"
FROM ref_data.rq_wf_ratio;

DROP TABLE ref_data.rq_wf_ratio;
ALTER TABLE ref_data.rq_wf_ratio_route_keyed RENAME TO rq_wf_ratio;

CREATE TABLE rev_data.rq_wf_ratio_route_keyed (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "Area_Name" VARCHAR,
    "공정" VARCHAR,
    "STEP_SEQ" VARCHAR,
    "MCP_SEQ" VARCHAR,
    "양산구분" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "WF측정률" DOUBLE,
    PRIMARY KEY (revision_id, source_row_no)
);

INSERT INTO rev_data.rq_wf_ratio_route_keyed
SELECT revision_id, source_row_no, "생산계획년월", NULL, "공정", NULL, NULL,
       "양산구분", "제품정보", "Stack", "WF 구분", "WF측정률"
FROM rev_data.rq_wf_ratio;

DROP TABLE rev_data.rq_wf_ratio;
ALTER TABLE rev_data.rq_wf_ratio_route_keyed RENAME TO rq_wf_ratio;
