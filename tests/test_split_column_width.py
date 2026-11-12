# Purpose: 분류(라벨) 컬럼 폭이 창 크기와 무관하게 px 로 고정되는지 지킨다.

"""분류 컬럼이 창 폭에 따라 줄어 이름이 잘리던 문제를 고정한다.

`st.columns` 의 인자는 비율이다. 그런데 분류 폭은 px 로 계산한 값을 그대로 넘기고 있어서,
컨테이너가 설계 폭보다 좁으면 분류 컬럼도 같이 줄었다. 1280px 창의 HOME 에서 구분 컬럼이
260px 대신 149px 로 잡혀 "Capa LOB 현황" 이 잘렸고, 반대로 조회 월이 두세 달뿐이면 비율이
커져 분류 컬럼이 필요 이상 넓어졌다.
"""

import re
from pathlib import Path

import pytest

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
from capa_simulation.components.home_dimensions import (
    DASHBOARD_LABEL_COLUMN_WIDTH_PX,
    NARROW_LABEL_COLUMN_WIDTH_PX,
    NARROW_VIEWPORT_MAX_PX,
)
from capa_simulation.components.monthly_table_base import (
    CLASSIFICATION_HORIZONTAL_PADDING_PX,
    MONTH_COLUMN_WIDTH_PX,
    MONTH_FLOOR_PX,
    MONTH_ROOM_COLUMNS,
    SCROLLBAR_HEIGHT_PX,
    classification_floor_px,
)
from capa_simulation.components.scroll_shell import (
    PLOTLY_MIN_CHART_WIDTH_PX,
    split_scroll_columns_style,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _rules(css: str) -> list[str]:
    return [line.strip() for line in re.sub(r"<[^>]+>", "", css).split("\n") if line.strip()]


def test_label_column_is_pinned_and_month_column_takes_the_rest() -> None:
    assert _rules(
        split_scroll_columns_style(
            label_key="demo_label_canvas",
            month_key="demo_month_region",
            label_width_px=318,
        )
    ) == _rules(
        """
        [data-testid="stColumn"]:has(.st-key-demo_label_canvas) {
            flex: 0 0 318px !important;
            width: 318px !important;
            min-width: 318px !important;
        }
        [data-testid="stColumn"]:has(.st-key-demo_month_region) {
            flex: 1 1 0 !important;
            width: auto !important;
            min-width: 0 !important;
        }
        """
    )


def test_month_column_may_shrink_below_its_content() -> None:
    """월 영역은 가로로 스크롤하므로 0 까지 줄어도 내용이 잘리지 않는다.

    `min-width: 0` 이 빠지면 flex 항목의 기본 `min-width: auto` 때문에 월 Figure 의 폭이
    컬럼의 최소 폭이 되고, 분류 컬럼이 다시 밀려 잘린다.
    """
    css = split_scroll_columns_style(
        label_key="demo_label_canvas",
        month_key="demo_month_region",
        label_width_px=200,
    )

    assert "min-width: 0 !important;" in css


def test_month_room_shares_a_tight_body_between_label_and_month_columns() -> None:
    """분류 합이 본문보다 넓으면 1100 창(사이드바 펼침)에서 달 칸이 아래로 떨어지고 분류 칸이 본문
    밖으로 94px 나갔다. 라벨 폭의 위 끝을 본문 비율로 건다 — 본문이 라벨 폭 + 달 칸 몫보다 넓으면
    `min()` 이 라벨 폭 그대로라 넓은 창의 칸은 줄지 않는다."""
    expected = "min(876px, 81.413%)"

    assert _rules(
        split_scroll_columns_style(
            label_key="demo_label_canvas",
            month_key="demo_month_region",
            label_width_px=876,
            month_room_px=200,
        )
    ) == _rules(
        f"""
        [data-testid="stColumn"]:has(.st-key-demo_label_canvas) {{
            flex: 0 0 {expected} !important;
            width: {expected} !important;
            min-width: {expected} !important;
        }}
        [data-testid="stColumn"]:has(.st-key-demo_month_region) {{
            flex: 1 1 0 !important;
            width: auto !important;
            min-width: 0 !important;
        }}
        """
    )


@pytest.mark.parametrize(
    ("body_px", "label_px"),
    [
        (1265, 876.0),  # 1600 창 — 라벨 폭 그대로, 달 칸은 남는 폭 전부
        (1076, 876.0),  # 라벨 폭 + 달 칸 몫 — 여기까지는 줄지 않는다
        (948, 771.8),  # 1283 창 — 달 칸 한 칸이 다 보인다
        (765, 622.8),  # 1100 창 — 넘치지 않고 달 칸이 곁에 남는다
    ],
)
def test_month_room_shrinks_only_when_the_body_cannot_hold_both_columns(
    body_px: float, label_px: float
) -> None:
    """규칙의 비율을 본문 폭에 대어 본다 — 브라우저가 `min()` 으로 풀 값과 같은 셈이다."""
    css = split_scroll_columns_style(
        label_key="demo_label_canvas",
        month_key="demo_month_region",
        label_width_px=876,
        month_room_px=200,
    )
    found = re.search(r"width: min\(876px, ([\d.]+)%\)", css)

    assert found is not None
    assert min(876.0, body_px * float(found[1]) / 100) == pytest.approx(label_px, abs=0.1)


def _floored_label_px(body_px: float, css: str) -> float:
    """`min(clamp(바닥, 비율, 라벨), calc(100% - 달 바닥))` 을 본문 폭에 대어 푼다."""
    found = re.search(
        r"width: min\(clamp\((\d+)px, ([\d.]+)%, (\d+)px\), calc\(100% - (\d+)px\)\)", css
    )

    assert found is not None
    floor_px, share, label_px, month_floor_px = (float(group) for group in found.groups())
    kept = min(max(floor_px, body_px * share / 100), label_px)
    return min(kept, body_px - month_floor_px)


@pytest.mark.parametrize(
    ("body_px", "label_px"),
    [
        (1265, 876.0),  # 1600 창 — 라벨 폭 그대로
        (948, 771.8),  # 1283 창 — 바닥 위에서는 비율대로
        (765, 670.0),  # 1100 창 — 바닥에 닿아 달 칸이 대신 준다
        (750, 670.0),  # 달 칸도 바닥에 닿는 자리
        (540, 460.0),  # 창 900 — 라벨 컬럼이 좁아지고 캔버스가 바닥 폭으로 스크롤한다
    ],
)
def test_label_floor_makes_the_month_column_give_way_before_the_text_is_cut(
    body_px: float, label_px: float
) -> None:
    """바닥이 없으면 창 1000 아래에서 분류 값 글이 잘렸고 창 800 에서 머리 글이 겹쳤다."""
    css = split_scroll_columns_style(
        label_key="demo_label_canvas",
        month_key="demo_month_region",
        label_width_px=876,
        month_room_px=200,
        label_floor_px=670,
        month_floor_px=80,
    )

    assert _floored_label_px(body_px, css) == pytest.approx(label_px, abs=0.1)


def test_label_floor_keeps_every_column_above_its_text() -> None:
    """칸은 같은 비율로 주므로 가장 넓은 칸이 여백을 다 내주는 폭이 바닥이다. 그 폭에서 어느 칸도
    글 폭(여백을 뺀 폭)보다 좁지 않다."""
    widths = [84, 153, 84, 117, 84, 90, 96, 84, 84]

    floor_px = classification_floor_px(widths)

    assert floor_px == 670
    for width in widths:
        assert width * floor_px / sum(widths) >= width - CLASSIFICATION_HORIZONTAL_PADDING_PX


def _split_table_app() -> None:
    import plotly.graph_objects as go

    from capa_simulation.components.monthly_table_base import render_split_scroll_table

    render_split_scroll_table(
        key="demo",
        label_figure=go.Figure(),
        month_figure=go.Figure(),
        classification_widths=[400, 476],
        month_count=12,
    )


def test_monthly_tables_ask_for_the_month_room(monkeypatch: pytest.MonkeyPatch) -> None:
    """월별 표 두 종류의 껍데기가 달 칸 몫을 걸고, 그 몫은 달 칸 두 칸이다. HOME · 가용설비 · 제약 ·
    공정 상세는 이 인자를 주지 않아 지금 폭 그대로다."""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda **_: None)
    app = AppTest.from_function(_split_table_app).run()

    assert not app.exception
    assert MONTH_ROOM_COLUMNS * MONTH_COLUMN_WIDTH_PX == 200
    bodies = [element.proto.body for element in app.get("html")]
    assert any(
        f"min(clamp(810px, 81.413%, 876px), calc(100% - {MONTH_FLOOR_PX}px))" in body
        for body in bodies
    )
    for relative in (
        "src/capa_simulation/components/home_rendering.py",
        "src/capa_simulation/components/availability_gap_panel.py",
        "src/capa_simulation/components/constraint_simulation_view.py",
        "src/capa_simulation/components/process_capa_view.py",
    ):
        source = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert "month_room_px" not in source, relative


