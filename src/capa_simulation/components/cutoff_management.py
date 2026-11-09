# Purpose: 공정별 Cut-off 입력 표를 그리고 저장하는 「가용설비 설정」 팝업 본문을 담당한다.

"""공정별 Cut-off 편집 — 가용설비 현황 「가용설비 설정」 팝업의 본문(`equipment_settings_dialog`).

Cut-off 는 「그 공정 이후의 공정~입고까지 TAT 누적 합」이지만 저장소에 TAT 도 공정
선후관계도 없어 **사람이 적는 원장**이다(`services/process_cutoff.py`).

**이 표에 없는 공정은 월별 가용대수 산출에서 빠진다.** 0 을 적은 것과 다르다 — 0 은
「달력 월 그대로」이고, 없는 것은 「아직 기준을 못 정했으니 세지 말라」다. 그래서 설비는
있는데 Cut-off 를 안 적은 공정을 **화면에 반드시 드러낸다.** 조용히 빠지면 Static 대비
일정의 합이 이유 없이 작아 보이고, 그 원인을 화면 어디서도 찾을 수 없다.

저장은 리비전을 만들지 않고 표를 통째로 갈아 끼운다(`0009`). 행을 지우는 것이 곧
「그 공정을 빼라」는 편집이라, 들어온 키만 덮는 방식으로는 그 뜻을 표현할 수 없다.
"""

from __future__ import annotations

from typing import NoReturn

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.editor_state import discard_editor, editor_widget_key
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.literal_markdown import literal_names
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.table_toolbar import render_csv_download, toolbar_clearance
from capa_simulation.components.table_view_controls import (
    TableView,
    merge_edited_rows,
    render_table_view_controls,
    view_of,
)
from capa_simulation.components.write_guard import (
    forget_seen,
    held_notice,
    held_profile_conflict,
    is_own_save,
    note_notice,
    note_profile_conflict,
    notice_marks,
    own_save_marks,
    profile_conflict_marks,
    queue_refusal,
    remember_own_save,
    remember_seen,
    seen,
    take_refusal,
)
from capa_simulation.page_bootstrap import bootstrap_error_message
from capa_simulation.persistence.equipment_cache import (
    clear_process_cutoff_cache,
    load_process_cutoff,
)
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    ProcessCutoffConflict,
)
from capa_simulation.services.process_cutoff import (
    PROCESS_CUTOFF_COLUMNS,
    PROCESS_CUTOFF_EDIT_COLUMNS,
    add_missing_cutoff_rows,
    build_process_cutoff_template,
    missing_cutoff_processes,
    process_cutoff_fingerprint,
)

__all__ = [
    "CUTOFF_BASE_KEY",
    "CUTOFF_DRAFT_KEY",
    "CUTOFF_SAVE_HELP",
    "CUTOFF_UNCHANGED_MESSAGE",
    "forget_cutoff_draft",
    "render_cutoff_management",
]

