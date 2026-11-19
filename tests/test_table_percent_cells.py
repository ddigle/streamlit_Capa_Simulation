# Purpose: 표의 % 칸이 소수 둘째 자리 고정 글이고 값은 그대로인지와 그 꼴의 그물을 지킨다.

"""표의 % 칸은 소수 둘째 자리 고정이다(2026-11-19 아침 확인 보드 m19-e2e-percent (나) 「앱의 % 표
칸을 한 번에 소수 둘째 자리」 — 설계 규칙 UI-DAT-12).

두 겹으로 본다. ① 도우미(`components/percent_cells.py`) — 보이는 글 · 이웃 칸 글 · 표시만 바뀌는
것(데이터는 그대로라 칸 정렬은 원값 숫자, 표 도구 막대 CSV · 칸 복사는 원값 분수) · 상한을 넘는
표 · 회차마다 같은 표 꼴. ② 그물 — 화면 코드가 도우미 밖에서 `percent` 칸 꼴이나 끝 0 을 지우는
% 꼴을 쓰지 않고, `percent_column` 을 쓴 화면은 `percent_table` 로 그리고, 편집 그리드 percent 칸은
같은 자릿수 · 같은 글 함수를 쓴다.
"""

from __future__ import annotations

import ast
import math
import re
import warnings
from pathlib import Path

import pandas as pd
import pytest
from pandas.io.formats.style import Styler
from source_sites import PROJECT_ROOT, called_name, relative, screen_calls, screen_files
from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df
from streamlit.elements.lib.pandas_styler_utils import marshall_styler
from streamlit.proto.ArrowData_pb2 import ArrowData

from capa_simulation.components import edit_grid as grid_component
from capa_simulation.components.percent_cells import (
    PERCENT_STEP,
    TABLE_PERCENT_DIGITS,
    _default_number_text,
    percent_cell_text,
    percent_column,
    percent_progress_column,
    percent_table,
)
from capa_simulation.services import edit_grid as eg

HELPER = "src/capa_simulation/components/percent_cells.py"
# 2026-11-19 보드 답의 합성 예 — 지금 꼴(끝 0 지움)과 바뀐 꼴.
VALUES = (5.8448, 6.053, 1.25, 0.639551, 12.3456, -0.1093, 0.0, 0.1755, 0.5844599, 0.00125)
TEXTS = (
    "584.48%",
    "605.30%",
    "125.00%",
    "63.96%",
    "1,234.56%",
    "-10.93%",
    "0.00%",
    "17.55%",
    "58.45%",
    "0.13%",
)
# 결정이 있어 남긴 % 수 꼴(파일, 꼴) — 확보율차이는 「보이는 두 확보율의 차」 검산 · 퍼센트 포인트
# 기호 금지 결정과 묶인 첫째 자리 · 부호 꼴이다(`tests/test_percent_unit_text.py`).
KEPT_PRINTF = {("src/capa_simulation/components/availability_gap_panel.py", "%+.1f%%")}
FIXED_PRINTF = re.compile(rf"^%[+ ,]*\.{TABLE_PERCENT_DIGITS}f%%$")


def _shown(styler: pd.DataFrame | Styler, column: str) -> list[str]:
    """Streamlit 이 싣는 Styler 표시 글(칸 `column`)."""
    assert isinstance(styler, Styler)
    proto = ArrowData()
    marshall_styler(proto, styler, "default")
    table = convert_arrow_bytes_to_pandas_df(proto.styler.display_values)
    return [str(value) for value in table[column]]


def test_percent_text_is_two_fixed_decimals_with_grouping_and_sign() -> None:
    assert tuple(percent_cell_text(value) for value in VALUES) == TEXTS
    assert percent_cell_text(-1e-6) == "-0.00%", "0 아래 작은 수는 부호를 남긴다(지금 Intl 꼴)"
    assert percent_cell_text(-0.0) == "0.00%"
    for empty in (None, math.nan, pd.NA, math.inf, -math.inf):
        assert percent_cell_text(empty) == "", empty


def test_the_read_table_text_and_the_grid_text_are_one_function() -> None:
    """반올림이 한 벌이다 — 읽기 표 % 칸과 편집 그리드 percent 칸(브라우저 `formatValue` 쌍둥이)."""
    fmt = eg.ValueFormat("percent", TABLE_PERCENT_DIGITS)
    for value in (*VALUES, 0.01005, 0.98765, 1 / 3, -0.00005, 2.675, 100.0):
        assert percent_cell_text(value) == eg.format_value(value, fmt), value


