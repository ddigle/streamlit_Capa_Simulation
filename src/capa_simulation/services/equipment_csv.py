# Purpose: CSV templates, parsing, preview, and natural-key merge for equipment operations.

"""CSV templates, parsing, preview, and natural-key merge for equipment operations."""

from __future__ import annotations

import difflib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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
    EQUIPMENT_ID_COLUMN,
    EQUIPMENT_KEY_COLUMNS,
    LEGACY_DOWNTIME_HEADER_ALIASES,
    LEGACY_EQUIPMENT_HEADER_ALIASES,
    OBSOLETE_EQUIPMENT_COLUMNS,
    OPTIONAL_EQUIPMENT_COLUMNS,
    PARENT_EQUIPMENT_COLUMN,
    RELOCATION_DATE_COLUMN,
    compact_header,
    rename_legacy_headers,
    with_optional_equipment_columns,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_schedule,
    prepare_equipment_baseline,
    prepare_equipment_master,
)
from capa_simulation.services.floor_layout_profile import FloorCanvasMap
from capa_simulation.services.frame_contracts import require_columns
from capa_simulation.services.reference_csv import (
    guard_excel_text,
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

# 설비명을 비워 둔 안내 행. 열별 허용값만 나열하며 `prepare_equipment_master` 가 버린다.
EQUIPMENT_CHOICE_ROWS: tuple[dict[str, str], ...] = (
    {"공정구분": "PKG", "투자Capa": "322K", "투자구분": "WLP", "확정상태": "확정"},
    {"투자구분": "2.5D", "확정상태": "완료"},
    {"투자구분": "HCB", "확정상태": "지연"},
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
                    "구분": "",
                    "공정대분류": "Wafer_Sorter",
                    "공정소분류": "Wafer_Sorter_P878",
                    "Maker": "KOREATECHNO",
                    "Model": "KTLMS-3404B",
                    EQUIPMENT_ID_COLUMN: SAMPLE_EQUIPMENT_ID,
                    "공정구분": "FRONT",
                    "투자Capa": "299K",
                    "투자구분": "HBM",
                    # Dynamic 가용대수는 사용기준이 HBM·EDP 인 호기만 센다(`counts_for_capacity`).
                    "사용기준": "HBM",
                    "동": "C1",
                    "층": "4F",
                    "담당자": SAMPLE_EQUIPMENT_MANAGER,
                    "설비가동현황": "",
                    "X좌표": "",
                    "Y좌표": "",
                    "Xsize": "",
                    "Ysize": "",
                    "제진대일정": "2026-09-01",
                    "물류일정": "2026-09-03",
                    "반입일정": "2026-09-05",
                    "Qual일정": "2026-09-16",
                    "확정상태": "계획",
                    "반출일정": "",
                    RELOCATION_DATE_COLUMN: "",
                    "반입/Qual 이력": "",
                    "호기이력": "호기 변동 이력 기록",
                    "설비이력": SAMPLE_EQUIPMENT_NOTE,
                    "보관유무": "N",
                    "기존설비여부": "N",
                    "레이아웃표시": "N",
                    # 기준 모델이 1 이다. 비워 두면 검증이 1 로 채운다.
                    "환산비": "1",
                    # 모듈로 관리하는 설비만 적는다(APW01A~D → APW01). 비모듈은 비운다.
                    PARENT_EQUIPMENT_COLUMN: "",
                    "메모1": "",
                    "메모2": "",
                    "메모3": "",
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
                    EQUIPMENT_ID_COLUMN: SAMPLE_EQUIPMENT_ID,
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
EQUIPMENT_GUARDED_COLUMNS: tuple[str, ...] = (EQUIPMENT_ID_COLUMN, PARENT_EQUIPMENT_COLUMN)
BASELINE_GUARDED_COLUMNS: tuple[str, ...] = BASELINE_KEY_COLUMNS
DOWNTIME_GUARDED_COLUMNS: tuple[str, ...] = (EQUIPMENT_ID_COLUMN, "비가동유형")


def equipment_csv_bytes(equipment: pd.DataFrame) -> bytes:
    """호기 마스터 **현재 데이터** 그대로. 다시 붙여넣으면 통과하는 것이 이 함수의 계약이다.

    행은 `공정소분류` → `설비명` 오름차순이다(2026-10-08 사용자 요청). 글자 속 숫자는 수로 견준다 —
    `EQ2` 가 `EQ10` 앞이다. 빈 값은 뒤로 간다. 붙여넣기는 설비명으로 맞추므로 차례는 읽는 쪽과
    무관하다.
    """
    return _export_csv_bytes(
        _sorted_equipment(equipment), EQUIPMENT_COLUMNS, EQUIPMENT_GUARDED_COLUMNS
    )


_DIGIT_RUN = re.compile(r"(\d+)")


def _natural_key(value: object) -> tuple[bool, tuple[int | str, ...]]:
    """사람이 읽는 오름차순 키 — 빈 값은 뒤, 글자는 대소문자 무시, 숫자 덩어리는 수로."""
    text = "" if value is None or (isinstance(value, float) and np.isnan(value)) else str(value)
    text = text.strip().casefold()
    if text in {"", "nan", "<na>", "none", "nat"}:
        return (True, ())
    parts = tuple(int(part) if part.isdigit() else part for part in _DIGIT_RUN.split(text))
    return (False, parts)


def _sorted_equipment(equipment: pd.DataFrame) -> pd.DataFrame:
    """`공정소분류` → `설비명` 오름차순. 둘 중 없는 컬럼은 건너뛴다(같은 값끼리는 원래 차례)."""
    keys = [column for column in ("공정소분류", EQUIPMENT_ID_COLUMN) if column in equipment.columns]
    if not keys or len(equipment) < 2:
        return equipment
    columns = [equipment[column].tolist() for column in keys]
    order = sorted(
        range(len(equipment)), key=lambda row: tuple(_natural_key(c[row]) for c in columns)
    )
    return equipment.iloc[order]


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
        exported[column] = exported[column].map(guard_excel_text)
    return exported.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8-sig")


def read_baseline_csv(payload: bytes) -> pd.DataFrame:
    return prepare_equipment_baseline(_read_csv(payload, _BASELINE_HEADERS))


def read_equipment_csv(
    payload: bytes,
    *,
    floor_canvases: FloorCanvasMap | None = None,
    notices: list[str] | None = None,
) -> pd.DataFrame:
    """`floor_canvases` 를 넘기면 읽는 즉시 층별 캔버스 좌표 상한까지 검사한다.

    옛 머리 이름은 새 이름으로 바꿔 읽는다. 빠진 옛 컬럼(`투자기준`)을 떼어 냈으면 그 알림
    문구를 `notices` 에 덧붙인다.
    """
    return prepare_equipment_master(
        _read_csv(payload, _EQUIPMENT_HEADERS, notices=notices),
        floor_canvases=floor_canvases,
    )


def read_downtime_csv(payload: bytes, *, equipment: pd.DataFrame) -> pd.DataFrame:
    return prepare_downtime_schedule(
        _read_csv(payload, _DOWNTIME_HEADERS),
        equipment=equipment,
    )


def read_baseline_clipboard(content: str) -> pd.DataFrame:
    return prepare_equipment_baseline(
        _select_columns(parse_clipboard_table(content, _BASELINE_HEADERS.label), _BASELINE_HEADERS)
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
    notices: list[str] | None = None,
) -> pd.DataFrame:
    """`floor_canvases` 를 넘기면 붙여넣기 시점에 층별 캔버스 좌표 상한까지 검사한다.

    머리 이름 변환과 `notices` 는 `read_equipment_csv` 와 같다.
    """
    return prepare_equipment_master(
        _select_columns(
            parse_clipboard_table(content, _EQUIPMENT_HEADERS.label),
            _EQUIPMENT_HEADERS,
            notices=notices,
        ),
        floor_canvases=floor_canvases,
    )


@dataclass(frozen=True)
class EquipmentPaste:
    """편집본에 맞춰 채운 호기 마스터 붙여넣기(또는 CSV) 한 건.

    - `rows` — 검증을 마친 36컬럼 표. 붙여넣지 않은 열은 편집본의 그 호기 값이고, 새 호기는
      빈 칸이다. `merge_equipment_rows` 에 그대로 넘긴다.
    - `columns` — 붙여넣은 계약 컬럼(설비명 포함, 계약 차례).
    - `cleared_cells` — 기존 호기의 값이 있던 칸을 붙여넣은 빈 칸이 지우는 수. 검증을 거친 값으로
      센다 — 빈 환산비는 1 이 되므로 지우는 칸이 아니라 바뀌는 칸이다.
    """

    rows: pd.DataFrame
    columns: tuple[str, ...]
    cleared_cells: int = 0

    @property
    def kept_columns(self) -> tuple[str, ...]:
        """붙여넣지 않아 기존 값을 그대로 두는 계약 컬럼(계약 차례)."""
        return tuple(column for column in EQUIPMENT_COLUMNS if column not in self.columns)


def read_equipment_update(
    payload: str | bytes,
    current: pd.DataFrame,
    *,
    floor_canvases: FloorCanvasMap | None = None,
    notices: list[str] | None = None,
) -> EquipmentPaste:
    """호기 마스터 붙여넣기(글) 또는 CSV(바이트)를 **붙여넣은 열만 바꾸는** 행으로 읽는다.

    2026-10-08 사용자 요청 — 컬럼이 많으니 기준인 `설비명` 과 바꿀 열만 넣어도 검사하고 반영한다.

    - 머리에 `설비명`(옛 이름 `호기`)이 꼭 있어야 한다. 나머지 열은 아무것이나 골라 넣는다.
    - `current`(붙여넣기 전 편집본)에 있는 설비명은 붙여넣은 열만 바꾸고 나머지 열은 그 호기의 값을
      채운다. 붙여넣은 열의 빈 칸은 「그 값을 지운다」이다 — 전체 열 붙여넣기와 같다.
    - 편집본에 없는 설비명(새 호기)은 지금 새 호기에 필요한 열(선택 컬럼 밖 30개)이 다 있어야 한다.
      하나라도 없으면 막는다 — 반만 채운 호기를 받지 않는다.
    - 채운 표를 `prepare_equipment_master` 로 검증한다. 호출부가 이 표를 편집본에 합친 뒤 병합된
      전체 표를 한 번 더 검증한다(`merge_equipment_rows`) — 날짜·환산비·Main 설비·중복 규칙이
      전체 열 붙여넣기와 똑같이 돈다.

    모르는 머리글은 `_select_update_columns` 가 다룬다. 옛 머리 이름 변환과 `notices` 는
    `read_equipment_csv` 와 같다.
    """
    label = _EQUIPMENT_HEADERS.label
    frame = (
        _read_csv_frame(payload, label)
        if isinstance(payload, bytes)
        else parse_clipboard_table(payload, label)
    )
    pasted = _select_update_columns(frame, notices=notices)
    columns = tuple(str(column) for column in pasted.columns)
    # 설비명이 빈 행(양식의 허용값 안내 행)은 전체 열 붙여넣기처럼 버린다. 남기면 새 호기로 세어
    # 「필요한 열이 없다」로 막힌다.
    ids = pasted[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    named = (ids.notna() & ids.ne("")).fillna(False).to_numpy()
    pasted = pasted.loc[named].copy()
    pasted[EQUIPMENT_ID_COLUMN] = ids.loc[named]
    pasted = pasted.reset_index(drop=True)

    base = _rows_by_equipment_id(current)
    matched = pasted[EQUIPMENT_ID_COLUMN].isin(base.index)
    # 새 호기 검사는 검증 **앞**이다. 뒤에 하면 「공정소분류에 누락값」 같은 엉뚱한 문구가
    # 먼저 뜬다.
    needed = [
        column
        for column in EQUIPMENT_COLUMNS
        if column not in OPTIONAL_EQUIPMENT_COLUMNS and column not in columns
    ]
    if needed and not matched.all():
        raise ValueError(
            _new_units_message(pasted.loc[~matched, EQUIPMENT_ID_COLUMN].tolist(), needed)
        )
    filled = pasted.reindex(columns=list(EQUIPMENT_COLUMNS))
    for column in EQUIPMENT_COLUMNS:
        if column not in columns:
            # 새 호기는 비어 있다(위 검사로 선택 컬럼만 남았다).
            filled[column] = pasted[EQUIPMENT_ID_COLUMN].map(base[column])
    rows = prepare_equipment_master(filled, floor_canvases=floor_canvases)
    return EquipmentPaste(rows, columns, _cleared_cells(base, rows, columns))


def _rows_by_equipment_id(current: pd.DataFrame) -> pd.DataFrame:
    """편집본을 설비명(앞뒤 공백을 뗀다 — 편집본은 검증 전일 수 있다)으로 찾는 표.

    설비명이 빈 행은 맞출 수 없으니 뺀다. 같은 이름이 둘이면 마지막 행이다 — 미리보기
    (`_build_import_preview`)가 대조하는 행과 같다. `map` 은 겹친 인덱스를 받지 않는다.
    """
    frame = with_optional_equipment_columns(current)
    require_columns(frame, EQUIPMENT_COLUMNS, _EQUIPMENT_HEADERS.label)
    ids = frame[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    named = (ids.notna() & ids.ne("")).fillna(False).to_numpy()
    keyed = frame.loc[named, list(EQUIPMENT_COLUMNS)].copy()
    keyed[EQUIPMENT_ID_COLUMN] = ids.loc[named]
    return keyed.drop_duplicates(EQUIPMENT_ID_COLUMN, keep="last").set_index(EQUIPMENT_ID_COLUMN)


def _new_units_message(names: Sequence[object], needed: Sequence[str]) -> str:
    shown = ", ".join(str(name) for name in names[:5])
    more = f" 외 {len(names) - 5}건" if len(names) > 5 else ""
    return (
        f"지금 호기 마스터에 없는 설비명 {len(names):,}건({shown}{more})은 새 호기로 추가되는데, "
        f"새 호기에 필요한 열 {len(needed)}개가 붙여넣은 표에 없습니다: {' · '.join(needed)}. "
        "새 호기를 넣으려면 이 열도 함께 붙여넣거나, 새 호기만 양식(전체 열)으로 따로 "
        "붙여넣으세요. 기존 호기만 고치려던 것이면 설비명이 맞는지 확인하세요."
    )


def _blank_cells(values: pd.Series) -> pd.Series:
    return values.astype("string").str.strip().fillna("").eq("")


def _cleared_cells(base: pd.DataFrame, rows: pd.DataFrame, columns: Sequence[str]) -> int:
    """붙여넣은 열에서 기존 값이 있던 칸이 빈 칸이 되는 수. 새 호기는 세지 않는다."""
    if base.empty or rows.empty:
        return 0
    names = rows[EQUIPMENT_ID_COLUMN]
    cleared = 0
    for column in columns:
        if column == EQUIPMENT_ID_COLUMN:
            continue
        before = names.map(base[column])
        cleared += int((~_blank_cells(before) & _blank_cells(rows[column])).sum())
    return cleared


def read_downtime_clipboard(content: str, *, equipment: pd.DataFrame) -> pd.DataFrame:
    return prepare_downtime_schedule(
        _select_columns(parse_clipboard_table(content, _DOWNTIME_HEADERS.label), _DOWNTIME_HEADERS),
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
        _merge_by_keys(current, incoming, EQUIPMENT_KEY_COLUMNS),
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
    *,
    columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    """`columns`(붙여넣은 열, `EquipmentPaste.columns`)를 주면 그 열만 견주고 보여 준다.

    붙여넣지 않은 열은 편집본 값을 채운 것이라 바뀌지 않는다. 그래도 견주면 편집본의 다듬기 전
    값(「 HBM 」)이 검증을 거친 값(「HBM」)과 달라 「변경」으로 잡힌다.
    """
    return _build_import_preview(current, incoming, EQUIPMENT_KEY_COLUMNS, columns=columns)


def build_downtime_import_preview(
    current: pd.DataFrame,
    incoming: pd.DataFrame,
) -> pd.DataFrame:
    return _build_import_preview(current, incoming, DOWNTIME_KEY_COLUMNS)


@dataclass(frozen=True)
class _TableHeaders:
    """입구 하나가 받는 표의 머리 계약. 옛 이름 변환표는 표마다 따로다."""

    label: str
    columns: tuple[str, ...]
    optional: tuple[str, ...] = ()
    aliases: Mapping[str, str] = field(default_factory=dict)
    obsolete: tuple[str, ...] = ()


_EQUIPMENT_HEADERS = _TableHeaders(
    "호기 마스터",
    EQUIPMENT_COLUMNS,
    optional=OPTIONAL_EQUIPMENT_COLUMNS,
    aliases=LEGACY_EQUIPMENT_HEADER_ALIASES,
    obsolete=OBSOLETE_EQUIPMENT_COLUMNS,
)
_DOWNTIME_HEADERS = _TableHeaders(
    "비가동 일정", DOWNTIME_COLUMNS, aliases=LEGACY_DOWNTIME_HEADER_ALIASES
)
_BASELINE_HEADERS = _TableHeaders("기존 보유대수", BASELINE_COLUMNS)


def _read_csv(
    payload: bytes,
    headers: _TableHeaders,
    *,
    notices: list[str] | None = None,
) -> pd.DataFrame:
    return _select_columns(_read_csv_frame(payload, headers.label), headers, notices=notices)


def _read_csv_frame(payload: bytes, label: str) -> pd.DataFrame:
    """CSV 바이트를 글자 그대로의 표로 읽는다(머리 이름 변환·컬럼 고르기 전)."""
    if not payload:
        raise ValueError(f"{label} CSV 파일이 비어 있습니다.")
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            # 붙여넣기 경로와 같은 옵션을 쓴다. pandas 기본값은 `NA`·`N/A` 를 결측으로
            # 바꾸므로, 같은 파일이 전송 경로에 따라 다른 결측 판정을 받는다. 옵션 묶음이
            # `Any` 라 반환 타입이 풀린다 — 받는 쪽에서 다시 묶는다.
            frame: pd.DataFrame = pd.read_csv(
                BytesIO(payload), encoding=encoding, **TEXT_TABLE_READ_OPTIONS
            )
            # 붙여넣기 경로처럼 머리글 앞뒤 공백을 뗀다. Excel 이 저장한 「Main 설비 」가
            # 없는 열로 읽히면 선택 컬럼은 조용히 빈 칸이 된다.
            frame.columns = [str(column).strip() for column in frame.columns]
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise ValueError(f"{label} CSV 인코딩은 UTF-8 또는 CP949여야 합니다.") from last_error
    return frame


def _select_columns(
    frame: pd.DataFrame,
    headers: _TableHeaders,
    *,
    notices: list[str] | None = None,
) -> pd.DataFrame:
    """옛 머리 이름을 새 이름으로 바꾼 뒤 계약 컬럼만 계약 차례로 고른다(표 전체를 읽는 입구).

    옛 이름 변환이 **먼저**다. 뒤에 하면 옛 이름(「모체호기」)이 아래의 닮은 이름 검사를
    빠져나가 선택 컬럼이 조용히 빈 칸이 된다. 빠진 옛 컬럼(`투자기준`)은 떼어 내고 알림 한
    줄을 `notices` 에 덧붙인다.

    `headers.optional` 은 없어도 되는 컬럼이다. 없으면 빈 칸으로 채운다 — 그 컬럼이 생기기
    전의 양식도 그대로 읽힌다. 이 표로 `merge_equipment_rows` 를 바로 부르면 **대체 행의 그 칸은
    빈 값으로 바뀐다.** RawData 붙여넣기는 이 입구가 아니라 `read_equipment_update` 를 타서
    붙여넣지 않은 열의 값을 지킨다.
    """
    label, columns = headers.label, headers.columns
    frame, dropped = rename_legacy_headers(
        frame, columns, headers.aliases, label, obsolete=headers.obsolete
    )
    if notices is not None:
        notices.extend(dropped)
    missing = [column for column in headers.optional if column not in frame.columns]
    _reject_lookalike_headers(frame, headers, missing)
    if missing:
        frame = frame.reindex(columns=[*frame.columns, *missing])
        if notices is not None:
            notices.append(
                f"{label}에 {' · '.join(missing)} 열이 없어 빈칸으로 읽었습니다. 이 파일로 바꾸는 "
                "행은 그 칸의 저장된 값이 지워집니다 — 「변경컬럼」을 확인하세요."
            )
    require_columns(frame, columns, label)
    selected = frame.loc[:, columns].copy()
    # 내보내기가 식별 컬럼에 씌운 `="…"` 껍데기를 벗긴다. Excel 을 거친 값은 이미 벗겨져
    # 오고, 고치지 않고 그대로 되돌린 파일만 껍데기를 달고 온다 — 어느 쪽이든 같은 값이다.
    for column in columns:
        selected[column] = selected[column].map(strip_excel_text_guard)
    return selected


def _reject_lookalike_headers(
    frame: pd.DataFrame, headers: _TableHeaders, missing: Sequence[str]
) -> None:
    """빠진 선택 컬럼과 이름이 닮은 머리글이 있으면 막는다.

    이름이 조금 틀린 선택 컬럼(「Main 설비(선택)」·「모체호기(선택)」)을 빈 칸으로 읽으면
    모듈 행이 모두 따로 세어진다. 필수 컬럼은 이름이 틀리면 막히는데 선택 컬럼만 조용하면
    안 된다. 옛 이름으로 적은 닮은 이름도 잡는다.
    """
    for column in missing:
        names = [column, *(old for old, new in headers.aliases.items() if new == column)]
        lookalikes = [
            str(header)
            for header in frame.columns
            if header not in headers.columns
            and any(compact_header(name) in compact_header(header) for name in names)
        ]
        if lookalikes:
            raise ValueError(
                f"{headers.label}의 {column} 열 이름이 다릅니다: {lookalikes} — 머리글을 "
                f"「{column}」로 고치세요."
            )


# 머리글이 빈 열. 두 입구 모두 pandas 가 「Unnamed: 3」 같은 이름을 붙인다.
_UNNAMED_HEADER = re.compile(r"Unnamed: \d+")


def _select_update_columns(
    frame: pd.DataFrame,
    *,
    notices: list[str] | None = None,
) -> pd.DataFrame:
    """일부 열 붙여넣기(`read_equipment_update`)의 머리글을 읽고 붙여넣은 계약 컬럼만 고른다.

    옛 이름 변환·빠진 옛 컬럼 알림·닮은 선택 컬럼 검사는 `_select_columns` 와 같다. 다른 점:

    - `설비명` 하나만 꼭 있어야 하고, 나머지는 있는 열만 계약 차례로 고른다(빈 칸을 채우지 않는다).
    - 설비명 말고 고를 열이 없으면 막는다 — 아무것도 바꾸지 않는 붙여넣기다.
    - **모르는 머리글**: 필수 컬럼이 다 있는 붙여넣기는 읽지 않고 넘기되 알림 한 줄을 남긴다. 필수
      컬럼이 하나라도 빠진 붙여넣기(일부 열만 고른 것)에서는 막는다 — 고른 열마다 바꾸려는 뜻이
      있으니, 이름이 틀린 열(「Qual일졍」)을 조용히 빼면 사용자는 바꿨다고 믿는데 그 열은 그대로다.
      머리글이 빈 열은 값도 비어 있으면 Excel 이 범위 끝에 딸려 보낸 것이라 그냥 뺀다.
    """
    headers = _EQUIPMENT_HEADERS
    label, contract = headers.label, headers.columns
    frame, dropped = rename_legacy_headers(
        frame, contract, headers.aliases, label, obsolete=headers.obsolete
    )
    if notices is not None:
        notices.extend(dropped)
    empty_unnamed = [
        header
        for header in frame.columns
        if _UNNAMED_HEADER.fullmatch(str(header)) and _blank_cells(frame[header]).all()
    ]
    frame = frame.drop(columns=empty_unnamed)
    missing = [column for column in contract if column not in frame.columns]
    _reject_lookalike_headers(frame, headers, [c for c in missing if c in headers.optional])
    if EQUIPMENT_ID_COLUMN not in frame.columns:
        raise ValueError(
            f"{label} 붙여넣기에는 {EQUIPMENT_ID_COLUMN} 열이 꼭 있어야 합니다 — 어느 호기를 "
            f"바꿀지 {EQUIPMENT_ID_COLUMN}으로 찾습니다. 머리글 줄까지 함께 복사했는지 확인하세요."
        )
    unknown = [str(header) for header in frame.columns if header not in contract]
    partial = any(column not in headers.optional for column in missing)
    if unknown and partial:
        raise ValueError(
            f"{label}에 없는 열이 있습니다: {_describe_unknown_headers(unknown, missing)}. "
            "바꿀 열만 붙여넣을 때 이름이 틀린 열을 빼고 읽으면 그 열은 바뀌지 않으므로 막습니다 — "
            "머리글을 호기 마스터 열 이름으로 고치거나 그 열을 빼고 다시 붙여넣으세요."
        )
    if unknown and notices is not None:
        notices.append(
            f"{label}에 없는 열 {_describe_unknown_headers(unknown, missing)}은 읽지 않았습니다."
        )
    present = [column for column in contract if column in frame.columns]
    if present == [EQUIPMENT_ID_COLUMN]:
        raise ValueError(
            f"{label} 붙여넣기에 {EQUIPMENT_ID_COLUMN} 말고 바꿀 열이 없습니다 — "
            f"{EQUIPMENT_ID_COLUMN}과 함께 바꿀 열을 머리글째 붙여넣으세요."
        )
    selected = frame.loc[:, present].copy()
    for column in present:
        selected[column] = selected[column].map(strip_excel_text_guard)
    return selected


def _describe_unknown_headers(unknown: Sequence[str], missing: Sequence[str]) -> str:
    """모르는 머리글마다 빠진 열 가운데 가장 닮은 이름을 붙인다(옛 이름도 견준다)."""
    candidates = {compact_header(column): column for column in missing}
    for old, new in LEGACY_EQUIPMENT_HEADER_ALIASES.items():
        if new in missing:
            candidates.setdefault(compact_header(old), new)
    described = []
    for header in unknown:
        close = difflib.get_close_matches(compact_header(header), list(candidates), n=1, cutoff=0.6)
        hint = f"(「{candidates[close[0]]}」?)" if close else ""
        described.append(f"「{header}」{hint}")
    return ", ".join(described)


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
    *,
    columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Classify incoming rows as new or replacement and list changed columns.

    `columns` 를 주면 그 열만 견주고 결과 표에도 그 열만 싣는다. 키는 빠져 있으면 앞에 붙인다.
    """
    shown = (
        incoming
        if columns is None
        else incoming.loc[:, [*(key for key in keys if key not in columns), *columns]]
    )
    if incoming.empty:
        result = shown.copy()
        result.insert(0, "변경내용", pd.Series(dtype="string"))
        result.insert(0, "변경컬럼", pd.Series(dtype="string"))
        result.insert(0, "Import구분", pd.Series(dtype="string"))
        return result
    current_by_key = {_row_key(row, keys): row for _, row in current.iterrows()}
    actions: list[str] = []
    changed_columns: list[str] = []
    change_details: list[str] = []
    for _, incoming_row in shown.iterrows():
        previous = current_by_key.get(_row_key(incoming_row, keys))
        if previous is None:
            actions.append("신규")
            changed_columns.append("-")
            change_details.append("-")
            continue
        actions.append("대체")
        changes = [
            column
            for column in shown.columns
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
    result = shown.reset_index(drop=True)
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
