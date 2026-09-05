# Purpose: PKG PLAN 을 바꾸면 HOME 대시보드가 그 계획으로 다시 계산되는지 고정한다.

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

HOME_PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "home.py"

# 사용자가 보고한 증상: 부하량에서 PKG PLAN 을 고쳐도 HOME 이 예전 계획의 숫자를 보여준다.
# 원인은 HOME 계산 캐시 키가 시나리오 편집 카운터(`revision`)를 쓴 것이었다. 그 번호는
# 내용이 달라도 겹친다(세션 편집은 0,1,2..., 저장 리비전을 불러오면 그 번호가 그대로).
# `st.cache_data` 는 프로세스 전역이라 다른 브라우저 세션과도 겹쳤다.


def _script(database_path: Path) -> str:
    """HOME 을 실행하고 월별 Figure 의 셀 값을 session_state 에 기록한다."""
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
apply_pending_scenario_preset()

st.session_state["spy_cells"] = []
_original_plotly_chart = st.plotly_chart
_original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar


def _spy_plotly_chart(figure, *args, **kwargs):
    # HOME 의 월별 숫자는 bar·scatter trace 의 text·customdata 에 실린다.
    # numpy 배열이라 진리값 비교를 피하고 문자열 지문으로 모은다.
    prints = []
    for trace in getattr(figure, "data", []) or []:
        prints.append(str(getattr(trace, "text", None)))
        prints.append(str(getattr(trace, "customdata", None)))
    if prints:
        st.session_state["spy_cells"] = st.session_state["spy_cells"] + [prints]
    return _original_plotly_chart(figure, *args, **kwargs)


st.plotly_chart = _spy_plotly_chart
horizontal_scrollbar.render_horizontal_scrollbar = lambda *a, **k: None
try:
    exec(
        compile(
            Path({str(HOME_PAGE)!r}).read_text(encoding="utf-8"),
            {str(HOME_PAGE)!r},
            "exec",
        ),
        {{"__name__": "__main__"}},
    )
finally:
    st.plotly_chart = _original_plotly_chart
    horizontal_scrollbar.render_horizontal_scrollbar = _original_scrollbar
"""


@pytest.fixture(scope="module")
def seeded_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("home_sync") / "scenario.duckdb"


def test_home_recomputes_when_the_plan_changes(seeded_database: Path) -> None:
    """계획을 절반으로 줄이면 HOME 의 월별 숫자도 달라져야 한다."""
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    assert not list(app.exception)
    before = app.session_state["spy_cells"]
    assert before, "HOME 이 월별 표를 그리지 않았습니다."

    scenario = app.session_state["active_scenario"]
    plan = scenario["tables"]["RQ_PKG_PLAN"].copy()
    plan["생산수량"] = plan["생산수량"].astype(float) * 0.5
    app.session_state["active_scenario"] = {
        **scenario,
        "tables": {**scenario["tables"], "RQ_PKG_PLAN": plan},
        # 편집 경로(apply_month_updates)가 하는 일과 같다: 내용이 바뀌면 토큰을 새로 발급한다.
        "content_token": f"{scenario['content_token']}-halved",
    }

    app.run()

    assert not list(app.exception)
    after = app.session_state["spy_cells"]
    assert after != before, (
        "계획을 바꿨는데 HOME 숫자가 그대로입니다. 계산 캐시가 예전 결과를 재사용했습니다."
    )


def test_home_reuses_results_while_the_plan_is_unchanged(seeded_database: Path) -> None:
    """토큰이 그대로면 같은 결과를 재사용해야 한다. 캐시가 무의미해지면 안 된다."""
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    assert not list(app.exception)
    first = app.session_state["spy_cells"]

    app.run()

    assert not list(app.exception)
    assert app.session_state["spy_cells"] == first
