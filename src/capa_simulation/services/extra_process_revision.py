# Purpose: 저장 리비전의 부대공정 값(03 · 04 · 05)을 활성 판 위에 겹쳐 다음 판 양식을 거꾸로 만들고
# 「이 리비전 값을 새 판으로」 를 누를 수 없는 까닭을 가른다.

"""「이 리비전 값을 새 판으로」 의 거꾸로 만들기(설계 3-5 · A15 — 순수 함수).

앱에서 고쳐 저장한 부대공정 값을 다음 판으로 올린다. 바탕은 그 리비전 데이터셋의 출처 표가 가리키는
판이고 **활성 판과 같은 판이어야 한다**(`revision_refusal` — 설계 G4).

**바탕 판 줄에서 시작한다.** 리비전 표에서 통째로 다시 접지 않는다 — 빈칸 → 1.0(측정률) ·
`달력` → 날수 · 대여 빈칸 → 0 은 거꾸로 돌릴 수 없어, 고치지 않은 리비전도 「바뀐 칸」 이 생긴다.
그래서 바탕 판의 값 줄(03 · 04 · 05)마다 리비전 기간(그 리비전 `RQ_PKG_PLAN` 의 달) 안의 달을
리비전 값과 견주고, 같으면(빈칸 ≡ 1.0 · `달력` ≡ 그 달 날수 · 대여 빈칸 ≡ 0) 바탕 줄을 그대로
두고, 다른 달이 있을 때만 그 줄의 기간을 값이 바뀌는 달마다 쪼갠다(설계 G3 — 리비전 기간 밖의 달 ·
리비전에 값이 없는 달은 바탕 값, 열린 끝은 열린 채). `모두` 줄은 양산 · ER 값이 같은 구간에서
`모두` 로 남고 갈린 구간만 둘로 나뉜다. 바꾼 칸은 그 칸만 리비전 값이고 나머지 칸은 바탕 글자
그대로다 — 가동일수가 그 달 날수와 같으면 `달력` 이다.

- **옮기는 표는 03 · 04 · 05 뿐**이다(G2) — 01(모듈수 — 데이터셋 칸이라 고칠 수 없음)과
  02(경로 꼴)는 바탕 판 그대로다. 앱에서 STEP 을 더하거나 뺀 공정은 「경로가 판과 다름」 으로 세고
  경로는 옮기지 않는다 — 바탕 판에 있는 STEP 의 값만 옮긴다(2026-11-19 사용자 답 Q1). 경로
  견줌은 리비전 표에서 그 공정 행을 걷고 바탕 판을 다시 펼친 경로와 리비전 경로를 맞댄다.
- **옮기지 못하는 공정**(바탕 판 값 그대로 — 까닭을 미리보기에 싣는다): 공통 값 줄(따라가기 꼴
  경로 · 공통 값 지정 꼴)인데 리비전에서 제품마다 값이 갈림(G11), 가용대수가 보유 − 대여와
  다름(가용대수를 따로 고침 — 판은 보유 · 대여만 받는다).
- 측정률 0 은 0 그대로다(G9). 바탕 판에서 합치지 않은 공정(뺌 · BDQ 에 생김)은 그대로 둔다.

Streamlit 을 import 하지 않는다.
"""

from __future__ import annotations

import calendar
import math
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final, Protocol, TypeVar

import pandas as pd

from capa_simulation.services.extra_process_merge import (
    MIXED_REASON,
    OUTCOME_MERGED,
    YEAR_SHIFT_NOTE,
    ActiveExtraPack,
    ExtraPackVersion,
    merge_extra_processes,
    strip_extra_processes,
)
from capa_simulation.services.extra_process_pack import (
    BOTH_CLASSES,
    CLASS_EXPANSION,
    ENGINEERING,
    FORMAT_VERSION,
    MASS,
    EquipmentRow,
    ExtraProcessPack,
    PackInfo,
    PackReading,
    Period,
    ProductivityRow,
    RateVitalRow,
    pack_to_zip,
    read_pack_zip,
    wf_key,
)

