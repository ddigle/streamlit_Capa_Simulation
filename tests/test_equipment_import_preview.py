# Purpose: 붙여넣기 오류의 행 단위 귀속 컴포넌트 관련 정상·예외·회귀 동작을 검증한다.

from collections.abc import Callable
from functools import partial

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components.equipment_import_preview import (
    OK_MARK,
    PINNED_COLUMNS,
    ROW_COLUMN,
    VERDICT_COLUMN,
    attribute_row_errors,
    build_preview_table,
    error_rows_csv,
    parse_raw_rows,
)
from capa_simulation.services.equipment_csv import (
    read_downtime_clipboard,
    read_equipment_clipboard,
)
from capa_simulation.services.equipment_samples import sample_equipment_master

_STATUS_COLUMN = "확정상태"
_INVALID_STATUS = "없는상태"


def _fleet(rows: int) -> pd.DataFrame:
    """데모 fleet 리터럴을 호기 접미로 늘려 원하는 행 수를 만든다(합성 표본)."""
    parts: list[pd.DataFrame] = []
    made = 0
    batch = 0
    while made < rows:
        part = sample_equipment_master().copy()
        part["호기"] = part["호기"].astype(str) + f"-{batch:02d}"
        parts.append(part)
        made += len(part)
        batch += 1
    return pd.concat(parts, ignore_index=True).head(rows)


def _tsv(frame: pd.DataFrame) -> str:
    return frame.to_csv(sep="\t", index=False).strip("\r\n")


def _corrupt_rows(text: str, row_numbers: tuple[int, ...]) -> str:
    """1-based 행 번호의 `확정상태` 칸을 허용값 밖으로 바꾼다(그 행만의 잘못)."""
    lines = text.splitlines()
    column_index = lines[0].split("\t").index(_STATUS_COLUMN)
    for number in row_numbers:
        cells = lines[number].split("\t")
        cells[column_index] = _INVALID_STATUS
        lines[number] = "\t".join(cells)
    return "\n".join(lines)


def _counting(
    parser: Callable[[str], pd.DataFrame], calls: list[str]
) -> Callable[[str], pd.DataFrame]:
    def wrapped(text: str) -> pd.DataFrame:
        calls.append(text)
        return parser(text)

    return wrapped


def test_clean_paste_returns_the_frame_and_no_errors() -> None:
    text = _tsv(_fleet(12))
    calls: list[str] = []

    result = attribute_row_errors(text, _counting(read_equipment_clipboard, calls))

    assert result.ok
    assert result.frame is not None
    assert len(result.frame) == 12
    assert result.row_errors == []
    assert result.frame_error is None
    assert result.row_count == 12
    # 통과하면 파서를 한 번만 부른다. 행마다 다시 부르는 것은 실패했을 때뿐이다.
    assert len(calls) == 1


def test_two_bad_rows_are_attributed_to_their_one_based_numbers() -> None:
    text = _corrupt_rows(_tsv(_fleet(10)), (3, 7))

    result = attribute_row_errors(text, read_equipment_clipboard)

    assert not result.ok
    assert result.frame is None
    assert result.error_row_numbers == [3, 7]
    # 메시지는 파서가 낸 문장 그대로다 — 이 모듈이 규칙을 다시 적지 않는다.
    assert all(_STATUS_COLUMN in message for _, message in result.row_errors)
    # 행에 붙였으면 프레임 오류로 또 알리지 않는다.
    assert result.frame_error is None
    assert result.row_count == 10


def test_duplicate_equipment_id_is_a_frame_level_error_without_row_numbers() -> None:
    fleet = _fleet(6)
    duplicated = pd.concat([fleet, fleet.iloc[[0]]], ignore_index=True)

    result = attribute_row_errors(_tsv(duplicated), read_equipment_clipboard)

    # 한 행씩은 전부 통과한다 — 호기 중복은 행을 넘나드는 규칙이다.
    assert result.row_errors == []
    assert result.frame_error is not None
    assert "호기는 중복될 수 없습니다" in result.frame_error
    assert result.row_count == 7


def test_missing_header_column_does_not_paint_every_row_red() -> None:
    lines = _tsv(_fleet(5)).splitlines()
    column_index = lines[0].split("\t").index(_STATUS_COLUMN)
    lines = ["\t".join(_drop(line.split("\t"), column_index)) for line in lines]
    calls: list[str] = []

    result = attribute_row_errors("\n".join(lines), _counting(read_equipment_clipboard, calls))

    assert result.row_errors == []
    assert result.frame_error is not None
    assert _STATUS_COLUMN in result.frame_error
    # 전체 한 번 + 헤더만 한 번. 행은 하나도 다시 부르지 않는다.
    assert len(calls) == 2


def test_binary_search_finds_the_same_rows_as_the_row_by_row_pass() -> None:
    text = _corrupt_rows(_tsv(_fleet(40)), (4, 31))
    linear_calls: list[str] = []
    bisect_calls: list[str] = []

    linear = attribute_row_errors(
        text, _counting(read_equipment_clipboard, linear_calls), max_row_parse=100
    )
    bisect = attribute_row_errors(
        text, _counting(read_equipment_clipboard, bisect_calls), max_row_parse=8
    )

    assert linear.error_row_numbers == [4, 31]
    assert bisect.row_errors == linear.row_errors
    # 이분 탐색은 실패한 구간만 내려간다 — 전수보다 호출이 적어야 값이 있다.
    assert len(bisect_calls) < len(linear_calls)


