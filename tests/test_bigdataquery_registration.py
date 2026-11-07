# Purpose: bigdataquery registration 관련 정상·예외·회귀 동작을 검증한다.

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from alert_marks import (
    active_state,
    flashed,
    note_table,
    page_html,
    place_errors,
    successes,
    table_frame,
)
from streamlit.testing.v1 import AppTest

from capa_simulation import alerts
from capa_simulation.components import bigdataquery_registration as registration
from capa_simulation.components.date_panel import panel_key
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.scenario_list_state import DRAFT_KEY
from capa_simulation.io.company_bigdataquery_adapter import QueryWindow
from capa_simulation.services.bigdataquery_catalog_view import UNSAVABLE_REASON, CatalogRow
from capa_simulation.services.scenario_list_edits import ListDraft


@pytest.fixture(autouse=True)
def _no_process_labels_from_the_repository_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """충돌 보고의 공정 표시명은 저장소 `data/` DB 를 읽는다 — 이 파일의 시험은 그 DB 를 열지
    않는다."""
    monkeypatch.setattr(registration, "get_process_labels", ProcessLabels)


REPORT_SCRIPT = """
import pandas as pd
import streamlit as st

from capa_simulation.components.bigdataquery_registration import (
    REGISTRATION_FLASH_KEYS,
    _queue_reference_conflict_report,
    _render_oversized_conflict_download,
)
from capa_simulation.components.flash import render_flash

if "__queued__" not in st.session_state:
    st.session_state["__queued__"] = True
    _queue_reference_conflict_report(
        pd.DataFrame(
            {
                "RQ테이블": ["RQ_PKG_PLAN", "RQ_YLD"],
                "충돌그룹": ["RQ_PKG_PLAN-0001", "RQ_YLD-0001"],
                "업무키컬럼": ["생산계획년월 | 제품정보", "공정 | 제품정보"],
                "공정": [None, "P-Process"],
                "생산계획년월": [202608, None],
                "제품정보": ["Product-A", "Product-A"],
                "충돌컬럼": ["생산수량", "EDS_수율"],
                "후보값": ['[{"생산수량":100.0},{"생산수량":200.0}]', '[{"EDS_수율":0.8}]'],
                "선택값": ['{"생산수량":100.0}', '{"EDS_수율":0.8}'],
                "충돌행수": [2, 2],
                "임시제외행수": [1, 1],
                "후보원천행번호": ["1 | 2", "3 | 4"],
                "선택원천행번호": [1, 3],
                "임시처리": ["원천 행 순서상 첫 번째 행 유지", "원천 행 순서상 첫 번째 행 유지"],
            }
        ),
        "SIM-001",
    )
render_flash(*REGISTRATION_FLASH_KEYS)
_render_oversized_conflict_download()
"""


def _conflict_note(app: AppTest) -> dict[str, Any]:
    (shown,) = flashed(app, "warning")
    assert shown.note is not None
    return shown.note


def test_the_conflict_report_is_an_alert_with_its_tables_not_a_place_report() -> None:
    """등록 뒤 「기준정보 업무 키 충돌」 보고는 자리에 그리지 않는다(경고 · 요약 표 · CSV · 접힘
    없음 — 답 v10 (가)). 사건 알림 `SC-04` 하나와 그 Alarm 줄의 표 둘(요약 · 상세, 표마다 CSV)이고
    한 번만 보낸다. 알림창 짧은 글(앞 60자)이 결과를 말한다."""
    app = AppTest.from_string(REPORT_SCRIPT).run()

    assert not app.exception
    assert not app.warning and not app.dataframe and not app.expander
    assert not app.get("download_button")
    note = _conflict_note(app)
    assert (note["code"], note["level"], note["kind"]) == ("SC-04", "check", "event")
    assert note["short"].startswith(
        "기준정보 업무 키 충돌 2개 그룹 — 표 「임시처리」 규칙대로 한 행씩 임시 적용하고"
    )
    assert "Alarm › 이 줄 「충돌 요약」" in note["full"]
    assert "Alarm › 이 줄 「충돌 상세」" in note["full"]
    summary = note_table(note, registration.CONFLICT_SUMMARY_TITLE)
    assert summary["file"].startswith("RQ_업무키_충돌_요약_SIM-001_")
    assert table_frame(summary)["RQ테이블"].tolist() == ["RQ_PKG_PLAN", "RQ_YLD"]
    detail = note_table(note, registration.CONFLICT_DETAIL_TITLE)
    assert detail["file"].startswith("RQ_업무키_충돌_SIM-001_")
    assert detail["total"] == 2
    assert table_frame(detail)["충돌컬럼"].tolist() == ["생산수량", "EDS_수율"]

    app.run()

    assert not flashed(app, "warning")


@pytest.mark.parametrize("table", ["RQ_PKG_PLAN", "RQ_RUN_RATE"])
def test_the_conflict_alert_points_at_the_rule_its_summary_table_states(table: str) -> None:
    """알림 글이 고른 행을 「원천 첫 행」 이라고 하지 않는다 — 승자는 표마다 「값이 있는 첫 행」
    (효율 · UPEH 는 0 · 빈 값만 다르면 0 행)이라 원천 첫 행이 아닐 때가 많다(E2E 2026-11-02). 글은
    요약 표의 「임시처리」 칸(`conflict_resolution` 한 곳)을 가리킨다."""
    from capa_simulation.services.reference_conflicts import conflict_resolution

    app = AppTest.from_string(REPORT_SCRIPT.replace('"RQ_PKG_PLAN", "RQ_YLD"]', f'"{table}"] * 2'))
    app.run()

    assert not app.exception
    note = _conflict_note(app)
    assert "원천 첫 행" not in note["full"]
    assert "표 「임시처리」 규칙대로 한 행씩 임시 적용하고 등록했습니다" in note["full"]
    summary = table_frame(note_table(note, registration.CONFLICT_SUMMARY_TITLE))
    assert summary["임시처리"].tolist() == [conflict_resolution(table)]


def test_the_conflict_detail_shows_process_labels_and_keeps_originals_for_the_csv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """상세 표의 공정 칸은 화면에서만 표시명이다(`shown`) — 표 값 · CSV 는 원본으로 남는다."""
    monkeypatch.setattr(
        registration,
        "get_process_labels",
        lambda: ProcessLabels(version=1, labels={"P-Process": "표시 공정"}),
    )
    app = AppTest.from_string(REPORT_SCRIPT).run()

    assert not app.exception
    detail = note_table(_conflict_note(app), registration.CONFLICT_DETAIL_TITLE)
    assert detail["shown"] == {"공정": {"P-Process": "표시 공정"}}
    assert "P-Process" in table_frame(detail)["공정"].tolist()
    assert "표시 공정" not in table_frame(detail)["공정"].tolist()


