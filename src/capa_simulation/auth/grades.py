# Purpose: 접속 등급 넷 · 동작별 필요한 등급 · 감사 사건의 바닥 동작과 쓰는 순간의 벽을 한곳에 둔다.

"""접속 등급(열람 · 실무자 · 관리자 · 개발자)의 판정 한 곳(표준 라이브러리 + 감사 기록기만).

**등급 넷**(낮은 차례) — 열람 `viewer` · 실무자 `editor` · 관리자 `manager` · 개발자 `developer`.
화면 글은 `GRADE_LABELS` 하나에서 짓는다. 명단 파일(`access_store`)의 저장 값 `user` · `admin` 은
되돌림 안전 때문에 그대로이고(`admin` = 개발자) 이 모듈의 새 값에는 `admin` 을 쓰지 않는다.

**동작 표**(`ACTIONS`) — 동작 이름 → 필요한 등급 · 거절 글 조각. 감사 표지를 단 저장소 쓰기는
사건 이름 → 바닥 동작 표(`EVENT_FLOORS`)로 벽이 선다(`audit/work.py`). 한 사건이 여러 동작에
쓰이면 바닥(가장 낮은 것)을 두고 안쪽에서 더 높인다(설비 저장의 비가동 대조).

**누가 어느 등급인가**는 꽂아 둔 판정기(`install_caller_source` — `components/grade_ui.install` 이
`sso_identity.real_caller` 를 꽂는다)가 정한다. 꽂힌 것이 없는 프로세스(스크립트 · 저장소 시험)는
제한이 없다. 판정기가 실패하면 열람으로 읽는다(못 읽었다고 넓어지지 않는다).

**벽은 바깥 쓰기만 본다** — 표지를 단 함수가 표지를 단 다른 함수를 부르면 바깥 한 번만 판정한다.
깊이는 스레드 로컬이고 감사 기록기의 깊이와 따로다(기록기가 꺼진 운영 + 꺼짐에서도 벽이 서야 한다).
멈춤 · 다시 그리기 예외(`BaseException`)가 지나가도 `finally` 로 되돌린다.

**거절**은 감사 한 줄(`authz_fail_grade` · `authz_fail_signin`)을 남기고 예외를 던진다. 알림은 담지
않는다 — 잠금 안 쓰기에서도 불리고 세션 칸 쓰기는 끊길 수 있다(받는 자리가 담는다 —
`components/grade_ui`). 두 예외는 `Exception` 직속이다 — `PermissionError` 는 `OSError` 라 화면 공용
예외 튜플(`page_bootstrap.BOOTSTRAP_ERRORS`)에 삼켜진다.
"""

from __future__ import annotations

import functools
import logging
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final, Literal, ParamSpec, TypeVar

from capa_simulation.audit import recorder

_LOGGER = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

VIEWER: Final = "viewer"
EDITOR: Final = "editor"
MANAGER: Final = "manager"
DEVELOPER: Final = "developer"
# 낮은 차례.
GRADES: Final = (VIEWER, EDITOR, MANAGER, DEVELOPER)
# 등급 파일에 적는 값(열람 = 줄 없음, 개발자 = 명단 파일의 `admin`).
STORED_GRADES: Final = (EDITOR, MANAGER)
GRADE_LABELS: Final[Mapping[str, str]] = {
    VIEWER: "열람",
    EDITOR: "실무자",
    MANAGER: "관리자",
    DEVELOPER: "개발자",
}
ENV_DEVELOPER_LABEL: Final = "개발자(환경변수)"
# 배포를 적용하고 모듈을 승인하는 한 사람의 역할 이름 — 등급으로는 개발자다.
APP_MANAGER_ROLE: Final = "앱 관리자(개발자)"

# 감사 표지를 단 함수가 벽에 쓰는 동작 이름(`audit/work.py` · `gated`) — 그물이 읽는다.
GATE_ATTRIBUTE: Final = "__grade_action__"


def rank(grade: str) -> int:
    """등급의 차례(열람 0). 모르는 값은 열람이다."""
    return GRADES.index(grade) if grade in GRADES else 0


