# Purpose: HOME 대시보드가 내장 시드 시나리오에서 렌더링되는 현재 동작을 고정한다.

import json
from functools import partial
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from alert_marks import alert_notes, data_error_texts, place_errors
from streamlit.testing.v1 import AppTest

from capa_simulation.components.home_dimensions import (
    DASHBOARD_PANEL_TITLE_GAP_PX,
    DASHBOARD_TITLE_BAND_PX,
    DASHBOARD_TITLE_LINE_PX,
    LOB_BOTTOM_MARGIN_PX,
    LOB_TOP_MARGIN_PX,
    LOB_VALUE_FONT_SIZE_PX,
    delta_ink_yshift_px,
    lower_delta_row_height,
    table_row_height,
)
from capa_simulation.components.home_plan_detail_figures import (
    DETAIL_HEADER_FONT_SIZE_PX,
    DETAIL_VALUE_FONT_SIZE_PX,
)
from capa_simulation.components.home_preference import (
    KEY_PROCESS_FIELD_KEY,
    KEY_PROCESS_LOCKED_HELP,
    PRESET_DEFAULT_HELP,
    PRESET_DEFAULT_LOCKED_HELP,
    PRESET_DELETE_LOCKED_HELP,
)
from capa_simulation.components.home_rendering import (
    BOTTLENECK_MONTHS_CHART_KEY,
    HOME_CELL_CHART_KEYS,
    KEY_PROCESS_MONTHS_CHART_KEY,
    LOB_MONTHS_CHART_KEY,
    open_clicked_home_cell,
)
from capa_simulation.components.literal_markdown import literal_markdown, quoted
from capa_simulation.components.plotly_layout import table_text_y
from capa_simulation.design import tokens
from capa_simulation.home_state import (
    COMPARISON_TOGGLE_KEY,
    EDP_TOGGLE_KEY,
    HOME_KEY_PROCESS_DIALOG,
    PRODUCT_SHARE_BASIS_KEY,
)
from capa_simulation.navigation import REFERENCE_DATA
from capa_simulation.process_detail_state import (
    HOME_BOTTLENECK_SECTION,
    HOME_KEY_PROCESS_SECTION,
    HOME_LOB_SECTION,
)
from capa_simulation.scenario_preset_state import PROCESS_SELECTION_KEY
from capa_simulation.services.simulation_cache import shared_home_figure_store

# cwd 가 아니라 이 파일 위치를 기준으로 잡는다. tests/ 안에서 pytest 를 돌려도 같은 페이지를 연다.
HOME_PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "home.py"

# 이 파일은 특성화(characterization) 테스트다. 아래 값들은 "이래야 한다"는 규범이 아니라
# 리팩토링 전 HOME의 관측된 현재 동작이다. 의도적으로 화면을 바꿀 때는 이 기대값도 함께
# 바꾸고, 의도하지 않았다면 리팩토링이 무언가를 깨뜨린 것이다.


def _home_script(database_path: Path, *, retain_process_dialog: bool = False) -> str:
    """app.py의 전역 준비 단계만 재현한 뒤 HOME 페이지를 실행한다.

    AppTest에는 plotly_chart 접근자가 없어 st.plotly_chart를 감싸 호출별 trace 수와
    config·칸 선택(`on_select`·`selection_mode`)을 session_state에 기록한다. Components v2
    위젯은 모듈 import 시점에 한 번 등록되므로 AppTest 인스턴스를 새로 만들면 레지스트리에 남아
    있지 않다. 가로 스크롤바는
    특성화 대상이 아니므로 호출 횟수만 세는 스텁으로 대체한다.

    AppTest는 매 실행마다 fragment 저장소를 새로 만들어 dialog 내부 클릭도 전체 실행으로
    취급한다. 공정 선택 검증에서만 실제 HOME 함수와 인자를 보관해 dialog를 재호출한다.
    적용으로 초안이 제거되면 HOME 전체 실행으로 돌아간다. 실제 fragment 격리는 브라우저
    검증 몫이고, 여기서는 원본 콜백·초안·적용 동작을 대체하지 않는다.
    """
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
apply_pending_scenario_preset()

st.session_state["spy_traces"] = []
st.session_state["spy_configs"] = {{}}
st.session_state["spy_selections"] = {{}}
st.session_state["spy_figures"] = {{}}
st.session_state["spy_scrollbars"] = 0
_original_plotly_chart = st.plotly_chart
_original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar


def _spy_plotly_chart(figure, *args, **kwargs):
    st.session_state["spy_traces"] = st.session_state["spy_traces"] + [
        len(getattr(figure, "data", []) or [])
    ]
    st.session_state["spy_configs"] = {{
        **st.session_state["spy_configs"],
        kwargs.get("key"): dict(kwargs.get("config") or {{}}),
    }}
    st.session_state["spy_selections"] = {{
        **st.session_state["spy_selections"],
        kwargs.get("key"): (
            kwargs.get("on_select", "ignore"),
            kwargs.get("selection_mode", ("points", "box", "lasso")),
        ),
    }}
    st.session_state["spy_figures"] = {{
        **st.session_state["spy_figures"],
        kwargs.get("key"): figure,
    }}
    return _original_plotly_chart(figure, *args, **kwargs)


def _spy_scrollbar(*_args, **_kwargs):
    st.session_state["spy_scrollbars"] = st.session_state["spy_scrollbars"] + 1
    return None


st.plotly_chart = _spy_plotly_chart
horizontal_scrollbar.render_horizontal_scrollbar = _spy_scrollbar
try:
    if (
        {retain_process_dialog!r}
        and "test_process_dialog_function" in st.session_state
        and "dashboard_bottleneck_process_dialog_draft" in st.session_state
    ):
        st.session_state["test_process_dialog_function"](
            *st.session_state["test_process_dialog_arguments"]
        )
    else:
        page_source = Path({str(HOME_PAGE)!r}).read_text(encoding="utf-8")
        namespace = {{"__name__": "__main__"}}
        exec(compile(page_source, {str(HOME_PAGE)!r}, "exec"), namespace)
        if {retain_process_dialog!r}:
            st.session_state["test_process_dialog_function"] = namespace[
                "show_process_filter_dialog"
            ]
            st.session_state["test_process_dialog_arguments"] = (
                namespace["process_options"],
                namespace["build_process_picker_summary"](
                    namespace["securement_rate"], namespace["process_options"],
                    start_month=namespace["effective_start"],
                    end_month=namespace["effective_end"],
                    thresholds=namespace["thresholds"],
                ),
                namespace["securement_threshold_caption"](
                    namespace["thresholds"],
                    start_month=namespace["effective_start"],
                    end_month=namespace["effective_end"],
                ),
                namespace["effective_start"], namespace["effective_end"],
            )
finally:
    st.plotly_chart = _original_plotly_chart
    horizontal_scrollbar.render_horizontal_scrollbar = _original_scrollbar
