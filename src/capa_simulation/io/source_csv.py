# Purpose: 원천 CSV 를 흘려 읽어 머리 · 칸 수 · 코드를 보고 고른 코드 행만 Core Data 계약으로 읽는다

"""원천 CSV 읽기 — 올릴 때 요약(흘려 읽기 한 번)과 저장 때 고른 코드 행 읽기.

- 요약(`summarize_source_csv`)은 `csv` 모듈로 줄마다 지나며 수만 센다. 표를 짓지 않고, 해독한 전체
  글도 사본(`getvalue()`)도 쥐지 않는다. 그 한 번으로 인코딩 · 머리 맞춤 · 줄마다 칸 수 · 코드 · 행
  수를 본다. 멈춤은 `SourceCsvError` 한 글이다.
- 행 읽기(`read_source_csv_rows`)는 저장 회차에만 pandas 로 고른 코드 행을 Core Data 계약(구분자 ·
  따옴표 · 열 이름 · 글자 열 `string`)대로 읽어 계약 78열 차례로 낸다 — 정규화
  (`normalize_core_data`) 전 자리다. 결측은 빈칸만이고(글자 「NA」 · 「null」 은 글자 그대로)
  숫자 열은 `round_trip` 으로 읽어 최단 표기 글자가 적은 실수를 그대로 돌려받는다.
- 남는 열 셋(`SOURCE_CSV_EXTRA_COLUMNS`)과 값 없는 이름 없는 열(줄 끝 쉼표)은 읽지 않고 알리지
  않는다. 그 밖의 모르는 열 · 모자란 계약 열 · 겹친 머리는 멈춘다.
- 스크립트용 `read_core_data_csv` 는 경로만 받고 곧바로 78열 검사를 해 남는 열 셋을 뺄 수 없다 —
  같은 계약 객체를 쓰는 이 읽기를 따로 둔다.
"""

from __future__ import annotations

import codecs
import csv
import io
from collections.abc import Hashable, Iterator, Sequence
from dataclasses import dataclass
from typing import BinaryIO, Final, Protocol

import pandas as pd

from capa_simulation.io.core_data_source import (
    QUOTE_STYLES,
    CoreDataContract,
    load_core_data_contract,
)

# 원천 웹 CSV 에만 오는 열 셋 — 계약 78열 밖이라 읽지 않는다(늘 오는 열이라 알리지도 않는다).
SOURCE_CSV_EXTRA_COLUMNS: Final = ("설비대수변화관리여부", "설비대여평가여부", "공식여부")
# 원천 유형 — 머리 띠 「CSV」 · 점검 스크립트 묶음이 `CSV_CORE_DATA` 접두어로 저절로 선다.
SOURCE_CSV_SOURCE_TYPE: Final = "CSV_CORE_DATA_UPLOAD"
# 머리 줄 바이트를 풀어 보는 차례 — UTF-8(BOM 포함) 먼저, 그다음 계약 인코딩(설비 CSV 와 같은 차례).
# 엄한 UTF-8 이 CP949 한글을 받아들이는 일은 드물고, 거꾸로는 깨진 글로 읽힐 수 있다.
SOURCE_CSV_ENCODINGS: Final = ("utf-8-sig", "cp949")

SIMULATION_ID_COLUMN: Final = "시뮬레이션 ID"
PLAN_ID_COLUMN: Final = "PLAN ID"

EMPTY_FILE_TEXT: Final = "빈 파일입니다 — 원천 웹에서 받은 시나리오 CSV 를 올리세요."
DECODE_TEXT: Final = (
    "글자를 읽지 못했습니다 — CP949 · UTF-8 CSV 가 아닙니다. 문서 보안(DRM)이 걸렸거나 다른 꼴로 "
    "저장된 파일이면 원천 웹에서 다시 받아 그대로 올리세요."
)
HEADER_ONLY_TEXT: Final = "머리만 있고 행이 없습니다."
CHANGED_FILE_TEXT: Final = "올린 파일이 바뀌었습니다 — 파일을 다시 올리세요."
FIELD_COUNT_TAIL: Final = "잘렸거나 손으로 고친 줄이 있습니다."
BROKEN_LINE_TAIL: Final = "닫히지 않은 따옴표 같은 깨진 줄이 있습니다."
COLUMNS_TAIL: Final = "원천 CSV 꼴이 바뀌었으면 앱 관리자(개발자)에게 열 이름을 알려 주세요."

# 멈춤 글에 이름을 늘어놓는 수 — 그 뒤는 「외 n개」.
_NAME_LIMIT: Final = 10
# 읽지 않는 칸(남는 열 · 이름 없는 열)에 pandas 가 쓸 이름 — 계약 이름과 겹치지 않는 자리 이름.
_SKIP_NAME: Final = "__source_csv_skip_{position}"


