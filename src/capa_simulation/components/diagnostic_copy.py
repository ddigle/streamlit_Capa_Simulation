# Purpose: Admin 진단 펼침의 글 전체를 한 번에 복사하는 「복사」 단추와 그 글을 짓는 도우미를 둔다.

"""진단 글 복사(설계 규칙 UI-NTF-10 — 확인 보드 AMB-19 (가)).

C-DEP 서버에는 셸도 로그도 없어 Admin 펼침(서버 시작 점검 · 통합인증 점검 · 모듈 상태 · DB 동기화)의
글을 사람이 리뷰로 옮긴다. Alarm 「로그」 의 「복사」 와 같은 꼴로 펼침 맨 위에 단추 하나를 두어
표 · 값 줄을 통째로 글로 가져간다. Alarm 쪽 부품(`alert_center_assets/alert_center.js`)은 그 판의
줄에 묶여 있어 같은 규약을 이 컴포넌트가 따로 든다 —

- 클립보드에 넣으면 「복사했습니다」 를 잠깐 보인다(`navigator.clipboard`).
- 막히면(보안 연결이 아님 · DRM) 글을 고른 채 읽기 전용 칸으로 펴고 Ctrl+C 를 청한다.
  `execCommand('copy')` 는 쓰지 않는다 — 막힌 클립보드에서도 참을 돌려 「복사했습니다」 가 거짓이
  된다.

단추 글이 곧 설명이라 보이는 문장을 더 두지 않는다. 누르는 일은 브라우저 안에서 끝나 서버로 보내지
않는다(회차가 돌지 않는다 — AGENTS 9장 「Components v2 의 브라우저 전용 보기 상태」).

복사 글은 평문이다 — 마크다운 꾸밈을 걷고(`plain_lines`), 표는 탭으로 나눈 줄이다(`table_lines` —
그대로 붙이면 Excel 칸에 들어간다). **복사 글은 밖으로 나가는 글이다** — 부르는 쪽은 리뷰에 옮기지
말아야 할 값을 싣지 않는다(통합인증 점검의 포털 등록값 셋 — `sso_status.status_text`).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final

import pandas as pd
import streamlit as st

from capa_simulation import alerts

COPY_LABEL: Final = "복사"
COPY_TITLE: Final = "이 펼침의 글을 통째로 복사"
COPIED_MESSAGE: Final = "복사했습니다"
MANUAL_MESSAGE: Final = "Ctrl+C 로 복사하세요"
COMPONENT_KEY_PREFIX: Final = "capa_diagnostic_copy_"
# 「복사했습니다」 가 머무는 시간 — Alarm 「로그」 의 복사와 같다.
_COPIED_MS: Final = 1800

_HTML: Final = f"""
<div class="capa-diag-copy">
  <button type="button" class="capa-diag-copy-button" title="{COPY_TITLE}">{COPY_LABEL}</button>
  <span class="capa-diag-copy-state" role="status"></span>
  <textarea class="capa-diag-copy-area" rows="8" readonly hidden aria-label="복사할 글"></textarea>
</div>
"""

# 색은 적지 않는다 — 테마 변수만 쓴다(`st.components.v2.component` 는 등록 때의 CSS 를 그대로 쓴다).
_CSS: Final = """
.capa-diag-copy {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.6rem;
  font-family: var(--st-font);
  font-size: 0.875rem;
  color: var(--st-text-color);
}
.capa-diag-copy-button {
  min-height: 2rem;
  padding: 0.25rem 0.75rem;
  border: 1px solid var(--st-border-color);
  border-radius: var(--st-base-radius);
  background: var(--st-background-color);
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.capa-diag-copy-button:hover {
  border-color: var(--st-primary-color);
  color: var(--st-primary-color);
}
.capa-diag-copy-button:focus-visible {
  outline: 2px solid var(--st-primary-color);
  outline-offset: 1px;
}
.capa-diag-copy-state:empty {
  display: none;
}
.capa-diag-copy-area {
  flex: 1 0 100%;
  box-sizing: border-box;
  padding: 0.35rem 0.45rem;
  border: 1px solid var(--st-border-color);
  border-radius: var(--st-base-radius);
  background: var(--st-secondary-background-color);
  color: inherit;
  font-family: var(--st-code-font, monospace);
  font-size: 0.75rem;
  line-height: 1.4;
  resize: vertical;
}
"""

_JS: Final = (
    f"""
const COPIED_MESSAGE = {COPIED_MESSAGE!r}
const MANUAL_MESSAGE = {MANUAL_MESSAGE!r}
const COPIED_MS = {_COPIED_MS}
"""
    + """
// <diagnostic-copy>
function copyText(win, nav, content, done, manual) {
  let clip = null
  try {
    const usable = win.isSecureContext && nav.clipboard
    clip = usable && typeof nav.clipboard.writeText === 'function' ? nav.clipboard : null
  } catch (error) {
    clip = null
  }
  if (!clip) {
    manual()
    return
  }
  try {
    clip.writeText(content).then(done, manual)
  } catch (error) {
    manual()
  }
}
// </diagnostic-copy>

export default function ({ parentElement, data }) {
  const button = parentElement.querySelector('.capa-diag-copy-button')
  const state = parentElement.querySelector('.capa-diag-copy-state')
  const area = parentElement.querySelector('.capa-diag-copy-area')
  const content = (data && data.text) || ''
  if (!area.hidden) area.value = content
  const done = () => {
    area.hidden = true
    state.textContent = COPIED_MESSAGE
    clearTimeout(state.__capaCopied)
    state.__capaCopied = setTimeout(() => {
      if (state.textContent === COPIED_MESSAGE) state.textContent = ''
    }, COPIED_MS)
  }
  const manual = () => {
    area.value = content
    area.hidden = false
    state.textContent = MANUAL_MESSAGE
    area.focus({ preventScroll: true })
    area.select()
  }
  button.onclick = () => copyText(window, navigator, content, done, manual)
}
"""
)

_COPY = st.components.v2.component("capa_diagnostic_copy", html=_HTML, css=_CSS, js=_JS)


def plain_lines(lines: Iterable[str]) -> list[str]:
    """마크다운 줄 → 평문 줄(아이콘 · 코드 · 굵게 표지와 구두점 막음을 걷는다)."""
    return [alerts.plain_text(line) for line in lines]


def table_lines(frame: pd.DataFrame) -> list[str]:
    """표 → 탭으로 나눈 줄(머리 먼저). 빈 칸은 빈 글이다 — 「None」 글자를 쓰지 않는다."""
    cells = frame.astype(object).where(frame.notna(), "")
    rows = cells.itertuples(index=False, name=None)
    return ["\t".join(str(name) for name in frame.columns)] + [
        "\t".join(str(value) for value in row) for row in rows
    ]


def diagnostic_text(title: str, *blocks: Sequence[str]) -> str:
    """복사할 글 — 제목 줄 뒤에 묶음들을 빈 줄로 나눈다. 빈 묶음은 뺀다."""
    return "\n\n".join([title, *("\n".join(block) for block in blocks if block)])


def render_diagnostic_copy(text: str, *, key: str) -> None:
    """「복사」 단추. 복사가 막힌 환경의 글 칸도 이 자리에 펴진다. `key` 는 펼침마다 다르다."""
    _COPY(key=f"{COMPONENT_KEY_PREFIX}{key}", data={"text": text})
