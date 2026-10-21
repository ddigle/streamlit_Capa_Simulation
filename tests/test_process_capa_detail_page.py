# Purpose: 공정 Capa 상세 화면의 진입·공정 왕복·펼침·달 고르기·설비 일정 구획·CSV·탭 링크를 본다.

"""공정 Capa 상세 화면(AppTest).

페이지만 띄운다(`test_all_pages_render` 와 같은 하네스 — 내장 시드를 임시 DuckDB 에 부트스트랩).
HOME 칸 클릭과 월 그림의 칸 선택은 AppTest 가 재현하지 못하므로 콜백이 남기는 것(전달 칸·주소
인자·세션 달)을 넣고 돌린다(`tests/test_process_detail_state.py`·`tests/test_process_capa_view.py`
가 콜백 쪽을 본다).

- 설비 DB 가 빈 하네스는 「설비 일정 없음: 저장본 없음」 카드와 ① 공식 기준만 선다.
- 설비 일정은 시드 공정 하나(`DEMO_Chip_Attach`)에 저장본·Cut-off 를 넣은 따로 된 하네스로 본다.
- 칸 누름·◀▶ 는 **진짜 프래그먼트 회차**(`tests/fragment_browser.py`)로 본문 프래그먼트만 도는지,
  그 회차가 이벤트 칸에 앱 전체 회차와 같은 수를 쓰는지 본다.
"""

