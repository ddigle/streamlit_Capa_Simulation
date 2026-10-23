# Purpose: HOME 주요 Case 슬롯 셋(공식버전·Case1·Case2)의 글자·리비전·상태와 겹침 안내를 정한다.

"""HOME 주요 Case 슬롯.

슬롯은 셋으로 고정이다(2026-10-23 사용자 요청). 슬롯 1 은 **지금 최신 공식버전**이라 따로 지정하지
않고, 슬롯 2·3 은 Preference 에서 Case1·Case2 로 지정한 시나리오·리비전이다(공용 프로필
`app_meta.global_main_cases`, 마이그레이션 0036). 조회 조건 상자의 시나리오로 가지 않고 주요 검토
케이스를 곧바로 보려는 것이다.

Streamlit·DB 를 모른다 — 부르는 쪽이 최신 공식버전·Case 짝 둘·활성 시나리오 목록·그 시나리오들의
리비전 목록을 넘긴다. 모델을 import 하지 않고 읽기 전용 `@property` Protocol 로 쓰는 필드만 요구한다
(`components/profile_caption.py` 와 같은 까닭).

상태는 셋이다 — `ok`(가리키는 리비전이 있다)·`unset`(미지정)·`missing`(가리키던 시나리오·리비전이
목록에 없다 — 보관·삭제). 보관·삭제는 저장소가 그 Case 를 비우므로 `missing` 은 그 밖의 길로 생긴
드문 상태다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from capa_simulation.services.korean_particle import topic_particle

MAIN_CASE_NUMBERS: tuple[int, int] = (1, 2)
OFFICIAL_SLOT_TITLE = "공식버전"

SlotStatus = Literal["ok", "unset", "missing"]
SLOT_OK: SlotStatus = "ok"
SLOT_UNSET: SlotStatus = "unset"
SLOT_MISSING: SlotStatus = "missing"

UNSET_LABEL = "미지정"
NO_OFFICIAL_LABEL = "공식버전 없음"
MISSING_SCENARIO_LABEL = "지정한 시나리오가 목록에 없습니다(보관·삭제)"
MISSING_REVISION_LABEL = "지정한 리비전이 그 시나리오에 없습니다"


class OfficialPointer(Protocol):
    """최신 공식버전에서 슬롯이 쓰는 필드(`OfficialReleaseSummary`)."""

    @property
    def release_no(self) -> int: ...

    @property
    def release_name(self) -> str: ...

    @property
    def scenario_id(self) -> str: ...

    @property
    def scenario_name(self) -> str: ...

    @property
    def revision_id(self) -> str: ...

    @property
    def revision_no(self) -> int: ...


class ScenarioName(Protocol):
    """활성 시나리오 목록 한 줄에서 쓰는 필드(`ScenarioSummary`)."""

    @property
    def scenario_id(self) -> str: ...

    @property
    def scenario_name(self) -> str: ...


class RevisionPointer(Protocol):
    """리비전 목록 한 줄에서 쓰는 필드(`RevisionSummary`)."""

    @property
    def revision_id(self) -> str: ...

    @property
    def scenario_id(self) -> str: ...

    @property
    def revision_no(self) -> int: ...

    @property
    def revision_name(self) -> str: ...


@dataclass(frozen=True)
class MainCaseSlot:
    """슬롯 하나. `label` 은 사람이 읽는 글이고 상태가 `ok` 가 아니면 그 까닭이다.

    `missing` 이어도 식별자는 공용 프로필에 남아 있던 값을 그대로 둔다 — 무엇이 사라졌는지 알리는 데
    쓴다. 화면이 그 리비전을 불러오면 안 된다(상태로 가른다).
    """

    title: str
    label: str
    scenario_id: str | None
    revision_id: str | None
    status: SlotStatus


def case_title(case_no: int) -> str:
    """「Case1」·「Case2」."""
    return f"Case{case_no}"


def official_slot_label(official: OfficialPointer) -> str:
    """「공식 v4 · 시나리오명 r2 · 공식버전명」 — 시나리오 관리의 최신 공식 줄과 같은 차례다."""
    return (
        f"공식 v{official.release_no} · {official.scenario_name} "
        f"r{official.revision_no} · {official.release_name}"
    )


def case_slot_label(scenario_name: str, revision: RevisionPointer) -> str:
    """「시나리오명 · r3 · 리비전명」 — 리비전 글자는 `revision_label` 과 같은 꼴이다."""
    return f"{scenario_name} · r{revision.revision_no} · {revision.revision_name}"


def main_case_slots(
    *,
    official: OfficialPointer | None,
    cases: Sequence[tuple[str | None, str | None]],
    scenarios: Iterable[ScenarioName],
    revisions: Iterable[RevisionPointer],
) -> tuple[MainCaseSlot, MainCaseSlot, MainCaseSlot]:
    """(공식버전, Case1, Case2) 슬롯 셋.

    `cases` 는 Case1·Case2 차례의 (시나리오 id, 리비전 id) 둘이다(`GlobalMainCases.case`).
    `scenarios` 는 활성 시나리오 목록(보관본 빼고), `revisions` 는 Case 가 가리키는 시나리오들의
    리비전 목록이다 — 리비전이 그 시나리오의 것인지 `scenario_id` 로 견준다. 시나리오만 있고
    리비전이 비면 `unset` (화면이 첫 리비전으로 메우기 전의 짧은 상태)이고 식별자는 시나리오만
    남긴다.
    """
    if len(cases) != len(MAIN_CASE_NUMBERS):
        raise ValueError(
            f"주요 Case 는 {len(MAIN_CASE_NUMBERS)}개입니다: {len(cases)}개를 받았습니다."
        )
    names = {scenario.scenario_id: scenario.scenario_name for scenario in scenarios}
    by_revision = {revision.revision_id: revision for revision in revisions}
    if official is None:
        first = MainCaseSlot(OFFICIAL_SLOT_TITLE, NO_OFFICIAL_LABEL, None, None, SLOT_UNSET)
    else:
        first = MainCaseSlot(
            OFFICIAL_SLOT_TITLE,
            official_slot_label(official),
            official.scenario_id,
            official.revision_id,
            SLOT_OK,
        )
    case_slots = [
        _case_slot(case_title(case_no), pair, names, by_revision)
        for case_no, pair in zip(MAIN_CASE_NUMBERS, cases, strict=True)
    ]
    return first, case_slots[0], case_slots[1]


def _case_slot(
    title: str,
    pair: tuple[str | None, str | None],
    names: Mapping[str, str],
    by_revision: Mapping[str, RevisionPointer],
) -> MainCaseSlot:
    scenario_id, revision_id = pair
    if scenario_id is None:
        return MainCaseSlot(title, UNSET_LABEL, None, None, SLOT_UNSET)
    if scenario_id not in names:
        return MainCaseSlot(title, MISSING_SCENARIO_LABEL, scenario_id, revision_id, SLOT_MISSING)
    if revision_id is None:
        return MainCaseSlot(
            title, f"{names[scenario_id]} · 리비전 {UNSET_LABEL}", scenario_id, None, SLOT_UNSET
        )
    revision = by_revision.get(revision_id)
    if revision is None or revision.scenario_id != scenario_id:
        return MainCaseSlot(title, MISSING_REVISION_LABEL, scenario_id, revision_id, SLOT_MISSING)
    return MainCaseSlot(
        title, case_slot_label(names[scenario_id], revision), scenario_id, revision_id, SLOT_OK
    )


def main_case_overlap_notes(
    *,
    official_revision_id: str | None,
    cases: Sequence[tuple[str | None, str | None]],
) -> list[str]:
    """같은 리비전을 가리키는 슬롯을 알리는 줄. 막지 않는다 — 저장은 하고 알리기만 한다.

    Case1·Case2 가 같은 시나리오·리비전이면 한 줄, Case 가 지금 최신 공식버전과 같은 리비전이면 Case
    마다 한 줄이다. 리비전을 고르지 않은 Case 는 견주지 않는다.
    """
    if len(cases) != len(MAIN_CASE_NUMBERS):
        raise ValueError(
            f"주요 Case 는 {len(MAIN_CASE_NUMBERS)}개입니다: {len(cases)}개를 받았습니다."
        )
    notes: list[str] = []
    first, second = cases
    if first[1] is not None and first == second:
        notes.append(
            "Case1 과 Case2 는 같은 시나리오·리비전입니다 — 저장은 했고, 두 슬롯이 같은 "
            "내용을 보입니다."
        )
    for case_no, (_, revision_id) in zip(MAIN_CASE_NUMBERS, cases, strict=True):
        if revision_id is not None and revision_id == official_revision_id:
            title = case_title(case_no)
            notes.append(
                f"{title} {topic_particle(title)} 지금 공식버전과 같은 리비전입니다 — "
                "슬롯 1(공식버전)과 같은 내용을 보입니다."
            )
    return notes
