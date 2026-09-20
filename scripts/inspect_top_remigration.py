# Purpose: `Top` 재이관 마이그레이션을 쓰기 전에 실데이터의 전제를 읽기 전용으로 측정한다.

"""재이관을 **쓰기 전에** 재야 하는 것들.

마이그레이션 `0014` 는 `trim("WF 구분") = 'Top'` 으로 비교했는데 원천 표기가 대문자 `TOP`
이라 **운영 데이터에서 한 행도 걸리지 않았다.** 로컬 합성 표본만 `Top` 이라 검사도 조용히
통과했다. 적용된 마이그레이션은 버전 번호로 체크섬을 대조하므로 고칠 수 없고, 후속 번호로
다시 해야 한다.

**같은 실수를 번호만 태우고 반복하지 않으려고 이 스크립트를 먼저 만든다.** 후속
마이그레이션이 기대는 전제가 넷인데, 넷 다 코드가 보장하지 못하고 실데이터만 답할 수 있다.

1. `제품타입` 의 실제 표기가 `EDP-TSV` 인가. 원천 컬럼을 그대로 옮긴 값이라 코드가 정하지
   않는다. 다르면 `0014` 와 똑같은 자리에서 또 0행이 된다.
2. `제품정보` 가 **두 표기로 갈려 있다.** `build_q_core_data` 는 RQ 표를 만들기 전에
   언더스코어를 공백으로 바꾸는데(`core_data_derivation.py`) `raw_data.core_data` 는 원천을
   그대로 둔다. 둘을 글자로 맞대는 조인은 이름에 `_` 가 있는 제품에서 영영 빗나간다.
3. 한 제품이 데이터셋마다 다른 `제품타입` 을 갖거나 한쪽이 비어 있으면, 제품 단위 판별이
   HBM 행까지 끌고 간다.
4. 실제로 몇 행이 바뀌는가. 0 이면 전제가 틀린 것이고, 너무 많으면 범위를 잘못 잡은 것이다.

**읽기만 한다.** `read_only=True` 로 열어 쓰기 경로를 막았다. 제품명·고객명은 찍지 않고
**개수만** 보고한다 — `제품타입`(`HBM`·`EDP-TSV`)은 제품군 이름이라 그대로 적는다.

사용:

    uv run --no-sync python scripts/inspect_top_remigration.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capa_simulation.settings import DUCKDB_PATH  # noqa: E402

# `0014` 가 손댄 표. 두 스키마에 같은 이름으로 있다.
TABLES: tuple[str, ...] = (
    "rq_chip_eq",
    "rq_chip_qty",
    "rq_lot_ratio",
    "rq_reqb",
    "rq_upeh",
    "rq_wf_ratio",
    "rq_yld",
)

# `core_data_derivation.build_q_core_data` 의 `제품정보` 정리를 SQL 로 옮긴 것. 파생 표기와
# 원천 표기를 맞대려면 같은 규칙으로 줄여야 한다. `chr(160)` 은 RE2 가 NBSP 유니코드 이스케이프를
# 받지 않아 따로 바꾼다.
NORMALIZED_PRODUCT = (
    "trim(regexp_replace("
    "replace(replace(replace(\"제품정보\", chr(160), ' '), '*_', ' '), '_', ' '), "
    r"'\s+', ' ', 'g'))"
)


def _rows(connection: duckdb.DuckDBPyConnection, sql: str) -> list[tuple[object, ...]]:
    try:
        return connection.execute(sql).fetchall()
    except duckdb.Error as exc:
        print(f"    읽지 못함 — {str(exc).splitlines()[0]}")
        return []


def _scalar(connection: duckdb.DuckDBPyConnection, sql: str) -> int:
    rows = _rows(connection, sql)
    return int(rows[0][0]) if rows and rows[0][0] is not None else 0


def _product_type_shapes(connection: duckdb.DuckDBPyConnection) -> None:
    print("1) `제품타입` 의 실제 표기 — 재이관이 맞대는 리터럴이 이 중에 있어야 한다")
    rows = _rows(
        connection,
        "SELECT coalesce(upper(trim(\"제품타입\")), '(비어 있음)') AS k, count(*) "
        "FROM raw_data.core_data GROUP BY 1 ORDER BY 2 DESC",
    )
    for key, count in rows:
        mark = "  <- 재이관이 찾는 값" if key == "EDP-TSV" else ""
        print(f"    {str(key):20} {int(count):>10,}행{mark}")
    if not any(str(key) == "EDP-TSV" for key, _ in rows):
        print("    ** `EDP-TSV` 가 없다. 이대로 재이관하면 또 0행이 된다. **")
    print()


def _product_name_drift(connection: duckdb.DuckDBPyConnection) -> None:
    print("2) `제품정보` 표기 어긋남 — 원천과 파생이 다른 제품이 있으면 조인이 빗나간다")
    drifted = _scalar(
        connection,
        'SELECT count(*) FROM (SELECT DISTINCT "제품정보" FROM raw_data.core_data '
        f'WHERE "제품정보" IS NOT NULL AND "제품정보" <> {NORMALIZED_PRODUCT})',
    )
    total = _scalar(
        connection,
        'SELECT count(DISTINCT "제품정보") FROM raw_data.core_data WHERE "제품정보" IS NOT NULL',
    )
    print(f"    원천 제품 {total:,}종 중 정리하면 이름이 달라지는 것 {drifted:,}종")
    if drifted:
        print("    ** 0 이 아니다. 원천 이름으로 맞대는 조인은 그 제품에서 빗나간다 —")
        print("       재이관 SQL 이 파생과 같은 규칙으로 줄여서 조인해야 한다. **")
    orphan = _scalar(
        connection,
        'SELECT count(*) FROM ref_data.rq_pkg_plan WHERE "제품타입" IS NULL',
    )
    print(f"    `rq_pkg_plan.제품타입` 이 비어 있는 행 {orphan:,}개 (0013 백필이 놓친 자리)")
    print()


def _conflicting_types(connection: duckdb.DuckDBPyConnection) -> None:
    print("3) 제품 단위 판별이 위험한 자리 — 있으면 HBM 행까지 끌려간다")
    mixed = _scalar(
        connection,
        'SELECT count(*) FROM (SELECT dataset_id, "제품정보" FROM ref_data.rq_pkg_plan '
        'WHERE "제품타입" IS NOT NULL GROUP BY dataset_id, "제품정보" '
        'HAVING count(DISTINCT upper(trim("제품타입"))) > 1)',
    )
    print(f"    한 데이터셋 안에서 `제품타입` 이 갈리는 제품 {mixed:,}종")
    unset = _scalar(
        connection,
        'SELECT count(*) FROM raw_data.core_data WHERE "제품타입" IS NULL',
    )
    print(f"    원천에 `제품타입` 이 비어 있는 행 {unset:,}개")
    if mixed or unset:
        print("    ** 0 이 아니다. 재이관이 제품 단위로 판별하면 그 제품의 HBM 행도 바뀐다 —")
        print("       가드를 두 UPDATE 에 모두 걸어야 한다. **")
    print()


def _would_change(connection: duckdb.DuckDBPyConnection) -> None:
    print("4) 재이관이 실제로 바꿀 행 수 (모의 계산 — 아무것도 쓰지 않는다)")
    grand = 0
    for schema, scope in (("ref_data", "dataset_id"), ("rev_data", "revision_id")):
        for table in TABLES:
            count = _scalar(
                connection,
                f"SELECT count(*) FROM {schema}.{table} AS target WHERE "
                f"upper(trim(target.\"WF 구분\")) = 'TOP' AND EXISTS ("
                f"  SELECT 1 FROM {schema}.rq_pkg_plan AS plan"
                f"  WHERE plan.{scope} = target.{scope}"
                f'    AND plan."제품정보" = target."제품정보"'
                f'    AND plan."제품타입" IS NOT NULL'
                f'  GROUP BY plan.{scope}, plan."제품정보"'
                f'  HAVING count(DISTINCT upper(trim(plan."제품타입"))) = 1'
                f"     AND min(upper(trim(plan.\"제품타입\"))) = 'EDP-TSV')",
            )
            grand += count
            print(f"    {schema}.{table:14} {count:>10,}행")
        print()
    print(f"    합계 {grand:,}행이 `TOP` 에서 `Top_e` 로 바뀐다")
    if grand == 0:
        print("    0 이다. 로컬 합성 DB 에서는 정상이다 — 남은 `TOP` 이 HBM 제품이고 EDP 는")
        print("    이미 `0014` 가 바꿨기 때문이다. **사내에서 0 이면 전제가 틀린 것이므로**")
        print("    재이관 SQL 을 쓰지 말고 1~3 번 결과를 먼저 본다.")
    print()


def main() -> int:
    if not DUCKDB_PATH.exists():
        print(f"DB 파일이 없습니다: {DUCKDB_PATH}")
        return 1
    try:
        connection = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    except duckdb.Error as exc:
        print("DB 를 열지 못했습니다. 앱이 떠 있으면 먼저 끄세요 — DuckDB 는 배타 잠금입니다.")
        print(f"  {str(exc).splitlines()[0]}")
        return 1

    print(f"파일 {DUCKDB_PATH}")
    print("재이관 전제 점검 — 읽기만 하고 제품명·고객명은 찍지 않는다\n")
    try:
        _product_type_shapes(connection)
        _product_name_drift(connection)
        _conflicting_types(connection)
        _would_change(connection)
    finally:
        connection.close()

    print("네 항목을 그대로 리뷰 문서에 옮긴다. 이 결과를 보고 사외가 재이관 SQL 을 쓴다.")
    print("**여기서 고치지 않는다** — 리비전은 append-only 이고, 되돌릴 수 없는 변경이다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
