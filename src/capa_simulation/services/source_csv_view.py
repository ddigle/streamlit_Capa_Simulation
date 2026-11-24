# Purpose: 원천 CSV 요약을 목록 표 · 등록 칸 처음 값 · 리비전 메모 조각으로 바꾼다(Streamlit 없음).

"""원천 CSV 요약(`io/source_csv.SourceCsvSummary`)을 DB 등록 탭 「CSV 파일」 길이 그릴 값으로 바꾸는
순수 계층.

Streamlit 을 import 하지 않고 세션 상태도 만지지 않는다 — DB 목록의 `bigdataquery_catalog_view` 와
같은 자리다. 목록 표는 DB 목록과 같은 칸 이름 · 표지(등록여부 · 저장가능)를 쓰고, 파일에 없는
시뮬레이션명 · PLAN명 · 원천 등록시각 칸은 세우지 않는다. 등록 칸 처음 값은 DB 폼이 이름 빈 행을
채우는 꼴과 같다 — 원천 시뮬레이션명은 코드, 시나리오명은 「<원천명> (<코드>)」(원천 웹 파일
이름에는 시뮬레이션명 · 주차가 없다). 원천 등록시점 칸의 꼴 판정은 DB 폼의 검증 정규식 · 서버 판정과
같다 — DB 등록 화면 파일을 import 하지 않으려고 이 파일에 둔다."""

from __future__ import annotations

import unicodedata
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import pandas as pd

from capa_simulation.io.company_bigdataquery_adapter import is_valid_simulation_code
from capa_simulation.io.source_csv import SourceCsvSummary
from capa_simulation.services.bigdataquery_catalog_view import (
    REGISTERED_LABEL,
    SAVABLE_LABEL,
    UNREGISTERED_LABEL,
    UNSAVABLE_LABEL,
)

SOURCE_CSV_DISPLAY_COLUMNS: Final[tuple[str, ...]] = (
    "등록여부",
    "저장가능",
    "시뮬레이션 코드",
    "PLAN 코드",
    "행 수",
)
# 원천 등록시점 칸 — DB 폼 「원천 DB 등록시점 (선택)」 과 같은 검증(빈 값은 건너뜀 · 앞뒤 공백
# 허용).
REGISTERED_AT_PATTERN: Final = r"^\s*\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?\s*$"
REGISTERED_AT_FIELD_ERROR: Final = "등록시점은 YYYY-MM-DD HH:MM:SS 형식으로 입력하세요."
REGISTERED_AT_ERROR: Final = "원천 등록시점은 YYYY-MM-DD HH:MM:SS 형식이어야 합니다."
# 리비전 메모에 싣는 파일 이름의 글자 수 상한.
SAFE_FILE_NAME_LIMIT: Final = 60
DEFAULT_REVISION_NAME: Final = "초기 리비전"


@dataclass(frozen=True)
class SourceCsvPrefill:
    """고른 코드로 채우는 등록 칸 여섯 — DB 폼 처음 값(`RegistrationPrefill`)과 같은 칸."""

    simulation_code: str
    source_name: str
    scenario_name: str
    revision_name: str
    registered_at: str
    note: str


def build_source_csv_display_frame(
    summary: SourceCsvSummary, registered_codes: Collection[str]
) -> pd.DataFrame:
    """목록 표 — (코드, PLAN) 마다 한 행(요약 차례 그대로)과 등록여부 · 저장가능 · 행 수.

    코드는 앞뒤 공백을 뗀 값이다(요약이 뗀다) — 등록여부 · 저장가능 · 행 고르기가 모두 그 값을 본다.
    """
    known = set(registered_codes)
    entries = summary.codes
    return pd.DataFrame(
        {
            "등록여부": [
                REGISTERED_LABEL if entry.code in known else UNREGISTERED_LABEL for entry in entries
            ],
            "저장가능": [
                SAVABLE_LABEL if is_valid_simulation_code(entry.code) else UNSAVABLE_LABEL
                for entry in entries
            ],
            "시뮬레이션 코드": [entry.code for entry in entries],
            "PLAN 코드": [entry.plan for entry in entries],
            "행 수": pd.Series([entry.rows for entry in entries], dtype="int64"),
        },
        columns=list(SOURCE_CSV_DISPLAY_COLUMNS),
    )


