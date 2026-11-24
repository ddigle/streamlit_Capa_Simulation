# Purpose: 원천 CSV 요약(인코딩 · 머리 · 칸 수 · 코드)과 고른 코드 행 읽기를 합성 견본으로 본다.

from __future__ import annotations

import dataclasses
import io
import random

import pandas as pd
import pytest
from source_csv_samples import (
    DEMO_CODE,
    contract_names,
    demo_core_rows,
    file_columns,
    header_line,
    row_line,
    source_csv_bytes,
)

from capa_simulation.io.core_data_source import (
    core_data_hash,
    load_core_data_contract,
    normalize_core_data,
)
from capa_simulation.io.source_csv import (
    BROKEN_LINE_TAIL,
    CHANGED_FILE_TEXT,
    COLUMNS_TAIL,
    DECODE_TEXT,
    EMPTY_FILE_TEXT,
    HEADER_ONLY_TEXT,
    SOURCE_CSV_ENCODINGS,
    SOURCE_CSV_EXTRA_COLUMNS,
    SourceCsvCode,
    SourceCsvError,
    SourceCsvSummary,
    _fold_header,
    read_source_csv_rows,
    summarize_source_csv,
)
from capa_simulation.services.builtin_seed import build_builtin_core_data

WIDTH = len(file_columns())


def _summary(data: bytes) -> SourceCsvSummary:
    return summarize_source_csv(io.BytesIO(data), file_id="demo-file")


def _stop(data: bytes) -> str:
    with pytest.raises(SourceCsvError) as caught:
        _summary(data)
    return str(caught.value)


def _read(data: bytes, code: str = DEMO_CODE) -> pd.DataFrame:
    buffer = io.BytesIO(data)
    summary = summarize_source_csv(buffer, file_id="demo-file")
    return read_source_csv_rows(buffer, summary, code)


def _fields(line: str) -> list[str]:
    # 견본 값에는 쉼표 · 따옴표가 없어 쉼표로 나눠도 칸이 맞다.
    return line.split(",")


# ---------------------------------------------------------------- 기본 · 남는 열 · 머리


def test_summary_reads_a_cp949_crlf_file_with_some_quoted_headers() -> None:
    rows = demo_core_rows()
    data = source_csv_bytes(rows)
    assert data.startswith(header_line().encode("cp949") + b"\r\n")
    assert b'"Capa Code"' in data and b'"PLAN ID"' in data

    buffer = io.BytesIO(data)
    summary = summarize_source_csv(buffer, file_id="demo-file")

    assert summary.file_id == "demo-file"
    assert summary.encoding == "cp949"
    assert summary.rows == len(rows)
    assert {code.code for code in summary.codes} == {DEMO_CODE}
    assert sum(code.rows for code in summary.codes) == len(rows)
    frame = read_source_csv_rows(buffer, summary, DEMO_CODE)
    assert list(frame.columns) == contract_names()
    assert len(frame) == len(rows)
    # 같은 합성 값을 표로 바로 정규화한 것과 원천 해시까지 같다(글자 · 결측 · 실수 모두).
    seed = build_builtin_core_data()
    seed["시뮬레이션 ID"] = DEMO_CODE
    assert core_data_hash(normalize_core_data(frame)) == core_data_hash(normalize_core_data(seed))


def test_the_three_extra_columns_are_dropped_without_a_stop() -> None:
    rows = demo_core_rows(5)
    columns = file_columns()
    buffer = io.BytesIO(source_csv_bytes(rows))
    summary = summarize_source_csv(buffer, file_id="demo-file")

    extra_positions = [columns.index(name) for name in SOURCE_CSV_EXTRA_COLUMNS]
    assert not set(extra_positions) & set(summary.keep_positions)
    assert len(summary.keep_positions) == len(contract_names())
    assert all(summary.read_names[position] not in columns for position in extra_positions)
    frame = read_source_csv_rows(buffer, summary, DEMO_CODE)
    assert not set(SOURCE_CSV_EXTRA_COLUMNS) & set(frame.columns)
    # 남는 열 셋이 없는 파일도 읽는다 — 알리지도 막지도 않는 열이다.
    assert len(_read(source_csv_bytes(rows, extra_columns=False))) == len(rows)


