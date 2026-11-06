# Purpose: 시나리오 목록 초안의 op 접기 · 세대 · 저장본 맞추기 · 막힘 · 표 data · 저장 계획을 잰다.

"""`services/scenario_list_edits.py` — 브라우저가 보낸 op 를 행 id 로 접는 판정."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from capa_simulation.services.grid_outbox import MOUNT_LIMIT
from capa_simulation.services.scenario_list_edits import (
    ChangeCounts,
    ListDraft,
    ListProblems,
    ListRules,
    NameEdit,
    RevisionFacts,
    SavedList,
    SavedRevision,
    ScenarioFacts,
    SettledName,
    change_counts,
    changes_payload,
    cleared,
    draft_base,
    draft_fingerprint,
    edit_count,
    fold_ops,
    has_edits,
    list_problems,
    move_before,
    moved_rows,
    official_label,
    official_rename_note,
    order_token,
    reconcile,
    revision_status_label,
    revisions_payload,
    save_plan,
    scenarios_payload,
)

ROWS = ("a", "b", "c")
NAMES = {"a": "가", "b": "나", "c": "다"}
DRAFT = ListDraft(session="s1")
BASE = draft_base(DRAFT)
RULES = ListRules(
    duplicate="겹침",
    order="차례 바뀜",
    moved=lambda current: f"먼저 바뀜({current})",
    empty=lambda label: f"{label} 빈 값",
)
_SEQ = iter(range(1, 100_000))


def _box(*ops: dict[str, Any], mount: str = "m-1", base: str = BASE) -> dict[str, Any]:
    numbered = []
    for op in ops:
        seq = next(_SEQ)
        numbered.append({"seq": seq, "at": seq, "base": base, **op})
    return {"mount": mount, "ops": numbered}


def _name(kind: str, row_id: str, text: str, seen: str) -> dict[str, Any]:
    return {"op": "name", "kind": kind, "id": row_id, "text": text, "seen": seen}


def _move(row_id: str, before: str | None, order: tuple[str, ...] = ROWS) -> dict[str, Any]:
    return {"op": "move", "id": row_id, "before": before, "token": order_token(order)}


def _saved(**changes: Any) -> SavedList:
    return replace(SavedList(ROWS, NAMES, NAMES), **changes)


def test_a_name_keeps_the_name_seen_first_and_going_back_removes_the_edit() -> None:
    """`seen` 은 그 칸을 처음 고칠 때 본 이름이다 — 뒤 op 가 다른 `seen` 을 들고 와도 지킨다."""
    first = fold_ops(DRAFT, [_box(_name("scenario", "a", " 새 가 ", "가"))], ROWS).draft
    assert first.scenarios == {"a": NameEdit("가", "새 가")}
    second = fold_ops(first, [_box(_name("scenario", "a", "또 새 가", "남의 가"))], ROWS).draft
    assert second.scenarios == {"a": NameEdit("가", "또 새 가")}
    # 처음 본 이름으로 돌아오면 고침이 아니다(앞뒤 공백을 떼고 견준다).
    back = fold_ops(second, [_box(_name("scenario", "a", " 가", "또 새 가"))], ROWS).draft
    assert back.scenarios == {}
    # 빈 글도 고침이다 — 막힘으로 보인다.
    empty = fold_ops(DRAFT, [_box(_name("revision", "r1", "  ", "첫째"))], ROWS).draft
    assert empty.revisions == {"r1": NameEdit("첫째", "")}


def test_the_same_outbox_again_changes_nothing_and_malformed_ops_are_dropped_uncounted() -> None:
    box = _box(_name("scenario", "a", "새 가", "가"))
    once = fold_ops(DRAFT, [box], ROWS)
    again = fold_ops(once.draft, [box], ROWS)
    assert again.draft == once.draft and again.dropped == 0
    bad = _box(
        {"op": "name", "kind": "scenario", "id": "a", "text": 3, "seen": "가"},
        {"op": "name", "kind": "그 밖", "id": "a", "text": "x", "seen": "가"},
        {"op": "모름", "id": "a"},
        {"op": "move", "id": 3, "before": None, "token": order_token(ROWS)},
        {"op": "open", "id": ""},
    )
    result = fold_ops(DRAFT, [bad, "꼴이 다름", {"mount": 3, "ops": []}], ROWS)
    assert (result.draft.scenarios, result.draft.order, result.draft.opened) == ({}, None, None)
    assert result.dropped == 0 and not result.opened
    # 마운트 기억은 상한을 넘으면 오래된 것부터 잊는다.
    memory = {f"m{index}": index for index in range(MOUNT_LIMIT)}
    held = fold_ops(replace(DRAFT, applied=memory), [_box({"op": "open", "id": "a"})], ROWS).draft
    assert len(held.applied) == MOUNT_LIMIT and "m-1" in held.applied and "m0" not in held.applied


def test_old_generation_edits_are_counted_but_a_pick_is_not_lost() -> None:
    """저장 · 모두 버리기 사이에 고친 것은 반영하지 않고 센다. 고름은 초안을 바꾸지 않아 세대를 보지
    않는다 — 리비전 줄을 누르고 바로 「공식으로 지정…」 을 눌러도 고름이 그 리비전에 걸린다."""
    opened = replace(DRAFT, opened="a")
    old = "s1:옛 세대"
    result = fold_ops(
        opened,
        [
            _box(
                _name("scenario", "b", "새 나", "나"),
                _move("b", "a"),
                {"op": "revert", "kind": "order"},
                {"op": "pick", "owner": "a", "id": "r2"},
                base=old,
            )
        ],
        ROWS,
    )
    assert result.dropped == 3
    assert result.draft.scenarios == {} and result.draft.order is None
    assert result.draft.picked == "r2"
    # 세션 표지가 다른 값도 옛 세대다(세션이 바뀐 뒤 프런트가 다시 보낸 값).
    assert (
        fold_ops(
            DRAFT, [_box(_name("scenario", "a", "새", "가"), base="다른 세션:0")], ROWS
        ).dropped
        == 1
    )


def test_a_move_inserts_compares_the_seen_order_and_returning_clears_it() -> None:
    moved = fold_ops(DRAFT, [_box(_move("c", "a"))], ROWS).draft
    assert moved.order == ("c", "a", "b") and moved.order_base == ROWS
    # 끝으로 — before 없음.
    assert fold_ops(DRAFT, [_box(_move("a", None))], ROWS).draft.order == ("b", "c", "a")
    # 돌아오면 순서 고침이 없다.
    back = fold_ops(moved, [_box(_move("c", None))], ROWS).draft
    assert back.order is None and back.order_base is None
    # 본 차례의 지문이 다르면 그 op 만 거절한다.
    refused = fold_ops(
        moved,
        [_box(_move("b", "a", ("b", "a", "c")), _name("scenario", "a", "새 가", "가"))],
        ROWS,
    )
    assert refused.order_refused
    assert refused.draft.order == ("c", "a", "b")
    assert refused.draft.scenarios == {"a": NameEdit("가", "새 가")}
    # 처음 본 차례는 이어 옮겨도 그대로다.
    next_ = fold_ops(moved, [_box(_move("a", "c"))], ROWS).draft
    assert next_.order == ("a", "c", "b") and next_.order_base == ROWS
    assert move_before(ROWS, "z", "a") == ROWS
    assert move_before(ROWS, "a", "z") == ("b", "c", "a")


def test_revert_drops_only_that_edit() -> None:
    draft = replace(
        DRAFT,
        scenarios={"a": NameEdit("가", "새 가"), "b": NameEdit("나", "새 나")},
        revisions={"r1": NameEdit("첫", "새 첫")},
        order=("b", "a", "c"),
        order_base=ROWS,
    )
    result = fold_ops(draft, [_box({"op": "revert", "kind": "scenario", "id": "a"})], ROWS).draft
    assert set(result.scenarios) == {"b"} and result.order is not None
    result = fold_ops(result, [_box({"op": "revert", "kind": "revision", "id": "r1"})], ROWS).draft
    assert result.revisions == {} and set(result.scenarios) == {"b"}
    result = fold_ops(result, [_box({"op": "revert", "kind": "order"})], ROWS).draft
    assert result.order is None and result.order_base is None
    assert set(result.scenarios) == {"b"}


def test_open_keeps_the_pick_on_the_same_row_and_a_pick_needs_its_owner() -> None:
    draft = replace(DRAFT, opened="a", picked="r1")
    same = fold_ops(draft, [_box({"op": "open", "id": "a"})], ROWS)
    assert same.draft.picked == "r1" and same.opened and not same.to_detail
    other = fold_ops(draft, [_box({"op": "open", "id": "b", "detail": True})], ROWS)
    assert (other.draft.opened, other.draft.picked, other.to_detail) == ("b", None, True)
    # A → B → A 가 한 회차로 접혀도 마지막이 이긴다. 고름은 비고 씨앗이 다시 고른다.
    folded = fold_ops(
        draft, [_box({"op": "open", "id": "b"}, {"op": "open", "id": "a"})], ROWS
    ).draft
    assert (folded.opened, folded.picked) == ("a", None)
    # 그 사이 다른 줄을 열었으면 옛 줄의 고름은 걸리지 않는다.
    stale = fold_ops(draft, [_box({"op": "pick", "owner": "b", "id": "r9"})], ROWS).draft
    assert stale.picked == "r1"


def test_reconcile_counts_gone_rows_settles_same_names_and_fits_the_order() -> None:
    draft = replace(
        DRAFT,
        scenarios={"a": NameEdit("가", "다른 가"), "z": NameEdit("없음", "사라짐")},
        revisions={
            "r1": NameEdit("첫", "남길 이름"),
            "r2": NameEdit("둘", "이미 쓴 이름"),
            "r9": NameEdit("아홉", "사라짐"),
            "r8": NameEdit("여덟", "보관됨"),
        },
        order=("c", "z", "a", "b"),
        order_base=("c", "z", "a", "b"),
        opened="z",
        picked="r9",
    )
    saved = _saved(
        order=("a", "b", "c", "d"),
        names={**NAMES, "a": "다른 가", "d": "라"},
        revisions={
            "r1": SavedRevision("r1", 1, "첫", "a"),
            "r2": SavedRevision("r2", 2, "이미 쓴 이름", "a"),
            "r8": SavedRevision("r8", 8, "여덟", "x", active=False),
        },
    )
    result = reconcile(draft, saved, preferred_open="b")
    assert result.gone == 3
    assert result.settled == (
        SettledName("scenario", "a", "가", "다른 가"),
        SettledName("revision", "r2", "둘", "이미 쓴 이름"),
    )
    assert result.draft.scenarios == {}
    assert result.draft.revisions == {"r1": NameEdit("첫", "남길 이름")}
    assert result.draft.order == ("c", "a", "b", "d")
    # 연 줄이 사라지면 올라와 있는 시나리오로 열고 고름을 비운다.
    assert (result.draft.opened, result.draft.picked) == ("b", None)
    # 올라와 있는 시나리오가 없으면 맨 위 줄을 연다 — 오른쪽 칸이 빈 채 서지 않는다.
    assert reconcile(DRAFT, _saved()).draft.opened == "a"
    assert reconcile(DRAFT, _saved(order=(), names={})).draft.opened is None
    # 고친 차례가 저장 차례와 같아지면 순서 고침이 없다.
    same = reconcile(replace(DRAFT, order=ROWS, order_base=("c", "b", "a")), _saved()).draft
    assert same.order is None and same.order_base is None


def test_problems_see_the_name_seen_the_final_names_and_the_order_seen() -> None:
    draft = replace(
        DRAFT,
        scenarios={
            "a": NameEdit("가", "나"),  # 맞바꾸기
            "b": NameEdit("나", "가"),
            "c": NameEdit("옛 다", "내 이름"),  # 남이 먼저 바꿈
        },
    )
    problems = list_problems(draft, _saved(), RULES)
    assert problems.scenarios == {"c": "먼저 바뀜(다)"}
    # 남이 먼저 바꾼 줄의 새 이름은 겹침에 들지 않는다.
    held = replace(draft, scenarios={**draft.scenarios, "c": NameEdit("옛 다", "나")})
    assert list_problems(held, _saved(), RULES).scenarios == {"c": "먼저 바뀜(다)"}
    # 보관본과도 겹칠 수 없다.
    archived = {**NAMES, "x": "보관 이름"}
    same = replace(DRAFT, scenarios={"a": NameEdit("가", "보관 이름")})
    assert list_problems(same, _saved(all_names=archived), RULES).scenarios == {"a": "겹침"}
    # 빈 이름 — 칸마다 그 이름으로 말한다. 리비전명 겹침은 막힘이 아니다.
    blanks = replace(
        DRAFT,
        scenarios={"a": NameEdit("가", "")},
        revisions={
            "r1": NameEdit("첫", ""),
            "r2": NameEdit("둘", "같은"),
            "r3": NameEdit("셋", "같은"),
        },
    )
    revisions = {
        "r1": SavedRevision("r1", 1, "첫", "a"),
        "r2": SavedRevision("r2", 2, "둘", "a"),
        "r3": SavedRevision("r3", 3, "남의 셋", "a"),
    }
    found = list_problems(blanks, _saved(revisions=revisions), RULES)
    assert found.scenarios == {"a": "시나리오명 빈 값"}
    assert found.revisions == {"r1": "리비전명 빈 값", "r3": "먼저 바뀜(남의 셋)"}
    # 차례 — 처음 본 차례와 지금 저장 차례가 다르면 막힌다.
    order = replace(DRAFT, order=("c", "b", "a"), order_base=("b", "a", "c"))
    assert list_problems(order, _saved(), RULES).order == "차례 바뀜"
    assert list_problems(replace(order, order_base=ROWS), _saved(), RULES).order is None


def test_counts_and_save_plan() -> None:
    draft = replace(
        DRAFT,
        scenarios={"a": NameEdit("가", "새 가")},
        revisions={"r1": NameEdit("첫", "새 첫")},
        order=("b", "a", "c"),
        order_base=ROWS,
    )
    saved = _saved(revisions={"r1": SavedRevision("r1", 1, "첫", "a")})
    assert has_edits(draft) and edit_count(draft) == 3 and moved_rows(draft, ROWS) == 2
    assert change_counts(draft, saved, ListProblems(order="막힘")) == ChangeCounts(1, 2, 1, 1)
    plan = save_plan(draft, saved)
    assert plan.scenario_renames == {"a": ("가", "새 가")}
    assert plan.revision_renames == {"r1": ("첫", "새 첫")}
    assert (plan.order, plan.order_base) == (("b", "a", "c"), ROWS)
    assert plan.writes and plan.done
    empty = save_plan(cleared(draft), saved)
    assert not empty.writes and not empty.done
    settled = replace(empty, settled=(SettledName("revision", "r1", "첫", "새 첫"),))
    assert not settled.writes and settled.done and settled.revision_names() == {"r1": "새 첫"}
    # 비우면 세대가 오르고 연 줄 · 고름은 남는다.
    done = cleared(replace(draft, opened="a", picked="r1"))
    assert (done.generation, done.opened, done.picked) == (1, "a", "r1") and not has_edits(done)
    assert draft_base(done) == "s1:1"


def test_the_fingerprint_is_the_input_and_ignores_the_insertion_order() -> None:
    one = replace(DRAFT, scenarios={"a": NameEdit("가", "1"), "b": NameEdit("나", "2")})
    two = replace(DRAFT, scenarios={"b": NameEdit("나", "2"), "a": NameEdit("가", "1")})
    assert draft_fingerprint(one) == draft_fingerprint(two)
    assert draft_fingerprint(one) != draft_fingerprint(replace(one, order=ROWS))
    # 세대 · 고름 · 반영 기억은 저장 입력이 아니다 — 같은 누름의 둘째는 같은 지문이다.
    other = replace(one, opened="a", picked="r1", applied={"m": 3})
    assert draft_fingerprint(one) == draft_fingerprint(other)


def test_labels() -> None:
    official = {"a": (3, 2), "b": (5, 1)}
    assert official_label("a", official, "b") == "v3 · r2"
    assert official_label("b", official, "b") == "v5 · r1 · 최신"
    assert official_label("c", official, "b") == ""
    assert (
        revision_status_label(4, loaded=True, virtual_count=2) == "공식 v4 · 올라와 있음 · 가상 2"
    )
    assert revision_status_label(None, loaded=False, virtual_count=0) == ""
    # 「공식 vN」 뒤 조사는 번호 끝소리로 고른다 — v4 는 「로」, v3 은 「으로」.
    assert official_rename_note(4).startswith("공식 v4로 지정된 리비전입니다")
    assert official_rename_note(3).startswith("공식 v3으로 지정된 리비전입니다")


def test_the_scenario_rows_carry_saved_and_place_only_when_they_differ() -> None:
    draft = replace(
        DRAFT,
        opened="b",
        scenarios={"c": NameEdit("다", "새 다")},
        order=("c", "a", "b"),
        order_base=ROWS,
    )
    facts = {"a": ScenarioFacts("코드", "r3", "v1 · r2", "26.11.05 23:30")}
    data = scenarios_payload(draft, _saved(), ListProblems(scenarios={"c": "막힘"}), facts)
    assert data["open"] == "b" and data["orderToken"] == order_token(ROWS)
    assert data["rows"][0] == {
        "id": "c",
        "name": "새 다",
        "latest": "",
        "official": "",
        "updated": "",
        "saved": "다",
        "place": 3,
        "problem": "막힘",
    }
    assert data["rows"][1] == {
        "id": "a",
        "name": "가",
        "latest": "r3",
        "official": "v1 · r2",
        "updated": "26.11.05 23:30",
        "place": 1,
    }
    same = scenarios_payload(DRAFT, _saved(), ListProblems(), facts)["rows"][0]
    assert "saved" not in same and "place" not in same and "problem" not in same


def test_the_revision_rows_carry_their_values_and_the_pick() -> None:
    draft = replace(DRAFT, opened="a", picked="r1", revisions={"r2": NameEdit("둘", "새 둘")})
    facts = [
        RevisionFacts("r2", 2, "둘", "공식 v1", "메모", "26.11.05 23:30", "r1"),
        RevisionFacts("r1", 1, "첫"),
    ]
    data = revisions_payload(
        draft,
        owner="a",
        title="이름",
        sub="코드 · 26.11.05 23:30",
        facts=facts,
        problems=ListProblems(revisions={"r2": "막힘"}),
    )
    assert (data["mode"], data["owner"], data["picked"]) == ("revisions", "a", "r1")
    assert data["rows"][0]["name"] == "새 둘" and data["rows"][0]["saved"] == "둘"
    assert data["rows"][0]["problem"] == "막힘" and data["rows"][0]["no"] == "r2"
    assert "saved" not in data["rows"][1]


def test_the_changes_are_grouped_by_scenario_in_table_order_with_other_scenarios_too() -> None:
    draft = replace(
        DRAFT,
        opened="a",
        scenarios={"c": NameEdit("다", "새 다")},
        revisions={"r7": NameEdit("일곱", "새 일곱"), "r1": NameEdit("첫", "새 첫")},
        order=("c", "a", "b"),
        order_base=("a", "b", "c"),
    )
    saved = _saved(
        revisions={
            "r1": SavedRevision("r1", 1, "첫", "a", release_no=4),
            "r7": SavedRevision("r7", 7, "일곱", "c"),
        }
    )
    problems = ListProblems(revisions={"r7": "막힘"}, order="차례 막힘")
    data = changes_payload(draft, saved, problems, change_counts(draft, saved, problems))
    assert data["counts"] == {"scenario": 1, "order": 3, "revision": 2, "blocked": 2}
    assert data["order"] == {"moved": 3, "problem": "차례 막힘"}
    assert [group["id"] for group in data["groups"]] == ["c", "a"]
    (first, second) = data["groups"]
    assert first["name"] == "새 다"
    assert [line["kind"] for line in first["lines"]] == ["scenario", "revision"]
    assert first["lines"][1]["label"] == "리비전명 r7" and first["lines"][1]["problem"] == "막힘"
    assert second["lines"][0]["mark"] == "공식 v4"
    assert second["lines"][0]["note"].startswith("공식 v4로 지정된")
