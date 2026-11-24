# Purpose: company bigdataquery adapter 관련 정상·예외·회귀 동작을 검증한다.

from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pandas as pd
import pytest
from bdq_login_support import (
    ACCOUNT,
    ADMIN_ID,
    MEASURED_INNER,
    MEASURED_OUTER,
    OTHER_ACCOUNT,
    PASSWORD,
    WRONG_PASSWORD,
    FakeBdq,
    measured_token_failure,
    requests_on,
    run_with_fake_package,
    running_mock,
    switch_on,
    target_of,
    use_fake_bdq,
)
from conftest import DEMO_CUSTOM_TABLE
from s3_mock_store import MockStore

from capa_simulation import module_helpers
from capa_simulation.io import bdq_login
from capa_simulation.io import bdq_login_store as login_store
from capa_simulation.io import company_bigdataquery_adapter as adapter
from capa_simulation.io.bdq_login_store import LoginSecret
from capa_simulation.io.s3_small import S3Target
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS
from capa_simulation.services.builtin_seed import (
    build_builtin_seed_dataset,
    load_builtin_display_order,
)
from capa_simulation.services.core_data_derivation import CUSTOM_BLANK
from capa_simulation.services.core_data_pipeline import (
    PreparedCoreDataset,
    prepare_core_data_dataset,
)
from capa_simulation.services.custom_source_check import CUSTOM_SOURCE_COLUMNS, SWITCHED_OFF_MEMO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "config" / "data_contract.json"


def _module(get_data: object) -> SimpleNamespace:
    return SimpleNamespace(getData=get_data)


# 시험의 CUSTOM 원천 표 이름(`DEMO_CUSTOM_TABLE` — `tests/conftest.py` 의 autouse 가 환경변수에 넣는
# 합성 값)의 두 조각 — 가린 글에 남지 않아야 하는 것이다.
DEMO_SCHEMA, DEMO_TABLE = DEMO_CUSTOM_TABLE.split(".")
# 본 조회문이 CUSTOM 칸에 싣는 상수 자리(합성) — 붙이기가 덮어야 하는 값이다.
QUERY_CONSTANT = "DEMO_CONSTANT"
CUSTOM_A = "DEMO_CUSTOM_A"
CUSTOM_B = "DEMO_CUSTOM_B"


def _answers(
    main: pd.DataFrame, custom: pd.DataFrame, *, asked: list[str] | None = None
) -> Callable[..., pd.DataFrame]:
    """두 조회 가짜 `getData` — 조회문에 CUSTOM 원천 표 이름이 있으면 둘째 답, 아니면 본 답(사본).
    `asked` 에 부른 조회문을 차례로 남긴다."""

    def get_data(*, param: str, **_kwargs: object) -> pd.DataFrame:
        if asked is not None:
            asked.append(param)
        return (custom if DEMO_CUSTOM_TABLE in param else main).copy()

    return get_data


def _custom_for(main: pd.DataFrame, values: Mapping[str, str] | None = None) -> pd.DataFrame:
    """본 표의 (Capa Code, 생산계획년월) 칸마다 행 수를 센 CUSTOM 원천 표 답 — 부품의 CUSTOM 은
    `values`(없으면 모든 부품 `CUSTOM_A`)."""
    cells = main.groupby(["Capa Code", "생산계획년월"]).size().rename("행수").reset_index()
    cells["CUSTOM"] = [
        CUSTOM_A if values is None else values[str(code)] for code in cells["Capa Code"]
    ]
    return cells.loc[:, list(CUSTOM_SOURCE_COLUMNS)]


def _one_custom_row() -> pd.DataFrame:
    """본 표와 맞대기 전에 멈추는 시험이 쓰는 한 줄 CUSTOM 원천 표 답."""
    return pd.DataFrame([("DEMO_CAPA_A", 202611, CUSTOM_A, 1)], columns=list(CUSTOM_SOURCE_COLUMNS))


def _part_columns(rows: int) -> dict[str, list[object]]:
    """본 프레임에 넣는 부품 칸 — Capa Code · 생산계획년월 · 조회문 상수 CUSTOM."""
    return {
        "Capa Code": ["DEMO_CAPA_A"] * rows,
        "생산계획년월": [202611] * rows,
        "CUSTOM": [QUERY_CONSTANT] * rows,
    }


def test_the_requester_account_reaches_get_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """환경변수에 계정이 있으면 `user_name` 으로 실려야 한다.

    사내 WebIDE 에서 이 값이 안 실려 조회가 통째로 막혀 있었다 — 로그인도 토큰도 정상인데
    `parameter user_name is necessary.` 만 돌아왔다.
    """
    captured: dict[str, object] = {}
    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, "  AD_ACCOUNT  ")
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _: _module(lambda **kwargs: captured.update(kwargs) or pd.DataFrame({"a": [1]})),
    )

    adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert captured["user_name"] == "AD_ACCOUNT", "앞뒤 공백을 떼고 넘겨야 한다"


def test_no_requester_account_means_no_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    """값이 없으면 **인자를 아예 넘기지 않는다.**

    Windows 에서는 패키지가 로그인 이름으로 요청자를 스스로 식별해 지금도 인자 없이 돈다.
    빈 문자열이나 `None` 을 넣으면 그 경로를 새로 깨는데, 그렇게 넣었을 때 어떻게 되는지는
    아무도 재지 않았다.
    """
    captured: dict[str, object] = {}
    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _: _module(lambda **kwargs: captured.update(kwargs) or pd.DataFrame({"a": [1]})),
    )

    adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert "user_name" not in captured
    assert set(captured) == {"param", "convert_type", "verbose"}


def test_a_rejected_blank_account_names_the_variable_to_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """서버가 빈값을 거부하면 패키지 문구 대신 채울 환경변수를 알려야 한다."""

    def refuse(**_kwargs: object) -> pd.DataFrame:
        raise ValueError("Parameter user_name is necessary.")

    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(refuse))

    with pytest.raises(RuntimeError, match=adapter.BDQ_USER_NAME_ENV):
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")


def test_an_unrelated_failure_is_not_disguised(monkeypatch: pytest.MonkeyPatch) -> None:
    """계정과 상관없는 실패까지 계정 안내로 바꾸면 진짜 원인이 가려진다. 감싸도 원문과 원래 예외는
    남는다."""
    original = ValueError("table not found")

    def refuse(**_kwargs: object) -> pd.DataFrame:
        raise original

    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(refuse))

    with pytest.raises(adapter.BigDataQueryCallError, match="table not found") as raised:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert adapter.BDQ_USER_NAME_ENV not in str(raised.value)
    assert raised.value.__cause__ is original
    assert (raised.value.kind, raised.value.type_names) == (
        adapter.QUERY_FAILURE_SQL,
        ("ValueError",),
    )


class Error(Exception):
    """사내 패키지가 내는 꼴 — 이름이 `Error` 하나뿐이고 화면이 잡는 예외 튜플 밖이다."""


def _chained(outer: BaseException, cause: BaseException) -> BaseException:
    outer.__cause__ = cause
    return outer


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (TimeoutError(), adapter.QUERY_FAILURE_TIMEOUT),
        (ConnectionResetError(), adapter.QUERY_FAILURE_CONNECTION),
        (Error("Read timed out"), adapter.QUERY_FAILURE_TIMEOUT),
        (Error("connect timeout"), adapter.QUERY_FAILURE_TIMEOUT),
        (Error("Connection refused"), adapter.QUERY_FAILURE_CONNECTION),
        (Error("AnalysisException: Could not resolve table reference"), adapter.QUERY_FAILURE_SQL),
        (Error(""), adapter.QUERY_FAILURE_OTHER),
        (_chained(Error(""), TimeoutError()), adapter.QUERY_FAILURE_TIMEOUT),
        (_chained(Error(""), Error("TTransportException")), adapter.QUERY_FAILURE_CONNECTION),
    ],
)
def test_a_failure_is_sorted_by_its_chain_names_and_words(error: BaseException, kind: str) -> None:
    """사내 리뷰 202610200720 — 「조회 실패(Error)」 만으로는 시간 초과인지 가를 수 없었다."""
    assert adapter.classify_query_failure(error) == kind


@pytest.mark.parametrize(
    ("error", "kind", "clue"),
    [
        (TimeoutError(), adapter.QUERY_FAILURE_TIMEOUT, ""),
        (Error("Read timed out"), adapter.QUERY_FAILURE_TIMEOUT, "timed out"),
        (Error("Error executing SQL statement"), adapter.QUERY_FAILURE_OTHER, "sql"),
        (Error("Query cancelled (SQLFetch)"), adapter.QUERY_FAILURE_OTHER, "cancel"),
        (Error("Memory limit exceeded (SQLFetch)"), adapter.QUERY_FAILURE_OTHER, "memory"),
        (Error("Syntax error in SQL statement"), adapter.QUERY_FAILURE_SQL, "syntax"),
        (Error("expired due to execution time limit"), adapter.QUERY_FAILURE_TIMEOUT, "time limit"),
        (Error("File does not exist: part-0001"), adapter.QUERY_FAILURE_SQL, "does not exist"),
        (
            Error("AnalysisException: Could not resolve table"),
            adapter.QUERY_FAILURE_SQL,
            "analysis",
        ),
        (Error(""), adapter.QUERY_FAILURE_OTHER, ""),
    ],
)
def test_a_failure_clue_is_the_vocabulary_word_that_sorted_it(
    error: BaseException, kind: str, clue: str
) -> None:
    """사내 리뷰 202610271800 — 판마다 다른 코드에서 간헐로 난 「SQL」 실패는 문법 오류가 아닐 수
    있다. 갈래를 정한 낱말(목록의 것 — 문구 원문이 아니다)을 함께 내 점검 스크립트가 적는다."""
    assert (adapter.classify_query_failure(error), adapter.query_failure_clue(error)) == (
        kind,
        clue,
    )
    wrapped = adapter.BigDataQueryCallError(error)
    assert (wrapped.kind, wrapped.clue) == (kind, clue)


@pytest.mark.parametrize(
    ("error", "seconds", "kind", "clue"),
    [
        (Error("Error executing SQL"), 907.4, adapter.QUERY_FAILURE_TIMEOUT, "오래 걸림 sql"),
        (Error(""), 907.4, adapter.QUERY_FAILURE_TIMEOUT, "오래 걸림"),
        (Error("Error executing SQL"), 14.1, adapter.QUERY_FAILURE_OTHER, "sql"),
        (Error("Error executing SQL"), None, adapter.QUERY_FAILURE_OTHER, "sql"),
        (Error("Syntax error"), 907.4, adapter.QUERY_FAILURE_SQL, "syntax"),
        (Error("Parse failure"), 907.4, adapter.QUERY_FAILURE_SQL, "parse"),
        (Error("AnalysisException"), 907.4, adapter.QUERY_FAILURE_SQL, "analysis"),
        (Error("Semantic error"), 907.4, adapter.QUERY_FAILURE_SQL, "semantic"),
        (Error("Connection reset"), 907.4, adapter.QUERY_FAILURE_CONNECTION, "connect"),
        (
            Error("SQL error: File does not exist"),
            907.4,
            adapter.QUERY_FAILURE_TIMEOUT,
            "오래 걸림 does not exist",
        ),
        (Error("table not found"), 907.4, adapter.QUERY_FAILURE_TIMEOUT, "오래 걸림 not found"),
        (
            Error("could not resolve"),
            907.4,
            adapter.QUERY_FAILURE_TIMEOUT,
            "오래 걸림 could not resolve",
        ),
        (Error("unknown column"), 907.4, adapter.QUERY_FAILURE_TIMEOUT, "오래 걸림 unknown column"),
        (Error("File does not exist"), 14.1, adapter.QUERY_FAILURE_SQL, "does not exist"),
        (Error("table not found"), None, adapter.QUERY_FAILURE_SQL, "not found"),
    ],
)
def test_only_a_failure_that_does_not_blame_the_query_text_becomes_a_timeout_after_a_long_wait(
    error: BaseException, seconds: float | None, kind: str, clue: str
) -> None:
    """같은 조회문이 짧은 창에서 선 뒤 907초 만에 실패한 꼴 — 조회문 거절이 아니다. `File does not
    exist` 는 긴 조회 중 다시 적재한 표에서도 나므로 함께 올린다. 문법 낱말과 연결은 그대로 둔다."""
    wrapped = adapter.BigDataQueryCallError(error, seconds=seconds)

    assert (wrapped.kind, wrapped.clue) == (kind, clue)
    if wrapped.kind == adapter.QUERY_FAILURE_TIMEOUT:
        assert "다시 해도 같으니" not in str(wrapped) and "기간을 줄여" in str(wrapped)


