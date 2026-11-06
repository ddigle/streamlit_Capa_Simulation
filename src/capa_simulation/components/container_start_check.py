# Purpose: Admin Area 탭 위에 CD 컨테이너 시작 점검 결과나 그 결과가 없음을 펼침으로 보인다.

"""서버 시작 점검.

CD 서버에는 셸도 로그도 없어(시작 명령도 못 바꾼다) 시작 스크립트(`scripts/container_start.py`)의
결과를 이 펼침에서 읽는다. 결과 파일이 없는 개발·사내 PC 에서는 아무것도 그리지 않는다. CD 전용
환경변수가 앱에 들어왔는데 결과 파일이 없으면(스크립트가 돌지 않았거나 결과를 쓰지 못함) 그 사실을
「결과 없음」 펼침으로 알린다 — 그러지 않으면 화면이 개발 PC 와 같아 막힌 자리를 가를 수 없다.
파일은 있는데 읽지 못하면(빈 파일·JSON 아님·모르는 꼴) 「결과 파일을 읽지 못함」 펼침이다 —
스크립트는 돌았으니 「결과 없음」 과 가른다.

파일은 작은 JSON 하나라 회차마다 읽고 DB 는 열지 않는다. 비밀값은 파일에 원래 없다(스크립트가
가렸다). 사람이 넣은 값에서 나온 글(까닭·pip 출력)은 표·코드 칸에 그대로 싣고, 캡션에 넣는 값은
`literal_markdown` 으로 싣는다.

S3 키나 `managed` 가 있는 서버는 표에 동기화 줄(aws CLI · ECS 연결 · 버킷 목록 · DB 받기)이 더해지고
캡션에 디스크 · pod 끝 글자 · cgroup · 다운 시간 값이 더해진다 — 사내가 이 값을 보고 정할 것이 있다
(읽기 전용 화면, DuckDB `memory_limit`). 값은 갈래와 수뿐이라 리뷰 압축본에 옮길 수 있다.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.sso_status import sso_start_step, started_environment_caption
from capa_simulation.io.container_start_report import (
    BDQ_USER_NAME_ENV,
    STATUS_LABELS,
    STEP_LABELS,
    STEPS,
    SYNC_STEP_LABELS,
    SYNC_STEPS,
    UNREADABLE_REPORT_NOTICE,
    ContainerStartReport,
    SyncStart,
    missing_report_notice,
    read_app_ready,
    read_container_start_report,
    report_file_exists,
    report_verdict,
    seconds_between,
)
from capa_simulation.sidebar_status import remembered_expander

# 펼침 key. 탭 묶음 위에 서므로 자리를 key 로 고정한다(9장 「조건부 알림 뒤 key 없는 펼침」).
# 편 상태는 기억 칸(`remembered_expander`)에 둔다 — 진단을 읽다 다른 화면(VOC 등)에 다녀와도
# 접히지 않는다(VOC 글 상자와 같은 꼴, E2E r1). 제목 끝(판정)이 바뀌어도 편 상태는 그대로다.
EXPANDER_KEY = "admin_area_container_start_check"
_GIB = 1024**3
# pod 이름은 사내 식별값이고 이 줄은 리뷰 압축본에 옮긴다. 같은 pod 인지 가르는 데는 끝이면 족하다.
POD_TAIL_CHARS = 5


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


def fact_lines(report: ContainerStartReport) -> list[str]:
    """표 아래 한 줄씩 — 깔린 판·토큰 파일·요청자 계정. 값은 마크다운에 글자 그대로 싣는다."""
    version = report.bigdataquery_version
    account = report.user_name_masked
    if report.token_file_exists is None:
        token = "확인하지 못함(폴더에 들어갈 수 없음)" if account else "계정을 몰라 보지 않음"
    elif report.token_file_exists:
        token = f"있음 · 수정 {literal_markdown(report.token_file_modified_at or '알 수 없음')}"
    else:
        token = "없음"
    if report.token_file_path:
        token += f" · 자리 {literal_markdown(report.token_file_path)}"
    lines = [
        f"bigdataquery 판: {literal_markdown(version) if version else '없음'}",
        f"로그인 토큰 파일: {token}",
        f"`{BDQ_USER_NAME_ENV}`: {f'있음({literal_markdown(account)})' if account else '없음'}",
    ]
    if report.os_user_masked:
        same = {True: " · 계정 값과 같음", False: " · 계정 값과 다름", None: ""}
        lines.append(
            f"실행 사용자: {literal_markdown(report.os_user_masked)}"
            f"{same[report.os_user_is_bdq_user]}"
        )
    if report.home_masked:
        lines.append(f"HOME: {literal_markdown(report.home_masked)}")
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
    return f"한도: {' · '.join(parts)}" if parts else None


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
        lines.append(f"/project 디스크: 여유 {free} · 전체 {total}")
    if sync.pod:
        lines.append(f"pod 끝: {literal_markdown(sync.pod[-POD_TAIL_CHARS:])}")
    limits = _limits_line(sync)
    if limits is not None:
        lines.append(limits)
    if sync.duckdb_memory_limit or sync.duckdb_threads:
        limit = literal_markdown(sync.duckdb_memory_limit or "?")
        threads = literal_markdown(sync.duckdb_threads or "?")
        lines.append(f"DuckDB 기본값: memory_limit {limit} · threads {threads}")
    downtime = _downtime_line(sync, ready_utc)
    if downtime is not None:
        lines.append(downtime)
    gap = seconds_between(sync.previous_upload_utc, ready_utc)
    if gap is not None:
        lines.append(f"앞 pod 마지막 올림 → 이번 앱 준비: {gap:.0f}초")
    return lines


def report_origin_caption(report: ContainerStartReport) -> str:
    """펼침 맨 위 값 줄 — 언제 남긴 결과인지(「라벨 · 값」).

    넣을 환경변수와 토큰 값 얻는 법(`docs/bigdataquery_webide_setup.md` 「C-DEP CD(배포 서버)」)은
    Guide 「서버 시작 점검」 이 말한다 — 펼침에 길 안내 문장을 늘 띄우지 않는다(설계 규칙
    UI-TXT-03).
    """
    started = literal_markdown(report.written_at) if report.written_at else "알 수 없음"
    return f"**시작 기록** · {started} · `scripts/container_start.py`"


def render_container_start_check() -> None:
    report = read_container_start_report()
    if report is None:
        _render_missing_report()
        return
    _report_missing(None)
    with remembered_expander(
        f"서버 시작 점검 · {report_verdict(report)}",
        icon=":material/rocket_launch:",
        key=EXPANDER_KEY,
    ):
        st.caption(report_origin_caption(report))
        # 넷째 줄 「통합인증」 은 결과 파일이 아니라 이 프로세스의 지금 설정에서 판정한다 — 시작
        # 스크립트는 통합인증 값을 검증하지 않고 앱에 넘긴다(이름만 결과 파일에 남긴다).
        st.dataframe(
            build_step_table(report, (sso_start_step(), *sync_rows(report))),
            hide_index=True,
            width="stretch",
        )
        lines = fact_lines(report) + sync_fact_lines(report, read_app_ready())
        started = started_environment_caption(
            None if report.sso_environment is None else dict(report.sso_environment)
        )
        if started is not None:
            lines.append(started)
        st.caption("  \n".join(lines))
        if report.missing_environment:
            names = " · ".join(f"`{name}`" for name in report.missing_environment)
            st.caption(f"시작 때 비어 있던 CD 환경변수: {names}")
        if report.pip_tail:
            st.caption("pip 출력 끝(자격증명은 가렸습니다)")
            st.code("\n".join(report.pip_tail), language=None)


def _render_missing_report() -> None:
    """결과를 못 읽은 회차 — 파일이 있으면 「결과 파일을 읽지 못함」(꼴이 다름), 없으면 CD 서버로
    보일 때만 「결과 없음」. 펼침 제목이 판정이고 본문은 까닭 캡션이다 — 알릴 조건은 상태
    알림(`AD-01`)으로도 낸다(알림창 · Alarm)."""
    if report_file_exists():
        title, notice = "서버 시작 점검 · 결과 파일을 읽지 못함", UNREADABLE_REPORT_NOTICE
    else:
        missing = missing_report_notice()
        if missing is None:
            _report_missing(None)
            return
        title, notice = "서버 시작 점검 · 결과 없음", missing
    _report_missing(title, notice)
    # 넣을 환경변수와 이때 볼 것은 Guide 「서버 시작 점검」 이 안내 문서 절을 가리킨다(UI-TXT-03).
    with remembered_expander(title, icon=":material/rocket_launch:", key=EXPANDER_KEY):
        st.caption(notice)


def _report_missing(title: str | None, notice: str = "") -> None:
    """서버 시작 점검 결과를 못 읽었는지 상태 알림(`AD-01`). 읽었거나 CD 서버가 아니면 해소다 —
    Admin 회차마다 한 번 부른다(이벤트 칸 한 자리)."""
    alerts.state(
        "AD-01",
        scope=None,
        content=title,
        active=title is not None,
        text=(None if title is None else f"{title} — 배포 서버 환경변수를 확인하세요"),
        full=notice or None,
    )
