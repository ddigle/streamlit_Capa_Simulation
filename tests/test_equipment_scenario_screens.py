# Purpose: 설비 시나리오 화면(탭·일정 없음·미확인·잠금·기준선·Space·상세·머리 띠)을 검증한다.

"""설비 시나리오 1단계의 화면 몫(설계 5·6장 — 세션·화면 시험).

- 시나리오 관리: 「설비 시나리오」 구획(표·복제·이름·발행·이어 쓰기 — 가용설비 현황의 탭이던 것,
  2026-10-24), 설비 화면 옛 배포 흔적 경고의 「시나리오 관리에서 이어 쓰기」.
- 가용설비 현황: 「일정 없음 n대」, 가정 설비 시나리오의 미확인 = 공식 일정 기준(Main·RawData 일정
  확인 목록), Preference(공용 Cut-off) 잠금.
- 필요 단축 일정: 기준선 저장은 공식 발행 쌍에서만(거부 까닭 둘), 기준선 머리의 설비 시나리오 출처,
  진척 비교 머리, 카드 링크 `eq`.
- 공정 Capa 상세: HOME 칸 방문은 ◀▶ 뒤에도 공식(방문 기준 칸), 잠근 줄, 카드 `eq` 가 다르면 띠 꼬리.
- Space: 세션 설비 시나리오의 배치를 그리고(가정이면 그 시나리오 일정 호기도), FAB 전체 배치 편집은
  공식에서만(「공식으로 바꾸기」), 찍힌 역할이 바뀌면 배치 저장이 꺼지고 「배치 변경만 버리기」.
- 머리 띠: 아래 줄 끝 「설비 시나리오 · 운영 일정 · r1 · 공식 v1」(Space 도 같은 꼬리).
- 설비 시나리오 구획의 E7 도구: 리비전명(비교 후 쓰기), 「이 리비전으로 되돌리기」(확인 글·확인 체크
  뒤 새 리비전, 세션이 따라감), 「여기서 새 시나리오」(옛 리비전에서).
"""

from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_scenario_repository import (
    OPERATIONS,
    _clone,
    _request,
    _seeded,
    _session,
    _set,
    _with_unit,
)

from capa_simulation.components import equipment_data_workspace as workspace
from capa_simulation.components.app_header import equipment_header_suffix
from capa_simulation.components.equipment_data_workspace import official_confirmation_master
from capa_simulation.components.equipment_scenario_management import (
    CLONE_BUTTON_KEY,
    CLONE_NAME_KEY,
    CONTINUE_BUTTON_KEY,
    EQUIPMENT_KIND,
    LEGACY_TRACE_GOTO_KEY,
    PUBLISH_BUTTON_KEY,
    RESTORE_BUTTON_KEY,
    RESTORE_CONFIRM_KEY,
    RESTORE_NAME_KEY,
    RESTORE_PUBLISH_KEY,
    REVISION_KEY,
    REVISION_NAME_BUTTON_KEY,
    REVISION_NAME_KEY,
    SCENARIO_KEY,
    SCENARIO_KIND_KEY,
    SCENARIO_MANAGEMENT_TAB,
    SCENARIO_MANAGEMENT_TABS_KEY,
    SIMULATION_KIND,
    added_since_sentence,
    branch_unscheduled_sentence,
    publish_preview,
    restore_confirm_label,
    restore_layout_sentence,
    restore_result_message,
    session_heading,
)
from capa_simulation.components.equipment_scenario_status import (
    EQUIPMENT_SCENARIO_FIELD_KEY,
    HOME_VISIT_LOCK_REASON,
    PREFERENCE_LOCK_MESSAGE,
    baseline_equipment_refusal,
    shortening_equipment_basis,
    unscheduled_notice,
)
from capa_simulation.components.equipment_settings_dialog import SETTINGS_BUTTON_KEY
from capa_simulation.components.pick_edit_table import (
    TableDraft,
    draft_session_key,
    shown_session_key,
)
from capa_simulation.components.scenario_management import LIST_EDITOR_KEY
from capa_simulation.components.tab_state import remembered_tab_key
from capa_simulation.equipment_scenario_activation import SELECTION_KEY, EquipmentSession
from capa_simulation.navigation import (
    AVAILABLE_EQUIPMENT_STATUS,
    PROCESS_CAPA_DETAIL,
    SCENARIO_MANAGEMENT,
    SPACE_STATUS,
)
from capa_simulation.page_tabs_state import PAGE_TABS_OPEN_KEY
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    clear_equipment_scenario_cache,
)
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentRelease,
    EquipmentScenarioCatalog,
    EquipmentScenarioSummary,
    EquipmentScheduleRevisionSummary,
    ScheduleRestoreResult,
)
from capa_simulation.process_detail_state import (
    EQUIPMENT_BASIS_OFFICIAL,
    EQUIPMENT_PARAM,
    PROCESS_DETAIL_EQUIPMENT_BASIS_KEY,
    PROCESS_DETAIL_REQUEST_KEY,
    ProcessDetailRequest,
    equipment_band_tail,
    shortening_card_query_params,
)
from capa_simulation.services.equipment_scenario import ScheduleRestorePreview
from capa_simulation.services.schedule_confirmation import (
    CONFIRMATION_KIND_COLUMN,
    STAGE_COLUMN,
    UNCONFIRMED,
    schedule_confirmation_issues,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"
TODAY = date(2026, 10, 24)


@pytest.fixture(autouse=True)
def _fresh_caches() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


# ── 판정이 고르는 글 ─────────────────────────────────────────────────────────────────


def _catalog(*, latest: str = "s14", latest_no: int = 14) -> EquipmentScenarioCatalog:
    return EquipmentScenarioCatalog(
        scenarios=(
            EquipmentScenarioSummary(
                "operations",
                "운영 일정",
                "ACTIVE",
                list_order=1,
                latest_schedule_revision_id=latest,
                latest_revision_no=latest_no,
                revision_count=latest_no,
            ),
            EquipmentScenarioSummary(
                "setup",
                "셋업 실무",
                "ACTIVE",
                latest_schedule_revision_id="b4",
                latest_revision_no=4,
                revision_count=4,
            ),
        ),
        latest_release=EquipmentRelease(3, "operations", "s12", datetime(2026, 10, 24)),
    )


def test_baseline_saving_is_refused_off_the_official_pair_with_two_reasons() -> None:
    """기준선은 공식 발행 쌍에서만 저장한다(E5). 가정 설비 시나리오와 공식 시나리오의 발행하지
    않은 리비전을 다른 까닭으로 알린다."""
    catalog = _catalog()
    official = EquipmentSession(catalog, catalog.scenarios[0], "s12")
    assert baseline_equipment_refusal(official) is None
    assert baseline_equipment_refusal(None) is None

    assumption = EquipmentSession(catalog, catalog.scenarios[1], "b4")
    refusal = baseline_equipment_refusal(assumption)
    assert refusal is not None and refusal.startswith("가정 설비 시나리오(「셋업 실무」 r4)")
    assert "공식 v3" in refusal

    unpublished = EquipmentSession(catalog, catalog.scenarios[0], "s14")
    refusal = baseline_equipment_refusal(unpublished)
    assert refusal is not None and refusal.startswith("발행하지 않은 리비전(「운영 일정」 r14")
    assert "공식은 공식 v3" in refusal


def test_the_shortening_basis_carries_the_label_and_the_compare_note() -> None:
    catalog = _catalog()
    official = shortening_equipment_basis(EquipmentSession(catalog, catalog.scenarios[0], "s12"))
    assert official.label == "공식 v3" and official.compare_note is None
    assert official.release_no == 3 and official.scenario_name == "운영 일정"

    assumption = shortening_equipment_basis(EquipmentSession(catalog, catalog.scenarios[1], "b4"))
    assert assumption.label == "셋업 실무 r4" and assumption.release_no is None
    assert assumption.compare_note is not None
    assert assumption.compare_note.startswith("지금 = 셋업 실무 r4 · 기준선 = 공식")


def test_the_unscheduled_notice_says_how_many_and_what_to_do() -> None:
    assert unscheduled_notice(0) is None
    line = unscheduled_notice(2)
    assert line is not None and line.startswith("이 설비 시나리오에 일정이 없는 호기 2대")
    assert "일정 칸이나 시나리오 메모" in line
    official = unscheduled_notice(1, official=True)
    assert official is not None and official.startswith("공식 일정 없음 1대")


def test_the_header_suffix_follows_the_badge_order() -> None:
    """차례는 사이드바 배지와 같다 — 미저장 → 공식 vN → 낡음 → 가정 배치 → 저장된 리비전(설계 8-2).
    Space 의 「(고정)」 꼬리는 걷었다(S3 — Space 도 세션 설비 시나리오를 그린다)."""
    label = {
        "scenario_name": "운영 일정",
        "revision_no": 12,
        "latest_revision_no": 14,
        "release_no": 3,
        "official_pair": True,
        "stale": True,
        "layout_differs": True,
    }
    assert equipment_header_suffix(label) == "설비 시나리오 · 운영 일정 · r12 · 공식 v3"
    assert equipment_header_suffix(label, unsaved=True) == (
        "설비 시나리오 · 운영 일정 · r12 · 미저장 변경"
    )
    stale = {**label, "official_pair": False}
    assert equipment_header_suffix(stale) == "설비 시나리오 · 운영 일정 · r12 · 최신 r14 있음"
    layout = {**stale, "stale": False}
    assert equipment_header_suffix(layout) == "설비 시나리오 · 운영 일정 · r12 · 가정 배치"
    saved = {**layout, "layout_differs": False}
    assert equipment_header_suffix(saved) == "설비 시나리오 · 운영 일정 · r12 · 저장된 리비전"
    assert equipment_header_suffix({"scenario_name": None}) is None
    assert equipment_header_suffix(None) is None


def test_the_card_link_carries_eq_and_the_band_tail_only_when_it_differs() -> None:
    params = shortening_card_query_params(
        process="P",
        month=202601,
        target=1.1,
        start_month=202601,
        end_month=202612,
        shortened=1,
        new=0,
        theme=None,
        equipment="셋업 실무 r4",
    )
    assert params[EQUIPMENT_PARAM] == "셋업 실무 r4"
    without = shortening_card_query_params(
        process="P",
        month=None,
        target=1.1,
        start_month=202601,
        end_month=202612,
        shortened=1,
        new=0,
        theme=None,
    )
    assert EQUIPMENT_PARAM not in without
    assert equipment_band_tail("셋업 실무 r4", "공식 v3") == (
        "카드는 「셋업 실무 r4」 기준 — 이 화면은 공식 v3"
    )
    assert equipment_band_tail("공식 v3", "공식 v3") is None
    assert equipment_band_tail(None, "공식 v3") is None


def test_the_publish_preview_puts_the_current_and_the_new_official_side_by_side() -> None:
    catalog = _catalog()
    session = EquipmentSession(catalog, catalog.scenarios[0], "s12")
    revision = EquipmentScheduleRevisionSummary("b3", "setup", 3, "save", datetime(2026, 10, 24))

    lines = publish_preview(session, catalog.scenarios[1], revision)

    assert lines[0] == "지금 공식 v3 · 「운영 일정」 → 새 공식 v4 · 「셋업 실무」 r3"
    assert lines[1] == "r3은 「셋업 실무」 의 최신(r4)이 아닙니다."


# ── 미확인 = 공식 일정 기준 ───────────────────────────────────────────────────────────


def _diverged(tmp_path: Path) -> tuple[DuckDBEquipmentRepository, str]:
    """공식(운영 일정)은 EQ-01 만 Qual 이 지났고, 가정(셋업 실무)은 EQ-02 만 Qual 이 지났다."""
    repository = _seeded(tmp_path)
    clone = _clone(repository)
    mine = _session(repository, clone.equipment_scenario_id)
    repository.save_equipment(
        _request(
            mine,
            clone.equipment_scenario_id,
            equipment=_set(mine.equipment, "EQ-01", "Qual일정", "2027-01-01"),
        )
    )
    official = _session(repository)
    repository.save_equipment(
        _request(official, equipment=_set(official.equipment, "EQ-02", "Qual일정", "2027-01-01"))
    )
    return repository, clone.equipment_scenario_id


def _qual_unconfirmed(master: pd.DataFrame) -> set[str]:
    issues = schedule_confirmation_issues(master, today=TODAY)
    picked = issues.loc[issues[CONFIRMATION_KIND_COLUMN].eq(UNCONFIRMED)]
    return set(picked.loc[picked[STAGE_COLUMN].eq("Qual"), "설비명"].astype(str))


def test_an_assumption_sees_unconfirmed_by_the_official_schedule(tmp_path: Path) -> None:
    """공식에서만 지난 호기(EQ-01)는 보이고 가정에서만 지난 호기(EQ-02)는 안 보인다. 공통
    칸(편집본)은 그대로 — 실적·상태를 고치면 빠진다."""
    repository, setup = _diverged(tmp_path)
    mine = _session(repository, setup)
    official = repository.load_official_snapshot()
    assert official is not None

    assert _qual_unconfirmed(mine.equipment) == {"EQ-02"}
    assert _qual_unconfirmed(official_confirmation_master(mine.equipment, official)) == {"EQ-01"}
    done = _set(mine.equipment, "EQ-01", "Qual실적", "2026-08-09")
    done = _set(done, "EQ-01", "Qual상태", "완료")
    assert _qual_unconfirmed(official_confirmation_master(done, official)) == set()


def test_the_confirmation_memo_keys_on_the_official_token_and_buffer_generation() -> None:
    """설비 마스터 탭의 일정 확인 마스터 메모(`_confirmation_master`)는 공식 토큰 · 편집본 세대로만
    키를 잡는다 — 옛 폼이 넘기던 붙여넣기 미리보기 후보 칸(`preview`)은 개편 D 리뷰 rs-d 로 걷었다
    (부르는 곳은 탭 하나이고 늘 없음을 넘겼다)."""
    parameters = inspect.signature(workspace._confirmation_master).parameters

    assert list(parameters) == ["master", "official"]
    assert "preview" not in inspect.getsource(workspace._confirmation_master)


# ── app.py 와 함께 ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def _shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """빈 시나리오 DB(내장 시드) + 래퍼로 한 번 저장한 설비 DB 를 보는 `app.py`."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.settings as settings

    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    _seeded(tmp_path)
    return AppTest.from_file(str(APP_PATH), default_timeout=300)


def _repository(tmp_path: Path) -> DuckDBEquipmentRepository:
    return DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _select(app: AppTest, scenario_id: str, schedule_revision_id: str | None) -> None:
    app.session_state[SELECTION_KEY] = {
        "scenario_id": scenario_id,
        "schedule_revision_id": schedule_revision_id,
    }


def _texts(app: AppTest) -> list[str]:
    return [
        str(item.value)
        for kind in ("caption", "info", "warning", "success", "error", "markdown")
        for item in getattr(app, kind)
    ]


def _heading(app: AppTest) -> str:
    """시나리오 관리 「설비 시나리오」 구획 머리 한 줄(「이 세션: …」) — 이 화면에는 사이드바 줄이
    없다."""
    return next(
        str(item.value).strip("*")
        for item in app.markdown
        if str(item.value).startswith("**이 세션:")
    )


def _equipment_section(app: AppTest) -> AppTest:
    """시나리오 관리 「설비 시나리오」 구획을 연다."""
    app.switch_page(SCENARIO_MANAGEMENT.path)
    app.session_state[SCENARIO_KIND_KEY] = EQUIPMENT_KIND
    return _ok(app.run())


def _field(app: AppTest) -> Any:
    return next(
        (button for button in app.sidebar.button if button.key == EQUIPMENT_SCENARIO_FIELD_KEY),
        None,
    )


def _header_bodies(app: AppTest) -> list[str]:
    return [
        str(element.proto.body)
        for element in app.get("html")
        if '[data-testid="stHeader"]::after' in element.proto.body
    ]


def test_the_header_ends_with_the_equipment_scenario_in_the_same_run(_shell: AppTest) -> None:
    """설비 화면 첫 회차부터 머리 띠 아래 줄 끝에 설비 시나리오가 선다(한 회차 늦지 않음). Space 도
    같은 꼬리다(S3 — 「(고정)」 을 걷었다)."""
    app = _ok(_shell.run())
    assert not any("설비 시나리오 ·" in body for body in _header_bodies(app))

    _ok(app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path).run())
    assert "설비 시나리오 · 운영 일정 · r1 · 공식 v1" in _header_bodies(app)[-1]
    # 다음 회차는 `app.py` 가 먼저 그 글로 그리고, 페이지가 같은 글로 한 번 더 보낸다(이벤트 칸
    # 자리가 회차마다 같다).
    _ok(app.run())
    bodies = _header_bodies(app)
    assert len(bodies) == 2
    assert all("설비 시나리오 · 운영 일정 · r1 · 공식 v1" in body for body in bodies)

    _ok(app.switch_page(SPACE_STATUS.path).run())
    assert "설비 시나리오 · 운영 일정 · r1 · 공식 v1" in _header_bodies(app)[-1]
    assert "(고정)" not in _header_bodies(app)[-1]


