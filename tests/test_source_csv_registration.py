# Purpose: DB 등록 탭 「CSV 파일」 길(올림 · 목록 · 등록 칸 · 저장 · 길 바꿈 · 겹친 저장)을 AppTest
# 로 본다.

"""DB 등록 탭 「CSV 파일」 길 — 합성 견본(`tests/source_csv_samples.py` · 내장 합성 시드 값)만 쓴다.

등록 화면(`render_bigdataquery_registration`)을 실제 저장소(임시 DuckDB)로 그리고 원천 종류 단추를
`CSV 파일` 로 바꿔 올림 칸에 견본 CSV 를 싣는다. 스크립트 끝에 업로드 관리자가 쥔 파일 수를 세션
칸에 적는다 — AppTest 는 `run()` 마다 관리자를 새로 세우므로 그 회차 안에서 센다."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from alert_marks import active_state, events, place_errors, successes
from source_csv_samples import DEMO_CODE, demo_core_rows, source_csv_bytes
from streamlit.testing.v1 import AppTest
from test_source_csv import PART_CUSTOM, _with_custom
from test_write_entry_points import _press_twice, _SecondPress

from capa_simulation.components import bigdataquery_registration as registration
from capa_simulation.components import source_csv_registration as route
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.io import company_bigdataquery_adapter as adapter
from capa_simulation.io import source_csv
from capa_simulation.io.source_csv import DECODE_TEXT, SOURCE_CSV_SOURCE_TYPE
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.bigdataquery_catalog_view import UNSAVABLE_REASON
from capa_simulation.services.builtin_seed import load_builtin_display_order
from capa_simulation.services.custom_source_check import SWITCHED_OFF_MEMO
from capa_simulation.services.source_csv_view import REGISTERED_AT_ERROR

CSV_SCRIPT = """
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from capa_simulation.components import bigdataquery_registration as registration
from capa_simulation.io.company_bigdataquery_adapter import QueryWindow
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.bigdataquery_catalog_view import normalize_catalog

# 시험이 켜면 DB 목록 결과 하나와 그 첫 행 고름을 한 번 심는다(길 바꿈 뒤 남는지 본다).
if st.session_state.pop("__catalog__", False):
    window = QueryWindow(start_date=date(2026, 9, 1), end_date=date(2026, 9, 8))
    catalog = normalize_catalog(
        pd.DataFrame(
            {
                "simulation_name": ["알파 시뮬"],
                "simulation_code": ["DEMO-A-001"],
                "plan_name": ["PLAN 알파"],
                "plan_code": ["DEMO-PLAN-1"],
                "regist_data": ["2026-09-02 03:04:05"],
            }
        )
    )
    st.session_state[registration.CATALOG_RESULT_KEY] = registration.CatalogResult(
        frame=catalog,
        window=window,
        queried_at=datetime(2026, 9, 8, 10, 0, 0),
        token="demo-token",
    )
    registration._apply_pick(
        registration.CatalogPick(row=registration.catalog_row_at(catalog, 0), window=window)
    )

