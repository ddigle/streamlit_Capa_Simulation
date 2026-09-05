-- Purpose: PKG PLAN 에 제품타입과 Pack Code 를 실어 EDP 판별과 제품타입별 로직을 가능하게 한다.

ALTER TABLE ref_data.rq_pkg_plan ADD COLUMN "제품타입" VARCHAR;
ALTER TABLE ref_data.rq_pkg_plan ADD COLUMN "Pack Code" VARCHAR;
ALTER TABLE rev_data.rq_pkg_plan ADD COLUMN "제품타입" VARCHAR;
ALTER TABLE rev_data.rq_pkg_plan ADD COLUMN "Pack Code" VARCHAR;

-- 기존 행을 원천에서 되채운다. 비워 두면 EDP 판별이 조용히 "전부 EDP 아님" 으로 떨어진다.
-- 원천이 한 제품에 두 값을 싣고 있으면 고르지 않고 NULL 로 남긴다(HAVING 절).
UPDATE ref_data.rq_pkg_plan AS plan
SET "제품타입" = mapped."제품타입"
FROM (
    SELECT dataset_id, "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY dataset_id, "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE plan.dataset_id = mapped.dataset_id AND plan."제품정보" = mapped."제품정보";

UPDATE ref_data.rq_pkg_plan AS plan
SET "Pack Code" = mapped."Pack Code"
FROM (
    SELECT dataset_id, "제품정보", "Stack", "Capa Code", "Customer", "CS",
           min("Pack Code") AS "Pack Code"
    FROM raw_data.core_data
    WHERE "Pack Code" IS NOT NULL
    GROUP BY dataset_id, "제품정보", "Stack", "Capa Code", "Customer", "CS"
    HAVING count(DISTINCT "Pack Code") = 1
) AS mapped
WHERE plan.dataset_id = mapped.dataset_id
  AND plan."제품정보" = mapped."제품정보"
  AND plan."Stack" = mapped."Stack"
  AND plan."Capa Code" = mapped."Capa Code"
  AND plan."Customer" = mapped."Customer"
  AND plan."CS" = mapped."CS";

-- 리비전 스냅샷은 시나리오를 거쳐 데이터셋에 닿는다. 한 시나리오에 데이터셋이 여럿이고
-- 값이 갈리면 역시 NULL 로 남긴다.
UPDATE rev_data.rq_pkg_plan AS plan
SET "제품타입" = mapped."제품타입"
FROM (
    SELECT revision.revision_id, core."제품정보", min(core."제품타입") AS "제품타입"
    FROM app_meta.scenario_revision AS revision
    JOIN app_meta.dataset AS dataset ON dataset.scenario_id = revision.scenario_id
    JOIN raw_data.core_data AS core ON core.dataset_id = dataset.dataset_id
    WHERE core."제품타입" IS NOT NULL
    GROUP BY revision.revision_id, core."제품정보"
    HAVING count(DISTINCT core."제품타입") = 1
) AS mapped
WHERE plan.revision_id = mapped.revision_id AND plan."제품정보" = mapped."제품정보";

UPDATE rev_data.rq_pkg_plan AS plan
SET "Pack Code" = mapped."Pack Code"
FROM (
    SELECT revision.revision_id, core."제품정보", core."Stack", core."Capa Code",
           core."Customer", core."CS", min(core."Pack Code") AS "Pack Code"
    FROM app_meta.scenario_revision AS revision
    JOIN app_meta.dataset AS dataset ON dataset.scenario_id = revision.scenario_id
    JOIN raw_data.core_data AS core ON core.dataset_id = dataset.dataset_id
    WHERE core."Pack Code" IS NOT NULL
    GROUP BY revision.revision_id, core."제품정보", core."Stack", core."Capa Code",
             core."Customer", core."CS"
    HAVING count(DISTINCT core."Pack Code") = 1
) AS mapped
WHERE plan.revision_id = mapped.revision_id
  AND plan."제품정보" = mapped."제품정보"
  AND plan."Stack" = mapped."Stack"
  AND plan."Capa Code" = mapped."Capa Code"
  AND plan."Customer" = mapped."Customer"
  AND plan."CS" = mapped."CS";

-- 복제 시나리오(DUCKDB_SCENARIO_CLONE)는 자기 raw_data.core_data 가 0행이라 위 백필이 닿지
-- 않는다. 제품타입은 제품의 속성이므로 아직 빈 자리만 전역 매핑으로 채운다. 여기서도 값이
-- 갈리면 채우지 않는다.
UPDATE ref_data.rq_pkg_plan AS plan
SET "제품타입" = mapped."제품타입"
FROM (
    SELECT "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE plan."제품타입" IS NULL AND plan."제품정보" = mapped."제품정보";

UPDATE rev_data.rq_pkg_plan AS plan
SET "제품타입" = mapped."제품타입"
FROM (
    SELECT "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE plan."제품타입" IS NULL AND plan."제품정보" = mapped."제품정보";

UPDATE ref_data.rq_pkg_plan AS plan
SET "Pack Code" = mapped."Pack Code"
FROM (
    SELECT "제품정보", "Stack", "Capa Code", "Customer", "CS",
           min("Pack Code") AS "Pack Code"
    FROM raw_data.core_data
    WHERE "Pack Code" IS NOT NULL
    GROUP BY "제품정보", "Stack", "Capa Code", "Customer", "CS"
    HAVING count(DISTINCT "Pack Code") = 1
) AS mapped
WHERE plan."Pack Code" IS NULL
  AND plan."제품정보" = mapped."제품정보"
  AND plan."Stack" = mapped."Stack"
  AND plan."Capa Code" = mapped."Capa Code"
  AND plan."Customer" = mapped."Customer"
  AND plan."CS" = mapped."CS";

UPDATE rev_data.rq_pkg_plan AS plan
SET "Pack Code" = mapped."Pack Code"
FROM (
    SELECT "제품정보", "Stack", "Capa Code", "Customer", "CS",
           min("Pack Code") AS "Pack Code"
    FROM raw_data.core_data
    WHERE "Pack Code" IS NOT NULL
    GROUP BY "제품정보", "Stack", "Capa Code", "Customer", "CS"
    HAVING count(DISTINCT "Pack Code") = 1
) AS mapped
WHERE plan."Pack Code" IS NULL
  AND plan."제품정보" = mapped."제품정보"
  AND plan."Stack" = mapped."Stack"
  AND plan."Capa Code" = mapped."Capa Code"
  AND plan."Customer" = mapped."Customer"
  AND plan."CS" = mapped."CS";
