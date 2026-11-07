# Purpose: 잠글 수 있는 단추마다 까닭 풍선(help=)이 있는지 소스를 훑어 허용 목록과 맞댄다.

"""잠긴 단추 까닭 그물(설계 규칙 UI-INP-07 — `docs/design_rules.md`).

못 하는 조작은 잠그고 까닭 풍선을 단다 — 곁 글로 까닭을 적지 않는다. 이 그물은 화면 코드에서
`disabled=` 를 받는 단추(`st.button` · `st.download_button` · `st.form_submit_button` ·
`st.popover` · `st.link_button`)가 `help=` 도 받는지 (파일, 맨 바깥 함수) 마다 세어 허용 목록과
**정확히** 맞댄다.
`help=None if 켜짐 else 까닭` 꼴은 풍선이 있는 것으로 센다 — 글이 까닭인지는 화면 시험과 판단 질문이
본다. 브라우저 컴포넌트 안 단추(설비 마스터 표 · Space 편집기)는 자산 시험이 본다.

- 새 자리가 생기면 실패한다 — 까닭을 `help=` 로 달거나, 달 수 없으면 까닭과 함께 목록에 둔다.
- 자리가 줄면 실패한다 — 목록도 줄인다.
"""

from __future__ import annotations

import ast
from collections import Counter

from source_sites import method, screen_calls, screen_files

BUTTONS = frozenset({"button", "download_button", "form_submit_button", "popover", "link_button"})
# 답이 바로 아래 있는 추천 질문 — 누른 자리가 곧 까닭이다.
ANSWERED = "이미 답한 질문 — 눌린 답이 바로 아래 선다"
# 잠금을 부르는 쪽이 정하는 공용 부품 — 부품에 까닭 인자가 아직 없다.
PART = "공용 부품 — 잠그는 쪽이 까닭을 넘길 인자가 없다(미정리)"
ALLOWED: dict[tuple[str, str], tuple[int, str]] = {
    ("app_pages/capa_chatbot.py", ""): (1, ANSWERED),
    ("src/capa_simulation/components/column_filter.py", "render_column_filter_controls"): (1, PART),
}


def _unset(value: ast.expr | None) -> bool:
    return value is None or (isinstance(value, ast.Constant) and value.value in (None, False))


def locked_without_help() -> Counter[tuple[str, str]]:
    """(파일, 맨 바깥 함수) 마다 `disabled=` 를 받고 `help=` 가 없는 단추 수."""
    found: Counter[tuple[str, str]] = Counter()
    for relative, outer, _path, _scope, call in screen_calls(screen_files()):
        if method(call) not in BUTTONS:
            continue
        keywords = {item.arg: item.value for item in call.keywords}
        if not _unset(keywords.get("disabled")) and _unset(keywords.get("help")):
            found[(relative, outer)] += 1
    return found


def test_a_button_that_can_lock_says_why_in_a_balloon() -> None:
    allowed = {site: count for site, (count, _) in ALLOWED.items()}
    assert dict(locked_without_help()) == allowed, (
        "잠글 수 있는 단추에 까닭 풍선이 없습니다 — `help=` 로 달거나"
        "(`help=None if 켜짐 else 까닭`), 달 수 없으면 tests/test_locked_button_help.py ALLOWED 에"
        " 까닭과 함께 두세요."
    )
