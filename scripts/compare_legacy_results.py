# Purpose: 원천에 보존된 기존 결과와 신규 계산값을 대조해 요약과 상세 CSV 를 만든다.

"""기존 앱 결과와 이 앱의 계산을 맞춰 본다.

    .venv\Scripts\python.exe scripts\compare_legacy_results.py
    .venv\Scripts\python.exe scripts\compare_legacy_results.py --output data/output/legacy.csv

기본은 가장 최근 데이터셋을 쓴다. `--dataset-id` 로 다른 데이터셋을 고를 수 있다.
DuckDB 는 같은 파일에 모드가 다른 연결을 허용하지 않으므로 **앱을 끄고 실행한다.**

읽어 온 원시 행은 `build_q_core_data` 로 파생 프레임을 만든 뒤에 대조에 넘긴다.
기존 결과를 접는 단위가 `RQ_PKG_PLAN` 업무 키인데 그 키의 `양산구분` 이 파생 단계에서
만들어지기 때문이다.

매 실행마다 **대조 후보 컬럼의 채움 상태**를 먼저 찍는다. 지금 로컬 샘플은 `소요대수` 가
비어 있어 두 지표만 대조하지만, 그것은 업무 사실이 아니라 합성 샘플의 사정이다. 실데이터가
들어와 값이 차면 이 진단이 사람보다 먼저 알려 준다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capa_simulation.io.core_data_source import load_core_data_contract  # noqa: E402
from capa_simulation.services.core_data_derivation import build_q_core_data  # noqa: E402
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

# 기존 앱 결과가 실려 오는 컬럼. 지금 대조하지 않는 것도 채움 상태만은 매번 확인한다.
_LEGACY_CANDIDATES = (
    "WF수(매)",
    "EQ(억Gb)",
    "소요대수",
    "PCB수(K매)",
    "Plan_Chip(K개)",
    "GOOD_DIE",
)

_NEEDED_TABLES = {
    "rq_pkg_plan": "RQ_PKG_PLAN",
    "rq_yld": "RQ_YLD",
    "rq_chip_qty": "RQ_CHIP_QTY",
    "rq_chip_eq": "RQ_CHIP_EQ",
}


def _latest_dataset_id(connection: duckdb.DuckDBPyConnection) -> str:
    row = connection.execute(
        "SELECT dataset_id FROM app_meta.dataset ORDER BY imported_at DESC LIMIT 1"
    ).fetchone()
    if row is None:
        raise SystemExit("데이터셋이 없습니다. 먼저 시나리오를 등록하세요.")
    return str(row[0])


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


def _report_candidate_columns(raw: pd.DataFrame) -> None:
    """기존 결과 컬럼이 실제로 채워져 있는지 매번 보여 준다.

    파생 프레임이 아니라 **원시 78컬럼**을 본다. `PCB수(K매)` 처럼 파생이 떨어뜨리는
    컬럼도 원천에는 있으므로, 파생 쪽만 보면 "컬럼 없음" 으로 잘못 읽는다.
    """
    print("\n[기존 결과 컬럼 채움 상태]")
    for column in _LEGACY_CANDIDATES:
        if column not in raw.columns:
            print(f"  {column:<14} 원천에 컬럼 없음")
            continue
        values = pd.to_numeric(raw[column], errors="coerce")
        filled = int(values.notna().sum())
        note = " ← 비어 있어 대조 불가" if filled == 0 else ""
        print(f"  {column:<14} 값 {filled:>7,}/{len(raw):,} · 고유값 {values.nunique():>5,}{note}")


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
        raw = connection.execute(
            "SELECT * EXCLUDE (dataset_id, source_row_no, row_hash) "
            "FROM raw_data.core_data WHERE dataset_id = ?",
            [dataset_id],
        ).fetch_df()
        tables = _tables_for(connection, dataset_id)
    finally:
        connection.close()

    if raw.empty:
        raise SystemExit(f"데이터셋 {dataset_id} 의 원천 행이 없습니다.")

    contract = load_core_data_contract()
    core = build_q_core_data(raw, contract)

    calculated = {
        "WF수(매)": calculate_wafer_load(
            tables["RQ_PKG_PLAN"], tables["RQ_YLD"], tables["RQ_CHIP_QTY"]
        ),
        "EQ(억Gb)": calculate_density_load(tables["RQ_PKG_PLAN"], tables["RQ_CHIP_EQ"]),
    }

    print(f"데이터셋 {dataset_id} · 원천 {len(core):,}행")
    _report_candidate_columns(raw)

    frames: list[pd.DataFrame] = []
    for metric in COMPARISONS:
        comparison = compare_metric(core, calculated[metric.legacy_column], metric, contract)
        summary = summarize_comparison(comparison, tolerance=args.tolerance)
        frames.append(comparison)
        rate = summary["최대 차이율"]
        print(
            f"\n[{metric.label}]"
            f"\n  대조 {summary['대조 건수']:,}건 · 허용 초과 {summary['허용 초과']:,}건"
            f" · 최대 차이율 {'-' if rate is None else f'{rate:.4%}'}"
            f"\n  기존 0·신규 있음 {summary['기존 0·신규 있음']:,}건 (비율을 구할 수 없다)"
            f" · 값 불일치 {summary['값 불일치']:,}건 (기존 쪽을 접을 수 없어 뺐다)"
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
