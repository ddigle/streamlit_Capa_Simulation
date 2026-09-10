# Purpose: 설비 운영 입력 세 종류의 컬럼 계약과 허용값 목록을 정의한다.

"""설비 운영 입력 세 종류의 컬럼 계약과 허용값 목록을 정의한다."""

from __future__ import annotations

import pandas as pd

BASELINE_COLUMNS = ("공정", "분류", "기존보유대수", "비고")

# 기존 보유대수의 자연키. 집계는 `공정` 하나로 합산하지만 한 공정에 분류가 여럿일 수 있어
# 중복 판정과 Import 병합은 두 컬럼 조합으로 한다.
BASELINE_KEY_COLUMNS = ("공정", "분류")

EQUIPMENT_COLUMNS = (
    "호기",
    "공정대분류",
    "공정소분류",
    "라인구분",
    "활용구분",
    "투자기준",
    "담당자",
    "Maker",
    "모델",
    "분류1",
    "분류2",
    "분류3",
    "동",
    "층",
    "X좌표",
    "Y좌표",
    "Xsize",
    "Ysize",
    "제진대일정",
    "물류일정",
    "입고일정",
    "Qual일정",
    "확정상태",
    "반출일정",
    "이설일",
    "장기보관여부",
    "기존설비여부",
    "호기이력",
    "비고",
    "레이아웃표시",
)

DOWNTIME_COLUMNS = ("호기", "비가동유형", "시작일", "종료일", "상세사유", "비고")

DOWNTIME_KEY_COLUMNS = ("호기", "비가동유형", "시작일")

DATE_COLUMNS = (
    "제진대일정",
    "물류일정",
    "입고일정",
    "Qual일정",
    "반출일정",
    "이설일",
)

SCHEDULE_STAGES = (
    ("제진대일정", "제진대"),
    ("물류일정", "물류"),
    ("입고일정", "입고"),
    ("Qual일정", "Qual"),
    ("반출일정", "반출"),
    ("이설일", "이설"),
)

QUAL_CONFIRMATION_STATUSES = ("계획", "확정", "완료", "지연")

MILESTONES = SCHEDULE_STAGES

EQUIPMENT_STATUSES = (
    "입고 예정",
    "셋업 진행중",
    "가용",
    "반출 예정",
    "이설 예정",
    "보관 설비",
    "운영 비가동",
    "반출 완료",
    "이설 완료",
)

STATUS_COUNT_COLUMNS = {
    "입고 예정": "입고예정대수",
    "셋업 진행중": "셋업중대수",
    "가용": "가용호기대수",
    "반출 예정": "반출예정대수",
    "이설 예정": "이설예정대수",
    "보관 설비": "보관설비대수",
    "운영 비가동": "운영비가동대수",
    "반출 완료": "반출완료대수",
    "이설 완료": "이설완료대수",
}

TRANSITION_EVENT_COLUMNS = (
    "호기",
    "공정대분류",
    "공정소분류",
    "동",
    "층",
    "이전단계",
    "전환단계",
    "전환일",
    "확정상태",
    "일정상태",
    "기준일대비",
)

DOWNTIME_TYPES = ("개발대여", "공사", "고장", "이설", "기타")

WEEKLY_COLUMNS = (
    "Weeknum",
    "주차시작일",
    "주차종료일",
    "공정소분류",
    "기존보유대수",
    "추가설비대수",
    "총대수",
    "가용대수",
    "비가동대수",
    *STATUS_COUNT_COLUMNS.values(),
)

REFERENCE_TEXT_COLUMNS = (
    "공정대분류",
    "라인구분",
    "활용구분",
    "투자기준",
    "담당자",
    "Maker",
    "모델",
    "분류1",
    "분류2",
    "분류3",
    "호기이력",
    "비고",
)

COORDINATE_COLUMNS = ("X좌표", "Y좌표", "Xsize", "Ysize")

FLAG_COLUMNS = ("장기보관여부", "기존설비여부", "레이아웃표시")

VALID_BUILDINGS = tuple(f"C{index}" for index in range(1, 6))

VALID_FLOORS = tuple(f"{index}F" for index in range(1, 7))


def empty_equipment_baseline() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": pd.Series(dtype="string"),
            "분류": pd.Series(dtype="string"),
            "기존보유대수": pd.Series(dtype="float64"),
            "비고": pd.Series(dtype="string"),
        }
    )


def empty_equipment_master() -> pd.DataFrame:
    return pd.DataFrame(
        {
            column: pd.Series(
                dtype=(
                    "datetime64[ns]"
                    if column in DATE_COLUMNS
                    else "float64"
                    if column in COORDINATE_COLUMNS
                    else "string"
                )
            )
            for column in EQUIPMENT_COLUMNS
        }
    )


def empty_downtime_schedule() -> pd.DataFrame:
    return pd.DataFrame(
        {
            column: pd.Series(
                dtype="datetime64[ns]" if column in {"시작일", "종료일"} else "string"
            )
            for column in DOWNTIME_COLUMNS
        }
    )
