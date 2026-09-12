# Purpose: HOME 의 차트 표시 설정(EDP 포함 여부·선행 투입 물량)을 입력받아 공용 프로필에 저장한다.

"""HOME `Preference` 탭과 `Capa LOB 현황` 제목 줄.

두 컨트롤의 **값은 계산보다 먼저** 필요하고 **위젯은 계산 뒤에** 그려진다. 그래서
`app_pages/home.py` 는 위젯이 쓰는 세션 키를 직접 읽고, 여기서는 같은 키로 위젯을 만든다.
키 문자열이 두 곳에서 따로 적히면 조용히 끊어지므로 상수로 내보낸다.

제목 `Capa LOB 현황` 은 Plotly 주석이 아니라 여기서 그린다. 주석 안에는 위젯을 놓을 수
없어 「선행」 토글을 제목 옆에 둘 수 없었다.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import streamlit as st

from capa_simulation.design import tokens
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import (
    clear_global_advance_load_cache,
    clear_global_comparison_scenario_cache,
    get_scenario_repository,
    load_global_comparison_scenario,
)
from capa_simulation.persistence.models import (
    GlobalAdvanceLoad,
    RevisionSummary,
    ScenarioSummary,
)
from capa_simulation.scenario_activation import active_persisted_revision_id
from capa_simulation.services.advance_load import (
    ADVANCE_LOAD_ROW_LABEL,
    merge_advance_load_edits,
)
from capa_simulation.services.month_columns import month_label

EDP_TOGGLE_KEY = "home_preference_include_edp"
ADVANCE_TOGGLE_KEY = "home_show_advance"
PLAN_DETAIL_CUSTOMER_KEY = "home_preference_plan_detail_customer"
COMPARISON_TOGGLE_KEY = "home_show_comparison"
COMPARISON_SCENARIO_KEY = "home_preference_comparison_scenario"
COMPARISON_REVISION_KEY = "home_preference_comparison_revision"
ADVANCE_EDITOR_KEY = "home_preference_advance_editor"
ADVANCE_NOTE_KEY = "home_preference_advance_note"
DIMENSION_COLUMN = "구분"


def render_plan_detail_title_row(*, applied_customer: bool) -> None:
    """`계획 세부수량` 제목과 그 옆의 「상세」 토글.

    이 줄은 두 칸이 나란한 캔버스 **안**에서 그려진다. 제목이 Plotly 주석으로 있던 44px 을
    그대로 받아 쓰되 월 칸에도 같은 높이의 빈 줄을 끼워야 행이 맞는다.

    캔버스는 fragment 안이라 여기서 토글을 누르면 fragment 만 다시 돈다. 그러면 Figure 는
    옛것 그대로다. `applied_customer` 는 지금 그림이 만들어질 때 쓴 값이고, 그것과 달라지면
    앱 전체를 다시 돌린다.
    """
    with st.container(
        key="plan_detail_title_row",
        horizontal=True,
        vertical_alignment="center",
        gap="medium",
    ):
        st.markdown(section_title_markup("계획 세부수량"), unsafe_allow_html=True)
        st.toggle(
            "상세",
            value=False,
            key=PLAN_DETAIL_CUSTOMER_KEY,
            persist_state="session",
            help=(
                "제품·Stack 아래에 거래선을 분류로 더합니다. 거래선 수만큼 행이 늘어 표가 "
                "길어집니다. 거래선 정렬은 Admin Area 의 표시순서 관리에서 정합니다."
            ),
        )
    if bool(st.session_state.get(PLAN_DETAIL_CUSTOMER_KEY, False)) != applied_customer:
        st.rerun(scope="app")


def render_section_title_row(text: str, *, key: str) -> None:
    """위젯 없는 구획 제목 줄. 토글이 붙는 줄들과 같은 높이·같은 모양이다.

    세 구획의 제목이 같은 컴포넌트로 그려져야 제목과 표 사이 간격이 하나로 맞는다.
    하나만 Plotly 주석으로 남겨 두면 그 구획만 간격이 다르다.
    """
    with st.container(key=key, horizontal=True, vertical_alignment="center", gap="medium"):
        st.markdown(section_title_markup(text), unsafe_allow_html=True)


def section_title_markup(text: str) -> str:
    """구획 제목 한 줄. Plotly 주석이 그리던 모양을 그대로 옮긴 것이다."""
    return (
        f'<span style="color:{tokens.ACCENT}">▍</span>'
        f'<span style="font-size:20px;font-weight:700">{text}</span>'
    )


def render_lob_title_row(
    *,
    unapplied_months: Sequence[int],
    comparison_ready: bool,
) -> None:
    """`Capa LOB 현황` 제목과 그 옆의 「선행」·「GAP」 토글.

    토글은 값을 바꾸기만 하고 아무것도 계산하지 않는다. 다음 실행에서 `home.py` 가 이
    키를 읽어 계산에 반영한다.

    비교 시나리오를 고르지 않았으면 「GAP」 을 누를 수 없다. 켤 수는 있는데 아무것도
    바뀌지 않으면 고장으로 읽힌다.
    """
    with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
        st.markdown(section_title_markup("Capa LOB 현황"), unsafe_allow_html=True)
        st.toggle(
            "선행",
            value=False,
            key=ADVANCE_TOGGLE_KEY,
            persist_state="session",
            help=(
                "Preference 탭에 넣은 선행 투입 물량을 계획과 확보율에 반영합니다. "
                "설비가 늘어난 것이 아니므로 Capa 는 그대로이고 계획과 확보율만 "
                "반비례로 움직입니다."
            ),
        )
        st.toggle(
            "GAP",
            value=False,
            key=COMPARISON_TOGGLE_KEY,
            persist_state="session",
            disabled=not comparison_ready,
            help=(
                "Preference 탭에서 고른 비교 시나리오 대비 증감을 Density·Wafer 계획·"
                "계획 세부수량 값 **아래**에 적습니다. 선행 증감은 값 위에 적습니다."
                if comparison_ready
                else "Preference 탭에서 비교 시나리오를 먼저 고르세요."
            ),
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
    database_path: str,
    active_scenario_id: str | None,
) -> None:
    """표시 기준 토글과 비교 시나리오 선택, 선행 물량 입력 시트."""
    with st.container(border=True):
        st.markdown("#### :material/tune: 표시 기준")
        # 기본은 **끔**이다. LOB 로 읽는 수치는 EDP 를 뺀 값이 기준이고, 넣은 화면을 보려면
        # 그때 켜면 된다. 기본값을 바꿀 때는 `app_pages/home.py` 의 세션 기본값도 같이 고친다.
        st.toggle(
            "EDP 포함",
            value=False,
            key=EDP_TOGGLE_KEY,
            persist_state="session",
            help=(
                "끄면 Density·Wafer 계획·Wafer Capa 와 계획 세부수량에서 EDP-TSV 제품을 "
                "뺍니다. 설비가 받는 부하는 그대로라 확보율과 B/N 공정 순위는 바뀌지 "
                "않습니다."
            ),
        )
    _render_comparison_picker(database_path, active_scenario_id)
    _render_advance_editor(
        months=months,
        month_labels=month_labels,
        advance_profile=advance_profile,
        database_path=database_path,
    )


def _render_comparison_picker(database_path: str, active_scenario_id: str | None) -> None:
    """GAP 의 비교 대상. 시나리오와 리비전까지 골라 그 리비전의 계획을 쓴다.

    **지금 활성인 시나리오도 고를 수 있다.** 리비전이 달라지며 계획이 얼마나 바뀌었는지가
    비교의 중요한 쓰임이고, 시나리오가 하나뿐이면 그것을 빼는 순간 고를 것이 없어진다.
    지금 활성인 리비전을 그대로 고르면 자기와 견주는 셈이라 증감이 전부 0 이므로, 그
    자리에는 표시를 붙여 알린다.
    """
    with st.container(border=True):
        st.markdown("#### :material/compare_arrows: 비교 시나리오")
        st.caption(
            "고른 리비전에서 **계획만** 가져와 현재 기준정보로 환산해 비교합니다. 수율·Chip "
            "기준정보가 그 사이 바뀌었어도 그것은 계획 변동이 아니므로 환산에 쓰는 표는 "
            "현재 것을 씁니다."
        )
        repository = get_scenario_repository(database_path)
        # 비교 대상은 시나리오와 분리된 공용 프로필이다. 세션에 없으면 프로필에서 심어
        # 새 브라우저 세션에서도 고른 대상이 그대로 살아 있게 한다. 이미 세션 값이 있으면
        # 그쪽이 최신이므로 덮지 않는다.
        profile = load_global_comparison_scenario(database_path)
        if COMPARISON_SCENARIO_KEY not in st.session_state and profile.scenario_id is not None:
            st.session_state[COMPARISON_SCENARIO_KEY] = profile.scenario_id
            if profile.revision_id is not None:
                st.session_state[COMPARISON_REVISION_KEY] = profile.revision_id
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
            st.info("그 시나리오에는 리비전이 없습니다.")
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
        if st.session_state.get(COMPARISON_REVISION_KEY) == active_revision_id:
            st.caption(
                "지금 화면이 쓰고 있는 리비전입니다. 자기와 견주는 셈이라 증감이 모두 "
                "0 으로 나옵니다."
            )


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
        st.caption(
            "Capa 여유만큼 앞당겨 투입한 달에는 **+**, 그만큼 줄어드는 이후 달에는 **−** 를 "
            "억Gb 로 넣습니다. 시나리오와 분리된 공용 설정이라 모든 시나리오에 같이 "
            "적용되며, 「선행」 토글을 켠 화면에만 반영됩니다."
        )
        st.caption(_version_caption(advance_profile))
        if not months:
            st.info("조회기간에 계획이 있는 달이 없어 입력할 칸이 없습니다.")
            return
        stored = _stored_by_month(advance_profile)
        table = pd.DataFrame(
            [[ADVANCE_LOAD_ROW_LABEL, *[stored.get(month, 0.0) for month in months]]],
            columns=[DIMENSION_COLUMN, *month_labels],
        )
        with st.form("home_advance_load_form"):
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
            note = st.text_input(
                "변경 메모",
                placeholder="예: 26.07 선행 투입분 반영",
                key=ADVANCE_NOTE_KEY,
            )
            submitted = st.form_submit_button(
                "선행 물량 저장",
                icon=":material/save:",
                type="primary",
                width="stretch",
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
            st.error(bootstrap_error_message(exc))
        else:
            st.success("선행 투입 물량을 공용 설정으로 저장했습니다.")
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


def _version_caption(advance_profile: GlobalAdvanceLoad) -> str:
    if advance_profile.version == 0:
        return "공용 버전 없음 · 아직 넣은 선행 물량이 없습니다"
    if advance_profile.updated_at is None:
        return f"공용 버전 v{advance_profile.version} · {advance_profile.source}"
    return (
        f"공용 버전 v{advance_profile.version} · {advance_profile.source} · "
        f"{advance_profile.updated_at:%Y-%m-%d %H:%M}"
    )
