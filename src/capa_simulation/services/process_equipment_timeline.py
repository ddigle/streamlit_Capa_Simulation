# Purpose: 공정 하나의 설비 일정(신규 호기·비가동 손실·전월 대비·판정)을 생산월 좌표로 정리한다.

"""공정 Capa 상세의 설비 일정(Dynamic, 참고).

공정 Capa 상세 페이지는 공식 요약 표 아래에 그 공정의 설비 일정을 **같은 달 칸**에 맞춰 그린다 —
신규 호기마다 한 줄(필요 단축 일정 양식), 그 아래 호기별 비가동 화살표, 그리고 그 둘이 가용대수를
어떻게 바꿨는지(전월 대비). 이 모듈은 그 재료를 순수 함수로 만든다. **어느 DB 도 열지 않는다.**

## 생산월 좌표

월 칸은 생산월이다. 어떤 날 `d` 는 W/D 구간 `(전월 말일 - c, 당월 말일 - c]`
(`services/wd_window.py`)가 그날을 담는 달에 선다 — 곧 `d + c` 의 달력 월이다(`c` 는 Cut-off 의
내림 일수). 칸 안 위치는
`(d + c).day - 1` 을 그 달 일수로 나눈 비율이라 구간 첫날이 칸의 왼쪽 끝이다
(`production_position`). 날짜의 뜻은 엔진과 같다 — Qual·반입·비가동 경계는 **다음 날부터**, 정지·
반출/이설은 **당일부터**다. 그래서 표지가 앉은 칸이 곧 가용이 바뀐 칸이다.

## 신규 호기 줄

설비키(Main 설비 묶음) 하나가 한 줄이다. 대상은 기존설비 N·보관 N·사용기준 HBM·EDP·Qual 있음인
행이고(세지 않는 모듈은 묶음에 넣지 않는다 — 단축 후보와 같다), Qual상태 「완료」와 정지·반출/이설
일정이 적힌 호기도 든다. 묶음의 반입·Qual 은 가장 늦은 모듈의 날, 정지·반출/이설은 가장 이른
날이다. 줄에 서는 것은 기여 시작(Qual 다음 날)이 축 안인 호기와 단축 계획에 든 호기다
(`unit_events`).
신규 줄이 없는 호기(기존설비 Y, 축 앞에 Qual 을 마친 호기)가 축 안에서 정지·반출/이설되면 따로
모은다(`exiting_unit_rows`) — 전월 대비의 `반출이설` 이 어느 호기에서 왔는지 보이는 재료다.

## 비가동 손실 — 반사실로 잰다

비가동이 가용을 깎았는지는 비가동 표만 보고는 모른다 — 셋업 중·보관·입고 전 호기의 비가동은 엔진이
가용으로 세지 않던 날이라 깎을 것이 없다. 그래서 공정 호기만으로 생애주기 구간을 **두 번** 만든다
(실제 비가동 / 비가동 비움, `build_equipment_lifecycle_spans(with_unit_share=True)`). 둘을 같은
월별 기여(`build_monthly_equipment_contributions`)에 넣어 「가용」 환산대수 차이가 호기 x 월의
손실이다(`downtime_loss`). 비가동 한 행의 몫은 비가동 없는 쪽의 가용 구간을 그 행의
`[시작일, 종료일]` 로 잘라 같은 월별 기여에 넣은 값이다(`downtime_arrows`). 한 호기의 비가동 행이
겹치면 겹친 날은 시작일이 이른 행에 한 번만 매긴다 — 엔진도 그날을 한 번 비가동으로 본다. 그래서
행들의 합이 늘 그 호기의 손실과 같다.

## 전월 대비

비가동 없는 쪽의 호기별 증감을 늘어난 몫(신규 +)과 줄어든 몫(정지·반출/이설 −)으로 가르고, 손실의
증감을 비가동으로 둔다 — `전월대비 = 신규 + 비가동 + 반출이설`(`availability_bridge`). 비가동이
없으면 호기의 가용은 반입·Qual 로 한 번 늘고 정지·반출/이설로 한 번 줄 뿐이라 갈림이 깨끗하다. 한
호기가 앞 달에 늘고 이번 달에 나가면 그 호기의 몫은 순증감 한쪽에 든다.

## Dynamic 판정

설비 일정 구획은 저장본 → 공정 이름(설비 마스터 `공정소분류`·기존보유 `공정` 이 시뮬레이션
공정과 **완전히 같은 이름**) → Cut-off → 사용기준 HBM·EDP 호기 차례로 보고, 처음 걸린 까닭 하나를
돌려준다(`dynamic_readiness`). 이름을 Cut-off 보다 먼저 보는 것은 필요 단축 일정 계획과 같은 까닭을
내려는 것이다 — 「Cut-off 미기재」는 `ShorteningPlan.missing_cutoff`(설비는 있고 Cut-off 가 없는
공정), 「설비 없음」은 그 밖의 `required_only` 와 맞는다. 기존보유만 있는 공정은 통과하되 호기 줄이
없다.
"""

from __future__ import annotations

import calendar
import math
from bisect import bisect_left
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import NamedTuple

import pandas as pd

from capa_simulation.services.equipment_availability import build_equipment_lifecycle_spans
from capa_simulation.services.equipment_contract import (
    ARRIVAL_DATE_COLUMN,
    CONVERSION_RATIO_COLUMN,
    COUNT_CATEGORY_COLUMN,
    COUNTED_COLUMN,
    EQUIPMENT_ID_COLUMN,
    EXIT_FOLLOWS_COLUMN,
    EXIT_SCHEDULE_COLUMNS,
    EXIT_STARTS_COLUMN,
    QUAL_STATUS_COLUMN,
    RELOCATION_DATE_COLUMN,
    STOP_DATE_COLUMN,
    STORAGE_FLAG_COLUMN,
    counts_for_capacity,
)
from capa_simulation.services.equipment_units import UNIT_KEY_COLUMN, unit_keys
from capa_simulation.services.equipment_validation import (
    prepare_downtime_for_prepared_equipment,
    prepare_equipment_master,
)
from capa_simulation.services.monthly_equipment_availability import (
    BASELINE_CATEGORY,
    build_monthly_equipment_contributions,
)
from capa_simulation.services.process_cutoff import ALL_PRODUCTS, cutoff_lookup
from capa_simulation.services.required_shortening import KIND_NEW, KIND_SHORTENED, unit_number
from capa_simulation.services.wd_window import WdWindow, wd_window

__all__ = [
    "ARROW_COLUMNS",
    "BRIDGE_COLUMNS",
    "EXIT_UNIT_COLUMNS",
    "MISSING_CUTOFF",
    "NEW_UNIT_COLUMNS",
    "NO_COUNTED_UNITS",
    "NO_EQUIPMENT",
    "NO_SNAPSHOT",
    "READY",
    "ROW_NEW",
    "ROW_SHORTENED",
    "ROW_VIRTUAL",
    "UNIT_EVENT_COLUMNS",
    "UNIT_MONTH_COLUMNS",
    "DynamicReadiness",
    "ProcessEquipmentTimeline",
    "ProductionPosition",
    "availability_bridge",
    "build_process_equipment_timeline",
    "downtime_arrows",
    "downtime_loss",
    "dynamic_readiness",
    "exiting_unit_rows",
    "keep_released_units",
    "month_share",
    "new_unit_rows",
    "production_position",
    "unit_events",
]

_ONE_DAY = timedelta(days=1)
_AVAILABLE = "가용"
# 부동소수 끝자리를 털어 내는 자리. `required_shortening` 과 같은 9자리다.
_DECIMALS = 9

ROW_SHORTENED = "단축"
"""단축 계획에 든 신규 호기 줄. 기존 기여 시작에서 목표 기여 시작까지 당긴다."""

ROW_NEW = "신규"
"""단축하지 않는 신규 호기 줄."""

ROW_VIRTUAL = "추가"
"""가상 호기 「추가N」 줄. 계획의 `구분` 「신규」(`KIND_NEW`)가 이 줄이 된다."""

READY = "ready"
NO_SNAPSHOT = "no_snapshot"
MISSING_CUTOFF = "missing_cutoff"
NO_EQUIPMENT = "no_equipment"
NO_COUNTED_UNITS = "no_counted_units"

