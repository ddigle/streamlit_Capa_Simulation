# Purpose: HOME 제목 줄 주요 Case 칩의 글자·풍선·칠하기·상태와 사이드바와 같은 불러오기를 지킨다.

"""HOME 제목 줄 끝의 주요 Case 칩 셋(2026-10-23 사용자 결정 — 시안 C · 동작 (가)).

칩을 누르면 사이드바에서 그 리비전을 불러온 것과 **똑같아야** 한다 — 세션 활성 시나리오, 사이드바
「시나리오」 칸과 그 아래 알림, 머리 띠 위 줄까지. 그래서 실제 DB 와 실제 활성화로 사이드바 필드·
팝업·칩·HOME 탭을 한 스크립트에 세워 본다(`app.py` 의 차례 — 필드와 팝업이 페이지보다 먼저다).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

import capa_simulation.components.scenario_status as scenario_status
import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.home_main_case_chips import (
    CASE1_CHIP_KEY,
    CASE2_CHIP_KEY,
    CHIP_ROW_KEY,
    MISSING_REVISION_HELP,
    OFFICIAL_CHIP_KEY,
    OUTSIDE_SLOTS_TEXT,
    SlotChip,
    changed_slot_notice,
    chip_style,
    outside_slots,
    slot_chips,
)
from capa_simulation.components.intro_summary import _SESSION_KEY as OFFICIAL_SESSION_KEY
from capa_simulation.components.intro_summary import OfficialIdentity
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.scenario_status import (
    LOAD_MODE,
    SCENARIO_DIALOG_KEY,
    SCENARIO_DIALOG_MODE_KEY,
    SCENARIO_FIELD_KEY,
    SIDEBAR_REVISION_KEY,
    SIDEBAR_SCENARIO_KEY,
)
from capa_simulation.design import tokens
from capa_simulation.home_state import HOME_MAIN_TAB, HOME_PREFERENCE_TAB, HOME_TAB_KEY
from capa_simulation.persistence.cache import (
    clear_global_main_cases_cache,
    clear_scenario_snapshot_cache,
)
from capa_simulation.persistence.models import ScenarioCreate
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import (
    ACTIVE_PERSISTED_REVISION_ID_KEY,
    ACTIVE_PERSISTED_SCENARIO_ID_KEY,
    ACTIVE_PERSISTED_SESSION_REVISION_KEY,
)
from capa_simulation.services.main_cases import (
    NO_OFFICIAL_LABEL,
    SLOT_MISSING,
    SLOT_OK,
    SLOT_UNSET,
    MainCaseSlot,
    SlotStatus,
)

# `app.py` 차례 — 공식버전 부트스트랩·프리셋 적용 → 사이드바 시나리오 필드 → 열린 팝업 → 페이지(제목
# 줄 칩·칩 알림·HOME 탭). 공식버전은 입장 화면 요약이 세션에 두는 칸(`intro_summary._SESSION_KEY`)에
# 시험이 직접 넣는다 — 칩과 칩 콜백이 둘 다 그 칸을 읽는다. 실제 `app.py` 의 배선은
# `test_app_navigation.py` 가 본다. 머리 띠 위 줄은 `header_lines` 를 그대로 불러 세션에 적는다(머리
# 띠는 CSS 가상요소라 AppTest 가 못 읽는다).
CHIPS_SCRIPT = """
from pathlib import Path

import streamlit as st

import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path(st.session_state["database_path"])

from capa_simulation.components.app_header import header_lines
from capa_simulation.components.home_main_case_chips import (
    render_main_case_chip_notice,
    render_main_case_chips,
)
from capa_simulation.components.intro_summary import latest_official_revision
from capa_simulation.components.page_header import render_page_header_with_status
from capa_simulation.components.scenario_status import (
    render_scenario_field,
    scenario_dialog_is_open,
    show_scenario_dialog,
)
from capa_simulation.components.tab_state import stateful_tabs
from capa_simulation.home_state import HOME_TAB_KEY, HOME_TAB_LABELS
from capa_simulation.scenario_activation import (
    active_scenario_label,
    bootstrap_latest_official_scenario,
    has_unsaved_scenario_changes,
)
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
apply_pending_scenario_preset()
render_scenario_field()
if scenario_dialog_is_open():
    show_scenario_dialog("home.py")
