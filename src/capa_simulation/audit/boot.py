# Purpose: 운영 진입점이 기동 때 한 번 감사 기록기를 켠다 — 통합인증이 켜진 서버만.

"""감사 기록기 기동(`capa_server.py` 가 `start_sso()` 바로 뒤에 부른다).

켜짐 판정은 여기 한 곳이다 — 통합인증 모드가 켜짐(`SsoMode.ON`)이면 켠다. 꺼짐 · 막힘이면 아무것도
하지 않는다(사내 PC · WebIDE · 시험 · `app.py` 개발 실행은 이 함수를 부르지 않거나 꺼짐이다). 끄는
환경변수는 두지 않는다.

켜면 줄 셋을 남긴다 — `sys_startup`(환경 · 판 · 통합인증 · 동기화 모드),
`authz_admin_config`(개발자 수 · 목록 지문 8자 — 사람 값은 싣지 않는다), 시작 받기
기록이 있으면 `sys_boot_pull`. 그 뒤 기록기가 켜지기 전에 지나간 기동 사건을 그 차례로 따라잡는다 —
진입 파일은 `start_sso()`(설정을 읽고 S3 명단을 한 번 읽는다) 다음에 이 함수를 불러, 그 안의 사건이
대응표에 닿지 못한다. 만료가 30일 안인 서명 인증서마다 `sys_cert_expiring` 한 줄
(`_note_expiring_certs` — 설정 읽기의 `cert_expiring`), 기동 명단 읽기가 실패한 서버면
`sys_access_read_fail` 한 줄(`_note_list_read_at_start`)이다. 오래 떠 있는 서버에서 뒤에 30일 안으로
들어온 인증서는 다음 기동에 남는다(화면은 `AD-03` 이 알린다).
"""

from __future__ import annotations

import hashlib
import logging

from capa_simulation import settings, sync_boot
from capa_simulation.audit import recorder
from capa_simulation.auth import access_store, grade_store, runtime
from capa_simulation.auth.access import GRADE_ADMIN
from capa_simulation.auth.config import SsoConfig, SsoMode

_LOGGER = logging.getLogger(__name__)

ENVIRONMENT = "cdep"


def deploy_version() -> str:
    """배포 표지 — 적용 기록의 stamp(앱 정보 카드와 같은 값), 없으면 앱 판 글."""
    from capa_simulation.deploy_stamp import deployed_stamp

    try:
        return deployed_stamp() or settings.APP_VERSION
    except Exception:  # noqa: BLE001 — 판 글 하나로 기동이 멈추지 않는다
        return settings.APP_VERSION


def grader(cfg: SsoConfig) -> recorder.Grader:
    """loginid → 접속 등급(`developer` · `manager` · `editor` · `viewer` —
    `grade_store.grade_of`)."""

    def grade(loginid: str) -> str:
        return grade_store.grade_of(cfg, loginid)

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
        _note_expiring_certs(cfg)
        _note_list_read_at_start(cfg)
    except Exception:  # noqa: BLE001 — 기록기가 앱 기동을 막지 않는다
        _LOGGER.exception("감사 기록기를 켜지 못했습니다.")
    return recorder.enabled()


def _note_expiring_certs(cfg: SsoConfig) -> None:
    """설정 읽기(`runtime.start`)가 낸 서명 인증서 만료 임박을 인증서마다 지금 대응표로 넘긴다.

    서버 로그의 `cert_expiring` 과 같은 판정 · 같은 남은 날(`runtime.expiring_certs`)이다. 통합인증
    켜짐이면 S3 명단과 상관없이 부른다.
    """
    for days, _ in runtime.expiring_certs(cfg):
        recorder.from_sso_event("cert_expiring", {"days": str(days)})


def _note_list_read_at_start(cfg: SsoConfig) -> None:
    """기동 명단 읽기(`access_store.read_at_start`)가 실패했으면 그 사건을 지금 대응표로 넘긴다.

    서버 로그 · 사건 고리의 `access_read` 실패와 같은 칸(사유 · 상태)이다. 기동 때 한 번만 부르므로
    뒤의 자가 회복 실패(누계만 — `runtime.ACCESS_RETRY_FAILED_EVENT`)와 겹치지 않는다.
    """
    if not access_store.is_on(cfg):
        return
    source = runtime.access_source()
    problem = None if source is None else source.problem
    if problem is None:
        return
    recorder.from_sso_event(
        "access_read", {"reason": problem.kind, "status": str(problem.status or "-")}
    )
