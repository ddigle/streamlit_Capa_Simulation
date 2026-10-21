# Purpose: 사람이 적은 글을 마크다운이 그리는 자리에 글자 그대로 싣도록 ASCII 구두점을 escape 한다.

"""마크다운 자리에 싣는 사람 글.

`st.expander` 라벨·`st.caption`·`st.markdown` 은 글을 마크다운(GFM·수식·지시문)으로
그린다. 사람이 적은 제목·이름을 그대로 넣으면 「A~B~C」의 물결표는 취소선이 되어 사라지고
「$…$」는 수식, `![x](주소)` 는 보는 사람마다 그 주소를 부르는 이미지, `*이름*` 은 기울임이
된다. CommonMark 는 백슬래시 뒤의 ASCII 구두점을 글자 그대로 두므로 구두점마다 `\\` 를
붙인다. 한글·숫자·공백·`·` 같은 비 ASCII 기호는 그대로다.
"""

from __future__ import annotations

import string

_PUNCTUATION = frozenset(string.punctuation)


def literal_markdown(text: object) -> str:
    """`text` 를 마크다운으로 그려도 적은 글자 그대로 보이게 ASCII 구두점마다 `\\` 를 붙인다."""
    return "".join(f"\\{char}" if char in _PUNCTUATION else char for char in str(text))
