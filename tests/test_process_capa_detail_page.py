# Purpose: 공정 Capa 상세 화면의 진입·공정 왕복·펼침·달 고르기·설비 일정 구획·CSV·탭 링크를 본다.

"""공정 Capa 상세 화면(AppTest).

페이지만 띄운다(`test_all_pages_render` 와 같은 하네스 — 내장 시드를 임시 DuckDB 에 부트스트랩).
HOME 칸 클릭과 월 그림의 칸 선택은 AppTest 가 재현하지 못하므로 콜백이 남기는 것(전달 칸·주소
인자·세션 달)을 넣고 돌린다(`tests/test_process_detail_state.py`·`tests/test_process_capa_view.py`
가 콜백 쪽을 본다).

- 설비 DB 가 빈 하네스는 「설비 일정 없음: 저장본 없음」 마크와 ① 공식 기준만 선다.
- 설비 일정은 시드 공정 하나(`DEMO_Chip_Attach`)에 저장본·Cut-off 를 넣은 따로 된 하네스로 본다.
- 칸 누름·◀▶ 는 **진짜 프래그먼트 회차**(`tests/fragment_browser.py`)로 본문 프래그먼트만 도는지,
  그 회차가 이벤트 칸에 앱 전체 회차와 같은 수를 쓰는지 본다.
"""

from __future__ import annotations