def test_on_narrow_windows_the_equipment_tail_comes_first_in_the_bottom_line() -> None:
    """꼬리를 줄 끝에 두면 사이드바를 연 1280px 미만 창에서 말줄임이 꼬리를 통째로 지운다(900px 자리
    355px · 필요 526px — 2026-10-24 E2E). 1280px 미만에서는 아래 줄을 꼬리 먼저로 바꿔 적는다.
    꼬리가 없는 화면에는 그 규칙이 없다."""
    from capa_simulation.components.app_header import _header_css

    tail = "설비 시나리오 · 셋업 실무 · r4 · 저장된 리비전"
    css = _header_css("위", f"DEMO · 적용 26.01–26.12 · {tail}", narrow_bottom=f"{tail} · DEMO")

    wide, narrow = css.split("@media (max-width: 1279.98px)")
    assert f'content: "DEMO · 적용 26.01–26.12 · {tail}"' in wide
    assert f'content: "{tail} · DEMO"' in narrow
    assert "@media (max-width: 1279.98px)" not in _header_css("위", "DEMO")


def test_the_scenario_section_clones_publishes_and_the_session_stays_pinned(
    _shell: AppTest, tmp_path: Path
) -> None:
    app = _equipment_section(_ok(_shell.run()))
    assert _heading(app) == "이 세션: 운영 일정 · r1 · 공식 v1"
    assert any(
        "설비 시나리오" in frame.value.columns
        and frame.value["설비 시나리오"].tolist() == ["운영 일정"]
        for frame in app.dataframe
    )

    app.text_input(key=CLONE_NAME_KEY).input("셋업 실무")
    app.button(key=CLONE_BUTTON_KEY).click()
    _ok(app.run())
    repository = _repository(tmp_path)
    names = [item.scenario_name for item in repository.list_equipment_scenarios()]
    assert names == ["운영 일정", "셋업 실무"]
    assert any("「셋업 실무」 r1 을 만들었습니다" in text for text in _texts(app))

    # 셋업 실무 r1 을 공식으로 발행 — 세션은 고른 그대로(운영 일정 r1)이고 배지만 바뀐다.
    setup = next(
        item for item in repository.list_equipment_scenarios() if item.scenario_name == "셋업 실무"
    )
    app.selectbox(key=SCENARIO_KEY).set_value(setup.equipment_scenario_id)
    _ok(app.run())
    app.button(key=PUBLISH_BUTTON_KEY).click()
    _ok(app.run())
    release = repository.latest_equipment_release()
    assert release is not None and release.release_no == 2
    assert release.equipment_scenario_id == setup.equipment_scenario_id
    assert _heading(app) == "이 세션: 운영 일정 · r1"
    # 이 화면에는 사이드바 설비 시나리오 줄이 서지 않는다(D4).
    assert _field(app) is None


