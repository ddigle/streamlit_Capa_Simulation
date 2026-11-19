# Purpose: 표의 % 칸을 소수 둘째 자리 고정 글로 보이게 하는 한 벌 도우미다(값은 그대로).

"""표의 % 칸은 소수 둘째 자리로 고정한다(125.00% · 605.30% · 0.00% — 2026-11-19 아침 확인
보드 m19-e2e-percent (나) 「앱의 % 표 칸을 한 번에 소수 둘째 자리」, 설계 규칙 UI-DAT-12).

Streamlit 1.63 의 `percent` 꼴은 끝 0 을 지워(605.3% · 125%) 한 표 안에서도 줄마다 자릿수가
다르다. 칸 종류마다 길이 하나씩이다.

- **읽기 표의 수 칸** — `percent_column()` 으로 칸을 적고 `percent_table()` 에 표와 칸 설정을
  함께 넘긴다. 그 칸의 `format` 을 빼고 pandas Styler 표시 글(`percent_cell_text`)을 건다.
  Streamlit 은 읽기 전용이고 `format` 이 없는 칸에서만 Styler 글을 쓴다. **값은 그대로다** —
  칸 정렬은 원값 숫자, 표 도구 막대 CSV · 칸 복사는 원값 분수(0.639551)다. 표 찾기는 지금처럼
  보이는 글에 걸린다.
- **막대 칸** — `percent_progress_column()`(`ProgressColumn` percent + `step` 0.0001). 막대
  칸에는 Styler 글이 닿지 않고, `step` 은 글의 고정 자릿수에만 쓰여 값을 자르지 않는다(막대 ·
  내려받기 그대로).
- **편집 그리드** — 칸 글은 `services.edit_grid.fixed_percent_text`(브라우저 `formatValue`
  쌍둥이)다. 이 모듈의 글도 같은 함수를 부른다 — 반올림이 한 벌이다(반을 0 에서 먼 쪽).

`NumberColumn(format="percent", step=0.0001)` 은 값을 버림해(0.639551 → 63.95%, CSV 도
0.6395) 쓰지 않는다. 값을 100 배 한 표시 열 + `"%.2f%%"` 는 칸 복사 · CSV 가 100 배 수로 나가
쓰지 않는다.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, Final, Literal

import pandas as pd
import streamlit as st

from capa_simulation.services.edit_grid import fixed_percent_text

if TYPE_CHECKING:
    from pandas.io.formats.style import Styler

# 표 % 칸의 소수 자릿수 — 편집 그리드 percent 칸(`ValueFormat("percent", 2)`)과 같은 값이다.
TABLE_PERCENT_DIGITS: Final = 2
# 막대 칸 글의 고정 자릿수 — Streamlit 은 `step` 의 소수 자릿수 − 2 를 % 글 자릿수로 쓴다.
PERCENT_STEP: Final = 10.0 ** -(TABLE_PERCENT_DIGITS + 2)
# Streamlit 기본 수 글(꼴 없는 수 칸)의 소수 자릿수 상한 — `formatNumber` 기본 mantissa 와 같다.
_DEFAULT_MANTISSA: Final = 4

ColumnWidth = Literal["small", "medium", "large"] | int | None


def percent_cell_text(value: object) -> str:
    """% 칸에 보이는 글(분수 값 → 「63.96%」). 빈 값 · 무한대는 빈 글이다(Streamlit `percent`
    꼴이 무한대를 빈칸으로 그리던 것과 같다). 수가 아닌 값은 그 글 그대로다."""
    if value is None or value is pd.NA:
        return ""
    if isinstance(value, str):
        return value
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return ""
    return fixed_percent_text(number, TABLE_PERCENT_DIGITS)


def _default_number_text(value: object) -> str:
    """꼴 없는 실수 칸의 글 — Streamlit 기본 꼴(`formatNumber`: 천 단위 없음 · 소수 넷째
    자리까지 · 끝 0 걷음, 0.0001 보다 작은 수는 첫 유효 자리까지)을 흉내 낸다. Styler 를 건
    표에서는 꼴 없는 칸도 Styler 글(pandas 기본 6자리 — 0.333333 · 1e-7 은 0.000000)로
    그려지므로 이웃 칸이 지금 모습을 지키게 한다."""
    if value is None or value is pd.NA:
        return ""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return ""
    if number == 0 or abs(number) >= 1e-4:
        digits = _DEFAULT_MANTISSA
    else:
        digits = abs(int(f"{number:e}".split("e")[1]))
    quantum = Decimal(1).scaleb(-digits)
    text = format(Decimal(number).quantize(quantum, rounding=ROUND_HALF_UP), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def percent_column(
    label: str | None = None,
    *,
    help: str | None = None,
    width: ColumnWidth = None,
) -> Any:
    """% 칸 설정 — `percent_table()` 에 함께 넘기면 소수 둘째 자리 고정 글이 된다(넘기지 않으면
    지금 `percent` 꼴 그대로). `st.column_config` 는 타입이 아니라 생성 함수라 반환형을 이름으로
    적을 수 없다."""
    return st.column_config.NumberColumn(label, help=help, width=width, format="percent")


def percent_progress_column(
    label: str | None = None,
    *,
    min_value: float,
    max_value: float,
    help: str | None = None,
    width: ColumnWidth = None,
    color: Any = None,
) -> Any:
    """% 막대 칸 설정 — 글은 소수 둘째 자리 고정이고 막대 · 값은 그대로다."""
    return st.column_config.ProgressColumn(
        label,
        help=help,
        width=width,
        format="percent",
        step=PERCENT_STEP,
        min_value=min_value,
        max_value=max_value,
        color=color,
    )


def _number_format(config: object) -> object:
    """수 칸 설정의 `format`(수 칸이 아니면 None)."""
    if not isinstance(config, Mapping):
        return None
    type_config = config.get("type_config")
    if not isinstance(type_config, Mapping) or type_config.get("type") != "number":
        return None
    return type_config.get("format")


def _has_format(config: object) -> bool:
    """칸 설정이 글 꼴을 정하나(수 · 막대 · 날짜 칸의 `format`)."""
    if not isinstance(config, Mapping):
        return False
    type_config = config.get("type_config")
    return isinstance(type_config, Mapping) and bool(type_config.get("format"))


def _without_format(config: Mapping[str, Any]) -> dict[str, Any]:
    """`format` 만 뺀 칸 설정 — 머리 · 풍선 · 폭은 그대로다."""
    type_config = dict(config.get("type_config") or {})
    type_config["format"] = None
    return {**config, "type_config": type_config}


def _styler_uuid(columns: pd.Index) -> str:
    """회차마다 같은 Styler id — pandas 는 Styler 마다 무작위 id 를 지어 회차마다 표를 다시
    보내게 된다. 칸 이름으로 짓는다(칸 꾸밈 글이 없어 표끼리 같아도 겹칠 것이 없다)."""
    names = "\x1f".join(str(name) for name in columns)
    return "pct" + hashlib.sha1(names.encode("utf-8")).hexdigest()[:10]


def percent_table(
    data: pd.DataFrame, column_config: Mapping[str, Any]
) -> tuple[pd.DataFrame | Styler, dict[str, Any]]:
    """`st.dataframe(shown, column_config=config, …)` 에 넘길 (표, 칸 설정).

    `percent_column()` 칸(`format="percent"` 수 칸)이 표에 있으면 그 칸의 `format` 을 빼고
    Styler 표시 글을 건다. 같은 표의 꼴 없는 실수 칸에는 Streamlit 기본 꼴 글을 건다(Styler
    6자리 글이 새지 않게). % 칸이 없거나 표가 Styler 상한(`styler.render.max_elements`)을
    넘으면 받은 그대로다(지금 꼴)."""
    config = dict(column_config)
    percent = [
        name
        for name, settings in config.items()
        if name in data.columns and _number_format(settings) == "percent"
    ]
    if not percent or data.size > int(pd.get_option("styler.render.max_elements")):
        return data, config
    formatters: dict[str, Any] = dict.fromkeys(percent, percent_cell_text)
    for name in data.columns:
        if name in formatters or _has_format(config.get(name)):
            continue
        if pd.api.types.is_float_dtype(data[name]):
            formatters[name] = _default_number_text
    for name in percent:
        config[name] = _without_format(config[name])
    styler = data.style.format(formatters, na_rep="")
    styler.set_uuid(_styler_uuid(data.columns))
    return styler, config
