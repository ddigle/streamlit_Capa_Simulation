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
    publish_result_message,
    restore_layout_sentence,
    revision_rows,
    stored_layout_words,
)
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.equipment_scenario_activation import SELECTION_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentScenarioSummary,
    EquipmentScheduleRevisionSummary,
    LayoutPublishPreview,
)
from capa_simulation.services.equipment_scenario import (
    ScheduleRestorePreview,
    restore_writes_nothing,
)
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
        LayoutPublishPreview(action="blocked", newest_rows=3, is_newest=False, newest_units=2),
    )
    assert blocked and "r3에는 배치 차이가 없지만 최신 r5에 공식과 다른 배치" in older[0]
    assert "(실효 호기 2대 — 저장된 차이 3행)" in older[0]
    clean, blocked = publish_layout_lines(
        scenario, revision, LayoutPublishPreview(action="clean", stored_units=3, newest_rows=3)
    )
    assert not blocked
    assert "공식과 같아진 배치 차이 3행을 정리한 r6으로 발행합니다" in clean[0]


def test_an_old_revisions_publish_block_names_only_real_differences_and_working_ways_out() -> None:
    """S4 리뷰 — 옛 리비전의 막힘 글은 실제로 공식과 다른 쪽만 「실효」 로 적고, 옛 리비전에서는
    서지 않거나 소용없는 「배치 차이 모두 지우기」 대신 되돌린 뒤 지우기·최신 발행을 안내한다."""
    scenario = _scenario()
    # 옛 r2 에 공식과 다른 배치가 있다 — 최신만 비우는 지우기로는 풀리지 않는다.
    real, blocked = publish_layout_lines(
        scenario,
        _revision(2),
        LayoutPublishPreview(action="blocked", stored_units=1, is_newest=False, units=1),
    )
    assert blocked
    assert "r2에는 공식과 다른 배치(실효 호기 1대 — 저장된 차이 1행)가 있어" in real[0]
    assert "「배치 차이 모두 지우기」(최신만 비웁니다)로는 풀리지 않습니다" in real[0]
    assert "r2를 고르고 「이 리비전으로 되돌리기」 로 새 최신을 만든 뒤" in real[0]
    # 옛 r2 에 남은 행이 지금 공식과 같다(정리 발행 뒤의 옛 리비전) — 「공식과 다른 배치」 가
    # 아니다.
    same, blocked = publish_layout_lines(
        scenario,
        _revision(2),
        LayoutPublishPreview(action="blocked", stored_units=1, is_newest=False),
        official=True,
    )
    assert blocked
    assert "공식과 다른 배치" not in same[0]
    assert "r2에 저장된 배치 차이 1행은 지금 공식과 같아졌지만" in same[0]
    assert "「배치 차이 모두 지우기」" not in same[0]
    assert "「이 리비전으로 되돌리기」" in same[0]
    # 고른 r3 에는 없고 최신 r5 에 공식과 같은 행만 남았다.
    newest_same, blocked = publish_layout_lines(
        scenario,
        _revision(3),
        LayoutPublishPreview(action="blocked", newest_rows=2, is_newest=False),
    )
    assert blocked and "공식과 다른 배치" not in newest_same[0]
    assert "최신 r5에 저장된 배치 차이 2행(지금 공식과 같음)이 남아 있어" in newest_same[0]
    assert "최신 r5를 발행하세요" in newest_same[0]


