# Purpose: 원천 CSV 견줌 스크립트의 사본 강제 · 읽기 전용 · 수만 찍기 · 정확과 오차 안 셈을 본다.

"""`scripts/inspect_source_csv.py` 의 약속 — 운영 DB 자리는 열기 전에 거절한다, 사본은 읽기만 한다,
값 없이 수 · 같음/다름 · 계약 이름만 찍는다, 16표의 정확과 오차 안을 따로 센다. 출력은 리뷰 문서를
거쳐 사외로 나가므로 **새면 그대로 밖으로 나간다.**

합성 견본(내장 시드 — `tests/source_csv_samples.py`)의 시뮬레이션 코드 · 공정 · Capa Code · CUSTOM ·
파일 이름에 표지값(`ZZSENTINEL`)을 심어 출력에 없는지 본다. DB 쪽은 같은 견본을 원천 CSV 공급자로
지은 원천 묶음을 DB 길 원천 종류(`BIGDATAQUERY`)로 바꿔 화면 등록과 같은 함수로 저장한다 — 갈래마다
그 묶음의 칸 하나를 바꿔 둔다(끝자리 한 칸 · 작은 값의 상대 오차 · CUSTOM 조회문 상수).
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import numpy.typing as npt
import pandas as pd
import pytest
from source_csv_samples import demo_core_rows, source_csv_bytes

from capa_simulation.io.core_data_source import CoreDataBatch
from capa_simulation.io.source_csv import SourceCsvCoreDataProvider, summarize_source_csv
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_preset_state import full_data_scenario_preset
from capa_simulation.scenario_registration import save_bigdataquery_scenario
from capa_simulation.services.builtin_seed import load_builtin_display_order
from capa_simulation.services.core_data_pipeline import prepare_core_data_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import inspect_source_csv as script  # noqa: E402

SENTINEL = "ZZSENTINEL"
CODE = f"{SENTINEL}-SIM-1"
OTHER_CODE = f"{SENTINEL}-SIM-2"
# 원천 해시 · 16표 · 열이 모두 같을 때의 요약 줄.
ALIKE = (
    "전송용 요약: CSV견줌 원천행 같음 · 해시 같음 · 16표 정확 16/16 · 오차안 16/16 · 다른열 0 · "
    "CUSTOM뺌 정확 16/16 · 오차안 16/16"
)


def _rows(code: str = CODE) -> list[dict[str, str]]:
    """표지값을 심은 견본 행 — 공정 · Capa Code 앞에 표지, CUSTOM 은 부품마다 표지 값."""
    rows = demo_core_rows(code=code)
    for row in rows:
        row["CUSTOM"] = f"{SENTINEL}_CUSTOM_{row['Capa Code'][-1]}"
        row["Capa Code"] = f"{SENTINEL}-{row['Capa Code']}"
        if row["공정"]:
            row["공정"] = f"{SENTINEL}-{row['공정']}"
    return rows


def _csv(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / f"{SENTINEL}_원천_20261124.csv"
    path.write_bytes(data)
    return path


def _csv_batch(data: bytes, code: str = CODE) -> CoreDataBatch:
    summary = summarize_source_csv(io.BytesIO(data), file_id="demo-file")
    provider = SourceCsvCoreDataProvider(
        lambda: io.BytesIO(data), summary, simulation_name=f"{SENTINEL} 원천"
    )
    return provider.fetch(code)


def _copy(
    tmp_path: Path,
    data: bytes,
    edit: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    *,
    code: str = CODE,
) -> Path:
    """DB 사본 — 같은 견본의 원천 묶음(칸 하나를 `edit` 로 바꿈)을 DB 길 원천으로 등록한 것."""
    path = tmp_path / "e2e_copy" / "data" / "capa_simulation.duckdb"
    path.parent.mkdir(parents=True)
    batch = _csv_batch(data, code)
    frame = batch.frame.copy() if edit is None else edit(batch.frame.copy())
    db_batch = dataclasses.replace(batch, source_type="BIGDATAQUERY", frame=frame)
    prepared = prepare_core_data_dataset(db_batch, load_builtin_display_order())
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    save_bigdataquery_scenario(
        repository,
        prepared,
        full_data_scenario_preset(prepared.reference_tables),
        scenario_name=f"{SENTINEL} 시나리오",
        revision_name=f"{SENTINEL} 리비전",
        note=f"{SENTINEL} 메모",
    )
    return path


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = script.main(list(argv))
    return code, capsys.readouterr().out


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _summary(output: str) -> list[str]:
    return [line for line in output.splitlines() if line.startswith(script.SUMMARY_LABEL)]


# ---------------------------------------------------------------- 거절 · 읽기만


@pytest.mark.parametrize(
    "target",
    [
        PROJECT_ROOT / "data" / "capa_simulation.duckdb",
        PROJECT_ROOT / "data" / "temp" / "copy" / "capa_simulation.duckdb",
        PROJECT_ROOT / "data" / ".." / "data" / "other.duckdb",
    ],
    ids=["operational-db", "under-data", "dotted-path"],
)
def test_refuses_the_operational_database_place(
    target: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """사본 강제 — 운영 DB 자리(`settings.DUCKDB_PATH` · 저장소 `data/` 아래)는 CSV 도 DB 도 열기
    전에 거절한다(`inspect_revision_calculations.py` 와 같은 판정)."""

    def must_not_open(*_args: object, **_kwargs: object) -> duckdb.DuckDBPyConnection:
        raise AssertionError("운영 DB 자리는 열지 않는다")

    monkeypatch.setattr(duckdb, "connect", must_not_open)
    csv = _csv(tmp_path, source_csv_bytes(_rows()))

    code, output = _run(capsys, "--database", str(target), "--csv", str(csv))

    assert code == 2
    assert "운영 DB 자리" in output and "DB 를 열지 않았다" in output
    assert str(PROJECT_ROOT) not in output
    assert SENTINEL not in output


def test_the_place_rule_is_the_one_of_the_revision_calculation_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """운영 DB 를 `settings.DUCKDB_PATH` 로 옮겨 두어도 그 파일과 그 폴더는 거절하고 다른 폴더의
    사본은 받는다 — 두 사본 스크립트가 같은 판정을 쓴다."""
    import inspect_revision_calculations as revisions

    operational = tmp_path / "live" / "capa_simulation.duckdb"
    for module in (script, revisions):
        monkeypatch.setattr(module, "DUCKDB_PATH", operational)
    for candidate in (
        operational,
        operational.parent / "sibling.duckdb",
        tmp_path / "copy" / "capa_simulation.duckdb",
        PROJECT_ROOT / "data" / "x.duckdb",
    ):
        assert script.operational_path(candidate) == revisions.operational_path(candidate)
    assert script.operational_path(operational)
    assert not script.operational_path(tmp_path / "copy" / "capa_simulation.duckdb")


def test_the_database_and_the_csv_have_no_default(capsys: pytest.CaptureFixture[str]) -> None:
    for argv in ([], ["--database", "copy.duckdb"], ["--csv", "source.csv"]):
        with pytest.raises(SystemExit) as stopped:
            script.parse_args(argv)
        assert stopped.value.code == 2
    assert "--csv" in capsys.readouterr().err


def test_a_locked_database_says_to_use_a_copy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    data = source_csv_bytes(_rows())
    database = _copy(tmp_path, data)

    def locked(*_args: object, **_kwargs: object) -> duckdb.DuckDBPyConnection:
        raise duckdb.IOException(f"Could not set lock on file {SENTINEL}")

    monkeypatch.setattr(duckdb, "connect", locked)

    code, output = _run(capsys, "--database", str(database), "--csv", str(_csv(tmp_path, data)))

    assert code == 1
    assert "사본을 떠 `--database` 로 준다" in output
    assert SENTINEL not in output


def test_missing_files_stop_without_their_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = source_csv_bytes(_rows())
    database = _copy(tmp_path, data)

    code, output = _run(
        capsys, "--database", str(database), "--csv", str(tmp_path / f"{SENTINEL}.csv")
    )
    assert code == 2
    assert "`--csv` 파일이 없다" in output

    code, output = _run(
        capsys, "--database", str(tmp_path / "none.duckdb"), "--csv", str(_csv(tmp_path, data))
    )
    assert code == 2
    assert "`none.duckdb` 파일이 없다" in output
    assert str(tmp_path) not in output and SENTINEL not in output


# ---------------------------------------------------------------- 수만 · 요약 한 줄


def test_prints_counts_only_and_a_transfer_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """같은 원천이면 행 · 해시 · 16표 · 열이 모두 같다 — 출력은 수 · 같음/다름 · 계약 이름뿐이고
    사본은 바이트까지 그대로이며, `--output` 파일은 화면과 같은 글이다."""
    data = source_csv_bytes(_rows())
    database = _copy(tmp_path, data)
    before = _md5(database)
    target = tmp_path / "source_csv.md"
    target.write_text("STALE 지난 출력", encoding="utf-8")

    code, output = _run(
        capsys,
        "--database",
        str(database),
        "--csv",
        str(_csv(tmp_path, data)),
        "--output",
        str(target),
    )

    assert code == 0
    assert _summary(output) == [ALIKE]
    assert output.rstrip().splitlines()[-1] == ALIKE
    assert "- 원천 해시 같음" in output
    assert "DB 쪽 원천 종류 `BIGDATAQUERY` · 같은 코드 원천 데이터셋 1" in output
    assert SENTINEL not in output
    assert str(tmp_path) not in output
    assert _md5(database) == before
    written = target.read_text(encoding="utf-8")
    assert "STALE" not in written
    assert written.startswith("<!-- inspect_source_csv.py")
    assert written.strip() == output.strip()


def _nudge(
    column: str, change: Callable[[npt.NDArray[Any]], npt.NDArray[Any]]
) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """원천 묶음의 숫자 칸 하나를 통째로 바꾸는 손질."""

    def edit(frame: pd.DataFrame) -> pd.DataFrame:
        values = frame[column].astype("float64").to_numpy(dtype=np.float64)
        frame[column] = pd.Series(change(values), index=frame.index, dtype="float64")
        return frame

    return edit


def test_counts_exact_and_tolerant_table_matches_apart(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """DB 쪽 UPEH 가 모두 끝자리 한 칸(1 ulp) 다르면 원천 해시와 그 표의 정확은 다르고 오차 안은
    같다 — 다른 열은 0 이고 UPEH 는 「끝자리만」 이다."""
    data = source_csv_bytes(_rows())
    database = _copy(tmp_path, data, _nudge("UPEH", lambda v: np.nextafter(v, np.inf)))

    code, output = _run(capsys, "--database", str(database), "--csv", str(_csv(tmp_path, data)))

    assert code == 0
    assert _summary(output) == [
        "전송용 요약: CSV견줌 원천행 같음 · 해시 다름 · 16표 정확 15/16 · 오차안 16/16 · "
        "다른열 0 · CUSTOM뺌 정확 15/16 · 오차안 16/16"
    ]
    assert re.search(
        r"\| `RQ_UPEH` \| \d+ \| \d+ \| \*\*다름\*\* \| 같음 \| \*\*다름\*\* \| 같음 \|", output
    )
    assert "| `UPEH` |" in output and "| 끝자리만 |" in output
    assert "- 다른 열 0 · 끝자리만 1" in output


def test_tolerance_is_relative_only_so_small_values_do_not_hide(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """1 보다 작은 측정률이 상대 1e-9 만큼 다르면 오차 밖이다 — numpy 기본 절대 오차(1e-8)를 두면
    그 안에 묻혀 「오차 안」 으로 셀 것이다(`atol=0`)."""
    data = source_csv_bytes(_rows())
    database = _copy(tmp_path, data, _nudge("WF측정률", lambda v: v * (1 + 1e-9)))
    values = _csv_batch(data).frame["WF측정률"].astype("float64").dropna().to_numpy()
    assert np.allclose(values, values * (1 + 1e-9), rtol=script.RELATIVE_TOLERANCE)
    assert not np.allclose(values, values * (1 + 1e-9), rtol=script.RELATIVE_TOLERANCE, atol=0)

    code, output = _run(capsys, "--database", str(database), "--csv", str(_csv(tmp_path, data)))

    assert code == 0
    assert _summary(output) == [
        "전송용 요약: CSV견줌 원천행 같음 · 해시 다름 · 16표 정확 15/16 · 오차안 15/16 · "
        "다른열 1(WF측정률) · CUSTOM뺌 정확 15/16 · 오차안 15/16"
    ]
    assert re.search(r"\| `RQ_WF_RATIO` \| \d+ \| \d+ \| \*\*다름\*\* \| \*\*다름\*\* \|", output)


def test_a_db_source_with_a_query_constant_custom_matches_once_custom_is_set_aside(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CUSTOM 둘째 표를 붙이기 전에 DB 로 등록한 원천은 CUSTOM 칸이 조회문 상수 하나다 — CUSTOM 키
    표는 늘 갈리고, CUSTOM 뺌 셈은 그 밖의 칸이 같음을 말한다."""
    data = source_csv_bytes(_rows())
    database = _copy(tmp_path, data, lambda frame: frame.assign(CUSTOM="DEMO_CONSTANT"))

    code, output = _run(capsys, "--database", str(database), "--csv", str(_csv(tmp_path, data)))

    assert code == 0
    assert _summary(output) == [
        "전송용 요약: CSV견줌 원천행 같음 · 해시 다름 · 16표 정확 8/16 · 오차안 8/16 · "
        "다른열 1(CUSTOM) · CUSTOM뺌 정확 16/16 · 오차안 16/16"
    ]
    assert "DEMO_CONSTANT" not in output and SENTINEL not in output