def test_scenario_management_opens_on_simulation_and_switches_to_equipment(
    _shell: AppTest,
) -> None:
    """시나리오 관리 「시나리오 관리」 탭 맨 위 「관리할 시나리오」 — 처음은 시뮬레이션
    시나리오(저장소 상태·시나리오 작업 그대로), 「설비 시나리오」 를 고르면 설비 구획만 선다(D4)."""
    app = _ok(_shell.run())
    _ok(app.switch_page(SCENARIO_MANAGEMENT.path).run())
    kind = app.segmented_control(key=SCENARIO_KIND_KEY)
    assert kind.label == "관리할 시나리오" and kind.value == SIMULATION_KIND
    assert any("저장소 상태" in str(item.value) for item in app.markdown)
    assert not any("설비 시나리오" in frame.value.columns for frame in app.dataframe)

    kind.set_value(EQUIPMENT_KIND)
    _ok(app.run())
    assert not any("저장소 상태" in str(item.value) for item in app.markdown)
    assert any("설비 시나리오" in frame.value.columns for frame in app.dataframe)
    assert _heading(app) == "이 세션: 운영 일정 · r1 · 공식 v1"


def test_an_equipment_db_error_stays_inside_the_equipment_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """설비 DB 를 읽지 못해도 시뮬레이션 구획은 그대로 서고, 설비 구획만 까닭을 알린다(설비 DB 는 그
    구획 안에서만 연다)."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.settings as settings

    broken = tmp_path / "not_a_database"
    broken.mkdir()
    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", broken)
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    app = _ok(AppTest.from_file(str(APP_PATH), default_timeout=300).run())
    _ok(app.switch_page(SCENARIO_MANAGEMENT.path).run())
    assert any("저장소 상태" in str(item.value) for item in app.markdown)

    _equipment_section(app)
    assert any("설비 시나리오를 준비하지 못했습니다" in str(item.value) for item in app.error)
    # 「관리할 시나리오」 전환과 다른 탭은 그대로다.
    assert app.segmented_control(key=SCENARIO_KIND_KEY).value == EQUIPMENT_KIND
    assert len(app.tabs) >= 3


def test_a_session_move_notice_stands_above_the_tabs_while_the_section_tab_is_hidden(
    _shell: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """세션을 다른 리비전으로 옮겼다는 알림(미저장 설비 편집을 버렸다는 말)은 그 회차 한 번뿐이다.
    세 탭을 늘 그려 다른 탭을 보는 회차에도 구획이 세션을 풀므로, 그때는 숨은 패널이 아니라 탭 묶음
    위에 선다(2026-10-25 리뷰). 「시나리오 관리」 탭이 보이면 구획 안 그대로다."""
    from capa_simulation.components import equipment_scenario_management as section
    from capa_simulation.equipment_scenario_activation import resolve_equipment_session

    notice = (
        "「운영 일정」 r1 을 지금 공통 대장과 합칠 수 없어 「운영 일정」 r2 로 열었습니다 — "
        "저장하지 않은 설비 편집은 버렸습니다."
    )
    monkeypatch.setattr(
        section,
        "resolve_equipment_session",
        lambda path: replace(resolve_equipment_session(path), notice=notice),
    )
    app = _ok(_shell.run())
    app.switch_page(SCENARIO_MANAGEMENT.path)
    app.session_state[SCENARIO_KIND_KEY] = EQUIPMENT_KIND
    app.session_state[SCENARIO_MANAGEMENT_TABS_KEY] = ":material/cloud_download: BigDataQuery 등록"
    _ok(app.run())
    assert notice in [str(item.value) for item in app.main.warning]
    assert notice not in [str(item.value) for tab in app.main.tabs for item in tab.warning]

    app.session_state[SCENARIO_MANAGEMENT_TABS_KEY] = SCENARIO_MANAGEMENT_TAB
    _ok(app.run())
    assert [str(item.value) for item in app.main.warning].count(notice) == 1
    assert notice in [str(item.value) for item in app.main.tabs[0].warning]


def test_switching_the_managed_kind_keeps_unsaved_list_edits(_shell: AppTest) -> None:
    """「관리할 시나리오」 를 오가도 목록 표에서 고치고 저장하지 않은 이름은 남는다 — 위젯이
    아니라 행 id 초안이라 돌아오면 그대로이고 화면 탭 줄의 점도 남는다(다음 「변경 저장」 에
    실린다). Guide 가 「사라집니다」 라고 적었던 것을 바로잡았다(2026-10-25 리뷰) — 사라지는
    것은 입력 칸에 적던 글뿐이다."""
    app = _ok(_shell.run())
    _ok(app.switch_page(SCENARIO_MANAGEMENT.path).run())
    shown = app.session_state[shown_session_key(LIST_EDITOR_KEY)]
    row = shown.rows[0]
    app.session_state[draft_session_key(LIST_EDITOR_KEY)] = TableDraft(
        names={row: "PROBE-이름"}, name_base={row: shown.names[row]}
    )
    _ok(app.run())
    app.segmented_control(key=SCENARIO_KIND_KEY).set_value(EQUIPMENT_KIND)
    _ok(app.run())
    app.segmented_control(key=SCENARIO_KIND_KEY).set_value(SIMULATION_KIND)
    _ok(app.run())
    assert app.session_state[draft_session_key(LIST_EDITOR_KEY)].names == {row: "PROBE-이름"}

    guide_path = PROJECT_ROOT / "src" / "capa_simulation" / "guides" / "scenario_management.md"
    guide = " ".join(guide_path.read_text(encoding="utf-8").split())
    assert "저장하지 않은 표 편집은 사라집니다" not in guide
    assert "표에서 고치고 저장하지 않은 이름·순서는 남아" in guide


def test_the_section_heading_names_the_sessions_pair() -> None:
    catalog = _catalog()
    official = EquipmentSession(
        catalog=catalog, scenario=catalog.scenarios[0], schedule_revision_id="s12"
    )
    assert session_heading(official) == "이 세션: 운영 일정 · 공식 v3"
    latest = EquipmentSession(
        catalog=catalog, scenario=catalog.scenarios[1], schedule_revision_id="b4"
    )
    assert session_heading(latest) == "이 세션: 셋업 실무 · r4"
    assert session_heading(EquipmentSession(catalog=catalog)) == "이 세션: 설비 시나리오 없음"


def test_settings_cutoff_is_read_only_on_an_assumption_and_open_on_the_official(
    _shell: AppTest, tmp_path: Path
) -> None:
    """「설정」 팝업의 공용 Cut-off — 가정 설비 시나리오면 읽기 전용(E3, 개편 전 `Preference`
    탭)."""
    clone = _clone(_repository(tmp_path))
    app = _ok(_shell.run())
    _ok(app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path).run())
    _ok(app.button(key=SETTINGS_BUTTON_KEY).click().run())
    assert not any(item.value == PREFERENCE_LOCK_MESSAGE for item in app.info)
    assert any(button.label == "Cut-off 저장" for button in app.button)

    _select(app, clone.equipment_scenario_id, clone.latest_schedule_revision_id)
    _ok(app.run())
    assert any(item.value == PREFERENCE_LOCK_MESSAGE for item in app.info)
    assert not any(button.label == "Cut-off 저장" for button in app.button)


def test_an_unscheduled_unit_is_announced_and_left_out_of_the_assumption(
    _shell: AppTest, tmp_path: Path
) -> None:
    """함께 넣기를 끄고 공식에 넣은 새 호기는 가정 설비 시나리오에 일정이 없다 — 가용설비 현황이
    「일정 없음 1대」 를 알리고, 공식 설비 시나리오로 돌아오면 그 알림이 없다(공식에는 일정이
    있다)."""
    repository = _repository(tmp_path)
    clone = _clone(repository)
    session = _session(repository)
    repository.save_equipment(
        _request(
            session,
            equipment=_with_unit(session.equipment, "EQ-NEW", 70),
            propagate_new_units=False,
        )
    )
    app = _ok(_shell.run())
    app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path)
    _select(app, clone.equipment_scenario_id, clone.latest_schedule_revision_id)
    _ok(app.run())
    assert any("일정이 없는 호기 1대" in str(item.value) for item in app.info)

    _select(app, OPERATIONS, None)
    _ok(app.run())
    assert not any("일정이 없는 호기" in str(item.value) for item in app.info)


def test_space_draws_the_assumption_and_locks_only_the_fab_there(
    _shell: AppTest, tmp_path: Path
) -> None:
    """가정 설비 시나리오 세션의 Space 는 그 시나리오를 그린다(LY3 — 그 시나리오에만 일정이 있는
    호기도 서고 「공식 일정 없음」 알림이 없다). 층 배치 편집은 열리고(LY4), FAB 전체 배치 편집은
    잠기며
    (G5) 그 자리의 「공식으로 바꾸기」 가 세션을 공식으로 옮긴다."""
    repository = _repository(tmp_path)
    clone = _clone(repository)
    mine = _session(repository, clone.equipment_scenario_id)
    repository.save_equipment(
        _request(
            mine,
            clone.equipment_scenario_id,
            equipment=_with_unit(mine.equipment, "EQ-B-ONLY", 70),
            propagate_new_units=False,
        )
    )
    app = _ok(_shell.run())
    app.switch_page(SPACE_STATUS.path)
    _select(app, clone.equipment_scenario_id, None)
    _ok(app.run())
    texts = _texts(app)
    assert not any("공식 일정 없음" in text for text in texts)
    assert not any("배치 편집은 공식 설비 시나리오" in text for text in texts)
    assert app.toggle(key="space_fab_edit_mode").disabled
    field = _field(app)
    assert field is not None and not field.disabled and field.label == "셋업 실무 · r2"
    switch = app.button(key="space_switch_to_official")
    assert not switch.disabled
    switch.click()
    _ok(app.run())
    assert app.session_state[SELECTION_KEY]["scenario_id"] == OPERATIONS
    assert not app.toggle(key="space_fab_edit_mode").disabled
    assert any("공식 일정 없음 1대" in text for text in _texts(app))


def test_space_keeps_unsaved_layout_edits_savable_when_a_new_official_locks_editing(
    _shell: AppTest, tmp_path: Path
) -> None:
    """Space 에서 좌표를 적용해 둔 사이 남이 「운영 일정」 일정을 저장해 공식 v2 를 내면 세션은 공식
    시나리오의 낡은 리비전이 된다. 공식 배치는 공통이라 낡아도 잠기지 않고(설계 8-4 — 새 호기 폼만
    꺼진다) 남은 변경의 상자가 그대로 저장한다."""
    from capa_simulation.components.equipment_data_workspace import (
        BUFFER_GENERATION_KEY,
        BUFFER_KEY,
    )

    repository = _repository(tmp_path)
    app = _ok(_shell.run())
    _ok(app.switch_page(SPACE_STATUS.path).run())
    baseline, equipment, downtime = app.session_state[BUFFER_KEY]
    moved = equipment.copy()
    first = moved.index[moved["설비명"].eq("EQ-01")][0]
    moved.loc[first, "X좌표"] = float(moved.loc[first, "X좌표"]) + 1
    app.session_state[BUFFER_KEY] = (baseline, moved, downtime)
    app.session_state[BUFFER_GENERATION_KEY] = int(app.session_state[BUFFER_GENERATION_KEY]) + 1
    _ok(app.run())
    assert not app.button(key="space_layout_save").disabled

    other = _session(repository)
    published = repository.save_equipment(
        _request(other, equipment=_set(other.equipment, "EQ-02", "Qual일정", "2026-08-24"))
    )
    assert published.release_no == 2
    _ok(app.run())

    texts = _texts(app)
    assert not any("배치 편집이 잠겨" in text for text in texts)
    save = app.button(key="space_layout_save")
    assert not save.disabled
    save.click()
    _ok(app.run())
    saved = _session(repository)
    assert saved.revision.revision_no == 2
    assert _value_of(saved, "EQ-01", "X좌표") == float(equipment.loc[first, "X좌표"]) + 1
    assert saved.schedule is not None and saved.schedule.revision_no == 2


def test_space_refuses_an_official_layout_edit_once_its_scenario_lost_the_official(
    _shell: AppTest, tmp_path: Path
) -> None:
    """공식 세션에서 좌표를 적용해 둔 사이(적용이 역할 official 을 찍는다) 남이 다른 설비 시나리오를
    공식으로 내면 그 세션은 가정이 된다. 그 공식 배치 편집이 가정 배치 차이로 조용히 들어가지 않게
    층 배치 편집이 잠기고(찍힌 역할 ≠ 지금 역할 — 설계 6-2) 상자의 「배치 저장」 이 꺼지며 「배치
    변경만 버리기」 가 선다. 그 단추는 배치만 되돌리고 다른 편집은 남긴다(검토 M5). 저장소도 찍힌
    역할을 대조해 막는다(두 겹)."""
    from capa_simulation.components.equipment_data_workspace import (
        BUFFER_GENERATION_KEY,
        BUFFER_KEY,
        LAYOUT_ROLE_KEY,
    )

    repository = _repository(tmp_path)
    app = _ok(_shell.run())
    _ok(app.switch_page(SPACE_STATUS.path).run())
    baseline, equipment, downtime = app.session_state[BUFFER_KEY]
    moved = equipment.copy()
    first = moved.index[moved["설비명"].eq("EQ-01")][0]
    moved.loc[first, "X좌표"] = 40.0
    moved.loc[first, "설비이력"] = "남길 편집"
    app.session_state[BUFFER_KEY] = (baseline, moved, downtime)
    app.session_state[BUFFER_GENERATION_KEY] = int(app.session_state[BUFFER_GENERATION_KEY]) + 1
    app.session_state[LAYOUT_ROLE_KEY] = "official"
    _ok(app.run())
    clone = _clone(repository)
    assert clone.latest_schedule_revision_id is not None
    repository.publish_equipment_release(
        clone.latest_schedule_revision_id,
        released_by=None,
        note=None,
        expected_latest_release_no=1,
    )
    clear_equipment_scenario_cache()
    _ok(app.run())
    texts = _texts(app)
    reason = (
        "그 사이 공식 설비 시나리오가 「셋업 실무」로 바뀌어 이 배치 변경(공식 배치에 들어갈 "
        "편집이었음)을 저장할 수 없습니다"
    )
    # 까닭은 잠금 줄에 한 번만 — 저장 안 한 배치 상자는 저장하지 않는다는 것만 적는다(E2E r2).
    assert sum(reason in text for text in texts) == 1
    assert any(
        "배치 편집이 잠겨 이 배치 변경은 저장하지 않습니다 — 까닭은 아래 잠금 줄에 있습니다."
        in text
        for text in texts
    )
    assert app.button(key="space_layout_save").disabled
    before = [len(repository.list_revisions())] + [
        item.revision_count for item in repository.list_equipment_scenarios()
    ]

    app.button(key="space_layout_discard_layout").click()
    _ok(app.run())

    _, kept, _ = app.session_state[BUFFER_KEY]
    row = kept.loc[kept["설비명"].eq("EQ-01")].iloc[0]
    assert row["X좌표"] == 10 and row["설비이력"] == "남길 편집"
    assert LAYOUT_ROLE_KEY not in app.session_state
    after = [len(repository.list_revisions())] + [
        item.revision_count for item in repository.list_equipment_scenarios()
    ]
    assert after == before
    assert all(item.latest_layout_unit_count == 0 for item in repository.list_equipment_scenarios())
    official = repository.load_official_snapshot()
    assert official is not None and _value_of(official, "EQ-01", "X좌표") == 10


def test_space_layout_save_refuses_removing_a_unit_another_scenario_schedules(
    _shell: AppTest, tmp_path: Path
) -> None:
    """확인 체크가 없는 Space 「배치 저장」 도 다른 설비 시나리오에 일정이 있는 호기를 지우는 저장은
    막는다(설계 11-2 6단계) — RawData 저장 칸에서 확인하라고 알린다."""
    from capa_simulation.components.equipment_data_workspace import (
        BUFFER_GENERATION_KEY,
        BUFFER_KEY,
    )

    repository = _repository(tmp_path)
    _clone(repository)
    app = _ok(_shell.run())
    _ok(app.switch_page(SPACE_STATUS.path).run())
    baseline, equipment, downtime = app.session_state[BUFFER_KEY]
    moved = equipment.loc[equipment["설비명"].ne("EQ-02")].reset_index(drop=True)
    first = moved.index[moved["설비명"].eq("EQ-01")][0]
    moved.loc[first, "X좌표"] = float(moved.loc[first, "X좌표"]) + 1
    app.session_state[BUFFER_KEY] = (baseline, moved, downtime)
    app.session_state[BUFFER_GENERATION_KEY] = int(app.session_state[BUFFER_GENERATION_KEY]) + 1
    _ok(app.run())
    save = app.button(key="space_layout_save")
    assert not save.disabled
    save.click()
    _ok(app.run())

    assert len(repository.list_revisions()) == 1
    assert any(
        "지우는 호기 1대(EQ-02)는 다른 설비 시나리오 1개(「셋업 실무」)에도 일정이 있습니다" in text
        and "저장하려면 가용설비 현황 설비 마스터 탭 저장 칸의" in text
        for text in _texts(app)
    )


def _value_of(snapshot: Any, name: str, column: str) -> Any:
    return snapshot.equipment.set_index("설비명").loc[name, column]


def test_a_home_visit_to_the_detail_stays_official_and_locks_the_row(
    _shell: AppTest, tmp_path: Path
) -> None:
    """세션이 가정(셋업 실무)이어도 HOME 칸으로 들어온 공정 Capa 상세는 공식이고 줄이 잠긴다. 같은
    화면에서 다시 돌아도(◀▶ 와 같은 회차) 공식이고, 그 화면 탭이 열린 채 다른 화면에 갔다 와도 이어
    보아 공식이다(2026-10-24 페이지 탭). 탭을 닫고 새로 들어오면 세션을 따른다."""
    clone = _clone(_repository(tmp_path))
    app = _ok(_shell.run())
    _select(app, clone.equipment_scenario_id, clone.latest_schedule_revision_id)
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process="DEMO_Chip_Attach", month=202601
    )
    _ok(app.switch_page(PROCESS_CAPA_DETAIL.path).run())
    assert app.session_state[PROCESS_DETAIL_EQUIPMENT_BASIS_KEY] == EQUIPMENT_BASIS_OFFICIAL
    field = _field(app)
    assert field is not None and field.disabled
    # 값 칸은 「(고정)」 만 붙여 1280px 에서도 잘리지 않고, 까닭은 줄 아래 한 줄로 선다(꺼진 단추라
    # 풍선이 없다 — ◀▶ 뒤에는 출처 띠가 걷혀 이 줄이 기준을 알리는 자리다).
    assert field.label == "운영 일정 · r1 (고정)"
    assert any(HOME_VISIT_LOCK_REASON in str(item.value) for item in app.sidebar.caption)

    _ok(app.run())
    field = _field(app)
    assert field is not None and field.disabled and field.label.endswith("(고정)")
    assert any(HOME_VISIT_LOCK_REASON in str(item.value) for item in app.sidebar.caption)

    _ok(app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path).run())
    _ok(app.switch_page(PROCESS_CAPA_DETAIL.path).run())
    field = _field(app)
    assert field is not None and field.disabled and field.label.endswith("(고정)")
    assert app.session_state[PROCESS_DETAIL_EQUIPMENT_BASIS_KEY] == EQUIPMENT_BASIS_OFFICIAL

    _ok(app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path).run())
    # 공정 Capa 상세 탭을 닫았다(`page_tabs._on_close` 가 남기는 목록).
    app.session_state[PAGE_TABS_OPEN_KEY] = tuple(
        path for path in app.session_state[PAGE_TABS_OPEN_KEY] if path != PROCESS_CAPA_DETAIL.path
    )
    _ok(app.switch_page(PROCESS_CAPA_DETAIL.path).run())
    field = _field(app)
    assert field is not None and not field.disabled and field.label == "셋업 실무 · r1"
    assert PROCESS_DETAIL_EQUIPMENT_BASIS_KEY not in app.session_state
    assert not any(HOME_VISIT_LOCK_REASON in str(item.value) for item in app.sidebar.caption)


def test_a_home_visit_judges_the_constraint_link_by_the_session_snapshot(
    _shell: AppTest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HOME 칸 방문(공식 잠금)이고 세션이 가정 설비 시나리오면 「이 공정 제약 시뮬레이션」 판정만
    세션 스냅샷으로 한 번 더 낸다 — 제약 시뮬레이션은 늘 사이드바 설비 시나리오다(D6·R-14). 풍선이
    그 사실을 말한다. 사이드바로 들어온 방문은 화면의 판정을 그대로 쓴다(한 번)."""
    import streamlit as st

    import capa_simulation.services.process_equipment_timeline as timeline
    from capa_simulation.navigation import CONSTRAINT_SIMULATION

    clone = _clone(_repository(tmp_path))
    calls: list[str] = []
    original = timeline.dynamic_readiness

    def recording(
        equipment: pd.DataFrame | None,
        baseline: pd.DataFrame | None,
        cutoff: pd.DataFrame | None,
        *,
        process: str,
    ) -> Any:
        calls.append(process)
        return original(equipment, baseline, cutoff, process=process)

    links: list[dict[str, Any]] = []
    original_link = st.page_link

    def record(page: Any, **kwargs: Any) -> Any:
        links.append({"page": str(getattr(page, "_page", page)), **kwargs})
        return original_link(page, **kwargs)

    monkeypatch.setattr(timeline, "dynamic_readiness", recording)
    monkeypatch.setattr(st, "page_link", record)
    app = _ok(_shell.run())
    _select(app, clone.equipment_scenario_id, clone.latest_schedule_revision_id)
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process="DEMO_Chip_Attach", month=202601
    )
    calls.clear()
    links.clear()
    _ok(app.switch_page(PROCESS_CAPA_DETAIL.path).run())
    assert calls == ["DEMO_Chip_Attach", "DEMO_Chip_Attach"]
    constraint = [link for link in links if link["page"].endswith(CONSTRAINT_SIMULATION.path)]
    assert constraint
    assert "사이드바 설비 시나리오 기준으로 엽니다" in str(constraint[-1]["help"])

    # 탭을 닫고 사이드바로 새로 들어오면(세션 기준) 화면의 판정 하나뿐이다.
    _ok(app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path).run())
    app.session_state[PAGE_TABS_OPEN_KEY] = tuple(
        path for path in app.session_state[PAGE_TABS_OPEN_KEY] if path != PROCESS_CAPA_DETAIL.path
    )
    calls.clear()
    _ok(app.switch_page(PROCESS_CAPA_DETAIL.path).run())
    assert calls == ["DEMO_Chip_Attach"]