def at_least(have: str, need: str) -> bool:
    """`have` 가 `need` 이상인가."""
    return rank(have) >= rank(need)


def label_of(grade: str) -> str:
    """화면 글. 모르는 값은 열람의 글이다."""
    return GRADE_LABELS.get(grade, GRADE_LABELS[VIEWER])


@dataclass(frozen=True)
class Action:
    """동작 하나 — 이름 · 필요한 등급 · 거절 글 조각(「…할」 꼴)."""

    key: str
    need: str
    what: str


def _actions(*rows: tuple[str, str, str]) -> Mapping[str, Action]:
    return {key: Action(key, need, what) for key, need, what in rows}


ACTIONS: Final[Mapping[str, Action]] = _actions(
    ("voc.post", VIEWER, "VOC 글을 쓸"),
    ("voc.manage", DEVELOPER, "VOC 답변 표시 · 글 지우기를 할"),
    ("scenario.revision_save", EDITOR, "새 리비전을 저장할"),
    ("scenario.create", EDITOR, "새 시나리오를 저장할"),
    ("scenario.db_register", EDITOR, "DB 등록을 할"),
    ("scenario.list_edit", EDITOR, "시나리오 이름 · 차례를 바꿀"),
    ("scenario.archive", EDITOR, "시나리오를 보관하거나 되돌릴"),
    ("revision.rename", EDITOR, "리비전 이름을 바꿀"),
    ("scenario.delete", MANAGER, "시나리오를 영구 삭제할"),
    ("official.publish", MANAGER, "공식 지정을 할"),
    ("home.settings", MANAGER, "HOME 설정을 저장할"),
    ("shortening.baseline", EDITOR, "기준선을 남기거나 지울"),
    ("shortening.filter_default", MANAGER, "모두의 기본 조회 조건을 바꿀"),
    ("shortening.progress_log", EDITOR, "누적 진척 기록을 남기거나 고칠"),
    ("shortening.progress_goal", MANAGER, "누적 진척 최종 목표를 바꿀"),
    ("target.availability", MANAGER, "표준 목표 가용설비를 바꿀"),
    ("auto_update.view", MANAGER, "자동 갱신 탭을 볼"),
    ("auto_update.edit", DEVELOPER, "자동 갱신을 바꾸거나 실행할"),
    ("equipment.save", MANAGER, "설비 · Space 를 저장할"),
    ("equipment.downtime", EDITOR, "비가동 일정을 저장할"),
    ("equipment.manual_downtime", EDITOR, "입력 비가동을 저장할"),
    ("equipment.export", MANAGER, "설비 화면에서 내려받을"),
    ("equipment.scenario", MANAGER, "설비 시나리오를 만들거나 고칠"),
    ("equipment.publish", MANAGER, "설비 공식 지정을 할"),
    ("equipment.cutoff", MANAGER, "Cut-off 를 저장할"),
    ("equipment.legacy_ack", DEVELOPER, "옛 배포 흔적을 이어 쓸"),
    ("diag.full", DEVELOPER, "운영 진단 글을 볼"),
    ("admin.area", DEVELOPER, "Admin Area 를 쓸"),
)


def _floors(*rows: tuple[tuple[str, ...], str]) -> Mapping[str, str]:
    return {event: action for events, action in rows for event in events}


