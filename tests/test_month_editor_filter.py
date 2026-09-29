# Purpose: 편집기 탭의 공정 필터가 보기만 좁히고 저장은 전체를 유지하는지 검증한다.

"""필터는 보기만 좁히고 저장은 전체다.

`components/month_editor.py` 가 돌려주는 표는 언제나 원본 전체여야 한다. 걸러진 표를 그대로
돌려주면 `scenario_state.replace_month_range` 가 조회기간의 행을 편집값으로 갈아끼우면서
화면에서 걸러진 공정을 그 기간에서 지운다.
"""

from io import BytesIO

import pandas as pd
from streamlit.testing.v1 import AppTest

from capa_simulation.components.month_editor import (
    FILTER_LOCKED_NOTICE,
    PASTE_DROPS_EDITS_NOTICE,
    merge_edited_months,
)
from capa_simulation.components.page_guide import load_guide

RUN_DAY_TABLE = pd.DataFrame(
    {
        "공정": ["Process-A", "Process-B", "Process-C"],
        "202608": [31.0, 30.0, 29.0],
        "202609": [28.0, 27.0, 26.0],
    }
)

RATIO_TABLE = pd.DataFrame(
    {
        "공정": ["Process-A", "Process-A", "Process-B"],
        "Area_Name": ["Main", "MI", "Main"],
        "양산구분": ["양산", "양산", "개발"],
        "202608": [1.0, 2.0, 3.0],
    }
)

EDITOR_SCRIPT = r"""
import pandas as pd
import streamlit as st

import capa_simulation.components.month_editor as month_editor
from capa_simulation.components.process_labels import process_labels_from_rules
from capa_simulation.components.tab_state import stateful_tabs

TABLE_NAME = "RUN_DAY"
if TABLE_NAME == "RUN_DAY":
    table = pd.DataFrame(
        {
            "공정": ["Process-A", "Process-B", "Process-C"],
            "202608": [31.0, 30.0, 29.0],
            "202609": [28.0, 27.0, 26.0],
        }
    )
    dimensions = ["공정"]
else:
    table = pd.DataFrame(
        {
            "공정": ["Process-A", "Process-A", "Process-B"],
            "Area_Name": ["Main", "MI", "Main"],
            "양산구분": ["양산", "양산", "개발"],
            "202608": [1.0, 2.0, 3.0],
        }
    )
    dimensions = ["공정", "Area_Name", "양산구분"]

# 표시명은 페이지가 조회해 넘긴다. 이 컴포넌트는 받은 매핑을 필터 표기에만 쓴다.
labels = process_labels_from_rules(
    pd.DataFrame([("Process-A", "가공")], columns=["공정", "표시명"]), 1
)
original_download_button = st.download_button


def record_download_button(label, *args, **kwargs):
    # `data` 는 위젯 proto 에 실리지 않아 AppTest 로는 볼 수 없다. 버튼은 실제로 그리고
    # 내보내는 바이트만 세션 상태에 적어 둔다.
    captured = st.session_state.setdefault("captured_download_data", {})
    captured[kwargs.get("key")] = kwargs.get("data")
    return original_download_button(label, *args, **kwargs)


def record_paste(imported):
    # 붙여넣기는 팝업 안에서 끝난다. 페이지가 줄 적용 함수 대신 받은 표를 적어 둔다.
    st.session_state["returned_imported"] = imported


tabs = stateful_tabs(["편집"], key="editor_test_tab")
try:
    # streamlit 모듈 자체를 바꾸는 패치라 원복이 반드시 돌아야 한다.
    st.download_button = record_download_button
    edited, submitted = month_editor.render_month_editor(
        tabs[0],
        table,
        dimensions,
        "demo_editor",
        "%,.0f",
        1.0,
        table_name="RQ_DEMO",
        csv_file_name="demo.csv",
        dialog_key="demo_open_dialog",
        on_paste=record_paste,
        card_name="demo",
        value_labels=labels.value_labels(),
    )
finally:
    st.download_button = original_download_button

st.session_state["returned_table"] = edited
st.session_state["returned_submitted"] = submitted
"""


