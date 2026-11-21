# Purpose: 저장된 계정의 BigDataQuery 하위 프로세스 로그인 · 결과 갈래 · 잠김 방지 · 다시 로그인.

"""BigDataQuery 자동 로그인 실행기.

C-DEP(`managed`)에서 BDQ 토큰이 만료 · 무효가 되면 앱이 저장된 계정(`io/bdq_login_store`)으로 스스로
다시 로그인한다. 길은 셋이다 — 시작(`start_login` — 시작 스크립트가 부른다), 조회 중 토큰 예외
(`run_with_relogin` · `recover_after_token_failure` — 어댑터가 부른다), Admin 폼 제출
(`login_from_form`).

**앱 기동과 화면.** 앱은 기동 때 한 번(`start_in_app` — `capa_server.py`) 키를 쥐고 환경에서 빼고
저장 객체를 읽어 두며, 시작 스크립트가 거절을 보고도 멈춤 표시를 쓰지 못했으면 그 멈춤을 넘겨받는다
(시작 스크립트의 프로세스 안 멈춤은 앱으로 바뀌며 사라진다). 화면 회차마다 도는 알림은 S3 에 묻지
않는 `current_view` 로 상태를 읽는다 — 기억이 없으면 이번 시작 기록(결과 파일의 자동 로그인 칸).

**로그인 한 번**(`attempt_login`)은 `sys.executable` 하위 프로세스(`io/bdq_login_child.py`)다.
계정 · 비밀번호는 표준 입력으로만 넘기고 명령줄 · 환경변수에 없다. 하위 환경은 비밀
이름(시작 스크립트가 앱에 넘기지 않는 것 · 통합인증 비밀 · `CAPA_BDQ_SECRET_KEY` · `CAPA_S3_*` ·
`AWS_*`)을 뺀 것이고 표준 입출력은 UTF-8 이다(`child_environment` — 앱 자리의 로캘과 무관하게).
하위 출력(패키지 배너 포함)은 버리고 표지 한 줄과 단계 줄만 읽는다. 시간 제한이 있고, tty 가 있는
자리에서도 비밀번호를 표준 입력으로 읽게 새 세션으로 띄운다(제어 터미널 없음). 기다리는 동안
`CHILD_POLL_SECONDS` 마다 그 하위 자신의 최고 RSS 를 읽는다(`_run_child` — 새 스레드 없이 같은
자리에서 되풀이해 기다린다).

**진단**(`child_diag` → `LoginResult.diag` — `ChildDiag`). 하위 프로세스를 띄운 시도마다 종료
코드 · 시그널 · 걸린 초(부르는 쪽이 잰다), 하위 본문이 마지막으로 들어간 단계와 판(단계 줄 —
표지 없이 끝나도 남는다), 표준 오류 마지막 traceback 의 예외 종류(`stderr_kind` — 이름만, 계정 ·
비밀번호가 든 이름은 버린다), 하위 프로세스를 띄우기 바로 앞과 끝난 바로 뒤의 메모리 단서(cgroup
사용 · 한도 · OOM 종료 수, 앱 RSS)와 그 하위 자신의 최고 RSS(도는 동안 잰 가장 큰 값), 띄우기 바로
앞의 프로세스 단서(부른 프로세스가 뜬 시간 · 스레드 · 열린 파일, cgroup 프로세스 수 · 한도 · 좀비
수) — `io/memory_probe`, 못 읽으면 「모름」 — 를 남긴다. 표준 오류 글 자체는 그 자리에서 버린다.
마지막 시도 줄(Admin) · 로그 · 감사 상세 · 결과 파일 칸이 읽는다.

**판정.** 로그인 전후 토큰 파일(`io/bdq_token` 의 자리) 내용의 다이제스트가 바뀌었고 같은 하위
프로세스가 로그인 뒤 잰 남은 분이 `REMAINING_WARNING_MINUTES`(7시간)를 넘으면 성공이다(2026-11-16
사용자 답 「내용이 바뀌었고 남은 시간이 7시간을 넘으면 성공」). 바뀌었는데 남은 시간을 모르거나(하위
프로세스 시간 초과 · `getTokenTime` 예외 · 꼴이 다른 답) 7시간 이하면 `unconfirmed` 다 — 패키지가
실패 때 토큰 파일을 다른 글로 덮는 꼴이면 틀린 비밀번호일 수 있으니 폼은 저장하지 않고, 자동 길은
성공으로 세지 않고 곧바로 멈추지도 않는다 — 닿지 못함처럼 쉬는 시간과 재시작을 건너는 `misses` 에
들어 성공 없이 `MISS_LIMIT` 번이면 멈춘다(꼴이 다른 답 하나가 곧바로 멈춤이 되지는 않지만, 이어지면
계정 잠김 방지가 이긴다).
그대로(또는 파일 없음)면 표지로 가른다 — 패키지를 못 불러옴은 `unavailable`(시도 없음), 요청을
보내기 전 연결 단계의 양의 증거(`bdq_login_child.is_unreached` — 종류 이름만으로 가르지 않는다)나
하위 프로세스 시간 초과는 `unreached`, 그 밖은 모두 `rejected` 다(애매한 실패도 — 계정 잠김 방지가
불변식). 로그인 동안 토큰 파일을 치우지 않는다. 표지 없음(`no_marker`)은 멈춤은 거절과 같되 화면
낱말은 「로그인 확인 못 함」 이다(`UNCONFIRMED_REJECT_REASONS` — 비밀번호가 틀렸다는 뜻이 아니다).
하나 뺀다 — 표지 없이 시그널로 끝났고(바깥 강제 종료 — 시간 제한으로 끊은 것은 앞의 `unreached`)
마지막 단계 줄이 비밀번호를 보내기 전 단계(`PRE_SEND_STAGES` — `import`)면 `unavailable`(까닭
`import_killed`)이다. 하위 본문은 단계 줄 `login` 을 내보내지 못하면 `login()` 에 들어가지 않으므로
(`bdq_login_child.run`) 그 단계에서 끊긴 시도는 비밀번호가 서버에 가지 않았다 — 다시 해도 계정이
잠기지 않는다(2026-11-20 사용자 답 「쉬고 다시」). 그 밖의 표지 없음(단계 `login` · `time` · 모름 ·
스스로 끝남)은 그대로 멈춤이다.

**잠김 방지.** 폼 제출 한 번에 시도 한 번. 자동 시도(시작 · 조회 중)는 로그인 **앞에** 객체를
멈춤(`attempting`)으로 써 두고(`store.mark_attempting` — 그 쓰기가 실패하면 로그인하지 않는다)
결과로 고쳐 쓴다(`store.record_outcome`). 결과를 적지 못하거나 프로세스가 도중에 끊기면 객체는
멈춤으로 남아 다음 시작이 로그인하지 않는다(안전한 쪽으로 닫힘). `rejected` 는 다시 시도하지 않고
멈춘다 — 프로세스 안에 곧바로 적고(그 `cipher` 의 한 벌은 자동 시도 없음) 객체에 멈춤을
쓴다(재시작마다 다시 시도하지 않게). `unreached` · `unconfirmed` 는 멈추지 않되(D6) 객체의 `misses`
를 하나 올려 재시작을 건너 세고, 성공 없이 `MISS_LIMIT` 번에 닿으면 멈춘다(까닭 `miss_limit`).
관리자가 폼에서 다시 넣어 성공하면 풀린다. 자동 시도는 프로세스 안에서 연달아 `AUTO_ATTEMPT_LIMIT`
번까지(하위 프로세스를 띄운 수 — 보내기 전 끊김은 빼고, 성공에만 0 으로)이고, `unreached` ·
`unavailable` · `unconfirmed` 뒤에는 `UNREACHED_PAUSE_SECONDS` 동안 쉰다.

**보내기 전 끊김의 다시 시도**(2026-11-20 사용자 답). `import_killed` 는 멈추지 않고 객체의 `cuts`
를 하나 올리고 다음 시도 시각(`retry_after` — `CUT_RETRY_SECONDS` 차례로 늘어나는 간격)을
적는다(재시작이 셈을 지우지 않는다). 그 시각 전에는 자동 시도가 모두 쉰다 — 조회 중 자동 시도도,
재시작으로 뜬 시작 로그인도(`SKIP_CUT_WAIT` — 시작은 로그인 없이 `unavailable`/`import_killed` 로
예비 토큰 길에 가고, 그 시각 뒤의 조회 중 자동 시도 · 재시작이 다음 다시 시도다). 다시 시도
`CUT_RETRY_LIMIT`(3)번이 모두 끊기면 멈춘다(까닭 `cut_limit` — `AD-23`). 끊김은 비밀번호를 보내지
않았으므로 프로세스 안 연속 시도 수에 들지 않는다. 셈은 성공 · 넣기(폼 저장)에만 비고, 다른 실패는
셈을 그대로 두고 다음 시도 시각만 비운다. 차례는 둘이다 — 끊긴 시도 자신의 차례(`Attempt.retry` ·
진단 줄 · 로그 — 그 시도가 몇 번째 다시 시도였나, 처음 시도는 0)와 기다리는 차례(`LoginStatus.retry`
· 상태 줄 · `AD-24` — 끊김 k번 뒤 다시 시도 k).

**동시성.** 로그인은 프로세스 잠금 하나로 줄 세운다. 토큰 예외를 본 조회는 그 조회 앞의 토큰
다이제스트를 들고 잠금을 기다리고, 잠금을 얻었을 때 다이제스트가 바뀌었으면(누가 이미 다시 로그인)
로그인하지 않고 바로 다시 조회한다. 공식버전 자동 갱신 스레드도 어댑터를 부르므로 Streamlit 을
import 하지 않는다. 새 배경 스레드를 세우지 않는다.

**다시 로그인의 문.** 토큰 파일 없음(`bigdataquery.exceptions` 의 종류 —
`RELOGIN_EXCEPTIONS`)과 만료 · 무효 토큰(사슬 고리의 글에 `RELOGIN_MESSAGES` 문구 — 「You have
invalid token」. 실측의 응답 코드는 400 이고 판정은 코드를 보지 않는다)에서 다시 로그인한다.
사슬은 `failure_chain` 이다(원인이 있으면 원인, 없으면 문맥, `_CHAIN_LIMIT` 고리까지 — 둘째 고리부터
앱이 만든 예외 앞에서 멈춘다). 만료 · 무효는 패키지 종류가 아니고(바깥 `ConnectionError` · 안쪽
`Exception`, 2026-11-16 사내 실측) 둘의 사슬이 같아 한 길이다 — 바깥 `ConnectionError` 를 연결
실패로 먼저 가르지 않는다. 문구 상수 밖의 토큰 낱말만 맞은 갈래는 알림만이다(어댑터 몫). 문구는
판정에만 쓴다.

**비밀.** 결과 · 로그 · 예외에 계정 · 비밀번호 · 예외 문구 · 하위 출력이 없다 — 예외 종류의
`모듈.이름` 과 짧은 영문 까닭 코드, 진단의 수 · 판만. 토큰 다이제스트도 밖으로 내지
않는다(지문이다).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable, Mapping, MutableMapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, TypeVar

from capa_simulation.auth import names as sso_names
from capa_simulation.io import bdq_login_store as store
from capa_simulation.io import bdq_token, memory_probe
from capa_simulation.io.bdq_login_child import MARKER, STEP_MARKER, STEP_STAGES, VERSION_PACKAGES
from capa_simulation.io.bdq_login_store import LoadResult, LoginSecret, StoredLogin
from capa_simulation.io.container_start_report import (
    APP_WITHHELD_ENVIRONMENT,
    LOGIN_ERROR,
    LOGIN_OK,
    LOGIN_REJECTED,
    LOGIN_STANDING,
    LOGIN_STOPPED,
    ChildDiag,
    ChildMemory,
    LoginStart,
    ProcessClues,
    read_container_start_report,
)

if TYPE_CHECKING:
    from capa_simulation.io.s3_small import S3Target

T = TypeVar("T")

# 하위 프로세스 하나의 시간 제한(패키지 import · 로그인 · 남은 시간 재기까지).
LOGIN_TIMEOUT_SECONDS: Final = 60.0
# 하위 프로세스를 기다리며 그 하위의 최고 RSS 를 읽는 틈(초).
CHILD_POLL_SECONDS: Final = 0.1
# 시간 제한을 넘겨 끊은 뒤 남은 출력을 거두는 상한(초) — 손자 프로세스가 파이프를 쥐어도 멈추지
# 않는다.
CHILD_DRAIN_SECONDS: Final = 2.0
# 프로세스 안 연속 자동 시도 상한 — 하위 프로세스를 띄운 수(보내기 전 끊김은 빼고), 성공에만 0 으로.
AUTO_ATTEMPT_LIMIT: Final = 3
# 성공 없이 이어진 닿지 못함 · 확인 못 함의 상한 — 객체에 적어 재시작을 건너 센다. 닿으면 멈춤.
MISS_LIMIT: Final = 3
# `unreached` · `unavailable` · `unconfirmed` 뒤 자동 시도를 쉬는 초.
UNREACHED_PAUSE_SECONDS: Final = 300.0
# 비밀번호를 보내기 전에 바깥에서 끊긴 자동 시도(`import_killed`) 뒤 다음 시도까지 기다리는 초 —
# n번째 끊김 뒤 n번째 값(쉬는 시간에서 두 배씩). 그 수가 다시 시도 상한이다 — 그만큼 다시 해도
# 끊기면 멈춘다.
CUT_RETRY_SECONDS: Final[tuple[float, ...]] = (300.0, 600.0, 1200.0)
CUT_RETRY_LIMIT: Final = len(CUT_RETRY_SECONDS)
# 하위 본문이 `login()`(비밀번호를 서버에 보냄)에 들어가기 전 단계 — 단계 줄 `login` 을 내보내지
# 못하면 `login()` 에 들어가지 않으므로, 받은 마지막 단계 줄이 이 가운데 하나면 보내지 않았다.
PRE_SEND_STAGES: Final = frozenset({"import"})
# 이 분을 넘게 남아야 성공(수명 8시간 — 막 받은 토큰은 7시간 넘게 남는다). 이하 · 모름은
# `unconfirmed`.
REMAINING_WARNING_MINUTES: Final = 7 * 60
# 다시 로그인을 거는 예외 종류(`모듈.이름`). 사슬(`failure_chain`)의 고리가 그 종류(또는 하위
# 종류)면 건다.
RELOGIN_EXCEPTIONS: Final[tuple[str, ...]] = ("bigdataquery.exceptions.TokenNotFoundException",)
# 다시 로그인을 거는 문구(소문자 — `casefold` 로 견준다). 사슬(`failure_chain`)의 고리의 글에 있으면
# 건다. 만료 · 무효 토큰의 `getData` 가 조회 전 토큰 확인에서 내는 안쪽 문구다(두 경우가 같은 글 —
# 실측의 응답 코드는 400 이고, 판정은 글 끝의 응답 코드를 보지 않는다). 판정에만 쓰고 결과 · 로그 ·
# 예외에 싣지 않는다(문구에는 계정이 실릴 수 있다).
RELOGIN_MESSAGES: Final[tuple[str, ...]] = ("you have invalid token",)

Outcome = Literal["ok", "rejected", "unreached", "unavailable", "unconfirmed"]
OUTCOME_OK: Final = "ok"
OUTCOME_REJECTED: Final = "rejected"
OUTCOME_UNREACHED: Final = "unreached"
OUTCOME_UNAVAILABLE: Final = "unavailable"
# 토큰은 바뀌었지만 남은 시간이 7시간을 넘는다고 확인하지 못함 — 성공도 거절도 아니다.
OUTCOME_UNCONFIRMED: Final = "unconfirmed"

# 까닭 코드 — 짧은 영문(멈춤 표시 `stop_reason` 에도 그대로 들어간다).
REASON_TOKEN_UNCHANGED: Final = "token_unchanged"
REASON_LOGIN_RAISED: Final = "login_raised"
REASON_NO_MARKER: Final = "no_marker"
REASON_TIMEOUT: Final = "timeout"
REASON_CONNECTION: Final = "connection"
REASON_IMPORT_FAILED: Final = "import_failed"
REASON_NO_INPUT: Final = "no_input"
REASON_SPAWN_FAILED: Final = "spawn_failed"
REASON_BAD_INPUT: Final = "bad_input"
REASON_BAD_ACCOUNT: Final = "bad_account"
REASON_ENV_TOKEN: Final = "env_token"
REASON_TOKEN_AFTER_LOGIN: Final = "token_after_login"
# 시작 스크립트의 로그인 단계가 예상하지 못하게 멈춤 — 로그인을 시도했는지 모르니 멈춤으로 본다.
REASON_UNEXPECTED: Final = "unexpected"
# 닿지 못함 · 확인 못 함이 성공 없이 `MISS_LIMIT` 번 — 멈춤.
REASON_MISS_LIMIT: Final = "miss_limit"
# 표지 없이 시그널로 끝났고 마지막 단계가 비밀번호를 보내기 전(`PRE_SEND_STAGES`) — `unavailable`.
REASON_IMPORT_KILLED: Final = "import_killed"
# 그 끊김이 다시 시도 `CUT_RETRY_LIMIT` 번에도 이어짐 — 멈춤.
REASON_CUT_LIMIT: Final = "cut_limit"
# 시도 표시를 써 둔 채 결과를 적지 못함(또는 도중에 끊김) — 멈춤(`store.ATTEMPTING_REASON`).
REASON_ATTEMPTING: Final = store.ATTEMPTING_REASON
# 하위 프로세스를 띄우기 전에 돌아온 까닭 — 연속 시도 수에 들지 않는다.
PRE_SPAWN_REASONS: Final = frozenset({REASON_BAD_INPUT, REASON_BAD_ACCOUNT, REASON_ENV_TOKEN})

# `unconfirmed` 의 까닭 — 남은 시간이 7시간 이하 · 모름.
REASON_REMAINING_SHORT: Final = "remaining_short"
REASON_REMAINING_UNKNOWN: Final = "remaining_unknown"
# 거절(멈춤 — 계정 잠김 방지)로 다루되 화면 낱말은 「로그인 확인 못 함」 인 까닭 — 하위 프로세스가
# 표지 없이 끝나 로그인이 받아들여졌는지도 거절됐는지도 모른다(비밀번호가 틀렸다는 뜻이 아니다).
UNCONFIRMED_REJECT_REASONS: Final = frozenset({REASON_NO_MARKER})

# 자동 시도를 건너뛴 까닭.
SKIP_STOPPED: Final = "stopped"
SKIP_ATTEMPT_LIMIT: Final = "attempt_limit"
SKIP_PAUSED: Final = "paused"
# 비밀번호를 보내기 전 끊김 뒤 저장된 다음 시도 시각(`retry_after`) 전 — 시작 · 조회 중 모두
# 기다린다.
SKIP_CUT_WAIT: Final = "cut_wait"
# 시도 표시를 쓰지 못함 — 로그인하지 않았다(멈춤 아님 · 쉰다).
SKIP_UNGUARDED: Final = "unguarded"
# 객체가 그 사이 다른 계정으로 바뀌었거나 없어짐 — 든 한 벌로 로그인하지 않는다.
SKIP_CHANGED: Final = "changed"

# 조회 중 회복에서 로그인 없이 끝난 까닭.
RECOVERY_NO_LOGIN: Final = "no_login"
RECOVERY_RENEWED: Final = "renewed"

# 하위 프로세스에 넘기지 않는 이름 · 접두. 시작 스크립트가 앱에 넘기지 않는 비밀 · 통합인증 비밀과
# 명단 · 이 기능의 키 · S3 · AWS 전부.
CHILD_WITHHELD_ENVIRONMENT: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(
        (
            *APP_WITHHELD_ENVIRONMENT,
            *sso_names.SECRET_ENVIRONMENT,
            *sso_names.WITHHELD_ENVIRONMENT,
            store.SECRET_KEY_ENV,
        )
    )
)
CHILD_WITHHELD_PREFIXES: Final[tuple[str, ...]] = ("CAPA_S3_", "AWS_")

CHILD_SCRIPT: Final = Path(__file__).with_name("bdq_login_child.py")
# 하위 프로세스 본문을 그 폴더를 `sys.path` 에 넣지 않고 돌린다. 앱 패키지 경로 · 사용자 site 는
# 그대로 둔다(`-I` 를 쓰지 않는다 — 사내 패키지가 사용자 site 에 있을 수 있다).
_LAUNCH: Final = "import runpy, sys; runpy.run_path(sys.argv[1], run_name='__main__')"
_NAME: Final = r"[A-Za-z_][A-Za-z0-9_.]{0,199}"
_MARKER_LINE: Final = re.compile(
    rf"{re.escape(MARKER)} stage=(input|import|login|done) error=(-|{_NAME}) net=([01]) "
    rf"minutes=(-|[0-9]{{1,7}}) time_error=(-|{_NAME})"
)
# 단계 줄(`bdq_login_child.step_line`) — 표지와 따로 푼다. 꼴이 어긋나면 진단의 단계 · 판만 빈다.
_VERSION: Final = r"-|\?|[0-9A-Za-z][0-9A-Za-z.+!_-]{0,39}"
_STEP_LINE: Final = re.compile(
    rf"{re.escape(STEP_MARKER)} stage=({'|'.join(STEP_STAGES)})"
    + "".join(rf" {re.escape(name)}=({_VERSION})" for name in VERSION_PACKAGES)
)
# 표준 오류에서 마지막 traceback 을 찾는 머리와, 그 예외 줄 앞마디(종류 이름)의 꼴.
_TRACEBACK_HEAD: Final = "Traceback (most recent call last):"
_EXCEPTION_HEAD: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_.<>]{0,199}")
# 표준 오류에서 보는 끝자락(바이트) — 그 앞은 읽지 않는다.
_STDERR_TAIL_BYTES: Final = 65_536
# 원인을 따라가는 깊이.
_CHAIN_LIMIT: Final = 5

_LOGGER = logging.getLogger("capa_simulation.bdq_login")


# --- 결과 꼴 ----------------------------------------------------------------------------


@dataclass(frozen=True)
class LoginResult:
    """로그인 한 번(또는 시도 전 거절)의 결과. 비밀 · 예외 문구 · 하위 출력이 없다.

    `reason` 은 짧은 영문 까닭 코드, `error_kind` 는 예외 종류의 `모듈.이름`, `remaining_minutes` 는
    로그인 뒤 잰 남은 분(모르면 `None`)이다. `diag` 는 하위 프로세스 진단(띄우지 않았으면 `None`) —
    결과의 같음 판정에는 들지 않는다(같은 갈래의 두 시도는 걸린 초가 달라도 같은 결과다)."""

    outcome: Outcome
    reason: str = ""
    error_kind: str = ""
    remaining_minutes: int | None = None
    diag: ChildDiag | None = field(default=None, compare=False)

    @property
    def ok(self) -> bool:
        return self.outcome == OUTCOME_OK


@dataclass(frozen=True)
class Attempt:
    """자동 시도 한 번 — 건너뛰었으면 `result` 가 `None` 이고 `skipped` 가 까닭. 객체에 시도 표시 ·
    결과 · 멈춤을 쓰지 못했으면 `stop_write` 가 그 까닭이다(결과를 못 적었으면 프로세스 안 멈춤이
    선다). 이 시도로 멈췄으면 `stopped_reason` 이 그 까닭(거절 · 연속 상한). 비밀번호를 보내기 전에
    끊겼으면 `retry` 가 그 시도가 몇 번째 다시 시도였나다(시도 앞 객체의 `cuts` — 처음 시도는 0,
    다시 시도는 1 ~ `CUT_RETRY_LIMIT`). 기다리는 차례(`LoginStatus.retry` — 끊김 k번 뒤 k)와 다르다:
    첫 끊김 뒤 이 값은 0 이고 상태는 1 이다."""

    result: LoginResult | None
    skipped: str = ""
    stop_write: str = ""
    stopped_reason: str = ""
    retry: int = 0


@dataclass(frozen=True)
class Recovery:
    """조회 중 토큰 예외 뒤의 회복. `retry` 면 같은 조회를 한 번 다시 한다. `logged_in` 은 이 회복이
    스스로 로그인해 토큰이 바뀐 것(성공 · 확인 못 함 — 다시 한 조회가 또 토큰 오류면 멈춘다)."""

    retry: bool
    logged_in: bool = False
    attempt: Attempt | None = None
    reason: str = ""
    stored: StoredLogin | None = field(default=None, repr=False)


@dataclass(frozen=True)
class FormResult:
    """폼 제출 한 번. 로그인이 성공하고 저장까지 되면 `saved`. 로그인은 됐는데 저장하지 못했으면
    `save_failure` 가 그 까닭이다(앞서 저장된 계정 · 상태는 그대로). `retry` 는 넣기 때 걸려 있던
    다시 시도 차례(감사 상세 — 저장되면 넣기가 그 셈을 비웠다)."""

    result: LoginResult
    saved: bool = False
    save_failure: str = ""
    retry: int = 0


StartStatus = Literal[
    "off", "absent", "stopped", "ok", "rejected", "unreached", "unavailable", "unconfirmed"
]


@dataclass(frozen=True)
class StartLogin:
    """시작 때 로그인 단계. `off` — 기능이 서지 않음, `absent` — 저장된 계정 없음(지금 길),
    `stopped` — 멈춤이라 로그인 없음, 그 밖은 로그인 결과 갈래. `stored` 는 토큰 파일 이름에 쓸
    계정을 가진 한 벌이다(repr 에 나오지 않는다). `retry` 는 비밀번호를 보내기 전에 끊긴 시작 시도가
    몇 번째 다시 시도였나(`Attempt.retry` — 처음 시도 · 끊기지 않음 · 시도 없음은 0)."""

    status: StartStatus
    reason: str = ""
    failure_kind: str = ""
    result: LoginResult | None = None
    stop_write: str = ""
    stored: StoredLogin | None = field(default=None, repr=False)
    retry: int = 0


@dataclass(frozen=True)
class LastAttempt:
    """마지막 시도 — KST 시각 · 자동인가 · 결과 · 끊긴 시도면 그 시도가 몇 번째 다시 시도였나
    (`Attempt.retry` — 처음 시도는 0)."""

    at: str
    auto: bool
    result: LoginResult
    retry: int = 0


@dataclass(frozen=True)
class LoginStatus:
    """화면 · 알림이 읽는 한 벌. `state` — `none`(저장된 계정 없음) · `ok` · `stopped`."""

    load: LoadResult
    last: LastAttempt | None
    streak: int
    paused: bool
    stopped_in_process: bool
    # 프로세스 안 멈춤의 까닭 — 이번 시작이 남긴 멈춤(`start_in_app`) · 이 프로세스의 거절 · 결과를
    # 적지 못함. 없으면 빈 글.
    process_reason: str = ""

    @property
    def state(self) -> Literal["none", "ok", "stopped"]:
        stored = self.load.stored
        if stored is None:
            return "none"
        stopped = (
            stored.stopped
            or stored.misses >= MISS_LIMIT
            or stored.cuts > CUT_RETRY_LIMIT
            or self.stopped_in_process
        )
        return "stopped" if stopped else "ok"

    @property
    def active(self) -> bool:
        """자동 로그인이 서 있나(저장된 계정이 있고 멈춤이 아님)."""
        return self.state == "ok"

    @property
    def stop_reason(self) -> str:
        stored = self.load.stored
        if stored is not None and stored.stop_reason:
            return stored.stop_reason
        if self.stopped_in_process and self.process_reason:
            return self.process_reason
        if stored is not None and stored.misses >= MISS_LIMIT:
            return REASON_MISS_LIMIT
        if stored is not None and stored.cuts > CUT_RETRY_LIMIT:
            return REASON_CUT_LIMIT
        if self.stopped_in_process and self.last is not None:
            return self.last.result.reason
        return ""

    @property
    def retry(self) -> int:
        """보내기 전 끊김 뒤 기다리는 다시 시도 차례 — 끊김 k번 뒤 k(0 — 끊김 없음, 상한을 넘겨
        멈췄으면 마지막으로 쓴 상한). 끊긴 시도 자신의 차례(`LastAttempt.retry`)와 다르다."""
        stored = self.load.stored
        return 0 if stored is None else min(stored.cuts, CUT_RETRY_LIMIT)

    @property
    def retry_at(self) -> str:
        """다음 다시 시도를 기다리는 KST ISO 시각 — 멈춤이 아니고 기다리는 중일 때만(아니면 빈
        글)."""
        stored = self.load.stored
        if stored is None or self.state != "ok" or not _waiting(stored):
            return ""
        return stored.retry_after or ""


@dataclass(frozen=True)
class Marker:
    """하위 프로세스 표지 한 줄을 푼 것."""

    stage: str
    error: str
    net: bool
    minutes: int | None
    time_error: str


# --- 프로세스 상태 ------------------------------------------------------------------------


@dataclass
class _Process:
    streak: int = 0
    paused_until: float = 0.0
    # 프로세스 안에서 멈춘 한 벌(`cipher`)과 그 까닭 — 거절 · 결과를 적지 못함 · 다시 로그인 뒤 토큰
    # 오류. 객체의 멈춤 표시를 쓰지 못했어도 선다.
    stopped_cipher: str = field(default="", repr=False)
    stopped_reason: str = ""
    last: LastAttempt | None = None
    # 멈추지 않은 채 자동 로그인이 서지 못한 갈래(`unreached` · `unconfirmed` · `unavailable`)와 그
    # 까닭 — 관리자 알림(`AD-24`, D6 「알림만」)이 읽는다. 이번 시작 기록에서
    # 이어받고(`start_in_app`) 성공 · 멈춤 · 폼 성공 · 지우기에 걷힌다.
    trouble: str = ""
    trouble_reason: str = ""
    # 이번 시작이 남긴 멈춤(`start_in_app`) — 까닭 코드와, 객체에 멈춤 표시를 아직 써 보지
    # 않았는지. 어느 한 벌인지 모른 채(기동 읽기가 실패했어도) 선다 — 그 사이 객체를 바꿀 길은 이
    # 앱의 폼 하나이고 폼이 성공하면 걷힌다.
    held_reason: str = ""
    held_write: bool = False


_STATE = _Process()
_STATE_LOCK: Final = threading.Lock()
# 로그인을 줄 세우는 잠금 — 자동 · 폼 · 시작 모두.
_LOGIN_LOCK: Final = threading.Lock()
# 시험이 바꿔 끼우는 시계(쉬는 시간).
_monotonic: Callable[[], float] = time.monotonic


def _kst_wall() -> datetime:
    return datetime.now(store.KST)


# 시험이 바꿔 끼우는 벽시계(보내기 전 끊김의 다음 시도 시각 — 재시작을 건너므로 단조 시계가 아니다).
_wall: Callable[[], datetime] = _kst_wall


def is_cut(result: LoginResult) -> bool:
    """비밀번호를 보내기 전에 바깥에서 끊긴 시도인가(`import_killed`)."""
    return result.outcome == OUTCOME_UNAVAILABLE and result.reason == REASON_IMPORT_KILLED


def retry_fraction(retry: int) -> str:
    """다시 시도 차례 「n/3」(감사 상세 칸 값)."""
    return f"{min(max(retry, 0), CUT_RETRY_LIMIT)}/{CUT_RETRY_LIMIT}"


def retry_text(retry: int) -> str:
    """다시 시도 차례의 짧은 꼴 — 「다시 시도 n/3」(화면 값 줄 · 알림 · 로그가 함께 쓴다)."""
    return f"다시 시도 {retry_fraction(retry)}"


def _waiting(stored: StoredLogin) -> bool:
    """보내기 전 끊김 뒤 다음 시도 시각이 아직 오지 않았나. 시각을 읽지 못하면 기다리지 않는다(셈이
    상한을 지킨다)."""
    if stored.cuts <= 0 or not stored.retry_after:
        return False
    try:
        due = datetime.fromisoformat(stored.retry_after)
        return due.tzinfo is not None and _wall() < due
    except (TypeError, ValueError):
        return False


def forget_state() -> None:
    """시험 전용 — 프로세스 상태(연속 시도 · 쉬는 시간 · 멈춤 · 마지막 시도)와 저장 객체 기억을
    지운다."""
    with _STATE_LOCK:
        _STATE.streak = 0
        _STATE.paused_until = 0.0
        _STATE.stopped_cipher = ""
        _STATE.stopped_reason = ""
        _STATE.last = None
        _STATE.held_reason = ""
        _STATE.held_write = False
        _STATE.trouble = ""
        _STATE.trouble_reason = ""
    store.forget_state()


def _reset_after_success() -> None:
    with _STATE_LOCK:
        _STATE.streak = 0
        _STATE.paused_until = 0.0
        _STATE.stopped_cipher = ""
        _STATE.stopped_reason = ""
        _STATE.held_reason = ""
        _STATE.held_write = False
        _STATE.trouble = ""
        _STATE.trouble_reason = ""


def _stop_in_process(cipher: str, reason: str) -> None:
    with _STATE_LOCK:
        _STATE.stopped_cipher = cipher
        _STATE.stopped_reason = reason
        _STATE.trouble = ""
        _STATE.trouble_reason = ""


def _note_trouble(outcome: str, reason: str) -> None:
    with _STATE_LOCK:
        _STATE.trouble = outcome
        _STATE.trouble_reason = reason


def _pause(seconds: float = UNREACHED_PAUSE_SECONDS) -> None:
    with _STATE_LOCK:
        _STATE.paused_until = _monotonic() + seconds


def _note_last(result: LoginResult, *, auto: bool, retry: int = 0) -> None:
    with _STATE_LOCK:
        _STATE.last = LastAttempt(store.kst_text(), auto, result, retry)


def _status_of(loaded: LoadResult) -> LoginStatus:
    with _STATE_LOCK:
        stored = loaded.stored
        stopped_cipher = stored is not None and _STATE.stopped_cipher == stored.cipher
        stopped_here = stored is not None and (stopped_cipher or bool(_STATE.held_reason))
        reason = _STATE.held_reason or (_STATE.stopped_reason if stopped_cipher else "")
        return LoginStatus(
            load=loaded,
            last=_STATE.last,
            streak=_STATE.streak,
            paused=_monotonic() < _STATE.paused_until or (stored is not None and _waiting(stored)),
            stopped_in_process=stopped_here,
            process_reason=reason,
        )


def status() -> LoginStatus:
    """지금 상태(저장 객체 기억은 처음이면 읽는다)."""
    return _status_of(store.load_state())


def peek_status() -> LoginStatus | None:
    """지금 상태를 S3 에 묻지 않고 — 저장 객체를 아직 읽지 않았으면 `None`. 화면 회차마다 도는
    자리(알림)가 쓴다."""
    loaded = store.peek_state()
    return None if loaded is None else _status_of(loaded)


ViewState = Literal["off", "none", "ok", "stopped"]


@dataclass(frozen=True)
class LoginView:
    """알림 · 지금 상태 줄이 읽는 한 벌 — `off`(기능이 서지 않음) · `none`(저장된 계정 없음) ·
    `ok`(서 있음) · `stopped`(멈춤). `live` 는 이 프로세스가 기억한 것에서 읽었나(아니면 시작 기록).
    `trouble` 은 서 있는(`ok`) 채 자동 로그인이 서지 못한 갈래(`unreached` · `unconfirmed` ·
    `unavailable` — 멈추지 않았다, D6)이고 `trouble_reason` 이 그 까닭 코드다. `retry` · `retry_at`
    은 보내기 전 끊김 뒤 다시 시도 차례와 기다리는 KST ISO 시각이다(`LoginStatus.retry` ·
    `retry_at` — 기억이 있을 때만). 계정 · 비밀번호가 없다."""

    state: ViewState
    stop_reason: str = ""
    stopped_at: str = ""
    live: bool = False
    trouble: str = ""
    trouble_reason: str = ""
    retry: int = 0
    retry_at: str = ""

    @property
    def standing(self) -> bool:
        """자동 로그인이 서 있나 — 만료 전 알림(`AD-11`)을 내지 않는다."""
        return self.state == "ok"


def current_view(start: LoginStart | None = None) -> LoginView:
    """지금 자동 로그인 상태 — S3 에 묻지 않는다(화면 회차마다 불러도 된다).

    키가 없거나 꼴이 틀리거나 `managed` 가 아니면 `off` 다(키를 먼저 본다 — 키 없는 서버는 설정
    파일도 읽지 않는다). 이 프로세스가 저장 객체를 읽어 기억했으면(기동 때 `start_in_app`) 그것과
    프로세스 안 멈춤으로, 아직 읽지 않았거나 S3 를 읽지 못했으면 이번 시작 기록(`start` — 결과
    파일의 자동 로그인 칸)으로 가른다. 시작 기록의 거절 · 멈춤 · 예상하지 못한 실패는
    멈춤이다(애매하면 멈춤)."""
    if store.key_problem() is not None or not store.is_managed():
        return LoginView("off")
    live = peek_status()
    if live is not None and live.load.reason != store.REASON_UNREAD:
        if live.state == "stopped":
            stored = live.load.stored
            at = stored.stopped_at if stored is not None and stored.stopped_at else ""
            if not at and live.last is not None:
                at = live.last.at
            return LoginView("stopped", live.stop_reason, at, live=True)
        if live.state == "ok":
            with _STATE_LOCK:
                trouble, why = _STATE.trouble, _STATE.trouble_reason
            return LoginView(
                "ok",
                live=True,
                trouble=trouble,
                trouble_reason=why,
                retry=live.retry,
                retry_at=live.retry_at,
            )
        return LoginView(live.state, live=True)
    with _STATE_LOCK:
        held = _STATE.held_reason
    if held:
        return LoginView("stopped", held)
    if start is None:
        return LoginView("none")
    if start.status in (LOGIN_STOPPED, LOGIN_REJECTED, LOGIN_ERROR):
        return LoginView("stopped", start.reason or REASON_UNEXPECTED)
    if start.status in LOGIN_STANDING:
        trouble = "" if start.status == LOGIN_OK else start.status
        return LoginView("ok", trouble=trouble, trouble_reason=start.reason if trouble else "")
    return LoginView("none")


# --- 하위 프로세스 ------------------------------------------------------------------------


def child_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """로그인 하위 프로세스의 환경 — 비밀 이름 · 접두를 빼고 표준 입출력을 UTF-8 로.

    오류 처리기도 `surrogateescape` 로 정한다 — 인코딩만 적으면 strict 가 되어, 패키지가 UTF-8 로
    풀리지 않던 바이트(경로 · 환경 값)를 찍을 때 POSIX C · C.UTF-8 로캘 기본(surrogateescape)과
    달리 깨진다. 부모는 하위 출력을 `errors="replace"` 로 읽고 표준 입력은 늘 UTF-8 로 보낸다."""
    env = {
        name: value
        for name, value in environ.items()
        if name not in CHILD_WITHHELD_ENVIRONMENT and not name.startswith(CHILD_WITHHELD_PREFIXES)
    }
    env["PYTHONIOENCODING"] = "utf-8:surrogateescape"
    return env


def login_command() -> list[str]:
    """하위 프로세스 명령줄 — 계정 · 비밀번호가 없다."""
    return [sys.executable, "-c", _LAUNCH, str(CHILD_SCRIPT)]


def file_digest(path: Path) -> str | None:
    """파일 내용의 다이제스트(없거나 못 읽으면 `None`). 밖으로 내지 않는다(지문이다)."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def token_digest(account: str, folder: Path | None = None) -> str | None:
    """그 계정 토큰 파일의 다이제스트. 계정이 파일 이름으로 못 쓰는 글이면 `None`."""
    place = bdq_token.credential_dir() if folder is None else folder
    target = bdq_token.token_file_path(place, account)
    return None if target is None else file_digest(target)