# 감사 사건 이름 → 바닥 동작. 표지를 단 쓰기는 이 표로 벽이 선다(시험이 모든 표지와 맞댄다).
EVENT_FLOORS: Final[Mapping[str, str]] = _floors(
    (("data_scenario_create",), "scenario.create"),
    (("data_scenario_rename", "data_scenario_reorder"), "scenario.list_edit"),
    (("data_scenario_archive", "data_scenario_restore"), "scenario.archive"),
    (("data_scenario_delete",), "scenario.delete"),
    (("data_revision_save",), "scenario.revision_save"),
    (("data_revision_rename",), "revision.rename"),
    (("data_official_publish",), "official.publish"),
    (("data_auto_update_exclusions",), "auto_update.edit"),
    (("data_profile_save",), "home.settings"),
    (("data_voc_post", "data_voc_reply"), "voc.post"),
    (("data_voc_resolve", "data_voc_delete"), "voc.manage"),
    # 바닥 — 저장소 안쪽의 내용 대조가 비가동 말고 바뀐 것이 있으면 `equipment.save` 를 다시 본다.
    (("data_equipment_save",), "equipment.downtime"),
    (("data_layout_save", "data_floor_state_save", "data_drawing_save"), "equipment.save"),
    (
        (
            "data_equipment_scenario_clone",
            "data_equipment_scenario_rename",
            "data_schedule_rename",
            "data_schedule_restore",
            "data_layout_overlay_clear",
        ),
        "equipment.scenario",
    ),
    (("data_equipment_publish",), "equipment.publish"),
    (("data_downtime_save",), "equipment.manual_downtime"),
    (("data_cutoff_save",), "equipment.cutoff"),
    (("data_target_save", "data_target_clear"), "target.availability"),
    (("data_baseline_save", "data_baseline_delete"), "shortening.baseline"),
    (("data_shortening_filter_save",), "shortening.filter_default"),
    (("data_progress_log_save", "data_progress_log_delete"), "shortening.progress_log"),
    (("data_progress_goal_save",), "shortening.progress_goal"),
    (("data_legacy_trace_ack",), "equipment.legacy_ack"),
)
# 바닥 표에 없는 사건의 벽 — 닫힌 쪽(개발자). 시험(`tests/test_grades.py`)이 빠짐을 막는다.
UNMAPPED_ACTION: Final = "admin.area"

SIGNED_OUT_TEXT: Final = "로그인이 끝나 저장하지 않았습니다 — 다시 로그인하세요"


def need_of(action: str) -> str:
    """그 동작에 필요한 등급. 모르는 이름이면 `KeyError`(시험이 막는다)."""
    return ACTIONS[action].need


def floor_of(event: str) -> str:
    """감사 사건의 바닥 동작 — 표에 없으면 닫힌 쪽(`UNMAPPED_ACTION`)."""
    return EVENT_FLOORS.get(event, UNMAPPED_ACTION)


def highest(actions: Iterable[str]) -> str | None:
    """필요한 등급이 가장 높은 동작(같으면 앞의 것). 비면 `None`."""
    chosen: str | None = None
    for action in actions:
        if chosen is None or rank(need_of(action)) > rank(need_of(chosen)):
            chosen = action
    return chosen


def refusal_text(action: str) -> str:
    """누른 순간 거절 글 — 「관리자부터 공식 지정을 할 수 있습니다」 · 「개발자만 … 수
    있습니다」."""
    item = ACTIONS[action]
    if item.need == DEVELOPER:
        return f"{GRADE_LABELS[DEVELOPER]}만 {item.what} 수 있습니다"
    return f"{GRADE_LABELS[item.need]}부터 {item.what} 수 있습니다"


def stop_text(action: str, *, place: Literal["page", "tab"]) -> str:
    """주소 · 알림으로 연 등급 밖 화면 · 탭의 멈춤 글 — 「실무자부터 여는 탭입니다」 ·
    「개발자만 여는 화면입니다」."""
    need = need_of(action)
    where = "화면" if place == "page" else "탭"
    if need == DEVELOPER:
        return f"{GRADE_LABELS[DEVELOPER]}만 여는 {where}입니다"
    return f"{GRADE_LABELS[need]}부터 여는 {where}입니다"


class GradeDenied(Exception):  # noqa: N818 — 계약 이름(갈래 사이 약속)
    """등급이 모자라 쓰지 않았다. `Exception` 직속 — 화면 공용 예외 튜플에 삼켜지지 않는다."""

    def __init__(self, action: str, need: str, have: str) -> None:
        super().__init__(action, need, have)
        self.action = action
        self.need = need
        self.have = have


class SignInEnded(Exception):  # noqa: N818 — 계약 이름(갈래 사이 약속)
    """로그인이 끝나(신원 없음) 쓰지 않았다 — 등급 거절과 섞지 않는다."""

    def __init__(self, action: str, reason: str) -> None:
        super().__init__(action, reason)
        self.action = action
        self.reason = reason


