# Purpose: 공정 × 생산월 입력 비가동 대수의 모델·칸 검증·범위 병합·가용 차감 규칙을 둔다.

"""입력 비가동 대수 — 호기에 잇지 않고 공정 × 달로 넣는 비가동(2026-10-27 사용자 결정).

저장은 설비 DB 의 `equipment_ops.manual_downtime_profile`·`manual_downtime`·`manual_downtime_save`
(설비 `0032`)이고 SQL 은 `persistence/manual_downtime_store.py` 가 갖는다. 이 모듈은 Streamlit·DB 를
모르는 규칙만 둔다.

- **공용 프로필 하나**다 — 모든 설비 시나리오가 같이 쓴다(결정 2). 시나리오별로 두는 것은
  다음 몫이다.
- **값은 환산 대수**이고 소수를 받는다(0 이상). 빈칸은 0 이고 0 칸은 저장하지 않는다(행 없음 = 0).
  공정은 원본 공정명(설비 마스터 `공정소분류` = 시나리오 `공정`), 달은 `YYYYMM` 생산월(Cut-off W/D
  월 — 공정 Capa 상세와 같은 달)이다. 표시명(Proc Rename)은 닿지 않는다.
- **빼는 곳**은 실행 쪽 「설비 일정 기준 가용대수」(단축 전 월별 환산 가용)다(결정 1 — 「실행
  가용대수에서 뺀다」). 그 가용을 보이는 모든 자리 — 필요 단축 일정 계획·공정 Capa 상세 ②·제약
  시뮬레이션·Space 필요 단축·가용설비 현황 Static 대비 일정(그림·시트·확보율 교차검증) — 가 같은
  칸을 같은 규칙으로 뺀다. 호기별 비가동과 **별도 손실**이라 그 위에 더 뺀다(결정 3). 그 달 가용보다
  크면 가용은 0 에서 멈추고 넘친 자리를 알린다(`apply_manual_downtime` — `초과`,
  `clamp_manual_units`). HOME·Static 의 기준정보 가용과 주차별 가용은 바꾸지 않는다.
- **저장은 보이는 범위만 갈아 쓴다**(`merge_visible_cells`) — 화면 표는 조회기간의 달·지금 공정만
  보이므로, 그 밖의 저장 칸은 그대로 남긴다(보이지 않는 값을 말없이 지우지 않는다).
- 계산 캐시 키는 프로필 version 이 아니라 **계산할 달로 좁힌 칸 자체**(`manual_downtime_key`)다 —
  계획 키가 이 칸을 싣고 계산은 키에서 칸을 다시 세운다(목표 `MonthlyTarget` 과 같은 길). 그래서
  조회기간 밖 칸을 고친 저장은 계산 캐시를 가르지 않고, 키와 다른 칸이 계산에 들어올 길이 없다.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import pandas as pd

__all__ = [
    "MANUAL_DOWNTIME_BAND",
    "MANUAL_DOWNTIME_EFFECT_COLUMNS",
    "MANUAL_DOWNTIME_MAX_UNITS",
    "ManualDowntime",
    "ManualDowntimeKey",
    "ManualDowntimeSave",
    "ManualRow",
    "apply_manual_downtime",
    "changed_cell_count",
    "clamp_manual_units",
    "empty_manual_downtime_effect",
    "manual_cell_value",
    "manual_downtime_digest",
    "manual_downtime_key",
    "manual_effect_band",
    "manual_removed_text",
    "manual_rows_for_process",
    "manual_units_text",
    "merge_visible_cells",
    "overdrawn_rows",
    "period_months",
    "prepare_manual_downtime",
]

# 출처 띠에 붙이는 말(결정 5) — 계산 키에 0 이 아닌 칸이 있을 때만 붙인다.
MANUAL_DOWNTIME_BAND: Final = "입력 비가동 반영"
# 한 칸의 상한(환산 대수). 오타(소수점 빠짐 — 1.5 를 15000)를 막는 문턱이다 — 공정 하나의 호기가
# 이만큼 되는 일은 없다.
MANUAL_DOWNTIME_MAX_UNITS: Final = 9999.0
# 부동소수 끝자리를 털어 내는 자리. `required_shortening` 과 같은 9자리다.
_DECIMALS: Final = 9
# 저장 값의 자리(입력 칸 소수 둘째 자리보다 넉넉히).
_STORED_DECIMALS: Final = 6

ManualRow = tuple[str, int, float]
"""(원본 공정명, 생산월 `YYYYMM`, 환산 대수 > 0)."""

ManualDowntimeKey = tuple[ManualRow, ...]
"""계산 캐시 키에 싣는 칸 — 계산할 달로 좁혀 (공정, 달) 차례로 둔 0 아닌 칸."""

MANUAL_DOWNTIME_EFFECT_COLUMNS: Final = ("공정", "생산계획년월", "입력대수", "반영대수", "초과")
"""공정·달마다 입력과 실제로 가용에서 뺀 몫(`apply_manual_downtime`).

