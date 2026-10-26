# Purpose: 끼운 값 바로 뒤에 못박은 조사가 없고 상수 뒤 조사는 그 상수의 끝소리와 맞는지 지킨다.

"""값 뒤 조사는 `services/korean_particle.py` 한 길로 고른다(AGENTS 8장).

조사 도우미가 생긴 뒤에도(2026-10-05 E2E) 쓰는 것이 자리마다 고르는 일이라 회차마다 고친 자리만
고쳐지고 같은 꼴이 다른 파일에서 다시 나왔다(2026-10-25 E2E 1·2회차 — 「공식 v4 으로」·「4 을」·
「27-06 가」). 이 시험이 그 꼴을 앱 코드(`app.py`·`app_pages`·`src`) 전체에서 막는다. 허용 목록은
없다. `scripts/` 출력은 훑지 않는다 — 리뷰 몫이다(AGENTS 8장).

- **f-string** — 앱 코드를 AST 로 훑어 끼운 값(`FormattedValue`) 바로 뒤 글이(닫는 따옴표·낫표·
  굵게·백틱·백슬래시·「]」 뒤 — 도우미가 끝소리를 볼 때 건너뛰는 기호에서 「)」 를 뺀 것) 고정
  조사(을·를·은·는·이·가·으로·로·과·와)로 시작하면 실패한다. 붙은 꼴(「{x}을」)과 한 칸 띄운 꼴
  (「{x} 을」), 손으로 박은 갈래 꼴(「{x}은(는)」·「**{x}** 이(가)」)을 모두 본다.
- **괄호** — 괄호 뒤 조사는 괄호 앞 낱말에 붙는다. 그 낱말이 끼운 값이면(「{id}({name}) 가」·
  「{id}(고정 글)는」) 괄호 뒤 글을 같은 규칙으로 보고, 고정 글이면(「최신(r{n})이」) 뺀다.
- **빼는 것** — 앞 값이 `*_particle(…)` 호출인 꼴(「{with_topic_particle(x)} 이 기본값과」 — 뒤
  「이」 는 지시어다). **한 칸 띄운 「이」** 는 지시어(「{x} 이 시나리오」)와 갈리지 않아 잡지
  않는다 — 진짜 조사였던 넷(bigdataquery 모듈 이름·스냅샷 마이그레이션 버전·제약 시뮬레이션 공정·
  모듈 행 칸)은 고쳤고, 그 꼴의 재발은 리뷰 몫이다.
- **상수 뒤 조사** — 값이 ALL_CAPS 상수(이름·모듈 속성)이면 고정 조사를 두어도 된다. 대신 그 모듈을
  불러 실제 값(서식 지정까지 입힌 글)으로 `korean_particle` 이 같은 조사를 고르는지 단언한다 — 상수
  글이 바뀌면 이 시험이 잡는다. 도우미가 읽지 못하는 끝(영문)은 `_READINGS` 의 읽기로 견준다.
- **`str.format`·`%s` 틀** — f-string 이 아닌 글(문장으로 선 글·docstring 빼고)의 `{…}`·`%s` 바로
  뒤(괄호를 사이에 둔 꼴 포함) 고정 조사와 갈래 꼴.
- **JS** — `src/**/*.js` 의 `${…}` 바로 뒤(괄호를 사이에 둔 꼴 포함) 고정 조사와 갈래 꼴. 괄호
  앞 낱말이 고정 글인 꼴(「최신(r${n})이」)은 `${…}` 가 괄호 안이라 걸리지 않는다. 배치 편집기는
  `editor.js` 의 `withJosa` 를 쓰고, 그 표가 파이썬과 같은 답을 내는지 node 로 대조한다
  (node·bun 이 없으면 건너뛰고 CI 에서는 실패 — `test_space_module_group._node`).
"""

from __future__ import annotations

import ast
import importlib
import math
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, NamedTuple

import pandas as pd
import pytest
from test_space_module_group import _node

