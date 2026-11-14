# Purpose: Admin 「DB 동기화」 펼침과 동기화 상태 알림(`SY-*`)을 그린다.

"""DB 동기화.

운영 서버는 영속 볼륨이 없어 정본이 버킷에 있다. 이 화면은 **CI/CD 를 누르기 전에 보는 자리**다 —
올릴 것이 남았는지, 마지막으로 언제 올렸는지, 왜 못 올리는지. 펼침 제목 끝 배지 하나가 지금 CI/CD 를
눌러도 되는지 판정한다(`CICD_VERDICTS` — 2026-11-14 「앱 대신 뜨는 화면」 보드 카드 p2-sync).

`managed` 가 아닌 서버(개발 PC · 사내 PC · 시험)에서는 펼침이 없고 Streamlit 호출도 없다 — 요소
순번이 그대로다. 값은 일꾼의 메모리 사본만 읽어 디스크 · 네트워크를 쓰지 않고, 주소 · 버킷 · 키를
싣지 않아 리뷰 압축본에 그대로 옮길 수 있다(갈래 낱말 · 수 · 시각뿐).

「지금 올리기」 는 통합인증이 켜진 서버의 관리자 회차에만 있다(`access_store.is_admin`). 콜백은 그
회차 쿠키의 신원을 다시 보고(접속 명단과 같은 꼴) 일꾼에 요청만 넣고 바로 돌아온다 — 올리는 시간을
화면이 기다리지 않는다.

상태 알림은 `app.py` 가 `GL-02` 곁 한 자리에서 부른다(`render_object_sync_alerts`). 프래그먼트 ·
팝업 안에서 부르지 않는다.

**누구나 읽는 짧은 글 · 관리자 몫 전문**(2026-11-14 「앱 대신 뜨는 화면」 보드 카드
p1-not-canonical). 짧은 글은 누구나 읽는 꼴이고, 일반 사용자가 할 수 없는 지시(C-DEP 환경변수 칸 ·
CI/CD · 설정 파일)는 관리자 몫 전문에만 싣는다(`admin_view.admin_notes_visible` — 운영 아닌 꺼진
서버는 누구에게나). 정본 점검을 못 한 서버(`SY-06`)는 일반 사용자가 할 일이 없어 관리자 몫에만
세운다 — 정본이 아닌 것이 확인되면 `SY-05` 가 선다. 정본이 아닌 데이터로 뜬 서버(`SY-05` ·
`SY-01`)는 머리 띠에 상시 표지 「정본 아님」 이 선다(`not_canonical_code` — 알림 칸이 그린다, 누르면
Alarm 의 그 줄). 저장은 막지 않는다(2026-11-07 결정 그대로).
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Final

import streamlit as st

from capa_simulation import alerts, object_sync_worker, sync_boot
from capa_simulation.audit import recorder as audit_recorder
from capa_simulation.audit import shipper as audit_shipper
from capa_simulation.audit import spool as audit_spool
from capa_simulation.components import sso_identity
from capa_simulation.components.admin_view import admin_notes_visible
from capa_simulation.components.diagnostic_copy import (
    diagnostic_text,
    plain_lines,
    render_diagnostic_copy,
)
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.navigation import ADMIN_AREA
from capa_simulation.object_sync_worker import (
    TITLE_BLOCKED,
    TITLE_CLEAN,
    TITLE_DIRTY,
    TITLE_FAILED,
    TITLE_UPLOADING,
    SyncHealth,
    WorkerStatus,
    assess,
)
from capa_simulation.page_bootstrap import ADMIN_TAIL
from capa_simulation.page_tabs_state import tab_label
from capa_simulation.persistence import sync_state
from capa_simulation.services.object_storage_manifest import (
    DATASET_LABELS,
    DATASET_NAMES,
    FAILURE_LABELS,
    FAILURE_WORKER_ABSENT,
    PushDecision,
    origin_tail,
)
from capa_simulation.sidebar_status import note_periodic_fragment, remembered_expander

EXPANDER_KEY: Final = "admin_area_object_sync"
COPY_KEY: Final = "object_sync"
UPLOAD_NOW_KEY: Final = "admin_area_object_sync_upload_now"
FLASH_KEY: Final = "admin_area_object_sync_flash"
# 펼침이 서 있는 동안 값을 다시 보는 간격과 그 프래그먼트의 key.
REFRESH_SECONDS: Final = 5
LIVE_FRAGMENT_KEY: Final = "admin_area_object_sync_live"
DISABLED_CODE: Final = "SY-01"
OVERDUE_CODE: Final = "SY-02"
BLOCKED_CODE: Final = "SY-03"
HANDED_OVER_CODE: Final = "SY-04"
HEAD_IGNORED_CODE: Final = "SY-05"
HEAD_UNCHECKED_CODE: Final = "SY-06"
_MIB: Final = 1024 * 1024

NOT_ADMIN_MESSAGE: Final = "관리자만 지금 올리기를 쓸 수 있습니다"
NO_WORKER_MESSAGE: Final = "동기화 일꾼이 돌지 않아 올리지 못했습니다"
UPLOADING_WHY: Final = "올리는 중입니다"
BLOCKED_LABELS: Final[dict[str, str]] = {
    PushDecision.PARENT_MOVED.value: "원격이 앞섬",
    PushDecision.FORKED.value: "원격이 갈라짐",
    PushDecision.BLOCKED_UNPUBLISHED.value: "게시하지 못한 세대가 있음",
    PushDecision.REMOTE_EMPTY.value: "원격이 비어 있음",
    PushDecision.UNKNOWN_BASE.value: "이 DB 의 세대를 모름",
}


def current_health() -> tuple[WorkerStatus | None, SyncHealth]:
    status = object_sync_worker.current_status()
    return status, assess(status, sync_state.mark_clock(), time.monotonic())


def failure_label(kind: str | None) -> str:
    return "" if kind is None else FAILURE_LABELS.get(kind, kind)


def not_canonical_code() -> str | None:
    """정본이 아닌 데이터로 뜬 서버면 그 알림 코드 — 정본을 받지 않음(`SY-05`)이 먼저, 동기화 꺼짐
    (`SY-01`)이 다음이다. 아니면 None. 값은 프로세스에 한 번 정한 것뿐이라 회차마다 같다(머리 띠
    「정본 아님」 표지 — 알림 칸 data)."""
    if not sync_boot.sync_alerts_possible():
        return None
    if sync_boot.head_ignored():
        return HEAD_IGNORED_CODE
    if sync_boot.sync_disabled_reason() is not None:
        return DISABLED_CODE
    return None


# 일꾼이 서지 않은 서버의 관리자 몫 전문 끝 한 줄(카드 p2-sync).
WORKER_ABSENT_LINE: Final = "일꾼이 돌지 않음 — CI/CD 를 누르면 이 서버의 저장은 사라짐."


def _overdue_full(overdue: str, *, admin: bool) -> str:
    """`SY-02` 전문 — 관리자 몫은 갈래 · 할 일 · (일꾼이 없으면) 그 한 줄, 아니면 누구나 꼴."""
    if not admin:
        return (
            "저장이 정본에 올라가지 못했습니다 — 이대로 배포하면 그 저장은 사라집니다. 관리자에게 "
            "알려 주세요."
        )
    text = (
        f"저장이 정본에 올라가지 못했습니다 — {failure_label(overdue)}. 이대로 CI/CD 를 누르면 그 "
        "저장은 사라집니다. Admin 「DB 동기화」 를 보세요."
    )
    return f"{text} {WORKER_ABSENT_LINE}" if overdue == FAILURE_WORKER_ABSENT else text


# 누구나 읽는 짧은 글(카드 p1-not-canonical).
DISABLED_SHORT: Final = "저장이 정본에 올라가지 않습니다"
HEAD_IGNORED_SHORT: Final = "정본이 아닌 데이터 — 여기 저장은 다음 배포에 사라집니다"


def render_object_sync_alerts() -> None:
    """동기화 상태 알림 여섯. `app.py` 가 회차마다 조건 없이 부른다.

    알릴 일이 있을 수 없는 프로세스(`sync_alerts_possible` 이 거짓 — 프로세스에 한 번 정한 값)에서는
    표지도 쓰지 않는다. 개발 PC · 시험의 요소 순번이 그대로다. 관리자 몫 판정은 한 번 본다 —
    관리자가 아닌 회차에도 같은 수의 표지를 쓴다(조건만 거짓).
    """
    if not sync_boot.sync_alerts_possible():
        return
    admin = admin_notes_visible()
    reason = sync_boot.sync_disabled_reason()
    alerts.state(
        DISABLED_CODE,
        scope=None,
        content=reason,
        active=reason is not None,
        text=None if reason is None else DISABLED_SHORT,
        full=(
            None
            if reason is None
            else (
                f"동기화 꺼짐 — {reason}. 저장은 이 서버의 DB 에만 남습니다. 설정"
                "(CAPA_S3_SYNC_MODE · config/object_storage.json)을 고친 뒤 다시 띄우세요."
            )
            if admin
            else (
                "저장이 정본에 올라가지 않습니다 — 동기화가 꺼진 서버라 여기서 저장한 것은 이 "
                "서버에만 남고 다음 배포에 사라질 수 있습니다. 관리자에게 알려 주세요."
            )
        ),
    )
    managed = sync_boot.is_managed()
    health = current_health()[1] if managed else None
    # 관리자 몫 줄의 「그 화면으로」 — Admin 「DB 동기화」 펼침(Admin Area 맨 위). 관리자가 아닌
    # 회차는 그 화면이 없을 수 있어 달지 않는다.
    to_panel = (tab_label(ADMIN_AREA), ADMIN_AREA.href) if admin else None
    overdue = None if health is None else health.overdue
    alerts.state(
        OVERDUE_CODE,
        scope=None,
        content=overdue,
        active=overdue is not None,
        text=(
            None
            if overdue is None
            else f"저장이 정본에 올라가지 못함 — {failure_label(overdue)}"
            if admin
            else f"저장이 정본에 올라가지 못함{ADMIN_TAIL}"
        ),
        full=None if overdue is None else _overdue_full(overdue, admin=admin),
        goto=to_panel if overdue is not None else None,
    )
    blocked = None if health is None else health.blocked
    label = "" if blocked is None else BLOCKED_LABELS.get(blocked, blocked)
    alerts.state(
        BLOCKED_CODE,
        scope=None,
        content=blocked,
        active=blocked is not None,
        text=(
            None
            if blocked is None
            else f"올리기가 멈춤 — {label}"
            if admin
            else f"올리기가 멈춤{ADMIN_TAIL}"
        ),
        full=(
            None
            if blocked is None
            else (
                f"올리기가 멈췄습니다 — {label}. 이 뒤의 저장은 이 서버에만 남습니다. 런북 「세대 "
                "되돌리기」 를 보고 CI/CD 전에 알려 주세요."
            )
            if admin
            else (
                "올리기가 멈췄습니다 — 이 뒤의 저장은 이 서버에만 남고 다음 배포에 사라질 수 "
                "있습니다. 관리자에게 알려 주세요."
            )
        ),
        goto=to_panel if blocked is not None else None,
    )
    handed_over = sync_boot.handed_over_utc()
    alerts.state(
        HANDED_OVER_CODE,
        scope=None,
        content=None,
        active=handed_over is not None,
        text=None if handed_over is None else "이 DB 는 정본을 넘긴 사본입니다",
        full=(
            None
            if handed_over is None
            else (
                f"이 DB 는 {handed_over} 에 정본을 넘긴 사본입니다. 여기서 저장해도 정본에 "
                "올라가지 않습니다. 최신 데이터를 보려면 사본을 다시 받습니다(런북)."
            )
        ),
    )
    head_ignored = sync_boot.head_ignored()
    alerts.state(
        HEAD_IGNORED_CODE,
        scope=None,
        content=None,
        active=head_ignored,
        text=HEAD_IGNORED_SHORT,
        full=(
            (
                "버킷에 세대가 있는데 CAPA_S3_SYNC_MODE 칸이 managed 가 아니어서(비었거나 local) "
                "받지 않았습니다. 지금 화면은 정본이 아니고 여기서 저장한 것은 다음 CI/CD 에 "
                "사라집니다. 칸에 managed 를 넣고 CI/CD 를 다시 누르세요."
            )
            if admin
            else (
                "이 서버는 정본을 받지 않고 떴습니다. 지금 화면은 정본이 아니고 여기서 저장한 것은 "
                "다음 배포에 사라집니다 — 관리자에게 알려 주세요."
            )
        ),
    )
    # 일반 사용자는 이 알림으로 할 일이 없다 — 관리자 몫에만 선다(정본이 아닌 것이 확인되면
    # `SY-05`).
    unchecked = " · ".join(sync_boot.head_unchecked())
    alerts.state(
        HEAD_UNCHECKED_CODE,
        scope=None,
        content=unchecked or None,
        active=bool(unchecked) and admin,
        text=None if not unchecked else f"정본 점검 못 함 — CD 환경변수 {unchecked} 없음",
        full=(
            None
            if not unchecked
            else (
                f"C-DEP 환경변수 표에 {unchecked} 칸이 없어 시작 점검이 버킷에 정본이 있는지 보지 "
                "못했습니다. 정본이 있는데 받지 않은 서버라면 여기서 저장한 것은 다음 CI/CD 에 "
                "사라집니다. 표에 넣고 CI/CD 를 다시 누르세요(Admin 「서버 시작 점검」 동기화 줄)."
            )
        ),
    )


def _clock_text(value: str | None) -> str:
    """UTC 글 → 서버 시각대 글. 못 읽으면 받은 글 그대로."""
    if value is None:
        return "없음"
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return moment.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OverflowError, OSError):
        return value


def status_lines(status: WorkerStatus | None, health: SyncHealth, *, now: float) -> list[str]:
    """펼침 본문 — 라벨 · 값 줄(UI-TXT-01). 값은 갈래 · 수 · 시각뿐이다."""
    if status is None:
        return [f"**까닭** · {failure_label(health.overdue)}"]
    # 시작 펜스(받기 끝에 같은 멤버로 낸 세대)면 번호 뒤 꼬리 — 저장 없이 는 세대다(UI-TXT-04 표지).
    generation = "없음" if status.seq is None else f"{status.seq}{origin_tail(status.origin)}"
    lines = [
        f"**마지막 올림** · {_clock_text(status.last_success_utc)}",
        f"**세대** · {generation}",
    ]
    changed = [DATASET_LABELS[name] for name in DATASET_NAMES if status.dirty.get(name)]
    lines.append(f"**변경 있는 DB** · {' · '.join(changed) if changed else '없음'}")
    if status.sizes:
        sizes = " · ".join(
            f"{DATASET_LABELS[name]} {size / _MIB:.1f} MiB" for name, size in status.sizes.items()
        )
        lines.append(f"**올린 크기** · {sizes}")
    if status.lock_seconds is not None:
        lines.append(f"**복사 잠금** · {status.lock_seconds:.2f}초")
    if status.transfer_seconds is not None:
        lines.append(f"**전송** · {status.transfer_seconds:.1f}초")
    if status.failures:
        lines.append(f"**연속 실패** · {status.failures}회 · {failure_label(status.failure_kind)}")
    if health.blocked is not None:
        lines.append(f"**멈춘 까닭** · {BLOCKED_LABELS.get(health.blocked, health.blocked)}")
    if status.next_try_at is not None:
        lines.append(f"**다음 시도** · {max(status.next_try_at - now, 0):.0f}초 뒤")
    if status.last_prune_utc is not None:
        lines.append(
            f"**마지막 정리** · {_clock_text(status.last_prune_utc)} · "
            f"{status.last_prune_deleted}개 지움"
        )
    if status.prune_failure is not None:
        lines.append(f"**정리 실패** · {failure_label(status.prune_failure)}")
    if audit_recorder.enabled():
        # 접속 · 작업 감사 기록 — CI/CD 앞 「지금 올리기」 뒤 0 이어야 그 pod 의 기록이 남는다.
        # 아직 열린 시간 묶음(닫히면 한 줄씩)도 센다.
        lines.append(f"**감사 미전송** · {audit_spool.unsent_count()}줄")
        audit = audit_shipper.health()
        if audit.failures:
            lines.append(
                f"**감사 올리기 실패** · {audit.failures}회 · {failure_label(audit.failure_kind)}"
            )
    return lines


def _viewer_is_admin() -> bool:
    """관리자 판정 한 벌(`sso_identity.viewer_is_admin`)을 부른다 — 시험이 이 이름을 바꿔 끼운다."""
    return sso_identity.viewer_is_admin()


def _upload_now() -> None:
    """「지금 올리기」 콜백 — 위젯 콜백은 본문보다 먼저 돌아 보인 회차의 권한을 믿지 않는다. 거부는
    그 자리에 고칠 입력이 없어 알림창 · Alarm 에만 낸다(설계 규칙 UI-NTF-03)."""
    if not _viewer_is_admin():
        audit_recorder.record("admin_sync_push", out="denied", det={"result": "not_admin"})
        queue_flash(FLASH_KEY, NOT_ADMIN_MESSAGE, kind="error", popup_only=True)
        return
    worker = object_sync_worker.running_worker()
    if worker is None:
        audit_recorder.record("admin_sync_push", out="fail", det={"result": "no_worker"})
        queue_flash(FLASH_KEY, NO_WORKER_MESSAGE, kind="error", popup_only=True)
        return
    # 줄을 먼저 넣고 깨운다 — 일꾼이 그 올리기 앞에 한 번 더 비우므로 이 줄이 같은 올리기에 실린다.
    audit_recorder.record("admin_sync_push", det={"result": "requested"})
    worker.request_now()
    queue_flash(FLASH_KEY, "올리기를 시작했습니다")


def panel_title(health: SyncHealth) -> str:
    return f"DB 동기화 · {health.title}"


# 펼침 제목 끝 판정 표지 — 지금 CI/CD 를 눌러도 되는가(카드 p2-sync, 설계 규칙 UI-DAT-03 · UI-ACC-03
# — 색 + 낱말). 올릴 것이 없으면 눌러도 되고, 올리는 중 · 올릴 것이 있으면 기다리고, 실패 · 멈춤 ·
# 일꾼 없음이면 누르는 순간 이 서버의 저장을 잃는다. 멈춤을 푸는 단추는 두지 않는다(결정 C3 그대로).
CICD_VERDICTS: Final[dict[str, tuple[str, str]]] = {
    TITLE_CLEAN: ("green", "CI/CD 눌러도 됨"),
    TITLE_DIRTY: ("orange", "기다리세요"),
    TITLE_UPLOADING: ("orange", "기다리세요"),
    TITLE_FAILED: ("red", "누르면 저장 잃음"),
    TITLE_BLOCKED: ("red", "누르면 저장 잃음"),
}


def cicd_verdict(health: SyncHealth) -> tuple[str, str]:
    """(색, 낱말) — 모르는 판정은 기다리라고 한다."""
    return CICD_VERDICTS.get(health.title, ("orange", "기다리세요"))


def panel_label(health: SyncHealth) -> str:
    """펼침 제목 — 판정 제목 끝에 CI/CD 판정 배지(마크다운 지시문). 복사 글은 `panel_title` 평문 +
    판정 낱말이다."""
    color, word = cicd_verdict(health)
    return f"{panel_title(health)} :{color}-badge[{word}]"


def _is_uploading(status: WorkerStatus | None) -> bool:
    return status is not None and status.phase == object_sync_worker.PHASE_UPLOADING


def _render_body(status: WorkerStatus | None, health: SyncHealth) -> None:
    """값 줄과 그 글을 복사하는 단추 — 다시 그려도 복사 글이 화면과 같다."""
    lines = status_lines(status, health, now=time.monotonic())
    title = f"{panel_title(health)} · {cicd_verdict(health)[1]}"
    render_diagnostic_copy(diagnostic_text(title, plain_lines(lines)), key=COPY_KEY)
    st.caption("  \n".join(lines))


@st.fragment(run_every=REFRESH_SECONDS, key=LIVE_FRAGMENT_KEY)
def _render_live_body(drawn_label: str, drawn_uploading: bool) -> None:
    """펼침이 서 있는 동안 늘 값을 다시 그린다(접혀 있어도 — 제목 배지가 판정이다). 알림 표지는
    이 안에서 내지 않는다(AGENTS 9장).

    제목(CI/CD 판정 배지)과 「지금 올리기」 잠금은 앱 회차가 그린다. 그린 때와 판정 · 잠금이
    달라지면 — 다른 회차의 저장 · 올리기 시작과 끝 · 실패 — 앱 회차로 돌아가 함께 고친다. 그린
    순간 값에 머물면 연 채 둔 화면이 다른 회차의 저장 뒤에도 초록 「CI/CD 눌러도 됨」 을 보인다.
    """
    status, health = current_health()
    if panel_label(health) != drawn_label or _is_uploading(status) != drawn_uploading:
        st.rerun(scope="app")
    _render_body(status, health)


def render_object_sync_status() -> None:
    """Admin 「DB 동기화」 펼침. `managed` 가 아니면 아무것도 부르지 않는다(모듈 설명)."""
    if not sync_boot.is_managed():
        return
    status, health = current_health()
    uploading = _is_uploading(status)
    label = panel_label(health)
    with remembered_expander(label, icon=":material/cloud_sync:", key=EXPANDER_KEY):
        if _viewer_is_admin():
            st.button(
                "지금 올리기",
                icon=":material/cloud_upload:",
                key=UPLOAD_NOW_KEY,
                disabled=uploading,
                help=UPLOADING_WHY if uploading else None,
                on_click=_upload_now,
            )
        render_flash(FLASH_KEY)
        _render_live_body(label, uploading)
    # 이 페이지의 여닫기 · 팝업 열기가 시계를 멈추지 않게(`note_periodic_fragment`).
    note_periodic_fragment()