def test_binary_search_reports_a_cross_row_rule_as_a_frame_error() -> None:
    fleet = _fleet(40)
    duplicated = pd.concat([fleet, fleet.iloc[[0]]], ignore_index=True)

    result = attribute_row_errors(_tsv(duplicated), read_equipment_clipboard, max_row_parse=8)

    assert result.row_errors == []
    assert result.frame_error is not None
    assert "호기는 중복될 수 없습니다" in result.frame_error


def test_downtime_without_a_master_equipment_is_attributed_to_its_row() -> None:
    fleet = _fleet(3)
    downtime = pd.DataFrame(
        {
            "호기": [fleet["호기"].iloc[0], "없는호기", fleet["호기"].iloc[1]],
            "비가동유형": ["고장", "고장", "고장"],
            "시작일": ["2026-10-01", "2026-10-01", "2026-10-02"],
            "종료일": ["2026-10-03", "2026-10-03", "2026-10-04"],
            "상세사유": ["", "", ""],
            "비고": ["", "", ""],
        }
    )

    result = attribute_row_errors(_tsv(downtime), partial(read_downtime_clipboard, equipment=fleet))

    # 마스터 대조는 행마다 도는 검사라 그 행에 붙는다 — 이름으로 분류하지 않는다.
    assert result.error_row_numbers == [2]


def test_preview_table_pins_the_verdict_columns_and_lifts_error_rows() -> None:
    text = _corrupt_rows(_tsv(_fleet(5)), (4,))
    result = attribute_row_errors(text, read_equipment_clipboard)
    raw = parse_raw_rows(text)
    assert raw is not None

    table = build_preview_table(raw, result)

    assert tuple(table.columns[:2]) == PINNED_COLUMNS
    assert table[ROW_COLUMN].tolist() == [4, 1, 2, 3, 5]
    assert _STATUS_COLUMN in str(table[VERDICT_COLUMN].iloc[0])
    assert table[VERDICT_COLUMN].tolist()[1:] == [OK_MARK] * 4
    # 판정 두 칸을 빼면 붙여넣은 표 그대로다.
    assert list(table.columns[2:]) == list(raw.columns)


def test_error_rows_csv_keeps_the_pasted_lines_as_they_were() -> None:
    text = _corrupt_rows(_tsv(_fleet(5)), (2, 5))
    result = attribute_row_errors(text, read_equipment_clipboard)

    payload = error_rows_csv(text, result.error_row_numbers).decode("utf-8-sig")

    lines = payload.strip("\n").splitlines()
    pasted = text.splitlines()
    assert lines == [pasted[0], pasted[2], pasted[5]]


def test_blank_lines_do_not_shift_the_row_numbers() -> None:
    lines = _corrupt_rows(_tsv(_fleet(4)), (3,)).splitlines()
    text = "\n".join([lines[0], lines[1], "", lines[2], lines[3], "", lines[4]])

    result = attribute_row_errors(text, read_equipment_clipboard)

    assert result.row_count == 4
    assert result.error_row_numbers == [3]


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_paste_is_a_frame_error(text: str) -> None:
    result = attribute_row_errors(text, read_equipment_clipboard)

    assert result.row_errors == []
    assert result.frame_error is not None
    assert result.row_count == 0


def test_render_import_errors_draws_the_summary_and_one_download() -> None:
    app = AppTest.from_string(
        """
import pandas as pd

from capa_simulation.components.equipment_import_preview import (
    ImportPreviewResult,
    render_import_errors,
)

render_import_errors(
    ImportPreviewResult(
        frame=None,
        row_errors=[
            (3, "확정상태는 계획·확정·완료·지연 중 하나여야 합니다"),
            (7, "제진대·물류·입고·Qual 일정 순서가 올바르지 않습니다"),
        ],
        frame_error=None,
        row_count=10,
        source_text="호기\\t확정상태\\nA\\t계획\\nB\\t계획\\nC\\t없는상태\\nD\\t계획\\nE\\t계획\\nF\\t계획\\nG\\t없는상태\\nH\\t계획\\nI\\t계획\\nJ\\t계획",
    )
)
""",
        default_timeout=30,
    ).run()

    assert not app.exception
    assert any("2행에 오류" in element.value for element in app.error)
    assert len(app.expander) == 1
    assert len(app.download_button) == 1
    listed = [element.value for element in app.markdown]
    assert any("**3행**" in value for value in listed)
    assert any("**7행**" in value for value in listed)


def test_render_import_errors_states_a_cross_row_rule_without_a_download() -> None:
    app = AppTest.from_string(
        """
from capa_simulation.components.equipment_import_preview import (
    ImportPreviewResult,
    render_import_errors,
)

render_import_errors(
    ImportPreviewResult(
        frame=None,
        row_errors=[],
        frame_error="호기는 중복될 수 없습니다: ['SAM01']",
        row_count=4,
        source_text="호기\\nSAM01\\nSAM01",
    )
)
""",
        default_timeout=30,
    ).run()

    assert not app.exception
    assert any("호기는 중복될 수 없습니다" in element.value for element in app.error)
    # 어느 행의 잘못도 아니므로 목록도 내려받기도 그리지 않는다.
    assert len(app.expander) == 0
    assert len(app.download_button) == 0


def _drop(cells: list[str], index: int) -> list[str]:
    return [cell for position, cell in enumerate(cells) if position != index]
