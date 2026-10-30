# Purpose: 설비 시나리오 리비전 목록 한도(최근 n)와 그 밖까지 센 전체·출처별 수 한 줄을 검사한다.

"""설비 시나리오 리비전 목록은 최근 `SCHEDULE_REVISION_LIST_LIMIT` 줄까지다(시나리오 관리
「설비 시나리오」 구획 표·리비전 상자, 사이드바 팝업 라디오, 설비 마스터 탭 저장 이력). 이관
뒤 저장이 쌓이면 이관 리비전이 한도 밖으로 밀려 표를 세어서는 「리비전 N줄 = 이관 N」 을 견줄
수 없었다 — 한도는 그대로 두고, 표 아래 한 줄이 늘 전체 수와 출처별 수를 적고, 팝업·저장 이력은
한도에 걸렸을 때만 전체 수를 적는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_scenario_repository import OPERATIONS, _migrated, _request, _session, _set

from capa_simulation.components.equipment_data_workspace import (
    origin_count_words,
    revision_count_line,
)
from capa_simulation.components.equipment_scenario_status import DIALOG_REVISION_KEY
from capa_simulation.navigation import SPACE_STATUS
from capa_simulation.persistence import equipment_cache
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    load_equipment_schedule_revision_counts,
    load_equipment_schedule_revisions,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository


@pytest.fixture(autouse=True)
def _fresh_caches() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


def _migrated_and_saved(tmp_path: Path) -> DuckDBEquipmentRepository:
    """이관 리비전 셋(r1~r3) 위에 저장 한 번(r4) — 사내 「이관 70 + 저장 12」 의 작은 꼴."""
    repository = _migrated(tmp_path)
    session = _session(repository)
    repository.save_equipment(
        _request(session, equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-30"))
    )
    return repository


def _limit(monkeypatch: pytest.MonkeyPatch, rows: int) -> None:
    monkeypatch.setattr(equipment_cache, "SCHEDULE_REVISION_LIST_LIMIT", rows)


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _captions(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.caption]


# ── 글 ───────────────────────────────────────────────────────────────────────────────


def test_origin_words_follow_the_origin_order_and_skip_zero() -> None:
    assert origin_count_words({"save": 12, "legacy": 70, "restore": 0}) == "이관 70 · 저장 12"
    assert origin_count_words({"layout_clear": 1, "clone": 1}) == "복제 1 · 배치 차이 정리 1"
    # 모르는 출처는 그 값 그대로 뒤에(이름 차례).
    assert origin_count_words({"zeta": 2, "save": 1, "alpha": 3}) == "저장 1 · alpha 3 · zeta 2"
    assert origin_count_words({"legacy": 1_234}) == "이관 1,234"
    assert origin_count_words({}) == ""


def test_the_count_line_says_the_whole_count_with_or_without_the_limit() -> None:
    origins = {"legacy": 70, "save": 10, "restore": 2}

    assert revision_count_line(50, origins, unit="줄", place="이 표와 「리비전」 상자") == (
        "최근 50줄 · 전체 82줄(이관 70 · 저장 10 · 되돌리기 2) — 더 옛 32줄은 이 표와 「리비전」 "
        "상자에 없습니다."
    )
    assert (
        revision_count_line(82, origins, unit="줄", place="이 표와 「리비전」 상자")
        == "전체 82줄(이관 70 · 저장 10 · 되돌리기 2)"
    )
    # 팝업은 출처 없이, 「개」 뒤 조사는 「는」.
    assert (
        revision_count_line(50, origins, unit="개", place="이 목록", by_origin=False)
        == "최근 50개 · 전체 82개 — 더 옛 32개는 이 목록에 없습니다."
    )
    assert revision_count_line(3, {"save": 3}, unit="개", place="이 목록", by_origin=False) == (
        "전체 3개"
    )
    # 셈이 목록보다 작게 와도(셈을 읽지 못한 칸) 목록 수 아래로 적지 않는다.
    assert revision_count_line(2, {}, unit="줄", place="이 표") == "전체 2줄"


# ── 저장소 · 캐시 ─────────────────────────────────────────────────────────────────────


def test_the_repository_counts_revisions_beyond_the_list_limit(tmp_path: Path) -> None:
    repository = _migrated_and_saved(tmp_path)

    assert [
        item.revision_no for item in repository.list_schedule_revisions(OPERATIONS, limit=2)
    ] == [
        4,
        3,
    ]
    assert repository.count_schedule_revisions_by_origin(OPERATIONS) == {"legacy": 3, "save": 1}
    assert repository.count_schedule_revisions_by_origin("없는 시나리오") == {}


def test_the_cached_counts_ride_with_the_limited_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """목록과 셈은 한 캐시 칸이다 — 목록이 한도에 걸려도 셈은 전체, 받은 dict 를 고쳐도 캐시는
    그대로."""
    database = str(_migrated_and_saved(tmp_path).database_path)
    _limit(monkeypatch, 2)

    assert [
        item.revision_no for item in load_equipment_schedule_revisions(database, OPERATIONS)
    ] == [
        4,
        3,
    ]
    counts = load_equipment_schedule_revision_counts(database, OPERATIONS)
    assert counts == {"legacy": 3, "save": 1}
    counts["legacy"] = 0
    assert load_equipment_schedule_revision_counts(database, OPERATIONS) == {"legacy": 3, "save": 1}


# ── 화면 ─────────────────────────────────────────────────────────────────────────────


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


def test_the_section_line_counts_the_migrated_revisions_past_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """표가 최근 2줄만 실어도(이관 r1·r2 가 밀림) 표 아래 한 줄이 전체 4줄과 이관 3 을 적는다 — 사내
    런북이 그 이관 수를 8-4s `L` 과 견준다."""
    path = _migrated_and_saved(tmp_path).database_path
    _limit(monkeypatch, 2)

    app = _ok(_section(path).run())

    (table,) = [frame for frame in app.dataframe if "리비전명" in frame.value.columns]
    assert table.value["리비전"].tolist() == ["r4", "r3"]
    assert table.value["출처"].tolist() == ["저장", "이관"]
    assert (
        "최근 2줄 · 전체 4줄(이관 3 · 저장 1) — 더 옛 2줄은 이 표와 「리비전」 상자에 없습니다."
        in _captions(app)
    )


def test_the_section_line_stands_even_when_every_revision_fits(tmp_path: Path) -> None:
    """한도 안이면 「전체 4줄(…)」 — 늘 서는 줄이라 그 아래 칸의 자리가 회차마다 같다."""
    path = _migrated_and_saved(tmp_path).database_path

    app = _ok(_section(path).run())

    (table,) = [frame for frame in app.dataframe if "리비전명" in frame.value.columns]
    assert len(table.value) == 4
    assert "전체 4줄(이관 3 · 저장 1)" in _captions(app)
    assert not any("최근" in text for text in _captions(app))


def _popup(database: str, page_file: str) -> None:
    from pathlib import Path

    from capa_simulation.components.equipment_scenario_status import (
        render_equipment_scenario_dialog_body,
    )

    render_equipment_scenario_dialog_body(Path(database), page_file=page_file)


def _popup_app(path: Path) -> AppTest:
    return AppTest.from_function(
        _popup, args=(str(path), Path(SPACE_STATUS.path).name), default_timeout=60
    )


def test_the_popup_says_the_whole_count_only_past_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _migrated_and_saved(tmp_path).database_path

    fits = _ok(_popup_app(path).run())
    assert len(fits.radio(key=DIALOG_REVISION_KEY).options) == 4
    assert not any("전체" in text for text in _captions(fits))

    _limit(monkeypatch, 2)
    clear_equipment_repository()
    limited = _ok(_popup_app(path).run())
    assert len(limited.radio(key=DIALOG_REVISION_KEY).options) == 2
    assert "최근 2개 · 전체 4개 — 더 옛 2개는 이 목록에 없습니다." in _captions(limited)


def _history(database: str) -> None:
    from capa_simulation.components.equipment_data_workspace import _render_history
    from capa_simulation.persistence.equipment_cache import get_equipment_repository

    _render_history(
        get_equipment_repository(database), scenario_id="operations", scenario_name="운영 일정"
    )


def test_the_save_history_names_the_hidden_revisions_only_past_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """설비 마스터 탭 저장 이력 — 머리 한 줄 끝에 붙인다(줄이 생기거나 빠지지 않는다)."""
    path = _migrated_and_saved(tmp_path).database_path

    fits = _ok(AppTest.from_function(_history, args=(str(path),), default_timeout=60).run())
    (head,) = [text for text in _captions(fits) if "의 일정 리비전" in text]
    assert "전체" not in head

    _limit(monkeypatch, 2)
    clear_equipment_repository()
    limited = _ok(AppTest.from_function(_history, args=(str(path),), default_timeout=60).run())
    (head,) = [text for text in _captions(limited) if "의 일정 리비전" in text]
    assert head.endswith(
        "리비전입니다. 최근 2줄 · 전체 4줄 — 더 옛 2줄은 이 표와 「조회 리비전」 상자에 없습니다."
    )
    # 일정 리비전 표 — 그 아래 「공통 대장 저장 이력」 표(「공통」 칸)도 변경메모를 싣는다.
    (table,) = [
        frame for frame in limited.dataframe if {"리비전", "변경메모"} <= set(frame.value.columns)
    ]
    assert table.value["리비전"].tolist() == ["r4", "r3"]
