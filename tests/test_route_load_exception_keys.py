# Purpose: 부하 예외 선언이 계산 토큰 안에서만 계산에 들고 빈 선언의 키가 그대로인지 본다.

"""부하 예외 선언과 계산 키(AGENTS 5장 44).

선언은 **캐시 키 안의 값으로만** 계산에 든다 — 내용 토큰에 선언을 접은 계산 토큰
(`simulation_cache.calculation_token`)이 키의 둘째 칸이고, 전체 기간 칸이 그 토큰에서 선언을 다시
푼다. 이 파일이 붙드는 것:

- 빈 선언이면 세 키 빌더 · 편집표 키가 선언을 모르던 때의 튜플과 글자까지 같다.
- 접기 · 풀기, 두 선언은 두 칸 · 두 결과.
- 소요대수 길의 선언 칸에 기본값이 없다(빠뜨리면 mypy 가 잡는다).
- 빈 선언을 그대로 적는 자리는 정해 둔 목록뿐이다.
- `simulation_cache` 밖에서 (판, 토큰) 튜플을 손으로 짓지 않는다.
- 선언을 접지 않는 편집표 키는 두 편집 화면만 쓴다.
- 등록 R-07 판정(`capacity_stop`)은 선언을 넘겨도 같다.

공정 이름은 합성 `DEMO-*` 이거나 내장 합성 시드에서 읽는다.
"""

from __future__ import annotations

import ast
import functools
import inspect
import warnings
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import pytest

