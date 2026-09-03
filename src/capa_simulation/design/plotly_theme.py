# Purpose: Plotly Figure의 배경·서체·여백 공통 레이아웃을 토큰에서 생성한다.

"""Shared Plotly layout built from the design tokens.

Figure마다 배경색과 서체를 다시 선언하면 화면끼리 조용히 갈라진다. 여기서 한 번 만든
레이아웃을 넘기고, Figure별로 다른 값만 덧붙인다.
"""

from __future__ import annotations

from typing import Any, Final

from capa_simulation.design import tokens

DEFAULT_MARGIN: Final[dict[str, int]] = {"l": 20, "r": 20, "t": 20, "b": 30}


def base_layout(
    *,
    height: int | None = None,
    margin: dict[str, int] | None = None,
    font_size: int = 12,
    transparent: bool = False,
    **overrides: Any,
) -> dict[str, Any]:
    """공통 배경·서체·여백을 담은 `update_layout` 인자를 만든다.

    `transparent=True`는 표처럼 페이지 배경 위에 그대로 얹는 Figure에 쓴다.
    """
    background = "rgba(0,0,0,0)" if transparent else tokens.SURFACE
    layout: dict[str, Any] = {
        "paper_bgcolor": background,
        "plot_bgcolor": background,
        "font": chart_font(size=font_size),
        "margin": dict(margin) if margin is not None else dict(DEFAULT_MARGIN),
    }
    if height is not None:
        layout["height"] = height
    layout.update(overrides)
    return layout


def chart_font(*, size: int = 12, color: str | None = None) -> dict[str, Any]:
    """차트·축·범례용 서체 지정을 만든다."""
    return {"family": tokens.FONT_FAMILY, "color": color or tokens.TEXT, "size": size}


def table_font(
    *, size: int = 12, color: str | None = None, numeric: bool = False
) -> dict[str, Any]:
    """표 셀용 서체 지정을 만든다. `numeric=True`는 숫자 정렬용 서체를 앞세운다."""
    family = tokens.FONT_FAMILY_NUMERIC if numeric else tokens.FONT_FAMILY
    return {"family": family, "color": color or tokens.TEXT, "size": size}