def parse_marker(output: bytes) -> Marker | None:
    """하위 표준 출력에서 마지막 표지 줄을 푼다. 꼴이 어긋나면 `None`(표지 없음)."""
    text = output.decode("utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith(f"{MARKER} ")]
    if not lines:
        return None
    found = _MARKER_LINE.fullmatch(lines[-1])
    if found is None:
        return None
    stage, error, net, minutes, time_error = found.groups()
    return Marker(
        stage=stage,
        error="" if error == "-" else error,
        net=net == "1",
        minutes=None if minutes == "-" else int(minutes),
        time_error="" if time_error == "-" else time_error,
    )


def parse_steps(output: bytes) -> tuple[str, dict[str, str]]:
    """하위 표준 출력의 마지막 단계 줄 → (단계, 배포 → 판). 단계 줄이 없거나 마지막 줄의 꼴이
    어긋나면 `("", {})` — 표지 판정과 따로다."""
    text = output.decode("utf-8", errors="replace")
    lines = [
        line.strip() for line in text.splitlines() if line.strip().startswith(f"{STEP_MARKER} ")
    ]
    if not lines:
        return "", {}
    found = _STEP_LINE.fullmatch(lines[-1])
    if found is None:
        return "", {}
    stage, *versions = found.groups()
    return stage, dict(zip(VERSION_PACKAGES, versions, strict=True))


def stderr_kind(stderr: bytes, secrets: Iterable[str]) -> str:
    """표준 오류 끝자락의 마지막 traceback 이 끝난 예외 줄의 종류 이름(`모듈.이름`). traceback 이
    없거나 꼴이 낯설면 빈 글. 그 이름이 계정 · 비밀번호(`secrets`)를 품거나 그 안에 들면 버린다 —
    표준 오류는 패키지가 쓰는 글이라 값이 실릴 수 있다. 글은 돌려주지 않는다.

    traceback 머리는 줄 끝에서 찾는다 — 비밀번호 프롬프트(「Password: 」)를 줄바꿈 없이
    남기는 길(Windows 의 `getpass.fallback_getpass` 는 POSIX 와 달리 뒤에 줄바꿈을 쓰지
    않는다)에서는 머리가 프롬프트 뒤 같은 줄에 붙는다."""
    text = stderr[-_STDERR_TAIL_BYTES:].decode("utf-8", errors="replace")
    lines = text.splitlines()
    heads = [index for index, line in enumerate(lines) if line.rstrip().endswith(_TRACEBACK_HEAD)]
    if not heads:
        return ""
    head = ""
    for line in lines[heads[-1] + 1 :]:
        if line and not line[:1].isspace():
            head = line.split(":", 1)[0].strip()
            break
    if not _EXCEPTION_HEAD.fullmatch(head):
        return ""
    folded = head.casefold()
    for secret in secrets:
        value = secret.casefold()
        if value and (value in folded or folded in value):
            return ""
    return re.sub(r"[^A-Za-z0-9_.]", "_", head)


def _signal_name(exit_code: int | None) -> str:
    """POSIX 에서 시그널로 죽은 종료 코드(음수)의 시그널 이름. 그 밖은 빈 글."""
    if exit_code is None or exit_code >= 0 or os.name != "posix":
        return ""
    try:
        return signal.Signals(-exit_code).name
    except ValueError:
        return f"SIG{-exit_code}"


def child_diag(
    exit_code: int | None,
    seconds: float,
    stdout: bytes,
    stderr: bytes,
    *,
    secrets: Iterable[str],
    memory: ChildMemory | None = None,
    process: ProcessClues | None = None,
) -> ChildDiag:
    """하위 프로세스 한 번의 진단 — 종료 코드 · 시그널 · 걸린 초 · 단계 줄 · 표준 오류 마지막 예외
    종류 · 메모리 단서(`memory` — `memory_probe.child_memory`) · 띄우기 앞 프로세스 단서(`process`
    — `memory_probe.process_clues`). 하위 출력 · 표준 오류 글은 싣지 않는다."""
    stage, versions = parse_steps(stdout)
    return ChildDiag(
        exit_code=exit_code,
        signal=_signal_name(exit_code),
        seconds=round(max(seconds, 0.0), 1),
        stage=stage,
        stderr_kind=stderr_kind(stderr, secrets),
        bigdataquery=versions.get("bigdataquery", ""),
        getpass_asterisk=versions.get("getpass_asterisk", ""),
        memory=memory,
        process=process,
    )


def _output_bytes(value: object) -> bytes:
    return value if isinstance(value, bytes) else b""


@dataclass(frozen=True)
class _ChildRun:
    """하위 프로세스 한 번을 띄워 기다린 결과 — 종료 코드(시간 제한으로 끊었으면 `None`) · 받은
    출력 · 끊음 · 띄우지 못함 · 그 하위 자신의 최고 RSS(바이트, 못 읽으면 `None`)."""

    exit_code: int | None = None
    output: bytes = b""
    errors: bytes = b""
    timed_out: bool = False
    spawn_failed: bool = False
    peak_bytes: int | None = None


def _drain(child: subprocess.Popen[bytes], output: bytes, errors: bytes) -> tuple[bytes, bytes]:
    """끊은 하위의 남은 출력까지 거둔다 — `CHILD_DRAIN_SECONDS` 안에 파이프가 닫히지 않으면 그때까지
    받은 것."""
    try:
        out, err = child.communicate(timeout=CHILD_DRAIN_SECONDS)
    except subprocess.TimeoutExpired as waiting:
        if isinstance(waiting.output, bytes):
            output = waiting.output
        if isinstance(waiting.stderr, bytes):
            errors = waiting.stderr
        return output, errors
    return _output_bytes(out), _output_bytes(err)


def _wait_child(child: subprocess.Popen[bytes], data: bytes, limit: float) -> _ChildRun:
    """띄운 하위에 입력을 주고 끝날 때까지 기다린다 — `subprocess.run(…, timeout=limit)` 과 같은
    뜻(넘으면 끊고 받은 출력까지 읽는다)이되, `CHILD_POLL_SECONDS` 마다 그 하위의 최고 RSS 를 읽어
    가장 큰 값을 쥔다. `communicate` 를 짧은 제한으로 되풀이해 부른다 — 시간 초과를 잡고 다시
    불러도 출력을 잃지 않고, 파이프가 차서 하위가 막히지 않는다. 입력은 첫 부름에만 준다(그 부름이
    다 쓰고 닫는다 — 다시 부를 때 입력을 주면 `communicate` 가 거절한다)."""
    deadline = time.monotonic() + limit
    peak = memory_probe.process_peak_bytes(child.pid)
    pending: bytes | None = data
    output = errors = b""
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            child.kill()
            output, errors = _drain(child, output, errors)
            return _ChildRun(output=output, errors=errors, timed_out=True, peak_bytes=peak)
        try:
            out, err = child.communicate(pending, timeout=min(CHILD_POLL_SECONDS, left))
        except subprocess.TimeoutExpired as waiting:
            pending = None
            # 받은 데까지의 누적 출력이다(기다림만 넘긴 갈래는 비어 온다 — 앞 값을 둔다).
            if isinstance(waiting.output, bytes):
                output = waiting.output
            if isinstance(waiting.stderr, bytes):
                errors = waiting.stderr
            peak = memory_probe.higher(peak, memory_probe.process_peak_bytes(child.pid))
            continue
        return _ChildRun(
            exit_code=child.returncode,
            output=_output_bytes(out),
            errors=_output_bytes(err),
            peak_bytes=peak,
        )


def _run_child(command: list[str], data: bytes, env: dict[str, str], limit: float) -> _ChildRun:
    """로그인 하위 프로세스 한 번 — 띄우지 못하면 `spawn_failed`. 기다리다 뜻밖의 예외가 나면 끊고
    그대로 올린다(`subprocess.run` 과 같다)."""
    try:
        child = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=os.name == "posix",
        )
    except OSError:
        return _ChildRun(spawn_failed=True)
    with child:
        try:
            return _wait_child(child, data, limit)
        except BaseException:
            child.kill()
            raise