_READINESS_REASONS = {
    NO_SNAPSHOT: "저장본 없음",
    MISSING_CUTOFF: "Cut-off 미기재",
    NO_EQUIPMENT: "설비 없음",
    NO_COUNTED_UNITS: "HBM·EDP 호기 없음",
}
_READINESS_DETAILS = {
    NO_SNAPSHOT: "설비 DB 에 저장된 설비 마스터가 없습니다.",
    MISSING_CUTOFF: "가용설비 현황의 공정별 Cut-off 에 이 공정이 없습니다.",
    NO_EQUIPMENT: (
        "설비 마스터 공정소분류와 기존보유 공정에 이 공정과 같은 이름이 없습니다 — "
        "이름이 완전히 같아야 맞댑니다."
    ),
    NO_COUNTED_UNITS: (
        "이 공정의 설비 마스터 호기에 사용기준 HBM·EDP 인 호기가 없고 기존보유도 없습니다."
    ),
}

# ▼ 의 구분 글자. 그 날짜가 온 컬럼이다.
EXIT_KIND_STOP = "정지"
EXIT_KIND_RELOCATION = "반출/이설"
EXIT_KINDS = {STOP_DATE_COLUMN: EXIT_KIND_STOP, RELOCATION_DATE_COLUMN: EXIT_KIND_RELOCATION}

NEW_UNIT_COLUMNS = (
    "호기",
    EQUIPMENT_ID_COLUMN,
    "Model",
    "모듈 수",
    ARRIVAL_DATE_COLUMN,
    "Qual일정",
    "기여 시작",
    QUAL_STATUS_COLUMN,
    "반출이설일",
    "반출이설구분",
    "모듈별 Qual",
    "축 안",
)
"""신규 호기(설비키) 한 줄 — 단축 계획을 겹치기 전. 날짜는 `date`(없으면 None)다.

- `호기` 는 설비키(Main 설비, 없으면 설비명), `설비명` 은 묶음의 모듈 행을 「, 」로 잇는다.
- `반입일정`·`Qual일정` 은 가장 늦은 모듈, `반출이설일` 은 가장 이른 정지·반출/이설일정이고
  `반출이설구분` 은 그 날짜가 온 컬럼 — 「정지」(정지일정)·「반출/이설」(반출/이설일정)이다.
  같은 날이면 정지가 먼저고, 한 행에 두 날짜가 같은 날이면 그 행은 반출/이설이다
  (`_earliest_exit`).
- `모듈별 Qual` 은 모듈이 둘 이상일 때 `(설비명, Qual)` 튜플이다(풍선용, 하나면 빈 튜플).
- `축 안` 은 기여 시작(Qual 다음 날)의 생산월이 축 안인가.
"""

UNIT_EVENT_COLUMNS = (
    "줄",
    "호기",
    EQUIPMENT_ID_COLUMN,
    "Model",
    "모듈 수",
    ARRIVAL_DATE_COLUMN,
    "Qual일정",
    "기여 시작",
    QUAL_STATUS_COLUMN,
    "반출이설일",
    "반출이설구분",
    "모듈별 Qual",
    "목표 Qual",
    "목표 기여 시작",
    "단축일수",
    "늘어난 환산대수",
    "월별 늘어난 환산대수",
    "반입 전",
    "대상 월",
    "해소 기여 월",
    "반입 위치",
    "기여 시작 위치",
    "기여 시작 축 밖",
    "목표 기여 위치",
    "반출이설 위치",
)
"""③ 신규 설비 줄(`unit_events`). 차례가 곧 그리는 줄 차례다.

- `줄` — `ROW_SHORTENED`·`ROW_NEW`·`ROW_VIRTUAL`.
- 단축 칸(`목표 Qual`~`해소 기여 월`)은 계획(`LevelPlan.units`)의 값이다. `반입 전` 은 목표 Qual 이
  반입일정보다 이른가, `해소 기여 월` 은 `YYYYMM` 정수 튜플이다. `늘어난 환산대수` 는 대상 월
  구간의 몫(호기 하나의 요약), `월별 늘어난 환산대수` 는 달마다의 몫 `((YYYYMM, 몫), …)` 이다 —
  한 달의 증분은 그 달 몫이다(`required_shortening.UNIT_PLAN_COLUMNS`).
- 단축 줄의 `Qual일정`(곧 `기여 시작` = 그 다음 날)과 `모듈 수` 는 계획의 `기존 Qual`·`모듈 수` 다 —
  ●→◀ 길이가 `단축일수` 와 맞게 하려는 것이다. 계획은 정지·반출/이설 예정이나 Qual상태 「완료」
  모듈을 묶음에서 빼므로(단축 후보) 묶음의 가장 늦은 Qual 과 다를 수 있다. 그때 갈린 모듈은
  `모듈별 Qual`(묶음 전체)이 보인다. 반입·Qual상태·반출이설·설비명·Model 은 묶음의 값이다.
- `… 위치` 는 생산월 좌표(`production_position.x`, 축 밖은 0 또는 달 수로 자른다)이고 날짜가 없으면
  NaN 이다. 날짜의 뜻은 엔진과 같다 — 반입은 다음 날(x(반입일 + 1)), 기여 시작·목표 기여는 그날(이미
  Qual 다음 날이다), 정지·반출/이설은 실행일 당일의 좌표다. `기여 시작 축 밖` 은 기여 시작이 축
  밖이라 잘렸는가(축 뒤의 호기를 축 안으로 당긴 단축 줄).
"""

EXIT_UNIT_COLUMNS = (
    "호기",
    EQUIPMENT_ID_COLUMN,
    "Model",
    "모듈 수",
    "기존설비여부",
    "반출이설일",
    "반출이설구분",
    "반출이설 위치",
)
"""축 안에서 정지·반출/이설되는 호기(설비키) 한 줄 — ③ 신규 줄에 서지 않는 것(`exiting_unit_rows`).

② 전월 대비의 `반출이설` 이 어느 호기에서 왔는지 보이려는 재료다. 기존설비 Y 호기나 축 앞에 Qual 을
마친 호기는 ③ 에 줄이 없어 그림 어디에도 ▼ 가 서지 않기 때문이다. `반출이설일` 은 묶음에서 가장
이른 정지·반출/이설일정, `반출이설 위치` 는 그 당일의 생산월 좌표다. `기존설비여부` 는 모듈의 값을
「, 」로 잇는다.
"""

UNIT_MONTH_COLUMNS = (
    "생산계획년월",
    EQUIPMENT_ID_COLUMN,
    "설비키",
    "구간일수",
    "실제 기여일수",
    "비가동 없음 기여일수",
    "손실 기여일수",
    "실제 환산대수",
    "비가동 없음 환산대수",
    "손실 환산대수",
)
"""호기(모듈 행) x 월의 「가용」 기여 — 실제와 비가동을 비운 반사실, 그 차이(`downtime_loss`)."""

BRIDGE_COLUMNS = (
    "생산계획년월",
    "기존보유",
    "호기 가용",
    "가용대수",
    "전월대비",
    "신규",
    "비가동",
    "반출이설",
)
"""② 전월 대비(`availability_bridge`). 환산대수다. 첫 달의 증감 칸은 NaN 이다.

`가용대수 = 기존보유 + 호기 가용` 은 필요 단축 일정 계획의 `가용대수`(같은 공정·달)와 같고,
`전월대비 = 신규 + 비가동 + 반출이설` 이다. `비가동` 은 손실이 줄면 + 다.
"""

ARROW_COLUMNS = (
    EQUIPMENT_ID_COLUMN,
    "설비키",
    "Model",
    "모듈 수",
    "비가동유형",
    "시작일",
    "종료일",
    "열린 구간",
    "이전부터",
    "꼬리 위치",
    "촉 위치",
    "덮는 날 수",
    "손실 기여일수",
    "손실 환산대수",
    "달별 손실",
    "첫 달",
    "손실 최대 월",
    "가용 감소",
)
"""④ 비가동 화살표 한 행 = 비가동 표 한 행(`downtime_arrows`).

- 손실 기여일은 `[시작일 + 1, 종료일 + 1]` 이라 꼬리는 x(시작일 + 1), 촉은 x(종료일 + 2) 다.
  종료일이 빈 열린 구간은 촉이 축 끝(달 수)이고, 축 앞에서 시작한 것은 꼬리가 0 이다(`이전부터`).
- `덮는 날 수` 는 손실 기여일 구간이 축 안에서 덮는 날 수, `손실 기여일수`·`손실 환산대수` 는 그
  가운데 비가동이 없었으면 가용이었던 몫이다. 같은 설비명의 앞선(시작일이 이른) 행과 겹친 날은 그
  행의 몫이라 여기서 빼므로, 한 호기의 행들을 더하면 그 호기의 손실과 같다. `달별 손실` 은 덮는
  달마다 `(YYYYMM, 손실 환산대수)` 튜플이다.
- `가용 감소` 가 거짓이면 깎은 가용이 없다(셋업 중·보관·입고 전·사용기준 제외 호기, 또는 앞선 행이
  이미 깎은 날뿐인 겹친 행).
- 차례: 가용을 깎은 호기가 앞이고, 호기마다 첫 손실 비가동의 시작일 → 호기 번호다. 같은 `설비키` 는
  붙어 있고 그 안은 시작일 차례다.
"""


