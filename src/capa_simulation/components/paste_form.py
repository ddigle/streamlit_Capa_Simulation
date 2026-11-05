# Purpose: 붙여넣기 · 양식 창의 공통 부품 — 글 칸 · 적용과 양식 한 줄 · 창 크기 · 알림 길을 둔다.

"""붙여넣기 · 양식 창의 공통 부품(2026-11-05 사용자 검수 static-37 — 「이 규칙은 이러한 창에 모두
공통으로 적용」).

**꼴.** 창 안에는 글 칸과 그 입력 칸(전체 교체 확인 체크 등), 맨 아래 작업 줄만 둔다. 작업 줄은 왼쪽
「적용」 · 오른쪽 「양식 다운로드」 한 줄이다(`paste_action_row` — 좁은 폭에서 접혀도 그 차례다).

**글은 창에 두지 않는다.** 캡션 · 경고 상자 · 안내 글 · 글 칸 안내 문장(placeholder) · 입력 곁
거부를 창 안에 그리지 않고 알림창 · Alarm 으로 낸다. 붙여넣는 법(헤더 포함)은 그 화면 Guide 가
말한다.

- 창을 연 회차에 꼭 알릴 말(덮어쓰기 · 되돌릴 수 없음 · 버려지는 편집)은 `announce_on_open` 한
  번이다. 「연 회차」 는 입력 칸의 세션 값이 아직 없는 회차다 — Streamlit 이 닫힌 회차에 그리지 않은
  위젯의 값을 버리므로 닫는 길이 몇이든 다음에 열면 다시 알린다.
- 눌린 회차의 거부 · 안내는 `refuse_paste` · `tell_paste` 다(`popup_only`).
- 할 수 없는 조작은 단추 상태가 말한다(설계 규칙 UI-INP-07) — 「적용」 은 글 칸이 비었거나 확인
  체크가 꺼져 있으면 브라우저에서 잠기고 짧은 까닭 풍선이 선다. 판정이 브라우저 안에서 끝나는
  잠금이고, 서버는 눌린 회차에 같은 조건을 다시 본다.

**폼을 쓰지 않는다.** `st.download_button` 은 `st.form` 안에 들어가지 못해 「적용」 과 한 줄에 설 수
없다. 그래서 글 칸은 일반 위젯이고(초점을 잃을 때 값이 오른다 — 팝업 프래그먼트만 돈다), 「적용」 은
일반 단추다.

**창 크기.** `render_paste_window` 가 팝업 안에 숨은 컴포넌트를 세워 창 오른쪽 아래 손잡이를 단다
(`paste_window_assets/`) — 끌면 창 폭과 글 칸 높이가 따르고, 보기 상태라 서버로 보내지 않으며 그
브라우저의 `localStorage` 가 기억한다(AGENTS 9장 「Components v2 의 브라우저 전용 보기 상태」). 팝업
밖에서 그리면 아무 일도 하지 않는다. 그림자 DOM 에 가두지 않으므로 서식은 `capa-paste-*` ·
`st-key-capa_paste_*` 이름 아래에만 건다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.table_toolbar import CSV_TEMPLATE_LABEL, render_csv_download

_ASSETS: Final = Path(__file__).with_name("paste_window_assets")

# 글 칸 높이(라벨 포함, px)와 창 크기를 기억하는 칸의 기본 이름 — 같은 꼴 창은 한 크기를 함께 쓴다.
PASTE_TEXT_HEIGHT: Final = 220
PASTE_SIZE_KEY: Final = "paste"
PASTE_SIZE_STORAGE_PREFIX: Final = "capa-paste-size:"
PASTE_OPENING_ALERT = "PA-01"
# 알림 칸 — 표지만 든 칸이라 자리를 먹지 않게 서식이 빼낸다(`paste_window.css`).
_NOTE_SLOT_PREFIX: Final = "capa_paste_note_"
# 잠긴 「적용」 의 까닭 풍선(브라우저가 잠근 동안만 선다).
PASTE_EMPTY_WHY: Final = "표를 붙여넣으면 누를 수 있습니다."
PASTE_CONFIRM_WHY: Final = "확인 체크를 켜면 누를 수 있습니다."
PASTE_HANDLE_LABEL: Final = "창 크기 조절 — 끌거나 방향키로, 두 번 누르면 기본 크기"

# 그림자 DOM 에 가두지 않는다 — 팝업의 포커스 순서가 그 안을 보지 못한다(AGENTS 9장).
_PASTE_WINDOW = st.components.v2.component(
    "capa_paste_window",
    html='<span class="capa-paste-host" hidden></span>',
    css=(_ASSETS / "paste_window.css").read_text(encoding="utf-8"),
    js=(_ASSETS / "paste_window.js").read_text(encoding="utf-8"),
    isolate_styles=False,
)


@dataclass(frozen=True)
class PasteTemplate:
    """작업 줄 오른쪽의 양식 내려받기 하나."""

    data: bytes
    file_name: str
    key: str
    label: str = CSV_TEMPLATE_LABEL


@dataclass(frozen=True)
class PasteSubmit:
    """「적용」 을 누른 회차의 입력 — 글 칸의 글과 확인 체크(체크가 없는 창은 참)."""

    text: str
    confirmed: bool


def paste_note_key(key: str) -> str:
    """그 창의 알림 칸 이름."""
    return f"{key}_paste_note"


def announce_on_open(anchor_key: str, key: str, message: str | None) -> None:
    """창을 연 회차에 꼭 알릴 말을 알림창 · Alarm 에 한 번 낸다 — **입력 칸을 그리기 전에**
    부른다.

    `anchor_key` 는 그 창 입력 칸의 위젯 key 다 — 값이 세션에 없으면 방금 열린 것이다. 글은 앞
    60자에 결과가 들게 쓴다(알림창 짧은 글, 전문은 Alarm). 알릴 말이 없어도 부른다(알림 칸이 늘
    선다).
    """
    note = paste_note_key(key)
    if message and anchor_key not in st.session_state:
        queue_flash(note, message, kind="warning", alert=PASTE_OPENING_ALERT, popup_only=True)
    with st.container(key=f"{_NOTE_SLOT_PREFIX}{key}"):
        render_flash(note)


def refuse_paste(key: str, message: str) -> None:
    """눌린 회차의 거부 · 실패 — 창 안에 그리지 않고 알림창 · Alarm 으로 낸다."""
    note = paste_note_key(key)
    queue_flash(note, message, kind="error", popup_only=True)
    with st.container(key=f"{_NOTE_SLOT_PREFIX}{key}_pressed"):
        render_flash(note)


def tell_paste(key: str, message: str) -> None:
    """눌린 회차의 안내(「바뀐 것이 없습니다」 등) — 창 안에 그리지 않고 알림창 · Alarm 으로
    낸다."""
    note = paste_note_key(key)
    queue_flash(note, message, kind="info", popup_only=True)
    with st.container(key=f"{_NOTE_SLOT_PREFIX}{key}_pressed"):
        render_flash(note)


def render_paste_window(
    key: str,
    *,
    size_key: str = PASTE_SIZE_KEY,
    lock: bool = True,
    resizable: bool = True,
) -> None:
    """이 팝업의 크기 조절 손잡이와 「적용」 잠금을 세운다 — 자리를 먹지 않는다. 알림 칸보다 먼저
    부른다(그 칸을 자리에서 빼는 서식과 팝업이 뜬 뒤 표지를 알림 칸에 넘기는 일이 여기 있다).

    `size_key` 는 그 브라우저가 크기를 기억하는 칸 이름이고, `lock` 이면 「적용」 단추를 글 칸 ·
    확인 체크로 잠근다. `resizable` 을 끄면 손잡이를 달지 않는다(글 칸이 없는 확인 창).
    """
    _PASTE_WINDOW(
        key=f"capa_paste_host_{key}",
        data={
            "resizable": resizable,
            "marker": alerts.MARKER_ATTRIBUTE,
            "sizeKey": size_key,
            "storagePrefix": PASTE_SIZE_STORAGE_PREFIX,
            "handleLabel": PASTE_HANDLE_LABEL,
            "lock": lock,
            "reasons": {"empty": PASTE_EMPTY_WHY, "confirm": PASTE_CONFIRM_WHY},
        },
    )


def paste_text_area(key: str, *, text_key: str, label: str) -> str:
    """글 칸 하나 — 칸의 풍선 · 안내 문장(placeholder)을 두지 않는다(말은 알림창 · Guide). 창 크기를
    따라 높이가 늘어난다."""
    with st.container(key=f"capa_paste_text_{key}"):
        return st.text_area(label, key=text_key, height=PASTE_TEXT_HEIGHT)


@contextmanager
def paste_action_row(template: PasteTemplate | None = None) -> Iterator[None]:
    """작업 줄 — `with` 안의 단추가 왼쪽, 양식 내려받기가 오른쪽(좁아져 접혀도 그 차례다)."""
    with st.container(
        horizontal=True, horizontal_alignment="distribute", vertical_alignment="center", gap="small"
    ):
        with st.container(
            horizontal=True, vertical_alignment="center", gap="small", width="content"
        ):
            yield
        if template is not None:
            render_csv_download(
                data=template.data,
                file_name=template.file_name,
                key=template.key,
                label=template.label,
            )


def render_paste_form(
    key: str,
    *,
    text_key: str,
    text_label: str,
    apply_label: str,
    template: PasteTemplate | None = None,
    opening: str | None = None,
    confirm_key: str | None = None,
    confirm_label: str = "",
    size_key: str = PASTE_SIZE_KEY,
    side_actions: Callable[[], None] | None = None,
) -> PasteSubmit | None:
    """붙여넣기 창 본문 하나. 「적용」 을 누른 회차에만 입력을 돌려준다.

    거부는 부르는 쪽이 `refuse_paste(key, 글)` 로 낸다. `opening` 은 창을 연 회차의 알림 글
    (`announce_on_open`), `confirm_key` · `confirm_label` 은 전체 교체 확인 체크, `side_actions` 는
    「적용」 옆에 더 세울 단추(「닫기」)다.
    """
    render_paste_window(key, size_key=size_key)
    announce_on_open(text_key, key, opening)
    text = paste_text_area(key, text_key=text_key, label=text_label)
    confirmed = True
    if confirm_key is not None:
        with st.container(key=f"capa_paste_confirm_{key}"):
            confirmed = st.checkbox(confirm_label, key=confirm_key)
    with paste_action_row(template):
        pressed = st.button(
            apply_label,
            key=f"capa_paste_apply_{key}",
            icon=":material/content_paste:",
            type="primary",
        )
        if side_actions is not None:
            side_actions()
    return PasteSubmit(text, confirmed) if pressed else None