from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fragment_browser import install_fragment_browser
from streamlit.proto.RootContainer_pb2 import RootContainer
from streamlit.testing.v1 import AppTest
from test_required_shortening import _cutoff, _downtime, _master, _unit

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.process_capa_view import (
    DYNAMIC_ERROR_TITLE,
    NEXT_MONTH_KEY,
    UNITS_CSV_KEY,
)
from capa_simulation.components.required_shortening_panel import SHORTENING_PROCESS_KEY
from capa_simulation.home_state import EXECUTION_TOGGLE_KEY
from capa_simulation.navigation import PROCESS_CAPA_DETAIL
from capa_simulation.persistence.cache import clear_global_execution_capacity_cache
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.process_detail_state import (
    HOME_BOTTLENECK_SECTION,
    ORIGIN_BAND_ICON,
    PROCESS_DETAIL_CANVAS_CHART_KEY,
    PROCESS_DETAIL_EXPAND_KEY,
    PROCESS_DETAIL_MONTH_KEY,
    PROCESS_DETAIL_PROCESS_KEY,
    PROCESS_DETAIL_PRODUCT_FILTER_KEY,
    PROCESS_DETAIL_REQUEST_KEY,
    PROCESS_DETAIL_SPLIT_KEY,
    PROCESS_DETAIL_VIEW_FRAGMENT_KEY,
    ProcessDetailRequest,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.required_shortening import UNIT_EXPORT_COLUMNS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / PROCESS_CAPA_DETAIL.path
DYNAMIC_PROCESS = "DEMO_Chip_Attach"
OFFICIAL_BADGE = "공식 · Core Data"


def _page_script(database_path: Path, equipment_path: Path, *, fail_bootstrap: bool = False) -> str:
    """`fail_bootstrap` 이면 공통 진입(`load_page_context`)이 오류를 내는 회차를 흉내 낸다.

    내려받기 단추는 받은 바이트를 세션 `captured_downloads` 에 적어 둔다(시험이 CSV 를 읽는다).
    """
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.components.month_range_picker as month_range_picker
import capa_simulation.page_bootstrap as page_bootstrap
import capa_simulation.settings as settings

original_database_path = settings.DUCKDB_PATH
original_equipment_path = settings.EQUIPMENT_DUCKDB_PATH
original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
original_month_picker = month_range_picker.render_month_range_apply
original_load_page_context = page_bootstrap.load_page_context
original_download_button = st.download_button

settings.DUCKDB_PATH = Path({str(database_path)!r})
settings.EQUIPMENT_DUCKDB_PATH = Path({str(equipment_path)!r})
horizontal_scrollbar.render_horizontal_scrollbar = lambda *args, **kwargs: None
month_range_picker.render_month_range_apply = (
    lambda *, start, end, min_month, max_month, key: None
)


def _failing_page_context():
    raise ValueError("시험용 진입 오류")


def _recording_download_button(label, *args, **kwargs):
    st.session_state.setdefault("captured_downloads", {{}})[kwargs.get("key")] = {{
        "data": kwargs.get("data"),
        "file_name": kwargs.get("file_name"),
    }}
    return original_download_button(label, *args, **kwargs)


if {fail_bootstrap!r}:
    page_bootstrap.load_page_context = _failing_page_context
st.download_button = _recording_download_button

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


def _label_texts(app: AppTest) -> str:
    """라벨 Figure 의 글자 전부(주석·글자 trace)."""
    return json.dumps(_chart_spec(app, "process_detail_summary_labels"), ensure_ascii=False)


# ------------------------------------------------------------------ 진입·선택


def test_the_page_opens_with_header_kpis_canvas_and_evidence_without_equipment(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())

    process_box = app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY)
    assert process_box.value in process_box.options
    month = app.session_state[PROCESS_DETAIL_MONTH_KEY]
    assert isinstance(month, int)
    header = _header(app)
    assert header.startswith(f"**{process_box.value}**")
    # 설비 DB 에 저장본이 없다 — 샘플 fleet 을 쓰지 않는다.
    assert "설비 일정 없음: 저장본 없음" in header
    assert [metric.label for metric in app.metric] == [
        "최저 확보율",
        "확보기준 미달",
        "부족 원인",
        "대책",
    ]
    assert app.metric[3].value == "일정 없음"
    # 결합 캔버스 — 라벨 Figure(정적)와 월 Figure(칸 선택).
    spec = _chart_spec(app, PROCESS_DETAIL_CANVAS_CHART_KEY)
    assert spec["layout"]["xaxis"]["range"][0] == 0
    assert "① 공식 기준" in _label_texts(app)
    assert "② 설비 일정 기준 가용" not in _label_texts(app)
    # 산출 근거 패널은 고른 달이고 카드는 ① ~ ③ 셋이다.
    assert _panel_head(app) == f"**산출 근거 · {month_label(month)} · {process_box.value}**"
    cards = next(body for body in _html(app) if "pcd-cards" in body)
    assert all(title in cards for title in ("① 소요", "② 가용", "③ 판정"))
    assert "④ 단축 근거" not in cards
    # 설비 일정 없음 카드와 가용설비 현황 링크(단독 실행은 글자로 물러선다).
    assert any("설비 마스터가 없습니다" in str(element.value) for element in app.caption)
    # 정리 줄(CSV·탭 링크)은 설비 일정이 설 때만이다.
    assert UNITS_CSV_KEY not in {str(button.key) for button in app.get("download_button")}
    # HOME 에서 오지 않았으므로 출처 띠가 없다.
    assert _origin_bands(app) == []
    # 머리 오른쪽 「← HOME」 링크(단독 실행은 갈 페이지가 없어 글자로 물러선다).
    assert any(str(element.value) == "사이드바에서 HOME" for element in app.caption)


def test_a_chosen_process_survives_reruns_and_keeps_the_month(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())
    process_box = app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY)
    other = next(option for option in process_box.options if option != process_box.value)
    months = _months(app)
    app.session_state[PROCESS_DETAIL_MONTH_KEY] = months[-1]
    _ok(app.run())

    app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).set_value(other)
    _ok(app.run())
    assert app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).value == other
    _ok(app.run())
    assert app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).value == other
    assert _header(app).startswith(f"**{other}**")
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
    assert not app.get("button_group")

    app.toggle(key=PROCESS_DETAIL_EXPAND_KEY).set_value(True)
    _ok(app.run())
    first_product = app.multiselect(key=PROCESS_DETAIL_PRODUCT_FILTER_KEY).options[0]
    assert "소요대수 ▾" in _label_texts(app)
    assert first_product in _label_texts(app)
    split = app.get("button_group")
    assert len(split) == 1
    # 공정 안에서 늘 한 값인 소요기준은 「분류」에 두지 않는다.
    options = [str(option) for option in split[0].proto.options]
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
    options = list(app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).options)
    first_month = app.session_state[PROCESS_DETAIL_MONTH_KEY]
    target = options[-1]

    app.query_params.update({"process": target, "month": str(first_month), "from": "home"})
    app.query_params["theme"] = "dark"
    _ok(app.run())

    assert app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).value == target
    assert app.session_state[PROCESS_DETAIL_MONTH_KEY] == first_month
    # 읽은 키만 지운다 — 테마 인자는 남는다.
    assert dict(app.query_params) == {"theme": ["dark"]}


