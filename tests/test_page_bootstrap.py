# Purpose: 계산 페이지 공통 준비 절차의 조회기간 해석과 예외 계약을 검증한다.

import pandas as pd
import pytest

from capa_simulation import page_bootstrap
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, PageContext, resolve_effective_months
from capa_simulation.scenario_preset_state import MONTH_RANGE_KEY
from capa_simulation.scenario_state import pristine_content_token


def _context(start: int, end: int) -> PageContext:
    return PageContext(
        reference_version=1,
        reference_tables={},
        display_order=None,
        active_scenario={
            "reference_version": 1,
            "revision": 0,
            "content_token": pristine_content_token(1),
            "tables": {},
        },
        selected_start_month=start,
        selected_end_month=end,
    )


def _source(months: list[int]) -> pd.DataFrame:
    return pd.DataFrame({"생산계획년월": months, "값": [1.0] * len(months)})


def test_effective_months_are_the_intersection_with_the_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_disjoint_ranges_raise_the_page_specific_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_database_error_message_follows_who_holds_the_lock() -> None:
    """잠금을 쥔 쪽에 맞는 조치를 권한다(E2E G1-D0).

    이 앱 자신이 쥔 잠금에 「다른 창을 닫으라」고 하면 틀린 조치다 — 한 서버가 모든 창을
    받으므로 닫을 창이 없고, 새로고침이면 이어진다.
    """
    import os
    from pathlib import Path

    import duckdb

    def lock_error(pid: int) -> duckdb.IOException:
        return duckdb.IOException(
            'IO Error: Cannot open file "x.duckdb": ???\r\n\n'
            f"File is already open in \nC:\\Python310\\python.exe (PID {pid})"
        )

    own = page_bootstrap.bootstrap_error_message(lock_error(os.getpid()))
    assert "새로고침" in own
    assert "닫을 필요는 없습니다" in own
    assert "다른 창에서 실행 중" not in own

    other_pid = os.getpid() + 1
    other = page_bootstrap.bootstrap_error_message(lock_error(other_pid))
    assert f"PID {other_pid}" in other
    assert "브라우저 창·탭 여러 개로 여는 것은 원인이 아닙니다" in other

    # 쥔 프로세스를 적지 않은 열기 실패(권한·없는 폴더·공유 위반)는 열기 안내 그대로다.
    opening = page_bootstrap.bootstrap_error_message(
        duckdb.IOException('IO Error: Cannot open file "x.duckdb": Permission denied')
    )
    assert opening.startswith("데이터베이스를 열지 못했습니다.")
    assert "파일 권한과 경로" in opening
    assert "원문" not in opening

    # 어느 파일인지는 부르는 쪽이 정한다.
    equipment = Path("equipment_availability.duckdb")
    assert f"`{equipment}`" in page_bootstrap.bootstrap_error_message(
        lock_error(other_pid), database_paths=(equipment,)
    )
    assert page_bootstrap.bootstrap_error_message(ValueError("한국어 문장")) == "한국어 문장"


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(
            'IO Error: Could not write file "x.duckdb.wal": No space left on device',
            id="disk-full",
        ),
        pytest.param(
            'IO Error: Could not write to file "x.duckdb" - attempted to write 0 bytes: '
            "File too large",
            id="file-size-limit",
        ),
    ],
)
def test_a_write_failure_says_nothing_was_saved_instead_of_closing_other_programs(
    error: str,
) -> None:
    """저장 중 디스크 가득·파일 크기 한도는 잠금이 아니다 — 닫을 프로그램이 없다.

    DuckDB 가 영문으로 박아 둔 「Could not write」로 가른다. 원문(종류 이름 + 문구)을 붙여
    원인을 보인다.
    """
    import duckdb

    message = page_bootstrap.bootstrap_error_message(duckdb.IOException(error))

    assert message.startswith(
        "데이터베이스에 쓰지 못했습니다 — 저장되지 않았습니다. "
        "디스크 공간과 쓰기 권한을 확인하세요."
    )
    assert "다른 프로그램" not in message
    assert "열지 못했습니다" not in message
    assert f"- 원문: ` IOException: {error} `" in message


def test_a_failed_commit_is_a_write_failure_whatever_its_exception_kind() -> None:
    """커밋 실패는 `TransactionException` 등으로도 온다 — 종류가 아니라 「Failed to commit」
    으로 가른다."""
    import duckdb

    message = page_bootstrap.bootstrap_error_message(
        duckdb.TransactionException("TransactionContext Error: Failed to commit: disk I/O error")
    )

    assert message.startswith("데이터베이스에 쓰지 못했습니다 — 저장되지 않았습니다.")
    assert "TransactionException: TransactionContext Error: Failed to commit" in message


