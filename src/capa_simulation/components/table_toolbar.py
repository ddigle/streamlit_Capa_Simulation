# Purpose: 표 위 제목·부가 설명 줄, CSV 내보내기 버튼과 표 도구 막대 앞 띄움을 한 곳에서 그린다.

"""One heading row and one CSV download button for every table.

내보내기 버튼이 13곳에 흩어져 있었고 표기가 두 갈래로 갈라져 있었다. 라벨 안에
`:material/download:` 를 적은 것과 `icon=` 인자를 쓴 것인데, 아이콘과 글자 사이 간격이
달라 화면마다 버튼 모양이 미묘하게 어긋났다. `mime` 도 `text/csv` 와
`text/csv;charset=utf-8` 이 섞여 있었다. 내보내는 바이트는 전부 `utf-8-sig` 라 charset 을
밝히는 쪽이 맞다. 일부는 `on_click="ignore"` 가 빠져 내려받을 때마다 페이지 전체가 다시
계산됐다.

표 제목 · 단위 설명 · 내보내기 버튼을 한 줄에 놓는 구성도 다섯 화면이 같은 코드를
복제하고 있었다. `table_heading_row` 로 합치고, 그 줄에 위젯을 더 놓아야 하는 화면은
`with` 블록 안에서 이어 붙인다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st

# 내보내는 바이트는 전부 BOM 이 붙은 UTF-8 이다. Excel 이 한글을 깨뜨리지 않게 하려는
# 것이고, 그렇다면 charset 도 함께 밝혀야 브라우저가 같은 판단을 한다.
CSV_MIME = "text/csv;charset=utf-8"

DOWNLOAD_ICON = ":material/download:"

CSV_DOWNLOAD_LABEL = "CSV 다운로드"

CSV_TEMPLATE_LABEL = "CSV 양식 다운로드"

# 표 앞 띄움(px, `st.space`) — 표에 마우스를 올리면 오른쪽 위 도구 막대(열 보기·내려받기·찾기·
# 전체 화면)가 표 머리 위 37px 까지 솟는다. 표 바로 위 줄에 누를 것(입력·단추·팝오버·토글·날짜
# 칸)이 있으면 그 막대가 그 줄에 닿지 않을 만큼 표 앞에 띄운다(AGENTS 9장 「표 도구 막대」). 이
# 띄움의 숫자는 여기 하나다 — 다른 모듈의 이름은 이 값을 가리키는 별칭이다
# (`tests/test_table_toolbar.py`).
TABLE_TOOLBAR_CLEARANCE = 24


def render_csv_download(
    *,
    data: bytes,
    file_name: str,
    key: str | None = None,
    label: str = CSV_DOWNLOAD_LABEL,
) -> None:
    """CSV 내보내기 버튼 하나를 그린다.

    `on_click="ignore"` 를 항상 붙인다. 내려받기는 화면 상태를 바꾸지 않으므로 다시
    계산할 이유가 없고, 다시 계산하면 붙여넣던 텍스트나 펼쳐 둔 영역이 초기화된다.
    """
    st.download_button(
        label,
        data=data,
        file_name=file_name,
        mime=CSV_MIME,
        icon=DOWNLOAD_ICON,
        key=key,
        on_click="ignore",
        width="content",
    )


def toolbar_clearance() -> None:
    """표 바로 앞에 도구 막대 띄움(`TABLE_TOOLBAR_CLEARANCE`)을 둔다.

    위 줄에 누를 것이 있는 표는 `st.dataframe`·`st.data_editor` 바로 앞에 부른다 — 막대가 위 줄의
    단추·입력 칸 지우기(✕)를 덮어 표에서 그리로 옮긴 누름을 가로채지 않게 한다.
    """
    st.space(TABLE_TOOLBAR_CLEARANCE)


@contextmanager
def table_heading_row(
    title: str,
    *,
    caption: str | None = None,
    csv: bytes,
    file_name: str,
    key: str,
) -> Iterator[None]:
    """표 제목 · 부가 설명 · CSV 내보내기를 한 줄로 그리고 그 줄을 열어 둔다.

    `with` 블록 안에서 같은 줄에 위젯을 더 놓을 수 있다. 표시 기준을 바꾸는 토글처럼
    표와 붙어 있어야 뜻이 통하는 컨트롤이 그렇다. 더 놓을 것이 없으면
    `render_table_heading` 을 쓴다.
    """
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.subheader(title, width="content")
        if caption:
            st.caption(caption, width="content")
        render_csv_download(data=csv, file_name=file_name, key=key)
        yield


def render_table_heading(
    title: str,
    *,
    caption: str | None = None,
    csv: bytes,
    file_name: str,
    key: str,
) -> None:
    """표 제목 · 부가 설명 · CSV 내보내기 한 줄. 대부분의 표가 이 형태다."""
    with table_heading_row(title, caption=caption, csv=csv, file_name=file_name, key=key):
        pass