import io
import json
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from alert_marks import active_state, data_error_marks, data_error_texts, events
from fragment_browser import install_fragment_browser
from streamlit.proto.RootContainer_pb2 import RootContainer
from streamlit.testing.v1 import AppTest
from test_required_shortening import _cutoff, _downtime, _master, _unit
from xlsx_read import read_workbook

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.page_guide import load_guide
from capa_simulation.components.process_capa_canvas import (
    SECTION_DOWNTIME,
    SECTION_DYNAMIC,
    SECTION_IDS,
    SECTION_SUMMARY,
    SECTION_UNITS,
)
from capa_simulation.components.process_capa_view import (
    DOWNLOAD_STYLE,
    DYNAMIC_DB_ERROR_TITLE,
    DYNAMIC_ERROR_TITLE,
    EVIDENCE_SHORTENING_BUTTON_KEY,
    INVESTMENT_BADGE,
    NEXT_MONTH_KEY,
    SECTIONS_HELP,
    SHEET_XLSX_KEY,
    SHORTENING_TAB_LINK_KEY,
    SHOW_ALL_UNITS_KEY,
    UNITS_CSV_KEY,
    step_button_label,
)
from capa_simulation.components.process_capa_workbook import DETAIL_SHEET, UNITS_SHEET
from capa_simulation.components.process_field import CONTEXT_KEY as PROCESS_CONTEXT_KEY
from capa_simulation.components.process_field import FIELD_KEY as PROCESS_FIELD_KEY
from capa_simulation.components.required_shortening_panel import SHORTENING_PROCESS_KEY
from capa_simulation.components.shortening_board import (
    HIGHLIGHT_FROM_DETAIL,
    SHORTENING_HIGHLIGHT_KEY,
)
from capa_simulation.home_state import EXECUTION_TOGGLE_KEY
from capa_simulation.navigation import (
    AVAILABLE_EQUIPMENT_STATUS,
    CONSTRAINT_SIMULATION,
    PROCESS_CAPA_DETAIL,
)
from capa_simulation.page_tabs_state import tab_label
from capa_simulation.persistence.cache import (
    clear_global_execution_capacity_cache,
    clear_global_process_rename_cache,
    clear_global_securement_threshold_cache,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.process_detail_state import (
    HOME_BOTTLENECK_SECTION,
    ORIGIN_BAND_ICON,
    PROCESS_DETAIL_CANVAS_CHART_KEY,
    PROCESS_DETAIL_EXPAND_KEY,
    PROCESS_DETAIL_MONTH_KEY,
    PROCESS_DETAIL_NEXT_PROCESS_KEY,
    PROCESS_DETAIL_PREVIOUS_PROCESS_KEY,
    PROCESS_DETAIL_PROCESS_KEY,
    PROCESS_DETAIL_PRODUCT_FILTER_KEY,
    PROCESS_DETAIL_REQUEST_KEY,
    PROCESS_DETAIL_SECTIONS_KEY,
    PROCESS_DETAIL_SPLIT_KEY,
    PROCESS_DETAIL_VIEW_FRAGMENT_KEY,
    SHORTENING_BAND_HELP,
    ProcessDetailRequest,
    ProcessStep,
    shortening_card_query_params,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.required_shortening import UNIT_EXPORT_COLUMNS
from capa_simulation.upeh_assumption_state import (
    UPEH_ASSUMPTION_END_KEY,
    UPEH_ASSUMPTION_PERCENT_KEY,
    UPEH_ASSUMPTION_START_KEY,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / PROCESS_CAPA_DETAIL.path
DYNAMIC_PROCESS = "DEMO_Chip_Attach"
OFFICIAL_BADGE = "공식 · Core Data"


def _page_script(database_path: Path, equipment_path: Path, *, fail_bootstrap: bool = False) -> str:
    """`fail_bootstrap` 이면 공통 진입(`load_page_context`)이 오류를 내는 회차를 흉내 낸다.

    내려받기 단추는 받은 바이트를 세션 `captured_downloads` 에 적어 둔다(시험이 CSV 를 읽는다).
    페이지 링크(`st.page_link`)는 인자를 세션 `captured_page_links` 에 적은 뒤 원본을 부른다 — 단독
    실행의 물러섬 캡션(「사이드바에서 …」)은 그대로 선다.
    """
    return f"""
from datetime import date
from pathlib import Path

import streamlit as st

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.components.month_range_picker as month_range_picker
import capa_simulation.components.upeh_assumption_controls as upeh_controls
import capa_simulation.page_bootstrap as page_bootstrap
import capa_simulation.settings as settings

original_database_path = settings.DUCKDB_PATH
original_equipment_path = settings.EQUIPMENT_DUCKDB_PATH
original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
original_month_picker = month_range_picker.render_month_range_apply
original_load_page_context = page_bootstrap.load_page_context
original_download_button = st.download_button
original_page_link = st.page_link
original_upeh_options = upeh_controls.assumption_month_options

settings.DUCKDB_PATH = Path({str(database_path)!r})
settings.EQUIPMENT_DUCKDB_PATH = Path({str(equipment_path)!r})
horizontal_scrollbar.render_horizontal_scrollbar = lambda *args, **kwargs: None
month_range_picker.render_month_range_apply = (
    lambda *, start, end, min_month, max_month, key, this_month=None: None
)
# UPEH 적용 구간의 선택지는 「이번 달 이후」 다 — 시드(2026년) 달이 날짜에 따라 빠지지 않게
# 오늘을 박는다.
upeh_controls.assumption_month_options = lambda start, end, *, today: original_upeh_options(
    start, end, today=date(2026, 1, 1)
)


def _failing_page_context():
    raise ValueError("시험용 진입 오류")


def _recording_download_button(label, *args, **kwargs):
    st.session_state.setdefault("captured_downloads", {{}})[kwargs.get("key")] = {{
        "data": kwargs.get("data"),
        "file_name": kwargs.get("file_name"),
    }}
    return original_download_button(label, *args, **kwargs)


def _recording_page_link(page, *args, **kwargs):
    st.session_state.setdefault("captured_page_links", []).append({{"page": str(page), **kwargs}})
    return original_page_link(page, *args, **kwargs)


if {fail_bootstrap!r}:
    page_bootstrap.load_page_context = _failing_page_context
st.download_button = _recording_download_button
st.page_link = _recording_page_link
st.session_state["captured_page_links"] = []

try:
    from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
    from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

    bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
    apply_pending_scenario_preset()

    source = Path({str(PAGE)!r})
    exec(
        compile(source.read_text(encoding="utf-8"), str(source), "exec"),
        {{"__name__": "__main__"}},
    )
finally:
    settings.DUCKDB_PATH = original_database_path
    settings.EQUIPMENT_DUCKDB_PATH = original_equipment_path
    horizontal_scrollbar.render_horizontal_scrollbar = original_scrollbar
    month_range_picker.render_month_range_apply = original_month_picker
    page_bootstrap.load_page_context = original_load_page_context
    st.download_button = original_download_button
    st.page_link = original_page_link
    upeh_controls.assumption_month_options = original_upeh_options
"""


@pytest.fixture(scope="module")
def databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """내장 시드 부트스트랩은 멱등이라 모듈 안에서 DuckDB 두 개를 다시 쓴다. 설비 DB 는 빈 채다."""
    root = tmp_path_factory.mktemp("process_capa_detail")
    return root / "scenario.duckdb", root / "equipment.duckdb"


@pytest.fixture(scope="module")
def dynamic_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """시드 공정 하나에 설비 저장본·Cut-off 를 넣은 하네스 — 설비 일정 구획이 선다.

    기존보유가 없고 신규 호기 둘의 Qual 이 축 끝 무렵이라, 그 앞 달은 설비 일정 기준 가용이 0 이다
    (목표 미달 → 단축 계획). 한 호기에는 비가동을 둬 ④ 화살표가 선다. 오늘(실제 날짜)이 축을 지나면
    모든 달이 「기한 지남」이 되지만 구획은 그대로 선다 — 시험은 개수를 단언하지 않는다.
    """
    root = tmp_path_factory.mktemp("process_capa_detail_dynamic")
    equipment_path = root / "equipment.duckdb"
    repository = DuckDBEquipmentRepository(equipment_path)
    repository.initialize()
    master = _master(
        [
            _unit("DA-01", date(2026, 12, 10), process=DYNAMIC_PROCESS, arrival=date(2026, 11, 1)),
            _unit("DA-02", date(2027, 1, 20), process=DYNAMIC_PROCESS, arrival=date(2026, 12, 1)),
        ]
    )
    baseline = pd.DataFrame(columns=["공정", "분류", "기존보유대수", "비고"])
    repository.save_snapshot(
        baseline, master, _downtime([("DA-01", date(2026, 12, 20), date(2026, 12, 24))])
    )
    repository.save_process_cutoff(_cutoff(10, DYNAMIC_PROCESS))
    return root / "scenario.duckdb", equipment_path


def _app(databases: tuple[Path, Path], *, fail_bootstrap: bool = False) -> AppTest:
    return AppTest.from_string(
        _page_script(*databases, fail_bootstrap=fail_bootstrap), default_timeout=300
    )


class _ProcessBox:
    """공정 값 칸(하나 고름 — 공용 공정 칸, 2026-11-08)을 예전 상자처럼 읽는다. 값은 세션 칸,
    선택지는 팝업이 쓸 이 화면의 선택지이고, 고르기는 세션 칸에만 적는다(◀▶ 넘김과 같은 길 —
    팝업에서 직접 고른 공정은 공용 값도 보낸다, 2026-11-09 보드 C2 (가) ·
    `tests/test_process_field.py`)."""

    def __init__(self, app: AppTest) -> None:
        self.app = app

    @property
    def value(self) -> Any:
        return self.app.session_state[PROCESS_DETAIL_PROCESS_KEY]

    @property
    def options(self) -> list[str]:
        return list(self.app.session_state[PROCESS_CONTEXT_KEY].options)

    def set_value(self, value: str) -> _ProcessBox:
        self.app.session_state[PROCESS_DETAIL_PROCESS_KEY] = value
        return self


def _process_box(app: AppTest) -> _ProcessBox:
    return _ProcessBox(app)


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [element.message for element in app.exception]
    return app


def _origin_bands(app: AppTest) -> list[str]:
    """출처 띠 — 알림 상자가 아니라 아이콘 붙은 캡션 한 줄이다."""
    return [
        str(element.value) for element in app.caption if "칸에서 열었습니다" in str(element.value)
    ]


def _header(app: AppTest) -> str:
    """제목 아래 한 줄 — 공정 표시명과 배지 둘."""
    lines = [str(element.value) for element in app.markdown if OFFICIAL_BADGE in str(element.value)]
    assert len(lines) == 1, [str(element.value) for element in app.markdown]
    return lines[0]


def _panel_head(app: AppTest) -> str:
    """산출 근거 패널 머리(`**산출 근거 · YY.MM · 공정**`)."""
    lines = [str(element.value) for element in app.markdown if "산출 근거 ·" in str(element.value)]
    assert len(lines) == 1, [str(element.value) for element in app.markdown]
    return lines[0]


def _html(app: AppTest) -> list[str]:
    return [str(element.proto.body) for element in app.get("html")]


def _chart_spec(app: AppTest, key: str) -> dict[str, Any]:
    for chart in app.get("plotly_chart"):
        if str(chart.proto.id).endswith(f"-{key}"):
            spec: dict[str, Any] = json.loads(chart.proto.spec)
            return spec
    raise AssertionError(f"{key} 그림이 없다")


def _chart_config(app: AppTest, key: str) -> dict[str, Any]:
    for chart in app.get("plotly_chart"):
        if str(chart.proto.id).endswith(f"-{key}"):
            config: dict[str, Any] = json.loads(chart.proto.config)
            return config
    raise AssertionError(f"{key} 그림이 없다")


def _label_texts(app: AppTest) -> str:
    """라벨 Figure 의 글자 전부(주석·글자 trace)."""
    return json.dumps(_chart_spec(app, "process_detail_summary_labels"), ensure_ascii=False)


# ------------------------------------------------------------------ 진입·선택


def test_the_page_opens_with_header_kpis_canvas_and_evidence_without_equipment(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())

    process_box = _process_box(app)
    assert process_box.value in process_box.options
    month = app.session_state[PROCESS_DETAIL_MONTH_KEY]
    assert isinstance(month, int)
    # 기간은 사이드바 「적용」 표지가 보인다 — 카드가 거듭하지 않는다(설계 규칙 UI-TXT-07). 공정은
    # 조회 조건 패널의 값 칸(하나 고름)이고 기본 공정 규칙은 Guide 다.
    assert app.sidebar.button(key=PROCESS_FIELD_KEY).label == literal_markdown(process_box.value)
    assert not [item for item in app.sidebar.caption if str(item.value).startswith("기간 ")]
    header = _header(app)
    assert header.startswith(f"**{literal_markdown(process_box.value)}**")
    # 설비 DB 에 저장본이 없다 — 샘플 fleet 을 쓰지 않는다.
    assert "설비 일정 없음: 저장본 없음" in header
    assert [metric.label for metric in app.metric] == [
        "최저 확보율",
        "확보 기준 미달",
        "부족 원인",
        "대책",
    ]
    assert app.metric[3].value == "일정 없음"
    # 결합 캔버스 — 라벨 Figure(정적 — ③ 호기 줄이 없어 줄 이름 칸 풍선도 없다)와 월
    # Figure(칸 선택).
    spec = _chart_spec(app, PROCESS_DETAIL_CANVAS_CHART_KEY)
    assert spec["layout"]["xaxis"]["range"][0] == 0
    assert _chart_config(app, "process_detail_summary_labels")["staticPlot"] is True
    assert "① 공식 기준" in _label_texts(app)
    assert "② 설비 일정 기준 가용" not in _label_texts(app)
    # 산출 근거 패널은 고른 달이고 카드는 ① ~ ③ 셋이다.
    assert (
        _panel_head(app)
        == f"**산출 근거 · {month_label(month)} · {literal_markdown(process_box.value)}**"
    )
    cards = next(body for body in _html(app) if "pcd-cards" in body)
    assert all(title in cards for title in ("① 소요", "② 가용", "③ 판정"))
    assert "④ 단축 근거" not in cards
    # 채울 입력이 가용설비 현황에 있다 — 자리에는 마크만, 까닭은 알림 전문이고 길은 그 줄의 「그
    # 화면으로」 다(설계 규칙 UI-NTF-08). 머리 배지가 까닭을 적으니 KPI 칩은 거듭하지 않는다.
    assert data_error_marks(app) == 1
    (note,) = events(app, "PD-01")
    assert note["page"] == tab_label(AVAILABLE_EQUIPMENT_STATUS)
    assert note["href"] == AVAILABLE_EQUIPMENT_STATUS.href
    # 저장본 없음은 설비 DB 전체의 일이라 글에 공정이 없다 — 공정을 넘겨도 같은 알림이다(UI-NTF-07).
    assert note["full"].startswith("공정 Capa 상세 — ") and process_box.value not in note["full"]
    assert "설비 마스터가 없습니다" in note["full"]
    assert not any("설비 마스터가 없습니다" in str(element.value) for element in app.caption)
    # 호기 CSV 와 정리 줄의 탭 링크는 설비 일정이 설 때만이다. 시트 엑셀은 ① 이 있어 늘 서고 둘째
    # 시트(단축 일정)가 없다.
    assert UNITS_CSV_KEY not in {str(button.key) for button in app.get("download_button")}
    assert SHORTENING_TAB_LINK_KEY not in {str(button.key) for button in app.button}
    _, book = _sheet(app)
    assert list(book) == [DETAIL_SHEET]
    assert _heading(book[DETAIL_SHEET])["설비 일정"] == "설비 일정 없음: 저장본 없음"
    # HOME 에서 오지 않았으므로 출처 띠가 없다.
    assert _origin_bands(app) == []
    # 머리 오른쪽 「← HOME」 링크(단독 실행은 갈 페이지가 없어 글자로 물러선다).
    assert any(str(element.value) == "사이드바에서 HOME" for element in app.caption)


def test_the_route_factor_table_leaves_the_other_basis_cell_blank(
    databases: tuple[Path, Path],
) -> None:
    """「경로별 인자」 표의 UPEH(Main)·ST(MI)는 경로마다 하나만 값이다 — 다른 칸은 「None」 글자가
    아니라 빈칸이다(Streamlit 1.63 `st.dataframe` 은 `placeholder` 가 없으면 결측 칸에 「None」)."""
    app = _ok(_app(databases).run())

    (table,) = [
        element
        for element in app.dataframe
        if {"UPEH", "ST", "환산_UPEH"} <= set(element.value.columns)
    ]
    assert table.proto.HasField("placeholder") and table.proto.placeholder == ""


def test_a_chosen_process_survives_reruns_and_keeps_the_month(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())
    process_box = _process_box(app)
    other = next(option for option in process_box.options if option != process_box.value)
    months = _months(app)
    app.session_state[PROCESS_DETAIL_MONTH_KEY] = months[-1]
    _ok(app.run())

    _process_box(app).set_value(other)
    _ok(app.run())
    assert _process_box(app).value == other
    _ok(app.run())
    assert _process_box(app).value == other
    assert _header(app).startswith(f"**{literal_markdown(other)}**")
    # 공정을 바꿔도 보던 달은 그대로다.
    assert app.session_state[PROCESS_DETAIL_MONTH_KEY] == months[-1]
    assert month_label(months[-1]) in _panel_head(app)


def _months(app: AppTest) -> list[int]:
    """월 Figure 의 머리 칸 달(표적 막대 customdata 의 달)."""
    spec = _chart_spec(app, PROCESS_DETAIL_CANVAS_CHART_KEY)
    found: list[int] = []
    for trace in spec["data"]:
        for item in trace.get("customdata") or []:
            if isinstance(item, list) and len(item) > 1 and item[1] == "header":
                found.append(int(item[0]))
    assert found
    return sorted(set(found))


def test_an_injected_month_moves_the_evidence_panel_and_the_canvas_mark(
    databases: tuple[Path, Path],
) -> None:
    """칸을 누르면 콜백이 세션 달을 적는다 — 그 달로 근거 패널·그림의 지금 보는 달이 옮겨 간다."""
    app = _ok(_app(databases).run())
    months = _months(app)
    target = months[-1]
    app.session_state[PROCESS_DETAIL_MONTH_KEY] = target
    _ok(app.run())

    assert month_label(target) in _panel_head(app)
    first = json.dumps(_chart_spec(app, PROCESS_DETAIL_CANVAS_CHART_KEY))
    app.session_state[PROCESS_DETAIL_MONTH_KEY] = months[0]
    _ok(app.run())
    # 지금 보는 달 표시(머리 밑줄·열 테두리)는 그림에 구워진다 — 달이 바뀌면 그림도 바뀐다.
    assert json.dumps(_chart_spec(app, PROCESS_DETAIL_CANVAS_CHART_KEY)) != first
    assert month_label(months[0]) in _panel_head(app)


def test_expanding_products_adds_rows_and_the_split_drops_a_single_basis(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())
    assert "소요대수 ▸" in _label_texts(app)
    assert not app.segmented_control

    app.toggle(key=PROCESS_DETAIL_EXPAND_KEY).set_value(True)
    _ok(app.run())
    first_product = app.multiselect(key=PROCESS_DETAIL_PRODUCT_FILTER_KEY).options[0]
    assert "소요대수 ▾" in _label_texts(app)
    assert first_product in _label_texts(app)
    split = app.segmented_control(key=PROCESS_DETAIL_SPLIT_KEY)
    # 공정 안에서 늘 한 값인 소요기준은 「분류」에 두지 않는다.
    options = [str(option) for option in split.proto.options]
    assert "소요기준" not in json.dumps(options, ensure_ascii=False)
    assert "Stack" in json.dumps(options, ensure_ascii=False)

    app.session_state[PROCESS_DETAIL_SPLIT_KEY] = "Stack"
    _ok(app.run())
    labels = _label_texts(app)
    assert first_product not in labels
    # 펼침은 세션에 남는다(다른 화면에 다녀와도).
    _ok(app.run())
    assert app.toggle(key=PROCESS_DETAIL_EXPAND_KEY).value is True


def test_the_product_filter_lists_the_process_products_and_folds_the_rest(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())
    app.toggle(key=PROCESS_DETAIL_EXPAND_KEY).set_value(True)
    _ok(app.run())
    products = app.multiselect(key=PROCESS_DETAIL_PRODUCT_FILTER_KEY)
    assert len(products.options) >= 2
    kept, dropped = products.options[0], products.options[1]
    products.set_value([kept])
    _ok(app.run())

    labels = _label_texts(app)
    assert kept in labels
    assert dropped not in labels
    assert "거르기 밖" in labels


def test_the_address_opens_that_process_and_month(databases: tuple[Path, Path]) -> None:
    app = _ok(_app(databases).run())
    options = list(_process_box(app).options)
    first_month = app.session_state[PROCESS_DETAIL_MONTH_KEY]
    target = options[-1]

    app.query_params.update({"process": target, "month": str(first_month), "from": "home"})
    app.query_params["theme"] = "dark"
    _ok(app.run())

    assert _process_box(app).value == target
    assert app.session_state[PROCESS_DETAIL_MONTH_KEY] == first_month
    # 읽은 키만 지운다 — 테마 인자는 남는다.
    assert dict(app.query_params) == {"theme": ["dark"]}


@pytest.mark.parametrize(
    ("wanted", "shown"),
    [
        (
            "![x](http://h/p.png) [링크](http://h/q) A~B~C",
            "「![x](http://h/p.png) [링크](http://h/q) A~B~C」는 ",
        ),
        # 조사는 날 이름의 끝소리로 고른다(「2」 → 「는」).
        ("WB(2)", "「WB(2)」는 "),
    ],
    ids=["markdown", "particle"],
)
def test_an_address_process_outside_the_list_is_shown_as_literal_text(
    databases: tuple[Path, Path], wanted: str, shown: str
) -> None:
    """주소 인자 `?process=` 는 누구나 적어 보낼 수 있다 — 경고 상자에 마크다운으로 그리면
    링크 하나로 남의 화면에 외부 이미지·임의 링크를 띄운다. 이제 그 알림은 사건 알림(`PD-02` —
    알림창 · Alarm)이고 알림창 · 패널은 글을 `textContent` 로 넣어 마크다운이 그려지지 않는다 —
    이름은 글자 그대로 싣고 경고 상자(마크다운)는 그리지 않는다."""
    app = _ok(_app(databases).run())
    options = list(_process_box(app).options)
    assert wanted not in options

    app.query_params["process"] = wanted
    _ok(app.run())

    assert not [element for element in app.warning if "넘겨받은 공정" in str(element.value)]
    bodies = [str(note["full"]) for note in events(app, "PD-02")]
    assert len(bodies) == 1, bodies
    assert shown in bodies[0]
    # 목록에 없는 공정이므로 기본 공정으로 열린다.
    assert _process_box(app).value in options


def test_the_home_transfer_slot_opens_the_cell_and_shows_the_origin_band(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())
    target = list(_process_box(app).options)[0]
    month = app.session_state[PROCESS_DETAIL_MONTH_KEY]
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process=target,
        month=month,
        section=HOME_BOTTLENECK_SECTION,
        displayed_rate=1.03,
        raw_rate=0.98,
        execution_delta=5.0,
    )
    _ok(app.run())

    assert _process_box(app).value == target
    assert _origin_bands(app) == [
        f"{ORIGIN_BAND_ICON} HOME 상세 B/N 공정 · {month_label(month)} 칸에서 열었습니다 · "
        "표시 103% = 원 확보율 98% + 확보율 보정 +5.0% · 아래는 원 확보율"
    ]
    # 알림 상자 세 색은 뜻으로 가른다 — 출처는 「조건에 맞는 것이 없다」(`st.info`)가 아니다.
    assert not any("칸에서 열었습니다" in str(element.value) for element in app.info)


def test_a_single_shared_process_opens_on_the_detail_page_and_names_its_origin(
    databases: tuple[Path, Path],
) -> None:
    """HOME 에서 공정 하나로 좁히면 이 화면이 그 공정을 열고 값 칸이 「HOME 에서」 를 단다. 이
    화면에서 팝업 밖 길(◀▶)로 다른 공정으로 넘기면 출처가 걷히고 공용 값은 그대로다(2026-11-08
    사용자 답 P2-2 — 팝업에서 직접 고른 공정만 보낸다, 2026-11-09 보드 C2 (가))."""
    from test_process_field import share, shared_values

    app = _ok(_app(databases).run())
    first = _process_box(app).value
    target = next(option for option in _process_box(app).options if option != first)
    share(app, [target])
    _ok(app.run())

    assert _process_box(app).value == target
    assert "HOME 에서" in [str(item.value) for item in app.sidebar.caption]

    _process_box(app).set_value(first)
    _ok(app.run())
    assert _process_box(app).value == first
    assert "HOME 에서" not in [str(item.value) for item in app.sidebar.caption]
    assert shared_values(app) == [target]


def test_a_first_open_or_a_home_cell_sends_no_shared_process(
    databases: tuple[Path, Path],
) -> None:
    """공용 값은 사이드바 공정 칸 팝업에서 직접 고른 공정만 보낸다(2026-11-09 보드 C2 (가)). 처음 열
    때의 기본 공정(기간 최저 확보율 공정)은 공용 값을 만들지 않고, HOME 그림 칸(전달 칸)으로 들어온
    회차도 다른 화면의 거름을 그대로 둔다 — 한 공정을 들여다본 일로 3공정 거름이 사라지지 않게."""
    from test_process_field import share, shared_values

    app = _ok(_app(databases).run())
    assert _process_box(app).value is not None
    assert shared_values(app) == []
    _ok(app.run())
    assert shared_values(app) == []

    options = list(_process_box(app).options)
    assert len(options) >= 2
    held = [*options[1:3], "없는_공정"]
    share(app, held)
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process=options[0],
        month=app.session_state[PROCESS_DETAIL_MONTH_KEY],
        section=HOME_BOTTLENECK_SECTION,
        displayed_rate=1.0,
    )
    _ok(app.run())
    assert _process_box(app).value == options[0]
    assert shared_values(app) == held
    _ok(app.run())
    assert _process_box(app).value == options[0]
    assert shared_values(app) == held


def test_a_stopped_visit_consumes_the_transfer_slot(databases: tuple[Path, Path]) -> None:
    """공통 진입이 오류로 멈춘 회차도 전달 칸을 꺼낸다 — 남기면 나중에 사이드바로 들어온 방문이
    그 칸을 「HOME 에서 온 것」으로 읽어 거짓 출처 띠를 단다."""
    app = _app(databases, fail_bootstrap=True)
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process="DEMO-A", month=202603, section=HOME_BOTTLENECK_SECTION, displayed_rate=1.0
    )
    app.run()

    assert not app.exception, [element.message for element in app.exception]
    assert any("시험용 진입 오류" in text for text in data_error_texts(app))
    assert PROCESS_DETAIL_REQUEST_KEY not in app.session_state


