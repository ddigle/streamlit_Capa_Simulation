# Purpose: scenario sidebar 관련 정상·예외·회귀 동작을 검증한다.

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import capa_simulation.components.scenario_status as target
from capa_simulation.components.capacity_gate import GateVerdict
from capa_simulation.components.scenario_status import (
    SIDEBAR_REVISION_KEY,
    SIDEBAR_SCENARIO_KEY,
)
from capa_simulation.scenario_state import VIRTUAL_PRODUCTS_KEY
from capa_simulation.services.virtual_product import VirtualProductRecord


def scenario(scenario_id, name, code, revision_id, revision_no):
    return SimpleNamespace(
        scenario_id=scenario_id,
        scenario_name=name,
        source_simulation_code=code,
        source_simulation_name=name,
        active_revision_id=revision_id,
        active_revision_no=revision_no,
    )


def revision(revision_id, scenario_id, revision_no, name):
    return SimpleNamespace(
        revision_id=revision_id,
        scenario_id=scenario_id,
        revision_no=revision_no,
        revision_name=name,
    )


SCENARIOS = [
    scenario("scenario-1", "기준안", "SIM-001", "revision-1", 1),
    scenario("scenario-2", "증산안", "SIM-002", "revision-2", 1),
]
REVISIONS = {
    "scenario-1": [revision("revision-1", "scenario-1", 1, "초기")],
    "scenario-2": [revision("revision-2", "scenario-2", 1, "초기")],
}


class FakeRepository:
    def list_scenarios(self):
        return SCENARIOS

    def list_revisions(self, scenario_id):
        return REVISIONS[scenario_id]

    def latest_official_release(self):
        return None

    def list_virtual_products(self, revision_id):
        # 불러온 리비전(`revision-1`)의 가상 제품 이력. 테스트가 세션에 넣어 둔다.
        st.session_state["test_history_revision"] = revision_id
        return pd.DataFrame(
            st.session_state.get("test_parent_history", []),
            columns=["제품정보", "Stack", "원본 제품정보", "원본 Stack"],
        )

    def save_revision(self, scenario_id, tables, preset, **kwargs):
        st.session_state["test_saved_revision_name"] = kwargs["revision_name"]
        st.session_state["test_saved_virtual_products"] = list(kwargs.get("virtual_products", ()))
        return SimpleNamespace(
            scenario=SCENARIOS[0],
            revision=revision("revision-3", scenario_id, 2, kwargs["revision_name"]),
            preset=preset,
            tables=tables,
        )


def load_snapshot(_database_path, revision_id):
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
    st.session_state.pop(VIRTUAL_PRODUCTS_KEY, None)


TEST_SCRIPT = """
from pathlib import Path

import streamlit as st

import capa_simulation.components.scenario_status as target
target.render_scenario_controls(
    Path("unused.duckdb"), pending_edits=st.session_state.get("test_pending_edits", [])
)
"""


@pytest.fixture
def sidebar_app() -> Iterator[AppTest]:
    """callback은 스크립트보다 먼저 실행되므로 모든 rerun을 같은 patch로 감싼다."""
    replacements = {
        "get_scenario_repository": lambda _path: FakeRepository(),
        "load_scenario_snapshot": load_snapshot,
        "active_persisted_scenario_id": lambda: "scenario-1",
        "active_persisted_revision_id": lambda: "revision-1",
        "has_unsaved_scenario_changes": lambda: bool(st.session_state.get("test_unsaved", False)),
        "discard_unsaved_scenario_changes": lambda _tables, version: st.session_state.__setitem__(
            "test_reset_to_version", version
        ),
        "activate_persisted_snapshot": _activate,
        "get_effective_reference_version": lambda: 1,
        "get_effective_reference_tables": lambda: {
            "RQ_REQB": pd.DataFrame({"공정": ["공정 A"]}),
            "RQ_DISPLAY_ORDER": pd.DataFrame(),
        },
        "ensure_active_scenario": lambda _tables, _version: {
            "reference_version": 1,
            "revision": 1,
            "tables": {},
        },
        "revision_tables_for_save": lambda _active, tables: {"RQ_REQB": tables["RQ_REQB"].copy()},
        "capture_scenario_preset": lambda _tables: SimpleNamespace(),
        # 저장 검사는 따로 검증한다(`test_capacity_gate.py`). 여기서는 판정을 세션에서 읽어
        # 화면이 그 판정대로 움직이는지만 본다.
        "revision_save_verdict": lambda *_args: st.session_state.get(
            "test_save_verdict", GateVerdict(True)
        ),
    }
    originals = {name: getattr(target, name) for name in replacements}
    try:
        with patch.multiple(target, **replacements):
            yield AppTest.from_string(TEST_SCRIPT)
    finally:
        # 테스트 실패와 st.rerun 모두 원본 복원을 건너뛰어 다음 AppTest를 오염시키면 안 된다.
        for name, original in originals.items():
            assert getattr(target, name) is original, name