def editor_widget_key_in(app: AppTest, key: str) -> str:
    """앱이 지금 편집표를 그리는 위젯 키(`editor_state.editor_widget_key` 와 같은 규칙).

    필터가 바뀌거나 편집을 버리면 편집표가 새 세대 키로 선다. 브라우저는 그 키로 편집을
    보내므로 테스트도 같은 키에 넣는다.
    """
    generation_key = f"{key}__generation"
    generation = app.session_state[generation_key] if generation_key in app.session_state else 0
    return key if not generation else f"{key}__g{generation}"


RATIO_SCRIPT = EDITOR_SCRIPT.replace('TABLE_NAME = "RUN_DAY"', 'TABLE_NAME = "RATIO"')
# 탭이 둘인 화면. 닫힌 탭의 편집표가 편집을 지키는지 본다.
TWO_TAB_SCRIPT = EDITOR_SCRIPT.replace(
    'tabs = stateful_tabs(["편집"], key="editor_test_tab")',
    'tabs = stateful_tabs(["편집", "다른"], key="editor_test_tab")',
)

EDITOR_KEY = "demo_editor"


def _edit(app: AppTest, row: int, column: str, value: float) -> None:
    """data_editor 의 편집 델타를 사용자가 셀을 고친 것과 같은 모양으로 넣는다.

    편집 델타는 **보이는 표 안의 행 위치**로 기록된다 — 필터가 걸리면 걸러진 표의 위치다.
    """
    app.session_state[editor_widget_key_in(app, EDITOR_KEY)] = {
        "edited_rows": {row: {column: value}},
        "added_rows": [],
        "deleted_rows": [],
    }


def test_merge_edited_months_keeps_the_rows_the_filter_hid() -> None:
    """걸러진 행은 원본 값 그대로 남고, 행 수와 순서도 원본과 같다."""
    visible = RUN_DAY_TABLE.loc[RUN_DAY_TABLE["공정"].eq("Process-B")].copy()
    visible["202608"] = 15.0

    merged = merge_edited_months(RUN_DAY_TABLE, visible, ["공정"], ["202608", "202609"])

    assert merged["공정"].tolist() == ["Process-A", "Process-B", "Process-C"]
    assert merged["202608"].tolist() == [31.0, 15.0, 29.0]
    assert merged["202609"].tolist() == [28.0, 27.0, 26.0]
    assert len(merged) == len(RUN_DAY_TABLE)


def test_merge_edited_months_returns_the_editor_frame_when_nothing_is_filtered() -> None:
    """필터가 걸리지 않으면 편집표가 곧 전체 표다. 되머지 전 동작과 같아야 한다."""
    visible = RUN_DAY_TABLE.copy()
    visible.loc[0, "202608"] = 99.0

    merged = merge_edited_months(RUN_DAY_TABLE, visible, ["공정"], ["202608", "202609"])

    pd.testing.assert_frame_equal(merged, visible)


def test_merge_edited_months_matches_by_every_tab_dimension() -> None:
    """공정만으로는 행이 갈리지 않는 탭이 있다. 되머지 키는 그 탭의 분류 컬럼 전부다."""
    dimensions = ["공정", "Area_Name", "양산구분"]
    visible = RATIO_TABLE.loc[RATIO_TABLE["Area_Name"].eq("MI")].copy()
    visible["202608"] = 9.0

    merged = merge_edited_months(RATIO_TABLE, visible, dimensions, ["202608"])

    assert merged["202608"].tolist() == [1.0, 9.0, 3.0]
    assert merged[dimensions].equals(RATIO_TABLE[dimensions])