"""


@pytest.fixture(scope="module")
def seeded_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """내장 시드 부트스트랩은 멱등이므로 모듈 안에서 DuckDB 하나를 재사용한다."""
    return tmp_path_factory.mktemp("home") / "scenario.duckdb"


def _run(seeded_database: Path) -> AppTest:
    app = AppTest.from_string(_home_script(seeded_database), default_timeout=300).run()
    assert not list(app.exception)
    return app


def _run_process_dialog_app(database_path: Path) -> AppTest:
    app = AppTest.from_string(
        _home_script(database_path, retain_process_dialog=True), default_timeout=300
    ).run()
    assert not list(app.exception)
    return app


# 사이드바 「HOME 설정」 상자의 단추·팝업 열림 칸(2026-11-02 — 전에는 HOME 의 Preference·Past Data
# 탭).
SETTINGS_BUTTON_KEY = "home_settings_open"
HOME_DIALOG_KEY = "home_open_dialog"
# 사이드바 최상위 칸 key — 「HOME 설정」 상자는 `LOB 표시 조건` 카드 바로 위다(펼친 카드 밑이면
# 작은 화면의 사이드바 첫 화면 밖으로 밀린다).
SETTINGS_BOX = "sidebar_dialog_box_home_settings"
VIEW_CARD = "condition_card_home"


def _open_settings(app: AppTest) -> AppTest:
    """사이드바 「HOME 설정」 상자를 눌러 팝업을 연다 — Preference·Past Data 편집기가 그 안이다."""
    app.button(key=SETTINGS_BUTTON_KEY).click().run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state[HOME_DIALOG_KEY] == "settings"
    return app


def _close_settings(app: AppTest) -> AppTest:
    """팝업을 닫는다(X·바깥·Esc 의 `on_dismiss` — AppTest 는 닫기를 못 눌러 열림 칸을 비운다)."""
    del app.session_state[HOME_DIALOG_KEY]
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    return app


def _dismiss_home_dialog(app: AppTest) -> None:
    """공정 필터 · 주요공정 히트맵 팝업의 닫기(`HOME_DIALOG_HOST.close` — 호스트만 도는 회차)를
    흉내 낸다. AppTest 는 닫기를 못 누르므로 그 콜백이 하는 일 가운데 열림 칸만 지운다(입력 위젯
    값은 다시 여는 콜백이 다시 적는다) — 닫는 회차에 HOME 은 돌지 않는다."""
    del app.session_state[HOME_DIALOG_KEY]


def test_process_picker_buttons_show_aliases_but_only_apply_original_keys(tmp_path: Path) -> None:
    from capa_simulation.persistence.cache import clear_global_process_rename_cache
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    database = tmp_path / "process_picker.duckdb"
    app = _run_process_dialog_app(database)
    original_selection = list(app.session_state[PROCESS_SELECTION_KEY])
    process = original_selection[0]
    alias = "화면에서만 쓰는 긴 공정 표시명"
    repository = DuckDBScenarioRepository(database)
    repository.replace_global_process_rename(
        pd.DataFrame({"공정": [process], "표시명": [alias]}), source="공정 선택 UI 검증"
    )
    clear_global_process_rename_cache()
    app.run()
    # 사이드바 공정 필터 줄 — 이름 줄 오른쪽 보조 글이 뜻(판정 대상)을 지킨다. 표의 행을 거르는
    # 다른 화면의 「공정 필터」와 이름이 같다.
    assert {"공정 필터", "B/N 판정 대상"} <= {item.value for item in app.sidebar.caption}
    app.button(key="dashboard_bottleneck_process_dialog_open").click().run()
    assert not app.exception
    # 팝업 머리에는 설명 글이 없다(2026-11-04 검수 의견 home-20) — 고른 수 줄 하나이고, 무엇을
    # 고르는지와 기간 · 확보 기준은 그 줄의 풍선이다. 판정 기준을 정하는 자리는 Guide 가 말한다.
    captions = [item.value for item in app.caption]
    assert not any(text.startswith("B/N·확보율 판정에 넣을 공정") for text in captions), captions
    assert not any("에서 정합니다" in text for text in captions), captions
    head = next(item for item in app.markdown if str(item.value).startswith("**선택 "))
    assert "체크된 버튼" not in head.value
    assert str(head.proto.help).startswith("B/N·확보율 판정에 넣을 공정 · ")
    assert "확보 기준 " in head.proto.help
    # 여는 첫 렌더만 페이지의 호출부 인자로 그려진다(이후는 하네스가 다시 부른다). 거기서
    # 옵션이 표시명으로 바뀌면 적용된 공정이 OFF 로 보이므로, 적용값이 모두 ON 인지 본다.
    assert {
        str(button.key).removeprefix("home_bn_process_tile_")
        for button in app.button
        if str(button.key).startswith("home_bn_process_tile_") and button.proto.type == "primary"
    } == set(original_selection)
    assert app.button(key=f"home_bn_process_tile_{process}").label == alias
    # 설명 풍선은 `help` 가 아니라 CSS `:hover` 다 — 누른 뒤 다시 그려지는 동안 마우스가 떠나면
    # `help` 풍선이 열린 채 남았다(2026-09-29 사용자 신고). 원본 공정명은 그 풍선에 있다.
    assert not app.button(key=f"home_bn_process_tile_{process}").help
    assert any(f"원본 공정: {process}" in element.proto.body for element in app.get("html"))

    app.button(key=f"home_bn_process_tile_{process}").click().run()
    assert not app.exception
    draft = app.session_state["dashboard_bottleneck_process_dialog_draft"]
    assert process not in draft
    assert alias not in draft
    assert app.session_state[PROCESS_SELECTION_KEY] == original_selection

    app.button(key=f"home_bn_process_tile_{process}").click().run()
    assert not app.exception
    assert set(app.session_state["dashboard_bottleneck_process_dialog_draft"]) == set(
        original_selection
    )
    app.button(key=f"home_bn_process_tile_{process}").click().run()
    app.button(key="dashboard_bottleneck_process_restore").click().run()
    assert not app.exception
    assert app.session_state["dashboard_bottleneck_process_dialog_draft"] == original_selection
    assert app.session_state[PROCESS_SELECTION_KEY] == original_selection

    app.button(key=f"home_bn_process_tile_{process}").click().run()
    app.button(key="dashboard_bottleneck_process_apply").click().run()
    assert not app.exception, [item.message for item in app.exception]
    expected = [item for item in original_selection if item != process]
    assert app.session_state[PROCESS_SELECTION_KEY] == expected
    assert "dashboard_bottleneck_process_dialog_draft" not in app.session_state
    assert app.button(key="dashboard_bottleneck_process_dialog_open").label == (
        f"{len(expected)} / {len(original_selection)} 공정"
    )
    assert alias not in app.session_state[PROCESS_SELECTION_KEY]
    assert len(app.session_state["spy_traces"]) == 8


def test_process_picker_bulk_actions_restore_applied_values_and_apply_empty_or_all(
    tmp_path: Path,
) -> None:
    app = _run_process_dialog_app(tmp_path / "bulk_picker.duckdb")
    options = list(app.session_state[PROCESS_SELECTION_KEY])
    applied = options[:1]
    app.session_state[PROCESS_SELECTION_KEY] = applied
    app.run()
    app.button(key="dashboard_bottleneck_process_dialog_open").click().run()

    app.button(key="dashboard_bottleneck_process_all_on").click().run()
    assert not app.exception
    assert app.session_state["dashboard_bottleneck_process_dialog_draft"] == options
    assert app.session_state[PROCESS_SELECTION_KEY] == applied
    app.button(key="dashboard_bottleneck_process_restore").click().run()
    assert app.session_state["dashboard_bottleneck_process_dialog_draft"] == applied

    app.button(key="dashboard_bottleneck_process_all_off").click().run()
    assert not app.exception
    assert app.session_state["dashboard_bottleneck_process_dialog_draft"] == []
    assert app.session_state[PROCESS_SELECTION_KEY] == applied
    app.button(key="dashboard_bottleneck_process_apply").click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state[PROCESS_SELECTION_KEY] == []
    assert (
        app.button(key="dashboard_bottleneck_process_dialog_open").label
        == f"0 / {len(options)} 공정"
    )

    app.button(key="dashboard_bottleneck_process_dialog_open").click().run()
    app.button(key="dashboard_bottleneck_process_all_on").click().run()
    app.button(key="dashboard_bottleneck_process_restore").click().run()
    assert app.session_state["dashboard_bottleneck_process_dialog_draft"] == []
    app.button(key="dashboard_bottleneck_process_all_on").click().run()
    app.button(key="dashboard_bottleneck_process_apply").click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state[PROCESS_SELECTION_KEY] == options
    assert app.button(key="dashboard_bottleneck_process_dialog_open").label == (
        f"전체 {len(options)}공정"
    )


def test_opening_and_closing_the_process_filter_dialog_does_not_rerun_home() -> None:
    """공정 필터 팝업은 열어도 닫아도 HOME 을 다시 돌리지 않는다 — HOME 팝업 호스트가
    연다(2026-11-08 사용자 답 U5 — 설계 규칙 UI-PRF-01, 전에는 칸을 누른 회차가 앱 전체였고 진행
    막대도 떴다).

    칸의 콜백(`open_process_filter`)은 초안을 적고 `HOME_DIALOG_HOST.open` 으로 호스트만 다시
    돌리고,
    닫기(X·바깥·Esc)는 `HOME_DIALOG_HOST.close` 라 닫는 회차도 호스트만 돈다(`close_to_app` 이
    아니다 — 닫을 때 HOME 이 한 번 더 돌지 않는다, 2026-11-08 재연결 답 e2). 「선택 공정 적용」은
    열림 칸을 지우고 앱 전체를 다시 돌린다(`HOME_DIALOG_HOST.finish`). 주요공정 히트맵 팝업도 같다.
    AppTest 는 프래그먼트만 도는 회차와 닫기를 흉내 내지 못해 선언을 읽는다.
    """
    import ast

    tree = ast.parse(HOME_PAGE.read_text(encoding="utf-8"))
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    dialog = functions["show_process_filter_dialog"]
    decorator = dialog.decorator_list[0]
    assert isinstance(decorator, ast.Call)
    assert ast.unparse(decorator.func) == "st.dialog"
    dismiss = {keyword.arg: ast.unparse(keyword.value) for keyword in decorator.keywords}
    assert dismiss["on_dismiss"] == "HOME_DIALOG_HOST.close"
    assert "HOME_DIALOG_HOST.finish()" in ast.unparse(dialog)
    assert "HOME_DIALOG_HOST.open(HOME_PROCESS_FILTER_DIALOG, PROCESS_FIELD_KEY)" in ast.unparse(
        functions["open_process_filter"]
    )


def test_a_closed_process_filter_draft_neither_leaks_nor_survives_reopening(
    seeded_database: Path,
) -> None:
    """닫은 팝업의 초안은 대시보드에 새지 않고, 다시 열면 지금 적용된 선택으로 돌아간다(같은 숫자).

    닫기가 HOME 을 다시 돌리지 않으므로 고르다 만 초안이 세션에 남는다. 그 초안은 팝업 안에서만
    읽힌다 — 뒤따르는 HOME 회차의 판정 대상·칸 글자·Figure 는 열기 전과 같고, 다시 열면 초안을 지금
    선택으로 덮는다. 「선택 공정 적용」만 판정 대상을 바꾼다(무효화).
    """
    app = _run(seeded_database)
    selection = list(app.session_state[PROCESS_SELECTION_KEY])
    field_label = app.button(key="dashboard_bottleneck_process_dialog_open").label
    figures = {key: figure.to_json() for key, figure in app.session_state["spy_figures"].items()}

    app.button(key="dashboard_bottleneck_process_dialog_open").click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state["dashboard_bottleneck_process_dialog_draft"] == selection
    # 타일 몇 개를 끄고 적용하지 않은 채 닫는다(닫기는 호스트만 돈다 — 초안은 세션에 남는다).
    app.session_state["dashboard_bottleneck_process_dialog_draft"] = selection[1:]
    _dismiss_home_dialog(app)
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert "dashboard_bottleneck_process_apply" not in {button.key for button in app.button}
    assert app.session_state[PROCESS_SELECTION_KEY] == selection
    assert app.button(key="dashboard_bottleneck_process_dialog_open").label == field_label
    assert {
        key: figure.to_json() for key, figure in app.session_state["spy_figures"].items()
    } == figures

    app.button(key="dashboard_bottleneck_process_dialog_open").click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state["dashboard_bottleneck_process_dialog_draft"] == selection


@pytest.mark.parametrize(
    "group_rate,other_rate,rest_rate,group_title,group_first",
    [
        (0.8, 1.3, float("nan"), "확보 기준 미달", True),
        (1.3, 0.8, float("nan"), "확보 기준 충족", False),
        (float("nan"), 0.8, 1.3, "확보율 없음", False),
    ],
)
def test_process_picker_preserves_shared_order_within_each_securement_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    group_rate: float,
    other_rate: float,
    rest_rate: float,
    group_title: str,
    group_first: bool,
) -> None:
    """공용 표시순서는 확보율 구역 **안에서** 지켜진다.

    내장 시드의 공정 수에 묶이지 않게, 정렬 규칙과 구역은 앞 세 공정으로만 만들고 나머지
    공정에는 두 구역 어디에도 들지 않는 셋째 구역의 확보율(`rest_rate`)을 준다. 단언도 그 세
    공정의 타일·선택만 본다 — 시드가 공정을 늘려도 계약은 그대로다.
    """
    from capa_simulation.persistence.cache import (
        clear_global_display_order_cache,
        clear_global_process_rename_cache,
    )
    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.services import simulation_cache
    from capa_simulation.services.display_order_scopes import PAGE_CALCULATION, TAB_SECUREMENT

    database = tmp_path / "ordered_picker.duckdb"
    app = _run_process_dialog_app(database)
    initial_selection = list(app.session_state[PROCESS_SELECTION_KEY])
    assert len(initial_selection) >= 3
    originals = sorted(initial_selection)[:3]
    configured_order = list(reversed(originals))
    group_members = [configured_order[0], configured_order[2]]
    other = configured_order[1]
    repository = DuckDBScenarioRepository(database)
    repository.replace_global_display_order(
        pd.DataFrame(
            {
                "페이지 구분": [PAGE_CALCULATION] * 3,
                "탭 구분": [TAB_SECUREMENT] * 3,
                "정렬우선순위": [1] * 3,
                "분류컬럼": ["공정"] * 3,
                "정렬방식": ["사용자지정"] * 3,
                "분류값": configured_order,
                "값표시순서": [1, 2, 3],
                "활성여부": ["Y"] * 3,
            }
        ),
        source="공정 선택 구역별 표시순서 검증",
    )
    aliases = {process: f"화면 표시 {index}" for index, process in enumerate(originals)}
    repository.replace_global_process_rename(
        pd.DataFrame({"공정": originals, "표시명": [aliases[item] for item in originals]}),
        source="공정 선택 원본 키 검증",
    )
    clear_global_display_order_cache()
    clear_global_process_rename_cache()
    original_simulation = simulation_cache.get_home_simulation

    def simulation_with_group_rates(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
        result: list[Any] = list(original_simulation(*args, **kwargs))
        securement = result[3].copy()
        # 계산식은 실제 경로를 쓰고, 선택 UI의 세 구역을 만들 최종 확보율만 고정한다. 고른
        # 세 공정 밖의 공정은 모두 셋째 구역이다 — 두 구역의 개수와 차례에 끼지 않는다.
        rates = {process: group_rate for process in group_members}
        rates[other] = other_rate
        securement["확보율"] = securement["공정"].map(lambda process: rates.get(process, rest_rate))
        result[3] = securement
        return tuple(result)

    monkeypatch.setattr(simulation_cache, "get_home_simulation", simulation_with_group_rates)
    # 공용 프로필은 활성화 때 세션 기준정보로 읽힌다. 저장한 순서를 새 세션에서 불러온다.
    app = _run_process_dialog_app(database)
    app.button(key="dashboard_bottleneck_process_dialog_open").click().run()
    assert not app.exception, [item.message for item in app.exception]
    expected_order = [*group_members, other] if group_first else [other, *group_members]
    tile_prefix = "home_bn_process_tile_"
    tiles = [
        button
        for button in app.button
        if str(button.key).startswith(tile_prefix)
        and str(button.key).removeprefix(tile_prefix) in originals
    ]
    assert [button.key for button in tiles] == [
        f"{tile_prefix}{process}" for process in expected_order
    ]
    assert [button.label for button in tiles] == [aliases[process] for process in expected_order]
    assert f"**{group_title} · 2**" in [item.value for item in app.markdown]

    app.button(key="dashboard_bottleneck_process_apply").click().run()
    assert not app.exception, [item.message for item in app.exception]
    applied = app.session_state[PROCESS_SELECTION_KEY]
    assert [process for process in applied if process in originals] == configured_order
    assert sorted(applied) == sorted(initial_selection)
    assert not set(aliases.values()).intersection(applied)


def test_a_broken_securement_display_order_shows_an_error_instead_of_a_traceback(
    tmp_path: Path,
) -> None:
    """공정 옵션 정렬이 HOME 의 `BOOTSTRAP_ERRORS` 경계 안에 있어야 한다.

    이제 저장 검증이 적용과 같은 키(`match_key`)로 보아 대소문자만 다른 두 값을 막는다. 그래도
    그 검사 **전에** 저장된 프로필은 남아 있을 수 있다 — 저장 경로를 건너 프로필에 바로 넣어 그
    상태를 만든다. 기동은 막히지 않고, 정렬이 경계 밖이면 그 규칙 하나로 HOME 전체가 traceback
    을 남기고 멈춘다.
    """
    from capa_simulation.persistence import display_order_store
    from capa_simulation.persistence._sql_helpers import connect, reset_profile, transaction
    from capa_simulation.persistence.cache import (
        clear_global_display_order_cache,
        clear_scenario_repository,
    )
    from capa_simulation.services.display_order_scopes import PAGE_CALCULATION, TAB_SECUREMENT

    database = tmp_path / "broken_order.duckdb"
    app = _run_process_dialog_app(database)
    process = sorted(app.session_state[PROCESS_SELECTION_KEY])[0]
    assert process.upper() != process.lower()
    stored = pd.DataFrame(
        {
            "페이지 구분": [PAGE_CALCULATION] * 2,
            "탭 구분": [TAB_SECUREMENT] * 2,
            "정렬우선순위": [1] * 2,
            "분류컬럼": ["공정"] * 2,
            "정렬방식": ["사용자지정"] * 2,
            "분류값": [process.upper(), process.lower()],
            "값표시순서": [1, 2],
            "활성여부": ["Y"] * 2,
        }
    )
    with connect(database) as connection, transaction(connection):
        version = reset_profile(connection, "global_display_order", "global_display_order_rule")
        display_order_store.insert_global_display_order(
            connection, stored, version=version, source="검사 전에 저장된 대소문자 중복"
        )
    clear_global_display_order_cache()
    # 저장소는 프로세스마다 한 번 만들며 그때 기동 보강을 돈다. 새로 만들어 그 길도 지나게 한다.
    clear_scenario_repository()

    app = AppTest.from_string(
        _home_script(database, retain_process_dialog=True), default_timeout=300
    ).run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("중복" in text for text in data_error_texts(app))


def test_home_renders_summary_dashboard_from_the_builtin_seed(seeded_database: Path) -> None:
    app = _run(seeded_database)

    assert [element.value for element in app.title] == ["Capa LOB Summary"]
    # 내장 시드 프리셋이 복원한 조회기간. 판정 기준은 사이드바에 입력 칸이 없고 Preference 의
    # 공용 프로필이 정한다(2026-10-06 사용자 결정) — 저장 전에는 공식버전 프리셋 값을 쓴다.
    assert app.session_state["production_month_range_v2"] == ("2026-01", "2026-12")
    assert [widget.label for widget in app.sidebar.number_input] == []
    # 판정 기준을 정하는 자리는 사이드바가 아니라 Guide 가 말한다(2026-10-10 사용자 결정 —
    # 사이드바에 늘 한 줄을 차지하던 것을 걷었다. 2026-11-04 설계 규칙 UI-TXT-03 — 길 안내 글은
    # 어디에도 없다).
    assert not any("에서 정합니다" in element.value for element in app.sidebar.caption)

    # 그리는 차례다 — 라벨 칸 넷을 먼저, 그 다음 월 칸 넷. 요약 라벨은 trace 0(격자와
    # 글자가 전부 layout 항목이다), 계획 세부수량 라벨은 글자 trace 둘(머리글·값), 나머지 라벨
    # 둘은 `go.Table` 하나씩이다. 월 칸은 요약 16(표·꺾은선·막대 3 + 제품별 비중 도넛 13 —
    # 12개월과 26년 Total 칸마다 하나), 계획 세부수량 2(머리글·값 글자), 주요공정 히트맵 3(hover
    # 표적 막대·칸 막대·확보율 글자), B/N 상세 4(hover 표적·트랙·확보율 막대·공정명)다. 값이
    # 커지면 trace 를 늘린 것이다.
    assert app.session_state["spy_traces"] == [0, 2, 1, 1, 16, 2, 3, 4]
    assert app.session_state["spy_scrollbars"] == 1

    # 보는 조건 토글은 모두 사이드바 `LOB 표시 조건` 카드다(2026-09-29 사용자 결정 — 전에는
    # 제목 줄과 Preference 의 표시 기준에 흩어져 있었다). 순서는 계산이 얹히는 순서와 같다 —
    # 선행 B/O(계획 밖 재공)·선행 입고(표시만) → 확보율 보정(기준정보 밖 변수) → GAP(비교 표기) →
    # 보는 폭(상세 계획·EDP·Past). 라벨은 2026-09-29·2026-10-06 사용자 결정이다.
    assert [widget.label for widget in app.sidebar.toggle] == HOME_VIEW_TOGGLES
    assert [widget.label for widget in app.main.toggle] == []
    # 본문에는 편집기가 없다 — Preference·Past Data 는 사이드바 「HOME 설정」 팝업
    # 안이다(2026-11-02). 주요 Case 칩 셋은 사이드바 `LOB 표시 조건` 카드 맨 위다 — 이 실행에는 입장
    # 화면 요약이 없어 공식버전을 모르므로 공식 칩은
    # 「공식」(잠김)이다(`test_home_main_case_chips.py`). `Guide` 는 툴바 버튼이 누르는 숨은
    # 버튼이다.
    assert sorted(widget.label for widget in app.button) == sorted(
        ["공식", "Case1", "Case2", "Guide", "전체 3공정", "프리셋 없음", "HOME 설정"]
    )
    # 「HOME 설정」 상자는 카드 위다 — 펼친 카드 밑이면 작은 화면의 사이드바 첫 화면 밖이다.
    assert [widget.label for widget in app.sidebar.button][-4:] == [
        "HOME 설정",
        "공식",
        "Case1",
        "Case2",
    ]
    assert list(app.number_input) == []
    assert [button.label for button in app.download_button] == []
    # 프리셋이 없는 칸은 잠기고 만드는 자리는 풍선이 말한다 — 이름 줄에 길 안내를 적지 않는다.
    assert app.button(key=KEY_PROCESS_FIELD_KEY).disabled
    assert app.button(key=KEY_PROCESS_FIELD_KEY).help == KEY_PROCESS_LOCKED_HELP
    assert "HOME 설정에서 만듭니다" not in [element.value for element in app.sidebar.caption]

    app = _open_settings(app)

    # 팝업 안 Preference — 내장 시드 공식버전 프리셋의 1.095·0.995 를 정수 % 로 읽는다(2026-11-01
    # 사용자 결정). 「주요 Case」 상자(2026-10-23)는 Case 마다 시나리오 상자가 서고 지정 전이라
    # 빈다.
    assert [
        (widget.label, widget.value)
        for widget in app.number_input
        if widget.label.startswith("기본")
    ] == [("기본 확보 기준(%)", 110), ("기본 경고 기준(%)", 100)]
    assert list(app.main.number_input) == []
    from capa_simulation.components.home_main_cases import main_case_scenario_key

    assert [app.selectbox(key=main_case_scenario_key(case)).value for case in (1, 2)] == [
        None,
        None,
    ]
    # 붙여넣기는 표마다 작업 줄의 단추(누르면 그 표 상자 안에 붙여넣기 칸)이고, 저장은 Past Data
    # 맨 위 한 곳이다. 남은 내려받기는 Past Data 탭의 양식 세 개뿐이다.
    assert sorted(widget.label for widget in app.button) == sorted(
        [
            "공식",
            "Case1",
            "Case2",
            "HOME 설정",
            "Excel 붙여넣기",
            "Excel 붙여넣기",
            "Excel 붙여넣기",
            "Guide",
            "공지 저장",
            "전체 3공정",
            "프리셋 없음",
            "과거 구간 저장",
            "선행 B/O 저장",
            "선행 입고 저장",
            "확보율 보정 저장",
            "프리셋 저장",
            "판정 기준 저장",
            "확보율 구간 저장",
        ]
    )
    # 양식 내려받기는 붙여넣기 칸의 작업 줄에 선다(`tests/test_past_data.py`) — 칸을 펴기 전에는
    # 없다.
    assert not app.download_button
    # 팝업 뒤의 대시보드는 그대로다(그림 수·차례가 같다).
    assert app.session_state["spy_traces"] == [0, 2, 1, 1, 16, 2, 3, 4]


def test_home_has_no_tab_bar_and_starts_with_the_dashboard(seeded_database: Path) -> None:
    """HOME 은 탭 없이 Main 한 화면이다(2026-11-02 사용자 요청 — 전에는 Main·Preference·Past Data
    세 탭). 탭 줄이 없어 화면 탭 줄 바로 밑에서 Summary 가 시작하고, 차트는 첫 회차부터 그린다.
    공용 설정 팝업 안의 탭 다섯은 팝업을 열었을 때만 선다."""
    app = _run(seeded_database)

    assert [tab.label for tab in app.tabs] == []
    assert app.session_state["spy_traces"] == [0, 2, 1, 1, 16, 2, 3, 4]
    # 주요 Case 칩은 본문 제목 줄 끝이 아니라 사이드바 카드 안이다.
    sidebar_keys = {str(button.key) for button in app.sidebar.button}
    assert {
        "home_main_case_chip_official",
        "home_main_case_chip_case1",
        "home_main_case_chip_case2",
    } <= sidebar_keys
    assert not [button for button in app.main.button if "home_main_case_chip" in str(button.key)]

    app = _open_settings(app)
    # 팝업 안 탭은 쓰는 묶음 다섯이다(2026-11-04 사용자 검수 home-u01 — 전에는 Preference ·
    # Past Data).
    assert [tab.label for tab in app.tabs] == [
        ":material/compare_arrows: 비교 · 주요 Case",
        ":material/rule: 판정 기준",
        ":material/edit_calendar: 선행 · 보정",
        ":material/campaign: 공지 · 표시",
        ":material/history: Past Data",
    ]
    # 머리 안내 글은 없다 — 공용 설정 · 닫으면 사라짐은 저장 단추 풍선이 말한다.
    assert not [text for text in (c.value for c in app.caption) if "공용 설정입니다" in text]
    saves = {
        button.label: button.help
        for button in app.button
        if button.label
        in ("판정 기준 저장", "선행 B/O 저장", "선행 입고 저장", "공지 저장", "확보율 구간 저장")
        + ("프리셋 저장", "확보율 보정 저장")
    }
    assert len(saves) == 7 and all("공용 설정" in str(text) for text in saves.values()), saves


REQUIRED_EXCLUSION_PHRASE = "소요대수에 들지 않은 수요가 있습니다"


def test_home_keeps_left_out_demand_warnings_for_the_admin_alert_board(tmp_path: Path) -> None:
    """부하량에서 빠진 계획이 있어도 HOME 에는 경고 줄을 띄우지 않는다(2026-10-19 사용자 요청).

    한 제품의 Chip 구성을 빼면 그 제품 계획은 부하량에서 빠진다. 그런 알림은 HOME 에 줄줄이 달려
    읽히지 않았다 — Admin Area 「알림 모음」 이 시나리오 전체 기간으로 모은다
    (`tests/test_alert_board.py`). 결론 두 줄(최저 확보율 공정·기준 미달 수)도 HOME 에 없다.
    """
    app = AppTest.from_string(_home_script(tmp_path / "scenario.duckdb"), default_timeout=300)
    app.run()
    assert not list(app.exception)
    assert not [item.value for item in app.warning if REQUIRED_EXCLUSION_PHRASE in item.value]

    scenario = app.session_state["active_scenario"]
    chip = scenario["tables"]["RQ_CHIP_QTY"]
    product = chip["제품정보"].iloc[-1]
    updated = dict(scenario)
    updated["tables"] = {
        **scenario["tables"],
        "RQ_CHIP_QTY": chip.loc[chip["제품정보"].ne(product)].reset_index(drop=True),
    }
    updated["revision"] = scenario["revision"] + 1
    updated["content_token"] = f"home-chip-qty-dropped-{tmp_path.name}"
    app.session_state["active_scenario"] = updated
    app.run()

    assert not list(app.exception)
    assert not [item.value for item in app.warning if REQUIRED_EXCLUSION_PHRASE in item.value]
    assert not [item.value for item in app.markdown if "가장 낮은 확보율은" in item.value]
    assert not [item.value for item in app.caption if "판정 가능한" in item.value]


def test_the_bottleneck_detail_chart_keeps_hover_on(seeded_database: Path) -> None:
    """상세 B/N 월 Figure 의 hover 는 `staticPlot` 을 빼 둔 것이 유일한 근거다.

    같은 캔버스의 상세 두 Figure 중 계획 세부수량 쪽은 `staticPlot: True` 라, 일관성을
    이유로 이 한 곳에 다시 넣으면 hover 가 조용히 죽는다. 그 한 줄을 여기서 고정한다.
    """
    app = _run(seeded_database)
    configs = app.session_state["spy_configs"]

    bottleneck_config = configs["bottleneck_detail_months"]
    assert "staticPlot" not in bottleneck_config
    assert bottleneck_config["displayModeBar"] is False
    # `staticPlot` 을 빼면 기본값으로 돌아오는 둘도 함께 꺼져 있어야 한다.
    assert bottleneck_config["doubleClick"] is False
    assert bottleneck_config["showAxisDragHandles"] is False

    assert configs["production_detail_months"]["staticPlot"] is True
    assert configs["bottleneck_detail_labels"]["staticPlot"] is True


def test_only_the_three_month_figures_open_the_process_detail_on_a_cell_click(
    seeded_database: Path,
) -> None:
    """칸·막대를 누르면 공정 Capa 상세가 열리는 그림은 `Capa LOB 현황`(생산계획 LOB 의 B/N 막대 ·
    B/N Top 5 막대 — 2026-10-18 사용자 요청)·`주요공정 확보율`·`상세 B/N 공정` 월 그림 셋뿐이다.

    `on_select` 를 지우면 클릭이 조용히 죽고, 다른 그림에 켜면 그 그림 위 터치 스크롤이 막힌다 —
    선택을 켠 그림은 정확히 터치 스크롤 막이에 넘기는 묶음(`HOME_CELL_CHART_KEYS`)이어야 한다.
    """
    app = _run(seeded_database)
    selections = app.session_state["spy_selections"]

    assert len(selections) == 8
    linked = {key for key, (on_select, _) in selections.items() if on_select != "ignore"}
    assert linked == set(HOME_CELL_CHART_KEYS)
    for key, section in (
        (LOB_MONTHS_CHART_KEY, HOME_LOB_SECTION),
        (KEY_PROCESS_MONTHS_CHART_KEY, HOME_KEY_PROCESS_SECTION),
        (BOTTLENECK_MONTHS_CHART_KEY, HOME_BOTTLENECK_SECTION),
    ):
        on_select, selection_mode = selections[key]
        assert isinstance(on_select, partial)
        # 콜백은 자기 그림의 선택 칸과 자기 구획 이름을 읽는다.
        assert (on_select.func, on_select.args) == (open_clicked_home_cell, (key, section))
        assert selection_mode == "points"


def test_home_reuses_cached_figures_on_an_unchanged_rerun(seeded_database: Path) -> None:
    app = _run(seeded_database)

    app.session_state["dashboard_show_performance"] = True
    app.run()

    assert not list(app.exception)
    assert _cache_state(app) == "적중"
    # 고른 수는 캡션이 아니라 공정 필터 값 칸에 있다 — 좁혀 놓은 수가 팝업을 열지 않아도 보인다.
    assert "전체 3공정" in [button.label for button in app.button]


def _cache_state(app: AppTest) -> str:
    states = [
        element.value.removeprefix("Figure 캐시: ")
        for element in app.caption
        if element.value.startswith("Figure 캐시: ")
    ]
    assert len(states) == 1, f"Figure 캐시 캡션이 하나여야 한다: {states}"
    return states[0]


def _rebuilt_bundles(app: AppTest) -> set[str]:
    """성능 진단이 적은 「새로 만든 묶음」. 네 묶음이 다 맞았으면 빈 집합이다."""
    for element in app.caption:
        if element.value.startswith("새로 만든 묶음: "):
            return set(element.value.removeprefix("새로 만든 묶음: ").split(" · "))
    return set()


def _save_default_warning(app: AppTest, percent: int) -> AppTest:
    """「HOME 설정」 팝업 Preference 의 판정 기준 편집기로 기본 경고 기준을 저장한다(팝업은 열린
    채다 — 저장 뒤에도 열어 둔다)."""
    next(widget for widget in app.number_input if widget.label == "기본 경고 기준(%)").set_value(
        percent
    )
    next(button for button in app.button if button.label == "판정 기준 저장").click()
    return app.run()


def test_home_rebuilds_figures_when_a_threshold_changes(seeded_database: Path) -> None:
    # 같은 모듈 DB 를 쓰는 앞 시험이 같은 pristine 키의 그림을 공용 칸에 남겼을 수 있다. 남아
    # 있으면 처음 보는 조합도 복원되어 「생성」을 볼 수 없다.
    shared_home_figure_store.clear()
    app = _run(seeded_database)
    app.session_state["dashboard_show_performance"] = True
    app.run()
    assert _cache_state(app) == "적중"

    # 판정 기준은 Figure 캐시 키에 포함되어야 한다(AGENTS.md 5장 불변조건 7). 기준은 사이드바가
    # 아니라 「HOME 설정」 팝업 Preference 의 공용 프로필에서 바꾼다. 팝업이 열린 동안은 팝업을 열기
    # 전 그림을 그대로 쓰고(「유지」), 닫는 회차에 새 기준으로 만든다.
    app = _open_settings(app)
    try:
        app = _save_default_warning(app, 95)

        assert not list(app.exception), [element.message for element in app.exception]
        assert not list(app.error), [element.value for element in app.error]
        assert app.session_state[HOME_DIALOG_KEY] == "settings"
        assert _cache_state(app) == "유지"

        app = _close_settings(app)
        assert _cache_state(app) == "생성"
        # 판정 기준은 색을 칠하는 세 묶음에만 닿는다. 계획 세부수량은 그대로 꺼낸다.
        assert _rebuilt_bundles(app) == {"LOB", "주요공정", "상세 B/N"}

        # 조건이 그대로면 다시 캐시를 재사용한다.
        app.run()
        assert _cache_state(app) == "적중"
    finally:
        # 모듈 공용 DB 다. 뒤 테스트가 같은 기준(100% — 옛 99.5 와 같은 판정)에서 출발하게 되돌린다.
        app = _open_settings(app)
        app = _save_default_warning(app, 100)
        app = _close_settings(app)
    assert not list(app.error), [element.value for element in app.error]


def test_home_reports_a_missing_active_revision_instead_of_a_traceback(tmp_path: Path) -> None:
    """공식버전이 없는 저장소로 열면 활성 리비전이 없어 RuntimeError 가 난다.

    14개 페이지 중 HOME 만 이것을 잡지 않아 원문 트레이스백을 그대로 보여 줬다. 안내 한 줄과
    멈춤이어야 한다.
    """
    from capa_simulation.persistence.models import ScenarioCreate, ScenarioPreset
    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.services.builtin_seed import (
        BUILTIN_SEED_MONTHS,
        build_builtin_seed_dataset,
        builtin_seed_processes,
    )

    database = tmp_path / "unpublished.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    prepared = build_builtin_seed_dataset()
    repository.create_scenario(
        ScenarioCreate(
            scenario_name="공식버전 없는 시나리오",
            source_simulation_code="USER-SCENARIO-001",
            source_simulation_name="사용자 원천",
            source_type="TEST",
            pipeline_version="test-v1",
        ),
        prepared.reference_tables,
        ScenarioPreset(
            min(BUILTIN_SEED_MONTHS), max(BUILTIN_SEED_MONTHS), builtin_seed_processes()
        ),
        source_data=prepared.source_data,
    )

    app = AppTest.from_string(_home_script(database), default_timeout=300).run()

    assert not list(app.exception)
    assert len(data_error_texts(app)) == 1


def test_home_names_the_data_range_when_the_selection_is_outside_it(seeded_database: Path) -> None:
    """ "데이터가 없습니다" 만으로는 어디로 옮겨야 하는지 알 수 없다. 있는 범위를 같이 말한다."""
    app = _run(seeded_database)

    app.session_state["production_month_range_v2"] = ("2029-01", "2029-03")
    app.run()

    assert not list(app.exception)
    (error,) = data_error_texts(app)
    assert "데이터 범위" in error


HOME_VIEW_TOGGLES = [
    "선행 B/O",
    "선행 입고",
    "확보율 보정",
    "GAP",
    "상세 계획",
    "EDP 포함",
    "Past Data 포함",
]


def _save_plan_with_blank_product_type(database_path: Path, *, publish: bool) -> tuple[str, str]:
    """공식 리비전 계획에서 `DEMO PRODUCT B` 행의 제품타입만 비운 리비전을 새 시나리오로 저장한다.

    `publish` 면 그 리비전을 새 공식버전으로 발행해 새 세션의 활성 시나리오가 되게 하고, 아니면
    비교 대상으로만 쓴다. 돌려주는 것은 (시나리오 id, 리비전 id) 다.
    """
    from capa_simulation.persistence.cache import load_scenario_snapshot
    from capa_simulation.persistence.models import ScenarioCreate
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    repository = DuckDBScenarioRepository(database_path)
    official = repository.latest_official_release()
    assert official is not None
    snapshot = load_scenario_snapshot(str(database_path), official.revision_id)
    tables = dict(snapshot.tables)
    plan = tables["RQ_PKG_PLAN"].copy()
    blank_rows = plan["제품정보"].eq("DEMO PRODUCT B")
    assert blank_rows.any()
    plan.loc[blank_rows, "제품타입"] = None
    tables["RQ_PKG_PLAN"] = plan
    created = repository.create_scenario(
        ScenarioCreate(
            scenario_name="제품타입 빈 계획",
            source_simulation_code="BLANK-TYPE-1",
            source_simulation_name="제품타입 빈 계획",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="duckdb-rq-snapshot-v3",
        ),
        tables,
        snapshot.preset,
    )
    scenario_id = str(created.scenario.scenario_id)
    revision_id = str(created.revision.revision_id)
    if publish:
        repository.publish_official_revision(
            scenario_id, revision_id, release_name="제품타입 빈 계획"
        )
    return scenario_id, revision_id


def test_a_stopped_home_still_offers_the_edp_toggle_its_error_asks_for(tmp_path: Path) -> None:
    """계산이 멈춘 회차에도 사이드바 `LOB 표시 조건` 카드가 선다(2026-10-22 사용자 결정).

    EDP 를 뺀 조회(기본)는 계획에 제품타입이 빈 행이 있으면 「… EDP 를 포함해 조회하세요」로
    멈춘다. 카드가 정상 회차에서만 서면 그 토글을 켤 곳이 없다. 토글 key 가 정상 회차와 같아야 켠
    값으로 다음 회차가 정상 계산으로 돌아온다.
    """
    database_path = tmp_path / "scenario.duckdb"
    AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    _save_plan_with_blank_product_type(database_path, publish=True)

    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()

    assert not list(app.exception), [element.message for element in app.exception]
    (error,) = data_error_texts(app)
    assert "제품타입이 비어" in error
    assert "EDP 를 포함해" in error
    assert [widget.label for widget in app.sidebar.toggle] == HOME_VIEW_TOGGLES
    assert app.sidebar.toggle(key=EDP_TOGGLE_KEY).value is False
    # 「HOME 설정」 상자는 잠긴 채 같은 자리(카드 바로 위)에 선다 — 팝업 본문이 계산 결과를 쓴다.
    assert app.button(key=SETTINGS_BUTTON_KEY).disabled
    stopped_keys = _sidebar_keys(app)
    assert stopped_keys.index(SETTINGS_BOX) == stopped_keys.index(VIEW_CARD) - 1
    assert app.session_state["spy_traces"] == []

    app.sidebar.toggle(key=EDP_TOGGLE_KEY).set_value(True)
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert place_errors(app) == []
    assert not app.button(key=SETTINGS_BUTTON_KEY).disabled
    # 정상 회차도 같은 차례다(상자 바로 밑이 카드).
    keys = _sidebar_keys(app)
    assert keys.index(SETTINGS_BOX) == keys.index(VIEW_CARD) - 1
    assert app.session_state["spy_traces"]


def _publish_blank_run_rate(database_path: Path) -> None:
    """공식 리비전의 효율(`RQ_RUN_RATE`) 값 한 칸을 비운 리비전을 새 공식버전으로 낸다 — 기준 정보의
    빈 칸을 채우면 풀리는 계산 멈춤이다."""
    from capa_simulation.persistence.cache import load_scenario_snapshot
    from capa_simulation.persistence.models import ScenarioCreate
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    repository = DuckDBScenarioRepository(database_path)
    official = repository.latest_official_release()
    assert official is not None
    snapshot = load_scenario_snapshot(str(database_path), official.revision_id)
    tables = dict(snapshot.tables)
    run_rate = tables["RQ_RUN_RATE"].copy()
    run_rate["CAPA_RUN_RATE"] = run_rate["CAPA_RUN_RATE"].astype("object")
    run_rate.loc[run_rate.index[0], "CAPA_RUN_RATE"] = None
    tables["RQ_RUN_RATE"] = run_rate
    created = repository.create_scenario(
        ScenarioCreate(
            scenario_name="효율 빈 칸",
            source_simulation_code="BLANK-RATE-1",
            source_simulation_name="효율 빈 칸",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="duckdb-rq-snapshot-v3",
        ),
        tables,
        snapshot.preset,
    )
    repository.publish_official_revision(
        str(created.scenario.scenario_id),
        str(created.revision.revision_id),
        release_name="효율 빈 칸",
    )


def test_a_blank_stop_on_home_opens_the_screen_to_fill(tmp_path: Path) -> None:
    """기준 정보의 빈 칸으로 멈춘 HOME 의 오류 알림은 무엇을 · 어디서 채우는지 말하고 「그
    화면으로」 가 기준 정보를 연다(UI-NTF-06 · UI-NTF-08). 전문 첫머리의 화면 이름은 앱이 적은
    화면에서 온다 — 이 실행은 `app.py` 를 거치지 않아 비어 있다(`tests/test_page_bootstrap.py`)."""
    database_path = tmp_path / "scenario.duckdb"
    AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    _publish_blank_run_rate(database_path)

    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()

    assert not list(app.exception), [element.message for element in app.exception]
    (note,) = [item for item in alert_notes(app) if item["code"] == "HM-01"]
    assert note["short"].startswith("대당 Capa 계산 멈춤 — 기준 정보 「효율」 빈 칸 ")
    assert (note["page"], note["href"]) == ("기준 정보", REFERENCE_DATA.href)
    assert note["full"].startswith("대당 Capa 계산이 멈췄습니다. 기준 정보 「효율」 표의 ")
    assert "RQ_RUN_RATE" not in note["full"]


def test_a_stopped_home_keeps_both_page_rows_locked_in_the_panel(tmp_path: Path) -> None:
    """계산이 멈춰도 패널의 공정 필터 · 주요공정 히트맵 줄은 잠긴 채 선다 — 한 줄이라도 빠지면 그
    아래 상자가 줄 높이만큼 움직인다(UI-PRF-03). 잠긴 「HOME 설정」 풍선은 오류 글이 있는 Alarm 을
    가리킨다."""
    database_path = tmp_path / "scenario.duckdb"
    AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    _publish_blank_run_rate(database_path)

    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()

    assert not list(app.exception), [element.message for element in app.exception]
    for key in ("dashboard_bottleneck_process_dialog_open", KEY_PROCESS_FIELD_KEY):
        assert app.button(key=key).label == "계산 멈춤"
        assert app.button(key=key).disabled
    assert "Alarm 의 오류" in str(app.button(key=SETTINGS_BUTTON_KEY).help)


def test_a_stopped_home_still_offers_the_gap_toggle_when_the_comparison_stops_it(
    tmp_path: Path,
) -> None:
    """비교 시나리오 계획에 빈 제품타입이 있어 멈춘 회차에도 카드의 `GAP` 을 끌 수 있다."""
    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)
    scenario_id, revision_id = _save_plan_with_blank_product_type(database_path, publish=False)
    _pick_comparison(app, scenario_id, revision_id)
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    (error,) = data_error_texts(app)
    assert "제품타입이 비어" in error
    assert app.button(key=SETTINGS_BUTTON_KEY).disabled
    gap = app.sidebar.toggle(key=COMPARISON_TOGGLE_KEY)
    assert gap.value is True
    assert not gap.disabled

    gap.set_value(False)
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert place_errors(app) == []
    assert not app.button(key=SETTINGS_BUTTON_KEY).disabled


def test_the_two_display_toggles_are_part_of_the_figure_cache_key(
    seeded_database: Path,
) -> None:
    """EDP 포함 여부와 선행 반영 여부는 그림을 바꾼다. 캐시 키에 없으면 옛 그림이 남는다."""
    # 같은 모듈 DB 를 쓰는 앞 시험이 같은 pristine 키의 그림을 공용 칸에 남겼을 수 있다. 남아
    # 있으면 처음 보는 조합도 복원되어 「생성」을 볼 수 없다.
    shared_home_figure_store.clear()
    app = _run(seeded_database)
    app.session_state["dashboard_show_performance"] = True
    app.run()
    assert _cache_state(app) == "적중"

    # `EDP 포함` 의 기본은 꺼짐이다. 켜면 새로 그려야 한다 — LOB 로 표현되는 값을 읽는 세 묶음만.
    # 히트맵은 확보율만 읽고, 선행 B/O 가 꺼져 있으면 확보율은 EDP 와 무관하다.
    app.session_state["home_preference_include_edp"] = True
    app.run()
    assert not list(app.exception)
    assert _cache_state(app) == "생성"
    assert _rebuilt_bundles(app) == {"LOB", "계획 세부수량", "상세 B/N"}

    app.session_state["home_preference_include_edp"] = False
    app.run()
    # 되돌리면 다시 만들지 않는다. 두 토글을 오가며 비교하는 화면이라 칸이 넉넉해야 한다.
    assert _cache_state(app) == "적중"

    app.session_state["home_show_advance"] = True
    app.run()
    assert not list(app.exception)
    assert _cache_state(app) == "생성"
    # 선행 B/O 는 세부수량에 걸지 않는다.
    assert _rebuilt_bundles(app) == {"LOB", "주요공정", "상세 B/N"}


def test_advance_scales_the_plan_and_rate_but_leaves_capacity_alone(
    seeded_database: Path,
) -> None:
    """선행은 물량을 앞으로 옮긴 것이라 Capa 가 움직이면 안 된다.

    서비스 단위 시험이 있어도 페이지가 기존 계획과 선행 계획을 뒤바꿔 넘기면 여기서만
    드러난다. 그래서 화면까지 통과한 Figure 값으로 다시 확인한다.
    """
    import capa_simulation.settings as settings
    from capa_simulation.persistence.cache import clear_global_advance_load_cache
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    app = _run(seeded_database)
    before = _lob_traces(app)
    first_month_capacity = before["B/N 공정"].y[0]
    first_month_density = before["Density"].y[0]
    # 첫 달은 시드 프리셋이 정한다. 숫자를 적어 두면 시드가 바뀔 때 엉뚱한 달에 넣는다.
    # 점마다 [월 라벨, 공정 Capa 상세 이동 정보…] 다 — 첫 칸이 라벨이다.
    first_month = 200000 + int(str(before["Density"].customdata[0][0]).replace(".", ""))

    repository = DuckDBScenarioRepository(settings.DUCKDB_PATH)
    repository.replace_global_advance_load(
        pd.DataFrame({"생산계획년월": [first_month], "선행 물량": [2.5]}),
        source="테스트",
    )
    clear_global_advance_load_cache()
    try:
        app.session_state["home_show_advance"] = True
        app.run()

        assert not list(app.exception)
        after = _lob_traces(app)
        # 계획은 넣은 만큼 정확히 늘고, 그 달의 Capa 는 그대로다.
        assert after["Density"].y[0] == pytest.approx(first_month_density + 2.5)
        assert after["B/N 공정"].y[0] == pytest.approx(first_month_capacity)
        # 기존 계획은 표식·라벨 없는 점선으로 함께 남는다.
        assert after["Density (선행 B/O 전)"].y[0] == pytest.approx(first_month_density)
        assert after["Density (선행 B/O 전)"].mode == "lines"
        assert after["Density (선행 B/O 전)"].line.dash == "dot"
    finally:
        # 모듈 공용 DB 다. 뒤 시험이 선행 물량 없는 상태에서 출발하게 되돌린다.
        repository.replace_global_advance_load(
            pd.DataFrame(
                {
                    "생산계획년월": pd.Series(dtype="int64"),
                    "선행 물량": pd.Series(dtype="float64"),
                }
            ),
            source="테스트",
        )
        clear_global_advance_load_cache()


def _corner_notes(app: AppTest) -> dict[str, tuple[str, str, float]]:
    """LOB 월 Figure 의 Density 칸 오른쪽 끝 글자(선행 입고 실적) — 월 라벨 → (글자, hover, x).

    색으로 고르지 않는다 — 어두운 테마에서는 값과 같은 본문 글자색이다. hover 글자로 고른다.
    """
    figure = app.session_state["spy_figures"]["production_lob_months"]
    labels = _lob_month_labels(app)
    notes: dict[str, tuple[str, str, float]] = {}
    for annotation in figure.layout.annotations:
        if annotation.xanchor != "right" or not str(annotation.hovertext or "").startswith(
            "선행 입고 실적"
        ):
            continue
        # 값과 같은 높이·증감과 같은 고정 크기다(2026-10-07 사용자 결정).
        assert annotation.yanchor == "middle"
        assert annotation.yshift == pytest.approx(delta_ink_yshift_px())
        assert annotation.font.size == tokens.DELTA_FONT_SIZE_PX
        assert annotation.font.color == tokens.ADVANCE_SHIPMENT_TEXT
        index = round(float(annotation.x) * len(labels)) - 1
        notes[labels[index]] = (
            str(annotation.text),
            str(annotation.hovertext),
            float(annotation.x),
        )
    return notes


def test_the_advance_shipment_toggle_writes_notes_in_the_density_cells(tmp_path: Path) -> None:
    """「선행 입고」 를 켜면 선행 입고 실적이 Density 칸 오른쪽 끝, 값과 같은 높이에 적힌다.

    과거 달도 적는다.

    계산은 바꾸지 않는다 — 값·선 모두 그대로이고 글자만 더해진다. 토글과 프로필 version 은
    Figure 캐시 키에 든다.
    """
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    database_path = tmp_path / "scenario.duckdb"
    _seed_past_months(database_path, [202512])
    DuckDBScenarioRepository(database_path).replace_global_advance_shipment(
        pd.DataFrame({"생산계획년월": [202512, 202601, 202602], "선행 입고": [1.2, -0.5, 0.0]}),
        source="테스트",
    )
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception), [element.message for element in app.exception]
    app.session_state["production_month_range_v2"] = ("2025-12", "2026-12")
    app.session_state["dashboard_show_performance"] = True
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state["home_show_advance_shipment"] is False
    assert _corner_notes(app) == {}
    before_density = _lob_traces(app)["Density"].y
    before_slots = _value_slots(app)

    app.session_state["home_show_advance_shipment"] = True
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert _cache_state(app) == "생성"
    # 글자만 더해지는 LOB 묶음 하나만 다시 그린다.
    assert _rebuilt_bundles(app) == {"LOB"}
    notes = _corner_notes(app)
    labels = _lob_month_labels(app)
    assert {label: note[:2] for label, note in notes.items()} == {
        "25.12": ("+1.2", "선행 입고 실적 +1.2억Gb"),
        "26.01": ("-0.5", "선행 입고 실적 -0.5억Gb"),
    }
    # 칸 오른쪽 끝에 붙는다 — x 는 그 칸의 오른쪽 경계다.
    assert notes["26.01"][2] == pytest.approx((labels.index("26.01") + 1) / len(labels))
    # 값의 자리·크기와 Density 선은 그대로다.
    assert _value_slots(app) == before_slots
    assert list(_lob_traces(app)["Density"].y) == list(before_density)

    app.session_state["home_show_advance_shipment"] = False
    app.run()
    assert _cache_state(app) == "적중"
    assert _corner_notes(app) == {}


def test_the_advance_shipment_editor_offers_past_months_too(tmp_path: Path) -> None:
    """선행 입고 실적은 실적이라 지난 달에 넣는다 — 편집기 칸은 LOB 월 축의 과거 달까지 연다."""
    database_path = tmp_path / "scenario.duckdb"
    _seed_past_months(database_path, [202512, 202511])
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception), [element.message for element in app.exception]
    app.session_state["production_month_range_v2"] = ("2025-11", "2026-12")
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    app = _open_settings(app)

    editors = {
        str(frame.value.iloc[0]["구분"]): list(frame.value.columns)
        for frame in app.dataframe
        if "구분" in frame.value.columns and len(frame.value) == 1
    }
    assert editors["선행 입고 실적"][1:3] == ["25.11", "25.12"]
    # 칸은 LOB 월 축(연간 Total 을 뺀 달)과 같다.
    assert editors["선행 입고 실적"][1:] == [
        label for label in _lob_month_labels(app) if "." in label
    ]


def _lob_traces(app: AppTest) -> dict[str, Any]:
    """LOB 월 Figure 의 trace 를 이름으로 찾는다. 순서는 trace 를 더할 때마다 바뀐다."""
    figure = app.session_state["spy_figures"]["production_lob_months"]
    return {trace.name: trace for trace in figure.data}


def _create_comparison_scenario(
    database_path: Path, factor: float, *, name: str = "비교용"
) -> tuple[str, str]:
    """현재 활성 계획의 수량만 바꾼 비교용 시나리오를 만든다(이름은 겹칠 수 없어 둘째부터 `name`).

    계획만 다르고 나머지 기준정보는 같아야 GAP 이 계획 차이만 나타내는지 확인할 수 있다.
    """
    from capa_simulation.persistence.cache import load_scenario_snapshot
    from capa_simulation.persistence.models import ScenarioCreate
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    repository = DuckDBScenarioRepository(database_path)
    official = repository.latest_official_release()
    assert official is not None
    snapshot = load_scenario_snapshot(str(database_path), official.revision_id)
    tables = dict(snapshot.tables)
    plan = tables["RQ_PKG_PLAN"].copy()
    plan["생산수량"] = pd.to_numeric(plan["생산수량"], errors="coerce") * factor
    tables["RQ_PKG_PLAN"] = plan
    created = repository.create_scenario(
        ScenarioCreate(
            scenario_name=name,
            source_simulation_code="COMPARE-1",
            source_simulation_name=name,
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="duckdb-rq-snapshot-v3",
        ),
        tables,
        snapshot.preset,
    )
    return str(created.scenario.scenario_id), str(created.revision.revision_id)


def _pick_comparison(app: AppTest, scenario_id: str, revision_id: str) -> None:
    """비교 대상을 고른 상태로 만든다. 목록에 실린 **뒤에** 골라야 한다.

    AppTest 는 다음 실행을 시작할 때 직전 화면의 위젯 옵션으로 세션 값을 되짚는다. 화면이
    한 번도 보여 준 적 없는 시나리오를 세션에 바로 꽂으면 옵션에 없는 값이라며 멈춘다.
    실제 화면에서도 사용자는 목록에 뜬 뒤에야 고를 수 있으므로 한 번 더 돌려 맞춘다.
    """
    app.run()
    app.session_state["home_preference_comparison_scenario"] = scenario_id
    app.session_state["home_preference_comparison_revision"] = revision_id
    app.session_state["home_show_comparison"] = True


def test_comparison_gap_is_written_under_the_value(tmp_path: Path) -> None:
    """비교 GAP 은 값 아래에 붙는다. 선행 GAP(위)과 자리를 나눠 함께 켤 수 있어야 한다."""
    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)

    comparison_id, comparison_revision_id = _create_comparison_scenario(database_path, 0.5)
    _pick_comparison(app, comparison_id, comparison_revision_id)
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    gaps = _gap_annotations(app)
    # 계획을 절반으로 줄인 시나리오와 견주므로 현재가 더 많다 — 전부 증가여야 한다.
    assert gaps, "비교 GAP 주석이 하나도 없다"
    assert all(text.startswith("+") for text in gaps), gaps


def _gap_annotations(app: AppTest) -> list[str]:
    """LOB 월 Figure 에서 증감으로 적힌 주석만 고른다."""
    figure = app.session_state["spy_figures"]["production_lob_months"]
    return [
        str(annotation.text).strip()
        for annotation in figure.layout.annotations
        if str(annotation.text).strip().startswith(("+", "-"))
    ]


def test_a_comparison_revision_from_another_scenario_is_ignored(tmp_path: Path) -> None:
    """세션에 남은 리비전이 남의 것이면 조용히 비교를 끈다. 화면이 멈추면 안 된다."""
    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)

    comparison_id, _ = _create_comparison_scenario(database_path, 0.5)
    _pick_comparison(app, comparison_id, "사라진-리비전")
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert _gap_annotations(app) == []


def test_a_comparison_revision_deleted_after_the_check_draws_without_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """리비전을 확인한 뒤 계획을 읽기 전에 다른 세션이 그 시나리오를 지워도 HOME 은 GAP 없이 선다.

    계획 읽기는 지운 리비전에서 `KeyError` 를 낸다(빈 계획이 아니다). 확인에서 걸린 것과 같이
    조용히 비교를 끈다 — 화면 전체가 오류로 멈추면 안 된다.
    """
    import capa_simulation.persistence.cache as scenario_cache
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)

    comparison_id, comparison_revision_id = _create_comparison_scenario(database_path, 0.5)
    original_load_plan = scenario_cache.load_scenario_plan
    deleted: list[str] = []

    def delete_then_load(path: str, revision_id: str) -> pd.DataFrame:
        if revision_id == comparison_revision_id and not deleted:
            DuckDBScenarioRepository(database_path).delete_scenario(comparison_id)
            scenario_cache.clear_scenario_snapshot_cache()  # 삭제 경로가 부르는 비우기
            deleted.append(revision_id)
        return original_load_plan(path, revision_id)

    monkeypatch.setattr(scenario_cache, "load_scenario_plan", delete_then_load)
    _pick_comparison(app, comparison_id, comparison_revision_id)
    app.run()

    assert deleted == [comparison_revision_id]
    assert not list(app.exception), [element.message for element in app.exception]
    assert not list(app.error), [element.value for element in app.error]
    assert "production_lob_months" in app.session_state["spy_figures"]
    assert _gap_annotations(app) == []


@pytest.mark.parametrize("removal", ["archive_scenario", "delete_scenario"])
def test_a_comparison_scenario_removed_elsewhere_leaves_the_session_and_locks_gap(
    tmp_path: Path, removal: str
) -> None:
    """다른 곳(시나리오 관리)에서 비교 시나리오를 보관·영구 삭제하면 HOME 의 다음 회차가 세션의 비교
    짝을 걷고 「GAP」 을 잠근다 — 「HOME 설정」 팝업을 열지 않아도.

    저장소는 공용 프로필만 비우고 세션 값은 그대로다. 걷지 않으면 보관된 시나리오와 계속 견주고(GAP
    주석이 그대로), 삭제면 토글이 켜진 채 증감 없이 비어 있다. 전에는 숨은 `Preference` 탭의 피커가
    매 회차 걷었다 — 팝업으로 옮긴 뒤에는 HOME 첫머리의 정리(`forget_unlisted_comparison`)가 맡는다.
    """
    from capa_simulation.components.home_preference import (
        COMPARISON_REVISION_KEY,
        COMPARISON_SCENARIO_KEY,
        GAP_LOCKED_HELP,
    )
    from capa_simulation.persistence.cache import (
        clear_global_comparison_scenario_cache,
        clear_global_main_cases_cache,
        clear_scenario_snapshot_cache,
    )
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)
    comparison_id, comparison_revision_id = _create_comparison_scenario(database_path, 0.5)
    _pick_comparison(app, comparison_id, comparison_revision_id)
    app.run()
    assert _gap_annotations(app), "고른 비교 시나리오의 GAP 이 처음부터 없다"

    getattr(DuckDBScenarioRepository(database_path), removal)(comparison_id)
    # 시나리오 관리의 보관·삭제가 부르는 비우기 그대로.
    clear_scenario_snapshot_cache()
    clear_global_comparison_scenario_cache()
    clear_global_main_cases_cache()
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert COMPARISON_SCENARIO_KEY not in app.session_state
    assert COMPARISON_REVISION_KEY not in app.session_state
    assert _gap_annotations(app) == []
    gap = next(toggle for toggle in app.toggle if toggle.key == COMPARISON_TOGGLE_KEY)
    assert gap.disabled
    assert gap.help == GAP_LOCKED_HELP


def test_a_removed_comparison_gives_way_to_the_shared_profile_in_the_same_run(
    tmp_path: Path,
) -> None:
    """걷은 회차에 공용 프로필이 다른 비교 대상을 가리키면 그 회차에 바로 그것으로 선다(새 세션과
    같다).

    정리가 심기 **앞**이라 그렇다 — 뒤였다면 그 회차는 비교 없이 그리고 다음 회차에야 프로필 값이
    심긴다.
    """
    from capa_simulation.components.home_preference import COMPARISON_SCENARIO_KEY
    from capa_simulation.persistence.cache import (
        clear_global_comparison_scenario_cache,
        clear_global_main_cases_cache,
        clear_scenario_snapshot_cache,
    )
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)
    removed_id, removed_revision_id = _create_comparison_scenario(database_path, 0.5)
    shared_id, shared_revision_id = _create_comparison_scenario(
        database_path, 2.0, name="공용 비교"
    )
    repository = DuckDBScenarioRepository(database_path)
    repository.replace_global_comparison_scenario(shared_id, shared_revision_id, source="시험")
    clear_global_comparison_scenario_cache()
    _pick_comparison(app, removed_id, removed_revision_id)
    app.run()
    assert app.session_state[COMPARISON_SCENARIO_KEY] == removed_id

    repository.archive_scenario(removed_id)
    clear_scenario_snapshot_cache()
    clear_global_comparison_scenario_cache()
    clear_global_main_cases_cache()
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state[COMPARISON_SCENARIO_KEY] == shared_id
    gaps = _gap_annotations(app)
    # 계획을 두 배로 늘린 공용 비교 대상과 견주므로 전부 감소다.
    assert gaps and all(text.startswith("-") for text in gaps), gaps


def test_a_comparison_scenario_newer_than_the_cached_list_is_kept(tmp_path: Path) -> None:
    """비교 후보 목록은 캐시라 새로 만든 시나리오가 늦게 든다 — 그런 세션 값은 DB 로 확인하고
    남긴다.

    목록을 채운 뒤 만든 시나리오를 (프로필을 쓰지 않고) 세션에 고르면 캐시에는 없다. 캐시만 믿고
    걷으면 사용자가 방금 고른 비교가 말없이 사라진다.
    """
    from capa_simulation.components.home_preference import COMPARISON_SCENARIO_KEY

    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)
    first_id, first_revision_id = _create_comparison_scenario(database_path, 0.5)
    _pick_comparison(app, first_id, first_revision_id)
    app.run()
    assert _gap_annotations(app)

    newer_id, newer_revision_id = _create_comparison_scenario(database_path, 2.0, name="비교용 2")
    _pick_comparison(app, newer_id, newer_revision_id)
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state[COMPARISON_SCENARIO_KEY] == newer_id
    gaps = _gap_annotations(app)
    # 계획을 두 배로 늘린 시나리오와 견주므로 현재가 더 적다 — 전부 감소여야 한다.
    assert gaps and all(text.startswith("-") for text in gaps), gaps


def test_comparison_can_target_another_revision_of_the_same_scenario(tmp_path: Path) -> None:
    """리비전이 달라지며 계획이 얼마나 바뀌었는지가 비교의 중요한 쓰임이다.

    현재 활성 시나리오를 비교 대상에서 빼면 그 비교를 아예 할 수 없고, 시나리오가 하나뿐인
    저장소에서는 고를 것 자체가 없어진다.
    """
    from capa_simulation.persistence.cache import load_scenario_snapshot
    from capa_simulation.persistence.repository import REVISION_TABLES, DuckDBScenarioRepository

    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)

    repository = DuckDBScenarioRepository(database_path)
    official = repository.latest_official_release()
    assert official is not None
    base = load_scenario_snapshot(str(database_path), official.revision_id)
    revision_tables = {name: base.tables[name] for name in REVISION_TABLES if name in base.tables}
    halved = revision_tables["RQ_PKG_PLAN"].copy()
    halved["생산수량"] = pd.to_numeric(halved["생산수량"], errors="coerce") * 0.5
    revision_tables["RQ_PKG_PLAN"] = halved
    saved = repository.save_revision(
        official.scenario_id,
        revision_tables,
        base.preset,
        revision_name="계획 절반",
    )

    # 현재 활성은 공식 리비전 그대로 두고, 같은 시나리오의 새 리비전과 견준다.
    _pick_comparison(app, str(official.scenario_id), str(saved.revision.revision_id))
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    gaps = _gap_annotations(app)
    # 비교 쪽 계획이 절반이므로 현재가 더 많다 — 전부 증가여야 한다.
    assert gaps, "같은 시나리오의 다른 리비전과 견준 GAP 이 하나도 없다"
    assert all(text.startswith("+") for text in gaps), gaps


def test_switching_the_comparison_scenario_shows_its_own_revision(tmp_path: Path) -> None:
    """비교 시나리오를 바꾸면 리비전 상자도 **그 시나리오의 리비전**을 보여 준다.

    앞 시나리오의 리비전을 세션에서 지우기만 하면 서버는 새 시나리오의 첫 리비전을 쓰지만
    브라우저는 그것을 듣지 못해 앞 시나리오의 리비전 이름(`r5 · 임시 적용`)을 그대로
    보여 줬다 — GAP 이 어느 리비전과 견주는지 화면이 거짓말한다(2026-10-05 E2E).
    """
    from capa_simulation.components.home_preference import (
        COMPARISON_REVISION_KEY,
        COMPARISON_SCENARIO_KEY,
    )
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)
    official = DuckDBScenarioRepository(database_path).latest_official_release()
    assert official is not None
    comparison_id, comparison_revision_id = _create_comparison_scenario(database_path, 0.5)
    _pick_comparison(app, str(official.scenario_id), str(official.revision_id))
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    app = _open_settings(app)

    app.selectbox(key=COMPARISON_SCENARIO_KEY).set_value(comparison_id).run()

    assert not list(app.exception), [element.message for element in app.exception]
    revision = app.selectbox(key=COMPARISON_REVISION_KEY)
    assert revision.value == comparison_revision_id
    # 브라우저에 「이 값으로 그려라」를 함께 보낸다. 없으면 앞 시나리오의 리비전이 남는다.
    assert revision.proto.set_value is True


def _value_slots(app: AppTest) -> list[tuple[float, float, float]]:
    """LOB 표 세 행의 값 글자가 놓인 자리. 값 자체가 아니라 **자리**만 본다.

    선행을 켜면 값 숫자는 바뀌므로 글자로는 맞출 수 없다. 크기가 값 글자 크기인 주석의
    (x, y, yshift) 를 모으면 그 자리가 그대로인지 볼 수 있다.
    """
    figure = app.session_state["spy_figures"]["production_lob_months"]
    return sorted(
        (float(annotation.x), float(annotation.y), float(annotation.yshift or 0))
        for annotation in figure.layout.annotations
        if annotation.font.size == LOB_VALUE_FONT_SIZE_PX
    )


def test_the_value_never_moves_or_shrinks_when_gaps_are_switched_on(tmp_path: Path) -> None:
    """선행·GAP 을 어떻게 켜도 원 데이터의 크기와 자리는 그대로여야 한다.

    예전에는 증감을 끼우려고 값 글자를 0.85·0.65 배로 줄이고 반대쪽으로 밀었다. 토글 하나에
    표 전체의 숫자가 커졌다 작아졌다 해서 읽던 자리를 놓친다. 지금은 행 높이가 두 줄 자리를
    미리 비워 두므로 값은 언제나 같은 크기로 칸 한가운데에 선다.

    자리 **개수**까지 함께 본다. 값 하나라도 작아지면 그 주석이 이 묶음에서 빠진다.
    """
    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)

    before = _value_slots(app)
    assert before, "값 주석을 하나도 찾지 못했다"

    comparison_id, comparison_revision_id = _create_comparison_scenario(database_path, 0.5)
    _pick_comparison(app, comparison_id, comparison_revision_id)
    app.session_state["home_show_advance"] = True
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _gap_annotations(app), "선행·GAP 을 켰는데 증감이 하나도 없다"

    assert _value_slots(app) == before


def test_every_gap_uses_one_font_size(tmp_path: Path) -> None:
    """증감 글자는 자리마다 다르면 안 된다. 같은 뜻의 표기가 크기로 갈리면 위계로 읽힌다."""
    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)

    comparison_id, comparison_revision_id = _create_comparison_scenario(database_path, 0.5)
    _pick_comparison(app, comparison_id, comparison_revision_id)
    app.session_state["home_show_advance"] = True
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    figure = app.session_state["spy_figures"]["production_lob_months"]
    sizes = {
        int(annotation.font.size)
        for annotation in figure.layout.annotations
        if str(annotation.text).strip().startswith(("+", "-"))
    }
    assert sizes == {tokens.DELTA_FONT_SIZE_PX}, sizes


def test_the_dashboard_stays_drawn_behind_the_settings_popup(seeded_database: Path) -> None:
    """「HOME 설정」 팝업은 대시보드 위에 뜬다 — 연 회차에도 여덟 Figure 를 같은 차례로 그린다.

    전에는 Preference·Past Data 가 HOME 의 탭이라 그 탭을 보는 동안 Main 의 그림을 그리지
    않았다(숨은 탭에서 그리면 재서 자리를 잡는 글자가 어긋난다). 팝업은 본문을 가리지 않고 얹히므로
    본문은 보이는 채로 그린다.
    """
    app = _run(seeded_database)
    assert app.session_state["spy_traces"] == [0, 2, 1, 1, 16, 2, 3, 4]

    app = _open_settings(app)

    assert app.session_state["spy_traces"] == [0, 2, 1, 1, 16, 2, 3, 4]
    app = _close_settings(app)
    assert app.session_state["spy_traces"] == [0, 2, 1, 1, 16, 2, 3, 4]


def test_the_view_toggles_keep_their_values_across_the_settings_popup(
    seeded_database: Path,
) -> None:
    """팝업을 열고 닫아도 사이드바 `LOB 표시 조건` 카드의 토글 값은 그대로다 — 카드는 HOME 에서
    늘 서고(2026-11-02 — 전에는 Main 탭에서만), 팝업 안 위젯과 key 가 겹치지 않는다."""
    app = _run(seeded_database)
    app.sidebar.toggle(key="home_preference_plan_detail_customer").set_value(True).run()
    assert not list(app.exception)

    app = _open_settings(app)
    assert app.sidebar.toggle(key="home_preference_plan_detail_customer").value is True
    app = _close_settings(app)

    assert app.session_state["home_preference_plan_detail_customer"] is True
    assert app.sidebar.toggle(key="home_preference_plan_detail_customer").value is True
    app.sidebar.toggle(key="home_preference_plan_detail_customer").set_value(False).run()
    assert not list(app.exception)


def test_the_two_columns_keep_paired_children(seeded_database: Path) -> None:
    """왼쪽 라벨 칸과 오른쪽 월 칸은 자식 수·차례가 같아야 행이 맞는다.

    이 계약은 지금까지 브라우저로만 확인할 수 있었다. 한쪽에만 무언가를 끼우면 그 아래
    모든 행이 어긋나는데, 어긋난 픽셀은 눈으로 봐야 보였다. `AppTest` 가 1.63 부터 컨테이너
    key 를 내주므로 여기서 잡는다.
    """
    app = _run(seeded_database)

    label_canvas = app.get_by_key("production_lob_label_canvas")
    month_canvas = app.get_by_key("production_lob_month_canvas")
    assert [child.key for child in label_canvas.children.values()] == [
        "production_lob_labels",
        "plan_detail_title_row",
        "production_detail_labels",
        "key_process_title_row",
        "key_process_heatmap_labels",
        "bottleneck_title_row",
        "bottleneck_detail_labels",
    ]
    assert [child.key for child in month_canvas.children.values()] == [
        "production_lob_months",
        "plan_detail_title_spacer",
        "production_detail_months",
        "key_process_title_spacer",
        "key_process_heatmap_months",
        "bottleneck_title_spacer",
        "bottleneck_detail_months",
    ]


def test_the_title_spacers_keep_their_pinned_height(seeded_database: Path) -> None:
    """빈 컨테이너는 높이를 주지 않으면 Streamlit 이 아예 그리지 않는다.

    월 칸의 빈 줄이 사라지면 그 칸만 위로 올라붙어 아래 표의 행이 통째로 어긋난다.
    """
    app = _run(seeded_database)

    for key in ("plan_detail_title_spacer", "key_process_title_spacer", "bottleneck_title_spacer"):
        spacer = app.get_by_key(key)
        assert spacer.proto.height_config.pixel_height == DASHBOARD_TITLE_BAND_PX, key


def _pixel_gap(app: AppTest, key: str) -> int | None:
    """컨테이너의 px gap. 이름 gap(`small` 등)이나 gap 없음이면 None."""
    gap_config = app.get_by_key(key).proto.flex_container.gap_config
    return gap_config.pixel_gap if gap_config.HasField("pixel_gap") else None


def _css_rule(style: str, selector_tail: str) -> str:
    """`selector_tail` 로 끝나는 선택자 묶음의 선언 본문(공백을 한 칸으로)."""
    flat = " ".join(style.split())
    head = flat.index(selector_tail + " {")
    return flat[head + len(selector_tail) + 2 : flat.index("}", head)].strip()


def test_section_spacing_tokens_keep_the_title_closer_to_its_own_sheet() -> None:
    """제목→시트는 구획 사이보다 좁고, `Capa LOB 현황` 의 스크롤바가 드는 폭보다는 좁지 않다.

    2026-11-02 사용자 요청 — 「각 타이틀과 시트의 간격을 일정하게 붙이고, 각각의 영역간 간격을
    일정하게」. 제목→시트가 구획 사이보다 넓으면 제목이 위 시트의 꼬리로 읽힌다(바꾸기 전 사본 실측:
    글줄 상자 기준 제목→시트 20.2px · 구획 사이 15.8px, 세 폭 같음).
    """
    assert tokens.SECTION_TITLE_SHEET_GAP_PX < tokens.SECTION_GAP_PX
    assert 2 * tokens.SECTION_TITLE_SHEET_GAP_PX <= tokens.SECTION_GAP_PX + 4
    assert tokens.SECTION_TITLE_SHEET_GAP_PX >= tokens.SCROLLBAR_HEIGHT_PX
    assert DASHBOARD_PANEL_TITLE_GAP_PX >= 0
    assert DASHBOARD_TITLE_BAND_PX == (
        tokens.SECTION_GAP_PX + DASHBOARD_TITLE_LINE_PX + tokens.SECTION_TITLE_SHEET_GAP_PX
    )


def test_every_section_title_sits_the_same_gap_above_its_sheet(seeded_database: Path) -> None:
    """네 구획의 제목→시트와 구획 사이가 각각 한 값이다 — 위치를 정하는 모든 몫을 모아 셈한다.

    - 계획 세부수량 · 주요공정 · 상세 B/N: 두 캔버스의 gap 은 0 이고 제목 띠가 위 여백(구획 사이)과
      아래 여백(제목→시트)을 품는다. 띠 높이 = 위 + 제목 글줄 + 아래라 글줄이 남김없이 찬다.
    - `Capa LOB 현황`: 제목 줄은 글줄 높이 그대로이고, 제목→시트 = 상자 gap + 라벨 캔버스 위 여백
      (월 칸 스크롤바 높이)이다.
    """
    from capa_simulation.components.home_rendering import dashboard_title_row_style

    app = _run(seeded_database)
    assert _pixel_gap(app, "production_lob_label_canvas") == 0
    assert _pixel_gap(app, "production_lob_month_canvas") == 0
    assert _pixel_gap(app, "home_dashboard_panel") == DASHBOARD_PANEL_TITLE_GAP_PX

    style = dashboard_title_row_style()
    band = _css_rule(style, ".st-key-bottleneck_title_spacer")
    assert f"height: {DASHBOARD_TITLE_BAND_PX}px;" in band
    assert "box-sizing: border-box;" in band
    padding = _css_rule(style, ".st-key-bottleneck_title_row")
    assert padding == (
        f"padding: {tokens.SECTION_GAP_PX}px 0 {tokens.SECTION_TITLE_SHEET_GAP_PX}px;"
    )
    lob_row = _css_rule(style, ".st-key-lob_title_row")
    assert f"height: {DASHBOARD_TITLE_LINE_PX}px;" in lob_row
    # 띠 안 글줄 = 띠 - 위 - 아래 = 제목 글줄. 넷 다 같은 제목→시트다.
    assert (
        DASHBOARD_TITLE_BAND_PX - tokens.SECTION_GAP_PX - tokens.SECTION_TITLE_SHEET_GAP_PX
        == DASHBOARD_TITLE_LINE_PX
    )
    assert (
        DASHBOARD_PANEL_TITLE_GAP_PX + tokens.SCROLLBAR_HEIGHT_PX
        == tokens.SECTION_TITLE_SHEET_GAP_PX
    )


def test_section_titles_drop_the_paragraph_line_box_under_the_title() -> None:
    """제목 글줄 상자가 줄 높이와 꼭 같아야 위 · 아래 틈이 띠 여백 그대로다.

    마크다운은 제목 HTML 을 문단으로 감싸고, 본문 글줄(14px · 22.4px)의 기준선에 제목이 얹혀 문단이
    28.4px 가 된다 — 제목 글이 문단 위쪽에 붙어 아래가 4.4px 더 빈다(바꾸기 전 사본 실측: 36px 줄
    안에서 글 위 3.8px · 아래 8.2px). 문단을 flex 로, 문단 아래 여백과 칸의 음수 여백을 0 으로 둔다.
    """
    from capa_simulation.components.home_preference import section_title_markup
    from capa_simulation.components.home_rendering import dashboard_title_row_style

    style = dashboard_title_row_style()
    rows = ("lob", "plan_detail", "key_process", "bottleneck")
    container = '[data-testid="stMarkdownContainer"]'
    flat = " ".join(style.split())
    # 네 제목 줄이 한 선택자 묶음으로 같은 선언을 받는다.
    assert ", ".join(f".st-key-{row}_title_row {container}" for row in rows) + " {" in flat
    assert ", ".join(f".st-key-{row}_title_row {container} > p" for row in rows) + " {" in flat
    assert _css_rule(style, f".st-key-bottleneck_title_row {container}") == "margin-bottom: 0;"
    assert _css_rule(style, f".st-key-bottleneck_title_row {container} > p") == (
        "display: flex; align-items: center; margin: 0;"
    )
    assert f"line-height:{DASHBOARD_TITLE_LINE_PX}px" in section_title_markup("계획 세부수량")


def _lob_title_row_with_unapplied_month() -> None:
    import streamlit as st

    from capa_simulation.components.home_preference import render_lob_title_row
    from capa_simulation.components.state_alerts import AlertScope

    months = st.session_state.get("unapplied", [202607])
    render_lob_title_row(
        unapplied_months=months,
        scope=AlertScope({"token": "t1", "period": [202601, 202612]}, "DEMO · r1 · 26.01–26.12"),
    )


def test_the_unapplied_month_notice_is_a_state_alert_not_a_box() -> None:
    """선행 B/O 를 적용하지 못한 달은 제목 줄 밑에 상자를 세우지 않고 상태 알림(`HM-04`)으로 낸다 —
    달이 바뀔 때만 알림창에 뜨고 Alarm 에 남는다(2026-11-03 결정 보드 D2 (나)). 달이 없어진 회차는
    「없음」 표지(해소)다."""
    app = AppTest.from_function(_lob_title_row_with_unapplied_month).run()
    assert not list(app.exception)
    assert not app.warning
    (note,) = [note for note in alert_notes(app) if note.get("code") == "HM-04"]
    assert note["active"] is True and note["level"] == "check"
    assert "26.07" in note["short"] and "적용하지 못한 달" in note["full"]
    assert note["scope_label"] == "DEMO · r1 · 26.01–26.12"

    app.session_state["unapplied"] = []
    app.run()
    (quiet,) = [note for note in alert_notes(app) if note.get("code") == "HM-04"]
    assert quiet["active"] is False and quiet["scope"] == note["scope"]


def test_the_lob_panel_border_closes_on_the_bottom_edge(seeded_database: Path) -> None:
    """아래 테두리는 그림의 맨 아랫줄에 놓여야 한다.

    paper 좌표를 비율로 적어 두면 행 높이를 한 번 올릴 때마다 그림 영역이 함께 커져
    같은 비율이 캔버스 밖으로 밀린다. 그러면 Plotly 는 선을 그리기는 하지만 잘려 나가
    **화면에서는 아래 테두리가 통째로 사라진다.** 오류도 경고도 없다.
    """
    app = _run(seeded_database)
    figure = app.session_state["spy_figures"]["production_lob_labels"]

    plot_area = figure.layout.height - LOB_TOP_MARGIN_PX - LOB_BOTTOM_MARGIN_PX
    horizontals = [
        shape for shape in figure.layout.shapes if shape.type == "line" and shape.y0 == shape.y1
    ]
    assert horizontals, "가로선이 하나도 없다"
    # 패널 맨 아랫줄에는 테두리와 구획 격자선이 함께 놓인다. 굵은 쪽이 테두리다.
    # 아래 여백이 있으면 그 여백까지 감싸야 해 음수이고, 도넛 행이 그림 영역 맨 아래에 붙은
    # 지금은 여백이 0 이라 0 이다. 어느 쪽이든 아래 식이 그림 높이와 같아야 한다.
    bottom_y = min(shape.y0 for shape in horizontals)
    assert bottom_y <= 0, "아래 테두리가 그림 영역 안에 머물러 맨 아랫줄에 닿지 못한다"

    bottom_px = LOB_TOP_MARGIN_PX + plot_area * (1 - bottom_y)
    assert bottom_px == pytest.approx(figure.layout.height)

    def _widest(target_y: float) -> float:
        return float(max(shape.line.width for shape in horizontals if shape.y0 == target_y))

    # 맨 끝줄의 획은 절반이 잘린다. 위 테두리와 같은 굵기로 그려야 보이는 두께가 같다.
    assert _widest(bottom_y) == _widest(1)


def test_the_chart_rows_share_the_table_rows_label_color(seeded_database: Path) -> None:
    """`생산계획 LOB`·`B/N Top 5` 도 `Density (억Gb)` 와 같은 구분 칸의 행 이름이다.

    한쪽만 흐리면 같은 칸에 나란히 선 이름들이 서로 다른 위계로 읽힌다.
    """
    app = _run(seeded_database)
    figure = app.session_state["spy_figures"]["production_lob_labels"]

    colors = {annotation.text: annotation.font.color for annotation in figure.layout.annotations}
    row_names = [
        "<b>Density (억Gb)</b>",
        "<b>Wafer 계획</b>",
        "<b>Wafer Capa</b>",
        "<b>생산계획 LOB</b>",
        "<b>B/N Top 5</b>",
    ]
    missing = [name for name in row_names if name not in colors]
    assert not missing, missing
    assert {colors[name] for name in row_names} == {tokens.TEXT}
    # `제품별 비중` 은 이름 뒤에 단위를 흐린 글자로 붙인다. 이름 자체는 같은 본문색이다.
    share_title = next(text for text in colors if text.startswith("<b>제품별 비중</b>"))
    assert colors[share_title] == tokens.TEXT


def test_the_product_share_row_follows_the_unit_picked_in_the_sidebar(
    seeded_database: Path,
) -> None:
    """단위는 사이드바 `LOB 표시 조건` 카드에서 고른다. 기본은 Wafer 다.

    Wafer 도넛의 분모는 같은 표의 `Wafer 계획` 이다 — 칸마다 hover 에 적은 분모가 그 행의
    값과 같다. 단위를 바꾸면 Figure 캐시 키가 갈려 새 그림이 선다.
    """
    app = _run(seeded_database)
    picker = app.segmented_control(key=PRODUCT_SHARE_BASIS_KEY)
    assert picker.label == "제품별 비중 단위"
    assert picker.value == "Wafer"
    assert list(picker.options) == ["Wafer", "PKG"]

    months = app.session_state["spy_figures"]["production_lob_months"]
    pies = [trace for trace in months.data if trace.type == "pie"]
    assert pies, "도넛이 하나도 없다"
    for pie in pies:
        assert sum(pie.values) > 0
        assert all("Wafer " in text for text in pie.hovertext)
    labels = app.session_state["spy_figures"]["production_lob_labels"]
    assert any(
        "제품별 비중" in str(item.text) and ">Wafer<" in str(item.text)
        for item in labels.layout.annotations
    )

    picker.set_value("PKG").run()
    assert not app.exception, [item.message for item in app.exception]

    labels = app.session_state["spy_figures"]["production_lob_labels"]
    assert any(
        "제품별 비중" in str(item.text) and ">PKG<" in str(item.text)
        for item in labels.layout.annotations
    )
    months = app.session_state["spy_figures"]["production_lob_months"]
    pies = [trace for trace in months.data if trace.type == "pie"]
    assert pies and all("PKG " in text for pie in pies for text in pie.hovertext)


def test_both_detail_columns_center_when_the_gap_toggle_is_off(seeded_database: Path) -> None:
    """GAP 이 꺼져 있으면 분류 칸과 월 칸의 글자가 같은 눈높이(행 한가운데)에 선다.

    칸 글자는 표 칸이 아니라 숨긴 축 위 글자 trace(`data[1]`, y 는 그림 위에서 잰 px)가 그린다.
    한쪽만 다른 자리에 서면 같은 행의 두 칸이 어긋나 보이고, 두 그림의 행이 다르면 표 전체가
    틀어진다.
    """
    app = _run(seeded_database)
    assert not app.session_state["home_show_comparison"], "이 테스트는 GAP 이 꺼진 상태다"
    label_figure = app.session_state["spy_figures"]["production_detail_labels"]
    month_figure = app.session_state["spy_figures"]["production_detail_months"]
    header = table_row_height(DETAIL_HEADER_FONT_SIZE_PX)
    row = lower_delta_row_height(DETAIL_VALUE_FONT_SIZE_PX)

    for name, figure in (("분류", label_figure), ("월", month_figure)):
        values = figure.data[1]
        assert list(values.text), f"{name} 칸이 비어 있다"
        assert all(text and "<" not in text for text in values.text), name
        offsets = {round((y - header) % row, 6) for y in values.y}
        assert offsets == {round(table_text_y(0, DETAIL_VALUE_FONT_SIZE_PX, markup=True), 6)}, name

    assert label_figure.layout.height == month_figure.layout.height


# `Past Data 포함` 토글. 켜면 과거 구간이 월 축에 붙고, 끄면 활성 시나리오의 계산 구간만
# 남는다. 값 자체는 지워지지 않으므로 다시 켜면 그대로 돌아온다.


def _seed_past_months(
    database_path: Path,
    months: list[int],
    *,
    securement: list[tuple[int, str, float]] | None = None,
) -> None:
    """공용 과거 프로필에 월별 실적을 넣는다. 세 표는 한 버전을 공유하므로 함께 준다.

    `securement` 는 과거 확보율 행 `(년월, 공정, 확보율)` 이다. 주지 않으면 확보율 표는 비운다.
    """
    import pandas as pd

    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.services.past_data import (
        PAST_DETAIL_COLUMNS,
        PAST_SECUREMENT_COLUMNS,
        empty_past_table,
    )

    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_past_data(
        {
            "월별": pd.DataFrame(
                {
                    "생산계획년월": months,
                    "Density": [9.0 + index for index in range(len(months))],
                    "Wafer Total": [120_000.0 + index for index in range(len(months))],
                }
            ),
            "계획": empty_past_table(PAST_DETAIL_COLUMNS),
            "확보율": (
                pd.DataFrame(securement, columns=list(PAST_SECUREMENT_COLUMNS))
                if securement
                else empty_past_table(PAST_SECUREMENT_COLUMNS)
            ),
        },
        source="test",
    )


def _lob_month_labels(app: AppTest) -> list[str]:
    """LOB 월 Figure 의 x 축 눈금 글자. 월 축에 무엇이 실렸는지가 여기 그대로 나온다."""
    figure = app.session_state["spy_figures"]["production_lob_months"]
    return [str(text) for text in figure.layout.xaxis.ticktext]


def test_past_months_join_the_month_axis_while_the_toggle_is_on(tmp_path: Path) -> None:
    """기본은 켬이다. 넣어 둔 과거 구간이 조회 범위 안이면 월 축에 그대로 붙는다."""
    database_path = tmp_path / "scenario.duckdb"
    # 과거 프로필은 `st.cache_data` 경계 뒤에 있다. 앱을 한 번 돌린 뒤 심으면 첫 렌더가
    # 캐시한 빈 값이 그대로 다시 나온다. 그래서 돌리기 **전에** 심는다.
    _seed_past_months(database_path, [202512, 202511])
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception), [element.message for element in app.exception]
    # 첫 렌더는 공식 시나리오 프리셋이 조회기간을 덮는다. 범위는 그 뒤에 넣어야 남는다.
    app.session_state["production_month_range_v2"] = ("2025-11", "2026-12")
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state["home_preference_include_past"] is True
    labels = _lob_month_labels(app)
    assert "25.11" in labels and "25.12" in labels, labels


def test_turning_the_toggle_off_leaves_only_the_scenario_months(tmp_path: Path) -> None:
    """끄면 과거가 화면에서 빠진다. DB 시나리오의 계산 구간만으로 화면이 구성돼야 한다."""
    database_path = tmp_path / "scenario.duckdb"
    _seed_past_months(database_path, [202512, 202511])
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception), [element.message for element in app.exception]
    app.session_state["production_month_range_v2"] = ("2025-11", "2026-12")
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert "25.11" in _lob_month_labels(app)

    app.session_state["home_preference_include_past"] = False
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    labels = _lob_month_labels(app)
    assert "25.11" not in labels and "25.12" not in labels, labels
    # 값을 지운 것이 아니라 화면에서만 뺀 것이다. 다시 켜면 그대로 돌아온다.
    app.session_state["home_preference_include_past"] = True
    app.run()
    assert "25.11" in _lob_month_labels(app)


def _key_process_cell(app: AppTest, label: str) -> list[Any]:
    """주요공정 월 Figure 에서 한 달 칸의 hover `customdata`.

    차례는 `KEY_PROCESS_HOVER_TEMPLATE` 그대로다 — [년월, 공정, 확보율, 가용, 필요, 보정 줄, …].
    """
    figure = app.session_state["spy_figures"]["key_process_heatmap_months"]
    cells = [
        list(row)
        for trace in figure.data
        if trace.customdata is not None
        for row in trace.customdata
        if row[0] == label
    ]
    assert len(cells) == 1, cells
    return cells[0]


def test_a_past_month_takes_the_securement_adjustment_like_a_calculated_month(
    tmp_path: Path,
) -> None:
    """과거 구간 달도 확보율 보정을 받는다 — HOME 은 과거 확보율 행을 합친 **뒤**에 보정을 얹는다.

    Preference 입력 표의 년월에도 과거 달이 든다. 보정을 계산 구간 달에만 걸면 과거 달에 넣은
    보정이 조용히 빠지거나 「짝이 없어 반영되지 않은 행」 으로 알려져, 저장된 공용 보정의 뜻이
    바뀐다(AGENTS 6장 「HOME 얹기」). 그래서 화면까지 통과한 칸 값과 안내로 본다.
    """
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    database_path = tmp_path / "scenario.duckdb"
    # 과거·보정·프리셋 프로필은 모두 `st.cache_data` 경계 뒤에 있어 앱을 돌리기 **전에** 심는다.
    _seed_past_months(database_path, [202512], securement=[(202512, "DEMO_Chip_Attach", 1.10)])
    repository = DuckDBScenarioRepository(database_path)
    repository.replace_global_execution_capacity(
        pd.DataFrame(
            {
                "생산계획년월": [202512],
                "공정": ["DEMO_Chip_Attach"],
                "증감 확보율": [-20.0],
                "비고": ["과거 실적 보정"],
            }
        ),
        source="테스트",
    )
    repository.replace_global_key_process_presets(
        [("A 그룹", ["DEMO_Chip_Attach"])], source="테스트"
    )
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception), [element.message for element in app.exception]
    app.session_state["production_month_range_v2"] = ("2025-12", "2026-12")
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    # 보정을 끈 화면은 넣은 과거 확보율 그대로다.
    assert app.session_state["home_show_execution"] is False
    assert _key_process_cell(app, "25.12")[2] == "110.0%"

    app.session_state["home_show_execution"] = True
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    cell = _key_process_cell(app, "25.12")
    assert cell[2] == "90.0%"
    # 「%p」 가 아니라 「%」 다(2026-11-01 사용자 결정 「%p표기하지말고 %로만」).
    assert "확보율 보정 -20.0%<br>비고 과거 실적 보정" in str(cell[5])
    assert not [item.value for item in app.warning if "짝이 없어" in str(item.value)]


def test_home_offers_the_lob_howto_board_through_its_guide_button(seeded_database: Path) -> None:
    """HOME 의 Guide 는 따라하기 가이드 `lob` 를 고르는 차례(사내판 → 예시판 → md)대로 연다.

    어느 판이 서는지는 그 자리의 파일이 정한다(사내에는 사내판이 있을 수 있다) — 같은 고르기
    함수의 결과가 툴바 버튼 규칙에 실렸는지만 본다.
    """
    from capa_simulation.components.page_guide import find_howto_guide, guide_show_style

    app = _run(seeded_database)
    styles = [
        element.proto.body
        for element in app.get("html")
        if "#capa-guide-button" in element.proto.body
    ]

    assert styles == [guide_show_style(find_howto_guide("lob"))]


def test_the_home_guide_carries_what_left_the_body() -> None:
    """토글 툴팁·Preference·Past Data 의 설명은 Guide 로 옮겼다."""
    from capa_simulation.components.page_guide import load_guide

    guide = load_guide("home")
    for text in (
        "LOB 표시 조건",
        "반비례",
        # 확보율 보정은 더하기다 — 단위 글자는 「%」(2026-11-01 사용자 결정).
        "비율 곱셈이 아닙니다",
        "EDP-TSV",
        "거래선",
        "계산이 이깁니다",
        "한 버전",
        "고른 차례가 곧 행 순서",
        "hover 의 Capa 숫자는 자르지 않은 실제 값",
        "비우고 저장하면 공지가 내려갑니다",
        "유효한 월 중 최저 확보율",
        # 년월 셀을 병합한 Past Data 는 막힌다(2026-09-29 리뷰).
        "병합을 풀고",
    ):
        assert text in guide, text
    assert "년월이 **빈** 행만 읽지 않고 넘어갑니다" not in guide


def test_past_data_paste_opens_inside_its_table_box_in_the_settings_popup(
    seeded_database: Path,
) -> None:
    """붙여넣기 칸은 그 표 상자 안에 펴진다 — Past Data 는 이미 「HOME 설정」 팝업 안이라 팝업을 또
    열 수 없다(Streamlit 은 팝업 안 팝업을 막는다). 「닫기」 로 걷고, 팝업은 그대로 열려 있다."""
    app = _open_settings(_run(seeded_database))
    assert not [area for area in app.text_area if area.label.endswith("붙여넣기")]

    app.button(key="home_past_clipboard_월별_open").click().run()
    assert not app.exception
    assert [area.label for area in app.text_area if area.label.endswith("붙여넣기")] == [
        "월별 Density · Wafer Total 붙여넣기"
    ]
    assert app.session_state[HOME_DIALOG_KEY] == "settings"

    app.button(key="home_past_clipboard_월별_close").click().run()
    assert not app.exception
    assert not [area for area in app.text_area if area.label.endswith("붙여넣기")]
    assert app.session_state[HOME_DIALOG_KEY] == "settings"


def _sidebar_keys(app: AppTest) -> list[str]:
    """사이드바 **최상위** 칸의 key — key 를 준 컨테이너는 id 끝이 그 key 다."""
    keys: list[str] = []
    for node in app.sidebar.children.values():
        identifier = str(getattr(getattr(node, "proto", None), "id", "") or "")
        keys.append(identifier.rsplit("-", 1)[-1] if identifier else "")
    return keys


def _settings_tab_dot(app: AppTest) -> bool:
    """팝업 안 `Past Data` 탭 이름 옆 점(스타일만 든 `st.html` — 다섯째(끝) 탭 단추의 `::after`)."""
    selector = '.st-key-home_settings_tab [data-testid="stTab"]:nth-child(5)'
    return any(selector in str(element.proto.body) for element in app.get("html"))


def test_a_past_data_paste_waiting_to_be_saved_marks_the_settings_box_and_its_tab(
    tmp_path: Path,
) -> None:
    """읽어 두고 저장하지 않은 과거 구간이 있으면 사이드바 「HOME 설정」 상자 왼쪽에 주황 띠(key 끝
    `_pending`)가, 팝업 안 `Past Data` 탭 이름 옆에 점이 찍힌다. 팝업을 닫아도 남는다(대기는 세션
    칸이다). 저장하면 둘 다 사라진다.

    다른 화면의 미적용 점과 같은 규칙이다. 전에는 「대기 N행」이 남아도 점이 없었다(2026-10-01
    브라우저 점검). 2026-11-02 부터 Past Data 가 HOME 탭이 아니라 「HOME 설정」 팝업 안이라 점은
    팝업을 여는 상자에도 선다.
    """
    app = AppTest.from_string(_home_script(tmp_path / "scenario.duckdb"), default_timeout=300)
    app.run()
    assert not app.exception
    assert "sidebar_dialog_box_home_settings" in _sidebar_keys(app)
    assert not _settings_tab_dot(app)

    app = _open_settings(app)
    app.button(key="home_past_clipboard_확보율_open").click().run()
    app.text_area(key="home_past_clipboard_확보율").set_value(
        "생산계획년월\t공정\t확보율\n202511\tDEMO_P\t1.05\n"
    )
    next(button for button in app.button if button.label == "붙여넣기 읽기").click()
    app.run()
    assert not app.exception
    assert app.session_state[HOME_DIALOG_KEY] == "settings"
    assert "sidebar_dialog_box_home_settings_pending" in _sidebar_keys(app)
    assert _settings_tab_dot(app)
    assert "저장하지 않은 Past Data" in str(app.button(key=SETTINGS_BUTTON_KEY).help)

    app = _close_settings(app)
    assert "sidebar_dialog_box_home_settings_pending" in _sidebar_keys(app)

    app = _open_settings(app)
    next(button for button in app.button if button.label == "과거 구간 저장").click()
    app.run()
    assert not app.exception
    assert app.session_state[HOME_DIALOG_KEY] == "settings"
    assert "sidebar_dialog_box_home_settings" in _sidebar_keys(app)
    assert "sidebar_dialog_box_home_settings_pending" not in _sidebar_keys(app)
    assert not _settings_tab_dot(app)


def test_the_sidebar_picks_a_key_process_preset_and_the_heatmap_follows(tmp_path: Path) -> None:
    """주요공정 히트맵은 사이드바 `주요공정 히트맵` 줄에서 고른 프리셋의 공정을 그린다.

    2026-09-29 사용자 요청 — 「A 그룹은 A·B·C·D, B 그룹은 D·E·F·G」를 공용 프로필에 저장해 두고
    공정 필터와 따로 골라 본다. 고르지 않은 세션은 첫 프리셋(기본)이다. 줄은 팝업 칸이고(2026-10-10)
    팝업의 라디오는 프리셋마다 그 공정을 미리 보여 준다. 제목에 프리셋 이름이 붙는다.
    """
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    database_path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    # 프로필은 `st.cache_data` 경계 뒤에 있어 앱을 돌리기 **전에** 심는다.
    repository.replace_global_key_process_presets(
        [("A 그룹", ["DEMO_Chip_Attach"]), ("B 그룹", ["DEMO_Final_Test", "DEMO_Wafer_Inspect"])],
        source="테스트",
    )
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception), [element.message for element in app.exception]

    assert app.button(key="home_key_process_field").label == "A 그룹 · 1공정"
    assert app.session_state["home_key_process_preset"] == "A 그룹"
    assert any('title="주요공정 - A 그룹"' in item.value for item in app.markdown)
    labels = app.session_state["spy_figures"]["key_process_heatmap_labels"]
    assert "DEMO_Chip_Attach" in json.dumps(labels.to_plotly_json(), ensure_ascii=False)

    # 칸을 누른 회차에 팝업이 선다 — 라디오는 지금 보는 프리셋에서 시작하고 캡션이 공정을 보인다.
    app.button(key="home_key_process_field").click().run()
    assert not list(app.exception), [element.message for element in app.exception]
    picker = app.radio(key="home_key_process_preset_pick")
    assert picker.options == ["A 그룹", "B 그룹"]
    assert picker.value == "A 그룹"
    # 캡션은 마크다운이라 공정 이름을 막아 싣는다(보이는 글자는 「1공정 · DEMO_Chip_Attach」).
    assert list(picker.proto.captions) == [
        f"1공정 · {literal_markdown('DEMO_Chip_Attach')}",
        f"2공정 · {literal_markdown('DEMO_Final_Test')} · {literal_markdown('DEMO_Wafer_Inspect')}",
    ]

    # 팝업이 고른 값을 적는 칸(위젯이 아닌 세션 값)을 바꾸면 히트맵이 따라간다. 팝업 본문의 적용은
    # 아래 테스트가 본다 — 팝업은 열림 칸으로 서므로 닫은 뒤에 바꾼다.
    _dismiss_home_dialog(app)
    app.session_state["home_key_process_preset"] = "B 그룹"
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert app.button(key="home_key_process_field").label == "B 그룹 · 2공정"
    assert any('title="주요공정 - B 그룹"' in item.value for item in app.markdown)
    labels = app.session_state["spy_figures"]["key_process_heatmap_labels"]
    text = json.dumps(labels.to_plotly_json(), ensure_ascii=False)
    assert "DEMO_Final_Test" in text and "DEMO_Wafer_Inspect" in text
    assert "DEMO_Chip_Attach" not in text


def test_picking_a_preset_in_the_dialog_applies_it_once() -> None:
    """팝업에서 고르면 곧바로 적용하고 앱을 다시 돌린다 — 다시 도는 회차에는 되풀이하지 않는다.

    라디오 조작은 팝업만 다시 돌린다. 그래서 본문이 돌려받은 값을 **세션의 지금 값**과 견준다 —
    적은 뒤에는 같아져 멈춘다.
    """

    def script() -> None:
        import streamlit as st

        from capa_simulation.components.home_preference import render_key_process_dialog_body

        st.session_state["test_body_runs"] = int(st.session_state.get("test_body_runs", 0)) + 1
        render_key_process_dialog_body(["A 그룹", "B 그룹"], ["1공정 · a", "2공정 · b · c"])

    from capa_simulation.components.home_preference import (
        KEY_PROCESS_PICK_KEY,
        KEY_PROCESS_PRESET_KEY,
    )

    app = AppTest.from_function(script)
    app.session_state[KEY_PROCESS_PRESET_KEY] = "A 그룹"
    app.session_state[KEY_PROCESS_PICK_KEY] = "A 그룹"
    app.run()
    assert not app.exception
    assert app.session_state["test_body_runs"] == 1
    # 머리 설명 글은 없다(2026-11-04 검수 의견 home-21) — 라디오와 프리셋 미리보기뿐이다.
    assert [item.value for item in app.caption] == []

    app.radio(key=KEY_PROCESS_PICK_KEY).set_value("B 그룹").run()
    assert not app.exception
    assert app.session_state[KEY_PROCESS_PRESET_KEY] == "B 그룹"
    # 적은 회차 + 다시 돈 회차. 다시 돈 회차는 같은 값이라 멈춘다.
    assert app.session_state["test_body_runs"] == 3


def _stale_key_process_dialog_script(database: Path, meanwhile: list[tuple[str, list[str]]]) -> str:
    """HOME 이 프리셋을 읽어 칸을 그린 뒤, 그 사이 다른 세션이 묶음을 바꾸고, 그다음 팝업이 열린다.

    여는 회차는 HOME 팝업 호스트만 돈다 — 칸이 돌려준 팝업 함수가 받은 인자는 직전 앱 전체 회차의
    것이다. 그 흐름을 한 회차 안에서 흉내 낸다(다른 세션의 쓰기는 첫 회차에만).
    """
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.settings as settings
from capa_simulation.components.home_preference import render_key_process_field
from capa_simulation.persistence.cache import (
    clear_global_key_process_cache,
    load_global_key_process,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository

database = {str(database)!r}
# 팝업 본문이 읽는 공정 표시명(`get_process_labels`)도 이 DB 다.
settings.DUCKDB_PATH = Path(database)
body = render_key_process_field(
    load_global_key_process(database),
    process_options=["DEMO_Chip_Attach", "DEMO_Final_Test", "DEMO_Wafer_Inspect"],
    database_path=database,
)
if not st.session_state.get("test_other_session_saved"):
    st.session_state["test_other_session_saved"] = True
    DuckDBScenarioRepository(Path(database)).replace_global_key_process_presets(
        {meanwhile!r}, source="다른 세션"
    )
    clear_global_key_process_cache()
if body is not None:
    body()
"""


