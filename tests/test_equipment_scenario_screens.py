# Purpose: 설비 시나리오 화면(탭·일정 없음·미확인·잠금·기준선·Space·상세·머리 띠)을 검증한다.

"""설비 시나리오 1단계의 화면 몫(설계 5·6장 — 세션·화면 시험).

- 가용설비 현황: 「설비 시나리오」 탭(표·복제·이름·발행·이어 쓰기), 「일정 없음 n대」, 가정 설비
  시나리오의 미확인 = 공식 일정 기준(Main·RawData 일정 확인 목록), Preference(공용 Cut-off) 잠금.
- 필요 단축 일정: 기준선 저장은 공식 발행 쌍에서만(거부 까닭 둘), 기준선 머리의 설비 시나리오 출처,
  진척 비교 머리, 카드 링크 `eq`.
- 공정 Capa 상세: HOME 칸 방문은 ◀▶ 뒤에도 공식(방문 기준 칸), 잠근 줄, 카드 `eq` 가 다르면 띠 꼬리.
- Space: 가정이면 배치 편집이 잠기고 「공식으로 바꾸기」, 공식 일정 없음 호기는 그리지 않음.
- 머리 띠: 아래 줄 끝 「설비 시나리오 · 운영 일정 · r1 · 공식 v1」(Space 「(고정)」).
"""

from __future__ import annotations

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

from capa_simulation.components.app_header import equipment_header_suffix
from capa_simulation.components.equipment_data_workspace import official_confirmation_master
from capa_simulation.components.equipment_scenario_management import (
    CLONE_BUTTON_KEY,
    CLONE_NAME_KEY,
    CONTINUE_BUTTON_KEY,
    PUBLISH_BUTTON_KEY,
    SCENARIO_KEY,
    publish_preview,
)
from capa_simulation.components.equipment_scenario_status import (
    EQUIPMENT_SCENARIO_FIELD_KEY,
    PREFERENCE_LOCK_MESSAGE,
    baseline_equipment_refusal,
    shortening_equipment_basis,
    unscheduled_notice,
)
from capa_simulation.equipment_scenario_activation import SELECTION_KEY, EquipmentSession
from capa_simulation.navigation import (
    AVAILABLE_EQUIPMENT_STATUS,
    EQUIPMENT_PREFERENCE_TAB,
    EQUIPMENT_SCENARIO_TAB,
    EQUIPMENT_TAB_KEY,
    PROCESS_CAPA_DETAIL,
    SPACE_STATUS,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentRelease,
    EquipmentScenarioCatalog,
    EquipmentScenarioSummary,
    EquipmentScheduleRevisionSummary,
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


def test_the_header_suffix_follows_the_badge_order_and_space_is_fixed() -> None:
    label = {
        "scenario_name": "운영 일정",
        "revision_no": 12,
        "latest_revision_no": 14,
        "release_no": 3,
        "official_pair": True,
        "stale": True,
    }
    assert equipment_header_suffix(label) == "설비 시나리오 · 운영 일정 · r12 · 공식 v3"
    assert (
        equipment_header_suffix(label, fixed=True)
        == "설비 시나리오 · 운영 일정 · r12 · 공식 v3 (고정)"
    )
    assert equipment_header_suffix(label, unsaved=True) == (
        "설비 시나리오 · 운영 일정 · r12 · 미저장 변경"
    )
    stale = {**label, "official_pair": False}
    assert equipment_header_suffix(stale) == "설비 시나리오 · 운영 일정 · r12 · 최신 r14 있음"
    saved = {**stale, "stale": False}
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
    assert lines[1] == "r3 은 「셋업 실무」 의 최신(r4)이 아닙니다."


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
    """설비 화면 첫 회차부터 머리 띠 아래 줄 끝에 설비 시나리오가 선다(한 회차 늦지 않음). Space 는
    「(고정)」."""
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
    assert "설비 시나리오 · 운영 일정 · r1 · 공식 v1 (고정)" in _header_bodies(app)[-1]


def test_the_scenario_tab_clones_publishes_and_the_session_stays_pinned(
    _shell: AppTest, tmp_path: Path
) -> None:
    app = _ok(_shell.run())
    app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path)
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_SCENARIO_TAB
    _ok(app.run())
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
    field = _field(app)
    assert field is not None and field.label == "운영 일정 · r1"


