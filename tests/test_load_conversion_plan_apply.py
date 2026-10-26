# Purpose: 생산 계획 화면의 PKG PLAN·수율 적용·붙여넣기·가상 제품 등록 동작을 고정한다.

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest
from streamlit.proto.WidgetStates_pb2 import WidgetState, WidgetStates
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Dataframe, ElementTree

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.components.month_range_picker as month_range_picker
import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.services.korean_particle import with_object_particle

PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "load_conversion.py"

# 사용자 요청: 붙여넣기 일괄 적용 후 변경사항 적용을 또 눌러야 하는지 헷갈린다.
# 붙여넣기는 PKG PLAN 탭에만 반영하고, 전역 반영은 변경사항 적용 버튼으로만 한다.


def _script(database_path: Path) -> str:
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
apply_pending_scenario_preset()

exec(
    compile(Path({str(PAGE)!r}).read_text(encoding="utf-8"), {str(PAGE)!r}, "exec"),
    {{"__name__": "__main__"}},
)
"""


@pytest.fixture(autouse=True)
def _isolated_custom_renderers() -> Iterator[None]:
    """사용자 조작의 callback과 모든 rerun 동안 대역을 유지하고 테스트 뒤 원본을 복원한다."""
    original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
    original_month_picker = month_range_picker.render_month_range_apply
    try:
        with (
            patch.object(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None),
            patch.object(
                month_range_picker,
                "render_month_range_apply",
                lambda *, start, end, min_month, max_month, key: None,
            ),
        ):
            yield
    finally:
        assert horizontal_scrollbar.render_horizontal_scrollbar is original_scrollbar
        assert month_range_picker.render_month_range_apply is original_month_picker


@pytest.fixture(scope="module")
def seeded_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("plan_apply") / "scenario.duckdb"


def _plan_total(app: AppTest) -> float:
    plan = app.session_state["active_scenario"]["tables"]["RQ_PKG_PLAN"]
    return float(plan["생산수량"].astype(float).sum())


def _clipboard_text(app: AppTest, *, scale: float) -> str:
    """현재 편집 격자를 CSV 로 만들고 월 값을 배율만큼 바꾼 붙여넣기 문자열을 만든다."""
    from capa_simulation.scenario_state import scenario_month_table
    from capa_simulation.services.load_calculator import (
        PLAN_EDITOR_DIMENSIONS,
        plan_to_edit_table,
    )

    scenario = app.session_state["active_scenario"]
    # 프리셋이 복원한 조회기간("2026-01", "2026-12")을 YYYYMM 으로 바꾼다.
    start_label, end_label = app.session_state["production_month_range_v2"]
    start = int(str(start_label).replace("-", ""))
    end = int(str(end_label).replace("-", ""))
    wide = plan_to_edit_table(scenario_month_table(scenario, "RQ_PKG_PLAN", start, end))
    months = [c for c in wide.columns if c not in PLAN_EDITOR_DIMENSIONS]
    wide[months] = wide[months].astype(float) * scale
    # 클립보드 계약은 Excel 복사와 같은 탭 구분이다.
    return wide.to_csv(index=False, sep="	")


def _paste(app: AppTest, text: str) -> None:
    """작업 줄의 「Excel 붙여넣기」 팝업을 열고 붙여넣어 일괄 적용한다."""
    app.button(key="open_plan_paste").click().run()
    app.text_area(key="rq_pkg_plan_csv_clipboard").set_value(text)
    for button in app.button:
        if "붙여넣기 일괄 적용" in str(button.label):
            button.click().run()
            break


def _register(app: AppTest, product: str, stack: str) -> None:
    """작업 줄의 「가상 제품 등록」 팝업을 열고 등록한다."""
    app.button(key="open_virtual_product").click().run()
    app.text_input(key="virtual_product_name").set_value(product)
    app.text_input(key="virtual_product_stack").set_value(stack)
    for button in app.button:
        if "가상 제품 등록" in str(button.label) and button.key != "open_virtual_product":
            button.click().run()
            break


def test_paste_stages_into_the_tab_without_touching_the_global_plan(
    seeded_database: Path,
) -> None:
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    assert not list(app.exception)
    before_total = _plan_total(app)
    before_token = app.session_state["active_scenario"]["content_token"]

    _paste(app, _clipboard_text(app, scale=0.5))
    assert not list(app.exception)
    # 붙여넣기에 성공하면 팝업이 닫히고 완료 알림은 작업 줄 아래에 뜬다.
    assert "load_conversion_open_dialog" not in app.session_state
    assert any("PKG PLAN 탭에 반영했습니다" in item.value for item in app.success)

    # 탭에만 반영된다: 전역 계획값과 토큰은 그대로다.
    assert _plan_total(app) == pytest.approx(before_total)
    assert app.session_state["active_scenario"]["content_token"] == before_token
    assert "pkg_plan_staged_paste" in app.session_state


def test_apply_button_publishes_the_staged_plan_globally(seeded_database: Path) -> None:
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    assert not list(app.exception)
    before_total = _plan_total(app)
    before_token = app.session_state["active_scenario"]["content_token"]

    _paste(app, _clipboard_text(app, scale=0.5))
    app.button(key="apply_pkg_plan_changes").click().run()
    assert not list(app.exception)

    assert _plan_total(app) == pytest.approx(before_total * 0.5)
    assert app.session_state["active_scenario"]["content_token"] != before_token
    assert "pkg_plan_staged_paste" not in app.session_state


def test_virtual_product_registration_adds_the_key_to_every_clone_table(
    seeded_database: Path,
) -> None:
    """가상 제품 등록 팝업이 8개 기준정보에 새 제품 키를 넣고 계획은 0으로 시작해야 한다."""
    from capa_simulation.services.virtual_product import (
        available_source_products,
        clone_table_names,
    )

    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    assert not list(app.exception)
    tables = app.session_state["active_scenario"]["tables"]
    before_token = app.session_state["active_scenario"]["content_token"]
    source = available_source_products(tables).iloc[0]
    clone_tables = clone_table_names(tables)

    _register(app, "DEMO_VIRTUAL_X", str(source["Stack"]))
    assert not list(app.exception)
    # 등록하면 팝업이 닫히고, 다음 할 일(계획 수량 입력)을 알림이 작업 줄 아래에서 말한다.
    assert "load_conversion_open_dialog" not in app.session_state
    assert any(literal_markdown("DEMO_VIRTUAL_X") in item.value for item in app.success)
    # 복제된 계획 달이 조회기간 안이면 새 제품은 표에 바로 선다 — 입력하라고 말한다.
    assert any("아래 표에서 계획 수량을 입력하세요" in item.value for item in app.success)

    updated = app.session_state["active_scenario"]
    assert updated["content_token"] != before_token
    for name in clone_tables:
        assert "DEMO_VIRTUAL_X" in set(updated["tables"][name]["제품정보"]), name

    plan = updated["tables"]["RQ_PKG_PLAN"]
    cloned_plan = plan.loc[plan["제품정보"].eq("DEMO_VIRTUAL_X")]
    assert not cloned_plan.empty
    assert cloned_plan["생산수량"].astype(float).sum() == 0.0


def test_the_registration_notices_draw_the_typed_names_literally(
    seeded_database: Path,
) -> None:
    """등록 완료 알림은 다음 회차에 `st.success`(마크다운)로 그린다 — 사람이 적은 제품정보·Stack 을
    날로 끼우면 「HBM4~시제~」 의 물결표가 지움선(<del>)이 되어 사라지고 `*1*` 은 기울임이
    되었다(2026-10-26 E2E). 막아 실어 적은 글자 그대로 보인다."""
    from capa_simulation.services.virtual_product import available_source_products

    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    source = available_source_products(app.session_state["active_scenario"]["tables"]).iloc[0]
    assert str(source["Stack"]) != "E2E~가상~*1*"

    _register(app, "HBM4~시제~", "E2E~가상~*1*")
    assert not list(app.exception)

    (notice,) = [item.value for item in app.success if "등록했습니다" in item.value]
    assert notice.startswith(
        f"가상 제품 {literal_markdown('HBM4~시제~')} · "
        f"{with_object_particle(literal_markdown('E2E~가상~*1*'))} 등록했습니다."
    ), notice
    assert "HBM4~시제~" not in notice and "*1*" not in notice


def test_registered_virtual_product_appears_in_the_plan_editor(
    seeded_database: Path,
) -> None:
    """계획 수량 0 행을 보존하므로 등록 직후 편집 격자에 바로 나타나야 한다."""
    from capa_simulation.scenario_state import scenario_month_table
    from capa_simulation.services.load_calculator import plan_to_edit_table
    from capa_simulation.services.virtual_product import available_source_products

    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    source = available_source_products(app.session_state["active_scenario"]["tables"]).iloc[0]

    _register(app, "DEMO_VIRTUAL_Y", str(source["Stack"]))
    assert not list(app.exception)

    scenario = app.session_state["active_scenario"]
    start_label, end_label = app.session_state["production_month_range_v2"]
    grid = plan_to_edit_table(
        scenario_month_table(
            scenario,
            "RQ_PKG_PLAN",
            int(str(start_label).replace("-", "")),
            int(str(end_label).replace("-", "")),
        )
    )

    assert "DEMO_VIRTUAL_Y" in set(grid["제품정보"])


# --- 2026-09-29 횡전개 감사: 수율 원천 한 행이 화면 전체를 세우지 않는다 ---------------------


def _inject(app: AppTest, name: str, frame: pd.DataFrame, token: str) -> None:
    """활성 시나리오의 한 표를 바꿔 끼운다(원천이 그렇게 들어온 세션을 흉내 낸다)."""
    scenario = app.session_state["active_scenario"]
    updated = dict(scenario)
    updated["tables"] = {**scenario["tables"], name: frame}
    updated["revision"] = scenario["revision"] + 1
    updated["content_token"] = token
    app.session_state["active_scenario"] = updated
    app.run()


def _yield_rows(app: AppTest) -> pd.DataFrame:
    return pd.DataFrame(app.session_state["active_scenario"]["tables"]["RQ_YLD"]).reset_index(
        drop=True
    )


def _yield_values(frame: pd.DataFrame, product: str, month: int) -> list[float]:
    """그 제품·달 수율 행의 [EDS, BE]. 행이 없으면 빈 목록."""
    months = pd.to_numeric(frame["생산계획년월"])
    row = frame.loc[frame["제품정보"].eq(product) & months.eq(month), ["EDS_수율", "BE_수율"]]
    return [float(value) for value in row.to_numpy().ravel()]


def _widget_key(app: AppTest, key: str) -> str:
    """편집표가 지금 서 있는 세대 키(`editor_state.editor_widget_key` 와 같은 규칙)."""
    generation_key = f"{key}__generation"
    generation = app.session_state[generation_key] if generation_key in app.session_state else 0
    return key if not generation else f"{key}__g{generation}"


def _button_keys(app: AppTest) -> set[str]:
    return {button.key for button in app.button if button.key}


def test_an_empty_or_zero_yield_value_no_longer_stops_the_whole_page(
    seeded_database: Path,
) -> None:
    """RQ_YLD 한 행의 BE 가 비었거나 EDS 가 0 이어도 PKG PLAN·수율·등록이 선다.

    예전에는 `yield_to_edit_table` 이 표 전체를 거부하고 그 오류가 `plan_to_edit_table` 과 같은
    `try` 에서 `st.stop()` 해 화면 전체가 섰다. 그 행은 표에서 빼 「편집 불가」로 보이고, 무관한
    칸을 고쳐 적용해도 원본 그대로 남아야 한다.
    """
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    source = _yield_rows(app)
    months = pd.to_numeric(source["생산계획년월"])
    broken = source.copy()
    broken.loc[broken["제품정보"].eq("DEMO PRODUCT A") & months.eq(202603), "BE_수율"] = None
    broken.loc[broken["제품정보"].eq("DEMO PRODUCT B") & months.eq(202604), "EDS_수율"] = 0.0
    _inject(app, "RQ_YLD", broken, "broken-yield")

    assert not list(app.exception)
    assert not [item.value for item in app.error if "RQ_YLD" in item.value]
    assert {
        "apply_pkg_plan_changes",
        "open_plan_paste",
        "open_virtual_product",
        "apply_yield_changes",
        "open_yield_paste",
    } <= _button_keys(app)
    assert any("표에서 값을 뺐습니다" in item.value for item in app.warning)

    # 뺀 행과 무관한 칸(첫 행의 202601)을 고쳐 적용한다. 브라우저는 회차마다 편집표의 편집을
    # 다시 보내므로(AppTest 는 편집표 상태를 되보내지 않는다) 적용을 누르는 회차에도 넣는다.
    edit = {"edited_rows": {0: {"202601": 0.5}}, "added_rows": [], "deleted_rows": []}
    app.session_state[_widget_key(app, "yield_editor")] = edit
    app.run()
    app.session_state[_widget_key(app, "yield_editor")] = edit
    app.button(key="apply_yield_changes").click().run()
    assert not list(app.exception)
    assert any("활성 시나리오에 적용했습니다" in item.value for item in app.success)

    applied = _yield_rows(app)
    assert len(applied) == len(source)
    eds_a, be_a = _yield_values(applied, "DEMO PRODUCT A", 202603)
    assert eds_a == pytest.approx(0.96) and pd.isna(be_a)
    assert _yield_values(applied, "DEMO PRODUCT B", 202604)[0] == 0.0
    january = _yield_values(applied, "DEMO PRODUCT A", 202601) + _yield_values(
        applied, "DEMO PRODUCT B", 202601
    )
    assert january.count(0.5) == 1


def test_a_yield_source_that_cannot_build_a_table_stops_only_the_yield_tab(
    seeded_database: Path,
) -> None:
    """연결 키가 겹쳐 수율 표를 세울 수 없으면 수율 탭에만 오류가 뜨고 PKG PLAN 은 선다."""
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    source = _yield_rows(app)
    _inject(app, "RQ_YLD", pd.concat([source, source.iloc[[0]]]), "duplicated-yield")

    assert not list(app.exception)
    assert any("수율 표를 만들지 못했습니다" in item.value for item in app.error)
    keys = _button_keys(app)
    assert {"apply_pkg_plan_changes", "open_plan_paste", "open_virtual_product"} <= keys
    assert not {"apply_yield_changes", "open_yield_paste"} & keys


def _yield_clipboard_text(
    app: AppTest,
    *,
    blank: tuple[str, str] | None = None,
    fill: tuple[str, float, float] | None = None,
) -> str:
    """지금 수율 편집표를 붙여넣기 문자열로 만든다. `blank=(제품, 월)` 이면 그 달 EDS·BE 를
    비우고, `fill=(제품, EDS, BE)` 이면 그 제품의 모든 달을 그 값으로 채운다."""
    from capa_simulation.scenario_state import scenario_month_table
    from capa_simulation.services.load_calculator import (
        YIELD_EDITOR_DIMENSIONS,
        split_editable_yield_rows,
        yield_to_edit_table,
    )

    start_label, end_label = app.session_state["production_month_range_v2"]
    # 화면이 양식을 만드는 것과 같이, 값이 잘못된 행은 그 달 칸을 빈칸으로 실은 표다.
    editable, locked = split_editable_yield_rows(
        scenario_month_table(
            app.session_state["active_scenario"],
            "RQ_YLD",
            int(str(start_label).replace("-", "")),
            int(str(end_label).replace("-", "")),
        )
    )
    wide = yield_to_edit_table(editable, locked=locked)
    if blank is not None:
        product, month = blank
        wide[month] = wide[month].astype(object)
        wide.loc[wide["제품정보"].eq(product), month] = ""
    if fill is not None:
        product, eds, be = fill
        months = [column for column in wide.columns if column not in YIELD_EDITOR_DIMENSIONS]
        for kind, value in (("EDS", eds), ("BE", be)):
            wide.loc[wide["제품정보"].eq(product) & wide["수율 구분"].eq(kind), months] = value
    return wide.to_csv(index=False, sep="\t")


def _paste_yield(app: AppTest, text: str) -> None:
    """작업 줄의 수율 「Excel 붙여넣기」 팝업을 열고 붙여넣어 적용한다(수율은 바로 적용된다)."""
    app.button(key="open_yield_paste").click().run()
    app.text_area(key="rq_yield_csv_clipboard").set_value(text)
    for button in app.button:
        if "붙여넣기 일괄 적용" in str(button.label):
            button.click().run()
            break


def test_blanking_a_month_in_the_yield_paste_says_the_row_was_removed(
    seeded_database: Path,
) -> None:
    """한 (키, 월)의 EDS·BE 를 둘 다 비워 붙여넣으면 그 달 수율 행이 지워진다 — 완료 문구가 말한다.

    예전에는 말없이 지워지고 그 계획은 환산에서 빠졌다(알림은 환산 탭 경고뿐).
    """
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    before = len(_yield_rows(app))

    _paste_yield(app, _yield_clipboard_text(app, blank=("DEMO PRODUCT A", "202605")))
    assert not list(app.exception)

    assert len(_yield_rows(app)) == before - 1
    messages = [item.value for item in app.success]
    assert any("2칸을 비워 그 달 수율 행을 지웠습니다" in message for message in messages)
    assert any("환산에서 빠집니다" in message for message in messages)


def test_a_yield_paste_that_blanks_nothing_adds_no_removal_note(seeded_database: Path) -> None:
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()

    _paste_yield(app, _yield_clipboard_text(app))
    assert not list(app.exception)

    messages = [item.value for item in app.success]
    assert any("활성 시나리오에 적용했습니다" in message for message in messages)
    assert not any("지웠습니다" in message for message in messages)


def test_blanking_a_month_in_the_yield_grid_says_the_row_was_removed(
    seeded_database: Path,
) -> None:
    """E3 — 격자에서 한 (제품, 월)의 EDS·BE 를 둘 다 비워 적용해도 붙여넣기처럼 지운 칸 수를 말한다.

    그 달 수율 행이 지워져 그 계획은 환산·소요대수에서 빠진다. 붙여넣기만 알리고 격자는 말없이
    지나가면 같은 일이 길에 따라 다르게 보인다.
    """
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    before = len(_yield_rows(app))
    grid = _yield_grid(app)
    month = next(column for column in grid.columns if str(column).isdigit())
    target = grid.loc[grid["제품정보"].eq("DEMO PRODUCT A")]
    assert sorted(target["수율 구분"]) == ["BE", "EDS"]
    edit = {
        "edited_rows": {int(index): {month: None} for index in target.index},
        "added_rows": [],
        "deleted_rows": [],
    }
    app.session_state[_widget_key(app, "yield_editor")] = edit
    app.run()
    app.session_state[_widget_key(app, "yield_editor")] = edit
    app.button(key="apply_yield_changes").click().run()

    assert not list(app.exception)
    assert len(_yield_rows(app)) == before - 1
    messages = [item.value for item in app.success]
    assert any("2칸을 비워 그 달 수율 행을 지웠습니다" in message for message in messages), messages


def test_a_yield_paste_keeps_the_locked_rows_and_does_not_count_them_as_removed(
    seeded_database: Path,
) -> None:
    """붙여넣기도 편집 불가 행을 되붙인다. 양식에서 이미 빈칸인 그 달은 「지운 칸」이 아니다."""
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    source = _yield_rows(app)
    months = pd.to_numeric(source["생산계획년월"])
    broken = source.copy()
    broken.loc[broken["제품정보"].eq("DEMO PRODUCT A") & months.eq(202603), "BE_수율"] = None
    _inject(app, "RQ_YLD", broken, "broken-yield-paste")

    _paste_yield(app, _yield_clipboard_text(app))
    assert not list(app.exception)

    applied = _yield_rows(app)
    assert len(applied) == len(source)
    eds, be = _yield_values(applied, "DEMO PRODUCT A", 202603)
    assert eds == pytest.approx(0.96) and pd.isna(be)
    messages = [item.value for item in app.success]
    assert any("활성 시나리오에 적용했습니다" in message for message in messages)
    assert not any("지웠습니다" in message for message in messages)


# --- 2026-09-29 리뷰: 범위 밖 수율은 계산을 멈추되 어느 행인지 알리고, 이 화면에서 고칠 수 있다 ---


def _break_every_month(app: AppTest, product: str, token: str) -> pd.DataFrame:
    """그 제품의 모든 달 EDS 를 0 으로 바꿔 끼운다 — 편집표에서 그 제품 값이 전부 빠진다."""
    source = _yield_rows(app)
    broken = source.copy()
    broken.loc[broken["제품정보"].eq(product), "EDS_수율"] = 0.0
    _inject(app, "RQ_YLD", broken, token)
    return source


def _yield_grid(app: AppTest) -> pd.DataFrame:
    """화면에 선 수율 편집표(세대 키와 무관하게 `수율 구분` 컬럼으로 찾는다)."""
    grids = [frame.value for frame in app.dataframe if "수율 구분" in frame.value.columns]
    assert len(grids) == 1, len(grids)
    return grids[0].reset_index(drop=True)


def test_an_out_of_range_yield_names_the_row_where_the_conversion_stops(
    seeded_database: Path,
) -> None:
    """Wafer 환산이 EDS=0 한 행에서 멈출 때 오류문이 그 년월·제품과 고치는 곳을 말한다.

    멈추는 것은 그대로다(2026-09-28 사용자 결정). 예전 문구는 「RQ_YLD의 수율은 0 초과 100%
    이하여야 합니다.」뿐이었다.
    """
    app = AppTest.from_string(_script(seeded_database), default_timeout=300)
    app.session_state["monthly_volume_basis"] = "Wafer"
    app.run()
    source = _yield_rows(app)
    months = pd.to_numeric(source["생산계획년월"])
    broken = source.copy()
    broken.loc[broken["제품정보"].eq("DEMO PRODUCT B") & months.eq(202604), "EDS_수율"] = 0.0
    _inject(app, "RQ_YLD", broken, "out-of-range-yield")

    assert not list(app.exception)
    errors = [item.value for item in app.error if "RQ_YLD" in item.value]
    assert len(errors) == 1, errors
    assert "202604 · DEMO PRODUCT B" in errors[0]
    assert "EDS 0(0%)" in errors[0]
    assert "수율 탭에서 그 달의 EDS·BE 를 둘 다 고쳐 적용하세요" in errors[0]
    warnings = [item.value for item in app.warning if "편집 불가" in item.value]
    assert warnings and "HOME·소요대수·확보율 계산을 멈춥니다" in warnings[0]


def test_a_product_locked_in_every_month_can_be_fixed_from_the_yield_grid(
    seeded_database: Path,
) -> None:
    """모든 달이 잠긴 제품도 편집표에 빈칸 행으로 나오고, 둘 다 채워 적용하면 환산이 돈다.

    예전에는 그 제품 행이 표에 없어 이 화면에서 고칠 길이 없었고 Wafer 환산은 계속 멈췄다.
    """
    app = AppTest.from_string(_script(seeded_database), default_timeout=300)
    app.session_state["monthly_volume_basis"] = "Wafer"
    app.run()
    source = _break_every_month(app, "DEMO PRODUCT B", "locked-every-month")
    assert any("RQ_YLD" in item.value for item in app.error)

    grid = _yield_grid(app)
    b_rows = grid.loc[grid["제품정보"].eq("DEMO PRODUCT B")]
    assert sorted(b_rows["수율 구분"]) == ["BE", "EDS"]
    months = [column for column in grid.columns if str(column).isdigit()]
    assert b_rows[months].isna().all(axis=None)

    edit = {
        "edited_rows": {
            int(index): {month: (0.9 if kind == "EDS" else 0.95) for month in months}
            for index, kind in zip(b_rows.index, b_rows["수율 구분"], strict=True)
        },
        "added_rows": [],
        "deleted_rows": [],
    }
    app.session_state[_widget_key(app, "yield_editor")] = edit
    app.run()
    app.session_state[_widget_key(app, "yield_editor")] = edit
    app.button(key="apply_yield_changes").click().run()

    assert not list(app.exception)
    assert not [item.value for item in app.error if "RQ_YLD" in item.value]
    applied = _yield_rows(app)
    assert len(applied) == len(source)
    fixed = applied.loc[applied["제품정보"].eq("DEMO PRODUCT B"), ["EDS_수율", "BE_수율"]]
    assert fixed.to_numpy().tolist() == [[0.9, 0.95]] * len(fixed)


def test_a_yield_paste_can_overwrite_a_product_locked_in_every_month(
    seeded_database: Path,
) -> None:
    """붙여넣기 양식에도 그 제품 행이 빈칸으로 실려, 채워 붙여넣으면 고쳐진다."""
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    source = _break_every_month(app, "DEMO PRODUCT B", "locked-every-month-paste")

    _paste_yield(app, _yield_clipboard_text(app, fill=("DEMO PRODUCT B", 0.9, 0.95)))

    assert not list(app.exception)
    assert any("활성 시나리오에 적용했습니다" in item.value for item in app.success)
    applied = _yield_rows(app)
    assert len(applied) == len(source)
    fixed = applied.loc[applied["제품정보"].eq("DEMO PRODUCT B"), ["EDS_수율", "BE_수율"]]
    assert fixed.to_numpy().tolist() == [[0.9, 0.95]] * len(fixed)


def test_registering_a_product_planned_only_outside_the_period_says_to_widen_it(
    seeded_database: Path,
) -> None:
    """원본 제품의 계획이 조회기간 밖에만 있으면 새 제품은 PKG PLAN 표에 행이 없다.

    완료 문구가 「아래 표에서 입력하세요」라고 거짓을 말하던 것을, 조회기간을 넓혀야 한다는 말과
    복제된 계획 달로 바꾼다(2026-09-29 횡전개 감사).
    """
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    plan = pd.DataFrame(app.session_state["active_scenario"]["tables"]["RQ_PKG_PLAN"])
    months = pd.to_numeric(plan["생산계획년월"])
    first_half_only = plan.loc[~(plan["제품정보"].eq("DEMO PRODUCT A") & months.ge(202607))]
    _inject(app, "RQ_PKG_PLAN", first_half_only.reset_index(drop=True), "first-half-plan")
    app.session_state["production_month_range_v2"] = ("2026-07", "2026-12")
    app.run()

    # 후보 첫 제품이 DEMO PRODUCT A(8H)다.
    _register(app, "DEMO_VIRTUAL_Z", "8H")
    assert not list(app.exception)

    messages = [
        item.value for item in app.success if literal_markdown("DEMO_VIRTUAL_Z") in item.value
    ]
    assert messages
    assert "조회기간을 넓혀야 PKG PLAN 표에 나타납니다" in messages[0]
    assert "202601" in messages[0]
    assert "아래 표에서 계획 수량을 입력하세요" not in messages[0]


def test_a_space_only_cell_in_the_plan_paste_reads_as_zero(seeded_database: Path) -> None:
    """공백 한 칸(`' '`)만 든 붙여넣기 칸은 빈칸 — 0 수량이다.

    검증 단계는 빈칸으로 통과시키고 변환(`plan_from_edit_table`)은 「숫자가 아닌 값」으로 표 전체를
    거부했으며 어느 칸인지도 알리지 않았다(2026-09-29 횡전개 감사).
    """
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    rows = _clipboard_text(app, scale=1.0).splitlines()
    header = rows[0].split("\t")
    first = rows[1].split("\t")
    first[header.index("202601")] = " "
    rows[1] = "\t".join(first)

    _paste(app, "\n".join(rows))
    assert not list(app.exception)
    assert not [item.value for item in app.error]
    assert "pkg_plan_staged_paste" in app.session_state

    app.button(key="apply_pkg_plan_changes").click().run()
    assert not list(app.exception)
    plan = pd.DataFrame(app.session_state["active_scenario"]["tables"]["RQ_PKG_PLAN"])
    product = first[header.index("제품정보")]
    january = plan.loc[
        plan["제품정보"].eq(product) & pd.to_numeric(plan["생산계획년월"]).eq(202601), "생산수량"
    ]
    assert january.astype(float).tolist() == [0.0]


# --- 2026-10-01 브라우저 E2E: 한 표를 적용한 직후 회차에 사이드바가 보는 「적용 전 편집」 ---------

PRE_PAGE_LOG_KEY = "test_pre_page_pending_edits"
PLAN_CELL_EDIT = {"edited_rows": {0: {"202602": 200.0}}, "added_rows": [], "deleted_rows": []}
YIELD_CELL_EDIT = {"edited_rows": {0: {"202603": 0.9}}, "added_rows": [], "deleted_rows": []}


def _sidebar_probe_script(database_path: Path) -> str:
    """회차마다 페이지 **앞에서** 「적용 전 편집」 목록을 적어 두는 스크립트.

    `app.py` 는 `pending_edit_labels` 를 `navigation.run()` 전에 부르고, 사이드바 캡션과 저장
    팝업의 경고·확인 체크·잠금이 그 값으로 그려진다. 같은 차례에서 같은 함수를 불러 남긴다.
    """
    return _script(database_path).replace(
        "apply_pending_scenario_preset()\n",
        "apply_pending_scenario_preset()\n"
        "from capa_simulation.components.scenario_edit_bar import pending_edit_labels\n"
        f"st.session_state.setdefault({PRE_PAGE_LOG_KEY!r}, []).append(\n"
        "    pending_edit_labels('load_conversion.py')\n"
        ")\n",
        1,
    )


@contextmanager
def _browser_held_edits() -> Iterator[dict[str, str]]:
    """브라우저가 들고 있다가 사용자 조작마다 다시 보내는 편집표 상태를 흉내 낸다.

    AppTest 는 편집표의 편집을 되보내지 않고(위 수율 테스트의 주석), 세션에 넣은 값은 사용자 키
    칸이라 `st.rerun()` 회차에 그리지 않은 위젯 상태를 Streamlit 이 지우는 동작도 드러나지 않는다.
    그래서 돌려준 사전(요소 id → 편집 상태 JSON)을 AppTest 가 보내는 위젯 상태에 덧붙인다 —
    브라우저가 보내는 것과 같은 자리다. `ElementTree.get_widget_states` 는 Streamlit 테스트 도구의
    내부 이름이라, Streamlit 을 올린 뒤 이 테스트가 깨지면 여기부터 본다.
    """
    held: dict[str, str] = {}
    original = ElementTree.get_widget_states

    def with_held_edits(tree: ElementTree) -> WidgetStates:
        states = original(tree)
        for element_id, value in held.items():
            states.widgets.append(WidgetState(id=element_id, string_value=value))
        return states

    with patch.object(ElementTree, "get_widget_states", with_held_edits):
        yield held


def _editor_node(app: AppTest, key: str) -> Dataframe:
    """편집표가 지금 서 있는 세대 키의 요소."""
    widget_key = _widget_key(app, key)
    nodes: list[object] = [app.main]
    while nodes:
        node = nodes.pop()
        if isinstance(node, Dataframe) and node.key == widget_key:
            return node
        nodes.extend(getattr(node, "children", {}).values())
    raise AssertionError(f"{widget_key} 편집표가 그려지지 않았습니다.")


@pytest.mark.parametrize(
    ("applied", "applied_edit", "apply_button", "other", "other_edit", "other_label"),
    [
        (
            "pkg_plan_editor",
            PLAN_CELL_EDIT,
            "apply_pkg_plan_changes",
            "yield_editor",
            YIELD_CELL_EDIT,
            "생산 계획 · 수율",
        ),
        (
            "yield_editor",
            YIELD_CELL_EDIT,
            "apply_yield_changes",
            "pkg_plan_editor",
            PLAN_CELL_EDIT,
            "생산 계획 · PKG PLAN",
        ),
    ],
)
def test_applying_one_table_leaves_only_the_other_tables_edit_pending(
    seeded_database: Path,
    applied: str,
    applied_edit: dict[str, object],
    apply_button: str,
    other: str,
    other_edit: dict[str, object],
    other_label: str,
) -> None:
    """한 표를 적용한 다음 회차에 사이드바가 보는 목록은 **다른 표의 적용 전 편집** 뿐이다.

    두 결함이 겹쳐 있었다(2026-10-01 브라우저 E2E). 사이드바는 페이지보다 먼저 돌아, 방금 적용한
    표를 그 회차 동안 「적용 전 편집」으로 세고 저장을 잠갔다. 또 PKG PLAN 적용은 수율 편집표를
    그리기 **전에** `st.rerun()` 해, Streamlit 이 그 회차에 그리지 않은 수율 편집 상태를 서버에서
    지웠다 — 수율 점과 저장 경고가 사라졌고, 그때 누른 「신규 리비전 저장」은 다음 조작에 브라우저가
    되보낸 편집 때문에 잠긴 버튼이 되어 말없이 무시됐다.
    """
    with _browser_held_edits() as browser:
        app = AppTest.from_string(_sidebar_probe_script(seeded_database), default_timeout=300)
        app.run()
        assert not list(app.exception)
        browser[_editor_node(app, other).proto.id] = json.dumps(other_edit)
        app.run()
        assert app.session_state[PRE_PAGE_LOG_KEY][-1] == [other_label]
        applied_id = _editor_node(app, applied).proto.id
        browser[applied_id] = json.dumps(applied_edit)
        app.run()
        before_token = app.session_state["active_scenario"]["content_token"]
        runs_before = len(app.session_state[PRE_PAGE_LOG_KEY])

        app.button(key=apply_button).click().run()
        # 적용한 표는 새 세대 키로 다시 선다 — 브라우저에서 옛 요소와 그 편집이 사라진다.
        browser.pop(applied_id)
        assert not list(app.exception)
        assert app.session_state["active_scenario"]["content_token"] != before_token

        # 누른 회차와 적용 뒤 `st.rerun()` 회차. 사용자가 보는 사이드바는 뒤 회차의 것이다.
        runs = app.session_state[PRE_PAGE_LOG_KEY][runs_before:]
        assert len(runs) == 2
        assert runs[-1] == [other_label]
        # 다른 표의 편집은 서버에도 그대로 남아 탭 점·작업 줄이 계속 선다.
        assert app.session_state[_widget_key(app, other)]["edited_rows"]
        assert not app.session_state[_widget_key(app, applied)]["edited_rows"]

        # 다음 조작에서도 목록이 바뀌지 않는다 — 저장을 누른 회차에 경고가 새로 솟지 않는다.
        app.run()
        assert app.session_state[PRE_PAGE_LOG_KEY][-1] == [other_label]


def test_blank_cells_in_both_editors_show_as_blank_not_none(seeded_database: Path) -> None:
    """PKG PLAN 의 0 칸과 수율의 편집 불가 칸은 빈칸으로 싣는다 — "None" 글자가 아니다.

    빈칸 표시(`placeholder`)를 주지 않으면 Streamlit 은 빈 칸에 "None" 을 그린다(2026-10-01
    브라우저 E2E). 가이드는 그 칸을 「빈칸」이라고 설명한다.
    """
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    assert not list(app.exception)

    for key in ("pkg_plan_editor", "yield_editor"):
        proto = _editor_node(app, key).proto
        assert proto.HasField("placeholder"), key
        assert proto.placeholder == "", key


def _plan_grid_total(app: AppTest) -> float:
    """화면에 선 PKG PLAN 편집표(원본)의 월 칸 합계."""
    from capa_simulation.services.load_calculator import PLAN_EDITOR_DIMENSIONS

    grids = [
        frame.value
        for frame in app.dataframe
        if set(PLAN_EDITOR_DIMENSIONS) <= set(frame.value.columns)
        and "수율 구분" not in frame.value.columns
    ]
    assert len(grids) == 1, len(grids)
    months = [column for column in grids[0].columns if str(column).isdigit()]
    return float(grids[0][months].apply(pd.to_numeric).sum().sum())


def _plan_editor_path(app: AppTest) -> tuple[int, ...]:
    """PKG PLAN 편집표의 델타 경로(본문 기준 자식 번호 차례). 세대 키가 바뀌어도 같은 표다."""
    found: list[tuple[int, ...]] = []

    def walk(node: Any, path: tuple[int, ...]) -> None:
        if isinstance(node, Dataframe) and str(node.key or "").startswith("pkg_plan_editor"):
            found.append(path)
        for index, child in getattr(node, "children", {}).items():
            walk(child, (*path, index))

    walk(app.main, ())
    assert len(found) == 1, found
    return found[0]


def test_the_plan_notices_stand_in_one_slot_above_the_editor(
    seeded_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """붙여넣기·적용 알림은 작업 줄 아래 늘 서 있는 칸에 선다 — 생기고 빠져도 PKG PLAN 편집표의
    자리가 그대로다. 두 동작은 `st.rerun()` 으로 끊기고 다음 회차에 알림이 생기므로, 밀리면
    브라우저에 옛 편집표의 흐린 사본이 남는다(AGENTS 9장 「조건부 알림」). 여기서는 그 원인인 자리
    밀림을 잰다. 알림이 빠지는 회차를 보려고 쓰기 알림 표지의 창은 0 으로 둔다(창 안의 회차는 알림을
    다시 그린다 — 아래 두 번 누름 시험)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    assert not list(app.exception)
    before = _plan_editor_path(app)

    _paste(app, _clipboard_text(app, scale=0.5))
    assert any("붙여넣기 표를 PKG PLAN 탭에 반영했습니다" in item.value for item in app.success)
    assert _plan_editor_path(app) == before

    app.button(key="apply_pkg_plan_changes").click().run()
    assert not list(app.exception)
    assert any("PKG PLAN을 전역 계획값에 반영했습니다" in item.value for item in app.success)
    assert _plan_editor_path(app) == before

    app.run()
    assert not any("반영했습니다" in item.value for item in app.success)
    assert _plan_editor_path(app) == before