CUTOFF_DRAFT_KEY = "equipment_cutoff_draft_v1"
# 초안이 출발한 저장본의 지문(`process_cutoff_fingerprint`). 저장 회차에 저장소가 대조한다. 초안을
# 세우는 자리에서만 적는다(`write_guard.remember_seen`).
CUTOFF_BASE_KEY = "equipment_cutoff_base_v1"
# 이 세션이 한 Cut-off 저장의 제 저장 표지 이름(`write_guard.own_save_marks`).
CUTOFF_SAVE_NAME = "equipment_process_cutoff"
_EDITOR_KEY = "equipment_cutoff_editor_v1"
_FORM_KEY = "equipment_cutoff_form_v1"
_VIEW_PREFIX = "equipment_cutoff_view_v1"
_FLASH_KEY = "equipment_cutoff_flash_v1"
# 채우기 결과 칸. 빠른 둘째 누름의 창(`write_guard.held_notice`)은 칸마다 보므로 저장 칸과 가른다 —
# 한 칸이면 다른 단추의 누름을 같은 단추의 둘째 누름으로 읽어 그 누름에 답하지 못한다.
_FILL_FLASH_KEY = "equipment_cutoff_fill_flash_v1"
# 저장 제출의 곁 답을 다음 회차로 넘기는 이름(`write_guard.queue_refusal` — 남의 저장에 거부된 답은
# `CUTOFF_SAVE_NAME`).
_REJECTED_NAME = "equipment_process_cutoff_rejected"
_UNCHANGED_NAME = "equipment_process_cutoff_unchanged"
_LOCKED_VIEW_KEY = "equipment_cutoff_locked_view_v1"
# 편집표에 건 보기(행 필터 · 감춘 칸) — 보기 설정은 폼 안이라 「보기 적용」 · 다른 제출 단추를
# 눌러야 오고, 편집표는 그 앞 제출의 보기로 그려 그 제출의 칸 편집을 옛 행 자리로 읽는다(2026-11-08
# 사용자 답 X1).
_APPLIED_VIEW_KEY = "equipment_cutoff_applied_view_v1"
_VIEW_APPLY_KEY = "equipment_cutoff_view_apply_v1"
# 왕복 양식 CSV 단추와, 그 단추를 폼 제출 줄(「Cut-off 저장」 · 「설비 공정으로 채우기」) 오른쪽
# 끝에 얹는 칸 · 제출 줄(2026-11-08 사용자 답 g17 · d6). 내려받기 단추는 폼 안에 둘 수
# 없다(Streamlit).
_CSV_KEY = "equipment_cutoff_csv_v1"
_ACTIONS_KEY = "equipment_cutoff_actions_v1"
_SUBMIT_ROW_KEY = "equipment_cutoff_submit_row_v1"
# 폼 윗선 · 오른쪽 끝에서 제출 줄 단추까지(Streamlit 1.63 폼 꼴 — 사본 앱에서 잰 값).
CSV_INSET_PX = 14
# 제출 줄이 CSV 단추 밑으로 들어가지 않게 비우는 오른쪽 자리(단추 폭 + 간격의 올림).
CSV_RESERVE_PX = 156
# 「Cut-off 저장」 단추 풍선 — 팝업 머리에 안내 글을 두지 않으므로 꼭 남길 둘(공용 설정 · 저장하지
# 않고 닫으면 사라짐)을 누르는 자리에 둔다(HOME `home_preference.SHARED_SAVE_HELP` 와 같은 꼴).
CUTOFF_SAVE_HELP = (
    "모든 설비 시나리오가 함께 쓰는 공용 Cut-off 로 저장합니다. 저장하지 않고 팝업을 닫으면 고친 "
    "칸은 사라집니다."
)
# 바꾼 것 없는 저장의 알림(설계 규칙 UI-STA-01 — 쓰지 않는다). 다른 공용 저장과 같이 단추 곁이다.
CUTOFF_UNCHANGED_MESSAGE = (
    "바뀐 것이 없습니다 — 표가 지금 공용 Cut-off 그대로라 저장하지 않았습니다."
)


def forget_cutoff_draft() -> None:
    """초안·출발점·편집표를 걷는다 — 「가용설비 설정」 팝업을 새로 열 때(`open_equipment_settings`)
    부른다.

    초안은 그리는 회차마다 다시 적히므로, 걷지 않으면 한 번 열어 본 세션은 그때 저장본의 사본을
    계속 보였다 — 남이 AVI-PKG 를 12 로 저장한 뒤 다시 열어도 옛 값이었고, 고치지 않은 채 누른
    저장이 「다른 사용자가 먼저 …」 로 거부됐다(바깥 화면은 저장본으로 센다, 2026-10-27 E2E). 다음에
    그리는 회차가 최신 저장본에서 초안과 출발점을 다시 세운다. 팝업은 「닫으면 저장하지 않은 칸은
    사라진다」 이므로 여는 때 걷는 것과 뜻이 같다(닫힘은 X·Esc 말고 페이지 이동으로도 와 여는 쪽에
    둔다)."""
    st.session_state.pop(CUTOFF_DRAFT_KEY, None)
    st.session_state.pop(_APPLIED_VIEW_KEY, None)
    forget_seen(CUTOFF_BASE_KEY)
    discard_editor(_EDITOR_KEY)


