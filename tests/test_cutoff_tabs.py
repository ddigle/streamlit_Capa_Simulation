# Purpose: 「가용설비 설정」 팝업의 Cut-off 입력과 Static 대비 일정 비교가 따로 도는지 검사한다.

"""탭을 늘리면 **화면이 죽는 자리가 타입 검사에 안 걸린다.**

세션 키 겹침, 탭 언패킹, 폼 안의 위젯 배치, 활성 시나리오가 없을 때의 예외 — 넷 다
`mypy` 와 `ruff` 를 통과한 채로 화면에서만 터진다. 실제로 이 파일을 쓰다가
`pd.Series([pd.NA] * n, dtype="float64")` 가 `TypeError` 로 죽는 것을 잡았다.

이 페이지는 **활성 시나리오가 없어도 열리는 유일한 계산 계열 화면**이다. Static 을 읽는
탭이 생겼으므로, 그 탭이 못 읽어도 나머지가 살아 있어야 한다. Cut-off 는 사이드바 「가용설비 설정」
상자의 팝업이다(2026-11-03 — 전에는 머리 「설정」 단추, 개편 전 `Preference` 탭).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from alert_marks import active_state, states, successes
from streamlit.testing.v1 import AppTest
from test_equipment_pages import _open_settings, _open_tab, _page_script

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.cutoff_management import CUTOFF_DRAFT_KEY, CUTOFF_SAVE_HELP
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    clear_process_cutoff_cache,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.availability_gap import (
    DYNAMIC_SUBTOTAL_ROW,
    GAP_ROW,
    build_availability_gap,
    gap_matrix,
)
from capa_simulation.services.availability_sheet import (
    ROW_GAP_AVAILABLE,
    build_availability_sheet,
    sheet_view,
)
from capa_simulation.services.monthly_equipment_availability import (
    build_monthly_equipment_availability,
)
from capa_simulation.services.process_cutoff import prepare_process_cutoff

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"


def _run(database_path: Path, *, tab: str | None = None) -> AppTest:
    """탭을 주면 그 탭을, 안 주면 「설정」 팝업(공정별 Cut-off)을 연다."""
    app = AppTest.from_string(_page_script(PAGE, database_path), default_timeout=120).run()
    return _open_settings(app) if tab is None else _open_tab(app, tab)


def test_settings_offers_cutoff_input_on_an_empty_database(tmp_path: Path) -> None:
    app = _run(tmp_path / "availability.duckdb")

    assert not app.exception
    labels = [button.label for button in app.button]
    assert "Cut-off 저장" in labels, labels
    assert "설비 공정으로 채우기" in labels, labels
    assert not any(tab.label.endswith(" Cut-off") for tab in app.tabs)
    clear_equipment_repository()


def test_the_settings_popup_has_no_header_note_and_the_save_button_says_it(
    tmp_path: Path,
) -> None:
    """팝업 머리에 안내 글(공용 설정 · 닫기 전에 저장)을 두지 않는다 — 그 말은 「Cut-off 저장」
    단추 풍선이 한다."""
    app = _run(tmp_path / "availability.duckdb")

    assert not app.exception, [item.message for item in app.exception]
    captions = [str(item.value) for item in app.caption]
    assert not any("공용 설정입니다" in text or "닫기 전에" in text for text in captions), captions
    save = next(button for button in app.button if button.label == "Cut-off 저장")
    assert save.help == CUTOFF_SAVE_HELP
    assert "공용" in CUTOFF_SAVE_HELP and "닫으면" in CUTOFF_SAVE_HELP
    clear_equipment_repository()


def test_the_gap_tab_asks_for_a_cutoff_before_it_computes(tmp_path: Path) -> None:
    """Cut-off 가 없으면 Dynamic 을 낼 수 없다. 조용히 0 을 보이지 않고 이유를 말한다."""
    app = _run(tmp_path / "availability.duckdb", tab="Static 대비 일정")

    # 빈 상태는 회색 평문 한 줄(값)이고 하는 법은 그 줄의 풍선이다(설계 규칙 UI-TXT-04).
    (line,) = [item for item in app.caption if item.value == "공정별 Cut-off 가 없습니다."]
    assert "먼저 적어야" in str(line.proto.help)
    clear_equipment_repository()


def test_a_saved_cutoff_lets_the_gap_tab_draw(tmp_path: Path) -> None:
    """Cut-off 를 저장하면 비교 탭이 공정 선택과 그림을 낸다."""
    database_path = tmp_path / "availability.duckdb"
    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    repository.save_process_cutoff(
        pd.DataFrame({"공정": ["Die Attach"], "Cutoff일수": [15.0], "비고": [None]})
    )

    app = _run(database_path, tab="Static 대비 일정")

    assert not app.exception
    selectbox_labels = [widget.label for widget in app.selectbox]
    assert "공정" in selectbox_labels, selectbox_labels
    # 활성 시나리오가 없어도 비교 안내에 그치고 「설정」 의 Cut-off 입력은 계속 사용할 수 있다.
    _open_settings(app)
    assert not app.exception
    assert any(button.label == "Cut-off 저장" for button in app.button)
    clear_equipment_repository()


def test_a_process_without_a_cutoff_is_surfaced_not_silently_dropped(tmp_path: Path) -> None:
    """빠진 공정을 화면이 말해야 한다 — 조용히 빠지면 옆 탭 합이 이유 없이 작아진다. 팝업 안에는
    고칠 표 곁 경고(이름 목록 — 자리 글)가 서고, 화면은 팝업을 열지 않아도 상태 알림(`EQ-12` —
    알림창 · Alarm)을 낸다(2026-11-03 D2)."""
    app = _run(tmp_path / "availability.duckdb")

    warnings = " ".join(str(item.value) for item in app.warning)
    assert "Cut-off 를 적지 않은 공정" in warnings, warnings
    note = active_state(app, "EQ-12")
    assert note is not None and "Cut-off 를 적지 않은 공정" in note["full"], states(app, "EQ-12")
    assert "「가용설비 설정」" in note["short"] and "설비 공정으로 채우기" in note["full"], note
    clear_equipment_repository()


def _cutoff_body(database_path: str) -> None:
    """「설정」 팝업 본문만 — 설비 공정 둘(하나는 물결표 이름)에 Cut-off 가 없다."""
    from pathlib import Path

    from capa_simulation.components.cutoff_management import render_cutoff_management
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

    repository = DuckDBEquipmentRepository(Path(database_path))
    repository.initialize()
    render_cutoff_management(repository, equipment_processes=["E2E~공정~X", "SAMPLE1"])


def test_the_missing_cutoff_warning_blocks_the_tildes_of_the_process_names(
    tmp_path: Path,
) -> None:
    """팝업 안 「Cut-off 를 적지 않은 공정」 경고는 그 이름을 그대로 새 행에 옮겨 적으라는 글인데,
    원본 공정명 「E2E~공정~X」 의 물결표가 지움선이 되어 「E2E공정X」 로 보였다(2026-10-26 E2E r5).
    이름의 물결표만 막고 「빠집니다」 굵게는 둔다. 팝업 본문은 상태 알림을 내지 않는다(화면이
    낸다)."""
    app = AppTest.from_function(
        _cutoff_body, args=(str(tmp_path / "availability.duckdb"),), default_timeout=60
    ).run()

    assert not app.exception, [item.message for item in app.exception]
    (warning,) = [str(item.value) for item in app.warning if "Cut-off 를 적지" in str(item.value)]
    assert warning.endswith("**빠집니다** — E2E\\~공정\\~X, SAMPLE1"), warning
    assert not states(app, "EQ-12")
    clear_equipment_repository()


def _missing_report(names: list[str]) -> None:
    import pandas as pd

    from capa_simulation.components.cutoff_management import report_missing_cutoffs

    report_missing_cutoffs(names, pd.DataFrame(columns=["공정", "Cutoff일수"]))


def test_the_missing_cutoff_alert_keeps_the_process_names_verbatim() -> None:
    """상태 알림(`EQ-12`)의 알림창 · 패널은 평문(`textContent`)이라 이름을 막지 않고 글자 그대로
    싣는다. 빠진 공정이 없으면 해소 표지(`active` 거짓)를 낸다."""
    app = AppTest.from_function(_missing_report, args=(["E2E~공정~X", "SAMPLE1"],)).run()

    assert not app.exception, [item.message for item in app.exception]
    note = active_state(app, "EQ-12")
    assert note is not None
    assert "빠집니다 — E2E~공정~X, SAMPLE1." in str(note["full"]), note
    assert not app.warning
    quiet = AppTest.from_function(_missing_report, args=([],)).run()
    assert [item["active"] for item in states(quiet, "EQ-12")] == [False]


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
    from capa_simulation.components.availability_gap_figure import (
        build_availability_gap_figure,
    )

    spans = pd.DataFrame(
        {
            "설비명": ["EQ-1"],
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
    # 화면 그림은 비교 시트(환산 축)를 그린다 — 환산비가 없으면 같은 값이다. Figure 가 실제로
    # 만들어지는지도 본다.
    sheet = build_availability_sheet(monthly, None, None, None, static, [202610])
    view = sheet_view(sheet, processes=["Die Attach"])
    assert view.value(ROW_GAP_AVAILABLE, 202610) == -2.0
    figure = build_availability_gap_figure(view)
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


def test_reopening_settings_shows_a_cutoff_saved_by_someone_else(tmp_path: Path) -> None:
    """A 가 「설정」 을 열어 보고 닫은 뒤 B 가 AVI-PKG 를 12 로 저장하면, A 가 다시 열어도 옛
    값(45)이 보였고 고치지 않은 채 누른 저장이 「다른 사용자가 먼저 …」 로 거부됐다(2026-10-27
    E2E) — 초안이 그리는 회차마다 다시 적혀 닫아도 남았다. 새로 열면 초안을 걷어 최신 저장본에서
    연다."""
    from capa_simulation.components.equipment_settings_dialog import EQUIPMENT_DIALOG_KEY

    database_path = tmp_path / "availability.duckdb"
    outsider = DuckDBEquipmentRepository(database_path)
    outsider.initialize()
    outsider.save_process_cutoff(
        pd.DataFrame({"공정": ["AVI-PKG"], "Cutoff일수": [45.0], "비고": [None]})
    )
    clear_equipment_repository()
    app = _run(database_path)
    assert app.session_state[CUTOFF_DRAFT_KEY]["Cutoff일수"].tolist() == [45.0]
    del app.session_state[EQUIPMENT_DIALOG_KEY]
    app.run()

    outsider.save_process_cutoff(
        pd.DataFrame({"공정": ["AVI-PKG"], "Cutoff일수": [12.0], "비고": [None]})
    )
    clear_process_cutoff_cache()
    _open_settings(app)

    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state[CUTOFF_DRAFT_KEY]["Cutoff일수"].tolist() == [12.0]
    next(button for button in app.button if button.label == "Cut-off 저장").click().run()
    assert not app.exception, [item.message for item in app.exception]
    warnings = [str(item.value) for item in app.warning]
    assert not any("다른 사용자가 먼저" in text for text in warnings), warnings
    assert any("Cut-off 1건을 저장했습니다" in str(item.value) for item in successes(app))
    assert outsider.load_process_cutoff()["Cutoff일수"].tolist() == [12.0]
    clear_equipment_repository()


def test_a_cutoff_saved_by_someone_else_is_not_erased_by_an_older_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 가 탭을 연 뒤 B 가 Process-B 를 저장했다. A 가 옛 초안의 다른 행을 고쳐 저장하면 막고
    최신 저장본(Process-B 포함)으로 다시 연다 — 저장은 표 전체 교체라 그대로 쓰면 B 의 행이 지워져
    그 공정이 월별 가용대수에서 빠진다."""
    database_path = tmp_path / "cutoff.duckdb"
    outsider = DuckDBEquipmentRepository(database_path)
    outsider.initialize()
    outsider.save_process_cutoff(pd.DataFrame({"공정": ["Process-A"], "Cutoff일수": [10.0]}))
    clear_equipment_repository()
    script = f"""
from pathlib import Path

from capa_simulation.components.cutoff_management import render_cutoff_management
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

render_cutoff_management(
    DuckDBEquipmentRepository(Path({str(database_path)!r})),
    equipment_processes=["Process-A", "Process-B"],
)
"""
    app = AppTest.from_string(script, default_timeout=60).run()
    assert not app.exception

    outsider.save_process_cutoff(
        pd.DataFrame({"공정": ["Process-A", "Process-B"], "Cutoff일수": [10.0, 5.0]})
    )
    clear_process_cutoff_cache()
    draft = app.session_state[CUTOFF_DRAFT_KEY].copy()
    draft["Cutoff일수"] = 12.0
    app.session_state[CUTOFF_DRAFT_KEY] = draft
    next(button for button in app.button if button.label == "Cut-off 저장").click().run()

    assert not app.exception
    stored = outsider.load_process_cutoff()
    assert stored["공정"].tolist() == ["Process-A", "Process-B"]
    assert stored["Cutoff일수"].tolist() == [10.0, 5.0]
    warnings = [str(item.value) for item in app.warning]
    assert any("다른 사용자가 먼저" in text for text in warnings), warnings
    # 최신 저장본으로 다시 열었다 — 그 위에서 고친 다음 저장은 통과한다. 새 화면을 보고 다시 누른
    # 저장이라 거부 직후 둘째 누름의 창(`TRAILING_PRESS_SECONDS`)이 지났다. AppTest 의 회차 사이는
    # 그 창보다 짧아 창은 시험이 정한다.
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    reopened = app.session_state[CUTOFF_DRAFT_KEY]
    assert reopened["공정"].tolist() == ["Process-A", "Process-B"]
    edited = reopened.copy()
    edited["Cutoff일수"] = [12.0, 5.0]
    app.session_state[CUTOFF_DRAFT_KEY] = edited
    next(button for button in app.button if button.label == "Cut-off 저장").click().run()
    assert not app.exception
    assert outsider.load_process_cutoff()["Cutoff일수"].tolist() == [12.0, 5.0]
    clear_equipment_repository()


