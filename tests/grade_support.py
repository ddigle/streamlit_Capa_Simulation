# Purpose: 접속 등급 시험 도우미 — 운영 + 통합인증 켜짐 고정 · 등급 계정 쿠키 · 판정 엿보기 · 그물.

"""접속 등급 시험 재료(모든 등급 시험은 「운영 + 통합인증 켜짐」 판정을 거친다 — 헛돌기 막음).

- `operational_grades` — 운영(`APP_ENV=prod`) + 통합인증 켜짐 + 문지기 표시 + S3 명단 켜짐(가짜
  버킷)
  에 명단 · 등급 파일 한 벌을 올려 읽고 판정기를 꽂는다. 그리고 `cfg.operational` · 켜짐 · S3 명단
  켜짐 · 판정기 꽂힘 · 넷 계정의 등급을 **단언**한다 — 환경변수 명단(S3 꺼짐)이면 실무자 · 관리자가
  열람으로 읽혀 음성 시험이 내용 대조가 아니라 바닥 벽에서 그냥 통과하기 때문이다.
- `as_grade` — 그 등급 합성 계정(`demo.*`)의 세션 쿠키를 이 연결의 쿠키로 끼운다.
- `judge_spy` — `grades.require` 가 실제로 불린 (동작, 지금 등급)을 모은다(「판정기가 불렸다」).
- `grade_page_script` — 페이지 원문을 `grade_ui.install()` + `grade_ui.emit()` + 실제
  `run_core_page` 감싸기로 두른 AppTest 원문(conftest 가 시험마다 걷어 내는 감싸기를 이 모듈을 읽을
  때 붙잡아 둔다 — 화면 시험이 실제 받는 자리를 지난다).
- `assert_refusals_caught` — 쓰기 장부(`tests/test_write_entry_points.py` LEDGER)의 바깥 함수에
이르는
  뿌리(위젯 콜백 · `st.dialog` · `st.fragment`)를 파일을 넘어 이름 부름 길로 찾고, 넘긴 파일 안의
  뿌리가 받는 자리(`grade_ui.on_press` · `grade_ui.in_fragment`)를 달았는지 정적으로 본다. 어느
  콜백 · 팝업 · 프래그먼트에서도 불리지 않는 바깥 함수는 「본문」 뿌리다(`run_core_page` 가 받는다).

값은 모두 합성(`demo.*`)이고 저장소는 메모리 가짜 버킷이다(네트워크 없음).
"""

from __future__ import annotations

import ast
import time
import warnings
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import pytest
from sso_support import use_config
from streamlit.testing.v1 import AppTest

from capa_simulation.auth import access_store, grade_store, grades, names, runtime
from capa_simulation.auth.access import (
    GRADE_ADMIN,
    GRADE_USER,
    GradeDocument,
    GradeLine,
    ListDocument,
    ListEntry,
)
from capa_simulation.auth.config import SsoConfig, SsoMode
from capa_simulation.auth.tokens import issue_session
from capa_simulation.components import grade_ui, page_failure_card, sso_identity
from capa_simulation.io import s3_small
from capa_simulation.io.s3_small import S3Failure, S3Object

ROOT: Final = Path(__file__).resolve().parents[1]
SOURCE: Final = ROOT / "src" / "capa_simulation"

DEMO_DEVELOPER: Final = "demo.dev"
DEMO_MANAGER: Final = "demo.manager"
DEMO_EDITOR: Final = "demo.editor"
DEMO_VIEWER: Final = "demo.viewer"
GRADE_ACCOUNTS: Final[Mapping[str, str]] = {
    grades.VIEWER: DEMO_VIEWER,
    grades.EDITOR: DEMO_EDITOR,
    grades.MANAGER: DEMO_MANAGER,
    grades.DEVELOPER: DEMO_DEVELOPER,
}
GRADE_PARAMS: Final = pytest.mark.parametrize("grade", grades.GRADES)
# 명단 항목의 등록 시각(합성). 등급 파일 줄의 등록 시각이 이것과 같아야 그 줄이 산다.
ADDED_AT: Final = "2026-11-20T00:10:00Z"
# 가짜 S3 명단 설정(문서용 예약 도메인 · 합성 키).
S3_ENVIRON: Final[Mapping[str, str]] = {
    names.ENV_S3_ACCESS_KEY: "DEMOACCESSKEY",
    names.ENV_S3_SECRET_KEY: "demo-secret-key",
    names.ENV_S3_ENDPOINT: "https://s3.example.invalid",
    names.ENV_S3_BUCKET: "demo-bucket",
    names.ENV_S3_REGION: "us-east-1",
}

