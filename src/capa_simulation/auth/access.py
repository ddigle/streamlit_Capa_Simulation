# Purpose: 접속 명단 — 목록 글을 loginid → 등급 맵으로 읽고 들어올 수 있는지 판정한다.

"""접속 명단.

통합인증을 지났어도 이 명단에 없는 사람은 앱에 들어오지 못한다. 값은 C-DEP 환경변수 표와 S3 명단
파일(`access_store`)에서만 들어오고 이 저장소에는 적지 않는다(공개 저장소 — 실제 loginid 는 사람을
가리킨다). 표준 라이브러리만 쓴다.

안쪽 자료는 loginid → 등급 맵이다. 지금은 등급을 「들어올 수 있나」 로만 쓰고, 화면별 권한은 다음
단계가 이 맵에 등급을 늘려 얹는다.

순수 함수만 둔다 — 설정(`config.load_config`)이 환경변수 몫을 만들고, S3 명단이 켜져 있으면
`compose_access` 가 파일 몫을 얹은 한 벌을 `runtime` 이 들고 통째로 바꾼다. 판정은
`identity.session_check` 와 콜백 · 갱신 경로가 `runtime.current_access(cfg).allows` 로 묻는다.
**관리자는 환경변수뿐이다** — 파일의 등급 칸으로 관리자를 만들 수 없다(명단 편집 권한이 S3
쓰기 권한과 같아지지 않게). `LOGINID_PATTERN` 이 여기 있는 까닭은 `tokens` 가 `config` 를
import 하므로 `config` 가 `tokens` 에서 꺼내면 돌고 돌기 때문이다.

값은 repr · 로그 · 화면에 나오지 않는다 — 점검 화면에는 개수만, 거절 화면에는 `contact` 만 싣는다.
"""

from __future__ import annotations

import re
import types
from collections.abc import Mapping
from dataclasses import dataclass, field

GRADE_ADMIN = "admin"
GRADE_USER = "user"

# 쉼표가 든 값을 받지 않는 앞단이 있어 세미콜론 · 공백도 받는다. 환경변수 표는 한 줄 값만 받는다.
_ENTRY_SEPARATORS = re.compile(r"[,;\s]+")
# ID 토큰 · 세션 토큰의 loginid 와 같은 꼴. 백슬래시가 글자 집합 밖이라 `DOMAIN\이름` 은 꼴이
# 아니다.
LOGINID_PATTERN = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")


def normalize_loginid(value: str) -> str | None:
    """견주는 꼴 — 앞뒤 공백을 떼고 대소문자를 접는다. loginid 꼴이 아니면 `None`.

    꼴을 접기 전에 본다 — 접으면 ASCII 가 되는 글자(켈빈 기호 등)가 다른 사람의 loginid 로 읽히지
    않게.
    """
    text = value.strip()
    if not LOGINID_PATTERN.match(text):
        return None
    return text.casefold()


def entry_key(value: str) -> str | None:
    """명단 항목 하나 → 견주는 꼴. 사람으로 읽지 못하면 `None`.

    글자 · 숫자가 하나도 없는 항목(`-` · `.` 같은 자리표)도 읽지 못한 것이다 — 빈 값을 받지 않는
    표에 넣은 자리표가 관리자 한 명으로 세어지면 「읽은 관리자 없으면 막힘」 을 비껴가 전원이
    잠긴다. 토큰 쪽 꼴(`LOGINID_PATTERN`)은 그대로다.
    """
    key = normalize_loginid(value)
    return key if key is not None and any(character.isalnum() for character in key) else None


def parse_entries(raw: str) -> tuple[tuple[str, ...], int]:
    """목록 글 → (견주는 꼴 loginid 들, 읽지 못한 항목 수). 항목 값은 어디에도 남기지 않는다."""
    kept: list[str] = []
    unreadable = 0
    for item in _ENTRY_SEPARATORS.split(raw):
        if not item:
            continue
        key = entry_key(item)
        if key is None:
            unreadable += 1
        else:
            kept.append(key)
    return tuple(kept), unreadable


