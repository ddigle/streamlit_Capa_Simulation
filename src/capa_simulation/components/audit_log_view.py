# Purpose: Admin Area 「접속 · 작업 기록」 탭 — 사이드바 기록 조건 카드와 요약 · 기록 보기.

"""접속 · 작업 기록 탭(관리자 · 점검자 회차에만 — `sso_identity.viewer_can_audit`).

- **읽기** — 로컬 스풀 · 미러 파일만 읽는다(`audit.read` — S3 를 부르지 않는다). 읽은 줄은 세션 칸에
  (파일 목록 · 크기 · 수정 시각 · 기간) 지문을 키로 두고 같으면 다시 읽지 않는다. 새 `st.cache_*`
  는 두지 않는다. 닫힌 탭이면 아무것도 읽지 않는다(부르는 쪽이 `tab_is_hidden` 으로 가른다).
- **조건** — 사이드바 「조회 조건」 의 「기록 조건」 카드(기간 · 사람 · 사건 갈래 · 결과 · 필터
  초기화). 기간은 KST 날짜다. 위젯은 `persist_state="session"` 이라 탭을 오가도 남는다.
- **보기** — 「요약 | 기록」 종류 단추(탭 안 탭이 아니다). 요약은 오늘(KST) 값 칸 넷과 날짜별 표,
  기록은 줄마다 시각 · 사람 · 갈래 · 사건 · 대상 · 결과 · 상세 · 화면 · 세션이다. 둘 다 고른 조건에
  맞는 줄로 센다. 조건에 맞는 줄이 없는 날은 0 이 아니라 빈칸이고(기록기가 돌지 않은 날과 아무도
  쓰지 않은 날을 가르지 못한다 — 기록기 멈춤은 `AD-12` 몫), 오늘 값 칸도 기간이 오늘을 담지 않거나
  오늘 줄이 없으면 0 이 아니라 「—」 다(UI-DAT-06). 설명 글은 화면에 두지 않는다(Guide · 풍선).

기록을 고치거나 지우는 기능은 없다. 감사 표의 「전체 행 CSV」 · 화면 진입 기록 · 점검 보기는
2판이다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Final

import pandas as pd
import streamlit as st

from capa_simulation.audit import events, read, spool
from capa_simulation.components.date_panel import date_range_field
from capa_simulation.page_bootstrap import prune_list_selection
from capa_simulation.sidebar_status import condition_card

KEY_PREFIX: Final = "admin_area_log"
START_KEY: Final = f"{KEY_PREFIX}_start"
END_KEY: Final = f"{KEY_PREFIX}_end"
PEOPLE_KEY: Final = f"{KEY_PREFIX}_people"
CATEGORIES_KEY: Final = f"{KEY_PREFIX}_categories"
OUTCOMES_KEY: Final = f"{KEY_PREFIX}_outcomes"
RESET_KEY: Final = f"{KEY_PREFIX}_reset"
VIEW_KEY: Final = f"{KEY_PREFIX}_view"
CACHE_KEY: Final = f"{KEY_PREFIX}_cache"
TABLE_KEY: Final = f"{KEY_PREFIX}_table"
CARD_NAME: Final = KEY_PREFIX
CARD_LABEL: Final = "기록 조건"
DEFAULT_DAYS: Final = 7

VIEW_SUMMARY: Final = "요약"
VIEW_RECORDS: Final = "기록"
VIEWS: Final = (VIEW_SUMMARY, VIEW_RECORDS)
VIEW_HELP: Final = (
    "요약은 오늘(KST) 값과 날짜별 수, 기록은 한 줄씩입니다. 시각은 KST 입니다. "
    "기록은 고치거나 지울 수 없습니다."
)
EMPTY_TEXT: Final = "조건에 맞는 기록이 없습니다"
TODAY_LABELS: Final = ("오늘 접속자", "로그인 실패", "명단 밖", "작업")

RECORD_COLUMNS: Final = (
    "시각(KST)",
    "사람",
    "갈래",
    "사건",
    "대상",
    "결과",
    "상세",
    "화면",
    "세션",
)
SUMMARY_COLUMNS: Final = (
    "날짜",
    "접속자",
    "로그인",
    "실패",
    "명단 밖",
    "작업",
    "공식 발행",
    "삭제",
    "관리",
)
EMPTY_VALUE: Final = "—"
_LOGIN_FAIL_EVENTS: Final = frozenset({"authn_login_fail"})
_DENIED_EVENTS: Final = frozenset({"authz_fail_access_list"})
_DELETE_EVENTS: Final = frozenset(
    {"data_scenario_delete", "data_voc_delete", "data_baseline_delete", "user_deleted"}
)


@dataclass(frozen=True)
class LogConditions:
    """카드에서 고른 조건 — KST 기간 · 사람(loginid) · 갈래 · 결과(원본 이름)."""

    start: date
    end: date
    people: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = ()


# ------------------------------------------------------------------ 읽기
def load_lines(start: date, end: date) -> list[dict[str, Any]]:
    """기간의 줄 — 지문이 같으면 세션 칸의 것을 그대로 쓴다(파일을 다시 읽지 않는다)."""
    base = spool.root()
    print_key = read.fingerprint(base, start, end)
    cached = st.session_state.get(CACHE_KEY)
    if isinstance(cached, tuple) and len(cached) == 2 and cached[0] == print_key:
        return list(cached[1])
    lines = read.load_lines(base, start, end)
    st.session_state[CACHE_KEY] = (print_key, tuple(lines))
    return lines


def people_names(lines: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """loginid → 「loginid · 이름」(이름은 로그인 성공 줄에만 있다)."""
    names: dict[str, str] = {}
    for line in lines:
        actor = str(line.get("actor", ""))
        if not actor:
            continue
        name = str(line.get("name", "")) if line.get("ev") == "authn_login_success" else ""
        if name:
            names[actor] = f"{actor} · {name}"
        else:
            names.setdefault(actor, actor)
    return names


def filtered(
    lines: Sequence[Mapping[str, Any]], conditions: LogConditions
) -> list[Mapping[str, Any]]:
    return [
        line
        for line in lines
        if (not conditions.people or line.get("actor") in conditions.people)
        and (not conditions.categories or line.get("cat") in conditions.categories)
        and (not conditions.outcomes or line.get("out") in conditions.outcomes)
    ]


# ------------------------------------------------------------------ 조건 카드
def recorded_categories() -> list[str]:
    """고를 수 있는 갈래 — 이 판에 사건이 있는 갈래만(사건이 없는 갈래는 늘 빈 결과다)."""
    present = {spec.cat for spec in events.SPECS}
    return [category for category in events.CATEGORIES if category in present]


def _reset() -> None:
    for key in (PEOPLE_KEY, CATEGORIES_KEY, OUTCOMES_KEY):
        st.session_state[key] = []


def render_conditions(today: date) -> tuple[LogConditions, list[dict[str, Any]]]:
    """사이드바 「기록 조건」 카드 — 고른 조건과 그 기간의 줄을 돌려준다."""
    with condition_card(CARD_LABEL, name=CARD_NAME, icon=":material/manage_search:", default=True):
        start, end = date_range_field(
            "기간",
            start_key=START_KEY,
            end_key=END_KEY,
            default=(today - timedelta(days=DEFAULT_DAYS - 1), today),
            max_date=today,
        )
        lines = load_lines(start, end)
        names = people_names(lines)
        st.button(
            "필터 초기화",
            key=RESET_KEY,
            icon=":material/filter_alt_off:",
            width="stretch",
            on_click=_reset,
        )
        people_options = sorted(names)
        prune_list_selection(PEOPLE_KEY, people_options)
        people = st.multiselect(
            "사람",
            options=people_options,
            key=PEOPLE_KEY,
            persist_state="session",
            placeholder="",
            format_func=lambda actor: names.get(actor, actor),
        )
        categories = st.multiselect(
            "사건 갈래",
            options=recorded_categories(),
            key=CATEGORIES_KEY,
            persist_state="session",
            placeholder="",
            format_func=lambda value: events.CATEGORIES.get(value, value),
        )
        outcomes = st.multiselect(
            "결과",
            options=list(events.OUTCOMES),
            key=OUTCOMES_KEY,
            persist_state="session",
            placeholder="",
            format_func=lambda value: events.OUTCOMES.get(value, value),
        )
    conditions = LogConditions(start, end, tuple(people), tuple(categories), tuple(outcomes))
    return conditions, lines


# ------------------------------------------------------------------ 표
def detail_text(line: Mapping[str, Any]) -> str:
    """상세 칸 — 「행 120 · 칸 3」 같은 짧은 값 글."""
    det = line.get("det")
    if not isinstance(det, Mapping):
        return line.get("why", "") or ""
    parts: list[str] = []
    for key, value in det.items():
        if isinstance(value, bool):
            value = events.YES_NO[value]
        elif isinstance(value, Mapping):
            value = " ".join(f"{name} {count}" for name, count in value.items())
        elif isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        parts.append(f"{events.DET_LABELS.get(key, key)} {value}")
    return " · ".join(parts)


def target_text(line: Mapping[str, Any]) -> str:
    target = line.get("tgt")
    if not isinstance(target, Mapping):
        return ""
    label = target.get("label")
    identifier = str(target.get("id", ""))
    return f"{label} ({identifier})" if label else identifier


def record_table(lines: Sequence[Mapping[str, Any]], names: Mapping[str, str]) -> pd.DataFrame:
    """기록 보기 표 — 새것 먼저."""
    rows = [
        (
            read.kst_text(str(line.get("ts", ""))),
            names.get(str(line.get("actor", "")), str(line.get("actor", ""))),
            events.CATEGORIES.get(str(line.get("cat", "")), str(line.get("cat", ""))),
            events.label_of(str(line.get("ev", ""))),
            target_text(line),
            events.OUTCOMES.get(str(line.get("out", "")), str(line.get("out", ""))),
            detail_text(line),
            str(line.get("page", "")),
            str(line.get("sid8", "") or line.get("tab8", "")),
        )
        for line in reversed(lines)
    ]
    return pd.DataFrame(rows, columns=list(RECORD_COLUMNS))


def _kst_day(line: Mapping[str, Any]) -> date | None:
    moment = read.parse_ts(str(line.get("ts", "")))
    return None if moment is None else moment.astimezone(read.KST).date()


@dataclass
class _Day:
    people: set[str]
    logins: int = 0
    fails: int = 0
    denied: int = 0
    work: int = 0
    official: int = 0
    deletes: int = 0
    admin: int = 0


def _whole(value: object) -> int:
    """건수 칸 — 정수(참 · 거짓 제외)가 아니면 0. 바깥에서 고친 줄 하나가 탭을 멈추지 않게."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _count(day: _Day, line: Mapping[str, Any]) -> None:
    ev = str(line.get("ev", ""))
    actor = str(line.get("actor", ""))
    raw = line.get("det")
    det: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
    if ev in ("session_created", "authn_login_success") and actor and line.get("verified"):
        day.people.add(actor)
    if ev == "authn_login_success":
        day.logins += 1
    if ev in _LOGIN_FAIL_EVENTS:
        day.fails += 1
    elif ev == "authn_login_fail_summary":
        day.fails += _whole(det.get("total"))
    if ev in _DENIED_EVENTS:
        day.denied += 1
    elif ev == "authz_fail_access_list_summary":
        day.denied += max(_whole(det.get("total")) - _whole(det.get("accounts")), 0)
    if line.get("cat") == "data":
        day.work += 1
    if ev == "data_official_publish":
        day.official += 1
    if ev in _DELETE_EVENTS and det.get("deleted") is not False:
        # 지울 것이 없었던 지우기(그 사이 다른 세션이 지움 — `deleted` 거짓)는 삭제로 세지 않는다.
        day.deletes += 1
    if line.get("cat") == "admin":
        day.admin += 1


