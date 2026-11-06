# Purpose: Admin 「DB 동기화」 펼침과 동기화 상태 알림(`SY-*`)을 그린다.

"""DB 동기화.

운영 서버는 영속 볼륨이 없어 정본이 버킷에 있다. 이 화면은 **CI/CD 를 누르기 전에 보는 자리**다 —
올릴 것이 남았는지, 마지막으로 언제 올렸는지, 왜 못 올리는지.

`managed` 가 아닌 서버(개발 PC · 사내 PC · 시험)에서는 펼침이 없고 Streamlit 호출도 없다 — 요소
순번이 그대로다. 값은 일꾼의 메모리 사본만 읽어 디스크 · 네트워크를 쓰지 않고, 주소 · 버킷 · 키를
싣지 않아 리뷰 압축본에 그대로 옮길 수 있다(갈래 낱말 · 수 · 시각뿐).

「지금 올리기」 는 통합인증이 켜진 서버의 관리자 회차에만 있다(`access_store.is_admin`). 콜백은 그
회차 쿠키의 신원을 다시 보고(접속 명단과 같은 꼴) 일꾼에 요청만 넣고 바로 돌아온다 — 올리는 시간을
화면이 기다리지 않는다.

상태 알림은 `app.py` 가 `GL-02` 곁 한 자리에서 부른다(`render_object_sync_alerts`). 프래그먼트 ·
팝업 안에서 부르지 않는다.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Final

import streamlit as st

from capa_simulation import alerts, object_sync_worker, sync_boot
from capa_simulation.auth import access_store, runtime
from capa_simulation.auth.config import SsoMode
from capa_simulation.components import sso_identity
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.object_sync_worker import SyncHealth, WorkerStatus, assess
from capa_simulation.persistence import sync_state
from capa_simulation.services.object_storage_manifest import (
    DATASET_LABELS,
    DATASET_NAMES,
    FAILURE_LABELS,
    PushDecision,
)
from capa_simulation.sidebar_status import remembered_expander

EXPANDER_KEY: Final = "admin_area_object_sync"
UPLOAD_NOW_KEY: Final = "admin_area_object_sync_upload_now"
FLASH_KEY: Final = "admin_area_object_sync_flash"
# 올리는 동안 펼침 안 값을 다시 그리는 간격.
REFRESH_SECONDS: Final = 5
DISABLED_CODE: Final = "SY-01"
OVERDUE_CODE: Final = "SY-02"
BLOCKED_CODE: Final = "SY-03"
HANDED_OVER_CODE: Final = "SY-04"
HEAD_IGNORED_CODE: Final = "SY-05"
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


def render_object_sync_alerts() -> None:
    """동기화 상태 알림 다섯. `app.py` 가 회차마다 조건 없이 부른다.

    알릴 일이 있을 수 없는 프로세스(`sync_alerts_possible` 이 거짓 — 프로세스에 한 번 정한 값)에서는
    표지도 쓰지 않는다. 개발 PC · 시험의 요소 순번이 그대로다.
    """
    if not sync_boot.sync_alerts_possible():
        return
    reason = sync_boot.sync_disabled_reason()
    alerts.state(
        DISABLED_CODE,
        scope=None,
        content=reason,
        active=reason is not None,
        text=None if reason is None else "동기화 꺼짐 — 저장이 정본에 올라가지 않습니다",
        full=(
            None
            if reason is None
            else (
                f"동기화 꺼짐 — {reason}. 저장은 이 서버의 DB 에만 남습니다. 설정"
                "(CAPA_S3_SYNC_MODE · config/object_storage.json)을 고친 뒤 다시 띄우세요."
            )
        ),
    )
    managed = sync_boot.is_managed()
    health = current_health()[1] if managed else None
    overdue = None if health is None else health.overdue
    alerts.state(
        OVERDUE_CODE,
        scope=None,
        content=overdue,
        active=overdue is not None,
        text=(
            None if overdue is None else f"저장이 정본에 올라가지 못함 — {failure_label(overdue)}"
        ),
        full=(
            None
            if overdue is None
            else (
                f"저장이 정본에 올라가지 못했습니다 — {failure_label(overdue)}. 이대로 CI/CD 를 "
                "누르면 그 저장은 사라집니다. Admin 「DB 동기화」 를 보세요."
            )
        ),
    )
    blocked = None if health is None else health.blocked
    label = "" if blocked is None else BLOCKED_LABELS.get(blocked, blocked)
    alerts.state(
        BLOCKED_CODE,
        scope=None,
        content=blocked,
        active=blocked is not None,
        text=None if blocked is None else f"올리기가 멈춤 — {label}",
        full=(
            None
            if blocked is None
            else (
                f"올리기가 멈췄습니다 — {label}. 이 뒤의 저장은 이 서버에만 남습니다. 런북 「세대 "
                "되돌리기」 를 보고 CI/CD 전에 알려 주세요."
            )
        ),
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
                "올라가지 않습니다."
            )
        ),
    )
    head_ignored = sync_boot.head_ignored()
    alerts.state(
        HEAD_IGNORED_CODE,
        scope=None,
        content=None,
        active=head_ignored,
        text="정본을 받지 않은 서버입니다 — 이 저장은 다음 CI/CD 에 사라집니다",
        full=(
            "버킷에 세대가 있는데 CAPA_S3_SYNC_MODE 칸이 비어 받지 않았습니다. 지금 화면은 "
            "정본이 아니고 여기서 저장한 것은 다음 CI/CD 에 사라집니다. 칸에 managed 를 넣고 "
            "CI/CD 를 다시 누르세요. 일부러 끈 서버면 local 을 넣습니다."
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
    lines = [
        f"**마지막 올림** · {_clock_text(status.last_success_utc)}",
        f"**세대** · {'없음' if status.seq is None else status.seq}",
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
    return lines


def _viewer_is_admin() -> bool:
    cfg = runtime.config()
    if cfg.mode is not SsoMode.ON:
        return False
    identity = sso_identity.verified_identity()
    return identity is not None and access_store.is_admin(cfg, identity.loginid)


def _upload_now() -> None:
    """「지금 올리기」 콜백 — 위젯 콜백은 본문보다 먼저 돌아 보인 회차의 권한을 믿지 않는다."""
    if not _viewer_is_admin():
        queue_flash(FLASH_KEY, NOT_ADMIN_MESSAGE, kind="error")
        return
    worker = object_sync_worker.running_worker()
    if worker is None:
        queue_flash(FLASH_KEY, NO_WORKER_MESSAGE, kind="error")
        return
    worker.request_now()
    queue_flash(FLASH_KEY, "올리기를 시작했습니다")


def _render_body() -> None:
    status, health = current_health()
    st.caption("  \n".join(status_lines(status, health, now=time.monotonic())))


@st.fragment(run_every=REFRESH_SECONDS)
def _render_live_body() -> None:
    """올리는 동안만 값을 다시 그린다. 알림 표지는 이 안에서 내지 않는다(AGENTS 9장).

    끝나면 앱 회차로 돌아가 제목 · 단추를 함께 고친다 — 이 프래그먼트도 그때 사라진다.
    """
    status = object_sync_worker.current_status()
    if status is None or status.phase != object_sync_worker.PHASE_UPLOADING:
        st.rerun(scope="app")
    _render_body()


def render_object_sync_status() -> None:
    """Admin 「DB 동기화」 펼침. `managed` 가 아니면 아무것도 부르지 않는다(모듈 설명)."""
    if not sync_boot.is_managed():
        return
    status, health = current_health()
    uploading = status is not None and status.phase == object_sync_worker.PHASE_UPLOADING
    with remembered_expander(
        f"DB 동기화 · {health.title}", icon=":material/cloud_sync:", key=EXPANDER_KEY
    ):
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
        if uploading:
            _render_live_body()
        else:
            _render_body()
