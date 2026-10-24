# Purpose: 설비 시나리오 탭 공식 발행의 본 번호 대조와 이어 쓰기 확인 체크 key 를 검사한다.

"""E7 리뷰가 권한 두 가지(설비 시나리오 2단계 S1 에 묶음).

- 「공식으로 발행」 은 누르기 **전** 회차의 확인 글이 보인 공식 번호를 남겨 두고, 누른 회차에 그
  번호가 달라졌으면(그 사이 남이 발행) 거절하고 까닭을 알린다 — 「지금 공식 v1 → 새 공식 v2」 를
  본 사람이 말없이 v3 을 내지 않게.
- 「이대로 이어 쓰기」 확인 체크 key 에 체크 글을 정하는 값 셋(흔적 수·옛 배포 리비전 번호·빠지는
  호기 수)을 붙인다 — 글이 바뀌면 체크가 풀린 새 칸으로 선다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_scenario_repository import _clone, _request, _seeded, _session, _set

from capa_simulation.components.equipment_scenario_management import (
    PUBLISH_BUTTON_KEY,
    SCENARIO_KEY,
    continue_confirm_key,
    publish_seen_refusal,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import LegacyTraceReview


@pytest.fixture(autouse=True)
def _fresh_caches() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


def test_the_publish_refusal_compares_the_seen_number_with_the_click_run() -> None:
    seen = {"revision": "r-setup", "release_no": 1}

    assert publish_seen_refusal(seen, schedule_revision_id="r-setup", release_no=1) is None
    moved = publish_seen_refusal(seen, schedule_revision_id="r-setup", release_no=2)
    assert moved is not None
    assert "확인 글을 본 뒤 공식이 바뀌어(v1 → 지금 v2) 발행하지 않았습니다" in moved
    assert "지금 공식 v2 → 새 공식 v3" in moved
    first = publish_seen_refusal(
        {"revision": "r-setup", "release_no": 0}, schedule_revision_id="r-setup", release_no=1
    )
    assert first is not None and "(발행 없음 → 지금 v1)" in first
    # 앞 회차에 확인 글이 없었거나 다른 리비전의 글이었으면 다시 보게 한다.
    for unseen in (None, {"revision": "r-other", "release_no": 1}):
        refusal = publish_seen_refusal(unseen, schedule_revision_id="r-setup", release_no=1)
        assert refusal is not None and "다시 누르세요" in refusal


def _tab(path: Path) -> AppTest:
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


def test_a_release_by_someone_else_after_the_preview_is_not_overtaken_silently(
    tmp_path: Path,
) -> None:
    """「셋업 실무」 r1 을 발행하려고 확인 글(지금 공식 v1 → 새 공식 v2)을 본 사이 남이 「운영
    일정」 을 저장해 v2 를 냈다. 누르면 v3 으로 내지 않고 거절하며, 바뀐 확인 글을 본 뒤 다시 누르면
    낸다."""
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    path = tmp_path / "equipment.duckdb"
    app = _ok(_tab(path).run())
    app.selectbox(key=SCENARIO_KEY).set_value(setup.equipment_scenario_id)
    _ok(app.run())
    assert any("지금 공식 v1" in str(item.value) for item in app.caption)

    other = _session(repository)
    published = repository.save_equipment(
        _request(other, equipment=_set(other.equipment, "EQ-02", "Qual일정", "2026-08-24"))
    )
    assert published.release_no == 2

    app.button(key=PUBLISH_BUTTON_KEY).click()
    _ok(app.run())
    release = repository.latest_equipment_release()
    assert release is not None and release.release_no == 2
    assert release.equipment_scenario_id != setup.equipment_scenario_id
    assert any(
        "확인 글을 본 뒤 공식이 바뀌어(v1 → 지금 v2) 발행하지 않았습니다" in str(item.value)
        for item in app.error
    )
    assert any("지금 공식 v2" in str(item.value) for item in app.caption)

    app.button(key=PUBLISH_BUTTON_KEY).click()
    _ok(app.run())
    release = repository.latest_equipment_release()
    assert release is not None and release.release_no == 3
    assert release.equipment_scenario_id == setup.equipment_scenario_id


def test_the_continue_confirm_key_changes_with_any_number_in_its_label() -> None:
    review = LegacyTraceReview(count=1, trace_revision_no=2, dropped_units=2)
    same = continue_confirm_key(1, LegacyTraceReview(count=1, trace_revision_no=2, dropped_units=2))

    assert continue_confirm_key(1, review) == same
    others = {
        continue_confirm_key(2, review),
        continue_confirm_key(1, LegacyTraceReview(count=1, trace_revision_no=3, dropped_units=2)),
        continue_confirm_key(1, LegacyTraceReview(count=1, trace_revision_no=2, dropped_units=5)),
        continue_confirm_key(
            1, LegacyTraceReview(count=1, trace_revision_no=None, dropped_units=2)
        ),
    }
    assert same not in others and len(others) == 4