def daily_counts(lines: Sequence[Mapping[str, Any]], start: date, end: date) -> dict[date, _Day]:
    days: dict[date, _Day] = {}
    for line in lines:
        day = _kst_day(line)
        if day is None or not start <= day <= end:
            continue
        _count(days.setdefault(day, _Day(set())), line)
    return days


def summary_table(lines: Sequence[Mapping[str, Any]], start: date, end: date) -> pd.DataFrame:
    """날짜별 표(오늘이 위). 기록이 없는 날은 0 이 아니라 빈칸이다(UI-DAT-11)."""
    counted = daily_counts(lines, start, end)
    rows: list[tuple[object, ...]] = []
    day = end
    while day >= start:
        found = counted.get(day)
        if found is None:
            rows.append((day.isoformat(), *([None] * (len(SUMMARY_COLUMNS) - 1))))
        else:
            rows.append(
                (
                    day.isoformat(),
                    len(found.people),
                    found.logins,
                    found.fails,
                    found.denied,
                    found.work,
                    found.official,
                    found.deletes,
                    found.admin,
                )
            )
        day -= timedelta(days=1)
    frame = pd.DataFrame(rows, columns=list(SUMMARY_COLUMNS))
    for column in SUMMARY_COLUMNS[1:]:
        frame[column] = frame[column].astype("Int64")
    return frame


