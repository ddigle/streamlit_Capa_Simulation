-- Purpose: 리비전 1 과 행 단위로 같은 `ref_data` 의 옛 리비전 표 사본을 지운다.

-- 2026-10-06 사용자 결정(B3) 전에는 `create_scenario` 가 리비전 표 14개(`repository.REVISION_TABLES`)
-- 를 데이터셋(`ref_data`)과 리비전 1(`rev_data`)에 똑같이 적었다. 스냅샷은 그 14개를 `rev_data`
-- 에서만 읽고 리비전은 불변이라, 데이터셋 쪽 사본은 읽는 코드 없이 파일만 키웠다(사내 DB
-- 1,484,071행, 21 데이터셋 — 2026-10-08 리뷰). 2026-10-10 사용자가 지우기를 승인했다.
--
-- **지우는 단위는 (데이터셋, 표)다.** 한 데이터셋의 한 표 사본을 통째로 지우거나 통째로 둔다.
-- 지우는 조건은 하나다 — 그 사본의 **모든 행**이 그 데이터셋을 가진 시나리오의 **리비전 1**
-- (`revision_no = 1`) `rev_data` 에 **행 단위로** 들어 있어야 한다. 아래 `EXCEPT ALL` 이 그
-- 데이터셋 몫으로 한 행도 남기지 않을 때만 지운다. 그래서 지워도 사라지는 값이 없다.
--
--   - 맞대는 열은 소유 열(`dataset_id` · `revision_id`)만 빼고 **전부**다 — `source_row_no` 와
--     값 열 모두. 위치가 아니라 **이름으로** 적어 맞댄다(0013 이 덧붙인 `제품타입`·`Pack Code`
--     처럼 열이 뒤에 붙어도 이름이 짝을 정한다). 집합 연산이라 NULL 은 NULL 과 같다고 본다.
--   - 사본이 리비전 1 보다 적은 것(사본 ⊂ 리비전 1)은 지운다 — 사본의 행이 다 리비전 1 에 있다.
--   - **남기는 것**: 한 행이라도 리비전 1 에 없는 사본(값이 다르거나 행이 더 많다), 리비전 1
--     이 없는 데이터셋, `app_meta.dataset` 에 없는 데이터셋의 행. 셋 다 `EXCEPT ALL` 이 행을
--     남겨 `unmatched` 에 든다. 옛 복제 경로처럼 데이터셋에 적은 표와 리비전 1 에 적은 표가
--     달랐던 데이터셋이 여기 해당할 수 있다 — 읽는 곳은 없지만 다른 곳에 없는 값이라 두고 간다.
--   - 리비전 1 이 아닌 리비전과는 맞대지 않는다. 사본은 시나리오를 만들 때 리비전 1 과 함께
--     적혔고, 다른 리비전과 같다고 해서 리비전 1 의 사본이었다는 뜻은 아니다.
--
-- **DELETE 가 아니라 표를 다시 만든다**(0006 과 같은 꼴). 남길 행(`unmatched` 가 있는 데이터셋의
-- 사본 전부)만 새 표에 옮기고 옛 표를 지운 뒤 이름을 바꾼다. 거의 모든 행을 지우는 일이라
-- 기본키 색인이 걸린 표에서 DELETE 가 느렸다 — 샘플 관측(합성 데모 DB 를 1,685,790행으로 부풀린
-- 사본, 개발 PC): DELETE 약 20초(그 가운데 커밋 8초) → 다시 만들기 3초. 새 표의 열 이름·순서·
-- 형식·NOT NULL·기본키는 0001·0006·0007·0008·0011·0012·0013 을 거친 뒤의 것과 같다
-- (`tests/test_migration_0033_ref_data_copies.py` 가 마이그레이션 전후 스키마가 같은지 본다).
-- `INSERT ... BY NAME` 이라 새 표에 없는 열이 옛 표에 있으면 오류로 멈추고 통째로 되돌린다.
--
-- 데이터셋 표 둘(`rq_display_order` · `rq_module`, `repository.DATASET_TABLES`)은 손대지 않는다
-- — 지금도 그 둘은 `ref_data` 에만 산다. `rev_data` 는 읽기만 하고 고치지 않는다.
--
-- **두 번 돌려도 같다.** 지운 데이터셋은 사본이 없어 다시 걸리지 않고, 남긴 사본은 같은
-- 까닭으로 다시 남는다. 새 데이터셋(B3 뒤)은 처음부터 사본이 없어 아무 일도 없다.
--
-- 지운 표의 블록은 DuckDB 의 빈 블록 목록으로 돌아가 다음 쓰기가 다시 쓰지만 **파일은 줄지
-- 않는다.** 파일 크기를 줄이는 것은 `scripts/compact_duckdb.py` 재구축(E8)뿐이고 여기서 하지 않는다.
--
-- 번호는 claude 후보 브랜치의 홀수 배정(0032 는 비운다).

