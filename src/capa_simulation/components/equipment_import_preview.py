# Purpose: 붙여넣기 파싱 실패를 행 단위로 귀속해 어느 행이 왜 틀렸는지 보여준다.

"""붙여넣은 표의 오류를 **행에 붙인다.**

`services/equipment_csv.py` 의 `read_*_clipboard` 는 표 전체를 한 번에 검증하고 한 문장을
던진다. 30행을 붙여넣고 「확정상태는 계획·확정·완료·지연 중 하나여야 합니다: [...]」 를
받은 사람은 그 예시 값이 몇 번째 줄인지 눈으로 찾아야 한다. 예시는 다섯 개까지만 실리므로
여섯 번째부터는 화면에 나오지도 않는다.

그래서 **같은 파서를 행 하나씩 다시 부른다.** 헤더 한 줄 + 데이터 한 줄을 붙여 파서에
넘기면 그 행만의 잘못이 그 행에 남는다. `services/` 는 한 줄도 고치지 않는다 — 계산이
그대로인 것이 이 과제의 통과 조건이라, 검증 규칙을 이쪽에서 흉내 내지 않고 **원본 파서를
그대로 여러 번 부르는 것**이 유일하게 안전한 방법이다.

세 가지를 가른다.

1. **헤더의 잘못** — 컬럼이 빠졌거나 중복이면 모든 행이 같은 이유로 실패한다. 행마다
   붙이면 N행 전부가 빨개져 정작 고칠 곳(첫 줄)을 가린다. 헤더만으로 한 번 파싱해 보고
   (세 파서 모두 데이터 0행을 정상으로 받는다) 거기서 터지면 프레임 오류로 돌린다.
2. **행의 잘못** — 날짜 형식·허용값·필수값처럼 그 행만 보면 판정되는 것. 행 번호는
   붙여넣은 표 기준 1-based(헤더 제외)다.
3. **행을 넘나드는 규칙** — 호기 중복, 공정+분류 중복, 호기·비가동유형·시작일 중복.
   한 행씩은 전부 통과하는데 전체가 실패하면 그것이다. 어느 한 행의 잘못이 아니므로
   행 목록 없이 프레임 오류로 돌린다.

비가동의 「호기 마스터에 없는 설비」는 행을 넘나드는 것처럼 보이지만 `prepare_downtime_
schedule` 이 행마다 마스터와 맞대므로 한 행씩 파싱해도 그 행에서 터진다 — 규칙을 이름으로
분류하지 않고 **기계가 가른 대로** 둔다.

행 수가 `max_row_parse` 를 넘으면 구간 이분 탐색으로 바꾼다. 실패한 구간만 반으로 쪼개고
성공한 구간은 더 내려가지 않으므로 호출 수가 O(오류 수 × log 행 수) 로 줄어든다. 구간이
실패했는데 양쪽 반이 모두 성공하면 그 구간 안에 행을 넘나드는 규칙이 있는 것이다.

**표본 관측(합성 데모 fleet, `services/equipment_samples.sample_equipment_master` 리터럴을
호기 접미로 늘려 만든 표. 실적이 아니다):** 31컬럼 호기 마스터는 **행 수와 거의 무관하게
한 번 파싱에 약 34ms** 가 든다 — 프레임을 만들고 열마다 검증을 도는 고정비다. 그래서 비용은
「몇 행이냐」가 아니라 「파서를 몇 번 부르냐」로 정해진다.

| 경우 | 파서 호출 | 시간 |
|---|---|---|
| 800행, 오류 없음 | 1 | 57ms |
| 30행, 오류 2행, 전수 | 32 | 1.0초 |
| 800행, 오류 2행, 전수 | 802 | 27.3초 |
| 800행, 오류 2행, 이분 탐색 | 42 | 1.4초 |

전수가 800행에서 27초라서 이분 탐색이 필요하다(같은 입력에서 두 방식의 행 오류가 완전히
같은 것을 테스트가 고정한다). 기본 `max_row_parse=100` 은 전수 약 3.4초를 상한으로 본
값이다 — 더 낮추면 작은 표가 이분 탐색으로 가고, 오류가 많은 작은 표에서는 이분 탐색이
전수보다 두 배까지 느려진다(실패한 구간마다 양쪽 반을 다시 부른다).

**칸 안에 줄바꿈이 든 표는 귀속하지 않는다.** Excel 에서 Alt+Enter 로 줄을 나눈 칸은
따옴표로 묶인 채 붙여넣기 텍스트에 `\n` 을 남긴다. 줄 수와 표의 행 수가 어긋나므로 행
번호를 믿을 수 없다 — 그때는 원래 메시지를 프레임 오류로 그대로 돌린다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from io import StringIO

import pandas as pd
import streamlit as st

from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.services.clipboard_table import TEXT_TABLE_READ_OPTIONS

__all__ = [
    "DEFAULT_MAX_ROW_PARSE",
    "ERROR_ROWS_FILE_NAME",
    "IMPORT_ERROR_DOWNLOAD_KEY",
    "OK_MARK",
    "PINNED_COLUMNS",
    "ROW_COLUMN",
    "VERDICT_COLUMN",
    "ImportPreviewResult",
    "attribute_row_errors",
    "build_preview_table",
    "error_rows_csv",
    "parse_raw_rows",
    "render_import_errors",
    "split_pasted_rows",
]

VERDICT_COLUMN = "검증"
ROW_COLUMN = "행"
# 미리보기 표 맨 앞에 고정할 두 컬럼. 호출부가 `st.column_config.Column(pinned=True)` 에
# 그대로 넣는다 — 31컬럼을 가로로 밀어도 「몇 행이 왜 틀렸는가」는 화면에 남아야 한다.
PINNED_COLUMNS: tuple[str, str] = (VERDICT_COLUMN, ROW_COLUMN)
OK_MARK = "✅"

# 붙여넣은 줄을 **그대로** 돌려주므로 탭 구분이다. 확장자를 `.csv` 로 적으면 Excel 이 한
# 컬럼으로 열어 버려, 고쳐서 다시 붙여넣는 왕복이 끊긴다.
ERROR_ROWS_FILE_NAME = "import_오류행.tsv"
ERROR_ROWS_LABEL = "오류 행만 내려받기"
IMPORT_ERROR_DOWNLOAD_KEY = "equipment_import_error_rows_download_v1"

# 한 줄씩 전수 파싱을 참고 기다릴 수 있는 행 수. 위 관측(호출당 약 34ms)에서 왔다.
DEFAULT_MAX_ROW_PARSE = 100

ClipboardParser = Callable[[str], pd.DataFrame]


@dataclass(frozen=True, eq=False)
class ImportPreviewResult:
    """붙여넣기 한 번의 판정.

    `eq=False` 인 것은 DataFrame 때문이다. 자동 생성된 `__eq__` 는 프레임끼리 `==` 를
    비교해 진리값이 모호한 프레임을 만들고, 그 결과를 `bool()` 하는 순간 터진다.
    """

    frame: pd.DataFrame | None
    row_errors: list[tuple[int, str]]
    frame_error: str | None
    row_count: int
    # 화면이 오류 행만 내려받게 하려면 원문이 필요하다. 계약의 네 칸으로는 `render_import_
    # errors(result)` 가 CSV 를 만들 수 없어 여기 실어 둔다(보고서의 이탈 항목).
    source_text: str = ""
    # 파싱이 실패하면 `frame` 이 없어 미리보기에 그릴 표가 없다. 검증을 거치지 않은 원문
    # 표를 함께 실어 `build_preview_table` 이 그 위에 판정을 얹는다.
    raw_frame: pd.DataFrame | None = field(default=None)

    @property
    def ok(self) -> bool:
        """오류가 하나도 없는가."""
        return self.frame is not None

    @property
    def error_row_numbers(self) -> list[int]:
        return [number for number, _ in self.row_errors]


def split_pasted_rows(text: str) -> tuple[str, list[str]]:
    """헤더 한 줄과 **빈 줄을 뺀** 데이터 줄들.

    빈 줄을 먼저 버리는 것은 `parse_clipboard_table` 이 `dropna(how="all")` 로 같은 행을
    버리기 때문이다. 여기서 세어 둔 번호와 표의 행 순서가 어긋나면 안 된다.
    """
    normalized = text.lstrip("﻿").strip("\r\n")
    lines = normalized.splitlines()
    if not lines:
        return "", []
    return lines[0], [line for line in lines[1:] if line.strip()]


def parse_raw_rows(text: str) -> pd.DataFrame | None:
    """검증 없이 원문을 표로만 읽는다. 읽지 못하면 `None`.

    `read_*_clipboard` 와 **같은 읽기 옵션**을 쓴다. 한쪽만 다르면 `NA` 같은 값이 미리보기와
    실제 적용에서 다르게 읽혀, 화면에서 통과한 표가 적용에서 터진다.
    """
    normalized = text.lstrip("﻿").strip("\r\n")
    if not normalized:
        return None
    try:
        frame: pd.DataFrame = pd.read_csv(StringIO(normalized), sep="\t", **TEXT_TABLE_READ_OPTIONS)
    except (pd.errors.ParserError, ValueError):
        return None
    frame.columns = [str(column).lstrip("﻿").strip() for column in frame.columns]
    return frame.dropna(how="all").reset_index(drop=True)


def attribute_row_errors(
    text: str,
    parser: ClipboardParser,
    *,
    max_row_parse: int = DEFAULT_MAX_ROW_PARSE,
) -> ImportPreviewResult:
    """붙여넣기 전체를 파싱하고, 실패하면 그 잘못을 행에 붙인다.

    `parser` 는 `read_baseline_clipboard` 처럼 **붙여넣기 문자열 하나만 받는** 호출이다.
    `floor_canvases`·`equipment` 같은 맥락은 호출부가 `partial` 로 묶어 넘긴다 — 이 모듈이
    세 파서의 인자를 알면 파서가 늘 때마다 여기도 고쳐야 한다.
    """
    header, rows = split_pasted_rows(text)
    row_count = len(rows)
    try:
        frame = parser(text)
    except ValueError as exc:
        whole_message = str(exc)
    else:
        return ImportPreviewResult(
            frame=frame,
            row_errors=[],
            frame_error=None,
            row_count=row_count,
            source_text=text,
            raw_frame=None,
        )

    raw_frame = parse_raw_rows(text)

    def frame_level(message: str) -> ImportPreviewResult:
        return ImportPreviewResult(
            frame=None,
            row_errors=[],
            frame_error=message,
            row_count=row_count,
            source_text=text,
            raw_frame=raw_frame,
        )

    if row_count == 0:
        return frame_level(whole_message)
    # 줄 수와 표의 행 수가 어긋나면 칸 안에 줄바꿈이 있다. 행 번호를 믿을 수 없다.
    if raw_frame is None or len(raw_frame) != row_count:
        return frame_level(whole_message)
    # 헤더의 잘못이면 모든 행이 같은 이유로 실패한다. 세 파서 모두 데이터 0행을 받는다.
    if _range_error(header, rows, 0, 0, parser) is not None:
        return frame_level(whole_message)

    if row_count <= max_row_parse:
        row_errors = [
            (index + 1, message)
            for index in range(row_count)
            if (message := _range_error(header, rows, index, index + 1, parser)) is not None
        ]
        cross_messages: list[str] = []
    else:
        row_errors, cross_messages = _bisect_errors(header, rows, 0, row_count, parser)

    if not row_errors:
        return frame_level(cross_messages[0] if cross_messages else whole_message)
    return ImportPreviewResult(
        frame=None,
        row_errors=row_errors,
        frame_error=cross_messages[0] if cross_messages else None,
        row_count=row_count,
        source_text=text,
        raw_frame=raw_frame,
    )


def build_preview_table(preview: pd.DataFrame, result: ImportPreviewResult) -> pd.DataFrame:
    """미리보기 표 맨 앞에 `검증`·`행` 을 붙이고 오류 행을 위로 올린다.

    행 번호는 **자리로** 매긴다(첫 행이 1행). `preview` 는 붙여넣은 순서를 지킨 표여야
    한다 — `result.raw_frame` 이나 그것으로 만든 Import 미리보기가 그렇다.

    `insert` 전에 인덱스를 버린다. `insert` 는 Series 를 **인덱스로 맞춰** 넣으므로
    인덱스가 0 부터가 아니면 판정이 통째로 어긋난다(`services/equipment_csv.py` 의 같은
    주석이 그 사고를 적어 두었다).
    """
    table = preview.reset_index(drop=True)
    messages = dict(result.row_errors)
    numbers = list(range(1, len(table) + 1))
    table.insert(0, ROW_COLUMN, pd.Series(numbers, dtype="int64"))
    table.insert(
        0,
        VERDICT_COLUMN,
        pd.Series([messages.get(number, OK_MARK) for number in numbers], dtype="string"),
    )
    # 오류 행이 먼저, 그 안에서는 붙여넣은 순서 그대로. `kind="stable"` 이 뒤쪽을 지킨다.
    order = pd.Series([0 if number in messages else 1 for number in numbers], dtype="int64")
    return table.iloc[order.sort_values(kind="stable").index].reset_index(drop=True)


def error_rows_csv(text: str, row_numbers: Sequence[int]) -> bytes:
    """헤더 + 오류 행만 담은 붙여넣기 원문.

    **탭 구분 그대로** 돌려준다. 고친 뒤 다시 붙여넣는 것이 이 파일의 쓸모라, 여기서
    쉼표로 바꾸면 값 안의 쉼표를 따옴표로 감싸야 하고 사용자는 Excel 에서 텍스트 나누기를
    한 번 더 해야 한다. BOM 을 붙인 UTF-8 인 것은 저장소의 다른 내보내기와 같다.
    """
    header, rows = split_pasted_rows(text)
    if not header:
        return b""
    picked = [rows[number - 1] for number in sorted(set(row_numbers)) if 1 <= number <= len(rows)]
    return ("\n".join([header, *picked]) + "\n").encode("utf-8-sig")


def render_import_errors(
    result: ImportPreviewResult,
    *,
    key: str = IMPORT_ERROR_DOWNLOAD_KEY,
) -> None:
    """오류 요약 한 줄 · 행 목록 · 오류 행 내려받기. 그 밖에는 아무것도 그리지 않는다.

    표와 적용 버튼은 호출부가 그린다 — 이 함수가 그리면 세 표(기존 보유대수·호기 마스터·
    비가동 일정)의 미리보기 구성이 이 모듈에 갇힌다.
    """
    if not result.row_errors:
        if result.frame_error:
            st.error(result.frame_error)
            st.caption("행을 넘나드는 규칙이라 어느 한 행의 잘못이 아닙니다.")
        return

    error_count = len(result.row_errors)
    st.error(f"붙여넣은 {result.row_count:,}행 중 **{error_count:,}행에 오류**가 있습니다.")
    if result.frame_error:
        st.caption(result.frame_error)
    with st.expander(f"오류 {error_count:,}행 보기", expanded=True):
        for number, message in result.row_errors:
            st.markdown(f"- **{number:,}행** — {message}")
    render_csv_download(
        data=error_rows_csv(result.source_text, result.error_row_numbers),
        file_name=ERROR_ROWS_FILE_NAME,
        key=key,
        label=ERROR_ROWS_LABEL,
    )


def _range_error(
    header: str,
    rows: list[str],
    lo: int,
    hi: int,
    parser: ClipboardParser,
) -> str | None:
    """`rows[lo:hi]` 만 붙여 파싱해 본다. 통과하면 `None`."""
    try:
        parser("\n".join([header, *rows[lo:hi]]))
    except ValueError as exc:
        return str(exc)
    return None


def _bisect_errors(
    header: str,
    rows: list[str],
    lo: int,
    hi: int,
    parser: ClipboardParser,
) -> tuple[list[tuple[int, str]], list[str]]:
    """실패한 구간만 반으로 쪼갠다. 돌려주는 것은 (행 오류, 구간을 넘나든 메시지).

    구간이 실패했는데 양쪽 반이 모두 성공하면 그 구간 안에 **행을 넘나드는 규칙**이 있다
    (예: 멀리 떨어진 두 행의 호기 중복). 그때는 그 구간의 메시지를 그대로 올린다.
    """
    message = _range_error(header, rows, lo, hi, parser)
    if message is None:
        return [], []
    if hi - lo <= 1:
        return [(lo + 1, message)], []
    mid = (lo + hi) // 2
    left_rows, left_cross = _bisect_errors(header, rows, lo, mid, parser)
    right_rows, right_cross = _bisect_errors(header, rows, mid, hi, parser)
    if not (left_rows or right_rows or left_cross or right_cross):
        return [], [message]
    return left_rows + right_rows, left_cross + right_cross
