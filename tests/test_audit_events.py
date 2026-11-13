# Purpose: 감사 사건 목록의 꼴 — 이름 규칙 · 갈래 · 결과 · 수준 · 표시명 · 스레드 이름을 지킨다.

from __future__ import annotations

import re

from capa_simulation import auto_update_scheduler, object_sync_worker
from capa_simulation.audit import events, recorder

NAME = re.compile(r"^[a-z]+(_[a-z0-9]+)*$")


def test_every_event_name_is_lowercase_words_joined_by_underscores() -> None:
    names = [spec.name for spec in events.SPECS]

    assert len(names) == len(set(names))
    assert all(NAME.match(name) for name in names), [n for n in names if not NAME.match(n)]


def test_every_event_has_a_known_category_level_and_korean_label() -> None:
    for spec in events.SPECS:
        assert spec.cat in events.CATEGORIES, spec
        assert spec.lvl in events.LEVELS, spec
        assert spec.label and any("가" <= ch <= "힣" for ch in spec.label), spec
        assert all(NAME.match(key) for key in spec.det_keys), spec


def test_the_six_categories_and_four_outcomes() -> None:
    assert list(events.CATEGORIES) == ["access", "admin", "data", "export", "audit", "system"]
    assert list(events.OUTCOMES) == ["success", "fail", "denied", "unknown"]
    assert events.OUTCOMES["unknown"] == "결과 모름"


def test_the_bad_event_name_is_itself_registered() -> None:
    assert events.spec_of(events.BAD_EVENT) is not None
    assert events.label_of("not_listed_here") == "not_listed_here"


def test_no_event_allows_free_text_keys() -> None:
    """값 원문 · 메모 · 본문 · 토큰 칸은 어느 사건의 허용 키에도 없다(설계서 3장)."""
    banned = {"note", "memo", "body", "text", "value", "token", "cookie", "secret", "dept", "jti"}
    for spec in events.SPECS:
        assert not (spec.det_keys & banned), spec


def test_system_thread_names_match_the_two_background_threads() -> None:
    assert recorder.SYSTEM_THREADS == {
        auto_update_scheduler.THREAD_NAME: "system:auto_update",
        object_sync_worker.THREAD_NAME: "system:object_sync",
    }
