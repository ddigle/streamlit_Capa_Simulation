# Purpose: site/catalog.json 으로 GitHub Pages 첫 화면(뿌리 index.html)을 쓰고 어긋남을 검사한다.

"""자료실 첫 화면 만들기.

GitHub Pages 는 저장소 뿌리를 그대로 내보내고 저장소 하나에 주소 하나다. 그래서 한 사이트
안에서 자료를 폴더로 가른다 — 자료는 `site/<폴더>/index.html`, 목록 정본은 `site/catalog.json`,
첫 화면은 이 생성기가 쓰는 뿌리 `index.html` 이다. 프로젝트 사이트는 주소 앞에 하위 경로가
붙으므로 링크는 늘 상대 경로다.

사용:

    .venv/bin/python scripts/build_site_index.py          # 뿌리 index.html 을 쓴다
    .venv/bin/python scripts/build_site_index.py --check  # 다르면 실패한다(쓰지 않는다)

새 자료는 `site/<폴더>/index.html` 을 두고 `site/catalog.json` 에 한 줄을 더한 뒤 이것을 돌린다.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SITE_DIR_NAME = "site"
CATALOG_NAME = "catalog.json"
INDEX_NAME = "index.html"
SITE_TITLE = "S.PKG CAPA AX 자료실"

CATALOG_FIELDS = ("path", "title", "summary", "kind", "updated")
_FOLDER_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

_STYLE = """\
:root {
  --bg: #f3f5f4; --surface: #ffffff; --ink: #16201e; --muted: #56625e;
  --line: #d5ddda; --accent: #0f766e;
  --font-body: "Malgun Gothic", "맑은 고딕", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1514; --surface: #162020; --ink: #e2ebe8; --muted: #98a8a3;
    --line: #2a3936; --accent: #45b7aa;
    color-scheme: dark;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: var(--font-body); line-height: 1.5;
  padding: 48px max(16px, env(safe-area-inset-right, 0px)) 64px
    max(16px, env(safe-area-inset-left, 0px));
}
main { max-width: 880px; margin: 0 auto; display: grid; gap: 24px; }
h1 { margin: 0; font-size: clamp(24px, 4vw, 32px); font-weight: 700; line-height: 1.25; }
.shelf {
  list-style: none; margin: 0; padding: 0; display: grid; gap: 14px;
  grid-template-columns: repeat(auto-fill, minmax(min(300px, 100%), 1fr));
}
.shelf li { display: grid; min-width: 0; }
.item {
  display: grid; grid-template-rows: auto auto 1fr auto; gap: 6px; min-width: 0; padding: 18px;
  background: var(--surface); border: 1px solid var(--line); border-radius: 10px;
  color: inherit; text-decoration: none; word-break: keep-all; overflow-wrap: anywhere;
}
.item:hover { border-color: var(--accent); }
.item:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.kind { font-size: 12.5px; font-weight: 600; letter-spacing: .04em; color: var(--accent); }
.item h2 { margin: 0; font-size: 18px; font-weight: 700; line-height: 1.35; }
.item p { margin: 0; font-size: 14.5px; color: var(--muted); }
.item time {
  margin-top: 6px; font-size: 12.5px; color: var(--muted); font-variant-numeric: tabular-nums;
}
"""


@dataclass(frozen=True)
class CatalogEntry:
    """목록의 자료 한 칸."""

    path: str
    title: str
    summary: str
    kind: str
    updated: str

    @property
    def href(self) -> str:
        """뿌리에서 그 자료로 가는 상대 경로. `file://` 로 열어도 서게 파일까지 적는다."""
        return f"{SITE_DIR_NAME}/{self.path}/{INDEX_NAME}"


def _is_real_date(text: str) -> bool:
    if _ISO_DATE.fullmatch(text) is None:
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _entry_problems(number: int, item: object) -> list[str]:
    """목록 한 줄의 꼴 검사. 빈 목록이어야 그 줄을 항목으로 옮길 수 있다."""
    if not isinstance(item, dict):
        return [f"{number}번째 줄이 객체가 아닙니다."]
    problems = [
        f"{number}번째 줄의 {field} 칸이 비었거나 글자가 아닙니다."
        for field in CATALOG_FIELDS
        if not isinstance(item.get(field), str) or not item[field].strip()
    ]
    unknown = sorted(str(key) for key in item if key not in CATALOG_FIELDS)
    if unknown:
        problems.append(f"{number}번째 줄에 모르는 칸이 있습니다: {unknown}")
    if problems:
        return problems
    if _FOLDER_NAME.fullmatch(item["path"]) is None:
        problems.append(
            f"{number}번째 줄의 path 는 영문 소문자 · 숫자 · - 로 된 폴더 이름이어야 합니다: "
            f"{item['path']!r}"
        )
    if not _is_real_date(item["updated"]):
        problems.append(f"{number}번째 줄의 updated 는 YYYY-MM-DD 여야 합니다: {item['updated']!r}")
    problems.extend(
        f"{number}번째 줄의 {field} 칸은 한 줄이어야 합니다."
        for field in CATALOG_FIELDS
        if "\n" in item[field] or "\r" in item[field]
    )
    return problems


def parse_catalog(raw: object) -> tuple[list[CatalogEntry], list[str]]:
    """JSON 값을 항목으로 옮긴다. 꼴이 어긋난 줄은 빼고 그 까닭을 함께 돌려준다."""
    if not isinstance(raw, list) or not raw:
        return [], [f"{CATALOG_NAME} 은 한 줄 이상의 배열이어야 합니다."]
    entries: list[CatalogEntry] = []
    problems: list[str] = []
    for number, item in enumerate(raw, start=1):
        found = _entry_problems(number, item)
        if found:
            problems.extend(found)
        else:
            entries.append(CatalogEntry(**{field: item[field] for field in CATALOG_FIELDS}))
    return entries, problems


def load_catalog(path: Path) -> tuple[list[CatalogEntry], list[str]]:
    """목록 파일을 읽는다. 없거나 JSON 이 아니면 항목 없이 그 까닭을 돌려준다."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [], [f"{path.name} 파일을 읽지 못했습니다: {error}"]
    return parse_catalog(raw)