REFUSALS: Final = (GradeDenied, SignInEnded)


@dataclass(frozen=True)
class Caller:
    """지금 쓰려는 사람 — 유효 등급, 판정 없음(운영 아님 · 앱 자신), 로그인 끝남 까닭."""

    grade: str
    unrestricted: bool = False
    ended: str | None = None


_UNRESTRICTED: Final = Caller(DEVELOPER, unrestricted=True)
_SOURCE: Callable[[], Caller] | None = None
_LOCAL = threading.local()


def install_caller_source(source: Callable[[], Caller] | None) -> None:
    """「지금 누가 어느 등급인가」 를 꽂는다(같은 함수면 그대로). `None` 이면 뺀다(제한 없음)."""
    global _SOURCE
    _SOURCE = source


def caller_source() -> Callable[[], Caller] | None:
    """꽂힌 판정기(시험 · 그물이 「꽂혔다」 를 단언한다)."""
    return _SOURCE


def caller() -> Caller:
    """지금 이 스레드의 쓰는 사람. 꽂힌 것이 없으면 제한 없음, 판정기가 실패하면 열람."""
    source = _SOURCE
    if source is None:
        return _UNRESTRICTED
    try:
        return source()
    except Exception:  # noqa: BLE001 — 판정기가 넘어져도 넓어지지 않는다
        _LOGGER.exception("접속 등급을 정하지 못했습니다 — 열람으로 읽습니다.")
        return Caller(VIEWER)


def allowed(action: str) -> bool:
    """지금 쓰는 사람의 실제 등급으로 그 동작을 할 수 있는가(기록 없음)."""
    need = need_of(action)
    who = caller()
    if who.unrestricted:
        return True
    if who.ended is not None:
        return False
    return at_least(who.grade, need)


def require(action: str) -> None:
    """그 동작을 할 수 없으면 감사 한 줄을 남기고 `GradeDenied` · `SignInEnded` 를 던진다."""
    need = need_of(action)
    who = caller()
    if who.unrestricted:
        return
    if who.ended is not None:
        recorder.record(
            "authz_fail_signin",
            out="denied",
            det={"action": action, "reason": who.ended},
            why=who.ended,
        )
        raise SignInEnded(action, who.ended)
    if not at_least(who.grade, need):
        recorder.record(
            "authz_fail_grade",
            out="denied",
            det={"action": action, "need": need, "have": who.grade},
        )
        raise GradeDenied(action, need, who.grade)


def require_all(actions: Iterable[str]) -> None:
    """한 누름이 여러 쓰기를 부를 때 — 필요한 등급이 가장 높은 것 하나로 한 번 본다."""
    chosen = highest(actions)
    if chosen is not None:
        require(chosen)


def depth() -> int:
    """이 스레드에서 지금 벽 안에 든 바깥 쓰기의 깊이(0 이면 바깥)."""
    value = getattr(_LOCAL, "depth", 0)
    return value if isinstance(value, int) else 0


@contextmanager
def outer_wall(action: str) -> Iterator[None]:
    """바깥 쓰기(깊이 0)에서만 `require(action)` 를 보고 그 안을 한 깊이 내린다.

    판정이 거절하면 깊이를 바꾸지 않은 채 던진다. 안에서 무엇이 지나가도(멈춤 · 다시 그리기 예외
    포함) `finally` 로 깊이를 되돌린다 — 남은 깊이가 다음 쓰기의 벽을 건너뛰지 않게.
    """
    level = depth()
    if level == 0:
        require(action)
    _LOCAL.depth = level + 1
    try:
        yield
    finally:
        _LOCAL.depth = level


def gated(action: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """감사 표지가 없는(손으로 감사를 남기는) 쓰기에 벽만 단다 — 깊이 0 에서만 `require`."""
    need_of(action)

    def wrap(function: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(function)
        def inner(*args: P.args, **kwargs: P.kwargs) -> R:
            with outer_wall(action):
                return function(*args, **kwargs)

        setattr(inner, GATE_ATTRIBUTE, action)
        return inner

    return wrap
