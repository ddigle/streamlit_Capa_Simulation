# Purpose: 「자동 갱신」 탭의 상태·설정 저장·켤 때 막기·지금 실행·기록 표와 공정 표지를 고정한다.

"""시나리오 관리 「자동 갱신」 탭(`components/auto_official_update_tab.py`).

탭 하나만 AppTest 로 돌린다 — 가짜 BigDataQuery 와 고정 시계는 이 모듈의 칸(`SOURCES`)으로
스크립트에 넘긴다. 사외에서는 BigDataQuery 를 부를 수 없고, 원천은 내장 합성 시드다(확보율은 샘플
관측).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, time
from pathlib import Path

import pytest
from auto_update_fakes import (
    NOW,
    WAFER,
    FakeBigDataQuery,
    catalog_frame,
    fixed_clock,
    new_repository,
    official_w40,
    register_code,
    source_frame,
)
from fragment_browser import install_fragment_browser
from streamlit.testing.v1 import AppTest, element_tree

import capa_simulation.components.write_guard as write_guard
from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.auto_official_update_runner import (
    AutoUpdateSources,
    auto_off_marks,
    run_auto_official_update,
)
from capa_simulation.auto_update_scheduler import ENV_VAR
from capa_simulation.components.auto_official_update_tab import (
    EMPTY,
    RUN_NOW_BUTTON_KEY,
    UNCOUNTED_DEMAND_MARK,
)
from capa_simulation.components.process_picker import auto_off_mark_line, tile_tooltip_text
from capa_simulation.components.required_exclusion_notice import UNCOUNTED_DEMAND_LEAD
from capa_simulation.persistence.models import ScenarioPreset
from capa_simulation.persistence.repository import REVISION_TABLES, DuckDBScenarioRepository
from capa_simulation.services.auto_official_update import (
    MISSING_WEEK_MESSAGE,
    STATUS_PUBLISHED,
    STATUS_RUNNING,
    TRIGGER_MANUAL,
    AutoUpdateConfig,
    auto_off_mark,
)
from capa_simulation.services.process_picker import ProcessPickerItem

# 스크립트가 읽는 가짜 원천. 테스트가 채우고 스크립트가 같은 모듈을 import 해 꺼낸다.
SOURCES: list[AutoUpdateSources] = []

TAB_SCRIPT = """
from pathlib import Path

import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({path!r})

import test_auto_official_update_tab as harness
from auto_update_fakes import fixed_clock

from capa_simulation.components.auto_official_update_tab import render_auto_official_update
from capa_simulation.persistence.cache import get_scenario_repository