def test_neighbour_numbers_keep_the_streamlit_default_look() -> None:
    """Styler 를 건 표의 꼴 없는 실수 칸 — Streamlit 기본 꼴(천 단위 없음 · 소수 넷째 자리
    까지 · 끝 0 걷음, 아주 작은 수는 첫 유효 자리까지)이고 pandas 6자리 글(0.333333 ·
    0.000000)이 아니다."""
    cases = {
        1 / 3: "0.3333",
        2.5: "2.5",
        1234.5678: "1234.5678",
        16.1666666: "16.1667",
        12.0: "12",
        0.0: "0",
        -0.5: "-0.5",
        1e-7: "0.0000001",
        0.0001: "0.0001",
    }
    assert {value: _default_number_text(value) for value in cases} == cases
    assert _default_number_text(None) == "" and _default_number_text(math.nan) == ""


def _mixed() -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "공정": ["DEMO-A", "DEMO-B", None, "DEMO-D"],
            "확보율": [6.053, None, 0.639551, -0.1093],
            "소요대수": [12.0, 1 / 3, None, 1e-7],
            "대수": [1, 22, 333, 4444],
            "배치": [1.5, 2.25, 3.0, 4.0],
            "날짜": pd.to_datetime(["2027-01-01", "2027-02-01", "2027-03-01", "2027-04-01"]),
        },
        index=[3, 7, 11, 15],
    )
    return frame


def test_percent_table_writes_fixed_text_and_leaves_the_data_alone() -> None:
    """표시만 바뀐다 — 칸 정렬 · 도구 막대 CSV · 칸 복사는 표 데이터(원값 분수)를 쓰므로
    그대로다."""
    frame = _mixed()
    before = frame.copy()
    shown, config = percent_table(
        frame,
        {
            "확보율": percent_column("확보율 (%)", help="풍선", width="small"),
            "배치": {"type_config": {"type": "number", "format": "localized"}},
        },
    )
    assert isinstance(shown, Styler)
    pd.testing.assert_frame_equal(shown.data, before)  # type: ignore[attr-defined]
    pd.testing.assert_frame_equal(frame, before)
    rate = config["확보율"]
    assert rate["type_config"]["format"] is None
    assert (rate["label"], rate["help"], rate["width"]) == ("확보율 (%)", "풍선", "small")
    assert _shown(shown, "확보율") == ["605.30%", "", "63.96%", "-10.93%"]
    assert _shown(shown, "소요대수") == ["12", "0.3333", "", "0.0000001"]
    assert _shown(shown, "대수") == ["1", "22", "333", "4444"], "정수 칸은 기본 글 그대로"


def test_percent_table_is_the_same_bytes_every_run() -> None:
    """회차마다 같은 표 꼴 — pandas 의 무작위 Styler id 로 표를 다시 보내지 않는다."""

    def styler_bytes() -> bytes:
        shown, _ = percent_table(_mixed(), {"확보율": percent_column()})
        assert isinstance(shown, Styler)
        proto = ArrowData()
        marshall_styler(proto, shown, "default")
        return bytes(proto.styler.SerializeToString())

    assert styler_bytes() == styler_bytes()


def test_percent_table_falls_back_to_the_plain_table_past_the_styler_limit() -> None:
    """Styler 상한을 넘는 표 · % 칸이 없는 표는 받은 그대로다(지금 `percent` 꼴)."""
    frame = _mixed()
    with pd.option_context("styler.render.max_elements", frame.size - 1):
        shown, config = percent_table(frame, {"확보율": percent_column()})
    assert shown is frame and config["확보율"]["type_config"]["format"] == "percent"
    plain, plain_config = percent_table(frame, {"공정": {"label": "공정"}})
    assert plain is frame and plain_config == {"공정": {"label": "공정"}}


def test_the_bar_column_fixes_its_text_without_cutting_the_value() -> None:
    """막대 칸 — Streamlit 은 `step` 의 소수 자릿수 − 2 를 % 글 자릿수로 쓴다(값은 자르지 않음)."""
    config = percent_progress_column(min_value=0.0, max_value=1.5, width="small")
    type_config = config["type_config"]
    assert (type_config["type"], type_config["format"]) == ("progress", "percent")
    assert type_config["step"] == PERCENT_STEP == 0.0001
    assert (type_config["min_value"], type_config["max_value"]) == (0.0, 1.5)
    assert TABLE_PERCENT_DIGITS == len(str(PERCENT_STEP).split(".")[1]) - 2


def _column_calls() -> list[tuple[str, int, ast.Call]]:
    return [
        (path, call.lineno, call)
        for path, _outer, _file, _scope, call in screen_calls(screen_files(exclude=(HELPER,)))
        if called_name(call).endswith("Column")
    ]