def render_cutoff_management(
    repository: DuckDBEquipmentRepository,
    *,
    equipment_processes: list[str],
    process_labels: ProcessLabels | None = None,
    locked_reason: str | None = None,
) -> pd.DataFrame:
    """Cut-off 표를 그리고 **현재 저장된 값**을 돌려준다.

    `locked_reason` 을 주면 표를 읽기 전용으로 보이고(저장값 그대로) 「설비 공정으로 채우기」·CSV
    단추(왕복 양식)·저장을 세우지 않는다 — Cut-off 는 모든 설비 시나리오 공용이라 가정 설비
    시나리오에서는 고치지 않는다(E3). 잠근 동안 초안(세션 칸)은 건드리지 않는다. 초안은 팝업이 열린
    동안만 산다 — 팝업을 새로 열면 `forget_cutoff_draft` 가 걷어 최신 저장본에서 다시 선다.

    돌려주는 것이 편집 중인 값이 아니라 저장된 값인 것은, Static 대비 일정의 GAP 계산이 저장되지
    않은 초안으로 숫자를 내면 안 되기 때문이다(그 화면은 저장된 값을 캐시 경계에서 직접 읽는다).
    화면에 보이는 수와 계산에 쓰인 수가 달라지는 것이 가장 나쁜 종류의 어긋남이다.

    **이 표는 원본 공정명을 적는 원장이다**(2026-10-10 사용자 결정 — 입력 칸의 값은 원본).
    편집표의 `공정` 칸·「Cut-off 를 적지 않은 공정」 경고·`process_cutoff.csv` 는 원본 그대로다 —
    경고의 이름을 그대로 새 행에 적어야 맞댄다. 공정 표시명(`process_labels`)은 「표 보기」 팝오버의
    `공정` 필터 선택지 글자에만 쓴다. 편집표에 표시명 보조 칸을 두지 않는다 — 편집 결과가 곧
    저장값이라(필터가 없으면 `merge_edited_rows` 가 편집표를 통째로 돌려준다) 보조 칸을 저장 전에
    매번 걸러야 하고, `볼 컬럼` 에도 끼어든다.
    """
    # 회차마다 DB 를 열지 않는다 — 저장이 성공하면 아래에서 비운다(`equipment_cache`).
    stored = load_process_cutoff(str(repository.database_path))

    # Cut-off 의 뜻(표준 납기 일수, 소수는 내림)은 가용설비 현황 Guide 가 말한다.
    st.markdown("#### :material/schedule: 공정별 Cut-off")

    missing = missing_cutoff_processes(equipment_processes, stored)
    if missing:
        # 곁 경고는 고칠 표가 바로 아래일 때만이다 — 잠긴 표에는 고칠 입력이 없어 상태 알림
        # (`report_missing_cutoffs` — `EQ-12`)에 맡긴다(설계 규칙 UI-NTF-02).
        if locked_reason is None:
            _render_missing_cutoffs(missing)

    if locked_reason is not None:
        # 자리에는 표지 한 마디, 까닭은 풍선이다(설계 규칙 UI-TXT-04 · UI-INP-07). 왕복 양식 CSV 는
        # 잠긴 표에도 둔다 — 표 도구 막대 내려받기에는 감춘 「제품구분」 칸이 없고 표가 비면 받을
        # 길이 없다(2026-11-08 사용자 답 d6). 고치는 표와 같은 꼴로 줄 오른쪽 끝이다.
        with st.container(
            horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"
        ):
            st.caption(":material/lock: Cut-off 잠김", help=locked_reason, width="content")
            _render_roundtrip_csv(stored)
        toolbar_clearance()
        st.dataframe(
            stored.loc[:, PROCESS_CUTOFF_EDIT_COLUMNS] if not stored.empty else stored,
            hide_index=True,
            width="stretch",
            placeholder="",
            key=_LOCKED_VIEW_KEY,
        )
        return stored

    draft = st.session_state.get(CUTOFF_DRAFT_KEY)
    if not isinstance(draft, pd.DataFrame) or seen(CUTOFF_BASE_KEY) is None:
        # 초안이 출발한 저장본의 지문. 저장은 표 전체 교체라, 저장 회차에 저장본이 이 지문과 다르면
        # 다른 사람이 그 사이 저장한 것이다 — 옛 초안으로 덮지 않는다(`ProcessCutoffConflict`).
        # 초안만 있고 지문이 없는 세션(이 키가 생기기 전 세션)은 지금 저장본을 출발점으로 본다 —
        # 일부러 정한 결정이다 — 본 값이 없다고 저장을 거부하지 않는다(시험
        # `tests/test_write_guard_cas.py`).
        remember_seen(CUTOFF_BASE_KEY, process_cutoff_fingerprint(stored))
    if not isinstance(draft, pd.DataFrame):
        draft = stored.loc[:, PROCESS_CUTOFF_EDIT_COLUMNS].copy() if not stored.empty else None
    if draft is None:
        draft = build_process_cutoff_template(equipment_processes).loc[
            :, PROCESS_CUTOFF_EDIT_COLUMNS
        ]

    # 왕복 CSV 는 「Cut-off 저장」 · 「설비 공정으로 채우기」 와 한 줄 오른쪽 끝이다(2026-11-08
    # 사용자 답 g17 — 창 작업 줄은 적용 왼쪽 · 내려받기 오른쪽, 설계 규칙 UI-INP-08). 내려받기
    # 단추는 폼 안에 둘 수 없어 폼 앞에 두고 서식(`_actions_style`)이 제출 줄 끝에 얹는다(흐름 높이
    # 0).
    with st.container(key=_ACTIONS_KEY):
        _render_roundtrip_csv(stored)
        form = st.form(_FORM_KEY, border=True)
    with form:
        # 표에 친 칸은 폼을 제출해야 서버에 온다. 「설비 공정으로 채우기」 도 그 칸 위에 얹으므로 폼
        # 밖 단추로 두지 않는다 — 친 값을 모른 채 표를 다시 세우면 그 값이 말없이 사라진다.
        view_applied = False

        def view_button() -> None:
            nonlocal view_applied
            view_applied = st.form_submit_button("보기 적용", key=_VIEW_APPLY_KEY)

        with st.container(key=_SUBMIT_ROW_KEY, horizontal=True, gap="small"):
            submitted = st.form_submit_button(
                "Cut-off 저장",
                help=CUTOFF_SAVE_HELP,
                icon=":material/save:",
                type="primary",
                width="content",
            )
            filling = st.form_submit_button(
                "설비 공정으로 채우기",
                help=(
                    "설비 마스터와 기존보유대수에 있는데 표에 없는 공정을 빈 행으로 덧붙입니다. "
                    "적어 둔 값은 그대로 둡니다."
                ),
                icon=":material/playlist_add:",
                width="content",
            )
            # 보기 설정은 이 제출 줄 끝 「표 보기 ▾」 팝오버다 — 접힘 줄을 따로 세우지 않는다
            # (2026-11-09 사용자 보드 T5 — 설비 마스터 작은 편집표와 같은 꼴). 폼 안이라 칸을 친 채
            # 공정 필터 · 볼 컬럼을 바꿔도 회차가 돌지 않아 친 칸이 남고, 「보기 적용」 이 친 칸과
            # 새 보기를 함께 가져간다(2026-11-08 사용자 답 X1).
            requested = render_table_view_controls(
                draft,
                key_prefix=_VIEW_PREFIX,
                # 고른 보기의 행이 바뀌어도 편집표는 버리지 않는다 — 적용한 보기로 그린다.
                editor_key=f"{_EDITOR_KEY}_requested_view",
                filter_columns=["공정"],
                locked_columns=["공정", "Cutoff일수"],
                value_labels=process_labels.value_labels() if process_labels else None,
                footer=view_button,
            )
            # 서식만 든 글은 이벤트 칸으로 가 팝업 본문이 그 칸을 쓰게 된다 — 빈 칸 하나를 함께 둬
            # 제출 줄 안 제자리에 둔다(폭 0).
            st.html(_actions_style())
        # 저장 결과는 누른 버튼 바로 아래 한 자리다. 저장 뒤 rerun 을 건너 살아남게 flash 로 남긴다
        # — `st.success` 뒤에 곧바로 `st.rerun()` 을 부르면 한 번도 보이지 않는다. 거부 ·
        # 「바뀐 것이 없습니다」 도 제출 회차가 담아 둔 글을 여기서 꺼낸다
        # (`write_guard.queue_refusal` — dict 칸이라 끊기지 않는다). 거부 글도 알림 칸 안에 쓴다 —
        # 칸을 한 겹 더 싸면 알림이 없는 회차에 바깥 칸이 비지 않아 줄 사이 간격을
        # 먹는다(`app_header.EMPTY_FORM_SLOT_SELECTOR` — 2026-11-09 사용자 검수 g17).
        with render_flash(_FLASH_KEY, _FILL_FLASH_KEY):
            refused = take_refusal(CUTOFF_SAVE_NAME)
            if refused is not None:
                st.warning(refused, icon=":material/sync_problem:")
            rejected = take_refusal(_REJECTED_NAME)
            if rejected is not None:
                st.error(rejected)
            if take_refusal(_UNCHANGED_NAME) is not None:
                st.info(CUTOFF_UNCHANGED_MESSAGE, icon=":material/info:")
        view = _applied_view(draft, requested)
        # 바로 위가 누를 것이 든 제출 줄(단추 · 팝오버 · 오른쪽 끝 CSV)이다 — 표 도구 막대(표 머리
        # 위 37px)가 그 줄을 덮지 않게 띄운다. 띄움과 표는 간격 없는 칸 하나에 둔다 — 폼 줄
        # 사이(14px)를 띄움 앞뒤로 두 번 먹지 않게(2026-11-09 사용자 검수 g17). 띄움 24 + 줄 사이
        # 14 = 38px 로 막대 바로 위까지다.
        with st.container(gap=None):
            toolbar_clearance()
            edited = st.data_editor(
                view.frame,
                key=editor_widget_key(_EDITOR_KEY, in_form=True),
                num_rows=view.row_mode,
                width="stretch",
                hide_index=True,
                # 결측 칸은 `None` 글자가 아니라 빈칸으로 그린다(`month_editor` 와 같은 규칙).
                placeholder="",
                column_config={
                    **dict(view.column_config),
                    "Cutoff일수": st.column_config.NumberColumn(
                        "Cutoff일수",
                        min_value=0.0,
                        step=0.5,
                        format="%.1f",
                        help=(
                            "0 은 「달력 월 그대로」입니다. 비워 두는 것과 뜻이 다릅니다. 소수점은 "
                            "내림해 일 단위로 셉니다(35.8 → 35일) — 다른 화면은 그 일수로 적습니다."
                        ),
                    ),
                },
            )

    # 행을 더하거나 지운 제출의 편집표는 RangeIndex 가 아니다. 그 꼴이 초안이 되면 다음 표가
    # `hide_index=True` 를 무시하고 인덱스를 머리 없는 필수 칸으로 세우고(`table_view_controls`), 그
    # 칸이 빈 새 행은 브라우저가 보내지 않아 저장에서 빠진다.
    merged = merge_edited_rows(draft, edited, filtered=view.filtered).reset_index(drop=True)
    st.session_state[CUTOFF_DRAFT_KEY] = merged
    # 친 칸을 앞 보기로 얹은 뒤 새 보기를 건다 — 보이는 행이 바뀌니 편집표는 새로 선다.
    if _store_view(requested):
        discard_editor(_EDITOR_KEY)
        if not (filling or submitted):
            st.rerun()
    elif view_applied:
        st.rerun()

    # 제출을 받은 회차는 어느 갈래로 끝나든 `st.rerun()` 으로 표를 이 초안으로 다시 그린다 — 행
    # 추가가 열린 표의 위젯 id 는 데이터로 지어져, 초안만 바꾸고 끝나면 화면의 표는 옛 id 로 남아
    # 다음 제출의 칸 편집이 버려진다. 그래서 곁 답도 그리지 않고 담아 넘긴다.
    if filling:
        _fill_missing_rows(merged, equipment_processes)

    if submitted:
        # 표지 dict 는 저장 전에 받아 둔다 — 저장 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
        save_marks = own_save_marks()
        conflict_marks = profile_conflict_marks()
        held = held_profile_conflict(conflict_marks, CUTOFF_SAVE_NAME)
        if held is not None:
            # 남의 저장에 거부된 누름의 둘째 누름이다. 거부 회차가 초안·출발점을 최신으로 다시
            # 세웠으므로 이 누름은 고친 칸 없이 대조를 지난다 — 저장하면 같은 내용을 다시 쓰며
            # 「저장했습니다」 가 거부 알림을 덮고, 버려진 편집이 말없이 지나간다. 저장하지 않고 그
            # 거부를 다시 알린다(write_guard).
            queue_refusal(CUTOFF_SAVE_NAME, held)
            st.rerun()
        expected = str(seen(CUTOFF_BASE_KEY))
        notices = notice_marks()
        try:
            if _same_as_saved(stored, merged, expected):
                # 방금 저장한 같은 표의 느린 둘째 누름이면 알림 칸이 그 성공을 이미 다시 그렸다 —
                # 「바뀐 것이 없습니다」 로 덮지도 겹쳐 쓰지도 않는다(write_guard.held_notice).
                if held_notice(_FLASH_KEY) is None:
                    queue_refusal(_UNCHANGED_NAME, CUTOFF_UNCHANGED_MESSAGE)
                st.rerun()
            saved = repository.save_process_cutoff(merged, expected_fingerprint=expected)
        except ProcessCutoffConflict as exc:
            clear_process_cutoff_cache()
            latest = load_process_cutoff(str(repository.database_path))
            if is_own_save(
                CUTOFF_SAVE_NAME, expected, process_cutoff_fingerprint(latest), save_marks
            ):
                # 같은 단추의 빠른 두 번 누름이다 — 첫 누름이 이미 저장했다(write_guard).
                _reset_draft(latest)
                queue_flash(_FLASH_KEY, _saved_message(latest))
                st.rerun()
            message = (
                f"{bootstrap_error_message(exc)} 최신 저장본으로 다시 열었으니 확인한 뒤 다시 "
                "고치세요."
            )
            # 거부 표지는 초안을 다시 세우기 **전에** 적는다 — 다시 세운 출발점으로는 창 안의 둘째
            # 누름이 대조를 지난다. 표지·알림 모두 dict 칸이라 끊기지 않는다(write_guard).
            note_profile_conflict(conflict_marks, CUTOFF_SAVE_NAME, message)
            queue_refusal(CUTOFF_SAVE_NAME, message)
            # 최신 저장본으로 다시 연다. 옛 초안을 남기면 다음 저장도 같은 충돌이거나(지문 그대로),
            # 지문만 고치면 그 사람이 넣은 행을 지운다.
            _reset_draft(latest)
            st.rerun()
        except ValueError as exc:
            queue_refusal(_REJECTED_NAME, bootstrap_error_message(exc))
            st.rerun()
        else:
            remember_own_save(
                CUTOFF_SAVE_NAME, expected, process_cutoff_fingerprint(saved), save_marks
            )
            # 느린 둘째 누름이 이 알림을 다시 낸다(write_guard.held_notice — 위 「바뀐 것이
            # 없습니다」 갈래).
            note_notice(notices, _FLASH_KEY, _saved_message(saved))
            # 다음 회차가 저장된 값을 읽는다 — Static 대비 일정·필요 단축 일정이 이 값으로 센다.
            clear_process_cutoff_cache()
            _reset_draft(saved)
            queue_flash(_FLASH_KEY, _saved_message(saved))
            st.rerun()

    return stored


