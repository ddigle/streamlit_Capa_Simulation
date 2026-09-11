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
    get_scenario_repository,
)
from capa_simulation.persistence.models import GlobalAdvanceLoad
from capa_simulation.services.advance_load import (
    ADVANCE_LOAD_ROW_LABEL,
    merge_advance_load_edits,
)

EDP_TOGGLE_KEY = "home_preference_include_edp"
ADVANCE_TOGGLE_KEY = "home_show_advance"
ADVANCE_EDITOR_KEY = "home_preference_advance_editor"
ADVANCE_NOTE_KEY = "home_preference_advance_note"
DIMENSION_COLUMN = "구분"


def render_lob_title_row(*, unapplied_months: Sequence[int]) -> None:
    """`Capa LOB 현황` 제목과 그 옆의 「선행」 토글.

    토글은 값을 바꾸기만 하고 아무것도 계산하지 않는다. 다음 실행에서 `home.py` 가 이
    키를 읽어 계산에 반영한다.
    """
    with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
        st.markdown(
            f'<span style="color:{tokens.ACCENT}">▍</span>'
            f'<span style="font-size:20px;font-weight:700">Capa LOB 현황</span>',
            unsafe_allow_html=True,
        )
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
) -> None:
    """EDP 토글과 선행 물량 입력 시트 한 장."""
    with st.container(border=True):
        st.markdown("#### :material/tune: 표시 기준")
        st.toggle(
            "EDP 포함",
            value=True,
            key=EDP_TOGGLE_KEY,
            persist_state="session",
            help=(
                "끄면 Density·Wafer 계획·Wafer Capa 와 계획 세부수량에서 EDP-TSV 제품을 "
                "뺍니다. 설비가 받는 부하는 그대로라 확보율과 B/N 공정 순위는 바뀌지 "
                "않습니다."
            ),
        )
    _render_advance_editor(
        months=months,
        month_labels=month_labels,
        advance_profile=advance_profile,
        database_path=database_path,
    )


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
    return ", ".join(f"{month // 100 % 100:02d}.{month % 100:02d}" for month in months)


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
