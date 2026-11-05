# Purpose: 가용설비 현황 「엑셀·CSV로 한꺼번에」 팝업 — 붙여넣기·CSV 를 미리보고 편집본에 넣는다.

"""가용설비 현황 「엑셀·CSV로 한꺼번에」 팝업(개편 명세 4-8 — 옛 설비 마스터 탭 「입력」 탭을 옮김).

- **자리**: 탭 ① 불러오기 줄의 「엑셀·CSV로 한꺼번에」 단추(표 컴포넌트 `dialog` 트리거)·첫 데이터
  안내 단추 → 큰 팝업. 열림 칸은 페이지 한 칸(`EQUIPMENT_DIALOG_KEY` — 값 `import`, 「가용설비
  설정」 팝업과 한 칸이라 한 실행에 팝업 하나)이고 여는 콜백은 `forget_page_dialogs()` 부터 부른다.
- **안은 옛 입력 탭 그대로**: 등록할 표(기본 설비 마스터) · Excel 표 붙여넣기 · CSV 업로드(50MB) ·
  「변경 미리보기」 · 미리보기(두 쪽 한 줄 · 신규/기존 대체/변경 없음 수 · 변경 표 · 저장 후 행 수).
  「바뀔 행」·「기존 대체」 는 넣으면 실제로 바뀌는 줄만 센다(같은 값 그대로인 대체 줄은 「변경
  없음」).
- **창 꼴은 공통 부품**(`components/paste_form`, 2026-11-05 검수 static-37): 작업 줄 왼쪽 「변경
  미리보기」 · 「편집본에 넣기」, 오른쪽 고른 표의 양식 내려받기. 창 안에 글을 두지 않는다 — 연
  회차의 맞대는 규칙과 미리보기의 알림 · 주의 · 거부는 알림창 · Alarm 이다. 창 크기 손잡이가 선다.
  위젯은 폼 밖이다(내려받기가 폼 안에 들어가지 못한다).
  붙여넣은 열만 바꾸는 규칙·옛 머리 이름·대소문자 경고·낡은 세션 거절·가정 세션 「배치 칸도
  붙여넣기」(기본 끔 — 설비 시나리오 2단계 Q2)·새 방문 때 미리보기 거두기는 그대로다.
- **끝 단추는 「편집본에 넣기」 하나**(D7, 사용자 R4) — 저장은 「저장 전 변경」 한 곳이다. 넣으면
  편집본 세 표를 미리본 후보로 바꾸고(`replace_equipment_buffer`), 새로 든 설비명을 표 목록 맨 위로
  불러오며, 되돌리기 통째 단계 하나(편집본 세 표·칸 초안·이름 지도·불러온 목록 사진)를 쌓고, 팝업을
  닫은 뒤 앱을 다시 돌린다. 칸 초안(못 읽은 글)도 비운다 — 남기면 넣은 값 위에 옛 초안 글이 덮인다.
- 미리보기는 지금 편집본 설비 마스터 전체를 다시 본다 — 편집본에 규칙 오류가 남았으면 기존
  보유대수·비가동 붙여넣기 미리보기도 그 오류로 막힌다(옛 입력 탭과 같다). 그때 오류 알림에
  「「저장 전 변경」 의 고칠 것을 먼저 고칩니다」 를 더한다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Final

import streamlit as st

from capa_simulation.components.equipment_data_workspace import (
    _PREVIEW_VISIT_KEY,
    _TARGETS,
    BUFFER_KEY,
    CLIPBOARD_KEY,
    CSV_UPLOAD_LIMIT_MB,
    DROP_EXAMPLE_ROWS_KEY,
    EQUIPMENT_DRAFT_KEY,
    GRID_LOADED_KEY,
    GRID_OVERLAY_KEY,
    GRID_UNDO_KEY,
    PASTE_LAYOUT_HELP,
    PASTE_LAYOUT_KEY,
    PASTE_LAYOUT_LABEL,
    PREVIEW_BUTTON_KEY,
    PREVIEW_KEY,
    TARGET_KEY,
    Frames,
    ImportReview,
    LayoutMode,
    _csv_scenario_mismatch,
    _saved_master,
    _upload_widget_key,
    assumption_group_paste_refusal,
    buffer_has_layout_edits,
    build_import_review,
    grid_loaded_ids,
    grid_overlay,
    layout_paste_refusal,
    paste_split_summary,
    pending_unit_renames,
    prune_new_unit_propagation,
    queue_grid_toast,
    remember_pasted_new_units,
    replace_equipment_buffer,
    stale_paste_refusal,
    stamp_layout_role,
)
from capa_simulation.components.equipment_save_fields import EquipmentSaveBasis
from capa_simulation.components.equipment_settings_dialog import (
    EQUIPMENT_DIALOG_KEY,
    IMPORT_DIALOG,
)
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.literal_markdown import literal_markdown, markdown_safe_tildes
from capa_simulation.components.paste_form import (
    PasteTemplate,
    announce_on_open,
    paste_action_row,
    paste_text_area,
    render_paste_window,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    forget_page_dialogs,
    page_visit,
)
from capa_simulation.services.equipment_csv import (
    EquipmentNamesError,
    baseline_csv_template,
    downtime_csv_template,
    equipment_csv_template,
    import_preview_changed_rows,
)
from capa_simulation.services.equipment_grid import (
    GridState,
    grid_index,
    load_ids,
    undo_to_state,
    whole_step,
)
from capa_simulation.services.equipment_validation import equipment_master_issues
from capa_simulation.services.floor_layout_profile import FloorCanvasMap
from capa_simulation.services.layout_overlay import Place

IMPORT_DIALOG_TITLE: Final = "엑셀·CSV로 한꺼번에"
# 공통 부품(`paste_form`)의 칸 앞머리와 창 크기를 기억하는 칸 이름 — 미리보기 표가 있어 다른 창과
# 따로 든다.
IMPORT_FORM_KEY: Final = "equipment_import"
IMPORT_SIZE_KEY: Final = "import"
IMPORT_APPLY_BUTTON_KEY: Final = "equipment_import_apply_v1"
IMPORT_APPLY_LABEL: Final = "편집본에 넣기"
# 팝업 안 알림 — 작은 편집표 알림 칸과 가른다(팝업이 그 글을 가져가지 않게). 모두 알림창 · Alarm
# 으로 간다(`popup_only` — 창 안에 그리지 않는다).
IMPORT_ERROR_KEY: Final = "equipment_import_error_v1"
IMPORT_NOTICE_KEY: Final = "equipment_import_notice_v1"
IMPORT_REVIEW_NOTICE_KEY: Final = "equipment_import_review_notice_v1"
IMPORT_REVIEW_CAUTION_KEY: Final = "equipment_import_review_caution_v1"
IMPORT_NOTE_SLOT_KEY: Final = "capa_paste_note_equipment_import_review"
IMPORT_LOCKED_HELP: Final = "「변경 미리보기」 를 먼저 누르면 넣을 수 있습니다."
# 팝업이 닫힌 수(넣은 뒤·Esc·바깥 누름 — `_close_dialog`). 표 불러오기 data 에 실려, 그 불러오기의
# 단추로 연 팝업이 닫힌 회차에 초점을 여는 단추로 돌린다(Streamlit 은 그림자 DOM 안 단추로 돌려주지
# 못해 BODY 로 빠진다).
IMPORT_CLOSED_KEY: Final = "equipment_import_closed_v1"
FIX_FIRST_HINT: Final = (
    "편집본 설비 마스터에 고칠 것이 남아 있으면 미리보기도 막힙니다 — 「저장 전 변경」 의 고칠 "
    "것을 "
    "먼저 고칩니다."
)


@dataclass(frozen=True)
class ImportContext:
    """팝업이 미리볼 때 쓰는 화면 조건(페이지가 세션에서 만든다)."""

    floor_canvases: FloorCanvasMap
    basis: EquipmentSaveBasis | None = None
    layout_mode: LayoutMode = "official"
    layout_lock_reason: str | None = None
    official_places: dict[str, Place] = field(default_factory=dict)


def open_equipment_import() -> None:
    """「엑셀·CSV로 한꺼번에」 를 여는 콜백 — 다른 팝업 칸부터 비운다(한 실행에 팝업 하나). 남은
    미리보기도 거둔다 — 팝업이 닫혀 있던 회차에 입력 칸은 버려져 늘 빈 칸으로 열린다
    (`_close_dialog`)."""
    forget_page_dialogs()
    st.session_state.pop(PREVIEW_KEY, None)
    st.session_state[EQUIPMENT_DIALOG_KEY] = IMPORT_DIALOG


def _close_dialog() -> None:
    """팝업을 닫는다(넣은 뒤·Esc·바깥 누름). 미리보기도 거둔다 — 닫힌 회차에 붙여넣기 칸·업로드는
    그리지 않아 버려지므로, 다시 열면 빈 입력에 옛 미리보기와 켜진 「편집본에 넣기」 만 남아 누를 때
    입력이 없다는 오류로 막힌다(옛 입력 탭은 늘 그려 둘이 함께 살았다)."""
    st.session_state.pop(EQUIPMENT_DIALOG_KEY, None)
    st.session_state.pop(PREVIEW_KEY, None)
    st.session_state[IMPORT_CLOSED_KEY] = import_closed_count() + 1


def import_closed_count() -> int:
    """이 세션에서 팝업이 닫힌 수(`IMPORT_CLOSED_KEY`). 표 불러오기 data 의 `dialogClosed` 다."""
    value = st.session_state.get(IMPORT_CLOSED_KEY, 0)
    return value if isinstance(value, int) else 0


def withdraw_preview_on_new_visit() -> None:
    """페이지에 새로 들어온 회차에는 미리보기를 거둔다 — 미리보기는 입력 칸보다 오래 사는 세션
    칸이라, 다른 화면을 다녀와 입력이 빈 팝업에 「편집본에 넣기」 만 남으면 누를 때 입력이 없다는
    오류로 막힌다. 같은 페이지 안의 `st.rerun()` 은 브라우저가 입력을 다시 보내므로 남긴다. 페이지가
    매 회차 부른다(팝업이 닫힌 회차에도)."""
    visit = page_visit()
    if st.session_state.get(_PREVIEW_VISIT_KEY) != visit:
        st.session_state.pop(PREVIEW_KEY, None)
    st.session_state[_PREVIEW_VISIT_KEY] = visit


def _render_review(review: ImportReview) -> None:
    # 바뀔 행은 넣으면 실제로 바뀌는 줄만 센다 — 내려받은 「현재 데이터」 를 그대로 올리면 「바뀌는
    # 값 없음 · 바뀔 행 0행」 이다(내려받기 캡션 「그대로 붙여넣어도 통과합니다」 와 어긋나지 않게).
    # 미리보기의 알림 · 주의는 창 안에 그리지 않는다 — 미리본 회차에 알림창으로 낸다
    # (`_queue_review_alerts`).
    changed = import_preview_changed_rows(review.changes)
    count = int(changed.sum())
    new_rows = int(review.changes["Import구분"].eq("신규").sum())
    unchanged = len(review.changes) - count
    head = f"{review.target} · 바뀔 행 {count:,}행"
    if not count:
        head = f"{review.target} · 바뀌는 값 없음 · 바뀔 행 0행"
    st.markdown(f"**{head}**")
    split = paste_split_summary(review.source, review.candidate)
    if split is not None:
        st.caption(f":material/call_split: {split}")
    with st.container(horizontal=True):
        st.metric("신규", f"{new_rows:,}건")
        st.metric("기존 대체", f"{count - new_rows:,}건")
        if unchanged:
            st.metric("변경 없음", f"{unchanged:,}건")
    st.dataframe(review.changes, hide_index=True, width="stretch", placeholder="")
    st.caption(
        f"넣은 뒤 편집본: 기존 보유대수 {len(review.candidate[0]):,}행 · "
        f"호기 {len(review.candidate[1]):,}행 · 비가동 {len(review.candidate[2]):,}행"
    )


def _queue_review_alerts(review: ImportReview) -> None:
    """미리본 회차의 알림 · 주의를 알림창 · Alarm 으로 담는다(갈래마다 한 칸 — 다음 회차가
    보낸다)."""
    notices = [markdown_safe_tildes(message) for message in review.notices]
    if st.session_state.get(DROP_EXAMPLE_ROWS_KEY, False):
        notices.append("예시 행은 빼고 검토했습니다.")
    if notices:
        queue_flash(IMPORT_REVIEW_NOTICE_KEY, " ".join(notices), kind="info", popup_only=True)
    if review.cautions:
        queue_flash(
            IMPORT_REVIEW_CAUTION_KEY,
            " ".join(markdown_safe_tildes(message) for message in review.cautions),
            kind="warning",
            popup_only=True,
        )


def _master_has_errors(frames: Frames, floor_canvases: FloorCanvasMap) -> bool:
    try:
        issues = equipment_master_issues(frames[1], floor_canvases=floor_canvases)
    except ValueError:
        return True
    return any(issue.blocking for issue in issues)


def _review(
    context: ImportContext,
    target: str,
    content: str | bytes,
    frames: Frames,
    *,
    paste_layout: bool,
    file_name: str | None,
) -> ImportReview:
    """옛 입력 탭과 같은 미리보기 — 낡은 세션·배치 잠금·가정 묶음 거절과 CSV 시나리오 주의까지."""
    mode = context.layout_mode
    basis = context.basis
    review = build_import_review(
        target,
        content,
        frames,
        floor_canvases=context.floor_canvases,
        drop_examples=bool(st.session_state.get(DROP_EXAMPLE_ROWS_KEY, False)),
        layout_role=None if mode == "locked" else mode,
        paste_layout=paste_layout,
        official_places=context.official_places,
    )
    if basis is not None and basis.stale:
        refusal = stale_paste_refusal(review, frames, basis)
        if refusal is not None:
            raise ValueError(refusal)
    if mode == "locked":
        refusal = layout_paste_refusal(
            review,
            saved=_saved_master(),
            renames=pending_unit_renames().units,
            reason=context.layout_lock_reason,
        )
        if refusal is not None:
            raise ValueError(refusal)
    elif mode == "overlay":
        refusal = assumption_group_paste_refusal(
            review,
            saved=_saved_master(),
            renames=pending_unit_renames().units,
            official_places=context.official_places,
        )
        if refusal is not None:
            raise ValueError(refusal)
    mismatch = _csv_scenario_mismatch(file_name, basis.scenario_name if basis else None)
    return replace(
        review,
        cautions=(*review.cautions, *((mismatch,) if mismatch is not None else ())),
        layout_pasted=paste_layout or mode != "overlay",
    )


def apply_import_review(review: ImportReview, *, layout_mode: LayoutMode = "official") -> str:
    """미리본 후보를 편집본에 넣는다(저장하지 않는다) — 편집본 세 표 통째 바꿈, 새로 든 설비명은 표
    목록 맨 위(상한 안), 되돌리기 통째 단계 하나, 칸 초안 비움, 빠진 「새 호기」 칸 호기의 함께 넣기
    고름 걷기. 돌려주는 글은 표 토스트다.

    넣은 편집본에 배치 편집(있던 호기 배치 칸·새 호기 자리)이 있으면 그때의 역할(`layout_mode`)을
    찍는다 — 넣고 나중에 「리비전 저장」 하므로, 그 사이 역할이 바뀌면(남이 그 가정 시나리오를
    공식으로 발행) 저장소가 쓰기 잠금 안에서 대조해 막고 Space·이 탭이 그 회차를 잠근다(설계 6-2,
    표 출납·Space 적용과 같다). 잠긴 회차는 미리보기가 배치를 바꾸는 붙여넣기를 막아 찍을 것이
    없다."""
    frames: Frames = st.session_state[BUFFER_KEY]
    saved = st.session_state[EQUIPMENT_DRAFT_KEY]
    renames = pending_unit_renames()
    overlay = grid_overlay()
    loaded = grid_loaded_ids()
    step = whole_step(
        "엑셀·CSV 넣기",
        GridState(frames=frames, saved=frames, renames=renames, overlay=overlay, loaded=loaded),
    )
    before = set(grid_index(frames[1], saved, renames.units).ids)
    replace_equipment_buffer(review.candidate)
    # 이 넣기로 든 새 호기 — 지운 호기와 함께 저장하면 결과 알림이 이름 바꾸기 길을 가리킨다.
    remember_pasted_new_units(frames[1], review.candidate[1])
    # 넣은 편집본에서 빠진 「새 호기」 칸 호기의 함께 넣기 고름을 걷는다(같은 이름이 이 넣기로 다시
    # 들면 저장 칸 체크를 따른다 — D8).
    prune_new_unit_propagation()
    st.session_state.pop(GRID_OVERLAY_KEY, None)
    st.session_state[GRID_UNDO_KEY] = undo_to_state((step,))
    if layout_mode != "locked" and buffer_has_layout_edits():
        stamp_layout_role(layout_mode)
    after = grid_index(review.candidate[1], saved, renames.units)
    fresh = [row_id for row_id in after.ids if row_id not in before]
    st.session_state[GRID_LOADED_KEY] = load_ids(loaded, fresh).loaded
    st.session_state.pop(PREVIEW_KEY, None)
    # 넣은 행은 미리보기 머리의 「바뀔 행」 과 같이 실제로 바뀐 줄만 센다 — 맞댄 줄 전부를 세면
    # 한 칸 고친 「현재 데이터」 를 「675행을 넣었습니다」 라 했다(2026-10-27 E2E).
    count = int(import_preview_changed_rows(review.changes).sum())
    text = (
        f"붙여넣기로 {count:,}행을 편집본에 넣었습니다 — 「저장 전 변경」 에서 확인하고 리비전을 "
        "저장하세요"
        if count
        else "붙여넣기에 바뀌는 값이 없어 편집본은 그대로입니다"
    )
    if overlay:
        text += f" · 못 읽은 칸 {len(overlay):,}개에 적던 글은 버렸습니다"
    queue_grid_toast("grid", text, undo=step.token)
    return text


# 창을 연 회차의 알림 글 — 맞대는 열 · 넣는 차례 · 저장 때(창 안 글 · 칸 풍선 대신, 2026-11-05 검수
# static-37). 앞 60자가 잘못 붙였을 때의 결과를 말한다(알림창 짧은 글).
IMPORT_OPENING = (
    "설비명으로 맞대므로 설비명을 바꿔 붙이면 새 호기가 됩니다 — 이름만 바꾸려면 호기 상세의 "
    "설비명 칸을 씁니다. 엑셀에서 복사한 표(머리 줄 포함)를 붙이거나 CSV 를 올린 뒤 「변경 "
    "미리보기」 → 「편집본에 넣기」. 넣은 것은 「저장 전 변경」 에서 확인하고 리비전을 저장할 때 "
    "저장됩니다."
)
# 등록할 표 → (양식 바이트, 파일 이름, 내려받기 key).
IMPORT_TEMPLATES: Final[Mapping[str, tuple[Callable[[], bytes], str, str]]] = {
    "설비 마스터": (
        equipment_csv_template,
        "equipment_master_template.csv",
        "equipment_import_template_master",
    ),
    "기존 보유대수": (
        baseline_csv_template,
        "equipment_baseline_template.csv",
        "equipment_import_template_baseline",
    ),
    "비가동 일정": (
        downtime_csv_template,
        "equipment_downtime_template.csv",
        "equipment_import_template_downtime",
    ),
}


def _template_of(target: str) -> PasteTemplate | None:
    """고른 표의 양식(작업 줄 오른쪽). 모르는 이름이면 없다."""
    entry = IMPORT_TEMPLATES.get(target)
    if entry is None:
        return None
    build, file_name, key = entry
    return PasteTemplate(data=build(), file_name=file_name, key=key)


def _render_body(context: ImportContext) -> None:
    frames: Frames = st.session_state[BUFFER_KEY]
    pending = st.session_state.get(PREVIEW_KEY)
    # 「적용」 잠금은 두지 않는다 — 입력이 글 칸이나 파일이고 「편집본에 넣기」 는 미리보기가
    # 잠근다.
    render_paste_window(IMPORT_FORM_KEY, size_key=IMPORT_SIZE_KEY, lock=False)
    # 알림은 모두 알림창 · Alarm 이다 — 창 안에 글을 두지 않는다(공통 부품 `components/paste_form`).
    announce_on_open(CLIPBOARD_KEY, IMPORT_FORM_KEY, IMPORT_OPENING)
    with st.container(key=IMPORT_NOTE_SLOT_KEY):
        render_flash(
            IMPORT_ERROR_KEY, IMPORT_NOTICE_KEY, IMPORT_REVIEW_NOTICE_KEY, IMPORT_REVIEW_CAUTION_KEY
        )
    target = st.selectbox("등록할 표", _TARGETS, key=TARGET_KEY)
    paste_layout = False
    if context.layout_mode == "overlay":
        # 가정 세션만 — 기본 끔(Q2). 배치 칸이 어디로 드는지는 이 체크의 풍선이 말한다(설계 규칙
        # UI-TXT-01 — 켜기 전에 읽는 칸의 뜻이다).
        paste_layout = st.checkbox(
            PASTE_LAYOUT_LABEL, value=False, key=PASTE_LAYOUT_KEY, help=PASTE_LAYOUT_HELP
        )
    paste_column, upload_column = st.columns([3, 2])
    with paste_column:
        clipboard = paste_text_area(
            IMPORT_FORM_KEY,
            text_key=CLIPBOARD_KEY,
            label="Excel 표 붙여넣기",
            placeholder=(
                "헤더를 포함해 Ctrl+V로 붙여넣으세요. 설비 마스터는 설비명과 바꿀 열만 넣어도 "
                "됩니다."
            ),
        )
    with upload_column:
        uploaded = st.file_uploader(
            "또는 CSV 파일 업로드",
            type=["csv"],
            key=_upload_widget_key(),
            max_upload_size=CSV_UPLOAD_LIMIT_MB,
        )
    locked = not isinstance(pending, ImportReview)
    with paste_action_row(_template_of(target)):
        preview_clicked = st.button(
            "변경 미리보기", key=PREVIEW_BUTTON_KEY, icon=":material/preview:"
        )
        apply_clicked = st.button(
            IMPORT_APPLY_LABEL,
            key=IMPORT_APPLY_BUTTON_KEY,
            type="primary",
            disabled=locked,
            icon=":material/input:",
            # 잠근 단추에만 까닭 풍선(설계 규칙 UI-INP-07).
            help=IMPORT_LOCKED_HELP if locked else None,
        )
    if isinstance(pending, ImportReview):
        _render_review(pending)
    if not (preview_clicked or apply_clicked):
        return
    try:
        if clipboard.strip() and uploaded is not None:
            raise ValueError(
                "붙여넣기와 CSV 파일이 함께 있습니다. 사용할 입력 하나만 남기고 다시 미리보세요."
            )
        content: str | bytes = uploaded.getvalue() if uploaded is not None else clipboard
        if not content.strip():
            raise ValueError("Excel 표를 붙여넣거나 CSV 파일을 올린 뒤 미리보세요.")
        layout_pasted = paste_layout or context.layout_mode != "overlay"
        if (
            apply_clicked
            and isinstance(pending, ImportReview)
            and pending.matches(target, content, frames, layout_pasted=layout_pasted)
        ):
            apply_import_review(pending, layout_mode=context.layout_mode)
            _close_dialog()
            st.rerun()
        review = _review(
            context,
            target,
            content,
            frames,
            paste_layout=paste_layout,
            file_name=uploaded.name if uploaded is not None else None,
        )
        st.session_state[PREVIEW_KEY] = review
        _queue_review_alerts(review)
        if apply_clicked:
            queue_flash(
                IMPORT_NOTICE_KEY,
                "입력 또는 편집본이 바뀌어 미리보기를 갱신했습니다. 변경 내용을 확인한 뒤 다시 "
                "넣으세요.",
                kind="info",
            )
    except BOOTSTRAP_ERRORS as exc:
        st.session_state.pop(PREVIEW_KEY, None)
        # 설비명을 날로 담은 거절은 이름마다 구두점을 막아 다시 짓는다 — 물결표만 막으면 「NEW*A*1」
        # 이 기울임 「NEWA1」 로 보였다(2026-10-27 E2E).
        message = (
            exc.text(literal_markdown)
            if isinstance(exc, EquipmentNamesError)
            else bootstrap_error_message(exc)
        )
        if _master_has_errors(frames, context.floor_canvases):
            message = f"{message}\n\n{FIX_FIRST_HINT}"
        queue_flash(IMPORT_ERROR_KEY, markdown_safe_tildes(message), kind="error", popup_only=True)
    # 앱 범위로 다시 돈다 — 팝업 안 단추의 회차가 늘 프래그먼트 회차는 아니다(앱 회차에서
    # `scope="fragment"` 는 오류). 열림 칸이 남아 팝업은 열린 채 미리보기·오류를 그린다.
    st.rerun()


@st.dialog(
    IMPORT_DIALOG_TITLE, width="large", icon=":material/upload_file:", on_dismiss=_close_dialog
)
def render_import_dialog(context: ImportContext) -> None:
    """팝업 본문(`render_equipment_dialog_host` 가 열림 칸이 `import` 일 때 부른다)."""
    _render_body(context)
