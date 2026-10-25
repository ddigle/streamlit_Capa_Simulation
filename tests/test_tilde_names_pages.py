# Purpose: 물결표가 든 이름이 화면의 마크다운 자리에서 막혀 그려지는지 화면을 열어 검증한다.

"""화면 그물 — 물결표 이름.

「A~B~C」 는 물결표 둘이라 가운데가 지움선이 되고, 「10~12월 증설」 처럼 물결표 하나인 이름도 한
글에 두 번 나오면 짝이 맞는다(2026-10-26 E2E 1~3회차). 이름이 들어오는 길(바로 끼움·저장소 예외
글·문구를 짓는 함수)은 `tests/test_markdown_sink_guard.py` 가 코드로 막고, 이 시험은 그런 이름을
담은 DB 로 화면을 실제로 열어 **마크다운으로 그리는 요소**(마크다운·캡션·알림 상자·토스트·펼침/
팝오버/탭 라벨·위젯 라벨·풍선)에 막지 않은 이름이 남았는지 본다. 표·코드·HTML·고르기 칸 값처럼
마크다운이 아닌 요소는 보지 않는다 — 거기에 `\\~` 가 보이면 그것이 결함이다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_scenario_repository import _clone

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.components.literal_markdown import markdown_safe_tildes
from capa_simulation.equipment_scenario_activation import SELECTION_KEY
from capa_simulation.navigation import (
    ADMIN_AREA,
    ADMIN_BOX_PAGES,
    AVAILABLE_EQUIPMENT_STATUS,
    CONSTRAINT_SIMULATION,
    PROCESS_CAPA_DETAIL,
    REQUIRED_SHORTENING,
    SCENARIO_MANAGEMENT,
    SPACE_STATUS,
    PageSpec,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.repository import DuckDBScenarioRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"
VOC = ADMIN_BOX_PAGES[0]

# 화면에 나오는 사람이 지은 이름. 둘째 꼴은 물결표 하나 — 한 글에 두 번 나오면 짝이 맞는다.
SCENARIO_NAME = "시뮬~가정~A"
REVISION_NAME = "10~12월 증설"
EQUIPMENT_SCENARIO_NAME = "운영~일정~B"
EQUIPMENT_ASSUMPTION_NAME = "11~12월 증설"
EQUIPMENT_REVISION_NAME = "B~안~2"
UNIT_NAME = "NEW~01~C"
PROCESS_LABEL = "공정~표시~D"
VOC_TITLE = "VOC~제목~E"
NAMES = (
    SCENARIO_NAME,
    REVISION_NAME,
    EQUIPMENT_SCENARIO_NAME,
    EQUIPMENT_ASSUMPTION_NAME,
    EQUIPMENT_REVISION_NAME,
    UNIT_NAME,
    PROCESS_LABEL,
    VOC_TITLE,
)


@pytest.fixture(autouse=True)
def _fresh_caches() -> Iterator[None]:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


def _seed_scenario_database(path: Path) -> str:
    """내장 시드(공식) 위에 물결표 이름을 단다 — 시나리오·리비전·공정 표시명·VOC 제목. 이름을 바꾼
    공정 코드를 돌려준다."""
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    ensure_initial_scenario(repository)
    release = repository.latest_official_release()
    assert release is not None
    scenario = next(
        item for item in repository.list_scenarios() if item.scenario_id == release.scenario_id
    )
    repository.rename_scenario(scenario.scenario_id, SCENARIO_NAME)
    revision = next(
        item
        for item in repository.list_revisions(scenario.scenario_id)
        if item.revision_id == release.revision_id
    )
    repository.rename_revision(
        revision.revision_id, REVISION_NAME, expected_name=revision.revision_name
    )
    tables = repository.load_revision(release.revision_id).tables
    process = str(tables["RQ_REQB"]["공정"].dropna().astype(str).iloc[0])
    repository.replace_global_process_rename(
        pd.DataFrame({"공정": [process], "표시명": [PROCESS_LABEL]}), source="시험"
    )
    repository.create_voc_post(category="질문", title=VOC_TITLE, body="본문", author="시험")
    return process


def _seed_equipment_database(path: Path) -> str:
    """공식 설비 시나리오·호기·일정 리비전에 물결표 이름을 달고, 가정 시나리오 하나를 복제한다.
    세션이 볼 가정 시나리오 id 를 돌려준다."""
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    equipment = _equipment()
    equipment.loc[equipment.index[-1], "설비명"] = UNIT_NAME
    repository.save_snapshot(_baseline(), equipment, _downtime(), note="처음")
    official = repository.list_equipment_scenarios()[0]
    repository.rename_equipment_scenario(
        official.equipment_scenario_id,
        name=EQUIPMENT_SCENARIO_NAME,
        expected_name=official.scenario_name,
    )
    assert official.latest_schedule_revision_id is not None
    repository.rename_schedule_revision(
        official.latest_schedule_revision_id, name=EQUIPMENT_REVISION_NAME, expected_name=None
    )
    return _clone(repository, EQUIPMENT_ASSUMPTION_NAME).equipment_scenario_id


@pytest.fixture
def _app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[AppTest, str, str]:
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.settings as settings

    scenario_path = tmp_path / "scenario.duckdb"
    equipment_path = tmp_path / "equipment.duckdb"
    process = _seed_scenario_database(scenario_path)
    assumption = _seed_equipment_database(equipment_path)
    monkeypatch.setattr(settings, "DUCKDB_PATH", scenario_path)
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", equipment_path)
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    return AppTest.from_file(str(APP_PATH), default_timeout=300), process, assumption


def _walk(node: Any) -> Iterator[Any]:
    yield node
    children = getattr(node, "children", None)
    if isinstance(children, dict):
        for child in children.values():
            yield from _walk(child)


def _markdown_texts(app: AppTest) -> list[tuple[str, str]]:
    """마크다운으로 그리는 글 — (요소 종류, 글). 마크다운·캡션·알림·토스트 본문, 블록(펼침·팝오버·
    탭) 라벨, 위젯 라벨·풍선."""
    texts: list[tuple[str, str]] = []
    for node in _walk(app._tree):
        proto = getattr(node, "proto", None)
        if proto is None:
            continue
        kind = type(proto).__name__
        if kind in ("Markdown", "Alert", "Toast"):
            texts.append((kind, str(proto.body)))
        if kind == "Block":
            for field in ("expandable", "popover", "tab"):
                if proto.HasField(field):
                    texts.append((field, str(getattr(proto, field).label)))
            continue
        for field in ("label", "help"):
            if field in {item.name for item in proto.DESCRIPTOR.fields}:
                texts.append((f"{kind}.{field}", str(getattr(proto, field))))
    return texts


def _bare_names(app: AppTest) -> list[str]:
    return [
        f"{kind}: {text}" for kind, text in _markdown_texts(app) for name in NAMES if name in text
    ]


def _blocked_names(app: AppTest) -> set[str]:
    """막혀 그려진 이름 — 그물이 이름이 실제로 나오는 화면을 보고 있는지 확인한다."""
    texts = [text for _, text in _markdown_texts(app)]
    return {name for name in NAMES if any(markdown_safe_tildes(name) in text for text in texts)}


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _visit(
    app: AppTest, specs: tuple[PageSpec, ...]
) -> tuple[dict[str, list[str]], dict[str, set[str]]]:
    bare: dict[str, list[str]] = {}
    blocked: dict[str, set[str]] = {}
    for spec in specs:
        _ok(app.switch_page(spec.path).run())
        bare[spec.title] = _bare_names(app)
        blocked[spec.title] = _blocked_names(app)
    return bare, blocked


def test_tilde_names_are_blocked_on_every_markdown_element_of_the_main_screens(
    _app: tuple[AppTest, str, str],
) -> None:
    app, process, _ = _app
    _ok(app.run())
    bare = {"HOME": _bare_names(app)}
    blocked = {"HOME": _blocked_names(app)}
    for found, shown in (
        _visit(
            app,
            (
                SCENARIO_MANAGEMENT,
                AVAILABLE_EQUIPMENT_STATUS,
                SPACE_STATUS,
                REQUIRED_SHORTENING,
                ADMIN_AREA,
                VOC,
            ),
        ),
        _visit_with_process(app, process),
    ):
        bare.update(found)
        blocked.update(shown)

    assert not {page: found for page, found in bare.items() if found}
    # 그물이 이름이 나오는 화면을 실제로 봤다(막혀 그려진 이름).
    assert SCENARIO_NAME in blocked["HOME"]
    assert {SCENARIO_NAME, REVISION_NAME} <= blocked[SCENARIO_MANAGEMENT.title]
    assert EQUIPMENT_SCENARIO_NAME in blocked[AVAILABLE_EQUIPMENT_STATUS.title]
    assert EQUIPMENT_SCENARIO_NAME in blocked[SPACE_STATUS.title]
    assert VOC_TITLE in blocked[VOC.title]
    assert PROCESS_LABEL in blocked[PROCESS_CAPA_DETAIL.title]
    assert PROCESS_LABEL in blocked[CONSTRAINT_SIMULATION.title]


def _visit_with_process(
    app: AppTest, process: str
) -> tuple[dict[str, list[str]], dict[str, set[str]]]:
    app.query_params["process"] = process
    return _visit(app, (PROCESS_CAPA_DETAIL, CONSTRAINT_SIMULATION))


def test_tilde_names_are_blocked_in_an_assumption_equipment_session(
    _app: tuple[AppTest, str, str],
) -> None:
    """가정 설비 시나리오 세션 — 설비 화면 머리 알림·잠금 글·Space 머리 줄이 그 이름을 싣는다."""
    app, _, assumption = _app
    app.session_state[SELECTION_KEY] = {"scenario_id": assumption, "schedule_revision_id": None}
    _ok(app.run())
    bare, blocked = _visit(
        app,
        (AVAILABLE_EQUIPMENT_STATUS, SPACE_STATUS, REQUIRED_SHORTENING, SCENARIO_MANAGEMENT),
    )

    assert not {page: found for page, found in bare.items() if found}
    assert EQUIPMENT_ASSUMPTION_NAME in blocked[AVAILABLE_EQUIPMENT_STATUS.title]


def test_the_net_sees_a_bare_name_on_a_markdown_element() -> None:
    """그물이 실제로 걸리는지 — 막지 않은 이름은 잡고, 막은 이름·마크다운이 아닌 요소는 지나간다."""
    script = f"""
import streamlit as st
from capa_simulation.components.literal_markdown import quoted
st.caption("{SCENARIO_NAME} 저장")
st.warning(f"{{quoted({REVISION_NAME!r})}} 은 막았다")
st.code("{UNIT_NAME}")
st.text("{VOC_TITLE}")
with st.expander("{PROCESS_LABEL}"):
    st.button("눌러", help="{EQUIPMENT_REVISION_NAME}")
"""
    app = _ok(AppTest.from_string(script, default_timeout=60).run())

    found = _bare_names(app)

    assert len(found) == 3, found
    assert any(SCENARIO_NAME in item for item in found)
    assert any(item.startswith("Expandable.label:") for item in found)
    assert any(EQUIPMENT_REVISION_NAME in item for item in found)