def test_the_label_canvas_scrolls_under_its_own_bar_at_the_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """바닥 아래로 좁아진 라벨 컬럼은 캔버스가 바닥 폭을 지키고 스크롤한다. 표가 길어 네이티브
    막대는 표 끝에 떨어지니 월 쪽과 같은 위쪽 막대를 쓰고, 높이가 같아 두 표의 첫 행이 맞는다."""
    from streamlit.testing.v1 import AppTest

    bars: list[dict[str, object]] = []
    monkeypatch.setattr(
        horizontal_scrollbar,
        "render_horizontal_scrollbar",
        lambda **kwargs: bars.append(kwargs),
    )
    app = AppTest.from_function(_split_table_app).run()

    assert not app.exception
    assert [bar["target_selector"] for bar in bars] == [
        ".st-key-demo_label_scroll",
        ".st-key-demo_month_scroll",
    ]
    assert {bar["height"] for bar in bars} == {SCROLLBAR_HEIGHT_PX}
    assert bars[0]["aria_label"] != "월별 데이터 가로 스크롤"
    rules = next(
        element.proto.body
        for element in app.get("html")
        if ".st-key-demo_label_canvas { min-width: 810px !important; }" in element.proto.body
    )
    assert ".st-key-demo_label_scroll {" in rules
    assert "scrollbar-width: none !important;" in rules


