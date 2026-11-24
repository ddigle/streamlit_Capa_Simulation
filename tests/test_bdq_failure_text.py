# Purpose: 패키지 예외의 글 만들기가 깨져도 BigDataQuery 실패 판정 · 안내가 서는지 본다.

from __future__ import annotations

import pytest

from capa_simulation.io import company_bigdataquery_adapter as adapter


class _BrokenText(Exception):
    """글 만들기(`__str__`)가 깨지는 패키지 예외 꼴 — 종류 이름은 갈래 낱말을 싣지 않는다."""

    def __str__(self) -> str:
        raise RuntimeError("글을 만들 수 없음")


class _BrokenTokenNotFound(_BrokenText):
    """종류 이름이 토큰 예외(`_TOKEN_FAILURE_TYPE_WORDS` 의 `tokennotfound`)인 깨진 예외."""


def _chained(outer: BaseException, cause: BaseException) -> BaseException:
    outer.__cause__ = cause
    return outer


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
