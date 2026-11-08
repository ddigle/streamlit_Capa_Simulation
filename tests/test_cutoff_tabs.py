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
from alert_marks import active_state, infos, states, successes
from streamlit.testing.v1 import AppTest
from test_equipment_pages import _open_settings, _open_tab, _page_script
from widget_browser import BrowserTables

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.cutoff_management import (
    CUTOFF_DRAFT_KEY,
    CUTOFF_SAVE_HELP,
    CUTOFF_UNCHANGED_MESSAGE,
)
from capa_simulation.components.sample_data import (
    NO_UNITS_HELP,
    NO_UNITS_MARK,
    SAMPLE_TOGGLE_KEY,
)
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


@pytest.mark.parametrize("with_cutoff", [False, True])
def test_the_gap_tab_says_no_units_with_the_sample_switch_off(
    tmp_path: Path, with_cutoff: bool
) -> None:
    """호기가 없고 샘플도 끄면 머리 배지도 조건 카드 표지도 없는 이 탭의 본문이 호기 없음을 말한다 —
    빈 까닭이 Cut-off 와 상관없다. 카드는 접힌 채 조회 조건을 담아 표지를 카드에 두지 않는다."""
    database_path = tmp_path / "availability.duckdb"
    if with_cutoff:
        repository = DuckDBEquipmentRepository(database_path)
        repository.initialize()
        repository.save_process_cutoff(
            pd.DataFrame({"공정": ["Die Attach"], "Cutoff일수": [15.0], "비고": [None]})
        )
    app = AppTest.from_string(_page_script(PAGE, database_path), default_timeout=120)
    app.session_state[SAMPLE_TOGGLE_KEY] = False

    app = _open_tab(app.run(), "Static 대비 일정")

    assert not app.exception
    (mark,) = [item for item in app.main.caption if str(item.value) == NO_UNITS_MARK]
    assert mark.proto.help == NO_UNITS_HELP
    assert NO_UNITS_MARK not in [str(item.value) for item in app.sidebar.caption]
    clear_equipment_repository()


def test_the_gap_tab_stays_silent_about_units_while_the_sample_shows(tmp_path: Path) -> None:
    """샘플을 켠 회차에는 호기가 보이므로 호기 없음 표지가 서지 않는다."""
    app = _run(tmp_path / "availability.duckdb", tab="Static 대비 일정")

    assert not app.exception
    assert NO_UNITS_MARK not in [str(item.value) for item in app.main.caption]
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


def _locked_cutoff_body(database_path: str) -> None:
    """가정 설비 시나리오의 팝업 본문 — 표는 읽기만 하고 고칠 수 없다."""
    from pathlib import Path

    from capa_simulation.components.cutoff_management import render_cutoff_management
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

    repository = DuckDBEquipmentRepository(Path(database_path))
    repository.initialize()
    render_cutoff_management(
        repository, equipment_processes=["E2E~공정~X"], locked_reason="가정 설비 시나리오"
    )


def test_the_locked_table_keeps_only_the_toolbar_download(tmp_path: Path) -> None:
    """잠긴 표는 읽기만 해 곁 CSV 단추를 두지 않는다 — 내려받기는 표 도구 막대 한 곳이다(설계 규칙
    UI-LAY-12 · 답 csv-dup). 고치는 표의 CSV 는 왕복 양식이라 그대로다. 표 위에 누를 것이 없어 앞
    띄움도 없다(`tests/test_table_toolbar.py`)."""
    locked = AppTest.from_function(
        _locked_cutoff_body, args=(str(tmp_path / "locked.duckdb"),), default_timeout=60
    ).run()

    assert not locked.exception, [item.message for item in locked.exception]
    assert len(locked.dataframe) == 1
    assert not locked.get("download_button")
    assert not locked.get("space")
    assert any("Cut-off 잠김" in str(item.value) for item in locked.caption)

    editable = AppTest.from_function(
        _cutoff_body, args=(str(tmp_path / "editable.duckdb"),), default_timeout=60
    ).run()

    assert [item.proto.url != "" for item in editable.get("download_button")] == [True]
    clear_equipment_repository()


def test_the_locked_table_leaves_the_missing_cutoff_to_the_alert(tmp_path: Path) -> None:
    """곁 경고는 고칠 표가 바로 아래일 때만이다 — 잠긴 표에는 고칠 입력이 없어 경고 상자를 세우지
    않고, 같은 조건은 화면의 상태 알림 `EQ-12` 가 말한다(설계 규칙 UI-NTF-02 · g8-15)."""
    locked = AppTest.from_function(
        _locked_cutoff_body, args=(str(tmp_path / "locked.duckdb"),), default_timeout=60
    ).run()

    assert not locked.exception, [item.message for item in locked.exception]
    assert not [str(item.value) for item in locked.warning]
    assert not any("모두 채워졌습니다" in str(item.value) for item in locked.caption)
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