def test_filtered_editor_returns_the_whole_table_with_only_the_edited_row_changed() -> None:
    """필터를 걸고 고쳐도 돌려주는 표는 전체다 — 저장이 그 표를 통째로 쓰기 때문이다."""
    app = AppTest.from_string(EDITOR_SCRIPT, default_timeout=60).run()
    assert not app.exception

    app.session_state[f"{EDITOR_KEY}_filter_공정"] = ["Process-B"]
    app.run()
    assert not app.exception
    # 필터를 건 직후의 화면은 한 행이다. 편집 델타는 그 위치로 들어온다.
    _edit(app, 0, "202608", 15.0)
    app.run()

    assert not app.exception
    returned = app.session_state["returned_table"]
    assert returned["공정"].tolist() == ["Process-A", "Process-B", "Process-C"]
    assert returned["202608"].tolist() == [31.0, 15.0, 29.0]
    assert returned["202609"].tolist() == [28.0, 27.0, 26.0]


def test_filtered_editor_of_a_multi_key_tab_keeps_the_other_rows() -> None:
    """분류 컬럼이 여러 개인 탭도 같다. 필터로 감춘 행이 값을 잃지 않는다."""
    app = AppTest.from_string(RATIO_SCRIPT, default_timeout=60).run()
    assert not app.exception

    app.session_state[f"{EDITOR_KEY}_filter_Area_Name"] = ["MI"]
    app.run()
    assert not app.exception
    _edit(app, 0, "202608", 9.0)
    app.run()

    assert not app.exception
    returned = app.session_state["returned_table"]
    assert returned["Area_Name"].tolist() == ["Main", "MI", "Main"]
    assert returned["202608"].tolist() == [1.0, 9.0, 3.0]


def test_unfiltered_editor_keeps_the_previous_round_trip() -> None:
    """필터를 만지지 않으면 예전과 같은 표가 그대로 돌아온다."""
    app = AppTest.from_string(EDITOR_SCRIPT, default_timeout=60).run()
    assert not app.exception

    _edit(app, 2, "202609", 5.0)
    app.run()

    assert not app.exception
    returned = app.session_state["returned_table"]
    assert returned["공정"].tolist() == ["Process-A", "Process-B", "Process-C"]
    assert returned["202609"].tolist() == [28.0, 27.0, 5.0]


def test_changing_the_filter_drops_the_edit_that_was_not_applied() -> None:
    """편집 델타는 행 위치라 보이는 행이 바뀌면 다른 행에 붙는다. 그래서 버린다.

    화면에서는 편집이 남은 동안 필터가 잠겨 이 길로 들어설 수 없다(아래 테스트). 그래도 세션
    값이 바뀌는 길(프리셋 복원 등)이 남아 있어, 엉뚱한 행에 붙이는 대신 버리는 안전망을 지킨다.
    """
    app = AppTest.from_string(EDITOR_SCRIPT, default_timeout=60).run()
    app.session_state[f"{EDITOR_KEY}_filter_공정"] = ["Process-B"]
    app.run()
    _edit(app, 0, "202608", 15.0)
    app.run()

    app.session_state[f"{EDITOR_KEY}_filter_공정"] = ["Process-C"]
    app.run()

    assert not app.exception
    returned = app.session_state["returned_table"]
    assert returned["202608"].tolist() == [31.0, 30.0, 29.0]


TEMPLATE_DOWNLOAD_KEY = f"{EDITOR_KEY}_csv_download"


def _template_bytes(app: AppTest) -> bytes:
    """붙여넣기 팝업이 실제로 내보낸 양식 CSV 바이트."""
    captured = app.session_state["captured_download_data"]
    assert TEMPLATE_DOWNLOAD_KEY in captured, f"양식 버튼이 없습니다: {sorted(captured)}"
    return bytes(captured[TEMPLATE_DOWNLOAD_KEY])


def _filtered_to_one_process(app: AppTest) -> AppTest:
    app.session_state[f"{EDITOR_KEY}_filter_공정"] = ["Process-B"]
    app.run()
    assert not app.exception
    # 화면 표가 실제로 좁아져 있어야 CSV 가 전체라는 것이 뜻을 가진다.
    assert app.dataframe[0].value["공정"].tolist() == ["Process-B"]
    # 양식과 붙여넣기는 작업 줄의 「Excel 붙여넣기」 팝업 안이다.
    app.button(key=f"{EDITOR_KEY}_open_paste").click().run()
    assert not app.exception
    return app


