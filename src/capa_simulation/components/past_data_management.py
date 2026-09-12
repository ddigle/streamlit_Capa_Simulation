# Purpose: HOME Past Data 탭에서 과거 구간 세 표를 CSV·붙여넣기로 받아 공용 프로필에 저장한다.

"""HOME `Past Data` 탭.

DB 원천은 적재 시점 이후의 달만 담는다. 지난 해를 함께 보려면 그 구간을 손으로 넣어야 하고,
과거는 이미 끝난 값이라 불변이므로 시나리오 리비전이 아니라 공용 프로필에 둔다.

세 표가 **한 버전을 공유한다.** 한 표만 고쳐도 저장할 때 세 표를 함께 쓴다 — 부분 저장을
허용하면 어느 표가 어느 버전인지 알 수 없다. 그래서 화면은 세 표를 모두 세션에 들고 있다가
한 번에 저장한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import (
    clear_global_past_data_cache,
    get_scenario_repository,
    past_table_csv,
)
from capa_simulation.persistence.models import GlobalPastData
from capa_simulation.services.past_data import (
    PAST_DETAIL_COLUMNS,
    PAST_MONTH_COLUMNS,
    PAST_SECUREMENT_COLUMNS,
    past_sample_rows,
    past_table_from_clipboard,
)

PAST_CLIPBOARD_KEY = "home_past_clipboard"
PAST_NOTE_KEY = "home_past_note"
PAST_DRAFT_KEY = "home_past_draft"


@dataclass(frozen=True)
class PastTableSpec:
    """한 표의 화면 이름·컬럼 계약·설명. 세 표가 같은 모양의 칸을 갖게 한다."""

    name: str
    title: str
    icon: str
    columns: tuple[str, ...]
    caption: str


PAST_TABLE_SPECS = (
    PastTableSpec(
        name="월별",
        title="월별 Density · Wafer Total",
        icon=":material/calendar_month:",
        columns=PAST_MONTH_COLUMNS,
        caption=(
            "Density 는 억Gb, Wafer Total 은 매입니다. Wafer Capa 와 B/N Capa 는 확보율을 "
            "곱해 만들므로 따로 넣지 않습니다."
        ),
    ),
    PastTableSpec(
        name="계획",
        title="계획 세부수량",
        icon=":material/table_rows:",
        columns=PAST_DETAIL_COLUMNS,
        caption=(
            "제품·Stack·거래선별 월 수량입니다. 화면에서 `계획 세부수량 상세`를 끄면 "
            "거래선을 합쳐 접어 보여 줍니다."
        ),
    ),
    PastTableSpec(
        name="확보율",
        title="공정별 확보율",
        icon=":material/percent:",
        columns=PAST_SECUREMENT_COLUMNS,
        caption=(
            "공정별 월 확보율입니다(1.05 = 105%). **확보율 오름차순이 곧 B/N 순위**라 "
            "B/N 공정명을 따로 넣지 않습니다. 가용대수·소요대수는 받지 않으므로 상세 "
            "B/N 의 그 두 칸은 과거 구간에서 빕니다."
        ),
    ),
)


def render_past_data_management(database_path: str, profile: GlobalPastData) -> None:
    """세 표의 양식 내려받기·붙여넣기와 한 번의 저장."""
    stored = {
        "월별": profile.monthly,
        "계획": profile.plan_detail,
        "확보율": profile.securement,
    }
    draft = st.session_state.setdefault(PAST_DRAFT_KEY, {})
    with st.container(border=True):
        st.markdown("#### :material/history: 과거 구간")
        st.caption(
            "DB 원천은 적재 시점 이후의 달만 담습니다. 지난 구간은 여기에 넣으면 화면이 "
            "이어 그립니다. **계산 결과가 있는 달은 계산이 이깁니다** — 적재 범위가 뒤로 "
            "넘어가도 입력을 지울 필요가 없습니다."
        )
        st.caption(_version_caption(profile))
    for spec in PAST_TABLE_SPECS:
        _render_table_editor(database_path, profile.version, spec, stored[spec.name], draft)
    _render_save(database_path, stored, draft)


def _render_table_editor(
    database_path: str,
    version: int,
    spec: PastTableSpec,
    stored: pd.DataFrame,
    draft: dict[str, pd.DataFrame],
) -> None:
    pending = draft.get(spec.name)
    current = stored if pending is None else pending
    with st.container(border=True):
        st.markdown(f"#### {spec.icon} {spec.title}")
        st.caption(spec.caption)
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.caption(
                f"저장 {len(stored):,}행"
                + ("" if pending is None else f" · 대기 {len(pending):,}행")
            )
            render_csv_download(
                # 탭이 닫혀 있어도 그리므로 인코딩을 HOME 의 매 실행에 얹지 않는다.
                data=past_table_csv(
                    database_path,
                    version,
                    spec.name,
                    spec.columns,
                    stored if not stored.empty else past_sample_rows(spec.columns),
                ),
                file_name=f"PAST_{spec.name}.csv",
                key=f"home_past_download_{spec.name}",
                label="양식 CSV",
            )
        with st.form(f"home_past_form_{spec.name}", border=False):
            clipboard = st.text_area(
                f"{spec.title} 붙여넣기",
                key=f"{PAST_CLIPBOARD_KEY}_{spec.name}",
                height=150,
                placeholder="Excel에서 헤더를 포함한 전체 셀 범위를 복사한 뒤 Ctrl+V",
            )
            submitted = st.form_submit_button(
                "붙여넣기 읽기",
                icon=":material/content_paste:",
                width="stretch",
            )
        if submitted:
            try:
                draft[spec.name] = past_table_from_clipboard(clipboard, spec.columns)
            except BOOTSTRAP_ERRORS as exc:
                st.error(bootstrap_error_message(exc))
            else:
                st.success(f"{len(draft[spec.name]):,}행을 읽었습니다. 아래에서 저장하세요.")
                st.rerun()
        if not current.empty:
            with st.expander(f"현재 {len(current):,}행 확인", icon=":material/preview:"):
                st.dataframe(current, hide_index=True, width="stretch", height=240)


def _render_save(
    database_path: str,
    stored: dict[str, pd.DataFrame],
    draft: dict[str, pd.DataFrame],
) -> None:
    with st.container(border=True):
        st.markdown("#### :material/save: 과거 구간 저장")
        st.caption(
            "세 표가 한 버전을 공유합니다. 붙여넣지 않은 표는 저장된 값 그대로 다시 "
            "기록되며, 읽어 둔 표만 새 값으로 바뀝니다."
        )
        note = st.text_input(
            "변경 메모",
            placeholder="예: 25년 실적 반영",
            key=PAST_NOTE_KEY,
            # 이 값은 바로 아래 저장 버튼을 누를 때만 읽는다. Enter·포커스 이탈로 HOME 을
            # 통째로 다시 그릴 이유가 없고, 버튼을 누른 실행에 값이 함께 올라온다.
            on_change="ignore",
        )
        pending_names = [name for name in stored if name in draft]
        if st.button(
            "과거 구간 저장",
            icon=":material/save:",
            type="primary",
            width="stretch",
            disabled=not pending_names,
        ):
            merged = {name: draft.get(name, frame) for name, frame in stored.items()}
            try:
                get_scenario_repository(database_path).replace_global_past_data(
                    merged, source=note.strip() or "웹 붙여넣기"
                )
            except BOOTSTRAP_ERRORS as exc:
                st.error(bootstrap_error_message(exc))
            else:
                clear_global_past_data_cache()
                st.session_state.pop(PAST_DRAFT_KEY, None)
                st.success("과거 구간을 공용 설정으로 저장했습니다.")
                st.rerun()
        if not pending_names:
            st.caption("읽어 둔 표가 없습니다. 위에서 붙여넣기를 먼저 읽으세요.")


def _version_caption(profile: GlobalPastData) -> str:
    if profile.version == 0:
        return "공용 버전 없음 · 아직 넣은 과거 구간이 없습니다"
    if profile.updated_at is None:
        return f"공용 버전 v{profile.version} · {profile.source}"
    return f"공용 버전 v{profile.version} · {profile.source} · {profile.updated_at:%Y-%m-%d %H:%M}"
