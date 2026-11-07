# Purpose: 팝오버를 Esc 로 닫아도 친 값을 잃지 않게 닫기 전에 글 칸을 확정하는 스크립트를 만든다.

"""팝오버 안 글 칸의 Esc 확정.

Streamlit 글 칸은 포커스가 빠지거나 Enter 를 누를 때 값을 서버로 보낸다. 바깥을 눌러 팝오버를 닫으면
포커스가 먼저 빠져 값이 가지만, Esc 로 닫으면 포커스가 빠지기 전에 칸이 없어져 친 글이 서버에 가지
않는다. 칸 값을 팝오버 **바깥** 단추가 읽는 자리(Space 저장 상자의 변경 메모 · 저장자 — 「배치
저장」 은 팝오버 밖이다)에서는 메모가 아무 알림 없이 빠진 채 저장된다. 그런 칸을 `ESC_COMMIT_PREFIX`
로 시작하는 key 의 칸에 넣으면 Esc 를 Streamlit 보다 먼저 받아 칸의 포커스를 빼 값을 보낸다.

팝오버 안 단추로 값을 제출하는 자리(이름 바꾸기 · 확인 체크)는 Esc 가 취소이므로 넣지 않는다.

Streamlit 팝오버는 열릴 때 `document` 의 capture 단계에서 Esc 를 듣는다. 그보다 앞서려고 부모 창의
capture 단계에서 듣는다 — 등록 차례와 상관없이 창이 문서보다 먼저다.

테마 버튼 iframe 에 다른 툴바 스크립트와 함께 싣는다(`theme_toggle.render_theme_toggle` 의
`extra_scripts`) — iframe 내용은 회차마다 같아야 하므로 고정 문자열이고, iframe 이 다시 만들어지면
옛 듣개를 뗀다.

**비공식 경로다.** Streamlit 의 `st-key-` 칸과 글 칸이 포커스 빠짐에 값을 보내는 동작에 기댄다.
판올림에서 바뀌면 Esc 로 닫은 값이 전처럼 빠질 뿐 화면은 그대로다.
"""

from __future__ import annotations

# 이 글자로 시작하는 key 의 칸 안 글 칸이 Esc 확정 대상이다.
ESC_COMMIT_PREFIX = "esc_commit_"
# 부모 창에 남기는 지금 듣개의 이름. iframe 이 다시 만들어지면 이것으로 옛 듣개를 뗀다.
HANDLER_NAME = "__capaPopoverFieldCommit"

_SCRIPT = """
(function () {
  var parentWindow = window.parent;
  if (!parentWindow || parentWindow === window) return;
  var BOX = '[class*="st-key-%(prefix)s"]';
  var FIELDS = BOX + " input, " + BOX + " textarea";

  function onKey(event) {
    if (event.key !== "Escape") return;
    var target = event.target;
    if (target && target.matches && target.matches(FIELDS)) target.blur();
  }

  var previous = parentWindow.%(handler)s;
  if (previous) parentWindow.removeEventListener("keydown", previous, true);
  parentWindow.%(handler)s = onKey;
  parentWindow.addEventListener("keydown", onKey, true);
})();
"""


def popover_field_commit_script() -> str:
    """팝오버 글 칸을 Esc 에 확정하는 스크립트(고정 문자열 — `render_theme_toggle` 의
    `extra_scripts`)."""
    return _SCRIPT % {"prefix": ESC_COMMIT_PREFIX, "handler": HANDLER_NAME}
