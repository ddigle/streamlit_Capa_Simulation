# Purpose: 생산 계획 화면의 PKG PLAN·수율 적용·붙여넣기·가상 제품 등록 동작을 고정한다.

from collections.abc import Iterator
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest
from alert_marks import (
    active_state,
    alert_notes,
    data_error_texts,
    flashed,
    note_table,
    place_errors,
    successes,
    table_frame,
)
from edit_grid_fake import Calls, install_fake_edit_grid, last, send_ops, shell_frame, shell_key
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block, TextInput

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.components.month_range_picker as month_range_picker
import capa_simulation.components.write_guard as write_guard
from capa_simulation import alerts
from capa_simulation.components import table_toolbar
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.services.korean_particle import with_object_particle
from capa_simulation.services.month_columns import month_label

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
                lambda *, start, end, min_month, max_month, key, this_month=None: None,
            ),
        ):
            yield
    finally:
        assert horizontal_scrollbar.render_horizontal_scrollbar is original_scrollbar
        assert month_range_picker.render_month_range_apply is original_month_picker


@pytest.fixture(scope="module")
def seeded_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("plan_apply") / "scenario.duckdb"


# 생산 계획 PKG PLAN · 수율 표는 범용 편집 그리드다 — AppTest 는 그 JS 를 못 돌려 대역이 받은
# 껍데기 · feed 를 적고 출납(op)을 콜백으로 보낸다(`tests/edit_grid_fake.py`).
_GRID: dict[str, Calls] = {}
PLAN_HOST = "plan_grid"
YIELD_HOST = "yield_grid"
TAB_KEY = "load_conversion_active_tab"
PLAN_TAB = ":material/edit_calendar: PKG PLAN"
YIELD_TAB = ":material/percent: 수율"


@pytest.fixture(autouse=True)
def _fake_grids(monkeypatch: pytest.MonkeyPatch) -> None:
    _GRID["calls"] = install_fake_edit_grid(monkeypatch)


def _open_tab(app: AppTest, label: str) -> AppTest:
    """그 탭을 연다 — 닫힌 탭의 그리드는 표 없는 껍데기라 칸을 고치려면 먼저 연다."""
    app.session_state[TAB_KEY] = label
    app.run()
    assert not list(app.exception)
    return app


def _shell(host: str) -> dict[str, Any] | None:
    """그 그리드가 마지막으로 받은 껍데기(한 번도 세우지 않았으면 None)."""
    return next((data for name, data in reversed(_GRID["calls"]) if name == host), None)


def _grid(app: AppTest, host: str) -> pd.DataFrame:
    """그 그리드에 실린 표(분류 칸 원값 + 값 칸, 빈칸 None) — 탭이 닫혔으면 열고 읽는다."""
    shell = _shell(host)
    if not shell or not shell.get("table"):
        _open_tab(app, PLAN_TAB if host == PLAN_HOST else YIELD_TAB)
    return shell_frame(last(_GRID["calls"], host))


def test_a_grid_mounts_once_its_tab_is_opened_and_resends_its_last_shell_when_hidden(
    seeded_database: Path,
) -> None:
    """한 번도 연 적 없는 탭은 그리드를 세우지 않는다(그리드 요소는 등록 JS · CSS 를 싣는다 — 생산
    계획 진입 전송량). 연 탭의 그리드는 탭이 닫혀도 같은 자리에 남고, 닫힌 회차에는 앞서 보낸 껍데기
    · feed 를 그대로 다시 보낸다(같은 dict — 해시 참조로 간다)."""
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    assert not list(app.exception)
    assert _shell(PLAN_HOST) is None and _shell(YIELD_HOST) is None

    _open_tab(app, PLAN_TAB)
    opened = _shell(PLAN_HOST)
    assert opened is not None and opened["table"] == "RQ_PKG_PLAN"
    assert _shell(YIELD_HOST) is None

    _open_tab(app, ":material/calculate: 환산")
    assert _shell(PLAN_HOST) == opened
    assert _shell(YIELD_HOST) is None


def _grid_edit(app: AppTest, host: str, cells: dict[int, dict[str, str]]) -> AppTest:
    """그리드 줄 번호 → {달: 적은 글} 을 그 그리드 출납으로 보낸다(빈 글은 빈칸)."""
    _grid(app, host)
    shell = last(_GRID["calls"], host)
    ops = [
        {"op": "write", "rows": [shell_key(shell, row)], "cols": [month], "values": [[text]]}
        for row, months in cells.items()
        for month, text in months.items()
    ]
    return send_ops(app, _GRID["calls"], *ops, host=host)


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
    """작업 줄의 「Excel 붙여넣기」 팝업을 열고 붙여넣어 대기 표로 올린다."""
    app.button(key="open_plan_paste").click().run()
    app.text_area(key="rq_pkg_plan_csv_clipboard").set_value(text)
    for button in app.button:
        if "붙여넣기 올리기" in str(button.label):
            button.click().run()
            break


def test_the_paste_button_says_what_each_table_does(seeded_database: Path) -> None:
    """PKG PLAN 은 대기 표로 올릴 뿐이고 수율은 바로 적용된다 — 단추 이름이 그 차이를 말한다."""
    labels = [
        ("open_plan_paste", "붙여넣기 올리기", "붙여넣기 적용"),
        ("open_yield_paste", "붙여넣기 적용", "붙여넣기 올리기"),
    ]
    for opener, shown, other in labels:
        app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
        app.button(key=opener).click().run()
        assert not list(app.exception)
        names = {str(button.label) for button in app.button}
        assert shown in names and other not in names