render_page_header_with_status(
    "Capa LOB Summary",
    trailing=lambda: render_main_case_chips(st.session_state["database_path"]),
)
render_main_case_chip_notice()
stateful_tabs(HOME_TAB_LABELS, key=HOME_TAB_KEY)
st.session_state["test_header_top"] = header_lines(
    active_scenario_label(),
    official=latest_official_revision(),
    unsaved=has_unsaved_scenario_changes(),
)[0]
"""


class Seeded:
    """내장 시드 공식버전(S1) 과 리비전이 둘인 「증설안」(S2). Case1 은 S2 의 새 리비전이다."""

    def __init__(self, database: Path) -> None:
        from capa_simulation.application_bootstrap import ensure_initial_scenario

        self.database = database
        self.repository = DuckDBScenarioRepository(database)
        self.repository.initialize()
        release = ensure_initial_scenario(self.repository).release
        assert release is not None
        base = self.repository.load_revision(release.revision_id)
        tables = {name: frame.copy() for name, frame in base.tables.items()}
        second = self.repository.create_scenario(
            ScenarioCreate(
                scenario_name="증설안",
                source_simulation_code="CASE",
                source_simulation_name="증설안",
                source_type="DUCKDB_SCENARIO_CLONE",
                pipeline_version="duckdb-rq-snapshot-v3",
            ),
            tables,
            base.preset,
        )
        newer = self.repository.save_revision(
            second.scenario.scenario_id, tables, base.preset, revision_name="증설안 확정"
        )
        self.official_scenario = base.scenario.scenario_id
        self.official_revision = base.revision.revision_id
        self.case_scenario = second.scenario.scenario_id
        self.older_revision = second.revision.revision_id
        self.newer_revision = newer.revision.revision_id
        latest = self.repository.latest_official_release()
        assert latest is not None
        self.official = OfficialIdentity(
            release_no=latest.release_no,
            release_name=latest.release_name,
            scenario_id=latest.scenario_id,
            scenario_name=latest.scenario_name,
            revision_id=latest.revision_id,
            revision_no=latest.revision_no,
        )
        self.set_case(1, self.case_scenario, self.newer_revision)

    def set_case(self, case_no: int, scenario_id: str | None, revision_id: str | None) -> None:
        self.repository.replace_global_main_case(case_no, scenario_id, revision_id, source="시험")
        clear_global_main_cases_cache()


@pytest.fixture
def seeded(tmp_path: Path) -> Seeded:
    clear_global_main_cases_cache()
    return Seeded(tmp_path / "scenario.duckdb")


def _app(seeded: Seeded, *, official: bool = True) -> AppTest:
    app = AppTest.from_string(CHIPS_SCRIPT, default_timeout=120)
    app.session_state["database_path"] = str(seeded.database)
    if official:
        app.session_state[OFFICIAL_SESSION_KEY] = {"official": seeded.official._asdict()}
    return _ran(app.run())


def _ran(app: AppTest) -> AppTest:
    assert not app.exception, [element.message for element in app.exception]
    return app


def _chip(app: AppTest, key: str) -> tuple[str, str, str, bool]:
    """(글자, 풍선, 단추 종류, 잠김)."""
    button = app.button(key=key)
    return str(button.label), str(button.help), str(button.proto.type), bool(button.disabled)


def _active(app: AppTest) -> tuple[object, object]:
    state = app.session_state
    return state[ACTIVE_PERSISTED_SCENARIO_ID_KEY], state[ACTIVE_PERSISTED_REVISION_ID_KEY]


def _style(app: AppTest) -> str:
    """칩 모양 CSS(스타일만 든 `st.html`)."""
    return " ".join(
        str(element.proto.body)
        for element in app.get("html")
        if CHIP_ROW_KEY in str(element.proto.body)
    )


HIDDEN_OUTSIDE_RULE = (
    f'.st-key-{CHIP_ROW_KEY} [data-testid="stCaptionContainer"] {{ visibility: hidden; }}'
)


def _outside_shown(app: AppTest) -> bool:
    """칩 줄 앞 「슬롯 밖」 이 보이는가.

    글자는 늘 그리고(자리를 잡아 둔다) 슬롯 안이면 CSS 로 감춘다.
    """
    captions = [str(item.value) for item in app.caption]
    assert captions.count(OUTSIDE_SLOTS_TEXT) == 1, captions
    return HIDDEN_OUTSIDE_RULE not in _style(app)


def _notices(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.warning]


def test_three_chips_carry_only_their_short_names_and_tell_the_rest_on_hover(
    seeded: Seeded,
) -> None:
    """칩 글자는 `공식 vN` · `Case1` · `Case2` 뿐이고 시나리오·리비전은 풍선이 말한다.

    새 세션은 공식버전으로 열리므로 공식 칩만 칠하고 「슬롯 밖」은 없다. 미지정 Case2 는 점선이고
    누를 수 있다(누르면 `Preference`).
    """
    app = _app(seeded)
    official = seeded.official

    assert _chip(app, OFFICIAL_CHIP_KEY) == (
        f"공식 v{official.release_no}",
        literal_markdown(
            f"공식 v{official.release_no} · {official.scenario_name} "
            f"r{official.revision_no} · {official.release_name}"
        ),
        "primary",
        False,
    )
    assert _chip(app, CASE1_CHIP_KEY) == (
        "Case1",
        literal_markdown("증설안 · r2 · 증설안 확정"),
        "secondary",
        False,
    )
    assert _chip(app, CASE2_CHIP_KEY) == ("Case2", "Case2 · 지정 안 함", "secondary", False)
    assert f".st-key-{CASE2_CHIP_KEY} button {{ border-style: dashed; }}" in _style(app)
    assert f".st-key-{CASE1_CHIP_KEY} button" not in _style(app)
    assert not _outside_shown(app)
    # 칩은 제목 줄 끝 칸이다 — 제목은 그대로 「Capa LOB Summary」.
    assert [str(item.value) for item in app.title] == ["Capa LOB Summary"]


def test_clicking_a_case_loads_it_exactly_like_the_sidebar(seeded: Seeded) -> None:
    """칩을 누르면 활성 시나리오가 그 리비전이 되고 사이드바 칸·알림·머리 띠가 함께 바뀐다.

    알림 글자도 사이드바 팝업의 「불러오기」 그대로다(한 길 — `load_saved_revision`). 그 칩이
    칠해지고 공식 칩은 풀린다. 공식 칩을 누르면 공식버전으로 돌아온다.
    """
    app = _app(seeded)
    assert _active(app) == (seeded.official_scenario, seeded.official_revision)

    app = _ran(app.button(key=CASE1_CHIP_KEY).click().run())

    assert _active(app) == (seeded.case_scenario, seeded.newer_revision)
    assert app.button(key=SCENARIO_FIELD_KEY).label == "증설안 · r2"
    assert [item.value for item in app.success] == ["증설안 r2를 불러왔습니다."]
    assert app.session_state["test_header_top"] == "증설안 · r2 증설안 확정 · 저장된 리비전"
    assert _chip(app, CASE1_CHIP_KEY)[2] == "primary"
    assert _chip(app, OFFICIAL_CHIP_KEY)[2] == "secondary"
    assert SCENARIO_DIALOG_KEY not in app.session_state

    app = _ran(app.button(key=OFFICIAL_CHIP_KEY).click().run())

    assert _active(app) == (seeded.official_scenario, seeded.official_revision)
    official = seeded.official
    assert app.session_state["test_header_top"].endswith(f"· 공식 v{official.release_no}")
    assert _chip(app, OFFICIAL_CHIP_KEY)[2] == "primary"
    assert _chip(app, CASE1_CHIP_KEY)[2] == "secondary"


def test_the_painted_chip_does_nothing_when_clicked_again(seeded: Seeded) -> None:
    """이미 그 Case 를 보고 있으면(편집 없음) 다시 불러오지 않는다 — 알림도 서지 않는다."""
    app = _app(seeded)
    app = _ran(app.button(key=OFFICIAL_CHIP_KEY).click().run())

    assert _active(app) == (seeded.official_scenario, seeded.official_revision)
    assert [item.value for item in app.success] == []


def test_a_second_press_on_the_chip_just_loaded_keeps_the_load_notice(
    seeded: Seeded, monkeypatch: pytest.MonkeyPatch
) -> None:
    """칩을 0.15~0.3초 간격으로 두 번 누르면 둘째 누름은 이미 올린 짝이라 아무것도 하지 않고
    끝나는데, 첫 회차가 꺼내 그린 「…을 불러왔습니다.」 를 그 회차가 다시 그리며 지웠다
    (2026-10-26 E2E — 18/18). 올린 알림을 쓰기 알림 표지에 적어 그 창(`TRAILING_PRESS_SECONDS`)
    안의 회차가 다시 그린다. 창이 지난 누름은 전처럼 아무것도 알리지 않는다. AppTest 의 회차
    사이는 창보다 짧아 창은 시험이 정한다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    app = _app(seeded)
    app = _ran(app.button(key=CASE1_CHIP_KEY).click().run())
    assert [item.value for item in app.success] == ["증설안 r2를 불러왔습니다."]

    app = _ran(app.button(key=CASE1_CHIP_KEY).click().run())

    assert _active(app) == (seeded.case_scenario, seeded.newer_revision)
    assert [item.value for item in app.success] == ["증설안 r2를 불러왔습니다."]

    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    app = _ran(app.button(key=CASE1_CHIP_KEY).click().run())
    assert [item.value for item in app.success] == []


