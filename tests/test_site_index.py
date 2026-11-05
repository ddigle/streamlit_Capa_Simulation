# Purpose: GitHub Pages 자료실의 목록 · 첫 화면 · 자료가 서로 맞고 외부 요청 없이 서는지 고정한다.

"""자료실 위생.

첫 화면은 `site/catalog.json` 에서 나오는 생성물이고 자료는 `site/<폴더>/index.html` 이다.
자료를 더하면서 목록이나 생성기 실행을 빠뜨리면 사내 Pages 에서 그 자료로 가는 길이 없어진다.
폐쇄망이라 외부 파일을 부르는 자료도 서지 않는다. 안내서는 동료가 첫 지시와 명령을 복사해 쓰는
곳이라 코드 블록은 글 원본과, 첫 지시는 지침서 0장과 글자까지 같아야 한다.
"""

import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_deploy_package import deploy_set, forbidden_entries, tracked_files  # noqa: E402
from build_site_index import (  # noqa: E402
    CATALOG_NAME,
    INDEX_NAME,
    SITE_DIR_NAME,
    CatalogEntry,
    catalog_problems,
    load_catalog,
    main,
    parse_catalog,
    render_index,
)

SITE_DIR = PROJECT_ROOT / SITE_DIR_NAME
CATALOG_PATH = SITE_DIR / CATALOG_NAME
ROOT_INDEX = PROJECT_ROOT / INDEX_NAME
DECK = SITE_DIR / "contest-deck" / INDEX_NAME
GUIDE = SITE_DIR / "module-guide" / INDEX_NAME
MODULE_GUIDE = PROJECT_ROOT / "docs" / "module_guide.md"
COLLEAGUE_GUIDE = PROJECT_ROOT / "docs" / "module_colleague_guide.md"
NO_JEKYLL = PROJECT_ROOT / ".nojekyll"

_GOOD_ROW = {
    "path": "demo-a",
    "title": "제목",
    "summary": "요약",
    "kind": "안내서",
    "updated": "2026-01-05",
}

# 파일을 부르는 자리의 바깥 주소만 본다. 글자로 적은 주소(`<code>http://localhost:8510</code>`,
# 번들 라이브러리의 이름공간 문자열)는 요청이 아니다. 주소가 글자 그대로 적힌 꼴까지가 이 그물이다 —
# 변수로 든 주소 · `new Worker` · `XMLHttpRequest` 는 못 본다(덱의 번들 라이브러리가 `fetch(변수)` ·
# `new Worker(변수)` 를 들고 있어 넓히면 오탐이다). 새 자료는 브라우저로 한 번 열어 본다.
_OUTSIDE_REQUEST = re.compile(
    r"""(?:\b(?:src|href|poster)\s*=\s*["']?\s*"""
    r"""|\bsrcset\s*=\s*["']?(?:[^"'>]*[\s,])?"""
    r"""|\burl\(\s*["']?\s*"""
    r"""|@import\s*["']\s*"""
    r"""|\b(?:fetch|import)\(\s*["'`]\s*)(?:https?:)?//""",
    re.IGNORECASE,
)


def _entries() -> list[CatalogEntry]:
    entries, problems = load_catalog(CATALOG_PATH)
    assert not problems, problems
    return entries


def _site_pages() -> list[Path]:
    return sorted(SITE_DIR.glob(f"*/{INDEX_NAME}"))


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.hrefs.extend(value for name, value in attrs if name == "href" and value)


def _sample_site(root: Path, *, listed: tuple[str, ...], pages: tuple[str, ...]) -> None:
    site = root / SITE_DIR_NAME
    site.mkdir()
    for name in pages:
        (site / name).mkdir()
        (site / name / INDEX_NAME).write_text("<!doctype html>", encoding="utf-8")
    rows = [{**_GOOD_ROW, "path": name} for name in listed]
    (site / CATALOG_NAME).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def test_every_catalog_entry_has_its_page() -> None:
    missing = [entry.path for entry in _entries() if not (PROJECT_ROOT / entry.href).is_file()]

    assert not missing, f"{CATALOG_NAME} 에 있는데 페이지가 없습니다: {missing}"
    assert not catalog_problems(_entries(), SITE_DIR)


def test_every_site_page_is_in_the_catalog() -> None:
    listed = {entry.path for entry in _entries()}
    unlisted = [page.parent.name for page in _site_pages() if page.parent.name not in listed]

    assert not unlisted, f"첫 화면에서 갈 길이 없습니다. {CATALOG_NAME} 에 더합니다: {unlisted}"


def test_the_root_index_is_the_generators_output() -> None:
    assert ROOT_INDEX.read_bytes() == render_index(_entries()).encode("utf-8")
    assert main(["--check"]) == 0


def test_the_generator_writes_then_check_passes_and_a_later_edit_fails(tmp_path: Path) -> None:
    _sample_site(tmp_path, listed=("demo-a",), pages=("demo-a",))

    assert main(["--check"], root=tmp_path) == 1
    assert main([], root=tmp_path) == 0
    assert main(["--check"], root=tmp_path) == 0

    written = tmp_path / INDEX_NAME
    written.write_bytes(written.read_bytes() + b"\n")
    assert main(["--check"], root=tmp_path) == 1