def _cutoff_app(
    database_path: Path, stored: dict[str, float], processes: list[str]
) -> tuple[AppTest, DuckDBEquipmentRepository]:
    """`stored` 를 저장해 둔 Cut-off 표를 그린다. 돌려주는 저장소는 화면 밖에서 DB 를 읽는다."""
    outside = DuckDBEquipmentRepository(database_path)
    outside.initialize()
    outside.save_process_cutoff(
        pd.DataFrame({"공정": list(stored), "Cutoff일수": list(stored.values())})
    )
    clear_equipment_repository()
    script = f"""
from pathlib import Path

from capa_simulation.components.cutoff_management import render_cutoff_management
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

render_cutoff_management(
    DuckDBEquipmentRepository(Path({str(database_path)!r})),
    equipment_processes={processes!r},
)
"""
    return AppTest.from_string(script, default_timeout=60).run(), outside


def _editor_key(app: AppTest) -> str:
    """지금 그려진 Cut-off 편집표의 위젯 key — 표를 다시 세우면 세대 꼬리가 바뀐다."""
    (found,) = [
        proto_id
        for node in app._tree
        if isinstance(proto_id := getattr(getattr(node, "proto", None), "id", ""), str)
        and "equipment_cutoff_editor_v1" in proto_id
    ]
    return found.rsplit("-", 1)[-1]


def _press(tables: BrowserTables, label: str) -> AppTest:
    """브라우저처럼 단추를 누른다 — 폼 안 단추면 그 폼을 제출해 표에 친 칸이 이 회차에 함께 가고, 폼
    밖 단추면 친 칸은 브라우저에 남는다."""
    button = next(item for item in tables.app.button if item.label == label)
    form_id = button.proto.form_id
    button.click()
    app = tables.run(submit=form_id or None)
    assert not app.exception, [item.message for item in app.exception]
    return app


def _saved(outside: DuckDBEquipmentRepository) -> dict[str, float]:
    saved = outside.load_process_cutoff()
    return dict(zip(saved["공정"], saved["Cutoff일수"], strict=True))


def test_filling_keeps_a_typed_value_and_adds_the_missing_process(tmp_path: Path) -> None:
    """저장 안 한 칸을 친 채 「설비 공정으로 채우기」 를 눌렀다. 단추가 폼 밖이라 친 칸이 서버에
    없는데 표를 새로 세워 그 값이 말없이 사라졌고, 이어 저장하면 「바뀐 것이 없습니다」
    였다(2026-11-08 점검). 풍선은 「적어 둔 값은 그대로 둡니다」 라고 한다."""
    app, outside = _cutoff_app(
        tmp_path / "fill.duckdb", {"Process-A": 10.0}, ["Process-A", "Process-B"]
    )
    tables = BrowserTables(app, forms=True)
    tables.edit(_editor_key(app), 0, "Cutoff일수", 31.5)

    _press(tables, "설비 공정으로 채우기")

    draft = app.session_state[CUTOFF_DRAFT_KEY]
    assert draft["공정"].tolist() == ["Process-A", "Process-B"]
    assert draft["Cutoff일수"].iloc[0] == 31.5
    assert pd.isna(draft["Cutoff일수"].iloc[1])
    assert "1개 행을 표 끝에 더했습니다." in [str(item.value) for item in successes(app)]
    # 채우기는 저장이 아니다 — 저장은 「Cut-off 저장」 만 한다.
    assert _saved(outside) == {"Process-A": 10.0}

    _press(tables, "Cut-off 저장")

    assert _saved(outside) == {"Process-A": 31.5}
    clear_equipment_repository()


def test_filling_with_nothing_to_add_keeps_the_table_and_says_so(tmp_path: Path) -> None:
    """더할 공정이 없으면 표를 다시 세우지 않고 누른 회차에 그렇게 답한다 — 친 값은 저장까지
    간다. 전에는 무응답으로 표만 새로 서서 친 값을 버렸다(2026-11-08 점검)."""
    app, outside = _cutoff_app(
        tmp_path / "fill.duckdb",
        {"Process-A": 10.0, "Process-B": 5.0},
        ["Process-A", "Process-B"],
    )
    editor = _editor_key(app)
    tables = BrowserTables(app, forms=True)
    tables.edit(editor, 0, "Cutoff일수", 33.5)

    _press(tables, "설비 공정으로 채우기")

    assert _editor_key(app) == editor
    assert app.session_state[CUTOFF_DRAFT_KEY]["Cutoff일수"].tolist() == [33.5, 5.0]
    assert "더할 공정이 없습니다." in [str(item.value) for item in infos(app)]
    assert _saved(outside) == {"Process-A": 10.0, "Process-B": 5.0}

    _press(tables, "Cut-off 저장")

    assert _saved(outside) == {"Process-A": 33.5, "Process-B": 5.0}
    clear_equipment_repository()


