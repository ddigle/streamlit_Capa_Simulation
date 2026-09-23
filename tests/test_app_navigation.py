# Purpose: 사이드바 페이지 인벤토리와 네비게이션 설정을 고정한다.

import ast
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components.scenario_status import SCENARIO_BOX_KEY
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
    SIDEBAR_GROUPS,
    STATIC_CAPA,
    STATIC_CAPA_SUBPAGES,
)
from capa_simulation.sidebar_status import BOTTLENECK_BOX_KEY, remembered_box_key

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


# AppTest 는 확장 패널을 **아이콘 유무로** 두 이름에 나눠 담는다(아이콘이 있으면
# `Status`, 없으면 `Expander` — `element_tree.py` 의 `expandable` 분기). 아이콘은 서식이지
# 종류가 아니므로 둘 다 본다. 지금은 사이드바 상자가 전부 아이콘을 달아 `Status` 뿐이지만,
# 아이콘 없는 상자가 하나라도 생기면 한쪽만 보는 헬퍼는 그 상자를 통째로 잃는다.
_EXPANDER_ELEMENTS = {"Status", "Expander"}


def _expanded(app: AppTest) -> dict[str, bool]:
    """사이드바 **그룹 상자**의 펼침 상태. 상자가 없는 그룹은 여기 나오지 않는다.

    조회 컨트롤 넷(시나리오·조회기간·B/N·Preference)도 같은 확장 패널이 되면서 사이드바의
    확장 패널이 여덟 개로 늘었다. 이 헬퍼가 말하는 것은 「지금 보는 페이지가 든 그룹만
    편다」는 **그룹 규칙 하나**이므로, 그룹 제목을 단 것만 센다. 하위가 없는 그룹의
    제목도 함께 본다 — 그쪽에 펼침 장치가 생기는 것도 이 헬퍼가 잡아야 한다.
    """
    group_titles = {group.main.title for group in SIDEBAR_GROUPS}
    return {
        element.label: element.proto.expanded
        for element in app.sidebar
        if type(element).__name__ in _EXPANDER_ELEMENTS and element.label in group_titles
    }


def _control_boxes(app: AppTest) -> dict[str, bool]:
    """조회 컨트롤 상자의 펼침 상태를 `key` 로 찾아 돌려준다.

    라벨로는 가를 수 없다 — 시나리오 상자의 라벨에는 상태에 따라 바뀌는 배지가 붙는다.
    `key` 와 `on_change="rerun"` 을 함께 준 확장 패널은 위젯이라 id 끝이 그 `key` 다.
    그렇지 않은 그룹 상자는 id 가 비어 있어 여기 나오지 않는다.
    """
    found: dict[str, bool] = {}
    for element in app.sidebar:
        if type(element).__name__ not in _EXPANDER_ELEMENTS:
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

    사이드바 링크는 열일곱 개고 대부분의 화면에서 그중 열 개는 지금 쓰지 않는 그룹의
    하위다. 접히지 않으면 조회기간·Preference 가 스크롤 밖으로 밀린다.

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


def test_groups_without_subpages_are_boxed_but_not_expandable(_app: AppTest) -> None:
    """하위가 없는 그룹도 **상자에는 들어가되 펼침 장치는 갖지 않는다.**

    테두리는 사이드바에서 「한 칸」이라는 뜻이라 없으면 그 둘만 맨몸으로 서서 목록이 두
    층으로 읽힌다. 다만 펼칠 것이 없으므로 화살표까지 달면 눌러도 아무 일도 없는 장치가
    생긴다 — 상자는 주고 확장 패널은 주지 않는다.
    """
    app = _app.run()

    expandable = set(_expanded(app))
    assert expandable == {STATIC_CAPA.title, DYNAMIC_CAPA.title}
    assert CAPA_CHATBOT.title not in expandable
    assert SCENARIO_MANAGEMENT.title not in expandable


# ------------------------------------------------------- 조회 컨트롤 상자 접기
#
# 페이지 그룹과 **같은 양식**으로 접는다. 넷 다 `st.expander` 이고 `key` 로 펼침 상태가
# 세션에 남는다. 확인할 것은 셋이다 — 첫 화면에서 접혀 있는가, 세션 값으로 펼 수 있는가,
# HOME 에만 있는 B/N 상자가 페이지를 왕복해도 제 상태를 기억하는가.


