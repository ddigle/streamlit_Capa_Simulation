-- Purpose: 이미 저장된 EDP-TSV 행의 `WF 구분` `Top` 을 `Top_e` 로 바꿔 신규 파생과 맞춘다.

-- `build_q_core_data` 가 이제 EDP-TSV 의 `Top` 을 `Top_e` 로 가르므로, 그 전에 적재된
-- 기준정보·리비전 스냅샷만 옛 값을 들고 있게 된다. 같은 조인 키가 두 이름으로 갈리면
-- 수율·Chip·경로가 조용히 안 붙는다. 여기서 한 번에 맞춘다.
--
-- 판별은 `rq_pkg_plan` 의 `제품타입`(0013 에서 채움)을 쓰고, 계획에 없는 제품은 원천의
-- 제품→타입 매핑으로 한 번 더 훑는다. 매핑이 갈리는 제품은 건드리지 않는다.

UPDATE ref_data.rq_chip_eq AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT DISTINCT dataset_id, "제품정보"
    FROM ref_data.rq_pkg_plan
    WHERE "제품타입" = 'EDP-TSV'
) AS edp
WHERE target.dataset_id = edp.dataset_id
  AND target."제품정보" = edp."제품정보"
  AND trim(target."WF 구분") = 'Top';

UPDATE ref_data.rq_chip_eq AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND mapped."제품타입" = 'EDP-TSV'
  AND trim(target."WF 구분") = 'Top';

UPDATE ref_data.rq_chip_qty AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT DISTINCT dataset_id, "제품정보"
    FROM ref_data.rq_pkg_plan
    WHERE "제품타입" = 'EDP-TSV'
) AS edp
WHERE target.dataset_id = edp.dataset_id
  AND target."제품정보" = edp."제품정보"
  AND trim(target."WF 구분") = 'Top';

UPDATE ref_data.rq_chip_qty AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND mapped."제품타입" = 'EDP-TSV'
  AND trim(target."WF 구분") = 'Top';

UPDATE ref_data.rq_lot_ratio AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT DISTINCT dataset_id, "제품정보"
    FROM ref_data.rq_pkg_plan
    WHERE "제품타입" = 'EDP-TSV'
) AS edp
WHERE target.dataset_id = edp.dataset_id
  AND target."제품정보" = edp."제품정보"
  AND trim(target."WF 구분") = 'Top';

UPDATE ref_data.rq_lot_ratio AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND mapped."제품타입" = 'EDP-TSV'
  AND trim(target."WF 구분") = 'Top';

UPDATE ref_data.rq_reqb AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT DISTINCT dataset_id, "제품정보"
    FROM ref_data.rq_pkg_plan
    WHERE "제품타입" = 'EDP-TSV'
) AS edp
WHERE target.dataset_id = edp.dataset_id
  AND target."제품정보" = edp."제품정보"
  AND trim(target."WF 구분") = 'Top';

UPDATE ref_data.rq_reqb AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND mapped."제품타입" = 'EDP-TSV'
  AND trim(target."WF 구분") = 'Top';

UPDATE ref_data.rq_upeh AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT DISTINCT dataset_id, "제품정보"
    FROM ref_data.rq_pkg_plan
    WHERE "제품타입" = 'EDP-TSV'
) AS edp
WHERE target.dataset_id = edp.dataset_id
  AND target."제품정보" = edp."제품정보"
  AND trim(target."WF 구분") = 'Top';

UPDATE ref_data.rq_upeh AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND mapped."제품타입" = 'EDP-TSV'
  AND trim(target."WF 구분") = 'Top';

UPDATE ref_data.rq_wf_ratio AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT DISTINCT dataset_id, "제품정보"
    FROM ref_data.rq_pkg_plan
    WHERE "제품타입" = 'EDP-TSV'
) AS edp
WHERE target.dataset_id = edp.dataset_id
  AND target."제품정보" = edp."제품정보"
  AND trim(target."WF 구분") = 'Top';

UPDATE ref_data.rq_wf_ratio AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND mapped."제품타입" = 'EDP-TSV'
  AND trim(target."WF 구분") = 'Top';

UPDATE ref_data.rq_yld AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT DISTINCT dataset_id, "제품정보"
    FROM ref_data.rq_pkg_plan
    WHERE "제품타입" = 'EDP-TSV'
) AS edp
WHERE target.dataset_id = edp.dataset_id
  AND target."제품정보" = edp."제품정보"
  AND trim(target."WF 구분") = 'Top';

