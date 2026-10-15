# Purpose: 포함 공정 판정이 저장값·새 공정·첫 렌더·보이지 않는 공정에서 무엇을 고르는지 고정한다.

"""포함 공정 판정의 계약.

저장되는 것은 포함 목록이라 "끈 공정" 과 "처음 보는 공정" 이 구분되지 않는다. 이 세션이 아는
공정 집합이 그 구분을 만들어 주는데, 첫 렌더에는 그것이 없다. 이번 조회기간에 보이지 않는 공정은
지우지 않는다 — 리비전 프리셋에 그대로 실려야 공식버전 자동 갱신이 그 공정을 「사람이 끈 공정」으로
잘못 이어받지 않는다.
"""

from capa_simulation.services.process_selection import (
    apply_dialog_selection,
    remember_known_processes,
    resolve_included_processes,
    visible_processes,
)

OPTIONS = ["AVI", "Burn-In", "Cure", "Molding"]


def test_the_first_render_trusts_the_saved_list() -> None:
    """공식버전이 저장해 둔 공정 필터가 새 세션의 첫 화면에서 살아 있어야 한다.

    첫 렌더에는 직전 옵션 집합이 없다. 그때 '처음 보는 공정은 포함' 규칙을 그대로 쓰면
    **모든 공정이 처음 보는 공정**이 되어 저장된 포함 목록이 통째로 덮인다.
    """
    assert resolve_included_processes(["AVI", "Cure"], OPTIONS, None) == ["AVI", "Cure"]


def test_a_process_that_appeared_since_the_last_render_is_included() -> None:
    """시나리오를 바꾸거나 과거를 넣어 공정이 늘면 그 공정은 포함한다. 빠지면 B/N 이 틀린다."""
    seen = ["AVI", "Burn-In", "Cure"]

    assert resolve_included_processes(["AVI"], OPTIONS, seen) == ["AVI", "Molding"]


def test_a_process_the_user_turned_off_stays_off() -> None:
    """직전에도 있던 공정을 끈 것은 사용자의 선택이다. 다시 켜지 않는다."""
    assert resolve_included_processes(["AVI"], OPTIONS, OPTIONS) == ["AVI"]


def test_a_saved_process_outside_the_options_is_kept_behind_the_options() -> None:
    """이번 선택지에 없는 저장값은 지우지 않고 뒤에 둔다 — 화면은 `visible_processes` 만 읽는다.

    조회기간 안에 가용 행이 없는 공정은 사람이 토글할 수 없었다. 지우면 그 세션이 저장한 리비전
    프리셋에서 조용히 빠진다(2026-10-15 자동 갱신 리뷰). 저장소에 없는 공정은 프리셋을 만들 때
    `RQ_REQB` 로 거른다(`capture_scenario_preset`).
    """
    selection = resolve_included_processes(["숨은공정", "AVI"], OPTIONS, OPTIONS)

    assert selection == ["AVI", "숨은공정"]
    assert visible_processes(selection, OPTIONS) == ["AVI"]


def test_an_empty_seen_list_is_not_the_same_as_no_baseline() -> None:
    """`seen` 이 빈 목록인 것은 '직전에 옵션이 없었다' 는 관측이라 전부 새 공정이다."""
    assert resolve_included_processes(["AVI"], OPTIONS, []) == OPTIONS


def test_the_option_order_is_kept() -> None:
    """차례는 옵션 목록이 정한다. 저장값의 차례를 따라가면 화면이 흔들린다."""
    assert resolve_included_processes(["Molding", "AVI"], OPTIONS, OPTIONS) == ["AVI", "Molding"]


def test_narrowing_and_widening_the_period_does_not_revive_an_off_process() -> None:
    """좁혔다 넓혀 다시 보인 공정은 새 공정이 아니다 — 아는 공정은 쌓인다.

    프리셋을 건 직후(`seen` 없음)에는 리비전의 `RQ_REQB` 공정에서 출발한다. 그래서 첫 화면의 좁은
    조회기간에 보이지 않던 공정도 이미 아는 공정이다.
    """
    universe = ["A", "B", "P"]
    saved = ["A", "B", "Q"]  # P 는 프리셋이 뺀 공정, Q 는 지금 기간에 보이지 않는 포함 공정
    narrow = ["A", "B"]
    wide = ["A", "B", "P", "Q"]

    first = resolve_included_processes(saved, narrow, None)
    known = remember_known_processes(None, narrow, universe)
    assert first == ["A", "B", "Q"]
    assert known == ["A", "B", "P"]

    widened = resolve_included_processes(first, wide, known)
    known = remember_known_processes(known, wide)
    assert widened == ["A", "B", "Q"]
    assert "P" not in widened

    narrowed = resolve_included_processes(widened, narrow, known)
    known = remember_known_processes(known, narrow)
    again = resolve_included_processes(narrowed, wide, known)
    assert again == ["A", "B", "Q"]


def test_a_process_new_to_the_session_is_still_included_after_widening() -> None:
    """리비전에도, 이 세션에도 없던 공정(과거 구간 입력 등으로 생긴 것)은 여전히 포함한다."""
    known = remember_known_processes(None, ["A"], ["A", "B"])

    assert resolve_included_processes(["A"], ["A", "B", "NEW"], known) == ["A", "NEW"]


def test_the_dialog_keeps_processes_it_could_not_show() -> None:
    """팝업의 「전체 OFF」·적용은 이번 선택지만 바꾼다. 보이지 않던 포함 공정은 그대로다."""
    assert apply_dialog_selection([], ["A", "B"], ["A", "B", "Q"]) == ["Q"]
    assert apply_dialog_selection({"B"}, ["A", "B"], ["A", "Q"]) == ["B", "Q"]
