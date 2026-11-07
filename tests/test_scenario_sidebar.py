# Purpose: 사이드바 시나리오 필드와 팝업(불러오기·저장·되돌리기)의 정상·예외·회귀 동작을 검증한다.

from collections.abc import Iterator
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest
import streamlit as st
from alert_marks import flashed, infos, place_errors, successes
from streamlit.testing.v1 import AppTest

import capa_simulation.components.scenario_status as target
import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.capacity_gate import GateVerdict
from capa_simulation.components.equipment_scenario_management import (
    CAPA_SCENARIO_TAB,
    SCENARIO_MANAGEMENT_TABS_KEY,
)
from capa_simulation.components.scenario_management import DISCARD_LOCK_HELP
from capa_simulation.components.scenario_status import (
    LOAD_MODE,
    SAVE_BUTTON_HELP,
    SAVE_MODE,
    SCENARIO_DIALOG_KEY,
    SCENARIO_DIALOG_MODE_KEY,
    SCENARIO_FIELD_KEY,
    SIDEBAR_REVISION_KEY,
    SIDEBAR_SCENARIO_KEY,
    revision_unchanged_notice,
    scenario_status_badge,
)
from capa_simulation.components.tab_state import remembered_tab_key
from capa_simulation.page_bootstrap import forget_page_dialogs
from capa_simulation.persistence.repository import RevisionUnchanged
from capa_simulation.scenario_state import VIRTUAL_PRODUCTS_KEY, pristine_content_token
from capa_simulation.services.virtual_product import VirtualProductRecord


def scenario(
    scenario_id: str, name: str, code: str, revision_id: str, revision_no: int
) -> SimpleNamespace:
    return SimpleNamespace(
        scenario_id=scenario_id,
        scenario_name=name,
        source_simulation_code=code,
        source_simulation_name=name,
        active_revision_id=revision_id,
        active_revision_no=revision_no,
    )


def revision(
    revision_id: str, scenario_id: str, revision_no: int, name: str, note: str | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        revision_id=revision_id,
        scenario_id=scenario_id,
        revision_no=revision_no,
        revision_name=name,
        note=note,
        created_at=datetime(2026, 10, 8, 9, 30),
    )


SCENARIOS = [
    scenario("scenario-1", "기준안", "SIM-001", "revision-1", 1),
    scenario("scenario-2", "증산안", "SIM-002", "revision-2", 1),
]
REVISIONS = {
    "scenario-1": [revision("revision-1", "scenario-1", 1, "초기", "첫 저장")],
    "scenario-2": [revision("revision-2", "scenario-2", 1, "초기")],
}
# 머리 띠와 같은 세션 값(활성 이름표). 필드는 이것만 읽는다.
LABEL = SimpleNamespace(
    scenario_id="scenario-1",
    revision_id="revision-1",
    scenario_name="기준안",
    revision_no=1,
    revision_name="초기",
)


class FakeRepository:
    def list_scenarios(self, *, include_archived: bool = False) -> list[SimpleNamespace]:
        _count_read()
        listed: list[SimpleNamespace] = st.session_state.get("test_scenarios", SCENARIOS)
        if include_archived:
            # 보관본까지 — 테스트가 세션에 넣어 둔 보관본을 덧붙인다.
            return [*listed, *st.session_state.get("test_archived_scenarios", [])]
        return listed

    def list_revisions(self, scenario_id: str) -> list[SimpleNamespace]:
        _count_read()
        return REVISIONS[scenario_id]

    def latest_official_release(self) -> None:
        _count_read()
        return None

    def list_virtual_products(self, revision_id: str) -> pd.DataFrame:
        # 불러온 리비전(`revision-1`)의 가상 제품 이력. 테스트가 세션에 넣어 둔다.
        st.session_state["test_history_revision"] = revision_id
        return pd.DataFrame(
            st.session_state.get("test_parent_history", []),
            columns=["제품정보", "Stack", "원본 제품정보", "원본 Stack"],
        )

    def save_revision(
        self,
        scenario_id: str,
        tables: dict[str, pd.DataFrame],
        preset: object,
        **kwargs: Any,
    ) -> SimpleNamespace:
        # 화면이 「바꾼 것 없는 저장」 견주기를 켰는지(개선 I5). 켰고 시험이 「최신과 같다」 고 정해
        # 두면 실제 저장소처럼 쓰지 않고 거절한다.
        st.session_state["test_skip_unchanged"] = kwargs.get("skip_unchanged")
        if kwargs.get("skip_unchanged") and st.session_state.get("test_same_as_latest"):
            raise RevisionUnchanged(1)
        st.session_state["test_saved_revision_name"] = kwargs["revision_name"]
        st.session_state["test_saved_virtual_products"] = list(kwargs.get("virtual_products", ()))
        return SimpleNamespace(
            scenario=SCENARIOS[0],
            revision=revision("revision-3", scenario_id, 2, kwargs["revision_name"]),
            preset=preset,
            tables=tables,
        )


def _count_read() -> None:
    st.session_state["test_repository_reads"] = (
        int(st.session_state.get("test_repository_reads", 0)) + 1
    )


def load_snapshot(_database_path: object, revision_id: str) -> SimpleNamespace:
    selected = next(
        item
        for revisions in REVISIONS.values()
        for item in revisions
        if item.revision_id == revision_id
    )
    selected_scenario = next(item for item in SCENARIOS if item.scenario_id == selected.scenario_id)
    return SimpleNamespace(
        scenario=selected_scenario,
        revision=selected,
        preset=SimpleNamespace(),
        tables={},
    )


def _activate(snapshot: SimpleNamespace) -> None:
    """실제 활성화처럼 세션의 가상 제품 목록도 비운다(`clear_virtual_products`).

    비우지 않는 가짜로는 활성화 **뒤에** 목록을 읽는 저장도 통과해 버린다.
    """
    st.session_state["test_activated_revision"] = snapshot.revision.revision_id
    st.session_state["test_activation_path"] = "바꾸기"
    st.session_state.pop(VIRTUAL_PRODUCTS_KEY, None)


def _activate_saved(snapshot: SimpleNamespace) -> None:
    """저장 경로의 활성화. HOME 토글을 풀지 않는 쪽이라 어느 경로로 왔는지 따로 적는다."""
    _activate(snapshot)
    st.session_state["test_activation_path"] = "저장"


# 실제 `app.py` 처럼 필드를 그리고, 열림 키가 있으면 팝업을 부른다(세션 키 방식이라 AppTest 에서도
# 회차를 넘어 열려 있다).
TEST_SCRIPT = """
import streamlit as st

import capa_simulation.components.scenario_status as target

target.render_scenario_field()
if target.scenario_dialog_is_open():
    target.show_scenario_dialog(None)
"""


