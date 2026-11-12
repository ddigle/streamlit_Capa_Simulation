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
  이 세션이 바꾸는 값(화면 · 탭 · 조건)은 바꾸는 조작이 모두 앱 전체 회차라 낡지 않는다. **다른
  세션이 바꿀 수 있는 공용 저장값(DB 현행값 · 공용 프로필)은 그 회차 뒤에도 바뀐다** — 아래 「쓰는
  쪽이 지키는 것」 1.

**부품이 지키는 것 다섯.**

1. **이벤트 칸(본문 밖 최상위 칸)에 어느 갈래든 정확히 한 자리를 쓴다** — 열렸으면 팝업 블록, 아니면
   빈 스타일 자리표시자(`IDLE_MARKUP`)다(AGENTS 9장 「프래그먼트 · 이벤트 칸」). 호스트만 도는
   회차에 Streamlit 은 이벤트 칸 쓰기 위치를 앱 전체 회차에서 호스트를 부른 자리로 되돌리고
   브라우저는 그 자리만 갈아 끼운다 — 앱 전체 회차에서 자리를 비워 두면 뒤 페이지 요소를 팝업이
   덮는다. 팝업 본문도 이벤트 칸에 따로 쓰지 않는다(스타일만 든 `st.html` 을 두지 않는다 — 알림
   표지는 `alerts.in_dialog` 갈래가 그 칸 안에 그린다).
2. **원본을 바꾸는 동작(저장 · 적용)은 팝업 본문이 앱 전체를 다시 돌린다** — 성공하면 `finish()`
   (열림 칸 · 입력 위젯 값을 지우고 `st.rerun()`)로 끝낸다. 앱 전체 재실행으로 끝날 수 있는 본문은
   `sidebar_status.keeps_app_run_open` 으로 감싼다(`@st.dialog` 안쪽).
3. **판정을 못 넘으면 앱 전체 회차로 물러난다** — 직전 앱 전체 회차가 끝까지 돌지 않았거나,
   페이지가 다르거나, 이번 상호작용에서 다른 위젯도 바뀌었거나, 호스트를 찾지 못하면
   (`rerun_fragment_if_alone`), 그리고 이 열림 칸에 이미 값이 있었으면(그 팝업을 걷을 회차가
   필요하다).
4. **한 실행에 팝업은 하나다** — 여는 콜백이 `forget_page_dialogs()` 로 다른 열림 칸부터 비우고,
   호스트는 열림 칸 값 하나로 팝업 하나만 고른다.
5. **닫으면 그 팝업의 입력 위젯 값을 지운다** — Streamlit 은 프래그먼트 회차에 그 회차가 돌린
   프래그먼트의 위젯만 거둔다. 팝업은 자기 프래그먼트라 호스트만 도는 닫기 회차에 그 위젯 값이
   세션에 남고, 앱 전체 회차 없이 다시 열면 브라우저는 기본값을 그리는데 서버는 옛 값을 본다(여는
   알림 `paste_form.announce_on_open` 이 다시 뜨지 않고, 확인 체크로 잠근 단추가 꺼진 체크 아래
   풀린다). 그래서 닫기(`close` — `finish` · `close_to_app` 도 거친다)가 `render(widget_keys=)` 로
   받은 그 팝업의 입력 위젯 key 를 함께 지운다.

**쓰는 쪽이 지키는 것 둘.**

1. **공용 저장값은 팝업 본문에서 다시 읽는다** — 호스트만 도는 여는 회차에 팝업이 잡은 값은 그
   화면의 마지막 앱 전체 회차의 것이라 그 사이 다른 세션이 저장한 값이 빠진다. 그 값을 채운
   양식 · 초안을 되붙이면 남의 저장을 알림 없이 옛 값으로 덮는다. 저장값을 읽는 캐시 함수(DB
   stamp · 쓰기 세대가 키)를 본문에서 다시 부른다 — 값싸다.