def _fill_missing_rows(draft: pd.DataFrame, equipment_processes: list[str]) -> NoReturn:
    """친 칸까지 얹은 초안(`draft`)에 빠진 공정을 빈 행으로 덧붙이고 결과를 알린다. 저장은 하지
    않는다.

    잠그지 않고 누른 회차에 답한다 — 초안의 빈 행과 손으로 더한 행까지 보려면 폼을 받아야 해서
    그리는 회차에는 더할 공정이 있는지 모른다(설계 규칙 UI-INP-07). 새 행은 표 끝이라 첫 화면에 안
    보여 알림이 그 변화를 말한다. 더할 공정이 없으면 행을 바꾸지 않고 그렇게 답한다.

    빠른 두 번 누름의 둘째 누름은 더할 공정이 없어도 그렇게 답하지 않는다 — 첫 누름이 방금 더한
    것을 「더할 공정이 없습니다」 로 덮게 된다. 첫 누름의 알림은 알림 칸이 다시 낸다
    (`write_guard.held_notice`)."""
    notices = notice_marks()
    filled = add_missing_cutoff_rows(draft, equipment_processes)
    added = len(filled) - len(draft)
    if added:
        st.session_state[CUTOFF_DRAFT_KEY] = filled
        # 편집 델타는 행 위치다. 표가 바뀌는데 옛 델타를 남기면 다른 공정에 붙는다.
        # 세션 칸만 지우면 브라우저가 옛 편집을 다시 보내므로 위젯 키를 바꾼다.
        discard_editor(_EDITOR_KEY)
        message = f"{added}개 행을 표 끝에 더했습니다."
        note_notice(notices, _FILL_FLASH_KEY, message)
        queue_flash(_FILL_FLASH_KEY, message)
    elif held_notice(_FILL_FLASH_KEY) is None:
        queue_flash(_FILL_FLASH_KEY, "더할 공정이 없습니다.", kind="info")
    st.rerun()


