# Purpose: 시나리오 관리 「자동 갱신」 탭(상태·설정·지금 실행·실행/설정 기록)을 그린다.

"""시나리오 관리 셋째 탭 「자동 갱신」(2026-10-15 사용자 결정).

켜 두면 매일 지정 시각에 앱 안에서 BigDataQuery 목록을 본다. 시뮬레이션명에 키워드(기본 `PSM`)와
주차(`W##`)가 있고 현재 공식버전보다 새 코드를 받아 등록 → 확보율 판정(기준 미만 공정 off) →
리비전 2 → 공식버전 발행까지 한다. 규칙은 `services/auto_official_update.py`, 한 회차는
`auto_official_update_runner.py`, 예약은 `auto_update_scheduler.py` 다. 이 탭은 그 셋을 보여 주고
설정을 바꾼다.

- **지금 상태**: 이 실행(앱 프로세스)에서 예약이 서 있는가 — 실행 줄 허락
  (`CAPA_AUTO_OFFICIAL_UPDATE=1`)이 없으면 「이 실행에서는 꺼짐」 안내, 다음 실행 시각(오늘 회차를
  이미 잡았으면 내일), 현재 공식버전의 주차(또는 오류). 회차가 오래 돌거나 배경 확인이 멈춘 것
  같으면 경고한다(사내 조회에는 시간 제한이 없다).
- **설정**: 켜기·확인 시각·시뮬레이션명 키워드·기준 확보율. 공용 프로필이라 저장은 편집을 시작할
  때 본 version 과 대조하고, 바꾼 칸을 설정 변경 기록에 남긴다. **켤 때** 현재 공식버전에 주차가
  없으면 저장하지 않고 오류로 알린다.
- **지금 실행**: 예약과 같은 회차 함수를 지금 한 번 돈다(시험·확인용). 켜짐·실행 줄 허락과
  상관없이 돈다. 회차 선점 키가 누를 때마다 달라 **같은 날 예약 회차를 막지도, 그것에 막히지도
  않는다** — 이미 받은 코드는 다시 받지 않으므로 같은 코드가 두 번 발행되지 않는다. 같은
  프로세스에서 다른 회차가 도는 중이면 돌지 않고 알린다. 현재 공식버전에 주차가 없으면 아무것도
  하지 않고 오류로 알린다(기록도 남기지 않는다). 회차 전에 세션에 표를 적어 두므로, 도는 사이
  다른 칸을 눌러 결과 알림이 끊겨도 새 실행이 실행 기록에서 찾는다 — 아직 돌면 끝날 때까지 기록을
  다시 보다가 결과를 보인다. 발행한 회차에 소요대수에
  들지 않은 수요가 있었으면 화면 발행과 같이 성공 알림 밑에 그 건수를 경고로 따로 띄운다(실행 기록의
  사유에는 이어 적힌 그대로다).
- **실행 기록·off 공정·설정 변경 기록** 표. 실행 기록은 그 경고가 사유 끝에 이어 적혀 칸이 좁으면
  잘려 안 보이므로 「결과」 바로 뒤 「경고」 칸에 짧은 표지를 따로 둔다.

설정 칸에는 `key` 를 두지 않는다(HOME 판정 기준 편집기와 같은 까닭) — 키가 붙은 칸은 한 번 그려진
뒤 세션 값을 써서, 다른 사람이 바꾼 설정을 이 화면이 못 본 채 저장 한 번으로 되돌린다. 키 없는
칸은 `value=` 가 바뀌면 새로 서서 저장본을 따라온다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Final
from uuid import uuid4

import pandas as pd
import streamlit as st

from capa_simulation.auto_official_update_runner import (
    AutoUpdateSources,
    Clock,
    auto_off_marks,
    current_official_baseline,
    run_auto_official_update,
    split_published_reason,
)
from capa_simulation.auto_update_scheduler import (
    ENV_VAR,
    SchedulerStatus,
    running_scheduler,
    scheduler_opted_in,
)
from capa_simulation.components.flash import FlashKind, pending_flash, queue_flash, render_flash
from capa_simulation.components.intro_summary import forget_intro_summary_check
from capa_simulation.components.literal_markdown import (
    literal_markdown,
    markdown_safe_tildes,
    quoted,
)
from capa_simulation.components.process_labels import ProcessLabels, get_process_labels
from capa_simulation.components.profile_caption import profile_version_caption
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
from capa_simulation.persistence.auto_official_update_store import (
    AutoOfficialUpdateSettingsConflict,
)
from capa_simulation.persistence.cache import (
    clear_global_securement_threshold_cache,
    get_scenario_repository,
)
from capa_simulation.persistence.models import (
    AutoOfficialUpdateExclusion,
    AutoOfficialUpdateRun,
    AutoOfficialUpdateSettingChange,
    AutoOfficialUpdateSettings,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import (
    active_persisted_revision_id,
    active_persisted_scenario_id,
)
from capa_simulation.services.auto_official_update import (
    DEFAULT_CONFIG,
    EXCLUSION_AUTO,
    MAX_KEYWORD_LENGTH,
    MAX_THRESHOLD,
    MIN_THRESHOLD,
    STAGE_LABELS,
    STATUS_ERROR,
    STATUS_LABELS,
    STATUS_PUBLISH_SKIPPED,
    STATUS_PUBLISHED,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    TRIGGER_LABELS,
    TRIGGER_MANUAL,
    AutoUpdateConfig,
    MissingOfficialWeek,
    auto_off_mark,
    describe_config_change,
    next_scheduled_run,
    percent_text,
    scheduled_run_key,
    time_text,
    week_label,
)

SETTINGS_FLASH_KEY = "auto_official_update_settings_flash"
# 설정 폼을 제출하지 않은 회차에 본 저장본 version(`write_guard.remember_seen`). 제출 회차에는
# 이것이 「편집을 시작할 때 본 version」이다.
SETTINGS_BASE_VERSION_KEY = "auto_official_update_settings_base_version"
# 설정 저장의 제 저장·충돌·거부 표지 이름(`write_guard`).
SETTINGS_SAVE_NAME = "auto_official_update_settings"
SETTINGS_SAVED_PREFIX: Final = "자동 갱신 설정을 저장했습니다"
# 「지금 실행」 결과 알림과, 발행한 회차의 소요대수에 들지 않은 수요 경고(성공 알림 밑에 따로).
# rerun 을 건너 그 자리에 한 번 그린다(`flash`).
RUN_RESULT_KEY = "auto_official_update_run_result"
RUN_WARNING_KEY = "auto_official_update_run_warning"
# 「지금 실행」 회차의 표(회차 키 끝). 회차 전에 적고 결과를 보이면 지운다 — 도는 사이 다른 칸을
# 눌러 새 실행이 서면 결과 알림을 그릴 실행이 끊기므로, 새 실행이 이 표로 실행 기록을 찾는다.
PENDING_RUN_TOKEN_KEY = "auto_official_update_pending_run_token"
# 끊긴 「지금 실행」 회차가 아직 도는 동안 기록을 다시 보는 프래그먼트와 그 간격.
RUN_POLL_FRAGMENT_KEY = "auto_official_update_run_poll"
RUN_POLL_INTERVAL: Final = timedelta(seconds=3)
RUNNING_MESSAGE: Final = (
    "「지금 실행」 회차가 아직 도는 중입니다 — 끝나면 결과가 여기에 저절로 뜹니다."
)
# 끝난 「지금 실행」 회차의 상태별 알림 종류·아이콘. 표에 없는 상태는 아이콘 없는 안내다.
_RUN_RESULT_STYLES: Final[dict[str, tuple[FlashKind, str | None]]] = {
    STATUS_PUBLISHED: ("success", ":material/publish:"),
    STATUS_SKIPPED: ("info", ":material/skip_next:"),
    STATUS_PUBLISH_SKIPPED: ("warning", ":material/warning:"),
    STATUS_ERROR: ("error", ":material/error:"),
}
RUN_NOW_BUTTON_KEY = "auto_official_update_run_now"
OFF_LIST_EXPANDER_KEY = "auto_official_update_off_list_expander"
RUN_HISTORY_LIMIT: Final = 30
SETTING_HISTORY_LIMIT: Final = 20
DATETIME_FORMAT: Final = "%Y-%m-%d %H:%M"
# 회차가 이보다 오래 「진행 중」이면 멈춘 것으로 보고 경고한다(사내 조회·전체 기간 계산은 보통
# 몇 분이다).
LONG_RUN_WARNING: Final = timedelta(minutes=30)
# 배경 확인이 이 횟수만큼 건너뛰었으면 스레드가 멈춘 것으로 보고 경고한다.
STALE_TICK_FACTOR: Final = 4
EMPTY: Final = "—"
# 실행 기록 「경고」 칸의 표지 — 발행한 회차의 사유 끝에 소요대수에 들지 않은 수요 경고가 이어
# 적혔다. 문장 전체는 「사유」 칸에 그대로 남는다.
UNCOUNTED_DEMAND_MARK: Final = "⚠ 소요대수 밖 수요"
SETTINGS_SOURCE: Final = "시나리오 관리 · 자동 갱신"


def render_auto_official_update(
    repository: DuckDBScenarioRepository,
    *,
    sources: AutoUpdateSources | None = None,
    clock: Clock = datetime.now,
) -> None:
    """탭 본문. `sources`·`clock` 은 시험이 가짜 원천·시계를 넣는 자리다(화면은 넘기지 않는다)."""
    st.subheader("공식버전 자동 갱신")
    try:
        settings = repository.load_auto_official_update_settings()
    except BOOTSTRAP_ERRORS as exc:
        st.error("자동 갱신 설정을 읽지 못했습니다: " + bootstrap_error_message(exc))
        return
    _render_status(repository, settings, now=clock())
    _render_settings_form(repository, settings)
    _render_run_now(repository, sources=sources, clock=clock)
    try:
        runs = repository.list_auto_official_update_runs(limit=RUN_HISTORY_LIMIT)
        exclusions = repository.list_auto_official_update_exclusions(
            run_ids=[run.run_id for run in runs]
        )
        changes = repository.list_auto_official_update_setting_changes(limit=SETTING_HISTORY_LIMIT)
    except BOOTSTRAP_ERRORS as exc:
        st.error("자동 갱신 기록을 읽지 못했습니다: " + bootstrap_error_message(exc))
        return
    labels = get_process_labels()
    _render_run_history(runs, exclusions, labels)
    _render_setting_history(changes)


# ---------------------------------------------------------------------------
# 지금 상태
# ---------------------------------------------------------------------------


def _render_status(
    repository: DuckDBScenarioRepository,
    settings: AutoOfficialUpdateSettings,
    *,
    now: datetime,
) -> None:
    config = settings.config
    scheduler = running_scheduler()
    with st.container(border=True):
        st.markdown("#### :material/schedule: 지금 상태")
        if scheduler is not None:
            status = scheduler.status()
            st.success("이 실행에서 예약이 켜져 있습니다.", icon=":material/schedule:")
            parts = [
                f"배경 확인 {status.tick_seconds:.0f}초마다",
                f"시작 {format(status.started_at, DATETIME_FORMAT)}",
            ]
            if status.last_tick_at is not None and status.last_outcome is not None:
                last = status.last_outcome
                detail = f" — {last.message}" if last.message else ""
                parts.append(
                    f"마지막 확인 {format(status.last_tick_at, '%Y-%m-%d %H:%M:%S')} "
                    f"{last.label}{detail}"
                )
            if status.pending_day is not None:
                parts.append(f"{status.pending_day.isoformat()} 회차를 다시 시도하는 중")
            st.caption(" · ".join(parts))
            stall = scheduler_stall_message(status, now)
            if stall is not None:
                st.warning(stall, icon=":material/hourglass_top:")
        elif scheduler_opted_in():
            st.warning(
                f"실행 줄은 예약을 허락했지만(`{ENV_VAR}=1`) 예약 스레드가 서 있지 않습니다. 앱 "
                "로그를 확인하고 앱을 다시 띄우세요.",
                icon=":material/warning:",
            )
        else:
            st.info(
                f"이 실행에서는 예약이 꺼져 있습니다 — 실행 줄에 `{ENV_VAR}=1` 을 더해 앱을 띄워야 "
                "지정 시각에 돕니다. 「지금 실행」은 이 실행에서도 됩니다.",
                icon=":material/info:",
            )
        st.markdown(f"**설정** · {_config_line(config)}")
        try:
            claimed_today = repository.auto_official_update_run_key_exists(
                scheduled_run_key(now.date())
            )
        except BOOTSTRAP_ERRORS:
            claimed_today = False
        st.markdown(
            f"**다음 실행** · "
            f"{next_run_line(config, scheduler is not None, now, claimed_today=claimed_today)}"
        )
        try:
            baseline = current_official_baseline(repository)
        except MissingOfficialWeek as exc:
            # 켜져 있으면 예약 회차가 이 까닭으로 멈춘다 — 오류다. 꺼져 있으면 켤 때 막히는 것을
            # 미리 알리는 상태 한 줄이다(켜거나 「지금 실행」을 누르면 그때 오류로 막는다).
            if config.enabled:
                st.error(bootstrap_error_message(exc), icon=":material/error:")
            else:
                st.markdown(f"**현재 공식버전** · :red[주차 없음] — {bootstrap_error_message(exc)}")
        except BOOTSTRAP_ERRORS as exc:
            st.error("현재 공식버전을 읽지 못했습니다: " + bootstrap_error_message(exc))
        else:
            st.markdown(
                f"**현재 공식버전** · {baseline.label} · {literal_markdown(baseline.release_name)} "
                f"({baseline.week_source}에서 읽은 주차)"
            )


def _config_line(config: AutoUpdateConfig) -> str:
    switch = "켜짐" if config.enabled else "꺼짐"
    return (
        f"{switch} · 매일 {time_text(config.check_time)} · 키워드 {quoted(config.keyword)} · "
        f"기준 확보율 {percent_text(config.threshold)}"
    )


def next_run_line(
    config: AutoUpdateConfig,
    scheduled_here: bool,
    now: datetime,
    *,
    claimed_today: bool = False,
) -> str:
    """「다음 실행」 한 줄. 오늘 예약 회차를 이미 잡았으면 오늘 남은 지정 시각이 아니라 내일이다."""
    if not config.enabled:
        return "꺼져 있어 돌지 않습니다."
    if not scheduled_here:
        return "이 실행에서는 돌지 않습니다(실행 줄 허락 없음)."
    upcoming = next_scheduled_run(now, config.check_time)
    if claimed_today and upcoming.date() == now.date():
        upcoming += timedelta(days=1)
        return f"{format(upcoming, DATETIME_FORMAT)} (오늘 회차는 이미 돌았습니다)"
    return format(upcoming, DATETIME_FORMAT)


def scheduler_stall_message(status: SchedulerStatus, now: datetime) -> str | None:
    """배경 예약이 멈춘 것 같으면 그 경고 글. 아니면 None.

    - 회차가 `LONG_RUN_WARNING` 보다 오래 「진행 중」 — 사내 조회가 응답하지 않을 수 있다(시간
      제한이 없다). 그동안 「지금 실행」도 막히고 다음 날 예약도 돌지 않는다.
    - 회차 밖인데 마지막 확인이 확인 간격의 `STALE_TICK_FACTOR` 배보다 오래됐다 — 스레드가 멈췄다.
    """
    last = status.last_outcome
    if status.last_tick_at is None or last is None:
        return None
    elapsed = now - status.last_tick_at
    if last.kind == "running":
        if elapsed < LONG_RUN_WARNING:
            return None
        return (
            f"예약 회차가 {format(status.last_tick_at, DATETIME_FORMAT)}부터 "
            f"{int(elapsed.total_seconds() // 60)}분째 도는 중입니다 — 사내 조회가 응답하지 "
            "않을 수 있습니다. 그동안 「지금 실행」과 다음 예약도 돌지 않습니다. 오래 이어지면 "
            "앱을 다시 띄우세요(실행 기록의 「실행 중」 줄은 다시 띄울 때 오류로 닫힙니다)."
        )
    if elapsed.total_seconds() <= status.tick_seconds * STALE_TICK_FACTOR:
        return None
    return (
        f"배경 확인이 {format(status.last_tick_at, DATETIME_FORMAT)} 뒤로 멈춰 있습니다 — 앱 "
        "로그를 확인하고 앱을 다시 띄우세요."
    )


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------


def _render_settings_form(
    repository: DuckDBScenarioRepository, settings: AutoOfficialUpdateSettings
) -> None:
    submitted_base = seen(SETTINGS_BASE_VERSION_KEY)
    config = settings.config
    with st.container(border=True):
        st.markdown("#### :material/tune: 설정")
        st.caption(
            profile_version_caption(
                settings,
                empty=f"아직 저장하지 않아 기본값({_config_line(DEFAULT_CONFIG)})을 씁니다",
            )
        )
        with st.form("auto_official_update_settings_form"):
            enabled = st.toggle(
                "자동 갱신 켜기",
                value=config.enabled,
                help=(
                    "켜 두면 매일 확인 시각에 새 코드를 받아 등록·판정하고 공식버전을 발행합니다. "
                    f"실행 줄에 `{ENV_VAR}=1` 이 있는 앱에서만 돕니다."
                ),
            )
            with st.container(horizontal=True, gap="small"):
                check_time = st.time_input(
                    "확인 시각",
                    value=config.check_time,
                    step=60,
                    width=160,
                    help="사내 PC 시계(OS 시각) 기준입니다. 매일 이 시각에 한 번 돕니다.",
                )
                keyword = st.text_input(
                    "시뮬레이션명 키워드",
                    value=config.keyword,
                    max_chars=MAX_KEYWORD_LENGTH,
                    width=240,
                    help=(
                        "시뮬레이션명에 이 글자(대소문자 무시)와 주차(W##)가 함께 있는 코드만 "
                        "받습니다."
                    ),
                )
                threshold_percent = st.number_input(
                    "기준 확보율(%)",
                    value=round(config.threshold * 100, 4),
                    min_value=MIN_THRESHOLD * 100,
                    max_value=MAX_THRESHOLD * 100,
                    step=1.0,
                    format="%.1f",
                    width=180,
                    help=(
                        "리비전 전체 기간에서 한 달이라도 원 확보율(가용 ÷ 소요)이 이 값 "
                        "**미만**인 공정을 공정 필터에서 끕니다. 같으면 남깁니다. 소요가 0 인 "
                        "달은 보지 않습니다."
                    ),
                )
            with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
                submitted = st.form_submit_button(
                    "설정 저장", icon=":material/save:", type="primary"
                )
                changed_by = st.text_input(
                    "바꾼 사람(선택)",
                    value="",
                    placeholder="이름을 적으면 설정 변경 기록에 남습니다",
                    width=280,
                )
        notice = render_flash(SETTINGS_FLASH_KEY)
        refused = take_refusal(SETTINGS_SAVE_NAME)
        if refused is not None:
            notice.error(refused)
    if not submitted:
        # 이 회차가 그린 저장본이 사용자가 본 화면이다 — 제출·충돌 회차에는 적지 않는다
        # (write_guard).
        remember_seen(SETTINGS_BASE_VERSION_KEY, settings.version)
        return
    # 표지 dict 는 저장 전에 받아 둔다 — 거부 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
    save_marks = own_save_marks()
    conflict_marks = profile_conflict_marks()
    messages = notice_marks()
    held = held_profile_conflict(conflict_marks, SETTINGS_SAVE_NAME)
    if held is not None:
        # 남의 저장에 거부된 누름의 둘째 누름이다 — 옛 화면의 입력이라 저장하지 않고 그 거부를 다시
        # 알린다(write_guard). 「바뀐 값이 없습니다」로도 바꾸지 않는다. 이 회차가 거부 회차의 글을
        # 이미 꺼내 그렸으면 한 번만(Proc Rename·표시순서와 같은 꼴). 본 version 은 이 회차가 그린
        # 최신 저장본으로 적는다 — 둘째 누름이 끊은 거부 뒤 회차 몫(2026-10-27 E2E).
        remember_seen(SETTINGS_BASE_VERSION_KEY, settings.version)
        if refused != held:
            notice.error(held)
        return
    if not isinstance(submitted_base, int):
        # 편집을 시작한 version 을 모른다 — 지금 version 으로 대체하면 남의 저장을 모르는 채 덮는다.
        # 다음 회차(제출 아님)가 최신을 그리며 본 version 을 적는다.
        queue_refusal(SETTINGS_SAVE_NAME, SEEN_MISSING_MESSAGE)
        st.rerun()
    expected_version = submitted_base
    try:
        updated = AutoUpdateConfig(
            enabled=bool(enabled),
            check_time=check_time,
            keyword=str(keyword),
            threshold=round(float(threshold_percent), 4) / 100,
        )
    except ValueError as exc:
        notice.error(bootstrap_error_message(exc))
        return
    if updated == config and expected_version == settings.version:
        # 방금 저장한 같은 값의 둘째 누름(새 화면이 서고 나서 닿은 느린 더블클릭)이면 알림 칸
        # (`render_flash`)이 방금 성공을 이미 다시 그렸다 — 「바뀐 값이 없습니다」 로 그 알림을
        # 덮지도 겹쳐 쓰지도 않는다(write_guard.held_notice).
        if held_notice(SETTINGS_FLASH_KEY) is None:
            notice.info("바뀐 값이 없습니다.")
        return
    if updated.enabled and not config.enabled:
        # 켜기 전에 막는다 — 주차 없는 공식버전과는 「더 새 코드」를 견줄 수 없다.
        try:
            current_official_baseline(repository)
        except MissingOfficialWeek as exc:
            notice.error(bootstrap_error_message(exc), icon=":material/error:")
            return
        except BOOTSTRAP_ERRORS as exc:
            notice.error(bootstrap_error_message(exc))
            return
    try:
        saved = repository.replace_auto_official_update_settings(
            updated,
            expected_version=expected_version,
            changed_by=str(changed_by),
            source=SETTINGS_SOURCE,
        )
    except AutoOfficialUpdateSettingsConflict as exc:
        _settings_conflict(repository, exc, expected_version, save_marks, conflict_marks)
    except BOOTSTRAP_ERRORS as exc:
        # 검증 실패는 ValueError 이고 원문이 무엇을 할지 말한다(물결표만 막아 그대로). 본 version 은
        # 그대로 둔다.
        notice.error(bootstrap_error_message(exc))
        return
    else:
        remember_own_save(SETTINGS_SAVE_NAME, expected_version, saved.version, save_marks)
        message = f"{SETTINGS_SAVED_PREFIX} — {describe_config_change(config, updated)}"
        # 빠른 두 번 누름의 둘째가 이 알림을 다시 낸다(write_guard.held_notice).
        note_notice(messages, SETTINGS_FLASH_KEY, message)
        queue_flash(SETTINGS_FLASH_KEY, message)
        st.rerun()


def _settings_conflict(
    repository: DuckDBScenarioRepository,
    exc: AutoOfficialUpdateSettingsConflict,
    expected_version: int,
    save_marks: Mapping[str, tuple[SeenToken, SeenToken]],
    conflict_marks: dict[str, tuple[str, float]],
) -> None:
    """설정 저장의 버전 충돌. 제 저장(빠른 두 번 누름의 둘째)이면 성공을, 아니면 거부를 다음
    회차에 그린다.

    충돌 예외는 지금 version 을 싣지 않아 저장본을 다시 읽어 짝을 맞춘다. 어느 쪽이든 이 회차는 본
    version 을 올리지 않고 앱을 다시 돌린다 — 다음 회차(제출 아님)가 최신을 그리며 적는다.
    """
    try:
        stored: int | None = repository.load_auto_official_update_settings().version
    except BOOTSTRAP_ERRORS:
        stored = None
    if is_own_save(SETTINGS_SAVE_NAME, expected_version, stored, save_marks):
        # 같은 단추의 빠른 두 번 누름이다 — 첫 누름이 이미 저장했다(write_guard). 첫 누름의 알림을
        # 다시 낸다(창이 지났으면 짧은 글).
        queue_flash(
            SETTINGS_FLASH_KEY, held_notice(SETTINGS_FLASH_KEY) or f"{SETTINGS_SAVED_PREFIX}."
        )
    else:
        # 충돌 글도 원문이 무엇을 할지 말한다(물결표만 막아 그대로 — 거부 알림은 마크다운으로 간다).
        message = bootstrap_error_message(exc)
        note_profile_conflict(conflict_marks, SETTINGS_SAVE_NAME, message)
        queue_refusal(SETTINGS_SAVE_NAME, message)
    st.rerun()


# ---------------------------------------------------------------------------
# 지금 실행
# ---------------------------------------------------------------------------


def _render_run_now(
    repository: DuckDBScenarioRepository,
    *,
    sources: AutoUpdateSources | None,
    clock: Clock,
) -> None:
    with st.container(border=True):
        st.markdown("#### :material/play_circle: 지금 실행")
        st.caption(
            "예약과 같은 회차를 지금 한 번 돕니다 — 새 코드가 있으면 등록·판정하고 공식버전을 "
            "발행합니다. 켜짐·실행 줄 허락과 상관없이 돌고 결과는 아래 실행 기록에 남습니다. "
            "같은 날 예약 회차와는 따로 셉니다(이미 받은 코드는 다시 받지 않습니다). 사내 조회와 "
            "전체 기간 계산이라 몇십 초 걸릴 수 있습니다."
        )
        clicked = st.button(
            "지금 실행", key=RUN_NOW_BUTTON_KEY, icon=":material/play_arrow:", type="secondary"
        )
        notice = st.container()
        with notice:
            _render_run_result(repository)
    if not clicked:
        return
    try:
        # 실행할 때도 먼저 막는다. 회차를 잡지 않으므로 기록도 남지 않는다.
        current_official_baseline(repository)
    except MissingOfficialWeek as exc:
        notice.error(bootstrap_error_message(exc), icon=":material/error:")
        return
    except BOOTSTRAP_ERRORS as exc:
        notice.error(bootstrap_error_message(exc))
        return
    token = uuid4().hex[:12]
    # 회차 **전에** 적는다. 도는 사이 다른 칸을 누르면 Streamlit 은(`runner.fastReruns`, 기본값) 이
    # 실행에 멈춤만 걸고 새 실행을 곧바로 띄운다. 회차는 이 스레드에서 끝까지 돌지만 그 뒤 첫
    # Streamlit 호출에서 멈춰 아래 결과 알림을 그리지 못한다 — 새 실행이 이 표로 기록을 찾아, 아직
    # 도는 중이면 끝날 때까지 기록을 다시 보고(`_poll_running_round`) 끝나면 결과를 대신 보인다.
    st.session_state[PENDING_RUN_TOKEN_KEY] = token
    try:
        with notice, st.spinner("자동 갱신 회차를 돌리는 중입니다..."):
            result = run_auto_official_update(
                repository,
                trigger=TRIGGER_MANUAL,
                sources=sources,
                clock=clock,
                after_publish=clear_global_securement_threshold_cache,
                manual_token=token,
            )
    except BOOTSTRAP_ERRORS as exc:
        st.session_state.pop(PENDING_RUN_TOKEN_KEY, None)
        notice.error(bootstrap_error_message(exc))
        return
    st.session_state.pop(PENDING_RUN_TOKEN_KEY, None)
    run = result.run
    if run is None:
        notice.warning(result.not_run_reason or "회차를 잡지 못했습니다.")
        return
    _hold_run_result(run)
    st.rerun()


def _hold_run_result(run: AutoOfficialUpdateRun) -> None:
    """끝난 「지금 실행」 회차의 결과를 다음 회차 알림 자리에 맡긴다.

    발행한 회차는 사유 끝에 이어 적힌 소요대수에 들지 않은 수요 경고를 갈라 `warning` 에 따로 둔다
    — 화면 발행처럼 성공 알림 밑의 경고로 띄운다(`_render_run_result`).
    """
    reason, warning = run.reason or "", ""
    if run.status == STATUS_PUBLISHED:
        # 이 세션의 입장 화면 Summary 가 새 공식버전을 다음 회차에 곧바로 싣는다.
        forget_intro_summary_check()
        reason, warning = split_published_reason(reason)
    kind, icon = _RUN_RESULT_STYLES.get(run.status, ("info", None))
    # 사유는 회차 기록(표 칸 — 평문)과 같은 글이라 짓는 곳(`_RunLog.finish`)이 아니라 알림 칸에
    # 담는 여기서 막는다 — 저장한 시나리오 이름·원천 시뮬레이션명을 날로 담는다.
    queue_flash(
        RUN_RESULT_KEY,
        markdown_safe_tildes(_run_result_text(run, reason)),
        kind=kind,
        icon=icon,
    )
    if warning:
        # 허락하면서 하는 경고는 화면 발행(`scenario_management`)과 같이 성공 알림 밑에 따로 띄운다.
        queue_flash(
            RUN_WARNING_KEY,
            markdown_safe_tildes(warning),
            kind="warning",
            icon=":material/warning:",
        )


def _recover_run_result(repository: DuckDBScenarioRepository) -> bool:
    """결과 알림이 rerun 에 끊긴 「지금 실행」 회차를 표로 찾는다. 아직 도는 중이면 True.

    끝난 회차면 표를 지우고 그 결과를 알림 칸에 담는다(`_hold_run_result`) — 부르는 쪽이 같은 회차에
    그린다.
    """
    token = st.session_state.get(PENDING_RUN_TOKEN_KEY)
    if not isinstance(token, str):
        return False
    try:
        run = repository.find_manual_auto_official_update_run(token)
    except BOOTSTRAP_ERRORS:
        return False
    if run is not None and run.status == STATUS_RUNNING:
        return True
    st.session_state.pop(PENDING_RUN_TOKEN_KEY, None)
    if run is not None:
        _hold_run_result(run)
    return False


def _run_result_text(run: AutoOfficialUpdateRun, reason: str) -> str:
    label = STATUS_LABELS.get(run.status, run.status)
    return f"{TRIGGER_LABELS.get(run.trigger_kind, run.trigger_kind)} 회차 — {label}. {reason}"


def _render_run_result(repository: DuckDBScenarioRepository) -> None:
    """「지금 실행」 결과 알림 한 칸. 담아 둔 결과가 없으면 끊긴 회차를 기록에서 찾는다 — 아직 도는
    중이면 결과 대신 「도는 중」 안내를 두고 기록을 다시 본다(`_poll_running_round`)."""
    if pending_flash(RUN_RESULT_KEY) is None and _recover_run_result(repository):
        _poll_running_round(repository)
        return
    render_flash(RUN_RESULT_KEY, RUN_WARNING_KEY)


@st.fragment(run_every=RUN_POLL_INTERVAL, key=RUN_POLL_FRAGMENT_KEY)
def _poll_running_round(repository: DuckDBScenarioRepository) -> None:
    """끊긴 「지금 실행」 회차가 도는 동안 안내를 두고 기록을 다시 본다. 끝나면 앱 전체를 돌린다.

    회차를 돌던 실행은 끊겨 끝난 뒤에도 다시 돌지 않으므로, 가만히 두면 「도는 중」 이 다음
    클릭까지 남았다. 앱 전체 실행의 `_recover_run_result` 가 표를 지우고 결과 알림 + 따로 띄운
    경고를 그리며, 그 실행은 이 프래그먼트를 그리지 않아 다시 보기도 멈춘다. 기록을 못 읽은 회는
    다음 간격에 다시 본다.
    """
    token = st.session_state.get(PENDING_RUN_TOKEN_KEY)
    still_running = False
    if isinstance(token, str):
        try:
            run = repository.find_manual_auto_official_update_run(token)
            still_running = run is not None and run.status == STATUS_RUNNING
        except BOOTSTRAP_ERRORS:
            still_running = True
    if still_running:
        st.info(RUNNING_MESSAGE, icon=":material/hourglass_top:")
        return
    st.rerun()


# ---------------------------------------------------------------------------
# 기록
# ---------------------------------------------------------------------------


def _render_run_history(
    runs: Sequence[AutoOfficialUpdateRun],
    exclusions: Sequence[AutoOfficialUpdateExclusion],
    labels: ProcessLabels,
) -> None:
    with st.container(border=True):
        st.markdown("#### :material/history: 실행 기록")
        if not runs:
            st.caption("아직 돈 회차가 없습니다.")
            return
        st.caption(f"최근 {RUN_HISTORY_LIMIT}회차까지 · 최근 것이 위")
        st.dataframe(run_history_frame(runs, exclusions, labels), hide_index=True, width="stretch")
        offs = off_process_frame(runs, exclusions, labels)
        with st.expander(
            f"off 공정 목록 · {len(offs):,}건",
            icon=":material/filter_alt_off:",
            key=OFF_LIST_EXPANDER_KEY,
        ):
            if offs.empty:
                st.caption("off 한 공정이 없습니다.")
            else:
                st.dataframe(offs, hide_index=True, width="stretch")


def run_history_frame(
    runs: Sequence[AutoOfficialUpdateRun],
    exclusions: Sequence[AutoOfficialUpdateExclusion],
    labels: ProcessLabels,
) -> pd.DataFrame:
    """실행 기록 표. 한 회차 한 줄 — off 공정은 최저 확보율·그 달과 함께 한 칸에 적는다.

    발행한 회차의 사유 끝에 소요대수에 들지 않은 수요 경고가 이어 적혔으면 「결과」 바로 뒤 「경고」
    칸에 표지를 둔다 — 사유는 맨 끝 칸이라 넓은 표에서 그 경고가 잘린다. 사유는 전체 글 그대로다.
    """
    by_run: dict[str, list[AutoOfficialUpdateExclusion]] = {}
    for exclusion in exclusions:
        by_run.setdefault(exclusion.run_id, []).append(exclusion)
    rows = []
    for run in runs:
        mine = by_run.get(run.run_id, [])
        auto = [exclusion for exclusion in mine if exclusion.kind == EXCLUSION_AUTO]
        inherited = [exclusion for exclusion in mine if exclusion.kind != EXCLUSION_AUTO]
        rows.append(
            {
                "시작": format(run.started_at, DATETIME_FORMAT),
                "방식": TRIGGER_LABELS.get(run.trigger_kind, run.trigger_kind),
                "결과": _status_text(run),
                "경고": _warning_text(run),
                "받은 코드": _received_text(run),
                "등록 시나리오": run.created_scenario_name or EMPTY,
                "자동 off": _off_text(
                    run.auto_off_count,
                    [
                        f"{labels.label(exclusion.process)} "
                        f"{auto_off_mark(exclusion.min_rate, exclusion.min_month)}"
                        for exclusion in auto
                    ],
                ),
                "이어받은 수동 off": _off_text(
                    run.inherited_off_count,
                    [labels.label(exclusion.process) for exclusion in inherited],
                ),
                "발행": EMPTY
                if run.official_release_no is None
                else f"공식 v{run.official_release_no}",
                "기준": f"「{run.keyword}」 · {percent_text(run.threshold)}",
                "사유": run.reason or EMPTY,
            }
        )
    return pd.DataFrame(rows)


def off_process_frame(
    runs: Sequence[AutoOfficialUpdateRun],
    exclusions: Sequence[AutoOfficialUpdateExclusion],
    labels: ProcessLabels,
) -> pd.DataFrame:
    """회차별 off 공정 한 줄씩 — 구분(자동 / 이어받은 수동)·최저 확보율·그 달."""
    started = {run.run_id: run.started_at for run in runs}
    rows = [
        {
            "회차 시작": format(started[exclusion.run_id], DATETIME_FORMAT),
            "공정": labels.label(exclusion.process),
            "구분": "자동 off" if exclusion.kind == EXCLUSION_AUTO else "이어받은 수동 off",
            "표지": (
                auto_off_mark(exclusion.min_rate, exclusion.min_month)
                if exclusion.kind == EXCLUSION_AUTO
                else EMPTY
            ),
            "최저 확보율": (
                EMPTY if exclusion.min_rate is None else f"{exclusion.min_rate * 100:.1f}%"
            ),
            "그 달": EMPTY if exclusion.min_month is None else str(exclusion.min_month),
            "리비전 2 저장": "예" if exclusion.filtered_revision_id else "아니오",
        }
        for exclusion in exclusions
        if exclusion.run_id in started
    ]
    rows.sort(key=lambda row: str(row["회차 시작"]), reverse=True)
    return pd.DataFrame(
        rows,
        columns=["회차 시작", "공정", "구분", "표지", "최저 확보율", "그 달", "리비전 2 저장"],
    )


def _status_text(run: AutoOfficialUpdateRun) -> str:
    label = STATUS_LABELS.get(run.status, run.status)
    if run.status == STATUS_RUNNING:
        return f"{label} · {STAGE_LABELS.get(run.stage, run.stage)}"
    return label


def _warning_text(run: AutoOfficialUpdateRun) -> str:
    if run.status != STATUS_PUBLISHED:
        return EMPTY
    _, warning = split_published_reason(run.reason or "")
    return UNCOUNTED_DEMAND_MARK if warning else EMPTY


def _received_text(run: AutoOfficialUpdateRun) -> str:
    if run.simulation_code is None:
        return EMPTY
    week = EMPTY if run.simulation_week is None else week_label(run.simulation_week)
    return f"{week} {run.simulation_code}"


def _off_text(count: int | None, names: Sequence[str]) -> str:
    if count is None:
        return EMPTY
    if not names:
        return f"{count}공정"
    return f"{count}공정 · " + ", ".join(names)


def _render_setting_history(changes: Sequence[AutoOfficialUpdateSettingChange]) -> None:
    with st.container(border=True):
        st.markdown("#### :material/manage_history: 설정 변경 기록")
        if not changes:
            st.caption("아직 설정을 바꾼 적이 없습니다.")
            return
        st.dataframe(setting_history_frame(changes), hide_index=True, width="stretch")


def setting_history_frame(changes: Sequence[AutoOfficialUpdateSettingChange]) -> pd.DataFrame:
    """설정 변경 기록 표 — 언제·누가(선택)·무엇을 바꿨는지. 최근 것이 위다."""
    rows = [
        {
            "시각": format(change.changed_at, DATETIME_FORMAT),
            "바꾼 사람": change.changed_by or EMPTY,
            "바꾼 내용": change.change_text,
            "판": f"v{change.version}",
        }
        for change in changes
    ]
    return pd.DataFrame(rows, columns=["시각", "바꾼 사람", "바꾼 내용", "판"])


# ---------------------------------------------------------------------------
# HOME 공정 필터 표지
# ---------------------------------------------------------------------------


def load_auto_off_marks(database_path: str) -> dict[str, str]:
    """이 세션에 올라온 리비전(과 조상)에서 자동 갱신이 뺀 공정 → `자동 off(확보율 n%, YY.MM)`.

    HOME 공정 필터 팝업을 여는 회차에만 부른다. 읽지 못해도 팝업은 열려야 해서 빈 표지로 돌아간다.
    """
    scenario_id = active_persisted_scenario_id()
    revision_id = active_persisted_revision_id()
    if scenario_id is None or revision_id is None:
        return {}
    try:
        return auto_off_marks(get_scenario_repository(database_path), scenario_id, revision_id)
    except BOOTSTRAP_ERRORS:
        return {}
