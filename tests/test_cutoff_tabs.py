# Purpose: Preference의 Cut-off 입력과 Static/Dynamic 비교가 독립적으로 동작하는지 검사한다.

"""탭을 늘리면 **화면이 죽는 자리가 타입 검사에 안 걸린다.**

세션 키 겹침, 탭 언패킹, 폼 안의 위젯 배치, 활성 시나리오가 없을 때의 예외 — 넷 다
`mypy` 와 `ruff` 를 통과한 채로 화면에서만 터진다. 실제로 이 파일을 쓰다가
`pd.Series([pd.NA] * n, dtype="float64")` 가 `TypeError` 로 죽는 것을 잡았다.

이 페이지는 **활성 시나리오가 없어도 열리는 유일한 계산 계열 화면**이다. Static 을 읽는
탭이 생겼으므로, 그 탭이 못 읽어도 나머지가 살아 있어야 한다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest
from test_equipment_pages import _open_tab, _page_script

from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.availability_gap import (
    DYNAMIC_SUBTOTAL_ROW,
    GAP_ROW,
    build_availability_gap,
    gap_matrix,
)
from capa_simulation.services.monthly_equipment_availability import (
    build_monthly_equipment_availability,
)
from capa_simulation.services.process_cutoff import prepare_process_cutoff

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"


def _run(database_path: Path, *, tab: str = "Preference") -> AppTest:
    app = AppTest.from_string(_page_script(PAGE, database_path), default_timeout=120).run()
    return _open_tab(app, tab)


def test_preference_offers_cutoff_input_on_an_empty_database(tmp_path: Path) -> None:
    app = _run(tmp_path / "availability.duckdb")

    assert not app.exception
    preference = next(tab for tab in app.tabs if tab.label.endswith(" Preference"))
    labels = [button.label for button in preference.button]
    assert "Cut-off 저장" in labels, labels
    assert "설비 공정으로 채우기" in labels, labels
    assert not any(tab.label.endswith(" Cut-off") for tab in app.tabs)
    clear_equipment_repository()


def test_the_gap_tab_asks_for_a_cutoff_before_it_computes(tmp_path: Path) -> None:
    """Cut-off 가 없으면 Dynamic 을 낼 수 없다. 조용히 0 을 보이지 않고 이유를 말한다."""
    app = _run(tmp_path / "availability.duckdb", tab="Static/Dynamic")

    notices = " ".join(str(item.value) for item in app.info)
    assert "Cut-off" in notices, notices
    clear_equipment_repository()


def test_a_saved_cutoff_lets_the_gap_tab_draw(tmp_path: Path) -> None:
    """Cut-off 를 저장하면 비교 탭이 공정 선택과 그림을 낸다."""
    database_path = tmp_path / "availability.duckdb"
    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    repository.save_process_cutoff(
        pd.DataFrame({"공정": ["Die Attach"], "Cutoff일수": [15.0], "비고": [None]})
    )

    app = _run(database_path, tab="Static/Dynamic")

    assert not app.exception
    selectbox_labels = [widget.label for widget in app.selectbox]
    assert "공정" in selectbox_labels, selectbox_labels
    # 활성 시나리오가 없어도 비교 안내에 그치고 Preference 입력은 계속 사용할 수 있다.
    _open_tab(app, "Preference")
    assert not app.exception
    assert any(button.label == "Cut-off 저장" for button in app.button)
    clear_equipment_repository()


def test_a_process_without_a_cutoff_is_surfaced_not_silently_dropped(tmp_path: Path) -> None:
    """빠진 공정을 화면이 말해야 한다 — 조용히 빠지면 옆 탭 합이 이유 없이 작아진다."""
    app = _run(tmp_path / "availability.duckdb")

    warnings = " ".join(str(item.value) for item in app.warning)
    assert "Cut-off 를 적지 않은 공정" in warnings, warnings
    clear_equipment_repository()


def test_the_cutoff_editor_has_its_own_view_controls(tmp_path: Path) -> None:
    """편집표에는 컬럼 선택·행 필터가 붙는다. 다른 편집표와 세션 키가 겹치면 안 된다."""
    app = _run(tmp_path / "availability.duckdb")

    keys = [widget.key for widget in app.multiselect]
    assert "equipment_cutoff_view_v1_columns" in keys, keys
    assert len(keys) == len(set(keys)), keys
    clear_equipment_repository()


def test_the_panel_accepts_a_real_static_frame(tmp_path: Path) -> None:
    """**Static 이 실제로 있는 경로**를 밟는다.

    `static_availability or pd.DataFrame()` 이 프레임에 `or` 를 걸어
    「truth value of a DataFrame is ambiguous」로 죽던 자리다. `None` 일 때는 멀쩡해서
    AppTest 가 시뮬레이션 DB 를 못 읽는 동안 그 버그가 통과했다 — 실제 화면에서만 터졌다.
    """
    from capa_simulation.components import availability_gap_panel

    spans = pd.DataFrame(
        {
            "호기": ["EQ-1"],
            "공정소분류": ["Die Attach"],
            "상태": ["가용"],
            "시작일": [date(2020, 1, 1)],
            "종료일": [date(2030, 1, 1)],
        }
    )
    baseline = pd.DataFrame({"공정": ["Die Attach"], "기존보유대수": [3.0]})
    cutoff = prepare_process_cutoff(
        pd.DataFrame({"공정": ["Die Attach"], "Cutoff일수": [15.0], "비고": [None]})
    )
    static = pd.DataFrame({"생산계획년월": [202610], "공정": ["Die Attach"], "가용대수": [6.0]})

    monthly = build_monthly_equipment_availability(spans, baseline, cutoff, [202610])
    comparison = build_availability_gap(monthly, static, [202610])
    matrix = gap_matrix(comparison.rows, "Die Attach")

    # 소계 = 기존보유 3 + 가용 1 = 4, Static 6 → GAP -2
    assert matrix.loc[DYNAMIC_SUBTOTAL_ROW, "202610"] == 4.0
    assert matrix.loc[GAP_ROW, "202610"] == -2.0
    # Figure 가 실제로 만들어지는지도 본다 — 빈 행이 섞여도 죽지 않아야 한다.
    figure = availability_gap_panel.build_availability_gap_figure(matrix)
    assert len(figure.data) == 3


def test_filling_from_equipment_processes_keeps_the_values_already_written() -> None:
    """「설비 공정으로 채우기」는 표에 없는 공정만 빈 행으로 덧붙인다.

    몇 공정만 적어 저장하면 저장은 적은 행만 남긴다. 그때 채우기가 표 전체를 새로 깔아
    저장한 값까지 지웠다(2026-10-05 E2E).
    """
    from capa_simulation.services.process_cutoff import (
        PROCESS_CUTOFF_EDIT_COLUMNS,
        add_missing_cutoff_rows,
        build_process_cutoff_template,
    )

    draft = build_process_cutoff_template(["AVI-CoW", "Die Attach"]).loc[
        :, PROCESS_CUTOFF_EDIT_COLUMNS
    ]
    draft["Cutoff일수"] = [7.0, 14.0]

    filled = add_missing_cutoff_rows(draft, ["Die Attach", "Wire Bond", " AVI-CoW ", "Mold"])

    assert filled["공정"].tolist() == ["AVI-CoW", "Die Attach", "Wire Bond", "Mold"]
    assert filled["Cutoff일수"].iloc[:2].tolist() == [7.0, 14.0]
    assert filled["Cutoff일수"].iloc[2:].isna().all()
    assert list(filled.columns) == PROCESS_CUTOFF_EDIT_COLUMNS
    # 빠진 공정이 없으면 표를 그대로 돌려준다.
    assert add_missing_cutoff_rows(draft, ["Die Attach"]) is draft
