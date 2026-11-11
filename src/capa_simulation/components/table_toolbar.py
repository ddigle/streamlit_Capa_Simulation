# Purpose: 표 제목 줄, CSV·엑셀 내려받기 쌍·높이·파일 이름 토막, 표 도구 막대 띄움·자리를 짓는다.

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

표 곁 CSV 와 「시트 엑셀」(화면 서식째 xlsx) 한 쌍은 `render_download_pair` 하나가 그린다 — 공정
Capa 상세 표 도구 줄 · 산출 결과 대당 Capa · 소요대수 제목 줄 · 가용설비 Static 대비 일정
시트(전환 줄 끝) · 호기 목록(목록 아래). 둘은 「내려받기 ▾」 메뉴 하나에 묶인다(2026-11-10 답
Q2-7 — 설계 규칙 UI-LAY-11 「드물게 쓰는 같은 갈래 단추를 메뉴 하나로」).
파일이 하나뿐이면(CSV 가 없는 자리) 메뉴 없이 그 단추 하나다. 줄에 선 메뉴(또는 그 단추
하나)의 높이는 네 자리 모두 28px 하나다(2026-11-11 남은 물음 보드 C9 — `DOWNLOAD_MENU_STYLE`).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

# 내보내는 바이트는 전부 BOM 이 붙은 UTF-8 이다. Excel 이 한글을 깨뜨리지 않게 하려는
# 것이고, 그렇다면 charset 도 함께 밝혀야 브라우저가 같은 판단을 한다.
CSV_MIME = "text/csv;charset=utf-8"

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

DOWNLOAD_ICON = ":material/download:"

CSV_DOWNLOAD_LABEL = "CSV 다운로드"

CSV_TEMPLATE_LABEL = "CSV 양식 다운로드"

# 화면 표 하나를 지금 화면 상태 · 서식 그대로 내려받는 xlsx 단추 글(공정 Capa 상세 · 산출 결과).
SHEET_XLSX_LABEL = "시트 엑셀"

# 표 곁 내려받기 둘(CSV · 시트 엑셀)을 묶는 메뉴(팝오버) 글 — 「내려받기 ▾」(2026-11-10 답 Q2-7,
# 설비 마스터 「선택 ▾」 과 같은 꼴). 안의 단추는 `on_click="ignore"` 라 눌러도 회차가 돌지 않아
# 메뉴가 열린 채 초점이 그 단추에 남고 Esc 로 닫힌다.
DOWNLOAD_MENU_LABEL = "내려받기"
# 줄에 선 「내려받기 ▾」 메뉴(또는 CSV 가 없어 메뉴 없이 선 「시트 엑셀」 칸)의 key 접두어와
# 그 단추 높이. 높이는 `render_download_pair` 를 쓰는 네 자리(공정 Capa 상세 표 도구 줄 · 산출
# 결과 표 제목 줄 · Static 대비 일정 전환 줄 · 호기 목록 아래)가 모두 같다(2026-11-11 남은 물음
# 보드 C9 「render_download_pair 한 곳에서 같은 높이」). 값은 공정 Capa 상세 표 도구 줄 · Static
# 대비 일정 전환 줄의 이웃 높이 — 「구획」 칩 · 「조회 결과 · 표시」 전환 단추 28px(설계 규칙
# UI-CON-01 · 4장) — 이고, 호기 목록 아래 메뉴는 혼자 선다. 산출 결과 표 제목 줄은 곁 칸에 따라 줄
# 높이가 갈린다 — 메뉴만 선 줄(대당 Capa · 소요대수 상세 끔)은 28.4px, 소요대수 상세 켬은 곁 「표시
# 범위」 칸(33px)이, 확보율 탭은 맨 CSV 단추(기본 35px)가 줄을 35px 로 세워 탭을 오가거나 상세를
# 켜고 끌 때 표 윗선이 갈린다(4장 「산출 결과 표 제목 줄」 · UI-PRF-03 — 그 줄의 높이 값은 사용자
# 물음). 메뉴 안 단추는 줄 밖(떠 있는 층)이라 기본 높이다. 서식은 앱 전체 서식(`app.py` 가 매
# 회차 보내는 사이드바 서식 `st.html`)에 실어 보낸다 — 부르는 자리마다 스타일만 든 `st.html` 을
# 두면 이벤트 칸에 서서 본문 프래그먼트(공정 Capa 상세)의 이벤트 칸 수가 바뀐다.
DOWNLOAD_MENU_KEY_PREFIX = "download_menu_"
DOWNLOAD_MENU_HEIGHT_PX = 28
DOWNLOAD_MENU_STYLE = (
    f'<style>[class*="st-key-{DOWNLOAD_MENU_KEY_PREFIX}"] button '
    f"{{ min-height: {DOWNLOAD_MENU_HEIGHT_PX}px; height: {DOWNLOAD_MENU_HEIGHT_PX}px; "
    "padding-block: 0; }</style>"
)

