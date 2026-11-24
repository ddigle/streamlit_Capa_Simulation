# Purpose: 원천 CSV 요약이 목록 표 · 고른 행 · 등록 칸 처음 값 · 메모 조각으로 바뀌는 것을 본다.

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from capa_simulation.components import bigdataquery_registration as registration
from capa_simulation.io.source_csv import SourceCsvCode, SourceCsvSummary
from capa_simulation.services.bigdataquery_catalog_view import (
    REGISTERED_LABEL,
    SAVABLE_LABEL,
    UNREGISTERED_LABEL,
    UNSAVABLE_LABEL,
    CatalogRow,
    registration_prefill,
)
from capa_simulation.services.source_csv_view import (
    REGISTERED_AT_ERROR,
    REGISTERED_AT_PATTERN,
    SAFE_FILE_NAME_LIMIT,
    SOURCE_CSV_DISPLAY_COLUMNS,
    build_source_csv_display_frame,
    code_rows,
    default_pick,
    optional_registered_at,
    safe_file_name,
    source_csv_note,
    source_csv_prefill,
    source_csv_value_line,
)


def _summary(*codes: SourceCsvCode) -> SourceCsvSummary:
    return SourceCsvSummary(
        file_id="demo-file",
        encoding="cp949",
        read_names=(),
        keep_positions=(),
        rows=sum(code.rows for code in codes),
        codes=codes,
    )


def test_display_frame_marks_registered_and_savable_by_stripped_code() -> None:
    """목록 표는 DB 목록과 같은 표지(등록여부 · 저장가능)에 행 수 칸이고, 파일에 없는 시뮬레이션명 ·
    PLAN명 · 원천 등록시각 칸은 없다. 코드는 요약이 앞뒤 공백을 뗀 값이라 그 값으로 맞댄다."""
    summary = _summary(
        SourceCsvCode("DEMO-SIM-1", "DEMO-PLAN-1", 3),
        SourceCsvCode("DEMO-SIM-1", "DEMO-PLAN-2", 2),
        SourceCsvCode("DEMO SIM#2", "DEMO-PLAN-1", 4),
    )

    frame = build_source_csv_display_frame(summary, frozenset({"DEMO-SIM-1"}))

    assert tuple(frame.columns) == SOURCE_CSV_DISPLAY_COLUMNS
    assert frame["등록여부"].tolist() == [REGISTERED_LABEL, REGISTERED_LABEL, UNREGISTERED_LABEL]
    assert frame["저장가능"].tolist() == [SAVABLE_LABEL, SAVABLE_LABEL, UNSAVABLE_LABEL]
    assert frame["시뮬레이션 코드"].tolist() == ["DEMO-SIM-1", "DEMO-SIM-1", "DEMO SIM#2"]
    assert frame["PLAN 코드"].tolist() == ["DEMO-PLAN-1", "DEMO-PLAN-2", "DEMO-PLAN-1"]
    assert frame["행 수"].tolist() == [3, 2, 4]


def test_default_pick_is_the_first_row_only_when_one_code() -> None:
    """코드가 하나면 그 코드의 첫 행(PLAN 이 여럿이어도), 여럿이면 사람이 고른다."""
    one = _summary(SourceCsvCode("DEMO-SIM-1", "P1", 1), SourceCsvCode("DEMO-SIM-1", "P2", 1))
    two = _summary(SourceCsvCode("DEMO-SIM-1", "P1", 1), SourceCsvCode("DEMO-SIM-2", "P1", 1))

    assert default_pick(one) == 0
    assert default_pick(two) is None
    assert default_pick(_summary()) is None


def test_prefill_joins_every_plan_of_the_code() -> None:
    """메모 처음 값은 그 코드의 PLAN 모두를 파일 차례대로 잇는다 — 다른 코드 · 빈 PLAN 은 뺀다."""
    summary = _summary(
        SourceCsvCode("DEMO-SIM-1", "P1", 1),
        SourceCsvCode("DEMO-SIM-2", "P9", 1),
        SourceCsvCode("DEMO-SIM-1", "P2", 1),
        SourceCsvCode("DEMO-SIM-1", "", 1),
    )

    assert source_csv_prefill(summary, "DEMO-SIM-1").note == "원천 PLAN P1 · P2"
    assert source_csv_prefill(_summary(SourceCsvCode("DEMO-SIM-3", "", 1)), "DEMO-SIM-3").note == ""


