# Purpose: VOC 의 아직 남지 않은 글을 지킨다 — 새 글 초안을 브라우저 탭에 두었다 되살리고, 적어 둔
# 답변을 「잃을 것」 판정에 내준다.

"""VOC 새 글 초안 보관 · 적어 둔 답변의 「잃을 것」 판정.

새 글 폼(`st.form`)의 제목·내용은 「글 올리기」 를 누르기 전에는 서버가 모른다. 그래서 쓰다가 다른
화면·화면 탭으로 옮기거나 테마를 바꾸면(테마 전환은 문서를 새로 읽어 세션이 새로 선다) 적은 글이
말없이 사라졌다 — 4000자까지 받는 칸이다(2026-10-26 E2E). 서버 세션으로는 테마 새로고침을
넘지 못하므로 **브라우저 탭**(`sessionStorage`)에 둔다. 탭을 닫으면 사라진다 — 서버·DB·다른 사람에게
가지 않는다.

- **적기** — 폼의 두 칸(`st-key-voc_post_title`·`st-key-voc_post_body`)에 글을 칠 때마다 탭 칸
  (`DRAFT_STORAGE_KEY`)에 (세션 표지, 폼 세대, 제목, 내용)을 적는다. 듣개는 문서에 하나다 — 회차마다
  옛 것을 떼고 새로 단다(그 회차의 세대를 쓴다).
- **되살리기** — 두 칸이 모두 비어 있고 탭 칸에 글이 있으면 그 글을 칸에 넣는다(React 가 받는 꼴 —
  값 설정 뒤 `input` 사건). 폼 안이라 서버에는 「글 올리기」 때 간다. 되살렸으면 같은 문서의 알림
  칸(`window.__capaAlerts.raise` — 칸이 아직 서지 않았으면 `window.__capaAlertQueue`)에 사건 알림
  `VO-02` 를 낸다 — 폼 아래에 제 꼴의 줄을 두지 않는다(설계 규칙 UI-NTF-01 · 03, 화면 탭 줄 JS 와
  같은 길).
- **버리기** — 같은 세션에서 폼 세대가 올랐으면(글을 올렸다 — `voc._submit_post`) 탭 칸을 비운다.
  올린 뒤 새 폼이 선 사이 옛 값으로 한 번 더 돈 회차가 그 초안을 빈 새 폼에 되살릴 수 있어(브라우저
  실측 — 서버는 비웠는데 칸에 올린 글이 남았다), 두 칸이 올린 초안 그대로면 칸도 비운다.
  세션 표지(`_SESSION_TOKEN_KEY`)는 세션마다 새로 뽑아, 새로고침으로 선 세션(세대 0)이 옛 세대의
  글을 「올린 글」 로 잘못 보지 않게 한다.

판정은 DOM 을 모르는 순수 구획(`// <voc-draft>`)이라 node 시험이 떼어 돌린다
(`tests/test_voc_draft_keeper.py`). **비공식 경로다** — Streamlit 의 `st-key-` 칸 이름과 React 입력
칸의 값 설정 꼴에 기댄다. 판올림에서 바뀌면 되살리기만 멈추고 폼은 그대로다.

**적어 둔 답변**(`KEPT_REPLY_KEY`)은 남지 못한 답변을 머리 알림 칸에 「닫기」 까지 두는 서버 세션
칸이다(`app_pages/voc.py`). 다른 화면에 갔다 와도 남지만 새로고침 · 테마 전환 · 브라우저 탭 닫기에는
세션과 함께 사라진다. 그래서 「잃을 것」 에 든다 — 화면 탭 「VOC」 주황 점
(`page_tabs.page_unsaved_marks`)과 머리 변경 칩 「저장 안 함」 한 줄
(`change_summary.session_changes`)이 같은 판정(`kept_reply_count`)을 읽고, 그 점이 테마 단추 ·
떠나기 확인 창의 표지가 된다. 탭 점 · 변경 칩은 페이지 앞에서 세션만 읽으므로 화면 파일이 아니라
여기에 키를 둔다.
"""

