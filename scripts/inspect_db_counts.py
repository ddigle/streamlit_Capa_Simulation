# Purpose: 두 DB 의 표 행 수 · 모듈 묶음 · 파일 크기와 생산 계획 편집 표 크기를 읽기만 해 센다.

"""런북 7-8 의 개수 세기 — 사내에서는 사용자가 Claude 밖의 별도 PowerShell 창에서 앱을 끈 뒤
돌리고, 사내 에이전트는 `--output` 파일만 읽어 옮긴다(런북 0장 — 에이전트는 사내 DB 를 여는
명령을 치지 않는다).

    uv run --no-sync python scripts/inspect_db_counts.py --output $HOME\\db_counts.md

예전 7-8 은 `python -c` 긴 줄 셋(한 줄 1,000 ~ 2,700자)이라 사용자 창에 붙이면 줄바꿈으로 깨질 수
있고 결과 파일이 없었다(2026-11-12 사용자 답 ②-1 (가) — 짧은 스크립트로). 그 셋의 출력은 **글자
그대로** 둔다 — 7장의 기대 줄과 지난 리뷰의 값이 그 꼴이다. 넷째 줄은 생산 계획 그리드 두
표(PKG PLAN · 수율)의 크기다(2026-11-12 사용자 답 ③-7 (가) — 큰 표 상한을 둘지 실제 크기를 보고
정한다).

| 줄 | `--only` | 무엇을 |
|---|---|---|
| 1 | `counts` | 두 DB 의 마이그레이션 번호와 표마다 행 수(없는 표는 `None`) |
| 2 | `bundles` | 최신 설비 리비전의 Space 모듈 묶음 — 모듈 수 · 상자 · 바둑판 |
| 3 | `sizes` | 두 DB 파일 크기 · 블록 · `.wal` · gzip 크기 · 블록이 많은 표 여섯 |
| 4 | `plan` | 생산 계획 PKG PLAN · 수율 그리드 양식의 줄 · 달 · 칸 수와 본문 바이트의 최대 |

**지키는 것 셋** — 실데이터 확인(`inspect_real_data_checks.py`)과 같다.

- **앱을 끄고 돌린다.** 운영 DB 자리(`settings.is_operational_database_place`)를 열면 사용자 앱
  프로세스를 먼저 보고, 보이면 DB 를 열지 않고 멈춘다(코드 1). `--database` · `--equipment-database`
  로 사본만 주면 앱을 보지 않는다(런북 6-4 「사본 받기」).
- **읽기만 한다.** 두 DB 를 `read_only=True` 로 연다. 저장소(Repository)를 만들지 않는다.
- **값을 찍지 않는다.** 수 · 크기와 코드가 정한 표 이름만 찍는다 — 제품 · 공정 · 설비 이름, 좌표,
  층 번호, 경로, 예외 문구는 찍지 않는다(실패는 예외 종류 이름만). 출력은 리뷰를 거쳐 사외로 나간다.

**`--output` 은 같은 출력을 UTF-8 파일에도 쓴다**(먼저 비우고 줄마다 비운다 — 멈춰도 앞 줄이
남는다). PowerShell 5.1 의 `>` 는 콘솔 코드페이지로 읽어 한글을 깨뜨린다.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import zlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TextIO, cast

import duckdb
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capa_simulation.persistence._sql_helpers import load_frame  # noqa: E402
from capa_simulation.persistence.repository import REVISION_TABLES  # noqa: E402
from capa_simulation.services.edit_grid import GridSpec, ValueFormat  # noqa: E402
from capa_simulation.services.edit_grid_payload import build_base  # noqa: E402
from capa_simulation.services.load_calculator import (  # noqa: E402
    PLAN_EDITOR_DIMENSIONS,
    YIELD_EDITOR_DIMENSIONS,
    plan_to_edit_table,
    split_editable_yield_rows,
    yield_to_edit_table,
)
from capa_simulation.services.month_filter import (  # noqa: E402
    available_month_range,
    filter_month_range,
)
from capa_simulation.services.space_layout_edit import module_tile_deviation  # noqa: E402
from capa_simulation.services.unit_capacity import failure_kind  # noqa: E402
from capa_simulation.settings import (  # noqa: E402
    DUCKDB_PATH,
    EQUIPMENT_DUCKDB_PATH,
    is_operational_database_place,
)

LINES: Final[tuple[str, ...]] = ("counts", "bundles", "sizes", "plan")
_SIMULATION_LINES: Final = frozenset({"counts", "sizes", "plan"})
_EQUIPMENT_LINES: Final = frozenset({"counts", "bundles", "sizes"})

_APP_RUNNING_MESSAGE: Final = (
    "사용자 앱이 떠 있습니다 — DB 는 열지 않았습니다. 앱을 끈 뒤 다시 칩니다(런북 1-1)."
)
_LOCK_MESSAGE: Final = (
    "DB 를 열지 못했습니다. 앱이 떠 있으면 먼저 끄세요 — DuckDB 는 프로세스 배타 잠금입니다."
)

# 줄 1 — `ref_data` 에 남은 리비전 표 14개 사본(0 이어야 한다 — 마이그레이션 `0033`).
_REF_COPY_TABLES: Final = (
    "pkg_plan yld chip_qty chip_eq upeh run_rate vital run_day lot_ratio wf_ratio reqb "
    "eqp_own eqp_lent eqp_avbl"
).split()
_AUTO_UPDATE_TABLES: Final = (
    "global_auto_official_update",
    "auto_official_update_setting_log",
    "auto_official_update_run",
    "auto_official_update_exclusion",
)
_EQUIPMENT_SCENARIO_TABLES: Final = (
    "equipment_scenario",
    "equipment_schedule_revision",
    "equipment_official_release",
    "equipment_legacy_boundary",
)
_LAYOUT_OVERLAY_TABLES: Final = (
    "equipment_schedule_layout_unit",
    "equipment_schedule_layout_mark",
    "equipment_schedule_layout_label",
)
_MANUAL_DOWNTIME_TABLES: Final = (
    "manual_downtime_profile",
    "manual_downtime",
    "manual_downtime_save",
)
_MARK_LOOK_TABLES: Final = (
    "floor_layout_mark",
    "fab_layout_mark",
    "equipment_schedule_layout_mark",
)

# 줄 3 — 바이트 단위와 gzip 을 셀 때 한 번에 읽는 크기.
_MIB: Final = 1 << 20
_TOP_TABLES: Final = 6

# 줄 4 — 생산 계획 그리드(`components/plan_grid.py` · `app_pages/load_conversion.py`)와 같은 표
# 제목 · 값 꼴. 화면 모듈(streamlit)이라 부르지 않고 시험이 맞대 본다.
PLAN_TABLE: Final = "RQ_PKG_PLAN"
YIELD_TABLE: Final = "RQ_YLD"
PLAN_TITLE: Final = "PKG PLAN"
YIELD_TITLE: Final = "수율"
PLAN_FORMATS: Final[Mapping[str, ValueFormat]] = {
    PLAN_TABLE: ValueFormat("fixed", 0),
    YIELD_TABLE: ValueFormat("percent", 2, max_value=1.0),
}
# 실데이터 확인 8-10 · 8-11 과 같은 리비전 묶음 — 시나리오마다 활성 리비전과 공식버전 대상.
_PICKED_REVISIONS: Final = (
    "SELECT revision_id FROM app_meta.scenario_revision "
    "WHERE revision_id IN (SELECT active_revision_id FROM app_meta.scenario) "
    "OR revision_id IN (SELECT revision_id FROM app_meta.official_release) ORDER BY 1"
)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="두 DB 의 개수 · 묶음 · 크기 · 생산 계획 표 크기(읽기 전용). "
        "앱을 끈 뒤 돌린다 — 런북 7-8."
    )
    parser.add_argument(
        "--only",
        default=",".join(LINES),
        help=f"찍을 줄을 쉼표로({', '.join(LINES)}). 기본은 넷 다",
    )
    parser.add_argument(
        "--database", type=Path, default=None, help="시뮬레이션 DuckDB 사본. 비우면 운영 DB"
    )
    parser.add_argument(
        "--equipment-database", type=Path, default=None, help="설비 DuckDB 사본. 비우면 운영 DB"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="같은 출력을 이 파일에도 쓴다(UTF-8, 먼저 비운다). 저장소 밖 경로를 준다",
    )
    return parser.parse_args(argv)


class _Tee:
    """화면과 `--output` 파일에 같은 글을 쓴다 — 줄마다 비워 중간에 멈춰도 앞 줄이 남는다."""

    def __init__(self, screen: TextIO, file: TextIO) -> None:
        self._screen = screen
        self._file = file

    def write(self, text: str) -> int:
        self._screen.write(text)
        self._file.write(text)
        if "\n" in text:
            self._file.flush()
        return len(text)

    def flush(self) -> None:
        self._screen.flush()
        self._file.flush()


def main(argv: Sequence[str] | None = None) -> int:
    """`argv` 가 없으면 인자 없이 돈다(운영 DB). 명령줄에서는 `__main__` 이 `sys.argv` 를 준다."""
    args = parse_args([] if argv is None else argv)
    if args.output is None:
        return _run(args)
    with Path(args.output).open("w", encoding="utf-8", newline="\n") as file:
        with contextlib.redirect_stdout(cast(TextIO, _Tee(sys.stdout, file))):
            return _run(args)


@dataclass
class _Databases:
    simulation_path: Path
    equipment_path: Path
    simulation: duckdb.DuckDBPyConnection | None = None
    equipment: duckdb.DuckDBPyConnection | None = None

    def close(self) -> None:
        for connection in (self.simulation, self.equipment):
            if connection is not None:
                connection.close()


def _run(args: argparse.Namespace) -> int:
    selected = [name.strip() for name in str(args.only).split(",") if name.strip()]
    unknown = [name for name in selected if name not in LINES]
    if unknown or not selected:
        print(f"모르는 줄: {unknown or '(없음)'} — 고를 수 있는 것: {', '.join(LINES)}")
        return 2
    databases = _Databases(
        simulation_path=DUCKDB_PATH if args.database is None else Path(args.database),
        equipment_path=(
            EQUIPMENT_DUCKDB_PATH
            if args.equipment_database is None
            else Path(args.equipment_database)
        ),
    )
    needs_simulation = any(name in _SIMULATION_LINES for name in selected)
    needs_equipment = any(name in _EQUIPMENT_LINES for name in selected)
    targets = [
        path
        for path, needed in (
            (databases.simulation_path, needs_simulation),
            (databases.equipment_path, needs_equipment),
        )
        if needed
    ]
    # 경로는 찍지 않는다 — 이름만. 출력은 리뷰 문서로 그대로 나가는데 경로에는 사용자 폴더 이름이
    # 든다.
    missing = [path.name for path in targets if not path.exists()]
    if missing:
        print(f"DB 파일이 없습니다: {', '.join(missing)}")
        return 1
    operational = (DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH)
    if any(is_operational_database_place(path, operational) for path in targets):
        # 앱은 rerun 동안만 DB 를 쥐므로 쉬는 앱은 잠금에 안 잡힌다 — 프로세스를 먼저 본다. 판정은
        # 화면 확인 스크립트와 같은 것을 쓴다(살피지 못하면 None — 잠금만 본다).
        from check_deploy_screens import running_app_count

        if running_app_count():
            print(_APP_RUNNING_MESSAGE)
            return 1
    # 줄 3 의 gzip 은 DB 를 열기 전에 파일을 읽는다 — 예전 한 줄과 같은 차례다.
    packed = {path: _gzip_size(path) for path in targets} if "sizes" in selected else {}
    try:
        if needs_simulation:
            databases.simulation = duckdb.connect(str(databases.simulation_path), read_only=True)
        if needs_equipment:
            databases.equipment = duckdb.connect(str(databases.equipment_path), read_only=True)
    except duckdb.Error as exc:
        databases.close()
        print(_LOCK_MESSAGE)
        print(f"  {type(exc).__name__}")
        return 1
    try:
        for name in LINES:
            if name not in selected:
                continue
            try:
                for line in _LINE_BUILDERS[name](databases, packed):
                    print(line, flush=True)
            except Exception as exc:  # 한 줄이 멈춰도 다음 줄은 센다. 문구는 찍지 않는다
                print(f"{name} 실패 {type(exc).__name__}", flush=True)
    finally:
        databases.close()
    return 0


# ---------------------------------------------------------------------------------- 줄 1 counts


def _first(
    connection: duckdb.DuckDBPyConnection, sql: str, params: Sequence[object] = ()
) -> object:
    return connection.execute(sql, list(params)).fetchall()[0][0]


def _has_table(connection: duckdb.DuckDBPyConnection, schema: str, table: str) -> bool:
    return bool(
        _first(
            connection,
            "SELECT count(*) FROM duckdb_tables() WHERE schema_name = ? AND table_name = ?",
            [schema, table],
        )
    )


def count_line(simulation: duckdb.DuckDBPyConnection, equipment: duckdb.DuckDBPyConnection) -> str:
    """두 DB 의 마이그레이션 번호와 표마다 행 수 — 끝 다섯 칸의 표 · 칸이 없으면 `None`."""

    def sim(table: str) -> object:
        return _first(simulation, f"SELECT count(*) FROM app_meta.{table}")

    def eq(table: str) -> object:
        return _first(equipment, f"SELECT count(*) FROM equipment_ops.{table}")

    def sim_if(table: str) -> object:
        return sim(table) if _has_table(simulation, "app_meta", table) else None

    def eq_if(table: str) -> object:
        return eq(table) if _has_table(equipment, "equipment_ops", table) else None

    def looks(table: str) -> object:
        has_column = _first(
            equipment,
            "SELECT count(*) FROM duckdb_columns() "
            "WHERE schema_name = ? AND table_name = ? AND column_name = ?",
            ["equipment_ops", table, "look_json"],
        )
        if not has_column:
            return None
        return _first(
            equipment, f"SELECT count(*) FROM equipment_ops.{table} WHERE look_json IS NOT NULL"
        )

    parts: list[object] = [
        "migration",
        _first(simulation, "SELECT max(version) FROM app_meta.schema_migration"),
        "equipment_migration",
        _first(equipment, "SELECT max(version) FROM equipment_meta.schema_migration"),
        "shortening_filter",
        [eq("shortening_filter_profile"), eq("shortening_filter_process")],
        "baselines",
        [
            eq("shortening_baseline"),
            eq("shortening_baseline_process"),
            eq("shortening_baseline_unit"),
        ],
        "advance_shipment",
        [sim("global_advance_shipment"), sim("global_advance_shipment_month")],
        "thresholds",
        [sim("global_securement_threshold"), sim("global_securement_threshold_month")],
        "fab",
        [eq("fab_layout_profile"), eq("fab_layout_mark")],
        "layout_marks",
        eq("floor_layout_mark"),
        "dup_names",
        _first(
            simulation,
            "SELECT count(*) FROM (SELECT scenario_name FROM app_meta.scenario "
            "GROUP BY scenario_name HAVING count(*) > 1)",
        ),
        "ref_copies",
        sum(
            cast(int, _first(simulation, f"SELECT count(*) FROM ref_data.rq_{table}"))
            for table in _REF_COPY_TABLES
        ),
        "auto_update",
        [sim_if(table) for table in _AUTO_UPDATE_TABLES],
        "main_cases",
        sim_if("global_main_cases"),
        "group_labels",
        eq_if("floor_layout_group_label"),
        "eq_scenario",
        [eq_if(table) for table in _EQUIPMENT_SCENARIO_TABLES],
        "floor_state",
        [eq_if("floor_state_profile"), eq_if("floor_state")],
        "layout_overlay",
        [eq_if(table) for table in _LAYOUT_OVERLAY_TABLES],
        "manual_downtime",
        [eq_if(table) for table in _MANUAL_DOWNTIME_TABLES],
        "mark_look",
        [looks(table) for table in _MARK_LOOK_TABLES],
    ]
    return " ".join(str(part) for part in parts)


# ---------------------------------------------------------------------------------- 줄 2 bundles

_Box = tuple[float, float, float, float]


def bundle_line(equipment: duckdb.DuckDBPyConnection) -> str:
    """최신 설비 리비전에서 Main 설비가 같은 행이 둘 이상인 묶음 — 모듈 수 · 상자 · 바둑판.

    `boxed` 는 모든 모듈에 좌표 · 크기가 있는 묶음(`all`) · 일부만(`some`) · 하나도 없음(`none`),
    `untiled` 는 `all` 가운데 바둑판이 아닌 묶음 수, `more split` 은 다섯 모듈 이상 묶음마다
    `<모듈 수>:f<층 수>,t<가장 큰 층의 모듈 수>,p<공정 수>,c<Main 설비 글자 수>` 다.
    """
    top = equipment.execute(
        "SELECT revision_id FROM equipment_ops.revision ORDER BY revision_no DESC LIMIT 1"
    ).fetchone()
    rows = (
        equipment.execute(
            "SELECT trim(parent_equipment_id), equipment_id, x_coordinate, y_coordinate, x_size, "
            "y_size, floor_name, process_small FROM equipment_ops.equipment_master_snapshot "
            "WHERE revision_id = ? AND length(trim(parent_equipment_id)) > 0",
            [top[0]],
        ).fetchall()
        if top
        else []
    )
    groups: dict[str, dict[str, _Box | None]] = {}
    for row in rows:
        box = row[2:6]
        groups.setdefault(row[0], {})[row[1]] = None if None in box else box
    bundles = [members for members in groups.values() if len(members) > 1]
    sizes = [len(members) for members in bundles]
    boxed = [sum(box is not None for box in members.values()) for members in bundles]

    def floors(parent: str) -> list[str]:
        return [(row[6] or "").strip() for row in rows if row[0] == parent]

    def split(parent: str) -> str:
        names = floors(parent)
        processes = {(row[7] or "").strip() for row in rows if row[0] == parent}
        tallest = max(names.count(name) for name in names)
        return (
            f"{len(groups[parent])}:f{len(set(names))},t{tallest},p{len(processes)},c{len(parent)}"
        )

    larger = sorted(
        (p for p, members in groups.items() if len(members) > 4), key=lambda p: len(groups[p])
    )
    untiled = sum(
        filled == size and (module_tile_deviation(members) or 0) > 0
        for filled, size, members in zip(boxed, sizes, bundles, strict=True)
    )
    more = sum(size > 4 for size in sizes)
    every = sum(filled == size for filled, size in zip(boxed, sizes, strict=True))
    some = sum(0 < filled < size for filled, size in zip(boxed, sizes, strict=True))
    larger_sizes = ",".join(str(size) for size in sorted(size for size in sizes if size > 4))
    return (
        f"groups {len(bundles)} = two {sizes.count(2)} + three {sizes.count(3)} + "
        f"four {sizes.count(4)} + more {more}; boxed {len(bundles)} = all {every} + "
        f"some {some} + none {boxed.count(0)}; untiled {untiled}; "
        f"more sizes {larger_sizes or '-'}; "
        f"more split {' '.join(split(parent) for parent in larger) or '-'}"
    )


# ---------------------------------------------------------------------------------- 줄 3 sizes


def _gzip_size(path: Path) -> int:
    """gzip(zlib 6) 로 줄인 크기 — 1 MiB 씩 읽는다. 이관 때 버킷에 올라갈 크기의 어림이다."""
    packer = zlib.compressobj(6)
    total = 0
    with path.open("rb") as file:
        for block in iter(lambda: file.read(_MIB), b""):
            total += len(packer.compress(block))
    return total + len(packer.flush())


def size_line(label: str, path: Path, connection: duckdb.DuckDBPyConnection, packed: int) -> str:
    """파일 크기 · 블록(쓰는 것 + 빈 것) · `.wal` · gzip 크기 · 표 수와 블록이 많은 표 여섯.

    표 MiB 는 그 표가 쓰는 블록 어림이라(작은 표는 블록을 나눠 써) 합이 `used` 와 같지 않다.
    """
    size = connection.execute("PRAGMA database_size").fetchone()
    assert size is not None
    block_size = int(size[2])
    tables = sorted(
        (
            (
                connection.execute(
                    "SELECT count(DISTINCT block_id) FROM pragma_storage_info(?) "
                    "WHERE block_id >= 0",
                    [f"{schema}.{table}"],
                ).fetchone()[0],  # type: ignore[index]
                f"{schema}.{table}",
                rows,
            )
            for schema, table, rows in connection.execute(
                "SELECT schema_name, table_name, estimated_size FROM duckdb_tables()"
            ).fetchall()
        ),
        reverse=True,
    )
    top = ", ".join(
        f"{name} {blocks * block_size / _MIB:.1f}MiB {int(rows)}rows"
        for blocks, name, rows in tables[:_TOP_TABLES]
    )
    wal = str(size[6]).replace(" ", "")
    return (
        f"{label} file {os.path.getsize(path) / _MIB:.1f}MiB; blocks {int(size[3])} = "
        f"used {int(size[4])} + free {int(size[5])}; block {block_size // 1024}KiB; wal {wal}; "
        f"gzip {packed / _MIB:.1f}MiB; tables {len(tables)}; top {top}"
    )


# ---------------------------------------------------------------------------------- 줄 4 plan


def zero_as_blank(table: pd.DataFrame, dimensions: Sequence[str]) -> pd.DataFrame:
    """PKG PLAN 그리드 양식 — 달 칸을 수로 읽고 0 을 빈칸으로(`plan_grid.zero_as_blank` 와 같다)."""
    shown = table.copy()
    months = [column for column in shown.columns if column not in dimensions]
    values = shown[months].apply(pd.to_numeric, errors="coerce").astype(float)
    shown[months] = values.mask(values.eq(0))
    return shown


@dataclass(frozen=True)
class PlanSize:
    """그리드 양식 하나의 줄 · 달 수와 껍데기 본문 바이트(`build_base` — 앱이 싣는 그 본문)."""

    rows: int
    months: int
    body_bytes: int

    @property
    def cells(self) -> int:
        return self.rows * self.months


def plan_templates(
    plan: pd.DataFrame, yield_data: pd.DataFrame
) -> dict[str, tuple[pd.DataFrame, tuple[str, ...]]]:
    """리비전 하나의 두 그리드 양식 — 기간은 PKG PLAN 의 첫 달 ~ 끝 달(조회기간을 가장 넓게 고른
    때 — 앱은 조회기간 ∩ 이 범위를 싣고 수율도 같은 기간으로 자른다). 줄 차례(표시순서)는 입히지
    않는다 — 본문 바이트는 줄 차례와 상관없다."""
    start, end = available_month_range(plan, PLAN_TABLE)
    plan_rows = filter_month_range(plan, start, end, PLAN_TABLE)
    yield_rows = filter_month_range(yield_data, start, end, YIELD_TABLE)
    editable, locked = split_editable_yield_rows(yield_rows)
    return {
        PLAN_TABLE: (
            zero_as_blank(plan_to_edit_table(plan_rows, None), PLAN_EDITOR_DIMENSIONS),
            tuple(PLAN_EDITOR_DIMENSIONS),
        ),
        YIELD_TABLE: (
            yield_to_edit_table(editable, None, locked=locked),
            tuple(YIELD_EDITOR_DIMENSIONS),
        ),
    }


def plan_size(table: str, template: pd.DataFrame, dimensions: tuple[str, ...]) -> PlanSize:
    months = tuple(str(column) for column in template.columns if column not in dimensions)
    title = PLAN_TITLE if table == PLAN_TABLE else YIELD_TITLE
    spec = GridSpec(table, title, dimensions, months, PLAN_FORMATS[table])
    return PlanSize(len(template), len(months), build_base(template, spec, None).size)


def plan_line(simulation: duckdb.DuckDBPyConnection) -> str:
    """생산 계획 그리드 두 표의 크기 — 본 리비전(시나리오마다 활성 리비전과 공식버전 대상)마다 재서
    표마다 줄 · 달 · 칸 수와 본문 KB 의 최대. 기간을 정하지 못하거나 양식을 짓지 못한 리비전은
    `skipped` 에 예외 종류만 센다."""
    revisions = [str(row[0]) for row in simulation.execute(_PICKED_REVISIONS).fetchall()]
    sizes: dict[str, list[PlanSize]] = {PLAN_TABLE: [], YIELD_TABLE: []}
    skipped: dict[str, int] = {}
    for revision_id in revisions:
        frames = [
            load_frame(
                simulation,
                schema="rev_data",
                table_name=REVISION_TABLES[table],
                owner_column="revision_id",
                owner_id=revision_id,
            )
            for table in (PLAN_TABLE, YIELD_TABLE)
        ]
        try:
            templates = plan_templates(*frames)
            measured = {
                table: plan_size(table, template, dimensions)
                for table, (template, dimensions) in templates.items()
            }
        except Exception as exc:  # 화면도 이 리비전에서는 그리드를 세우지 않는다 — 종류만 센다
            kind = failure_kind(exc)
            skipped[kind] = skipped.get(kind, 0) + 1
            continue
        for table, size in measured.items():
            sizes[table].append(size)

    def most(table: str, pick: Callable[[PlanSize], int]) -> int:
        return max((pick(size) for size in sizes[table]), default=0)

    parts = [f"plan revisions {len(revisions)}"]
    for table, label in ((PLAN_TABLE, "pkg_plan"), (YIELD_TABLE, "yield")):
        parts.append(
            f"{label} rows {most(table, lambda size: size.rows)} "
            f"months {most(table, lambda size: size.months)} "
            f"cells {most(table, lambda size: size.cells)} "
            f"body {most(table, lambda size: size.body_bytes) / 1000:.1f}KB"
        )
    kinds = " ".join(f"{kind} {count}" for kind, count in sorted(skipped.items()))
    parts.append(f"skipped {sum(skipped.values())}" + (f" ({kinds})" if kinds else ""))
    return "; ".join(parts)


# ---------------------------------------------------------------------------------- 묶음


def _counts(databases: _Databases, _packed: Mapping[Path, int]) -> list[str]:
    assert databases.simulation is not None and databases.equipment is not None
    return [count_line(databases.simulation, databases.equipment)]


def _bundles(databases: _Databases, _packed: Mapping[Path, int]) -> list[str]:
    assert databases.equipment is not None
    return [bundle_line(databases.equipment)]


def _sizes(databases: _Databases, packed: Mapping[Path, int]) -> list[str]:
    assert databases.simulation is not None and databases.equipment is not None
    return [
        size_line(label, path, connection, packed[path])
        for label, path, connection in (
            ("sim", databases.simulation_path, databases.simulation),
            ("eq", databases.equipment_path, databases.equipment),
        )
    ]


def _plan(databases: _Databases, _packed: Mapping[Path, int]) -> list[str]:
    assert databases.simulation is not None
    return [plan_line(databases.simulation)]


_LINE_BUILDERS: Final[dict[str, Callable[[_Databases, Mapping[Path, int]], list[str]]]] = {
    "counts": _counts,
    "bundles": _bundles,
    "sizes": _sizes,
    "plan": _plan,
}


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