class SourceCsvError(ValueError):
    """원천 CSV 를 읽지 못한 까닭 한 글(올릴 때 입력 곁 한 줄 · 저장 때 결과 칸)."""


@dataclass(frozen=True)
class SourceCsvCode:
    """파일 안 (시뮬레이션 ID, PLAN ID) 하나 — 앞뒤 공백을 뗀 값과 그 행 수."""

    code: str
    plan: str
    rows: int


@dataclass(frozen=True)
class SourceCsvSummary:
    """흘려 읽기 한 번의 결과 — 수 KB 다. 표 · 해독한 글은 들지 않는다.

    `read_names` 는 파일 칸 차례마다 pandas 에 줄 이름(계약 이름, 읽지 않는 칸은 자리 이름)이고
    `keep_positions` 는 계약 78열이 놓인 파일 칸 자리(파일 차례)다. `rows` 는 빈 줄을 뺀 데이터
    레코드 수, `codes` 는 처음 나온 차례의 (코드, PLAN) 마다 행 수다.
    """

    file_id: str
    encoding: str
    read_names: tuple[str, ...]
    keep_positions: tuple[int, ...]
    rows: int
    codes: tuple[SourceCsvCode, ...]


@dataclass(frozen=True)
class _Header:
    read_names: tuple[str, ...]
    keep_positions: tuple[int, ...]
    positions: dict[str, int]
    unnamed: tuple[int, ...]


class _LineReader(Protocol):
    @property
    def line_num(self) -> int: ...

    def __next__(self) -> list[str]: ...


def summarize_source_csv(
    buffer: BinaryIO,
    *,
    file_id: str,
    contract: CoreDataContract | None = None,
) -> SourceCsvSummary:
    """올린 파일을 한 번 흘려 읽어 요약한다 — 올릴 때 · 저장 때 같은 함수.

    인코딩은 첫 머리 줄 바이트로 정한다(`TextIOWrapper` 는 덩이로 풀어서, 머리 줄 뒤 첫 덩이 안의
    깨진 바이트가 머리 레코드보다 먼저 오류를 낸다 — 「풀다 실패하면 다음 인코딩」 꼴이면 UTF-8
    파일이 CP949 로 다시 읽혀 깨진 머리가 엉뚱한 모르는 열로 보인다). 정한 뒤 풀리지 않는 바이트는
    다른 인코딩으로 다시 읽지 않고 멈춘다.

    감싼 글 읽개는 늘 떼어 낸다(`detach`) — 닫거나 버리면(GC) 올린 파일이 닫혀 저장 회차의 다시
    읽기가 깨진다. 끝나면 파일 자리를 맨 앞으로 돌려 둔다.
    """
    selected = contract or load_core_data_contract()
    encoding = _header_encoding(buffer, selected)
    buffer.seek(0)
    text = io.TextIOWrapper(buffer, encoding=encoding, errors="strict", newline="")
    try:
        reader = csv.reader(
            text,
            delimiter=selected.delimiter,
            quotechar='"',
            quoting=QUOTE_STYLES[selected.quote_style],
            doublequote=True,
            # 엄하지 않은 꼴은 닫히지 않은 따옴표를 오류 없이 파일 끝까지 한 칸으로 삼켜 칸 수
            # 검사를 지나간다. 대가로 닫는 따옴표 뒤 글자(`"ab"c`)도 깨진 줄로 막는다.
            strict=True,
        )
        header, rows, codes = _scan_records(reader, selected)
    finally:
        text.detach()
        buffer.seek(0)
    return SourceCsvSummary(
        file_id=file_id,
        encoding=encoding,
        read_names=header.read_names,
        keep_positions=header.keep_positions,
        rows=rows,
        codes=codes,
    )


