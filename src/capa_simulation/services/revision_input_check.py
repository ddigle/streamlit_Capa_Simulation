# Purpose: 저장 리비전 하나의 전체 기간 계산에서 빠진 행을 묶음 · 까닭별 수로 센 입력 점검을 짓는다.

"""**계산에서 빠진 것을 리비전 하나에 대해 한자리에서 센다**(2026-11-11 입력 점검 보드 답 q1 ~ q7).

시나리오 관리 › 목록 관리 오른쪽 칸 「점검」 이 고른 리비전 하나를 시나리오 전체 기간으로 계산해 그
결과에서 빠진 행을 묶음으로 보인다. 이 모듈은 그 묶음을 짓는 **순수 셈**이다 — Streamlit · 세션 ·
DB 를 모른다. 계산(`simulation_cache.full_capacity_outcome`)과 멈춤 판정(`capacity_gate`)은 부르는
쪽이 하고, 여기는 그 결과 조각을 받는다(`simulation_cache` 를 import 하면 순환이다).

묶음은 저장 · 지정 검사(`required_exclusion_counts`)와 **같은 행**을 센다 — 경로 묶음 부제 · 계획 ·
경로 밖 부하의 수가 검사 경고의 네 수와 같다(`tests/test_revision_input_check.py`). 규칙대로 셈에서
뺀 것(PKG 의 Buffer 밖 행 · 쓰지 않는 경로 조합)은 검사가 세지 않는 행이라 맨 아래 한 묶음에 따로
모은다.

- **단계**는 넷이다 — 오류(계산 멈춤) · 확인 필요(빠진 행 네 묶음과 측정률 1.0 가정) · 알림(등록 때
  뺀 원천 행) · 규칙(규칙대로 뺀 것). 「계산」 칸의 「확인 n」 은 수가 0 이 아닌 확인 필요 묶음
  수다(`RevisionInputCheck.calculation_label`).
- **까닭**은 원본 값과 수로 든다 — 화면 표시명은 그릴 때 `reason_label` 로 바꾸고 CSV 는 원본 값
  그대로다(설계 규칙 UI-DAT-10).
- **멈춘 리비전**은 앞 단계가 멈춰 뒤 묶음을 세지 못한다 — 묶음 하나(「셀 수 없음」)로 접는다.
  등록 때 뺀 원천 행은 계산과 상관없이 센다. HOME Density 환산만 멈춘 리비전은 「멈춤」 줄은 두고
  뒤 묶음도 센다 — 대당 Capa · 소요대수는 끝났으므로 셀 수 있다(2026-11-11 입력 점검 검토 보드
  F1 (나), `DENSITY_STOP_KEEPS_COUNTS`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal, Protocol

import pandas as pd

from capa_simulation.reference_grid_keys import DATASETS
from capa_simulation.services.core_data_derivation import plan_row_mask
from capa_simulation.services.load_calculator import (
    LOAD_EXCLUSION_COLUMNS,
    PLAN_QUANTITY_BLANK_REASON,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.required_equipment import (
    PKG_UNCOUNTED_REASON,
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
    REQUIRED_LOAD_EXCLUSIONS_ATTR,
    UNROUTED_LOADS_ATTR,
    UNROUTED_REASON_COLUMN,
    UNROUTED_UNUSED_REASON,
    counted_unrouted_loads,
)
from capa_simulation.services.unit_capacity import (
    CAPACITY_EXCLUSIONS_ATTR,
    RUN_RATE_EXCLUSION_REASON,
    ReferenceJoinProblem,
    capacity_assumptions,
)

InputCheckLevel = Literal["error", "check", "info", "rule", "muted"]
StopKind = Literal["capacity", "density", "blocked"]

# 단계 표지 글. 규칙 · 셀 수 없음 묶음은 표지가 없다(시안 `mock_ga` · `mock_ga_stop`).
LEVEL_LABELS: Final[Mapping[str, str]] = {"error": "오류", "check": "확인 필요", "info": "알림"}

# 묶음 id — 「그 화면으로」 도착지 · 펼침 상태가 이 이름으로 갈린다.
GROUP_STOP: Final = "stop"
GROUP_CAPACITY: Final = "capacity"
GROUP_ROUTES: Final = "routes"
GROUP_PLANS: Final = "plans"
GROUP_UNROUTED: Final = "unrouted"
GROUP_ASSUMED: Final = "assumed"
GROUP_SOURCE: Final = "source"
GROUP_RULES: Final = "rules"
GROUP_UNCOUNTED: Final = "uncounted"

# 묶음 이름 · 부제 · 수 자리 글 — 시안 글자 그대로다.
STOP_TITLE: Final = "계산 멈춤"
CAPACITY_TITLE: Final = "대당 Capa 에서 뺀 기준"
ROUTES_TITLE: Final = "대당 Capa 가 없어 소요대수에서 뺀 경로"
PLANS_TITLE: Final = "부하량에서 빠진 계획"
UNROUTED_TITLE: Final = "경로에 닿지 않은 계획 부하"
ASSUMED_TITLE: Final = "측정률 1.0 가정"
SOURCE_TITLE: Final = "등록 때 뺀 원천 행"
RULES_TITLE: Final = "규칙대로 셈에서 뺀 것"
UNCOUNTED_TITLE: Final = "대당 Capa 에서 뺀 기준 · 소요대수 · 계획 · 가정"
UNCOUNTED_SUBTITLE: Final = "앞 단계가 멈춰 그 뒤 묶음은 세지 못함"
PKG_RULE_TITLE: Final = "PKG Buffer 밖"
UNUSED_RULE_TITLE: Final = "쓰지 않는 경로 조합"
NONE_NOTE: Final = "없음"
UNCOUNTABLE_NOTE: Final = "셀 수 없음"
NO_SOURCE_NOTE: Final = "—"
# 멈춘 단계 말 — 단계를 아는 멈춤만 제목 뒤에 붙인다. 기준정보 연결 오류(`ReferenceJoinProblem`)는
# 대당 Capa, Density 검사(`capacity_gate.density_error`)는 HOME Density 환산이다. 그 밖의 계산
# 오류는 대당 Capa · 소요대수 어느 쪽인지 결과가 말하지 않아 맨 「계산 멈춤」 이다.
JOIN_STOP_STAGE: Final = "대당 Capa"
DENSITY_STOP_STAGE: Final = "Density 환산"

# 「계산」 칸 글.
CALCULATED_LABEL: Final = "됨"
STOPPED_LABEL: Final = "멈춤"

# HOME Density 환산만 멈춘 리비전(대당 Capa · 소요대수는 끝남)에서 뒤 묶음을 셀지. 참이면 「멈춤」
# 줄 뒤에 다른 묶음을 그대로 센다(2026-11-11 검토 보드 F1 (나)). 거짓이면 Capa 계산이 멈춘
# 리비전처럼 「셀 수 없음」 한 묶음으로 접는다(시안 `mock_ga_stop` 의 꼴).
DENSITY_STOP_KEEPS_COUNTS: Final = True

# 까닭 원본 값 → 화면 표시명. 없는 값은 원본 그대로 보인다. CSV 는 늘 원본 값이다. 부하량에서 빠진
# 계획의 까닭은 표 이름만이면 그 표에 계획 키 행이 없는 것, 「… 값 없음」 이면 행은 있고 값이 빈
# 것이다(`load_calculator`).
REASON_LABELS: Final[Mapping[str, str]] = {
    RUN_RATE_EXCLUSION_REASON: f"{DATASETS['RQ_RUN_RATE']}(CAPA_RUN_RATE) 0 이하",
    PLAN_QUANTITY_BLANK_REASON: "생산수량 빈 값",
    "RQ_YLD": "RQ_YLD 행 없음",
    "RQ_CHIP_QTY": "RQ_CHIP_QTY 행 없음",
}

# 묶음 줄을 펼칠 때 보이는 앞 칸(원본 칸 이름). 「넓게 보기」 · CSV 는 모든 칸이다.
CAPACITY_PREVIEW: Final = ("생산계획년월", "공정", "양산구분", "제품정보", "제외사유")
ROUTES_PREVIEW: Final = ("생산계획년월", "공정", "제품정보", "부하량", "제외사유")
PLANS_PREVIEW: Final = tuple(LOAD_EXCLUSION_COLUMNS)
UNROUTED_PREVIEW: Final = ("생산계획년월", "제품정보", "소요기준", "부하량", UNROUTED_REASON_COLUMN)
SOURCE_PREVIEW: Final = ("생산계획년월", "공정", "제품정보", "계획기초정보여부", "CS")

# 원천의 계획 행 표시 칸 — 등록 때 뺀 행을 계획 · 경로로 가른다(`plan_row_mask`).
SOURCE_PLAN_FLAG_COLUMN: Final = "계획기초정보여부"
_MONTH_COLUMN = "생산계획년월"
_CAPACITY_REASON_COLUMN = "제외사유"
_PLAN_REASON_COLUMN = "누락 기준정보"
_ROUTE_REASON_COLUMN = "제외사유"
# 측정률 가정 부제에 적는 달 수. 넘으면 「외 N개월」 로 줄인다 — 묶음 부제는 한 줄이다.
ASSUMED_MONTH_LIMIT: Final = 3


class CapacityResult(Protocol):
    """전체 기간 계산 결과의 꼴(`simulation_cache.CapacityOutcome`) — 순환 import 없이 받는다."""

    @property
    def unit_capacity(self) -> pd.DataFrame | None: ...

    @property
    def required_equipment(self) -> pd.DataFrame | None: ...

    @property
    def error(self) -> str | None: ...

    @property
    def problem(self) -> ReferenceJoinProblem | None: ...


@dataclass(frozen=True, eq=False)
class InputCheckTable:
    """묶음 하나의 행 표 — 원본 칸 · 원본 값(CSV 그대로). `preview` 는 묶음 줄에 펼칠 앞 칸이다."""

    title: str
    frame: pd.DataFrame
    preview: tuple[str, ...]
    reason_column: str | None = None

    @property
    def preview_columns(self) -> list[str]:
        """앞 칸 가운데 이 표에 있는 칸 — 빈 결과는 칸 없는 프레임일 수 있다."""
        return [column for column in self.preview if column in self.frame.columns]


@dataclass(frozen=True, eq=False)
class InputCheckGroup:
    """묶음 한 줄. `count` 가 None 이면 수 자리에 `count_note`(셀 수 없음 · 원천 없음 「—」)가 선다.

    `reasons` 는 (원본 까닭 값, 수) — 많은 차례. 측정률 가정은 (표 이름, 경로 수)이고 그 달은
    `months` 다. `tables` 는 「행 보기」 · CSV 의 표(규칙 묶음은 둘)다.
    """

    key: str
    level: InputCheckLevel
    title: str
    count: int | None
    subtitle: str = ""
    count_note: str = ""
    reasons: tuple[tuple[str, int], ...] = ()
    months: tuple[tuple[str, tuple[int, ...]], ...] = ()
    tables: tuple[InputCheckTable, ...] = ()

    @property
    def count_text(self) -> str:
        """수 자리 글 — 0 이면 「없음」, 셀 수 없으면 `count_note`."""
        if self.count is None:
            return self.count_note
        return f"{self.count:,}" if self.count else NONE_NOTE

    @property
    def flagged(self) -> bool:
        """「확인 n」 에 드는 묶음인가 — 확인 필요 단계이고 수가 0 이 아니다."""
        return self.level == "check" and bool(self.count)


@dataclass(frozen=True)
class InputCheckStop:
    """멈춤의 재료 — 갈래 · 계산 오류 원문(화면 글은 `page_bootstrap.calculation_stop_notice`) ·
    기준정보 연결 오류의 꼴과 수(경로 n — 없으면 None)."""

    kind: StopKind
    error: str
    problem: ReferenceJoinProblem | None = None


@dataclass(frozen=True, eq=False)
class RevisionInputCheck:
    """리비전 하나의 입력 점검 — 묶음 차례대로, 기간(계산이 본 달 범위 — `calculation_period`),
    멈춤."""

    groups: tuple[InputCheckGroup, ...]
    period: tuple[int, int] | None = None
    stop: InputCheckStop | None = None

    @property
    def stopped(self) -> bool:
        return self.stop is not None

    @property
    def check_count(self) -> int:
        """「확인 n」 의 n — 수가 0 이 아닌 확인 필요 묶음 수(측정률 가정 포함, 등록 · 규칙
        묶음 제외)."""
        return sum(group.flagged for group in self.groups)

    @property
    def calculation_label(self) -> str:
        """「계산」 칸 글 — 「멈춤」 · 「됨」 · 「됨 · 확인 n」."""
        if self.stopped:
            return STOPPED_LABEL
        count = self.check_count
        return f"{CALCULATED_LABEL} · 확인 {count:,}" if count else CALCULATED_LABEL

    @property
    def period_label(self) -> str:
        """「YY.MM–YY.MM」 — 계획이 없으면 빈 글."""
        if self.period is None:
            return ""
        start, end = self.period
        return f"{month_label(start)}–{month_label(end)}"

    def group(self, key: str) -> InputCheckGroup | None:
        return next((group for group in self.groups if group.key == key), None)


def reason_label(reason: str) -> str:
    """까닭 원본 값의 화면 표시명(`REASON_LABELS`, 없으면 원본 그대로)."""
    return REASON_LABELS.get(reason, reason)


def calculation_period(
    tables: Mapping[str, pd.DataFrame], names: Sequence[str]
) -> tuple[int, int] | None:
    """계산이 본 달 범위(첫 달, 끝 달) — `names` 표(계획 `RQ_PKG_PLAN` 과 달 축이 있는 계산 입력
    표)의 달을 합친 범위다. 묶음은 기준정보 표 전체 달의 행을 세므로 기준정보 달이 계획보다 넓으면
    그 달도 범위에 든다(2026-11-11 입력 점검 검토 보드 F5 (가)). 달 칸이 없는 표 · 없는 표는
    건너뛰고, 어느 표에도 달이 없으면 None. 등록 때 뺀 원천 행은 계산 밖이라 넣지 않는다."""
    found: list[pd.Series] = []
    for name in names:
        frame = tables.get(name)
        if frame is None or _MONTH_COLUMN not in frame.columns:
            continue
        found.append(pd.to_numeric(frame[_MONTH_COLUMN], errors="coerce").dropna())
    months = pd.concat(found) if found else pd.Series(dtype="float64")
    if months.empty:
        return None
    return int(months.min()), int(months.max())


def _frame(value: object) -> pd.DataFrame:
    """`attrs` 에서 꺼낸 값 — 프레임이 아니면 빈 프레임이다."""
    return value if isinstance(value, pd.DataFrame) else pd.DataFrame()


def _reason_counts(frame: pd.DataFrame, column: str) -> tuple[tuple[str, int], ...]:
    """까닭별 수 — 많은 차례, 같은 수는 까닭 글 차례."""
    if frame.empty or column not in frame.columns:
        return ()
    counts = frame[column].astype("string").fillna("").value_counts()
    return tuple(sorted(((str(k), int(v)) for k, v in counts.items()), key=lambda i: (-i[1], i[0])))


def _reason_subtitle(reasons: Sequence[tuple[str, int]]) -> str:
    return " · ".join(f"{reason_label(reason)} {count:,}" for reason, count in reasons)


def _month_list(months: Sequence[int]) -> str:
    shown = ", ".join(month_label(month) for month in months[:ASSUMED_MONTH_LIMIT])
    rest = len(months) - ASSUMED_MONTH_LIMIT
    return f"{shown} 외 {rest}개월" if rest > 0 else shown


def _loaded(frame: pd.DataFrame) -> int:
    """부하가 붙은 행 수 — 검사(`count_required_exclusions`)와 같은 식."""
    if frame.empty or "부하량" not in frame.columns:
        return 0
    return int(pd.to_numeric(frame["부하량"], errors="coerce").gt(0).sum())


def _source_group(blank_cs: pd.DataFrame | None) -> InputCheckGroup:
    """등록 때 뺀 원천 행 — 원천이 없는 시나리오(복제 · 머지 · Shift)는 None 이라 「—」."""
    if blank_cs is None:
        return InputCheckGroup(GROUP_SOURCE, "info", SOURCE_TITLE, None, count_note=NO_SOURCE_NOTE)
    count = len(blank_cs)
    subtitle = ""
    if count:
        plans = int(plan_row_mask(blank_cs).sum()) if SOURCE_PLAN_FLAG_COLUMN in blank_cs else 0
        subtitle = f"CS 빈 칸 — 계획 {plans:,} · 경로 {count - plans:,}"
    return InputCheckGroup(
        GROUP_SOURCE,
        "info",
        SOURCE_TITLE,
        count,
        subtitle,
        tables=(InputCheckTable(SOURCE_TITLE, blank_cs, SOURCE_PREVIEW),),
    )


def _stop_group(stop: InputCheckStop | None) -> InputCheckGroup:
    if stop is None:
        return InputCheckGroup(GROUP_STOP, "error", STOP_TITLE, 0)
    stage = (
        JOIN_STOP_STAGE
        if stop.problem is not None
        else DENSITY_STOP_STAGE
        if stop.kind == "density"
        else ""
    )
    title = f"{STOP_TITLE} — {stage}" if stage else STOP_TITLE
    # 부제는 원문이다 — 화면이 `calculation_stop_notice` 로 알아보면 그 짧은 글로 바꾼다.
    return InputCheckGroup(GROUP_STOP, "error", title, None, stop.error)


def _uncounted_group() -> InputCheckGroup:
    return InputCheckGroup(
        GROUP_UNCOUNTED,
        "muted",
        UNCOUNTED_TITLE,
        None,
        UNCOUNTED_SUBTITLE,
        count_note=UNCOUNTABLE_NOTE,
    )


def _counted_groups(
    unit_capacity: pd.DataFrame, required_equipment: pd.DataFrame
) -> tuple[list[InputCheckGroup], InputCheckGroup]:
    """계산이 끝난 결과의 묶음 — 확인 필요 다섯과 규칙 묶음."""
    capacity = _frame(unit_capacity.attrs.get(CAPACITY_EXCLUSIONS_ATTR))
    capacity_reasons = _reason_counts(capacity, _CAPACITY_REASON_COLUMN)

    routes_all = _frame(required_equipment.attrs.get(REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR))
    if _ROUTE_REASON_COLUMN in routes_all.columns:
        pkg = routes_all[_ROUTE_REASON_COLUMN].eq(PKG_UNCOUNTED_REASON).fillna(False)
    else:
        pkg = pd.Series(False, index=routes_all.index, dtype="bool")
    routes = routes_all.loc[~pkg]
    pkg_rows = routes_all.loc[pkg]

    plans = _frame(required_equipment.attrs.get(REQUIRED_LOAD_EXCLUSIONS_ATTR))
    plan_reasons = _reason_counts(plans, _PLAN_REASON_COLUMN)

    unrouted_all = _frame(required_equipment.attrs.get(UNROUTED_LOADS_ATTR))
    unrouted = counted_unrouted_loads(unrouted_all)
    if UNROUTED_REASON_COLUMN in unrouted_all.columns:
        unused = unrouted_all.loc[unrouted_all[UNROUTED_REASON_COLUMN].eq(UNROUTED_UNUSED_REASON)]
    else:
        unused = unrouted_all.iloc[0:0]
    unrouted_reasons = _reason_counts(unrouted, UNROUTED_REASON_COLUMN)

    assumed = capacity_assumptions(unit_capacity)
    assumed_counts = tuple((table, int(n)) for table, n in assumed.counts.items() if n)
    assumed_months = tuple(
        (table, tuple(int(month) for month in assumed.months.get(table, ())))
        for table, _ in assumed_counts
    )
    assumed_subtitle = " · ".join(
        f"{DATASETS.get(table, table)} {count:,}" + (f"({_month_list(months)})" if months else "")
        for (table, count), (_, months) in zip(assumed_counts, assumed_months, strict=True)
    )

    checks = [
        InputCheckGroup(
            GROUP_CAPACITY,
            "check",
            CAPACITY_TITLE,
            len(capacity),
            _reason_subtitle(capacity_reasons),
            reasons=capacity_reasons,
            tables=(
                InputCheckTable(
                    CAPACITY_TITLE, capacity, CAPACITY_PREVIEW, _CAPACITY_REASON_COLUMN
                ),
            ),
        ),
        InputCheckGroup(
            GROUP_ROUTES,
            "check",
            ROUTES_TITLE,
            len(routes),
            f"그 가운데 부하가 붙은 경로 {_loaded(routes):,}" if len(routes) else "",
            reasons=_reason_counts(routes, _ROUTE_REASON_COLUMN),
            tables=(InputCheckTable(ROUTES_TITLE, routes, ROUTES_PREVIEW, _ROUTE_REASON_COLUMN),),
        ),
        InputCheckGroup(
            GROUP_PLANS,
            "check",
            PLANS_TITLE,
            len(plans),
            _reason_subtitle(plan_reasons),
            reasons=plan_reasons,
            tables=(InputCheckTable(PLANS_TITLE, plans, PLANS_PREVIEW, _PLAN_REASON_COLUMN),),
        ),
        InputCheckGroup(
            GROUP_UNROUTED,
            "check",
            UNROUTED_TITLE,
            len(unrouted),
            _reason_subtitle(unrouted_reasons),
            reasons=unrouted_reasons,
            tables=(
                InputCheckTable(UNROUTED_TITLE, unrouted, UNROUTED_PREVIEW, UNROUTED_REASON_COLUMN),
            ),
        ),
        InputCheckGroup(
            GROUP_ASSUMED,
            "check",
            ASSUMED_TITLE,
            sum(count for _, count in assumed_counts),
            assumed_subtitle,
            reasons=assumed_counts,
            months=assumed_months,
        ),
    ]
    rule_parts = ((PKG_RULE_TITLE, len(pkg_rows)), (UNUSED_RULE_TITLE, len(unused)))
    rules = InputCheckGroup(
        GROUP_RULES,
        "rule",
        RULES_TITLE,
        len(pkg_rows) + len(unused),
        " · ".join(f"{title} {count:,}" for title, count in rule_parts if count),
        reasons=tuple(
            (reason, count)
            for reason, count in (
                (PKG_UNCOUNTED_REASON, len(pkg_rows)),
                (UNROUTED_UNUSED_REASON, len(unused)),
            )
            if count
        ),
        tables=(
            InputCheckTable(PKG_RULE_TITLE, pkg_rows, ROUTES_PREVIEW, _ROUTE_REASON_COLUMN),
            InputCheckTable(UNUSED_RULE_TITLE, unused, UNROUTED_PREVIEW, UNROUTED_REASON_COLUMN),
        ),
    )
    return checks, rules


def build_input_check(
    outcome: CapacityResult,
    density_error: str | None,
    blank_cs: pd.DataFrame | None,
    *,
    period: tuple[int, int] | None = None,
) -> RevisionInputCheck:
    """전체 기간 계산 결과 · Density 검사 오류 · 등록 때 뺀 원천 행(원천 없으면 None)으로 점검을
    짓는다.

    `density_error` 는 Capa 계산이 통과했을 때만 본 값이다(`capacity_gate` 의 멈춤 판정과 같은
    차례).
    `period` 는 그 리비전 계산이 본 달 범위(`calculation_period`)다.
    """
    source = _source_group(blank_cs)
    if outcome.error is not None:
        calculation_stop = InputCheckStop("capacity", outcome.error, outcome.problem)
        return RevisionInputCheck(
            (_stop_group(calculation_stop), _uncounted_group(), source),
            period=period,
            stop=calculation_stop,
        )
    assert outcome.unit_capacity is not None and outcome.required_equipment is not None
    stop = InputCheckStop("density", density_error) if density_error is not None else None
    if stop is not None and not DENSITY_STOP_KEEPS_COUNTS:
        return RevisionInputCheck(
            (_stop_group(stop), _uncounted_group(), source), period=period, stop=stop
        )
    checks, rules = _counted_groups(outcome.unit_capacity, outcome.required_equipment)
    return RevisionInputCheck((_stop_group(stop), *checks, source, rules), period=period, stop=stop)


def blocked_input_check(
    reason: str, blank_cs: pd.DataFrame | None, *, period: tuple[int, int] | None = None
) -> RevisionInputCheck:
    """경로 키가 없는 옛 리비전(`revision_compatibility.revision_block_reason`) — 계산을 부르지 않고
    그 글로 멈춘다."""
    stop = InputCheckStop("blocked", reason)
    return RevisionInputCheck(
        (_stop_group(stop), _uncounted_group(), _source_group(blank_cs)), period=period, stop=stop
    )
