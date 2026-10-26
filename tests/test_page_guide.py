# Purpose: Guide 버튼의 가이드 고르는 차례 · 옆 창 · 설정 사전 · 가이드 자리와 md 글 위생을 잰다.

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
- md 글 위생: 탭 이름을 일괄로 바꿀 때 떨어져 남은 조사(「… 탭 와」)가 Guide·문서에 없고, 같은
  낱말이 두 곳을 가리키는 자리(가용설비 현황 `Summary` 탭과 입장 화면 Summary)에 가르는 한 줄이
  있고, 범위 글의 물결표(「100~140%」)가 지움선 짝이 되지 않게 `\\~` 로 막혀 있다.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from capa_simulation import settings
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
GUIDES = PROJECT_ROOT / "src" / "capa_simulation" / "guides"
HOWTO = GUIDES / "howto"
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


# ------------------------------------------------------------------------------ 커밋된 예시판


def _board_data(html: str) -> dict[str, object]:
    payload = html.split("const DATA = ", 1)[1].split(";\n", 1)[0]
    data = json.loads(payload)
    assert isinstance(data, dict)
    return data


def _identity_needles() -> list[str]:
    """실 담당 조직 · 문의처와 거기서 나오는 조각(이름 · 회사). 값은 settings 정본에서 읽는다."""
    from capa_simulation.io.object_storage import DEFAULT_PROFILE

    local, domain = settings.APP_CONTACT_EMAIL.split("@", 1)
    return [
        settings.APP_OWNER_TEAM,
        settings.APP_CONTACT_EMAIL,
        local,
        *[part for part in re.split(r"[._-]", local) if len(part) >= 3],
        domain,
        domain.split(".", 1)[0],
        DEFAULT_PROFILE,
    ]