# 리비전 경로를 바탕 판 경로와 맞대는 칸(계획 변형 · 경로 · WF 구분).
ROUTE_COMPARE_COLUMNS: Final = (
    "생산계획년월",
    "양산구분",
    "제품정보",
    "Stack",
    "Capa Code",
    "Customer",
    "CS",
    "WF 구분",
    "STEP_SEQ",
    "MCP_SEQ",
)
SPLIT_PRODUCTS_REASON: Final = "공통 값인데 제품마다 값이 갈림 — 파일을 고쳐 다시 놓으세요"
AVAILABLE_REASON: Final = "가용대수가 보유 − 대여와 다름 — 판은 보유 · 대여만 받습니다"
_KEY_COLUMNS: Final = (
    "생산계획년월",
    "공정",
    "STEP_SEQ",
    "MCP_SEQ",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
)

_Value = tuple[object, ...]


class _ValueRow(Protocol):
    """값 줄(03 · 04 · 05)의 읽는 칸."""

    @property
    def process(self) -> str: ...

    @property
    def period(self) -> Period: ...


_T = TypeVar("_T", bound=_ValueRow)


@dataclass(frozen=True)
class KeptProcess:
    """옮기지 못해 바탕 판 값 그대로 둔 공정과 그 까닭."""

    process: str
    reason: str


@dataclass(frozen=True)
class RevisionPack:
    """거꾸로 만든 판 한 벌 — 양식 ZIP 바이트(미리보기부터 적용까지 이 바이트 그대로) · 접수 검증
    결과 · 값을 옮긴 공정 · 옮기지 못한 공정 · 경로가 판과 다른 공정."""

    data: bytes
    reading: PackReading
    moved: tuple[str, ...]
    kept: tuple[KeptProcess, ...]
    route_differs: tuple[str, ...]


class _Provenance(Protocol):
    """출처 줄의 읽는 칸(`persistence.models.ExtraProcessProvenance`)."""

    @property
    def process_name(self) -> str: ...

    @property
    def version_no(self) -> int: ...

    @property
    def sha256(self) -> str: ...

    @property
    def outcome(self) -> str: ...

    @property
    def reason(self) -> str | None: ...

    @property
    def note(self) -> str | None: ...


def revision_refusal(
    *,
    off: bool,
    active_sha: str | None,
    active_version_no: int | None,
    records: Sequence[_Provenance],
) -> str | None:
    """「새 판으로」 를 누를 수 없는 까닭(풍선 글) — 누를 수 있으면 None(설계 G4).

    판은 판 이력 차례가 아니라 sha 로 견준다 — 끄기 → 다시 켜기 뒤에도 같은 판이다.
    """
    if off or active_sha is None:
        return "부대공정 판이 꺼져 있습니다 — 먼저 「다시 켜기」"
    if not any(item.outcome == OUTCOME_MERGED for item in records):
        return "이 리비전에는 합친 부대공정이 없습니다"
    if (
        any(item.reason == MIXED_REASON for item in records)
        or len({item.sha256 for item in records}) > 1
    ):
        return "판이 섞인 리비전(월 머지)입니다 — 부대공정 얹기로 한 판으로 맞춘 뒤 누르세요"
    if any(YEAR_SHIFT_NOTE in (item.note or "") for item in records):
        return "연도 Shift 로 만든 리비전이라 달이 판과 어긋납니다 — 부대공정 얹기로 다시 맞추세요"
    record = records[0]
    if record.sha256 != active_sha:
        return (
            f"판 {record.version_no} 로 만든 리비전입니다 — 활성 판 {active_version_no} 로 얹거나 "
            "등록한 시나리오에서 고쳐 저장한 뒤 누르세요"
        )
    return None


def merged_processes(records: Iterable[_Provenance]) -> tuple[str, ...]:
    """출처에서 합친 공정(처음 나온 차례)."""
    return tuple(
        dict.fromkeys(item.process_name for item in records if item.outcome == OUTCOME_MERGED)
    )


