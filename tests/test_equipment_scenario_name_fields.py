# Purpose: 설비 시나리오 구획 팝오버 안 이름 칸이 회차마다 지금 이름을 브라우저에 싣는지 검사한다.

"""「리비전명」·「시나리오 이름 바꾸기」 팝오버 안 이름 칸(2026-10-26 브라우저 E2E 결함).

닫힌 팝오버 안 칸은 브라우저에 마운트되지 않는다. 나중에 열려 마운트될 때 브라우저는 **마지막
회차가 실어 보낸 값**(`set_value` 가 켜진 `value`)으로 칸을 세우고, 없으면 빈 기본값(`default`)으로
세운다. 칸을 처음 세운 회차에만 지금 이름을 적으면, 한 회차라도 지나 연 칸은 빈 칸으로 서고 그대로
누른 「리비전명 저장」 이 그 빈 값을 되보내 리비전명을 지웠다. 일반 `AppTest.run()` 은 회차마다 세션
값을 되보내 이 결함을 보지 못하므로, 브라우저가 늦게 마운트할 때 보일 글자(`_late_mount`)로 잰다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_scenario_repository import OPERATIONS, _request, _seeded, _session, _set

from capa_simulation.components.equipment_scenario_management import (
    RENAME_KEY,
    REVISION_KEY,
    REVISION_NAME_BUTTON_KEY,
    REVISION_NAME_KEY,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository


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


def _late_mount(widget: Any) -> str:
    """닫혀 있던 팝오버를 지금 열 때 브라우저가 칸에 세울 글자 — 이번 회차가 값을 실어 보냈으면 그
    값, 아니면 빈 기본값."""
    proto = widget.proto
    return str(proto.value) if proto.set_value else str(proto.default)


def _named_revisions(tmp_path: Path) -> tuple[DuckDBEquipmentRepository, dict[int, str]]:
    """「운영 일정」 r1(리비전명 「u2 이름」)·r2(최신 — EQ-02 의 Qual일정이 다르다)."""
    repository = _seeded(tmp_path)
    session = _session(repository)
    repository.save_equipment(
        _request(session, equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-24"))
    )
    numbers = {
        item.revision_no: item.schedule_revision_id
        for item in repository.list_schedule_revisions(OPERATIONS)
    }
    repository.rename_schedule_revision(numbers[1], name="u2 이름", expected_name=None)
    return repository, numbers


def test_the_revision_name_field_carries_the_name_on_every_run_while_untouched(
    tmp_path: Path,
) -> None:
    """r1 을 고른 뒤 팝오버를 열지 않은 채 한 회차가 더 돌아도 리비전명 칸은 「u2 이름」 으로 서고,
    그 칸 그대로 「리비전명 저장」 을 눌러도 이름이 지워지지 않는다."""
    repository, numbers = _named_revisions(tmp_path)
    app = _ok(_section(repository.database_path).run())
    app.selectbox(key=REVISION_KEY).set_value(numbers[1])
    _ok(app.run())
    field = f"{REVISION_NAME_KEY}__{numbers[1]}"
    assert _late_mount(app.text_input(key=field)) == "u2 이름"

    # 팝오버와 상관없는 다시 돌기(안쪽 탭을 다시 누르기 등) — 칸은 여전히 지금 이름을 싣는다.
    _ok(app.run())
    assert _late_mount(app.text_input(key=field)) == "u2 이름"

    # 브라우저처럼 늦게 마운트된 칸의 글자 그대로 저장을 누른다.
    app.text_input(key=field).input(_late_mount(app.text_input(key=field)))
    app.button(key=REVISION_NAME_BUTTON_KEY).click()
    _ok(app.run())
    names = {
        item.revision_no: item.revision_name
        for item in repository.list_schedule_revisions(OPERATIONS)
    }
    assert names[1] == "u2 이름"


def test_the_scenario_name_field_carries_the_name_after_another_run(tmp_path: Path) -> None:
    """새 세션에서 리비전만 한 번 바꾼 뒤 「시나리오 이름 바꾸기」 를 열어도 이름 칸은 지금 이름으로
    선다(바꾸기 전 회차에만 이름을 실어 보내 빈 칸으로 섰다)."""
    repository, numbers = _named_revisions(tmp_path)
    app = _ok(_section(repository.database_path).run())
    field = f"{RENAME_KEY}__{OPERATIONS}"
    assert _late_mount(app.text_input(key=field)) == "운영 일정"

    app.selectbox(key=REVISION_KEY).set_value(numbers[1])
    _ok(app.run())
    assert _late_mount(app.text_input(key=field)) == "운영 일정"


def test_an_edited_name_field_is_not_overwritten_by_the_rewrite(tmp_path: Path) -> None:
    """매 회차 다시 적기는 고치지 않은 칸만이다 — 고치던 글자는 다른 회차가 돌아도 그대로다."""
    repository, numbers = _named_revisions(tmp_path)
    app = _ok(_section(repository.database_path).run())
    field = f"{RENAME_KEY}__{OPERATIONS}"
    app.text_input(key=field).input("고치는 중")
    _ok(app.run())
    app.selectbox(key=REVISION_KEY).set_value(numbers[1])
    _ok(app.run())
    widget = app.text_input(key=field)
    assert widget.value == "고치는 중"
    assert not widget.proto.set_value
