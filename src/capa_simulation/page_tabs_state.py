# Purpose: 이 접속에서 연 화면 탭·고정·이동 대기를 세션에 두고 열기·닫기·상한 규칙을 정한다.

"""머리 띠 아래 화면 탭 줄의 상태(2026-10-24 사용자 결정).

탭 줄 자체(Components v2)는 `components/page_tabs.py` 이고 `app.py` 에서만 불러온다. 이 모듈은 UI 가
없어 공정 Capa 상세(`process_detail_state`)처럼 화면 쪽 모듈이 가볍게 불러올 수 있다.

- **탭 하나 = 화면 하나.** 탭 id 는 `PageSpec.path`(`app_pages/home.py`)다 —
  `st.switch_page` 에 그대로 넘긴다. 사이드바·HOME 칸·카드 링크·뒤로가기·주소 직접 입력, 어느
  길로 화면에 들어와도 `app.py` 가 매 회차 그 화면을 목록에 더한다(`note_current_page`). 새 탭은
  끝에 붙는다.
- **고정.** HOME 은 고정 탭으로 시작한다. 어느 탭이든 고정·고정 풀기가 되고, 고정 탭은 왼쪽에
  모이며 닫기가 없다. 고정을 풀면 닫을 수 있다. 마지막 남은 탭 하나는 닫지 않는다.
- **상한 10개.** 열린 탭이 10개일 때 목록에 없는 화면으로 가면 열지 않고 직전 화면으로 되돌린
  뒤 탭 줄에 「안 쓰는 탭을 닫아 주세요」를 띄운다(`switch_to_queued_tab`).
- **목록은 이 접속에만 산다.** 새로고침·테마 바꾸기(새로고침과 같다)는 새 세션이라 HOME
  하나로 돌아간다.
- **탭은 화면을 살려 두지 않는다.** 탭을 누르는 것은 사이드바 링크와 같은 페이지 바꾸기다.
  돌아왔을 때 남는 것은 `persist_state="session"` 위젯과 위젯이 아닌 세션 칸뿐이다. 닫아도 그
  화면의 보기 조건은 지우지 않는다 — 다시 열면 이어진다.

콜백(`components/page_tabs.py`)은 목록 칸과 이동 대기 칸만 적는다. `st.switch_page` 는 회차 본문
(`app.py` 의 `st.navigation()` 바로 뒤)에서 부른다(AGENTS 9장 「팝업과 콜백」).
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Final

import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

from capa_simulation.design.theme import THEME_QUERY_PARAM
from capa_simulation.navigation import ALL_SPECS, HOME

# 연 탭(보이는 차례, `PageSpec.path`)과 그 가운데 고정한 탭. 둘 다 글자 튜플이다 — 코드를 다시 읽은
# 서버에서도 세션 값이 그대로 읽히게 클래스를 세션에 두지 않는다.
PAGE_TABS_OPEN_KEY = "page_tabs_open"
PAGE_TABS_PINNED_KEY = "page_tabs_pinned"
# 목록(열기·닫기·고정)이 바뀔 때만 1 오른다. 탭 줄 data 와 트리거에 싣는다.
PAGE_TABS_EPOCH_KEY = "page_tabs_epoch"
# 콜백이 적은 이동 대상 path. `app.py` 가 `st.navigation()` 바로 뒤에서 꺼낸다.
PAGE_TABS_QUEUED_KEY = "page_tabs_queued_switch"
# 이번 앱 전체 회차가 **이미 열린 탭**의 화면으로 들어온 것이면 그 path, 아니면 None. 회차마다 새로
# 적는다.
PAGE_TABS_REENTRY_KEY = "page_tabs_reentry"
# 상한에 걸려 열지 못한 화면의 알림 (일련번호, 글, 아직 탭 줄에 싣지 않았나). 탭 줄은 새 일련번호를
# 한 번 띄운다.
PAGE_TABS_NOTICE_KEY = "page_tabs_notice"
# 탭 줄 컴포넌트의 key. `st-key-page_tabs_strip` 클래스가 되어 껍데기 CSS
# (`app_header.SHELL_STYLE`)가 고른다 — CSS 로 고르는 컨테이너 key 는 계약이다(AGENTS 9장). 탭 줄
# 모듈이 아니라 여기 두는 것은 `app_header` 가 이 key 를 읽기 때문이다(탭 줄 모듈은 `app.py` 에서만
# 불러온다).
PAGE_TABS_COMPONENT_KEY = "page_tabs_strip"

HOME_TAB: Final = HOME.path
MAX_TABS: Final = 10
VALID_TABS: Final = frozenset(spec.path for spec in ALL_SPECS)


@dataclass(frozen=True)
class TabStrip:
    """연 탭(보이는 차례)과 고정한 탭. 고정 탭은 늘 왼쪽에 모여 있다(`normalized`)."""

    paths: tuple[str, ...]
    pinned: frozenset[str] = frozenset()

    def is_pinned(self, path: str) -> bool:
        return path in self.pinned

    def closable(self, path: str) -> bool:
        """닫기 단추를 다는가 — 고정 탭과 마지막 남은 탭에는 달지 않는다."""
        return path in self.paths and path not in self.pinned and len(self.paths) > 1


INITIAL_STRIP: Final = TabStrip((HOME_TAB,), frozenset({HOME_TAB}))


def normalized(strip: TabStrip, valid: Collection[str] = VALID_TABS) -> TabStrip:
    """모르는 path·겹침을 걷고 고정 탭을 왼쪽에 모은다. 고정 탭끼리·나머지끼리의 차례는 그대로다.

    고정하면 그 탭은 고정 묶음의 끝으로, 풀면 나머지 묶음의 앞으로 간다 — 고정 탭이 늘 왼쪽에
    있으므로 차례를 지키며 모으는 것만으로 브라우저 탭과 같은 자리가 된다.
    """
    seen: set[str] = set()
    paths: list[str] = []
    for path in strip.paths:
        if path in valid and path not in seen:
            seen.add(path)
            paths.append(path)
    pinned = frozenset(path for path in strip.pinned if path in seen)
    ordered = (
        *(path for path in paths if path in pinned),
        *(path for path in paths if path not in pinned),
    )
    return TabStrip(ordered, pinned)


def can_open(strip: TabStrip, path: str) -> bool:
    """`path` 가 이미 열렸거나 상한 아래라 탭이 될 수 있는가."""
    return path in strip.paths or len(strip.paths) < MAX_TABS


def opened(strip: TabStrip, path: str, valid: Collection[str] = VALID_TABS) -> TabStrip:
    """없으면 끝에 붙인다. 이미 있으면 차례 그대로다. 모르는 path·상한에 걸리면 그대로 돌려준다."""
    if path not in valid or not can_open(strip, path) or path in strip.paths:
        return normalized(strip, valid)
    return normalized(TabStrip((*strip.paths, path), strip.pinned), valid)


def closed(strip: TabStrip, path: str, active: str | None) -> tuple[TabStrip, str | None]:
    """(새 목록, 옮겨 갈 탭). 닫을 수 없는 탭(없음·고정·마지막 하나)이면 (그대로, None).

    닫은 것이 지금 탭이면 오른쪽 이웃, 없으면 왼쪽 이웃으로 옮긴다. 지금 탭이 아니면 옮기지 않는다.
    """
    if not strip.closable(path):
        return strip, None
    index = strip.paths.index(path)
    rest = strip.paths[:index] + strip.paths[index + 1 :]
    remaining = TabStrip(rest, strip.pinned - {path})
    if path != active:
        return remaining, None
    return remaining, rest[min(index, len(rest) - 1)]


def pinned_to(strip: TabStrip, path: str, pinned: bool) -> TabStrip:
    """`path` 를 고정하거나 고정을 푼다. 없는 탭이면 그대로다."""
    if path not in strip.paths:
        return strip
    marks = strip.pinned | {path} if pinned else strip.pinned - {path}
    return normalized(TabStrip(strip.paths, marks))


def fallback_tab(strip: TabStrip, previous: str | None) -> str:
    """상한에 걸린 이동을 되돌릴 탭 — 직전 화면이 목록에 있으면 그것, 아니면 맨 앞 탭."""
    if previous is not None and previous in strip.paths:
        return previous
    return strip.paths[0] if strip.paths else HOME_TAB


# ------------------------------------------------------------------ 세션


def _strings(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, (tuple, list)):
        return None
    return tuple(item for item in value if isinstance(item, str))


def load_strip() -> TabStrip:
    """세션의 탭 목록. 아직 없으면(이 접속의 첫 회차) HOME 하나를 고정한 목록이다."""
    paths = _strings(st.session_state.get(PAGE_TABS_OPEN_KEY))
    if paths is None:
        return INITIAL_STRIP
    pinned = _strings(st.session_state.get(PAGE_TABS_PINNED_KEY)) or ()
    return normalized(TabStrip(paths, frozenset(pinned)))


def tabs_epoch() -> int:
    value = st.session_state.get(PAGE_TABS_EPOCH_KEY)
    return value if isinstance(value, int) else 0


def store_strip(strip: TabStrip) -> None:
    """바뀌었을 때만 적고 epoch 를 올린다. 첫 회차에는 처음 목록부터 적는다."""
    fresh = PAGE_TABS_OPEN_KEY not in st.session_state
    if not fresh and load_strip() == strip:
        return
    st.session_state[PAGE_TABS_OPEN_KEY] = strip.paths
    st.session_state[PAGE_TABS_PINNED_KEY] = tuple(
        path for path in strip.paths if path in strip.pinned
    )
    st.session_state[PAGE_TABS_EPOCH_KEY] = tabs_epoch() + 1


def note_current_page(path: str, *, page_changed: bool) -> None:
    """이번 앱 전체 회차의 화면을 목록에 더하고 「이미 연 탭으로 들어옴」 표지를 적는다.

    매 회차 멱등이다. 표지는 화면이 바뀐 회차에 그 화면이 **이미 목록에 있었을 때만** 선다
    (공정 Capa 상세가 `reentered_open_tab` 으로 읽는다). 같은 화면의 다음 회차·처음 연 화면은
    None 이다.
    """
    strip = load_strip()
    was_open = path in strip.paths and PAGE_TABS_OPEN_KEY in st.session_state
    st.session_state[PAGE_TABS_REENTRY_KEY] = path if page_changed and was_open else None
    store_strip(opened(strip, path))


def reentered_open_tab(path: str) -> bool:
    """이번 앱 전체 회차가 이미 열린 탭인 `path` 로 다시 들어온 회차인가."""
    return st.session_state.get(PAGE_TABS_REENTRY_KEY) == path


def queue_switch(path: str) -> None:
    """콜백이 부른다. 대기 칸만 적고 옮기는 것은 `switch_to_queued_tab` 이다."""
    st.session_state[PAGE_TABS_QUEUED_KEY] = path


def _notice() -> tuple[int, str, bool] | None:
    value = st.session_state.get(PAGE_TABS_NOTICE_KEY)
    if (
        isinstance(value, tuple)
        and len(value) == 3
        and isinstance(value[0], int)
        and isinstance(value[1], str)
        and isinstance(value[2], bool)
    ):
        return value[0], value[1], value[2]
    return None


def pop_fresh_notice() -> tuple[int, str] | None:
    """아직 탭 줄에 싣지 않은 상한 알림 (일련번호, 글). 한 번만 돌려주고 실었다고 적는다.

    일련번호는 남긴다 — 다음 알림이 새 번호를 받아야 탭 줄이 같은 알림으로 보지 않는다."""
    notice = _notice()
    if notice is None or not notice[2]:
        return None
    st.session_state[PAGE_TABS_NOTICE_KEY] = (notice[0], notice[1], False)
    return notice[0], notice[1]


def limit_notice(title: str) -> str:
    return f"탭은 {MAX_TABS}개까지 엽니다 — 「{title}」을(를) 열려면 안 쓰는 탭을 닫아 주세요."


def _switch(target: str) -> None:
    theme_value = st.query_params.get(THEME_QUERY_PARAM)
    try:
        # 주소를 통째로 바꾼다 — 테마 인자를 싣지 않으면 지워져 다음 로드가 첫 방문이 된다
        # (AGENTS 9장). 떠나는 화면의 다른 주소 인자(공정 Capa 상세의 `process` 등)는 지워지는
        # 것이 맞다 — 그 화면은 세션으로 다시 선다.
        st.switch_page(
            target,
            query_params={THEME_QUERY_PARAM: theme_value} if theme_value else None,
        )
    except StreamlitPageNotFoundError:
        # 내비게이션 없는 단독 실행(페이지만 띄운 AppTest). 대기 칸은 이미 꺼냈다.
        return


def switch_to_queued_tab(
    current_path: str | None,
    *,
    current_title: str = "",
    previous_path: str | None = None,
    handoff_keys: Sequence[str] = (),
) -> None:
    """탭 줄이 적어 둔 이동을 하고, 상한에 걸린 화면은 직전 화면으로 되돌린다. 회차 본문에서 부른다.

    `app.py` 의 `st.navigation()` 바로 뒤, 사이드바·머리 띠를 보내기 전이다 — 옮길 회차는 그 앞에서
    끊어 반쯤 그린 사이드바를 보내지 않는다.

    - 대기 칸이 지금 화면과 다르면 그 화면으로 옮긴다.
    - 대기 칸이 없고 지금 화면이 목록에 없는데 탭이 이미 `MAX_TABS` 개면, 알림을 남기고
      `handoff_keys`(그 화면으로 넘기던 세션 전달 칸 — 공정 Capa 상세의 HOME 칸 전달 등)를 버린 뒤
      직전 화면(`previous_path`)으로 되돌린다. 남겨 두면 나중에 다른 길로 그 화면에 들어온 방문이 이
      클릭을 이어받는다.
    """
    target = st.session_state.pop(PAGE_TABS_QUEUED_KEY, None)
    if current_path is None:
        return
    if isinstance(target, str) and target != current_path and target in VALID_TABS:
        _switch(target)
        return
    strip = load_strip()
    if PAGE_TABS_OPEN_KEY not in st.session_state or can_open(strip, current_path):
        return
    serial = (_notice() or (0, "", False))[0] + 1
    st.session_state[PAGE_TABS_NOTICE_KEY] = (
        serial,
        limit_notice(current_title or current_path),
        True,
    )
    for key in handoff_keys:
        st.session_state.pop(key, None)
    _switch(fallback_tab(strip, previous_path))