def test_a_month_outside_the_page_axis_opens_the_default_month_with_a_notice(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())
    target = list(_process_box(app).options)[0]
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process=target, month=199001
    )
    _ok(app.run())

    assert isinstance(app.session_state[PROCESS_DETAIL_MONTH_KEY], int)
    # 넘겨받은 달이 밖이라는 것은 사건 알림(`PD-03` — 알림창 · Alarm)이다.
    assert not [element for element in app.info if "밖이라" in str(element.value)]
    assert any(
        "90.01" in str(note["full"]) and "밖이라" in str(note["full"])
        for note in events(app, "PD-03")
    )


def test_the_home_display_row_appears_only_when_home_adds_an_execution_delta(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """HOME 「확보율 보정」 토글이 켜져 있고 이 공정·달에 증감이 있으면 「확보율 (HOME 표시)」
    회색 줄이 선다(HOME 과 같은 계산). 토글이 꺼져 있거나 얹을 것이 없으면 줄이 없다 — 원
    확보율과 같은 줄을 두지 않는다."""
    root = tmp_path_factory.mktemp("process_capa_detail_home_rate")
    databases = (root / "scenario.duckdb", root / "equipment.duckdb")
    app = _ok(_app(databases).run())
    process = str(_process_box(app).value)
    month = int(app.session_state[PROCESS_DETAIL_MONTH_KEY])
    DuckDBScenarioRepository(databases[0]).replace_global_execution_capacity(
        pd.DataFrame(
            {"생산계획년월": [month], "공정": [process], "증감 확보율": [5.0], "비고": ["시험"]}
        ),
        source="시험",
    )
    clear_global_execution_capacity_cache()
    _ok(app.run())
    assert "확보율 (HOME 표시)" not in _label_texts(app)

    app.session_state[EXECUTION_TOGGLE_KEY] = True
    _ok(app.run())
    assert "확보율 (HOME 표시)" in _label_texts(app)


# ------------------------------------------------------------------ 구획 접기


def _sections(app: AppTest) -> list[str]:
    return [str(value) for value in app.pills(key=PROCESS_DETAIL_SECTIONS_KEY).value or []]


def test_the_section_chips_start_all_open_with_four_fixed_options(
    databases: tuple[Path, Path],
) -> None:
    """선택지는 설비 일정이 없는 공정에서도 넷 그대로다 — 빼면 세션 값이 선택지 밖으로 나가
    지워진다."""
    app = _ok(_app(databases).run())
    chips = app.pills(key=PROCESS_DETAIL_SECTIONS_KEY)

    assert list(chips.options) == ["① 공식", "② 일정 가용", "③ 단축", "④ 비가동"]
    assert _sections(app) == list(SECTION_IDS)
    assert "① 공식 기준 ▾" in _label_texts(app)


def test_folding_the_summary_leaves_its_title_and_disables_the_product_toggle(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())
    app.toggle(key=PROCESS_DETAIL_EXPAND_KEY).set_value(True)
    _ok(app.run())
    first_product = app.multiselect(key=PROCESS_DETAIL_PRODUCT_FILTER_KEY).options[0]
    assert first_product in _label_texts(app)

    app.pills(key=PROCESS_DETAIL_SECTIONS_KEY).set_value(
        [SECTION_DYNAMIC, SECTION_UNITS, SECTION_DOWNTIME]
    )
    _ok(app.run())
    labels = _label_texts(app)
    assert "① 공식 기준 ▸" in labels
    assert "총보유대수" not in labels and first_product not in labels
    # 펼침 값은 남고(다시 펴면 그대로) 접힌 동안 토글은 쓸 수 없다. 분류도 서지 않는다.
    assert app.toggle(key=PROCESS_DETAIL_EXPAND_KEY).value is True
    assert app.toggle(key=PROCESS_DETAIL_EXPAND_KEY).proto.disabled
    assert not app.segmented_control
    # 근거 패널은 접힘과 상관없이 선다.
    assert _panel_head(app).startswith("**산출 근거 ·")

    # 세션 값이라 다시 돌아도 그대로다.
    _ok(app.run())
    assert _sections(app) == [SECTION_DYNAMIC, SECTION_UNITS, SECTION_DOWNTIME]


def test_folding_units_hides_its_more_toggle_even_when_it_was_on(
    dynamic_databases: tuple[Path, Path],
) -> None:
    app = _dynamic_app(dynamic_databases)
    app.session_state[SHOW_ALL_UNITS_KEY] = True
    _ok(app.run())
    assert any(toggle.label == "더 보기 — 신규 설비 모두" for toggle in app.toggle)

    app.pills(key=PROCESS_DETAIL_SECTIONS_KEY).set_value(
        [SECTION_SUMMARY, SECTION_DYNAMIC, SECTION_DOWNTIME]
    )
    _ok(app.run())
    assert "③ 신규 설비 일정과 단축 ▸" in _label_texts(app)
    assert not any(toggle.label == "더 보기 — 신규 설비 모두" for toggle in app.toggle)
    assert app.session_state[SHOW_ALL_UNITS_KEY] is True


def test_the_gap_link_reopens_the_downtime_section(
    dynamic_databases: tuple[Path, Path],
) -> None:
    """가용설비 현황 「④ 에서 비가동 화살표로 보기」(`from=gap`)로 들어오면 접어 둔 ④ 를 다시 편다 —
    링크 글이 거짓이 되지 않게. 다른 구획의 접힘은 둔다."""
    app = _dynamic_app(dynamic_databases)
    app.pills(key=PROCESS_DETAIL_SECTIONS_KEY).set_value([SECTION_SUMMARY])
    _ok(app.run())
    assert "④ 호기별 비가동 ▸" in _label_texts(app)
    month = app.session_state[PROCESS_DETAIL_MONTH_KEY]

    app.query_params.update({"process": DYNAMIC_PROCESS, "month": str(month), "from": "gap"})
    _ok(app.run())
    assert _sections(app) == [SECTION_SUMMARY, SECTION_DOWNTIME]
    assert "④ 호기별 비가동 ▾" in _label_texts(app)
    assert "③ 신규 설비 일정과 단축 ▸" in _label_texts(app)


def test_a_home_cell_reopens_the_summary_section(databases: tuple[Path, Path]) -> None:
    app = _ok(_app(databases).run())
    app.pills(key=PROCESS_DETAIL_SECTIONS_KEY).set_value([])
    _ok(app.run())
    assert "① 공식 기준 ▸" in _label_texts(app)
    target = str(_process_box(app).value)

    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process=target, month=app.session_state[PROCESS_DETAIL_MONTH_KEY]
    )
    _ok(app.run())
    assert _sections(app) == [SECTION_SUMMARY]
    assert "① 공식 기준 ▾" in _label_texts(app)


