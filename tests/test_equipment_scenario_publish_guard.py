# Purpose: 설비 시나리오 구획 공식 발행의 본 번호·최신 대조와 이어 쓰기 확인 체크 key 를 검사한다.

"""E7 리뷰가 권한 두 가지(설비 시나리오 2단계 S1 에 묶음).

- 「공식으로 발행」 은 누르기 **전** 회차의 확인 글이 보인 공식 번호를 남겨 두고, 누른 회차에 그
  번호가 달라졌으면(그 사이 남이 발행) 거절하고 까닭을 알린다 — 「지금 공식 v1 → 새 공식 v2」 를
  본 사람이 말없이 v3 을 내지 않게. 그 사이 남이 같은 시나리오에 새 리비전을 저장해 최신이
  바뀌었어도 거절한다 — 「rN은 최신이 아닙니다」 를 본 적 없는 사람이 최신이 아닌 리비전을 말없이
  내지 않게(2026-10-26 E2E).
- 「이대로 이어 쓰기」 확인 체크 key 에 체크 글을 정하는 값 셋(흔적 수·옛 배포 리비전 번호·빠지는
  호기 수)을 붙인다 — 글이 바뀌면 체크가 풀린 새 칸으로 선다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

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
    CONTINUE_BUTTON_KEY,
    PUBLISH_BUTTON_KEY,
    SCENARIO_KEY,
    continue_confirm_key,
    publish_seen_refusal,
    publish_seen_token,
    release_words,
)
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    clear_equipment_scenario_cache,
)
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentReleaseMoved,
    EquipmentScenarioSummary,
    EquipmentScheduleRevisionSummary,
    LegacyTraceReview,
)


@pytest.fixture(autouse=True)
def _fresh_caches() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


def _setup(latest_id: str = "r-setup", latest_no: int = 4) -> EquipmentScenarioSummary:
    return EquipmentScenarioSummary(
        "setup",
        "셋업 실무",
        "ACTIVE",
        latest_schedule_revision_id=latest_id,
        latest_revision_no=latest_no,
        revision_count=latest_no,
    )


def _seen(release_no: int, scenario: EquipmentScenarioSummary | None = None) -> dict[str, object]:
    """「셋업 실무」 r4(최신) 확인 글을 공식 `release_no` 에서 본 값."""
    revision = EquipmentScheduleRevisionSummary(
        "r-setup", "setup", 4, "save", datetime(2026, 10, 26)
    )
    return publish_seen_token(scenario or _setup(), revision, release_no)


def test_the_publish_refusal_compares_the_seen_number_with_the_click_run() -> None:
    seen = _seen(1)
    setup = _setup()

    def refusal(seen: object, release_no: int = 1, scenario: Any = setup) -> str | None:
        return publish_seen_refusal(
            seen, scenario=scenario, schedule_revision_id="r-setup", release_no=release_no
        )

    assert refusal(seen) is None
    moved = refusal(seen, 2)
    assert moved is not None
    assert "확인 글을 본 뒤 공식이 바뀌어(v1 → 지금 v2) 발행하지 않았습니다" in moved
    assert "지금 공식 v2 → 새 공식 v3" in moved
    first = refusal(_seen(0))
    assert first is not None and "(발행 없음 → 지금 v1)" in first
    # 앞 회차에 확인 글이 없었거나 다른 리비전의 글이었으면 다시 보게 한다.
    for unseen in (None, {**seen, "revision": "r-other"}):
        again = refusal(unseen)
        assert again is not None and "다시 누르세요" in again


def test_the_publish_refusal_sees_a_newer_revision_of_the_same_scenario() -> None:
    """확인 글을 본 뒤 그 시나리오에 r5 가 저장되면(최신 r4 → r5) 거절하고 까닭을 알린다 — 다시 그린
    확인 글은 「r4는 「셋업 실무」 의 최신(r5)이 아닙니다」 를 보인다."""
    newer = _setup("r-newer", 5)

    refusal = publish_seen_refusal(
        _seen(1), scenario=newer, schedule_revision_id="r-setup", release_no=1
    )

    assert refusal == (
        "확인 글을 본 뒤 「셋업 실무」 의 최신이 바뀌어(r4 → 지금 r5) 발행하지 않았습니다 — 다른 "
        "사용자가 그 사이 r5를 저장했습니다. 바뀐 확인 글을 다시 보고 발행하세요."
    )
    # 공식도 바뀌었으면 공식 번호 까닭이 먼저다(그 글에 새 공식 번호가 있다).
    both = publish_seen_refusal(
        _seen(1), scenario=newer, schedule_revision_id="r-setup", release_no=2
    )
    assert both is not None and "공식이 바뀌어(v1 → 지금 v2)" in both


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


def test_a_newer_revision_saved_after_the_preview_stops_the_publish_once(tmp_path: Path) -> None:
    """「운영 일정」 최신 r2(공식 v1 = r1)를 발행하려고 확인 글(최신이 아니라는 줄 없음)을 본 사이
    남이 r3 을 저장했다. 누르면 r2 를 내지 않고 거절하며, 다시 그린 확인 글이 「r2는 … 의
    최신(r3)이 아닙니다」 를 보인다. 그 글을 본 뒤 다시 누르면 r2 를 낸다(최신이 아닌 리비전 발행은
    원래 된다)."""
    repository = _seeded(tmp_path)
    session = _session(repository)
    repository.save_equipment(
        _request(
            session,
            equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-24"),
            publish_official=False,
        )
    )
    path = repository.database_path
    app = _ok(_tab(path).run())
    captions = [str(item.value) for item in app.caption]
    assert any("새 공식 v2 · 「운영 일정」 r2" in text for text in captions)
    assert not any("의 최신(r" in text for text in captions)

    other = _session(repository)
    repository.save_equipment(
        _request(
            other,
            equipment=_set(other.equipment, "EQ-02", "Qual일정", "2026-08-31"),
            publish_official=False,
        )
    )
    clear_equipment_scenario_cache()
    app.button(key=PUBLISH_BUTTON_KEY).click()
    _ok(app.run())
    release = repository.latest_equipment_release()
    assert release is not None and release.release_no == 1
    assert any(
        "확인 글을 본 뒤 「운영 일정」 의 최신이 바뀌어(r2 → 지금 r3) 발행하지 않았습니다"
        in str(item.value)
        for item in app.error
    )
    assert "r2는 「운영 일정」 의 최신(r3)이 아닙니다." in [str(item.value) for item in app.caption]

    app.button(key=PUBLISH_BUTTON_KEY).click()
    _ok(app.run())
    release = repository.latest_equipment_release()
    assert release is not None and release.release_no == 2
    published = {
        item.schedule_revision_id: item.revision_no
        for item in repository.list_schedule_revisions(OPERATIONS)
    }
    assert published[release.schedule_revision_id] == 2


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


def test_a_release_moved_under_a_stale_list_says_no_release_instead_of_v0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """목록 캐시가 늦어 화면 대조를 지난 발행을 저장소가 거절하면 같은 꼴로 알린다 — 발행이 없던
    번호는 「v0」 이 아니라 「발행 없음」 이다."""
    repository = _seeded(tmp_path)
    setup = _clone(repository)

    def moved(*args: object, **kwargs: object) -> None:
        raise EquipmentReleaseMoved(0, 1)

    monkeypatch.setattr(DuckDBEquipmentRepository, "publish_equipment_release", moved)
    app = _ok(_tab(tmp_path / "equipment.duckdb").run())
    app.selectbox(key=SCENARIO_KEY).set_value(setup.equipment_scenario_id)
    _ok(app.run())
    app.button(key=PUBLISH_BUTTON_KEY).click()
    _ok(app.run())

    errors = [str(item.value) for item in app.error]
    assert any("확인 글을 본 뒤 공식이 바뀌어(발행 없음 → 지금 v1)" in text for text in errors)
    assert not any("v0" in text for text in errors)
    assert release_words(0) == "발행 없음" and release_words(3) == "v3"


def _add_trace(path: Path, revision_id: str, revision_no: int) -> None:
    """0027 경계 뒤에 옛 배포(계약 v3)가 남긴 빈 공통 리비전."""
    import duckdb

    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            INSERT INTO equipment_ops.revision (
                revision_id, revision_no, note, baseline_hash, schedule_hash, equipment_hash,
                downtime_hash, equipment_contract_version
            ) VALUES (?, ?, '옛 배포', 'b', 's', 'e', 'd', 3)
            """,
            [revision_id, revision_no],
        )


