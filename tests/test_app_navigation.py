# Purpose: 사이드바 페이지 인벤토리와 네비게이션 설정을 고정한다.

import ast
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY
from capa_simulation.components.scenario_status import SCENARIO_BOX_KEY
from capa_simulation.navigation import (
    ADMIN_AREA,
    ADMIN_BOX_PAGES,
    ALL_SPECS,
    CAPA_CHATBOT,
    CONDITIONS_SECTION,
    DATA_PENDING_SUFFIX,
    DYNAMIC_CAPA,
    DYNAMIC_CAPA_SUBPAGES,
    EQUIPMENT_GAP_TAB,
    EQUIPMENT_TAB_KEY,
    HOME,
    IMPLEMENTING_SUFFIX,
    SCENARIO_MANAGEMENT,
    SIDEBAR_GROUPS,
    STATIC_CAPA,
    STATIC_CAPA_SUBPAGES,
)
from capa_simulation.scenario_preset_state import (
    MONTH_RANGE_KEY,
)
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.sidebar_status import (
    BOTTLENECK_BOX_KEY,
    CONDITION_CARD_PREFIX,
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
    ("app_pages/reference_integrity.py", "Dynamic Capa", ":material/sync_alt:", False),
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
    for spec in (CAPA_CHATBOT, *DYNAMIC_CAPA_SUBPAGES):
        assert spec.title.endswith((IMPLEMENTING_SUFFIX, DATA_PENDING_SUFFIX)), spec.path
    # `Dynamic Capa` 그룹 머리는 표기를 달지 않는다(2026-09-29 사용자 결정) — 하위 화면이 각자
    # 표기를 달고 있어 머리에도 달면 그룹 전체가 안 된 것처럼 읽힌다. 성숙도는 본문 배지가 말한다.
    assert not DYNAMIC_CAPA.title.endswith((IMPLEMENTING_SUFFIX, DATA_PENDING_SUFFIX))
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

    조회 컨트롤 넷(시나리오·조회기간·B/N·Support)도 같은 확장 패널이 되면서 사이드바의
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
    하위다. 접히지 않으면 조회기간·Support 가 스크롤 밖으로 밀린다.

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


def test_the_scenario_box_opens_the_database_that_settings_points_to_at_run_time(
    _app: AppTest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """사이드바 시나리오 상자는 **부르는 순간의** `settings.DUCKDB_PATH` 를 연다.

    기본 경로를 import 때 잡으면 픽스처가 `settings` 를 갈아끼워도 상자만 저장소의
    `data/capa_simulation.duckdb` 를 만들고 마이그레이션하며 잠근다 — 앱 서버가 떠 있는
    개발 PC 에서 잠금 충돌이 난다. 파일이 없는지로 보지 않는다: 작업 사본에는 그 파일이
    정상적으로 있을 수 있어서다. 상자가 연 경로를 그대로 적어 둔다.
    """
    import capa_simulation.components.scenario_status as scenario_status

    opened: list[str] = []
    original = scenario_status.get_scenario_repository

    def _recording(database_path: str) -> Any:
        opened.append(database_path)
        return original(database_path)

    monkeypatch.setattr(scenario_status, "get_scenario_repository", _recording)

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert opened
    assert set(opened) == {str((tmp_path / "scenario.duckdb").resolve())}


# ------------------------------------------------------- 조회 컨트롤 상자 접기
#
# 페이지 그룹과 **같은 양식**으로 접는다. 넷 다 `st.expander` 이고 `key` 로 펼침 상태가
# 세션에 남는다. 확인할 것은 셋이다 — 첫 화면에서 접혀 있는가, 세션 값으로 펼 수 있는가,
# HOME 에만 있는 B/N 상자가 페이지를 왕복해도 제 상태를 기억하는가.


def test_the_intro_overlay_is_drawn_before_the_bootstrap_on_every_run(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """입장 화면은 무거운 부트스트랩보다 **먼저**, 그리고 **매 회차** 그려진다.

    먼저여야 그동안을 덮고, 매 회차여야 첫 실행 도중의 rerun 에도 덮개가 내려가지 않는다. 툴바
    iframe(Guide·테마·Print 단추와 사이드바 `S.PKG CAPA` 라벨)은 입장 화면 바로 뒤·부트스트랩
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

    def _recording_bootstrap(*args: object, **kwargs: object) -> object:
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
    monkeypatch.setattr(
        scenario_activation, "bootstrap_latest_official_scenario", _recording_bootstrap
    )

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    app.run()

    # 요약은 부트스트랩 뒤·페이지 앞이다 — 로딩에 들어가고, 페이지가 멈춰도 이미 보냈다. 툴바는
    # Guide·Summary·Print 스크립트 셋을 함께 싣는다. ⋮ 메뉴 감춤과 인쇄 규칙을 담은 껍데기 스타일도
    # 부트스트랩 앞이다 — 부트스트랩 오류 화면(`st.stop()`)에서도 메뉴가 보이지 않고, 그 화면을
    # 인쇄해도 사이드바가 빠져야 한다. 서체 스타일(페이지 제목 등의 Archivo)도 그 바로 뒤다 — 오류
    # 화면의 제목도 같은 서체로 선다.
    one_run = ["intro", "shell", "type", "toolbar:3", "bootstrap", "summary"]
    assert order == one_run * 2
    # 고정 문자열을 회차마다 한 번씩 보낸다 — 빠진 회차에는 규칙이 사라진다.
    sent = [el.proto.body for el in app.get("html") if el.proto.body == typography.TYPOGRAPHY_STYLE]
    assert len(sent) == 1


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
    저장소는 내장 시드를 공식 v1 로 올린다. 개발자·인증 정보는 머리 띠에서 빠졌다."""
    from capa_simulation.services.builtin_seed import (
        BUILTIN_SEED_REVISION_NAME,
        BUILTIN_SEED_SCENARIO_NAME,
        BUILTIN_SEED_SOURCE_CODE,
    )
    from capa_simulation.settings import APP_AUTH_CODE

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    style = _header_style(app)
    assert (
        f'content: "{BUILTIN_SEED_SCENARIO_NAME} · r1 {BUILTIN_SEED_REVISION_NAME} · 공식 v1";'
        in style
    )
    assert f'content: "{BUILTIN_SEED_SOURCE_CODE} · 적용 26.01–26.12 · 내장 시드 ' in style
    assert APP_AUTH_CODE not in style


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

    def counted_connect(*args: object, **kwargs: object) -> Any:
        if inside:
            calls.append("connect")
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(sql_helpers, "connect", counted_connect)
    original_header = app_header.render_app_header
    rendered: list[int] = []

    def watched_header() -> None:
        inside.append(1)
        try:
            original_header()
        finally:
            inside.pop()
        rendered.append(1)

    monkeypatch.setattr(app_header, "render_app_header", watched_header)

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    app.run()

    assert len(rendered) == 2
    assert calls == []


def test_the_bootstrap_error_screen_still_shows_the_app_name_in_the_header(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """부트스트랩이 실패해 `st.stop()` 으로 끝나는 화면에도 머리 띠가 선다. 올라온 시나리오가
    없으므로 앱 이름 한 줄이다(아래 줄은 비어 위 줄이 띠 가운데에 선다)."""
    import capa_simulation.scenario_activation as scenario_activation
    from capa_simulation.settings import APP_NAME

    def _failing_bootstrap(*args: object, **kwargs: object) -> bool:
        raise RuntimeError("부트스트랩 실패")

    monkeypatch.setattr(
        scenario_activation, "bootstrap_latest_official_scenario", _failing_bootstrap
    )

    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert len(app.error) == 1

    style = _header_style(app)
    assert f'content: "{APP_NAME}";' in style
    assert 'content: "";' in style


def test_the_header_marks_unsaved_edits(_app: AppTest) -> None:
    """미저장 판정은 사이드바 시나리오 상자의 「미저장 변경」과 같은
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


def test_the_control_boxes_open_collapsed_on_the_first_run(_app: AppTest) -> None:
    """시나리오·조회기간·Support 는 **접힌 채로** 열린다.

    사이드바가 길어지는 것을 막는 것이 이 과제의 목적이라, 기본값이 펼침이면 고치기 전과
    같아진다. 접어도 공식버전 배지와 적용 기간은 요약 줄에 남으므로 잃는 정보가 없다.
    """
    app = _app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    boxes = _control_boxes(app)
    assert boxes[SCENARIO_BOX_KEY] is False
    assert boxes[_app_constant("MONTH_BOX_KEY")] is False
    assert boxes[_app_constant("ADMIN_BOX_KEY")] is False
    # B/N 도 접힌다. 기준은 한 번 정해 두고 보는 값이라 들어오자마자 펴 둘 이유가 없다 —
    # 넷이 다 접혀야 사이드바 첫 화면이 「어디로 갈까」만 말한다.
    assert boxes[BOTTLENECK_BOX_KEY] is False


def test_an_opened_control_box_stays_open_across_reruns(_app: AppTest) -> None:
    """편 상태는 **세션 동안 남는다.** 매 rerun 마다 다시 펴야 하면 안 고치느니만 못하다."""
    app = _app.run()
    app.session_state[SCENARIO_BOX_KEY] = True
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    assert _control_boxes(app)[SCENARIO_BOX_KEY] is True

    # 페이지를 옮겨도 그대로다. 공통 상자는 그 조건을 읽는 페이지에서 `app.py` 가 그린다.
    app.switch_page(SCENARIO_MANAGEMENT.path).run()
    assert _control_boxes(app)[SCENARIO_BOX_KEY] is True


def test_the_shared_sample_switch_stays_on_across_sample_pages(_app: AppTest) -> None:
    """「샘플 데이터」 스위치는 샘플 화면 전체가 나눠 쓴다. 두 번째 화면에서도 켜진 채다."""
    app = _app
    for path in ("app_pages/actual_efficiency.py", "app_pages/actual_upeh.py"):
        app.switch_page(path).run()
        assert not list(app.exception), [element.message for element in app.exception]
        switch = next(element for element in app.toggle if element.key == SAMPLE_TOGGLE_KEY)
        assert (switch.proto.value, switch.proto.set_value) == (True, True), path


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

    app.switch_page(SCENARIO_MANAGEMENT.path).run()
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
def test_the_conditions_heading_stands_right_before_the_scenario_box(
    _app: AppTest, page_path: str
) -> None:
    """「조회 조건」 제목은 시나리오 상자 **바로 앞**이다.

    제목은 그 아래 세 상자(시나리오·리비전, 조회기간, B/N 집계 공정)가 다른 화면으로 가는
    목록이 아니라 지금 화면의 계산 조건이라고 말한다. 뒤로 밀리면 시나리오 상자가 목록
    쪽에 붙어 읽히고, 조회기간 앞으로 가면 적용 기간 자리표시자가 제 상자에서 떨어진다.
    """
    app = _app.run()
    if page_path != HOME.path:
        app.switch_page(page_path).run()
    assert not list(app.exception), [element.message for element in app.exception]

    keys = _sidebar_keys(app)
    heading = keys.index(CONDITIONS_SECTION.key)
    assert keys[heading + 1] == SCENARIO_BOX_KEY, keys
    # 선언한 두 글자가 실제로 들어 있다. 빈 컨테이너는 화면에 그려지지도 않는다.
    heading_block = list(app.sidebar.children.values())[heading]
    captions = [element.value for element in heading_block if type(element).__name__ == "Caption"]
    assert captions == [CONDITIONS_SECTION.title, CONDITIONS_SECTION.hint]


@pytest.mark.parametrize("page_path", [HOME.path, SCENARIO_MANAGEMENT.path])
def test_the_applied_range_placeholder_stands_right_before_the_month_box(
    _app: AppTest, page_path: str
) -> None:
    """적용 기간 자리표시자는 조회기간 상자 **바로 앞** 형제다.

    CSS 가 그 칸의 높이를 0 으로 눌러 바로 아래 요약 줄 위에 글자를 얹는다. 사이에 다른
    칸이 끼면 글자가 그 칸 위에 앉는다. 상자 **뒤**로 옮기면 페이지가 `st.stop()` 한 회차에
    자리표시자가 아예 그려지지 않는다(`app.py` 가 이유를 적었다).
    """
    app = _app.run()
    if page_path != HOME.path:
        app.switch_page(page_path).run()
    assert not list(app.exception), [element.message for element in app.exception]

    keys = _sidebar_keys(app)
    placeholder = keys.index(_app_constant("MONTH_APPLIED_BOX_KEY"))
    assert keys[placeholder + 1] == _app_constant("MONTH_BOX_KEY"), keys


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


def _range_caption(app: AppTest) -> str:
    """조회기간 요약 줄 위에 얹히는 한 줄(적용 기간 자리표시자)의 글자."""
    placeholder_key = _app_constant("MONTH_APPLIED_BOX_KEY")
    (block,) = [
        node
        for node in app.sidebar.children.values()
        if str(getattr(getattr(node, "proto", None), "id", "") or "").endswith(placeholder_key)
    ]
    (caption,) = [element.value for element in block if type(element).__name__ == "Caption"]
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
    for page_path in (HOME.path, STATIC_CAPA.path):
        if page_path != HOME.path:
            app.switch_page(page_path).run()
        assert not list(app.exception), [element.message for element in app.exception]
        errors = [str(element.value) for element in app.error]
        assert any("밖의 달에 기준정보 오류가 있어 계산을 멈췄습니다" in e for e in errors), (
            page_path,
            errors,
        )
        assert _range_caption(app) == ":material/block: 계산 멈춤", page_path


# ------------------------------------------------ 화면이 읽는 공통 조건만 세운다
#
# 사이드바 「조회 조건」은 지금 화면이 **실제로 읽는** 조건만 모은다(2026-09-29 사용자 결정).
# 무엇을 읽는지는 `navigation.PageSpec` 의 선언이 말하고 `app.py` 가 그대로 따른다.


def _common_boxes(app: AppTest) -> set[str]:
    keys = set(_sidebar_keys(app))
    return {
        name
        for name, key in (
            ("heading", CONDITIONS_SECTION.key),
            ("scenario", SCENARIO_BOX_KEY),
            ("period", _app_constant("MONTH_BOX_KEY")),
        )
        if key in keys
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
    """「조회 조건」 제목 아래에 설 상자 가운데 사이드바 최상위에 있는 것의 key.

    사이드바 CSS(`sidebar_style.lone_conditions_heading_selector`)는 이것이 하나도 없을 때만 제목을
    감춘다. AppTest 는 CSS 를 계산하지 않으므로 그 조건이 되는 칸을 직접 본다.
    """
    return {
        key
        for key in _sidebar_keys(app)
        if key in {SCENARIO_BOX_KEY, _app_constant("MONTH_BOX_KEY"), BOTTLENECK_BOX_KEY}
        or key.startswith(CONDITION_CARD_PREFIX)
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
    """가용설비 현황은 `Static/Dynamic` 탭만 활성 시나리오·조회기간을 읽는다."""
    equipment = DYNAMIC_CAPA_SUBPAGES[0]
    assert equipment.condition_tabs is not None
    app = _app.run()
    app.switch_page(equipment.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    # Main 은 공통 조건을 읽지 않지만 자기 조건 카드(`설비 조회 조건`)가 있어 제목은 선다.
    assert _common_boxes(app) == {"heading"}

    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_GAP_TAB
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _common_boxes(app) == {"heading", "scenario", "period"}

    # RawData 는 카드도 공통 조건도 없다 — 제목만 남는 빈 구역을 세우지 않는다.
    app.session_state[EQUIPMENT_TAB_KEY] = ":material/table_rows: RawData"
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _common_boxes(app) == set()


def test_every_declared_condition_tab_is_a_real_label() -> None:
    """선언한 탭 라벨이 페이지의 실제 탭과 어긋나면 그 탭에서도 상자가 영영 서지 않는다."""
    source = (PROJECT_ROOT / DYNAMIC_CAPA_SUBPAGES[0].path).read_text(encoding="utf-8")
    assert "EQUIPMENT_GAP_TAB," in source and "key=EQUIPMENT_TAB_KEY" in source


# ----------------------------------------------------------------- 설비 DB 핀
#
# 설비 DB 핀은 rerun 한 번만 사는 **화면 한정** 핀이다. 전역으로 걸면 설비 DB 를 안 보는
# 화면마다 인스턴스 생성 비용이 붙고, 선언과 어긋나면 이득이 조용히 사라진다.


def test_only_the_equipment_status_screen_declares_the_equipment_db_pin() -> None:
    declared = {spec.path for spec in ALL_SPECS if spec.uses_equipment_db}
    assert declared == {DYNAMIC_CAPA_SUBPAGES[0].path}


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
    app.switch_page(DYNAMIC_CAPA_SUBPAGES[0].path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert pinned == [(settings.DUCKDB_PATH,), (equipment_db,)]

    # 설비 DB 를 한 번만 여는 화면(Space 현황)과 HOME 으로 가면 다시 걸지 않는다.
    for path in (DYNAMIC_CAPA_SUBPAGES[1].path, HOME.path):
        pinned.clear()
        app.switch_page(path).run()
        assert not list(app.exception), [element.message for element in app.exception]
        assert pinned == [(settings.DUCKDB_PATH,)], path


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
        f"시뮬레이션 DB 가 이 코드보다 새 버전입니다(DB {newer} · 코드"
    )

    # 설비 DB 를 여는 네 화면 모두를 돈다. 페이지 소스에서 경고 호출을 찾아 대조해 두어,
    # 호출을 지우거나 새 화면에 더하면 이 목록도 같이 고치게 한다.
    equipment_pages = (
        DYNAMIC_CAPA_SUBPAGES[0].path,
        DYNAMIC_CAPA_SUBPAGES[1].path,
        STATIC_CAPA_SUBPAGES[3].path,
        DYNAMIC_CAPA_SUBPAGES[-1].path,
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
        names = sorted(warning.split(" 가 ", 1)[0] for warning in ahead_warnings(app))
        assert names == ["설비 DB", "시뮬레이션 DB"], path