def test_a_single_press_after_a_held_double_press_saves_the_cutoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """남의 저장 뒤 옛 화면 두 번 누름이 둘 다 거부된 다음, 최신 화면을 보고 한 번 누른 저장은
    저장된다. Proc Rename·표시순서·자동 갱신 설정은 본 값을 거부 뒤 회차가 적어, 둘째 누름이 그
    회차를 끊으면 창 뒤의 한 번 누름이 옛 본 값으로 또 거부됐다(2026-10-27 E2E). Cut-off 는 거부
    회차가 초안과 출발점을 함께 다시 세우므로(`_reset_draft`) 거부 표지 회차가 본 값을 적지 않아도
    된다 — 그 꼴을 지킨다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    database_path = tmp_path / "cutoff-held.duckdb"
    outsider = DuckDBEquipmentRepository(database_path)
    outsider.initialize()
    outsider.save_process_cutoff(pd.DataFrame({"공정": ["Process-A"], "Cutoff일수": [10.0]}))
    clear_equipment_repository()
    script = f"""
from pathlib import Path

from capa_simulation.components.cutoff_management import render_cutoff_management
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

render_cutoff_management(
    DuckDBEquipmentRepository(Path({str(database_path)!r})),
    equipment_processes=["Process-A", "Process-B"],
)
"""
    app = AppTest.from_string(script, default_timeout=60).run()
    outsider.save_process_cutoff(
        pd.DataFrame({"공정": ["Process-A", "Process-B"], "Cutoff일수": [10.0, 5.0]})
    )
    clear_process_cutoff_cache()
    draft = app.session_state[CUTOFF_DRAFT_KEY].copy()
    draft["Cutoff일수"] = 12.0
    app.session_state[CUTOFF_DRAFT_KEY] = draft
    next(button for button in app.button if button.label == "Cut-off 저장").click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert any("다른 사용자가 먼저" in str(item.value) for item in app.warning)

    app._run(widget_state=pressed)
    assert any("다른 사용자가 먼저" in str(item.value) for item in app.warning)
    assert outsider.load_process_cutoff()["Cutoff일수"].tolist() == [10.0, 5.0]

    # 거부 표지의 창이 지났다 — 최신 화면을 보고 다시 누른 저장이다.
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    edited = app.session_state[CUTOFF_DRAFT_KEY].copy()
    assert edited["공정"].tolist() == ["Process-A", "Process-B"]
    edited["Cutoff일수"] = [12.0, 5.0]
    app.session_state[CUTOFF_DRAFT_KEY] = edited
    next(button for button in app.button if button.label == "Cut-off 저장").click().run()

    assert not app.exception
    assert not app.warning, [str(item.value) for item in app.warning]
    assert outsider.load_process_cutoff()["Cutoff일수"].tolist() == [12.0, 5.0]
    clear_equipment_repository()
