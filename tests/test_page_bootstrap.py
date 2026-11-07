# Purpose: 계산 페이지 공통 준비 절차의 조회기간 해석과 예외 계약을 검증한다.

import duckdb
import pandas as pd
import pytest

from capa_simulation import alerts, page_bootstrap
from capa_simulation.navigation import REFERENCE_DATA
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PageContext,
    calculation_stop_notice,
    resolve_effective_months,
)
from capa_simulation.reference_grid_keys import DATASETS
from capa_simulation.scenario_preset_state import MONTH_RANGE_KEY
from capa_simulation.scenario_state import pristine_content_token
from capa_simulation.services import unit_capacity
from capa_simulation.services.simulation_cache import outside_period_error


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


def _service_stop(status: int, table: str = "RQ_RUN_RATE", column: str = "CAPA_RUN_RATE") -> str:
    """계산이 실제로 내는 오류 글 — 글이 바뀌면 판정이 조용히 빗나가지 않게 여기서 받는다."""
    joined = pd.DataFrame({"공정": ["DEMO-P1"], "상태": [status]})
    check = unit_capacity._PendingCheck(table, column, ["공정"], "상태", None)
    with pytest.raises(ValueError) as error:
        unit_capacity._raise_on_unusable_values(joined, check)
    return str(error.value)


def _on_page(monkeypatch: pytest.MonkeyPatch, page: str = "HOME") -> None:
    monkeypatch.setattr(alerts, "current_page", lambda: (page, "home"))


@pytest.mark.parametrize(
    ("table", "column", "name"),
    [
        ("RQ_RUN_RATE", "CAPA_RUN_RATE", "효율"),
        ("RQ_VITAL", "편중률", "여유율"),
        ("RQ_RUN_DAY", "RUN_DAY", "일수"),
        ("RQ_LOT_RATIO", "Lot 측정률", "Lot측정률"),
    ],
)
def test_a_blank_stop_points_at_the_table_to_fill_on_the_reference_screen(
    monkeypatch: pytest.MonkeyPatch, table: str, column: str, name: str
) -> None:
    """빈 칸 멈춤은 무엇을 · 어디서 채우는지 말하고 「그 화면으로」 가 기준 정보의 그 표를 연다
    (UI-NTF-06 · UI-NTF-08). 전문은 어느 화면의 일인지부터 적고, 건수 · 예시 행은 남기되 표 이름은
    화면 이름이다."""
    _on_page(monkeypatch)
    stop = calculation_stop_notice(
        ValueError(_service_stop(unit_capacity._VALUE_BLANK, table, column))
    )

    assert stop is not None
    assert stop.text == f"대당 Capa 계산 멈춤 — 기준 정보 「{name}」 빈 칸 1건을 채움"
    assert DATASETS[table] == name
    assert stop.goto == ("기준 정보", REFERENCE_DATA.href, name)
    assert stop.message.startswith(
        f"HOME — 대당 Capa 계산이 멈췄습니다. 기준 정보 「{name}」 표의 "
    )
    assert "「변경사항 적용」" in stop.message
    assert f"「{name}」 표의 빈 칸: 1건, 예시 " in stop.message
    assert "'공정': 'DEMO-P1'" in stop.message
    assert table not in stop.message and column not in stop.message


def test_a_row_missing_from_the_reference_table_is_the_same_empty_cell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """연결값 없음도 빠진 입력이다 — 기준 정보 표의 같은 빈 칸을 채워 푼다."""
    _on_page(monkeypatch)
    stop = calculation_stop_notice(ValueError(_service_stop(unit_capacity._VALUE_NO_MATCH)))

    assert stop is not None
    assert stop.text == "대당 Capa 계산 멈춤 — 기준 정보 「효율」 빈 칸 1건을 채움"


def test_a_stop_outside_the_period_keeps_saying_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """조회기간 밖 달의 빈 칸도 같은 곳에서 채운다 — 글 끝의 머리를 찾고 기간 말은 전문에 남는다."""
    _on_page(monkeypatch)
    error = outside_period_error(202601, 202612, _service_stop(unit_capacity._VALUE_BLANK))

    stop = calculation_stop_notice(ValueError(error))

    assert stop is not None
    assert stop.text == "대당 Capa 계산 멈춤 — 기준 정보 「효율」 빈 칸 1건을 채움"
    assert "밖의 달에 기준정보 오류가 있어" in stop.message
    assert "RQ_RUN_RATE" not in stop.message


def test_a_stop_without_a_page_name_starts_from_the_stop_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _on_page(monkeypatch, "")
    stop = calculation_stop_notice(ValueError(_service_stop(unit_capacity._VALUE_BLANK)))

    assert stop is not None and stop.message.startswith("대당 Capa 계산이 멈췄습니다.")


@pytest.mark.parametrize(
    "error",
    [
        duckdb.IOException("Could not set lock on file: Conflicting lock is held"),
        duckdb.CatalogException("Table with name RQ_RUN_RATE does not exist"),
        OSError("읽지 못함"),
        RuntimeError("활성 리비전이 없습니다."),
        KeyError("RQ_REQB"),
        ValueError("선택 범위에 소요대수 산출 기준이 없습니다. (데이터 범위 26.01–26.12)"),
        ValueError("RQ_YLD의 수율 값이 비었습니다: 1건"),
        ValueError("RQ_RUN_RATE의 CAPA_RUN_RATE 컬럼에 숫자가 아닌 값이 있습니다: 1건, 예시 []"),
        ValueError("RQ_RUN_RATE의 CAPA_RUN_RATE 값은 0보다 커야 합니다: 1건, 예시 []"),
        ValueError("RQ_MODULE의 모듈수 값이 빈 대당 Capa 기준이 있습니다: 1건, 예시 []"),
        duckdb.Error("RQ_RUN_RATE의 CAPA_RUN_RATE 값이 빈 대당 Capa 기준이 있습니다: 1건, 예시 []"),
    ],
)
def test_other_failures_have_no_screen_to_fill_and_keep_the_plain_message(
    error: BaseException,
) -> None:
    """DB 잠금 · 읽기 실패 · 자료 없는 달은 같은 `except` 로 오지만 채울 화면이 없다. 앱에서 고칠 수
    없는 모듈수와 빠진 입력이 아닌 값도 기준 정보로 보내지 않는다 — 부르는 쪽이 지금 글을 그대로
    쓴다."""
    assert calculation_stop_notice(error) is None


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
