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
    official_publish_verdict,
    revision_save_verdict,
)
from capa_simulation.persistence.repository import REVISION_TABLES, DuckDBScenarioRepository
from capa_simulation.scenario_state import ActiveScenario, pristine_content_token
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset

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
