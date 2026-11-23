# Purpose: 기존 결과 대조 스크립트의 기본 데이터셋 고르기와 계획 행 갈래 출력을 본다.

"""`scripts/compare_legacy_results.py` 는 데이터셋의 원천 행과 그 시나리오의 리비전 1 을 맞춰 본다.

복제·월 병합·연도 이동은 원천 행을 남기지 않는다. 그것이 가장 최근이어도 기본 실행은 원천에서 온
데이터셋을 골라야 한다 — 그렇지 않으면 복제가 흔한 사외 DB 에서 기본 명령이 늘 「원천 행이
없습니다」로 끝난다. 정식 대조 셋 뒤에는 같은 Wafer 대조를 계획 행으로 접은 갈래와 그 진단이 찍힌다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from before_custom_copy import database_before_custom

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.persistence.models import ScenarioCreate
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.legacy_comparison import COMPARISONS, PLAN_ROW_METRIC

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import compare_legacy_results as compare  # noqa: E402


@pytest.fixture(scope="module")
def seeded_with_clone(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """내장 시드 + 그보다 나중에 만든 복제 하나. 시드 데이터셋 id 를 함께 돌려준다."""
    path = tmp_path_factory.mktemp("legacy") / "capa_simulation.duckdb"
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    release = ensure_initial_scenario(repository).release
    assert release is not None
    seed = repository.load_revision(release.revision_id, apply_global_display_order=False)
    repository.create_scenario(
        ScenarioCreate(
            scenario_name="clone",
            source_simulation_code="CODE-clone",
            source_simulation_name="clone",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="test",
        ),
        seed.tables,
        seed.preset,
        source_data=None,
        revision_tables=seed.tables,
    )
    with duckdb.connect(str(path), read_only=True) as connection:
        rows = connection.execute(
            "SELECT dataset_id, scenario_id, source_type FROM app_meta.dataset "
            "ORDER BY imported_at DESC"
        ).fetchall()
    # 복제가 더 최근이어야 이 시험이 뜻을 갖는다.
    assert [row[2] for row in rows][0] == "DUCKDB_SCENARIO_CLONE"
    seed_dataset = next(str(row[0]) for row in rows if row[1] == seed.scenario.scenario_id)
    return path, seed_dataset


def _run(monkeypatch: pytest.MonkeyPatch, database: Path) -> int:
    monkeypatch.setattr(sys, "argv", ["compare_legacy_results.py", "--database", str(database)])
    return compare.main()


def _printed_count(text: str, pattern: str) -> int:
    """찍힌 줄에서 `{:,}` 꼴의 수 하나를 읽는다."""
    found = re.search(pattern, text)
    assert found is not None, pattern
    return int(found.group(1).replace(",", ""))


def test_a_newer_clone_dataset_is_not_taken_by_default(
    seeded_with_clone: tuple[Path, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path, seed_dataset = seeded_with_clone

    code = _run(monkeypatch, path)

    assert code == 0
    first_line = capsys.readouterr().out.splitlines()[0]
    assert first_line.startswith(f"데이터셋 {seed_dataset} · 리비전 1 ")


def test_the_plan_row_fold_is_reported_after_the_formal_comparisons(
    seeded_with_clone: tuple[Path, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """정식 대조 셋 뒤에 「계획 행으로 접음」 Wafer 대조와 그 진단이 찍히고, CSV 에는 지표 이름이
    따로 든다.

    내장 시드는 계획 행과 경로 행에 같은 `WF수(매)` 를 싣는다 — 접어도 값 불일치가 없고, 계획 행이
    실제로 접혀 정식 Wafer 대조와 같은 수의 키가 기존값을 갖고 맞대어진다.
    """
    wafer = next(metric for metric in COMPARISONS if metric.legacy_column == "WF수(매)")
    path, _ = seeded_with_clone
    output = tmp_path / "legacy.csv"
    monkeypatch.setattr(
        sys,
        "argv",
        ["compare_legacy_results.py", "--database", str(path), "--output", str(output)],
    )

    assert compare.main() == 0

    text = capsys.readouterr().out
    labels = [line for line in text.splitlines() if line.startswith("[") and "]" in line]
    assert labels[-1] == f"[{PLAN_ROW_METRIC.label}]"
    section = text.split(f"[{PLAN_ROW_METRIC.label}]", 1)[1]
    formal = text.split(f"[{wafer.label}]", 1)[1].split("\n[", 1)[0]
    matched = _printed_count(section, r"대조 ([\d,]+)건")
    assert matched > 0
    assert matched == _printed_count(formal, r"대조 ([\d,]+)건")
    assert " · 값 불일치 0건 " in section
    assert "신규에만 있음 0건" in section
    assert _printed_count(section, r"계획 행 진단 — 접은 행 ([\d,]+)\(") > 0
    assert "Y 인데 공정 있음 0행" in section
    assert "계획 행 값 둘 이상 칸 0" in section
    written = pd.read_csv(output, encoding="utf-8-sig")
    assert PLAN_ROW_METRIC.label in set(written["지표"])
    folded = written.loc[written["지표"].eq(PLAN_ROW_METRIC.label)]
    assert not folded.empty
    assert not folded["값 불일치"].astype(bool).any()
    assert folded["기존값"].notna().all()


def test_without_a_source_dataset_it_says_so(
    seeded_with_clone: tuple[Path, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _ = seeded_with_clone
    path = tmp_path / "capa_simulation.duckdb"
    path.write_bytes(source.read_bytes())
    with duckdb.connect(str(path)) as connection:
        connection.execute("DELETE FROM raw_data.core_data")

    with pytest.raises(SystemExit, match="원천에서 온 데이터셋이 없습니다"):
        _run(monkeypatch, path)


def test_a_constant_source_custom_under_a_blank_revision_compares_like_a_blank_source(
    seeded_with_clone: tuple[Path, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """0039 전 등록분 — 리비전 표는 모두 빈 값 표지(`-`)인데 원천 `CUSTOM` 칸에 그때 값이 남아 있다.

    파생 전에 원천을 리비전에 맞춰(`source_custom_aligned`) 원천도 빈 칸인 사본과 같은 출력 · 같은
    상세 CSV 를 낸다. 맞추지 않으면 모든 키가 한쪽에만 남는다."""
    source, _ = seeded_with_clone
    printed: dict[str, str] = {}
    written: dict[str, pd.DataFrame] = {}
    for name in ("blank", "constant"):
        path = tmp_path / f"{name}.duckdb"
        path.write_bytes(source.read_bytes())
        if name == "constant":
            with duckdb.connect(str(path)) as connection:
                connection.execute('UPDATE raw_data.core_data SET "CUSTOM" = ?', ["DEMO_CUSTOM_A"])
        output = tmp_path / f"{name}.csv"
        monkeypatch.setattr(
            sys,
            "argv",
            ["compare_legacy_results.py", "--database", str(path), "--output", str(output)],
        )
        assert compare.main() == 0
        printed[name] = capsys.readouterr().out.replace(str(output), "<csv>")
        written[name] = pd.read_csv(output, encoding="utf-8-sig")

    assert printed["constant"] == printed["blank"]
    pd.testing.assert_frame_equal(written["constant"], written["blank"])
    assert "신규에만 있음 0건" in printed["blank"]
    assert written["blank"]["기존값"].notna().any()


def test_a_copy_before_the_custom_column_compares_like_the_migrated_copy(
    seeded_with_clone: tuple[Path, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """0039 전 사본(CUSTOM 칸 · 0039 기록 없음)도 마이그레이션하지 않고 0039 와 같은 뜻으로 채워
    대조한다 — 출력 · 상세 CSV 가 0039 뒤 사본과 같고, 첫 줄 바로 뒤에 `사본 0039 전` 한 줄만 더
    있다. 채우지 않으면 계산이 「필수 컬럼이 없습니다: CUSTOM」 으로 멈춘다."""
    source, seed_dataset = seeded_with_clone
    paths = {
        "migrated": source,
        "before": database_before_custom(source, tmp_path / "capa_simulation.duckdb"),
    }
    printed: dict[str, list[str]] = {}
    written: dict[str, pd.DataFrame] = {}
    for name, path in paths.items():
        output = tmp_path / f"{name}.csv"
        monkeypatch.setattr(
            sys,
            "argv",
            ["compare_legacy_results.py", "--database", str(path), "--output", str(output)],
        )
        assert compare.main() == 0
        printed[name] = capsys.readouterr().out.replace(str(output), "<csv>").splitlines()
        written[name] = pd.read_csv(output, encoding="utf-8-sig")

    before = printed["before"]
    assert before[0].startswith(f"데이터셋 {seed_dataset} · 리비전 1 ")
    assert before[1] == (
        "사본 0039 전 — 마이그레이션 최고 38 · CUSTOM 키 표는 0039 와 같이 모든 행을 빈 값 "
        "표지(-)로 채워 읽었다(DB 는 고치지 않는다)"
    )
    assert [before[0], *before[2:]] == printed["migrated"]
    pd.testing.assert_frame_equal(written["before"], written["migrated"])
