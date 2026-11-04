# Purpose: 설비 시나리오 구획의 알림 뒤 팝오버 자리·리비전 표 위 띄움·값 뒤 조사를 검사한다.

"""시나리오 관리 「설비 시나리오」 구획의 화면 자리와 글(브라우저 E2E 결함 셋).

- 작업 알림(알림창 표지 — 구획 맨 위 늘 서 있는 칸이 보낸다)은 한 회차뿐이다. 알림이 빠지는 다음
  회차에 팝오버 줄이 한 칸 당겨지면 팝오버가 다시 서며 닫혀, 알림 뒤 처음 누른 확인 체크·Enter 가
  열린 팝오버를 닫았다. 알림 칸은 늘 서 있고 팝오버 key 는 알림을 꺼내는 회차에만 바뀐다(작업을
  마친 팝오버는 그대로 닫힌다).
- 리비전 표의 도구 막대는 표 오른쪽 위로 솟아, 표가 바로 위 줄에 붙어 있으면 그 줄 맨 오른쪽
  팝오버 단추(「시나리오 이름 바꾸기」·「배치 차이 모두 지우기」)의 누름을 가로챘다 — 표 앞에
  띄움(`st.space`)이 선다.
- 리비전 번호·시나리오 이름 뒤 조사는 끝소리로 고른다(「r2를」·「r5는」·「「셋업 시나리오」로」).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from alert_marks import successes
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block, Dataframe
from test_equipment_scenario_repository import OPERATIONS, _request, _seeded, _session, _set

from capa_simulation.components.equipment_scenario_management import (
    LOAD_BUTTON_KEY,
    PUBLISH_BUTTON_HELP,
    PUBLISH_BUTTON_KEY,
    RENAME_BUTTON_KEY,
    RENAME_KEY,
    RESTORE_BUTTON_KEY,
    RESTORE_CONFIRM_KEY,
    REVISION_KEY,
    REVISION_NAME_BUTTON_KEY,
    REVISION_NAME_KEY,
    REVISION_TABLE_TOOLBAR_CLEARANCE,
    publish_preview,
    revision_name_help,
)
from capa_simulation.equipment_scenario_activation import EquipmentSession
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentScenarioCatalog,
    EquipmentScenarioSummary,
    EquipmentScheduleRevisionSummary,
)


@pytest.fixture(autouse=True)
def _fresh_caches() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


def _section(path: Path) -> AppTest:
    return AppTest.from_string(
        f"""