def test_the_advice_of_a_long_failure_is_to_wait_or_narrow_not_to_report_the_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`call_get_data` 가 잰 시간으로 갈린다 — 화면 안내가 「다시 해도 같으니」 로 끝나지 않는다."""

    def refuse(**_kwargs: object) -> pd.DataFrame:
        raise Error("Error executing SQL")

    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(refuse))

    with pytest.raises(adapter.BigDataQueryCallError) as quick:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")
    assert (quick.value.kind, quick.value.clue) == (adapter.QUERY_FAILURE_OTHER, "sql")
    assert "다시 해도 같으니" not in str(quick.value)

    monkeypatch.setattr(adapter, "LONG_FAILURE_SECONDS", 0.0)
    with pytest.raises(adapter.BigDataQueryCallError) as slow:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")
    assert (slow.value.kind, slow.value.clue) == (adapter.QUERY_FAILURE_TIMEOUT, "오래 걸림 sql")
    assert "기간을 줄여" in str(slow.value) and "다시 해도 같으니" not in str(slow.value)


class _SeenJoin(Future[object]):
    """기다리기 시작한 때를 알리는 결과 자리 — 시험이 잠으로 때맞추지 않게 한다."""

    joined = threading.Event()

    def result(self, timeout: float | None = None) -> object:
        type(self).joined.set()
        return super().result(timeout)


@pytest.fixture
def _seen_join(monkeypatch: pytest.MonkeyPatch) -> threading.Event:
    joined = threading.Event()
    monkeypatch.setattr(_SeenJoin, "joined", joined)
    monkeypatch.setattr(adapter, "Future", _SeenJoin)
    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    return joined


def test_the_same_query_pressed_again_while_it_runs_joins_it(
    _seen_join: threading.Event,
) -> None:
    """조회 중에 단추를 다시 눌러도 서버에 같은 조회가 겹치지 않는다. 기다린 쪽은 사본을 받고, 끝난
    뒤의 조회는 새로 묻는다 — 캐시가 아니다."""
    started = threading.Event()
    release = threading.Event()
    asked: list[object] = []
    answer = pd.DataFrame({"a": [1, 2]})

    def slow(**keywords: object) -> pd.DataFrame:
        asked.append(keywords["param"])
        started.set()
        assert release.wait(30)
        return answer

    module = _module(slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(adapter.call_get_data, module, "SELECT 1")
        assert started.wait(30)
        second = pool.submit(adapter.call_get_data, module, "SELECT 1")
        assert _seen_join.wait(30)
        release.set()
        owner, joined = first.result(30), second.result(30)

    assert asked == ["SELECT 1"]
    assert owner is answer
    assert isinstance(joined, pd.DataFrame) and joined is not answer
    pd.testing.assert_frame_equal(joined, answer)
    assert adapter._IN_FLIGHT == {}

    adapter.call_get_data(module, "SELECT 1")
    assert asked == ["SELECT 1", "SELECT 1"]


def test_a_failure_reaches_everyone_who_joined_and_the_next_press_asks_again(
    _seen_join: threading.Event,
) -> None:
    started = threading.Event()
    release = threading.Event()
    asked: list[object] = []

    def slow(**keywords: object) -> pd.DataFrame:
        asked.append(keywords["param"])
        started.set()
        assert release.wait(30)
        raise Error("Error executing SQL")

    module = _module(slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(adapter.call_get_data, module, "SELECT 1")
        assert started.wait(30)
        second = pool.submit(adapter.call_get_data, module, "SELECT 1")
        assert _seen_join.wait(30)
        release.set()
        for waited in (first, second):
            with pytest.raises(adapter.BigDataQueryCallError):
                waited.result(30)

    assert asked == ["SELECT 1"]
    assert adapter._IN_FLIGHT == {}

    with pytest.raises(adapter.BigDataQueryCallError):
        adapter.call_get_data(module, "SELECT 1")
    assert asked == ["SELECT 1", "SELECT 1"]


def _hung_then_answering(
    asked: list[object], started: threading.Event, release: threading.Event
) -> SimpleNamespace:
    """첫 부름은 `release` 까지 돌아오지 않고, 그 뒤 부름은 곧바로 답하는 패키지."""

    def getter(**keywords: object) -> pd.DataFrame:
        asked.append(keywords["param"])
        if len(asked) == 1:
            started.set()
            assert release.wait(30)
        return pd.DataFrame({"차례": [len(asked)]})

    return _module(getter)


def test_a_query_past_the_join_limit_is_not_joined_and_the_press_asks_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """돌아오지 않는 첫 조회가 그 조회문의 부름을 다 멈춰 세우지 않는다 — 다시 누르면 묻는다."""
    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(adapter, "IN_FLIGHT_JOIN_SECONDS", 0.0)
    asked: list[object] = []
    started = threading.Event()
    release = threading.Event()
    module = _hung_then_answering(asked, started, release)

    with ThreadPoolExecutor(max_workers=1) as pool:
        hung = pool.submit(adapter.call_get_data, module, "SELECT 1")
        assert started.wait(30)
        again = adapter.call_get_data(module, "SELECT 1")
        assert isinstance(again, pd.DataFrame) and again["차례"].tolist() == [2]
        assert not hung.done()
        release.set()
        hung.result(30)

    assert asked == ["SELECT 1", "SELECT 1"]
    assert adapter._IN_FLIGHT == {}


def test_a_press_waiting_on_a_query_that_never_comes_back_asks_again_at_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이미 기다리던 부름도 상한에서 풀려 새로 묻는다 — 조회문 하나의 기다림에 끝이 있다."""
    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(adapter, "IN_FLIGHT_JOIN_SECONDS", 0.2)
    asked: list[object] = []
    started = threading.Event()
    release = threading.Event()
    module = _hung_then_answering(asked, started, release)

    with ThreadPoolExecutor(max_workers=2) as pool:
        hung = pool.submit(adapter.call_get_data, module, "SELECT 1")
        assert started.wait(30)
        waiting = pool.submit(adapter.call_get_data, module, "SELECT 1")
        answer = waiting.result(30)
        assert isinstance(answer, pd.DataFrame) and answer["차례"].tolist() == [2]
        assert not hung.done()
        release.set()
        hung.result(30)

    assert asked == ["SELECT 1", "SELECT 1"]


def test_an_old_query_coming_back_late_leaves_the_slot_of_the_one_that_took_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """넘겨준 뒤에 돌아온 옛 조회가 새 자리를 지우면 그다음 부름이 다시 겹친다."""
    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(adapter, "IN_FLIGHT_JOIN_SECONDS", 0.0)
    asked: list[object] = []
    first_in, second_in = threading.Event(), threading.Event()
    release_first, release_second = threading.Event(), threading.Event()

    def getter(**keywords: object) -> pd.DataFrame:
        asked.append(keywords["param"])
        entered, release = (
            (first_in, release_first) if len(asked) == 1 else (second_in, release_second)
        )
        entered.set()
        assert release.wait(30)
        return pd.DataFrame({"차례": [len(asked)]})

    module = _module(getter)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(adapter.call_get_data, module, "SELECT 1")
        assert first_in.wait(30)
        second = pool.submit(adapter.call_get_data, module, "SELECT 1")
        assert second_in.wait(30)
        holder = adapter._IN_FLIGHT["SELECT 1"]

        release_first.set()
        first.result(30)
        assert adapter._IN_FLIGHT["SELECT 1"] is holder

        release_second.set()
        second.result(30)

    assert adapter._IN_FLIGHT == {}


def test_a_different_window_is_not_held_back_by_a_long_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """넓은 창이 도는 동안 사용자가 기간을 줄여 다시 물으면 바로 답을 받는다 — 앞 조회를 취소할 길은
    없다."""
    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    started = threading.Event()
    release = threading.Event()

    def getter(**keywords: object) -> pd.DataFrame:
        if keywords["param"] == "WIDE":
            started.set()
            assert release.wait(30)
        return pd.DataFrame({"a": [str(keywords["param"])]})

    module = _module(getter)
    with ThreadPoolExecutor(max_workers=1) as pool:
        wide = pool.submit(adapter.call_get_data, module, "WIDE")
        assert started.wait(30)
        narrow = adapter.call_get_data(module, "NARROW")
        assert isinstance(narrow, pd.DataFrame) and narrow["a"].tolist() == ["NARROW"]
        assert not wide.done()
        release.set()
        wide.result(30)


def test_a_wrapped_failure_keeps_the_chain_names_and_cuts_a_long_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(**_kwargs: object) -> pd.DataFrame:
        raise Error("x" * 1000) from TimeoutError()

    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(refuse))

    with pytest.raises(RuntimeError) as raised:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert isinstance(raised.value, adapter.BigDataQueryCallError)
    assert raised.value.type_names == ("Error", "TimeoutError")
    assert "시간 초과" in str(raised.value) and "다시" in str(raised.value)
    assert len(str(raised.value)) < 500


_PACKAGE_MISSING_TEXT = (
    "현재 환경에 bigdataquery 패키지가 없습니다. "
    "이 패키지는 공개 인덱스(PyPI)에 없어 pyproject.toml 의존성에 넣지 않습니다. "
    "README 「초기 설정」 4단계대로 따로 설치한 뒤 실행하세요."
)


def _installed_package(monkeypatch: pytest.MonkeyPatch, root: Path, init_body: str) -> None:
    """`root` 에 깔린 가짜 `bigdataquery` — 패키지는 있고 `__init__` 이 `init_body` 를 돈다."""
    package = root / "bigdataquery"
    package.mkdir()
    (package / "__init__.py").write_text(init_body, encoding="utf-8")
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.delitem(sys.modules, "bigdataquery", raising=False)


def test_a_missing_package_keeps_the_install_advice(monkeypatch: pytest.MonkeyPatch) -> None:
    """맨 `uv sync` 가 패키지를 지운 경우다. 점검 스크립트가 이 문구의 「패키지가 없습니다」로
    가른다."""
    monkeypatch.setitem(sys.modules, "bigdataquery", None)

    with pytest.raises(RuntimeError) as raised:
        adapter.load_bigdataquery_module()

    assert str(raised.value) == _PACKAGE_MISSING_TEXT
    assert isinstance(raised.value.__cause__, ModuleNotFoundError)


def test_a_failure_the_screen_catches_still_leaves_one_log_line(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """화면이 잡아 보여 주는 실패도 앱 로그에 한 줄 남는다 — 셸·화면을 볼 수 없는 C-DEP CD 에서는
    로그가 유일한 단서일 수 있다. 원문(계정 이름 등이 든다)은 화면에만 두고 로그에는 갈래·종류만."""
    secret_like = "AD user 'someone' at '/config/.credential/'"

    def refuse(**_kwargs: object) -> pd.DataFrame:
        raise ValueError(f"table not found {secret_like}")

    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(refuse))
    caplog.set_level("WARNING", logger=adapter.__name__)

    with pytest.raises(adapter.BigDataQueryCallError):
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    lines = [record.getMessage() for record in caplog.records]
    assert lines == [
        f"BigDataQuery 실패: 조회 실패 갈래={adapter.QUERY_FAILURE_SQL} 종류=ValueError"
    ]
    assert secret_like not in "\n".join(lines)

    caplog.clear()
    monkeypatch.undo()
    monkeypatch.setitem(sys.modules, "bigdataquery", None)
    with pytest.raises(RuntimeError):
        adapter.load_bigdataquery_module()
    assert [record.getMessage() for record in caplog.records] == [
        "BigDataQuery 실패: 패키지를 불러오지 못함(없는 모듈 bigdataquery)"
    ]


@pytest.mark.parametrize(
    ("init_body", "original"),
    [
        (
            'raise ImportError("DLL load failed while importing _jpype: 모듈이 없습니다.")\n',
            "DLL load failed while importing _jpype",
        ),
        ("from importlib import capa_bdq_no_such_name\n", "cannot import name"),
        (
            "raise AttributeError(\"module 'numpy' has no attribute 'float'\")\n",
            "has no attribute 'float'",
        ),
    ],
    ids=["dll-load", "cannot-import-name", "numpy-attribute"],
)
def test_a_package_that_fails_to_import_is_reported_where_the_screens_catch_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, init_body: str, original: str
) -> None:
    """패키지는 깔렸는데 불러오다 깨지면(DLL·numpy 판·이름 없음) 화면이 잡는 `RuntimeError` 로 온다.
    `ImportError`·`AttributeError` 는 `BOOTSTRAP_ERRORS` 밖이라 그대로 두면 목록 조회·저장이
    traceback 으로 멈춘다. 「패키지가 없습니다」라고 하면 틀린 조치다."""
    _installed_package(monkeypatch, tmp_path, init_body)

    with pytest.raises(RuntimeError) as raised:
        adapter.load_bigdataquery_module()

    text = str(raised.value)
    assert isinstance(raised.value, BOOTSTRAP_ERRORS)
    assert "불러오지 못했습니다" in text and original in text
    assert "패키지가 없습니다" not in text
    assert isinstance(raised.value.__cause__, ImportError | AttributeError)


def test_a_missing_dependency_names_that_module_not_the_package(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """빠진 것이 패키지가 쓰는 모듈이면 그 이름을 알린다. 같은 화면 배너는 패키지를 확인했다고
    띄운다."""
    _installed_package(monkeypatch, tmp_path, "import capa_bdq_missing_dependency\n")

    with pytest.raises(RuntimeError) as raised:
        adapter.load_bigdataquery_module()

    text = str(raised.value)
    assert "capa_bdq_missing_dependency" in text and "불러오지 못했습니다" in text
    assert "패키지가 없습니다" not in text
    assert adapter.failure_type_names(raised.value) == ("RuntimeError", "ModuleNotFoundError")


def test_unconfigured_query_is_rejected_before_package_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = False

    def fake_import(_: str) -> object:
        nonlocal imported
        imported = True
        return object()

    monkeypatch.setattr(importlib, "import_module", fake_import)
    # 모듈 기본 SQL 은 사내 조회문으로 채워져 있다. 미설정 경로를 보려면 표식이 남은
    # 템플릿을 명시로 준다.
    provider = adapter.BigDataQueryCoreDataProvider(
        "사내 조회",
        query_template=f"SELECT {adapter.UNCONFIGURED_MARKER} WHERE x = '{{simulation_code}}'",
    )

    with pytest.raises(RuntimeError, match="SQL이 아직 설정되지 않았습니다"):
        provider.fetch("SIM-001")

    assert not imported


def test_provider_returns_renamed_dataframe_without_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    # `fetch` 는 MPGA TEST 예외를 적용하므로 원천에 `공정`·`모듈수` 가 있어야 한다. CUSTOM 은
    # Capa Code 로 붙이므로 그 칸 · 생산계획년월도 있어야 한다.
    main = pd.DataFrame(
        {"db_product": ["Product*_A"], "공정": ["ASSY"], "모듈수": [2], **_part_columns(1)}
    )
    answer = _answers(main, _custom_for(main))

    def fake_get_data(*, param: str, convert_type: bool, verbose: bool) -> pd.DataFrame:
        # CUSTOM 원천 표를 먼저 묻고 본 조회가 마지막이라 남는 것은 본 조회의 인자다.
        captured.update(
            param=param,
            convert_type=convert_type,
            verbose=verbose,
        )
        return answer(param=param)

    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _: SimpleNamespace(getData=fake_get_data),
    )
    provider = adapter.BigDataQueryCoreDataProvider(
        "사내 조회",
        query_template="SELECT * FROM source WHERE simulation_code = '{simulation_code}'",
        column_mapping={"db_product": "제품정보"},
    )

    batch = provider.fetch("SIM-001")

    assert batch.source_type == "BIGDATAQUERY"
    assert batch.frame.columns.tolist() == [
        "제품정보",
        "공정",
        "모듈수",
        "Capa Code",
        "생산계획년월",
        "CUSTOM",
    ]
    assert captured == {
        "param": "SELECT * FROM source WHERE simulation_code = 'SIM-001'",
        "convert_type": True,
        "verbose": True,
    }


