# Purpose: 원천에 보존된 기존 결과와 신규 계산값을 대조해 요약과 상세 CSV 를 만든다.

"""기존 앱 결과와 이 앱의 계산을 맞춰 본다.

신규 계산을 실제 업무 판단에 쓰기 전 마지막 관문이다. `raw_data.core_data` 에 기존
결과 컬럼이 그대로 남아 있으므로 별도 테이블 없이 대조할 수 있다.

    .venv\\Scripts\\python.exe scripts\\compare_legacy_results.py
    .venv\\Scripts\\python.exe scripts\\compare_legacy_results.py --output data/output/legacy.csv

기본은 최신 공식 리비전의 데이터셋을 쓴다. `--dataset-id` 로 다른 데이터셋을 고를 수 있다.
읽기 전용으로 열기 때문에 앱이 떠 있어도 안전하다 — 는 것은 사실이 아니다. DuckDB 는
같은 파일에 모드가 다른 연결을 허용하지 않으므로 **앱을 끄고 실행한다.**
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capa_simulation.services.legacy_comparison import (  # noqa: E402
    COMPARISONS,
    compare_metric,
    summarize_comparison,
)
from capa_simulation.services.load_calculator import (  # noqa: E402
    calculate_density_load,
    calculate_wafer_load,
)
from capa_simulation.settings import DUCKDB_PATH  # noqa: E402

# 기존 결과 컬럼과 신규 계산에 필요한 입력을 함께 뽑는다.
_CORE_QUERY = """
    SELECT * FROM raw_data.core_data WHERE dataset_id = ?
"""


def _latest_dataset_id(connection: duckdb.DuckDBPyConnection) -> str:
    row = connection.execute(
        """
        SELECT dataset_id FROM app_meta.dataset ORDER BY imported_at DESC LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise SystemExit("데이터셋이 없습니다. 먼저 시나리오를 등록하세요.")
    return str(row[0])


_NEEDED_TABLES = {
    "rq_pkg_plan": "RQ_PKG_PLAN",
    "rq_yld": "RQ_YLD",
    "rq_chip_qty": "RQ_CHIP_QTY",
    "rq_chip_eq": "RQ_CHIP_EQ",
}


def _tables_for(connection: duckdb.DuckDBPyConnection, dataset_id: str) -> dict[str, pd.DataFrame]:
    """기술 키를 뺀 RQ 프레임을 계산 서비스가 받는 형태로 돌려준다."""
    tables: dict[str, pd.DataFrame] = {}
    for physical, logical in _NEEDED_TABLES.items():
        query = (
            "SELECT * EXCLUDE (dataset_id, source_row_no) "
            f"FROM ref_data.{physical} WHERE dataset_id = ?"
        )
        tables[logical] = connection.execute(query, [dataset_id]).fetch_df()
    return tables


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(DUCKDB_PATH), help="시뮬레이션 DuckDB 경로")
    parser.add_argument("--dataset-id", default=None, help="비우면 가장 최근 데이터셋")
    parser.add_argument("--output", default=None, help="상세 대조 결과를 저장할 CSV 경로")
    parser.add_argument("--tolerance", type=float, default=0.005, help="허용 차이율")
    args = parser.parse_args()

    connection = duckdb.connect(args.database, read_only=True)
    try:
        dataset_id = args.dataset_id or _latest_dataset_id(connection)
        core = connection.execute(_CORE_QUERY, [dataset_id]).fetch_df()
        tables = _tables_for(connection, dataset_id)
    finally:
        connection.close()

    if core.empty:
        raise SystemExit(f"데이터셋 {dataset_id} 의 원천 행이 없습니다.")

    calculated = {
        "WF수(매)": calculate_wafer_load(
            tables["RQ_PKG_PLAN"], tables["RQ_YLD"], tables["RQ_CHIP_QTY"]
        ),
        "EQ(억Gb)": calculate_density_load(tables["RQ_PKG_PLAN"], tables["RQ_CHIP_EQ"]),
    }

    print(f"데이터셋 {dataset_id} · 원천 {len(core):,}행")
    frames: list[pd.DataFrame] = []
    for metric in COMPARISONS:
        comparison = compare_metric(core, calculated[metric.legacy_column], metric)
        summary = summarize_comparison(comparison, tolerance=args.tolerance)
        frames.append(comparison)
        rate = summary["최대 차이율"]
        print(
            f"\n[{metric.label}]"
            f"\n  대조 {summary['대조 건수']:,}건 · 허용 초과 {summary['허용 초과']:,}건"
            f" · 최대 차이율 {'-' if rate is None else f'{rate:.4%}'}"
            f"\n  신규에만 있음 {summary['신규에만 있음']:,}건 (기존이 비워 둔 자리를 채운다)"
            f" · 기존에만 있음 {summary['기존에만 있음']:,}건 (신규가 놓친 자리)"
        )
        worst = comparison.dropna(subset=["차이율"]).nlargest(5, "차이율")
        if not worst.empty and float(worst["차이율"].iloc[0]) > args.tolerance:
            print(worst.to_string(index=False))

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        pd.concat(frames, ignore_index=True).to_csv(output, index=False, encoding="utf-8-sig")
        print(f"\n상세 결과: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
