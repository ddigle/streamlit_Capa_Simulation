# Purpose: 설비 마스터 표 순수 계산 시간이 합성 3천 대에서 넉넉한 상한 안인지 본다.

"""회귀만 잡는 상한 시험(개편 명세 8장). 상한은 합성 표본 「샘플 관측」(3,024대 — 표본 fleet 56벌,
2026-10-25 사외 WSL: 칸 결과 0.08s · 표 모양 0.08s · 표 data 1,000줄 0.002s · 불러오기 data 0.01s ·
칸 하나 0.005s · 붙여넣기 500칸 0.3s · 「새 호기」 초안 판정 0.05s · 「호기 추가」 0.05s)의 약
10배다. 실데이터 모양을 가정하지 않는다."""

from __future__ import annotations

import time
from datetime import date

import pandas as pd

from capa_simulation.services import equipment_grid as eg
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.equipment_validation import equipment_master_issues
from capa_simulation.services.space_layout_edit import PendingRenames

ANCHOR = date(2026, 10, 1)


def _big() -> eg.Frames:
    master = sample_equipment_master(anchor_date=ANCHOR)
    parts = []
    for copy in range(56):
        part = master.copy()
        part["설비명"] = part["설비명"] + f"-{copy:02d}"
        parts.append(part)
    return (
        sample_equipment_baseline(),
        pd.concat(parts, ignore_index=True),
        sample_downtime_schedule(anchor_date=ANCHOR),
    )


def test_a_rerun_of_three_thousand_units_stays_well_inside_the_budget() -> None:
    saved = _big()
    frames = (saved[0], saved[1].copy(), saved[2])
    context = eg.GridContext(base="t#1", scenario_name="운영")
    started = time.perf_counter()
    issues = equipment_master_issues(frames[1])
    view = eg.build_grid_view(eg.GridSource(frames=frames, saved=saved, issues=issues), context)
    loaded = list(view.index.live)[: eg.GRID_ROW_LIMIT]
    eg.grid_data(view, loaded)
    eg.loader_data(view, loaded)
    eg.changes_data(view)
    eg.detail_data(view, loaded[3])
    assert time.perf_counter() - started < 3.0

    state = eg.GridState(frames=frames, saved=saved, loaded=tuple(loaded))
    started = time.perf_counter()
    eg.apply_ops(
        state,
        [{"seq": 1, "base": "t#1", "op": "cell", "id": loaded[0], "col": "담당자", "text": "X"}],
        context,
    )
    assert time.perf_counter() - started < 0.5

    rows = [[f"2026-11-{day % 28 + 1:02d}"] * 5 for day in range(100)]
    started = time.perf_counter()
    result = eg.apply_ops(
        state,
        [
            {
                "seq": 2,
                "base": "t#1",
                "op": "paste",
                "ids": loaded[:100],
                "cols": ["반입일정", "Qual일정", "메모1", "메모2", "메모3"],
                "rows": rows,
            }
        ],
        context,
    )
    assert time.perf_counter() - started < 3.0
    assert result.toast == "붙여넣기 100줄 → 500칸 바뀜"


def test_the_new_unit_check_and_add_stay_well_inside_the_budget() -> None:
    """「새 호기」 칸은 열린 회차마다 초안을 편집본 위에서 본다(개편 단계 C) — 관련 행만 규칙 표에
    넣어 편집본 전체를 다시 돌리지 않는다."""
    saved = _big()
    frames = (saved[0], saved[1].copy(), saved[2])
    context = eg.GridContext(base="t#1", scenario_name="운영", today=ANCHOR)
    draft = eg.blank_draft()
    draft[eg.COLUMN_INDEX["설비명"]] = "NEW-X"
    draft[eg.COLUMN_INDEX["공정소분류"]] = "TC Bonding"
    started = time.perf_counter()
    check = eg.new_unit_check(
        draft, frames=frames, saved_master=saved[1], renames=PendingRenames(), context=context
    )
    assert time.perf_counter() - started < 0.5 and not check.blocked

    state = eg.GridState(frames=frames, saved=saved)
    started = time.perf_counter()
    result = eg.apply_ops(state, [{"seq": 1, "base": "t#1", "op": "add", "draft": draft}], context)
    assert time.perf_counter() - started < 0.5 and result.added
