# Purpose: 끼운 값 바로 뒤에 못박은 조사가 없고 상수 뒤 조사는 그 상수의 끝소리와 맞는지 지킨다.

"""값 뒤 조사는 `services/korean_particle.py` 한 길로 고른다(AGENTS 8장).

조사 도우미가 생긴 뒤에도(2026-10-05 E2E) 쓰는 것이 자리마다 고르는 일이라 회차마다 고친 자리만
고쳐지고 같은 꼴이 다른 파일에서 다시 나왔다(2026-10-25 E2E 1·2회차 — 「공식 v4 으로」·「4 을」·
「27-06 가」). 이 시험이 그 꼴을 저장소 전체에서 막는다. 허용 목록은 없다.

- **f-string** — `app.py`·`app_pages`·`src` 를 AST 로 훑어 끼운 값(`FormattedValue`) 바로 뒤 글이
  (닫는 `」』`*` 뒤) 고정 조사(을·를·은·는·이·가·으로·로·과·와)로 시작하면 실패한다. 붙은 꼴
  (「{x}을」)과 한 칸 띄운 꼴(「{x} 을」), 손으로 박은 갈래 꼴(「{x}은(는)」·「**{x}** 이(가)」)을
  모두 본다.
- **빼는 것** — 「)」 로 시작하는 꼴(「최신(r{n})이」 — 조사가 괄호 앞 낱말에 붙는다), 앞 값이
  `*_particle(…)` 호출인 꼴(「{with_topic_particle(x)} 이 기본값과」 — 뒤 「이」 는 지시어다).
  **한 칸 띄운 「이」** 는 지시어(「{x} 이 시나리오」)와 갈리지 않아 잡지 않는다 — 진짜 조사였던 넷
  (bigdataquery 모듈 이름·스냅샷 마이그레이션 버전·제약 시뮬레이션 공정·모듈 행 칸)은 고쳤고, 그
  꼴의 재발은 리뷰 몫이다.
- **상수 뒤 조사** — 값이 ALL_CAPS 상수(이름·모듈 속성)이면 고정 조사를 두어도 된다. 대신 그 모듈을
  불러 실제 값(서식 지정까지 입힌 글)으로 `korean_particle` 이 같은 조사를 고르는지 단언한다 — 상수
  글이 바뀌면 이 시험이 잡는다. 도우미가 읽지 못하는 끝(영문)은 `_READINGS` 의 읽기로 견준다.
- **`str.format`·`%s` 틀** — f-string 이 아닌 글(문장으로 선 글·docstring 빼고)의 `{…}`·`%s` 바로
  뒤 고정 조사.
- **JS** — `src/**/*.js` 의 `${…}` 바로 뒤 고정 조사. 배치 편집기는 `editor.js` 의 `withJosa` 를
  쓰고, 그 표가 파이썬과 같은 답을 내는지 node 로 대조한다(node·bun 이 없으면 건너뛰고 CI 에서는
  실패 — `test_space_module_group._node`).
"""

from __future__ import annotations

import ast
import importlib
import math
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from test_space_module_group import _node

from capa_simulation.components import space_layout_editor
from capa_simulation.io import object_storage
from capa_simulation.page_bootstrap import schema_ahead_message
from capa_simulation.persistence._migration_core import SchemaAheadOfCode
from capa_simulation.persistence._sql_helpers import required_text
from capa_simulation.services import (
    display_order_editor,
    equipment_validation,
    month_filter,
    securement_threshold,
    space_layout_edit,
)
from capa_simulation.services.floor_layout_profile import normalize_canvas_size
from capa_simulation.services.frame_contracts import normalize_month_column
from capa_simulation.services.korean_particle import (
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
_BOUNDARY = r"(?=[\s.,·—:;)」』!?]|$)"
_CLOSERS = "[」』`*]*"
# 끼운 값 바로 뒤 글의 머리 — 붙은 꼴, 한 칸 띄운 꼴(이 빼고), 손으로 박은 갈래 꼴.
_FIXED_HEAD = re.compile(
    rf"^{_CLOSERS}(?:(?:{_PARTICLES})|\s(?:{_SPACED_PARTICLES})){_BOUNDARY}"
    rf"|^{_CLOSERS}\s?(?:{_HEDGED})"
)
# 상수 뒤 고정 조사. 띄운 「이」 는 지시어와 갈리지 않아 붙은 꼴만 본다.
_CONSTANT_HEAD = re.compile(
    rf"^{_CLOSERS}(?:(?P<attached>{_PARTICLES})|\s(?P<spaced>{_SPACED_PARTICLES})){_BOUNDARY}"
)
_TEMPLATE_SITE = re.compile(
    rf"(?:\{{[^{{}}]*\}}|%[sdr]){_CLOSERS}(?:{_PARTICLES}|\s(?:{_SPACED_PARTICLES})){_BOUNDARY}"
)
_JS_SITE = re.compile(
    rf"\$\{{[^}}]*\}}{_CLOSERS}"
    rf"(?:(?:{_PARTICLES}|\s(?:{_SPACED_PARTICLES})){_BOUNDARY}|\s?(?:{_HEDGED}))"
)
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


def _value_sites(tree: ast.AST) -> Iterator[tuple[ast.FormattedValue, str, int]]:
    """f-string 안에서 끼운 값과 그 바로 뒤 글(·줄 번호)의 쌍."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        for value, following in zip(node.values, node.values[1:], strict=False):
            if (
                isinstance(value, ast.FormattedValue)
                and isinstance(following, ast.Constant)
                and isinstance(following.value, str)
            ):
                yield value, following.value, following.lineno


def _site(path: Path, value: ast.FormattedValue, text: str, line: int) -> str:
    return f"{_relative(path)}:{line}: {{{ast.unparse(value.value)}}}{text[:24]!r}"


def _trees() -> Iterator[tuple[Path, ast.Module]]:
    for path in _source_files():
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def test_no_fixed_particle_follows_an_interpolated_value() -> None:
    """런타임 값 뒤 조사는 `with_*_particle`·`*_particle` 로 고른다 — 붙은·띄운·갈래 꼴 모두."""
    offenders: list[str] = []
    for path, tree in _trees():
        for value, text, line in _value_sites(tree):
            if text.startswith(")") or _is_particle_call(value.value):
                continue
            if not _FIXED_HEAD.match(text):
                continue
            if _is_constant(value.value) and _CONSTANT_HEAD.match(text):
                continue  # 아래 상수 시험이 실제 값으로 견준다.
            offenders.append(_site(path, value, text, line))
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
        for value, text, line in _value_sites(tree):
            match = _CONSTANT_HEAD.match(text)
            if match and _is_constant(value.value):
                yield path, value, text, line, match["attached"] or match["spaced"]


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
    passed = [" 이 시나리오", "의 칸", "개를", "이다", "으로써", "로부터", " 이상"]
    assert all(_FIXED_HEAD.match(text) for text in caught)
    assert not any(_FIXED_HEAD.match(text) for text in passed)
    assert _TEMPLATE_SITE.search("회차 %s 가 멈췄습니다") and _TEMPLATE_SITE.search("「{name}」는")
    assert not _TEMPLATE_SITE.search("{list}\n이 화면을")
    assert _JS_SITE.search("`${id} 는 이미`") and _JS_SITE.search("`${w}이 되어`")
    assert not _JS_SITE.search("`${withJosa(id, '은')} 이미`")


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
