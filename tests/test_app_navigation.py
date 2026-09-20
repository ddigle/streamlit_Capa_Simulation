# Purpose: 사이드바 페이지 인벤토리와 네비게이션 설정을 고정한다.

import ast
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.navigation import (
    ADMIN_AREA,
    ADMIN_BOX_PAGES,
    ALL_SPECS,
    CAPA_CHATBOT,
    DATA_PENDING_SUFFIX,
    DYNAMIC_CAPA,
    DYNAMIC_CAPA_SUBPAGES,
    HOME,
    IMPLEMENTING_SUFFIX,
    SCENARIO_MANAGEMENT,
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
    ("app_pages/load_conversion.py", "생산 계획", ":material/scale:", False),
    ("app_pages/reference_data.py", "기준 정보", ":material/settings:", False),
    ("app_pages/calculation_result.py", "산출 결과", ":material/monitoring:", False),
    ("app_pages/standard_target_capa.py", "표준 목표", ":material/track_changes:", False),
    ("app_pages/reference_integrity.py", "Dynamic Capa (구현중)", ":material/sync_alt:", False),
    (
        "app_pages/available_equipment_status.py",
        "가용설비 현황 (Data확보중)",
        ":material/precision_manufacturing:",
        False,
    ),
    ("app_pages/space_status.py", "Space 현황 (Data확보중)", ":material/grid_view:", False),
    ("app_pages/actual_efficiency.py", "효율 실적 (구현중)", ":material/speed:", False),
    ("app_pages/actual_upeh.py", "UPEH 실적 (구현중)", ":material/timer:", False),
    ("app_pages/yield_actual.py", "수율 실적 (구현중)", ":material/percent:", False),
    ("app_pages/wip_status.py", "표준 대비 재공 현황 (구현중)", ":material/inventory_2:", False),
    (
        "app_pages/admin_area.py",
        "Admin Area",
        ":material/admin_panel_settings:",
        False,
    ),
    ("app_pages/voc.py", "VOC", ":material/forum:", False),
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
    # 자원 현황(설비·공간) → 실적(효율·UPEH·수율) → 그 결과가 쌓인 재공 순서다.
    assert len(DYNAMIC_CAPA_SUBPAGES) == 6
    # 관리 기능이라 하위 페이지가 아니라 자기 박스로 사이드바 맨 아래에 있다. 그 박스에
    # VOC 가 **같은 층위로** 함께 선다 — 계산 화면이 아니라 사람이 쓰는 자리라 계산 그룹
    # 어디에도 안 맞고, 관리 화면과 게시판은 서로를 포함하지도 않는다.
    assert ADMIN_AREA.path == "app_pages/admin_area.py"
    assert [spec.path for spec in ADMIN_BOX_PAGES] == ["app_pages/voc.py"]
    assert ALL_SPECS[-len(ADMIN_BOX_PAGES) - 1] is ADMIN_AREA
    assert ALL_SPECS[-len(ADMIN_BOX_PAGES) :] == ADMIN_BOX_PAGES


def test_unimplemented_pages_use_one_suffix_matching_their_body_title() -> None:
    """사이드바 라벨과 페이지 본문 `st.title` 이 같은 표기를 써야 한다.

    이전에는 사이드바만 `(구현중)`·`(구현 중)`·`(DB 셋팅중)` 세 갈래였다.
    `Capa Chatbot` 은 본문이 "인터랙티브 프로토타입" 이라고 밝히는데도 사이드바에만 표기가 없어
    가장 덜 된 화면이 완성된 것처럼 보였다.

    표기는 둘이다. `(구현중)` 은 아직 못 만든 화면, `(Data확보중)` 은 화면은 다 만들었고
    연결할 데이터만 기다리는 화면이다. 사용자에게 뜻이 다르므로 갈라 둔다.
    """
    for spec in (CAPA_CHATBOT, DYNAMIC_CAPA, *DYNAMIC_CAPA_SUBPAGES):
        assert spec.title.endswith((IMPLEMENTING_SUFFIX, DATA_PENDING_SUFFIX)), spec.path
    # 사이드바 라벨과 본문 제목이 같아야 한다는 계약은 표기 유무와 무관하다. `Admin Area`
    # 는 이미 쓰는 관리 화면이라 표기를 달지 않지만 두 제목은 여전히 같아야 한다.
    for spec in (CAPA_CHATBOT, DYNAMIC_CAPA, *DYNAMIC_CAPA_SUBPAGES, ADMIN_AREA):
        # 본문은 공통 헤더가 그린다. 서식(한 줄/여러 줄)에 흔들리지 않도록 AST 로 첫 인자를
        # 읽는다.
        assert _page_header_title(PROJECT_ROOT / spec.path) == spec.title, spec.path
    assert not ADMIN_AREA.title.endswith((IMPLEMENTING_SUFFIX, DATA_PENDING_SUFFIX))


def _page_header_title(page_path: Path) -> str | None:
    tree = ast.parse(page_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"render_page_header", "render_page_header_with_status"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            return str(node.args[0].value)
    return None


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


# ----------------------------------------------------------------- 그룹 접기
#
# `app.py` 를 **파일 그대로** 연다. `AppTest.from_string` 은 못 쓴다 — `st.Page` 의 상대
# 경로가 주 스크립트 기준이라 임시 파일에서 열면 `app_pages/home.py` 를 못 찾는다.


@pytest.fixture
def _app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """빈 DuckDB 를 보는 `app.py`. 내장 시드가 부트스트랩을 채운다."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.month_range_picker as month_range_picker
    import capa_simulation.settings as settings

    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    # Components v2 위젯은 모듈 로드 때 등록되어 AppTest 인스턴스마다 살아 있지 않다.
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(
        month_range_picker,
        "render_month_range_picker",
        lambda *, start, end, min_month, max_month, key: (start, end),
    )
    return AppTest.from_file(str(APP_PATH), default_timeout=300)


def _expanded(app: AppTest) -> dict[str, bool]:
    """사이드바 그룹 상자의 펼침 상태. 상자가 없는 그룹은 여기 나오지 않는다."""
    return {
        element.label: element.proto.expanded
        for element in app.sidebar
        if type(element).__name__ == "Status"
    }


def test_only_the_group_holding_the_current_page_is_expanded(_app: AppTest) -> None:
    """그룹 상자는 **지금 보고 있는 페이지가 든 것 하나만** 펴진다.

    사이드바 링크는 열일곱 개고 대부분의 화면에서 그중 열 개는 지금 쓰지 않는 그룹의
    하위다. 접히지 않으면 조회기간·관리가 스크롤 밖으로 밀린다.

    **`expanded` 는 `st.navigation()` 이 돌아야 정해진다.** `page.url_path` 가 그 전에는
    아예 없어서(`AttributeError`) 두 줄의 순서를 바꾸면 사이드바가 통째로 죽는다 —
    그 순서를 여기서 함께 지킨다.
    """
    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    static, dynamic = STATIC_CAPA.title, DYNAMIC_CAPA.title
    # HOME 은 어느 그룹에도 속하지 않는다. 둘 다 접힌 채로 연다.
    assert _expanded(app) == {static: False, dynamic: False}

    for page_path, opened in (
        (STATIC_CAPA.path, static),
        # 하위 페이지도 그 그룹을 편다 — 대표 페이지만 보는 것이 아니다.
        (STATIC_CAPA_SUBPAGES[0].path, static),
        (DYNAMIC_CAPA_SUBPAGES[1].path, dynamic),
        (DYNAMIC_CAPA.path, dynamic),
        # 어느 그룹에도 없는 페이지에서는 다시 둘 다 접힌다.
        (CAPA_CHATBOT.path, None),
    ):
        app.switch_page(page_path).run()
        assert not list(app.exception), [element.message for element in app.exception]
        assert _expanded(app) == {
            static: opened == static,
            dynamic: opened == dynamic,
        }, page_path


def test_groups_without_subpages_get_no_box(_app: AppTest) -> None:
    """묶을 것이 없는 그룹은 상자를 두지 않는다.

    항목 하나짜리 상자는 테두리로 「여기 묶음이 있다」고 말해 놓고 아무것도 묶지 않는다.
    """
    app = _app.run()

    boxed = set(_expanded(app))
    assert CAPA_CHATBOT.title not in boxed
    assert SCENARIO_MANAGEMENT.title not in boxed
    assert boxed == {STATIC_CAPA.title, DYNAMIC_CAPA.title}
