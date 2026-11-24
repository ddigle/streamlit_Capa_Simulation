# Purpose: 패키지 예외의 글 만들기가 깨져도 BigDataQuery 실패 판정 · 안내가 서는지 본다.

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from capa_simulation.io import company_bigdataquery_adapter as adapter
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS

# 깨진 예외의 원문 한 줄 — 종류 이름과 빈 문구 자리.
_BROKEN_ORIGINAL = "원문 — _BrokenText: (문구 없음)"


class _BrokenText(Exception):
    """글 만들기(`__str__`)가 깨지는 패키지 예외 꼴 — 종류 이름은 갈래 낱말을 싣지 않는다."""

    def __str__(self) -> str:
        raise RuntimeError("글을 만들 수 없음")


class _BrokenTokenNotFound(_BrokenText):
    """종류 이름이 토큰 예외(`_TOKEN_FAILURE_TYPE_WORDS` 의 `tokennotfound`)인 깨진 예외."""


def _chained(outer: BaseException, cause: BaseException) -> BaseException:
    outer.__cause__ = cause
    return outer


def _refusing_package(error: BaseException) -> SimpleNamespace:
    """`getData` 가 `error` 를 내는 가짜 패키지."""

    def refuse(**_kwargs: object) -> object:
        raise error

    return SimpleNamespace(getData=refuse)


@pytest.mark.parametrize(
    ("error", "kind", "clue", "token"),
    [
        pytest.param(_BrokenText(), adapter.QUERY_FAILURE_OTHER, "", False, id="alone"),
        pytest.param(
            _chained(_BrokenText(), TimeoutError()),
            adapter.QUERY_FAILURE_TIMEOUT,
            "",
            False,
            id="timeout-cause",
        ),
        pytest.param(
            _BrokenTokenNotFound(), adapter.QUERY_FAILURE_TOKEN, "", True, id="token-name"
        ),
        pytest.param(
            _chained(_BrokenText(), Exception("Admission rejected: queue is full")),
            adapter.QUERY_FAILURE_BUSY,
            adapter.BUSY_CLUE,
            False,
            id="busy-cause",
        ),
        pytest.param(
            _chained(_BrokenText(), Exception("Connection refused")),
            adapter.QUERY_FAILURE_CONNECTION,
            "connect",
            False,
            id="connection-cause",
        ),
    ],
)
def test_a_failure_whose_text_breaks_is_still_sorted(
    error: BaseException, kind: str, clue: str, token: bool
) -> None:
    """고리 글을 만들다 깨지는 패키지 예외도 갈래 · 근거 낱말 · 토큰 안내 판정이 그 예외로 터지지
    않는다 — 깨진 고리는 빈 글로 보고 종류 이름과 다른 고리의 글로 가른다. 터지면 화면이 잡는
    `BigDataQueryCallError` 대신 낯선 예외가 올라가 traceback 이 남는다."""
    with pytest.raises(RuntimeError):
        str(error)
    assert adapter.classify_query_failure(error) == kind
    assert adapter.query_failure_clue(error) == clue
    assert adapter.is_login_token_failure(error) is token


def test_a_query_failing_with_unprintable_text_raises_the_call_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`getData` 가 글을 만들 수 없는 예외를 내도 화면이 잡는 `BigDataQueryCallError` 로 온다 — 원문
    한 줄은 종류 이름과 「(문구 없음)」 이고 원래 예외는 `__cause__` 에 남는다. 요청자 계정이 있어
    원문 가리기가 빈 글 위를 돈다."""
    original = _BrokenText()
    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, "DEMO_ACCOUNT")
    monkeypatch.setattr(importlib, "import_module", lambda _: _refusing_package(original))

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert isinstance(raised.value, BOOTSTRAP_ERRORS)
    assert raised.value.__cause__ is original
    assert raised.value.kind == adapter.QUERY_FAILURE_OTHER
    assert str(raised.value).endswith(_BROKEN_ORIGINAL)


def test_a_package_import_failing_with_unprintable_text_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """패키지를 불러오다 글을 만들 수 없는 예외가 나도 「불러오지 못했습니다」 안내와 원문 한 줄로
    온다 — 원문을 만들다 깨진 글 만들기의 예외가 대신 올라가지 않는다."""
    original = _BrokenText()

    def broken_import(_name: str) -> object:
        raise original

    monkeypatch.setattr(importlib, "import_module", broken_import)

    with pytest.raises(RuntimeError) as raised:
        adapter.load_bigdataquery_module()

    text = str(raised.value)
    assert "불러오지 못했습니다" in text
    assert text.endswith(_BROKEN_ORIGINAL)
    assert raised.value.__cause__ is original


def test_the_user_name_hint_survives_a_failure_whose_text_breaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """요청자 계정이 없을 때의 계정 안내 판정(문구에 `user_name` 이 있나)이 글을 만들 수 없는 예외에
    터지지 않는다 — 그 예외는 계정 안내가 아니라 `BigDataQueryCallError` 갈래로 간다."""
    original = _BrokenText()
    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(importlib, "import_module", lambda _: _refusing_package(original))
    assert adapter.resolve_user_name() is None

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert adapter.BDQ_USER_NAME_ENV not in str(raised.value)
    assert raised.value.__cause__ is original
    assert raised.value.kind == adapter.QUERY_FAILURE_OTHER
    assert str(raised.value).endswith(_BROKEN_ORIGINAL)