from __future__ import annotations

import secrets
from typing import Final

import streamlit as st

from capa_simulation import alerts

# 브라우저 탭(`sessionStorage`)의 초안 칸 이름.
DRAFT_STORAGE_KEY: Final = "capa-voc-post-draft"
# 적어 둔 답변 — 거절된 차례대로 든 답변 글 튜플(`app_pages/voc.py` 가 적고 「닫기」 가 걷는다).
KEPT_REPLY_KEY: Final = "voc_kept_reply"
# VOC 화면 파일 이름(탭 점 · 변경 칩이 그 화면을 찾는 값 — `navigation.ADMIN_BOX_PAGES`).
VOC_PAGE_FILE: Final = "voc.py"
# 이 세션의 표지(세션마다 새로 뽑는다).
_SESSION_TOKEN_KEY: Final = "voc_draft_session_token"
# 되살림 알림(`VO-02`)의 짧은 글과 전문 — 보관 범위(이 탭 · 올리기 전에는 탭을 닫으면 사라짐)는
# 전문(Alarm 패널 · 로그)과 Guide 가 말한다.
RESTORED_ALERT_CODE: Final = "VO-02"
RESTORED_SHORT: Final = "VOC 새 글 — 쓰다 만 제목·내용을 되살렸습니다"
RESTORED_NOTE: Final = (
    "이 브라우저 탭에 임시 보관한 제목·내용을 되살렸습니다 — 올리기 전에는 탭을 닫으면 사라집니다."
)

# 그릴 것이 없는 컴포넌트다 — 폼 칸은 문서에 있고 알림은 알림 칸이 띄운다.
_HTML = "<span hidden></span>"

_JS = """
export default function (component) {
  const { data, parentElement } = component
  const doc = parentElement.ownerDocument || document
  const win = doc.defaultView || window

// <voc-draft>
// 탭 칸의 초안(`stored`)으로 이 회차에 할 일. 'forget' — 같은 세션에서 폼 세대가 올랐다(글을
// 올렸다). 그때 두 칸이 올린 초안 그대로면 'forget-clear' — 올린 뒤 새 폼이 선 사이 옛 값으로 한 번
// 더 돈 회차가 그 초안을 빈 새 폼에 되살렸다(브라우저 실측) — 칸도 비운다. 'restore' — 두 칸이 모두
// 비었고 초안에 글이 있다. 그 밖은 'none'.
function draftAction(stored, session, generation, current) {
  if (!stored || typeof stored !== 'object') return 'none'
  const title = typeof stored.title === 'string' ? stored.title : ''
  const body = typeof stored.body === 'string' ? stored.body : ''
  if (!title && !body) return 'none'
  if (stored.session === session && Number(generation) > Number(stored.generation)) {
    return current.title === title && current.body === body ? 'forget-clear' : 'forget'
  }
  if (current.title || current.body) return 'none'
  return 'restore'
}
// </voc-draft>

  function read() {
    try {
      return JSON.parse(win.sessionStorage.getItem(data.storageKey) || 'null')
    } catch (error) {
      return null
    }
  }
  function write(value) {
    try {
      if (value === null) win.sessionStorage.removeItem(data.storageKey)
      else win.sessionStorage.setItem(data.storageKey, JSON.stringify(value))
    } catch (error) { /* 탭 칸을 못 쓰면 보관하지 않는다 */ }
  }
  function fields() {
    return {
      title: doc.querySelector(data.titleSelector),
      body: doc.querySelector(data.bodySelector),
    }
  }
  // React 가 받는 값 설정 — 원래 setter 로 넣고 `input` 사건을 낸다(폼 안이라 서버에는 올릴 때
  // 간다).
  function setValue(element, value) {
    const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), 'value')
    if (descriptor && descriptor.set) descriptor.set.call(element, value)
    else element.value = value
    element.dispatchEvent(new Event('input', { bubbles: true }))
  }
  // 같은 문서의 알림 칸에 낸다. 칸이 아직 서지 않았으면 담아 두고 칸이 설 때 꺼낸다.
  function raiseAlert(note) {
    if (!note) return
    const center = win.__capaAlerts
    if (center && typeof center.raise === 'function') center.raise(note)
    else (win.__capaAlertQueue = win.__capaAlertQueue || []).push(note)
  }
  function snapshot(found) {
    return {
      session: data.session,
      generation: data.generation,
      title: found.title ? found.title.value : '',
      body: found.body ? found.body.value : '',
    }
  }

  const previous = win.__capaVocDraftInput
  if (previous) doc.removeEventListener('input', previous, true)
  const onInput = (event) => {
    const found = fields()
    if (event.target !== found.title && event.target !== found.body) return
    write(snapshot(found))
  }
  win.__capaVocDraftInput = onInput
  doc.addEventListener('input', onInput, true)

  let frames = 0
  let frame = 0
  const settle = () => {
    const found = fields()
    if (!found.title || !found.body) {
      frames += 1
      if (frames < 60) frame = win.requestAnimationFrame(settle)
      return
    }
    const stored = read()
    const action = draftAction(stored, data.session, data.generation, {
      title: found.title.value,
      body: found.body.value,
    })
    if (action === 'forget' || action === 'forget-clear') {
      write(null)
      if (action === 'forget-clear') {
        setValue(found.title, '')
        setValue(found.body, '')
      }
    } else if (action === 'restore') {
      setValue(found.title, stored.title || '')
      setValue(found.body, stored.body || '')
      write(snapshot(found))
      raiseAlert(data.alert)
    }
  }
  settle()

  return () => {
    if (frame) win.cancelAnimationFrame(frame)
    if (win.__capaVocDraftInput === onInput) {
      doc.removeEventListener('input', onInput, true)
      delete win.__capaVocDraftInput
    }
  }
}
"""