def test_the_committed_example_board_is_one_synthetic_self_contained_file() -> None:
    """예시판(`static/guides/howto/lob.html`)은 공개 저장소에 실린다 — 한 파일로 서고(외부 참조 0),
    그림 밖 글에 실 담당 조직 · 문의처 · 이메일이 없고, 지금 원고 판으로 만든 것이다."""
    path = PROJECT_ROOT / "static" / "guides" / "howto" / "lob.html"
    html = path.read_text(encoding="utf-8")
    data = _board_data(html)
    content = json.loads((HOWTO / "lob" / "content.json").read_text(encoding="utf-8"))

    assert "\r" not in html
    assert path.stat().st_size < 6 * 1024 * 1024
    assert data["version"] == content["version"]
    assert data["shotLabel"] == "예시 화면 · 합성 샘플"
    images = data["images"]
    assert isinstance(images, dict) and len(images) >= 40
    assert all(str(uri).startswith("data:image/webp;base64,") for uri in images.values())
    # 외부 참조 0.
    assert not re.findall(r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//""", html)
    assert not re.findall(r"""url\(\s*["']?\s*(?:https?:)?//""", html)
    assert "@import" not in html and "<link" not in html
    # 그림 밖 글(그림 바이트를 걷어 낸 나머지)에 실 식별값이 없다. 그림은 촬영기가 가린다.
    text = re.sub(r"data:image/webp;base64,[A-Za-z0-9+/=]+", "", html)
    lowered = text.lower()
    for needle in _identity_needles():
        assert needle.lower() not in lowered, "예시판에 실 식별값이 남았습니다"
    assert not re.findall(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}", text)
    # 설정 사전(md 대화상자로 가는 길)이 실린 틀로 만들었다.
    assert ">설정 사전</button>" in html


def test_the_committed_example_shots_cover_the_states_internal_runs_skip() -> None:
    """사내 1단계가 찍지 않는 상태(사슬에 `db` · `shared`)의 합성 그림이 뼈대에 실려 있다."""
    folder = HOWTO / "lob" / "example"
    shots = json.loads((folder / "shots.json").read_text(encoding="utf-8"))
    plan = json.loads((HOWTO / "lob" / "plan.json").read_text(encoding="utf-8"))
    content = json.loads((HOWTO / "lob" / "content.json").read_text(encoding="utf-8"))
    states = {state["id"]: state for state in plan["states"]}

    def chain_writes(state_id: str) -> set[str]:
        grades: set[str] = set()
        current: str | None = state_id
        while current:
            grades.add(states[current]["writes"])
            current = states[current].get("from")
        return grades

    skipped = {state_id for state_id in states if chain_writes(state_id) & {"db", "shared"}}

    assert shots["version"] == content["version"] and shots["mode"] == "example"
    assert {state["id"] for state in shots["states"]} == skipped
    assert sorted(path.name for path in folder.glob("*.webp")) == sorted(
        f"{state_id}.webp" for state_id in skipped
    )


# ------------------------------------------------------------------------------ md 글 위생

# 「탭」 은 받침이 있어 조사가 붙어 「탭과·탭의·탭에서」 가 된다. 띄어 쓴 조사(「탭 와」)는
# 「RawData 와」 를 「설비 마스터 탭 와」 로 일괄로 바꾼 흔적이다(2026-10-25 리뷰 — Space Guide
# 여섯 줄).
_DETACHED_TAB_PARTICLE = re.compile(r"탭 (와|과|의|에서|에|을|를|은|는|이|가)(?![가-힣])")


def test_guides_and_docs_keep_particles_attached_to_tab() -> None:
    documents = [
        *sorted(GUIDES.glob("*.md")),
        *sorted((PROJECT_ROOT / "docs").rglob("*.md")),
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "AGENTS.md",
        PROJECT_ROOT / "CLAUDE.md",
    ]
    found = [
        f"{path.relative_to(PROJECT_ROOT)}:{number}: {line.strip()}"
        for path in documents
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if _DETACHED_TAB_PARTICLE.search(line)
    ]
    assert not found, "탭 뒤 조사를 붙여 씁니다(「탭과」·「탭의」·「탭에서」):\n" + "\n".join(found)


def test_the_equipment_guide_tells_its_summary_tab_from_the_intro_summary() -> None:
    """가용설비 현황 ② 「Summary」 는 입장 화면·사이드바 앱 이름 라벨이 여는 Summary 와 낱말이
    같다 — 아이콘으로 가르고 Guide 에 한 줄을 둔다(가용설비 현황 개편 사양 R18)."""
    from capa_simulation.navigation import EQUIPMENT_SUMMARY_TAB

    guide = " ".join((GUIDES / "available_equipment_status.md").read_text(encoding="utf-8").split())
    assert EQUIPMENT_SUMMARY_TAB.startswith(":material/")
    assert "입장 화면이나 사이드바 맨 위 앱 이름 라벨이 여는 **Summary**" in guide
    assert "다른 것입니다" in guide


# Streamlit 마크다운(GFM)은 홑물결표 짝도 지움선으로 읽는다 — 「버튼 100~140% 또는 직접 50~300%」 가
# 「버튼 100<del>140% 또는 직접 50</del>300%」 로 그려졌다(2026-10-25 E2E, 제약 시뮬레이션 Guide).
# 앞뒤가 모두 빈칸인 `~`(「1일 ~ 말일」)는 짝이 되지 못하고, 코드 칸(`` `…` ``) 안은 글 그대로다.
_CODE_SPAN = re.compile(r"`[^`]*`")
_OPEN_TILDE = re.compile(r"(?<!\\)~(?! )|(?<! )(?<!\\)~")


def _tilde_lines(text: str) -> list[str]:
    """지움선 짝이 될 수 있는 물결표가 든 줄 — 코드 칸 밖 · `\\~` 아님 · 한쪽이라도 빈칸이 아닌
    이웃."""
    found: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        bare = _CODE_SPAN.sub("", line)
        if _OPEN_TILDE.search(f" {bare} "):
            found.append(f"{number}: {line.strip()}")
    return found


def test_the_tilde_check_tells_a_range_from_a_spaced_or_escaped_tilde() -> None:
    assert _tilde_lines("버튼 100~140% 또는 직접 50~300%") == ["1: 버튼 100~140% 또는 직접 50~300%"]
    assert _tilde_lines("~앞에 붙은 것") and _tilde_lines("뒤에 붙은 것~")
    assert _tilde_lines("첫 소요 달 ~ 보이는 마지막 달") == []
    assert _tilde_lines("버튼 100\\~140% 또는 직접 50\\~300%") == []
    assert _tilde_lines("코드 `A~B~C` 는 글 그대로") == []


@pytest.mark.parametrize("page", sorted(path.stem for path in GUIDES.glob("*.md")))
def test_guide_ranges_escape_the_tilde(page: str) -> None:
    """Guide 대화상자는 md 원문을 그대로 `st.markdown` 에 넘긴다(`page_guide._open_guide`) — 범위
    글의 물결표는 원문에서 `\\~` 로 막는다(같은 화면의 `schedule_lines` 와 같은 꼴)."""
    found = _tilde_lines((GUIDES / f"{page}.md").read_text(encoding="utf-8"))
    assert not found, "물결표를 \\~ 로 막습니다(지움선이 됩니다):\n" + "\n".join(found)


def test_a_wide_guide_table_scrolls_inside_its_own_box() -> None:
    """390px 창에서 가용설비 현황 Guide 의 「묶음·보유·대여·가용」 표(400px)가 칸(320px)을 넘어
    대화상자를 옆으로 밀고 「가용」 열이 잘렸다(2026-10-26 E2E). 본문은 키 붙은 칸에 들고, 그 칸의
    표만 제 폭 안에서 옆으로 굴린다 — 기본 규칙은 모든 화면이 매 회차 깐다."""
    from streamlit.testing.v1 import AppTest

    assert re.search(
        rf"\.st-key-{page_guide.GUIDE_BODY_KEY} table \{{ display: block; max-width: 100%; "
        r"overflow: auto; \}",
        page_guide._BASE_STYLE,
    )
    app = AppTest.from_string(
        "from capa_simulation.components.page_guide import render_page_guide\n"
        'render_page_guide("available_equipment_status", title="가용설비 현황")\n'
    ).run()
    app.button(key=page_guide.GUIDE_TRIGGER_KEY).click().run()

    assert not app.exception
    bodies = _markdown_under_key(app._tree, page_guide.GUIDE_BODY_KEY)
    assert any("| 묶음 | 보유 | 대여 | 가용 |" in body for body in bodies), bodies


def _markdown_under_key(node: object, key: str, inside: bool = False) -> list[str]:
    """`st.container(key=key)` 블록 안의 마크다운 글 — 블록 id 가 `…-<key>` 로 끝난다."""
    proto = getattr(node, "proto", None)
    block_id = getattr(proto, "id", "") if proto is not None else ""
    inside = inside or (isinstance(block_id, str) and block_id.endswith(f"-{key}"))
    found = (
        [str(getattr(node, "value", ""))] if inside and type(node).__name__ == "Markdown" else []
    )
    children = getattr(node, "children", None)
    if isinstance(children, dict):
        for child in children.values():
            found += _markdown_under_key(child, key, inside)
    return found