@dataclass(frozen=True)
class AccessList:
    """접속 명단 한 벌. `enforced` 가 아니면 인증된 사람 전부가 들어온다(루프백 개발 · 시험)."""

    enforced: bool
    grades: Mapping[str, str] = field(repr=False, hash=False)
    unreadable_admins: int = 0
    unreadable_users: int = 0
    contact: str = field(default="", repr=False)

    def grade_of(self, loginid: str) -> str | None:
        """이 사람의 등급. 명단에 없거나 loginid 꼴이 아니면 `None`."""
        key = normalize_loginid(loginid)
        return None if key is None else self.grades.get(key)

    def allows(self, loginid: str) -> bool:
        """앱에 들어올 수 있는가."""
        return not self.enforced or self.grade_of(loginid) is not None

    def _count(self, grade: str) -> int:
        return sum(1 for value in self.grades.values() if value == grade)

    @property
    def admin_count(self) -> int:
        return self._count(GRADE_ADMIN)

    @property
    def user_count(self) -> int:
        return self._count(GRADE_USER)

    @property
    def unreadable_count(self) -> int:
        return self.unreadable_admins + self.unreadable_users


def build_access_list(admins: str, users: str, *, enforced: bool, contact: str = "") -> AccessList:
    """목록 글 둘 → 명단. 두 목록에 다 있으면 관리자다(사용자를 먼저 적고 관리자로 덮는다)."""
    admin_keys, unreadable_admins = parse_entries(admins)
    user_keys, unreadable_users = parse_entries(users)
    grades = dict.fromkeys(user_keys, GRADE_USER)
    grades.update(dict.fromkeys(admin_keys, GRADE_ADMIN))
    return AccessList(
        enforced=enforced,
        grades=types.MappingProxyType(grades),
        unreadable_admins=unreadable_admins,
        unreadable_users=unreadable_users,
        contact=contact,
    )


@dataclass(frozen=True)
class ListEntry:
    """S3 명단 파일의 사람 하나 — 넣은 사람과 때는 Admin 표에만 보인다."""

    loginid: str
    added_by: str = ""
    added_at: str = ""


@dataclass(frozen=True)
class ListChange:
    """고친 기록 한 줄 — 누가 · 언제 · 무엇(`add` · `remove` · `drop_unreadable n`)을 누구에게."""

    by: str
    at: str
    what: str
    loginid: str = ""


@dataclass(frozen=True)
class ListDocument:
    """S3 명단 파일 한 벌. `revision` 은 저장할 때마다 1 씩 는다. repr 에 사람이 나오지 않는다."""

    revision: int = 0
    entries: tuple[ListEntry, ...] = field(default=(), repr=False)
    changes: tuple[ListChange, ...] = field(default=(), repr=False)
    unreadable: int = 0
    # 등급 칸이 `user` 가 아니어서 사용자로 읽은 항목 수 — 파일로는 관리자를 만들 수 없다.
    demoted: int = 0


@dataclass(frozen=True)
class SourceProblem:
    """S3 명단을 읽거나 쓰지 못한 까닭. 분류 · HTTP 상태 · 저장소 오류 코드뿐이다(값 · 키 없음).

    `unconfirmed` 는 PUT 을 보내고 답을 받지 못한 쓰기다 — 저장소에 들어갔는지 모른다.
    """

    kind: str
    status: int | None = None
    code: str = ""
    unconfirmed: bool = False


@dataclass(frozen=True)
class AccessSource:
    """지금 명단 한 벌과 그 내력 — `runtime` 이 하나를 들고 통째로 바꾼다.

    `access` 는 판정이 보는 합성 명단이다. `document` 가 `None` 이면 아직 한 번도 읽지 못한 것이고
    그때 `access` 는 환경변수 관리자뿐이다(열림으로 떨어지지 않는다). 한 번 읽어 둔 뒤의 실패는
    `problem` 에만 적고 `access` 를 건드리지 않는다. 저장이 성공하면 `problem` 을 비운다 — 저장소에
    닿았고 방금 쓴 것이 지금 명단이다.
    """

    access: AccessList
    document: ListDocument | None = None
    etag: str = ""
    read_at: int | None = None
    attempted_at: int | None = None
    problem: SourceProblem | None = None
    saved_at: int | None = None
    save_problem: SourceProblem | None = None
    # 파일이 아직 없어 환경변수 목록을 첫 판으로 쓰는 중이다(`document` 가 그 목록이다).
    seeded: bool = False
    # 첫 판을 파일로 썼는데 표지 객체를 못 남겼다 — 다음 저장이 다시 남긴다.
    seed_mark_pending: bool = False


def compose_access(base: AccessList, document: ListDocument) -> AccessList:
    """환경변수 몫(`base` — 관리자) + S3 파일 몫(사용자). 두 쪽에 다 있으면 관리자다."""
    grades = dict.fromkeys((entry.loginid for entry in document.entries), GRADE_USER)
    grades.update(base.grades)
    return AccessList(
        enforced=True,
        grades=types.MappingProxyType(grades),
        unreadable_admins=base.unreadable_admins,
        unreadable_users=document.unreadable,
        contact=base.contact,
    )
