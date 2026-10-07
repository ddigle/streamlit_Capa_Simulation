# Purpose: 호기 생애주기 구간을 공정별 W/D 구간에 일수로 안분해 월별 가용대수를 만든다.

"""월별 Dynamic 가용대수.

호기 하나가 한 달에 기여하는 대수는 **그 달의 W/D 구간과 겹친 일수의 비율**이다
(`services/wd_window.py`). 9월 30일에 Qual 이 끝난 설비는 Cut-off 15일 공정의 2026-10
구간 `(9/15, 10/16]` 에 16일만 걸치므로 `1대 x 16/31 = 0.52대` 를 기여한다.

기존 주차별 집계(`build_weekly_equipment_availability`)와 **다른 질문에 답한다.** 그쪽은
「그 주 일요일에 몇 대가 가용인가」라는 시점 표본이라 모듈 설비가 없으면 정수이고
(모듈 하나가 멈추면 0.25 같은 소수), 여기는 「이 달 생산에 며칠씩 보탰나」라서 소수가
나온다. 그래서 같은 달을 두 화면이 다르게 말할 수 있고, 그것이 정상이다.

**상태가 바뀌는 날은 그 상태의 첫날이 아니다.** 일정이 `D` 에 완료되면 설비는 `D` 의
경계 시각 이후, 곧 다음 날부터 기여한다. `build_equipment_lifecycle_spans` 는 상태가
바뀐 날을 구간 시작으로 주므로 여기서 하루씩 민다. 모든 구간을 똑같이 밀어야 구간이
서로 맞물린 채로 남는다 — 하나만 밀면 하루가 어느 상태에도 안 잡힌다.

## 무엇이 가용 합계에 들어가나

호기 상태 아홉은 **서로 배타적**이다. 한 호기는 어느 날 하나의 상태만 갖는다. 그래서
아홉을 다 더하면 「그 공정이 그 달에 가진 호기-일수 전부」가 되지, 가용대수가 되지
않는다. 가용 합계에 들어가는 것은 둘뿐이다.

- `기존보유` — 호기 마스터에 아직 못 올린 설비의 단순 대수 합. **안분하지 않는다**
  (`baseline_snapshot` 에 날짜 컬럼이 없어 언제부터 있었는지 알 수 없다). 호기 마스터가
  채워질수록 이 항목이 줄고 안분되는 항목이 는다.
- `가용` — 입고·Qual 을 지나고 반출·이설 전이며 비가동·보관이 아닌 호기. **가용 판정으로
  고른다**(구간의 `집계분류`). 반출·이설일정이 적힌 호기는 실행일 전까지 상태 이름이 「반출
  예정」·「이설 예정」이지만, 그날 가용이면 여기에 든다 — 이름으로 고르면 날짜를 적는 순간
  멀쩡히 쓰는 호기가 첫날부터 빠졌다(2026-10-07 사용자 결정으로 고침).

나머지 여덟은 **왜 못 쓰는지**를 보여 주는 참고 행이다. 화면은 `부호` 로 늘고 주는 것을
표시하되 `가용반영` 이 참인 행만 소계에 넣는다. 여덟을 합계에 넣으면 아직 들어오지도
않은 설비가 가용대수로 세어진다. 그래서 `반출 예정`·`이설 예정` 행에는 **가용이 아닌**
예정 호기(셋업 중·보관·입고 전)만 남는다.

## 사용기준 HBM 만 센다

호기 마스터의 기여 줄은 **사용기준이 HBM 인 행만** 만든다(구간의 `가용대수반영`,
`equipment_contract.counts_for_capacity`, 2026-10-07 사용자 결정). 다른 행은 참고 행에도 들지
않는다 — 이 표는 HBM Capa 의 가용대수를 분해한 것이다. 행마다 보므로 모듈 넷 중 둘만 HBM 인
설비는 지분대로 0.5대다. `기존보유` 는 사용기준이 없어 지금처럼 센다.

## 대수와 환산대수는 다른 질문이다

같은 공정 안에서도 모델마다 생산성이 달라, 호기 마스터는 `환산비`(기준 1.0)를 갖는다.
그래서 이 모듈은 **두 값을 함께** 낸다.

- `대수` — 설비를 센 것. 「몇 대인가」에 답한다. 환산비를 보지 않는다. 모듈 행은
  `설비지분`(그 시점 보유 중인 모듈 수로 나눈 몫)을 곱해 설비 한 대로 모인다
  (`services/equipment_units.py`). 구간에 지분 컬럼이 없으면 행 하나를 한 대로 본다.
- `환산대수` — 기여도에 그 호기의 환산비를 곱한 것. **월 Total Capa 를 낼 때 이쪽을 쓴다.**

환산비 1.5 인 호기가 3월에 15일 기여하면 `1.5 x 15/31 = 0.726` 이 `환산대수` 이고,
`대수` 는 `15/31 = 0.484` 다. 설비 대수를 세는 화면에서 환산비를 곱하면 「열 대가 있다」가
「열다섯 대가 있다」가 되어 버린다 — 그래서 한 숫자로 합치지 않는다.

`기존보유` 는 호기 단위가 아니라 `(공정, 분류)` 집계 대수라 환산비를 걸 데가 없다. 두 값이
같다 — 1.0 을 곱한 것과 같고, 호기 마스터가 채워질수록 이 비대칭이 줄어든다.

## 대수 표와 호기 목록은 같은 줄에서 나온다

`build_monthly_equipment_availability` 는 호기(와 기존보유)마다 만든 기여 줄을
`(월, 공정, 분류)` 로 더한 것이고, `build_monthly_equipment_contributions` 는 같은 줄을
호기 단위로만 모은 것이다. 두 함수가 줄을 **따로 만들지 않는다**(`_raw_rows`) — 따로 만들면
「표에는 3.5대인데 목록은 5행」이 조용히 생긴다. 목록의 `대수` 를 같은 칸끼리 더하면 표의
값이다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from capa_simulation.services.equipment_contract import (
    COUNT_CATEGORY_COLUMN,
    COUNTED_COLUMN,
    EQUIPMENT_ID_COLUMN,
)
from capa_simulation.services.equipment_units import UNIT_KEY_COLUMN, UNIT_SHARE_COLUMN
from capa_simulation.services.process_cutoff import cutoff_lookup
from capa_simulation.services.wd_window import WdWindow, wd_window

__all__ = [
    "MONTHLY_AVAILABILITY_COLUMNS",
    "MONTHLY_CONTRIBUTION_COLUMNS",
    "AvailabilityCategory",
    "BASELINE_CATEGORY",
    "CATEGORIES",
    "available_subtotal",
    "build_monthly_equipment_availability",
    "build_monthly_equipment_contributions",
    "empty_monthly_availability",
    "processes_in",
    "span_date_range",
]

_ONE_DAY = timedelta(days=1)

MONTHLY_AVAILABILITY_COLUMNS = (
    "생산계획년월",
    "공정",
    "분류",
    "대수",
    "환산대수",
    "부호",
    "가용반영",
)

# 호기 목록 한 줄. `설비명` 이 비면 기존보유 줄이고 `기존보유분류` 가 그 분류들이다.
# `기여일수` 는 그 달 W/D 구간(`구간일수`)과 겹친 날 수다 — 기존보유는 안분하지 않아 비운다.
MONTHLY_CONTRIBUTION_COLUMNS = (
    "생산계획년월",
    "공정",
    "분류",
    EQUIPMENT_ID_COLUMN,
    "설비키",
    "기존보유분류",
    "기여일수",
    "구간일수",
    "대수",
    "환산대수",
)


@dataclass(frozen=True)
class AvailabilityCategory:
    """표에 한 행으로 펼쳐질 분류."""

    name: str
    sign: int
    """화면 표시용. `+1` 은 늘리는 쪽, `-1` 은 줄이는 쪽으로 보인다."""

    counts_as_available: bool
    """참이면 Dynamic 가용 소계에 들어간다."""

    prorated: bool
    """참이면 W/D 구간에 일수로 안분한다. 거짓이면 달마다 만액이다."""


BASELINE_CATEGORY = AvailabilityCategory(
    name="기존보유",
    sign=1,
    counts_as_available=True,
    prorated=False,
)

# 차례가 곧 표의 행 순서다. 가용에 들어가는 둘을 앞에 둔다.
CATEGORIES: tuple[AvailabilityCategory, ...] = (
    BASELINE_CATEGORY,
    AvailabilityCategory("가용", 1, True, True),
    AvailabilityCategory("운영 비가동", -1, False, True),
    AvailabilityCategory("입고 예정", 1, False, True),
    AvailabilityCategory("셋업 진행중", 1, False, True),
    AvailabilityCategory("보관 설비", -1, False, True),
    AvailabilityCategory("반출 예정", -1, False, True),
    AvailabilityCategory("반출 완료", -1, False, True),
    AvailabilityCategory("이설 예정", -1, False, True),
    AvailabilityCategory("이설 완료", -1, False, True),
)

_BY_NAME = {category.name: category for category in CATEGORIES}


def empty_monthly_availability() -> pd.DataFrame:
    """행이 없는 계약 프레임."""
    return pd.DataFrame(
        {
            "생산계획년월": pd.Series(dtype="int64"),
            "공정": pd.Series(dtype="string"),
            "분류": pd.Series(dtype="string"),
            "대수": pd.Series(dtype="float64"),
            "환산대수": pd.Series(dtype="float64"),
            "부호": pd.Series(dtype="int64"),
            "가용반영": pd.Series(dtype="bool"),
        }
    )


def span_date_range(months: Sequence[int], cutoff: pd.DataFrame) -> tuple[date, date] | None:
    """이 달들을 채우려면 호기 구간을 **언제부터 언제까지** 만들어야 하는지.

    Cut-off 가 크면 그 달의 W/D 구간이 앞으로 크게 밀린다 — 조회기간만큼만 구간을
    만들면 첫 달이 조용히 모자라게 세어진다. 부르는 쪽이 이 값으로
    `build_equipment_lifecycle_spans` 의 범위를 넓힌다.

    **시작은 첫 구간의 앞 경계(`boundary_start`)다 — 첫날(`first_day`)이 아니다.** 상태는 바뀐
    다음 날부터 기여하므로(`_prorated_rows` 가 구간 양 끝을 하루씩 민다) 구간의 첫 기여일을
    정하는 것은 **그 전날**의 상태다. 첫날부터 만들면 조회 시작 전부터 가용이던 호기도 첫날에
    기여하지 못해 첫 달이 호기마다 `1/구간일수` 씩 모자랐다(2026-10-07 리뷰 — 늘 가용인 30대가
    29.03대로 세어졌다).
    """
    windows = _windows_for(months, cutoff)
    if not windows:
        return None
    every = [window for group in windows.values() for window in group]
    return min(w.boundary_start for w in every), max(w.boundary_end for w in every)


def _windows_for(months: Sequence[int], cutoff: pd.DataFrame) -> dict[str, tuple[WdWindow, ...]]:
    """공정마다 요청한 달들의 W/D 구간. Cut-off 가 없는 공정은 아예 담기지 않는다."""
    lookup = cutoff_lookup(cutoff)
    ordered = list(dict.fromkeys(int(month) for month in months))
    return {
        process: tuple(wd_window(month, days) for month in ordered)
        for process, days in lookup.items()
    }


def build_monthly_equipment_availability(
    spans: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    months: Sequence[int],
    *,
    conversion_ratios: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """월별·공정별·분류별 기여 대수.

    `spans` 는 `build_equipment_lifecycle_spans(with_unit_share=True)` 의 결과(`호기·공정소분류·
    상태·시작일·종료일` 에 `설비지분`·`집계분류`·`가용대수반영`)이고, `baseline` 은 `공정·
    기존보유대수` 를 가진 기존보유 표다. 둘의 공정
    이름은 같은 이름 공간으로 본다 — 저장소에 그것을 강제하는 장치가 없으므로 부르는
    쪽이 `missing_cutoff_processes` 로 어긋남을 화면에 드러내야 한다.

    **어느 DB 도 열지 않는다.** 프레임 셋을 받아 프레임 하나를 돌려주는 순수 함수라,
    시뮬레이션 DB 와 설비 DB 를 각각 읽는 것은 페이지의 몫이다.
    """
    rows = _raw_rows(spans, baseline, cutoff, months, conversion_ratios)
    if not rows:
        return empty_monthly_availability()

    result = pd.DataFrame(rows)
    result = result.groupby(["생산계획년월", "공정", "분류"], as_index=False).agg(
        {"대수": "sum", "환산대수": "sum"}
    )
    result["부호"] = result["분류"].map(lambda name: _BY_NAME[str(name)].sign)
    result["가용반영"] = result["분류"].map(lambda name: _BY_NAME[str(name)].counts_as_available)
    result["생산계획년월"] = result["생산계획년월"].astype("int64")
    result["공정"] = result["공정"].astype("string")
    result["분류"] = result["분류"].astype("string")
    result["대수"] = result["대수"].astype("float64")
    result["환산대수"] = result["환산대수"].astype("float64")
    order = {category.name: index for index, category in enumerate(CATEGORIES)}
    result = result.sort_values(
        by=["생산계획년월", "공정", "분류"],
        key=lambda column: column.map(order) if column.name == "분류" else column,
    )
    return result.loc[:, list(MONTHLY_AVAILABILITY_COLUMNS)].reset_index(drop=True)


def build_monthly_equipment_contributions(
    spans: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    months: Sequence[int],
    *,
    conversion_ratios: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """월별 분류 대수를 이루는 **호기별 기여**. 분류별 내역의 호기 목록이 이것을 보인다.

    `build_monthly_equipment_availability` 와 같은 줄(`_raw_rows`)을 쓰고 호기 단위로만
    모은다 — 한 달 안에서 지분이 바뀌어 구간이 끊긴 호기도 한 줄이다. 그래서 같은
    `(월, 공정, 분류)` 의 `대수` 를 더하면 대수 표의 값이다.
    """
    rows = _raw_rows(spans, baseline, cutoff, months, conversion_ratios)
    if not rows:
        return _empty_contributions()
    raw = pd.DataFrame(rows)
    keys = [
        "생산계획년월",
        "공정",
        "분류",
        EQUIPMENT_ID_COLUMN,
        "설비키",
        "기존보유분류",
        "구간일수",
    ]
    for column in (EQUIPMENT_ID_COLUMN, "설비키", "기존보유분류"):
        raw[column] = raw[column].fillna("")
    result = raw.groupby(keys, as_index=False, sort=False).agg(
        {"기여일수": "sum", "대수": "sum", "환산대수": "sum"}
    )
    for column in (EQUIPMENT_ID_COLUMN, "설비키", "기존보유분류"):
        result[column] = result[column].replace("", pd.NA).astype("string")
    baseline_rows = result[EQUIPMENT_ID_COLUMN].isna()
    result["기여일수"] = result["기여일수"].astype("Int64").mask(baseline_rows)
    result["생산계획년월"] = result["생산계획년월"].astype("int64")
    result["구간일수"] = result["구간일수"].astype("int64")
    order = {category.name: index for index, category in enumerate(CATEGORIES)}
    result = result.sort_values(
        by=["생산계획년월", "공정", "분류", EQUIPMENT_ID_COLUMN],
        key=lambda column: column.map(order) if column.name == "분류" else column,
        na_position="first",
        kind="stable",
    )
    return result.loc[:, list(MONTHLY_CONTRIBUTION_COLUMNS)].reset_index(drop=True)


def _empty_contributions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": pd.Series(dtype="int64"),
            "공정": pd.Series(dtype="string"),
            "분류": pd.Series(dtype="string"),
            EQUIPMENT_ID_COLUMN: pd.Series(dtype="string"),
            "설비키": pd.Series(dtype="string"),
            "기존보유분류": pd.Series(dtype="string"),
            "기여일수": pd.Series(dtype="Int64"),
            "구간일수": pd.Series(dtype="int64"),
            "대수": pd.Series(dtype="float64"),
            "환산대수": pd.Series(dtype="float64"),
        }
    )


def _raw_rows(
    spans: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    months: Sequence[int],
    conversion_ratios: Mapping[str, float] | None,
) -> list[dict[str, object]]:
    """대수 표와 호기 목록이 함께 쓰는 기여 줄. 두 결과가 갈라지지 않게 여기서만 만든다."""
    windows = _windows_for(months, cutoff)
    if not windows:
        return []
    return [
        *_baseline_rows(baseline, windows),
        *_prorated_rows(spans, windows, conversion_ratios or {}),
    ]


def _baseline_rows(
    baseline: pd.DataFrame, windows: dict[str, tuple[WdWindow, ...]]
) -> list[dict[str, object]]:
    """기존보유는 안분하지 않는다 — 날짜가 없어 어느 달에 얼마나 있었는지 알 수 없다."""
    if baseline.empty or "공정" not in baseline.columns:
        return []
    process = baseline["공정"].astype("string").str.strip()
    counts = baseline.groupby(process)["기존보유대수"].sum().to_dict()
    # 목록이 「어느 기존보유인가」를 말하도록 분류 이름을 붙인다. 합계는 공정 단위 그대로다.
    labels: dict[str, str] = {}
    if "분류" in baseline.columns:
        for name, group in baseline.groupby(process)["분류"]:
            values = [str(value).strip() for value in group.dropna() if str(value).strip()]
            labels[str(name)] = " · ".join(dict.fromkeys(values))
    rows: list[dict[str, object]] = []
    for process_name, total in counts.items():
        for window in windows.get(str(process_name), ()):
            rows.append(
                {
                    "생산계획년월": window.year_month,
                    "공정": str(process_name),
                    "분류": BASELINE_CATEGORY.name,
                    EQUIPMENT_ID_COLUMN: None,
                    "설비키": None,
                    "기존보유분류": labels.get(str(process_name)) or "전체",
                    "기여일수": 0,
                    "구간일수": window.days,
                    "대수": float(total),
                    # 기존보유는 호기 단위가 아니라 집계 대수라 환산비를 걸 데가 없다.
                    # 그대로 둔다 — 1.0 을 곱한 것과 같다.
                    "환산대수": float(total),
                }
            )
    return rows


def _prorated_rows(
    spans: pd.DataFrame,
    windows: dict[str, tuple[WdWindow, ...]],
    conversion_ratios: Mapping[str, float],
) -> list[dict[str, object]]:
    if spans.empty:
        return []
    rows: list[dict[str, object]] = []
    shares = (
        spans[UNIT_SHARE_COLUMN]
        if UNIT_SHARE_COLUMN in spans.columns
        else pd.Series(1.0, index=spans.index)
    )
    unit_keys = (
        spans[UNIT_KEY_COLUMN] if UNIT_KEY_COLUMN in spans.columns else spans[EQUIPMENT_ID_COLUMN]
    )
    # 분류는 가용 판정으로 고른 `집계분류` 다(모듈 docstring). 그 컬럼이 없는 구간(손으로 만든
    # 표·Gantt 용 구간)은 상태 이름 그대로 — 가용 판정을 모르니 이름이 곧 분류다.
    categories = (
        spans[COUNT_CATEGORY_COLUMN] if COUNT_CATEGORY_COLUMN in spans.columns else spans["상태"]
    )
    # 사용기준이 HBM 이 아닌 호기는 기여 줄을 만들지 않는다. 지분만 0 으로 두면 환산대수(환산비를
    # 곱하는 축)에 남는다. 컬럼이 없는 구간은 걸러 오지 않은 것으로 보고 모두 센다.
    counted = (
        spans[COUNTED_COLUMN].fillna(False).astype("bool")
        if COUNTED_COLUMN in spans.columns
        else pd.Series(True, index=spans.index)
    )
    # `itertuples` 는 한글 컬럼명을 그대로 속성으로 주지만 이름이 겹치면 말없이 `_3` 으로
    # 바꾼다. 필요한 컬럼만 짝지어 도는 편이 빠르고 그 위험도 없다.
    columns = zip(
        spans[EQUIPMENT_ID_COLUMN],
        spans["공정소분류"],
        categories,
        spans["시작일"],
        spans["종료일"],
        shares,
        unit_keys,
        counted,
        strict=True,
    )
    for (
        raw_unit,
        raw_process,
        raw_category,
        raw_start,
        raw_end,
        raw_share,
        raw_key,
        is_counted,
    ) in columns:
        if not is_counted:
            continue
        process = str(raw_process or "").strip()
        month_windows = windows.get(process)
        if not month_windows:
            continue
        category = _BY_NAME.get(str(raw_category))
        if category is None or not category.prorated:
            continue
        ratio = float(conversion_ratios.get(str(raw_unit or "").strip(), 1.0))
        # 상태는 바뀐 날 **다음 날**부터다. 구간 양 끝을 같이 밀어야 서로 맞물린 채 남는다.
        began = _as_date(raw_start) + _ONE_DAY
        finished = _as_date(raw_end) + _ONE_DAY
        unit = str(raw_unit or "").strip()
        for window in month_windows:
            overlap = window.overlap_days(began, finished)
            if overlap:
                contribution = overlap / window.days
                rows.append(
                    {
                        "생산계획년월": window.year_month,
                        "공정": process,
                        "분류": category.name,
                        EQUIPMENT_ID_COLUMN: unit,
                        "설비키": str(raw_key or unit).strip(),
                        "기존보유분류": None,
                        "기여일수": overlap,
                        "구간일수": window.days,
                        "대수": contribution * float(raw_share),
                        "환산대수": contribution * ratio,
                    }
                )
    return rows


def _as_date(value: object) -> date:
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()  # type: ignore[arg-type]


def available_subtotal(monthly: pd.DataFrame) -> pd.DataFrame:
    """월·공정별 Dynamic 가용 소계. `가용반영` 이 참인 분류만 더한다.

    **두 축을 같이 낸다.** `Dynamic가용대수` 는 대수를 센 것이고
    `Dynamic가용환산대수` 는 호기별 환산비를 곱한 것이다. 「몇 대인가」와 「얼마나
    만드나」는 다른 질문이라 한 숫자로 합칠 수 없다.
    """
    if monthly.empty:
        return pd.DataFrame(
            {"생산계획년월": [], "공정": [], "Dynamic가용대수": [], "Dynamic가용환산대수": []}
        )
    included = monthly.loc[monthly["가용반영"]]
    subtotal = included.groupby(["생산계획년월", "공정"], as_index=False).agg(
        {"대수": "sum", "환산대수": "sum"}
    )
    return subtotal.rename(columns={"대수": "Dynamic가용대수", "환산대수": "Dynamic가용환산대수"})


def processes_in(spans: pd.DataFrame, baseline: pd.DataFrame) -> list[str]:
    """설비가 실제로 있는 공정 목록. Cut-off 누락을 재는 기준이 된다."""
    names: set[str] = set()
    if not spans.empty and "공정소분류" in spans.columns:
        names |= {str(value).strip() for value in spans["공정소분류"].dropna()}
    if not baseline.empty and "공정" in baseline.columns:
        names |= {str(value).strip() for value in baseline["공정"].dropna()}
    return sorted(name for name in names if name)
