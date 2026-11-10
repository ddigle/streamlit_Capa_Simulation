# Purpose: 실적 화면의 탭 건너뛰기 · 같은 값과 사이드바 샘플 줄 · 조건 카드 · 머리 배지 없음을 본다.

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Expander, Status

from capa_simulation.components import performance_actual_screen as screen
from capa_simulation.services.performance_actuals import (
    EFFICIENCY_METRIC,
    build_monthly_actual_demo,
    build_priority_table,
)

TAB_KEY = "tabs_test_active_tab"
PAGES = Path(__file__).resolve().parents[1] / "app_pages"


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
    # 상세 분석의 조회 조건은 본문이 아니라 사이드바 카드다.
    assert not _tab(app, "상세 분석").get("multiselect")
    assert app.sidebar.multiselect


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


def test_the_summary_verdict_is_the_tooltip_of_the_needs_action_card() -> None:
    """요약 결론(가장 시급한 공정)은 칸 위 캡션이 아니라 「개선 필요 공정」 칸 풍선이다 — 본문 상단
    문구 최소화(2026-11-09 보드 T8). 공정 이름 바로 뒤에 조사를 붙이지 않는다 — 라틴 이름이
    「이(가)」 가 됐다(「TC Bonding 이(가) 12개월 연속 …」 — E2E r2 #90·r3 #93). 건수는 칸 값이라
    풍선이 되풀이하지 않는다(설계 규칙 UI-TXT-04 · UI-TXT-07)."""
    priority = _expected_priority()
    worst = priority.loc[priority["상태"].eq("개선 필요")].iloc[0]

    app = _open("요약")

    assert not _tab(app, "요약").get("warning")
    assert not _tab(app, "요약").get("caption")
    (card,) = [item for item in _tab(app, "요약").get("metric") if item.label == "개선 필요 공정"]
    tooltip = str(card.proto.help)
    assert "3개월 이상 연속" in tooltip
    assert f"**{worst['공정']}** · {int(worst['연속 미달'])}개월 연속 미달" in tooltip
    assert "이(가)" not in tooltip
    assert "개선 필요 공정은" not in tooltip


@pytest.mark.parametrize("label", ["요약", "상세 분석", "개선과제"])
def test_reading_notes_are_tooltips_not_lines_in_the_open_tab(label: str) -> None:
    """구획을 읽는 법(Gap · 순위 · 점수 셈)은 구획 제목 풍선이다 — 열린 탭 자리에는 설명 캡션이 없다
    (설계 규칙 UI-TXT-01 · UI-TXT-02, 합성 데모라 빈 결과 줄도 서지 않는다). 요약 탭의 결론도 칸
    풍선이다(2026-11-09 보드 T8)."""
    app = _open(label)
    tab = _tab(app, label)

    assert not tab.get("caption")
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


def test_the_detail_conditions_stand_in_the_sidebar_card_while_the_tab_is_open() -> None:
    """상세 분석의 조회 조건(분석 기간 · 공정 · 제품)은 사이드바 「효율 실적 조건」 카드이고 그 탭이
    열린 회차에만 선다(2026-11-09 보드 T8 — 구현 중 화면도 지금 사이드바로, 설계 규칙 UI-LAY-02).
    카드가 없는 회차를 지나도 고른 값은 남는다(`persist_state`)."""
    app = _open("상세 분석")

    (card,) = _cards(app, "효율 실적 조건")
    # 카드는 처음 펼친 채다 — 본문에 있을 때처럼 조건이 첫 화면에 보인다(2026-11-10 보드 Q-7).
    assert card.proto.expanded
    assert [element.label for element in card.children.values()] == ["분석 기간", "공정", "제품"]
    assert not _tab(app, "상세 분석").get("select_slider")
    assert not _tab(app, "상세 분석").get("selectbox")
    product = app.selectbox(key="tabs_test_product_filter")
    choice = product.options[1]
    product.set_value(choice).run()
    assert not app.exception, [item.message for item in app.exception]

    app.session_state[TAB_KEY] = "요약"
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert not _cards(app, "효율 실적 조건")

    app.session_state[TAB_KEY] = "상세 분석"
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.selectbox(key="tabs_test_product_filter").value == choice