def test_the_control_boxes_open_collapsed_on_the_first_run(_app: AppTest) -> None:
    """시나리오·조회기간·Preference 는 **접힌 채로** 열린다.

    사이드바가 길어지는 것을 막는 것이 이 과제의 목적이라, 기본값이 펼침이면 고치기 전과
    같아진다. 접어도 공식버전 배지와 적용 기간은 요약 줄에 남으므로 잃는 정보가 없다.
    """
    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    boxes = _control_boxes(app)
    assert boxes[SCENARIO_BOX_KEY] is False
    assert boxes[_app_constant("MONTH_BOX_KEY")] is False
    assert boxes[_app_constant("ADMIN_BOX_KEY")] is False
    # B/N 만 기본이 펼침이다. HOME 에서만 쓰는 상자이고 HOME 에만 있다.
    assert boxes[BOTTLENECK_BOX_KEY] is True


def test_an_opened_control_box_stays_open_across_reruns(_app: AppTest) -> None:
    """편 상태는 **세션 동안 남는다.** 매 rerun 마다 다시 펴야 하면 안 고치느니만 못하다."""
    app = _app.run()
    app.session_state[SCENARIO_BOX_KEY] = True
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    assert _control_boxes(app)[SCENARIO_BOX_KEY] is True

    # 페이지를 옮겨도 그대로다. 세 상자는 어느 페이지에서나 `app.py` 가 그린다.
    app.switch_page(CAPA_CHATBOT.path).run()
    assert _control_boxes(app)[SCENARIO_BOX_KEY] is True


def test_the_bottleneck_box_remembers_its_state_across_a_page_round_trip(_app: AppTest) -> None:
    """HOME 에만 있는 상자라 **기억 칸**이 없으면 왕복할 때마다 펼침으로 되돌아간다.

    Streamlit 은 한 회차에 만들어지지 않은 위젯의 값을 버린다. 다른 페이지에 있는 동안
    이 상자는 아예 그려지지 않으므로, 위젯 값만 믿으면 접어 둔 사람이 HOME 에 돌아올
    때마다 다시 접어야 한다.
    """
    app = _app.run()
    app.session_state[BOTTLENECK_BOX_KEY] = False
    app.run()
    assert _control_boxes(app)[BOTTLENECK_BOX_KEY] is False

    app.switch_page(CAPA_CHATBOT.path).run()
    assert BOTTLENECK_BOX_KEY not in _control_boxes(app)
    # 위젯 값은 버려져도 기억 칸은 남는다.
    assert app.session_state[remembered_box_key(BOTTLENECK_BOX_KEY)][0] is False

    app.switch_page(HOME.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _control_boxes(app)[BOTTLENECK_BOX_KEY] is False


def test_group_boxes_follow_the_page_only_when_the_page_changes(_app: AppTest) -> None:
    """그룹 상자는 **페이지가 바뀐 회차에만** 규칙대로 되돌리고, 그 안에서는 사용자 뜻대로 둔다.

    `expanded=` 는 처음 그릴 때만 읽힌다. 링크로 페이지를 옮기는 것은 새로고침이 아니라
    같은 화면 안의 rerun 이라, 프런트엔드는 이미 그려 둔 확장 패널의 여닫힘을 그대로 두고
    바뀐 값을 무시한다(브라우저 실측). 그래서 `key` 로 위젯을 만들고 세션 값을 페이지가
    바뀔 때만 「지금 보는 페이지가 든 그룹」으로 쓴다 — 매 회차 덮어쓰면 방금 누른 클릭을
    지우고, 한 번도 안 쓰면 옮겨도 따라오지 않는다.
    """
    static, dynamic = STATIC_CAPA.title, DYNAMIC_CAPA.title
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
    assert _expanded(app) == {static: False, dynamic: True}

    # 거기서 사용자가 Static 을 펴 두면, 같은 페이지의 rerun 은 그것도 존중한다.
    app.session_state[static_key] = True
    app.run()
    assert _expanded(app) == {static: True, dynamic: True}