def test_a_deleted_units_difference_is_not_called_one_that_caught_up_with_the_official() -> None:
    """E2E r3 — 저장된 배치 차이가 공통 대장에서 지운 호기의 것이면 정리 발행 확인 글·옛 리비전
    막힘 글·발행 뒤 알림이 그 행을 「공식과 같아진」 차이라 하지 않고 「지운 호기의 배치 차이」 로
    따로 말한다."""
    scenario = _scenario()
    revision = _revision(5, "d5", layout_unit_count=1)
    deleted, blocked = publish_layout_lines(
        scenario,
        revision,
        LayoutPublishPreview(action="clean", stored_units=1, newest_rows=1, orphan_units=1),
    )
    assert not blocked
    assert (
        "r5의 배치 차이(호기 1행)는 공통 대장에서 지운 호기의 것입니다 — 지운 호기의 배치 차이 "
        "1행을 정리한 r6으로 발행합니다" in deleted[0]
    ), deleted
    assert "공식과 같아" not in deleted[0]
    mixed, _ = publish_layout_lines(
        scenario,
        _revision(5, "d5", layout_unit_count=3),
        LayoutPublishPreview(action="clean", stored_units=3, newest_rows=3, orphan_units=1),
    )
    assert (
        "는 지금 공식과 같아졌거나 공통 대장에서 지운 호기의 것입니다 — 공식과 같아진 배치 차이 "
        "2행과 지운 호기의 배치 차이 1행을 정리한 r6으로 발행합니다" in mixed[0]
    ), mixed

    old, blocked = publish_layout_lines(
        scenario,
        _revision(2),
        LayoutPublishPreview(action="blocked", stored_units=1, is_newest=False, orphan_units=1),
    )
    assert blocked
    assert "r2에 저장된 배치 차이 1행은 공통 대장에서 지운 호기의 것이지만, 최신(r5)이" in old[0]
    assert "(되돌리기는 지운 호기의 배치 차이를 빼고 씁니다)" in old[0]
    assert "공식과 같아" not in old[0]
    newest, blocked = publish_layout_lines(
        scenario,
        _revision(3),
        LayoutPublishPreview(
            action="blocked", newest_rows=2, is_newest=False, newest_orphan_units=2
        ),
    )
    assert blocked
    assert "최신 r5에 저장된 배치 차이 2행(공통 대장에서 지운 호기의 것)이 남아 있어" in newest[0]
    assert "(지운 호기의 배치 차이는 그때 정리됩니다)" in newest[0]

    message = publish_result_message(
        "셋업 실무",
        revision,
        2,
        cleaned_no=6,
        moved=False,
        kept_unsaved=False,
        layout=LayoutPublishPreview(action="clean", stored_units=1, newest_rows=1, orphan_units=1),
    )
    assert "「셋업 실무」 r5의 지운 호기의 배치 차이를 정리한 r6." in message, message
    plain = publish_result_message(
        "셋업 실무", revision, 2, cleaned_no=6, moved=False, kept_unsaved=False
    )
    assert "「셋업 실무」 r5의 공식과 같아진 배치 차이를 정리한 r6." in plain


def test_the_restore_confirm_names_units_whose_place_changed_since_then() -> None:
    """검토 F21 — 되살리는 가정 배치에서 그때 손대지 않은 호기는 지금 공식 자리를 따른다."""
    chosen = _revision(2, "d2", layout_unit_count=1)
    moved = ScheduleRestorePreview(
        layout_unit_rows=1,
        layout_digest="d",
        layout_moved_since=4,
        restored_layout_unit_rows=1,
        restored_layout_digest="d",
    )
    sentence = restore_layout_sentence(chosen, moved, official_scenario=False)
    assert sentence.startswith("r2의 가정 배치(저장된 차이 호기 1행)도 되살립니다.")
    assert "그때와 자리가 다른 호기 4대가 있습니다(이력 「그때 그대로」 와 다름)" in sentence
    same = ScheduleRestorePreview(
        layout_unit_rows=1,
        layout_digest="d",
        restored_layout_unit_rows=1,
        restored_layout_digest="d",
    )
    assert "그때와" not in restore_layout_sentence(chosen, same, official_scenario=False)


def test_the_restore_confirm_does_not_promise_a_layout_it_will_not_write() -> None:
    """E2E r2 eq-flows — 고른 리비전의 차이가 그 뒤 지운 호기뿐이면(정규화하면 빈다) 「되살립니다」
    라 하지 않는다. 지금 최신도 차이가 없으면 배치는 그대로라 하고, 있으면 지워진다고 적는다."""
    chosen = _revision(2, "d2", layout_unit_count=1)
    gone = ScheduleRestorePreview(layout_unit_rows=1, layout_digest="d")
    sentence = restore_layout_sentence(chosen, gone, official_scenario=False)
    assert "되살립니다" not in sentence
    assert "되살릴 것이 없습니다" in sentence and "지금 최신 그대로" in sentence
    assert restore_writes_nothing(gone, official_scenario=False)
    current = ScheduleRestorePreview(
        layout_unit_rows=1,
        layout_digest="d",
        current_layout_unit_rows=2,
        current_layout_digest="c",
        current_effective_layout_digest="c",
    )
    sentence = restore_layout_sentence(chosen, current, official_scenario=False)
    assert "되살릴 것이 없습니다" in sentence and "공식 배치를 따릅니다" in sentence
    assert not restore_writes_nothing(current, official_scenario=False)
    partly = ScheduleRestorePreview(
        layout_unit_rows=2,
        layout_digest="d",
        restored_layout_unit_rows=1,
        restored_layout_digest="n",
    )
    sentence = restore_layout_sentence(chosen, partly, official_scenario=False)
    assert sentence.startswith("r2의 가정 배치(되살릴 차이 호기 1행)도 되살립니다 — ")
    assert "그 뒤 지운 호기·지금 공식과 같아진 것은 빠집니다" in sentence


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


