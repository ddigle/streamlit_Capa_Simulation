# Purpose: CSV templates, parsing, preview, and natural-key merge for equipment operations.

"""CSV templates, parsing, preview, and natural-key merge for equipment operations."""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from typing import Any

import numpy as np
import pandas as pd

from capa_simulation.services.clipboard_table import (
    TEXT_TABLE_READ_OPTIONS,
    parse_clipboard_table,
)
from capa_simulation.services.equipment_contract import (
    BASELINE_COLUMNS,
    BASELINE_KEY_COLUMNS,
    DOWNTIME_COLUMNS,
    DOWNTIME_KEY_COLUMNS,
    EQUIPMENT_COLUMNS,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_schedule,
    prepare_equipment_baseline,
    prepare_equipment_master,
)
from capa_simulation.services.floor_layout_profile import FloorCanvasMap
from capa_simulation.services.frame_contracts import require_columns
from capa_simulation.services.reference_csv import (
    excel_text_guard_needed,
    strip_excel_text_guard,
)

SAMPLE_EQUIPMENT_ID = "SAM01"
SAMPLE_EQUIPMENT_MANAGER = "홍길동"
SAMPLE_EQUIPMENT_NOTE = "이력 기록"
SAMPLE_DOWNTIME_NOTE = "내용 기록"
# 기존 보유대수 양식의 예시 한 줄. `공정` 은 호기 마스터의 `공정소분류` 와 이어 붙는 값이다.
# 비고 상수 이름에 `TEMPLATE` 을 넣는다. `equipment_samples.SAMPLE_BASELINE_NOTE` 는 저장
# 가드가 손대지 않은 개발 샘플 행을 가려내는 표식이라 같은 이름을 쓰면 의미가 뒤섞인다.
SAMPLE_BASELINE_PROCESS = "Wafer_Sorter_P878"
SAMPLE_BASELINE_CATEGORY = "전체"
SAMPLE_BASELINE_COUNT = 12
SAMPLE_BASELINE_TEMPLATE_NOTE = "집계 근거 기록"

# 호기를 비워 둔 안내 행. 열별 허용값만 나열하며 `prepare_equipment_master` 가 버린다.
EQUIPMENT_CHOICE_ROWS: tuple[dict[str, str], ...] = (
    {"라인구분": "PKG", "활용구분": "WLP", "투자기준": "322K", "확정상태": "확정"},
    {"활용구분": "2.5D", "확정상태": "완료"},
    {"활용구분": "HCB", "확정상태": "지연"},
)


