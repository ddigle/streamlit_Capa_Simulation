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
from streamlit.testing.v1 import AppTest

import capa_simulation.components.scenario_status as target
from capa_simulation.components.capacity_gate import GateVerdict
from capa_simulation.components.scenario_status import (
    LOAD_MODE,
    SAVE_MODE,
    SCENARIO_DIALOG_KEY,
    SCENARIO_DIALOG_MODE_KEY,
    SCENARIO_FIELD_KEY,
    SIDEBAR_REVISION_KEY,
    SIDEBAR_SCENARIO_KEY,
    scenario_status_badge,
)
from capa_simulation.page_bootstrap import forget_page_dialogs
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
    def list_scenarios(self) -> list[SimpleNamespace]:
        _count_read()
        return SCENARIOS

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


@pytest.fixture
def sidebar_app() -> Iterator[AppTest]:
    """callback은 스크립트보다 먼저 실행되므로 모든 rerun을 같은 patch로 감싼다."""
    # 가짜의 모양이 제각각이라(함수·람다·클래스) 값 타입을 하나로 좁히지 않는다.
    replacements: dict[str, Any] = {
        "get_scenario_repository": lambda _path: FakeRepository(),
        "load_scenario_snapshot": load_snapshot,
        "pinned_connections": lambda *_paths: nullcontext(),
        "pending_edit_labels": lambda _page: list(st.session_state.get("test_pending_edits", [])),
        "active_persisted_scenario_id": lambda: "scenario-1",
        "active_persisted_revision_id": lambda: "revision-1",
        "active_scenario_label": lambda: LABEL,
        "latest_official_revision": lambda: st.session_state.get("test_official"),
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


def test_the_dialog_selects_and_loads_another_revision(sidebar_app: AppTest) -> None:
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
    assert [item.value for item in app.success] == ["증산안 r1을 불러왔습니다."]
    app.run()
    assert [item.value for item in app.success] == []


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


def test_the_dialog_saves_current_state_as_a_new_revision(sidebar_app: AppTest) -> None:
    app = _open_save(sidebar_app.run())
    # 공정 필터·조회기간도 리비전 프리셋에 담긴다 — 편집이 없어도 저장할 것이 있다.
    assert any("조회기간·공정 필터도 담깁니다" in item.value for item in app.caption)

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
    assert [item.value for item in app.success] == [
        "신규 리비전 r2를 저장했습니다. 가상 제품 1건이 포함되어 있습니다. "
        "실적과 대조할 수 없으므로 공식버전으로 발행하기 전에 확인하세요."
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
    assert [item.value for item in app.success] == [
        "신규 리비전 r2를 저장했습니다. 가상 제품 3건이 포함되어 있습니다. "
        "실적과 대조할 수 없으므로 공식버전으로 발행하기 전에 확인하세요."
    ]


def test_sidebar_save_without_virtual_products_says_only_what_it_saved(
    sidebar_app: AppTest,
) -> None:
    """가상 제품이 없으면 이력도 넘기지 않고 알림은 저장한 리비전 한 문장 그대로다."""
    app = _save(_open_save(sidebar_app.run()), "가상 제품 없는 저장")

    assert not app.exception
    assert app.session_state["test_saved_virtual_products"] == []
    assert [item.value for item in app.success] == ["신규 리비전 r2를 저장했습니다."]


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
    assert "저장하지 않은 편집을 버렸습니다." in {item.value for item in app.success}
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
    """편집 전부터 있던 오류는 저장을 막지 않는다. 대신 발행이 막힌다고 저장 뒤에 알린다."""
    app = sidebar_app
    app.session_state["test_save_verdict"] = GateVerdict(True, "공식버전으로 지정할 수 없습니다")
    app = _save(_open_save(app.run()), "고치는 중")

    assert not app.exception
    assert app.session_state["test_saved_revision_name"] == "고치는 중"
    assert any("공식버전으로 지정할 수 없습니다" in warning.value for warning in app.warning)


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
    app = app.checkbox(key="sidebar_discard_unsaved_changes").check().run()
    assert not app.button(key="sidebar_load_revision").disabled

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