def _render_roundtrip_csv(stored: pd.DataFrame) -> None:
    """왕복 양식 `process_cutoff.csv` — 저장된 표 그대로(감춘 「제품구분」 칸 포함), 비었으면 머리
    줄만 든 빈 양식이다. 다른 설비 표와 같은 인코딩을 쓴다 — Excel 이 BOM 없이는 한글을 깬다."""
    missing = [column for column in PROCESS_CUTOFF_COLUMNS if column not in stored.columns]
    frame = stored.reindex(columns=[*stored.columns, *missing]) if missing else stored
    render_csv_download(
        data=frame.to_csv(index=False).encode("utf-8-sig"),
        file_name="process_cutoff.csv",
        key=_CSV_KEY,
    )


def _actions_style() -> str:
    """CSV 단추를 폼 제출 줄 오른쪽 끝에 얹는 서식 — 단추 칸은 폼 앞 흐름에서 빠지고(절대 위치)
    제출 줄은 그 폭만큼 오른쪽을 비워 좁은 창에서 줄이 바뀌어도 단추 밑으로 들어가지 않는다.
    빈 칸 하나를 함께 담는다(`st.html` 의 서식만 든 글은 이벤트 칸으로 간다)."""
    return (
        "<style>"
        f".st-key-{_ACTIONS_KEY} {{ position: relative; }}"
        f".st-key-{_CSV_KEY} {{ position: absolute; top: {CSV_INSET_PX}px; "
        f"right: {CSV_INSET_PX}px; width: auto; z-index: 1; }}"
        f".st-key-{_SUBMIT_ROW_KEY} {{ padding-right: {CSV_RESERVE_PX}px; }}"
        "</style><span></span>"
    )


