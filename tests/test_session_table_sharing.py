# Purpose: 시나리오를 연 세션 표가 공용 칸의 잠긴 배열을 함께 쓰고 편집은 표 교체로만 되는지 잠근다.

"""세션 표 공유(AGENTS 5장 20, 스위치 `CAPA_SHARE_SESSION_TABLES`).

시나리오를 여는 길(부트스트랩 · 사이드바 불러오기)은 공용 칸(`_load_scenario_snapshot_resource`)의
잠긴 프레임을 겉껍데기 사본으로 받아 세션 원본 · 편집본이 같은 배열을 함께 쓴다. 이 시험은 그것이
실제로 함께 쓰이고(`np.shares_memory`) 잠겼는지(`writeable` 거짓), 편집은 표를 통째로 갈아 끼워 공용
칸에 닿지 않는지, 숨은 제자리 쓰기는 바로 터지는지, 끈 서버는 깊은 사본인지를 진짜 화면 길
(`AppTest`)로 본다. 모든 화면을 돌린 멈춤 0 은 `tests/test_all_pages_render.py` 가 본다.

정적 그물: 잠긴 표는 크기를 재면(`memory_usage(deep=True)` · `info(memory_usage="deep")` ·
`sys.getsizeof`) 읽기만 해도 터지므로 앱 코드에 그 호출이 없고, `server.enableExpensiveMemoryStats`
(세션 상태 · 공용 칸 크기를 재는 Streamlit 지표)를 켜지 않는다.
"""

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation import settings
from capa_simulation.frame_sharing import frame_arrays, frame_is_locked
from capa_simulation.io.reference_cache import SESSION_REFERENCE_TABLES_KEY
from capa_simulation.persistence import cache as scenario_cache
from capa_simulation.persistence._sql_helpers import hash_tables
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_state import ACTIVE_SCENARIO_KEY, EDITABLE_SCENARIO_TABLES

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 시나리오를 여는 길을 앱과 같은 함수로 돈다. 차례는 세션 칸 `test_step` 이 고른다.
SCRIPT = """
import streamlit as st

from capa_simulation.components.scenario_status import load_saved_revision
from capa_simulation.scenario_activation import (
    activate_saved_revision,
    bootstrap_latest_official_scenario,
)
from capa_simulation.scenario_state import apply_table_updates, scenario_table

database_path = st.session_state["test_database_path"]
step = st.session_state.get("test_step", "bootstrap")
if step == "bootstrap":
    bootstrap_latest_official_scenario(database_path)
elif step == "load":
    st.session_state["test_load_result"] = load_saved_revision(
        database_path, st.session_state["test_revision_id"]
    )
elif step == "edit":
    active = st.session_state["active_scenario"]
    upeh = scenario_table(active, "RQ_UPEH")
    apply_table_updates(active, {"RQ_UPEH": upeh})
elif step == "saved":
    from pathlib import Path

    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    snapshot = DuckDBScenarioRepository(Path(database_path)).load_revision(
        st.session_state["test_revision_id"]
    )
    activate_saved_revision(snapshot)
"""


@dataclass(frozen=True)
class _Seeded:
    database_path: Path
    official_revision_id: str
    halved_revision_id: str


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> _Seeded:
    """내장 합성 시드의 공식 리비전과, 계획만 절반으로 바꾼 같은 시나리오의 새 리비전."""
    from capa_simulation.application_bootstrap import ensure_initial_scenario
    from capa_simulation.persistence.repository import REVISION_TABLES
    from capa_simulation.services import builtin_seed
    from capa_simulation.services.builtin_seed import load_builtin_display_order

    database_path = tmp_path_factory.mktemp("session-share") / "scenario.duckdb"
    with pytest.MonkeyPatch.context() as patch:
        missing = tmp_path_factory.mktemp("no_local_display_order") / "RQ_DISPLAY_ORDER.csv"
        patch.setattr(builtin_seed, "LOCAL_DISPLAY_ORDER_CSV_PATH", missing)
        repository = DuckDBScenarioRepository(database_path)
        repository.initialize()
        repository.initialize_global_display_order(load_builtin_display_order())
        release = ensure_initial_scenario(repository).release
        assert release is not None
        base = repository.load_revision(release.revision_id)
        tables = {name: base.tables[name] for name in REVISION_TABLES if name in base.tables}
        plan = tables["RQ_PKG_PLAN"].copy()
        plan["생산수량"] = pd.to_numeric(plan["생산수량"], errors="coerce") * 0.5
        tables["RQ_PKG_PLAN"] = plan
        halved = repository.save_revision(
            release.scenario_id, tables, base.preset, revision_name="계획 절반"
        )
    return _Seeded(database_path, release.revision_id, halved.revision.revision_id)


