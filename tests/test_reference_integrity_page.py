# Purpose: Dynamic Capa 상위 화면의 공정 표시명·선택값·상세 상자 되돌림·닫힌 탭 건너뛰기를 검증한다.

import json
from typing import Any, NamedTuple

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from widget_browser import BrowserChoice

import capa_simulation.components.process_labels as process_labels_module
from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY
from capa_simulation.services.dynamic_capacity import build_dynamic_capacity_demo

TEST_SCRIPT = r"""
from pathlib import Path

import pandas as pd
import streamlit as st

import capa_simulation
import capa_simulation.components.process_labels as process_labels_module
from capa_simulation.services.dynamic_capacity import build_dynamic_capacity_demo

# 데모 공정명은 합성 표본이라 리터럴로 고정하지 않는다. 표본에서 첫 공정을 뽑아 규칙을
# 만든다 — 나머지 공정은 매핑 밖이라 원본 그대로 나와야 한다.
demo_processes = sorted(build_dynamic_capacity_demo()["공정"].astype(str).unique())
st.session_state["renamed_source"] = demo_processes[0]
st.session_state["untouched_source"] = demo_processes[1]

original_get_process_labels = process_labels_module.get_process_labels
APPLY_RENAME = False
# 프로필이 없는 경우도 빈 매핑을 주입해야 로컬 공용 프로필을 읽거나 DB를 초기화하지 않는다.
labels = process_labels_module.ProcessLabels()
if APPLY_RENAME:
    labels = process_labels_module.process_labels_from_rules(
        pd.DataFrame([(demo_processes[0], "표시공정")], columns=["공정", "표시명"]), 5
    )
process_labels_module.get_process_labels = lambda: labels

try:
    page = Path(capa_simulation.__file__).resolve().parents[2] / "app_pages"
    source = page / "reference_integrity.py"
    exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"))
finally:
    process_labels_module.get_process_labels = original_get_process_labels
"""

RENAMED_TEST_SCRIPT = TEST_SCRIPT.replace("APPLY_RENAME = False", "APPLY_RENAME = True")

PRIORITY_COLUMNS = {"순위", "공정", "Capa 실현률"}


def _priority_frame(app: AppTest) -> pd.DataFrame:
    for frame in app.dataframe:
        if PRIORITY_COLUMNS.issubset(set(getattr(frame.value, "columns", []))):
            return frame.value
    raise AssertionError("관리 우선순위 표가 없습니다.")


def test_the_priority_requirement_column_keeps_its_own_name() -> None:
    """칸 값은 CHIP · WF · PKG 라 단위(매 · Kea)가 아니다 — 머리를 「단위」 로 바꿔 달지 않는다."""
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()
    assert not app.exception, app.exception
    (frame,) = [
        item
        for item in app.dataframe
        if PRIORITY_COLUMNS.issubset(set(getattr(item.value, "columns", [])))
    ]
    assert "소요기준" in frame.value.columns
    assert "label" not in json.loads(frame.proto.columns)["소요기준"]