def _input_problem(account: str, password: str) -> str | None:
    """표준 입력 줄 약속을 깨는 값(빈 값 · 줄바꿈)."""
    if not account or not password:
        return REASON_BAD_INPUT
    if any(mark in account or mark in password for mark in ("\n", "\r", "\0")):
        return REASON_BAD_INPUT
    if account != account.strip():
        return REASON_BAD_INPUT
    return None


def killed_before_send(exit_code: int | None, stage: str) -> bool:
    """하위 프로세스가 시그널로 끝났고(POSIX 음수 종료 코드 — 바깥 강제 종료, 시간 제한으로 끊은
    것은 종료 코드가 없다) 받은 마지막 단계 줄이 비밀번호를 보내기 전 단계(`PRE_SEND_STAGES`)인가.
    단계를 모르면(단계 줄 없음 · 꼴이 어긋남) 아니다 — 양의 증거만 받는다."""
    return exit_code is not None and exit_code < 0 and stage in PRE_SEND_STAGES


def _judge(
    *,
    changed: bool,
    marker: Marker | None,
    timed_out: bool,
    spawn_failed: bool,
    cut_before_send: bool = False,
) -> LoginResult:
    if changed:
        minutes = marker.minutes if marker is not None and marker.stage == "done" else None
        if minutes is not None and minutes > REMAINING_WARNING_MINUTES:
            return LoginResult(OUTCOME_OK, remaining_minutes=minutes)
        reason = REASON_REMAINING_UNKNOWN if minutes is None else REASON_REMAINING_SHORT
        error_kind = ""
        if marker is not None:
            error_kind = marker.error if marker.stage == "login" else marker.time_error
        return LoginResult(OUTCOME_UNCONFIRMED, reason, error_kind, minutes)
    if spawn_failed:
        return LoginResult(OUTCOME_UNAVAILABLE, REASON_SPAWN_FAILED)
    if timed_out:
        return LoginResult(OUTCOME_UNREACHED, REASON_TIMEOUT)
    if marker is None:
        if cut_before_send:
            return LoginResult(OUTCOME_UNAVAILABLE, REASON_IMPORT_KILLED)
        return LoginResult(OUTCOME_REJECTED, REASON_NO_MARKER)
    if marker.stage == "input":
        return LoginResult(OUTCOME_UNAVAILABLE, REASON_NO_INPUT)
    if marker.stage == "import":
        return LoginResult(OUTCOME_UNAVAILABLE, REASON_IMPORT_FAILED, marker.error)
    if marker.stage == "login":
        if marker.net:
            return LoginResult(OUTCOME_UNREACHED, REASON_CONNECTION, marker.error)
        return LoginResult(OUTCOME_REJECTED, REASON_LOGIN_RAISED, marker.error)
    return LoginResult(OUTCOME_REJECTED, REASON_TOKEN_UNCHANGED)