def test_unknown_and_missing_columns_are_named_in_one_stop() -> None:
    names = contract_names()
    renamed = names[2:14]
    override = {name: f"DEMO_NEW_{index:02d}" for index, name in enumerate(renamed)}
    text = _stop(source_csv_bytes(demo_core_rows(3), header_override=override))

    unknown = " · ".join(f"DEMO_NEW_{index:02d}" for index in range(10))
    missing = " · ".join(renamed[:10])
    assert text == (
        f"앱이 모르는 열: {unknown} 외 2개 · Core Data 열 가운데 없는 열: {missing} 외 2개 "
        f"— {COLUMNS_TAIL}"
    )
    assert "앱 관리자(개발자)에게" in text


def test_an_unknown_column_alone_is_named_without_a_missing_part() -> None:
    # 남는 열은 없어도 되므로 그 머리를 바꾸면 모르는 열만 남는다.
    text = _stop(source_csv_bytes(demo_core_rows(3), header_override={"공식여부": "DEMO_NEW"}))
    assert text == f"앱이 모르는 열: DEMO_NEW — {COLUMNS_TAIL}"


def test_headers_match_ignoring_case_and_spaces() -> None:
    override = {
        "Capa Code": "  capa   CODE ",
        "PLAN ID": "plan id",
        "시뮬레이션 ID": " 시뮬레이션  id",
        "공식여부": "공식여부 ",
    }
    rows = demo_core_rows(4)
    frame = _read(source_csv_bytes(rows, header_override=override))
    assert list(frame.columns) == contract_names()
    assert frame["Capa Code"].tolist() == [row["Capa Code"] for row in rows]


def test_folded_duplicate_headers_stop() -> None:
    text = _stop(source_csv_bytes(demo_core_rows(3), header_override={"Customer": "capa  CODE"}))
    assert text == "같은 열 이름이 둘 이상 있습니다: Capa Code"


def test_a_literally_repeated_header_stops_as_duplicate() -> None:
    # pandas 라면 둘째가 「Capa Code.1」 로 바뀌어 모르는 열로 샜을 머리다 — 날 머리로 본다.
    text = _stop(source_csv_bytes(demo_core_rows(3), header_override={"Customer": "Capa Code"}))
    assert text == "같은 열 이름이 둘 이상 있습니다: Capa Code"
    assert "모르는 열" not in text


def test_a_trailing_comma_column_without_values_is_dropped() -> None:
    rows = demo_core_rows(4)
    data = source_csv_bytes(rows, trailing_comma=True)
    assert data.split(b"\r\n")[0].endswith(b",")
    buffer = io.BytesIO(data)
    summary = summarize_source_csv(buffer, file_id="demo-file")
    assert len(summary.read_names) == WIDTH + 1
    assert WIDTH not in summary.keep_positions
    frame = read_source_csv_rows(buffer, summary, DEMO_CODE)
    assert list(frame.columns) == contract_names()
    assert len(frame) == len(rows)


def test_an_unnamed_column_with_values_is_an_unknown_column() -> None:
    rows = demo_core_rows(3)
    lines = [header_line(trailing_comma=True)]
    lines += [row_line(row, trailing_comma=True) for row in rows[:2]]
    lines.append(row_line(rows[2]) + ",DEMO_VALUE")
    text = _stop("".join(line + "\r\n" for line in lines).encode("cp949"))
    assert text == f"앱이 모르는 열: 이름 없는 열({WIDTH + 1}번째 칸) — {COLUMNS_TAIL}"


def test_contract_and_extra_names_fold_to_distinct_keys() -> None:
    # 공백 · 대소문자를 접어 맞추므로 접은 꼴이 겹치면 바른 파일이 겹친 머리로 멈춘다.
    names = [*contract_names(), *SOURCE_CSV_EXTRA_COLUMNS]
    assert len({_fold_header(name) for name in names}) == len(names)


def test_the_encodings_try_utf8_first_and_end_with_the_contract_encoding() -> None:
    assert SOURCE_CSV_ENCODINGS[0] == "utf-8-sig"
    assert SOURCE_CSV_ENCODINGS[-1] == load_core_data_contract().encoding