# 표 앞 띄움(px, `st.space`) — 표에 마우스를 올리면 오른쪽 위 도구 막대(열 보기·내려받기·찾기·
# 전체 화면)가 표 머리 위 37px 까지 솟는다. 표 바로 위 줄에 누를 것(입력·단추·팝오버·토글·날짜
# 칸)이 있으면 그 막대가 그 줄에 닿지 않을 만큼 표 앞에 띄운다(AGENTS 9장 「표 도구 막대」). 이
# 띄움의 숫자는 여기 하나다 — 다른 모듈의 이름은 이 값을 가리키는 별칭이다
# (`tests/test_table_toolbar.py`).
TABLE_TOOLBAR_CLEARANCE = 24
# 표 도구 막대 자리(px) — 표 바로 위 줄의 오른쪽 끝을 이만큼 비우면 막대(1600 · 1283 창에서 행을
# 더하고 지우는 표 112px · 행이 고정된 표 92.4px — 샘플 관측)가 그 빈 위에 서므로 표 앞 띄움 없이
# 표가 줄 바로 아래(줄 사이 14px)에 붙는다. 넓은 막대보다 8px 남긴다(AGENTS 9장 「표 도구 막대」).
TABLE_TOOLBAR_ROOM = 120


def file_name_part(text: str, *, fallback: str) -> str:
    """내려받는 파일 이름의 한 토막 — 경로 · 예약 글자(`\\ / : * ? " < > |`)와 빈칸을 `_` 로,
    겹친 `_` 는 하나로, 앞뒤 `_` 는 걷는다. 남는 글자가 없으면 `fallback`. 설비 시나리오 이름 ·
    공정 표시명처럼 사람이 적은 글을 파일 이름에 실을 때 쓴다."""
    cleaned = "".join("_" if char in '\\/:*?"<>|' or char.isspace() else char for char in text)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or fallback


def render_csv_download(
    *,
    data: bytes,
    file_name: str,
    key: str | None = None,
    label: str = CSV_DOWNLOAD_LABEL,
    text_link: bool = False,
) -> None:
    """CSV 내보내기 버튼 하나를 그린다.

    `on_click="ignore"` 를 항상 붙인다. 내려받기는 화면 상태를 바꾸지 않으므로 다시
    계산할 이유가 없고, 다시 계산하면 붙여넣던 텍스트나 펼쳐 둔 영역이 초기화된다.

    `text_link` 가 참이면 아이콘 없는 글자 단추(`type="tertiary"`)다 — 같은 줄 이웃이 글자
    단추뿐인 자리(시나리오 관리 「점검」 묶음 줄 「넓게 보기」 · 「CSV」)에서 이웃과 같은 꼴 ·
    같은 윗선으로 선다(설계 규칙 UI-CON-01).
    """
    st.download_button(
        label,
        data=data,
        file_name=file_name,
        mime=CSV_MIME,
        icon=None if text_link else DOWNLOAD_ICON,
        type="tertiary" if text_link else "secondary",
        key=key,
        on_click="ignore",
        width="content",
    )


def render_xlsx_download(*, data: bytes, file_name: str, key: str, label: str) -> None:
    """엑셀(xlsx) 내려받기 단추 하나 — CSV 단추와 같은 꼴(아이콘 · `on_click="ignore"` · 내용 폭).

    바이트는 부르는 쪽이 회차마다 다시 만들지 않게 기억해 둔 것을 넘긴다. 콜러블 지연 생성은 쓰지
    않는다 — 실패가 「Failed to generate file for download」 한 줄로 삼켜진다(9장 · TODO 결정 기록
    2026-09-18).
    """
    st.download_button(
        label,
        data=data,
        file_name=file_name,
        mime=XLSX_MIME,
        icon=DOWNLOAD_ICON,
        key=key,
        on_click="ignore",
        width="content",
    )


@dataclass(frozen=True, eq=False)
class CsvFile:
    """표 곁 CSV 단추 하나의 재료 — 바이트 · 파일 이름 · 위젯 key · 단추 글."""

    data: bytes
    file_name: str
    key: str
    label: str = CSV_DOWNLOAD_LABEL


@dataclass(frozen=True, eq=False)
class SheetFile:
    """「시트 엑셀」 단추 하나의 재료. 바이트는 부르는 쪽이 조건 키로 기억해 둔 것이다
    (`sheet_download.remembered_bytes`)."""

    data: bytes
    file_name: str
    key: str
    label: str = SHEET_XLSX_LABEL


def download_menu_key(key: str) -> str:
    """CSV 단추 key 로 짓는 「내려받기 ▾」 메뉴 key(`table_heading_row`) — 접두어
    `DOWNLOAD_MENU_KEY_PREFIX` 로 시작한다."""
    return f"{DOWNLOAD_MENU_KEY_PREFIX}{key}"


