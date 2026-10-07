# Purpose: 설비 운영 입력 세 종류의 컬럼 계약과 허용값 목록을 정의한다.

"""설비 운영 입력 세 종류의 컬럼 계약과 허용값 목록을 정의한다."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

import pandas as pd

BASELINE_COLUMNS = ("공정", "분류", "기존보유대수", "비고")

# 기존 보유대수의 자연키. 집계는 `공정` 하나로 합산하지만 한 공정에 분류가 여럿일 수 있어
# 중복 판정과 Import 병합은 두 컬럼 조합으로 한다.
BASELINE_KEY_COLUMNS = ("공정", "분류")

EQUIPMENT_COLUMNS = (
    "구분",
    "공정대분류",
    "공정소분류",
    "Maker",
    "Model",
    "설비명",
    "공정구분",
    "투자Capa",
    "투자구분",
    "사용기준",
    "동",
    "층",
    "담당자",
    "설비가동현황",
    "X좌표",
    "Y좌표",
    "Xsize",
    "Ysize",
    "제진대일정",
    "물류일정",
    "반입일정",
    "Qual일정",
    "확정상태",
    "반출일정",
    "이설일정",
    "반입/Qual 이력",
    "호기이력",
    "설비이력",
    "보관유무",
    "기존설비여부",
    "레이아웃표시",
    "환산비",
    "Main 설비",
    "메모1",
    "메모2",
    "메모3",
)

# 설비 한 대(모듈 행이면 모듈 하나)를 가리키는 식별 컬럼. 설비 마스터의 자연키이고 비가동
# 일정이 같은 이름으로 설비를 가리킨다.
EQUIPMENT_ID_COLUMN = "설비명"

EQUIPMENT_KEY_COLUMNS = (EQUIPMENT_ID_COLUMN,)

DOWNTIME_COLUMNS = (EQUIPMENT_ID_COLUMN, "비가동유형", "시작일", "종료일", "상세사유", "비고")

DOWNTIME_KEY_COLUMNS = (EQUIPMENT_ID_COLUMN, "비가동유형", "시작일")

# 반입일정이 설비가 들어오는 날이다. 단계 이름(「입고 예정」·SCHEDULE_STAGES 의 「입고」)은
# 컬럼 이름과 따로 움직이며 바꾸지 않는다.
ARRIVAL_DATE_COLUMN = "반입일정"

# 다른 자리로 옮기는 날이다. 단계 이름(「이설」)과 상태(「이설 예정」·「이설 완료」)는
# 컬럼 이름과 따로 움직이며 바꾸지 않는다.
RELOCATION_DATE_COLUMN = "이설일정"

DATE_COLUMNS = (
    "제진대일정",
    "물류일정",
    ARRIVAL_DATE_COLUMN,
    "Qual일정",
    "반출일정",
    RELOCATION_DATE_COLUMN,
)

SCHEDULE_STAGES = (
    ("제진대일정", "제진대"),
    ("물류일정", "물류"),
    (ARRIVAL_DATE_COLUMN, "입고"),
    ("Qual일정", "Qual"),
    ("반출일정", "반출"),
    (RELOCATION_DATE_COLUMN, "이설"),
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

# 상태 판정(`equipment_availability`)이 상태 이름 옆에 붙이는 집계 컬럼 둘.
#
# - `집계분류` — 대수를 셀 때 쓰는 분류. **가용 판정이 먼저다**: 가용이면 「가용」, 아니면 상태 이름
#   그대로다. 상태 이름은 사다리 아래쪽이 위쪽을 덮어, 반출·이설일정이 적힌 호기는 가용인 날에도
#   「반출 예정」·「이설 예정」이다. 그 이름으로 세면 실행일 전까지 멀쩡히 쓰는 호기가 가용대수에서
#   통째로 빠진다. 그래서 세는 자리(주차·월별 대수)는 이 컬럼을 보고, 이름을 보여 주는 자리
#   (상태 분포·호기 목록·생애주기 Gantt·Space)는 `상태` 를 본다. 이 컬럼의 「반출 예정」·
#   「이설 예정」은 가용이 아닌(셋업 중·보관·입고 전) 예정 호기만 남는다.
# - `가용대수반영` — 그 행을 대수에 세는가(`counts_for_capacity`, 사용기준 HBM).
COUNT_CATEGORY_COLUMN = "집계분류"
COUNTED_COLUMN = "가용대수반영"

# 주차별 집계의 분류 대수 컬럼. **키는 `집계분류` 값이다** — 「가용호기대수」는 가용 판정을 받은
# 호기 전체(반출·이설 예정이어도 실행일 전이면 든다)라 `가용대수 = 기존보유대수 + 가용호기대수`
# 이고, 「반출예정대수」·「이설예정대수」는 가용이 아닌 예정 호기다.
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
    EQUIPMENT_ID_COLUMN,
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

# 빈 칸을 허용하는 글자 컬럼. 앞뒤 공백을 떼고 빈 글자는 빈 칸으로 맞춘다.
REFERENCE_TEXT_COLUMNS = (
    "구분",
    "공정대분류",
    "Maker",
    "Model",
    "공정구분",
    "투자Capa",
    "투자구분",
    "사용기준",
    "담당자",
    "설비가동현황",
    "반입/Qual 이력",
    "호기이력",
    "설비이력",
    "메모1",
    "메모2",
    "메모3",
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
# 모듈 행(아래 `Main 설비`)에는 「그 행이 기준 설비 몇 대 몫인가」를 적는다. 4모듈 설비의
# 모듈 행은 1 ÷ 4 = 0.25 이고, 모듈 생산성이 기준과 다르면 곱한다(0.25 × 1.2 = 0.30).
#
# 빈 칸은 1.0 이다. 대부분의 공정은 모델이 하나뿐이라 적을 것이 없고, 그때 빈 칸을 0 으로
# 읽으면 그 설비가 통째로 사라진다.
CONVERSION_RATIO_COLUMN = "환산비"

DEFAULT_CONVERSION_RATIO = 1.0

NUMERIC_COLUMNS = (*COORDINATE_COLUMNS, CONVERSION_RATIO_COLUMN)

# --------------------------------------------------------------------- Main 설비
# 모듈로 관리하는 공정(CoW Bonder 등)은 설비 한 대를 모듈마다 한 행으로 적고, 같은
# 설비의 행에 설비 ID 를 똑같이 적어 묶는다(APW01A~D → Main 설비 APW01). 비모듈 공정은
# 비워 둔다 — 행 하나가 설비 한 대다. 대수 축은 이 묶음을 한 대로 센다
# (`services/equipment_units.py`).
PARENT_EQUIPMENT_COLUMN = "Main 설비"

# 투자 당시의 설비 능력 표기(예 "322K"). 계산에 쓰지 않는 글자 값이다. 옛 계약의 `투자기준` 과는
# 다른 컬럼이다 — 그 값은 이어받지 않는다(아래 `OBSOLETE_EQUIPMENT_COLUMNS`).
INVESTMENT_CAPA_COLUMN = "투자Capa"

MEMO_COLUMNS = ("메모1", "메모2", "메모3")

# **선택 컬럼이다.** 이 컬럼들이 없던 파일·리비전·편집본은 모두 빈 칸으로 읽는다
# (`with_optional_equipment_columns`). 파일 입구는 컬럼 이름으로 고르므로 계약 중간에 있어도
# 열이 밀리지 않는다.
OPTIONAL_EQUIPMENT_COLUMNS = (
    INVESTMENT_CAPA_COLUMN,
    "반입/Qual 이력",
    PARENT_EQUIPMENT_COLUMN,
    *MEMO_COLUMNS,
)

# 한 설비의 모듈 행끼리 같아야 하는 컬럼. 화면 필터가 이 값들로 행을 거르므로, 다르면
# 필터가 설비 하나를 쪼개 지분 합이 1 이 아니게 된다.
UNIT_CONSISTENT_COLUMNS = ("공정소분류", "공정대분류", "공정구분", "투자구분", "동", "층")


def with_optional_equipment_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """선택 컬럼이 없는 호기 마스터에 빈 칸으로 채워 넣는다. 원본은 건드리지 않는다."""
    missing = [column for column in OPTIONAL_EQUIPMENT_COLUMNS if column not in frame.columns]
    if not missing:
        return frame
    filled = frame.copy()
    for column in missing:
        filled[column] = pd.Series(pd.NA, index=frame.index, dtype="string")
    return filled


# ------------------------------------------------------------------ 옛 머리 이름
# 사내에는 옛 이름으로 적은 엑셀·CSV 가 이미 있다. 설비 표를 받는 모든 입구(CSV 올리기·붙여넣기)가
# 이 표 하나로 옛 이름을 새 이름으로 바꿔 읽는다. **표마다 따로다** — `비고` 는 설비 마스터에서만
# `설비이력` 이 되고, 비가동 일정·기존 보유대수의 `비고` 는 그대로다.
LEGACY_EQUIPMENT_HEADER_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "호기": EQUIPMENT_ID_COLUMN,
        "라인구분": "공정구분",
        "활용구분": "투자구분",
        "분류1": "구분",
        "분류2": "사용기준",
        "분류3": "설비가동현황",
        "모델": "Model",
        "입고일정": ARRIVAL_DATE_COLUMN,
        "이설일": RELOCATION_DATE_COLUMN,
        "비고": "설비이력",
        "장기보관여부": "보관유무",
        "모체호기": PARENT_EQUIPMENT_COLUMN,
    }
)

LEGACY_DOWNTIME_HEADER_ALIASES: Mapping[str, str] = MappingProxyType({"호기": EQUIPMENT_ID_COLUMN})

# 계약에서 빠진 옛 컬럼. 이 열이 오면 읽지 않고 알림 한 줄을 남긴다. 저장소의 옛 값
# (`investment_basis`)은 지우지 않고 읽지만 않는다 — 되살릴 수 있게.
OBSOLETE_EQUIPMENT_COLUMNS = ("투자기준",)


def compact_header(header: object) -> str:
    """머리 이름 비교용. 공백을 모두 빼고 대소문자를 가리지 않는다.

    「Main설비」·「모체 호기」·「MAIN 설비」·「투자CAPA」도 같은 이름으로 본다. 영문이 든 선택
    컬럼이 대소문자만 달라 모르는 열로 버려지면 빈 칸으로 조용히 읽히기 때문이다.
    """
    return "".join(str(header).split()).casefold()


def rename_legacy_headers(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    aliases: Mapping[str, str],
    label: str,
    *,
    obsolete: tuple[str, ...] = (),
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """옛 머리 이름을 새 이름으로 바꾸고, 빠진 옛 컬럼은 떼어 낸 뒤 알림 문구와 함께 돌려준다.

    공백·대소문자만 다른 이름(「Main설비」·「MAIN 설비」)도 계약 이름으로 맞춘다. 옛 이름과
    새 이름이 함께 오면 어느 쪽이 맞는지 알 수 없으므로 막는다. 원본은 건드리지 않는다.
    """
    targets = {compact_header(column): column for column in columns}
    for old, new in aliases.items():
        targets.setdefault(compact_header(old), new)
    dropped = {compact_header(column): column for column in obsolete}
    renames: dict[object, str] = {}
    removed: list[object] = []
    for header in frame.columns:
        key = compact_header(header)
        if key in dropped:
            removed.append(header)
        elif key in targets and targets[key] != header:
            renames[header] = targets[key]
    if not renames and not removed:
        return frame, ()
    result = frame.drop(columns=removed).rename(columns=renames)
    names = [str(column) for column in result.columns]
    duplicated = sorted({name for name in names if names.count(name) > 1})
    if duplicated:
        sources = {
            name: [
                str(header)
                for header in frame.columns
                if targets.get(compact_header(header)) == name
            ]
            for name in duplicated
        }
        detail = ", ".join(f"{name} ← {' · '.join(found)}" for name, found in sources.items())
        raise ValueError(
            f"{label}에 같은 컬럼을 가리키는 옛 이름과 새 이름이 함께 있습니다({detail}). "
            "하나만 남기세요."
        )
    notices = tuple(
        f"{label}의 「{dropped[compact_header(header)]}」 열은 빠진 컬럼이라 읽지 않았습니다"
        f"(새 컬럼 「{INVESTMENT_CAPA_COLUMN}」 는 별개의 컬럼입니다)."
        if dropped[compact_header(header)] == "투자기준"
        else f"{label}의 「{dropped[compact_header(header)]}」 열은 빠진 컬럼이라 읽지 않았습니다."
        for header in removed
    )
    return result, notices


STORAGE_FLAG_COLUMN = "보관유무"

FLAG_COLUMNS = (STORAGE_FLAG_COLUMN, "기존설비여부", "레이아웃표시")

# ------------------------------------------------------------------- 사용기준
# **Dynamic 가용대수에 세는 호기는 사용기준이 이 값인 행뿐이다**(2026-10-07 사용자 결정). 다른 제품
# Capa 를 함께 반영하게 되면 사용기준별로 나눠 집계할 것이고, 그때까지는 HBM 만 유효 대수다.
# 배치(Space)·호기 목록·상태 분포·RawData 편집과 검증은 이 규칙을 보지 않는다 — 세지 않을 뿐
# 호기는 그대로 있다.
#
# 대조는 **앞뒤 공백을 떼고 대소문자를 가리지 않는 완전 일치**다. 「 hbm 」은 세고 「HBM3E」·
# 「HBM 양산」처럼 다른 글자가 붙은 값과 빈 칸은 세지 않는다. 기존 보유대수 표에는 사용기준이
# 없으므로 그 대수는 지금처럼 `기존보유` 로 센다.
#
# 행(모듈 행이면 모듈 하나)마다 본다. 대수 축은 행의 설비지분에 이 판정을 곱하므로 모듈 넷 중 둘만
# HBM 인 설비는 0.5대다. 분류별 집계로 넓힐 때는 이 판정 대신 `usage_basis_key` 로 묶으면 된다.
USAGE_BASIS_COLUMN = "사용기준"

COUNTED_USAGE_BASIS: tuple[str, ...] = ("HBM",)


def usage_basis_key(values: pd.Series) -> pd.Series:
    """사용기준 대조용 글자. 앞뒤 공백을 떼고 대소문자를 접는다. 빈 칸은 결측이다."""
    text = values.astype("string").str.strip().str.casefold()
    return text.mask(text.eq(""))


def counts_for_capacity(frame: pd.DataFrame) -> pd.Series:
    """행마다 Dynamic 가용대수(Capa)에 세는가. 사용기준이 `COUNTED_USAGE_BASIS` 와 같으면 참이다.

    검증 전 편집본도 받는다(대조가 공백·대소문자를 스스로 정리한다). 사용기준 컬럼이 없는 표는
    모든 행이 빈 칸과 같다 — 세지 않는다.
    """
    if USAGE_BASIS_COLUMN not in frame.columns:
        return pd.Series(False, index=frame.index, dtype="bool")
    wanted = {value.strip().casefold() for value in COUNTED_USAGE_BASIS}
    keys = usage_basis_key(frame[USAGE_BASIS_COLUMN])
    return keys.isin(wanted).fillna(False).astype("bool")


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