@pytest.mark.parametrize("code", ["SIM 001", "SIM'001", "한글코드"])
def test_provider_rejects_unsafe_simulation_code(code: str) -> None:
    with pytest.raises(ValueError, match="영문·숫자"):
        adapter.build_query("SELECT '{simulation_code}'", code)


def test_mpga_test_module_count_exception_normalizes_to_one() -> None:
    """MPGA TEST 의 0.95~0.96 모듈수는 1로 본다.

    원천 산정 규칙이 확정될 때까지 두는 예외이므로(`docs/TODO.md` 결정 기록, 옛 3-7) 동작을 고정해
    조용히 사라지지 않게 한다. 같은 값이라도 공정이 다르면 손대지 않는다.
    """
    frame = pd.DataFrame(
        {
            "공정": ["MPGA TEST", "MPGA TEST", "MPGA TEST", "ASSY"],
            "모듈수": [0.955, 0.94, 2, 0.955],
            **_part_columns(4),
        }
    )

    provider = adapter.BigDataQueryCoreDataProvider(
        "사내 조회",
        query_template="SELECT '{simulation_code}'",
        column_mapping={},
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            importlib,
            "import_module",
            lambda _: SimpleNamespace(getData=_answers(frame, _custom_for(frame))),
        )
        batch = provider.fetch("SIM-001")

    assert batch.frame["모듈수"].tolist() == [1, 0.94, 2, 0.955]


@pytest.mark.parametrize("missing_column", ["공정", "모듈수"])
def test_provider_reports_missing_columns_before_source_adjustment(
    monkeypatch: pytest.MonkeyPatch, missing_column: str
) -> None:
    frame = pd.DataFrame({"공정": ["MPGA TEST"], "모듈수": [0.955]}).drop(columns=missing_column)
    monkeypatch.setattr(
        adapter, "load_bigdataquery_module", lambda: _module(_answers(frame, _one_custom_row()))
    )
    provider = adapter.BigDataQueryCoreDataProvider("사내 조회", column_mapping={})

    with pytest.raises(ValueError, match=f"필요한 컬럼이 없습니다: {missing_column}"):
        provider.fetch("SIM-001")


def test_provider_reports_mapping_collisions_before_source_adjustment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = pd.DataFrame({"공정": ["MPGA TEST"], "모듈수": [0.955], "module_count": [2]})
    monkeypatch.setattr(
        adapter, "load_bigdataquery_module", lambda: _module(_answers(frame, _one_custom_row()))
    )
    provider = adapter.BigDataQueryCoreDataProvider(
        "사내 조회", column_mapping={"module_count": "모듈수"}
    )

    with pytest.raises(ValueError, match="중복 컬럼이 있습니다: 모듈수"):
        provider.fetch("SIM-001")

    assert frame["모듈수"].tolist() == [0.955]


def _contract_columns() -> list[str]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return [column["name"] for column in contract["source"]["columns"]]


def _query_aliases() -> list[str]:
    select_clause = adapter.QUERY_TEMPLATE.split("FROM", 1)[0]
    aliases: list[str] = []
    for line in select_clause.splitlines():
        item = line.strip().rstrip(",")
        if not item or item.upper() == "SELECT":
            continue
        assert " AS " in item, f"별칭이 없는 SELECT 항목: {item}"
        aliases.append(item.rsplit(" AS ", 1)[1].strip().strip("`"))
    return aliases


def test_query_aliases_match_the_core_data_contract() -> None:
    """SELECT 별칭이 78컬럼 계약과 한 글자라도 다르면 정규화에서 통째로 실패한다.

    실제로 `Module/Comp`·`Plan_Chip(k개)`·`WF측정룰` 세 개가 대소문자·철자만 달라
    사내 조회가 통째로 막혔었다. 눈으로는 걸러지지 않아 여기서 잡는다.
    """
    assert _query_aliases() == _contract_columns()


def test_column_mapping_only_targets_contract_columns() -> None:
    """대문자가 섞인 계약 컬럼은 소문자 키가 모두 있어야 한다.

    드라이버가 컬럼명을 소문자로 돌려주는 경우를 위한 매핑이므로, 하나라도 빠지면 그
    컬럼만 계약과 어긋난다.
    """
    expected = _contract_columns()
    assert [
        value for value in adapter.SOURCE_COLUMN_MAPPING.values() if value not in expected
    ] == []
    needs_key = [name for name in expected if name.lower() != name]
    assert [name for name in needs_key if name.lower() not in adapter.SOURCE_COLUMN_MAPPING] == []


def test_query_window_upper_bound_includes_the_end_date() -> None:
    """종료일 당일 적재분이 빠지던 결함의 회귀선(docs/TODO.md 결정 기록, 옛 3-7).

    화면 라벨이 '포함' 이므로 배타 상한(`<`)을 다음 날로 민다.
    """
    window = adapter.QueryWindow(start_date=date(2026, 6, 10), end_date=date(2026, 9, 8))

    assert window.sql_bounds() == ("2026-06-10", "2026-09-09")
    assert window.days == 91
    assert window.label() == "2026-06-10 ~ 2026-09-08"


def test_query_window_rejects_a_reversed_period() -> None:
    with pytest.raises(ValueError, match="시작일은 종료일보다"):
        adapter.QueryWindow(start_date=date(2026, 9, 9), end_date=date(2026, 9, 8))


def test_build_query_uses_the_given_window() -> None:
    window = adapter.QueryWindow(start_date=date(2026, 9, 1), end_date=date(2026, 9, 8))

    query = adapter.build_query(adapter.QUERY_TEMPLATE, "SIM-001", window=window)

    assert "'2026-09-01'" in query
    assert "'2026-09-09'" in query
    assert "{" not in query


def test_build_query_without_a_window_keeps_the_default_window() -> None:
    """기존 호출부(위치 인자 2개)가 그대로 돌아야 한다."""
    today = date(2026, 9, 8)
    expected = adapter.default_query_window(today=today).sql_bounds()

    query = adapter.build_query(adapter.QUERY_TEMPLATE, "SIM-001")

    assert adapter.DEFAULT_QUERY_WINDOW_DAYS == 90
    assert len(expected[0]) == 10
    assert "impala_insert_time" in query


def test_the_detail_window_defaults_to_a_few_days_around_the_registration_date() -> None:
    """상세 조회 기본 창은 원천 등록일 7일 전 ~ 3일 뒤다(2026-09-29 사용자 결정 A+B).

    예전에는 기본 90일 ∪ 목록 기간 ∪ 등록일 7일 전~오늘이라 옛 코드일수록 창이 길어져 사내
    조회가 오래 걸렸다. 몇 달 전 코드도 이제 등록일 앞뒤 11일치만 읽는다.
    """
    today = date(2026, 9, 29)
    registered = date(2026, 3, 10)

    window = adapter.registration_detail_window(registered, today=today)

    assert window.start_date == registered - timedelta(days=adapter.DETAIL_WINDOW_DAYS_BEFORE)
    assert window.end_date == registered + timedelta(days=adapter.DETAIL_WINDOW_DAYS_AFTER)
    assert (adapter.DETAIL_WINDOW_DAYS_BEFORE, adapter.DETAIL_WINDOW_DAYS_AFTER) == (7, 3)
    assert window.days == 11


def test_provider_passes_the_window_into_the_query(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    asked: list[str] = []
    main = pd.DataFrame(
        {"제품정보": ["Product-A"], "공정": ["ASSY"], "모듈수": [2], **_part_columns(1)}
    )
    answer = _answers(main, _custom_for(main), asked=asked)

    def fake_get_data(*, param: str, convert_type: bool, verbose: bool) -> pd.DataFrame:
        captured["param"] = param
        return answer(param=param)

    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _: SimpleNamespace(getData=fake_get_data),
    )
    provider = adapter.BigDataQueryCoreDataProvider(
        "사내 조회",
        query_template=(
            "SELECT '{simulation_code}' WHERE t >= '{start_date}' AND t < '{end_date}'"
        ),
        column_mapping={},
        window=adapter.QueryWindow(start_date=date(2026, 9, 1), end_date=date(2026, 9, 8)),
    )

    provider.fetch("SIM-001")

    assert captured["param"] == "SELECT 'SIM-001' WHERE t >= '2026-09-01' AND t < '2026-09-09'"
    # CUSTOM 원천 표가 먼저다 — 그 조회문에는 기간이 없다.
    assert asked == [adapter.build_custom_query("SIM-001"), captured["param"]]


def test_empty_result_is_rejected_before_the_module_count_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """0행 가드가 rename 뒤에 있으면 `KeyError('모듈수')` 로 먼저 터진다. CUSTOM 원천 표 답은
    있고 본 답만 0행인 꼴이다(CUSTOM 원천 표 0행 멈춤도 「0행」 이라 그 답은 채워 둔다)."""
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _: SimpleNamespace(getData=_answers(pd.DataFrame(), _one_custom_row())),
    )
    provider = adapter.BigDataQueryCoreDataProvider(
        "사내 조회",
        query_template="SELECT '{simulation_code}'",
        column_mapping={},
    )

    with pytest.raises(ValueError, match="0행"):
        provider.fetch("SIM-001")