UPDATE ref_data.rq_yld AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND mapped."제품타입" = 'EDP-TSV'
  AND trim(target."WF 구분") = 'Top';

UPDATE rev_data.rq_chip_eq AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT DISTINCT revision_id, "제품정보"
    FROM rev_data.rq_pkg_plan
    WHERE "제품타입" = 'EDP-TSV'
) AS edp
WHERE target.revision_id = edp.revision_id
  AND target."제품정보" = edp."제품정보"
  AND trim(target."WF 구분") = 'Top';

UPDATE rev_data.rq_chip_eq AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND mapped."제품타입" = 'EDP-TSV'
  AND trim(target."WF 구분") = 'Top';

UPDATE rev_data.rq_chip_qty AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT DISTINCT revision_id, "제품정보"
    FROM rev_data.rq_pkg_plan
    WHERE "제품타입" = 'EDP-TSV'
) AS edp
WHERE target.revision_id = edp.revision_id
  AND target."제품정보" = edp."제품정보"
  AND trim(target."WF 구분") = 'Top';

UPDATE rev_data.rq_chip_qty AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND mapped."제품타입" = 'EDP-TSV'
  AND trim(target."WF 구분") = 'Top';

UPDATE rev_data.rq_lot_ratio AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT DISTINCT revision_id, "제품정보"
    FROM rev_data.rq_pkg_plan
    WHERE "제품타입" = 'EDP-TSV'
) AS edp
WHERE target.revision_id = edp.revision_id
  AND target."제품정보" = edp."제품정보"
  AND trim(target."WF 구분") = 'Top';

UPDATE rev_data.rq_lot_ratio AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND mapped."제품타입" = 'EDP-TSV'
  AND trim(target."WF 구분") = 'Top';

UPDATE rev_data.rq_reqb AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT DISTINCT revision_id, "제품정보"
    FROM rev_data.rq_pkg_plan
    WHERE "제품타입" = 'EDP-TSV'
) AS edp
WHERE target.revision_id = edp.revision_id
  AND target."제품정보" = edp."제품정보"
  AND trim(target."WF 구분") = 'Top';

UPDATE rev_data.rq_reqb AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND mapped."제품타입" = 'EDP-TSV'
  AND trim(target."WF 구분") = 'Top';

UPDATE rev_data.rq_upeh AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT DISTINCT revision_id, "제품정보"
    FROM rev_data.rq_pkg_plan
    WHERE "제품타입" = 'EDP-TSV'
) AS edp
WHERE target.revision_id = edp.revision_id
  AND target."제품정보" = edp."제품정보"
  AND trim(target."WF 구분") = 'Top';

UPDATE rev_data.rq_upeh AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND mapped."제품타입" = 'EDP-TSV'
  AND trim(target."WF 구분") = 'Top';

UPDATE rev_data.rq_wf_ratio AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT DISTINCT revision_id, "제품정보"
    FROM rev_data.rq_pkg_plan
    WHERE "제품타입" = 'EDP-TSV'
) AS edp
WHERE target.revision_id = edp.revision_id
  AND target."제품정보" = edp."제품정보"
  AND trim(target."WF 구분") = 'Top';

UPDATE rev_data.rq_wf_ratio AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND mapped."제품타입" = 'EDP-TSV'
  AND trim(target."WF 구분") = 'Top';

UPDATE rev_data.rq_yld AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT DISTINCT revision_id, "제품정보"
    FROM rev_data.rq_pkg_plan
    WHERE "제품타입" = 'EDP-TSV'
) AS edp
WHERE target.revision_id = edp.revision_id
  AND target."제품정보" = edp."제품정보"
  AND trim(target."WF 구분") = 'Top';

UPDATE rev_data.rq_yld AS target
SET "WF 구분" = 'Top_e'
FROM (
    SELECT "제품정보", min("제품타입") AS "제품타입"
    FROM raw_data.core_data
    WHERE "제품타입" IS NOT NULL
    GROUP BY "제품정보"
    HAVING count(DISTINCT "제품타입") = 1
) AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND mapped."제품타입" = 'EDP-TSV'
  AND trim(target."WF 구분") = 'Top';