# conftest(`_core_page_errors_still_raise`)가 시험마다 걷기 전, 이 모듈을 읽는 때의 실제 감싸기.
REAL_RUN_CORE_PAGE: Final = page_failure_card.run_core_page


# ------------------------------------------------------------------ 가짜 버킷
@dataclass
class FakeBucket:
    """메모리 객체 저장소 — `io/s3_small` 의 GET · HEAD · PUT 을 대신한다. `failing` 에 든 키는 그
    동작에서 `S3Failure`(`fail_kind`)를 낸다(쓰기 실패 · 읽기 실패 시험)."""

    objects: dict[str, tuple[bytes, str]] = field(default_factory=dict)
    failing: dict[str, set[str]] = field(default_factory=dict)
    fail_kind: str = s3_small.KIND_UNREACHABLE
    counter: int = 0

    def _check(self, operation: str, key: str) -> None:
        if key in self.failing.get(operation, set()):
            raise S3Failure(self.fail_kind)

    def get(self, _target: Any, key: str, **_: Any) -> S3Object | None:
        self._check("get", key)
        found = self.objects.get(key)
        return None if found is None else S3Object(body=found[0], etag=found[1])

    def head(self, _target: Any, key: str, **_: Any) -> str | None:
        self._check("head", key)
        found = self.objects.get(key)
        return None if found is None else found[1]

    def put(self, _target: Any, key: str, body: bytes, **_: Any) -> str:
        self._check("put", key)
        self.counter += 1
        etag = f"etag-{self.counter}"
        self.objects[key] = (body, etag)
        return etag

    def fail(self, operation: str, key: str) -> None:
        self.failing.setdefault(operation, set()).add(key)

    def heal(self) -> None:
        self.failing.clear()


def install_fake_bucket(monkeypatch: pytest.MonkeyPatch) -> FakeBucket:
    """명단(`access_store`)과 등급 파일(`grade_store` — `s3_small` 모듈 이름)의 S3 입출력을 가짜
    버킷으로 바꾼다."""
    bucket = FakeBucket()
    for owner in (s3_small, access_store):
        monkeypatch.setattr(owner, "get_object", bucket.get)
        monkeypatch.setattr(owner, "head_object", bucket.head)
        monkeypatch.setattr(owner, "put_object", bucket.put)
    return bucket


# ------------------------------------------------------------------ 운영 + 켜짐
def demo_list_document() -> ListDocument:
    """합성 명단 — 넷 계정(개발자는 환경변수 개발자이기도 하다)."""
    entries = (
        ListEntry(DEMO_DEVELOPER, "demo.dev", ADDED_AT, grade=GRADE_ADMIN),
        ListEntry(DEMO_EDITOR, "demo.dev", ADDED_AT, name="DEMO 이대리", dept="DEMO 팀"),
        ListEntry(DEMO_MANAGER, "demo.dev", ADDED_AT, name="DEMO 최과장", dept="DEMO 팀"),
        ListEntry(DEMO_VIEWER, "demo.dev", ADDED_AT, grade=GRADE_USER),
    )
    return ListDocument(revision=1, entries=tuple(sorted(entries, key=lambda e: e.loginid)))


def demo_grade_document() -> GradeDocument:
    """합성 등급 파일 — 실무자 · 관리자 한 줄씩(열람은 줄 없음, 개발자는 명단이 정한다)."""
    return GradeDocument(
        revision=1,
        lines=(
            GradeLine(DEMO_EDITOR, grades.EDITOR, ADDED_AT, DEMO_DEVELOPER, ADDED_AT),
            GradeLine(DEMO_MANAGER, grades.MANAGER, ADDED_AT, DEMO_DEVELOPER, ADDED_AT),
        ),
    )


@dataclass
class GradeWorld:
    """운영 + 켜짐 한 벌 — 설정 · 가짜 버킷."""

    cfg: SsoConfig
    bucket: FakeBucket


_WORLD: dict[str, GradeWorld] = {}


def current_world() -> GradeWorld | None:
    return _WORLD.get("world")


def forget_world() -> None:
    """conftest 가 시험마다 비운다."""
    _WORLD.clear()


