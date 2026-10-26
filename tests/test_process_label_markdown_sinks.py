# Purpose: 공정 표시명이 실적·Dynamic·Chatbot·HOME 마크다운 자리에 글자 그대로 실리는지 본다.

"""공정 표시명(Proc Rename)은 사람 글이다 — 마크다운 자리에서 막는다(AGENTS 9장).

표시명 「TC~B~1 *z*」 가 효율·UPEH·수율 실적 요약 경고와 Dynamic Capa 요약 경고에서는
`**{이름}**` 에 날로 끼워져 `<strong>TC<del>B</del>1 <em>z</em></strong>` 로, 공정 상세 캡션에서는
지움선·기울임으로 그려졌다. Capa Chatbot 은 결론의 조회기간 「26.01~12월」 물결표가 이름 물결표와
짝을 지어 문장 대부분이 지움선이 되었고(물결표 하나인 「10~12월 본딩」 도 같다), HOME 사이드바
「주요공정 히트맵」 팝업의 라디오 캡션도 같은 꼴이었다(2026-10-26 E2E). 시험은 그리는 글(마크다운
원문)에 막은 이름이 실리고 막지 않은 이름이 남지 않는지 본다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import capa_simulation.components.process_labels as process_labels_module
from capa_simulation.components.home_preference import key_process_preview
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.services.dynamic_capacity import build_dynamic_capacity_demo
from capa_simulation.services.performance_actuals import build_monthly_actual_demo

ROOT = Path(__file__).resolve().parents[1]
CHATBOT_PAGE = ROOT / "app_pages" / "capa_chatbot.py"
DYNAMIC_PAGE = ROOT / "app_pages" / "reference_integrity.py"

# 물결표 둘(지움선)과 별표 둘(기울임)을 함께 든 표시명. 공정마다 번호를 붙여 겹치지 않게 한다.
MARKED = "TC~B~{index} *z*"
# 물결표 하나인 표시명 — 앱이 지은 범위 물결표(조회기간 「26.01~12월」)와 짝을 짓는다.
SINGLE_TILDE = "10~12월 본딩{index}"


def _renamed(processes: list[str], template: str) -> ProcessLabels:
    """표본 공정 전부에 `template` 꼴 표시명을 단다(표본 공정명을 리터럴로 두지 않는다)."""
    return ProcessLabels(
        version=11,
        labels={process: template.format(index=index) for index, process in enumerate(processes)},
    )


def _markdown_texts(app: AppTest) -> list[str]:
    """마크다운으로 그려지는 글 — 알림 상자·캡션·마크다운(대화 말풍선 포함)과 단추 라벨."""
    texts: list[str] = []
    for kind in ("markdown", "caption", "warning", "info", "success", "error"):
        texts += [str(item.value) for item in getattr(app, kind)]
    texts += [str(button.label) for button in app.button]
    return texts


def _assert_literal(texts: list[str], labels: ProcessLabels) -> list[str]:
    """막지 않은 표시명이 어느 글에도 남지 않는다. 막은 표시명이 실린 글을 돌려준다."""
    for shown in labels.labels.values():
        raw = [text for text in texts if shown in text]
        assert not raw, (shown, raw)
    escaped = {literal_markdown(shown) for shown in labels.labels.values()}
    return [text for text in texts if any(name in text for name in escaped)]


@pytest.fixture
def shared_labels(monkeypatch: pytest.MonkeyPatch) -> dict[str, ProcessLabels]:
    """화면이 읽는 공용 공정 표시명 — 시험이 `labels["now"]` 를 정한다(공용 프로필 DB 를 열지
    않는다)."""
    holder = {"now": ProcessLabels()}
    monkeypatch.setattr(process_labels_module, "get_process_labels", lambda: holder["now"])
    return holder


# ------------------------------------------------------------- 효율·UPEH·수율 실적 요약


def _performance_screen() -> None:
    from capa_simulation.components.performance_actual_screen import (
        render_performance_actual_screen,
    )
    from capa_simulation.components.process_labels import get_process_labels
    from capa_simulation.services.performance_actuals import EFFICIENCY_METRIC

    render_performance_actual_screen(
        EFFICIENCY_METRIC, key_prefix="markdown_sink", process_labels=get_process_labels()
    )


def test_the_actual_summary_warning_shows_the_display_name_literally(
    shared_labels: dict[str, ProcessLabels],
) -> None:
    processes = sorted(build_monthly_actual_demo()["공정"].astype(str).unique())
    shared_labels["now"] = _renamed(processes, MARKED)

    app = AppTest.from_function(_performance_screen, default_timeout=60).run()

    assert not app.exception, [item.message for item in app.exception]
    warnings = [str(item.value) for item in app.warning]
    assert warnings, "개선 필요 공정이 있는 표본이어야 결론 경고가 선다"
    carrying = _assert_literal(_markdown_texts(app), shared_labels["now"])
    assert any(text in carrying for text in warnings), warnings


# ------------------------------------------------------------------------ Dynamic Capa


def test_the_dynamic_summary_and_detail_caption_show_the_display_name_literally(
    shared_labels: dict[str, ProcessLabels],
) -> None:
    processes = sorted(build_dynamic_capacity_demo()["공정"].astype(str).unique())
    labels = _renamed(processes, MARKED)
    shared_labels["now"] = labels

    app = AppTest.from_file(str(DYNAMIC_PAGE), default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]
    summary = [str(item.value) for item in app.warning if "Capa 실현률이" in str(item.value)]
    assert summary, "개선 필요 공정이 있는 표본이어야 결론 경고가 선다"
    assert all(text in _assert_literal(_markdown_texts(app), labels) for text in summary)

    app.session_state["dynamic_capa_active_tab"] = "공정 상세"
    app.selectbox(key="dynamic_capacity_process_filter").set_value(processes[0])
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    carrying = _assert_literal(_markdown_texts(app), labels)
    caption = f"선택한 {literal_markdown(labels.label(processes[0]))} 공정의"
    assert any(caption in text for text in carrying), carrying


# ------------------------------------------------------------------------ Capa Chatbot


@pytest.mark.parametrize("template", [MARKED, SINGLE_TILDE])
def test_the_chatbot_script_shows_the_display_name_literally(
    shared_labels: dict[str, ProcessLabels], template: str
) -> None:
    """결론·질문(말풍선·추천 질문 단추)·조건 줄 — 조회기간 「26.01~12월」 과 짝을 짓지 않는다."""
    processes = sorted(build_monthly_actual_demo()["공정"].astype(str).unique())
    labels = _renamed(processes, template)
    shared_labels["now"] = labels
    app = AppTest.from_file(str(CHATBOT_PAGE), default_timeout=60).run()
    for index in (1, 2, 3):
        app.button(key=f"capa_chatbot_example_{index}").click().run()
        assert not app.exception, [item.message for item in app.exception]

    carrying = _assert_literal(_markdown_texts(app), labels)

    # 결론 셋(미달·원인·우선순위)·원인 질문(말풍선과 단추)·원인 조건 줄이 표시명을 싣는다.
    assert sum("기준으로 효율이 기준에 못 미치는 공정은" in text for text in carrying) == 1
    assert sum("효율·UPEH·수율 세 지표가 모두" in text for text in carrying) == 1
    assert sum("부터입니다. 미달폭만 보면" in text for text in carrying) == 1
    assert sum(text.endswith(" 왜 부족해?") for text in carrying) == 2
    assert any("· 공정 " in text and "조회기간 " in text for text in carrying), carrying
    # 근거 표의 `공정` 칸은 평문이라 막지 않은 표시명이다.
    evidence = [frame.value for frame in app.dataframe if "공정" in frame.value.columns]
    assert evidence
    shown = set(labels.labels.values())
    assert all(value in shown for frame in evidence for value in frame["공정"])


# ------------------------------------------------------------- HOME 주요공정 히트맵 팝업


def test_the_key_process_preview_caption_shows_the_display_name_literally() -> None:
    labels = ProcessLabels(labels={"DEMO_A": "TC~B~1 *z*", "DEMO_B": "10~12월 본딩"})

    preview = key_process_preview(["DEMO_A", "DEMO_B"], labels, ["DEMO_A"])

    assert preview == (
        f"1공정 · {literal_markdown('TC~B~1 *z*')} · 이 화면에 없음: "
        f"{literal_markdown('10~12월 본딩')}"
    )


def _preference_notices() -> None:
    import pandas as pd

    from capa_simulation.components.home_preference import (
        _render_execution_notices,
        _render_key_process_notice,
    )
    from capa_simulation.components.process_labels import ProcessLabels

    labels = ProcessLabels(labels={"DEMO_A": "TC~B~1 *z*"})
    _render_key_process_notice(["DEMO_A"], labels)
    _render_execution_notices(
        pd.DataFrame({"생산계획년월": [202607], "공정": ["DEMO_A"]}), pd.DataFrame(), labels
    )


def test_the_preference_notices_show_the_display_name_literally() -> None:
    """같은 화면(HOME Preference)의 이웃 자리 — 프리셋에 있으나 그리지 않는 공정 캡션과 확보율
    보정의 짝 없는 행 경고."""
    app = AppTest.from_function(_preference_notices, default_timeout=60).run()

    assert not app.exception, [item.message for item in app.exception]
    texts = [str(item.value) for item in app.caption] + [str(item.value) for item in app.warning]
    assert not [text for text in texts if "TC~B~1 *z*" in text], texts
    escaped = literal_markdown("TC~B~1 *z*")
    assert any("그리지 않는 공정: " + escaped in text for text in texts), texts
    assert any("26.07·" + escaped in text for text in texts), texts


def test_the_markers_really_turn_into_markdown() -> None:
    """시험의 표시명이 정말 마크다운 꾸밈을 품는지 — 막은 글이 원문과 다르다."""
    assert literal_markdown(MARKED.format(index=1)) != MARKED.format(index=1)
    assert literal_markdown(SINGLE_TILDE.format(index=1)) != SINGLE_TILDE.format(index=1)