from capa_simulation.components import space_layout_editor
from capa_simulation.io import object_storage
from capa_simulation.page_bootstrap import schema_ahead_message
from capa_simulation.page_tabs_state import LIMIT_NOTICE, MAX_TABS, limit_notice
from capa_simulation.persistence._migration_core import SchemaAheadOfCode
from capa_simulation.persistence._sql_helpers import required_text
from capa_simulation.services import (
    display_order_editor,
    equipment_validation,
    month_filter,
    securement_threshold,
    space_layout_edit,
)
from capa_simulation.services.floor_layout_mark import mark_box
from capa_simulation.services.floor_layout_profile import normalize_canvas_size
from capa_simulation.services.frame_contracts import normalize_month_column
from capa_simulation.services.korean_particle import (
    _SKIPPED_TAIL,
    direction_particle,
    object_particle,
    subject_particle,
    topic_particle,
    with_direction_particle,
    with_object_particle,
    with_subject_particle,
    with_topic_particle,
)
from capa_simulation.services.monthly_amount import prepare_monthly_amounts
from capa_simulation.services.object_storage_manifest import pointer_from_json
from capa_simulation.services.simulation_cache import _require_assumed, _require_official

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PARTICLES = "을|를|은|는|이|가|으로|로|과|와"
_SPACED_PARTICLES = "을|를|은|는|가|으로|로|과|와"
_HEDGED = r"\(으\)로|을\(를\)|은\(는\)|이\(가\)"
# 조사 뒤 — 띄움·문장 부호·닫는 기호·글 끝(JS 는 템플릿을 닫는 백틱).
_BOUNDARY = r"(?=[\s.,·—:;)」』!?`]|$)"
# 값을 감싸 닫는 기호 — 도우미가 끝소리를 볼 때 건너뛰는 기호에서 「)」(아래 괄호 규칙이 따로
# 본다)를 뺀 것. 도우미가 건너뛰는 기호를 늘리면 그물도 따라 넓어진다.
_CLOSER_CHARS = _SKIPPED_TAIL.replace(")", "")
_CLOSERS = f"[{re.escape(_CLOSER_CHARS)}]*"
# 값 뒤에 괄호를 사이에 둔 꼴(「{a}({b}) 가」) — 조사는 괄호 앞 값에 붙는다.
_PAREN_GAP = rf"(?:\([^()]*\){_CLOSERS})?"
# 끼운 값 바로 뒤 글의 머리 — 붙은 꼴, 한 칸 띄운 꼴(이 빼고), 손으로 박은 갈래 꼴.
_FIXED_HEAD = re.compile(
    rf"^{_CLOSERS}(?:(?:{_PARTICLES})|\s(?:{_SPACED_PARTICLES})){_BOUNDARY}"
    rf"|^{_CLOSERS}\s?(?:{_HEDGED})"
)
# 상수 뒤 고정 조사. 띄운 「이」 는 지시어와 갈리지 않아 붙은 꼴만 본다.
_CONSTANT_HEAD = re.compile(
    rf"^{_CLOSERS}(?:(?P<attached>{_PARTICLES})|\s(?P<spaced>{_SPACED_PARTICLES})){_BOUNDARY}"
)
# 틀 자리 뒤 — 붙은 꼴·띄운 꼴(이 빼고)·갈래 꼴. 괄호를 사이에 둔 꼴도 본다.
_TAIL = (
    rf"{_CLOSERS}{_PAREN_GAP}"
    rf"(?:(?:{_PARTICLES}|\s(?:{_SPACED_PARTICLES})){_BOUNDARY}|\s?(?:{_HEDGED}))"
)
_TEMPLATE_SITE = re.compile(rf"(?:\{{[^{{}}]*\}}|%[sdr]){_TAIL}")
_JS_SITE = re.compile(rf"\$\{{[^}}]*\}}{_TAIL}")
_JOSA_BLOCK = re.compile(r"// <josa>\n(?P<body>.*?)\n\s*// </josa>", re.S)

# 도우미가 읽지 못하는 끝(영문)으로 끝나는 상수의 끝 낱말 읽기. 상수 글이 바뀌면 이 표에서 빠져
# 시험이 실패한다 — 새 글의 읽기를 적거나 조사를 도우미로 고른다.
_READINGS = {
    "Area Code": "코드",
    "CAPA_ARTIFACTORY_USER": "유저",
    "HBM·EDP": "이디피",
}


def _comitative_particle(word: str) -> str:
    """`과/와` — 상수 자리뿐이라 도우미 함수를 두지 않고 주격 조사의 받침 판단을 빌린다."""
    return {"이": "과", "가": "와"}.get(subject_particle(word), "과(와)")