def test_preference_is_read_only_on_an_assumption_and_open_on_the_official(
    _shell: AppTest, tmp_path: Path
) -> None:
    clone = _clone(_repository(tmp_path))
    app = _ok(_shell.run())
    app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path)
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_PREFERENCE_TAB
    _ok(app.run())
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
    「일정 없음 1대」 를 알리고, Space(공식)는 그 호기를 그린다(공식에는 일정이 있다)."""
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


def test_space_shows_the_official_and_locks_editing_on_an_assumption(
    _shell: AppTest, tmp_path: Path
) -> None:
    """가정 설비 시나리오면 Space 배치 편집이 잠기고 「공식으로 바꾸기」 가 선다. 공식 일정이 없는
    호기(가정에만 넣은 호기)는 그리지 않고 「공식 일정 없음 1대」 를 알린다. 바꾸면 세션이 공식이
    된다."""
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
    assert any("배치 편집은 공식 설비 시나리오(운영 일정 · r1)에서 합니다" in t for t in texts)
    assert any("공식 일정 없음 1대" in text for text in texts)
    switch = app.button(key="space_switch_to_official")
    assert not switch.disabled
    switch.click()
    _ok(app.run())
    assert app.session_state[SELECTION_KEY]["scenario_id"] == OPERATIONS
    assert not any("배치 편집은 공식 설비 시나리오" in text for text in _texts(app))


def test_a_home_visit_to_the_detail_stays_official_and_locks_the_row(
    _shell: AppTest, tmp_path: Path
) -> None:
    """세션이 가정(셋업 실무)이어도 HOME 칸으로 들어온 공정 Capa 상세는 공식이고 줄이 잠긴다. 같은
    화면에서 다시 돌아도(◀▶ 와 같은 회차) 공식이고, 사이드바로 새로 들어오면 세션을 따른다."""
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
    assert field.label == "운영 일정 · r1 (HOME 칸에서 들어온 방문)"

    _ok(app.run())
    field = _field(app)
    assert field is not None and field.disabled and "HOME 칸" in field.label

    _ok(app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path).run())
    _ok(app.switch_page(PROCESS_CAPA_DETAIL.path).run())
    field = _field(app)
    assert field is not None and not field.disabled and field.label == "셋업 실무 · r1"
    assert PROCESS_DETAIL_EQUIPMENT_BASIS_KEY not in app.session_state


def test_a_legacy_trace_warns_and_the_tab_continues_writing(
    _shell: AppTest, tmp_path: Path
) -> None:
    """옛 배포가 0027 경계 뒤에 계약 v3 리비전을 남기면 화면 맨 위에 경고, 설비 시나리오 탭의
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
    app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path)
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_SCENARIO_TAB
    _ok(app.run())
    assert any("옛 배포로 저장한 설비 리비전 1개" in str(item.value) for item in app.warning)

    app.button(key=CONTINUE_BUTTON_KEY).click()
    _ok(app.run())
    assert repository.legacy_trace_count() == 0
    assert not any("옛 배포로 저장한 설비 리비전" in str(item.value) for item in app.warning)


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


def test_the_layout_editor_turns_off_only_the_new_unit_form_when_asked() -> None:
    """공식 발행 쌍이지만 낡은 세션 — 새 호기 폼(「+ 호기 추가」)만 끄고 까닭을 풍선으로 보인다."""
    editor = (
        PROJECT_ROOT
        / "src"
        / "capa_simulation"
        / "components"
        / "space_layout_editor_assets"
        / "editor.js"
    ).read_text(encoding="utf-8")
    assert "if (NEW_UNIT.disabled) {\n    addToggle.disabled = true" in editor
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