def test_a_second_press_of_fill_does_not_cover_what_the_first_added(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """빠른 두 번 누름은 첫 누름이 행을 더한 뒤라 둘째 누름에 더할 공정이 없다. 그 답이 「1개 행을
    더했습니다」 를 덮어 행이 늘었는데 「더할 공정이 없습니다」 만 떴다(2026-11-08 브라우저 측정).
    창이 지난 뒤의 누름에는 그대로 답한다."""
    app, _ = _cutoff_app(tmp_path / "fill.duckdb", {"Process-A": 10.0}, ["Process-A", "Process-B"])
    tables = BrowserTables(app, forms=True)
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)

    _press(tables, "설비 공정으로 채우기")
    _press(tables, "설비 공정으로 채우기")

    assert app.session_state[CUTOFF_DRAFT_KEY]["공정"].tolist() == ["Process-A", "Process-B"]
    assert "1개 행을 표 끝에 더했습니다." in [str(item.value) for item in successes(app)]
    assert "더할 공정이 없습니다." not in [str(item.value) for item in infos(app)]

    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    _press(tables, "설비 공정으로 채우기")

    assert "더할 공정이 없습니다." in [str(item.value) for item in infos(app)]
    clear_equipment_repository()


def test_filling_sees_a_row_added_in_the_table_but_not_saved(tmp_path: Path) -> None:
    """표에 손으로 더한 행은 제출 전에는 서버에 없다 — 채우기가 폼을 받아야 같은 공정을 두 번 더하지
    않는다."""
    app, outside = _cutoff_app(
        tmp_path / "fill.duckdb", {"Process-A": 10.0}, ["Process-A", "Process-B"]
    )
    tables = BrowserTables(app, forms=True)
    tables.add(_editor_key(app), {"공정": "Process-B", "Cutoff일수": 7.0})

    _press(tables, "설비 공정으로 채우기")

    draft = app.session_state[CUTOFF_DRAFT_KEY]
    assert draft["공정"].tolist() == ["Process-A", "Process-B"]
    assert "더할 공정이 없습니다." in [str(item.value) for item in infos(app)]
    # 행을 더한 제출의 초안이 RangeIndex 가 아니면 다음 표가 인덱스를 머리 없는 필수 칸으로 세우고,
    # 그 칸이 빈 새 행은 브라우저가 보내지 않아 저장 알림은 뜨는데 그 행만 빠졌다(2026-11-08 검토).
    assert isinstance(draft.index, pd.RangeIndex)

    _press(tables, "Cut-off 저장")

    assert _saved(outside) == {"Process-A": 10.0, "Process-B": 7.0}
    clear_equipment_repository()


def test_filling_under_a_row_filter_keeps_the_typed_value(tmp_path: Path) -> None:
    """공정 필터가 걸린 표는 일부 행만 보이지만 초안 전체에 값을 얹고 그 끝에 더한다."""
    app, outside = _cutoff_app(
        tmp_path / "fill.duckdb",
        {"Process-A": 10.0, "Process-C": 20.0},
        ["Process-A", "Process-B", "Process-C"],
    )
    tables = BrowserTables(app, forms=True)
    app.multiselect(key="equipment_cutoff_view_v1_filter_공정").select("Process-C")
    _press(tables, "보기 적용")
    tables.edit(_editor_key(app), 0, "Cutoff일수", 21.5)

    _press(tables, "설비 공정으로 채우기")

    draft = app.session_state[CUTOFF_DRAFT_KEY]
    assert draft["공정"].tolist() == ["Process-A", "Process-C", "Process-B"]
    assert draft["Cutoff일수"].iloc[:2].tolist() == [10.0, 21.5]
    assert pd.isna(draft["Cutoff일수"].iloc[2])

    _press(tables, "Cut-off 저장")

    assert _saved(outside) == {"Process-A": 10.0, "Process-C": 21.5}
    clear_equipment_repository()