def operational_grades(monkeypatch: pytest.MonkeyPatch, *, grade_file: bool = True) -> SsoConfig:
    """운영 + 켜짐 · 문지기 표시 · S3 명단(가짜 버킷) · 명단 · 등급 파일 publish · 판정기 꽂기.

    `cfg.operational` · 켜짐 · S3 명단 켜짐 · 판정기 꽂힘 · 넷 계정의 등급을 단언한다(모듈 설명).
    `grade_file` 이 거짓이면 등급 파일을 올리지 않는다(아직 등급이 없음 — 모두 열람).
    """
    bucket = install_fake_bucket(monkeypatch)
    cfg = use_config(
        {
            names.ENV_ACCESS_ADMINS: DEMO_DEVELOPER,
            names.ENV_ACCESS_USERS: "",
            **S3_ENVIRON,
        }
    )
    runtime.mark_gate_installed()
    bucket.put(None, cfg.access_object_key, access_store.render_document(demo_list_document()))
    if grade_file:
        bucket.put(
            None, grade_store.object_key(cfg), grade_store.render_document(demo_grade_document())
        )
        bucket.put(None, grade_store.mark_key(cfg), b'{"format": 1}')
    access_store.read_at_start(cfg, now=int(time.time()))
    grade_store.read_at_start(cfg, now=int(time.time()))
    grade_ui.install()
    _WORLD["world"] = GradeWorld(cfg, bucket)
    assert cfg.operational and cfg.mode is SsoMode.ON, "운영 + 통합인증 켜짐이어야 한다"
    assert access_store.is_on(cfg), "S3 명단이 켜져야 등급 파일을 읽는다"
    assert grades.caller_source() is sso_identity.real_caller, "판정기가 꽂혀야 한다"
    if grade_file:
        for grade, account in GRADE_ACCOUNTS.items():
            assert grade_store.grade_of(cfg, account) == grade, (account, grade)
    return cfg


def session_jar(cfg: SsoConfig, loginid: str | None) -> dict[str, str]:
    """그 사람의 세션 쿠키 한 벌(없으면 빈 쿠키)."""
    if loginid is None:
        return {}
    token, _ = issue_session(cfg, loginid=loginid, name=None, dept=None, now=int(time.time()))
    return {cfg.session_cookie: token}


def as_account(monkeypatch: pytest.MonkeyPatch, loginid: str | None) -> None:
    """이 연결의 쿠키를 그 계정의 세션으로(없으면 쿠키 없음 — 로그인 끝남). 실행 문맥이 없는 시험
    스레드도 화면 스레드로 본다."""
    world = current_world()
    cfg = runtime.config() if world is None else world.cfg
    jar = session_jar(cfg, loginid)
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: jar)
    monkeypatch.setattr(sso_identity, "script_context_present", lambda: True)


def as_grade(monkeypatch: pytest.MonkeyPatch, grade: str) -> str:
    """`operational_grades`(아직이면) + 그 등급 합성 계정의 쿠키. 계정을 돌려준다."""
    if current_world() is None:
        operational_grades(monkeypatch)
    account = GRADE_ACCOUNTS[grade]
    as_account(monkeypatch, account)
    return account


def unrestricted(monkeypatch: pytest.MonkeyPatch) -> None:
    """운영 아님(개발 `app.py` · 사내 WebIDE · 사내 PC) — 판정기를 꽂아도 늘 지나간다."""
    for name in names.SSO_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    runtime.reset()
    grade_ui.install()
    assert not runtime.config().operational


def operational_sso_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """운영(`APP_ENV=prod`)인데 통합인증 꺼짐(client id 없음) — 관리자까지 된다."""
    for name in names.SSO_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(names.ENV_APP_ENV, "prod")
    runtime.reset()
    grade_ui.install()
    cfg = runtime.config()
    assert cfg.operational and cfg.mode is not SsoMode.ON


def preview(monkeypatch: pytest.MonkeyPatch, grade: str) -> None:
    """실제 개발자 + 「이 등급으로 보기」 — 미리 보기 판정(`sso_identity.preview_grade`)이 그 등급을
    낸다(자격 판정 — 운영 + 켜짐의 실제 개발자 — 은 그대로 거친다)."""
    as_grade(monkeypatch, grades.DEVELOPER)
    original = sso_identity.preview_grade

    def previewed() -> str | None:
        cfg = runtime.config()
        if cfg.operational and cfg.mode is SsoMode.ON and sso_identity.viewer_is_developer():
            return grade
        return original()

    monkeypatch.setattr(sso_identity, "preview_grade", previewed)


