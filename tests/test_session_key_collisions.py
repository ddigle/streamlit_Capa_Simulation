# Purpose: 세션 상태·위젯 키가 두 모듈에서 겹쳐 조용히 새는 것을 막는다.

"""**키가 겹쳐도 예외가 나지 않는다.**

Streamlit 의 세션 상태는 네임스페이스가 없다. 두 화면이 같은 키를 쓰면 git 은 깨끗이
합치고, 앱은 오류 없이 뜨고, 검증 4종도 전부 초록이다. 그런데 한쪽에서 고른 값이 다른
화면에 나타나거나, 한쪽이 위젯을 만들면서 다른 쪽이 넣어 둔 값을 덮는다. 병행 개발에서
가장 사후 수습이 어려운 종류라 `AGENTS.md` 14-5 가 규칙으로 두었는데, 검사가 없었다.

**키를 만드는 자리는 셋이다.** 셋 다 봐야 한다 — 하나라도 빼면 그 통로로 샌다.

1. 위젯의 `key="..."`
2. `*_KEY` 로 끝나는 모듈 최상위 문자열 상수 (이 저장소가 공유 키를 선언하는 방식이다)
3. `st.session_state["..."] = ...` 와 `st.session_state.setdefault("...", ...)`
   — **위젯이 없어 충돌해도 경고할 상대조차 없는 자리다.**

읽기(`st.session_state.get("...")`)는 보지 않는다. 남이 만든 키를 읽는 것은 충돌이 아니라
**공유 상수가 존재하는 이유** 그 자체다.

f-string 키(`f"{editor_key}_apply"` 등)는 넘겨받은 기준 키에서 파생되므로 여기서 풀지
않는다. 그 기준 키가 위 셋 중 하나로 잡히면 파생된 것들도 함께 갈린다.

**허용목록이 없다.** 이 검사를 넣을 때 세 축 모두 겹침이 0 이었다 — 예외를 하나라도 두는
순간 「겹치지 않는다」는 보장이 사라지므로, 걸리면 목록에 더하지 말고 키를 고친다.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KEY_CONSTANT_SUFFIX = "_KEY"


def _scanned_files() -> list[Path]:
    files = [PROJECT_ROOT / "app.py"]
    files += sorted((PROJECT_ROOT / "app_pages").glob("*.py"))
    files += sorted((PROJECT_ROOT / "src").rglob("*.py"))
    return files


def _is_session_state(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "session_state"
        and isinstance(node.value, ast.Name)
        and node.value.id == "st"
    )


def _string(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _definitions(path: Path) -> list[tuple[str, str]]:
    """이 파일이 **만드는** 키. `(키 값, 어떤 자리인지)` 로 돌려준다."""
    found: list[tuple[str, str]] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "key" and (value := _string(keyword.value)) is not None:
                    found.append((value, "위젯 key="))
            function = node.func
            if (
                isinstance(function, ast.Attribute)
                and function.attr == "setdefault"
                and _is_session_state(function.value)
                and node.args
                and (value := _string(node.args[0])) is not None
            ):
                found.append((value, "session_state.setdefault"))
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and _is_session_state(target.value)
                    and (value := _string(target.slice)) is not None
                ):
                    found.append((value, "session_state 대입"))

    # 최상위 `*_KEY` 상수. 함수 안의 지역 변수는 공유 선언이 아니므로 보지 않는다.
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        first = targets[0] if targets else None
        if not isinstance(first, ast.Name) or not first.id.endswith(KEY_CONSTANT_SUFFIX):
            continue
        if (value := _string(node.value)) is not None:
            found.append((value, f"{first.id} 상수"))

    return found


def test_no_session_key_is_defined_in_two_modules() -> None:
    owners: dict[str, dict[str, str]] = defaultdict(dict)
    for path in _scanned_files():
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        for value, where in _definitions(path):
            owners[value].setdefault(relative, where)

    assert owners, "키를 하나도 못 찾았습니다 — 이 검사가 헛돌고 있습니다."

    collisions = {value: places for value, places in owners.items() if len(places) > 1}
    if not collisions:
        return

    lines: list[str] = []
    for value, places in sorted(collisions.items()):
        lines.append(f"{value!r}")
        lines.extend(f"    {path} — {where}" for path, where in sorted(places.items()))

    raise AssertionError(
        "같은 세션 키를 두 모듈이 만듭니다. Streamlit 세션 상태에는 네임스페이스가 없어 "
        "**예외 없이 값이 새고**, 검증 4종도 전부 초록입니다. 고치는 법은 자리에 따라 "
        "다릅니다:\n"
        "  · 리터럴 둘 → 소유한 모듈에 `*_KEY` 상수를 두고 나머지는 import\n"
        "  · 리터럴 하나 + 상수 하나 → 리터럴 쪽이 그 상수를 import\n"
        "  · 상수 둘 → 같은 위젯을 두 번 선언한 것이다. 하나를 지운다\n"
        "허용목록에 더하지 마세요 — 예외가 하나 생기면 보장이 사라집니다.\n" + "\n".join(lines)
    )