def test_the_csv_template_covers_every_process_while_the_filter_narrows_the_screen() -> None:
    """양식 CSV 가 부분 표가 되면 행 집합 검증을 그대로 통과해 나머지 공정을 지운다.

    붙여넣기 팝업에 넘기는 표는 반드시 필터 이전의 전체 표다.
    되머지와 같은 등급의 데이터 손실 경로라 바이트를 직접 디코드해 고정한다.
    """
    app = AppTest.from_string(EDITOR_SCRIPT, default_timeout=60).run()
    assert not app.exception
    app = _filtered_to_one_process(app)

    template = pd.read_csv(
        BytesIO(_template_bytes(app)),
        encoding="utf-8-sig",
        dtype="object",
    )

    assert template["공정"].tolist() == ["Process-A", "Process-B", "Process-C"]
    assert list(template.columns) == ["공정", "202608", "202609"]


def test_the_pasted_template_still_applies_to_every_process_while_filtered() -> None:
    """내려받은 양식을 그대로 되붙이는 왕복도 전체 표여야 한다."""
    app = AppTest.from_string(EDITOR_SCRIPT, default_timeout=60).run()
    assert not app.exception
    app = _filtered_to_one_process(app)

    # Excel 클립보드는 탭 구분이다. 이 표본에는 쉼표가 든 값이 없어 그대로 바꿔도 된다.
    pasted = _template_bytes(app).decode("utf-8-sig").replace(",", "\t")
    app.text_area(key=f"{EDITOR_KEY}_csv_clipboard").set_value(pasted)
    app.run()
    assert not app.exception
    submit = next(button for button in app.button if button.label == "붙여넣기 일괄 적용")
    app = submit.click().run()

    assert not app.exception
    imported = app.session_state["returned_imported"]
    assert imported is not None
    assert imported["공정"].tolist() == ["Process-A", "Process-B", "Process-C"]


def test_the_filters_live_in_the_sidebar_card_and_the_scope_says_they_narrow() -> None:
    """필터는 사이드바 조건 카드다. 접혀 있으면 본문만 보고는 행이 빠진 까닭을 모르므로,
    편집 범위 줄이 필터로 줄어든 행 수를 말한다. 필터가 보기만 좁힌다는 뜻은 Guide 가 말한다."""
    app = AppTest.from_string(EDITOR_SCRIPT, default_timeout=60).run()
    assert not app.exception
    assert f"{EDITOR_KEY}_filter_공정" in {widget.key for widget in app.sidebar.multiselect}
    assert f"{EDITOR_KEY}_filter_공정" not in {widget.key for widget in app.main.multiselect}

    app = _filtered_to_one_process(app)
    scope = next(item.value for item in app.markdown if item.value.startswith("**편집 범위**"))
    assert "필터로 1개 행 표시" in scope and "전체 3개 행" in scope
    guide = load_guide("reference_data")
    assert "필터는 화면만 좁힙니다" in guide and "표 **전체**" in guide


def test_a_pending_edit_locks_the_filters_and_can_be_discarded() -> None:
    """고친 것이 남은 동안 필터를 바꾸면 편집을 버려야 한다 — 그래서 잠그고 까닭을 적는다."""
    app = AppTest.from_string(EDITOR_SCRIPT, default_timeout=60).run()
    _edit(app, 0, "202608", 15.0)
    app.run()

    assert not app.exception
    assert app.multiselect(key=f"{EDITOR_KEY}_filter_공정").disabled
    assert FILTER_LOCKED_NOTICE in {caption.value for caption in app.sidebar.caption}

    app.button(key=f"{EDITOR_KEY}_discard").click().run()
    assert not app.exception
    assert not app.multiselect(key=f"{EDITOR_KEY}_filter_공정").disabled
    assert app.session_state["returned_table"]["202608"].tolist() == [31.0, 30.0, 29.0]