def read_source_csv_rows(
    buffer: BinaryIO,
    summary: SourceCsvSummary,
    simulation_code: str,
    *,
    contract: CoreDataContract | None = None,
) -> pd.DataFrame:
    """고른 코드의 행만 계약 78열 차례로 읽는다 — 저장 회차에만(정규화 전).

    머리 줄은 버리고 요약이 맞춘 이름을 준다(`header=0, names=`) — 겹침 · 「X.1」 · 「Unnamed」 가
    생기지 않는다. `index_col=False` 는 첫 데이터 줄만 칸이 많을 때 열이 밀리는 것을 막는 둘째
    방어다(그런 줄은 요약이 이미 막는다 — pandas 는 남는 칸을 오류 없이 버린다). 두 파서가 행을
    다르게 세면 올린 파일이 바뀐 것으로 멈춘다.

    시뮬레이션 ID 는 앞뒤 공백을 뗀 값으로 맞대고, 남긴 행의 그 칸도 뗀 값으로 둔다 — DB 조회는
    코드와 같은 값의 행만 받으므로 두 길의 원천이 같은 글이 된다. 전체 표는 그 자리에서 놓는다.
    """
    selected = contract or load_core_data_contract()
    names = [column.name for column in selected.columns]
    string_dtypes: dict[Hashable, str] = {
        column.name: "string" for column in selected.columns if column.dtype == "string"
    }
    buffer.seek(0)
    try:
        frame = pd.read_csv(
            buffer,
            encoding=summary.encoding,
            encoding_errors="strict",
            sep=selected.delimiter,
            quoting=QUOTE_STYLES[selected.quote_style],
            header=0,
            names=list(summary.read_names),
            usecols=list(summary.keep_positions),
            index_col=False,
            dtype=string_dtypes,
            keep_default_na=False,
            na_values=[""],
            float_precision="round_trip",
            low_memory=False,
        )
    except UnicodeDecodeError as error:
        raise SourceCsvError(DECODE_TEXT) from error
    except pd.errors.ParserError as error:
        # pandas 글의 줄 · 행 번호는 메모장 줄 번호가 아니라 번호 없는 글로 멈춘다.
        raise SourceCsvError(_broken_line_text(None)) from error
    except ValueError as error:
        # 이름 · 칸 자리가 파일과 맞지 않음 — 요약 뒤 파일이 바뀐 때다.
        raise SourceCsvError(CHANGED_FILE_TEXT) from error
    finally:
        buffer.seek(0)
    if len(frame) != summary.rows:
        raise SourceCsvError(CHANGED_FILE_TEXT)
    code = simulation_code.strip()
    ids = frame[SIMULATION_ID_COLUMN].astype("string").str.strip()
    picked = frame.loc[ids.eq(code).fillna(False).to_numpy(dtype=bool), names]
    picked = picked.reset_index(drop=True)
    picked[SIMULATION_ID_COLUMN] = picked[SIMULATION_ID_COLUMN].astype("string").str.strip()
    return picked


def _header_encoding(buffer: BinaryIO, contract: CoreDataContract) -> str:
    """첫 머리 줄(앞 빈 줄 · BOM 뺌)까지의 바이트가 엄하게 풀리는 첫 인코딩."""
    encodings = tuple(dict.fromkeys((*SOURCE_CSV_ENCODINGS, contract.encoding)))
    buffer.seek(0)
    head = bytearray()
    first = True
    while True:
        line = buffer.readline()
        if not line:
            raise SourceCsvError(EMPTY_FILE_TEXT)
        head += line
        content = line.removeprefix(codecs.BOM_UTF8) if first else line
        first = False
        if content.strip():
            break
    for encoding in encodings:
        try:
            bytes(head).decode(encoding)
        except UnicodeDecodeError:
            continue
        return encoding
    raise SourceCsvError(DECODE_TEXT)


def _records(reader: _LineReader) -> Iterator[tuple[int, list[str]]]:
    """빈 레코드(빈 줄 — pandas 도 건너뜀)를 뺀 (시작 줄 번호, 레코드). 깨진 줄 · 해독은 멈춤."""
    while True:
        start = reader.line_num + 1
        try:
            record = next(reader)
        except StopIteration:
            return
        except csv.Error as error:
            raise SourceCsvError(_broken_line_text(start)) from error
        except UnicodeDecodeError as error:
            raise SourceCsvError(DECODE_TEXT) from error
        if record:
            yield start, record


def _scan_records(
    reader: _LineReader, contract: CoreDataContract
) -> tuple[_Header, int, tuple[SourceCsvCode, ...]]:
    """머리를 맞추고 끝까지 지나며 칸 수 · 이름 없는 칸 값 · 코드를 센다.

    판정 차례: 머리(겹침 · 이름 있는 모르는 열 · 모자란 열 — 걸리면 나머지를 읽지 않음) → 끝까지
    (깨진 줄 · 해독은 그 자리) → 칸 수 → 값 든 이름 없는 열 → 행 없음 → 빈 시뮬레이션 ID.
    """
    records = _records(reader)
    first = next(records, None)
    if first is None:
        raise SourceCsvError(EMPTY_FILE_TEXT)
    raw_header = first[1]
    header = _match_headers(raw_header, contract)
    width = len(raw_header)
    id_position = header.positions[SIMULATION_ID_COLUMN]
    plan_position = header.positions[PLAN_ID_COLUMN]
    rows = 0
    first_mismatch: tuple[int, int] | None = None
    other_mismatches = 0
    valued_unnamed: set[int] = set()
    blank_ids = 0
    counts: dict[tuple[str, str], int] = {}
    for line, record in records:
        rows += 1
        if len(record) != width:
            # 칸 수가 다른 줄은 자리로 값을 읽지 않는다(잘린 줄에는 그 자리가 없다).
            if first_mismatch is None:
                first_mismatch = (line, len(record))
            else:
                other_mismatches += 1
            continue
        for position in header.unnamed:
            if record[position].strip():
                valued_unnamed.add(position)
        code = record[id_position].strip()
        if not code:
            blank_ids += 1
            continue
        key = (code, record[plan_position].strip())
        counts[key] = counts.get(key, 0) + 1
    if first_mismatch is not None:
        line, line_width = first_mismatch
        raise SourceCsvError(_field_count_text(line, width, line_width, other_mismatches))
    if valued_unnamed:
        unnamed_names = [_unnamed_name(position) for position in sorted(valued_unnamed)]
        raise SourceCsvError(_columns_text(unnamed_names, []))
    if rows == 0:
        raise SourceCsvError(HEADER_ONLY_TEXT)
    if blank_ids:
        raise SourceCsvError(f"시뮬레이션 ID 가 빈 행이 {blank_ids}개 있어 읽지 않았습니다.")
    codes = tuple(SourceCsvCode(code, plan, count) for (code, plan), count in counts.items())
    return header, rows, codes