@pytest.mark.parametrize(
    ("listed", "pages", "expected"),
    [
        (("demo-a",), (), "site/demo-a/index.html 이 없습니다."),
        ((), ("demo-a",), "catalog.json 은 한 줄 이상의 배열이어야 합니다."),
        (("demo-a",), ("demo-a", "demo-b"), "site/demo-b/ 이 catalog.json 에 없습니다."),
        (("demo-a", "demo-a"), ("demo-a",), "demo-a 이 목록에 두 번 있습니다."),
    ],
)
def test_the_generator_refuses_a_catalog_that_does_not_match_the_folders(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    listed: tuple[str, ...],
    pages: tuple[str, ...],
    expected: str,
) -> None:
    _sample_site(tmp_path, listed=listed, pages=pages)

    assert main([], root=tmp_path) == 1
    assert not (tmp_path / INDEX_NAME).exists()
    assert expected in capsys.readouterr().err


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"title": ""}, "title"),
        ({"path": "../up"}, "path"),
        ({"updated": "2026-13-05"}, "updated"),
        ({"updated": "2026-1-5"}, "updated"),
        ({"summary": "a\nb"}, "summary"),
        ({"note": "1"}, "모르는 칸"),
    ],
)
def test_a_malformed_catalog_row_is_named(change: dict[str, str], expected: str) -> None:
    entries, problems = parse_catalog([{**_GOOD_ROW, **change}])

    assert not entries
    assert any(expected in problem for problem in problems), problems


def test_a_catalog_row_missing_a_field_is_named_and_a_good_row_passes() -> None:
    partial = {key: value for key, value in _GOOD_ROW.items() if key != "updated"}

    assert any("updated" in problem for problem in parse_catalog([partial])[1])
    assert parse_catalog([_GOOD_ROW]) == ([CatalogEntry(**_GOOD_ROW)], [])


def test_catalog_text_is_escaped_on_the_list() -> None:
    entry = CatalogEntry("demo-a", "<b>제목</b>", 'A & "B"', "안내서", "2026-01-05")

    rendered = render_index([entry])

    assert "<b>제목" not in rendered
    assert "&lt;b&gt;제목&lt;/b&gt;" in rendered
    assert "A &amp; &quot;B&quot;" in rendered


def test_the_root_index_stands_alone_in_both_themes_at_phone_width() -> None:
    text = ROOT_INDEX.read_text(encoding="utf-8")

    assert "<title>S.PKG CAPA AX 자료실</title>" in text
    assert "@media (prefers-color-scheme: dark)" in text
    assert '--font-body: "Malgun Gothic",' in text
    assert "minmax(min(300px, 100%), 1fr)" in text
    assert ".item:focus-visible" in text
    assert "<script" not in text


def test_the_list_links_are_relative_and_cover_the_catalog() -> None:
    collector = _LinkCollector()
    collector.feed(ROOT_INDEX.read_text(encoding="utf-8"))

    assert collector.hrefs == [entry.href for entry in _entries()]
    for href in collector.hrefs:
        parts = urlsplit(href)
        assert not parts.scheme and not parts.netloc and not href.startswith("/"), href


@pytest.mark.parametrize(
    "path",
    [ROOT_INDEX, *_site_pages()],
    ids=lambda path: path.relative_to(PROJECT_ROOT).as_posix(),
)
def test_a_page_asks_for_nothing_outside_and_has_no_cr(path: Path) -> None:
    data = path.read_bytes()

    assert b"\r" not in data, f"{path.name}: CR 을 뺀 뒤 복사합니다."
    assert not _OUTSIDE_REQUEST.findall(data.decode("utf-8"))


def test_the_outside_request_pattern_tells_a_request_from_written_text() -> None:
    assert _OUTSIDE_REQUEST.search('<script src="https://example.invalid/a.js">')
    assert _OUTSIDE_REQUEST.search("<link href=//example.invalid/a.css>")
    assert _OUTSIDE_REQUEST.search("background: url('http://example.invalid/a.png')")
    assert _OUTSIDE_REQUEST.search('<img srcset="https://example.invalid/a.png 1x">')
    assert _OUTSIDE_REQUEST.search('<img srcset="a.png 1x, //example.invalid/b.png 2x">')
    assert _OUTSIDE_REQUEST.search('<video poster="https://example.invalid/a.png">')
    assert _OUTSIDE_REQUEST.search('@import "https://example.invalid/a.css";')
    assert _OUTSIDE_REQUEST.search("@import'//example.invalid/a.css';")
    assert _OUTSIDE_REQUEST.search('fetch("https://example.invalid/a.json")')
    assert _OUTSIDE_REQUEST.search("import(`https://example.invalid/a.js`)")
    assert not _OUTSIDE_REQUEST.search("<code>http://localhost:8510</code>")
    assert not _OUTSIDE_REQUEST.search('createElementNS("http://www.w3.org/2000/svg", "g")')
    assert not _OUTSIDE_REQUEST.search("src:url(data:font/woff2;base64,AAAA)")
    assert not _OUTSIDE_REQUEST.search('<img srcset="a.png 1x, b.png 2x">')
    assert not _OUTSIDE_REQUEST.search('<img srcset="data:image/png;base64,AA//BB 1x">')
    assert not _OUTSIDE_REQUEST.search('@import "a.css";')
    assert not _OUTSIDE_REQUEST.search("fetch(t).then(i => i.arrayBuffer())")
    assert not _OUTSIDE_REQUEST.search('fetch("data.json")')
    assert not _OUTSIDE_REQUEST.search('import("./a.js")')