`반영대수 = min(입력대수, 그 달 가용)` 이고 `초과` 는 입력이 그 달 가용보다 컸는가(가용은 0 에서
멈췄다)다."""


@dataclass(frozen=True)
class ManualDowntime:
    """입력 비가동 대수 한 벌. `version` 0 은 한 번도 저장하지 않은 것(모든 칸 0)이다.

    `rows` 는 0 아닌 칸만의 (공정, 달, 대수)이고 (공정, 달) 차례다 — 캐시에 실리도록 기본형 튜플로
    둔다(AGENTS 5장 21). 저장자·메모는 마지막 저장의 것이다.
    """

    rows: tuple[ManualRow, ...] = ()
    version: int = 0
    saved_by: str = ""
    note: str = ""
    updated_at: datetime | None = None

    @property
    def source(self) -> str:
        """버전 캡션(`profile_version_caption`)의 출처 — 저장자 · 메모(있는 것만)."""
        return " · ".join(part for part in (self.saved_by, self.note) if part)

    @property
    def cells(self) -> dict[tuple[str, int], float]:
        """(공정, 달) → 대수. 없는 칸은 0 이다."""
        return {(process, month): units for process, month, units in self.rows}

    @property
    def processes(self) -> tuple[str, ...]:
        """값이 있는 공정(이름 차례)."""
        return tuple(sorted({process for process, _, _ in self.rows}))


@dataclass(frozen=True)
class ManualDowntimeSave:
    """저장 이력 한 줄(`manual_downtime_save`)."""

    version: int
    saved_at: datetime
    saved_by: str
    note: str
    changed_cells: int
    filled_cells: int
    total_units: float


def manual_cell_value(value: object, *, where: str = "") -> float:
    """편집표 칸 하나를 대수로 읽는다. 빈칸(None·NaN·빈 글자)은 0 이다.

    숫자가 아니거나 음수·무한·상한(`MANUAL_DOWNTIME_MAX_UNITS`) 초과면 `ValueError` — `where` 는
    오류 글 앞에 붙일 자리(「Wafer Mount 26.07」)다. 글자 숫자(「1.5」)는 받는다(붙여넣기).
    """
    prefix = f"{where}: " if where else ""
    if value is None or value is pd.NA or isinstance(value, bool):
        if isinstance(value, bool):
            raise ValueError(f"{prefix}비가동 대수는 숫자여야 합니다: {value!r}")
        return 0.0
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return 0.0
        try:
            number = float(text)
        except ValueError:
            raise ValueError(f"{prefix}비가동 대수는 숫자여야 합니다: {value!r}") from None
    elif isinstance(value, int | float):
        number = float(value)
    else:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError(f"{prefix}비가동 대수는 숫자여야 합니다: {value!r}") from None
    if math.isnan(number):
        return 0.0
    if math.isinf(number) or number < 0:
        raise ValueError(f"{prefix}비가동 대수는 0 이상이어야 합니다: {value!r}")
    if number > MANUAL_DOWNTIME_MAX_UNITS:
        raise ValueError(
            f"{prefix}비가동 대수가 너무 큽니다(상한 {MANUAL_DOWNTIME_MAX_UNITS:g}): {value!r}"
        )
    return round(number, _STORED_DECIMALS)


def _process(value: object) -> str:
    """원본 공정명 — 앞뒤 공백만 뗀다(설비 쪽 공정 맞대기와 같은 규칙). 빈 값은 빈 글자."""
    if value is None or value is pd.NA or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def _month(value: object) -> int:
    try:
        number = int(str(value).strip())
    except ValueError:
        raise ValueError(f"달은 YYYYMM 정수여야 합니다: {value!r}") from None
    if isinstance(value, bool) or not 100_001 <= number <= 999_912 or not 1 <= number % 100 <= 12:
        raise ValueError(f"달은 YYYYMM 정수여야 합니다: {value!r}")
    return number


def prepare_manual_downtime(cells: Mapping[tuple[object, object], object]) -> tuple[ManualRow, ...]:
    """저장 입구 — (공정, 달) → 값을 검증해 0 아닌 칸만 (공정, 달) 차례로 돌려준다.

    공정은 앞뒤 공백을 떼고(빈 공정은 `ValueError`), 달은 `YYYYMM`(1~12월), 값은 `manual_cell_value`
    규칙이다. 같은 (공정, 달)이 두 번 오면 `ValueError` 다.
    """
    seen: dict[tuple[str, int], float] = {}
    for (raw_process, raw_month), raw_value in cells.items():
        process = _process(raw_process)
        if not process:
            raise ValueError("공정이 빈 비가동 칸이 있습니다.")
        month = _month(raw_month)
        key = (process, month)
        if key in seen:
            raise ValueError(f"같은 공정·달의 비가동 칸이 두 번 있습니다: {process} {month}")
        seen[key] = manual_cell_value(raw_value, where=f"{process} {month}")
    return tuple(
        (process, month, units)
        for (process, month), units in sorted(seen.items())
        if round(units, _DECIMALS) > 0
    )


def merge_visible_cells(
    current: Iterable[ManualRow],
    edited: Mapping[tuple[str, int], object],
    *,
    processes: Collection[str],
    months: Collection[int],
) -> tuple[ManualRow, ...]:
    """화면이 보인 범위(`processes` × `months`)만 `edited` 로 갈아 쓰고 그 밖의 저장 칸은 남긴다.

    `edited` 는 보인 범위의 칸(빈칸 포함)이다 — 보인 범위에서 `edited` 에 없는 칸은 비운 것(0)으로
    본다. 결과는 `prepare_manual_downtime` 을 지난 값이다.
    """
    visible_processes = {_process(process) for process in processes}
    visible_months = {int(month) for month in months}
    merged: dict[tuple[object, object], object] = {
        (process, month): units
        for process, month, units in current
        if not (process in visible_processes and int(month) in visible_months)
    }
    for (process, month), value in edited.items():
        name = _process(process)
        if name in visible_processes and int(month) in visible_months:
            merged[(name, int(month))] = value
    return prepare_manual_downtime(merged)


def changed_cell_count(before: Iterable[ManualRow], after: Iterable[ManualRow]) -> int:
    """두 벌에서 값이 다른 (공정, 달) 수 — 새로 채운 칸·비운 칸·값을 바꾼 칸."""
    left = {(process, month): units for process, month, units in before}
    right = {(process, month): units for process, month, units in after}
    return sum(
        1
        for key in left.keys() | right.keys()
        if round(left.get(key, 0.0) - right.get(key, 0.0), _DECIMALS) != 0
    )


def manual_downtime_key(rows: Iterable[ManualRow], months: Iterable[int]) -> ManualDowntimeKey:
    """계산 캐시 키에 실을 칸 — `months` 안의 0 아닌 칸을 (공정, 달) 차례로.

    계획·설비 일정 계산은 이 값만 본다(키에서 다시 세운다). 달 밖 칸을 빼 두어 조회기간 밖 저장이
    계산 캐시를 가르지 않게 한다.
    """
    wanted = {int(month) for month in months}
    return tuple(
        sorted(
            (str(process), int(month), float(units))
            for process, month, units in rows
            if int(month) in wanted and round(float(units), _DECIMALS) > 0
        )
    )


def period_months(start_month: int, end_month: int) -> tuple[int, ...]:
    """`YYYYMM` 두 끝을 담은 달들(차례대로). 시작이 끝보다 늦으면 빈 튜플."""
    months: list[int] = []
    year, month = divmod(int(start_month), 100)
    end_year, end = divmod(int(end_month), 100)
    while (year, month) <= (end_year, end):
        months.append(year * 100 + month)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return tuple(months)


def manual_rows_for_process(
    rows: Iterable[ManualRow], process: str
) -> tuple[tuple[int, float], ...]:
    """공정 하나의 (달, 대수) — 달 차례. 공정 이름은 앞뒤 공백만 떼고 견준다."""
    name = str(process).strip()
    return tuple(
        sorted((int(month), float(units)) for found, month, units in rows if found == name)
    )


def clamp_manual_units(units: float, available: float) -> tuple[float, bool]:
    """입력 하나를 그 달 가용에 건다 — (가용에서 뺄 몫, 넘쳤는가). 뺄 몫은 `min(입력, 가용)` 이라
    가용은 0 에서 멈춘다. 계획(`apply_manual_downtime`)과 공정 Capa 상세 ② 전월 대비가 같은 함수를
    쓴다 — 둘의 가용대수가 같은 값이어야 한다."""
    applied = round(min(float(units), max(float(available), 0.0)), _DECIMALS)
    return applied, round(float(units) - float(available), _DECIMALS) > 0


def empty_manual_downtime_effect() -> pd.DataFrame:
    """행이 없는 효과 프레임(`MANUAL_DOWNTIME_EFFECT_COLUMNS`)."""
    return pd.DataFrame(
        {
            "공정": pd.Series(dtype="object"),
            "생산계획년월": pd.Series(dtype="int64"),
            "입력대수": pd.Series(dtype="float64"),
            "반영대수": pd.Series(dtype="float64"),
            "초과": pd.Series(dtype="bool"),
        }
    )


def apply_manual_downtime(
    available: pd.DataFrame, rows: Sequence[ManualRow]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """가용(`생산계획년월·공정·가용대수`)에서 입력 비가동을 뺀다 — (뺀 가용, 효과).

    - 빼는 몫은 `min(입력, 그 달 가용)` 이라 가용은 0 에서 멈춘다(결정 3). 입력이 가용보다 크면
      효과의 `초과` 가 참이다.
    - 가용 행이 없는 (공정, 달)은 가용 0 으로 본다 — 뺄 것이 없어 반영 0 이고 입력이 0 보다 크면
      초과다. 가용 프레임에 행을 새로 만들지 않는다(그 공정·달은 계산이 맞대지 않는 자리다).
    - 칸이 없으면 `available` 을 그대로(같은 객체) 돌려준다 — 입력이 없는 계산은 전과 같은 숫자다.
    """
    if not rows:
        return available, empty_manual_downtime_effect()
    adjusted = available.copy()
    months = pd.to_numeric(adjusted["생산계획년월"], errors="coerce")
    processes = adjusted["공정"].astype("string").str.strip()
    values: list[float] = [
        float(value)
        for value in pd.to_numeric(adjusted["가용대수"], errors="coerce").fillna(0.0).tolist()
    ]
    effect: list[dict[str, object]] = []
    for process, month, units in rows:
        mask = (months.eq(int(month)) & processes.eq(str(process))).fillna(False).to_numpy()
        positions = [position for position, hit in enumerate(mask) if hit]
        before = sum(values[position] for position in positions)
        applied, overdrawn = clamp_manual_units(units, before)
        # 같은 (달, 공정)이 여러 줄이면 앞 줄부터 뺀다 — 합이 같고 음수가 나지 않는다.
        remaining = applied
        for position in positions:
            if remaining <= 0:
                break
            take = min(remaining, max(values[position], 0.0))
            values[position] = round(values[position] - take, _DECIMALS)
            remaining -= take
        effect.append(
            {
                "공정": str(process),
                "생산계획년월": int(month),
                "입력대수": float(units),
                "반영대수": applied,
                "초과": overdrawn,
            }
        )
    adjusted["가용대수"] = pd.Series(values, index=adjusted.index, dtype="float64")
    frame = pd.DataFrame(effect, columns=list(MANUAL_DOWNTIME_EFFECT_COLUMNS))
    frame["생산계획년월"] = frame["생산계획년월"].astype("int64")
    frame["입력대수"] = frame["입력대수"].astype("float64")
    frame["반영대수"] = frame["반영대수"].astype("float64")
    frame["초과"] = frame["초과"].astype("bool")
    return adjusted, frame


def overdrawn_rows(effect: pd.DataFrame) -> pd.DataFrame:
    """입력이 그 달 가용보다 커 가용이 0 에서 멈춘 줄."""
    if effect.empty:
        return effect
    return effect.loc[effect["초과"].astype("bool").to_numpy()].reset_index(drop=True)


def manual_effect_band(effect: pd.DataFrame, processes: Collection[str] | None = None) -> str:
    """출처 띠 꼬리 — 계획이 실제로 건 칸(`ShorteningPlan.manual_downtime`)으로 적는다.

    `processes` 를 주면 그 공정 칸만 본다. 칸이 없으면 빈 글자, 있으면 「입력 비가동 반영(n칸 · 합
    x대)」 이고 그 달 가용보다 커 0 에서 멈춘 칸이 있으면 「· 가용 넘침 k칸」 을 덧붙인다.
    """
    if effect.empty:
        return ""
    rows = effect
    if processes is not None:
        wanted = {str(process).strip() for process in processes}
        rows = effect.loc[effect["공정"].astype("string").str.strip().isin(wanted).fillna(False)]
    entered = pd.to_numeric(rows["입력대수"], errors="coerce").fillna(0.0)
    rows = rows.loc[entered.gt(0).to_numpy()]
    if rows.empty:
        return ""
    total = float(pd.to_numeric(rows["입력대수"], errors="coerce").fillna(0.0).sum())
    over = int(rows["초과"].astype("bool").sum())
    tail = f" · 가용 넘침 {over}칸" if over else ""
    return f"{MANUAL_DOWNTIME_BAND}({len(rows)}칸 · 합 {manual_units_text(total)}대{tail})"


def manual_units_text(value: float, digits: int = 2) -> str:
    """대수 글 — 소수 `digits`(기본 둘째) 자리까지, 끝 0 은 뗀다(1.50 → 1.5, 2.00 → 2)."""
    text = f"{round(float(value), digits):.{digits}f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def manual_removed_text(value: float) -> str:
    """가용에서 실제로 뺀 몫(`입력 비가동 반영`, 0 이상)의 글 — 공정 Capa 상세 ④ 첫 줄 칸 풍선
    「가용에서 x 뺌」·② 가용 칸 풍선 「입력 비가동 −x 반영」·산출 근거 ② 가용 카드 「− 입력 비가동
    x」 가 함께 쓴다(같은 몫을 세 곳이 다르게 적지 않는다).

    넣은 대수 글(`manual_units_text`)과 같은 꼴이라 넘치지 않은 달은 「입력 비가동 0.04대 — 가용에서
    0.04 뺌」 처럼 두 수가 같은 글이다. 넘친 달의 몫(그 달 가용)은 어떤 자리든 될 수 있어 0 이 아닌
    몫이 「0」 으로 적히면 0 이 아니게 적힐 때까지 한 자리씩 더 본다 — 끝자리를 터는 `_DECIMALS`
    자리까지(그 자리로 0 이면 빈칸 문턱 아래라 「0」).
    """
    digits = 2
    text = manual_units_text(value, digits)
    while round(value, _DECIMALS) != 0 and float(text) == 0 and digits < _DECIMALS:
        digits += 1
        text = manual_units_text(value, digits)
    return text


def manual_downtime_digest(rows: Iterable[ManualRow]) -> str:
    """칸 내용의 지문 — 같은 칸·같은 값이면 같다. Preference 저장의 입력 지문(`save_once` — 같은
    입력의 겹친 둘째 누름을 첫 결과로 알린다)이 쓴다."""
    payload = repr(sorted((str(p), int(m), round(float(u), _STORED_DECIMALS)) for p, m, u in rows))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
