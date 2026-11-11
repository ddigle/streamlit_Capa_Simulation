# Purpose: 시나리오 관리 「점검」 칸의 회차 · 「계산」 칸 · 묶음 줄 · 그 화면으로를 AppTest 로 잰다.

"""「점검」 칸(`components/scenario_input_check.py` — 2026-11-11 입력 점검 시안 보드 답 q1 ~ q7).

묶음 수가 검사와 같은지는 순수 셈 시험(`tests/test_revision_input_check.py`)이 본다. 여기는
화면이다 —
칸이 열린 회차에 고른 리비전만 세는지, 「계산」 칸이 「—」 에서 그 결과로 바뀌는지, 멈춘 리비전의
꼴, 다른 줄을 열어도 칸이 남는지, 「그 화면으로」 가 도착 칸을 적고 옮김을 대기하는지(불러오지 않은
리비전은 불러온 뒤), 「넓게 보기」 가 화면 팝업 호스트로 열리는지, 숨은 탭에서 세지 않는지.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pytest
from alert_marks import data_error_marks
from scenario_list_fake import Calls, ListBrowser, install_fake_list_grid, last
from streamlit.testing.v1 import AppTest
from test_all_pages_render import _page_script

import capa_simulation.components.capacity_gate as capacity_gate
import capa_simulation.components.scenario_input_check as input_check
from capa_simulation.components.scenario_input_check import (
    CALCULATION_REQUIRED_TAB,
    CALCULATION_RESULT,
    CALCULATION_TAB_KEY,
    CALCULATION_UNIT_TAB,
    CHECK_LABELS_KEY,
    GO_LOADS_HELP,
    PLAN_PKG_TAB,
    PLAN_TAB_KEY,
    PLAN_YIELD_TAB,
    STOP_NOTICE_HEAD,
    WIDE_TAG,
    arrival_for,
    wide_target,
)
from capa_simulation.components.scenario_list_grid import CHECKS_KEY, REVISIONS_KEY, TABLE_KEY
from capa_simulation.components.scenario_list_state import DRAFT_KEY
from capa_simulation.components.scenario_management import (
    OFFICIAL_DIALOG_KEY,
    SIDE_CHECK,
    SIDE_DETAIL,
    SIDE_KEY,
    SIDES,
)
from capa_simulation.components.scenario_management_tabs import (
    QUERY_TAB,
    SCENARIO_MANAGEMENT_TABS_KEY,
)
from capa_simulation.components.tab_state import remembered_tab_key
from capa_simulation.navigation import LOAD_CONVERSION, REFERENCE_DATA
from capa_simulation.page_bootstrap import calculation_stop_notice
from capa_simulation.page_tabs_state import PAGE_TABS_QUEUED_KEY
from capa_simulation.persistence.repository import REVISION_TABLES, DuckDBScenarioRepository
from capa_simulation.reference_grid_keys import DATASET_KEY
from capa_simulation.scenario_activation import ACTIVE_PERSISTED_REVISION_ID_KEY
from capa_simulation.services.revision_input_check import (
    GROUP_ASSUMED,
    GROUP_CAPACITY,
    GROUP_PLANS,
    GROUP_ROUTES,
    GROUP_SOURCE,
    GROUP_STOP,
    GROUP_UNROUTED,
    InputCheckGroup,
    RevisionInputCheck,
)
from capa_simulation.services.scenario_list_edits import ListDraft

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = "app_pages/scenario_management.py"
Tables = dict[str, pd.DataFrame]


def _months(frame: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(frame["생산계획년월"])


def _with_exclusions(tables: Tables) -> Tables:
    """경로 하나의 UPEH 를 빼고(경로 묶음) 첫 공정 마지막 달 효율을 0 으로(대당 Capa 제외) — 계산은
    멈추지 않는다."""
    edited = {name: frame.copy() for name, frame in tables.items()}
    processes = list(dict.fromkeys(edited["RQ_UPEH"]["공정"]))
    upeh = edited["RQ_UPEH"]
    edited["RQ_UPEH"] = upeh.loc[upeh["공정"].ne(processes[-1])].reset_index(drop=True)
    run_rate = edited["RQ_RUN_RATE"]
    zero = run_rate["공정"].eq(processes[0]) & _months(run_rate).eq(_months(run_rate).max())
    run_rate.loc[zero, "CAPA_RUN_RATE"] = 0.0
    return edited


def _vital_blank(tables: Tables) -> Tables:
    """여유율 두 행을 비운다 — 대당 Capa 가 기준정보 연결 오류로 멈춘다."""
    vital = tables["RQ_VITAL"].copy()
    vital["편중률"] = vital["편중률"].astype("object")
    vital.loc[vital.index[:2], "편중률"] = None
    return {**tables, "RQ_VITAL": vital}


def _save(database: Path, scenario_id: str, base: str, edit: Any, name: str) -> str:
    repository = DuckDBScenarioRepository(database)
    snapshot = repository.load_revision(base)
    saved = repository.save_revision(
        scenario_id,
        edit({table: snapshot.tables[table] for table in REVISION_TABLES}),
        snapshot.preset,
        revision_name=name,
        parent_revision_id=base,
    )
    return saved.revision.revision_id


def _official(database: Path) -> tuple[str, str]:
    release = DuckDBScenarioRepository(database).latest_official_release()
    assert release is not None
    return release.scenario_id, release.revision_id


def _seeded(tmp_path: Path) -> tuple[str, Path]:
    database = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    return script, database


def _check_app(
    script: str, monkeypatch: pytest.MonkeyPatch, *, side: str = SIDE_CHECK
) -> tuple[AppTest, ListBrowser, Calls]:
    calls = install_fake_list_grid(monkeypatch)
    app = AppTest.from_string(script, default_timeout=120)
    app.session_state[SIDE_KEY] = side
    browser = ListBrowser(app, calls)
    browser.run()
    return app, browser, calls


def _draft(app: AppTest) -> ListDraft:
    draft = app.session_state[DRAFT_KEY]
    assert isinstance(draft, ListDraft)
    return draft


def _calc(calls: Calls) -> dict[str, tuple[str, str]]:
    return {row["id"]: (row["calc"], row["tone"]) for row in last(calls, CHECKS_KEY)["rows"]}


def _heads(app: AppTest) -> str:
    return "\n".join(str(item.value) for item in app.markdown)


def _captions(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.caption]


# ------------------------------------------------------------------ 칸 · 회차


def test_the_check_panel_is_the_second_of_five_and_counts_only_when_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """오른쪽 칸은 다섯이고 「점검」 은 「상세」 다음이다. 「상세」 칸에서 리비전을 골라도 세지 않고
    (UI-PRF-01), 「점검」 칸이 열린 회차에 고른 리비전 하나만 센다."""
    script, _ = _seeded(tmp_path)
    counted: list[str] = []
    real = capacity_gate.input_check_verdict

    def spy(database_path: str, scenario_id: str, revision_id: str) -> RevisionInputCheck:
        counted.append(revision_id)
        return real(database_path, scenario_id, revision_id)

    monkeypatch.setattr(input_check, "input_check_verdict", spy)
    app, browser, calls = _check_app(script, monkeypatch, side=SIDE_DETAIL)
    assert SIDES == ("상세", "점검", "저장 전 변경", "공식 이력", "보관함")
    assert list(app.segmented_control(key=SIDE_KEY).options) == list(SIDES)
    assert counted == [] and not any(name == CHECKS_KEY for name, _ in calls)

    app.session_state[SIDE_KEY] = SIDE_CHECK
    browser.run()

    picked = _draft(app).picked
    assert counted and set(counted) == {picked}
    data = last(calls, CHECKS_KEY)
    assert data["mode"] == "checks" and data["picked"] == picked
    assert _calc(calls)[str(picked)] == ("됨", "done")
    # 칸 머리 한 줄 — 기간은 이 한 자리다.
    assert any(text.startswith("r") and "· 전체 기간 " in text for text in _captions(app))
    heads = _heads(app)
    for title in ("계산 멈춤", "대당 Capa 에서 뺀 기준", "부하량에서 빠진 계획", "측정률 1.0 가정"):
        assert title in heads
    assert "규칙대로 셈에서 뺀 것" in {button.label for button in app.button}


def test_a_revision_turns_from_dash_to_its_count_when_picked_and_keeps_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """고르지 않은 리비전은 「—」 이고, 고르면 그 회차에 「됨 · 확인 n」 이 선다. 다른 리비전으로
    옮겨도 이 세션에서 센 글은 남는다(시안 ga-stop)."""
    script, database = _seeded(tmp_path)
    scenario_id, base = _official(database)
    edited = _save(database, scenario_id, base, _with_exclusions, "빠짐")
    app, browser, calls = _check_app(script, monkeypatch)
    picked = _draft(app).picked
    other = base if picked == edited else edited
    assert _calc(calls)[other] == ("—", "none")

    browser.send(CHECKS_KEY, {"op": "pick", "owner": scenario_id, "id": other})

    assert _draft(app).picked == other
    cells = _calc(calls)
    text, tone = cells[edited]
    assert text.startswith("됨 · 확인 ") and tone == "check"
    assert cells[base] == ("됨", "done")
    assert app.session_state[CHECK_LABELS_KEY][edited] == (text, tone)
    # 고른 리비전의 묶음 — 행 보기 · 그 화면으로.
    labels = [button.label for button in app.button]
    if _draft(app).picked == edited:
        assert "행 보기" in labels and "그 화면으로" in labels


def test_a_stopped_revision_is_marked_and_folds_what_comes_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """멈춘 리비전 — 「계산」 칸 「멈춤」, 멈춤 줄 「계산 멈춤 — 대당 Capa」 와 부제(경로 n),
    뒤 묶음은 「셀 수 없음」 한 줄. 「그 화면으로」 는 기준 정보 그 종류다."""
    script, database = _seeded(tmp_path)
    scenario_id, base = _official(database)
    stopped = _save(database, scenario_id, base, _vital_blank, "멈춤")
    app, browser, calls = _check_app(script, monkeypatch)
    browser.send(CHECKS_KEY, {"op": "pick", "owner": scenario_id, "id": stopped})

    assert _calc(calls)[stopped] == ("멈춤", "error")
    heads = _heads(app)
    assert "계산 멈춤 — 대당 Capa" in heads and "셀 수 없음" in heads
    assert "앞 단계가 멈춰 그 뒤 묶음은 세지 못함" in _captions(app)
    assert any("· 경로 " in text for text in _captions(app))
    # 부제는 계산 멈춤 알림 짧은 글에서 묶음 이름과 겹치는 머리를 뗀 글이다 — 그 머리가 알림 글과
    # 같아야 떼어진다.
    check = capacity_gate.input_check_verdict(str(database), scenario_id, stopped)
    assert check.stop is not None
    notice = calculation_stop_notice(ValueError(check.stop.error))
    assert notice is not None and notice.text.startswith(STOP_NOTICE_HEAD)
    shown = notice.text.removeprefix(STOP_NOTICE_HEAD)
    assert any(text.startswith(shown) for text in _captions(app))
    assert not any(text.startswith(STOP_NOTICE_HEAD) for text in _captions(app))
    go = app.button(key=f"input_check_go_{GROUP_STOP}")
    assert go.help == GO_LOADS_HELP

    go.click().run()
    assert not app.exception
    # 불러오지 않은 리비전이라 불러온 뒤 기준 정보 「여유율」 로 옮김을 대기한다.
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == stopped
    assert app.session_state[DATASET_KEY] == "RQ_VITAL"
    assert app.session_state[PAGE_TABS_QUEUED_KEY] == REFERENCE_DATA.path


def test_opening_another_row_keeps_the_check_panel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「점검」 을 보며 다른 시나리오 줄을 열어도 칸이 남는다(결정 16) — 그 시나리오의 리비전을
    이어 센다."""
    script, database = _seeded(tmp_path)
    repository = DuckDBScenarioRepository(database)
    scenario_id, base = _official(database)
    official = repository.load_revision(base)
    from capa_simulation.persistence.models import ScenarioCreate

    other = repository.create_scenario(
        ScenarioCreate(
            scenario_name="다른 시나리오",
            source_simulation_code="CHECK-OTHER",
            source_simulation_name="다른 시나리오",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="test-v1",
        ),
        official.tables,
        official.preset,
    )
    app, browser, calls = _check_app(script, monkeypatch)
    browser.open(other.scenario.scenario_id)

    assert app.segmented_control(key=SIDE_KEY).value == SIDE_CHECK
    assert _draft(app).opened == other.scenario.scenario_id
    assert last(calls, CHECKS_KEY)["owner"] == other.scenario.scenario_id
    assert _calc(calls)[other.revision.revision_id][0] == "됨"
    # 복제 시나리오는 원천이 없다 — 「—」.
    assert "등록 때 뺀 원천 행" in _heads(app)
    assert "—" in _heads(app)
    del scenario_id