def test_sidebar_selects_and_loads_another_revision(sidebar_app: AppTest) -> None:
    app = sidebar_app.run()

    assert not app.exception
    assert [widget.label for widget in app.selectbox] == ["시나리오", "리비전"]

    app = app.selectbox(key=SIDEBAR_SCENARIO_KEY).select("scenario-2").run()
    assert app.selectbox(key=SIDEBAR_REVISION_KEY).value == "revision-2"

    # 라벨이 짧다. 무엇을 불러오는지는 바로 위 두 선택 상자가 말하고, 이 버튼은 「저장」
    # 과 한 줄에 반씩 서므로 긴 라벨이 들어가지 않는다.
    load_button = next(button for button in app.button if button.label == "불러오기")
    app = load_button.click().run()

    assert not app.exception
    assert app.session_state["test_activated_revision"] == "revision-2"


def test_sidebar_saves_current_state_as_a_new_revision(sidebar_app: AppTest) -> None:
    app = sidebar_app.run()

    revision_name = next(widget for widget in app.text_input if widget.label == "새 리비전명")
    app = revision_name.set_value("사이드바 저장안").run()
    save_button = next(button for button in app.button if button.label == "신규 리비전 저장")
    app = save_button.click().run()

    assert not app.exception
    assert app.session_state["test_saved_revision_name"] == "사이드바 저장안"
    assert app.session_state["test_activated_revision"] == "revision-3"


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
    app = _save(app.run(), "가상 제품 포함 저장")

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
    app = _save(app.run(), "이어 저장")

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
    app = _save(sidebar_app.run(), "가상 제품 없는 저장")

    assert not app.exception
    assert app.session_state["test_saved_virtual_products"] == []
    assert [item.value for item in app.success] == ["신규 리비전 r2를 저장했습니다."]


def test_discarding_edits_lives_in_the_scenario_box_only_when_there_are_edits(
    sidebar_app: AppTest,
) -> None:
    """「편집 되돌리기」는 모든 화면의 편집을 버리는 시나리오 단위 동작이다.

    본문 맨 위의 「활성 시나리오 · 수정본 N · 전체 입력 원본으로 초기화」 줄을 없애고 이
    상자로 옮겼다(2026-09-29 사용자 결정). 버릴 것이 없으면 서지 않는다.
    """
    app = sidebar_app.run()
    assert "sidebar_reset_active_scenario" not in {button.key for button in app.button}

    app.session_state["test_unsaved"] = True
    app.run()
    app.button(key="sidebar_reset_active_scenario").click().run()

    assert not app.exception
    assert app.session_state["test_reset_to_version"] == 1
    assert "저장하지 않은 편집을 버렸습니다." in {item.value for item in app.success}


def _save(app: AppTest, name: str) -> AppTest:
    revision_name = next(widget for widget in app.text_input if widget.label == "새 리비전명")
    app = revision_name.set_value(name).run()
    save_button = next(button for button in app.button if button.label == "신규 리비전 저장")
    return save_button.click().run()


def test_a_save_the_gate_refuses_writes_nothing(sidebar_app: AppTest) -> None:
    """편집이 계산을 깨뜨렸으면 저장하지 않고 그 이유를 그 자리에서 말한다."""
    app = sidebar_app
    app.session_state["test_save_verdict"] = GateVerdict(False, "이번 편집이 깨뜨린 것입니다")
    app = _save(app.run(), "깨진 저장안")

    assert not app.exception
    assert "test_saved_revision_name" not in app.session_state
    assert any("이번 편집이 깨뜨린" in error.value for error in app.error)


