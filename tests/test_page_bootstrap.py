# Purpose: 계산 페이지 공통 준비 절차의 조회기간 해석과 예외 계약을 검증한다.

import pandas as pd
import pytest

from capa_simulation import page_bootstrap
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, PageContext, resolve_effective_months


def _context(start: int, end: int) -> PageContext:
    return PageContext(
        reference_version=1,
        reference_tables={},
        display_order=pd.DataFrame(),
        active_scenario={},
        selected_start_month=start,
        selected_end_month=end,
    )


def _source(months: list[int]) -> pd.DataFrame:
    return pd.DataFrame({"생산계획년월": months, "값": [1.0] * len(months)})


def test_effective_months_are_the_intersection_with_the_source(monkeypatch) -> None:
    applied: list[tuple[int, int]] = []
    monkeypatch.setattr(
        page_bootstrap, "show_applied_month_range", lambda s, e: applied.append((s, e))
    )

    result = resolve_effective_months(
        _context(202601, 202612),
        _source([202603, 202606, 202609]),
        "RQ_REQB",
        empty_message="없음",
    )

    assert result == (202603, 202609)
    assert applied == [(202603, 202609)]


def test_disjoint_ranges_raise_the_page_specific_message(monkeypatch) -> None:
    monkeypatch.setattr(page_bootstrap, "show_applied_month_range", lambda s, e: None)

    with pytest.raises(ValueError, match="선택 범위에 소요대수 산출 기준이 없습니다"):
        resolve_effective_months(
            _context(202701, 202712),
            _source([202601, 202602]),
            "RQ_REQB",
            empty_message="선택 범위에 소요대수 산출 기준이 없습니다.",
        )


def test_bootstrap_errors_cover_every_failure_the_entry_sequence_can_raise() -> None:
    """활성 리비전이 없으면 RuntimeError 다. 페이지마다 다른 조합을 잡으면 새어나간다.

    `duckdb.Error` 가 빠지면 파일 잠금이 원문 트레이스백으로 뜬다 — IOException 의 MRO 에
    OSError 가 없다는 것을 09-04 기준선이 실측했다.
    """
    import duckdb

    assert set(BOOTSTRAP_ERRORS) == {
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        duckdb.Error,
    }
    assert issubclass(duckdb.IOException, BOOTSTRAP_ERRORS)


def test_month_range_falls_back_when_the_widget_state_is_missing_or_broken(monkeypatch) -> None:
    """`st.session_state` 전역을 교체하면 AppTest 기반 페이지 테스트를 오염시킨다.

    실제 Streamlit 런타임 없이 검증해야 하므로 모듈이 참조하는 `st` 만 바꿔치기한다.
    """

    class _FakeStreamlit:
        def __init__(self, state: dict[str, object]) -> None:
            self.session_state = state

    for broken in (
        {},
        {page_bootstrap.MONTH_RANGE_KEY: "202601"},
        {page_bootstrap.MONTH_RANGE_KEY: ("2026-01",)},
    ):
        monkeypatch.setattr(page_bootstrap, "st", _FakeStreamlit(broken))
        start, end = page_bootstrap.selected_month_range()
        assert start < end

    monkeypatch.setattr(
        page_bootstrap,
        "st",
        _FakeStreamlit({page_bootstrap.MONTH_RANGE_KEY: ("2026-03", "2026-08")}),
    )
    assert page_bootstrap.selected_month_range() == (202603, 202608)