def _view_state(view: TableView) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    return dict(view.filters), tuple(view.hidden_columns)


def _applied_view(draft: pd.DataFrame, requested: TableView) -> TableView:
    """편집표에 건 보기 — 앞 제출의 고름(`_APPLIED_VIEW_KEY`)을 지금 초안에 다시 건다. 처음 그리는
    회차는 고른 보기 그대로다."""
    state = st.session_state.get(_APPLIED_VIEW_KEY)
    if not (isinstance(state, tuple) and len(state) == 2 and isinstance(state[0], dict)):
        st.session_state[_APPLIED_VIEW_KEY] = _view_state(requested)
        return requested
    return view_of(draft, filters=state[0], hidden_columns=state[1])


def _store_view(requested: TableView) -> bool:
    """고른 보기를 편집표에 건다 — 앞 보기와 달랐으면 참이다."""
    state = _view_state(requested)
    if st.session_state.get(_APPLIED_VIEW_KEY) == state:
        return False
    st.session_state[_APPLIED_VIEW_KEY] = state
    return True


def _same_as_saved(stored: pd.DataFrame, edited: pd.DataFrame, expected: str) -> bool:
    """편집본이 이 회차가 그린 최신 저장본과 같은가.

    출발점(`expected`)이 그 저장본이어야 한다 — 옛 화면의 저장은 견주지 않고 저장소의 지문 대조에
    맡긴다(남의 저장 뒤라면 거부). 같음은 저장소가 쓸 꼴끼리다(`process_cutoff_fingerprint` — 칸을
    잘못 적었으면 `ValueError`).
    """
    saved = process_cutoff_fingerprint(stored)
    return expected == saved and process_cutoff_fingerprint(edited) == saved


