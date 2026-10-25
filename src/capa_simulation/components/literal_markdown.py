# Purpose: 사람 글·거부 문구가 마크다운 자리에서 글자 그대로 보이게 구두점(또는 물결표만)을 막는다.

"""마크다운 자리에 싣는 사람 글.

`st.expander` 라벨·`st.caption`·`st.markdown` 은 글을 마크다운(GFM·수식·지시문)으로
그린다. 사람이 적은 제목·이름을 그대로 넣으면 「A~B~C」의 물결표는 취소선이 되어 사라지고
「$…$」는 수식, `![x](주소)` 는 보는 사람마다 그 주소를 부르는 이미지, `*이름*` 은 기울임이
된다. CommonMark 는 백슬래시 뒤의 ASCII 구두점을 글자 그대로 두므로 구두점마다 `\\` 를
붙인다. 한글·숫자·공백·`·` 같은 비 ASCII 기호는 그대로다.

앱이 지은 거부·안내 문구(`st.error`·`st.warning`·`st.info`·`st.success` 인자)는 일부러 넣은
굵게·코드가 있을 수 있어 구두점 전부를 막지 않고 물결표만 막는다(`markdown_safe_tildes`) —
「동은 C1~C5, 층은 1F~6F」 처럼 물결표가 둘인 문구가 취소선이 되지 않게.
"""

from __future__ import annotations

import re
import string

_PUNCTUATION = frozenset(string.punctuation)


def literal_markdown(text: object) -> str:
    """`text` 를 마크다운으로 그려도 적은 글자 그대로 보이게 ASCII 구두점마다 `\\` 를 붙인다."""
    return "".join(f"\\{char}" if char in _PUNCTUATION else char for char in str(text))


_BARE_TILDE = re.compile(r"(?<!\\)~")


def markdown_safe_tildes(text: object) -> str:
    """`text` 의 물결표만 `\\~` 로 막는다 — 마크다운 취소선을 막고 다른 꾸밈(굵게·코드)은 살린다.

    이미 막힌 물결표(`\\~`, 예: `literal_markdown` 을 지난 이름)는 다시 막지 않는다.
    """
    return _BARE_TILDE.sub(r"\\~", str(text))