# ------------------------------------------------------------------ ◀▶ 공정 넘기기·다음 화면


@pytest.fixture(scope="module")
def strict_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """판정 기준을 아주 높여 시드의 모든 공정이 확보 기준 미달인 하네스 — ◀▶ 와 부족 원인 줄이 선다.
    합성 시드의 확보율은 수천 % 대라 기준을 그만큼 올린다(표본 관측)."""
    root = tmp_path_factory.mktemp("process_capa_detail_strict")
    databases = (root / "scenario.duckdb", root / "equipment.duckdb")
    _ok(_app(databases).run())
    repository = DuckDBScenarioRepository(databases[0])
    threshold = repository.load_global_securement_threshold()
    repository.replace_global_securement_threshold(
        100_000.0,
        90_000.0,
        pd.DataFrame(columns=["생산계획년월", "확보 기준", "경고 기준"]),
        source="시험",
        expected_version=threshold.version,
    )
    clear_global_securement_threshold_cache()
    return databases


def _step_caption(app: AppTest) -> str:
    captions = [str(item.value) for item in app.caption if str(item.value).startswith("미달 ")]
    assert len(captions) == 1, captions
    return captions[0]


def test_the_header_steps_through_shortfall_processes(
    strict_databases: tuple[Path, Path],
) -> None:
    """머리 ◀▶ 는 확보 기준 미달 공정을 최저 확보율이 낮은 차례로 넘기고, 옮긴 공정의 첫 미달 달을
    연다. 기본 공정(최저 확보율)이 첫째라 ◀ 는 쓸 수 없다."""
    app = _ok(_app(strict_databases).run())
    first = str(_process_box(app).value)
    caption = _step_caption(app)
    assert caption.startswith("미달 1/")
    assert app.button(key=PROCESS_DETAIL_PREVIOUS_PROCESS_KEY).proto.disabled
    months = _months(app)

    app.button(key=PROCESS_DETAIL_NEXT_PROCESS_KEY).click()
    _ok(app.run())
    second = str(_process_box(app).value)
    assert second != first
    assert _step_caption(app).startswith("미달 2/")
    assert _header(app).startswith(f"**{literal_markdown(second)}**")
    # 모든 달이 미달인 하네스 — 첫 미달 달은 축 첫 달이다.
    assert app.session_state[PROCESS_DETAIL_MONTH_KEY] == months[0]

    app.button(key=PROCESS_DETAIL_PREVIOUS_PROCESS_KEY).click()
    _ok(app.run())
    assert _process_box(app).value == first


def test_the_header_step_buttons_are_named_by_where_they_go(
    strict_databases: tuple[Path, Path],
) -> None:
    """머리 ◀ ▶ 는 기호만 보이지만 접근 이름(라벨)은 갈 곳 — 「다음 미달 공정: <공정명> · 최저
    …」 다(E2E 2026-10-26 — 이름이 「◀」·「▶」 뿐이라 읽기 도구가 갈 곳을 몰랐다). 라벨 글은
    화면에서 시각적으로만 숨기고 기호를 대체 글 없는 생성 글로 그린다. 풍선은 그대로다."""
    app = _ok(_app(strict_databases).run())
    previous = app.button(key=PROCESS_DETAIL_PREVIOUS_PROCESS_KEY)
    following = app.button(key=PROCESS_DETAIL_NEXT_PROCESS_KEY)

    assert previous.label == "이전 미달 공정 없음" and previous.proto.disabled
    assert following.label.startswith("다음 미달 공정: ") and " · 최저 " in following.label
    help_text = str(following.proto.help)
    assert following.label == f"다음 미달 공정: {help_text}"
    style = next(body for body in _html(app) if PROCESS_DETAIL_NEXT_PROCESS_KEY in body)
    assert 'content:"◀" / ""' in style and 'content:"▶" / ""' in style
    assert "clip-path:inset(50%)" in style and "display:none" not in style

    following.click()
    _ok(app.run())
    second = str(_process_box(app).value)
    assert app.button(key=PROCESS_DETAIL_PREVIOUS_PROCESS_KEY).label.startswith("이전 미달 공정: ")
    assert second


