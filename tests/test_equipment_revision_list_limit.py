# Purpose: 설비 시나리오 리비전 목록이 표·상자·저장 이력은 전부이고 팝업만 최근 n 인 것을 검사한다.

"""설비 시나리오 리비전 목록의 한도(2026-11-01 사용자 결정 A4 「표 · 상자는 전부, 팝업만 50」).

사내 리뷰 202610271800 사외 요청 4 — 리비전 목록이 네 곳 모두 최근 50줄까지라 이관 70 가운데
옛 32개는 어느 화면에서도 고를 수 없었다. 이제 시나리오 관리 「설비 시나리오」 구획의 리비전
표·리비전 상자와 설비 마스터 탭 저장 이력(표·「조회 리비전」 상자)은 전부 싣고, 한 줄씩 긴
사이드바 팝업 라디오만 최근 `SCHEDULE_REVISION_LIST_LIMIT` 개다 — 한도에 걸리면 라디오 아래 한
줄이 전체 수와 더 옛 리비전을 고르는 자리를 적는다. 구획 표 아래 한 줄은 늘 전체 수와 출처별 수를
적는다(사내 런북이 그 이관 수를 8-4s `L` 과 견준다).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_scenario_repository import OPERATIONS, _migrated, _request, _session, _set

from capa_simulation.components.equipment_data_workspace import (
    common_revision_words,
    origin_count_words,
    revision_count_line,
)
from capa_simulation.components.equipment_scenario_management import REVISION_KEY
from capa_simulation.components.equipment_scenario_status import DIALOG_REVISION_KEY
from capa_simulation.navigation import SPACE_STATUS
from capa_simulation.persistence import equipment_cache
from capa_simulation.persistence.equipment_cache import (
    SCHEDULE_REVISION_LIST_LIMIT,
    clear_equipment_repository,
    load_equipment_schedule_revision_counts,
    load_equipment_schedule_revisions,
    load_recent_equipment_schedule_revisions,
)
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentScheduleRevisionSummary,
)

# 한도(50)를 넘는 리비전 수 — 이관 셋(r1~r3) + 저장 r4 위에 SQL 로 복제한 저장을 얹는다.
PILED = SCHEDULE_REVISION_LIST_LIMIT + 10


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


def _piled(tmp_path: Path, total: int = PILED) -> DuckDBEquipmentRepository:
    """`_migrated_and_saved` 의 저장 r4 를 그 일정 행째 복제해 리비전을 `total` 개로 늘린 DB —
    저장을 수십 번 돌리지 않고 한도 밖을 만든다(공식 v1 = 이관 r3 은 한도 밖으로 밀린다)."""
    repository = _migrated_and_saved(tmp_path)
    path = str(repository.database_path)
    clear_equipment_repository()
    connection = duckdb.connect(path)
    try:
        (source,) = connection.execute(
            """SELECT schedule_revision_id FROM equipment_ops.equipment_schedule_revision
            WHERE equipment_scenario_id = ? AND revision_no = 4""",
            [OPERATIONS],
        ).fetchone() or ("",)
        extra = total - 4
        connection.execute(
            """
            INSERT INTO equipment_ops.equipment_schedule_revision
            SELECT 'piled-' || CAST(g.i AS VARCHAR), s.equipment_scenario_id, 4 + g.i, NULL,
                   'DEMO 메모 ' || CAST(g.i AS VARCHAR), s.saved_by, 'save', s.common_revision_id,
                   NULL, s.schedule_hash, s.downtime_hash, s.created_at + INTERVAL (g.i) MINUTE,
                   s.layout_hash
            FROM equipment_ops.equipment_schedule_revision s, range(1, ? + 1) g(i)
            WHERE s.schedule_revision_id = ?
            """,
            [extra, source],
        )
        connection.execute(
            """
            INSERT INTO equipment_ops.equipment_schedule_snapshot
            SELECT 'piled-' || CAST(g.i AS VARCHAR), x.unit_key, x.vibration_table_date,
                   x.logistics_date, x.arrival_date, x.qual_date, x.removal_date,
                   x.relocation_date, x.scenario_memo
            FROM equipment_ops.equipment_schedule_snapshot x, range(1, ? + 1) g(i)
            WHERE x.schedule_revision_id = ?
            """,
            [extra, source],
        )
    finally:
        connection.close()
    piled = DuckDBEquipmentRepository(Path(path))
    piled.initialize()
    return piled


def _limit(monkeypatch: pytest.MonkeyPatch, rows: int) -> None:
    monkeypatch.setattr(equipment_cache, "SCHEDULE_REVISION_LIST_LIMIT", rows)


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _captions(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.caption]


def _numbers(labels: list[str]) -> list[str]:
    """선택지 글자의 리비전 번호 「r12」(뒤 꼬리 — 저장시각·공식·메모 — 는 뗀다)."""
    return [label.split(" · ")[0] for label in labels]


# ── 글 ───────────────────────────────────────────────────────────────────────────────


def test_origin_words_follow_the_origin_order_and_skip_zero() -> None:
    assert origin_count_words({"save": 12, "legacy": 70, "restore": 0}) == "이관 70 · 저장 12"
    assert origin_count_words({"layout_clear": 1, "clone": 1}) == "복제 1 · 배치 차이 정리 1"
    # 모르는 출처는 그 값 그대로 뒤에(이름 차례).
    assert origin_count_words({"zeta": 2, "save": 1, "alpha": 3}) == "저장 1 · alpha 3 · zeta 2"
    assert origin_count_words({"legacy": 1_234}) == "이관 1,234"
    assert origin_count_words({}) == ""


def test_the_count_line_says_the_whole_count_and_where_the_older_ones_are() -> None:
    origins = {"legacy": 70, "save": 10, "restore": 2}

    # 구획 표 — 늘 전부 싣는다.
    assert (
        revision_count_line(82, origins, unit="줄") == "전체 82줄(이관 70 · 저장 10 · 되돌리기 2)"
    )
    # 팝업 라디오 — 최근 50개, 출처 없이, 「개」 뒤 조사는 「는」, 더 옛 것을 고르는 자리.
    assert (
        revision_count_line(
            50, origins, unit="개", elsewhere="시나리오 관리 › 설비 시나리오", by_origin=False
        )
        == "최근 50개 · 전체 82개 — 더 옛 32개는 시나리오 관리 › 설비 시나리오에서 고릅니다."
    )
    # 자리를 주지 않으면 그 목록에 없다고만.
    assert revision_count_line(50, origins, unit="줄") == (
        "최근 50줄 · 전체 82줄(이관 70 · 저장 10 · 되돌리기 2) — 더 옛 32줄은 이 목록에 없습니다."
    )
    assert revision_count_line(3, {"save": 3}, unit="개", by_origin=False) == "전체 3개"
    # 셈이 목록보다 작게 와도(셈을 읽지 못한 칸) 목록 수 아래로 적지 않는다.
    assert revision_count_line(2, {}, unit="줄") == "전체 2줄"


def test_the_common_cell_uses_the_number_the_revision_row_carries() -> None:
    """리비전 표는 전부 싣는데 공통 대장 이력 목록은 최신 50개라, 옛 줄의 공통은 그 목록에 없다 —
    리비전 줄이 들고 온 공통 번호가 먼저이고, 그것이 없는 옛 캐시 값만 목록에서 찾는다."""
    created = datetime(2026, 10, 24)
    carried = EquipmentScheduleRevisionSummary(
        "s1", OPERATIONS, 1, "legacy", created, common_revision_id="c1", common_revision_no=7
    )
    old_cache = EquipmentScheduleRevisionSummary(
        "s2", OPERATIONS, 2, "save", created, common_revision_id="c2"
    )
    no_common = EquipmentScheduleRevisionSummary("s3", OPERATIONS, 3, "clone", created)

    assert common_revision_words(carried, {}) == "r7"
    assert common_revision_words(carried, {"c1": 99}) == "r7"
    assert common_revision_words(old_cache, {"c2": 4}) == "r4"
    assert common_revision_words(old_cache, {}) == ""
    assert common_revision_words(no_common, {"c1": 1}) == ""


# ── 저장소 · 캐시 ─────────────────────────────────────────────────────────────────────


def test_the_repository_lists_every_revision_unless_asked_for_a_limit(tmp_path: Path) -> None:
    repository = _piled(tmp_path)

    every = repository.list_schedule_revisions(OPERATIONS)
    assert [item.revision_no for item in every] == list(range(PILED, 0, -1))
    assert [
        item.revision_no for item in repository.list_schedule_revisions(OPERATIONS, limit=2)
    ] == [
        PILED,
        PILED - 1,
    ]
    # 줄마다 함께 본 공통 대장 번호를 싣는다 — 공통 대장 이력 목록(최신 50개)과 상관없이.
    numbers = {item.revision_id: item.revision_no for item in repository.list_revisions()}
    assert all(item.common_revision_id is not None for item in every)
    assert {item.common_revision_no for item in every} <= set(numbers.values())
    assert all(item.common_revision_no == numbers[str(item.common_revision_id)] for item in every)
    # 한 줄 읽기도 같은 투영이다(발행 두 번 누름이 목록을 읽지 않고 찾는다).
    oldest = every[-1]
    assert repository.schedule_revision_summary(oldest.schedule_revision_id) == oldest
    assert repository.schedule_revision_summary("없는 리비전") is None
    with pytest.raises(ValueError):
        repository.list_schedule_revisions(OPERATIONS, limit=0)


def test_the_cache_holds_every_revision_and_the_popup_takes_the_recent_head(
    tmp_path: Path,
) -> None:
    """목록·셈은 한 캐시 칸이다 — 전부 싣고, 팝업은 그 앞머리 최근 50개, 셈은 같은 줄에서 센다.
    받은 dict 를 고쳐도 캐시는 그대로."""
    database = str(_piled(tmp_path).database_path)

    every = load_equipment_schedule_revisions(database, OPERATIONS)
    assert len(every) == PILED
    recent = load_recent_equipment_schedule_revisions(database, OPERATIONS)
    assert recent == every[:SCHEDULE_REVISION_LIST_LIMIT]
    counts = load_equipment_schedule_revision_counts(database, OPERATIONS)
    assert counts == {"legacy": 3, "save": PILED - 3}
    counts["legacy"] = 0
    assert load_equipment_schedule_revision_counts(database, OPERATIONS)["legacy"] == 3


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


def test_the_section_table_and_box_hold_every_revision_past_the_popup_limit(
    tmp_path: Path,
) -> None:
    """결정 A4 — 한도보다 많아도 구획 표·리비전 상자가 r1 까지 전부 싣는다. 한도 밖의 지금
    공식(저장 r4 — 저장이 공식으로 발행했다)도 표의 「공식」 칸과 상자 글자에 서고, 옛 리비전을
    상자에서 고를 수 있다. 표 아래 한 줄은 전체 수와 출처별 수 — 「최근 …」 이 서지 않는다."""
    repository = _piled(tmp_path)
    path = repository.database_path
    oldest = repository.list_schedule_revisions(OPERATIONS)[-1]
    release = repository.latest_equipment_release()
    assert release is not None and release.revision_no is not None
    assert release.revision_no <= PILED - SCHEDULE_REVISION_LIST_LIMIT
    official_row, official_mark = f"r{release.revision_no}", f"v{release.release_no}"

    app = _ok(_section(path).run())

    (table,) = [frame for frame in app.dataframe if "리비전명" in frame.value.columns]
    assert table.value["리비전"].tolist() == [f"r{number}" for number in range(PILED, 0, -1)]
    rows = table.value.set_index("리비전")
    assert rows.loc[official_row, "공식"] == official_mark
    assert rows.loc["r1", "출처"] == "이관"
    assert rows.loc["r1", "공통"] == "r1"
    captions = _captions(app)
    assert f"전체 {PILED}줄(이관 3 · 저장 {PILED - 3})" in captions
    assert not any(text.startswith("최근") for text in captions)

    box = app.selectbox(key=REVISION_KEY)
    assert len(box.options) == PILED
    assert _numbers(box.options)[-3:] == ["r3", "r2", "r1"]
    assert any(
        label.startswith(f"{official_row} · ") and f"공식 {official_mark}" in label
        for label in box.options
    )
    # 한도 밖의 옛 리비전을 고르면 아래 작업(불러오기 · 되돌리기 · …)이 그 리비전에 걸린다.
    box.select(oldest.schedule_revision_id)
    _ok(app.run())
    assert app.selectbox(key=REVISION_KEY).value == oldest.schedule_revision_id
    assert any("r1을 이 세션의 설비 시나리오로 올립니다" in text for text in _captions(app))


def test_the_section_ignores_the_popup_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """팝업 한도를 바꿔도 구획은 전부다 — 한도는 팝업 라디오만의 것."""
    path = _migrated_and_saved(tmp_path).database_path
    _limit(monkeypatch, 2)

    app = _ok(_section(path).run())

    (table,) = [frame for frame in app.dataframe if "리비전명" in frame.value.columns]
    assert table.value["리비전"].tolist() == ["r4", "r3", "r2", "r1"]
    assert table.value["출처"].tolist() == ["저장", "이관", "이관", "이관"]
    assert "전체 4줄(이관 3 · 저장 1)" in _captions(app)
    assert len(app.selectbox(key=REVISION_KEY).options) == 4


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


def test_the_popup_keeps_the_recent_fifty_and_points_to_the_section(tmp_path: Path) -> None:
    """팝업 라디오만 최근 50개 — 넘으면 라디오 아래 한 줄이 전체 수와 더 옛 리비전을 고르는
    자리(시나리오 관리 › 설비 시나리오)를 적는다. 화면 확인 스크립트는 그 줄의 「최근 n개 · 전체
    N개」 를 읽는다."""
    (tmp_path / "small").mkdir()
    (tmp_path / "piled").mkdir()
    small = _migrated_and_saved(tmp_path / "small").database_path
    fits = _ok(_popup_app(small).run())
    assert len(fits.radio(key=DIALOG_REVISION_KEY).options) == 4
    assert not any("전체" in text for text in _captions(fits))

    clear_equipment_repository()
    piled = _piled(tmp_path / "piled").database_path
    limited = _ok(_popup_app(piled).run())
    radio = limited.radio(key=DIALOG_REVISION_KEY)
    assert len(radio.options) == SCHEDULE_REVISION_LIST_LIMIT
    assert (
        f"최근 {SCHEDULE_REVISION_LIST_LIMIT}개 · 전체 {PILED}개 — 더 옛 "
        f"{PILED - SCHEDULE_REVISION_LIST_LIMIT}개는 시나리오 관리 › 설비 시나리오에서 고릅니다."
        in _captions(limited)
    )


def _history(database: str) -> None:
    from capa_simulation.components.equipment_data_workspace import _render_history
    from capa_simulation.persistence.equipment_cache import get_equipment_repository

    _render_history(
        get_equipment_repository(database), scenario_id="operations", scenario_name="운영 일정"
    )


def test_the_save_history_holds_every_revision(tmp_path: Path) -> None:
    """설비 마스터 탭 저장 이력 — 표와 「조회 리비전」 상자도 전부 싣는다(머리 한 줄에 한도 글이
    붙지 않는다)."""
    path = _piled(tmp_path).database_path

    app = _ok(AppTest.from_function(_history, args=(str(path),), default_timeout=60).run())

    (head,) = [text for text in _captions(app) if "의 일정 리비전" in text]
    assert head.endswith("공통 대장은 저장 때 함께 본 리비전입니다.")
    (table,) = [
        frame for frame in app.dataframe if {"리비전", "변경메모"} <= set(frame.value.columns)
    ]
    assert table.value["리비전"].tolist() == [f"r{number}" for number in range(PILED, 0, -1)]
    assert table.value.set_index("리비전").loc["r1", "공통"] == "r1"
    box = app.selectbox(key="equipment_history_revision_id_v4")
    assert len(box.options) == PILED
    assert _numbers(box.options)[-1] == "r1"


def _named_box(count: int, renamed: bool) -> None:
    """리비전 상자처럼 번호 큰 것부터 `count` 개 — `renamed` 면 맨 앞(최근) 항목의 글자가 바뀐다."""
    import streamlit as st

    from capa_simulation.page_bootstrap import prune_named_choice

    names = {
        f"rev-{number}": (
            f"r{number} · 새 이름" if renamed and number == count else f"r{number} · 옛 이름"
        )
        for number in range(count, 0, -1)
    }
    choice = prune_named_choice("named_box", names, default=f"rev-{count // 2}")
    st.write(f"{choice.value}|{choice.moved}")


def test_a_renamed_recent_choice_survives_a_box_longer_than_the_name_memory() -> None:
    """리비전 상자가 전부를 실으면(결정 A4) 선택지가 세션이 드는 지난 이름 상한(256)보다
    많다. 빠른 두 번 누름의 둘째 회차는 브라우저가 이름을 바꾸기 전 글자를 보내는데, 상한이 지금
    글자까지 지워 번호 큰 최근 리비전의 옛 글자를 잊으면 고름이 기본값으로 튀고 그 회차 누름이
    엉뚱한 리비전에 걸린다 — 지금 글자는 늘 든다."""
    count = 400
    app = AppTest.from_function(_named_box, args=(count, False), default_timeout=30)
    _ok(app.run())
    # 브라우저가 보낸 글자 — 이름을 바꾸기 전 최근 리비전의 글자.
    app.session_state["named_box"] = f"r{count} · 옛 이름"
    app.args = (count, True)
    _ok(app.run())

    assert app.markdown[0].value == f"rev-{count}|False"