def test_a_staged_paste_blanks_the_zero_cells_like_the_plain_table(seeded_database: Path) -> None:
    """붙여넣기 대기 표의 달 칸은 글자로 온다 — 숫자로 읽지 않으면 0 가림이 듣지 않아, 양식을 그대로
    붙여넣기만 했는데 빈칸이던 칸이 0 으로 보여 값이 바뀐 것처럼 읽혔다. 그리드는 0 을 빈칸으로 싣고
    (2026-11-12 보드 답 k-a1), 적용하면 값은 그대로다."""
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    wide = pd.read_csv(StringIO(_clipboard_text(app, scale=1.0)), sep="\t", dtype="object")
    months = [column for column in wide.columns if column.isdigit()]
    filled = wide[months[0]].astype(float).gt(0).idxmax()
    plain_blanks = _grid(app, PLAN_HOST)[months].isna().to_numpy().sum()
    wide.loc[filled, months[0]] = "0.0"
    _paste(app, wide.to_csv(index=False, sep="\t"))
    assert not list(app.exception)

    shown = _grid(app, PLAN_HOST)
    assert shown[months].isna().to_numpy().sum() == plain_blanks + 1
    assert not shown[months].eq(0).to_numpy().any()

    app.button(key="apply_pkg_plan_changes").click().run()
    assert not list(app.exception)
    assert _applied(app, "PKG PLAN을 전역 계획값에 반영했습니다") == [APPLIED_ICON]


def test_the_plan_paste_window_calls_the_table_by_its_screen_name(seeded_database: Path) -> None:
    """화면에서 「PKG PLAN」 이라 부르는 표를 글 칸 이름 · 거부 알림도 같은 이름으로 부른다 — 내부
    표 이름은 왕복 양식의 파일 이름에만 남는다(설계 규칙 UI-CON-02)."""
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    _paste(app, "아무 글자\t값\n1\t2")
    assert not list(app.exception)

    assert app.text_area(key="rq_pkg_plan_csv_clipboard").label == "PKG PLAN 표 붙여넣기"
    (refused,) = flashed(app, "error")
    assert refused.value.startswith("PKG PLAN 입력 표의 열이 다운로드 양식과 다릅니다")


def _stack_field(app: AppTest) -> TextInput:
    """가상 제품 팝업의 Stack 칸 — 기준 제품마다 다른 위젯이라 라벨로 찾는다."""
    return next(field for field in app.text_input if field.label == "Stack")


def test_the_virtual_product_button_sits_in_the_more_menu_that_closes_when_picked(
    seeded_database: Path,
) -> None:
    """PKG PLAN 작업 줄은 「변경사항 적용」 · 「Excel 붙여넣기」 · 「⋯」(풍선 「더 보기」) 차례이고 「가상
    제품 등록」 은 「⋯」 안이다(2026-11-12 보드 답 n2 나). 메뉴 안 단추를 누르면 팝오버 key 세대가
    올라 다음 회차에 메뉴가 닫혀 선다 — 열린 채면 그 단추가 연 창 위에 메뉴가 떠 있다."""
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    app = _open_tab(app, PLAN_TAB)
    assert app.button(key="apply_pkg_plan_changes").label == "변경사항 적용"
    menus = [block for block in app.main.get("popover") if block.proto.popover.help == "더 보기"]
    assert len(menus) == 1 and menus[0].proto.popover.label == ""
    assert "pkg_plan_more_generation" not in app.session_state

    app.button(key="open_virtual_product").click().run()
    assert not list(app.exception)
    assert app.session_state["pkg_plan_more_generation"] == 1
    assert app.session_state["load_conversion_open_dialog"] == "virtual_product"


def test_the_stack_field_follows_the_chosen_source_product(seeded_database: Path) -> None:
    """폼 안이던 기준 제품을 바꿔도 Stack 칸이 첫 제품 값으로 남아, 그대로 누르면 기준과 다른 Stack
    으로 말없이 등록됐다. 고를 때마다 그 제품 값이 오고, 사람이 고친 값은 그대로 남는다.

    기준 제품마다 위젯이 달라야 한다 — 브라우저 폼은 제출 전 값을 위젯마다 들고 있어 같은 칸에
    서버가 값을 써도 미제출 값이 그대로 제출된다. AppTest 는 그 값을 재현하지 못해 key 로 본다."""
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    app.button(key="open_virtual_product").click().run()
    assert not list(app.exception)
    source = app.selectbox(key="virtual_product_source")
    stacks = [str(option).rsplit(" · ", 1)[1] for option in source.options]
    assert _stack_field(app).value == stacks[0]
    first_key = _stack_field(app).key
    other = next(index for index, stack in enumerate(stacks) if stack != stacks[0])

    source.set_value(other).run()
    assert not list(app.exception)
    assert _stack_field(app).value == stacks[other]
    assert _stack_field(app).key != first_key

    _stack_field(app).set_value("99H").run()
    assert _stack_field(app).value == "99H"
    app.selectbox(key="virtual_product_source").set_value(0).run()
    assert not list(app.exception)
    assert _stack_field(app).value == stacks[0]


def _register(app: AppTest, product: str, stack: str) -> None:
    """작업 줄의 「가상 제품 등록」 팝업을 열고 등록한다."""
    app.button(key="open_virtual_product").click().run()
    app.text_input(key="virtual_product_name").set_value(product)
    _stack_field(app).set_value(stack)
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
    assert any("PKG PLAN 탭에 올렸습니다" in item.value for item in successes(app))

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
    assert any(literal_markdown("DEMO_VIRTUAL_X") in item.value for item in successes(app))
    # 복제된 계획 달이 조회기간 안이면 새 제품은 표에 바로 선다 — 입력하라고 말한다.
    assert any("아래 표에서 계획 수량을 입력하세요" in item.value for item in successes(app))

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

    (notice,) = [item.value for item in successes(app) if "등록했습니다" in item.value]
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


