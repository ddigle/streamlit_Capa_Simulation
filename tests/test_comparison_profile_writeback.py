# Purpose: HOME 비교 대상 선택의 공용 프로필 되쓰기 조건과 활성 상태를 따르지 않는 라벨을 고정한다.

"""비교 대상 프로필은 **시나리오에 딸리지 않은 공용 값**이라 두 사용자가 같은 행을 쓴다.

HOME 은 `st.tabs` 라 숨은 Preference 탭 본문도 매 rerun 실행된다. 그 안에서 「세션과 다르면
세션이 최신이다」로 판정하면, 남이 방금 고른 값이 이쪽 세션의 옛 값으로 되쓰인다. 두 사람이
번갈아 rerun 하는 동안 선택이 계속 뒤집히는데, 화면은 멈추지도 오류를 내지도 않아서
사용자에게는 「내가 고른 비교 대상이 저절로 되돌아간다」는 재현 불가 증상으로만 보인다.

되쓰기가 필요한 자리는 하나뿐이다 — 선택 위젯의 기본값은 `on_change` 를 부르지 않아
시나리오만 고른 순간에는 `revision_id=None` 으로 저장된다. 그 한 칸만 뒤늦게 채운다.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import capa_simulation.components.home_preference as home_preference
from capa_simulation.components.home_preference import (
    COMPARISON_REVISION_KEY,
    COMPARISON_SCENARIO_KEY,
    _revision_choice,
    _scenario_choice,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository

SCRIPT = """
import streamlit as st

from capa_simulation.components.home_preference import _persist_comparison_choice

_persist_comparison_choice(
    st.session_state["database_path"], st.session_state["revision_ids"]
)
st.write("done")
"""


def _saved_profile(database: Path) -> tuple[str | None, str | None]:
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    profile = repository.load_global_comparison_scenario()
    return profile.scenario_id, profile.revision_id


def _run(
    database: Path,
    scenario_id: str,
    revision_id: str | None,
    revision_ids: tuple[str, ...] = ("R1",),
) -> AppTest:
    app = AppTest.from_string(SCRIPT)
    app.session_state["database_path"] = str(database)
    # 피커가 읽어 둔 「그 시나리오의 리비전 집합」. 프로필의 칸이 이 안에 있으면 메우지 않는다.
    app.session_state["revision_ids"] = revision_ids
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


def test_a_revision_from_another_scenario_is_replaced(tmp_path: Path) -> None:
    """시나리오만 바꾸면 **남의 리비전이 짝지어 저장된다.** 그 짝을 여기서 바로잡는다.

    두 선택 상자가 콜백 하나를 공유해 어느 쪽이 눌렸는지 모른다. 시나리오를 S1→S2 로
    바꾼 순간 세션에 남아 있던 S1 의 리비전과 함께 `(S2, S1의 리비전)` 이 저장된다.
    다음 rerun 에서 화면은 남의 리비전을 버리고 S2 의 기본값을 잡지만, 프로필의 칸은 비어
    있지 않으므로 「비었을 때만 메운다」로는 그 짝이 영영 남는다.

    판정은 「비었는가」가 아니라 **「그 시나리오의 리비전인가」**다.
    """
    database = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    repository.replace_global_comparison_scenario("S2", "S1-R1", source="시나리오만 바꾼 직후")

    _run(database, "S2", "S2-R1", revision_ids=("S2-R1", "S2-R2"))

    assert _saved_profile(database) == ("S2", "S2-R1")


def test_a_valid_revision_of_the_same_scenario_is_left_alone(tmp_path: Path) -> None:
    """남이 고른 것이 **그 시나리오의 멀쩡한 리비전**이면 손대지 않는다.

    위 검사만 있으면 「세션 값으로 늘 덮는다」로 고쳐도 통과한다. 그러면 오늘 없앤 핑퐁이
    되살아나므로 반대편을 같이 못박는다.
    """
    database = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    repository.replace_global_comparison_scenario("S2", "S2-R2", source="다른 사용자")

    _run(database, "S2", "S2-R1", revision_ids=("S2-R1", "S2-R2"))

    assert _saved_profile(database) == ("S2", "S2-R2")


def _two_revision_scenario(database: Path) -> tuple[str, str, str]:
    """내장 시드 공식 시나리오에 리비전 하나를 더 저장한다. (시나리오, 공식 리비전, 새 리비전)."""
    from capa_simulation.application_bootstrap import ensure_initial_scenario

    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    release = ensure_initial_scenario(repository).release
    assert release is not None
    base = repository.load_revision(release.revision_id)
    saved = repository.save_revision(
        base.scenario.scenario_id,
        {name: frame.copy() for name, frame in base.tables.items()},
        base.preset,
        revision_name="비교용",
    )
    return (
        str(base.scenario.scenario_id),
        str(base.revision.revision_id),
        str(saved.revision.revision_id),
    )


def _profile_version(database: Path) -> int:
    return DuckDBScenarioRepository(database).load_global_comparison_scenario().version


PICKER_SCRIPT = """
import streamlit as st

