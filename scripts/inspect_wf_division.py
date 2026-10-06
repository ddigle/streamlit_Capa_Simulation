# Purpose: 저장된 기준정보·리비전의 `WF 구분` 값 분포를 읽기 전용으로 세어 보고한다.

"""`Top` 이관이 실제로 어디까지 걸렸는지 사내에서 확인하는 도구.

마이그레이션 `0013`·`0014` 는 `trim("WF 구분") = 'Top'` 으로 비교하는데 **원천 표기는
대문자 `TOP`** 이다. 적용된 마이그레이션은 버전 번호로 체크섬을 대조하므로 고칠 수 없고,
그래서 이미 저장된 리비전에 `Top_e` 가 얼마나 들어갔는지는 실데이터를 봐야만 안다.

**이 스크립트는 읽기만 한다.** `read_only=True` 로 열어 쓰기 경로를 아예 막았다. 사내에서
SQL 로 직접 고치는 것을 막으려는 것이다 — 리비전은 append-only 이고, 재이관이 필요하면
사외가 후속 마이그레이션을 만든다.

**값을 화면에 찍지 않는다.** `WF 구분` 값 자체가 실데이터이므로, 세어야 할 것(`Top`·`Top_e`
꼴)만 따로 세고 나머지는 **개수만** 보고한다. 리뷰 문서는 사내에서 사외로 나가는 유일한
것이라 여기서 값이 새면 그대로 밖으로 나간다.

**소요기준 PKG 절.** PKG 기준 소요대수는 `RQ_REQB` 의 Buffer 행에만 붙는다(2026-09-28).
EDP-TSV 제품의 PKG 행이 어떤 WF 구분을 싣는지는 사외가 모른다 — Buffer 가 아니면 그 행은
제외 목록으로 간다. 그래서 PKG 행을 제품타입별로 나눠 이미 코드에 적힌 분류명만 따로 세고,
나머지는 개수만 센다.

`ref_data` 는 데이터셋 단위, `rev_data` 는 리비전 단위다. 2026-10-06 사용자 결정(B3) 뒤 만든
데이터셋은 리비전 표(이 스크립트가 보는 표 전부)를 **`rev_data` 에만** 적고 `ref_data` 에는 사본이
없다 — 그 데이터셋의 값은 `ref_data` 줄에 들어가지 않는다. 출력 첫머리에 사본이 있는 데이터셋 수를
함께 찍는다.

사용:

    uv run --no-sync python scripts/inspect_wf_division.py
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

# `0013`·`0014` 가 `WF 구분` 을 건드린 표. 두 스키마에 같은 이름으로 있다.
# `rq_pkg_plan` 은 뺀다 — 0013 이 EDP 행을 가려내려고 **읽기만** 할 뿐 그 표에는
# `WF 구분` 컬럼 자체가 없다.
TABLES: tuple[str, ...] = (
    "rq_chip_eq",
    "rq_chip_qty",
    "rq_lot_ratio",
    "rq_reqb",
    "rq_upeh",
    "rq_wf_ratio",
    "rq_yld",
)
SCHEMAS: tuple[str, ...] = ("ref_data", "rev_data")

# 세어야 할 것만 이름으로 가른다. 그 밖의 값은 개수만 센다 — 값이 곧 실데이터다.
WATCHED: tuple[str, ...] = ("TOP", "TOP_E")

# PKG 절에서 따로 세는 이름. 모두 `services/product_type.py` 에 이미 적힌 분류명이다.
PKG_WATCHED: tuple[str, ...] = ("BUFFER", "CORE", "TOP", "TOP_E", "DUMMY", "MASTER", "SLAVE")
PRODUCT_TYPES: tuple[str, ...] = ("HBM", "EDP-TSV")


def _ref_data_coverage(connection: duckdb.DuckDBPyConnection) -> None:
    """`ref_data` 에 리비전 표 사본이 있는 데이터셋 수. 결정 B3 뒤 만든 데이터셋은 사본이 없다."""
    try:
        total = connection.execute("SELECT count(*) FROM app_meta.dataset").fetchone()
        covered = connection.execute(
            "SELECT count(DISTINCT dataset_id) FROM ref_data.rq_pkg_plan"
        ).fetchone()
    except duckdb.Error as exc:
        print(f"ref_data 사본 범위를 읽지 못함 — {str(exc).splitlines()[0]}\n")
        return
    total_count = int(total[0]) if total and total[0] is not None else 0
    covered_count = int(covered[0]) if covered and covered[0] is not None else 0
    print(
        f"ref_data 에 리비전 표 사본이 있는 데이터셋 {covered_count:,} / 전체 {total_count:,} — "
        "나머지는 사본 없이 rev_data(리비전)에만 있다(2026-10-06 결정 B3 뒤 만든 데이터셋)\n"
    )


def _counts(connection: duckdb.DuckDBPyConnection, schema: str, table: str) -> str:
    try:
        rows = connection.execute(
            f'SELECT upper(trim("WF 구분")) AS k, count(*) FROM {schema}.{table} GROUP BY 1'
        ).fetchall()
    except duckdb.Error as exc:
        first_line = str(exc).splitlines()[0] if str(exc).strip() else exc.__class__.__name__
        return f"    {schema}.{table:14} 읽지 못함 — {first_line}"

    watched = {key: 0 for key in WATCHED}
    other_values = 0
    other_rows = 0
    for key, count in rows:
        name = str(key or "")
        if name in watched:
            watched[name] = int(count)
        else:
            other_values += 1
            other_rows += int(count)
    summary = " · ".join(f"{key}={watched[key]:,}" for key in WATCHED)
    return f"    {schema}.{table:14} {summary} · 그 밖 {other_values}종 {other_rows:,}행"


def _pkg_counts(connection: duckdb.DuckDBPyConnection, schema: str) -> list[str]:
    """소요기준 PKG 인 `RQ_REQB` 행을 제품타입 × WF 구분으로 센다.

    제품타입은 `RQ_PKG_PLAN` 에서 제품정보로 붙인다(`RQ_REQB` 에는 없다). 한 제품의 비지 않은
    제품타입이 하나로 모일 때만 그 값을 쓴다(`0026` 과 같은 규칙). 빈 타입뿐이면 `빈 타입`,
    둘 이상이면 `타입 갈림`, 계획에 없는 제품은 `계획에 없음` 으로 따로 센다 — `any_value` 로
    하나를 고르면 빈 문자열이 뽑혀 EDP-TSV 행이 EDP-TSV 줄에서 빠진다.

    `rev_data` 는 모든 리비전의 행을 더한 수다.
    """
    try:
        rows = connection.execute(
            f"""
            WITH types AS (
                SELECT "제품정보",
                    CASE count(DISTINCT upper(trim("제품타입")))
                            FILTER (WHERE trim(coalesce("제품타입", '')) <> '')
                        WHEN 1 THEN max(upper(trim("제품타입")))
                            FILTER (WHERE trim(coalesce("제품타입", '')) <> '')
                        WHEN 0 THEN '빈 타입'
                        ELSE '타입 갈림'
                    END AS t
                FROM {schema}.rq_pkg_plan GROUP BY 1
            )
            SELECT coalesce(types.t, '계획에 없음') AS t, upper(trim(r."WF 구분")) AS k, count(*)
            FROM {schema}.rq_reqb AS r LEFT JOIN types USING ("제품정보")
            WHERE upper(trim(r."소요기준")) = 'PKG'
            GROUP BY 1, 2
            """
        ).fetchall()
    except duckdb.Error as exc:
        first_line = str(exc).splitlines()[0] if str(exc).strip() else exc.__class__.__name__
        return [f"    {schema}  읽지 못함 — {first_line}"]
    if not rows:
        return [f"    {schema}  소요기준 PKG 행 없음"]

    by_type: dict[str, dict[str, int]] = {}
    for product_type, key, count in rows:
        known = (*PRODUCT_TYPES, "빈 타입", "타입 갈림", "계획에 없음")
        name = str(product_type) if product_type in known else "그 밖 제품타입"
        bucket = by_type.setdefault(name, {})
        division = str(key or "")
        label = division if division in PKG_WATCHED else "_other"
        bucket[label] = bucket.get(label, 0) + int(count)
        if label == "_other":
            bucket["_other_kinds"] = bucket.get("_other_kinds", 0) + 1
    lines = []
    for name, bucket in by_type.items():
        watched = " · ".join(f"{key}={bucket[key]:,}" for key in PKG_WATCHED if bucket.get(key))
        other = (
            f" · 그 밖 {bucket['_other_kinds']}종 {bucket['_other']:,}행"
            if "_other" in bucket
            else ""
        )
        lines.append(f"    {schema}  {name:10} {watched or '(따로 세는 이름 없음)'}{other}")
    return lines


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
    print("`WF 구분` 값 분포 (대문자로 모아서 셈, 값은 찍지 않음)\n")
    try:
        _ref_data_coverage(connection)
        for schema in SCHEMAS:
            for table in TABLES:
                print(_counts(connection, schema, table))
            print()
        print("소요기준 PKG 인 `RQ_REQB` 행의 WF 구분 (제품타입별)")
        print()
        for schema in SCHEMAS:
            for line in _pkg_counts(connection, schema):
                print(line)
        print()
    finally:
        connection.close()

    print("읽는 법 — `TOP_E` 가 0 이 아니면 그 표에는 이관이 걸렸다는 뜻이다.")
    print("`TOP` 이 남아 있으면 대소문자 때문에 건너뛴 행이다. 두 숫자를 리뷰 문서에 적는다.")
    print("PKG 절 — PKG 소요대수는 BUFFER 행에만 붙는다. EDP-TSV 줄에 BUFFER 가 아닌 값이")
    print("있으면 그 행은 제외 목록으로 간다. PKG 절 출력을 그대로 리뷰 문서에 옮긴다.")
    print("**여기서 고치지 않는다.** 재이관은 사외가 후속 마이그레이션으로 만든다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
