# Purpose: 운영 진입점이 기동 때 한 번 감사 기록기를 켠다 — 통합인증이 켜진 서버만.

"""감사 기록기 기동(`capa_server.py` 가 `start_sso()` 바로 뒤에 부른다).

켜짐 판정은 여기 한 곳이다 — 통합인증 모드가 켜짐(`SsoMode.ON`)이면 켠다. 꺼짐 · 막힘이면 아무것도
하지 않는다(사내 PC · WebIDE · 시험 · `app.py` 개발 실행은 이 함수를 부르지 않거나 꺼짐이다). 끄는
환경변수는 두지 않는다.

켜면 줄 셋을 남긴다 — `sys_startup`(환경 · 판 · 통합인증 · 동기화 모드),
`authz_admin_config`(관리자 수 · 목록 지문 8자 — 사람 값은 싣지 않는다), 시작 받기
기록이 있으면 `sys_boot_pull`.
"""

from __future__ import annotations

import hashlib
import logging

from capa_simulation import settings, sync_boot
from capa_simulation.audit import recorder
from capa_simulation.auth import access_store
from capa_simulation.auth.access import GRADE_ADMIN
from capa_simulation.auth.config import SsoConfig, SsoMode

_LOGGER = logging.getLogger(__name__)

ENVIRONMENT = "cdep"


def deploy_version() -> str:
    """배포 표지 — 적용 기록의 stamp(앱 정보 카드와 같은 값), 없으면 앱 판 글."""
    from capa_simulation.components.app_credits import deployed_stamp

    try:
        return deployed_stamp() or settings.APP_VERSION
    except Exception:  # noqa: BLE001 — 판 글 하나로 기동이 멈추지 않는다
        return settings.APP_VERSION


def grader(cfg: SsoConfig) -> recorder.Grader:
    """loginid → `admin` · `user`. 관리자는 지금 명단(`access_store.is_admin`)."""

    def grade(loginid: str) -> str:
        return "admin" if access_store.is_admin(cfg, loginid) else "user"

    return grade


def admin_fingerprint(cfg: SsoConfig) -> str:
    admins = sorted(key for key, grade in cfg.access.grades.items() if grade == GRADE_ADMIN)
    return hashlib.sha256(",".join(admins).encode("utf-8")).hexdigest()[:8]


def start(cfg: SsoConfig) -> bool:
    """통합인증이 켜졌으면 기록기를 켜고 시작 줄을 남긴다. 켰는지 돌려준다(예외 없음)."""
    if cfg.mode is not SsoMode.ON:
        return False
    try:
        recorder.start(env=ENVIRONMENT, version=deploy_version(), inst=sync_boot.INSTANCE_ID)
        recorder.set_grader(grader(cfg))
        managed = sync_boot.is_managed()
        recorder.record(
            "sys_startup",
            actor="system:app",
            det={
                "env": ENVIRONMENT,
                "sso": cfg.mode.value,
                "sync": "managed" if managed else "local",
                "spool": "on",
            },
        )
        recorder.record(
            "authz_admin_config",
            actor="system:app",
            det={
                "admins": cfg.access.admin_count,
                "admin_fp": admin_fingerprint(cfg),
            },
        )
        boot = sync_boot.read_boot_record() if managed else None
        if boot is not None:
            recorder.record(
                "sys_boot_pull",
                actor="system:app",
                det={
                    "action": boot.action,
                    "seq": boot.seq,
                    "seconds": round(boot.pull_seconds, 1),
                },
            )
    except Exception:  # noqa: BLE001 — 기록기가 앱 기동을 막지 않는다
        _LOGGER.exception("감사 기록기를 켜지 못했습니다.")
    return recorder.enabled()
