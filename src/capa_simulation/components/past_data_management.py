# Purpose: HOME 설정 팝업 Past Data 탭에서 과거 구간 세 표를 받아 공용 프로필에 저장한다.

"""HOME 「설정」 팝업의 `Past Data` 탭(2026-11-02 — 전에는 HOME 의 `Past Data` 탭).

DB 원천은 적재 시점 이후의 달만 담는다. 지난 해를 함께 보려면 그 구간을 손으로 넣어야 하고,
과거는 이미 끝난 값이라 불변이므로 시나리오 리비전이 아니라 공용 프로필에 둔다.

세 표가 **한 버전을 공유한다.** 한 표만 고쳐도 저장할 때 세 표를 함께 쓴다 — 부분 저장을
허용하면 어느 표가 어느 버전인지 알 수 없다. 그래서 화면은 세 표를 모두 세션에 들고 있다가
한 번에 저장한다.

**붙여넣기는 팝업이 아니라 그 표 상자 안 칸이다.** 이 탭은 이미 「설정」 팝업(`st.dialog`) 안이고
Streamlit 은 팝업 안에 팝업을 열지 못한다(「Dialogs may not be nested inside other dialogs」).
표마다 「Excel 붙여넣기」 를 누르면 그 표 상자 안에 붙여넣기 칸(폼)이 펴지고, 한 번에 한 표만 편다
(`PAST_PASTE_KEY` — 세션 칸 하나). 「설정」 팝업을 열고 닫는 콜백이 그 칸을 걷는다
(`forget_past_paste`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.intro_summary import forget_intro_summary_check
from capa_simulation.components.paste_form import PasteTemplate, refuse_paste, render_paste_form
from capa_simulation.components.profile_caption import profile_version_caption
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
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

HOME_PAST_DOWNLOAD_KEY = "home_past_download"
PAST_CLIPBOARD_KEY = "home_past_clipboard"
PAST_NOTE_KEY = "home_past_note"
PAST_DRAFT_KEY = "home_past_draft"
# 지금 붙여넣기 칸을 편 표 이름(한 번에 한 표). 팝업 열림 칸이 아니다 — 「설정」 팝업 안의 칸이라
# 열림 칸 접미(`_open_dialog`)를 달지 않고, 「설정」 팝업을 열고 닫는 콜백이
# 걷는다(`forget_past_paste`).
PAST_PASTE_KEY = "home_past_paste_target"
# 저장은 읽어 둔 표로 저장된 그 표를 **지우고 다시 넣는다**(`replace_global_past_data`). 새 달만
# 붙여넣고 저장하면 이전 달이 사라진다. 누르기 전에 알아야 해 칸을 편 회차의 알림과 저장 버튼
# 풍선에 둔다.
PAST_REPLACE_NOTICE = (
    "저장하면 이 표는 붙여넣은 내용으로 통째로 바뀝니다 — 붙여넣지 않은 달·행은 지워지고 되돌릴 수 "
    "없습니다. 기존 행을 남기려면 함께 붙여넣으세요."
)


# 저장 단추 풍선의 둘째 말 — 「HOME 설정」 팝업 머리 안내 글(2026-11-04 사용자 검수 home-u01 「설명
# 제거」)이 하던 말 가운데 이 탭 몫(공용 설정 · 읽어 둔 표는 닫아도 남음)을 누르는 자리에 둔다.
PAST_SHARED_HELP = (
    "모든 사용자가 함께 쓰는 공용 설정입니다. 읽어 둔 표는 팝업을 닫아도 저장할 때까지 남습니다."
)


@dataclass(frozen=True)
class PastTableSpec:
    """한 표의 화면 이름·컬럼 계약·설명. 세 표가 같은 모양의 칸을 갖게 한다."""

    name: str
    title: str
    icon: str
    columns: tuple[str, ...]
    # 무엇을 넣는 표인지 — 붙여넣기 칸을 편 회차의 알림 전문(Alarm)이다. 칸에 늘 두지 않는다(같은
    # 말이 Guide 「Past Data」 에도 있다).
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
    """세 표의 양식 내려받기·붙여넣기(그 표 상자 안 칸)와 한 번의 저장(맨 위 작업 줄).

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