def sidebar_replacements() -> dict[str, Any]:
    """사이드바 시나리오 팝업을 가짜 저장소·활성화로 돌리는 바꿔치기.

    `tests/test_write_entry_points.py` 의 겹친 저장 시험도 쓴다.
    """
    # 가짜의 모양이 제각각이라(함수·람다·클래스) 값 타입을 하나로 좁히지 않는다.
    return {
        "get_scenario_repository": lambda _path: FakeRepository(),
        "load_scenario_snapshot": load_snapshot,
        "pinned_connections": lambda *_paths: nullcontext(),
        "pending_edit_labels": lambda _page: list(st.session_state.get("test_pending_edits", [])),
        "active_persisted_scenario_id": lambda: "scenario-1",
        "active_persisted_revision_id": lambda: "revision-1",
        "active_scenario_label": lambda: st.session_state.get("test_label", LABEL),
        "latest_official_revision": lambda: st.session_state.get("test_official"),
        # `app.py` 가 30초에 한 번 확인해 둔 「더 새 리비전」(세션 값). 확인 자체는 따로 검증한다
        # (`test_scenario_activation.py`).
        "newer_active_revision_no": lambda: st.session_state.get("test_newer"),
        "has_unsaved_scenario_changes": lambda: bool(st.session_state.get("test_unsaved", False)),
        "discard_unsaved_scenario_changes": lambda _tables, version: st.session_state.__setitem__(
            "test_reset_to_version", version
        ),
        "activate_persisted_snapshot": _activate,
        "activate_saved_revision": _activate_saved,
        "get_effective_reference_version": lambda: 1,
        "get_effective_reference_tables": lambda: {
            "RQ_REQB": pd.DataFrame({"공정": ["공정 A"]}),
            "RQ_DISPLAY_ORDER": pd.DataFrame(),
        },
        "ensure_active_scenario": lambda _tables, _version: {
            "reference_version": 1,
            "revision": 1,
            "content_token": pristine_content_token(1),
            "tables": {},
        },
        "revision_tables_for_save": lambda _active, tables: {"RQ_REQB": tables["RQ_REQB"].copy()},
        "capture_scenario_preset": lambda _tables: SimpleNamespace(),
        # 저장 검사는 따로 검증한다(`test_capacity_gate.py`). 여기서는 판정을 세션에서 읽어
        # 화면이 그 판정대로 움직이는지만 본다.
        "revision_save_verdict": lambda *_args: st.session_state.get(
            "test_save_verdict", GateVerdict(True)
        ),
        # 옛 리비전 호환 검사는 따로 검증한다(`test_revision_compatibility.py`).
        "revision_block_reason": lambda _tables: st.session_state.get("test_block_reason"),
    }


@pytest.fixture
def sidebar_app() -> Iterator[AppTest]:
    """callback은 스크립트보다 먼저 실행되므로 모든 rerun을 같은 patch로 감싼다."""
    replacements = sidebar_replacements()
    originals = {name: getattr(target, name) for name in replacements}
    try:
        with patch.multiple(target, **replacements):
            yield AppTest.from_string(TEST_SCRIPT)
    finally:
        # 테스트 실패와 st.rerun 모두 원본 복원을 건너뛰어 다음 AppTest를 오염시키면 안 된다.
        for name, original in originals.items():
            assert getattr(target, name) is original, name