def render_download_pair(
    *, csv: CsvFile | None, sheet: SheetFile | None = None, menu_key: str
) -> DeltaGenerator:
    """표 곁 내려받기 한 쌍 — 부르는 쪽 줄에 「내려받기 ▾」 메뉴 하나(`menu_key`)를 세우고 그 안에
    CSV 단추, 그 아래 「시트 엑셀」 칸을 이 차례로 둔다(2026-11-10 답 Q2-7).

    시트 바이트를 아직 짓지 못한 회차(공정 Capa 상세 — 제품 행 표를 받은 뒤에야 짓는다)는
    `sheet=None` 으로 부르고, 돌려받은 그 칸에 나중에 `render_sheet_download` 를 부른다. CSV 가 없는
    표(`csv=None`)는 묶을 것이 없어 메뉴 없이 내용 폭 엑셀 칸만 줄에 선다 — 그 칸이 `menu_key` 를
    받는다. `menu_key` 는 `DOWNLOAD_MENU_KEY_PREFIX` 로 시작해야 한다 — 줄에 선 메뉴 · 칸의 높이
    (`DOWNLOAD_MENU_STYLE`)가 그 접두어로 걸린다.
    """
    if not menu_key.startswith(DOWNLOAD_MENU_KEY_PREFIX):
        raise ValueError(f"메뉴 key 는 {DOWNLOAD_MENU_KEY_PREFIX!r} 로 시작합니다: {menu_key!r}")
    if csv is None:
        slot = st.container(width="content", key=menu_key)
    else:
        with st.popover(DOWNLOAD_MENU_LABEL, icon=DOWNLOAD_ICON, key=menu_key):
            render_csv_download(
                data=csv.data, file_name=csv.file_name, key=csv.key, label=csv.label
            )
            slot = st.container(width="content")
    if sheet is not None:
        render_sheet_download(slot, sheet)
    return slot


def render_sheet_download(slot: DeltaGenerator, sheet: SheetFile) -> None:
    """`render_download_pair` 가 돌려준 칸에 「시트 엑셀」 단추를 채운다."""
    with slot:
        render_xlsx_download(
            data=sheet.data, file_name=sheet.file_name, key=sheet.key, label=sheet.label
        )


def toolbar_clearance() -> None:
    """표 바로 앞에 도구 막대 띄움(`TABLE_TOOLBAR_CLEARANCE`)을 둔다.

    위 줄에 누를 것이 있는 표는 `st.dataframe`·`st.data_editor` 바로 앞에 부른다 — 막대가 위 줄의
    단추·입력 칸 지우기(✕)를 덮어 표에서 그리로 옮긴 누름을 가로채지 않게 한다.
    """
    st.space(TABLE_TOOLBAR_CLEARANCE)


def toolbar_room_css(row_key: str) -> str:
    """key 있는 가로 줄의 오른쪽 끝을 표 도구 막대 자리(`TABLE_TOOLBAR_ROOM`)만큼 비우는 서식 한 줄.

    표 바로 위 줄을 표 앞 띄움(`toolbar_clearance`) 대신 이것으로 비운다 — 입력 칸은 그 앞까지만
    늘어나고, 줄에 다 들지 못하는 단추는 막대 자리로 들어가지 않고 다음 줄로 내려간다. 부르는 쪽이
    화면 서식(`<style>`) 안에 넣는다.
    """
    return f".st-key-{row_key} {{ padding-right: {TABLE_TOOLBAR_ROOM}px; }}"


@contextmanager
def table_heading_row(
    title: str,
    *,
    caption: str | None = None,
    csv: bytes,
    file_name: str,
    key: str,
    sheet: SheetFile | None = None,
) -> Iterator[None]:
    """표 제목 · 부가 설명 · CSV 내보내기를 한 줄로 그리고 그 줄을 열어 둔다.

    `with` 블록 안에서 같은 줄에 위젯을 더 놓을 수 있다. 표시 기준을 바꾸는 토글처럼
    표와 붙어 있어야 뜻이 통하는 컨트롤이 그렇다. 더 놓을 것이 없으면
    `render_table_heading` 을 쓴다. `sheet` 를 주면 CSV 와 「시트 엑셀」 이 「내려받기 ▾」 메뉴
    하나에 묶인다(`render_download_pair`, 메뉴 key 는 `download_menu_key(key)`) — 주지 않으면 CSV
    단추 하나다.
    """
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.subheader(title, width="content")
        if caption:
            st.caption(caption, width="content")
        if sheet is None:
            render_csv_download(data=csv, file_name=file_name, key=key)
        else:
            render_download_pair(
                csv=CsvFile(data=csv, file_name=file_name, key=key),
                sheet=sheet,
                menu_key=download_menu_key(key),
            )
        yield


def render_table_heading(
    title: str,
    *,
    caption: str | None = None,
    csv: bytes,
    file_name: str,
    key: str,
    sheet: SheetFile | None = None,
) -> None:
    """표 제목 · 부가 설명 · CSV 내보내기 한 줄. 대부분의 표가 이 형태다."""
    with table_heading_row(
        title, caption=caption, csv=csv, file_name=file_name, key=key, sheet=sheet
    ):
        pass
