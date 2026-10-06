# Purpose: 공용 선행 입고 실적 프로필의 값 정규화·편집 병합과 LOB 칸 글자를 만든다.

"""선행 입고 실적 — 계획보다 앞서 라인 기준으로 입고한 물량(2026-10-06 사용자 설명).

선행 **입고**는 이미 생산계획에 들어 있는 물량이다. 그래서 계산을 **아무것도 바꾸지 않는다** —
선행 B/O(`advance_load`, 계획 밖 재공이라 부하를 더한다)와 다르다. 사용자가 알고 싶은 것은 그 달
Density 가운데 얼마가 선행 입고였는가 하나라, HOME `Capa LOB 현황` 의 Density 칸 오른쪽 위에
값만 적는다(`home_lob_figures`).

저장 모양과 입력 규칙은 선행 B/O 와 같다(`monthly_amount`) — 월별 억Gb 한 칸, 부호는 입력한
그대로(음수도 받는다), 0·빈칸은 「없음」, 조회기간 밖 저장분은 보존한다. 시나리오와 무관한
공용 프로필이다(`app_meta.global_advance_shipment*`, 마이그레이션 0031).
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from capa_simulation.services.month_columns import month_label
from capa_simulation.services.monthly_amount import (
    amounts_by_month,
    empty_monthly_amounts,
    merge_monthly_amount_edits,
    prepare_monthly_amounts,
)

# 저장 컬럼(`app_meta.global_advance_shipment_month`) 이름.
ADVANCE_SHIPMENT_VALUE_COLUMN = "선행 입고"
ADVANCE_SHIPMENT_COLUMNS = ("생산계획년월", ADVANCE_SHIPMENT_VALUE_COLUMN)
# 편집 표의 구분 칸·hover 앞머리. 편집기 제목과 같은 낱말이다.
ADVANCE_SHIPMENT_ROW_LABEL = "선행 입고 실적"
# 칸 글자의 자릿수. 부호를 늘 붙인다(`+1.2`·`-0.5`).
ADVANCE_SHIPMENT_FORMAT = "{:+.1f}"


def empty_advance_shipment() -> pd.DataFrame:
    """아직 아무것도 넣지 않은 정상 상태의 빈 프레임."""
    return empty_monthly_amounts(ADVANCE_SHIPMENT_VALUE_COLUMN)


def prepare_advance_shipment(frame: pd.DataFrame) -> pd.DataFrame:
    """저장·표시 공용 정규화. 0 과 결측은 「넣지 않은 달」이라 지우고 부호는 그대로 둔다."""
    return prepare_monthly_amounts(
        frame,
        value_column=ADVANCE_SHIPMENT_VALUE_COLUMN,
        subject=ADVANCE_SHIPMENT_VALUE_COLUMN,
    )


def merge_advance_shipment_edits(
    stored: pd.DataFrame,
    months: Sequence[int],
    values: Sequence[object],
) -> pd.DataFrame:
    """화면에 보인 달만 갈아 끼우고 조회기간 밖 저장분은 그대로 둔다(선행 B/O 와 같은 규칙)."""
    return merge_monthly_amount_edits(
        stored,
        months,
        values,
        value_column=ADVANCE_SHIPMENT_VALUE_COLUMN,
        subject=ADVANCE_SHIPMENT_VALUE_COLUMN,
    )


def advance_shipment_by_month(rows: pd.DataFrame) -> dict[int, float]:
    """저장본을 `{YYYYMM: 억Gb}` 로. 편집기 칸이 읽는다."""
    return amounts_by_month(rows, ADVANCE_SHIPMENT_VALUE_COLUMN)


def advance_shipment_notes(
    rows: pd.DataFrame,
    month_labels: Sequence[str],
) -> list[tuple[str, str]]:
    """월 축 칸마다 `(칸 글자, hover 글자)`. 적을 것이 없는 칸은 `("", "")` 이다.

    축의 라벨(`YY.MM`)로 달을 찾으므로 연간 Total 칸은 늘 비고(합계를 적지 않는다), 과거 구간 달도
    축에 있으면 그대로 적는다. 자릿수에서 0 으로 보이는 값(`+0.0`)은 적지 않는다 — 0 이 아닌 값이
    0 으로 읽히면 「선행 입고가 없었다」가 되어 오히려 거짓이다.
    """
    by_label = {
        month_label(month): value for month, value in advance_shipment_by_month(rows).items()
    }
    notes: list[tuple[str, str]] = []
    for label in month_labels:
        value = by_label.get(str(label))
        text = "" if value is None else ADVANCE_SHIPMENT_FORMAT.format(value)
        if not any(character in "123456789" for character in text):
            notes.append(("", ""))
            continue
        notes.append((text, f"{ADVANCE_SHIPMENT_ROW_LABEL} {text}억Gb"))
    return notes
