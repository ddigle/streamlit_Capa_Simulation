# Purpose: 가용설비 현황 캐시 래퍼가 키로 적중하고 캐시 없이 새로 계산한 결과와 같은지 고정한다.

"""가용설비 현황 캐시 래퍼(`services/simulation_cache.py`).

래퍼는 프레임을 해시하지 않고 키만 본다(`_` 인자). 그래서 **키에서 입력을 하나라도 빠뜨리면 낡은
값이 나온다.** 여기서는 입력을 하나씩 바꿔 가며 (1) 키가 바뀌는지, (2) 캐시를 거친 결과가 캐시 없이
새로 계산한 결과와 같은지를 본다.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import pytest
from test_required_shortening import MAY, PROCESS, _worked_example

from capa_simulation.services import simulation_cache
from capa_simulation.services.required_shortening import (
    TARGET_LEVELS,
    ShorteningPlan,
    process_month_export_frame,
    unit_export_frame,
)


def _csv(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


# ------------------------------------------------------------------ 필요단축일정 CSV(A10)


def test_shortening_csvs_are_built_once_per_plan_key_and_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """목표만 바꾼 rerun 이 세 표를 다시 만들지 않는다 — 바이트는 새로 만든 것과 같다(점검 A10)."""
    simulation_cache.get_required_shortening_csvs.clear()
    plan = _worked_example()
    key = ((1, "plan-token", MAY, MAY), "m", "d", "b", "c", plan.months, plan.today.isoformat())
    built: list[tuple[float, ...]] = []

    def counting(
        plan: ShorteningPlan, levels: Sequence[float], processes: Sequence[str] | None = None
    ) -> pd.DataFrame:
        built.append(tuple(levels))
        return unit_export_frame(plan, levels, processes)

    monkeypatch.setattr(simulation_cache, "unit_export_frame", counting)
    scope = (PROCESS,)

    first = simulation_cache.get_required_shortening_csvs(key, 1.1, scope, (MAY,), _plan=plan)
    again = simulation_cache.get_required_shortening_csvs(key, 1.1, scope, (MAY,), _plan=plan)

    assert again == first
    assert built == [(1.1,), TARGET_LEVELS]
    assert first == (
        _csv(unit_export_frame(plan, (1.1,), scope)),
        _csv(unit_export_frame(plan, TARGET_LEVELS, scope)),
        _csv(process_month_export_frame(plan, (1.1,), scope, (MAY,))),
    )
    assert first[0].startswith(b"\xef\xbb\xbf")

    # 목표를 바꾸면 새 키다 — 고른 목표의 두 표가 그 목표로 다시 나온다.
    other = simulation_cache.get_required_shortening_csvs(key, 1.3, scope, (MAY,), _plan=plan)
    assert len(built) == 4
    assert other[0] == _csv(unit_export_frame(plan, (1.3,), scope))
    assert other[2] == _csv(process_month_export_frame(plan, (1.3,), scope, (MAY,)))
    assert other[1] == first[1]
