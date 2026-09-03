# Purpose: app.py가 선언한 페이지 인벤토리와 네비게이션 설정을 고정한다.

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"

# 특성화 테스트다. app.py의 네비게이션을 선언형 구조로 추출할 때 페이지가 빠지거나
# 제목·아이콘이 바뀌는 것을 잡기 위한 기준값이며, 의도적으로 바꿀 때는 함께 갱신한다.
# 미구현 표기가 `(구현중)`·`(구현 중)`·`(DB 셋팅중)` 세 가지로 갈려 있는 것도
# 현재 상태 그대로 기록한다.
EXPECTED_PAGES = [
    ("app_pages/actual_efficiency.py", "효율 실적 (DB 셋팅중)", ":material/speed:", False),
    ("app_pages/actual_upeh.py", "UPEH 실적 (DB 셋팅중)", ":material/timer:", False),
    (
        "app_pages/available_equipment_status.py",
        "가용설비 현황 (구현 중)",
        ":material/precision_manufacturing:",
        False,
    ),
    ("app_pages/capa_chatbot.py", "Capa Chatbot", ":material/chat:", False),
    ("app_pages/capacity_standards.py", "공정별 Capa", ":material/settings:", False),
    ("app_pages/home.py", "HOME", None, True),
    ("app_pages/load_conversion.py", "부하량", ":material/scale:", False),
    ("app_pages/process_securement.py", "공정별 확보율", ":material/monitoring:", False),
    (
        "app_pages/reference_integrity.py",
        "Dynamic Capa (구현중)",
        ":material/sync_alt:",
        False,
    ),
    ("app_pages/scenario_management.py", "시나리오 관리", ":material/database:", False),
    ("app_pages/space_status.py", "Space 현황 (구현 중)", ":material/grid_view:", False),
    ("app_pages/standard_target_capa.py", "표준 목표 Capa", ":material/track_changes:", False),
    ("app_pages/static_capa.py", "Static Capa", ":material/factory:", False),
    (
        "app_pages/wip_status.py",
        "표준 대비 재공 현황 (DB 셋팅중)",
        ":material/inventory_2:",
        False,
    ),
]


def _literal(node: ast.expr | None) -> object:
    return None if node is None else ast.literal_eval(node)


def _declared_pages() -> list[tuple[object, object, object, object]]:
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    pages: list[tuple[object, object, object, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "Page"):
            continue
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        pages.append(
            (
                _literal(node.args[0]) if node.args else None,
                _literal(keywords.get("title")),
                _literal(keywords.get("icon")),
                bool(_literal(keywords.get("default")) or False),
            )
        )
    # ast.walk는 소스 순서를 보장하지 않으므로 경로로 정렬해 비교한다.
    return sorted(pages, key=lambda page: str(page[0]))


def test_app_declares_the_expected_page_inventory() -> None:
    assert _declared_pages() == EXPECTED_PAGES


def test_every_declared_page_file_exists() -> None:
    missing = [path for path, *_ in _declared_pages() if not (PROJECT_ROOT / str(path)).is_file()]

    assert not missing, f"선언된 페이지 파일이 없습니다: {missing}"


def test_exactly_one_page_is_the_default_entry_point() -> None:
    defaults = [path for path, _title, _icon, default in _declared_pages() if default]

    assert defaults == ["app_pages/home.py"]


def test_navigation_hides_the_builtin_sidebar_widget() -> None:
    """사이드바는 app.py가 직접 그리므로 기본 네비게이션 위젯을 숨긴다."""
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    positions = [
        _literal(keyword.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "navigation"
        for keyword in node.keywords
        if keyword.arg == "position"
    ]

    assert positions == ["hidden"]
