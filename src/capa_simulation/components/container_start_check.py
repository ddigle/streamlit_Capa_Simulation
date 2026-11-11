# Purpose: CD 서버 시작 점검 결과를 Admin 펼침으로 보이고 그 서버의 토큰 실패를 관리자에게 알린다.

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

**토큰 실패 관리자 알림(`AD-10`)** — 결과 파일이 있는 서버(C-DEP)에서 BigDataQuery 조회가 토큰
갈래로 실패했거나(`company_bigdataquery_adapter.last_query_failed_on_token` — 프로세스의 마지막
판정) 시작 점검 토큰 줄이 「실패」 면 관리자의 모든 화면 회차에 상태 알림으로 낸다
(`render_token_alert` — `app.py` 가 동기화 알림 곁에서 부른다). 토큰은 공용 계정 하나라 고칠 사람이
관리자다. 결과 파일이 없는 서버(개발 · 사내 PC · WebIDE · 시험)는 Streamlit 호출이 없어 요소 순번이
그대로다.
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
from capa_simulation.components.diagnostic_copy import (
    diagnostic_text,
    plain_lines,
    render_diagnostic_copy,
    table_lines,
)
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.sso_status import (
    CLOCK_FORMAT,
    sso_start_step,
    started_environment_caption,
)
from capa_simulation.io.company_bigdataquery_adapter import last_query_failed_on_token
from capa_simulation.io.container_start_report import (
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
    missing_report_detail,
    missing_report_notice,
    read_app_ready,
    read_container_start_report,
    report_file_exists,
    report_verdict,
    seconds_between,
)
from capa_simulation.navigation import ADMIN_AREA
from capa_simulation.page_tabs_state import tab_label
from capa_simulation.sidebar_status import remembered_expander