def test_go_on_the_loaded_revision_remembers_the_tab_and_queues_the_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """올라와 있는 리비전의 「그 화면으로」 — 불러오지 않고 도착 탭을 기억 칸에 적고 옮김을
    대기한다(옮기는 것은 `app.py`). 풍선이 없다."""
    script, database = _seeded(tmp_path)
    scenario_id, base = _official(database)
    edited = _save(database, scenario_id, base, _with_exclusions, "빠짐")
    app, browser, calls = _check_app(script, monkeypatch)
    browser.send(CHECKS_KEY, {"op": "pick", "owner": scenario_id, "id": edited})
    loaded_before = app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY]
    go = app.button(key=f"input_check_go_{GROUP_ROUTES}")
    assert go.help == GO_LOADS_HELP

    go.click().run()

    assert not app.exception
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == edited != loaded_before
    assert app.session_state[remembered_tab_key(CALCULATION_TAB_KEY)] == CALCULATION_REQUIRED_TAB
    assert app.session_state[PAGE_TABS_QUEUED_KEY] == CALCULATION_RESULT.path

    # 이제 올라와 있다 — 다시 누르면 풍선 없이 곧바로 옮긴다.
    app.session_state[PAGE_TABS_QUEUED_KEY] = None
    browser.run()
    go = app.button(key=f"input_check_go_{GROUP_ROUTES}")
    assert go.help is None or go.help == ""
    go.click().run()
    assert app.session_state[PAGE_TABS_QUEUED_KEY] == CALCULATION_RESULT.path