@pytest.mark.parametrize(
    ("official_ready", "session_ready"),
    [(True, False), (False, True)],
)
def test_a_home_visit_opens_or_locks_the_constraint_link_by_the_session_judgment(
    _shell: AppTest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    official_ready: bool,
    session_ready: bool,
) -> None:
    """R-14 — HOME 칸 방문(공식 잠금)이고 세션이 가정 설비 시나리오면 링크의 켜짐·꺼짐은 **세션
    스냅샷 판정**을 따른다. 공식은 서고 가정은 서지 않는 공정이면 꺼지고(까닭 풍선), 그 반대면
    켜진다. 판정 차례는 화면 판정(공식 스냅샷) → 링크 판정(세션 스냅샷)이다 — 두 판정의 답을 갈라
    링크가 어느 쪽을 보는지 잰다."""
    import streamlit as st

    import capa_simulation.services.process_equipment_timeline as timeline
    from capa_simulation.navigation import CONSTRAINT_SIMULATION

    clone = _clone(_repository(tmp_path))
    answers = iter([official_ready, session_ready])

    def judged(
        equipment: pd.DataFrame | None,
        baseline: pd.DataFrame | None,
        cutoff: pd.DataFrame | None,
        *,
        process: str,
    ) -> Any:
        if next(answers):
            return timeline.DynamicReadiness(
                timeline.READY, cutoff_days=7, has_units=True, has_baseline=True
            )
        return timeline.DynamicReadiness(timeline.NO_EQUIPMENT)

    links: list[dict[str, Any]] = []
    original_link = st.page_link

    def record(page: Any, **kwargs: Any) -> Any:
        links.append({"page": str(getattr(page, "_page", page)), **kwargs})
        return original_link(page, **kwargs)

    app = _ok(_shell.run())
    _select(app, clone.equipment_scenario_id, clone.latest_schedule_revision_id)
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process="DEMO_Chip_Attach", month=202601
    )
    monkeypatch.setattr(timeline, "dynamic_readiness", judged)
    monkeypatch.setattr(st, "page_link", record)
    _ok(app.switch_page(PROCESS_CAPA_DETAIL.path).run())
    constraint = [link for link in links if link["page"].endswith(CONSTRAINT_SIMULATION.path)]
    assert constraint
    assert constraint[-1]["disabled"] is (not session_ready)
    help_text = str(constraint[-1]["help"])
    assert "사이드바 설비 시나리오 기준으로 엽니다" in help_text
    assert ("설비 일정이 서야 엽니다" in help_text) is (not session_ready)


