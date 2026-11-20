# Purpose: CD 서버 시작 점검 결과를 Admin 펼침으로 보이고 그 서버의 토큰 실패를 개발자에게 알린다.

"""서버 시작 점검.

CD 서버에는 셸도 로그도 없어(시작 명령도 못 바꾼다) 시작 스크립트(`scripts/container_start.py`)의
결과를 이 펼침에서 읽는다. 결과 파일이 없는 개발·사내 PC 에서는 아무것도 그리지 않는다. CD 전용
환경변수가 앱에 들어왔는데 결과 파일이 없으면(스크립트가 돌지 않았거나 결과를 쓰지 못함) 그 사실을
「결과 없음」 펼침으로 알린다 — 그러지 않으면 화면이 개발 PC 와 같아 막힌 자리를 가를 수 없다.
파일은 있는데 읽지 못하면(빈 파일·JSON 아님·모르는 꼴) 「결과 파일을 읽지 못함」 펼침이다 —
스크립트는 돌았으니 「결과 없음」 과 가른다.

파일은 작은 JSON 하나라 회차마다 읽고 DB 는 열지 않는다. 비밀값은 파일에 원래 없다(스크립트가
가렸다). 사람이 넣은 값에서 나온 글(까닭·pip 출력)은 표·코드 칸에 그대로 싣고, 캡션에 넣는 값은
`literal_markdown` 으로 싣는다. 「복사」 글은 리뷰로 나가므로 pip 출력의 주소를 가린다
(`share_pip_line`).

S3 키나 `managed` 가 있는 서버는 표에 동기화 줄(aws CLI · ECS 연결 · 버킷 목록 · DB 받기)이 더해지고
캡션에 디스크 · pod 끝 글자 · cgroup · 다운 시간 값이 더해진다 — 사내가 이 값을 보고 정할 것이 있다
(읽기 전용 화면, DuckDB `memory_limit`). 값은 갈래와 수뿐이라 리뷰 압축본에 옮길 수 있다.

**메모리** — 표 끝 「DuckDB 메모리 한도」 줄(지금 연결 설정의 한도 칸 판정 — 틀린 값이면
「실패」 라 제목 판정 `start_verdict` 와 `AD-01` 에 든다)과 사실 줄 끝 메모리 값 줄(RSS · 세션 ·
`cache_data` · DB 마다 DuckDB 회차 끝 표본)은 `memory_diagnostic` 이 짓는다. 둘 다 결과 파일이
아니라 이 프로세스의 지금 값이다.

**부하** — 메모리 값 줄 뒤 부하 값 줄 셋(화면 응답 · CPU 5분 평균 · 동시 세션 — `load_diagnostic`)도
이 프로세스의 지금 값이다. 신호표 문턱(느린 쪽 3초 · CPU 0.7코어 · 연결 25)을 넘으면 개발자 상태
알림 `AD-26`(`render_load_alert` — `app.py` 가 코어 화면 오류 알림 곁에서 부른다)이 선다 — 시작 점검
알림과 같은 판정의 서버만 이벤트 칸 한 자리이고 그 밖은 Streamlit 호출이 없다. 지문은 넘은 문턱
이름뿐이라 값이 오르내려도 다시 뜨지 않는다. 「그 화면으로」 는 Admin Area 의 이 펼침까지다.

**토큰 넣기 · 만료 알림** — 표 아래 「지금 토큰」 줄과 개발자의 「토큰 넣기」 단추 · 팝업, 만료
1시간 전 개발자 알림 `AD-11` 은 `bdq_token_admin` 이 짓는다(이 펼침과 아래 `render_token_alert` 가
부른다).

**BDQ 자동 로그인** — `managed` 서버의 표에는 통합인증 줄 뒤에 「BDQ 자동 로그인」 줄
(`login_rows` — 시작 때 결과: 꺼짐 · 계정 없음 · 정상(남은 시간) · 멈춤(까닭) · 닿지 못함(예비
토큰))이 서고 판정에 든다. 자동 로그인이 멈추면 개발자 알림 `AD-23`(`login_stop_note`)이
서고, 서 있는 동안 `AD-11` 은 해소다. 상태는 S3 에 묻지 않고 읽는다(`login_view` —
`bdq_login.current_view`).

**시작 점검 개발자 알림(`AD-01`)** — 결과 파일이 없거나(CD 서버로 보일 때) 읽지 못했거나, 읽었는데
실패한 단계가 있으면(토큰 줄은 `AD-10` 몫이라 뺀다) 개발자 몫의 모든 화면 회차에 상태 알림으로 낸다
(`render_start_check_alert` — `app.py` 가 토큰 알림 곁에서 부른다, 2026-11-14 「앱 대신 뜨는 화면」
보드 카드 p2-sync 「AD-01 범위를 넓힘」). 키만 넣은 서버나 local 서버의 버킷 연결 실패가 펼침
제목으로만 드러나던 틈을 메운다. 「그 화면으로」 는 Admin Area(이 펼침)다. 알릴 일이 있을 수 없는
프로세스(결과 파일도 CD 전용 환경변수도 없음 — 프로세스 동안 그대로다)는 Streamlit 호출이 없다.
Admin 펼침은 이 알림을 따로 내지 않는다. 줄은 이 펼침을 대상으로 들고 가 다른 화면에서 눌려도
펼침까지 연다(`open_start_check` — 알림 칸의 받는 쪽 `START_CHECK_TARGET_KIND`, 설계 규칙
UI-NAV-01).

**토큰 실패 개발자 알림(`AD-10`)** — 결과 파일이 있는 서버(C-DEP)에서 BigDataQuery 조회가 토큰
갈래로 실패했거나(`company_bigdataquery_adapter.last_query_failed_on_token` — 프로세스의 마지막
판정) 시작 점검 토큰 줄이 「실패」 면 개발자의 모든 화면 회차에 상태 알림으로 낸다
(`render_token_alert` — `app.py` 가 동기화 알림 곁에서 부른다). 토큰은 공용 계정 하나라 고칠 사람이
개발자다. 결과 파일이 없는 서버(개발 · 사내 PC · WebIDE · 시험)는 Streamlit 호출이 없어 요소 순번이
그대로다. `app.py` 는 페이지보다 먼저 표지를 낸다 — 그 회차 페이지 조회의 실패 · 조회 중 자동
로그인의 멈춤은 화면이 끝까지 돈 회차면 회차 끝의 다시 내기(`render_token_alert_late` — 바뀐 것만,
이벤트 칸 한 자리)로 같은 회차에, 화면이 `st.stop()` 으로 멈춘 회차나 프래그먼트 · 팝업 본문만
다시 도는 회차(`app.py` 가 돌지 않아 앞 · 끝 표지가 모두 없다)면 다음 전체 회차의 앞 표지부터
알림이 된다(실패 글은 화면 곁에 바로 선다).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime

import pandas as pd
import streamlit as st
from streamlit.elements.lib.column_types import ColumnConfig

from capa_simulation import alerts
from capa_simulation.components import sso_identity
from capa_simulation.components.admin_view import developer_alerts_visible
from capa_simulation.components.bdq_login_admin import bdq_login_target
from capa_simulation.components.bdq_token_admin import (
    AUTO_LOGIN_FIX,
    ENVIRONMENT_FIX,
    INSTALL_FIX,
    RELOGIN_FIX,
    expiry_alert_note,
    render_token_dialog,
    render_token_row,
    token_line,
)
from capa_simulation.components.diagnostic_copy import (
    diagnostic_text,
    plain_lines,
    render_diagnostic_copy,
    table_lines,
)
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.load_diagnostic import load_lines, load_signal
from capa_simulation.components.memory_diagnostic import (
    MEMORY_LIMIT_STEP_LABEL,
    memory_limit_failed,
    memory_limit_step,
    memory_lines,
)
from capa_simulation.components.sso_status import (
    CLOCK_FORMAT,
    sso_start_step,
    started_environment_caption,
)
from capa_simulation.io import bdq_login, bdq_token
from capa_simulation.io.company_bigdataquery_adapter import last_query_failed_on_token
from capa_simulation.io.container_start_report import (
    BDQ_LOGIN_LABEL,
    BDQ_TOKEN_ENV,
    BDQ_USER_NAME_ENV,
    STATUS_FAILED,
    STATUS_LABELS,
    STEP_LABELS,
    STEP_TOKEN,
    STEPS,
    SYNC_STEP_LABELS,
    SYNC_STEPS,
    UNREADABLE_REPORT_DETAIL,
    UNREADABLE_REPORT_NOTICE,
    ContainerStartReport,
    SyncStart,
    login_reason_text,
    login_step,
    missing_report_detail,
    missing_report_notice,
    read_app_ready,
    read_container_start_report,
    report_file_exists,
    report_verdict,
    seconds_between,
)
from capa_simulation.korea_time import kst_clock
from capa_simulation.navigation import ADMIN_AREA
from capa_simulation.page_tabs_state import tab_label
from capa_simulation.sidebar_status import open_remembered_box, remembered_expander

# 펼침 key. 탭 묶음 위에 서므로 자리를 key 로 고정한다(9장 「조건부 알림 뒤 key 없는 펼침」).
# 편 상태는 기억 칸(`remembered_expander`)에 둔다 — 진단을 읽다 다른 화면(VOC 등)에 다녀와도
# 접히지 않는다(VOC 글 상자와 같은 꼴, E2E r1). 제목 끝(판정)이 바뀌어도 편 상태는 그대로다.
EXPANDER_KEY = "admin_area_container_start_check"
COPY_KEY = "container_start_check"
# BigDataQuery 토큰 실패 개발자 알림(`render_token_alert`).
TOKEN_ALERT_CODE = "AD-10"
# BigDataQuery 자동 로그인 멈춤 개발자 알림(`render_token_alert` 끝).
LOGIN_STOP_ALERT_CODE = "AD-23"
# BigDataQuery 자동 로그인이 멈추지 않은 채 서지 못함(닿지 못함 · 확인 못 함 · 못 함 — D6
# 「알림만」).
LOGIN_TROUBLE_ALERT_CODE = "AD-24"
# 서버 부하 신호표 문턱 넘음 개발자 알림(`render_load_alert`).
LOAD_ALERT_CODE = "AD-26"
# 그 갈래의 알림창 짧은 글 낱말.
_TROUBLE_WORDS = {
    "unreached": "서버에 닿지 못함",
    "unconfirmed": "로그인 확인 못 함",
    "unavailable": "시도하지 못함",
}
PIP_TAIL_LABEL = "pip 출력 끝(자격증명은 가렸습니다)"
COPY_PIP_TAIL_LABEL = "pip 출력 끝(자격증명 · 주소는 가렸습니다)"
ADDRESS_MASK = "<주소>"
# 복사 글의 pip 출력에서 가리는 주소(런북 7-7) — URL 통째, 호스트 없이 서는 경로(`with url: /…`),
# 호스트만 서는 자리(`host='…'` · `located at … is not` · `Connection to … timed out`), IP.
# 파일 이름의 판(`x-1.2.3.tar.gz`)과 모듈 경로(`urllib3.exceptions.…`)는 남고, 갈래를 가르는 글(HTTP
# 상태 · 인증서 · 판 없음)도 그대로다.
_ADDRESS_TAIL = r"[^\s'\"<>()]*[^\s'\"<>():,.;]"
_ADDRESS = re.compile(
    rf"[A-Za-z][A-Za-z0-9+.-]*://{_ADDRESS_TAIL}"
    rf"|(?:(?<=url: )|(?<=': ))/{_ADDRESS_TAIL}"
    r"|(?<![\w./-])(?:[a-z][a-z0-9-]*\.)+[a-z]{2,}(?![\w-]|\.[\w-])"
    r"|(?<![\w.-])\d{1,3}(?:\.\d{1,3}){3}(?![\w-]|\.[\w-])"
)
_GIB = 1024**3
# pod 이름은 사내 식별값이고 이 줄은 리뷰 압축본에 옮긴다. 같은 pod 인지 가르는 데는 끝이면 족하다.
POD_TAIL_CHARS = 5


def step_column_config() -> dict[str, ColumnConfig]:
    """까닭은 기본 폭에서 잘려 넓히고 나머지 칸은 줄인다 — 앱 관리자(개발자)가 셀을 눌러 펴지
    않고 읽는다.
    폭 이름(`"small"` · `"large"`)이 아니라 px 이다 — 표가 stretch 라 남는 폭을 세 칸이 똑같이 나눠
    `"small"` 칸이 줄지 않는다. 셋의 합은 창 1283 의 표 폭 안이라 가로 스크롤이 서지 않는다."""
    return {
        "단계": st.column_config.TextColumn(width=150),
        "결과": st.column_config.TextColumn(width=70),
        "까닭": st.column_config.TextColumn(width=690),
    }


def build_step_table(
    report: ContainerStartReport, extra_rows: Sequence[tuple[str, str, str]] = ()
) -> pd.DataFrame:
    """단계 | 결과 | 까닭. `extra_rows` 는 결과 파일이 아니라 지금 프로세스에서 판정한 줄이다
    (통합인증 — `sso_status.sso_start_step`)."""
    rows = [
        (STEP_LABELS[step], STATUS_LABELS[report.steps[step].status], report.steps[step].reason)
        for step in STEPS
    ]
    rows += list(extra_rows)
    return pd.DataFrame(rows, columns=["단계", "결과", "까닭"])


def clock_text(value: str) -> str:
    """결과 파일의 ISO 시각 → 진단 펼침 시각 꼴(`sso_status.CLOCK_FORMAT` — KST, `korea_time`). 못
    읽으면(시각대 없는 시각 포함) 받은 글 그대로다."""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return kst_clock(moment, CLOCK_FORMAT)
    except (ValueError, OverflowError, OSError):
        return value


def fact_lines(report: ContainerStartReport) -> list[str]:
    """표 아래 한 줄씩 — 깔린 판·토큰 파일·요청자 계정과 자동 로그인 하위 프로세스를 띄웠으면 그
    진단. 값은 마크다운에 글자 그대로 싣는다."""
    version = report.bigdataquery_version
    account = report.user_name_masked
    if report.token_file_exists is None:
        token = "확인하지 못함(폴더에 들어갈 수 없음)" if account else "계정을 몰라 보지 않음"
    elif report.token_file_exists:
        modified = report.token_file_modified_at
        token = (
            f"있음 · 수정 {literal_markdown(clock_text(modified) if modified else '알 수 없음')}"
        )
    else:
        token = "없음"
    if report.token_file_path:
        token += f" · 자리 {literal_markdown(report.token_file_path)}"
    lines = [
        f"**bigdataquery 판** · {literal_markdown(version) if version else '없음'}",
        f"**로그인 토큰 파일** · {token}",
        f"`{BDQ_USER_NAME_ENV}` · {f'있음({literal_markdown(account)})' if account else '없음'}",
    ]
    if report.os_user_masked:
        same = {True: " · 계정 값과 같음", False: " · 계정 값과 다름", None: ""}
        lines.append(
            f"**실행 사용자** · {literal_markdown(report.os_user_masked)}"
            f"{same[report.os_user_is_bdq_user]}"
        )
    if report.home_masked:
        lines.append(f"**HOME** · {literal_markdown(report.home_masked)}")
    child = None if report.bdq_login is None else report.bdq_login.child
    if child is not None:
        lines.append(f"**{BDQ_LOGIN_LABEL} 진단** · {literal_markdown(child.text)}")
    return lines


def login_rows(report: ContainerStartReport) -> list[tuple[str, str, str]]:
    """표에 더하는 「BDQ 자동 로그인」 줄 — 시작 때의 결과(상태 낱말 · 남은 시간 · 까닭). 옛 파일 ·
    `managed` 가 아닌 서버는 빈 목록이다. 계정 · 비밀번호는 결과 파일에 원래 없다."""
    login = report.bdq_login
    step = None if login is None else login_step(login)
    if step is None:
        return []
    return [(BDQ_LOGIN_LABEL, STATUS_LABELS[step.status], step.reason)]


def sync_rows(report: ContainerStartReport) -> list[tuple[str, str, str]]:
    """표에 더하는 동기화 줄. 옛 파일 · 동기화가 없는 서버는 빈 목록이다."""
    if report.sync is None:
        return []
    steps = report.sync.steps
    return [
        (SYNC_STEP_LABELS[name], STATUS_LABELS[steps[name].status], steps[name].reason)
        for name in SYNC_STEPS
        if name in steps
    ]


def _gib(value: int) -> str:
    return f"{value / _GIB:.1f} GiB"


def _core_text(value: float) -> str:
    return f"{value:g}"


def _limits_line(sync: SyncStart) -> str | None:
    parts = []
    if sync.memory_limit_bytes is not None:
        parts.append(f"메모리 {_gib(sync.memory_limit_bytes)}")
    if sync.cpu_limit is not None:
        parts.append(f"CPU {_core_text(sync.cpu_limit)}")
    if sync.logical_cores is not None:
        parts.append(f"논리 코어 {sync.logical_cores}")
    return f"**한도** · {' · '.join(parts)}" if parts else None


def _downtime_line(sync: SyncStart, ready_utc: str | None) -> str | None:
    """받기 · 앱 응답까지. 앱 응답은 시작 스크립트 맨 앞에서 잰다."""
    parts = []
    if sync.pull_seconds is not None:
        parts.append(f"받기 {sync.pull_seconds:.1f}초")
    response = seconds_between(sync.started_at_utc, ready_utc)
    if response is not None:
        parts.append(f"앱 응답까지 {response:.0f}초")
    return " · ".join(parts) if parts else None


def sync_fact_lines(report: ContainerStartReport, ready_utc: str | None) -> list[str]:
    """표 아래 동기화 사실 줄. 잴 수 없었던 값은 줄을 빼 빈 자리를 남기지 않는다."""
    sync = report.sync
    if sync is None:
        return []
    lines: list[str] = []
    if sync.disk_free_bytes is not None and sync.disk_total_bytes is not None:
        free, total = _gib(sync.disk_free_bytes), _gib(sync.disk_total_bytes)
        lines.append(f"**/project 디스크** · 여유 {free} · 전체 {total}")
    if sync.pod:
        lines.append(f"**pod 끝** · {literal_markdown(sync.pod[-POD_TAIL_CHARS:])}")
    limits = _limits_line(sync)
    if limits is not None:
        lines.append(limits)
    if sync.duckdb_memory_limit or sync.duckdb_threads:
        limit = literal_markdown(sync.duckdb_memory_limit or "?")
        threads = literal_markdown(sync.duckdb_threads or "?")
        lines.append(f"**DuckDB 기본값** · memory_limit {limit} · threads {threads}")
    downtime = _downtime_line(sync, ready_utc)
    if downtime is not None:
        lines.append(downtime)
    gap = seconds_between(sync.previous_upload_utc, ready_utc)
    if gap is not None:
        lines.append(f"**앞 pod 마지막 올림 → 이번 앱 준비** · {gap:.0f}초")
    return lines


def report_origin_caption(report: ContainerStartReport) -> str:
    """펼침 맨 위 값 줄 — 언제 남긴 결과인지(「라벨 · 값」).

    넣을 환경변수와 토큰 값 얻는 법(`docs/bigdataquery_webide_setup.md` 「C-DEP CD(배포 서버)」)은
    Guide 「서버 시작 점검」 이 말한다 — 펼침에 길 안내 문장을 늘 띄우지 않는다(설계 규칙
    UI-TXT-03).
    """
    written = report.written_at
    started = literal_markdown(clock_text(written)) if written else "알 수 없음"
    return f"**시작 기록** · {started} · `scripts/container_start.py`"


def share_pip_line(line: str) -> str:
    """pip 출력 한 줄의 주소를 가린다 — 화면은 글자 그대로, 리뷰로 나가는 복사 글은 이 꼴이다."""
    return _ADDRESS.sub(ADDRESS_MASK, line)


def report_text(
    title: str, report: ContainerStartReport, steps: pd.DataFrame, facts: list[str]
) -> str:
    """「복사」 글 — 펼침의 값 줄 · 단계 표 · 사실 줄 · pip 출력 끝. 값은 갈래와 수뿐이고 비밀값은
    결과 파일에 원래 없으며(모듈 설명) pip 출력의 주소는 가린다."""
    missing = missing_environment_line(report)
    pip_tail = [share_pip_line(line) for line in report.pip_tail]
    return diagnostic_text(
        title,
        plain_lines([report_origin_caption(report)]),
        table_lines(steps),
        plain_lines([*facts, *([missing] if missing else [])]),
        [COPY_PIP_TAIL_LABEL, *pip_tail] if pip_tail else [],
    )


def report_fact_lines(report: ContainerStartReport) -> list[str]:
    """표 아래 사실 줄 전부 — 판 · 토큰 · 동기화 값과 시작 때 있던 통합인증 환경변수."""
    lines = fact_lines(report) + sync_fact_lines(report, read_app_ready())
    started = started_environment_caption(
        None if report.sso_environment is None else dict(report.sso_environment)
    )
    return lines if started is None else [*lines, started]


def missing_environment_line(report: ContainerStartReport) -> str | None:
    if not report.missing_environment:
        return None
    names = " · ".join(f"`{name}`" for name in report.missing_environment)
    return f"**시작 때 비어 있던 CD 환경변수** · {names}"


def render_container_start_check() -> None:
    report = read_container_start_report()
    if report is None:
        _render_missing_report()
        return
    title = f"서버 시작 점검 · {start_verdict(report)}"
    # 넷째 줄 「통합인증」 은 결과 파일이 아니라 이 프로세스의 지금 설정에서 판정한다 — 시작
    # 스크립트는 통합인증 값을 검증하지 않고 앱에 넘긴다(이름만 결과 파일에 남긴다). 끝 줄
    # 「DuckDB 메모리 한도」 도 지금 연결 설정의 판정이다(`memory_diagnostic.memory_limit_step`).
    steps = build_step_table(
        report,
        (sso_start_step(), *login_rows(report), *sync_rows(report), memory_limit_step()),
    )
    # 사실 줄 끝의 메모리 · 부하 값 줄은 「지금 토큰」 처럼 이 프로세스의 지금 값이다
    # (`memory_diagnostic` · `load_diagnostic`).
    facts = [*report_fact_lines(report), *memory_lines(), *load_lines()]
    # 「지금 토큰」 은 시작 기록이 아니라 지금 파일에서 읽는다 — 「토큰 넣기」 가 바꾼다.
    token = token_line()
    with remembered_expander(title, icon=":material/rocket_launch:", key=EXPANDER_KEY):
        render_diagnostic_copy(report_text(title, report, steps, [*facts, token]), key=COPY_KEY)
        st.caption(report_origin_caption(report))
        st.dataframe(steps, column_config=step_column_config(), hide_index=True, width="stretch")
        st.caption("  \n".join(facts))
        admin = render_token_row(token)
        missing = missing_environment_line(report)
        if missing is not None:
            st.caption(missing)
        if report.pip_tail:
            st.caption(PIP_TAIL_LABEL)
            # 접힌 진단의 평문 칸 — 줄을 꺾는다(앱 안 멈춤 판 진단 · 모듈 오류 카드와 같은 꼴).
            st.code("\n".join(report.pip_tail), language=None, wrap_lines=True)
    if admin:
        render_token_dialog()


def start_verdict(report: ContainerStartReport) -> str:
    """펼침 제목 끝 판정 — 결과 파일의 판정(`report_verdict`)에, 지금 연결 설정의 DuckDB 한도 칸이
    틀렸으면 「실패 있음」 을 더한다(그 줄은 `AD-01` 에도 든다)."""
    return "실패 있음" if memory_limit_failed() else report_verdict(report)


def _render_missing_report() -> None:
    """결과를 못 읽은 회차 — 파일이 있으면 「결과 파일을 읽지 못함」(꼴이 다름), 없으면 CD 서버로
    보일 때만 「결과 없음」. 펼침 제목이 판정이고 본문은 까닭 캡션이다 — 알릴 조건은 개발자 몫 상태
    알림(`AD-01` — `render_start_check_alert`)이 낸다(알림창 · Alarm)."""
    problem = _missing_problem()
    if problem is None:
        return
    title, notice, _ = problem
    # 넣을 환경변수와 이때 볼 것은 Guide 「서버 시작 점검」 이 안내 문서 절을 가리킨다(UI-TXT-03).
    with remembered_expander(title, icon=":material/rocket_launch:", key=EXPANDER_KEY):
        render_diagnostic_copy(diagnostic_text(title, plain_lines([notice])), key=COPY_KEY)
        st.caption(notice)


def _missing_problem() -> tuple[str, str, str] | None:
    """결과를 못 읽은 서버의 (펼침 제목, 펼침 캡션, 알림 전문). 알릴 일이 아니면 None."""
    if report_file_exists():
        return (
            "서버 시작 점검 · 결과 파일을 읽지 못함",
            UNREADABLE_REPORT_NOTICE,
            UNREADABLE_REPORT_DETAIL,
        )
    missing = missing_report_notice()
    if missing is None:
        return None
    return "서버 시작 점검 · 결과 없음", missing, missing_report_detail(missing)


START_CHECK_ALERT_CODE = "AD-01"
# 알림의 「그 화면으로」 가 Admin Area 에 닿은 뒤 이 펼침을 여는 받는 쪽의 이름
# (`alerts.GotoTarget`).
START_CHECK_TARGET_KIND = "start_check"


def start_check_target() -> alerts.GotoTarget:
    """`AD-01` 이 들고 가는 대상 — 받는 쪽이 이 펼침을 연다(나머지 칸은 쓰지 않는다)."""
    return alerts.GotoTarget(kind=START_CHECK_TARGET_KIND, scenario="-", revision="-")


def open_start_check(_scenario: str, _revision: str) -> None:
    """알림 칸의 「그 화면으로」 콜백이 Admin Area 에 닿은 회차 맨 앞에서 부른다 — 「서버 시작
    점검」 펼침을 연다(설계 규칙 UI-NAV-01 — 데려가면 그 자리까지 연다)."""
    open_remembered_box(EXPANDER_KEY)


def failed_start_steps(report: ContainerStartReport) -> list[tuple[str, str]]:
    """실패한 시작 점검 단계의 (이름, 까닭) — 시작 단계 뒤 동기화 단계 차례. 로그인 토큰 줄은
    토큰 알림(`AD-10`) 몫이라 뺀다. 까닭은 시작 스크립트가 값을 가린 글이다."""
    failed = [
        (STEP_LABELS[step], report.steps[step].reason)
        for step in STEPS
        if step != STEP_TOKEN and report.steps[step].status == STATUS_FAILED
    ]
    if report.sync is not None:
        steps = report.sync.steps
        failed += [
            (SYNC_STEP_LABELS[name], steps[name].reason)
            for name in SYNC_STEPS
            if name in steps and steps[name].status == STATUS_FAILED
        ]
    return failed


def live_failed_steps() -> list[tuple[str, str]]:
    """결과 파일이 아니라 이 프로세스의 지금 설정에서 실패한 단계의 (이름, 까닭) — DuckDB 메모리
    한도 칸이 틀려 기본으로 물러섰을 때 하나."""
    if not memory_limit_failed():
        return []
    _, _, reason = memory_limit_step()
    return [(MEMORY_LIMIT_STEP_LABEL, reason)]


def start_check_alert_possible() -> bool:
    """`AD-01` 을 낼 일이 있을 수 있는 프로세스인가 — 결과 파일이 있거나 CD 전용 환경변수가 앱에
    들어왔다. 둘 다 시작 스크립트 · 실행 환경이 정해 프로세스 동안 그대로라 이벤트 칸 수가 회차마다
    같다."""
    return report_file_exists() or missing_report_notice() is not None


def render_start_check_alert() -> None:
    """서버 시작 점검 개발자 알림(`AD-01`) — `app.py` 가 회차마다 조건 없이 부른다(모듈 설명).

    개발자 몫이 아닌 회차는 해소로 부른다(같은 수의 표지 —
    `admin_view.developer_notes_visible`, 운영 아닌 꺼진 서버는 누구에게나). 지문은 (제목, 실패
    단계 이름들)이다 — 까닭 글이 바뀌어도 같은 단계면 다시 뜨지 않는다."""
    if not start_check_alert_possible():
        return
    report = read_container_start_report()
    text: str | None = None
    full: str | None = None
    content: object = None
    if report is None:
        problem = _missing_problem()
        if problem is not None:
            title, _, detail = problem
            text = f"{title} — 배포 서버 환경변수를 확인하세요"
            full = alerts.plain_text(detail)
            content = title
    else:
        failed = [*failed_start_steps(report), *live_failed_steps()]
        if failed:
            names = " · ".join(name for name, _ in failed)
            text = f"서버 시작 점검 실패 — {names}"
            reasons = " · ".join(f"{name}: {reason}" for name, reason in failed)
            full = (
                f"서버 시작 점검에 실패한 단계가 있습니다 — {reasons}. Admin 「서버 시작 점검」 "
                "단계 표를 보고 배포 서버 환경변수를 고친 뒤 CI/CD 를 다시 누르세요."
            )
            content = ["실패 있음", [name for name, _ in failed]]
    active = text is not None and developer_alerts_visible()
    alerts.state(
        START_CHECK_ALERT_CODE,
        scope=None,
        content=content if active else None,
        active=active,
        text=text if active else None,
        full=full if active else None,
        goto=(tab_label(ADMIN_AREA), ADMIN_AREA.href) if active else None,
        target=start_check_target() if active else None,
    )


def render_load_alert() -> None:
    """서버 부하 개발자 알림(`AD-26`) — `app.py` 가 회차마다 조건 없이 부른다(모듈 설명 「부하」).

    시작 점검 알림과 같은 판정(`start_check_alert_possible` — 프로세스 동안 그대로)이 거짓이면
    Streamlit 호출이 없다. 참이면 회차마다 이벤트 칸 한 자리를 쓰고, 개발자 몫이 아닌 회차는 글
    없는 해소다(`admin_view.developer_alerts_visible`). 지문은 넘은 문턱
    이름(`load_metrics.crossed`)이다."""
    if not start_check_alert_possible():
        return
    signal = load_signal() if developer_alerts_visible() else None
    active = signal is not None
    alerts.state(
        LOAD_ALERT_CODE,
        scope=None,
        content=list(signal.names) if signal is not None else None,
        active=active,
        text=signal.text if signal is not None else None,
        full=signal.full if signal is not None else None,
        goto=(tab_label(ADMIN_AREA), ADMIN_AREA.href) if active else None,
        target=start_check_target() if active else None,
    )


def login_view(report: ContainerStartReport | None) -> bdq_login.LoginView:
    """지금 자동 로그인 상태(S3 에 묻지 않음 — `bdq_login.current_view`). 무엇이 나도 `off` 로
    물러선다 — 모든 화면 회차에 도는 알림 자리다."""
    try:
        return bdq_login.current_view(None if report is None else report.bdq_login)
    except Exception:
        return bdq_login.LoginView("off")


# 토큰 알림 넷이 한 회차 앞에서 낸 표지 — (코드, 조건이 있나, 지문). 회차 끝의 다시 내기가 견준다.
TokenAlertMarks = tuple[tuple[str, bool, str], ...]


def render_token_alert() -> TokenAlertMarks | None:
    """BigDataQuery 토큰 개발자 알림 넷 — 실패 `AD-10`, 만료 1시간 전 `AD-11`
    (`bdq_token_admin.expiry_alert_note`), 자동 로그인 멈춤 `AD-23`, 자동 로그인이 멈추지 않은 채
    서지 못함 `AD-24`. `app.py` 가 화면 앞에서 회차마다 조건 없이 부르고 돌려준 표지를 회차 끝의
    `render_token_alert_late` 에 넘긴다.

    결과 파일이 없는 서버(C-DEP 밖)는 아무것도 부르지 않고 `None` 이다 — 그 파일은 시작 스크립트가
    앱보다 먼저 한 번 쓰므로 프로세스 동안 있고 없음이 바뀌지 않는다. 있는 서버는 회차마다 이벤트 칸
    네 자리를 쓰고 개발자가 아닌 회차는 해소로 부른다. `AD-10` 의 지문은 (시작 점검 토큰 줄 실패,
    조회 토큰 실패) 두 참거짓뿐이다 — 시각 · 계정 · 원문을 싣지 않는다. 자동 로그인 상태는 S3 에
    묻지 않고 읽는다(`login_view`) — 서 있는 동안 `AD-11` 은 해소다.
    """
    if not report_file_exists():
        return None
    notes = token_alert_notes()
    for note in notes:
        alerts.emit([note])
    return tuple(_mark(note) for note in notes)


def render_token_alert_late(marks: TokenAlertMarks | None) -> None:
    """회차 끝의 토큰 알림 다시 내기 — `app.py` 가 화면이 끝까지 돈 회차(멈춤 · 다시 돌기 예외 밖)의
    끝에서 부른다. 앞 표지가 `None`(결과 파일이 없는 서버)이면 아무것도 부르지 않는다.

    조회 실패(`AD-10`) · 조회 중 자동 로그인의 멈춤(`AD-23`) · 서지 못함(`AD-24`)은 화면 본문의
    조회에서 생기는데 토큰 알림은 화면 앞에서 낸다 — 그 회차의 앞 표지는 해소라, 개발자가 실패 글을
    본 그 자리에서 Alarm 을 열어도 없다. 같은 짓기(`token_alert_notes` — 코드 · 범위 · 지문이 앞
    표지와 같다)로 다시 지어 앞 표지와 (조건, 지문)이 달라진 것만 이벤트 칸 한 자리에
    싣는다(없으면 빈 칸 — 갈래와 상관없이 늘 한 자리, 회차의 마지막 칸이라 앞 칸 순번을 밀지
    않는다). 알림 칸 JS 는 한 번 훑을 때 같은 상태 칸의 마지막 표지만 받는다(`latestStateNotes`).
    담아 둔 사건 알림은 꺼내지 않는다(`drain=False`) — 닿는 회차가 지금과 같다.

    덮지 못하는 회차는 둘이다 — 화면이 `st.stop()` 으로 멈춘 회차(여기까지 오지 않는다)와
    프래그먼트 · 팝업 본문만 다시 도는 회차(`app.py` 가 돌지 않아 앞 표지도 이 다시 내기도 없다).
    둘 다 다음 전체 회차의 앞 표지(`render_token_alert`)가 낸다. 프래그먼트 · 팝업을 처음 그리는
    전체 회차 안의 조회는 이 다시 내기가 덮는다."""
    if marks is None:
        return
    moved = [note for note in token_alert_notes() if _mark(note) not in marks]
    alerts.emit(moved, drain=False)


def _mark(note: alerts.AlertNote) -> tuple[str, bool, str]:
    return (str(note.get("code", "")), bool(note.get("active")), str(note.get("fp", "")))


def token_alert_notes() -> list[alerts.AlertNote]:
    """토큰 알림 넷의 표지(그리지 않는다) — `AD-10` · `AD-11` · `AD-23` · `AD-24` 차례. 결과 파일이
    있는 서버에서만 부른다(`render_token_alert` · `render_token_alert_late`)."""
    report = read_container_start_report()
    step = None if report is None else report.steps.get(STEP_TOKEN)
    start_failed = step is not None and step.status == STATUS_FAILED
    query_failed = last_query_failed_on_token()
    view = login_view(report)
    admin = sso_identity.viewer_is_developer()
    active = (start_failed or query_failed) and admin
    failure = alerts.state_note(
        TOKEN_ALERT_CODE,
        scope=None,
        content=(start_failed, query_failed) if active else None,
        active=active,
        text="BigDataQuery 로그인 토큰 실패 — 조회가 막힙니다" if active else None,
        full=(
            _token_alert_text(
                step.reason if start_failed and step else None, query_failed, view=view
            )
            if active
            else None
        ),
        goto=(tab_label(ADMIN_AREA), ADMIN_AREA.href),
        target=_token_alert_target(start_failed, view) if active else None,
    )
    return [
        failure,
        # 만료 1시간 전 개발자 알림(`AD-11`) — 같은 서버 · 같은 회차.
        expiry_alert_note(standing=view.standing),
        # 자동 로그인 멈춤(`AD-23`).
        login_stop_note(view, admin=admin),
        # 자동 로그인이 멈추지 않은 채 서지 못함(`AD-24`).
        login_trouble_note(view, admin=admin),
    ]


def _token_alert_target(start_failed: bool, view: bdq_login.LoginView) -> alerts.GotoTarget | None:
    """`AD-10` 이 들고 갈 대상 — 전문의 첫 할 일이 Admin 「BDQ 자동 로그인」 에 계정 넣기 · 다시
    넣기일 때만(시작 점검 실패도 패키지가 읽는 토큰 환경변수도 아니고 기능이 섬 —
    `_token_alert_text` 와 같은 차례) 그 펼침이다(UI-NAV-01). 그 밖은 대상 없이 Admin Area 다."""
    if start_failed or bdq_token.environment_token_set() or view.state == "off":
        return None
    return bdq_login_target()


def login_stop_note(view: bdq_login.LoginView, *, admin: bool) -> alerts.AlertNote:
    """자동 로그인 멈춤 개발자 알림(`AD-23`) 표지 한 칸. 멈춤이 아니거나 개발자가 아니면 해소다.
    지문은 (멈춘 까닭, 멈춘 시각)이다 — 계정을 싣지 않는다. 다시 넣어 성공하면 풀린다(D3). 「그
    화면으로」 는 Admin 「BDQ 자동 로그인」 펼침까지 연다(대상 `bdq_login` — UI-NAV-01)."""
    active = view.state == "stopped" and admin
    return alerts.state_note(
        LOGIN_STOP_ALERT_CODE,
        scope=None,
        content=[view.stop_reason, view.stopped_at] if active else None,
        active=active,
        text=_login_stop_short(view) if active else None,
        full=_login_stop_text(view) if active else None,
        goto=(tab_label(ADMIN_AREA), ADMIN_AREA.href),
        target=bdq_login_target() if active else None,
    )


def login_trouble_note(view: bdq_login.LoginView, *, admin: bool) -> alerts.AlertNote:
    """자동 로그인이 멈추지 않은 채 서지 못함 개발자 알림(`AD-24` — D6 「알림만」) 표지 한 칸. 시작
    때 · 조회 중 자동 로그인이 서버에 닿지 못했거나 · 로그인을 확인하지 못했거나 · 시도하지 못한 채
    서 있으면(`view.trouble`) 선다. 지문은 갈래 낱말 하나다 — 계정 · 까닭 글을 싣지 않는다. 다음
    자동 시도가 성공하거나 멈추거나 폼에서 다시 넣으면 걷힌다. 「그 화면으로」 는 Admin 「BDQ 자동
    로그인」 펼침까지 연다. 비밀번호를 보내기 전에 끊긴 갈래(`import_killed`)는 짧은 글 · 지문에
    다시 시도 차례(「다시 시도 n/3」 — `bdq_login.retry_text`)가 붙는다 — 차례가 바뀌면 다시
    선다."""
    word = _TROUBLE_WORDS.get(view.trouble, "")
    active = view.state == "ok" and bool(word) and admin
    retry = _cut_retry(view)
    waiting = bdq_login.retry_text(retry) if retry else "다시 시도"
    return alerts.state_note(
        LOGIN_TROUBLE_ALERT_CODE,
        scope=None,
        content=([view.trouble, retry] if retry else [view.trouble]) if active else None,
        active=active,
        text=f"BigDataQuery 자동 로그인 {word} — {waiting} 대기" if active else None,
        full=_login_trouble_text(view, word) if active else None,
        goto=(tab_label(ADMIN_AREA), ADMIN_AREA.href),
        target=bdq_login_target() if active else None,
    )


def _cut_retry(view: bdq_login.LoginView) -> int:
    """서지 못한 갈래가 비밀번호를 보내기 전 끊김이면 그 다시 시도 차례(아니면 0)."""
    return view.retry if view.trouble_reason == bdq_login.REASON_IMPORT_KILLED else 0


def _login_trouble_text(view: bdq_login.LoginView, word: str) -> str:
    """`AD-24` 전문(평문) — 무엇이 서지 못했고 무엇이 그다음인가. 계정 · 비밀번호가 없다."""
    reason = login_reason_text(view.trouble_reason) if view.trouble_reason else "까닭 모름"
    if view.trouble_reason == bdq_login.REASON_IMPORT_KILLED:
        retry = _cut_retry(view)
        turn = f"{bdq_login.retry_text(retry)} — " if retry else ""
        due = f"{clock_text(view.retry_at)} 뒤 " if view.retry_at else ""
        return (
            f"저장된 BigDataQuery 계정의 자동 로그인이 {word}({reason} — 비밀번호를 "
            f"보내기 전). {turn}{due}다음 토큰 오류 · 재시작 때 다시 시도하고, 다시 시도 "
            f"{bdq_login.CUT_RETRY_LIMIT}번이 모두 끊기면 멈춥니다. Admin Area "
            f"「{BDQ_LOGIN_LABEL}」 의 진단 줄(종료 코드 · 메모리 단서)이 끊긴 모습이고, 계정을 "
            "다시 넣으면 곧바로 로그인해 봅니다."
        )
    return (
        f"저장된 BigDataQuery 계정의 자동 로그인이 {word}({reason}). 멈추지 않고 다음 토큰 오류 · "
        f"재시작 때 다시 시도합니다 — 성공 없이 {bdq_login.MISS_LIMIT}번 이어지면 멈춥니다. Admin "
        f"Area 「{BDQ_LOGIN_LABEL}」 에서 계정을 다시 넣으면 곧바로 로그인해 봅니다."
    )


def _login_stop_short(view: bdq_login.LoginView) -> str:
    """`AD-23` 짧은 글 — 표지 없이 끝난 멈춤은 「로그인 확인 못 함」(비밀번호를 의심하게 하지
    않는다), 보내기 전 끊김이 다시 시도 상한을 넘긴 멈춤은 「다시 시도 3/3 끊김」."""
    if view.stop_reason in bdq_login.UNCONFIRMED_REJECT_REASONS:
        return "BigDataQuery 자동 로그인 멈춤 — 로그인 확인 못 함"
    if view.stop_reason == bdq_login.REASON_CUT_LIMIT:
        limit = bdq_login.retry_text(bdq_login.CUT_RETRY_LIMIT)
        return f"BigDataQuery 자동 로그인 멈춤 — {limit} 끊김"
    return "BigDataQuery 자동 로그인 멈춤 — 계정을 다시 넣으세요"


def _login_stop_text(view: bdq_login.LoginView) -> str:
    """전문(평문) — 왜 멈췄고 무엇을 하면 풀리나. 계정 · 비밀번호가 없다. 표지 없이 끝난 멈춤은
    로그인이 거절됐는지 모른다는 것과 진단을 볼 자리를 먼저 말한다. 보내기 전 끊김이 다시 시도
    상한을 넘긴 멈춤은 계정 잠김 때문이 아니라 다시 시도를 다 썼다는 것과 진단을 볼 자리를
    말한다."""
    reason = login_reason_text(view.stop_reason) if view.stop_reason else "까닭 모름"
    unlock = (
        f"Admin Area 「{BDQ_LOGIN_LABEL}」 에서 계정을 다시 넣어 로그인이 성공하면 풀립니다. "
        f"그때까지 조회는 예비 토큰(CD 환경변수 {BDQ_TOKEN_ENV} · 「토큰 넣기」)으로 합니다."
    )
    if view.stop_reason == bdq_login.REASON_CUT_LIMIT:
        return (
            f"저장된 BigDataQuery 계정의 자동 로그인을 멈췄습니다({reason}). 로그인 하위 "
            "프로세스가 패키지를 불러오는 중(비밀번호를 보내기 전) 바깥에서 끊겼고, 쉬며 다시 "
            f"시도한 {bdq_login.CUT_RETRY_LIMIT}번도 모두 끊겼습니다 — Admin Area "
            f"「{BDQ_LOGIN_LABEL}」 · 「서버 시작 점검」 의 진단 줄(종료 코드 · 메모리 단서)을 "
            f"먼저 봅니다. 더는 다시 시도하지 않습니다. {unlock}"
        )
    if view.stop_reason in bdq_login.UNCONFIRMED_REJECT_REASONS:
        head = (
            f"저장된 BigDataQuery 계정의 자동 로그인을 멈췄습니다(로그인 확인 못 함 — {reason}). "
            "로그인 하위 프로세스가 결과를 남기지 못하고 끝나 비밀번호가 틀렸는지 모릅니다 — "
            f"Admin Area 「{BDQ_LOGIN_LABEL}」 · 「서버 시작 점검」 의 진단 줄(종료 코드 · "
            "걸린 시간 · 단계)을 먼저 봅니다."
        )
    else:
        head = f"저장된 BigDataQuery 계정의 자동 로그인을 멈췄습니다({reason})."
    return f"{head} 계정이 잠기지 않게 다시 시도하지 않습니다. {unlock}"


def _token_alert_text(
    start_reason: str | None,
    query_failed: bool,
    *,
    view: bdq_login.LoginView | None = None,
) -> str:
    """전문(평문 — 알림창 · Alarm 은 `textContent` 로 넣는다) — 무엇이 실패했고 무엇을 하면 풀리나.
    시작 점검 까닭은 시작 스크립트가 이미 가린 글이다. 시작 점검 실패의 까닭은 토큰 값만이 아니다
    (계정 칸 · 파일 권한 · 폴더 쓰기 등) — 그때 할 일은 그 까닭 고치기이고, 새 토큰은 조회 실패만의
    길이다. 조회 실패의 새 토큰 길은 패키지가 읽는 자리를 따른다 — 환경변수
    `BIGDATAQUERY_LOGIN_TOKEN` 이 있으면 「토큰 넣기」 가 잠기니 그 값 바꾸기다(값은 보지
    않는다). 자동 로그인이 켜졌는데 저장된 계정이 없으면(`view.state == "none"`) Admin Area 의 계정
    넣는 자리를, 저장된 계정이 있으면(정상 · 멈춤) 그 자리에서 다시 넣기(곧바로 로그인해 새 토큰 —
    조회 중 다시 로그인이 토큰 파일 없음 · 만료 · 무효를 풀지 못한 뒤다)를 먼저 가리킨다."""
    found: list[str] = []
    if start_reason is not None:
        found.append(f"서버 시작 점검의 「로그인 토큰 파일」 줄이 실패입니다({start_reason})")
    if query_failed:
        found.append(
            "최근 BigDataQuery 조회가 토큰 갈래로 실패했습니다(로그인 토큰이 없거나 만료 · 무효)"
        )
    if start_reason is not None:
        return ". ".join(found) + (
            ". 그 까닭을 고치고 CI/CD 를 다시 누르세요 — Admin 「서버 시작 점검」 에서 토큰 줄을 "
            "봅니다."
        )
    if bdq_token.environment_token_set():
        return ". ".join(found) + f". {ENVIRONMENT_FIX}"
    if view is not None and view.state == "none":
        return ". ".join(found) + f". {AUTO_LOGIN_FIX}"
    if view is not None and view.state in ("ok", "stopped"):
        return ". ".join(found) + (
            f". {RELOGIN_FIX} {INSTALL_FIX} 이 알림은 그 뒤 조회가 한 번 성공하면 풀립니다."
        )
    return ". ".join(found) + f". {INSTALL_FIX} 이 알림은 넣은 뒤 조회가 한 번 성공하면 풀립니다."