def _precheck(
    account: str,
    password: str,
    *,
    folder: Path | None,
    environ: Mapping[str, str] | None,
) -> LoginResult | None:
    """하위 프로세스를 띄우기 전 거절(`PRE_SPAWN_REASONS` — 빈 값 · 줄바꿈 · 파일 이름으로 못 쓰는
    계정 · 패키지가 파일보다 먼저 읽는 토큰 환경변수가 있음). 띄울 수 있으면 `None`."""
    env = os.environ if environ is None else environ
    problem = _input_problem(account, password)
    if problem is not None:
        return LoginResult(OUTCOME_UNAVAILABLE, problem)
    place = bdq_token.credential_dir() if folder is None else folder
    if bdq_token.token_file_path(place, account) is None:
        return LoginResult(OUTCOME_UNAVAILABLE, REASON_BAD_ACCOUNT)
    if bdq_token.environment_token_set(env):
        return LoginResult(OUTCOME_UNAVAILABLE, REASON_ENV_TOKEN)
    return None


def attempt_login(
    account: str,
    password: str,
    *,
    folder: Path | None = None,
    environ: Mapping[str, str] | None = None,
    timeout: float | None = None,
) -> LoginResult:
    """로그인 하위 프로세스 한 번 — 잠김 방지 장치 없이 그대로 한 번 띄운다(부르는 쪽이 문을
    지킨다).

    `folder` 는 토큰 폴더(기본 `bdq_token.credential_dir()`), `environ` 은 하위 환경의 바탕(기본
    프로세스 환경 — 비밀 이름은 뺀다)이다. 시도 전 거절(빈 값 · 줄바꿈 · 파일 이름으로 못 쓰는
    계정 · 패키지가 파일보다 먼저 읽는 토큰 환경변수가 있음)은 `unavailable` 이고 하위 프로세스를
    띄우지 않는다."""
    env = os.environ if environ is None else environ
    refused = _precheck(account, password, folder=folder, environ=env)
    if refused is not None:
        return refused
    place = bdq_token.credential_dir() if folder is None else folder
    target = bdq_token.token_file_path(place, account)
    if target is None:
        return LoginResult(OUTCOME_UNAVAILABLE, REASON_BAD_ACCOUNT)
    limit = LOGIN_TIMEOUT_SECONDS if timeout is None else timeout
    # 앞뒤 다이제스트 사이에 이 프로세스의 「토큰 넣기」 가 끼면 로그인이 토큰을 바꾼 것으로 읽힌다
    # — 그 쓰기를 막은 채 잰다(로그인 잠금 다음 토큰 쓰기 잠금 차례).
    with bdq_token.holding_token_writes():
        before = file_digest(target)
        # 띄우기 앞 프로세스 단서(막 뜬 pod 와 오래 떠 있던 pod 를 가를 값 — 한 번만)와 하위
        # 프로세스 앞뒤 메모리 단서(바깥 SIGKILL 을 가를 값) — 진단 줄. 예외를 내지 않는다.
        process_before = memory_probe.process_clues()
        memory_before = memory_probe.read()
        started = time.monotonic()
        run = _run_child(
            login_command(),
            f"{account}\n{account}\n{password}\n".encode(),
            child_environment(env),
            limit,
        )
        seconds = time.monotonic() - started
        memory_after = memory_probe.read()
        after = file_digest(target)
    result = _judge(
        changed=after is not None and after != before,
        # 끊었으면 받은 출력에서 단계 줄 · 판만 읽는다(표지는 보지 않는다).
        marker=None if run.timed_out or run.spawn_failed else parse_marker(run.output),
        timed_out=run.timed_out,
        spawn_failed=run.spawn_failed,
        cut_before_send=killed_before_send(run.exit_code, parse_steps(run.output)[0]),
    )
    if run.spawn_failed:
        return result
    diag = child_diag(
        run.exit_code,
        seconds,
        run.output,
        run.errors,
        secrets=(account, password),
        memory=memory_probe.child_memory(memory_before, memory_after, run.peak_bytes),
        process=process_before,
    )
    return replace(result, diag=diag)