@pytest.fixture(autouse=True)
def _default_switches(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """바깥 환경의 스위치가 결과를 뒤집지 않게 두 스위치를 지우고(= 기본 켬), 캐시를 비운다."""
    monkeypatch.delenv(settings.SHARE_STRINGS_ENV, raising=False)
    monkeypatch.delenv(settings.SHARE_SESSION_TABLES_ENV, raising=False)
    scenario_cache.clear_scenario_repository()
    yield
    scenario_cache.clear_scenario_repository()


def _run(app: AppTest, step: str, **state: object) -> AppTest:
    app.session_state["test_step"] = step
    for key, value in state.items():
        app.session_state[key] = value
    app = app.run()
    assert not app.exception, [element.message for element in app.exception]
    return app


def _opened(seeded: _Seeded) -> AppTest:
    app = AppTest.from_string(SCRIPT, default_timeout=120)
    app.session_state["test_database_path"] = str(seeded.database_path)
    return _run(app, "bootstrap")


def _slot(seeded: _Seeded, revision_id: str) -> dict[str, pd.DataFrame]:
    payload = scenario_cache._load_scenario_snapshot_resource(
        str(seeded.database_path), revision_id, scenario_cache._write_generation("snapshot")
    )
    return payload["tables"]


def _session(app: AppTest) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """(세션 원본, 세션 편집본)."""
    reference: dict[str, pd.DataFrame] = app.session_state[SESSION_REFERENCE_TABLES_KEY]
    active: dict[str, Any] = app.session_state[ACTIVE_SCENARIO_KEY]
    return reference, active["tables"]


def _same_memory(first: pd.DataFrame, second: pd.DataFrame) -> bool:
    """두 표의 데이터 · 축 배열이 차례대로 모두 같은 메모리인가."""
    left, right = list(frame_arrays(first)), list(frame_arrays(second))
    return len(left) == len(right) and all(
        np.shares_memory(a, b) for a, b in zip(left, right, strict=True)
    )


def _data_arrays(frame: pd.DataFrame) -> list[np.ndarray[Any, Any]]:
    """데이터 블록의 배열만(축 빼고) — `copy(deep=True)` 도 열 이름 배열은 함께 쓴다."""
    blocks: tuple[Any, ...] = cast(Any, frame)._mgr.blocks
    arrays: list[np.ndarray[Any, Any]] = []
    for block in blocks:
        values = block.values
        for array in (values, *(getattr(values, slot, None) for slot in ("_ndarray", "_data"))):
            if isinstance(array, np.ndarray):
                arrays.append(array)
    return arrays


def _any_data_memory(first: pd.DataFrame, second: pd.DataFrame) -> bool:
    """두 표의 데이터 배열이 하나라도 같은 메모리인가."""
    return any(np.shares_memory(a, b) for a in _data_arrays(first) for b in _data_arrays(second))


def _assert_shares_the_slot(app: AppTest, slot: dict[str, pd.DataFrame]) -> None:
    reference, editable = _session(app)
    assert set(reference) == set(slot)
    for name, shared in slot.items():
        original = reference[name]
        assert original is not shared, name  # 공용 칸의 프레임 객체 자체는 넘기지 않는다
        assert original.columns is not shared.columns, name
        assert frame_is_locked(original), name
        assert _same_memory(original, shared), name
    for name in EDITABLE_SCENARIO_TABLES:
        table = editable[name]
        assert table is not reference[name], name
        assert table.columns is not reference[name].columns, name
        assert frame_is_locked(table), name
        assert _same_memory(table, slot[name]), name


def test_a_new_session_shares_the_locked_official_tables(seeded: _Seeded) -> None:
    """부트스트랩 뒤 세션 원본 · 편집본의 배열은 모두 잠겼고 공용 칸과 같은 메모리다."""
    app = _opened(seeded)

    _assert_shares_the_slot(app, _slot(seeded, seeded.official_revision_id))


def test_a_revision_loaded_from_the_sidebar_shares_its_slot_too(seeded: _Seeded) -> None:
    """사이드바 불러오기(HOME 주요 Case 칩도 같은 길)도 그 리비전의 공용 칸을 함께 쓴다."""
    app = _opened(seeded)
    app = _run(app, "load", test_revision_id=seeded.halved_revision_id)

    assert app.session_state["test_load_result"] is None
    _assert_shares_the_slot(app, _slot(seeded, seeded.halved_revision_id))


def test_an_edit_replaces_only_its_table_and_leaves_the_slot_alone(seeded: _Seeded) -> None:
    """편집 적용은 그 표만 새 프레임으로 갈아 끼운다 — 나머지는 계속 함께 쓰고 공용 칸은 그대로."""
    app = _opened(seeded)
    slot = _slot(seeded, seeded.official_revision_id)
    before = hash_tables(slot, list(slot))

    app = _run(app, "edit")

    reference, editable = _session(app)
    edited = editable["RQ_UPEH"]
    assert not _any_data_memory(edited, slot["RQ_UPEH"])
    assert not frame_is_locked(edited)
    for name in EDITABLE_SCENARIO_TABLES:
        if name != "RQ_UPEH":
            assert _same_memory(editable[name], slot[name]), name
    assert _same_memory(reference["RQ_UPEH"], slot["RQ_UPEH"])
    assert hash_tables(slot, list(slot)) == before


def test_a_hidden_in_place_write_fails_loudly_instead_of_reaching_other_sessions(
    seeded: _Seeded,
) -> None:
    """세션 표에 같은 dtype 으로 제자리 쓰면 바로 터지고 공용 칸 · 다른 세션의 숫자는 그대로다."""
    first = _opened(seeded)
    second = _opened(seeded)
    slot = _slot(seeded, seeded.official_revision_id)
    _, editable = _session(first)
    upeh = editable["RQ_UPEH"]
    numeric = next(
        str(name) for name, dtype in upeh.dtypes.items() if pd.api.types.is_float_dtype(dtype)
    )
    value = float(upeh[numeric].iloc[0])

    with pytest.raises(ValueError, match="read-only"):
        upeh.iloc[0, list(upeh.columns).index(numeric)] = value + 1.0
    with pytest.raises(ValueError, match="read-only"):
        upeh.columns.values[0] = "오염된_컬럼"

    assert float(slot["RQ_UPEH"][numeric].iloc[0]) == value
    assert float(_session(second)[1]["RQ_UPEH"][numeric].iloc[0]) == value


def test_a_saved_revision_keeps_its_own_read_and_locks_it(seeded: _Seeded) -> None:
    """저장 뒤 길은 공용 칸을 거치지 않는다(저장소가 새로 읽은 한 벌) — 그 한 벌을 잠그고 편집본이
    함께 쓴다(2026-11-17 보드 q-share: 저장 뒤 길은 지금 그대로)."""
    app = _opened(seeded)
    app = _run(app, "saved", test_revision_id=seeded.halved_revision_id)

    reference, editable = _session(app)
    slot = _slot(seeded, seeded.halved_revision_id)
    for name in EDITABLE_SCENARIO_TABLES:
        assert frame_is_locked(reference[name]), name
        assert _same_memory(editable[name], reference[name]), name
        assert not _any_data_memory(reference[name], slot[name]), name


def test_the_switch_turns_sharing_off(seeded: _Seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    """스위치를 끄면(`off`) 세션마다 공용 칸과 데이터 배열을 함께 쓰지 않는 깊은 사본이다."""
    monkeypatch.setenv(settings.SHARE_SESSION_TABLES_ENV, "off")
    app = _opened(seeded)
    slot = _slot(seeded, seeded.official_revision_id)

    reference, editable = _session(app)
    for name, shared in slot.items():
        assert not _any_data_memory(reference[name], shared), name
        assert not frame_is_locked(reference[name]), name
    for name in EDITABLE_SCENARIO_TABLES:
        assert not _any_data_memory(editable[name], reference[name]), name
        assert all(array.flags.writeable for array in frame_arrays(editable[name])), name


@pytest.mark.parametrize(
    ("value", "enabled"),
    [(None, True), ("", True), ("1", True), ("off", False), (" Off ", False)],
)
def test_the_switch_reads_off_only(value: str | None, enabled: bool) -> None:
    environ = {} if value is None else {settings.SHARE_SESSION_TABLES_ENV: value}

    assert settings.share_session_tables_enabled(environ) is enabled


# --------------------------------------------------------------- 정적 그물


def _app_sources() -> list[Path]:
    roots = [PROJECT_ROOT / "src", PROJECT_ROOT / "app_pages"]
    files = [path for root in roots for path in sorted(root.rglob("*.py"))]
    return [*files, PROJECT_ROOT / "app.py", PROJECT_ROOT / "capa_server.py"]


def _size_measuring_calls(source: str) -> list[int]:
    """크기를 재는 호출의 줄 번호 — `memory_usage(deep=True)` · `info(memory_usage="deep")` ·
    `getsizeof(…)` · `asizeof(…)`. 주석 · 문서 글은 세지 않는다."""
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        name = (
            function.attr
            if isinstance(function, ast.Attribute)
            else function.id
            if isinstance(function, ast.Name)
            else ""
        )
        keywords = {
            keyword.arg: keyword.value.value
            for keyword in node.keywords
            if keyword.arg and isinstance(keyword.value, ast.Constant)
        }
        if (
            name in {"getsizeof", "asizeof"}
            or (name == "memory_usage" and keywords.get("deep") is True)
            or (name == "info" and keywords.get("memory_usage") == "deep")
        ):
            lines.append(node.lineno)
    return lines


def test_the_app_code_never_measures_the_size_of_a_frame() -> None:
    """잠긴 객체 배열은 크기를 재기만 해도 `ValueError` 다(pandas 2.2.3) — 앱 코드에 그 호출 0."""
    found = {
        str(path.relative_to(PROJECT_ROOT)): lines
        for path in _app_sources()
        if (lines := _size_measuring_calls(path.read_text(encoding="utf-8")))
    }

    assert not found, found


def test_the_size_net_catches_each_measuring_call() -> None:
    source = (
        "import sys\n"
        "frame.memory_usage(deep=True)\n"
        "frame.info(memory_usage='deep')\n"
        "sys.getsizeof(frame)\n"
        "frame.memory_usage(deep=False)\n"
        "frame.info()\n"
    )

    assert _size_measuring_calls(source) == [2, 3, 4]


def test_the_expensive_memory_stats_stay_off() -> None:
    """`server.enableExpensiveMemoryStats` 를 켜면 `/_stcore/metrics` 가 잠긴 세션 표 · 공용 칸의
    크기를 재다 `ValueError` 로 실패한다 — 설정 파일에 켜 두지 않는다(기본 꺼짐)."""
    text = (PROJECT_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    lines = [line.split("#", 1)[0] for line in text.splitlines()]

    assert not [
        line
        for line in lines
        if re.match(r"\s*enableExpensiveMemoryStats\s*=\s*true\b", line, flags=re.IGNORECASE)
    ]