2. **`render(widget_keys=)` 에 팝업마다 입력 위젯 key 를 빠짐없이 준다** — 다시 열 때 기본값으로
   서야 하는 것(글 칸 · 확인 체크 · 고르는 칸 · 편집표). key 없는 입력 위젯은 key 를 달아 넣는다.
   단추 · 내려받기는 회차마다 풀리는 값이라 넣지 않아도 된다. 입력 위젯이 없는 팝업은 빈 튜플이다.

**쓰는 법** — 화면마다 호스트 하나(열림 칸은 그 화면의 `<페이지>_open_dialog` 한 칸):

```python
HOST = DialogHost("standard_target_dialog_host", DIALOG_KEY)


@st.dialog("가용설비 붙여넣기", width="large", on_dismiss=HOST.close)
@keeps_app_run_open
def _paste_dialog() -> None:
    saved = load_standard_target_availability(database)  # 공용 저장값은 본문에서 다시 읽는다
    ...
    st.text_area("가용설비 표 붙여넣기", key=PASTE_TEXT_KEY)
    ...
    if written:
        HOST.finish()  # 열림 칸 · 입력 위젯 값을 지우고 앱 전체를 다시 돌린다


st.button(
    "가용설비 붙여넣기",
    key=PASTE_BUTTON_KEY,
    on_click=HOST.open,
    args=(PASTE_DIALOG, PASTE_BUTTON_KEY),  # (열림 값, 이 단추 key)
)
# 매 앱 전체 회차 빠짐없이 — 단추를 그린 뒤, `st.stop()` 이 걸릴 수 있는 곳보다 앞에서.
HOST.render({PASTE_DIALOG: _paste_dialog}, widget_keys={PASTE_DIALOG: (PASTE_TEXT_KEY,)})
```

- `render` 는 `{열림 값: 팝업 함수}` 사전이나 `열림 값 → 팝업 함수 | None` 함수를 받는다. 값이
  튜플처럼 인자를 싣는 팝업(시나리오 관리 공식 지정)은 함수로 고르고, 팝업에 넘길 인자는
  `functools.partial` · 람다로 묶어 돌려준다. 고른 함수는 반드시 팝업 하나를 연다 — 열지 않을 값이면
  `None` 을 돌려준다.
- `widget_keys` 도 `{열림 값: key 튜플}` 사전이나 `열림 값 → key 튜플` 함수다. key 가 열림 값에
  달린 팝업(공식 지정의 확인 체크 `official_confirm_key(revision_id)`)은 함수로 준다. 호스트는
  팝업을 그린 회차에 그 key 를 세션 칸(`<호스트 key>__widget_keys`)에 적어 두고 닫기가 그것을
  지운다 — 닫기는 다음 상호작용의 콜백이라 `render` 의 인자를 볼 수 없다.
