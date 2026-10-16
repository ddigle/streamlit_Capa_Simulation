# Purpose: 확보율 보정의 값 정규화·퍼센트포인트 차감과 공용 프로필 저장의 버전 대조를 검증한다.

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.persistence import DuckDBScenarioRepository
from capa_simulation.persistence._sql_helpers import ProfileVersionConflict
from capa_simulation.persistence.cache import clear_global_execution_capacity_cache
from capa_simulation.services.execution_capacity import (
    EXECUTION_CAPACITY_COLUMNS,
    apply_execution_adjustment,
    clamped_execution_adjustments,
    empty_execution_capacity,
    prepare_execution_capacity,
    unmatched_execution_adjustments,
)


def _rows(records: list[tuple[int, str, float, str]]) -> pd.DataFrame:
    return pd.DataFrame(records, columns=list(EXECUTION_CAPACITY_COLUMNS))


def _securement(records: list[tuple[int, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(records, columns=["생산계획년월", "공정", "확보율"])


def test_adjustment_is_percentage_points_not_a_ratio() -> None:
    """105% 에 -10 을 넣으면 95% 다. 비율 곱셈이면 94.5% 가 나온다.

    목적이 '비가동대수가 늘어 가용대수가 줄었다' 같은 변수를 확보율에 바로 얹는 것이라
    입력 숫자가 화면 퍼센트와 같은 눈금이어야 한다.
    """
    adjusted = apply_execution_adjustment(
        _securement([(202607, "DEMO_A", 1.05)]),
        _rows([(202607, "DEMO_A", -10.0, "비가동 3대")]),
    )

    assert adjusted.loc[0, "확보율"] == pytest.approx(0.95)
    assert adjusted.loc[0, "기준 확보율"] == pytest.approx(1.05)
    assert adjusted.loc[0, "확보율 증감"] == pytest.approx(-10.0)
    assert adjusted.loc[0, "실행 비고"] == "비가동 3대"


def test_baseline_columns_exist_even_with_no_adjustment() -> None:
    """조정 0건이어도 세 컬럼을 만든다. 뒤의 순위·Figure 가 컬럼 유무로 갈라지면 안 된다."""
    securement = _securement([(202607, "DEMO_A", 1.05), (202608, "DEMO_B", 0.80)])

    adjusted = apply_execution_adjustment(securement, empty_execution_capacity())

    assert {"기준 확보율", "확보율 증감", "실행 비고"} <= set(adjusted.columns)
    assert adjusted["확보율"].tolist() == securement["확보율"].tolist()
    assert adjusted["확보율 증감"].eq(0.0).all()


def test_only_the_matching_month_and_process_moves() -> None:
    """년월과 공정이 **둘 다** 같은 행만 움직인다."""
    adjusted = apply_execution_adjustment(
        _securement(
            [
                (202607, "DEMO_A", 1.00),
                (202608, "DEMO_A", 1.00),
                (202607, "DEMO_B", 1.00),
            ]
        ),
        _rows([(202607, "DEMO_A", -20.0, "")]),
    )

    assert adjusted["확보율"].tolist() == pytest.approx([0.80, 1.00, 1.00])


def test_zero_rows_are_dropped_but_a_clearing_save_is_still_valid() -> None:
    """증감 0 은 '넣지 않은 행' 이다. 지정하지 않은 것과 결과가 같다."""
    prepared = prepare_execution_capacity(
        _rows([(202607, "DEMO_A", -10.0, "유지"), (202607, "DEMO_B", 0.0, "버려짐")])
    )

    assert prepared["공정"].tolist() == ["DEMO_A"]
    assert prepare_execution_capacity(empty_execution_capacity()).empty


def test_duplicate_month_and_process_is_rejected() -> None:
    """같은 달·공정이 두 번 들어오면 어느 값이 맞는지 알 수 없다."""
    with pytest.raises(ValueError, match="같은 달·공정이 두 번"):
        prepare_execution_capacity(
            _rows([(202607, "DEMO_A", -10.0, ""), (202607, "DEMO_A", -5.0, "")])
        )


def test_month_must_be_yyyymm() -> None:
    with pytest.raises(ValueError, match="YYYYMM"):
        prepare_execution_capacity(_rows([(202613, "DEMO_A", -10.0, "")]))


def test_process_is_normalized_so_stray_spaces_still_match() -> None:
    """공정은 원본 코드 기준이고 정규화는 저장·조회가 같은 함수를 쓴다."""
    adjusted = apply_execution_adjustment(
        _securement([(202607, "DEMO_A", 1.00)]),
        _rows([(202607, "  DEMO_A  ", -10.0, "")]),
    )

    assert adjusted.loc[0, "확보율"] == pytest.approx(0.90)


def test_negative_result_is_clamped_at_zero_and_reported() -> None:
    """음수 확보율은 막대 길이도 순위도 무의미해진다. 0 에서 자르고 알린다."""
    adjusted = apply_execution_adjustment(
        _securement([(202607, "DEMO_A", 0.05)]),
        _rows([(202607, "DEMO_A", -20.0, "재공 부진")]),
    )

    assert adjusted.loc[0, "확보율"] == pytest.approx(0.0)
    clamped = clamped_execution_adjustments(adjusted)
    assert clamped["공정"].tolist() == ["DEMO_A"]


def test_rows_without_a_match_are_reported_not_rejected() -> None:
    """공용 프로필이라 다른 시나리오에서는 유효할 수 있다. 저장은 막지 않고 알린다."""
    securement = _securement([(202607, "DEMO_A", 1.00)])
    rows = _rows([(202607, "DEMO_A", -10.0, ""), (202609, "DEMO_Z", -5.0, "다른 시나리오")])

    unmatched = unmatched_execution_adjustments(securement, rows)

    assert unmatched["공정"].tolist() == ["DEMO_Z"]
    # 매칭되는 행은 정상 적용된다.
    assert apply_execution_adjustment(securement, rows).loc[0, "확보율"] == pytest.approx(0.90)


def test_column_contract_is_enforced() -> None:
    with pytest.raises(ValueError, match="컬럼 계약"):
        prepare_execution_capacity(pd.DataFrame({"생산계획년월": [202607]}))


# ------------------------------------------------------------------- 공용 프로필 버전 대조


def _scenario_repository(path: Path) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    return repository


def test_a_save_started_from_an_older_version_is_refused(tmp_path: Path) -> None:
    """편집을 시작한 뒤 다른 사람이 저장했으면 덮지 않는다 — 판정 기준과 같은 버전 대조다."""
    repository = _scenario_repository(tmp_path / "scenario.duckdb")
    repository.replace_global_execution_capacity(
        _rows([(202607, "DEMO_A", -10.0, "")]), source="A 가 본 것"
    )
    repository.replace_global_execution_capacity(
        _rows([(202607, "DEMO_A", -10.0, ""), (202608, "DEMO_B", -5.0, "B")]), source="B 의 저장"
    )

    with pytest.raises(ProfileVersionConflict, match="다른 사용자가 먼저"):
        repository.replace_global_execution_capacity(
            _rows([(202607, "DEMO_A", -20.0, "")]), source="A 의 저장", expected_version=1
        )

    profile = repository.load_global_execution_capacity()
    assert (profile.version, profile.source) == (2, "B 의 저장")
    assert profile.rows["공정"].tolist() == ["DEMO_A", "DEMO_B"]
    saved = repository.replace_global_execution_capacity(
        _rows([(202607, "DEMO_A", -20.0, "")]), source="A 의 저장", expected_version=2
    )
    assert saved.version == 3


def test_the_execution_editor_refuses_to_overwrite_a_newer_save(tmp_path: Path) -> None:
    """화면: A 가 편집기를 연 뒤 B 가 저장했다. A 의 저장은 막히고 B 의 저장본이 남는다. 그 회차가
    그린 최신 저장본에서 다시 누르면 저장된다."""
    database_path = tmp_path / "scenario.duckdb"
    repository = _scenario_repository(database_path)
    repository.replace_global_execution_capacity(
        _rows([(202607, "DEMO_A", -10.0, "")]), source="A 가 본 것"
    )
    script = f"""
import pandas as pd

from capa_simulation.components.home_preference import _render_execution_editor
from capa_simulation.components.process_labels import process_labels_from_rules
from capa_simulation.persistence.cache import load_global_execution_capacity

database_path = {str(database_path)!r}
_render_execution_editor(
    months=[202607, 202608],
    execution_profile=load_global_execution_capacity(database_path),
    process_options=["DEMO_A", "DEMO_B"],
    process_labels=process_labels_from_rules(pd.DataFrame()),
    unmatched=pd.DataFrame(),
    clamped=pd.DataFrame(),
    database_path=database_path,
)
"""
    clear_global_execution_capacity_cache()
    app = AppTest.from_string(script, default_timeout=60).run()
    assert not app.exception

    repository.replace_global_execution_capacity(
        _rows([(202607, "DEMO_A", -10.0, ""), (202608, "DEMO_B", -5.0, "B")]), source="B 의 저장"
    )
    clear_global_execution_capacity_cache()
    next(button for button in app.button if button.label == "확보율 보정 저장").click().run()

    assert not app.exception
    errors = [str(item.value) for item in app.error]
    assert any("다른 사용자가 먼저" in text for text in errors), errors
    profile = repository.load_global_execution_capacity()
    assert (profile.version, profile.source) == (2, "B 의 저장")

    next(button for button in app.button if button.label == "확보율 보정 저장").click().run()
    assert not app.exception
    assert not app.error, [str(item.value) for item in app.error]
    assert repository.load_global_execution_capacity().version == 3
    clear_global_execution_capacity_cache()