database_path = st.session_state["__database__"]
registration.render_bigdataquery_registration(
    DuckDBScenarioRepository(Path(database_path)), database_path
)
context = get_script_run_ctx()
st.session_state["__held__"] = len(
    context.uploaded_file_mgr.file_storage.get(context.session_id, {})
)
"""

SAVE_LABEL = route.SOURCE_CSV_SAVE_LABEL
DB_SAVE_LABEL = "DB 조회 후 시나리오 저장"


@pytest.fixture(autouse=True)
def _no_process_labels_from_the_repository_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """저장 뒤 알림의 공정 표시명은 저장소 `data/` DB 를 읽는다 — 이 파일의 시험은 그 DB 를 열지
    않는다."""
    monkeypatch.setattr(registration, "get_process_labels", ProcessLabels)


def _database(tmp_path: Path) -> Path:
    """표시순서까지 채운 빈 저장소. 등록은 공용 표시순서를 읽는다."""
    database = tmp_path / "registration.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    repository.initialize_global_display_order(load_builtin_display_order())
    return database


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _app(database: Path, **session: object) -> AppTest:
    app = AppTest.from_string(CSV_SCRIPT, default_timeout=120)
    app.session_state["__database__"] = str(database)
    for key, value in session.items():
        app.session_state[key] = value
    return _ok(app.run())


def _csv_route(app: AppTest) -> AppTest:
    return _ok(app.segmented_control(key=registration.SOURCE_ROUTE_KEY).set_value("CSV 파일").run())


def _db_route(app: AppTest) -> AppTest:
    return _ok(app.segmented_control(key=registration.SOURCE_ROUTE_KEY).set_value("DB 조회").run())


def _rows(code: str = DEMO_CODE) -> list[dict[str, str]]:
    """내장 합성 시드 전부를 한 코드로 — 부품마다 CUSTOM 을 채운다(시드는 비어 있다)."""
    return _with_custom(demo_core_rows(code=code))


def _upload(app: AppTest, data: bytes, name: str = "DEMO_원천.csv") -> AppTest:
    app.file_uploader[0].set_value((name, data, "text/csv"))
    return _ok(app.run())


def _button(app: AppTest, label: str) -> Any:
    return next(button for button in app.button if button.label == label)


def _field(app: AppTest, label: str) -> Any:
    return next(widget for widget in app.text_input if widget.label == label)


def _save(app: AppTest) -> AppTest:
    return _ok(_button(app, SAVE_LABEL).click().run())


def _scenarios(database: Path) -> list[Any]:
    return DuckDBScenarioRepository(database).list_scenarios(include_archived=True)


def test_the_db_route_is_the_default_and_has_no_upload_box(tmp_path: Path) -> None:
    """원천 종류 단추가 작업 줄 맨 앞이고 처음 값은 DB 조회다 — 그때 화면은 지금과 같다(올림 칸 ·
    CSV 저장 단추 없음)."""
    app = _app(_database(tmp_path))

    switch = app.segmented_control(key=registration.SOURCE_ROUTE_KEY)
    assert switch.label == "원천"
    assert list(switch.options) == ["DB 조회", "CSV 파일"]
    assert switch.value == "DB 조회"
    assert not app.file_uploader
    labels = {button.label for button in app.button}
    assert DB_SAVE_LABEL in labels and SAVE_LABEL not in labels


def test_the_source_csv_uploader_has_its_own_limit(tmp_path: Path) -> None:
    """올림 칸은 서버 상한을 물려받지 않고 칸 고유 상한 50MB 로 막는다 — 칸 안내 「50MB per file」
    과 브라우저가 올리기 전에 막는 크기가 이 값이다. 라벨은 접어 접근성 이름으로만 남는다."""
    app = _csv_route(_app(_database(tmp_path)))

    [uploader] = app.file_uploader
    assert route.SOURCE_CSV_UPLOAD_LIMIT_MB == 50
    assert uploader.proto.max_upload_size_mb == route.SOURCE_CSV_UPLOAD_LIMIT_MB
    assert uploader.label == "원천 CSV"
    assert list(uploader.proto.type) == [".csv"]


def test_without_a_file_the_form_stands_with_a_locked_save(tmp_path: Path) -> None:
    """파일이 없으면 목록은 없고 등록 칸은 서되 저장 단추가 잠겨 까닭 풍선을 단다(설계 규칙
    UI-INP-07 — 지금만 못 하는 조작). DB 저장 단추 · 상세 조회 기간은 이 길에 없다."""
    app = _csv_route(_app(_database(tmp_path)))

    assert not app.dataframe and not place_errors(app)
    save = _button(app, SAVE_LABEL)
    assert save.disabled and save.help == route.NO_FILE_HELP
    assert DB_SAVE_LABEL not in {button.label for button in app.button}
    assert [widget.label for widget in app.text_input] == [
        "시뮬레이션 코드",
        "원천 시뮬레이션명",
        "저장할 시나리오명",
        "초기 리비전명",
        "원천 등록시점 (선택)",
    ]
    assert _field(app, "시뮬레이션 코드").disabled


def test_uploading_a_csv_fills_the_form_and_saves_a_csv_scenario(tmp_path: Path) -> None:
    """올리면 목록 한 행(코드 하나 — 첫 행이 골라짐)과 등록 칸 처음 값이 서고, 저장하면 DB 등록과
    같은 저장 길로 시나리오가 선다. 원천 유형은 `CSV_CORE_DATA_UPLOAD`, 메모 꼬리는 파일 이름과
    CUSTOM 파일 값 종류 수이고, 성공 알림은 DB 등록과 같은 글이다. 저장하면 올림 칸이 비고 업로드
    관리자가 쥔 바이트도 지운다. 합성 시드 — 샘플 관측."""
    database = _database(tmp_path)
    app = _upload(_csv_route(_app(database)), source_csv_bytes(_rows()))

    assert not place_errors(app)
    assert app.session_state["__held__"] == 1
    [listed] = app.dataframe
    assert set(listed.value["시뮬레이션 코드"]) == {DEMO_CODE}
    assert any(caption.value.startswith("**원천 CSV** · 코드 1 · ") for caption in app.caption)
    assert _field(app, "시뮬레이션 코드").value == DEMO_CODE
    assert _field(app, "원천 시뮬레이션명").value == DEMO_CODE
    assert _field(app, "저장할 시나리오명").value == f"{DEMO_CODE} ({DEMO_CODE})"
    assert _field(app, "초기 리비전명").value == "초기 리비전"
    assert _field(app, "원천 등록시점 (선택)").value == ""
    note = str(app.text_area[0].value)
    assert note.startswith("원천 PLAN ")
    save = _button(app, SAVE_LABEL)
    assert not save.disabled and not save.help

    app = _save(app)

    assert not place_errors(app), place_errors(app)
    assert [str(item.value) for item in successes(app)] == [
        f"{DEMO_CODE} ({DEMO_CODE})을 저장하고 r1을 올렸습니다."
    ]
    [scenario] = _scenarios(database)
    assert scenario.source_type == SOURCE_CSV_SOURCE_TYPE
    assert scenario.source_simulation_code == DEMO_CODE
    assert scenario.source_simulation_name == DEMO_CODE
    assert scenario.source_registered_at is None
    repository = DuckDBScenarioRepository(database)
    snapshot = repository.load_revision(scenario.active_revision_id)
    assert str(snapshot.revision.note).startswith(
        f"{note} · CSV 파일 DEMO_원천.csv · CUSTOM 파일 값 — 종류 {len(PART_CUSTOM)}"
    )
    source = repository.load_source_data(scenario.scenario_id)
    assert set(source["CUSTOM"]) == set(PART_CUSTOM.values())
    assert set(source["설비대수변화관리"].fillna("")) == {""}
    assert [uploader.value for uploader in app.file_uploader] == [None]
    assert app.session_state["__held__"] == 0
    assert route.SOURCE_CSV_STATE_KEY not in app.session_state
    assert not app.dataframe
    assert _button(app, SAVE_LABEL).disabled


def test_the_registered_at_field_is_saved_as_source_registered_at(tmp_path: Path) -> None:
    """등록시점 칸을 채우면 원천 등록시각(머리 띠 · 공식 주차 기준 시각)으로 저장된다."""
    database = _database(tmp_path)
    app = _upload(_csv_route(_app(database)), source_csv_bytes(_rows()))
    _field(app, "원천 등록시점 (선택)").set_value("2026-11-23 08:30:00")

    _save(app)

    [scenario] = _scenarios(database)
    assert scenario.source_registered_at == datetime(2026, 11, 23, 8, 30)


def test_an_unreadable_file_shows_one_refusal_line_and_locks_save(tmp_path: Path) -> None:
    """못 읽은 파일은 올림 칸 아래 거부 한 줄이고 목록은 없고 저장은 잠겨 그 줄을 가리킨다 — 다른
    파일을 올리면 사라진다."""
    database = _database(tmp_path)
    app = _upload(_csv_route(_app(database)), b"\xff\xfe\xfa\x00\x81", "DEMO_bad.csv")

    assert [str(item.value) for item in app.error] == [DECODE_TEXT]
    assert not app.dataframe
    save = _button(app, SAVE_LABEL)
    assert save.disabled and save.help == route.UNREADABLE_HELP

    app = _upload(app, source_csv_bytes(_rows()))

    assert not app.error
    assert len(app.dataframe) == 1
    assert not _button(app, SAVE_LABEL).disabled


def test_the_same_file_is_read_once_across_reruns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """파일 id 가 같으면 다시 흘려 읽지 않는다(설계 규칙 UI-PRF-01) — 탭 본문은 회차마다 돈다."""
    reads: list[str] = []
    original = source_csv.summarize_source_csv

    def counted(*args: Any, **kwargs: Any) -> Any:
        reads.append(str(kwargs.get("file_id")))
        return original(*args, **kwargs)

    monkeypatch.setattr(route, "summarize_source_csv", counted)
    app = _upload(_csv_route(_app(_database(tmp_path))), source_csv_bytes(_rows()))
    _ok(app.run())
    _ok(app.run())

    assert len(reads) == 1


def test_a_file_with_two_codes_waits_for_a_pick(tmp_path: Path) -> None:
    """코드가 여럿이면 목록은 (코드, PLAN) 행 모두이고 아무 행도 골라지지 않아 저장이 잠긴다."""
    rows = _rows()
    second = [{**row, "시뮬레이션 ID": "DEMO-SIM-2"} for row in _rows()[:4]]
    app = _upload(_csv_route(_app(_database(tmp_path))), source_csv_bytes([*rows, *second]))

    [listed] = app.dataframe
    assert set(listed.value["시뮬레이션 코드"]) == {DEMO_CODE, "DEMO-SIM-2"}
    assert any(caption.value.startswith("**원천 CSV** · 코드 2 · ") for caption in app.caption)
    assert _field(app, "시뮬레이션 코드").value == ""
    save = _button(app, SAVE_LABEL)
    assert save.disabled and save.help == route.NO_PICK_HELP


def test_an_unsavable_code_locks_save_with_the_db_list_reason(tmp_path: Path) -> None:
    """저장 불가 코드(영문 · 숫자 · `.` `_` `-` 밖 글자)는 DB 목록과 같은 까닭 풍선으로 잠긴다."""
    app = _upload(_csv_route(_app(_database(tmp_path))), source_csv_bytes(_rows("DEMO SIM#9")))

    save = _button(app, SAVE_LABEL)
    assert save.disabled and save.help == UNSAVABLE_REASON


def test_a_single_code_with_two_plans_is_picked_on_its_first_row(tmp_path: Path) -> None:
    """한 코드에 PLAN 이 여럿이면 목록은 PLAN 마다 한 행이고 첫 행이 골라진 채 등록 칸이 찬다 — 메모
    처음 값은 그 코드의 PLAN 모두다."""
    rows = _rows()
    for index, row in enumerate(rows):
        row["PLAN ID"] = "DEMO-P1" if index % 2 == 0 else "DEMO-P2"
    app = _upload(_csv_route(_app(_database(tmp_path))), source_csv_bytes(rows))

    [listed] = app.dataframe
    assert listed.value["PLAN 코드"].tolist() == ["DEMO-P1", "DEMO-P2"]
    assert _field(app, "시뮬레이션 코드").value == DEMO_CODE
    assert app.text_area[0].value == "원천 PLAN DEMO-P1 · DEMO-P2"
    assert not _button(app, SAVE_LABEL).disabled


def test_same_name_blank_fields_bad_time_and_changed_source_stop_in_the_result_slot(
    tmp_path: Path,
) -> None:
    """저장하지 못한 까닭은 단추 아래 결과 칸에 서고 아무것도 저장하지 않는다 — 같은 이름 · 빈 필수
    칸(한 번에) · 등록시점 꼴 · 같은 코드의 다른 원천(원천 코드 불변 — 파일로 다시 받는 길도
    말함)."""
    database = _database(tmp_path)
    app = _upload(_csv_route(_app(database)), source_csv_bytes(_rows()))
    app = _save(app)
    assert len(_scenarios(database)) == 1

    changed = _rows()
    changed[0]["생산수량"] = str(float(changed[0]["생산수량"] or 0) + 7.0)
    app = _upload(app, source_csv_bytes(changed), "DEMO_원천_다시.csv")

    app = _save(app)
    assert [str(item.value) for item in app.error] == [route.SAME_NAME_TEXT]

    _field(app, "원천 시뮬레이션명").set_value(" ")
    _field(app, "저장할 시나리오명").set_value("")
    app = _save(app)
    assert [str(item.value) for item in app.error] == [
        "필수 칸이 비어 있습니다: 원천 시뮬레이션명, 저장할 시나리오명"
    ]

    _field(app, "원천 시뮬레이션명").set_value("DEMO 다시")
    _field(app, "저장할 시나리오명").set_value("DEMO 다시 받은 원천")
    _field(app, "원천 등록시점 (선택)").set_value("2026-13-45 99:99")
    app = _save(app)
    assert [str(item.value) for item in app.error] == [REGISTERED_AT_ERROR]

    _field(app, "원천 등록시점 (선택)").set_value("")
    app = _save(app)
    [refused] = [str(item.value) for item in app.error]
    assert "원천 코드는 불변" in refused or "다른 원천 데이터" in refused
    assert "상세 조회 기간이나 파일을 바꿔" in refused
    assert len(_scenarios(database)) == 1
    # 거부된 저장은 올린 파일을 놓지 않는다 — 고쳐 다시 누를 수 있다.
    assert app.session_state["__held__"] == 1
    assert len(app.dataframe) == 1


def test_switching_routes_drops_the_upload_and_keeps_the_db_list(tmp_path: Path) -> None:
    """DB 조회 길로 바꾸면 올린 파일(요약 · 업로드 관리자의 바이트)을 놓는다 — 돌아오면 올림 칸이
    비어 있다. DB 목록 결과 · 고른 행 · 검색은 남고, DB 폼 글자 칸은 고른 행의 처음 값으로 다시
    찬다(고쳐 적은 글자는 사라진다 — 다른 화면에 다녀올 때와 같은 지금 대가)."""
    app = _app(_database(tmp_path), __catalog__=True)
    assert _field(app, "조회할 시뮬레이션 코드").value == "DEMO-A-001"
    app.text_input(key=registration.CATALOG_KEYWORD_KEY).set_value("알파")
    _field(app, "저장할 시나리오명").set_value("고쳐 적은 이름")
    app = _ok(app.run())

    app = _upload(_csv_route(app), source_csv_bytes(_rows()))
    assert app.session_state["__held__"] == 1
    assert route.SOURCE_CSV_STATE_KEY in app.session_state

    app = _db_route(app)

    assert app.session_state["__held__"] == 0
    assert route.SOURCE_CSV_STATE_KEY not in app.session_state
    assert registration.CATALOG_RESULT_KEY in app.session_state
    assert registration.CATALOG_PICK_KEY in app.session_state
    assert app.text_input(key=registration.CATALOG_KEYWORD_KEY).value == "알파"
    assert _field(app, "조회할 시뮬레이션 코드").value == "DEMO-A-001"
    assert _field(app, "저장할 시나리오명").value == "알파 시뮬 (DEMO-A-001)"

    app = _csv_route(app)

    assert [uploader.value for uploader in app.file_uploader] == [None]
    assert not app.dataframe
    assert _button(app, SAVE_LABEL).help == route.NO_FILE_HELP


def test_csv_save_is_open_without_custom_table_sql_or_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CUSTOM 원천 표 환경변수 · 조회 SQL · bigdataquery 패키지가 모두 없어도 CSV 길은 열린다 — DB
    저장 단추는 잠기고 `AD-04` 는 그대로 서지만, CSV 저장은 파일 CUSTOM 으로 시나리오를 올린다."""
    monkeypatch.delenv(adapter.BDQ_CUSTOM_TABLE_ENV, raising=False)
    monkeypatch.setattr(registration, "is_bigdataquery_catalog_configured", lambda: False)
    monkeypatch.setattr(registration, "is_bigdataquery_adapter_configured", lambda: False)
    monkeypatch.setattr(registration, "is_bigdataquery_package_available", lambda: False)
    database = _database(tmp_path)
    app = _app(database)
    db_save = _button(app, DB_SAVE_LABEL)
    assert db_save.disabled and db_save.help

    app = _upload(_csv_route(app), source_csv_bytes(_rows()))
    assert not _button(app, SAVE_LABEL).disabled
    app = _save(app)

    assert not place_errors(app), place_errors(app)
    assert active_state(app, "AD-04") is not None
    [scenario] = _scenarios(database)
    source = DuckDBScenarioRepository(database).load_source_data(scenario.scenario_id)
    assert set(source["CUSTOM"]) == set(PART_CUSTOM.values())