def _log(result: LoginResult, *, path: str, retry: int = 0) -> None:
    detail = f" 종류={result.error_kind}" if result.error_kind else ""
    if result.remaining_minutes is not None:
        detail += f" 남은분={result.remaining_minutes}"
    if retry:
        detail += f" {retry_text(retry)}"
    if result.diag is not None:
        detail += f" 진단 {result.diag.code}"
    _LOGGER.warning(
        "BigDataQuery 로그인(%s): 결과=%s 까닭=%s%s",
        path,
        result.outcome,
        result.reason or "-",
        detail,
    )


# --- 자동 시도 ----------------------------------------------------------------------------


def _resolve_target(target: S3Target | None) -> S3Target | None:
    if target is not None:
        return target
    try:
        return store.app_target()
    except Exception:  # 통합인증 설정을 읽지 못해도 멈춤 표시만 못 쓸 뿐이다
        return None


def _write_failure(write: store.WriteResult) -> str:
    """쓰기 실패의 짧은 코드(`까닭:분류`)."""
    return f"{write.reason}:{write.failure_kind}" if write.failure_kind else write.reason


def _persist_stop(stored: StoredLogin, reason: str, target: S3Target | None) -> str:
    """객체에 멈춤 표시를 쓴다. 못 쓰면 그 까닭(빈 글이면 씀). 프로세스 안 멈춤은 먼저 선다."""
    _stop_in_process(stored.cipher, reason)
    resolved = _resolve_target(target)
    if resolved is None:
        return store.WRITE_UNAVAILABLE
    write = store.mark_stopped(resolved, reason, cipher=stored.cipher)
    return "" if write.ok else _write_failure(write)


