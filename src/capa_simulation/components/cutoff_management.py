# Purpose: 공정별 Cut-off 입력 표를 그리고 저장하는 탭 본문을 담당한다.

"""공정별 Cut-off 편집 탭.

Cut-off 는 「그 공정 이후의 공정~입고까지 TAT 누적 합」이지만 저장소에 TAT 도 공정
선후관계도 없어 **사람이 적는 원장**이다(`services/process_cutoff.py`).

**이 표에 없는 공정은 월별 가용대수 산출에서 빠진다.** 0 을 적은 것과 다르다 — 0 은
「달력 월 그대로」이고, 없는 것은 「아직 기준을 못 정했으니 세지 말라」다. 그래서 설비는
있는데 Cut-off 를 안 적은 공정을 **화면에 반드시 드러낸다.** 조용히 빠지면 옆 탭의 합이
이유 없이 작아 보이고, 그 원인을 화면 어디서도 찾을 수 없다.

저장은 리비전을 만들지 않고 표를 통째로 갈아 끼운다(`0009`). 행을 지우는 것이 곧
「그 공정을 빼라」는 편집이라, 들어온 키만 덮는 방식으로는 그 뜻을 표현할 수 없다.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.components.editor_state import discard_editor, editor_widget_key
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.components.table_view_controls import (
    merge_edited_rows,
    render_table_view_controls,
)
from capa_simulation.persistence.equipment_cache import (
    clear_process_cutoff_cache,
    load_process_cutoff,
)
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    ProcessCutoffConflict,
)
from capa_simulation.services.process_cutoff import (
    PROCESS_CUTOFF_EDIT_COLUMNS,
    add_missing_cutoff_rows,
    build_process_cutoff_template,
    missing_cutoff_processes,
    process_cutoff_fingerprint,
)

__all__ = ["CUTOFF_BASE_KEY", "CUTOFF_DRAFT_KEY", "render_cutoff_management"]

CUTOFF_DRAFT_KEY = "equipment_cutoff_draft_v1"
# 초안이 출발한 저장본의 지문(`process_cutoff_fingerprint`). 저장 회차에 저장소가 대조한다.
CUTOFF_BASE_KEY = "equipment_cutoff_base_v1"
_EDITOR_KEY = "equipment_cutoff_editor_v1"
_FORM_KEY = "equipment_cutoff_form_v1"
_VIEW_PREFIX = "equipment_cutoff_view_v1"
_FLASH_KEY = "equipment_cutoff_flash_v1"
_CONFLICT_KEY = "equipment_cutoff_conflict_v1"


def render_cutoff_management(
    repository: DuckDBEquipmentRepository,
    *,
    equipment_processes: list[str],
    process_labels: ProcessLabels | None = None,
) -> pd.DataFrame:
    """Cut-off 탭을 그리고 **현재 저장된 값**을 돌려준다.

    돌려주는 것이 편집 중인 값이 아니라 저장된 값인 것은, 옆 탭의 GAP 계산이 저장되지
    않은 초안으로 숫자를 내면 안 되기 때문이다. 화면에 보이는 수와 계산에 쓰인 수가
    달라지는 것이 가장 나쁜 종류의 어긋남이다.

    **이 표는 원본 공정명을 적는 원장이다**(2026-10-10 사용자 결정 — 입력 칸의 값은 원본).
    편집표의 `공정` 칸·「Cut-off 를 적지 않은 공정」 경고·`process_cutoff.csv` 는 원본 그대로다 —
    경고의 이름을 그대로 새 행에 적어야 맞댄다. 공정 표시명(`process_labels`)은 `표 보기 설정` 의
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
        st.warning(
            f"설비는 있는데 Cut-off 를 적지 않은 공정 {len(missing)}개는 "
            f"월별 가용대수 산출에서 **빠집니다** — {', '.join(missing[:10])}"
            + (" …" if len(missing) > 10 else "")
        )
    elif equipment_processes:
        st.caption(f"설비가 있는 공정 {len(equipment_processes)}개가 모두 채워졌습니다.")

    draft = st.session_state.get(CUTOFF_DRAFT_KEY)
    if not isinstance(draft, pd.DataFrame) or CUTOFF_BASE_KEY not in st.session_state:
        # 초안이 출발한 저장본의 지문. 저장은 표 전체 교체라, 저장 회차에 저장본이 이 지문과 다르면
        # 다른 사람이 그 사이 저장한 것이다 — 옛 초안으로 덮지 않는다(`ProcessCutoffConflict`).
        # 초안만 있고 지문이 없는 세션(이 키가 생기기 전 세션)은 지금 저장본을 출발점으로 본다.
        st.session_state[CUTOFF_BASE_KEY] = process_cutoff_fingerprint(stored)
    if not isinstance(draft, pd.DataFrame):
        draft = stored.loc[:, PROCESS_CUTOFF_EDIT_COLUMNS].copy() if not stored.empty else None
    if draft is None:
        draft = build_process_cutoff_template(equipment_processes).loc[
            :, PROCESS_CUTOFF_EDIT_COLUMNS
        ]

    with st.container(horizontal=True, gap="small"):
        if st.button(
            "설비 공정으로 채우기",
            icon=":material/playlist_add:",
            help=(
                "설비 마스터와 기존보유대수에 있는데 표에 없는 공정을 빈 행으로 덧붙입니다. "
                "적어 둔 값은 그대로 둡니다."
            ),
            width="content",
        ):
            st.session_state[CUTOFF_DRAFT_KEY] = add_missing_cutoff_rows(draft, equipment_processes)
            # 편집 델타는 행 위치다. 표가 바뀌는데 옛 델타를 남기면 다른 공정에 붙는다.
            # 세션 칸만 지우면 브라우저가 옛 편집을 다시 보내므로 위젯 키를 바꾼다.
            discard_editor(_EDITOR_KEY)
            st.rerun()
        # 왕복 CSV 는 다른 설비 표와 같은 인코딩을 쓴다 — Excel 이 BOM 없이는 한글을 깬다.
        render_csv_download(
            data=stored.to_csv(index=False).encode("utf-8-sig"),
            file_name="process_cutoff.csv",
            key="equipment_cutoff_csv_v1",
        )

    view = render_table_view_controls(
        draft,
        key_prefix=_VIEW_PREFIX,
        editor_key=_EDITOR_KEY,
        filter_columns=["공정"],
        locked_columns=["공정", "Cutoff일수"],
        value_labels=process_labels.value_labels() if process_labels else None,
    )

    with st.form(_FORM_KEY, border=True):
        submitted = st.form_submit_button(
            "Cut-off 저장", icon=":material/save:", type="primary", width="content"
        )
        # 저장 결과는 누른 버튼 바로 아래다. 저장 뒤 rerun 을 건너 살아남게 flash 로 남긴다 —
        # `st.success` 뒤에 곧바로 `st.rerun()` 을 부르면 한 번도 보이지 않는다.
        render_flash(_FLASH_KEY)
        conflict = st.session_state.pop(_CONFLICT_KEY, None)
        if isinstance(conflict, str) and conflict:
            st.warning(conflict, icon=":material/sync_problem:")
        edited = st.data_editor(
            view.frame,
            key=editor_widget_key(_EDITOR_KEY),
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
                    help="0 은 「달력 월 그대로」입니다. 비워 두는 것과 뜻이 다릅니다.",
                ),
            },
        )

    merged = merge_edited_rows(draft, edited, filtered=view.filtered)
    st.session_state[CUTOFF_DRAFT_KEY] = merged

    if submitted:
        try:
            saved = repository.save_process_cutoff(
                merged, expected_fingerprint=str(st.session_state[CUTOFF_BASE_KEY])
            )
        except ProcessCutoffConflict as exc:
            # 최신 저장본으로 다시 연다. 옛 초안을 남기면 다음 저장도 같은 충돌이거나(지문 그대로),
            # 지문만 고치면 그 사람이 넣은 행을 지운다.
            clear_process_cutoff_cache()
            _reset_draft(load_process_cutoff(str(repository.database_path)))
            st.session_state[_CONFLICT_KEY] = (
                f"{exc} 최신 저장본으로 다시 열었으니 확인한 뒤 다시 고치세요."
            )
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        else:
            # 다음 회차가 저장된 값을 읽는다 — Static 대비 일정·필요단축일정이 이 값으로 센다.
            clear_process_cutoff_cache()
            _reset_draft(saved)
            queue_flash(_FLASH_KEY, f"공정별 Cut-off {len(saved)}건을 저장했습니다.")
            st.rerun()

    return stored


def _reset_draft(stored: pd.DataFrame) -> None:
    """초안을 저장본으로 다시 세우고 그 지문을 출발점으로 둔다. 편집표는 새 위젯으로 선다(행 위치
    델타가 다른 공정에 붙지 않게)."""
    st.session_state[CUTOFF_DRAFT_KEY] = (
        stored.loc[:, PROCESS_CUTOFF_EDIT_COLUMNS].copy()
        if not stored.empty
        else build_process_cutoff_template([]).loc[:, PROCESS_CUTOFF_EDIT_COLUMNS]
    )
    st.session_state[CUTOFF_BASE_KEY] = process_cutoff_fingerprint(stored)
    discard_editor(_EDITOR_KEY)