def test_priority_table_and_process_selector_show_the_display_name() -> None:
    app = AppTest.from_string(RENAMED_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    renamed_source = app.session_state["renamed_source"]
    untouched_source = app.session_state["untouched_source"]

    priority = _priority_frame(app)
    assert "표시공정" in set(priority["공정"])
    assert renamed_source not in set(priority["공정"])
    # 매핑 밖 공정은 원본 그대로다.
    assert untouched_source in set(priority["공정"])

    process_filter = app.selectbox(key="dynamic_capacity_process_filter")
    assert "표시공정" in process_filter.options
    assert renamed_source not in process_filter.options


def test_selecting_a_renamed_process_keeps_the_original_value() -> None:
    """표기만 표시명이다. 선택값이 표시명이면 아래 `eq` 가 원본 컬럼과 맞지 않는다."""
    app = AppTest.from_string(RENAMED_TEST_SCRIPT, default_timeout=60).run()
    renamed_source = app.session_state["renamed_source"]

    # 워터폴은 「공정 상세」 탭 안이고 숨은 탭에서는 그리지 않는다. 조회 조건 위젯은
    # 숨어 있어도 그려지므로 선택은 어느 탭에서든 걸린다.
    app.session_state["dynamic_capa_active_tab"] = "공정 상세"
    app.selectbox(key="dynamic_capacity_process_filter").set_value(renamed_source)
    app.run()

    assert not app.exception
    assert app.session_state["dynamic_capacity_process_filter"] == renamed_source
    # 손실 구조 그림이 무엇을 잇는지는 구획 제목 풍선이 고른 공정의 표시명으로 말한다.
    assert any(
        "표시공정 공정의 표준 Capa부터" in str(markdown.proto.help) for markdown in app.markdown
    )


def test_priority_table_stays_original_without_a_rename_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_profile_load(*args: object, **kwargs: object) -> None:
        raise AssertionError("화면 테스트는 로컬 공정 표시명 DB를 조회하면 안 됩니다.")

    monkeypatch.setattr(
        process_labels_module, "load_global_process_rename", unexpected_profile_load
    )
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert app.session_state["renamed_source"] in set(_priority_frame(app)["공정"])


def test_the_summary_keeps_its_explanations_in_tooltips() -> None:
    """요약 탭의 판정 기준 · 그림 읽는 법 · 손실 차례와 실행 관리로 가는 까닭은 늘 서는 캡션이
    아니라 칸 · 구획 제목 · 링크의 풍선이다(설계 규칙 UI-TXT-01 · UI-TXT-02 · UI-TXT-03). 결론
    경고는 값만 싣는다."""
    from capa_simulation.navigation import EXECUTION_MANAGEMENT

    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()
    assert not app.exception

    summary_tab = next(tab for tab in app.tabs if tab.label == "요약")
    tab_markdown: list[Any] = list(summary_tab.get("markdown"))
    tab_captions: list[Any] = list(summary_tab.get("caption"))
    captions = [str(caption.value) for caption in tab_captions]
    assert captions, "요약 탭에는 판정 기준 줄이 없어도 링크 · 카드 글이 선다"
    assert not any(text.endswith("니다.") for text in captions), captions
    helps = {
        str(markdown.value): str(markdown.proto.help)
        for markdown in tab_markdown
        if str(markdown.value).startswith("####")
    }
    assert "90% 이상 정상" in helps["#### :material/bar_chart: 공정별 Capa 실현 수준"]
    assert "제품 Mix" in helps["#### :material/priority_high: 관리 우선순위"]
    # 카드 다섯 가운데 워터폴에 서는 것은 셋이다 — 나머지 둘이 어디 있는지도 같은 풍선이 말한다.
    routes_help = helps["#### :material/alt_route: 손실을 파고드는 화면"]
    assert "효율 손실 · UPEH 손실 · 재공부족 미활용은 워터폴에서" in routes_help
    assert "수율 손실은 워터폴에 칸이 따로 없어 기타 Gap 에" in routes_help
    assert "설비 가용은 손실 이전의 전제" in routes_help
    needs_action = next(metric for metric in app.metric if metric.label == "개선 필요")
    assert "80% 미만" in str(needs_action.proto.help)
    warnings: list[Any] = list(summary_tab.get("warning"))
    (verdict,) = [str(item.value) for item in warnings]
    assert "깎아먹는지" not in verdict and verdict.endswith("개입니다.")
    # 실행 관리 링크는 단독 실행에서 글로 물러서고, 늘 서던 길 안내 캡션은 없다.
    page_captions = [str(caption.value) for caption in app.caption]
    assert f"사이드바에서 {EXECUTION_MANAGEMENT.title}" in page_captions
    assert not any("A/Item" in text for text in page_captions)


def test_the_pending_screen_says_what_it_will_do_in_the_title_tooltip() -> None:
    """샘플을 끄면 자리 글은 들어올 값뿐이다 — 연결되면 하는 일은 「표준 대비 실적 Capa」 제목
    풍선이다(설계 규칙 UI-TXT-01 · UI-TXT-02)."""
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60)
    app.session_state[SAMPLE_TOGGLE_KEY] = False
    app.run()

    assert not app.exception
    (title,) = [item for item in app.markdown if str(item.value).startswith("####")]
    assert title.value == "#### :material/pending: 표준 대비 실적 Capa"
    tooltip = str(title.proto.help)
    assert "이 자리에 들어옵니다" in tooltip
    for meaning in ("손실 한 칸씩", "어느 하위 화면부터", "합산하지 않고 비율로 비교"):
        assert meaning in tooltip


def test_closed_formula_guide_is_not_drawn_until_its_tab_opens() -> None:
    """산식 가이드는 위젯 없는 정적 설명이라 닫혀 있으면 그리지 않는다. 열면 그 회차에 선다."""
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert not any("Capa 단계" in markdown.value for markdown in app.markdown)

    app.session_state["dynamic_capa_active_tab"] = "산식 가이드"
    app.run()

    assert not app.exception
    assert any("Capa 단계" in markdown.value for markdown in app.markdown)
    assert any("Gap 해석" in markdown.value for markdown in app.markdown)


def test_the_efficiency_gap_reads_percent_not_percent_point() -> None:
    """공정 상세 「효율 실적 / 기준」 의 증감과 산식 가이드 「Gap 해석」 은 「%」 다 — 「%p」 를
    쓰지 않는다(2026-11-01 사용자 결정 「%p표기하지말고 %로만」). 효율 Gap 은 그대로
    `실적 − 표준` 이다."""
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60)
    app.session_state["dynamic_capa_active_tab"] = "공정 상세"
    app.run()

    assert not app.exception
    efficiency = next(metric for metric in app.metric if metric.label == "효율 실적 / 기준")
    assert str(efficiency.delta).endswith("%") and "%p" not in str(efficiency.delta)

    app.session_state["dynamic_capa_active_tab"] = "산식 가이드"
    app.run()

    assert not app.exception
    guide = next(markdown.value for markdown in app.markdown if "효율 Gap" in markdown.value)
    assert "`실적 효율 − 표준 효율`" in guide and "%p" not in guide


