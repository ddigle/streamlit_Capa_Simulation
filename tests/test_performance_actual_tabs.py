# Purpose: 실적 화면이 닫힌 요약·개선과제 탭을 건너뛰고 열린 탭은 같은 값을 그리는지 본다.

from __future__ import annotations

from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components import performance_actual_screen as screen
from capa_simulation.services.performance_actuals import (
    EFFICIENCY_METRIC,
    build_monthly_actual_demo,
    build_priority_table,
)

TAB_KEY = "tabs_test_active_tab"


def _app() -> None:
    from capa_simulation.components.performance_actual_screen import (
        render_performance_actual_screen,
    )
    from capa_simulation.components.process_labels import ProcessLabels
    from capa_simulation.services.performance_actuals import EFFICIENCY_METRIC

    render_performance_actual_screen(
        EFFICIENCY_METRIC, key_prefix="tabs_test", process_labels=ProcessLabels()
    )


@pytest.fixture
def priority_builds(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return build_priority_table(*args, **kwargs)

    monkeypatch.setattr(screen, "build_priority_table", counting)
    return calls


def _open(label: str) -> AppTest:
    app = AppTest.from_function(_app, default_timeout=60)
    app.session_state[TAB_KEY] = label
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _tab(app: AppTest, label: str) -> Any:
    return next(tab for tab in app.tabs if tab.label == label)


def _expected_priority() -> Any:
    return build_priority_table(build_monthly_actual_demo(), EFFICIENCY_METRIC, ["공정"])


@pytest.mark.parametrize(("label", "builds"), [("요약", 1), ("상세 분석", 0), ("개선과제", 1)])
def test_the_priority_table_is_built_once_and_only_for_an_open_tab_that_uses_it(
    priority_builds: list[int], label: str, builds: int
) -> None:
    app = _open(label)
    priority_builds.clear()

    app.run()

    assert len(priority_builds) == builds


def test_closed_summary_and_action_tabs_draw_nothing() -> None:
    app = _open("상세 분석")

    assert not _tab(app, "요약").get("metric")
    assert not _tab(app, "요약").get("plotly_chart")
    assert not _tab(app, "개선과제").get("dataframe")
    # 상세 분석의 조회 조건 위젯은 그대로다.
    assert _tab(app, "상세 분석").get("multiselect")


def test_the_open_summary_shows_the_same_numbers() -> None:
    app = _open("요약")
    priority = _expected_priority()

    metrics = {metric.label: metric.value for metric in _tab(app, "요약").get("metric")}
    assert metrics["개선 필요 공정"] == f"{int(priority['상태'].eq('개선 필요').sum()):,}개"
    assert metrics["관찰 공정"] == f"{int(priority['상태'].eq('관찰').sum()):,}개"
    assert metrics["분석 공정"] == f"{priority['공정'].nunique():,}개"
    assert len(_tab(app, "요약").get("plotly_chart")) == 2
    assert not _tab(app, "개선과제").get("dataframe")


def test_the_open_action_tab_shows_the_priority_table() -> None:
    app = _open("개선과제")
    priority = _expected_priority()

    tables = _tab(app, "개선과제").get("dataframe")
    shown = tables[0].value
    assert shown["우선순위"].tolist() == priority["우선순위"].tolist()
    assert shown["점수"].tolist() == priority["점수"].tolist()
    assert shown["상태"].tolist() == priority["상태"].tolist()
    assert not _tab(app, "요약").get("metric")


def test_opening_a_tab_draws_it_in_that_run() -> None:
    app = _open("상세 분석")
    assert not _tab(app, "개선과제").get("dataframe")

    app.session_state[TAB_KEY] = "개선과제"
    app.run()

    assert not app.exception
    assert _tab(app, "개선과제").get("dataframe")
    assert not _tab(app, "상세 분석").get("plotly_chart")


def test_the_summary_verdict_is_one_plain_line_with_no_particle_after_the_process_name() -> None:
    """요약 결론은 공정 이름 바로 뒤에 조사를 붙이지 않는다 — 라틴 이름이 「이(가)」 가 됐다
    (「TC Bonding 이(가) 12개월 연속 …」 — E2E r2 #90·r3 #93). 결론은 상자 없는 평문 한 줄이고
    건수는 바로 아래 「개선 필요 공정」 칸 몫이다(설계 규칙 UI-TXT-04 · UI-TXT-07)."""
    priority = _expected_priority()
    worst = priority.loc[priority["상태"].eq("개선 필요")].iloc[0]

    app = _open("요약")

    assert not _tab(app, "요약").get("warning")
    (verdict,) = [str(item.value) for item in _tab(app, "요약").get("caption")]
    assert verdict.startswith(f"**{worst['공정']}** — {int(worst['연속 미달'])}개월 연속 ")
    assert "이(가)" not in verdict
    assert "개선 필요 공정은" not in verdict


@pytest.mark.parametrize("label", ["요약", "상세 분석", "개선과제"])
def test_reading_notes_are_tooltips_not_lines_in_the_open_tab(label: str) -> None:
    """구획을 읽는 법(Gap · 순위 · 점수 셈)은 구획 제목 풍선이다 — 열린 탭 자리에는 설명 캡션이 없다
    (설계 규칙 UI-TXT-01 · UI-TXT-02, 합성 데모라 빈 결과 줄도 서지 않는다). 요약 탭의 한 줄은 결론
    값이다(UI-TXT-04)."""
    app = _open(label)
    tab = _tab(app, label)

    assert len(tab.get("caption")) == (1 if label == "요약" else 0)
    titled = [item for item in tab.get("markdown") if str(item.value).startswith("#### ")]
    assert titled
    explained = [item for item in titled if item.proto.help]
    assert explained, [item.value for item in titled]


def test_the_metric_meaning_is_the_tooltip_of_the_actual_card() -> None:
    """지표의 뜻(무엇을 재는가 · 기준이 어디서 오는가)은 머리 캡션이 아니라 실적 칸 풍선이다."""
    app = _open("요약")

    (actual,) = [
        item
        for item in _tab(app, "요약").get("metric")
        if item.label == f"실적 {EFFICIENCY_METRIC.name}"
    ]
    assert actual.proto.help == EFFICIENCY_METRIC.description


def test_the_sample_switch_line_is_a_badge_with_its_meaning_in_a_tooltip() -> None:
    """켜진 샘플 스위치 곁은 「합성 샘플」 배지와 표지 「실적 아님」 이고 뜻은 그 풍선이다 — 끄면
    스위치만 서고 「… 미연결」 은 머리 배지 몫이라 거듭 세우지 않으며, 끈 상태의 뜻은 스위치 풍선이
    말한다(설계 규칙 UI-TXT-04 · UI-TXT-07 · UI-NTF-05)."""
    app = _open("요약")
    (badge,) = [item for item in app.markdown if "합성 샘플" in str(item.value)]
    assert badge.value == ":orange-badge[:material/science: 합성 샘플] **실적 아님**"
    assert "실적이 아닙니다" in badge.proto.help

    switch = app.toggle(key="dynamic_capa_sample_data")
    assert "켜면 연결 후 모습" in switch.proto.help
    assert f"{EFFICIENCY_METRIC.source} 연결 대기" in switch.proto.help

    switch.set_value(False).run()
    assert not app.exception, [item.message for item in app.exception]
    assert not [item.value for item in app.markdown if "미연결" in str(item.value)]
    assert not [item.value for item in app.markdown if "합성 샘플" in str(item.value)]
    assert not [item.value for item in app.caption]
    (title,) = [item for item in app.markdown if ":material/pending:" in str(item.value)]
    assert "이 자리에 들어옵니다" in title.proto.help


def test_the_pending_screen_keeps_what_it_will_calculate_in_the_title_tooltip() -> None:
    """샘플을 끄면 「연결되면 계산할 것」 네 줄은 제목 풍선이다 — 자리에는 제목과 연결 대기 표지
    한 줄뿐이다(설계 규칙 UI-LAY-10 · UI-TXT-01, 사용자 답 desc-blocks)."""
    app = _open("요약")
    app.toggle(key="dynamic_capa_sample_data").set_value(False).run()
    assert not app.exception, [item.message for item in app.exception]

    (title,) = [item for item in app.markdown if str(item.value).startswith("####")]
    tooltip = str(title.proto.help)
    assert "연결되면 계산할 것" in tooltip
    assert EFFICIENCY_METRIC.gap_formula in tooltip
    for name in ("**상태**", "**우선순위 점수**", "**비율 집계**"):
        assert name in tooltip
    (slot,) = [item for item in app.get("html") if "연결 대기" in item.proto.body]
    assert f"<strong>{EFFICIENCY_METRIC.source} 연결 대기</strong>" in slot.proto.body