def _key_process_database(tmp_path: Path) -> Path:
    from capa_simulation.persistence.cache import (
        clear_global_key_process_cache,
        clear_scenario_repository,
    )
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    database = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    repository.replace_global_key_process_presets(
        [("A 그룹", ["DEMO_Chip_Attach"]), ("B 그룹", ["DEMO_Final_Test"])], source="시험"
    )
    clear_scenario_repository()
    clear_global_key_process_cache()
    return database


def test_the_preset_dialog_lists_presets_saved_after_home_last_ran(tmp_path: Path) -> None:
    """주요공정 히트맵 팝업은 열 때 공용 프리셋을 다시 읽는다(`dialog_host` 「쓰는 쪽이 지키는
    것」 1).

    여는 회차가 호스트만 돌아, 칸을 그린 회차의 목록을 실으면 남이 이름을 바꾼 프리셋이 옛 이름으로
    남았다 — 그것을 고르면 다음 앱 전체 회차가 그 이름을 찾지 못해 알림 없이 기본 프리셋이
    됐다(2026-11-08 검토, 슬롯 사본 재현). 남이 새로 만든 프리셋도 앱 전체 회차 전에는 없었다.
    """
    from capa_simulation.components.home_preference import KEY_PROCESS_PICK_KEY

    database = _key_process_database(tmp_path)
    meanwhile = [
        ("A 그룹", ["DEMO_Chip_Attach"]),
        ("B 그룹 새 이름", ["DEMO_Final_Test", "DEMO_Wafer_Inspect"]),
        ("C 그룹", ["DEMO_Wafer_Inspect"]),
    ]
    app = AppTest.from_string(
        _stale_key_process_dialog_script(database, meanwhile), default_timeout=60
    ).run()

    assert not app.exception, [item.message for item in app.exception]
    # 칸은 HOME 이 읽은 회차의 것이다(다음 앱 전체 회차에 바뀐다).
    assert app.button(key="home_key_process_field").label == "A 그룹 · 1공정"
    picker = app.radio(key=KEY_PROCESS_PICK_KEY)
    assert picker.options == ["A 그룹", "B 그룹 새 이름", "C 그룹"]
    # 미리보기도 새 묶음의 공정이다(캡션은 마크다운이라 공정명을 막아 적는다).
    shown = " · ".join(literal_markdown(name) for name in ("DEMO_Final_Test", "DEMO_Wafer_Inspect"))
    assert list(picker.proto.captions)[1] == f"2공정 · {shown}"


