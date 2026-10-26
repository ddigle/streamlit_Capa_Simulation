# Purpose: 사이드바 페이지 인벤토리와 네비게이션 설정을 고정한다.

import ast
import json
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from fragment_browser import install_fragment_browser
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from streamlit.proto.RootContainer_pb2 import RootContainer
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Caption, Expander, Status

from capa_simulation.components.availability_sheet_keys import GAP_SHEET_CHART_KEY
from capa_simulation.components.equipment_data_workspace import PENDING_FAB_KEY
from capa_simulation.components.equipment_scenario_status import EQUIPMENT_SCENARIO_FIELD_KEY
from capa_simulation.components.home_rendering import (
    BOTTLENECK_MONTHS_CHART_KEY,
    HOME_CELL_CHART_KEYS,
    KEY_PROCESS_MONTHS_CHART_KEY,
)
from capa_simulation.components.period_field import PERIOD_DIALOG_KEY, PERIOD_FIELD_KEY
from capa_simulation.components.plotly_touch_scroll import plotly_touch_scroll_script
from capa_simulation.components.process_capa_view import NEXT_MONTH_KEY
from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY
from capa_simulation.components.scenario_status import (
    SAVE_MODE,
    SAVE_REVISION_NAME_KEY,
    SCENARIO_DIALOG_KEY,
    SCENARIO_DIALOG_MODE_KEY,
    SCENARIO_FIELD_KEY,
    save_field_key,
)
from capa_simulation.components.tab_state import remembered_tab_key
from capa_simulation.components.theme_toggle import UNSAVED_EDITS_CSS_VARIABLE
from capa_simulation.constraint_simulation_state import CONSTRAINT_CHART_KEY, CONSTRAINT_SHEET_KEY
from capa_simulation.navigation import (
    ADMIN_AREA,
    ADMIN_BOX_PAGES,
    ALL_SPECS,
    AVAILABLE_EQUIPMENT_STATUS,
    CAPA_CHATBOT,
    CONDITIONS_SECTION,
    CONSTRAINT_SIMULATION,
    DYNAMIC_CAPA,
    DYNAMIC_CAPA_SUBPAGES,
    EQUIPMENT_GAP_TAB,
    EQUIPMENT_MAIN_TAB,
    EQUIPMENT_MASTER_TAB,
    EQUIPMENT_SUMMARY_TAB,
    EQUIPMENT_SUMMARY_TAB_KEY,
    EQUIPMENT_SUMMARY_TABS,
    EQUIPMENT_TAB_KEY,
    EQUIPMENT_TABS,
    EXECUTION_MANAGEMENT,
    EXECUTION_MANAGEMENT_SUBPAGES,
    HOME,
    IMPLEMENTING_SUFFIX,
    LOAD_CONVERSION,
    PROCESS_CAPA_DETAIL,
    REQUIRED_SHORTENING,
    SCENARIO_MANAGEMENT,
    SIDEBAR_GROUPS,
    SPACE_COLOR_BASIS_KEY,
    SPACE_DEFAULT_BASIS,
    SPACE_SHORTENING_BASIS,
    SPACE_STATUS,
    STANDARD_TARGET_CAPA,
    STATIC_CAPA,
    STATIC_CAPA_SUBPAGES,
    WIP_STATUS,
)
from capa_simulation.page_bootstrap import PAGE_VISIT_KEY
from capa_simulation.process_detail_state import (
    PROCESS_DETAIL_CANVAS_CHART_KEY,
    PROCESS_DETAIL_MONTH_KEY,
    PROCESS_DETAIL_PROCESS_KEY,
    PROCESS_DETAIL_VIEW_FRAGMENT_KEY,
)
from capa_simulation.scenario_preset_state import (
    MONTH_RANGE_KEY,
)
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.sidebar_status import (
    CONDITION_CARD_PREFIX,
    CONDITION_DIALOG_FRAGMENT_KEY,
    CONDITIONS_BOX_KEY,
    remembered_box_key,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"
# `_app` 이 바꿔 끼운 요약 컴포넌트가 받은 값. 회차마다 하나씩 쌓인다.
SENT_SUMMARIES: list[dict[str, Any]] = []

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
    (
        "app_pages/execution_management.py",
        "실행 관리",
        ":material/task_alt:",
        False,
    ),
    ("app_pages/process_capa_detail.py", "공정 Capa 상세", ":material/troubleshoot:", False),
    (
        "app_pages/required_shortening.py",
        "필요 단축 일정",
        ":material/event_upcoming:",
        False,
    ),
    ("app_pages/constraint_simulation.py", "제약 시뮬레이션", ":material/call_split:", False),
    (
        "app_pages/available_equipment_status.py",
        "가용설비 현황",
        ":material/precision_manufacturing:",
        False,
    ),
    ("app_pages/space_status.py", "Space 현황", ":material/grid_view:", False),
    ("app_pages/actual_efficiency.py", "효율 실적 (구현중)", ":material/speed:", False),
    ("app_pages/actual_upeh.py", "UPEH 실적 (구현중)", ":material/timer:", False),
    ("app_pages/yield_actual.py", "수율 실적 (구현중)", ":material/percent:", False),
    ("app_pages/reference_integrity.py", "Dynamic Capa", ":material/sync_alt:", False),
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
    """계산 그룹은 셋이다 — 약속(Static) → 이행(실행 관리) → 실적(Dynamic)
    (2026-10-17 사용자 결정). 화면 파일·제목·주소는 그룹을 옮겨도 그대로다."""
    assert [group.slug for group in SIDEBAR_GROUPS] == [
        "capa_chatbot",
        "scenario_management",
        "static_capa",
        "execution_management",
        "dynamic_capa",
    ]
    assert STATIC_CAPA.path == "app_pages/static_capa.py"
    # Static 하위 넷 — 표준 목표는 약속(대당 Capa)을 일·주로 푼 표준이라 Static 에 남는다.
    assert [spec.path for spec in STATIC_CAPA_SUBPAGES] == [
        LOAD_CONVERSION.path,
        "app_pages/reference_data.py",
        "app_pages/calculation_result.py",
        STANDARD_TARGET_CAPA.path,
    ]
    # 실행 관리 하위 여덟 — 공정 하나의 대책 → 전체 공정의 단축 계획(필요 단축 일정, 2026-10-18
    # 가용설비 현황 탭에서 뗐다) → 공정 하나의 미래 제약(제약 시뮬레이션, 2026-10-24) → 설비 일정 →
    # 현장 → 성능 실적 셋.
    assert EXECUTION_MANAGEMENT.path == "app_pages/execution_management.py"
    assert list(EXECUTION_MANAGEMENT_SUBPAGES[:5]) == [
        PROCESS_CAPA_DETAIL,
        REQUIRED_SHORTENING,
        CONSTRAINT_SIMULATION,
        AVAILABLE_EQUIPMENT_STATUS,
        SPACE_STATUS,
    ]
    assert [spec.path for spec in EXECUTION_MANAGEMENT_SUBPAGES[5:]] == [
        "app_pages/actual_efficiency.py",
        "app_pages/actual_upeh.py",
        "app_pages/yield_actual.py",
    ]
    # Dynamic 은 실현 Capa 머리와 재공 하나다. 머리 주소는 `dynamic_capa` 그대로다.
    assert DYNAMIC_CAPA.path == "app_pages/reference_integrity.py"
    assert DYNAMIC_CAPA.url_path == "dynamic_capa"
    assert DYNAMIC_CAPA_SUBPAGES == (WIP_STATUS,)
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

    표기는 `(구현중)` 하나다 — 아직 못 만든 화면에만 단다. 데이터만 기다리던 운영 화면의
    `(Data확보중)` 은 걷었다(2026-10-19 사용자 요청).
    """
    # 운영 화면은 표기가 없다. 공정 Capa 상세는 본문 머리가 공정 이름이라 제목 대조에서도 뺀다.
    operating = (
        REQUIRED_SHORTENING,
        CONSTRAINT_SIMULATION,
        AVAILABLE_EQUIPMENT_STATUS,
        SPACE_STATUS,
    )
    for spec in (PROCESS_CAPA_DETAIL, *operating):
        assert "(" not in spec.title, spec.path
    unfinished = [
        spec
        for spec in (*EXECUTION_MANAGEMENT_SUBPAGES, *DYNAMIC_CAPA_SUBPAGES)
        if spec is not PROCESS_CAPA_DETAIL and spec not in operating
    ]
    for spec in (CAPA_CHATBOT, *unfinished):
        assert spec.title.endswith(IMPLEMENTING_SUFFIX), spec.path
    # 그룹 머리는 표기를 달지 않는다(2026-09-29 사용자 결정) — 하위 화면이 각자 표기를 달고 있어
    # 머리에도 달면 그룹 전체가 안 된 것처럼 읽힌다. 성숙도는 본문 배지가 말한다.
    for head in (EXECUTION_MANAGEMENT, DYNAMIC_CAPA):
        assert not head.title.endswith(IMPLEMENTING_SUFFIX), head.path
    # 사이드바 라벨과 본문 제목이 같아야 한다는 계약은 표기 유무와 무관하다. `Admin Area`
    # 는 이미 쓰는 관리 화면이라 표기를 달지 않지만 두 제목은 여전히 같아야 한다.
    for spec in (
        CAPA_CHATBOT,
        EXECUTION_MANAGEMENT,
        DYNAMIC_CAPA,
        *unfinished,
        *operating,
        ADMIN_AREA,
    ):
        # 본문은 공통 헤더가 그린다. 서식(한 줄/여러 줄)에 흔들리지 않도록 AST 로 첫 인자를
        # 읽는다.
        assert _page_header_title(PROJECT_ROOT / spec.path) == spec.title, spec.path
    assert not ADMIN_AREA.title.endswith(IMPLEMENTING_SUFFIX)


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

    SENT_SUMMARIES.clear()
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.components.month_range_picker as month_range_picker
    import capa_simulation.settings as settings

    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    # Components v2 위젯은 모듈 로드 때 등록되어 AppTest 인스턴스마다 살아 있지 않다.
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    # 요약 계산은 그대로 돌리고 브라우저로 보내는 컴포넌트만 바꿔 끼운다.
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: SENT_SUMMARIES.append(kwargs))
    # 조회기간 팝업의 월 선택(Components v2). **컴포넌트 한 겹만** 바꿔 끼워 「적용」 트리거가 없는
    # 회차를 흉내 낸다 — 트리거를 읽고 검증하는 `render_month_range_apply` 와 `period_field` 는
    # 실제로 돈다(`_press_apply_with`).
    monkeypatch.setattr(
        month_range_picker,
        "_MONTH_RANGE_APPLY",
        lambda **kwargs: SimpleNamespace(apply=None),
    )
    return AppTest.from_file(str(APP_PATH), default_timeout=300)


# AppTest 는 확장 패널을 **아이콘 유무로** 두 이름에 나눠 담는다(아이콘이 있으면
# `Status`, 없으면 `Expander` — `element_tree.py` 의 `expandable` 분기). 아이콘은 서식이지
# 종류가 아니므로 둘 다 본다. 지금은 사이드바 상자가 전부 아이콘을 달아 `Status` 뿐이지만,
# 아이콘 없는 상자가 하나라도 생기면 한쪽만 보는 헬퍼는 그 상자를 통째로 잃는다.
_EXPANDER_ELEMENTS = (Status, Expander)


def _expanded(app: AppTest) -> dict[str, bool]:
    """사이드바 **그룹 상자**의 펼침 상태. 상자가 없는 그룹은 여기 나오지 않는다.

    `Support` 와 조건 카드도 같은 확장 패널이라 사이드바에는 그룹 말고도 확장 패널이 선다.
    이 헬퍼가 말하는 것은 「지금 보는 페이지가 든 그룹만 편다」는 **그룹 규칙 하나**이므로,
    그룹 제목을 단 것만 센다. 하위가 없는 그룹의
    제목도 함께 본다 — 그쪽에 펼침 장치가 생기는 것도 이 헬퍼가 잡아야 한다.
    """
    group_titles = {group.main.title for group in SIDEBAR_GROUPS}
    return {
        element.label: element.proto.expanded
        for element in app.sidebar
        if isinstance(element, _EXPANDER_ELEMENTS) and element.label in group_titles
    }


def _control_boxes(app: AppTest) -> dict[str, bool]:
    """`key` 를 단 확장 패널(`Support`·조건 카드)의 펼침 상태를 `key` 로 찾아 돌려준다.

    라벨로는 가를 수 없다 — 라벨은 화면 글자라 바뀔 수 있다.
    `key` 와 `on_change="rerun"` 을 함께 준 확장 패널은 위젯이라 id 끝이 그 `key` 다.
    그렇지 않은 그룹 상자는 id 가 비어 있어 여기 나오지 않는다.
    """
    found: dict[str, bool] = {}
    for element in app.sidebar:
        if not isinstance(element, _EXPANDER_ELEMENTS):
            continue
        widget_id = str(element.proto.id)
        if widget_id:
            found[widget_id.rsplit("-", 1)[-1]] = element.proto.expanded
    return found


def _app_constant(name: str) -> str:
    """`app.py` 의 최상위 문자열 상수. import 하면 앱이 통째로 실행되므로 AST 로 읽는다."""
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return str(ast.literal_eval(node.value))
    raise AssertionError(f"app.py 에 {name} 상수가 없습니다.")


def test_only_the_group_holding_the_current_page_is_expanded(_app: AppTest) -> None:
    """그룹 상자는 **지금 보고 있는 페이지가 든 것 하나만** 펴진다.

    사이드바 링크는 열아홉 개고 그 가운데 열넷이 세 계산 그룹(머리 + 하위) 안이다. 접히지
    않으면 조회기간·Support 가 스크롤 밖으로 밀린다.

    **`expanded` 는 `st.navigation()` 이 돌아야 정해진다.** `page.url_path` 가 그 전에는
    아예 없어서(`AttributeError`) 두 줄의 순서를 바꾸면 사이드바가 통째로 죽는다 —
    그 순서를 여기서 함께 지킨다.
    """
    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    static, execution, dynamic = (
        STATIC_CAPA.title,
        EXECUTION_MANAGEMENT.title,
        DYNAMIC_CAPA.title,
    )
    # HOME 은 어느 그룹에도 속하지 않는다. 셋 다 접힌 채로 연다.
    assert _expanded(app) == {static: False, execution: False, dynamic: False}

    for page_path, opened in (
        (STATIC_CAPA.path, static),
        # 하위 페이지도 그 그룹을 편다 — 대표 페이지만 보는 것이 아니다.
        (LOAD_CONVERSION.path, static),
        (STANDARD_TARGET_CAPA.path, static),
        (EXECUTION_MANAGEMENT.path, execution),
        (PROCESS_CAPA_DETAIL.path, execution),
        (SPACE_STATUS.path, execution),
        (WIP_STATUS.path, dynamic),
        (DYNAMIC_CAPA.path, dynamic),
        # 어느 그룹에도 없는 페이지에서는 다시 셋 다 접힌다.
        (CAPA_CHATBOT.path, None),
    ):
        app.switch_page(page_path).run()
        assert not list(app.exception), [element.message for element in app.exception]
        assert _expanded(app) == {
            static: opened == static,
            execution: opened == execution,
            dynamic: opened == dynamic,
        }, page_path


def test_the_execution_head_links_every_screen_of_its_group(_app: AppTest) -> None:
    """실행 관리 머리(데이터를 읽지 않는 목차)는 앱 안에서 하위 여섯과 Static·Dynamic 머리로 가는
    링크를 단다. 공통 조건도 조건 카드도 없어 「조회 조건」 구역이 서지 않고, 사이드바는 그 그룹만
    편다."""
    app = _app.run()
    app.switch_page(EXECUTION_MANAGEMENT.path).run()
    assert not list(app.exception), [element.message for element in app.exception]

    links = [link.proto for link in app.main.get("page_link")]
    labels = [link.label for link in links]
    assert labels == [
        "열기",
        "열기",
        *(spec.title for spec in EXECUTION_MANAGEMENT_SUBPAGES),
    ]
    assert _expanded(app) == {
        STATIC_CAPA.title: False,
        EXECUTION_MANAGEMENT.title: True,
        DYNAMIC_CAPA.title: False,
    }
    assert _common_boxes(app) == set()


def test_groups_without_subpages_are_boxed_but_not_expandable(_app: AppTest) -> None:
    """하위가 없는 그룹도 **상자에는 들어가되 펼침 장치는 갖지 않는다.**

    테두리는 사이드바에서 「한 칸」이라는 뜻이라 없으면 그 둘만 맨몸으로 서서 목록이 두
    층으로 읽힌다. 다만 펼칠 것이 없으므로 화살표까지 달면 눌러도 아무 일도 없는 장치가
    생긴다 — 상자는 주고 확장 패널은 주지 않는다.
    """
    app = _app.run()

    expandable = set(_expanded(app))
    assert expandable == {STATIC_CAPA.title, EXECUTION_MANAGEMENT.title, DYNAMIC_CAPA.title}
    assert CAPA_CHATBOT.title not in expandable
    assert SCENARIO_MANAGEMENT.title not in expandable


def test_the_scenario_field_reads_no_database_until_its_dialog_opens(
    _app: AppTest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """사이드바 시나리오 줄은 회차마다 저장소를 읽지 않는다 — 팝업을 연 동안에만 읽는다.

    전에는 접히는 상자가 모든 화면의 회차마다 시나리오 목록·최신 공식버전·리비전 목록을 읽었다
    (2026-10-10 통합 패널로 걷었다). 팝업을 열면 **부르는 순간의** `settings.DUCKDB_PATH` 를 연다 —
    기본 경로를 import 때 잡으면 픽스처가 `settings` 를 갈아끼워도 팝업만 저장소의
    `data/capa_simulation.duckdb` 를 만들고 잠근다(앱 서버가 떠 있는 개발 PC 에서 잠금 충돌).
    """
    import capa_simulation.components.scenario_status as scenario_status
    from capa_simulation.persistence.cache import get_scenario_repository

    opened: list[str] = []
    original = get_scenario_repository

    def _recording(database_path: str) -> Any:
        opened.append(database_path)
        return original(database_path)

    monkeypatch.setattr(scenario_status, "get_scenario_repository", _recording)

    app = _app.run()
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert opened == []

    app.button(key=SCENARIO_FIELD_KEY).click().run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert opened
    assert set(opened) == {str((tmp_path / "scenario.duckdb").resolve())}


# ------------------------------------------------------- 조건 패널과 접히는 상자
#
# 「조회 조건」 아래는 늘 펼친 통합 패널 하나(2026-10-10 사용자 결정)와 그 밑의 접히는 조건 카드다.
# 확인할 것은 셋이다 — 패널이 그 화면이 읽는 줄만 세우는가, 팝업이 세션 키로 열리고 닫히는가,
# 탭에 딸린 카드가 페이지를 왕복해도 제 펼침을 기억하는가.


def test_the_intro_overlay_is_drawn_before_the_bootstrap_on_every_run(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """입장 화면은 무거운 부트스트랩보다 **먼저**, 그리고 **매 회차** 그려진다.

    먼저여야 그동안을 덮고, 매 회차여야 첫 실행 도중의 rerun 에도 덮개가 내려가지 않는다. 툴바
    iframe(Guide·Print·테마 단추와 사이드바 앱 이름 라벨)은 입장 화면 바로 뒤·부트스트랩
    앞이다 — 첫 방문처럼 테마 스크립트가 새로고침할 로드는 그 세션이 버려지므로, 부트스트랩·요약을
    돌기 전에 새로고침이 걸려야 한다.
    """
    import capa_simulation.components.app_header as app_header
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.components.theme_toggle as theme_toggle
    import capa_simulation.components.typography as typography
    import capa_simulation.scenario_activation as scenario_activation

    order: list[str] = []
    original_bootstrap = scenario_activation.bootstrap_latest_official_scenario

    def _recording_bootstrap(*args: Any, **kwargs: Any) -> object:
        order.append("bootstrap")
        return original_bootstrap(*args, **kwargs)

    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: order.append("intro"))
    original_shell_style = app_header.render_shell_style

    def _recording_shell_style() -> None:
        # 진짜 스타일도 보낸다 — 인쇄 규칙이 든 그 스타일이 부트스트랩 앞에 나가는지가 요점이다.
        assert "@media print" in app_header.SHELL_STYLE
        order.append("shell")
        original_shell_style()

    monkeypatch.setattr(app_header, "render_shell_style", _recording_shell_style)
    original_typography = typography.render_typography_style

    def _recording_typography() -> None:
        order.append("type")
        original_typography()

    monkeypatch.setattr(typography, "render_typography_style", _recording_typography)
    monkeypatch.setattr(
        theme_toggle,
        "render_theme_toggle",
        lambda extra_scripts=(): order.append(f"toolbar:{len(extra_scripts)}"),
    )
    monkeypatch.setattr(intro_summary, "render_intro_summary", lambda path: order.append("summary"))
    monkeypatch.setattr(intro_summary, "warm_intro_summary", lambda path: order.append("warm"))
    monkeypatch.setattr(
        scenario_activation, "bootstrap_latest_official_scenario", _recording_bootstrap
    )

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    app.run()

    # 요약은 부트스트랩 뒤·페이지 앞이다 — 로딩에 들어가고, 페이지가 멈춰도 이미 보냈다. 툴바는
    # Guide·Summary·Print 스크립트 셋과 칸 선택 그림의 터치 스크롤 막이를 함께 싣는다. ⋮ 메뉴
    # 감춤과 인쇄 규칙을 담은 껍데기 스타일도 부트스트랩 앞이다 — 부트스트랩 오류 화면
    # (`st.stop()`)에서도 메뉴가 보이지 않고, 그 화면을
    # 인쇄해도 사이드바가 빠져야 한다. 서체 스타일(페이지 제목 등의 Archivo)도 그 바로 뒤다 — 오류
    # 화면의 제목도 같은 서체로 선다.
    # 「준비 중」으로 보낸 Summary GAP 은 페이지를 다 그린 **뒤** 만든다(`warm_intro_summary`).
    one_run = ["intro", "shell", "type", "toolbar:4", "bootstrap", "summary", "warm"]
    assert order == one_run * 2
    # 고정 문자열을 회차마다 한 번씩 보낸다 — 빠진 회차에는 규칙이 사라진다.
    sent = [el.proto.body for el in app.get("html") if el.proto.body == typography.TYPOGRAPHY_STYLE]
    assert len(sent) == 1


@pytest.mark.parametrize(("mode", "colour"), [("dark", "#131316"), ("light", "#FFFFFF")])
def test_every_run_paints_the_accent_button_text_for_its_theme(
    _app: AppTest, mode: str, colour: str
) -> None:
    """강조색으로 칠한 단추(primary·primary 폼 제출)·multiselect 고른 칩의 글자색 스타일을 매 회차
    그 회차 테마로 보낸다 — 어두운 테마의 밝은 강조색 위 Streamlit 흰 글자는 1.86:1 이었다(표준 목표
    「가용설비 붙여넣기」·표준 대비 재공 현황 조회 조건 칩). 밝은 테마는 흰 글자 그대로다."""
    from capa_simulation.components.accent_button_style import (
        ACCENT_BUTTON_SELECTORS,
        ACCENT_CHIP_SELECTORS,
    )

    selectors = (*ACCENT_BUTTON_SELECTORS, *ACCENT_CHIP_SELECTORS)
    rule = f"{', '.join(selectors)} {{ color: {colour}; }}"
    _app.query_params["theme"] = mode
    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    app.run()

    sent = [el.proto.body for el in app.get("html") if rule in el.proto.body]
    assert len(sent) == 1
    assert 'button[kind="primary"]:not(:disabled)' in sent[0]


def test_the_summary_gap_is_warmed_after_a_page_that_stops(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """페이지가 `st.stop()` 해도 Summary GAP 은 페이지 뒤에서 만든다(페이지보다 앞에서는 않는다)."""
    import streamlit as st

    import capa_simulation.components.intro_summary as intro_summary

    order: list[str] = []
    real_navigation = st.navigation

    def _stopping_navigation(*args: Any, **kwargs: Any) -> Any:
        page = real_navigation(*args, **kwargs)

        def _run() -> None:
            order.append("page")
            st.stop()

        monkeypatch.setattr(page, "run", _run)
        return page

    monkeypatch.setattr(st, "navigation", _stopping_navigation)
    monkeypatch.setattr(intro_summary, "render_intro_summary", lambda path: order.append("summary"))
    monkeypatch.setattr(intro_summary, "warm_intro_summary", lambda path: order.append("warm"))

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert order == ["summary", "page", "warm"]


@pytest.mark.parametrize(("stopped_by_page", "complete"), [(True, True), (False, False)])
def test_only_a_page_that_stops_itself_counts_as_a_completed_run(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch, stopped_by_page: bool, complete: bool
) -> None:
    """페이지가 `st.stop()` 으로 멈춘 실행은 끝까지 돈 실행이고, 다른 요청이 끊은 실행은 아니다.

    Streamlit 은 새 상호작용이 들어오면(`runner.fastReruns`, 기본값) 돌던 실행에 멈춤을 걸고 새
    실행을 따로 띄운다. 끊긴 실행은 다음 양보 지점에서 `st.stop()` 과 같은 멈춤 예외로 끝나 본문이
    반쯤 그려진 채다. 그 실행을 「끝났다」로 적으면 같은 때 도는 새 실행의 콜백(상자 여닫기·조건
    패널 값 칸)이 프래그먼트만 다시 돌려 본문이 반쯤 그려진 채 남는다 — 조회기간 「적용」 직후
    시나리오 칸을 누른 브라우저 확인에서 실제로 그렇게 됐다(2026-10-14). 끊긴 실행은 같은 예외를
    `st.stop()` 밖에서 던지는 것으로 흉내 낸다.
    """
    import streamlit as st
    from streamlit.runtime.scriptrunner_utils.exceptions import StopException

    from capa_simulation.sidebar_status import APP_RUN_STATE_KEY

    real_navigation = st.navigation

    def _stopping_navigation(*args: Any, **kwargs: Any) -> Any:
        page = real_navigation(*args, **kwargs)

        def _run() -> None:
            if stopped_by_page:
                st.stop()
            raise StopException()

        monkeypatch.setattr(page, "run", _run)
        return page

    monkeypatch.setattr(st, "navigation", _stopping_navigation)

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state[APP_RUN_STATE_KEY]["complete"] is complete


def test_the_intro_summary_sends_the_official_six_months_once_per_value(_app: AppTest) -> None:
    """내장 시드(공식버전 하나)에서 요약이 실제로 계산되어 나간다. 값은 회차마다 같다.

    같아야 Streamlit 이 다시 보내지 않고 브라우저 JS 도 다시 불리지 않는다.
    """
    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    app.run()

    assert len(SENT_SUMMARIES) == 2
    first, second = (sent["data"] for sent in SENT_SUMMARIES)
    assert first["available"] is True, first
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    count = first["count"]
    assert 1 <= count <= 6
    for key in ("months", "density", "wafer", "bn", "mix"):
        assert len(first[key]) == count, key
    assert first["products"] and all(item["color"].startswith("#") for item in first["products"])
    # 머리 줄 토글 셋의 값도 같은 회차에 함께 간다. 빈 저장소에는 선행 B/O·선행 입고 입력도 비교
    # 대상도 없으므로 셋 다 켤 수 없고 까닭을 단다.
    toggles = first["toggles"]
    assert set(toggles) == {"advance", "shipment", "comparison"}
    assert all(part["available"] is False and part["reason"] for part in toggles.values())


def _header_style(app: AppTest) -> str:
    """이 회차의 머리 띠 스타일(`stHeader` 가상요소 글이 든 `st.html`)."""
    bodies = [
        element.proto.body
        for element in app.get("html")
        if '[data-testid="stHeader"]::before' in element.proto.body
    ]
    assert len(bodies) == 1, len(bodies)
    return str(bodies[0])


def test_the_header_names_the_scenario_this_session_applied(_app: AppTest) -> None:
    """머리 띠 위 줄은 이 세션에 적용 중인 시나리오·리비전과 상태다(2026-10-06 사용자 결정). 빈
    저장소는 내장 시드를 공식 v1 로 올린다. 개발 정보는 머리 띠에 없다(사이드바 맨 아래 카드)."""
    from capa_simulation.services.builtin_seed import (
        BUILTIN_SEED_REVISION_NAME,
        BUILTIN_SEED_SCENARIO_NAME,
        BUILTIN_SEED_SOURCE_CODE,
    )
    from capa_simulation.settings import APP_CONTACT_EMAIL

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    style = _header_style(app)
    assert (
        f'content: "{BUILTIN_SEED_SCENARIO_NAME} · r1 {BUILTIN_SEED_REVISION_NAME} · 공식 v1";'
        in style
    )
    assert f'content: "{BUILTIN_SEED_SOURCE_CODE} · 적용 26.01–26.12 · 내장 시드 ' in style
    assert APP_CONTACT_EMAIL not in style


def test_the_header_reads_no_database_on_a_rerun(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HOME 을 무겁게 하지 않는다(2026-10-03 사용자 원칙). 머리 띠는 세션이 든 값만 읽는다 — 그리는
    동안 시나리오 저장소 메서드도, DuckDB 연결도 한 번도 부르지 않는다."""
    import capa_simulation.components.app_header as app_header
    import capa_simulation.persistence._sql_helpers as sql_helpers
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    calls: list[str] = []
    inside: list[int] = []
    for name, value in list(vars(DuckDBScenarioRepository).items()):
        if name.startswith("__") or not callable(value):
            continue

        def counted(
            *args: object, __name: str = name, __func: Any = value, **kwargs: object
        ) -> Any:
            if inside:
                calls.append(__name)
            return __func(*args, **kwargs)

        monkeypatch.setattr(DuckDBScenarioRepository, name, counted)
    original_connect = sql_helpers.connect

    def counted_connect(*args: Any, **kwargs: Any) -> Any:
        if inside:
            calls.append("connect")
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(sql_helpers, "connect", counted_connect)
    original_header = app_header.render_app_header
    rendered: list[int] = []

    def watched_header(**kwargs: Any) -> None:
        inside.append(1)
        try:
            original_header(**kwargs)
        finally:
            inside.pop()
        rendered.append(1)

    monkeypatch.setattr(app_header, "render_app_header", watched_header)

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    app.run()

    assert len(rendered) == 2
    assert calls == []


def test_the_home_main_case_chips_read_no_database_on_a_rerun(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """규칙 23 — HOME 제목 줄의 주요 Case 칩도 회차마다 DB 를 읽지 않는다.

    첫 회차만 주요 Case 재료를 쓰기 세대 키 캐시(`load_main_case_targets`)에 채우고, 다음 회차는
    저장소 메서드도 DuckDB 연결도 부르지 않는다. 공식 칩은 입장 화면 요약이 세션에 둔 값이다.
    """
    import capa_simulation.components.home_main_case_chips as chips
    import capa_simulation.persistence._sql_helpers as sql_helpers
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    runs: list[list[str]] = []
    watching: list[int] = []
    for name, value in list(vars(DuckDBScenarioRepository).items()):
        if name.startswith("__") or not callable(value):
            continue

        def counted(
            *args: object, __name: str = name, __func: Any = value, **kwargs: object
        ) -> Any:
            if watching:
                runs[-1].append(__name)
            return __func(*args, **kwargs)

        monkeypatch.setattr(DuckDBScenarioRepository, name, counted)
    original_connect = sql_helpers.connect

    def counted_connect(*args: Any, **kwargs: Any) -> Any:
        if watching:
            runs[-1].append("connect")
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(sql_helpers, "connect", counted_connect)
    original_chips = chips.render_main_case_chips

    def watched_chips(database_path: str) -> None:
        runs.append([])
        watching.append(1)
        try:
            original_chips(database_path)
        finally:
            watching.pop()

    monkeypatch.setattr(chips, "render_main_case_chips", watched_chips)

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    app = app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    assert len(runs) == 2
    # 첫 회차는 정말 읽는다 — 이 시험이 칩 안의 읽기를 잡는다는 표지다.
    assert "load_global_main_cases" in runs[0]
    assert runs[1] == []


def test_the_home_main_case_chips_follow_the_real_official_check(_app: AppTest) -> None:
    """실제 `app.py` 배선 — 입장 화면 요약의 공식버전 확인 → HOME 제목 줄 칩 → 사이드바 불러오기.

    새 세션은 공식버전으로 열리므로 공식 칩이 칠해져 있다(`latest_official_identity`). Case1 을
    지정해 누르면 활성 시나리오와 사이드바 칸이 그 리비전이 되고, 켜 둔 HOME 토글이 기본값으로
    돌아온다(콜백이 토글 위젯보다 먼저 적는다). 미지정 Case2 는 `Preference` 탭을 연다.
    """
    import capa_simulation.settings as settings
    from capa_simulation.components.home_main_case_chips import (
        CASE1_CHIP_KEY,
        CASE2_CHIP_KEY,
        OFFICIAL_CHIP_KEY,
    )
    from capa_simulation.home_state import (
        EDP_TOGGLE_KEY,
        HOME_PREFERENCE_TAB,
        HOME_TAB_KEY,
        HOME_TOGGLE_DEFAULTS,
    )
    from capa_simulation.persistence.cache import clear_global_main_cases_cache
    from capa_simulation.persistence.models import ScenarioCreate
    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.scenario_activation import (
        ACTIVE_PERSISTED_REVISION_ID_KEY,
        ACTIVE_PERSISTED_SCENARIO_ID_KEY,
    )

    def chip(app: AppTest, key: str) -> tuple[str, str, bool]:
        button = app.button(key=key)
        return str(button.label), str(button.proto.type), bool(button.disabled)

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    repository = DuckDBScenarioRepository(settings.DUCKDB_PATH)
    release = repository.latest_official_release()
    assert release is not None
    assert chip(app, OFFICIAL_CHIP_KEY) == (f"공식 v{release.release_no}", "primary", False)
    assert chip(app, CASE2_CHIP_KEY) == ("Case2", "secondary", False)

    base = repository.load_revision(release.revision_id)
    created = repository.create_scenario(
        ScenarioCreate(
            scenario_name="증설안",
            source_simulation_code="CASE",
            source_simulation_name="증설안",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="duckdb-rq-snapshot-v3",
        ),
        {name: frame.copy() for name, frame in base.tables.items()},
        base.preset,
    )
    repository.replace_global_main_case(
        1, created.scenario.scenario_id, created.revision.revision_id, source="시험"
    )
    clear_global_main_cases_cache()
    toggled = not HOME_TOGGLE_DEFAULTS[EDP_TOGGLE_KEY]
    app.session_state[EDP_TOGGLE_KEY] = toggled
    app = app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state[EDP_TOGGLE_KEY] is toggled

    app = app.button(key=CASE1_CHIP_KEY).click().run()
    assert not list(app.exception), [element.message for element in app.exception]

    assert (
        app.session_state[ACTIVE_PERSISTED_SCENARIO_ID_KEY],
        app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY],
    ) == (created.scenario.scenario_id, created.revision.revision_id)
    assert app.button(key=SCENARIO_FIELD_KEY).label == "증설안 · r1"
    assert app.session_state[EDP_TOGGLE_KEY] is HOME_TOGGLE_DEFAULTS[EDP_TOGGLE_KEY]
    assert chip(app, CASE1_CHIP_KEY)[1] == "primary"
    assert chip(app, OFFICIAL_CHIP_KEY)[1] == "secondary"

    app = app.button(key=CASE2_CHIP_KEY).click().run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state[HOME_TAB_KEY] == HOME_PREFERENCE_TAB


def test_the_bootstrap_error_screen_still_shows_the_app_name_in_the_header(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """부트스트랩이 실패해 `st.stop()` 으로 끝나는 화면에도 머리 띠가 선다. 올라온 시나리오가
    없으므로 앱 이름 두 줄이다(위 줄 메인 라벨 · 아래 줄 부제)."""
    import capa_simulation.scenario_activation as scenario_activation
    from capa_simulation.settings import APP_LABEL, APP_SUBTITLE

    def _failing_bootstrap(*args: object, **kwargs: object) -> bool:
        raise RuntimeError("부트스트랩 실패")

    monkeypatch.setattr(
        scenario_activation, "bootstrap_latest_official_scenario", _failing_bootstrap
    )

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert len(app.error) == 1

    style = _header_style(app)
    assert f'content: "{APP_LABEL}";' in style
    assert f'content: "{APP_SUBTITLE}";' in style


def test_the_header_marks_unsaved_edits(_app: AppTest) -> None:
    """미저장 판정은 사이드바 시나리오 줄의 「미저장 변경」과 같은
    함수다(`has_unsaved_scenario_changes`)."""
    from capa_simulation.scenario_activation import ACTIVE_PERSISTED_SESSION_REVISION_KEY

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    # 저장 표시를 한 칸 뒤로 돌리면 지금 편집 번호와 달라져 미저장으로 읽힌다.
    app.session_state[ACTIVE_PERSISTED_SESSION_REVISION_KEY] = (
        app.session_state[ACTIVE_PERSISTED_SESSION_REVISION_KEY] - 1
    )
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    style = _header_style(app)
    assert ' · 미저장 변경";' in style
    assert "공식 v1" not in style


def _has_theme_unsaved_marker(app: AppTest) -> bool:
    """이 회차에 테마 단추가 읽는 「저장하지 않은 편집」 표지(CSS 변수)가 섰는가."""
    marker = f"{UNSAVED_EDITS_CSS_VARIABLE}:1"
    return any(marker in element.proto.body for element in app.get("html"))


def test_the_theme_marker_counts_a_pending_fab_layout(_app: AppTest) -> None:
    """Space FAB 전체 배치는 설비 편집본 세대를 올리지 않고 따로 대기한다. 그 대기분만 있어도
    테마 단추가 묻게 표지를 단다 — 묻지 않고 새로고침하면 새 세션이 대기분을 잃는다."""
    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert not _has_theme_unsaved_marker(app)

    app.session_state[PENDING_FAB_KEY] = {"canvas": None, "marks": (), "base": (None, "")}
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _has_theme_unsaved_marker(app)


def test_the_theme_marker_counts_pending_unapplied_edits(_app: AppTest) -> None:
    """적용하지 않은 편집(편집표·붙여넣기 대기)은 시나리오에 들어 있지 않아 미저장 판정에 잡히지
    않는다. 사이드바 패널 맨 위 「적용 전 편집」 줄이 서는 회차면 테마 단추도 묻게 표지를 단다 —
    새로고침한 새 세션에는 그 편집이 없다."""
    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert not _has_theme_unsaved_marker(app)

    app.session_state["test_staged_paste"] = "붙여넣은 표"
    app.session_state["scenario_pending_edit_registry"] = {
        "load_conversion.py": ("생산 계획", {}, {"test_staged_paste": "PKG PLAN 붙여넣기"}, None)
    }
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert any("생산 계획 · PKG PLAN 붙여넣기" in caption.value for caption in app.sidebar.caption)
    assert _has_theme_unsaved_marker(app)


def _panel_fields(app: AppTest) -> list[str]:
    """조건 패널 안 값 칸(버튼)의 key 를 화면 차례대로."""
    keys = _sidebar_keys(app)
    if CONDITIONS_BOX_KEY not in keys:
        return []
    panel = list(app.sidebar.children.values())[keys.index(CONDITIONS_BOX_KEY)]
    return [str(button.key) for button in panel.button]


@pytest.mark.parametrize(
    "page_path,fields",
    [
        (
            HOME.path,
            [
                SCENARIO_FIELD_KEY,
                PERIOD_FIELD_KEY,
                "dashboard_bottleneck_process_dialog_open",
                "home_key_process_field",
            ],
        ),
        (SCENARIO_MANAGEMENT.path, [SCENARIO_FIELD_KEY, PERIOD_FIELD_KEY]),
        (STATIC_CAPA.path, [SCENARIO_FIELD_KEY, PERIOD_FIELD_KEY]),
        (ADMIN_AREA.path, [SCENARIO_FIELD_KEY]),
        (CAPA_CHATBOT.path, []),
    ],
)
def test_the_conditions_panel_holds_only_the_rows_the_screen_reads(
    _app: AppTest, page_path: str, fields: list[str]
) -> None:
    """패널은 **늘 펼친** 한 상자이고, 줄은 그 화면이 실제로 읽는 조건뿐이다(`PageSpec`).

    HOME 은 공통 두 줄 뒤에 페이지 칸 둘(공정 필터 — 세 탭 모두, 주요공정 히트맵 — Main 탭)을
    채운다. 접히는 상자가 아니므로 펼침 상태가 없다.
    """
    app = _app.run()
    if page_path != HOME.path:
        app.switch_page(page_path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _panel_fields(app) == fields
    assert CONDITIONS_BOX_KEY not in _control_boxes(app)


def test_the_home_heatmap_row_follows_the_main_tab_and_the_filter_stays(_app: AppTest) -> None:
    """주요공정 히트맵 줄은 Main 탭에서만, 공정 필터 줄은 세 탭 모두에서 선다.

    「사이드바 = 이 화면이 실제로 읽는 조건」(2026-09-29). 히트맵은 Main 에만 그려지고, 판정
    대상은 HOME 의 결론·Top5·상세 B/N 이 읽고 리비전 저장 때 프리셋에 담긴다.
    """
    app = _app.run()
    app.session_state["home_active_tab"] = ":material/tune: Preference"
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _panel_fields(app) == [
        SCENARIO_FIELD_KEY,
        PERIOD_FIELD_KEY,
        "dashboard_bottleneck_process_dialog_open",
    ]


@pytest.mark.parametrize(
    "opener,stale_key,opened_key",
    [
        # 시나리오·조회기간 칸: 페이지 팝업(HOME Past Data 붙여넣기)이 남은 채 연다.
        (SCENARIO_FIELD_KEY, "home_open_dialog", SCENARIO_DIALOG_KEY),
        (PERIOD_FIELD_KEY, "home_open_dialog", PERIOD_DIALOG_KEY),
        # 공정 필터·주요공정 히트맵 칸: 사이드바 팝업 열림 키가 남은 채 연다(칸을 누른 회차에만
        # 여는 팝업이라 열림 키가 없다).
        ("dashboard_bottleneck_process_dialog_open", SCENARIO_DIALOG_KEY, None),
        ("home_key_process_field", PERIOD_DIALOG_KEY, None),
    ],
)
def test_every_popup_opener_clears_the_other_popup_keys_first(
    _app: AppTest, tmp_path: Path, opener: str, stale_key: str, opened_key: str | None
) -> None:
    """팝업을 여는 칸 넷 모두 다른 팝업 열림 키부터 비운다(AGENTS 2장 — 여는 콜백의
    `forget_page_dialogs`). 한 실행에 팝업이 둘 불리면 `StreamlitInvalidLayoutContextError` 로
    화면이 멈춘다(2026-10-10 브라우저 실측). 2026-10-11 병합 전 리뷰가 넷 중 하나만 고정돼 있다고
    짚었다.
    """
    from capa_simulation.persistence.cache import clear_global_key_process_cache
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    app = _app.run()
    # 히트맵 칸은 프리셋이 있어야 눌린다. 프로필은 캐시 뒤라 심은 뒤 비운다.
    DuckDBScenarioRepository(tmp_path / "scenario.duckdb").replace_global_key_process_presets(
        [("A 그룹", ["DEMO_Chip_Attach"])], source="테스트"
    )
    clear_global_key_process_cache()
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    app.session_state[stale_key] = "월별" if stale_key == "home_open_dialog" else True
    app.button(key=opener).click().run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert stale_key not in app.session_state
    if opened_key is not None:
        assert app.session_state[opened_key] is True


def test_the_official_popup_opener_clears_the_other_popup_keys_first(
    _app: AppTest, tmp_path: Path
) -> None:
    """다섯째 여는 칸 — 시나리오 관리 카드의 「공식으로 지정…」도 다른 팝업 열림 키부터 비운다.

    사이드바 시나리오 팝업 열림 키가 남은 채 열면 한 실행에 팝업이 둘 불려
    `StreamlitInvalidLayoutContextError` 로 화면이 멈춘다. 2026-10-22 리뷰가 위 넷의 목록에 이 칸이
    빠져 여는 콜백의 `forget_page_dialogs` 를 지워도 시험이 통과한다고 짚었다.
    """
    from capa_simulation.components.pick_edit_table import TableDraft, draft_session_key
    from capa_simulation.components.scenario_management import (
        ACTION_KEY,
        LIST_EDITOR_KEY,
        OFFICIAL_DIALOG_KEY,
    )
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    app = _app.run()
    app.switch_page(SCENARIO_MANAGEMENT.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    (scenario,) = DuckDBScenarioRepository(tmp_path / "scenario.duckdb").list_scenarios()
    app.session_state[draft_session_key(LIST_EDITOR_KEY)] = TableDraft(picked=scenario.scenario_id)
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    app.session_state[SCENARIO_DIALOG_KEY] = True
    app.button(key=f"{ACTION_KEY}_official").click().run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert SCENARIO_DIALOG_KEY not in app.session_state
    assert app.session_state[OFFICIAL_DIALOG_KEY] == (
        scenario.scenario_id,
        scenario.active_revision_id,
    )


def test_the_scenario_dialog_stays_open_across_reruns_and_closes_on_leaving(
    _app: AppTest,
) -> None:
    """시나리오 팝업은 세션 키로 열린다 — 페이지가 다시 도는 회차에도 닫히지 않고, 페이지를
    옮기면 `forget_page_dialogs` 가 버린다(닫지 않고 떠나면 돌아왔을 때 저절로 뜨지 않게)."""
    app = _app.run()
    app.button(key=SCENARIO_FIELD_KEY).click().run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state[SCENARIO_DIALOG_KEY] is True
    assert "sidebar_load_revision" in {button.key for button in app.button}

    app.run()
    assert "sidebar_load_revision" in {button.key for button in app.button}

    app.switch_page(SCENARIO_MANAGEMENT.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert SCENARIO_DIALOG_KEY not in app.session_state
    assert "sidebar_load_revision" not in {button.key for button in app.button}


def test_the_page_visit_count_rises_only_when_the_page_changes(_app: AppTest) -> None:
    """방문 차례는 페이지가 바뀐 회차에만 오른다. 같은 페이지의 rerun 에서도 오르면 그 차례를 보는
    화면(설비 RawData 의 미리보기)이 브라우저에 입력이 그대로인데도 미리보기를 거둔다."""
    app = _app.run()
    first = app.session_state[PAGE_VISIT_KEY]
    app.run()
    assert app.session_state[PAGE_VISIT_KEY] == first

    app.switch_page(SCENARIO_MANAGEMENT.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state[PAGE_VISIT_KEY] == first + 1
    app.switch_page(HOME.path).run()
    assert app.session_state[PAGE_VISIT_KEY] == first + 2


def test_the_dialog_host_runs_on_every_full_run_even_where_no_field_stands(
    _app: AppTest,
) -> None:
    """팝업 호스트 프래그먼트는 두 줄이 다 서지 않는 화면에서도 매 전체 실행 불린다 — 이번
    실행에 등록되지 않은 프래그먼트는 여는 콜백도 팝업 닫기도 겨눌 수 없다. 그런 화면에서는 열림
    키를 버리는 갈래만 돈다(같은 페이지 회차라 `forget_page_dialogs` 가 아니라 호스트가 지운다)."""
    app = _app.run()
    app.switch_page(CAPA_CHATBOT.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert SCENARIO_FIELD_KEY not in {button.key for button in app.button}

    app.session_state[SCENARIO_DIALOG_KEY] = True
    app.session_state[PERIOD_DIALOG_KEY] = True
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert SCENARIO_DIALOG_KEY not in app.session_state
    assert PERIOD_DIALOG_KEY not in app.session_state


def _event_slots(messages: Sequence[ForwardMsg]) -> dict[int, tuple[str, str, str]]:
    """메시지가 이벤트 칸(본문 밖 최상위 칸)의 몇째 자리에 무엇을 썼나.

    값은 `(종류, html 본문, 프래그먼트 id)` 다.

    브라우저는 프래그먼트 회차에 받은 자리의 요소만 갈아 끼우고 나머지는 그대로 둔다.
    """
    slots: dict[int, tuple[str, str, str]] = {}
    for message in messages:
        if message.WhichOneof("type") != "delta":
            continue
        path = list(message.metadata.delta_path)
        if len(path) != 2 or path[0] != RootContainer.EVENT:
            continue
        delta = message.delta
        if delta.WhichOneof("type") == "add_block":
            kind, body = str(delta.add_block.WhichOneof("type")), ""
        else:
            kind = str(delta.new_element.WhichOneof("type"))
            body = delta.new_element.html.body if kind == "html" else ""
        slots[path[1]] = (kind, body, delta.fragment_id)
    return slots


def _open_home_for_fragment_runs(app: AppTest) -> AppTest:
    """HOME 을 앱 전체로 그린다.

    브라우저는 회차마다 지금 페이지의 표를 보내는데 AppTest 는 `switch_page` 뒤에야 그렇게 한다 —
    그래야 여는 콜백이 끝까지 돈 실행과 같은 페이지로 판정한다.
    """
    app.run()
    app.switch_page(HOME.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    return app


@pytest.mark.parametrize(
    ("field_key", "dialog_key"),
    [
        pytest.param(SCENARIO_FIELD_KEY, SCENARIO_DIALOG_KEY, id="scenario"),
        pytest.param(PERIOD_FIELD_KEY, PERIOD_DIALOG_KEY, id="period"),
    ],
)
def test_the_dialog_host_opens_and_closes_in_its_own_event_slot(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch, field_key: str, dialog_key: str
) -> None:
    """진짜 프래그먼트 회차로 본다 — 값 칸을 누르면 콜백만 도는 회차와 호스트만 도는 회차가 돌고
    페이지는 돌지 않는다. 닫기도 호스트만 돈다.

    호스트는 어느 갈래든 이벤트 칸에 **정확히 한 자리**를 쓴다(팝업이 아니면 빈 스타일
    자리표시자). 프래그먼트 회차는 이벤트 칸 쓰기 위치를 전체 실행에서 호스트를 부른 자리로 되돌리고
    브라우저는 그 자리만 갈아 끼우므로, 전체 실행에서 그 자리를 비워 두면 페이지의 첫 이벤트
    요소(툴바 Guide 단추를 보이게 하는 규칙)를 팝업이 덮어 다음 전체 실행까지 돌아오지 않는다.
    열고 닫는 회차가 쓰는 이벤트 칸 자리는 호스트 자리 하나뿐이어야 한다.
    """
    browser = install_fragment_browser(monkeypatch)
    app = _open_home_for_fragment_runs(_app)
    page_slots = _event_slots(browser.messages)
    host = browser.fragment_keyed(CONDITION_DIALOG_FRAGMENT_KEY)
    host_slots = [index for index, slot in page_slots.items() if slot[2] == host]
    assert len(host_slots) == 1, f"호스트가 전체 실행에서 쓴 이벤트 칸 자리: {host_slots}"
    (host_slot,) = host_slots
    assert page_slots[host_slot][:2] == ("html", "<style></style>")
    # 덮이면 안 되는 페이지 쪽 이벤트 요소가 실제로 그 뒤에 선다.
    assert any(
        index > host_slot and "#capa-guide-button" in body and "inline-block" in body
        for index, (_, body, _) in page_slots.items()
    )

    app.button(key=field_key).click().run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert browser.started == [[], [host]]
    # 페이지는 돌지 않았다 — 이 `run()` 의 델타는 모두 호스트(와 그 안 팝업)의 것이다.
    assert all(
        message.delta.fragment_id
        for message in browser.messages
        if message.WhichOneof("type") == "delta"
    )
    opened = _event_slots(browser.messages)
    assert list(opened) == [host_slot]
    assert opened[host_slot][0] == "dialog"

    # 닫기(X·바깥·Esc). AppTest 는 닫기를 흉내 내지 못해 `on_dismiss` 콜백의 일(열림 키 지우기)을
    # 하고 호스트만 다시 돌린다.
    browser.fragment_queue = [host]
    del app.session_state[dialog_key]
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert browser.started == [[host]]
    assert _event_slots(browser.messages) == {host_slot: page_slots[host_slot]}


def test_an_ignored_home_cell_click_reruns_the_figures_in_their_own_event_slots(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HOME 월 그림의 무시되는 클릭(과거 실적 칸·같은 칸 다시 누르기·더블클릭)은 그림
    프래그먼트(`render_home_figures`)만 다시 돌린다. 그 프래그먼트는 스타일만 든 `st.html`(구분
    컬럼 폭·라벨 칸 내림·월 캔버스 폭)을 이벤트 칸에 쓴다 — 프래그먼트 회차가 전체 실행 때와
    **같은 자리에 같은 내용**만 쓰는지 진짜 프래그먼트 회차로 본다. 다른 자리를 쓰면 페이지의
    이벤트 요소(툴바 Guide 단추를 보이게 하는 규칙)를 덮어 다음 전체 실행까지 돌아오지 않는다
    (2026-10-14 팝업 호스트 결함과 같은 부류).

    AppTest 는 Plotly 선택을 넣지 못한다. 무시되는 클릭의 콜백은 아무것도 하지 않으므로 그 회차는
    그림 프래그먼트만 도는 회차와 같다.
    """
    browser = install_fragment_browser(monkeypatch)
    app = _open_home_for_fragment_runs(_app)
    page_slots = _event_slots(browser.messages)
    figures = browser.fragment_of(BOTTLENECK_MONTHS_CHART_KEY)
    assert browser.fragment_of(KEY_PROCESS_MONTHS_CHART_KEY) == figures
    own = {index: slot for index, slot in page_slots.items() if slot[2] == figures}
    assert own, "그림 프래그먼트가 전체 실행에서 이벤트 칸에 쓴 것이 없다"
    assert all(kind == "html" and "<style>" in body for kind, body, _ in own.values())
    assert any(
        index not in own and "#capa-guide-button" in body and "inline-block" in body
        for index, (_, body, _) in page_slots.items()
    )

    browser.fragment_queue = [figures]
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert browser.started == [[figures]]
    assert all(
        message.delta.fragment_id
        for message in browser.messages
        if message.WhichOneof("type") == "delta"
    )
    assert _event_slots(browser.messages) == own


def test_the_toolbar_iframe_carries_the_touch_scroll_guard_for_home_cell_charts(
    _app: AppTest,
) -> None:
    """칸 선택을 켠 그림(HOME 두 월 그림·공정 Capa 상세 결합 캔버스·가용설비 비교 시트·제약
    시뮬레이션 그래프와 계산표) 위에서 시작한 터치가 화면을 스크롤하게 하는 막이는 테마 버튼 iframe
    에 한 번 실린다(`components/plotly_touch_scroll.py`). 빠지면 그 그림 위 터치 스크롤이 다시
    막힌다."""
    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    guard = plotly_touch_scroll_script(
        (
            *HOME_CELL_CHART_KEYS,
            PROCESS_DETAIL_CANVAS_CHART_KEY,
            GAP_SHEET_CHART_KEY,
            CONSTRAINT_CHART_KEY,
            CONSTRAINT_SHEET_KEY,
        )
    )
    assert f".st-key-{PROCESS_DETAIL_CANVAS_CHART_KEY} .js-plotly-plot" in guard
    assert f".st-key-{GAP_SHEET_CHART_KEY} .js-plotly-plot" in guard
    assert f".st-key-{CONSTRAINT_CHART_KEY} .js-plotly-plot" in guard
    assert f".st-key-{CONSTRAINT_SHEET_KEY} .js-plotly-plot" in guard
    frames = [str(element.proto.srcdoc) for element in app.get("iframe")]
    assert sum(frame.count(guard) for frame in frames) == 1


def test_the_scenario_dialog_writes_nothing_outside_itself_when_switching_to_save(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """팝업 안 조작(구획을 「새 리비전 저장」으로)은 팝업 프래그먼트만 돌고 이벤트 칸 최상위에
    아무것도 쓰지 않는다 — 팝업 본문이 스타일만 든 `st.html`·`st.toast` 를 쓰면 페이지의 이벤트
    요소를 덮는다."""
    browser = install_fragment_browser(monkeypatch)
    app = _open_home_for_fragment_runs(_app)
    app.button(key=SCENARIO_FIELD_KEY).click().run()
    assert browser.started[-1] == [browser.fragment_keyed(CONDITION_DIALOG_FRAGMENT_KEY)]

    dialog_body = browser.fragment_of(SCENARIO_DIALOG_MODE_KEY)
    browser.fragment_queue = [dialog_body]
    app.segmented_control(key=SCENARIO_DIALOG_MODE_KEY).set_value(SAVE_MODE).run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert browser.started == [[dialog_body]]
    assert _event_slots(browser.messages) == {}
    # 저장 구획이 실제로 섰다(리비전명 칸).
    assert any(widget.key == save_field_key(SAVE_REVISION_NAME_KEY) for widget in app.text_input)


def _calculation_snapshot(app: AppTest) -> dict[str, Any]:
    """계산 입력(활성 리비전·`content_token`·조회기간)과 본문 Figure·글."""
    active = app.session_state["active_scenario"]
    return {
        "content_token": active["content_token"],
        "revision": active["revision"],
        "period": app.session_state[MONTH_RANGE_KEY],
        "figures": [chart.proto.spec for chart in app.get("plotly_chart")],
        "markdown": [element.value for element in app.main.markdown],
    }


def test_opening_and_closing_a_condition_dialog_leaves_the_numbers_alone(_app: AppTest) -> None:
    """같은 숫자 — 값 칸으로 팝업을 열고 닫는 것은 열림 키와 초안만 바꾼다. 활성 리비전·
    `content_token`·조회기간과 HOME 의 Figure·글이 열기 전과 같다. AppTest 는 여는 콜백이 물러나는
    길(앱 전체 재실행)을 탄다 — 프래그먼트 회차는 페이지를 아예 다시 그리지 않는다."""
    app = _app.run()
    app.run()
    before = _calculation_snapshot(app)
    assert before["figures"]

    for field_key, dialog_key in (
        (SCENARIO_FIELD_KEY, SCENARIO_DIALOG_KEY),
        (PERIOD_FIELD_KEY, PERIOD_DIALOG_KEY),
    ):
        app.button(key=field_key).click().run()
        assert not list(app.exception), [element.message for element in app.exception]
        assert app.session_state[dialog_key] is True
        assert _calculation_snapshot(app) == before
        # 닫기(X·바깥·Esc). AppTest 는 닫기를 흉내 내지 못해 `on_dismiss` 콜백의 일을 한다.
        del app.session_state[dialog_key]
        app.run()
        assert _calculation_snapshot(app) == before


def _press_apply_with(monkeypatch: pytest.MonkeyPatch, applied: tuple[str, str] | None) -> None:
    """팝업 월 선택 컴포넌트의 「적용」 트리거를 흉내 낸다(Components v2 는 AppTest 에 없다).

    `applied` 가 있으면 다음 회차의 컴포넌트가 `apply` 트리거로 `{start, end}` 를 돌려준다 — 실제
    컴포넌트는 입력 칸 값과 누름을 한 트리거로 보낸다. 바꾸는 것은 컴포넌트 한 겹이라 그 트리거를
    읽고 검증하는 `render_month_range_apply`(JS→파이썬 계약)와 `period_field` 는 실제로 돈다.
    """
    import capa_simulation.components.month_range_picker as month_range_picker

    trigger = None if applied is None else {"start": applied[0], "end": applied[1]}
    monkeypatch.setattr(
        month_range_picker,
        "_MONTH_RANGE_APPLY",
        lambda **kwargs: SimpleNamespace(apply=trigger),
    )


def test_the_period_changes_only_when_applied_in_its_dialog(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """조회기간은 팝업의 「적용」을 눌러야 바뀐다(2026-10-10 — 전에는 고르는 즉시 바뀌었다).

    팝업 안에서 고른 범위는 초안이다. 여는 콜백이 다른 팝업 칸(시나리오)부터 비운다 — 한 실행에
    팝업은 하나뿐이다.
    """
    app = _app.run()
    before = app.session_state[MONTH_RANGE_KEY]
    app.button(key=SCENARIO_FIELD_KEY).click().run()
    app.button(key=PERIOD_FIELD_KEY).click().run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert SCENARIO_DIALOG_KEY not in app.session_state
    assert app.session_state[PERIOD_DIALOG_KEY] is True
    # 고르기만 해서는(「적용」 트리거가 없는 회차) 바뀌지 않는다.
    app.run()
    assert app.session_state[MONTH_RANGE_KEY] == before

    # 컴포넌트가 거꾸로 된 범위를 보내 오면(JS 가 막지만) 파이썬도 받지 않는다 — 팝업은 열린 채다.
    _press_apply_with(monkeypatch, ("2026-05", "2026-02"))
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state[MONTH_RANGE_KEY] == before
    assert app.session_state[PERIOD_DIALOG_KEY] is True

    _press_apply_with(monkeypatch, ("2026-02", "2026-04"))
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state[MONTH_RANGE_KEY] == ("2026-02", "2026-04")
    assert PERIOD_DIALOG_KEY not in app.session_state
    assert _range_caption(app) == ":material/check_circle: 적용 · 26.02–26.04"
    assert app.button(key=PERIOD_FIELD_KEY).label == "26.02 → 26.04"


def test_applying_a_period_keeps_the_unapplied_edit_list(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """조회기간 「적용」은 적용하지 않은 편집 목록을 비우지 않는다(2026-10-11 병합 전 리뷰).

    고른 범위가 바뀌어도 데이터가 있는 달이 그대로면 편집표의 원본도 그대로라 편집이 남는다. 목록을
    비우면 그 회차에 패널 맨 위 「적용 전 편집」 줄과 저장 확인이 사라져 편집을 잃을 수 있다.
    """
    registry_key = "scenario_pending_edit_registry"
    app = _app.run()
    app.session_state["test_staged_paste"] = "붙여넣은 표"
    app.session_state[registry_key] = {
        "load_conversion.py": ("생산 계획", {}, {"test_staged_paste": "PKG PLAN 붙여넣기"}, None)
    }
    app.run()
    notice = "생산 계획 · PKG PLAN 붙여넣기"
    assert any(notice in caption.value for caption in app.sidebar.caption)

    app.button(key=PERIOD_FIELD_KEY).click().run()
    _press_apply_with(monkeypatch, ("2026-01", "2027-06"))
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert PERIOD_DIALOG_KEY not in app.session_state
    assert registry_key in app.session_state
    assert any(notice in caption.value for caption in app.sidebar.caption)


def test_an_out_of_range_period_is_snapped_back_each_run(_app: AppTest) -> None:
    """고를 수 있는 범위 밖의 조회기간은 매 회차 범위 끝으로 끼운다(2026-10-11 병합 전 리뷰).

    전에는 사이드바 월 선택이 매 회차 그 일을 했다. 월 선택이 팝업으로 들어간 뒤에는 조회기간 줄이
    한다 — 범위 밖 시작은 최소 월, 범위 밖 끝은 최대 월이다.
    """
    from capa_simulation.settings import MONTH_SELECTION_END, MONTH_SELECTION_START, format_month

    app = _app.run()
    app.session_state[MONTH_RANGE_KEY] = ("2040-01", "2040-12")
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state[MONTH_RANGE_KEY] == (
        format_month(MONTH_SELECTION_START),
        format_month(MONTH_SELECTION_END),
    )


def test_the_shared_sample_switch_stays_on_across_sample_pages(_app: AppTest) -> None:
    """「샘플 데이터」 스위치는 샘플 화면 전체가 나눠 쓴다. 두 번째 화면에서도 켜진 채다."""
    app = _app
    for path in ("app_pages/actual_efficiency.py", "app_pages/actual_upeh.py"):
        app.switch_page(path).run()
        assert not list(app.exception), [element.message for element in app.exception]
        switch = next(element for element in app.toggle if element.key == SAMPLE_TOGGLE_KEY)
        assert (switch.proto.value, switch.proto.set_value) == (True, True), path


def test_a_tab_scoped_card_remembers_its_state_across_a_page_round_trip(_app: AppTest) -> None:
    """HOME Main 탭에만 서는 `LOB 표시 조건` 카드는 **기억 칸**이 없으면 왕복할 때마다 접힌다.

    Streamlit 은 한 회차에 만들어지지 않은 위젯의 값을 버린다. 다른 페이지에 있는 동안
    이 카드는 아예 그려지지 않으므로, 위젯 값만 믿으면 펴 둔 사람이 HOME 에 돌아올 때마다
    다시 펴야 한다.
    """
    card_key = f"{CONDITION_CARD_PREFIX}home"
    app = _app.run()
    app.session_state[card_key] = True
    app.run()
    assert _control_boxes(app)[card_key] is True

    app.switch_page(SCENARIO_MANAGEMENT.path).run()
    assert card_key not in _control_boxes(app)
    # 위젯 값은 버려져도 기억 칸은 남는다.
    assert app.session_state[remembered_box_key(card_key)][0] is True

    app.switch_page(HOME.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _control_boxes(app)[card_key] is True


def test_group_boxes_follow_the_page_only_when_the_page_changes(_app: AppTest) -> None:
    """그룹 상자는 **페이지가 바뀐 회차에만** 규칙대로 되돌리고, 그 안에서는 사용자 뜻대로 둔다.

    `expanded=` 는 처음 그릴 때만 읽힌다. 링크로 페이지를 옮기는 것은 새로고침이 아니라
    같은 화면 안의 rerun 이라, 프런트엔드는 이미 그려 둔 확장 패널의 여닫힘을 그대로 두고
    바뀐 값을 무시한다(브라우저 실측). 그래서 `key` 로 위젯을 만들고 세션 값을 페이지가
    바뀔 때만 「지금 보는 페이지가 든 그룹」으로 쓴다 — 매 회차 덮어쓰면 방금 누른 클릭을
    지우고, 한 번도 안 쓰면 옮겨도 따라오지 않는다.
    """
    static, execution, dynamic = (
        STATIC_CAPA.title,
        EXECUTION_MANAGEMENT.title,
        DYNAMIC_CAPA.title,
    )
    static_key = next(f"{group.slug}_box" for group in SIDEBAR_GROUPS if group.main is STATIC_CAPA)

    app = _app.run()
    app.switch_page(STATIC_CAPA.path).run()
    assert _expanded(app)[static] is True

    # 같은 페이지에서 사용자가 접었다. 다음 rerun 이 도로 펴면 안 된다.
    app.session_state[static_key] = False
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _expanded(app)[static] is False

    # 다른 그룹의 페이지로 옮기면 규칙이 다시 선다 — Static 은 접히고 Dynamic 이 펴진다.
    app.switch_page(DYNAMIC_CAPA.path).run()
    assert _expanded(app) == {static: False, execution: False, dynamic: True}

    # 거기서 사용자가 Static 을 펴 두면, 같은 페이지의 rerun 은 그것도 존중한다.
    app.session_state[static_key] = True
    app.run()
    assert _expanded(app) == {static: True, execution: False, dynamic: True}

    # 실행 관리 화면으로 옮기면 그 그룹만 편다 — 사용자가 편 Static 도 페이지가 바뀌면 접힌다.
    app.switch_page(PROCESS_CAPA_DETAIL.path).run()
    assert _expanded(app) == {static: False, execution: True, dynamic: False}


# ------------------------------------------------------------ 사이드바 칸의 차례
#
# 사이드바의 **이웃 관계**가 뜻을 나르는 자리가 둘이다. 둘 다 파이썬 호출 차례가 정하고,
# 어긋나도 예외 없이 화면만 틀어진다 — 칸의 차례를 AppTest 로 직접 본다.


def _sidebar_keys(app: AppTest) -> list[str]:
    """사이드바 **최상위** 칸의 key 를 화면 차례대로. key 가 없는 칸은 빈 문자열이다.

    `for element in app.sidebar` 는 상자 안까지 내려가 이웃을 가를 수 없어 최상위만 본다.
    key 를 준 컨테이너와 확장 패널은 id 끝이 그 key 다.
    """
    keys: list[str] = []
    for node in app.sidebar.children.values():
        identifier = str(getattr(getattr(node, "proto", None), "id", "") or "")
        keys.append(identifier.rsplit("-", 1)[-1] if identifier else "")
    return keys


@pytest.mark.parametrize("page_path", [HOME.path, SCENARIO_MANAGEMENT.path])
def test_the_conditions_heading_stands_right_before_the_panel(
    _app: AppTest, page_path: str
) -> None:
    """「조회 조건」 제목은 통합 조건 패널 **바로 앞**이다.

    제목은 그 아래 패널(시나리오·조회기간과 화면 칸)과 조건 카드가 다른 화면으로 가는 목록이
    아니라 지금 화면의 계산 조건이라고 말한다. 뒤로 밀리면 패널이 목록 쪽에 붙어 읽힌다.
    """
    app = _app.run()
    if page_path != HOME.path:
        app.switch_page(page_path).run()
    assert not list(app.exception), [element.message for element in app.exception]

    keys = _sidebar_keys(app)
    heading = keys.index(CONDITIONS_SECTION.key)
    assert keys[heading + 1] == CONDITIONS_BOX_KEY, keys
    # 선언한 두 글자가 실제로 들어 있다. 빈 컨테이너는 화면에 그려지지도 않는다.
    heading_block = list(app.sidebar.children.values())[heading]
    captions = [element.value for element in heading_block if isinstance(element, Caption)]
    assert captions == [CONDITIONS_SECTION.title, CONDITIONS_SECTION.hint]


@pytest.mark.parametrize("page_path", [HOME.path, SCENARIO_MANAGEMENT.path])
def test_the_applied_range_stands_in_the_period_name_row(_app: AppTest, page_path: str) -> None:
    """적용 기간은 조회기간 줄의 **이름 줄 오른쪽**이다 — 패널의 일반 흐름 안이다.

    전에는 접힌 상자의 요약 줄 위에 107px 절대좌표로 얹었다(2026-10-10 걷었다). 자리표시자는
    여전히 `app.py` 가 페이지보다 먼저 세운다 — 그 값은 페이지 계산 뒤에야 정해지고, 페이지가
    `st.stop()` 하면 그 뒤 코드는 돌지 않는다.
    """
    app = _app.run()
    if page_path != HOME.path:
        app.switch_page(page_path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _range_caption(app)


def test_the_support_box_opens_on_entering_its_pages_and_never_forces_closed(
    _app: AppTest,
) -> None:
    """`Support` 상자는 안의 화면(Admin Area·VOC)으로 **들어온 회차에만** 펴진다.

    접혀 있으면 그 화면의 「지금 여기」 표시가 상자 안에 가려져 사이드바 어디에도 지금
    자리가 보이지 않는다. 떠날 때는 접지 않는다 — 조회 컨트롤 상자는 사용자가 여닫은 대로
    기억하는 규칙이라, 억지로 접으면 편 채로 두려던 사람의 뜻을 지운다. 같은 페이지 안에서
    사용자가 접은 것도 그대로 둔다.
    """
    support_key = _app_constant("ADMIN_BOX_KEY")
    app = _app.run()
    assert _control_boxes(app)[support_key] is False

    app.switch_page(ADMIN_AREA.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _control_boxes(app)[support_key] is True

    # 떠나도 접지 않는다.
    app.switch_page(CAPA_CHATBOT.path).run()
    assert _control_boxes(app)[support_key] is True

    # 다른 쪽 화면(VOC)으로 들어와 사용자가 접으면, 같은 페이지의 다음 회차도 접힌 채다.
    app.switch_page(ADMIN_BOX_PAGES[0].path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _control_boxes(app)[support_key] is True
    app.session_state[support_key] = False
    app.run()
    assert _control_boxes(app)[support_key] is False


# --------------------------------------------------- 조회기간 요약 줄의 선택·적용
#
# 「✓ 적용」은 **이 화면이 이 범위를 읽었다**는 뜻이다. 공통 사이드바는 고른 범위를 중립
# 「선택」으로만 적고, 조회기간을 읽는 화면(`resolve_effective_months`·HOME)이 「✓ 적용」으로
# 덮는다. 범위를 읽은 뒤 계산이 멈추면 「계산 멈춤」으로 거둔다.


def _find_block(node: Any, suffix: str) -> Any:
    """사이드바 트리에서 id 가 `suffix` 로 끝나는 칸(key 를 준 컨테이너)을 찾는다."""
    for child in getattr(node, "children", {}).values():
        identifier = str(getattr(getattr(child, "proto", None), "id", "") or "")
        if identifier.endswith(suffix):
            return child
        found = _find_block(child, suffix)
        if found is not None:
            return found
    return None


def _range_caption(app: AppTest) -> str:
    """조회기간 이름 줄 오른쪽의 적용 기간 글자(자리표시자)."""
    row = _find_block(app.sidebar, "condition_name_period")
    assert row is not None, "조회기간 이름 줄이 없습니다"
    captions = [element.value for element in row if isinstance(element, Caption)]
    # 첫 캡션은 이름(「조회기간」), 둘째가 자리표시자다.
    assert captions[0] == "조회기간", captions
    (caption,) = captions[1:]
    return str(caption)


def _run_with_range(app: AppTest, start: str, end: str) -> AppTest:
    """첫 회차를 돌린 **뒤** 조회기간을 좁혀 다시 돌린다.

    첫 회차는 공식 시나리오를 올리며 그 프리셋의 조회기간(시나리오 전체)을 세션에 심는다.
    먼저 심어 두면 그 값에 덮인다.
    """
    app.run()
    app.session_state[MONTH_RANGE_KEY] = (start, end)
    return app.run()


def test_the_range_says_applied_only_where_the_screen_read_it(_app: AppTest) -> None:
    """HOME 은 「✓ 적용」, 범위를 저장할 때 담기만 하는 시나리오 관리는 중립 「선택」이다."""
    app = _run_with_range(_app, "2026-01", "2026-03")
    assert not list(app.exception), [element.message for element in app.exception]
    assert _range_caption(app) == ":material/check_circle: 적용 · 26.01–26.03"

    app.switch_page(SCENARIO_MANAGEMENT.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _range_caption(app) == "선택 · 26.01–26.03"


def test_a_stopped_calculation_withdraws_applied(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """조회기간 **밖** 달의 기준정보 오류로 계산이 멈추면 「✓ 적용」 대신 「계산 멈춤」이다.

    Capa 는 시나리오 전체 기간을 한 번에 계산해 보지 않는 달의 오류로도 멈춘다. 사이드바가
    「✓ 적용」인 채 본문이 「계산을 멈췄습니다」를 말하면 둘이 어긋난다. 내장 시드에서
    마지막 달의 가동률을 빼 실제 계산을 멈춘다(가동률은 중립값이 없어 하드 오류다).
    """
    import capa_simulation.application_bootstrap as application_bootstrap

    seed = build_builtin_seed_dataset()
    run_rate = seed.reference_tables["RQ_RUN_RATE"]
    months = pd.to_numeric(run_rate["생산계획년월"])
    broken_tables = dict(seed.reference_tables)
    broken_tables["RQ_RUN_RATE"] = run_rate.loc[months.ne(int(months.max()))].reset_index(drop=True)
    broken_seed = replace(seed, reference_tables=broken_tables)
    monkeypatch.setattr(application_bootstrap, "build_builtin_seed_dataset", lambda: broken_seed)

    app = _run_with_range(_app, "2026-01", "2026-03")
    # 산출 결과·표준 목표는 대당 Capa·소요대수 프레임을 풀지 않는 키 전용 캐시로 오류를 낸다.
    # 그 길로도 같은 자리·같은 문구로 멈추는지 함께 본다.
    for page_path in (
        HOME.path,
        STATIC_CAPA.path,
        "app_pages/calculation_result.py",
        "app_pages/standard_target_capa.py",
    ):
        if page_path != HOME.path:
            app.switch_page(page_path).run()
        assert not list(app.exception), [element.message for element in app.exception]
        errors = [str(element.value) for element in app.error]
        assert any("밖의 달에 기준정보 오류가 있어 계산을 멈췄습니다" in e for e in errors), (
            page_path,
            errors,
        )
        assert _range_caption(app) == ":material/block: 계산 멈춤", page_path


def test_a_securement_error_on_static_capa_keeps_applied(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """대당 Capa·소요대수 계산은 섰고 확보율 단계에서 난 오류는 「계산 멈춤」이 아니다.

    Static Capa 는 확보율을 키 전용 캐시 하나로 꺼내고, 그 호출이 오류를 낼 때만 시나리오 계산이
    멈춘 것인지 가른다. 확보율 오류(가용대수 없는 공정 등)는 본문에 그 문구로 뜨고 사이드바는
    「✓ 적용」 그대로다.
    """
    import streamlit as st

    import capa_simulation.services.simulation_cache as simulation_cache

    app = _run_with_range(_app, "2026-01", "2026-03")
    assert not list(app.exception), [element.message for element in app.exception]

    def failing(*_args: object, **_kwargs: object) -> pd.DataFrame:
        raise ValueError("시험용 확보율 오류")

    monkeypatch.setattr(simulation_cache, "calculate_securement_rate", failing)
    # 확보율 칸이 HOME 회차에 이미 찼다. 비워야 이 화면이 확보율을 다시 계산한다.
    st.cache_data.clear()
    app.switch_page(STATIC_CAPA.path).run()

    assert not list(app.exception), [element.message for element in app.exception]
    errors = [str(element.value) for element in app.error]
    assert any("시험용 확보율 오류" in error for error in errors), errors
    assert _range_caption(app) == ":material/check_circle: 적용 · 26.01–26.03"


# ------------------------------------------------ 화면이 읽는 공통 조건만 세운다
#
# 사이드바 「조회 조건」은 지금 화면이 **실제로 읽는** 조건만 모은다(2026-09-29 사용자 결정).
# 무엇을 읽는지는 `navigation.PageSpec` 의 선언이 말하고 `app.py` 가 그대로 따른다.


def _common_boxes(app: AppTest) -> set[str]:
    keys = set(_sidebar_keys(app))
    fields = set(_panel_fields(app))
    return {
        name
        for name, present in (
            ("heading", CONDITIONS_SECTION.key in keys),
            ("scenario", SCENARIO_FIELD_KEY in fields),
            ("period", PERIOD_FIELD_KEY in fields),
            ("equipment", EQUIPMENT_SCENARIO_FIELD_KEY in fields),
        )
        if present
    }


def test_a_screen_that_reads_no_common_condition_shows_none(_app: AppTest) -> None:
    app = _app.run()
    app.switch_page(CAPA_CHATBOT.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _common_boxes(app) == set()


def test_a_screen_with_only_its_own_card_keeps_the_heading(_app: AppTest) -> None:
    """VOC 는 공통 조건을 읽지 않지만 글 목록 필터가 자기 조건 카드라 제목은 선다."""
    app = _app.run()
    app.switch_page(ADMIN_BOX_PAGES[0].path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _common_boxes(app) == {"heading"}
    assert {"voc_category_filter", "voc_open_only"} <= {
        widget.key for widget in (*app.sidebar.multiselect, *app.sidebar.toggle)
    }


def _heading_content_keys(app: AppTest) -> set[str]:
    """「조회 조건」 제목 아래에 설 상자(조건 패널·카드) 가운데 사이드바 최상위에 있는 것의 key.

    사이드바 CSS(`sidebar_style.lone_conditions_heading_selector`)는 이것이 하나도 없을 때만 제목을
    감춘다. AppTest 는 CSS 를 계산하지 않으므로 그 조건이 되는 칸을 직접 본다.
    """
    return {
        key
        for key in _sidebar_keys(app)
        if key == CONDITIONS_BOX_KEY or key.startswith(CONDITION_CARD_PREFIX)
    }


def test_a_card_only_screen_that_stops_before_its_card_leaves_the_heading_alone(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """카드를 그리기 전에 멈춘 회차에는 제목 아래 상자가 하나도 없어 CSS 가 제목을 감춘다.

    제목은 늘 페이지보다 먼저 같은 자리에 선다 — 회차마다 미뤘다 채우면 rerun 마다 제목이 사라지고
    카드가 튀었다(2026-10-07 8543 실측). VOC 게시판을 읽지 못하면 페이지는 오류만 적고 멈추는데,
    그때 제목 아래 상자가 없다는 것(CSS 가 감추는 조건)을 여기서 본다. 규칙 자체는
    `tests/test_sidebar_stylesheet.py` 가 지킨다.
    """
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    app = _app.run()
    readable = DuckDBScenarioRepository.list_voc_posts

    def _unreadable(_self: object) -> pd.DataFrame:
        raise RuntimeError("VOC 게시판을 읽지 못함")

    monkeypatch.setattr(DuckDBScenarioRepository, "list_voc_posts", _unreadable)
    app.switch_page(ADMIN_BOX_PAGES[0].path).run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert any("VOC 게시판을 읽지 못함" in element.value for element in app.error)
    assert _common_boxes(app) == {"heading"}
    assert _heading_content_keys(app) == set()

    # 다시 읽히면 같은 세션의 다음 회차에 카드가 서 제목이 다시 보인다(제목 칸은 그대로다).
    monkeypatch.setattr(DuckDBScenarioRepository, "list_voc_posts", readable)
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _common_boxes(app) == {"heading"}
    assert _heading_content_keys(app) == {f"{CONDITION_CARD_PREFIX}voc"}


# ------------------------------------------------------------ 사이드바 맨 아래 앱 정보 카드


def _credit_card_captions(app: AppTest) -> list[str]:
    """사이드바 최상위의 앱 정보 카드 안 캡션들. 카드가 정확히 하나여야 한다."""
    from capa_simulation.components.app_credits import APP_CREDITS_KEY

    keys = _sidebar_keys(app)
    assert keys.count(APP_CREDITS_KEY) == 1, keys
    block = list(app.sidebar.children.values())[keys.index(APP_CREDITS_KEY)]
    return [element.value for element in block if isinstance(element, Caption)]


def _assert_two_credit_lines(captions: list[str]) -> None:
    """앱·버전·배포 한 줄과 개발 팀·문의처 한 줄, 그것뿐이다(2026-10-07 사용자 결정)."""
    from capa_simulation.components.app_credits import credit_lines

    assert captions == ["  \n".join(credit_lines())]
    (text,) = captions
    assert len(text.split("\n")) == 2, text
    assert "인증번호" not in text and "반출" not in text


@pytest.mark.parametrize("page_path", [HOME.path, SCENARIO_MANAGEMENT.path, ADMIN_AREA.path])
def test_the_app_credits_card_stands_in_the_sidebar_on_every_screen(
    _app: AppTest, page_path: str
) -> None:
    """앱 정보는 모든 화면의 사이드바 카드 하나다. Admin Area 본문에는 없다.

    사이드바 맨 아래 자리와 바닥 고정은 CSS(`sidebar_style`)가 지키고 규칙은
    `tests/test_sidebar_stylesheet.py` 가 본다. 여기서는 카드가 서는지와 그 두 줄을 본다.
    """
    from capa_simulation.settings import APP_CONTACT_EMAIL

    app = _app.run()
    if page_path != HOME.path:
        app.switch_page(page_path).run()
    assert not list(app.exception), [element.message for element in app.exception]

    _assert_two_credit_lines(_credit_card_captions(app))
    assert not any(APP_CONTACT_EMAIL in caption.value for caption in app.main.caption)


def test_the_app_credits_card_survives_a_screen_that_stops_early(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """카드는 페이지보다 **먼저** 그린다 — 페이지가 `st.stop()` 해도 남는다. VOC 게시판을 읽지
    못하면 VOC 는 오류만 적고 멈춘다. 그 회차에도 카드가 서고, 「조회 조건」 제목을 살리는 상자로
    세지 않는다(제목은 CSS 가 감춘다)."""
    from capa_simulation.components.app_credits import APP_CREDITS_KEY
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    def _unreadable(_self: object) -> pd.DataFrame:
        raise RuntimeError("VOC 게시판을 읽지 못함")

    app = _app.run()
    monkeypatch.setattr(DuckDBScenarioRepository, "list_voc_posts", _unreadable)
    app.switch_page(ADMIN_BOX_PAGES[0].path).run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert any("VOC 게시판을 읽지 못함" in element.value for element in app.error)
    _assert_two_credit_lines(_credit_card_captions(app))
    assert _heading_content_keys(app) == set()
    # CSS 는 조건 카드를 클래스 **부분 일치**(`[class*="st-key-condition_card_"]`)로 센다.
    assert f"st-key-{CONDITION_CARD_PREFIX}" not in f"st-key-{APP_CREDITS_KEY}"


def test_support_and_the_credits_card_keep_one_sidebar_slot_on_every_screen(
    _app: AppTest,
) -> None:
    """`Support` 상자와 앱 정보 카드는 화면마다 사이드바 최상위의 **같은 순번**이다.

    Streamlit 은 사이드바 요소를 key 가 아니라 순번으로 맞춰 갈아 끼운다. 순번이 화면마다 다르면
    페이지를 옮기는 동안 지난 회차의 사본이 옛 순번에 흐리게 남고, CSS 의 `order`·`sticky` 가 그
    사본까지 맨 아래로 끌어내려 두 벌로 보인다. 그래서 둘은 화면마다 수가 달라지는 조회 조건
    구역보다 앞에 선다. 고른 화면은 공통 조건이 모두 서는 HOME, 아무것도 서지 않는 Chatbot,
    제목만 서는 VOC, 시나리오만 서는 시나리오 관리다.
    """
    from capa_simulation.components.app_credits import APP_CREDITS_KEY

    support_key = _app_constant("ADMIN_BOX_KEY")
    app = _app.run()
    slots: dict[str, tuple[int, int]] = {}
    for page_path in (
        HOME.path,
        CAPA_CHATBOT.path,
        ADMIN_BOX_PAGES[0].path,
        SCENARIO_MANAGEMENT.path,
        ADMIN_AREA.path,
        HOME.path,
    ):
        if page_path != HOME.path or slots:
            app.switch_page(page_path).run()
        assert not list(app.exception), [element.message for element in app.exception]
        keys = _sidebar_keys(app)
        assert keys.count(support_key) == 1 and keys.count(APP_CREDITS_KEY) == 1, keys
        slots[page_path] = (keys.index(support_key), keys.index(APP_CREDITS_KEY))
        if CONDITIONS_SECTION.key in keys:
            assert keys.index(APP_CREDITS_KEY) < keys.index(CONDITIONS_SECTION.key), keys

    assert len(set(slots.values())) == 1, slots


def test_a_screen_that_reads_only_the_scenario_shows_only_its_box(_app: AppTest) -> None:
    app = _app.run()
    app.switch_page(ADMIN_AREA.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _common_boxes(app) == {"heading", "scenario"}


def test_hidden_boxes_keep_their_choice_for_the_screens_that_read_them(_app: AppTest) -> None:
    """상자를 세우지 않은 동안에도 고른 범위는 남는다 — 돌아오면 그 범위로 계산한다."""
    app = _run_with_range(_app, "2026-01", "2026-03")
    app.switch_page(ADMIN_BOX_PAGES[0].path).run()
    assert app.session_state[MONTH_RANGE_KEY] == ("2026-01", "2026-03")

    app.switch_page(HOME.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _range_caption(app) == ":material/check_circle: 적용 · 26.01–26.03"


def test_a_tab_scoped_screen_shows_the_common_boxes_only_on_that_tab(_app: AppTest) -> None:
    """가용설비 현황은 `Summary` › `Static 대비 일정` 탭만 활성 시나리오·조회기간을 읽는다.

    바깥 탭 ① 「설비 마스터」(처음 여는 탭)는 카드도 공통 조건도 없지만 설비 시나리오를
    편집·저장하는 탭이라 그 줄만 서고, Summary 는 안쪽 탭으로 가른다(`SubTabs`).
    """
    equipment = AVAILABLE_EQUIPMENT_STATUS
    assert equipment.condition_tabs is not None
    app = _app.run()
    app.switch_page(equipment.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _common_boxes(app) == {"heading", "equipment"}

    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_SUMMARY_TAB
    app.session_state[EQUIPMENT_SUMMARY_TAB_KEY] = EQUIPMENT_GAP_TAB
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _common_boxes(app) == {"heading", "scenario", "period", "equipment"}

    # Main 은 공통 조건을 읽지 않지만 자기 조건 카드(`설비 조회 조건`)가 있어 제목은 서고, 설비
    # 시나리오 줄이 패널에 선다.
    app.session_state[EQUIPMENT_SUMMARY_TAB_KEY] = EQUIPMENT_MAIN_TAB
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _common_boxes(app) == {"heading", "equipment"}

    # 다시 ① 로 — 안쪽에 Static 대비 일정을 남겨 두어도 바깥이 ① 이면 공통 조건 줄을 세우지 않는다.
    app.session_state[EQUIPMENT_SUMMARY_TAB_KEY] = EQUIPMENT_GAP_TAB
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _common_boxes(app) == {"heading", "equipment"}


@pytest.fixture
def _fleet_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """`_app` 과 같되 설비 DB 에 오늘에 맞춘 합성 fleet 저장본과 그 공정 Cut-off 를 넣는다 — 필요
    단축 일정 카드(「도면에서 보기」 는 저장본 fleet 에서만 선다)와 Space 필요 단축 보기가 계획까지
    돈다."""
    from datetime import date

    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.components.month_range_picker as month_range_picker
    import capa_simulation.components.required_shortening_panel as required_shortening_panel
    import capa_simulation.settings as settings
    from capa_simulation.persistence.equipment_cache import clear_equipment_repository
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
    from capa_simulation.services.equipment_contract import empty_equipment_baseline
    from capa_simulation.services.equipment_samples import (
        sample_downtime_schedule,
        sample_equipment_master,
    )

    equipment_path = tmp_path / "equipment.duckdb"
    repository = DuckDBEquipmentRepository(equipment_path)
    repository.initialize()
    today = date.today()
    # 합성 fleet 의 공정을 내장 시드의 세 공정으로 바꿔 시나리오 소요대수와 맞댄다(이름이 다르면
    # 「맞댄 공정 없음」 으로 멈춘다).
    master = sample_equipment_master(anchor_date=today)
    seed = ("DEMO_Chip_Attach", "DEMO_Wafer_Inspect", "DEMO_Final_Test")
    names = sorted(set(master["공정소분류"]))
    master["공정소분류"] = master["공정소분류"].map(
        {name: seed[index % len(seed)] for index, name in enumerate(names)}
    )
    # 지금 가용이 넉넉하면 모자란 달이 없어 카드가 서지 않는다 — Qual 이 아직 오지 않은 호기만 남겨
    # 그 호기들을 당겨야 하는 계획을 만든다.
    master = master.loc[
        master["Qual일정"].isna() | master["Qual일정"].gt(pd.Timestamp(today))
    ].reset_index(drop=True)
    downtime = sample_downtime_schedule(anchor_date=today)
    downtime = downtime.loc[downtime["설비명"].isin(master["설비명"])].reset_index(drop=True)
    repository.save_snapshot(empty_equipment_baseline(), master, downtime, note="처음")
    processes = list(seed)
    repository.save_process_cutoff(
        pd.DataFrame(
            {
                "공정": processes,
                "Cutoff일수": [10.0] * len(processes),
                "비고": [None] * len(processes),
            }
        )
    )
    SENT_SUMMARIES.clear()
    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", equipment_path)
    # 필요 단축 일정 패널은 판정 기준·LOB 줄을 읽을 때 모듈을 읽을 때 받은 `DUCKDB_PATH` 를 쓴다 —
    # 같은 프로세스에서 먼저 불러온 패널이면 저장소 DB 자리라, 카드까지 그리는 이 시험이 저장소 DB
    # 를 만든다 (`conftest` 의 저장소 DB 검사). 그 이름도 갈아 끼운다.
    monkeypatch.setattr(required_shortening_panel, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: SENT_SUMMARIES.append(kwargs))
    monkeypatch.setattr(
        month_range_picker, "_MONTH_RANGE_APPLY", lambda **kwargs: SimpleNamespace(apply=None)
    )
    clear_equipment_repository()
    return AppTest.from_file(str(APP_PATH), default_timeout=300)


def test_space_shows_the_common_boxes_only_while_the_shortening_basis_is_chosen(
    _fleet_app: AppTest,
) -> None:
    """D4 B — Space 현황은 사이드바 색 기준이 `필요 단축` 인 동안만 활성 시나리오·조회기간을 읽어 그
    두 줄을 세운다(`ConditionTabs` 를 보기 값으로). 실제 `app.py` 가 라디오 값을 읽고, 페이지는 켠
    회차에 예외 없이 계획까지 돈다(본문 조작 줄의 목표 확보율이 선다)."""
    app = _fleet_app.run()
    app.switch_page(SPACE_STATUS.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _common_boxes(app) == {"heading", "equipment"}

    app.sidebar.radio(key=SPACE_COLOR_BASIS_KEY).set_value(SPACE_SHORTENING_BASIS).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _common_boxes(app) == {"heading", "scenario", "period", "equipment"}
    assert [
        item
        for item in app.main.get("button_group")
        if getattr(item, "label", None) == "목표 확보율"
    ]
    assert not [
        item for item in app.main.warning if "필요 단축을 칠하지 못했습니다" in str(item.value)
    ], [str(item.value) for item in app.main.warning]

    app.sidebar.radio(key=SPACE_COLOR_BASIS_KEY).set_value(SPACE_DEFAULT_BASIS).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _common_boxes(app) == {"heading", "equipment"}


def test_the_shortening_card_links_to_space_and_the_arrival_shows_the_rows_at_once(
    _fleet_app: AppTest,
) -> None:
    """필요 단축 일정 카드의 「도면에서 보기」 는 실제 `st.page_link`(Space 경로·`layer=short`
    주소)로 선다(단독 실행의 물러선 글이 아니다). 그 주소로 Space 에 들어온 회차는 페이지가 색
    기준을 적고 한 번 더 돌아(`st.rerun`) 사이드바 시나리오·조회기간 줄이 그 회차에 바로 선다 —
    `app.py` 가 사이드바를 페이지보다 먼저 그리므로 다시 돌지 않으면 한 회차 늦는다."""
    app = _fleet_app.run()
    app.switch_page(REQUIRED_SHORTENING.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    links = [
        link.proto for link in app.main.get("page_link") if link.proto.label == "도면에서 보기"
    ]
    assert links, [link.proto.label for link in app.main.get("page_link")]
    # 실제 내비게이션의 Space 페이지(주소 이름 = 파일 이름)로 간다.
    assert {link.page for link in links} == {Path(SPACE_STATUS.path).stem}
    assert all("layer=short" in link.query_string for link in links)
    assert not [
        caption
        for caption in app.main.caption
        if "사이드바 Space 현황에서 색 기준" in str(caption.value)
    ]
    query = links[0].query_string

    app.switch_page(SPACE_STATUS.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _common_boxes(app) == {"heading", "equipment"}
    for name, value in (part.split("=", 1) for part in query.split("&")):
        from urllib.parse import unquote_plus

        app.query_params[name] = unquote_plus(value)
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state[SPACE_COLOR_BASIS_KEY] == SPACE_SHORTENING_BASIS
    assert _common_boxes(app) == {"heading", "scenario", "period", "equipment"}
    assert "layer" not in app.query_params


def test_the_sidebar_reads_the_innermost_tab_and_ignores_old_labels() -> None:
    """`ConditionTabs.active_label`(사이드바 `app.active_condition_tab`)은 바깥 탭이 안쪽 탭을
    품었으면 안쪽 라벨을 돌려준다. 위젯 값 → 기억 칸 → 첫 탭 차례이고, 먼저 찾은 값이 라벨 목록
    밖(개편 전 「RawData」 등)이면 `stateful_tabs` 처럼 첫 탭으로 본다 — 사이드바와 본문이 한 회차
    어긋나지 않게."""
    state: dict[str, object] = {}
    spec = AVAILABLE_EQUIPMENT_STATUS
    tabs = spec.condition_tabs
    assert tabs is not None and tabs.sub is not None
    assert tabs.sub.parent == EQUIPMENT_SUMMARY_TAB

    def active() -> str:
        assert tabs is not None
        return tabs.active_label(state)

    assert active() == EQUIPMENT_MASTER_TAB

    state[EQUIPMENT_TAB_KEY] = ":material/table_rows: RawData"
    assert active() == EQUIPMENT_MASTER_TAB

    state[EQUIPMENT_TAB_KEY] = EQUIPMENT_SUMMARY_TAB
    assert active() == EQUIPMENT_MAIN_TAB
    state[remembered_tab_key(EQUIPMENT_SUMMARY_TAB_KEY)] = EQUIPMENT_GAP_TAB
    assert active() == EQUIPMENT_GAP_TAB
    state[EQUIPMENT_SUMMARY_TAB_KEY] = ":material/tune: Preference"
    assert active() == EQUIPMENT_MAIN_TAB
    state[EQUIPMENT_SUMMARY_TAB_KEY] = EQUIPMENT_MAIN_TAB
    assert active() == EQUIPMENT_MAIN_TAB

    # 위젯 값이 없으면 기억 칸 — 다른 화면에서 Summary › Static 대비 일정으로 보낸 꼴.
    state.clear()
    state[remembered_tab_key(EQUIPMENT_TAB_KEY)] = EQUIPMENT_SUMMARY_TAB
    state[remembered_tab_key(EQUIPMENT_SUMMARY_TAB_KEY)] = EQUIPMENT_GAP_TAB
    assert active() == EQUIPMENT_GAP_TAB
    assert spec.reads_common_conditions_on(active())


def test_every_declared_condition_tab_is_a_real_label() -> None:
    """선언한 탭 라벨이 페이지의 실제 탭과 어긋나면 그 탭에서도 상자가 영영 서지 않는다. 페이지는
    선언의 라벨 목록 그대로 탭을 세우고, 안쪽 탭은 바깥 Summary 안에서 세운다."""
    source = (PROJECT_ROOT / AVAILABLE_EQUIPMENT_STATUS.path).read_text(encoding="utf-8")
    assert "stateful_tabs(EQUIPMENT_TABS, key=EQUIPMENT_TAB_KEY)" in source
    assert "stateful_tabs(EQUIPMENT_SUMMARY_TABS, key=EQUIPMENT_SUMMARY_TAB_KEY)" in source
    tabs = AVAILABLE_EQUIPMENT_STATUS.condition_tabs
    assert tabs is not None and tabs.sub is not None
    assert tabs.tabs == EQUIPMENT_TABS and tabs.first in tabs.tabs
    assert tabs.sub.parent in tabs.tabs
    assert tabs.sub.tabs == EQUIPMENT_SUMMARY_TABS and tabs.sub.first in tabs.sub.tabs
    inner = set(tabs.sub.tabs)
    assert tabs.labels <= inner and (tabs.card_labels or set()) <= inner


# ----------------------------------------------------------------- 설비 DB 핀
#
# 설비 DB 핀은 rerun 한 번만 사는 **화면 한정** 핀이다. 선언과 어긋나면 이득이 조용히
# 사라진다. 핀은 첫 연결 때 잡히는 게으른 핀이라, 대상으로 적는 것과 실제로 여는 것을 따로 본다.


def test_only_the_screens_that_reopen_the_equipment_db_declare_its_pin() -> None:
    """가용설비 현황·필요 단축 일정·공정 Capa 상세·제약 시뮬레이션(설비 운영 스냅샷을 읽기만 하되 한
    회차에 여러 번 연다)과 Space 현황(공식 스냅샷·설비 시나리오 목록·공통 최신·도면을 한 회차에
    따로 읽는다), 시나리오 관리(「설비 시나리오」 구획이 목록·리비전·공통 최신을 따로 읽는다 —
    2026-10-24)다."""
    declared = {spec.path for spec in ALL_SPECS if spec.uses_equipment_db}
    assert declared == {
        AVAILABLE_EQUIPMENT_STATUS.path,
        REQUIRED_SHORTENING.path,
        PROCESS_CAPA_DETAIL.path,
        CONSTRAINT_SIMULATION.path,
        SPACE_STATUS.path,
        SCENARIO_MANAGEMENT.path,
    }


def test_the_process_detail_page_opens_from_its_address_inside_the_app(_app: AppTest) -> None:
    """HOME 칸 클릭은 `st.switch_page(공정 Capa 상세, query_params=…)` 다(콜백 쪽은
    `tests/test_process_detail_state.py`). 실제 `app.py` 내비게이션에서 그 주소로 들어오면 사이드바
    `공정 상세 조건` 카드의 공정 상자가 그 공정을 보이고, 읽은 키만 지워 테마 인자는 남는다.
    """
    app = _app.run()
    app.switch_page(PROCESS_CAPA_DETAIL.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    options = list(app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).options)
    target = options[-1]

    app.query_params.update({"process": target, "from": "home"})
    app.query_params["theme"] = "dark"
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).value == target
    assert "process" not in app.query_params
    assert "from" not in app.query_params
    assert app.query_params.get("theme") == ["dark"]


def test_a_month_step_on_the_process_detail_reruns_only_its_view_inside_the_app(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """공정 Capa 상세의 ◀▶·칸 누름은 본문 프래그먼트(`process_detail_view`)만 **한 번** 다시
    돌린다 — `app.py` 가 끝까지 돈 실행 표지를 세운 실제 앱에서 본다. 콜백이 `st.rerun(<key>)` 를
    부르면 콜백만 도는 회차가 하나 더 돈다(그래서 `rerun_app_unless_alone`). 그 회차는 이벤트
    칸에 앱 전체 회차의 그 프래그먼트와 같은 자리만 쓴다."""
    browser = install_fragment_browser(monkeypatch)
    app = _app.run()
    app.switch_page(PROCESS_CAPA_DETAIL.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    view = browser.fragment_keyed(PROCESS_DETAIL_VIEW_FRAGMENT_KEY)
    own = {
        slot: (kind, body)
        for slot, (kind, body, owner) in _event_slots(browser.messages).items()
        if owner == view
    }
    before = app.session_state[PROCESS_DETAIL_MONTH_KEY]

    browser.fragment_queue = [view]
    app.button(key=NEXT_MONTH_KEY).click().run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert browser.started == [[view]]
    assert app.session_state[PROCESS_DETAIL_MONTH_KEY] > before
    assert {
        slot: (kind, body) for slot, (kind, body, _) in _event_slots(browser.messages).items()
    } == own


def test_the_equipment_db_is_pinned_only_on_the_screen_that_declares_it(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`app.py` 는 실행마다 핀 함수를 새로 import 하므로 기록용 대역이 그대로 불린다."""
    import capa_simulation.persistence._sql_helpers as sql_helpers
    import capa_simulation.settings as settings

    pinned: list[tuple[Path, ...]] = []
    original = sql_helpers.pinned_connections

    def recording(*database_paths: Path) -> Any:
        pinned.append(database_paths)
        return original(*database_paths)

    monkeypatch.setattr(sql_helpers, "pinned_connections", recording)
    equipment_db = settings.EQUIPMENT_DUCKDB_PATH

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert pinned == [(settings.DUCKDB_PATH,)]

    pinned.clear()
    app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert pinned == [(settings.DUCKDB_PATH,), (equipment_db,)]

    # 설비 시나리오를 공식으로 보는 Space 현황도 핀을 건다. HOME 으로 가면 다시 걸지 않는다.
    pinned.clear()
    app.switch_page(SPACE_STATUS.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert pinned == [(settings.DUCKDB_PATH,), (equipment_db,)]
    pinned.clear()
    app.switch_page(HOME.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert pinned == [(settings.DUCKDB_PATH,)]
    # 시나리오 관리도 설비 DB 를 핀 대상에 적는다(「설비 시나리오」 구획). 게으른 핀이라 시뮬레이션
    # 구획만 그린 회차에는 설비 DB 를 열지 않는다 — 아래 시험이 연결 수로 본다.
    pinned.clear()
    app.switch_page(SCENARIO_MANAGEMENT.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert pinned == [(settings.DUCKDB_PATH,), (equipment_db,)]


def test_the_run_pin_opens_a_database_only_on_a_rerun_that_reads_it(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """실행 핀은 게으르다 — 그 회차에 DB 를 읽는 저장소 연결이 있을 때만 핀 하나를 더한다.

    같은 화면 재실행에서 시나리오 DB 를 읽지 않는 화면(Chatbot)은 그 DB 를 한 번도 열지 않고,
    읽는 화면은 「읽기 N + 핀 1」로 인스턴스 하나를 나눠 쓴다. 핀을 블록 시작에 열면 읽지 않는
    화면도 회차마다 인스턴스 생성(20ms 안팎)을 내고, 핀을 아예 빼면 읽는 화면이 읽기마다
    인스턴스를 다시 만든다 — 둘 다 이 테스트가 잡는다.
    """
    import duckdb

    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.persistence.equipment_cache as equipment_cache
    import capa_simulation.persistence.equipment_repository as equipment_repository
    import capa_simulation.persistence.repository as repository
    import capa_simulation.settings as settings

    # 입장 화면 요약의 공식버전 재확인(`RECHECK_SECONDS`)은 첫 회차 한 번으로 고정한다. 측정 회차
    # 전에 그 주기가 지나면 어느 화면이든 DB 를 한 번 더 읽어, 느린 환경에서 Chatbot 의 「읽기 0」이
    # 시각에 따라 흔들린다.
    monkeypatch.setattr(intro_summary, "RECHECK_SECONDS", float("inf"))
    scenario_db = str(settings.DUCKDB_PATH.resolve())
    equipment_db = str(settings.EQUIPMENT_DUCKDB_PATH.resolve())
    opened: list[str] = []
    reads: list[str] = []
    real_connect = duckdb.connect

    def counted_open(*args: Any, **kwargs: Any) -> Any:
        opened.append(str(Path(str(args[0])).resolve()))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(duckdb, "connect", counted_open)
    for module in (repository, equipment_repository):
        original = module.connect

        def counted_read(database_path: Path, __original: Any = original) -> Any:
            reads.append(str(Path(database_path).resolve()))
            return __original(database_path)

        monkeypatch.setattr(module, "connect", counted_read)

    def warm_rerun(
        path: str, before: Callable[[], None] = lambda: None
    ) -> tuple[dict[str, int], dict[str, int]]:
        app.switch_page(path).run()
        app.run()
        before()
        opened.clear()
        reads.clear()
        app.run()
        assert not list(app.exception), [element.message for element in app.exception]
        return (
            {db: opened.count(db) for db in (scenario_db, equipment_db)},
            {db: reads.count(db) for db in (scenario_db, equipment_db)},
        )

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    scenario_reads: dict[str, int] = {}
    for path in (CAPA_CHATBOT.path, EXECUTION_MANAGEMENT.path, HOME.path, SCENARIO_MANAGEMENT.path):
        opens, read_counts = warm_rerun(path)
        scenario_reads[path] = read_counts[scenario_db]
        expected = read_counts[scenario_db] + (1 if read_counts[scenario_db] else 0)
        assert opens[scenario_db] == expected, (path, opens, read_counts)
        if path in (EXECUTION_MANAGEMENT.path, SCENARIO_MANAGEMENT.path):
            # 실행 관리 머리는 데이터를 읽지 않는다 — 설비 DB 도 열지 않는다. 시나리오 관리는 설비
            # DB 핀을 선언했지만 「시뮬레이션 시나리오」 쪽(처음 값)만 그린 회차에는 설비 DB 를
            # 열지 않는다(게으른 핀).
            assert opens[equipment_db] == read_counts[equipment_db] == 0, (opens, read_counts)
    # Chatbot·실행 관리 머리는 시나리오 DB 를 읽지 않아 열지도 않는다. 시나리오 관리는 회차마다
    # 목록을 읽으므로 핀이 실제로 잡히는 길도 지난다.
    assert scenario_reads[CAPA_CHATBOT.path] == 0
    assert scenario_reads[EXECUTION_MANAGEMENT.path] == 0
    assert scenario_reads[SCENARIO_MANAGEMENT.path] >= 2

    # 설비 DB 핀을 선언한 화면도 같은 꼴이다. 바뀐 것이 없는 회차는 최신 리비전 id·Cut-off 를
    # 캐시에서 받아 설비 DB 를 읽지 않으므로 열지도 않는다.
    opens, read_counts = warm_rerun(AVAILABLE_EQUIPMENT_STATUS.path)
    assert read_counts[equipment_db] == 0, (opens, read_counts)
    assert opens[equipment_db] == 0, (opens, read_counts)

    # 캐시가 빈 회차(저장 직후 꼴)는 설비 DB 를 여러 번 읽고, 핀 하나로 인스턴스를 나눠 쓴다.
    def forget_equipment_reads() -> None:
        equipment_cache.clear_equipment_snapshot_cache()
        equipment_cache.clear_process_cutoff_cache()

    opens, read_counts = warm_rerun(AVAILABLE_EQUIPMENT_STATUS.path, forget_equipment_reads)
    assert read_counts[equipment_db] >= 2, (opens, read_counts)
    assert opens[equipment_db] == read_counts[equipment_db] + 1, (opens, read_counts)


def test_a_database_newer_than_the_code_is_warned_on_the_screens_that_open_it(
    _app: AppTest,
) -> None:
    """예전 배포로 되돌린 DB 도 화면은 그대로 열리고, 그 DB 를 여는 화면마다 경고 한 줄이 선다.

    시뮬레이션 DB 경고는 `app.py` 가 모든 화면에, 설비 DB 경고는 설비 DB 를 여는 화면만 세운다.
    HOME 은 설비 DB 를 열지 않으므로 그 경고가 없다.
    """
    import duckdb

    import capa_simulation.settings as settings
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    newer = 9999
    for repository, schema in (
        (DuckDBScenarioRepository(settings.DUCKDB_PATH), "app_meta"),
        (DuckDBEquipmentRepository(settings.EQUIPMENT_DUCKDB_PATH), "equipment_meta"),
    ):
        repository.initialize()
        with duckdb.connect(str(repository.database_path)) as connection:
            connection.execute(
                f"INSERT INTO {schema}.schema_migration (version, name, checksum) "
                "VALUES (?, 'newer.sql', 'newer')",
                [newer],
            )

    def ahead_warnings(app: AppTest) -> list[str]:
        return [
            str(element.value)
            for element in app.warning
            if "이 코드보다 새 버전입니다" in str(element.value)
        ]

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    home_warnings = ahead_warnings(app)
    assert len(home_warnings) == 1
    assert home_warnings[0].startswith(
        f"시뮬레이션 DB가 이 코드보다 새 버전입니다(DB {newer} · 코드"
    )

    # 설비 DB 를 여는 일곱 화면 모두를 돈다(공정 Capa 상세·제약 시뮬레이션은 설비 시나리오를 읽으며
    # 경고를 세운다).
    # 페이지 소스에서 경고 호출을 찾아 대조해 두어, 호출을 지우거나 새 화면에 더하면 이 목록도 같이
    # 고치게 한다.
    equipment_pages = (
        AVAILABLE_EQUIPMENT_STATUS.path,
        REQUIRED_SHORTENING.path,
        PROCESS_CAPA_DETAIL.path,
        CONSTRAINT_SIMULATION.path,
        SPACE_STATUS.path,
        STANDARD_TARGET_CAPA.path,
        WIP_STATUS.path,
    )
    callers = {
        spec.path
        for spec in ALL_SPECS
        if "render_schema_ahead_warning(" in (PROJECT_ROOT / spec.path).read_text(encoding="utf-8")
    }
    assert callers == set(equipment_pages)
    for path in equipment_pages:
        app.switch_page(path).run()
        assert not list(app.exception), [element.message for element in app.exception]
        names = sorted(warning.split("가 이 코드보다", 1)[0] for warning in ahead_warnings(app))
        assert names == ["설비 DB", "시뮬레이션 DB"], path