def test_a_long_scenario_name_is_shortened_in_the_field_so_the_revision_stays_visible() -> None:
    """값 칸은 한 줄 말줄임이다 — 26자 이름(「셋업 실무 2026 하반기 반입 지연 가정 케이스」)이면
    1280px·900px 모두 「 · r4」 가 잘려 고정된 리비전 번호가 보이지 않았다(2026-10-24 E2E). 이름만
    줄인다. 짧은 이름은 그대로다."""
    from capa_simulation.components.app_header import FIELD_NAME_WIDTH, short_scenario_name
    from capa_simulation.components.equipment_scenario_status import equipment_field_label

    long = "셋업 실무 2026 하반기 반입 지연 가정 케이스"
    short = short_scenario_name(long)
    assert short.endswith("…") and long.startswith(short[:-1])
    width = sum(2 if "가" <= char <= "힣" else 1 for char in short)
    assert width <= FIELD_NAME_WIDTH
    assert short_scenario_name("운영 일정") == "운영 일정"
    assert short_scenario_name("A" * FIELD_NAME_WIDTH) == "A" * FIELD_NAME_WIDTH

    catalog = _catalog()
    session = EquipmentSession(
        catalog=catalog,
        scenario=EquipmentScenarioSummary(
            "setup", long, "ACTIVE", latest_schedule_revision_id="b4", latest_revision_no=4
        ),
        schedule_revision_id="b4",
    )
    assert equipment_field_label(session) == f"{short} · r4"
    # 머리 띠 꼬리도 같은 줄인 이름이다 — 좁은 창에서 꼬리 끝 상태까지 들어간다.
    assert equipment_header_suffix(session.label()) == (
        f"설비 시나리오 · {short} · r4 · 저장된 리비전"
    )


# ── 설비 시나리오 탭 — E7 리비전 도구 ─────────────────────────────────────────────────


def _scenario_tab(shell: AppTest) -> AppTest:
    """설비 화면을 먼저 열어 편집본을 세운 뒤(미저장 판정의 재료) 시나리오 관리 「설비 시나리오」
    구획으로 간다."""
    app = _ok(shell.run())
    _ok(app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path).run())
    return _equipment_section(app)


def _revision_id(repository: DuckDBEquipmentRepository, revision_no: int) -> str:
    return next(
        item.schedule_revision_id
        for item in repository.list_schedule_revisions(OPERATIONS)
        if item.revision_no == revision_no
    )


def _revision_table(app: AppTest) -> pd.DataFrame:
    return next(frame.value for frame in app.dataframe if "리비전명" in frame.value.columns)


def _restore_confirm(app: AppTest) -> Any:
    """되돌리기 확인 체크 — key 꼬리가 확인 글을 정한 값 다섯이라 머리로 찾는다(늘 하나)."""
    (confirm,) = [box for box in app.checkbox if str(box.key).startswith(RESTORE_CONFIRM_KEY)]
    return confirm


def _restore_input(app: AppTest, base: str) -> Any:
    """되돌리기 입력 칸 — key 꼬리가 고른 리비전이라 머리로 찾는다(늘 하나)."""
    (field,) = [item for item in app.text_input if str(item.key).startswith(base)]
    return field