def test_painting_needs_the_same_revision_and_otherwise_says_outside_the_slots(
    seeded: Seeded,
) -> None:
    """같은 시나리오라도 리비전이 다르면 칠하지 않고, 칩 줄 끝에 「슬롯 밖」 한 마디가 선다."""
    seeded.set_case(1, seeded.case_scenario, seeded.older_revision)
    app = _app(seeded)
    app = _ran(app.button(key=CASE1_CHIP_KEY).click().run())
    assert _active(app) == (seeded.case_scenario, seeded.older_revision)
    assert _chip(app, CASE1_CHIP_KEY)[2] == "primary"

    # 다른 세션이 Case1 을 같은 시나리오의 새 리비전으로 바꿨다.
    seeded.set_case(1, seeded.case_scenario, seeded.newer_revision)
    app = _ran(app.run())

    assert [_chip(app, key)[2] for key in (OFFICIAL_CHIP_KEY, CASE1_CHIP_KEY, CASE2_CHIP_KEY)] == [
        "secondary",
        "secondary",
        "secondary",
    ]
    assert _outside_shown(app)


def test_an_unset_case_opens_the_preference_tab(seeded: Seeded) -> None:
    """미지정 칩은 불러오지 않고 HOME `Preference` 탭(「주요 Case」 상자)으로 옮긴다."""
    app = _app(seeded)
    assert app.session_state[HOME_TAB_KEY] == HOME_MAIN_TAB

    app = _ran(app.button(key=CASE2_CHIP_KEY).click().run())

    assert app.session_state[HOME_TAB_KEY] == HOME_PREFERENCE_TAB
    assert _active(app) == (seeded.official_scenario, seeded.official_revision)
    assert SCENARIO_DIALOG_KEY not in app.session_state