-- 데이터셋마다 그 시나리오의 리비전 1. `dataset.scenario_id` 가 UNIQUE 이고
-- `(scenario_id, revision_no)` 도 UNIQUE 라 데이터셋 하나에 리비전 1 은 많아야 하나다.
CREATE OR REPLACE TEMP VIEW _ref_copy_first_revision AS
SELECT r.revision_id, d.dataset_id
FROM app_meta.scenario_revision AS r
JOIN app_meta.dataset AS d ON d.scenario_id = r.scenario_id
WHERE r.revision_no = 1;

-- 표마다 같은 꼴이다: 리비전 1 에 없는 행(`unmatched`)이 하나라도 있는 데이터셋의 사본만
-- 새 표로 옮기고, 나머지(리비전 1 에 다 들어 있는 사본)는 옛 표와 함께 지운다.

-- rq_pkg_plan
CREATE TABLE ref_data.rq_pkg_plan_kept (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "양산구분" VARCHAR,
    "CS" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "Capa Code" VARCHAR,
    "Customer" VARCHAR,
    "생산수량" DOUBLE,
    "제품타입" VARCHAR,
    "Pack Code" VARCHAR,
    PRIMARY KEY (dataset_id, source_row_no)
);

INSERT INTO ref_data.rq_pkg_plan_kept BY NAME
SELECT * FROM ref_data.rq_pkg_plan
WHERE dataset_id IN (
    SELECT dataset_id FROM (
        SELECT dataset_id, source_row_no, "생산계획년월", "양산구분", "CS", "제품정보", "Stack", "Capa Code",
               "Customer", "생산수량", "제품타입", "Pack Code"
        FROM ref_data.rq_pkg_plan
        EXCEPT ALL
        SELECT r1.dataset_id, v.source_row_no, v."생산계획년월", v."양산구분", v."CS", v."제품정보",
               v."Stack", v."Capa Code", v."Customer", v."생산수량", v."제품타입", v."Pack Code"
        FROM rev_data.rq_pkg_plan AS v
        JOIN _ref_copy_first_revision AS r1 USING (revision_id)
    ) AS unmatched
);

DROP TABLE ref_data.rq_pkg_plan;
ALTER TABLE ref_data.rq_pkg_plan_kept RENAME TO rq_pkg_plan;

