# Purpose: 공용 프로필의 버전·출처·저장시각 캡션 한 줄을 한 규칙으로 만들어 제목 옆에 그린다.

"""공용 프로필 버전 캡션.

`GlobalAdvanceLoad`·`GlobalPastData`·`GlobalKeyProcess` 처럼 시나리오와 분리된 공용
프로필은 모두 `version`·`source`·`updated_at` 세 필드를 갖고, 저장 화면은 그 셋을 같은
모양의 한 줄로 적는다. 그 템플릿이 여덟 자리에 따로 적혀 있어 한 곳만 고치면 화면마다
문구가 갈렸다 — 규칙을 여기 하나로 둔다.

**출처(`source`)는 사람 글이다.** 판정 기준·선행 B/O·확보율 보정·과거 구간·
Proc Rename 의 「변경 메모」가 그대로 출처가 되고, 캡션은 늘 `st.caption`(마크다운
자리)으로 그린다. 그래서 출처만 `literal_markdown` 으로 막아 잇는다 — 날로 이으면
「26.07~12 확정 / 27.01~06 잠정」 의 물결표가 지움선이 되고 `*검토*`·`$1$`·백틱 글이
기울임·수식·코드로 그려졌다(2026-10-27 E2E). 돌려준 글은 이미 막은 글이라 부르는 쪽이
`literal_markdown` 으로 다시 감싸지 않는다 — 다시 막으면 `\\` 가 글자로 보인다
(`tests/test_markdown_sink_guard.py` 의 `ESCAPED_BUILDERS`). `empty`·`detail` 은
앱이 지은 글이라 그대로 잇는다.

`empty` 문구만 프로필마다 다르다. 「아직 넣은 선행 B/O 가 없습니다」처럼 무엇이 비었는지
말해야 하고, 값을 끼워 만드는 자리도 있어 호출부가 완성해 넘긴다.

모델을 import 하지 않는다. `persistence.models` 를 붙잡으면 화면 조각 하나가 저장 계층을
끌고 들어오고, 프로필이 늘 때마다 이 모듈도 같이 고쳐야 한다. 구조적 타입(Protocol)으로
세 필드만 요구한다.

**제목 옆 버전 줄**(`render_profile_heading`). 구획 제목 아래 따로 서던 버전 캡션을 제목과 한 줄에
둔다(2026-11-08 사용자 그림 메모 g18 「공용 버전 … 타임스탬프 줄을 각 타이틀 옆으로」). 줄은 가로 칸
(`st.container(horizontal=True)` — 기본 줄 바꿈)이라 칸이 좁으면 버전 줄이 제목 아래로 내려간다. 두
글은 글자 밑줄에 맞춘다. 버전 줄 글은 `profile_version_caption` 그대로라 출처를 막는 규칙도 같다.

```python
render_profile_heading(
    "#### :material/rule: 확보율 판정 기준",
    threshold_profile,
    key="home_threshold",  # 화면 안에서 줄마다 다른 이름
    empty="아직 저장하지 않아 …",
    detail=_threshold_detail(threshold_profile),
    help=THRESHOLD_HELP,  # 제목 풍선(있으면)
)
```
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Final, Protocol

import streamlit as st

from capa_simulation.components.literal_markdown import literal_markdown

VERSION_CAPTION_PREFIX = "공용 버전 "
CAPTION_SEPARATOR = " · "
# 제목과 버전 줄 사이 — 같은 줄의 짝이라 본문 칸 사이(medium)보다 좁다.
HEADING_GAP: Final = "small"
# 제목 · 버전 줄 한 줄 칸의 key 접두어와, 그 칸들의 두 글을 글자 밑줄에 맞추는 규칙.
HEADING_KEY_PREFIX: Final = "profile_heading_"
HEADING_BASELINE_STYLE: Final = (
    f'<style>[class*="st-key-{HEADING_KEY_PREFIX}"]{{align-items:baseline}}</style>'
)
# 앞에 `\` 가 없는 `<` — `literal_markdown` 이 막은 `\<` 는 이미 글자다.
_RAW_TAG_START: Final = re.compile(r"(?<!\\)<")


class HasProfileVersion(Protocol):
    """버전 캡션을 만들 수 있는 공용 프로필의 최소 모양.

    **읽기 전용 `@property` 로 선언한다.** 평범한 속성 주석은 불변(invariant)이라
    `GlobalDisplayOrder.updated_at: datetime` 이 `datetime | None` 에 맞지 않아 mypy
    strict 가 거절한다. 읽기 전용이면 공변이라 둘 다 받는다.
    """

    @property
    def version(self) -> int: ...

    @property
    def source(self) -> str: ...

    @property
    def updated_at(self) -> datetime | None: ...


def profile_version_caption(
    profile: HasProfileVersion,
    *,
    empty: str,
    detail: str | None = None,
) -> str:
    """공용 프로필 한 줄 캡션.

    `version == 0` 은 **한 번도 저장하지 않은 상태**라 버전 대신 `empty` 문구를 적는다.
    저장된 뒤에는 `v{version} · [detail ·] [source ·] [저장시각]` 순으로 잇는다. `detail` 은
    출처 앞(「3개 공정」)에 붙는다. 맨 뒤 꼬리(공지의 「공지 중 · 내림」)는 두지 않는다 — 바로 아래
    칸이 지금 값을 보인다(2026-11-09 사용자 검수 g18 「중복되는 문구(공지)」). 출처는 사람이 적은
    메모일 수 있어 `literal_markdown` 으로 막는다(마크다운 자리에서 적은 글자 그대로 보인다).
    출처가 비면(저장자·변경 메모를 모두 비운 저장) 그 자리를 건너뛴다 — 빈 토막을 이으면 구분자가
    `v14 · · 2026-…` 처럼 겹친다.
    """
    if profile.version == 0:
        return f"{VERSION_CAPTION_PREFIX}없음{CAPTION_SEPARATOR}{empty}"
    parts = [f"v{profile.version}"]
    if detail is not None:
        parts.append(detail)
    if profile.source.strip():
        parts.append(literal_markdown(profile.source))
    if profile.updated_at is not None:
        parts.append(format(profile.updated_at, "%Y-%m-%d %H:%M"))
    return VERSION_CAPTION_PREFIX + CAPTION_SEPARATOR.join(parts)


def render_profile_heading(
    title: str,
    profile: HasProfileVersion,
    *,
    key: str,
    empty: str,
    detail: str | None = None,
    help: str | None = None,
    mark: tuple[str, str] | None = None,
    style: str | None = None,
) -> None:
    """구획 제목과 그 공용 버전 줄(`profile_version_caption`)을 한 줄에 그린다.

    `title` 은 앱이 지은 마크다운 제목(「#### :material/…: 이름」)이고 `help` 는 그 제목의 풍선이다.
    `key` 는 화면 안에서 줄마다 다른 이름이다(줄 칸 key 는 `HEADING_KEY_PREFIX` + `key`). 버전 줄은
    제목 오른쪽에 붙고, 칸이 좁으면 제목 아래로 내려간다. `empty`·`detail` 은
    `profile_version_caption` 과 같다. `mark` 는 (표지 글, 풍선) — 그 구획 표의 숨은 데이터 안내
    표지(설계 규칙 UI-TXT-04 — 칸 머리 표지 + 풍선)를 버전 줄 뒤 같은 줄에 둔다. 따로 줄을 세우지
    않는다(2026-11-09 사용자 규칙 「상단 여백 · 문구 최소화」). 앱이 지은 글이라 그대로 싣는다.

    **두 글은 글자 밑줄(baseline)에 맞춘다** — 제목(h4)은 위아래 여백이 달라 가운데 맞춤이면 작은
    버전 줄이 제목 글자보다 3 ~ 8px 떠 보인다(샘플 관측 — 팝업 안 제목 · 본문 제목). 줄 칸에
    `align-items: baseline` 을 거는 규칙은 버전 줄 글과 한 마크다운에 싣는다 — 스타일만 든 `st.html`
    은 이벤트 칸으로 가 팝업 본문 · 프래그먼트의 이벤트 칸 자리 수를 바꾸고, 따로 세운 칸은 줄에
    간격을 하나 더 만든다. 그래서 버전 줄은 HTML 을 받는 캡션이다 — 사람 글(출처)은
    `literal_markdown` 이 `<` 까지 막았고, 앱 글의 맨 `<` 는 글자 그대로 보이게
    바꾼다(`_without_raw_html`). 본문 칸에만 쓰고 이벤트 칸에는 아무것도 쓰지 않아 팝업 본문 ·
    프래그먼트 어디서나 부를 수 있다.

    `style` 은 그 구획의 다른 칸에 거는 앱이 지은 서식 규칙(`<style>` 없이 — 예: 저장 줄 오른쪽 끝을
    표 도구 막대 자리로 비우는 `table_toolbar.toolbar_room_css`)이다. 같은 까닭으로 버전 줄 캡션에
    함께 싣는다 — 팝업 본문(HOME 설정)은 스타일만 든 `st.html` 을 쓸 수 없다.
    """
    caption = profile_version_caption(profile, empty=empty, detail=detail)
    extra = f"<style>{style}</style>" if style else ""
    with st.container(
        horizontal=True,
        vertical_alignment="center",
        gap=HEADING_GAP,
        key=f"{HEADING_KEY_PREFIX}{key}",
    ):
        st.markdown(title, help=help, width="content")
        st.caption(
            _without_raw_html(caption) + HEADING_BASELINE_STYLE + extra,
            unsafe_allow_html=True,
            width="content",
        )
        if mark is not None:
            st.caption(mark[0], help=mark[1], width="content")


def _without_raw_html(text: str) -> str:
    """막히지 않은 `<` 를 글자 참조로 — HTML 을 받는 마크다운 자리에서 태그로 읽히지 않게 한다."""
    return _RAW_TAG_START.sub("&lt;", text)
