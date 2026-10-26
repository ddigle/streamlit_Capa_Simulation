# Purpose: 공용 공정 표시명 프로필의 값 정규화·컬럼 계약 검증과 CSV·붙여넣기 직렬화를 담당한다.

"""공용 공정 표시명 프로필의 값 정규화·컬럼 계약 검증과 CSV·붙여넣기 직렬화.

여기에는 **치환이 없다.** 원본 공정명을 표시명으로 바꾸는 헬퍼는 렌더 계층
(`components/process_labels.py`)에만 두고 서비스는 그것을 import 하지 않는다. 서비스가
표시명을 다루기 시작하면 계산·조인 키가 화면 라벨을 따라가고, `공정` 은 `RQ_*` 여러 표의
1급 조인 키라 그 순간 merge 가 조용히 어긋난다.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from capa_simulation.services.clipboard_table import parse_clipboard_table
from capa_simulation.services.frame_contracts import require_exact_columns
from capa_simulation.services.korean_particle import with_subject_particle, with_topic_particle

PROCESS_RENAME_COLUMNS = ("공정", "표시명")

# Excel·웹 표에서 복사한 값에는 줄바꿈 방지용 U+00A0 이 섞여 들어온다. 화면 월별 표가
# 공백을 U+00A0 으로 바꿔 그리기 때문이고, 그 글자를 그대로 저장하면 원본 공정명과 한
# 글자가 달라 매칭이 조용히 어긋난다.
_NO_BREAK_SPACE = " "


def normalize_process_text(value: object) -> str:
    """앞뒤 공백과 U+00A0 을 정리한 비교·저장용 문자열.

    저장 전 검증과 표시 직전 조회가 **같은 함수**를 써야 매칭이 어긋나지 않는다.
    """
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value)
    if text in {"nan", "<NA>", "None", "NaT"}:
        return ""
    return text.replace(_NO_BREAK_SPACE, " ").strip()


# 중복 오류문에 적는 이름 수 — 붙여넣은 표 전체가 잘못이면 오류문이 화면을 덮는다.
DUPLICATE_REPORT_LIMIT = 5


def process_rename_duplicate_message(label: str, names: Sequence[str]) -> str:
    """1:1 위반 오류문. `names` 는 겹친 이름(앞의 `DUPLICATE_REPORT_LIMIT` 개만 적는다).

    예외 글(평문)과 화면 글이 한 문장을 쓴다 — 화면은 마크다운으로 그려 이름을 막아 넘긴다.
    """
    shown = ", ".join(names[:DUPLICATE_REPORT_LIMIT])
    return (
        f"{with_subject_particle(label)} 중복되었습니다: {shown}. "
        "원본 공정과 표시명은 항상 1:1이어야 합니다."
    )


class ProcessRenameDuplicateError(ValueError):
    """원본 공정명이나 표시명이 둘 이상이다(1:1 위반).

    글은 평문이다(스크립트·로그). 겹친 이름은 사람 글이라 `label`·`names` 로도 실어, 마크다운으로
    그리는 화면이 이름을 글자 그대로 막아 다시 짓게 한다 — 「~x~ *y*」 가 지움선·기울임이 되지
    않게(`components/process_rename_management.py`, 2026-10-26 E2E).
    """

    def __init__(self, label: str, names: Sequence[str]) -> None:
        self.label = label
        self.names = tuple(names)
        super().__init__(process_rename_duplicate_message(label, self.names))


def empty_process_rename_rules() -> pd.DataFrame:
    """아직 아무것도 지정하지 않은 정상 상태의 빈 규칙 프레임."""
    return pd.DataFrame({column: pd.Series(dtype="object") for column in PROCESS_RENAME_COLUMNS})


def validate_process_rename_frame(frame: pd.DataFrame) -> None:
    """컬럼 계약과 1:1 규칙을 검사한다. 빈 프레임은 '지정 없음' 이라 허용한다."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("공정 표시명은 pandas DataFrame이어야 합니다.")
    require_exact_columns(frame.columns, PROCESS_RENAME_COLUMNS, "공정 표시명 컬럼")

    normalized = {
        column: [normalize_process_text(value) for value in frame[column]]
        for column in PROCESS_RENAME_COLUMNS
    }
    for column, label in (("공정", "원본 공정명"), ("표시명", "표시명")):
        if any(not value for value in normalized[column]):
            raise ValueError(f"{with_topic_particle(label)} 비어 있을 수 없습니다.")
        duplicates = sorted(
            {value for value in normalized[column] if normalized[column].count(value) > 1}
        )
        if duplicates:
            raise ProcessRenameDuplicateError(label, duplicates)


def prepare_process_rename_rules(frame: pd.DataFrame) -> pd.DataFrame:
    """검증한 뒤 두 컬럼 값을 정규화한 저장용 프레임을 돌려준다."""
    if isinstance(frame, pd.DataFrame) and frame.empty and not list(frame.columns):
        return empty_process_rename_rules()
    validate_process_rename_frame(frame)
    if frame.empty:
        return empty_process_rename_rules()
    prepared = pd.DataFrame(
        {
            column: [normalize_process_text(value) for value in frame[column]]
            for column in PROCESS_RENAME_COLUMNS
        }
    )
    return prepared.reset_index(drop=True)


def drop_blank_process_rename_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """두 칸이 모두 빈 행을 버린다. `data_editor` 의 빈 새 행이 검증에 걸리지 않게 한다."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("공정 표시명은 pandas DataFrame이어야 합니다.")
    if frame.empty:
        return frame.reset_index(drop=True)
    keep = [
        index
        for index, row in enumerate(frame.itertuples(index=False))
        if any(normalize_process_text(value) for value in row)
    ]
    return frame.iloc[keep].reset_index(drop=True)


def process_rename_to_csv(rules: pd.DataFrame) -> bytes:
    """수정 없이 그대로 다시 붙여넣을 수 있는 UTF-8 CSV."""
    prepared = prepare_process_rename_rules(rules)
    return prepared.to_csv(index=False).encode("utf-8-sig")


def process_rename_from_clipboard(content: str) -> pd.DataFrame:
    """헤더를 포함한 Excel 붙여넣기 블록을 읽어 전체 계약을 검증한다."""
    return validate_process_rename_import(parse_clipboard_table(content, "공정 표시명"))


def validate_process_rename_import(parsed: pd.DataFrame) -> pd.DataFrame:
    """전송수단(CSV·클립보드)과 무관한 입력 계약 검증 한 곳."""
    require_exact_columns(
        parsed.columns,
        PROCESS_RENAME_COLUMNS,
        "공정 표시명 입력 표 컬럼",
        check_order=True,
        strip=True,
    )
    parsed.columns = list(PROCESS_RENAME_COLUMNS)
    return prepare_process_rename_rules(drop_blank_process_rename_rows(parsed))
