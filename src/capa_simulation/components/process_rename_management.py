# Purpose: Admin Area 의 Proc Rename 탭에서 공용 공정 표시명을 CSV·붙여넣기·직접 편집으로 관리한다.

"""공용 공정 표시명 프로필의 웹 편집기와 Excel 붙여넣기 가져오기.

여기서 저장한 표시명은 **화면 표기에만** 적용된다. 보고용 다운로드와 DB 저장값은 원본
공정명 그대로다. 저장은 시나리오와 무관한 공용 DB 프로필이라 리비전을 만들지 않는다.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation import alerts
from capa_simulation.components.admin_dialog import (
    admin_dialog_is_open,
    close_admin_dialog,
    open_admin_dialog,
)
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.intro_summary import forget_intro_summary_check
from capa_simulation.components.literal_markdown import literal_markdown, literal_names
from capa_simulation.components.paste_form import (
    PasteTemplate,
    refuse_paste,
    render_paste_form,
    tell_paste,
)
from capa_simulation.components.process_labels import process_labels_from_rules
from capa_simulation.components.profile_caption import profile_version_caption
from capa_simulation.components.table_toolbar import render_csv_download, toolbar_clearance
from capa_simulation.components.write_guard import (
    SEEN_MISSING_MESSAGE,
    SeenToken,
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
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence._sql_helpers import ProfileVersionConflict
from capa_simulation.persistence.cache import (
    clear_global_process_rename_cache,
    load_global_process_rename,
)
from capa_simulation.persistence.models import GlobalProcessRename
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.process_rename import (
    PROCESS_RENAME_COLUMNS,
    ProcessRenameDuplicateError,
    drop_blank_process_rename_rows,
    empty_process_rename_rules,
    prepare_process_rename_rules,
    process_rename_duplicate_message,
    process_rename_from_clipboard,
    process_rename_to_csv,
)

# 이 탭의 붙여넣기 팝업. Admin Area 의 팝업 칸은 하나라 값이 탭을 가른다.
PASTE_DIALOG = "process_rename_paste"
CLIPBOARD_KEY = "admin_area_process_rename_clipboard"
CLIPBOARD_FORM_KEY = "admin_area_process_rename"
# 전체 교체 확인 체크박스의 자리. 적용에 성공하면 비워 다음 붙여넣기가 다시 확인을 거친다.
CLIPBOARD_CONFIRM_KEY = "admin_area_process_rename_clipboard_confirm"
EDITOR_KEY = "admin_area_process_rename_editor"
# 직접 편집을 시작한 회차가 본 공용 version. 저장 회차에 저장소가 대조한다.
BASE_VERSION_KEY = "admin_area_process_rename_base_version"
# 이 세션이 한 직접 편집 저장의 표지 이름(`write_guard.own_save_marks`)과 성공 알림.
PROCESS_RENAME_SAVE_NAME = "admin_area_process_rename"
PROCESS_RENAME_SAVED_MESSAGE = "공정 표시명을 공용 설정으로 저장했습니다."
# 바꾼 것 없는 직접 편집 저장의 알림(2026-11-01 개선 I5 — 새 버전을 만들지 않는다).
PROCESS_RENAME_UNCHANGED_MESSAGE = (
    "바뀐 것이 없습니다 — 표가 지금 공용 표시명 그대로라 새 버전을 만들지 않았습니다."
)
# 직접 편집 저장의 결과 알림 칸(`flash`·`write_guard.held_notice`).
PROCESS_RENAME_FLASH_KEY = "process_rename_flash"
# 바꾼 것 없는 붙여넣기의 알림(직접 편집과 같은 「바뀐 것이 없습니다」 — 설계 규칙 UI-STA-01).
PROCESS_RENAME_PASTE_UNCHANGED_MESSAGE = (
    "바뀐 것이 없습니다 — 붙여넣은 표가 지금 공용 표시명 그대로라 새 버전을 만들지 않았습니다."
)


@st.cache_data(show_spinner=False, max_entries=4)
def _process_rename_csv(database_path: str, version: int, _rules: pd.DataFrame) -> bytes:
    """내려받기 CSV. 순수 함수라 공용 버전이 같으면 결과도 같다.

    이 탭은 닫혀 있어도 항상 그리므로(폼 입력값 보존) 직렬화 비용이 모든 rerun 에 실린다.
    규칙은 교체할 때마다 version 이 오르므로 키에 version 만 있으면 된다.
    """
    del database_path, version
    return process_rename_to_csv(_rules)


def render_process_rename_management(
    repository: DuckDBScenarioRepository,
    available_processes: list[str],
    *,
    alert_tab: str | None = "",
) -> None:
    """Proc Rename 탭 한 장. `available_processes` 는 안내용이며 비어 있어도 편집·저장한다.
    `alert_tab` 은 이 탭 이름(상태 알림 `AD-06` 의 「그 화면으로」 —
    `state_alerts.open_tab_name`)이고 None 이면 닫힌 탭이라 그 회차에는 알리지 않는다."""
    st.subheader("Proc Rename")
    database_path = str(repository.database_path)
    try:
        profile = load_global_process_rename(database_path)
        csv_bytes = _process_rename_csv(database_path, profile.version, profile.rules)
    except BOOTSTRAP_ERRORS as exc:
        render_data_error(
            bootstrap_error_message(exc), code="AD-07", text="공정 표시명을 읽지 못했습니다"
        )
        return

    version_caption = profile_version_caption(profile, empty="아직 지정한 표시명이 없습니다")
    # 작업 줄: 지금 표 내려받기와 Excel 붙여넣기(팝업 — 창 안 작업 줄에도 양식이 선다). 붙여넣기는
    # 가끔 하는 전체 교체라 본문을 차지하지 않는다(2026-09-29 사용자 결정). 여는 버튼은 콜백으로
    # 연다.
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.caption(version_caption)
        render_csv_download(
            data=csv_bytes,
            file_name=f"PROC_RENAME_v{profile.version}.csv",
            key="admin_area_process_rename_download",
        )
        st.button(
            "Excel 붙여넣기",
            icon=":material/content_paste:",
            key="admin_area_process_rename_open_paste",
            on_click=open_admin_dialog,
            args=(PASTE_DIALOG,),
        )
    # 직접 편집 저장의 「바뀐 것이 없습니다」 도 이 칸(성공 알림 자리)에 선다.
    notice = render_flash(PROCESS_RENAME_FLASH_KEY)

    labels = process_labels_from_rules(profile.rules, profile.version)
    unmatched = labels.unmatched(available_processes)
    collisions = labels.owned_name_collisions(available_processes)
    # 표시명을 쓰는 화면의 공정 선택 상자는 겹친 글자를 가른다(`unique_format_func`). 표·그림·버튼은
    # 가르지 않아 같은 글자로 보인다. 검사 범위는 시나리오 `RQ_MODULE` 공정뿐이다 — 설비 마스터까지
    # 보려면 Admin 이 설비 DB 를 읽어야 해서 넓히지 않고 문구에 적는다. 상태 알림(`AD-06` — 알림창 ·
    # Alarm, 자리에 그리지 않는다)이고 없어도 부른다(해소). 알림창 · 패널은 평문이라 이름을 막지
    # 않는다.
    if alert_tab is not None:
        alerts.state(
            "AD-06",
            scope=None,
            content=sorted(collisions) or None,
            active=bool(collisions),
            text=(
                f"보유 공정의 원본명과 같은 표시명 {len(collisions):,}건 — 두 공정이 같은 글자로 "
                "보임 · Proc Rename 에서 고치기"
            ),
            full=(
                f"보유 공정의 원본명과 같은 표시명 {len(collisions):,}건이 있습니다: "
                f"{', '.join(collisions[:10])}{' …' if len(collisions) > 10 else ''}. "
                "서로 다른 두 공정이 같은 글자로 보입니다 — 공정을 고르는 상자에서는 "
                "「표시명 (원본)」 으로 갈라 보이지만 표·그림·버튼에서는 같은 글자로 보입니다. "
                "값은 원본이라 계산·조인은 그대로이며 저장은 막지 않습니다. 설비 마스터에만 있는 "
                "공정은 여기서 검사하지 않습니다."
            ),
            tab=alert_tab,
        )

    if admin_dialog_is_open(PASTE_DIALOG):
        _clipboard_dialog(repository, profile.rules, csv_bytes, profile.version)
    _render_direct_editor(repository, profile, available_processes, notice, unmatched)


def _listed(names: list[str], limit: int = 10) -> str:
    """풍선에 늘어놓는 이름 — 앞의 `limit` 개를 막아 쉼표로 잇는다."""
    return literal_names(names[:limit]) + (" …" if len(names) > limit else "")


def unmatched_help(unmatched: list[str]) -> str:
    """「보유 공정 밖 표시명」 표지의 풍선 — 그 이름들과 어디에 입혀지는지.

    「무시합니다」 가 아니다 — 표시명은 원본이 보유 공정인지 보지 않고 입혀, 시나리오 밖 공정을
    그리는 화면(가용설비·실적 데모·Dynamic Capa·Capa Chatbot)에는 그대로 나온다(AGENTS 8장).
    늘어놓는 공정명은 사람 글이라 막아 적는다(AGENTS 9장 — 「ZZ~9~9 *q*」).
    """
    return (
        f"{_listed(unmatched)} — 이 시나리오의 보유 공정에 없는 공정입니다. 이 시나리오의 계산 "
        "화면에는 나오지 않지만, 그 공정이 나오는 화면(가용설비·실적·Dynamic Capa·Capa Chatbot "
        "등)에서는 그대로 적용됩니다."
    )


def _save_error_message(exc: BaseException) -> str:
    """저장·붙여넣기 실패를 알림 상자(마크다운)에 그릴 글.

    1:1 위반은 겹친 이름(사람 글)을 막아 같은 문장으로 다시 짓는다 — 예외 글 그대로면
    `bootstrap_error_message` 가 물결표만 막아 「~x~ *y*」 의 별표가 기울임이 된다(2026-10-26 E2E).
    나머지는 `bootstrap_error_message` 다.
    """
    if isinstance(exc, ProcessRenameDuplicateError):
        return process_rename_duplicate_message(
            exc.label, [literal_markdown(name) for name in exc.names]
        )
    return bootstrap_error_message(exc)


@st.dialog("Excel 붙여넣기 · 공정 표시명", width="large", on_dismiss=close_admin_dialog)
def _clipboard_dialog(
    repository: DuckDBScenarioRepository,
    current: pd.DataFrame,
    template_csv: bytes,
    template_version: int,
) -> None:
    # 적용이 무엇을 바꾸는지는 누르기 전에 알아야 해 창을 연 회차에 알린다(창 안에 글을 두지
    # 않는다).
    submit = render_paste_form(
        CLIPBOARD_FORM_KEY,
        text_key=CLIPBOARD_KEY,
        text_label="공정 표시명 표 붙여넣기",
        apply_label="붙여넣기 표시명 적용",
        template=PasteTemplate(
            data=template_csv,
            file_name=f"PROC_RENAME_v{template_version}.csv",
            key="admin_area_process_rename_template_download",
        ),
        opening="적용하면 현재 공용 표시명 전체가 교체됩니다.",
        confirm_key=CLIPBOARD_CONFIRM_KEY,
        confirm_label="현재 공용 공정 표시명 전체 교체를 확인했습니다.",
    )
    if submit is None:
        return
    if not submit.text.strip():
        refuse_paste(CLIPBOARD_FORM_KEY, "적용할 공정 표시명 표를 Excel에서 복사해 붙여넣으세요.")
        return
    if not submit.confirmed:
        refuse_paste(CLIPBOARD_FORM_KEY, "전체 교체 확인을 선택하세요.")
        return
    try:
        imported = process_rename_from_clipboard(submit.text)
        if imported.equals(prepare_process_rename_rules(current)):
            tell_paste(CLIPBOARD_FORM_KEY, PROCESS_RENAME_PASTE_UNCHANGED_MESSAGE)
            return
        _save_process_rename(repository, imported, source="Excel 붙여넣기")
    except BOOTSTRAP_ERRORS as exc:
        refuse_paste(CLIPBOARD_FORM_KEY, _save_error_message(exc))
    else:
        # 확인 체크는 이번 교체 한 번에만 유효하다. 팝업이 닫힌 회차에 값이 버려지지만, 끊긴
        # 회차까지 여기서 함께 버린다.
        st.session_state.pop(CLIPBOARD_CONFIRM_KEY, None)
        queue_flash(
            PROCESS_RENAME_FLASH_KEY,
            "붙여넣은 공정 표시명을 공용 설정으로 적용했습니다.",
        )
        close_admin_dialog()
        st.rerun()


def _render_direct_editor(
    repository: DuckDBScenarioRepository,
    profile: GlobalProcessRename,
    available_processes: list[str],
    notice: DeltaGenerator,
    unmatched: list[str],
) -> None:
    """직접 편집 표. 저장은 **버전 대조**다 — 판정 기준과 같은 결로 편집을 시작한 회차의 version 을
    세션(`BASE_VERSION_KEY`)에 두고 저장 회차에 넘긴다. 그 사이 다른 사람이 저장했으면 저장소가
    거부한다(그대로 쓰면 그 사람이 넣은 표시명을 모르는 채 덮는다).

    **바꾼 것 없는 저장은 새 버전을 만들지 않는다**(2026-11-01 개선 I5) — 최신 저장본을 보고 고친
    표가 그 저장본과 같으면 쓰지 않고 `notice`(머리 알림 칸)에 「바뀐 것이 없습니다」 를 적는다(변경
    메모만 적은 저장도 같다). 아직 저장본이 없으면(v0) 첫 저장은 쓴다.

    보유 공정에 없는 공정에 지정된 표시명(`unmatched`)은 표에 있지만 이 시나리오의 계산 화면에는
    그리지 않는 항목이라 표 머리 표지 + 풍선으로 둔다(설계 규칙 UI-TXT-04 — 숨은 데이터 안내).
    거부 · 오류는 저장 단추 바로 위 칸(`save_status`)에 선다 — 표 밑에 두면 단추에서 표 높이만큼
    떨어진다(UI-LAY-03, 표시순서 관리와 같은 꼴)."""
    current = profile.rules
    submitted_base = seen(BASE_VERSION_KEY)
    st.markdown("#### 직접 편집")
    if unmatched:
        st.caption(f"보유 공정 밖 표시명 {len(unmatched):,}건", help=unmatched_help(unmatched))
    if available_processes:
        with st.expander(
            f"보유 공정 {len(available_processes):,}개",
            icon=":material/list:",
            key="admin_area_process_rename_available_expander",
        ):
            # 원본 공정명이다. 여기에 표시명을 입히면 붙여넣을 원본을 확인할 수 없다.
            st.dataframe(
                pd.DataFrame({"공정": available_processes}),
                hide_index=True,
                width="stretch",
                height=240,
            )
    editable = (
        empty_process_rename_rules() if current.empty else prepare_process_rename_rules(current)
    )
    save_status = st.container()
    with st.form("admin_area_process_rename_edit_form"):
        # 작업 줄(저장·메모)은 표 **위**, 버튼이 왼쪽이다(오른쪽 끝은 표 도구 막대에 가린다).
        with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
            submitted = st.form_submit_button(
                "공용 공정 표시명 저장",
                icon=":material/save:",
                type="primary",
            )
            note = st.text_input(
                "변경 메모",
                placeholder="예: LOB 차트 공정명 축약",
                key="admin_area_process_rename_note",
            )
        # 「변경 메모」 칸은 오른쪽 끝까지 늘어난다 — 표 도구 막대가 그 칸에 닿지 않게 띄운다(AGENTS
        # 9장 「표 도구 막대」).
        toolbar_clearance()
        edited = st.data_editor(
            editable,
            hide_index=True,
            num_rows="dynamic",
            width="stretch",
            height=420,
            # 결측 칸은 `None` 글자가 아니라 빈칸으로 그린다(`month_editor` 와 같은 규칙).
            placeholder="",
            column_config={
                "공정": st.column_config.TextColumn("공정 (원본)"),
                "표시명": st.column_config.TextColumn("표시명 (화면 표기)"),
            },
            key=EDITOR_KEY,
        )
    refused = take_refusal(PROCESS_RENAME_SAVE_NAME)
    if refused is not None:
        save_status.error(refused)
    if not submitted:
        # 이 회차가 그린 저장본이 사용자가 본 화면이다 — 제출·충돌 회차에는 적지 않는다
        # (write_guard).
        remember_seen(BASE_VERSION_KEY, profile.version)
        return
    # 표지 dict 는 저장 전에 받아 둔다 — 저장 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
    save_marks = own_save_marks()
    conflict_marks = profile_conflict_marks()
    held = held_profile_conflict(conflict_marks, PROCESS_RENAME_SAVE_NAME)
    if held is not None:
        # 남의 저장에 거부된 누름의 둘째 누름이다 — 옛 화면의 입력이라 저장하지 않고 그 거부를 다시
        # 알린다(write_guard). 이 회차가 거부 회차의 글을 이미 꺼내 그렸으면 한 번만 — 둘째 누름이
        # 거부 뒤 회차를 글을 꺼내기 전에 끊으면 그 글이 이 회차로 넘어온다(2026-10-26 E2E). 이
        # 회차가 그린 최신 저장본이 사용자가 보게 될 화면이라 본 version 은 적는다 — 둘째 누름이
        # 거부 뒤 회차(제출 아님)를 끊어 그 회차가 적지 못했다(판정 기준과 같은 꼴, 2026-10-27
        # E2E).
        remember_seen(BASE_VERSION_KEY, profile.version)
        if refused != held:
            save_status.error(held)
        return
    if not isinstance(submitted_base, int):
        # 편집을 시작한 version 을 모른다 — 지금 version 으로 대체하지 않는다(write_guard).
        queue_refusal(PROCESS_RENAME_SAVE_NAME, SEEN_MISSING_MESSAGE)
        st.rerun()
    expected_version = submitted_base
    notices = notice_marks()
    try:
        revised = drop_blank_process_rename_rows(
            pd.DataFrame(edited, columns=list(PROCESS_RENAME_COLUMNS))
        )
        if _same_as_saved(profile, revised, expected_version):
            # 방금 저장한 같은 표의 느린 둘째 누름(새로 그린 표에 닿았다)이면 알림 칸이 그 성공을
            # 이미 다시 그렸다 — 「바뀐 것이 없습니다」 로 덮지도 겹쳐 쓰지도
            # 않는다(write_guard.held_notice).
            if held_notice(PROCESS_RENAME_FLASH_KEY) is None:
                notice.info(PROCESS_RENAME_UNCHANGED_MESSAGE, icon=":material/info:")
            return
        _save_process_rename(
            repository,
            revised,
            source=note.strip() or "웹 직접 편집",
            expected_version=expected_version,
            save_marks=save_marks,
        )
    except ProfileVersionConflict as exc:
        # 앱 밖의 쓰기면 이 회차가 그린 저장본도 낡았을 수 있다. 다음 회차가 최신 저장본을 그리게
        # 캐시를 비운다. 이 회차는 본 version 을 올리지 않는다 — 다음 회차(제출 아님)가 최신을
        # 그리며 적는다.
        clear_global_process_rename_cache()
        if is_own_save(PROCESS_RENAME_SAVE_NAME, exc.expected, exc.stored, save_marks):
            # 같은 단추의 빠른 두 번 누름이다 — 첫 누름이 이미 저장했다(write_guard).
            queue_flash(PROCESS_RENAME_FLASH_KEY, PROCESS_RENAME_SAVED_MESSAGE)
        else:
            message = bootstrap_error_message(exc)
            note_profile_conflict(conflict_marks, PROCESS_RENAME_SAVE_NAME, message)
            queue_refusal(PROCESS_RENAME_SAVE_NAME, message)
        st.rerun()
    except BOOTSTRAP_ERRORS as exc:
        save_status.error(_save_error_message(exc))
    else:
        # 느린 둘째 누름이 이 알림을 다시 낸다(write_guard.held_notice — 위 「바뀐 것이 없습니다」
        # 갈래).
        note_notice(notices, PROCESS_RENAME_FLASH_KEY, PROCESS_RENAME_SAVED_MESSAGE)
        queue_flash(PROCESS_RENAME_FLASH_KEY, PROCESS_RENAME_SAVED_MESSAGE)
        st.rerun()


def _same_as_saved(
    profile: GlobalProcessRename, revised: pd.DataFrame, expected_version: int
) -> bool:
    """직접 편집 표(`revised` — 빈 줄을 뺀 것)가 이 회차가 그린 최신 저장본과 같은가.

    편집을 시작한 version 이 그 저장본이어야 한다 — 옛 화면의 저장은 견주지 않고 저장소의 버전
    대조에 맡긴다(남의 저장 뒤라면 거부). 저장본이 없으면(v0) 늘 다르다고 본다. 같음은 저장소가 쓸
    꼴(`prepare_process_rename_rules` — 1:1 위반이면 `ValueError`)끼리다.
    """
    if profile.version <= 0 or expected_version != profile.version:
        return False
    return prepare_process_rename_rules(revised).equals(prepare_process_rename_rules(profile.rules))


def _save_process_rename(
    repository: DuckDBScenarioRepository,
    rules: pd.DataFrame,
    *,
    source: str,
    expected_version: int | None = None,
    save_marks: dict[str, tuple[SeenToken, SeenToken]] | None = None,
) -> GlobalProcessRename:
    """검증 → 교체 저장 → 캐시 폐기 → 입장 화면 Summary 확인 비우기(그 표시명으로 그린다).

    1:1 위반은 반드시 파이썬 `ValueError` 로 먼저 낸다. DB 의 UNIQUE 는 마지막 방어선이고
    그 위반은 `duckdb.ConstraintException` 이라 화면 오류 문구로 바뀌지 않는다. 붙여넣기는
    「현재 전체 교체」를 확인받는 일이라 `expected_version` 없이 부른다(버전 대조는 직접 편집).

    직접 편집은 저장 전에 받아 둔 제 저장 표지(`save_marks`)를 넘긴다. 짝은 저장소에 쓴 **바로
    뒤**, 세션 칸을 건드리는 뒷정리(입장 화면 확인 비우기) **앞**에 적는다 — 뒷정리는 둘째 누름의
    회차에 끊길 수 있는 자리다(write_guard, 2026-10-26 E2E).
    """
    prepared = prepare_process_rename_rules(rules)
    saved = repository.replace_global_process_rename(
        prepared, source=source, expected_version=expected_version
    )
    if expected_version is not None and save_marks is not None:
        remember_own_save(PROCESS_RENAME_SAVE_NAME, expected_version, saved.version, save_marks)
    clear_global_process_rename_cache()
    forget_intro_summary_check()
    return saved