def test_reloaded_duplicate_rows_fold_and_leave_the_columns_alike(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """DB 길 재적재가 겹쳐 완전 중복 행이 붙으면 원천 행 · 해시는 다르고, 접은 행 · 열은 같다."""
    data = source_csv_bytes(_rows())
    database = _copy(
        tmp_path, data, lambda frame: pd.concat([frame, frame.iloc[:3]], ignore_index=True)
    )

    code, output = _run(capsys, "--database", str(database), "--csv", str(_csv(tmp_path, data)))

    assert code == 0
    rows = len(_rows())
    assert (
        f"- 원천 행 CSV {rows} · DB {rows + 3} — 접음 {rows} · {rows} · 두 쪽에 다 있음 {rows}"
        in output
    )
    (line,) = _summary(output)
    assert line.startswith("전송용 요약: CSV견줌 원천행 다름 · 해시 다름 · ")
    assert "다른열 0" in line


# ---------------------------------------------------------------- 코드 · 멈춤


def test_each_file_code_with_a_db_source_is_compared_by_its_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """파일에 코드가 둘이면 사본에 DB 길 원천이 있는 코드만 파일 차례 번호로 견준다."""
    data = source_csv_bytes([*_rows(OTHER_CODE), *_rows(CODE)])
    database = _copy(tmp_path, data)

    code, output = _run(capsys, "--database", str(database), "--csv", str(_csv(tmp_path, data)))

    assert code == 0
    assert "파일 코드 2 · 그 가운데 사본에 DB 길 원천이 있는 코드 1" in output
    assert "#### 코드 2" in output and "#### 코드 1" not in output
    assert _summary(output) == [ALIKE.replace("CSV견줌 ", "CSV견줌 코드2 ")]
    assert SENTINEL not in output


def test_no_shared_code_stops(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    database = _copy(tmp_path, source_csv_bytes(_rows(OTHER_CODE)), code=OTHER_CODE)
    csv = _csv(tmp_path, source_csv_bytes(_rows()))

    code, output = _run(capsys, "--database", str(database), "--csv", str(csv))

    assert code == 2
    assert "사본에 DB 길 원천이 있는 코드 0" in output
    assert _summary(output) == ["전송용 요약: CSV견줌 같은 코드 없음"]
    assert SENTINEL not in output


def test_csv_registered_sources_are_not_a_db_counterpart(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """같은 코드를 원천 CSV 로 등록한 데이터셋은 DB 길 짝이 아니다 — 견주지 않는다."""
    data = source_csv_bytes(_rows())
    path = tmp_path / "e2e_copy" / "data" / "capa_simulation.duckdb"
    path.parent.mkdir(parents=True)
    prepared = prepare_core_data_dataset(_csv_batch(data), load_builtin_display_order())
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    save_bigdataquery_scenario(
        repository,
        prepared,
        full_data_scenario_preset(prepared.reference_tables),
        scenario_name=f"{SENTINEL} 시나리오",
        revision_name="초기 리비전",
        note="",
    )

    code, output = _run(capsys, "--database", str(path), "--csv", str(_csv(tmp_path, data)))

    assert code == 2
    assert _summary(output) == ["전송용 요약: CSV견줌 같은 코드 없음"]


def test_an_unreadable_csv_stops_with_its_kind_only_before_the_database_opens(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """원천 CSV 멈춤 글에는 파일의 열 이름이 실린다 — 예외 종류만 적고 DB 는 열지 않는다."""

    def must_not_open(*_args: object, **_kwargs: object) -> duckdb.DuckDBPyConnection:
        raise AssertionError("CSV 를 읽지 못하면 DB 는 열지 않는다")

    monkeypatch.setattr(duckdb, "connect", must_not_open)
    data = source_csv_bytes(_rows(), header_override={"Capa Code": f"{SENTINEL} 부품"})
    database = tmp_path / "e2e_copy" / "capa_simulation.duckdb"

    code, output = _run(capsys, "--database", str(database), "--csv", str(_csv(tmp_path, data)))

    assert code == 2
    assert "원천 CSV 를 읽지 못했다 — SourceCsvError" in output
    assert _summary(output) == ["전송용 요약: CSV견줌 읽지 못함(SourceCsvError)"]
    assert SENTINEL not in output


def test_a_custom_stop_names_only_its_kind(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """한 부품에 CUSTOM 이 둘이면 CSV 원천이 멈춘다 — 그 글에는 부품 코드가 실려 종류만 적는다."""
    rows = _rows()
    database = _copy(tmp_path, source_csv_bytes(rows))
    rows[0]["CUSTOM"] = f"{SENTINEL}_CUSTOM_OTHER"

    code, output = _run(
        capsys, "--database", str(database), "--csv", str(_csv(tmp_path, source_csv_bytes(rows)))
    )

    assert code == 2
    assert "- CSV 원천을 짓지 못했다 — ValueError" in output
    assert _summary(output) == ["전송용 요약: CSV견줌 멈춤(CSV 원천 ValueError)"]
    assert SENTINEL not in output


# ---------------------------------------------------------------- 견줌 함수


def test_rows_are_ordered_by_text_columns_before_numbers() -> None:
    """끝자리만 다른 실수가 행 차례를 바꾸지 않는다 — 글자 칸이 앞 열쇠다. 실수를 앞 열쇠로 두면
    두 쪽의 a · b 행이 서로 엇갈려 맞대져 글자 칸이 다르게 된다."""
    up = float(np.nextafter(1.0, 2.0))
    left = pd.DataFrame({"x": [up, 1.0], "k": pd.array(["a", "b"], dtype="string")})
    right = pd.DataFrame({"x": [up, 1.0], "k": pd.array(["b", "a"], dtype="string")})

    assert not script.tables_equal_exactly(left, right)
    assert script.tables_equal_within_tolerance(left, right)
    assert script.tables_equal_exactly(left, right.assign(x=[1.0, up]))


def test_value_groups_count_each_differing_value_and_the_missing_count() -> None:
    left = pd.Series(["a", "a", "b", None], dtype="string")
    right = pd.Series(["a", "b", "b", "c"], dtype="string")

    assert script.differing_value_groups(left, left.copy()) == 0
    # a(2 · 1) · b(1 · 2) · c(0 · 1) 셋과 빈 값 수(1 · 0).
    assert script.differing_value_groups(left, right) == 4


def test_derived_source_types_are_those_of_the_real_data_checks() -> None:
    import inspect_real_data_checks as checks

    assert script.DERIVED_SOURCE_TYPES == checks.DERIVED_SOURCE_TYPES
