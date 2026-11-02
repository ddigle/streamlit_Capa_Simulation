# Purpose: 사내 모듈 뼈대(module.json·첫 화면·스모크 시험·README)를 modules/<id>/ 안에만 만든다.

"""사내 모듈 뼈대 만들기 — 새 모듈 등록은 앱 관리자의 승인 뒤에 한다.

담당자 클론(사내 PC, PowerShell — 저장소 뿌리에서):

    uv run --no-sync python scripts/new_module.py <id> --name "<모듈 이름>"
    uv run --no-sync python scripts/new_module.py demo_new --name "데모 새 모듈" --owner "데모 담당"

사외(개발 PC, WSL — 시험·견본용, 사외 저장소에는 `modules/` 를 두지 않는다):

    .venv/bin/python scripts/new_module.py demo_new --name "데모 새 모듈" --root <저장소 밖>/modules

선택: `--owner "<담당 역할>"`(기본 「담당 미정」 — 사람 이름·사번이 아니라 역할 이름) ·
`--title "<첫 화면 이름>"`(기본 `--name` — 첫 화면 이름은 24자까지라 `--name` 이 24자를 넘거나
Markdown 글자가 들면 함께 준다) · `--root <모듈 뿌리>`(기본 <이 트리>/modules — 이름이
`modules` 여야 한다. 도움 import `modules.<id>` 가 그 뿌리로 풀린다).

만드는 것은 `<뿌리>/<id>/` 안의 넷뿐이다 — `module.json`·`page.py`·`tests/test_<id>_smoke.py`·
`README.md`(UTF-8, LF). 선언은 런타임과 같은 검증(`module_registry.parse_manifest`)을 지나야 쓴다.
`data/modules/<id>/` 는 만들지 않는다(화면이 처음 쓸 때 생긴다). 만든 뼈대는 그대로
`check_module.py` 를 통과한다. 거절(종료 코드 2, 아무것도 쓰지 않음): id 규칙(소문자·숫자·밑줄 하나,
2 ~ 24자, 파이썬 예약어 아님) 밖 · 폴더가 이미 있음 · `--root` 이름이 `modules` 가 아님 · 이름·제목
규칙 밖(길이·Markdown 글자) · 제목이 코어 화면 이름이나 「현황 요약」 과 같음.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Final

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capa_simulation import module_registry, navigation  # noqa: E402

MODULES_FOLDER_NAME: Final = "modules"
DEFAULT_OWNER: Final = "담당 미정"
PAGE_FILE: Final = "page.py"
LINE_WIDTH: Final = 100
# 선언 검증이 첫 화면 이름 칸을 부르는 이름 — 거절 까닭에서 담당자가 친 옵션 이름으로 바꾼다.
TITLE_FIELD: Final = "pages[0].title"


def _width(text: str) -> int:
    """ruff 와 같은 줄 폭 — 넓은 글자(한글 등)는 2칸이다."""
    return sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in text)


def _literal(text: str) -> str:
    """ruff format 이 고치지 않을 글자 상수 — 큰따옴표만 들면 작은따옴표로 감싼다."""
    if '"' in text and "'" not in text:
        return "'" + text.replace("\\", "\\\\") + "'"
    return json.dumps(text, ensure_ascii=False)


def _purpose(text: str, fallback: str) -> str:
    line = f"# Purpose: {text}"
    return line if _width(line) <= LINE_WIDTH else f"# Purpose: {fallback}"


def manifest_text(module_id: str, *, name: str, owner: str, title: str) -> str:
    data = {
        "id": module_id,
        "name": name,
        "api": module_registry.API_MAJOR,
        "owner": owner,
        "enabled": True,
        "maturity": "L0",
        "description": "",
        "order": module_registry.DEFAULT_ORDER,
        "pages": [
            {
                "slug": "main",
                "file": PAGE_FILE,
                "title": title,
                "icon": module_registry.DEFAULT_PAGE_ICON,
                "order": 10,
            }
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def page_text(module_id: str, *, name: str, title: str) -> str:
    purpose = _purpose(
        f"{name} 사내 모듈의 첫 화면을 그린다.", f"사내 모듈 {module_id} 의 첫 화면을 그린다."
    )
    return f"""{purpose}

import streamlit as st

from capa_simulation import module_api as api

ctx = api.context(__file__)
api.page_header(
    ctx,
    {_literal(title)},
    description="이 화면이 무엇을 하는지 한 줄로 적습니다.",
)


def _greet() -> None:
    st.session_state[ctx.key("greeted")] = True


name = st.text_input("이름", key=ctx.key("name"))
st.button("인사", key=ctx.key("greet"), on_click=ctx.callback(_greet))
if name and st.session_state.get(ctx.key("greeted")):
    st.write(f"{{name}} 님, 반갑습니다.")
"""


def smoke_test_text(module_id: str, *, title: str) -> str:
    return f'''# Purpose: 사내 모듈 {module_id} 의 첫 화면이 빈 데이터 자리로 오류 없이 서는지 본다.

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[1] / "{PAGE_FILE}"
TITLE = {_literal(title)}


def test_first_page_renders_with_empty_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CAPA_MODULES_DATA_ROOT", str(tmp_path))
    app = AppTest.from_file(str(PAGE)).run(timeout=60)
    assert not app.exception
    assert [element.value for element in app.title] == [TITLE]
'''


def readme_text(module_id: str, *, name: str, owner: str, title: str) -> str:
    return f"""# {name}

