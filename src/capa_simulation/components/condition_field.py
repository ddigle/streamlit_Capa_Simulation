# Purpose: 사이드바 통합 조건 패널의 한 줄(이름 줄과 팝업을 여는 값 칸)을 그린다.

"""사이드바 「조회 조건」 패널의 필드 한 줄(2026-10-10 사용자 결정 — 늘 펼친 패널 하나).

한 줄은 둘로 선다.

- **이름 줄**: 왼쪽에 조건 이름, 오른쪽에 상태(배지·적용 기간·보조 글). 버튼 라벨은 배지를 그리지
  못하므로(1.63 `st.button` 은 굵게·기울임·취소선·코드·링크·이미지만 받는다) 상태는 이 줄에 둔다.
- **값 칸**: 지금 값이 적힌 전폭 버튼. 누르면 그 조건을 고치는 팝업이 뜬다. 오른쪽 끝의 `⇕`
  (`unfold_more`) 표식과 칸 모양은 `sidebar_style.py` 가 그린다.

**`with` 안에서 평범한 `st.*` 로만 그린다.** `st.sidebar.*` 는 `with` 문맥을 따르지 않아 글자가 패널
밖으로 샌다. 부르는 쪽이 패널(또는 페이지 칸) 안으로 들어간 뒤에 부른다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

# 필드 한 줄을 감싸는 컨테이너 key 의 접두어. 서식(`sidebar_style.py`)이 이 접두어로 모든 필드를
# 고르고, 저장하지 않은 편집이 있는 필드는 끝에 `PENDING_SUFFIX` 를 단다(왼쪽 주황 띠).
FIELD_KEY_PREFIX = "condition_field_"
NAME_ROW_KEY_PREFIX = "condition_name_"
PENDING_SUFFIX = "_pending"


def condition_name_row(
    name: str,
    *,
    slug: str,
    status: str | None = None,
    on_row: Callable[[DeltaGenerator], None] | None = None,
) -> DeltaGenerator:
    """이름 줄. 이름은 왼쪽, `status` 는 오른쪽 끝이다. `on_row` 는 오른쪽에 칸을 더 세운다.

    조회기간처럼 상태가 페이지 계산 뒤에야 정해지는 줄은 `on_row` 로 빈 칸을 세워 등록해 둔다.
    """
    row = st.container(
        key=f"{NAME_ROW_KEY_PREFIX}{slug}",
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center",
        gap="small",
    )
    row.caption(name, width="content")
    if status:
        row.caption(status, width="content")
    if on_row is not None:
        on_row(row)
    return row


def condition_field(
    name: str,
    value: str,
    *,
    slug: str,
    key: str,
    icon: str,
    status: str | None = None,
    disabled: bool = False,
    pending: bool = False,
    on_click: Callable[..., None] | None = None,
    args: Sequence[object] | None = None,
    on_row: Callable[[DeltaGenerator], None] | None = None,
) -> bool:
    """이름 줄 + 값 칸 한 벌. 값 칸을 누른 회차에 True 를 돌려준다.

    값 칸은 한 줄을 넘지 않는다(`wrap=False`). 넘치면 말줄임하고, 마우스를 올리면 전체 글이
    풍선으로 보인다(`help` 를 주지 않은 한 줄 버튼의 Streamlit 동작). 팝업을 세션 키로 여는
    조건(시나리오·조회기간)은 `on_click` 으로, 버튼이 눌린 회차에만 여는 조건(공정 필터·히트맵)은
    돌려준 값으로 연다.
    """
    box_key = f"{FIELD_KEY_PREFIX}{slug}{PENDING_SUFFIX if pending else ''}"
    with st.container(key=box_key, gap=None):
        condition_name_row(name, slug=slug, status=status, on_row=on_row)
        return st.button(
            value,
            key=key,
            icon=icon,
            type="secondary",
            width="stretch",
            wrap=False,
            disabled=disabled,
            on_click=on_click,
            args=tuple(args) if args is not None else None,
        )