def _counting_import(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """패키지 import 를 세는 가짜 — 부른 모듈 이름을 남기고 쓸 수 없는 물건을 돌려준다."""
    imported: list[str] = []

    def fake_import(name: str) -> object:
        imported.append(name)
        return object()

    monkeypatch.setattr(importlib, "import_module", fake_import)
    return imported


@pytest.mark.parametrize("value", [None, "", "   "], ids=["없음", "빈 값", "공백뿐"])
def test_a_missing_custom_table_variable_stops_before_the_package_is_imported(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    """CUSTOM 원천 표 환경변수가 없으면 부품의 CUSTOM 을 읽을 수 없어 등록을 멈춘다 — 패키지를
    부르기 전이고, 미설정 SQL 검사(`build_query`)보다는 뒤다. 글은 변수 이름을 든다."""
    if value is None:
        monkeypatch.delenv(adapter.BDQ_CUSTOM_TABLE_ENV, raising=False)
    else:
        monkeypatch.setenv(adapter.BDQ_CUSTOM_TABLE_ENV, value)
    imported = _counting_import(monkeypatch)

    with pytest.raises(RuntimeError) as raised:
        adapter.BigDataQueryCoreDataProvider("사내 조회").fetch("SIM-001")

    assert str(raised.value).startswith(adapter.CUSTOM_TABLE_MISSING)
    assert adapter.BDQ_CUSTOM_TABLE_ENV in str(raised.value)
    assert isinstance(raised.value, BOOTSTRAP_ERRORS)
    assert imported == []
    assert adapter.custom_table_problem() == adapter.CUSTOM_TABLE_MISSING
    # 미설정 SQL 이면 그 글이 먼저다(변수 없음 갈래가 SQL 안내를 가리지 않는다).
    unconfigured = adapter.BigDataQueryCoreDataProvider(
        "사내 조회",
        query_template=f"SELECT {adapter.UNCONFIGURED_MARKER} WHERE x = '{{simulation_code}}'",
    )
    with pytest.raises(RuntimeError, match="SQL이 아직 설정되지 않았습니다"):
        unconfigured.fetch("SIM-001")


@pytest.mark.parametrize(
    "value",
    [
        "demo schema.demo_custom",
        "demo_schema.demo_custom;",
        "demo_schema.demo_custom' --",
        "demo_schema.demo.custom",
        "1demo.demo_custom",
        "demo-schema.demo_custom",
        "데모_스키마.데모_표",
        "demo_schema.",
    ],
)
def test_a_custom_table_value_that_is_not_a_table_name_stops_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """표 이름 꼴(영문 · 숫자 · 밑줄 낱말 하나 또는 점으로 이은 둘)이 아니면 조회문에 끼우지 않고
    멈춘다 — 패키지를 부르기 전이다. 사내 값이라 글에 그 값을 싣지 않는다."""
    monkeypatch.setenv(adapter.BDQ_CUSTOM_TABLE_ENV, value)
    imported = _counting_import(monkeypatch)

    with pytest.raises(RuntimeError) as raised:
        adapter.BigDataQueryCoreDataProvider("사내 조회").fetch("SIM-001")

    text = str(raised.value)
    assert text.startswith(adapter.CUSTOM_TABLE_MALFORMED)
    assert value.strip() not in text
    assert imported == []
    assert adapter.custom_table_problem() == adapter.CUSTOM_TABLE_MALFORMED
    with pytest.raises(RuntimeError, match="표 이름"):
        adapter.build_custom_query("SIM-001")


@pytest.mark.parametrize("value", [DEMO_CUSTOM_TABLE, "demo_custom", f"  {DEMO_CUSTOM_TABLE}  "])
def test_a_table_name_with_or_without_a_schema_is_usable(value: str) -> None:
    assert adapter.custom_table_problem(value) is None
    assert f"FROM {value.strip()}\n" in adapter.build_custom_query("SIM-001", value)


def test_the_main_query_text_is_unchanged() -> None:
    """본 조회문은 글자 하나 바꾸지 않는다 — 상수 CUSTOM 칸은 붙이기가 덮는다(설계 B 1-5). 목록
    조회 · 상세 창 · 별칭 대조가 이 글에 기대므로 바뀌면 이 지문이 먼저 깨진다(바꿀 때는 그 까닭과
    함께 지문을 새로 적는다)."""
    digest = hashlib.sha256(adapter.QUERY_TEMPLATE.encode("utf-8")).hexdigest()

    assert digest == "1beec0c708869a82c78dd6b97794242815d87e59b0a83eb21a19c1766050b5dd"


def _select_aliases(query: str) -> list[str]:
    aliases: list[str] = []
    for line in query.split("FROM", 1)[0].splitlines():
        item = line.strip().rstrip(",")
        if not item or item.upper() == "SELECT":
            continue
        aliases.append(item.rsplit(" AS ", 1)[1].strip().strip("`"))
    return aliases


def test_the_custom_query_asks_one_code_from_the_variable_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CUSTOM 원천 표 조회는 환경변수의 표에서 코드 하나를 기간 없이 묻고, 별칭이 붙이기가 읽는 칸
    (`CUSTOM_SOURCE_COLUMNS`)과 같다. 공급자가 받은 이름이 환경변수보다 앞선다."""
    query = adapter.build_custom_query("SIM-001")

    assert f"FROM {DEMO_CUSTOM_TABLE}\n" in query
    assert "WHERE catb_sim_info_id = 'SIM-001'" in query
    assert "{" not in query and "impala_insert_time" not in query
    assert _select_aliases(query) == list(CUSTOM_SOURCE_COLUMNS)
    assert "FROM other_schema.other_custom\n" in adapter.build_custom_query(
        "SIM-001", "other_schema.other_custom"
    )
    with pytest.raises(ValueError, match="영문·숫자"):
        adapter.build_custom_query("SIM'001")

    asked: list[str] = []
    main = pd.DataFrame({"공정": ["ASSY"], "모듈수": [2], **_part_columns(1)})
    other = _custom_for(main)

    def get_data(*, param: str, **_kwargs: object) -> pd.DataFrame:
        asked.append(param)
        return (other if "other_schema.other_custom" in param else main).copy()

    monkeypatch.setattr(adapter, "load_bigdataquery_module", lambda: _module(get_data))
    adapter.BigDataQueryCoreDataProvider(
        "사내 조회", column_mapping={}, custom_table="other_schema.other_custom"
    ).fetch("SIM-001")

    assert asked[0] == adapter.build_custom_query("SIM-001", "other_schema.other_custom")


@pytest.mark.parametrize(
    "custom",
    [
        pd.DataFrame(columns=list(CUSTOM_SOURCE_COLUMNS)),
        pd.DataFrame(
            [("DEMO_CAPA_A", 202611, CUSTOM_A)], columns=["Capa Code", "생산계획년월", "CUSTOM"]
        ),
        pd.DataFrame(
            [("DEMO_CAPA_A", 202611, CUSTOM_A, 1), ("DEMO_CAPA_A", 202612, CUSTOM_B, 1)],
            columns=list(CUSTOM_SOURCE_COLUMNS),
        ),
    ],
    ids=["0행", "칸 없음", "부품 하나에 둘"],
)
def test_an_empty_custom_answer_stops_before_the_main_query(
    monkeypatch: pytest.MonkeyPatch, custom: pd.DataFrame
) -> None:
    """CUSTOM 원천 표 답이 0행(그 표 적재가 늦은 날) · 칸 없음 · 한 부품에 CUSTOM 둘이면 본 조회를
    부르지 않고 멈춘다 — 헛 본 조회가 없다."""
    asked: list[str] = []
    main = pd.DataFrame({"공정": ["ASSY"], "모듈수": [2], **_part_columns(1)})
    monkeypatch.setattr(
        adapter, "load_bigdataquery_module", lambda: _module(_answers(main, custom, asked=asked))
    )

    with pytest.raises(ValueError, match="CUSTOM 원천 표"):
        adapter.BigDataQueryCoreDataProvider("사내 조회", column_mapping={}).fetch("SIM-001")

    assert asked == [adapter.build_custom_query("SIM-001")]


@pytest.mark.parametrize(
    ("error", "kind", "names_access"),
    [
        (
            Error(
                "AnalysisException: Could not resolve table reference: "
                f"'{DEMO_CUSTOM_TABLE.upper()}' (table {DEMO_TABLE.title()})"
            ),
            adapter.QUERY_FAILURE_SQL,
            True,
        ),
        (
            TimeoutError(f"timed out reading {DEMO_CUSTOM_TABLE}"),
            adapter.QUERY_FAILURE_TIMEOUT,
            False,
        ),
    ],
    ids=["SQL", "시간 초과"],
)
def test_a_custom_query_failure_names_the_variable_and_hides_the_table_name(
    monkeypatch: pytest.MonkeyPatch, error: BaseException, kind: str, names_access: bool
) -> None:
    """CUSTOM 원천 표 조회가 실패하면 본 조회를 부르지 않고, 그 조회에서 멈췄다는 머리를 단 같은
    갈래의 실패로 올린다. SQL 갈래(표 없음 · 권한)면 변수 값과 조회 권한을 보라고 덧붙인다. 원문이
    실은 표 이름(값 전체 · 끝 조각, 대소문자가 달라도)은 가린다 — 자동 갱신 실행 기록 사유로 남는
    글이다."""
    asked: list[str] = []

    def get_data(*, param: str, **_kwargs: object) -> pd.DataFrame:
        asked.append(param)
        raise error

    monkeypatch.setattr(adapter, "load_bigdataquery_module", lambda: _module(get_data))

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.BigDataQueryCoreDataProvider("사내 조회", column_mapping={}).fetch("SIM-001")

    text = str(raised.value)
    assert text.startswith(f"CUSTOM 원천 표({adapter.BDQ_CUSTOM_TABLE_ENV}) 조회에서 멈췄습니다.")
    assert f"BigDataQuery 조회가 실패했습니다({kind})" in text
    assert ("조회 권한을 확인하세요" in text) is names_access
    assert DEMO_TABLE not in text.casefold() and DEMO_SCHEMA not in text.casefold()
    assert adapter.CUSTOM_TABLE_MASK in text
    assert (raised.value.kind, raised.value.type_names) == (kind, (type(error).__name__,))
    assert raised.value.__cause__ is error
    assert asked == [adapter.build_custom_query("SIM-001")]


def test_fetch_overwrites_the_query_constant_custom_with_the_looked_up_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """본 조회문의 상수 CUSTOM 칸을 부품(Capa Code)마다 CUSTOM 원천 표의 값으로 덮는다 — 행 수 ·
    차례 · 다른 칸은 그대로다. 대조 수는 원천 묶음(`custom_check`)에 실린다."""
    main = pd.DataFrame(
        {
            "공정": ["ASSY", "ASSY", "TEST", "TEST"],
            "모듈수": [2, 2, 1, 1],
            "Capa Code": ["DEMO_CAPA_A", "DEMO_CAPA_B", "DEMO_CAPA_A", "DEMO_CAPA_B"],
            "생산계획년월": [202611, 202611, 202612, 202612],
            "CUSTOM": [QUERY_CONSTANT] * 4,
        }
    )
    custom = _custom_for(main, {"DEMO_CAPA_A": CUSTOM_A, "DEMO_CAPA_B": f"  {CUSTOM_B} "})
    custom["Capa Code"] = " " + custom["Capa Code"] + " "
    monkeypatch.setattr(
        adapter, "load_bigdataquery_module", lambda: _module(_answers(main, custom))
    )

    batch = adapter.BigDataQueryCoreDataProvider("사내 조회", column_mapping={}).fetch("SIM-001")

    assert batch.frame["CUSTOM"].tolist() == [CUSTOM_A, CUSTOM_B, CUSTOM_A, CUSTOM_B]
    pd.testing.assert_frame_equal(batch.frame.drop(columns="CUSTOM"), main.drop(columns="CUSTOM"))
    assert batch.custom_check is not None
    assert (batch.custom_check.kinds, batch.custom_check.warns) == (2, False)
    assert batch.custom_check.memo().startswith("CUSTOM 원천 대조 — 종류 2")


def _two_part_source() -> pd.DataFrame:
    """내장 시드 원천에서 한 제품의 행을 한 벌 더 두어 두 부품으로 가른 본 답 — 둘째 부품은 Capa
    Code 가 다르고 EDS 수율만 다르다(Capa Code 가 키 밖인 `RQ_YLD` 에서만 두 부품이 갈린다)."""
    source = build_builtin_seed_dataset().source_data
    first = source["제품정보"].eq(source["제품정보"].iloc[0])
    part_b = source.loc[first].copy()
    part_b["Capa Code"] = "DEMO_CAPA_A2"
    part_b["EDS_수율"] = pd.to_numeric(part_b["EDS_수율"]) * 0.8
    return pd.concat([source, part_b], ignore_index=True)


def test_two_parts_through_fetch_and_prepare_keep_two_custom_keys_and_no_custom_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """한 제품의 두 부품이 CUSTOM 원천 표에서 다른 CUSTOM 을 받으면 조회 → 변환 끝까지 두 CUSTOM
    키로 남고 업무 키 충돌이 없다. 두 부품이 같은 CUSTOM 이면(조회문 상수 그대로와 같은 꼴) 키 밖
    Capa Code 로 갈린 충돌이 선다 — 붙이기가 그 충돌을 없앤다는 것을 견준다."""
    main = _two_part_source()
    first = str(main["Capa Code"].iloc[0])
    other = sorted(set(main["Capa Code"].astype(str)) - {first, "DEMO_CAPA_A2"})

    def prepared(values: dict[str, str]) -> PreparedCoreDataset:
        custom = _custom_for(main, values)
        monkeypatch.setattr(
            adapter, "load_bigdataquery_module", lambda: _module(_answers(main, custom))
        )
        batch = adapter.BigDataQueryCoreDataProvider("사내 조회").fetch("SIM-001")
        return prepare_core_data_dataset(batch, load_builtin_display_order())

    split = prepared({first: CUSTOM_A, "DEMO_CAPA_A2": CUSTOM_B, **dict.fromkeys(other, CUSTOM_A)})
    folded = prepared({first: CUSTOM_A, "DEMO_CAPA_A2": CUSTOM_A, **dict.fromkeys(other, CUSTOM_A)})

    assert split.reference_conflicts.empty
    for table in ("RQ_PKG_PLAN", "RQ_YLD"):
        parts = split.reference_tables[table].groupby("제품정보")["CUSTOM"]
        assert {CUSTOM_A, CUSTOM_B} in [set(values) for _, values in parts], table
    assert "RQ_YLD" in set(folded.reference_conflicts["RQ테이블"])


def _switch_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """CUSTOM 원천 끄개를 내린다 — 앞뒤 공백 · 대문자도 끈 값이다(conftest 가 지워 둔다)."""
    monkeypatch.setenv(adapter.BDQ_CUSTOM_SOURCE_ENV, " OFF ")


def _two_part_main() -> pd.DataFrame:
    """부품 둘 · 달 둘의 본 답 — CUSTOM 칸은 조회문 상수다."""
    return pd.DataFrame(
        {
            "공정": ["ASSY", "ASSY", "TEST", "TEST"],
            "모듈수": [2, 2, 1, 1],
            "Capa Code": ["DEMO_CAPA_A", "DEMO_CAPA_B", "DEMO_CAPA_A", "DEMO_CAPA_B"],
            "생산계획년월": [202611, 202611, 202612, 202612],
            "CUSTOM": [QUERY_CONSTANT] * 4,
        }
    )


@pytest.mark.parametrize(
    ("value", "on"),
    [
        (None, True),
        ("", True),
        ("on", True),
        ("0", True),
        ("false", True),
        ("of", True),
        ("off", False),
        (" OFF ", False),
    ],
    ids=["없음", "빈 값", "on", "0", "false", "오타 of", "off", "공백 · 대문자 OFF"],
)
def test_only_off_turns_the_custom_source_off(
    monkeypatch: pytest.MonkeyPatch, value: str | None, on: bool
) -> None:
    """끄개는 값이 `off`(앞뒤 공백 · 대소문자 무시)일 때만 끈다 — 비었거나 다른 값(오타 `of` ·
    `false` 포함)은 켬이다. 끄면 표 이름을 판정하지 않고(변수가 없거나 꼴이 틀려도 None), 켬이면
    판정이 표 이름 판정(`custom_table_problem`) 그대로다. 넘긴 환경과 이 프로세스의 환경이 같은
    답이다."""
    environ = {} if value is None else {adapter.BDQ_CUSTOM_SOURCE_ENV: value}
    if value is None:
        monkeypatch.delenv(adapter.BDQ_CUSTOM_SOURCE_ENV, raising=False)
    else:
        monkeypatch.setenv(adapter.BDQ_CUSTOM_SOURCE_ENV, value)
    monkeypatch.delenv(adapter.BDQ_CUSTOM_TABLE_ENV)

    assert adapter.custom_source_on(environ) is on
    assert adapter.custom_source_on() is on
    missing = adapter.CUSTOM_TABLE_MISSING if on else None
    assert adapter.custom_source_problem(environ) == missing
    assert adapter.custom_source_problem() == missing
    named = {**environ, adapter.BDQ_CUSTOM_TABLE_ENV: DEMO_CUSTOM_TABLE}
    assert adapter.custom_source_problem(named) is None
    malformed = {**environ, adapter.BDQ_CUSTOM_TABLE_ENV: "demo schema.demo_custom"}
    assert adapter.custom_source_problem(malformed) == (
        adapter.CUSTOM_TABLE_MALFORMED if on else None
    )


def test_the_switch_off_asks_only_the_main_query_and_marks_every_part_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """끄개를 내리면 CUSTOM 원천 표를 묻지 않는다 — 가짜가 받은 조회문은 본 조회 하나다. 본 조회문의
    상수 CUSTOM 칸은 모든 부품이 구분 없음(`CUSTOM_BLANK`)으로 덮이고(상수 그대로가 아니다) 행 수 ·
    차례 · 다른 칸은 그대로다. 원천 묶음의 대조(`custom_check`)는 「붙이지 않음」 이다."""
    _switch_off(monkeypatch)
    asked: list[str] = []
    main = _two_part_main()
    monkeypatch.setattr(
        adapter,
        "load_bigdataquery_module",
        lambda: _module(_answers(main, _custom_for(main), asked=asked)),
    )

    batch = adapter.BigDataQueryCoreDataProvider("사내 조회", column_mapping={}).fetch("SIM-001")

    [query] = asked
    assert "'SIM-001'" in query and DEMO_CUSTOM_TABLE not in query
    assert batch.frame["CUSTOM"].tolist() == [CUSTOM_BLANK] * 4
    pd.testing.assert_frame_equal(batch.frame.drop(columns="CUSTOM"), main.drop(columns="CUSTOM"))
    assert batch.custom_check is not None
    assert not batch.custom_check.attached
    assert batch.custom_check.memo() == SWITCHED_OFF_MEMO


@pytest.mark.parametrize(
    "value", [None, "demo schema.demo_custom", "   "], ids=["변수 없음", "꼴 틀림", "공백뿐"]
)
def test_the_switch_off_needs_no_custom_table_variable(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    """끄개를 내리면 표 이름을 판정하지 않는다 — 변수가 없거나 꼴이 틀려도 멈추지 않고 본 조회
    하나로 원천을 낸다. 꼴이 틀린 값은 조회문 어디에도 끼지 않는다."""
    _switch_off(monkeypatch)
    if value is None:
        monkeypatch.delenv(adapter.BDQ_CUSTOM_TABLE_ENV)
    else:
        monkeypatch.setenv(adapter.BDQ_CUSTOM_TABLE_ENV, value)
    asked: list[str] = []
    main = _two_part_main()
    monkeypatch.setattr(
        adapter,
        "load_bigdataquery_module",
        lambda: _module(_answers(main, _custom_for(main), asked=asked)),
    )

    batch = adapter.BigDataQueryCoreDataProvider("사내 조회", column_mapping={}).fetch("SIM-001")

    [query] = asked
    if value is not None and value.strip():
        assert value not in query
    assert set(batch.frame["CUSTOM"]) == {CUSTOM_BLANK}


def test_the_switch_is_judged_after_the_unconfigured_sql_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """끄개 판정은 본 조회문 짓기(미설정 SQL 검사) 뒤다 — 미설정 SQL 이면 끄개를 읽기 전에
    멈춰(`custom_source_problem` · `custom_source_on` 을 부르지 않음) 끄개를 내려도 「SQL 미설정」
    글이 그대로이고 패키지를 부르지 않는다. 끔이면 판정이 늘 None 이라 글만으로는 차례가 갈리지
    않아 판정 함수가 불렸는지를 본다(켬이고 변수가 없을 때 SQL 글이 먼저인 것은 변수 없음 갈래
    시험이 본다)."""
    _switch_off(monkeypatch)
    monkeypatch.delenv(adapter.BDQ_CUSTOM_TABLE_ENV)
    imported = _counting_import(monkeypatch)
    judged: list[str] = []
    switch_on = adapter.custom_source_on
    source_problem = adapter.custom_source_problem

    def spied_switch_on(environ: Mapping[str, str] | None = None) -> bool:
        judged.append("custom_source_on")
        return switch_on(environ)

    def spied_source_problem(environ: Mapping[str, str] | None = None) -> str | None:
        judged.append("custom_source_problem")
        return source_problem(environ)

    monkeypatch.setattr(adapter, "custom_source_on", spied_switch_on)
    monkeypatch.setattr(adapter, "custom_source_problem", spied_source_problem)
    unconfigured = adapter.BigDataQueryCoreDataProvider(
        "사내 조회",
        query_template=f"SELECT {adapter.UNCONFIGURED_MARKER} WHERE x = '{{simulation_code}}'",
    )

    with pytest.raises(RuntimeError, match="SQL이 아직 설정되지 않았습니다"):
        unconfigured.fetch("SIM-001")

    assert judged == []
    assert imported == []
    # 갈아 끼운 판정 함수를 상세 조회가 실제로 부르는지 — 설정된 SQL 이면 같은 끔 길이 판정한다.
    main = _two_part_main()
    monkeypatch.setattr(
        adapter,
        "load_bigdataquery_module",
        lambda: _module(_answers(main, _custom_for(main), asked=[])),
    )
    adapter.BigDataQueryCoreDataProvider("사내 조회", column_mapping={}).fetch("SIM-001")
    assert judged[0] == "custom_source_problem"


def test_catalog_sql_is_not_mixed_into_the_detail_template() -> None:
    """상세 SQL 은 78별칭 대조를 받는다. 목록 문장을 여기 합치면 그 검사가 깨진다."""
    assert "{simulation_code}" in adapter.QUERY_TEMPLATE
    assert "SELECT DISTINCT" not in adapter.QUERY_TEMPLATE


def test_package_probe_does_not_import_the_module(monkeypatch: pytest.MonkeyPatch) -> None:
    imported = False

    def fake_import(_: str) -> object:
        nonlocal imported
        imported = True
        return object()

    monkeypatch.setattr(importlib, "import_module", fake_import)

    adapter.is_bigdataquery_package_available()

    assert not imported


def test_valid_simulation_code_predicate_matches_the_validator() -> None:
    assert adapter.is_valid_simulation_code("DEMO-A_001.2") is True
    assert adapter.is_valid_simulation_code("DEMO 공백") is False
    assert adapter.is_valid_simulation_code("   ") is False


def test_the_detail_window_covers_every_registration_the_catalog_saw() -> None:
    """목록에 같은 코드의 등록일이 여러 날 보였으면 기본 창이 그 사이를 자르지 않는다."""
    window = adapter.registration_detail_window(
        date(2026, 3, 1), date(2026, 3, 20), today=date(2026, 9, 29)
    )

    assert window.start_date == date(2026, 2, 22)
    assert window.end_date == date(2026, 3, 23)


def test_the_detail_window_never_ends_after_today() -> None:
    """날짜 입력의 상한이 오늘이다. 등록일이 어제거나 (시계가 어긋나) 내일이어도 창이 선다."""
    today = date(2026, 9, 29)

    yesterday = adapter.registration_detail_window(today - timedelta(days=1), today=today)
    tomorrow = adapter.registration_detail_window(today + timedelta(days=1), today=today)

    assert yesterday.start_date == today - timedelta(days=8)
    assert yesterday.end_date == today
    assert tomorrow.start_date <= tomorrow.end_date <= today


def _start_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    install: tuple[str, str] = ("skipped", "CD 환경변수 CAPA_ARTIFACTORY_USER 없음"),
    token: tuple[str, str] = ("skipped", "CD 환경변수 CAPA_BDQ_TOKEN 없음"),
    user_name: tuple[str, str] = ("skipped", "CD 환경변수 CAPA_BDQ_USER_NAME 없음"),
    missing: tuple[str, ...] = ("CAPA_ARTIFACTORY_USER", "CAPA_BDQ_TOKEN", "CAPA_BDQ_USER_NAME"),
) -> None:
    """C-DEP CD 시작 스크립트가 남기는 결과 파일(`settings.CONTAINER_START_REPORT_PATH`)."""
    import capa_simulation.settings as settings

    path = tmp_path / "container_start.json"
    steps = {"install": install, "token": token, "user_name": user_name}
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "written_at": "2026-10-24T09:00:00+09:00",
                "steps": {
                    name: {"status": status, "reason": reason}
                    for name, (status, reason) in steps.items()
                },
                "bigdataquery_version": None,
                "token_file": {"exists": None, "modified_at": None},
                "user_name": {"present": False, "masked": None},
                "missing_environment": list(missing),
                "pip_tail": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", path)


def test_a_missing_package_in_the_cd_container_adds_the_start_check_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CD 서버에는 셸이 없어 설치 안내(`uv pip install …`)를 따를 수 없다. 시작 스크립트가 남긴 설치
    단계 결과와 넣을 환경변수를 덧붙인다. 첫 문장은 점검 스크립트가 가르는 문구라 그대로다."""
    _start_report(tmp_path, monkeypatch, install=("failed", "설치 시도 실패 — pip 종료 코드 1"))
    monkeypatch.setitem(sys.modules, "bigdataquery", None)

    with pytest.raises(RuntimeError) as raised:
        adapter.load_bigdataquery_module()

    text = str(raised.value)
    assert text.startswith(_PACKAGE_MISSING_TEXT)
    assert "서버 시작 점검" in text and "pip 종료 코드 1" in text
    assert adapter.BDQ_USER_NAME_ENV not in text

    _start_report(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError) as raised:
        adapter.load_bigdataquery_module()
    assert "`CAPA_ARTIFACTORY_USER`" in str(raised.value)


class TokenNotFoundException(Exception):
    """사내 패키지가 로그인 토큰이 없을 때 내는 꼴(`docs/bigdataquery_webide_setup.md` 1단계)."""


def _missing_token(**_kwargs: object) -> pd.DataFrame:
    raise TokenNotFoundException(
        "There is no bigdataquery token issued for AD user 'fake' at '/config/.credential/' "
        "on 'Linux'."
    )


def test_a_missing_login_token_in_the_cd_container_adds_the_start_check_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """토큰이 없다는 패키지 예외에는 토큰 파일 단계 결과와 `CAPA_BDQ_TOKEN` 을 덧붙인다. 갈래·종류
    이름(점검 스크립트가 찍는 것)은 결과 파일이 있든 없든 같고, 끝 절만 자리대로다 — 결과 파일이
    없으면 BigDataQuery 로그인을 다시, 있으면 관리자에게."""
    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, "fake")
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(_missing_token))

    with pytest.raises(adapter.BigDataQueryCallError) as plain:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")
    assert "서버 시작 점검" not in str(plain.value)

    _start_report(tmp_path, monkeypatch)
    with pytest.raises(adapter.BigDataQueryCallError) as hinted:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    text = str(hinted.value)
    assert adapter.TOKEN_ADVICE_LOCAL in str(plain.value)
    assert text.startswith(
        str(plain.value).replace(adapter.TOKEN_ADVICE_LOCAL, adapter.TOKEN_ADVICE_SERVER)
    )
    assert "서버 시작 점검" in text and "`CAPA_BDQ_TOKEN`" in text
    assert (hinted.value.kind, hinted.value.type_names) == (
        plain.value.kind,
        plain.value.type_names,
    )


