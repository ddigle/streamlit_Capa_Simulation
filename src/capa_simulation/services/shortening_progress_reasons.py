# Purpose: 누적 진척 기록 주마다 바로 앞 기록 주와 넣기 스냅숏을 견줘 오르내린 까닭 항목을 낸다.

"""누적 진척 「주차별」 까닭(2026-11-20 · 21 사용자 보드 답 — 꼴 중간-1 「점 곁 곧은 꼬리표」,
재료 「자동 + 사람이 고침」 의 1단계 자동).

**스냅숏**(`ProgressSnapshotDraft` · `ProgressSnapshot`)은 「이번 주 값 넣기」 로 기록을 저장할
때 그 화면이 보던 호기 표다 — 고른 목표의 계획(`LevelPlan.units`)에서 범위 공정의 당긴 호기 ·
추가N 행과 범위 공정 차례 · Cut-off, 현재 일정 기준 · 목표 확보율 · 그날 오늘 · 조회 달 · 계산의
출처. 기록 값은 사람이 적은 수 그대로이고(「한 줄 기록」 을 넓힘 — 넣기를 쓴 주에만
근거가 곁에 남는다), 손으로 적은 주는 스냅숏이 없다. 저장은 설비 DB `0037`
(`persistence/shortening_progress_snapshot_store.py`)이다.

**까닭 항목**(`explain_week_changes`)은 저장하지 않고 그릴 때 센다 — 기록을 차례로 보며 바로 앞
기록 주와만 짝짓고(건너뛴 주는 그 사이 전체가 한 구간), 두 주 모두 스냅숏이 있을 때만 낸다
(하나라도 없으면 항목 없음 — 0 이 아니다, 설계 규칙 UI-DAT-06). 짝짓기는 진척 비교와 같은
`compare_progress` 다.

- **조건 먼저** — 두 스냅숏의 현재 일정 기준이나 목표 확보율이 다르면 호기별로 가르지 않고
  「기준 바뀜」 한 항목(스냅숏 합 차이)이다(진척 비교 Q14 (가)와 같은 까닭 — 기준 차이가 진척으로
  둔갑하지 않게).
- **당긴 호기 짝** — 확보 몫 s(기존 Qual 이동)와 필요 몫 n(−목표 Qual 이동) 가운데 |몫| 이 큰 쪽
  꼬리표에 그 호기의 단축일수 증감 전체를 싣는다(같으면 확보 쪽) — 「Qual 당김」 · 「Qual 밀림」 ·
  「필요 늦춰짐」 · 「필요 당겨짐」. 몫은 꼬리표를 고르는 데만 쓰고 양은 늘 `단축일수` 차이다.
- **한쪽에만** — 이 주에만 있는 당긴 호기는 「신규 필요」(+이 주 일수), 앞 주에만 있는 것은
  「해소」(−앞 일수). 한쪽 범위에만 있는 공정의 호기는 「범위 바뀜」 한 항목이다. 한 공정에 해소와
  신규 필요가 함께면(호기 이름이 바뀌었을 수 있음 — `rename_suspects`) 둘 다 항목으로 두되 그림
  꼬리표에는 올리지 않는다(`WeekChange.drawn` — 풍선만).
- **진척 아님** — 앞 주 필요 시점이 이 주 오늘보다 앞이면 「기한 지남」, 한 시점에만 현재 일정이
  없는 호기(Static 의 남는 호기)는 「기준 바뀜」(진척 비교의 같은 이름 상태)이다.
- **손 고침** — (이 주 기록 − 이 주 스냅숏 합) − (앞 기록 − 앞 스냅숏 합). 넣기 뒤 수를 고쳤거나
  나중에 손으로 고친 몫이다. 그래서 항목 합은 화면 합계가 아니라 기록 차이와 맞는다.
- **맞춤** — 항목 합이 기록 차이와 정수로 같아야 그린다(`WeekChange.balanced`). 어긋나면 글을
  싣지 않는다(설계 규칙 UI-DAT-07).

추가N(구분 「신규」)은 일수가 없어 합에 넣지 않고 대수 변화만 덧말이다. 두 스냅숏의 계산
입력(조회 달 · 범위 공정의 Cut-off · 시나리오 · 설비 일정 · 공통 대장 리비전)이 다르면 그것도 합 밖
덧말이다(입력 바뀜 — 그 차이로 생긴 호기 몫이 진척 항목에 섞여 있을 수 있음을 풍선이 말한다,
진척 비교 「조회 달 다름」 과 같은 결). 공정은 원본 이름으로 묶고 화면이 표시명으로
바꾼다(UI-DAT-10). 이 모듈은 Streamlit · DB 를 모른다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from itertools import pairwise

import pandas as pd

from capa_simulation.services.frame_contracts import blank_cell
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.required_shortening import KIND_NEW, KIND_SHORTENED
from capa_simulation.services.shortening_baseline import BaselineProvenance
from capa_simulation.services.shortening_progress import (
    PROGRESS_LAPSED,
    PROGRESS_NEW,
    PROGRESS_OUT_OF_SCOPE,
    PROGRESS_REBASED,
    PROGRESS_RESOLVED,
    compare_progress,
    rename_suspects,
    scope_difference,
)
from capa_simulation.services.shortening_progress_log import ProgressLog, ProgressWeek

__all__ = [
    "DRAWN_ITEMS_MAX",
    "LISTED_ITEMS_MAX",
    "PROGRESS_TAGS",
    "SNAPSHOT_UNIT_COLUMNS",
    "TAG_BASIS",
    "TAG_LAPSED",
    "TAG_MANUAL",
    "TAG_NEED_EARLIER",
    "TAG_NEED_LATER",
    "TAG_NEW",
    "TAG_OTHER",
    "TAG_QUAL_EARLIER",
    "TAG_QUAL_LATER",
    "TAG_RESOLVED",
    "TAG_SCOPE",
    "ProgressSnapshot",
    "ProgressSnapshotDraft",
    "ReasonItem",
    "WeekChange",
    "empty_snapshot_units",
    "explain_week_changes",
    "snapshot_digest",
    "snapshot_draft",
    "snapshot_units_total",
]

TAG_QUAL_EARLIER = "Qual 당김"
TAG_QUAL_LATER = "Qual 밀림"
TAG_NEED_LATER = "필요 늦춰짐"
TAG_NEED_EARLIER = "필요 당겨짐"
TAG_NEW = "신규 필요"
TAG_RESOLVED = "해소"
TAG_SCOPE = "범위 바뀜"
TAG_BASIS = "기준 바뀜"
TAG_LAPSED = "기한 지남"
TAG_MANUAL = "손 고침"
TAG_OTHER = "그 밖"

PROGRESS_TAGS = (
    TAG_QUAL_EARLIER,
    TAG_QUAL_LATER,
    TAG_NEED_LATER,
    TAG_NEED_EARLIER,
    TAG_NEW,
    TAG_RESOLVED,
)
"""공정마다 묶는 진척 꼬리표. 그 밖(범위 · 기준 · 기한 · 손 고침)은 항목 하나씩이다."""

_TAG_ORDER = {
    tag: position
    for position, tag in enumerate(
        (*PROGRESS_TAGS, TAG_SCOPE, TAG_BASIS, TAG_LAPSED, TAG_MANUAL, TAG_OTHER)
    )
}

SNAPSHOT_UNIT_COLUMNS = ("공정", "호기", "구분", "기존 Qual", "목표 Qual", "단축일수", "모듈 수")
"""스냅숏 호기 표의 칸 — 진척 비교 짝짓기(`compare_progress`)가 읽는 칸 그대로다. 날짜는 `date`
(빈칸 None), 단축일수 · 모듈 수는 정수(단축일수 빈칸 None)다."""

DRAWN_ITEMS_MAX = 2
"""그림 꼬리표에 올리는 항목 수의 위끝(보드 답 중간-1 「항목 둘까지」)."""

LISTED_ITEMS_MAX = 6
"""풍선에 하나씩 적는 항목 수의 위끝 — 넘으면 앞 다섯과 「그 밖 k건」."""


@dataclass(frozen=True, eq=False)
class ProgressSnapshotDraft:
    """넣기로 남길 화면 호기 표 한 벌(주 · 기록과 잇기 전)."""

    days: int
    """그 화면의 단축 필요일수 합계(`screen_shortening_days`) — 넣기가 칸에 채운 값."""
    level_percent: int
    basis: str
    selected: bool
    today: date
    months: tuple[int, int]
    processes: tuple[str, ...]
    """범위 공정(화면 차례, 원본 이름)."""
    cutoff_days: tuple[int | None, ...]
    """`processes` 와 같은 차례의 Cut-off 일수(모르면 None)."""
    units: pd.DataFrame = field(repr=False)
    """`SNAPSHOT_UNIT_COLUMNS` — 범위 공정의 당긴 호기 · 추가N 행."""
    provenance: BaselineProvenance = BaselineProvenance()
    digest: str = ""
    """같은 수 · 같은 구성이면 같은 글(`snapshot_digest`) — 바뀐 것이 없는 넣기를 가른다."""


@dataclass(frozen=True, eq=False)
class ProgressSnapshot:
    """저장된 스냅숏 — 그 주와, 같은 쓰기 트랜잭션에서 쓴 기록 줄의 저장 시각."""

    week: ProgressWeek
    draft: ProgressSnapshotDraft
    log_updated_at: datetime | None = None
    captured_at: datetime | None = None
    captured_by: str = ""


@dataclass(frozen=True)
class ReasonItem:
    """까닭 항목 하나 — 꼬리표 · 일수(지난 기록 대비 몫) · 대수와 덧말 재료."""

    tag: str
    days: int
    units: int = 0
    process: str | None = None
    """진척 항목의 공정(원본 이름). 범위 · 기준 · 기한 · 손 고침 · 그 밖은 None."""
    parts: tuple[tuple[str, int], ...] = ()
    """범위 바뀜의 공정별 몫(원본 이름, 일수)."""
    note: str = ""
    """풍선 덧말(기준 바뀜의 무엇이 바뀌었나 등)."""
    count: int = 0
    """그 밖의 건수."""

    @property
    def progress(self) -> bool:
        return self.tag in PROGRESS_TAGS


@dataclass(frozen=True)
class WeekChange:
    """기록 한 주의 지난 기록 대비와 그 까닭 항목(차례대로, 0 은 버림)."""

    week: ProgressWeek
    previous: ProgressWeek
    change: int
    items: tuple[ReasonItem, ...]
    balanced: bool
    renamed: tuple[str, ...] = ()
    """당긴 호기의 해소와 신규 필요가 함께 있는 공정 — 호기 이름이 바뀌었을 수 있다(합에는 든다)."""
    virtual: tuple[int, int] | None = None
    """추가N 대수(앞 주, 이 주) — 다를 때만. 일수가 없어 합 밖이다."""
    inputs: tuple[str, ...] = ()
    """두 스냅숏의 조회 달 · 계산 입력(시나리오 · 설비 일정 · 공통 대장 리비전)이 다르면 그 글 —
    합 밖."""
    cutoffs: tuple[tuple[str, int, int], ...] = ()
    """두 범위에 함께 있는 공정의 Cut-off 일수가 다르면 (원본 이름, 앞 주, 이 주) — 둘 다 알 때만,
    합 밖. 화면이 공정 표시명으로 적는다."""

    @property
    def weeks_between(self) -> int:
        return self.previous.weeks_until(self.week)

    @property
    def total(self) -> int:
        return sum(item.days for item in self.items)

    def drawn(self, limit: int = DRAWN_ITEMS_MAX) -> tuple[ReasonItem, ...]:
        """그림 꼬리표에 올릴 항목 — 그 주 변동과 같은 쪽만, 둘째부터는 변동의 1/4 이상일 때만.
        호기 이름이 바뀌었을 수 있는 공정(`renamed`)의 신규 필요 · 해소는 올리지 않는다 — 같은
        설비가 옛 이름 해소 · 새 이름 신규 필요로 갈렸을 수 있어 그림 글로는 근거가 모자란다."""
        if not self.balanced or self.change == 0:
            return ()
        picked: list[ReasonItem] = []
        for item in self.items:
            if (item.days > 0) != (self.change > 0):
                continue
            if item.process in self.renamed and item.tag in (TAG_NEW, TAG_RESOLVED):
                continue
            if picked and abs(item.days) * 4 < abs(self.change):
                continue
            picked.append(item)
            if len(picked) >= limit:
                break
        return tuple(picked)

    def listed(self, limit: int = LISTED_ITEMS_MAX) -> tuple[ReasonItem, ...]:
        """풍선 항목 — `limit` 이하면 전부, 넘으면 앞 `limit − 1` 개와 나머지를 묶은 「그 밖」."""
        if len(self.items) <= limit:
            return self.items
        shown, rest = self.items[: limit - 1], self.items[limit - 1 :]
        other = ReasonItem(TAG_OTHER, sum(item.days for item in rest), count=len(rest))
        return (*shown, other)


def snapshot_units_total(units: pd.DataFrame) -> int:
    """스냅숏 호기 표의 단축 필요일수 합 — 당긴 호기(구분 「단축」)의 단축일수(빈칸 0일)."""
    if units.empty:
        return 0
    chosen = units.loc[units["구분"].eq(KIND_SHORTENED), "단축일수"]
    return int(pd.to_numeric(chosen, errors="coerce").fillna(0).sum())


def snapshot_draft(
    units: pd.DataFrame,
    processes: Sequence[str],
    *,
    level_percent: int,
    basis: str,
    selected: bool,
    today: date,
    months: tuple[int, int],
    cutoff_days: Mapping[str, int] | None = None,
    provenance: BaselineProvenance | None = None,
) -> ProgressSnapshotDraft:
    """넣기로 남길 스냅숏 — 고른 목표의 계획 호기 표(`LevelPlan.units`)에서 범위 공정 행만 새 표로
    옮긴다(넘겨받은 표는 읽기만 한다 — 잠긴 표일 수 있다). 합계는 `screen_shortening_days` 와 같은
    셈이다."""
    scope = tuple(dict.fromkeys(str(process) for process in processes))
    frame = _snapshot_units(units, scope)
    cutoffs = cutoff_days or {}
    draft = ProgressSnapshotDraft(
        days=snapshot_units_total(frame),
        level_percent=int(level_percent),
        basis=str(basis),
        selected=bool(selected),
        today=today,
        months=(int(months[0]), int(months[1])),
        processes=scope,
        cutoff_days=tuple(_whole(cutoffs.get(process)) for process in scope),
        units=frame,
        provenance=provenance or BaselineProvenance(),
    )
    return _with_digest(draft)


def snapshot_digest(draft: ProgressSnapshotDraft) -> str:
    """같은 수 · 같은 구성(목표 · 기준 · 범위 공정 · 호기 행)이면 같은 글. 오늘 · 출처는 넣지
    않는다."""
    rows = sorted(
        (
            str(row["공정"]),
            str(row["구분"]),
            str(row["호기"]),
            _iso(row["기존 Qual"]),
            _iso(row["목표 Qual"]),
            _whole(row["단축일수"]),
            _whole(row["모듈 수"]),
        )
        for row in draft.units.to_dict("records")
    )
    payload = json.dumps(
        [draft.level_percent, draft.basis, list(draft.processes), rows],
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def explain_week_changes(
    log: ProgressLog, snapshots: Mapping[ProgressWeek, ProgressSnapshot]
) -> dict[ProgressWeek, WeekChange]:
    """기록마다(첫 기록 밖) 바로 앞 기록 주와 견준 까닭 — 두 주 모두 그 기록과 함께 쓴 스냅숏이 있을
    때만 낸다. 스냅숏이 그 기록 줄의 저장 시각과 다르면(옛 코드가 그 주를 고침) 없는 것으로 본다."""
    out: dict[ProgressWeek, WeekChange] = {}
    for before, after in pairwise(log.entries):
        past, current = snapshots.get(before.week), snapshots.get(after.week)
        if past is None or current is None:
            continue
        if not _fresh(past, before.updated_at) or not _fresh(current, after.updated_at):
            continue
        out[after.week] = _explain_pair(
            before.week, before.days, past.draft, after.week, after.days, current.draft
        )
    return out


# ---------------------------------------------------------------------- 가름


def _explain_pair(
    previous: ProgressWeek,
    previous_days: int,
    past: ProgressSnapshotDraft,
    week: ProgressWeek,
    days: int,
    current: ProgressSnapshotDraft,
) -> WeekChange:
    change = days - previous_days
    items: list[ReasonItem] = []
    renamed: tuple[str, ...] = ()
    conditions = _condition_notes(past, current)
    order = {
        process: position
        for position, process in enumerate(
            dict.fromkeys((*current.processes, *past.processes, *_unit_processes(past)))
        )
    }
    if conditions:
        moved = snapshot_units_total(current.units) - snapshot_units_total(past.units)
        if moved:
            items.append(ReasonItem(TAG_BASIS, moved, note=" · ".join(conditions)))
    else:
        rows = compare_progress(
            past.units,
            current.units,
            current_processes=current.processes,
            today=current.today,
        )
        items.extend(_unit_items(rows, set(past.processes), order))
        common = [process for process in current.processes if process in set(past.processes)]
        renamed = rename_suspects(rows, common)
    manual = (days - current.days) - (previous_days - past.days)
    if manual:
        items.append(ReasonItem(TAG_MANUAL, manual))
    ordered = tuple(sorted(items, key=lambda item: _item_order(item, order, bool(conditions))))
    return WeekChange(
        week=week,
        previous=previous,
        change=change,
        items=ordered,
        balanced=sum(item.days for item in ordered) == change,
        renamed=renamed,
        virtual=_virtual_counts(past, current),
        inputs=(*_months_notes(past, current), *_input_notes(past.provenance, current.provenance)),
        cutoffs=_cutoff_changes(past, current),
    )


def _unit_items(
    rows: pd.DataFrame, past_scope: set[str], order: Mapping[str, int]
) -> list[ReasonItem]:
    """짝지은 당긴 호기 행을 꼬리표로 가른다 — 진척 항목은 (공정, 꼬리표)로, 범위 · 기준 · 기한은
    항목 하나로 더한다. 증감이 0 인 행 · 항목은 버린다."""
    progress: dict[tuple[str, str], list[int]] = {}
    scope_parts: dict[str, int] = {}
    scope_units = 0
    machine: dict[str, list[int]] = {TAG_BASIS: [0, 0], TAG_LAPSED: [0, 0]}
    for record in rows.to_dict("records"):
        if record["구분"] != KIND_SHORTENED:
            continue
        delta = (_whole(record["현재 단축일수"]) or 0) - (_whole(record["과거 단축일수"]) or 0)
        if delta == 0:
            continue
        process, status = str(record["공정"]), str(record["상태"])
        if status == PROGRESS_OUT_OF_SCOPE or process not in past_scope:
            scope_parts[process] = scope_parts.get(process, 0) + delta
            scope_units += 1
            continue
        if status in (PROGRESS_LAPSED, PROGRESS_REBASED):
            tag = TAG_LAPSED if status == PROGRESS_LAPSED else TAG_BASIS
            machine[tag][0] += delta
            machine[tag][1] += 1
            continue
        if status == PROGRESS_NEW:
            tag = TAG_NEW
        elif status == PROGRESS_RESOLVED:
            tag = TAG_RESOLVED
        else:
            secure = _whole(record["확보 시점 이동(일)"]) or 0
            need = -(_whole(record["필요 시점 이동(일)"]) or 0)
            if abs(secure) >= abs(need):
                tag = TAG_QUAL_EARLIER if delta < 0 else TAG_QUAL_LATER
            else:
                tag = TAG_NEED_LATER if delta < 0 else TAG_NEED_EARLIER
        bucket = progress.setdefault((process, tag), [0, 0])
        bucket[0] += delta
        bucket[1] += 1
    items = [
        ReasonItem(tag, total, units=count, process=process)
        for (process, tag), (total, count) in progress.items()
        if total
    ]
    scope_total = sum(scope_parts.values())
    if scope_total:
        parts = tuple(
            (process, value)
            for process, value in sorted(
                scope_parts.items(), key=lambda pair: order.get(pair[0], len(order))
            )
            if value
        )
        items.append(ReasonItem(TAG_SCOPE, scope_total, units=scope_units, parts=parts))
    for tag, (total, count) in machine.items():
        if total:
            items.append(
                ReasonItem(
                    tag,
                    total,
                    units=count,
                    note="현재 일정 없음 ↔ 있음" if tag == TAG_BASIS else "",
                )
            )
    return items


def _item_order(
    item: ReasonItem, order: Mapping[str, int], conditions: bool
) -> tuple[int, int, int, int, int]:
    """조건 바뀜(기준 · 목표)은 늘 첫 자리, 그다음 |일수| 큰 차례 — 같으면 진척 항목이 앞, 공정
    차례, 꼬리표 차례."""
    first = 0 if conditions and item.tag == TAG_BASIS else 1
    process = order.get(item.process, len(order)) if item.process is not None else len(order)
    return (first, -abs(item.days), 0 if item.progress else 1, process, _TAG_ORDER[item.tag])


def _condition_notes(past: ProgressSnapshotDraft, current: ProgressSnapshotDraft) -> list[str]:
    notes = []
    if past.basis != current.basis:
        notes.append(f"현재 일정 기준 {past.basis} → {current.basis}")
    if past.level_percent != current.level_percent:
        notes.append(f"목표 {past.level_percent}% → {current.level_percent}%")
    return notes


def _virtual_counts(
    past: ProgressSnapshotDraft, current: ProgressSnapshotDraft
) -> tuple[int, int] | None:
    before = int(past.units["구분"].eq(KIND_NEW).sum()) if not past.units.empty else 0
    after = int(current.units["구분"].eq(KIND_NEW).sum()) if not current.units.empty else 0
    return None if before == after else (before, after)


def _months_notes(past: ProgressSnapshotDraft, current: ProgressSnapshotDraft) -> tuple[str, ...]:
    """조회 달이 바뀌었으면 그 글 — 끝 달을 늘리면 그 달 부족으로 새 호기가 들어 「신규 필요」 로
    보일 수 있다(진척 비교 `scope_note` 의 「조회 달 다름」 과 같은 견줌)."""
    difference = scope_difference(
        baseline_months=past.months,
        baseline_processes=past.processes,
        months=current.months,
        processes=current.processes,
    )
    if not difference.months_differ:
        return ()
    before, after = difference.baseline_months, difference.current_months
    return (f"조회 달 {_span(before)} → {_span(after)}",)


def _span(months: tuple[int, int]) -> str:
    return f"{month_label(months[0])}–{month_label(months[1])}"


def _cutoff_changes(
    past: ProgressSnapshotDraft, current: ProgressSnapshotDraft
) -> tuple[tuple[str, int, int], ...]:
    """두 범위에 함께 있는 공정의 Cut-off 가 다른 자리(이 주 범위 차례) — 한쪽이라도 모르면(None)
    바뀜으로 보지 않는다."""
    before = dict(zip(past.processes, past.cutoff_days, strict=False))
    changed = []
    for process, after in zip(current.processes, current.cutoff_days, strict=False):
        previous = before.get(process)
        if previous is None or after is None or previous == after:
            continue
        changed.append((process, previous, after))
    return tuple(changed)


def _input_notes(past: BaselineProvenance, current: BaselineProvenance) -> tuple[str, ...]:
    """계산 입력이 바뀐 자리 — 둘 다 알 때만 견준다(모르는 출처는 바뀜으로 보지 않는다).
    `reference_version` 은 시나리오 리비전 id 에서 나오는 값(`reference_version_for_revision`)이라
    리비전 id 를 모를 때(시나리오 이름표가 없는 세션)만 그 대신 견준다 — 값은 적지 않는다."""
    scenario_known = (
        past.scenario_revision_id is not None and current.scenario_revision_id is not None
    )
    pairs = (
        ("시나리오", past.scenario_revision_id, current.scenario_revision_id,
         past.scenario_revision_no, current.scenario_revision_no)
        if scenario_known
        else ("시나리오", past.reference_version, current.reference_version, None, None),
        ("설비 일정", past.equipment_schedule_revision_ref, current.equipment_schedule_revision_ref,
         past.equipment_schedule_revision_no, current.equipment_schedule_revision_no),
        ("공통 대장", past.equipment_revision_id, current.equipment_revision_id,
         past.equipment_revision_no, current.equipment_revision_no),
    )  # fmt: skip
    notes = []
    for name, before, after, before_no, after_no in pairs:
        if before is None or after is None or before == after:
            continue
        if before_no is not None and after_no is not None:
            notes.append(f"{name} 리비전 r{before_no} → r{after_no}")
        else:
            notes.append(f"{name} 리비전")
    return tuple(notes)


def _fresh(snapshot: ProgressSnapshot, updated_at: datetime | None) -> bool:
    """스냅숏이 지금 기록 줄과 같은 쓰기에서 섰나 — 둘 다 시각이 있을 때만 견준다."""
    if snapshot.log_updated_at is None or updated_at is None:
        return True
    return snapshot.log_updated_at == updated_at


def _unit_processes(draft: ProgressSnapshotDraft) -> Iterable[str]:
    if draft.units.empty:
        return ()
    return (str(process) for process in dict.fromkeys(draft.units["공정"]))


# ---------------------------------------------------------------------- 표


def _snapshot_units(units: pd.DataFrame, scope: Sequence[str]) -> pd.DataFrame:
    if units.empty:
        return empty_snapshot_units()
    chosen = units.loc[units["공정"].isin(list(scope)), list(SNAPSHOT_UNIT_COLUMNS)]
    position = {process: index for index, process in enumerate(scope)}
    records = []
    for record in chosen.to_dict("records"):
        if _day(record["목표 Qual"]) is None:
            # 필요 시점이 없는 줄은 단축일수도 셀 수 없다 — 저장 칸(NOT NULL)에 맞춰 뺀다.
            continue
        records.append(
            {
                "공정": str(record["공정"]),
                "호기": str(record["호기"]),
                "구분": str(record["구분"]),
                "기존 Qual": _day(record["기존 Qual"]),
                "목표 Qual": _day(record["목표 Qual"]),
                "단축일수": _whole(record["단축일수"]),
                "모듈 수": _whole(record["모듈 수"]) or 1,
            }
        )
    records.sort(key=lambda row: position.get(str(row["공정"]), len(position)))
    if not records:
        return empty_snapshot_units()
    frame = pd.DataFrame(records, columns=list(SNAPSHOT_UNIT_COLUMNS))
    for column in ("단축일수", "모듈 수"):
        frame[column] = pd.to_numeric(frame[column]).astype("Int64")
    return frame


def empty_snapshot_units() -> pd.DataFrame:
    """빈 스냅숏 호기 표(`SNAPSHOT_UNIT_COLUMNS`)."""
    frame = pd.DataFrame({column: pd.Series(dtype="object") for column in SNAPSHOT_UNIT_COLUMNS})
    for column in ("단축일수", "모듈 수"):
        frame[column] = frame[column].astype("Int64")
    return frame


def _with_digest(draft: ProgressSnapshotDraft) -> ProgressSnapshotDraft:
    return replace(draft, digest=snapshot_digest(draft))


def _day(value: object) -> date | None:
    if blank_cell(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    stamp = pd.Timestamp(str(value))
    return None if pd.isna(stamp) else stamp.date()


def _iso(value: object) -> str | None:
    day = _day(value)
    return None if day is None else day.isoformat()


def _whole(value: object) -> int | None:
    return None if blank_cell(value) else round(float(str(value)))
