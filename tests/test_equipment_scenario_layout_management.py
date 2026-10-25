# Purpose: 시나리오 관리 설비 시나리오 구획의 배치 차이 칸·지우기·발행 막힘·되돌리기·옛 판 흔적 글을
# 검증한다.

"""설비 시나리오 2단계 S4 — 시나리오 관리 「설비 시나리오」 구획의 배치 차이 보강(설계
6-5·6-6·14장).

- 시나리오 표 「저장된 배치 차이」(최신의 원시 행)·리비전 표 「배치」(원시 행 — 옛 판이 저장해
  배치가 빠진 리비전은 「옛 판 저장 — rN 배치 빠짐」).
- 「배치 차이 모두 지우기」 — 가정 시나리오 최신에 차이가 있을 때만 서고, 확인 체크 뒤 차이를 비운
  새 리비전을 쓰며 이 세션을 그리로 옮긴다.
- 「공식으로 발행」 — 발행 쓰기와 같은 판정을 미리 읽어 막히면 까닭과 함께 단추를 끄고, 공식과
  같아진 차이만 남았으면 정리 리비전으로 발행한다고 적는다.
- 「이 리비전으로 되돌리기」 확인 글 — 그때 손대지 않은 호기가 지금 공식 자리를 따라 그때와 자리가
  다른 수.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_scenario_repository import (
    OPERATIONS,
    _clone,
    _request,
    _seeded,
    _session,
    _set,
)

from capa_simulation.components.equipment_scenario_management import (
    CLEAR_LAYOUT_BUTTON_KEY,
    CLEAR_LAYOUT_CONFIRM_KEY,
    PUBLISH_BUTTON_KEY,
    REVISION_KEY,
    SCENARIO_KEY,
    clear_layout_lines,
    clear_layout_message,
    clearable_layout,
    layout_trace_sentence,
    layout_trace_sources,
    publish_layout_lines,
    restore_layout_sentence,
    revision_rows,
    stored_layout_words,
)
from capa_simulation.equipment_scenario_activation import SELECTION_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentScenarioSummary,
    EquipmentScheduleRevisionSummary,
    LayoutPublishPreview,
)
from capa_simulation.services.equipment_scenario import ScheduleRestorePreview
from capa_simulation.services.layout_overlay import EMPTY_LAYOUT_DIGEST


@pytest.fixture(autouse=True)
def _fresh_caches() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


def _revision(no: int, layout_hash: str | None = EMPTY_LAYOUT_DIGEST, **values: Any) -> Any:
    return EquipmentScheduleRevisionSummary(
        f"s{no}", "setup", no, "save", datetime(2026, 10, 25), layout_hash=layout_hash, **values
    )


def _scenario(**values: Any) -> EquipmentScenarioSummary:
    defaults: dict[str, Any] = {
        "equipment_scenario_id": "setup",
        "scenario_name": "셋업 실무",
        "status": "ACTIVE",
        "latest_schedule_revision_id": "s5",
        "latest_revision_no": 5,
    }
    return EquipmentScenarioSummary(**{**defaults, **values})


# ---------------------------------------------------------------- 글(순수)


def test_the_tables_name_the_stored_layout_rows_and_the_old_code_traces() -> None:
    """원시 행 수 「호기 n행·요소 n개·이름표 n개」, 옛 판 흔적은 가장 가까운 앞 배치안을
    가리킨다."""
    assert stored_layout_words(3, 1, 0) == "호기 3행·요소 1개"
    assert stored_layout_words(0, 0, 0) == ""
    revisions = [
        _revision(1, None, legacy_revision_id="legacy-1"),
        _revision(2, "d2", layout_unit_count=2),
        _revision(3, None),
        _revision(4, "d4", layout_mark_count=1),
        _revision(5, None),
    ]
    assert layout_trace_sources(revisions) == {3: 2, 5: 4}
    table = revision_rows(revisions, common_numbers={}, official_id=None, official_no=None)
    assert table["배치"].tolist() == [
        "",
        "호기 2행",
        "옛 판 저장 — r2 배치 빠짐",
        "요소 1개",
        "옛 판 저장 — r4 배치 빠짐",
    ]
    sentence = layout_trace_sentence(_scenario(layout_trace_count=2), revisions)
    assert sentence is not None
    assert "「셋업 실무」 r5는 옛 판이 저장해 r4의 가정 배치가 빠졌습니다" in sentence
    assert "r4로 되돌리기" in sentence
    assert "모두 2개" in sentence
    assert layout_trace_sentence(_scenario(), [_revision(1), _revision(2, "d2")]) is None


def test_the_clear_button_belongs_to_assumption_scenarios_with_a_difference() -> None:
    session = type("S", (), {"official_scenario_id": OPERATIONS})()
    assert not clearable_layout(session, _scenario(equipment_scenario_id=OPERATIONS))
    assert not clearable_layout(session, _scenario())
    assert clearable_layout(session, _scenario(latest_layout_unit_count=1))
    assert clearable_layout(session, _scenario(latest_layout_hash="d5"))
    lines = clear_layout_lines(_scenario(latest_layout_unit_count=3, latest_layout_mark_count=1))
    assert "배치 차이(호기 3행·요소 1개)만 비운 새 리비전 r6을 저장합니다" in lines[0]
    assert "r5는 그대로 남습니다" in lines[1]
    created = _revision(6, EMPTY_LAYOUT_DIGEST)
    message = clear_layout_message("셋업 실무", created, moved=True, kept_unsaved=False)
    assert "배치 차이를 모두 지운 r6을 저장했습니다" in message
    assert "이 세션을 r6으로 옮겼습니다." in message
    assert "지울 배치 차이가 없어" in clear_layout_message(
        "셋업 실무", None, moved=False, kept_unsaved=False
    )


def test_the_publish_confirm_reads_the_same_layout_judgment() -> None:
    """설계 6-5 — 막히면 「실효 … — 저장된 차이 m행」 과 빠져나갈 길, 정리면 rN+1 로 발행한다는
    줄."""
    revision = _revision(5, "d5", layout_unit_count=3)
    scenario = _scenario()
    assert publish_layout_lines(scenario, revision, LayoutPublishPreview()) == ([], False)
    lines, blocked = publish_layout_lines(
        scenario,
        revision,
        LayoutPublishPreview(action="blocked", stored_units=3, newest_rows=3, units=2, marks=1),
    )
    assert blocked
    assert "공식과 다른 배치(실효 호기 2대·요소 1개 — 저장된 차이 3행)가 있어" in lines[0]
    assert "「배치 차이 모두 지우기」" in lines[0] and "「여기서 새 시나리오」" in lines[0]
    older, blocked = publish_layout_lines(
        scenario,
        _revision(3),
        LayoutPublishPreview(action="blocked", newest_rows=3, units=2),
    )
    assert blocked and "r3에는 배치 차이가 없지만 최신 r5에 공식과 다른 배치" in older[0]
    clean, blocked = publish_layout_lines(
        scenario, revision, LayoutPublishPreview(action="clean", stored_units=3, newest_rows=3)
    )
    assert not blocked
    assert "공식과 같아진 배치 차이 3행을 정리한 r6으로 발행합니다" in clean[0]


def test_the_restore_confirm_names_units_whose_place_changed_since_then() -> None:
    """검토 F21 — 되살리는 가정 배치에서 그때 손대지 않은 호기는 지금 공식 자리를 따른다."""
    chosen = _revision(2, "d2", layout_unit_count=1)
    moved = ScheduleRestorePreview(layout_unit_rows=1, layout_digest="d", layout_moved_since=4)
    sentence = restore_layout_sentence(chosen, moved, official_scenario=False)
    assert sentence.startswith("r2의 가정 배치(저장된 차이 호기 1행)도 되살립니다.")
    assert "그때와 자리가 다른 호기 4대가 있습니다(이력 「그때 그대로」 와 다름)" in sentence
    same = ScheduleRestorePreview(layout_unit_rows=1, layout_digest="d")
    assert "그때와" not in restore_layout_sentence(chosen, same, official_scenario=False)


# ---------------------------------------------------------------- 구획(AppTest)


_SECTION = """
from pathlib import Path
import capa_simulation.settings as settings
settings.EQUIPMENT_DUCKDB_PATH = Path({path!r})
from capa_simulation.components.equipment_scenario_management import (
    render_equipment_scenario_section,
)
render_equipment_scenario_section()
"""


def _section(tmp_path: Path, scenario_id: str) -> AppTest:
    app = AppTest.from_string(
        _SECTION.format(path=str(tmp_path / "equipment.duckdb")), default_timeout=120
    )
    app.session_state[SELECTION_KEY] = {"scenario_id": scenario_id, "schedule_revision_id": None}
    return app


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _texts(app: AppTest) -> list[str]:
    return [
        str(item.value)
        for kind in ("caption", "info", "warning", "success", "error", "markdown")
        for item in getattr(app, kind)
    ]


def _moved_setup(tmp_path: Path) -> tuple[DuckDBEquipmentRepository, str, str]:
    """「운영 일정」 r1(공식 v1) + 「셋업 실무」 r2 — EQ-01 을 X=50 으로 옮긴 가정 배치."""
    repository = _seeded(tmp_path)
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
    return repository, clone.equipment_scenario_id, saved.schedule.schedule_revision_id


def test_the_section_shows_the_layout_columns_and_blocks_publishing(tmp_path: Path) -> None:
    _, setup, latest = _moved_setup(tmp_path)
    app = _ok(_section(tmp_path, setup).run())
    app.selectbox(key=SCENARIO_KEY).set_value(setup)
    _ok(app.run())

    scenarios = next(frame.value for frame in app.dataframe if "설비 시나리오" in frame.value)
    by_name = dict(zip(scenarios["설비 시나리오"], scenarios["저장된 배치 차이"], strict=True))
    assert by_name == {"운영 일정": "", "셋업 실무": "호기 1행"}
    revisions = next(frame.value for frame in app.dataframe if "리비전명" in frame.value)
    assert revisions["배치"].tolist()[0] == "호기 1행"
    assert app.selectbox(key=REVISION_KEY).value == latest
    publish = next(button for button in app.button if button.key == PUBLISH_BUTTON_KEY)
    assert publish.disabled
    assert any("공식과 다른 배치(실효 호기 1대 — 저장된 차이 1행)가 있어" in t for t in _texts(app))


def test_clearing_the_layout_writes_a_new_revision_and_moves_the_session(tmp_path: Path) -> None:
    repository, setup, latest = _moved_setup(tmp_path)
    app = _ok(_section(tmp_path, setup).run())
    app.selectbox(key=SCENARIO_KEY).set_value(setup)
    _ok(app.run())
    (confirm,) = [box for box in app.checkbox if str(box.key).startswith(CLEAR_LAYOUT_CONFIRM_KEY)]
    clear = next(button for button in app.button if button.key == CLEAR_LAYOUT_BUTTON_KEY)
    assert clear.disabled

    confirm.check().run()
    _ok(app.button(key=CLEAR_LAYOUT_BUTTON_KEY).click().run())

    newest = repository.list_schedule_revisions(setup, limit=1)[0]
    assert (newest.revision_no, newest.origin, newest.layout_unit_count) == (3, "layout_clear", 0)
    assert any("배치 차이를 모두 지운 r3을 저장했습니다" in text for text in _texts(app))
    assert app.session_state[SELECTION_KEY]["schedule_revision_id"] == newest.schedule_revision_id
    # 지운 뒤에는 단추가 없고 발행이 열린다(I2 — 행이 없다).
    assert not [button for button in app.button if button.key == CLEAR_LAYOUT_BUTTON_KEY]
    publish = next(button for button in app.button if button.key == PUBLISH_BUTTON_KEY)
    assert not publish.disabled
    with duckdb.connect(str(repository.database_path), read_only=True) as connection:
        rows = connection.execute(
            "SELECT count(*) FROM equipment_ops.equipment_schedule_layout_unit "
            "WHERE schedule_revision_id = ?",
            [latest],
        ).fetchone()
    assert rows == (1,)
