# Purpose: 화면 단추로 여는 팝업을 그 화면의 키 붙은 호스트 프래그먼트 안에서 여닫는 부품을 둔다.

"""화면 팝업의 호스트 프래그먼트(설계 규칙 UI-PRF-01 — 보이는 데이터가 바뀌지 않는 조작은 앱 전체를
다시 돌리지 않는다).

본문 단추로 연 팝업(`st.dialog`)은 열기 · 닫기가 앱 전체 회차라 페이지를 처음부터 다시 계산했다(HOME
은 진행 막대까지 떴다). 여닫는 회차에 바뀌는 것은 열림 칸과 팝업 초안뿐이므로 사이드바 조건 팝업
(`app.py` 의 `render_condition_dialogs` · `sidebar_status.CONDITION_DIALOG_FRAGMENT_KEY`)과 같은
꼴로 **그 화면의 키 붙은 호스트 프래그먼트**가 팝업을 부른다.

- 여는 콜백(`DialogHost.open`)은 열림 칸을 적은 뒤 마지막 줄에서 호스트만 다시 돌린다
  (`sidebar_status.rerun_fragment_if_alone`). 팝업이 호스트 안에서 만들어지므로 닫기
  (X · 바깥 · Esc — `on_dismiss`)도 호스트만 돈다. 둘 다 페이지를 다시 계산하지 않는다.
- 호스트만 도는 회차의 인자(팝업을 그리는 함수와 그것이 잡은 값)는 직전 앱 전체 회차의 것이다.
  화면 · 탭 · 조건을 바꾸는 조작은 모두 앱 전체 회차라 그 값이 낡지 않는다.

**부품이 지키는 것 넷.**

1. **이벤트 칸(본문 밖 최상위 칸)에 어느 갈래든 정확히 한 자리를 쓴다** — 열렸으면 팝업 블록, 아니면
   빈 스타일 자리표시자(`IDLE_MARKUP`)다(AGENTS 9장 「프래그먼트 · 이벤트 칸」). 호스트만 도는
   회차에 Streamlit 은 이벤트 칸 쓰기 위치를 앱 전체 회차에서 호스트를 부른 자리로 되돌리고
   브라우저는 그 자리만 갈아 끼운다 — 앱 전체 회차에서 자리를 비워 두면 뒤 페이지 요소를 팝업이
   덮는다. 팝업 본문도 이벤트 칸에 따로 쓰지 않는다(스타일만 든 `st.html` 을 두지 않는다 — 알림
   표지는 `alerts.in_dialog` 갈래가 그 칸 안에 그린다).
2. **원본을 바꾸는 동작(저장 · 적용)은 팝업 본문이 앱 전체를 다시 돌린다** — 성공하면 `finish()`
   (열림 칸을 지우고 `st.rerun()`)로 끝낸다. 앱 전체 재실행으로 끝날 수 있는 본문은
   `sidebar_status.keeps_app_run_open` 으로 감싼다(`@st.dialog` 안쪽).
3. **판정을 못 넘으면 앱 전체 회차로 물러난다** — 직전 앱 전체 회차가 끝까지 돌지 않았거나,
   페이지가 다르거나, 이번 상호작용에서 다른 위젯도 바뀌었거나, 호스트를 찾지 못하면
   (`rerun_fragment_if_alone`), 그리고 이 열림 칸에 이미 값이 있었으면(그 팝업을 걷을 회차가
   필요하다).
4. **한 실행에 팝업은 하나다** — 여는 콜백이 `forget_page_dialogs()` 로 다른 열림 칸부터 비우고,
   호스트는 열림 칸 값 하나로 팝업 하나만 고른다.

**쓰는 법** — 화면마다 호스트 하나(열림 칸은 그 화면의 `<페이지>_open_dialog` 한 칸):

```python
HOST = DialogHost("standard_target_dialog_host", DIALOG_KEY)


@st.dialog("가용설비 붙여넣기", width="large", on_dismiss=HOST.close)
@keeps_app_run_open
def _paste_dialog() -> None:
    ...
    if saved:
        HOST.finish()  # 열림 칸을 지우고 앱 전체를 다시 돌린다


st.button(
    "가용설비 붙여넣기",
    key=PASTE_BUTTON_KEY,
    on_click=HOST.open,
    args=(PASTE_DIALOG, PASTE_BUTTON_KEY),  # (열림 값, 이 단추 key)
)
# 매 앱 전체 회차 빠짐없이 — 단추를 그린 뒤, `st.stop()` 이 걸릴 수 있는 곳보다 앞에서.
HOST.render({PASTE_DIALOG: _paste_dialog})
```

- `render` 는 `{열림 값: 팝업 함수}` 사전이나 `열림 값 → 팝업 함수 | None` 함수를 받는다. 값이
  튜플처럼 인자를 싣는 팝업(시나리오 관리 공식 지정)은 함수로 고르고, 팝업에 넘길 인자는
  `functools.partial` · 람다로 묶어 돌려준다. 고른 함수는 반드시 팝업 하나를 연다 — 열지 않을 값이면
  `None` 을 돌려준다.
- 닫힌 갈래의 자리를 다른 표지가 채워야 하면(팝업을 닫은 회차에 상태 알림을 해소하는 Space 캔버스 —
  `alerts.state(..., active=False)` 가 이벤트 칸 한 자리를 쓴다) `idle=` 로 그 함수를 준다.
- 열림 칸에 이 호스트가 모르는 값이 있으면 호스트는 지우지 않고 빈 자리만 쓴다 — 같은 칸을 쓰되 이
  호스트 밖에서 그리는 팝업(표준 목표 「입력 초기화」)이 있다.
- 닫는 회차에 앱 전체를 다시 돌려야 하는 팝업(HOME 「HOME 설정」 — 닫는 회차에 지금 조건으로 그림을
  만든다)은 `on_dismiss=HOST.close_to_app` 이다.
- 인자 없는 콜백만 받는 자리(사이드바 설정 상자
  `components/settings_box.render_settings_box(on_click=)`)는 `HOST.opener(열림 값, 단추 key)` 를
  넘긴다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from typing import NoReturn

import streamlit as st

from capa_simulation.page_bootstrap import PAGE_DIALOG_SUFFIX, forget_page_dialogs
from capa_simulation.sidebar_status import rerun_fragment_if_alone

__all__ = ["IDLE_MARKUP", "DialogBody", "DialogHost", "DialogPicker"]

# 닫힌 갈래의 이벤트 칸 자리표시자 — 스타일만 든 `st.html` 은 본문 자리를 먹지 않는다.
IDLE_MARKUP = "<style></style>"

DialogBody = Callable[[], None]
DialogPicker = Callable[[object], DialogBody | None]


@dataclass(frozen=True)
class DialogHost:
    """화면 하나의 팝업 호스트 — 호스트 프래그먼트 key 와 그 화면의 열림 칸."""

    key: str
    open_key: str

    def __post_init__(self) -> None:
        # 페이지를 옮기면 `app.py` 가 이 접미어의 칸을 버린다 — 닫지 않고 떠난 팝업이 안 뜨게.
        if not self.open_key.endswith(PAGE_DIALOG_SUFFIX):
            raise ValueError(f"열림 칸은 `{PAGE_DIALOG_SUFFIX}` 로 끝나야 합니다: {self.open_key}")

    def opened(self) -> object | None:
        """지금 열림 값(닫혔으면 None)."""
        return st.session_state.get(self.open_key)

    def open(self, value: object, widget_key: str) -> None:
        """여는 콜백(`on_click=host.open, args=(열림 값, 단추 key)`). 콜백에서만 부른다.

        다른 열림 칸부터 비우고(한 실행에 팝업 하나) 열림 값을 적은 뒤, 할 수 있으면 호스트만 다시
        돌린다. 이 열림 칸에 이미 값이 있었으면(같은 칸을 쓰는 다른 팝업 — 이 호스트 밖에서 그리는
        팝업일 수 있다) 그 팝업을 걷는 앱 전체 회차로 둔다. 다른 칸의 팝업은 막는 창이라 그 위로 이
        단추를 누를 수 없다. `rerun_fragment_if_alone` 의 재실행 예외는 잡지 않는다.
        """
        was_open = self.opened() is not None
        forget_page_dialogs()
        st.session_state[self.open_key] = value
        if was_open:
            return
        rerun_fragment_if_alone(self.key, widget_key)

    def opener(self, value: object, widget_key: str) -> Callable[[], None]:
        """인자 없는 여는 콜백 — `on_click=` 이 인자를 따로 받지 못하는 자리에 넘긴다."""
        return partial(self.open, value, widget_key)

    def close(self) -> None:
        """닫기(X · 바깥 · Esc — `on_dismiss`). 콜백이라 뒤이은 회차는 호스트만 돈다."""
        st.session_state.pop(self.open_key, None)

    def close_to_app(self) -> None:
        """닫는 회차에 앱 전체를 다시 돌리는 닫기(`on_dismiss`) — 닫는 회차에 페이지가 할 일이 있는
        팝업이 쓴다. 콜백의 `st.rerun()` 은 이 상호작용의 회차를 앱 전체로 바꾼다."""
        self.close()
        st.rerun()

    def finish(self) -> NoReturn:
        """원본을 바꾼 동작의 끝 — 열림 칸을 지우고 앱 전체를 다시 돌린다. 팝업 본문에서만 부른다
        (`st.rerun()` 은 `on_dismiss` 를 거치지 않는다)."""
        self.close()
        st.rerun()

    def render(
        self,
        dialogs: Mapping[str, DialogBody] | DialogPicker,
        *,
        idle: Callable[[], None] | None = None,
    ) -> None:
        """호스트 프래그먼트를 세운다. **매 앱 전체 회차 빠짐없이** 부른다 — 이번 회차에 등록되지
        않은 호스트는 여는 콜백(`st.rerun(<key>)`)도 팝업 닫기도 겨눌 수 없다."""
        st.fragment(_host_body, key=self.key)(self.open_key, dialogs, idle)


def _host_body(
    open_key: str,
    dialogs: Mapping[str, DialogBody] | DialogPicker,
    idle: Callable[[], None] | None,
) -> None:
    """호스트 본문 — 열림 값이 고른 팝업 하나, 아니면 닫힌 갈래의 자리 하나(이벤트 칸 정확히
    한 자리)."""
    body = _pick(dialogs, st.session_state.get(open_key))
    if body is not None:
        body()
    elif idle is not None:
        idle()
    else:
        st.html(IDLE_MARKUP)


def _pick(dialogs: Mapping[str, DialogBody] | DialogPicker, value: object) -> DialogBody | None:
    if value is None:
        return None
    if callable(dialogs):
        return dialogs(value)
    return dialogs.get(value) if isinstance(value, str) else None
