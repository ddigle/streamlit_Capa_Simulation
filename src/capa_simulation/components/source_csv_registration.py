# Purpose: DB 등록 탭의 「CSV 파일」 길 — 원천 CSV 올림 칸 · 코드 목록 · 등록 칸 · 저장을 그린다.

"""DB 등록 탭 「CSV 파일」 길 — 원천 웹에서 받은 시나리오 CSV 로 시나리오를 등록한다.

탭 표 위 작업 줄 맨 앞 종류 단추(`bigdataquery_registration`)가 `CSV 파일` 이면 DB 목록 · 등록 폼
대신 이 길을 그린다. 차례는 작업 줄의 올림 칸 → (못 읽으면 입력 곁 거부 한 줄) → 값 줄 · 코드
목록(한 행 고르기 — 코드가 하나면 그 코드 첫 행을 고른 채) → 등록 칸 · 저장 단추 → 저장 결과 칸이다.
저장 길은 DB 등록과 같다 — 공급자(`io/source_csv.SourceCsvCoreDataProvider`) →
`fetch_registration_dataset` → 프리셋 → `save_bigdataquery_scenario` → 뒤
처리(`RegistrationSteps.finish` — 활성화 · 목록 따라감 · 성공 알림 · 저장 뒤 경고). CUSTOM 원천 표 ·
끄개 · 조회 SQL · 패키지 판정은 부르지 않는다 — 그것들이 막혀도 이 길은 열린다.

**이 파일은 DB 등록 화면 파일을 import 하지 않는다**(그 파일이 이 파일을 부른다). 두 길이 나눠 쓰는
저장 결과 칸 · 부대공정 칩 · 뒤 처리는 `RegistrationSteps` 로 받는다.

**메모리.** 회차 사이에 드는 것은 Streamlit 업로드 관리자가 쥔 올린 바이트 한 벌과
요약(`SourceCsvUpload` — 수 KB)뿐이다. 읽기는 파일 id 가 바뀐 회차에만 한 번 흘려 읽고(탭 본문은
숨어도 회차마다 돈다), 표는 저장 회차에만 짓는다. 저장하면 · 길을 바꾸면 · 칸을 비우면 관리자가 쥔
바이트를 지운다(`drop_uploaded_file` — Streamlit 1.63 관리자는 브라우저의 지우기 요청이나 세션
끝에만 지운다)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Final, cast

import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit.runtime.memory_uploaded_file_manager import MemoryUploadedFileManager
from streamlit.runtime.scriptrunner import get_script_run_ctx
from streamlit.runtime.uploaded_file_manager import UploadedFile

from capa_simulation.auth import grades
from capa_simulation.components.widget_generation import bump, widget_key
from capa_simulation.design import tokens
from capa_simulation.io.company_bigdataquery_adapter import is_valid_simulation_code
from capa_simulation.io.source_csv import (
    CHANGED_FILE_TEXT,
    SourceCsvCoreDataProvider,
    SourceCsvError,
    SourceCsvSummary,
    summarize_source_csv,
)
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import load_global_display_order
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_preset_state import capture_full_data_scenario_preset
from capa_simulation.scenario_registration import (
    BigDataQueryRegistration,
    load_active_extra_pack,
    save_bigdataquery_scenario,
)
from capa_simulation.services.bigdataquery_catalog_view import UNSAVABLE_REASON, view_token
from capa_simulation.services.core_data_pipeline import (
    RegistrationDataset,
    fetch_registration_dataset,
)
from capa_simulation.services.source_csv_view import (
    DEFAULT_REVISION_NAME,
    REGISTERED_AT_FIELD_ERROR,
    REGISTERED_AT_PATTERN,
    build_source_csv_display_frame,
    code_rows,
    default_pick,
    optional_registered_at,
    source_csv_note,
    source_csv_prefill,
    source_csv_value_line,
)
from capa_simulation.session_slot import SessionSlot

# 올림 칸 고유 상한(MB) — 서버 전체 상한(`config.toml` `maxUploadSize`)보다 낮게 둔다. 칸 안내
# 「50MB per file」 와 브라우저가 올리기 전에 막는 크기가 이 값이다(설비 CSV 칸과 같은 값 · 제
# 상수).
SOURCE_CSV_UPLOAD_LIMIT_MB: Final = 50
SOURCE_CSV_UPLOAD_LABEL: Final = "원천 CSV"
# 올림 칸 폭 — 작업 줄 한 줄 안에 종류 단추와 함께 선다(설계 규칙 UI-LAY-11).
SOURCE_CSV_UPLOAD_WIDTH_PX: Final = 360
SOURCE_CSV_SAVE_LABEL: Final = "CSV 파일로 시나리오 저장"

# 잠긴 저장 단추의 까닭 풍선(설계 규칙 UI-INP-07) — 앞선 까닭 하나다. 못 읽은 파일의 까닭 글은 올림
# 칸 아래 거부 한 줄이 말하므로 풍선은 그 자리를 가리키기만 한다(UI-TXT-07).
NO_FILE_HELP: Final = "원천 웹에서 받은 시나리오 CSV 를 올려야 저장할 수 있습니다."
UNREADABLE_HELP: Final = (
    "올린 파일을 읽지 못해 저장할 수 없습니다 — 까닭은 올림 칸 아래 줄이 적습니다."
)
NO_PICK_HELP: Final = "목록에서 등록할 시뮬레이션 코드를 골라야 저장할 수 있습니다."
SAME_NAME_TEXT: Final = "같은 이름의 시나리오가 이미 있습니다. 이름을 바꿔 저장하세요."

SOURCE_CSV_UPLOAD_KEY = "source_csv_upload"
# 올림 칸의 세대 — 저장하면 올려 새 칸(빈 칸)으로 선다.
SOURCE_CSV_UPLOAD_GENERATION_KEY = "source_csv_upload_generation"
SOURCE_CSV_STATE_KEY = "source_csv_state"
SOURCE_CSV_LIST_KEY_PREFIX = "source_csv_rows_"
SOURCE_CSV_FORM_KEY = "source_csv_registration_form"
# 등록 칸 글자 칸의 세대 — 새 파일 · 다른 코드를 고를 때마다 새 위젯으로 세워 고른 값을 채운다(폼 안
# 칸에 친 글자는 제출 전까지 브라우저만 들고 있다 — `bigdataquery_registration` 머리말).
SOURCE_CSV_FORM_GENERATION_KEY = "source_csv_form_generation"
SOURCE_CSV_FORM_CODE_KEY = "source_csv_form_simulation_code"
SOURCE_CSV_FORM_SOURCE_NAME_KEY = "source_csv_form_source_name"
SOURCE_CSV_FORM_SCENARIO_NAME_KEY = "source_csv_form_scenario_name"
SOURCE_CSV_FORM_REVISION_NAME_KEY = "source_csv_form_revision_name"
SOURCE_CSV_FORM_REGISTERED_AT_KEY = "source_csv_form_registered_at"
SOURCE_CSV_FORM_NOTE_KEY = "source_csv_form_note"
SOURCE_CSV_FORM_DEFAULTS: Final[dict[str, str]] = {
    SOURCE_CSV_FORM_CODE_KEY: "",
    SOURCE_CSV_FORM_SOURCE_NAME_KEY: "",
    SOURCE_CSV_FORM_SCENARIO_NAME_KEY: "",
    SOURCE_CSV_FORM_REVISION_NAME_KEY: DEFAULT_REVISION_NAME,
    SOURCE_CSV_FORM_REGISTERED_AT_KEY: "",
    SOURCE_CSV_FORM_NOTE_KEY: "",
}


@dataclass(frozen=True)
class SourceCsvUpload:
    """올린 파일 하나를 읽은 결과 — 파일 id 가 같으면 다시 읽지 않는다(설계 규칙 UI-PRF-01).

    읽혔으면 `summary`, 못 읽었으면 `refusal`(입력 곁 한 줄 글)이다. 바이트 · 표 · 해독한 글은 들지
    않는다. `picked` 는 목록에서 고른 행(목록 차례), `applied` 는 등록 칸을 채운 코드다 — 같은
    코드의 다른 PLAN 행을 골라도 칸을 다시 채우지 않는다(고친 글자를 덮지 않게)."""

    file_id: str
    file_name: str
    summary: SourceCsvSummary | None
    refusal: str | None
    picked: int | None = None
    applied: str | None = None


@dataclass(frozen=True)
class RegistrationSteps:
    """DB 등록 길과 나눠 쓰는 자리 · 처리 — DB 등록 화면 파일이 지어 넘긴다(고리 import 를 만들지
    않게).

    `begin` 은 저장을 누른 회차 맨 앞(앞 등록의 큰 충돌 상세를 버림), `result_slot` 은 저장 단추
    아래 늘 서 있는 결과 칸, `reveal` 은 그 칸이 화면 밖이면 본문을 옮기는 스크립트, `extra_chip` 은
    부대공정 판 칩, `finish` 는 저장한 등록의 뒤 처리다."""

    begin: Callable[[], None]
    result_slot: Callable[[], DeltaGenerator]
    reveal: Callable[[DeltaGenerator], None]
    extra_chip: Callable[[DuckDBScenarioRepository], None]
    finish: Callable[
        [DuckDBScenarioRepository, BigDataQueryRegistration, RegistrationDataset], None
    ]


STATE_SLOT: Final = SessionSlot(SOURCE_CSV_STATE_KEY, SourceCsvUpload)


def render_source_csv_route(
    repository: DuckDBScenarioRepository,
    database_path: str,
    *,
    toolbar: DeltaGenerator,
    registered_codes: frozenset[str],
    existing_names: frozenset[str],
    steps: RegistrationSteps,
) -> None:
    """「CSV 파일」 길 본문 — 작업 줄(`toolbar`)에 올림 칸을 세우고 그 아래 목록 · 등록 칸을
    그린다."""
    with toolbar:
        uploaded = st.file_uploader(
            SOURCE_CSV_UPLOAD_LABEL,
            type=["csv"],
            key=widget_key(SOURCE_CSV_UPLOAD_KEY, SOURCE_CSV_UPLOAD_GENERATION_KEY),
            max_upload_size=SOURCE_CSV_UPLOAD_LIMIT_MB,
            # 라벨 글은 접근성 이름으로 남는다 — 작업 줄 높이를 올림 칸에 맞춰 키우지 않게 접는다.
            label_visibility="collapsed",
            width=SOURCE_CSV_UPLOAD_WIDTH_PX,
        )
    state = _sync_upload(uploaded)
    if state is not None and state.refusal is not None:
        # 못 읽은 파일의 까닭 — 입력 곁 거부 한 줄이다(설계 규칙 UI-NTF-03). 다른 파일을 올리거나
        # 칸의 × 로 지우면 사라진다.
        st.error(state.refusal)
    if state is not None and state.summary is not None:
        state = _render_code_list(state, registered_codes)
    _render_form(
        repository,
        database_path,
        state=state,
        uploaded=uploaded,
        existing_names=existing_names,
        steps=steps,
    )


def forget_source_csv() -> None:
    """올린 원천 CSV 를 놓는다 — 업로드 관리자가 쥔 바이트를 지우고 요약 칸을 비운다.

    저장 뒤 · DB 조회 길로 바꾼 회차 · 올림 칸이 빈 회차(칸의 × · 다른 화면에 다녀옴)에 부른다. 놓을
    것이 없으면 아무것도 하지 않는다.
    """
    state = STATE_SLOT.peek()
    if state is None:
        return
    drop_uploaded_file(state.file_id)
    STATE_SLOT.clear()


def drop_uploaded_file(file_id: str) -> None:
    """업로드 관리자가 쥔 그 파일의 바이트를 지운다 — `st.chat_input` 이 쓰는 꼴과 같다.

    Streamlit 1.63 의 업로드 관리자는 브라우저가 지우기 요청을 보내거나 세션이 끝날 때만 파일을
    지워, 칸의 key 를 바꿔도 바이트가 세션 끝까지 남을 수 있다. 내부 API 라 관리자가 메모리 관리자일
    때만 부르고, 아니면 아무것도 하지 않는다(세션 끝에 빈다) — Streamlit 을 올리면 이 꼴을 다시 본다
    (AGENTS 3장 이 파일 줄)."""
    context = get_script_run_ctx()
    if context is None:
        return
    manager = context.uploaded_file_mgr
    if isinstance(manager, MemoryUploadedFileManager):
        manager.remove_file(session_id=context.session_id, file_id=file_id)


def _sync_upload(uploaded: UploadedFile | None) -> SourceCsvUpload | None:
    """올림 칸의 파일과 요약 칸을 맞춘다 — 파일 id 가 바뀐 회차에만 한 번 흘려 읽는다."""
    state = STATE_SLOT.peek()
    if uploaded is None:
        forget_source_csv()
        return None
    if state is not None and state.file_id == uploaded.file_id:
        return state
    if state is not None:
        drop_uploaded_file(state.file_id)
    try:
        summary = summarize_source_csv(uploaded, file_id=uploaded.file_id)
    except SourceCsvError as exc:
        fresh = SourceCsvUpload(uploaded.file_id, uploaded.name, None, bootstrap_error_message(exc))
    else:
        fresh = SourceCsvUpload(uploaded.file_id, uploaded.name, summary, None)
    # 새 파일이면 등록 칸을 새 위젯으로 세운다 — 앞 파일의 값 · 친 글자가 남지 않게.
    bump(SOURCE_CSV_FORM_GENERATION_KEY)
    if fresh.summary is not None:
        fresh = _apply_pick(fresh, default_pick(fresh.summary))
    STATE_SLOT.set(fresh)
    return fresh


def _apply_pick(state: SourceCsvUpload, row: int | None) -> SourceCsvUpload:
    """고른 행을 적고, 고른 코드가 바뀌었으면 등록 칸을 그 코드의 처음 값으로 채운다(새 세대).

    등록 칸 위젯을 만들기 **전에** 부른다 — 만든 위젯 key 에 같은 회차에 쓰면 Streamlit 이 예외를
    낸다(목록이 등록 칸보다 위에 그려지는 까닭).
    """
    summary = state.summary
    entries = () if summary is None else summary.codes
    code = entries[row].code if row is not None and 0 <= row < len(entries) else None
    picked = row if code is not None else None
    if code == state.applied:
        return replace(state, picked=picked)
    bump(SOURCE_CSV_FORM_GENERATION_KEY)
    if code is not None and summary is not None:
        prefill = source_csv_prefill(summary, code)
        for base, value in (
            (SOURCE_CSV_FORM_CODE_KEY, prefill.simulation_code),
            (SOURCE_CSV_FORM_SOURCE_NAME_KEY, prefill.source_name),
            (SOURCE_CSV_FORM_SCENARIO_NAME_KEY, prefill.scenario_name),
            (SOURCE_CSV_FORM_REVISION_NAME_KEY, prefill.revision_name),
            (SOURCE_CSV_FORM_REGISTERED_AT_KEY, prefill.registered_at),
            (SOURCE_CSV_FORM_NOTE_KEY, prefill.note),
        ):
            _field(base).set(value)
    return replace(state, picked=picked, applied=code)


def _render_code_list(state: SourceCsvUpload, registered_codes: frozenset[str]) -> SourceCsvUpload:
    """값 줄 · 코드 목록(DB 목록과 같은 꼴 — 한 행 고르기 · 같은 행 높이)과 행 고르기."""
    summary = state.summary
    assert summary is not None
    st.caption(source_csv_value_line(summary))
    selection_default: dict[str, Any] | None = None
    if state.picked is not None:
        selection_default = {"selection": {"rows": [state.picked], "columns": []}}
    event = st.dataframe(
        build_source_csv_display_frame(summary, registered_codes),
        # 파일 id 가 key 에 든다 — 다른 파일의 같은 자리 행이 골라진 채 남지 않는다.
        key=SOURCE_CSV_LIST_KEY_PREFIX + view_token(state.file_id),
        on_select="rerun",
        selection_mode="single-row",
        selection_default=cast(Any, selection_default),
        hide_index=True,
        row_height=tokens.CATALOG_LIST_ROW_HEIGHT_PX,
        width="stretch",
        placeholder="",
    )
    selected = _selected_row(event)
    if selected == state.picked:
        return state
    picked = _apply_pick(state, selected)
    STATE_SLOT.set(picked)
    return picked


def _selected_row(event: object) -> int | None:
    """선택 이벤트에서 첫 행 위치만 방어적으로 읽는다(DB 목록 `first_selected_row` 와 같은 판정)."""
    selection = event.get("selection") if isinstance(event, dict) else None
    rows = selection.get("rows") if isinstance(selection, dict) else None
    if not isinstance(rows, (list, tuple)) or not rows:
        return None
    first = rows[0]
    if isinstance(first, bool) or not isinstance(first, int):
        return None
    return int(first)


def _render_form(
    repository: DuckDBScenarioRepository,
    database_path: str,
    *,
    state: SourceCsvUpload | None,
    uploaded: UploadedFile | None,
    existing_names: frozenset[str],
    steps: RegistrationSteps,
) -> None:
    """등록 칸 · 저장 단추 · 저장 결과 칸 — DB 폼과 같은 칸에서 상세 조회 기간 하나만 뺀다.

    파일이 없거나 못 읽었거나 코드를 고르지 않았으면 단추를 잠그고 까닭 풍선을 단다(설계 규칙
    UI-INP-07 — 지금만 못 하는 조작). 시뮬레이션 코드 칸은 파일 값이라 잠근다.
    """
    for base, value in SOURCE_CSV_FORM_DEFAULTS.items():
        if not _field(base).exists():
            _field(base).set(value)
    if state is None:
        locked_help: str | None = NO_FILE_HELP
    elif state.summary is None:
        locked_help = UNREADABLE_HELP
    elif state.applied is None:
        locked_help = NO_PICK_HELP
    else:
        locked_help = None if is_valid_simulation_code(state.applied) else UNSAVABLE_REASON
    with st.form(SOURCE_CSV_FORM_KEY):
        st.text_input("시뮬레이션 코드", key=_key(SOURCE_CSV_FORM_CODE_KEY), disabled=True)
        st.text_input("원천 시뮬레이션명", key=_key(SOURCE_CSV_FORM_SOURCE_NAME_KEY))
        st.text_input("저장할 시나리오명", key=_key(SOURCE_CSV_FORM_SCENARIO_NAME_KEY))
        st.text_input("초기 리비전명", key=_key(SOURCE_CSV_FORM_REVISION_NAME_KEY))
        st.text_input(
            "원천 등록시점 (선택)",
            key=_key(SOURCE_CSV_FORM_REGISTERED_AT_KEY),
            placeholder="2026-08-29 14:30:00",
            # DB 폼 「원천 DB 등록시점 (선택)」 과 같은 검증이다 — 서버 판정은 마지막 방어선으로
            # 남긴다.
            validate=(REGISTERED_AT_PATTERN, REGISTERED_AT_FIELD_ERROR),
        )
        st.text_area("등록 메모", key=_key(SOURCE_CSV_FORM_NOTE_KEY), height=90)
        steps.extra_chip(repository)
        submitted = st.form_submit_button(
            SOURCE_CSV_SAVE_LABEL,
            icon=":material/upload_file:",
            type="primary",
            width="stretch",
            disabled=locked_help is not None,
            help=locked_help,
        )
    notice = steps.result_slot()
    if submitted:
        with notice:
            _save_source_csv_scenario(
                repository,
                database_path,
                state=state,
                uploaded=uploaded,
                existing_names=existing_names,
                steps=steps,
            )
        # 저장하면 다음 회차로 넘어가므로(`st.rerun`) 여기까지 오면 칸에 저장하지 못한 까닭이 섰다.
        steps.reveal(notice)


def _save_source_csv_scenario(
    repository: DuckDBScenarioRepository,
    database_path: str,
    *,
    state: SourceCsvUpload | None,
    uploaded: UploadedFile | None,
    existing_names: frozenset[str],
    steps: RegistrationSteps,
) -> None:
    """CSV 파일로 시나리오 하나를 저장한다 — DB 등록과 같은 저장 길 · 같은 뒤 처리.

    차례: 등급 → 같은 이름(파일을 읽기 전) → 빈 필수 칸(한 번에) → 등록시점 꼴 → 올린 파일 · 고른
    코드 → 공급자(파일 다시 흘려 읽기 · 고른 코드 행 · CUSTOM · 원천 보정) → 정규화 · 파생 ·
    부대공정 판 → 프리셋 → 저장 → 뒤 처리 → 올린 바이트 버림 · 올림 칸 새로 → 다음 회차. 저장하지
    못한 까닭은 결과 칸에 선다."""
    # DB 등록과 같은 동작이다 — 누른 순간 실제 등급으로 다시 본다(실무자부터). 거절은 화면 본문의
    # 받는 자리(`page_failure_card.run_core_page`)가 알림창 · Alarm 으로 낸다.
    grades.require("scenario.db_register")
    steps.begin()
    scenario_name = _field(SOURCE_CSV_FORM_SCENARIO_NAME_KEY).get().strip()
    if scenario_name in existing_names:
        st.error(SAME_NAME_TEXT)
        return
    source_name = _field(SOURCE_CSV_FORM_SOURCE_NAME_KEY).get()
    revision_name = _field(SOURCE_CSV_FORM_REVISION_NAME_KEY).get() or DEFAULT_REVISION_NAME
    note = _field(SOURCE_CSV_FORM_NOTE_KEY).get()
    missing = [
        label
        for label, value in (
            ("원천 시뮬레이션명", source_name),
            ("저장할 시나리오명", scenario_name),
        )
        if not value.strip()
    ]
    if missing:
        st.error(f"필수 칸이 비어 있습니다: {', '.join(missing)}")
        return
    try:
        registered_at = optional_registered_at(_field(SOURCE_CSV_FORM_REGISTERED_AT_KEY).get())
    except ValueError as exc:
        st.error(bootstrap_error_message(exc))
        return
    if state is None or state.summary is None or state.applied is None or uploaded is None:
        st.error(CHANGED_FILE_TEXT)
        return
    summary = state.summary
    code = state.applied
    held = uploaded
    try:
        display_order = load_global_display_order(database_path).rules
        provider = SourceCsvCoreDataProvider(
            lambda: held,
            summary,
            simulation_name=source_name,
            source_registered_at=registered_at,
        )
        with st.spinner(f"CSV 파일을 읽고 검증하는 중입니다 — {code_rows(summary, code):,}행..."):
            registration_data = fetch_registration_dataset(
                provider, code, display_order, load_active_extra_pack(repository)
            )
            prepared = registration_data.prepared
            preset = capture_full_data_scenario_preset(prepared.reference_tables)
            registration = save_bigdataquery_scenario(
                repository,
                prepared,
                preset,
                scenario_name=scenario_name,
                revision_name=revision_name,
                note=source_csv_note(note, state.file_name, provider.custom_kinds or 0),
                extra=registration_data.extra,
            )
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return
    steps.finish(repository, registration, registration_data)
    # 저장했으면 올린 파일을 놓는다 — 관리자가 쥔 바이트를 지우고 올림 칸을 새 칸(빈 칸)으로 세운다.
    forget_source_csv()
    bump(SOURCE_CSV_UPLOAD_GENERATION_KEY)
    st.rerun()


def _key(base: str) -> str:
    """등록 칸 글자 칸의 지금 세대 key."""
    return widget_key(base, SOURCE_CSV_FORM_GENERATION_KEY)


def _field(base: str) -> SessionSlot[str]:
    """등록 칸 글자 칸 하나의 세션 칸(지금 세대) — 비었으면 빈 글자."""
    return SessionSlot(_key(base), str, lambda: "")