def test_the_preset_dialog_closes_when_every_preset_was_deleted_meanwhile(tmp_path: Path) -> None:
    """팝업을 여는 사이 프리셋이 모두 지워졌으면 고를 것이 없다 — 팝업을 닫고 앱 전체를 다시 돌려
    칸이 「프리셋 없음」 으로 잠긴다(빈 라디오 팝업을 세우지 않는다)."""
    database = _key_process_database(tmp_path)
    app = AppTest.from_string(
        _stale_key_process_dialog_script(database, []), default_timeout=60
    ).run()

    assert not app.exception, [item.message for item in app.exception]
    assert not list(app.radio)
    field = app.button(key="home_key_process_field")
    assert field.disabled
    assert field.label == "프리셋 없음"


def _save_preset(app: AppTest, name: str, processes: list[str]) -> None:
    next(widget for widget in app.text_input if widget.label == "프리셋 이름").set_value(name)
    next(widget for widget in app.multiselect if widget.label == "공정").set_value(processes)
    next(button for button in app.button if button.label == "프리셋 저장").click().run()
    assert not list(app.exception), [element.message for element in app.exception]


def test_presets_are_made_renamed_promoted_and_deleted_from_preference(tmp_path: Path) -> None:
    """「HOME 설정」 팝업 Preference 의 「주요공정 히트맵 프리셋」 — 만들기·이름
    바꾸기·기본으로·삭제.

    저장은 늘 묶음 전체의 교체이고, 맨 앞 프리셋이 새 세션의 기본이다. 이름을 바꾸면 사이드바에서
    그 프리셋을 보고 있던 선택도 새 이름으로 옮긴다. 저장 뒤에도 팝업은 열려 있다.
    """
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)
    app = _open_settings(app)
    repository = DuckDBScenarioRepository(database_path)
    target = "home_key_process_preset_edit"
    assert app.selectbox(key=target).value == "＋ 새 프리셋"

    _save_preset(app, "A 그룹", ["DEMO_Chip_Attach"])
    assert repository.load_global_key_process().presets == (("A 그룹", ("DEMO_Chip_Attach",)),)
    assert app.selectbox(key=target).value == "A 그룹"
    assert app.session_state["home_key_process_preset"] == "A 그룹"

    app.selectbox(key=target).set_value("＋ 새 프리셋").run()
    _save_preset(app, "B 그룹", ["DEMO_Final_Test"])
    assert repository.load_global_key_process().preset_names == ("A 그룹", "B 그룹")

    # 사이드바에서 A 를 보는 중에 A 의 이름을 바꾸면 사이드바 선택도 따라간다.
    app.selectbox(key=target).set_value("A 그룹").run()
    _save_preset(app, "A 그룹(개정)", ["DEMO_Chip_Attach", "DEMO_Wafer_Inspect"])
    assert repository.load_global_key_process().presets[0] == (
        "A 그룹(개정)",
        ("DEMO_Chip_Attach", "DEMO_Wafer_Inspect"),
    )
    assert app.session_state["home_key_process_preset"] == "A 그룹(개정)"

    # B 를 기본으로 올린다.
    app.selectbox(key=target).set_value("B 그룹").run()
    labels_before = set(app.selectbox(key=target).options)
    assert app.button(key="home_key_process_preset_default").help == PRESET_DEFAULT_HELP
    app.button(key="home_key_process_preset_default").click().run()
    assert repository.load_global_key_process().preset_names == ("B 그룹", "A 그룹(개정)")
    # 맨 앞이 된 프리셋의 「기본으로」 는 잠기고 풍선이 뜻이 아니라 잠긴 까닭을 말한다(UI-INP-07).
    assert app.button(key="home_key_process_preset_default").disabled
    assert app.button(key="home_key_process_preset_default").help == PRESET_DEFAULT_LOCKED_HELP
    # 선택지 라벨은 기본이 바뀌어도 같다 — 라벨이 바뀌면 브라우저가 옛 라벨을 되보낸다. 무엇이
    # 기본인지는 캡션이 말한다.
    assert set(app.selectbox(key=target).options) == labels_before
    assert not [label for label in labels_before if "기본" in label]
    assert any("「B 그룹」" in caption.value and "기본" in caption.value for caption in app.caption)

    # 삭제는 확인을 체크해야 열린다. 잠긴 동안만 까닭 풍선이 있다.
    assert app.button(key="home_key_process_preset_delete").disabled
    assert app.button(key="home_key_process_preset_delete").help == PRESET_DELETE_LOCKED_HELP
    next(box for box in app.checkbox if box.label == "「B 그룹」 삭제 확인").check().run()
    assert not app.button(key="home_key_process_preset_delete").help
    app.button(key="home_key_process_preset_delete").click().run()
    assert not list(app.exception)
    assert repository.load_global_key_process().preset_names == ("A 그룹(개정)",)
    assert app.session_state[HOME_DIALOG_KEY] == "settings"