def _cards(app: AppTest, label: str) -> list[Any]:
    """사이드바 조건 카드(아이콘을 단 확장 패널은 AppTest 에서 `Status` 다)."""
    return [
        item for item in app.sidebar if isinstance(item, (Status, Expander)) and item.label == label
    ]


def test_the_sample_switch_is_a_sidebar_row_with_its_meaning_in_the_name_tooltip() -> None:
    """「샘플 데이터」 는 사이드바 조회 조건 패널 줄(이름 + 스위치)이고 뜻 · 「실적 아님」 은 이름
    풍선이다 — 본문에는 스위치 상자도 「합성 샘플 실적 아님」 표지도 없다(2026-11-09 보드 T8 —
    합성 샘플 표지는 머리 띠 몫). 끄면 연결 전 자리만 서고 본문 캡션은 없다(설계 규칙 UI-TXT-04 ·
    UI-TXT-07 · UI-LAY-02)."""
    from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY, SAMPLE_TOGGLE_LABEL

    app = _open("요약")
    assert not [item for item in app.main.toggle]
    assert not [item.value for item in app.markdown if "합성 샘플" in str(item.value)]
    switch = app.toggle(key=SAMPLE_TOGGLE_KEY)
    assert switch in list(app.sidebar.toggle)
    (name,) = [item for item in app.sidebar.caption if item.value == SAMPLE_TOGGLE_LABEL]
    assert "켜면 연결 후 모습" in name.proto.help
    assert "실적이 아닙니다" in name.proto.help
    assert f"{EFFICIENCY_METRIC.source} 연결 대기" in name.proto.help

    switch.set_value(False).run()
    assert not app.exception, [item.message for item in app.exception]
    assert not [item.value for item in app.markdown if "미연결" in str(item.value)]
    assert not [item.value for item in app.main.caption]
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


@pytest.mark.parametrize(
    ("page", "title", "source"),
    [
        ("actual_efficiency.py", "효율 실적", "생산이력 DB"),
        ("actual_upeh.py", "UPEH 실적", "생산이력 DB"),
        ("yield_actual.py", "수율 실적", "수율 실적 DB"),
    ],
)
def test_the_head_has_no_badge_line_on_either_side_of_the_switch(
    monkeypatch: pytest.MonkeyPatch, page: str, title: str, source: str
) -> None:
    """머리에는 배지 줄(「구현중 · 인터랙티브 프로토타입 · … 미연결」)이 없다 — 구현 중 표지는 화면
    탭 이름 곁, 합성 샘플 표지는 머리 띠다(2026-11-09 보드 T8, 본문 상단 문구 · 여백 최소화). 큰
    제목은 사이드바 라벨에서 「(구현중)」 을 뗀 이름이다(화면에서는 숨는다). 끄면 연결 전 자리가
    무엇을 기다리는지 말한다."""
    import capa_simulation.components.process_labels as process_labels_module
    from capa_simulation.components.process_labels import ProcessLabels
    from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY

    monkeypatch.setattr(process_labels_module, "get_process_labels", lambda: ProcessLabels())
    app = AppTest.from_file(str(PAGES / page), default_timeout=60)
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert [item.value for item in app.title] == [title]
    assert not _badge_lines(app)

    app.toggle(key=SAMPLE_TOGGLE_KEY).set_value(False).run()
    assert not app.exception, [item.message for item in app.exception]
    assert not _badge_lines(app)
    (slot,) = [item for item in app.get("html") if "연결 대기" in item.proto.body]
    assert f"<strong>{source} 연결 대기</strong>" in slot.proto.body


def _badge_lines(app: AppTest) -> list[str]:
    """머리 배지 글(구현중 · 성숙도 · 미연결)이 든 본문 마크다운."""
    marks = ("구현중", "인터랙티브 프로토타입", "미연결", "-badge[")
    return [
        str(item.value)
        for item in app.main.markdown
        if any(mark in str(item.value) for mark in marks)
    ]