def test_a_cell_fixed_after_a_refused_save_reaches_the_next_save(tmp_path: Path) -> None:
    """거부된 저장 뒤 칸을 고쳐 다시 저장했다. 거부 회차가 초안만 바꾸고 끝나 화면의 표가 옛
    위젯으로 남았고, 고친 칸은 그 옛 위젯 앞으로 가 버려져 표가 거부된 값으로 돌아갔다(2026-11-08
    검토)."""
    app, outside = _cutoff_app(tmp_path / "fill.duckdb", {"Process-A": 10.0}, ["Process-A"])
    tables = BrowserTables(app, forms=True)
    tables.edit(_editor_key(app), 0, "Cutoff일수", 99999.0)

    _press(tables, "Cut-off 저장")

    assert ["넘습니다" in str(item.value) for item in app.error] == [True]
    assert app.session_state[CUTOFF_DRAFT_KEY]["Cutoff일수"].tolist() == [99999.0]
    assert _saved(outside) == {"Process-A": 10.0}

    tables.edit(_editor_key(app), 0, "Cutoff일수", 30.5)
    _press(tables, "Cut-off 저장")

    assert not app.error
    assert _saved(outside) == {"Process-A": 30.5}
    clear_equipment_repository()


def test_a_cell_fixed_after_a_refused_save_survives_filling(tmp_path: Path) -> None:
    """채우기도 같은 폼의 제출이다 — 거부 뒤 고친 칸이 풍선 말대로 그대로 남아 저장까지 간다."""
    app, outside = _cutoff_app(
        tmp_path / "fill.duckdb", {"Process-A": 10.0}, ["Process-A", "Process-B"]
    )
    tables = BrowserTables(app, forms=True)
    tables.edit(_editor_key(app), 0, "Cutoff일수", 99999.0)
    _press(tables, "Cut-off 저장")

    tables.edit(_editor_key(app), 0, "Cutoff일수", 36.5)
    _press(tables, "설비 공정으로 채우기")

    draft = app.session_state[CUTOFF_DRAFT_KEY]
    assert draft["공정"].tolist() == ["Process-A", "Process-B"]
    assert draft["Cutoff일수"].iloc[0] == 36.5

    _press(tables, "Cut-off 저장")

    assert _saved(outside) == {"Process-A": 36.5}
    clear_equipment_repository()


def test_a_cell_fixed_after_a_refused_save_under_a_row_filter_reaches_the_next_save(
    tmp_path: Path,
) -> None:
    """필터가 걸린 표는 행 고정이라 위젯이 그대로 서고 편집이 남는다 — 다시 그려도 거른 행의 칸이
    다른 행에 붙거나 사라지지 않는다."""
    app, outside = _cutoff_app(
        tmp_path / "fill.duckdb",
        {"Process-A": 10.0, "Process-C": 20.0},
        ["Process-A", "Process-C"],
    )
    tables = BrowserTables(app, forms=True)
    app.multiselect(key="equipment_cutoff_view_v1_filter_공정").select("Process-C")
    _press(tables, "보기 적용")
    tables.edit(_editor_key(app), 0, "Cutoff일수", 99999.0)

    _press(tables, "Cut-off 저장")

    assert ["넘습니다" in str(item.value) for item in app.error] == [True]

    tables.edit(_editor_key(app), 0, "Cutoff일수", 21.5)
    _press(tables, "Cut-off 저장")

    assert _saved(outside) == {"Process-A": 10.0, "Process-C": 21.5}
    clear_equipment_repository()


def test_a_cell_typed_after_an_unchanged_save_reaches_the_next_save(tmp_path: Path) -> None:
    """「바뀐 것이 없습니다」 도 초안을 바꾼다 — 저장에 들지 않는 빈 행의 비고가 그렇다. 그 회차가
    표를 다시 그리지 않으면 다음 칸이 버려져 같은 답만 되풀이했다(2026-11-08 검토)."""
    app, outside = _cutoff_app(
        tmp_path / "fill.duckdb", {"Process-A": 10.0}, ["Process-A", "Process-B"]
    )
    tables = BrowserTables(app, forms=True)
    _press(tables, "설비 공정으로 채우기")
    tables.edit(_editor_key(app), 1, "비고", "memo")

    _press(tables, "Cut-off 저장")

    assert [str(item.value) for item in app.info] == [CUTOFF_UNCHANGED_MESSAGE]
    assert _saved(outside) == {"Process-A": 10.0}

    tables.edit(_editor_key(app), 1, "Cutoff일수", 6.0)
    _press(tables, "Cut-off 저장")

    assert _saved(outside) == {"Process-A": 10.0, "Process-B": 6.0}
    assert outside.load_process_cutoff()["비고"].tolist()[1] == "memo"
    clear_equipment_repository()