@contextmanager
def judge_spy() -> Iterator[list[tuple[str, str]]]:
    """`grades.require` 가 불린 (동작, 지금 등급) — 판정이 실제로 섰다는 단언에 쓴다."""
    seen: list[tuple[str, str]] = []
    original = grades.require

    def spy(action: str) -> None:
        who = grades.caller()
        seen.append((action, "unrestricted" if who.unrestricted else who.grade))
        original(action)

    grades.require = spy
    try:
        yield seen
    finally:
        grades.require = original


def grade_page_script(page_source: str) -> str:
    """페이지 원문을 판정기 꽂기 + 거절 알림 내기 + 실제 `run_core_page` 감싸기로 두른 AppTest 원문.

    `app.py` 와 같은 차례다 — 꽂기 → 알림 칸 곁 `emit`(페이지보다 앞) → 감싼 페이지.
    """
    return f"""
import grade_support
from capa_simulation.components import grade_ui

grade_ui.install()
grade_ui.emit()


def _page() -> None:
    exec(compile({page_source!r}, "<grade page>", "exec"), {{"__name__": "__main__"}})


grade_support.REAL_RUN_CORE_PAGE(_page, page="", href="")
"""


def visible_labels(app: AppTest) -> set[str]:
    """단추 · 내려받기 · 탭 · 팝오버 · 펼침 · 라디오 · 고르기 라벨 모음(본문 · 사이드바)."""
    labels: set[str] = set()
    for root in (app.main, app.sidebar):
        for node in root:
            kind = getattr(node, "type", "")
            proto = getattr(node, "proto", None)
            label: object = None
            if kind == "popover" and proto is not None:
                label = proto.popover.label
            elif kind == "expandable" and proto is not None:
                label = proto.expandable.label
            else:
                try:
                    label = getattr(node, "label", None)
                except (AttributeError, KeyError):
                    label = None
            if isinstance(label, str) and label:
                labels.add(label)
    return labels


# ------------------------------------------------------------------ 받는 자리 그물
_PAGES = "app_pages"
_PARTS = "src/capa_simulation/components"
_CALLBACK_KWARGS: Final = ("on_click", "on_change", "on_submit")


def _parse(path: Path) -> ast.Module:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(path.read_text(encoding="utf-8"))


def ui_paths() -> list[Path]:
    """화면 모듈 — 앱 · 페이지 · 부품(장부 시험과 같은 범위)."""
    return [
        ROOT / "app.py",
        *sorted((ROOT / "app_pages").glob("*.py")),
        *sorted((SOURCE / "components").rglob("*.py")),
    ]


def ledger_outer_functions() -> set[tuple[str, str]]:
    """쓰기 장부의 (파일, 바깥 함수) — 장부를 import 하지 않고 글로 읽는다(무거운 시험 묶음을
    끌어오지
    않게)."""
    tree = _parse(ROOT / "tests" / "test_write_entry_points.py")
    constants: dict[str, str] = {}
    found: set[tuple[str, str]] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value.value, str):
                    constants[target.id] = node.value.value
        value = node.value if isinstance(node, ast.AnnAssign | ast.Assign) else None
        target_name = (
            node.target.id
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
            else None
        )
        if target_name != "LEDGER" or not isinstance(value, ast.Dict):
            continue
        for key in value.keys:
            if not isinstance(key, ast.Tuple) or len(key.elts) != 3:
                continue
            path = _text_of(key.elts[0], constants)
            outer = _text_of(key.elts[1], constants)
            if path is not None and outer is not None:
                found.add((path, outer))
    return found