def _open(app: AppTest) -> AppTest:
    app = app.button(key=SCENARIO_FIELD_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state[SCENARIO_DIALOG_KEY] is True
    return app


def _open_save(app: AppTest) -> AppTest:
    app = _open(app)
    app.session_state[SCENARIO_DIALOG_MODE_KEY] = SAVE_MODE
    return app.run()


def _dismiss(app: AppTest) -> AppTest:
    """닫기(X·바깥 클릭·Esc). AppTest 는 닫기를 흉내 내지 못해 `on_dismiss` 콜백의 일을 한다."""
    del app.session_state[SCENARIO_DIALOG_KEY]
    return app.run()


def test_the_field_reads_only_the_session_until_the_dialog_opens(sidebar_app: AppTest) -> None:
    """필드는 머리 띠와 같은 세션 값만 읽는다 — 회차마다 저장소를 읽지 않는다(2026-10-10).

    전에는 접히는 상자가 회차마다 시나리오 목록·최신 공식버전·리비전 목록을 읽었다. 모든 화면의
    모든 회차에 서는 패널이라 그 값이 HOME 회차에 그대로 실렸다. 저장소는 팝업을 연 동안에만 읽는다.
    """
    app = sidebar_app.run()
    app.run()
    assert not app.exception
    assert "test_repository_reads" not in app.session_state
    assert app.button(key=SCENARIO_FIELD_KEY).label == "기준안 · r1"
    # 리비전 번호는 이름 줄에도 있다 — 이름이 길면 값 칸 끝의 「· rN」 이 말줄임에 잘린다.
    assert [item.value for item in app.caption] == ["시나리오 · r1", ":gray-badge[저장된 리비전]"]

    app.session_state["test_official"] = ("revision-1", 4)
    app.run()
    assert ":green-badge[공식 v4]" in [item.value for item in app.caption]
    assert "test_repository_reads" not in app.session_state

    app = _open(app)
    assert app.session_state["test_repository_reads"] > 0


def test_the_field_and_the_save_line_show_a_markdown_like_name_as_typed(
    sidebar_app: AppTest,
) -> None:
    """시나리오명은 사람이 적은 글이다 — 값 칸(버튼 라벨)과 팝업 머리 「올라와 있음」 caption 은
    마크다운으로 그려지므로 「*별* _밑_ `코드`」 가 기울임·코드로 바뀌어 글자가 빠졌다. 구두점을
    escape 해 싣는다(`literal_markdown`). 저장 구획은 저장 대상을 따로 적지 않는다 — 머리 줄이
    말한다(설계 규칙 UI-TXT-01)."""
    from capa_simulation.components.literal_markdown import literal_markdown

    name = "*별* _밑_ `코드`"
    app = sidebar_app
    app.session_state["test_label"] = SimpleNamespace(**{**LABEL.__dict__, "scenario_name": name})
    app.session_state["test_scenarios"] = [
        scenario("scenario-1", name, "SIM-001", "revision-1", 1),
        *SCENARIOS[1:],
    ]
    app = _open_save(app.run())

    assert not app.exception, [item.message for item in app.exception]
    assert app.button(key=SCENARIO_FIELD_KEY).label == f"{literal_markdown(name)} · r1"
    captions = [str(item.value) for item in app.caption]
    assert any(text.startswith(f"올라와 있음 · {literal_markdown(name)} · r1") for text in captions)
    assert not any("새 리비전으로 저장합니다" in text for text in captions), captions


def test_the_badge_says_official_saved_or_unsaved_in_that_order() -> None:
    """배지는 하나다. 미저장이 먼저 — 머리 띠와 같은 차례다."""
    assert (
        scenario_status_badge(active_revision_id="r1", official=("r1", 4), unsaved=False)
        == ":green-badge[공식 v4]"
    )
    assert (
        scenario_status_badge(active_revision_id="r2", official=("r1", 4), unsaved=False)
        == ":gray-badge[저장된 리비전]"
    )
    assert (
        scenario_status_badge(active_revision_id="r1", official=("r1", 4), unsaved=True)
        == ":orange-badge[미저장 변경]"
    )
    assert scenario_status_badge(active_revision_id=None, official=None, unsaved=False) == ""


def test_the_badge_says_a_newer_revision_after_official_and_before_saved() -> None:
    """E2E #102 — 남이 그 시나리오에 새 리비전을 저장했으면 「최신 rN 있음」(설비 시나리오 줄과 같은
    말). 미저장·공식 vN 이 먼저다 — 보는 리비전이 공식이면 공식 배지 그대로다."""
    assert (
        scenario_status_badge(
            active_revision_id="r2", official=("r1", 4), unsaved=False, newer_revision_no=3
        )
        == ":orange-badge[최신 r3 있음]"
    )
    assert (
        scenario_status_badge(
            active_revision_id="r1", official=("r1", 4), unsaved=False, newer_revision_no=3
        )
        == ":green-badge[공식 v4]"
    )
    assert (
        scenario_status_badge(
            active_revision_id="r2", official=None, unsaved=True, newer_revision_no=3
        )
        == ":orange-badge[미저장 변경]"
    )


def test_the_field_shows_a_newer_revision_from_the_session_only(sidebar_app: AppTest) -> None:
    """필드는 확인해 둔 세션 값만 읽어 「최신 r3 있음」 을 단다 — 저장소는 여전히 읽지 않는다."""
    sidebar_app.session_state["test_newer"] = 3
    app = sidebar_app.run()
    assert not app.exception
    assert ":orange-badge[최신 r3 있음]" in [item.value for item in app.caption]
    assert "test_repository_reads" not in app.session_state


def test_the_dialog_selects_and_loads_another_revision(
    sidebar_app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _open(sidebar_app.run())
    # 팝업은 올라와 있는 값으로 연다 — 닫힌 뒤에 「골랐지만 불러오지 않은 선택」이 남지 않는다.
    assert app.selectbox(key=SIDEBAR_SCENARIO_KEY).value == "scenario-1"
    revisions = app.radio(key=SIDEBAR_REVISION_KEY)
    assert revisions.value == "revision-1"
    # 바뀌는 상태(공식·올라와 있음·메모)는 라벨이 아니라 캡션이다 — 라벨이 바뀌면 브라우저가 옛
    # 라벨을 되보낸다(AGENTS 9장).
    assert revisions.options == ["r1 · 초기"]
    assert list(revisions.proto.captions) == ["26.10.08 저장 · 올라와 있음 · 첫 저장"]

    app = app.selectbox(key=SIDEBAR_SCENARIO_KEY).select("scenario-2").run()
    assert app.radio(key=SIDEBAR_REVISION_KEY).value == "revision-2"

    # 적용하지 않은 편집 목록은 페이지가 다음 회차에 편집표를 비우기 전에 사이드바가 먼저 센다.
    # 불러오기가 원본을 바꿨으니 목록을 비워 패널 맨 위 경고가 한 회차 남지 않게 한다.
    app.session_state["scenario_pending_edit_registry"] = {"reference_data.py": ()}
    app = app.button(key="sidebar_load_revision").click().run()

    assert not app.exception
    assert "scenario_pending_edit_registry" not in app.session_state
    assert app.session_state["test_activated_revision"] == "revision-2"
    # 불러오기는 보는 내용을 바꾸므로 HOME 토글을 푸는 경로다.
    assert app.session_state["test_activation_path"] == "바꾸기"
    # 성공하면 팝업을 닫고 알림은 필드 아래에 다음 회차 한 번 선다.
    assert SCENARIO_DIALOG_KEY not in app.session_state
    assert [item.value for item in successes(app)] == ["증산안 r1을 불러왔습니다."]
    # 쓰기 알림 표지의 창(빠른 두 번 누름의 꼬리 회차가 같은 알림을 다시 그린다)이 지난 회차다.
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    app.run()
    assert [item.value for item in successes(app)] == []


def test_reopening_the_dialog_starts_from_the_active_revision(sidebar_app: AppTest) -> None:
    """닫은 팝업의 초안은 남지 않는다. 다시 열면 올라와 있는 시나리오·리비전에서 시작한다."""
    app = _open(sidebar_app.run())
    app = app.selectbox(key=SIDEBAR_SCENARIO_KEY).select("scenario-2").run()
    app = _dismiss(app)
    assert [item.key for item in app.selectbox] == []

    app = _open(app)
    assert app.selectbox(key=SIDEBAR_SCENARIO_KEY).value == "scenario-1"
    assert app.radio(key=SIDEBAR_REVISION_KEY).value == "revision-1"


def test_an_unsaved_session_opens_on_the_save_section(sidebar_app: AppTest) -> None:
    """저장하지 않은 편집이 있으면 팝업이 저장 구획으로 열린다 — 남길 사람이 먼저 할 일이다."""
    app = sidebar_app
    app.session_state["test_unsaved"] = True
    app = _open(app.run())
    assert app.session_state[SCENARIO_DIALOG_MODE_KEY] == SAVE_MODE
    assert app.button(key=SCENARIO_FIELD_KEY).label == "기준안 · r1"
    assert ":orange-badge[미저장 변경]" in [item.value for item in app.caption]
    assert [widget.label for widget in app.text_input] == ["새 리비전명"]

    app.session_state["test_unsaved"] = False
    app = _open(_dismiss(app))
    assert app.session_state[SCENARIO_DIALOG_MODE_KEY] == LOAD_MODE


def test_saving_into_a_scenario_archived_elsewhere_says_why_and_where_to_go(
    sidebar_app: AppTest,
) -> None:
    """E2E #55 — 올라와 있는 「기준안」 을 다른 세션이 보관했다. 「새 리비전 저장」 은 「정보를 찾지
    못했습니다」 한 줄 대신 까닭(보관됨)과 길(보관함에서 되돌리기·복제·다른 시나리오
    불러오기)을 말하고 시나리오 관리로 가는 링크를 세운다. 저장 폼은 서지 않는다. 보관본에도 없으면
    (영구 삭제) 그 말로 바뀐다."""
    archived = scenario("scenario-1", "기준안", "SIM-001", "revision-1", 1)
    archived.status = "ARCHIVED"
    sidebar_app.session_state["test_scenarios"] = [SCENARIOS[1]]
    sidebar_app.session_state["test_archived_scenarios"] = [archived]
    app = _open_save(sidebar_app.run())
    assert not app.exception

    (warning,) = [str(item.value) for item in app.warning]
    assert warning.startswith(
        "「기준안」은 그 사이 다른 사용자가 보관해 새 리비전을 저장할 수 없습니다 — 저장하려면 "
        "시나리오 관리 「목록 관리」 오른쪽 「보관함」 에서 목록으로 되돌린 뒤 다시 "
        "저장하세요."
    ), warning
    assert "시나리오 관리 「복제」 로 새 시나리오를 만들고" in warning
    assert "올라와 있는 시나리오 정보를 찾지 못했습니다" not in warning
    # 가는 길은 Capa 시나리오 탭까지 여는 단추다(설비 탭을 보던 세션도 — 단독 실행은 칸만 적는다).
    route = next(button for button in app.button if button.label == "시나리오 관리로 가기")
    route.click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state[remembered_tab_key(SCENARIO_MANAGEMENT_TABS_KEY)] == CAPA_SCENARIO_TAB
    assert "신규 리비전 저장" not in [button.label for button in app.button]

    app.session_state["test_archived_scenarios"] = []
    app.run()
    (warning,) = [str(item.value) for item in app.warning]
    assert warning.startswith(
        "「기준안」은 그 사이 다른 사용자가 영구 삭제해 새 리비전을 저장할 수 없습니다"
    ), warning


def test_the_dialog_saves_current_state_as_a_new_revision(sidebar_app: AppTest) -> None:
    app = _open_save(sidebar_app.run())
    # 공정 필터·조회기간도 리비전 프리셋에 담긴다 — 편집이 없어도 저장할 것이 있다. 그 말은 늘
    # 띄워 두지 않고 저장 단추 풍선에 둔다(설계 규칙 UI-TXT-01 · AMB-01 (가)).
    assert not any("조회기간·공정 필터도 담깁니다" in item.value for item in app.caption)
    save = next(button for button in app.button if button.label == "신규 리비전 저장")
    assert str(save.help) == SAVE_BUTTON_HELP
    assert "조회기간·공정 필터도" in SAVE_BUTTON_HELP

    revision_name = next(widget for widget in app.text_input if widget.label == "새 리비전명")
    app = revision_name.set_value("사이드바 저장안").run()
    save_button = next(button for button in app.button if button.label == "신규 리비전 저장")
    app = save_button.click().run()

    assert not app.exception
    assert app.session_state["test_saved_revision_name"] == "사이드바 저장안"
    assert app.session_state["test_activated_revision"] == "revision-3"
    # 방금 보던 내용을 적은 리비전이라 HOME 토글을 풀지 않는 경로로 올린다.
    assert app.session_state["test_activation_path"] == "저장"
    assert SCENARIO_DIALOG_KEY not in app.session_state


def test_a_save_with_nothing_changed_makes_no_revision_and_says_so(sidebar_app: AppTest) -> None:
    """바꾼 것 없는 「신규 리비전 저장」 은 새 리비전을 만들지 않는다(2026-11-01 개선 I5 — E2E #10:
    「저장된 리비전」 · 미저장 없음인데 r1 과 같은 r3 이 생겼다). 화면은 저장소에 견주기를 켜고,
    같다는 거절을 받으면 팝업 안에 「바뀐 것이 없습니다」 를 적고 칸(리비전명)을 그대로 둔다."""
    app = sidebar_app
    app.session_state["test_same_as_latest"] = True
    app = _save(_open_save(app.run()), "그대로 저장")

    assert not app.exception
    assert app.session_state["test_skip_unchanged"] is True
    assert [str(item.value) for item in infos(app)] == [revision_unchanged_notice(1)]
    assert "바뀐 것이 없습니다" in revision_unchanged_notice(1)
    # 이름표만 바꾸는 곳으로 가는 길 안내 꼬리는 붙이지 않는다(설계 규칙 UI-TXT-03 · AMB-06 (나)).
    assert "시나리오 관리" not in revision_unchanged_notice(1)
    assert "test_saved_revision_name" not in app.session_state
    assert "test_activated_revision" not in app.session_state
    assert not successes(app) and not place_errors(app)
    assert app.session_state[SCENARIO_DIALOG_KEY] is True
    name = next(widget for widget in app.text_input if widget.label == "새 리비전명")
    assert name.value == "그대로 저장"


def test_sidebar_save_keeps_the_session_virtual_products(sidebar_app: AppTest) -> None:
    """사이드바 저장도 가상 제품 이력을 리비전에 남기고 관리 페이지와 같은 문장으로 알린다.

    이 경로만 `virtual_products` 를 넘기지 않아 가상 제품을 등록한 편집본을 사이드바로 저장하면
    `app_meta.revision_virtual_product` 가 비었다. 활성화가 세션 목록을 비우므로 그 전에 읽는다.
    """
    record = VirtualProductRecord(
        product="DEMO_VIRTUAL", stack="8H", source_product="DEMO_SOURCE", source_stack="8H"
    )
    app = sidebar_app
    app.session_state[VIRTUAL_PRODUCTS_KEY] = (record,)
    app = _save(_open_save(app.run()), "가상 제품 포함 저장")

    assert not app.exception
    assert app.session_state["test_saved_virtual_products"] == [
        {
            "product": "DEMO_VIRTUAL",
            "stack": "8H",
            "source_product": "DEMO_SOURCE",
            "source_stack": "8H",
        }
    ]
    assert [item.value for item in successes(app)] == [
        "신규 리비전 r2를 저장했습니다. 가상 제품 1건이 포함되어 있습니다. "
        "실적과 대조할 수 없으므로 공식버전으로 지정하기 전에 확인하세요."
    ]


def test_sidebar_save_carries_over_the_loaded_revisions_virtual_products(
    sidebar_app: AppTest,
) -> None:
    """새 리비전은 불러온 리비전의 가상 제품 이력을 물려받고 이 세션의 등록을 더한다.

    세션 목록은 리비전을 불러올 때 비므로, 물려받지 않으면 가상 제품을 등록한 리비전에서 이어
    저장한 리비전부터 출처가 사라졌다. 같은 제품은 한 건이고, 알림은 합친 건수를 센다. 이 가짜
    저장 표에는 제품 키를 가진 표가 없어 물려받은 이력을 거를 근거가 없으므로 모두 남는다.
    """
    app = sidebar_app
    app.session_state["test_parent_history"] = [
        ("DEMO_PARENT", "8H", "DEMO_SOURCE", "8H"),
        ("DEMO_VIRTUAL", "8H", "DEMO_SOURCE", "8H"),
    ]
    app.session_state[VIRTUAL_PRODUCTS_KEY] = (
        VirtualProductRecord(
            product="DEMO_VIRTUAL", stack="8H", source_product="DEMO_SOURCE", source_stack="8H"
        ),
        VirtualProductRecord(
            product="DEMO_SESSION", stack="4H", source_product="DEMO_SOURCE", source_stack="8H"
        ),
    )
    app = _save(_open_save(app.run()), "이어 저장")

    assert not app.exception
    assert app.session_state["test_history_revision"] == "revision-1"
    assert [
        (row["product"], row["stack"]) for row in app.session_state["test_saved_virtual_products"]
    ] == [("DEMO_PARENT", "8H"), ("DEMO_VIRTUAL", "8H"), ("DEMO_SESSION", "4H")]
    assert [item.value for item in successes(app)] == [
        "신규 리비전 r2를 저장했습니다. 가상 제품 3건이 포함되어 있습니다. "
        "실적과 대조할 수 없으므로 공식버전으로 지정하기 전에 확인하세요."
    ]


def test_sidebar_save_without_virtual_products_says_only_what_it_saved(
    sidebar_app: AppTest,
) -> None:
    """가상 제품이 없으면 이력도 넘기지 않고 알림은 저장한 리비전 한 문장 그대로다."""
    app = _save(_open_save(sidebar_app.run()), "가상 제품 없는 저장")

    assert not app.exception
    assert app.session_state["test_saved_virtual_products"] == []
    assert [item.value for item in successes(app)] == ["신규 리비전 r2를 저장했습니다."]


def test_discarding_edits_lives_in_the_dialog_only_when_there_are_edits(
    sidebar_app: AppTest,
) -> None:
    """「편집 되돌리기」는 모든 화면의 편집을 버리는 시나리오 단위 동작이다.

    본문 맨 위의 「활성 시나리오 · 수정본 N · 전체 입력 원본으로 초기화」 줄을 없애고 사이드바로
    옮겼다(2026-09-29 사용자 결정). 지금은 팝업의 불러오기 곁이고, 버릴 것이 없으면 서지 않는다.
    """
    app = _open(sidebar_app.run())
    assert "sidebar_reset_active_scenario" not in {button.key for button in app.button}

    app.session_state["test_unsaved"] = True
    app.session_state[SCENARIO_DIALOG_MODE_KEY] = LOAD_MODE
    app.run()
    app.button(key="sidebar_reset_active_scenario").click().run()

    assert not app.exception
    assert app.session_state["test_reset_to_version"] == 1
    assert "저장하지 않은 편집을 버렸습니다." in {item.value for item in successes(app)}
    assert SCENARIO_DIALOG_KEY not in app.session_state


def _save(app: AppTest, name: str) -> AppTest:
    revision_name = next(widget for widget in app.text_input if widget.label == "새 리비전명")
    app = revision_name.set_value(name).run()
    save_button = next(button for button in app.button if button.label == "신규 리비전 저장")
    return save_button.click().run()


def test_a_save_the_gate_refuses_writes_nothing(sidebar_app: AppTest) -> None:
    """편집이 계산을 깨뜨렸으면 저장하지 않고 그 이유를 그 자리(팝업 안)에서 말한다."""
    app = sidebar_app
    app.session_state["test_save_verdict"] = GateVerdict(False, "이번 편집이 깨뜨린 것입니다")
    app = _save(_open_save(app.run()), "깨진 저장안")

    assert not app.exception
    assert "test_saved_revision_name" not in app.session_state
    assert any("이번 편집이 깨뜨린" in error.value for error in app.error)
    assert app.session_state[SCENARIO_DIALOG_KEY] is True


def test_a_save_with_an_old_error_is_kept_and_warned(sidebar_app: AppTest) -> None:
    """편집 전부터 있던 오류는 저장을 막지 않는다. 대신 발행이 막힌다고 저장 뒤에 알린다 — 저장은
    끝났고 고칠 입력이 이 자리에 없어 시나리오 칸 밑 상자 없이 알림창 · Alarm 에만 낸다(설계 규칙
    AMB-05 (나)). 단계는 확인 필요(`FL-03`)다."""
    app = sidebar_app
    app.session_state["test_save_verdict"] = GateVerdict(True, "공식버전으로 지정할 수 없습니다")
    app = _save(_open_save(app.run()), "고치는 중")

    assert not app.exception
    assert app.session_state["test_saved_revision_name"] == "고치는 중"
    assert not app.warning and not app.sidebar.warning, [item.value for item in app.warning]
    (warned,) = flashed(app, "warning")
    assert warned.value == "공식버전으로 지정할 수 없습니다"
    assert warned.note is not None
    assert (warned.note["code"], warned.note["level"]) == ("FL-03", "check")
    # 다음 회차에는 다시 내지 않는다(한 번뿐인 결과 알림).
    app.run()
    assert not flashed(app, "warning")


def test_a_save_that_leaves_demand_out_warns_only_through_the_alert_popup(
    sidebar_app: AppTest,
) -> None:
    """소요대수에 들지 않은 수요(계산은 통과 — `GateVerdict.exclusion`)는 저장 뒤 시나리오 칸 밑
    경고 상자 없이 오른쪽 아래 알림창 · Alarm 에만 낸다(2026-11-04 검수 의견 home-18). 단계는 확인
    필요(`FL-03`)다."""
    message = (
        "소요대수에 들지 않은 수요가 있습니다(시나리오 전체 기간) — "
        "대당 Capa 가 없어 뺀 부하 경로 2건"
    )
    app = sidebar_app
    app.session_state["test_save_verdict"] = GateVerdict(True, message, exclusion=True)
    app = _save(_open_save(app.run()), "빠진 수요 저장안")

    assert not app.exception
    assert app.session_state["test_saved_revision_name"] == "빠진 수요 저장안"
    assert not any("소요대수에 들지 않은 수요" in warning.value for warning in app.warning)
    (warned,) = flashed(app, "warning")
    assert warned.value == message
    assert warned.note is not None
    assert (warned.note["code"], warned.note["level"]) == ("FL-03", "check")


@pytest.mark.parametrize("allowed", [False, True])
def test_the_gate_refusal_and_warning_keep_tildes_in_example_keys(
    sidebar_app: AppTest, allowed: bool
) -> None:
    """계산 검사 거절·경고 글은 알림 상자(마크다운)다 — 오류 예시 키 「P~Q~R」 의 물결표 둘이
    지움선(「P<del>Q</del>R」)이 되지 않는다."""
    message = "오류: RQ_UPEH 에 없는 공정이 있습니다: 1건, 예시 ['P~Q~R']"
    app = sidebar_app
    app.session_state["test_save_verdict"] = GateVerdict(allowed, message)
    app = _save(_open_save(app.run()), "물결표 저장안")

    assert not app.exception
    # 허락한 경고는 알림창 표지로만 간다(마크다운 원문은 표지의 `markdown`) — 자리에는 없다.
    shown = flashed(app, "warning") if allowed else app.error
    assert message.replace("~", "\\~") in [item.value for item in shown]
    assert not app.warning


def test_unapplied_edits_gate_both_load_and_save(sidebar_app: AppTest) -> None:
    """적용하지 않은 편집은 시나리오에 없다 — 저장에 실리지 않고 저장·불러오기에 사라진다.

    2026-09-29 2차 리뷰가 브라우저로 재현했다: UPEH 를 고친 채 「신규 리비전 저장」을 누르면 저장
    알림이 뜨는데 그 편집은 저장에도 없이 사라졌다. 두 동작 모두 한 번 더 묻는다.
    """
    app = sidebar_app
    app.session_state["test_pending_edits"] = ["기준 정보 · UPEH"]
    app = _open(app.run())
    assert not app.exception

    assert any("기준 정보 · UPEH" in item.value for item in app.caption)
    # 불러오기는 「변경을 버리고 불러오기」를 체크해야 열린다.
    assert app.button(key="sidebar_load_revision").disabled
    assert app.button(key="sidebar_load_revision").help == DISCARD_LOCK_HELP
    app = app.checkbox(key="sidebar_discard_unsaved_changes").check().run()
    assert not app.button(key="sidebar_load_revision").disabled
    assert not app.button(key="sidebar_load_revision").help

    # 저장은 「적용하지 않은 편집을 버리고 저장」을 체크해야 된다. 버튼은 잠그지 않는다 — 체크하지
    # 않고 누르면 저장하지 않고 그렇다고 알린다(아래 테스트가 잠그지 않는 까닭을 말한다).
    app.session_state[SCENARIO_DIALOG_MODE_KEY] = SAVE_MODE
    app = _save(app.run(), "체크 없이 누른 저장안")
    assert "test_saved_revision_name" not in app.session_state
    refusals = [item.value for item in app.warning if "저장하지 않았습니다" in item.value]
    assert refusals
    # 거절돼도 리비전명·메모는 남는다(`SAVE_FORM_GENERATION_KEY` 가 그대로다). 다시 적으라고
    # 하면 지금 동작과 어긋난 안내가 된다 — 체크하고 다시 누르기만 하면 된다.
    assert all("체크한 뒤 다시 저장하세요" in text for text in refusals), refusals
    assert not any("다시 적어" in text for text in refusals), refusals
    app = app.checkbox(key="sidebar_save_discards_pending_edits").check().run()
    app = _save(app, "편집을 버린 저장안")
    assert app.session_state["test_saved_revision_name"] == "편집을 버린 저장안"


def test_a_save_pressed_as_unapplied_edits_resurface_is_refused_out_loud(
    sidebar_app: AppTest,
) -> None:
    """보여 준 회차에는 없던 적용 전 편집이 누른 회차에 생기면, 저장하지 않고 **그렇다고 알린다**.

    2026-10-01 브라우저 E2E: 수율을 고친 채 PKG PLAN 을 적용하면 수율 편집이 서버에서 한 회차
    사라져 저장 팝업이 경고 없이 켜진 버튼을 보였다. 누른 회차에는 브라우저가 그 편집을 되보내
    버튼이 잠긴 채 다시 그려졌고, Streamlit 은 잠긴 버튼으로 온 제출을 서버에서 버린다 — 리비전도
    알림도 없이 리비전명만 지워졌다. 그래서 버튼은 잠그지 않고 누른 회차의 목록으로 판정한다.
    적용 전 편집은 팝업이 **누른 회차에** 다시 센다.
    """
    app = _open_save(sidebar_app.run())
    revision_name = next(widget for widget in app.text_input if widget.label == "새 리비전명")
    app = revision_name.set_value("E2E-D1b-rev").run()
    save_button = next(button for button in app.button if button.label == "신규 리비전 저장")
    assert not save_button.disabled

    app.session_state["test_pending_edits"] = ["생산 계획 · 수율"]
    app = save_button.click().run()

    assert not app.exception
    assert "test_saved_revision_name" not in app.session_state
    # 막았다는 알림은 팝업 안에 선다 — 팝업은 프래그먼트 재실행으로 닫히지 않는다.
    refusals = [item.value for item in app.warning if "저장하지 않았습니다" in item.value]
    assert refusals and all("생산 계획 · 수율" in refusal for refusal in refusals)
    assert app.session_state[SCENARIO_DIALOG_KEY] is True

    # 막은 회차는 다시 돌리지 않았다 — 다음 조작에도 적용 전 편집 경고가 그대로 선다.
    app = app.run()
    assert "test_saved_revision_name" not in app.session_state
    assert any("생산 계획 · 수율" in item.value for item in app.warning)


def test_without_unapplied_edits_nothing_extra_is_asked(sidebar_app: AppTest) -> None:
    app = _open(sidebar_app.run())

    assert not app.exception
    assert not app.button(key="sidebar_load_revision").disabled
    assert "sidebar_discard_unsaved_changes" not in {box.key for box in app.checkbox}
    app.session_state[SCENARIO_DIALOG_MODE_KEY] = SAVE_MODE
    app.run()
    assert "sidebar_save_discards_pending_edits" not in {box.key for box in app.checkbox}


def _field_key(base: str, generation: int) -> str:
    """`scenario_status.save_field_key` 가 그 세대에 내는 key. 테스트는 세션 밖이라 직접 짓는다."""
    return base if generation == 0 else f"{base}__g{generation}"


def _fill_and_save(app: AppTest, name: str, note: str, *, generation: int = 0) -> AppTest:
    app.text_input(key=_field_key(target.SAVE_REVISION_NAME_KEY, generation)).set_value(name)
    app.text_area(key=_field_key(target.SAVE_REVISION_NOTE_KEY, generation)).set_value(note)
    app = app.run()
    save_button = next(button for button in app.button if button.label == "신규 리비전 저장")
    return save_button.click().run()


def test_a_refused_save_keeps_the_typed_name_and_memo(sidebar_app: AppTest) -> None:
    """거절된 저장은 적은 리비전명·메모를 지우지 않는다(2026-10-01 E2E 후속).

    `clear_on_submit` 은 제출만 보면 비워, 계산 검사나 적용 전 편집 확인에 막힌 저장도 적은 글을
    잃었다. 막힌 까닭을 고치고 그대로 다시 누르면 되어야 한다.
    """
    app = sidebar_app
    app.session_state["test_save_verdict"] = GateVerdict(False, "이번 편집이 깨뜨린 것입니다")
    app = _fill_and_save(_open_save(app.run()), "막힐 저장안", "고친 까닭")

    assert not app.exception
    assert "test_saved_revision_name" not in app.session_state
    assert app.text_input(key=target.SAVE_REVISION_NAME_KEY).value == "막힐 저장안"
    assert app.text_area(key=target.SAVE_REVISION_NOTE_KEY).value == "고친 까닭"

    # 적용 전 편집을 확인하지 않아 막힌 저장도 같다.
    app.session_state["test_save_verdict"] = GateVerdict(True)
    app.session_state["test_pending_edits"] = ["기준 정보 · UPEH"]
    app = _fill_and_save(app.run(), "확인 없이 누른 저장안", "메모 그대로")
    assert "test_saved_revision_name" not in app.session_state
    assert app.text_input(key=target.SAVE_REVISION_NAME_KEY).value == "확인 없이 누른 저장안"
    assert app.text_area(key=target.SAVE_REVISION_NOTE_KEY).value == "메모 그대로"

    # 까닭을 고치고 그대로 다시 누르면 적어 둔 이름으로 저장된다.
    app = app.checkbox(key="sidebar_save_discards_pending_edits").check().run()
    save_button = next(button for button in app.button if button.label == "신규 리비전 저장")
    app = save_button.click().run()
    assert app.session_state["test_saved_revision_name"] == "확인 없이 누른 저장안"


def test_a_successful_save_clears_the_name_and_memo(sidebar_app: AppTest) -> None:
    """저장에 성공하면 다음에 여는 저장 구획의 칸이 빈다 — 같은 이름의 리비전이 또 서지 않게.

    **세션 칸에 빈 값을 적는 것으로는 브라우저가 비워지지 않았다**(2026-10-08 안정화 점검). 닫힌
    팝업 안 칸은 브라우저가 새 값을 받지 못하고 옛 이름·메모를 들고 있다가 다음 조작에 되보냈다.
    그래서 성공한 회차에만 두 칸의 key 세대를 올려 **새 위젯**으로 세운다 — AppTest 는 브라우저
    쪽을 흉내 내지 않으므로, 여기서는 key 가 바뀌어 옛 위젯이 사라졌는지를 본다.
    """
    app = _fill_and_save(_open_save(sidebar_app.run()), "성공할 저장안", "남지 않을 메모")

    assert not app.exception
    assert app.session_state["test_saved_revision_name"] == "성공할 저장안"
    assert app.session_state[target.SAVE_FORM_GENERATION_KEY] == 1
    app = _open_save(app)
    keys = {widget.key for widget in [*app.text_input, *app.text_area]}
    assert target.SAVE_REVISION_NAME_KEY not in keys
    assert target.SAVE_REVISION_NOTE_KEY not in keys
    assert app.text_input(key=_field_key(target.SAVE_REVISION_NAME_KEY, 1)).value == ""
    assert app.text_area(key=_field_key(target.SAVE_REVISION_NOTE_KEY, 1)).value == ""

    # 새 칸으로도 저장되고, 그 뒤 거절된 저장은 다시 적은 글을 남긴다(세대가 오르지 않는다).
    app = _fill_and_save(app, "두 번째 저장안", "두 번째 메모", generation=1)
    assert app.session_state["test_saved_revision_name"] == "두 번째 저장안"
    assert app.session_state[target.SAVE_FORM_GENERATION_KEY] == 2
    app.session_state["test_save_verdict"] = GateVerdict(False, "이번 편집이 깨뜨린 것입니다")
    app = _fill_and_save(_open_save(app), "막힐 세 번째", "남을 메모", generation=2)
    assert app.session_state[target.SAVE_FORM_GENERATION_KEY] == 2
    assert app.text_input(key=_field_key(target.SAVE_REVISION_NAME_KEY, 2)).value == "막힐 세 번째"
    assert app.text_area(key=_field_key(target.SAVE_REVISION_NOTE_KEY, 2)).value == "남을 메모"


def test_the_dialog_key_is_forgotten_on_leaving_the_page() -> None:
    """열림 키는 `PAGE_DIALOG_SUFFIX` 로 끝난다 — 닫지 않고 페이지를 떠나면 `app.py` 가 버린다.

    다른 팝업을 여는 콜백도 같은 함수로 이 칸을 비워, 한 실행에 팝업이 둘 불리지 않는다(둘이면
    `StreamlitInvalidLayoutContextError` 로 화면이 멈춘다 — 2026-10-10 브라우저 실측).
    """
    state: dict[str, object] = {SCENARIO_DIALOG_KEY: True, "other": 1}
    with patch.object(st, "session_state", state):
        forget_page_dialogs()
    assert state == {"other": 1}


def test_the_database_path_is_read_from_settings_at_call_time(
    sidebar_app: AppTest, tmp_path: Path
) -> None:
    """팝업 본문은 **부를 때의** `settings.DUCKDB_PATH` 를 쓴다(테스트가 갈아끼운다)."""
    import capa_simulation.settings as settings

    seen: list[str] = []

    def _repository(path: str) -> FakeRepository:
        seen.append(path)
        return FakeRepository()

    with (
        patch.object(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb"),
        patch.object(target, "get_scenario_repository", _repository),
    ):
        _open(sidebar_app.run())
    assert seen and set(seen) == {str((tmp_path / "scenario.duckdb").resolve())}


def test_a_revision_the_compatibility_check_blocks_is_not_loaded(sidebar_app: AppTest) -> None:
    """팝업의 불러오기도 활성화 **전에** 옛 리비전 호환을 본다 — 시나리오 관리 화면과 같은 검사.

    활성화한 뒤에 계산이 죽으면 활성 시나리오가 이미 바뀐 뒤라 되돌릴 방법이 없다(2026-10-11 병합
    전 리뷰 — 시나리오 관리가 막는 리비전을 사이드바가 올렸다).
    """
    app = _open(sidebar_app.run())
    app.session_state["test_block_reason"] = "경로 키가 빈 옛 리비전입니다"
    app = app.button(key="sidebar_load_revision").click().run()

    assert not app.exception
    assert "test_activated_revision" not in app.session_state
    assert any("경로 키가 빈 옛 리비전" in item.value for item in app.error)
    assert app.session_state[SCENARIO_DIALOG_KEY] is True


def test_a_revision_renamed_while_the_dialog_is_open_is_still_the_one_loaded(
    sidebar_app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """팝업이 열린 동안 다른 세션이 고른 리비전의 이름을 바꿔도 「불러오기」는 고른 리비전을 올린다.

    radio 선택지 글자에는 리비전명이 든다. 브라우저가 옛 글자를 되보내면 Streamlit 1.63 은 그 글자를
    못 찾아 **예외 없이** 첫 선택지로 되돌렸다. 그래서 누른 회차에 실제로 올린 리비전 id 를 잰다.
    """
    from widget_browser import BrowserChoice

    newest = revision("revision-1c", "scenario-1", 3, "세 번째")
    picked = revision("revision-1b", "scenario-1", 2, "두 번째")
    monkeypatch.setitem(REVISIONS, "scenario-1", [newest, picked, *REVISIONS["scenario-1"]])
    app = _open(sidebar_app.run())
    browser = BrowserChoice(app, "radio", SIDEBAR_REVISION_KEY)
    browser.sync()
    assert browser.wire == "r1 · 초기"
    browser.pick("r2 · 두 번째")
    browser.run()
    assert app.session_state[SIDEBAR_REVISION_KEY] == "revision-1b"

    # 다른 세션이 이름을 바꾼다. 이 세션은 팝업에서 다른 조작을 한 번 한다.
    monkeypatch.setattr(picked, "revision_name", "바뀐 이름")
    browser.run()
    assert not app.exception
    assert browser.wire == "r2 · 바뀐 이름", "radio 가 옛 이름을 보입니다."

    app.button(key="sidebar_load_revision").click()
    browser.run()
    assert not app.exception
    assert app.session_state["test_activated_revision"] == "revision-1b"


def test_a_scenario_renamed_while_the_dialog_is_open_is_still_the_one_loaded(
    sidebar_app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """같은 팝업의 시나리오 상자도 고른 값을 매 회차 다시 적는다 — 글자에 시나리오명이 든다."""
    from widget_browser import BrowserChoice

    app = _open(sidebar_app.run())
    browser = BrowserChoice(app, "selectbox", SIDEBAR_SCENARIO_KEY)
    browser.sync()
    browser.pick("증산안 · SIM-002")
    browser.run()
    assert app.session_state[SIDEBAR_SCENARIO_KEY] == "scenario-2"

    monkeypatch.setattr(SCENARIOS[1], "scenario_name", "증산 새안")
    browser.run()
    assert not app.exception
    assert browser.wire == "증산 새안 · SIM-002", "상자가 옛 이름을 보입니다."

    app.button(key="sidebar_load_revision").click()
    browser.run()
    assert not app.exception
    assert app.session_state["test_activated_revision"] == "revision-2"


def test_names_in_the_dialog_are_shown_as_typed(
    sidebar_app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """머리 줄 캡션·radio 선택지·메모 캡션은 마크다운으로 그려진다. 사람이 적은 글은 글자 그대로."""
    from capa_simulation.components.literal_markdown import literal_markdown

    monkeypatch.setattr(LABEL, "scenario_name", "A~B~C")
    monkeypatch.setattr(LABEL, "revision_name", "$x$")
    odd = revision("revision-1", "scenario-1", 1, "*별*", "기간 2026-08-01~2026-08-31~")
    monkeypatch.setitem(REVISIONS, "scenario-1", [odd])
    app = _open(sidebar_app.run())

    assert any(
        item.value.startswith(
            f"올라와 있음 · {literal_markdown('A~B~C')} · r1 {literal_markdown('$x$')}"
        )
        for item in app.caption
    ), [item.value for item in app.caption]
    revisions = app.radio(key=SIDEBAR_REVISION_KEY)
    assert revisions.options == [literal_markdown("r1 · *별*")]
    assert list(revisions.proto.captions) == [
        "26.10.08 저장 · 올라와 있음 · " + literal_markdown("기간 2026-08-01~2026-08-31~")
    ]


def test_the_load_section_points_to_where_names_are_changed(sidebar_app: AppTest) -> None:
    """이름 변경은 시나리오 관리 페이지 몫이라 불러오기 구획 끝에 그리로 가는 단추 하나가 선다(S7).

    그 탭까지 열어야 하므로 링크가 아니라 단추다 — 기억된 탭이 설비 시나리오면 링크는 다른
    시나리오의 이름 칸에 닿는다. 시나리오 관리 페이지에서 연 팝업에는 서지 않는다(아래 시험).
    """
    route = "시나리오 관리에서 이름 바꾸기"
    app = _open(sidebar_app.run())
    assert route in [button.label for button in app.button]

    _open_save(app)
    assert route not in [button.label for button in app.button]


def test_the_popup_opened_on_the_management_page_draws_no_route_line() -> None:
    """시나리오 관리 페이지에서 연 팝업은 같은 화면이라 링크가 팝업을 닫지 못한다 — 「어디서
    고친다」 는 길 안내 글도, 그 자리의 바로 가기 단추도 두지 않는다(설계 규칙 UI-TXT-03 · AMB-06
    (나))."""
    app = AppTest.from_string(
        "from capa_simulation.components.scenario_status import _render_rename_route\n"
        "_render_rename_route(on_management_page=True)\n"
    ).run()
    assert not app.exception
    assert [item.value for item in app.caption] == []
    assert [item.value for item in app.markdown] == []
    assert list(app.button) == []


def test_an_empty_store_says_so_in_one_plain_line(sidebar_app: AppTest) -> None:
    """저장된 시나리오가 없으면 팝업은 그 값 한 줄만 평문으로 둔다 — 「어디서 등록하세요」 같은 하는
    법 · 길 안내 꼬리와 안내 상자를 붙이지 않는다(설계 규칙 AMB-02 (가) · UI-TXT-03)."""
    app = sidebar_app
    app.session_state["test_scenarios"] = []
    app = _open(app.run())

    captions = [str(item.value) for item in app.caption]
    assert "저장된 시나리오가 없습니다." in captions, captions
    assert not any("등록하세요" in text or "시나리오 관리" in text for text in captions), captions
    assert not app.info and not app.warning and not app.success


def test_a_scenario_without_revisions_says_so_in_one_plain_line(sidebar_app: AppTest) -> None:
    """고른 시나리오에 저장된 리비전이 없으면 불러오기 구획은 그 값 한 줄을 평문으로 둔다(안내
    상자 없이 — 설계 규칙 AMB-02 (가))."""
    app = sidebar_app
    app.session_state["test_scenarios"] = [scenario("scenario-9", "빈 시나리오", "SIM-9", "", 0)]
    with patch.dict(REVISIONS, {"scenario-9": []}):
        app = _open(app.run())

    assert "선택한 시나리오에 저장된 리비전이 없습니다." in [
        str(item.value) for item in app.caption
    ]
    assert not app.info
