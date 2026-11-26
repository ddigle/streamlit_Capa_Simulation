# Purpose: 공용 공정 그룹 서비스의 그룹 차례 · 정규화 · 편집 표 줄 · 그룹 단추 묶음을 고정한다.

"""공정 그룹 서비스(`services/process_group.py`) — 순수 함수만 본다.

세 자리(저장 검증 · 편집 표 줄 · 그룹 단추)가 같은 열쇠 함수로 맞대는지, 그룹 낱말이 설비 마스터
「공정구분」 그룹 표기를 단추 차례로 들이는지, 쓰지 않는 그룹과 이번 선택지에 공정이 없는 그룹을
어떻게 가르는지 고정한다. 공정 이름은 모두 합성(`DEMO_*`)이다.
"""

from __future__ import annotations

import pandas as pd
import pytest

from capa_simulation.services.equipment_contract import LINE_TYPE_GROUPS
from capa_simulation.services.process_group import (
    PROCESS_GROUP_COLUMNS,
    PROCESS_GROUPS,
    ProcessGroupDuplicateError,
    assignments_from_editor,
    canonical_process_group,
    normalize_process_groups,
    process_group_buttons,
    process_group_duplicate_message,
    process_group_editor_frame,
    process_group_key,
    same_process_groups,
)
from capa_simulation.services.process_rename import DUPLICATE_REPORT_LIMIT

NBSP = "\u00a0"


# ---------------------------------------------------------------- 그룹 낱말 · 차례


def test_the_groups_follow_the_button_order_with_the_line_type_spellings() -> None:
    """단추 · 편집 칸 차례는 FRONT · PKG · MI · TEST · FDY · 물류이고 표기는 설비 마스터 공정구분
    그룹과 같다. 그쪽 낱말이 늘거나 줄거나 표기가 바뀌면 여기서 걸린다."""
    assert PROCESS_GROUPS == ("FRONT", "PKG", "MI", "TEST", "FDY", "물류")
    assert set(PROCESS_GROUPS) == set(LINE_TYPE_GROUPS)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("FRONT", "FRONT"),
        ("front", "FRONT"),
        (f" Pkg{NBSP}", "PKG"),
        ("물류", "물류"),
        ("", None),
        ("   ", None),
        (None, None),
        (float("nan"), None),
        (pd.NA, None),
    ],
)
def test_a_group_is_read_into_its_canonical_spelling(value: object, expected: str | None) -> None:
    assert canonical_process_group(value) == expected


def test_a_group_outside_the_list_is_refused_with_the_whole_list() -> None:
    with pytest.raises(ValueError, match="FRONT · PKG · MI · TEST · FDY · 물류 가운데") as caught:
        canonical_process_group("DEMO_X")

    assert str(caught.value).endswith(": DEMO_X")


# ---------------------------------------------------------------- 저장 정규화


def test_the_key_cleans_spaces_but_keeps_case() -> None:
    assert process_group_key(f"  DEMO{NBSP}DA ") == "DEMO DA"
    assert process_group_key("demo_da") != process_group_key("DEMO_DA")
    assert process_group_key(None) == ""


def test_normalizing_cleans_keys_drops_ungrouped_rows_and_sorts_by_process() -> None:
    normalized = normalize_process_groups(
        [
            ("DEMO_WB", "pkg"),
            (f" DEMO{NBSP}DA ", "FRONT"),
            ("DEMO_MOLD", None),
            ("DEMO_SAW", ""),
            ("", ""),
            (None, None),
        ]
    )

    assert normalized == (("DEMO DA", "FRONT"), ("DEMO_WB", "PKG"))


def test_processes_differing_only_in_case_are_kept_apart() -> None:
    normalized = normalize_process_groups([("DEMO_DA", "FRONT"), ("demo_da", "PKG")])

    assert dict(normalized) == {"DEMO_DA": "FRONT", "demo_da": "PKG"}


def test_the_same_process_on_two_rows_is_refused() -> None:
    with pytest.raises(ProcessGroupDuplicateError) as caught:
        normalize_process_groups([("DEMO_DA", "FRONT"), (f"DEMO_DA{NBSP}", "PKG")])

    assert caught.value.names == ("DEMO_DA",)
    assert str(caught.value) == "같은 공정이 두 줄입니다: DEMO_DA"
    assert isinstance(caught.value, ValueError)


def test_the_duplicate_message_lists_only_the_first_few_names() -> None:
    names = [f"DEMO_{index}" for index in range(DUPLICATE_REPORT_LIMIT + 2)]

    message = process_group_duplicate_message(names)

    assert f"DEMO_{DUPLICATE_REPORT_LIMIT - 1}" in message
    assert f"DEMO_{DUPLICATE_REPORT_LIMIT}" not in message


def test_a_group_on_a_blank_process_is_refused() -> None:
    with pytest.raises(ValueError, match="공정이 빈 줄"):
        normalize_process_groups([("  ", "FRONT")])


def test_a_group_outside_the_list_stops_normalizing() -> None:
    with pytest.raises(ValueError, match="가운데 하나입니다: DEMO_X"):
        normalize_process_groups([("DEMO_DA", "DEMO_X")])


def test_sameness_ignores_the_order() -> None:
    left = (("DEMO_DA", "FRONT"), ("DEMO_WB", "PKG"))

    assert same_process_groups(left, tuple(reversed(left)))
    assert not same_process_groups(left, (("DEMO_DA", "FRONT"),))
    assert not same_process_groups(left, (("DEMO_DA", "PKG"), ("DEMO_WB", "PKG")))


# ---------------------------------------------------------------- 편집 표


