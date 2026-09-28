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
    "환산비",
    "모체호기",
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
    # 모듈 행 넷이 같은 날 같은 단계로 넘어가면 설비 한 대의 전환 한 건이다. 건수·대상 대수는
    # 이 키로 센다.
    "설비키",
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

# ------------------------------------------------------------------------ 환산비
# 같은 공정에 생산성이 다른 설비 모델이 섞일 때 **한 대가 몇 대 몫을 하는지**다. 기준
# 모델이 1.0 이고 더 빠른 모델은 1 보다 크다.
#
#     환산비 1.5 모델 2대 + 환산비 1.0 모델 2대
#       → 설비대수 4대, 가용대수 5대
#
# **능력 축의 값이다.** 「몇 대 몫을 하나」에 답하는 `환산대수` 와 확보율 교차검증이 이
# 값을 곱한다(`services/monthly_equipment_availability.py`). 「몇 대인가」에 답하는 대수 축은
# 곱하지 않는다 — 환산비를 곱하면 열 대가 열다섯 대가 된다. 대수 축은 대신 `설비지분` 을
# 곱한다(`services/equipment_units.py`).
#
# 모듈 행(아래 `모체호기`)에는 「그 행이 기준 설비 몇 대 몫인가」를 적는다. 4모듈 설비의
# 모듈 행은 1 ÷ 4 = 0.25 이고, 모듈 생산성이 기준과 다르면 곱한다(0.25 × 1.2 = 0.30).
#
# 빈 칸은 1.0 이다. 대부분의 공정은 모델이 하나뿐이라 적을 것이 없고, 그때 빈 칸을 0 으로
# 읽으면 그 설비가 통째로 사라진다.
CONVERSION_RATIO_COLUMN = "환산비"

DEFAULT_CONVERSION_RATIO = 1.0

NUMERIC_COLUMNS = (*COORDINATE_COLUMNS, CONVERSION_RATIO_COLUMN)

# ---------------------------------------------------------------------- 모체호기
# 모듈로 관리하는 공정(CoW Bonder 등)은 설비 한 대를 모듈마다 한 행으로 적고, 같은
# 설비의 행에 설비 ID 를 똑같이 적어 묶는다(APW01A~D → 모체호기 APW01). 비모듈 공정은
# 비워 둔다 — 행 하나가 설비 한 대다. 대수 축은 이 묶음을 한 대로 센다
# (`services/equipment_units.py`).
#
# **선택 컬럼이다.** 이 컬럼이 없던 파일·리비전·편집본은 모두 빈 칸으로 읽는다
# (`with_optional_equipment_columns`). 계약 맨 끝에 둔다 — 중간에 끼우면 붙여넣기 열이 밀린다.
PARENT_EQUIPMENT_COLUMN = "모체호기"

OPTIONAL_EQUIPMENT_COLUMNS = (PARENT_EQUIPMENT_COLUMN,)

# 한 설비의 모듈 행끼리 같아야 하는 컬럼. 화면 필터가 이 값들로 행을 거르므로, 다르면
# 필터가 설비 하나를 쪼개 지분 합이 1 이 아니게 된다.
UNIT_CONSISTENT_COLUMNS = ("공정소분류", "공정대분류", "라인구분", "활용구분", "동", "층")


def with_optional_equipment_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """선택 컬럼이 없는 호기 마스터에 빈 칸으로 채워 넣는다. 원본은 건드리지 않는다."""
    missing = [column for column in OPTIONAL_EQUIPMENT_COLUMNS if column not in frame.columns]
    if not missing:
        return frame
    filled = frame.copy()
    for column in missing:
        filled[column] = pd.Series(pd.NA, index=frame.index, dtype="string")
    return filled


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
                    if column in NUMERIC_COLUMNS
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
