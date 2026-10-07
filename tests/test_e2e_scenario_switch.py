# Purpose: 실제 app.py 로 시나리오 전환의 토글 해제·보던 자리 유지·새 수치 반영을 고정한다.

"""시나리오를 바꾸면 **값에 닿는 것만** 풀리고, 보던 자리는 그대로 남는다.

이 검사가 실제 `app.py` 를 돌리는 이유는 결함의 원인이 **차례**였기 때문이다. 사이드바
「불러오기」는 `activate_persisted_snapshot` 을 부른 뒤 그 자리에서 `st.rerun()` 을 부르고,
그 호출은 실행을 끊어 **페이지 본문이 그 회차에 아예 돌지 않는다.** Streamlit 은 한 회차에
만들어지지 않은 위젯의 값을 버리므로, 사이드바만 도는 이 한 회차에서 페이지의 탭·필터가
통째로 초기값으로 돌아갔다. 페이지를 따로 띄워 보는 검사로는 이 차례가 재현되지 않는다 —
사이드바가 먼저 돌고 그 안에서 실행이 끊기는 것은 `app.py` 뿐이다.

고정하는 것은 셋이다.

1. HOME 토글 일곱 개가 **전부 풀린다.** 토글은 모두 기준정보 위에 무언가를 얹거나 빼는
   스위치라 앞 시나리오를 전제로 켠 것이 새 계획 위에 남으면 안 된다.
2. 같은 전환에서 **탭과 조회 조건은 남는다.** 무엇을 보고 있는지는 값에 닿지 않는다.
3. 전환 뒤 화면이 **새 리비전의 수치**를 보여 준다. 옛 그림이 캐시에 남아 있으면 안 된다.

전환을 모듈 스코프에서 한 줄기로 돌리고 그때 본 것을 아래 검사들이 나눠 본다. HOME 한
회차가 무겁기 때문이며, 검사마다 앱을 다시 띄우면 같은 사실을 여러 번 사는 셈이다.

**조회 조건은 두 갈래라 따로 본다.** HOME 의 조회기간·판정 기준·공정 선택은 리비전 프리셋
소유라 전환 때 `apply_pending_scenario_preset` 이 되살리고, 산출 결과의 집계 수준·상세처럼
어디에도 저장되지 않는 값은 위젯에 준 `persist_state="session"` 만으로 버틴다. 앞엣것에
`persist_state` 검사를 걸면 프리셋이 덮어써 주기 때문에 무엇을 지워도 통과한다.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.components.intro_overlay as intro_overlay
import capa_simulation.components.intro_summary as intro_summary
import capa_simulation.components.month_range_picker as month_range_picker
import capa_simulation.settings as settings
from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.components.home_preference import (
    ADVANCE_SHIPMENT_TOGGLE_KEY,
    ADVANCE_TOGGLE_KEY,
    COMPARISON_TOGGLE_KEY,
    EDP_TOGGLE_KEY,
    EXECUTION_TOGGLE_KEY,
    PAST_DATA_TOGGLE_KEY,
    PLAN_DETAIL_CUSTOMER_KEY,
)
from capa_simulation.components.scenario_status import SIDEBAR_REVISION_KEY
from capa_simulation.components.tab_state import remembered_tab_key
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import ACTIVE_PERSISTED_REVISION_ID_KEY
from capa_simulation.scenario_preset_state import (
    MONTH_RANGE_KEY,
    PROCESS_SELECTION_KEY,
    SECURE_THRESHOLD_KEY,
    WARNING_THRESHOLD_KEY,
)
from capa_simulation.settings import MONTH_SELECTION_END, MONTH_SELECTION_START, format_month

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"
LOAD_BUTTON_KEY = "sidebar_load_revision"
HOME_TAB_KEY = "home_active_tab"

# 프리셋에 딸리지 않은 **페이지 국소** 조회 조건. HOME 의 조회 조건은 전부 리비전 프리셋
# 소유라 전환에서 프리셋이 되살린다 — `persist_state="session"` 이 실제 앱 차례에서 듣는지는
# 프리셋 밖 위젯에서만 드러나므로 산출 결과 페이지에서 확인한다.
RESULT_PAGE = "app_pages/calculation_result.py"
DETAIL_LEVEL_KEY = "unit_capacity_detail_level"
REQUIRED_DETAIL_KEY = "required_equipment_detail"
PAGE_FILTER_KEYS = (DETAIL_LEVEL_KEY, REQUIRED_DETAIL_KEY)

# 일곱 토글의 기본값. 「풀린다」는 이 값으로 돌아간다는 뜻이고, `Past Data 포함` 만 켬이라
# 여섯은 꺼지고 하나는 켜진다. 목록이 일곱인지 지키는 것은 `tests/test_scenario_activation.py`
# 의 AST 그물이고, 여기서는 그 일곱이 **실제 실행에서** 풀리는지만 본다.
TOGGLE_DEFAULTS: Mapping[str, bool] = {
    ADVANCE_TOGGLE_KEY: False,
    ADVANCE_SHIPMENT_TOGGLE_KEY: False,
    EXECUTION_TOGGLE_KEY: False,
    COMPARISON_TOGGLE_KEY: False,
    PLAN_DETAIL_CUSTOMER_KEY: False,
    EDP_TOGGLE_KEY: False,
    PAST_DATA_TOGGLE_KEY: True,
}

# 전환을 사이 두고 비교할 조회 조건. 셋 다 **리비전 프리셋 소유**라 전환 때마다
# `apply_pending_scenario_preset` 이 위젯보다 먼저 덮어쓴다. 같은 프리셋을 가진 리비전으로
# 옮기면 값이 그대로여야 하고, 앱 기본값으로 떨어졌다면 프리셋이 아니라 초기값이 올라온 것이다.
VIEW_CONDITION_KEYS = (MONTH_RANGE_KEY, SECURE_THRESHOLD_KEY, WARNING_THRESHOLD_KEY)

# 앱 전체 기본 조회기간. 전환이 조회 조건을 버리면 화면이 되돌아가는 자리다.
APP_DEFAULT_MONTH_RANGE = (format_month(MONTH_SELECTION_START), format_month(MONTH_SELECTION_END))

# 화면에 그려진 Figure 의 지문. AppTest 에는 plotly 접근자가 없어 `st.plotly_chart` 를 감싼다.
_DRAWN_FIGURES: list[str] = []


def _figure_fingerprint(figure: object) -> str:
    """월별 숫자는 trace 의 `text`·`customdata` 에 실린다.

    numpy 배열이라 진리값 비교를 피하고 문자열로 모은다. 좌표까지 훑지 않는 이유는 계획이
    달라지면 이 둘이 반드시 달라지기 때문이다 — 화면에 적히는 숫자가 그 자리에 있다.
    """
    prints: list[str] = []
    for trace in getattr(figure, "data", []) or []:
        prints.append(str(getattr(trace, "text", None)))
        prints.append(str(getattr(trace, "customdata", None)))
    return "|".join(prints)


def _month_range_stub(
    *, start: str, end: str, min_month: str, max_month: str, key: str
) -> tuple[str, str]:
    """조회기간 피커는 Components v2 라 AppTest 인스턴스에 등록되어 있지 않다.

    받은 구간을 그대로 돌려준다. 이 검사의 관심은 피커의 그림이 아니라 **세션에 남은
    구간**이므로, 실제 위젯이 하는 일 중 여기서 필요한 것은 그것뿐이다.
    """
    return start, end


def _session_value(app: AppTest, key: str) -> Any:
    return app.session_state[key] if key in app.session_state else None


def _toggle_values(app: AppTest) -> dict[str, Any]:
    """토글을 **화면이 읽는 방식으로** 읽는다 — 칸이 없으면 기본값이다.

    일곱 토글은 사이드바 `LOB 표시 조건` 카드라 Main 이 아닌 탭에서는 위젯이 그려지지 않는다.
    전환이 칸을 버리고 나면 Main 을 열기 전까지 칸 자체가 없는데, `app_pages/home.py` 는
    그 자리를 `st.session_state.get(키, 기본값)` 으로 읽으므로 없는 것이 곧 기본값이다.
    없는 칸을 「풀리지 않았다」로 세면 실제와 다른 실패가 된다.
    """
    return {
        key: app.session_state[key] if key in app.session_state else default
        for key, default in TOGGLE_DEFAULTS.items()
    }


def _shown_toggle_values(app: AppTest, held: Mapping[str, bool]) -> dict[str, bool]:
    """사이드바 토글이 **브라우저에 보이는** 값.

    AppTest 의 위젯 값(`toggle.value`)은 서버 세션에서 읽고, 다음 실행에 보내는 위젯 상태도
    거기서 만든다. 그래서 「브라우저는 옛 값을 들고 있다가 되보낸다」가 AppTest 에서는 저절로
    일어나지 않는다 — 시나리오를 불러온 뒤 토글이 화면에는 켜진 채 남던 결함(2026-10-08 안정화
    점검 B1)을 서버 값만 보던 이 파일이 못 잡은 까닭이다.

    브라우저는 서버가 그 위젯에 `set_value` 를 실어 보낼 때만 값을 바꾼다. 아니면 들고 있던
    값(`held`)을, 새로 붙는 위젯이면 위젯 기본값(`proto.default`)을 보인다. 그 규칙을 여기서
    흉내 낸다.
    """
    shown: dict[str, bool] = {}
    for toggle in app.sidebar.toggle:
        key = str(toggle.key)
        if toggle.proto.set_value:
            shown[key] = bool(toggle.proto.value)
        else:
            shown[key] = held.get(key, bool(toggle.proto.default))
    return shown


def _tab_label(app: AppTest, needle: str) -> str:
    """라벨을 손으로 적지 않는다. 아이콘 접두사가 붙어 있어 화면에서 읽어 오는 편이 낫다."""
    for tab in app.tabs:
        if needle in tab.label:
            return str(tab.label)
    raise AssertionError(f"`{needle}` 탭을 찾지 못했습니다: {[tab.label for tab in app.tabs]}")


@dataclass(frozen=True)
class SwitchObservation:
    """전환 한 번을 앞뒤로 관찰한 것. 아래 검사들이 이 기록만 본다."""

    failures: tuple[str, ...]
    toggles_before: Mapping[str, Any]
    toggles_after: Mapping[str, Any]
    toggles_after_main: Mapping[str, Any]
    toggles_shown_after_main: Mapping[str, bool]
    drawn_toggle_keys: tuple[str, ...]
    view_before: Mapping[str, Any]
    view_after: Mapping[str, Any]
    tab_before: str
    tab_after: Any
    remembered_tab_after: Any
    processes_before: Any
    processes_after: Any
    numbers_before: tuple[str, ...]
    numbers_after: tuple[str, ...]
    numbers_during_switch: tuple[str, ...]
    loaded_revision_id: str
    active_revision_before: Any
    active_revision_after: Any
    page_filter_defaults: Mapping[str, Any]
    page_filters_chosen: Mapping[str, Any]
    page_filters_after: Mapping[str, Any]
    returned_revision_id: str
    active_revision_returned: Any


def _seed_two_revisions(database: Path) -> tuple[str, str]:
    """내장 시드 공식버전 하나와, 계획만 두 배로 키운 리비전 하나를 만든다.

    두 배로 키우는 것은 `RQ_PKG_PLAN` 의 생산수량뿐이다. 계획이 달라지면 부하량·확보율을
    거쳐 HOME 의 숫자가 전부 달라지므로, 「옛 수치가 남았는지」를 한 지문으로 가를 수 있다.
    정수 배라 컬럼 dtype 도 그대로다.

    프리셋은 **그대로 물려준다.** 조회 조건은 리비전 프리셋 소유라, 프리셋이 다르면
    「전환 뒤에도 조회 조건이 남는가」와 「새 프리셋이 적용되는가」가 한 검사에서 섞인다.
    """
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    bootstrap = ensure_initial_scenario(repository)
    assert bootstrap.release is not None, "내장 시드 공식버전이 만들어지지 않았습니다."
    baseline = repository.load_revision(bootstrap.release.revision_id)

    doubled = {name: frame.copy() for name, frame in baseline.tables.items()}
    plan = doubled["RQ_PKG_PLAN"]
    plan["생산수량"] = plan["생산수량"] * 2
    other = repository.save_revision(
        baseline.scenario.scenario_id,
        doubled,
        baseline.preset,
        revision_name="계획 2배",
        note="시나리오 전환 검사용",
    )
    # 「GAP」 토글은 비교 대상이 있어야 눌린다. 일곱 토글을 모두 켜 두려면 여기서 심는다.
    repository.replace_global_comparison_scenario(
        baseline.scenario.scenario_id,
        baseline.revision.revision_id,
        source="시나리오 전환 검사",
    )
    return str(baseline.revision.revision_id), str(other.revision.revision_id)


@pytest.fixture(scope="module")
def switch(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SwitchObservation]:
    """앱을 띄우고 → 토글을 켜고 → 다른 리비전을 불러오고 → 다시 본다.

    DuckDB 는 프로세스 배타 잠금이라 반드시 `tmp_path` 에 만든 DB 를 쓴다. 운영 DB 를
    가리키는 기본값이 한 군데라도 남아 있으면 앱 서버가 떠 있는 개발 PC 에서 이 검사가
    `duckdb.IOException` 으로 죽는다. 사이드바 시나리오 상자도 기본 경로를 부를 때
    `settings` 에서 찾으므로 `settings.DUCKDB_PATH` 하나만 바꾸면 된다.
    """
    database = tmp_path_factory.mktemp("e2e_scenario_switch") / "scenario.duckdb"
    baseline_revision_id, other_revision_id = _seed_two_revisions(database)

    failures: list[str] = []
    original_plotly_chart = st.plotly_chart

    def _spy_plotly_chart(figure: object, *args: Any, **kwargs: Any) -> Any:
        _DRAWN_FIGURES.append(_figure_fingerprint(figure))
        return original_plotly_chart(figure, *args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "DUCKDB_PATH", database)
        patch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", database.parent / "equipment.duckdb")
        patch.setattr(month_range_picker, "render_month_range_picker", _month_range_stub)
        patch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
        patch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
        patch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
        patch.setattr(st, "plotly_chart", _spy_plotly_chart)

        app = AppTest.from_file(str(APP_PATH), default_timeout=600)

        # 1. 공식버전이 올라온 첫 화면. Main 탭의 숫자를 지문으로 남긴다.
        _DRAWN_FIGURES.clear()
        app.run()
        failures.extend(f"첫 화면: {element.message}" for element in app.exception)
        numbers_before = tuple(_DRAWN_FIGURES)
        preference_tab = _tab_label(app, "Preference")
        main_tab = _tab_label(app, "Main")

        # 2. 사용자가 일곱 토글을 모두 기본값과 다르게 두고, Preference 탭을 보고 있다.
        for key, default in TOGGLE_DEFAULTS.items():
            app.session_state[key] = not default
        app.session_state[HOME_TAB_KEY] = preference_tab
        app.run()
        failures.extend(f"토글을 켠 화면: {element.message}" for element in app.exception)
        toggles_before = _toggle_values(app)
        view_before = {key: _session_value(app, key) for key in VIEW_CONDITION_KEYS}
        processes_before = _session_value(app, PROCESS_SELECTION_KEY)
        active_revision_before = _session_value(app, ACTIVE_PERSISTED_REVISION_ID_KEY)

        # 3. 사이드바에서 다른 리비전을 골라 「불러오기」를 누른다. 이 한 번 안에서
        #    `st.rerun()` 이 실행을 끊고, 사이드바만 돈 회차가 페이지 위젯 값을 버린다.
        app.session_state[SIDEBAR_REVISION_KEY] = other_revision_id
        _DRAWN_FIGURES.clear()
        app.button(LOAD_BUTTON_KEY).click().run()
        failures.extend(f"불러온 직후: {element.message}" for element in app.exception)
        numbers_during_switch = tuple(_DRAWN_FIGURES)
        toggles_after = _toggle_values(app)
        view_after = {key: _session_value(app, key) for key in VIEW_CONDITION_KEYS}
        processes_after = _session_value(app, PROCESS_SELECTION_KEY)
        tab_after = _session_value(app, HOME_TAB_KEY)
        remembered_tab_after = _session_value(app, remembered_tab_key(HOME_TAB_KEY))
        active_revision_after = _session_value(app, ACTIVE_PERSISTED_REVISION_ID_KEY)

        # 4. Main 으로 돌아와 새 수치를 확인한다. 숨은 탭은 Figure 를 그리지 않으므로
        #    (`render_home_figures` 가 `owner_tab` 으로 건너뛴다) 여기서만 지문이 나온다.
        app.session_state[HOME_TAB_KEY] = main_tab
        _DRAWN_FIGURES.clear()
        app.run()
        failures.extend(f"전환 뒤 Main 탭: {element.message}" for element in app.exception)
        numbers_after = tuple(_DRAWN_FIGURES)
        # Main 에서는 일곱 토글이 모두 다시 그려진다. 숨은 탭에서 칸이 없던 「상세 계획」까지
        # 실제 위젯 값으로 확인할 수 있는 자리가 여기다.
        toggles_after_main = _toggle_values(app)
        # 전환 회차의 화면은 Preference 라 카드가 없었다 — 브라우저에는 다시 새로 붙는 위젯이다.
        toggles_shown_after_main = _shown_toggle_values(app, {})
        drawn_toggle_keys = tuple(str(toggle.key) for toggle in app.toggle)

        # 5. 페이지 국소 조회 조건을 건드린 뒤 **그 페이지에서** 다시 불러온다. 프리셋이
        #    되살려 주지 않는 값이라, 사이드바만 도는 회차를 견디는 것은 위젯에 준
        #    `persist_state="session"` 뿐이다. 두 값이 다시 기본값으로 뜨면 사용자에게는
        #    「처음 열었을 때로 돌아갔다」로 보인다.
        app.switch_page(RESULT_PAGE)
        app.run()
        failures.extend(f"산출 결과 첫 화면: {element.message}" for element in app.exception)
        page_filter_defaults = {key: _session_value(app, key) for key in PAGE_FILTER_KEYS}
        level_options = list(app.selectbox(DETAIL_LEVEL_KEY).options)
        assert len(level_options) > 1, (
            "집계 수준 선택지가 하나뿐이라 기본값과 다른 값을 고를 수 없습니다."
        )
        app.session_state[DETAIL_LEVEL_KEY] = level_options[-1]
        app.session_state[REQUIRED_DETAIL_KEY] = True
        app.run()
        failures.extend(f"조회 조건을 바꾼 화면: {element.message}" for element in app.exception)
        page_filters_chosen = {key: _session_value(app, key) for key in PAGE_FILTER_KEYS}

        app.session_state[SIDEBAR_REVISION_KEY] = baseline_revision_id
        app.button(LOAD_BUTTON_KEY).click().run()
        failures.extend(f"산출 결과에서 불러온 뒤: {element.message}" for element in app.exception)
        page_filters_after = {key: _session_value(app, key) for key in PAGE_FILTER_KEYS}
        active_revision_returned = _session_value(app, ACTIVE_PERSISTED_REVISION_ID_KEY)

        yield SwitchObservation(
            failures=tuple(failures),
            toggles_before=toggles_before,
            toggles_after=toggles_after,
            toggles_after_main=toggles_after_main,
            toggles_shown_after_main=toggles_shown_after_main,
            drawn_toggle_keys=drawn_toggle_keys,
            view_before=view_before,
            view_after=view_after,
            tab_before=preference_tab,
            tab_after=tab_after,
            remembered_tab_after=remembered_tab_after,
            processes_before=processes_before,
            processes_after=processes_after,
            numbers_before=numbers_before,
            numbers_after=numbers_after,
            numbers_during_switch=numbers_during_switch,
            loaded_revision_id=other_revision_id,
            active_revision_before=active_revision_before,
            active_revision_after=active_revision_after,
            page_filter_defaults=page_filter_defaults,
            page_filters_chosen=page_filters_chosen,
            page_filters_after=page_filters_after,
            returned_revision_id=baseline_revision_id,
            active_revision_returned=active_revision_returned,
        )


def test_the_whole_switch_runs_without_an_exception(switch: SwitchObservation) -> None:
    """어느 회차에서도 예외가 뜨지 않는다. 뜨면 아래 검사가 보는 값은 읽을 것이 못 된다."""
    assert not switch.failures, "\n".join(switch.failures)


def test_the_user_really_had_every_toggle_flipped(switch: SwitchObservation) -> None:
    """전제 확인. 켜지지 않았다면 「풀렸다」는 뒤의 검사가 아무것도 보지 않은 것이 된다."""
    flipped = {key: not default for key, default in TOGGLE_DEFAULTS.items()}
    assert switch.toggles_before == flipped


def test_loading_another_revision_releases_every_home_toggle(switch: SwitchObservation) -> None:
    """일곱 토글이 **전부** 기본값으로 돌아간다.

    토글은 모두 기준정보 위에 무언가를 얹거나 빼는 스위치이고, 켠 사람은 **그 시나리오**를
    보며 켰다. 켠 채로 바뀌면 얹힌 것이 새 계획 위에 남는데 — 실행 Capa 증감은 확보율을
    통해 B/N 순위·Top5 막대·히트맵까지 바꾼다 — 화면에는 토글이 켜져 있으니 사용자는 그것을
    새 시나리오의 원래 값으로 읽는다.

    `Past Data 포함` 만 기본값이 켬이라 「풀린다」가 켜진 상태로 돌아간다는 뜻이다.
    """
    still_flipped = {
        key: value for key, value in switch.toggles_after.items() if value != TOGGLE_DEFAULTS[key]
    }
    assert not still_flipped, (
        "시나리오를 바꿨는데 HOME 토글이 앞 시나리오의 상태로 남았습니다: "
        f"{still_flipped} (기본값: {dict(TOGGLE_DEFAULTS)})"
    )


def test_the_released_toggles_are_still_released_back_on_the_main_tab(
    switch: SwitchObservation,
) -> None:
    """Main 으로 돌아와 일곱 위젯이 다시 그려져도 기본값이다.

    전환 회차의 화면은 Preference 탭이라 토글 칸(사이드바 카드)이 아예 없었다. 그 칸이 다시
    생기는 자리가 여기이므로, 풀린 것이 **위젯 값으로도** 풀렸는지는 여기서만 확인된다.
    Main 에서 카드의 위젯을 직접 켠 채 전환하는 흔한 경우는 아래 따로 본다.
    그래서 칸이 있는지부터 본다 — 없는 칸을 기본값으로 읽으면 이 검사가 저절로 통과한다.
    """
    missing = [key for key in TOGGLE_DEFAULTS if key not in switch.drawn_toggle_keys]
    assert not missing, f"Main 탭인데 토글 위젯이 그려지지 않았습니다: {missing}"
    assert switch.toggles_after_main == dict(TOGGLE_DEFAULTS)
    # 서버 값만이 아니라 **브라우저가 보이는 값**도 기본값이다. 위젯은 기본값을 `value=` 로
    # 받지 않으므로(`Past Data 포함` 의 위젯 기본은 끔), 켬은 서버가 밀어 줘야 보인다.
    assert switch.toggles_shown_after_main == dict(TOGGLE_DEFAULTS)


def test_the_open_tab_survives_the_same_load(switch: SwitchObservation) -> None:
    """같은 전환에서 보던 탭은 남는다.

    「불러오기」가 부르는 `st.rerun()` 은 사이드바에서 실행을 끊으므로 페이지 본문이 그
    회차에 돌지 않고, Streamlit 은 그 회차에 만들어지지 않은 위젯의 값을 버린다. 되돌려
    놓는 것은 `stateful_tabs` 가 위젯 아닌 칸에 적어 둔 기억이다.
    """
    assert switch.remembered_tab_after == switch.tab_before
    assert switch.tab_after == switch.tab_before, (
        "시나리오를 바꾸니 보던 탭이 첫 칸으로 돌아갔습니다. "
        f"기대: {switch.tab_before}, 실제: {switch.tab_after}"
    )


def test_the_preset_owned_conditions_come_back_from_the_loaded_revision(
    switch: SwitchObservation,
) -> None:
    """조회기간·판정 기준·공정 선택은 **불러온 리비전의 프리셋**에서 온다.

    이 셋은 `persist_state` 가 지키는 값이 아니다. 전환마다 `apply_pending_scenario_preset`
    이 위젯보다 먼저 세션에 덮어쓰므로, 여기서 보는 것은 「위젯 값이 살아남았는가」가 아니라
    **「불러온 리비전의 값이 올라왔는가, 앱 기본값으로 떨어지지 않았는가」**다. 두 리비전에
    같은 프리셋을 물려 둔 것이 그래서다 — 값이 그대로인 것이 정상이고, 앱 기본 조회기간으로
    돌아갔다면 프리셋이 아니라 초기값이 올라온 것이다.

    프리셋 밖 조회 조건이 사이드바 회차를 견디는지는 아래 페이지 국소 필터 검사가 본다.
    """
    assert switch.view_before[MONTH_RANGE_KEY] != APP_DEFAULT_MONTH_RANGE, (
        "검사 전제가 무너졌습니다 — 시드 프리셋의 조회기간이 앱 기본값과 같으면 "
        "값을 잃어도 드러나지 않습니다."
    )
    assert switch.view_after == switch.view_before, (
        "시나리오를 바꾸니 조회 조건이 달라졌습니다. "
        f"기대: {dict(switch.view_before)}, 실제: {dict(switch.view_after)}"
    )
    assert list(switch.processes_after or []) == list(switch.processes_before or [])


def test_a_page_local_filter_survives_a_load_from_that_page(switch: SwitchObservation) -> None:
    """프리셋 밖 조회 조건은 전환을 그대로 건너간다.

    산출 결과의 「집계 수준」·「상세」는 어느 리비전에도 저장되지 않는 값이라 되살려 줄
    프리셋이 없다. 「불러오기」가 부른 `st.rerun()` 이 사이드바에서 실행을 끊어 페이지 본문이
    그 회차에 돌지 않으면 Streamlit 이 두 위젯의 값을 버리고, 사용자에게는 「시나리오만
    바꿨는데 화면이 처음 열었을 때로 돌아갔다」로 보인다. 견디게 하는 것은 위젯에 준
    `persist_state="session"` 하나뿐이다.
    """
    assert switch.active_revision_returned == switch.returned_revision_id, (
        "그 페이지에서 누른 「불러오기」가 리비전을 바꾸지 못했습니다 — 아래 비교는 "
        "아무것도 보지 않은 것이 됩니다."
    )
    assert dict(switch.page_filters_chosen) != dict(switch.page_filter_defaults), (
        "고른 값이 페이지 기본값과 같습니다 — 값을 잃어도 드러나지 않습니다."
    )
    assert switch.page_filters_after == dict(switch.page_filters_chosen), (
        "시나리오를 바꾸니 페이지 조회 조건이 초기값으로 돌아갔습니다. "
        f"고른 값: {dict(switch.page_filters_chosen)}, 전환 뒤: {dict(switch.page_filters_after)}"
    )


def test_the_dashboard_shows_the_new_revision_numbers(switch: SwitchObservation) -> None:
    """전환 뒤 화면에 옛 수치가 남지 않는다.

    새 리비전은 `RQ_PKG_PLAN` 의 생산수량만 두 배인 계획이다. Figure 캐시 칸이 전환에서
    지워지지 않으면 화면은 앞 리비전의 그림을 그대로 다시 건다 — 사용자에게는 「시나리오를
    바꿨는데 숫자가 그대로」로 보인다.
    """
    assert switch.numbers_before, "첫 화면이 Figure 를 하나도 그리지 않았습니다."
    assert switch.numbers_after, "전환 뒤 Main 탭이 Figure 를 하나도 그리지 않았습니다."
    assert switch.numbers_after != switch.numbers_before, (
        "리비전을 바꿨는데 화면 수치가 그대로입니다. 앞 시나리오의 Figure 가 그대로 남았습니다."
    )


def test_the_switch_actually_activated_the_other_revision(switch: SwitchObservation) -> None:
    """위 셋이 「아무 일도 없었다」로 통과하지 않게 전환 자체를 함께 못 박는다."""
    assert switch.active_revision_before != switch.loaded_revision_id
    assert switch.active_revision_after == switch.loaded_revision_id


def test_the_hidden_tab_draws_nothing_during_the_switch(switch: SwitchObservation) -> None:
    """전환 회차에는 Preference 탭만 열려 있어 무거운 Figure 를 그리지 않는다.

    이것이 깨지면 위 수치 검사가 아니라 **성능**이 먼저 무너진다 — 숨은 탭의 Figure 까지
    매 전환에 그리게 된다.
    """
    assert switch.numbers_during_switch == ()


def test_toggles_flipped_in_the_card_on_main_are_released_by_a_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """가장 흔한 경우 — Main 에서 사이드바 카드의 토글을 켠 채 다른 리비전을 불러온다.

    위의 모듈 시나리오는 Preference 탭에서 세션 값을 직접 바꾸므로 **그려진 위젯 값**이 풀리는지는
    보지 않는다. 여기서는 카드의 위젯으로 켜고, 불러오기 뒤 같은 위젯이 기본값으로 서는지 본다.

    서버 값만 보면 이 검사는 결함이 있을 때도 통과했다(2026-10-08 안정화 점검 B1). 불러오기가
    토글 칸을 지우기만 하자 서버는 기본값으로 그렸지만 브라우저에는 새 값을 보내지 않아 토글이
    켜진 채 보였고, 다음 조작이 그 옛 값을 되보내 토글이 되살아났다. 그래서 불러온 회차에
    서버가 **브라우저에 새 값을 보냈는지**(`set_value`)를 보고, 브라우저가 보이는 값을 그대로
    되보내는 다음 조작을 흉내 내 토글이 되살아나지 않는지 본다(`_shown_toggle_values`).
    """
    database = tmp_path / "scenario.duckdb"
    _, other = _seed_two_revisions(database)
    monkeypatch.setattr(settings, "DUCKDB_PATH", database)
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    monkeypatch.setattr(month_range_picker, "render_month_range_picker", _month_range_stub)
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    app = AppTest.from_file(str(APP_PATH), default_timeout=600)
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    # 첫 화면부터 브라우저에 기본값이 보인다 — `Past Data 포함` 의 켬은 카드가 세션에 심은 값이다.
    assert _shown_toggle_values(app, {}) == dict(TOGGLE_DEFAULTS)
    for key, default in TOGGLE_DEFAULTS.items():
        app.toggle(key=key).set_value(not default)
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    flipped = {key: not default for key, default in TOGGLE_DEFAULTS.items()}
    # GAP 은 비교 대상이 없으면 잠겨 계산에는 안 걸리지만 위젯 값은 켠 그대로다.
    assert {toggle.key: toggle.value for toggle in app.sidebar.toggle} == flipped
    assert _shown_toggle_values(app, flipped) == flipped

    app.session_state[SIDEBAR_REVISION_KEY] = other
    app.button(LOAD_BUTTON_KEY).click().run()
    assert not app.exception, [element.message for element in app.exception]
    assert {toggle.key: toggle.value for toggle in app.sidebar.toggle} == dict(TOGGLE_DEFAULTS)
    pushed = {
        str(toggle.key): (toggle.proto.set_value, toggle.proto.value)
        for toggle in app.sidebar.toggle
    }
    assert pushed == {key: (True, default) for key, default in TOGGLE_DEFAULTS.items()}, (
        "불러온 회차에 서버가 토글의 새 값을 브라우저에 보내지 않았습니다 — 화면에는 앞 "
        f"시나리오에서 켠 토글이 그대로 보입니다: {pushed}"
    )
    shown = _shown_toggle_values(app, flipped)
    assert shown == dict(TOGGLE_DEFAULTS)

    # 다음 조작 — 브라우저는 보이는 값을 그대로 되보낸다. 옛 값이 남아 있었다면 여기서 되살아난다.
    for toggle in app.sidebar.toggle:
        toggle.set_value(shown[str(toggle.key)])
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    assert {toggle.key: toggle.value for toggle in app.sidebar.toggle} == dict(TOGGLE_DEFAULTS)
    assert _shown_toggle_values(app, shown) == dict(TOGGLE_DEFAULTS)
