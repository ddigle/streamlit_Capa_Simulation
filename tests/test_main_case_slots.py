# Purpose: HOME 주요 Case 슬롯 셋의 글자·상태(ok·미지정·사라짐)와 겹침 안내 줄을 고정한다.

"""2단계(HOME 슬롯 고르기)가 쓸 순수 도우미. 슬롯은 공식버전·Case1·Case2 셋으로 고정이다."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from capa_simulation.services.main_cases import (
    MISSING_REVISION_LABEL,
    MISSING_SCENARIO_LABEL,
    NO_OFFICIAL_LABEL,
    SLOT_MISSING,
    SLOT_OK,
    SLOT_UNSET,
    UNSET_LABEL,
    MainCaseSlot,
    main_case_overlap_notes,
    main_case_slots,
)

OFFICIAL = SimpleNamespace(
    release_no=4,
    release_name="10월 확정",
    scenario_id="S0",
    scenario_name="공식 시나리오",
    revision_id="S0-R2",
    revision_no=2,
)
SCENARIOS = [
    SimpleNamespace(scenario_id="S0", scenario_name="공식 시나리오"),
    SimpleNamespace(scenario_id="S1", scenario_name="증설안"),
]
REVISIONS = [
    SimpleNamespace(revision_id="S1-R1", scenario_id="S1", revision_no=1, revision_name="초안"),
    SimpleNamespace(revision_id="S1-R2", scenario_id="S1", revision_no=2, revision_name="확정"),
    SimpleNamespace(revision_id="S0-R2", scenario_id="S0", revision_no=2, revision_name="공식"),
]


def _slots(
    cases: list[tuple[str | None, str | None]], official: object = OFFICIAL
) -> tuple[MainCaseSlot, MainCaseSlot, MainCaseSlot]:
    return main_case_slots(
        official=official,  # type: ignore[arg-type]
        cases=cases,
        scenarios=SCENARIOS,
        revisions=REVISIONS,
    )


def test_three_fixed_slots_with_titles_labels_and_pointers() -> None:
    official, case1, case2 = _slots([("S1", "S1-R2"), (None, None)])

    assert (official.title, official.status) == ("공식버전", SLOT_OK)
    assert official.label == "공식 v4 · 공식 시나리오 r2 · 10월 확정"
    assert (official.scenario_id, official.revision_id) == ("S0", "S0-R2")
    assert (case1.title, case1.label, case1.status) == ("Case1", "증설안 · r2 · 확정", SLOT_OK)
    assert (case1.scenario_id, case1.revision_id) == ("S1", "S1-R2")
    assert (case2.title, case2.label, case2.status) == ("Case2", UNSET_LABEL, SLOT_UNSET)
    assert (case2.scenario_id, case2.revision_id) == (None, None)


def test_no_official_release_is_an_unset_first_slot() -> None:
    official, _, _ = _slots([(None, None), (None, None)], official=None)

    assert (official.label, official.status, official.revision_id) == (
        NO_OFFICIAL_LABEL,
        SLOT_UNSET,
        None,
    )


def test_a_vanished_scenario_or_a_foreign_revision_is_missing() -> None:
    """목록에 없는 시나리오(보관·삭제), 그 시나리오 것이 아닌 리비전은 「사라짐」 — 불러오지 않는다.

    식별자는 프로필 값 그대로 둔다(무엇이 사라졌는지 알린다).
    """
    _, gone, foreign = _slots([("S9", "S9-R1"), ("S1", "S0-R2")])

    assert (gone.status, gone.label, gone.scenario_id) == (
        SLOT_MISSING,
        MISSING_SCENARIO_LABEL,
        "S9",
    )
    assert (foreign.status, foreign.label) == (SLOT_MISSING, MISSING_REVISION_LABEL)
    assert foreign.revision_id == "S0-R2"


def test_a_scenario_without_its_revision_is_unset_but_named() -> None:
    _, case1, _ = _slots([("S1", None), (None, None)])

    assert (case1.status, case1.scenario_id, case1.revision_id) == (SLOT_UNSET, "S1", None)
    assert case1.label == f"증설안 · 리비전 {UNSET_LABEL}"


def test_exactly_two_cases_are_required() -> None:
    with pytest.raises(ValueError, match="2개"):
        _slots([("S1", "S1-R1")])
    with pytest.raises(ValueError, match="2개"):
        main_case_overlap_notes(official_revision_id=None, cases=[])


def test_overlap_notes_name_the_same_pairs_but_do_not_block() -> None:
    same = main_case_overlap_notes(
        official_revision_id="S0-R2", cases=[("S1", "S1-R1"), ("S1", "S1-R1")]
    )
    assert same == [
        "Case1 과 Case2 는 같은 시나리오·리비전입니다 — 저장은 했고, "
        "두 슬롯이 같은 내용을 보입니다."
    ]

    official = main_case_overlap_notes(
        official_revision_id="S0-R2", cases=[("S0", "S0-R2"), ("S1", "S1-R1")]
    )
    assert official == [
        "Case1 은 지금 공식버전과 같은 리비전입니다 — 슬롯 1(공식버전)과 같은 내용을 보입니다."
    ]

    both = main_case_overlap_notes(
        official_revision_id="S0-R2", cases=[("S0", "S0-R2"), ("S0", "S0-R2")]
    )
    assert len(both) == 3
    assert both[2].startswith("Case2 는 지금 공식버전과")


def test_blank_or_different_cases_make_no_notes() -> None:
    assert main_case_overlap_notes(official_revision_id="S0-R2", cases=[(None, None)] * 2) == []
    assert main_case_overlap_notes(official_revision_id=None, cases=[("S1", None)] * 2) == []
    assert (
        main_case_overlap_notes(
            official_revision_id="S0-R2", cases=[("S1", "S1-R1"), ("S1", "S1-R2")]
        )
        == []
    )