def _text_of(node: ast.expr, constants: Mapping[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            elif isinstance(value, ast.FormattedValue) and isinstance(value.value, ast.Name):
                if value.value.id not in constants:
                    return None
                parts.append(constants[value.value.id])
            else:
                return None
        return "".join(parts)
    return None


@dataclass(frozen=True)
class Root:
    """받는 자리가 필요한 뿌리 — 파일 · 함수 이름 · 종류(`callback` · `dialog` · `fragment` ·
    `body`) · 받는 자리를 달았나."""

    path: str
    name: str
    kind: str
    caught: bool


def _decorator_names(function: ast.FunctionDef) -> list[str]:
    names_found: list[str] = []
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute):
            names_found.append(target.attr)
        elif isinstance(target, ast.Name):
            names_found.append(target.id)
    return names_found


Node = tuple[str, str]


def _module_path(module: str) -> str | None:
    """`capa_simulation.components.x` → 저장소 상대 경로(화면 모듈이 아니면 `None`)."""
    if not module.startswith("capa_simulation."):
        return None
    candidate = ROOT / "src" / Path(*module.split("."))
    path = candidate.with_suffix(".py")
    return path.relative_to(ROOT).as_posix() if path.exists() else None


@dataclass
class _FileScope:
    """한 파일의 이름 풀이 — 그 파일에서 정의한 함수 · 가져온 이름 · 가져온 모듈."""

    rel: str
    defs: dict[str, ast.FunctionDef] = field(default_factory=dict)
    names: dict[str, Node] = field(default_factory=dict)
    modules: dict[str, str] = field(default_factory=dict)

    def resolve(self, node: ast.expr) -> Node | None:
        """부름 · 넘김 자리의 함수 → (정의한 파일, 이름). 풀지 못하면 `None`."""
        if isinstance(node, ast.Name):
            if node.id in self.defs:
                return (self.rel, node.id)
            return self.names.get(node.id)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            module = self.modules.get(node.value.id)
            return None if module is None else (module, node.attr)
        if isinstance(node, ast.Call):
            func = node.func
            wrapper = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if wrapper in ("partial", "on_press") and node.args:
                return self.resolve(node.args[0])
        if isinstance(node, ast.Lambda) and isinstance(node.body, ast.Call):
            return self.resolve(node.body.func)
        return None


def _file_scope(path: Path) -> tuple[_FileScope, ast.Module]:
    rel = path.relative_to(ROOT).as_posix()
    tree = _parse(path)
    scope = _FileScope(rel)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            scope.defs.setdefault(node.name, node)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                as_module = _module_path(f"{node.module}.{alias.name}")
                if as_module is not None:
                    scope.modules[alias.asname or alias.name] = as_module
                    continue
                owner = _module_path(node.module)
                if owner is not None:
                    scope.names[alias.asname or alias.name] = (owner, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                owner = _module_path(alias.name)
                if owner is not None and alias.asname:
                    scope.modules[alias.asname] = owner
    return scope, tree


@dataclass
class _Scan:
    edges: dict[Node, set[Node]] = field(default_factory=dict)
    defs: dict[Node, ast.FunctionDef] = field(default_factory=dict)
    callbacks: set[Node] = field(default_factory=set)
    wrapped_callbacks: set[Node] = field(default_factory=set)


def _scan() -> _Scan:
    scan = _Scan()
    for path in ui_paths():
        scope, tree = _file_scope(path)
        for name, function in scope.defs.items():
            node = (scope.rel, name)
            scan.defs[node] = function
            targets = scan.edges.setdefault(node, set())
            for inner in ast.walk(function):
                if isinstance(inner, ast.Call):
                    resolved = scope.resolve(inner.func)
                    if resolved is not None and resolved != node:
                        targets.add(resolved)
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call):
                continue
            for keyword in call.keywords:
                if keyword.arg not in _CALLBACK_KWARGS:
                    continue
                resolved = scope.resolve(keyword.value)
                if resolved is None:
                    continue
                scan.callbacks.add(resolved)
                value = keyword.value
                if (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Attribute)
                    and value.func.attr == "on_press"
                ):
                    scan.wrapped_callbacks.add(resolved)
    return scan


def _reaches(scan: _Scan, start: Node, goal: Node) -> bool:
    seen: set[Node] = set()
    stack = [start]
    while stack:
        node = stack.pop()
        if node == goal:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(scan.edges.get(node, ()))
    return False


def roots_for(outer: Node | str, scan: _Scan | None = None) -> list[Root]:
    """장부 바깥 함수 하나(파일, 이름 — 이름만 주면 그 이름의 모든 정의)에 이르는 뿌리들. 콜백 ·
    팝업 · 프래그먼트가 없으면 「본문」 하나(`run_core_page` 가 받는다)."""
    scan = scan or _scan()
    goals = (
        [outer]
        if isinstance(outer, tuple)
        else [node for node in scan.defs if node[1] == outer] or [("", outer)]
    )
    found: list[Root] = []
    for (rel, name), function in scan.defs.items():
        decorators = _decorator_names(function)
        kind = (
            "dialog"
            if "dialog" in decorators
            else "fragment"
            if "fragment" in decorators
            else "callback"
            if (rel, name) in scan.callbacks
            else None
        )
        if kind is None or not any(_reaches(scan, (rel, name), goal) for goal in goals):
            continue
        if kind == "callback":
            caught = "on_press" in decorators or (rel, name) in scan.wrapped_callbacks
        else:
            caught = "in_fragment" in decorators
        found.append(Root(rel, name, kind, caught))
    if not found:
        found.append(Root(goals[0][0], goals[0][1], "body", True))
    return found