def past_data_has_pending() -> bool:
    """붙여넣기로 읽어 두고 아직 저장하지 않은 표가 있는가. HOME 이 사이드바 「HOME 설정」 상자와
    팝업 안 `Past Data` 탭에 점을 찍고, 화면 탭 줄이 HOME 탭에 점을 찍는다.

    읽기와 저장 모두 끝나면 곧바로 앱 전체가 다시 돌므로(`st.rerun`) 상자를 그리는 회차의 값이 곧
    지금 상태다.
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
    st.session_state[PAST_PASTE_KEY] = name


def forget_past_paste() -> None:
    """편 붙여넣기 칸을 걷는다 — 「설정」 팝업을 열고 닫는 콜백과 붙여넣기 칸의 「닫기」가
    부른다."""
    st.session_state.pop(PAST_PASTE_KEY, None)


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
        # 작업 줄: 붙여넣기(이 상자 안 칸)와 저장·대기 행 수. 양식은 붙여넣기 칸의 작업 줄에 선다
        # (맨 위 줄 왼쪽 읽기 · 오른쪽 양식 — 공통 부품). 여는 버튼은 콜백으로 연다 — 칸은 한 번에
        # 한 표만 편다.
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.button(
                "Excel 붙여넣기",
                icon=":material/content_paste:",
                key=f"{PAST_CLIPBOARD_KEY}_{spec.name}_open",
                on_click=_open_paste,
                args=(spec.name,),
            )
            st.caption(
                f"저장 {len(stored):,}행"
                + ("" if pending is None else f" · 대기 {len(pending):,}행")
            )
        if st.session_state.get(PAST_PASTE_KEY) == spec.name:
            _render_paste_form(database_path, version, spec, stored, draft)
        render_flash(f"past_data_read_flash_{spec.name}")
        if not current.empty:
            with st.expander(
                f"현재 {len(current):,}행 확인",
                icon=":material/preview:",
                key=f"past_data_current_expander_{spec.name}",
            ):
                st.dataframe(current, hide_index=True, width="stretch", height=240)


def _close_paste_action(spec: PastTableSpec) -> None:
    st.button(
        "닫기",
        icon=":material/close:",
        key=f"{PAST_CLIPBOARD_KEY}_{spec.name}_close",
        on_click=forget_past_paste,
    )


def _render_paste_form(
    database_path: str,
    version: int,
    spec: PastTableSpec,
    stored: pd.DataFrame,
    draft: dict[str, pd.DataFrame],
) -> None:
    """표 하나를 붙여넣어 **대기**로 읽는 칸(그 표 상자 안). 기록은 맨 위 `과거 구간 저장` 이 한다.

    칸을 편 회차에 되돌릴 수 없는 덮어쓰기와 그 표의 양식 규칙을 알림창 · Alarm 으로 알린다 — 상자
    안에 글을 두지 않는다(공통 부품 `components/paste_form`). 칸이 펴진 동안은 「HOME 설정」 팝업이
    붙여넣기 창이라 크기 손잡이가 선다. 읽으면 칸을 걷고 앱 전체를 다시 돌린다 — 사이드바 「HOME
    설정」 상자와 화면 탭 줄의 대기 점이 그 회차에 선다(팝업 안 위젯의 회차는 팝업만 돈다). 열림
    칸이 남아 「설정」 팝업은 그대로 열려 있다.
    """
    form_key = f"{PAST_CLIPBOARD_KEY}_{spec.name}"
    with st.container(border=True):
        submit = render_paste_form(
            form_key,
            text_key=form_key,
            text_label=f"{spec.title} 붙여넣기",
            apply_label="붙여넣기 읽기",
            template=PasteTemplate(
                # 표가 비어 있으면 예시 행이 양식이다. 칸이 펴진 표만 그려 팝업 매 실행에
                # 인코딩을 얹지 않는다.
                data=past_table_csv(
                    database_path,
                    version,
                    spec.name,
                    spec.columns,
                    stored if not stored.empty else past_sample_rows(spec.columns),
                ),
                file_name=f"PAST_{spec.name}.csv",
                key=f"{HOME_PAST_DOWNLOAD_KEY}_{spec.name}",
            ),
            opening=f"{PAST_REPLACE_NOTICE} {spec.caption}",
            size_key="past",
            side_actions=lambda: _close_paste_action(spec),
            in_box=True,
        )
        if submit is None:
            return
        try:
            draft[spec.name] = past_table_from_clipboard(submit.text, spec.columns)
        except BOOTSTRAP_ERRORS as exc:
            refuse_paste(form_key, bootstrap_error_message(exc))
            return
    queue_flash(
        f"past_data_read_flash_{spec.name}",
        f"{len(draft[spec.name]):,}행을 읽었습니다. 맨 위 「과거 구간 저장」을 누르세요.",
    )
    forget_past_paste()
    st.rerun()


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
                f"{PAST_REPLACE_NOTICE} {PAST_SHARED_HELP}"
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
    render_flash("past_data_save_flash")
    if not save:
        return
    merged = merged_past_tables(database_path, draft)
    try:
        save_past_tables(database_path, merged, source=note.strip() or "웹 붙여넣기")
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return
    st.session_state.pop(PAST_DRAFT_KEY, None)
    queue_flash("past_data_save_flash", "과거 구간을 공용 설정으로 저장했습니다.")
    st.rerun()


def save_past_tables(
    database_path: str, tables: Mapping[str, pd.DataFrame], *, source: str
) -> None:
    """과거 구간 세 표를 저장하고 그것을 읽는 캐시·확인을 비운다.

    입장 화면 Summary 도 과거 구간으로 달·계획을 채운다(2026-11-02 사용자 요청(검수표) home-02) — 이
    세션의 요약 확인을 비워(`forget_intro_summary_check`) 다음 회차가 새 판으로 다시 만든다. 저장이
    실패하면 아무것도 비우지 않는다(바뀐 것이 없다).
    """
    get_scenario_repository(database_path).replace_global_past_data(tables, source=source)
    clear_global_past_data_cache()
    forget_intro_summary_check()