def test_go_over_unsaved_edits_asks_in_the_sidebar_popup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """미저장 편집이 있으면 불러오지 않고 사이드바 시나리오 팝업이 그 리비전으로 묻는다 — 옮기지
    않는다."""
    from capa_simulation.components.scenario_status import (
        SCENARIO_DIALOG_KEY,
        SIDEBAR_REVISION_KEY,
    )

    script, database = _seeded(tmp_path)
    scenario_id, base = _official(database)
    edited = _save(database, scenario_id, base, _with_exclusions, "빠짐")
    app, browser, _ = _check_app(script, monkeypatch)
    browser.send(CHECKS_KEY, {"op": "pick", "owner": scenario_id, "id": edited})
    monkeypatch.setattr(input_check, "has_unsaved_scenario_changes", lambda: True)

    app.button(key=f"input_check_go_{GROUP_ROUTES}").click().run()

    assert not app.exception
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == base
    assert app.session_state[SCENARIO_DIALOG_KEY] is True
    assert app.session_state[SIDEBAR_REVISION_KEY] == edited
    assert (
        PAGE_TABS_QUEUED_KEY not in app.session_state or not app.session_state[PAGE_TABS_QUEUED_KEY]
    )


def test_a_press_after_another_pick_does_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """누른 회차에 함께 닿은 고름이 그린 리비전과 다르면 아무것도 하지 않고 단추 곁에 알린다."""
    script, database = _seeded(tmp_path)
    scenario_id, base = _official(database)
    edited = _save(database, scenario_id, base, _with_exclusions, "빠짐")
    app, browser, _ = _check_app(script, monkeypatch)
    browser.send(CHECKS_KEY, {"op": "pick", "owner": scenario_id, "id": edited})
    browser.prepared(CHECKS_KEY, {"op": "pick", "owner": scenario_id, "id": base})

    app.button(key=f"input_check_go_{GROUP_ROUTES}").click().run()

    assert not app.exception
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == base
    assert (
        PAGE_TABS_QUEUED_KEY not in app.session_state or not app.session_state[PAGE_TABS_QUEUED_KEY]
    )