from capa_simulation.components.equipment_scenario_management import (
    render_equipment_scenario_management,
)
from capa_simulation.equipment_scenario_activation import resolve_equipment_session
session = resolve_equipment_session({str(path)!r})
render_equipment_scenario_management({str(path)!r}, session)
""",
        default_timeout=60,
    )


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _two_revisions(tmp_path: Path) -> tuple[Path, dict[int, str]]:
    """「운영 일정」 r1·r2(r2 가 최신 — EQ-02 의 Qual일정이 다르다)."""
    repository = _seeded(tmp_path)
    session = _session(repository)
    repository.save_equipment(
        _request(session, equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-24"))
    )
    numbers = {
        item.revision_no: item.schedule_revision_id
        for item in repository.list_schedule_revisions(OPERATIONS)
    }
    return repository.database_path, numbers


def _walk(block: Block, path: tuple[int, ...] = ()) -> list[tuple[tuple[int, ...], Any]]:
    found: list[tuple[tuple[int, ...], Any]] = []
    for index, child in block.children.items():
        found.append(((*path, index), child))
        if isinstance(child, Block):
            found.extend(_walk(child, (*path, index)))
    return found


def _popovers(app: AppTest) -> dict[str, tuple[tuple[int, ...], str]]:
    """팝오버 라벨 → (본문 안 자리, 블록 id). 프런트엔드는 블록 id(없으면 자리)로 팝오버를
    가린다."""
    return {
        str(node.proto.popover.label): (path, str(node._block_id))
        for path, node in _walk(app.main)
        if getattr(node, "type", "") == "popover"
    }


def _successes(app: AppTest) -> list[str]:
    """작업 알림 — 성공은 구획 맨 위에 그리지 않고 알림창 표지로만 낸다(설계 규칙 UI-NTF-03)."""
    assert not app.success, [str(item.value) for item in app.success]
    return [str(item.value) for item in successes(app)]


def test_a_popover_keeps_its_place_and_key_when_the_alert_goes_away(tmp_path: Path) -> None:
    """「리비전명 저장」 알림이 선 회차에는 팝오버가 새로 선다(작업을 마친 팝오버는 닫힌다). 그
    다음 회차(되돌리기 확인 체크 — 알림이 빠진다)에는 팝오버의 자리와 key 가 그대로라 열린
    「이 리비전으로 되돌리기」 가 닫히지 않는다."""
    path, numbers = _two_revisions(tmp_path)
    app = _ok(_section(path).run())
    app.selectbox(key=REVISION_KEY).set_value(numbers[1])
    _ok(app.run())
    before = _popovers(app)
    assert set(before) == {
        "시나리오 이름 바꾸기",
        "이 리비전 불러오기",
        "이 리비전으로 되돌리기",
        "여기서 새 시나리오",
        "리비전명",
        "공식으로 발행",
    }
    assert all(block_id for _, block_id in before.values())

    app.text_input(key=f"{REVISION_NAME_KEY}__{numbers[1]}").input("알림 만들기")
    app.button(key=REVISION_NAME_BUTTON_KEY).click()
    _ok(app.run())
    assert any("리비전명을 저장했습니다" in text for text in _successes(app))
    with_alert = _popovers(app)
    for label, (place, block_id) in with_alert.items():
        assert place == before[label][0], label
        assert block_id != before[label][1], label

    (confirm,) = [box for box in app.checkbox if str(box.key).startswith(RESTORE_CONFIRM_KEY)]
    confirm.check()
    _ok(app.run())
    assert not _successes(app)
    assert _popovers(app) == with_alert
    assert not app.button(key=RESTORE_BUTTON_KEY).disabled


def test_the_revision_table_stands_clear_of_the_row_above_it(tmp_path: Path) -> None:
    """시나리오 줄(맨 오른쪽 팝오버 단추)과 리비전 표 사이에 띄움이 선다 — 표 도구 막대가 그 단추를
    덮지 않게. 그 사이의 칸(옛 판 흔적 경고 자리)은 비어 있으면 높이가 없다."""
    path, _ = _two_revisions(tmp_path)
    app = _ok(_section(path).run())
    siblings = sorted(app.main.children.items())
    row = next(
        index
        for index, node in siblings
        if isinstance(node, Block)
        and any(
            getattr(child, "type", "") == "popover"
            and child.proto.popover.label == "시나리오 이름 바꾸기"
            for child in node.children.values()
        )
    )
    table = next(
        index
        for index, node in siblings
        if isinstance(node, Dataframe) and "리비전명" in node.value.columns
    )
    between = [node for index, node in siblings if row < index < table]
    spaces = [node for node in between if getattr(node, "type", "") == "space"]
    assert len(spaces) == 1
    assert between[-1] is spaces[0]
    assert REVISION_TABLE_TOOLBAR_CLEARANCE >= 20
    assert all(
        isinstance(node, Block) and not node.children for node in between if node is not spaces[0]
    )


def test_loading_a_revision_picks_the_particle_by_its_number(tmp_path: Path) -> None:
    """「이 리비전 불러오기」 안내와 불러온 알림 — 「r2을」 이 아니라 「r2를」."""
    path, numbers = _two_revisions(tmp_path)
    app = _ok(_section(path).run())
    assert app.selectbox(key=REVISION_KEY).value == numbers[2]
    assert any(
        str(item.value) == "「운영 일정」 r2를 이 세션의 설비 시나리오로 올립니다."
        for item in app.caption
    )
    app.button(key=LOAD_BUTTON_KEY).click()
    _ok(app.run())
    assert "설비 시나리오 「운영 일정」 r2를 불러왔습니다." in _successes(app)


def test_the_rename_notice_puts_no_particle_right_after_the_new_name(tmp_path: Path) -> None:
    """이름 바로 뒤에 조사를 붙이지 않는다 — 라틴 글자로 끝나는 이름(「가정 P」)도 「(으)로」 같은
    겸용 조사 없이 읽힌다(E2E r2 #83)."""
    path, _ = _two_revisions(tmp_path)
    app = _ok(_section(path).run())
    for generation, name in enumerate(("셋업 시나리오", "가정 P", "운영 일정")):
        key = RENAME_KEY if generation == 0 else f"{RENAME_KEY}__g{generation}"
        app.text_input(key=f"{key}__{OPERATIONS}").input(name)
        app.button(key=RENAME_BUTTON_KEY).click()
        _ok(app.run())
        assert f"설비 시나리오 이름을 바꿨습니다 — 새 이름 「{name}」." in _successes(app)
        assert not [text for text in _successes(app) if "(으)로" in text]
    assert DuckDBEquipmentRepository(path).list_equipment_scenarios()[0].scenario_name == (
        "운영 일정"
    )


@pytest.mark.parametrize(("chosen", "particle"), [(5, "는"), (3, "은"), (2, "는")])
def test_the_publish_preview_picks_the_particle_by_the_revision_number(
    chosen: int, particle: str
) -> None:
    """「r5 은 … 최신(r6)이 아닙니다」 가 아니라 「r5는」 — 받침 있는 번호(r3)만 우연히 맞았다."""
    scenario = EquipmentScenarioSummary(
        "setup",
        "셋업 실무",
        "ACTIVE",
        latest_schedule_revision_id="b6",
        latest_revision_no=6,
        revision_count=6,
    )
    catalog = EquipmentScenarioCatalog(scenarios=(scenario,))
    session = EquipmentSession(catalog, scenario, "b6")
    revision = EquipmentScheduleRevisionSummary(
        f"b{chosen}", "setup", chosen, "save", datetime(2026, 10, 24)
    )

    lines = publish_preview(session, scenario, revision)

    assert lines[1] == f"r{chosen}{particle} 「셋업 실무」 의 최신(r6)이 아닙니다."


def test_an_empty_store_says_so_in_one_plain_line(tmp_path: Path) -> None:
    """설비 시나리오가 하나도 없으면 구획은 그 값 한 줄만 평문으로 둔다 — 「어느 탭에서 무엇을
    저장하면 섭니다」 같은 하는 법 꼬리와 안내 상자를 붙이지 않는다(설계 규칙 AMB-02 (가) ·
    UI-TXT-03 · V-16)."""
    path = tmp_path / "equipment.duckdb"
    DuckDBEquipmentRepository(path)
    app = _ok(
        AppTest.from_string(
            f"""
from capa_simulation.components.equipment_scenario_management import (
    render_equipment_scenario_management,
)
from capa_simulation.equipment_scenario_activation import EquipmentSession
from capa_simulation.persistence.equipment_repository import EquipmentScenarioCatalog
session = EquipmentSession(EquipmentScenarioCatalog(scenarios=()))
render_equipment_scenario_management({str(path)!r}, session)
""",
            default_timeout=60,
        ).run()
    )

    captions = [str(item.value) for item in app.caption]
    assert captions == ["설비 시나리오가 없습니다."], captions
    assert not app.info and not app.success and not app.warning


def test_popover_explanations_sit_in_balloons_not_standing_captions(tmp_path: Path) -> None:
    """「리비전명」 · 「공식으로 발행」 팝오버의 설명 글(이름표의 뜻 · 공식이 무엇에 쓰이는지)은 늘
    띄워 두지 않고 그 칸 · 단추의 풍선에 둔다(설계 규칙 UI-TXT-01 · AMB-01 (가))."""
    path, numbers = _two_revisions(tmp_path)
    app = _ok(_section(path).run())
    assert app.selectbox(key=REVISION_KEY).value == numbers[2]

    captions = [str(item.value) for item in app.caption]
    assert not any("이름표입니다" in text for text in captions), captions
    assert not any("append-only" in text for text in captions), captions
    name = app.text_input(key=f"{REVISION_NAME_KEY}__{numbers[2]}")
    assert str(name.help) == revision_name_help(2)
    # 꺼진 회차에는 꺼진 까닭이 앞에 붙는다(설계 규칙 UI-INP-07) — 공식의 뜻은 늘 풍선 끝이다.
    assert str(app.button(key=PUBLISH_BUTTON_KEY).help).endswith(PUBLISH_BUTTON_HELP)