def test_home_dashboard_label_width_fits_its_longest_label() -> None:
    """구분 컬럼에는 구획 제목과 가장 긴 행 이름이 함께 들어간다.

    실측(1920px 창, Malgun Gothic 20px): "▍Capa LOB 현황" 159px, "Density (억Gb)" 140px.
    셀 좌우 여백까지 감안해 260px 로 잡았다. 이 값을 줄이면 제목이 다시 잘린다.
    """
    assert DASHBOARD_LABEL_COLUMN_WIDTH_PX >= 200


def test_split_layouts_pin_their_label_column() -> None:
    """분류 + 월 2단 배치를 쓰는 곳은 반드시 폭을 못박아야 한다."""
    owners = {
        "src/capa_simulation/components/monthly_table_base.py",
        "src/capa_simulation/components/home_rendering.py",
    }

    for relative in sorted(owners):
        source = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert "split_scroll_columns_style(" in source, f"{relative} 가 폭을 고정하지 않습니다."


def test_a_narrow_screen_shrinks_the_label_column_only_when_asked() -> None:
    """390px 창에서 260px 라벨 칸이 달 칸에 한 달도 안 되는 폭만 남겼다(E2E r1 #20 — 개선 거리
    I12). 줄 이름 하나짜리 라벨(월 시트 캔버스)만 좁은 창에서 라벨 칸을 줄인다 — 넓은 창 규칙은
    그대로다. 컬럼에 `overflow` 를 걸지 않는다(라벨 칸 풍선이 잘린다)."""
    plain = split_scroll_columns_style(
        label_key="demo_label_canvas", month_key="demo_month_region", label_width_px=260
    )
    narrow = split_scroll_columns_style(
        label_key="demo_label_canvas",
        month_key="demo_month_region",
        label_width_px=260,
        narrow_label_width_px=NARROW_LABEL_COLUMN_WIDTH_PX,
        narrow_viewport_max_px=NARROW_VIEWPORT_MAX_PX,
    )

    assert "@media" not in plain
    assert narrow.startswith(plain.removesuffix("</style>"))
    assert _rules(narrow)[len(_rules(plain)) :] == _rules(
        f"""
        @media (max-width: {NARROW_VIEWPORT_MAX_PX}px) {{
            [data-testid="stColumn"]:has(.st-key-demo_label_canvas) {{
                flex: 0 0 {NARROW_LABEL_COLUMN_WIDTH_PX}px !important;
                width: {NARROW_LABEL_COLUMN_WIDTH_PX}px !important;
                min-width: {NARROW_LABEL_COLUMN_WIDTH_PX}px !important;
            }}
        }}
        """
    )
    # 좁은 라벨 칸 뒤에도 달 칸이 한 달(100px) 넘게 남는다 — 390px 창의 본문 폭(약 327px) 기준.
    assert 327 - NARROW_LABEL_COLUMN_WIDTH_PX > 100
    # 라벨 그림은 `width="stretch"` 라 Streamlit 이 150px 아래로 그리지 않는다 — 칸이 그보다 좁으면
    # 그림이 칸보다 넓게 그려져 오른쪽이 잘린다.
    assert NARROW_LABEL_COLUMN_WIDTH_PX >= PLOTLY_MIN_CHART_WIDTH_PX