@pytest.mark.parametrize(
    "path",
    [ROOT_INDEX, *(page for page in _site_pages() if page != DECK)],
    ids=lambda path: path.relative_to(PROJECT_ROOT).as_posix(),
)
def test_a_page_keeps_the_browser_from_asking_the_site_root_for_an_icon(path: Path) -> None:
    """선언이 없으면 브라우저가 저장소 경로 밖 `/favicon.ico` 를 불러 404 를 남긴다.

    덱은 쇼케이스 복사본이라 CR 말고는 손대지 않는다 — 쇼케이스 다음 빌드 때 넣는다.
    """
    assert '<link rel="icon" href="data:,">' in path.read_text(encoding="utf-8")


def test_jekyll_stays_off() -> None:
    """Jekyll 이 돌면 사내에만 있는 md 의 구문 오류 하나로 자료실 빌드 전체가 실패한다."""
    assert NO_JEKYLL.read_bytes() == b""


def test_the_catalog_has_no_cr() -> None:
    assert b"\r" not in CATALOG_PATH.read_bytes()


def test_the_deck_stays_a_plain_copy_with_no_link_back() -> None:
    """덱은 쇼케이스 `contest/dist/capa-contest.html` 의 복사본이다 — CR 만 빼고 그대로 둔다."""
    text = DECK.read_bytes().decode("utf-8")

    assert "<title>S.PKG CAPA 혁신대회</title>" in text
    assert "../../index.html" not in text


def test_the_guide_links_back_to_the_list_first() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    head = text[text.index('<header class="head">') : text.index("</header>")]
    back_link = '<a class="back" href="../../index.html">← 자료 목록</a>'

    assert head.index(back_link) < head.index("<h1>")


def test_the_guides_first_instruction_is_the_module_guides_block() -> None:
    guide = MODULE_GUIDE.read_text(encoding="utf-8")
    section = guide[guide.index("## 0. 에이전트에게 줄 첫 지시") :]
    expected = re.search(r"```text\n(.*?)\n```", section, re.DOTALL)
    assert expected is not None

    text = GUIDE.read_text(encoding="utf-8")
    chapter = text[text.index('id="ch3"') : text.index('id="ch4"')]
    block = re.search(r"<pre>(.*?)</pre>", chapter, re.DOTALL)
    assert block is not None

    assert html.unescape(block.group(1)) == expected.group(1)


def test_the_guides_code_blocks_are_the_colleague_guides_blocks() -> None:
    """글 원본을 고치고 HTML 을 빠뜨리면 동료가 옛 명령을 복사한다 — 차례까지 글자 그대로다."""
    source = COLLEAGUE_GUIDE.read_text(encoding="utf-8")
    fences = re.findall(r"^```[a-z]*\n(.*?)\n```$", source, re.DOTALL | re.MULTILINE)
    blocks = re.findall(r"<pre>(.*?)</pre>", GUIDE.read_text(encoding="utf-8"), re.DOTALL)

    assert fences
    assert [html.unescape(block) for block in blocks] == fences


def test_the_guide_does_not_say_the_internal_word() -> None:
    assert "사내" not in GUIDE.read_text(encoding="utf-8")


def test_the_deploy_set_carries_the_whole_site() -> None:
    wanted = {
        INDEX_NAME,
        NO_JEKYLL.name,
        f"{SITE_DIR_NAME}/{CATALOG_NAME}",
        *(entry.href for entry in _entries()),
    }

    shipped = deploy_set(tracked_files(PROJECT_ROOT))

    assert wanted <= set(shipped)
    assert not forbidden_entries(wanted)


def test_the_image_leaves_the_site_out() -> None:
    """앱은 자료실을 쓰지 않는다 — 이미지(`COPY . /project/`)에 싣지 않는다."""
    lines = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert f"{SITE_DIR_NAME}/" in lines


def test_the_agents_may_not_edit_the_site() -> None:
    """덱이 뿌리를 떠나 `Edit(/*.html)` 밖으로 나왔다 — 폴더를 따로 막아야 코어로 남는다."""
    template = json.loads(
        (PROJECT_ROOT / "docs" / "internal_claude_settings.json").read_text(encoding="utf-8")
    )

    assert f"Edit({SITE_DIR_NAME}/**)" in template["permissions"]["deny"]
    assert f'"Edit(/{SITE_DIR_NAME}/**)"' in MODULE_GUIDE.read_text(encoding="utf-8")
