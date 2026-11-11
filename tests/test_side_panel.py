# Purpose: 편집기 두 칸 공용 틀 — 두 화면의 서식이 이름만 다르고 표지를 나눠 쓰지 않는지 본다.

"""`components/side_panel.py`(설계 규칙 UI-LAY-09 · UI-CON-04). 설비 마스터와 시나리오 목록 관리가
함께 쓴다 — 칸막이 · 접기 · 폭 기억 · 두 칸 서식의 수치와 식은 같고, 화면끼리 `<html>` 표지 ·
저장소를 나눠 쓰지 않는다. 설비 마스터는 떼기 전 이름을 그대로 둬 사용자의 폭 기억을 잃지 않는다.
칸막이 마운트 자체는 `tests/test_equipment_side_panel.py` 가 돌린다."""

from __future__ import annotations

from dataclasses import astuple

from capa_simulation.components import side_panel as sp
from capa_simulation.components.equipment_master_grid import MASTER_SIDE
from capa_simulation.components.scenario_list_grid import LIST_SIDE
from capa_simulation.components.scenario_list_state import SIDE_CHOICE_KEY, SIDE_NEXT_KEY


def test_the_equipment_master_keeps_its_names_so_the_saved_width_is_not_lost() -> None:
    assert MASTER_SIDE.store == "capa-equipment-side-v1"
    assert MASTER_SIDE.css_name == "emd"
    assert MASTER_SIDE.frame_key == "equipment_master_frame"
    assert MASTER_SIDE.choice_key == "equipment_master_side_v1"
    assert MASTER_SIDE.next_key == "equipment_master_side_next_v1"
    assert MASTER_SIDE.reveal_key == "equipment_master_side_reveal_v1"
    assert MASTER_SIDE.splitter_key == "equipment_master_side_splitter"
    assert (MASTER_SIDE.default_share, MASTER_SIDE.default_offset_px) == (0.3, 28)


def test_the_two_screens_do_not_share_a_mark_a_key_or_a_store() -> None:
    assert not set(astuple(MASTER_SIDE)[:10]) & set(astuple(LIST_SIDE)[:10])
    assert MASTER_SIDE.store != LIST_SIDE.store
    assert MASTER_SIDE.css_name != LIST_SIDE.css_name
    assert (LIST_SIDE.choice_key, LIST_SIDE.next_key) == (SIDE_CHOICE_KEY, SIDE_NEXT_KEY)


def _renamed(style: str) -> str:
    """목록 관리 서식의 이름을 설비 마스터 이름으로 — 다른 것은 처음 폭과 고르기 여백뿐이어야
    한다."""
    return (
        style.replace(sp.choice_padding_rule(LIST_SIDE), "")
        .replace("scenario_list_", "equipment_master_")
        .replace("--sls-", "--emd-")
        .replace("data-sls-side", "data-emd-side")
        .replace("calc(40% - 0px)", "calc(30% - 28px)")
    )


def test_the_two_layouts_differ_only_by_names_and_the_first_width() -> None:
    assert _renamed(sp.side_layout_style(LIST_SIDE)) == sp.side_layout_style(MASTER_SIDE)
    # 처음 폭 — 이 화면만 줄의 40%. 한계는 같다.
    assert sp.side_bounds(LIST_SIDE)["defaultShare"] == 0.4
    assert sp.side_bounds(LIST_SIDE)["defaultOffset"] == 0
    for name in ("minPx", "minShare", "maxPx", "maxShare"):
        assert sp.side_bounds(LIST_SIDE)[name] == sp.side_bounds(MASTER_SIDE)[name]
    assert "var(--sls-side-w, calc(40% - 0px))" in sp.side_width_rule(LIST_SIDE)


def test_only_the_scenario_list_narrows_its_choice_buttons() -> None:
    """칸 고르기 단추 좌우 안쪽 여백은 시나리오 목록 관리 칸 고르기에만 12px 로 좁힌다(2026-11-11
    입력 점검 검토 보드 F2 (라) — 고르기 다섯이 창 1283 의 처음 폭에서 한 줄). 설비 마스터 서식에는
    여백 규칙이 없다(Streamlit 기본 14px 그대로)."""
    rule = sp.choice_padding_rule(LIST_SIDE)
    assert rule == (
        f'.st-key-{SIDE_CHOICE_KEY} [data-testid="stButtonGroup"] button '
        "{ padding-left: 12px; padding-right: 12px; }"
    )
    assert rule in sp.side_layout_style(LIST_SIDE)
    assert sp.choice_padding_rule(MASTER_SIDE) == ""
    assert "padding-left: 12px" not in sp.side_layout_style(MASTER_SIDE)
    assert "stButtonGroup" not in sp.side_layout_style(MASTER_SIDE)
