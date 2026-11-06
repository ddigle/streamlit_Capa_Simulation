# Purpose: 시나리오 수백 개에서 목록 표 data 조립 시간 · 크기가 상한 안인지 합성 표본으로 본다.

"""줄을 다 그리는 표라 data 크기가 회차 전송량이다 — 이름이 그대로면 `saved` · `place` 를 싣지
않는다. Capa 탭은 다른 탭이 열린 회차에도 그리므로(폼 · 보관함 입력을 잃지 않는다) 조립 시간이 그
회차에도 실린다. 상한은 이 PC 샘플 관측의 넉넉한 몇 배다 — 계약이 아니라 크기 자릿수가 뛰는 것을
잡는 그물이다. 값은 모두 합성이다."""

from __future__ import annotations

import json
import time

from test_scenario_list_ops import RULES

from capa_simulation.services.scenario_list_edits import (
    ListDraft,
    ListProblems,
    NameEdit,
    SavedList,
    ScenarioFacts,
    change_counts,
    changes_payload,
    fold_ops,
    list_problems,
    reconcile,
    scenarios_payload,
)

ROWS = 500


def _saved() -> tuple[SavedList, dict[str, ScenarioFacts]]:
    ids = tuple(f"00000000-0000-4000-8000-{index:012d}" for index in range(ROWS))
    names = {
        row_id: f"합성 시나리오 {index:03d} · 27년 정기 검토" for index, row_id in enumerate(ids)
    }
    facts = {
        row_id: ScenarioFacts(f"DEMO-SIM-{index:04d}", "r12", "v3 · r2", "26.11.05 23:30")
        for index, row_id in enumerate(ids)
    }
    return SavedList(order=ids, names=names, all_names=names), facts


def test_the_table_data_stays_small_and_quick_for_five_hundred_rows() -> None:
    saved, facts = _saved()
    draft = ListDraft(
        session="s",
        scenarios={saved.order[3]: NameEdit(saved.names[saved.order[3]], "합성 고친 이름")},
        order=tuple(reversed(saved.order)),
        order_base=saved.order,
    )
    started = time.perf_counter()
    for _ in range(20):
        fitted = reconcile(draft, saved).draft
        problems = list_problems(fitted, saved, RULES)
        data = scenarios_payload(fitted, saved, problems, facts)
        changes_payload(fitted, saved, problems, change_counts(fitted, saved, problems))
    per_run_ms = (time.perf_counter() - started) / 20 * 1000
    size = len(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    # 샘플 관측 — 이 PC 1 회차 조립 약 1ms, data 약 100KB(모든 줄 자리가 달라 `place` 가 붙은 꼴).
    assert per_run_ms < 100, per_run_ms
    assert size < 200_000, size


def test_rows_without_edits_carry_no_saved_or_place() -> None:
    saved, facts = _saved()
    data = scenarios_payload(ListDraft(session="s"), saved, ListProblems(), facts)
    size = len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    assert all("saved" not in row and "place" not in row for row in data["rows"])
    # 샘플 관측 — 줄당 약 170B.
    assert size / ROWS < 300, size / ROWS


def test_folding_a_full_outbox_is_quick() -> None:
    """이동 단추 · 끌기 몇백 번이 쌓인 출납도 한 번에 접는다(보낼 목록 상한 2,000)."""
    saved, _ = _saved()
    draft = ListDraft(session="s")
    from capa_simulation.services.scenario_list_edits import draft_base, order_token

    ops = [
        {
            "seq": seq,
            "at": seq,
            "base": draft_base(draft),
            "op": "move",
            "id": saved.order[seq % ROWS],
            "before": saved.order[(seq * 7) % ROWS],
            "token": order_token(saved.order),
        }
        for seq in range(1, 2001)
    ]
    started = time.perf_counter()
    result = fold_ops(draft, [{"mount": "m", "ops": ops}], saved.order)
    assert result.draft.applied == {"m": 2000}
    assert time.perf_counter() - started < 5
