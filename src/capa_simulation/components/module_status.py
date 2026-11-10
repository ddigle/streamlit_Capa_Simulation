# Purpose: Admin Area 탭 줄 끝 팝오버에 모듈 찾기 결과와 마지막 오류를 보인다(모듈 없으면 없음).

"""Admin Area 「모듈 상태」.

모듈 폴더가 없으면(사외 · `CAPA_MODULES_ROOT=off` · 시험 기본값) 아무것도 그리지 않는다 — Admin
화면이 사외와 같다. DB 를 열지 않는다 — 회차마다 캐시된 찾기 결과(`navigation.module_scan`)와 실행
기록(`module_failures`)만 읽는다. 표는 평문 칸이라 사람이 지은 이름을 그대로 싣고, 캡션의 값은
`literal_markdown` 으로 싣는다.

**자리는 안쪽 탭 줄 오른쪽 끝 팝오버다**(2026-11-10 보드 Q-6 — T7 의 「보유 공정」 팝오버 ·
「알림 모음」 수 표지와 같은 꼴). 탭 위에 펼침 한 줄을 세우면 모듈을 켠 Admin 의 상단 띠가 한
줄(약 49px) 늘었다(설계 규칙 UI-LAY-13). 수(켜짐 · 꺼짐 · 실패)는 닫힌 채로 보이는 팝오버 단추
글이고(`status_title` — 사내 런북의 화면 확인이 이 수를 읽는다), 표 · 복사 · 환경변수 줄은 팝오버
안이다.
부르는 쪽이 탭 묶음을 담은 칸의 key(`box_key`)를 주면 단추 칸을 그 칸의 오른쪽 위(탭 줄 높이)에
절대 위치로 얹고 탭 줄은 그 폭만큼 오른쪽을 비운다 — 새 줄을 세우지 않는다. 그 칸에 탭이 없는
회차(DB 를 못 열어 멈춤)에는 단추가 흐름 안 한 줄로 선다.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from streamlit.elements.lib.column_types import ColumnConfig

from capa_simulation import alerts, module_failures
from capa_simulation.components.diagnostic_copy import (
    diagnostic_text,
    plain_lines,
    render_diagnostic_copy,
    table_lines,
)
from capa_simulation.components.literal_markdown import literal_markdown, literal_names
from capa_simulation.module_registry import (
    DISABLED_ENV_VAR,
    MATURITY_LABELS,
    ROOT_ENV_VAR,
    STATE_LABELS,
    ModuleScan,
)
from capa_simulation.navigation import module_scan

# 팝오버(라벨의 수가 바뀌어도 같은 블록이게 key 를 단다 — `tests/test_popover_keys.py`), 그 단추를
# 담는 칸(탭 줄 오른쪽 끝에 얹는 자리), 팝오버 안 칸(표가 읽히는 폭을 준다)의 key.
POPOVER_KEY = "admin_area_module_status_popover"
TOOLS_KEY = "admin_area_module_status_tools"
CONTENT_KEY = "admin_area_module_status_content"
COPY_KEY = "module_status"
# 탭 줄 오른쪽에 비워 두는 폭 — 단추 글 「모듈 상태 · 켜짐 n · 꺼짐 n · 실패 n」(수 두 자리)과
# 아이콘 · 꺾쇠 · 안쪽 여백이 드는 폭에 사내 글꼴이 조금 넓어도 남게 더한 값
# (`display_order_management.ACTION_ROW_RESERVE_REM` 과 같은 꼴). 탭이 이 폭을 넘으면 탭 줄이 제
# 안에서 옆으로 민다.
TAB_ROW_RESERVE_REM = 19
# 팝오버 안 표 폭 — 12칸 표의 까닭 칸이 넓게 서도록 넓게 주되, 펼친 사이드바(300px)를 덮지 않게
# 창 폭에서 뺀다. 팝오버 몸은 단추 오른쪽 끝(창 − 본문 오른쪽 여백 약 17px)에 맞춰 왼쪽으로 펴지고
# 몸의 테 · 안쪽 여백이 양쪽 합 약 42px 이라, 빼는 몫 27rem(rem 14px — 378px)이면 몸 왼쪽이 창 폭과
# 상관없이 약 319px(사이드바 오른쪽 + 19px)이다. 창 1283 · 1600 에서는 64rem 쪽이 작아 그대로다.
CONTENT_WIDTH = "min(64rem, calc(100vw - 27rem))"
# 환경변수 줄의 풍선 — 바꾼 것이 언제 보이는지는 칸 하나의 뜻이라 늘 띄우지 않는다(설계 규칙
# UI-TXT-01 · 02).
RESTART_NOTICE = "`module.json`·환경변수를 바꾼 것은 앱을 다시 띄운 뒤 보입니다."
# 회차 시간 칸 — 단위를 이름에 적고 ms 정수로 싣는다(초 소수 둘째 자리면 가벼운 모듈이 모두
# 0.00 이라 서로 갈리지 않는다). 숫자 칸(`Int64`, 기록이 없으면 빈칸)이라 머리글로 정렬하면 값
# 차례로 선다 — 글 칸이면 「12,346」 < 「123」 < 「2」 처럼 글자 차례라 느린 모듈이 위로 안 온다.
RUN_TIME_COLUMN = "마지막 회차 시간(ms)"
# 「모듈 이름」 은 `module.json` 의 `name` 이다 — 화면 이름(`pages[].title`)과 가른다(같은 줄의 까닭
# 「화면 이름 겹침: …」 은 화면 이름을 말한다). 「빠진 화면」 은 「화면」 곁이다 — 끝에 두면 좁은
# 창에서 가로 스크롤 뒤로 숨어 빠진 수가 보이지 않는다.
COLUMNS = (
    "모듈",
    "모듈 이름",
    "상태",
    "까닭",
    "성숙도",
    "담당",
    "API",
    "화면",
    "빠진 화면",
    "마지막 오류",
    RUN_TIME_COLUMN,
    "접두 없는 키",
)


def status_title(scan: ModuleScan) -> str:
    counts = {state: 0 for state in STATE_LABELS}
    for record in scan.records:
        counts[record.state] += 1
    return f"모듈 상태 · 켜짐 {counts['on']} · 꺼짐 {counts['off']} · 실패 {counts['failed']}"


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
                sum(1 for owner, _ in excluded if owner == module_id),
                ""
                if failure is None
                else " · ".join(
                    part for part in (failure.at, failure.kind, failure.where, failure.page) if part
                ),
                None if module_id not in seconds else run_time_ms(seconds[module_id]),
                len(warnings.get(module_id, ())),
            )
        )
    table = pd.DataFrame(rows, columns=list(COLUMNS))
    table[RUN_TIME_COLUMN] = table[RUN_TIME_COLUMN].astype("Int64")
    return table


def status_column_config() -> dict[str, ColumnConfig]:
    """까닭·마지막 오류는 기본 폭에서 잘리므로 넓힌다 — 앱 관리자가 셀을 눌러 펴지 않고 읽는다.
    까닭은 줄이지 않는다 — 좁은 창에서 끝 칸이 가로 스크롤 뒤로 가도 빠진 수는 「화면」 곁에서
    보인다(`COLUMNS`). 회차 시간은 숫자 칸(오른쪽 맞춤 · 값 차례 정렬)에 천 단위 쉼표를 붙인다."""
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


def status_text(title: str, scan: ModuleScan, table: pd.DataFrame | None) -> str:
    """「복사」 글 — 뿌리 오류 · 모듈 표 · 환경변수 줄."""
    return diagnostic_text(
        title,
        [scan.root_error] if scan.root_error else [],
        [] if table is None else table_lines(table),
        plain_lines([environment_caption(scan)]),
    )


def tools_style(box_key: str | None) -> str:
    """단추 칸 · 팝오버 안 칸 서식. `box_key` 를 주면 단추 칸을 그 칸 오른쪽 위에 얹고(절대 위치
    — 흐름에서 빠져 줄 · 간격을 먹지 않는다) 그 칸의 탭 묶음(탭 안 탭은 빼고) 탭 줄은 단추 폭만큼
    오른쪽을 비운다. 그 칸에 탭 묶음이 없는 회차(DB 를 못 열어 멈춤)에는 단추 칸이 흐름 안에
    남는다."""
    rules = [
        f".st-key-{TOOLS_KEY} button {{ min-height: 2rem; padding-top: 0.125rem; "
        "padding-bottom: 0.125rem; }",
        f".st-key-{CONTENT_KEY} {{ width: {CONTENT_WIDTH}; max-width: 100%; }}",
        # 팝오버 몸은 Streamlit 이 최대 폭(창 1600 에서 708px)을 요소 서식으로 박아 안 칸 폭만으로는
        # 넓어지지 않는다 — 그 칸을 든 몸만 풀어 준다(창 폭 안).
        f'[data-testid="stPopoverBody"]:has(.st-key-{CONTENT_KEY}) '
        "{ max-width: calc(100vw - 2rem) !important; }",
    ]
    if box_key is not None:
        # 탭 묶음은 그 칸의 바로 밑 자식이다(`stateful_tabs` 를 그 칸 안에서 부른다). `:has()` 안에
        # 칸 자신을 다시 적는 꼴(`:has(.칸 …)`)은 브라우저가 맞추지 않아 자식 결합자로 고른다.
        box = f'.st-key-{box_key}:has(> [data-testid="stTabs"])'
        holder = f'{box} > [data-testid="stLayoutWrapper"]:has(> .st-key-{TOOLS_KEY})'
        tablist = f'{box} > [data-testid="stTabs"] > div > [role="tablist"]'
        rules += [
            f"{box} {{ position: relative; }}",
            f"{holder} {{ position: absolute; top: 0; right: 0; width: auto; z-index: 1; }}",
            f"{tablist} {{ padding-right: {TAB_ROW_RESERVE_REM}rem; }}",
        ]
    return "<style>" + "\n".join(rules) + "</style>"


def render_module_status(*, box_key: str | None = None) -> None:
    """모듈 기록이 있거나 뿌리를 못 읽었을 때만 팝오버를 그린다. 뿌리를 못 읽은 것은 상태
    알림(`MO-01` — 알림창 · Alarm)으로도 낸다(그리지 않는 회차에도 부른다 — 해소).

    `box_key` 는 탭 묶음을 담은 칸의 key 다 — 이 함수를 그 칸 안 맨 앞에서 부르면 단추가 탭 줄
    오른쪽 끝에 선다(`tools_style`). 주지 않으면 지금 자리 흐름 안 한 줄이다."""
    scan = module_scan()
    alerts.state(
        "MO-01",
        scope=None,
        content=scan.root_error or None,
        active=bool(scan.root_error),
        text="모듈 전체 폴더를 읽지 못해 모듈 화면이 서지 않습니다 — Admin 「모듈 상태」 확인",
        full=scan.root_error or None,
    )
    if not scan.records and not scan.root_error:
        return
    title = status_title(scan)
    table = build_status_table(scan) if scan.records else None
    with st.container(key=TOOLS_KEY):
        st.html(tools_style(box_key))
        with (
            st.popover(title, icon=":material/extension:", key=POPOVER_KEY),
            st.container(key=CONTENT_KEY),
        ):
            render_diagnostic_copy(status_text(title, scan, table), key=COPY_KEY)
            if scan.root_error:
                st.caption(f":material/folder_off: {literal_markdown(scan.root_error)}")
            if table is not None:
                st.dataframe(
                    table,
                    column_config=status_column_config(),
                    hide_index=True,
                    width="stretch",
                    placeholder="",
                )
            st.caption(environment_caption(scan), help=RESTART_NOTICE)
