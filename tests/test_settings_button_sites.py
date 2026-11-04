# Purpose: 「설정」 팝업을 여는 단추가 본문에 없고 사이드바 설정 상자로만 서는지 소스에서 본다.

"""본문 설정 단추 그물(설계 규칙 UI-LAY-01 — `docs/design_rules.md` 5-1).

화면 설정 묶음(여럿이 함께 쓰는 공용 값을 고치는 팝업)을 여는 단추는 페이지 본문에 두지 않고
사이드바 조회 조건 패널 바로 밑 설정 상자(`components/settings_box.py` — 상자 = 단추 → 같은 제목
팝업)로 둔다(2026-11-03 사용자 지시 · 2026-11-04 확인 보드 AMB-07 (가)). 새 화면도 같다.

- 화면 코드(`app.py` · `app_pages/` · `src/capa_simulation/`, 상자를 그리는 `settings_box.py`
  밖)에서 라벨에 「설정」 이 든 `st.button(` · `st.popover(`(칸 · 사이드바의 같은 이름 부름 포함)를
  찾아 빈 허용 목록과 맞댄다. 저장 · 적용 · 지우기 같은 쓰기 단추(「설정 저장」)는 팝업을 열지
  않아 뺀다. 편집표에 딸린 「표 보기 설정」 은 펼침(`st.expander`)이라 팝업 단추가 아니다
  (AMB-07 (가) — 본문).
- 제목에 「설정」 이 든 팝업(`st.dialog`)은 모두 같은 제목의 사이드바 설정 상자
  (`render_settings_box`)가 연다 — 본문 단추로 여는 새 설정 팝업은 상자가 없어 실패한다.
- 라벨을 매개변수로 받는 단추(공용 도우미 안)는 그물 밖이다 — 판단 질문이 본다.
"""

from __future__ import annotations

from pathlib import Path

from source_sites import (
    PROJECT_ROOT,
    TextResolver,
    called_name,
    first_text_argument,
    method,
    screen_calls,
    screen_files,
)

SETTINGS_WORD = "설정"
# 사이드바 설정 상자 — 이 모듈만 「… 설정」 단추를 그린다.
OWNERS = ("src/capa_simulation/components/settings_box.py",)
# 팝업을 여는 단추.
OPENERS = frozenset({"button", "popover"})
# 쓰기 단추의 낱말 — 「설정 저장」 처럼 설정 값을 쓰는 단추는 팝업을 열지 않는다.
WRITE_WORDS = ("저장", "적용", "지우", "되돌", "초기화", "버리", "내려받")
# (파일, 맨 바깥 함수) → 본문 설정 단추 수. 비어 있다 — 늘리지 않는다.
ALLOWED: dict[tuple[str, str], int] = {}


def _opens_settings(label: str) -> bool:
    return SETTINGS_WORD in label and not any(word in label for word in WRITE_WORDS)


def body_settings_buttons(
    paths: list[Path] | None = None, root: Path = PROJECT_ROOT
) -> dict[tuple[str, str], list[int]]:
    """(파일, 맨 바깥 함수) 마다 라벨에 「설정」 이 든 팝업 여는 단추의 줄 번호."""
    resolver = TextResolver()
    found: dict[tuple[str, str], list[int]] = {}
    for relative, outer, path, scope, call in screen_calls(
        paths or screen_files(exclude=OWNERS), root
    ):
        if method(call) not in OPENERS:
            continue
        label = first_text_argument(call, "label")
        if label is not None and any(
            _opens_settings(text) for text in resolver.wholes(label, path, scope)
        ):
            found.setdefault((relative, outer), []).append(call.lineno)
    return found


def _titles(paths: list[Path], root: Path, name: str) -> dict[str, str]:
    """제목에 「설정」 이 든 `name` 부름(`st.dialog` · `render_settings_box`)의 제목 → 자리."""
    resolver = TextResolver()
    titles: dict[str, str] = {}
    for relative, outer, path, scope, call in screen_calls(paths, root):
        if called_name(call) != name:
            continue
        title = first_text_argument(call, "title")
        if title is None:
            continue
        for text in resolver.wholes(title, path, scope):
            if SETTINGS_WORD in text:
                titles[text] = f"{relative} {outer or '(본문)'}"
    return titles


def test_no_page_body_opens_a_settings_popup() -> None:
    found = body_settings_buttons()
    assert {site: len(lines) for site, lines in found.items()} == ALLOWED, (
        "라벨에 「설정」 이 든 팝업 여는 단추가 페이지 본문에 있습니다(줄 번호) — 공용 값을 고치는"
        " 팝업은 사이드바 설정 상자(components/settings_box.render_settings_box)로 엽니다:\n"
        + "\n".join(f"{file} {func or '(본문)'}: {lines}" for (file, func), lines in found.items())
    )


def test_every_settings_popup_opens_from_a_sidebar_box() -> None:
    files = screen_files()
    dialogs = _titles(files, PROJECT_ROOT, "dialog")
    boxes = _titles(files, PROJECT_ROOT, "render_settings_box")

    assert dialogs, "제목에 「설정」 이 든 팝업을 찾지 못했습니다 — 그물이 낡았습니다."
    missing = {title: place for title, place in dialogs.items() if title not in boxes}
    assert not missing, (
        "사이드바 설정 상자 없이 서는 설정 팝업입니다 — 같은 제목으로 render_settings_box 를"
        f" 부르세요: {missing}"
    )


SAMPLE_PAGE = """
import streamlit as st

TITLE = "가동 설정"


def render(slot) -> None:
    st.button(TITLE)
    slot.popover("표 설정")
    st.button(f"{TITLE} 저장")
    st.form_submit_button("설정 적용")
    st.expander("표 보기 설정")
    st.button("열기")
"""


def test_the_net_finds_a_settings_opener_in_the_body(tmp_path: Path) -> None:
    page = tmp_path / "page.py"
    page.write_text(SAMPLE_PAGE, encoding="utf-8")

    found = body_settings_buttons([page], tmp_path)

    assert {site: len(lines) for site, lines in found.items()} == {("page.py", "render"): 2}
