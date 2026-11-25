# Purpose: 7-8 개수 세기 스크립트가 읽기만 하고 다섯 줄을 7장 기대 줄 꼴 그대로 수만 찍는지 본다.

"""`scripts/inspect_db_counts.py` 의 약속 — 줄 1 ~ 3 은 런북 7-8 의 기대 줄 · 지난 리뷰 값과 견주는
꼴이라 키 · 차례 · 값 꼴을 글자 그대로 찍고, 넷째 줄은 생산 계획 그리드 두 표의 크기, 다섯째 줄은
모듈 묶음 안에서 같이 바뀌는 칸이 갈린 묶음 수다. 두 DB 를 읽기만 하고, 운영 DB 자리를 열 때는
사용자 앱을 먼저 보며, 이름 · 값은 찍지 않는다. 묶음 줄의 갈래(모듈 묶음 크기 · 상자 · 바둑판)와
갈림 줄의 갈래(값 다름 · 빈 칸 섞임)는 손으로 지은 설비 DB 로 붙든다.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from before_custom_copy import database_before_custom, database_marked_after_custom
from test_equipment_migration_0027_scenarios import _database_before

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.components import plan_grid
from capa_simulation.persistence.equipment_migration_runner import load_equipment_migrations
from capa_simulation.persistence.equipment_repository import (
    EQUIPMENT_MASTER_DB_COLUMNS,
    DuckDBEquipmentRepository,
)
from capa_simulation.persistence.migration_runner import load_migrations
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.plan_grid_keys import PLAN_TABLE, YIELD_TABLE
from capa_simulation.services.equipment_contract import (
    UNIT_CONSISTENT_COLUMNS,
    UNIT_SAVE_CONSISTENT_COLUMNS,
    UNIT_SHARED_COLUMNS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import check_deploy_screens  # noqa: E402
import inspect_db_counts as script  # noqa: E402

SENTINEL = "ZZSENTINEL"
# 누적 진척 넣기 스냅숏 세 표(머리 · 범위 공정 · 호기)를 만든 설비 마이그레이션 번호.
SNAPSHOT_MIGRATION = 37
_N = r"(?:\d+|None)"


def _listed(size: int) -> str:
    return r"\[" + ", ".join([_N] * size) + r"\]"


# 첫 줄 — 7장 기대 줄의 키 차례와 칸마다의 값 꼴(수 · `None` · 그 목록의 길이) 그대로.
COUNT_LINE = re.compile(
    "^"
    + " ".join(
        f"{key} {value}"
        for key, value in (
            ("migration", r"\d+"),
            ("equipment_migration", r"\d+"),
            ("shortening_filter", _listed(2)),
            ("baselines", _listed(3)),
            ("advance_shipment", _listed(2)),
            ("thresholds", _listed(2)),
            ("fab", _listed(2)),
            ("layout_marks", r"\d+"),
            ("dup_names", r"\d+"),
            ("ref_copies", r"\d+"),
            ("auto_update", _listed(4)),
            ("main_cases", _N),
            ("group_labels", _N),
            ("eq_scenario", _listed(4)),
            ("floor_state", _listed(2)),
            ("layout_overlay", _listed(3)),
            ("manual_downtime", _listed(3)),
            ("mark_look", _listed(3)),
            ("layout_stack", _listed(3)),
            ("progress_log", _listed(2)),
            ("progress_snapshot", _listed(3)),
        )
    )
    + "$"
)
SIZE_LINE = re.compile(
    r"^(sim|eq) file \d+\.\dMiB; blocks \d+ = used \d+ \+ free \d+; block \d+KiB; wal \S+; "
    r"gzip \d+\.\dMiB; tables \d+; top (?:[a-z_]+\.[a-z_0-9]+ \d+\.\dMiB \d+rows(?:, )?)+$"
)
PLAN_LINE = re.compile(
    r"^plan revisions (\d+); pkg_plan rows (\d+) months (\d+) cells (\d+) body \d+\.\dKB; "
    r"yield rows (\d+) months (\d+) cells (\d+) body \d+\.\dKB; skipped (\d+)(?: \(.+\))?$"
)


@pytest.fixture(scope="module")
def databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    folder = tmp_path_factory.mktemp("db_counts")
    simulation = DuckDBScenarioRepository(folder / "capa_simulation.duckdb")
    simulation.initialize()
    ensure_initial_scenario(simulation)
    equipment = DuckDBEquipmentRepository(folder / "equipment_availability.duckdb")
    equipment.initialize()
    return simulation.database_path, folder / "equipment_availability.duckdb"


def _run(args: list[str], tmp_path: Path) -> tuple[int, list[str]]:
    output = tmp_path / "db_counts.md"
    code = script.main([*args, "--output", str(output)])
    return code, output.read_text(encoding="utf-8").splitlines()


def test_the_five_lines_are_counts_only(databases: tuple[Path, Path], tmp_path: Path) -> None:
    simulation, equipment = databases
    code, lines = _run(
        ["--database", str(simulation), "--equipment-database", str(equipment)], tmp_path
    )

    assert code == 0
    assert len(lines) == 6, lines
    counts, bundles, sim_size, eq_size, plan, mixed = lines
    sim_version = max(migration.version for migration in load_migrations())
    eq_version = max(migration.version for migration in load_equipment_migrations())
    assert counts.startswith(f"migration {sim_version} equipment_migration {eq_version} ")
    assert COUNT_LINE.match(counts), counts
    assert " ref_copies 0 " in counts
    assert counts.endswith(" progress_log [0, 0] progress_snapshot [0, 0, 0]"), counts
    assert bundles == (
        "groups 0 = two 0 + three 0 + four 0 + more 0; boxed 0 = all 0 + some 0 + none 0; "
        "untiled 0; more sizes -; more split -"
    )
    assert SIZE_LINE.match(sim_size) and sim_size.startswith("sim ")
    assert SIZE_LINE.match(eq_size) and eq_size.startswith("eq ")
    found = PLAN_LINE.match(plan)
    assert found is not None, plan
    revisions, plan_rows, plan_months, plan_cells = (int(found[n]) for n in range(1, 5))
    assert revisions >= 1 and found[8] == "0"
    assert plan_rows > 0 and plan_months > 0 and 0 < plan_cells <= plan_rows * plan_months
    assert int(found[5]) > 0 and int(found[6]) == plan_months
    assert mixed == (
        "unit_mixed groups 0; read ps 0+0 pl 0+0 line 0+0 inv 0+0 bldg 0+0 floor 0+0; "
        "save area 0+0 maker 0+0 model 0+0 capa 0+0 owner 0+0 store 0+0 exist 0+0; show 0+0"
    )


def test_a_copy_before_the_custom_column_adds_one_line_right_after_the_plan_line(
    databases: tuple[Path, Path], tmp_path: Path
) -> None:
    """0039 전 사본 — 줄 4 는 두 표의 CUSTOM 칸을 0039 와 같이 채워 재 0039 뒤 사본과 같은 수를
    내고, 그 바로 뒤에 `사본 0039 전` 한 줄이 선다. 다섯 줄의 꼴은 그대로이고 끝 줄은 여전히
    `mixed` 다. 채우지 않으면 줄 4 는 리비전마다 `skipped` 로 빠진다."""
    simulation, equipment = databases
    before = database_before_custom(simulation, tmp_path / "capa_simulation.duckdb")

    code, old = _run(["--database", str(before), "--equipment-database", str(equipment)], tmp_path)
    _, new = _run(["--database", str(simulation), "--equipment-database", str(equipment)], tmp_path)

    assert code == 0
    assert len(old) == len(new) + 1 == 7, old
    counts, _bundles, sim_size, eq_size, plan, marker, mixed = old
    assert COUNT_LINE.match(counts) and counts.startswith("migration 38 ")
    assert SIZE_LINE.match(sim_size) and SIZE_LINE.match(eq_size)
    assert PLAN_LINE.match(plan) and plan == new[4]
    assert marker == (
        "사본 0039 전 — migration 38; plan 은 두 표의 CUSTOM 칸을 0039 와 같이 빈 값 표지(-)로 "
        "채워 쟀다"
    )
    assert mixed == new[5]
    assert old[1] == new[1]
    code, only_plan = _run(
        ["--only", "plan", "--database", str(before), "--equipment-database", str(equipment)],
        tmp_path,
    )
    assert code == 0 and only_plan == [plan, marker]


def test_a_copy_marked_after_the_custom_migration_is_not_filled(
    databases: tuple[Path, Path], tmp_path: Path
) -> None:
    """채우기는 마이그레이션 번호로만 가른다 — 0039 를 건 것으로 적힌 사본에 칸이 없으면 채우지 않고
    줄 4 가 그 리비전을 `skipped` 로 빼며, `사본 0039 전` 한 줄도 없다."""
    simulation, equipment = databases
    marked = database_marked_after_custom(simulation, tmp_path / "capa_simulation.duckdb")

    code, lines = _run(
        ["--database", str(marked), "--equipment-database", str(equipment)], tmp_path
    )

    assert code == 0
    assert not [line for line in lines if "사본 0039 전" in line]
    [plan] = [line for line in lines if line.startswith("plan ")]
    assert PLAN_LINE.match(plan) and plan.endswith("skipped 1 (ValueError 1)"), plan


def _counts_only(simulation: Path, equipment: Path, tmp_path: Path) -> str:
    code, lines = _run(
        ["--only", "counts", "--database", str(simulation), "--equipment-database", str(equipment)],
        tmp_path,
    )
    assert code == 0 and len(lines) == 1, lines
    assert COUNT_LINE.match(lines[0]), lines[0]
    return lines[0]


def test_the_count_line_ends_with_the_progress_snapshot_rows(
    databases: tuple[Path, Path], tmp_path: Path
) -> None:
    """설비 `0037` 넣기 스냅숏 — 첫 줄 끝 칸 `progress_snapshot [머리, 공정, 호기]` 가 세 표의
    행 수를 그 차례로 찍는다(수가 모두 달라 차례가 바뀌면 깨진다). 공정 · 호기 이름은 찍지
    않는다."""
    simulation, source = databases
    equipment = tmp_path / "equipment_availability.duckdb"
    shutil.copyfile(source, equipment)
    with duckdb.connect(str(equipment)) as connection:
        connection.execute(
            "INSERT INTO equipment_ops.shortening_progress_snapshot (iso_year, iso_week, "
            "snapshot_id, log_updated_at, snapshot_days, target_level, schedule_basis, "
            "scope_selected, plan_today, start_month, end_month, content_digest) VALUES "
            "(2026, 47, 's1', TIMESTAMP '2026-11-20 09:00:00', 10, 100, 'Static', false, "
            "DATE '2026-11-20', 202701, 202703, 'd')"
        )
        connection.executemany(
            "INSERT INTO equipment_ops.shortening_progress_snapshot_process "
            "(snapshot_id, process_name, sort_order) VALUES ('s1', ?, ?)",
            [(f"{SENTINEL}-P{index}", index) for index in range(2)],
        )
        connection.executemany(
            "INSERT INTO equipment_ops.shortening_progress_snapshot_unit (snapshot_id, "
            "sort_order, process_name, unit_name, unit_kind, module_count, target_qual) "
            "VALUES ('s1', ?, ?, ?, ?, 1, DATE '2027-03-01')",
            [
                (0, f"{SENTINEL}-P0", f"{SENTINEL}-U0", "단축"),
                (1, f"{SENTINEL}-P0", f"{SENTINEL}-U1", "단축"),
                (2, f"{SENTINEL}-P1", f"{SENTINEL}-U2", "신규"),
            ],
        )

    counts = _counts_only(simulation, equipment, tmp_path)

    eq_version = max(migration.version for migration in load_equipment_migrations())
    assert eq_version >= SNAPSHOT_MIGRATION
    assert f" equipment_migration {eq_version} " in counts
    assert counts.endswith(" progress_log [0, 0] progress_snapshot [1, 2, 3]"), counts
    assert SENTINEL not in counts


def test_an_equipment_copy_before_the_snapshot_tables_counts_none(
    databases: tuple[Path, Path], tmp_path: Path
) -> None:
    """설비 `0037` 을 건 적 없는 사본(앞 판 코드가 연 설비 36) — 세 표가 없어 끝 칸이
    `[None, None, None]` 이고 첫 줄 꼴은 그대로다. 앞 칸 `progress_log` 은 그대로 센다."""
    simulation, _ = databases
    equipment = tmp_path / "equipment_availability.duckdb"
    _database_before(equipment, SNAPSHOT_MIGRATION - 1)

    counts = _counts_only(simulation, equipment, tmp_path)

    assert f" equipment_migration {SNAPSHOT_MIGRATION - 1} " in counts
    assert counts.endswith(" progress_log [0, 0] progress_snapshot [None, None, None]"), counts


def _bundle_database(path: Path) -> Path:
    """Space 모듈 묶음 줄이 보는 두 표만 지은 설비 DB — 갈래마다 묶음 하나."""
    with duckdb.connect(str(path)) as connection:
        connection.execute("CREATE SCHEMA equipment_ops")
        connection.execute(
            "CREATE TABLE equipment_ops.revision (revision_id VARCHAR, revision_no INTEGER)"
        )
        connection.execute(
            "CREATE TABLE equipment_ops.equipment_master_snapshot (revision_id VARCHAR, "
            "parent_equipment_id VARCHAR, equipment_id VARCHAR, x_coordinate DOUBLE, "
            "y_coordinate DOUBLE, x_size DOUBLE, y_size DOUBLE, floor_name VARCHAR, "
            "process_small VARCHAR)"
        )
        connection.execute("INSERT INTO equipment_ops.revision VALUES ('old', 1), ('new', 2)")
        rows: list[tuple[object, ...]] = []

        def add(
            parent: str, unit: str, box: tuple[float, ...] | None, floor: str, process: str
        ) -> None:
            x, y, w, h = box if box is not None else (None, None, None, None)
            rows.append(("new", parent, unit, x, y, w, h, floor, process))

        # 2모듈 — 바둑판 그대로(가로로 둘).
        add(f"{SENTINEL}-A", "A1", (0, 0, 1, 1), "1F", "P1")
        add(f"{SENTINEL}-A", "A2", (1, 0, 1, 1), "1F", "P1")
        # 3모듈 — 일부만 상자.
        for index in range(3):
            add("B", f"B{index}", (index, 5, 1, 1) if index else None, "1F", "P1")
        # 4모듈 — 상자 없음(미배치).
        for index in range(4):
            add("C", f"C{index}", None, "2F", "P2")
        # 6모듈 — 모두 상자인데 흩어짐(바둑판 아님), 두 층 · 두 공정, Main 글자 수 6.
        for index in range(6):
            box = (10.0 * index, 0.0 if index < 3 else 50.0, 5.0, 5.0)
            add("DDDDDD", f"D{index}", box, "1F" if index < 4 else "2F", f"P{index % 2}")
        # 혼자인 Main(묶음 아님)과 Main 이 빈 행, 옛 리비전의 행은 세지 않는다.
        add("E", "E1", None, "1F", "P1")
        add("  ", "F1", None, "1F", "P1")
        rows.append(("old", "G", "G1", None, None, None, None, "1F", "P1"))
        rows.append(("old", "G", "G2", None, None, None, None, "1F", "P1"))
        connection.executemany(
            "INSERT INTO equipment_ops.equipment_master_snapshot "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    return path


def test_the_bundle_line_counts_sizes_boxes_and_tiles_without_names(tmp_path: Path) -> None:
    equipment = _bundle_database(tmp_path / "equipment_availability.duckdb")

    code, lines = _run(["--only", "bundles", "--equipment-database", str(equipment)], tmp_path)

    assert code == 0
    assert lines == [
        "groups 4 = two 1 + three 1 + four 1 + more 1; boxed 4 = all 2 + some 1 + none 1; "
        "untiled 1; more sizes 6; more split 6:f2,t4,p2,c6"
    ]
    assert SENTINEL not in "\n".join(lines)


def test_the_mixed_line_keys_follow_the_contract_tuples() -> None:
    """갈림 줄의 칸은 같이 바뀌는 14칸(`UNIT_SHARED_COLUMNS`) 그대로이고 갈래는 계약 튜플에서
    나온다 — 계약에 칸이 늘거나 빠지면 이 줄도 따라가야 한다(짧은 키는 겹치지 않고 DB 칸이 있다)."""
    assert set(script.MIXED_KEYS) == set(UNIT_SHARED_COLUMNS)
    assert len(set(script.MIXED_KEYS.values())) == len(script.MIXED_KEYS)
    assert all(column in EQUIPMENT_MASTER_DB_COLUMNS for column in script.MIXED_KEYS)
    parts = dict(script._MIXED_PARTS)
    assert parts["read"] == UNIT_CONSISTENT_COLUMNS
    assert parts["save"] == UNIT_SAVE_CONSISTENT_COLUMNS
    assert parts["show"] == ("레이아웃표시",)


def _mixed_database(path: Path) -> Path:
    """갈림 줄이 보는 두 표만 지은 설비 DB — 갈래마다 묶음 하나(값은 모두 표지값)."""
    columns = {column: EQUIPMENT_MASTER_DB_COLUMNS[column] for column in UNIT_SHARED_COLUMNS}
    with duckdb.connect(str(path)) as connection:
        connection.execute("CREATE SCHEMA equipment_ops")
        connection.execute(
            "CREATE TABLE equipment_ops.revision (revision_id VARCHAR, revision_no INTEGER)"
        )
        names = ", ".join(f"{db} VARCHAR" for db in columns.values())
        connection.execute(
            "CREATE TABLE equipment_ops.equipment_master_snapshot (revision_id VARCHAR, "
            f"parent_equipment_id VARCHAR, equipment_id VARCHAR, {names})"
        )
        connection.execute("INSERT INTO equipment_ops.revision VALUES ('old', 1), ('new', 2)")
        rows: list[tuple[object, ...]] = []

        def add(revision: str, parent: str, unit: str, **values: str | None) -> None:
            cells = [values.get(column, f"{SENTINEL}-{column}") for column in columns]
            rows.append((revision, parent, unit, *cells))

        # 담당자 값 다름 · Maker 빈 칸 섞임 · 동 값 다름(앞뒤 공백은 같은 값) · 레이아웃표시 다름.
        add("new", f"{SENTINEL}-A", "A1", 담당자="가", 동=" C1 ")
        add("new", f"{SENTINEL}-A", "A2", 담당자="나", 동="C1")
        add("new", "B", "B1", Maker=None)
        add("new", "B", "B2")
        add("new", "B", "B3", Maker="")
        add("new", "C", "C1", 동="C1", 레이아웃표시="Y")
        add("new", "C", "C2", 동="C2", 레이아웃표시="N")
        # 혼자인 Main · Main 이 빈 행 · 옛 리비전의 갈린 묶음은 세지 않는다.
        add("new", "E", "E1", 담당자="다")
        add("new", "  ", "F1", 담당자="라")
        add("new", "  ", "F2", 담당자="마")
        add("old", "G", "G1", 담당자="바")
        add("old", "G", "G2", 담당자="사")
        marks = ", ".join("?" * (3 + len(columns)))
        connection.executemany(
            f"INSERT INTO equipment_ops.equipment_master_snapshot VALUES ({marks})", rows
        )
    return path


def test_the_mixed_line_tells_a_different_value_from_a_mixed_blank_without_names(
    tmp_path: Path,
) -> None:
    """다섯째 줄 — 최신 리비전의 묶음 수와 칸마다 `값 다름+빈 칸 섞임`. 저장 규칙이 빈 칸도 한
    값으로 견주므로 둘 다 갈림이다. 값 · 이름은 찍지 않는다."""
    equipment = _mixed_database(tmp_path / "equipment_availability.duckdb")

    code, lines = _run(["--only", "mixed", "--equipment-database", str(equipment)], tmp_path)

    assert code == 0
    assert lines == [
        "unit_mixed groups 3; read ps 0+0 pl 0+0 line 0+0 inv 0+0 bldg 1+0 floor 0+0; "
        "save area 0+0 maker 0+1 model 0+0 capa 0+0 owner 1+0 store 0+0 exist 0+0; show 1+0"
    ]
    assert SENTINEL not in "\n".join(lines)


def test_the_plan_line_mirrors_the_production_plan_grid() -> None:
    """화면 모듈(streamlit)을 부르지 않고 같은 값을 들고 있다 — 표 이름 · 값 꼴 · 0 을 빈칸으로."""
    page = (PROJECT_ROOT / "app_pages" / "load_conversion.py").read_text(encoding="utf-8")

    assert (script.PLAN_TABLE, script.YIELD_TABLE) == (PLAN_TABLE, YIELD_TABLE)
    assert dict(script.PLAN_FORMATS) == dict(plan_grid.FORMATS)
    assert f'PKG_PLAN_TAB_NAME = "{script.PLAN_TITLE}"' in page
    assert f'YIELD_TAB_NAME = "{script.YIELD_TITLE}"' in page
    frame = pd.DataFrame(
        {"제품정보": ["a", "b", "c"], "202601": [0, 3.5, None], "202602": ["0", "7", ""]}
    )
    pd.testing.assert_frame_equal(
        script.zero_as_blank(frame, ["제품정보"]), plan_grid.zero_as_blank(frame, ["제품정보"])
    )


def test_the_operational_place_waits_for_the_app_to_stop(
    databases: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """사본을 주지 않으면 운영 DB 자리다 — 앱 프로세스가 보이면 DB 를 열지 않고 한 줄로 멈춘다."""
    simulation, equipment = databases
    monkeypatch.setattr(script, "DUCKDB_PATH", simulation)
    monkeypatch.setattr(script, "EQUIPMENT_DUCKDB_PATH", equipment)
    monkeypatch.setattr(check_deploy_screens, "running_app_count", lambda *_a, **_k: 1)
    opened: list[str] = []
    monkeypatch.setattr(duckdb, "connect", lambda *a, **_k: opened.append(str(a)))

    code, lines = _run([], tmp_path)

    assert code == 1
    assert lines == [script._APP_RUNNING_MESSAGE]
    assert opened == []


def test_a_copy_does_not_look_at_the_app(
    databases: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    simulation, equipment = databases

    def refuse(*_a: object, **_k: object) -> int:
        raise AssertionError("사본인데 앱 프로세스를 봤다")

    monkeypatch.setattr(check_deploy_screens, "running_app_count", refuse)

    code, lines = _run(
        ["--only", "counts", "--database", str(simulation), "--equipment-database", str(equipment)],
        tmp_path,
    )

    assert code == 0 and len(lines) == 1 and lines[0].startswith("migration ")


def test_unknown_lines_and_missing_files_stop_without_paths(tmp_path: Path) -> None:
    missing = tmp_path / "nowhere" / "capa_simulation.duckdb"

    assert _run(["--only", "census"], tmp_path) == (
        2,
        [f"모르는 줄: ['census'] — 고를 수 있는 것: {', '.join(script.LINES)}"],
    )
    code, lines = _run(["--only", "plan", "--database", str(missing)], tmp_path)
    assert code == 1
    assert lines == ["DB 파일이 없습니다: capa_simulation.duckdb"]
    assert str(tmp_path) not in "\n".join(lines)