-- rq_yld
CREATE TABLE ref_data.rq_yld_kept (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "EDS_수율" DOUBLE,
    "BE_수율" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

INSERT INTO ref_data.rq_yld_kept BY NAME
SELECT * FROM ref_data.rq_yld
WHERE dataset_id IN (
    SELECT dataset_id FROM (
        SELECT dataset_id, source_row_no, "생산계획년월", "제품정보", "Stack", "WF 구분", "EDS_수율", "BE_수율"
        FROM ref_data.rq_yld
        EXCEPT ALL
        SELECT r1.dataset_id, v.source_row_no, v."생산계획년월", v."제품정보", v."Stack", v."WF 구분",
               v."EDS_수율", v."BE_수율"
        FROM rev_data.rq_yld AS v
        JOIN _ref_copy_first_revision AS r1 USING (revision_id)
    ) AS unmatched
);

DROP TABLE ref_data.rq_yld;
ALTER TABLE ref_data.rq_yld_kept RENAME TO rq_yld;

-- rq_chip_qty
CREATE TABLE ref_data.rq_chip_qty_kept (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "구분_Chip" DOUBLE,
    "Net Die" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

INSERT INTO ref_data.rq_chip_qty_kept BY NAME
SELECT * FROM ref_data.rq_chip_qty
WHERE dataset_id IN (
    SELECT dataset_id FROM (
        SELECT dataset_id, source_row_no, "제품정보", "Stack", "WF 구분", "구분_Chip", "Net Die"
        FROM ref_data.rq_chip_qty
        EXCEPT ALL
        SELECT r1.dataset_id, v.source_row_no, v."제품정보", v."Stack", v."WF 구분", v."구분_Chip",
               v."Net Die"
        FROM rev_data.rq_chip_qty AS v
        JOIN _ref_copy_first_revision AS r1 USING (revision_id)
    ) AS unmatched
);

DROP TABLE ref_data.rq_chip_qty;
ALTER TABLE ref_data.rq_chip_qty_kept RENAME TO rq_chip_qty;

-- rq_chip_eq
CREATE TABLE ref_data.rq_chip_eq_kept (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "구분_Chip" DOUBLE,
    "구분_EQ" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

INSERT INTO ref_data.rq_chip_eq_kept BY NAME
SELECT * FROM ref_data.rq_chip_eq
WHERE dataset_id IN (
    SELECT dataset_id FROM (
        SELECT dataset_id, source_row_no, "제품정보", "Stack", "WF 구분", "구분_Chip", "구분_EQ"
        FROM ref_data.rq_chip_eq
        EXCEPT ALL
        SELECT r1.dataset_id, v.source_row_no, v."제품정보", v."Stack", v."WF 구분", v."구분_Chip",
               v."구분_EQ"
        FROM rev_data.rq_chip_eq AS v
        JOIN _ref_copy_first_revision AS r1 USING (revision_id)
    ) AS unmatched
);

DROP TABLE ref_data.rq_chip_eq;
ALTER TABLE ref_data.rq_chip_eq_kept RENAME TO rq_chip_eq;

-- rq_upeh
CREATE TABLE ref_data.rq_upeh_kept (
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

INSERT INTO ref_data.rq_upeh_kept BY NAME
SELECT * FROM ref_data.rq_upeh
WHERE dataset_id IN (
    SELECT dataset_id FROM (
        SELECT dataset_id, source_row_no, "생산계획년월", "Area_Name", "공정", "STEP_SEQ", "MCP_SEQ",
               "양산구분", "제품정보", "Stack", "WF 구분", "소요기준", "UPEH", "ST"
        FROM ref_data.rq_upeh
        EXCEPT ALL
        SELECT r1.dataset_id, v.source_row_no, v."생산계획년월", v."Area_Name", v."공정", v."STEP_SEQ",
               v."MCP_SEQ", v."양산구분", v."제품정보", v."Stack", v."WF 구분", v."소요기준", v."UPEH", v."ST"
        FROM rev_data.rq_upeh AS v
        JOIN _ref_copy_first_revision AS r1 USING (revision_id)
    ) AS unmatched
);

DROP TABLE ref_data.rq_upeh;
ALTER TABLE ref_data.rq_upeh_kept RENAME TO rq_upeh;

-- rq_run_rate
CREATE TABLE ref_data.rq_run_rate_kept (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "양산구분" VARCHAR,
    "CAPA_RUN_RATE" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

INSERT INTO ref_data.rq_run_rate_kept BY NAME
SELECT * FROM ref_data.rq_run_rate
WHERE dataset_id IN (
    SELECT dataset_id FROM (
        SELECT dataset_id, source_row_no, "생산계획년월", "공정", "양산구분", "CAPA_RUN_RATE"
        FROM ref_data.rq_run_rate
        EXCEPT ALL
        SELECT r1.dataset_id, v.source_row_no, v."생산계획년월", v."공정", v."양산구분", v."CAPA_RUN_RATE"
        FROM rev_data.rq_run_rate AS v
        JOIN _ref_copy_first_revision AS r1 USING (revision_id)
    ) AS unmatched
);

DROP TABLE ref_data.rq_run_rate;
ALTER TABLE ref_data.rq_run_rate_kept RENAME TO rq_run_rate;

-- rq_vital
CREATE TABLE ref_data.rq_vital_kept (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "양산구분" VARCHAR,
    "편중률" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

INSERT INTO ref_data.rq_vital_kept BY NAME
SELECT * FROM ref_data.rq_vital
WHERE dataset_id IN (
    SELECT dataset_id FROM (
        SELECT dataset_id, source_row_no, "생산계획년월", "공정", "양산구분", "편중률"
        FROM ref_data.rq_vital
        EXCEPT ALL
        SELECT r1.dataset_id, v.source_row_no, v."생산계획년월", v."공정", v."양산구분", v."편중률"
        FROM rev_data.rq_vital AS v
        JOIN _ref_copy_first_revision AS r1 USING (revision_id)
    ) AS unmatched
);

DROP TABLE ref_data.rq_vital;
ALTER TABLE ref_data.rq_vital_kept RENAME TO rq_vital;

-- rq_run_day
CREATE TABLE ref_data.rq_run_day_kept (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "RUN_DAY" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

INSERT INTO ref_data.rq_run_day_kept BY NAME
SELECT * FROM ref_data.rq_run_day
WHERE dataset_id IN (
    SELECT dataset_id FROM (
        SELECT dataset_id, source_row_no, "생산계획년월", "공정", "RUN_DAY"
        FROM ref_data.rq_run_day
        EXCEPT ALL
        SELECT r1.dataset_id, v.source_row_no, v."생산계획년월", v."공정", v."RUN_DAY"
        FROM rev_data.rq_run_day AS v
        JOIN _ref_copy_first_revision AS r1 USING (revision_id)
    ) AS unmatched
);

DROP TABLE ref_data.rq_run_day;
ALTER TABLE ref_data.rq_run_day_kept RENAME TO rq_run_day;

-- rq_lot_ratio
CREATE TABLE ref_data.rq_lot_ratio_kept (
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

INSERT INTO ref_data.rq_lot_ratio_kept BY NAME
SELECT * FROM ref_data.rq_lot_ratio
WHERE dataset_id IN (
    SELECT dataset_id FROM (
        SELECT dataset_id, source_row_no, "생산계획년월", "Area_Name", "공정", "STEP_SEQ", "MCP_SEQ",
               "양산구분", "제품정보", "Stack", "WF 구분", "Lot 측정률"
        FROM ref_data.rq_lot_ratio
        EXCEPT ALL
        SELECT r1.dataset_id, v.source_row_no, v."생산계획년월", v."Area_Name", v."공정", v."STEP_SEQ",
               v."MCP_SEQ", v."양산구분", v."제품정보", v."Stack", v."WF 구분", v."Lot 측정률"
        FROM rev_data.rq_lot_ratio AS v
        JOIN _ref_copy_first_revision AS r1 USING (revision_id)
    ) AS unmatched
);

DROP TABLE ref_data.rq_lot_ratio;
ALTER TABLE ref_data.rq_lot_ratio_kept RENAME TO rq_lot_ratio;

-- rq_wf_ratio
CREATE TABLE ref_data.rq_wf_ratio_kept (
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

INSERT INTO ref_data.rq_wf_ratio_kept BY NAME
SELECT * FROM ref_data.rq_wf_ratio
WHERE dataset_id IN (
    SELECT dataset_id FROM (
        SELECT dataset_id, source_row_no, "생산계획년월", "Area_Name", "공정", "STEP_SEQ", "MCP_SEQ",
               "양산구분", "제품정보", "Stack", "WF 구분", "WF측정률"
        FROM ref_data.rq_wf_ratio
        EXCEPT ALL
        SELECT r1.dataset_id, v.source_row_no, v."생산계획년월", v."Area_Name", v."공정", v."STEP_SEQ",
               v."MCP_SEQ", v."양산구분", v."제품정보", v."Stack", v."WF 구분", v."WF측정률"
        FROM rev_data.rq_wf_ratio AS v
        JOIN _ref_copy_first_revision AS r1 USING (revision_id)
    ) AS unmatched
);

DROP TABLE ref_data.rq_wf_ratio;
ALTER TABLE ref_data.rq_wf_ratio_kept RENAME TO rq_wf_ratio;

-- rq_reqb
CREATE TABLE ref_data.rq_reqb_kept (
    dataset_id VARCHAR NOT NULL,
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
    PRIMARY KEY (dataset_id, source_row_no)
);

INSERT INTO ref_data.rq_reqb_kept BY NAME
SELECT * FROM ref_data.rq_reqb
WHERE dataset_id IN (
    SELECT dataset_id FROM (
        SELECT dataset_id, source_row_no, "생산계획년월", "Area_Name", "공정", "양산구분", "제품정보", "Stack",
               "Capa Code", "Customer", "CS", "WF 구분", "STEP_SEQ", "MCP_SEQ", "소요기준"
        FROM ref_data.rq_reqb
        EXCEPT ALL
        SELECT r1.dataset_id, v.source_row_no, v."생산계획년월", v."Area_Name", v."공정", v."양산구분",
               v."제품정보", v."Stack", v."Capa Code", v."Customer", v."CS", v."WF 구분",
               v."STEP_SEQ", v."MCP_SEQ", v."소요기준"
        FROM rev_data.rq_reqb AS v
        JOIN _ref_copy_first_revision AS r1 USING (revision_id)
    ) AS unmatched
);

DROP TABLE ref_data.rq_reqb;
ALTER TABLE ref_data.rq_reqb_kept RENAME TO rq_reqb;

-- rq_eqp_own
CREATE TABLE ref_data.rq_eqp_own_kept (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "설비보유" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

INSERT INTO ref_data.rq_eqp_own_kept BY NAME
SELECT * FROM ref_data.rq_eqp_own
WHERE dataset_id IN (
    SELECT dataset_id FROM (
        SELECT dataset_id, source_row_no, "생산계획년월", "공정", "설비보유"
        FROM ref_data.rq_eqp_own
        EXCEPT ALL
        SELECT r1.dataset_id, v.source_row_no, v."생산계획년월", v."공정", v."설비보유"
        FROM rev_data.rq_eqp_own AS v
        JOIN _ref_copy_first_revision AS r1 USING (revision_id)
    ) AS unmatched
);

DROP TABLE ref_data.rq_eqp_own;
ALTER TABLE ref_data.rq_eqp_own_kept RENAME TO rq_eqp_own;

-- rq_eqp_lent
CREATE TABLE ref_data.rq_eqp_lent_kept (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "설비대여평가" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

INSERT INTO ref_data.rq_eqp_lent_kept BY NAME
SELECT * FROM ref_data.rq_eqp_lent
WHERE dataset_id IN (
    SELECT dataset_id FROM (
        SELECT dataset_id, source_row_no, "생산계획년월", "공정", "설비대여평가"
        FROM ref_data.rq_eqp_lent
        EXCEPT ALL
        SELECT r1.dataset_id, v.source_row_no, v."생산계획년월", v."공정", v."설비대여평가"
        FROM rev_data.rq_eqp_lent AS v
        JOIN _ref_copy_first_revision AS r1 USING (revision_id)
    ) AS unmatched
);

DROP TABLE ref_data.rq_eqp_lent;
ALTER TABLE ref_data.rq_eqp_lent_kept RENAME TO rq_eqp_lent;

-- rq_eqp_avbl
CREATE TABLE ref_data.rq_eqp_avbl_kept (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "가용대수" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

INSERT INTO ref_data.rq_eqp_avbl_kept BY NAME
SELECT * FROM ref_data.rq_eqp_avbl
WHERE dataset_id IN (
    SELECT dataset_id FROM (
        SELECT dataset_id, source_row_no, "생산계획년월", "공정", "가용대수"
        FROM ref_data.rq_eqp_avbl
        EXCEPT ALL
        SELECT r1.dataset_id, v.source_row_no, v."생산계획년월", v."공정", v."가용대수"
        FROM rev_data.rq_eqp_avbl AS v
        JOIN _ref_copy_first_revision AS r1 USING (revision_id)
    ) AS unmatched
);

DROP TABLE ref_data.rq_eqp_avbl;
ALTER TABLE ref_data.rq_eqp_avbl_kept RENAME TO rq_eqp_avbl;

-- 뷰는 세션에 남기지 않는다.
DROP VIEW IF EXISTS _ref_copy_first_revision;
