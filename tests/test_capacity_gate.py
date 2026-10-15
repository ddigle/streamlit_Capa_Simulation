# Purpose: 리비전 저장·공식 발행이 시나리오 전체 기간 Capa 계산을 먼저 검사하는지 검증한다.

"""**오류를 만든 사람이 그 자리에서 보게 한다.**

계산 페이지만 막으면 오류는 HOME 을 연 사람 — 대개 고칠 수 없는 사람 — 이 처음 본다.
저장·발행 순간에 같은 계산을 돌려, 편집이 깨뜨린 것은 저장을 막고 공식버전은 계산되는
리비전만 받는다. 편집 전부터 깨져 있던 것은 저장을 허락한다 — 막으면 오류가 여럿일 때
하나씩 고쳐 가며 저장할 길이 없다.
"""

from __future__ import annotations

import ast
import random
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from capa_simulation.components.capacity_gate import (
    derived_save_verdict,
    official_publish_verdict,
    revision_save_verdict,
)
from capa_simulation.persistence.models import ScenarioCreate, ScenarioPreset, ScenarioSnapshot
from capa_simulation.persistence.repository import REVISION_TABLES, DuckDBScenarioRepository
from capa_simulation.scenario_state import ActiveScenario, pristine_content_token
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.scenario_month_merge import merge_scenario_months
from capa_simulation.services.scenario_transform import MONTHLY_TABLES, NON_MONTHLY_TABLES
from capa_simulation.services.simulation_cache import (
    full_capacity_outcome,
    get_full_capacity_outcome,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def tables() -> dict[str, pd.DataFrame]:
    return dict(build_builtin_seed_dataset().reference_tables)


def _broken(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """가동률에서 마지막 달을 뺀다. 가동률은 중립값이 없어 행이 없으면 하드 오류다."""
    run_rate = tables["RQ_RUN_RATE"]
    months = pd.to_numeric(run_rate["생산계획년월"])
    return {**tables, "RQ_RUN_RATE": run_rate.loc[months.ne(months.max())].reset_index(drop=True)}


def _version() -> int:
    # st.cache_data 는 프로세스 전역이다. 테스트마다 다른 칸을 쓰게 한다.
    return random.randrange(10**12, 10**15)


def _edited(version: int, tables: dict[str, pd.DataFrame]) -> ActiveScenario:
    return {
        "reference_version": version,
        "revision": 2,
        "content_token": uuid4().hex,
        "tables": tables,
    }


def test_a_scenario_that_calculates_saves_without_a_word(tables: dict[str, pd.DataFrame]) -> None:
    version = _version()

    verdict = revision_save_verdict(version, _edited(version, tables), tables)

    assert verdict.allowed and verdict.message is None


def test_an_edit_that_breaks_the_calculation_is_not_saved(
    tables: dict[str, pd.DataFrame],
) -> None:
    version = _version()

    verdict = revision_save_verdict(version, _edited(version, _broken(tables)), tables)

    assert not verdict.allowed
    assert verdict.message is not None and "이번 편집이 깨뜨린" in verdict.message


def test_an_error_that_was_already_there_does_not_block_the_save(
    tables: dict[str, pd.DataFrame],
) -> None:
    """막으면 오류가 여럿일 때 하나씩 고쳐 가며 저장할 길이 없다. 대신 발행은 막힌다고 말한다."""
    version = _version()
    broken = _broken(tables)

    edited = revision_save_verdict(version, _edited(version, broken), broken)
    untouched = revision_save_verdict(
        version,
        {**_edited(version, broken), "content_token": pristine_content_token(version)},
        broken,
    )

    for verdict in (edited, untouched):
        assert verdict.allowed
        assert verdict.message is not None and "공식버전으로 지정할 수 없습니다" in verdict.message


def test_the_uncached_core_judges_like_the_cached_check(tables: dict[str, pd.DataFrame]) -> None:
    """배경 회차(공식버전 자동 갱신)가 쓰는 순수 코어는 화면 검사와 같은 결과를 낸다."""
    for candidate in (tables, _broken(tables)):
        version = _version()
        cached = get_full_capacity_outcome(
            (version, pristine_content_token(version)),
            _scenario_tables=candidate,
            _reference_tables=candidate,
        )
        uncached = full_capacity_outcome(candidate, candidate)

        assert uncached.error == cached.error
        if cached.required_equipment is not None:
            assert uncached.required_equipment is not None
            pd.testing.assert_frame_equal(uncached.required_equipment, cached.required_equipment)


def test_only_a_calculating_revision_can_become_official(tmp_path: Path) -> None:
    """공식버전은 모두의 첫 화면이다. 계산이 안 되면 지정하는 순간 모두의 HOME 이 멈춘다."""
    from capa_simulation.application_bootstrap import ensure_initial_scenario

    database = tmp_path / "gate.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    release = ensure_initial_scenario(repository).release
    assert release is not None
    snapshot = repository.load_revision(release.revision_id)
    broken = repository.save_revision(
        snapshot.scenario.scenario_id,
        _broken({name: snapshot.tables[name] for name in REVISION_TABLES}),
        snapshot.preset,
        revision_name="가동률 한 달 누락",
        parent_revision_id=release.revision_id,
    )

    assert official_publish_verdict(str(database), release.revision_id).allowed
    refused = official_publish_verdict(str(database), broken.revision.revision_id)
    assert not refused.allowed
    assert refused.message is not None and "RQ_RUN_RATE" in refused.message


def _vital_broken(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """여유율에서 마지막 달을 뺀다. `_broken` 과 **다른** 오류로 멈춘다."""
    vital = tables["RQ_VITAL"]
    months = pd.to_numeric(vital["생산계획년월"])
    return {**tables, "RQ_VITAL": vital.loc[months.ne(months.max())].reset_index(drop=True)}


def test_a_different_error_after_the_edit_is_not_called_the_old_one(
    tables: dict[str, pd.DataFrame],
) -> None:
    """편집 전 오류와 다른 오류를 「편집 전부터 있던 오류」라 부르지 않는다(사내 감사 E7).

    편집 전·후가 둘 다 실패한다는 것만 보면 이번 편집이 새로 깬 것도 「편집 전부터 있던 오류」로
    저장된다. 계산은 첫 오류에서 멈추므로 다른 오류가 곧 새로 깬 것은 아니다(앞 오류를 고쳐 가려져
    있던 오류가 드러날 수 있다). 그래서 막지 않고 문구로 가른다.
    """
    version = _version()

    verdict = revision_save_verdict(
        version, _edited(version, _vital_broken(tables)), _broken(tables)
    )

    assert verdict.allowed
    assert verdict.message is not None
    assert "편집 전부터 있던" not in verdict.message
    assert "편집 전과 다른" in verdict.message
    assert "RQ_VITAL" in verdict.message and "RQ_RUN_RATE" in verdict.message
    assert "공식버전으로 지정할 수 없습니다" in verdict.message


def _vital_blank(tables: dict[str, pd.DataFrame], count: int) -> dict[str, pd.DataFrame]:
    """여유율 앞 `count` 행을 비운다. 건수만 다른 같은 오류(「… 값이 빈 …: N건」)를 만든다."""
    vital = tables["RQ_VITAL"].copy()
    vital["편중률"] = vital["편중률"].astype("object")
    vital.loc[vital.index[:count], "편중률"] = None
    return {**tables, "RQ_VITAL": vital}


def test_the_same_error_with_another_count_is_not_called_a_different_one(
    tables: dict[str, pd.DataFrame],
) -> None:
    """같은 오류의 건수·예시만 달라지면 「편집 전과 다른 오류」라 부르지 않는다.

    오류문은 건수와 예시 키를 싣는다. 빈 칸 둘 가운데 하나를 고친 편집을 문자열로만 견주면 「새로
    깨뜨렸거나 가려져 있던 오류가 드러난 것」이 되는데, 둘 다 아니다 — 같은 오류가 덜 남았다.
    """
    version = _version()

    verdict = revision_save_verdict(
        version, _edited(version, _vital_blank(tables, 1)), _vital_blank(tables, 2)
    )

    assert verdict.allowed
    assert verdict.message is not None
    assert "편집 전과 다른" not in verdict.message
    assert "같은 종류" in verdict.message
    assert "1건" in verdict.message and "2건" in verdict.message
    assert "공식버전으로 지정할 수 없습니다" in verdict.message


def _density_broken(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """계획이 있는 제품 하나의 `구분_EQ` 를 0 으로. 대당 Capa·소요대수는 이 값을 쓰지 않는다."""
    plan = tables["RQ_PKG_PLAN"]
    planned = plan.loc[pd.to_numeric(plan["생산수량"]).gt(0)].iloc[0]
    chip_eq = tables["RQ_CHIP_EQ"].copy()
    target = chip_eq["제품정보"].eq(planned["제품정보"]) & chip_eq["Stack"].eq(planned["Stack"])
    assert target.any()
    chip_eq.loc[target, "구분_EQ"] = 0.0
    return {**tables, "RQ_CHIP_EQ": chip_eq}


def test_an_edit_that_stops_the_home_density_is_not_saved(
    tables: dict[str, pd.DataFrame],
) -> None:
    """HOME 의 Density 환산도 저장 검사가 돌린다(사내 감사 E6).

    계획이 있는 제품의 `구분_EQ` 가 0 이하면 HOME 이 「RQ_CHIP_EQ.구분_EQ 값은 0보다 커야」로
    멈춘다. 대당 Capa·소요대수만 돌리는 검사는 이 값을 보지 않는다.
    """
    version = _version()

    verdict = revision_save_verdict(version, _edited(version, _density_broken(tables)), tables)

    assert not verdict.allowed
    assert verdict.message is not None and "RQ_CHIP_EQ.구분_EQ" in verdict.message


def test_a_revision_whose_density_stops_cannot_become_official(tmp_path: Path) -> None:
    """공식버전이 되는 순간 모두의 HOME 이 Density 에서 멈춘다. 발행 검사가 전체 기간으로 돌린다."""
    from capa_simulation.application_bootstrap import ensure_initial_scenario

    database = tmp_path / "gate.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    release = ensure_initial_scenario(repository).release
    assert release is not None
    snapshot = repository.load_revision(release.revision_id)
    broken = repository.save_revision(
        snapshot.scenario.scenario_id,
        _density_broken({name: snapshot.tables[name] for name in REVISION_TABLES}),
        snapshot.preset,
        revision_name="구분_EQ 0",
        parent_revision_id=release.revision_id,
    )

    refused = official_publish_verdict(str(database), broken.revision.revision_id)

    assert not refused.allowed
    assert refused.message is not None and "RQ_CHIP_EQ.구분_EQ" in refused.message


def _without_chip_qty(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """한 제품의 Chip 구성을 뺀다 — 그 제품 계획은 부하량에서 빠지지만 계산은 멈추지 않는다."""
    chip = tables["RQ_CHIP_QTY"]
    product = str(chip["제품정보"].iloc[-1])
    return {**tables, "RQ_CHIP_QTY": chip.loc[chip["제품정보"].ne(product)].reset_index(drop=True)}


def _plan_off_route(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """한 제품의 계획 Capa Code 를 경로에 없는 값으로 바꾼다 — 그 부하는 어느 공정에도 안 닿는다."""
    plan = tables["RQ_PKG_PLAN"].copy()
    product = plan["제품정보"].iloc[-1]
    plan.loc[plan["제품정보"].eq(product), "Capa Code"] = "DEMO_NO_ROUTE"
    return {**tables, "RQ_PKG_PLAN": plan}


def _route_without_capacity(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """한 공정의 UPEH 를 뺀다 — 부하가 있는 그 경로는 대당 Capa 가 없어 소요대수에서 빠진다."""
    upeh = tables["RQ_UPEH"]
    process = upeh["공정"].iloc[-1]
    return {**tables, "RQ_UPEH": upeh.loc[upeh["공정"].ne(process)].reset_index(drop=True)}


@pytest.mark.parametrize(
    "edit,phrase",
    [
        (_without_chip_qty, "기준정보가 없어 부하량에서 빠진 계획"),
        (_plan_off_route, "RQ_REQB 경로에 닿지 않은 계획 부하"),
        (_route_without_capacity, "대당 Capa 가 없어 뺀 부하 경로"),
    ],
    ids=["load_exclusion", "unrouted_load", "route_without_capacity"],
)
def test_a_save_that_leaves_demand_out_of_the_requirement_says_how_much(
    tables: dict[str, pd.DataFrame], edit: object, phrase: str
) -> None:
    """P1·P2·P3 — 계산은 되지만 소요대수에 들지 않은 수요가 있으면 저장은 하되 몇 건인지 말한다.

    말하지 않으면 확보율이 그만큼 높게 나온 리비전이 아무 표시 없이 저장·발행된다.
    """
    assert callable(edit)
    version = _version()

    verdict = revision_save_verdict(version, _edited(version, edit(tables)), tables)

    assert verdict.allowed
    assert verdict.message is not None and phrase in verdict.message
    assert "시나리오 전체 기간" in verdict.message


def _pkg_route_on_one_product(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """한 제품의 한 공정 경로를 소요기준 PKG·WF 구분 BUFFER 로 바꾼다(경로와 UPEH 를 함께).

    사내 실데이터 구조와 같은 꼴이다 — PKG 경로는 한 제품군(HBM)에만 있고, 다른 제품(EDP-TSV)에는
    PKG 공정이 없다.
    """
    reqb = tables["RQ_REQB"].copy()
    upeh = tables["RQ_UPEH"].copy()
    product = reqb["제품정보"].iloc[0]
    process = reqb["공정"].iloc[-1]
    for frame in (reqb, upeh):
        rows = frame["제품정보"].eq(product) & frame["공정"].eq(process)
        frame.loc[rows, ["소요기준", "WF 구분"]] = ["PKG", "BUFFER"]
    return {**tables, "RQ_REQB": reqb, "RQ_UPEH": upeh}


def test_a_product_without_pkg_routes_does_not_make_every_save_warn(
    tables: dict[str, pd.DataFrame],
) -> None:
    """R1 — PKG 경로가 없는 제품의 PKG 부하는 「경로 없는 계획」이 아니다. 세면 모든 저장·발행이
    늘 경고하고, 그 경고(「확보율이 실제보다 높게」)는 이 경우 사실도 아니다."""
    version = _version()

    edited = _edited(version, _pkg_route_on_one_product(tables))

    verdict = revision_save_verdict(version, edited, tables)

    assert verdict.allowed and verdict.message is None


def test_publishing_a_revision_with_demand_outside_the_requirement_warns(tmp_path: Path) -> None:
    """P1·P3 — 발행은 막지 않고 알린다. 공식버전은 모두의 첫 화면이라 지정하는 사람이 알아야
    한다."""
    from capa_simulation.application_bootstrap import ensure_initial_scenario

    database = tmp_path / "gate-warning.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    release = ensure_initial_scenario(repository).release
    assert release is not None
    snapshot = repository.load_revision(release.revision_id)
    dropped = repository.save_revision(
        snapshot.scenario.scenario_id,
        _without_chip_qty({name: snapshot.tables[name] for name in REVISION_TABLES}),
        snapshot.preset,
        revision_name="Chip 구성 한 제품 누락",
        parent_revision_id=release.revision_id,
    )

    clean = official_publish_verdict(str(database), release.revision_id)
    warned = official_publish_verdict(str(database), dropped.revision.revision_id)

    assert clean.allowed and clean.message is None
    assert warned.allowed
    assert warned.message is not None and "부하량에서 빠진 계획" in warned.message


@pytest.mark.parametrize(
    "module,function,write_call,gate_call",
    [
        (
            "src/capa_simulation/components/scenario_management.py",
            "_render_revision_save",
            "save_revision",
            "revision_save_verdict",
        ),
        (
            "src/capa_simulation/components/scenario_management.py",
            "_render_official",
            "publish_official_revision",
            "official_publish_verdict",
        ),
        (
            "src/capa_simulation/components/scenario_status.py",
            "_render_revision_save",
            "save_revision",
            "revision_save_verdict",
        ),
        (
            "src/capa_simulation/components/scenario_management.py",
            "_render_clone",
            "create_scenario",
            "revision_save_verdict",
        ),
        (
            "src/capa_simulation/components/scenario_transform.py",
            "render_derived_save",
            "create_scenario",
            "derived_save_verdict",
        ),
        # 공식버전 자동 갱신은 세션 없는 배경 회차라 캐시 래퍼 대신 같은 계산의 순수 코어를 쓴다.
        (
            "src/capa_simulation/auto_official_update_runner.py",
            "_publish_filtered_revision",
            "publish_official_revision",
            "full_capacity_outcome",
        ),
    ],
)
def test_every_write_path_checks_before_it_writes(
    module: str, function: str, write_call: str, gate_call: str
) -> None:
    """검사를 쓰기 **뒤에** 부르면 막는 척만 한다. 새 저장 경로가 생기면 여기에 더한다."""
    tree = ast.parse((PROJECT_ROOT / module).read_text(encoding="utf-8"))
    target = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == function
    )
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", ""): (
            node.lineno
        )
        for node in ast.walk(target)
        if isinstance(node, ast.Call)
    }

    assert gate_call in calls and write_call in calls
    assert calls[gate_call] < calls[write_call]


def _snapshot(
    repository: DuckDBScenarioRepository, name: str, tables: dict[str, pd.DataFrame]
) -> ScenarioSnapshot:
    months = sorted(int(month) for month in tables["RQ_UPEH"]["생산계획년월"].unique())
    return repository.create_scenario(
        ScenarioCreate(
            scenario_name=name,
            source_simulation_code=f"GATE-{uuid4().hex[:8]}",
            source_simulation_name=name,
            source_type="TEST",
            pipeline_version="test-v1",
        ),
        tables,
        ScenarioPreset(months[0], months[-1], ()),
    )


def test_a_derived_result_that_breaks_the_calculation_is_not_saved(
    tmp_path: Path, tables: dict[str, pd.DataFrame]
) -> None:
    """감사 D3: 월 머지·연도 Shift 결과도 리비전 저장과 같은 규칙으로 검사한다.

    원본이 모두 계산되는데 결과가 안 되면 이 변환이 깨뜨린 것이라 막는다. 원본부터 안 되면
    허락하되 공식버전으로 못 쓴다고 말한다.
    """
    repository = DuckDBScenarioRepository(tmp_path / "derived.duckdb")
    repository.initialize()
    healthy = _snapshot(repository, "계산되는 원본", tables)
    broken = _snapshot(repository, "계산 안 되는 원본", _broken(tables))

    assert derived_save_verdict(tables, (healthy,)) == (True, None)
    refused = derived_save_verdict(_broken(tables), (healthy,))
    assert not refused.allowed
    assert refused.message is not None and "RQ_RUN_RATE" in refused.message
    inherited = derived_save_verdict(_broken(tables), (healthy, broken))
    assert inherited.allowed
    assert inherited.message is not None and "공식버전으로 지정할 수 없습니다" in inherited.message


def test_a_merge_left_without_a_module_points_to_a_new_merge(tmp_path: Path) -> None:
    """감사 D2: 모듈수 결손은 앱에서 못 고친다 — 새 리비전도 물려받는다. 고칠 길을 말한다.

    사내 머지 ①을 줄인 것이다. 월 없는 표를 베이스 것만 남긴 채 저장된 머지 시나리오는 발행
    검사에서 「다시 머지하라」를 듣고, 같은 두 원본을 지금 규칙으로 다시 머지하면 발행된다.
    """
    process = "DEMO_Final_Test"
    seed = dict(build_builtin_seed_dataset().reference_tables)
    months = sorted(int(month) for month in seed["RQ_UPEH"]["생산계획년월"].unique())
    first, second = months[:6], months[6:]
    base_tables = {
        name: (
            frame.loc[frame["생산계획년월"].isin(first)].reset_index(drop=True)
            if name in MONTHLY_TABLES
            else frame.copy(deep=True)
        )
        for name, frame in seed.items()
    }
    for name in (*MONTHLY_TABLES, "RQ_MODULE"):
        if "공정" in base_tables[name].columns:
            frame = base_tables[name]
            base_tables[name] = frame.loc[frame["공정"].ne(process)].reset_index(drop=True)
    donor_tables = {
        name: (
            frame.loc[frame["생산계획년월"].isin(second)].reset_index(drop=True)
            if name in MONTHLY_TABLES
            else frame.copy(deep=True)
        )
        for name, frame in seed.items()
    }
    old_merge = merge_scenario_months(base_tables, donor_tables, second[0], second[-1])
    old_merge.update({name: base_tables[name] for name in NON_MONTHLY_TABLES})
    database = tmp_path / "module.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    stuck = _snapshot(repository, "옛 머지", old_merge)
    resaved = repository.save_revision(
        stuck.scenario.scenario_id,
        {name: stuck.tables[name] for name in REVISION_TABLES},
        stuck.preset,
        revision_name="고쳐 보려 한 리비전",
        parent_revision_id=stuck.revision.revision_id,
    )

    for revision_id in (stuck.revision.revision_id, resaved.revision.revision_id):
        refused = official_publish_verdict(str(database), revision_id)
        assert not refused.allowed
        assert refused.message is not None and "RQ_MODULE" in refused.message
        assert "다시 머지" in refused.message
    remerged = _snapshot(
        repository,
        "다시 머지",
        merge_scenario_months(base_tables, donor_tables, second[0], second[-1]),
    )
    assert official_publish_verdict(str(database), remerged.revision.revision_id).allowed


# 공식버전 발행(`publish_official_revision`)을 부르는 자리. 앞의 둘은 위 쓰기 경로 목록이 검사
# 차례를 보고, 내장 시드 부트스트랩은 검사하지 않는 길이다(빈 저장소의 합성 시드). 시나리오 관리
# 「자동 갱신」 탭의 「지금 실행」과 예약 스레드는 발행을 직접 부르지 않고 회차 함수
# (`run_auto_official_update` → `_publish_filtered_revision`)를 지난다.
PUBLISH_CALLERS = {
    ("src/capa_simulation/components/scenario_management.py", "_render_official"),
    ("src/capa_simulation/auto_official_update_runner.py", "_publish_filtered_revision"),
    ("src/capa_simulation/application_bootstrap.py", "ensure_initial_scenario"),
}


def test_no_new_path_publishes_an_official_version_around_the_check() -> None:
    """발행을 부르는 함수가 늘면 이 목록과 위 쓰기 경로 목록에 함께 더한다."""
    found: set[tuple[str, str]] = set()
    sources = [
        *sorted((PROJECT_ROOT / "src" / "capa_simulation").rglob("*.py")),
        *sorted((PROJECT_ROOT / "app_pages").glob("*.py")),
        PROJECT_ROOT / "app.py",
    ]
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.name == "publish_official_revision":
                continue
            if any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "publish_official_revision"
                for call in ast.walk(node)
            ):
                found.add((path.relative_to(PROJECT_ROOT).as_posix(), node.name))

    assert found == PUBLISH_CALLERS