def today_values(
    lines: Sequence[Mapping[str, Any]], today: date
) -> tuple[int, int, int, int] | None:
    """오늘(KST) 값 칸 넷 — 접속자 · 로그인 실패 · 명단 밖 · 작업. 오늘 줄이 없으면 `None`(0 이
    아니라 판정할 값이 없다 — 날짜별 표의 빈칸과 같다)."""
    found = daily_counts(lines, today, today).get(today)
    if found is None:
        return None
    return len(found.people), found.fails, found.denied, found.work


def _cell(value: int | None) -> str:
    return EMPTY_VALUE if value is None else f"{value:,}"


# ------------------------------------------------------------------ 본문
def range_text(count: int, start: date, end: date) -> str:
    return f"{count:,}건 · {start:%m.%d}–{end:%m.%d}"


def render_audit_log(
    conditions: LogConditions, lines: Sequence[Mapping[str, Any]], today: date
) -> None:
    """탭 본문 — 제목 줄(종류 단추 · 건수 · 기간)과 고른 보기 하나."""
    shown = filtered(lines, conditions)
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        view = st.segmented_control(
            "보기",
            options=list(VIEWS),
            default=VIEW_SUMMARY,
            key=VIEW_KEY,
            persist_state="session",
            label_visibility="collapsed",
        )
        # 접은 라벨의 풍선은 보이지 않는다 — 뜻은 줄 끝 값 글의 ⓘ 풍선에 둔다.
        st.caption(
            range_text(len(shown), conditions.start, conditions.end),
            width="content",
            help=VIEW_HELP,
        )
    if not shown:
        st.caption(EMPTY_TEXT)
        return
    if view == VIEW_RECORDS:
        st.dataframe(
            record_table(shown, people_names(lines)),
            hide_index=True,
            width="stretch",
            key=TABLE_KEY,
            placeholder="",
        )
        return
    # 기간이 오늘을 담지 않으면 오늘 줄을 읽지 않았다 — 0 이 아니라 값 없음이다.
    covered = conditions.start <= today <= conditions.end
    values = today_values(shown, today) if covered else None
    with st.container(horizontal=True, gap="small"):
        for label, value in zip(TODAY_LABELS, values or (None,) * len(TODAY_LABELS), strict=True):
            st.metric(label, _cell(value))
    st.dataframe(
        summary_table(shown, conditions.start, conditions.end),
        hide_index=True,
        width="stretch",
        placeholder="",
    )


def render_audit_tab(*, today: date | None = None) -> None:
    """열린 탭 한 번 — 카드(사이드바)를 세우고 본문을 그린다."""
    day = read.kst_today() if today is None else today
    conditions, lines = render_conditions(day)
    render_audit_log(conditions, lines, day)