def test_a_vanished_revision_and_a_missing_official_lock_their_chips(seeded: Seeded) -> None:
    """가리키던 리비전이 없으면 그 칩을 잠그고 다시 지정하라고 한다. 공식버전이 없어도 잠근다."""
    seeded.set_case(2, seeded.case_scenario, "revision-gone")
    app = _app(seeded, official=False)

    assert _chip(app, CASE2_CHIP_KEY) == (
        "Case2",
        literal_markdown(f"Case2 · {MISSING_REVISION_HELP}"),
        "secondary",
        True,
    )
    assert _chip(app, OFFICIAL_CHIP_KEY) == ("공식", NO_OFFICIAL_LABEL, "secondary", True)
    assert f".st-key-{CASE2_CHIP_KEY} button" not in _style(app)


@pytest.mark.parametrize("edit", ["unsaved", "pending"])
def test_edits_go_through_the_same_confirmation_as_the_sidebar(seeded: Seeded, edit: str) -> None:
    """저장하지 않은 편집·적용 전 편집이 있으면 곧바로 올리지 않고 사이드바 팝업을 그 Case 로 연다.

    확인 칸 「변경을 버리고 불러오기」를 체크해야 「불러오기」가 풀리고, 누르면 그 Case 가 올라온다.
    """
    app = _app(seeded)
    if edit == "unsaved":
        # 저장 표시와 지금 세션 번호가 어긋나면 미저장이다(`has_unsaved_scenario_changes`).
        app.session_state[ACTIVE_PERSISTED_SESSION_REVISION_KEY] = -1
    else:
        app.session_state["scenario_pending_edit_registry"] = {
            "reference_data.py": ("기준 정보", {}, {"test_staged_upeh": "UPEH"})
        }
        app.session_state["test_staged_upeh"] = "붙여넣기 대기"
    app = _ran(app.run())

    app = _ran(app.button(key=CASE1_CHIP_KEY).click().run())

    assert _active(app) == (seeded.official_scenario, seeded.official_revision)
    assert app.session_state[SCENARIO_DIALOG_KEY] is True
    assert app.session_state[SCENARIO_DIALOG_MODE_KEY] == LOAD_MODE
    assert app.session_state[SIDEBAR_SCENARIO_KEY] == seeded.case_scenario
    assert app.session_state[SIDEBAR_REVISION_KEY] == seeded.newer_revision
    confirm = app.checkbox(key="sidebar_discard_unsaved_changes")
    assert confirm.label == "변경을 버리고 불러오기"
    assert app.button(key="sidebar_load_revision").disabled

    app = _ran(confirm.check().run())
    app = _ran(app.button(key="sidebar_load_revision").click().run())

    assert _active(app) == (seeded.case_scenario, seeded.newer_revision)
    assert SCENARIO_DIALOG_KEY not in app.session_state
    assert app.button(key=SCENARIO_FIELD_KEY).label == "증설안 · r2"


