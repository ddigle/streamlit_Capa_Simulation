# Purpose: 사내 모듈 실행 기록(실패·제외 화면·회차 시간·접두 없는 키)의 넣기·읽기·비우기를 고정한다.

from __future__ import annotations

import dataclasses
import inspect
import re

import pytest

from capa_simulation import module_failures
from capa_simulation.module_failures import (
    MAX_KEY_WARNINGS,
    ModuleFailure,
    callback_failure_key,
    clear_records,
    exclude_page,
    excluded_pages,
    key_warnings,
    last_failures,
    last_run_seconds,
    note_key_warnings,
    note_run_seconds,
    record_failure,
)


def test_the_last_failure_per_module_is_kept_without_the_message() -> None:
    record_failure("demo_a", page="main", kind="RuntimeError", where="page")
    record_failure("demo_a", page="", kind="KeyError", where="callback")
    record_failure("demo_b", page="main", kind="SystemExit", where="guard")

    failures = last_failures()
    assert set(failures) == {"demo_a", "demo_b"}
    assert (failures["demo_a"].kind, failures["demo_a"].where, failures["demo_a"].page) == (
        "KeyError",
        "callback",
        "",
    )
    assert re.fullmatch(r"\d\d:\d\d:\d\d", failures["demo_b"].at)
    # 메시지 본문(실데이터가 들 수 있다)을 받는 자리가 없다.
    assert [field.name for field in dataclasses.fields(ModuleFailure)] == [
        "at",
        "page",
        "kind",
        "where",
    ]
    assert list(inspect.signature(record_failure).parameters) == [
        "module_id",
        "page",
        "kind",
        "where",
    ]


def test_the_records_are_read_only_copies() -> None:
    record_failure("demo_a", page="main", kind="RuntimeError", where="page")
    failures = last_failures()

    with pytest.raises(TypeError):
        failures["demo_b"] = failures["demo_a"]  # type: ignore[index]
    record_failure("demo_b", page="main", kind="RuntimeError", where="page")
    assert set(failures) == {"demo_a"}


def test_excluded_pages_stay_until_cleared() -> None:
    exclude_page("demo_a", "main", "StreamlitPageNotFoundError")
    exclude_page("demo_a", "main", "StreamlitPageNotFoundError")
    exclude_page("demo_b", "two", "StreamlitAPIException")

    assert excluded_pages() == frozenset({("demo_a", "main"), ("demo_b", "two")})


def test_run_seconds_keep_the_last_value() -> None:
    note_run_seconds("demo_a", 0.5)
    note_run_seconds("demo_a", 0.25)

    assert last_run_seconds() == {"demo_a": 0.25}


def test_key_warnings_keep_at_most_five_names() -> None:
    names = [f"plain_{index}" for index in range(8)]
    note_key_warnings("demo_a", names)

    assert MAX_KEY_WARNINGS == 5
    assert key_warnings() == {"demo_a": tuple(names[:5])}


def test_clearing_empties_every_record() -> None:
    record_failure("demo_a", page="main", kind="RuntimeError", where="page")
    exclude_page("demo_a", "main", "x")
    note_run_seconds("demo_a", 1.0)
    note_key_warnings("demo_a", ["plain"])

    clear_records()

    assert (last_failures(), excluded_pages(), last_run_seconds(), key_warnings()) == (
        {},
        frozenset(),
        {},
        {},
    )


def test_the_marker_keys_sit_behind_the_module_prefix_with_an_underscore() -> None:
    """모듈 키는 `_` 로 시작하지 못하므로(`ModuleContext.key`) 표지 칸과 겹치지 않는다."""
    assert callback_failure_key("demo_ok") == "mod_demo_ok___core_callback_failure"
    assert module_failures.CALLBACK_FAILURE_SUFFIX.startswith("_")
