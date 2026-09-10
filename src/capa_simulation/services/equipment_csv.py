# Purpose: CSV templates, parsing, preview, and natural-key merge for equipment operations.

"""CSV templates, parsing, preview, and natural-key merge for equipment operations."""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO

import pandas as pd

from capa_simulation.services.clipboard_table import parse_clipboard_table
from capa_simulation.services.equipment_contract import (
    DOWNTIME_COLUMNS,
    DOWNTIME_KEY_COLUMNS,
    EQUIPMENT_COLUMNS,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_schedule,
    prepare_equipment_master,
)

SAMPLE_EQUIPMENT_ID = "SAM01"
SAMPLE_EQUIPMENT_MANAGER = "홍길동"
SAMPLE_EQUIPMENT_NOTE = "이력 기록"
SAMPLE_DOWNTIME_NOTE = "내용 기록"

# 호기를 비워 둔 안내 행. 열별 허용값만 나열하며 `prepare_equipment_master` 가 버린다.
EQUIPMENT_CHOICE_ROWS: tuple[dict[str, str], ...] = (
    {"라인구분": "PKG", "활용구분": "WLP", "투자기준": "322K", "확정상태": "확정"},
    {"활용구분": "2.5D", "확정상태": "완료"},
    {"활용구분": "HCB", "확정상태": "지연"},
)


def equipment_csv_template() -> bytes:
    return _to_csv_bytes(
        pd.DataFrame(
            [
                {
                    "호기": SAMPLE_EQUIPMENT_ID,
                    "공정대분류": "Wafer_Sorter",
                    "공정소분류": "Wafer_Sorter_P878",
                    "라인구분": "FRONT",
                    "활용구분": "HBM",
                    "투자기준": "299K",
                    "담당자": SAMPLE_EQUIPMENT_MANAGER,
                    "Maker": "KOREATECHNO",
                    "모델": "KTLMS-3404B",
                    "분류1": "",
                    "분류2": "",
                    "분류3": "",
                    "동": "C1",
                    "층": "4F",
                    "X좌표": "",
                    "Y좌표": "",
                    "Xsize": "",
                    "Ysize": "",
                    "제진대일정": "2026-09-01",
                    "물류일정": "2026-09-03",
                    "입고일정": "2026-09-05",
                    "Qual일정": "2026-09-16",
                    "확정상태": "계획",
                    "반출일정": "",
                    "이설일": "",
                    "장기보관여부": "N",
                    "기존설비여부": "N",
                    "호기이력": "호기 변동 이력 기록",
                    "비고": SAMPLE_EQUIPMENT_NOTE,
                    "레이아웃표시": "N",
                },
                *EQUIPMENT_CHOICE_ROWS,
            ],
            columns=EQUIPMENT_COLUMNS,
        ).fillna("")
    )


def downtime_csv_template() -> bytes:
    return _to_csv_bytes(
        pd.DataFrame(
            [
                {
                    "호기": SAMPLE_EQUIPMENT_ID,
                    "비가동유형": "고장",
                    "시작일": "2026-10-01",
                    "종료일": "2026-10-03",
                    "상세사유": "사유 기록",
                    "비고": SAMPLE_DOWNTIME_NOTE,
                }
            ],
            columns=DOWNTIME_COLUMNS,
        )
    )


def read_equipment_csv(payload: bytes) -> pd.DataFrame:
    return prepare_equipment_master(_read_csv(payload, EQUIPMENT_COLUMNS, "호기 마스터"))


def read_downtime_csv(payload: bytes, *, equipment: pd.DataFrame) -> pd.DataFrame:
    return prepare_downtime_schedule(
        _read_csv(payload, DOWNTIME_COLUMNS, "비가동 일정"),
        equipment=equipment,
    )


def read_equipment_clipboard(content: str) -> pd.DataFrame:
    return prepare_equipment_master(
        _select_columns(
            parse_clipboard_table(content, "호기 마스터"), EQUIPMENT_COLUMNS, "호기 마스터"
        )
    )


def read_downtime_clipboard(content: str, *, equipment: pd.DataFrame) -> pd.DataFrame:
    return prepare_downtime_schedule(
        _select_columns(
            parse_clipboard_table(content, "비가동 일정"),
            DOWNTIME_COLUMNS,
            "비가동 일정",
        ),
        equipment=equipment,
    )