class ProductionPosition(NamedTuple):
    """날짜 하나의 생산월 좌표."""

    x: float
    """축 위 좌표 — 달 index + 달 안 비율. 축 앞이면 0, 축 뒤면 달 수로 자른다."""

    month: int
    """그날이 기여하는 생산월 `YYYYMM`. 축 밖이어도 실제 생산월이다."""

    before: bool
    """축 첫 달보다 앞이다."""

    after: bool
    """축 끝 달보다 뒤다."""


def production_position(day: date, cutoff_days: float, months: Sequence[int]) -> ProductionPosition:
    """날짜를 생산월 좌표로 옮긴다.

    `p = day + int(cutoff)`, `x = 달 index + (p.day - 1) / 그 달 일수` 다.

    W/D(M) = `(전월 말일 - c, 당월 말일 - c]` 라 `day` 를 담는 달은 `day + c` 의 달력 월이다
    (`wd_window` 와 같은 내림). 그 달이 축에 없고 축 안쪽(달이 이어지지 않는 축)이면 다음 축 달의
    왼쪽 끝에 놓는다.
    """
    ordered = sorted({int(month) for month in months})
    if not ordered:
        raise ValueError("생산월 축에 달이 없습니다.")
    if cutoff_days < 0:
        raise ValueError(f"Cutoff 는 음수일 수 없습니다: {cutoff_days}")
    shifted = day + timedelta(days=int(cutoff_days))
    month = shifted.year * 100 + shifted.month
    if month < ordered[0]:
        return ProductionPosition(0.0, month, True, False)
    if month > ordered[-1]:
        return ProductionPosition(float(len(ordered)), month, False, True)
    index = bisect_left(ordered, month)
    if ordered[index] != month:
        return ProductionPosition(float(index), month, False, False)
    days = calendar.monthrange(shifted.year, shifted.month)[1]
    return ProductionPosition(index + (shifted.day - 1) / days, month, False, False)


# ---------------------------------------------------------------------- Dynamic 판정


@dataclass(frozen=True)
class DynamicReadiness:
    """공정 하나에 설비 일정 구획을 세울 수 있는가와 그 까닭."""

    status: str
    """`READY`·`NO_SNAPSHOT`·`MISSING_CUTOFF`·`NO_EQUIPMENT`·`NO_COUNTED_UNITS`."""

    cutoff_days: int | None = None
    """그 공정의 Cut-off(내림 일수). Cut-off 가 없거나 저장본이 없어 멈추면 None 이다."""

    has_units: bool = False
    """설비 마스터에 사용기준 HBM·EDP 호기가 있는가. 기존보유만 있는 공정은 거짓이다(② 만 선다).

    이름 확인을 지난 판정(`MISSING_CUTOFF`·`NO_COUNTED_UNITS`·`READY`)에서만 채운다.
    """

    has_baseline: bool = False
    """기존보유에 이 공정 행이 있는가. `has_units` 와 같이 이름 확인을 지난 판정에서만 채운다."""

    @property
    def ready(self) -> bool:
        return self.status == READY

    @property
    def reason(self) -> str:
        """배지에 적는 짧은 까닭. 통과했으면 빈 글자다."""
        return _READINESS_REASONS.get(self.status, "")

    @property
    def detail(self) -> str:
        """「설비 일정 없음」 카드에 적는 한 줄. 통과했으면 빈 글자다."""
        return _READINESS_DETAILS.get(self.status, "")

    @property
    def badge(self) -> str:
        """머리 배지 — 「설비 일정 참고」 또는 「설비 일정 없음: <까닭>」."""
        return "설비 일정 참고" if self.ready else f"설비 일정 없음: {self.reason}"