from capa_simulation.components.home_preference import _render_comparison_picker

_render_comparison_picker(st.session_state["database_path"])
"""


def test_the_comparison_labels_do_not_follow_the_active_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """선택지 라벨은 어느 리비전이 활성이든 같다. 활성 표시는 상자 아래 캡션이 맡는다.

    Streamlit 1.63 선택 상자는 고른 항목의 **라벨 글자**를 주고받는다. 라벨에 「· 현재 활성」·
    「· 현재 시나리오」를 붙이던 때는 시나리오를 불러와 활성이 바뀌면 브라우저가 옛 라벨을
    되보냈고, 서버는 그것을 바뀐 값으로 읽어 앱 전체를 다시 돌리고 그 라벨 글자를 리비전 id
    자리에 공용 프로필로 저장했다(2026-10-08 안정화 점검, 브라우저 계측).
    """
    database = tmp_path / "scenario.duckdb"
    scenario_id, official_id, other_id = _two_revision_scenario(database)
    repository = DuckDBScenarioRepository(database)
    # 비교 대상은 선택지 첫 항목(최신 리비전)이다 — 옛 결함이 실제로 드러난 자리다.
    repository.replace_global_comparison_scenario(scenario_id, other_id, source="테스트")
    version = _profile_version(database)
    monkeypatch.setattr(
        home_preference,
        "active_persisted_revision_id",
        lambda: st.session_state.get("active_revision"),
    )
    app = AppTest.from_string(PICKER_SCRIPT, default_timeout=120)
    app.session_state["database_path"] = str(database)

    seen: list[tuple[tuple[str, ...], tuple[str, ...], list[str]]] = []
    for active in ("다른-시나리오의-리비전", other_id, official_id):
        app.session_state["active_revision"] = active
        app.run()
        assert not app.exception, [element.message for element in app.exception]
        seen.append(
            (
                tuple(app.selectbox(key=COMPARISON_SCENARIO_KEY).options),
                tuple(app.selectbox(key=COMPARISON_REVISION_KEY).options),
                [str(caption.value) for caption in app.caption],
            )
        )

    labels = {(scenarios, revisions) for scenarios, revisions, _ in seen}
    assert len(labels) == 1, f"활성 리비전에 따라 선택지 라벨이 바뀌었습니다: {labels}"
    scenarios, revisions = next(iter(labels))
    assert not [label for label in (*scenarios, *revisions) if "현재" in label]
    assert seen[0][2] == []
    assert any("지금 화면이 쓰고 있는 리비전" in caption for caption in seen[1][2])
    assert any("리비전이 올라와 있습니다" in caption for caption in seen[2][2])
    assert app.selectbox(key=COMPARISON_REVISION_KEY).value == other_id
    assert _profile_version(database) == version, "고르지 않았는데 공용 프로필을 다시 썼습니다."


SAVE_SCRIPT = """
import streamlit as st

import capa_simulation.components.home_preference as home_preference

