# Purpose: 상세 B/N 가로막대의 길이 정규화와 월 열 그리드 계약을 고정한다.

import unicodedata
from typing import Any, cast

import pandas as pd
import pytest

from capa_simulation.components.home_dimensions import (
    BOTTLENECK_DETAIL_HEADER_HEIGHT_PX,
    BOTTLENECK_DETAIL_ROW_HEIGHT_PX,
)
from capa_simulation.components.home_figures import (
    BOTTLENECK_DETAIL_RANK_LIMIT,
    BOTTLENECK_NAME_ELLIPSIS,
    BOTTLENECK_NAME_INSET_RATIO,
    BOTTLENECK_NAME_MIN_FONT_PX,
    bottleneck_bar_ratio,
    bottleneck_name_layout,
    build_bottleneck_detail_figures,
)
from capa_simulation.design import tokens

MONTH_LABELS = ["26.01", "26.02", "26.03"]


@pytest.mark.parametrize(
    ("rate", "expected"),
    [
        # 확보율은 비율이다. 0.80 미만은 막대가 보이지 않고 1.50 이상은 꽉 찬다.
        (0.0, 0.0),
        (0.799, 0.0),
        (0.80, 0.0),
        (0.85, 0.5 / 7),
        (1.15, 0.5),
        (1.50, 1.0),
        (1.501, 1.0),
        (3.0, 1.0),
    ],
)
def test_bar_ratio_clamps_to_the_80_to_150_percent_band(rate: float, expected: float) -> None:
    assert bottleneck_bar_ratio(rate) == pytest.approx(expected)


def test_bar_ratio_treats_a_missing_rate_as_no_bar() -> None:
    """소요대수 0 이면 확보율이 NaN 이다. 막대를 그리지 않는다."""
    assert bottleneck_bar_ratio(float("nan")) == 0.0
    assert bottleneck_bar_ratio(None) == 0.0