# ---------------------------------------------------------------- 값 읽기 계약


def test_numeric_columns_read_back_the_exact_floats() -> None:
    """숫자 열은 `round_trip` 으로 읽어 글자가 적은 실수를 비트까지 돌려받는다.

    `float_precision="round_trip"` 을 빼면(pandas 기본 빠른 꼴) 이 견본의 여러 값이 마지막
    비트에서 어긋나 실패한다 — 변이로 확인했다. 기대값은 파이썬 `float(글자)`(바르게 반올림)다.
    """
    rng = random.Random(20261124)
    rows = demo_core_rows()
    columns = ("소요대수", "WF측정률", "UPEH", "편중률", "설비보유HCB", "Lot 측정률")
    texts: dict[str, list[str]] = {column: [] for column in columns}
    for index, row in enumerate(rows):
        for column in columns:
            value = rng.uniform(0.001, 100.0) * 10.0 ** rng.randint(-9, 4)
            if index % 7 == 0:
                # 원천 웹 꼴 — 대문자 E · 0 채움 없는 지수(E-5 꼴).
                text = f"{rng.randint(1, 99)}.{rng.randint(1, 999)}E-{rng.randint(1, 9)}"
            elif index % 7 == 1:
                # 실수가 담는 유효 자릿수(17)보다 긴 고정 소수 글자.
                text = format(rng.uniform(0.001, 100.0), f".{rng.randint(18, 40)}f")
            else:
                text = repr(value)
            row[column] = text
            texts[column].append(text)
    frame = _read(source_csv_bytes(rows))
    for column in columns:
        assert frame[column].dtype == "float64"
        read = [float.hex(float(value)) for value in frame[column]]
        assert read == [float.hex(float(text)) for text in texts[column]], column


def test_only_empty_cells_are_missing_and_na_words_stay_text() -> None:
    words = ["NA", "null", "None", "N/A", "nan", "NULL", ""]
    rows = demo_core_rows(len(words))
    for row, word in zip(rows, words, strict=True):
        row["Customer"] = word
        row["소요대수"] = "" if word == "" else "1.5"
    frame = _read(source_csv_bytes(rows))
    assert frame["Customer"].iloc[:-1].tolist() == words[:-1]
    assert frame["Customer"].isna().tolist() == [False] * (len(words) - 1) + [True]
    assert frame["소요대수"].isna().tolist() == [False] * (len(words) - 1) + [True]


def test_text_columns_keep_percent_and_leading_zeros() -> None:
    rows = demo_core_rows(3)
    rows[0].update({"Family4": "50%", "U/6": "%", "Customer": "DEMO 10%", "MCP_SEQ": "007"})
    rows[1].update({"MCP_SEQ": "0012A", "STEP_SEQ": "0100"})
    frame = normalize_core_data(_read(source_csv_bytes(rows)))
    first = frame.iloc[0]
    assert [first["Family4"], first["U/6"], first["Customer"], first["MCP_SEQ"]] == [
        "50%",
        "%",
        "DEMO 10%",
        "007",
    ]
    second = frame.iloc[1]
    assert [second["MCP_SEQ"], second["STEP_SEQ"]] == ["0012A", "0100"]


# ---------------------------------------------------------------- 코드 · 행


def test_two_codes_list_both_and_rows_read_only_the_picked_code() -> None:
    first = demo_core_rows(6)
    second = demo_core_rows(4, code="DEMO-SIM-2")
    rows = [*first[:3], *second, *first[3:]]
    buffer = io.BytesIO(source_csv_bytes(rows))
    summary = summarize_source_csv(buffer, file_id="demo-file")

    per_code: dict[str, int] = {}
    for code in summary.codes:
        per_code[code.code] = per_code.get(code.code, 0) + code.rows
    assert per_code == {DEMO_CODE: 6, "DEMO-SIM-2": 4}
    assert summary.codes[0].code == DEMO_CODE
    picked = read_source_csv_rows(buffer, summary, "DEMO-SIM-2")
    assert picked["시뮬레이션 ID"].tolist() == ["DEMO-SIM-2"] * 4
    assert picked["PLAN ID"].tolist() == [row["PLAN ID"] for row in second]