def test_a_written_token_that_is_still_refused_points_at_expiry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, "fake")
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(_missing_token))
    _start_report(tmp_path, monkeypatch, token=("ok", "토큰 파일을 씀"), missing=())

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert "만료" in str(raised.value) and "WebIDE" in str(raised.value)


class HTTPError(OSError):
    """HTTP 클라이언트가 내는 꼴 — 내장 `ConnectionError` 밖이다."""


class TokenizeLikeError(Exception):
    """이름에 token 이 들었을 뿐 로그인 토큰과 상관없는 예외."""


class InvalidTokenError(Exception):
    """무효 토큰을 종류 이름에 단 꼴."""


@pytest.mark.parametrize(
    ("error", "kind", "clue"),
    [
        (Error("invalid token"), adapter.QUERY_FAILURE_TOKEN, "invalid token"),
        (Error("HTTP 500 invalid token"), adapter.QUERY_FAILURE_TOKEN, "invalid token"),
        (ConnectionError("500 invalid token"), adapter.QUERY_FAILURE_TOKEN, "invalid token"),
        (
            _chained(HTTPError("500 Server Error for url"), ConnectionError("Invalid Token")),
            adapter.QUERY_FAILURE_TOKEN,
            "invalid token",
        ),
        (Error("Token expired"), adapter.QUERY_FAILURE_TOKEN, "token expired"),
        (Error("the token has expired"), adapter.QUERY_FAILURE_TOKEN, "token has expired"),
        (Error('{"error": "invalid_token"}'), adapter.QUERY_FAILURE_TOKEN, "invalid_token"),
        (
            TokenNotFoundException("There is no bigdataquery token issued for AD user 'fake'"),
            adapter.QUERY_FAILURE_TOKEN,
            "",
        ),
        (
            TokenNotFoundException("no bigdataquery token for the query (… analysis)"),
            adapter.QUERY_FAILURE_TOKEN,
            "",
        ),
        (
            RuntimeError("There is no bigdataquery token issued for AD user 'fake'"),
            adapter.QUERY_FAILURE_TOKEN,
            "no bigdataquery token",
        ),
        (InvalidTokenError("HTTP 500"), adapter.QUERY_FAILURE_TOKEN, ""),
        (InvalidTokenError("Syntax error at line 1"), adapter.QUERY_FAILURE_SQL, "syntax"),
        (TokenizeLikeError("x"), adapter.QUERY_FAILURE_OTHER, ""),
        (
            Error("table not found at '/config/.credential/'"),
            adapter.QUERY_FAILURE_SQL,
            "not found",
        ),
        (Error("Syntax error: unexpected token"), adapter.QUERY_FAILURE_SQL, "syntax"),
        (Error("ParseException: invalid token near 'FROM'"), adapter.QUERY_FAILURE_SQL, "parse"),
        (Error("unexpected token"), adapter.QUERY_FAILURE_OTHER, ""),
        (Error("Session expired"), adapter.QUERY_FAILURE_OTHER, "expired"),
        (ConnectionError("500 Server Error"), adapter.QUERY_FAILURE_CONNECTION, ""),
        (measured_token_failure("context"), adapter.QUERY_FAILURE_TOKEN, "invalid token"),
        (measured_token_failure("cause"), adapter.QUERY_FAILURE_TOKEN, "invalid token"),
        (
            _chained(
                ConnectionError(MEASURED_OUTER),
                _chained(Exception(MEASURED_INNER), Error("AnalysisException: query rejected")),
            ),
            adapter.QUERY_FAILURE_TOKEN,
            "invalid token",
        ),
        (ConnectionError(MEASURED_OUTER), adapter.QUERY_FAILURE_CONNECTION, ""),
    ],
)
def test_a_login_token_failure_is_its_own_kind_before_connection(
    error: BaseException, kind: str, clue: str
) -> None:
    """getData 의 invalid token(HTTP 500)은 「연결」 이 아니라 「토큰」 이다 — 「연결」 안내
    (네트워크 · 다시 하기)는 틀린 길이다(리뷰 202611111500 사외요청 3). 분명한 근거만 「토큰」 이고,
    구문 오류의 token 은 SQL 그대로다. 토큰 예외 종류 이름은 문법 낱말보다 먼저다. 만료 · 무효
    토큰의 실측 꼴 사슬(바깥 `ConnectionError` · 안쪽 「You have invalid token」 — 2026-11-16)은
    안쪽이 문맥이든 원인이든, 다른 고리에 문법 낱말이 있어도 「토큰」 이고(다시 로그인 문구가 먼저),
    문구 없는 바깥 `ConnectionError` 하나는 「연결」 이다. 「토큰」 이면 시작 점검 토큰 줄
    안내(`is_login_token_failure`)도 붙는다."""
    assert (adapter.classify_query_failure(error), adapter.query_failure_clue(error)) == (
        kind,
        clue,
    )
    if kind == adapter.QUERY_FAILURE_TOKEN:
        assert adapter.is_login_token_failure(error) is True


