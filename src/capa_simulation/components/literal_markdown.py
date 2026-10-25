# Purpose: 사람 글·이름·거부 문구가 마크다운 자리에서 글자 그대로 보이게 구두점이나 물결표를 막는다.

"""마크다운 자리에 싣는 사람 글.

`st.expander` 라벨·`st.caption`·`st.markdown` 은 글을 마크다운(GFM·수식·지시문)으로
그린다. 사람이 적은 제목·이름을 그대로 넣으면 「A~B~C」의 물결표는 취소선이 되어 사라지고
「$…$」는 수식, `![x](주소)` 는 보는 사람마다 그 주소를 부르는 이미지, `*이름*` 은 기울임이
된다. CommonMark 는 백슬래시 뒤의 ASCII 구두점을 글자 그대로 두므로 구두점마다 `\\` 를
붙인다. 한글·숫자·공백·`·` 같은 비 ASCII 기호는 그대로다.

앱이 지은 거부·안내 문구(`st.error`·`st.warning`·`st.info`·`st.success` 인자)는 일부러 넣은
굵게·코드가 있을 수 있어 구두점 전부를 막지 않고 물결표만 막는다(`markdown_safe_tildes`) —
「동은 C1~C5, 층은 1F~6F」 처럼 물결표가 둘인 문구가 취소선이 되지 않게.

이름이 마크다운 자리로 들어오는 길은 셋이다 — 문구에 바로 끼우는 이름, 저장소·서비스 예외 글
(`str(exc)`), 문구를 짓는 함수. 막는 길도 하나씩 둔다. 문구에 끼우는 이름은 `quoted`(「이름」),
예외 글은 `page_bootstrap.bootstrap_error_message`(DuckDB 가 아닌 예외는 `markdown_safe_tildes`),
문구를 짓는 함수는 이름을 끼울 때 `quoted`·`literal_markdown` 을 쓴다. 그리는 자리마다 고르면 한
자리를 고칠 때 옆 자리가 남는다(2026-10-26 E2E 1~3회차 — 「E2E~가정~A」 지움선). 지키는 시험은
`tests/test_markdown_sink_guard.py`(AST)와 `tests/test_tilde_names_pages.py`(화면)다.
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


def quoted(name: object, *, empty: str = "「」") -> str:
    """`「name」` — 문구에 끼우는 이름을 낫표로 감싸고 `literal_markdown` 으로 막는다.

    이름이 없거나(`None`) 빈 글이면 `empty` 를 돌려준다(「이 설비 시나리오」 처럼 이름 대신 쓸
    말). 조사는 감싼 글로 골라도 이름으로 고른 것과 같다 — `korean_particle` 이 끝의 `」`·`\\` 를
    건너뛴다.
    """
    text = "" if name is None else str(name)
    if not text:
        return empty
    return f"「{literal_markdown(text)}」"
