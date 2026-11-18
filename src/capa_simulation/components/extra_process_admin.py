# Purpose: Admin Area 「부대공정」 탭 — 판 상태 줄 · 양식 내려받기 · 끄기 / 다시 켜기 · 판 이력과
# 받은 판의 거절 표 · 미리보기 시험 계산 · 적용을 그린다.

"""Admin 「부대공정」(설계 3-4 · A7 — 1단계).

**보이는 것.** 상태 줄 값 한 줄(「부대공정 · 판 3 · 공정 2 · 적용 11-13 09:12」 — 끈 동안 「꺼짐 ·
마지막 판 3」, 판이 없으면 「판 없음」. 원천을 본 적이 있으면 끝에 「<자리> <낱말>(hh:mm 에 봄)」),
단추 줄(가져오기 · 양식 내려받기 · 끄기 / 다시 켜기), 받은 판이 있으면 그 거절 표 또는 미리보기,
맨 아래 판 이력 표. 설명 글은 세우지 않는다 — 단추 · 칸의 뜻은 풍선, 탭의 쓰임은 Guide 다(설계
규칙 UI-TXT-01 · UI-TXT-02).

**가져오기 단추는 원천이 꽂혀 있을 때만 선다**(`extra_process_intake.installed_source`). 1단계는
원천을 꽂지 않는다 — S3 Drive 가져오기는 사내 확인 부대 5 · 6 의 답 뒤에 붙인다(설계 9-4).

**쓰는 단추**(가져오기 · 적용 · 끄기 / 다시 켜기)는 C-DEP(`managed` + S3 접속 정보)의 실제
개발자에게만 열린다(`write_lock_reason`) — 그 밖에는 잠그고 풍선에 까닭을 단다(UI-INP-07). 누른
회차에도 판정을 한 번 더 하고, 저장소 쓰기는 `admin.area` 벽 뒤다. 쓰기는 화면이 본 판 이력 마지막
차례와 대조한다 — 겹친 둘째 누름 · 남의 먼저 쓰기는 쓰지 않는다(UI-STA-05). 쓰기는 본문에서
한다(콜백 아님).

**미리보기 시험 계산**은 「시험 계산」 을 누른 회차에만 돈다 — 지금 활성 시나리오의 표에 받은 판을
합쳐(그 시나리오에 이미 든 부대공정은 먼저 걷고) 공정마다 합침 · 뺌, 월별 소요대수 · 가용 · 확보율,
부하 붙은 · 0 경로 수와 지금 판과의 차이 · 앞 판 값으로 되돌리는 칸 수 · 측정률 칸 수를 보인다.
결과는 (판 sha, 활성 리비전 content_token)마다 세션에 둔다 — 회차마다 다시 돌리지 않는다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components import sso_identity
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.state_alerts import tab_name
from capa_simulation.components.table_toolbar import render_zip_download, toolbar_clearance
from capa_simulation.extra_process_intake import (
    PackPreview,
    SourceFailure,
    StagedPack,
    installed_source,
    preview_pack,
    previous_content,
    production_place,
    stage_pack,
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
    ExtraProcessProvenance,
    ExtraProcessState,
    ExtraProcessVersion,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import active_persisted_scenario_id
from capa_simulation.scenario_state import ensure_active_scenario
from capa_simulation.services.extra_process_merge import (
    OUTCOME_DROPPED,
    OUTCOME_GRADUATED,
    OUTCOME_MERGED,
)
from capa_simulation.services.extra_process_pack import (
    JUDGE_RESUME,
    JUDGE_UNCHANGED,
    ExtraProcessPack,
    pack_to_zip,
    read_pack_zip,
    template_zip,
)

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

STATUS_HEAD: Final = "부대공정"
DOWNLOAD_LABEL: Final = "양식 내려받기"
OFF_LABEL: Final = "끄기"
RESUME_LABEL: Final = "다시 켜기"
PREVIEW_LABEL: Final = "시험 계산"
APPLY_LABEL: Final = "적용"
DISCARD_LABEL: Final = "치우기"
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
OUTCOME_LABELS: Final = {
    OUTCOME_MERGED: "합침",
    OUTCOME_DROPPED: "뺌",
    OUTCOME_GRADUATED: "BDQ 에 생김",
}
HISTORY_COLUMNS: Final = ("판", "갈래", "적용 시각", "적용한 사람", "sha", "공정 수", "행 수")


@dataclass(frozen=True)
class SeenSource:
    """마지막으로 원천을 본 결과 — 상태 줄 끝 낱말과 본 시각."""

    place: str
    word: str
    seen_at: datetime


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
        render_data_error(
            bootstrap_error_message(exc),
            code="AD-07",
            tab=tab_name(TAB_LABEL),
            text="부대공정 판을 읽지 못했습니다",
        )
        return
    lock = write_lock_reason()
    seen = st.session_state.get(SEEN_KEY)
    st.caption(status_line(state, seen if isinstance(seen, SeenSource) else None))
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
        _render_download(repository, state)
        _render_toggle(repository, state, lock)
    staged = st.session_state.get(STAGED_KEY)
    if isinstance(staged, StagedPack):
        _render_staged(repository, state, staged, lock, opened=opened)
    if opened:
        _render_history(state)


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
    memo = st.session_state.get(TEMPLATE_KEY)
    if isinstance(memo, tuple) and len(memo) == 3 and memo[0] == latest.sha256:
        return bytes(memo[1]), str(memo[2])
    reading = read_pack_zip(repository.load_extra_process_content(latest.sha256))
    if reading.pack is None:
        return template_zip(), BLANK_TEMPLATE_FILE
    result = (pack_to_zip(reading.pack), TEMPLATE_FILE.format(version=latest.version_no))
    st.session_state[TEMPLATE_KEY] = (latest.sha256, *result)
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


def _import(repository: DuckDBScenarioRepository) -> None:
    """원천에서 받아 검사한다 — 바뀐 것 없으면 알리기만, 아니면 받은 판을 세션에 둔다."""
    source = installed_source()
    if source is None or write_lock_reason() is not None:
        return
    now = datetime.now(KST)
    st.session_state.pop(PREVIEW_KEY, None)
    try:
        with st.spinner("부대공정 판을 받는 중입니다..."):
            fetched = source.fetch()
    except SourceFailure as failure:
        st.session_state[SEEN_KEY] = SeenSource(source.place, f"읽지 못함({failure.reason})", now)
        queue_flash(
            FLASH_KEY,
            f"부대공정 판을 가져오지 못했습니다 — {failure.reason}. 지난 판으로 계속합니다.",
            kind="error",
            icon=":material/error:",
            alert="EP-01",
            popup_only=True,
        )
        st.rerun()
    staged = stage_pack(repository.load_extra_process_state(), fetched, now=now)
    word = _staged_word(staged)
    st.session_state[SEEN_KEY] = SeenSource(source.place, word, now)
    if staged.judgement is not None and staged.judgement.verdict == JUDGE_UNCHANGED:
        st.session_state.pop(STAGED_KEY, None)
        queue_flash(FLASH_KEY, "바뀐 것 없음 — 활성 판과 같은 파일입니다", kind="info")
    else:
        st.session_state[STAGED_KEY] = staged
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
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(f"**받은 판** · {_staged_word(staged)} · sha {reading.sha256[:8]}")
            if st.button(DISCARD_LABEL, key=DISCARD_BUTTON_KEY, type="tertiary"):
                st.session_state.pop(STAGED_KEY, None)
                st.session_state.pop(PREVIEW_KEY, None)
                st.rerun()
        if not reading.accepted or staged.judgement is None:
            toolbar_clearance()
            st.dataframe(_problem_frame(staged), hide_index=True, width="stretch", placeholder="")
            return
        if not staged.judgement.applicable:
            st.error(staged.judgement.reason, icon=":material/block:")
            return
        st.caption(reading.ratio.text())
        preview = _preview(repository, state, staged, run=opened)
        if preview is not None:
            _render_preview(preview)
        if st.button(
            APPLY_LABEL,
            key=APPLY_BUTTON_KEY,
            type="primary",
            icon=":material/check:",
            disabled=lock is not None,
            help=lock or APPLY_HELP,
        ):
            _apply(repository, staged)


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
    except BOOTSTRAP_ERRORS:
        return None
    memo_key = (staged.reading.sha256, str(active["content_token"]))
    memo = st.session_state.get(PREVIEW_KEY)
    if isinstance(memo, tuple) and len(memo) == 2 and memo[0] == memo_key:
        cached = memo[1]
        if isinstance(cached, PackPreview):
            return cached
    if not run or not st.button(PREVIEW_LABEL, key=PREVIEW_BUTTON_KEY, help=PREVIEW_HELP):
        return None
    try:
        with st.spinner("시험 계산 중입니다..."):
            preview = _compute_preview(repository, state, pack, tables)
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc), icon=":material/error:")
        return None
    st.session_state[PREVIEW_KEY] = (memo_key, preview)
    return preview


def _compute_preview(
    repository: DuckDBScenarioRepository,
    state: ExtraProcessState,
    pack: ExtraProcessPack,
    tables: Mapping[str, pd.DataFrame],
) -> PackPreview:
    scenario_id = active_persisted_scenario_id()
    previous = (
        ()
        if scenario_id is None
        else tuple(
            dict.fromkeys(
                item.process_name
                for item in repository.load_scenario_extra_process(scenario_id)
                if item.outcome == OUTCOME_MERGED
            )
        )
    )
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
    changes = preview.changes
    st.caption(
        " · ".join(
            [
                f"더한 공정 {len(changes.added)}",
                f"뺀 공정 {len(changes.removed)}",
                f"바뀐 칸 {changes.changed_cells}",
                f"앞 판 값으로 되돌리는 칸 {changes.reverted_cells}",
                preview.report.counts_text(),
            ]
        )
    )
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
                }
                for item in preview.report.outcomes
            ]
        ),
        hide_index=True,
        width="stretch",
        placeholder="",
    )
    if not preview.rates.empty:
        st.dataframe(preview.rates, hide_index=True, width="stretch", placeholder="")


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
    try:
        if judgement.verdict == JUDGE_RESUME:
            repository.resume_extra_process(expected_seq=staged.seen_seq, applied_by=who)
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
        st.session_state.pop(STAGED_KEY, None)
        st.session_state.pop(PREVIEW_KEY, None)
        queue_flash(FLASH_KEY, f"부대공정 판 {pack.info.version_no} 적용")
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


def history_frame(state: ExtraProcessState) -> pd.DataFrame:
    """판 이력 표(새 줄이 위) — 판 · 갈래 · 적용 시각 · 적용한 사람(가림) · sha 앞 8자 · 공정 수 ·
    행 수."""
    rows = []
    for item in reversed(state.history):
        counts = json.loads(item.row_counts) if item.row_counts else {}
        rows.append(
            {
                "판": "" if item.version_no is None else str(item.version_no),
                "갈래": item.kind_label,
                "적용 시각": f"{item.created_at:%Y-%m-%d %H:%M}",
                "적용한 사람": _masked(item.applied_by),
                "sha": (item.sha256 or "")[:8],
                "공정 수": "" if item.process_count is None else str(item.process_count),
                "행 수": "" if not counts else str(sum(int(value) for value in counts.values())),
            }
        )
    return pd.DataFrame(rows, columns=list(HISTORY_COLUMNS))


def _render_history(state: ExtraProcessState) -> None:
    if not state.history:
        return
    st.dataframe(history_frame(state), hide_index=True, width="stretch", placeholder="")