def test_the_plan_editor_shows_the_applied_plan_right_after_apply(seeded_database: Path) -> None:
    """편집표 원본은 (시나리오 내용·편집 기간·표시순서) 키 캐시다. 적용이 새 토큰을 내므로 바로 다음
    회차 편집표가 새 계획을 보인다 — 옛 원본이 남으면 다음 적용에서 값이 되돌아간다."""
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    assert not list(app.exception)
    before = _plan_grid_total(app)

    _paste(app, _clipboard_text(app, scale=0.5))
    app.button(key="apply_pkg_plan_changes").click().run()
    assert not list(app.exception)

    assert _plan_grid_total(app) == pytest.approx(before * 0.5)


APPLIED_ICON = ":material/published_with_changes:"


def _applied(app: AppTest, text: str) -> list[str | None]:
    """그 글이 든 성공 알림의 아이콘들(알림이 없으면 빈 목록)."""
    return [item.icon for item in app.success if text in str(item.value)]


def test_the_plan_apply_notice_survives_a_second_press_on_the_locked_button(
    seeded_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「PKG PLAN 변경사항 적용」 을 0.3~0.35초 간격으로 두 번 누르면 적용은 되는데 성공 알림이
    사라졌다(2026-10-27 E2E 3/4). 둘째 누름은 적용 뒤 잠긴 단추에 닿아 버려지고, 그 회차가 화면을
    다시 그리며 앞 회차가 꺼내 그린 알림을 지웠다. 쓰기 직후 적어 둔 알림 표지로 창 안의 회차가 같은
    아이콘으로 다시 그린다 — 창이 지난 회차는 그리지 않는다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    _paste(app, _clipboard_text(app, scale=0.5))
    app.button(key="apply_pkg_plan_changes").click().run()
    assert not list(app.exception)
    assert _applied(app, "PKG PLAN을 전역 계획값에 반영했습니다") == [APPLIED_ICON]
    assert app.button(key="apply_pkg_plan_changes").disabled

    # 둘째 누름의 회차 — 잠긴 단추의 누름은 버려져 아무것도 하지 않고 화면만 다시 그린다.
    app.run()
    assert not list(app.exception)
    assert _applied(app, "PKG PLAN을 전역 계획값에 반영했습니다") == [APPLIED_ICON]

    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    app.run()
    assert _applied(app, "PKG PLAN을 전역 계획값에 반영했습니다") == []


def test_the_yield_apply_notice_survives_a_second_press_on_the_locked_button(
    seeded_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「수율 변경사항 적용」 도 같다(2026-10-27 E2E 4/6)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    grid = _yield_grid(app)
    month = next(column for column in grid.columns if str(column).isdigit())
    edit = {
        "edited_rows": {0: {month: 0.5}},
        "added_rows": [],
        "deleted_rows": [],
    }
    app.session_state[_widget_key(app, "yield_editor")] = edit
    app.run()
    app.session_state[_widget_key(app, "yield_editor")] = edit
    app.button(key="apply_yield_changes").click().run()
    assert not list(app.exception)
    assert _applied(app, "RQ_YLD 편집값을 활성 시나리오에 적용했습니다") == [APPLIED_ICON]

    app.run()
    assert not list(app.exception)
    assert _applied(app, "RQ_YLD 편집값을 활성 시나리오에 적용했습니다") == [APPLIED_ICON]
