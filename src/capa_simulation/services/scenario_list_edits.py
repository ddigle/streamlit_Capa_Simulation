# Purpose: 시나리오 목록 초안의 op 접기 · 저장본 맞추기 · 막힘 판정 · 표 data · 저장 계획을 둔다.

"""시나리오 관리 › 목록 관리 표의 판정(streamlit · duckdb · persistence 를 부르지 않는다).

브라우저 표(`components/scenario_list_grid`)는 고른 것과 고친 것을 상태 값 `outbox` 로 보내고,
파이썬은 그 op 를 초안(`ListDraft`)에 접는다(`fold_ops`). 고침은 행 id 로 든다 — 차례가 바뀌어도,
다른 시나리오를 열어도 그 줄에 붙어 있다.

- **이름은 비교 후 쓰기다.** `seen` 은 브라우저가 그 칸을 처음 고칠 때 든 이름 — 사용자가 **본**
  이름이다. 회차가 더 돌아도 바뀌지 않아, 남이 먼저 바꾼 이름을 알림 없이 덮지 않는다(`write_guard`
  「본 값」).
- **차례도 본 차례와 대조한다.** `move` 의 `token` 이 지난 회차에 그린 저장 차례의 지문과 같을 때만
  끼워 넣고, 처음 옮길 때의 저장 차례를 `order_base` 로 적는다.
- **세대(`base`)는 초안을 통째로 갈아 끼울 때만 오른다** — 저장 성공 · 모두 버리기. 옛 세대의 고침은
  반영하지 않고 세어 알린다(`FoldResult.dropped`). 세션 표지(`session`)를 함께 실어 세션이 바뀐 뒤
  프런트가 다시 보낸 옛 값이 되살지 않는다.
- **지금 저장본에 맞추기**(`reconcile`)는 회차마다 한다 — 사라진 줄의 고침을 세어 빼고, 지금 이름과
  같아진 고침을 빼고(`settled` — 끊긴 첫 저장의 뒷정리를 여기서 잇는다), 고친 차례를 지금 행에
  맞춘다.
- **막힘 판정**(`list_problems`)은 저장소가 거부할 것을 미리 보이는 몫이고 끝 판정은 저장소다. 같은
  글을 쓰도록 규칙 글을 `ListRules` 로 받는다(이 계층은 저장소를 부르지 않는다).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final, Literal

from capa_simulation.services.grid_outbox import pending_ops
from capa_simulation.services.korean_particle import with_direction_particle

SCENARIO_LABEL: Final = "시나리오명"
REVISION_LABEL: Final = "리비전명"
NameKind = Literal["scenario", "revision"]


@dataclass(frozen=True)
class NameEdit:
    """이름 한 칸의 고침 — 처음 고칠 때 본 이름(비교 후 쓰기 대상), 앞뒤 공백을 뗀 새 이름."""

    seen: str
    text: str


@dataclass(frozen=True)
class ListDraft:
    """목록 관리의 미저장 초안 한 벌. 모두 행 id 로 적는다.

    `order` 는 고친 화면 차례(저장 차례 그대로면 None), `order_base` 는 순서를 처음 고칠 때 본 저장
    차례다. `applied` 는 마운트 → 반영한 마지막 seq — 초안과 한 칸에 두어 접기가 끊겨도 「반영했다고
    적었는데 초안은 옛것」 꼴이 없다. `opened` · `picked` 는 연 시나리오 · 고른 리비전이다.
    """

    session: str = ""
    generation: int = 0
    applied: Mapping[str, int] = field(default_factory=dict)
    scenarios: Mapping[str, NameEdit] = field(default_factory=dict)
    revisions: Mapping[str, NameEdit] = field(default_factory=dict)
    order: tuple[str, ...] | None = None
    order_base: tuple[str, ...] | None = None
    opened: str | None = None
    picked: str | None = None


@dataclass(frozen=True)
class SavedRevision:
    """고친 리비전의 지금 값 — 번호 · 이름 · 소속 · 소속 시나리오가 활성인가 · 공식 지정 번호."""

    revision_id: str
    no: int
    name: str
    scenario_id: str
    active: bool = True
    release_no: int | None = None


@dataclass(frozen=True)
class SavedList:
    """그 회차에 읽은 저장본(평범한 값만). `all_names` 는 보관본까지(이름 겹침 판정)."""

    order: tuple[str, ...]
    names: Mapping[str, str]
    all_names: Mapping[str, str] = field(default_factory=dict)
    revisions: Mapping[str, SavedRevision] = field(default_factory=dict)


@dataclass(frozen=True)
class ListRules:
    """저장소와 같은 글을 쓰기 위한 규칙 글 — 이 계층은 저장소를 부르지 않는다."""

    duplicate: str
    order: str
    moved: Callable[[str], str]
    empty: Callable[[str], str]


@dataclass(frozen=True)
class FoldResult:
    """op 접기 결과. `dropped` 는 옛 세대라 반영하지 않은 op 수, `order_refused` 는 차례 지문이 달라
    거절한 `move` 가 있었다는 표지, `opened` 는 줄을 연 op 가 있었다는 표지(오른쪽 칸을 편다),
    `to_detail` 은 「저장 전 변경」 안 이름 누름처럼 「상세」 로 돌릴 때다."""

    draft: ListDraft
    dropped: int = 0
    order_refused: bool = False
    opened: bool = False
    to_detail: bool = False


@dataclass(frozen=True)
class SettledName:
    """지금 이름과 같아져 초안에서 뺀 고침 — (본 이름, 새 이름) 이 제 저장 짝이면 끊긴 저장이다."""

    kind: NameKind
    row_id: str
    seen: str
    text: str


@dataclass(frozen=True)
class Reconciled:
    """저장본에 맞춘 결과. `gone` 은 사라진 줄의 고침 수."""

    draft: ListDraft
    gone: int = 0
    settled: tuple[SettledName, ...] = ()


@dataclass(frozen=True)
class ListProblems:
    """막힘 — 줄 id → 까닭, 목록 전체의 까닭."""

    scenarios: Mapping[str, str] = field(default_factory=dict)
    revisions: Mapping[str, str] = field(default_factory=dict)
    order: str | None = None

    def count(self) -> int:
        return len(self.scenarios) + len(self.revisions) + (1 if self.order else 0)


@dataclass(frozen=True)
class ChangeCounts:
    """「저장 전 변경」 수 넷."""

    scenario: int = 0
    order: int = 0
    revision: int = 0
    blocked: int = 0


@dataclass(frozen=True)
class SavePlan:
    """저장 한 번의 내용 — (본 이름, 새 이름), 새 차례 · 그 본 차례. `settled` 는 이미 쓰인 제
    저장의 고침(끊긴 첫 저장 — 쓰지 않고 뒷정리만 잇는다)."""

    scenario_renames: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    revision_renames: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    order: tuple[str, ...] | None = None
    order_base: tuple[str, ...] | None = None
    settled: tuple[SettledName, ...] = ()

    @property
    def writes(self) -> bool:
        return bool(self.scenario_renames or self.revision_renames or self.order is not None)

    @property
    def done(self) -> bool:
        """이 저장으로 일어난 일이 있는가(쓰기 또는 끊긴 첫 저장의 뒷정리)."""
        return self.writes or bool(self.settled)

    def scenario_names(self) -> dict[str, str]:
        """이름이 바뀐 시나리오 — id → 새 이름(이미 쓰인 것 포함)."""
        names = {row_id: text for row_id, (_, text) in self.scenario_renames.items()}
        names.update({s.row_id: s.text for s in self.settled if s.kind == "scenario"})
        return names

    def revision_names(self) -> dict[str, str]:
        """이름이 바뀐 리비전 — id → 새 이름(이미 쓰인 것 포함)."""
        names = {row_id: text for row_id, (_, text) in self.revision_renames.items()}
        names.update({s.row_id: s.text for s in self.settled if s.kind == "revision"})
        return names


@dataclass(frozen=True)
class ScenarioFacts:
    """목록 표 값 칸 — 원천 코드, 최신 리비전, 공식버전, 최근 수정."""

    source_code: str = ""
    latest: str = ""
    official: str = ""
    updated: str = ""


@dataclass(frozen=True)
class RevisionFacts:
    """리비전 표 한 줄 — 번호 · 저장 이름 · 상태 · 값 줄(메모 · 저장일 · 부모)."""

    revision_id: str
    no: int
    name: str
    status: str = ""
    memo: str = ""
    created: str = ""
    parent: str = ""


def draft_base(draft: ListDraft) -> str:
    """브라우저에 보내는 세대 — 세션 표지 + 세대."""
    return f"{draft.session}:{draft.generation}"


def has_edits(draft: ListDraft) -> bool:
    """저장하지 않은 이름 · 차례 고침이 있는가."""
    return bool(draft.scenarios or draft.revisions or draft.order is not None)


def edit_count(draft: ListDraft) -> int:
    """「저장 전 변경 n건」 — 이름 한 칸이 한 건, 차례는 묶어 한 건."""
    return len(draft.scenarios) + len(draft.revisions) + (1 if draft.order is not None else 0)


def cleared(draft: ListDraft) -> ListDraft:
    """고침 · 차례를 비우고 세대를 올린다(저장 성공 · 모두 버리기). 연 시나리오 · 고름은 남는다."""
    return replace(
        draft,
        generation=draft.generation + 1,
        scenarios={},
        revisions={},
        order=None,
        order_base=None,
    )


def order_token(order: Sequence[str]) -> str:
    """저장 차례의 지문 — 브라우저가 `move` 에 실어 온다."""
    return hashlib.sha1("\n".join(order).encode("utf-8")).hexdigest()[:8]


def move_before(order: Sequence[str], row_id: str, before: str | None) -> tuple[str, ...]:
    """`row_id` 를 `before` 앞으로 끼워 넣는다(None · 모르는 줄이면 끝). 없는 줄을 옮기면 그대로다.
    브라우저 `moveBefore` 와 같은 답이다(시험이 대 본다)."""
    if row_id not in order:
        return tuple(order)
    rest = [item for item in order if item != row_id]
    if before is None or before not in rest:
        return (*rest, row_id)
    position = rest.index(before)
    return (*rest[:position], row_id, *rest[position:])


def table_rows(draft: ListDraft, saved_order: Sequence[str]) -> tuple[str, ...]:
    """화면 행 차례 — 순서를 고쳤으면 그 차례, 아니면 저장 차례."""
    return draft.order if draft.order is not None else tuple(saved_order)


def _name_op(draft: ListDraft, op: Mapping[str, Any]) -> ListDraft:
    kind, row_id, text, seen = op.get("kind"), op.get("id"), op.get("text"), op.get("seen")
    if kind not in ("scenario", "revision"):
        return draft
    if not isinstance(row_id, str) or not isinstance(text, str) or not isinstance(seen, str):
        return draft
    edits = dict(draft.scenarios if kind == "scenario" else draft.revisions)
    held = edits.get(row_id)
    first_seen = held.seen if held is not None else seen
    typed = text.strip()
    if typed == first_seen:
        edits.pop(row_id, None)
    else:
        edits[row_id] = NameEdit(first_seen, typed)
    return (
        replace(draft, scenarios=edits) if kind == "scenario" else replace(draft, revisions=edits)
    )


def _move_op(
    draft: ListDraft, op: Mapping[str, Any], shown_order: Sequence[str]
) -> tuple[ListDraft, bool]:
    """`move` 하나 — (초안, 거절됐는가). 본 차례의 지문이 다르면 그 op 만 거절한다."""
    row_id, before, token = op.get("id"), op.get("before"), op.get("token")
    if not isinstance(row_id, str) or not (before is None or isinstance(before, str)):
        return draft, False
    if token != order_token(shown_order):
        return draft, True
    rows = table_rows(draft, shown_order)
    moved = move_before(rows, row_id, before)
    if moved == tuple(shown_order):
        return replace(draft, order=None, order_base=None), False
    base = draft.order_base if draft.order is not None else tuple(shown_order)
    return replace(draft, order=moved, order_base=base), False


def _revert_op(draft: ListDraft, op: Mapping[str, Any]) -> ListDraft:
    kind, row_id = op.get("kind"), op.get("id")
    if kind == "order":
        return replace(draft, order=None, order_base=None)
    if kind == "scenario" and isinstance(row_id, str):
        return replace(
            draft, scenarios={key: edit for key, edit in draft.scenarios.items() if key != row_id}
        )
    if kind == "revision" and isinstance(row_id, str):
        return replace(
            draft, revisions={key: edit for key, edit in draft.revisions.items() if key != row_id}
        )
    return draft


def fold_ops(
    draft: ListDraft, outboxes: Iterable[object], shown_order: Sequence[str]
) -> FoldResult:
    """마운트들의 출납을 초안에 접는다. `shown_order` 는 지난 회차에 그린 저장 차례다.

    같은 출납이 여러 회차에 다시 와도 한 번이다(`applied`). 고침 op 의 `base` 가 지금 세대와 다르면
    반영하지 않고 센다 — `open` · `pick` 은 세대를 보지 않는다(고름은 초안을 바꾸지 않는다). 꼴이
    다른 op 는 세지 않고 버린다.
    """
    ops, applied = pending_ops(outboxes, draft.applied)
    base = draft_base(draft)
    folded = replace(draft, applied=applied)
    dropped = 0
    refused = False
    opened = False
    to_detail = False
    for op in ops:
        name = op.get("op")
        if name in ("name", "move", "revert"):
            if op.get("base") != base:
                dropped += 1
            elif name == "name":
                folded = _name_op(folded, op)
            elif name == "revert":
                folded = _revert_op(folded, op)
            else:
                folded, rejected = _move_op(folded, op, shown_order)
                refused = refused or rejected
        elif name == "open":
            row_id = op.get("id")
            if isinstance(row_id, str) and row_id:
                # 이미 연 줄을 다시 눌러도 고름은 남는다 — 씨앗은 처음 볼 때만 고른다.
                picked = folded.picked if row_id == folded.opened else None
                folded = replace(folded, opened=row_id, picked=picked)
                opened = True
                to_detail = to_detail or op.get("detail") is True
        elif name == "pick":
            owner, row_id = op.get("owner"), op.get("id")
            if isinstance(row_id, str) and row_id and owner == folded.opened:
                folded = replace(folded, picked=row_id)
    return FoldResult(folded, dropped, refused, opened, to_detail)


def reconcile(
    draft: ListDraft, saved: SavedList, *, preferred_open: str | None = None
) -> Reconciled:
    """초안을 지금 저장본에 맞춘다.

    사라진 줄(보관 · 삭제된 시나리오와 그 리비전)의 고침은 빼고 센다. 새 이름이 지금 이름과 같아진
    고침은 쓸 것이 없어 빼고 `settled` 로 돌려준다. 고친 차례는 지금 행에 맞추고(새 행은 끝), 저장
    차례와 같아지면 순서 고침이 없는 것이다. 연 시나리오가 없거나 사라졌으면 `preferred_open`(올라와
    있는 시나리오) 또는 맨 위 줄을 연다 — 오른쪽 칸이 빈 채 서지 않는다.
    """
    gone = 0
    settled: list[SettledName] = []
    scenarios: dict[str, NameEdit] = {}
    for row_id, edit in draft.scenarios.items():
        current = saved.names.get(row_id)
        if current is None:
            gone += 1
        elif edit.text == current:
            settled.append(SettledName("scenario", row_id, edit.seen, edit.text))
        else:
            scenarios[row_id] = edit
    revisions: dict[str, NameEdit] = {}
    for row_id, edit in draft.revisions.items():
        revision = saved.revisions.get(row_id)
        if revision is None or not revision.active:
            gone += 1
        elif edit.text == revision.name:
            settled.append(SettledName("revision", row_id, edit.seen, edit.text))
        else:
            revisions[row_id] = edit
    order = draft.order
    if order is not None:
        present = set(saved.order)
        kept = [row_id for row_id in order if row_id in present]
        known = set(kept)
        order = (*kept, *(row_id for row_id in saved.order if row_id not in known))
        if order == saved.order:
            order = None
    opened = draft.opened
    picked = draft.picked
    if opened not in saved.names:
        rows = order if order is not None else saved.order
        fallback = preferred_open if preferred_open in saved.names else None
        opened = fallback if fallback is not None else (rows[0] if rows else None)
        picked = None
    fitted = replace(
        draft,
        scenarios=scenarios,
        revisions=revisions,
        order=order,
        order_base=draft.order_base if order is not None else None,
        opened=opened,
        picked=picked,
    )
    return Reconciled(fitted, gone, tuple(settled))


def list_problems(draft: ListDraft, saved: SavedList, rules: ListRules) -> ListProblems:
    """저장소가 거부할 것 — 빈 이름, 남이 먼저 바꾼 이름, 이 저장이 끝난 뒤의 이름으로 겹치는
    시나리오명 (보관본 포함 — 맞바꾸기는 된다), 남이 바꾼 차례. 리비전명 겹침은 막힘이
    아니다(번호가 가른다)."""
    scenarios: dict[str, str] = {}
    final = dict(saved.all_names or saved.names)
    labels: dict[str, str] = {}
    for row_id, edit in draft.scenarios.items():
        current = saved.names.get(row_id)
        if current is None:
            continue
        if edit.seen != current:
            scenarios[row_id] = rules.moved(current)
        elif not edit.text:
            scenarios[row_id] = rules.empty(SCENARIO_LABEL)
        else:
            labels[row_id] = edit.text
            final[row_id] = edit.text
    for row_id, label in labels.items():
        if any(other != row_id and name == label for other, name in final.items()):
            scenarios[row_id] = rules.duplicate
    revisions: dict[str, str] = {}
    for row_id, edit in draft.revisions.items():
        revision = saved.revisions.get(row_id)
        if revision is None:
            continue
        if edit.seen != revision.name:
            revisions[row_id] = rules.moved(revision.name)
        elif not edit.text:
            revisions[row_id] = rules.empty(REVISION_LABEL)
    order = None
    if draft.order is not None and draft.order_base != saved.order:
        order = rules.order
    return ListProblems(scenarios, revisions, order)


def moved_rows(draft: ListDraft, saved_order: Sequence[str]) -> int:
    """저장 차례와 자리가 다른 줄 수."""
    if draft.order is None:
        return 0
    return sum(
        1 for shown, stored in zip(draft.order, saved_order, strict=False) if shown != stored
    )


def change_counts(draft: ListDraft, saved: SavedList, problems: ListProblems) -> ChangeCounts:
    """수 넷 — 시나리오명 · 순서(자리가 달라진 줄) · 리비전명 · 막힘."""
    return ChangeCounts(
        scenario=len(draft.scenarios),
        order=moved_rows(draft, saved.order),
        revision=len(draft.revisions),
        blocked=problems.count(),
    )


def save_plan(draft: ListDraft, saved: SavedList) -> SavePlan:
    """맞춘 초안 → 저장 내용. 초안은 `reconcile` 을 지난 것이다."""
    return SavePlan(
        scenario_renames={
            row_id: (edit.seen, edit.text)
            for row_id, edit in draft.scenarios.items()
            if row_id in saved.names
        },
        revision_renames={
            row_id: (edit.seen, edit.text)
            for row_id, edit in draft.revisions.items()
            if row_id in saved.revisions
        },
        order=draft.order,
        order_base=draft.order_base,
    )


def draft_fingerprint(draft: ListDraft) -> tuple[object, ...]:
    """저장 입력의 지문 — `reconcile` **앞** 초안으로 짓는다. 첫 콜백이 쓴 뒤 초안을 비우기 전에
    끊기면 둘째 누름의 초안이 같아 저장소에 다시 가지 않고 첫 결과로 뒷정리를
    잇는다(`write_guard.save_once`). 맞춘 뒤로 지으면 이미 쓰인 이름이 빠져 같은 누름이 다른 지문이
    된다."""
    return (
        tuple(sorted((key, edit.seen, edit.text) for key, edit in draft.scenarios.items())),
        tuple(sorted((key, edit.seen, edit.text) for key, edit in draft.revisions.items())),
        draft.order,
        draft.order_base,
    )


def official_label(
    scenario_id: str,
    official_by_scenario: Mapping[str, tuple[int, int]],
    latest_official_scenario: str | None,
) -> str:
    """그 시나리오의 최신 공식버전과 그 리비전(「v3 · r3」). 저장소 전체의 최신이면 「· 최신」."""
    release = official_by_scenario.get(scenario_id)
    if release is None:
        return ""
    label = f"v{release[0]} · r{release[1]}"
    return f"{label} · 최신" if scenario_id == latest_official_scenario else label


def revision_status_label(release_no: int | None, *, loaded: bool, virtual_count: int) -> str:
    """리비전 표 「상태」 칸 — 「공식 v3 · 올라와 있음 · 가상 2」(해당하는 것만)."""
    parts = []
    if release_no is not None:
        parts.append(f"공식 v{release_no}")
    if loaded:
        parts.append("올라와 있음")
    if virtual_count:
        parts.append(f"가상 {virtual_count}")
    return " · ".join(parts)


def official_rename_note(release_no: int) -> str:
    """이름을 고치는 중인 공식 리비전의 풍선 — 공식버전명은 그대로라는 것."""
    return (
        f"{with_direction_particle(f'공식 v{release_no}')} 지정된 리비전입니다 — "
        "공식버전명은 바뀌지 않습니다."
    )


def scenarios_payload(
    draft: ListDraft,
    saved: SavedList,
    problems: ListProblems,
    facts: Mapping[str, ScenarioFacts],
) -> dict[str, Any]:
    """목록 표 data. 행은 초안 차례다. `saved` 는 이름이 고쳐졌을 때만, `place` 는 자리가 다를 때만
    싣는다(크기 — 줄이 수백 개여도 data 가 부풀지 않는다)."""
    rows = []
    places = {row_id: index for index, row_id in enumerate(saved.order, start=1)}
    for index, row_id in enumerate(table_rows(draft, saved.order), start=1):
        fact = facts.get(row_id, ScenarioFacts())
        stored = saved.names.get(row_id, "")
        edit = draft.scenarios.get(row_id)
        row: dict[str, Any] = {
            "id": row_id,
            "name": edit.text if edit is not None else stored,
            "latest": fact.latest,
            "official": fact.official,
            "updated": fact.updated,
        }
        if edit is not None:
            row["saved"] = stored
        if places.get(row_id) != index:
            row["place"] = places.get(row_id)
        if row_id in problems.scenarios:
            row["problem"] = problems.scenarios[row_id]
        rows.append(row)
    return {
        "mode": "scenarios",
        "orderToken": order_token(saved.order),
        "open": draft.opened,
        "rows": rows,
    }


def revisions_payload(
    draft: ListDraft,
    *,
    owner: str,
    title: str,
    sub: str,
    facts: Sequence[RevisionFacts],
    problems: ListProblems,
) -> dict[str, Any]:
    """리비전 표 data — 값 줄(메모 · 저장일 · 부모)도 같은 마운트가 그려 줄을 누르면 회차 전에
    바뀐다."""
    rows = []
    for fact in facts:
        edit = draft.revisions.get(fact.revision_id)
        row: dict[str, Any] = {
            "id": fact.revision_id,
            "no": f"r{fact.no}",
            "name": edit.text if edit is not None else fact.name,
            "status": fact.status,
            "memo": fact.memo,
            "created": fact.created,
            "parent": fact.parent,
        }
        if edit is not None:
            row["saved"] = fact.name
        if fact.revision_id in problems.revisions:
            row["problem"] = problems.revisions[fact.revision_id]
        rows.append(row)
    return {
        "mode": "revisions",
        "owner": owner,
        "title": title,
        "sub": sub,
        "picked": draft.picked,
        "rows": rows,
    }


def changes_payload(
    draft: ListDraft, saved: SavedList, problems: ListProblems, counts: ChangeCounts
) -> dict[str, Any]:
    """「저장 전 변경」 data — 수 넷, 시나리오별 묶음(옛 값 → 새 값), 차례 한 줄. 열려 있지 않은
    시나리오의 줄도 다 보인다(되돌리고 이름을 눌러 열 수 있다)."""
    lines: dict[str, list[dict[str, Any]]] = {}
    for row_id, edit in draft.scenarios.items():
        line: dict[str, Any] = {
            "kind": "scenario",
            "id": row_id,
            "label": SCENARIO_LABEL,
            "before": saved.names.get(row_id, edit.seen),
            "after": edit.text,
        }
        if row_id in problems.scenarios:
            line["problem"] = problems.scenarios[row_id]
        lines.setdefault(row_id, []).append(line)
    for row_id, edit in draft.revisions.items():
        revision = saved.revisions.get(row_id)
        if revision is None:
            continue
        line = {
            "kind": "revision",
            "id": row_id,
            "label": f"{REVISION_LABEL} r{revision.no}",
            "before": revision.name,
            "after": edit.text,
        }
        if row_id in problems.revisions:
            line["problem"] = problems.revisions[row_id]
        if revision.release_no is not None:
            line["mark"] = f"공식 v{revision.release_no}"
            line["note"] = official_rename_note(revision.release_no)
        lines.setdefault(revision.scenario_id, []).append(line)
    groups = []
    for row_id in table_rows(draft, saved.order):
        if row_id in lines:
            current = draft.scenarios.get(row_id)
            groups.append(
                {
                    "id": row_id,
                    "name": current.text if current else saved.names.get(row_id, ""),
                    "lines": lines[row_id],
                }
            )
    order: dict[str, Any] = {"moved": counts.order}
    if problems.order:
        order["problem"] = problems.order
    return {
        "mode": "changes",
        "counts": {
            "scenario": counts.scenario,
            "order": counts.order,
            "revision": counts.revision,
            "blocked": counts.blocked,
        },
        "groups": groups,
        "order": order,
    }
