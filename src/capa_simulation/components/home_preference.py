# Purpose: HOME 의 LOB 표시 조건 카드·제목 줄과 Preference 탭 편집기를 그려 공용 프로필에 저장한다.

"""HOME 사이드바 `LOB 표시 조건` 카드, `Capa LOB 현황` 제목 줄, `Preference` 탭.

**화면을 보는 조건(선행·실행·GAP·상세·EDP·Past Data)은 사이드바 조건 카드**다(2026-09-29
사용자 결정 — 전에는 제목 줄과 Preference 의 `표시 기준` 상자에 흩어져 있었다). 탭에는 비교
시나리오·선행 투입 물량·`Summary 공지`·Top5 대역·주요공정·실행 Capa 편집기가 있고, 저장은 모두
공용 프로필 교체다. 저장 버튼은 편집 칸 **위**다. 설명은 Guide(`guides/home.md`)다.

토글 **값은 계산보다 먼저** 필요하고 **위젯은 계산 뒤에** 그려진다. 그래서 `app_pages/home.py`
는 위젯이 쓰는 세션 키를 직접 읽고, 여기서는 같은 키로 위젯을 만든다. 키와 기본값은 UI
의존성이 없는 `home_state` 에서 가져온다.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

import pandas as pd
import streamlit as st

from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.profile_caption import profile_version_caption
from capa_simulation.design import tokens
from capa_simulation.home_state import (
    ADVANCE_TOGGLE_KEY as ADVANCE_TOGGLE_KEY,
)
from capa_simulation.home_state import (
    COMPARISON_TOGGLE_KEY as COMPARISON_TOGGLE_KEY,
)
from capa_simulation.home_state import (
    EDP_TOGGLE_KEY as EDP_TOGGLE_KEY,
)
from capa_simulation.home_state import (
    EXECUTION_TOGGLE_KEY as EXECUTION_TOGGLE_KEY,
)
from capa_simulation.home_state import (
    HOME_TOGGLE_DEFAULTS,
)
from capa_simulation.home_state import (
    PAST_DATA_TOGGLE_KEY as PAST_DATA_TOGGLE_KEY,
)
from capa_simulation.home_state import (
    PLAN_DETAIL_CUSTOMER_KEY as PLAN_DETAIL_CUSTOMER_KEY,
)
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import (
    clear_global_advance_load_cache,
    clear_global_comparison_scenario_cache,
    clear_global_execution_capacity_cache,
    clear_global_key_process_cache,
    clear_global_summary_note_cache,
    clear_global_top5_band_cache,
    get_scenario_repository,
    load_global_comparison_scenario,
)
from capa_simulation.persistence.models import (
    GlobalAdvanceLoad,
    GlobalExecutionCapacity,
    GlobalKeyProcess,
    GlobalSummaryNote,
    GlobalTop5Band,
    RevisionSummary,
    ScenarioSummary,
)
from capa_simulation.scenario_activation import active_persisted_revision_id
from capa_simulation.services.advance_load import (
    ADVANCE_LOAD_ROW_LABEL,
    merge_advance_load_edits,
)
from capa_simulation.services.execution_capacity import (
    EXECUTION_CAPACITY_COLUMNS,
    empty_execution_capacity,
    prepare_execution_capacity,
)
from capa_simulation.services.key_process import KEY_PROCESS_LIMIT
from capa_simulation.services.month_columns import month_label
from capa_simulation.sidebar_status import condition_card

EXECUTION_EDITOR_KEY = "home_preference_execution_editor"
EXECUTION_NOTE_KEY = "home_preference_execution_note"
COMPARISON_SCENARIO_KEY = "home_preference_comparison_scenario"
COMPARISON_REVISION_KEY = "home_preference_comparison_revision"
ADVANCE_EDITOR_KEY = "home_preference_advance_editor"
ADVANCE_NOTE_KEY = "home_preference_advance_note"
DIMENSION_COLUMN = "구분"
# 구획 제목의 글자 크기와 앞 강조 막대의 치수. `home_rendering` 의 `Summary` 상자가 같은
# 값을 CSS 가상요소로 다시 그리므로 상수로 내보낸다 — 두 곳에 숫자를 따로 적으면 한쪽만
# 고쳐져 막대 크기가 어긋난다.
SECTION_TITLE_FONT_PX = 20
SECTION_BAR_WIDTH_PX = 4
SECTION_BAR_HEIGHT_PX = 18
SECTION_BAR_RADIUS_PX = 2
SECTION_BAR_GAP_PX = 8
STATUS_LEGEND_ROW_KEY = "home_status_legend"
# 범례 안쪽 div 의 클래스. 높이를 물려주는 CSS 가 이 이름을 읽는다.
STATUS_LEGEND_CLASS = "capa-status-legend"


def render_section_title_row(text: str, *, key: str) -> None:
    """구획 제목 줄. `Capa LOB 현황` 줄과 같은 높이·같은 모양이다.

    네 구획의 제목이 같은 컴포넌트로 그려져야 제목과 표 사이 간격이 하나로 맞는다.
    하나만 Plotly 주석으로 남겨 두면 그 구획만 간격이 다르다.
    """
    with st.container(key=key, horizontal=True, vertical_alignment="center", gap="medium"):
        st.markdown(section_title_markup(text), unsafe_allow_html=True)


def section_title_markup(text: str) -> str:
    """구획 제목 한 줄. Plotly 주석이 그리던 모양을 그대로 옮긴 것이다.

    앞의 강조 막대는 **글자가 아니라 그린 사각형**이다. `▍` 문자로 두면 막대 높이가 그
    글자가 상속한 글자 크기를 따라가는데, 제목 글자만 20px 로 키운 이 줄에서는 막대가
    본문 크기(작게)로 남고 `Summary` 상자처럼 제목 전체가 20px 인 곳에서는 크게 나온다.
    같은 막대가 화면마다 다른 크기로 보이던 이유가 그것이다. px 로 못 박으면 어디에 놓든
    같다.

    실제 `<h2>` 가 아니라 **역할만** 붙인다. Streamlit 제목은 `padding: 7.5px 0 15px` 와
    감싸개 `margin-bottom: -15px` 짝을 함께 끌고 와(`app.py` 의 제목 CSS) 이미 맞춰 둔 제목
    줄 높이가 다시 어긋난다. 레벨이 2 인 것은 페이지 제목이 h1 이고 상세 B/N 구획 안에 h4 가
    이미 있기 때문이다.
    """
    return (
        f'<span role="heading" aria-level="2" '
        f'style="display:inline-flex;align-items:center;'
        f"gap:{SECTION_BAR_GAP_PX}px;"
        f'font-size:{SECTION_TITLE_FONT_PX}px;font-weight:700;line-height:1.2">'
        f'<span aria-hidden="true" style="{section_accent_bar_css()}"></span>'
        f"{text}</span>"
    )


def section_accent_bar_css() -> str:
    """강조 막대의 모양 선언. `st.markdown` 과 CSS 가상요소가 같은 값을 읽는다."""
    return (
        f"display:inline-block;flex:none;"
        f"width:{SECTION_BAR_WIDTH_PX}px;height:{SECTION_BAR_HEIGHT_PX}px;"
        f"border-radius:{SECTION_BAR_RADIUS_PX}px;background:{tokens.ACCENT}"
    )


def status_legend_markup(
    *, secure_threshold: float, warning_threshold: float, has_past: bool = False
) -> str:
    """확보·경고·부족 세 색이 무슨 뜻인지 한 줄로 적는다.

    이 앱은 확보율을 세 색으로 판정해 놓고 **그 색이 무슨 뜻인지 화면 어디에도 적지
    않았다.** 처음 보는 사람은 회색 막대가 좋은 것인지 나쁜 것인지 알 길이 없다.
    색만으로 뜻을 나르지 않으려면 이름과 경계 숫자가 같이 있어야 한다.

    `has_past` 는 과거 구간 열이 실제로 그려졌을 때만 켠다. 그 열도 뜻을 면색 하나로만
    나르는데, 판정 세 색과 달리 이름이 어디에도 없었다. 과거 열이 없는 실행에서까지 칩을
    달면 화면에 없는 것을 설명하게 된다.
    """
    chips: tuple[tuple[str, str], ...] = (
        (tokens.STATUS_SECURE, f"확보 {secure_threshold:.0%} 초과"),
        (tokens.STATUS_WARNING, f"경고 {warning_threshold:.0%}~{secure_threshold:.0%}"),
        (tokens.STATUS_SHORTAGE, f"부족 {warning_threshold:.0%} 미만"),
    )
    if has_past:
        chips += ((tokens.SURFACE_PAST, "과거 구간"),)
    swatches = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:14px">'
        # 테두리가 `BORDER` 가 아니라 `LINE` 인 것은 과거 구간 칩(`SURFACE_PAST`) 때문이다.
        # 그 면색은 페이지 바탕과 1.16:1 이라 칩이 사라지는데, `BORDER` 는 바탕과 1.25:1 이라
        # 구해 주지 못한다. `LINE` 은 9.83:1 이고, 확보 막대가 트랙 위에서 같은 이유로 이미
        # 쓰는 선이다(`tokens.BAR_OUTLINE_WIDTH_PX` 주석).
        f'<span style="width:11px;height:11px;border-radius:3px;background:{color};'
        f'border:1px solid {tokens.LINE};display:inline-block"></span>'
        f'<span style="font-size:12px;color:{tokens.TEXT_MUTED}">{label}</span>'
        f"</span>"
        for color, label in chips
    )
    # 높이를 **여기서 정하지 않는다.** 칩은 11px 사각형이고 토글은 위젯이라 줄상자 높이가
    # 서로 다른데, 이 div 가 자기 높이를 가지면 Streamlit 이 잡은 칸 위쪽에 붙어 토글보다
    # 아래로 처진다. 칸 높이를 그대로 물려받아 그 안에서 가운데로 모으는 일은
    # `home_rendering.dashboard_title_row_style()` 의 CSS 가 한다.
    return f'<div class="{STATUS_LEGEND_CLASS}">{swatches}</div>'


def render_home_view_card(*, comparison_ready: bool) -> None:
    """사이드바 조건 카드 `LOB 표시 조건`. Main 탭이 열렸을 때만 선다(2026-09-29 사용자 결정).

    토글은 값을 바꾸기만 하고 아무것도 계산하지 않는다. 다음 실행에서 `home.py` 가 이 키를
    읽어 계산에 반영한다. 안 그려진 회차(다른 탭)에도 값은 `persist_state` 가 지킨다.

    비교 시나리오를 고르지 않았으면 「GAP」 을 누를 수 없다. 켤 수는 있는데 아무것도 바뀌지
    않으면 고장으로 읽힌다 — 그래서 막힌 까닭만은 툴팁으로 남긴다. 각 토글의 뜻은 Guide 다.
    """
    with condition_card("LOB 표시 조건", name="home"):
        st.toggle(
            "선행 전망",
            value=HOME_TOGGLE_DEFAULTS[ADVANCE_TOGGLE_KEY],
            key=ADVANCE_TOGGLE_KEY,
            persist_state="session",
        )
        st.toggle(
            "실행 Loss",
            value=HOME_TOGGLE_DEFAULTS[EXECUTION_TOGGLE_KEY],
            key=EXECUTION_TOGGLE_KEY,
            persist_state="session",
        )
        st.toggle(
            "GAP",
            value=HOME_TOGGLE_DEFAULTS[COMPARISON_TOGGLE_KEY],
            key=COMPARISON_TOGGLE_KEY,
            persist_state="session",
            disabled=not comparison_ready,
            help=None if comparison_ready else "Preference 탭에서 비교 시나리오를 먼저 고르세요.",
        )
        st.toggle(
            "상세 계획",
            value=HOME_TOGGLE_DEFAULTS[PLAN_DETAIL_CUSTOMER_KEY],
            key=PLAN_DETAIL_CUSTOMER_KEY,
            persist_state="session",
        )
        # 기본은 **끔**이다. LOB 로 읽는 수치는 EDP 를 뺀 값이 기준이다.
        st.toggle(
            "EDP 포함",
            value=HOME_TOGGLE_DEFAULTS[EDP_TOGGLE_KEY],
            key=EDP_TOGGLE_KEY,
            persist_state="session",
        )
        # 기본은 **켬**이다. 과거 이력까지 이어 보는 것이 이 화면의 기본 쓰임이다.
        st.toggle(
            "Past Data 포함",
            value=HOME_TOGGLE_DEFAULTS[PAST_DATA_TOGGLE_KEY],
            key=PAST_DATA_TOGGLE_KEY,
            persist_state="session",
        )


def render_lob_title_row(
    *,
    unapplied_months: Sequence[int],
    secure_threshold: float,
    warning_threshold: float,
    has_past: bool,
) -> None:
    """`Capa LOB 현황` 제목과 오른쪽 끝의 판정 색 범례.

    `has_past` 를 받는 것은 과거 구간 칩을 그 열이 실제로 있을 때만 달기 위해서다.

    **범례가 이 줄 안에 있는 이유.** 제목 줄과 Figure 사이 간격은 스크롤바 높이를 뺀
    나머지(`DASHBOARD_PANEL_TITLE_GAP_PX`)뿐이라 거의 0 이다. 범례를 두 줄 사이에 독립
    블록으로 끼우면 바로 아래 월 영역 위에 얹힌 가로 스크롤바와 겹친다. 제목 줄은 이미
    높이가 못박힌 가로 컨테이너라 여기에 넣으면 세로 자리를 새로 먹지 않는다.
    """
    with st.container(
        key="lob_title_row",
        horizontal=True,
        vertical_alignment="center",
        gap="medium",
    ):
        st.markdown(section_title_markup("Capa LOB 현황"), unsafe_allow_html=True)
        # 판정 색의 뜻과 경계 숫자. Top5 막대에 그은 기준선과 같은 값을 읽는다.
        # 아래 CSS 의 `margin-left:auto` 가 이 칸만 오른쪽 끝으로 민다.
        with st.container(key=STATUS_LEGEND_ROW_KEY):
            st.markdown(
                status_legend_markup(
                    secure_threshold=secure_threshold,
                    warning_threshold=warning_threshold,
                    has_past=has_past,
                ),
                unsafe_allow_html=True,
            )
    if unapplied_months:
        labels = _month_labels(unapplied_months)
        st.warning(
            f"선행 반영 계획이 0 이하가 되어 적용하지 못한 달이 있습니다: {labels}. "
            "해당 달은 기존 계획 그대로 그립니다.",
            icon=":material/report:",
        )


def render_home_preference(
    *,
    months: Sequence[int],
    month_labels: Sequence[str],
    advance_profile: GlobalAdvanceLoad,
    execution_profile: GlobalExecutionCapacity,
    top5_band_profile: GlobalTop5Band,
    key_process_profile: GlobalKeyProcess,
    summary_profile: GlobalSummaryNote,
    process_options: Sequence[str],
    process_labels: ProcessLabels,
    unmatched_execution: pd.DataFrame,
    clamped_execution: pd.DataFrame,
    database_path: str,
    active_scenario_id: str | None,
) -> None:
    """비교 시나리오 선택과 Summary 공지·선행 물량·Top5 대역·주요공정·실행 Capa 입력 시트.

    보는 조건(EDP·Past Data 포함 등)은 사이드바 `LOB 표시 조건` 카드다(`render_home_view_card`).
    """
    _render_comparison_picker(database_path, active_scenario_id)
    _render_advance_editor(
        months=months,
        month_labels=month_labels,
        advance_profile=advance_profile,
        database_path=database_path,
    )
    _render_summary_note_editor(
        summary_profile=summary_profile,
        database_path=database_path,
    )
    _render_top5_band_editor(
        top5_band_profile=top5_band_profile,
        database_path=database_path,
    )
    _render_key_process_editor(
        key_process_profile=key_process_profile,
        process_options=process_options,
        process_labels=process_labels,
        database_path=database_path,
    )
    _render_execution_editor(
        months=months,
        execution_profile=execution_profile,
        process_options=process_options,
        process_labels=process_labels,
        unmatched=unmatched_execution,
        clamped=clamped_execution,
        database_path=database_path,
    )


def seed_comparison_selection(database_path: str) -> None:
    """비교 대상 공용 프로필을 세션에 심는다. 이미 세션 값이 있으면 덮지 않는다.

    **`Preference` 탭이 그려질 때가 아니라 HOME 진입 첫 줄에서 불러야 한다.** 이 함수가
    피커 안에만 있으면, 프로필에 비교 대상이 저장돼 있어도 첫 화면에서는 세션이 비어
    있어 「GAP」 토글이 꺼진 채로 뜬다. 탭을 한 번 다녀와야 켜지는데 그 왕복이 사용자에게는
    고장으로 읽힌다.

    세션 값이 있으면 그쪽이 최신이므로 덮지 않는다 — 이번 실행에서 사용자가 고른 값이다.
    """
    if COMPARISON_SCENARIO_KEY in st.session_state:
        return
    try:
        profile = load_global_comparison_scenario(database_path)
    except BOOTSTRAP_ERRORS:
        # 심기에 실패해도 화면은 떠야 한다. 피커가 열릴 때 같은 오류를 사용자에게 알린다.
        return
    if profile.scenario_id is None:
        return
    st.session_state[COMPARISON_SCENARIO_KEY] = profile.scenario_id
    if profile.revision_id is not None:
        st.session_state[COMPARISON_REVISION_KEY] = profile.revision_id


def _render_comparison_picker(database_path: str, active_scenario_id: str | None) -> None:
    """GAP 의 비교 대상. 시나리오와 리비전까지 골라 그 리비전의 계획을 쓴다.

    **지금 활성인 시나리오도 고를 수 있다.** 리비전이 달라지며 계획이 얼마나 바뀌었는지가
    비교의 중요한 쓰임이고, 시나리오가 하나뿐이면 그것을 빼는 순간 고를 것이 없어진다.
    지금 활성인 리비전을 그대로 고르면 자기와 견주는 셈이라 증감이 전부 0 이므로, 그
    자리에는 표시를 붙여 알린다.
    """
    with st.container(border=True):
        st.markdown("#### :material/compare_arrows: 비교 시나리오")
        repository = get_scenario_repository(database_path)
        seed_comparison_selection(database_path)
        try:
            scenarios = repository.list_scenarios()
        except BOOTSTRAP_ERRORS as exc:
            st.error(bootstrap_error_message(exc))
            return
        if not scenarios:
            st.info("저장된 시나리오가 없습니다.")
            st.session_state.pop(COMPARISON_SCENARIO_KEY, None)
            st.session_state.pop(COMPARISON_REVISION_KEY, None)
            return
        scenario_by_id = {scenario.scenario_id: scenario for scenario in scenarios}
        # 지운 시나리오가 세션에 남아 있으면 위젯이 옵션에 없는 값을 만나 죽는다.
        if st.session_state.get(COMPARISON_SCENARIO_KEY) not in scenario_by_id:
            st.session_state.pop(COMPARISON_SCENARIO_KEY, None)
            st.session_state.pop(COMPARISON_REVISION_KEY, None)
        scenario_id = st.selectbox(
            "비교 시나리오",
            options=[None, *scenario_by_id],
            format_func=lambda value: _comparison_label(scenario_by_id, value, active_scenario_id),
            key=COMPARISON_SCENARIO_KEY,
            persist_state="session",
            on_change=_save_comparison_choice,
            args=(database_path,),
        )
        if scenario_id is None:
            st.session_state.pop(COMPARISON_REVISION_KEY, None)
            return
        try:
            revisions = repository.list_revisions(str(scenario_id))
        except BOOTSTRAP_ERRORS as exc:
            st.error(bootstrap_error_message(exc))
            return
        revision_by_id = {revision.revision_id: revision for revision in revisions}
        # 시나리오를 바꾸면 앞서 고른 리비전은 남의 것이 된다. 위젯을 만들기 전에 버린다.
        if st.session_state.get(COMPARISON_REVISION_KEY) not in revision_by_id:
            st.session_state.pop(COMPARISON_REVISION_KEY, None)
        if not revision_by_id:
            st.info("선택한 시나리오에 저장된 리비전이 없습니다.")
            return
        active_revision_id = active_persisted_revision_id()
        st.selectbox(
            "비교 리비전",
            options=list(revision_by_id),
            format_func=lambda value: _revision_label(
                revision_by_id[value], value == active_revision_id
            ),
            key=COMPARISON_REVISION_KEY,
            persist_state="session",
            on_change=_save_comparison_choice,
            args=(database_path,),
        )
        # **위젯 기본값은 `on_change` 를 부르지 않는다.** 시나리오만 고르면 그 시점의
        # 콜백은 리비전 위젯이 생기기 전이라 `revision_id=None` 으로 저장하고, 뒤이어
        # 잡히는 리비전 기본값은 세션에만 들어간다. 그러면 다음 세션에서 짝이 맞지 않아
        # 「GAP」 토글이 꺼진 채로 뜨고, Preference 를 한 번 다녀와야 켜진다.
        _persist_comparison_choice(database_path, revision_by_id.keys())
        if st.session_state.get(COMPARISON_REVISION_KEY) == active_revision_id:
            st.caption(
                "지금 화면이 쓰고 있는 리비전입니다. 자기와 견주는 셈이라 증감이 모두 "
                "0 으로 나옵니다."
            )


def _persist_comparison_choice(database_path: str, revision_ids: Collection[str]) -> None:
    """프로필의 리비전 칸이 **그 시나리오의 것이 아닐 때만** 뒤늦게 메운다.

    선택 위젯의 기본값은 콜백을 부르지 않는다. 시나리오만 고른 순간의 콜백은 리비전
    위젯이 생기기 전이라 `revision_id=None` 으로 저장하고, 뒤이어 잡히는 리비전 기본값은
    세션에만 들어간다. 그 한 칸을 여기서 채운다 — 위젯이 다 그려진 뒤라 기본값이 보인다.

    비어 있는 것만 메우면 부족하다. 두 선택 상자가 콜백 하나를 공유해 **어느 쪽이 눌렸는지
    모르므로**, 시나리오만 S1→S2 로 바꾸면 세션에 남아 있던 S1 의 리비전과 함께
    `(S2, S1의 리비전)` 이 그대로 저장된다. 다음 rerun 에서 화면은 남의 리비전을 버리고
    S2 의 기본값을 잡지만, 프로필의 칸은 비어 있지 않으므로 어긋난 짝이 DB 에 그대로 남는다.

    그래서 「비었는가」가 아니라 **「그 시나리오의 리비전 집합 안에 있는가」**로 판정한다.
    집합은 피커가 이미 읽어 둔 것을 받으므로 DB 를 더 읽지 않는다.

    **그 밖의 불일치는 쓰지 않는다.** 프로필은 시나리오에 딸리지 않은 공용 값이라 다른
    사용자도 같은 행을 쓴다. 「세션과 다르다」를 「세션이 최신이다」로 읽으면, 남이 방금
    고른 값을 이쪽 세션의 옛 값으로 되쓰게 된다. HOME 은 `st.tabs` 라 숨은 Preference
    탭도 매 rerun 실행되므로, 두 사람이 서로의 선택을 계속 뒤집는 핑퐁이 된다. 아무도
    아무것도 고르지 않아도 쓰기가 일어나 `version` 이 오르고 DB 가 dirty 로 표시된다.

    사용자가 실제로 고른 값은 `_save_comparison_choice` 가 맡는다. 여기는 메우는 일만 한다.

    **저장에 실패해도 화면을 멈추지 않는다.** 이번 화면은 세션 값으로 이미 동작하고,
    남기지 못한 것은 다음 세션에서 기본값이 안 뜨는 정도의 일이다.
    """
    scenario_id = st.session_state.get(COMPARISON_SCENARIO_KEY)
    revision_id = st.session_state.get(COMPARISON_REVISION_KEY)
    if scenario_id is None or revision_id is None:
        return
    current = (str(scenario_id), str(revision_id))
    try:
        profile = load_global_comparison_scenario(database_path)
        if profile.scenario_id != current[0] or profile.revision_id in revision_ids:
            return
        get_scenario_repository(database_path).replace_global_comparison_scenario(
            current[0],
            current[1],
            source="HOME 비교 대상 선택",
        )
    except (*BOOTSTRAP_ERRORS, ValueError):
        return
    clear_global_comparison_scenario_cache()


def _save_comparison_choice(database_path: str) -> None:
    """고른 비교 대상을 공용 프로필에 남긴다.

    선택 위젯이라 저장 버튼을 따로 두지 않는다 — 고르는 것이 곧 결정이고, 버튼을 한 번 더
    누르게 하면 눌렀는지 아닌지가 화면에 남지 않는다.

    **저장에 실패해도 화면을 멈추지 않는다.** 비교 대상은 이번 화면에서 이미 세션 값으로
    동작하고, 남기지 못한 것은 다음 세션에서 기본값이 안 뜨는 정도의 일이다. 그것 때문에
    대시보드가 서면 손해가 더 크다.
    """
    scenario_id = st.session_state.get(COMPARISON_SCENARIO_KEY)
    revision_id = st.session_state.get(COMPARISON_REVISION_KEY)
    if scenario_id is None:
        # 시나리오를 비우면 리비전은 남의 것이 된다. 짝을 맞춰 함께 비운다.
        revision_id = None
        st.session_state.pop(COMPARISON_REVISION_KEY, None)
    try:
        get_scenario_repository(database_path).replace_global_comparison_scenario(
            None if scenario_id is None else str(scenario_id),
            None if revision_id is None else str(revision_id),
            source="HOME 비교 대상 선택",
        )
    except (*BOOTSTRAP_ERRORS, ValueError):
        return
    clear_global_comparison_scenario_cache()


def _comparison_label(
    scenarios: dict[str, ScenarioSummary],
    value: str | None,
    active_scenario_id: str | None,
) -> str:
    if value is None:
        return "선택 안 함"
    name = scenarios[value].scenario_name
    return f"{name} · 현재 시나리오" if value == active_scenario_id else name


def _revision_label(revision: RevisionSummary, is_active: bool) -> str:
    label = f"r{revision.revision_no} · {revision.revision_name}"
    return f"{label} · 현재 활성" if is_active else label


def _render_advance_editor(
    *,
    months: Sequence[int],
    month_labels: Sequence[str],
    advance_profile: GlobalAdvanceLoad,
    database_path: str,
) -> None:
    with st.container(border=True):
        st.markdown("#### :material/fast_forward: 선행 투입 물량")
        st.caption(profile_version_caption(advance_profile, empty="아직 넣은 선행 물량이 없습니다"))
        if not months:
            st.info("조회기간에 계획이 있는 달이 없어 입력할 칸이 없습니다.")
            return
        stored = _stored_by_month(advance_profile)
        table = pd.DataFrame(
            [[ADVANCE_LOAD_ROW_LABEL, *[stored.get(month, 0.0) for month in months]]],
            columns=[DIMENSION_COLUMN, *month_labels],
        )
        with st.form("home_advance_load_form"):
            # 작업 줄(저장·메모)은 표 **위**다 — 표를 고친 뒤 버튼을 찾지 않게 한다. 버튼이
            # 왼쪽이다 — 오른쪽 끝에 두면 표 위에 떠오르는 도구 막대(보기·내려받기·검색)에 가린다.
            with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
                submitted = st.form_submit_button(
                    "선행 물량 저장",
                    icon=":material/save:",
                    type="primary",
                )
                note = st.text_input(
                    "변경 메모",
                    placeholder="예: 26.07 선행 투입분 반영",
                    key=ADVANCE_NOTE_KEY,
                )
            # 저장 결과(성공·오류)는 누른 버튼 바로 아래 한 자리다.
            notice = st.container()
            with notice:
                render_flash("home_advance_flash")
            edited = st.data_editor(
                table,
                key=ADVANCE_EDITOR_KEY,
                hide_index=True,
                num_rows="fixed",
                width="stretch",
                disabled=[DIMENSION_COLUMN],
                column_config={
                    DIMENSION_COLUMN: st.column_config.TextColumn(DIMENSION_COLUMN, width="small"),
                    **{
                        label: st.column_config.NumberColumn(label, step=0.01, format="%.2f")
                        for label in month_labels
                    },
                },
            )
        if not submitted:
            _render_out_of_range_notice(months, advance_profile)
            return
        try:
            _save_advance_load(
                database_path,
                months=months,
                month_labels=month_labels,
                edited=edited,
                advance_profile=advance_profile,
                source=note.strip() or "웹 직접 편집",
            )
        except BOOTSTRAP_ERRORS as exc:
            notice.error(bootstrap_error_message(exc))
        else:
            queue_flash("home_advance_flash", "선행 투입 물량을 공용 설정으로 저장했습니다.")
            st.rerun()


def _render_out_of_range_notice(
    months: Sequence[int],
    advance_profile: GlobalAdvanceLoad,
) -> None:
    """조회기간 밖에 남아 있는 입력분. 보이지 않는 값이 계산에 남는 것을 알린다."""
    outside = sorted(set(_stored_by_month(advance_profile)) - set(months))
    if not outside:
        return
    labels = _month_labels(outside)
    st.caption(
        f"조회기간 밖에 저장된 달이 {len(outside):,}개 있습니다({labels}). 표에는 보이지 "
        "않지만 그대로 보존되며, 저장해도 지워지지 않습니다."
    )


def _save_advance_load(
    database_path: str,
    *,
    months: Sequence[int],
    month_labels: Sequence[str],
    edited: pd.DataFrame,
    advance_profile: GlobalAdvanceLoad,
    source: str,
) -> None:
    """표에 보이는 달만 갈아 끼우고 조회기간 밖 입력분은 그대로 둔다.

    보이지 않는 달까지 함께 지우면 조회기간을 좁힌 채 저장한 사람이 다른 달의 입력을
    모르는 새 날린다.
    """
    row = edited.iloc[0]
    frame = merge_advance_load_edits(
        advance_profile.rows,
        list(months),
        [row[label] for label in month_labels],
    )
    get_scenario_repository(database_path).replace_global_advance_load(frame, source=source)
    clear_global_advance_load_cache()


def _month_labels(months: Sequence[int]) -> str:
    """차트 월 칸과 같은 `YY.MM` 표기. 안내 문구가 표와 같은 낱말을 써야 찾을 수 있다."""
    return ", ".join(month_label(month) for month in months)


def _stored_by_month(advance_profile: GlobalAdvanceLoad) -> dict[int, float]:
    rows = advance_profile.rows
    if rows.empty:
        return {}
    return {
        int(month): float(value)
        for month, value in zip(rows["생산계획년월"], rows["선행 물량"], strict=True)
    }


def _render_summary_note_editor(
    *,
    summary_profile: GlobalSummaryNote,
    database_path: str,
) -> None:
    """HOME 맨 위에 띄우는 공지 문구.

    계산에 들어가지 않는 **화면 문구**다. 그래서 공용 프로필 중 유일하게 캐시를 비운 뒤
    `st.rerun` 을 부르지 않아도 되지만, 부르지 않으면 저장한 사람만 옛 문구를 본다.

    **빈 문구도 저장한다.** 공지를 내리는 것도 결정이고, 지우고 저장하면 화면에서
    사라지는 것이 지우기의 뜻이다.
    """
    with st.container(border=True):
        st.markdown("#### :material/campaign: Summary 공지")
        st.caption(
            profile_version_caption(
                summary_profile,
                empty="아직 공지를 올린 적이 없습니다",
                suffix="공지 중" if summary_profile.is_visible else "내림",
            )
        )
        with st.form("home_summary_note_form"):
            submitted = st.form_submit_button(
                "Summary 저장",
                icon=":material/save:",
                type="primary",
            )
            # 저장 결과(성공·오류)는 누른 버튼 바로 아래 한 자리다.
            notice = st.container()
            with notice:
                render_flash("home_summary_note_flash")
            # **`key` 를 두지 않는다.** 키가 붙은 위젯은 한 번 그려진 뒤 `value` 를 무시하고
            # 세션 값을 쓴다. Preference 는 숨은 탭에서도 위젯을 그리므로 HOME 첫 진입의
            # 공지(대개 빈 문구)가 세션에 박히고, 그 뒤 다른 사람이 올린 공지를 이 화면은
            # 영영 못 본 채 저장 버튼 한 번으로 덮어쓴다. 값은 폼 반환값으로 받으면 된다.
            note = st.text_area(
                "Summary",
                value=summary_profile.note,
                height=180,
                placeholder="예: 9월 물량 확정 전 잠정 계획입니다. B/N 은 SAM 기준.",
            )
        if not submitted:
            return
        try:
            get_scenario_repository(database_path).replace_global_summary_note(
                str(note),
                source="웹 직접 편집",
            )
        except BOOTSTRAP_ERRORS as exc:
            notice.error(bootstrap_error_message(exc))
            return
        except ValueError as exc:
            notice.error(str(exc))
            return
        clear_global_summary_note_cache()
        queue_flash(
            "home_summary_note_flash",
            "Summary 공지를 저장했습니다." if str(note).strip() else "Summary 공지를 내렸습니다.",
        )
        st.rerun(scope="app")


def _render_top5_band_editor(
    *,
    top5_band_profile: GlobalTop5Band,
    database_path: str,
) -> None:
    """B/N Top5 막대가 표현하는 확보율 구간."""
    with st.container(border=True):
        st.markdown("#### :material/straighten: B/N Top5 확보율 구간")
        st.caption(
            profile_version_caption(
                top5_band_profile,
                empty=(
                    f"기본값 {top5_band_profile.min_rate:.0%}~"
                    f"{top5_band_profile.max_rate:.0%} 을 씁니다"
                ),
            )
        )
        with st.form("home_top5_band_form"):
            submitted = st.form_submit_button(
                "확보율 구간 저장",
                icon=":material/save:",
                type="primary",
            )
            # 저장 결과(성공·오류)는 누른 버튼 바로 아래 한 자리다.
            notice = st.container()
            with notice:
                render_flash("home_top5_band_flash")
            # **`key` 를 두지 않는다.** 바로 위 Summary 공지와 같은 이유다 — 키가 붙은 위젯은
            # 한 번 그려진 뒤 `value` 를 무시하고 세션 값을 쓴다. Preference 는 숨은 탭에서도
            # 그려지므로 HOME 첫 진입의 구간이 세션에 박히고, 그 뒤 다른 사람이 바꾼 구간을
            # 이 화면은 못 본 채 저장 한 번으로 되돌린다. 위의 `공용 버전 v…` 캡션만 새 번호로
            # 바뀌어 화면이 스스로 모순이 된다. 값은 폼 반환값으로 받으면 된다.
            min_column, max_column = st.columns(2)
            with min_column:
                minimum = st.number_input(
                    "하한(%)",
                    value=top5_band_profile.min_rate * 100,
                    step=10.0,
                    format="%.0f",
                )
            with max_column:
                maximum = st.number_input(
                    "상한(%)",
                    value=top5_band_profile.max_rate * 100,
                    step=10.0,
                    format="%.0f",
                )
        if not submitted:
            return
        try:
            get_scenario_repository(database_path).replace_global_top5_band(
                float(minimum) / 100,
                float(maximum) / 100,
                source="웹 직접 편집",
            )
        except BOOTSTRAP_ERRORS as exc:
            notice.error(bootstrap_error_message(exc))
            return
        except ValueError as exc:
            notice.error(str(exc))
            return
        clear_global_top5_band_cache()
        queue_flash("home_top5_band_flash", "B/N Top5 확보율 구간을 저장했습니다.")
        st.rerun(scope="app")


def _render_key_process_editor(
    *,
    key_process_profile: GlobalKeyProcess,
    process_options: Sequence[str],
    process_labels: ProcessLabels,
    database_path: str,
) -> None:
    """HOME `주요공정 확보율` 격자에 그릴 공정을 고르는 시트.

    **위젯에 `key` 를 두지 않는다.** `Preference` 탭은 숨어 있어도 본문이 그려지므로,
    `key` 를 두면 첫 진입의 값(대개 빈 목록)이 세션에 박히고 그 뒤 다른 사람이 저장한
    목록을 이 화면은 영영 못 본 채 저장 한 번으로 덮어쓴다. 값은 폼 반환값으로 받는다.
    """
    with st.container(border=True):
        st.markdown("#### :material/grid_view: 주요공정 히트맵")
        st.caption(
            profile_version_caption(
                key_process_profile,
                empty="아직 고른 주요공정이 없습니다",
                detail=f"{len(key_process_profile.processes)}개 공정",
            )
        )
        known_options = set(process_options)
        with st.form("home_key_process_form"):
            submitted = st.form_submit_button(
                "주요공정 저장",
                icon=":material/save:",
                type="primary",
            )
            # 저장 결과(성공·오류)는 누른 버튼 바로 아래 한 자리다.
            notice = st.container()
            with notice:
                render_flash("home_key_process_flash")
            selected = st.multiselect(
                "주요 공정",
                options=list(process_options),
                default=[
                    process for process in key_process_profile.processes if process in known_options
                ],
                format_func=process_labels.format_func(),
                max_selections=KEY_PROCESS_LIMIT,
                # 몇 개까지 되는지는 고르기 전에 알아야 해 자리 글자에 둔다.
                placeholder=f"공정을 고르세요 (최대 {KEY_PROCESS_LIMIT}개)",
            )
        if not submitted:
            _render_key_process_notice(key_process_profile, known_options, process_labels)
            return
        try:
            get_scenario_repository(database_path).replace_global_key_process(
                selected,
                source="웹 직접 편집",
            )
        except BOOTSTRAP_ERRORS as exc:
            notice.error(bootstrap_error_message(exc))
            return
        except ValueError as exc:
            notice.error(str(exc))
            return
        clear_global_key_process_cache()
        queue_flash("home_key_process_flash", "주요공정 목록을 저장했습니다.")
        st.rerun(scope="app")


def _render_key_process_notice(
    profile: GlobalKeyProcess,
    known_options: set[str],
    process_labels: ProcessLabels,
) -> None:
    """저장돼 있으나 이번 화면에서는 그릴 수 없는 공정을 알린다.

    **프로필에서 지우지 않는다.** 공용 설정이라 다른 시나리오·조회기간에는 그 공정이
    있고, 여기서 조용히 걷어내면 그 화면의 히트맵이 함께 비어 버린다.
    """
    missing = [process for process in profile.processes if process not in known_options]
    if not missing:
        return
    names = ", ".join(process_labels.label(process) for process in missing)
    st.caption(
        f":material/info: 이번 시나리오·조회기간에 없어 그리지 않은 공정: {names}. "
        "공용 설정이라 저장은 그대로 남고, 해당 공정이 있는 화면에서는 그려집니다."
    )


def _render_execution_editor(
    *,
    months: Sequence[int],
    execution_profile: GlobalExecutionCapacity,
    process_options: Sequence[str],
    process_labels: ProcessLabels,
    unmatched: pd.DataFrame,
    clamped: pd.DataFrame,
    database_path: str,
) -> None:
    """기준정보 밖에서 생긴 변수를 확보율에 퍼센트포인트로 얹는 입력 표."""
    with st.container(border=True):
        st.markdown("#### :material/bolt: 실행 Capa 반영")
        st.caption(
            profile_version_caption(execution_profile, empty="아직 넣은 실행 Capa 반영이 없습니다")
        )
        if not months or not process_options:
            st.info("조회기간에 계산된 공정이 없어 입력할 칸이 없습니다.")
            return
        table = _execution_editor_frame(execution_profile)
        with st.form("home_execution_capacity_form"):
            # 작업 줄(저장·메모)은 표 **위**, 버튼이 왼쪽이다(오른쪽 끝은 표 도구 막대에 가린다).
            with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
                submitted = st.form_submit_button(
                    "실행 Capa 저장",
                    icon=":material/save:",
                    type="primary",
                )
                note = st.text_input(
                    "변경 메모",
                    placeholder="예: 26.07 Wafer Mount 비가동 3대",
                    key=EXECUTION_NOTE_KEY,
                )
            # 저장 결과(성공·오류)는 누른 버튼 바로 아래 한 자리다.
            notice = st.container()
            with notice:
                render_flash("home_execution_flash")
            edited = st.data_editor(
                table,
                key=EXECUTION_EDITOR_KEY,
                hide_index=True,
                num_rows="dynamic",
                width="stretch",
                column_config={
                    "생산계획년월": st.column_config.SelectboxColumn(
                        "년월",
                        options=list(months),
                        # 저장은 YYYYMM 정수다. 표시만 `26.07` 로 바꾼다.
                        format_func=_month_option_label,
                        required=True,
                    ),
                    "공정": st.column_config.SelectboxColumn(
                        "공정",
                        options=list(process_options),
                        # **값은 원본 공정명이고 보이는 글자만 표시명이다.** 표시명으로
                        # 저장하면 Proc Rename 을 바꾸는 순간 매칭이 끊긴다.
                        format_func=process_labels.label,  # 값은 원본, 글자만 표시명
                        required=True,
                    ),
                    "증감 확보율": st.column_config.NumberColumn(
                        "증감 확보율(%p)",
                        step=0.1,
                        format="%.1f",
                        required=True,
                    ),
                    "비고": st.column_config.TextColumn("비고", width="medium"),
                },
            )
        if not submitted:
            _render_execution_notices(unmatched, clamped, process_labels)
            return
        try:
            _save_execution_capacity(
                database_path,
                edited=edited,
                source=note.strip() or "웹 직접 편집",
            )
        except BOOTSTRAP_ERRORS as exc:
            notice.error(bootstrap_error_message(exc))
            return
        except ValueError as exc:
            notice.error(str(exc))
            return
        queue_flash("home_execution_flash", "실행 Capa 반영을 저장했습니다.")
        st.rerun(scope="app")


def _month_option_label(value: str | int | float | bool) -> str:
    """`SelectboxColumn` 은 스칼라 합집합을 넘긴다. 저장값은 YYYYMM 정수다."""
    return month_label(int(value))


def _execution_editor_frame(execution_profile: GlobalExecutionCapacity) -> pd.DataFrame:
    """저장분을 그대로 보여준다. 한 행도 없으면 빈 표로 시작한다."""
    rows = execution_profile.rows
    if rows.empty:
        return empty_execution_capacity()
    return rows.loc[:, list(EXECUTION_CAPACITY_COLUMNS)].copy()


def _save_execution_capacity(
    database_path: str,
    *,
    edited: pd.DataFrame,
    source: str,
) -> None:
    frame = edited.loc[:, list(EXECUTION_CAPACITY_COLUMNS)].copy()
    get_scenario_repository(database_path).replace_global_execution_capacity(
        prepare_execution_capacity(frame),
        source=source,
    )
    clear_global_execution_capacity_cache()


def _render_execution_notices(
    unmatched: pd.DataFrame,
    clamped: pd.DataFrame,
    process_labels: ProcessLabels,
) -> None:
    """넣었는데 화면이 그대로인 이유와, 0 에서 잘린 행을 알린다."""
    if not unmatched.empty:
        examples = ", ".join(
            f"{month_label(int(month))}·{process_labels.label(process)}"
            for month, process in zip(
                unmatched["생산계획년월"].head(5),
                unmatched["공정"].head(5),
                strict=True,
            )
        )
        st.warning(
            f"이번 시나리오·조회기간에 짝이 없어 반영되지 않은 행 {len(unmatched)}건: "
            f"{examples}. 공용 설정이라 저장은 남아 있고, 해당 공정이 있는 시나리오에서는 "
            "그대로 적용됩니다.",
            icon=":material/link_off:",
        )
    if not clamped.empty:
        st.warning(
            f"조정 결과가 0% 아래로 내려가 0 에서 자른 행이 {len(clamped)}건 있습니다. "
            "막대 길이와 순위가 의미를 잃지 않도록 자릅니다.",
            icon=":material/vertical_align_bottom:",
        )
