# Purpose: 기준 정보 종류 단추와 범용 편집 그리드(편집 표 아홉)의 새 동작을 AppTest 로 본다.

"""기준 정보 화면은 탭 대신 종류 단추 한 줄과 큰 편집 표 하나다(2026-11-02 사용자 결정). 편집 표
아홉(`reference_grid_keys.EDIT_TABLES`)이 모두 범용 편집 그리드라 초안을 업무 키로 세션에 두므로, 옛
`st.data_editor` 와 달리 종류를 바꾸거나 화면을 떠나거나 줄 차례만 바뀌어도 편집이 남고 필터를
잠그지 않는다. 시험은 `tests/edit_grid_fake.py` 대역으로 브라우저가 보내는 op 를 넣는다.
"""

from __future__ import annotations

from typing import Any

import pytest
from alert_marks import flashed, infos, successes
from edit_grid_fake import (
    FAKE_EVENT_KEY,
    Calls,
    deliver_ops,
    install_fake_edit_grid,
    last,
    outbox,
    send_ops,
)
from streamlit.testing.v1 import AppTest
from test_reference_data_page import (
    DATASET,
    DISPLAY_ORDER_SWAP_TEST_SCRIPT,
    EDITOR_KEYS,
    REAL_APPLY_TEST_SCRIPT,
    RENAMED_TWO_PROCESS_TEST_SCRIPT,
    TEST_SCRIPT,
    TWO_PROCESS_TEST_SCRIPT,
    _download_frame,
    _filtered_editor_app,
    _grid_write,
    _open_paste,
    _paste,
    _scenario_table,
    _visible_keys,
    _walk,
)

from capa_simulation.components import page_tabs, reference_grid
from capa_simulation.components.edit_grid import feed_key
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.tab_marks import pending_segments_style
from capa_simulation.reference_grid_keys import (
    DATASET_KEY,
    DATASETS,
    DEFAULT_DATASET,
    EDIT_TABLES,
    GRID_HOST,
    cells_key,
    history_key,
)
from capa_simulation.services.edit_grid import DROPPED_TOAST, change_counts, draft_from

FEED = feed_key(GRID_HOST)
RUN_DAY_CELLS = cells_key("RQ_RUN_DAY")
APPLY = "capa_run_day_editor_apply"
# 옛 `st.data_editor` 편집표가 적용하지 않은 편집이 있을 때 사이드바 필터 아래에 쓰던 잠금 문구.
OLD_FILTER_LOCKED_NOTICE = (
    "적용하지 않은 편집이 있어 필터를 잠갔습니다. 적용하거나 「편집 취소」를 누른 뒤 바꾸세요."
)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return install_fake_edit_grid(monkeypatch)


def _open(script: str, name: str = "일수") -> AppTest:
    app = AppTest.from_string(script, default_timeout=60)
    app.session_state[DATASET_KEY] = DATASET[name]
    app.run()
    assert not app.exception, app.exception
    return app


def _choose(app: AppTest, name: str) -> AppTest:
    app.session_state[DATASET_KEY] = DATASET[name]
    app.run()
    assert not app.exception, app.exception
    return app


def _draft(app: AppTest) -> Any:
    return app.session_state[RUN_DAY_CELLS] if RUN_DAY_CELLS in app.session_state else None


def _shell_rows(calls: Calls) -> list[str]:
    """마지막 껍데기의 보이는 줄 차례(분류 칸 하나 — 64자 코드 한 글자씩)."""
    shell = last(calls, GRID_HOST)
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
    return [shell["dims"][0][alphabet.index(code)] for code in shell["codes"][0]]


def test_dataset_buttons_replace_the_tabs(calls: Calls) -> None:
    """탭이 없고 종류 단추 한 줄(옛 탭 차례, 기본 UPEH)이 선다 — 설비대수 안쪽 탭도 단추로 폈다."""
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()
    assert not app.exception
    assert not app.tabs
    control = app.segmented_control(key=DATASET_KEY)
    assert control.options == list(DATASETS.values())
    assert control.value == DEFAULT_DATASET == "RQ_UPEH"
    assert list(DATASETS) == [
        "RQ_UPEH",
        "RQ_EQP_OWN",
        "RQ_EQP_LENT",
        "RQ_EQP_AVBL",
        "EQP_OVERVIEW",
        "RQ_RUN_RATE",
        "RQ_VITAL",
        "RQ_RUN_DAY",
        "RQ_LOT_RATIO",
        "RQ_WF_RATIO",
        "STEP",
    ]
    # 기본 종류 UPEH 도 그리드다 — 마운트는 feed 다음 껍데기 차례 하나다.
    assert [key for key, _ in calls] == [FEED, GRID_HOST]
    assert last(calls, GRID_HOST)["table"] == "RQ_UPEH"


