# Purpose: Space 층 사용 규칙(사유 글 검증·동 머리·끄기 대상·층 거르기·호기 셈·경고)을 검증한다.

from __future__ import annotations

import pandas as pd
import pytest

from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.services.equipment_contract import (
    EQUIPMENT_ID_COLUMN,
    LAYOUT_EXITED_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
)
from capa_simulation.services.fab_layout import FLOOR_KEYS
from capa_simulation.services.floor_state import (
    ACTIVE_STATE,
    FLOOR_REASON_MAX_CHARS,
    FloorStates,
    building_active_count,
    building_state,
    floor_reason_code,
    floor_reason_refusal,
    floor_states_fingerprint,
    floor_unit_counts,
    floors_by_building,
    inactive_floor_summary,
    inactive_floor_warnings,
    inactive_label,
    master_location_options,
    newly_inactive,
    prepare_floor_states,
    selectable_floor_keys,
    with_building,
)


def _states(*rows: tuple[str, str, str], version: int = 1) -> FloorStates:
    return FloorStates(rows=prepare_floor_states({(b, f): r for b, f, r in rows}), version=version)


def test_prepare_keeps_floor_key_order_and_reads_blank_as_in_use() -> None:
    rows = prepare_floor_states(
        {("C5", "6F"): "NOT_LINE", ("C1", "3F"): "UNUSED", ("C2", "1F"): "", ("C2", "2F"): None}
    )
    assert rows == (("C1", "3F", "UNUSED"), ("C5", "6F", "NOT_LINE"))


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({("C6", "1F"): "UNUSED"}, "FAB 의 층이 아닙니다"),
        ({("C1", "7F"): "UNUSED"}, "FAB 의 층이 아닙니다"),
        ({("C1", "1F"): 3}, "C1 1F 층 사용 사유는 글이어야 합니다"),
        ({("C1", "1F"): "가" * 21}, "C1 1F 사유는 20자까지입니다\\(지금 21자\\)"),
        ({("C2", "3F"): "창고\n임시"}, "C2 3F 사유에 줄바꿈·탭 같은 제어 문자는"),
        ({("C2", "3F"): "창고\t임시"}, "제어 문자"),
        ({("C2", "3F"): "창고\u202e임시"}, "제어 문자"),
    ],
)
def test_prepare_refuses_unknown_floors_and_reasons(
    raw: dict[tuple[str, str], object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        prepare_floor_states(raw)


def test_prepare_stores_free_text_trimmed_and_legacy_labels_as_codes() -> None:
    """사유는 직접 적는 글이다(2026-10-26 결정) — 앞뒤 공백을 떼고 그대로 저장한다. 옛 코드의 글
    「사용 안 함」·「생산라인 아님」 을 그대로 적으면 그 코드다. 옛 코드도 그대로 받는다."""
    rows = prepare_floor_states(
        {
            ("C1", "1F"): "  설비 반입 대기  ",
            ("C1", "2F"): "생산라인 아님(사무·창고 등)",
            ("C1", "3F"): "사용 안 함",
            ("C1", "4F"): " 생산라인 아님 ",
            ("C1", "5F"): "NOT_LINE",
            ("C1", "6F"): "   ",
        }
    )
    assert rows == (
        ("C1", "1F", "설비 반입 대기"),
        ("C1", "2F", "생산라인 아님(사무·창고 등)"),
        ("C1", "3F", "UNUSED"),
        ("C1", "4F", "NOT_LINE"),
        ("C1", "5F", "NOT_LINE"),
    )


def test_prepare_takes_exactly_twenty_characters_after_trimming() -> None:
    twenty = "가나다라마바사아자차카타파하ABC-12"
    assert len(twenty) == FLOOR_REASON_MAX_CHARS
    assert prepare_floor_states({("C3", "2F"): f"  {twenty}  "}) == (("C3", "2F", twenty),)
    assert floor_reason_refusal(twenty) is None
    assert floor_reason_refusal(twenty + "!") == "사유는 20자까지입니다(지금 21자)"
    # 거절 글은 사람 글을 싣지 않는다(마크다운 자리 알림으로 간다).
    with pytest.raises(ValueError) as caught:
        prepare_floor_states({("C3", "2F"): "~취소선~" * 5})
    assert "~" not in str(caught.value)


def test_markdown_characters_are_stored_and_labelled_as_written() -> None:
    """마크다운 글자(물결표·별표·괄호·달러)도 적은 그대로다 — 막는 것은 그리는 자리의 몫."""
    text = "A~B~C *굵* [x](y)$1$"
    assert len(text) <= FLOOR_REASON_MAX_CHARS
    (row,) = prepare_floor_states({("C4", "5F"): text})
    assert row == ("C4", "5F", text)
    assert inactive_label(text) == text


def test_reason_code_reads_blank_as_no_reason() -> None:
    """편집표 칸 값 읽기 — 비면 None(화면은 끈 층을 「사용 안 함」 으로 채운다 — 페이지 시험), 옛
    글은 코드, 그 밖은 뗀 글. 저장 입구에서 빈 사유는 「사용」 이다."""
    for blank in (None, "", "   ", float("nan"), pd.NA):
        assert floor_reason_code(blank) is None
    assert floor_reason_code(" 사용 안 함 ") == "UNUSED"
    assert floor_reason_code("생산라인 아님") == "NOT_LINE"
    assert floor_reason_code(" 창고 ") == "창고"
    assert prepare_floor_states({("C1", "1F"): "  "}) == ()


def test_states_read_helpers() -> None:
    states = _states(("C1", "3F", "UNUSED"), ("C2", "1F", "NOT_LINE"))
    assert states.reason_of(("C1", "3F")) == "UNUSED"
    assert states.reason_of(("C1", "1F")) is None
    assert not states.is_active(("C2", "1F")) and states.is_active(("C2", "2F"))
    assert len(states.active_keys) == len(FLOOR_KEYS) - 2
    assert states.inactive == {("C1", "3F"): "UNUSED", ("C2", "1F"): "NOT_LINE"}


def test_building_head_value_and_count() -> None:
    draft = {("C1", floor): "NOT_LINE" for floor in ("1F", "2F", "3F", "4F", "5F", "6F")}
    draft[("C2", "3F")] = "UNUSED"
    assert building_state(draft, "C1") == "NOT_LINE"
    assert building_state(draft, "C3") == ACTIVE_STATE
    assert building_state(draft, "C2") is None
    assert building_active_count(draft, "C2") == (5, 6)
    mixed = {**draft, ("C1", "1F"): "UNUSED"}
    assert building_state(mixed, "C1") is None
    # 직접 적은 사유로 6개 층을 다 끈 동은 동 머리 값이 없다 — 「ACTIVE」 라고 적어도 「모두
    # 사용」 이 아니다.
    for written in ("창고", ACTIVE_STATE):
        typed = {("C4", floor): written for floor in ("1F", "2F", "3F", "4F", "5F", "6F")}
        assert building_state(typed, "C4") is None
        assert building_active_count(typed, "C4") == (0, 6)


def test_with_building_sets_or_clears_one_building_only() -> None:
    draft = {("C1", "3F"): "UNUSED", ("C5", "1F"): "UNUSED"}
    turned_off = with_building(draft, "C5", "NOT_LINE")
    assert {key for key in turned_off if key[0] == "C5"} == {
        key for key in FLOOR_KEYS if key[0] == "C5"
    }
    assert set(turned_off.values()) == {"UNUSED", "NOT_LINE"}
    assert turned_off[("C1", "3F")] == "UNUSED"
    assert with_building(draft, "C5", None) == {("C1", "3F"): "UNUSED"}
    assert with_building(draft, "C5", ACTIVE_STATE) == {("C1", "3F"): "UNUSED"}


def test_newly_inactive_skips_reason_changes() -> None:
    before = _states(("C1", "3F", "UNUSED"))
    draft = {("C1", "3F"): "NOT_LINE", ("C2", "1F"): "UNUSED"}
    assert newly_inactive(before, draft) == (("C2", "1F"),)


def test_fingerprint_follows_content_not_version() -> None:
    one = _states(("C1", "3F", "UNUSED"), version=1)
    two = _states(("C1", "3F", "UNUSED"), version=7)
    other = _states(("C1", "3F", "NOT_LINE"))
    assert floor_states_fingerprint(one) == floor_states_fingerprint(two)
    assert floor_states_fingerprint(one) != floor_states_fingerprint(other)
    assert floor_states_fingerprint(FloorStates()) != floor_states_fingerprint(one)
    # 사유 글에 가름표가 들어도 다른 내용은 다른 지문이다.
    split = FloorStates(rows=(("C1", "1F", "a|C1:2F:b"),))
    joined = FloorStates(rows=(("C1", "1F", "a"), ("C1", "2F", "b")))
    assert floor_states_fingerprint(split) != floor_states_fingerprint(joined)


def test_selectable_floor_keys_keeps_the_open_floor() -> None:
    states = _states(("C1", "3F", "UNUSED"), ("C2", "1F", "UNUSED"))
    keys = selectable_floor_keys(states)
    assert ("C1", "3F") not in keys and len(keys) == len(FLOOR_KEYS) - 2
    kept = selectable_floor_keys(states, keep=("C1", "3F"))
    assert ("C1", "3F") in kept and ("C2", "1F") not in kept
    assert list(kept) == [key for key in FLOOR_KEYS if key in set(kept)]


def test_master_location_options_drop_only_fully_inactive_values_but_keep_present_ones() -> None:
    whole_c5 = [("C5", floor, "NOT_LINE") for floor in ("1F", "2F", "3F", "4F", "5F", "6F")]
    every_6f = [(building, "6F", "UNUSED") for building in ("C1", "C2", "C3", "C4")]
    states = _states(*whole_c5, *every_6f, ("C1", "3F", "UNUSED"))
    buildings, floors = master_location_options(states, pd.DataFrame({"동": [], "층": []}))
    assert buildings == ["C1", "C2", "C3", "C4"]
    assert floors == ["1F", "2F", "3F", "4F", "5F"]  # 3F 는 짝(C1 3F)만 꺼져 남는다

    present = pd.DataFrame({"동": ["C5", None, "X9"], "층": ["6F", "1F", None]})
    buildings, floors = master_location_options(states, present)
    assert buildings == ["C1", "C2", "C3", "C4", "C5"]
    assert floors == ["1F", "2F", "3F", "4F", "5F", "6F"]


def test_floors_by_building_lists_active_floors() -> None:
    states = _states(("C1", "3F", "UNUSED"))
    by_building = floors_by_building(states)
    assert by_building["C1"] == ("1F", "2F", "4F", "5F", "6F")
    assert by_building["C2"] == ("1F", "2F", "3F", "4F", "5F", "6F")


def test_floor_unit_counts_count_units_not_rows() -> None:
    status = pd.DataFrame(
        {
            EQUIPMENT_ID_COLUMN: ["M-1", "M-2", "M-3", "M-4", "S-1", "S-2", "GONE", "OUT"],
            PARENT_EQUIPMENT_COLUMN: ["MAIN", "MAIN", "MAIN", "MAIN", None, None, None, None],
            "동": ["C1", "C1", "C1", "C1", "C1", "C1", "C1", "C9"],
            "층": ["3F"] * 7 + ["1F"],
            "레이아웃표시": ["Y", "Y", "Y", "Y", "N", "Y", "Y", "Y"],
            LAYOUT_EXITED_COLUMN: [False, False, False, False, False, False, True, False],
        }
    )
    assert floor_unit_counts(status) == {("C1", "3F"): 3}
    assert floor_unit_counts(status.iloc[0:0]) == {}


def test_inactive_floor_warnings_count_moved_and_new_rows_only() -> None:
    states = _states(("C1", "3F", "UNUSED"))
    saved = pd.DataFrame(
        {EQUIPMENT_ID_COLUMN: ["STAY", "MOVE"], "동": ["C1", "C2"], "층": ["3F", "1F"]}
    )
    master = pd.DataFrame(
        {
            EQUIPMENT_ID_COLUMN: ["STAY", "MOVE", "NEW", "ELSE"],
            "동": ["C1", "C1", "C1", "C2"],
            "층": ["3F", "3F", "3F", "2F"],
        }
    )
    (warning,) = inactive_floor_warnings(master, saved, states)
    assert warning.startswith("비활성 층으로 옮긴 호기 2대")
    assert "C1 3F 사용 안 함" in warning and "MOVE, NEW" in warning and "STAY" not in warning
    assert inactive_floor_warnings(saved, saved, states) == []
    assert inactive_floor_warnings(master, saved, FloorStates()) == []
    # 마크다운 자리에 그리는 화면은 사람 글(사유·호기 이름)을 막는 함수를 넘긴다.
    written = FloorStates(rows=(("C1", "3F", "창고~임시~*"),), version=1)
    (escaped,) = inactive_floor_warnings(master, saved, written, escape=literal_markdown)
    assert "C1 3F 창고\\~임시\\~\\*" in escaped
    (plain,) = inactive_floor_warnings(master, saved, written)
    assert "C1 3F 창고~임시~*" in plain


def test_labels_and_summary() -> None:
    assert inactive_label("UNUSED") == "사용 안 함"
    assert inactive_label("NOT_LINE") == "생산라인 아님"
    # 그 밖의 글은 적은 그대로(앞으로 사유를 더한 코드도 글로 보인다), 빈 사유만 「비활성」, 제어
    # 문자는 빈칸으로 그린다(손으로 넣은 행 — 읽기는 막지 않는다).
    assert inactive_label("FUTURE") == "FUTURE"
    assert inactive_label("창고 · 임시") == "창고 · 임시"
    assert inactive_label("") == "비활성"
    assert inactive_label("창고\n임시") == "창고 임시"
    assert inactive_label("가" * 30) == "가" * 30
    whole_c5 = [("C5", floor, "NOT_LINE") for floor in ("1F", "2F", "3F", "4F", "5F", "6F")]
    states = _states(
        ("C1", "3F", "UNUSED"), ("C1", "5F", "UNUSED"), ("C1", "6F", "UNUSED"), *whole_c5
    )
    assert inactive_floor_summary(states) == "C1 3F·5F~6F(사용 안 함) · C5 1F~6F(생산라인 아님)"
    assert inactive_floor_summary(FloorStates()) == ""
