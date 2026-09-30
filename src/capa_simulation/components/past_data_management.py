# Purpose: HOME Past Data 탭에서 과거 구간 세 표를 CSV·붙여넣기로 받아 공용 프로필에 저장한다.

"""HOME `Past Data` 탭.

DB 원천은 적재 시점 이후의 달만 담는다. 지난 해를 함께 보려면 그 구간을 손으로 넣어야 하고,
과거는 이미 끝난 값이라 불변이므로 시나리오 리비전이 아니라 공용 프로필에 둔다.

세 표가 **한 버전을 공유한다.** 한 표만 고쳐도 저장할 때 세 표를 함께 쓴다 — 부분 저장을
허용하면 어느 표가 어느 버전인지 알 수 없다. 그래서 화면은 세 표를 모두 세션에 들고 있다가
한 번에 저장한다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.profile_caption import profile_version_caption
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PAGE_DIALOG_SUFFIX,
    bootstrap_error_message,
)
from capa_simulation.persistence.cache import (
    clear_global_past_data_cache,
    get_scenario_repository,
    load_global_past_data,
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

HOME_PAST_FORM_KEY = "home_past_form"
HOME_PAST_DOWNLOAD_KEY = "home_past_download"
PAST_CLIPBOARD_KEY = "home_past_clipboard"
PAST_NOTE_KEY = "home_past_note"
PAST_DRAFT_KEY = "home_past_draft"
# 지금 열린 붙여넣기 팝업의 표 이름. HOME 한 화면에 팝업 칸은 하나다(`PAGE_DIALOG_SUFFIX` —
# 페이지를 떠나면 `forget_page_dialogs` 가 비운다).
PAST_DIALOG_KEY = f"home{PAGE_DIALOG_SUFFIX}"
# 저장은 읽어 둔 표로 저장된 그 표를 **지우고 다시 넣는다**(`replace_global_past_data`). 새 달만
# 붙여넣고 저장하면 이전 달이 사라진다. 누르기 전에 알아야 해 팝업과 저장 버튼에 남긴다.
PAST_REPLACE_NOTICE = (
    "저장하면 이 표는 붙여넣은 내용으로 통째로 바뀝니다 — 붙여넣지 않은 달·행은 지워지고 되돌릴 수 "
    "없습니다. 기존 행을 남기려면 함께 붙여넣으세요."
)


@dataclass(frozen=True)
class PastTableSpec:
    """한 표의 화면 이름·컬럼 계약·설명. 세 표가 같은 모양의 칸을 갖게 한다."""

    name: str
    title: str
    icon: str
    columns: tuple[str, ...]
    # 무엇을 넣는 표인지. 본문이 아니라 붙여넣기 팝업에 적는다 — 넣을 때 읽는 글이다.
    caption: str


PAST_TABLE_SPECS = (
    PastTableSpec(
        name="월별",
        title="월별 Density · Wafer Total",
        icon=":material/calendar_month:",
        columns=PAST_MONTH_COLUMNS,
        caption=(
            "Density 는 억Gb, Wafer Total 은 매입니다. Wafer Capa 와 B/N Capa 는 확보율을 "
            "곱해 만들므로 따로 넣지 않습니다. 빈칸·천 단위 쉼표(`180,000`)는 받지 않습니다."
        ),
    ),
    PastTableSpec(
        name="계획",
        title="계획 세부수량",
        icon=":material/table_rows:",
        columns=PAST_DETAIL_COLUMNS,
        caption=(
            "제품·Stack·거래선별 월 수량입니다. 화면에서 `계획 세부수량 상세`를 끄면 "
            "거래선을 합쳐 접어 보여 줍니다. 빈칸은 0 으로 읽습니다."
        ),
    ),
    PastTableSpec(
        name="확보율",
        title="공정별 확보율",
        icon=":material/percent:",
        columns=PAST_SECUREMENT_COLUMNS,
        caption=(
            "공정별 월 확보율입니다(1.05 = 105% — `105%`·빈칸은 받지 않습니다). "
            "**확보율 오름차순이 곧 B/N 순위**라 "
            "B/N 공정명을 따로 넣지 않습니다. 가용대수·소요대수는 받지 않으므로 상세 "
            "B/N 의 그 두 칸은 과거 구간에서 빕니다."
        ),
    ),
)


def render_past_data_management(database_path: str, profile: GlobalPastData) -> None:
    """세 표의 양식 내려받기·붙여넣기(팝업)와 한 번의 저장(맨 위 작업 줄).

    저장은 세 표가 한 버전을 공유해 **한 번**이다. 붙여넣기 결과는 대기로 쌓이고 맨 위
    `과거 구간 저장` 이 한꺼번에 기록한다(2026-09-29 — 저장 버튼을 표들 아래에서 위로).
    """
    stored = {
        "월별": profile.monthly,
        "계획": profile.plan_detail,
        "확보율": profile.securement,
    }
    draft = st.session_state.setdefault(PAST_DRAFT_KEY, {})
    with st.container(border=True):
        st.markdown("#### :material/history: 과거 구간")
        st.caption(profile_version_caption(profile, empty="아직 넣은 과거 구간이 없습니다"))
        _render_save(database_path, draft)
    for spec in PAST_TABLE_SPECS:
        _render_table_editor(database_path, profile.version, spec, stored[spec.name], draft)
    opened = st.session_state.get(PAST_DIALOG_KEY)
    for spec in PAST_TABLE_SPECS:
        if spec.name == opened:
            _paste_dialog(spec, draft)


def past_data_has_pending() -> bool:
    """붙여넣기로 읽어 두고 아직 저장하지 않은 표가 있는가. HOME 이 Past Data 탭에 점을 찍는다.

    읽기와 저장 모두 끝나면 곧바로 다시 돌므로(`st.rerun`) 탭을 만드는 회차의 값이 곧 지금 상태다.
    """
    return bool(st.session_state.get(PAST_DRAFT_KEY))


def merged_past_tables(
    database_path: str,
    draft: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """저장에 쓸 세 표. **저장된 값은 화면이 아니라 DB 에서 다시 읽는다.**

    세 표가 한 버전을 공유하므로 한 표만 고쳐도 나머지를 함께 다시 써야 하고, 그래서 이
    함수가 무엇을 「나머지」로 보느냐가 곧 남는 데이터다. 화면이 건넨 프로필을 믿으면
    안 된다 — HOME 은 `Past Data 포함` 토글이 꺼졌을 때 **표시용으로 행을 비운 프로필**을
    만들고, 그것을 그대로 쓰면 붙여넣지 않은 두 표가 빈 채로 기록되어 저장된 과거 구간이
    사라진다. `replace_global_past_data` 는 지우고 다시 넣으므로 되돌릴 수 없다.
    """
    stored = load_global_past_data(database_path)
    current = {
        "월별": stored.monthly,
        "계획": stored.plan_detail,
        "확보율": stored.securement,
    }
    return {name: draft.get(name, frame) for name, frame in current.items()}


def _open_paste(name: str) -> None:
    st.session_state[PAST_DIALOG_KEY] = name


def _close_paste() -> None:
    st.session_state.pop(PAST_DIALOG_KEY, None)


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
        # 작업 줄: 붙여넣기(팝업)·양식 내려받기와 저장·대기 행 수. 여는 버튼은 콜백으로 연다 —
        # 한 회차에 팝업이 둘 뜨지 않는다.
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.button(
                "Excel 붙여넣기",
                icon=":material/content_paste:",
                key=f"{PAST_CLIPBOARD_KEY}_{spec.name}_open",
                on_click=_open_paste,
                args=(spec.name,),
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
                key=f"{HOME_PAST_DOWNLOAD_KEY}_{spec.name}",
                label="양식 CSV",
            )
            st.caption(
                f"저장 {len(stored):,}행"
                + ("" if pending is None else f" · 대기 {len(pending):,}행")
            )
        render_flash(f"past_data_read_flash_{spec.name}")
        if not current.empty:
            with st.expander(f"현재 {len(current):,}행 확인", icon=":material/preview:"):
                st.dataframe(current, hide_index=True, width="stretch", height=240)


def _paste_dialog(spec: PastTableSpec, draft: dict[str, pd.DataFrame]) -> None:
    """표 하나를 붙여넣어 **대기**로 읽는다. 기록은 맨 위 `과거 구간 저장` 이 한다."""

    @st.dialog(f"Excel 붙여넣기 · {spec.title}", width="large", on_dismiss=_close_paste)
    def _body() -> None:
        st.caption(spec.caption)
        # 되돌릴 수 없는 덮어쓰기라는 것은 누르기 전에 알아야 한다 — Guide 로만 보내지 않는다.
        st.caption(PAST_REPLACE_NOTICE)
        with st.form(f"{HOME_PAST_FORM_KEY}_{spec.name}", border=False):
            clipboard = st.text_area(
                f"{spec.title} 붙여넣기",
                key=f"{PAST_CLIPBOARD_KEY}_{spec.name}",
                height=180,
                placeholder="Excel에서 헤더를 포함한 전체 셀 범위를 복사한 뒤 Ctrl+V",
            )
            submitted = st.form_submit_button(
                "붙여넣기 읽기",
                icon=":material/content_paste:",
                type="primary",
            )
        if not submitted:
            return
        try:
            draft[spec.name] = past_table_from_clipboard(clipboard, spec.columns)
        except BOOTSTRAP_ERRORS as exc:
            st.error(bootstrap_error_message(exc))
            return
        queue_flash(
            f"past_data_read_flash_{spec.name}",
            f"{len(draft[spec.name]):,}행을 읽었습니다. 맨 위 「과거 구간 저장」을 누르세요.",
        )
        _close_paste()
        st.rerun()

    _body()


def _render_save(
    database_path: str,
    draft: dict[str, pd.DataFrame],
) -> None:
    """맨 위 작업 줄 — 변경 메모와 `과거 구간 저장`. 읽어 둔 표가 없으면 저장이 잠긴다."""
    pending_names = [spec.name for spec in PAST_TABLE_SPECS if spec.name in draft]
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        save = st.button(
            "과거 구간 저장",
            icon=":material/save:",
            type="primary",
            disabled=not pending_names,
            help=(
                PAST_REPLACE_NOTICE
                if pending_names
                else "읽어 둔 표가 없습니다. 아래 표의 「Excel 붙여넣기」로 먼저 읽으세요."
            ),
        )
        note = st.text_input(
            "변경 메모",
            placeholder="예: 25년 실적 반영",
            key=PAST_NOTE_KEY,
            # 이 값은 옆 저장 버튼을 누를 때만 읽는다. Enter·포커스 이탈로 HOME 을 통째로
            # 다시 그릴 이유가 없고, 버튼을 누른 실행에 값이 함께 올라온다.
            on_change="ignore",
        )
    if pending_names:
        st.caption(
            f":orange-badge[덮어쓰기] 읽어 둔 표({'·'.join(pending_names)})가 저장된 그 표를 "
            "통째로 바꿉니다. 되돌릴 수 없습니다."
        )
    render_flash("past_data_save_flash")
    if not save:
        return
    merged = merged_past_tables(database_path, draft)
    try:
        get_scenario_repository(database_path).replace_global_past_data(
            merged, source=note.strip() or "웹 붙여넣기"
        )
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return
    clear_global_past_data_cache()
    st.session_state.pop(PAST_DRAFT_KEY, None)
    queue_flash("past_data_save_flash", "과거 구간을 공용 설정으로 저장했습니다.")
    st.rerun()
