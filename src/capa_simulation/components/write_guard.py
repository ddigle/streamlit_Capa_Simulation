# Purpose: 쓰기 단추의 빠른 두 번 누름이 한 번만 쓰고 저장과 거부를 뒤바꿔 알리지 않게 한다.

"""빠른 두 번 누름이 **겹쳐** 올 때의 거름.

쓰기 단추는 그린 회차의 key 세대를 콜백 인자로 받아 지금 세대와 다르면 쓰지 않는다
(AGENTS 9장). 그 비교만으로는 둘째 누름이 **첫 쓰기의 뒷정리가 끝난 뒤** 닿을 때만
막힌다. 브라우저 더블클릭은 그렇지 않다 — Streamlit 1.63 은 `runner.fastReruns`(기본
켜짐)로 둘째 누름이 닿는 순간 돌던 회차에 멈춤을 걸고 새 회차를 세운다. 두 회차는
스레드가 다르고 세션 칸 잠금(`SafeSessionState`)도 회차마다 따로라, 두 콜백이 수 ms
차이로 같은 세대를 보고 둘 다 썼다(2026-10-25 E2E — VOC 글·답변이 두 건). 멈춤을 받은
첫 콜백은 DB 에 쓴 뒤 다음 세션 칸 접근에서 `StopException` 으로 끊겨 세대도 못 올린다.

그래서 `write_once` 는 두 가지를 한다.

- 세대 비교와 쓰기를 **프로세스 잠금 하나** 안에서 한다. 둘째 콜백은 첫 쓰기가 끝날
  때까지 기다린다.
- 「이 세대는 썼다」 는 세션 칸이 아니라 **세션에 걸어 둔 dict 하나**에 적는다. 세션 칸
  쓰기는 멈춤을 받은 회차에서 그 자리에서 끊기지만 dict 칸 쓰기는 Streamlit 을 거치지
  않아 끊기지 않는다. 첫 콜백이 세대를 못 올리고 끊겨도 둘째 콜백이 그 표지를 보고 쓰지
  않은 채 뒷정리(알림·비우기·세대 올리기)만 한다.

`write` 는 잠금 안에서 표지를 적기 전에 돈다. 그 안에서 세션 칸을 읽지 않는다 — 세션 칸
접근도 끊기는 자리라, 입력은 부르기 전에 읽어 둔다.

**버전 대조 저장**(공용 프로필 — 공정 표시명·표시순서·판정 기준·확보율 보정)은 본문에서 저장하고
`st.rerun()` 한다. 둘째 누름의 회차가 그 rerun 회차를 끊으면 편집 시작 version 이 저장 전 그대로라
저장소가 `ProfileVersionConflict` 로 거부했고, 화면은 방금 한 제 저장을 「다른 사용자가 먼저 저장」
이라 알렸다(2026-10-26 E2E). 저장 전에 `profile_save_marks` 로 받아 둔 dict 에 저장에 성공한
`(편집 시작, 저장된)` version 짝을 적고, 거부가 그 짝이면(`is_own_profile_save`) 오류 대신 성공을
다시 알린다 — 그 사이 남이 저장했으면 지금 version 이 짝과 달라 그대로 거부를 알린다.

거꾸로 **남이 먼저 저장해 거부된** 누름의 둘째 누름도 거른다. 거부한 회차는 최신 저장본을 그리며
편집 시작 version 을 그 version 으로 올린다(다음 저장은 그 화면에서 출발한다). 사용자가 그 화면을
보기도 전에 닿은 둘째 누름은 옛 화면의 입력을 든 채 그 version 으로 대조를 지나, 거부 알림이
「저장했습니다」로 바뀌고 입력은 말없이 버려지거나 남의 새 저장을 덮었다(2026-10-26 E2E — 판정
기준·공정 표시명·확보율 보정). 거부를 받으면 `profile_conflict_marks` 로 미리 받아 둔 dict 에 그
알림과 시각을 곧바로 적고(`note_profile_conflict`), `TRAILING_PRESS_SECONDS` 안의 다음 제출은
저장하지 않고 그 거부를 다시 알린다(`held_profile_conflict`). 창이 지나면 새 화면을 보고 다시 누른
저장이라 평소대로 대조한다.

**아주 빠른** 두 번 누름(0.05~0.15초)은 둘째 누름이 아직 옛 화면의 단추에 닿는다. 그 회차는
쓰지 않고(지나간 세대·이미 지운 글·잠긴 단추) 끝나는데, 첫 쓰기의 성공 알림은 앞 회차가 이미 꺼내
그렸다 — 둘째 회차가 화면을 다시 그리며 알림이 사라져, 한 건 쓰였는데 아무 알림도 남지 않았다
(2026-10-26 E2E — VOC 글 올리기·Preference 프리셋 삭제). 세대 쓰기는 `just_written` 으로 그 꼬리를
알아보고 성공을 다시 알린다. 누름이 회차에 닿지 않는 단추(잠긴 단추는 Streamlit 이 값을 버린다)는
쓰기 전에 `notice_marks` 로 받아 둔 dict 에 알림과 시각을 적고(`note_notice`), 그 창 안의 회차가
`held_notice` 로 다시 그린다.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping

import streamlit as st

# 쓰기를 마친 세대의 표지(세대 칸 이름 → 그 세대). 세션마다 하나이고 처음 쓰는 콜백이
# 잠금 안에서 건다.
WRITE_MARKS_KEY = "write_guard_marks"

# 세대를 쓴 시각(세대 칸 이름 → `time.monotonic()`). `write_once` 가 표지와 함께 적는다.
RECENT_WRITES_KEY = "write_guard_recent_writes"
# 쓰기 직후 이 안에 들어온 **빈** 제출은 같은 단추의 느린 두 번 누름의 꼬리로 본다. 사람 더블클릭
# 간격(Windows 기본 0.5초)에 회차 한 번의 여유를 더한 값이다.
TRAILING_PRESS_SECONDS = 1.0

# 이 세션이 마지막으로 한 버전 대조 저장(저장 이름 → (편집 시작 version, 저장된 version)).
PROFILE_SAVES_KEY = "write_guard_profile_saves"

# 이 세션이 마지막으로 받은 버전 충돌 거부(저장 이름 → (거부 알림 글, 받은 시각)). 시각은
# `time.monotonic()` 이다.
PROFILE_CONFLICTS_KEY = "write_guard_profile_conflicts"

# 이 세션이 마지막으로 낸 쓰기 알림(알림 칸 이름 → (알림 글, 쓴 시각 `time.monotonic()`)).
RECENT_NOTICES_KEY = "write_guard_recent_notices"

# 세션을 가리지 않는 잠금 하나다. 두 회차의 세션 칸 잠금이 따로라 세션 안에 둘 자리가
# 없고, 잠그는 동안 하는 일은 기록 한 줄 쓰기다.
_WRITE_LOCK = threading.Lock()


def current_generation(counter_key: str) -> int:
    """세대 칸의 지금 값. 아직 없거나 정수가 아니면 0 이다."""
    value = st.session_state.get(counter_key, 0)
    return value if isinstance(value, int) else 0


def write_once(counter_key: str, generation: int, write: Callable[[], object]) -> bool:
    """그린 회차의 세대(`generation`)로 `write` 를 **세대마다 한 번만** 부른다.

    - `False` — 지나간 화면의 누름이다(지금 세대가 다르다). 쓰지 않았다. 부르는 쪽은
      알리지 않고, 옛 화면이 함께 보낸 입력은 이미 쓴 것이라 비우기만 한다.
    - `True` — 이 세대의 쓰기가 끝났다. 이 누름이 썼거나, 겹쳐 온 같은 세대의 누름이 쓰고
      뒷정리 전에 끊겼다. 부르는 쪽은 뒷정리를 하고 **세대 올리기를 맨 끝에** 둔다 — 그
      앞에서 끊기면 다음 누름이 표지를 보고 뒷정리를 잇는다.

    `write` 가 던진 예외는 그대로 나간다. 표지를 남기지 않으므로 다시 누르면 다시 쓴다.
    """
    with _WRITE_LOCK:
        if generation != current_generation(counter_key):
            return False
        marks = st.session_state.get(WRITE_MARKS_KEY)
        if not isinstance(marks, dict):
            marks = {}
            st.session_state[WRITE_MARKS_KEY] = marks
        recent = st.session_state.get(RECENT_WRITES_KEY)
        if not isinstance(recent, dict):
            recent = {}
            st.session_state[RECENT_WRITES_KEY] = recent
        if marks.get(counter_key) != generation:
            write()
            marks[counter_key] = generation
            recent[counter_key] = time.monotonic()
    return True


def just_written(counter_key: str) -> bool:
    """`counter_key` 의 쓰기가 `TRAILING_PRESS_SECONDS` 안에 있었는가.

    느린 두 번 누름(0.15~0.3초)은 둘째 누름이 첫 쓰기 뒤 **새로 그린 빈 폼**의 단추에 닿는다. 세대가
    같아 `write_once` 는 정상 제출로 보고, 빈 입력이 거절되어 방금 성공한 쓰기 자리에 「제목을
    입력하세요.」가 남았다(2026-10-26 E2E). 부르는 쪽은 입력이 **모두 빈** 제출이 이 안에 오면 쓰지
    않고 방금 성공을 다시 알린다 — 적은 것이 하나라도 있으면 정상 제출이다.
    """
    recent = st.session_state.get(RECENT_WRITES_KEY)
    if not isinstance(recent, dict):
        return False
    moment = recent.get(counter_key)
    return isinstance(moment, float) and time.monotonic() - moment < TRAILING_PRESS_SECONDS


def profile_save_marks() -> dict[str, tuple[int, int]]:
    """버전 대조 저장의 표지 dict(저장 이름 → (편집 시작 version, 저장된 version)).

    저장 **전에** 받아 두고 저장에 성공하면 이 dict 칸에 적는다. 세션 칸 쓰기는 둘째 누름의
    회차가 멈춤을 건 자리에서 끊기지만 dict 칸 쓰기는 끊기지 않는다(위 `write_once` 의 표지와
    같은 까닭).
    """
    with _WRITE_LOCK:
        marks = st.session_state.get(PROFILE_SAVES_KEY)
        if not isinstance(marks, dict):
            marks = {}
            st.session_state[PROFILE_SAVES_KEY] = marks
        return marks


def is_own_profile_save(
    name: str,
    expected: int | None,
    stored: int | None,
    marks: Mapping[str, tuple[int, int]] | None = None,
) -> bool:
    """버전 충돌 `(편집 시작 expected, 지금 stored)` 가 이 세션이 방금 한 `name` 저장 그것인가.

    그렇다면 같은 단추를 빠르게 두 번 누른 것이다 — 첫 누름이 이미 저장했고 그 뒤 아무도 저장하지
    않았다. 부르는 쪽은 거부 대신 저장 성공을 알린다. 저장 전에 받아 둔 표지 dict(`marks`)를 주면
    세션 칸을 읽지 않는다 — 거부 직후는 둘째 누름의 회차에 끊길 수 있는 자리다.
    """
    if expected is None or stored is None:
        return False
    found = st.session_state.get(PROFILE_SAVES_KEY) if marks is None else marks
    return isinstance(found, Mapping) and found.get(name) == (int(expected), int(stored))


def profile_conflict_marks() -> dict[str, tuple[str, float]]:
    """버전 대조 저장의 충돌 표지 dict(저장 이름 → (거부 알림 글, 받은 시각)).

    `profile_save_marks` 와 같이 저장 **전에** 받아 두고, 남의 저장 때문에 거부되면 곧바로
    `note_profile_conflict` 로 적는다(dict 칸 쓰기는 끊기지 않는다).
    """
    with _WRITE_LOCK:
        marks = st.session_state.get(PROFILE_CONFLICTS_KEY)
        if not isinstance(marks, dict):
            marks = {}
            st.session_state[PROFILE_CONFLICTS_KEY] = marks
        return marks


def note_profile_conflict(marks: dict[str, tuple[str, float]], name: str, message: str) -> None:
    """`name` 저장이 남의 저장 때문에 거부됐다고 적는다 — 그 거부 알림 글(`message`)과 지금 시각."""
    marks[name] = (message, time.monotonic())


def held_profile_conflict(marks: Mapping[str, tuple[str, float]], name: str) -> str | None:
    """`name` 저장이 `TRAILING_PRESS_SECONDS` 안에 남의 저장 때문에 거부됐으면 그 거부 알림 글.

    그렇다면 이번 제출은 거부된 누름과 같은 단추의 둘째 누름이다 — 옛 화면의 입력을 들었고, 거부한
    회차가 올려 둔 편집 시작 version 으로는 대조를 지난다. 부르는 쪽은 저장하지 않고 이 글을 다시
    알린다. 창이 지난 제출은 새 화면을 보고 다시 누른 저장이라 `None` 이다.
    """
    entry = marks.get(name)
    if not isinstance(entry, tuple) or len(entry) != 2:
        return None
    message, moment = entry
    if not isinstance(message, str) or not isinstance(moment, float):
        return None
    return message if time.monotonic() - moment < TRAILING_PRESS_SECONDS else None


def notice_marks() -> dict[str, tuple[str, float]]:
    """쓰기 알림 표지 dict(알림 칸 이름 → (알림 글, 쓴 시각)).

    쓰기 **전에** 받아 두고 쓰기에 성공하면 곧바로 `note_notice` 로 적는다(dict 칸 쓰기는 끊기지
    않는다 — 그 뒤 `queue_flash` 같은 세션 칸 쓰기는 둘째 누름의 회차에 끊길 수 있다).
    """
    with _WRITE_LOCK:
        marks = st.session_state.get(RECENT_NOTICES_KEY)
        if not isinstance(marks, dict):
            marks = {}
            st.session_state[RECENT_NOTICES_KEY] = marks
        return marks


def note_notice(marks: dict[str, tuple[str, float]], key: str, message: str) -> None:
    """`key` 칸에 낼 쓰기 알림(`message`)과 지금 시각을 적는다."""
    marks[key] = (message, time.monotonic())


def held_notice(key: str) -> str | None:
    """`key` 칸의 쓰기 알림이 `TRAILING_PRESS_SECONDS` 안에 났으면 그 글.

    그 창 안의 회차는 같은 단추의 빠른 둘째 누름일 수 있다 — 쓰지 않고 끝나 첫 쓰기의 알림을 지운다.
    부르는 쪽은 담아 둔 알림(`flash.render_flash`)이 없을 때 이 글을 그 자리에 다시 그린다.
    """
    marks = st.session_state.get(RECENT_NOTICES_KEY)
    if not isinstance(marks, dict):
        return None
    entry = marks.get(key)
    if not isinstance(entry, tuple) or len(entry) != 2:
        return None
    message, moment = entry
    if not isinstance(message, str) or not isinstance(moment, float):
        return None
    return message if time.monotonic() - moment < TRAILING_PRESS_SECONDS else None