def test_a_preset_with_a_duplicate_name_is_refused(tmp_path: Path) -> None:
    database_path = tmp_path / "scenario.duckdb"
    app = _open_settings(
        AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    )
    _save_preset(app, "A 그룹", ["DEMO_Chip_Attach"])
    app.selectbox(key="home_key_process_preset_edit").set_value("＋ 새 프리셋").run()
    _save_preset(app, "A 그룹", ["DEMO_Final_Test"])

    assert any("같은 이름의 프리셋" in item.value for item in app.error)


def test_a_preset_name_with_markdown_marks_reads_literally_everywhere(tmp_path: Path) -> None:
    """프리셋 이름 「P~1~2 *k*」 의 물결표·별표가 사이드바 `주요공정 히트맵` 칸·팝업 라디오·같은
    이름 거부 오류에서 마크다운(지움선·기울임)으로 그려졌다(2026-10-26 E2E — 칸이
    `P<del>1</del>2 <em>k</em> · 1공정`). 세 자리 모두 글자 그대로 싣는다."""
    name = "P~1~2 *k*"
    app, _ = _preset_app(tmp_path, [(name, ["DEMO_Chip_Attach"])])

    assert app.button(key="home_key_process_field").label == f"{literal_markdown(name)} · 1공정"
    app.button(key="home_key_process_field").click().run()
    assert not list(app.exception), [element.message for element in app.exception]
    picker = app.radio(key="home_key_process_preset_pick")
    assert picker.options == [literal_markdown(name)]
    assert picker.value == name
    # 히트맵 칸의 팝업은 「HOME 설정」 과 같은 열림 칸을 쓴다 — 한 실행에 팝업 하나.
    assert app.session_state[HOME_DIALOG_KEY] == HOME_KEY_PROCESS_DIALOG

    app = _open_settings(app)
    app.selectbox(key="home_key_process_preset_edit").set_value("＋ 새 프리셋").run()
    _save_preset(app, name, ["DEMO_Final_Test"])

    errors = [str(item.value) for item in app.error]
    assert f"같은 이름의 프리셋이 이미 있습니다: {quoted(name)}" in errors, errors


