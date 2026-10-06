# Purpose: `0026` 적용 뒤 이관 결과가 맞는지 — 오염·누락·재고 출처를 읽기 전용으로 잰다.

"""`0026` 이 예측보다 많이 바꾼 것처럼 보일 때 **무엇을 잰 것인지** 가른다.

2026-09-23 사내 리뷰가 예측 40,516행 대비 실제 44,527행(+9.9%)을 보고했다. 두 수는
**서로 다른 것을 센다.**

- `inspect_top_remigration.py` 4번은 **유량**이다 — 지금 `TOP` 이면서 이관 대상인 행 수.
- `inspect_wf_division.py` 는 **재고**다 — 지금 `Top_e` 인 모든 행 수. 그 안에는 `0026`
  이 바꾼 행뿐 아니라 **파생이 처음부터 `Top_e` 로 만든 행**도 들어 있다.

파생(`services/product_type.apply_edp_wf_division`)은 대소문자를 가리지 않게 고쳐진 뒤로
운영에서도 동작한다. 그래서 그 고침이 실린 뒤에 적재한 데이터셋과 그 뒤에 저장한 리비전은
`0026` 과 무관하게 이미 `Top_e` 다. 재고에서 유량을 빼면 그 몫이 남는다.

**두 조건이 다른 것은 아니다.** `0026` 의 두 UPDATE 와 점검 스크립트의 예측식이 같은 행을
잡는 것은 사외에서 합성 DB 로 확인했다 — 원천 형태로만 걸리는 제품·정규화가 필요한 이름·
NBSP·타입 갈림·빈 타입을 모두 태워 14개 표 전부 예측과 실제가 같았다.

그러니 여기서 재야 하는 것은 「몇 행이 바뀌었나」가 아니라 **「잘못 바뀐 행이 있나」**다.
되돌릴 수 없는 것은 그것 하나다.

1. **오염** — `Top_e` 인데 EDP-TSV 로 판별되지 않는 행. **0 이어야 한다.**
2. **누락** — 아직 `TOP` 인데 이관 대상인 행. `0026` 은 멱등이므로 **0 이어야 한다.**
3. **재고 출처** — 데이터셋·리비전별 `Top_e` 개수와 그 생성 시각. 초과분이 최근에 만들어진
   쪽에 몰려 있으면 파생이 만든 것이다.

**읽기만 한다.** `read_only=True` 로 열고 제품명·고객명은 찍지 않는다 — 개수와 시각만이다.

`ref_data` 는 데이터셋 단위, `rev_data` 는 리비전 단위다. 2026-10-06 사용자 결정(B3) 뒤 만든
데이터셋은 리비전 표를 **`rev_data` 에만** 적고 `ref_data` 에는 사본이 없다 — 그 데이터셋은
`ref_data` 줄에서 0 이고 3번 재고 출처의 데이터셋 목록에도 나오지 않는다. 출력 첫머리에 사본이
있는 데이터셋 수를 함께 찍는다.

사용:

    uv run --no-sync python scripts/audit_top_remigration.py
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

TABLES: tuple[str, ...] = (
    "rq_chip_eq",
    "rq_chip_qty",
    "rq_lot_ratio",
    "rq_reqb",
    "rq_upeh",
    "rq_wf_ratio",
    "rq_yld",
)
SCOPES: tuple[tuple[str, str], ...] = (("ref_data", "dataset_id"), ("rev_data", "revision_id"))

# `0026` 과 글자까지 같은 정규화. 갈라지면 여기서 재는 수가 뜻을 잃는다.
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


def _ref_data_coverage(connection: duckdb.DuckDBPyConnection) -> None:
    """`ref_data` 에 리비전 표 사본이 있는 데이터셋 수. 결정 B3 뒤 만든 데이터셋은 사본이 없다."""
    total = _scalar(connection, "SELECT count(*) FROM app_meta.dataset")
    covered = _scalar(connection, "SELECT count(DISTINCT dataset_id) FROM ref_data.rq_pkg_plan")
    print(
        f"ref_data 에 리비전 표 사본이 있는 데이터셋 {covered:,} / 전체 {total:,} — "
        "나머지는 사본 없이 rev_data(리비전)에만 있다(2026-10-06 결정 B3 뒤 만든 데이터셋)"
    )
    print()


def _edp_source_products() -> str:
    """`0026` 의 `_edp_source_products` 뷰와 같은 조건."""
    return (
        f"SELECT {NORMALIZED_PRODUCT} AS p FROM raw_data.core_data "
        'WHERE "제품타입" IS NOT NULL AND trim("제품타입") <> \'\' '
        "GROUP BY 1 "
        'HAVING count(DISTINCT upper(trim("제품타입"))) = 1 '
        "   AND min(upper(trim(\"제품타입\"))) = 'EDP-TSV'"
    )


def _edp_plan_products(schema: str, scope: str) -> str:
    """`0026` 의 `_edp_plan_products` 뷰와 같은 조건."""
    return (
        f'SELECT {scope} AS s, "제품정보" AS p FROM {schema}.rq_pkg_plan '
        'WHERE "제품타입" IS NOT NULL AND trim("제품타입") <> \'\' '
        f'GROUP BY {scope}, "제품정보" '
        'HAVING count(DISTINCT upper(trim("제품타입"))) = 1 '
        "   AND min(upper(trim(\"제품타입\"))) = 'EDP-TSV'"
    )


def _is_edp(schema: str, scope: str) -> str:
    """`0026` 의 두 형태 중 하나라도 EDP 로 판별하는가."""
    return (
        f'(t."제품정보" IN (SELECT p FROM ({_edp_source_products()})) '
        f"OR EXISTS (SELECT 1 FROM ({_edp_plan_products(schema, scope)}) AS pl "
        f'  WHERE pl.s = t.{scope} AND pl.p = t."제품정보"))'
    )


def _contamination(connection: duckdb.DuckDBPyConnection) -> int:
    print("1) 오염 — `Top_e` 인데 EDP-TSV 로 판별되지 않는 행 (0 이어야 한다)")
    total = 0
    for schema, scope in SCOPES:
        for table in TABLES:
            count = _scalar(
                connection,
                f"SELECT count(*) FROM {schema}.{table} AS t "
                "WHERE upper(trim(t.\"WF 구분\")) = 'TOP_E' "
                f"AND NOT {_is_edp(schema, scope)}",
            )
            total += count
            mark = "" if count == 0 else "   <<< 확인 필요"
            print(f"    {schema}.{table:14} {count:>8,}행{mark}")
    print()
    if total:
        print(f"    ** 합계 {total:,}행. 이 행들이 왜 `Top_e` 인지 사외가 판단해야 한다. **")
        print("       파생이 만든 것일 수도 있고(그때는 원천 `제품타입` 이 그 사이 바뀐 것)")
        print("       이관이 잘못 잡은 것일 수도 있다. **리뷰 문서에 그대로 옮긴다.**")
    else:
        print("    0 이다. **잘못 바뀐 행은 없다** — 되돌릴 수 없는 피해가 없다는 뜻이다.")
    print()
    return total


def _leftover(connection: duckdb.DuckDBPyConnection) -> int:
    print("2) 누락 — 아직 `TOP` 인데 이관 대상인 행 (0 이어야 한다)")
    total = 0
    for schema, scope in SCOPES:
        for table in TABLES:
            count = _scalar(
                connection,
                f"SELECT count(*) FROM {schema}.{table} AS t "
                "WHERE upper(trim(t.\"WF 구분\")) = 'TOP' "
                f"AND {_is_edp(schema, scope)}",
            )
            total += count
            mark = "" if count == 0 else "   <<< 안 바뀐 행"
            print(f"    {schema}.{table:14} {count:>8,}행{mark}")
    print()
    if total:
        print(f"    ** 합계 {total:,}행이 남았다. `0026` 이 다 훑지 못했다는 뜻이다. **")
    else:
        print("    0 이다. 대상이 전부 바뀌었고 다시 돌려도 바뀔 것이 없다(멱등).")
    print()
    return total


def _stock_origin(connection: duckdb.DuckDBPyConnection) -> None:
    print("3) 재고 출처 — `Top_e` 를 만든 데이터셋·리비전과 그 생성 시각")
    print("   최근에 만들어진 쪽에 몰려 있으면 파생이 만든 몫이다(이관과 무관하다).")
    print()
    print("  ref_data (데이터셋별, `rq_upeh` 기준)")
    rows = _rows(
        connection,
        "SELECT t.dataset_id, count(*) AS n, max(d.imported_at) AS last_at "
        "FROM ref_data.rq_upeh AS t LEFT JOIN app_meta.dataset AS d USING (dataset_id) "
        "WHERE upper(trim(t.\"WF 구분\")) = 'TOP_E' "
        "GROUP BY 1 ORDER BY last_at ASC NULLS FIRST",
    )
    for dataset_id, count, imported_at in rows:
        stamp = str(imported_at)[:19] if imported_at is not None else "(시각 없음)"
        print(f"    {str(dataset_id)[:12]:14} {int(count):>8,}행   적재 {stamp}")
    print()
    print("  rev_data (리비전별, `rq_upeh` 기준)")
    rows = _rows(
        connection,
        "SELECT t.revision_id, count(*) AS n, max(r.created_at) AS last_at "
        "FROM rev_data.rq_upeh AS t LEFT JOIN app_meta.scenario_revision AS r USING (revision_id) "
        "WHERE upper(trim(t.\"WF 구분\")) = 'TOP_E' "
        "GROUP BY 1 ORDER BY last_at ASC NULLS FIRST",
    )
    for revision_id, count, created_at in rows:
        stamp = str(created_at)[:19] if created_at is not None else "(시각 없음)"
        print(f"    {str(revision_id)[:12]:14} {int(count):>8,}행   생성 {stamp}")
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
    print("`0026` 적용 뒤 감사 — 읽기만 하고 제품명·고객명은 찍지 않는다\n")
    try:
        _ref_data_coverage(connection)
        contaminated = _contamination(connection)
        leftover = _leftover(connection)
        _stock_origin(connection)
    finally:
        connection.close()

    print("세 항목을 그대로 리뷰 문서에 옮긴다.")
    if contaminated == 0 and leftover == 0:
        print("1·2 번이 모두 0 이면 **이관은 정확했다.** 예측과 재고의 차이는 파생이 만든")
        print("몫이고, 3번의 시각이 그것을 보여 준다. 후속 마이그레이션은 필요 없다.")
    else:
        print("**사내에서 SQL 로 고치지 않는다** — 리비전은 append-only 다. 출력을 보내면")
        print("사외가 후속 번호로 판단한다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