def test_blank_simulation_id_rows_stop() -> None:
    rows = demo_core_rows(5)
    rows[1]["시뮬레이션 ID"] = ""
    rows[3]["시뮬레이션 ID"] = "   "
    assert _stop(source_csv_bytes(rows)) == "시뮬레이션 ID 가 빈 행이 2개 있어 읽지 않았습니다."


def test_a_header_only_file_stops() -> None:
    assert _stop(source_csv_bytes([])) == HEADER_ONLY_TEXT
    assert _stop(source_csv_bytes([], raw_lines={0: ""})) == HEADER_ONLY_TEXT


@pytest.mark.parametrize(
    "data",
    [b"", b"\xef\xbb\xbf", b"\r\n\r\n", b"\xef\xbb\xbf\r\n \r\n"],
    ids=["zero-bytes", "bom-only", "blank-lines", "bom-and-blank-lines"],
)
def test_an_empty_file_stops(data: bytes) -> None:
    assert _stop(data) == EMPTY_FILE_TEXT


def test_summary_and_rows_match_on_the_stripped_simulation_id() -> None:
    rows = demo_core_rows(6)
    for row in rows[::2]:
        row["시뮬레이션 ID"] = f" {DEMO_CODE} "
    buffer = io.BytesIO(source_csv_bytes(rows))
    summary = summarize_source_csv(buffer, file_id="demo-file")
    assert {code.code for code in summary.codes} == {DEMO_CODE}
    assert sum(code.rows for code in summary.codes) == len(rows)
    picked = read_source_csv_rows(buffer, summary, f"  {DEMO_CODE}")
    # DB 조회는 코드와 같은 값의 행만 받는다 — 남긴 행의 시뮬레이션 ID 도 뗀 값이다.
    assert picked["시뮬레이션 ID"].tolist() == [DEMO_CODE] * len(rows)


def test_a_code_with_two_plans_lists_two_rows() -> None:
    rows = demo_core_rows(7)
    for index, row in enumerate(rows):
        row["PLAN ID"] = "DEMO-P1" if index < 4 else " DEMO-P2"
    buffer = io.BytesIO(source_csv_bytes(rows))
    summary = summarize_source_csv(buffer, file_id="demo-file")
    assert summary.codes == (
        SourceCsvCode(DEMO_CODE, "DEMO-P1", 4),
        SourceCsvCode(DEMO_CODE, "DEMO-P2", 3),
    )
    assert len(read_source_csv_rows(buffer, summary, DEMO_CODE)) == len(rows)


# ---------------------------------------------------------------- 인코딩 · 줄 꼴


def test_a_utf8_bom_file_reads() -> None:
    rows = demo_core_rows(4)
    for index, row in enumerate(rows):
        row["설비대여평가DESC"] = f"합성 값 {index}"
    data = source_csv_bytes(rows, encoding="utf-8-sig")
    assert data.startswith(b"\xef\xbb\xbf")
    buffer = io.BytesIO(data)
    summary = summarize_source_csv(buffer, file_id="demo-file")
    assert summary.encoding == "utf-8-sig"
    frame = read_source_csv_rows(buffer, summary, DEMO_CODE)
    assert list(frame.columns) == contract_names()
    assert frame["설비대여평가DESC"].tolist() == [row["설비대여평가DESC"] for row in rows]


def test_undecodable_bytes_stop_with_the_encoding_text() -> None:
    data = b"\xff\xfe" + source_csv_bytes(demo_core_rows(2))
    for encoding in SOURCE_CSV_ENCODINGS:
        with pytest.raises(UnicodeDecodeError):
            data.split(b"\r\n")[0].decode(encoding)
    assert _stop(data) == DECODE_TEXT