def _fold_header(name: str) -> str:
    """맞댈 꼴 — 앞뒤 공백을 떼고 안쪽 공백을 하나로, 대소문자를 접는다."""
    return " ".join(name.split()).casefold()


def _match_headers(raw_header: Sequence[str], contract: CoreDataContract) -> _Header:
    """날 머리(pandas 가 이름을 고치기 전)를 계약 78 이름 · 남는 열 셋에 맞춘다.

    접은 꼴이 같은 머리가 둘 이상이면(글자 그대로 같은 것 포함) 겹침으로 멈춘다. 빈 머리(공백뿐
    포함)는 이름 없는 칸으로 두고 값이 있는지는 끝까지 읽은 뒤 본다. 모르는 열과 모자란 계약 열은
    한 글에 함께 알린다 — 이름이 바뀐 열이면 둘이 짝으로 보인다.
    """
    contract_names = [column.name for column in contract.columns]
    known = {_fold_header(name): name for name in (*contract_names, *SOURCE_CSV_EXTRA_COLUMNS)}
    folded = [_fold_header(raw) for raw in raw_header]
    shown: dict[str, str] = {}
    duplicated: list[str] = []
    for raw, key in zip(raw_header, folded, strict=True):
        if not key:
            continue
        if key in shown:
            if shown[key] not in duplicated:
                duplicated.append(shown[key])
        else:
            shown[key] = " ".join(raw.split())
    if duplicated:
        raise SourceCsvError(f"같은 열 이름이 둘 이상 있습니다: {_listed(duplicated)}")
    unknown = [shown[key] for key in folded if key and key not in known]
    present = {known[key] for key in folded if key in known}
    missing = [name for name in contract_names if name not in present]
    if unknown or missing:
        raise SourceCsvError(_columns_text(unknown, missing))

    contract_set = set(contract_names)
    read_names: list[str] = []
    keep_positions: list[int] = []
    positions: dict[str, int] = {}
    unnamed: list[int] = []
    for position, key in enumerate(folded):
        name = known.get(key)
        if name is not None and name in contract_set:
            read_names.append(name)
            keep_positions.append(position)
            positions[name] = position
            continue
        read_names.append(_SKIP_NAME.format(position=position))
        if not key:
            unnamed.append(position)
    return _Header(tuple(read_names), tuple(keep_positions), positions, tuple(unnamed))


def _listed(names: Sequence[str]) -> str:
    shown = " · ".join(names[:_NAME_LIMIT])
    hidden = len(names) - _NAME_LIMIT
    return f"{shown} 외 {hidden}개" if hidden > 0 else shown


def _unnamed_name(position: int) -> str:
    return f"이름 없는 열({position + 1}번째 칸)"


def _columns_text(unknown: Sequence[str], missing: Sequence[str]) -> str:
    parts: list[str] = []
    if unknown:
        parts.append(f"앱이 모르는 열: {_listed(unknown)}")
    if missing:
        parts.append(f"Core Data 열 가운데 없는 열: {_listed(missing)}")
    return f"{' · '.join(parts)} — {COLUMNS_TAIL}"


def _field_count_text(line: int, header_width: int, line_width: int, others: int) -> str:
    more = f" 외 {others}줄" if others else ""
    return (
        f"{line}번째 줄의 칸 수가 머리와 다릅니다(머리 {header_width}칸 · 그 줄 {line_width}칸)"
        f"{more} — {FIELD_COUNT_TAIL}"
    )


def _broken_line_text(line: int | None) -> str:
    head = f"{line}번째 줄을" if line is not None else "줄을"
    return f"{head} 읽지 못했습니다 — {BROKEN_LINE_TAIL}"
