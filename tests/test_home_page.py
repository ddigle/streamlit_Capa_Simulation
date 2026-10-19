# Purpose: HOME 대시보드가 내장 시드 시나리오에서 렌더링되는 현재 동작을 고정한다.

import json
from functools import partial
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components.home_dimensions import (
    DASHBOARD_TITLE_HEIGHT_PX,
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
from capa_simulation.components.home_preference import THRESHOLD_POINTER
from capa_simulation.components.home_rendering import (
    BOTTLENECK_MONTHS_CHART_KEY,
    HOME_CELL_CHART_KEYS,
    KEY_PROCESS_MONTHS_CHART_KEY,
    LOB_MONTHS_CHART_KEY,
    open_clicked_home_cell,
)
from capa_simulation.components.plotly_layout import table_text_y
from capa_simulation.design import tokens
from capa_simulation.home_state import PRODUCT_SHARE_BASIS_KEY
from capa_simulation.process_detail_state import (
    HOME_BOTTLENECK_SECTION,
    HOME_KEY_PROCESS_SECTION,
    HOME_LOB_SECTION,
)
from capa_simulation.scenario_preset_state import PROCESS_SELECTION_KEY

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
    # 팝업 머리 — 무엇을 고르는지와 판정 기준을 정하는 자리(전에는 사이드바 상자에 늘 섰다).
    captions = [item.value for item in app.caption]
    assert any(text.startswith("B/N·확보율 판정에 넣을 공정 · ") for text in captions), captions
    assert THRESHOLD_POINTER in captions
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


def test_closing_the_process_filter_dialog_does_not_rerun_home() -> None:
    """공정 필터 팝업은 닫아도(X·바깥·Esc) HOME 을 다시 돌리지 않는다 — `on_dismiss` 기본값(ignore).

    닫는 회차에 서버가 할 일이 없다. 초안은 팝업 안에서만 읽히고 열 때마다
    `set_process_dialog_selection` 이 다시 적으며, 「선택 공정 적용」은 `st.rerun(scope="app")`
    이다. 주요공정 히트맵 팝업도 같은 기본값이다. AppTest 는 닫기를 흉내 내지 못해 선언을 읽는다.
    """
    import ast

    tree = ast.parse(HOME_PAGE.read_text(encoding="utf-8"))
    (dialog,) = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "show_process_filter_dialog"
    ]
    (decorator,) = dialog.decorator_list
    assert isinstance(decorator, ast.Call)
    assert ast.unparse(decorator.func) == "st.dialog"
    assert "on_dismiss" not in {keyword.arg for keyword in decorator.keywords}


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
    # 타일 몇 개를 끄고 적용하지 않은 채 닫는다(닫기는 서버로 오지 않는다).
    app.session_state["dashboard_bottleneck_process_dialog_draft"] = selection[1:]
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
    assert any("중복" in item.value for item in app.error)