def _format_keyword(call: ast.Call) -> object:
    for keyword in call.keywords:
        if keyword.arg == "format" and isinstance(keyword.value, ast.Constant):
            return keyword.value.value
    return None


def test_no_screen_writes_a_percent_column_outside_the_helper() -> None:
    """칸 설정 `format="percent"`(끝 0 을 지우는 꼴)는 도우미 안에만 있다 — 새 표의 % 칸은
    `percent_column` · `percent_progress_column` 으로 적는다."""
    offenders = [
        f"{path}:{line}"
        for path, line, call in _column_calls()
        if _format_keyword(call) == "percent"
    ]
    assert offenders == []


def test_printf_percent_columns_keep_two_fixed_decimals() -> None:
    """100 배 한 값을 「…%%」 로 적는 칸도 소수 둘째 자리 고정이다(결정이 있는 확보율차이만
    남김)."""
    found = {
        (path, text)
        for path, _line, call in _column_calls()
        if isinstance(text := _format_keyword(call), str) and text.endswith("%%")
    }
    assert {item for item in found if not FIXED_PRINTF.match(item[1])} == KEPT_PRINTF


def test_screens_that_declare_percent_columns_draw_through_the_helper() -> None:
    """`percent_column` 칸은 `percent_table` 을 거쳐야 고정 글이 된다 — 거치지 않으면 지금 꼴
    그대로다. 칸을 적은 화면 파일은 `percent_table` 도 부른다."""
    declared: set[str] = set()
    drawn: set[str] = set()
    for path, _outer, _file, _scope, call in screen_calls(screen_files(exclude=(HELPER,))):
        if called_name(call) == "percent_column":
            declared.add(path)
        if called_name(call) == "percent_table":
            drawn.add(path)
    assert declared, "그물이 볼 자리가 있다"
    assert declared <= drawn, sorted(declared - drawn)


def _value_format_digits() -> list[tuple[str, int, object]]:
    roots = [*screen_files(), *sorted((PROJECT_ROOT / "scripts").rglob("*.py"))]
    found: list[tuple[str, int, object]] = []
    for path in roots:
        with warnings.catch_warnings():
            # 옛 독스트링의 역슬래시 경고는 이 그물의 일이 아니다.
            warnings.simplefilter("ignore")
            tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and called_name(node) == "ValueFormat"):
                continue
            args = node.args
            if args and isinstance(args[0], ast.Constant) and args[0].value == "percent":
                second = args[1] if len(args) > 1 else None
                digits = second.value if isinstance(second, ast.Constant) else None
                found.append((relative(path), node.lineno, digits))
    return found


def test_grid_percent_columns_use_the_table_digits() -> None:
    """편집 그리드 percent 칸(기준 정보 효율 · 여유율 · 측정률, 생산 계획 수율)도 같은 자릿수다."""
    found = _value_format_digits()
    assert found, "그물이 볼 자리가 있다"
    assert [item for item in found if item[2] != TABLE_PERCENT_DIGITS] == []


def test_the_browser_grid_text_does_not_strip_percent_zeros() -> None:
    """브라우저 `formatValue` 의 percent 갈래는 끝 0 을 걷지 않는다(쌍둥이 사례는
    `tests/fixtures/edit_grid_cases.json` 의 `format`)."""
    source = Path(PROJECT_ROOT, "src/capa_simulation/components/edit_grid_assets/eg_pure.js")
    lines = [
        line
        for line in source.read_text(encoding="utf-8").splitlines()
        if "fmt.kind === 'percent'" in line and "formatValue" not in line and "return" in line
    ]
    shown = [line for line in lines if "number * 100" in line]
    assert len(shown) == 1 and "stripZeros" not in shown[0], shown


@pytest.mark.parametrize("value", [0.9875, 0.85, 1.0, 0.0])
def test_the_grid_bound_text_and_edit_text_keep_their_short_look(value: float) -> None:
    """상한 오류 글(「100% 이하로」)과 칸 편집기 처음 글은 칸 글이 아니다 — 끝 0 없이 그대로."""
    fmt = eg.ValueFormat("percent", 2, max_value=value)
    spec = eg.GridSpec("RQ_DEMO", "효율", ("공정",), ("202701",), fmt)
    texts = grid_component.texts(spec, changes_label="적용 전 변경")
    expected = {0.9875: "98.75%", 0.85: "85%", 1.0: "100%", 0.0: "0%"}[value]
    assert texts["errors"]["max"].startswith(f"{expected} 이하로 적습니다")
    assert texts["errors"]["min"] == "0% 이상으로 적습니다"
