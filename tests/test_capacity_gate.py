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
