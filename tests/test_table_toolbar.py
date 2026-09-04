# Purpose: CSV 내보내기 버튼과 표 제목 줄이 한 곳에서만 만들어지는지 지킨다.

"""내보내기 버튼 표기가 갈라지지 않게 막는다.

예전에는 13곳이 각자 `st.download_button` 을 불렀고 표기가 두 갈래였다. 라벨에
`:material/download:` 를 적은 것과 `icon=` 인자를 쓴 것이라 아이콘 간격이 달랐고,
`mime` 도 `text/csv` 와 `text/csv;charset=utf-8` 이 섞여 있었으며, 일부는
`on_click="ignore"` 가 빠져 내려받을 때마다 페이지가 통째로 다시 계산됐다.
"""

import re
from pathlib import Path

from capa_simulation.components.table_toolbar import CSV_MIME, DOWNLOAD_ICON

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OWNER = PROJECT_ROOT / "src/capa_simulation/components/table_toolbar.py"


def _sources() -> list[Path]:
    return [
        path
        for path in [
            *(PROJECT_ROOT / "app_pages").glob("*.py"),
            *(PROJECT_ROOT / "src/capa_simulation").rglob("*.py"),
        ]
        if path != OWNER
    ]


def test_download_button_is_created_in_one_place() -> None:
    offenders = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in _sources()
        if "st.download_button(" in path.read_text(encoding="utf-8")
    ]

    assert not offenders, f"table_toolbar.render_csv_download 를 쓰세요: {offenders}"


def test_download_icon_is_not_inlined_in_labels() -> None:
    """라벨 문자열에 아이콘을 섞으면 `icon=` 을 쓴 버튼과 간격이 달라진다."""
    offenders = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in _sources()
        if f"{DOWNLOAD_ICON} " in path.read_text(encoding="utf-8")
    ]

    assert not offenders, f"라벨 대신 render_csv_download 의 label 을 쓰세요: {offenders}"


def test_csv_mime_declares_the_charset() -> None:
    """내보내는 바이트는 전부 `utf-8-sig` 다. charset 을 빼면 Excel 밖에서 한글이 깨진다."""
    assert CSV_MIME == "text/csv;charset=utf-8"


BUTTON_LABEL_ICON = re.compile(
    r"st\.(?:button|form_submit_button)\(\s*\"?:material/",
    re.MULTILINE,
)


def test_button_icons_use_the_icon_argument() -> None:
    """버튼 라벨에 아이콘을 섞으면 `icon=` 을 쓴 버튼과 간격·크기가 달라진다.

    라벨에 넣은 것은 본문 글자와 같은 흐름으로 그려지고, `icon=` 은 별도 아이콘 자리에
    놓인다. 두 표기가 섞여 있어 같은 화면의 버튼끼리 아이콘 위치가 어긋났다.
    `st.tabs` 처럼 `icon=` 이 없는 위젯은 라벨에 넣는 수밖에 없으므로 검사하지 않는다.
    """
    offenders = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in [*_sources(), OWNER]
        if BUTTON_LABEL_ICON.search(path.read_text(encoding="utf-8"))
    ]

    assert not offenders, f"라벨 대신 st.button(icon=...) 을 쓰세요: {offenders}"