def test_the_section_caption_names_the_assumption_layout_as_held_per_scenario(
    tmp_path: Path,
) -> None:
    """E2E r3 — 구획 캡션이 설비 시나리오가 따로 드는 것에 가정 배치를 넣는다(같은 구획에 「저장된
    배치 차이」·「배치 차이 모두 지우기」 가 있다). 「일정 여섯·시나리오 메모·비가동만」 이라 하지
    않는다."""
    _, setup, _ = _moved_setup(tmp_path)
    app = _ok(_section(tmp_path, setup).run())

    caption = next(
        str(item.value)
        for item in app.caption
        if "모든 설비 시나리오가 함께 씁니다" in str(item.value)
    )
    assert "비가동만" not in caption
    assert (
        "일정 여섯·시나리오 메모·비가동과 가정 배치(공식과 다른 호기 위치·층 도면 요소·Main 설비명 "
        "위치)를 따로 듭니다" in caption
    ), caption


def test_a_session_move_notice_keeps_tildes_in_the_scenario_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E2E r3 같은 꼴 — 세션을 다른 리비전으로 옮겼다는 알림은 설비 시나리오 이름을 두 번 싣는다.
    막지 않으면 물결표 하나짜리 이름(「10~12월 증설」)도 두 이름 사이가 지움선 짝이 된다."""
    from dataclasses import replace

    from capa_simulation.components import equipment_scenario_management as section
    from capa_simulation.equipment_scenario_activation import resolve_equipment_session

    _, setup, _ = _moved_setup(tmp_path)
    notice = (
        "「10~12월 증설」 r1 을 지금 공통 대장과 합칠 수 없어 「10~12월 증설」 r2 로 열었습니다 — "
        "저장하지 않은 설비 편집은 버렸습니다."
    )
    monkeypatch.setattr(
        section,
        "resolve_equipment_session",
        lambda path: replace(resolve_equipment_session(path), notice=notice),
    )
    app = _ok(_section(tmp_path, setup).run())

    warnings = [str(item.value) for item in app.warning]
    # 세션 알림은 표(평문)에도 가는 글이라 그리는 자리에서 글 통째로 막는다(E2E r5 — `*` 까지).
    assert literal_markdown(notice) in warnings, warnings
    assert notice not in warnings


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


def test_a_cleaning_publish_moves_the_session_and_revision_box_to_the_new_revision(
    tmp_path: Path,
) -> None:
    """정리 발행(공식과 같아진 차이만 남은 최신 → rN+1 로 발행) 뒤에는 「배치 차이 모두 지우기」
    처럼 리비전 상자와 그 시나리오를 보던 세션이 새 리비전으로 옮겨 간다 — 옛 rN 에 남으면
    낡음·Space 배치 잠금·빨간 막힘 글이 바로 섰다(S4 리뷰)."""
    repository, setup, latest = _moved_setup(tmp_path)
    official = _session(repository)
    repository.save_equipment(
        _request(official, equipment=_set(official.equipment, "EQ-01", "X좌표", 50.0))
    )
    clear_equipment_repository()
    app = _ok(_section(tmp_path, setup).run())
    app.selectbox(key=SCENARIO_KEY).set_value(setup)
    _ok(app.run())
    assert app.selectbox(key=REVISION_KEY).value == latest
    assert any("정리한 r3으로 발행합니다" in text for text in _texts(app))

    _ok(app.button(key=PUBLISH_BUTTON_KEY).click().run())

    newest = repository.list_schedule_revisions(setup, limit=1)[0]
    assert (newest.revision_no, newest.origin) == (3, "layout_clear")
    release = repository.latest_equipment_release()
    assert release is not None and release.schedule_revision_id == newest.schedule_revision_id
    texts = _texts(app)
    assert any(
        "공식 v2로 발행했습니다" in text and "이 세션을 r3으로 옮겼습니다." in text
        for text in texts
    ), texts
    assert app.session_state[SELECTION_KEY]["schedule_revision_id"] == newest.schedule_revision_id
    assert app.selectbox(key=REVISION_KEY).value == newest.schedule_revision_id
    assert not app.error, [item.value for item in app.error]
