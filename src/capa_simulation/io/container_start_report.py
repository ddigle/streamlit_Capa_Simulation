# Purpose: CD 시작 스크립트와 앱이 함께 쓰는 환경변수 이름·결과 파일 꼴과 화면 안내를 정한다.

"""C-DEP CD 컨테이너 시작 점검 결과.

CD 서버는 시작 명령을 바꿀 수 없고 셸에 들어갈 수도 없다. 그래서 이미지의 시작 스크립트
(`scripts/container_start.py`)가 C-DEP 배포 설정의 환경변수(key·value 표)만으로 사내
`bigdataquery` 설치(0)·로그인 토큰 파일(1)·요청자 계정(2)을 갖추고, 단계마다 결과를
`settings.CONTAINER_START_REPORT_PATH` 에 남긴다. 로그도 볼 수 없다고 보아 **앱 화면이 진단
창구다** — Admin Area 「서버 시작 점검」과 BigDataQuery 안내(`company_bigdataquery_adapter`)가
이 파일을 읽는다.

**비밀값은 파일에 없다.** 스크립트가 Artifactory 토큰·BDQ 토큰·URL 의 자격증명을 가리고, 계정은
앞 두 글자만 남긴다(`mask_account`). 이 모듈은 표준 라이브러리와 `settings` 만 읽는다 — 시작
스크립트가 앱 의존성을 불러오기 전에 쓰기 때문이다.

**동기화 칸**(`sync`)은 S3 키 · `managed` 가 있는 서버에만 있다 — aws 판 · ECS 연결 · 버킷 목록 ·
DB 받기와 재서 남긴 수(디스크 · pod · cgroup · 다운 시간). 값은 갈래와 수뿐이고 주소 · 버킷 · 키가
없어 리뷰 압축본에 옮길 수 있다. 꼴은 더하기만 했다 — 옛 파일은 그 칸이 없어 `None` 이다.

**자동 로그인 칸**(`bdq_login`)은 BigDataQuery 자동 로그인 단계의 결과다 — 갈래 낱말 · 까닭 코드 ·
키 꼴 검사 · 남은 분뿐이고 계정 · 비밀번호 · 키가 없다(`parse_login` 이 꼴을 다시 본다). 「서버 시작
점검」 표 줄(`login_step`)과 앱 기동의 멈춤 넘겨받기(`bdq_login.start_in_app`) · 알림이 읽는다.

**앱 응답 시각**은 앱이 따로 남긴다(`note_app_ready`) — 시작 스크립트는 exec 뒤에 없다.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from capa_simulation import settings

# C-DEP 배포 설정의 환경변수 표에 넣는 key. 값은 사람마다 다르고 비밀이라 저장소·배포 ZIP 에
# 두지 않는다.
ARTIFACTORY_USER_ENV: Final = "CAPA_ARTIFACTORY_USER"
ARTIFACTORY_TOKEN_ENV: Final = "CAPA_ARTIFACTORY_TOKEN"
BDQ_TOKEN_ENV: Final = "CAPA_BDQ_TOKEN"
# 걷은 갱신 토큰 이름 — 앱은 읽지 않는다. 표에 남아 있어도 비밀이라 앱 · 하위 프로세스에 넘기지
# 않고 시작 스크립트 출력에서 가린다(`APP_WITHHELD_ENVIRONMENT`).
RETIRED_BDQ_REFRESH_TOKEN_ENV: Final = "CAPA_BDQ_REFRESH_TOKEN"
# 조회 요청자의 사내 계정. 사람마다 다른 값이라 저장소에 두지 않는다 — 배포 ZIP 을 받은 다른
# 사람이 남의 계정으로 조회하게 된다. 어댑터(`getData(user_name=…)`)와 시작 스크립트(토큰 파일
# 이름)가 함께 읽는다.
BDQ_USER_NAME_ENV: Final = "CAPA_BDQ_USER_NAME"
# BigDataQuery 자동 로그인 계정을 감싸는 cryptography Fernet 키(`io/bdq_login_store.py`). 비밀이다
# — 앱 프로세스가 저장 · 다시 로그인에 쓰므로 시작 스크립트는 앱에 넘기고
# (`APP_WITHHELD_ENVIRONMENT` 에 넣지 않는다 — 앱 환경의 그 이름들은 「시작 스크립트가 안 돎」
# 표지다), 하위 프로세스에는 넘기지 않고 출력에서 가린다. 앱은 기동 때 읽은 뒤 `os.environ` 에서
# 뺀다(`bdq_login.start_in_app`).
BDQ_SECRET_KEY_ENV: Final = "CAPA_BDQ_SECRET_KEY"
# 사내 패키지 저장소 주소. 사내 값이라 저장소에 두지 않는다(공개 저장소) —
# `requirements-company.txt` 의 `--index-url` 줄이 이 이름을 `${…}` 로 가리키고, 사내 PC 는 사용자
# 환경변수 · C-DEP 는 환경변수 표에 둔다. 비밀값은 아니다(자격증명은 시작 스크립트가 따로 넣는다).
COMPANY_INDEX_URL_ENV: Final = "CAPA_COMPANY_INDEX_URL"
CD_ENVIRONMENT: Final = (
    ARTIFACTORY_USER_ENV,
    ARTIFACTORY_TOKEN_ENV,
    COMPANY_INDEX_URL_ENV,
    BDQ_TOKEN_ENV,
    BDQ_USER_NAME_ENV,
)
# 시작 스크립트가 앱 프로세스에 넘기지 않는 비밀값 셋. 앱 환경에 남아 있으면 스크립트가 돌지
# 않았다는 뜻이다(`missing_report_notice` — CD 전용 key 와 겹치는 것만 본다).
APP_WITHHELD_ENVIRONMENT: Final = (
    ARTIFACTORY_TOKEN_ENV,
    BDQ_TOKEN_ENV,
    RETIRED_BDQ_REFRESH_TOKEN_ENV,
)
# CD 배포 설정에만 넣는 key. 개발·사내 PC(WebIDE)는 `CAPA_BDQ_USER_NAME` 과 `CAPA_COMPANY_INDEX_URL`
# 도 쓰므로 그 둘로는 CD 서버인지 가르지 않는다. 자동 로그인 키는 「비어 있던 CD 환경변수」
# (`CD_ENVIRONMENT`)에 들지 않는다 — 넣지 않은 서버가 늘 그 이름을 빈 값으로 적게 된다.
CD_ONLY_ENVIRONMENT: Final = (
    ARTIFACTORY_USER_ENV,
    ARTIFACTORY_TOKEN_ENV,
    BDQ_TOKEN_ENV,
    BDQ_SECRET_KEY_ENV,
)
START_SCRIPT: Final = "scripts/container_start.py"
# 운영 이미지의 aws 판. `docker/Dockerfile-prod` 의 고정 줄과 시험이 맞댄다 — 시작 점검이 이 판과
# 견준다.
AWS_CLI_VERSION: Final = "1.46.3"
# 결과 파일에 이름으로 싣는 환경변수의 꼴.
_ENVIRONMENT_NAME: Final = re.compile(r"[A-Z][A-Z0-9_]*")

REPORT_VERSION: Final = 1
APP_READY_NAME: Final = "container_app_ready.json"
STEP_INSTALL: Final = "install"
STEP_TOKEN: Final = "token"
STEP_USER_NAME: Final = "user_name"
STEPS: Final = (STEP_INSTALL, STEP_TOKEN, STEP_USER_NAME)
STEP_LABELS: Final[Mapping[str, str]] = {
    STEP_INSTALL: "bigdataquery 설치",
    STEP_TOKEN: "로그인 토큰 파일",
    STEP_USER_NAME: "요청자 계정",
}
# 단계마다 그 단계가 읽는 환경변수. 화면 안내는 빠진 것 가운데 그 단계 몫만 「넣을 것」으로
# 적는다 — 설치 안내에 `CAPA_BDQ_USER_NAME` 이 섞이면 점검 스크립트
# (`inspect_real_data_checks._bdq_failure`)가 그 이름으로 「요청자 계정 필요」를 가른다.
STEP_ENVIRONMENT: Final[Mapping[str, tuple[str, ...]]] = {
    STEP_INSTALL: (ARTIFACTORY_USER_ENV, ARTIFACTORY_TOKEN_ENV, COMPANY_INDEX_URL_ENV),
    STEP_TOKEN: (BDQ_TOKEN_ENV, BDQ_USER_NAME_ENV),
    STEP_USER_NAME: (BDQ_USER_NAME_ENV,),
}

# 동기화 줄. 옛 파일에 없어도 읽도록 `STEPS` 와 따로 둔다.
SYNC_STEP_PROFILE: Final = "aws_profile"
SYNC_STEP_CLI: Final = "aws_cli"
SYNC_STEP_ECS: Final = "ecs"
SYNC_STEP_BUCKET: Final = "bucket"
SYNC_STEP_PULL: Final = "boot_pull"
SYNC_STEPS: Final = (
    SYNC_STEP_PROFILE,
    SYNC_STEP_CLI,
    SYNC_STEP_ECS,
    SYNC_STEP_BUCKET,
    SYNC_STEP_PULL,
)
SYNC_STEP_LABELS: Final[Mapping[str, str]] = {
    SYNC_STEP_PROFILE: "AWS 프로필",
    SYNC_STEP_CLI: "aws CLI",
    SYNC_STEP_ECS: "ECS 연결",
    SYNC_STEP_BUCKET: "버킷 목록",
    SYNC_STEP_PULL: "DB 받기",
}

STATUS_OK: Final = "ok"
STATUS_SKIPPED: Final = "skipped"
STATUS_FAILED: Final = "failed"
STATUS_LABELS: Final[Mapping[str, str]] = {
    STATUS_OK: "정상",
    STATUS_SKIPPED: "건너뜀",
    STATUS_FAILED: "실패",
}

# BigDataQuery 자동 로그인 칸(`bdq_login`). 이름은 Admin 「서버 시작 점검」 표의 줄 이름이자 Admin
# Area 의 계정 넣는 자리 이름이다 — 알림 글(`AD-10` · `AD-23`)이 이 이름으로 그 자리를 가리킨다.
BDQ_LOGIN_LABEL: Final = "BDQ 자동 로그인"
# 갈래 — `off`(기능이 서지 않음) · `absent`(저장된 계정 없음) · `stopped`(멈춤이라 로그인 없음) ·
# 로그인 결과 다섯(`ok` · `rejected` · `unreached` · `unavailable` · `unconfirmed` — 토큰은
# 바뀌었지만 남은 시간을 확인하지 못함, 패키지가 쓴 토큰을 둔다) · `error`(단계가 예상하지 못하게
# 멈춤 — 예비 토큰 길). `io/bdq_login.StartLogin.status` 와 같은 낱말에 `error` 를 더했다.
LOGIN_OFF: Final = "off"
LOGIN_ABSENT: Final = "absent"
LOGIN_STOPPED: Final = "stopped"
LOGIN_OK: Final = "ok"
LOGIN_REJECTED: Final = "rejected"
LOGIN_UNREACHED: Final = "unreached"
LOGIN_UNAVAILABLE: Final = "unavailable"
LOGIN_UNCONFIRMED: Final = "unconfirmed"
LOGIN_ERROR: Final = "error"
LOGIN_STATUSES: Final = frozenset(
    {
        LOGIN_OFF,
        LOGIN_ABSENT,
        LOGIN_STOPPED,
        LOGIN_OK,
        LOGIN_REJECTED,
        LOGIN_UNREACHED,
        LOGIN_UNAVAILABLE,
        LOGIN_UNCONFIRMED,
        LOGIN_ERROR,
    }
)
# 자동 로그인이 서 있는(저장된 계정이 있고 멈춤이 아닌) 시작 갈래 — 예비 토큰 길로 갔어도 조회 중
# 토큰 예외면 다시 로그인한다.
LOGIN_STANDING: Final = frozenset({LOGIN_OK, LOGIN_UNREACHED, LOGIN_UNAVAILABLE, LOGIN_UNCONFIRMED})
# 키 꼴 검사 결과(`key`) — `bdq_login_store` 의 까닭 코드와 같은 낱말.
LOGIN_KEY_OK: Final = "ok"
LOGIN_KEY_MISSING: Final = "no_key"
LOGIN_KEY_BAD: Final = "bad_key"
_LOGIN_KEYS: Final = frozenset({LOGIN_KEY_OK, LOGIN_KEY_MISSING, LOGIN_KEY_BAD})
# 꺼짐 까닭 가운데 표 줄을 세우지 않는 것 — 동기화 모드가 `managed` 가 아닌 서버는 이 기능이 없다.
LOGIN_NOT_MANAGED: Final = "not_managed"
# 칸에 싣는 코드 꼴 — 짧은 영문 소문자 · 숫자 · 밑줄 · 쌍점(쓰기 실패 `까닭:분류`), 예외 종류의
# `모듈.이름`. 꼴이 어긋난 값은 읽을 때 버린다 — 화면 · 알림에 값이 실리지 않게.
_LOGIN_CODE: Final = re.compile(r"[a-z][a-z0-9_]{0,39}(?::[a-z][a-z0-9_]{0,39})?")
_LOGIN_ERROR_KIND: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,199}")
# 넣은 시각 꼴 — KST ISO(초까지, 시각대 붙음).
_LOGIN_MOMENT: Final = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}")
# 표 줄 까닭 — 아는 코드는 낱말로, 모르는 코드는 그대로.
_LOGIN_REASON_WORDS: Final[Mapping[str, str]] = {
    "token_unchanged": "토큰이 바뀌지 않음",
    "login_raised": "로그인 예외",
    "no_marker": "결과 표지 없음",
    "token_after_login": "다시 로그인 뒤에도 토큰 오류",
    "timeout": "시간 초과",
    "connection": "연결 실패",
    "import_failed": "패키지를 불러오지 못함",
    "no_input": "입력을 읽지 못함",
    "spawn_failed": "하위 프로세스를 띄우지 못함",
    "bad_input": "값 꼴이 틀림",
    "bad_account": "계정을 파일 이름으로 못 씀",
    "env_token": "환경변수 BIGDATAQUERY_LOGIN_TOKEN 있음",
    "attempt_limit": "연속 시도 상한",
    "paused": "쉬는 중",
    "stopped": "멈춤",
    "no_key": "키 없음",
    "bad_key": "키 꼴이 틀림",
    "no_target": "S3 닿을 곳 없음",
    "no_object": "계정 없음",
    "unread": "읽지 못함",
    "broken": "객체 꼴이 다름",
    "version": "객체 판이 다름",
    "undecryptable": "키로 풀지 못함",
    "unexpected": "예상하지 못한 실패",
    "remaining_unknown": "남은 시간 모름",
    "remaining_short": "남은 시간 7시간 이하",
    "miss_limit": "닿지 못함 · 확인 못 함 연속 상한",
    "attempting": "시도 결과를 적지 못함",
    "unguarded": "시도 표시를 쓰지 못함",
    "changed": "계정이 그 사이 바뀜",
}


@dataclass(frozen=True)
class StartStep:
    status: str
    reason: str


@dataclass(frozen=True)
class SyncStart:
    """동기화 칸. 값은 갈래 · 판 · 수뿐이다. 어느 칸이든 옛 파일 · 못 잰 값이면 `None` 이다."""

    steps: Mapping[str, StartStep]
    started_at_utc: str | None = None
    aws_version: str | None = None
    disk_free_bytes: int | None = None
    disk_total_bytes: int | None = None
    pod: str | None = None
    memory_limit_bytes: int | None = None
    cpu_limit: float | None = None
    logical_cores: int | None = None
    duckdb_memory_limit: str | None = None
    duckdb_threads: str | None = None
    pull_seconds: float | None = None
    pull_attempts: int | None = None
    previous_upload_utc: str | None = None
    # 버킷에 세대가 있는데 모드 칸이 managed 가 아니어서(비었거나 local) 받지 않았다.
    head_ignored: bool = False
    # 모드 칸이 managed 가 아닌데 빈 CD 환경변수(이름) 때문에 버킷 목록을 보지 못해 위 표지를 가리지
    # 못했다. 이름만 — 값은 비었다.
    head_unchecked: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoginStart:
    """BigDataQuery 자동 로그인 칸. 값은 갈래 낱말 · 짧은 코드 · 수뿐이다 — 계정 · 비밀번호 · 키 ·
    예외 문구가 없다. 꼴이 어긋난 칸은 비운다.

    `status` — `LOGIN_*`. `reason` — 까닭 코드. `key` — 키 꼴 검사(`LOGIN_KEY_*`, 못 읽으면 빈 글).
    `remaining_minutes` — 로그인 뒤 잰 남은 분(모르면 `None`).
    `error_kind` — 예외 종류의 `모듈.이름`. `failure_kind` — S3 읽기 실패 분류. `stop_write` —
    객체에 시도 표시 · 결과 · 멈춤을 쓰지 못한 까닭(빈 글이면 씀 · 해당 없음). `entered_at` — 판정한
    저장 객체의 넣은 시각(KST ISO — 비밀이 아니다. 앱 기동이 그 사이 다시 넣은 계정에 멈춤을 잘못
    넘겨받지 않게 대조한다)."""

    status: str
    reason: str = ""
    key: str = ""
    remaining_minutes: int | None = None
    error_kind: str = ""
    failure_kind: str = ""
    stop_write: str = ""
    entered_at: str = ""

    @property
    def shown(self) -> bool:
        """「서버 시작 점검」 표에 줄을 세우나 — `managed` 가 아닌 서버는 이 기능이 없어 세우지
        않는다."""
        return not (self.status == LOGIN_OFF and self.reason == LOGIN_NOT_MANAGED)


@dataclass(frozen=True)
class ContainerStartReport:
    """시작 스크립트가 남긴 한 번의 결과. 값은 모두 이미 가린 꼴이다."""

    written_at: str
    steps: Mapping[str, StartStep]
    bigdataquery_version: str | None
    token_file_exists: bool | None
    token_file_modified_at: str | None
    user_name_masked: str | None
    missing_environment: tuple[str, ...]
    pip_tail: tuple[str, ...]
    # 토큰 파일 자리(계정은 가린 꼴)와 컨테이너의 실행 사용자·HOME. 패키지가 토큰을 다른 이름이나
    # 자리에서 찾는지 화면만으로 가르려고 싣는다. 옛 꼴 파일에는 없어 `None` 이다.
    token_file_path: str | None = None
    os_user_masked: str | None = None
    os_user_is_bdq_user: bool | None = None
    home_masked: str | None = None
    # 시작 때 통합인증 환경변수(`auth.names.SSO_ENVIRONMENT`)가 있었는지 — 이름 → 있음. 값은 없다.
    # 옛 꼴 파일에는 없어 `None` 이다.
    sso_environment: Mapping[str, bool] | None = None
    # 동기화 칸. S3 키도 `managed` 도 없는 서버 · 옛 꼴 파일에는 없어 `None` 이다.
    sync: SyncStart | None = None
    # BigDataQuery 자동 로그인 칸. 옛 꼴 파일 · 도중에 멈춘 시작 점검에는 없어 `None` 이다.
    bdq_login: LoginStart | None = None


def mask_account(name: str) -> str:
    """계정은 앞 두 글자만 남긴다(`fakeaccount` → `fa***`)."""
    return f"{name[:2]}***"


def report_path() -> Path:
    """결과 파일 자리. 부를 때마다 `settings` 에서 읽는다 — 시험이 그 칸을 tmp 로 옮긴다."""
    return settings.CONTAINER_START_REPORT_PATH


def read_container_start_report(path: Path | None = None) -> ContainerStartReport | None:
    """결과 파일을 읽는다. 없거나 꼴이 어긋나면 `None` — 개발·사내 PC 는 늘 `None` 이다.

    화면 회차마다 불러도 되는 크기(작은 JSON 하나)라 캐시하지 않는다. DB 를 열지 않는다.
    """
    target = report_path() if path is None else path
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return parse_report(data)


def report_file_exists(path: Path | None = None) -> bool:
    """결과 파일이 있는가 — `read_container_start_report` 가 None 일 때 「없음」 과 「있는데 못
    읽음」 을 가른다. 자리를 볼 수 없으면 없는 것으로 본다."""
    target = report_path() if path is None else path
    try:
        return target.is_file()
    except OSError:
        return False


def parse_report(data: object) -> ContainerStartReport | None:
    if not isinstance(data, dict) or not isinstance(data.get("steps"), dict):
        return None
    steps: dict[str, StartStep] = {}
    for name in STEPS:
        step = data["steps"].get(name)
        if not isinstance(step, dict):
            return None
        status, reason = step.get("status"), step.get("reason")
        if status not in STATUS_LABELS or not isinstance(reason, str):
            return None
        steps[name] = StartStep(status=str(status), reason=reason)
    token_file = _mapping(data.get("token_file"))
    user_name = _mapping(data.get("user_name"))
    runtime = _mapping(data.get("runtime"))
    same_user = runtime.get("os_user_is_bdq_user")
    missing = data.get("missing_environment")
    tail = data.get("pip_tail")
    exists = token_file.get("exists")
    return ContainerStartReport(
        written_at=str(data.get("written_at") or ""),
        steps=steps,
        bigdataquery_version=_text_or_none(data.get("bigdataquery_version")),
        token_file_exists=exists if isinstance(exists, bool) else None,
        token_file_modified_at=_text_or_none(token_file.get("modified_at")),
        user_name_masked=_text_or_none(user_name.get("masked")),
        missing_environment=tuple(
            str(name) for name in (missing if isinstance(missing, list) else [])
        ),
        pip_tail=tuple(str(line) for line in (tail if isinstance(tail, list) else [])),
        token_file_path=_text_or_none(token_file.get("path")),
        os_user_masked=_text_or_none(runtime.get("os_user")),
        os_user_is_bdq_user=same_user if isinstance(same_user, bool) else None,
        home_masked=_text_or_none(runtime.get("home")),
        sso_environment=_presence_or_none(data.get("sso_environment")),
        sync=parse_sync(data.get("sync")),
        bdq_login=parse_login(data.get("bdq_login")),
    )


def parse_login(data: object) -> LoginStart | None:
    """자동 로그인 칸을 읽는다. 없거나 갈래 낱말이 어긋나면 `None`. 꼴이 어긋난 나머지 칸은 그
    칸만 비운다 — 화면 · 알림에 값이 실리지 않게."""
    if not isinstance(data, dict) or data.get("status") not in LOGIN_STATUSES:
        return None
    minutes = _int_or_none(data.get("remaining_minutes"))
    key = data.get("key")
    error_kind = data.get("error_kind")
    return LoginStart(
        status=str(data["status"]),
        reason=_login_code(data.get("reason")),
        key=key if isinstance(key, str) and key in _LOGIN_KEYS else "",
        remaining_minutes=minutes if minutes is not None and minutes >= 0 else None,
        error_kind=(
            error_kind
            if isinstance(error_kind, str) and _LOGIN_ERROR_KIND.fullmatch(error_kind)
            else ""
        ),
        failure_kind=_login_code(data.get("failure_kind")),
        stop_write=_login_code(data.get("stop_write")),
        entered_at=_login_moment(data.get("entered_at")),
    )


def _login_code(value: object) -> str:
    return value if isinstance(value, str) and _LOGIN_CODE.fullmatch(value) else ""


def _login_moment(value: object) -> str:
    return value if isinstance(value, str) and _LOGIN_MOMENT.fullmatch(value) else ""


def login_reason_text(code: str) -> str:
    """자동 로그인 까닭 코드 → 낱말(표 줄 · 알림 글). 모르는 코드는 그대로."""
    return _LOGIN_REASON_WORDS.get(code, code)


def remaining_text(minutes: int | None) -> str:
    """남은 분 → 「남은 n시간 n분」(모르면 「남은 시간 모름」) — 표 줄과 Admin 「BDQ 자동
    로그인」 이 함께 쓴다."""
    if minutes is None:
        return "남은 시간 모름"
    hours, rest = divmod(minutes, 60)
    return f"남은 {hours}시간 {rest}분"


def login_step(login: LoginStart) -> StartStep | None:
    """자동 로그인 칸 → 「서버 시작 점검」 표 한 줄(결과 · 까닭). 줄을 세우지 않는 서버는 `None`.

    까닭은 상태 낱말과 결과뿐이다 — 꺼짐(키 없음) · 계정 없음 · 정상(남은 시간) · 멈춤(까닭) ·
    닿지 못함(예비 토큰). 예비 토큰 길로 간 갈래는 그 사실을 붙이고, 객체에 결과를 적지 못했으면
    (다음 시작은 멈춤으로 읽는다) 그 사실을 붙인다."""
    if not login.shown:
        return None
    fallback = " · 예비 토큰"
    unwritten = " · 결과 저장 못 함" if login.stop_write else ""
    status = login.status
    reason = login.reason
    if status == LOGIN_OK:
        line = f"정상 · {remaining_text(login.remaining_minutes)}{unwritten}"
        return StartStep(STATUS_FAILED if unwritten else STATUS_OK, line)
    if status == LOGIN_OFF:
        result = STATUS_SKIPPED if reason == LOGIN_KEY_MISSING else STATUS_FAILED
        return StartStep(result, f"꺼짐 — {login_reason_text(reason)}")
    if status == LOGIN_ABSENT:
        if reason in ("", "no_object"):
            return StartStep(STATUS_SKIPPED, "계정 없음")
        detail = login_reason_text(reason)
        if login.failure_kind:
            detail += f"({login.failure_kind})"
        return StartStep(STATUS_FAILED, f"계정 없음 — {detail}")
    if status in (LOGIN_STOPPED, LOGIN_REJECTED):
        tail = " · 멈춤 저장 못 함" if login.stop_write else ""
        detail = login_reason_text(reason) if reason else "까닭 모름"
        return StartStep(STATUS_FAILED, f"멈춤 — {detail}{tail}{fallback}")
    if status == LOGIN_UNREACHED:
        detail = f"{login_reason_text(reason)}{unwritten}{fallback}"
        return StartStep(STATUS_FAILED, f"닿지 못함 — {detail}")
    if status == LOGIN_UNAVAILABLE:
        return StartStep(STATUS_FAILED, f"못 함 — {login_reason_text(reason)}{unwritten}{fallback}")
    if status == LOGIN_UNCONFIRMED:
        return StartStep(STATUS_FAILED, f"확인 못 함 — {login_reason_text(reason)}{unwritten}")
    kind = f"({login.error_kind})" if login.error_kind else ""
    return StartStep(STATUS_FAILED, f"예상하지 못한 실패{kind}{fallback}")


def parse_sync(data: object) -> SyncStart | None:
    """동기화 칸을 읽는다. 없으면 `None`. 꼴이 어긋난 칸은 그 칸만 버린다 — 옛 판이 쓴 파일 하나가
    펼침 전체를 지우지 않게 한다."""
    if not isinstance(data, dict):
        return None
    raw_steps = _mapping(data.get("steps"))
    steps: dict[str, StartStep] = {}
    for name in SYNC_STEPS:
        step = _mapping(raw_steps.get(name))
        status, reason = step.get("status"), step.get("reason")
        if status in STATUS_LABELS and isinstance(reason, str):
            steps[name] = StartStep(status=str(status), reason=reason)
    return SyncStart(
        steps=steps,
        started_at_utc=_text_or_none(data.get("started_at_utc")),
        aws_version=_text_or_none(data.get("aws_version")),
        disk_free_bytes=_int_or_none(data.get("disk_free_bytes")),
        disk_total_bytes=_int_or_none(data.get("disk_total_bytes")),
        pod=_text_or_none(data.get("pod")),
        memory_limit_bytes=_int_or_none(data.get("memory_limit_bytes")),
        cpu_limit=_float_or_none(data.get("cpu_limit")),
        logical_cores=_int_or_none(data.get("logical_cores")),
        duckdb_memory_limit=_text_or_none(data.get("duckdb_memory_limit")),
        duckdb_threads=_text_or_none(data.get("duckdb_threads")),
        pull_seconds=_float_or_none(data.get("pull_seconds")),
        pull_attempts=_int_or_none(data.get("pull_attempts")),
        previous_upload_utc=_text_or_none(data.get("previous_upload_utc")),
        head_ignored=data.get("head_ignored") is True,
        head_unchecked=_environment_names(data.get("head_unchecked")),
    )


def _environment_names(value: object) -> tuple[str, ...]:
    """환경변수 이름 목록. 이름 꼴이 아닌 항목은 버린다 — 화면 · 알림에 값이 실리지 않게."""
    items = value if isinstance(value, list) else []
    return tuple(
        item for item in items if isinstance(item, str) and _ENVIRONMENT_NAME.fullmatch(item)
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def _presence_or_none(value: object) -> dict[str, bool] | None:
    """`{이름: 있음}` 칸. 없거나 꼴이 다르면 `None`(옛 꼴 파일). 참·거짓이 아닌 값은 버린다."""
    if not isinstance(value, dict):
        return None
    return {str(name): flag for name, flag in value.items() if isinstance(flag, bool)}


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def utc_timestamp() -> str:
    """UTC 시각 글자 — 포인터 시각(`snapshot_export.utc_timestamp`)과 같은 꼴."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def seconds_between(earlier_utc: str | None, later_utc: str | None) -> float | None:
    """두 UTC 시각 글자 사이의 초. 어느 쪽이든 없거나 못 읽으면 `None`."""
    earlier, later = _parse_utc(earlier_utc), _parse_utc(later_utc)
    return None if earlier is None or later is None else (later - earlier).total_seconds()


