# Purpose: 지표 카드 줄이 카드를 같은 폭·높이로 세우고 모자라면 줄을 접는 서식을 보내는지 지킨다.

"""지표 카드 줄(`metric_row`)의 서식.

값이 숫자뿐인 카드(「62.9%」)는 Archivo 한 서체라 줄 상자가 낮고, 한글이 섞인 카드(「28개월」)는
한글 서체 높이를 따라 높아 같은 줄에서 카드 상자 높이가 9px 갈렸다(공정 Capa 상세 KPI). 줄 높이를
고정하고 칸을 줄 높이로 늘리는 규칙이 빠지면 예외 없이 다시 갈리므로 서식 글로 지킨다. 실제 높이는
브라우저에서 쟀다(여섯 화면의 카드 줄마다 높이 하나).
"""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

from capa_simulation.components import status_metric


def _row_app() -> None:
    import streamlit as st

    from capa_simulation.components.status_metric import metric_row, render_status_metric

    with metric_row(key="sample_row"):
        render_status_metric("최저", "62.9%", key="sample_low", tone="critical", caption="26.11")
        render_status_metric("미달", "28개월", key="sample_short", caption="월별")
        st.metric("원인", "보유 28", border=True)


def _row_style() -> str:
    app = AppTest.from_function(_row_app)
    app.run()
    assert not app.exception
    styles = [str(element.proto.body) for element in app.get("html")]
    (row,) = [body for body in styles if ".st-key-sample_row" in body]
    return row


def test_the_metric_row_stretches_cards_to_one_height() -> None:
    style = _row_style()

    assert '.st-key-sample_row [data-testid="stHorizontalBlock"] {' in style
    assert "align-items: stretch !important;" in style
    assert ':has(> [data-testid="stMetric"]) {' in style
    assert '.st-key-sample_row [data-testid="stMetric"] {\n    height: 100%;' in style
    # 폭 맞춤은 그대로다.
    assert "flex: 1 1 0 !important;" in style


def test_the_metric_row_wraps_cards_instead_of_cutting_their_text() -> None:
    """카드 최소 폭이 0 이면 좁은 창(1024~1366px)에서 카드가 글자보다 좁아져 값·라벨이 한 줄
    말줄임으로 잘렸다(「71.8% / 82…」 · 「99.2…」 · 「중앙 설비 성능 실현…」). 최소 폭을 내용
    폭으로 두어 들어가지 않는 카드는 다음 줄로 내린다 — 라벨은 grid 칸 최소 폭이 0 이라 따로
    내용 폭으로 둔다."""
    style = _row_style()

    assert (
        '.st-key-sample_row [data-testid="stHorizontalBlock"] > * {\n'
        "    flex: 1 1 0 !important;\n"
        "    min-width: min-content !important;\n"
        "}"
    ) in style
    assert "min-width: 0" not in style
    assert (
        '.st-key-sample_row [data-testid="stMetricLabel"] {\n    min-width: max-content;' in style
    )


def test_the_metric_row_fixes_value_and_caption_line_heights() -> None:
    style = _row_style()

    assert (
        '.st-key-sample_row [data-testid="stMetricValue"],\n'
        '.st-key-sample_row [data-testid="stMetricValue"] * {\n'
        f"    line-height: {status_metric.VALUE_LINE_HEIGHT};"
    ) in style
    assert (
        '.st-key-sample_row [data-testid="stMetricDelta"],\n'
        '.st-key-sample_row [data-testid="stMetricDelta"] * {\n'
        f"    line-height: {status_metric.DELTA_LINE_HEIGHT};"
    ) in style
    # 한글 서체의 기본 줄 높이(≈1.43)보다 낮으면 한글 값의 글자가 줄 상자 밖으로 나간다.
    assert status_metric.VALUE_LINE_HEIGHT >= 1.43
    assert status_metric.DELTA_LINE_HEIGHT >= 1.43