@pytest.mark.parametrize(
    "error",
    [
        TokenizeLikeError("x"),
        Error("table not found at '/config/.credential/'"),
        Error("Could not read the bigdataquery token file"),
    ],
)
def test_the_start_check_line_reaches_wider_than_the_token_kind(error: BaseException) -> None:
    """안내(서버 시작 점검 토큰 줄)는 종류 이름의 token · 토큰 자리 문구에도 붙는다 — 덧붙일 뿐
    다시 하기 · 관리자 알림을 바꾸지 않으므로 갈래 「토큰」 보다 넓게 둔다."""
    assert adapter.is_login_token_failure(error) is True
    assert adapter.classify_query_failure(error) != adapter.QUERY_FAILURE_TOKEN


def test_a_token_failure_in_webide_asks_for_a_new_login_not_a_retry() -> None:
    """토큰은 다시 해도 같다 — 네트워크 · 다시 하기가 아니다. 서버 시작 기록이 없는 자리(WebIDE ·
    사내 PC)는 사용자가 BigDataQuery 로그인을 다시 해 토큰을 새로 받는다(2026-11-12 보드 ⑤-4 (나)).
    오래 기다린 끝이어도 시간 초과로 올리지 않는다."""
    wrapped = adapter.BigDataQueryCallError(Error("HTTP 500 invalid token"), seconds=907.4)

    assert (wrapped.kind, wrapped.clue) == (adapter.QUERY_FAILURE_TOKEN, "invalid token")
    text = str(wrapped)
    assert text.startswith("BigDataQuery 조회가 실패했습니다(토큰).")
    assert adapter.TOKEN_ADVICE_LOCAL in text and "BigDataQuery 로그인을 다시 하세요" in text
    assert "관리자에게" not in text
    assert "네트워크" not in text and "기간을 줄여" not in text


def test_a_token_failure_on_the_cd_server_advises_the_administrator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """서버 시작 기록이 있는 C-DEP 는 관리자가 토큰을 넣는다 — 결과 파일이 있거나, 없어도 CD 전용
    환경변수가 들어왔으면(시작 스크립트가 돌지 않은 C-DEP) 지금대로 「관리자에게」 다."""
    _start_report(tmp_path, monkeypatch, token=("ok", "토큰 파일을 씀"), missing=())

    text = str(adapter.BigDataQueryCallError(Error("HTTP 500 invalid token")))
    assert adapter.TOKEN_ADVICE_SERVER in text and "로그인을 다시" not in text

    import capa_simulation.settings as settings

    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", tmp_path / "absent.json")
    monkeypatch.setenv("CAPA_ARTIFACTORY_USER", "fake")
    text = str(adapter.BigDataQueryCallError(Error("HTTP 500 invalid token")))
    assert adapter.TOKEN_ADVICE_SERVER in text and "로그인을 다시" not in text


def test_an_invalid_token_in_the_cd_container_adds_the_start_check_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """「invalid token」 도 토큰 파일 단계 결과를 덧붙인다 — 토큰이 없는 꼴
    (`TokenNotFoundException`)만이 아니다. 갈래는 연결이 아니라 토큰이다."""

    def refuse(**_kwargs: object) -> pd.DataFrame:
        raise ConnectionError("500 invalid token")

    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, "fake")
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(refuse))
    _start_report(tmp_path, monkeypatch, token=("ok", "토큰 파일을 씀"), missing=())

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert raised.value.kind == adapter.QUERY_FAILURE_TOKEN
    assert "서버 시작 점검" in str(raised.value)
    assert adapter.TOKEN_ADVICE_SERVER in str(raised.value)


def test_a_missing_account_in_the_cd_container_adds_the_start_check_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def refuse(**_kwargs: object) -> pd.DataFrame:
        raise ValueError("Parameter user_name is necessary.")

    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(refuse))
    _start_report(tmp_path, monkeypatch)

    with pytest.raises(RuntimeError) as raised:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    text = str(raised.value)
    assert text.startswith("BigDataQuery 조회에 요청자의 AD 계정이 필요합니다.")
    assert "서버 시작 점검" in text and "C-DEP" in text


def test_an_unrelated_failure_gets_no_start_check_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def refuse(**_kwargs: object) -> pd.DataFrame:
        raise ValueError("table not found")

    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, "fake")
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(refuse))
    _start_report(tmp_path, monkeypatch)

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert "서버 시작 점검" not in str(raised.value)


