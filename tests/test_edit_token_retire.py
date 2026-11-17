# Purpose: 편집 적용이 옛 편집본의 전체 기간 칸만 걷고 리비전 칸은 남기는지와 그 칸 상한을 검증한다.

"""**죽은 편집본 칸이 프로세스 전역 칸을 차지했다.**

전체 기간 결과 칸(`get_full_capacity_outcome`)은 프로세스 전역이고 키는 (reference_version,
content_token)이다. 편집 토큰은 uuid 라 새 편집이 서면 옛 토큰은 아무도 다시 부르지 않는데, 칸은
상한까지 남아 다른 세션이 나눠 쓰는 리비전 칸을 밀어냈다. 그래서 편집 적용이 새 토큰을 낼 때
갈아끼워지는 편집본 칸 하나를 키로 걷는다(`scenario_state._next_edit_token`). 리비전 칸(pristine
토큰)은 걷지 않는다 — 다른 세션 · 다음 불러오기가 그대로 쓴다.

칸 수 판단은 합성 표본의 샘플 관측이다(실험 R3 — 편집 16번 뒤 전체 칸이 리비전 하나 + 지금
편집본 하나로 머묾).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator, Mapping
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest
import streamlit as st

from capa_simulation import scenario_state
from capa_simulation.services import simulation_cache as sc
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def tables() -> dict[str, pd.DataFrame]:
    return dict(build_builtin_seed_dataset().reference_tables)


@pytest.fixture(autouse=True)
def _clean_session() -> Iterator[None]:
    yield
    st.session_state.clear()


@pytest.fixture
def computed(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """전체 기간 칸의 몸통(`full_capacity_outcome`)이 돈 횟수 — 그 칸이 빗나갈 때만 는다. 계산은
    그대로 한다(멈춘 계산의 조회기간 오류 칸 `get_period_capacity_error` 는 세지 않는다)."""
    calls: list[int] = []
    original = sc.full_capacity_outcome

    def counted(
        scenario_tables: Mapping[str, pd.DataFrame], reference_tables: Mapping[str, pd.DataFrame]
    ) -> sc.CapacityOutcome:
        calls.append(1)
        return original(scenario_tables, reference_tables)

    monkeypatch.setattr(sc, "full_capacity_outcome", counted)
    return calls


def _version() -> int:
    # 칸은 프로세스 전역이다. 리비전 칸(`pristine-<번호>`)을 다른 시험과 나눠 쓰지 않게 번호를 새로
    # 낸다.
    return 10**6 + uuid4().int % 10**9


def _months(tables: Mapping[str, pd.DataFrame]) -> list[int]:
    values = pd.to_numeric(tables["RQ_PKG_PLAN"]["생산계획년월"]).unique().tolist()
    return sorted(int(value) for value in values)


def _calculate(
    scenario: scenario_state.ActiveScenario, tables: Mapping[str, pd.DataFrame]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """화면과 같은 길 — 시나리오 키(`scenario_cache_key`)로 조회기간 결과를 받는다."""
    months = _months(scenario["tables"])
    key = sc.scenario_cache_key(scenario["reference_version"], scenario, months[0], months[-1])
    return sc.get_scenario_capacity_and_demand(
        key, _scenario_tables=scenario["tables"], _reference_tables=tables
    )


def _plan_edit(scenario: scenario_state.ActiveScenario) -> scenario_state.ActiveScenario:
    """첫 달 PKG PLAN 수량을 두 배로 — 화면의 적용과 같은 `apply_month_updates`."""
    month = _months(scenario["tables"])[0]
    plan = scenario_state.scenario_month_table(scenario, "RQ_PKG_PLAN", month, month)
    plan["생산수량"] = pd.to_numeric(plan["생산수량"]) * 2
    return scenario_state.apply_month_updates(scenario, {"RQ_PKG_PLAN": plan}, month, month)


def _table_edit(scenario: scenario_state.ActiveScenario) -> scenario_state.ActiveScenario:
    """월 축 없는 표를 통째로 — 화면의 가상 제품 등록과 같은 `apply_table_updates`."""
    return scenario_state.apply_table_updates(
        scenario, {"RQ_CHIP_QTY": scenario["tables"]["RQ_CHIP_QTY"]}
    )


def test_an_edit_retires_the_replaced_edit_cell_but_keeps_the_revision_cell(
    tables: dict[str, pd.DataFrame], computed: list[int]
) -> None:
    pristine = scenario_state.reset_active_scenario(tables, _version())
    assert scenario_state.is_pristine_content_token(pristine["content_token"])
    _calculate(pristine, tables)
    assert len(computed) == 1

    first = _plan_edit(pristine)
    _calculate(pristine, tables)
    assert len(computed) == 1, "리비전 칸은 편집이 서도 남는다"
    _calculate(first, tables)
    assert len(computed) == 2

    second = _table_edit(first)
    assert st.session_state[scenario_state.ACTIVE_SCENARIO_KEY] is second
    _calculate(pristine, tables)
    _calculate(second, tables)
    assert len(computed) == 3, "리비전 칸은 그대로 적중하고 새 편집본만 계산한다"
    _calculate(second, tables)
    assert len(computed) == 3

    _calculate(first, tables)
    assert len(computed) == 4, "갈아끼워진 편집본 칸은 걷혔다"


def test_an_edit_from_the_revision_retires_nothing(
    tables: dict[str, pd.DataFrame], computed: list[int]
) -> None:
    """리비전 상태(pristine 토큰)에서 처음 편집할 때는 걷을 편집본이 없다 — 리비전 칸은 세션끼리
    나눈다."""
    pristine = scenario_state.reset_active_scenario(tables, _version())
    _calculate(pristine, tables)

    _table_edit(pristine)

    _calculate(pristine, tables)
    assert len(computed) == 1


def test_a_refused_edit_retires_nothing(
    tables: dict[str, pd.DataFrame], computed: list[int]
) -> None:
    """적용이 막히면(`ValueError`) 활성 시나리오도 칸도 그대로다 — 토큰은 표를 다 갈아끼운 뒤에
    낸다."""
    first = _plan_edit(scenario_state.reset_active_scenario(tables, _version()))
    _calculate(first, tables)
    months = _months(first["tables"])
    outside = scenario_state.scenario_month_table(first, "RQ_PKG_PLAN", months[1], months[1])

    with pytest.raises(ValueError, match="선택 범위 밖"):
        scenario_state.apply_month_updates(first, {"RQ_PKG_PLAN": outside}, months[0], months[0])

    assert st.session_state[scenario_state.ACTIVE_SCENARIO_KEY] is first
    _calculate(first, tables)
    assert len(computed) == 1


def test_retiring_a_cell_that_is_not_there_is_quiet(tables: dict[str, pd.DataFrame]) -> None:
    """한 번도 계산하지 않았거나 이미 밀려난 편집본 칸을 걷어도 아무 일이 없다."""
    sc.retire_full_capacity_outcome((_version(), uuid4().hex))

    first = _table_edit(scenario_state.reset_active_scenario(tables, _version()))
    second = _table_edit(first)

    assert second["content_token"] != first["content_token"]


def _without_last_run_rate_month(tables: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """가동률에서 마지막 달을 뺀다 — 중립값이 없어 시나리오 전체 계산이 멈춘다."""
    broken = dict(tables)
    run_rate = tables["RQ_RUN_RATE"]
    months = pd.to_numeric(run_rate["생산계획년월"])
    broken["RQ_RUN_RATE"] = run_rate.loc[months.ne(months.max())].reset_index(drop=True)
    return broken


def test_a_failed_revision_edit_cell_is_retired_like_any_other(
    tables: dict[str, pd.DataFrame], computed: list[int]
) -> None:
    """계산이 멈춘 리비전도 실패를 칸에 담는다(`CapacityOutcome`). 그 편집본 칸도 같은 길로 걷고,
    걷어도 화면이 받는 것은 같은 계산 멈춤(`ValueError`)뿐이다."""
    broken = _without_last_run_rate_month(tables)
    first = _table_edit(scenario_state.reset_active_scenario(broken, _version()))
    for _ in range(2):
        with pytest.raises(ValueError, match="RQ_RUN_RATE"):
            _calculate(first, broken)
    assert len(computed) == 1, "실패도 칸에 담긴다"

    second = _table_edit(first)

    with pytest.raises(ValueError, match="RQ_RUN_RATE"):
        _calculate(second, broken)
    with pytest.raises(ValueError, match="RQ_RUN_RATE"):
        _calculate(first, broken)
    assert len(computed) == 3, "갈아끼워진 실패 편집본 칸도 걷혔다"


def test_the_full_cell_holds_eight_contents(monkeypatch: pytest.MonkeyPatch) -> None:
    """전체 기간 칸은 여덟 내용(리비전 · 편집본)을 쥐고, 아홉째가 들면 가장 오래 안 쓴 칸이
    밀린다."""
    assert sc.FULL_CAPACITY_MAX_ENTRIES == 8
    calls: list[int] = []

    def cheap(*_args: object) -> sc.CapacityOutcome:
        calls.append(1)
        return sc.CapacityOutcome(None, None, "칸 상한 시험")

    monkeypatch.setattr(sc, "full_capacity_outcome", cheap)
    version = _version()
    keys = [(version, uuid4().hex) for _ in range(9)]

    def call(key: tuple[int, str]) -> None:
        sc.get_full_capacity_outcome(key, _scenario_tables={}, _reference_tables={})

    for key in keys[:8]:
        call(key)
    for key in keys[:8]:
        call(key)
    assert len(calls) == 8, "여덟 칸이 모두 남는다"

    call(keys[8])
    call(keys[7])
    assert len(calls) == 9
    call(keys[0])
    assert len(calls) == 10, "아홉째가 가장 오래 안 쓴 칸을 밀어냈다"


# 편집 적용(`apply_month_updates` · `apply_table_updates`)을 부르는 곳. 모두 적용 뒤 곧바로 앱 전체
# 회차를 다시 돌리고(`st.rerun` · `DialogHost.finish`), 그 사이에 계산을 부르지 않는다 — 걷은 옛
# 편집본 칸을 같은 회차가 다시 채우지 않는다(생산 계획 적용 두 번은
# `test_load_conversion_plan_apply.py` 가 실제로 돌려 본다). `_apply_yield` 는 부르는 두 곳(편집표
# 적용 · 붙여넣기 팝업)이, `_apply_edit` 는 그리드 적용 · 붙여넣기 팝업(`month_editor.paste_dialog`
# → `DialogHost.finish`)이 다시 돌린다. 곳을 더하면 같은 차례인지 보고 여기 더한다.
EDIT_APPLY_SITES = frozenset(
    {
        ("app_pages/load_conversion.py", "_apply_yield"),
        ("app_pages/load_conversion.py", "_virtual_product_dialog"),
        ("app_pages/load_conversion.py", "<module>"),
        ("app_pages/reference_data.py", "_step_dialog"),
        ("app_pages/reference_data.py", "_apply_edit"),
    }
)
EDIT_APPLY_FUNCTIONS = frozenset({"apply_month_updates", "apply_table_updates"})


def _apply_sites(relative: str) -> set[tuple[str, str]]:
    tree = ast.parse((PROJECT_ROOT / relative).read_text(encoding="utf-8"))
    found: set[tuple[str, str]] = set()

    def visit(node: ast.AST, owner: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = (
                child.name if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef) else owner
            )
            if isinstance(child, ast.Call):
                func = child.func
                name = (
                    func.id
                    if isinstance(func, ast.Name)
                    else func.attr
                    if isinstance(func, ast.Attribute)
                    else ""
                )
                if name in EDIT_APPLY_FUNCTIONS:
                    found.add((relative, owner))
            visit(child, inner)

    visit(tree, "<module>")
    return found


def test_every_edit_apply_site_is_one_that_reruns_right_after() -> None:
    """편집 적용을 부르는 곳이 늘면 그 곳도 적용 뒤 곧바로 앱 전체를 다시 돌리는지 보고 목록에
    더한다 — 적용 뒤 같은 회차가 옛 시나리오로 계산을 부르면 걷은 칸을 다시 채워 같은 내용을 한 번
    더 계산한다."""
    paths = [
        PROJECT_ROOT / "app.py",
        *(PROJECT_ROOT / "app_pages").rglob("*.py"),
        *(PROJECT_ROOT / "src").rglob("*.py"),
    ]
    sources = [
        relative
        for relative in sorted(path.relative_to(PROJECT_ROOT).as_posix() for path in paths)
        if relative != "src/capa_simulation/scenario_state.py"
    ]

    found = set().union(*(_apply_sites(relative) for relative in sources))

    assert found == EDIT_APPLY_SITES