# ------------------------------------------------------------------ 공정 상세 · 제품·Stack·WF 속성
PROCESS_KEY = "dynamic_capacity_process_filter"
PRODUCT_KEY = "dynamic_capacity_product_filter"
STACK_KEY = "dynamic_capacity_stack_filter"
WAFER_TYPE_KEY = "dynamic_capacity_wafer_type_filter"
ALL = "전체"


class _StaleChoice(NamedTuple):
    """첫 공정에서 고른 제품·Stack·WF 속성이 둘째 공정에는 없는 짝과, 두 공정에 다 있는 제품."""

    first_process: str
    second_process: str
    product: str
    stack: str
    wafer_type: str
    shared_product: str


def _stale_choice() -> _StaleChoice:
    """표본 공정·제품은 리터럴로 고정하지 않는다 — 합성 데모에서 조건에 맞는 짝을 찾는다."""
    demo = build_dynamic_capacity_demo().astype(
        {"공정": str, "제품정보": str, "Stack": str, "WF 구분": str}
    )
    processes = sorted(demo["공정"].unique())
    for first in processes:
        first_rows = demo.loc[demo["공정"].eq(first)]
        for second in processes:
            second_rows = demo.loc[demo["공정"].eq(second)]
            shared = sorted(set(first_rows["제품정보"]) & set(second_rows["제품정보"]))
            if first == second or not shared:
                continue
            for product in sorted(set(first_rows["제품정보"]) - set(second_rows["제품정보"])):
                product_rows = first_rows.loc[first_rows["제품정보"].eq(product)]
                for stack in sorted(set(product_rows["Stack"]) - set(second_rows["Stack"])):
                    stack_rows = product_rows.loc[product_rows["Stack"].eq(stack)]
                    wafer_types = set(stack_rows["WF 구분"]) - set(second_rows["WF 구분"])
                    if wafer_types:
                        return _StaleChoice(
                            first, second, product, stack, min(wafer_types), shared[0]
                        )
    raise AssertionError("합성 데모에 첫 공정에만 있는 제품·Stack·WF 속성 짝이 없습니다.")


def _choose(app: AppTest, browser: BrowserChoice, key: str, value: str) -> None:
    """상자 하나를 골라 회차를 돌린다. 들고 다니는 상자면 보이는 글자를 고른다."""
    if browser.key == key:
        browser.pick(value)
    else:
        app.selectbox(key=key).set_value(value)
    browser.run()
    assert not app.exception


@pytest.mark.parametrize("tracked_key", [PRODUCT_KEY, STACK_KEY, WAFER_TYPE_KEY])
def test_detail_choice_missing_from_the_new_process_shows_all_in_the_browser(
    tracked_key: str,
) -> None:
    """공정을 바꿔 고른 값이 선택지 밖이 되면 「전체」 로 돌아오고 **브라우저 글자도** 「전체」 다.

    세션 칸을 지우기만 하면 서버는 「전체」 로 계산하지만 새 값을 보내지 않아(`set_value` 없음)
    브라우저가 옛 글자를 계속 보이고 되보낸다 — 화면은 「공정 · 옛 제품」 인데 숫자는 공정 전체다.
    """
    choice = _stale_choice()
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60)
    app.session_state["dynamic_capa_active_tab"] = "공정 상세"
    browser = BrowserChoice(app, "selectbox", tracked_key)
    browser.start()
    assert not app.exception

    _choose(app, browser, PROCESS_KEY, choice.first_process)
    _choose(app, browser, PRODUCT_KEY, choice.product)
    _choose(app, browser, STACK_KEY, choice.stack)
    _choose(app, browser, WAFER_TYPE_KEY, choice.wafer_type)
    assert app.session_state[tracked_key] in {choice.product, choice.stack, choice.wafer_type}

    _choose(app, browser, PROCESS_KEY, choice.second_process)

    for key in (PRODUCT_KEY, STACK_KEY, WAFER_TYPE_KEY):
        assert app.session_state[key] == ALL
    assert browser.last_set_value
    assert browser.wire == ALL

    # 다음 조작들에도 브라우저가 옛 글자를 되보내지 않는다.
    for _ in range(2):
        browser.run()
        assert not app.exception
        assert app.session_state[tracked_key] == ALL
        assert browser.wire == ALL


def test_detail_product_kept_by_the_new_process_stays_selected() -> None:
    """새 공정에도 있는 제품은 그대로 남는다 — 선택지 밖일 때만 「전체」 로 돌린다."""
    choice = _stale_choice()
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60)
    app.session_state["dynamic_capa_active_tab"] = "공정 상세"
    browser = BrowserChoice(app, "selectbox", PRODUCT_KEY)
    browser.start()

    _choose(app, browser, PROCESS_KEY, choice.first_process)
    _choose(app, browser, PRODUCT_KEY, choice.shared_product)
    _choose(app, browser, PROCESS_KEY, choice.second_process)

    assert app.session_state[PRODUCT_KEY] == choice.shared_product
    assert browser.wire == choice.shared_product
    browser.run()
    assert not app.exception
    assert app.session_state[PRODUCT_KEY] == choice.shared_product