def test_a_utf8_header_with_a_bad_byte_in_the_first_chunk_stops_without_trying_cp949() -> None:
    rows = demo_core_rows(3)
    rows[1]["설비대여평가DESC"] = "합성 값"
    lines = [header_line().encode("utf-8")]
    lines += [row_line(row).encode("utf-8") for row in rows[:1]]
    # 머리는 UTF-8 로 풀리고, 둘째 행만 CP949 바이트다 — 첫 덩이(8KB) 안이다.
    lines += [row_line(row).encode("cp949") for row in rows[1:]]
    data = b"".join(line + b"\r\n" for line in lines)
    assert len(data) < 8192
    with pytest.raises(SourceCsvError) as caught:
        _summary(data)
    assert str(caught.value) == DECODE_TEXT
    # 머리 줄로 UTF-8 을 정한 뒤 그 디코더가 깨진 바이트를 만났다 — CP949 로 다시 읽지 않았다.
    cause = caught.value.__cause__
    assert isinstance(cause, UnicodeDecodeError)
    assert cause.encoding == "utf-8"


def test_a_truncated_last_line_stops_with_its_line_number() -> None:
    rows = demo_core_rows(5)
    truncated = ",".join(_fields(row_line(rows[4]))[:-2])
    text = _stop(source_csv_bytes(rows[:4], raw_lines={4: truncated}))
    assert text == (
        f"6번째 줄의 칸 수가 머리와 다릅니다(머리 {WIDTH}칸 · 그 줄 {WIDTH - 2}칸) "
        "— 잘렸거나 손으로 고친 줄이 있습니다."
    )


def test_a_first_data_line_with_one_more_field_stops_instead_of_shifting() -> None:
    rows = demo_core_rows(4)
    longer = row_line(rows[0]) + ",DEMO_VALUE"
    data = source_csv_bytes(rows[1:], raw_lines={0: longer})
    text = _stop(data)
    assert text.startswith(
        f"2번째 줄의 칸 수가 머리와 다릅니다(머리 {WIDTH}칸 · 그 줄 {WIDTH + 1}칸)"
    )
    # pandas 는 이 줄을 오류 없이 받는다 — 칸 수 검사는 요약 한 곳이다. 둘째 방어
    # (`index_col=False`)는 열이 한 칸씩 밀리지 않게만 막는다.
    clean = io.BytesIO(source_csv_bytes(rows))
    summary = summarize_source_csv(clean, file_id="demo-file")
    shifted = read_source_csv_rows(io.BytesIO(data), summary, DEMO_CODE)
    assert shifted["시뮬레이션 ID"].tolist() == [DEMO_CODE] * len(rows)


def test_a_middle_line_with_more_fields_stops() -> None:
    rows = demo_core_rows(6)
    longer = row_line(rows[2]) + ",DEMO_VALUE"
    truncated = ",".join(_fields(row_line(rows[4]))[:-1])
    data = source_csv_bytes(
        [rows[0], rows[1], rows[3], rows[5]], raw_lines={2: longer, 3: truncated}
    )
    assert _stop(data) == (
        f"4번째 줄의 칸 수가 머리와 다릅니다(머리 {WIDTH}칸 · 그 줄 {WIDTH + 1}칸) 외 1줄 "
        "— 잘렸거나 손으로 고친 줄이 있습니다."
    )


def test_a_quoted_newline_counts_as_one_record() -> None:
    rows = demo_core_rows(4)
    rows[1]["설비대여평가DESC"] = "합성\r\n두 줄"
    data = source_csv_bytes(rows)
    assert b'"' + "합성\r\n두 줄".encode("cp949") + b'"' in data
    buffer = io.BytesIO(data)
    summary = summarize_source_csv(buffer, file_id="demo-file")
    assert summary.rows == len(rows)
    frame = read_source_csv_rows(buffer, summary, DEMO_CODE)
    assert len(frame) == len(rows)
    assert "두 줄" in str(frame.loc[1, "설비대여평가DESC"])


def _broken_text(line: int) -> str:
    return f"{line}번째 줄을 읽지 못했습니다 — {BROKEN_LINE_TAIL}"


def test_an_unclosed_quote_on_the_last_line_stops_on_upload() -> None:
    rows = demo_core_rows(5)
    fields = _fields(row_line(rows[4]))
    unclosed = ",".join([*fields[:-1], '"' + fields[-1]])
    # 칸 수는 머리와 같다 — 따옴표가 줄 끝을 삼킨 채 파일이 끝난다.
    assert len(fields) == WIDTH
    assert _stop(source_csv_bytes(rows[:4], raw_lines={4: unclosed})) == _broken_text(6)


