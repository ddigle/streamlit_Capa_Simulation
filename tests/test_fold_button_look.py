# Purpose: 설비 마스터와 Space 의 접힌 칸 떠 있는 단추가 같은 생김인지 두 자산을 맞대 본다.

"""접힌 칸의 떠 있는 단추(2026-11-05 검수 eqp-side-01 — 설계 규칙 UI-LAY-09).

두 편집기는 부품이 다르다 — Space 는 편집기 안 모든 단추가 쓰는 `.sle button` 꼴 위에 면 색만
더하고, 설비 마스터는 칸막이 마운트의 `.ess-rail` 이 제 꼴을 적는다. 자산을 하나로 묶을 수 없어
값을 맞댄다 — 한쪽만 고치면 여기서 실패한다(UI-CON-03 · 04). 값은 옛 미배치 서랍 단추 꼴이다.
"""

from __future__ import annotations

import re
from pathlib import Path

from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components import space_layout_editor as space

COMPONENTS = Path(__file__).resolve().parents[1] / "src/capa_simulation/components"
MASTER_CSS = (COMPONENTS / "equipment_master_grid_assets/splitter.css").read_text(encoding="utf-8")
SPACE_CSS = (COMPONENTS / "space_layout_editor_assets/editor.css").read_text(encoding="utf-8")
# 두 팔레트 이름 → 뜻. 값은 아래에서 같은 토큰인지 본다.
MASTER_COLORS = {
    "var(--ess-border)": "border",
    "var(--ess-surface)": "surface",
    "var(--ess-text)": "text",
    "var(--ess-accent)": "accent",
}
SPACE_COLORS = {
    "var(--sle-border)": "border",
    "var(--sle-surface)": "surface",
    "var(--sle-ui-text)": "text",
    "var(--sle-accent)": "accent",
}
# 설비 마스터 편집기 영역의 안쪽 여백 — 단추의 자리 기준(칸 끝)이 여기까지 들어와 있다.
FRAME_PADDING_PX = 13
FLOAT_INSET_PX = 8


def _block(css: str, selector: str) -> dict[str, str]:
    match = re.search(rf"(?m)^{re.escape(selector)} \{{(?P<body>[^}}]*)\}}", css)
    assert match, selector
    declarations = (part.partition(":") for part in match.group("body").split(";") if part.strip())
    return {name.strip(): value.strip() for name, _, value in declarations}


def _named(props: dict[str, str], colors: dict[str, str]) -> dict[str, str]:
    """값의 팔레트 변수 이름을 뜻으로 바꾼다 — 접두가 달라도 같은 칸이면 같은 글자다."""
    named = {}
    for name, value in props.items():
        for variable, meaning in colors.items():
            value = value.replace(variable, meaning)
        named[name] = value
    return named


def _master_look() -> dict[str, str]:
    rail = _named(_block(MASTER_CSS, ".ess-rail"), MASTER_COLORS)
    weight, size_line, _family = rail.pop("font").split(" ", 2)
    size, line = size_line.split("/")
    return {
        **{name: rail[name] for name in _LOOK if name in rail},
        "font-weight": weight,
        "font-size": size,
        "line-height": line,
    }


def _space_look() -> dict[str, str]:
    button = _named(_block(SPACE_CSS, ".sle button"), SPACE_COLORS)
    strip = _named(_block(SPACE_CSS, ".sle button.sle-side-strip"), SPACE_COLORS)
    merged = {**button, **strip}
    return {name: merged[name] for name in (*_LOOK, "font-weight", "font-size", "line-height")}


_LOOK = (
    "height",
    "padding",
    "border",
    "border-radius",
    "background",
    "color",
    "white-space",
    "align-items",
    "justify-content",
    "gap",
    "cursor",
)


def test_the_two_floating_buttons_have_the_same_look() -> None:
    assert _master_look() == _space_look()
    assert _master_look()["height"] == "27px"
    assert "box-shadow" not in _block(MASTER_CSS, ".ess-rail")
    assert "box-shadow" not in _block(SPACE_CSS, ".sle button")


def test_the_two_floating_buttons_react_the_same_way() -> None:
    assert _named(_block(MASTER_CSS, ".ess-rail:hover"), MASTER_COLORS) == _named(
        _block(SPACE_CSS, ".sle button:hover"), SPACE_COLORS
    )
    assert _named(_block(MASTER_CSS, ".ess-rail:focus-visible"), MASTER_COLORS) == _named(
        _block(SPACE_CSS, ".sle button:focus-visible"), SPACE_COLORS
    )


def test_the_two_palettes_give_the_same_colors() -> None:
    master = emg._splitter_palette()
    editor = space._palette()

    assert master["border"] == editor["border"]
    assert master["surface"] == editor["surface"]
    assert master["text"] == editor["ui-text"]
    assert master["accent"] == editor["accent"]


def test_both_float_eight_pixels_inside_their_editor() -> None:
    """설비 마스터 단추의 자리 기준은 영역 안쪽 여백 안이라 음수로 나가 영역 끝에서 8px 이다."""
    rail = _block(MASTER_CSS, ".ess-rail")
    outset = FRAME_PADDING_PX - FLOAT_INSET_PX

    assert rail["top"] == rail["right"] == f"-{outset}px"
    floating = _block(SPACE_CSS, ".sle-body > .sle-side.is-min")
    assert floating["top"] == f"{FLOAT_INSET_PX}px"
    assert _block(SPACE_CSS, ".sle-body > .sle-side.is-min.is-right")["right"] == (
        f"{FLOAT_INSET_PX}px"
    )