def _settle(
    stored: StoredLogin, result: LoginResult, target: S3Target, *, retry: int = 0
) -> Attempt:
    """하위 프로세스를 띄운 자동 시도의 결과를 객체와 프로세스에 적는다.

    성공은 `misses` · `cuts` 0 · 멈춤 풂, 거절은 멈춤, 닿지 못함 · 확인 못 함은 `misses` 하나
    더(성공 없이 `MISS_LIMIT` 번이면 멈춤), 비밀번호를 보내기 전 끊김은 `cuts` 하나 더와 다음 시도
    시각(`CUT_RETRY_SECONDS` — 다시 시도 `CUT_RETRY_LIMIT` 번을 넘기면 멈춤), 패키지 · 하위
    프로세스가 서지 못함(로그인 시도 없음)은 그대로다. 끊김 밖의 결과는 다음 시도 시각을 비운다(그
    시각의 다시 시도를 이 시도가 썼다). 결과를 적지 못하면 객체는 앞서 써 둔 시도 표시(멈춤)로 남고
    이 프로세스도 그 한 벌을 멈춘다. `retry` 는 끊긴 이 시도 자신의 차례(`Attempt.retry`)다."""
    stopped = False
    reason: str | None = None
    misses = stored.misses
    cuts = stored.cuts
    retry_after: str | None = None
    wait = UNREACHED_PAUSE_SECONDS
    if result.ok:
        misses = cuts = 0
    elif result.outcome == OUTCOME_REJECTED:
        stopped, reason = True, result.reason or REASON_TOKEN_UNCHANGED
    elif result.outcome in (OUTCOME_UNREACHED, OUTCOME_UNCONFIRMED):
        misses = stored.misses + 1
        if misses >= MISS_LIMIT:
            stopped, reason = True, REASON_MISS_LIMIT
    elif is_cut(result):
        cuts = stored.cuts + 1
        if cuts > CUT_RETRY_LIMIT:
            stopped, reason = True, REASON_CUT_LIMIT
        else:
            wait = CUT_RETRY_SECONDS[cuts - 1]
            retry_after = store.kst_text(_wall() + timedelta(seconds=wait))
    write = store.record_outcome(
        target,
        cipher=stored.cipher,
        stopped=stopped,
        reason=reason,
        misses=misses,
        cuts=cuts,
        retry_after=retry_after,
    )
    failure = "" if write.ok else _write_failure(write)
    if result.ok:
        _reset_after_success()
    elif not stopped:
        _pause(wait)
        _note_trouble(result.outcome, result.reason)
    if stopped or failure:
        _stop_in_process(stored.cipher, reason if reason is not None else REASON_ATTEMPTING)
    return Attempt(result, stop_write=failure, stopped_reason=reason or "", retry=retry)