def _moved_on(repository: DuckDBEquipmentRepository) -> None:
    """「운영 일정」 r2 — EQ-02 의 Qual일정을 옮기고 새 호기 EQ-NEW 를 넣는다(공통 r2 · 공식 v2)."""
    session = _session(repository)
    repository.save_equipment(
        _request(
            session,
            equipment=_with_unit(
                _set(session.equipment, "EQ-02", "Qual일정", "2026-08-24"), "EQ-NEW", 70
            ),
        )
    )


def test_the_tab_names_a_revision_and_refuses_a_name_someone_changed_meanwhile(
    _shell: AppTest, tmp_path: Path
) -> None:
    """리비전명은 이름표다 — 저장하면 리비전 표가 바로 새 이름을 보인다. 칸을 세운 뒤 남이 먼저
    바꿨으면 덮지 않고 맨 위에 지금 이름을 알리고 칸을 그 이름으로 다시 세운다."""
    repository = _repository(tmp_path)
    first = _revision_id(repository, 1)
    app = _scenario_tab(_shell)
    field = f"{REVISION_NAME_KEY}__{first}"

    app.text_input(key=field).input("셋업 전 일정")
    app.button(key=REVISION_NAME_BUTTON_KEY).click()
    _ok(app.run())
    assert any("r1 · 셋업 전 일정 — 리비전명을 저장했습니다" in text for text in _texts(app))
    assert _revision_table(app)["리비전명"].tolist() == ["셋업 전 일정"]
    assert repository.list_schedule_revisions(OPERATIONS)[0].revision_name == "셋업 전 일정"

    # 칸을 세운 뒤(세대 1) 남이 먼저 바꾼다 — 같은 프로세스의 다른 세션이 목록을 비운 것과 같다.
    repository.rename_schedule_revision(first, name="남이 바꿈", expected_name="셋업 전 일정")
    clear_equipment_scenario_cache()
    app.text_input(key=f"{REVISION_NAME_KEY}__g1__{first}").input("내 이름")
    app.button(key=REVISION_NAME_BUTTON_KEY).click()
    _ok(app.run())
    assert any(
        "다른 사용자가 먼저 리비전명을 바꿨습니다(지금: 남이 바꿈)" in t for t in _texts(app)
    )
    assert repository.list_schedule_revisions(OPERATIONS)[0].revision_name == "남이 바꿈"
    assert app.text_input(key=f"{REVISION_NAME_KEY}__g2__{first}").value == "남이 바꿈"


def test_the_tab_restores_an_old_revision_after_a_confirm_that_says_what_changes(
    _shell: AppTest, tmp_path: Path
) -> None:
    """옛 r1 을 고르면 확인 글이 바뀌는 호기 수와 「r1 뒤에 공통 대장에 든 호기 n대는 일정 없음」 을
    적고, 확인 체크를 켜야 단추가 선다. 되돌리면 r3 이 r1 의 일정으로 서고 공식으로 발행되며, 이
    세션(저장 안 한 편집 없음)이 r3 으로 옮긴다. 공통 대장은 그대로다."""
    repository = _repository(tmp_path)
    _moved_on(repository)
    first = _revision_id(repository, 1)
    app = _scenario_tab(_shell)
    # 최신을 고른 동안은 되돌릴 것이 없다.
    assert any("r2는 「운영 일정」 의 최신이라 되돌릴 것이 없습니다" in t for t in _texts(app))

    app.selectbox(key=REVISION_KEY).set_value(first)
    _ok(app.run())
    texts = _texts(app)
    assert any("최신 r2 위에 새 리비전 r3을 저장하고 r1~r2는 그대로 남습니다" in t for t in texts)
    assert any("일정이나 비가동이 바뀌는 호기 2대" in text for text in texts)
    assert any(
        "r1 뒤에 공통 대장에 든 호기(지금 1대)는 r1에 일정이 없어 이 설비 시나리오에서 「일정 "
        "없음」 이 됩니다" in text
        for text in texts
    )
    confirm = _restore_confirm(app)
    assert str(confirm.label) == (
        "r1의 일정으로 되돌립니다 — 호기 2대의 일정이 바뀌고, r1 뒤에 공통 대장에 든 호기 1대는 "
        "「일정 없음」 이 됩니다."
    )
    assert app.button(key=RESTORE_BUTTON_KEY).disabled
    common_before = repository.latest_revision_id()

    confirm.check()
    _ok(app.run())
    app.button(key=RESTORE_BUTTON_KEY).click()
    _ok(app.run())

    message = next(text for text in _texts(app) if "되돌려" in text)
    assert "「운영 일정」 r1의 일정으로 되돌려 r3을 저장했습니다(일정이 바뀐 호기 2대)." in message
    assert "공식 v3으로 발행했습니다." in message and "이 세션을 r3으로 옮겼습니다." in message
    third = _revision_id(repository, 3)
    assert app.session_state[SELECTION_KEY]["schedule_revision_id"] == third
    # 리비전 상자도 새 리비전으로 옮긴다 — 옛 r1 에 머물면 「같아 되돌릴 것이 없습니다」 만 보인다.
    assert app.selectbox(key=REVISION_KEY).value == third
    assert repository.latest_revision_id() == common_before
    official = repository.load_official_snapshot()
    assert official is not None and official.schedule is not None
    assert official.schedule.schedule_revision_id == third
    assert official.schedule.origin == "restore"
    assert _value_of(official, "EQ-02", "Qual일정") == pd.Timestamp("2026-08-21")
    assert official.unscheduled_units == frozenset({"EQ-NEW"})
    assert _heading(app) == "이 세션: 운영 일정 · r3 · 공식 v3"


def test_restoring_the_official_scenario_to_a_layout_only_revision_offers_nothing(
    _shell: AppTest, tmp_path: Path
) -> None:
    """S2 리뷰 — 공식 시나리오의 「가정이던 때」 리비전(배치 차이만 다름)을 고르면 저장소는 차이를
    버리고 쓸 것이 없다고 본다. 확인 화면도 같은 판정이라 확인 체크·단추를 세우지 않고, 차이가
    따라오지 않는다고 적는다(전에는 체크·단추가 서고 누르면 아무것도 쓰지 않았다)."""
    repository = _repository(tmp_path)
    clone = _clone(repository)
    mine = _session(repository, clone.equipment_scenario_id)
    saved = repository.save_equipment(
        _request(
            mine,
            clone.equipment_scenario_id,
            equipment=_set(mine.equipment, "EQ-01", "X좌표", 50.0),
        )
    )
    assert saved.schedule is not None
    cleared = repository.clear_layout_overlay(
        clone.equipment_scenario_id,
        expected_latest_schedule_revision_id=saved.schedule.schedule_revision_id,
    )
    assert cleared is not None
    repository.publish_equipment_release(
        cleared.schedule_revision_id, released_by=None, note=None, expected_latest_release_no=1
    )
    app = _scenario_tab(_shell)
    app.selectbox(key=SCENARIO_KEY).set_value(clone.equipment_scenario_id)
    _ok(app.run())
    app.selectbox(key=REVISION_KEY).set_value(saved.schedule.schedule_revision_id)
    _ok(app.run())

    texts = _texts(app)
    assert any(
        "r2에 저장된 배치 차이(호기 1행)는 공식 설비 시나리오라 따라오지 않습니다" in text
        for text in texts
    )
    assert any("모두 같아 되돌릴 것이 없습니다" in text for text in texts)
    assert not [box for box in app.checkbox if str(box.key).startswith(RESTORE_CONFIRM_KEY)]
    assert not [button for button in app.button if button.key == RESTORE_BUTTON_KEY]


def test_the_restore_words_say_what_happens_to_the_layout_difference() -> None:
    """가정 시나리오의 배치만 다른 리비전을 되돌리면 확인 글·결과 글이 배치 차이를 말한다(「일정이
    바뀐 호기 0대」 만 적지 않게)."""
    chosen = _summary(2)
    preview = ScheduleRestorePreview(
        layout_unit_rows=1,
        layout_digest="d",
        restored_layout_unit_rows=1,
        restored_layout_digest="d",
    )
    assert restore_layout_sentence(chosen, preview, official_scenario=False) == (
        "r2의 가정 배치(저장된 차이 호기 1행)도 되살립니다."
    )
    assert "따라오지 않습니다" in restore_layout_sentence(chosen, preview, official_scenario=True)
    assert restore_layout_sentence(chosen, ScheduleRestorePreview(), official_scenario=False) == ""
    created = EquipmentScheduleRevisionSummary(
        "s4", OPERATIONS, 4, "restore", datetime(2026, 10, 25), layout_unit_count=1
    )
    message = restore_result_message(
        "셋업 실무",
        chosen,
        ScheduleRestoreResult(schedule=created, preview=preview),
        moved=False,
        kept_unsaved=False,
    )
    assert "(일정이 바뀐 호기 0대)" in message
    assert "배치 차이도 r2 것으로 맞췄습니다(r4에 저장된 차이 호기 1행)." in message


def _saved_elsewhere(repository: DuckDBEquipmentRepository, unit: str, value: str) -> None:
    """다른 세션의 저장 — 「운영 일정」 최신 위에 그 호기의 Qual일정만 옮긴 새 리비전(공식 발행)."""
    session = _session(repository)
    repository.save_equipment(
        _request(session, equipment=_set(session.equipment, unit, "Qual일정", value))
    )