def _download_labels(app: AppTest) -> list[str]:
    """화면에 선 내려받기 단추 글 — 그려진 차례다."""
    return [str(item.proto.label) for item in app.get("download_button")]


def _folds(app: AppTest) -> set[str]:
    """본문 펼침 이름 — 아이콘을 단 `st.expander` 는 AppTest 가 `status` 로 읽는다."""
    return {str(item.label) for item in app.expander} | {str(item.label) for item in app.status}


def _yield_rows(app: AppTest) -> pd.DataFrame:
    return pd.DataFrame(app.session_state["active_scenario"]["tables"]["RQ_YLD"]).reset_index(
        drop=True
    )


def _yield_values(frame: pd.DataFrame, product: str, month: int) -> list[float]:
    """그 제품·달 수율 행의 [EDS, BE]. 행이 없으면 빈 목록."""
    months = pd.to_numeric(frame["생산계획년월"])
    row = frame.loc[frame["제품정보"].eq(product) & months.eq(month), ["EDS_수율", "BE_수율"]]
    return [float(value) for value in row.to_numpy().ravel()]


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
    assert not [text for text in place_errors(app) if "RQ_YLD" in text]
    assert {
        "apply_pkg_plan_changes",
        "open_plan_paste",
        "open_virtual_product",
        "apply_yield_changes",
        "open_yield_paste",
    } <= _button_keys(app)
    # 뺀 행은 수율 탭이 열린 회차의 상태 알림 `ST-06` 과 그 줄의 「편집 불가 수율 행」 표가
    # 까닭(`사유`)과 함께 보인다(자리에 경고 상자 · 접힌 목록을 그리지 않는다 — 2026-11-05 사용자
    # 요청(검수표)). 계산에서 어떻게 되고 어떻게 고치는지는 `사유` 칸 머리 풍선이다(설계 규칙
    # UI-TXT-01 · 02). 처음 열린 탭은 환산이라 `ST-06` 은 내지 않고 환산 탭의 상태 알림
    # `ST-05`(환산에서 빠진 계획 — 기본 소요기준 PKG 는 수율을 쓰지 않아 없음)만 낸다.
    assert not any("표에서 값을 뺐습니다" in str(item.value) for item in app.caption)
    assert "편집 불가 수율 행" not in _folds(app)
    assert not app.warning
    codes = {str(note["code"]): note for note in alert_notes(app)}
    assert "ST-06" not in codes
    assert codes["ST-05"]["tab"] == "환산"
    app.session_state["load_conversion_active_tab"] = ":material/percent: 수율"
    app.run()
    (locked,) = [note for note in alert_notes(app) if note.get("code") == "ST-06"]
    assert locked["active"] is True and locked["level"] == "action" and locked["tab"] == "수율"
    assert "EDS·BE" in locked["short"]
    locked_table = note_table(locked, "편집 불가 수율 행")
    assert locked_table["total"] == 2 and "표에서 값을 뺐습니다" in locked_table["help"]["사유"]
    assert set(table_frame(locked_table)["제품정보"]) == {"DEMO PRODUCT A", "DEMO PRODUCT B"}

    # 뺀 행과 무관한 칸(첫 줄의 202601)을 그리드에서 고쳐 적용한다.
    app = _grid_edit(app, YIELD_HOST, {0: {"202601": "0.5"}})
    app.button(key="apply_yield_changes").click().run()
    assert not list(app.exception)
    assert any("활성 시나리오에 적용했습니다" in item.value for item in successes(app))

    applied = _yield_rows(app)
    assert len(applied) == len(source)
    eds_a, be_a = _yield_values(applied, "DEMO PRODUCT A", 202603)
    assert eds_a == pytest.approx(0.96) and pd.isna(be_a)
    assert _yield_values(applied, "DEMO PRODUCT B", 202604)[0] == 0.0
    january = _yield_values(applied, "DEMO PRODUCT A", 202601) + _yield_values(
        applied, "DEMO PRODUCT B", 202601
    )
    assert january.count(0.5) == 1


def test_the_excluded_plan_list_says_what_happened_in_its_column_tooltip(
    seeded_database: Path,
) -> None:
    """환산에서 빠진 계획의 목록은 상태 알림 `ST-05` 줄의 표다(2026-11-05 사용자 요청(검수표)) —
    고칠 곳과 빈 생산수량의 뜻은 `누락 기준정보` 칸 머리 풍선이고, 본문에 접힘 · 설명 문장을 두지
    않는다(설계 규칙 UI-TXT-01 · 02 · 04)."""
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    plan = pd.DataFrame(app.session_state["active_scenario"]["tables"]["RQ_PKG_PLAN"]).copy()
    plan["생산수량"] = plan["생산수량"].astype(float)
    plan.loc[plan.index[0], "생산수량"] = None
    _inject(app, "RQ_PKG_PLAN", plan, "blank-plan-quantity")

    assert not list(app.exception)
    excluded = active_state(app, "ST-05")
    assert excluded is not None and excluded["code"] == "ST-05"
    assert not any("계획 없음(0)으로 봤습니다" in str(item.value) for item in app.caption)
    assert "제외한 계획 확인" not in _folds(app)
    table = note_table(excluded, "제외한 계획")
    assert "기준정보를 채우면" in table["help"]["누락 기준정보"]
    assert "계획 없음(0)" in table["help"]["누락 기준정보"]
    assert table["file"].startswith("Capa_Conversion_Excluded_Plans_")
    assert "Alarm › 이 줄" in excluded["short"]
    # 다 실었으면 전체 CSV 단추는 서지 않는다 — 표의 「CSV 내려받기」 가 전체다.
    assert table["total"] == len(table["rows"])
    assert "앞 " not in excluded["full"]
    assert "제외한 계획 전체 CSV 다운로드" not in _download_labels(app)