def test_a_revision_the_load_refuses_leaves_the_scenario_and_says_why(seeded: Seeded) -> None:
    """사이드바가 막는 리비전(옛 리비전 호환)은 칩도 막고, 제목 줄 밑에 까닭을 한 번 적는다."""
    app = _app(seeded)
    with patch.object(scenario_status, "revision_block_reason", lambda _tables: "옛 리비전입니다"):
        app = _ran(app.button(key=CASE1_CHIP_KEY).click().run())

    assert _active(app) == (seeded.official_scenario, seeded.official_revision)
    assert [item.value for item in app.warning] == ["옛 리비전입니다"]
    app = _ran(app.run())
    assert [item.value for item in app.warning] == []


def test_a_chip_drawn_before_another_session_changed_its_case_loads_nothing(
    seeded: Seeded,
) -> None:
    """콜백 인자는 그린 회차의 짝이다 — 그사이 다른 세션이 Case1 을 다시 지정했으면 칩은 낡았다.

    콜백이 누르는 순간 슬롯을 다시 풀어 그린 짝과 다르면 아무것도 올리지 않고 알린다. 예전 Case 가
    올라오면 「Case1 을 눌렀는데 Case1 이 아닌 것」이 된다. 새로 그린 칩을 누르면 새 Case 가 온다.
    """
    app = _app(seeded)
    seeded.set_case(1, seeded.case_scenario, seeded.older_revision)

    app = _ran(app.button(key=CASE1_CHIP_KEY).click().run())

    assert _active(app) == (seeded.official_scenario, seeded.official_revision)
    assert _notices(app) == [changed_slot_notice(1)]
    assert [item.value for item in app.success] == []
    assert _chip(app, CASE1_CHIP_KEY)[:3] == (
        "Case1",
        literal_markdown("증설안 · r1 · 초기 리비전"),
        "secondary",
    )

    app = _ran(app.button(key=CASE1_CHIP_KEY).click().run())

    assert _active(app) == (seeded.case_scenario, seeded.older_revision)
    assert _notices(app) == []
    assert _chip(app, CASE1_CHIP_KEY)[2] == "primary"