def roots_by_file() -> Mapping[str, set[str]]:
    """장부 바깥 함수마다 찾은 뿌리를 파일 → 함수 이름으로(가로지르는 그물이 쓴다)."""
    scan = _scan()
    grouped: dict[str, set[str]] = {}
    for outer in ledger_outer_functions():
        for root in roots_for(outer, scan):
            grouped.setdefault(root.path, set()).add(root.name)
    return grouped


def uncaught_roots(paths: Sequence[str]) -> list[Root]:
    """넘긴 파일 안의 뿌리 가운데 받는 자리를 달지 않은 것."""
    scan = _scan()
    wanted = set(paths)
    missing: list[Root] = []
    for outer in sorted(ledger_outer_functions()):
        for root in roots_for(outer, scan):
            if root.path in wanted and not root.caught and root not in missing:
                missing.append(root)
    return missing


def assert_refusals_caught(paths: Sequence[str]) -> None:
    """넘긴 파일 안의 뿌리가 모두 받는 자리(`on_press` · `in_fragment`)를 달았다(모듈 설명)."""
    missing = uncaught_roots(paths)
    assert not missing, (
        "등급 거절을 받는 자리가 없는 뿌리 — 콜백은 grade_ui.on_press, 팝업 · 프래그먼트는 "
        f"grade_ui.in_fragment 를 단다: {[(root.path, root.name, root.kind) for root in missing]}"
    )


def ledger_write_names() -> set[str]:
    """쓰기 장부의 쓰기 이름(세 번째 칸) — 장부를 import 하지 않고 글로 읽는다."""
    tree = _parse(ROOT / "tests" / "test_write_entry_points.py")
    found: set[str] = set()
    for node in tree.body:
        if not (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)):
            continue
        if node.target.id != "LEDGER" or not isinstance(node.value, ast.Dict):
            continue
        for key in node.value.keys:
            if isinstance(key, ast.Tuple) and len(key.elts) == 3:
                name = key.elts[2]
                if isinstance(name, ast.Constant) and isinstance(name.value, str):
                    found.add(name.value)
    return found


@dataclass(frozen=True)
class LedgerWalls:
    """장부 쓰기 이름의 벽 — 저장소 메서드에 벽(`grades.GATE_ATTRIBUTE`)이 있음 · 없음 · 저장소
    메서드가 아닌 감싸개(그 안의 저장소 쓰기가 벽을 단다 — 사람이 본다) · 앱 자신의 길(첫 시드)."""

    walled: frozenset[str]
    unwalled: frozenset[str]
    wrappers: frozenset[str]
    system: frozenset[str]


# 앱 자신의 쓰기(`audit.recorder.as_system`)로만 부르는 장부 쓰기 — 사람 등급으로 막지 않는다.
SYSTEM_WRITES: Final = frozenset({"bootstrap_latest_official_scenario"})


def ledger_wall_report() -> LedgerWalls:
    """장부의 쓰기 이름마다 벽이 닿는지(가로지르는 그물 — 갈래를 합친 머리에서 `unwalled` 가
    비어야 한다)."""
    from capa_simulation.persistence import equipment_repository, repository

    owners = (
        repository.DuckDBScenarioRepository,
        equipment_repository.DuckDBEquipmentRepository,
    )
    walled: set[str] = set()
    unwalled: set[str] = set()
    wrappers: set[str] = set()
    system: set[str] = set()
    for name in sorted(ledger_write_names()):
        if name in SYSTEM_WRITES:
            system.add(name)
            continue
        methods = [getattr(owner, name) for owner in owners if hasattr(owner, name)]
        if not methods:
            wrappers.add(name)
        elif any(action_of(method) is not None for method in methods):
            walled.add(name)
        else:
            unwalled.add(name)
    return LedgerWalls(
        frozenset(walled), frozenset(unwalled), frozenset(wrappers), frozenset(system)
    )


def action_of(function: Callable[..., Any]) -> str | None:
    """표지를 단 저장소 쓰기의 벽 동작(`grades.GATE_ATTRIBUTE`)."""
    value = getattr(function, grades.GATE_ATTRIBUTE, None)
    return value if isinstance(value, str) else None