def merge_equipment_rows(current: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    return prepare_equipment_master(_merge_by_keys(current, incoming, ("호기",)))


def merge_downtime_rows(
    current: pd.DataFrame,
    incoming: pd.DataFrame,
    *,
    equipment: pd.DataFrame,
) -> pd.DataFrame:
    merged = _merge_by_keys(current, incoming, DOWNTIME_KEY_COLUMNS)
    return prepare_downtime_schedule(merged, equipment=equipment)


def build_equipment_import_preview(
    current: pd.DataFrame,
    incoming: pd.DataFrame,
) -> pd.DataFrame:
    return _build_import_preview(current, incoming, ("호기",))


def build_downtime_import_preview(
    current: pd.DataFrame,
    incoming: pd.DataFrame,
) -> pd.DataFrame:
    return _build_import_preview(current, incoming, DOWNTIME_KEY_COLUMNS)


def _read_csv(payload: bytes, columns: tuple[str, ...], label: str) -> pd.DataFrame:
    if not payload:
        raise ValueError(f"{label} CSV 파일이 비어 있습니다.")
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            frame = pd.read_csv(BytesIO(payload), encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise ValueError(f"{label} CSV 인코딩은 UTF-8 또는 CP949여야 합니다.") from last_error
    return _select_columns(frame, columns, label)


def _select_columns(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    label: str,
) -> pd.DataFrame:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{label} 필수 컬럼이 없습니다: {', '.join(missing)}")
    return frame.loc[:, columns]


def _merge_by_keys(
    current: pd.DataFrame,
    incoming: pd.DataFrame,
    keys: tuple[str, ...],
) -> pd.DataFrame:
    if incoming.empty:
        return current.copy().reset_index(drop=True)
    current_index = pd.MultiIndex.from_frame(current.loc[:, keys])
    incoming_index = pd.MultiIndex.from_frame(incoming.loc[:, keys])
    current_without_updates = current.loc[~current_index.isin(incoming_index)]
    return pd.concat([current_without_updates, incoming], ignore_index=True)


def _build_import_preview(
    current: pd.DataFrame,
    incoming: pd.DataFrame,
    keys: tuple[str, ...],
) -> pd.DataFrame:
    """Classify incoming rows as new or replacement and list changed columns."""
    if incoming.empty:
        result = incoming.copy()
        result.insert(0, "변경내용", pd.Series(dtype="string"))
        result.insert(0, "변경컬럼", pd.Series(dtype="string"))
        result.insert(0, "Import구분", pd.Series(dtype="string"))
        return result
    current_by_key = {_row_key(row, keys): row for _, row in current.iterrows()}
    actions: list[str] = []
    changed_columns: list[str] = []
    change_details: list[str] = []
    for _, incoming_row in incoming.iterrows():
        previous = current_by_key.get(_row_key(incoming_row, keys))
        if previous is None:
            actions.append("신규")
            changed_columns.append("-")
            change_details.append("-")
            continue
        actions.append("대체")
        changes = [
            column
            for column in incoming.columns
            if column not in keys and not _same_value(previous.get(column), incoming_row[column])
        ]
        changed_columns.append(", ".join(changes) if changes else "변경 없음")
        change_details.append(
            "; ".join(
                f"{column}: {_format_value(previous.get(column))} → "
                f"{_format_value(incoming_row[column])}"
                for column in changes
            )
            if changes
            else "변경 없음"
        )
    result = incoming.copy()
    result.insert(0, "변경내용", pd.Series(change_details, dtype="string"))
    result.insert(0, "변경컬럼", pd.Series(changed_columns, dtype="string"))
    result.insert(0, "Import구분", pd.Series(actions, dtype="string"))
    return result.reset_index(drop=True)


def _row_key(row: pd.Series, keys: Sequence[str]) -> tuple[object, ...]:
    return tuple(row[key] for key in keys)


def _same_value(left: object, right: object) -> bool:
    left_missing = bool(pd.Series([left]).isna().iloc[0])
    right_missing = bool(pd.Series([right]).isna().iloc[0])
    if left_missing and right_missing:
        return True
    if isinstance(left, pd.Timestamp) and isinstance(right, pd.Timestamp):
        return left == right
    return str(left) == str(right)


def _format_value(value: object) -> str:
    if bool(pd.Series([value]).isna().iloc[0]):
        return "(빈 값)"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _to_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")
