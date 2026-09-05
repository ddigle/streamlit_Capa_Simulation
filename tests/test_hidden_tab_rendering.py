# Purpose: 숨겨진 탭 안에서 Plotly 표를 그리지 않는다는 규칙을 지킨다.

"""사용자가 신고한 "년월 헤더가 셀 구석에 처박힌다" 의 두 번째 원인을 고정한다.

`st.tabs` 는 모든 탭의 본문을 한 번에 그려 두고 비활성 탭만 `display: none` 으로 감춘다.
숨겨진 요소 안에서는 SVG 글자 폭 측정이 0 이라 `go.Table` 이 가운데 정렬 보정을 못 하고,
헤더가 셀 중앙에서 **글자 폭의 절반만큼** 오른쪽으로 밀린다. `staticPlot` 이라 나중에
보이게 되어도 다시 그리지 않아 어긋난 채로 남는다.

브라우저 실측(1400x900, 공정별 확보율):
  보이는 탭 헤더 중심 x = 50, 150, 250, 350   (컬럼 폭 100px 의 가운데)
  숨은 탭에서 그려진 뒤 열어 본 헤더 중심 x = 68, 168, 268, 368  (+18 = 36px 글자의 절반)
  숨은 탭의 라벨 Figure 는 폭까지 어긋났다. 컨테이너가 0 이라 plotly 기본값 700 이 잡혔다.

고친 방법: `st.tabs` 에 `key` 와 `on_change="rerun"` 을 줘서 서버가 열린 탭을 알게 하고,
닫힌 탭에서는 Figure 를 그리지 않는다. 탭을 누르면 rerun 이 돌아 그때 보이는 상태로 그린다.
"""

import re
from pathlib import Path

import plotly.graph_objects as go

from capa_simulation.components.monthly_table_base import header_label, render_split_scroll_table
from capa_simulation.components.tab_state import tab_is_hidden

PROJECT_ROOT = Path(__file__).resolve().parents[1]

TAB_OWNER = PROJECT_ROOT / "src/capa_simulation/components/tab_state.py"

# 페이지가 직접 `st.tabs(` 를 부르면 key·on_change 를 빠뜨릴 수 있고, 그러면 `tab.open` 이
# 계속 None 이라 닫힌 탭을 가려낼 수 없다. 실측으로 확인한 동작이다.
DIRECT_TABS_CALL = re.compile(r"\bst\.tabs\(")


class _FakeTab:
    """`st.tabs` 컨테이너 흉내. `open` 만 있으면 판정에 충분하다."""

    def __init__(self, is_open: bool | None) -> None:
        self.open = is_open


def _month_figure() -> go.Figure:
    figure = go.Figure(
        go.Table(
            columnwidth=[1.0, 1.0],
            header={"values": ["<b>26.07</b>", "<b>26.08</b>"]},
            cells={"values": [[1.0], [2.0]]},
        )
    )
    figure.update_layout(width=200, autosize=False)
    return figure


def test_hidden_tab_is_only_the_definitely_closed_one() -> None:
    """`None` 은 "모른다" 다. 모를 때 건너뛰면 화면이 통째로 비어 버린다."""
    assert tab_is_hidden(_FakeTab(False)) is True
    assert tab_is_hidden(_FakeTab(True)) is False
    assert tab_is_hidden(_FakeTab(None)) is False
    assert tab_is_hidden(None) is False


def test_closed_tab_draws_nothing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """닫힌 탭에서는 Figure 를 하나도 그리지 않는다."""
    drawn: list[object] = []
    monkeypatch.setattr(
        "capa_simulation.components.monthly_table_base.st.plotly_chart",
        lambda *args, **kwargs: drawn.append(args),
    )

    render_split_scroll_table(
        key="demo",
        label_figure=go.Figure(),
        month_figure=_month_figure(),
        classification_widths=[100.0],
        month_count=2,
        owner_tab=_FakeTab(False),
    )

    assert drawn == []


# 탭 안에서 이 중 하나라도 그리면 열린 탭을 가려낼 수 있어야 한다. Plotly 표는
# 숨겨진 채로 그리면 헤더가 어긋나고, `data_editor` 는 닫힌 탭을 건너뛰어 계산을 아낀다.
CHART_MARKERS = (
    "st.plotly_chart",
    "render_hierarchical_monthly_table(",
    "render_grouped_monthly_table(",
    "render_month_editor(",
)


def test_tabs_that_hold_charts_use_the_stateful_helper() -> None:
    """`st.tabs` 를 직접 부르면 `key`·`on_change` 를 빠뜨려 `tab.open` 이 계속 None 이다.

    차트가 없는 탭은 숨겨져도 어긋날 것이 없으므로 강제하지 않는다. 탭 클릭마다 rerun 을
    치르는 값을 얻는 것이 없기 때문이다.
    """
    sources = [
        *(PROJECT_ROOT / "app_pages").glob("*.py"),
        *(PROJECT_ROOT / "src/capa_simulation").rglob("*.py"),
    ]
    offenders = []
    for path in sources:
        if path == TAB_OWNER:
            continue
        source = path.read_text(encoding="utf-8")
        if not DIRECT_TABS_CALL.search(source):
            continue
        if any(marker in source for marker in CHART_MARKERS):
            offenders.append(path.relative_to(PROJECT_ROOT).as_posix())

    assert not offenders, f"tab_state.stateful_tabs 를 쓰세요: {offenders}"


def test_stateful_tabs_asks_for_a_rerun() -> None:
    """`key` 만으로는 부족하다. `on_change="rerun"` 이 있어야 `tab.open` 이 확정된다."""
    source = TAB_OWNER.read_text(encoding="utf-8")

    assert 'on_change="rerun"' in source


def test_header_labels_never_contain_a_plain_space() -> None:
    """머리글에 공백이 있으면 plotly 가 줄바꿈 경로로 내려간다.

    그 경로는 `getComputedTextLength()` 로 재는데, 숨겨진 채로 그리면 글자가 통째로 비기도
    한다. `COLUMN_LABELS["Capa Code"] = "PKG Code"` 가 유일하게 공백을 갖고 있었다.
    """
    assert header_label("PKG Code") == "<b>PKG Code</b>"
    assert " " not in header_label("PKG Code")


def test_header_label_stays_bold() -> None:
    """`<b>` 를 빼면 가로는 항상 정확해지지만 글자가 밴드 위쪽에 붙는다(실측 4.5px).

    가로 어긋남은 숨겨진 채로 그리지 않는 것으로 막고, 세로 정렬은 그대로 지킨다.
    """
    assert header_label("26.07").startswith("<b>")