def app_ready_path() -> Path:
    """앱이 준비를 마친 시각 자리. 결과 파일 옆이다."""
    return report_path().with_name(APP_READY_NAME)


def clear_app_ready() -> None:
    """앞 실행의 시각을 지운다. 시작 스크립트가 맨 앞에서 부른다."""
    app_ready_path().unlink(missing_ok=True)


def note_app_ready() -> None:
    """앱이 받을 준비를 마친 시각을 한 번 남긴다 — 「앱 응답까지 n초」 의 끝.

    시작 스크립트가 돌지 않은 자리(개발 · 사내 PC)에서는 결과 파일이 없어 아무것도 쓰지 않는다.
    첫 시각이 답이라 덮어쓰지 않는다. 진단 값 하나라 실패가 앱 띄우기를 막지 않는다.
    """
    target = app_ready_path()
    try:
        if not report_path().is_file() or target.exists():
            return
        target.write_text(json.dumps({"ready_at_utc": utc_timestamp()}), encoding="utf-8")
    except OSError:
        return


def read_app_ready() -> str | None:
    """앱이 남긴 시각. 없거나 꼴이 어긋나면 `None`."""
    try:
        payload = json.loads(app_ready_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return _text_or_none(_mapping(payload).get("ready_at_utc"))


def missing_for_step(report: ContainerStartReport, step: str) -> tuple[str, ...]:
    """그 단계가 읽는데 시작 때 비어 있던 환경변수."""
    return tuple(name for name in STEP_ENVIRONMENT[step] if name in report.missing_environment)


def step_hint(report: ContainerStartReport, step: str) -> str:
    """BigDataQuery 안내에 덧붙일 한 단락 — 그 단계의 결과와 넣을 환경변수."""
    result = report.steps[step]
    line = f"서버 시작 점검 — {STEP_LABELS[step]} {STATUS_LABELS[result.status]}: {result.reason}."
    missing = missing_for_step(report, step)
    if missing:
        names = "·".join(f"`{name}`" for name in missing)
        line += (
            f" 넣을 CD 환경변수: {names} — C-DEP 배포 설정의 환경변수 표에 넣고 CI/CD 를 다시 "
            "돌리세요."
        )
    elif step == STEP_TOKEN and result.status == STATUS_OK:
        # 파일을 써 두었는데도 토큰 오류면 두 갈래다 — 패키지가 다른 이름·자리를 찾거나 토큰이
        # 만료됐다. 원문의 계정·자리를 먼저 대 보게 해 헛된 재로그인으로 보내지 않는다.
        written = f"`{report.token_file_path}`" if report.token_file_path else "토큰 파일"
        line += (
            f" 시작 스크립트는 {written} 에 써 두었습니다 — 위 원문이 찾은 계정·자리가 "
            "그와 다르면 패키지가 다른 이름이나 자리를 보는 것이니 Admin Area 「서버 시작 "
            "점검」 의 실행 사용자·HOME 과 함께 알려 주세요. 같다면 토큰이 만료됐을 수 "
            "있습니다 — WebIDE 에서 다시 로그인해 "
            f"`{BDQ_TOKEN_ENV}` 값을 바꾸고 CI/CD 를 다시 돌리세요."
        )
    elif result.status == STATUS_FAILED:
        line += " 자세한 결과는 Admin Area 「서버 시작 점검」 에 있습니다."
    return line


def start_check_hint(
    step: str, path: Path | None = None, environ: Mapping[str, str] | None = None
) -> str | None:
    """결과 파일이 있으면 그 단계의 안내 한 단락이다. 있는데 읽지 못하면 「결과 파일을 읽지
    못했습니다」 한 단락(`UNREADABLE_REPORT_DETAIL`)이다. 없으면 CD 서버로 보일 때만 「결과 없음」
    한 단락(`missing_report_detail`)이고, 개발·사내 PC 는 `None`(지금 문구 그대로)이다."""
    report = read_container_start_report(path)
    if report is None:
        if report_file_exists(path):
            return UNREADABLE_REPORT_DETAIL
        notice = missing_report_notice(environ)
        return None if notice is None else missing_report_detail(notice)
    return step_hint(report, step)


# 결과 파일은 있는데 읽지 못했을 때(빈 파일·JSON 아님·모르는 단계 결과 등)의 한 단락. 「결과 없음」
# (`missing_report_notice` — 스크립트가 돌지 않았거나 쓰지 못함)과 가른다 — 파일이 있으니 스크립트는
# 돌았다(E2E r2). CD 환경변수와 상관없이 낸다. 이 문구에 `CAPA_BDQ_USER_NAME` 을 섞지 않는다(점검
# 스크립트의 갈래).
UNREADABLE_REPORT_NOTICE: Final = (
    "서버 시작 점검 결과 파일을 읽지 못했습니다(꼴이 다름) — 결과 파일"
    "(`data/temp/container_start.json`)은 있는데 비었거나 JSON 이 아니거나 이 앱이 모르는 "
    f"꼴입니다. 시작 스크립트(`{START_SCRIPT}`)가 쓰다 끊겼거나 앱과 판이 다를 수 있습니다."
)
# 그다음 할 일 — 펼침 자리에는 결론만 두고(설계 규칙 UI-TXT-04) Guide 「서버 시작 점검」 이 말한다.
# 펼침 밖의 글(알림 전문 · 조회 실패 안내)은 Guide 를 열지 않아도 되게 잇는다.
UNREADABLE_REPORT_ACTION: Final = (
    "CI/CD 를 다시 돌리고, 그래도 같으면 이 문구를 그대로 알려 주세요."
)
UNREADABLE_REPORT_DETAIL: Final = f"{UNREADABLE_REPORT_NOTICE} {UNREADABLE_REPORT_ACTION}"
# 「결과 없음」 의 그다음 할 일 — 읽지 못함과 같이 펼침 밖의 글에만 잇는다(`missing_report_detail`).
MISSING_REPORT_ACTION: Final = "이 문구를 그대로 알려 주세요."


def missing_report_notice(environ: Mapping[str, str] | None = None) -> str | None:
    """CD 환경변수는 앱에 들어왔는데 결과 파일이 없을 때의 한 단락. CD 전용 key 가 없으면 `None`.

    시작 스크립트는 비밀값(`APP_WITHHELD_ENVIRONMENT`)을 앱에 넘기지 않으므로, 그 key 가 앱
    환경에 있으면 스크립트가 돌지 않은 것이다(C-DEP 이 이미지 `CMD` 대신 다른 시작 명령을 썼을
    때). 비밀값이 없고 계정만 있으면
    스크립트가 돌지 않았는지 결과를 쓰지 못했는지 가를 수 없다. 이 문구에 `CAPA_BDQ_USER_NAME` 을
    섞지 않는다 — 점검 스크립트가 그 이름으로 「요청자 계정 필요」를 가른다.
    """
    env = os.environ if environ is None else environ
    present = [name for name in CD_ONLY_ENVIRONMENT if env.get(name, "").strip()]
    if not present:
        return None
    withheld = [name for name in APP_WITHHELD_ENVIRONMENT if name in present]
    if withheld:
        names = "·".join(f"`{name}`" for name in withheld)
        return (
            f"서버 시작 점검 결과가 없습니다 — 시작 스크립트(`{START_SCRIPT}`)가 돌지 않은 "
            "것으로 보입니다. 그 스크립트가 앱에 넘기지 않는 CD 환경변수가 앱에 그대로 "
            f"있습니다({names}). C-DEP 이 이미지의 시작 "
            "명령(`CMD`) 대신 다른 명령으로 앱을 띄운 것으로 보이고, 그러면 시작 스크립트로 "
            "설치·로그인 토큰을 갖출 수 없습니다."
        )
    names = "·".join(f"`{name}`" for name in present)
    return (
        f"서버 시작 점검 결과가 없습니다 — CD 환경변수({names})는 들어왔는데 "
        f"시작 스크립트(`{START_SCRIPT}`)의 결과 파일이 없습니다. 스크립트가 돌지 않았거나 "
        "`data/temp/` 에 결과를 쓰지 못했습니다."
    )


def missing_report_detail(notice: str) -> str:
    """`missing_report_notice` 의 글에 그다음 할 일을 이은 펼침 밖의 글."""
    return f"{notice} {MISSING_REPORT_ACTION}"


def report_verdict(report: ContainerStartReport) -> str:
    """펼침 제목 끝에 붙는 한마디 — 실패가 하나라도 있으면 실패, 다음은 건너뜀."""
    statuses = {step.status for step in report.steps.values()}
    if report.sync is not None:
        statuses |= {step.status for step in report.sync.steps.values()}
    login = None if report.bdq_login is None else login_step(report.bdq_login)
    if login is not None:
        statuses.add(login.status)
    if STATUS_FAILED in statuses:
        return "실패 있음"
    if STATUS_SKIPPED in statuses:
        return "건너뜀 있음"
    return "모두 정상"