@pytest.mark.parametrize(
    ("wanted", "shown"),
    [
        (
            "![x](http://h/p.png) [링크](http://h/q) A~B~C",
            f"「{literal_markdown('![x](http://h/p.png) [링크](http://h/q) A~B~C')}」은(는) ",
        ),
        # 조사는 escape 하기 전의 이름으로 고른다 — `\)` 의 `\` 로 고르면 「은(는)」이 된다.
        ("WB(2)", "「WB\\(2\\)」는 "),
    ],
    ids=["markdown", "particle"],
)
def test_an_address_process_outside_the_list_is_shown_as_literal_text(
    databases: tuple[Path, Path], wanted: str, shown: str
) -> None:
    """주소 인자 `?process=` 는 누구나 적어 보낼 수 있다 — 경고 상자에 마크다운으로 그리면
    링크 하나로 남의 화면에 외부 이미지·임의 링크를 띄운다."""
    app = _ok(_app(databases).run())
    options = list(app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).options)
    assert wanted not in options

    app.query_params["process"] = wanted
    _ok(app.run())

    bodies = [
        str(element.value) for element in app.warning if "넘겨받은 공정" in str(element.value)
    ]
    assert len(bodies) == 1, bodies
    assert shown in bodies[0]
    assert "![x](" not in bodies[0]
    assert "](http://h/q)" not in bodies[0]
    # 목록에 없는 공정이므로 기본 공정으로 열린다.
    assert app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).value in options


def test_the_home_transfer_slot_opens_the_cell_and_shows_the_origin_band(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())
    target = list(app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).options)[0]
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

    assert app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).value == target
    assert _origin_bands(app) == [
        f"{ORIGIN_BAND_ICON} HOME 상세 B/N 공정 · {month_label(month)} 칸에서 열었습니다 · "
        "표시 103% = 원 확보율 98% + 확보율 보정 +5.0%p · 아래는 원 확보율"
    ]
    # 알림 상자 세 색은 뜻으로 가른다 — 출처는 「조건에 맞는 것이 없다」(`st.info`)가 아니다.
    assert not any("칸에서 열었습니다" in str(element.value) for element in app.info)


def test_a_stopped_visit_consumes_the_transfer_slot(databases: tuple[Path, Path]) -> None:
    """공통 진입이 오류로 멈춘 회차도 전달 칸을 꺼낸다 — 남기면 나중에 사이드바로 들어온 방문이
    그 칸을 「HOME 에서 온 것」으로 읽어 거짓 출처 띠를 단다."""
    app = _app(databases, fail_bootstrap=True)
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process="DEMO-A", month=202603, section=HOME_BOTTLENECK_SECTION, displayed_rate=1.0
    )
    app.run()

    assert not app.exception, [element.message for element in app.exception]
    assert any("시험용 진입 오류" in str(element.value) for element in app.error)
    assert PROCESS_DETAIL_REQUEST_KEY not in app.session_state


def test_a_month_outside_the_page_axis_opens_the_default_month_with_a_notice(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())
    target = list(app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).options)[0]
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process=target, month=199001
    )
    _ok(app.run())

    assert isinstance(app.session_state[PROCESS_DETAIL_MONTH_KEY], int)
    assert any(
        "90.01" in str(element.value) and "밖이라" in str(element.value) for element in app.info
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
    process = str(app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).value)
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


# ------------------------------------------------------------------ 설비 일정(참고)


def _dynamic_app(dynamic_databases: tuple[Path, Path]) -> AppTest:
    app = _app(dynamic_databases)
    app.query_params["process"] = DYNAMIC_PROCESS
    return _ok(app.run())


