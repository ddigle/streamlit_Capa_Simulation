# Purpose: 페이지가 계산 뒤에 채우는 자리를 `st.empty` 가 아니라 블록으로 두는지 소스에서 고정한다.

"""계산 뒤에 채우는 자리는 `st.container` 다(AGENTS 9장).

`st.empty()` 는 실행되는 순간 빈 요소를 보내 같은 자리의 앞 회차 내용을 지운다. 그 자리를 무거운
계산이 끝난 뒤에야 채우면 계산 동안 그 줄이 사라지고 아래 본문이 위로 올라갔다 내려온다(공정
Capa 상세의 공정명·배지 줄, Static Capa 판정 기준 카드의 기준 글). 블록은 페이지가 다시 보낼 때까지
앞 회차 줄을 남기고, 비어 있으면 그려지지 않는다. 회차 사이 깜빡임은 프런트엔드 동작이라 AppTest
로 재현되지 않으므로 소스 꼴을 막는다.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "app_pages"
# 회차 시작에 비워져야 하는 자리 — 조건이 맞을 때만 채우는 알림·안내라 앞 회차 글이 남으면 안 된다.
CLEARED_EACH_RUN: frozenset[tuple[str, str]] = frozenset(
    {
        ("available_equipment_status.py", "first_action"),
        ("available_equipment_status.py", "sample_notice"),
        ("load_conversion.py", "plan_notice"),
        ("load_conversion.py", "yield_notice"),
        # 설비 세션을 옮겼다는 한 번뿐인 알림 — 다음 회차에 남으면 이미 지난 이동을 다시 알린다.
        ("scenario_management.py", "equipment_notice_slot"),
    }
)


def _is_st_empty_call(value: ast.expr) -> bool:
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr == "empty"
        and isinstance(value.func.value, ast.Name)
        and value.func.value.id == "st"
        and not value.args
        and not value.keywords
    )


def _empty_slots() -> dict[tuple[str, str], int]:
    """`app_pages/*.py` 의 `<이름> = st.empty()` 대입을 (파일, 이름) → 줄 번호로 모은다."""
    slots: dict[tuple[str, str], int] = {}
    for path in sorted(PAGES.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Assign) and _is_st_empty_call(node.value)):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    slots[(path.name, target.id)] = node.lineno
    return slots


def test_slots_filled_after_calculation_are_blocks_not_empty_elements() -> None:
    """허용 목록 밖의 `st.empty()` 자리는 계산 동안 앞 회차 줄을 지워 화면을 튀게 한다."""
    offenders = sorted(
        f"app_pages/{name}:{line} {slot}"
        for (name, slot), line in _empty_slots().items()
        if (name, slot) not in CLEARED_EACH_RUN
    )
    assert not offenders, (
        "계산 뒤 채우는 자리는 `st.container()` 로 둔다 — AGENTS 9장:\n" + "\n".join(offenders)
    )


def test_the_list_of_slots_cleared_each_run_is_not_stale() -> None:
    """허용 목록의 자리가 사라졌으면 목록에서도 지운다 — 남겨 두면 같은 이름의 퇴행을 못 잡는다."""
    stale = sorted(f"{name} {slot}" for name, slot in CLEARED_EACH_RUN - _empty_slots().keys())
    assert not stale, stale