def test_rows_open_in_place_and_the_wide_view_opens_on_the_page_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「행 보기」 는 앞 칸 · 앞 행과 「앞 n행 · 전체 m행」 · 넓게 보기 · CSV 를 펼친다. 「넓게
    보기」 는 화면 팝업 호스트 하나로 열리고, 그 칸이 그 단추를 그리는 동안 남는다."""
    script, database = _seeded(tmp_path)
    scenario_id, base = _official(database)
    edited = _save(database, scenario_id, base, _with_exclusions, "빠짐")
    app, browser, _ = _check_app(script, monkeypatch)
    browser.send(CHECKS_KEY, {"op": "pick", "owner": scenario_id, "id": edited})

    app.button(key=f"input_check_rows_{GROUP_CAPACITY}").click().run()

    assert not app.exception
    assert app.button(key=f"input_check_rows_{GROUP_CAPACITY}").label == "행 접기"
    assert any(text.startswith("앞 ") and "· 전체 " in text for text in _captions(app))
    preview = app.dataframe[0].value
    assert list(preview.columns) == ["생산계획년월", "공정", "양산구분", "제품정보", "제외사유"]
    assert "효율(CAPA_RUN_RATE) 0 이하" in set(preview["제외사유"])
    assert app.get("download_button")

    app.button(key=f"input_check_wide_{GROUP_CAPACITY}_0").click().run()

    assert not app.exception
    opened = app.session_state[OFFICIAL_DIALOG_KEY]
    target = wide_target(opened)
    assert target is not None and target[0] == WIDE_TAG and target[2] == edited
    browser.run()
    assert app.session_state[OFFICIAL_DIALOG_KEY] == opened

    # 다른 칸으로 가면 그 팝업은 걷힌다(호스트 하나 — 열림 값의 꼴로 가른다).
    app.session_state[SIDE_KEY] = SIDE_DETAIL
    browser.run()
    assert OFFICIAL_DIALOG_KEY not in app.session_state


def test_the_db_registration_group_switches_the_tab_on_this_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「등록 때 뺀 원천 행」 의 「그 화면으로」 는 같은 화면 DB 등록 탭이다 — 탭만 바꾸고 불러오지
    않는다."""
    script, database = _seeded(tmp_path)
    scenario_id, base = _official(database)
    check = RevisionInputCheck(
        (
            InputCheckGroup(
                GROUP_SOURCE, "info", "등록 때 뺀 원천 행", 3, "CS 빈 칸 — 계획 1 · 경로 2"
            ),
        )
    )
    monkeypatch.setattr(input_check, "input_check_verdict", lambda *_args: check)
    app, _, _ = _check_app(script, monkeypatch)

    app.button(key=f"input_check_go_{GROUP_SOURCE}").click().run()

    assert not app.exception
    assert app.session_state[SCENARIO_MANAGEMENT_TABS_KEY] == QUERY_TAB
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == base
    assert (
        PAGE_TABS_QUEUED_KEY not in app.session_state or not app.session_state[PAGE_TABS_QUEUED_KEY]
    )
    del scenario_id