def test_home_renders_summary_dashboard_from_the_builtin_seed(seeded_database: Path) -> None:
    app = _run(seeded_database)

    assert [element.value for element in app.title] == ["Capa LOB Summary"]
    # 내장 시드 프리셋이 복원한 조회기간. 판정 기준은 사이드바에 입력 칸이 없고 Preference 의
    # 공용 프로필이 정한다(2026-10-06 사용자 결정) — 저장 전에는 공식버전 프리셋 값을 쓴다.
    assert app.session_state["production_month_range_v2"] == ("2026-01", "2026-12")
    assert [widget.label for widget in app.sidebar.number_input] == []
    # 「판정 기준은 HOME → Preference 에서 정합니다」는 사이드바가 아니라 공정 필터 팝업 머리와
    # Guide 에 있다(2026-10-10 사용자 결정 — 사이드바에 늘 한 줄을 차지하던 것을 걷었다).
    assert THRESHOLD_POINTER not in [element.value for element in app.sidebar.caption]
    assert [
        (widget.label, widget.value)
        for widget in app.main.number_input
        if widget.label.startswith("기본")
    ] == [("기본 확보 기준(%)", 109.5), ("기본 경고 기준(%)", 99.5)]

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
    assert [widget.label for widget in app.sidebar.toggle] == [
        "선행 B/O",
        "선행 입고",
        "확보율 보정",
        "GAP",
        "상세 계획",
        "EDP 포함",
        "Past Data 포함",
    ]
    assert [widget.label for widget in app.main.toggle] == []
    # 붙여넣기는 표마다 작업 줄의 팝업이고, 저장은 Past Data 맨 위 한 곳이다. `Guide` 는
    # 툴바 버튼이 누르는 숨은 버튼이다.
    assert sorted(widget.label for widget in app.button) == sorted(
        [
            "Excel 붙여넣기",
            "Excel 붙여넣기",
            "Excel 붙여넣기",
            "Guide",
            "Summary 저장",
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
    # 제목 아래 설명 문구와 계획 세부수량 CSV 는 탭 자리를 내주고 사라졌다. 남은 내려받기는
    # Past Data 탭의 양식 세 개뿐이다.
    assert [button.label for button in app.download_button] == ["양식 CSV"] * 3


def test_home_puts_the_charts_in_a_main_tab_next_to_preference(seeded_database: Path) -> None:
    """차트별 설정을 담을 자리를 만들기 위한 탭이다. Main 은 기존 화면 그대로다."""
    app = _run(seeded_database)

    tabs = [tab.label for tab in app.main.tabs]
    assert tabs == [
        ":material/dashboard: Main",
        ":material/tune: Preference",
        ":material/history: Past Data",
    ]
    # 차트는 Main 탭 안에서만 그린다.
    assert app.session_state["spy_traces"] == [0, 2, 1, 1, 16, 2, 3, 4]


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


def _save_default_warning(app: AppTest, percent: float) -> AppTest:
    """Preference 의 판정 기준 편집기로 기본 경고 기준을 저장한다."""
    next(
        widget for widget in app.main.number_input if widget.label == "기본 경고 기준(%)"
    ).set_value(percent)
    next(button for button in app.button if button.label == "판정 기준 저장").click()
    return app.run()


def test_home_rebuilds_figures_when_a_threshold_changes(seeded_database: Path) -> None:
    app = _run(seeded_database)
    app.session_state["dashboard_show_performance"] = True
    app.run()
    assert _cache_state(app) == "적중"

    # 판정 기준은 Figure 캐시 키에 포함되어야 한다(AGENTS.md 5장 불변조건 7). 기준은 사이드바가
    # 아니라 Preference 의 공용 프로필에서 바꾼다.
    try:
        app = _save_default_warning(app, 95.0)

        assert not list(app.exception), [element.message for element in app.exception]
        assert not list(app.error), [element.value for element in app.error]
        assert _cache_state(app) == "생성"
        # 판정 기준은 색을 칠하는 세 묶음에만 닿는다. 계획 세부수량은 그대로 꺼낸다.
        assert _rebuilt_bundles(app) == {"LOB", "주요공정", "상세 B/N"}

        # 조건이 그대로면 다시 캐시를 재사용한다.
        app.run()
        assert _cache_state(app) == "적중"
    finally:
        # 모듈 공용 DB 다. 뒤 테스트가 같은 기준(99.5%)에서 출발하게 되돌린다.
        app = _save_default_warning(app, 99.5)
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
    assert len(app.error) == 1


def test_home_names_the_data_range_when_the_selection_is_outside_it(seeded_database: Path) -> None:
    """ "데이터가 없습니다" 만으로는 어디로 옮겨야 하는지 알 수 없다. 있는 범위를 같이 말한다."""
    app = _run(seeded_database)

    app.session_state["production_month_range_v2"] = ("2029-01", "2029-03")
    app.run()

    assert not list(app.exception)
    assert len(app.error) == 1
    assert "데이터 범위" in app.error[0].value


def test_the_two_display_toggles_are_part_of_the_figure_cache_key(
    seeded_database: Path,
) -> None:
    """EDP 포함 여부와 선행 반영 여부는 그림을 바꾼다. 캐시 키에 없으면 옛 그림이 남는다."""
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


def _create_comparison_scenario(database_path: Path, factor: float) -> tuple[str, str]:
    """현재 활성 계획의 수량만 바꾼 비교용 시나리오를 만든다.

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
            scenario_name="비교용",
            source_simulation_code="COMPARE-1",
            source_simulation_name="비교용",
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
            # 삭제 경로가 부르는 비우기와 같다(모듈 속성을 이 대역으로 바꿔 두어 직접 비운다).
            original_load_plan.clear()
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


def test_the_dashboard_is_not_drawn_while_its_tab_is_hidden(seeded_database: Path) -> None:
    """숨은 탭에서 그리면 재서 자리를 잡는 글자(주석 머리글 등)가 가운데를 놓치고 그대로 굳는다.

    숨겨진 요소 안에서는 SVG 글자 폭 측정이 0 이라 Plotly 가 가운데 정렬 보정을 못 하고,
    상세 세 Figure 는 `staticPlot` 이라 탭을 열어도 다시 그리지 않는다. Preference 에서
    비교 시나리오를 고르거나 선행 물량을 저장하면 앱이 다시 도는데, 그때 Main 이 닫혀
    있으면 정확히 그 상황이 된다.
    """
    app = _run(seeded_database)
    assert app.session_state["spy_traces"] == [0, 2, 1, 1, 16, 2, 3, 4]

    app.session_state["home_active_tab"] = ":material/tune: Preference"
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state["spy_traces"] == []


def test_the_detail_toggle_survives_a_hidden_tab(seeded_database: Path) -> None:
    """닫힌 동안 위젯을 그리지 않아도 값은 남아야 한다.

    보는 조건 토글 여섯은 사이드바 `LOB 표시 조건` 카드라 Main 이 아닌 탭에서는 그리지 않는다.
    `persist_state="session"` 이 그 값을 붙들어 주는데, 그것이 깨지면 탭을 오갈 때마다 분류가
    초기화된다.
    """
    app = _run(seeded_database)
    app.session_state["home_preference_plan_detail_customer"] = True
    app.session_state["home_active_tab"] = ":material/tune: Preference"
    app.run()
    assert not list(app.exception)

    app.session_state["home_active_tab"] = ":material/dashboard: Main"
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state["home_preference_plan_detail_customer"] is True


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
        assert spacer.proto.height_config.pixel_height == DASHBOARD_TITLE_HEIGHT_PX, key


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


def _seed_past_months(database_path: Path, months: list[int]) -> None:
    """공용 과거 프로필에 월별 실적만 넣는다. 세 표는 한 버전을 공유하므로 함께 준다."""
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
            "확보율": empty_past_table(PAST_SECUREMENT_COLUMNS),
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


def test_the_home_guide_carries_what_left_the_body() -> None:
    """토글 툴팁·Preference·Past Data 의 설명은 Guide 로 옮겼다."""
    from capa_simulation.components.page_guide import load_guide

    guide = load_guide("home")
    for text in (
        "LOB 표시 조건",
        "반비례",
        "퍼센트포인트",
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


def test_past_data_paste_opens_in_a_popup_and_save_sits_on_top(seeded_database: Path) -> None:
    """붙여넣기 칸은 본문을 차지하지 않고, 저장은 표들 위 한 곳이다."""
    app = _run(seeded_database)
    assert not [area for area in app.text_area if area.label.endswith("붙여넣기")]

    app.button(key="home_past_clipboard_월별_open").click().run()
    assert not app.exception
    assert [area.label for area in app.text_area if area.label.endswith("붙여넣기")] == [
        "월별 Density · Wafer Total 붙여넣기"
    ]


def test_a_past_data_paste_waiting_to_be_saved_puts_a_dot_on_its_tab(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """읽어 두고 저장하지 않은 과거 구간이 있으면 Past Data 탭 이름 옆에 점이 찍힌다.

    다른 화면의 미적용 점과 같은 규칙이다. 전에는 「대기 N행」이 남아도 점이 없었다(2026-10-01
    브라우저 점검). 저장하면 점이 사라진다.
    """
    import capa_simulation.components.tab_marks as tab_marks

    marked: dict[str, set[str]] = {}
    monkeypatch.setattr(
        tab_marks,
        "mark_pending_tabs",
        lambda key, labels, pending: marked.__setitem__(key, set(pending)),
    )
    app = AppTest.from_string(_home_script(tmp_path / "scenario.duckdb"), default_timeout=300)
    app.run()
    assert not app.exception
    assert marked["home_active_tab"] == set()

    app.button(key="home_past_clipboard_확보율_open").click().run()
    app.text_area(key="home_past_clipboard_확보율").set_value(
        "생산계획년월\t공정\t확보율\n202511\tDEMO_P\t1.05\n"
    )
    next(button for button in app.button if button.label == "붙여넣기 읽기").click()
    app.run()
    assert not app.exception
    assert marked["home_active_tab"] == {":material/history: Past Data"}

    next(button for button in app.button if button.label == "과거 구간 저장").click()
    app.run()
    assert not app.exception
    assert marked["home_active_tab"] == set()


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
    assert list(picker.proto.captions) == [
        "1공정 · DEMO_Chip_Attach",
        "2공정 · DEMO_Final_Test · DEMO_Wafer_Inspect",
    ]

    # 팝업이 고른 값을 적는 칸(위젯이 아닌 세션 값)을 바꾸면 히트맵이 따라간다. 팝업 본문의 적용은
    # 아래 테스트가 본다 — 칸을 누른 회차에만 서는 팝업이라 AppTest 의 다음 회차에는 없다.
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

    app.radio(key=KEY_PROCESS_PICK_KEY).set_value("B 그룹").run()
    assert not app.exception
    assert app.session_state[KEY_PROCESS_PRESET_KEY] == "B 그룹"
    # 적은 회차 + 다시 돈 회차. 다시 돈 회차는 같은 값이라 멈춘다.
    assert app.session_state["test_body_runs"] == 3


def _save_preset(app: AppTest, name: str, processes: list[str]) -> None:
    next(widget for widget in app.text_input if widget.label == "프리셋 이름").set_value(name)
    next(widget for widget in app.multiselect if widget.label == "공정").set_value(processes)
    next(button for button in app.button if button.label == "프리셋 저장").click().run()
    assert not list(app.exception), [element.message for element in app.exception]


def test_presets_are_made_renamed_promoted_and_deleted_from_preference(tmp_path: Path) -> None:
    """Preference 의 「주요공정 히트맵 프리셋」 — 만들기·이름 바꾸기·기본으로·삭제.

    저장은 늘 묶음 전체의 교체이고, 맨 앞 프리셋이 새 세션의 기본이다. 이름을 바꾸면 사이드바에서
    그 프리셋을 보고 있던 선택도 새 이름으로 옮긴다.
    """
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)
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
    app.button(key="home_key_process_preset_default").click().run()
    assert repository.load_global_key_process().preset_names == ("B 그룹", "A 그룹(개정)")
    # 선택지 라벨은 기본이 바뀌어도 같다 — 라벨이 바뀌면 브라우저가 옛 라벨을 되보낸다. 무엇이
    # 기본인지는 캡션이 말한다.
    assert set(app.selectbox(key=target).options) == labels_before
    assert not [label for label in labels_before if "기본" in label]
    assert any("「B 그룹」" in caption.value and "기본" in caption.value for caption in app.caption)

    # 삭제는 확인을 체크해야 열린다.
    assert app.button(key="home_key_process_preset_delete").disabled
    next(box for box in app.checkbox if box.label == "「B 그룹」 삭제 확인").check().run()
    app.button(key="home_key_process_preset_delete").click().run()
    assert not list(app.exception)
    assert repository.load_global_key_process().preset_names == ("A 그룹(개정)",)


def test_a_preset_with_a_duplicate_name_is_refused(tmp_path: Path) -> None:
    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    _save_preset(app, "A 그룹", ["DEMO_Chip_Attach"])
    app.selectbox(key="home_key_process_preset_edit").set_value("＋ 새 프리셋").run()
    _save_preset(app, "A 그룹", ["DEMO_Final_Test"])

    assert any("같은 이름의 프리셋" in item.value for item in app.error)


def _preset_app(tmp_path: Path, presets: list[tuple[str, list[str]]]) -> tuple[AppTest, Any]:
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    database_path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_key_process_presets(presets, source="테스트")
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception), [element.message for element in app.exception]
    return app, repository


def test_saving_a_preset_keeps_processes_this_screen_does_not_have(tmp_path: Path) -> None:
    """이 시나리오·조회기간에 없는 공정도 저장에서 살아남는다(2026-09-29 리뷰에서 재현).

    공용 프리셋이라 다른 시나리오에는 있는 공정이다. 전에는 선택지에서 빠져 이름만 바꿔도 지워졌고,
    공정이 모두 없는 프리셋은 「공정을 하나 이상 고르세요」로 이름조차 못 바꿨다.
    """
    app, repository = _preset_app(
        tmp_path,
        [("A 그룹", ["ELSEWHERE", "DEMO_Chip_Attach"]), ("B 그룹", ["ONLY_ELSEWHERE"])],
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

    프리셋 편집 상자는 key 없는 multiselect 라 값을 보이는 글자로 주고받는다 — 같은 글자면 고른
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


def test_renaming_the_viewed_preset_from_preference_carries_the_view_on_return(
    tmp_path: Path,
) -> None:
    """보던 프리셋의 이름을 Preference 에서 두 번 바꾸고 Main 으로 돌아오면 첫 화면부터 새 이름이다.

    카드가 서지 않는 Preference 탭에서 옮긴 선택이 쌓이기만 해, 돌아온 첫 화면이 기본 프리셋을
    그리고 두 번째 이름 변경은 아예 따라가지 못했다(2026-09-29 리뷰에서 재현).
    """
    app, _ = _preset_app(
        tmp_path, [("A 그룹", ["DEMO_Chip_Attach"]), ("B 그룹", ["DEMO_Final_Test"])]
    )
    app.session_state["home_key_process_preset"] = "B 그룹"
    app.run()
    app.session_state["home_active_tab"] = ":material/tune: Preference"
    app.run()

    app.selectbox(key="home_key_process_preset_edit").set_value("B 그룹").run()
    _save_preset_name_only(app, "B2")
    _save_preset_name_only(app, "B3")

    app.session_state["home_active_tab"] = ":material/dashboard: Main"
    app.run()
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
    assert caption == "그릴 공정 없음 · 이 화면에 없음: ONLY_ELSEWHERE"


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
