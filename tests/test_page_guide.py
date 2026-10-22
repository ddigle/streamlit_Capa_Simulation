# Purpose: Guide 버튼의 가이드 고르는 차례 · 옆 창 · 설정 사전 · 가이드 자리 위생을 잰다.

"""Guide 버튼의 따라하기 가이드(`components/page_guide.py`).

- 고르는 차례: `static/guides/local/<가이드>.html`(사내판) → `static/guides/howto/<가이드>.html`
  (예시판) → 지금의 md 대화상자. 셋을 임시 `static/` 으로 하나씩 세워 본다 — 저장소의
  `static/` 을 보지 않으므로 사내에 사내판이 있어도 같은 결과다.
- 옆 창: 툴바 버튼이 누르는 순간 CSS 변수의 상대 주소로 이름 붙은 좁은 창을 열고, 못 열면
  대화상자로 간다.
- 설정 사전: 창(틀 `guides/howto/template.html`)이 앱 창의 숨은 Guide 버튼을 같은 선택자로
  누른다.
- 자리 위생: 사내 자리(`static/guides/local/` · `review/guide/`)는 추적하지 않고 무시되며,
  추적하는 가이드 HTML 은 `static/guides/howto/` 아래 뼈대 이름으로만 있다.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from capa_simulation.components import page_guide
from capa_simulation.components.page_guide import (
    GUIDE_HREF_VARIABLE,
    GUIDE_WINDOW_NAME,
    GUIDE_WINDOW_WIDTH,
    STATIC_URL_PREFIX,
    TRIGGER_SELECTOR,
    find_howto_guide,
    guide_show_style,
    guide_toolbar_script,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOWTO = PROJECT_ROOT / "src" / "capa_simulation" / "guides" / "howto"
TEMPLATE = HOWTO / "template.html"


def _board(static_dir: Path, folder: str, name: str = "lob") -> Path:
    path = static_dir / "guides" / folder / f"{name}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<!doctype html><title>가이드</title>", encoding="utf-8")
    return path


def _tracked(*patterns: str) -> list[str]:
    completed = subprocess.run(
        ["git", "-c", "core.quotePath=false", "ls-files", *patterns],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


# ------------------------------------------------------------------------------ 고르는 차례


def test_the_internal_board_wins_over_the_example(tmp_path: Path) -> None:
    local = _board(tmp_path, "local")
    _board(tmp_path, "howto")

    guide = find_howto_guide("lob", static_dir=tmp_path)

    assert guide is not None
    assert (guide.kind, guide.path, guide.url) == (
        "local",
        local,
        "app/static/guides/local/lob.html",
    )


def test_without_an_internal_board_the_example_opens(tmp_path: Path) -> None:
    example = _board(tmp_path, "howto")
    # 다른 가이드의 사내판은 이 가이드를 가로채지 않는다.
    _board(tmp_path, "local", name="other")

    guide = find_howto_guide("lob", static_dir=tmp_path)

    assert guide is not None
    assert (guide.kind, guide.path, guide.url) == (
        "example",
        example,
        "app/static/guides/howto/lob.html",
    )


def test_without_either_board_the_markdown_dialog_stays(tmp_path: Path) -> None:
    # 폴더만 있고 파일이 없거나, 같은 이름의 폴더가 있어도 가이드가 아니다.
    (tmp_path / "guides" / "local" / "lob.html").mkdir(parents=True)
    (tmp_path / "guides" / "howto").mkdir(parents=True)

    assert find_howto_guide("lob", static_dir=tmp_path) is None
    # 대화상자 쪽은 지금 규칙 그대로 — 버튼만 보이게 하고 주소를 싣지 않는다.
    assert guide_show_style(None) == page_guide._SHOW_STYLE
    assert GUIDE_HREF_VARIABLE not in guide_show_style(None)


@pytest.mark.parametrize("name", ["../lob", "lob.html", 'lob"', "Lob", "", "guides/lob", "lob "])
def test_a_guide_name_cannot_leave_the_static_folder_or_break_the_css(name: str) -> None:
    with pytest.raises(ValueError):
        find_howto_guide(name, static_dir=PROJECT_ROOT / "static")


def test_the_show_style_carries_a_relative_address_for_the_toolbar_button(tmp_path: Path) -> None:
    """WebIDE 의 `/proxy/<포트>/` 접두에서도 열리도록 문서 기준 상대 주소다(앞에 `/` 없음)."""
    _board(tmp_path, "howto")
    guide = find_howto_guide("lob", static_dir=tmp_path)
    assert guide is not None

    style = guide_show_style(guide)

    assert guide.url.startswith(STATIC_URL_PREFIX) and not guide.url.startswith("/")
    assert STATIC_URL_PREFIX == "app/static/"
    assert f'{GUIDE_HREF_VARIABLE}: "{guide.url}";' in style
    # 탐색 · 프래그먼트 시험이 찾는 꼴(버튼을 보이게 하는 규칙)은 그대로다.
    assert f"#{page_guide.BUTTON_ID}" in style and "inline-block" in style
    assert style.startswith("<style>") and style.endswith("</style>")


def test_the_default_static_folder_is_the_one_streamlit_serves() -> None:
    """Streamlit 은 `app.py` 옆 `static/` 만 `app/static/…` 으로 보낸다."""
    assert page_guide.STATIC_DIR == PROJECT_ROOT / "static"
    assert (PROJECT_ROOT / "app.py").is_file()
    config = (PROJECT_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert re.search(r"^enableStaticServing = true$", config, re.MULTILINE)


# ------------------------------------------------------------------------------ 옆 창 · 설정 사전


def test_the_toolbar_button_opens_a_named_side_window_and_falls_back_to_the_dialog() -> None:
    script = guide_toolbar_script()
    click = script[script.index("button.onclick") :]

    # 누르는 순간 버튼에 실린 주소를 읽어 문서 기준으로 풀고, 이름 붙은 좁은 창을 연다.
    assert f'getPropertyValue("{GUIDE_HREF_VARIABLE}")' in script
    assert "new parentWindow.URL(href, doc.baseURI)" in script
    assert f'parentWindow.open("", "{GUIDE_WINDOW_NAME}", features)' in script
    assert f"var width = {GUIDE_WINDOW_WIDTH};" in script
    # 창을 열었으면 끝, 못 열었으면(가이드 없음 · 팝업 막힘) 숨은 버튼으로 대화상자.
    assert click.index("openGuideWindow(guideHref(button))") < click.index(TRIGGER_SELECTOR)
    assert "if (!win) return false;" in script
    # 있는 창은 다시 읽지 않는다 — 보던 단계가 남는다.
    assert 'win.location.href.split("#")[0] !== url' in script


def test_the_guide_window_keeps_the_markdown_guide_as_its_settings_dictionary() -> None:
    """md 설명서는 창 머리의 「설정 사전」 단추로 남는다 — 앱 창의 숨은 버튼을 같은 꼴로 누른다."""
    template = TEMPLATE.read_text(encoding="utf-8")

    assert ">설정 사전</button>" in template
    assert f'const DICT_TRIGGER = "{TRIGGER_SELECTOR}";' in template
    assert "window.opener.top" in template
    assert "detail: 1" in template
    # 앱 없이 연 파일(앱 창이 없음)에서는 단추를 감춘다.
    assert 'id="dict" type="button" hidden' in template
    assert "dict.hidden = !appWindow();" in template


# ------------------------------------------------------------------------------ 자리 위생


def test_internal_guide_places_stay_untracked_and_ignored() -> None:
    """사내판 · 사내 덮어쓰기 · 매개값은 사내에서만 만든다 — 커밋되지 않고, 무시되어 배포 적용이
    지우지 않는다(무시된 파일은 적용기의 지움 후보가 아니다)."""
    assert _tracked("static/guides/local", "review/guide") == []
    for path in (
        "static/guides/local/lob.html",
        "review/guide/overrides.json",
        "review/guide/params.json",
    ):
        completed = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", path], cwd=PROJECT_ROOT, check=False
        )
        assert completed.returncode == 0, f"{path} 가 .gitignore 에 걸리지 않습니다"
    # 예시판 자리는 무시되면 안 된다(추적).
    completed = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", "static/guides/howto/lob.html"],
        cwd=PROJECT_ROOT,
        check=False,
    )
    assert completed.returncode == 1


def test_tracked_guide_boards_sit_under_static_howto_and_match_a_skeleton() -> None:
    boards = _tracked("static/guides")
    skeletons = {path.name for path in HOWTO.iterdir() if (path / "content.json").is_file()}

    for board in boards:
        match = re.fullmatch(r"static/guides/howto/([a-z][a-z0-9_]*)\.html", board)
        assert match, f"가이드 HTML 은 static/guides/howto/<가이드>.html 에만 둡니다: {board}"
        assert match.group(1) in skeletons, board
    # 문서가 새 자리를 가리킨다 — 읽는 쪽이 이 파일이 무엇인지 찾지 않게 한다.
    for name in ("README.md", "AGENTS.md"):
        text = (PROJECT_ROOT / name).read_text(encoding="utf-8")
        assert "static/guides/howto/" in text, name
        assert "static/guides/local/" in text, name