def test_a_read_failure_is_the_data_error_mark_and_the_table_stays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """점검을 읽지 못하면 「데이터 Error」 마크(`SC-02`)이고 리비전 표는 남는다 — 다른 리비전을 고를
    수 있다."""
    script, _ = _seeded(tmp_path)

    def held(*_args: object) -> RevisionInputCheck:
        raise duckdb.IOException("IO Error: Could not set lock on file")

    monkeypatch.setattr(input_check, "input_check_verdict", held)
    app, _, calls = _check_app(script, monkeypatch)

    assert data_error_marks(app)
    assert any(name == CHECKS_KEY for name, _ in calls)
    assert "계산 멈춤" not in _heads(app)


def test_a_hidden_tab_draws_the_table_without_counting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Capa 시나리오 탭이 닫힌 회차에도 그 본문은 그린다 — 그 회차의 「점검」 칸은 세지 않는다."""
    script, _ = _seeded(tmp_path)

    def no_count(*_args: object) -> RevisionInputCheck:
        raise AssertionError("닫힌 탭에서 세면 안 된다")

    app, browser, calls = _check_app(script, monkeypatch)
    monkeypatch.setattr(input_check, "input_check_verdict", no_count)
    app.session_state[SCENARIO_MANAGEMENT_TABS_KEY] = QUERY_TAB
    browser.run()

    assert any(name == CHECKS_KEY for name, _ in calls)


# ------------------------------------------------------------------ 도착지 · 화면 글


def _group(key: str, reasons: tuple[tuple[str, int], ...]) -> InputCheckGroup:
    return InputCheckGroup(key, "check", key, sum(n for _, n in reasons), reasons=reasons)


def test_each_group_arrives_where_it_is_fixed() -> None:
    """결정 15 — 묶음마다 고칠 화면의 그 탭 · 종류 단추. 수가 0 이면 단추가 없다."""
    empty = RevisionInputCheck(())
    run_rate = arrival_for(_group(GROUP_CAPACITY, (("CAPA_RUN_RATE 0 이하", 3),)), empty)
    assert run_rate is not None
    assert (run_rate.path, run_rate.key, run_rate.value, run_rate.tab) == (
        REFERENCE_DATA.path,
        DATASET_KEY,
        "RQ_RUN_RATE",
        False,
    )
    both = arrival_for(
        _group(GROUP_CAPACITY, (("CAPA_RUN_RATE 0 이하", 3), ("UPEH 0 이하", 1))), empty
    )
    assert both is not None and both.value == CALCULATION_UNIT_TAB
    routes = arrival_for(_group(GROUP_ROUTES, (("x", 1),)), empty)
    assert routes is not None and routes.value == CALCULATION_REQUIRED_TAB
    yields = arrival_for(_group(GROUP_PLANS, (("RQ_YLD", 2), ("RQ_YLD 값 없음", 1))), empty)
    assert yields is not None and (yields.path, yields.value) == (
        LOAD_CONVERSION.path,
        PLAN_YIELD_TAB,
    )
    plan = arrival_for(
        _group(GROUP_PLANS, (("RQ_YLD", 2), ("RQ_PKG_PLAN 생산수량 빈 값", 1))), empty
    )
    assert plan is not None and plan.value == PLAN_PKG_TAB
    unrouted = arrival_for(_group(GROUP_UNROUTED, (("경로 키 어긋남", 1),)), empty)
    assert unrouted is not None and unrouted.key == PLAN_TAB_KEY
    one = arrival_for(_group(GROUP_ASSUMED, (("RQ_LOT_RATIO", 2),)), empty)
    assert one is not None and (one.path, one.value) == (REFERENCE_DATA.path, "RQ_LOT_RATIO")
    two = arrival_for(_group(GROUP_ASSUMED, (("RQ_LOT_RATIO", 2), ("RQ_WF_RATIO", 1))), empty)
    assert two is not None and (two.path, two.value) == (REFERENCE_DATA.path, None)
    assert arrival_for(_group(GROUP_ROUTES, ()), empty) is None
    assert arrival_for(InputCheckGroup(GROUP_STOP, "error", "계산 멈춤", 0), empty) is None


def test_the_arrival_tabs_are_the_pages_own_labels() -> None:
    """산출 결과 · 생산 계획 화면은 불러올 수 없어 탭 key · 라벨을 따로 둔다 — 화면 글과 같다."""
    calculation = (PROJECT_ROOT / "app_pages" / "calculation_result.py").read_text(encoding="utf-8")
    plan = (PROJECT_ROOT / "app_pages" / "load_conversion.py").read_text(encoding="utf-8")
    assert f'key="{CALCULATION_TAB_KEY}"' in calculation
    for label in (CALCULATION_UNIT_TAB, CALCULATION_REQUIRED_TAB):
        assert f'"{label}"' in calculation
    assert f'TAB_KEY = "{PLAN_TAB_KEY}"' in plan
    for label in (PLAN_PKG_TAB, PLAN_YIELD_TAB):
        assert f'"{label}"' in plan
    assert LOAD_CONVERSION.path == "app_pages/load_conversion.py"
    assert CHECKS_KEY not in {REVISIONS_KEY, TABLE_KEY}