- 닫힌 갈래의 자리를 다른 표지가 채워야 하면(팝업을 닫은 회차에 상태 알림을 해소하는 팝업 —
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

__all__ = [
    "IDLE_MARKUP",
    "WIDGET_KEYS_SUFFIX",
    "DialogBody",
    "DialogHost",
    "DialogPicker",
    "DialogWidgetKeys",
]

# 닫힌 갈래의 이벤트 칸 자리표시자 — 스타일만 든 `st.html` 은 본문 자리를 먹지 않는다.
IDLE_MARKUP = "<style></style>"
# 연 팝업의 입력 위젯 key 를 닫기 콜백까지 쥐는 세션 칸의 꼬리(`<호스트 key>__widget_keys`).
WIDGET_KEYS_SUFFIX = "__widget_keys"

DialogBody = Callable[[], None]
DialogPicker = Callable[[object], DialogBody | None]
DialogWidgetKeys = Mapping[str, tuple[str, ...]] | Callable[[object], tuple[str, ...]]


@dataclass(frozen=True)
class DialogHost:
    """화면 하나의 팝업 호스트 — 호스트 프래그먼트 key 와 그 화면의 열림 칸."""

    key: str
    open_key: str

    def __post_init__(self) -> None:
        # 페이지를 옮기면 `app.py` 가 이 접미어의 칸을 버린다 — 닫지 않고 떠난 팝업이 안 뜨게.
        if not self.open_key.endswith(PAGE_DIALOG_SUFFIX):
            raise ValueError(f"열림 칸은 `{PAGE_DIALOG_SUFFIX}` 로 끝나야 합니다: {self.open_key}")

    @property
    def widget_keys_slot(self) -> str:
        """연 팝업의 입력 위젯 key 를 쥐는 세션 칸 — 호스트가 팝업을 그린 회차에 적고 닫기가
        지운다."""
        return f"{self.key}{WIDGET_KEYS_SUFFIX}"

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
        """닫기(X · 바깥 · Esc — `on_dismiss`). 콜백이라 뒤이은 회차는 호스트만 돈다.

        열림 칸과 함께 그 팝업의 입력 위젯 값을 지운다(지키는 것 5) — 호스트만 도는 회차는 팝업
        프래그먼트의 위젯을 거두지 않아, 남겨 두면 다시 연 팝업의 서버 판정이 기본값을 그린 화면과
        어긋난다.
        """
        st.session_state.pop(self.open_key, None)
        for widget_key in st.session_state.pop(self.widget_keys_slot, ()):
            st.session_state.pop(widget_key, None)

    def close_to_app(self) -> None:
        """닫는 회차에 앱 전체를 다시 돌리는 닫기(`on_dismiss`) — 닫는 회차에 페이지가 할 일이 있는
        팝업이 쓴다. 콜백의 `st.rerun()` 은 이 상호작용의 회차를 앱 전체로 바꾼다."""
        self.close()
        st.rerun()

    def finish(self) -> NoReturn:
        """원본을 바꾼 동작의 끝 — 열림 칸 · 입력 위젯 값을 지우고 앱 전체를 다시 돌린다. 팝업
        본문에서만 부른다(`st.rerun()` 은 `on_dismiss` 를 거치지 않는다)."""
        self.close()
        st.rerun()

    def render(
        self,
        dialogs: Mapping[str, DialogBody] | DialogPicker,
        *,
        widget_keys: DialogWidgetKeys,
        idle: Callable[[], None] | None = None,
    ) -> None:
        """호스트 프래그먼트를 세운다. **매 앱 전체 회차 빠짐없이** 부른다 — 이번 회차에 등록되지
        않은 호스트는 여는 콜백(`st.rerun(<key>)`)도 팝업 닫기도 겨눌 수 없다. `widget_keys` 는
        팝업마다의 입력 위젯 key 다(쓰는 쪽이 지키는 것 2)."""
        st.fragment(_host_body, key=self.key)(
            self.open_key, self.widget_keys_slot, dialogs, widget_keys, idle
        )


def _host_body(
    open_key: str,
    widget_keys_slot: str,
    dialogs: Mapping[str, DialogBody] | DialogPicker,
    widget_keys: DialogWidgetKeys,
    idle: Callable[[], None] | None,
) -> None:
    """호스트 본문 — 열림 값이 고른 팝업 하나, 아니면 닫힌 갈래의 자리 하나(이벤트 칸 정확히
    한 자리). 팝업을 그리는 회차에는 그 팝업의 입력 위젯 key 를 닫기가 볼 칸에 적는다."""
    value = st.session_state.get(open_key)
    body = _pick(dialogs, value)
    if body is not None:
        st.session_state[widget_keys_slot] = _widget_keys_of(widget_keys, value)
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


def _widget_keys_of(widget_keys: DialogWidgetKeys, value: object) -> tuple[str, ...]:
    if callable(widget_keys):
        return tuple(widget_keys(value))
    return tuple(widget_keys.get(value, ())) if isinstance(value, str) else ()