def _preset_app(
    tmp_path: Path, presets: list[tuple[str, list[str]]], *, settings: bool = False
) -> tuple[AppTest, Any]:
    """프리셋을 심은 DB 로 HOME 을 돌린다. `settings` 면 「HOME 설정」 팝업까지 연다(편집기)."""
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    database_path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_key_process_presets(presets, source="테스트")
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception), [element.message for element in app.exception]
    return (_open_settings(app) if settings else app), repository


def test_saving_a_preset_keeps_processes_this_screen_does_not_have(tmp_path: Path) -> None:
    """이 시나리오·조회기간에 없는 공정도 저장에서 살아남는다(2026-09-29 리뷰에서 재현).

    공용 프리셋이라 다른 시나리오에는 있는 공정이다. 전에는 선택지에서 빠져 이름만 바꿔도 지워졌고,
    공정이 모두 없는 프리셋은 「공정을 하나 이상 고르세요」로 이름조차 못 바꿨다.
    """
    app, repository = _preset_app(
        tmp_path,
        [("A 그룹", ["ELSEWHERE", "DEMO_Chip_Attach"]), ("B 그룹", ["ONLY_ELSEWHERE"])],
        settings=True,
    )
    target = "home_key_process_preset_edit"
    app.selectbox(key=target).set_value("A 그룹").run()
    _save_preset_name_only(app, "A 그룹(개정)")
    assert repository.load_global_key_process().presets[0] == (
        "A 그룹(개정)",
        ("ELSEWHERE", "DEMO_Chip_Attach"),
    )

    app.selectbox(key=target).set_value("B 그룹").run()
    _save_preset_name_only(app, "B 그룹(개정)")
    assert not [item.value for item in app.error]
    assert repository.load_global_key_process().presets[1] == ("B 그룹(개정)", ("ONLY_ELSEWHERE",))