def test_the_restore_confirm_and_fields_belong_to_the_chosen_revision(
    _shell: AppTest, tmp_path: Path
) -> None:
    """확인 체크는 고른 리비전의 확인 글에 묶인다 — r1 에서 체크한 뒤 r2 를 고르면 r2 의 확인 글은
    풀린 채 서고 단추가 잠긴다(r2 글을 보지 않고 되돌리지 않게). 새 리비전명 칸도 리비전마다
    따로다(「r1 일정 복원」 이 r2 로 따라가지 않게). 리비전만 바꾼 것이라 「그 사이 바뀌었다」
    알림은 없다."""
    repository = _repository(tmp_path)
    _moved_on(repository)
    _saved_elsewhere(repository, "EQ-01", "2026-09-30")
    first = _revision_id(repository, 1)
    second = _revision_id(repository, 2)
    app = _scenario_tab(_shell)
    app.selectbox(key=REVISION_KEY).set_value(first)
    _ok(app.run())
    _restore_input(app, RESTORE_NAME_KEY).input("r1 일정 복원")
    _restore_confirm(app).check()
    _ok(app.run())
    assert not app.button(key=RESTORE_BUTTON_KEY).disabled

    app.selectbox(key=REVISION_KEY).set_value(second)
    _ok(app.run())
    confirm = _restore_confirm(app)
    assert str(confirm.label).startswith("r2의 일정으로 되돌립니다")
    assert confirm.value is False
    assert app.button(key=RESTORE_BUTTON_KEY).disabled
    assert _restore_input(app, RESTORE_NAME_KEY).value == ""
    assert not any("확인 체크를 풀었습니다" in text for text in _texts(app))
    assert len(repository.list_schedule_revisions(OPERATIONS)) == 3


def test_a_restore_confirmed_before_someone_else_saved_waits_for_a_new_confirm(
    _shell: AppTest, tmp_path: Path
) -> None:
    """확인 체크 뒤 다른 사용자가 저장하면(확인 글을 정한 그 시나리오 최신이 바뀜) 누른 회차에
    체크가 풀린 새 칸이 서고 단추가 잠긴다 — 본 적 없는 차이로 되돌리지 않고 까닭을 알린다. 바뀐
    글을 보고 다시 체크하면 그 글의 수대로 되돌린다."""
    repository = _repository(tmp_path)
    _moved_on(repository)
    first = _revision_id(repository, 1)
    app = _scenario_tab(_shell)
    app.selectbox(key=REVISION_KEY).set_value(first)
    _ok(app.run())
    seen = str(_restore_confirm(app).label)
    assert "호기 2대의 일정이 바뀌고" in seen
    _restore_confirm(app).check()
    _ok(app.run())

    _saved_elsewhere(repository, "EQ-01", "2026-09-30")
    clear_equipment_scenario_cache()
    app.button(key=RESTORE_BUTTON_KEY).click()
    _ok(app.run())

    assert len(repository.list_schedule_revisions(OPERATIONS)) == 3
    assert any("확인 체크를 풀었습니다" in text for text in _texts(app))
    confirm = _restore_confirm(app)
    assert confirm.value is False
    assert "호기 3대의 일정이 바뀌고" in str(confirm.label)
    assert app.button(key=RESTORE_BUTTON_KEY).disabled

    confirm.check()
    _ok(app.run())
    assert not any("확인 체크를 풀었습니다" in text for text in _texts(app))
    app.button(key=RESTORE_BUTTON_KEY).click()
    _ok(app.run())
    message = next(text for text in _texts(app) if "되돌려" in text)
    assert "r1의 일정으로 되돌려 r4를 저장했습니다(일정이 바뀐 호기 3대)." in message


def test_restoring_with_unsaved_equipment_edits_leaves_the_session_where_it_was(
    _shell: AppTest, tmp_path: Path
) -> None:
    """이 세션에 저장하지 않은 설비 편집이 있으면 되돌린 뒤에도 세션을 새 리비전으로 옮기지
    않는다 — 편집을 버리지 않고, 알림이 사이드바에서 최신을 불러오라고 말한다. 탭의 리비전 상자는
    새 리비전으로 간다."""
    from capa_simulation.components.equipment_data_workspace import (
        _SEEDED_GENERATION_KEY,
        BUFFER_GENERATION_KEY,
    )

    repository = _repository(tmp_path)
    _moved_on(repository)
    first = _revision_id(repository, 1)
    app = _scenario_tab(_shell)
    app.session_state[BUFFER_GENERATION_KEY] = int(app.session_state[BUFFER_GENERATION_KEY]) + 1
    app.selectbox(key=REVISION_KEY).set_value(first)
    _ok(app.run())
    _restore_confirm(app).check()
    _ok(app.run())
    app.button(key=RESTORE_BUTTON_KEY).click()
    _ok(app.run())

    message = next(text for text in _texts(app) if "되돌려" in text)
    assert "r1의 일정으로 되돌려 r3을 저장했습니다" in message
    assert "저장하지 않은 설비 편집이 있어 보던 리비전을 그대로 둡니다" in message
    assert "이 세션을" not in message
    assert _heading(app).startswith("이 세션: 운영 일정 · r2")
    assert app.selectbox(key=REVISION_KEY).value == _revision_id(repository, 3)
    # 편집은 버리지 않았다(`has_unsaved_equipment_edits` 와 같은 판정).
    assert int(app.session_state[BUFFER_GENERATION_KEY]) > int(
        app.session_state[_SEEDED_GENERATION_KEY]
    )


def test_restoring_the_official_scenario_over_an_unpublished_revision_says_it_did_not_publish(
    _shell: AppTest, tmp_path: Path
) -> None:
    """공식 시나리오에 발행하지 않은 더 새 리비전(r2)이 있으면 발행 체크가 켜져 있어도 되돌린 r3 을
    발행하지 않고 알림이 그 까닭과 「공식으로 발행」 을 말한다."""
    repository = _repository(tmp_path)
    session = _session(repository)
    repository.save_equipment(
        _request(
            session,
            equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-24"),
            publish_official=False,
        )
    )
    first = _revision_id(repository, 1)
    app = _scenario_tab(_shell)
    app.selectbox(key=REVISION_KEY).set_value(first)
    _ok(app.run())
    assert any("공식 설비 시나리오입니다" in text for text in _texts(app))
    (publish,) = [box for box in app.checkbox if str(box.key).startswith(RESTORE_PUBLISH_KEY)]
    assert publish.value is True
    _restore_confirm(app).check()
    _ok(app.run())
    app.button(key=RESTORE_BUTTON_KEY).click()
    _ok(app.run())

    message = next(text for text in _texts(app) if "되돌려" in text)
    assert "r1의 일정으로 되돌려 r3을 저장했습니다" in message
    assert (
        "공식 설비 시나리오에 발행하지 않은 더 새 리비전이 있어 공식 발행은 하지 않았습니다 — 이 "
        "구획의 「공식으로 발행」 으로 냅니다." in message
    )
    assert "발행했습니다." not in message
    release = repository.latest_equipment_release()
    assert release is not None and release.release_no == 1


def _summary(revision_no: int) -> EquipmentScheduleRevisionSummary:
    return EquipmentScheduleRevisionSummary(
        f"s{revision_no}", OPERATIONS, revision_no, "save", datetime(2026, 10, 24)
    )


def test_the_restore_sentences_say_none_when_no_unit_came_after_the_revision() -> None:
    """그 리비전 뒤에 공통 대장에 든 호기가 0대면 「일정 없음이 된다 — 빠진다」 대신 없다고
    적는다(수는 늘 적는다). 「여기서 새 시나리오」 안내도 같다."""
    first = _summary(1)
    none_added = ScheduleRestorePreview(changed_units=2, unscheduled_after=1, added_since=0)
    assert added_since_sentence(first, 0) == "r1 뒤에 공통 대장에 든 호기는 없습니다(0대)."
    assert "빠집니다" in added_since_sentence(first, 3) and "(지금 3대)" in added_since_sentence(
        first, 3
    )
    assert restore_confirm_label(first, none_added) == (
        "r1의 일정으로 되돌립니다 — 호기 2대의 일정이 바뀌고, r1 뒤에 공통 대장에 든 호기는 "
        "없습니다(0대)."
    )
    assert branch_unscheduled_sentence(first, none_added) == (
        "r1에 일정이 없는 호기 1대는 새 시나리오에서도 「일정 없음」 입니다 — r1 뒤에 공통 "
        "대장에 든 호기는 없습니다(0대)."
    )
    assert branch_unscheduled_sentence(first, ScheduleRestorePreview()) == (
        "r1에는 일정이 없는 호기가 없습니다(0대) — 새 시나리오의 모든 호기가 일정을 듭니다."
    )


def test_the_tab_starts_a_new_scenario_from_an_old_revision(
    _shell: AppTest, tmp_path: Path
) -> None:
    """「여기서 새 시나리오」 는 최신이 아닌 리비전에서도 된다 — 새 시나리오 r1 은 그 리비전의
    일정이고 그 뒤 공통 대장에 든 호기는 일정 없음이다(안내가 수를 적는다)."""
    repository = _repository(tmp_path)
    _moved_on(repository)
    first = _revision_id(repository, 1)
    app = _scenario_tab(_shell)
    app.selectbox(key=REVISION_KEY).set_value(first)
    _ok(app.run())
    assert any(
        "r1에 일정이 없는 호기 1대는 새 시나리오에서도 「일정 없음」 입니다 — 그 가운데 r1 뒤에 "
        "공통 대장에 든 호기가 1대입니다." in text
        for text in _texts(app)
    )

    app.text_input(key=CLONE_NAME_KEY).input("r1 가지")
    app.button(key=CLONE_BUTTON_KEY).click()
    _ok(app.run())

    assert any(
        "「운영 일정」 r1에서 설비 시나리오 「r1 가지」 r1 을 만들었습니다" in text
        for text in _texts(app)
    )
    branch = next(
        item for item in repository.list_equipment_scenarios() if item.scenario_name == "r1 가지"
    )
    copied = _session(repository, branch.equipment_scenario_id)
    assert copied.unscheduled_units == frozenset({"EQ-NEW"})
    assert _value_of(copied, "EQ-02", "Qual일정") == pd.Timestamp("2026-08-21")
    assert len(repository.list_schedule_revisions(OPERATIONS)) == 2