def test_the_narrow_rule_needs_its_viewport_width() -> None:
    with pytest.raises(ValueError, match="narrow_viewport_max_px"):
        split_scroll_columns_style(
            label_key="demo_label_canvas",
            month_key="demo_month_region",
            label_width_px=260,
            narrow_label_width_px=NARROW_LABEL_COLUMN_WIDTH_PX,
        )


def test_process_detail_clips_its_label_drawing_at_every_width_but_not_its_tooltip() -> None:
    """공정 Capa 상세는 줄 이름 칸 풍선이 넘치게 라벨 그림의 `overflow` 를 풀되, 그림·글 SVG 는 어느
    창 폭에서나 다시 자르고 풍선 SVG(마지막)만 넘치게 둔다. 풀어 두면 라벨 그림의 바깥 테 · 흰
    바탕이 칸 밖으로 새어 구분 칸이 월 칸 위에 떠 보이고(2026-11-12 사용자 답 k-b3), 좁은 창에서는
    줄 이름이 월 칸 위에 겹친다(개선 거리 I12)."""
    from capa_simulation.components.process_capa_view import (
        LABEL_CHART_KEY,
        label_overflow_style,
    )

    css = label_overflow_style()
    chart = f".st-key-{LABEL_CHART_KEY}"
    assert "@media" not in css
    assert f"{chart} .main-svg {{ overflow: visible !important; }}" in css
    clip = f"{chart} svg.main-svg:not(:last-of-type) {{ overflow: hidden !important; }}"
    # 자르는 규칙이 푸는 규칙 뒤에 와야 이긴다(같은 !important · 더 구체적인 선택자).
    assert css.index(clip) > css.index(f"{chart} .main-svg {{ overflow: visible !important; }}")


def test_month_sheet_canvases_shrink_their_label_on_narrow_screens() -> None:
    """줄 이름 하나짜리 라벨(월 시트 캔버스)인 세 화면만 좁은 창 폭을 넘긴다. 라벨이 여러 분류 칸인
    HOME·월별 표는 넘기지 않는다 — 칸 경계가 비율로 눌려 분류 이름이 겹친다."""
    sheets = {
        "src/capa_simulation/components/process_capa_view.py",
        "src/capa_simulation/components/constraint_simulation_view.py",
        "src/capa_simulation/components/availability_gap_panel.py",
    }
    others = {
        "src/capa_simulation/components/monthly_table_base.py",
        "src/capa_simulation/components/home_rendering.py",
    }

    for relative in sorted(sheets):
        source = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert "narrow_label_width_px=NARROW_LABEL_COLUMN_WIDTH_PX" in source, relative
    for relative in sorted(others):
        source = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert "narrow_label_width_px" not in source, relative