def dynamic_readiness(
    equipment: pd.DataFrame | None,
    baseline: pd.DataFrame | None,
    cutoff: pd.DataFrame | None,
    *,
    process: str,
) -> DynamicReadiness:
    """저장본 → 공정 이름 완전 일치 → Cut-off → HBM·EDP 호기 차례로 보고 처음 걸린 까닭을 낸다.

    이름을 Cut-off 보다 먼저 본다 — 필요 단축 일정 계획의 갈래와 같은 까닭을 내려는 것이다. 계획은
    설비(마스터 `공정소분류`·기존보유 `공정`)가 있는 공정만 `missing_cutoff` 로 두고, 설비가 없는
    공정은 `required_only` 에만 둔다. 설비도 Cut-off 도 없는 공정에 「Cut-off 미기재」를 내면
    Cut-off 를 적어도 다음 판정이 「설비 없음」이라 구획이 열리지 않는다.

    `equipment` 가 None 이면 설비 DB 에 저장본이 없는 것이다(샘플 fleet 을 넘기지 않는다).
    이름은 앞뒤 공백만 떼고 견준다 — 필요 단축 일정이 맞대는 규칙과 같다. 회차마다 불러도 되게
    마스터를 검증하지 않는다(설비명이 빈 행만 뺀다) — 계약 위반은 계획·설비 일정 계산이 멈추며
    알린다.
    """
    if equipment is None:
        return DynamicReadiness(NO_SNAPSHOT)
    name = str(process).strip()
    days = _cutoff_days(cutoff, name)
    rows = equipment
    if EQUIPMENT_ID_COLUMN in rows.columns:
        ids = rows[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
        rows = rows.loc[(ids.notna() & ids.ne("")).fillna(False).to_numpy()]
    in_process = (
        _process_mask(rows["공정소분류"], name)
        if "공정소분류" in rows.columns
        else pd.Series(False, index=rows.index, dtype="bool")
    )
    has_baseline = baseline is not None and bool(_baseline_rows(baseline, name).shape[0])
    if not in_process.any() and not has_baseline:
        return DynamicReadiness(NO_EQUIPMENT, cutoff_days=days)
    has_units = bool(counts_for_capacity(rows.loc[in_process.to_numpy()]).any())
    if days is None:
        return DynamicReadiness(MISSING_CUTOFF, has_units=has_units, has_baseline=has_baseline)
    if not has_units and not has_baseline:
        return DynamicReadiness(NO_COUNTED_UNITS, cutoff_days=days)
    return DynamicReadiness(READY, cutoff_days=days, has_units=has_units, has_baseline=has_baseline)


def _cutoff_days(cutoff: pd.DataFrame | None, process: str) -> int | None:
    if cutoff is None or cutoff.empty:
        return None
    lookup = {str(name).strip(): days for name, days in cutoff_lookup(cutoff).items()}
    days = lookup.get(process)
    if days is None or (isinstance(days, float) and math.isnan(days)):
        return None
    return int(days)


def _process_mask(values: pd.Series, process: str) -> pd.Series:
    return values.astype("string").str.strip().eq(process).fillna(False).astype("bool")


def _baseline_rows(baseline: pd.DataFrame, process: str) -> pd.DataFrame:
    if baseline.empty or "공정" not in baseline.columns:
        return baseline.iloc[0:0]
    return baseline.loc[_process_mask(baseline["공정"], process).to_numpy()]


# ---------------------------------------------------------------------- 묶음 결과


@dataclass(frozen=True)
class ProcessEquipmentTimeline:
    """공정 하나의 설비 일정(`build_process_equipment_timeline`). 오늘을 보지 않는다."""

    process: str
    months: tuple[int, ...]
    cutoff_days: int | None
    """None 이면 Cut-off 가 없어 아무것도 만들지 않았다(모든 표가 빈다)."""

    new_units: pd.DataFrame = field(default_factory=lambda: _empty(NEW_UNIT_COLUMNS))
    """`NEW_UNIT_COLUMNS` — 신규 호기 전부(축 밖 포함). 기여 시작 → 호기 번호 차례."""

    unit_months: pd.DataFrame = field(default_factory=lambda: _empty(UNIT_MONTH_COLUMNS))
    """`UNIT_MONTH_COLUMNS`."""

    bridge: pd.DataFrame = field(default_factory=lambda: _empty(BRIDGE_COLUMNS))
    """`BRIDGE_COLUMNS` — 축의 달마다 한 행."""

    arrows: pd.DataFrame = field(default_factory=lambda: _empty(ARROW_COLUMNS))
    """`ARROW_COLUMNS`."""

    baseline_units: float = 0.0
    """기존보유 합(안분하지 않는다)."""

    steady_units: int = 0
    """축 내내 모든 날 가용이고 신규 줄에도 없는 호기(설비키) 수 — ④ 의 「k대」 한 줄."""

    exits: pd.DataFrame = field(default_factory=lambda: _empty(EXIT_UNIT_COLUMNS))
    """`EXIT_UNIT_COLUMNS` — 축 안에서 정지·반출/이설되고 `new_units` 의 `축 안` 줄이 아닌 호기.

    어디에 그릴지(④ 의 ▼ 줄, 「정지·반출/이설 k대」 한 줄)는 화면이 정한다. 단축 계획이 축 밖에서
    당겨 ③ 에 세운 호기(`unit_events` 의 단축 줄)와 겹칠 수 있으므로 화면은 ③ 에 선 `호기` 를 뺀다.
    """


def build_process_equipment_timeline(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    *,
    process: str,
    months: Sequence[int],
) -> ProcessEquipmentTimeline:
    """공정 하나의 신규 호기·호기별 손실·전월 대비·비가동 화살표를 한 번에 만든다.

    설비 마스터를 그 공정(`공정소분류` 완전 일치)으로 거르고 비가동도 그 설비명으로 함께 거른다 —
    모듈 묶음은 검증이 같은 공정으로 막아 두어 거르기가 묶음을 쪼개지 않는다. 비가동은 **거르기 전**
    마스터로 검증한다(필요 단축 일정과 같은 오류에서 멈춘다). 구간은 그 공정 축의 W/D 구간만큼
    만들고 공용 구간 캐시를 쓰지 않는다.
    """
    ordered = tuple(sorted({int(month) for month in months}))
    name = str(process).strip()
    days = _cutoff_days(cutoff, name)
    if days is None or not ordered:
        return ProcessEquipmentTimeline(process=name, months=ordered, cutoff_days=days)
    prepared = prepare_equipment_master(equipment)
    prepared_downtime = prepare_downtime_for_prepared_equipment(downtime, prepared)
    chosen = prepared.loc[_process_mask(prepared["공정소분류"], name).to_numpy()].reset_index(
        drop=True
    )
    ids = set(chosen[EQUIPMENT_ID_COLUMN].astype("string").str.strip())
    own_downtime = prepared_downtime.loc[
        prepared_downtime[EQUIPMENT_ID_COLUMN].astype("string").str.strip().isin(ids).to_numpy()
    ].reset_index(drop=True)
    own_baseline = _baseline_rows(baseline, name)
    own_cutoff = _single_cutoff(name, days)
    windows = [wd_window(month, days) for month in ordered]
    ratios = {
        str(unit).strip(): float(ratio)
        for unit, ratio in zip(
            chosen[EQUIPMENT_ID_COLUMN], chosen[CONVERSION_RATIO_COLUMN], strict=True
        )
    }

    def spans(with_downtime: bool) -> pd.DataFrame:
        if chosen.empty:
            return pd.DataFrame()
        return build_equipment_lifecycle_spans(
            chosen,
            own_downtime if with_downtime else own_downtime.iloc[0:0],
            start_date=windows[0].boundary_start,
            end_date=windows[-1].boundary_end,
            with_unit_share=True,
        )

    actual_spans = spans(True)
    free_spans = spans(False)
    actual = build_monthly_equipment_contributions(
        actual_spans, own_baseline, own_cutoff, ordered, conversion_ratios=ratios
    )
    free = build_monthly_equipment_contributions(
        free_spans, own_baseline, own_cutoff, ordered, conversion_ratios=ratios
    )
    new_units = new_unit_rows(chosen, process=name, cutoff_days=days, months=ordered)
    arrows = downtime_arrows(
        own_downtime,
        free_spans,
        chosen,
        cutoff=own_cutoff,
        process=name,
        months=ordered,
        conversion_ratios=ratios,
    )
    unit_months = downtime_loss(actual, free)
    in_axis = set(new_units.loc[new_units["축 안"].astype("bool"), "호기"].astype(str))
    return ProcessEquipmentTimeline(
        process=name,
        months=ordered,
        cutoff_days=days,
        new_units=new_units,
        unit_months=unit_months,
        bridge=availability_bridge(actual, free, ordered),
        arrows=arrows,
        baseline_units=float(
            pd.to_numeric(own_baseline.get("기존보유대수", pd.Series(dtype="float64"))).sum()
        ),
        steady_units=_steady_units(chosen, unit_months, windows, excluded=in_axis),
        exits=exiting_unit_rows(
            chosen, process=name, cutoff_days=days, months=ordered, excluded=in_axis
        ),
    )


def _single_cutoff(process: str, days: int) -> pd.DataFrame:
    """그 공정 하나만 든 Cut-off 표(`cutoff_lookup` 이 읽는 꼴)."""
    return pd.DataFrame(
        {
            "공정": pd.Series([process], dtype="string"),
            "제품구분": pd.Series([ALL_PRODUCTS], dtype="string"),
            "Cutoff일수": pd.Series([float(days)], dtype="float64"),
            "비고": pd.Series([pd.NA], dtype="string"),
        }
    )


def _steady_units(
    master: pd.DataFrame,
    unit_months: pd.DataFrame,
    windows: Sequence[WdWindow],
    *,
    excluded: set[str],
) -> int:
    """세는 모듈이 축의 모든 달 모든 날 가용인 설비키 수(신규 줄에 선 호기는 뺀다)."""
    if master.empty:
        return 0
    counted = counts_for_capacity(master).to_numpy()
    keys = unit_keys(master).loc[counted].astype(str)
    ids = master.loc[counted, EQUIPMENT_ID_COLUMN].astype("string").str.strip().astype(str)
    full = {
        (int(month), str(unit))
        for month, unit, used, span in zip(
            unit_months["생산계획년월"],
            unit_months[EQUIPMENT_ID_COLUMN],
            unit_months["실제 기여일수"],
            unit_months["구간일수"],
            strict=True,
        )
        if int(used) == int(span)
    }
    modules: dict[str, list[str]] = {}
    for key, unit in zip(keys, ids, strict=True):
        modules.setdefault(key, []).append(unit)
    return sum(
        1
        for key, members in modules.items()
        if key not in excluded
        and all((window.year_month, unit) in full for window in windows for unit in members)
    )


# ---------------------------------------------------------------------- 신규 호기


def new_unit_rows(
    equipment: pd.DataFrame,
    *,
    process: str,
    cutoff_days: float,
    months: Sequence[int],
) -> pd.DataFrame:
    """그 공정의 신규 호기를 설비키마다 한 줄로(`NEW_UNIT_COLUMNS`). 축 밖 호기도 든다(`축 안`).

    대상은 기존설비 N·보관 N·사용기준 HBM·EDP·Qual 있음인 행이다. Qual상태 「완료」·정지·반출/이설
    예정도 든다 — 단축 후보보다 넓다. `equipment` 는 거르기 전 마스터여도 된다(공정으로 고른다).
    """
    prepared = prepare_equipment_master(equipment)
    name = str(process).strip()
    if prepared.empty:
        return _empty(NEW_UNIT_COLUMNS)
    eligible = (
        (
            _process_mask(prepared["공정소분류"], name)
            & prepared["기존설비여부"].eq("N")
            & prepared[STORAGE_FLAG_COLUMN].eq("N")
            & prepared["Qual일정"].notna()
            & counts_for_capacity(prepared)
        )
        .fillna(False)
        .astype("bool")
        .to_numpy()
    )
    chosen = prepared.loc[eligible]
    if chosen.empty:
        return _empty(NEW_UNIT_COLUMNS)
    keys = unit_keys(prepared).loc[chosen.index].astype(str)
    groups: dict[str, list[dict[str, object]]] = {}
    for key, record in zip(keys, chosen.to_dict("records"), strict=True):
        groups.setdefault(key, []).append({str(column): value for column, value in record.items()})
    rows: list[dict[str, object]] = []
    for key, members in groups.items():
        members.sort(key=lambda member: str(member[EQUIPMENT_ID_COLUMN]))
        quals = [_as_date(member["Qual일정"]) for member in members]
        qual = max(day for day in quals if day is not None)
        arrival = _latest(_as_date(member[ARRIVAL_DATE_COLUMN]) for member in members)
        exit_day, exit_kind = _earliest_exit(members)
        start = qual + _ONE_DAY
        position = production_position(start, cutoff_days, months)
        rows.append(
            {
                "호기": key,
                EQUIPMENT_ID_COLUMN: ", ".join(
                    str(member[EQUIPMENT_ID_COLUMN]).strip() for member in members
                ),
                "Model": _distinct_text(member["Model"] for member in members),
                "모듈 수": len(members),
                ARRIVAL_DATE_COLUMN: arrival,
                "Qual일정": qual,
                "기여 시작": start,
                QUAL_STATUS_COLUMN: _distinct_text(
                    member[QUAL_STATUS_COLUMN] for member in members
                ),
                "반출이설일": exit_day,
                "반출이설구분": exit_kind,
                "모듈별 Qual": (
                    tuple(
                        (str(member[EQUIPMENT_ID_COLUMN]).strip(), day)
                        for member, day in zip(members, quals, strict=True)
                    )
                    if len(members) > 1
                    else ()
                ),
                "축 안": not (position.before or position.after),
            }
        )
    rows.sort(key=lambda row: (row["기여 시작"], *_unit_order(str(row["호기"]))))
    frame = pd.DataFrame(rows, columns=list(NEW_UNIT_COLUMNS))
    frame["모듈 수"] = frame["모듈 수"].astype("int64")
    frame["축 안"] = frame["축 안"].astype("bool")
    return frame


def exiting_unit_rows(
    equipment: pd.DataFrame,
    *,
    process: str,
    cutoff_days: float,
    months: Sequence[int],
    excluded: Iterable[str] = (),
) -> pd.DataFrame:
    """축 안에서 정지·반출/이설되는 호기를 설비키마다 한 줄로(`EXIT_UNIT_COLUMNS`).

    대상은 그 공정의 보관 N·사용기준 HBM·EDP 행이다(기존설비 Y·N 모두). 묶음의 가장 이른
    정지·반출/이설일정(③ 의 ▼ 와 같은 규칙)이 축 안의 생산월에 들어야 한다. `excluded` 의
    설비키(③ 에 줄이 서는 신규 호기)는 뺀다. 차례는 반출이설일 → 호기 번호다.
    """
    prepared = prepare_equipment_master(equipment)
    if prepared.empty:
        return _empty(EXIT_UNIT_COLUMNS)
    name = str(process).strip()
    eligible = (
        (
            _process_mask(prepared["공정소분류"], name)
            & prepared[STORAGE_FLAG_COLUMN].eq("N")
            & counts_for_capacity(prepared)
            & prepared.loc[:, list(EXIT_SCHEDULE_COLUMNS)].notna().any(axis=1)
        )
        .fillna(False)
        .astype("bool")
        .to_numpy()
    )
    chosen = prepared.loc[eligible]
    if chosen.empty:
        return _empty(EXIT_UNIT_COLUMNS)
    skip = {str(key) for key in excluded}
    keys = unit_keys(prepared).loc[chosen.index].astype(str)
    groups: dict[str, list[dict[str, object]]] = {}
    for key, record in zip(keys, chosen.to_dict("records"), strict=True):
        if key not in skip:
            groups.setdefault(key, []).append(
                {str(column): value for column, value in record.items()}
            )
    rows: list[dict[str, object]] = []
    for key, members in groups.items():
        members.sort(key=lambda member: str(member[EQUIPMENT_ID_COLUMN]))
        exit_day, exit_kind = _earliest_exit(members)
        if exit_day is None:
            continue
        position = production_position(exit_day, cutoff_days, months)
        if position.before or position.after:
            continue
        rows.append(
            {
                "호기": key,
                EQUIPMENT_ID_COLUMN: ", ".join(
                    str(member[EQUIPMENT_ID_COLUMN]).strip() for member in members
                ),
                "Model": _distinct_text(member["Model"] for member in members),
                "모듈 수": len(members),
                "기존설비여부": _distinct_text(member["기존설비여부"] for member in members),
                "반출이설일": exit_day,
                "반출이설구분": exit_kind,
                "반출이설 위치": position.x,
            }
        )
    if not rows:
        return _empty(EXIT_UNIT_COLUMNS)
    rows.sort(key=lambda row: (row["반출이설일"], *_unit_order(str(row["호기"]))))
    frame = pd.DataFrame(rows, columns=list(EXIT_UNIT_COLUMNS))
    frame["모듈 수"] = frame["모듈 수"].astype("int64")
    frame["반출이설 위치"] = frame["반출이설 위치"].astype("float64")
    return frame


def _earliest_exit(members: Sequence[Mapping[str, object]]) -> tuple[date | None, str | None]:
    """설비(모듈 묶음)가 처음 나가는 날과 그 날짜가 온 컬럼의 구분(`EXIT_KINDS`).

    같은 날이면 `EXIT_KINDS` 차례(정지 먼저)로 고른다 — 글자 차례로 고르면 「반출/이설」이
    앞서, 모듈마다 따로 적은 정지·반출/이설이 같은 날인 묶음의 ▼ 가 개편 전(정지 = 옛
    반출)과 달라진다. 한 행에 두 날짜가 같은 날이면 그 행은 그날 바로 「반출/이설 완료」라
    (정지를 거치지 않는다) 반출/이설 하나로 본다.
    """
    found: list[tuple[date, int, str]] = []
    for member in members:
        days = {column: _as_date(member[column]) for column in EXIT_KINDS}
        same_day = days[STOP_DATE_COLUMN] is not None and (
            days[STOP_DATE_COLUMN] == days[RELOCATION_DATE_COLUMN]
        )
        for rank, (column, label) in enumerate(EXIT_KINDS.items()):
            day = days[column]
            if day is None or (same_day and column == STOP_DATE_COLUMN):
                continue
            found.append((day, rank, label))
    if not found:
        return None, None
    day, _, label = min(found)
    return day, label


def unit_events(timeline: ProcessEquipmentTimeline, plan_units: pd.DataFrame) -> pd.DataFrame:
    """신규 호기 줄에 단축 계획을 겹친다(`UNIT_EVENT_COLUMNS`). ③ 이 이 차례로 그린다.

    `plan_units` 는 `ShorteningPlan.at(목표).units` 다(다른 공정 줄은 걸러 낸다). 차례는 단축 대상
    (계획 차례 — 기존 Qual 이른 순 → 호기 번호) → 나머지 신규(기여 시작이 축 안인 호기, 기여 시작 →
    호기 번호) → 추가N(계획 차례)이다. 단축 대상은 기여 시작이 축 밖이어도 든다 — 계획이 축 안으로
    당긴 호기다.
    """
    if timeline.cutoff_days is None or not timeline.months:
        return _empty(UNIT_EVENT_COLUMNS)
    plan = _plan_rows(plan_units, timeline.process)
    base = {str(row["호기"]): row for row in _records(timeline.new_units)}
    rows: list[dict[str, object]] = []
    shortened: set[str] = set()
    for record in plan:
        if record["구분"] != KIND_SHORTENED:
            continue
        unit = str(record["호기"])
        shortened.add(unit)
        rows.append(_event(timeline, ROW_SHORTENED, base.get(unit), record, unit))
    for unit, row in base.items():
        if unit not in shortened and bool(row["축 안"]):
            rows.append(_event(timeline, ROW_NEW, row, None, unit))
    for record in plan:
        if record["구분"] == KIND_NEW:
            rows.append(_event(timeline, ROW_VIRTUAL, None, record, str(record["호기"])))
    if not rows:
        return _empty(UNIT_EVENT_COLUMNS)
    frame = pd.DataFrame(rows, columns=list(UNIT_EVENT_COLUMNS))
    for column in ("모듈 수", "단축일수", "대상 월"):
        frame[column] = pd.to_numeric(frame[column]).astype("Int64")
    for column in (
        "늘어난 환산대수",
        "반입 위치",
        "기여 시작 위치",
        "목표 기여 위치",
        "반출이설 위치",
    ):
        frame[column] = pd.to_numeric(frame[column]).astype("float64")
    for column in ("반입 전", "기여 시작 축 밖"):
        frame[column] = frame[column].astype("bool")
    return frame


def keep_released_units(
    events: pd.DataFrame, official_events: pd.DataFrame, units: Iterable[str]
) -> pd.DataFrame:
    """UPEH 가정 계획의 ③ 줄(`events`)에, 공식 계획에서는 당겼는데 가정 계획 줄에 없는 호기를 신규
    줄로 더한다 — 가정으로 단축이 필요 없어진 호기를 흐린 줄로 남기려고(공정 Capa 상세 P5).

    `official_events` 는 같은 설비 일정에 **공식** 계획을 겹친 `unit_events` 결과, `units` 는
    공식·가정의 단축일수가 다른 호기(`upeh_assumption.pull_changes`)다. 기여 시작이 축 밖이라 가정
    계획 줄에 들지 않은 호기만 더한다(축 안 호기는 이미 신규 줄로 있다). 차례는 추가N 앞이다.
    """
    present = set(events["호기"].astype(str)) if not events.empty else set()
    wanted = [str(unit) for unit in units if str(unit) not in present]
    if not wanted or official_events.empty:
        return events
    missing = official_events.loc[
        official_events["호기"].astype(str).isin(wanted).to_numpy()
    ].assign(줄=ROW_NEW)
    if missing.empty:
        return events
    if events.empty:
        return missing.reset_index(drop=True)
    virtual = events["줄"].astype(str).eq(ROW_VIRTUAL).to_numpy()
    return pd.concat([events.loc[~virtual], missing, events.loc[virtual]], ignore_index=True)


def _plan_rows(plan_units: pd.DataFrame, process: str) -> list[dict[str, object]]:
    if plan_units.empty:
        return []
    if "공정" in plan_units.columns:
        plan_units = plan_units.loc[_process_mask(plan_units["공정"], process).to_numpy()]
    return _records(plan_units)


def _event(
    timeline: ProcessEquipmentTimeline,
    kind: str,
    base: Mapping[str, object] | None,
    plan: Mapping[str, object] | None,
    unit: str,
) -> dict[str, object]:
    assert timeline.cutoff_days is not None
    days = timeline.cutoff_days
    months = timeline.months

    def x(day: date | None) -> float:
        return math.nan if day is None else production_position(day, days, months).x

    # 계획이 있는 줄은 계획의 기존 Qual·모듈 수를 쓴다 — 계획이 묶음에서 뺀 모듈(정지·반출/이설
    # 예정, Qual상태 「완료」)이 있으면 묶음의 가장 늦은 Qual 과 갈려 ●→◀ 길이가 단축일수와
    # 어긋난다.
    qual = _as_date(plan.get("기존 Qual")) if plan is not None else None
    if qual is None and base is not None:
        qual = _as_date(base["Qual일정"])
    modules = _whole(plan.get("모듈 수")) if plan is not None else None
    if modules is None and base is not None:
        modules = _whole(base["모듈 수"])
    start = qual + _ONE_DAY if qual is not None else None
    arrival = _as_date(base[ARRIVAL_DATE_COLUMN]) if base is not None else None
    exit_day = _as_date(base["반출이설일"]) if base is not None else None
    target = _as_date(plan["목표 Qual"]) if plan is not None else None
    target_start = _as_date(plan["기여 시작"]) if plan is not None else None
    start_position = production_position(start, days, months) if start is not None else None
    return {
        "줄": kind,
        "호기": unit,
        EQUIPMENT_ID_COLUMN: base[EQUIPMENT_ID_COLUMN] if base is not None else None,
        "Model": base["Model"] if base is not None else None,
        "모듈 수": modules,
        ARRIVAL_DATE_COLUMN: arrival,
        "Qual일정": qual,
        "기여 시작": start,
        QUAL_STATUS_COLUMN: base[QUAL_STATUS_COLUMN] if base is not None else None,
        "반출이설일": exit_day,
        "반출이설구분": base["반출이설구분"] if base is not None else None,
        "모듈별 Qual": base["모듈별 Qual"] if base is not None else (),
        "목표 Qual": target,
        "목표 기여 시작": target_start,
        "단축일수": None if plan is None else _whole(plan.get("단축일수")),
        "늘어난 환산대수": (
            math.nan if plan is None else float(str(plan.get("늘어난 환산대수", math.nan)))
        ),
        "월별 늘어난 환산대수": ()
        if plan is None
        else _month_shares(plan.get("월별 늘어난 환산대수")),
        "반입 전": bool(
            kind == ROW_SHORTENED
            and target is not None
            and arrival is not None
            and target < arrival
        ),
        "대상 월": None if plan is None else _whole(plan.get("대상 월")),
        "해소 기여 월": () if plan is None else _month_tuple(plan.get("해소 기여 월")),
        "반입 위치": x(None if arrival is None else arrival + _ONE_DAY),
        "기여 시작 위치": math.nan if start_position is None else start_position.x,
        "기여 시작 축 밖": bool(
            start_position is not None and (start_position.before or start_position.after)
        ),
        "목표 기여 위치": x(target_start),
        "반출이설 위치": x(exit_day),
    }


def _month_shares(value: object) -> tuple[tuple[int, float], ...]:
    """계획의 `월별 늘어난 환산대수`(`((YYYYMM, 몫), …)`)를 그대로 — 칸이 없거나 비면 빈 튜플."""
    if not isinstance(value, (tuple, list)):
        return ()
    return tuple(
        (int(str(item[0])), float(str(item[1])))
        for item in value
        if isinstance(item, (tuple, list)) and len(item) == 2
    )


def month_share(shares: object, month: int) -> float | None:
    """`월별 늘어난 환산대수` 에서 그 달 몫 — 칸이 없으면(튜플이 아니면) None, 그 달이 없으면 0."""
    if not isinstance(shares, (tuple, list)):
        return None
    for item_month, share in _month_shares(shares):
        if item_month == month:
            return share
    return 0.0


def _month_tuple(value: object) -> tuple[int, ...]:
    """계획의 `해소 기여 월`(「YYYYMM, YYYYMM」 글자)을 정수 튜플로."""
    if _blank(value):
        return ()
    return tuple(int(part) for part in str(value).split(",") if part.strip())


# ---------------------------------------------------------------------- 비가동 손실


def downtime_loss(actual: pd.DataFrame, counterfactual: pd.DataFrame) -> pd.DataFrame:
    """호기 x 월의 비가동 손실(`UNIT_MONTH_COLUMNS`).

    두 표는 같은 공정·축으로 만든 `build_monthly_equipment_contributions` 결과다 — 실제 비가동과
    비가동을 비운 반사실. 「가용」 분류의 호기 행만 맞대고 한쪽에 없는 칸은 0 이다. 손실은
    반사실 - 실제다.
    """
    left = _available_units(actual)
    right = _available_units(counterfactual)
    keys = ["생산계획년월", EQUIPMENT_ID_COLUMN, "설비키", "구간일수"]
    merged = left.merge(right, on=keys, how="outer", suffixes=("_실제", "_반사실"))
    if merged.empty:
        return _empty(UNIT_MONTH_COLUMNS)
    for column in ("기여일수_실제", "기여일수_반사실"):
        merged[column] = pd.to_numeric(merged[column]).fillna(0).astype("int64")
    for column in ("환산대수_실제", "환산대수_반사실"):
        merged[column] = pd.to_numeric(merged[column]).fillna(0.0).astype("float64")
    result = pd.DataFrame(
        {
            "생산계획년월": merged["생산계획년월"].astype("int64"),
            EQUIPMENT_ID_COLUMN: merged[EQUIPMENT_ID_COLUMN].astype(str),
            "설비키": merged["설비키"].astype(str),
            "구간일수": merged["구간일수"].astype("int64"),
            "실제 기여일수": merged["기여일수_실제"],
            "비가동 없음 기여일수": merged["기여일수_반사실"],
            "손실 기여일수": merged["기여일수_반사실"] - merged["기여일수_실제"],
            "실제 환산대수": merged["환산대수_실제"],
            "비가동 없음 환산대수": merged["환산대수_반사실"],
            "손실 환산대수": (merged["환산대수_반사실"] - merged["환산대수_실제"]).round(_DECIMALS)
            + 0.0,
        }
    )
    return result.sort_values(["생산계획년월", EQUIPMENT_ID_COLUMN], kind="stable").reset_index(
        drop=True
    )


def _available_units(contributions: pd.DataFrame) -> pd.DataFrame:
    """「가용」 호기 행만(기존보유 줄은 뺀다), 모듈 행 x 월로."""
    columns = ["생산계획년월", EQUIPMENT_ID_COLUMN, "설비키", "구간일수", "기여일수", "환산대수"]
    if contributions.empty:
        return pd.DataFrame({column: pd.Series(dtype="object") for column in columns})
    chosen = contributions.loc[
        contributions["분류"].astype("string").eq(_AVAILABLE).fillna(False).to_numpy()
        & contributions[EQUIPMENT_ID_COLUMN].notna().to_numpy()
    ]
    frame = chosen.loc[:, columns].copy()
    frame[EQUIPMENT_ID_COLUMN] = frame[EQUIPMENT_ID_COLUMN].astype(str)
    frame["설비키"] = frame["설비키"].astype(str)
    return frame


def availability_bridge(
    actual: pd.DataFrame, counterfactual: pd.DataFrame, months: Sequence[int]
) -> pd.DataFrame:
    """달마다 가용대수와 전월 대비 갈림(`BRIDGE_COLUMNS`).

    `actual`·`counterfactual` 은 `downtime_loss` 와 같은 두 기여 표다. 반사실의 호기별 증감이 + 면
    신규, - 면 반출이설이고, 손실 합의 증감에 - 를 붙인 것이 비가동이다.
    """
    ordered = tuple(sorted({int(month) for month in months}))
    baseline = _baseline_by_month(actual)
    real = _units_by_month(actual)
    free = _units_by_month(counterfactual)
    units = sorted({unit for unit, _ in real} | {unit for unit, _ in free})
    rows: list[dict[str, object]] = []
    for index, month in enumerate(ordered):
        held = baseline.get(month, 0.0)
        own = sum(real.get((unit, month), 0.0) for unit in units)
        row: dict[str, object] = {
            "생산계획년월": month,
            "기존보유": held,
            "호기 가용": _tidy(own),
            "가용대수": _tidy(held + own),
            "전월대비": math.nan,
            "신규": math.nan,
            "비가동": math.nan,
            "반출이설": math.nan,
        }
        if index:
            previous = ordered[index - 1]
            gained = 0.0
            lost = 0.0
            loss_now = 0.0
            loss_before = 0.0
            for unit in units:
                change = free.get((unit, month), 0.0) - free.get((unit, previous), 0.0)
                if change > 0:
                    gained += change
                else:
                    lost += change
                loss_now += free.get((unit, month), 0.0) - real.get((unit, month), 0.0)
                loss_before += free.get((unit, previous), 0.0) - real.get((unit, previous), 0.0)
            before_total = baseline.get(previous, 0.0) + sum(
                real.get((unit, previous), 0.0) for unit in units
            )
            row.update(
                {
                    "전월대비": _tidy(held + own - before_total),
                    "신규": _tidy(gained),
                    "비가동": _tidy(loss_before - loss_now),
                    "반출이설": _tidy(lost),
                }
            )
        rows.append(row)
    if not rows:
        return _empty(BRIDGE_COLUMNS)
    frame = pd.DataFrame(rows, columns=list(BRIDGE_COLUMNS))
    frame["생산계획년월"] = frame["생산계획년월"].astype("int64")
    for column in BRIDGE_COLUMNS[1:]:
        frame[column] = frame[column].astype("float64")
    return frame


def _baseline_by_month(contributions: pd.DataFrame) -> dict[int, float]:
    if contributions.empty:
        return {}
    rows = contributions.loc[
        contributions["분류"].astype("string").eq(BASELINE_CATEGORY.name).fillna(False).to_numpy()
    ]
    totals: dict[int, float] = {}
    for month, value in zip(rows["생산계획년월"], rows["환산대수"], strict=True):
        totals[int(month)] = totals.get(int(month), 0.0) + float(value)
    return totals


def _units_by_month(contributions: pd.DataFrame) -> dict[tuple[str, int], float]:
    frame = _available_units(contributions)
    totals: dict[tuple[str, int], float] = {}
    for month, unit, value in zip(
        frame["생산계획년월"], frame[EQUIPMENT_ID_COLUMN], frame["환산대수"], strict=True
    ):
        key = (str(unit), int(month))
        totals[key] = totals.get(key, 0.0) + float(value)
    return totals


def downtime_arrows(
    downtime: pd.DataFrame,
    counterfactual_spans: pd.DataFrame,
    equipment: pd.DataFrame,
    *,
    cutoff: pd.DataFrame,
    process: str,
    months: Sequence[int],
    conversion_ratios: Mapping[str, float],
) -> pd.DataFrame:
    """비가동 한 행마다 화살표 하나(`ARROW_COLUMNS`). 축과 겹치는 행만 남긴다.

    `downtime`·`equipment` 는 그 공정으로 거른(검증된) 비가동·마스터, `counterfactual_spans` 는 같은
    마스터로 **비가동을 비우고** 만든 세는 구간(`with_unit_share=True`)이다. 한 행의 손실은 반사실의
    가용 구간을 그 행의 `[시작일, 종료일]` 로 잘라 월별 기여에 넣은 값이다 — 경계 규칙(다음 날·정지
    당일)이 엔진 그대로 걸린다. 같은 설비명의 행이 겹치면 겹친 날은 시작일이 이른 행(같은 날이면 표
    차례)에 한 번만 매긴다 — 그래서 행들의 손실 합이 늘 그 호기의 손실(`downtime_loss`)과 같다.
    """
    name = str(process).strip()
    days = _cutoff_days(cutoff, name)
    ordered = tuple(sorted({int(month) for month in months}))
    if days is None or not ordered or downtime.empty:
        return _empty(ARROW_COLUMNS)
    windows = [wd_window(month, days) for month in ordered]
    first_day, last_day = windows[0].first_day, windows[-1].boundary_end
    keys = dict(
        zip(
            equipment[EQUIPMENT_ID_COLUMN].astype("string").str.strip().astype(str),
            unit_keys(equipment).astype(str),
            strict=True,
        )
    )
    group_size: dict[str, int] = {}
    for key in keys.values():
        group_size[key] = group_size.get(key, 0) + 1
    models = dict(
        zip(
            equipment[EQUIPMENT_ID_COLUMN].astype("string").str.strip().astype(str),
            equipment["Model"],
            strict=True,
        )
    )
    available = _available_spans(counterfactual_spans)

    # 같은 설비명의 비가동 행이 겹치면 겹친 날은 시작일이 이른 행에 한 번만 매긴다 — 엔진은 그날을
    # 한 번 비가동으로 보므로, 행마다 따로 세면 행들의 합이 그 호기의 손실보다 커진다.
    entries: list[tuple[date, int, str, object, date | None]] = []
    for index, (unit_value, kind, began, finished) in enumerate(
        zip(
            downtime[EQUIPMENT_ID_COLUMN],
            downtime["비가동유형"],
            downtime["시작일"],
            downtime["종료일"],
            strict=True,
        )
    ):
        start = _as_date(began)
        if start is not None:
            entries.append((start, index, str(unit_value).strip(), kind, _as_date(finished)))
    entries.sort(key=lambda entry: (entry[0], entry[1]))

    records: list[dict[str, object]] = []
    covered_months: list[list[int]] = []
    clipped: list[dict[str, object]] = []
    clipped_ratios: dict[str, float] = {}
    claimed: dict[str, list[tuple[date, date]]] = {}
    for start, _, unit, kind, end in entries:
        loss_start = start + _ONE_DAY
        loss_end = last_day if end is None else min(end + _ONE_DAY, last_day)
        if loss_start > last_day or (end is not None and end + _ONE_DAY < first_day):
            continue
        row_id = str(len(records))
        taken = claimed.setdefault(unit, [])
        for piece in available.get(unit, ()):
            low = max(piece.start, start)
            high = piece.end if end is None else min(piece.end, end)
            if low > high:
                continue
            for part_low, part_high in _unclaimed(low, high, taken):
                clipped.append(
                    {
                        EQUIPMENT_ID_COLUMN: row_id,
                        "공정소분류": name,
                        "공정대분류": None,
                        "상태": _AVAILABLE,
                        "시작일": part_low,
                        "종료일": part_high,
                        "설비지분": piece.share,
                        COUNT_CATEGORY_COLUMN: _AVAILABLE,
                        UNIT_KEY_COLUMN: row_id,
                        COUNTED_COLUMN: True,
                        EXIT_STARTS_COLUMN: piece.exit_starts and part_low == piece.start,
                        EXIT_FOLLOWS_COLUMN: piece.exit_follows and part_high == piece.end,
                    }
                )
            taken.append((low, high))
        clipped_ratios[row_id] = float(conversion_ratios.get(unit, 1.0))
        tail = production_position(loss_start, days, ordered)
        head = (
            ProductionPosition(float(len(ordered)), ordered[-1], False, True)
            if end is None
            else production_position(end + 2 * _ONE_DAY, days, ordered)
        )
        covered_from = max(loss_start, first_day)
        covered_months.append(
            [window.year_month for window in windows if window.overlap_days(covered_from, loss_end)]
        )
        key = keys.get(unit, unit)
        records.append(
            {
                EQUIPMENT_ID_COLUMN: unit,
                "설비키": key,
                "Model": _text(models.get(unit)),
                "모듈 수": group_size.get(key, 1),
                "비가동유형": _text(kind),
                "시작일": start,
                "종료일": end,
                "열린 구간": end is None,
                "이전부터": tail.before,
                "꼬리 위치": tail.x,
                "촉 위치": head.x,
                "덮는 날 수": max(0, (loss_end - covered_from).days + 1),
                "첫 달": _window_month(windows, covered_from),
            }
        )
    if not records:
        return _empty(ARROW_COLUMNS)
    losses = _clipped_losses(clipped, clipped_ratios, name, days, ordered)
    for index, (record, covered) in enumerate(zip(records, covered_months, strict=True)):
        by_month = losses.get(str(index), {})
        monthly = tuple((month, _tidy(by_month.get(month, (0, 0.0))[1])) for month in covered)
        total = _tidy(sum(found[1] for found in by_month.values()))
        biggest = max(monthly, key=lambda pair: pair[1]) if monthly else None
        record.update(
            {
                "손실 기여일수": sum(found[0] for found in by_month.values()),
                "손실 환산대수": total,
                "달별 손실": monthly,
                "손실 최대 월": biggest[0] if biggest is not None and biggest[1] > 0 else None,
                "가용 감소": total > 0,
            }
        )
    return _ordered_arrows(records)


class _Piece(NamedTuple):
    start: date
    end: date
    share: float
    exit_starts: bool
    exit_follows: bool


def _available_spans(spans: pd.DataFrame) -> dict[str, tuple[_Piece, ...]]:
    """반사실 구간 가운데 세는 「가용」 구간을 설비명마다."""
    if spans.empty:
        return {}
    chosen = spans.loc[
        spans[COUNT_CATEGORY_COLUMN].astype("string").eq(_AVAILABLE).fillna(False).to_numpy()
        & spans[COUNTED_COLUMN].fillna(False).astype("bool").to_numpy()
    ]
    pieces: dict[str, list[_Piece]] = {}
    for unit, began, finished, share, starts, follows in zip(
        chosen[EQUIPMENT_ID_COLUMN],
        chosen["시작일"],
        chosen["종료일"],
        chosen["설비지분"],
        chosen[EXIT_STARTS_COLUMN],
        chosen[EXIT_FOLLOWS_COLUMN],
        strict=True,
    ):
        start = _as_date(began)
        end = _as_date(finished)
        if start is None or end is None:
            continue
        pieces.setdefault(str(unit).strip(), []).append(
            _Piece(start, end, float(share), bool(starts), bool(follows))
        )
    return {unit: tuple(found) for unit, found in pieces.items()}


def _unclaimed(
    low: date, high: date, claimed: Sequence[tuple[date, date]]
) -> list[tuple[date, date]]:
    """`[low, high]` 에서 이미 앞선 행이 매긴 날(`claimed`, 양 끝 포함)을 뺀 조각들(날짜 차례)."""
    parts = [(low, high)]
    for taken_low, taken_high in claimed:
        remaining: list[tuple[date, date]] = []
        for part_low, part_high in parts:
            if taken_high < part_low or part_high < taken_low:
                remaining.append((part_low, part_high))
                continue
            if part_low < taken_low:
                remaining.append((part_low, taken_low - _ONE_DAY))
            if taken_high < part_high:
                remaining.append((taken_high + _ONE_DAY, part_high))
        parts = remaining
    return sorted(parts)


def _clipped_losses(
    clipped: list[dict[str, object]],
    ratios: Mapping[str, float],
    process: str,
    days: int,
    months: Sequence[int],
) -> dict[str, dict[int, tuple[int, float]]]:
    """잘라 낸 반사실 가용 구간의 월별 기여 — 비가동 행 id 마다 `{월: (기여일수, 환산대수)}`."""
    if not clipped:
        return {}
    contributions = build_monthly_equipment_contributions(
        pd.DataFrame(clipped),
        pd.DataFrame(),
        _single_cutoff(process, days),
        months,
        conversion_ratios=ratios,
    )
    found: dict[str, dict[int, tuple[int, float]]] = {}
    for month, row_id, used, weighted in zip(
        contributions["생산계획년월"],
        contributions[EQUIPMENT_ID_COLUMN],
        contributions["기여일수"],
        contributions["환산대수"],
        strict=True,
    ):
        by_month = found.setdefault(str(row_id), {})
        before = by_month.get(int(month), (0, 0.0))
        by_month[int(month)] = (before[0] + int(used), before[1] + float(weighted))
    return found


def _window_month(windows: Sequence[WdWindow], day: date) -> int | None:
    for window in windows:
        if window.boundary_start < day <= window.boundary_end:
            return window.year_month
    return None


def _ordered_arrows(records: list[dict[str, object]]) -> pd.DataFrame:
    """가용을 깎은 호기가 앞, 호기마다 첫 손실 비가동의 시작일 → 호기 번호. 호기 안은 시작일."""
    first: dict[str, tuple[int, date]] = {}
    for record in records:
        key = str(record["설비키"])
        lossy = bool(record["가용 감소"])
        start = record["시작일"]
        assert isinstance(start, date)
        rank = (0 if lossy else 1, start)
        if key not in first or rank < first[key]:
            first[key] = rank
    records.sort(
        key=lambda record: (
            *first[str(record["설비키"])],
            *_unit_order(str(record["설비키"])),
            record["시작일"],
            str(record[EQUIPMENT_ID_COLUMN]),
        )
    )
    frame = pd.DataFrame(records, columns=list(ARROW_COLUMNS))
    for column in ("모듈 수", "덮는 날 수", "손실 기여일수"):
        frame[column] = frame[column].astype("int64")
    for column in ("첫 달", "손실 최대 월"):
        frame[column] = pd.to_numeric(frame[column]).astype("Int64")
    for column in ("꼬리 위치", "촉 위치", "손실 환산대수"):
        frame[column] = frame[column].astype("float64")
    for column in ("열린 구간", "이전부터", "가용 감소"):
        frame[column] = frame[column].astype("bool")
    return frame


# ---------------------------------------------------------------------- 작은 도움


def _empty(columns: Iterable[str]) -> pd.DataFrame:
    return pd.DataFrame({column: pd.Series(dtype="object") for column in columns})


def _tidy(value: float) -> float:
    """끝자리 부동소수 찌꺼기를 털고 -0.0 을 0.0 으로 둔다(표에 「-0」이 찍히지 않게)."""
    return round(value, _DECIMALS) + 0.0


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return [{str(key): value for key, value in row.items()} for row in frame.to_dict("records")]


def _unit_order(name: str) -> tuple[int, int, str]:
    """호기 번호 차례 — 이름 끝 숫자, 없으면 번호 있는 호기 뒤(`required_shortening` 과 같다)."""
    number = unit_number(name)
    return (0 if number is not None else 1, number or 0, name)


def _blank(value: object) -> bool:
    return (
        value is None
        or value is pd.NA
        or value is pd.NaT
        or (isinstance(value, float) and math.isnan(value))
    )


def _as_date(value: object) -> date | None:
    """표 칸의 날짜(`Timestamp`·`datetime`·`date`). 빈칸은 None."""
    if _blank(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _latest(days: Iterable[date | None]) -> date | None:
    found = [day for day in days if day is not None]
    return max(found) if found else None


def _distinct_text(values: Iterable[object]) -> str | None:
    """빈칸을 빼고 서로 다른 값을 처음 나온 차례로 「, 」로 잇는다. 하나도 없으면 None."""
    seen: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in seen:
            seen.append(text)
    return ", ".join(seen) if seen else None


def _text(value: object) -> str | None:
    if _blank(value):
        return None
    text = str(value).strip()
    return text or None


def _whole(value: object) -> int | None:
    return None if _blank(value) else int(str(value))
