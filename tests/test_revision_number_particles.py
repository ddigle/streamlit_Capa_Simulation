# Purpose: 화면 글에서 리비전 번호(rN) 뒤 조사를 띄우지 않고 바로 붙였는지 앱 코드 전체에서 지킨다.

"""리비전 번호 뒤 조사는 번호에 붙인다 — 「r7이 더 새롭습니다」·「r1을 불러왔습니다」.

같은 화면의 글이 「r7이 더 새롭습니다」·「r1의 일정으로 되돌려 r3을 저장했습니다」 처럼 붙이는데,
몇 자리만 「「셋업 B」 r1 을 만들었습니다」·「지금 보는 r6 에서는」·「r7 의 이름표입니다」 처럼 띄워
철자가 어색했다(2026-10-31 E2E). 바뀌는 조사(을·를·은·는·가·으로·로·과·와)는 값이면
`korean_particle` 로 고르고(`tests/test_particle_sites.py`), 이 시험은 띄운 꼴만 본다.

- 앱 코드(`app.py`·`app_pages`·`src`)를 AST 로 훑어, 문장으로 선 글(docstring 등)을 뺀 글과
  f-string 에서 `r` + 숫자나 끼운 값(「r1」·「r{n}」) 뒤 한 칸 띄운 조사를 찾는다.
- **한 칸 띄운 「이」** 는 지시어(「r7 이 리비전」)와 갈리지 않아 잡지 않는다.
- 번호를 이름에 든 값(`latest = f"r{n}"` 뒤 「{latest} 의」)은 값 이름으로 알 수 없어 잡지 않는다 —
  그 글을 단언하는 화면 시험이 지킨다.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# f-string 의 끼운 값 자리 — 사람이 쓰지 않는 글자 하나로 바꿔 훑는다.
_VALUE = ""
_PARTICLES = "을|를|은|는|가|으로|로|과|와|의|에|에서|에서는|에는|도|만|부터|까지"
_SPACED = re.compile(rf"(?<![A-Za-z0-9_])r(?:{_VALUE}|\d+) (?:{_PARTICLES})(?=[\s.,·—:;)」』!?]|$)")


def _app_files() -> Iterator[Path]:
    yield PROJECT_ROOT / "app.py"
    for folder in ("app_pages", "src"):
        yield from sorted((PROJECT_ROOT / folder).rglob("*.py"))


def _texts(tree: ast.AST) -> Iterator[tuple[int, str]]:
    """문장으로 선 글을 뺀 글(f-string 은 끼운 값을 `_VALUE` 로)과 그 줄."""
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            skipped.add(id(node.value))
        elif isinstance(node, ast.JoinedStr):
            skipped.update(id(part) for part in node.values)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            yield (
                node.lineno,
                "".join(
                    str(part.value) if isinstance(part, ast.Constant) else _VALUE
                    for part in node.values
                ),
            )
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skipped
        ):
            yield node.lineno, node.value


def _offenders(source: str, name: str) -> list[str]:
    return [
        f"{name}:{line}: {match.group(0).replace(_VALUE, '{…}')!r}"
        for line, text in _texts(ast.parse(source))
        for match in _SPACED.finditer(text)
    ]


def test_no_particle_is_spaced_after_a_revision_number() -> None:
    offenders = [
        hit
        for path in _app_files()
        for hit in _offenders(path.read_text(encoding="utf-8"), str(path.relative_to(PROJECT_ROOT)))
    ]
    assert not offenders, "리비전 번호 뒤 조사는 붙입니다:\n" + "\n".join(offenders)


@pytest.mark.parametrize(
    "source",
    [
        'f"「{name}」 r1 을 만들었습니다"',
        'f"지금 보는 r{basis.revision_no} 에서는 잠갔습니다"',
        'f"r{revision.revision_no} 의 이름표입니다"',
        'st.caption("r1 로 옮깁니다.")',
        'f"{name} r{latest_no} 에 다른 배치가 저장됐습니다"',
        'x = ("…시나리오 「" f"{made}」 " "r1 을 만들었습니다")',
    ],
)
def test_the_guard_catches_a_spaced_particle(source: str) -> None:
    assert _offenders(source, "<시험>")


@pytest.mark.parametrize(
    "source",
    [
        'f"「{name}」 r1을 만들었습니다"',
        'f"{latest}{subject_particle(latest)} 더 새롭습니다 — 지금 보는 r{n}에서는"',
        'f"r{n} 이 리비전의 일정"',
        'f"r{n} · 공식 v3"',
        'f"Dr{n} 의 값"',
        '"""docstring 의 r1 을 은 화면 글이 아니다."""',
        'f"Per {count} 의 값"',
    ],
)
def test_the_guard_leaves_attached_or_unrelated_forms(source: str) -> None:
    assert not _offenders(source, "<시험>")
