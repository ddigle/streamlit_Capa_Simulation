# Purpose: HOME 이 공용 비교 대상 프로필을 언제 되쓰고 언제 손대지 않는지 고정한다.

"""비교 대상 프로필은 **시나리오에 딸리지 않은 공용 값**이라 두 사용자가 같은 행을 쓴다.

HOME 은 `st.tabs` 라 숨은 Preference 탭 본문도 매 rerun 실행된다. 그 안에서 「세션과 다르면
세션이 최신이다」로 판정하면, 남이 방금 고른 값이 이쪽 세션의 옛 값으로 되쓰인다. 두 사람이
번갈아 rerun 하는 동안 선택이 계속 뒤집히는데, 화면은 멈추지도 오류를 내지도 않아서
사용자에게는 「내가 고른 비교 대상이 저절로 되돌아간다」는 재현 불가 증상으로만 보인다.

되쓰기가 필요한 자리는 하나뿐이다 — 선택 위젯의 기본값은 `on_change` 를 부르지 않아
시나리오만 고른 순간에는 `revision_id=None` 으로 저장된다. 그 한 칸만 뒤늦게 채운다.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from capa_simulation.components.home_preference import (
    COMPARISON_REVISION_KEY,
    COMPARISON_SCENARIO_KEY,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository

SCRIPT = """
import streamlit as st

from capa_simulation.components.home_preference import _persist_comparison_choice

_persist_comparison_choice(st.session_state["database_path"])
st.write("done")
"""


def _saved_profile(database: Path) -> tuple[str | None, str | None]:
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    profile = repository.load_global_comparison_scenario()
    return profile.scenario_id, profile.revision_id


def _run(database: Path, scenario_id: str, revision_id: str | None) -> AppTest:
    app = AppTest.from_string(SCRIPT)
    app.session_state["database_path"] = str(database)
    app.session_state[COMPARISON_SCENARIO_KEY] = scenario_id
    if revision_id is not None:
        app.session_state[COMPARISON_REVISION_KEY] = revision_id
    app.run()
    assert not app.exception
    return app


def test_the_missing_revision_is_filled_in(tmp_path: Path) -> None:
    """`on_change` 가 남긴 `(S1, None)` 을 화면에 그려진 리비전으로 완성한다."""
    database = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    repository.replace_global_comparison_scenario("S1", None, source="테스트")

    _run(database, "S1", "R1")

    assert _saved_profile(database) == ("S1", "R1")


def test_another_users_choice_is_not_overwritten(tmp_path: Path) -> None:
    """프로필이 이미 완전하면 이쪽 세션 값과 달라도 손대지 않는다.

    세션에 `(S1, R1)` 을 들고 있는 사용자의 rerun 이 남이 고른 `(S2, R2)` 를 되쓰던 자리다.
    """
    database = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    repository.replace_global_comparison_scenario("S2", "R2", source="다른 사용자")

    _run(database, "S1", "R1")

    assert _saved_profile(database) == ("S2", "R2")


def test_a_different_scenario_with_a_blank_revision_is_left_alone(tmp_path: Path) -> None:
    """메우는 것은 **같은 시나리오**의 빈 리비전뿐이다. 남의 시나리오는 채워 주지 않는다."""
    database = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    repository.replace_global_comparison_scenario("S2", None, source="다른 사용자")

    _run(database, "S1", "R1")

    assert _saved_profile(database) == ("S2", None)


def test_an_untouched_default_does_not_claim_an_empty_profile(tmp_path: Path) -> None:
    """아무도 고르지 않은 상태에서 위젯 기본값이 공용 프로필을 차지하면 안 된다.

    사용자가 실제로 고른 값은 선택 위젯의 `on_change` 가 남긴다.
    """
    database = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()

    _run(database, "S1", "R1")

    assert _saved_profile(database) == (None, None)