def test_a_chip_whose_scenario_was_archived_meanwhile_loads_nothing(seeded: Seeded) -> None:
    """그사이 가리키던 시나리오가 보관됐으면 낡은 칩은 그것을 올리지 않는다.

    사이드바 팝업은 보관 시나리오를 고를 수 없다 — 칩이 올리면 「사이드바와 똑같다」가 깨지고 저장
    구획이 막힌다. 저장소가 보관하면서 그 Case 를 비우므로 새로 그린 칩은 「지정 안 함」 점선 칩이다
    (잠금이 아니다 — 잠금은 저장소 밖에서 고친 DB 처럼 찾지 못하는 짝만).
    """
    app = _app(seeded)
    seeded.repository.archive_scenario(seeded.case_scenario)
    clear_scenario_snapshot_cache()
    clear_global_main_cases_cache()

    app = _ran(app.button(key=CASE1_CHIP_KEY).click().run())

    assert _active(app) == (seeded.official_scenario, seeded.official_revision)
    assert _notices(app) == [changed_slot_notice(1)]
    assert app.button(key=SCENARIO_FIELD_KEY).label != "증설안 · r2"
    assert _chip(app, CASE1_CHIP_KEY) == ("Case1", "Case1 · 지정 안 함", "secondary", False)
    assert (
        f".st-key-{CASE1_CHIP_KEY} button, .st-key-{CASE2_CHIP_KEY} button"
        " { border-style: dashed; }"
    ) in _style(app)


def test_an_official_chip_drawn_before_the_official_changed_loads_nothing(seeded: Seeded) -> None:
    """공식 칩도 누르는 순간 이 세션이 확인한 공식버전으로 다시 푼다 — 그린 뒤 바뀌었으면 알린다."""
    app = _app(seeded)
    official = seeded.official._replace(
        release_no=seeded.official.release_no + 1,
        scenario_id=seeded.case_scenario,
        scenario_name="증설안",
        revision_id=seeded.newer_revision,
        revision_no=2,
    )
    app.session_state[OFFICIAL_SESSION_KEY] = {"official": official._asdict()}

    app = _ran(app.button(key=OFFICIAL_CHIP_KEY).click().run())

    assert _active(app) == (seeded.official_scenario, seeded.official_revision)
    assert _notices(app) == [changed_slot_notice(0)]
    assert _chip(app, OFFICIAL_CHIP_KEY)[0] == f"공식 v{official.release_no}"


def test_an_official_chip_drawn_before_a_new_release_elsewhere_loads_nothing(
    seeded: Seeded,
) -> None:
    """다른 곳에서 새 공식버전을 발행한 뒤 낡은 공식 칩을 누르면 옛 공식버전을 올리지 않는다.

    세션의 공식버전은 입장 화면 요약이 30초마다 보는 값이라 그린 짝과 다시 푼 짝이 함께 낡는다 —
    콜백이 저장소의 지금 공식버전과 대조하고, 다음 회차가 곧바로 다시 확인하게 세션 값을 버린다.
    """
    app = _app(seeded)
    app = _ran(app.button(key=CASE1_CHIP_KEY).click().run())
    assert _active(app) == (seeded.case_scenario, seeded.newer_revision)
    seeded.repository.publish_official_revision(
        seeded.case_scenario, seeded.older_revision, release_name="다른 세션 발행"
    )

    app = _ran(app.button(key=OFFICIAL_CHIP_KEY).click().run())

    assert _active(app) == (seeded.case_scenario, seeded.newer_revision)
    assert _notices(app) == [changed_slot_notice(0)]
    assert OFFICIAL_SESSION_KEY not in app.session_state


def test_unsaved_edits_paint_no_chip_and_do_not_say_outside_the_slots(seeded: Seeded) -> None:
    """저장하지 않은 편집이 있으면 칠하지 않는다 — 머리 띠·사이드바 배지처럼 「미저장」이 먼저다.

    편집본은 어느 저장 리비전과도 같은 내용이 아니다. 그렇다고 「슬롯 밖」 도 아니다 — 올라온 저장
    리비전은 여전히 공식버전이다.
    """
    app = _app(seeded)
    app.session_state[ACTIVE_PERSISTED_SESSION_REVISION_KEY] = -1
    app = _ran(app.run())

    assert app.session_state["test_header_top"].endswith("미저장 변경")
    assert [_chip(app, key)[2] for key in (OFFICIAL_CHIP_KEY, CASE1_CHIP_KEY, CASE2_CHIP_KEY)] == [
        "secondary",
        "secondary",
        "secondary",
    ]
    assert not _outside_shown(app)