def _auto_attempt_locked(
    stored: StoredLogin,
    *,
    target: S3Target | None,
    folder: Path | None,
    environ: Mapping[str, str] | None,
    path: str,
) -> Attempt:
    """자동 시도 한 번 — `_LOGIN_LOCK` 을 쥔 채 부른다.

    멈춤(객체 · 프로세스 안 · 이번 시작이 남긴 것 — `held_reason`)이면 로그인하지 않고, 시작의
    거절을 아직 객체에 써 보지 않았으면 한 번 써 본다. 연속 상한 · 쉬는 중이면 건너뛰고, 보내기 전
    끊김의 다음 시도 시각 전이면 `SKIP_CUT_WAIT` 로 건너뛴다(시작 로그인도 그 시각을 기다린다).
    띄우기 전 거절은 시도 표시 없이 돌아온다. 그 밖은 시도 표시를 먼저 쓰고(실패하면 로그인하지
    않는다) 로그인한 뒤 결과를 적는다(`_settle`). 보내기 전 끊김은 연속 시도 수에서 도로 빼고, 그
    시도가 몇 번째 다시 시도였나(시도 앞 `cuts` — 처음 시도는 0)를 마지막 시도 · 로그 · 결과에
    싣는다."""
    with _STATE_LOCK:
        held = _STATE.held_reason
        write_held = bool(held) and _STATE.held_write and not stored.stopped
        if write_held:
            _STATE.held_write = False
        stopped = (
            stored.stopped
            or stored.misses >= MISS_LIMIT
            or stored.cuts > CUT_RETRY_LIMIT
            or _STATE.stopped_cipher == stored.cipher
            or bool(held)
        )
    if stopped:
        if write_held:
            return Attempt(None, SKIP_STOPPED, stop_write=_persist_stop(stored, held, target))
        return Attempt(None, SKIP_STOPPED)
    with _STATE_LOCK:
        if _STATE.streak >= AUTO_ATTEMPT_LIMIT:
            return Attempt(None, SKIP_ATTEMPT_LIMIT)
        if _monotonic() < _STATE.paused_until:
            return Attempt(None, SKIP_PAUSED)
    if _waiting(stored):
        return Attempt(None, SKIP_CUT_WAIT)
    secret = stored.secret
    refused = _precheck(secret.account, secret.password, folder=folder, environ=environ)
    if refused is not None:
        _note_last(refused, auto=True)
        _log(refused, path=path)
        _pause()
        _note_trouble(refused.outcome, refused.reason)
        return Attempt(refused)
    resolved = _resolve_target(target)
    if resolved is None:
        _pause()
        _note_trouble(OUTCOME_UNAVAILABLE, SKIP_UNGUARDED)
        return Attempt(None, SKIP_UNGUARDED, stop_write=store.WRITE_UNAVAILABLE)
    guard = store.mark_attempting(resolved, cipher=stored.cipher)
    if not guard.ok:
        if guard.reason in (store.WRITE_CHANGED, store.WRITE_GONE):
            return Attempt(None, SKIP_CHANGED, stop_write=_write_failure(guard))
        _pause()
        _note_trouble(OUTCOME_UNAVAILABLE, SKIP_UNGUARDED)
        return Attempt(None, SKIP_UNGUARDED, stop_write=_write_failure(guard))
    with _STATE_LOCK:
        _STATE.streak += 1
    result = attempt_login(secret.account, secret.password, folder=folder, environ=environ)
    retry = 0
    if is_cut(result):
        retry = min(stored.cuts, CUT_RETRY_LIMIT)
        with _STATE_LOCK:
            _STATE.streak = max(_STATE.streak - 1, 0)
    _note_last(result, auto=True, retry=retry)
    _log(result, path=path, retry=retry)
    return _settle(stored, result, resolved, retry=retry)


def _has_relogin_message(error: BaseException) -> bool:
    """그 고리의 글에 `RELOGIN_MESSAGES` 문구가 있나. 글을 만들다 깨지면 없음이다."""
    try:
        text = str(error).casefold()
    except Exception:  # 패키지 예외의 글 만들기가 깨져도 판정은 이어 간다
        return False
    return any(message and message.casefold() in text for message in RELOGIN_MESSAGES)


def _made_by_app(error: BaseException) -> bool:
    """앱이 만든 예외인가 — 종류나 상위 종류가 `capa_simulation` 모듈의 것(어댑터
    `BigDataQueryCallError` · 모듈 창구 `BigDataQueryError` 따위)."""
    return any(
        kind.__module__ == "capa_simulation" or kind.__module__.startswith("capa_simulation.")
        for kind in type(error).__mro__
    )


def failure_chain(error: BaseException) -> list[BaseException]:
    """`error` 와 그 앞 고리들 — 원인(`__cause__`)이 있으면 원인, 없으면 문맥(`__context__`)을 따라
    `_CHAIN_LIMIT` 고리까지(traceback 이 보여 주는 차례). 돌아오는 사슬은 끊는다.

    둘째 고리부터는 앱이 만든 예외(`_made_by_app`)를 만나면 그 고리를 넣지 않고 멈춘다 — 호출자가
    앞 실패를 처리하는 `except` 안에서 다시 조회하면 새 실패의 문맥이 그 앞 실패(어댑터가 감싼
    것)여서, 그 너머의 앞 토큰 실패를 새 실패의 근거로 읽지 않게. 감싼 예외의 글은 패키지 글을
    옮겨 싣기도 하니 그 고리의 글도 보지 않는다. 패키지 사슬에는 앱 예외가 끼지 않는다."""
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in chain and len(chain) < _CHAIN_LIMIT:
        if chain and _made_by_app(current):
            break
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def is_relogin_error(error: BaseException) -> bool:
    """다시 로그인을 걸 예외인가 — 사슬(`failure_chain`)의 고리 가운데 그 종류나 상위 종류가
    `RELOGIN_EXCEPTIONS` 에 있거나 그 글에 `RELOGIN_MESSAGES` 문구가 있는 것. 패키지를 import 하지
    않는다. 문구는 판정에만 쓰고 돌려주지 않는다."""
    for link in failure_chain(error):
        for kind in type(link).__mro__:
            if f"{kind.__module__}.{kind.__qualname__}" in RELOGIN_EXCEPTIONS:
                return True
        if _has_relogin_message(link):
            return True
    return False


