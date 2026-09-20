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
        for schema in SCHEMAS:
            for table in TABLES:
                print(_counts(connection, schema, table))
            print()
    finally:
        connection.close()

    print("읽는 법 — `TOP_E` 가 0 이 아니면 그 표에는 이관이 걸렸다는 뜻이다.")
    print("`TOP` 이 남아 있으면 대소문자 때문에 건너뛴 행이다. 두 숫자를 리뷰 문서에 적는다.")
    print("**여기서 고치지 않는다.** 재이관은 사외가 후속 마이그레이션으로 만든다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