# 그림자 DOM 으로 가두지 않는다 — 폼 칸이 문서에 있다.
_DRAFT_KEEPER = st.components.v2.component(
    "capa_voc_draft_keeper", html=_HTML, js=_JS, isolate_styles=False
)


def kept_reply_count() -> int:
    """적어 둔 답변의 수 — 세션만 읽는다(화면 탭 점 · 머리 변경 칩이 페이지 앞에서 부른다)."""
    kept = st.session_state.get(KEPT_REPLY_KEY)
    return len(kept) if isinstance(kept, tuple) else 0


def _session_token() -> str:
    token = st.session_state.get(_SESSION_TOKEN_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_hex(8)
        st.session_state[_SESSION_TOKEN_KEY] = token
    return token


def restored_alert() -> dict[str, str]:
    """되살림 사건 알림(`VO-02`)의 표지 — JS 가 되살린 회차에만 알림 칸에 낸다(id 는 알림 칸이
    붙인다). 화면 이름 · 주소는 이 회차의 화면이다(`alerts.current_page`)."""
    page, href = alerts.current_page()
    return {
        "code": RESTORED_ALERT_CODE,
        "level": alerts.spec(RESTORED_ALERT_CODE).level,
        "short": alerts.short_text(RESTORED_SHORT),
        "full": RESTORED_NOTE,
        "page": page,
        "href": href,
    }


def render_voc_draft_keeper(*, title_key: str, body_key: str, generation: int) -> None:
    """새 글 폼의 초안 보관 — 폼 **바로 뒤**(폼과 간격 없는 한 칸)에서 부른다. `title_key`·
    `body_key` 는 두 칸의 위젯 key, `generation` 은 지금 폼
    세대(`voc.POST_FORM_GENERATION_KEY`)다."""
    _DRAFT_KEEPER(
        key="voc_draft_keeper",
        data={
            "storageKey": DRAFT_STORAGE_KEY,
            "session": _session_token(),
            "generation": int(generation),
            "titleSelector": f".st-key-{title_key} input",
            "bodySelector": f".st-key-{body_key} textarea",
            "alert": restored_alert(),
        },
        width="stretch",
    )
