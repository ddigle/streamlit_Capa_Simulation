# Purpose: 공용 공정 표시명 프로필의 값 정규화·컬럼 계약 검증과 CSV·붙여넣기 직렬화를 담당한다.

"""공용 공정 표시명 프로필의 값 정규화·컬럼 계약 검증과 CSV·붙여넣기 직렬화.

여기에는 **치환이 없다.** 원본 공정명을 표시명으로 바꾸는 헬퍼는 렌더 계층
(`components/process_labels.py`)에만 두고 서비스는 그것을 import 하지 않는다. 서비스가
표시명을 다루기 시작하면 계산·조인 키가 화면 라벨을 따라가고, `공정` 은 `RQ_*` 여러 표의
1급 조인 키라 그 순간 merge 가 조용히 어긋난다.
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from capa_simulation.services.clipboard_table import parse_clipboard_table

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


def empty_process_rename_rules() -> pd.DataFrame:
    """아직 아무것도 지정하지 않은 정상 상태의 빈 규칙 프레임."""
    return pd.DataFrame({column: pd.Series(dtype="object") for column in PROCESS_RENAME_COLUMNS})


def validate_process_rename_frame(frame: pd.DataFrame) -> None:
    """컬럼 계약과 1:1 규칙을 검사한다. 빈 프레임은 '지정 없음' 이라 허용한다."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("공정 표시명은 pandas DataFrame이어야 합니다.")
    missing = [column for column in PROCESS_RENAME_COLUMNS if column not in frame.columns]
    extra = [column for column in frame.columns if column not in PROCESS_RENAME_COLUMNS]
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"누락: {', '.join(missing)}")
        if extra:
            details.append(f"추가: {', '.join(str(column) for column in extra)}")
        raise ValueError(f"공정 표시명 컬럼 계약이 일치하지 않습니다 ({'; '.join(details)}).")

    normalized = {
        column: [normalize_process_text(value) for value in frame[column]]
        for column in PROCESS_RENAME_COLUMNS
    }
    for column, label in (("공정", "원본 공정명"), ("표시명", "표시명")):
        if any(not value for value in normalized[column]):
            raise ValueError(f"{label}은(는) 비어 있을 수 없습니다.")
        duplicates = sorted(
            {value for value in normalized[column] if normalized[column].count(value) > 1}
        )
        if duplicates:
            raise ValueError(
                f"{label}이(가) 중복되었습니다: {', '.join(duplicates[:5])}. "
                "원본 공정과 표시명은 항상 1:1이어야 합니다."
            )


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


def process_rename_from_csv(content: bytes) -> pd.DataFrame:
    """UTF-8 또는 CP949 CSV 를 읽어 전체 계약을 검증한다."""
    if not content:
        raise ValueError("공정 표시명 CSV 파일이 비어 있습니다.")
    parsed: pd.DataFrame | None = None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            parsed = pd.read_csv(
                BytesIO(content),
                encoding=encoding,
                keep_default_na=False,
                na_values=[""],
            )
        except UnicodeDecodeError:
            continue
        break
    if parsed is None:
        raise ValueError("공정 표시명 CSV는 UTF-8 또는 CP949 인코딩이어야 합니다.")
    return validate_process_rename_import(parsed)


def process_rename_from_clipboard(content: str) -> pd.DataFrame:
    """헤더를 포함한 Excel 붙여넣기 블록을 읽어 전체 계약을 검증한다."""
    return validate_process_rename_import(parse_clipboard_table(content, "공정 표시명"))


def validate_process_rename_import(parsed: pd.DataFrame) -> pd.DataFrame:
    """전송수단(CSV·클립보드)과 무관한 입력 계약 검증 한 곳."""
    actual_columns = [str(column).strip() for column in parsed.columns]
    expected_columns = list(PROCESS_RENAME_COLUMNS)
    if actual_columns != expected_columns:
        missing = [column for column in expected_columns if column not in actual_columns]
        extra = [column for column in actual_columns if column not in expected_columns]
        details: list[str] = []
        if missing:
            details.append(f"누락: {', '.join(missing)}")
        if extra:
            details.append(f"추가: {', '.join(extra)}")
        if not details:
            details.append("컬럼 순서가 양식과 다름")
        raise ValueError(
            f"공정 표시명 입력 표 컬럼 계약이 일치하지 않습니다 ({'; '.join(details)})."
        )
    parsed.columns = expected_columns
    return prepare_process_rename_rules(drop_blank_process_rename_rows(parsed))
