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
# 줄의 등급 칸 — 사람 넷(`auth/grades.GRADES` 의 높은 차례) · 앱 자신 · 없음. 옛 줄의 `admin` ·
# `user` 는 읽기 표시에서 「개발자(옛 기록)」 · 「일반(옛 기록)」 이다(`LEGACY_GRADE_LABELS`).
GRADES: Final = ("developer", "manager", "editor", "viewer", "system", "none")
LEGACY_GRADES: Final = ("admin", "user")

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
# 시간 묶음 한 줄 — 건수 표 · 합계 · 묶은 시간 · 정시 전에 앞당겨 닫았는가.
_SUMMARY: Final = ("counts", "total", "hour", "partial")

SPECS: Final[tuple[EventSpec, ...]] = (
    # --- 접속 ---------------------------------------------------------------------------------
    _spec("authn_login_success", "access", "로그인", "hours", "max_hours"),
    _spec("authn_login_fail", "access", "로그인 실패", "reason", lvl="warn"),
    _spec(
        "authn_login_fail_summary",
        "access",
        "로그인 전 실패(시간 묶음)",
        *_SUMMARY,
        lvl="warn",
    ),
    _spec("authn_username_missing", "access", "계정 클레임 없음", "claim", lvl="warn"),
    _spec("authz_fail_access_list", "access", "명단 밖 접속", "reason", lvl="warn"),
    # 등급 때문에 막힌 누름 — 누가(행위자) · 무엇(동작) · 필요한 등급 · 지금 등급. 로그인이 끝나
    # 막힌
    # 것은 따로 적는다(값 원문 없음 — 2026-11-18 접속 등급 결정 30).
    _spec("authz_fail_grade", "access", "등급 때문에 막힘", "action", "need", "have", lvl="warn"),
    _spec("authz_fail_signin", "access", "로그인 끝나 막힘", "action", "reason", lvl="warn"),
    _spec(
        "authz_fail_access_list_summary",
        "access",
        "명단 밖 접속(시간 묶음)",
        "total",
        "accounts",
        "hour",
        "partial",
        lvl="warn",
    ),
    _spec("session_created", "access", "세션 시작"),
    _spec("session_logout", "access", "로그아웃"),
    _spec("session_expired", "access", "만료로 닫힘", "end"),
    _spec("session_revoked", "access", "폐기로 닫힘", "reason"),
    _spec("authz_fail_session", "access", "명단에서 빠져 끊김", "reason", lvl="warn"),
    _spec("session_invalid", "access", "쿠키 이상으로 닫힘", "reason", lvl="warn"),
    _spec("session_renew_summary", "access", "로그인 갱신(시간 묶음)", *_SUMMARY),
    # --- 관리 ---------------------------------------------------------------------------------
    _spec("user_created", "admin", "명단 추가", *_REV),
    _spec("user_deleted", "admin", "명단 삭제", *_REV),
    _spec("user_self_registered", "admin", "스스로 등록", *_REV),
    _spec("user_grade_changed", "admin", "등급 바꿈", "grade_from", "grade_to", *_REV),
    _spec("user_bulk_dropped", "admin", "못 읽는 항목 정리", "count", *_REV),
    _spec("user_seeded", "admin", "명단 첫 판 심기", "count", *_REV),
    _spec("authz_admin_config", "admin", "개발자 구성", "admins", "admin_fp"),
    _spec("admin_token_set", "admin", "BigDataQuery 토큰 넣기", "result", "expires"),
    # 결과 · 까닭과 로그인 하위 프로세스 진단(`container_start_report.ChildDiag.fields` — 수 ·
    # 이름 · 판 · 메모리 단서(`MEMORY_FIELDS` — MiB · 수)만, 계정 · 비밀번호 없음).
    _spec(
        "admin_bdq_login_set",
        "admin",
        "BigDataQuery 자동 로그인 계정 넣기",
        "result",
        "reason",
        "exit",
        "signal",
        "sec",
        "stage",
        "stderr",
        "bigdataquery",
        "getpass_asterisk",
        "cg_before",
        "cg_after",
        "cg_max",
        "oom_before",
        "oom_after",
        "rss_before",
        "rss_after",
        "kid_peak",
    ),
    _spec("admin_bdq_login_delete", "admin", "BigDataQuery 자동 로그인 계정 지우기", "result"),
    _spec("admin_sync_push", "admin", "지금 올리기", "result"),
    _spec("admin_sync_rollback", "admin", "세대 되돌리기", *_SEQ, "result"),
    _spec("admin_sync_init", "admin", "이관", *_SEQ, "result", "datasets"),
    _spec("admin_fetch_copy", "admin", "사본 받기", "seq_to", "result"),
    _spec("admin_sync_prune", "admin", "수동 정리", "deleted", "result"),
    _spec("admin_auto_update_settings", "admin", "자동 갱신 설정", "fields", *_VERSION),
    _spec("admin_auto_update_run", "admin", "자동 갱신 수동 실행", "run_id", "status"),
    # 공지 — 대상은 공지 id(`tgt`), 상세는 결과 · 끝 시각뿐이고 글은 싣지 않는다.
    _spec("admin_notice_send", "admin", "공지 보냄", "result", "until"),
    _spec("admin_notice_withdraw", "admin", "공지 거둠", "result"),
    # 부대공정 판 — 갈래(적용 · 끄기 · 다시 켜기) · 이력 차례 · 판 번호 · 공정 수뿐이고 공정 이름 ·
    # 생산성 값은 싣지 않는다.
    _spec("admin_extra_process", "admin", "부대공정 판", "kind", "entry", "version", "processes"),
    # 부대공정 판의 S3 Drive 파일 쓰기 — 결과(씀 · 덮지 않음 · 실패) · 쓴 판의 이력 차례 ·
    # 기록 차례뿐.
    _spec(
        "admin_extra_process_write",
        "admin",
        "부대공정 판 S3 Drive 쓰기",
        "result",
        "version_entry",
        "entry",
    ),
    # --- 작업 ---------------------------------------------------------------------------------
    _spec("data_scenario_create", "data", "시나리오 만들기", "source", "rows"),
    _spec("data_scenario_rename", "data", "시나리오 이름 바꾸기"),
    _spec("data_scenario_reorder", "data", "시나리오 순서 바꾸기", "rows"),
    _spec("data_scenario_archive", "data", "시나리오 보관", "home_cleared"),
    _spec("data_scenario_restore", "data", "시나리오 되살리기"),
    _spec("data_scenario_delete", "data", "시나리오 삭제", lvl="warn"),
    _spec("data_revision_save", "data", "리비전 저장", "scenario", "parent", "tables"),
    _spec("data_revision_rename", "data", "리비전 이름 바꾸기"),
    _spec("data_official_publish", "data", "공식 발행", "release_no", "revision"),
    _spec("data_auto_update_exclusions", "data", "자동 갱신 제외 기록", "run_id", "rows"),
    _spec("data_profile_save", "data", "공용 설정 저장", "profile", "version_to", "source", "rows"),
    _spec("data_voc_post", "data", "VOC 글"),
    _spec("data_voc_reply", "data", "VOC 답글"),
    _spec("data_voc_resolve", "data", "VOC 답변 표시", "resolved"),
    _spec("data_voc_delete", "data", "VOC 글 지우기", "deleted"),
    _spec(
        "data_equipment_save",
        "data",
        "설비 저장",
        "source",
        "rows",
        "schedule_revision",
        "release_no",
        "propagated",
    ),
    _spec("data_layout_save", "data", "Space 배치 저장", "source", "rows", "schedule_revision"),
    _spec("data_equipment_scenario_clone", "data", "설비 시나리오 복제", "source"),
    _spec("data_equipment_scenario_rename", "data", "설비 시나리오 이름 바꾸기"),
    _spec("data_equipment_publish", "data", "설비 공식 발행", "schedule_revision"),
    _spec("data_schedule_rename", "data", "일정 리비전 이름 바꾸기"),
    _spec("data_schedule_restore", "data", "일정 리비전 되돌리기", "schedule_revision"),
    _spec("data_layout_overlay_clear", "data", "가정 배치 차이 지우기"),
    _spec("data_downtime_save", "data", "입력 비가동 저장", "rows"),
    _spec("data_baseline_save", "data", "단축 기준선 저장"),
    _spec("data_baseline_delete", "data", "단축 기준선 지우기", "deleted"),
    _spec("data_cutoff_save", "data", "Cut-off 저장", "rows"),
    _spec("data_target_save", "data", "표준 목표 저장", "rows"),
    _spec("data_target_clear", "data", "표준 목표 지우기"),
    _spec("data_floor_state_save", "data", "층 사용 저장", "rows"),
    _spec("data_drawing_save", "data", "Space 도면 저장", "rows"),
    _spec("data_shortening_filter_save", "data", "필요 단축 기본 조회 조건 저장", "field", "rows"),
    _spec("data_legacy_trace_ack", "data", "옛 배포 흔적 이어 쓰기", "count"),
    # 모듈 화면의 운영 서버 파일 올리기 · 공용 BigDataQuery 조회 — 대상은 모듈 id, 상세는 결과 낱말
    # ·
    # 크기 · 행 수만(파일 이름 · 조회문 없음).
    _spec("data_module_upload", "data", "모듈 파일 올리기", "result", "bytes"),
    _spec("data_module_query", "data", "모듈 BigDataQuery 조회", "result", "rows"),
    # --- 시스템 -------------------------------------------------------------------------------
    _spec("sys_startup", "system", "앱 시작", "env", "sso", "sync", "spool"),
    _spec("sys_boot_pull", "system", "시작 받기", "action", "seq", "seconds"),
    _spec("sys_cert_expiring", "system", "서명 인증서 만료 임박", "days", lvl="warn"),
    _spec("sys_access_read_fail", "system", "접속 명단 읽기 실패", "reason", "status", lvl="warn"),
    _spec("sys_access_save_fail", "system", "접속 명단 저장 실패", "reason", "status", lvl="warn"),
    _spec("sys_grade_read_fail", "system", "등급 파일 읽기 실패", "reason", "status", lvl="warn"),
    _spec("sys_grade_save_fail", "system", "등급 파일 저장 실패", "reason", "status", lvl="warn"),
    _spec("sys_sync_fail", "system", "DB 올리기 실패", "kind", "failures", lvl="warn"),
    _spec("sys_sync_blocked", "system", "DB 올리기 멈춤", "decision", lvl="warn"),
    _spec("sys_sync_summary", "system", "DB 올리기(시간 묶음)", *_SUMMARY),
    _spec("sys_clock_skew", "system", "시계 차이", "seconds", lvl="warn"),
    _spec("sys_audit_dropped", "system", "기록 못 한 줄", "count", lvl="crit"),
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

# 상세(`det`) 키의 한글 표시명 — 기록 보기 「상세」 칸이 쓴다. 허용 키를 더하면 여기에도 더한다
# (`trunc` 는 기록기가 1KB 를 넘겨 줄였을 때 붙인다). 시험이 허용 키 전부와 맞댄다.
DET_LABELS: Final[Mapping[str, str]] = {
    "accounts": "계정",
    "action": "동작",
    "admin_fp": "개발자 지문",
    "admins": "개발자 수",
    "bigdataquery": "bigdataquery 판",
    "bytes": "바이트",
    "cg_after": "cgroup 뒤(MiB)",
    "cg_before": "cgroup 앞(MiB)",
    "cg_max": "cgroup 한도(MiB)",
    "claim": "클레임",
    "count": "수",
    "counts": "건수",
    "datasets": "DB",
    "date": "날짜",
    "days": "남은 날",
    "decision": "판정",
    "deleted": "지움",
    "end": "끝",
    "end_mark": "끝 표지",
    "env": "실행 자리",
    "exit": "종료",
    "expires": "만료",
    "failures": "실패 수",
    "field": "칸",
    "fields": "칸",
    "getpass_asterisk": "getpass_asterisk 판",
    "grade_from": "등급 전",
    "grade_to": "등급",
    "have": "지금 등급",
    "home_cleared": "HOME 지정 비움",
    "hour": "시간",
    "hours": "유지(시간)",
    "key": "조각",
    "kid_peak": "하위 최고 RSS(MiB)",
    "kind": "갈래",
    "entry": "이력 줄",
    "max_hours": "최대 유지(시간)",
    "name": "사건 이름",
    "need": "필요 등급",
    "oom_after": "OOM 종료 뒤",
    "oom_before": "OOM 종료 앞",
    "parent": "부모 리비전",
    "partial": "앞당겨 닫음",
    "prev_h": "앞 해시",
    "prev_inst": "앞 인스턴스",
    "prev_seq": "앞 순번",
    "profile": "설정",
    "propagated": "함께 넣은 시나리오",
    "reason": "사유",
    "release_no": "발행 번호",
    "resolved": "답변 완료",
    "processes": "공정 수",
    "result": "결과",
    "rev_from": "판 전",
    "rev_to": "판",
    "revision": "리비전",
    "rows": "행",
    "rss_after": "앱 RSS 뒤(MiB)",
    "rss_before": "앱 RSS 앞(MiB)",
    "run_id": "실행",
    "scenario": "시나리오",
    "schedule_revision": "일정 리비전",
    "sec": "걸린 초",
    "seconds": "초",
    "seq": "세대",
    "seq_from": "세대 전",
    "seq_to": "세대",
    "signal": "시그널",
    "source": "출처",
    "spool": "스풀",
    "sso": "통합인증",
    "stage": "단계",
    "status": "상태",
    "stderr": "오류 종류",
    "sync": "동기화",
    "tables": "표",
    "total": "합계",
    "trunc": "줄임",
    "until": "끝 시각",
    "version": "판",
    "version_entry": "판 이력 줄",
    "version_from": "판 전",
    "version_to": "판",
}
# 등급 칸 · 상세 등급 값의 표시 — 사람 넷은 등급 이름, 옛 줄의 값은 「(옛 기록)」 을 단다.
GRADE_VALUE_LABELS: Final[Mapping[str, str]] = {
    "developer": "개발자",
    "manager": "관리자",
    "editor": "실무자",
    "viewer": "열람",
    "system": "앱",
    "none": "-",
    "admin": "개발자(옛 기록)",
    "user": "일반(옛 기록)",
}
# 참 · 거짓 값의 표시(상세 칸).
YES_NO: Final[Mapping[bool, str]] = {True: "예", False: "아니오"}
# 명단 판 전 = 후인 줄(쓰지 못한 실패)의 표시 — 두 칸 대신 「판 n(그대로)」 한 칸(상세 칸).
SAME_REVISION_MARK: Final = "(그대로)"


def spec_of(name: str) -> EventSpec | None:
    return SPEC_BY_NAME.get(name)


def label_of(name: str) -> str:
    """화면에 보일 한글 표시명. 목록 밖이면 원본 이름 그대로."""
    spec = SPEC_BY_NAME.get(name)
    return name if spec is None else spec.label