def test_the_step_label_keeps_a_renamed_process_as_written() -> None:
    step = ProcessStep("DEMO_Chip_Attach", 0.011, 202611)
    label = step_button_label("▶", step, lambda _: "Chip Attach 1~2차/3~4차")
    assert label == f"다음 미달 공정: {literal_markdown('Chip Attach 1~2차/3~4차')} · 최저 1.1%"
    assert step_button_label("◀", None, str) == "이전 미달 공정 없음"


def test_the_investment_mark_stands_in_the_evidence_panel_of_an_owned_shortfall_month(
    strict_databases: tuple[Path, Path],
) -> None:
    """KPI 아래 부족 원인 줄은 걷었다(2026-11-10 보드 c2-picked) — 「투자 검토 대상」 표지와 산출
    결과 링크는 근거 패널이 그 달 원인이 보유로도 부족일 때 단다(단독 실행은 갈 페이지가 없어 글자로
    물러선다). 기간 전체의 원인별 달 수는 KPI 「부족 원인」 이다."""
    app = _ok(_app(strict_databases).run())
    cause = next(metric for metric in app.metric if metric.label == "부족 원인")
    assert not any("개월 — 산출 결과" in str(item.value) for item in app.caption)
    if "보유" not in str(cause.value):
        return
    for month in _months(app):
        app.session_state[PROCESS_DETAIL_MONTH_KEY] = month
        _ok(app.run())
        links = [str(item.value) for item in app.caption if "— 산출 결과" in str(item.value)]
        if links:
            assert any(str(item.value) == INVESTMENT_BADGE for item in app.markdown)
            assert links == ["사이드바에서 이 달 보유로도 부족 — 산출 결과"], links
            return
    raise AssertionError("보유로도 부족 달의 근거 패널에 산출 결과 링크가 없다")


# ------------------------------------------------------------------ 설비 일정(참고)


def _dynamic_app(dynamic_databases: tuple[Path, Path]) -> AppTest:
    app = _app(dynamic_databases)
    app.query_params["process"] = DYNAMIC_PROCESS
    return _ok(app.run())


def test_a_ready_process_draws_the_equipment_schedule_sections(
    dynamic_databases: tuple[Path, Path],
) -> None:
    app = _dynamic_app(dynamic_databases)

    assert _process_box(app).value == DYNAMIC_PROCESS
    assert "설비 일정 참고 · Cut-off 10일" in _header(app)
    labels = _label_texts(app)
    for title in ("② 설비 일정 기준 가용", "③ 신규 설비 일정과 단축", "④ 호기별 비가동"):
        assert title in labels
    assert "DA-01" in labels
    # ③ 호기 줄 이름 칸에 풍선이 있으면 라벨 그림도 hover 를 켠다(`staticPlot` 을 뺀다).
    label_spec = _chart_spec(app, "process_detail_summary_labels")
    assert any(
        str(row_id).startswith(("unit:", "exit:"))
        for trace in label_spec["data"]
        for row_id, _ in trace["customdata"]
    )
    assert "staticPlot" not in _chart_config(app, "process_detail_summary_labels")
    # 단축 목표는 확보 기준(월별) 표시뿐이다 — 고르는 위젯이 없다. 그 값을 고치는 곳(HOME 설정 →
    # 판정 기준)은 풍선이다(길 안내는 자리 글이 아니다 — UI-TXT-03).
    targets = [element for element in app.caption if "단축 목표 = " in str(element.value)]
    assert len(targets) == 1
    assert str(targets[0].value).startswith("단축 목표 = 확보 기준(월별)")
    assert "HOME 설정 → 판정 기준 › 확보 기준(월별)" in str(targets[0].help)
    # 단축 목표를 적는 자리는 이 한 줄이다 — KPI 칩이 거듭하지 않는다(설계 규칙 UI-TXT-07).
    assert _metric(app, "대책").delta == "설비 일정 기준"
    # 공정 상자 뒤의 선택 상자는 「이 세션만」 UPEH 적용 구간 둘뿐이다(목표를 고르는 상자가 아니다).
    assert {box.key for box in app.get("selectbox")[1:]} <= {
        UPEH_ASSUMPTION_START_KEY,
        UPEH_ASSUMPTION_END_KEY,
    }
    legend = next(body for body in _html(app) if "pcd-legend" in body)
    # 생산월 규칙은 「칸 = 생산월」 표지의 풍선(title)이다 — 늘 보이는 글이 아니다.
    assert "칸 = 생산월 · Cut-off 10일</span>" in legend
    assert 'title="칸 = 생산월 — Cut-off 10일이면' in legend
    # 설비 일정 없음 카드는 서지 않는다.
    assert not any("설비 마스터가 없습니다" in str(element.value) for element in app.caption)


def test_the_unit_csv_is_this_process_only_with_the_tab_columns(
    dynamic_databases: tuple[Path, Path],
) -> None:
    app = _dynamic_app(dynamic_databases)

    captured = app.session_state["captured_downloads"][UNITS_CSV_KEY]
    frame = pd.read_csv(io.BytesIO(captured["data"]), encoding="utf-8-sig")
    assert list(frame.columns) == list(UNIT_EXPORT_COLUMNS)
    assert set(frame["공정"].astype(str)) <= {DYNAMIC_PROCESS}
    assert captured["file_name"].startswith("process_capa_detail_units_")
    assert captured["data"].startswith("﻿".encode())


def _sheet(app: AppTest) -> tuple[dict[str, Any], Any]:
    """「시트 엑셀」 단추가 받은 것 — (기록, 그 통을 읽은 시트들)."""
    captured = app.session_state["captured_downloads"][SHEET_XLSX_KEY]
    assert isinstance(captured["data"], bytes)
    return captured, read_workbook(captured["data"])


def _heading(sheet: Any) -> dict[str, str]:
    """시트 맨 위 (이름, 값) 줄 — 제목 다음부터 빈 줄 앞까지."""
    rows: dict[str, str] = {}
    index = 1
    while sheet.row(index):
        name, value = sheet.row(index)[:2]
        rows[str(name)] = str(value)
        index += 1
    return rows


def test_the_sheet_xlsx_follows_the_screen_state(
    dynamic_databases: tuple[Path, Path],
) -> None:
    """「시트 엑셀」 은 표 도구 줄 오른쪽 끝(CSV 곁)에 늘 선다. 내용은 지금
    화면 상태 그대로다 — 켠 구획만 행이 서고 접은 구획은 제목 줄(▸)뿐, 「제품별 소요대수」 를 켜면
    펼친 제품 줄, 달 열은 화면 달 그대로, 둘째 시트는 호기 CSV 와 같은 표다(2026-11-10 보드
    c2-picked)."""
    app = _dynamic_app(dynamic_databases)
    months = _months(app)
    captured, book = _sheet(app)

    assert captured["file_name"] == f"process_capa_detail_{months[0]}_{months[-1]}.xlsx"
    assert list(book) == [DETAIL_SHEET, UNITS_SHEET]
    detail = book[DETAIL_SHEET]
    heading = _heading(detail)
    assert heading["공정"] == DYNAMIC_PROCESS
    # 시나리오 · 설비 시나리오는 머리 띠와 같은 함수의 글이다(위 줄 · 아래 줄 꼬리).
    assert " · r" in heading["시나리오"] and heading["설비 시나리오"] != "—"
    assert heading["설비 일정"].startswith("설비 일정 참고 · Cut-off 10일")
    assert heading["구획"] == "① 공식 · ② 일정 가용 · ③ 단축 · ④ 비가동"
    assert heading["단축 목표"].startswith("확보 기준(월별)")
    header = detail.find_row(f"구분 · {DYNAMIC_PROCESS}")
    assert detail.row(header)[2:] == [month_label(month) for month in months]
    assert detail.freeze == (header + 1, 2)
    labels = [str(value) for value in detail.column(0) if value is not None]
    for title in ("① 공식 기준 ▾", "② 설비 일정 기준 가용 ▾", "③ 신규 설비 일정과 단축 ▾"):
        assert title in labels
    assert "DA-01" in labels and "소요대수 ▸" in labels
    rate = detail.find_row("확보율")
    assert all(
        detail.cells[(rate, column)].numeric
        and detail.cells[(rate, column)].number_format.endswith("%")
        for column in range(2, 2 + len(months))
    )
    units = book[UNITS_SHEET]
    assert units.row(0) == list(UNIT_EXPORT_COLUMNS)
    csv = pd.read_csv(
        io.BytesIO(app.session_state["captured_downloads"][UNITS_CSV_KEY]["data"]),
        encoding="utf-8-sig",
    )
    assert len([row for row, column in units.cells if column == 0]) == len(csv) + 1

    app.pills(key=PROCESS_DETAIL_SECTIONS_KEY).set_value([SECTION_SUMMARY, SECTION_DYNAMIC])
    app.toggle(key=PROCESS_DETAIL_EXPAND_KEY).set_value(True)
    _ok(app.run())
    _, book = _sheet(app)
    detail = book[DETAIL_SHEET]
    heading = _heading(detail)
    assert heading["구획"] == "① 공식 · ② 일정 가용"
    assert heading["제품별 소요대수"].startswith("펼침 · 분류 ")
    labels = [str(value) for value in detail.column(0) if value is not None]
    assert "③ 신규 설비 일정과 단축 ▸" in labels and "④ 호기별 비가동 ▸" in labels
    assert "DA-01" not in labels
    assert "소요대수 ▾" in labels and any(label.startswith("└ ") for label in labels)


