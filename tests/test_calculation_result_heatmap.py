# Purpose: 산출 결과 확보율 히트맵이 표 필터와 같은 행을 그리고 편 상태를 지키는지 검증한다.

"""산출 결과 확보율 탭의 `히트맵` 상자.

- 편 상자는 다른 탭에 갔다 와도 편 채다(2026-10-01 브라우저 점검). 산출 결과는 열린 탭의 본문만
  그린다. `key` 없는 확장 패널은 떠난 동안 그려지지 않아 돌아올 때 새로 만들어지고 기본값(접힘)으로
  섰다.
- 히트맵의 행은 **위 확보율 표와 같다**(2026-10-06 사용자 결정). 따로 고르는 「히트맵 주요 공정」
  목록·부족 요약·범례는 없다.
"""

from collections.abc import Iterator

import pytest
from streamlit.testing.v1 import AppTest
from test_reference_data_page import (
    CALC_TAB_KEY,
    REQUIRED_TAB,
    SECUREMENT_TAB,
    TWO_PROCESS_RESULT_SCRIPT,
)

HEATMAP_EXPANDER_KEY = "securement_heatmap_expander"
PROCESS_FILTER_KEY = "securement_filter_공정"
TABLE_PROCESSES = "captured_processes::securement_rate_monthly_table"
HEATMAP_PROCESSES = "captured_heatmap_processes"

# 히트맵이 받은 표의 공정을 잡는다. 페이지는 exec 로 새로 읽히므로 모듈 속성을 갈아끼우면 페이지의
# `from ... import render_securement_heatmap` 이 이 가짜를 집는다.
_HEATMAP_SPY = """
import capa_simulation.components.securement_heatmap as securement_heatmap_module


def capture_securement_heatmap(table, *args, **kwargs):
    st.session_state["captured_heatmap_processes"] = sorted(set(table["공정"].astype(str)))


securement_heatmap_module.render_securement_heatmap = capture_securement_heatmap
"""
_SPY_ANCHOR = "hierarchical_table.render_hierarchical_monthly_table = capture_hierarchical_table"
assert _SPY_ANCHOR in TWO_PROCESS_RESULT_SCRIPT
SPIED_RESULT_SCRIPT = TWO_PROCESS_RESULT_SCRIPT.replace(_SPY_ANCHOR, _SPY_ANCHOR + _HEATMAP_SPY)


@pytest.fixture(autouse=True)
def _restore_heatmap_renderer() -> Iterator[None]:
    """가짜는 실제 모듈 속성을 갈아끼운다.

    AppTest 는 같은 프로세스에서 돌아, 되돌리지 않으면 뒤의 시험이 가짜를 부른다.
    """
    from capa_simulation.components import securement_heatmap

    original = securement_heatmap.render_securement_heatmap
    yield
    securement_heatmap.render_securement_heatmap = original


def _heatmap_boxes(app: AppTest) -> list[bool]:
    """히트맵 상자의 펼침. 상태를 추적하는 상자는 id 끝이 그 `key` 다."""
    return [
        bool(box.proto.expanded)
        for box in app.expander
        if str(box.proto.id).endswith(f"-{HEATMAP_EXPANDER_KEY}")
    ]


def _open(app: AppTest, tab: str) -> AppTest:
    app.session_state[CALC_TAB_KEY] = tab
    app.run()
    assert not app.exception
    return app


def test_an_opened_heatmap_stays_open_after_a_trip_to_another_tab() -> None:
    app = _open(AppTest.from_string(TWO_PROCESS_RESULT_SCRIPT, default_timeout=60), SECUREMENT_TAB)
    assert _heatmap_boxes(app) == [False]

    app.session_state[HEATMAP_EXPANDER_KEY] = True  # 사용자가 상자를 편다
    app.run()
    assert _heatmap_boxes(app) == [True]

    _open(app, REQUIRED_TAB)
    assert _heatmap_boxes(app) == []
    _open(app, SECUREMENT_TAB)

    assert _heatmap_boxes(app) == [True]


def test_the_heatmap_follows_the_table_filter_and_carries_no_extra_parts() -> None:
    """표 조건 카드의 필터로 표를 좁히면 히트맵도 같은 공정만 그린다."""
    app = _open(AppTest.from_string(SPIED_RESULT_SCRIPT, default_timeout=60), SECUREMENT_TAB)

    # 상자 이름은 「히트맵」 하나다. 따로 고르는 목록·부족 요약·범례는 없다.
    assert [
        box.label for box in app.expander if str(box.proto.id).endswith(f"-{HEATMAP_EXPANDER_KEY}")
    ] == ["히트맵"]
    assert "히트맵 주요 공정" not in [widget.label for widget in app.sidebar.multiselect]
    assert "securement_shortage_summary" not in [frame.key for frame in app.dataframe]
    assert app.session_state[HEATMAP_PROCESSES] == ["Process-A", "Process-B"]
    assert app.session_state[HEATMAP_PROCESSES] == app.session_state[TABLE_PROCESSES]

    app.multiselect(key=PROCESS_FILTER_KEY).set_value(["Process-B"]).run()
    assert not app.exception

    assert app.session_state[TABLE_PROCESSES] == ["Process-B"]
    assert app.session_state[HEATMAP_PROCESSES] == ["Process-B"]
