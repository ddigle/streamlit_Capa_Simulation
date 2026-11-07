# Purpose: Admin Area 탭 위에 모듈 찾기 결과와 마지막 오류를 펼침으로 보인다(모듈 없으면 없음).

"""Admin Area 「모듈 상태」.

모듈 폴더가 없으면(사외 · `CAPA_MODULES_ROOT=off` · 시험 기본값) 아무것도 그리지 않는다 — Admin
화면이 사외와 같다. DB 를 열지 않는다 — 회차마다 캐시된 찾기 결과(`navigation.module_scan`)와 실행
기록(`module_failures`)만 읽는다. 표는 평문 칸이라 사람이 지은 이름을 그대로 싣고, 캡션의 값은
`literal_markdown` 으로 싣는다.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from streamlit.elements.lib.column_types import ColumnConfig

from capa_simulation import alerts, module_failures
from capa_simulation.components.literal_markdown import literal_markdown, literal_names
from capa_simulation.module_registry import (
    DISABLED_ENV_VAR,
    MATURITY_LABELS,
    ROOT_ENV_VAR,
    STATE_LABELS,
    ModuleScan,
)
from capa_simulation.navigation import module_scan
from capa_simulation.sidebar_status import remembered_expander

# 펼침 key — 탭 묶음 위에 서므로 자리를 key 로 고정하고, 편 상태는 기억 칸에 둔다(「서버 시작 점검」
# 과 같은 꼴).
EXPANDER_KEY = "admin_area_module_status"
# 환경변수 줄의 풍선 — 바꾼 것이 언제 보이는지는 칸 하나의 뜻이라 늘 띄우지 않는다(설계 규칙
# UI-TXT-01 · 02).
RESTART_NOTICE = "`module.json`·환경변수를 바꾼 것은 앱을 다시 띄운 뒤 보입니다."
# 회차 시간 칸 — 단위를 이름에 적고 ms 정수로 싣는다(초 소수 둘째 자리면 가벼운 모듈이 모두
# 0.00 이라 서로 갈리지 않는다). 숫자 칸(`Int64`, 기록이 없으면 빈칸)이라 머리글로 정렬하면 값
# 차례로 선다 — 글 칸이면 「12,346」 < 「123」 < 「2」 처럼 글자 차례라 느린 모듈이 위로 안 온다.
RUN_TIME_COLUMN = "마지막 회차 시간(ms)"
# 「모듈 이름」 은 `module.json` 의 `name` 이다 — 화면 이름(`pages[].title`)과 가른다(같은 줄의 까닭
# 「화면 이름 겹침: …」 은 화면 이름을 말한다).
COLUMNS = (
    "모듈",
    "모듈 이름",
    "상태",
    "까닭",
    "성숙도",
    "담당",
    "API",
    "화면",
    "마지막 오류",
    RUN_TIME_COLUMN,
    "접두 없는 키",
    "빠진 화면",
)


def status_title(scan: ModuleScan) -> str:
    counts = {state: 0 for state in STATE_LABELS}
    for record in scan.records:
        counts[record.state] += 1
    return f"모듈 상태 — 켜짐 {counts['on']} · 꺼짐 {counts['off']} · 실패 {counts['failed']}"


def run_time_ms(seconds: float) -> int:
    """기록한 회차 시간(초)을 ms 정수로 — 파이썬 `round`(.5 는 짝수 쪽)라 0.5ms 아래는 0 이다.

    천 단위 쉼표는 칸 꼴(`status_column_config` 의 `localized`)이 붙인다.
    """
    return round(seconds * 1000)


def build_status_table(scan: ModuleScan) -> pd.DataFrame:
    """모듈마다 한 줄 — 찾기 결과와 실행 기록(마지막 오류·회차 시간·접두 없는 키·빠진 화면)."""
    failures = module_failures.last_failures()
    seconds = module_failures.last_run_seconds()
    warnings = module_failures.key_warnings()
    excluded = module_failures.excluded_pages()
    rows = []
    for record in scan.records:
        manifest = record.manifest
        module_id = record.folder_name
        failure = failures.get(module_id)
        rows.append(
            (
                module_id,
                "" if manifest is None else manifest.name,
                STATE_LABELS[record.state],
                record.reason,
                "" if manifest is None else MATURITY_LABELS.get(manifest.maturity, ""),
                "" if manifest is None else manifest.owner,
                "" if manifest is None else f"{manifest.api}.{manifest.api_minor}",
                0 if manifest is None else len(manifest.pages),
                ""
                if failure is None
                else " · ".join(
                    part for part in (failure.at, failure.kind, failure.where, failure.page) if part
                ),
                None if module_id not in seconds else run_time_ms(seconds[module_id]),
                len(warnings.get(module_id, ())),
                sum(1 for owner, _ in excluded if owner == module_id),
            )
        )
    table = pd.DataFrame(rows, columns=list(COLUMNS))
    table[RUN_TIME_COLUMN] = table[RUN_TIME_COLUMN].astype("Int64")
    return table


def status_column_config() -> dict[str, ColumnConfig]:
    """까닭·마지막 오류는 기본 폭에서 잘리므로 넓힌다 — 앱 관리자가 셀을 눌러 펴지 않고 읽는다.
    회차 시간은 숫자 칸(오른쪽 맞춤 · 값 차례 정렬)에 천 단위 쉼표를 붙인다."""
    return {
        "까닭": st.column_config.TextColumn(width="large"),
        "마지막 오류": st.column_config.TextColumn(width="medium"),
        RUN_TIME_COLUMN: st.column_config.NumberColumn(format="localized"),
    }


def environment_caption(scan: ModuleScan) -> str:
    """끄는 스위치·뿌리 환경변수의 지금 값(id 만 담는다)과 폴더가 없는 끈 id."""
    parts = []
    root_value = os.environ.get(ROOT_ENV_VAR, "").strip()
    if root_value:
        parts.append(f"`{ROOT_ENV_VAR}` {literal_markdown(root_value)}")
    disabled = scan.disabled_value.strip()
    parts.append(f"`{DISABLED_ENV_VAR}` {literal_markdown(disabled) if disabled else '없음'}")
    if scan.unknown_disabled:
        parts.append(f"폴더가 없는 끈 id {literal_names(scan.unknown_disabled)}")
    return " · ".join(parts)


def render_module_status() -> None:
    """모듈 기록이 있거나 뿌리를 못 읽었을 때만 펼침을 그린다. 뿌리를 못 읽은 것은 상태
    알림(`MO-01` — 알림창 · Alarm)으로도 낸다(그리지 않는 회차에도 부른다 — 해소)."""
    scan = module_scan()
    alerts.state(
        "MO-01",
        scope=None,
        content=scan.root_error or None,
        active=bool(scan.root_error),
        text="모듈 폴더를 읽지 못해 모듈 화면이 서지 않습니다 — Admin 「모듈 상태」 확인",
        full=scan.root_error or None,
    )
    if not scan.records and not scan.root_error:
        return
    with remembered_expander(status_title(scan), icon=":material/extension:", key=EXPANDER_KEY):
        if scan.root_error:
            st.caption(f":material/folder_off: {literal_markdown(scan.root_error)}")
        if scan.records:
            st.dataframe(
                build_status_table(scan),
                column_config=status_column_config(),
                hide_index=True,
                width="stretch",
                placeholder="",
            )
        st.caption(environment_caption(scan), help=RESTART_NOTICE)
