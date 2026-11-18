# Purpose: Admin Area 「부대공정」 탭 — 판 상태 줄 · 양식 내려받기 · 끄기 / 다시 켜기 · 이 리비전
# 값을 새 판으로 · S3 에 다시 쓰기 · 판 이력과 받은 판의 거절 표 · 미리보기 시험 계산 · 적용을
# 그린다.

"""Admin 「부대공정」(설계 3-4 · A7 — 1단계).

**보이는 것.** 상태 줄 값 한 줄(「부대공정 · 판 3 · 공정 2 · 적용 11-13 09:12」 — 끈 동안 「꺼짐 ·
마지막 판 3」, 판이 없으면 「판 없음」. 원천을 본 적이 있으면 끝에 「<자리> <낱말>(hh:mm 에 봄)」),
단추 줄(가져오기 · 양식 내려받기 · 끄기 / 다시 켜기), 받은 판이 있으면 그 거절 표 또는 값 줄(지금
판과의 차이 · 앞 판 값으로 되돌리는 칸 · 측정률 칸 — 받는 때 센다)과 미리보기 · 「적용」, 맨 아래 판
이력 표. 설명 글은 세우지 않는다 — 단추 · 칸의 뜻은 풍선, 탭의 쓰임은 Guide 다(설계 규칙 UI-TXT-01 ·
UI-TXT-02). 앞 판 값으로 되돌리는 칸이 있으면(G12 — 옛 사본에서 판 번호만 올린 판) 「적용」 앞 확인
칸을 채워야 「적용」 이 열린다(UI-NTF-09).

**가져오기 단추는 원천이 꽂혀 있을 때만 선다**(`extra_process_intake.installed_source`). 1단계는
원천을 꽂지 않는다 — S3 Drive 가져오기는 사내 확인 부대 5 · 6 의 답 뒤에 붙인다(설계 9-4).

**쓰는 단추**(가져오기 · 적용 · 끄기 / 다시 켜기)는 C-DEP(`managed` + S3 접속 정보)의 실제
개발자에게만 열린다(`write_lock_reason`) — 그 밖에는 잠그고 풍선에 까닭을 단다(UI-INP-07). 누른
회차에도 판정을 한 번 더 하고, 저장소 쓰기는 `admin.area` 벽 뒤다. 쓰기는 화면이 본 판 이력 마지막
차례와 대조한다 — 겹친 둘째 누름 · 남의 먼저 쓰기는 쓰지 않는다(UI-STA-05). 쓰기는 본문에서
한다(콜백 아님).

**미리보기 시험 계산**은 「시험 계산」 을 누른 회차에만 돈다 — 지금 활성 시나리오의 표에 받은 판을
합쳐(그 시나리오에 이미 든 부대공정은 먼저 걷고) 공정마다 합침 · 뺌, 월별 소요대수 · 가용 · 확보율,
부하 붙은 · 0 경로 수를 보인다. 결과는 (판 sha, 활성 리비전 content_token)마다 세션에 둔다 —
회차마다 다시 돌리지 않는다. 시나리오를 못 읽으면 단추 자리에 「데이터 Error」 마크다(UI-NTF-08).

**「이 리비전 값을 새 판으로」**(2단계 — 설계 3-5 · A15)는 올라와 있는 **저장 리비전**(사이드바의
활성 시나리오 · 리비전 — 저장하지 않은 편집은 들어가지 않는다, G1)의 부대공정 값(03 · 04 · 05)을
활성 판 위에 겹쳐 다음 판(P + 1)을 거꾸로
만들고(`services/extra_process_revision.pack_from_revision`) 받은 판과 같은 자리에 둔다 — 같은 거절
표 · 값 줄 · 시험 계산을 지나고, 값 줄에 옮기지 못한 공정 · 경로가 판과 다른 공정 수가 더 붙는다.
「새 판 적용」 은 DB 에 새 판(갈래 「새 판」)을 먼저 넣고, 내보내기 자리가 꽂혀
있으면(`extra_process_intake.installed_sink` — 지금 판은 시험만 꽂는다) 그다음 S3 Drive 파일을
덮는다(`write_back` — 적용하지 않은 사람 파일이면 덮지 않음). 쓰지 못한 동안은 상태 알림 `EP-05` 와
단추 「S3 에 다시 쓰기」 가 선다. 누를 수 없는 까닭(꺼짐 · 판 없음 · 다른 판 · 섞인 판 · 연도
Shift · 부대공정 없음 — G4)은 풍선이다.

**닫힌 탭은 그리지 않는다**(`app_pages/admin_area.py`) — 이 탭의 위젯은 단추 · 내려받기 · 확인
칸뿐이라 버릴 값이 없고, 닫힌 탭이 회차마다 판 이력을 읽지 않게 한다. 세션 칸은 `SessionSlot`
창구다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components import sso_identity
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.state_alerts import tab_name
from capa_simulation.components.table_toolbar import render_zip_download, toolbar_clearance
from capa_simulation.extra_process_intake import (
    NEW_FILE_WORD,
    PackPreview,
    RevisionOrigin,
    SourceFailure,
    SourceFetch,
    StagedPack,
    WriteOutcome,
    failure_reason,
    head_word,
    installed_sink,
    installed_source,
    needs_write,
    pending_write,
    preview_pack,
    previous_content,
    production_place,
    stage_pack,
    write_back,
)
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.korea_time import KST
from capa_simulation.navigation import ADMIN_AREA_TABS
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.extra_process_store import ExtraProcessMoved
from capa_simulation.persistence.models import (
    EXTRA_KIND_REVISION,
    EXTRA_REVISION_PLACE,
    EXTRA_WRITE_WRITTEN,
    ExtraProcessProvenance,
    ExtraProcessS3Write,
    ExtraProcessState,
    ExtraProcessVersion,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import (
    active_persisted_revision_id,
    active_persisted_scenario_id,
)
from capa_simulation.scenario_state import ensure_active_scenario
from capa_simulation.services.extra_process_merge import (
    OUTCOME_DROPPED,
    OUTCOME_GRADUATED,
    OUTCOME_MERGED,
    ExtraPackVersion,
    split_previous,
)
from capa_simulation.services.extra_process_pack import (
    JUDGE_APPLY,
    JUDGE_RESUME,
    JUDGE_UNCHANGED,
    ExtraProcessPack,
    PackChanges,
    PackJudgement,
    pack_changes,
    pack_to_zip,
    read_pack_zip,
    template_zip,
)
from capa_simulation.services.extra_process_revision import (
    merged_processes,
    pack_from_revision,
    revision_refusal,
)
from capa_simulation.services.korean_particle import (
    with_direction_particle,
    with_object_particle,
    with_subject_particle,
)
from capa_simulation.session_slot import SessionSlot

TAB_LABEL: Final = ADMIN_AREA_TABS[3]
STAGED_KEY: Final = "admin_extra_process_staged"
PREVIEW_KEY: Final = "admin_extra_process_preview"
SEEN_KEY: Final = "admin_extra_process_seen"
TEMPLATE_KEY: Final = "admin_extra_process_template"
FLASH_KEY: Final = "admin_extra_process_flash"
IMPORT_BUTTON_KEY: Final = "admin_extra_process_import"
TOGGLE_BUTTON_KEY: Final = "admin_extra_process_toggle"
DOWNLOAD_BUTTON_KEY: Final = "admin_extra_process_download"
PREVIEW_BUTTON_KEY: Final = "admin_extra_process_preview_run"
APPLY_BUTTON_KEY: Final = "admin_extra_process_apply"
DISCARD_BUTTON_KEY: Final = "admin_extra_process_discard"
APPLY_CONFIRM_KEY: Final = "admin_extra_process_apply_confirm"
REVISION_BUTTON_KEY: Final = "admin_extra_process_from_revision"
REWRITE_BUTTON_KEY: Final = "admin_extra_process_rewrite"

STATUS_HEAD: Final = "부대공정"
DOWNLOAD_LABEL: Final = "양식 내려받기"
OFF_LABEL: Final = "끄기"
RESUME_LABEL: Final = "다시 켜기"
PREVIEW_LABEL: Final = "시험 계산"
APPLY_LABEL: Final = "적용"
DISCARD_LABEL: Final = "치우기"
REVISION_LABEL: Final = "이 리비전 값을 새 판으로"
REVISION_APPLY_LABEL: Final = "새 판 적용"
REWRITE_LABEL: Final = "S3 에 다시 쓰기"
TEMPLATE_FILE: Final = "extra_process_v{version}.zip"
BLANK_TEMPLATE_FILE: Final = "extra_process_template.zip"
# 잠긴 쓰는 단추의 풍선(UI-INP-07) — 무엇이 막는지 한 줄.
NOT_PRODUCTION_REASON: Final = "운영 서버(C-DEP)에서만 바꿀 수 있습니다"
NOTHING_TO_TOGGLE: Final = "적용한 판이 없습니다"
# 누르기 전에 알아야 할 결과(UI-NTF-09).
OFF_HELP: Final = (
    "다음 등록부터 부대공정을 빼는 비상 단추입니다 — 이미 저장된 리비전은 그대로이고, 같은 자리의 "
    "「다시 켜기」 로 마지막 판이 파일 없이 돌아옵니다."
)
RESUME_HELP: Final = "마지막으로 적용한 판을 파일 없이 다시 켭니다 — 다음 등록부터 다시 들어갑니다."
DOWNLOAD_HELP: Final = (
    "마지막으로 적용한 판(끈 동안에도)을 양식 ZIP 으로 받습니다 — 판이 없으면 빈 양식입니다. 고친 "
    "뒤 판 번호를 1 올려 놓습니다."
)
APPLY_HELP: Final = (
    "이 판을 활성 판으로 둡니다 — 다음 BDQ 등록 · 자동 갱신 · 부대공정 얹기부터 들어가고, "
    "이미 저장된 리비전은 그대로입니다."
)
PREVIEW_HELP: Final = "지금 올라와 있는 시나리오에 이 판을 합쳐 봅니다 — 저장하지 않습니다."
REVISION_HELP: Final = (
    "올라와 있는 저장 리비전에서 고친 부대공정 값(생산성 · 설비 · 효율)으로 다음 판을 만들어 "
    "봅니다 — 「새 판 적용」 을 눌러야 바뀝니다. 저장하지 않은 편집 · 바꾼 경로(STEP)는 들어가지 "
    "않습니다."
)
REVISION_APPLY_HELP: Final = (
    "이 판을 활성 판으로 둡니다 — 다음 BDQ 등록 · 자동 갱신 · 부대공정 얹기부터 들어가고, S3 "
    "Drive 의 파일도 덮을 수 있으면 이 판으로 바꿉니다."
)
REWRITE_HELP: Final = (
    "활성 판을 S3 Drive 의 current.zip 에 다시 씁니다 — 적용하지 않은 파일이 놓여 있으면 덮지 "
    "않습니다."
)
NO_REVISION_REASON: Final = "올라와 있는 저장 리비전이 없습니다"
UNCHANGED_REVISION: Final = "바뀐 것 없음 — 이 리비전의 부대공정 값이 활성 판과 같습니다"
OUTCOME_LABELS: Final = {
    OUTCOME_MERGED: "합침",
    OUTCOME_DROPPED: "뺌",
    OUTCOME_GRADUATED: "BDQ 에 생김",
}
HISTORY_COLUMNS: Final = (
    "판",
    "갈래",
    "적용 시각",
    "적용한 사람",
    "sha",
    "공정 수",
    "행 수",
    "바탕",
    "S3 쓰기",
)
# 앞 판 값으로 되돌리는 칸이 있는 판의 「적용」 앞 확인 칸(UI-NTF-09 — 누르기 전에 알아야 할 결과).
REVERT_CONFIRM_LABEL: Final = "앞 판 값으로 되돌리는 칸 {n}개를 확인했습니다"
REVERT_CONFIRM_HELP: Final = (
    "옛 사본에서 판 번호만 올린 판이면 지금 판에서 고친 값이 앞 판 값으로 돌아갑니다"
)
UNCONFIRMED_REASON: Final = "앞 판 값으로 되돌리는 칸을 확인하면 누를 수 있습니다"


@dataclass(frozen=True)
class SeenSource:
    """마지막으로 원천을 본 결과 — 상태 줄 끝 낱말과 본 시각."""

    place: str
    word: str
    seen_at: datetime


# 세션 칸(AGENTS 5장 42 — 창구로만). 받은 판 · 원천을 본 결과는 「있거나 없음」, 메모 둘은 튜플.
STAGED: Final = SessionSlot(STAGED_KEY, StagedPack)
SEEN: Final = SessionSlot(SEEN_KEY, SeenSource)
# (판 sha, 활성 리비전 content_token) → 미리보기.
PREVIEW: Final = SessionSlot(PREVIEW_KEY, tuple, tuple)
# (판 sha, 양식 ZIP 바이트, 파일 이름).
TEMPLATE: Final = SessionSlot(TEMPLATE_KEY, tuple, tuple)
# 마지막으로 가져온 파일의 (ETag, 상태 줄 낱말) — S3 쓰기가 덮지 않은 파일이 그것이면 그 낱말을
# 잇는다.
FETCHED_KEY: Final = "admin_extra_process_fetched"
FETCHED: Final = SessionSlot(FETCHED_KEY, tuple, tuple)
# 새 파일 감지(`EP-02`) HEAD 를 마지막으로 본 (시각, 낱말) — 회차마다 S3 를 묶지 않게 띄워 본다.
HEAD_SEEN_KEY: Final = "admin_extra_process_head_seen"
HEAD_SEEN: Final = SessionSlot(HEAD_SEEN_KEY, tuple, tuple)
HEAD_INTERVAL: Final = timedelta(minutes=5)


def write_lock_reason() -> str | None:
    """쓰는 단추를 잠그는 까닭 — 열려 있으면 None. 화면과 누른 회차가 함께 부른다."""
    from capa_simulation.auth import grades

    if not production_place():
        return NOT_PRODUCTION_REASON
    if not sso_identity.viewer_is_developer():
        return grades.refusal_text("admin.area")
    return None


def status_line(state: ExtraProcessState, seen: SeenSource | None = None) -> str:
    """상태 줄 값 한 줄 — 값만 싣고 공정 이름 · 생산성은 싣지 않는다(리뷰 압축본에 옮길 꼴)."""
    active = state.active
    latest = state.latest_content
    if active is not None:
        parts = [f"판 {active.version_no}", f"공정 {active.process_count or 0}"]
        parts.append(f"적용 {active.created_at:%m-%d %H:%M}")
    elif state.off and latest is not None:
        parts = ["꺼짐", f"마지막 판 {latest.version_no}"]
    else:
        parts = ["판 없음"]
    if seen is not None:
        parts.append(f"{seen.place} {seen.word}({seen.seen_at:%H:%M} 에 봄)")
    return " · ".join([STATUS_HEAD, *parts])


def render_extra_process_admin(
    repository: DuckDBScenarioRepository, *, alert_tab: str | None
) -> None:
    """탭 본문. `alert_tab` 은 이 탭 이름(열린 탭)이고 None 이면 닫힌 탭이다 — 닫힌 탭은 위젯만
    세우고 상태 알림 · 시험 계산 · 이력 표를 건너뛴다(`state_alerts.open_tab_name`)."""
    opened = alert_tab is not None
    render_flash(FLASH_KEY)
    if alert_tab is not None:
        _report_official_outcomes(repository, alert_tab)
    try:
        state = repository.load_extra_process_state()
    except BOOTSTRAP_ERRORS as exc:
        if alert_tab is not None:
            _report_remote_state(None, alert_tab)
        render_data_error(
            bootstrap_error_message(exc),
            code="AD-07",
            tab=tab_name(TAB_LABEL),
            text="부대공정 판을 읽지 못했습니다",
        )
        return
    lock = write_lock_reason()
    if alert_tab is not None:
        _report_remote_state(state if lock is None else None, alert_tab)
    st.caption(status_line(state, SEEN.peek()))
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        source = installed_source()
        if source is not None and st.button(
            source.label,
            key=IMPORT_BUTTON_KEY,
            icon=":material/cloud_download:",
            disabled=lock is not None,
            help=lock,
        ):
            _import(repository)
        _render_revision_button(repository, state, lock)
        _render_rewrite(repository, state, lock)
        _render_download(repository, state)
        _render_toggle(repository, state, lock)
    staged = STAGED.peek()
    if staged is not None:
        _render_staged(repository, state, staged, lock, opened=opened)
    if opened:
        _render_history(repository, state)


def _report_official_outcomes(repository: DuckDBScenarioRepository, tab: str) -> None:
    """최신 공식버전 데이터셋에서 뺀 · BDQ 에 생겨 건너뛴 부대공정 — 상태 알림 `EP-03` · `EP-04`.

    판정은 출처 표(데이터셋 단위)라 자동 갱신(화면 없음)이 뺀 것도 잡는다. 조건이 없어도 늘 두 번
    부른다(해소 — 이벤트 칸 자리 수가 갈래와 상관없이 같다). 이름은 알림 전문에만 싣는다.
    """
    release_no: int | None = None
    records: tuple[ExtraProcessProvenance, ...] = ()
    try:
        release = repository.latest_official_release()
        if release is not None:
            release_no = release.release_no
            records = repository.load_scenario_extra_process(release.scenario_id)
    except BOOTSTRAP_ERRORS:
        records = ()
    scope = {"official": release_no}
    for code, outcome, head, tail in (
        (
            "EP-03",
            OUTCOME_DROPPED,
            "뺀 부대공정",
            "판을 고쳐 다시 놓거나 부대공정 얹기로 다시 맞추세요",
        ),
        (
            "EP-04",
            OUTCOME_GRADUATED,
            "BDQ 에 같은 이름이 생겨 건너뛴 부대공정",
            "판에서 그 공정을 지워 다시 놓으세요",
        ),
    ):
        picked = [item for item in records if item.outcome == outcome]
        names = sorted({item.process_name for item in picked})
        alerts.state(
            code,
            scope=scope,
            content=names or None,
            active=bool(names),
            text=f"공식 v{release_no} 에서 {head} {len(names)}개",
            full=(
                f"최신 공식버전(v{release_no})에서 {head} {len(names)}개 — "
                + "; ".join(
                    f"{item.process_name} {item.rule or ''} {item.reason or ''}".strip()
                    for item in picked
                )
                + f". {tail}."
            ),
            tab=tab,
        )


def _render_download(repository: DuckDBScenarioRepository, state: ExtraProcessState) -> None:
    latest = state.latest_content
    data, file_name = _template_bytes(repository, latest)
    render_zip_download(
        data=data,
        file_name=file_name,
        key=DOWNLOAD_BUTTON_KEY,
        label=DOWNLOAD_LABEL,
        tooltip=DOWNLOAD_HELP,
    )


def _template_bytes(
    repository: DuckDBScenarioRepository, latest: ExtraProcessVersion | None
) -> tuple[bytes, str]:
    """마지막 내용 판의 양식 ZIP(끈 동안에도 P) — 없으면 빈 양식. 판 sha 마다 세션에 한 번
    만든다."""
    if latest is None or latest.sha256 is None:
        return template_zip(), BLANK_TEMPLATE_FILE
    memo = TEMPLATE.get()
    if len(memo) == 3 and memo[0] == latest.sha256:
        return bytes(memo[1]), str(memo[2])
    reading = read_pack_zip(repository.load_extra_process_content(latest.sha256))
    if reading.pack is None:
        return template_zip(), BLANK_TEMPLATE_FILE
    result = (pack_to_zip(reading.pack), TEMPLATE_FILE.format(version=latest.version_no))
    TEMPLATE.set((latest.sha256, *result))
    return result


def _render_toggle(
    repository: DuckDBScenarioRepository, state: ExtraProcessState, lock: str | None
) -> None:
    resume = state.off and state.latest_content is not None
    nothing = state.active is None and not resume
    pressed = st.button(
        RESUME_LABEL if resume else OFF_LABEL,
        key=TOGGLE_BUTTON_KEY,
        icon=":material/play_arrow:" if resume else ":material/power_settings_new:",
        disabled=lock is not None or nothing,
        help=lock or (NOTHING_TO_TOGGLE if nothing else RESUME_HELP if resume else OFF_HELP),
    )
    if not pressed:
        return
    again = write_lock_reason()
    if again is not None:
        queue_flash(FLASH_KEY, again, kind="error", icon=":material/block:")
        st.rerun()
    who = _who()
    try:
        if resume:
            after = repository.resume_extra_process(expected_seq=state.last_seq, applied_by=who)
            active = after.active
            message = f"부대공정 판 {None if active is None else active.version_no} 다시 켬"
        else:
            repository.turn_off_extra_process(expected_seq=state.last_seq, applied_by=who)
            message = "부대공정 판 끔 — 다음 등록부터 빠집니다"
    except (ExtraProcessMoved, ValueError) as exc:
        queue_flash(FLASH_KEY, bootstrap_error_message(exc), kind="error", icon=":material/error:")
    else:
        queue_flash(FLASH_KEY, message)
    st.rerun()


# 받은 파일을 판정하다 난 예외(검사가 못 거른 꼴 · 지운 판 내용) — 원천 실패와 같은 길로 알린다.
_STAGE_ERRORS: Final = (*BOOTSTRAP_ERRORS, NotImplementedError)


def _stage_error_word(exc: BaseException) -> str:
    return f"판을 읽지 못함 · {type(exc).__name__}"


def _import(repository: DuckDBScenarioRepository) -> None:
    """원천에서 받아 검사한다 — 바뀐 것 없으면 알리기만, 아니면 받은 판을 세션에 둔다."""
    source = installed_source()
    if source is None or write_lock_reason() is not None:
        return
    now = datetime.now(KST)
    PREVIEW.clear()
    try:
        with st.spinner("부대공정 판을 받는 중입니다..."):
            fetched = source.fetch()
        state = repository.load_extra_process_state()
        staged = stage_pack(
            state,
            fetched,
            now=now,
            current=_content(repository, state.active),
            before=_content(repository, previous_content(state)),
        )
    except (SourceFailure, *_STAGE_ERRORS) as exc:
        reason = exc.reason if isinstance(exc, SourceFailure) else _stage_error_word(exc)
        SEEN.set(SeenSource(source.place, f"읽지 못함({reason})", now))
        queue_flash(
            FLASH_KEY,
            f"부대공정 판을 가져오지 못했습니다 — {reason}. 지난 판으로 계속합니다.",
            kind="error",
            icon=":material/error:",
            alert="EP-01",
            popup_only=True,
        )
        st.rerun()
    SEEN.set(SeenSource(source.place, _staged_word(staged), now))
    if fetched.etag:
        FETCHED.set((fetched.etag, _staged_word(staged)))
    # 새 파일 감지 메모를 비운다 — 다음 회차가 HEAD 를 다시 보아 방금 가져온 파일을 「새 파일」 로
    # 잇지 않는다(가져온 파일은 그 낱말, 적용한 파일은 「같음」 — `head_word`).
    HEAD_SEEN.clear()
    if staged.judgement is not None and staged.judgement.verdict == JUDGE_UNCHANGED:
        STAGED.clear()
        queue_flash(FLASH_KEY, "바뀐 것 없음 — 활성 판과 같은 파일입니다", kind="info")
    else:
        STAGED.set(staged)
    st.rerun()


def _staged_word(staged: StagedPack) -> str:
    """상태 줄 끝 원천 낱말(설계 3-4 의 1번) — 같음 · 적용 전 판 n · 거절."""
    if staged.judgement is None or not staged.reading.accepted:
        return "거절"
    if staged.judgement.verdict == JUDGE_UNCHANGED:
        return "같음"
    if staged.judgement.applicable:
        return f"적용 전 판 {staged.reading.version_no}"
    return "거절"


def _render_staged(
    repository: DuckDBScenarioRepository,
    state: ExtraProcessState,
    staged: StagedPack,
    lock: str | None,
    *,
    opened: bool,
) -> None:
    reading = staged.reading
    origin = staged.revision
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            if origin is None:
                st.markdown(f"**받은 판** · {_staged_word(staged)} · sha {reading.sha256[:8]}")
            else:
                st.markdown(
                    f"**리비전에서 만든 판** · {literal_markdown(origin.label)} · 새 판 "
                    f"{reading.version_no} · sha {reading.sha256[:8]}"
                )
            if st.button(DISCARD_LABEL, key=DISCARD_BUTTON_KEY, type="tertiary"):
                STAGED.clear()
                PREVIEW.clear()
                st.rerun()
        if not reading.accepted or staged.judgement is None:
            toolbar_clearance()
            st.dataframe(_problem_frame(staged), hide_index=True, width="stretch", placeholder="")
            return
        if not staged.judgement.applicable:
            st.error(staged.judgement.reason, icon=":material/block:")
            return
        st.caption(
            " · ".join(
                [*_changes_parts(staged.changes), reading.ratio.text(), *_origin_parts(origin)]
            )
        )
        if origin is not None and origin.kept:
            st.dataframe(
                pd.DataFrame(
                    [{"공정": item.process, "까닭": item.reason} for item in origin.kept],
                    columns=["공정", "까닭"],
                ),
                hide_index=True,
                width="stretch",
                placeholder="",
            )
        preview = _preview(repository, state, staged, run=opened)
        if preview is not None:
            _render_preview(preview)
        reverted = 0 if staged.changes is None else staged.changes.reverted_cells
        confirmed = reverted == 0 or st.checkbox(
            REVERT_CONFIRM_LABEL.format(n=f"{reverted:,}"),
            key=APPLY_CONFIRM_KEY,
            help=REVERT_CONFIRM_HELP,
        )
        if st.button(
            APPLY_LABEL if origin is None else REVISION_APPLY_LABEL,
            key=APPLY_BUTTON_KEY,
            type="primary",
            icon=":material/check:",
            disabled=lock is not None or not confirmed,
            help=lock
            or (
                (APPLY_HELP if origin is None else REVISION_APPLY_HELP)
                if confirmed
                else UNCONFIRMED_REASON
            ),
        ):
            _apply(repository, staged)


def _origin_parts(origin: RevisionOrigin | None) -> list[str]:
    """리비전에서 만든 판의 값 줄 뒤 조각 — 옮긴 · 옮기지 못한 공정 · 경로가 판과 다른 공정 수."""
    if origin is None:
        return []
    return [
        f"옮긴 공정 {len(origin.moved)}",
        f"옮기지 못한 공정 {len(origin.kept)}",
        f"경로가 판과 다름 {len(origin.route_differs)}",
    ]


def _changes_parts(changes: PackChanges | None) -> list[str]:
    """값 줄 앞 조각 — 지금 판과의 차이 · 앞 판 값으로 되돌리는 칸(받은 판이 읽혔을 때만)."""
    if changes is None:
        return []
    return [
        f"더한 공정 {len(changes.added)}",
        f"뺀 공정 {len(changes.removed)}",
        f"바뀐 칸 {changes.changed_cells}",
        f"앞 판 값으로 되돌리는 칸 {changes.reverted_cells}",
    ]


def _preview(
    repository: DuckDBScenarioRepository,
    state: ExtraProcessState,
    staged: StagedPack,
    *,
    run: bool,
) -> PackPreview | None:
    """시험 계산 — 단추를 누른 회차에만 돌리고 (sha, content_token)마다 세션에 둔다."""
    pack = staged.reading.pack
    if pack is None:
        return None
    try:
        tables = get_effective_reference_tables()
        active = ensure_active_scenario(tables, get_effective_reference_version())
    except BOOTSTRAP_ERRORS as exc:
        # 시험 계산 단추가 설 자리 — 까닭 없이 사라지지 않게 마크로 둔다(UI-NTF-08).
        render_data_error(
            bootstrap_error_message(exc),
            code="AD-07",
            tab=tab_name(TAB_LABEL),
            text="시험 계산에 쓸 시나리오를 읽지 못했습니다",
        )
        return None
    memo_key = (staged.reading.sha256, str(active["content_token"]))
    memo = PREVIEW.get()
    if len(memo) == 2 and memo[0] == memo_key and isinstance(memo[1], PackPreview):
        return memo[1]
    if not run or not st.button(PREVIEW_LABEL, key=PREVIEW_BUTTON_KEY, help=PREVIEW_HELP):
        return None
    try:
        with st.spinner("시험 계산 중입니다..."):
            preview = _compute_preview(repository, state, staged, tables)
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc), icon=":material/error:")
        return None
    PREVIEW.set((memo_key, preview))
    return preview


def _compute_preview(
    repository: DuckDBScenarioRepository,
    state: ExtraProcessState,
    staged: StagedPack,
    tables: Mapping[str, pd.DataFrame],
) -> PackPreview:
    pack = staged.reading.pack
    assert pack is not None
    scenario_id = active_persisted_scenario_id()
    previous = (
        ()
        if scenario_id is None
        else split_previous(repository.load_scenario_extra_process(scenario_id)).stripped
    )
    if staged.changes is not None:
        return preview_pack(tables, previous, pack, seq=state.last_seq + 1, changes=staged.changes)
    current = _content(repository, state.active)
    before = _content(repository, previous_content(state))
    return preview_pack(
        tables, previous, pack, seq=state.last_seq + 1, current=current, before=before
    )


def _content(
    repository: DuckDBScenarioRepository, version: ExtraProcessVersion | None
) -> ExtraProcessPack | None:
    if version is None or version.sha256 is None:
        return None
    return read_pack_zip(repository.load_extra_process_content(version.sha256)).pack


def _render_preview(preview: PackPreview) -> None:
    st.caption(preview.report.counts_text())
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "공정": item.process,
                    "결과": OUTCOME_LABELS.get(item.outcome, item.outcome),
                    "규칙": item.rule or "",
                    "까닭": item.reason,
                    "부하 붙은 경로": preview.lines.get(item.process, (0, 0))[0],
                    "부하 0 경로": preview.lines.get(item.process, (0, 0))[1],
                    "맞물리지 않은 경로 줄": item.zero_lines,
                    "이어받은 Buffer 밖 줄": item.inherited_uncounted,
                    "이어받은 대당 Capa 결손 줄": preview.capacity_gaps.get(item.process, 0),
                }
                for item in preview.report.outcomes
            ]
        ),
        hide_index=True,
        width="stretch",
        placeholder="",
    )
    if not preview.rates.empty:
        # 확보율은 비율 값이다 — 다른 화면처럼 %(`percent`)로 보인다.
        st.dataframe(
            preview.rates,
            hide_index=True,
            width="stretch",
            placeholder="",
            column_config={"확보율": st.column_config.NumberColumn(format="percent")},
        )


def _apply(repository: DuckDBScenarioRepository, staged: StagedPack) -> None:
    lock = write_lock_reason()
    if lock is not None:
        queue_flash(FLASH_KEY, lock, kind="error", icon=":material/block:")
        st.rerun()
    pack = staged.reading.pack
    judgement = staged.judgement
    if pack is None or judgement is None:
        return
    who = _who()
    if staged.revision is not None:
        _apply_revision(repository, staged, pack, staged.revision, who)
        return
    try:
        if judgement.verdict == JUDGE_RESUME:
            repository.resume_extra_process(
                expected_seq=staged.seen_seq,
                applied_by=who,
                s3_key=staged.fetch.key,
                s3_etag=staged.fetch.etag,
                s3_last_modified=staged.fetch.last_modified,
            )
        else:
            repository.apply_extra_process(
                staged.fetch.data,
                sha256=staged.reading.sha256,
                version_no=pack.info.version_no,
                expected_seq=staged.seen_seq,
                applied_by=who,
                process_count=len(pack.processes),
                row_counts=json.dumps(pack.row_counts(), ensure_ascii=False, sort_keys=True),
                source_place=staged.fetch.place,
                s3_key=staged.fetch.key,
                s3_etag=staged.fetch.etag,
                s3_last_modified=staged.fetch.last_modified,
            )
    except (ExtraProcessMoved, ValueError) as exc:
        queue_flash(FLASH_KEY, bootstrap_error_message(exc), kind="error", icon=":material/error:")
    else:
        STAGED.clear()
        PREVIEW.clear()
        HEAD_SEEN.clear()
        queue_flash(FLASH_KEY, f"부대공정 판 {pack.info.version_no} 적용")
    st.rerun()


# ------------------------------------------------------------------- S3 Drive 쓰기 · 새 파일


def _report_remote_state(state: ExtraProcessState | None, tab: str) -> None:
    """상태 알림 `EP-05`(「새 판으로」 뒤 S3 Drive 에 쓰지 못함)와 `EP-02`(가져오지 않은 새 파일).

    내보내기 자리가 꽂혀 있을 때만 조건이 선다(지금 판은 시험만 꽂는다). 조건이 없어도 늘 두 번
    부른다(해소 — 이벤트 칸 자리 수가 갈래와 상관없이 같다). `state` 가 None(판을 못 읽음 · 쓰는
    단추가 잠긴 회차)이면 둘 다 조건 없음이다.
    """
    sink = installed_sink()
    active = None if state is None else state.active
    found = False if sink is None or state is None else pending_write(state)
    pending = found is not False
    last = found if isinstance(found, ExtraProcessS3Write) else None
    version = None if active is None else active.version_no
    name = f"판 {version}"
    why = (
        "아직 쓰지 않음"
        if last is None
        else f"{last.result_label}"
        + (f" — {last.stage} {last.reason or ''}".rstrip() if last.stage else "")
    )
    alerts.state(
        "EP-05",
        scope={"version": version},
        content=None if not pending or last is None else [last.seq, last.result],
        active=pending,
        text=f"부대공정 {with_object_particle(name)} S3 Drive 에 쓰지 못함 · {why}",
        full=(
            f"「이 리비전 값을 새 판으로」 로 만든 {with_subject_particle(name)} S3 Drive 의 "
            f"current.zip 에 아직 없습니다({why}). 적용하지 않은 파일이 놓여 있으면 치운 뒤 "
            "「S3 에 다시 쓰기」 를 누르세요. 다음 등록 · 자동 갱신은 DB 의 "
            f"{with_direction_particle(name)} 돕니다."
        ),
        tab=tab,
    )
    word = _new_file_word(state) if sink is not None and state is not None else None
    alerts.state(
        "EP-02",
        scope=None,
        content=None,
        active=word == NEW_FILE_WORD,
        text="S3 Drive 에 가져오지 않은 부대공정 파일이 있음",
        full=(
            "S3 Drive 의 extra_process/current.zip 이 적용한 판 · 앱이 쓴 파일과 다릅니다 — "
            "가져와 검사한 뒤 적용하세요."
        ),
        tab=tab,
    )


def _new_file_word(state: ExtraProcessState) -> str | None:
    """S3 Drive 자리를 HEAD 로 본 낱말 — `HEAD_INTERVAL` 안에 본 적이 있으면 그 낱말을 잇는다
    (HEAD 한 번이 회차를 묶지 않게). 가져오기 원천이 없으면 가져올 길이 없어 보지 않는다. 가져오기 ·
    적용이 성공하면 메모를 비워 다음 회차가 다시 본다 — 같은 세션이 가져와 적용한 파일을 5분 동안
    「새 파일」 로 잇지 않게(2026-11-19 E2E e3-D2)."""
    sink = installed_sink()
    if sink is None or installed_source() is None:
        return None
    now = datetime.now(KST)
    memo = HEAD_SEEN.get()
    if len(memo) == 2 and isinstance(memo[0], datetime) and now - memo[0] < HEAD_INTERVAL:
        return str(memo[1])
    try:
        head = sink.head()
    except Exception as exc:  # noqa: BLE001 — 꽂이의 어떤 실패도 탭을 멈추지 않고 「읽지 못함」 이다.
        word = f"읽지 못함({failure_reason(exc)})"
    else:
        word = head_word(head.etag, state, _known_etags())
    HEAD_SEEN.set((now, word))
    SEEN.set(SeenSource(sink.place, word, now))
    return word


def _known_etags() -> dict[str, str]:
    memo = FETCHED.get()
    if len(memo) == 2 and memo[0]:
        return {str(memo[0]): str(memo[1])}
    return {}


def _write_active(
    repository: DuckDBScenarioRepository,
    state: ExtraProcessState,
    version: ExtraProcessVersion,
    data: bytes,
    who: str | None,
) -> WriteOutcome | None:
    """활성 판을 S3 Drive 에 쓰고 결과를 넣는다(넣기만). 꽂힌 내보내기가 없으면 None."""
    sink = installed_sink()
    if sink is None:
        return None
    now = datetime.now(KST)
    outcome = write_back(sink, data, baseline=state.baseline[0], now=now, known=_known_etags())
    SEEN.set(SeenSource(sink.place, outcome.word, now))
    # 방금 본 낱말을 새 파일 감지 메모에도 둔다 — 다음 회차 HEAD 가 「같음 — 앱이 씀」 을 곧바로
    # 「같음」 으로 덮지 않게(`HEAD_INTERVAL` 동안 잇는다).
    HEAD_SEEN.set((now, outcome.word))
    repository.record_extra_process_write(
        version_seq=version.seq,
        result=outcome.result,
        written_by=who,
        etag=outcome.etag,
        seen_etag=outcome.seen_etag,
        stage=outcome.stage,
        reason=outcome.reason,
    )
    return outcome


def _queue_write_result(head: str, version_no: int | None, outcome: WriteOutcome | None) -> None:
    """적용 · 다시 쓰기의 알림 하나 — 덮으면 「앱이 덮음 · 판 · 시각」(성공), 덮지 못하면 경고 ·
    오류(그 자리에 고칠 입력이 없어 알림창 · Alarm 에만)."""
    if outcome is None:
        queue_flash(FLASH_KEY, head)
        return
    stamp = f"{datetime.now(KST):%m-%d %H:%M}"
    if outcome.result == EXTRA_WRITE_WRITTEN:
        queue_flash(
            FLASH_KEY,
            " · ".join(
                part
                for part in (head, f"S3 Drive current.zip 을 앱이 덮음 · 판 {version_no} · {stamp}")
                if part
            ),
        )
        return
    if outcome.stage is None:
        detail = (
            f"S3 Drive 에 적용하지 않은 파일이 있어 덮지 않았습니다({outcome.word}) — 그 파일을 "
            "치운 뒤 「S3 에 다시 쓰기」 를 누르세요"
        )
        kind = "warning"
    else:
        detail = (
            f"S3 Drive 에 쓰지 못했습니다({outcome.stage} {outcome.reason or ''}".rstrip()
            + ") — 「S3 에 다시 쓰기」 로 다시 씁니다"
        )
        kind = "error"
    queue_flash(
        FLASH_KEY,
        " — ".join(part for part in (head, detail) if part),
        kind="warning" if kind == "warning" else "error",
        icon=":material/cloud_off:",
        popup_only=True,
    )


def _render_rewrite(
    repository: DuckDBScenarioRepository, state: ExtraProcessState, lock: str | None
) -> None:
    """「S3 에 다시 쓰기」 — 꽂힌 내보내기가 있고 활성 「새 판」 을 아직 쓰지 못했을 때만 선다."""
    if installed_sink() is None or not needs_write(state):
        return
    if not st.button(
        REWRITE_LABEL,
        key=REWRITE_BUTTON_KEY,
        icon=":material/cloud_upload:",
        disabled=lock is not None,
        help=lock or REWRITE_HELP,
    ):
        return
    again = write_lock_reason()
    if again is not None:
        queue_flash(FLASH_KEY, again, kind="error", icon=":material/block:")
        st.rerun()
    try:
        # 누른 회차에 다시 읽는다 — 겹친 둘째 누름은 이미 쓴 판을 보고 쓰지 않는다.
        fresh = repository.load_extra_process_state()
        active = fresh.active
        if active is None or active.sha256 is None or not needs_write(fresh):
            queue_flash(FLASH_KEY, "S3 Drive 에 이미 썼습니다", kind="info")
            st.rerun()
        assert active is not None and active.sha256 is not None
        data = repository.load_extra_process_content(active.sha256)
        outcome = _write_active(repository, fresh, active, data, _who())
    except (*BOOTSTRAP_ERRORS,) as exc:
        queue_flash(FLASH_KEY, bootstrap_error_message(exc), kind="error", icon=":material/error:")
        st.rerun()
    _queue_write_result("", active.version_no, outcome)
    st.rerun()


# ------------------------------------------------------------------- 이 리비전 값을 새 판으로


def _revision_target() -> tuple[str, str] | None:
    """올라와 있는 저장 리비전(시나리오 id, 리비전 id) — 없으면 None(내장 시드 등)."""
    scenario_id = active_persisted_scenario_id()
    revision_id = active_persisted_revision_id()
    if scenario_id is None or revision_id is None:
        return None
    return scenario_id, revision_id


def _revision_lock(
    repository: DuckDBScenarioRepository,
    state: ExtraProcessState,
    target: tuple[str, str] | None,
) -> str | None:
    """「새 판으로」 를 누를 수 없는 까닭(G4) — 누를 수 있으면 None."""
    if target is None:
        return NO_REVISION_REASON
    active = state.active
    try:
        records = repository.load_scenario_extra_process(target[0])
    except BOOTSTRAP_ERRORS as exc:
        return bootstrap_error_message(exc)
    return revision_refusal(
        off=state.off,
        active_sha=None if active is None else active.sha256,
        active_version_no=None if active is None else active.version_no,
        records=records,
    )


def _render_revision_button(
    repository: DuckDBScenarioRepository, state: ExtraProcessState, lock: str | None
) -> None:
    target = _revision_target()
    reason = lock or _revision_lock(repository, state, target)
    if st.button(
        REVISION_LABEL,
        key=REVISION_BUTTON_KEY,
        icon=":material/upgrade:",
        disabled=reason is not None,
        help=reason or REVISION_HELP,
    ):
        _stage_revision(repository)


def _stage_revision(repository: DuckDBScenarioRepository) -> None:
    """올라와 있는 저장 리비전의 값으로 다음 판을 거꾸로 만들어 받은 판 자리에 둔다(쓰지 않는다)."""
    lock = write_lock_reason()
    target = _revision_target()
    if lock is not None or target is None:
        queue_flash(FLASH_KEY, lock or NO_REVISION_REASON, kind="error", icon=":material/block:")
        st.rerun()
    assert target is not None
    scenario_id, revision_id = target
    now = datetime.now(KST)
    PREVIEW.clear()
    try:
        with st.spinner("리비전 값으로 다음 판을 만드는 중입니다..."):
            state = repository.load_extra_process_state()
            refusal = _revision_lock(repository, state, target)
            active = state.active
            base = None if refusal is not None else _content(repository, active)
            if refusal is not None or base is None or active is None:
                queue_flash(
                    FLASH_KEY,
                    refusal or "활성 부대공정 판을 읽지 못했습니다",
                    kind="error",
                    icon=":material/block:",
                )
                st.rerun()
            assert base is not None and active is not None and active.sha256 is not None
            snapshot = repository.load_revision(revision_id, apply_global_display_order=False)
            label = f"{snapshot.scenario.scenario_name} r{snapshot.revision.revision_no}"
            latest = state.latest_content
            version_no = (0 if latest is None else latest.version_no or 0) + 1
            built = pack_from_revision(
                base,
                snapshot.tables,
                merged_processes(repository.load_scenario_extra_process(scenario_id)),
                version=ExtraPackVersion(active.seq, active.version_no or 0, active.sha256),
                version_no=version_no,
                written_at=now.isoformat(timespec="seconds"),
                memo=f"앱 — {label} 에서",
            )
            pack = built.reading.pack
            changes = (
                None
                if pack is None
                else pack_changes(pack, base, _content(repository, previous_content(state)))
            )
    except _STAGE_ERRORS as exc:
        queue_flash(
            FLASH_KEY,
            f"리비전 값으로 판을 만들지 못했습니다 — {_stage_error_word(exc)}",
            kind="error",
            icon=":material/error:",
        )
        st.rerun()
    if changes is not None and not (changes.changed_cells or changes.added or changes.removed):
        STAGED.clear()
        queue_flash(FLASH_KEY, UNCHANGED_REVISION, kind="info")
        st.rerun()
    STAGED.set(
        StagedPack(
            fetch=SourceFetch(data=built.data, place=EXTRA_REVISION_PLACE),
            reading=built.reading,
            judgement=None if pack is None else PackJudgement(JUDGE_APPLY, f"새 판 {version_no}"),
            seen_seq=state.last_seq,
            staged_at=now,
            changes=changes,
            revision=RevisionOrigin(
                scenario_id,
                revision_id,
                label,
                built.moved,
                built.kept,
                built.route_differs,
            ),
        )
    )
    st.rerun()


def _apply_revision(
    repository: DuckDBScenarioRepository,
    staged: StagedPack,
    pack: ExtraProcessPack,
    origin: RevisionOrigin,
    who: str | None,
) -> None:
    """「새 판 적용」 — DB 에 새 판을 먼저 넣고(정본), 꽂힌 내보내기가 있으면 S3 Drive 를 덮는다."""
    try:
        after = repository.revise_extra_process(
            staged.fetch.data,
            sha256=staged.reading.sha256,
            version_no=pack.info.version_no,
            expected_seq=staged.seen_seq,
            applied_by=who,
            process_count=len(pack.processes),
            row_counts=json.dumps(pack.row_counts(), ensure_ascii=False, sort_keys=True),
            base_scenario_ref=origin.scenario_id,
            base_revision_ref=origin.revision_id,
        )
    except (ExtraProcessMoved, ValueError) as exc:
        queue_flash(FLASH_KEY, bootstrap_error_message(exc), kind="error", icon=":material/error:")
        st.rerun()
    STAGED.clear()
    PREVIEW.clear()
    head = f"부대공정 판 {pack.info.version_no} 적용 — 리비전에서"
    active = after.active
    try:
        outcome = (
            None
            if active is None or active.kind != EXTRA_KIND_REVISION
            else _write_active(repository, after, active, staged.fetch.data, who)
        )
    except BOOTSTRAP_ERRORS as exc:
        queue_flash(
            FLASH_KEY,
            f"{head} — S3 Drive 쓰기 결과를 남기지 못했습니다({bootstrap_error_message(exc)})",
            kind="error",
            icon=":material/error:",
            popup_only=True,
        )
        st.rerun()
    _queue_write_result(head, pack.info.version_no, outcome)
    st.rerun()


def _who() -> str | None:
    identity = sso_identity.verified_identity()
    return None if identity is None else identity.loginid


def _problem_frame(staged: StagedPack) -> pd.DataFrame:
    rows = [
        {
            "규칙": problem.code,
            "파일": problem.file,
            "행": problem.row,
            "칸": problem.column,
            "까닭": problem.reason,
        }
        for problem in staged.reading.problems
    ]
    return pd.DataFrame(rows, columns=["규칙", "파일", "행", "칸", "까닭"])


def _masked(name: str | None) -> str:
    """적용한 사람은 앞 두 글자만(값 원문을 넓게 펴지 않는다)."""
    if not name:
        return ""
    return name[:2] + "…" if len(name) > 2 else name


def history_frame(state: ExtraProcessState, bases: Mapping[str, str] | None = None) -> pd.DataFrame:
    """판 이력 표(새 줄이 위) — 판 · 갈래 · 적용 시각 · 적용한 사람(가림) · sha 앞 8자 · 공정 수 ·
    행 수 · 바탕(새 판이면 시나리오 · 리비전 — `bases` 는 리비전 id → 글) · S3 쓰기(그 판의 마지막
    쓰기 결과와 시각 — 「앱이 덮음 11-19 01:23」)."""
    rows = []
    for item in reversed(state.history):
        counts = json.loads(item.row_counts) if item.row_counts else {}
        last = state.last_write(item.seq)
        base = (
            (bases or {}).get(item.base_revision_ref, "")
            if item.kind == EXTRA_KIND_REVISION and item.base_revision_ref
            else ""
        )
        rows.append(
            {
                "판": "" if item.version_no is None else str(item.version_no),
                "갈래": item.kind_label,
                "적용 시각": f"{item.created_at:%Y-%m-%d %H:%M}",
                "적용한 사람": _masked(item.applied_by),
                "sha": (item.sha256 or "")[:8],
                "공정 수": "" if item.process_count is None else str(item.process_count),
                "행 수": "" if not counts else str(sum(int(value) for value in counts.values())),
                "바탕": base,
                "S3 쓰기": (
                    "" if last is None else f"{last.result_label} {last.created_at:%m-%d %H:%M}"
                ),
            }
        )
    return pd.DataFrame(rows, columns=list(HISTORY_COLUMNS))


def _base_labels(repository: DuckDBScenarioRepository, state: ExtraProcessState) -> dict[str, str]:
    """「새 판」 줄의 바탕 리비전 id → 「시나리오 r번호」(지운 리비전 · 못 읽음은 빈 글)."""
    refs = [
        item.base_revision_ref
        for item in state.history
        if item.kind == EXTRA_KIND_REVISION and item.base_revision_ref
    ]
    if not refs:
        return {}
    try:
        found = repository.list_revisions_by_ids(refs)
        names = {
            item.scenario_id: item.scenario_name
            for item in repository.list_scenarios(include_archived=True)
        }
    except BOOTSTRAP_ERRORS:
        return {}
    return {
        revision_id: f"{names.get(summary.scenario_id, '')} r{summary.revision_no}".strip()
        for revision_id, (summary, _status) in found.items()
    }


def _render_history(repository: DuckDBScenarioRepository, state: ExtraProcessState) -> None:
    if not state.history:
        return
    st.dataframe(
        history_frame(state, _base_labels(repository, state)),
        hide_index=True,
        width="stretch",
        placeholder="",
    )