def test_a_legacy_trace_warns_and_the_section_continues_writing(
    _shell: AppTest, tmp_path: Path
) -> None:
    """옛 배포가 0027 경계 뒤에 계약 v3 리비전을 남기면 설비 화면 맨 위에 경고와 「시나리오 관리에서
    이어 쓰기」 단추가 서고, 그 단추는 시나리오 관리 「설비 시나리오」 구획으로 옮긴다. 그 구획의
    「이대로 이어 쓰기」 뒤에는 경고가 걷힌다."""
    import duckdb

    repository = _repository(tmp_path)
    with duckdb.connect(str(repository.database_path)) as connection:
        connection.execute(
            """
            INSERT INTO equipment_ops.revision (
                revision_id, revision_no, note, baseline_hash, schedule_hash, equipment_hash,
                downtime_hash, equipment_contract_version
            ) VALUES ('old-deploy', 2, '옛 배포', 'b', 's', 'e', 'd', 3)
            """
        )
    assert repository.legacy_trace_count() == 1
    app = _ok(_shell.run())
    _ok(app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path).run())
    warning = next(
        str(item.value) for item in app.warning if "옛 배포로 저장한 설비 리비전 1개" in item.value
    )
    assert "시나리오 관리 › 설비 시나리오의 「이대로 이어 쓰기」" in warning
    # 단추는 탭 기억·전환 칸을 적고 그 화면으로 옮긴다(`app.py` 를 연 AppTest 는 그 회차에 진짜로
    # 옮긴다 — 다음 `run()` 의 화면으로 기억하지는 않는다).
    app.button(key=LEGACY_TRACE_GOTO_KEY).click()
    _ok(app.run())
    assert app.session_state[SCENARIO_KIND_KEY] == EQUIPMENT_KIND
    assert app.session_state[remembered_tab_key(SCENARIO_MANAGEMENT_TABS_KEY)] == (
        SCENARIO_MANAGEMENT_TAB
    )
    assert any("설비 시나리오" in frame.value.columns for frame in app.dataframe), (
        "설비 시나리오 구획으로 옮기지 않았다"
    )
    _equipment_section(app)
    assert any("옛 배포로 저장한 설비 리비전 1개" in str(item.value) for item in app.warning)

    # 되돌릴 수 없는 쓰기라 확인 체크를 켜야 단추가 선다. 체크 글은 빠지는 호기 수를 말한다(새
    # 판에서 만든 두 호기 — 옛 배포 리비전 r2 는 비어 있다).
    assert app.button(key=CONTINUE_BUTTON_KEY).disabled
    confirm = next(box for box in app.checkbox if "이대로 이어 씁니다" in str(box.label))
    assert "옛 배포 리비전 r2를 공통 대장 최신으로" in str(confirm.label)
    assert "호기 2대가 그 리비전에 없어 모든 설비 시나리오에서 빠지고" in str(confirm.label)
    confirm.check()
    _ok(app.run())
    app.button(key=CONTINUE_BUTTON_KEY).click()
    _ok(app.run())
    assert repository.legacy_trace_count() == 0
    assert not any("옛 배포로 저장한 설비 리비전" in str(item.value) for item in app.warning)


def test_an_unmergeable_legacy_trace_opens_the_screens_without_schedules_and_says_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """옛 배포 리비전이 공식 일정과도 합쳐지지 않으면 설비 화면이 「준비하지 못했습니다」 로 멈추지
    않고 공통만 읽어 **일정 없이** 연다(배지 「일정 없이 엶」·알림). 설비 시나리오 탭은 이어 쓰기
    단추 대신 그 까닭과 백업 복원을 말하고, Space 도 열린다(편집 잠금)."""
    from test_equipment_migration_0027_scenarios import build_legacy_database
    from test_equipment_scenario_repository import _add_unmergeable_trace

    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.settings as settings

    path = tmp_path / "equipment.duckdb"
    build_legacy_database(path)
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    _add_unmergeable_trace(repository)
    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", path)
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    app = _ok(AppTest.from_file(str(APP_PATH), default_timeout=300).run())

    _ok(app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path).run())
    texts = _texts(app) + [str(item.value) for item in app.sidebar.warning]
    assert not any("준비하지 못했습니다" in text for text in texts)
    assert any("일정 없이 열었습니다" in text for text in texts)
    assert any("옛 배포로 저장한 설비 리비전 1개" in text for text in texts)
    field = _field(app)
    assert field is not None and field.label == "운영 일정"
    assert any("일정 없이 엶" in str(item.value) for item in app.sidebar.caption)

    # 시나리오 관리 「설비 시나리오」 구획 — 사이드바 줄이 없어 머리 한 줄과 세션 알림이 대신한다.
    _equipment_section(app)
    texts = _texts(app)
    assert _heading(app).startswith("이 세션: 운영 일정 · 일정 없이 엶")
    assert any("일정 없이 열었습니다" in text for text in texts)
    assert any("이어 쓸 수 없습니다" in text and "백업을 복원하세요" in text for text in texts)
    assert not any(button.key == CONTINUE_BUTTON_KEY for button in app.button)

    _ok(app.switch_page(SPACE_STATUS.path).run())
    assert not any("준비하지 못했습니다" in text for text in _texts(app))


def _fields_app() -> None:
    import streamlit as st

    from capa_simulation.components.equipment_save_fields import (
        render_equipment_save_fields,
        save_fields_from_state,
    )

    st.session_state["before"] = save_fields_from_state("space_test")
    render_equipment_save_fields("space_test")
    st.session_state["after"] = save_fields_from_state("space_test")


def test_the_space_layout_save_reads_its_save_fields_from_the_session() -> None:
    """Space 「배치 저장」 은 단추 콜백이라 저장 칸 값을 세션에서 읽는다 — 칸이 없으면
    기본값(질문 1·F6·F2 모두 켬), 칸을 바꾸면 그 값."""
    from capa_simulation.components.equipment_save_fields import EquipmentSaveFields

    app = AppTest.from_function(_fields_app).run()
    assert app.session_state["before"] == EquipmentSaveFields()
    app.checkbox(key="space_test_publish").uncheck()
    app.text_input(key="space_test_saved_by").input(" 홍길동 ")
    app.run()
    assert app.session_state["after"] == EquipmentSaveFields(
        saved_by="홍길동", publish_official=False
    )


def _first_release_fields_app() -> None:
    import streamlit as st

    from capa_simulation.components.equipment_save_fields import render_equipment_save_fields

    st.session_state["fields"] = render_equipment_save_fields("first", release_exists=False)


def test_before_any_release_the_save_fields_say_v1_instead_of_a_publish_checkbox() -> None:
    """발행이 하나도 없으면 저장소가 첫 일정 리비전을 늘 공식 v1 로 낸다 — 끌 수 있는 발행 체크 대신
    그 한 줄이 선다."""
    from capa_simulation.components.equipment_save_fields import (
        FIRST_RELEASE_NOTE,
        EquipmentSaveFields,
    )

    app = _ok(AppTest.from_function(_first_release_fields_app).run())

    assert [box.key for box in app.checkbox] == [
        "first_propagate_units",
        "first_propagate_downtime",
    ]
    assert any(FIRST_RELEASE_NOTE in str(item.value) for item in app.caption)
    assert app.session_state["fields"] == EquipmentSaveFields()


def test_the_layout_editor_turns_off_only_the_new_unit_form_when_asked() -> None:
    """공식 발행 쌍이지만 낡은 세션 — 새 호기 폼(「+ 호기 추가」)만 끄고 까닭을 풍선으로 보인다.
    잠금은 회차마다 받은 값대로 켜고 끈다(`lockNewUnitToggle` — 다시 켜지는지는
    `test_space_layout_overlay_page.test_the_editor_locks_follow_each_run_and_come_back_off`)."""
    editor = (
        PROJECT_ROOT
        / "src"
        / "capa_simulation"
        / "components"
        / "space_layout_editor_assets"
        / "editor.js"
    ).read_text(encoding="utf-8")
    assert "lockNewUnitToggle(addToggle, addForm, NEW_UNIT.disabled)" in editor
    assert "toggle.disabled = Boolean(reason)" in editor
    assert "if (NEW_UNIT.disabled) return" in editor


def test_the_paste_preview_splits_common_and_scenario_cells(tmp_path: Path) -> None:
    """붙여넣기 미리보기는 바뀐 칸을 공통·시나리오로 가르고 새 호기·새 비가동(함께 넣기 후보)을
    센다."""
    from test_equipment_scenario_repository import _with_downtime

    from capa_simulation.components.equipment_data_workspace import paste_split_summary

    saved = _session(_seeded(tmp_path))
    source = (saved.baseline, saved.equipment, saved.downtime)
    assert paste_split_summary(source, source) is None

    master = _set(saved.equipment, "EQ-01", "담당자", "새 담당")
    master = _set(master, "EQ-02", "Qual일정", "2026-09-30")
    master = _set(master, "EQ-02", "시나리오 메모", "셋업 메모")
    master = _with_unit(master, "EQ-NEW", 70)
    downtime = _with_downtime(saved.downtime, "EQ-02", "PM", "2026-09-01")

    assert paste_split_summary(source, (saved.baseline, master, downtime)) == (
        "공통 칸 1 · 시나리오 칸 2 바뀜 · 새 호기 1 · 새 비가동 1(다른 설비 시나리오에 넣을 후보)"
    )