def _saved_message(saved: pd.DataFrame) -> str:
    return f"공정별 Cut-off {len(saved)}건을 저장했습니다."


def _reset_draft(stored: pd.DataFrame) -> None:
    """초안을 저장본으로 다시 세우고 그 지문을 출발점으로 둔다. 편집표는 새 위젯으로 선다(행 위치
    델타가 다른 공정에 붙지 않게)."""
    st.session_state[CUTOFF_DRAFT_KEY] = (
        stored.loc[:, PROCESS_CUTOFF_EDIT_COLUMNS].copy()
        if not stored.empty
        else build_process_cutoff_template([]).loc[:, PROCESS_CUTOFF_EDIT_COLUMNS]
    )
    remember_seen(CUTOFF_BASE_KEY, process_cutoff_fingerprint(stored))
    discard_editor(_EDITOR_KEY)


def _render_missing_cutoffs(missing: list[str]) -> None:
    """팝업 안 「Cut-off 를 적지 않은 공정」 — 고칠 표가 바로 아래라 자리 글(이름 목록)이다. 화면
    밖에서도 알도록 같은 조건을 상태 알림(`report_missing_cutoffs` — `EQ-12`)이 따로 낸다.

    원본 공정명을 그대로 새 행에 옮겨 적는 글이다 — 물결표가 지움선·별표가 기울임이 되면 옮긴 이름이
    맞지 않는다. 「빠집니다」 굵게는 살리고 이름마다 막는다."""
    st.warning(
        f"설비는 있는데 Cut-off 를 적지 않은 공정 {len(missing)}개는 "
        f"월별 가용대수 산출에서 **빠집니다** — {literal_names(missing[:10])}"
        + (" …" if len(missing) > 10 else "")
    )