def _slot(title: str, status: SlotStatus, pair: tuple[str | None, str | None]) -> MainCaseSlot:
    return MainCaseSlot(title, f"{title} 글자", pair[0], pair[1], status)


def test_chips_paint_every_slot_on_the_active_revision_and_lock_what_cannot_load() -> None:
    """Case 가 공식버전과 같은 리비전이면 둘 다 칠한다. 공식 슬롯 미지정은 점선이 아닌 잠금이다."""
    slots = (
        _slot("공식버전", SLOT_OK, ("s1", "r1")),
        _slot("Case1", SLOT_OK, ("s1", "r1")),
        _slot("Case2", SLOT_MISSING, ("s2", "gone")),
    )
    chips = slot_chips(slots, official_release_no=4, active=("s1", "r1"))
    assert [(chip.text, chip.painted, chip.disabled) for chip in chips] == [
        ("공식 v4", True, False),
        ("Case1", True, False),
        ("Case2", False, True),
    ]
    assert not outside_slots(chips, ("s1", "r1"))
    assert chips[2].target == (None, None)

    unset = (
        _slot("공식버전", SLOT_UNSET, (None, None)),
        _slot("Case1", SLOT_UNSET, (None, None)),
        _slot("Case2", SLOT_OK, ("s2", "r9")),
    )
    chips = slot_chips(unset, official_release_no=None, active=("s3", "r3"))
    assert [(chip.text, chip.disabled, chip.dashed) for chip in chips] == [
        ("공식", True, False),
        ("Case1", False, True),
        ("Case2", False, False),
    ]
    assert outside_slots(chips, ("s3", "r3"))
    # 올라온 리비전이 없으면 「슬롯 밖」 도 없다.
    assert not outside_slots(chips, (None, None))


def test_the_chip_style_dashes_only_unset_chips() -> None:
    plain = SlotChip("a", "Case1", "", (None, None), painted=False, disabled=False, dashed=False)
    dashed = SlotChip("b", "Case2", "", (None, None), painted=False, disabled=False, dashed=True)
    assert "border-style: dashed" not in chip_style((plain,), outside=False)
    assert ".st-key-b button { border-style: dashed; }" in chip_style(
        (plain, dashed), outside=False
    )


def test_the_chip_style_keeps_one_row_and_hides_outside_only_inside_the_slots() -> None:
    """칩 줄은 한 줄이다. 「슬롯 밖」 은 늘 자리를 잡고 슬롯 안이면 감출 뿐이다 — 나타나고 사라질 때
    칩이 옆으로 밀리거나 칩 줄이 두 줄로 접히지 않는다(사이드바를 편 900px 에서 접혔다)."""
    chips = (SlotChip("a", "Case1", "", (None, None), painted=False, disabled=False, dashed=False),)
    assert f".st-key-{CHIP_ROW_KEY} {{ flex-wrap: nowrap; }}" in chip_style(chips, outside=True)
    assert HIDDEN_OUTSIDE_RULE in chip_style(chips, outside=False)
    assert HIDDEN_OUTSIDE_RULE not in chip_style(chips, outside=True)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_a_painted_chip_writes_in_the_text_colour_for_the_accent_fill(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """칠한 칩 글자는 강조 면 위 글자색(`ACCENT_TEXT`)이다 — 어두운 테마의 밝은 강조색 위 흰 글자는
    1.9:1 이었다(대비는 `test_design_tokens.py`). 누르거나 올려 놓아도 그 색이다."""
    from capa_simulation.design import theme

    monkeypatch.setattr(theme, "current_mode", lambda: mode)
    style = chip_style((), outside=False)
    painted = f'.st-key-{CHIP_ROW_KEY} button[kind="primary"]'
    colour = tokens.palette_value(mode, "ACCENT_TEXT")
    assert (
        f"{painted}, {painted}:hover, {painted}:active, {painted}:focus, {painted}:focus-visible"
        f" {{ color: {colour}; }}"
    ) in style