def source_csv_value_line(summary: SourceCsvSummary) -> str:
    """목록 위 값 줄 — 「**원천 CSV** · 코드 k · n행」(DB 목록의 「기간 · 시각 조회 · n건」
    자리)."""
    codes = len({entry.code for entry in summary.codes})
    return f"**원천 CSV** · 코드 {codes:,} · {summary.rows:,}행"


def default_pick(summary: SourceCsvSummary) -> int | None:
    """처음 고른 행 — 코드가 하나면 그 코드의 첫 행(0), 여럿이면 None(사람이 고른다)."""
    codes = {entry.code for entry in summary.codes}
    return 0 if len(codes) == 1 and summary.codes else None


def code_rows(summary: SourceCsvSummary, code: str) -> int:
    """고른 코드의 행 수 — PLAN 이 여럿이면 모두 더한다(등록은 그 코드의 행 모두다)."""
    return sum(entry.rows for entry in summary.codes if entry.code == code)


def source_csv_prefill(summary: SourceCsvSummary, code: str) -> SourceCsvPrefill:
    """고른 코드로 등록 칸 여섯을 채운다 — DB 폼이 이름 빈 행을 채우는 꼴과 같다.

    원천 시뮬레이션명은 코드, 시나리오명은 「<원천명> (<코드>)」 다 — 원천 웹 파일 이름에는
    시뮬레이션명 · 주차가 없다(내려받은 날짜 · 시각뿐). 원천 등록시점은 빈칸이다(선택). 메모는 그
    코드의 PLAN 을 파일 차례대로 「 · 」 로 잇는다(빈 PLAN 은 뺀다).
    """
    plans = [entry.plan for entry in summary.codes if entry.code == code and entry.plan]
    plan_text = " · ".join(dict.fromkeys(plans))
    return SourceCsvPrefill(
        simulation_code=code,
        source_name=code,
        scenario_name=f"{code} ({code})",
        revision_name=DEFAULT_REVISION_NAME,
        registered_at="",
        note=f"원천 PLAN {plan_text}" if plan_text else "",
    )


def safe_file_name(name: str) -> str:
    """메모에 싣는 파일 이름 — 경로(`/` · `\\`)와 제어 글자를 떼고 앞뒤 공백을 지워 60자로
    자른다."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(char for char in base if not unicodedata.category(char).startswith("C"))
    return cleaned.strip()[:SAFE_FILE_NAME_LIMIT]


def source_csv_note(note: str, file_name: str, kinds: int) -> str:
    """리비전 1 메모 — 적은 메모 뒤에 「CSV 파일 <이름>」 · 「CUSTOM 파일 값 — 종류 n」 을 붙인다.

    `kinds` 는 붙은 CUSTOM 값 종류 수(공급자 `custom_kinds` — 대소문자 표기를 하나로 모은 뒤, DB 길
    메모 「CUSTOM 원천 대조 — 종류 n」 과 같은 셈)다. 저장 길(`save_bigdataquery_scenario`)이 그
    뒤에 업무 키 충돌 · CS 빈 행 · 부대공정 · 대당 Capa 조각을 DB 등록과 같은 차례로 붙인다."""
    shown = safe_file_name(file_name)
    file_part = f"CSV 파일 {shown}" if shown else "CSV 파일"
    pieces = (note.strip(), file_part, f"CUSTOM 파일 값 — 종류 {kinds:,}")
    return " · ".join(piece for piece in pieces if piece)


def optional_registered_at(text: str) -> datetime | None:
    """원천 등록시점 칸 — 빈 값은 None, 아니면 ISO 꼴 시각(DB 폼 `_optional_datetime` 과 같은
    판정)."""
    normalized = text.strip()
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(REGISTERED_AT_ERROR) from exc