def report_missing_cutoffs(equipment_processes: list[str], stored: pd.DataFrame) -> None:
    """설비는 있는데 Cut-off 를 적지 않은 공정의 상태 알림(`EQ-12` — 2026-11-03 결정 보드 D2).

    가용설비 현황이 회차마다(빠진 공정이 없어도 — 해소 · 이벤트 칸 한 자리) 부른다 —
    「가용설비 설정」 팝업을 열지 않아도 Static 대비 일정 합이 왜 작은지 알게 한다. 팝업 안
    경고(`_render_missing_cutoffs`)는 고칠 표 곁의 자리 글이라 표가 잠긴 회차에는 서지 않는다.
    Cut-off 는 모든 설비 시나리오 공용이라 범위가 없고, 내용은 빠진 공정 이름 목록이다(알림창 ·
    패널은 평문이라 이름을 막지 않는다).
    """
    missing = missing_cutoff_processes(equipment_processes, stored)
    shown = ", ".join(missing[:10]) + (" …" if len(missing) > 10 else "")
    alerts.state(
        "EQ-12",
        scope=None,
        content=missing or None,
        active=bool(missing),
        text=(
            f"Cut-off 를 적지 않은 공정 {len(missing)}개 — 가용대수에서 빠짐 · "
            "「가용설비 설정」 에서 행을 더하세요"
        ),
        full=(
            f"설비는 있는데 Cut-off 를 적지 않은 공정 {len(missing)}개는 월별 가용대수 산출에서 "
            f"빠집니다 — {shown}. 가용설비 현황 사이드바 「가용설비 설정」 › 공정별 Cut-off "
            "에서 「설비 공정으로 채우기」 로 행을 더해 저장하세요."
        ),
    )