# 펼침 key. 탭 묶음 위에 서므로 자리를 key 로 고정한다(9장 「조건부 알림 뒤 key 없는 펼침」).
# 편 상태는 기억 칸(`remembered_expander`)에 둔다 — 진단을 읽다 다른 화면(VOC 등)에 다녀와도
# 접히지 않는다(VOC 글 상자와 같은 꼴, E2E r1). 제목 끝(판정)이 바뀌어도 편 상태는 그대로다.
EXPANDER_KEY = "admin_area_container_start_check"
COPY_KEY = "container_start_check"
# BigDataQuery 토큰 실패 관리자 알림(`render_token_alert`).
TOKEN_ALERT_CODE = "AD-10"
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
    """까닭은 기본 폭에서 잘려 넓히고 나머지 칸은 줄인다 — 앱 관리자가 셀을 눌러 펴지 않고 읽는다.

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
    """결과 파일의 ISO 시각 → 진단 펼침 시각 꼴(`sso_status.CLOCK_FORMAT`). 못 읽으면 받은 글
    그대로다."""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return moment.astimezone().strftime(CLOCK_FORMAT)
    except (ValueError, OverflowError, OSError):
        return value


def fact_lines(report: ContainerStartReport) -> list[str]:
    """표 아래 한 줄씩 — 깔린 판·토큰 파일·요청자 계정. 값은 마크다운에 글자 그대로 싣는다."""
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
    return lines


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
    _report_missing(None)
    title = f"서버 시작 점검 · {report_verdict(report)}"
    # 넷째 줄 「통합인증」 은 결과 파일이 아니라 이 프로세스의 지금 설정에서 판정한다 — 시작
    # 스크립트는 통합인증 값을 검증하지 않고 앱에 넘긴다(이름만 결과 파일에 남긴다).
    steps = build_step_table(report, (sso_start_step(), *sync_rows(report)))
    facts = report_fact_lines(report)
    with remembered_expander(title, icon=":material/rocket_launch:", key=EXPANDER_KEY):
        render_diagnostic_copy(report_text(title, report, steps, facts), key=COPY_KEY)
        st.caption(report_origin_caption(report))
        st.dataframe(steps, column_config=step_column_config(), hide_index=True, width="stretch")
        st.caption("  \n".join(facts))
        missing = missing_environment_line(report)
        if missing is not None:
            st.caption(missing)
        if report.pip_tail:
            st.caption(PIP_TAIL_LABEL)
            st.code("\n".join(report.pip_tail), language=None)


def _render_missing_report() -> None:
    """결과를 못 읽은 회차 — 파일이 있으면 「결과 파일을 읽지 못함」(꼴이 다름), 없으면 CD 서버로
    보일 때만 「결과 없음」. 펼침 제목이 판정이고 본문은 까닭 캡션이다 — 알릴 조건은 상태
    알림(`AD-01`)으로도 낸다(알림창 · Alarm)."""
    if report_file_exists():
        title, notice = "서버 시작 점검 · 결과 파일을 읽지 못함", UNREADABLE_REPORT_NOTICE
        _report_missing(title, UNREADABLE_REPORT_DETAIL)
    else:
        missing = missing_report_notice()
        if missing is None:
            _report_missing(None)
            return
        title, notice = "서버 시작 점검 · 결과 없음", missing
        _report_missing(title, missing_report_detail(missing))
    # 넣을 환경변수와 이때 볼 것은 Guide 「서버 시작 점검」 이 안내 문서 절을 가리킨다(UI-TXT-03).
    with remembered_expander(title, icon=":material/rocket_launch:", key=EXPANDER_KEY):
        render_diagnostic_copy(diagnostic_text(title, plain_lines([notice])), key=COPY_KEY)
        st.caption(notice)


def _report_missing(title: str | None, detail: str = "") -> None:
    """서버 시작 점검 결과를 못 읽었는지 상태 알림(`AD-01`). 읽었거나 CD 서버가 아니면 해소다 —
    Admin 회차마다 한 번 부른다(이벤트 칸 한 자리)."""
    alerts.state(
        "AD-01",
        scope=None,
        content=title,
        active=title is not None,
        text=(None if title is None else f"{title} — 배포 서버 환경변수를 확인하세요"),
        full=alerts.plain_text(detail) or None,
    )


def render_token_alert() -> None:
    """BigDataQuery 토큰 실패 관리자 알림(`AD-10`). `app.py` 가 회차마다 조건 없이 부른다.

    결과 파일이 없는 서버(C-DEP 밖)는 아무것도 부르지 않는다 — 그 파일은 시작 스크립트가 앱보다 먼저
    한 번 쓰므로 프로세스 동안 있고 없음이 바뀌지 않는다. 있는 서버는 회차마다 이벤트 칸 한 자리를
    쓰고 관리자가 아닌 회차는 해소로 부른다. 지문은 (시작 점검 토큰 줄 실패, 조회 토큰 실패) 두
    참거짓뿐이다 — 시각 · 계정 · 원문을 싣지 않는다.
    """
    if not report_file_exists():
        return
    report = read_container_start_report()
    step = None if report is None else report.steps.get(STEP_TOKEN)
    start_failed = step is not None and step.status == STATUS_FAILED
    query_failed = last_query_failed_on_token()
    active = (start_failed or query_failed) and sso_identity.viewer_is_admin()
    alerts.state(
        TOKEN_ALERT_CODE,
        scope=None,
        content=(start_failed, query_failed) if active else None,
        active=active,
        text="BigDataQuery 로그인 토큰 실패 — 조회가 막힙니다" if active else None,
        full=(
            _token_alert_text(step.reason if start_failed and step else None, query_failed)
            if active
            else None
        ),
        goto=(tab_label(ADMIN_AREA), ADMIN_AREA.href),
    )


def _token_alert_text(start_reason: str | None, query_failed: bool) -> str:
    """전문 — 무엇이 실패했고 무엇을 하면 풀리나. 시작 점검 까닭은 시작 스크립트가 이미 가린
    글이다."""
    found: list[str] = []
    if start_reason is not None:
        found.append(f"서버 시작 점검의 「로그인 토큰 파일」 줄이 실패입니다({start_reason})")
    if query_failed:
        found.append(
            "최근 BigDataQuery 조회가 토큰 갈래로 실패했습니다(로그인 토큰이 없거나 만료 · 무효)"
        )
    return (
        ". ".join(found) + f". `{BDQ_TOKEN_ENV}` 에 새 토큰을 넣고 CI/CD 를 다시 누르세요 — "
        "Admin 「서버 시작 점검」 에서 토큰 줄을 봅니다."
    )