def test_switching_datasets_keeps_the_grid_draft_and_the_mount(calls: Calls) -> None:
    """일수를 고치고 다른 종류(편집 표·읽기 보기)를 골랐다 돌아와도 초안이 남는다. 그리드 요소는
    모든 회차에 같은 key·같은 차례로 서고(다시 마운트되지 않는다) 편집 표는 그 표를, 읽기 보기는 표
    없는 껍데기를 싣는다."""
    app = _open(TWO_PROCESS_TEST_SCRIPT)
    app = _grid_write(app, calls, "Process-A", "202608", "20")
    assert _draft(app) == {"cells": {"Process-A": {"202608": 20.0}}, "bad": {}}

    for name in ("효율", "설비대수 현황", "STEP 구성", "UPEH"):
        app = _choose(app, name)
        assert last(calls, GRID_HOST)["table"] == (
            DATASET[name] if DATASET[name] in EDIT_TABLES else None
        )
        assert _draft(app) == {"cells": {"Process-A": {"202608": 20.0}}, "bad": {}}
    app = _choose(app, "일수")
    feed = last(calls, FEED)
    assert feed["table"] == "RQ_RUN_DAY" and feed["counts"]["cells"] == 1
    assert feed["drows"]  # 초안이 다시 그려진다
    keys = [key for key, _ in calls]
    assert keys == [FEED, GRID_HOST] * (len(keys) // 2)


def test_an_op_sent_just_before_switching_lands_in_its_own_table(calls: Calls) -> None:
    """표를 바꾸는 회차에 함께 온 op(고친 뒤 곧바로 다른 종류를 누름)도 그 표 초안에 쓴다."""
    app = _open(TWO_PROCESS_TEST_SCRIPT)
    app.session_state[DATASET_KEY] = DATASET["효율"]
    app = send_ops(
        app,
        calls,
        {"op": "write", "rows": ["Process-B"], "cols": ["202608"], "values": [["29"]]},
        host=GRID_HOST,
    )
    assert not app.exception
    assert last(calls, GRID_HOST)["table"] == "RQ_RUN_RATE"
    assert _draft(app) == {"cells": {"Process-B": {"202608": 29.0}}, "bad": {}}


def test_the_pending_dot_style_marks_the_nth_button() -> None:
    style = pending_segments_style(DATASET_KEY, list(DATASETS), {"RQ_RUN_DAY", "RQ_UPEH"})
    assert '[role="radio"]:nth-of-type(8)::after' in style
    assert '[role="radio"]:nth-of-type(1)::after' in style
    assert style.count("::after") == 2
    assert pending_segments_style(DATASET_KEY, list(DATASETS), set()) == ""


def test_a_row_order_change_keeps_the_grid_draft_on_its_business_key(calls: Calls) -> None:
    """공용 표시순서만 바뀐 회차에 그리드 초안은 남고 같은 업무 키 칸에 붙는다 — 옛 편집표는 줄
    위치라 비우고 알렸다(그 알림에 일수가 끼지 않는다)."""
    app = _open(DISPLAY_ORDER_SWAP_TEST_SCRIPT)
    assert _shell_rows(calls) == ["Process-A", "Process-B"]
    app = _grid_write(app, calls, "Process-A", "202608", "20")

    app.session_state["test_display_order_descending"] = True
    app.run()
    assert not app.exception
    assert _shell_rows(calls) == ["Process-B", "Process-A"]
    assert _draft(app) == {"cells": {"Process-A": {"202608": 20.0}}, "bad": {}}
    assert not any("일수" in str(item.value) for item in app.warning)


def test_the_filter_is_not_locked_while_a_grid_draft_is_pending(calls: Calls) -> None:
    app = _filtered_editor_app("일수", "capa_run_day_editor", "공정")
    app = _grid_write(app, calls, "Process-B", "202608", "20")
    widget = app.sidebar.multiselect(key="capa_run_day_editor_filter_공정")
    assert not widget.disabled
    assert OLD_FILTER_LOCKED_NOTICE not in {str(item.value) for item in app.sidebar.caption}
    # 필터를 풀어도 초안은 그대로다(업무 키).
    widget.set_value([]).run()
    assert not app.exception
    assert last(calls, FEED)["filters"] is None
    assert _draft(app) == {"cells": {"Process-B": {"202608": 20.0}}, "bad": {}}


_LEAVE_PROBE = (
    '    exec(compile(page.read_text(encoding="utf-8"), str(page), "exec"))\n'
    "    from capa_simulation.components import page_tabs as _probe_tabs\n"
    "    from capa_simulation.components.scenario_edit_bar import pending_edit_labels as _labels\n"
    '    st.session_state["probe_other_page"] = _labels("home.py")\n'
    '    st.session_state["probe_leave"] = _probe_tabs.leave_notice("reference_data.py")\n'
    '    st.session_state["probe_marks"] = _probe_tabs.page_unsaved_marks("home.py")\n'
)


def test_a_grid_draft_stays_when_leaving_and_shows_on_every_page(calls: Calls) -> None:
    """그리드 초안은 세션 칸이라 화면을 떠나도 남는다 — 다른 화면의 사이드바 「적용 전 편집」·화면
    탭 점에 「기준 정보 · 일수」 가 서고, 떠날 때 묻지 않는다."""
    script = TWO_PROCESS_TEST_SCRIPT.replace(
        '    exec(compile(page.read_text(encoding="utf-8"), str(page), "exec"))\n', _LEAVE_PROBE, 1
    )
    assert script != TWO_PROCESS_TEST_SCRIPT
    app = _open(script)
    app = _grid_write(app, calls, "Process-A", "202608", "20")
    assert app.session_state["probe_other_page"] == ["기준 정보 · 일수"]
    assert app.session_state["probe_leave"] == ""
    assert "기준 정보 · 일수" in app.session_state["probe_marks"]["app_pages/reference_data.py"]


_CHIP_PROBE = (
    '    exec(compile(page.read_text(encoding="utf-8"), str(page), "exec"))\n'
    "    from capa_simulation.components.change_summary import session_changes as _changes\n"
    '    st.session_state["probe_here"] = _changes("reference_data.py", hrefs={})\n'
    '    st.session_state["probe_there"] = _changes("home.py", hrefs={})\n'
)


def test_a_hand_edited_draft_is_named_as_an_unapplied_edit_in_the_chip(calls: Calls) -> None:
    """칸을 손으로 고친 일을 머리 칩 · 판이 「붙여넣기 대기」 라 부르지 않는다(UI-DAT-11). 화면을
    떠나도 남으므로 묶음은 「화면을 떠나면 사라짐」 이 아니라 「저장 안 함」 이다."""
    script = TWO_PROCESS_TEST_SCRIPT.replace(
        '    exec(compile(page.read_text(encoding="utf-8"), str(page), "exec"))\n', _CHIP_PROBE, 1
    )
    assert script != TWO_PROCESS_TEST_SCRIPT
    app = _open(script)
    app = _grid_write(app, calls, "Process-A", "202608", "20")

    for probe in ("probe_here", "probe_there"):
        [item] = app.session_state[probe]
        assert (item["group"], item["page"]) == ("keep", "기준 정보")
        assert (item["top"], item["text"]) == ("기준 정보 적용 전", "적용 전 편집 · 일수")


def test_a_fractional_day_is_a_cell_error_and_apply_stops_on_it(calls: Calls) -> None:
    """일수는 정수만 받는다 — 30.5 는 칸 오류로 남고(옛 편집표는 말없이 30), 「변경사항 적용」 은
    고칠 칸을 알리고 멈춘다."""
    app = _open(TWO_PROCESS_TEST_SCRIPT)
    app = _grid_write(app, calls, "Process-A", "202608", "30.5")
    feed = last(calls, FEED)
    assert feed["counts"] == {"cells": 1, "rows": 1, "errors": 1}
    assert feed["bad"] == [[0, 0, "30.5", "int"]]
    assert "고칠 칸 1개" in " ".join(str(item.value) for item in app.markdown)

    app.button(key=APPLY).click().run()
    assert not app.exception
    errors = [str(item.value) for item in app.error]
    # 알림은 마크다운이라 분류 값은 막아 싣는다(「Process-A」 의 `-`).
    assert errors == [
        reference_grid.ERRORS_NOTICE.format(
            n="1", places=f"{literal_markdown('Process-A')} · 202608"
        )
    ], errors
    assert "test_month_updates" not in app.session_state
    assert _draft(app) == {"cells": {}, "bad": {"Process-A": {"202608": ("30.5", "int")}}}


def test_thousands_commas_are_read_and_text_is_a_cell_error(calls: Calls) -> None:
    app = _open(TWO_PROCESS_TEST_SCRIPT)
    app = _grid_write(app, calls, "Process-A", "202608", "1,234")
    app = _grid_write(app, calls, "Process-B", "202608", "#N/A")
    assert _draft(app) == {
        "cells": {"Process-A": {"202608": 1234.0}},
        "bad": {"Process-B": {"202608": ("#N/A", "num")}},
    }


def test_apply_raises_the_revision_and_drops_only_that_tables_draft(calls: Calls) -> None:
    """적용은 옛 편집표와 같은 길이다 — 활성 리비전이 오르고 새 내용 토큰이 서며, 작업 줄 아래에
    성공 글이 서고, 그 표 초안만 사라진다."""
    app = _open(REAL_APPLY_TEST_SCRIPT)
    # 시험 대본의 첫 활성 시나리오 — 리비전 1, 내용 토큰은 대본이 정한 값.
    revision, token = 1, "test-capacity-real-apply-page"
    assert "active_scenario" not in app.session_state
    app = _grid_write(app, calls, "Process-A", "202608", "20")
    app.button(key=APPLY).click().run()
    assert not app.exception

    after = app.session_state["active_scenario"]
    assert after["revision"] == revision + 1
    assert after["content_token"] != token
    assert _scenario_table(app, "RQ_RUN_DAY")["RUN_DAY"].tolist() == [20.0]
    assert any(
        "RQ_RUN_DAY 편집값을 활성 시나리오에 적용했습니다" in str(s.value) for s in successes(app)
    )
    assert _draft(app) is None
    assert last(calls, FEED)["counts"]["cells"] == 0
    assert app.button(key=APPLY).disabled


def test_a_business_rule_error_is_a_sentence_and_keeps_the_draft(calls: Calls) -> None:
    """UPEH 경로가 쓰는 일수 칸을 비우면 적용할 때 문장으로 막고(칸 오류가 아니다) 초안은 남는다."""
    app = _open(TEST_SCRIPT)
    app = _grid_write(app, calls, "Process-A", "202608", "")
    assert last(calls, FEED)["counts"] == {"cells": 1, "rows": 1, "errors": 0}
    app.button(key=APPLY).click().run()
    assert not app.exception
    errors = [str(item.value) for item in app.error]
    assert any("UPEH 경로가 씁니다" in error and "Process-A" in error for error in errors), errors
    assert "test_month_updates" not in app.session_state
    assert _draft(app) == {"cells": {"Process-A": {"202608": None}}, "bad": {}}


def test_a_source_change_drops_the_grid_draft_and_the_ops_sent_before(calls: Calls) -> None:
    """원본(버전·리비전·기간)이 바뀌면 초안·이력을 버린다 — 새 `gen` 이 서서 그 전에 보낸 op 는
    버려지고 수가 토스트로 간다."""
    app = _open(TWO_PROCESS_TEST_SCRIPT)
    app = _grid_write(app, calls, "Process-A", "202608", "20")
    old_gen = last(calls, FEED)["gen"]

    app.session_state["reference_data_source_token"] = "다른 원본"
    app.run()
    assert not app.exception
    assert _draft(app) is None
    assert last(calls, FEED)["gen"] != old_gen

    app = send_ops(
        app,
        calls,
        {"op": "write", "rows": ["Process-B"], "cols": ["202608"], "values": [["25"]]},
        host=GRID_HOST,
        gen=old_gen,
    )
    assert _draft(app) is None
    toast = last(calls, FEED)["toast"]
    assert toast is not None and DROPPED_TOAST.format(n="1") in toast["text"]


def test_the_paste_popup_warns_about_the_draft_and_applying_it_drops_the_draft(
    calls: Calls,
) -> None:
    app = _open(TWO_PROCESS_TEST_SCRIPT)
    app = _grid_write(app, calls, "Process-A", "202608", "20")
    app = _open_paste(app, "capa_run_day_editor")
    (opening,) = flashed(app, "warning")
    assert reference_grid.PASTE_DROPS_DRAFT_NOTICE.format(n="1") in opening.value
    assert not app.warning
    app.text_area(key="capa_run_day_editor_csv_clipboard").set_value(
        "공정\t202608\nProcess-A\t28\nProcess-B\t31\n"
    )
    app = next(b for b in app.button if b.label == "붙여넣기 일괄 적용").click().run()
    assert not app.exception
    saved = app.session_state["test_month_updates"]["RQ_RUN_DAY"]
    assert dict(zip(saved["공정"], saved["RUN_DAY"], strict=True)) == {
        "Process-A": 28.0,
        "Process-B": 31.0,
    }
    assert _draft(app) is None
    assert history_key("RQ_RUN_DAY") not in app.session_state or (last(calls, FEED)["undo"] == 0)


def test_undo_and_redo_go_through_the_server_history(calls: Calls) -> None:
    app = _open(TWO_PROCESS_TEST_SCRIPT)
    app = _grid_write(app, calls, "Process-A", "202608", "20")
    app = send_ops(app, calls, {"op": "undo"}, host=GRID_HOST)
    assert _draft(app) is None
    assert (last(calls, FEED)["undo"], last(calls, FEED)["redo"]) == (0, 1)
    app = send_ops(app, calls, {"op": "redo"}, host=GRID_HOST)
    assert _draft(app) == {"cells": {"Process-A": {"202608": 20.0}}, "bad": {}}


def test_the_action_row_sits_above_the_grid_and_discard_drops_the_draft(calls: Calls) -> None:
    """작업 줄(적용·붙여넣기·편집 취소·변경 수)은 표 위다 — 「편집 취소」 는 그 표 초안만 버린다."""
    app = _open(TWO_PROCESS_TEST_SCRIPT)
    assert app.button(key=APPLY).disabled
    assert "capa_run_day_editor_discard" not in {button.key for button in app.button}
    app = _grid_write(app, calls, "Process-A", "202608", "20")
    elements = _walk(app.main)
    keys = [getattr(node, "key", None) for node in elements]
    assert keys.index(APPLY) < keys.index("capa_run_day_editor_discard")
    assert "**변경사항 확인** &nbsp;1개 값 · 1개 행" in {str(item.value) for item in app.markdown}
    app.button(key="capa_run_day_editor_discard").click().run()
    assert not app.exception
    assert _draft(app) is None


def test_the_grid_host_holds_tab_clicks_like_the_other_edit_grids() -> None:
    """화면 탭 줄 붙들기(`<tabs-hold>`)가 기준 정보 그리드도 편집 칸으로 본다."""
    assert GRID_HOST in page_tabs.EDIT_HOST_KEYS
    assert GRID_HOST == "reference_grid"


# ------------------------------- 나머지 여덟 표 — 효율·여유율·설비대수 셋·Lot·WF·UPEH

# 표마다 보이는 첫 줄에 쓸 값(그 표가 받는 값).
VALID_VALUES = {
    "RQ_UPEH": "55",
    "RQ_EQP_OWN": "7",
    "RQ_EQP_LENT": "1.5",
    "RQ_EQP_AVBL": "3",
    "RQ_RUN_RATE": "0.5",
    "RQ_VITAL": "1.2",
    "RQ_RUN_DAY": "20",
    "RQ_LOT_RATIO": "0.5",
    "RQ_WF_RATIO": "85%",
}


def test_every_edit_table_rides_the_one_grid_and_keeps_its_own_draft(calls: Calls) -> None:
    """편집 표 아홉이 모두 같은 그리드 마운트에 실린다 — 종류를 바꾸면 그 표를 싣고(다시 마운트하지
    않는다), 표마다 고친 초안은 다른 표를 고르고 돌아와도 제 표에 남는다. 그 표의 작업 줄(적용 단추
    key)이 서고, 초안이 있는 표의 단추에 점이 찍힌다."""
    assert set(VALID_VALUES) == set(EDIT_TABLES)
    app = _open(TWO_PROCESS_TEST_SCRIPT, "UPEH")
    written: dict[str, str] = {}
    for table in EDIT_TABLES:
        app.session_state[DATASET_KEY] = table
        app.run()
        assert not app.exception
        shell = last(calls, GRID_HOST)
        assert shell["table"] == table, table
        key = _visible_keys(calls)[0]
        app = _grid_write(app, calls, key, "202608", VALID_VALUES[table])
        written[table] = key
        assert f"{EDITOR_KEYS[table]}_apply" in {button.key for button in app.button}
        assert not app.button(key=f"{EDITOR_KEYS[table]}_apply").disabled

    for table, key in written.items():
        draft = app.session_state[cells_key(table)]
        assert draft is not None and draft["bad"] == {}, table
        assert list(draft["cells"]) == [key], table
    assert app.session_state[cells_key("RQ_WF_RATIO")]["cells"][written["RQ_WF_RATIO"]] == {
        "202608": 0.85
    }
    keys = [name for name, _ in calls]
    assert keys == [FEED, GRID_HOST] * (len(keys) // 2)
    style = pending_segments_style(DATASET_KEY, list(DATASETS), set(EDIT_TABLES))
    assert style.count("::after") == len(EDIT_TABLES)


@pytest.mark.parametrize("name", ["효율", "Lot측정률", "WF측정률"])
def test_ratio_tables_read_percent_and_refuse_a_whole_number(calls: Calls, name: str) -> None:
    """효율·측정률은 분수 1 이 상한이다 — 「85」 는 칸 오류(85 배가 되는 실수를 막는다)로 남고,
    「85%」 는 0.85 로 받는다. 오류 문구는 껍데기 글이 0.85 · 85% 꼴을 알려 준다."""
    app = _open(TWO_PROCESS_TEST_SCRIPT, name)
    table = DATASET[name]
    shell = last(calls, GRID_HOST)
    assert shell["fmt"]["kind"] == "percent" and shell["fmt"]["max"] == 1.0
    assert "85% 는 0.85 또는 85% 로 적습니다" in shell["texts"]["errors"]["max"]
    first, second = _visible_keys(calls)[:2]
    app = _grid_write(app, calls, first, "202608", "85")
    app = _grid_write(app, calls, second, "202608", "85%")
    assert app.session_state[cells_key(table)] == {
        "cells": {second: {"202608": 0.85}},
        "bad": {first: {"202608": ("85", "max")}},
    }
    feed = last(calls, FEED)
    assert feed["counts"]["errors"] == 1
    app.button(key=f"{EDITOR_KEYS[table]}_apply").click().run()
    assert not app.exception
    assert any("고칠 칸 1개" in str(item.value) for item in app.error)
    assert "test_month_updates" not in app.session_state


def test_the_vital_table_takes_a_percent_over_one(calls: Calls) -> None:
    """여유율(편중률)은 1 을 넘을 수 있다 — 「150%」 를 1.5 로 받는다(상한 없음)."""
    app = _open(TWO_PROCESS_TEST_SCRIPT, "여유율")
    assert last(calls, GRID_HOST)["fmt"]["max"] is None
    key = _visible_keys(calls)[0]
    app = _grid_write(app, calls, key, "202608", "150%")
    assert app.session_state[cells_key("RQ_VITAL")] == {"cells": {key: {"202608": 1.5}}, "bad": {}}


@pytest.mark.parametrize(
    ("name", "column"),
    [
        ("설비대수 보유", "설비보유"),
        ("설비대수 대여", "설비대여평가"),
        ("설비대수 가용", "가용대수"),
    ],
)
def test_an_equipment_blank_is_zero_units(calls: Calls, name: str, column: str) -> None:
    """설비대수는 빈칸 = 0 대다 — 비운 칸은 0 으로 다듬어 초안에 들고(양식이 0 이면 바뀐 것이
    없다), 적용하면 0 대로 저장한다. 껍데기 형식이 그 규칙을 브라우저에 알린다(「빈칸 = 0」)."""
    app = _open(TWO_PROCESS_TEST_SCRIPT, name)
    table = DATASET[name]
    shell = last(calls, GRID_HOST)
    assert shell["fmt"]["blankZero"] is True
    assert shell["fmt"]["kind"] == "fixed" and shell["fmt"]["digits"] == 2
    app = _grid_write(app, calls, "Process-A", "202608", "4")
    app = _grid_write(app, calls, "Process-A", "202608", "")
    draft = app.session_state[cells_key(table)]
    template_zero = draft is None
    if not template_zero:
        assert draft == {"cells": {"Process-A": {"202608": 0.0}}, "bad": {}}
        app.button(key=f"{EDITOR_KEYS[table]}_apply").click().run()
        assert not app.exception
        saved = app.session_state["test_month_updates"][table]
        values = dict(zip(saved["공정"], saved[column], strict=True))
        assert values.get("Process-A", 0.0) == 0.0


def test_an_emptied_ratio_table_rides_the_grid_as_an_empty_table(calls: Calls) -> None:
    """측정률 표가 통째로 비면 그리드는 빈 표(머리만)를 싣고, 작업 줄 칸에 빈 결과 한 줄을 쓴다 —
    1.0 으로 계산한다는 것은 그 줄의 풍선이다(파란 상자 아님). 거를 줄이 없어 사이드바 필터는 서지
    않는다."""
    app = _open(REAL_APPLY_TEST_SCRIPT, "Lot측정률")
    key = _visible_keys(calls)[0]
    app = _grid_write(app, calls, key, "202608", "")
    app.button(key="capa_lot_ratio_editor_apply").click().run()
    assert not app.exception
    app.run()
    shell = last(calls, GRID_HOST)
    assert shell["table"] == "RQ_LOT_RATIO" and shell["rows"] == 0
    assert not any("측정률" in str(item.value) for item in infos(app))
    empty_lines = [item for item in app.caption if "행이 없습니다" in str(item.value)]
    assert [str(item.value) for item in empty_lines] == ["이 기간에 Lot측정률 행이 없습니다."]
    assert "측정률 1.0 으로 계산합니다" in empty_lines[0].proto.help
    assert not any(
        str(widget.key).startswith("capa_lot_ratio_editor_filter") for widget in app.multiselect
    )


def test_a_big_table_loads_only_the_filtered_or_first_rows_and_applies_the_whole(
    calls: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """큰 표 안전 상한(칸 수 · 껍데기 바이트)을 넘으면 사이드바 필터로 고른 줄이나 앞 줄만 싣고
    작업 줄 아래 표지 한 줄(풍선 — 고르는 법 · 적용 범위)로 알린다(파란 상자 아님). 초안은 업무
    키라 실은 줄이 바뀌어도 제 줄에 남고, 적용은 언제나 전체 양식에 덮는다. 고칠 칸 알림도 지금
    싣지 않은 줄의 오류까지 센다."""
    monkeypatch.setattr(reference_grid, "CAP_CELLS", 1)
    monkeypatch.setattr(reference_grid, "CAP_ROWS", 1)
    app = _open(TWO_PROCESS_TEST_SCRIPT)
    assert _visible_keys(calls) == ["Process-A"]
    notices = {str(item.value): item.proto.help for item in app.caption}
    assert notices[reference_grid.CAP_HEAD_NOTICE.format(rows=2, cells=2, shown=1)] == (
        reference_grid.CAP_HELP
    )
    assert not any("줄만" in str(item.value) for item in infos(app))
    app = _grid_write(app, calls, "Process-A", "202608", "20")

    app.session_state["capa_run_day_editor_filter_공정"] = ["Process-B"]
    app.run()
    assert not app.exception
    assert _visible_keys(calls) == ["Process-B"]
    notices = {str(item.value): item.proto.help for item in app.caption}
    assert notices[reference_grid.CAP_FILTERED_NOTICE.format(rows=2, cells=2, shown=1)] == (
        reference_grid.CAP_HELP
    )
    app = _grid_write(app, calls, "Process-B", "202608", "15")
    assert _draft(app) == {
        "cells": {"Process-A": {"202608": 20.0}, "Process-B": {"202608": 15.0}},
        "bad": {},
    }

    app.button(key=APPLY).click().run()
    assert not app.exception
    saved = app.session_state["test_month_updates"]["RQ_RUN_DAY"]
    assert dict(zip(saved["공정"], saved["RUN_DAY"], strict=True)) == {
        "Process-A": 20.0,
        "Process-B": 15.0,
    }


def test_a_capped_table_counts_the_errors_of_rows_it_does_not_load(
    calls: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reference_grid, "CAP_CELLS", 1)
    monkeypatch.setattr(reference_grid, "CAP_ROWS", 1)
    app = _open(TWO_PROCESS_TEST_SCRIPT)
    app = _grid_write(app, calls, "Process-A", "202608", "30.5")
    app.session_state["capa_run_day_editor_filter_공정"] = ["Process-B"]
    app.run()
    app.button(key=APPLY).click().run()
    assert not app.exception
    errors = [str(item.value) for item in app.error]
    place = f"{literal_markdown('Process-A')} · 202608"
    assert errors == [reference_grid.ERRORS_NOTICE.format(n="1", places=place)]


def test_the_paste_template_is_the_whole_table_while_the_filter_narrows_the_grid(
    calls: Calls,
) -> None:
    """「Excel 붙여넣기」 양식은 필터 이전의 전체 표다(부분 표가 되면 행 집합 검증을 통과해 나머지
    공정을 그 기간에서 지운다) — 그리드는 필터로 한 줄만 보여도 양식은 두 줄이다."""
    for name, editor_key in (
        ("효율", "capa_run_rate_editor"),
        ("설비대수 가용", "capa_eqp_avbl_editor"),
    ):
        app = _filtered_editor_app(name, editor_key, "공정")
        assert [key.split("\x1f")[0] for key in _visible_keys(calls)] == ["Process-B"]
        app = _open_paste(app, editor_key)
        exported = _download_frame(app, f"{editor_key}_csv_download")
        assert exported["공정"].tolist() == ["Process-A", "Process-B"], name


def test_the_first_edit_shows_in_the_sidebar_of_the_run_it_arrives_in(calls: Calls) -> None:
    """사이드바 「적용 전 편집」 은 페이지 본문보다 먼저 그린다. 첫 편집(초안 없던 표)의 op 가
    온 회차에 그 표가 바로 서야 한다 — 그리드는 첫 편집 뒤 다시 보내지 않아, 한 회차 늦으면 다음
    조작까지 사이드바·화면 탭 점이 편집을 모른다. 출납 콜백이 빈 초안 자리를 두고 본문이 진짜
    초안으로 덮는다(빈 자리는 「변경사항 적용」·단추 점에 들지 않는다)."""
    probe = "test_pre_page_labels"
    script = TWO_PROCESS_TEST_SCRIPT.replace(
        '    PAGE_NAME = "reference_data.py"\n',
        "    from capa_simulation.components.scenario_edit_bar import pending_edit_labels\n"
        f"    st.session_state.setdefault({probe!r}, []).append(\n"
        "        (pending_edit_labels('reference_data.py'),"
        " st.session_state.get('reference_grid_cells__RQ_RUN_RATE'))\n"
        "    )\n"
        '    PAGE_NAME = "reference_data.py"\n',
        1,
    )
    assert script != TWO_PROCESS_TEST_SCRIPT
    app = _open(script, "효율")
    # 대역은 콜백을 그리는 자리에서 부른다 — 진짜는 회차 맨 앞이다. 콜백이 돈 회차 다음 회차의
    # 페이지 앞 탐침이 진짜 회차의 사이드바 자리다.
    app.session_state[FAKE_EVENT_KEY] = (
        GRID_HOST,
        outbox(
            calls,
            {"op": "write", "rows": ["Process-A\x1f양산"], "cols": ["202608"], "values": [["0.5"]]},
            host=GRID_HOST,
        ),
    )
    app.run()
    assert not app.exception
    assert app.session_state[cells_key("RQ_RUN_RATE")] == {"cells": {}, "bad": {}}
    app.run()
    assert not app.exception
    labels, slot = app.session_state[probe][-1]
    assert labels == ["기준 정보 · 효율"]
    assert slot == {"cells": {}, "bad": {}}
    # 본문이 진짜 초안으로 덮었다.
    assert app.session_state[cells_key("RQ_RUN_RATE")] == {
        "cells": {"Process-A\x1f양산": {"202608": 0.5}},
        "bad": {},
    }


# 페이지 앞에서 `app.py` 가 그리는 표지(사이드바 「적용 전 편집」·화면 탭 점)를 회차마다 적는 대본 —
# 대역을 `early=True` 로 깔면 콜백이 진짜처럼 회차 맨 앞에서 돌아, 이 탐침이 진짜 회차의 사이드바
# 자리다.
PRE_PAGE_PROBE = "test_pre_page_marks"
PRE_PAGE_PROBE_SCRIPT = TWO_PROCESS_TEST_SCRIPT.replace(
    '    PAGE_NAME = "reference_data.py"\n',
    "    from capa_simulation.components.page_tabs import page_unsaved_marks\n"
    "    from capa_simulation.components.scenario_edit_bar import pending_edit_labels\n"
    f"    st.session_state.setdefault({PRE_PAGE_PROBE!r}, []).append(\n"
    "        (pending_edit_labels('reference_data.py'), page_unsaved_marks('reference_data.py'))\n"
    "    )\n"
    '    PAGE_NAME = "reference_data.py"\n',
    1,
)
assert PRE_PAGE_PROBE_SCRIPT != TWO_PROCESS_TEST_SCRIPT
REFERENCE_TAB = "app_pages/reference_data.py"


@pytest.fixture
def early_calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    """출납 콜백을 진짜처럼 회차 맨 앞에서 부르는 대역(`edit_grid_fake` 의 `early`)."""
    return install_fake_edit_grid(monkeypatch, early=True)


def _probes(app: AppTest) -> list[tuple[list[str], dict[str, str]]]:
    return list(app.session_state[PRE_PAGE_PROBE])


def test_undo_back_to_no_edit_drops_the_sidebar_and_tab_marks_in_that_run(
    early_calls: Calls,
) -> None:
    """Ctrl+Z 로 마지막 편집을 되돌려 초안이 0칸이 되면 그 회차에 사이드바 「적용 전 편집」·화면 탭
    점이 사라진다. `app.py` 는 그 표지를 페이지(반영)보다 **먼저** 그리므로, 반영이 초안을 비운
    회차는 한 번 다시 돈다 — 전에는 다음 조작까지 표지가 남았다(2026-11-03 마지막 검토 C1). 다시
    도는 것은 한 번뿐이고 보통 편집 회차는 다시 돌지 않는다."""
    app = _open(PRE_PAGE_PROBE_SCRIPT, "효율")
    before = len(_probes(app))
    app = deliver_ops(
        app,
        early_calls,
        {"op": "write", "rows": ["Process-A\x1f양산"], "cols": ["202608"], "values": [["0.5"]]},
        host=GRID_HOST,
    )
    # 첫 편집은 그 회차 사이드바에 선다(출납 콜백의 빈 초안 자리) — 다시 돌지 않는다.
    assert len(_probes(app)) == before + 1
    labels, marks = _probes(app)[-1]
    assert labels == ["기준 정보 · 효율"]
    assert REFERENCE_TAB in marks
    assert change_counts(draft_from(app.session_state[cells_key("RQ_RUN_RATE")]))[0] == 1

    before = len(_probes(app))
    app = deliver_ops(app, early_calls, {"op": "undo"}, host=GRID_HOST)
    assert app.session_state[cells_key("RQ_RUN_RATE")] is None
    probes = _probes(app)
    assert len(probes) == before + 2
    # 반영 전에 그린 표지(옛 초안)는 같은 회차의 다시 돌기가 걷는다.
    assert probes[-2][0] == ["기준 정보 · 효율"]
    labels, marks = probes[-1]
    assert labels == []
    assert REFERENCE_TAB not in marks
    # 다음 회차는 그대로다(다시 돌기가 되풀이되지 않는다).
    before = len(_probes(app))
    app.run()
    assert not app.exception
    assert len(_probes(app)) == before + 1
    assert _probes(app)[-1][0] == []


def test_a_first_op_that_changes_nothing_leaves_no_sidebar_mark(early_calls: Calls) -> None:
    """초안이 없던 표의 첫 op 가 아무것도 바꾸지 않으면(빈칸에 Delete · 양식과 같은 값) 그 회차에
    사이드바 「적용 전 편집」·화면 탭 점이 서지 않는다 — 출납 콜백이 둔 빈 초안 자리를 반영이 None
    으로 걷고 한 번 다시 돈다(2026-11-03 마지막 검토 C1)."""
    app = _open(PRE_PAGE_PROBE_SCRIPT, "효율")
    for value in ("0.9", "90%"):
        app = deliver_ops(
            app,
            early_calls,
            {"op": "write", "rows": ["Process-A\x1f양산"], "cols": ["202608"], "values": [[value]]},
            host=GRID_HOST,
        )
        assert app.session_state[cells_key("RQ_RUN_RATE")] is None
        labels, marks = _probes(app)[-1]
        assert labels == [], value
        assert REFERENCE_TAB not in marks, value


def test_an_empty_draft_slot_counts_as_no_edit() -> None:
    """빈 초안 자리는 초안이 아니다 — 「변경사항 적용」 을 켜지 않고 변경 수도 0 이다."""
    assert draft_from({"cells": {}, "bad": {}}) is None
    assert change_counts(draft_from({"cells": {}, "bad": {}})) == (0, 0, 0)


# 다른 화면의 적용을 흉내 내는 대본 — 활성 리비전·내용 토큰은 세션 값(`probe_revision`·
# `probe_token`)이고, `probe_run_day` 를 주면 그 적용이 일수 표 내용도 바꾼 것이다(생산 계획 화면의
# 적용은 리비전과 내용 토큰만 바꾸고 기준 정보 표는 그대로다).
OTHER_PAGE_APPLY_SCRIPT = (
    TWO_PROCESS_TEST_SCRIPT.replace(
        '    "revision": 1,\n', '    "revision": st.session_state.get("probe_revision", 1),\n', 1
    )
    .replace(
        '    "content_token": "test-capacity-two-process-page",\n',
        '    "content_token": st.session_state.get(\n'
        '        "probe_token", "test-capacity-two-process-page"\n'
        "    ),\n",
        1,
    )
    .replace(
        "\nactive = {\n",
        "\nif st.session_state.get('probe_run_day') is not None:\n"
        "    tables['RQ_RUN_DAY'] = tables['RQ_RUN_DAY'].assign("
        "RUN_DAY=st.session_state['probe_run_day'])\n"
        "\nactive = {\n",
        1,
    )
)
RUN_RATE_CELLS = cells_key("RQ_RUN_RATE")


def _cells(app: AppTest, key: str) -> int:
    value = app.session_state[key] if key in app.session_state else None
    return change_counts(draft_from(value))[0]


def _other_page_apply(app: AppTest, *, run_day: float | None = None) -> AppTest:
    """다른 화면이 적용한 회차 — 활성 리비전이 오르고 새 내용 토큰이 선다(내용마다 다른 토큰 —
    캐시는 프로세스 전역이다)."""
    app.session_state["probe_revision"] = 2
    app.session_state["probe_token"] = f"test-capacity-other-page-apply-{run_day}"
    if run_day is not None:
        app.session_state["probe_run_day"] = run_day
    app.run()
    assert not app.exception, app.exception
    return app


def _drafts_in_two_tables(calls: Calls) -> AppTest:
    assert OTHER_PAGE_APPLY_SCRIPT.count("probe_") == 4, "대본 바꾸기 셋이 모두 걸렸다"
    app = _open(OTHER_PAGE_APPLY_SCRIPT)
    app = _grid_write(app, calls, "Process-A", "202608", "20")
    app = _choose(app, "효율")
    app = send_ops(
        app,
        calls,
        {"op": "write", "rows": ["Process-B\x1f양산"], "cols": ["202608"], "values": [["50%"]]},
        host=GRID_HOST,
    )
    assert not app.exception
    assert _cells(app, RUN_DAY_CELLS) == 1 and _cells(app, RUN_RATE_CELLS) == 1
    return _choose(app, "일수")


def test_another_pages_apply_keeps_the_drafts_of_the_tables_it_did_not_touch(
    calls: Calls,
) -> None:
    """생산 계획(PKG PLAN·수율)처럼 다른 화면의 적용은 리비전만 올린다 — 내용이 그대로인 표의
    초안·이력은 남고(업무 키라 같은 칸에 붙는다) 버렸다는 알림도 없다. 전에는 어느 화면의 적용이든
    아홉 표 초안을 말없이 모두 버렸다(2026-11-03 리뷰 — Guide 「다른 화면에 다녀와도 그대로」 와
    어긋남)."""
    app = _drafts_in_two_tables(calls)
    old_gen = last(calls, FEED)["gen"]

    app = _other_page_apply(app)
    assert _draft(app) == {"cells": {"Process-A": {"202608": 20.0}}, "bad": {}}
    assert _cells(app, RUN_RATE_CELLS) == 1
    assert not [item for item in app.warning if "버렸습니다" in str(item.value)]
    # 이력(gen)도 남아 그 전에 보낸 op 가 그대로 붙는다.
    assert last(calls, FEED)["gen"] == old_gen
    app = send_ops(
        app,
        calls,
        {"op": "write", "rows": ["Process-B"], "cols": ["202608"], "values": [["25"]]},
        host=GRID_HOST,
        gen=old_gen,
    )
    assert _draft(app) == {
        "cells": {"Process-A": {"202608": 20.0}, "Process-B": {"202608": 25.0}},
        "bad": {},
    }
    toast = last(calls, FEED)["toast"]
    assert toast is None or DROPPED_TOAST.format(n="1") not in toast["text"]


def test_another_pages_apply_that_changed_a_table_drops_only_its_draft_and_says_so(
    calls: Calls,
) -> None:
    """다른 화면의 적용이 일수 표 내용도 바꿨다 — 그 표 초안만 버리고(옛 양식에 붙은 값이다) 작업
    줄에 한 번 알린다. 효율 초안은 남는다."""
    app = _drafts_in_two_tables(calls)

    app = _other_page_apply(app, run_day=25.0)
    assert _draft(app) is None
    assert _cells(app, RUN_RATE_CELLS) == 1
    warnings = [str(item.value) for item in app.warning]
    assert any(
        "다른 화면의 적용으로 표 내용이 바뀌어 적용하지 않은 편집(일수 1칸)을 버렸습니다" in text
        for text in warnings
    ), warnings
    app.run()
    assert not any("다른 화면의 적용으로" in str(item.value) for item in app.warning)


def test_the_dropped_notice_survives_the_rerun_of_a_run_that_emptied_a_draft(
    early_calls: Calls,
) -> None:
    """다른 화면의 적용이 일수 표를 바꾼 회차에 효율 초안을 비우는 op(Ctrl+Z)도 함께 왔다 — 반영이
    초안을 비워 그 회차가 다시 돌아도(C1) 일수 초안을 버렸다는 알림은 다시 돈 회차에 선다. 그다음
    회차에는 없다."""
    app = _drafts_in_two_tables(early_calls)
    gen = app.session_state[history_key("RQ_RUN_RATE")]["gen"]
    app.session_state["probe_revision"] = 2
    app.session_state["probe_token"] = "test-capacity-other-page-apply-carry"
    app.session_state["probe_run_day"] = 26.0
    app = deliver_ops(
        app, early_calls, {"op": "undo"}, host=GRID_HOST, table="RQ_RUN_RATE", gen=gen
    )
    assert _draft(app) is None
    assert _cells(app, RUN_RATE_CELLS) == 0
    warnings = [str(item.value) for item in app.warning]
    assert any(
        "다른 화면의 적용으로 표 내용이 바뀌어 적용하지 않은 편집(일수 1칸)을 버렸습니다" in text
        for text in warnings
    ), warnings
    app.run()
    assert not app.exception
    assert not any("다른 화면의 적용으로" in str(item.value) for item in app.warning)


def test_discarding_right_after_an_edit_drops_the_batched_op_without_a_retry_toast(
    calls: Calls,
) -> None:
    """고친 직후(300ms 출납 묶음 안) 「편집 취소」 — 누름의 focusout 이 보낸 op 는 일부러 버린
    편집이다. 초안은 비고(사이드바 「적용 전 편집」 도 서지 않는다) 「표가 바뀌기 전에 보낸 편집 …
    다시 고쳐 주세요」 토스트는 서지 않는다(2026-11-03 리뷰)."""
    app = _open(TWO_PROCESS_TEST_SCRIPT)
    app = _grid_write(app, calls, "Process-A", "202608", "20")
    batched = outbox(
        calls,
        {"op": "write", "rows": ["Process-B"], "cols": ["202608"], "values": [["23"]]},
        host=GRID_HOST,
    )
    app.button(key="capa_run_day_editor_discard").click()
    app.session_state[FAKE_EVENT_KEY] = (GRID_HOST, batched)
    app.run()
    assert not app.exception
    app.run()
    assert not app.exception
    assert _draft(app) is None
    toast = last(calls, FEED)["toast"]
    assert toast is None or "다시 고쳐" not in toast["text"], toast
    sidebar = " ".join(str(item.value) for item in app.sidebar.markdown)
    assert "기준 정보 · 일수" not in sidebar


def test_the_error_notice_escapes_the_names_it_puts_in_markdown(calls: Calls) -> None:
    """「고칠 칸」 알림은 마크다운(`st.error`)이다 — 공정 표시명 「E2E~가정~A」 가 지움선이 되지
    않게 칸마다 `literal_markdown` 으로 막는다."""
    script = RENAMED_TWO_PROCESS_TEST_SCRIPT.replace(
        '[("Process-A", "가공")]', '[("Process-A", "E2E~가정~A")]', 1
    )
    assert script != RENAMED_TWO_PROCESS_TEST_SCRIPT
    app = _open(script)
    app = _grid_write(app, calls, "Process-A", "202608", "30.5")
    app.button(key=APPLY).click().run()
    assert not app.exception
    errors = [str(item.value) for item in app.error]
    assert errors == [
        reference_grid.ERRORS_NOTICE.format(
            n="1", places=f"{literal_markdown('E2E~가정~A')} · 202608"
        )
    ], errors


def test_the_paste_popup_refuses_a_fractional_day_like_the_grid() -> None:
    """일수는 정수만 받는다 — 그리드는 30.5 를 칸 오류로 막고, 「Excel 붙여넣기」 도 같은 규칙으로
    막는다(전에는 붙여넣기가 RUN_DAY 30.5 를 그대로 적용했다)."""
    app = _open(TWO_PROCESS_TEST_SCRIPT)
    app = _paste(app, "capa_run_day_editor", "공정\t202608\nProcess-A\t30.5\nProcess-B\t31\n")
    errors = [str(item.value) for item in flashed(app, "error")]
    assert any("0 이상 정수" in text and "'30.5'" in text for text in errors), errors
    assert "test_month_updates" not in app.session_state
    app = _paste(app, "capa_run_day_editor", "공정\t202608\nProcess-A\t30\nProcess-B\t31\n")
    assert app.session_state["test_month_updates"]["RQ_RUN_DAY"]["RUN_DAY"].tolist() == [
        30.0,
        31.0,
    ]


def test_the_edited_dataset_button_gets_its_dot_drawn_on_the_page(calls: Calls) -> None:
    """종류 단추 점은 페이지가 그리는 `<style>` 이다 — 고친 표(일수 = 8번째 단추)에 점 규칙이 서고,
    고치기 전에는 없다(단위 시험은 CSS 만, 페이지 시험은 넘긴 집합만 보던 틈 — 2026-11-03 리뷰)."""
    selector = '[role="radio"]:nth-of-type(8)::after'
    app = _open(TWO_PROCESS_TEST_SCRIPT)
    assert not any(selector in element.proto.body for element in app.get("html"))
    app = _grid_write(app, calls, "Process-A", "202608", "20")
    bodies = [element.proto.body for element in app.get("html") if selector in element.proto.body]
    assert bodies == [pending_segments_style(DATASET_KEY, list(DATASETS), {"RQ_RUN_DAY"}).strip()]


def test_a_table_over_the_byte_cap_never_caches_or_unpacks_its_whole_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """껍데기 본문이 `CAP_BYTES` 를 넘는 표는 앞 줄만 싣는다(알림은 그대로). 그 표의 **전체**
    본문은 캐시에서 나오지 않는다 — 전에는 크기만 보려고 전체 본문을 캐시에 담고 회차마다 통째로
    풀었다(수 MB — 다른 캐시 칸을 밀어냈다)(2026-11-03 마지막 검토 C6). 넘지 않는 표는 지금처럼
    전체를 싣는다."""
    import uuid

    import pandas as pd

    from capa_simulation.services import simulation_cache
    from capa_simulation.services.edit_grid_payload import EditGridBase

    template = pd.DataFrame({"공정": [f"DEMO_P{row:03d}" for row in range(60)]})
    for month in ("202701", "202702", "202703"):
        template[month] = [float(row) / 7 for row in range(60)]
    served: list[object] = []

    def _spy(function: Any) -> Any:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            result = function(*args, **kwargs)
            served.append(result)
            return result

        return wrapped

    for name in ("get_edit_grid_base", "get_edit_grid_base_within"):
        monkeypatch.setattr(reference_grid, name, _spy(getattr(simulation_cache, name)))
    monkeypatch.setattr(reference_grid, "CAP_ROWS", 5)

    def _build(cap_bytes: int) -> reference_grid.GridTable:
        monkeypatch.setattr(reference_grid, "CAP_BYTES", cap_bytes)
        return reference_grid.build_grid_table(
            "RQ_RUN_DAY",
            "일수",
            "capa_run_day_editor",
            template,
            ("공정",),
            cache_key=(1, f"test-byte-cap-{uuid.uuid4().hex}", 202701, 202703),
            order_digest="order",
            value_labels=None,
        )

    for _ in range(2):
        capped = _build(10)
        assert capped.cap_notice == reference_grid.CAP_HEAD_NOTICE.format(
            rows=60, cells=180, shown=5
        )
        assert len(capped.base.index.keys) == 5
    whole = [
        base for base in served if isinstance(base, EditGridBase) and len(base.index.keys) == 60
    ]
    assert whole == []

    served.clear()
    roomy = _build(10_000_000)
    assert roomy.cap_notice is None and len(roomy.base.index.keys) == 60
