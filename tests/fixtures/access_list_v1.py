# Purpose: 등급 파일을 모르는 앞 판(2e7e6e9c)의 명단 쓰기를 얼린 견본 — 되돌림 뒤 등급 이어짐을
# 잰다.

"""앞 판 명단 쓰기 견본(되돌림 시험 — `tests/test_grade_store.py`).

접속 등급을 싣기 전 판(`2e7e6e9c`)의 `access_store.render_document` 와 고침 한
번(`_changed_document` —
관리자의 넣기 · 빼기 · 등급 바꿈, 거절 화면의 스스로 등록)을 그대로 옮겨 얼린다. 앞 ZIP 으로 되돌린
동안 앞 코드가 명단 파일을 다시 써도 새 코드가 둔 등급 파일은 건드리지 않고, 다시 앞으로 오면 등록
시각이 같은 사람은 옛 등급으로, 빠졌다 다시 든 사람은 열람으로 읽혀야 한다 — 그 맞댐의 재료다.
지금 코드를 import 해 쓰면 지금 코드가 바뀔 때 함께 바뀌어 견본이 되지 못한다.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import datetime, timezone

from capa_simulation.auth.access import ListChange, ListDocument, ListEntry

OBJECT_FORMAT = 1
MAX_CHANGES = 200
GRADE_ADMIN = "admin"
GRADE_USER = "user"
GRADES = (GRADE_USER, GRADE_ADMIN)
VIA_ADMIN = "admin"
VIA_SELF = "self"


def _iso_text(moment: int) -> str:
    return datetime.fromtimestamp(moment, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def render_document(document: ListDocument) -> bytes:
    """앞 판 그대로 — 한 벌 → 파일 바이트."""
    payload = {
        "format": OBJECT_FORMAT,
        "revision": document.revision,
        "users": [
            {
                "loginid": entry.loginid,
                "grade": entry.grade if entry.grade in GRADES else GRADE_USER,
                "name": entry.name,
                "dept": entry.dept,
                "via": entry.via if entry.via == VIA_SELF else VIA_ADMIN,
                "added_by": entry.added_by,
                "added_at": entry.added_at,
            }
            for entry in document.entries
        ],
        "changes": [
            {"by": item.by, "at": item.at, "what": item.what, "loginid": item.loginid}
            for item in document.changes[-MAX_CHANGES:]
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")


def changed_document(
    document: ListDocument,
    actor: str,
    *,
    add: Iterable[str] = (),
    remove: Iterable[str] = (),
    moment: int,
    grades: Mapping[str, str] | None = None,
    joined: ListEntry | None = None,
) -> ListDocument:
    """앞 판 그대로 — 고침을 얹은 새 한 벌(첫 판 심기 · 못 읽은 항목 기록은 뺐다)."""
    stamp = _iso_text(moment)
    entries = {entry.loginid: entry for entry in document.entries}
    changes: list[ListChange] = []
    if joined is not None and joined.loginid not in entries:
        entries[joined.loginid] = replace(joined, added_at=stamp)
        changes.append(ListChange(actor, stamp, "self_add", joined.loginid))
    for key in dict.fromkeys(add):
        if key in entries:
            continue
        entries[key] = ListEntry(key, actor, stamp)
        changes.append(ListChange(actor, stamp, "add", key))
    for key in dict.fromkeys(remove):
        if entries.pop(key, None) is not None:
            changes.append(ListChange(actor, stamp, "remove", key))
    for key, grade in (grades or {}).items():
        entry = entries.get(key)
        if entry is None or entry.grade == grade:
            continue
        entries[key] = replace(entry, grade=grade)
        changes.append(ListChange(actor, stamp, f"grade {grade}", key))
    if not changes:
        return document
    return ListDocument(
        revision=document.revision + 1,
        entries=tuple(sorted(entries.values(), key=lambda entry: entry.loginid)),
        changes=(*document.changes, *changes)[-MAX_CHANGES:],
    )


def register_self(document: ListDocument, loginid: str, *, moment: int) -> ListDocument:
    """앞 판 그대로 — 거절 화면 「접속 권한 신청」 이 얹는 항목(늘 일반 등급, 있으면 그대로)."""
    joined = ListEntry(loginid, added_by=loginid, via=VIA_SELF, grade=GRADE_USER)
    return changed_document(document, loginid, moment=moment, joined=joined)