def test_an_unclosed_quote_in_the_middle_stops_on_upload() -> None:
    rows = demo_core_rows(5)
    fields = _fields(row_line(rows[2]))
    fields[5] = '"' + fields[5]
    data = source_csv_bytes([rows[0], rows[1], rows[3], rows[4]], raw_lines={2: ",".join(fields)})
    assert _stop(data) == _broken_text(4)


def test_a_character_after_a_closing_quote_stops_as_a_broken_line() -> None:
    rows = demo_core_rows(4)
    fields = _fields(row_line(rows[1]))
    fields[5] = f'"{fields[5]}"X'
    data = source_csv_bytes([rows[0], rows[2], rows[3]], raw_lines={1: ",".join(fields)})
    assert _stop(data) == _broken_text(3)


def test_blank_lines_are_skipped_like_pandas() -> None:
    rows = demo_core_rows(5)
    data = source_csv_bytes(rows, raw_lines={0: "", 2: "", 5: ""})
    buffer = io.BytesIO(data)
    summary = summarize_source_csv(buffer, file_id="demo-file")
    assert summary.rows == len(rows)
    assert len(read_source_csv_rows(buffer, summary, DEMO_CODE)) == len(rows)


def test_leading_blank_lines_before_the_header_are_skipped_and_the_header_sets_the_encoding() -> (
    None
):
    rows = demo_core_rows(3)
    frame = _read(b"\r\n\r\n" + source_csv_bytes(rows))
    assert list(frame.columns) == contract_names()
    assert len(frame) == len(rows)


# ---------------------------------------------------------------- 두 파서 · 파일 자리


def test_rows_stop_when_pandas_counts_other_rows_than_the_summary() -> None:
    buffer = io.BytesIO(source_csv_bytes(demo_core_rows(4)))
    summary = summarize_source_csv(buffer, file_id="demo-file")
    other = dataclasses.replace(summary, rows=summary.rows + 1)
    with pytest.raises(SourceCsvError) as caught:
        read_source_csv_rows(buffer, other, DEMO_CODE)
    assert str(caught.value) == CHANGED_FILE_TEXT


def test_a_pandas_parser_error_becomes_the_broken_line_text() -> None:
    rows = demo_core_rows(4)
    summary = _summary(source_csv_bytes(rows))
    fields = _fields(row_line(rows[3]))
    unclosed = ",".join([*fields[:-1], '"' + fields[-1]])
    broken = io.BytesIO(source_csv_bytes(rows[:3], raw_lines={3: unclosed}))
    # 엄한 흘려 읽기를 건너뛴 요약으로 부른다 — pandas 의 ParserError 를 같은 꼴 글로 바꾼다.
    with pytest.raises(SourceCsvError) as caught:
        read_source_csv_rows(broken, summary, DEMO_CODE)
    assert str(caught.value) == f"줄을 읽지 못했습니다 — {BROKEN_LINE_TAIL}"


def test_the_buffer_stays_open_and_a_second_summary_is_the_same() -> None:
    rows = demo_core_rows(4)
    buffer = io.BytesIO(source_csv_bytes(rows))
    first = summarize_source_csv(buffer, file_id="demo-file")
    assert not buffer.closed
    assert buffer.tell() == 0
    # 저장 회차는 파일 자리가 끝에 있어도 처음부터 다시 읽는다.
    buffer.seek(0, io.SEEK_END)
    assert summarize_source_csv(buffer, file_id="demo-file") == first
    frame = read_source_csv_rows(buffer, first, DEMO_CODE)
    assert not buffer.closed
    pd.testing.assert_frame_equal(read_source_csv_rows(buffer, first, DEMO_CODE), frame)

    broken = io.BytesIO(source_csv_bytes(rows[:3], raw_lines={3: "DEMO"}))
    with pytest.raises(SourceCsvError):
        summarize_source_csv(broken, file_id="demo-file")
    assert not broken.closed
    assert broken.tell() == 0