from capa_simulation.scenario_state import is_pristine_content_token, pristine_content_token
from capa_simulation.services import extra_process_merge
from capa_simulation.services import simulation_cache as sc
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.required_equipment import (
    calculate_required_equipment,
    required_exclusion_counts,
)
from capa_simulation.services.route_load_exceptions import (
    BUFFER_X_CORE_CHIP,
    NO_ROUTE_LOAD_EXCEPTIONS,
    RouteLoadDeclaration,
    normalize_route_load_declaration,
    route_load_declaration_json,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = ("src", "app_pages", "scripts")
SIMULATION_CACHE = "src/capa_simulation/services/simulation_cache.py"
_DECLARED: RouteLoadDeclaration = {"DEMO-P1": BUFFER_X_CORE_CHIP}
_MONTHS = (202601, 202606)


def _sources() -> Iterator[tuple[str, ast.Module]]:
    """앱 · 스크립트 소스(시험 밖)의 (뿌리 기준 경로, 구문 나무)."""
    paths = [path for root in SOURCE_ROOTS for path in (PROJECT_ROOT / root).rglob("*.py")]
    for path in sorted([*paths, PROJECT_ROOT / "app.py"]):
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        with warnings.catch_warnings():
            # 소스 글 속 역슬래시 경고는 이 그물이 볼 것이 아니다.
            warnings.simplefilter("ignore", DeprecationWarning)
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(path.read_text(encoding="utf-8"))
        yield relative, tree


def _owned_nodes(tree: ast.AST) -> Iterator[tuple[str, ast.AST]]:
    """(감싼 가장 안쪽 함수 이름 — 없으면 `<module>`, 노드)."""

    def walk(node: ast.AST, owner: str) -> Iterator[tuple[str, ast.AST]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                yield from walk(child, child.name)
                continue
            yield owner, child
            yield from walk(child, owner)

    yield from walk(tree, "<module>")


@functools.cache
def _seed() -> Mapping[str, pd.DataFrame]:
    return build_builtin_seed_dataset().reference_tables


def _seed_tables() -> dict[str, pd.DataFrame]:
    return dict(_seed())


def _declarable_process(tables: Mapping[str, pd.DataFrame]) -> str:
    """시드에서 소요기준 WF · `WF 구분` Core 경로를 가진 첫 공정 — 선언이 결과를 바꾸는 공정."""
    reqb = tables["RQ_REQB"]
    wafer = reqb["소요기준"].astype("string").str.strip().str.upper().isin(["WF", "WAFER"])
    core = reqb["WF 구분"].astype("string").str.strip().str.casefold().eq("core")
    processes = sorted(set(reqb.loc[wafer & core, "공정"].astype(str)))
    assert processes, "시드에 WF Core 경로가 없다 — 견본이 바뀌었다"
    return processes[0]


def _process_load(required: pd.DataFrame, process: str, *, inside: bool) -> float:
    picked = required["공정"].astype(str).eq(process)
    return float(required.loc[picked if inside else ~picked, "부하량"].sum())


# ----------------------------------------------------------------- 빈 선언의 키는 그대로


@pytest.mark.parametrize("token", ["0f3a9c", pristine_content_token(7)], ids=["edit", "pristine"])
def test_an_empty_declaration_leaves_every_key_as_it_was(token: str) -> None:
    """빈 선언이면 계산 토큰이 내용 토큰 그대로이고 세 빌더 · 편집표 키가 선언을 모르던 꼴이다 —
    선언을 저장하기 전에는 어느 칸도 옮겨 앉지 않는다."""
    scenario = {"content_token": token}
    order = pd.DataFrame({"순서": [1, 2], "값": ["DEMO-A", "DEMO-B"]})
    start, end = _MONTHS

    assert sc.calculation_token(token, NO_ROUTE_LOAD_EXCEPTIONS) is token
    assert sc.calculation_token(token, {}) == token
    assert sc.token_route_exceptions(token) == {}
    assert sc.scenario_cache_key(
        7, scenario, start, end, route_exceptions=NO_ROUTE_LOAD_EXCEPTIONS
    ) == (7, token, start, end)
    assert sc.scenario_content_key(7, scenario, start, end) == (7, token, start, end)
    assert sc.full_scenario_cache_key(7, token, route_exceptions=NO_ROUTE_LOAD_EXCEPTIONS) == (
        7,
        token,
    )
    assert sc.build_home_simulation_cache_key(
        reference_version=7,
        scenario_token=token,
        start_month=start,
        end_month=end,
        display_order=order,
        route_exceptions=NO_ROUTE_LOAD_EXCEPTIONS,
    ) == (7, token, start, end, sc.display_order_digest(order))


# ----------------------------------------------------------------- 접기 · 풀기


def test_a_declaration_folds_into_the_calculation_token_and_unfolds_back() -> None:
    """선언은 내용 토큰 뒤에 정규 글로 붙고 거꾸로 풀린다. 앞뒤 공백 · 대소문자만 다른 표기는 같은
    토큰이고(판 지문과 같은 정규화), `pristine-` 판정은 접은 뒤에도 그대로다. 편집표 키는 선언을
    접지 않는다."""
    token = pristine_content_token(3)
    folded = sc.calculation_token(token, _DECLARED)

    assert (
        folded == f"{token}{sc.ROUTE_EXCEPTION_TOKEN_MARK}{route_load_declaration_json(_DECLARED)}"
    )
    assert is_pristine_content_token(folded)
    assert sc.token_route_exceptions(folded) == normalize_route_load_declaration(_DECLARED)
    assert sc.calculation_token(token, {"  demo-p1 ": BUFFER_X_CORE_CHIP}) == folded

    scenario = {"content_token": token}
    declared = sc.scenario_cache_key(3, scenario, *_MONTHS, route_exceptions=_DECLARED)
    assert declared == (3, folded, *_MONTHS)
    assert sc.scenario_content_key(3, scenario, *_MONTHS) == (3, token, *_MONTHS)
    assert sc.full_scenario_cache_key(3, token, route_exceptions=_DECLARED) == (3, folded)


def test_a_folded_token_with_an_unknown_formula_stops() -> None:
    """키에서 푼 선언도 다시 검증한다 — 코드가 모르는 산식 id 는 일반 산식으로 떨어지지 않고
    멈춘다."""
    token = f"0f3a9c{sc.ROUTE_EXCEPTION_TOKEN_MARK}" + '{"demo-p1":"demo_unknown"}'
    with pytest.raises(ValueError, match="모르는 산식"):
        sc.token_route_exceptions(token)


def test_the_full_period_cell_and_the_period_check_unfold_the_declaration_from_the_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """전체 기간 칸 · 조회기간 오류 칸은 선언을 따로 받지 않고 키의 계산 토큰에서 푼다. 같은 내용의
    두 선언은 두 칸이다 — 두 번째 부름은 칸에 적중한다."""
    seen: list[dict[str, str]] = []

    def probe(
        scenario_tables: Mapping[str, pd.DataFrame],
        reference_tables: Mapping[str, pd.DataFrame],
        *,
        route_exceptions: RouteLoadDeclaration,
    ) -> sc.CapacityOutcome:
        del scenario_tables, reference_tables
        seen.append(dict(route_exceptions))
        return sc.CapacityOutcome(None, None, f"칸 {len(seen)}")

    monkeypatch.setattr(sc, "full_capacity_outcome", probe)
    token = f"test-keys-{uuid4().hex}"
    plain = sc.full_scenario_cache_key(1, token, route_exceptions=NO_ROUTE_LOAD_EXCEPTIONS)
    declared = sc.full_scenario_cache_key(1, token, route_exceptions=_DECLARED)

    outcomes = [
        sc.get_full_capacity_outcome(key, _scenario_tables={}, _reference_tables={})
        for key in (plain, declared, declared)
    ]

    assert seen == [{}, normalize_route_load_declaration(_DECLARED)]
    assert [outcome.error for outcome in outcomes] == ["칸 1", "칸 2", "칸 2"]

    periods: list[dict[str, str]] = []

    def period_probe(
        tables: Mapping[str, pd.DataFrame], route_exceptions: RouteLoadDeclaration
    ) -> sc.CapacityOutcome:
        del tables
        periods.append(dict(route_exceptions))
        return sc.CapacityOutcome(None, None, None)

    monkeypatch.setattr(sc, "_capacity_outcome", period_probe)
    seed = _seed_tables()
    months = sorted(int(month) for month in pd.to_numeric(seed["RQ_UPEH"]["생산계획년월"]).unique())
    sc.get_period_capacity_error(
        (1, declared[1], months[0], months[-1]), _scenario_tables=seed, _reference_tables=seed
    )
    assert periods == [normalize_route_load_declaration(_DECLARED)]


def test_two_declarations_take_two_cells_and_two_results() -> None:
    """같은 시나리오 내용이라도 선언이 다르면 칸도 결과도 다르다 — 선언 공정의 경로 부하량만
    바뀌고 다른 공정은 그대로다. 접은 키의 칸은 캐시 없는 같은 계산과 같다."""
    tables = _seed_tables()
    process = _declarable_process(tables)
    declaration = {process: BUFFER_X_CORE_CHIP}
    token = f"test-keys-{uuid4().hex}"
    plain_key = sc.full_scenario_cache_key(1, token, route_exceptions=NO_ROUTE_LOAD_EXCEPTIONS)
    declared_key = sc.full_scenario_cache_key(1, token, route_exceptions=declaration)
    assert plain_key != declared_key

    plain = sc.get_full_capacity_outcome(
        plain_key, _scenario_tables=tables, _reference_tables=tables
    )
    declared = sc.get_full_capacity_outcome(
        declared_key, _scenario_tables=tables, _reference_tables=tables
    )

    assert plain.error is None and declared.error is None
    assert plain.required_equipment is not None and declared.required_equipment is not None
    assert _process_load(declared.required_equipment, process, inside=True) != pytest.approx(
        _process_load(plain.required_equipment, process, inside=True)
    )
    assert _process_load(declared.required_equipment, process, inside=False) == pytest.approx(
        _process_load(plain.required_equipment, process, inside=False)
    )
    direct = sc.full_capacity_outcome(tables, tables, route_exceptions=declaration)
    assert direct.required_equipment is not None
    pd.testing.assert_frame_equal(
        declared.required_equipment.reset_index(drop=True),
        direct.required_equipment.reset_index(drop=True),
    )


# ----------------------------------------------------------------- 기본값 없음


_REQUIRED_DECLARATION: tuple[Callable[..., Any], ...] = (
    calculate_required_equipment,
    sc.get_capacity_and_demand,
    sc._capacity_outcome,
    sc.full_capacity_outcome,
    extra_process_merge.capacity_outcome,
    extra_process_merge.process_rows_frame,
    extra_process_merge.load_lines,
    sc.calculation_token,
    sc.scenario_cache_key,
    sc.full_scenario_cache_key,
    sc.build_home_simulation_cache_key,
)


@pytest.mark.parametrize(
    "function", _REQUIRED_DECLARATION, ids=[item.__name__ for item in _REQUIRED_DECLARATION]
)
def test_the_declaration_has_no_default_on_the_required_equipment_path(
    function: Callable[..., Any],
) -> None:
    """소요대수로 가는 함수와 계산 키 빌더는 선언 칸에 기본값이 없다 — 호출처가 선언을 빠뜨리면
    mypy 가 잡는다(빈 선언도 적어서 넘긴다)."""
    parameter = inspect.signature(function).parameters.get("route_exceptions")
    assert parameter is not None, f"{function.__name__} 에 선언 칸이 없다"
    assert parameter.default is inspect.Parameter.empty, f"{function.__name__} 선언에 기본값"


# ----------------------------------------------------------------- 빈 선언을 적는 자리

# 빈 선언을 그대로 적어도 되는 자리 — 파일 전체(`None`) 또는 (파일, 함수) 와 그 수. 시험(`tests/`)은
# 이 그물 밖이다.
# - 검수용 합성 견본 두 스크립트 — 합성 견본에는 선언이 없다.
# - `capacity_stop` — 등록 R-07 의 멈춤만 본다. 선언은 멈춤을 만들지도 풀지도 않으므로(겹친 바탕도
#   그 줄만 빼고 알린다 — 2026-11-22 답 Q13) 빈 선언으로 돈다. 새 산식이 멈춤을 낼 수 있게 되면
#   그 판정에 선언을 넘기고 이 줄을 지운다(아래 등록 R-07 판정 시험).
_PERMANENT_EMPTY: Mapping[tuple[str, str | None], int | None] = {
    ("scripts/review_sample_sim.py", None): None,
    ("scripts/review_sample_equip.py", None): None,
    ("src/capa_simulation/services/extra_process_merge.py", "capacity_stop"): 1,
}
# 아직 부하 예외 선언을 읽지 않는 자리 — 화면 · 저장/발행/입력 점검 · 입장 Summary · HOME · 자동
# 갱신 · 확인 스크립트가 선언을 읽어 넘기면 그 줄을 지운다. 끝에는 이 목록이 빈다(AGENTS 6장
# 「공정별 부하 산출 예외」). 줄을 더하지 않는다 — 새 계산 자리는 처음부터 선언을 읽어 넘긴다.
_NOT_YET_READ: Mapping[tuple[str, str], int] = {
    ("app_pages/available_equipment_status.py", "<module>"): 1,
    ("app_pages/calculation_result.py", "<module>"): 1,
    ("app_pages/home.py", "<module>"): 1,
    ("app_pages/load_conversion.py", "_render_uncounted_demand_after_apply"): 1,
    ("app_pages/process_capa_detail.py", "home_advance_ratio"): 1,
    ("app_pages/standard_target_capa.py", "<module>"): 1,
    ("app_pages/static_capa.py", "<module>"): 1,
    ("app_pages/wip_status.py", "<module>"): 2,
    ("scripts/benchmark_upeh_assumption.py", "measure"): 1,
    ("scripts/inspect_real_data_checks.py", "_required_from"): 1,
    ("scripts/inspect_revision_calculations.py", "calculate"): 1,
    ("src/capa_simulation/auto_official_update_runner.py", "_execute"): 1,
    ("src/capa_simulation/auto_official_update_runner.py", "_publish_filtered_revision"): 1,
    ("src/capa_simulation/components/capacity_gate.py", "derived_save_verdict"): 1,
    ("src/capa_simulation/components/capacity_gate.py", "input_check_verdict"): 1,
    ("src/capa_simulation/components/capacity_gate.py", "official_publish_verdict"): 1,
    ("src/capa_simulation/components/capacity_gate.py", "revision_save_verdict"): 1,
    ("src/capa_simulation/components/intro_summary.py", "_build"): 1,
    ("src/capa_simulation/components/required_shortening_panel.py", "_lob_rows"): 1,
    ("src/capa_simulation/components/shortening_source.py", "load_shortening_demand"): 1,
    ("src/capa_simulation/extra_process_intake.py", "preview_pack"): 1,
    ("src/capa_simulation/page_bootstrap.py", "process_page_inputs"): 1,
    ("src/capa_simulation/scenario_state.py", "_retire_edit_cell"): 1,
}


def _empty_declaration_uses() -> Counter[tuple[str, str]]:
    uses: Counter[tuple[str, str]] = Counter()
    for path, tree in _sources():
        for owner, node in _owned_nodes(tree):
            if (
                isinstance(node, ast.Name)
                and node.id == "NO_ROUTE_LOAD_EXCEPTIONS"
                and isinstance(node.ctx, ast.Load)
            ):
                uses[(path, owner)] += 1
    return uses


def test_an_empty_declaration_is_written_out_only_where_it_is_allowed() -> None:
    """빈 선언(`NO_ROUTE_LOAD_EXCEPTIONS`)을 그대로 적는 자리는 위 두 목록과 수까지 같다 — 계산
    자리가 선언을 읽지 않고 빈 선언으로 덮는 일이 말없이 늘지 않는다. 계산 서비스
    (`simulation_cache` · `required_equipment`)는 빈 선언을 적지 않는다."""
    uses = _empty_declaration_uses()
    whole_files = {path for (path, owner), _ in _PERMANENT_EMPTY.items() if owner is None}
    counted = {
        key: count
        for key, count in uses.items()
        if key[0] not in whole_files and key not in _PERMANENT_EMPTY
    }
    assert counted == dict(_NOT_YET_READ)
    for key, expected in _PERMANENT_EMPTY.items():
        if key[1] is not None:
            assert uses.get((key[0], key[1]), 0) == expected, key
    assert not any(path == SIMULATION_CACHE for path, _ in uses)
    assert not any(path.endswith("services/required_equipment.py") for path, _ in uses)


# ----------------------------------------------------------------- 손 키 없음


def _hand_keys(tree: ast.AST) -> list[str]:
    """(판, 토큰) 꼴로 손으로 지은 튜플 — 첫 칸이 판(`version`), 둘째 칸이 토큰(`token`)인 글."""
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Tuple) or len(node.elts) < 2:
            continue
        first, second = node.elts[0], node.elts[1]
        if isinstance(first, ast.Constant) or isinstance(second, ast.Constant):
            continue
        if "version" in ast.unparse(first).lower() and "token" in ast.unparse(second).lower():
            found.append(ast.unparse(node))
    return found


def test_the_hand_key_detector_sees_the_shapes_it_guards() -> None:
    """그물이 실제로 잡는지 — 화면 · 검사가 짓던 꼴은 잡고, 글자 튜플은 잡지 않는다."""
    caught = _hand_keys(
        ast.parse(
            "a = (reference_version, active_scenario['content_token'])\n"
            "b = (context.reference_version, str(scenario['content_token']))\n"
            "c = (old_version, old_token)\n"
            "d = (reference_version, pristine_content_token(reference_version))\n"
            "e = ('reference_version', 'content_token')\n"
            "f = (SCHEMA_VERSION, theme_mode, scenario_key)\n"
        )
    )
    assert len(caught) == 4


def test_no_calculation_key_is_built_by_hand_outside_the_cache_module() -> None:
    """전체 기간 칸 · 입력 점검 칸 · 편집본 칸 걷기의 키는 `full_scenario_cache_key` 로만 짓는다 —
    손으로 지은 (판, 토큰) 튜플은 선언을 접지 않아 다른 선언의 칸에 묶인다."""
    offenders = {
        path: keys
        for path, tree in _sources()
        if path != SIMULATION_CACHE and (keys := _hand_keys(tree))
    }
    assert offenders == {}


# ----------------------------------------------------------------- 편집표 키


def test_only_the_two_edit_screens_use_the_content_key() -> None:
    """선언을 접지 않는 편집표 키(`scenario_content_key`)는 생산 계획 · 기준 정보 편집표 두 자리만
    쓴다 — 계산 칸에 넘기면 선언이 키에 실리지 않는다."""
    calls: Counter[str] = Counter()
    for path, tree in _sources():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name == "scenario_content_key":
                calls[path] += 1
    assert dict(calls) == {"app_pages/load_conversion.py": 1, "app_pages/reference_data.py": 1}


# ----------------------------------------------------------------- 등록 R-07 판정


def _stopped(tables: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """가동률에서 마지막 달을 뺀 표 — 계산이 멈춘다."""
    run_rate = tables["RQ_RUN_RATE"]
    months = pd.to_numeric(run_rate["생산계획년월"])
    return {**tables, "RQ_RUN_RATE": run_rate.loc[months.ne(months.max())].reset_index(drop=True)}


@pytest.mark.parametrize("variant", ["seed", "stopped"])
def test_the_registration_stop_reads_the_same_with_or_without_a_declaration(
    variant: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """등록 R-07 판정(`capacity_stop`)은 빈 선언으로 돈다 — 선언을 넘겨도 멈춤 판정이 같다는 것이
    그 근거다. 시드의 선언 공정은 선언이 결과를 실제로 바꾸는 공정이다(바탕 없음 줄이 선다). 한 키에
    바탕이 둘인 겹침도 멈추지 않고 그 줄만 뺀다는 것은 계산 단위에서 붙든다
    (`tests/test_route_load_exceptions.py` 의 겹친 바탕 시험)."""
    seed = _seed_tables()
    process = _declarable_process(seed)
    declaration = {process: BUFFER_X_CORE_CHIP}
    tables = seed if variant == "seed" else _stopped(seed)
    off = extra_process_merge.capacity_stop(tables)
    original = extra_process_merge.capacity_outcome
    reached: list[int] = []

    def declared(
        frames: Mapping[str, pd.DataFrame], *, route_exceptions: RouteLoadDeclaration
    ) -> sc.CapacityOutcome:
        assert not route_exceptions
        outcome = original(frames, route_exceptions=declaration)
        if outcome.required_equipment is not None:
            reached.append(
                required_exclusion_counts(outcome.required_equipment).basis_missing_routes
            )
        return outcome

    monkeypatch.setattr(extra_process_merge, "capacity_outcome", declared)
    on = extra_process_merge.capacity_stop(tables)

    assert on == off
    if variant == "seed":
        assert off is None and reached and reached[0] > 0
    else:
        assert off is not None