getattr(home_preference, st.session_state["callback"])(st.session_state["database_path"])
st.write("done")
"""


def _save(
    database: Path,
    scenario_id: object,
    revision_id: object,
    *,
    callback: str = "_save_comparison_revision",
) -> None:
    """두 상자의 콜백 가운데 하나를 그 세션 값으로 부른다. 기본은 리비전 상자의 콜백이다."""
    app = AppTest.from_string(SAVE_SCRIPT, default_timeout=120)
    app.session_state["database_path"] = str(database)
    app.session_state["callback"] = callback
    app.session_state[COMPARISON_SCENARIO_KEY] = scenario_id
    app.session_state[COMPARISON_REVISION_KEY] = revision_id
    app.run()
    assert not app.exception, [element.message for element in app.exception]


def test_the_same_choice_is_not_written_to_the_profile_again(tmp_path: Path) -> None:
    """프로필과 같은 짝이면 쓰지 않는다. 바뀐 짝은 한 번 쓴다.

    콜백은 Streamlit 이 「바뀌었다」고 본 회차마다 불린다. 같은 항목을 다른 글자로 되보낸
    경우에도 그렇게 보므로, 같은 값을 다시 쓰면 아무도 고르지 않았는데 공용 프로필의
    `version` 이 오른다.
    """
    database = tmp_path / "scenario.duckdb"
    scenario_id, official_id, other_id = _two_revision_scenario(database)
    DuckDBScenarioRepository(database).replace_global_comparison_scenario(
        scenario_id, official_id, source="테스트"
    )
    version = _profile_version(database)

    _save(database, scenario_id, official_id)
    assert _profile_version(database) == version

    _save(database, scenario_id, other_id)
    assert _saved_profile(database) == (scenario_id, other_id)
    assert _profile_version(database) == version + 1


def test_a_label_sent_back_instead_of_an_id_is_not_written(tmp_path: Path) -> None:
    """브라우저가 되보낸 **라벨 글자**는 시나리오·리비전 id 가 아니다. 프로필에 쓰지 않는다."""
    database = tmp_path / "scenario.duckdb"
    scenario_id, official_id, _ = _two_revision_scenario(database)
    DuckDBScenarioRepository(database).replace_global_comparison_scenario(
        scenario_id, official_id, source="테스트"
    )
    version = _profile_version(database)

    _save(database, scenario_id, "r1 · 초기 리비전 · 현재 활성")
    _save(database, "내장 시드 시나리오 · 현재 시나리오", official_id)
    _save(
        database,
        "내장 시드 시나리오 · 현재 시나리오",
        official_id,
        callback="_save_comparison_scenario",
    )

    assert _saved_profile(database) == (scenario_id, official_id)
    assert _profile_version(database) == version


class _FakeRepository:
    """시나리오 S1·S2 와 각자의 리비전 둘. 두 콜백이 읽는 두 목록만 있다."""

    def list_scenarios(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(scenario_id="S1"), SimpleNamespace(scenario_id="S2")]

    def list_revisions(self, scenario_id: str) -> list[SimpleNamespace]:
        return [SimpleNamespace(revision_id=f"{scenario_id}-R{number}") for number in (1, 2)]


def test_each_box_saves_only_what_it_chooses() -> None:
    """시나리오 상자는 시나리오만(리비전 칸은 비워 — 피커가 메운다), 리비전 상자는 그 시나리오의
    실제 리비전만 낸다. 앞 시나리오의 리비전이 따라와도 시나리오 선택은 버려지지 않는다.
    """
    repository: Any = _FakeRepository()

    assert _scenario_choice(repository, "S2") == ("S2", None)
    assert _scenario_choice(repository, None) == (None, None)
    assert _scenario_choice(repository, "S2 의 라벨 글자") is None
    assert _revision_choice(repository, "S2", "S2-R1") == ("S2", "S2-R1")
    assert _revision_choice(repository, "S2", "S1-R1") is None
    assert _revision_choice(repository, "S2", "r1 · 초기") is None
    assert _revision_choice(repository, None, "S1-R1") is None
    assert _revision_choice(repository, "S1", None) is None


def _two_scenarios(database: Path) -> tuple[str, str, str, str, str]:
    """내장 시드 시나리오 S1 과, 리비전이 둘인 시나리오 S2 를 만든다.

    (S1, S1 공식 리비전, S2, S2 옛 리비전, S2 새 리비전). 선택지는 리비전 번호 내림차순이라 S2 의
    첫 항목은 새 리비전이다.
    """
    from capa_simulation.application_bootstrap import ensure_initial_scenario
    from capa_simulation.persistence.models import ScenarioCreate

    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    release = ensure_initial_scenario(repository).release
    assert release is not None
    base = repository.load_revision(release.revision_id)
    tables = {name: frame.copy() for name, frame in base.tables.items()}
    second = repository.create_scenario(
        ScenarioCreate(
            scenario_name="비교용 시나리오",
            source_simulation_code="COMPARE",
            source_simulation_name="비교용 시나리오",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="duckdb-rq-snapshot-v3",
        ),
        tables,
        base.preset,
    )
    newer = repository.save_revision(
        second.scenario.scenario_id, tables, base.preset, revision_name="비교용 새 리비전"
    )
    return (
        str(base.scenario.scenario_id),
        str(base.revision.revision_id),
        str(second.scenario.scenario_id),
        str(second.revision.revision_id),
        str(newer.revision.revision_id),
    )


def test_choosing_a_scenario_is_saved_even_when_the_profile_already_points_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """공용 프로필이 이미 그 시나리오(다른 리비전)를 가리켜도, 고른 시나리오는 화면 그대로 저장된다.

    사내 공용 DB 라 다른 탭·사용자가 프로필을 바꾸는 일이 흔하다. 이 세션은 (S1, S1 리비전)을 보고
    있고 프로필은 남이 고른 (S2, S2 옛 리비전)일 때 비교 시나리오를 S2 로 고르면, 화면은 S2 의 첫
    리비전(새 리비전)과 견준다. 프로필도 그 짝이어야 한다 — 「고르는 것이 곧 저장」.

    콜백 하나를 두 상자가 나눠 쓰던 때는 시나리오 콜백이 앞 시나리오의 리비전을 함께 받아 「같은
    시나리오의 엉뚱한 리비전(옛 라벨)」으로 읽고 쓰지 않았다. 프로필이 이미 S2 의 멀쩡한 리비전이라
    `_persist_comparison_choice` 도 메우지 않아, 화면과 프로필이 갈렸다(2026-10-08 적대적 리뷰 F1).
    """
    database = tmp_path / "scenario.duckdb"
    s1, s1_revision, s2, s2_older, s2_newer = _two_scenarios(database)
    DuckDBScenarioRepository(database).replace_global_comparison_scenario(
        s1, s1_revision, source="이 세션이 본 값"
    )
    monkeypatch.setattr(home_preference, "active_persisted_revision_id", lambda: None)
    app = AppTest.from_string(PICKER_SCRIPT, default_timeout=120)
    app.session_state["database_path"] = str(database)
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    assert app.selectbox(key=COMPARISON_SCENARIO_KEY).value == s1

    # 다른 사용자가 같은 서버에서 공용 프로필을 (S2, 옛 리비전)으로 바꾼다. 그 사용자의 저장도
    # 프로세스 공용 캐시를 비우므로 여기서 같이 비운다.
    DuckDBScenarioRepository(database).replace_global_comparison_scenario(
        s2, s2_older, source="다른 사용자"
    )
    from capa_simulation.persistence.cache import clear_global_comparison_scenario_cache

    clear_global_comparison_scenario_cache()

    app.selectbox(key=COMPARISON_SCENARIO_KEY).set_value(s2).run()
    assert not app.exception, [element.message for element in app.exception]
    shown = app.selectbox(key=COMPARISON_REVISION_KEY).value
    assert shown == s2_newer
    assert _saved_profile(database) == (s2, shown), (
        "화면은 S2 의 첫 리비전과 견주는데 공용 프로필에는 남이 고른 리비전이 남았습니다."
    )