def pack_from_revision(
    base: ExtraProcessPack,
    tables: Mapping[str, pd.DataFrame],
    merged: Collection[str],
    *,
    version: ExtraPackVersion,
    version_no: int,
    written_at: str,
    memo: str,
) -> RevisionPack:
    """바탕 판(`base` — 리비전 출처가 가리키는 활성 판) 위에 리비전 값을 겹친 다음 판(`version_no`).

    `merged` 는 그 리비전 데이터셋 출처에서 합친 공정이다 — 나머지 공정은 바탕 판 그대로다.
    `version` 은 바탕 판의 판 이력 차례 · 판 번호 · sha(경로 견줌에 바탕 판을 다시 펼 때 쓴다).
    """
    months = sorted(
        {int(month) for month in pd.to_numeric(tables["RQ_PKG_PLAN"]["생산계획년월"]).dropna()}
    )
    names = [process.name for process in base.processes if process.name in set(merged)]
    route_differs = _route_differs(base, tables, names, version)
    revision = _RevisionValues(tables, names)
    productivity = list(base.productivity)
    equipment = list(base.equipment)
    rate_vital = list(base.rate_vital)
    moved: list[str] = []
    kept: list[KeptProcess] = []
    for process in base.processes:
        if process.name not in names:
            continue
        try:
            new_productivity = _overlay_rows(
                [row for row in productivity if row.process == process.name],
                months,
                _productivity_reader(revision, process.area),
                _productivity_rows,
            )
            new_equipment = _overlay_rows(
                [row for row in equipment if row.process == process.name],
                months,
                lambda row, month: _equipment_values(revision, row, month),
                _equipment_rows,
            )
            new_rates = _overlay_rows(
                [row for row in rate_vital if row.process == process.name],
                months,
                lambda row, month: _rate_values(revision, row, month),
                _rate_rows,
            )
        except _Kept as kept_process:
            kept.append(KeptProcess(process.name, kept_process.reason))
            continue
        productivity = _replaced(productivity, process.name, new_productivity)
        equipment = _replaced(equipment, process.name, new_equipment)
        rate_vital = _replaced(rate_vital, process.name, new_rates)
        moved.append(process.name)
    pack = replace(
        base,
        info=PackInfo(FORMAT_VERSION, version_no, written_at=written_at, author="", memo=memo),
        productivity=tuple(productivity),
        equipment=tuple(equipment),
        rate_vital=tuple(rate_vital),
    )
    data = pack_to_zip(pack)
    return RevisionPack(data, read_pack_zip(data), tuple(moved), tuple(kept), route_differs)


