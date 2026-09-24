# Purpose: 표시순서 구분자가 실제 페이지 제목·탭 이름과 갈라지지 않는지 검사한다.

"""**이 검사가 없어서 구분자가 화면 이름과 조용히 갈라졌다.**

표시순서 규칙은 `(페이지 구분, 탭 구분)` 으로 범위를 정하는데, 그 값이 호출부 일곱 곳에
문자열 리터럴로 흩어져 있었다. 화면 이름이 바뀌는 동안 아무도 따라오지 않아 2026-09-24
에는 **어느 것도 실제 페이지 이름이 아니었고**, 한 구분자가 여러 페이지에 걸쳐 있기까지
했다(`공정별 Capa` 가 `기준 정보` 여섯 탭 + `산출 결과` 한 탭).

어긋나도 **오류가 나지 않는다.** 규칙이 어느 탭에도 걸리지 않아 정렬만 기본값으로 돌아갈
뿐이라 눈치채기 어렵다. 그래서 검사로 막는다.

`config/bootstrap_display_order.json` 과 `0027_display_order_scope_rename.sql` 도 같은
대응을 쓰므로 함께 본다 — 셋 중 하나만 고치면 저장된 규칙이 갈 곳을 잃는다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from capa_simulation.services.display_order_scopes import (
    DISPLAY_ORDER_SCOPES,
    LEGACY_SCOPE_RENAMES,
    PAGE_CALCULATION,
    PAGE_PLAN,
    PAGE_REFERENCE,
    PAGE_STANDARD_TARGET,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NAVIGATION = PROJECT_ROOT / "src" / "capa_simulation" / "navigation.py"
BOOTSTRAP = PROJECT_ROOT / "config" / "bootstrap_display_order.json"
MIGRATION = (
    PROJECT_ROOT
    / "src"
    / "capa_simulation"
    / "persistence"
    / "migrations"
    / "0027_display_order_scope_rename.sql"
)

# 구분자를 쓰는 페이지와 그 파일. 탭 이름은 각 페이지의 `TAB_NAMES` 에서 읽는다.
SCOPE_PAGES = {
    PAGE_PLAN: "app_pages/load_conversion.py",
    PAGE_REFERENCE: "app_pages/reference_data.py",
    PAGE_CALCULATION: "app_pages/calculation_result.py",
    PAGE_STANDARD_TARGET: "app_pages/standard_target_capa.py",
}


def _navigation_titles() -> dict[str, str]:
    """`PageSpec("app_pages/x.py", "제목"` 에서 모듈 경로 → 제목."""
    text = NAVIGATION.read_text(encoding="utf-8")
    found = re.findall(r'PageSpec\(\s*"(app_pages/[a-z_]+\.py)",\s*(?:_\w+\()?"([^"]+)"', text)
    return {module: title for module, title in found}


def _tab_names(module: str) -> set[str]:
    """그 페이지의 `TAB_NAMES`. 아이콘 접두어(`:material/x:`)는 이름이 아니라 서식이다."""
    text = (PROJECT_ROOT / module).read_text(encoding="utf-8")
    block = re.search(r"^TAB_NAMES\s*=\s*\((.*?)\)", text, re.S | re.M)
    if block is None:
        return set()
    names = re.findall(r'"([^"]+)"', block.group(1))
    return {re.sub(r"^:material/[a-z_0-9]+:\s*", "", name) for name in names}


def test_every_page_scope_is_a_real_page_title() -> None:
    """페이지 구분은 사이드바에 실제로 서는 페이지 이름이어야 한다."""
    titles = set(_navigation_titles().values())
    pages = {page for page, _ in DISPLAY_ORDER_SCOPES}

    unknown = sorted(page for page in pages if page not in titles)

    assert not unknown, (
        "표시순서의 `페이지 구분` 이 실제 페이지 제목과 다릅니다. "
        f"`navigation.py` 를 고쳤다면 `display_order_scopes.py` 도 함께 고칩니다:\n{unknown}"
    )


def test_every_tab_scope_is_a_real_tab_on_that_page() -> None:
    """탭 구분은 그 페이지에 실제로 있는 탭이어야 한다.

    **표준 목표만 예외다** — `표준 대비 재공 현황` 과 규칙 한 벌을 함께 쓰기로 했고
    (2026-09-24 사용자 결정), 그 탭 이름은 `표준 목표` 페이지가 갖는다.
    """
    missing: list[str] = []
    for page, module in SCOPE_PAGES.items():
        declared = {tab for scope_page, tab in DISPLAY_ORDER_SCOPES if scope_page == page}
        if not declared:
            continue
        actual = _tab_names(module)
        if not actual:
            continue  # `TAB_NAMES` 가 없는 페이지는 이 검사가 답할 것이 없다
        missing += [f"{page} / {tab}" for tab in sorted(declared - actual)]

    assert not missing, (
        "표시순서의 `탭 구분` 이 그 페이지의 `TAB_NAMES` 에 없습니다. "
        f"탭 이름을 바꿨다면 `display_order_scopes.py` 도 함께 고칩니다:\n{missing}"
    )


def test_the_bootstrap_rules_use_only_declared_scopes() -> None:
    """부트스트랩 시드가 옛 구분자를 들고 있으면 새 DB 부터 어긋난 채 시작한다."""
    rules = json.loads(BOOTSTRAP.read_text(encoding="utf-8"))["rules"]
    declared = set(DISPLAY_ORDER_SCOPES)

    stray = sorted(
        {
            f"{rule['페이지 구분']} / {rule['탭 구분']}"
            for rule in rules
            if (rule["페이지 구분"], rule["탭 구분"]) not in declared
        }
    )

    assert not stray, (
        f"`config/bootstrap_display_order.json` 에 선언 밖 구분자가 있습니다:\n{stray}"
    )


def test_the_migration_covers_every_legacy_scope() -> None:
    """저장된 규칙을 옮기는 SQL 이 대응 하나라도 빠뜨리면 그 규칙은 갈 곳을 잃는다.

    걸리지 않는 규칙은 **오류가 아니라 무시**라, 빠뜨려도 화면은 조용하다.
    """
    sql = MIGRATION.read_text(encoding="utf-8")

    missing = [
        f"{old_page} / {tab}"
        for (old_page, tab), (new_page, _) in LEGACY_SCOPE_RENAMES.items()
        if f"'{new_page}'" not in sql or f"'{old_page}'" not in sql or f"'{tab}'" not in sql
    ]

    assert not missing, f"`0027` 이 옮기지 않는 옛 구분자가 있습니다:\n{missing}"


def test_every_legacy_rename_lands_on_a_declared_scope() -> None:
    """옮긴 뒤의 값이 선언 밖이면 옮기나 마나다."""
    declared = set(DISPLAY_ORDER_SCOPES)

    stray = sorted(
        f"{old} -> {new}" for old, new in LEGACY_SCOPE_RENAMES.items() if new not in declared
    )

    assert not stray, f"옛 구분자가 선언에 없는 곳으로 갑니다:\n{stray}"