def test_an_oversized_conflict_detail_stays_as_one_download_and_the_alert_says_where(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """상세가 커서 Alarm 줄에 싣지 못하면(`alert_table` 이 None) 탭 맨 아래 CSV 단추 하나로 남고
    글이 그 자리를 부른다 — 경고 · 표는 자리에 서지 않고 요약 표는 그대로 줄에 실린다."""
    monkeypatch.setattr(alerts, "TABLE_ROW_LIMIT", 1)
    script = REPORT_SCRIPT.replace('"RQ_PKG_PLAN", "RQ_YLD"]', '"RQ_PKG_PLAN"] * 2')
    assert script != REPORT_SCRIPT
    app = AppTest.from_string(script).run()

    assert not app.exception
    assert not app.warning and not app.dataframe
    note = _conflict_note(app)
    assert [table["title"] for table in note["tables"]] == [registration.CONFLICT_SUMMARY_TITLE]
    assert f"이 탭 「{registration.CONFLICT_CSV_LABEL}」" in note["full"]
    (download,) = app.get("download_button")
    assert download.proto.label == registration.CONFLICT_CSV_LABEL

    # 알림은 한 번이고 단추는 다음 등록까지 남는다.
    app.run()
    assert not flashed(app, "warning")
    assert len(app.get("download_button")) == 1


# 목록 결과를 세션에 심고 컴포넌트를 그리는 스크립트. 사내 패키지·DuckDB 없이 돈다.
STEP_SCRIPT = """
from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd
import streamlit as st

from capa_simulation.components import bigdataquery_registration as registration
from capa_simulation.io.company_bigdataquery_adapter import QueryWindow
from capa_simulation.services.bigdataquery_catalog_view import normalize_catalog

WINDOW = QueryWindow(start_date=date(2026, 9, 1), end_date=date(2026, 9, 8))
CATALOG = normalize_catalog(
    pd.DataFrame(
        {
            "simulation_name": ["알파 시뮬", "베타 시뮬"],
            "simulation_code": ["DEMO-A-001", "DEMO-B-002"],
            "plan_name": ["PLAN 알파", "PLAN 베타"],
            "plan_code": ["DEMO-PLAN-1", "DEMO-PLAN-2"],
            "regist_data": ["2026-09-02 03:04:05", "2026-09-01 01:02:03"],
        }
    )
)
st.session_state.setdefault(
    registration.CATALOG_RESULT_KEY,
    registration.CatalogResult(
        frame=CATALOG,
        window=WINDOW,
        queried_at=datetime(2026, 9, 8, 10, 0, 0),
        token="demo-token",
    ),
)
if st.session_state.get("__pick_row__") is not None:
    row = registration.catalog_row_at(CATALOG, int(st.session_state["__pick_row__"]))
    registration._apply_pick(registration.CatalogPick(row=row, window=WINDOW))
if st.session_state.get("__request_reset__"):
    st.session_state.pop("__request_reset__")
    registration._request_reset()
if st.session_state.get("__rerun__"):
    # 페이지의 다른 탭(시나리오 관리)이 등록 폼보다 먼저 `st.rerun()` 으로 끊은 회차.
    st.session_state["__rerun__"] = False
    st.rerun()

repository = SimpleNamespace(list_scenarios=lambda: [])
if not st.session_state.get("__skip__"):
    # 건너뛴 회차는 다른 화면을 다녀온 것이다 — 그 회차에 등록 폼이 그려지지 않는다.
    registration.render_bigdataquery_registration(repository, "demo.duckdb")
"""


def _run(**session: object) -> AppTest:
    app = AppTest.from_string(STEP_SCRIPT)
    for key, value in session.items():
        app.session_state[key] = value
    app.run()
    assert not app.exception
    return app


def test_both_steps_render_in_one_run(date_panels: dict[str, dict[str, Any]]) -> None:
    """탭을 오갈 때 값이 사라지지 않도록 두 폼을 항상 그린다."""
    app = _run()

    assert date_panels[panel_key(registration.CATALOG_START_DATE_KEY)]["label"] == "조회일"
    detail = date_panels[panel_key(registration.FORM_DETAIL_START_KEY)]
    assert detail["label"] == "상세 조회 기간"
    # 목록 조회는 폼 없이 단추 하나다 — 날짜 칸이 「적용」 때만 서버로 보낸다.
    assert app.button(key=registration.CATALOG_QUERY_BUTTON_KEY).label == "시뮬레이션 코드 조회"
    labels = {widget.label for widget in app.button}
    assert "시뮬레이션 코드 조회" in labels
    assert "DB 조회 후 시나리오 저장" in labels
    assert {"조회할 시뮬레이션 코드", "저장할 시나리오명"} <= {
        widget.label for widget in app.text_input
    }


def _save_button(app: AppTest) -> Any:
    return next(button for button in app.button if button.label == "DB 조회 후 시나리오 저장")


def test_an_unsavable_row_locks_the_save_button_with_its_reason_in_the_balloon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """원천 코드가 저장을 막으면 빨간 상자를 세우지 않고 꺼진 저장 단추 풍선이 까닭을 말한다 — 표
    「저장가능」 칸이 이미 값이다(설계 규칙 UI-INP-07 · UI-TXT-07)."""
    monkeypatch.setattr(registration, "is_bigdataquery_catalog_configured", lambda: True)
    monkeypatch.setattr(registration, "is_bigdataquery_adapter_configured", lambda: True)

    row = CatalogRow("DEMO SIM#9", "저장 불가 줄", "P9", "PLAN 9", "2026-09-02", False)
    pick = registration.CatalogPick(row=row, window=QueryWindow(date(2026, 9, 1), date(2026, 9, 8)))

    app = _run(**{registration.CATALOG_PICK_KEY: pick})

    assert not app.error
    locked = _save_button(app)
    assert locked.disabled and locked.help == UNSAVABLE_REASON

    savable = _save_button(_run(__pick_row__=0))
    assert not savable.disabled and not savable.help


@pytest.mark.parametrize(
    ("catalog_ready", "detail_ready"),
    [(False, False), (False, True), (True, False), (True, True)],
    ids=["둘 다 없음", "목록 없음", "상세 없음", "둘 다 있음"],
)
def test_the_buttons_a_missing_query_locks_say_why_in_their_balloons(
    monkeypatch: pytest.MonkeyPatch, catalog_ready: bool, detail_ready: bool
) -> None:
    """조회 SQL 이 없어 꺼진 단추는 잠긴 동안만 까닭 풍선을 단다(설계 규칙 UI-INP-07)."""
    monkeypatch.setattr(registration, "is_bigdataquery_catalog_configured", lambda: catalog_ready)
    monkeypatch.setattr(registration, "is_bigdataquery_adapter_configured", lambda: detail_ready)

    app = _run()

    query = app.button(key=registration.CATALOG_QUERY_BUTTON_KEY)
    assert query.disabled is (not catalog_ready)
    assert (query.help or None) == (None if catalog_ready else registration.CATALOG_LOCKED_HELP)
    save = _save_button(app)
    assert save.disabled is (not detail_ready)
    assert (save.help or None) == (None if detail_ready else registration.DETAIL_LOCKED_HELP)


@pytest.mark.parametrize("package_ready", [False, True], ids=["패키지 없음", "패키지 있음"])
def test_the_dropped_row_warning_follows_the_saved_notice_in_the_alert_popup(
    monkeypatch: pytest.MonkeyPatch, package_ready: bool
) -> None:
    """저장 뒤 회차에 성공 알림과 CS 빈 행 경고가 알림창에 차례로 뜨고(경고는 `FL-03` — 저장은
    끝났고 고칠 입력이 없어 단추 밑에 그리지 않는다, 설계 규칙 UI-NTF-03 · AMB-05 (나)), 한 번만
    보낸다.

    알림 칸 밑의 설정 띠는 값 줄이다 — 사내 패키지가 깔렸으면 「확인됨」, 없으면 「패키지 없음」
    표지와 그 내역을 든 상태 알림(`AD-04`)이다(설계 규칙 UI-NTF-02 — 자리에 상태 문장을 두지
    않는다). 이 PC 에 깔렸는지에 기대지 않고 두 경우를 다 본다(사내 PC 에는 깔려 있다)."""
    from capa_simulation.components.flash import FlashNote

    monkeypatch.setattr(registration, "is_bigdataquery_catalog_configured", lambda: True)
    monkeypatch.setattr(registration, "is_bigdataquery_adapter_configured", lambda: True)
    monkeypatch.setattr(registration, "is_bigdataquery_package_available", lambda: package_ready)
    saved = "「PSM W42」를 저장하고 r1을 올렸습니다."
    notice = (
        "CS 가 빈 행 3개(계획 1행 · 경로 2행)는 양산구분(양산·ER)을 정할 수 없어 빼고 저장했습니다."
    )
    app = _run(
        **{
            registration.REGISTRATION_FLASH_KEY: saved,
            registration.REGISTRATION_DROP_FLASH_KEY: FlashNote(
                "warning", notice, ":material/warning:", popup_only=True
            ),
        }
    )

    # 설정 띠의 점검 결론은 초록 상자가 아니라 값 줄(평문)이다 — 성공은 저장 알림 하나뿐.
    assert [item.value for item in successes(app)] == [saved]
    banner_lines = [
        item.value for item in app.caption if item.value == registration.BANNER_READY_LINE
    ]
    assert banner_lines == ([registration.BANNER_READY_LINE] if package_ready else [])
    assert not app.warning
    assert [(item.value, item.code) for item in flashed(app, "warning")] == [(notice, "FL-03")]
    assert not page_html(app)
    banner_note = active_state(app, "AD-04")
    if not package_ready:
        assert banner_note is not None and "bigdataquery 패키지가 없어" in banner_note["full"]
        assert any("패키지 없음" in caption.value for caption in app.caption)
        assert not any("bigdataquery 패키지가 없어" in caption.value for caption in app.caption)
    else:
        assert banner_note is None
    assert registration.REGISTRATION_DROP_FLASH_KEY not in app.session_state


def _drawn_in_order(node: object) -> list[tuple[str, str]]:
    """화면 차례대로 (요소 종류, 라벨 또는 글) — 블록(칸·폼)은 건너뛰고 그 안을 깊이 우선으로."""
    drawn: list[tuple[str, str]] = []
    for child in getattr(node, "children", {}).values():
        if hasattr(child, "children"):
            drawn.extend(_drawn_in_order(child))
            continue
        text = getattr(child, "label", None) or getattr(child, "value", None)
        drawn.append((type(child).__name__, text if isinstance(text, str) else ""))
    return drawn


def test_the_saved_notices_go_to_the_alert_popup_not_under_the_save_button(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """저장 결과(성공 · 대당 Capa 계산 멈춤 경고)는 알림창 · Alarm 으로만 간다 — 경고는 `FL-03` 이고
    저장 단추 밑 칸에는 그리지 않는다(설계 규칙 UI-NTF-03 · AMB-05 (나)). 그 칸에 그린 글이 없으니
    칸을 화면 안으로 옮기는 스크립트도 서지 않는다."""
    from capa_simulation.components.flash import FlashNote

    monkeypatch.setattr(registration, "is_bigdataquery_catalog_configured", lambda: True)
    monkeypatch.setattr(registration, "is_bigdataquery_adapter_configured", lambda: True)
    monkeypatch.setattr(registration, "is_bigdataquery_package_available", lambda: True)
    saved = "「PSM W44」를 저장하고 r1을 올렸습니다."
    stopped = "저장은 했지만 r1은 대당 Capa 계산이 멈춥니다 — RQ_RUN_RATE 의 효율이 비었습니다."
    app = _run(
        **{
            registration.REGISTRATION_FLASH_KEY: saved,
            registration.REGISTRATION_CAPACITY_FLASH_KEY: FlashNote(
                "warning", stopped, ":material/warning:", popup_only=True
            ),
        }
    )

    drawn = _drawn_in_order(app.main)
    assert ("Warning", stopped) not in drawn
    assert saved in [item.value for item in successes(app)]
    assert [(item.value, item.code) for item in flashed(app, "warning")] == [(stopped, "FL-03")]
    assert not page_html(app)

    app.run()

    assert saved not in [item.value for item in successes(app)]
    assert not flashed(app, "warning")


def test_a_refused_save_stands_in_the_same_slot_and_is_revealed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """저장하지 못한 까닭도 같은 칸(저장 단추 바로 아래)에 서고 그 칸을 화면 안으로 옮기는
    스크립트가 뒤따른다 — 성공과 실패가 같은 자리에서 답한다(`flash`)."""
    monkeypatch.setattr(registration, "is_bigdataquery_catalog_configured", lambda: True)
    monkeypatch.setattr(registration, "is_bigdataquery_adapter_configured", lambda: True)
    monkeypatch.setattr(registration, "is_bigdataquery_package_available", lambda: True)
    app = _run()
    assert not page_html(app)

    next(button for button in app.button if button.label == "DB 조회 후 시나리오 저장").click()
    app.run()

    assert not app.exception
    drawn = _drawn_in_order(app.main)
    button = drawn.index(("Button", "DB 조회 후 시나리오 저장"))
    kind, message = drawn[button + 1]
    assert kind == "Error" and message.startswith("상세 조회 기간을 지정하거나")
    (reveal,) = page_html(app)
    assert reveal.proto.unsafe_allow_javascript and "scrollIntoView" in reveal.proto.body


CATALOG_FAILURE_SCRIPT = """
import sys
from datetime import date
from types import SimpleNamespace

import streamlit as st

from capa_simulation.components import bigdataquery_registration as registration
from capa_simulation.io.company_bigdataquery_adapter import QueryWindow


class Error(Exception):
    pass


def get_data(**_kwargs):
    raise Error("Read timed out")


st.session_state.setdefault(registration.CATALOG_RESULT_KEY, "직전 목록")
saved = sys.modules.get("bigdataquery")
sys.modules["bigdataquery"] = SimpleNamespace(getData=get_data)
try:
    registration._run_catalog_query(
        QueryWindow(start_date=date(2026, 9, 21), end_date=date(2026, 10, 21))
    )
finally:
    if saved is None:
        sys.modules.pop("bigdataquery", None)
    else:
        sys.modules["bigdataquery"] = saved
"""


def test_a_package_failure_in_the_catalog_query_says_what_to_do_and_keeps_the_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """사내 패키지의 `Error` 는 화면이 잡는 예외 튜플 밖이다 — 감싸지 않으면 목록 조회가
    traceback 으로 멈췄다(사내 리뷰 202610200720 요청 2). 안내와 다시 할 길을 내고 직전 목록은
    둔다."""
    monkeypatch.delenv("CAPA_BDQ_USER_NAME", raising=False)
    app = AppTest.from_string(CATALOG_FAILURE_SCRIPT)
    app.run()

    assert not app.exception
    [error] = app.error
    assert "시간 초과" in error.value and "다시" in error.value
    assert app.session_state[registration.CATALOG_RESULT_KEY] == "직전 목록"


def test_a_failure_that_only_names_sql_is_not_told_as_a_rejected_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """문구에 `sql` 만 든 실패는 조회문 거절의 근거가 아니다 — 「다시 해도 같으니」 로 사용자를 돌려
    세우지 않고 다시 할 길을 낸다. 직전 목록은 그대로 둔다."""
    monkeypatch.delenv("CAPA_BDQ_USER_NAME", raising=False)
    app = AppTest.from_string(
        CATALOG_FAILURE_SCRIPT.replace("Read timed out", "Error executing SQL statement")
    )
    app.run()

    assert not app.exception
    [error] = app.error
    assert "(그 밖)" in error.value and "잠시 뒤 같은 조회를 다시" in error.value
    assert "다시 해도 같으니" not in error.value
    assert app.session_state[registration.CATALOG_RESULT_KEY] == "직전 목록"


IMPORT_FAILURE_SCRIPT = """
import sys
from datetime import date

import streamlit as st

from capa_simulation.components import bigdataquery_registration as registration
from capa_simulation.io.company_bigdataquery_adapter import QueryWindow

st.session_state.setdefault(registration.CATALOG_RESULT_KEY, "직전 목록")
saved = sys.modules.pop("bigdataquery", None)
sys.path.insert(0, PACKAGE_ROOT)
try:
    registration._run_catalog_query(
        QueryWindow(start_date=date(2026, 9, 21), end_date=date(2026, 10, 21))
    )
finally:
    sys.path.remove(PACKAGE_ROOT)
    sys.modules.pop("bigdataquery", None)
    if saved is not None:
        sys.modules["bigdataquery"] = saved
st.write("목록 조회 뒤")
"""


def test_a_package_that_fails_to_import_does_not_stop_the_catalog_query(
    tmp_path: Path,
) -> None:
    """패키지는 깔렸는데 불러오다 깨지면(DLL 등) `ImportError` 가 화면 예외 튜플 밖으로 새어
    목록 조회가 traceback 으로 멈췄다. 원인을 오류 칸에 적고 직전 목록과 뒤 화면은 둔다."""
    package = tmp_path / "bigdataquery"
    package.mkdir()
    (package / "__init__.py").write_text(
        'raise ImportError("DLL load failed while importing _jpype")\n', encoding="utf-8"
    )
    script = IMPORT_FAILURE_SCRIPT.replace("PACKAGE_ROOT", repr(str(tmp_path)))
    app = AppTest.from_string(script)
    app.run()

    assert not app.exception
    [error] = app.error
    assert "불러오지 못했습니다" in error.value and "DLL load failed" in error.value
    assert app.session_state[registration.CATALOG_RESULT_KEY] == "직전 목록"
    assert any(block.value == "목록 조회 뒤" for block in app.markdown)


def test_the_catalog_search_controls_share_one_line_above_the_result_line_and_the_table() -> None:
    """조회일 · 조회 단추 · 검색 · 표시 범위는 표 위 한 줄이고, 조회 결과 줄은 그 아래 표 바로 위다
    (설계 규칙 UI-LAY-11)."""
    app = _run()

    row = next(
        block
        for block in app.main.children.values()
        if getattr(getattr(block, "proto", None), "flex_container", None) is not None
        and block.proto.flex_container.direction == 2
    )
    labels = [text for _, text in _drawn_in_order(row)]
    assert labels == ["시뮬레이션 코드 조회", "검색", "표시 범위"]

    drawn = _drawn_in_order(app.main)
    scope = next(at for at, (_, text) in enumerate(drawn) if text == "표시 범위")
    summary = next(at for at, (_, text) in enumerate(drawn) if "코드·PLAN 기준" in text)
    table = next(at for at, (kind, _) in enumerate(drawn) if kind == "Dataframe")
    assert scope < summary < table


def test_catalog_list_is_drawn_with_a_fixed_height_for_scrolling() -> None:
    app = _run()

    values = [frame.value for frame in app.dataframe]
    assert any("시뮬레이션 코드" in getattr(value, "columns", []) for value in values)
    assert registration.CATALOG_LIST_HEIGHT_PX == 390


def test_selecting_a_row_prefills_the_registration_form() -> None:
    app = _run(__pick_row__=0)

    values = {widget.label: widget.value for widget in app.text_input}
    assert values["조회할 시뮬레이션 코드"] == "DEMO-A-001"
    assert values["원천 시뮬레이션명"] == "알파 시뮬"
    assert values["저장할 시나리오명"] == "알파 시뮬 (DEMO-A-001)"
    assert values["원천 DB 등록시점 (선택)"] == "2026-09-02 03:04:05"
    memo = app.text_area[0].value
    assert memo is not None and "PLAN 알파(DEMO-PLAN-1)" in memo


def test_reselecting_the_same_row_keeps_user_edits() -> None:
    """같은 행이 계속 선택돼 있을 뿐인 런에서 사용자가 고친 값을 덮지 않는다."""
    app = _run(__pick_row__=0)
    app.text_input(key=registration.FORM_SCENARIO_NAME_KEY).set_value("내가 고친 이름").run()

    assert not app.exception
    assert app.session_state[registration.FORM_SCENARIO_NAME_KEY] == "내가 고친 이름"


def test_reset_clears_the_pick_and_the_form_on_the_next_run() -> None:
    """이미 만든 위젯 key 는 같은 런에서 지울 수 없어 다음 런 첫 줄에서 비운다."""
    app = _run(__pick_row__=0)
    app.session_state["__pick_row__"] = None
    app.session_state["__request_reset__"] = True
    app.run()

    assert not app.exception
    assert app.session_state[registration.FORM_CODE_KEY] == ""
    assert registration.CATALOG_PICK_KEY not in app.session_state
    assert app.session_state[registration.FORM_DETAIL_START_KEY] is None
    assert app.session_state[registration.FORM_DETAIL_END_KEY] is None


@pytest.mark.parametrize("interruption", ["__skip__", "__rerun__"])
def test_a_picked_form_survives_a_run_that_did_not_draw_it(interruption: str) -> None:
    """목록 선택은 위젯이 아닌 칸이라 남는데, 폼 글자 칸은 그리지 않은 회차에 Streamlit 이 버린다.

    다른 화면을 다녀오거나 시나리오 관리 탭의 `st.rerun()` 이 등록 폼보다 먼저 끊으면 행은 선택된
    채 코드·이름만 비어 저장이 막혔고, 같은 행이 다시 선택될 뿐이라 다시 채워지지도 않았다.
    사용자가 넓힌 상세 조회 기간(세션에 남는 칸)은 기본값으로 되돌리지 않는다.
    """
    app = _run(__pick_row__=0)
    # 이제부터 폼을 다시 채울 길은 목록 표가 같은 행을 다시 고르는 `selection_default` 하나다.
    app.session_state["__pick_row__"] = None
    app.session_state[registration.FORM_DETAIL_END_KEY] = date(2026, 9, 20)
    app.run()
    app.session_state[interruption] = True
    app.run()
    app.session_state[interruption] = False
    app.run()

    assert not app.exception
    values = {widget.label: widget.value for widget in app.text_input}
    assert values["조회할 시뮬레이션 코드"] == "DEMO-A-001"
    assert values["원천 시뮬레이션명"] == "알파 시뮬"
    assert values["저장할 시나리오명"] == "알파 시뮬 (DEMO-A-001)"
    assert values["원천 DB 등록시점 (선택)"] == "2026-09-02 03:04:05"
    memo = app.text_area[0].value
    assert memo is not None and "PLAN 알파(DEMO-PLAN-1)" in memo
    assert app.session_state[registration.FORM_DETAIL_START_KEY] == date(2026, 8, 26)
    assert app.session_state[registration.FORM_DETAIL_END_KEY] == date(2026, 9, 20)


def test_a_reset_form_stays_empty_after_a_run_that_did_not_draw_it() -> None:
    """초기화한 폼은 다른 화면을 다녀와도 앞 선택의 값으로 되살아나지 않는다."""
    app = _run(__pick_row__=0)
    app.session_state["__pick_row__"] = None
    app.session_state["__request_reset__"] = True
    app.run()
    app.session_state["__skip__"] = True
    app.run()
    app.session_state["__skip__"] = False
    app.run()

    assert not app.exception
    assert app.text_input(key=registration.FORM_CODE_KEY).value == ""
    assert app.text_input(key=registration.FORM_SCENARIO_NAME_KEY).value == ""
    assert registration.CATALOG_PICK_KEY not in app.session_state


def test_picking_a_code_fills_the_detail_window_around_its_registration_date() -> None:
    """고른 코드의 원천 등록일 7일 전 ~ 3일 뒤로 두 칸을 채운다(2026-09-29 사용자 결정 A+B)."""
    app = _run(__pick_row__=0)

    assert app.session_state[registration.FORM_DETAIL_START_KEY] == date(2026, 8, 26)
    assert app.session_state[registration.FORM_DETAIL_END_KEY] == date(2026, 9, 5)
    captions = " ".join(item.value for item in app.caption)
    assert "**고른 코드의 원천 등록일** · 2026-09-02" in captions


def test_a_widened_detail_window_survives_the_same_pick() -> None:
    """등록 뒤에도 계속 수정된 코드는 사용자가 넓힌다.

    같은 행이 선택된 채 도는 다음 런이 넓힌 기간을 기본값으로 되돌리지 않는다.
    """
    app = _run(__pick_row__=0)
    app.session_state[registration.FORM_DETAIL_END_KEY] = date(2026, 9, 20)
    app.run()

    assert not app.exception
    assert app.session_state[registration.FORM_DETAIL_END_KEY] == date(2026, 9, 20)


@pytest.mark.parametrize(
    "event",
    [
        None,
        {},
        {"selection": None},
        {"selection": {"rows": []}},
        {"selection": {"rows": "0"}},
        {"selection": {"rows": [True]}},
        {"selection": {"rows": ["0"]}},
    ],
)
def test_first_selected_row_ignores_broken_events(event: object) -> None:
    assert registration.first_selected_row(event) is None


def test_first_selected_row_reads_the_first_position() -> None:
    assert registration.first_selected_row({"selection": {"rows": [3, 5]}}) == 3


def test_catalog_list_key_changes_with_the_visible_rows() -> None:
    """key 를 고정하면 필터로 행 수가 달라져도 옛 위치가 돌아와 다른 행이 선택된다."""
    base = registration.catalog_list_key("token", 0, "", "전체")

    assert base != registration.catalog_list_key("token", 1, "", "전체")
    assert base != registration.catalog_list_key("token", 0, "알파", "전체")
    assert base != registration.catalog_list_key("token", 0, "", "미등록만")
    assert base != registration.catalog_list_key("other", 0, "", "전체")
    assert base == registration.catalog_list_key("token", 0, "", "전체")


OLD_CODE_SCRIPT = (
    STEP_SCRIPT.replace(
        '"regist_data": ["2026-09-02 03:04:05", "2026-09-01 01:02:03"],',
        '"regist_data": ["2025-11-02 03:04:05", "2026-09-01 01:02:03"],',
    )
    .replace(
        """        token="demo-token",
    ),
)""",
        """        token="demo-token",
        first_registered={("DEMO-A-001", "DEMO-PLAN-1"): date(2025, 10, 1)},
    ),
)""",
    )
    .replace(
        "registration._apply_pick(registration.CatalogPick(row=row, window=WINDOW))",
        "registration._apply_pick(registration.CatalogPick(row=row, window=WINDOW, "
        "first_registered_on=date(2025, 10, 1)))",
    )
)


def test_an_old_code_seen_on_several_days_gets_a_window_across_all_of_them() -> None:
    """목록 기간이 최근 일주일이어도 상세 기본 창은 그 코드의 등록일에 맞춰진다.

    목록 정리는 최신 행(2025-11-02)만 남기고 가장 이른 등록일(2025-10-01)은 따로 들고 온다.
    기본 창이 그 사이를 자르면 이미 목록에 보인 적재분이 오류 없이 빠진다.
    """
    app = AppTest.from_string(OLD_CODE_SCRIPT)
    # 목록은 최신 등록순이라 2025-11-02 에 등록된 DEMO-A 가 둘째 행이다.
    app.session_state["__pick_row__"] = 1
    app.run()
    assert not app.exception

    assert app.session_state[registration.FORM_CODE_KEY] == "DEMO-A-001"
    assert app.session_state[registration.FORM_DETAIL_START_KEY] == date(2025, 9, 24)
    assert app.session_state[registration.FORM_DETAIL_END_KEY] == date(2025, 11, 5)
    captions = " ".join(item.value for item in app.caption)
    assert "**고른 코드의 원천 등록일** · 2025-10-01 ~ 2025-11-02" in captions
    # 메모의 상세 조회기간은 저장할 때 실제로 조회한 기간으로 붙는다(칸을 고칠 수 있어서).
    memo = app.text_area[0].value
    assert memo is not None and "상세 조회기간" not in memo


SUBMIT_SCRIPT = """
from datetime import date, datetime

import streamlit as st

from capa_simulation.components import bigdataquery_registration as registration

registered = st.session_state.get("__registered_at__")
window = registration._submitted_detail_window(
    registered, simulation_code=st.session_state.get("__code__", "")
)
st.session_state["__window__"] = None if window is None else window.label()
"""


@pytest.mark.parametrize(
    ("start", "end", "registered_at", "expected", "error"),
    [
        # 두 칸이 우선이다 — 등록 뒤 계속 수정된 코드는 사용자가 넓힌 기간 그대로 조회한다.
        (date(2025, 1, 1), date(2025, 12, 31), None, "2025-01-01 ~ 2025-12-31", None),
        # 둘 다 비었으면 원천 DB 등록시점 7일 전 ~ 3일 뒤(코드를 직접 적은 경우).
        (None, None, "2025-06-10", "2025-06-03 ~ 2025-06-13", None),
        # 기간을 모르는 채로 넓은 기본 창을 조용히 쓰지 않는다.
        (None, None, None, None, "원천 DB 등록시점"),
        (date(2025, 1, 1), None, "2025-06-10", None, "둘 다 비우세요"),
        (date(2025, 2, 1), date(2025, 1, 1), None, None, "늦을 수 없습니다"),
    ],
)
def test_the_submitted_detail_window(
    start: date | None,
    end: date | None,
    registered_at: str | None,
    expected: str | None,
    error: str | None,
) -> None:
    from datetime import datetime

    app = AppTest.from_string(SUBMIT_SCRIPT)
    app.session_state[registration.FORM_DETAIL_START_KEY] = start
    app.session_state[registration.FORM_DETAIL_END_KEY] = end
    app.session_state["__registered_at__"] = (
        None if registered_at is None else datetime.fromisoformat(registered_at)
    )
    app.run()

    assert not app.exception
    assert app.session_state["__window__"] == expected
    errors = " ".join(item.value for item in app.error)
    if error is None:
        assert not errors
    else:
        assert error in errors


PICKED_A = registration.PickedFields(
    code="DEMO-A-001",
    start=date(2026, 8, 26),
    end=date(2026, 9, 5),
    registered_at="2026-09-02 03:04:05",
)


@pytest.mark.parametrize(
    ("code", "start", "end", "registered_text", "blocked"),
    [
        # 목록에서 고른 코드 그대로면 그 창을 쓴다.
        ("DEMO-A-001", date(2026, 8, 26), date(2026, 9, 5), "2026-09-02 03:04:05", None),
        # 코드만 바꿔 적고 날짜는 손대지 않았다 — 남의 등록일 창이라 막는다.
        ("DEMO-Z-999", date(2026, 8, 26), date(2026, 9, 5), "", "원천 등록일로 채워진"),
        # 코드를 바꾸고 날짜도 고쳤다 — 사용자가 정한 기간을 믿는다.
        ("DEMO-Z-999", date(2026, 8, 26), date(2026, 9, 20), "", None),
        # 날짜를 고쳤어도 등록시점이 남의 값 그대로면 막는다 — 저장 메타데이터가 된다.
        ("DEMO-Z-999", date(2026, 8, 26), date(2026, 9, 20), "2026-09-02 03:04:05", "등록시점"),
        # 안내대로 두 칸을 비웠는데 등록시점이 남의 값이면, 같은 남의 창이 다시 만들어진다 — 막는다.
        ("DEMO-Z-999", None, None, "2026-09-02 03:04:05", "등록시점"),
        # 두 칸을 비우고 이 코드의 등록시점을 적으면 그 기준으로 조회한다.
        ("DEMO-Z-999", None, None, "2026-06-10 00:00:00", None),
    ],
)
def test_a_picked_window_is_not_reused_silently_for_another_code(
    code: str,
    start: date | None,
    end: date | None,
    registered_text: str,
    blocked: str | None,
) -> None:
    """목록에서 고른 뒤 코드 칸만 고쳐 적으면 앞 코드의 등록일 창으로 오류 없이 조회됐다.

    2026-09-29 리뷰 — 손대지 않은 남의 기본 창만 막고, 사용자가 고친 기간은 믿는다.
    """
    from datetime import datetime

    app = AppTest.from_string(SUBMIT_SCRIPT)
    app.session_state[registration.CATALOG_FORM_PICKED_WINDOW_KEY] = PICKED_A
    app.session_state[registration.FORM_DETAIL_START_KEY] = start
    app.session_state[registration.FORM_DETAIL_END_KEY] = end
    app.session_state[registration.FORM_REGISTERED_AT_KEY] = registered_text
    app.session_state["__registered_at__"] = (
        datetime.fromisoformat(registered_text) if registered_text else None
    )
    app.session_state["__code__"] = code
    app.run()

    assert not app.exception
    errors = " ".join(item.value for item in app.error)
    if blocked is None:
        assert not errors
        assert app.session_state["__window__"] is not None
    else:
        assert "다른 코드" in errors and blocked in errors
        assert app.session_state["__window__"] is None


MULTI_PLAN_SCRIPT = STEP_SCRIPT.replace(
    "registration._apply_pick(registration.CatalogPick(row=row, window=WINDOW))",
    "registration._apply_pick(registration.CatalogPick(row=row, window=WINDOW, "
    "first_registered_on=date(2026, 7, 1), last_registered_on=date(2026, 9, 10)))",
)


def test_a_pick_covers_every_plan_row_of_the_same_code() -> None:
    """고른 줄의 등록일이 아니라 그 코드의 모든 PLAN 줄 등록일 범위로 기본 창을 채운다."""
    app = AppTest.from_string(MULTI_PLAN_SCRIPT)
    app.session_state["__pick_row__"] = 0
    app.run()

    assert not app.exception
    assert app.session_state[registration.FORM_DETAIL_START_KEY] == date(2026, 6, 24)
    assert app.session_state[registration.FORM_DETAIL_END_KEY] == date(2026, 9, 13)
    assert app.session_state[registration.CATALOG_FORM_PICKED_WINDOW_KEY] == (
        registration.PickedFields(
            code="DEMO-A-001",
            start=date(2026, 6, 24),
            end=date(2026, 9, 13),
            registered_at="2026-09-02 03:04:05",
        )
    )


def test_the_detail_dates_stay_clearable_after_a_pick(
    date_panels: dict[str, dict[str, Any]],
) -> None:
    """고른 뒤에도 기간을 비울 수 있어야 등록시점 규칙으로 돌아간다 — 칸이 「비움」 을 받고 오늘
    뒤는 고르지 못한다."""
    app = _run(__pick_row__=0)

    assert app.session_state[registration.FORM_DETAIL_START_KEY] == date(2026, 8, 26)
    assert app.session_state[registration.FORM_DETAIL_END_KEY] == date(2026, 9, 5)
    sent = date_panels[panel_key(registration.FORM_DETAIL_START_KEY)]
    assert (sent["start"], sent["end"]) == ("2026-08-26", "2026-09-05")
    assert sent["clearable"] is True
    assert sent["maxDay"] == date.today().isoformat()


def test_the_selection_builds_the_span_from_every_plan_row_of_the_whole_catalog() -> None:
    """목록 선택은 정리된 목록 전체의 같은 코드 줄로 등록일 범위를 낸다.

    검색으로 좁힌 행(`visible`)으로 구하면 필터가 범위를 줄인다.
    """
    from datetime import datetime

    import pandas as pd

    from capa_simulation.io.company_bigdataquery_adapter import QueryWindow
    from capa_simulation.services.bigdataquery_catalog_view import (
        catalog_row_at,
        filter_catalog,
        normalize_catalog,
    )

    catalog = normalize_catalog(
        pd.DataFrame(
            {
                "simulation_name": ["알파", "알파", "베타"],
                "simulation_code": ["DEMO-A-001", "DEMO-A-001", "DEMO-B-002"],
                "plan_name": ["PLAN 하나", "PLAN 둘", "PLAN 셋"],
                "plan_code": ["DEMO-PLAN-1", "DEMO-PLAN-2", "DEMO-PLAN-3"],
                "regist_data": [
                    "2026-09-02 03:04:05",
                    "2026-07-15 00:00:00",
                    "2026-09-01 01:02:03",
                ],
            }
        )
    )
    result = registration.CatalogResult(
        frame=catalog,
        window=QueryWindow(start_date=date(2026, 6, 1), end_date=date(2026, 9, 8)),
        queried_at=datetime(2026, 9, 8, 10, 0, 0),
        token="demo",
        first_registered={("DEMO-A-001", "DEMO-PLAN-2"): date(2026, 7, 1)},
    )
    visible = filter_catalog(catalog, keyword="하나", scope="전체", registered_codes=frozenset())
    row = catalog_row_at(visible, 0)
    assert row is not None and row.plan_code == "DEMO-PLAN-1"

    pick = registration.catalog_pick(result, row)

    assert (pick.first_registered_on, pick.last_registered_on) == (
        date(2026, 7, 1),
        date(2026, 9, 2),
    )


SAVE_SCRIPT = """
from pathlib import Path

import pandas as pd
import streamlit as st

from capa_simulation.components import bigdataquery_registration as registration
from capa_simulation.io.core_data_source import CoreDataBatch
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset


class FakeProvider:
    def __init__(self, *, simulation_name, source_registered_at, window):
        st.session_state["__window__"] = window.label()
        self._name = simulation_name
        self._registered_at = source_registered_at

    def fetch(self, simulation_code):
        frame = build_builtin_seed_dataset().source_data.copy()
        # 시험이 고른 행의 CS 를 비운다(행 번호 → 넣을 값). 사내 원천에 CS 가 빈 행이 온 꼴.
        for index, value in st.session_state.get("__blank_cs__", {}).items():
            frame.loc[int(index), "CS"] = value
        # 시험이 고른 (행 번호, 컬럼) 칸을 비운다 — 대당 Capa 가 멈추는 원천의 꼴.
        for index, column in st.session_state.get("__blank_cells__", []):
            frame.loc[int(index), column] = None
        # 시험이 고른 행을 생산수량만 바꿔 한 번 더 넣는다 — 업무 키 값 충돌의 꼴.
        for index in st.session_state.get("__duplicate_rows__", []):
            extra = frame.loc[[int(index)]].copy()
            extra["생산수량"] = pd.to_numeric(extra["생산수량"]) + 1
            frame = pd.concat([frame, extra], ignore_index=True)
        return CoreDataBatch(
            simulation_code=simulation_code,
            simulation_name=self._name,
            source_type="BIGDATAQUERY",
            frame=frame,
            source_registered_at=self._registered_at,
        )


database_path = st.session_state["__database__"]
if not st.session_state.get("__saved__"):
    st.session_state["__saved__"] = True
    original = registration.BigDataQueryCoreDataProvider
    registration.BigDataQueryCoreDataProvider = FakeProvider
    try:
        registration._save_scenario(
            DuckDBScenarioRepository(Path(database_path)),
            database_path,
            existing_names=frozenset(),
        )
    finally:
        registration.BigDataQueryCoreDataProvider = original
"""


def test_the_form_saves_through_the_session_free_registration_path(tmp_path: Path) -> None:
    """화면 저장은 세션 없는 등록 경로(`scenario_registration`)를 지나도 예전과 같은 것을 남긴다.

    폼의 이름·리비전명·등록시점, 메모 뒤의 상세 조회기간, 세션의 레거시 확보·경고 값, 저장 뒤
    활성화와 안내 한 줄이다. 공식버전 자동 갱신이 같은 길로 저장한다.
    """
    from datetime import datetime

    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.scenario_preset_state import SECURE_THRESHOLD_KEY, WARNING_THRESHOLD_KEY
    from capa_simulation.services.builtin_seed import load_builtin_display_order

    database = tmp_path / "registration.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    repository.initialize_global_display_order(load_builtin_display_order())

    app = AppTest.from_string(SAVE_SCRIPT, default_timeout=60)
    app.session_state["__database__"] = str(database)
    app.session_state[registration.FORM_CODE_KEY] = "SIM-W41"
    app.session_state[registration.FORM_SOURCE_NAME_KEY] = "PSM W41"
    app.session_state[registration.FORM_SCENARIO_NAME_KEY] = "PSM W41 (SIM-W41)"
    app.session_state[registration.FORM_REVISION_NAME_KEY] = "초기 리비전"
    app.session_state[registration.FORM_REGISTERED_AT_KEY] = "2026-10-12 09:00:00"
    app.session_state[registration.FORM_NOTE_KEY] = "원천 PLAN 메모"
    app.session_state[registration.FORM_DETAIL_START_KEY] = date(2026, 10, 5)
    app.session_state[registration.FORM_DETAIL_END_KEY] = date(2026, 10, 15)
    app.session_state[SECURE_THRESHOLD_KEY] = 110.0
    app.session_state[WARNING_THRESHOLD_KEY] = 100.0
    app.run()

    assert not app.exception
    assert not place_errors(app)
    assert app.session_state["__window__"] == "2026-10-05 ~ 2026-10-15"
    assert "올렸습니다" in app.session_state[registration.REGISTRATION_FLASH_KEY]
    [scenario] = repository.list_scenarios()
    assert (scenario.scenario_name, scenario.source_simulation_code) == (
        "PSM W41 (SIM-W41)",
        "SIM-W41",
    )
    assert scenario.source_registered_at == datetime(2026, 10, 12, 9, 0)
    snapshot = repository.load_revision(scenario.active_revision_id)
    assert snapshot.revision.revision_name == "초기 리비전"
    assert snapshot.revision.note == "원천 PLAN 메모 · 상세 조회기간 2026-10-05 ~ 2026-10-15"
    assert (snapshot.preset.secure_threshold, snapshot.preset.warning_threshold) == (1.10, 1.00)
    assert snapshot.preset.included_processes == (
        "DEMO_Chip_Attach",
        "DEMO_Final_Test",
        "DEMO_Wafer_Inspect",
    )
    # CS 가 빈 행이 없으면 경고도 메모 조각도 없다. 대당 Capa 도 서므로 그 경고도 없다.
    assert registration.REGISTRATION_DROP_FLASH_KEY not in app.session_state
    assert registration.REGISTRATION_CAPACITY_FLASH_KEY not in app.session_state


def _registration_app(
    database: Path, blank_cs: dict[int, str | None], *, draft: ListDraft | None = None
) -> AppTest:
    """폼 값을 채우고 원천의 고른 행 CS 를 비운 채 화면 저장 경로를 한 번 돌린다."""
    app = AppTest.from_string(SAVE_SCRIPT, default_timeout=60)
    app.session_state["__database__"] = str(database)
    app.session_state["__blank_cs__"] = blank_cs
    if draft is not None:
        app.session_state[DRAFT_KEY] = draft
    app.session_state[registration.FORM_CODE_KEY] = "SIM-W42"
    app.session_state[registration.FORM_SOURCE_NAME_KEY] = "PSM W42"
    app.session_state[registration.FORM_SCENARIO_NAME_KEY] = "PSM W42 (SIM-W42)"
    app.session_state[registration.FORM_REVISION_NAME_KEY] = "초기 리비전"
    app.session_state[registration.FORM_REGISTERED_AT_KEY] = "2026-10-26 09:00:00"
    app.session_state[registration.FORM_NOTE_KEY] = "원천 PLAN 메모"
    app.session_state[registration.FORM_DETAIL_START_KEY] = date(2026, 10, 19)
    app.session_state[registration.FORM_DETAIL_END_KEY] = date(2026, 10, 27)
    return app.run()


def _registration_database(tmp_path: Path) -> Path:
    """표시순서까지 채운 빈 저장소. 등록은 공용 표시순서를 읽는다."""
    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.services.builtin_seed import load_builtin_display_order

    database = tmp_path / "registration.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    repository.initialize_global_display_order(load_builtin_display_order())
    return database


def test_a_registration_made_here_moves_the_base_of_the_unsaved_list_order(tmp_path: Path) -> None:
    """목록 관리에 미저장 순서를 둔 채 이 세션이 등록한 시나리오는 「다른 곳에서」 가 아니다 — 본
    차례를 그 줄이 든 차례로 옮긴다."""
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    database = _registration_database(tmp_path)
    app = _registration_app(database, {}, draft=ListDraft(order=(), order_base=()))
    assert not app.exception

    [scenario] = DuckDBScenarioRepository(database).list_scenarios()
    assert app.session_state[DRAFT_KEY].order_base == (scenario.scenario_id,)


def test_rows_with_a_blank_cs_are_dropped_and_the_registration_still_saves(
    tmp_path: Path,
) -> None:
    """사내 원천에 CS 가 빈 행이 와서 양산구분이 비고 저장이 막혔다(2026-10-27 사용자 결정).

    그 행은 표에서 빼고 저장한다. 저장 알림 밑에 뺀 행 수(계획 행 수)를 경고로 띄우고, 같은 수를
    리비전 메모 끝에 남긴다. 원천 스냅샷에는 받은 96행이 그대로 남는다(합성 시드 — 샘플 관측).
    """
    from capa_simulation.components.flash import FlashNote
    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.services.builtin_seed import build_builtin_seed_dataset

    database = _registration_database(tmp_path)
    source = build_builtin_seed_dataset().source_data
    plans = source.index[source["계획기초정보여부"].eq("Y")]
    routes = source.index[source["계획기초정보여부"].eq("N")]
    blank = {int(plans[-1]): None, int(routes[-1]): "   ", int(routes[-2]): ""}

    app = _registration_app(database, blank)

    assert not app.exception
    assert not place_errors(app)
    assert "올렸습니다" in app.session_state[registration.REGISTRATION_FLASH_KEY]
    note = FlashNote(*app.session_state[registration.REGISTRATION_DROP_FLASH_KEY])
    # 저장은 끝났고 고칠 입력이 없다 — 알림창 · Alarm 에만(설계 규칙 UI-NTF-03).
    assert note.kind == "warning" and note.popup_only
    assert note.message.startswith(
        "CS 가 빈 행 3개(계획 1행 · 경로 2행)는 양산구분(양산·ER)을 정할 수 없어 빼고 저장했습니다."
    )
    repository = DuckDBScenarioRepository(database)
    [scenario] = repository.list_scenarios()
    snapshot = repository.load_revision(scenario.active_revision_id)
    assert snapshot.revision.note == (
        "원천 PLAN 메모 · 상세 조회기간 2026-10-19 ~ 2026-10-27 · "
        "CS 빈 행 3개(계획 1행 · 경로 2행) 뺌"
    )
    assert len(snapshot.tables["RQ_PKG_PLAN"]) == len(plans) - 1
    assert snapshot.tables["RQ_PKG_PLAN"]["양산구분"].notna().all()
    assert snapshot.tables["RQ_REQB"]["양산구분"].notna().all()
    assert repository.load_source_row_count(scenario.scenario_id) == len(source)


def test_a_registration_whose_capacity_stops_still_saves_and_says_how_to_fix_it(
    tmp_path: Path,
) -> None:
    """저장 전에 대당 Capa 를 한 번 돌려 보고, 멈추면 저장은 하고 경고 띠로 알린다(2026-11-01 사용자
    결정 A1 「알리기만」). 사내 S27 은 등록은 됐는데 계산할 때 처음 멈췄다(리뷰 202610271800 발견
    1)."""
    from capa_simulation.components.flash import FlashNote
    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.services.builtin_seed import build_builtin_seed_dataset

    database = _registration_database(tmp_path)
    source = build_builtin_seed_dataset().source_data
    process = "DEMO_Wafer_Inspect"
    month = int(source.loc[source["공정"].eq(process), "생산계획년월"].min())
    rows = source.index[source["공정"].eq(process) & source["생산계획년월"].eq(month)]

    app = AppTest.from_string(SAVE_SCRIPT, default_timeout=60)
    app.session_state["__database__"] = str(database)
    app.session_state["__blank_cells__"] = [(int(row), "CAPA_RUN_RATE") for row in rows]
    app.session_state[registration.FORM_CODE_KEY] = "SIM-W44"
    app.session_state[registration.FORM_SOURCE_NAME_KEY] = "PSM W44"
    app.session_state[registration.FORM_SCENARIO_NAME_KEY] = "PSM W44 (SIM-W44)"
    app.session_state[registration.FORM_REVISION_NAME_KEY] = "초기 리비전"
    app.session_state[registration.FORM_REGISTERED_AT_KEY] = "2026-10-30 09:00:00"
    app.session_state[registration.FORM_NOTE_KEY] = ""
    app.session_state[registration.FORM_DETAIL_START_KEY] = date(2026, 10, 23)
    app.session_state[registration.FORM_DETAIL_END_KEY] = date(2026, 11, 1)
    app.run()

    assert not app.exception
    assert not place_errors(app)
    assert "올렸습니다" in app.session_state[registration.REGISTRATION_FLASH_KEY]
    warning = FlashNote(*app.session_state[registration.REGISTRATION_CAPACITY_FLASH_KEY])
    assert warning.kind == "warning" and warning.popup_only
    assert warning.message.startswith(
        "저장은 했지만 r1은 대당 Capa 계산이 멈춥니다 — RQ_RUN_RATE의 "
    )
    assert "기준 정보 화면 「효율」 표에서" in warning.message
    assert "r2부터 계산이 섭니다" in warning.message
    repository = DuckDBScenarioRepository(database)
    [scenario] = repository.list_scenarios()
    snapshot = repository.load_revision(scenario.active_revision_id)
    assert (snapshot.revision.note or "").startswith(
        "상세 조회기간 2026-10-23 ~ 2026-11-01 · 대당 Capa 계산 멈춤(RQ_RUN_RATE 빈 값 키 "
    )


def test_a_saved_registration_with_conflicting_keys_queues_the_report_after_the_saved_notice(
    tmp_path: Path,
) -> None:
    """화면 저장 길 끝까지 — 업무 키 값이 갈린 원천을 저장하면 보고가 성공 알림 바로 뒤 칸에 담기고
    (`REGISTRATION_FLASH_KEYS` 차례) 자리에는 아무것도 그리지 않는다. 합성 시드의 계획 행 하나를
    생산수량만 바꿔 한 번 더 넣는다."""
    from capa_simulation.components.flash import FlashNote
    from capa_simulation.services.builtin_seed import build_builtin_seed_dataset

    source = build_builtin_seed_dataset().source_data
    plan = int(source.index[source["계획기초정보여부"].eq("Y")][0])
    app = AppTest.from_string(SAVE_SCRIPT, default_timeout=60)
    app.session_state["__database__"] = str(_registration_database(tmp_path))
    app.session_state["__duplicate_rows__"] = [plan]
    app.session_state[registration.FORM_CODE_KEY] = "SIM-W45"
    app.session_state[registration.FORM_SOURCE_NAME_KEY] = "PSM W45"
    app.session_state[registration.FORM_SCENARIO_NAME_KEY] = "PSM W45 (SIM-W45)"
    app.session_state[registration.FORM_REVISION_NAME_KEY] = "초기 리비전"
    app.session_state[registration.FORM_REGISTERED_AT_KEY] = "2026-11-05 09:00:00"
    app.session_state[registration.FORM_DETAIL_START_KEY] = date(2026, 10, 29)
    app.session_state[registration.FORM_DETAIL_END_KEY] = date(2026, 11, 5)
    app.run()

    assert not app.exception
    assert not place_errors(app)
    assert not app.warning and not app.dataframe
    assert "올렸습니다" in app.session_state[registration.REGISTRATION_FLASH_KEY]
    keys = registration.REGISTRATION_FLASH_KEYS
    assert keys.index(registration.REGISTRATION_CONFLICT_FLASH_KEY) == 1
    note = FlashNote(*app.session_state[registration.REGISTRATION_CONFLICT_FLASH_KEY])
    assert (note.kind, note.alert, note.popup_only) == ("warning", "SC-04", True)
    assert [table["title"] for table in note.tables] == [
        registration.CONFLICT_SUMMARY_TITLE,
        registration.CONFLICT_DETAIL_TITLE,
    ]
    detail = table_frame(note.tables[1])
    assert set(detail["RQ테이블"]) == {"RQ_PKG_PLAN"}
    assert set(detail["충돌컬럼"]) == {"생산수량"}


def test_a_failed_save_queues_no_conflict_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """저장하지 못한 등록에는 「등록했습니다」 보고를 내지 않는다 — 원천을 받은 뒤 저장이 실패해도
    곁 오류만 선다."""
    from capa_simulation.services.builtin_seed import build_builtin_seed_dataset

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise ValueError("저장을 막았습니다.")

    monkeypatch.setattr(registration, "save_bigdataquery_scenario", refuse)
    source = build_builtin_seed_dataset().source_data
    plan = int(source.index[source["계획기초정보여부"].eq("Y")][0])
    app = AppTest.from_string(SAVE_SCRIPT, default_timeout=60)
    app.session_state["__database__"] = str(_registration_database(tmp_path))
    app.session_state["__duplicate_rows__"] = [plan]
    app.session_state[registration.FORM_CODE_KEY] = "SIM-W46"
    app.session_state[registration.FORM_SOURCE_NAME_KEY] = "PSM W46"
    app.session_state[registration.FORM_SCENARIO_NAME_KEY] = "PSM W46 (SIM-W46)"
    app.session_state[registration.FORM_REGISTERED_AT_KEY] = "2026-11-05 09:00:00"
    app.session_state[registration.FORM_DETAIL_START_KEY] = date(2026, 10, 29)
    app.session_state[registration.FORM_DETAIL_END_KEY] = date(2026, 11, 5)
    app.run()

    assert not app.exception
    assert [str(item.value) for item in app.error] == ["저장을 막았습니다."]
    assert registration.REGISTRATION_CONFLICT_FLASH_KEY not in app.session_state


def test_a_source_whose_cs_is_all_blank_is_refused_instead_of_saving_an_empty_scenario(
    tmp_path: Path,
) -> None:
    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.services.builtin_seed import build_builtin_seed_dataset

    database = _registration_database(tmp_path)
    source = build_builtin_seed_dataset().source_data

    app = _registration_app(database, dict.fromkeys(range(len(source))))

    assert not app.exception
    assert app.error and "CS 가 모두 비어" in app.error[0].value
    assert registration.REGISTRATION_FLASH_KEY not in app.session_state
    assert DuckDBScenarioRepository(database).list_scenarios() == []


CD_PACKAGE_MISSING_SCRIPT = """
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import streamlit as st

import capa_simulation.settings as settings
from capa_simulation.components import bigdataquery_registration as registration
from capa_simulation.io.company_bigdataquery_adapter import QueryWindow

REPORT = __REPORT__
if REPORT is not None:
    settings.CONTAINER_START_REPORT_PATH = Path(REPORT)
    Path(REPORT).write_text(
        json.dumps(
            {
                "version": 1,
                "written_at": "2026-10-24T09:00:00+09:00",
                "steps": {
                    "install": {
                        "status": "skipped",
                        "reason": "CD 환경변수 CAPA_ARTIFACTORY_TOKEN 없음",
                    },
                    "token": {"status": "skipped", "reason": "CD 환경변수 CAPA_BDQ_TOKEN 없음"},
                    "user_name": {"status": "ok", "reason": "있음"},
                },
                "bigdataquery_version": None,
                "token_file": {"exists": False, "modified_at": None},
                "user_name": {"present": True, "masked": "fa***"},
                "missing_environment": ["CAPA_ARTIFACTORY_TOKEN", "CAPA_BDQ_TOKEN"],
                "pip_tail": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

saved = sys.modules.get("bigdataquery")
sys.modules["bigdataquery"] = None
try:
    registration.render_bigdataquery_registration(
        SimpleNamespace(list_scenarios=lambda **_kwargs: []), "demo.duckdb"
    )
    registration._run_catalog_query(
        QueryWindow(start_date=date(2026, 9, 21), end_date=date(2026, 10, 21))
    )
finally:
    if saved is None:
        sys.modules.pop("bigdataquery", None)
    else:
        sys.modules["bigdataquery"] = saved
"""


@pytest.mark.parametrize("with_report", [False, True], ids=["dev-or-company-pc", "cd-container"])
def test_a_missing_package_in_the_cd_container_says_which_variable_to_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, with_report: bool
) -> None:
    """CD 서버에는 셸이 없어 `uv pip install` 안내를 따를 수 없다. 시작 스크립트가 남긴 결과가
    있으면 목록 조회 오류와 화면 머리 경고에 설치 단계 결과와 넣을 환경변수를 덧붙이고, 없으면
    지금과 같다."""
    monkeypatch.setattr(registration, "is_bigdataquery_package_available", lambda: False)
    report = repr(str(tmp_path / "container_start.json")) if with_report else "None"
    app = AppTest.from_string(CD_PACKAGE_MISSING_SCRIPT.replace("__REPORT__", report))
    app.run(timeout=60)

    assert not app.exception
    [error] = app.error
    assert error.value.startswith("현재 환경에 bigdataquery 패키지가 없습니다.")
    # 머리 설정 띠는 값 줄(「패키지 없음」 표지)이고 내역 · 설치 단계 결과는 상태 알림 `AD-04` 의
    # 전문이 든다(설계 규칙 UI-NTF-02).
    assert not app.warning
    note = active_state(app, "AD-04")
    assert note is not None and "bigdataquery 패키지가 없어" in note["full"]
    assert any(caption.value.endswith(":orange[패키지 없음]") for caption in app.caption), [
        caption.value for caption in app.caption
    ]
    banner = str(note["full"])
    for text in (error.value, banner):
        assert ("서버 시작 점검" in text) is with_report
        assert ("`CAPA_ARTIFACTORY_TOKEN`" in text) is with_report


@pytest.mark.parametrize(
    ("catalog_ready", "detail_ready", "places"),
    [
        (False, False, ("CATALOG_QUERY_TEMPLATE", "QUERY_TEMPLATE)")),
        (False, True, ("CATALOG_QUERY_TEMPLATE",)),
        (True, False, ("company_bigdataquery_adapter.py의 QUERY_TEMPLATE",)),
    ],
)
def test_the_missing_query_notice_puts_the_particle_on_the_fixed_word(
    catalog_ready: bool, detail_ready: bool, places: tuple[str, ...]
) -> None:
    """빠진 SQL 자리 이름(영문 상수 끝) 뒤에 조사를 두면 「… 이(가) 아직 설정되지 않았습니다」 갈래
    꼴이었다(개선 거리 I8). 조사는 고정 낱말 「SQL」 에 붙이고 자리는 줄표 뒤에 늘어놓는다."""
    notice = registration.missing_query_notice(
        catalog_ready=catalog_ready, detail_ready=detail_ready
    )

    assert notice is not None
    assert notice.startswith("조회 SQL이 아직 설정되지 않았습니다 — ")
    assert all(place in notice for place in places)
    assert "이(가)" not in notice


def test_no_missing_query_notice_once_both_queries_are_set() -> None:
    assert registration.missing_query_notice(catalog_ready=True, detail_ready=True) is None


@pytest.mark.parametrize(
    ("catalog_ready", "detail_ready", "package_ready", "marks"),
    [
        (False, False, True, ("목록 조회 SQL 미설정", "상세 조회 SQL 미설정")),
        (False, True, False, ("목록 조회 SQL 미설정",)),
        (True, False, True, ("상세 조회 SQL 미설정",)),
        (True, True, False, ("패키지 없음",)),
    ],
)
def test_the_configuration_line_is_a_value_line_with_markers(
    catalog_ready: bool, detail_ready: bool, package_ready: bool, marks: tuple[str, ...]
) -> None:
    """설정 띠는 「**BigDataQuery 설정** · …」 값 줄이고 준비 안 된 칸은 주황 표지 한 마디다 —
    무엇을 어디에 채우는지는 상태 알림 `AD-04` 전문이 든다(설계 규칙 UI-TXT-04 · UI-NTF-02).
    문장으로 끝나지 않는다."""
    line = registration.banner_line(
        catalog_ready=catalog_ready, detail_ready=detail_ready, package_ready=package_ready
    )

    assert line.startswith(registration.BANNER_LABEL + " · ")
    assert all(f":orange[{mark}]" in line for mark in marks)
    assert not line.endswith(("다.", "다", "요."))
    ready = registration.banner_line(catalog_ready=True, detail_ready=True, package_ready=True)
    assert ready == registration.BANNER_READY_LINE


def test_the_notice_reveal_is_the_only_script_run_through_st_html() -> None:
    """`st.html(..., unsafe_allow_javascript=True)` 는 BigDataQuery 등록 저장 결과 칸의 「화면
    밖이면 보이게 옮기기」 한 자리뿐이다 — AGENTS 9장 「스크립트와 컴포넌트」 가 이름을 적은 허용
    예외(2026-11-01 사용자 결정 「그대로 둠」). 다른 스크립트는 그 절의 규칙(`st.iframe` · 회차마다
    같은 내용)을 따른다."""
    root = Path(__file__).resolve().parents[1]
    sources = [root / "app.py", *(root / "app_pages").rglob("*.py"), *(root / "src").rglob("*.py")]
    users = sorted(
        path.relative_to(root).as_posix()
        for path in sources
        if "unsafe_allow_javascript" in path.read_text(encoding="utf-8")
    )
    assert users == ["src/capa_simulation/components/bigdataquery_registration.py"]