class _Kept(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _replaced(rows: Sequence[_T], process: str, new_rows: Sequence[_T]) -> list[_T]:
    """그 공정의 줄을 새 줄로 갈아 끼운다 — 차례는 그 공정의 첫 줄 자리."""
    result: list[_T] = []
    placed = False
    for row in rows:
        if row.process != process:
            result.append(row)
        elif not placed:
            result.extend(new_rows)
            placed = True
    if not placed:
        result.extend(new_rows)
    return result


# --------------------------------------------------------------------------- 리비전 값 읽기


class _RevisionValues:
    """리비전 표에서 부대공정 값을 키로 찾는다(공정 이름은 앞뒤 공백만 떼고 견준다). 고른 공정의
    행만 읽는다."""

    def __init__(self, tables: Mapping[str, pd.DataFrame], names: Collection[str]) -> None:
        tables = _only_processes(tables, names)
        self.productivity = _productivity_lookup(tables)
        # 공통 값 줄의 견줌 — (달, 공정, STEP, MCP, 양산구분) → 그 앞 칸이 같은 제품마다의 값.
        self.by_prefix: dict[tuple[object, ...], list[dict[str, float | None]]] = {}
        for key, value in self.productivity.items():
            self.by_prefix.setdefault(key[:5], []).append(value)
        self.equipment = _monthly_lookup(
            tables,
            {
                "RQ_RUN_DAY": "RUN_DAY",
                "RQ_EQP_OWN": "설비보유",
                "RQ_EQP_LENT": "설비대여평가",
                "RQ_EQP_AVBL": "가용대수",
            },
            ("생산계획년월", "공정"),
        )
        self.rates = _monthly_lookup(
            tables,
            {"RQ_RUN_RATE": "CAPA_RUN_RATE", "RQ_VITAL": "편중률"},
            ("생산계획년월", "공정", "양산구분"),
        )


def _only_processes(
    tables: Mapping[str, pd.DataFrame], names: Collection[str]
) -> dict[str, pd.DataFrame]:
    wanted = {name.strip() for name in names}
    picked: dict[str, pd.DataFrame] = {}
    for name, frame in tables.items():
        if "공정" not in frame.columns:
            continue
        keep = frame["공정"].astype("string").str.strip().isin(wanted).fillna(False)
        picked[name] = frame.loc[keep]
    return picked


def _number(value: object) -> float | None:
    if value is None or value is pd.NA:
        return None
    try:
        number = float(str(value))
    except ValueError:
        return None
    return None if math.isnan(number) else number


def _text(value: object) -> str:
    return "" if value is None or value is pd.NA else str(value).strip()


def _productivity_lookup(
    tables: Mapping[str, pd.DataFrame],
) -> dict[tuple[object, ...], dict[str, float | None]]:
    """(달, 공정, STEP, MCP, 양산구분, 제품, Stack, WF 구분 견줌 꼴) → UPEH · ST · 측정률 둘."""
    found: dict[tuple[object, ...], dict[str, float | None]] = {}
    for name, columns in (
        ("RQ_UPEH", ("UPEH", "ST")),
        ("RQ_LOT_RATIO", ("Lot 측정률",)),
        ("RQ_WF_RATIO", ("WF측정률",)),
    ):
        frame = tables.get(name)
        if frame is None or frame.empty:
            continue
        for record in frame[[*_KEY_COLUMNS, *columns]].to_dict("records"):
            month = _number(record["생산계획년월"])
            if month is None:
                continue
            key = (
                int(month),
                _text(record["공정"]),
                _text(record["STEP_SEQ"]),
                _text(record["MCP_SEQ"]),
                _text(record["양산구분"]),
                _text(record["제품정보"]),
                _text(record["Stack"]),
                wf_key(_text(record["WF 구분"])),
            )
            slot = found.setdefault(key, {})
            for column in columns:
                slot[column] = _number(record[column])
    return found


def _monthly_lookup(
    tables: Mapping[str, pd.DataFrame], values: Mapping[str, str], keys: Sequence[str]
) -> dict[tuple[object, ...], dict[str, float | None]]:
    found: dict[tuple[object, ...], dict[str, float | None]] = {}
    for name, column in values.items():
        frame = tables.get(name)
        if frame is None or frame.empty:
            continue
        for record in frame[[*keys, column]].to_dict("records"):
            month = _number(record[keys[0]])
            if month is None:
                continue
            key = (int(month), *(_text(record[item]) for item in keys[1:]))
            found.setdefault(key, {})[column] = _number(record[column])
    return found


# --------------------------------------------------------------------------- 견줌 · 겹치기


def _same(left: object, right: object) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-12)
    return left == right


def _pick(base: object, revised: object, equivalent: object = None) -> object:
    """칸 하나 — 리비전 값이 바탕 값과 같은 뜻이면 바탕 글자 그대로, 아니면 리비전 값.

    `equivalent` 는 바탕 빈칸이 뜻하는 값(측정률 1.0 · 대여 0)이다."""
    if revised is None:
        return base
    if _same(base, revised) or (base is None and _same(equivalent, revised)):
        return base
    return revised


def _overlay_rows(
    rows: Sequence[_T],
    months: Sequence[int],
    values: Callable[[_T, int], _Value | None],
    build: Callable[[_T, Sequence[tuple[Period, _Value]]], list[_T]],
) -> list[_T]:
    """바탕 줄마다 리비전 기간 안의 달을 리비전 값과 견줘, 다른 달이 있으면 값이 바뀌는 달마다
    쪼갠다. `values(row, month)` 는 그 달의 겹친 값(리비전 값이 없으면 None — 바탕 값)이고 바탕
    줄의 값과 같은 꼴(`build` 가 읽는 꼴)이다."""
    result: list[_T] = []
    for row in rows:
        period = row.period
        base_value = values(row, -1)
        assert base_value is not None
        inside = [month for month in months if period.covers(month)]
        overrides = {month: values(row, month) for month in inside}
        if all(value is None or value == base_value for value in overrides.values()):
            result.append(row)
            continue
        last = period.end if period.end is not None else max(period.start, max(months))
        segments: list[tuple[int, int | None, _Value]] = []
        month = period.start
        while month <= last:
            value = overrides.get(month) or base_value
            if segments and segments[-1][2] == value:
                start, _, _ = segments[-1]
                segments[-1] = (start, month, value)
            else:
                segments.append((month, month, value))
            month = _next_month(month)
        if period.end is None:
            start, end, value = segments[-1]
            if value == base_value:
                segments[-1] = (start, None, value)
            else:
                segments.append((_next_month(last), None, base_value))
        result.extend(build(row, [(Period(start, end), value) for start, end, value in segments]))
    return result