def test_an_edit_survives_switching_to_another_tab() -> None:
    """닫힌 탭의 편집표를 건너뛰면 편집 상태가 버려진다. 편집이 남은 표는 닫혀도 그린다.

    브라우저는 앞 회차에 있던 위젯의 상태를 다음 회차에 다시 보낸다. 그 회차에 위젯을 그리지
    않으면 Streamlit 이 상태를 버리고 브라우저도 그 위젯을 지운다 — 그래서 **닫힌 탭에서도
    편집표가 그려졌는가**가 편집이 살아남는가와 같다. AppTest 는 편집 상태를 스스로 다시 보내지
    않아 테스트가 브라우저처럼 넣어 준다.
    """
    app = AppTest.from_string(TWO_TAB_SCRIPT, default_timeout=60).run()
    _edit(app, 1, "202608", 15.0)
    app.run()

    app.session_state["editor_test_tab"] = "다른"
    _edit(app, 1, "202608", 15.0)
    app.run()
    assert not app.exception
    assert len(app.dataframe) == 1
    assert app.session_state["returned_table"]["202608"].tolist() == [31.0, 15.0, 29.0]
    # 닫힌 탭에서는 카드를 세우지 않는다 — 사이드바는 지금 보는 탭의 조건만이다.
    assert f"{EDITOR_KEY}_filter_공정" not in {widget.key for widget in app.sidebar.multiselect}


def test_a_closed_tab_without_edits_skips_its_editor() -> None:
    """고친 것이 없는 닫힌 탭은 예전처럼 건너뛴다 — 피벗·그리기 비용 때문이다."""
    app = AppTest.from_string(TWO_TAB_SCRIPT, default_timeout=60).run()
    app.session_state["editor_test_tab"] = "다른"
    app.run()
    assert not app.exception
    assert len(app.dataframe) == 0


def test_filter_options_show_display_names_but_keep_original_values() -> None:
    """표시명은 옵션 표기에만 닿는다. 걸러진 표와 되머지는 원본 공정명으로 돈다."""
    app = AppTest.from_string(EDITOR_SCRIPT, default_timeout=60).run()
    assert not app.exception
    process_filter = app.multiselect(key=f"{EDITOR_KEY}_filter_공정")
    assert process_filter.options == ["가공", "Process-B", "Process-C"]

    process_filter.select("가공")
    app.run()

    assert not app.exception
    assert app.session_state[f"{EDITOR_KEY}_filter_공정"] == ["Process-A"]
    assert app.session_state["returned_table"]["공정"].tolist() == [
        "Process-A",
        "Process-B",
        "Process-C",
    ]


def test_the_paste_popup_warns_before_it_drops_unapplied_edits() -> None:
    """붙여넣기를 적용하면 표의 편집이 비워진다. 고친 것이 남았으면 팝업이 먼저 말한다."""
    app = AppTest.from_string(EDITOR_SCRIPT, default_timeout=60).run()
    _edit(app, 0, "202608", 15.0)
    app.button(key=f"{EDITOR_KEY}_open_paste").click().run()

    assert not app.exception
    assert PASTE_DROPS_EDITS_NOTICE in {warning.value for warning in app.warning}


def test_discarding_moves_the_editor_to_a_new_widget_so_resent_edits_are_ignored() -> None:
    """「편집 취소」는 세션 칸만 지우지 않고 편집표를 새 위젯으로 세운다.

    세션만 지우면 브라우저가 옛 편집을 다음 회차에 다시 보내 취소한 편집이 되살아났다
    (2026-09-29 리뷰에서 브라우저로 재현). 옛 키로 편집이 다시 와도 새 편집표에는 붙지 않는다.
    """
    app = AppTest.from_string(EDITOR_SCRIPT, default_timeout=60).run()
    _edit(app, 0, "202608", 15.0)
    app.run()
    app.button(key=f"{EDITOR_KEY}_discard").click().run()
    assert not app.exception
    assert app.session_state[f"{EDITOR_KEY}__generation"] == 1

    # 브라우저가 옛 위젯 키로 편집을 다시 보낸 회차
    app.session_state[EDITOR_KEY] = {
        "edited_rows": {0: {"202608": 15.0}},
        "added_rows": [],
        "deleted_rows": [],
    }
    app.run()
    assert not app.exception
    assert app.session_state["returned_table"]["202608"].tolist() == [31.0, 30.0, 29.0]