def _details(rows: list[tuple[str, int, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": [202600 + int(month.split(".")[1]) for month, _, _, _ in rows],
            "년월": [month for month, _, _, _ in rows],
            "순위": [rank for _, rank, _, _ in rows],
            "공정": [process for _, _, process, _ in rows],
            "확보율": [rate for _, _, _, rate in rows],
            "가용대수": [10.0 for _ in rows],
            "소요대수": [20.0 for _ in rows],
            "Wafer Capa": [1_000.0 for _ in rows],
        }
    )


def _build(details: pd.DataFrame) -> tuple[object, object]:
    return build_bottleneck_detail_figures(
        monthly_bottleneck_details=details,
        month_labels=MONTH_LABELS,
        secure_threshold=1.095,
        warning_threshold=0.995,
    )


def _rank_labels(label_figure: object) -> list[str]:
    """순위 라벨은 표 칸이 아니라 주석으로 그린다. 머리글 주석만 빼고 순서대로 읽는다."""
    figure = cast(Any, label_figure)
    return [
        annotation.text
        for annotation in figure.layout.annotations
        if annotation.text != "<b>B/N</b>"
    ]


def test_month_figure_keeps_the_fixed_month_column_grid() -> None:
    """세 개의 월 Figure 가 같은 스크롤 캔버스에 들어가므로 폭 규칙이 같아야 한다."""
    label_figure, month_figure = _build(
        _details([("26.01", 1, "DEMO_공정", 0.5), ("26.02", 1, "DEMO_공정", 1.2)])
    )

    assert month_figure.layout.width == len(MONTH_LABELS) * tokens.MONTH_COLUMN_WIDTH_PX
    assert month_figure.layout.xaxis.range == (0, len(MONTH_LABELS))
    # 좌측 라벨 Figure 는 폭을 주지 않고 CSS 가 잡는다. 높이는 정확히 같아야 한다.
    assert label_figure.layout.width is None
    assert label_figure.layout.height == month_figure.layout.height


def test_row_count_follows_the_month_with_the_most_processes() -> None:
    label_figure, month_figure = _build(
        _details(
            [
                ("26.01", 1, "DEMO_A", 0.5),
                ("26.01", 2, "DEMO_B", 0.9),
                ("26.01", 3, "DEMO_C", 1.6),
                ("26.02", 1, "DEMO_D", 0.7),
            ]
        )
    )

    # 제목 자리는 Figure 밖이다. `상세 B/N 공정` 은 Streamlit 이 그리므로 Figure 높이는
    # 표 높이 그대로다.
    expected_height = BOTTLENECK_DETAIL_HEADER_HEIGHT_PX + 3 * BOTTLENECK_DETAIL_ROW_HEIGHT_PX
    assert month_figure.layout.height == expected_height
    # 순위 숫자는 표 칸이 아니라 주석이다. 칸에 글자를 넣으면 Plotly 가 29px 행을
    # `글자상자 + 16px` 로 부풀려 월 Figure 와 어긋난다.
    assert set(label_figure.data[0].cells.values[0]) == {""}
    assert _rank_labels(label_figure) == ["1", "2", "3"]


def test_rank_limit_is_the_twenty_row_screen_contract() -> None:
    """20 은 화면 계약이다. `docs/TODO.md` 가 `순위 1~20` 으로 못 박아 두었고 행 높이도
    20행이 한 화면에 들어가도록 잡혀 있으므로, 상수 자신이 아니라 숫자로 고정한다.
    """
    assert BOTTLENECK_DETAIL_RANK_LIMIT == 20


def test_row_count_trusts_the_frame_the_service_already_cut() -> None:
    """순위 상한은 서비스가 정본이다. Figure 는 다시 자르지 않고 받은 프레임을 그린다."""
    details = _details(
        [
            ("26.01", rank, f"DEMO_{rank}", 1.0)
            for rank in range(1, BOTTLENECK_DETAIL_RANK_LIMIT + 1)
        ]
    )

    label_figure, _ = _build(details)

    assert _rank_labels(label_figure) == [
        str(rank) for rank in range(1, BOTTLENECK_DETAIL_RANK_LIMIT + 1)
    ]
    # 칸은 끝까지 비어 있어야 29px 행이 유지된다.
    assert set(label_figure.data[0].cells.values[0]) == {""}


def test_month_figure_draws_hover_target_track_bars_and_names_in_four_traces() -> None:
    """이름은 annotation 이 아니라 배열 `text` 를 실은 trace 하나로 그린다."""
    _, month_figure = _build(
        _details(
            [
                ("26.01", 1, "DEMO_부족", 0.5),
                ("26.01", 2, "DEMO_확보", 1.2),
            ]
        )
    )

    hover_target, track, bar, names = month_figure.data
    # hover 표적은 칸마다 하나씩 있고 행 전체 높이를 덮는다. 막대가 0 길이여도, 칸
    # 가장자리에 마우스를 올려도 값이 뜬다.
    assert len(hover_target.x) == 2
    assert hover_target.width == BOTTLENECK_DETAIL_ROW_HEIGHT_PX
    assert hover_target.marker.color == tokens.HIT_TARGET
    # 여섯 값 + 실행 Capa 조정 줄. 조정이 없으면 마지막 칸이 빈 문자열이라 아무 줄도
    # 붙지 않는다.
    assert hover_target.hovertemplate.count("customdata") == 7
    # 보이는 트랙 막대는 눈금만 담당한다.
    assert track.marker.color == tokens.BAR_TRACK
    assert track.hoverinfo == "skip"
    # 80% 미만인 1순위는 막대를 그리지 않는다.
    assert len(bar.x) == 1
    assert bar.marker.color == (tokens.STATUS_SECURE,)
    assert bar.marker.line.width == tokens.BAR_OUTLINE_WIDTH_PX
    assert bar.marker.line.width >= tokens.GRID_LINE_WIDTH_PX
    assert bar.hoverinfo == "skip"
    assert names.mode == "text"
    assert len(names.text) == 2
    assert all("DEMO_" in text for text in names.text)
    # 칸마다 annotation 을 만들지 않는다. annotation 은 머리글 월 라벨뿐이고 개수는
    # 조회 월 수와 같다.
    assert len(month_figure.layout.annotations) == len(MONTH_LABELS)


def _details_with_execution(
    rows: list[tuple[str, int, str, float, float, float, str]],
) -> pd.DataFrame:
    """`기준 확보율`·`확보율 증감`·`실행 비고` 를 실은 상세 프레임."""
    base = _details([(label, rank, process, rate) for label, rank, process, rate, *_ in rows])
    base["기준 확보율"] = [baseline for *_, baseline, _delta, _note in rows]
    base["확보율 증감"] = [delta for *_, _baseline, delta, _note in rows]
    base["실행 비고"] = [note for *_, note in rows]
    return base


def test_no_adjustment_keeps_the_original_four_traces() -> None:
    """조정 0건이면 trace 구성이 조정 전과 같아야 한다.

    빈 trace 를 늘 끼우면 「조정이 없으면 오늘과 픽셀 단위로 같다」가 무너진다.
    """
    _, month_figure = _build(
        _details_with_execution([("26.01", 1, "DEMO_공정", 1.0, 1.0, 0.0, "")])
    )

    assert len(month_figure.data) == 4


def test_a_decrease_paints_the_lost_span_without_a_border() -> None:
    """줄어든 만큼은 테두리 없는 적분홍이고, 테두리는 줄어든 결과값에만 남는다."""
    _, month_figure = _build(
        _details_with_execution([("26.01", 1, "DEMO_공정", 1.0, 1.2, -20.0, "비가동 3대")])
    )

    # hover 표적 · 트랙 · 증감 영역 · 값 막대 · 공정명
    assert len(month_figure.data) == 5
    delta = month_figure.data[2]
    assert delta.marker.color == (tokens.DELTA_AREA_DECREASE,)
    assert delta.marker.line.width == 0
    value_bar = month_figure.data[3]
    # 줄어든 쪽은 값 막대가 곧 결과값이므로 제 테두리를 그대로 쓴다. 증가 행이 없으니
    # 굵기는 스칼라로 남는다.
    assert value_bar.marker.line.width == tokens.BAR_OUTLINE_WIDTH_PX


def test_an_increase_borders_the_whole_new_value_including_the_green_span() -> None:
    """늘어난 경우 테두리는 연두 영역까지 두르고, 값 막대 자신의 테두리는 꺼진다."""
    _, month_figure = _build(
        _details_with_execution([("26.01", 1, "DEMO_공정", 1.2, 1.0, 20.0, "UPEH 개선")])
    )

    # hover 표적 · 트랙 · 증감 영역 · 값 막대 · 증가 테두리 · 공정명
    assert len(month_figure.data) == 6
    delta = month_figure.data[2]
    assert delta.marker.color == (tokens.DELTA_AREA_INCREASE,)
    assert delta.marker.line.width == 0
    value_bar = month_figure.data[3]
    assert value_bar.marker.line.width == (0.0,)
    outline = month_figure.data[4]
    assert outline.marker.color == tokens.TRANSPARENT
    assert outline.marker.line.width == tokens.BAR_OUTLINE_WIDTH_PX
    # 테두리는 값 막대보다 길다 — 연두 구간을 품는다.
    assert outline.x[0] > value_bar.x[0]


def test_hover_carries_the_adjustment_and_the_note() -> None:
    """가용·필요대수는 기준정보 값 그대로다. 어긋나 보이는 까닭을 hover 가 밝힌다."""
    _, month_figure = _build(
        _details_with_execution([("26.01", 1, "DEMO_공정", 1.0, 1.2, -20.0, "비가동 3대")])
    )

    note = month_figure.data[0].customdata[0][6]

    assert "실행 반영 -20.0%p" in note
    assert "비고 비가동 3대" in note


def test_hover_escapes_markup_in_the_note() -> None:
    """비고는 자유 텍스트다. 꺾쇠가 그대로 들어가면 hover 마크업이 깨진다."""
    _, month_figure = _build(
        _details_with_execution([("26.01", 1, "DEMO_공정", 1.0, 1.2, -20.0, "<b>주의</b>")])
    )

    note = month_figure.data[0].customdata[0][6]

    assert "&lt;b&gt;" in note
    assert "<b>주의" not in note


def test_hover_shows_the_real_rate_above_the_bar_cap() -> None:
    """막대만 150% 에서 잘린다. hover 숫자는 실제 값 그대로다."""
    _, month_figure = _build(_details([("26.01", 1, "DEMO_공정", 2.0)]))

    hover_target = month_figure.data[0]
    assert list(hover_target.customdata[0]) == [
        "26.01",
        "DEMO_공정",
        "200.0%",
        "10.0대",
        "20.0대",
        "1K",
        # 실행 Capa 조정이 없으면 빈 문자열이라 hover 에 아무 줄도 붙지 않는다.
        "",
    ]


def test_both_axes_are_fixed_so_hover_does_not_enable_drag_zoom() -> None:
    """`staticPlot` 을 끄면 드래그 확대가 켜진다. 축 고정이 그 유일한 방어다."""
    _, month_figure = _build(_details([("26.01", 1, "DEMO_공정", 1.0)]))

    assert month_figure.layout.xaxis.fixedrange is True
    assert month_figure.layout.yaxis.fixedrange is True
    assert month_figure.layout.dragmode is False


def _rendered_width_px(text: str, font_size: int) -> float:
    """전각 1.0·반각 0.6 폭단위로 잰 렌더 폭."""
    units = sum(
        1.0 if unicodedata.east_asian_width(character) in {"F", "W"} else 0.6 for character in text
    )
    return units * font_size


# 사내 실제 공정명 표본. 앞의 것은 반각 24자라 글자 크기가 최소값 바닥에 걸린다.
SAMPLE_PROCESS_NAMES = ("Laser_Grooving_Front_HCB", "공 Tape Mount_HCB")


@pytest.mark.parametrize("process", SAMPLE_PROCESS_NAMES)
def test_process_name_fits_inside_one_month_cell(process: str) -> None:
    """`go.Scatter` 의 text 는 줄바꿈도 칸 단위 클립도 없다. 칸 안에 들어가야 한다."""
    display_text, font_size = bottleneck_name_layout(process)

    available_px = tokens.MONTH_COLUMN_WIDTH_PX * (1.0 - BOTTLENECK_NAME_INSET_RATIO)
    assert _rendered_width_px(display_text, font_size) <= available_px


def test_a_long_process_name_is_ellipsized_at_the_minimum_font_size() -> None:
    """글자 크기를 더 줄일 수 없으면 말줄임이 남은 한 단계다."""
    display_text, font_size = bottleneck_name_layout("Laser_Grooving_Front_HCB")

    assert font_size == BOTTLENECK_NAME_MIN_FONT_PX
    assert display_text.endswith(BOTTLENECK_NAME_ELLIPSIS)
    assert "Laser_Grooving_Front_HCB".startswith(display_text[: -len(BOTTLENECK_NAME_ELLIPSIS)])


def test_a_name_that_already_fits_is_not_ellipsized() -> None:
    display_text, _ = bottleneck_name_layout("공 Tape Mount_HCB")

    assert display_text == "공 Tape Mount_HCB"


def test_hover_keeps_the_full_process_name_even_when_the_label_is_cut() -> None:
    """잘리는 것은 칸 안의 라벨뿐이다. 전체 이름은 hover 에 그대로 뜬다."""
    long_name = "Laser_Grooving_Front_HCB"
    _, month_figure = _build(_details([("26.01", 1, long_name, 1.0)]))

    hover_target, *_, names = month_figure.data
    assert hover_target.customdata[0][1] == long_name
    assert BOTTLENECK_NAME_ELLIPSIS in names.text[0]


def _horizontal_boundaries(figure: object) -> list[tuple[float, float, str]]:
    """`y0 == y1` 인 수평 경계선만 추려 (위치, 굵기, 색) 으로 만든다.

    표 안쪽(`0 < y < 1`)만 본다. 위·아래 바깥 테두리는 좌측 라벨 쪽만 왼쪽 변을 강조해
    그리는 자리라 두 Figure 가 일부러 다르다.
    """
    return [
        (shape.y0, shape.line.width, shape.line.color)
        for shape in cast(Any, figure).layout.shapes
        if shape.type == "line" and shape.y0 == shape.y1 and 0.0 < shape.y0 < 1.0
    ]


def test_both_figures_share_the_same_horizontal_row_boundaries() -> None:
    """좌우 세로 정렬의 근거는 두 Figure 가 같은 경계 shape 을 쓰는 것 하나다.

    높이가 같아도 한쪽 shape 만 손대면 순위 숫자와 막대의 행 선이 어긋난다.
    """
    label_figure, month_figure = _build(
        _details(
            [
                ("26.01", 1, "DEMO_A", 0.5),
                ("26.01", 2, "DEMO_B", 1.2),
                ("26.02", 3, "DEMO_C", 1.6),
            ]
        )
    )

    label_boundaries = _horizontal_boundaries(label_figure)
    month_boundaries = _horizontal_boundaries(month_figure)

    # 머리글 밑줄 + 행 사이 격자선이 모두 있어야 비교가 의미를 갖는다.
    assert len(label_boundaries) >= 3
    assert label_boundaries == month_boundaries