def recover_after_token_failure(
    seen_digest: str | None,
    *,
    target: S3Target | None = None,
    folder: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Recovery:
    """조회가 토큰 예외를 본 뒤 — 잠금을 기다리고, 그 사이 토큰이 바뀌었으면 로그인 없이 다시 조회,
    아니면 자동 시도 한 번. `seen_digest` 는 그 조회 앞의 토큰 다이제스트(`token_digest`)다. 예외를
    내지 않는다."""
    with _LOGIN_LOCK:
        try:
            stored = store.current()
        except Exception:  # 저장 객체를 읽다 깨져도 조회 실패는 그대로 올라간다
            stored = None
        if stored is None:
            return Recovery(False, reason=RECOVERY_NO_LOGIN)
        if token_digest(stored.secret.account, folder) != seen_digest:
            return Recovery(True, reason=RECOVERY_RENEWED, stored=stored)
        attempt = _auto_attempt_locked(
            stored, target=target, folder=folder, environ=environ, path="조회"
        )
    # 확인 못 한 로그인도 토큰은 바뀌었다 — 같은 조회를 한 번 다시 하고, 또 토큰 오류면 멈춘다(D4).
    # 이 시도로 이미 멈췄으면(연속 상한) 다시 조회만 하고 멈춤을 또 쓰지 않는다.
    retry = attempt.result is not None and attempt.result.outcome in (
        OUTCOME_OK,
        OUTCOME_UNCONFIRMED,
    )
    logged_in = retry and not attempt.stopped_reason
    return Recovery(retry, logged_in=logged_in, attempt=attempt, stored=stored)


def _stop_after_retry(recovery: Recovery, target: S3Target | None) -> None:
    """스스로 다시 로그인한 뒤 다시 한 조회가 또 토큰 오류 — 멈춘다(저장). 로그인 잠금 아래에서,
    지금 기억한 한 벌이 그 로그인의 한 벌일 때만 — 그 사이 폼이 다른 계정을 넣었거나 지웠으면 새
    계정을 멈추지 않는다."""
    stored = recovery.stored
    if stored is None:
        return
    with _LOGIN_LOCK:
        try:
            now = store.current()
        except Exception:  # 기억을 읽다 깨지면 든 한 벌로 멈춘다(안전한 쪽)
            now = stored
        if now is None or now.cipher != stored.cipher:
            return
        failed = LoginResult(OUTCOME_REJECTED, REASON_TOKEN_AFTER_LOGIN)
        _note_last(failed, auto=True)
        _log(failed, path="조회")
        try:
            _persist_stop(now, REASON_TOKEN_AFTER_LOGIN, target)
        except Exception:  # 멈춤 표시를 못 써도 프로세스 안 멈춤은 섰다
            _LOGGER.warning("BigDataQuery 로그인 멈춤 표시를 쓰지 못함")


def run_with_relogin(
    query: Callable[[], T],
    *,
    target: S3Target | None = None,
    folder: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> T:
    """조회 한 번을 돌리고, 토큰 예외(`is_relogin_error`)면 다시 로그인 → 같은 조회를 한 번 다시
    한다.

    저장된 계정이 없으면 `query()` 를 그대로 부른다(지금과 같다). 다시 한 조회의 예외는 첫 실패를
    처리하는 블록 밖에서 나므로 첫 토큰 예외가 그 사슬에 붙지 않는다. 스스로 로그인한 뒤 또 토큰
    오류면 멈춘다(저장). `query` 는 부를 때마다 계정에 딸린 인자를 다시 읽어야 한다(계정이 폼으로
    바뀌었을 수 있다)."""
    try:
        stored = store.current()
    except Exception:  # 저장 객체를 읽다 깨져도 조회는 지금처럼 돈다
        stored = None
    if stored is None:
        return query()
    seen = token_digest(stored.secret.account, folder)
    recovery: Recovery | None = None
    try:
        return query()
    except Exception as error:
        if not is_relogin_error(error):
            raise
        recovery = recover_after_token_failure(seen, target=target, folder=folder, environ=environ)
        if not recovery.retry:
            raise
    try:
        return query()
    except Exception as again:
        if recovery.logged_in and is_relogin_error(again):
            _stop_after_retry(recovery, target)
        raise


# --- 폼 · 지우기 · 시작 ---------------------------------------------------------------------


def login_from_form(
    account: str,
    password: str,
    entered_by_login_id: str,
    *,
    target: S3Target | None = None,
    key: bytes | None = None,
    folder: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> FormResult:
    """Admin 폼 제출 한 번 — 시도 한 번. 성공하면 저장(상태 `ok` — 멈춤도 풀리고 `misses` · 끊김
    셈도 빈다), 실패면 저장하지 않고 앞서 저장된 계정 · 상태를 그대로 둔다(폼은 끊겨도 다시 하지
    않는다). 기능이 서지 않으면 시도하지 않는다."""
    off = store.availability(environ)
    if off is not None:
        return FormResult(LoginResult(OUTCOME_UNAVAILABLE, off))
    resolved_key = key if key is not None else store.secret_key(environ)
    resolved_target = _resolve_target(target)
    if resolved_key is None or resolved_target is None:
        return FormResult(LoginResult(OUTCOME_UNAVAILABLE, store.REASON_NO_TARGET))
    with _LOGIN_LOCK:
        seen = store.peek_state()
        before = None if seen is None else seen.stored
        retry = 0 if before is None else min(before.cuts, CUT_RETRY_LIMIT)
        result = attempt_login(account, password, folder=folder, environ=environ)
        _note_last(result, auto=False)
        _log(result, path="폼")
        if not result.ok:
            return FormResult(result, retry=retry)
        write = store.save_login(
            resolved_target, resolved_key, LoginSecret(account, password), entered_by_login_id
        )
        if not write.ok:
            failure = f"{write.reason}:{write.failure_kind}" if write.failure_kind else write.reason
            return FormResult(result, save_failure=failure, retry=retry)
        _reset_after_success()
    return FormResult(result, saved=True, retry=retry)


def forget_login(target: S3Target | None = None) -> store.WriteResult:
    """지우기 단추 — 객체를 지우고 프로세스 상태를 처음으로."""
    resolved = _resolve_target(target)
    if resolved is None:
        return store.WriteResult(False, store.WRITE_UNAVAILABLE)
    with _LOGIN_LOCK:
        write = store.delete_login(resolved)
        if write.ok:
            _reset_after_success()
    return write


def start_login(environ: Mapping[str, str], *, folder: Path | None = None) -> StartLogin:
    """시작 스크립트의 로그인 단계 — `managed` + 키 + 객체 상태 `ok` 면 로그인한다.

    `ok` 면 패키지가 새 토큰을 쓴 것이고, `rejected` 면 멈춤을 저장한다. 닿지 못함 · 확인 못 함이
    연속 상한에 닿았으면 `stopped`(까닭 `miss_limit`), 비밀번호를 보내기 전 끊김이 다시 시도 상한을
    넘겼으면 `stopped`(까닭 `cut_limit`)다. 보내기 전 끊김의 다음 시도 시각(객체의 `retry_after`)
    전이면 로그인하지 않고 `unavailable`(까닭 `import_killed` — 서지 못한 갈래는 그 끊김이고 앱의
    `AD-24` 가 이어받는다)이다 — 재시작이 간격을 건너뛰지 않게, 그 시각 뒤의 조회 중 자동 시도 ·
    재시작이 다음 다시 시도다(셈은 이어진다). 시도 표시를 쓰지 못했으면 로그인 없이
    `unavailable`(까닭 `unguarded`)이다. `unreached` · `unavailable` · `absent` · `stopped` ·
    `off` 는 지금 길(`CAPA_BDQ_TOKEN`)로 가고 `unconfirmed` 는 패키지가 쓴 토큰을 둔다 — 그 판단은
    부르는 쪽 몫이다."""
    off = store.availability(environ)
    if off is not None:
        return StartLogin("off", off)
    try:
        target = store.target_from_environ(environ)
    except Exception:  # 통합인증 설정을 읽다 깨져도 시작은 지금 길로 간다
        target = None
    if target is None:
        return StartLogin("off", store.REASON_NO_TARGET)
    loaded = store.load(target, store.secret_key(environ))
    stored = loaded.stored
    if stored is None:
        return StartLogin("absent", loaded.reason, loaded.failure_kind)
    store.remember(stored)
    if stored.stopped:
        return StartLogin("stopped", stored.stop_reason or "", stored=stored)
    with _LOGIN_LOCK:
        attempt = _auto_attempt_locked(
            stored, target=target, folder=folder, environ=environ, path="시작"
        )
    result = attempt.result
    written = attempt.stop_write
    if result is None:
        if attempt.skipped in (SKIP_UNGUARDED, SKIP_CHANGED):
            return StartLogin("unavailable", attempt.skipped, stop_write=written, stored=stored)
        if attempt.skipped == SKIP_CUT_WAIT:
            return StartLogin("unavailable", REASON_IMPORT_KILLED, stored=stored)
        reason = attempt.skipped
        if stored.misses >= MISS_LIMIT:
            reason = REASON_MISS_LIMIT
        elif stored.cuts > CUT_RETRY_LIMIT:
            reason = REASON_CUT_LIMIT
        return StartLogin("stopped", reason, stop_write=written, stored=stored)
    if attempt.stopped_reason and result.outcome != OUTCOME_REJECTED:
        return StartLogin(
            "stopped",
            attempt.stopped_reason,
            result=result,
            stop_write=written,
            stored=stored,
            retry=attempt.retry,
        )
    return StartLogin(
        result.outcome,
        result.reason,
        result=result,
        stop_write=written,
        stored=stored,
        retry=attempt.retry,
    )


def start_in_app(environ: MutableMapping[str, str]) -> None:
    """앱 기동 때 한 번(`capa_server.py` — 통합인증 기동 뒤, 연결을 받기 전). 예외를 내지 않는다 —
    어떤 실패도 앱 띄우기를 막지 않는다.

    1. 키를 쥐고 프로세스 환경에서 뺀다(`store.take_secret_key`) — 앱이 띄우는 하위 프로세스(aws
       등)가 물려받지 않게.
    2. 이번 시작 스크립트의 로그인 단계가 거절했거나(멈춤 표시를 썼든 못 썼든) 예상하지 못하게
       멈췄으면 그 멈춤을 이 프로세스에 든다(`held_reason`) — 시작 스크립트의 프로세스 안 멈춤은
       앱으로 바뀌며 사라지므로, 첫 토큰 예외가 같은 계정으로 또 로그인하지 않게(계정 잠김 방지).
       아래 읽기가 실패해도 선다. 읽은 한 벌이 시작이 판정한 한 벌이 아니면(넣은 시각
       `entered_at` 이 다름 — 그 뒤 관리자가 다시 넣음) 걷는다. 폼이 성공하거나 지우면 걷힌다.
    3. 시작이 멈추지 않은 채 서지 못했으면(닿지 못함 · 확인 못 함 · 못 함) 그 갈래를 이어받는다 —
       관리자 알림(`AD-24`)이 읽고, 이 프로세스의 다음 자동 시도가 고쳐 쓴다.
    4. 저장 객체를 한 번 읽어 기억한다 — 화면 회차의 첫 읽기가 S3 GET 을 기다리지 않게.
       기능이 서지 않으면 S3 에 묻지 않는다. 시작의 거절이고 객체가 아직 `ok` 면 멈춤 표시를 한 번
       더 써 본다(못 읽었으면 다음 자동 시도 자리에서 써 본다).
    """
    try:
        store.take_secret_key(environ)
    except Exception as error:  # 키를 못 쥐어도 앱은 뜬다 — 기능이 꺼짐으로 머문다
        _LOGGER.warning("BigDataQuery 자동 로그인 키 쥐기 실패: %s", type(error).__name__)
    try:
        report = read_container_start_report()
    except Exception:  # 결과 파일을 못 읽으면 넘겨받을 멈춤도 없다
        report = None
    start = None if report is None else report.bdq_login
    if start is not None and start.status in (LOGIN_REJECTED, LOGIN_ERROR):
        rejected = start.status == LOGIN_REJECTED
        reason = start.reason if start.reason and ":" not in start.reason else ""
        with _STATE_LOCK:
            _STATE.held_reason = reason or (
                REASON_TOKEN_UNCHANGED if rejected else REASON_UNEXPECTED
            )
            _STATE.held_write = rejected
        _LOGGER.warning("BigDataQuery 자동 로그인: 시작의 멈춤을 넘겨받음(%s)", start.status)
    elif start is not None and start.status in LOGIN_STANDING and start.status != LOGIN_OK:
        _note_trouble(start.status, start.reason)
    try:
        loaded = store.load_state()
    except Exception as error:  # 기동 읽기가 깨져도 앱은 뜬다 — 조회가 다시 읽는다
        _LOGGER.warning("BigDataQuery 자동 로그인 기동 읽기 실패: %s", type(error).__name__)
        return
    stored = loaded.stored
    judged = "" if start is None else start.entered_at
    with _STATE_LOCK:
        if stored is not None and judged and stored.entered_at != judged:
            _STATE.held_reason = ""
            _STATE.held_write = False
        write_held = _STATE.held_write and stored is not None and not stored.stopped
        held = _STATE.held_reason
        if write_held:
            _STATE.held_write = False
    if not write_held or stored is None:
        return
    try:
        failure = _persist_stop(stored, held, None)
    except Exception as error:  # 멈춤 표시를 못 써도 프로세스 안 멈춤은 섰다
        failure = type(error).__name__
    _LOGGER.warning("BigDataQuery 자동 로그인: 시작 거절의 멈춤 표시 %s", failure or "씀")