def test_csv_save_under_the_custom_source_switch_off_has_no_sc06_or_off_memo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CUSTOM 원천 끄개를 내려도 CSV 저장은 파일 CUSTOM 을 그대로 쓴다 — `custom_check` None 은
    「대조 없음」 이지 끔이 아니라 `SC-06` · 「CUSTOM 원천 붙이지 않음」 메모 조각이 서지 않는다."""
    monkeypatch.setenv(adapter.BDQ_CUSTOM_SOURCE_ENV, "off")
    database = _database(tmp_path)
    app = _save(_upload(_csv_route(_app(database)), source_csv_bytes(_rows())))

    assert not place_errors(app), place_errors(app)
    assert not events(app, "SC-06") and not events(app, "SC-05")
    [scenario] = _scenarios(database)
    repository = DuckDBScenarioRepository(database)
    note = str(repository.load_revision(scenario.active_revision_id).revision.note)
    assert SWITCHED_OFF_MEMO not in note
    source = repository.load_source_data(scenario.scenario_id)
    assert set(source["CUSTOM"]) == set(PART_CUSTOM.values())


def test_a_second_press_of_the_csv_save_creates_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """스피너 도는 저장 중 둘째 누름 — 저장은 한 번이고 그 이름 시나리오는 하나다. 둘째 회차는 같은
    이름 거절로 끝난다(DB 등록과 같은 `NAME_UNIQUE` 대가 — 쓰기 장부)."""
    database = _database(tmp_path)
    app = _upload(_csv_route(_app(database)), source_csv_bytes(_rows()))
    press = _SecondPress()
    monkeypatch.setattr(
        DuckDBScenarioRepository,
        "create_scenario",
        press.wrap(DuckDBScenarioRepository.create_scenario),
    )

    _press_twice(app, _button(app, SAVE_LABEL))

    _ok(app)
    assert press.tries == 1
    names = [scenario.scenario_name for scenario in _scenarios(database)]
    assert names == [f"{DEMO_CODE} ({DEMO_CODE})"]
    assert [str(item.value) for item in app.error] in ([], [route.SAME_NAME_TEXT])