_CHOOSER: dict[str, Callable[[str], str]] = {
    "을": object_particle,
    "를": object_particle,
    "은": topic_particle,
    "는": topic_particle,
    "이": subject_particle,
    "가": subject_particle,
    "으로": direction_particle,
    "로": direction_particle,
    "과": _comitative_particle,
    "와": _comitative_particle,
}


def _source_files() -> list[Path]:
    return [
        PROJECT_ROOT / "app.py",
        *sorted((PROJECT_ROOT / "app_pages").glob("*.py")),
        *sorted((PROJECT_ROOT / "src").rglob("*.py")),
    ]


def _relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _is_constant(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        name = node.id
    elif isinstance(node, ast.Attribute):
        name = node.attr
    else:
        return False
    stripped = name.strip("_")
    return bool(stripped) and stripped.isupper()


def _is_particle_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
    return isinstance(name, str) and name.endswith("_particle")


class _ValueSite(NamedTuple):
    """f-string 에 끼운 값과 그 바로 뒤 글. `parts`·`slot`(값의 자리)로 괄호 앞 낱말을 찾는다."""

    value: ast.FormattedValue
    text: str
    line: int
    parts: list[ast.expr]
    slot: int


def _value_sites(tree: ast.AST) -> Iterator[_ValueSite]:
    """f-string 안에서 끼운 값과 그 바로 뒤 글(·줄 번호)의 쌍."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        for index, (value, following) in enumerate(zip(node.values, node.values[1:], strict=False)):
            if (
                isinstance(value, ast.FormattedValue)
                and isinstance(following, ast.Constant)
                and isinstance(following.value, str)
            ):
                yield _ValueSite(value, following.value, following.lineno, node.values, index)


def _value_opens_the_parenthesis(parts: list[ast.expr], index: int) -> bool:
    """`parts[index]` 뒤 「)」 의 짝 「(」 바로 앞(공백·닫는 기호 건너)이 끼운 값인가.

    괄호 뒤 조사는 괄호 앞 낱말에 붙는다 — 그 낱말이 끼운 값이면 조사도 그 값으로 골라야 한다
    (「{id}({name}) 가」). 고정 글이면(「최신(r{n})이」) 조사는 그 글에 맞춘 것이다.
    """
    depth = 0
    for position in range(index - 1, -1, -1):
        part = parts[position]
        if not (isinstance(part, ast.Constant) and isinstance(part.value, str)):
            continue
        text = part.value
        for offset in range(len(text) - 1, -1, -1):
            if text[offset] == ")":
                depth += 1
            elif text[offset] == "(" and depth:
                depth -= 1
            elif text[offset] == "(":
                if text[:offset].rstrip().rstrip(_CLOSER_CHARS):
                    return False
                return position > 0 and isinstance(parts[position - 1], ast.FormattedValue)
    return False


def _after_leading_parenthesis(text: str) -> str | None:
    """「(」 로 시작하는 글에서 그 괄호를 닫은 뒤의 글. 이 글 안에서 닫히지 않으면 `None`."""
    depth = 0
    for offset, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if not depth:
                return text[offset + 1 :]
    return None


def _particle_heads(site: _ValueSite) -> list[str]:
    """고정 조사가 붙었는지 볼 글 — 값 바로 뒤, 괄호를 사이에 두었으면 그 괄호 뒤."""
    if site.text.startswith(")"):
        return [site.text[1:]] if _value_opens_the_parenthesis(site.parts, site.slot) else []
    heads = [site.text]
    if site.text.startswith("("):
        rest = _after_leading_parenthesis(site.text)
        heads += [] if rest is None else [rest]
    return heads


def _site(path: Path, value: ast.FormattedValue, text: str, line: int) -> str:
    return f"{_relative(path)}:{line}: {{{ast.unparse(value.value)}}}{text[:24]!r}"


def _trees() -> Iterator[tuple[Path, ast.Module]]:
    for path in _source_files():
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def _fixed_particle_sites(tree: ast.AST) -> Iterator[_ValueSite]:
    """값 뒤에 못박은 조사 자리(상수 뒤 조사는 아래 상수 시험 몫이라 뺀다)."""
    for site in _value_sites(tree):
        if _is_particle_call(site.value.value):
            continue
        if not any(_FIXED_HEAD.match(head) for head in _particle_heads(site)):
            continue
        if _is_constant(site.value.value) and _CONSTANT_HEAD.match(site.text):
            continue  # 아래 상수 시험이 실제 값으로 견준다.
        yield site


def test_no_fixed_particle_follows_an_interpolated_value() -> None:
    """런타임 값 뒤 조사는 `with_*_particle`·`*_particle` 로 고른다 — 붙은·띄운·갈래 꼴 모두."""
    offenders = [
        _site(path, site.value, site.text, site.line)
        for path, tree in _trees()
        for site in _fixed_particle_sites(tree)
    ]
    assert not offenders, "값 뒤에 못박은 조사 — korean_particle 로 고르세요:\n" + "\n".join(
        offenders
    )


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(PROJECT_ROOT / "src").with_suffix("").parts)


def _rendered(value: ast.FormattedValue, namespace: dict[str, Any]) -> tuple[object, str]:
    """상수 값과 f-string 이 그 자리에 찍는 글(변환·서식 지정까지)."""
    raw = eval(ast.unparse(value.value), namespace)  # 저장소 소스의 상수 이름·속성만 푼다
    conversions: dict[int, Callable[[object], object]] = {115: str, 114: repr, 97: ascii}
    converted = conversions[value.conversion](raw) if value.conversion in conversions else raw
    spec = ""
    if value.format_spec is not None:
        assert isinstance(value.format_spec, ast.JoinedStr)
        parts = value.format_spec.values
        assert all(isinstance(part, ast.Constant) for part in parts), ast.unparse(value)
        spec = "".join(str(part.value) for part in parts if isinstance(part, ast.Constant))
    return raw, format(converted, spec)


def _constant_sites() -> Iterator[tuple[Path, ast.FormattedValue, str, int, str]]:
    for path, tree in _trees():
        for site in _value_sites(tree):
            match = _CONSTANT_HEAD.match(site.text)
            if match and _is_constant(site.value.value):
                particle = match["attached"] or match["spaced"]
                yield path, site.value, site.text, site.line, particle


def test_constants_before_a_fixed_particle_end_in_the_matching_sound() -> None:
    """ALL_CAPS 상수 뒤 고정 조사는 그 상수의 실제 글로 `korean_particle` 이 고르는 조사와 같다."""
    sites = list(_constant_sites())
    assert sites, "상수 뒤 조사 자리를 하나도 못 찾았다 — 훑는 규칙이 망가졌다"
    wrong: list[str] = []
    for path, value, text, line, particle in sites:
        site = _site(path, value, text, line)
        assert path.is_relative_to(PROJECT_ROOT / "src"), f"{site}: 페이지 상수는 도우미로 고른다"
        namespace = vars(importlib.import_module(_module_name(path)))
        raw, rendered = _rendered(value, namespace)
        choose = _CHOOSER[particle]
        chosen = choose(rendered)
        if "(" in chosen:
            reading = _READINGS.get(str(raw))
            assert reading is not None, (
                f"{site}: 끝을 못 읽는 {rendered!r} — _READINGS 에 읽기를 적는다"
            )
            chosen = choose(reading)
        if chosen != particle:
            wrong.append(f"{site}: {rendered!r} 뒤는 「{chosen}」")
    assert not wrong, "상수 글과 조사가 어긋났다:\n" + "\n".join(wrong)


def _bare_strings(tree: ast.Module) -> Iterator[ast.Constant]:
    """f-string 조각도, 문장으로 선 글(docstring)도 아닌 글 상수."""
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            skipped.update(id(part) for part in ast.walk(node))
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            skipped.add(id(node.value))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skipped
        ):
            yield node


def test_no_fixed_particle_follows_a_format_placeholder() -> None:
    """`str.format` 틀의 `{name}`·로그 틀의 `%s` 뒤도 같다 — 값을 넣는 쪽이 도우미로 고른다."""
    offenders = [
        f"{_relative(path)}:{node.lineno}: {match.group(0)!r}"
        for path, tree in _trees()
        for node in _bare_strings(tree)
        for match in _TEMPLATE_SITE.finditer(str(node.value))
    ]
    assert not offenders, "틀 자리 뒤에 못박은 조사:\n" + "\n".join(offenders)


def test_no_fixed_particle_follows_a_js_template_value() -> None:
    """`${…}` 뒤 조사는 `withJosa` 로 고른다."""
    offenders = [
        f"{_relative(path)}:{number}: {line.strip()[:80]}"
        for path in sorted((PROJECT_ROOT / "src").rglob("*.js"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _JS_SITE.search(line)
    ]
    assert not offenders, "JS 템플릿 값 뒤에 못박은 조사:\n" + "\n".join(offenders)


def test_the_guard_catches_every_fixed_form() -> None:
    """그물 자체 — 고친 꼴은 걸리고 남겨 둔 꼴(괄호 뒤·지시어 「이」·도우미 뒤)은 걸리지 않는다."""
    caught = ["을 저장", "를", "」은 ", "** 가 ", " 로 고정", "과 함께", "은(는) 비어", " 이(가) "]
    caught += ["'을 지웠", '"을 지웠', "]는", "`이 "]
    passed = [" 이 시나리오", "의 칸", "개를", "이다", "으로써", "로부터", " 이상"]
    assert all(_FIXED_HEAD.match(text) for text in caught)
    assert not any(_FIXED_HEAD.match(text) for text in passed)
    templates = [
        "회차 %s 가 멈췄습니다",
        "「{name}」는",
        "「{label}」을(를) 열려면",
        "'{x}'을",
        "{a}({b}) 가",
    ]
    assert all(_TEMPLATE_SITE.search(text) for text in templates)
    assert not any(_TEMPLATE_SITE.search(text) for text in ["{list}\n이 화면을", "최신(r{n})이"])
    js_caught = ["`${id} 는 이미`", "`${w}이 되어`", "`'${x}'을 지웠`", "`${a}(${b})는`"]
    js_caught += ["`${a}(레이아웃표시 N)는 그리지`", "`${x}을(를)`"]
    assert all(_JS_SITE.search(text) for text in js_caught)
    js_passed = ["`${withJosa(id, '은')} 이미`", "`최신(r${n})이`", "`(${n}개)를`"]
    assert not any(_JS_SITE.search(text) for text in js_passed)


def _fixed_in(source: str) -> list[str]:
    """한 줄 소스의 f-string 에서 그물이 잡는 자리(끼운 값 + 뒤 글)."""
    return [
        f"{ast.unparse(site.value.value)}|{site.text}"
        for site in _fixed_particle_sites(ast.parse(source))
    ]


@pytest.mark.parametrize(
    "source",
    [
        'f"도면 요소 {mark_id}({name}) 가 캔버스"',
        'f"{a} ({b})이 바뀜"',
        'f"「{a}」({b})는"',
        'f"{a}({b}·{c})를"',
        'f"{a}(고정 글) 가"',
        'f"{a}(r{n}) 가"',
        "f\"'{name}'을 지웠습니다\"",
        "f'\"{name}\"을 지웠습니다'",
    ],
)
def test_the_guard_reads_the_word_before_a_parenthesis(source: str) -> None:
    """괄호 뒤 조사는 괄호 앞 낱말에 붙는다 — 그 낱말이 끼운 값이면 괄호 뒤 고정 조사도 잡는다."""
    assert _fixed_in(source)


@pytest.mark.parametrize(
    "source",
    [
        'f"최신(r{n})이 기본"',
        'f"최신 ({n}) 가"',
        'f"({n}) 가"',
        'f"{a}({b}){subject_particle(a)} 캔버스"',
        'f"{a}(r{n}) {subject_particle(a)}"',
        'f"{a}({b})"',
    ],
)
def test_the_guard_leaves_a_parenthesis_after_fixed_text(source: str) -> None:
    """괄호 앞이 고정 글이거나 조사를 도우미로 고른 꼴은 지나간다."""
    assert not _fixed_in(source)


_JS_WORDS = [
    "시나리오",
    "복제본",
    "서울",
    "부산",
    "r1",
    "r3",
    "r6",
    "10",
    "4.5",
    "2026-10-26",
    "85%",
    "「주요 공정」",
    "**복제본**",
    "WB\\(2\\)",
    "Customer",
    "C1-3F",
    "C2 2F",
    "Xsize",
    "「투자Capa」",
    "설비 DB",
    "Kea",
    "Staff",
    "연결 층",
    "  공백  ",
    "",
    "\U0001f600",
]
_PY_WITH = {
    "을": with_object_particle,
    "은": with_topic_particle,
    "이": with_subject_particle,
    "으로": with_direction_particle,
}
_JS_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
%s
process.stdout.write(JSON.stringify(input.cases.map(([word, kind]) => withJosa(word, kind))))
"""


def test_the_editor_josa_matches_the_python_helper() -> None:
    """`editor.js` 의 `withJosa` 는 파이썬 `with_*_particle` 과 같은 글을 낸다(소수·`%`·escape)."""
    script = (space_layout_editor._ASSETS / "editor.js").read_text(encoding="utf-8")
    block = _JOSA_BLOCK.search(script)
    assert block, "editor.js 의 // <josa> 구획을 못 찾았다"
    cases = [[word, kind] for word in _JS_WORDS for kind in _PY_WITH]
    result: Any = _node(_JS_RUNNER % block.group("body"), {"cases": cases})
    assert list(result) == [_PY_WITH[kind](word) for word, kind in cases]


# ---------------------------------------------------- 고친 자리 — 받침 있는·없는 이름 둘


def _raised(call: Callable[[], object]) -> str:
    with pytest.raises((ValueError, TypeError, KeyError)) as caught:
        call()
    return str(caught.value)


@pytest.mark.parametrize(
    ("message", "closed", "open_"),
    [
        (
            equipment_validation._unit_group_mixed_message,
            "Main 설비의 모듈 행은 반입일정이 같아야",
            "Main 설비의 모듈 행은 Qual상태가 같아야",
        ),
        (equipment_validation._flag_message, "반입일정은 Y 또는", "레이아웃표시는 Y 또는"),
        (equipment_validation._number_message, "반입일정을 숫자로", "레이아웃표시를 숫자로"),
        (equipment_validation._date_message, "반입일정은 날짜", "레이아웃표시는 날짜"),
        (
            equipment_validation._exit_before_arrival_message,
            "반입일정은 반입",
            "레이아웃표시는 반입",
        ),
    ],
)
def test_equipment_rule_messages_choose_the_particle_from_the_column(
    message: Callable[[str], str], closed: str, open_: str
) -> None:
    """설비 마스터 규칙 문구 — 칸 이름 끝소리로 조사가 갈린다(「{column}는」 등 고정이었다)."""
    closed_column = "반입일정"
    open_column = "Qual상태" if "Qual상태" in open_ else "레이아웃표시"
    assert closed in message(closed_column)
    assert open_ in message(open_column)


def test_equipment_status_and_actual_messages_follow_the_column() -> None:
    limit = pd.Timestamp("2026-10-26")
    assert equipment_validation._status_message("확정상태", ["Y", "N"]).startswith("확정상태는 ")
    assert equipment_validation._status_message("Qual실적", ["Y"]).startswith("Qual실적은 ")
    assert equipment_validation._actual_future_message("반입실적", limit).startswith("반입실적은 ")
    assert equipment_validation._actual_future_message("Qual 완료", limit).startswith(
        "Qual 완료는 "
    )


@pytest.mark.parametrize(
    ("subject", "expected"),
    [("새 호기 이름", "새 호기 이름은 1~"), ("설비명 바꾸기", "설비명 바꾸기는 1~")],
)
def test_unit_name_rule_follows_the_subject(subject: str, expected: str) -> None:
    assert expected in _raised(lambda: space_layout_edit._require_name("", subject))


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (lambda: month_filter._validate_month_value(0, "조회 시작월"), "조회 시작월은 YYYYMM"),
        (lambda: month_filter._validate_month_value(0, "기준 달"), "기준 달은 YYYYMM"),
        (lambda: month_filter._validate_month_value(0, "선행 기준"), "선행 기준은 YYYYMM"),
        (lambda: month_filter._validate_month_value(0, "끝 시기"), "끝 시기는 YYYYMM"),
        (lambda: required_text(" ", "시나리오명"), "시나리오명은 비어"),
        (lambda: required_text(" ", "리비전 메모"), "리비전 메모는 비어"),
        (lambda: display_order_editor._required_text("", "제품 코드"), "제품 코드는 비어"),
        (lambda: display_order_editor._required_text("", "공정명"), "공정명은 비어"),
        (lambda: securement_threshold._require_positive(0, "확보 기준"), "확보 기준은 0 보다"),
        (lambda: securement_threshold._require_positive(0, "경고 비율"), "경고 비율은 0 보다"),
        (lambda: normalize_canvas_size(math.nan, 100), "캔버스 폭은"),
        (lambda: normalize_canvas_size(100, math.nan), "캔버스 높이는"),
        (
            lambda: prepare_monthly_amounts([], value_column="v", subject="선행 물량"),  # type: ignore[arg-type]
            "선행 물량은 pandas",
        ),
        (
            lambda: prepare_monthly_amounts([], value_column="v", subject="선행 입고"),  # type: ignore[arg-type]
            "선행 입고는 pandas",
        ),
        (lambda: pointer_from_json('{"schema": 3}', pointer_key="k"), "포인터 스키마 3을 이"),
        (lambda: pointer_from_json('{"schema": 2}', pointer_key="k"), "포인터 스키마 2를 이"),
        (lambda: _require_official((1, (2,)), "공식 계획"), "공식 계획은 공식 계획 칸"),
        (lambda: _require_official((1, (2,)), "필요 단축"), "필요 단축은 공식 계획 칸"),
        (lambda: _require_assumed((), "가정 계획"), "가정 계획은 UPEH"),
        (lambda: _require_assumed((), "가정 단축"), "가정 단축은 UPEH"),
    ],
)
def test_service_errors_choose_the_particle_from_the_label(
    call: Callable[[], object], expected: str
) -> None:
    """서비스 오류 문구 — 끼운 라벨의 끝소리로 조사를 고른다(「{label}은(는)」 등 고정이었다)."""
    assert expected in _raised(call)