def _next_month(month: int) -> int:
    return month + 1 if month % 100 < 12 else (month // 100 + 1) * 100 + 1


def _split_classes(mass_class: str, value: _Value, unit: int) -> list[tuple[str, _Value]]:
    """`모두` 줄의 값(양산 몫 · ER 몫을 이은 꼴)이 같으면 `모두` 한 줄, 다르면 둘."""
    if mass_class != BOTH_CLASSES:
        return [(mass_class, value)]
    mass, engineering = value[:unit], value[unit:]
    if mass == engineering:
        return [(BOTH_CLASSES, mass)]
    return [(MASS, mass), (ENGINEERING, engineering)]


# ---- 03 생산성


def _productivity_reader(
    revision: _RevisionValues, area: str
) -> Callable[[ProductivityRow, int], _Value | None]:
    def read(row: ProductivityRow, month: int) -> _Value | None:
        return _productivity_values(revision, area, row, month)

    return read


def _productivity_values(
    revision: _RevisionValues, area: str, row: ProductivityRow, month: int
) -> _Value | None:
    """그 줄 · 그 달의 겹친 값 — 양산구분마다 (UPEH, ST, Lot, WF) 를 이은 꼴. `month` 가 -1 이면
    바탕 값."""
    classes = CLASS_EXPANSION[row.mass_class]
    base = (row.upeh, row.st, row.lot_ratio, row.wf_ratio)
    if month < 0:
        return base * len(classes)
    main_column = "UPEH" if area == "Main" else "ST"
    combined: list[object] = []
    found = False
    for mass_class in classes:
        revised = _productivity_at(revision, row, month, mass_class)
        if revised is None:
            combined.extend(base)
            continue
        found = True
        upeh = _pick(row.upeh, revised.get("UPEH")) if main_column == "UPEH" else row.upeh
        st = _pick(row.st, revised.get("ST")) if main_column == "ST" else row.st
        combined.extend(
            (
                upeh,
                st,
                _pick(row.lot_ratio, revised.get("Lot 측정률"), 1.0),
                _pick(row.wf_ratio, revised.get("WF측정률"), 1.0),
            )
        )
    return tuple(combined) if found else None


def _productivity_at(
    revision: _RevisionValues, row: ProductivityRow, month: int, mass_class: str
) -> dict[str, float | None] | None:
    prefix = (month, row.process.strip(), row.step, row.mcp, mass_class)
    if not row.common:
        return revision.productivity.get((*prefix, row.product, row.stack, wf_key(row.wf)))
    found = revision.by_prefix.get(prefix, [])
    if not found:
        return None
    distinct = {tuple(sorted(item.items())) for item in found}
    if len(distinct) > 1:
        raise _Kept(SPLIT_PRODUCTS_REASON)
    return found[0]


def _productivity_rows(
    row: ProductivityRow, segments: Sequence[tuple[Period, _Value]]
) -> list[ProductivityRow]:
    rows: list[ProductivityRow] = []
    for period, value in segments:
        for mass_class, part in _split_classes(row.mass_class, value, 4):
            upeh, st, lot, wafer = part
            rows.append(
                replace(
                    row,
                    mass_class=mass_class,
                    period=period,
                    upeh=_optional_float(upeh),
                    st=_optional_float(st),
                    lot_ratio=_optional_float(lot),
                    wf_ratio=_optional_float(wafer),
                    row=0,
                )
            )
    return rows


def _optional_float(value: object) -> float | None:
    return None if value is None else float(str(value))


# ---- 04 가동일수 · 설비


def _days(month: int) -> int:
    return calendar.monthrange(month // 100, month % 100)[1]


def _equipment_values(revision: _RevisionValues, row: EquipmentRow, month: int) -> _Value | None:
    """(RUN_DAY — None 은 달력, 보유, 대여) — `month` 가 -1 이면 바탕 값."""
    base = (row.run_day, row.owned, row.lent)
    if month < 0:
        return base
    revised = revision.equipment.get((month, row.process.strip()))
    if not revised:
        return None
    run_day = revised.get("RUN_DAY")
    owned = revised.get("설비보유")
    lent = revised.get("설비대여평가")
    available = revised.get("가용대수")
    if owned is not None and available is not None and not _same(available, owned - (lent or 0.0)):
        raise _Kept(AVAILABLE_REASON)
    if (
        run_day is None
        or _same(run_day, row.run_day)
        or (row.run_day is None and _same(run_day, _days(month)))
    ):
        day: object = row.run_day
    else:
        day = None if _same(run_day, _days(month)) else int(round(run_day))
    value = (day, _pick(row.owned, owned), _pick(row.lent, lent, 0.0))
    return None if value == base else value


def _equipment_rows(
    row: EquipmentRow, segments: Sequence[tuple[Period, _Value]]
) -> list[EquipmentRow]:
    rows: list[EquipmentRow] = []
    for period, (day, owned, lent) in segments:
        rows.append(
            replace(
                row,
                period=period,
                run_day=None if day is None else int(str(day)),
                owned=float(str(owned)),
                lent=_optional_float(lent),
                row=0,
            )
        )
    return rows


# ---- 05 효율 · 여유율


def _rate_values(revision: _RevisionValues, row: RateVitalRow, month: int) -> _Value | None:
    """양산구분마다 (효율, 여유율)을 이은 꼴 — `month` 가 -1 이면 바탕 값."""
    classes = CLASS_EXPANSION[row.mass_class]
    base = (row.run_rate, row.vital)
    if month < 0:
        return base * len(classes)
    combined: list[object] = []
    found = False
    for mass_class in classes:
        revised = revision.rates.get((month, row.process.strip(), mass_class))
        if not revised:
            combined.extend(base)
            continue
        found = True
        combined.extend(
            (
                _pick(row.run_rate, revised.get("CAPA_RUN_RATE")),
                _pick(row.vital, revised.get("편중률")),
            )
        )
    return tuple(combined) if found else None


def _rate_rows(row: RateVitalRow, segments: Sequence[tuple[Period, _Value]]) -> list[RateVitalRow]:
    rows: list[RateVitalRow] = []
    for period, value in segments:
        for mass_class, (rate, vital) in _split_classes(row.mass_class, value, 2):
            rows.append(
                replace(
                    row,
                    mass_class=mass_class,
                    period=period,
                    run_rate=float(str(rate)),
                    vital=float(str(vital)),
                    row=0,
                )
            )
    return rows


# --------------------------------------------------------------------------- 경로 견줌(Q1)


def _route_differs(
    base: ExtraProcessPack,
    tables: Mapping[str, pd.DataFrame],
    names: Sequence[str],
    version: ExtraPackVersion,
) -> tuple[str, ...]:
    """리비전 경로가 바탕 판을 다시 펼친 경로와 다른 공정 — 앱에서 STEP 을 더하거나 뺐다."""
    if not names:
        return ()
    stripped = strip_extra_processes(tables, names)
    expected = merge_extra_processes(
        stripped, ActiveExtraPack(version, base), check=lambda _tables: None
    ).tables["RQ_REQB"]
    actual = tables["RQ_REQB"]
    differs: list[str] = []
    for name in names:
        if _route_keys(expected, name) != _route_keys(actual, name):
            differs.append(name)
    return tuple(differs)


def _route_keys(frame: pd.DataFrame, process: str) -> set[tuple[object, ...]]:
    picked = frame.loc[frame["공정"].astype("string").str.strip().eq(process).fillna(False)]
    keys: set[tuple[object, ...]] = set()
    for record in picked[list(ROUTE_COMPARE_COLUMNS)].to_dict("records"):
        month = _number(record["생산계획년월"])
        keys.add(
            (
                None if month is None else int(month),
                *(
                    wf_key(_text(record[column])) if column == "WF 구분" else _text(record[column])
                    for column in ROUTE_COMPARE_COLUMNS[1:]
                ),
            )
        )
    return keys