def test_a_cd_server_without_a_start_report_says_so_after_the_missing_package_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CD 환경변수는 들어왔는데 결과 파일이 없으면(스크립트가 돌지 않음) 첫 문장 뒤에 그 사실을
    덧붙인다. 첫 문장과 점검 스크립트가 가르는 이름은 그대로다."""
    import capa_simulation.settings as settings

    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", tmp_path / "없음.json")
    monkeypatch.setenv("CAPA_ARTIFACTORY_TOKEN", "FAKE-artifactory-token")
    monkeypatch.setitem(sys.modules, "bigdataquery", None)

    with pytest.raises(RuntimeError) as raised:
        adapter.load_bigdataquery_module()

    text = str(raised.value)
    assert text.startswith(_PACKAGE_MISSING_TEXT)
    assert "서버 시작 점검 결과가 없습니다" in text and "돌지 않은 것으로" in text
    assert adapter.BDQ_USER_NAME_ENV not in text
    assert "FAKE-artifactory-token" not in text


# --- 서버 혼잡(Impala `queue full`) --------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        Error("Rejected query from pool root.default: queue full, limit=200, num_queued=200."),
        Error(
            "('HY000', '[HY000] [Cloudera][ImpalaODBC] (110) Error while executing a query in "
            "Impala: [HY000] : Admission rejected: Queue is full (SQLExecDirectW)')"
        ),
        Error("QUEUE FULL"),
        _chained(Error("Error executing SQL statement"), Error("the queue was full")),
        _chained(ConnectionError("server busy"), Error("queue full")),
    ],
)
def test_a_full_server_queue_is_its_own_kind_and_says_try_again_later(error: BaseException) -> None:
    """사내 확인(2026-11-16) — Impala 대기열이 가득 차면 `pyodbc.Error`(HY000)가 「queue full」 을
    싣고 온다. 토큰과 무관하고 잠시 뒤 다시 하면 풀린다 — 「Rejected query」 · `SQL…` 함수 이름이
    함께 실려도 그 밖이 아니라 「서버 혼잡」 이다(D8)."""
    assert (adapter.classify_query_failure(error), adapter.query_failure_clue(error)) == (
        adapter.QUERY_FAILURE_BUSY,
        adapter.BUSY_CLUE,
    )
    wrapped = adapter.BigDataQueryCallError(error, seconds=907.4)
    text = str(wrapped)
    assert (wrapped.kind, wrapped.clue) == (adapter.QUERY_FAILURE_BUSY, adapter.BUSY_CLUE)
    assert text.startswith("BigDataQuery 조회가 실패했습니다(서버 혼잡).")
    assert "잠시 뒤" in text and "다시 해도 같으니" not in text and "기간을 줄여" not in text
    assert adapter.is_login_token_failure(error) is False


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (Error("requeue fullness check"), adapter.QUERY_FAILURE_OTHER),
        (Error("queue length 3"), adapter.QUERY_FAILURE_OTHER),
        (TokenNotFoundException("no bigdataquery token (queue full)"), adapter.QUERY_FAILURE_TOKEN),
    ],
)
def test_only_the_full_queue_words_make_the_busy_kind_and_the_token_still_comes_first(
    error: BaseException, kind: str
) -> None:
    assert adapter.classify_query_failure(error) == kind


def test_a_busy_server_is_not_asked_again_by_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """서버 혼잡은 안내만 한다 — 앱은 같은 조회를 스스로 다시 묻지 않는다(D8)."""
    calls: list[int] = []

    def busy(**_kwargs: object) -> pd.DataFrame:
        calls.append(1)
        raise Error("Rejected query from pool root.default: queue full")

    monkeypatch.setattr(importlib, "import_module", lambda _: _module(busy))

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert raised.value.kind == adapter.QUERY_FAILURE_BUSY and calls == [1]
    assert adapter.last_query_failed_on_token() is False


# --- C-DEP 자동 로그인 — 조회 중 다시 로그인(D4 · 문구 기준) ------------------------------------
#
# 로그인은 진짜 하위 프로세스가 가짜 `bigdataquery`(`tests/fixtures/bdq_fake/`)를 불러 돈다.
# 장면마다 하위 프로세스에서 `login()` 이 불린 수를 센다(`FakeBdq.logins`) — 계정 잠김 방지가
# 불변식이다.


def _package_token_error() -> type[Exception]:
    """패키지의 토큰 파일 없음 예외와 같은 자리 · 이름(`bigdataquery.exceptions`)의 종류."""
    return type("TokenNotFoundException", (Exception,), {"__module__": "bigdataquery.exceptions"})


class _TokenFileReader:
    """조회마다 그 계정의 토큰 파일을 다시 읽는 `getData` — 파일이 없으면 패키지의 토큰 예외(사내
    2.5.0 확인과 같은 꼴). `always_refuse` 면 파일이 있어도 토큰 예외다."""

    def __init__(self, fake: FakeBdq, *, always_refuse: bool = False) -> None:
        self.fake = fake
        self.always_refuse = always_refuse
        self.error = _package_token_error()
        self.calls: list[dict[str, object]] = []

    def getData(self, **kwargs: object) -> pd.DataFrame:  # noqa: N802 — 패키지 이름 그대로
        self.calls.append(dict(kwargs))
        account = str(kwargs.get("user_name", ""))
        if self.always_refuse or not self.fake.token_path(account).is_file():
            raise self.error(f"There is no bigdataquery token issued for AD user {account}")
        return pd.DataFrame({"a": [1]})


@pytest.fixture()
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeBdq:
    return use_fake_bdq(monkeypatch, tmp_path)


@pytest.fixture()
def login_s3(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[MockStore, S3Target]]:
    """가짜 S3 한 벌 — 앱 프로세스의 닿을 곳(`app_target`)을 그곳으로."""
    with running_mock() as (mock, endpoint):
        target = target_of(mock, endpoint)
        monkeypatch.setattr(login_store, "app_target", lambda: target)
        yield mock, target


def _stored(monkeypatch: pytest.MonkeyPatch, target: S3Target, *, password: str = PASSWORD) -> None:
    """`managed` + 키를 켜고 계정을 저장한다(앱 프로세스 기억도 바뀐다)."""
    key = switch_on(monkeypatch)
    written = login_store.save_login(target, key.encode(), LoginSecret(ACCOUNT, password), ADMIN_ID)
    assert written.ok


def _object_state(mock: MockStore) -> str:
    with mock.lock:
        state = json.loads(mock.objects[login_store.OBJECT_KEY])["state"]
    assert isinstance(state, str)
    return state


def test_a_missing_token_logs_in_again_and_the_same_query_runs_once_more(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, login_s3: tuple[MockStore, S3Target]
) -> None:
    """저장된 계정이 `CAPA_BDQ_USER_NAME` 을 이긴다 — 조회 · 토큰 파일 · 다시 로그인이 한
    계정이다."""
    mock, target = login_s3
    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, OTHER_ACCOUNT)
    _stored(monkeypatch, target)
    module = _TokenFileReader(fake)

    frame = adapter.call_get_data(cast(adapter.BigDataQueryModule, module), "SELECT 1")

    assert isinstance(frame, pd.DataFrame) and len(frame) == 1
    assert [call["user_name"] for call in module.calls] == [ACCOUNT, ACCOUNT]
    assert fake.logins() == 1
    assert adapter.last_query_failed_on_token() is False
    assert _object_state(mock) == "ok" and bdq_login.status().state == "ok"


def test_the_relogin_reads_the_key_the_app_took_out_of_the_environment(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, login_s3: tuple[MockStore, S3Target]
) -> None:
    """운영 앱은 기동 때 키를 쥐고 환경에서 뺀다(`take_secret_key`) — 저장 객체 읽기 · 다시
    로그인이 쥔 키로 돈다."""
    _, target = login_s3
    _stored(monkeypatch, target)
    login_store.forget_state()
    login_store.take_secret_key(os.environ)
    assert login_store.SECRET_KEY_ENV not in os.environ
    module = _TokenFileReader(fake)

    frame = adapter.call_get_data(cast(adapter.BigDataQueryModule, module), "SELECT 1")

    assert isinstance(frame, pd.DataFrame)
    assert [call["user_name"] for call in module.calls] == [ACCOUNT, ACCOUNT]
    assert fake.logins() == 1


def test_a_second_token_error_after_our_own_login_stops_and_stays_a_token_failure(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, login_s3: tuple[MockStore, S3Target]
) -> None:
    mock, target = login_s3
    _stored(monkeypatch, target)
    module = _TokenFileReader(fake, always_refuse=True)

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(cast(adapter.BigDataQueryModule, module), "SELECT 1")

    assert raised.value.kind == adapter.QUERY_FAILURE_TOKEN
    assert len(module.calls) == 2 and fake.logins() == 1
    assert _object_state(mock) == "stopped"
    status = bdq_login.status()
    assert status.state == "stopped" and status.stop_reason == bdq_login.REASON_TOKEN_AFTER_LOGIN
    assert adapter.last_query_failed_on_token() is True

    with pytest.raises(adapter.BigDataQueryCallError):
        adapter.call_get_data(cast(adapter.BigDataQueryModule, module), "SELECT 1")
    assert len(module.calls) == 3 and fake.logins() == 1


def test_a_rejected_login_stops_and_returns_the_first_failure(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, login_s3: tuple[MockStore, S3Target]
) -> None:
    mock, target = login_s3
    _stored(monkeypatch, target, password=WRONG_PASSWORD)
    module = _TokenFileReader(fake)

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(cast(adapter.BigDataQueryModule, module), "SELECT 1")

    assert raised.value.kind == adapter.QUERY_FAILURE_TOKEN
    assert isinstance(raised.value.__cause__, module.error)
    assert len(module.calls) == 1 and fake.logins() == 1
    assert _object_state(mock) == "stopped"
    assert bdq_login.status().stop_reason == bdq_login.REASON_TOKEN_UNCHANGED
    for _ in range(2):
        with pytest.raises(adapter.BigDataQueryCallError):
            adapter.call_get_data(cast(adapter.BigDataQueryModule, module), "SELECT 1")
    assert fake.logins() == 1


def test_an_unreached_login_does_not_stop_and_returns_the_first_failure(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, login_s3: tuple[MockStore, S3Target]
) -> None:
    """서버에 닿지 못한 로그인은 멈추지 않는다(D6) — 원래 실패를 돌려주고, 쉬는 동안은 다시 띄우지
    않는다."""
    mock, target = login_s3
    _stored(monkeypatch, target)
    monkeypatch.setenv("FAKE_BDQ_SCENE", "connection")
    module = _TokenFileReader(fake)

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(cast(adapter.BigDataQueryModule, module), "SELECT 1")

    assert raised.value.kind == adapter.QUERY_FAILURE_TOKEN
    assert isinstance(raised.value.__cause__, module.error)
    assert len(module.calls) == 1 and fake.logins() == 1
    assert _object_state(mock) == "ok"
    status = bdq_login.status()
    assert status.state == "ok" and status.paused
    with pytest.raises(adapter.BigDataQueryCallError):
        adapter.call_get_data(cast(adapter.BigDataQueryModule, module), "SELECT 1")
    assert fake.logins() == 1


def test_a_token_failure_known_only_by_its_words_does_not_log_in(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, login_s3: tuple[MockStore, S3Target]
) -> None:
    """다시 로그인 문구(`bdq_login.RELOGIN_MESSAGES` — 「You have invalid token」) 밖의 토큰 낱말만
    맞은 갈래는 알림만이다 — 갈래는 「토큰」 이고 다시 묻지 않는다."""
    _, target = login_s3
    _stored(monkeypatch, target)
    calls: list[int] = []

    def refuse(**_kwargs: object) -> pd.DataFrame:
        calls.append(1)
        raise Error("HTTP 500 invalid token")

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(_module(refuse), "SELECT 1")

    assert raised.value.kind == adapter.QUERY_FAILURE_TOKEN
    assert calls == [1] and fake.logins() == 0
    assert adapter.last_query_failed_on_token() is True


class _MeasuredExpiry:
    """만료 · 무효 토큰에 실측 꼴 사슬을 내는 `getData` — 토큰 파일이 처음 내용(`stale`)이거나
    `always_refuse` 면 바깥 `ConnectionError` · 안쪽 「You have invalid token」(2026-11-16)."""

    def __init__(self, fake: FakeBdq, stale: bytes, *, link: str, always_refuse: bool = False):
        self.fake = fake
        self.stale = stale
        self.link = link
        self.always_refuse = always_refuse
        self.calls: list[dict[str, object]] = []

    def getData(self, **kwargs: object) -> pd.DataFrame:  # noqa: N802 — 패키지 이름 그대로
        self.calls.append(dict(kwargs))
        account = str(kwargs.get("user_name", ""))
        if self.always_refuse or self.fake.token_path(account).read_bytes() == self.stale:
            raise measured_token_failure(self.link)
        return pd.DataFrame({"a": [1]})


@pytest.mark.parametrize("link", ["context", "cause"])
def test_a_measured_expiry_logs_in_again_and_the_same_query_runs_once_more(
    link: str, monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, login_s3: tuple[MockStore, S3Target]
) -> None:
    """만료 · 무효 토큰의 실측 꼴 사슬(2026-11-16 사용자 결정 — 문구 기준)도 다시 로그인 1번 + 같은
    조회 1번 다시다 — 바깥 `ConnectionError` 를 연결 실패로 먼저 가르지 않는다."""
    mock, target = login_s3
    _stored(monkeypatch, target)
    module = _MeasuredExpiry(fake, fake.write_expired_token(), link=link)

    frame = adapter.call_get_data(cast(adapter.BigDataQueryModule, module), "SELECT 1")

    assert isinstance(frame, pd.DataFrame) and len(frame) == 1
    assert [call["user_name"] for call in module.calls] == [ACCOUNT, ACCOUNT]
    assert fake.logins() == 1
    assert adapter.last_query_failed_on_token() is False
    assert _object_state(mock) == "ok" and bdq_login.status().state == "ok"


@pytest.mark.parametrize("link", ["context", "cause"])
def test_a_measured_failure_again_after_our_own_login_stops_as_a_token_failure(
    link: str, monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, login_s3: tuple[MockStore, S3Target]
) -> None:
    """다시 로그인한 뒤 다시 한 조회도 같은 사슬 — 멈춤을 저장하고(D4) 갈래는 「연결」 이 아니라
    「토큰」 이다(다시 로그인 판정과 갈래가 어긋나지 않는다)."""
    mock, target = login_s3
    _stored(monkeypatch, target)
    module = _MeasuredExpiry(fake, fake.write_expired_token(), link=link, always_refuse=True)

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(cast(adapter.BigDataQueryModule, module), "SELECT 1")

    assert (raised.value.kind, raised.value.clue) == (adapter.QUERY_FAILURE_TOKEN, "invalid token")
    assert isinstance(raised.value.__cause__, ConnectionError)
    assert len(module.calls) == 2 and fake.logins() == 1
    assert _object_state(mock) == "stopped"
    status = bdq_login.status()
    assert status.state == "stopped" and status.stop_reason == bdq_login.REASON_TOKEN_AFTER_LOGIN
    assert adapter.last_query_failed_on_token() is True


_SYNTAX_TEXT = "AnalysisException: Syntax error in line 1: SELEC 1"


class _MeasuredThen:
    """토큰 파일이 처음 내용(`stale`)이면 실측 꼴 토큰 실패, 바뀐 뒤(다시 로그인 뒤)에는
    `later()` 의 실패를 내는 `getData`. 낸 예외를 `raised` 에 모은다."""

    def __init__(self, fake: FakeBdq, stale: bytes, later: Callable[[], BaseException]) -> None:
        self.fake = fake
        self.stale = stale
        self.later = later
        self.calls: list[dict[str, object]] = []
        self.raised: list[BaseException] = []

    def getData(self, **kwargs: object) -> pd.DataFrame:  # noqa: N802 — 패키지 이름 그대로
        self.calls.append(dict(kwargs))
        dead = self.fake.token_path(str(kwargs.get("user_name", ""))).read_bytes() == self.stale
        self.raised.append(measured_token_failure() if dead else self.later())
        raise self.raised[-1]


@pytest.mark.parametrize(
    ("later", "kind"),
    [
        (lambda: Error(_SYNTAX_TEXT), adapter.QUERY_FAILURE_SQL),
        (lambda: ConnectionRefusedError("Connection refused"), adapter.QUERY_FAILURE_CONNECTION),
        (lambda: TimeoutError("read timed out"), adapter.QUERY_FAILURE_TIMEOUT),
    ],
    ids=["sql", "connection", "timeout"],
)
def test_a_failure_after_our_own_login_that_is_not_a_token_error_does_not_stop(
    later: Callable[[], BaseException],
    kind: str,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeBdq,
    login_s3: tuple[MockStore, S3Target],
) -> None:
    """실측 꼴 토큰 실패 → 다시 로그인 1번 → 다시 한 조회가 토큰과 상관없는 실패 — 그 실패의 갈래로
    올라가고 멈추지 않으며 토큰 표지도 서지 않는다(멈춤은 다시 한 조회도 토큰 오류일 때만 — D4)."""
    mock, target = login_s3
    _stored(monkeypatch, target)
    module = _MeasuredThen(fake, fake.write_expired_token(), later)

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(cast(adapter.BigDataQueryModule, module), "SELECT 1")

    assert raised.value.kind == kind
    assert len(module.raised) == 2 and raised.value.__cause__ is module.raised[1]
    assert len(module.calls) == 2 and fake.logins() == 1
    assert _object_state(mock) == "ok"
    status = bdq_login.status()
    assert status.state == "ok" and not status.stop_reason
    assert adapter.last_query_failed_on_token() is False


def _earlier_failure(shape: str) -> RuntimeError:
    """호출자가 받아 들고 있는 앞 조회의 실패 — 어댑터가 감싼 토큰 실패(`call_error`), 그 글에
    문구가 실린 것(`call_error_phrase_in_text` — 패키지 바깥 글에 문구가 온 꼴), 모듈 창구가 그
    글을 옮겨 감싼 것(`module_error_phrase_in_text`)."""
    first = measured_token_failure() if shape == "call_error" else Exception(MEASURED_INNER)
    try:
        raise adapter.BigDataQueryCallError(first) from first
    except adapter.BigDataQueryCallError as call_error:
        if shape != "module_error_phrase_in_text":
            return call_error
        try:
            raise module_helpers.BigDataQueryError(call_error.kind, str(call_error)) from call_error
        except module_helpers.BigDataQueryError as module_error:
            return module_error


@pytest.mark.parametrize(
    "shape", ["call_error", "call_error_phrase_in_text", "module_error_phrase_in_text"]
)
def test_a_query_while_the_caller_handles_an_earlier_token_failure_does_not_log_in(
    shape: str, monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, login_s3: tuple[MockStore, S3Target]
) -> None:
    """호출자 · 모듈이 앞 토큰 실패를 처리하는 `except` 안에서 다시 조회했고 그 조회는 구문 오류 —
    앞 실패의 사슬(어댑터 · 모듈 창구가 감싼 것과 그 글)을 보지 않아 로그인 0번 · 조회 1번 · 갈래
    SQL 이고 멈춤도 토큰 표지도 없다."""
    mock, target = login_s3
    _stored(monkeypatch, target)
    fake.write_live_token()
    calls: list[int] = []

    def syntax(**_kwargs: object) -> pd.DataFrame:
        calls.append(1)
        raise Error(_SYNTAX_TEXT)

    earlier = _earlier_failure(shape)
    phrase_in_text = bdq_login.RELOGIN_MESSAGES[0] in str(earlier).casefold()
    assert phrase_in_text == (shape != "call_error")
    try:
        raise earlier
    except RuntimeError:
        with pytest.raises(adapter.BigDataQueryCallError) as raised:
            adapter.call_get_data(_module(syntax), "SELEC 1")

    assert raised.value.kind == adapter.QUERY_FAILURE_SQL
    assert raised.value.type_names == ("Error",)
    assert calls == [1] and fake.logins() == 0
    assert _object_state(mock) == "ok" and bdq_login.status().state == "ok"
    assert adapter.last_query_failed_on_token() is False


def test_the_failure_walk_reads_an_app_made_head_but_stops_before_a_later_one() -> None:
    """갈래 · 종류 이름은 다시 로그인과 같은 걷기다 — 머리 고리는 감싼 예외여도 읽어 그 원인을
    따라가고, 둘째 고리부터는 앱이 만든 예외 앞에서 멈춘다."""
    wrapped = _earlier_failure("call_error")
    assert adapter.classify_query_failure(wrapped) == adapter.QUERY_FAILURE_TOKEN
    assert adapter.failure_type_names(wrapped) == (
        "BigDataQueryCallError",
        "ConnectionError",
        "Exception",
    )
    try:
        raise wrapped
    except RuntimeError:
        try:
            raise Error(_SYNTAX_TEXT)
        except Error as later:
            assert later.__context__ is wrapped
            assert adapter.classify_query_failure(later) == adapter.QUERY_FAILURE_SQL
            assert not adapter.is_login_token_failure(later)
            assert adapter.failure_type_names(later) == ("Error",)


@pytest.mark.parametrize("code", [400, 500, 502, 503])
def test_the_relogin_phrase_is_the_token_kind_whatever_the_response_code(code: int) -> None:
    """갈래도 다시 로그인처럼 응답 코드를 보지 않는다(실측은 400) — 같은 문구면 5xx 여도
    「토큰」."""
    inner = Exception(MEASURED_INNER.replace("Code : 400", f"Code : {code}"))
    outer = ConnectionError(MEASURED_OUTER)
    outer.__context__ = inner
    assert (adapter.classify_query_failure(outer), adapter.query_failure_clue(outer)) == (
        adapter.QUERY_FAILURE_TOKEN,
        "invalid token",
    )


def test_an_authentication_connection_error_without_the_phrase_does_not_log_in(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, login_s3: tuple[MockStore, S3Target]
) -> None:
    """바깥 `ConnectionError` 만 오고 안쪽 문구가 없으면 다시 로그인하지 않는다 — 갈래 「연결」."""
    _, target = login_s3
    _stored(monkeypatch, target)
    calls: list[int] = []

    def refuse(**_kwargs: object) -> pd.DataFrame:
        calls.append(1)
        raise ConnectionError(MEASURED_OUTER)

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(_module(refuse), "SELECT 1")

    assert raised.value.kind == adapter.QUERY_FAILURE_CONNECTION
    assert calls == [1] and fake.logins() == 0
    assert adapter.last_query_failed_on_token() is False


def test_a_busy_server_with_a_stored_login_does_not_log_in(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, login_s3: tuple[MockStore, S3Target]
) -> None:
    _, target = login_s3
    _stored(monkeypatch, target)
    calls: list[int] = []

    def busy(**_kwargs: object) -> pd.DataFrame:
        calls.append(1)
        raise Error("Rejected query from pool root.default: queue full")

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(_module(busy), "SELECT 1")

    assert raised.value.kind == adapter.QUERY_FAILURE_BUSY
    assert calls == [1] and fake.logins() == 0


def test_without_a_key_or_a_stored_login_the_query_is_as_before(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, login_s3: tuple[MockStore, S3Target]
) -> None:
    """잠든 불변식 — 키가 없으면 S3 에 묻지 않고 하위 프로세스도 띄우지 않으며 인자 · 실패가 지금과
    같다. 키가 있어도 저장된 계정이 없으면 S3 읽기 한 번 뒤 같은 인자 · 갈래다(끝 절은 키가 CD 전용
    이름이라 서버 안내 — `token_advice`)."""
    mock, _ = login_s3
    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, OTHER_ACCOUNT)
    spawned: list[object] = []
    real_run = subprocess.run

    def record(*args: object, **kwargs: object) -> object:
        spawned.append(args)
        return real_run(*args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(subprocess, "run", record)
    module = _TokenFileReader(fake)

    with pytest.raises(adapter.BigDataQueryCallError) as plain:
        adapter.call_get_data(cast(adapter.BigDataQueryModule, module), "SELECT 1")
    assert module.calls == [
        {"param": "SELECT 1", "convert_type": True, "verbose": True, "user_name": OTHER_ACCOUNT}
    ]
    assert plain.value.kind == adapter.QUERY_FAILURE_TOKEN
    assert requests_on(mock, login_store.OBJECT_KEY) == []

    switch_on(monkeypatch)
    login_store.forget_state()
    with pytest.raises(adapter.BigDataQueryCallError) as keyed:
        adapter.call_get_data(cast(adapter.BigDataQueryModule, module), "SELECT 1")
    assert module.calls[-1] == module.calls[0] and len(module.calls) == 2
    assert (keyed.value.kind, keyed.value.type_names) == (plain.value.kind, plain.value.type_names)
    assert requests_on(mock, login_store.OBJECT_KEY) == ["GET"]
    assert spawned == [] and fake.logins() == 0


def test_an_account_changed_in_the_form_is_used_by_the_next_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """폼으로 계정이 바뀌면(저장소 기억이 바뀐다) 떠 있는 앱의 다음 조회가 곧바로 새 ID 다."""
    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, "env_account")
    captured: list[object] = []

    def answer(**kwargs: object) -> pd.DataFrame:
        captured.append(kwargs.get("user_name"))
        return pd.DataFrame({"a": [1]})

    def remember(account: str) -> None:
        login_store.remember(
            login_store.StoredLogin(
                LoginSecret(account, PASSWORD), "cipher", "de", "2026-11-16T09:00:00+09:00", "ok"
            )
        )

    remember(ACCOUNT)
    adapter.call_get_data(_module(answer), "SELECT 1")
    remember(OTHER_ACCOUNT)
    adapter.call_get_data(_module(answer), "SELECT 2")
    login_store.remember(None)
    adapter.call_get_data(_module(answer), "SELECT 3")

    assert captured == [ACCOUNT, OTHER_ACCOUNT, "env_account"]


def test_a_broken_store_read_falls_back_to_the_environment_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, " env_account ")

    def broken() -> object:
        raise RuntimeError("store read failed")

    monkeypatch.setattr(login_store, "current", broken)

    assert adapter.resolve_user_name() == "env_account"


def test_every_relogin_kind_and_phrase_is_also_the_token_kind() -> None:
    """다시 로그인을 거는 종류(`bdq_login.RELOGIN_EXCEPTIONS`)와 문구
    (`bdq_login.RELOGIN_MESSAGES`)는 모두 갈래 「토큰」 이다 — 한 줄을 더해도 그 실패의 안내 ·
    관리자 알림(`AD-10`)이 토큰 길을 따른다. 문구는 바깥 `ConnectionError` 의 안쪽에 있어도, 다른
    고리에 문법 낱말이 있어도 같다."""
    for qualified in bdq_login.RELOGIN_EXCEPTIONS:
        module_name, _, name = qualified.rpartition(".")
        error = type(name, (Exception,), {"__module__": module_name})("x")
        assert bdq_login.is_relogin_error(error), qualified
        assert adapter.classify_query_failure(error) == adapter.QUERY_FAILURE_TOKEN, qualified
    assert bdq_login.RELOGIN_MESSAGES
    for message in bdq_login.RELOGIN_MESSAGES:
        for error in (
            Exception(message.upper()),
            _chained(ConnectionError(MEASURED_OUTER), Exception(message)),
            _chained(ConnectionError(f"{message} (syntax)"), Error("ParseException")),
        ):
            assert bdq_login.is_relogin_error(error), (message, error)
            assert adapter.classify_query_failure(error) == adapter.QUERY_FAILURE_TOKEN, error
            assert adapter.is_login_token_failure(error), error
    assert adapter.classify_query_failure(measured_token_failure()) == adapter.QUERY_FAILURE_TOKEN
    assert MEASURED_INNER.casefold().startswith(bdq_login.RELOGIN_MESSAGES[0])


_THREAD_SCRIPT = """
import json
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from s3_mock_store import MockStore, start_mock

