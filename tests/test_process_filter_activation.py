# Purpose: 리비전을 불러올 때 HOME 공정 필터가 앞 선택지 기억으로 뺀 공정을 되살리지 않음을 본다.

"""공정 필터 「세션 되살림」 함정(2026-10-15 자동 갱신 조사).

HOME 은 직전 회차의 공정 선택지(`PROCESS_SEEN_KEY`)를 들고 있다가 그때 없던 공정을 「처음 보는
공정」으로 포함한다. 그 기억이 **앞 리비전**의 것인 채로 새 리비전을 불러오면, 새 리비전의 프리셋이
뺀 공정 가운데 앞 리비전에 없던 것이 되살아난다 — 공식버전 자동 갱신이 새 데이터에서 처음 생긴
공정을 off 해도 이미 HOME 을 본 세션에서는 켜지고, 그 세션이 리비전을 저장하면 off 가 풀린 프리셋이
저장된다. 프리셋을 걸 때(`apply_pending_scenario_preset`) 그 기억을 지워 막는다.

실제 HOME 페이지를 돌린다. 내장 합성 시드(공정 셋)로, 「앞 리비전에 없던 공정」은 세션의 기억을
줄여 흉내 낸다.
"""

from __future__ import annotations

from pathlib import Path

from auto_update_fakes import CHIP, FINAL, WAFER
from streamlit.testing.v1 import AppTest

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.persistence.models import ScenarioPreset
from capa_simulation.persistence.repository import REVISION_TABLES, DuckDBScenarioRepository
from capa_simulation.scenario_preset_state import PROCESS_SEEN_KEY, PROCESS_SELECTION_KEY
from capa_simulation.services.builtin_seed import load_builtin_display_order

HOME_PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "home.py"
ACTIVATE_KEY = "test_activate_revision"

SCRIPT = """
from pathlib import Path

import streamlit as st

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({database!r})
original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
horizontal_scrollbar.render_horizontal_scrollbar = lambda *args, **kwargs: None
try:
    from capa_simulation.persistence.cache import load_scenario_snapshot
    from capa_simulation.scenario_activation import (
        activate_persisted_snapshot,
        bootstrap_latest_official_scenario,
    )
    from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

    bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
    target = st.session_state.pop({activate_key!r}, None)
    if target:
        activate_persisted_snapshot(load_scenario_snapshot(str(settings.DUCKDB_PATH), target))
    apply_pending_scenario_preset()
    source = Path({home!r})
    code = compile(source.read_text(encoding="utf-8"), str(source), "exec")
    exec(code, {{"__name__": "__main__"}})
finally:
    horizontal_scrollbar.render_horizontal_scrollbar = original_scrollbar
"""


def _seeded(path: Path) -> tuple[DuckDBScenarioRepository, str]:
    """내장 시드 공식버전과, 같은 시나리오에서 WAFER 를 공정 필터에서 뺀 리비전 2."""
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    repository.initialize_global_display_order(load_builtin_display_order())
    release = ensure_initial_scenario(repository).release
    assert release is not None
    official = repository.load_revision(release.revision_id)
    assert set(official.preset.included_processes) == {CHIP, FINAL, WAFER}
    filtered = repository.save_revision(
        official.scenario.scenario_id,
        {name: official.tables[name] for name in REVISION_TABLES},
        ScenarioPreset(
            start_month=official.preset.start_month,
            end_month=official.preset.end_month,
            included_processes=(CHIP, FINAL),
            secure_threshold=official.preset.secure_threshold,
            warning_threshold=official.preset.warning_threshold,
        ),
        revision_name="WAFER off",
        parent_revision_id=official.revision.revision_id,
    )
    return repository, filtered.revision.revision_id


def test_loading_a_revision_keeps_its_excluded_process_off(tmp_path: Path) -> None:
    _, filtered_revision_id = _seeded(tmp_path / "scenario.duckdb")
    script = SCRIPT.format(
        database=str(tmp_path / "scenario.duckdb"),
        activate_key=ACTIVATE_KEY,
        home=str(HOME_PAGE),
    )
    app = AppTest.from_string(script, default_timeout=300).run()
    assert not app.exception, [element.message for element in app.exception]
    assert set(app.session_state[PROCESS_SELECTION_KEY]) == {CHIP, FINAL, WAFER}

    # 앞 리비전에는 WAFER 가 없었다고 치자(새 데이터에서 처음 생긴 공정) — 그 기억을 든 채 WAFER 를
    # 뺀 리비전을 불러온다.
    app.session_state[PROCESS_SEEN_KEY] = [CHIP, FINAL]
    app.session_state[ACTIVATE_KEY] = filtered_revision_id
    app = app.run()

    assert not app.exception, [element.message for element in app.exception]
    assert WAFER not in app.session_state[PROCESS_SELECTION_KEY]
    assert set(app.session_state[PROCESS_SELECTION_KEY]) == {CHIP, FINAL}
    # 기억은 새 리비전의 선택지로 다시 선다 — 그 뒤에 새로 보이는 공정은 여전히 포함된다.
    assert set(app.session_state[PROCESS_SEEN_KEY]) == {CHIP, FINAL, WAFER}


def _apply_preset_app() -> None:
    import streamlit as st

    from capa_simulation.persistence.models import ScenarioPreset as Preset
    from capa_simulation.scenario_preset_state import (
        PROCESS_SEEN_KEY as seen_key,
    )
    from capa_simulation.scenario_preset_state import (
        apply_pending_scenario_preset,
        queue_scenario_preset,
    )

    if "seeded" not in st.session_state:
        st.session_state["seeded"] = True
        st.session_state[seen_key] = ["앞 리비전 공정"]
        queue_scenario_preset(
            Preset(
                start_month=202601,
                end_month=202612,
                included_processes=("A",),
                secure_threshold=1.095,
                warning_threshold=0.995,
            )
        )
    st.session_state["applied"] = apply_pending_scenario_preset()


def test_applying_a_preset_forgets_the_previous_options() -> None:
    app = AppTest.from_function(_apply_preset_app).run()

    assert not app.exception
    assert app.session_state["applied"] is True
    assert PROCESS_SEEN_KEY not in app.session_state
    assert app.session_state[PROCESS_SELECTION_KEY] == ["A"]