def catalog_problems(entries: Sequence[CatalogEntry], site_dir: Path) -> list[str]:
    """목록과 폴더의 어긋남 — 겹친 줄 · 페이지가 없는 줄 · 목록에 없는 폴더."""
    listed = [entry.path for entry in entries]
    problems = [
        f"{name} 이 목록에 두 번 있습니다."
        for name in sorted(set(listed))
        if listed.count(name) > 1
    ]
    problems.extend(
        f"{SITE_DIR_NAME}/{name}/{INDEX_NAME} 이 없습니다."
        for name in listed
        if not (site_dir / name / INDEX_NAME).is_file()
    )
    folders = sorted(child.name for child in site_dir.iterdir() if child.is_dir())
    problems.extend(
        f"{SITE_DIR_NAME}/{name}/ 이 {CATALOG_NAME} 에 없습니다."
        for name in folders
        if name not in listed
    )
    return problems


def _card(entry: CatalogEntry) -> str:
    escape = html.escape
    return (
        f'    <li><a class="item" href="{escape(entry.href)}">'
        f'<span class="kind">{escape(entry.kind)}</span>'
        f"<h2>{escape(entry.title)}</h2>"
        f"<p>{escape(entry.summary)}</p>"
        f'<time datetime="{escape(entry.updated)}">{escape(entry.updated)}</time>'
        "</a></li>"
    )


def render_index(entries: Sequence[CatalogEntry]) -> str:
    """첫 화면 HTML. 같은 목록이면 늘 같은 글자다 — 시각을 넣지 않는다."""
    cards = "\n".join(_card(entry) for entry in entries)
    return f"""\
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(SITE_TITLE)}</title>
<link rel="icon" href="data:,">
<style>
{_STYLE}</style>
</head>
<body>
<main>
  <h1>{html.escape(SITE_TITLE)}</h1>
  <ul class="shelf">
{cards}
  </ul>
</main>
</body>
</html>
"""


def main(argv: Sequence[str] | None = None, *, root: Path = PROJECT_ROOT) -> int:
    """성공 0 · 목록이 어긋나거나 `--check` 에서 첫 화면이 다르면 1."""
    parser = argparse.ArgumentParser(description="site/catalog.json 으로 뿌리 index.html 을 쓴다.")
    parser.add_argument("--check", action="store_true", help="쓰지 않고 다르면 실패한다")
    args = parser.parse_args(argv)

    site_dir = root / SITE_DIR_NAME
    entries, problems = load_catalog(site_dir / CATALOG_NAME)
    if not problems:
        problems = catalog_problems(entries, site_dir)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1

    rendered = render_index(entries)
    target = root / INDEX_NAME
    if args.check:
        # 바이트로 읽는다 — 글자로 읽으면 줄바꿈 변환이 CR 을 가린다.
        current = target.read_bytes() if target.is_file() else b""
        if current != rendered.encode("utf-8"):
            print(
                f"{INDEX_NAME} 이 {SITE_DIR_NAME}/{CATALOG_NAME} 과 다릅니다. "
                "scripts/build_site_index.py 를 돌려 함께 커밋합니다.",
                file=sys.stderr,
            )
            return 1
        print(f"자료 목록 맞음 — {len(entries)}개")
        return 0

    target.write_bytes(rendered.encode("utf-8"))
    print(f"{INDEX_NAME} 을 썼습니다 — 자료 {len(entries)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