def test_an_oversized_excluded_plan_list_stays_in_the_alarm_with_one_full_csv_at_the_tab_bottom(
    seeded_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """표가 `alerts.TABLE_ROW_LIMIT` 를 넘어도 목록은 Alarm 에서 본다(2026-11-05 사용자 요청 —
    「제외한 계획 확인은 알람으로」) — 줄의 표는 앞부분만이고 글이 「앞 n건 · 전체 m건」 과 전체
    자리를 말하며, 본문에는 접힘 · 표 없이 환산 탭 맨 아래 CSV 단추 하나만 서서 전체를 준다."""
    monkeypatch.setattr(alerts, "TABLE_ROW_LIMIT", 1)
    written: dict[str, bytes] = {}
    original = table_toolbar.render_csv_download

    def recorded(*, data: bytes, file_name: str, key: str | None = None, **kwargs: Any) -> None:
        written[file_name] = data
        original(data=data, file_name=file_name, key=key, **kwargs)

    monkeypatch.setattr(table_toolbar, "render_csv_download", recorded)
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    plan = pd.DataFrame(app.session_state["active_scenario"]["tables"]["RQ_PKG_PLAN"]).copy()
    plan["생산수량"] = plan["생산수량"].astype(float)
    plan.loc[plan.index[:2], "생산수량"] = None
    _inject(app, "RQ_PKG_PLAN", plan, "blank-plan-quantities")

    assert not list(app.exception)
    excluded = active_state(app, "ST-05")
    assert excluded is not None
    assert excluded["short"].endswith("목록: Alarm › 이 줄")
    table = note_table(excluded, "제외한 계획")
    assert len(table["rows"]) == 1 and table["total"] == 2
    # 패널의 줄 글은 두 줄까지만 보이므로 앞부분만 실었다는 말과 전체 자리가 맨 앞이다.
    assert excluded["full"].startswith(
        "Alarm 표는 앞 1건 · 전체 2건 — 전체는 환산 탭 맨 아래 「제외한 계획 전체 CSV 다운로드」"
    )
    assert "제외한 계획 확인" not in _folds(app)
    assert not any("누락 기준정보" in frame.value.columns for frame in app.main.dataframe)
    labels = _download_labels(app)
    assert labels.count("제외한 계획 전체 CSV 다운로드") == 1
    assert labels[-1] == "제외한 계획 전체 CSV 다운로드"
    # 단추는 앞부분이 아니라 전체를 준다(머리 줄 + 2행, 표와 같은 파일 이름).
    payload = written[table["file"]]
    assert payload.startswith(b"\xef\xbb\xbf")
    assert len(payload.decode("utf-8-sig").splitlines()) == 3


def _yield_tab_kinds(app: AppTest) -> list[str]:
    """수율 탭 안 맨 위 차례의 요소 종류 — 탭 이름 끝이 수율인 칸 하나다."""
    (tab,) = [tab for tab in app.tabs if str(tab.label).endswith("수율")]
    return [str(child.type) for child in tab.children.values()]


def test_an_oversized_locked_yield_list_stays_in_the_alarm_with_one_full_csv_at_the_tab_bottom(
    seeded_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """표가 `alerts.TABLE_ROW_LIMIT` 를 넘어도 편집 불가 수율 행은 Alarm 에서 본다 — 줄의 표는
    앞부분만이고 글이 「앞 n건 · 전체 m건」 과 전체 자리를 말하며, 본문에는 접힘 · 표 없이 수율 탭
    맨 아래 CSV 단추 하나만 서서 전체를 준다. 단추는 그 탭이 열린 회차에만 선다."""
    monkeypatch.setattr(alerts, "TABLE_ROW_LIMIT", 1)
    written: dict[str, bytes] = {}
    original = table_toolbar.render_csv_download

    def recorded(*, data: bytes, file_name: str, key: str | None = None, **kwargs: Any) -> None:
        written[file_name] = data
        original(data=data, file_name=file_name, key=key, **kwargs)

    monkeypatch.setattr(table_toolbar, "render_csv_download", recorded)
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    source = _yield_rows(app)
    months = pd.to_numeric(source["생산계획년월"])
    broken = source.copy()
    broken.loc[broken["제품정보"].eq("DEMO PRODUCT A") & months.eq(202603), "BE_수율"] = None
    broken.loc[broken["제품정보"].eq("DEMO PRODUCT B") & months.eq(202604), "BE_수율"] = None
    _inject(app, "RQ_YLD", broken, "two-locked-yield-rows")

    assert not list(app.exception)
    label = "편집 불가 수율 행 전체 CSV 다운로드"
    # 환산 탭이 열린 회차에는 수율 탭의 알림 · 단추를 세우지 않는다.
    assert active_state(app, "ST-06") is None
    assert label not in _download_labels(app)

    app.session_state["load_conversion_active_tab"] = ":material/percent: 수율"
    app.run()
    assert not list(app.exception)
    locked = active_state(app, "ST-06")
    assert locked is not None
    table = note_table(locked, "편집 불가 수율 행")
    assert len(table["rows"]) == 1 and table["total"] == 2
    # 패널의 줄 글은 두 줄까지만 보이므로 앞부분만 실었다는 말과 전체 자리가 맨 앞이다.
    assert locked["full"].startswith(
        f"Alarm 표는 앞 1건 · 전체 2건 — 전체는 수율 탭 맨 아래 「{label}」로 받습니다."
    )
    assert "Alarm › 이 줄 「편집 불가 수율 행」" in locked["full"]
    assert "편집 불가 수율 행" not in _folds(app)
    assert not any("사유" in frame.value.columns for frame in app.main.dataframe)
    assert _download_labels(app) == [label]
    # 수율 탭의 맨 끝이 단추다 — 편집표 아래.
    assert _yield_tab_kinds(app)[-1] == "download_button"
    # 단추는 앞부분이 아니라 전체를 준다(머리 줄 + 2행, 표와 같은 파일 이름 · 칸).
    payload = written[table["file"]]
    assert payload.startswith(b"\xef\xbb\xbf")
    lines = payload.decode("utf-8-sig").splitlines()
    assert len(lines) == 3
    assert lines[0].split(",") == list(table["columns"])


def test_both_oversized_lists_keep_their_own_csv_on_their_own_tab(
    seeded_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """제외한 계획과 편집 불가 수율 행이 함께 크면 전체 CSV 단추는 제 탭에 하나씩만 서고, Alarm 의
    두 줄 글은 제 탭을 이름으로 부른다 — 두 줄이 한 Alarm 에 함께 서도 어느 탭인지 헷갈리지
    않는다."""
    monkeypatch.setattr(alerts, "TABLE_ROW_LIMIT", 1)
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    plan = pd.DataFrame(app.session_state["active_scenario"]["tables"]["RQ_PKG_PLAN"]).copy()
    plan["생산수량"] = plan["생산수량"].astype(float)
    plan.loc[plan.index[:2], "생산수량"] = None
    _inject(app, "RQ_PKG_PLAN", plan, "blank-plan-quantities")
    source = _yield_rows(app)
    months = pd.to_numeric(source["생산계획년월"])
    broken = source.copy()
    broken.loc[broken["제품정보"].eq("DEMO PRODUCT A") & months.eq(202603), "BE_수율"] = None
    broken.loc[broken["제품정보"].eq("DEMO PRODUCT B") & months.eq(202604), "BE_수율"] = None
    _inject(app, "RQ_YLD", broken, "two-locked-yield-rows")

    assert not list(app.exception)
    excluded = active_state(app, "ST-05")
    assert excluded is not None and "환산 탭 맨 아래" in excluded["full"]
    assert _download_labels(app)[-1] == "제외한 계획 전체 CSV 다운로드"
    assert "편집 불가 수율 행 전체 CSV 다운로드" not in _download_labels(app)

    app.session_state["load_conversion_active_tab"] = ":material/percent: 수율"
    app.run()
    assert not list(app.exception)
    locked = active_state(app, "ST-06")
    assert locked is not None and "수율 탭 맨 아래" in locked["full"]
    assert _download_labels(app) == ["편집 불가 수율 행 전체 CSV 다운로드"]

    app.session_state["load_conversion_active_tab"] = ":material/calculate: 환산"
    app.run()
    assert not list(app.exception)
    assert _download_labels(app)[-1] == "제외한 계획 전체 CSV 다운로드"
    assert "편집 불가 수율 행 전체 CSV 다운로드" not in _download_labels(app)


def test_a_small_locked_yield_list_has_no_full_csv_button(seeded_database: Path) -> None:
    """다 실었으면 전체 CSV 단추는 서지 않는다 — 표의 「CSV 내려받기」 가 전체다."""
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    source = _yield_rows(app)
    months = pd.to_numeric(source["생산계획년월"])
    broken = source.copy()
    broken.loc[broken["제품정보"].eq("DEMO PRODUCT A") & months.eq(202603), "BE_수율"] = None
    _inject(app, "RQ_YLD", broken, "one-locked-yield-row")
    app.session_state["load_conversion_active_tab"] = ":material/percent: 수율"
    app.run()

    assert not list(app.exception)
    locked = active_state(app, "ST-06")
    assert locked is not None
    table = note_table(locked, "편집 불가 수율 행")
    assert table["total"] == len(table["rows"]) == 1
    assert "앞 " not in locked["full"]
    assert "편집 불가 수율 행 전체 CSV 다운로드" not in _download_labels(app)


def test_a_yield_source_that_cannot_build_a_table_stops_only_the_yield_tab(
    seeded_database: Path,
) -> None:
    """연결 키가 겹쳐 수율 표를 세울 수 없으면 수율 탭에만 오류가 뜨고 PKG PLAN 은 선다."""
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    source = _yield_rows(app)
    _inject(app, "RQ_YLD", pd.concat([source, source.iloc[[0]]]), "duplicated-yield")

    assert not list(app.exception)
    assert any("수율 표를 만들지 못했습니다" in text for text in data_error_texts(app))
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
        if "붙여넣기 적용" in str(button.label):
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
    messages = [item.value for item in successes(app)]
    assert any("2칸을 비워 그 달 수율 행을 지웠습니다" in message for message in messages)
    assert any("환산에서 빠집니다" in message for message in messages)


def test_a_yield_paste_that_blanks_nothing_adds_no_removal_note(seeded_database: Path) -> None:
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()

    _paste_yield(app, _yield_clipboard_text(app))
    assert not list(app.exception)

    messages = [item.value for item in successes(app)]
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
    app = _grid_edit(app, YIELD_HOST, {int(index): {month: ""} for index in target.index})
    app.button(key="apply_yield_changes").click().run()

    assert not list(app.exception)
    assert len(_yield_rows(app)) == before - 1
    messages = [item.value for item in successes(app)]
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
    messages = [item.value for item in successes(app)]
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
    """수율 그리드에 실린 표(탭이 닫혔으면 연다)."""
    return _grid(app, YIELD_HOST)


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
    errors = [text for text in data_error_texts(app) if "RQ_YLD" in text]
    assert len(errors) == 1, errors
    assert "202604 · DEMO PRODUCT B" in errors[0]
    assert "EDS 0(0%)" in errors[0]
    assert "수율 탭에서 그 달의 EDS·BE 를 둘 다 고쳐 적용하세요" in errors[0]
    # 그 행이 계산을 멈춘다는 뜻은 「편집 불가 수율 행」 표(수율 탭의 `ST-06`) `사유` 칸 머리 풍선이
    # 말한다.
    app.session_state["load_conversion_active_tab"] = ":material/percent: 수율"
    app.run()
    locked = active_state(app, "ST-06")
    assert locked is not None
    guide = note_table(locked, "편집 불가 수율 행")["help"]["사유"]
    assert "편집 불가" in guide and "HOME·소요대수·확보율 계산을 멈춥니다" in guide


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
    assert any("RQ_YLD" in text for text in data_error_texts(app))

    grid = _yield_grid(app)
    b_rows = grid.loc[grid["제품정보"].eq("DEMO PRODUCT B")]
    assert sorted(b_rows["수율 구분"]) == ["BE", "EDS"]
    months = [column for column in grid.columns if str(column).isdigit()]
    assert b_rows[months].isna().all(axis=None)

    app = _grid_edit(
        app,
        YIELD_HOST,
        {
            int(index): {month: ("0.9" if kind == "EDS" else "0.95") for month in months}
            for index, kind in zip(b_rows.index, b_rows["수율 구분"], strict=True)
        },
    )
    app.button(key="apply_yield_changes").click().run()

    assert not list(app.exception)
    assert not [text for text in place_errors(app) if "RQ_YLD" in text]
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
    assert any("활성 시나리오에 적용했습니다" in item.value for item in successes(app))
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
        item.value for item in successes(app) if literal_markdown("DEMO_VIRTUAL_Z") in item.value
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
# 그리드 줄 0 의 한 칸 편집 — (그리드, 달, 적은 글).
PLAN_CELL_EDIT = (PLAN_HOST, "202602", "200")
YIELD_CELL_EDIT = (YIELD_HOST, "202603", "0.9")


def _sidebar_probe_script(database_path: Path) -> str:
    """회차마다 페이지 **앞에서** 「적용 전 편집」 목록을 적어 두는 스크립트.

    `app.py` 는 `pending_edit_labels` 를 `navigation.run()` 전에 부르고, 변경 칩 · 판과 저장
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


def _cell_edit(app: AppTest, edit: tuple[str, str, str]) -> AppTest:
    host, month, text = edit
    return _grid_edit(app, host, {0: {month: text}})


def _drafted(app: AppTest, table: str) -> bool:
    from capa_simulation.plan_grid_keys import cells_key

    draft = app.session_state[cells_key(table)] if cells_key(table) in app.session_state else None
    return bool(isinstance(draft, dict) and draft.get("cells"))


@pytest.mark.parametrize(
    ("applied_edit", "apply_button", "applied_table", "other_edit", "other_table", "other_label"),
    [
        (
            PLAN_CELL_EDIT,
            "apply_pkg_plan_changes",
            "RQ_PKG_PLAN",
            YIELD_CELL_EDIT,
            "RQ_YLD",
            "생산 계획 · 수율",
        ),
        (
            YIELD_CELL_EDIT,
            "apply_yield_changes",
            "RQ_YLD",
            PLAN_CELL_EDIT,
            "RQ_PKG_PLAN",
            "생산 계획 · PKG PLAN",
        ),
    ],
    ids=["pkg-plan", "yield"],
)
def test_applying_one_table_leaves_only_the_other_tables_edit_pending(
    seeded_database: Path,
    applied_edit: tuple[str, str, str],
    apply_button: str,
    applied_table: str,
    other_edit: tuple[str, str, str],
    other_table: str,
    other_label: str,
) -> None:
    """한 표를 적용한 다음 회차에 사이드바가 보는 목록은 **다른 표의 적용 전 편집** 뿐이다.

    사이드바는 페이지보다 먼저 돌아, 방금 적용한 표를 그 회차 동안 「적용 전 편집」으로 세고 저장을
    잠갔다(2026-10-01 브라우저 E2E). 그리드 초안은 세션 칸이라 다른 표를 적용해도 남고, 적용한 표는
    사이드바가 빼고 센다(`mark_own_change`).
    """
    app = AppTest.from_string(_sidebar_probe_script(seeded_database), default_timeout=300)
    app.run()
    assert not list(app.exception)
    app = _cell_edit(app, other_edit)
    app.run()
    assert app.session_state[PRE_PAGE_LOG_KEY][-1] == [other_label]
    app = _cell_edit(app, applied_edit)
    before_token = app.session_state["active_scenario"]["content_token"]
    runs_before = len(app.session_state[PRE_PAGE_LOG_KEY])

    app.button(key=apply_button).click().run()
    assert not list(app.exception)
    assert app.session_state["active_scenario"]["content_token"] != before_token

    # 누른 회차와 적용 뒤 `st.rerun()` 회차. 사용자가 보는 사이드바는 뒤 회차의 것이다.
    runs = app.session_state[PRE_PAGE_LOG_KEY][runs_before:]
    assert len(runs) == 2
    assert runs[-1] == [other_label]
    # 다른 표의 초안은 그대로 남아 탭 점·작업 줄이 계속 선다.
    assert _drafted(app, other_table)
    assert not _drafted(app, applied_table)

    # 다음 조작에서도 목록이 바뀌지 않는다 — 저장을 누른 회차에 경고가 새로 솟지 않는다.
    app.run()
    assert app.session_state[PRE_PAGE_LOG_KEY][-1] == [other_label]


def test_the_plan_grid_shows_zero_as_blank_and_takes_a_cleared_cell_as_zero(
    seeded_database: Path,
) -> None:
    """PKG PLAN 그리드는 0 칸을 빈칸으로 싣고(천 단위 · 소수 없이 · 0 이상), 칸을 비우면 적용 때 0
    이다(2026-11-12 보드 답 k-a1). 수율 그리드는 % 로 보이고 100% 를 넘으면 틀린 칸이다(k-a2)."""
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    shown = _grid(app, PLAN_HOST)
    months = [column for column in shown.columns if str(column).isdigit()]
    assert not shown[months].eq(0).to_numpy().any()
    shell = last(_GRID["calls"], PLAN_HOST)
    assert shell["fmt"]["kind"] == "fixed" and shell["fmt"]["digits"] == 0
    assert shell["fmt"]["min"] == 0.0 and not shell["fmt"]["blankZero"]
    assert [column["label"] for column in shell["keyCols"]][:2] == ["양산", "제품"]
    row = int(shown[months[0]].notna().to_numpy().argmax())
    product = str(shown.iloc[row]["제품정보"])

    app = _grid_edit(app, PLAN_HOST, {row: {months[0]: ""}})
    app.button(key="apply_pkg_plan_changes").click().run()
    assert not list(app.exception)
    plan = pd.DataFrame(app.session_state["active_scenario"]["tables"]["RQ_PKG_PLAN"])
    cleared = plan.loc[
        plan["제품정보"].eq(product) & pd.to_numeric(plan["생산계획년월"]).eq(int(months[0])),
        "생산수량",
    ]
    assert 0.0 in cleared.astype(float).tolist()

    _grid(app, YIELD_HOST)
    yields = last(_GRID["calls"], YIELD_HOST)
    assert yields["fmt"]["kind"] == "percent" and yields["fmt"]["max"] == 1.0


def _plan_grid_total(app: AppTest) -> float:
    """PKG PLAN 그리드에 실린 표(원본)의 월 칸 합계."""
    shown = _grid(app, PLAN_HOST)
    months = [column for column in shown.columns if str(column).isdigit()]
    return float(shown[months].apply(pd.to_numeric).sum().sum())


def _plan_grid_path(app: AppTest) -> tuple[int, ...]:
    """PKG PLAN 그리드 칸(`pkg_plan_grid_box`)의 델타 경로(본문 기준 자식 번호 차례)."""
    found: list[tuple[int, ...]] = []

    def walk(node: Any, path: tuple[int, ...]) -> None:
        if isinstance(node, Block) and node.key == "pkg_plan_grid_box":
            found.append(path)
        for index, child in getattr(node, "children", {}).items():
            walk(child, (*path, index))

    walk(app.main, ())
    assert len(found) == 1, found
    return found[0]


def test_the_plan_notices_stand_in_one_slot_above_the_editor(
    seeded_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """붙여넣기·적용 알림은 작업 줄 아래 늘 서 있는 칸에 선다 — 생기고 빠져도 PKG PLAN 그리드의
    자리가 그대로다. 두 동작은 `st.rerun()` 으로 끊기고 다음 회차에 알림이 생기므로, 밀리면
    브라우저에 옛 편집표의 흐린 사본이 남는다(AGENTS 9장 「조건부 알림」). 여기서는 그 원인인 자리
    밀림을 잰다. 알림이 빠지는 회차를 보려고 쓰기 알림 표지의 창은 0 으로 둔다(창 안의 회차는 알림을
    다시 그린다 — 아래 두 번 누름 시험)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    assert not list(app.exception)
    app = _open_tab(app, PLAN_TAB)
    before = _plan_grid_path(app)

    _paste(app, _clipboard_text(app, scale=0.5))
    assert any("붙여넣기 표를 PKG PLAN 탭에 올렸습니다" in item.value for item in successes(app))
    assert _plan_grid_path(app) == before

    app.button(key="apply_pkg_plan_changes").click().run()
    assert not list(app.exception)
    assert any("PKG PLAN을 전역 계획값에 반영했습니다" in item.value for item in successes(app))
    assert _plan_grid_path(app) == before

    app.run()
    assert not any("반영했습니다" in item.value for item in successes(app))
    assert _plan_grid_path(app) == before


def test_the_apply_notice_says_how_much_demand_the_required_count_leaves_out(
    seeded_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PKG PLAN 적용 알림이 서는 회차에 소요대수에 들지 않은 수요(시나리오 전체 기간)를 상태 알림
    `ST-04` 로 낸다 — 경로 없는 칸에 넣은 계획은 「다시 계산됩니다」 뒤에도 소요대수에 들지
    않는다(E2E r2 static, 개선 I38). 셈은 저장·발행 검사와 같은 `required_exclusion_counts`
    다(페이지는 exec 때 이름을 집으므로 모듈 속성을 바꾸면 그 셈이 들어간다). 자리에 그리지 않아
    편집표 자리가 밀리지 않고, 적용 알림이 빠지는 회차에는 내지 않는다(쓰기 알림 표지의 창은
    0 으로 둔다). 셈은 편집표를 그린 **뒤**다 — 시나리오 전체 기간 계산이 끝날 때까지 편집표가
    서지 않으면 적용 직후 다음 편집을 기다리게 한다(그 회차의 그리기 차례를 적어 본다). 계획 쪽
    건수만 싣는다 — 경로 쪽(대당 Capa 가 없어 뺀 부하 경로)은 계획을 고치지 않아도 늘 있을 수 있어
    적용할 때마다 서는 경고가 된다. 적용 알림이 없는 회차도 그 자리에서 이벤트 칸 한 자리를 써(빈
    표지) 뒤 수율 붙여넣기 팝업의 이벤트 칸 자리가 회차마다 같다."""
    import capa_simulation.services.required_equipment as required_equipment
    from capa_simulation.components import plan_grid

    seen: list[int] = []
    order: list[str] = []
    draw_grid = plan_grid.render_grid

    def counted(frame: pd.DataFrame) -> required_equipment.RequiredExclusionCounts:
        seen.append(len(frame))
        order.append("셈")
        return required_equipment.RequiredExclusionCounts(unrouted_loads=3, excluded_routes=5)

    def recorded_grid(table: str, grid: Any, *, hidden: bool = False) -> None:
        if table == "RQ_PKG_PLAN":
            order.append("편집표")
        draw_grid(table, grid, hidden=hidden)

    monkeypatch.setattr(required_equipment, "required_exclusion_counts", counted)
    monkeypatch.setattr(plan_grid, "render_grid", recorded_grid)
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    assert not list(app.exception)
    app = _open_tab(app, PLAN_TAB)
    before = _plan_grid_path(app)
    assert not _st04(app)

    _paste(app, _clipboard_text(app, scale=0.5))
    app.button(key="apply_pkg_plan_changes").click().run()
    assert not list(app.exception)
    assert any("PKG PLAN을 전역 계획값에 반영했습니다" in item.value for item in successes(app))
    assert not any("소요대수에 들지 않은 수요" in str(item.value) for item in app.warning)
    (note,) = _st04(app)
    assert note["active"] is True and note["tab"] == "PKG PLAN"
    assert "소요대수에 들지 않은 수요가 있습니다(시나리오 전체 기간)" in note["full"]
    assert "RQ_REQB 경로에 닿지 않은 계획 부하 3건" in note["full"]
    assert "대당 Capa 가 없어 뺀 부하 경로" not in note["full"]
    assert seen, "적용 뒤 소요대수 결과를 세지 않았다"
    # 알림이 서는 회차의 셈은 그 회차 그리드 뒤다(앞이면 「셈, 편집표」 로 끝난다).
    assert order[-2:] == ["편집표", "셈"], order
    assert _plan_grid_path(app) == before
    applied_slots = len(app.get("html"))

    # 적용 알림과 함께 빠진다(이 셈은 적용 알림이 서는 회차에만 한다). 그 자리는 빈 표지로 남는다.
    app.run()
    assert not any("반영했습니다" in item.value for item in successes(app))
    assert not _st04(app)
    assert _plan_grid_path(app) == before
    assert len(app.get("html")) == applied_slots


def _st04(app: AppTest) -> list[dict[str, Any]]:
    """PKG PLAN 적용 뒤 소요대수에 들지 않은 수요 상태 알림(`ST-04`) 표지."""
    return [note for note in alert_notes(app) if note.get("code") == "ST-04"]


def test_the_plan_editor_shows_the_applied_plan_right_after_apply(seeded_database: Path) -> None:
    """그리드 원본은 (시나리오 내용·편집 기간·표시순서) 키 캐시다. 적용이 새 토큰을 내므로 바로 다음
    회차 그리드가 새 계획을 보인다 — 옛 원본이 남으면 다음 적용에서 값이 되돌아간다."""
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
    return [item.icon for item in successes(app) if text in str(item.value)]


def test_a_locked_apply_button_says_why_and_an_open_one_says_what_it_does(
    seeded_database: Path,
) -> None:
    """잠긴 동안 풍선은 까닭이고 눌리면 하는 일이다 — 「적용해야 반영된다」 는 눌리는 단추에 남는다
    (설계 규칙 UI-INP-07)."""
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    for key in ("apply_pkg_plan_changes", "apply_yield_changes"):
        button = app.button(key=key)
        assert button.disabled
        assert button.proto.help == "고친 칸이 있으면 누를 수 있습니다."

    app = _cell_edit(app, PLAN_CELL_EDIT)
    app = _cell_edit(app, YIELD_CELL_EDIT)
    assert not list(app.exception)

    assert not app.button(key="apply_pkg_plan_changes").disabled
    assert "이 계획으로 다시 계산됩니다" in app.button(key="apply_pkg_plan_changes").proto.help
    assert not app.button(key="apply_yield_changes").disabled
    assert "이 수율로 다시 계산됩니다" in app.button(key="apply_yield_changes").proto.help


def test_the_plan_apply_notice_survives_a_second_press_on_the_locked_button(
    seeded_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PKG PLAN 「변경사항 적용」 을 0.3~0.35초 간격으로 두 번 누르면 적용은 되는데 성공 알림이
    사라졌다(2026-10-27 E2E 3/4). 둘째 누름은 적용 뒤 잠긴 단추에 닿아 버려지고, 그 회차가 화면을
    다시 그리며 앞 회차가 꺼내 그린 알림을 지웠다. 쓰기 직후 적어 둔 알림 표지로 창 안의 회차가 같은
    아이콘으로 다시 그린다 — 창이 지난 회차는 그리지 않는다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    _paste(app, _clipboard_text(app, scale=0.5))
    app.button(key="apply_pkg_plan_changes").click().run()
    assert not list(app.exception)
    assert _applied(app, "PKG PLAN을 전역 계획값에 반영했습니다") == [APPLIED_ICON]
    # 글 속 달 구간은 표 머리가 아니라 결과 표 꼴이다(`month_label` — AGENTS 8장).
    assert _applied(app, f"{month_label(202601)}–{month_label(202612)} 구간의 환산") == [
        APPLIED_ICON
    ]
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
    app = _grid_edit(app, YIELD_HOST, {0: {month: "0.5"}})
    app.button(key="apply_yield_changes").click().run()
    assert not list(app.exception)
    assert _applied(app, "수율 편집값을 활성 시나리오에 적용했습니다") == [APPLIED_ICON]

    app.run()
    assert not list(app.exception)
    assert _applied(app, "수율 편집값을 활성 시나리오에 적용했습니다") == [APPLIED_ICON]
