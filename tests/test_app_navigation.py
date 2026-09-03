# Purpose: 사이드바 페이지 인벤토리와 네비게이션 설정을 고정한다.

import ast
from pathlib import Path

from capa_simulation.navigation import (
    ALL_SPECS,
    CAPA_CHATBOT,
    DYNAMIC_CAPA,
    DYNAMIC_CAPA_SUBPAGES,
    HOME,
    IMPLEMENTING_SUFFIX,
    STATIC_CAPA,
    STATIC_CAPA_SUBPAGES,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"

# 특성화 테스트다. 페이지가 빠지거나 제목·아이콘이 바뀌는 것을 잡기 위한 기준값이며,
# 의도적으로 바꿀 때는 함께 갱신한다.
EXPECTED_PAGES = [
    ("app_pages/home.py", "HOME", None, True),
    ("app_pages/capa_chatbot.py", "Capa Chatbot (구현중)", ":material/chat:", False),
    ("app_pages/scenario_management.py", "시나리오 관리", ":material/database:", False),
    ("app_pages/static_capa.py", "Static Capa", ":material/factory:", False),
    ("app_pages/load_conversion.py", "부하량", ":material/scale:", False),
    ("app_pages/capacity_standards.py", "공정별 Capa", ":material/settings:", False),
    ("app_pages/process_securement.py", "공정별 확보율", ":material/monitoring:", False),
    ("app_pages/standard_target_capa.py", "표준 목표 Capa", ":material/track_changes:", False),
    ("app_pages/reference_integrity.py", "Dynamic Capa (구현중)", ":material/sync_alt:", False),
    ("app_pages/wip_status.py", "표준 대비 재공 현황 (구현중)", ":material/inventory_2:", False),
    (
        "app_pages/available_equipment_status.py",
        "가용설비 현황 (구현중)",
        ":material/precision_manufacturing:",
        False,
    ),
    ("app_pages/actual_efficiency.py", "효율 실적 (구현중)", ":material/speed:", False),
    ("app_pages/actual_upeh.py", "UPEH 실적 (구현중)", ":material/timer:", False),
    ("app_pages/space_status.py", "Space 현황 (구현중)", ":material/grid_view:", False),
]


def test_navigation_declares_the_expected_pages_in_sidebar_order() -> None:
    declared = [(spec.path, spec.title, spec.icon, spec.default) for spec in ALL_SPECS]

    assert declared == EXPECTED_PAGES


def test_every_declared_page_file_exists() -> None:
    missing = [spec.path for spec in ALL_SPECS if not (PROJECT_ROOT / spec.path).is_file()]

    assert not missing, f"선언된 페이지 파일이 없습니다: {missing}"


def test_exactly_one_page_is_the_default_entry_point() -> None:
    defaults = [spec.path for spec in ALL_SPECS if spec.default]

    assert defaults == [HOME.path]


def test_group_membership_matches_the_sidebar_sections() -> None:
    assert STATIC_CAPA.path == "app_pages/static_capa.py"
    assert len(STATIC_CAPA_SUBPAGES) == 4
    assert DYNAMIC_CAPA.path == "app_pages/reference_integrity.py"
    assert len(DYNAMIC_CAPA_SUBPAGES) == 5


def test_unimplemented_pages_use_one_suffix_matching_their_body_title() -> None:
    """사이드바 라벨과 페이지 본문 `st.title` 이 같은 표기를 써야 한다.

    이전에는 사이드바만 `(구현중)`·`(구현 중)`·`(DB 셋팅중)` 세 갈래였다.
    `Capa Chatbot` 은 본문이 "화면 초안" 이라고 밝히는데도 사이드바에만 표기가 없어
    가장 덜 된 화면이 완성된 것처럼 보였다.
    """
    for spec in (CAPA_CHATBOT, DYNAMIC_CAPA, *DYNAMIC_CAPA_SUBPAGES):
        assert spec.title.endswith(IMPLEMENTING_SUFFIX), spec.path
        body = (PROJECT_ROOT / spec.path).read_text(encoding="utf-8")
        assert f'st.title("{spec.title}")' in body, spec.path


def test_navigation_hides_the_builtin_sidebar_widget() -> None:
    """사이드바는 app.py가 직접 그리므로 기본 네비게이션 위젯을 숨긴다."""
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    positions = [
        ast.literal_eval(keyword.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "navigation"
        for keyword in node.keywords
        if keyword.arg == "position"
    ]

    assert positions == ["hidden"]