@pytest.mark.parametrize(
    ("mark_id", "expected"),
    [
        ("MK-lzx1y-3", "도면 요소 MK-lzx1y-3(영역)이 캔버스 100 × 60을 벗어났습니다."),
        ("MK-lzx1y-2", "도면 요소 MK-lzx1y-2(영역)가 캔버스 100 × 60을 벗어났습니다."),
    ],
)
def test_mark_outside_the_canvas_follows_the_mark_id(mark_id: str, expected: str) -> None:
    """괄호 뒤 조사는 괄호 앞 요소 id 의 끝소리를 따른다(「{id}({name}) 가」 고정이었다)."""
    raw = {"x": 95, "y": 0, "w": 10, "h": 10}
    assert _raised(lambda: mark_box(raw, mark_id, "영역", (100, 60))) == expected


def test_tab_limit_notice_puts_the_particle_on_a_fixed_noun() -> None:
    """탭 줄 JS 도 같은 틀을 채우므로 조사는 고정 명사 「화면」 에 붙는다(「을(를)」 이었다)."""
    assert "「생산 계획」 화면을 열려면" in limit_notice("생산 계획")
    assert "「Space 현황」 화면을 열려면" in LIMIT_NOTICE.format(max=MAX_TABS, label="Space 현황")


@pytest.mark.parametrize(
    ("column", "expected"),
    [("생산계획년월", "생산계획년월은 YYYYMM"), ("기준 시기", "기준 시기는 YYYYMM")],
)
def test_month_column_error_follows_the_column(column: str, expected: str) -> None:
    frame = pd.DataFrame({column: ["2026-13"]})
    assert expected in _raised(lambda: normalize_month_column(frame, "표", column=column))


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("공유 설정", "공유 설정을 읽지 못했습니다"),
        ("동기화 기록", "동기화 기록을 읽지"),
        ("포인터", "포인터를 읽지"),
    ],
)
def test_object_storage_json_errors_follow_the_label(
    tmp_path: Path, label: str, expected: str
) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert expected in _raised_storage(lambda: object_storage._read_json(broken, label=label))
    listed = tmp_path / "listed.json"
    listed.write_text("[]", encoding="utf-8")
    subject = with_subject_particle(label)
    assert f"{subject} JSON 객체가" in _raised_storage(
        lambda: object_storage._read_json(listed, label=label)
    )


def _raised_storage(call: Callable[[], object]) -> str:
    with pytest.raises(object_storage.ObjectStorageError) as caught:
        call()
    return str(caught.value)


@pytest.mark.parametrize(
    ("database", "expected"),
    [
        ("설비 저장소", "설비 저장소가 이 코드보다"),
        ("시뮬레이션 기록", "시뮬레이션 기록이 이 코드보다"),
    ],
)
def test_schema_ahead_message_follows_the_database_name(database: str, expected: str) -> None:
    notice = SchemaAheadOfCode(database_name=database, database_version=9, code_version=8)
    assert schema_ahead_message(notice).startswith(expected)
