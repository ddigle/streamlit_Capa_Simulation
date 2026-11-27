# Purpose: 부대공정 판 편집기의 순수 몸통 — 판 ↔ 편집 모형, 월 축 보기, 점 고침, 판 줄 접기, 정규
# 바이트, 「바뀐 것 없음」 견줌, 거절 되짚기, 입력 문제 · 기준 데이터 도우미를 맡는다.

"""부대공정 판 편집기(Admin Area 「부대공정」 탭의 셋째 길 — CSV · S3 Drive 가져오기 곁).

Streamlit 을 import 하지 않는다. 화면은 이 모듈의 모형(`EditorModel`)을 그리드 초안의 전체
상태로 다시 짓고(`with_lines` · `with_cells` — 병합이 아니다), 판은 `fold` → `canonical` 로 만들어
기존 받은 판 자리에 싣는다. 관문(V-01 ~ V-14)은 바꾸지 않는다 — 편집기는 검사 전 글 줄을 짓고
관문이 거절 표로 답한다(`input_problems` 는 입력을 돕기만 한다).

**공정은 둘로 가른다**(`carried_processes`).

- **편집기 몫** — 01 줄 하나 + 따라가기 꼴 경로(02) 정확히 하나, 그 공정의 03 이 모두 공통
  행(제품 칸 셋 빈칸)이고 키 (STEP_SEQ, MCP_SEQ) 가 그 경로와 같다, 측정률이 모두 1 과 같은
  뜻(빈칸 · 0 · 1 — 빈칸은 합치기가, 0 은 대당 Capa 가 1.0 으로 읽는다), 04 RUN_DAY 가 모두 `달력`.
- **통째 옮김** — 그 밖 전부. 02 ~ 05 의 그 공정 줄을 글자 그대로 다시 내보내고 편집기는 공정째
  지우기만 한다(이름 · Area · 값을 고치지 않는다).

**모형은 절대 달이다.** 값 칸 열쇠는 (줄 id, 표, 양산구분, 칸) × (달 `YYYYMM` 또는
`Onward(달)` — 그 달부터 경로 끝까지)이고 계획 창을 담지 않는다. 그래서 `fold` ·
`input_problems` 는 창을 받지 않고, 창은 무엇을 보이고 고칠 수 있나만 정한다(`month_view`). 같은
칸 고침이면 어느 시나리오에서든 같은 판이다.

**달마다 값**(줄 하나 · 칸 하나 — 앞의 것이 이긴다): 그 달 점 고침 → `Onward` 고침(시작이 가장
늦은 것) → 바탕 판 값 → 채움. 채움은 바탕에 값이 없는 달(새 공정 · 늘린 경로)에만 선다 — ER 줄은
같은 달 양산 값, 그 밖은 앞 달 값(빈칸은 건너뜀 · 대여는 빈칸도 값), 앞에 없으면 대여는 0 ·
나머지는 뒤에서 처음 적힌 값이다. 그래서 새 공정의 「이후」 칸은 마지막 창 달 값을, 「이전」 칸은
첫 창 달 값을 이어 쓴다. 바탕이 있는 달은 고친 그 칸만 바뀐다(점 고침 — 「계속」 표지 같은 숨은
이어 쓰기는 없다). `Onward` 고침은 그 범위의 바탕 값이 하나(또는 없음)일 때만 받고, 보기는 그 칸
고침을 뺀 값도 하나일 때만 「이후」 칸을 연다(다른 창의 고침이 범위 안에 있으면 「여러 값」 잠김).

**고침 걷기.** 들어온 칸 가운데 빼도 그 줄의 달마다 값이 하나도 바뀌지 않는 칸은 고침이
아니다(늦은 달부터 걷는다). 보인 값을 다시 적으면 「바뀐 것 없음」 이다 — MI 는 화면
UPEH(`60 / ST` 를 `MI_UPEH_DIGITS` 자리로 반올림)로 받고, 적은 값이 그 줄 바탕 ST 의 보인 값과
같으면 그 ST 원값을 쓴다(아니면 `ST = 60 / UPEH`). 대여 빈칸과 0 은 같다.

**접기.** 손대지 않은 표(공정 × 03 · 04 · 05)는 바탕 줄을 글자 그대로 제자리에 다시 쓴다. 고친
표는 경로 기간의 달마다 값을 같은 값 이웃 달끼리 한 기간으로 묶고, 양산 = ER 인 달은 `모두` 한
줄, 갈린 달은 양산 · ER 따로 쓴다 — 첫 기간 시작 = 경로 시작, 마지막 기간 끝 = 경로 끝(열렸으면
빈칸). 고치지 않은 달은 바탕 원 칸(ST · 측정률 · 대여 빈칸)을 그대로 쓴다. 고친 표의 새 줄은 그
공정의 첫 원 줄 자리, 새 공정은 끝에 붙는다. 01 줄 차례는 편집기 줄 차례(R-07)다. 이름 · 경로
기간을 바꾸면 그 공정의 세 표를, Area · STEP · MCP 를 바꾸면 03 을 다시 짓는다(Area Main ↔ MI 는
03 값을 UPEH 기준 `60 / x` 로 옮긴다). 다시 지은 표는 경로 기간만 덮는다.

**정규 바이트**(`canonical`): 글 줄 → `pack_files` → 묶기 → 관문 → 받으면 `pack_to_zip` 을
고정점까지 되풀이한다(겹친 Excel 가드처럼 한 번에 닿지 않는 글이 있다). **바뀐 것
없음**(`same_body`)은 00 을 바탕 판 것으로 고정한 본문 바이트 견줌이다(바탕이 없으면 늘 새 판).

**입력 돕기.** `input_problems` 는 관문이 거절할 입력(빈칸 · 0 이하 · 글 · 대여 > 보유 · 01 ·
02 칸)을 창과 상관없이 줄 · 칸마다 모은다 — 판 만들기를 막지 않는다(관문이 정본).
`editor_warnings` 는 관문이 모르는 기준 데이터 쪽 알림(R-01 이름 · R-02 참조공정 · 닫힌 끝월 ·
창과 안 겹친 경로 · 효율 > 1 · 판에 들지 않는 칸)이다. 기준 데이터 도우미(`editor_context` ·
`reference_choices` · `line_defaults` · `follow_preview`)는 옛 판 공정을 걷은 이름으로 센다 —
걷기는 strip 이름을 대소문자 그대로 견주고, 부대공정끼리 참조 금지(V-06)는 대소문자를 무시한다.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final, TypeAlias, TypeVar

import pandas as pd

from capa_simulation.services.extra_process_merge import bdq_process_names, follow_routes
from capa_simulation.services.extra_process_pack import (
    BOTH_CLASSES,
    BUFFER_WORD,
    CALENDAR_WORD,
    CLASS_EXPANSION,
    ENGINEERING,
    EQUIPMENT_FILE,
    INFO_FILE,
    MASS,
    PACK_HEADERS,
    PROCESS_FILE,
    PRODUCTIVITY_FILE,
    RATE_FILE,
    ROUTE_FILE,
    EquipmentRow,
    ExtraProcessPack,
    PackInfo,
    PackProblem,
    PackReading,
    Period,
    ProcessRow,
    ProductivityRow,
    RateVitalRow,
    RouteRow,
    bundle_pack_files,
    equipment_cells,
    info_rows,
    number_cell,
    pack_files,
    pack_to_zip,
    process_cells,
    productivity_cells,
    rate_cells,
    read_pack_zip,
    route_cells,
    text_cell,
)
from capa_simulation.services.frame_contracts import (
    AREA_NAMES,
    DEMAND_BASES,
    normalize_demand_basis,
    normalize_demand_basis_value,
)

# 표 · 칸 이름 — 그리드 줄 업무 키와 거절 되짚기가 같이 쓴다.
PROCESS_TABLE: Final = "01"
ROUTE_TABLE: Final = "02"
PRODUCTIVITY: Final = "03"
EQUIPMENT: Final = "04"
RATE: Final = "05"
UPEH_COLUMN: Final = "UPEH"
OWNED_COLUMN: Final = "설비보유"
LENT_COLUMN: Final = "설비대여평가"
RUN_RATE_COLUMN: Final = "CAPA_RUN_RATE"
VITAL_COLUMN: Final = "편중률"
# MI 화면 UPEH(60 / ST)를 보이는 자리 수 — 「보인 글과 같은가」 견줌도 이 자리로 한다.
MI_UPEH_DIGITS: Final = 2
# 펼친 판의 줄 id 머리 — 01 차례 1부터(`b1` …). 새 줄 id 는 화면이 짓고 이 머리를 쓰지 않는다.
BASE_LINE_PREFIX: Final = "b"
# 통째 옮김 까닭(`carried_processes`).
CARRY_ROUTES: Final = "경로가 둘 이상"
CARRY_SPECIFIED: Final = "지정 꼴 경로"
CARRY_PRODUCT_ROWS: Final = "생산성(03)에 제품 행이 있음"
CARRY_OTHER_KEY: Final = "생산성(03) 키가 경로의 STEP · MCP 와 다름"
CARRY_RATIO: Final = "측정률이 1 이 아님"
CARRY_RUN_DAY: Final = "RUN_DAY 가 달력이 아님"

CellInput: TypeAlias = float | int | str | None
# 값 줄 열쇠 — (줄 id, 표, 양산구분(04 는 빈칸), 칸).
RowKey: TypeAlias = tuple[str, str, str, str]
_ROW_SPECS: Final[tuple[tuple[str, str, str], ...]] = (
    (PRODUCTIVITY, MASS, UPEH_COLUMN),
    (PRODUCTIVITY, ENGINEERING, UPEH_COLUMN),
    (EQUIPMENT, "", OWNED_COLUMN),
    (EQUIPMENT, "", LENT_COLUMN),
    (RATE, MASS, RUN_RATE_COLUMN),
    (RATE, MASS, VITAL_COLUMN),
    (RATE, ENGINEERING, RUN_RATE_COLUMN),
    (RATE, ENGINEERING, VITAL_COLUMN),
)
_CLASS_ORDER: Final = {BOTH_CLASSES: 0, MASS: 1, ENGINEERING: 2}
_FileRow: TypeAlias = RouteRow | ProductivityRow | EquipmentRow | RateVitalRow
_T = TypeVar("_T")
_FILE_TABLES: Final = {
    PROCESS_FILE: PROCESS_TABLE,
    ROUTE_FILE: ROUTE_TABLE,
    PRODUCTIVITY_FILE: PRODUCTIVITY,
    EQUIPMENT_FILE: EQUIPMENT,
    RATE_FILE: RATE,
}


class _Missing:
    """바탕 판에 값이 없는 달(채움 대상) — 빈칸(None)과 다르다."""

    def __repr__(self) -> str:
        return "MISSING"


_MISSING: Final = _Missing()
_Slot: TypeAlias = float | int | str | None | _Missing


@dataclass(frozen=True, order=True)
class Onward:
    """「이후」 칸 열쇠 — 그 달부터 경로 끝까지(열렸으면 열린 끝까지) 한 값."""

    start: int


MonthCell: TypeAlias = int | Onward
CellKey: TypeAlias = tuple[RowKey, MonthCell]


def value_rows(line_id: str) -> tuple[RowKey, ...]:
    """편집기 몫 줄 하나의 값 줄 열쇠 — 03 양산 · ER, 04 보유 · 대여, 05 양산 · ER × 효율 ·
    편중률(이 차례로 짓는다 — ER 줄이 양산 줄을 따른다)."""
    return tuple((line_id, *spec) for spec in _ROW_SPECS)


# --------------------------------------------------------------------------- 모형


@dataclass(frozen=True)
class LineFields:
    """01 + 02 한 줄의 모형 값 — 사람 입력이라 글 · 수가 섞일 수 있다(검사는 관문 ·
    `input_problems`)."""

    name: str = ""
    area: str = ""
    basis: str = ""
    modules: CellInput = None
    memo: str = ""
    reference: str = ""
    step: str = ""
    mcp: str = ""
    start: CellInput = None
    end: CellInput = None


@dataclass(frozen=True)
class EditorLine:
    """편집기 줄 하나 — `base_name` 은 펼친 판의 공정 이름(새 줄 None), `carried` 는 통째 옮김
    까닭(None = 편집기 몫). 통째 옮김 줄의 `fields` 는 바탕 01 값이고 경로 칸은 빈칸이다."""

    line_id: str
    fields: LineFields
    base_name: str | None = None
    carried: str | None = None


@dataclass(frozen=True)
class EditorModel:
    """편집기 상태 — 바탕 판 · 펼친 때의 줄(고정) · 지금 줄(차례 = 01 차례) · 값 칸 입력 전체.

    `cells` 는 그리드가 보낸 칸 입력 그대로다(걷기 전). 걷은 고침은 `effective_edits` 가 센다.
    """

    base: ExtraProcessPack | None
    origin: tuple[EditorLine, ...]
    lines: tuple[EditorLine, ...]
    cells: Mapping[CellKey, CellInput] = field(default_factory=dict)

    def line(self, line_id: str) -> EditorLine | None:
        return next((line for line in self.lines if line.line_id == line_id), None)


def carried_processes(pack: ExtraProcessPack) -> dict[str, str]:
    """편집기 몫이 아닌 공정 → 통째 옮김 까닭(01 차례). 모듈 설명 「공정은 둘로 가른다」."""
    found: dict[str, str] = {}
    for process in pack.processes:
        reason = _carry_reason(pack, process.name)
        if reason is not None:
            found[process.name] = reason
    return found


def _carry_reason(pack: ExtraProcessPack, name: str) -> str | None:
    routes = [route for route in pack.routes if route.process == name]
    if len(routes) != 1:
        return CARRY_ROUTES
    route = routes[0]
    if not route.follows:
        return CARRY_SPECIFIED
    productivity = [row for row in pack.productivity if row.process == name]
    if any(not row.common for row in productivity):
        return CARRY_PRODUCT_ROWS
    if any((row.step, row.mcp) != (route.step, route.mcp) for row in productivity):
        return CARRY_OTHER_KEY
    if any(
        not _ratio_neutral(value) for row in productivity for value in (row.lot_ratio, row.wf_ratio)
    ):
        return CARRY_RATIO
    if any(row.run_day is not None for row in pack.equipment if row.process == name):
        return CARRY_RUN_DAY
    return None


def _ratio_neutral(value: float | None) -> bool:
    return value is None or value in (0.0, 1.0)


def model_from_pack(pack: ExtraProcessPack | None) -> EditorModel:
    """판을 펼친 편집기 모형(제안 a) — 판이 없으면 빈 모형(새 줄만)."""
    if pack is None:
        return EditorModel(None, (), ())
    carried = carried_processes(pack)
    lines: list[EditorLine] = []
    for number, process in enumerate(pack.processes, start=1):
        line_id = f"{BASE_LINE_PREFIX}{number}"
        reason = carried.get(process.name)
        fields = LineFields(
            name=process.name,
            area=process.area,
            basis=process.basis,
            modules=process.modules,
            memo=process.memo,
        )
        if reason is None:
            route = next(route for route in pack.routes if route.process == process.name)
            fields = replace(
                fields,
                reference=route.reference,
                step=route.step,
                mcp=route.mcp,
                start=route.period.start,
                end=route.period.end,
            )
        lines.append(EditorLine(line_id, fields, process.name, reason))
    return EditorModel(pack, tuple(lines), tuple(lines), {})


def with_lines(model: EditorModel, rows: Sequence[tuple[str, LineFields]]) -> EditorModel:
    """줄 그리드의 전체 상태(차례대로 (줄 id, 값))로 줄을 다시 짓는다 — 빠진 줄은 지운다(02 ~ 05 가
    함께 빠짐). 펼친 줄과 같은 값 칸은 바탕 값을 그대로 쓰고, 통째 옮김 줄은 값을 받지 않는다."""
    origin = {line.line_id: line for line in model.origin}
    lines: list[EditorLine] = []
    seen: set[str] = set()
    for line_id, fields in rows:
        if line_id in seen:
            continue
        seen.add(line_id)
        base = origin.get(line_id)
        if base is None:
            lines.append(EditorLine(line_id, fields))
        elif base.carried is not None:
            lines.append(base)
        else:
            lines.append(replace(base, fields=_settled_fields(fields, base.fields)))
    return replace(model, lines=tuple(lines))


def with_cells(model: EditorModel, cells: Mapping[CellKey, CellInput]) -> EditorModel:
    """값 그리드들의 전체 칸 입력으로 바꾼다(병합 아님 — 되돌린 칸은 빠진 채로 온다)."""
    return replace(model, cells=dict(cells))


def _settled_fields(new: LineFields, old: LineFields) -> LineFields:
    """펼친 줄과 같은 뜻의 칸은 바탕 값을 그대로 둔다(같은 글이 다시 쓰이게)."""

    def pick(name: str) -> Any:
        new_value, old_value = getattr(new, name), getattr(old, name)
        return old_value if _same_field(name, new_value, old_value) else new_value

    return LineFields(
        name=pick("name"),
        area=pick("area"),
        basis=pick("basis"),
        modules=pick("modules"),
        memo=pick("memo"),
        reference=pick("reference"),
        step=pick("step"),
        mcp=pick("mcp"),
        start=pick("start"),
        end=pick("end"),
    )


def _same_field(name: str, new: object, old: object) -> bool:
    if name in ("start", "end"):
        return _month_or_text(new) == _month_or_text(old)
    if name == "modules":
        return _number_or_text(new) == _number_or_text(old)
    if name == "area":
        return _text(new).casefold() == _text(old).casefold()
    if name == "basis":
        return _basis(new) == _basis(old)
    return _text(new) == _text(old)


# --------------------------------------------------------------------------- 칸 값 꼴


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _area(value: object) -> str | None:
    lookup = {name.casefold(): name for name in AREA_NAMES}
    return lookup.get(_text(value).casefold())


def _basis(value: object) -> str:
    text = _text(value)
    return normalize_demand_basis_value(text) if text else ""


def _number_or_text(value: object) -> CellInput:
    """사람 입력 → 수(유한) · 빈칸 None · 그 밖은 글 그대로(관문 V-14 가 거절)."""
    if value is None or isinstance(value, bool):
        return None if value is None else str(value)
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else str(value)
    text = str(value).strip()
    if text == "":
        return None
    if "," in text or "_" in text:
        return text
    try:
        number = float(text)
    except ValueError:
        return text
    return number if math.isfinite(number) else text


def _month_or_text(value: object) -> int | str | None:
    """월 입력 → YYYYMM 정수 · 빈칸 None · 그 밖은 글 그대로."""
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if not value.is_integer():
            return str(value)
        value = int(value)
    text = str(value).strip()
    if text == "":
        return None
    if len(text) == 6 and text.isdigit() and 1 <= int(text[4:]) <= 12:
        return int(text)
    return text


def _positive(value: object) -> bool:
    return isinstance(value, float) and value > 0 and math.isfinite(value)


def _mi_upeh(st: float) -> float:
    return round(60.0 / st, MI_UPEH_DIGITS)


def _shown(value: CellInput, area: str | None, table: str) -> CellInput:
    """판 칸 값 → 화면 값(MI 생산성은 UPEH 반올림)."""
    if table == PRODUCTIVITY and area == "MI" and isinstance(value, float) and _positive(value):
        return _mi_upeh(value)
    return value


def _same(column: str, left: object, right: object) -> bool:
    if column == LENT_COLUMN:
        left = 0.0 if left is None else left
        right = 0.0 if right is None else right
    return type(left) is type(right) and left == right


def _cell_text(value: object) -> str:
    if value is None or isinstance(value, _Missing):
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return number_cell(float(value))
    return text_cell(str(value))


# --------------------------------------------------------------------------- 월 축


def plan_span(months: Iterable[int]) -> tuple[int, ...]:
    """계획 월 → 첫 달 ~ 끝 달의 이어진 달(사이 빈 달도 칸으로 보인다 — 보이지 않는 달이 없게)."""
    present = sorted({int(month) for month in months})
    if not present:
        return ()
    return _months_between(present[0], present[-1])


@dataclass(frozen=True)
class MonthAxis:
    """줄 하나의 월 축 — [이전] + 창 달 + [이후]. 이전 · 이후는 (첫 달, 끝 달 · None = 열림)."""

    start: int
    end: int | None
    before: tuple[int, int] | None
    window: tuple[int, ...]
    after: tuple[int, int | None] | None


def month_axis(fields: LineFields, months: Iterable[int]) -> MonthAxis | None:
    """경로 기간(시작월 · 끝월)과 계획 월로 축을 짓는다 — 기간이 읽히지 않으면 None."""
    period = _route_period(fields)
    if period is None:
        return None
    start, end = period
    span = plan_span(months)
    if not span:
        return MonthAxis(start, end, None, (), (start, end))
    window = tuple(month for month in span if month >= start and (end is None or month <= end))
    before = None
    if start < span[0]:
        before_end = _previous_month(span[0])
        before = (start, before_end if end is None else min(end, before_end))
    after = None
    if end is None or end > span[-1]:
        after = (max(start, _next_month(span[-1])), end)
    return MonthAxis(start, end, before, window, after)


def _route_period(fields: LineFields) -> tuple[int, int | None] | None:
    start = _month_or_text(fields.start)
    end = _month_or_text(fields.end)
    if not isinstance(start, int) or isinstance(end, str):
        return None
    if end is not None and end < start:
        return None
    return start, end


def _next_month(month: int) -> int:
    return month + 1 if month % 100 < 12 else (month // 100 + 1) * 100 + 1


def _previous_month(month: int) -> int:
    return month - 1 if month % 100 > 1 else (month // 100 - 1) * 100 + 12


def _months_between(first: int, last: int) -> tuple[int, ...]:
    found: list[int] = []
    month = first
    while month <= last:
        found.append(month)
        month = _next_month(month)
    return tuple(found)


# --------------------------------------------------------------------------- 바탕 값


@dataclass(frozen=True)
class _BaseRows:
    process: ProcessRow
    route: RouteRow | None
    productivity: tuple[ProductivityRow, ...]
    equipment: tuple[EquipmentRow, ...]
    rate_vital: tuple[RateVitalRow, ...]


def _base_rows(pack: ExtraProcessPack | None, name: str | None) -> _BaseRows | None:
    if pack is None or name is None:
        return None
    process = next((item for item in pack.processes if item.name == name), None)
    if process is None:
        return None
    return _BaseRows(
        process,
        next((route for route in pack.routes if route.process == name), None),
        tuple(row for row in pack.productivity if row.process == name),
        tuple(row for row in pack.equipment if row.process == name),
        tuple(row for row in pack.rate_vital if row.process == name),
    )


def _converted(value: float | None, source: str, target: str | None) -> CellInput:
    """03 판 값을 다른 Area 의 판 값으로(Main UPEH ↔ MI ST — `60 / x`)."""
    if target is None or source == target or value is None or not value > 0:
        return value
    return 60.0 / value


def _layer(
    months: Sequence[int], base: _BaseRows | None, row: RowKey, area: str | None
) -> list[_Slot]:
    """바탕 판의 그 줄 값(달마다) — 없는 달은 `_MISSING`."""
    slots: list[_Slot] = [_MISSING] * len(months)
    if base is None:
        return slots
    _, table, mass_class, column = row
    pairs: list[tuple[Period, CellInput]] = []
    if table == PRODUCTIVITY:
        source = base.process.area
        for item in base.productivity:
            if mass_class in CLASS_EXPANSION[item.mass_class]:
                raw = item.upeh if source == "Main" else item.st
                pairs.append((item.period, _converted(raw, source, area)))
    elif table == EQUIPMENT:
        for equipment in base.equipment:
            held = equipment.owned if column == OWNED_COLUMN else equipment.lent
            pairs.append((equipment.period, held))
    else:
        for rate in base.rate_vital:
            if mass_class in CLASS_EXPANSION[rate.mass_class]:
                pairs.append(
                    (rate.period, rate.run_rate if column == RUN_RATE_COLUMN else rate.vital)
                )
    for period, found in pairs:
        for index, month in enumerate(months):
            if period.covers(month):
                slots[index] = found
    return slots


def _ratio_form(base: _BaseRows | None) -> tuple[float | None, float | None]:
    """다시 지은 03 의 바탕 없는 달 측정률 — 바탕 03 이 한 꼴이면 그 꼴, 아니면 1 · 1."""
    if base is not None:
        forms = {(row.lot_ratio, row.wf_ratio) for row in base.productivity}
        if len(forms) == 1:
            return next(iter(forms))
    return (1.0, 1.0)


def _ratio_at(
    base: _BaseRows | None, mass_class: str, month: int
) -> tuple[float | None, float | None] | None:
    if base is None:
        return None
    for row in base.productivity:
        if mass_class in CLASS_EXPANSION[row.mass_class] and row.period.covers(month):
            return (row.lot_ratio, row.wf_ratio)
    return None


# --------------------------------------------------------------------------- 줄 값 짓기


def _row_values(
    months: Sequence[int],
    layer: Sequence[_Slot],
    points: Mapping[int, CellInput],
    onward: Mapping[int, CellInput],
    *,
    column: str,
    follow: Sequence[CellInput] | None,
) -> list[CellInput]:
    """달마다 값 — 모듈 설명 「달마다 값」(점 고침 → Onward → 바탕 → 채움)."""
    slots: list[_Slot] = list(layer)
    for start in sorted(onward):
        for index, month in enumerate(months):
            if month >= start:
                slots[index] = onward[start]
    for index, month in enumerate(months):
        if month in points:
            slots[index] = points[month]
    if follow is not None:
        return [
            follow[index] if isinstance(slot, _Missing) else slot
            for index, slot in enumerate(slots)
        ]
    lent = column == LENT_COLUMN
    later: list[CellInput] = [None] * len(slots)
    upcoming: CellInput = None
    for index in range(len(slots) - 1, -1, -1):
        slot = slots[index]
        if not isinstance(slot, _Missing) and slot is not None:
            upcoming = slot
        later[index] = upcoming
    values: list[CellInput] = []
    carry: _Slot = _MISSING
    for index, slot in enumerate(slots):
        value: CellInput
        if not isinstance(slot, _Missing):
            value = slot
        elif not isinstance(carry, _Missing):
            value = carry
        elif lent:
            value = 0.0
        else:
            value = later[index]
        values.append(value)
        if value is not None or lent:
            carry = value
    return values


def _onward_open(months: Sequence[int], layer: Sequence[_Slot], start: int, column: str) -> bool:
    """그 달부터 끝까지 바탕 값이 하나(또는 없음)인가 — `Onward` 고침을 받는 조건."""
    seen: list[CellInput] = []
    for slot in _span(months, layer, start, None):
        if isinstance(slot, _Missing):
            continue
        if not any(_same(column, slot, value) for value in seen):
            seen.append(slot)
    return len(seen) <= 1


@dataclass(frozen=True)
class _RowResult:
    values: tuple[CellInput, ...]
    points: Mapping[int, CellInput]
    onward: Mapping[int, CellInput]
    layer: tuple[_Slot, ...]


@dataclass(frozen=True)
class _LineResult:
    line: EditorLine
    months: tuple[int, ...]
    end: int | None
    area: str | None
    base: _BaseRows | None
    rows: Mapping[RowKey, _RowResult]
    ignored: tuple[CellKey, ...]
    redundant: tuple[CellKey, ...]

    def without(self, row: RowKey, cell: MonthCell) -> list[CellInput]:
        """그 칸 고침만 뺀 그 줄의 달마다 값(그리드 양식 — 「이 칸을 고치지 않았을 때」)."""
        result = self.rows[row]
        points = dict(result.points)
        onward = dict(result.onward)
        if isinstance(cell, Onward):
            onward.pop(cell.start, None)
        else:
            points.pop(cell, None)
        follow = None
        if row[2] == ENGINEERING:
            follow = list(self.rows[(row[0], row[1], MASS, row[3])].values)
        return _row_values(self.months, result.layer, points, onward, column=row[3], follow=follow)


def _line_months(
    fields: LineFields, base: _BaseRows | None, cells: Iterable[MonthCell]
) -> tuple[tuple[int, ...], int | None] | None:
    """경로 달(시작 ~ 끝, 열렸으면 모든 꺾임 뒤 한 달까지 — 그 달이 열린 꼬리를 맡는다)."""
    period = _route_period(fields)
    if period is None:
        return None
    start, end = period
    if end is not None:
        return _months_between(start, end), end
    marks = [start]
    if base is not None:
        periods = [
            *(row.period for row in base.productivity),
            *(row.period for row in base.equipment),
            *(row.period for row in base.rate_vital),
        ]
        for row_period in periods:
            marks.append(row_period.start)
            if row_period.end is not None:
                marks.append(_next_month(row_period.end))
    for cell in cells:
        marks.append(cell.start if isinstance(cell, Onward) else cell)
    last = _next_month(max(marks))
    return _months_between(start, last), None


def _compute_line(model: EditorModel, line: EditorLine) -> _LineResult | None:
    """편집기 몫 줄 하나의 달마다 값과 걷은 고침 — 창과 상관없다."""
    if line.carried is not None:
        return None
    own = {key: value for key, value in model.cells.items() if key[0][0] == line.line_id}
    base = _base_rows(model.base, line.base_name)
    shape = _line_months(line.fields, base, (cell for _, cell in own))
    if shape is None:
        return None
    months, end = shape
    area = _area(line.fields.area)
    rows: dict[RowKey, _RowResult] = {}
    ignored: list[CellKey] = []
    redundant: list[CellKey] = []
    known_rows = set(value_rows(line.line_id))
    ignored.extend(key for key in own if key[0] not in known_rows)
    month_set = set(months)
    for row in value_rows(line.line_id):
        layer = _layer(months, base, row, area)
        candidates = _mi_candidates(layer, row, area)
        points: dict[int, CellInput] = {}
        onward: dict[int, CellInput] = {}
        for (key_row, cell), raw in own.items():
            if key_row != row:
                continue
            value = _input_value(raw, row, area, candidates)
            if isinstance(cell, Onward):
                if cell.start in month_set and _onward_open(months, layer, cell.start, row[3]):
                    onward[cell.start] = value
                else:
                    ignored.append((row, cell))
            elif cell in month_set and not (end is None and cell == months[-1]):
                points[cell] = value
            else:
                ignored.append((row, cell))
        follow = None
        if row[2] == ENGINEERING:
            follow = list(rows[(row[0], row[1], MASS, row[3])].values)
        settled = _settle(months, layer, points, onward, row[3], follow)
        rows[row] = settled
        redundant.extend((row, month) for month in points if month not in settled.points)
        redundant.extend((row, Onward(start)) for start in onward if start not in settled.onward)
    return _LineResult(line, months, end, area, base, rows, tuple(ignored), tuple(redundant))


def _mi_candidates(layer: Sequence[_Slot], row: RowKey, area: str | None) -> tuple[float, ...]:
    """MI 생산성 입력을 바탕 ST 원값으로 맞출 후보(그 줄 바탕 값, 달 차례)."""
    if row[1] != PRODUCTIVITY or area != "MI":
        return ()
    found: list[float] = []
    for slot in layer:
        if isinstance(slot, float) and slot not in found:
            found.append(slot)
    return tuple(found)


def _input_value(
    raw: CellInput, row: RowKey, area: str | None, candidates: Sequence[float]
) -> CellInput:
    """그리드 칸 입력 → 판 값. MI 생산성은 화면 UPEH 를 ST 로(보인 글이 같은 바탕 ST 는 원값)."""
    value = _number_or_text(raw)
    if (
        row[1] != PRODUCTIVITY
        or area != "MI"
        or not isinstance(value, float)
        or not _positive(value)
    ):
        return value
    shown = value
    for st in candidates:
        if _positive(st) and _mi_upeh(st) == shown:
            return st
    return 60.0 / shown


def _settle(
    months: Sequence[int],
    layer: Sequence[_Slot],
    points: Mapping[int, CellInput],
    onward: Mapping[int, CellInput],
    column: str,
    follow: Sequence[CellInput] | None,
) -> _RowResult:
    """빼도 줄 값이 하나도 바뀌지 않는 고침을 늦은 달부터 걷는다(모듈 설명 「고침 걷기」)."""
    kept_points = dict(points)
    kept_onward = dict(onward)
    values = _row_values(months, layer, kept_points, kept_onward, column=column, follow=follow)
    order: list[MonthCell] = [*kept_points, *(Onward(start) for start in kept_onward)]
    order.sort(key=lambda cell: (cell.start, 0) if isinstance(cell, Onward) else (cell, 1))
    for cell in reversed(order):
        trial_points = dict(kept_points)
        trial_onward = dict(kept_onward)
        if isinstance(cell, Onward):
            trial_onward.pop(cell.start)
        else:
            trial_points.pop(cell)
        trial = _row_values(months, layer, trial_points, trial_onward, column=column, follow=follow)
        if all(_same(column, left, right) for left, right in zip(values, trial, strict=True)):
            kept_points, kept_onward, values = trial_points, trial_onward, trial
    return _RowResult(tuple(values), kept_points, kept_onward, tuple(layer))


def effective_edits(model: EditorModel) -> dict[CellKey, CellInput]:
    """걷은 뒤 남은 고침(판 값 꼴 — MI 생산성은 ST)."""
    found: dict[CellKey, CellInput] = {}
    for line in model.lines:
        result = _compute_line(model, line)
        if result is None:
            continue
        for row, row_result in result.rows.items():
            for month, value in row_result.points.items():
                found[(row, month)] = value
            for start, value in row_result.onward.items():
                found[(row, Onward(start))] = value
    return found


def redundant_cells(model: EditorModel) -> tuple[CellKey, ...]:
    """판에 드는 자리지만 빼도 아무것도 바뀌지 않아 걷은 칸 입력 — 화면은 흡수할 때마다 이 가운데
    그리드에 보이지 않는 칸을 초안에서 지운다(남겨 두면 다른 칸 고침으로 그 칸의 「고치지 않았을 때
    값」 이 바뀔 때 보이지 않던 옛 입력이 되살아난다 — 다른 창에서 적은 이후 칸처럼). 보이는 칸은
    사람이 지금 보고 적은 값이라 남긴다(다른 칸을 바꿔도 그 값)."""
    found: list[CellKey] = []
    for line in model.lines:
        result = _compute_line(model, line)
        if result is not None:
            found.extend(result.redundant)
    return tuple(found)


def ignored_cells(model: EditorModel) -> tuple[CellKey, ...]:
    """판에 들지 않는 칸 입력 — 지운 줄 · 통째 옮김 줄 · 경로 밖 달 · 받지 않는 「이후」 칸."""
    live = {line.line_id: line for line in model.lines}
    found: list[CellKey] = []
    computed: dict[str, _LineResult | None] = {}
    for key in model.cells:
        line_id = key[0][0]
        line = live.get(line_id)
        if line is None or line.carried is not None:
            found.append(key)
            continue
        if line_id not in computed:
            computed[line_id] = _compute_line(model, line)
        result = computed[line_id]
        if result is None or key in result.ignored:
            found.append(key)
    return tuple(found)


# --------------------------------------------------------------------------- 보기


@dataclass(frozen=True)
class CellView:
    """값 칸 하나의 보기 — `value` 는 판에 들어갈 값(화면 꼴), `default` 는 이 칸 고침이 없을 때의
    값(그리드 양식). `multiple` 은 이전 · 이후 칸이 여러 값을 덮어 한 값으로 보일 수 없음이다."""

    value: CellInput
    default: CellInput
    editable: bool
    edited: bool
    multiple: bool = False
    key: MonthCell | None = None


@dataclass(frozen=True)
class LineView:
    """편집기 몫 줄 하나의 월 보기 — 값 줄마다 이전 칸 · 창 달 칸 · 이후 칸."""

    line_id: str
    axis: MonthAxis | None
    before: Mapping[RowKey, CellView]
    months: Mapping[RowKey, Mapping[int, CellView]]
    after: Mapping[RowKey, CellView]


def month_view(model: EditorModel, months: Iterable[int]) -> dict[str, LineView]:
    """계획 창에서 보이는 값 — 보이는 모든 칸의 값은 `fold` 가 그 달에 쓰는 값과 같다."""
    plan = tuple(months)
    views: dict[str, LineView] = {}
    for line in model.lines:
        if line.carried is not None:
            continue
        axis = month_axis(line.fields, plan)
        result = _compute_line(model, line)
        if axis is None or result is None:
            views[line.line_id] = LineView(line.line_id, axis, {}, {}, {})
            continue
        before: dict[RowKey, CellView] = {}
        window: dict[RowKey, dict[int, CellView]] = {}
        after: dict[RowKey, CellView] = {}
        area = result.area
        for row, row_result in result.rows.items():
            table, column = row[1], row[3]
            cells: dict[int, CellView] = {}
            for month in axis.window:
                value = _at(result.months, row_result.values, month)
                edited = month in row_result.points
                default = _at(result.months, result.without(row, month), month) if edited else value
                cells[month] = CellView(
                    _shown(value, area, table),
                    _shown(default, area, table),
                    True,
                    edited,
                    key=month,
                )
            window[row] = cells
            if axis.before is not None:
                single = _single(_span(result.months, row_result.values, *axis.before), column)
                shown_before = _shown(single[1], area, table)
                before[row] = CellView(shown_before, shown_before, False, False, not single[0])
            if axis.after is not None:
                start = axis.after[0]
                span = _span(result.months, row_result.values, *axis.after)
                edited = start in row_result.onward
                default_span = (
                    _span(result.months, result.without(row, Onward(start)), *axis.after)
                    if edited
                    else span
                )
                single = _single(span, column)
                default_single = _single(default_span, column)
                # 모형은 바탕 값이 하나인 범위의 Onward 를 받는다(받은 고침이 뒤 고침으로 떨어지지
                # 않게). 보기는 그 칸 고침을 뺀 값도 하나일 때만 연다 — 다른 창에서 한 고침이 범위
                # 안에 있으면 적어도 한 값이 되지 않으므로 「여러 값」 읽기 전용이다.
                editable = (
                    _onward_open(result.months, row_result.layer, start, column)
                    and default_single[0]
                )
                after[row] = CellView(
                    _shown(single[1], area, table),
                    _shown(default_single[1], area, table),
                    editable,
                    edited,
                    not single[0],
                    Onward(start),
                )
        views[line.line_id] = LineView(line.line_id, axis, before, window, after)
    return views


def _span(months: Sequence[int], values: Sequence[_T], first: int, last: int | None) -> list[_T]:
    """[첫 달, 끝 달 · None = 열림] 의 값 — 줄 달 뒤로 넘는 범위는 마지막 달(열린 꼬리) 값이다."""
    picked = [
        value
        for month, value in zip(months, values, strict=True)
        if month >= first and (last is None or month <= last)
    ]
    if not picked and months and first > months[-1] and (last is None or last >= first):
        picked = [values[-1]]
    return picked


def _at(months: Sequence[int], values: Sequence[CellInput], month: int) -> CellInput:
    """그 달 값 — 줄 달 뒤(열린 꼬리)는 마지막 달 값."""
    found = _span(months, values, month, month)
    return found[0] if found else None


def _single(values: Sequence[CellInput], column: str) -> tuple[bool, CellInput]:
    """(한 값인가, 그 값 · 여러 값이면 None)."""
    if not values:
        return True, None
    first = values[0]
    if all(_same(column, first, value) for value in values[1:]):
        return True, first
    return False, None


# --------------------------------------------------------------------------- 접기


@dataclass(frozen=True)
class RowOrigin:
    """만든 판의 한 줄이 어디서 왔나 — 줄 id · 공정 · 표 · 양산구분 · 기간, 통째 옮김 줄인가."""

    line_id: str
    process: str
    table: str
    mass_class: str = ""
    start: int | None = None
    end: int | None = None
    carried: bool = False


@dataclass(frozen=True)
class Folded:
    """편집기 모형을 접은 판 글 줄(파일 → 줄, 머리 칸 뺌)과 (파일, 행 번호 — 머리 = 1) 출처 지도."""

    rows: Mapping[str, tuple[tuple[str, ...], ...]]
    origins: Mapping[tuple[str, int], RowOrigin]


def fold(model: EditorModel, info: PackInfo) -> Folded:
    """모형 → 검사 전 판 글 줄(모듈 설명 「접기」). 창을 받지 않는다."""
    rows: dict[str, list[tuple[str, ...]]] = {name: [] for name in PACK_HEADERS}
    origins: dict[tuple[str, int], RowOrigin] = {}

    def add(file: str, cells: Sequence[str], origin: RowOrigin) -> None:
        rows[file].append(tuple(cells))
        origins[(file, len(rows[file]) + 1)] = origin

    rows[INFO_FILE] = [tuple(item) for item in info_rows(info)]
    lines = [line for line in model.lines if not _blank_line(model, line)]
    built: dict[str, _Built] = {}
    for line in lines:
        if line.carried is None:
            built[line.line_id] = _build_line(model, line)
    by_base = {line.base_name: line for line in lines if line.base_name is not None}
    base_processes = {} if model.base is None else {p.name: p for p in model.base.processes}
    for line in lines:
        process = base_processes.get(line.base_name or "")
        if line.carried is not None and process is not None:
            add(PROCESS_FILE, process_cells(process), _origin(line, PROCESS_TABLE, carried=True))
        else:
            add(PROCESS_FILE, _process_cells(line.fields), _origin(line, PROCESS_TABLE))
    for file in (ROUTE_FILE, PRODUCTIVITY_FILE, EQUIPMENT_FILE, RATE_FILE):
        table = _FILE_TABLES[file]
        placed: set[str] = set()
        for base_row in _base_file_rows(model.base, file):
            owner = by_base.get(base_row.process)
            if owner is None:
                continue
            build = built.get(owner.line_id)
            if build is None or (table != ROUTE_TABLE and table not in build.touched):
                add(file, _verbatim_cells(base_row), _verbatim_origin(owner, table, base_row))
            elif owner.line_id not in placed:
                placed.add(owner.line_id)
                for cells, origin in build.rows.get(table, ()):
                    add(file, cells, origin)
        for line in lines:
            build = built.get(line.line_id)
            if build is None or line.line_id in placed:
                continue
            if table == ROUTE_TABLE or table in build.touched:
                for cells, origin in build.rows.get(table, ()):
                    add(file, cells, origin)
    return Folded({name: tuple(found) for name, found in rows.items()}, origins)


@dataclass(frozen=True)
class _Built:
    touched: frozenset[str]
    rows: Mapping[str, tuple[tuple[tuple[str, ...], RowOrigin], ...]]


def _blank_line(model: EditorModel, line: EditorLine) -> bool:
    """빈 새 줄(값도 칸 입력도 없음) — 판에 싣지 않는다."""
    if line.base_name is not None:
        return False
    if any(_text(getattr(line.fields, name)) for name in LineFields.__dataclass_fields__):
        return False
    return not any(key[0][0] == line.line_id for key in model.cells)


def _origin(line: EditorLine, table: str, *, carried: bool = False) -> RowOrigin:
    return RowOrigin(line.line_id, _text(line.fields.name), table, carried=carried)


def _verbatim_origin(line: EditorLine, table: str, row: _FileRow) -> RowOrigin:
    mass_class = row.mass_class if isinstance(row, (ProductivityRow, RateVitalRow)) else ""
    return RowOrigin(
        line.line_id,
        row.process,
        table,
        mass_class,
        row.period.start,
        row.period.end,
        carried=line.carried is not None,
    )


def _base_file_rows(pack: ExtraProcessPack | None, file: str) -> Sequence[_FileRow]:
    if pack is None:
        return ()
    if file == ROUTE_FILE:
        return pack.routes
    if file == PRODUCTIVITY_FILE:
        return pack.productivity
    if file == EQUIPMENT_FILE:
        return pack.equipment
    return pack.rate_vital


def _verbatim_cells(row: _FileRow) -> list[str]:
    if isinstance(row, RouteRow):
        return route_cells(row)
    if isinstance(row, ProductivityRow):
        return productivity_cells(row)
    if isinstance(row, EquipmentRow):
        return equipment_cells(row)
    return rate_cells(row)


def _process_cells(fields: LineFields) -> list[str]:
    area = _area(fields.area)
    basis = _basis(fields.basis)
    return [
        text_cell(_text(fields.name)),
        area if area is not None else text_cell(_text(fields.area)),
        basis if basis in DEMAND_BASES else text_cell(_text(fields.basis)),
        _cell_text(_number_or_text(fields.modules)),
        text_cell(_text(fields.memo)),
    ]


def _route_row_cells(fields: LineFields) -> list[str]:
    return [
        text_cell(_text(fields.name)),
        text_cell(_text(fields.reference)),
        "",
        "",
        "",
        text_cell(_text(fields.step)),
        text_cell(_text(fields.mcp)),
        _month_cell(fields.start),
        _month_cell(fields.end),
    ]


def _month_cell(value: object) -> str:
    month = _month_or_text(value)
    if month is None:
        return ""
    return str(month) if isinstance(month, int) else text_cell(month)


def _touched(line: EditorLine, origin: EditorLine | None) -> frozenset[str]:
    """이름 · 경로 기간이 바뀌면 세 표, Area · STEP · MCP 가 바뀌면 03 을 다시 짓는다."""
    if origin is None:
        return frozenset({PRODUCTIVITY, EQUIPMENT, RATE})
    new, old = line.fields, origin.fields
    touched: set[str] = set()
    if (new.name, new.start, new.end) != (old.name, old.start, old.end):
        touched.update({PRODUCTIVITY, EQUIPMENT, RATE})
    if (new.area, new.step, new.mcp) != (old.area, old.step, old.mcp):
        touched.add(PRODUCTIVITY)
    return frozenset(touched)


def _build_line(model: EditorModel, line: EditorLine) -> _Built:
    origin = next((item for item in model.origin if item.line_id == line.line_id), None)
    if origin is not None and origin.carried is not None:
        origin = None
    touched = set(_touched(line, origin))
    route = ((tuple(_route_row_cells(line.fields)), _origin(line, ROUTE_TABLE)),)
    result = _compute_line(model, line)
    if result is None:
        return _Built(frozenset(touched), {ROUTE_TABLE: route})
    for row, row_result in result.rows.items():
        if row_result.points or row_result.onward:
            touched.add(row[1])
    name = _text(line.fields.name)
    built: dict[str, tuple[tuple[tuple[str, ...], RowOrigin], ...]] = {ROUTE_TABLE: route}
    built[PRODUCTIVITY] = _productivity_rows(result, line, name)
    built[EQUIPMENT] = _equipment_rows(result, line, name)
    built[RATE] = _rate_rows(result, line, name)
    return _Built(frozenset(touched), built)


def _runs(
    months: Sequence[int], end: int | None, values: Sequence[_T], mask: Sequence[bool]
) -> list[tuple[int, int | None, _T]]:
    """`mask` 가 참인 달에서 같은 값 이웃 달을 한 기간으로 — 마지막 달에 닿으면 끝은 경로 끝."""
    runs: list[tuple[int, int | None, _T]] = []
    index = 0
    count = len(months)
    while index < count:
        if not mask[index]:
            index += 1
            continue
        stop = index
        while stop + 1 < count and mask[stop + 1] and values[stop + 1] == values[index]:
            stop += 1
        runs.append((months[index], end if stop == count - 1 else months[stop], values[index]))
        index = stop + 1
    return runs


def _class_runs(
    months: Sequence[int], end: int | None, mass: Sequence[_T], er: Sequence[_T]
) -> list[tuple[str, int, int | None, _T]]:
    """양산 = ER 인 달은 `모두`, 갈린 달은 양산 · ER 따로 — (시작, 양산구분) 차례."""
    both = [left == right for left, right in zip(mass, er, strict=True)]
    split = [not flag for flag in both]
    pieces: list[tuple[str, int, int | None, _T]] = [
        *((BOTH_CLASSES, *run) for run in _runs(months, end, mass, both)),
        *((MASS, *run) for run in _runs(months, end, mass, split)),
        *((ENGINEERING, *run) for run in _runs(months, end, er, split)),
    ]
    pieces.sort(key=lambda piece: (piece[1], _CLASS_ORDER[piece[0]]))
    return pieces


def _productivity_rows(
    result: _LineResult, line: EditorLine, name: str
) -> tuple[tuple[tuple[str, ...], RowOrigin], ...]:
    form = _ratio_form(result.base)
    step, mcp = _text(line.fields.step), _text(line.fields.mcp)
    series: dict[str, list[tuple[CellInput, float | None, float | None]]] = {}
    for mass_class in (MASS, ENGINEERING):
        values = result.rows[(line.line_id, PRODUCTIVITY, mass_class, UPEH_COLUMN)].values
        series[mass_class] = [
            (value, *(_ratio_at(result.base, mass_class, month) or form))
            for month, value in zip(result.months, values, strict=True)
        ]
    built: list[tuple[tuple[str, ...], RowOrigin]] = []
    for mass_class, start, end, piece in _class_runs(
        result.months, result.end, series[MASS], series[ENGINEERING]
    ):
        value, lot, wafer = piece
        main = result.area != "MI"
        cells = (
            text_cell(name),
            "",
            "",
            "",
            text_cell(step),
            text_cell(mcp),
            mass_class,
            str(start),
            "" if end is None else str(end),
            _cell_text(value) if main else "",
            "" if main else _cell_text(value),
            _cell_text(lot),
            _cell_text(wafer),
        )
        built.append((cells, RowOrigin(line.line_id, name, PRODUCTIVITY, mass_class, start, end)))
    return tuple(built)


def _equipment_rows(
    result: _LineResult, line: EditorLine, name: str
) -> tuple[tuple[tuple[str, ...], RowOrigin], ...]:
    owned = result.rows[(line.line_id, EQUIPMENT, "", OWNED_COLUMN)].values
    lent = result.rows[(line.line_id, EQUIPMENT, "", LENT_COLUMN)].values
    pairs = list(zip(owned, lent, strict=True))
    built: list[tuple[tuple[str, ...], RowOrigin]] = []
    for start, end, pair in _runs(result.months, result.end, pairs, [True] * len(pairs)):
        owned_value, lent_value = pair
        cells = (
            text_cell(name),
            str(start),
            "" if end is None else str(end),
            CALENDAR_WORD,
            _cell_text(owned_value),
            _cell_text(lent_value),
        )
        built.append((cells, RowOrigin(line.line_id, name, EQUIPMENT, "", start, end)))
    return tuple(built)


def _rate_rows(
    result: _LineResult, line: EditorLine, name: str
) -> tuple[tuple[tuple[str, ...], RowOrigin], ...]:
    series: dict[str, list[tuple[CellInput, CellInput]]] = {}
    for mass_class in (MASS, ENGINEERING):
        run_rate = result.rows[(line.line_id, RATE, mass_class, RUN_RATE_COLUMN)].values
        vital = result.rows[(line.line_id, RATE, mass_class, VITAL_COLUMN)].values
        series[mass_class] = list(zip(run_rate, vital, strict=True))
    built: list[tuple[tuple[str, ...], RowOrigin]] = []
    for mass_class, start, end, pair in _class_runs(
        result.months, result.end, series[MASS], series[ENGINEERING]
    ):
        run_rate_value, vital_value = pair
        cells = (
            text_cell(name),
            mass_class,
            str(start),
            "" if end is None else str(end),
            _cell_text(run_rate_value),
            _cell_text(vital_value),
        )
        built.append((cells, RowOrigin(line.line_id, name, RATE, mass_class, start, end)))
    return tuple(built)


# --------------------------------------------------------------------------- 정규 바이트 · 견줌


@dataclass(frozen=True)
class Canonical:
    """판 만들기 결과 — 받으면 정규 바이트와 그 읽기(시험 계산 · 적용이 같은 바이트), 거절이면 묶은
    첫 바이트와 거절 표. `fixed` 는 쓰기 → 읽기가 고정점에 닿았나다."""

    data: bytes
    reading: PackReading
    fixed: bool


_FIXED_POINT_ROUNDS: Final = 4


def canonical(rows: Mapping[str, Sequence[Sequence[str]]]) -> Canonical:
    """글 줄 → 장 바이트 → 묶기 → 관문 → 받으면 `pack_to_zip` 을 고정점까지(모듈 설명 「정규
    바이트」)."""
    first = bundle_pack_files(pack_files(rows))
    reading = read_pack_zip(first)
    if reading.pack is None:
        return Canonical(first, reading, False)
    data = pack_to_zip(reading.pack)
    for _ in range(_FIXED_POINT_ROUNDS):
        again = read_pack_zip(data)
        if again.pack is None:
            return Canonical(data, again, False)
        rewritten = pack_to_zip(again.pack)
        if rewritten == data:
            return Canonical(data, again, True)
        data = rewritten
    return Canonical(data, read_pack_zip(data), False)


def same_body(new: ExtraProcessPack, base: ExtraProcessPack | None) -> bool:
    """00 을 바탕 판 것으로 고정한 본문 바이트가 같은가 — 바탕이 없으면 거짓(늘 새 판)."""
    if base is None:
        return False
    return pack_to_zip(replace(new, info=base.info)) == pack_to_zip(base)


# --------------------------------------------------------------------------- 거절 되짚기


@dataclass(frozen=True)
class ProblemPlace:
    """거절 표 한 줄이 가리키는 편집기 자리 — 줄 · 표 · 양산구분 · 칸(MI ST → UPEH) · 기간."""

    line_id: str
    process: str
    table: str
    mass_class: str
    column: str
    start: int | None
    end: int | None
    carried: bool


def locate(problem: PackProblem, folded: Folded) -> ProblemPlace | None:
    """관문 거절 → 편집기 자리(00 · 파일 전체 거절은 None). 통째 옮김 줄은 `carried`."""
    if problem.row is None or problem.file == INFO_FILE:
        return None
    origin = folded.origins.get((problem.file, problem.row))
    if origin is None:
        return None
    column = problem.column
    if origin.table == PRODUCTIVITY and not origin.carried and column in ("ST", "UPEH"):
        column = UPEH_COLUMN
    return ProblemPlace(
        origin.line_id,
        origin.process,
        origin.table,
        origin.mass_class,
        column,
        origin.start,
        origin.end,
        origin.carried,
    )


# --------------------------------------------------------------------------- 입력 문제 · 알림


@dataclass(frozen=True)
class InputProblem:
    """관문이 거절할 입력 한 갈래 — 줄 · 표(01 · 02 칸은 "01", 판 전체는 "") · 값 줄 · 칸 · 달 ·
    까닭."""

    line_id: str | None
    table: str
    row: RowKey | None
    column: str
    months: tuple[int, ...]
    reason: str


def input_problems(model: EditorModel) -> tuple[InputProblem, ...]:
    """창과 상관없이 모은 입력 문제(모듈 설명 「입력 돕기」) — 판 만들기를 막지 않는다."""
    lines = [line for line in model.lines if not _blank_line(model, line)]
    if not lines:
        return (InputProblem(None, "", None, "공정", (), "공정이 하나도 없음"),)
    found: list[InputProblem] = []
    names = [_text(line.fields.name).casefold() for line in lines]
    seen: set[str] = set()
    for line, key in zip(lines, names, strict=True):
        if key and key in seen:
            found.append(_field_problem(line, "공정", "공정 중복(대소문자 무시)"))
        seen.add(key)
        if line.carried is None:
            found.extend(_line_field_problems(line, set(names)))
            result = _compute_line(model, line)
            if result is not None:
                found.extend(_value_problems(result))
    return tuple(found)


def _field_problem(line: EditorLine, column: str, reason: str) -> InputProblem:
    return InputProblem(line.line_id, PROCESS_TABLE, None, column, (), reason)


def _line_field_problems(line: EditorLine, names: Collection[str]) -> list[InputProblem]:
    fields = line.fields
    found: list[InputProblem] = []
    if not _text(fields.name):
        found.append(_field_problem(line, "공정", "공정 빈칸"))
    if _area(fields.area) is None:
        found.append(_field_problem(line, "Area_Name", "Area_Name 은 Main · MI"))
    if _basis(fields.basis) not in DEMAND_BASES:
        found.append(_field_problem(line, "소요기준", "소요기준은 PKG · CHIP · WF"))
    if not _positive(_number_or_text(fields.modules)):
        found.append(_field_problem(line, "모듈수", "모듈수는 0 보다 커야 함"))
    reference = _text(fields.reference)
    if not reference:
        found.append(_field_problem(line, "참조공정", "참조공정 빈칸"))
    elif reference.casefold() in names:
        found.append(_field_problem(line, "참조공정", "부대공정끼리는 참조하지 않음"))
    if not _text(fields.step) or not _text(fields.mcp):
        found.append(_field_problem(line, "STEP_SEQ", "STEP_SEQ · MCP_SEQ 빈칸"))
    start = _month_or_text(fields.start)
    end = _month_or_text(fields.end)
    if start is None:
        found.append(_field_problem(line, "시작월", "시작월 빈칸"))
    elif isinstance(start, str):
        found.append(_field_problem(line, "시작월", "월 꼴(YYYYMM)이 아님"))
    if isinstance(end, str):
        found.append(_field_problem(line, "끝월", "월 꼴(YYYYMM)이 아님"))
    elif isinstance(start, int) and end is not None and end < start:
        found.append(_field_problem(line, "끝월", "끝월이 시작월보다 앞"))
    return found


def _value_problems(result: _LineResult) -> list[InputProblem]:
    found: list[InputProblem] = []
    line_id = result.line.line_id
    owned = result.rows[(line_id, EQUIPMENT, "", OWNED_COLUMN)].values
    for row, row_result in result.rows.items():
        column = row[3]
        reasons: dict[str, list[int]] = {}
        for index, (month, value) in enumerate(zip(result.months, row_result.values, strict=True)):
            reason = _value_reason(column, value, owned[index])
            if reason is not None:
                reasons.setdefault(reason, []).append(month)
        for reason, months in reasons.items():
            found.append(InputProblem(line_id, row[1], row, column, tuple(months), reason))
    return found


def _value_reason(column: str, value: CellInput, owned: CellInput) -> str | None:
    if column == LENT_COLUMN:
        if value is None:
            return None
        if not isinstance(value, float):
            return "수가 아님"
        if value < 0:
            return "0 이상이어야 함"
        if isinstance(owned, float) and value > owned:
            return "대여 > 보유"
        return None
    if value is None:
        return "빈칸"
    if not isinstance(value, float):
        return "수가 아님"
    if column == OWNED_COLUMN:
        return "0 이상이어야 함" if value < 0 else None
    return None if value > 0 else "0 보다 커야 함"


@dataclass(frozen=True)
class EditorWarning:
    """관문이 모르는 기준 데이터 쪽 알림 — 줄(판 전체는 None) · 갈래 낱말 · 글."""

    line_id: str | None
    code: str
    text: str


def editor_warnings(model: EditorModel, context: EditorContext) -> tuple[EditorWarning, ...]:
    """모듈 설명 「입력 돕기」 의 알림 — 등록 때 R-01 · R-02 · R-04 로 빠지거나 잘릴 것을 미리
    보인다."""
    found: list[EditorWarning] = []
    last_plan = context.months[-1] if context.months else None
    for line in model.lines:
        if _blank_line(model, line):
            continue
        name = _text(line.fields.name)
        if name and name.casefold() in context.bdq_names:
            found.append(
                EditorWarning(line.line_id, "R-01", "BDQ 에 같은 이름 — 등록 때 BDQ 값으로 셈")
            )
        if line.carried is not None:
            continue
        choice = _reference(context, _text(line.fields.reference))
        if _text(line.fields.reference) and choice is None:
            found.append(
                EditorWarning(
                    line.line_id, "R-02", "참조공정이 이번 기준 데이터 후보에 없음 — 등록 때 빠짐"
                )
            )
        elif choice is not None and choice.basis != _basis(line.fields.basis):
            found.append(
                EditorWarning(line.line_id, "R-02", "참조공정 소요기준이 다름 — 등록 때 빠짐")
            )
        period = _route_period(line.fields)
        if period is not None:
            end = period[1]
            if end is not None and last_plan is not None:
                text = (
                    f"경로 끝월 {end} 뒤 계획 달은 계산에 들지 않음"
                    if end < last_plan
                    else f"경로 끝월 {end} 이 닫힘 — 계획이 그 뒤로 가면 빠짐"
                )
                found.append(EditorWarning(line.line_id, "끝월", text))
            axis = month_axis(line.fields, context.months)
            if axis is not None and not axis.window:
                found.append(EditorWarning(line.line_id, "창", "경로가 이번 계획 월과 겹치지 않음"))
        result = _compute_line(model, line)
        if result is not None and _over_one(result):
            found.append(EditorWarning(line.line_id, "효율", "효율이 1 을 넘음"))
    ignored = len(ignored_cells(model))
    if ignored:
        found.append(EditorWarning(None, "고침", f"판에 안 든 칸 입력 {ignored}칸"))
    return tuple(found)


def _over_one(result: _LineResult) -> bool:
    for mass_class in (MASS, ENGINEERING):
        values = result.rows[(result.line.line_id, RATE, mass_class, RUN_RATE_COLUMN)].values
        if any(isinstance(value, float) and value > 1 for value in values):
            return True
    return False


# --------------------------------------------------------------------------- 기준 데이터 도우미


@dataclass(frozen=True)
class ReferenceChoice:
    """참조공정 후보 — 소요기준(하나), Area(Main · MI 한 값일 때), 모듈수(0 보다 큰 한 값일 때),
    (STEP_SEQ, MCP_SEQ) 고유 조합(차례대로 — 결정3 은 이 가운데 하나를 1경로로 고른다)."""

    name: str
    basis: str
    area: str | None
    modules: float | None
    steps: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class EditorContext:
    """활성 시나리오 기준 데이터에서 센 편집기 맥락 — 계획 월, 참조공정 후보, R-01
    이름(casefold)."""

    months: tuple[int, ...]
    references: Mapping[str, ReferenceChoice]
    bdq_names: frozenset[str]


def editor_context(
    tables: Mapping[str, pd.DataFrame], excluded: Collection[str] = ()
) -> EditorContext:
    """기준 데이터 16표에서 편집기 맥락을 센다 — 표는 고치지 않고 사본도 만들지 않는다.

    `excluded` 는 옛 판 공정(바탕 데이터셋 출처의 걷을 이름 — `split_previous(...).stripped`)이다.
    그 행은 strip 이름을 대소문자 그대로 견주어 뺀다(`strip_extra_processes` 와 같은 견줌). 후보는
    `normalize_demand_basis` 집합이 정확히 하나이고 PKG · CHIP · WF 인 공정이다(R-02 — 소요기준이
    섞인 공정 · BOX · PCB 는 늘 빠진다).
    """
    plan = tables["RQ_PKG_PLAN"]["생산계획년월"].dropna()
    months = tuple(sorted({int(month) for month in plan}))
    dropped = {name.strip() for name in excluded}
    reqb = tables["RQ_REQB"]
    names = reqb["공정"].astype("string").str.strip()
    keep = (names.notna() & ~names.isin(dropped)).fillna(False).astype(bool)
    frame = pd.DataFrame(
        {
            "name": names.loc[keep],
            "basis": normalize_demand_basis(reqb.loc[keep, "소요기준"]),
            "area": reqb.loc[keep, "Area_Name"].astype("string").str.strip(),
            "step": reqb.loc[keep, "STEP_SEQ"].astype("string"),
            "mcp": reqb.loc[keep, "MCP_SEQ"].astype("string"),
        }
    )
    modules = _module_counts(tables.get("RQ_MODULE"), dropped)
    references: dict[str, ReferenceChoice] = {}
    for name, group in frame.groupby("name", sort=True):
        bases = {str(value) for value in group["basis"].dropna().unique()}
        if len(bases) != 1 or next(iter(bases)) not in DEMAND_BASES:
            continue
        areas = {_area(value) for value in group["area"].dropna().unique()}
        pairs = group[["step", "mcp"]].dropna().drop_duplicates()
        steps = tuple(sorted((str(step), str(mcp)) for step, mcp in pairs.itertuples(index=False)))
        references[str(name)] = ReferenceChoice(
            str(name),
            next(iter(bases)),
            next(iter(areas)) if len(areas) == 1 and None not in areas else None,
            modules.get(str(name)),
            steps,
        )
    return EditorContext(months, references, frozenset(bdq_process_names(tables, dropped)))


def _module_counts(frame: pd.DataFrame | None, dropped: Collection[str]) -> dict[str, float]:
    """공정마다 0 보다 큰 모듈수가 한 값이면 그 값(모듈수 기본값)."""
    if frame is None or "공정" not in frame.columns or "모듈수" not in frame.columns:
        return {}
    names = frame["공정"].astype("string").str.strip()
    values = pd.to_numeric(frame["모듈수"], errors="coerce")
    found: dict[str, set[float]] = {}
    for name, value in zip(names, values, strict=True):
        if pd.isna(name) or str(name) in dropped or pd.isna(value) or not value > 0:
            continue
        found.setdefault(str(name), set()).add(float(value))
    return {name: next(iter(counts)) for name, counts in found.items() if len(counts) == 1}


def _reference(context: EditorContext, reference: str) -> ReferenceChoice | None:
    """합치기(`follow_routes`)처럼 strip 이름으로 찾고 없으면 대소문자를 무시해 찾는다."""
    choice = context.references.get(reference)
    if choice is not None:
        return choice
    folded = reference.casefold()
    return next(
        (item for name, item in context.references.items() if name.casefold() == folded), None
    )


def reference_choices(
    context: EditorContext, model: EditorModel, *, basis: str | None = None
) -> tuple[ReferenceChoice, ...]:
    """고를 수 있는 참조공정 — 지금 편집기 줄 이름(대소문자 무시 — V-06)과 같은 공정은 빼고,
    `basis` 를 주면 그 소요기준만(R-02)."""
    own = {_text(line.fields.name).casefold() for line in model.lines}
    wanted = None if basis is None else _basis(basis)
    return tuple(
        choice
        for name, choice in sorted(context.references.items())
        if name.casefold() not in own and (wanted is None or choice.basis == wanted)
    )


def line_defaults(context: EditorContext, reference: str) -> LineFields:
    """참조공정을 고른 새 줄의 기본값 — 소요기준 · Area · 모듈수 · 첫 (STEP, MCP) 조합, 시작월 = 첫
    계획 월, 끝월 빈칸(제안 e · f · 결정3). 후보에 없으면 참조공정과 시작월만."""
    first = context.months[0] if context.months else None
    choice = _reference(context, _text(reference))
    if choice is None:
        return LineFields(reference=_text(reference), start=first)
    step, mcp = choice.steps[0] if choice.steps else ("", "")
    return LineFields(
        area=choice.area or "",
        basis=choice.basis,
        modules=choice.modules,
        reference=choice.name,
        step=step,
        mcp=mcp,
        start=first,
    )


@dataclass(frozen=True)
class FollowGroup:
    """따라올 줄 한 묶음 — (제품정보, Stack, CUSTOM, WF 구분)의 줄 수 · 첫 달 · 끝 달 · 셈에
    드나."""

    product: str
    stack: str
    custom: str
    wf: str
    rows: int
    first: int
    last: int
    counted: bool


@dataclass(frozen=True)
class FollowPreview:
    """따라가기 미리보기(결정2 — 읽기 전용) — 줄 수 · Buffer 밖 수 · 묶음 · 이어받지 못한 까닭.
    수는 합치기(`ProcessOutcome.route_rows` · `inherited_uncounted`)와 같은 몸통에서 온다."""

    rows: int
    uncounted: int
    groups: tuple[FollowGroup, ...]
    refused: tuple[str, str] | None

    @property
    def products(self) -> int:
        return len({(group.product, group.stack) for group in self.groups})


def follow_preview(
    tables: Mapping[str, pd.DataFrame], reference: str, basis: str, period: Period
) -> FollowPreview:
    """참조공정 · 소요기준 · 경로 기간으로 따라올 줄을 센다(`follow_routes` — 걷은 표를 넘긴다)."""
    found = follow_routes(tables, reference, _basis(basis), period)
    groups: list[FollowGroup] = []
    if not found.rows.empty:
        keys = ["제품정보", "Stack", "CUSTOM", "WF 구분"]
        frame = found.rows.assign(
            **{key: found.rows[key].astype("string").fillna("") for key in keys}
        )
        for values, group in frame.groupby(keys, sort=True):
            product, stack, custom, wf = (str(value) for value in values)
            months = group["생산계획년월"].astype("int64")
            counted = _basis(basis) != "PKG" or wf.strip().casefold() == BUFFER_WORD
            groups.append(
                FollowGroup(
                    product,
                    stack,
                    custom,
                    wf,
                    len(group),
                    int(months.min()),
                    int(months.max()),
                    counted,
                )
            )
    return FollowPreview(len(found.rows), found.uncounted, tuple(groups), found.refused)