def test_a_ready_process_draws_the_equipment_schedule_sections(
    dynamic_databases: tuple[Path, Path],
) -> None:
    app = _dynamic_app(dynamic_databases)

    assert app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).value == DYNAMIC_PROCESS
    assert "설비 일정 참고 · Cut-off 10일" in _header(app)
    labels = _label_texts(app)
    for title in ("② 설비 일정 기준 가용", "③ 신규 설비 일정과 단축", "④ 호기별 비가동"):
        assert title in labels
    assert "DA-01" in labels
    # 단축 목표는 HOME Preference 확보기준 표시뿐이다 — 고르는 위젯이 없다.
    assert any(
        "단축 목표 = HOME Preference 확보기준(월별)" in str(element.value)
        for element in app.caption
    )
    assert not app.get("selectbox")[1:]
    legend = next(body for body in _html(app) if "pcd-legend" in body)
    assert "칸 = 생산월 — Cut-off 10일이면" in legend
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


def test_the_shortening_link_plants_only_session_keys(dynamic_databases: tuple[Path, Path]) -> None:
    """필요 단축 일정 화면 링크는 공정 상자 세션 키만 심는다 — 공용 조회 조건(0019)에는 쓰지 않는다.
    필요 단축 일정은 가용설비 현황의 탭이 아니라 별도 화면이라(2026-10-18) 그 탭 칸도 건드리지
    않는다.

    단독 실행이라 갈 페이지가 없어 옮기지는 않는다(`StreamlitPageNotFoundError` 를 삼킨다).
    """
    app = _dynamic_app(dynamic_databases)
    app.button(key="process_detail_open_shortening_tab").click()
    _ok(app.run())

    assert "equipment_active_tab" not in app.session_state
    assert app.session_state[SHORTENING_PROCESS_KEY] == [DYNAMIC_PROCESS]
    repository = DuckDBEquipmentRepository(dynamic_databases[1])
    profile = repository.load_shortening_filter_profile()
    assert profile.processes == ()


def _absent_card_titles(app: AppTest) -> list[str]:
    return [str(element.value) for element in app.markdown if "event_busy" in str(element.value)]


def test_a_broken_equipment_database_keeps_the_official_section(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """설비 DB 를 못 읽어도 ① 공식 구획·KPI·근거 패널은 남는다. 머리 배지와 까닭 카드가 같은
    말이다."""
    root = tmp_path_factory.mktemp("process_capa_detail_broken_equipment")
    broken = root / "equipment.duckdb"
    broken.write_bytes(b"not a duckdb database file" * 100)
    app = _ok(_app((root / "scenario.duckdb", broken)).run())

    assert "설비 일정 없음: 설비 DB 오류" in _header(app)
    assert _absent_card_titles(app) == [
        ":material/event_busy: **설비 일정 없음: 설비 DB 를 읽지 못했습니다**"
    ]
    labels = _label_texts(app)
    assert "① 공식 기준" in labels and "② 설비 일정 기준 가용" not in labels
    assert [metric.label for metric in app.metric][0] == "최저 확보율"
    cards = next(body for body in _html(app) if "pcd-cards" in body)
    assert all(title in cards for title in ("① 소요", "② 가용", "③ 판정"))


def test_a_schedule_calculation_error_names_itself_and_keeps_the_official_section(
    dynamic_databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """판정은 통과했는데 설비 일정 계산이 멈추면 까닭 카드 제목이 머리 배지와 같은 「계산 오류」다 —
    「설비 일정 참고」로 서지 않고, 이미 맞은 조건(저장본·이름·Cut-off)을 까닭처럼 적지 않는다."""

    def fail(*args: object, **kwargs: object) -> None:
        raise ValueError("시험용 계산 오류")

    monkeypatch.setattr(simulation_cache, "get_process_equipment_timeline", fail)
    app = _dynamic_app(dynamic_databases)

    assert "설비 일정 없음: 계산 오류" in _header(app)
    assert _absent_card_titles(app) == [f":material/event_busy: **{DYNAMIC_ERROR_TITLE}**"]
    caption = next(str(item.value) for item in app.caption if "시험용 계산 오류" in str(item.value))
    assert caption.startswith("설비 일정을 계산하지 못했습니다")
    assert "Cut-off 가 적힌 공정에만" not in caption
    labels = _label_texts(app)
    assert "① 공식 기준" in labels and "② 설비 일정 기준 가용" not in labels
    # 정리 줄(CSV·탭 링크)은 설비 일정이 설 때만이다.
    assert UNITS_CSV_KEY not in {str(button.key) for button in app.get("download_button")}


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