- 무엇: (이 모듈이 하는 일을 한두 줄로 적습니다)
- 담당 역할: {owner}
- id: `{module_id}` · 성숙도 L0 Lab

## 화면

| 화면 | 파일 |
|---|---|
| {title} | `{PAGE_FILE}` |

이 모듈은 `docs/module_guide.md` 를 따른다.
"""


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="사내 모듈 뼈대를 modules/<id>/ 안에만 만든다(새 모듈은 앱 관리자 승인 뒤)"
    )
    parser.add_argument("id", help="모듈 id — 소문자·숫자·밑줄 하나, 2 ~ 24자")
    parser.add_argument(
        "--name",
        required=True,
        help="모듈 이름(1 ~ 30자 — 24자를 넘으면 --title 로 첫 화면 이름을 따로 준다)",
    )
    parser.add_argument("--owner", default=DEFAULT_OWNER, help="담당 역할 이름(사람 이름 아님)")
    parser.add_argument("--title", default=None, help="첫 화면 이름(기본 --name, 1 ~ 24자)")
    parser.add_argument(
        "--root", default=None, help="모듈 뿌리(기본 <이 트리>/modules — 이름이 modules 여야 한다)"
    )
    return parser.parse_args(argv)


def option_reason(reason: str, *, title_given: bool) -> str:
    """선언 검증 까닭의 칸 이름을 친 옵션 이름으로 바꾼다 — 첫 화면 이름은 `--title` 이고, 주지
    않았으면 `--name` 이 그 자리에 들어가므로 `--title` 을 함께 주라고 안내한다."""
    if TITLE_FIELD in reason:
        if title_given:
            return reason.replace(TITLE_FIELD, "--title")
        return (
            reason.replace(TITLE_FIELD, "--name(--title 을 주지 않아 첫 화면 이름으로 씀)")
            + ' — `--title "<첫 화면 이름>"` 을 함께 줍니다'
        )
    for field, option in (("name", "--name"), ("owner", "--owner")):
        if reason.endswith(f": {field}"):
            return reason.removesuffix(field) + option
    return reason


def _refuse(message: str) -> int:
    print(f"만들지 않았습니다 — {message}", file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    try:
        args = _parse(argv)
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else 2
    module_id: str = args.id
    name: str = args.name
    owner: str = args.owner
    title: str = args.title if args.title is not None else name
    if not module_registry.is_valid_module_id(module_id):
        return _refuse(
            f"id `{module_id}` 가 규칙(소문자·숫자·밑줄 하나, 2 ~ 24자, 파이썬 예약어 아님)에 "
            "맞지 않습니다"
        )
    root = Path(args.root).resolve() if args.root else PROJECT_ROOT / MODULES_FOLDER_NAME
    if root.name != MODULES_FOLDER_NAME:
        return _refuse(
            f"--root 의 폴더 이름은 {MODULES_FOLDER_NAME} 여야 합니다"
            f"(`modules.<id>` 가 그 뿌리로 풀린다): {root.name}"
        )
    folder = root / module_id
    if folder.exists():
        return _refuse(f"폴더가 이미 있습니다: {MODULES_FOLDER_NAME}/{module_id}")
    reserved = {*navigation.core_page_titles(), module_registry.GROUP_MAIN_TITLE}
    if title in reserved:
        return _refuse(f"화면 이름 「{title}」 은 코어가 쓰는 이름입니다 — 다른 이름을 고릅니다")
    manifest = manifest_text(module_id, name=name, owner=owner, title=title)
    try:
        module_registry.parse_manifest(manifest.encode("utf-8"), folder_name=module_id)
    except module_registry.ManifestError as error:
        reason = option_reason(error.reason, title_given=args.title is not None)
        return _refuse(f"선언 규칙 — {reason}")
    files = {
        module_registry.MANIFEST_NAME: manifest,
        PAGE_FILE: page_text(module_id, name=name, title=title),
        f"tests/test_{module_id}_smoke.py": smoke_test_text(module_id, title=title),
        "README.md": readme_text(module_id, name=name, owner=owner, title=title),
    }
    created_root = not root.exists()
    try:
        for rel, text in files.items():
            path = folder / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
    except OSError as error:
        shutil.rmtree(folder, ignore_errors=True)
        if created_root:
            shutil.rmtree(root, ignore_errors=True)
        return _refuse(f"파일을 쓰지 못했습니다 — {type(error).__name__}")
    print(f"사내 모듈 뼈대를 만들었습니다 — {MODULES_FOLDER_NAME}/{module_id}/")
    for rel in files:
        print(f"  {MODULES_FOLDER_NAME}/{module_id}/{rel}")
    root_option = "" if args.root is None else f" --root {args.root}"
    print("다음 할 일:")
    print(
        "  1) 앱 관리자의 승인을 받는다(새 모듈 등록 — 커밋 본문과 PR 본문에 "
        "`승인: 앱 관리자 <YYYY-MM-DD>`)"
    )
    print(f"  2) uv run --no-sync python scripts/check_module.py {module_id}{root_option}")
    print(
        f"  3) 자기 가지(module/{module_id}/<주제>)에서 "
        f"git add {MODULES_FOLDER_NAME}/{module_id} → "
        f'git commit -m "module({module_id}): 새 모듈 뼈대" -m "승인: 앱 관리자 <YYYY-MM-DD>"'
    )
    print(
        "  4) 담당자가 그 가지를 푸시하고 사내 GitHub 에서 PR 을 연다 — 앱 관리자가 점검한 뒤 "
        "합친다(지침서 8-2)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