def test_the_sections_meaning_sits_in_one_info_mark_after_the_chips(
    dynamic_databases: tuple[Path, Path],
) -> None:
    """「구획」 칩은 라벨을 숨긴 칸이라 위젯 풍선이 서지 않는다 — 뜻은 칩 바로 뒤 빈 캡션 풍선
    하나다(2026-11-10 보드 Q-8 · 설계 규칙 UI-TXT-02)."""
    app = _dynamic_app(dynamic_databases)

    assert not app.pills(key=PROCESS_DETAIL_SECTIONS_KEY).proto.help
    marks = [item for item in app.caption if item.proto.help == SECTIONS_HELP]
    assert len(marks) == 1 and str(marks[0].value) == ""


def _main_order(block: Any) -> Iterator[Any]:
    """본문 요소를 화면 차례로."""
    for child in block.children.values():
        if hasattr(child, "children"):
            yield from _main_order(child)
        else:
            yield child


def test_the_unit_csv_stands_on_the_tool_row_above_the_canvas(
    dynamic_databases: tuple[Path, Path],
) -> None:
    """단추를 표에서 떼어 페이지 끝에 두지 않는다(설계 규칙 UI-LAY-03) — 표 도구 줄이 캔버스보다
    먼저 서고 CSV 는 그 줄의 끝, 곧 첫 그림 앞이다."""
    app = _dynamic_app(dynamic_databases)

    order = [element.type for element in _main_order(app.main)]
    assert order.index("download_button") < order.index("plotly_chart")
    # 곁의 칩과 같은 높이 서식은 보이는 글(범례)과 한 `st.html` 이라 이벤트 칸을 쓰지 않는다.
    assert any("pcd-legend" in body and DOWNLOAD_STYLE in body for body in _html(app))


def _closing_link(app: AppTest) -> bool:
    return SHORTENING_TAB_LINK_KEY in {str(button.key) for button in app.button}


def _buttons(app: AppTest) -> set[str]:
    return {str(button.key) for button in app.button}


def _open_schedule_short_month(app: AppTest) -> int:
    """근거 패널에 「이 달 일정 부족 — 필요 단축 일정」 이 서는 달을 골라 연다(그 달을 돌려준다)."""
    for month in _months(app):
        app.session_state[PROCESS_DETAIL_MONTH_KEY] = month
        _ok(app.run())
        if EVIDENCE_SHORTENING_BUTTON_KEY in _buttons(app):
            return month
    raise AssertionError("일정 부족 달이 없다")


def test_the_kpi_next_screen_row_is_gone_and_the_closing_link_still_steps_aside(
    dynamic_databases: tuple[Path, Path],
) -> None:
    """KPI 아래 「다음 화면 · 일정 n개월 — 필요 단축 일정」 줄은 걷었다(2026-11-10 보드 c2-picked).
    일정 부족 달이 있는 공정은 근거 패널의 그 달 단추가 같은 길이라 맨 아래 링크는 서지 않고(설계
    규칙 UI-LAY-12), 내려받기 둘은 그대로다."""
    app = _dynamic_app(dynamic_databases)

    assert not any("개월 — " in str(button.label) for button in app.button), [
        str(button.label) for button in app.button
    ]
    assert not _closing_link(app)
    downloads = {str(button.key) for button in app.get("download_button")}
    assert {UNITS_CSV_KEY, SHEET_XLSX_KEY} <= downloads
    _open_schedule_short_month(app)
    assert (
        app.button(key=EVIDENCE_SHORTENING_BUTTON_KEY).label == "이 달 일정 부족 — 필요 단축 일정"
    )
    assert not _closing_link(app)


@pytest.fixture(scope="module")
def calm_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """기존보유가 넉넉해 일정 부족 달이 없는 공정 — 필요 단축 일정으로 가는 다른 길이 없다."""
    root = tmp_path_factory.mktemp("process_capa_detail_calm")
    equipment_path = root / "equipment.duckdb"
    repository = DuckDBEquipmentRepository(equipment_path)
    repository.initialize()
    master = _master(
        [_unit("DA-01", date(2026, 12, 10), process=DYNAMIC_PROCESS, arrival=date(2026, 11, 1))]
    )
    baseline = pd.DataFrame(
        [{"공정": DYNAMIC_PROCESS, "분류": "시험", "기존보유대수": 9000.0, "비고": ""}]
    )
    repository.save_snapshot(baseline, master, _downtime([]))
    repository.save_process_cutoff(_cutoff(10, DYNAMIC_PROCESS))
    return root / "scenario.duckdb", equipment_path


def test_the_closing_link_stands_when_nothing_else_leads_to_the_shortening_page(
    calm_databases: tuple[Path, Path],
) -> None:
    """다른 길이 없는 공정에만 맨 아래 링크가 서고, 그 카드에서 왔으면(「← 필요 단축 일정」) 서지
    않는다."""
    app = _dynamic_app(calm_databases)

    assert EVIDENCE_SHORTENING_BUTTON_KEY not in _buttons(app)
    assert _closing_link(app)

    app.query_params.update(
        shortening_card_query_params(
            process=DYNAMIC_PROCESS,
            month=app.session_state[PROCESS_DETAIL_MONTH_KEY],
            target=1.2,
            start_month=202601,
            end_month=202606,
            shortened=0,
            new=0,
            theme=None,
        )
    )
    _ok(app.run())

    assert app.button(key="process_detail_back_to_shortening").label == "필요 단축 일정"
    assert not _closing_link(app)


@pytest.fixture(scope="module")
def usage_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """`dynamic_databases` 의 두 호기에 사용기준이 HBM·EDP 가 아닌 호기 하나를 더한 한 벌."""
    root = tmp_path_factory.mktemp("process_capa_detail_usage")
    equipment_path = root / "equipment.duckdb"
    repository = DuckDBEquipmentRepository(equipment_path)
    repository.initialize()
    master = _master(
        [
            _unit("DA-01", date(2026, 12, 10), process=DYNAMIC_PROCESS, arrival=date(2026, 11, 1)),
            _unit("DA-02", date(2027, 1, 20), process=DYNAMIC_PROCESS, arrival=date(2026, 12, 1)),
            _unit(
                "DA-09",
                date(2027, 1, 5),
                process=DYNAMIC_PROCESS,
                arrival=date(2026, 12, 1),
                attributes={"사용기준": "DDR"},
            ),
        ]
    )
    baseline = pd.DataFrame(columns=["공정", "분류", "기존보유대수", "비고"])
    repository.save_snapshot(baseline, master, _downtime([]))
    repository.save_process_cutoff(_cutoff(10, DYNAMIC_PROCESS))
    return root / "scenario.duckdb", equipment_path


def test_units_left_out_by_usage_basis_raise_an_alert_and_leave_the_closing_row_quiet(
    usage_databases: tuple[Path, Path],
) -> None:
    """정리 줄에 늘 서던 「사용기준 제외 n대 · 일정 미정 · 오늘이 든 달 · 단축은 공식을 바꾸지
    않음」 글은 걷었다 — 사용기준 제외 대수는 상태 알림(`PD-04` — 알림창 · Alarm)이고, 단축이 바꾸는
    숫자는 산출 근거 머리의 풍선이다(설계 규칙 UI-TXT-01 · 04 · UI-NTF-02)."""
    app = _dynamic_app(usage_databases)

    note = active_state(app, "PD-04")
    assert note is not None
    assert str(note["short"]).startswith("사용기준 제외 1대 — ")
    assert "단축 후보에도 들지 않습니다" in str(note["full"])
    captions = [str(item.value) for item in app.main.caption]
    gone_texts = (
        "사용기준 제외",
        "남은 날만 셉니다",
        "공식 확보율을 바꾸지 않습니다",
        "이 세션만입니다",
    )
    for gone in gone_texts:
        assert not any(gone in caption for caption in captions), gone
    # 호기 CSV 는 표 도구 줄에 그대로다.
    assert UNITS_CSV_KEY in {str(button.key) for button in app.get("download_button")}
    head = next(item for item in app.markdown if "산출 근거 ·" in str(item.value))
    assert "공식 확보율" in str(head.help)


def test_the_shortening_link_highlights_the_card_without_planting_the_filter(
    dynamic_databases: tuple[Path, Path],
) -> None:
    """필요 단축 일정 링크는 「강조 공정」 칸 하나만 적는다 — 공정 필터(공용 조회 조건 0019 의 세션
    칸)는 심지 않는다. 심은 [공정] 을 사용자가 지우면 빈 선택이 공용 프로필에 저장됐다(2026-10-22
    결함). 필요 단축 일정은 별도 화면이라(2026-10-18) 가용설비 현황의 탭 칸도 건드리지 않는다.

    단독 실행이라 갈 페이지가 없어 옮기지는 않는다(`StreamlitPageNotFoundError` 를 삼킨다).
    """
    app = _dynamic_app(dynamic_databases)
    repository = DuckDBEquipmentRepository(dynamic_databases[1])
    before = repository.load_shortening_filter_profile()
    _open_schedule_short_month(app)
    app.button(key=EVIDENCE_SHORTENING_BUTTON_KEY).click()
    _ok(app.run())

    assert "equipment_active_tab" not in app.session_state
    assert SHORTENING_PROCESS_KEY not in app.session_state
    assert app.session_state[SHORTENING_HIGHLIGHT_KEY] == (DYNAMIC_PROCESS, HIGHLIGHT_FROM_DETAIL)
    after = repository.load_shortening_filter_profile()
    assert after == before and after.processes == ()


