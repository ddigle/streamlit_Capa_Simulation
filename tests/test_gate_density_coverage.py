# Purpose: 저장·발행 판정과 공식 발행 경로가 모두 HOME Density 환산 검사를 거치는지 지킨다.

"""**Density 검사는 Capa 계산 검사 곁에 늘 같이 있어야 한다.**

계획이 있는 제품의 `구분_EQ` 가 0 이하면 대당 Capa·소요대수는 통과하고 HOME 의 Density 환산만
멈춘다(`capacity_gate.density_error`). Capa 계산 검사만 부르는 판정이나 발행 경로는 그 리비전을
「계산된다」고 보고 저장·발행해, 공식버전이 되는 순간 모두의 HOME 을 멈춘다. 판정 함수와 발행
경로는 갈래마다 늘어난다(파생 저장 판정, 세션 없는 자동 발행) — 새로 생긴 것이 이 검사를 빠뜨리면
그 자리에서 실패하게 구조로 지킨다. 동작 시험은 `tests/test_capacity_gate.py` 에 있다.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GATE_MODULE = PROJECT_ROOT / "src" / "capa_simulation" / "components" / "capacity_gate.py"
DENSITY_CHECK = "density_error"
PUBLISH_CALL = "publish_official_revision"
PUBLISH_GATES = {"official_publish_verdict", DENSITY_CHECK}
# 내장 합성 시드 부트스트랩은 검사하지 않는다(`capacity_gate` 머리말) — 빈 저장소에만 쓴다.
UNCHECKED_PUBLISHERS = {Path("src/capa_simulation/application_bootstrap.py")}


def _calls(node: ast.AST) -> dict[str, int]:
    """`node` 안에서 부르는 이름과 그 첫 줄 번호. `obj.f()` 는 `f` 로 센다."""
    calls: dict[str, int] = {}
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name and (name not in calls or call.lineno < calls[name]):
            calls[name] = call.lineno
    return calls


def test_every_gate_verdict_runs_the_density_check() -> None:
    """공개 판정 함수(`*_verdict`)는 모듈 안 어느 길로든 Density 검사에 닿는다."""
    tree = ast.parse(GATE_MODULE.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert DENSITY_CHECK in functions
    verdicts = [
        name for name in functions if name.endswith("_verdict") and not name.startswith("_")
    ]
    assert verdicts

    missing = []
    for verdict in verdicts:
        reached: set[str] = set()
        pending = [verdict]
        while pending:
            name = pending.pop()
            for called in _calls(functions[name]):
                if called in functions and called not in reached:
                    reached.add(called)
                    pending.append(called)
        if DENSITY_CHECK not in reached:
            missing.append(verdict)

    assert not missing, f"Density 검사에 닿지 않는 판정: {missing}"


def test_every_official_publish_is_checked_with_density_first() -> None:
    """공식 발행을 쓰는 함수는 쓰기 **앞에** 발행 판정이나 Density 검사를 부른다.

    화면은 `official_publish_verdict` 를, 세션 없는 배경 발행은 캐시 없는 계산 검사에 더해
    `density_error` 를 직접 부른다. 어느 쪽도 없으면 Capa 계산만 본 발행이다.
    """
    sources = [
        path
        for root in ("src", "app_pages")
        for path in sorted((PROJECT_ROOT / root).rglob("*.py"))
    ]
    sources.append(PROJECT_ROOT / "app.py")
    publishers = []
    unchecked = []
    for path in sources:
        relative = path.relative_to(PROJECT_ROOT)
        if relative in UNCHECKED_PUBLISHERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            calls = _calls(node)
            if PUBLISH_CALL not in calls:
                continue
            publishers.append(f"{relative}:{node.name}")
            gates = [calls[name] for name in PUBLISH_GATES if name in calls]
            if not gates or min(gates) > calls[PUBLISH_CALL]:
                unchecked.append(f"{relative}:{node.name}")

    assert publishers
    assert not unchecked, f"Density 검사 없이 공식 발행하는 함수: {unchecked}"
