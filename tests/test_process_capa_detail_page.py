# Purpose: 공정 Capa 상세가 내장 시드로 열리고 공정 선택·주소 인자·HOME 전달 칸으로 들어오는지 본다.

"""공정 Capa 상세의 진입·선택 흐름(화면 조립 전 골격).

페이지만 띄운다(`test_all_pages_render` 와 같은 하네스 — 내장 시드를 임시 DuckDB 에 부트스트랩).
HOME 칸 클릭 자체는 AppTest 가 재현하지 못하므로 콜백이 남기는 것(전달 칸·주소 인자)을 넣고 돌린다
(`tests/test_process_detail_state.py` 가 콜백 쪽을 본다).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.navigation import PROCESS_CAPA_DETAIL
from capa_simulation.process_detail_state import (
    HOME_BOTTLENECK_SECTION,
    ORIGIN_BAND_ICON,
    PROCESS_DETAIL_MONTH_KEY,
    PROCESS_DETAIL_PROCESS_KEY,
    PROCESS_DETAIL_REQUEST_KEY,
    ProcessDetailRequest,
)
from capa_simulation.services.month_columns import month_label

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / PROCESS_CAPA_DETAIL.path
ASSEMBLY_NOTICE = "화면 조립 중"


def _page_script(database_path: Path, equipment_path: Path, *, fail_bootstrap: bool = False) -> str:
    """`fail_bootstrap` 이면 공통 진입(`load_page_context`)이 오류를 내는 회차를 흉내 낸다."""
    return f"""
from pathlib import Path

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.components.month_range_picker as month_range_picker
import capa_simulation.page_bootstrap as page_bootstrap
import capa_simulation.settings as settings

original_database_path = settings.DUCKDB_PATH
original_equipment_path = settings.EQUIPMENT_DUCKDB_PATH
original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
original_month_picker = month_range_picker.render_month_range_apply
original_load_page_context = page_bootstrap.load_page_context

settings.DUCKDB_PATH = Path({str(database_path)!r})
settings.EQUIPMENT_DUCKDB_PATH = Path({str(equipment_path)!r})
horizontal_scrollbar.render_horizontal_scrollbar = lambda *args, **kwargs: None
month_range_picker.render_month_range_apply = (
    lambda *, start, end, min_month, max_month, key: None
)


def _failing_page_context():
    raise ValueError("시험용 진입 오류")


if {fail_bootstrap!r}:
    page_bootstrap.load_page_context = _failing_page_context

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
"""


@pytest.fixture(scope="module")
def databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """내장 시드 부트스트랩은 멱등이라 모듈 안에서 DuckDB 두 개를 다시 쓴다."""
    root = tmp_path_factory.mktemp("process_capa_detail")
    return root / "scenario.duckdb", root / "equipment.duckdb"


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


def _shown(app: AppTest) -> str:
    """골격이 지금 공정·달을 적는 한 줄(`**공정** · YY.MM`)."""
    lines = [str(element.value) for element in app.markdown if " · " in str(element.value)]
    assert lines, [str(element.value) for element in app.markdown]
    return lines[-1]


def test_the_page_opens_with_a_process_and_a_month_and_the_assembly_notice(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())

    process_box = app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY)
    assert process_box.value in process_box.options
    month = app.session_state[PROCESS_DETAIL_MONTH_KEY]
    assert isinstance(month, int)
    assert _shown(app) == f"**{process_box.value}** · {month_label(month)}"
    assert any(ASSEMBLY_NOTICE in str(element.value) for element in app.caption)
    # HOME 에서 오지 않았으므로 출처 띠가 없다.
    assert _origin_bands(app) == []


def test_a_chosen_process_survives_reruns(databases: tuple[Path, Path]) -> None:
    app = _ok(_app(databases).run())
    process_box = app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY)
    other = next(option for option in process_box.options if option != process_box.value)

    process_box.set_value(other)
    _ok(app.run())
    assert app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).value == other
    _ok(app.run())
    assert app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).value == other
    assert _shown(app).startswith(f"**{other}**")


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
        "표시 103% = 원 확보율 98% + 실행 Capa +5.0%p · 아래는 원 확보율"
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