def test_prefill_names_come_from_the_code_like_the_db_form_with_a_blank_name() -> None:
    """원천 웹 파일 이름에는 시뮬레이션명 · 주차가 없다 — 이름 처음 값은 파일 이름이 아니라 코드다.
    DB 폼이 이름 빈 목록 행을 채우는 꼴(원천명 = 코드, 시나리오명 「<원천명> (<코드>)」)과 같고,
    리비전명은 같은 처음 값, 등록시점은 빈칸이다."""
    summary = _summary(SourceCsvCode("DEMO-SIM-1", "P1", 1))
    db = registration_prefill(
        CatalogRow("DEMO-SIM-1", "", "P1", "", "", True), catalog_window_label="(합성)"
    )

    prefill = source_csv_prefill(summary, "DEMO-SIM-1")

    assert prefill.simulation_code == "DEMO-SIM-1"
    assert (prefill.source_name, prefill.scenario_name) == (db.source_name, db.scenario_name)
    assert prefill.scenario_name == "DEMO-SIM-1 (DEMO-SIM-1)"
    assert prefill.revision_name == db.revision_name
    assert prefill.registered_at == ""


def test_code_rows_add_every_plan_of_the_code() -> None:
    summary = _summary(
        SourceCsvCode("DEMO-SIM-1", "P1", 3),
        SourceCsvCode("DEMO-SIM-2", "P1", 5),
        SourceCsvCode("DEMO-SIM-1", "P2", 4),
    )

    assert code_rows(summary, "DEMO-SIM-1") == 7
    assert code_rows(summary, "DEMO-SIM-9") == 0


def test_value_line_counts_codes_and_rows() -> None:
    """목록 위 값 줄은 코드 수와 행 수다 — 파일 이름은 올림 칸 칩 · 메모가 말해 거듭하지 않는다."""
    summary = _summary(
        SourceCsvCode("DEMO-SIM-1", "P1", 1200),
        SourceCsvCode("DEMO-SIM-1", "P2", 34),
        SourceCsvCode("DEMO-SIM-2", "P1", 1),
    )

    assert source_csv_value_line(summary) == "**원천 CSV** · 코드 2 · 1,235행"


def test_note_names_the_file_and_custom_kinds() -> None:
    """리비전 메모는 적은 메모 뒤 「CSV 파일 <이름>」 · 「CUSTOM 파일 값 — 종류 n」 이다. 적은
    메모가 비면 그 조각은 없다."""
    assert (
        source_csv_note(" 원천 PLAN P1 ", "DEMO_원천.csv", 2)
        == "원천 PLAN P1 · CSV 파일 DEMO_원천.csv · CUSTOM 파일 값 — 종류 2"
    )
    assert source_csv_note("", "C:\\받은 파일\\DEMO.csv", 0) == (
        "CSV 파일 DEMO.csv · CUSTOM 파일 값 — 종류 0"
    )
    assert source_csv_note("메모", "\x00", 1) == "메모 · CSV 파일 · CUSTOM 파일 값 — 종류 1"


def test_safe_file_name_drops_paths_and_control_characters() -> None:
    assert safe_file_name("folder/sub/DEMO.csv") == "DEMO.csv"
    assert safe_file_name("C:\\Users\\demo\\DEMO.csv") == "DEMO.csv"
    assert safe_file_name("DE\x00MO\t\n.csv") == "DEMO.csv"
    assert safe_file_name("  DEMO.csv  ") == "DEMO.csv"
    long = "가" * (SAFE_FILE_NAME_LIMIT + 10) + ".csv"
    assert safe_file_name(long) == "가" * SAFE_FILE_NAME_LIMIT


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "2026-11-24",
        "2026-11-24 09:30",
        "2026-11-24 09:30:15",
        " 2026-11-24T09:30:15 ",
        "2026/11/24",
        "어제",
        "2026-13-01",
    ],
)
def test_optional_registered_at_matches_the_db_form_rule(text: str) -> None:
    """원천 등록시점 판정은 DB 폼(`_optional_datetime`)과 같은 값을 낸다 — 거절 글만 「원천 DB」 가
    아니라 「원천」 등록시점이다. 칸 검증 정규식도 DB 폼과 같은 글자다."""
    try:
        expected: datetime | None | str = registration._optional_datetime(text)
    except ValueError:
        expected = "거절"
    try:
        got: datetime | None | str = optional_registered_at(text)
    except ValueError as error:
        assert str(error) == REGISTERED_AT_ERROR
        got = "거절"

    assert got == expected
    if isinstance(got, datetime):
        assert got.date() == date(2026, 11, 24)


def test_the_registered_at_field_pattern_is_the_db_form_pattern() -> None:
    """CSV 등록 칸의 검증 정규식은 DB 폼 칸에 박힌 정규식과 같은 글자다(하나로 모으기는 1.0.x)."""
    source = Path(registration.__file__).read_text(encoding="utf-8")
    assert f'r"{REGISTERED_AT_PATTERN}"' in source