def baseline_csv_template() -> bytes:
    """기존 보유대수 양식. 예시 한 줄만 담고 허용값 안내 행은 두지 않는다.

    `분류` 에 허용값 목록이 없고, `prepare_equipment_baseline` 이 공정·분류·기존보유대수
    셋 중 하나만 채워져 있어도 행을 남기므로 안내 행이 곧바로 누락값 오류가 된다.
    """
    return _to_csv_bytes(
        pd.DataFrame(
            [
                {
                    "공정": SAMPLE_BASELINE_PROCESS,
                    "분류": SAMPLE_BASELINE_CATEGORY,
                    "기존보유대수": SAMPLE_BASELINE_COUNT,
                    "비고": SAMPLE_BASELINE_TEMPLATE_NOTE,
                }
            ],
            columns=BASELINE_COLUMNS,
        )
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
                    # 기준 모델이 1 이다. 비워 두면 검증이 1 로 채운다.
                    "환산비": "1",
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


# 내보낼 때 Excel 텍스트 가드를 씌우는 컬럼. 기준 정보 쪽과 같은 원칙이다 — **식별에 쓰는
# 컬럼만** 지킨다. 행을 가르는 값이 `0123` → `123` 으로 바뀌면 같은 행이 새 행으로 들어와
# 표 전체가 어긋나지만, 좌표·대수·환산비는 숫자로 읽히는 것이 맞고 날짜는 Excel 이 그대로
# 돌려준다(한국어 Excel 로 실측). 그래서 숫자·날짜 컬럼에는 씌우지 않는다.
EQUIPMENT_GUARDED_COLUMNS: tuple[str, ...] = ("호기",)
BASELINE_GUARDED_COLUMNS: tuple[str, ...] = BASELINE_KEY_COLUMNS
DOWNTIME_GUARDED_COLUMNS: tuple[str, ...] = ("호기", "비가동유형")


def equipment_csv_bytes(equipment: pd.DataFrame) -> bytes:
    """호기 마스터 **현재 데이터** 그대로. 다시 붙여넣으면 통과하는 것이 이 함수의 계약이다."""
    return _export_csv_bytes(equipment, EQUIPMENT_COLUMNS, EQUIPMENT_GUARDED_COLUMNS)


def baseline_csv_bytes(baseline: pd.DataFrame) -> bytes:
    """기존 보유대수 **현재 데이터** 그대로."""
    return _export_csv_bytes(baseline, BASELINE_COLUMNS, BASELINE_GUARDED_COLUMNS)


def downtime_csv_bytes(downtime: pd.DataFrame) -> bytes:
    """비가동 일정 **현재 데이터** 그대로."""
    return _export_csv_bytes(downtime, DOWNTIME_COLUMNS, DOWNTIME_GUARDED_COLUMNS)


def _export_csv_bytes(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    guarded_columns: tuple[str, ...],
) -> bytes:
    """읽는 쪽 계약(`columns`)과 같은 이름·차례로 내보낸다.

    - 컬럼은 계약 차례로 다시 세운다. 편집본에 없는 컬럼은 빈 칸으로 나간다 — 계약에 없는
      컬럼을 실어 보내면 읽는 쪽이 버리므로 애초에 싣지 않는다.
    - 날짜는 `YYYY-MM-DD` 다. 준비된 프레임의 날짜 컬럼은 `datetime64` 라 그냥 두면
      `2026-09-01 00:00:00` 처럼 시각까지 붙어 나갈 수 있다.
    - 빈 프레임은 헤더 한 줄만 나간다. 그 파일을 그대로 붙여넣으면 0행으로 읽힌다.
    - 식별 컬럼의 값 중 Excel 이 바꿔 놓을 것만 `="…"` 로 묶는다. 읽는 쪽(`_select_columns`)이
      그 껍데기를 벗기므로 고치지 않고 그대로 되돌려도 통과한다.
    """
    exported = frame.reindex(columns=list(columns)).copy()
    for column in guarded_columns:
        exported[column] = exported[column].map(_guard_excel_text)
    return exported.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8-sig")


def _guard_excel_text(value: object) -> object:
    if not isinstance(value, str) or not excel_text_guard_needed(value):
        return value
    return f'="{value}"'


def read_baseline_csv(payload: bytes) -> pd.DataFrame:
    return prepare_equipment_baseline(_read_csv(payload, BASELINE_COLUMNS, "기존 보유대수"))


def read_equipment_csv(
    payload: bytes,
    *,
    floor_canvases: FloorCanvasMap | None = None,
) -> pd.DataFrame:
    """`floor_canvases` 를 넘기면 읽는 즉시 층별 캔버스 좌표 상한까지 검사한다."""
    return prepare_equipment_master(
        _read_csv(payload, EQUIPMENT_COLUMNS, "호기 마스터"),
        floor_canvases=floor_canvases,
    )


def read_downtime_csv(payload: bytes, *, equipment: pd.DataFrame) -> pd.DataFrame:
    return prepare_downtime_schedule(
        _read_csv(payload, DOWNTIME_COLUMNS, "비가동 일정"),
        equipment=equipment,
    )


def read_baseline_clipboard(content: str) -> pd.DataFrame:
    return prepare_equipment_baseline(
        _select_columns(
            parse_clipboard_table(content, "기존 보유대수"),
            BASELINE_COLUMNS,
            "기존 보유대수",
        )
    )


def untouched_template_baseline_rows(baseline: pd.DataFrame) -> pd.DataFrame:
    """양식에 실어 보낸 **예시 한 줄이 그대로 남은** 행만 골라낸다.

    예시 행은 네 컬럼이 다 채워져 있어 `prepare_equipment_baseline` 을 그냥 통과한다. 지우지
    않고 저장하면 존재하지 않는 공정 하나가 불변 리비전에 영구 기록되고, 호기 마스터에 붙지
    않는 유령 공정이 총대수·가용대수·가용률에 영원히 섞인다.

    `equipment_samples.untouched_sample_baseline_rows` 와 **같은 위험, 다른 출처**다. 저쪽은
    DB 가 비었을 때 화면에 채워 준 표시용 샘플이고, 이쪽은 사용자가 내려받은 양식의 예시다.
    한 컬럼이라도 고쳤으면 그 행은 사용자의 것이므로 걸러 내지 않는다.
    """
    columns = list(BASELINE_COLUMNS)
    if baseline.empty or any(column not in baseline.columns for column in columns):
        return baseline.iloc[0:0]
    normalized = baseline.loc[:, columns].copy()
    for column in ("공정", "분류", "비고"):
        normalized[column] = normalized[column].astype("string").str.strip()
    normalized["기존보유대수"] = pd.to_numeric(normalized["기존보유대수"], errors="coerce")
    example = (
        normalized["공정"].eq(SAMPLE_BASELINE_PROCESS)
        & normalized["분류"].eq(SAMPLE_BASELINE_CATEGORY)
        & normalized["기존보유대수"].eq(SAMPLE_BASELINE_COUNT)
        & normalized["비고"].eq(SAMPLE_BASELINE_TEMPLATE_NOTE)
    )
    return baseline.loc[example.fillna(False).to_numpy()]


def read_equipment_clipboard(
    content: str,
    *,
    floor_canvases: FloorCanvasMap | None = None,
) -> pd.DataFrame:
    """`floor_canvases` 를 넘기면 붙여넣기 시점에 층별 캔버스 좌표 상한까지 검사한다."""
    return prepare_equipment_master(
        _select_columns(
            parse_clipboard_table(content, "호기 마스터"), EQUIPMENT_COLUMNS, "호기 마스터"
        ),
        floor_canvases=floor_canvases,
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


def merge_baseline_rows(current: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    return prepare_equipment_baseline(_merge_by_keys(current, incoming, BASELINE_KEY_COLUMNS))


def merge_equipment_rows(
    current: pd.DataFrame,
    incoming: pd.DataFrame,
    *,
    floor_canvases: FloorCanvasMap | None = None,
) -> pd.DataFrame:
    """`floor_canvases` 를 넘기면 편집본에 적용하기 전에 층별 좌표 상한까지 검사한다."""
    return prepare_equipment_master(
        _merge_by_keys(current, incoming, ("호기",)),
        floor_canvases=floor_canvases,
    )


def merge_downtime_rows(
    current: pd.DataFrame,
    incoming: pd.DataFrame,
    *,
    equipment: pd.DataFrame,
) -> pd.DataFrame:
    merged = _merge_by_keys(current, incoming, DOWNTIME_KEY_COLUMNS)
    return prepare_downtime_schedule(merged, equipment=equipment)


def build_baseline_import_preview(
    current: pd.DataFrame,
    incoming: pd.DataFrame,
) -> pd.DataFrame:
    return _build_import_preview(current, incoming, BASELINE_KEY_COLUMNS)


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
            # 붙여넣기 경로와 같은 옵션을 쓴다. pandas 기본값은 `NA`·`N/A` 를 결측으로
            # 바꾸므로, 같은 파일이 전송 경로에 따라 다른 결측 판정을 받는다.
            frame = pd.read_csv(BytesIO(payload), encoding=encoding, **TEXT_TABLE_READ_OPTIONS)
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
    require_columns(frame, columns, label)
    selected = frame.loc[:, columns].copy()
    # 내보내기가 식별 컬럼에 씌운 `="…"` 껍데기를 벗긴다. Excel 을 거친 값은 이미 벗겨져
    # 오고, 고치지 않고 그대로 되돌린 파일만 껍데기를 달고 온다 — 어느 쪽이든 같은 값이다.
    for column in columns:
        selected[column] = selected[column].map(strip_excel_text_guard)
    return selected


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
    # **인덱스를 먼저 버린다.** 아래 세 목록은 행 순서대로 쌓았는데, `insert` 는 Series 를
    # **인덱스로 맞춰** 넣는다. `incoming` 의 인덱스가 0 부터가 아니면(필터로 고른 행, 이어
    # 붙인 프레임) 전부 어긋나 판정이 통째로 `<NA>` 가 된다. 지금 호출부는 우연히 0 기반이라
    # 드러나지 않았을 뿐이다.
    result = incoming.reset_index(drop=True)
    result.insert(0, "변경내용", pd.Series(change_details, dtype="string"))
    result.insert(0, "변경컬럼", pd.Series(changed_columns, dtype="string"))
    result.insert(0, "Import구분", pd.Series(actions, dtype="string"))
    return result


def _row_key(row: pd.Series, keys: Sequence[str]) -> tuple[object, ...]:
    return tuple(row[key] for key in keys)


def _is_missing(value: object) -> bool:
    """칸 하나가 비었는가.

    `pd.Series([value]).isna()` 로 재면 **칸마다 Series 를 하나씩 만든다.** 31열 미리보기는
    그 호출이 행마다 수십 번이라, 실측으로 100행 944ms · 500행 4.7초 · 2,000행 19초가 나왔다
    (행당 9.4ms). 미리보기는 세션 키가 살아 있는 동안 매 rerun 다시 계산되므로 사용자가
    그 옆 위젯을 건드릴 때마다 그 시간을 다시 기다린다. `pd.isna` 는 같은 판정을 172배 빠르게
    한다 — 1만 회에 1,461ms 대 8.5ms.

    `pd.isna` 는 배열을 받으면 배열을 돌려주어 `bool()` 이 터진다. 옛 구현은 1원소 Series 를
    만들어 조용히 False 를 줬으므로, 그 동작을 유지하려면 여기서 먼저 가른다.
    """
    if isinstance(value, (list, tuple, set, dict, np.ndarray, pd.Series, pd.Index)):
        return False
    # 위에서 배열을 걸렀으므로 여기 남는 것은 스칼라뿐인데, 스텁의 오버로드는 `object` 를
    # 받지 않는다. 좁혀 준 사실을 타입 검사기에 전달할 방법이 이것뿐이다.
    scalar: Any = value
    return bool(pd.isna(scalar))


def _same_value(left: object, right: object) -> bool:
    if _is_missing(left) and _is_missing(right):
        return True
    if isinstance(left, pd.Timestamp) and isinstance(right, pd.Timestamp):
        return left == right
    return str(left) == str(right)


def _format_value(value: object) -> str:
    if _is_missing(value):
        return "(빈 값)"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _to_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")