def test_a_shortening_card_link_shows_its_band_from_the_address_only(
    dynamic_databases: tuple[Path, Path],
) -> None:
    """필요 단축 일정 카드의 「공정 Capa 상세에서 근거 보기」 — 주소 인자로 받은 그 카드의
    목표·기간·대수로 출처 띠를 내고, 접어 둔 ③ 을 다시 편다. 「← 필요 단축 일정」 은 그 공정을
    강조해 돌아간다."""
    app = _dynamic_app(dynamic_databases)
    app.pills(key=PROCESS_DETAIL_SECTIONS_KEY).set_value([SECTION_SUMMARY])
    _ok(app.run())
    month = app.session_state[PROCESS_DETAIL_MONTH_KEY]

    app.query_params.update(
        shortening_card_query_params(
            process=DYNAMIC_PROCESS,
            month=month,
            target=1.2,
            start_month=202601,
            end_month=202606,
            shortened=2,
            new=1,
            theme=None,
        )
    )
    _ok(app.run())

    band_items = [item for item in app.caption if "필요 단축 일정 카드" in str(item.value)]
    bands = [str(item.value) for item in band_items]
    assert len(bands) == 1, [str(item.value) for item in app.caption]
    assert bands[0].startswith(ORIGIN_BAND_ICON)
    assert "카드(목표 120%(1.20) · 기간 26.01–26.06)에서 열었습니다" in bands[0]
    assert "그 카드: 단축 2대 · 신규 1대" in bands[0]
    # 대수가 갈리는 까닭은 띠의 풍선이다(자리 글이 아니다 — UI-TXT-01).
    assert "다를 수 있습니다" not in bands[0]
    assert band_items[0].help == SHORTENING_BAND_HELP
    assert _sections(app) == [SECTION_SUMMARY, SECTION_UNITS]
    assert dict(app.query_params) == {}

    back = app.button(key="process_detail_back_to_shortening")
    assert back.label == "필요 단축 일정"
    back.click()
    _ok(app.run())
    assert app.session_state[SHORTENING_HIGHLIGHT_KEY] == (DYNAMIC_PROCESS, HIGHLIGHT_FROM_DETAIL)
    assert SHORTENING_PROCESS_KEY not in app.session_state


def test_an_equipment_name_from_the_card_address_reads_as_written_in_the_band(
    dynamic_databases: tuple[Path, Path],
) -> None:
    """카드가 본 설비 시나리오(`eq` 주소 인자)는 누구나 적어 보낼 수 있는 글이다 — 출처 띠(캡션,
    마크다운)에 실을 때 물결표 짝·링크가 해석되지 않게 막는다(E2E 2026-10-26 같은 갈래)."""
    app = _dynamic_app(dynamic_databases)
    equipment = "셋업~실무~A r4 [링크](http://h/q)"
    app.query_params.update(
        shortening_card_query_params(
            process=DYNAMIC_PROCESS,
            month=None,
            target=1.1,
            start_month=202601,
            end_month=202606,
            shortened=1,
            new=0,
            theme=None,
            equipment=equipment,
        )
    )
    _ok(app.run())

    (band,) = [str(item.value) for item in app.caption if "필요 단축 일정 카드" in str(item.value)]
    assert f"카드는 「{literal_markdown(equipment)}」 기준" in band
    assert not re.search(r"(?<!\\)~", band) and "](http" not in band


def test_a_renamed_process_label_reads_as_written_in_the_header_and_the_evidence_head(
    tmp_path: Path,
) -> None:
    """공정 표시명(Admin `Proc Rename`)은 사람이 적은 글이다 — 머리 줄과 「산출 근거」 제목은
    마크다운이라 「1~2차/3~4차」 의 물결표 짝이 지움선이 되고 `**…**`·`[…](…)` 가 굵게·눌리는
    링크가 됐다(E2E 2026-10-26). 제약 시뮬레이션 머리처럼 글자 그대로 막는다."""
    databases = (tmp_path / "scenario.duckdb", tmp_path / "equipment.duckdb")
    app = _ok(_app(databases).run())
    options = list(_process_box(app).options)
    tilde, link = options[0], options[1]
    labels = {
        tilde: "Chip Attach 1~2차/3~4차",
        link: "**굵게** [링크](https://example.com) Inspect",
    }
    DuckDBScenarioRepository(databases[0]).replace_global_process_rename(
        pd.DataFrame({"공정": list(labels), "표시명": list(labels.values())}),
        source="표시명 마크다운 시험",
    )
    clear_global_process_rename_cache()
    try:
        for process, label in labels.items():
            app.query_params["process"] = process
            _ok(app.run())
            for line in (_header(app), _panel_head(app)):
                assert literal_markdown(label) in line, line
                assert not re.search(r"(?<!\\)~", line)
                assert "](https://" not in line and "**굵게**" not in line
    finally:
        clear_global_process_rename_cache()


def test_the_page_identity_lives_in_the_guide_not_in_the_header(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())
    identity = "어느 화면에서든 공정 하나를 눌러 바로 깊게 보는 목적지"
    assert not any(identity in str(item.value) for item in app.caption)
    assert identity in load_guide("process_capa_detail")


# ------------------------------------------------------------------ UPEH 가정


def _upeh_app(databases: tuple[Path, Path], percent: int) -> AppTest:
    """설비 일정이 서는 공정을 UPEH 가정 `percent`%(시드 전 기간)로 연다.

    첫 회차는 공식버전 부트스트랩이 시나리오를 올리며 % 에 100 을 적으므로(시나리오 전환 리셋) 한 번
    돌린 뒤 값을 넣는다.
    """
    app = _dynamic_app(databases)
    app.session_state[UPEH_ASSUMPTION_PERCENT_KEY] = percent
    app.session_state[UPEH_ASSUMPTION_START_KEY] = 202601
    app.session_state[UPEH_ASSUMPTION_END_KEY] = 202612
    return _ok(app.run())


def _metric(app: AppTest, label: str) -> Any:
    return next(metric for metric in app.metric if metric.label == label)


def _percent_value(text: str) -> float:
    return float(str(text).rstrip("%").replace(",", ""))


def test_an_upeh_assumption_marks_the_header_rows_kpis_and_csv(
    dynamic_databases: tuple[Path, Path],
) -> None:
    """110% 면 머리 배지·효과 한 줄, ① 끝 세 줄, ② 바뀌는 행의 표지, KPI 회색 줄 「공식」, 역산 둘,
    가정 CSV(파일 이름·첫 열)가 선다."""
    app = _upeh_app(dynamic_databases, 110)

    assert "UPEH 가정 110% · 26.01–26.12" in _header(app)
    effect = [item for item in app.caption if "소요 −9.1%" in str(item.value)]
    assert len(effect) == 1, [str(item.value) for item in app.caption]
    # 효과 한 줄은 값만 — 이 화면의 목표 · 기간과 필요 단축 일정이 가정을 걸지 않는다는 말은
    # 풍선이다.
    assert "필요 단축 일정" not in str(effect[0].value)
    assert "필요 단축 일정은 이 가정을 걸지 않습니다(늘 공식)" in str(effect[0].proto.help)
    labels = _label_texts(app)
    for row in ("UPEH 110% · 소요대수", "UPEH 110% · 확보율", "UPEH 110% · 확보 기준 과부족"):
        assert row in labels
    assert "판정 대조 · UPEH 가정" in labels
    # ② 비가동 영향은 % 가 가정 소요로 바뀌어 표지를 단다.
    assert "비가동 영향 · UPEH 가정" in labels
    # ② 가용·전월 대비와 ④ 는 UPEH 와 무관해 표지를 달지 않는다.
    assert "가용 (환산) · UPEH 가정" not in labels and "전월 대비 · UPEH" not in labels
    assert "공식" in str(_metric(app, "확보 기준 미달").proto.help) or "공식" in "".join(
        str(item.value) for item in app.caption
    )
    legend = next(body for body in _html(app) if "pcd-legend" in body)
    assert "UPEH 가정 확보 기준 미달 달" in legend
    # 근거 ③ 판정 카드도 같은 기준이다 — 머리 식은 가정, 공식 판정은 회색 「공식: …」 한 줄.
    cards = next(body for body in _html(app) if "pcd-cards" in body)
    assert "③ 판정 (UPEH 가정 110%)" in cards and "공식: 확보율 " in cards
    inverse = [str(item.value) for item in app.caption if " → " in str(item.value)]
    assert any(text.startswith("확보 기준 미달 0 → ") for text in inverse), inverse
    assert any(text.startswith("구간 안 단축 0 → ") for text in inverse), inverse
    captured = app.session_state["captured_downloads"][UNITS_CSV_KEY]
    assert "_upeh110_202601_202612" in captured["file_name"]
    frame = pd.read_csv(io.BytesIO(captured["data"]), encoding="utf-8-sig")
    assert list(frame.columns) == ["UPEH 가정", *UNIT_EXPORT_COLUMNS]
    assert set(frame["UPEH 가정"].astype(str)) <= {"UPEH 가정 110% · 26.01–26.12"}
    # 시트 엑셀도 가정 표지 — 파일 이름 꼬리 · 머리 값 줄 · ① 끝 가정 세 줄 · 둘째 시트 첫 열.
    sheet, book = _sheet(app)
    assert sheet["file_name"].endswith("_upeh110_202601_202612.xlsx")
    detail = book[DETAIL_SHEET]
    assert _heading(detail)["UPEH 가정"] == "UPEH 가정 110% · 26.01–26.12"
    upeh_labels = [str(value) for value in detail.column(0) if value is not None]
    assert "UPEH 110% · 확보율" in upeh_labels and "판정 대조 · UPEH 가정" in upeh_labels
    assert book[UNITS_SHEET].row(0)[0] == "UPEH 가정"