render_auto_official_update(
    get_scenario_repository({path!r}),
    sources=harness.SOURCES[0] if harness.SOURCES else None,
    clock=fixed_clock,
)
"""

W41_CATALOG = catalog_frame(("PSM W41", "SIM-W41", "2026-10-12 09:00:00"))


@pytest.fixture(autouse=True)
def _forget_sources() -> Iterator[None]:
    SOURCES.clear()
    yield
    SOURCES.clear()


@pytest.fixture
def database(tmp_path: Path) -> Path:
    return tmp_path / "auto_tab.duckdb"


def _tab(path: Path) -> AppTest:
    app = AppTest.from_string(TAB_SCRIPT.format(path=str(path)), default_timeout=180).run()
    assert not app.exception, [element.message for element in app.exception]
    return app


def _with_w40(path: Path) -> DuckDBScenarioRepository:
    repository = new_repository(path)
    official_w40(repository)
    return repository


def _without_week(path: Path) -> DuckDBScenarioRepository:
    """내장 합성 시드가 공식버전 — 이름에 주차(W##)가 없다."""
    repository = new_repository(path)
    ensure_initial_scenario(repository)
    return repository


def _markdown(app: AppTest) -> str:
    return "\n".join(str(element.value) for element in app.markdown)


def _field(widgets: object, label: str) -> object:
    return next(widget for widget in widgets if widget.label == label)  # type: ignore[attr-defined]


def _submit_settings(app: AppTest) -> AppTest:
    return next(button for button in app.button if button.label == "설정 저장").click().run()


def _alerts(app: AppTest) -> list[tuple[str, str, str]]:
    """본문의 성공·경고 알림을 그린 차례대로 (종류, 아이콘, 글)."""
    return [
        (node.type, node.proto.icon, node.proto.body)
        for node in app.main
        if isinstance(node, (element_tree.Success, element_tree.Warning))
    ]


def _published_alerts(app: AppTest) -> tuple[tuple[str, str, str], ...]:
    """「지금 실행」 발행 회차의 성공 알림과 그 바로 밑 알림."""
    alerts = _alerts(app)
    index = next(
        index
        for index, (kind, _, text) in enumerate(alerts)
        if kind == "success" and "지금 실행 회차 — 등록·발행" in text
    )
    return tuple(alerts[index : index + 2])


# ---------------------------------------------------------------------------
# 지금 상태·기본값
# ---------------------------------------------------------------------------


def test_the_tab_shows_defaults_the_official_week_and_the_opt_in_notice(database: Path) -> None:
    _with_w40(database)

    app = _tab(database)

    assert any(ENV_VAR in str(element.value) for element in app.info)
    text = _markdown(app)
    assert "공식 v1 W40" in text
    assert "꺼짐 · 매일 07:00 · 키워드 「PSM」 · 기준 확보율 80%" in text
    assert "꺼져 있어 돌지 않습니다." in text
    assert _field(app.toggle, "자동 갱신 켜기").value is False  # type: ignore[attr-defined]
    assert _field(app.time_input, "확인 시각").value == time(7, 0)  # type: ignore[attr-defined]
    assert _field(app.text_input, "시뮬레이션명 키워드").value == "PSM"  # type: ignore[attr-defined]
    assert _field(app.number_input, "기준 확보율(%)").value == 80.0  # type: ignore[attr-defined]
    assert "아직 돈 회차가 없습니다." in {str(element.value) for element in app.caption}
    assert not app.error


def test_the_status_line_blocks_the_tildes_of_the_official_release_name(database: Path) -> None:
    """공식버전명은 사람이 지은 글이다 — 「현재 공식버전」 줄(마크다운)에서 「W43~공식~확정안」 의
    가운데가 지움선이 되지 않는다(2026-10-26 리뷰 — 바로 위 두 줄은 막고 이 줄만 날로 실었다)."""
    repository = new_repository(database)
    snapshot = register_code(
        repository, code="SIM-W40", name="PSM W40", registered_at=datetime(2026, 10, 5, 9, 0)
    )
    repository.publish_official_revision(
        snapshot.scenario.scenario_id,
        snapshot.revision.revision_id,
        release_name="W40~공식~확정안",
    )

    text = _markdown(_tab(database))

    assert "공식 v1 W40 · W40\\~공식\\~확정안 (시나리오명에서 읽은 주차)" in text
    assert "W40~공식~확정안" not in text


def test_the_run_result_blocks_the_tildes_of_the_names_in_its_reason(database: Path) -> None:
    """「지금 실행」 결과 알림의 사유는 회차 기록과 같은 글이라 저장한 시나리오 이름을 날로 담는다
    — 알림 상자(마크다운)에서 물결표가 지움선이 되지 않는다. 결과는 알림 칸에 담는 자리
    (`_hold_run_result`)에서 막으므로 끊긴 회차를 기록에서 찾는 길로 잰다(사유 밑 경고도)."""
    from capa_simulation.components.auto_official_update_tab import PENDING_RUN_TOKEN_KEY

    repository, run_id = _cut_off_published_round(database)
    repository.update_auto_official_update_run(
        run_id,
        {
            "reason": "「PSM~W41~X」 을 공식으로 발행했습니다"
            f". {UNCOUNTED_DEMAND_LEAD} — 「공정~표시~D」."
        },
    )
    app = AppTest.from_string(TAB_SCRIPT.format(path=str(database)), default_timeout=180)
    app.session_state[PENDING_RUN_TOKEN_KEY] = "cut0ff"
    app.run()
    assert not app.exception, [element.message for element in app.exception]

    alerts = [text for _, _, text in _alerts(app)]
    assert "지금 실행 회차 — 등록·발행. 「PSM\\~W41\\~X」 을 공식으로 발행했습니다" in alerts
    assert f"{UNCOUNTED_DEMAND_LEAD} — 「공정\\~표시\\~D」." in alerts


def test_a_missing_week_is_a_status_line_while_off(database: Path) -> None:
    """꺼져 있는 동안은 오류 상자가 아니라 상태 한 줄이다 — 켜거나 실행할 때 오류로 막는다."""
    _without_week(database)

    app = _tab(database)

    assert not app.error
    assert "주차 없음" in _markdown(app)
    assert MISSING_WEEK_MESSAGE in _markdown(app)


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------


def test_saving_the_settings_records_what_changed(database: Path) -> None:
    repository = _with_w40(database)
    app = _tab(database)

    _field(app.toggle, "자동 갱신 켜기").set_value(True)  # type: ignore[attr-defined]
    _field(app.time_input, "확인 시각").set_value(time(6, 30))  # type: ignore[attr-defined]
    _field(app.text_input, "시뮬레이션명 키워드").set_value(" PSS ")  # type: ignore[attr-defined]
    _field(app.number_input, "기준 확보율(%)").set_value(75.0)  # type: ignore[attr-defined]
    _field(app.text_input, "바꾼 사람(선택)").set_value("운영 담당")  # type: ignore[attr-defined]
    app = _submit_settings(app)

    assert not app.exception and not app.error
    saved = repository.load_auto_official_update_settings()
    assert saved.version == 1
    assert saved.config == AutoUpdateConfig(
        enabled=True, check_time=time(6, 30), keyword="PSS", threshold=0.75
    )
    assert any("자동 갱신 설정을 저장했습니다" in str(element.value) for element in app.success)
    history = app.dataframe[-1].value
    assert list(history["바꾼 사람"]) == ["운영 담당"]
    assert list(history["바꾼 내용"]) == [
        "자동 갱신 끔 → 켬 · 확인 시각 07:00 → 06:30 · 키워드 PSM → PSS · 기준 확보율 80% → 75%"
    ]
    # 칸이 저장본을 따라온다(키 없는 칸).
    assert _field(app.text_input, "시뮬레이션명 키워드").value == "PSS"  # type: ignore[attr-defined]
    assert "이 실행에서는 돌지 않습니다(실행 줄 허락 없음)." in _markdown(app)


def test_turning_on_without_an_official_week_is_refused(database: Path) -> None:
    repository = _without_week(database)
    app = _tab(database)

    _field(app.toggle, "자동 갱신 켜기").set_value(True)  # type: ignore[attr-defined]
    app = _submit_settings(app)

    assert any(MISSING_WEEK_MESSAGE in str(element.value) for element in app.error)
    assert repository.load_auto_official_update_settings().version == 0
    assert repository.list_auto_official_update_setting_changes() == []


def test_a_change_saved_elsewhere_meanwhile_is_not_overwritten(database: Path) -> None:
    repository = _with_w40(database)
    app = _tab(database)
    settings = repository.load_auto_official_update_settings()
    repository.replace_auto_official_update_settings(
        AutoUpdateConfig(enabled=False, check_time=time(8, 0), keyword="PSM", threshold=0.9),
        expected_version=settings.version,
    )

    _field(app.number_input, "기준 확보율(%)").set_value(70.0)  # type: ignore[attr-defined]
    app = _submit_settings(app)

    assert any("다른 사용자가 먼저" in str(element.value) for element in app.error)
    stored = repository.load_auto_official_update_settings()
    assert (stored.version, stored.config.threshold) == (1, 0.9)


@pytest.mark.parametrize(("window", "trailing"), [(3600.0, True), (0.0, False)])
def test_a_double_press_after_a_change_saved_elsewhere_keeps_the_refusal(
    database: Path, monkeypatch: pytest.MonkeyPatch, window: float, trailing: bool
) -> None:
    """남이 먼저 저장한 뒤 옛 화면에서 「설정 저장」을 빠르게 두 번 누른다(판정 기준과 같은 결함
    — 2026-10-26 E2E). 첫 누름은 거부되지만 그 회차가 편집 시작 version 을 최신으로 올려, 둘째
    누름이 옛 화면의 입력을 든 채 대조를 지나 저장했다. 거부 직후의 둘째 누름은 저장하지 않고 그
    거부를 다시 알린다. 창이 지난 누름은 새 화면을 보고 다시 누른 저장이다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", window)
    repository = _with_w40(database)
    app = _tab(database)
    settings = repository.load_auto_official_update_settings()
    repository.replace_auto_official_update_settings(
        AutoUpdateConfig(enabled=False, check_time=time(8, 0), keyword="PSM", threshold=0.9),
        expected_version=settings.version,
    )

    _field(app.text_input, "시뮬레이션명 키워드").set_value("PSS")  # type: ignore[attr-defined]
    next(button for button in app.button if button.label == "설정 저장").click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert any("다른 사용자가 먼저" in str(element.value) for element in app.error)

    app._run(widget_state=pressed)

    assert not app.exception, [element.message for element in app.exception]
    stored = repository.load_auto_official_update_settings()
    if trailing:
        errors = [str(element.value) for element in app.error]
        assert len(errors) == 1 and "다른 사용자가 먼저" in errors[0], errors
        assert not app.success
        assert "바뀐 값이 없습니다." not in [str(element.value) for element in app.info]
        assert (stored.version, stored.config.keyword) == (1, "PSM")
    else:
        assert not app.error, [str(element.value) for element in app.error]
        assert (stored.version, stored.config.keyword) == (2, "PSS")


def test_a_single_press_after_a_held_double_press_saves_the_settings(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """남의 저장 뒤 옛 화면 두 번 누름이 둘 다 거부된 다음, 최신 화면을 보고 한 번 누른 저장은
    저장된다(2026-10-27 E2E — 판정 기준과 같은 꼴). 둘째 누름이 거부 뒤 회차를 끊고 거부 표지에
    걸려 끝나도 그 회차가 그린 최신 version 을 본 값으로 적는다 — 적지 않으면 창 뒤의 한 번 누름이
    「편집 시작 v0 · 지금 v1」 로 또 거부됐다. 끊긴 회차는 본 version 을 옛 값으로 되살려 흉내
    낸다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    repository = _with_w40(database)
    app = _tab(database)
    settings = repository.load_auto_official_update_settings()
    repository.replace_auto_official_update_settings(
        AutoUpdateConfig(enabled=False, check_time=time(8, 0), keyword="PSM", threshold=0.9),
        expected_version=settings.version,
    )

    _field(app.text_input, "시뮬레이션명 키워드").set_value("PSS")  # type: ignore[attr-defined]
    next(button for button in app.button if button.label == "설정 저장").click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert any("다른 사용자가 먼저" in str(element.value) for element in app.error)

    app.session_state["auto_official_update_settings_base_version"] = settings.version
    app._run(widget_state=pressed)
    assert any("다른 사용자가 먼저" in str(element.value) for element in app.error)
    assert repository.load_auto_official_update_settings().version == 1

    # 거부 표지의 창이 지났다 — 최신 화면을 보고 다시 누른 저장이다.
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    _field(app.text_input, "시뮬레이션명 키워드").set_value("PSX")  # type: ignore[attr-defined]
    app = _submit_settings(app)

    assert not app.exception, [element.message for element in app.exception]
    assert not app.error, [str(element.value) for element in app.error]
    stored = repository.load_auto_official_update_settings()
    assert (stored.version, stored.config.keyword) == (2, "PSX")


def test_an_invalid_keyword_is_reported_without_saving(database: Path) -> None:
    repository = _with_w40(database)
    app = _tab(database)

    _field(app.text_input, "시뮬레이션명 키워드").set_value("   ")  # type: ignore[attr-defined]
    app = _submit_settings(app)

    assert any("키워드는 비어 있을 수 없습니다" in str(element.value) for element in app.error)
    assert repository.load_auto_official_update_settings().version == 0


# ---------------------------------------------------------------------------
# 지금 실행
# ---------------------------------------------------------------------------


def test_run_now_registers_judges_publishes_and_lists_the_round(database: Path) -> None:
    repository = _with_w40(database)
    fake = FakeBigDataQuery(
        W41_CATALOG, frames={"SIM-W41": source_frame(zero_available=[(WAFER, 202603)])}
    )
    SOURCES.append(fake.sources)
    app = _tab(database)

    app = app.button(key=RUN_NOW_BUTTON_KEY).click().run()

    assert not app.exception and not app.error
    assert any("지금 실행 회차 — 등록·발행" in str(element.value) for element in app.success)
    # 소요대수에 들지 않은 수요가 없으면 성공 알림만 뜬다 — 밑에 빈 경고를 그리지 않는다.
    assert not [text for _, _, text in _alerts(app) if UNCOUNTED_DEMAND_LEAD in text]
    release = repository.latest_official_release()
    assert release is not None and release.release_no == 2
    runs = repository.list_auto_official_update_runs()
    assert [(run.trigger_kind, run.status) for run in runs] == [(TRIGGER_MANUAL, STATUS_PUBLISHED)]

    history = app.dataframe[0].value
    # 「경고」 는 「결과」 바로 뒤다 — 맨 끝 「사유」 가 잘려도 보인다.
    assert list(history.columns) == [
        "시작",
        "방식",
        "결과",
        "경고",
        "받은 코드",
        "등록 시나리오",
        "자동 off",
        "이어받은 수동 off",
        "발행",
        "기준",
        "사유",
    ]
    row = history.iloc[0]
    assert row["시작"] == format(NOW, "%Y-%m-%d %H:%M")
    assert (row["방식"], row["결과"], row["받은 코드"]) == ("지금 실행", "등록·발행", "W41 SIM-W41")
    assert row["경고"] == EMPTY
    assert row["발행"] == "공식 v2"
    assert row["자동 off"] == f"1공정 · {WAFER} 자동 off(확보율 0%, 26.03)"
    assert row["이어받은 수동 off"] == "0공정"
    offs = app.dataframe[1].value
    assert list(offs["공정"]) == [WAFER]
    assert list(offs["표지"]) == ["자동 off(확보율 0%, 26.03)"]
    # 현재 공식버전이 새 주차로 바뀌었다.
    assert "공식 v2 W41" in _markdown(app)


def test_run_now_shows_uncounted_demand_as_a_warning_under_the_success(database: Path) -> None:
    """발행한 회차의 소요대수에 들지 않은 수요 경고는 화면 발행처럼 성공 알림 밑에 따로 뜬다.

    실행 기록의 사유(기록 표의 칸)에는 발행 줄 뒤에 이어 적힌 그대로 남고, 「경고」 칸에 표지가
    선다.
    """
    repository = _with_w40(database)
    fake = FakeBigDataQuery(W41_CATALOG, frames={"SIM-W41": source_frame(blank_first_plan=True)})
    SOURCES.append(fake.sources)
    app = _tab(database)

    app = app.button(key=RUN_NOW_BUTTON_KEY).click().run()

    assert not app.exception and not app.error
    head = (
        "공식 v2 발행 · W41 SIM-W41 · "
        "자동 갱신 · 기준 확보율 80% · off 0공정 · 이어받은 수동 off 0공정"
    )
    (success, warning) = _published_alerts(app)
    assert success == ("success", ":material/publish:", f"지금 실행 회차 — 등록·발행. {head}")
    kind, icon, text = warning
    assert (kind, icon) == ("warning", ":material/warning:")
    assert text.startswith(f"{UNCOUNTED_DEMAND_LEAD}(시나리오 전체 기간) — ")
    assert "생산수량이 비어 계획 없음으로 본 계획 1건" in text
    run = repository.list_auto_official_update_runs()[0]
    assert run.reason == f"{head}. {text}"
    row = app.dataframe[0].value.iloc[0]
    assert row["사유"] == run.reason
    assert row["경고"] == UNCOUNTED_DEMAND_MARK


def test_run_now_without_an_official_week_does_nothing(database: Path) -> None:
    repository = _without_week(database)
    fake = FakeBigDataQuery(W41_CATALOG)
    SOURCES.append(fake.sources)
    app = _tab(database)

    app = app.button(key=RUN_NOW_BUTTON_KEY).click().run()

    assert any(MISSING_WEEK_MESSAGE in str(element.value) for element in app.error)
    assert repository.list_auto_official_update_runs() == []
    assert fake.catalog_windows == []


def test_run_now_with_nothing_new_lists_a_skip(database: Path) -> None:
    repository = _with_w40(database)
    SOURCES.append(FakeBigDataQuery(catalog_frame()).sources)
    app = _tab(database)

    app = app.button(key=RUN_NOW_BUTTON_KEY).click().run()

    assert any("건너뜀" in str(element.value) for element in app.info)
    row = app.dataframe[0].value.iloc[0]
    assert (row["결과"], row["경고"]) == ("건너뜀", EMPTY)
    assert repository.latest_official_release().release_no == 1  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# HOME 공정 필터 표지
# ---------------------------------------------------------------------------


def test_marks_follow_the_filtered_revision_and_its_children(tmp_path: Path) -> None:
    repository = _with_w40(tmp_path / "marks.duckdb")
    fake = FakeBigDataQuery(
        W41_CATALOG, frames={"SIM-W41": source_frame(zero_available=[(WAFER, 202603)])}
    )
    result = run_auto_official_update(
        repository, trigger=TRIGGER_MANUAL, sources=fake.sources, clock=fixed_clock
    )
    run = result.run
    assert run is not None and run.filtered_revision_id is not None
    scenario_id = str(run.created_scenario_id)
    expected = {WAFER: "자동 off(확보율 0%, 26.03)"}

    assert auto_off_marks(repository, scenario_id, run.filtered_revision_id) == expected
    # 리비전 1(원천 그대로)은 자동 off 전이다.
    assert auto_off_marks(repository, scenario_id, str(run.base_revision_id)) == {}
    # 사람이 리비전 2 에서 리비전 3 을 저장해도 근거는 남는다.
    filtered = repository.load_revision(run.filtered_revision_id)
    child = repository.save_revision(
        scenario_id,
        {name: filtered.tables[name] for name in REVISION_TABLES},
        ScenarioPreset(
            start_month=filtered.preset.start_month,
            end_month=filtered.preset.end_month,
            included_processes=filtered.preset.included_processes,
            secure_threshold=filtered.preset.secure_threshold,
            warning_threshold=filtered.preset.warning_threshold,
        ),
        revision_name="사람 리비전",
        parent_revision_id=run.filtered_revision_id,
    )
    assert auto_off_marks(repository, scenario_id, child.revision.revision_id) == expected


def test_the_mark_text_and_the_picker_line() -> None:
    assert auto_off_mark(0.724, 202611) == "자동 off(확보율 72.4%, 26.11)"
    assert auto_off_mark(0.72, 202611) == "자동 off(확보율 72%, 26.11)"
    # 판정은 원값 「미만」이다 — 기준 80% 에서 꺼진 79.96% 가 「80%」로 보이지 않게 내린다.
    assert auto_off_mark(0.7996, 202611) == "자동 off(확보율 79.9%, 26.11)"
    assert auto_off_mark(None, None) == "자동 off"
    item = ProcessPickerItem(
        process=WAFER,
        minimum_rate=0.5,
        minimum_month=202603,
        valid_month_count=3,
        group="shortfall",
    )
    marks = {WAFER: "자동 off(확보율 50%, 26.03)"}

    assert auto_off_mark_line([item], marks, str) == (
        f"공식버전 자동 갱신이 뺀 공정 1개 · {WAFER} 자동 off(확보율 50%, 26.03)"
    )
    assert auto_off_mark_line([item], {}, str) is None
    # 사람이 다시 켠 공정은 지금 빠져 있지 않다 — 줄에서 세지 않는다.
    assert auto_off_mark_line([item], marks, str, {WAFER}) is None
    tooltip = tile_tooltip_text(item, WAFER, enabled=False, mark=marks[WAFER])
    assert tooltip.endswith("공식버전 자동 갱신: 자동 off(확보율 50%, 26.03)")


def _picker_app() -> None:
    import streamlit as st

    from capa_simulation.components.process_picker import render_process_picker as render
    from capa_simulation.services.process_picker import ProcessPickerItem as Item

    items = [
        Item("A", 0.5, 202603, 3, "shortfall"),
        Item("B", 1.5, 202603, 3, "sufficient"),
    ]
    render(
        items,
        set(st.session_state.get("picker_selected", ["B"])),
        format_func=str,
        on_toggle=lambda process: None,
        marks={"A": "자동 off(확보율 50%, 26.03)"},
    )


def test_the_popup_shows_the_mark_and_an_auto_icon_on_the_off_tile() -> None:
    app = AppTest.from_function(_picker_app).run()

    assert not app.exception
    captions = [str(element.value) for element in app.caption]
    assert "공식버전 자동 갱신이 뺀 공정 1개 · A 자동 off(확보율 50%, 26.03)" in captions
    icons = {button.label: button.proto.icon for button in app.button}
    assert icons == {"A": ":material/auto_mode:", "B": ":material/check:"}


def test_the_tab_frames_have_the_documented_columns() -> None:
    """빈 기록에서도 표 머리가 선다(사내 첫 실행 전 화면)."""
    from capa_simulation.components.auto_official_update_tab import (
        off_process_frame,
        setting_history_frame,
    )
    from capa_simulation.components.process_labels import ProcessLabels

    assert list(off_process_frame([], [], ProcessLabels()).columns) == [
        "회차 시작",
        "공정",
        "구분",
        "표지",
        "최저 확보율",
        "그 달",
        "리비전 2 저장",
    ]
    assert list(setting_history_frame([]).columns) == ["시각", "바꾼 사람", "바꾼 내용", "판"]


def test_only_a_published_round_with_the_trailing_warning_gets_the_mark() -> None:
    """표지는 발행한 회차의 사유 끝에 이어 적힌 경고에만 선다 — 발행 못 한 회차의 사유에 그 문장
    머리가 들어 있어도(오류 글이 경고를 인용해도) 표지를 세우지 않는다."""
    from capa_simulation.components.auto_official_update_tab import run_history_frame
    from capa_simulation.components.process_labels import ProcessLabels
    from capa_simulation.persistence.models import AutoOfficialUpdateRun
    from capa_simulation.services.auto_official_update import STATUS_ERROR, RunStatus

    plain = "공식 v2 발행 · W41 SIM-W41 · 자동 갱신"
    warned = f"{plain}. {UNCOUNTED_DEMAND_LEAD}(시나리오 전체 기간) — 1건."

    def run(run_id: str, status: RunStatus, reason: str) -> AutoOfficialUpdateRun:
        return AutoOfficialUpdateRun(
            run_id=run_id,
            run_key=run_id,
            trigger_kind=TRIGGER_MANUAL,
            run_date=NOW.date(),
            status=status,
            stage="DONE",
            started_at=NOW,
            finished_at=NOW,
            keyword="PSM",
            threshold=0.8,
            settings_version=1,
            reason=reason,
        )

    frame = run_history_frame(
        [
            run("warned", STATUS_PUBLISHED, warned),
            run("plain", STATUS_PUBLISHED, plain),
            run("error", STATUS_ERROR, warned),
        ],
        [],
        ProcessLabels(),
    )

    assert list(frame["경고"]) == [UNCOUNTED_DEMAND_MARK, EMPTY, EMPTY]
    assert list(frame["사유"]) == [warned, plain, warned]


# ---------------------------------------------------------------------------
# 지금 상태의 다음 실행·멈춤 경고·끊긴 결과 알림
# ---------------------------------------------------------------------------


def test_the_next_run_skips_to_tomorrow_once_today_is_claimed() -> None:
    from capa_simulation.components.auto_official_update_tab import next_run_line

    config = AutoUpdateConfig(enabled=True, check_time=time(9, 0), keyword="PSM", threshold=0.8)

    assert next_run_line(config, True, NOW) == "2026-10-15 09:00"
    assert next_run_line(config, True, NOW, claimed_today=True) == (
        "2026-10-16 09:00 (오늘 회차는 이미 돌았습니다)"
    )
    later = AutoUpdateConfig(enabled=True, check_time=time(6, 0), keyword="PSM", threshold=0.8)
    assert next_run_line(later, True, NOW, claimed_today=True) == "2026-10-16 06:00"


def test_a_long_round_or_a_silent_thread_is_warned() -> None:
    from datetime import timedelta

    from capa_simulation.auto_update_scheduler import SchedulerStatus, TickOutcome
    from capa_simulation.components.auto_official_update_tab import scheduler_stall_message

    def status(kind: str, at: object) -> SchedulerStatus:
        return SchedulerStatus(
            started_at=NOW,
            last_tick_at=at,  # type: ignore[arg-type]
            last_outcome=TickOutcome(kind, at),  # type: ignore[arg-type]
            pending_day=None,
            alive=True,
            tick_seconds=30.0,
        )

    assert scheduler_stall_message(status("running", NOW), NOW + timedelta(minutes=5)) is None
    long_run = scheduler_stall_message(status("running", NOW), NOW + timedelta(minutes=45))
    assert long_run is not None and "45분째 도는 중" in long_run
    assert scheduler_stall_message(status("waiting", NOW), NOW + timedelta(seconds=90)) is None
    silent = scheduler_stall_message(status("waiting", NOW), NOW + timedelta(minutes=5))
    assert silent is not None and "멈춰 있습니다" in silent


def test_a_run_result_cut_off_by_a_rerun_is_found_by_its_token(database: Path) -> None:
    """「지금 실행」 도중 다른 칸을 눌러 결과 알림이 끊겨도 다음 회차가 기록에서 찾아 보인다."""
    from capa_simulation.components.auto_official_update_tab import PENDING_RUN_TOKEN_KEY

    repository = _with_w40(database)
    run_auto_official_update(
        repository,
        trigger=TRIGGER_MANUAL,
        sources=FakeBigDataQuery(catalog_frame()).sources,
        clock=fixed_clock,
        manual_token="cut0ff",
    )
    app = AppTest.from_string(TAB_SCRIPT.format(path=str(database)), default_timeout=180)
    app.session_state[PENDING_RUN_TOKEN_KEY] = "cut0ff"

    app = app.run()

    assert not app.exception
    assert any("지금 실행 회차 — 건너뜀" in str(element.value) for element in app.info)
    assert PENDING_RUN_TOKEN_KEY not in app.session_state


def test_a_cut_off_published_round_still_shows_its_warning_apart(database: Path) -> None:
    """기록에서 찾은 발행 회차도 기록 한 칸의 사유를 갈라 경고를 성공 알림 밑에 따로 띄운다."""
    from capa_simulation.components.auto_official_update_tab import PENDING_RUN_TOKEN_KEY

    repository = _with_w40(database)
    run_auto_official_update(
        repository,
        trigger=TRIGGER_MANUAL,
        sources=FakeBigDataQuery(
            W41_CATALOG, frames={"SIM-W41": source_frame(blank_first_plan=True)}
        ).sources,
        clock=fixed_clock,
        manual_token="cut0ff",
    )
    app = AppTest.from_string(TAB_SCRIPT.format(path=str(database)), default_timeout=180)
    app.session_state[PENDING_RUN_TOKEN_KEY] = "cut0ff"

    app = app.run()

    assert not app.exception
    (success, warning) = _published_alerts(app)
    assert UNCOUNTED_DEMAND_LEAD not in success[2]
    assert warning[0] == "warning" and warning[2].startswith(UNCOUNTED_DEMAND_LEAD)


def _cut_off_published_round(path: Path) -> tuple[DuckDBScenarioRepository, str]:
    """표 `cut0ff` 로 발행까지 끝낸 「지금 실행」 회차(소요대수에 들지 않은 수요 경고가 붙는다)와 그
    실행 id. 시험은 상태 칸만 「실행 중」으로 되돌려 아직 도는 회차를 흉내 낸다."""
    repository = _with_w40(path)
    run_auto_official_update(
        repository,
        trigger=TRIGGER_MANUAL,
        sources=FakeBigDataQuery(
            W41_CATALOG, frames={"SIM-W41": source_frame(blank_first_plan=True)}
        ).sources,
        clock=fixed_clock,
        manual_token="cut0ff",
    )
    run = repository.find_manual_auto_official_update_run("cut0ff")
    assert run is not None and run.status == STATUS_PUBLISHED
    return repository, run.run_id


def _running_notices(app: AppTest) -> list[str]:
    return [
        str(element.proto.body)
        for element in app.info
        if "아직 도는 중" in str(element.value) and element.proto.icon == ":material/hourglass_top:"
    ]


def test_a_cut_off_round_still_running_keeps_its_token_and_shows_the_result_once_done(
    database: Path,
) -> None:
    """회차를 돌던 실행이 다른 칸 클릭으로 끊기면(`runner.fastReruns`) 새 실행이 먼저 보는 것은 아직
    「실행 중」인 기록이다. 그때 표를 지우지 않고 「도는 중」 안내를 두어야, 회차가 끝난 뒤의 실행이
    결과 알림과 따로 띄운 경고를 보인다."""
    from capa_simulation.components.auto_official_update_tab import PENDING_RUN_TOKEN_KEY

    repository, run_id = _cut_off_published_round(database)
    repository.update_auto_official_update_run(run_id, {"status": STATUS_RUNNING})
    app = AppTest.from_string(TAB_SCRIPT.format(path=str(database)), default_timeout=180)
    app.session_state[PENDING_RUN_TOKEN_KEY] = "cut0ff"

    app = app.run()

    assert not app.exception
    assert len(_running_notices(app)) == 1
    assert app.session_state[PENDING_RUN_TOKEN_KEY] == "cut0ff"
    assert not [alert for alert in _alerts(app) if alert[0] == "success"]

    repository.update_auto_official_update_run(run_id, {"status": STATUS_PUBLISHED})
    app = app.run()

    assert not app.exception
    assert not _running_notices(app)
    (success, warning) = _published_alerts(app)
    assert warning[0] == "warning" and warning[2].startswith(UNCOUNTED_DEMAND_LEAD)
    assert PENDING_RUN_TOKEN_KEY not in app.session_state


def test_the_running_notice_polls_and_hands_a_finished_round_to_the_whole_app(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「도는 중」 안내는 `run_every` 프래그먼트다 — 가만히 두어도 그 프래그먼트만 다시 돌며 기록을
    본다. 아직 돌면 프래그먼트만 돌고 끝이고, 끝났으면 앱 전체를 다시 돌려 결과 알림이 뜬다(끊긴
    실행은 다시 돌지 않아, 이것이 없으면 「도는 중」 이 다음 클릭까지 남았다)."""
    from capa_simulation.components.auto_official_update_tab import (
        PENDING_RUN_TOKEN_KEY,
        RUN_POLL_FRAGMENT_KEY,
    )

    browser = install_fragment_browser(monkeypatch)
    repository, run_id = _cut_off_published_round(database)
    repository.update_auto_official_update_run(run_id, {"status": STATUS_RUNNING})
    app = AppTest.from_string(TAB_SCRIPT.format(path=str(database)), default_timeout=180)
    app.session_state[PENDING_RUN_TOKEN_KEY] = "cut0ff"
    app = app.run()
    assert not app.exception
    poll = browser.fragment_keyed(RUN_POLL_FRAGMENT_KEY)

    browser.fragment_queue = [poll]
    app = app.run()
    assert not app.exception
    assert browser.started == [[poll]]
    assert len(_running_notices(app)) == 1
    assert app.session_state[PENDING_RUN_TOKEN_KEY] == "cut0ff"

    repository.update_auto_official_update_run(run_id, {"status": STATUS_PUBLISHED})
    app = app.run()

    assert not app.exception
    assert browser.started == [[poll], []]
    (success, warning) = _published_alerts(app)
    assert warning[0] == "warning" and warning[2].startswith(UNCOUNTED_DEMAND_LEAD)
    assert PENDING_RUN_TOKEN_KEY not in app.session_state