from capa_simulation.io import bdq_token
from capa_simulation.io import bdq_login_store as store
from capa_simulation.io import company_bigdataquery_adapter as adapter
from capa_simulation.io.bdq_login_store import LoginSecret
from capa_simulation.io.s3_small import S3Target

mock = MockStore()
server, endpoint = start_mock(mock)
target = S3Target(
    endpoint_url=endpoint,
    bucket=mock.bucket,
    region=mock.region,
    access_key=mock.access_key,
    secret_key=mock.secret_key,
)
store.app_target = lambda: target
bdq_token.CREDENTIAL_DIR = Path(os.environ["FAKE_BDQ_CREDENTIAL_DIR"])
account, password = sys.stdin.read().splitlines()[:2]
key = os.environ[store.SECRET_KEY_ENV].encode()
assert store.save_login(target, key, LoginSecret(account, password), "demo.admin").ok
out = {}


def work():
    try:
        answer = adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")
        out["rows"] = len(answer)
        out["thread"] = threading.current_thread() is not threading.main_thread()
    except BaseException as error:
        out["error"] = type(error).__name__
        out["kind"] = getattr(error, "kind", "")


worker = threading.Thread(target=work)
worker.start()
worker.join(120)
out["streamlit"] = "streamlit" in sys.modules
print(json.dumps(out))
"""


_THREAD_ROWS = {"rows": 1, "thread": True, "streamlit": False}


@pytest.mark.parametrize(
    ("start", "password", "expected"),
    [
        ("missing", PASSWORD, _THREAD_ROWS),
        ("expired", PASSWORD, _THREAD_ROWS),
        ("revoked", PASSWORD, _THREAD_ROWS),
        (
            "expired",
            WRONG_PASSWORD,
            {"error": "BigDataQueryCallError", "kind": "토큰", "streamlit": False},
        ),
    ],
)
def test_the_relogin_runs_in_a_plain_thread_without_streamlit(
    start: str,
    password: str,
    expected: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeBdq,
) -> None:
    """공식버전 자동 갱신 스레드도 어댑터를 지난다 — 실행 문맥 없는 스레드에서 토큰 예외 → 다시
    로그인 → 같은 조회가 돌고, 그 길 어디에서도 Streamlit 을 불러오지 않는다(부를 수 없다). 가짜
    패키지를 그대로 불러오는 별도 프로세스라 진짜 `bigdataquery.exceptions` 자리의 종류(토큰 파일
    없음)와 사내 실측 꼴 사슬(만료 · 다른 로그인으로 밀려난 토큰 — 바깥 `ConnectionError` · 안쪽
    「You have invalid token」)을 그대로 받는다. 로그인이 거절되면 첫 실패가 갈래 「토큰」 으로
    올라간다."""
    if start == "expired":
        fake.write_expired_token()
    elif start == "revoked":
        monkeypatch.setenv("FAKE_BDQ_REVOKED", fake.write_live_token().decode("ascii"))
    key = switch_on(monkeypatch)
    # Windows 파이프의 로캘을 흉내 낸다 — 스크립트가 제 프로세스 안에서 불러오는 가짜 패키지의
    # 배너도, 로그인 하위 프로세스도 UTF-8 로 선다.
    monkeypatch.setenv("PYTHONIOENCODING", "cp949")
    completed = run_with_fake_package(
        _THREAD_SCRIPT,
        str(PROJECT_ROOT / "scripts"),
        input_text=f"{ACCOUNT}\n{password}\n",
        extra_env={login_store.SECRET_KEY_ENV: key},
        timeout=180,
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert result == expected
    assert fake.logins() == 1


def test_the_failure_text_hides_the_requester_accounts(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, login_s3: tuple[MockStore, S3Target]
) -> None:
    """패키지 문구가 요청자 계정을 실어도 화면 · 모듈로 가는 실패 글에 저장된 BDQ 계정 ID ·
    `CAPA_BDQ_USER_NAME` 이 없다(D7 — 조회한 누구나 보는 글이다)."""
    from capa_simulation import module_helpers

    _, target = login_s3
    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, OTHER_ACCOUNT)
    _stored(monkeypatch, target, password=WRONG_PASSWORD)
    module = _TokenFileReader(fake)
    error = module.error(f"no token for {ACCOUNT} (env {OTHER_ACCOUNT})")
    text = str(adapter.BigDataQueryCallError(error))
    assert ACCOUNT not in text and OTHER_ACCOUNT not in text
    assert f"no token for {adapter.ACCOUNT_MASK}" in text

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(cast(adapter.BigDataQueryModule, module), "SELECT 1")
    assert ACCOUNT not in str(raised.value)

    monkeypatch.setattr(adapter, "load_bigdataquery_module", lambda: module)
    monkeypatch.setattr(module_helpers, "in_module_test_run", lambda: False)
    with pytest.raises(module_helpers.BigDataQueryError) as from_module:
        module_helpers.query_bigdataquery("demo_mod", "SELECT 1")
    assert ACCOUNT not in str(from_module.value)
    assert OTHER_ACCOUNT not in str(from_module.value)


def test_source_corrections_set_mpga_test_module_count_to_one() -> None:
    """원천 보정 함수 하나가 MPGA TEST 의 모듈수 0.95 ~ 0.96(양 끝 포함)을 1 로 보고, 범위 밖 값과
    다른 공정은 그대로 둔다. 받은 표를 그 자리에서 고쳐 같은 표를 돌려준다(사본을 더 들지 않음)."""
    frame = pd.DataFrame(
        {
            "공정": [
                "MPGA TEST",
                "MPGA TEST",
                " MPGA TEST ",
                "MPGA TEST",
                "MPGA TEST",
                "MPGA TEST",
                "ASSY",
            ],
            "모듈수": [0.95, 0.955, 0.96, 0.949, 0.961, 2, 0.955],
            **_part_columns(7),
        }
    )
    before = frame.copy()

    corrected = adapter.apply_source_corrections(frame)

    assert corrected is frame
    assert corrected["모듈수"].tolist() == [1, 1, 1, 0.949, 0.961, 2, 0.955]
    pd.testing.assert_frame_equal(corrected.drop(columns="모듈수"), before.drop(columns="모듈수"))