def test_a_cell_typed_in_the_refusal_window_reaches_the_next_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """남의 저장에 거부된 창 안의 누름은 쓰지 않지만, 거기 실린 칸은 다음 저장까지 간다."""
    app, outside = _cutoff_app(
        tmp_path / "fill.duckdb", {"Process-A": 10.0, "Process-B": 5.0}, ["Process-A", "Process-B"]
    )
    tables = BrowserTables(app, forms=True)
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    outside.save_process_cutoff(
        pd.DataFrame({"공정": ["Process-A", "Process-B"], "Cutoff일수": [12.0, 5.0]})
    )
    clear_process_cutoff_cache()
    _press(tables, "Cut-off 저장")
    assert any("다른 사용자가 먼저" in str(item.value) for item in app.warning)

    tables.edit(_editor_key(app), 1, "Cutoff일수", 8.5)
    _press(tables, "Cut-off 저장")

    assert ["다른 사용자가 먼저" in str(item.value) for item in app.warning] == [True]
    assert _saved(outside) == {"Process-A": 12.0, "Process-B": 5.0}

    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    tables.edit(_editor_key(app), 0, "Cutoff일수", 13.5)
    _press(tables, "Cut-off 저장")

    assert _saved(outside) == {"Process-A": 13.5, "Process-B": 8.5}
    clear_equipment_repository()


def test_a_save_right_after_filling_answers_for_the_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """채우기와 저장의 표지 칸이 하나면 1초 창 안의 저장을 채우기의 둘째 누름으로 읽어, 저장을 누른
    사람이 저장 쪽 답을 받지 못했다(2026-11-08 검토)."""
    app, _ = _cutoff_app(tmp_path / "fill.duckdb", {"Process-A": 10.0}, ["Process-A", "Process-B"])
    tables = BrowserTables(app, forms=True)
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)

    _press(tables, "설비 공정으로 채우기")
    _press(tables, "Cut-off 저장")

    assert CUTOFF_UNCHANGED_MESSAGE in [str(item.value) for item in app.info]
    clear_equipment_repository()


def test_a_fill_right_after_a_save_answers_for_the_fill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """같은 까닭의 반대 차례 — 저장 뒤 창 안의 채우기도 제 답을 받는다."""
    app, outside = _cutoff_app(tmp_path / "fill.duckdb", {"Process-A": 10.0}, ["Process-A"])
    tables = BrowserTables(app, forms=True)
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    tables.edit(_editor_key(app), 0, "Cutoff일수", 12.5)

    _press(tables, "Cut-off 저장")
    _press(tables, "설비 공정으로 채우기")

    assert "더할 공정이 없습니다." in [str(item.value) for item in infos(app)]
    assert _saved(outside) == {"Process-A": 12.5}
    clear_equipment_repository()


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
    assert CUTOFF_UNCHANGED_MESSAGE in [str(item.value) for item in infos(app)]
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


def test_changing_the_view_keeps_a_typed_cell_and_the_view_apply_brings_both(
    tmp_path: Path,
) -> None:
    """칸을 친 채 「표 보기 설정」 의 공정 필터 · 볼 컬럼을 바꾸면 회차가 돌며 표를 새로 세워 친
    칸이 말없이 사라졌다(AVI 44.5 → 20.8, 저장 「바뀐 것이 없습니다」 — X1). 보기 설정은 폼 안이라
    바꾸기만 해서는 회차가 돌지 않고, 「보기 적용」 이 친 칸과 새 보기를 함께 가져간다 — 친 칸은
    앞 보기의 행 자리로 읽힌다."""
    app, outside = _cutoff_app(
        tmp_path / "view.duckdb",
        {"Process-A": 10.0, "Process-C": 20.0},
        ["Process-A", "Process-C"],
    )
    assert app.button(key="equipment_cutoff_view_apply_v1").proto.form_id
    tables = BrowserTables(app, forms=True)
    tables.edit(_editor_key(app), 0, "Cutoff일수", 44.5)
    app.multiselect(key="equipment_cutoff_view_v1_filter_공정").select("Process-C")
    app.multiselect(key="equipment_cutoff_view_v1_columns").set_value([])

    _press(tables, "보기 적용")

    draft = app.session_state[CUTOFF_DRAFT_KEY]
    assert dict(zip(draft["공정"], draft["Cutoff일수"], strict=True)) == {
        "Process-A": 44.5,
        "Process-C": 20.0,
    }
    (editor,) = app.dataframe
    assert len(editor.value) == 1

    _press(tables, "Cut-off 저장")

    assert _saved(outside) == {"Process-A": 44.5, "Process-C": 20.0}
    clear_equipment_repository()