def test_at_100_percent_the_page_shows_only_the_official_basis(
    dynamic_databases: tuple[Path, Path],
) -> None:
    app = _upeh_app(dynamic_databases, 100)
    assert "UPEH 가정" not in _header(app)
    assert "UPEH 100%" not in _label_texts(app)
    assert "판정 대조 · UPEH 가정" not in _label_texts(app)
    legend = next(body for body in _html(app) if "pcd-legend" in body)
    assert "공식 확보 기준 미달 달" in legend
    assert not any("소요 −" in str(item.value) for item in app.caption)
    captured = app.session_state["captured_downloads"][UNITS_CSV_KEY]
    assert "_upeh" not in captured["file_name"]


def test_an_assumption_does_not_leak_into_the_official_rate_cache(
    dynamic_databases: tuple[Path, Path],
) -> None:
    """HOME 오염 회귀(화면) — 150% 로 본 뒤 100% 로 다시 열면 최저 확보율이 처음 공식 값 그대로다.

    가정 확보율은 캐시 밖 작은 프레임에서만 다시 세고 시나리오 키 전용 칸(HOME 과 같은 칸)에 넣지
    않는다. 150% 는 구간(시드 전 기간)의 확보율을 1.5 배로 본다.
    """
    before = _metric(_upeh_app(dynamic_databases, 100), "최저 확보율").value
    assumed = _metric(_upeh_app(dynamic_databases, 150), "최저 확보율").value
    after = _metric(_upeh_app(dynamic_databases, 100), "최저 확보율").value
    assert after == before
    assert _percent_value(assumed) == pytest.approx(_percent_value(before) * 1.5, rel=1e-3)


def test_a_broken_equipment_database_keeps_the_official_section(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """설비 DB 를 못 읽어도 ① 공식 구획·KPI·근거 패널은 남는다. 머리 배지와 알림 짧은 글이 같은
    말이다."""
    root = tmp_path_factory.mktemp("process_capa_detail_broken_equipment")
    broken = root / "equipment.duckdb"
    broken.write_bytes(b"not a duckdb database file" * 100)
    app = _ok(_app((root / "scenario.duckdb", broken)).run())

    assert "설비 일정 없음: 설비 DB 오류" in _header(app)
    assert [note["short"] for note in events(app, "PD-01")] == [DYNAMIC_DB_ERROR_TITLE]
    assert data_error_marks(app) == 1
    labels = _label_texts(app)
    assert "① 공식 기준" in labels and "② 설비 일정 기준 가용" not in labels
    assert [metric.label for metric in app.metric][0] == "최저 확보율"
    cards = next(body for body in _html(app) if "pcd-cards" in body)
    assert all(title in cards for title in ("① 소요", "② 가용", "③ 판정"))


def test_a_schedule_calculation_error_names_itself_and_keeps_the_official_section(
    dynamic_databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """판정은 통과했는데 설비 일정 계산이 멈추면 알림 짧은 글이 머리 배지와 같은 「계산 오류」다 —
    「설비 일정 참고」로 서지 않고, 이미 맞은 조건(저장본·이름·Cut-off)을 까닭처럼 적지 않는다."""

    def fail(*args: object, **kwargs: object) -> None:
        raise ValueError("시험용 계산 오류")

    monkeypatch.setattr(simulation_cache, "get_process_equipment_timeline", fail)
    app = _dynamic_app(dynamic_databases)

    assert "설비 일정 없음: 계산 오류" in _header(app)
    (note,) = events(app, "PD-01")
    assert note["short"] == DYNAMIC_ERROR_TITLE and data_error_marks(app) == 1
    assert "시험용 계산 오류" in note["full"]
    assert note["full"].startswith("설비 일정을 계산하지 못했습니다")
    assert "Cut-off 가 적힌 공정에만" not in note["full"]
    labels = _label_texts(app)
    assert "① 공식 기준" in labels and "② 설비 일정 기준 가용" not in labels
    # 호기 CSV 와 정리 줄의 탭 링크는 설비 일정이 설 때만이다.
    assert UNITS_CSV_KEY not in {str(button.key) for button in app.get("download_button")}
    assert SHORTENING_TAB_LINK_KEY not in {str(button.key) for button in app.button}


# ------------------------------------------------------------------ 본문 프래그먼트


def _event_slots(messages: list[Any]) -> dict[int, str]:
    """이벤트 칸(본문 밖 최상위 칸)의 몇째 자리를 어느 프래그먼트가 썼나."""
    slots: dict[int, str] = {}
    for message in messages:
        if message.WhichOneof("type") != "delta":
            continue
        path = list(message.metadata.delta_path)
        if len(path) != 2 or path[0] != RootContainer.EVENT:
            continue
        slots[path[1]] = str(message.delta.fragment_id)
    return slots


def test_a_picked_month_reruns_only_the_view_fragment_with_the_same_event_slots(
    dynamic_databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """칸 누름은 콜백이 세션 달을 적고 본문 프래그먼트만 다시 돈다(그 콜백 자체는
    `tests/test_process_capa_view.py`). 그 회차는 이벤트 칸에 앱 전체 회차의 그 프래그먼트와 같은
    자리를 쓰고, 그림·근거 패널은 같은 달의 앱 전체 회차와 같다."""
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda **_: None)
    browser = install_fragment_browser(monkeypatch)
    app = _app(dynamic_databases)
    app.query_params["process"] = DYNAMIC_PROCESS
    _ok(app.run())
    view = browser.fragment_keyed(PROCESS_DETAIL_VIEW_FRAGMENT_KEY)
    full_slots = {slot for slot, owner in _event_slots(browser.messages).items() if owner == view}
    assert len(full_slots) == 3
    months = _months(app)
    target = months[-1]

    browser.fragment_queue = [view]
    app.session_state[PROCESS_DETAIL_MONTH_KEY] = target
    _ok(app.run())
    assert browser.started == [[view]]
    assert set(_event_slots(browser.messages)) == full_slots
    assert month_label(target) in _panel_head(app)
    in_fragment = (json.dumps(_chart_spec(app, PROCESS_DETAIL_CANVAS_CHART_KEY)), _panel_head(app))

    # 같은 달의 앱 전체 회차 — 그림과 근거 패널 머리가 같다.
    browser.fragment_queue = []
    _ok(app.run())
    assert browser.started == [[]]
    assert (
        json.dumps(_chart_spec(app, PROCESS_DETAIL_CANVAS_CHART_KEY)),
        _panel_head(app),
    ) == in_fragment


def test_without_a_finished_app_run_a_month_step_escalates_to_the_whole_page(
    dynamic_databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """끝까지 돈 실행 표지(`app.py`)가 없는 회차 — 페이지만 띄운 이 하네스가 그렇다 — 의 ◀▶ 는
    프래그먼트만 돌리지 않고 앱 전체로 올린다(`rerun_app_unless_alone`). 표지가 있는 실제 앱에서
    프래그먼트만 한 번 도는 것은 `tests/test_app_navigation.py` 가 본다."""
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda **_: None)
    browser = install_fragment_browser(monkeypatch)
    app = _app(dynamic_databases)
    app.query_params["process"] = DYNAMIC_PROCESS
    _ok(app.run())
    view = browser.fragment_keyed(PROCESS_DETAIL_VIEW_FRAGMENT_KEY)
    months = _months(app)
    app.session_state[PROCESS_DETAIL_MONTH_KEY] = months[0]
    _ok(app.run())

    browser.fragment_queue = [view]
    app.button(key=NEXT_MONTH_KEY).click()
    _ok(app.run())
    assert browser.started[-1] == []
    assert app.session_state[PROCESS_DETAIL_MONTH_KEY] == months[1]
    assert month_label(months[1]) in _panel_head(app)


# ------------------------------------------------------------------ 제약 시뮬레이션 링크


def _constraint_links(app: AppTest) -> list[dict[str, Any]]:
    return [
        link
        for link in app.session_state["captured_page_links"]
        if link["page"] == CONSTRAINT_SIMULATION.path
    ]


def test_the_header_links_this_process_to_the_constraint_simulation(
    dynamic_databases: tuple[Path, Path],
) -> None:
    """머리 「이 공정 제약 시뮬레이션」 — 주소 인자는 원본 공정명(+ 테마)뿐, 설비 일정이 서므로 켜져
    있다."""
    app = _app(dynamic_databases)
    app.query_params["process"] = DYNAMIC_PROCESS
    app.query_params["theme"] = "dark"
    _ok(app.run())
    (link,) = _constraint_links(app)
    assert link["label"] == "이 공정 제약 시뮬레이션"
    assert link["query_params"] == {"process": DYNAMIC_PROCESS, "theme": "dark"}
    assert link["disabled"] is False
    assert link["help"] is None


def test_the_constraint_link_is_disabled_with_its_reason_without_equipment(
    databases: tuple[Path, Path], dynamic_databases: tuple[Path, Path]
) -> None:
    """설비 일정이 서지 않는 공정이면 링크는 자리를 지킨 채 꺼지고 풍선이 까닭을 말한다(D11)."""
    empty = _ok(_app(databases).run())
    (link,) = _constraint_links(empty)
    assert link["disabled"] is True
    assert link["help"] == "설비 일정이 서야 엽니다 — 저장본 없음"

    other = _app(dynamic_databases)
    other.query_params["process"] = "DEMO_Final_Test"
    _ok(other.run())
    (link,) = _constraint_links(other)
    assert link["disabled"] is True
    assert link["help"] == "설비 일정이 서야 엽니다 — 설비 없음"