def test_the_editor_rows_follow_the_options_then_the_saved_processes_outside() -> None:
    """줄은 선택지 차례(원본 글자) 다음 선택지 밖 저장 공정(글자순)이다. 목록 밖 저장 그룹은
    빈 칸이다."""
    frame, outside = process_group_editor_frame(
        (("DEMO_DA", "FRONT"), ("DEMO_Z", "MI"), ("DEMO_B", "PKG"), ("DEMO_WB", "DEMO_OLD")),
        ["DEMO_WB", "DEMO_MOLD", f"DEMO_DA{NBSP}"],
    )

    assert list(frame.columns) == list(PROCESS_GROUP_COLUMNS)
    assert frame["공정"].tolist() == ["DEMO_WB", "DEMO_MOLD", f"DEMO_DA{NBSP}", "DEMO_B", "DEMO_Z"]
    assert frame["공정그룹"].tolist() == [None, None, "FRONT", "PKG", "MI"]
    assert outside == ("DEMO_B", "DEMO_Z")


def test_the_editor_shows_a_saved_process_with_an_unknown_group_as_ungrouped() -> None:
    frame, outside = process_group_editor_frame((("DEMO_OLD", "DEMO_X"),), ["DEMO_DA"])

    assert frame["공정"].tolist() == ["DEMO_DA", "DEMO_OLD"]
    assert frame["공정그룹"].tolist() == [None, None]
    assert outside == ("DEMO_OLD",)


def test_saving_the_editor_back_keeps_what_it_shows() -> None:
    """보이는 대로 저장 — 선택지 밖 저장 공정은 남고, 목록 밖 그룹 줄은 빈 칸이라 사라진다."""
    saved = (("DEMO_DA", "FRONT"), ("DEMO_OLD", "DEMO_X"), ("DEMO_Z", "MI"))
    frame, _ = process_group_editor_frame(saved, ["DEMO_DA", "DEMO_WB"])
    edited = frame.copy()
    edited.loc[edited["공정"] == "DEMO_WB", "공정그룹"] = "TEST"

    assert assignments_from_editor(edited) == (
        ("DEMO_DA", "FRONT"),
        ("DEMO_WB", "TEST"),
        ("DEMO_Z", "MI"),
    )


def test_an_unchanged_editor_is_the_same_as_the_saved_assignments() -> None:
    saved = (("DEMO_DA", "FRONT"), ("DEMO_Z", "MI"))
    frame, _ = process_group_editor_frame(saved, ["DEMO_WB", "DEMO_DA"])

    assert same_process_groups(assignments_from_editor(frame), saved)


def test_an_editor_frame_with_other_columns_is_refused() -> None:
    with pytest.raises(ValueError, match="공정 그룹 컬럼"):
        assignments_from_editor(pd.DataFrame({"공정": ["DEMO_DA"], "그룹": ["FRONT"]}))


def test_the_editor_without_options_or_assignments_is_empty() -> None:
    frame, outside = process_group_editor_frame((), [])

    assert frame.empty
    assert list(frame.columns) == list(PROCESS_GROUP_COLUMNS)
    assert outside == ()


# ---------------------------------------------------------------- 그룹 단추


def test_the_buttons_follow_the_group_order_and_the_option_order() -> None:
    buttons = process_group_buttons(
        (
            ("DEMO_MOLD", "PKG"),
            ("DEMO_DA", "FRONT"),
            ("DEMO_WB", "FRONT"),
            ("DEMO_TEST", "TEST"),
        ),
        ["DEMO_WB", "DEMO_TEST", "DEMO_MOLD", "DEMO_SAW", "DEMO_DA"],
    )

    assert buttons == (
        ("FRONT", ("DEMO_WB", "DEMO_DA")),
        ("PKG", ("DEMO_MOLD",)),
        ("TEST", ("DEMO_TEST",)),
    )


def test_an_unused_group_has_no_button_and_a_group_absent_now_has_no_members() -> None:
    """대응이 없는 그룹은 단추가 없다. 대응은 있는데 이번 선택지에 그 그룹 공정이 없으면 공정이 빈
    묶음으로 든다 — 화면이 그 단추를 잠근다."""
    buttons = process_group_buttons(
        (("DEMO_DA", "FRONT"), ("DEMO_LOG", "물류")),
        ["DEMO_DA", "DEMO_WB"],
    )

    assert buttons == (("FRONT", ("DEMO_DA",)), ("물류", ()))


def test_no_assignment_means_no_buttons() -> None:
    assert process_group_buttons((), ["DEMO_DA", "DEMO_WB"]) == ()


def test_a_saved_row_with_an_unknown_group_is_skipped_by_the_buttons() -> None:
    assert process_group_buttons((("DEMO_DA", "DEMO_X"),), ["DEMO_DA"]) == ()


def test_the_buttons_match_options_with_the_same_key_and_return_the_option_text() -> None:
    """선택지 쪽 U+00A0 · 앞뒤 공백도 맞대고, 값은 선택지의 원본 글자다(초안이 쓰는 값). 대소문자만
    다른 공정은 맞대지 않는다."""
    buttons = process_group_buttons(
        (("DEMO DA", "FRONT"),),
        [f"DEMO{NBSP}DA", "demo da"],
    )

    assert buttons == (("FRONT", (f"DEMO{NBSP}DA",)),)


def test_a_repeated_option_is_listed_once() -> None:
    buttons = process_group_buttons((("DEMO_DA", "FRONT"),), ["DEMO_DA", "DEMO_DA"])

    assert buttons == (("FRONT", ("DEMO_DA",)),)