def _save_preset_name_only(app: AppTest, name: str) -> None:
    next(widget for widget in app.text_input if widget.label == "프리셋 이름").set_value(name)
    next(button for button in app.button if button.label == "프리셋 저장").click().run()
    assert not list(app.exception), [element.message for element in app.exception]


def test_a_colliding_display_name_saves_the_chosen_process_in_a_preset(tmp_path: Path) -> None:
    """DEMO_Final_Test 의 표시명이 다른 공정의 원본 DEMO_Chip_Attach 와 같다(2026-10-10 후속).

    프리셋 편집 상자는 multiselect 라 값을 보이는 글자로 주고받는다 — 같은 글자면 고른
    것과 다른 공정이 공용 프리셋에 저장됐다. 「표시명 (원본)」 으로 갈라 보이고 저장값은 원본이다.
    확보율 보정 편집표의 `공정` 칸은 값을 옵션 `value` 로 주고받아 값은 섞이지 않지만, 목록에서 둘을
    가려 고를 수 있게 같은 글자로 가른다.
    """
    from capa_simulation.components.home_preference import EXECUTION_EDITOR_KEY
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    database_path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    # 프로필은 `st.cache_data` 경계 뒤에 있어 앱을 돌리기 **전에** 심는다.
    repository.replace_global_process_rename(
        pd.DataFrame({"공정": ["DEMO_Final_Test"], "표시명": ["DEMO_Chip_Attach"]}),
        source="테스트",
    )
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception), [element.message for element in app.exception]
    app = _open_settings(app)

    picker = next(widget for widget in app.multiselect if widget.label == "공정")
    assert "DEMO_Chip_Attach" in picker.options
    assert "DEMO_Chip_Attach (DEMO_Final_Test)" in picker.options

    _save_preset(app, "A 그룹", ["DEMO_Final_Test"])
    assert repository.load_global_key_process().presets == (("A 그룹", ("DEMO_Final_Test",)),)

    editor = next(frame for frame in app.dataframe if EXECUTION_EDITOR_KEY in frame.proto.id)
    options = json.loads(editor.proto.columns)["공정"]["type_config"]["options"]
    labels = {option["value"]: option["label"] for option in options}
    assert labels["DEMO_Final_Test"] == "DEMO_Chip_Attach (DEMO_Final_Test)"
    assert labels["DEMO_Chip_Attach"] == "DEMO_Chip_Attach"
    # 증감 칸 머리도 「%」 다 — 「%p」 를 쓰지 않는다(2026-11-01 사용자 결정).
    assert json.loads(editor.proto.columns)["증감 확보율"]["label"] == "증감 확보율(%)"


