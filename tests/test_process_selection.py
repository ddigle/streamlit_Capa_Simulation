# Purpose: 포함 공정 판정이 저장값·새 공정·첫 렌더에서 각각 무엇을 고르는지 고정한다.

"""포함 공정 판정의 계약.

저장되는 것은 포함 목록이라 "끈 공정" 과 "처음 보는 공정" 이 구분되지 않는다. 직전 옵션
집합이 그 구분을 만들어 주는데, 첫 렌더에는 그것이 없다.
"""

from capa_simulation.services.process_selection import resolve_included_processes

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


def test_a_saved_process_that_no_longer_exists_is_dropped() -> None:
    """지워진 공정이 남아 있어도 옵션에 없으면 고를 수 없다."""
    assert resolve_included_processes(["AVI", "사라진공정"], OPTIONS, OPTIONS) == ["AVI"]


def test_an_empty_seen_list_is_not_the_same_as_no_baseline() -> None:
    """`seen` 이 빈 목록인 것은 '직전에 옵션이 없었다' 는 관측이라 전부 새 공정이다."""
    assert resolve_included_processes(["AVI"], OPTIONS, []) == OPTIONS


def test_the_option_order_is_kept() -> None:
    """차례는 옵션 목록이 정한다. 저장값의 차례를 따라가면 화면이 흔들린다."""
    assert resolve_included_processes(["Molding", "AVI"], OPTIONS, OPTIONS) == ["AVI", "Molding"]