def test_the_continue_check_resets_when_its_words_change_on_screen(tmp_path: Path) -> None:
    """확인 체크를 켠 뒤 옛 배포 흔적이 하나 더 생기면(체크 글의 리비전 번호가 r2 → r3) 체크가 풀린
    새 칸으로 서고 단추가 꺼진다 — 본 적 없는 글로 이어 쓰지 않게(E7 리뷰 권고 (b))."""
    repository = _seeded(tmp_path)
    path = repository.database_path
    _add_trace(path, "old-deploy", 2)
    app = _ok(_tab(path).run())
    confirm = next(box for box in app.checkbox if "이대로 이어 씁니다" in str(box.label))
    assert "옛 배포 리비전 r2" in str(confirm.label)
    confirm.check()
    _ok(app.run())
    assert not app.button(key=CONTINUE_BUTTON_KEY).disabled

    _add_trace(path, "old-deploy-2", 3)
    clear_equipment_scenario_cache()
    _ok(app.run())

    confirm = next(box for box in app.checkbox if "이대로 이어 씁니다" in str(box.label))
    assert "옛 배포 리비전 r3" in str(confirm.label)
    assert not confirm.value
    assert app.button(key=CONTINUE_BUTTON_KEY).disabled
    assert repository.legacy_trace_count() == 2