def test_any_other_database_error_says_the_operation_failed_and_shows_the_original() -> None:
    """열기·잠금·쓰기가 아닌 실패(없는 표·깨진 파일 등)에 열기 조치를 권하지 않는다."""
    from pathlib import Path

    import duckdb

    error = duckdb.CatalogException(
        "Catalog Error: Table with name x does not exist!\n\nLINE 1: select * from x"
    )
    equipment = Path("equipment_availability.duckdb")
    message = page_bootstrap.bootstrap_error_message(error, database_paths=(equipment,))

    assert message.startswith("데이터베이스 작업이 실패했습니다.")
    assert f"- 파일: `{equipment}`" in message
    assert "파일 권한과 경로" not in message
    assert "다른 프로그램" not in message
    # 원문의 줄바꿈은 한 줄로 접는다 — 줄 머리의 글자가 마크다운 블록으로 읽히지 않게.
    assert (
        "- 원문: ` CatalogException: Catalog Error: Table with name x does not exist! "
        "LINE 1: select * from x `"
    ) in message


def test_the_original_text_is_cut_and_stays_literal_under_markdown() -> None:
    """원문은 종류 이름 + 앞 300자이고, 코드 표기라 `$`·`*`·`#` 가 수식·강조·제목이 되지 않는다.

    원문에 역따옴표가 있으면 그보다 긴 울타리로 싼다 — 같은 길이면 코드 표기가 중간에 닫힌다.
    """
    import duckdb

    long_message = page_bootstrap.bootstrap_error_message(duckdb.InternalException("가" * 1000))
    original = next(line for line in long_message.splitlines() if line.startswith("- 원문: "))
    assert original == f"- 원문: ` InternalException: {'가' * 300} … `"

    tricky = "Binder Error: `a` $x$ *b*\n# 제목\n- 목록 ``c``"
    message = page_bootstrap.bootstrap_error_message(duckdb.BinderException(tricky))
    lines = message.splitlines()
    original_lines = [line for line in lines if line.startswith("- 원문: ")]
    assert original_lines == [
        "- 원문: ``` BinderException: Binder Error: `a` $x$ *b* # 제목 - 목록 ``c`` ```"
    ]
    assert not any(line.startswith("#") for line in lines)


def test_month_range_falls_back_when_the_widget_state_is_missing_or_broken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`st.session_state` 전역을 교체하면 AppTest 기반 페이지 테스트를 오염시킨다.

    실제 Streamlit 런타임 없이 검증해야 하므로 모듈이 참조하는 `st` 만 바꿔치기한다.
    """

    class _FakeStreamlit:
        def __init__(self, state: dict[str, object]) -> None:
            self.session_state = state

    broken_states: tuple[dict[str, object], ...] = (
        {},
        {MONTH_RANGE_KEY: "202601"},
        {MONTH_RANGE_KEY: ("2026-01",)},
    )
    for broken in broken_states:
        monkeypatch.setattr(page_bootstrap, "st", _FakeStreamlit(broken))
        start, end = page_bootstrap.selected_month_range()
        assert start < end

    monkeypatch.setattr(
        page_bootstrap,
        "st",
        _FakeStreamlit({MONTH_RANGE_KEY: ("2026-03", "2026-08")}),
    )
    assert page_bootstrap.selected_month_range() == (202603, 202608)


def test_date_range_value_reads_every_shape_the_range_picker_returns() -> None:
    """범위 날짜 입력은 두 날짜·한 날짜·`date` 하나 중 무엇이든 돌려준다."""
    from datetime import date

    from capa_simulation.page_bootstrap import date_range_value

    default = (date(2026, 1, 1), date(2026, 1, 31))

    assert date_range_value((date(2026, 3, 2), date(2026, 3, 9)), default) == (
        date(2026, 3, 2),
        date(2026, 3, 9),
    )
    # 사용자가 시작일만 누른 중간 상태다. 한쪽만 잡고 계산하면 기간이 엉뚱해진다.
    assert date_range_value((date(2026, 3, 2),), default) == default
    assert date_range_value(date(2026, 3, 2), default) == (date(2026, 3, 2), date(2026, 3, 2))
    assert date_range_value(None, default) == default
    assert date_range_value("2026-03-02", default) == default


def test_prune_list_selection_drops_values_the_current_options_no_longer_have(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """옵션이 계산 결과라 시나리오·조회기간이 바뀌면 옛 선택이 옵션 밖으로 나간다."""

    class _FakeStreamlit:
        def __init__(self, state: dict[str, object]) -> None:
            self.session_state = state

    state: dict[str, object] = {"filter": ["A", "Z"]}
    monkeypatch.setattr(page_bootstrap, "st", _FakeStreamlit(state))
    assert page_bootstrap.prune_list_selection("filter", ["A", "B"]) == ["A"]
    assert state["filter"] == ["A"]

    # 아직 아무것도 고르지 않은 세션에는 기본값을 심는다.
    state.clear()
    assert page_bootstrap.prune_list_selection("filter", ["A", "B"], default=["B"]) == ["B"]
    assert state["filter"] == ["B"]

    # 값이 리스트가 아니면(앞 리비전이 남긴 찌꺼기) 기본값으로 되돌린다.
    state["filter"] = "A"
    assert page_bootstrap.prune_list_selection("filter", ["A", "B"]) == []
    assert state["filter"] == []