def test_renaming_the_viewed_preset_from_preference_carries_the_view_on_return(
    tmp_path: Path,
) -> None:
    """보던 프리셋의 이름을 「HOME 설정」 팝업 Preference 에서 두 번 바꾸고 팝업을 닫으면 첫
    화면부터 새 이름이다.

    전에는 Preference 가 HOME 탭이라 카드가 서지 않는 그 탭에서 옮긴 선택이 쌓이기만 해, 돌아온 첫
    화면이 기본 프리셋을 그리고 두 번째 이름 변경은 아예 따라가지 못했다(2026-09-29 리뷰에서 재현).
    팝업이 열린 동안에도 사이드바 칸은 저장 회차마다 새 이름으로 선다.
    """
    app, _ = _preset_app(
        tmp_path, [("A 그룹", ["DEMO_Chip_Attach"]), ("B 그룹", ["DEMO_Final_Test"])]
    )
    app.session_state["home_key_process_preset"] = "B 그룹"
    app.run()
    app = _open_settings(app)

    app.selectbox(key="home_key_process_preset_edit").set_value("B 그룹").run()
    _save_preset_name_only(app, "B2")
    _save_preset_name_only(app, "B3")
    assert app.button(key="home_key_process_field").label == "B3 · 1공정"

    app = _close_settings(app)
    assert not list(app.exception)
    assert app.session_state["home_key_process_preset"] == "B3"
    assert app.button(key="home_key_process_field").label == "B3 · 1공정"
    assert any('title="주요공정 - B3"' in item.value for item in app.markdown)


def test_a_preset_absent_from_this_screen_says_so_instead_of_asking_to_choose(
    tmp_path: Path,
) -> None:
    """프리셋의 공정이 이 화면에 하나도 없으면 격자는 「고르세요」가 아니라 없다고 말한다."""
    from capa_simulation.components.home_figures import KEY_PROCESS_ABSENT_NOTICE

    app, _ = _preset_app(tmp_path, [("다른 라인", ["ONLY_ELSEWHERE"])])

    labels = app.session_state["spy_figures"]["key_process_heatmap_labels"]
    assert KEY_PROCESS_ABSENT_NOTICE in json.dumps(labels.to_plotly_json(), ensure_ascii=False)
    assert app.button(key="home_key_process_field").label == "다른 라인 · 0공정"
    app.button(key="home_key_process_field").click().run()
    assert not list(app.exception), [element.message for element in app.exception]
    (caption,) = app.radio(key="home_key_process_preset_pick").proto.captions
    assert caption == f"그릴 공정 없음 · 이 화면에 없음: {literal_markdown('ONLY_ELSEWHERE')}"


def test_a_long_section_title_stays_on_one_line_and_is_escaped() -> None:
    """구분 칸(260px) 제목 줄은 높이가 못박혀 있고 월 칸의 짝 빈 줄도 같은 높이다. 긴 프리셋
    이름이 줄을 바꾸면 그 줄만 높아져 아래 표의 행이 어긋났다 — 넘치면 한 줄로 말줄임하고 전체는
    풍선으로 보인다. 프리셋 이름은 사용자가 정한 글이라 이스케이프한다."""
    from capa_simulation.components.home_preference import section_title_markup
    from capa_simulation.components.home_rendering import dashboard_title_row_style

    markup = section_title_markup("주요공정 확보율 · <b>후공정 핵심 병목 관리 그룹 A</b>")

    assert "white-space:nowrap" in markup and "text-overflow:ellipsis" in markup
    assert 'title="주요공정 확보율 · &lt;b&gt;후공정 핵심 병목 관리 그룹 A&lt;/b&gt;"' in markup
    assert "<b>후공정" not in markup
    # 보이는 글은 `st.markdown` 을 거치므로 마크다운·지시어 글자도 엔티티로 넣는다(`~` 취소선,
    # `*` 기울임, `$` 수식, `:` 아이콘이 이름 글자를 먹지 않게).
    marked = section_title_markup("1~2공정 *핵심* $1 :red[x]")
    assert "1&#126;2공정 &#42;핵심&#42; &#36;1 &#58;red&#91;x&#93;" in marked
    style = " ".join(dashboard_title_row_style().split())
    # 줄부터 제목 글까지 모든 겹이 칸 폭 아래로 줄어들어야 말줄임이 칸 안에서 일어난다.
    assert ".st-key-key_process_title_row *," in style
    assert "_title_row * { min-width: 0; max-width: 100%; }" in style


def test_home_styles_sent_every_run_carry_no_css_comments() -> None:
    """HOME 의 제목 줄·공지 상자 스타일과 공정 필터 타일 풍선은 회차마다 소켓으로 다시 간다. CSS
    주석은 그때마다 함께 가는 바이트일 뿐이라 싣지 않는다 — 설명은 파이썬 주석에 둔다."""
    from capa_simulation.components.home_rendering import (
        dashboard_title_row_style,
        summary_notice_style,
    )
    from capa_simulation.components.process_picker import tile_tooltip_style

    for css in (
        dashboard_title_row_style(),
        summary_notice_style(),
        tile_tooltip_style(["공정 A", "공정 B"]),
    ):
        assert "<style>" in css
        assert "/*" not in css and "*/" not in css