def test_a_save_with_an_old_error_is_kept_and_warned(sidebar_app: AppTest) -> None:
    """편집 전부터 있던 오류는 저장을 막지 않는다. 대신 발행이 막힌다고 저장 뒤에 알린다."""
    app = sidebar_app
    app.session_state["test_save_verdict"] = GateVerdict(True, "공식버전으로 지정할 수 없습니다")
    app = _save(app.run(), "고치는 중")

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
    app = app.run()
    assert not app.exception

    notices = " ".join(item.value for item in app.caption) + " ".join(
        item.value for item in app.warning
    )
    assert "기준 정보 · UPEH" in notices
    # 불러오기는 「변경을 버리고 불러오기」를 체크해야 열린다.
    assert app.button(key="sidebar_load_revision").disabled
    app = app.checkbox(key="sidebar_discard_unsaved_changes").check().run()
    assert not app.button(key="sidebar_load_revision").disabled

    # 저장은 「적용하지 않은 편집을 버리고 저장」을 체크해야 된다. 버튼은 잠그지 않는다 — 체크하지
    # 않고 누르면 저장하지 않고 그렇다고 알린다(아래 테스트가 잠그지 않는 까닭을 말한다).
    app = _save(app, "체크 없이 누른 저장안")
    assert "test_saved_revision_name" not in app.session_state
    assert any("저장하지 않았습니다" in item.value for item in app.warning)
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
    """
    app = sidebar_app.run()
    revision_name = next(widget for widget in app.text_input if widget.label == "새 리비전명")
    app = revision_name.set_value("E2E-D1b-rev").run()
    save_button = next(button for button in app.button if button.label == "신규 리비전 저장")
    assert not save_button.disabled

    app.session_state["test_pending_edits"] = ["생산 계획 · 수율"]
    app = save_button.click().run()

    assert not app.exception
    assert "test_saved_revision_name" not in app.session_state
    # 누른 회차에 상자의 줄이 바뀌면(적용 전 편집 경고가 새로 서면) 팝업이 새 요소로 다시 서며
    # 닫힌다. 그래서 막았다는 알림은 **팝업 밖에도** 있어야 보인다.
    outside = _refusals_outside_popover(app.sidebar)
    assert outside, "팝업 밖에 저장을 막았다는 알림이 없습니다"
    assert all("생산 계획 · 수율" in refusal for refusal in outside)

    # 막은 회차는 다시 돌리지 않았다 — 다음 조작에도 적용 전 편집 경고가 그대로 선다.
    app = app.run()
    assert "test_saved_revision_name" not in app.session_state
    assert any("생산 계획 · 수율" in item.value for item in app.caption)


def _refusals_outside_popover(node: object) -> list[str]:
    """저장을 막았다는 알림 가운데 팝업 **밖**에 그려진 것의 글."""
    found: list[str] = []
    for child in getattr(node, "children", {}).values():
        kind = getattr(child, "type", None)
        if kind == "popover":
            continue
        if kind == "warning" and "저장하지 않았습니다" in str(getattr(child, "value", "")):
            found.append(str(child.value))
        found.extend(_refusals_outside_popover(child))
    return found


def test_without_unapplied_edits_nothing_extra_is_asked(sidebar_app: AppTest) -> None:
    app = sidebar_app.run()

    assert not app.exception
    assert not app.button(key="sidebar_load_revision").disabled
    assert "sidebar_save_discards_pending_edits" not in {box.key for box in app.checkbox}


def _fill_and_save(app: AppTest, name: str, note: str) -> AppTest:
    app.text_input(key=target.SAVE_REVISION_NAME_KEY).set_value(name)
    app.text_area(key=target.SAVE_REVISION_NOTE_KEY).set_value(note)
    app = app.run()
    save_button = next(button for button in app.button if button.label == "신규 리비전 저장")
    return save_button.click().run()


def test_a_refused_save_keeps_the_typed_name_and_memo(sidebar_app: AppTest) -> None:
    """거절된 저장은 적은 리비전명·메모를 지우지 않는다(2026-10-01 E2E 후속).

    `clear_on_submit` 은 제출만 보면 비워, 계산 검사나 적용 전 편집 확인에 막힌 저장도 적은 글을
    잃었다. 막힌 까닭을 고치고 그대로 다시 누르면 되어야 한다.

    AppTest 는 `clear_on_submit` 의 비우기를 흉내 내지 않아(그것은 브라우저 쪽 동작이다) 이
    테스트만으로는 옛 결함이 재현되지 않는다. 거절 쪽은 브라우저로 확인했고, 여기서는 거절과
    재시도가 적은 글로 이어지는 흐름을 고정한다. 성공 쪽 비우기는 아래 테스트가 잡는다.
    """
    app = sidebar_app
    app.session_state["test_save_verdict"] = GateVerdict(False, "이번 편집이 깨뜨린 것입니다")
    app = _fill_and_save(app.run(), "막힐 저장안", "고친 까닭")

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
    """저장에 성공하면 다음 회차의 칸이 빈다 — 한 번 더 눌러 같은 이름의 리비전이 또 서지 않게."""
    app = _fill_and_save(sidebar_app.run(), "성공할 저장안", "남지 않을 메모")

    assert not app.exception
    assert app.session_state["test_saved_revision_name"] == "성공할 저장안"
    assert app.text_input(key=target.SAVE_REVISION_NAME_KEY).value == ""
    assert app.text_area(key=target.SAVE_REVISION_NOTE_KEY).value == ""
    assert target.SAVE_FORM_CLEAR_KEY not in app.session_state
