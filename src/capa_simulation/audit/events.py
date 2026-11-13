# Purpose: 감사 사건 목록 — 이름 · 갈래 · 한글 표시명 · 허용 상세 키 · 결과 · 수준을 한곳에 둔다.

"""감사 사건 목록(표준 라이브러리만).

사건 이름은 OWASP Logging Vocabulary 꼴(`갈래_동작`, 영문 소문자와 `_`)이다. 화면은 한글 표시명을,
CSV 는 원본 이름을 싣는다. 목록 밖 이름은 기록기가 `sys_audit_bad_event` 로 바꾼다. 상세(`det`)는
사건마다 허용 키만 남긴다 — 값 원문 · 자유 글을 막는 첫 그물이다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

CATEGORIES: Final[Mapping[str, str]] = {
    "access": "접속",
    "admin": "관리",
    "data": "작업",
    "export": "내보내기",
    "audit": "기록 열람",
    "system": "시스템",
}
OUTCOMES: Final[Mapping[str, str]] = {
    "success": "성공",
    "fail": "실패",
    "denied": "거부",
    "unknown": "결과 모름",
}
LEVELS: Final = ("info", "warn", "crit")
GRADES: Final = ("admin", "auditor", "user", "system", "none")

BAD_EVENT: Final = "sys_audit_bad_event"


@dataclass(frozen=True)
class EventSpec:
    """사건 한 가지 — 이름 · 갈래 · 표시명 · 허용 상세 키 · 기본 수준."""

    name: str
    cat: str
    label: str
    det_keys: frozenset[str] = frozenset()
    lvl: str = "info"


def _spec(name: str, cat: str, label: str, *det: str, lvl: str = "info") -> EventSpec:
    return EventSpec(name, cat, label, frozenset(det), lvl)


_REV: Final = ("rev_from", "rev_to")
_SEQ: Final = ("seq_from", "seq_to")
_VERSION: Final = ("version_from", "version_to")

SPECS: Final[tuple[EventSpec, ...]] = (
    # --- 접속 ---------------------------------------------------------------------------------
    _spec("authn_login_success", "access", "로그인", "hours", "max_hours"),
    _spec("authn_login_fail", "access", "로그인 실패", "reason", lvl="warn"),
    _spec(
        "authn_login_fail_summary",
        "access",
        "로그인 전 실패(시간 묶음)",
        "counts",
        "total",
        "hour",
        lvl="warn",
    ),
    _spec("authn_username_missing", "access", "계정 클레임 없음", "claim", lvl="warn"),
    _spec("authz_fail_access_list", "access", "명단 밖 접속", "reason", lvl="warn"),
    _spec(
        "authz_fail_access_list_summary",
        "access",
        "명단 밖 접속(시간 묶음)",
        "total",
        "accounts",
        "hour",
        lvl="warn",
    ),
    _spec("session_created", "access", "세션 시작"),
    _spec("session_logout", "access", "로그아웃"),
    _spec("session_expired", "access", "만료로 닫힘", "end"),
    _spec("session_revoked", "access", "폐기로 닫힘", "reason"),
    _spec("authz_fail_session", "access", "명단에서 빠져 끊김", "reason", lvl="warn"),
    _spec("session_invalid", "access", "쿠키 이상으로 닫힘", "reason", lvl="warn"),
    _spec("session_renew_summary", "access", "로그인 갱신(시간 묶음)", "counts", "total", "hour"),
    # --- 관리 ---------------------------------------------------------------------------------
    _spec("user_created", "admin", "명단 추가", *_REV),
    _spec("user_deleted", "admin", "명단 삭제", *_REV),
    _spec("user_bulk_dropped", "admin", "못 읽는 항목 정리", "count", *_REV),
    _spec("user_seeded", "admin", "명단 첫 판 심기", "count", *_REV),
    _spec("authz_admin_config", "admin", "관리자 구성", "admins", "admin_fp", "auditors"),
    _spec("admin_token_set", "admin", "BigDataQuery 토큰 넣기", "result", "expires"),
    _spec("admin_sync_push", "admin", "지금 올리기", "result"),
    _spec("admin_sync_rollback", "admin", "세대 되돌리기", *_SEQ, "result"),
    _spec("admin_sync_init", "admin", "이관", *_SEQ, "result", "datasets"),
    _spec("admin_fetch_copy", "admin", "사본 받기", "seq_to", "result"),
    _spec("admin_sync_prune", "admin", "수동 정리", "deleted", "result"),
    _spec("admin_auto_update_settings", "admin", "자동 갱신 설정", "fields", *_VERSION),
    _spec("admin_auto_update_run", "admin", "자동 갱신 수동 실행", "run_id", "status"),
    # --- 작업 ---------------------------------------------------------------------------------
    _spec("data_scenario_create", "data", "시나리오 만들기", "source", "rows"),
    _spec("data_scenario_rename", "data", "시나리오 이름 바꾸기"),
    _spec("data_scenario_archive", "data", "시나리오 보관"),
    _spec("data_scenario_restore", "data", "시나리오 되살리기"),
    _spec("data_scenario_delete", "data", "시나리오 삭제", lvl="warn"),
    _spec("data_revision_save", "data", "리비전 저장", "parent", "tables"),
    _spec("data_revision_rename", "data", "리비전 이름 바꾸기"),
    _spec("data_official_publish", "data", "공식 발행", "release_no", "revision"),
    _spec("data_auto_update_exclusions", "data", "자동 갱신 제외 기록", "run_id", "rows"),
    _spec("data_profile_save", "data", "공용 설정 저장", "profile", "version_to", "source", "rows"),
    _spec("data_voc_post", "data", "VOC 글"),
    _spec("data_voc_reply", "data", "VOC 답글"),
    _spec("data_voc_resolve", "data", "VOC 답변 표시", "resolved"),
    _spec("data_voc_delete", "data", "VOC 글 지우기"),
    _spec("data_equipment_save", "data", "설비 저장", "source", "rows", "schedule_revision"),
    _spec("data_layout_save", "data", "Space 배치 저장", "schedule_revision"),
    _spec("data_equipment_scenario_clone", "data", "설비 시나리오 복제", "source"),
    _spec("data_equipment_scenario_rename", "data", "설비 시나리오 이름 바꾸기"),
    _spec("data_equipment_publish", "data", "설비 공식 발행", "schedule_revision"),
    _spec("data_schedule_rename", "data", "일정 리비전 이름 바꾸기"),
    _spec("data_schedule_restore", "data", "일정 리비전 되돌리기", "schedule_revision"),
    _spec("data_layout_overlay_clear", "data", "가정 배치 차이 지우기"),
    _spec("data_downtime_save", "data", "입력 비가동 저장", "rows"),
    _spec("data_baseline_save", "data", "단축 기준선 저장"),
    _spec("data_baseline_delete", "data", "단축 기준선 지우기"),
    _spec("data_cutoff_save", "data", "Cut-off 저장", "rows"),
    _spec("data_target_save", "data", "표준 목표 저장", "rows"),
    _spec("data_target_clear", "data", "표준 목표 지우기"),
    _spec("data_floor_state_save", "data", "층 사용 저장", "rows"),
    _spec("data_drawing_save", "data", "Space 도면 저장", "rows"),
    # --- 시스템 -------------------------------------------------------------------------------
    _spec("sys_startup", "system", "앱 시작", "env", "sso", "sync", "spool"),
    _spec("sys_boot_pull", "system", "시작 받기", "action", "seq", "seconds"),
    _spec("sys_cert_expiring", "system", "서명 인증서 만료 임박", "days", lvl="warn"),
    _spec("sys_access_read_fail", "system", "접속 명단 읽기 실패", "reason", "status", lvl="warn"),
    _spec("sys_access_save_fail", "system", "접속 명단 저장 실패", "reason", "status", lvl="warn"),
    _spec("sys_sync_fail", "system", "DB 올리기 실패", "kind", "failures", lvl="warn"),
    _spec("sys_sync_blocked", "system", "DB 올리기 멈춤", "decision", lvl="warn"),
    _spec("sys_sync_summary", "system", "DB 올리기(시간 묶음)", "counts", "total", "hour"),
    _spec("sys_clock_skew", "system", "시계 차이", "seconds", lvl="warn"),
    _spec("sys_audit_dropped", "system", "감사 기록 넘쳐 버림", "count", lvl="crit"),
    _spec("sys_audit_ship_fail", "system", "감사 기록 올리기 실패", "kind", "failures", lvl="warn"),
    _spec("sys_audit_bad_event", "system", "목록 밖 감사 사건", "name", lvl="warn"),
    _spec(
        "audit_chain_link",
        "system",
        "기록 사슬 잇기",
        "prev_inst",
        "prev_seq",
        "prev_h",
        "end_mark",
    ),
    _spec("audit_late_segment", "system", "늦게 온 기록 조각", "date", "key", lvl="crit"),
)

SPEC_BY_NAME: Final[Mapping[str, EventSpec]] = {spec.name: spec for spec in SPECS}


def spec_of(name: str) -> EventSpec | None:
    return SPEC_BY_NAME.get(name)


def label_of(name: str) -> str:
    """화면에 보일 한글 표시명. 목록 밖이면 원본 이름 그대로."""
    spec = SPEC_BY_NAME.get(name)
    return name if spec is None else spec.label
