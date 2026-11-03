# Purpose: 화면이 상태 알림·화면 오류 알림을 낼 때 쓰는 공용 조각(범위·딸린 표·오류 표지)을 둔다.

"""알림 체계 2단계(2026-11-03 결정 보드 D2 (나)) — 화면 쪽 공용 조각. 규칙은 `alerts` 모듈 설명이다.

- `simulation_scope` — 시뮬레이션 상태 알림의 범위(지문 재료 — 활성 리비전 `content_token` 과,
  조회기간을 보는 알림이면 그 기간)와 로그의 범위 줄(「시나리오 · rN · 26.01–26.12」). **세션만
  읽는다** — 시나리오나 조회기간을 바꾸면 수가 같아도 새 알림이다.
- `alert_table` — 본문에서 뺀 목록을 알림에 싣는 표(`alerts.AlertTable` — Alarm 줄에서 펼쳐 보고
  CSV 로 내려받는다). 값은 JSON 값으로 바꾸고(NaN → 빈칸) 공정 칸은 표시명을 화면에만 입힌다(CSV
  는 원본 — `exclusion_table` 과 같은 규칙). `alerts.TABLE_ROW_LIMIT` 를 넘으면 None 이라 화면이
  본문 목록을 그대로 둔다.
- `alert_page_error` — 화면을 그리지 못한 오류(설계 2-2 「오류는 두 길」). 자리 `st.error` 는 부르는
  쪽이 그대로 그리고, 이 함수는 사건 알림 하나를 보낸다 — id 를 그 글의 지문으로 고정해 같은 글이면
  이 브라우저 탭에 **한 번만** 알림창이 뜬다(회차마다 다시 그리는 오류가 알림창을 거듭 띄우지
  않는다). 해소 줄은 없다 — 화면이 다시 서면 자리 오류가 사라진다.
"""

from __future__ import annotations

import math
from datetime import date
from typing import NamedTuple

import pandas as pd

from capa_simulation import alerts
from capa_simulation.components.process_labels import PROCESS_COLUMN, ProcessLabels
from capa_simulation.scenario_activation import active_scenario_label
from capa_simulation.scenario_state import ActiveScenario, is_pristine_content_token
from capa_simulation.services.month_columns import month_label

# 범위 줄에서 기간을 보지 않는 알림(대당 Capa 의 측정률 가정 · 적용 뒤 전체 기간 셈)의 말.
FULL_PERIOD_LABEL = "시나리오 전체 기간"
# 활성 리비전에 저장하지 않은 편집이 든 회차의 범위 줄 꼬리.
UNSAVED_LABEL = "미저장 편집"


class AlertScope(NamedTuple):
    """상태 알림의 범위(`alerts.state(scope=…)`)와 로그의 범위 줄(`scope_label=…`)."""

    scope: dict[str, object]
    label: str


def simulation_scope(
    active_scenario: ActiveScenario,
    period: tuple[int, int] | None = None,
    *,
    dates: tuple[date, date] | None = None,
) -> AlertScope:
    """활성 리비전 내용 토큰(+ 조회기간)으로 범위를 짓는다. `period` 는 달(`YYYYMM`) 두 개, `dates`
    는 날짜로 보는 화면(표준 목표 조회일)의 두 날이다. 둘 다 None 이면 시나리오 전체 기간을 보는
    알림이다."""
    token = str(active_scenario["content_token"])
    scope: dict[str, object] = {"token": token}
    parts: list[str] = []
    label = active_scenario_label()
    if label is not None:
        parts.append(f"{label.scenario_name} · r{label.revision_no}")
    if not is_pristine_content_token(token):
        parts.append(UNSAVED_LABEL)
    if dates is not None:
        scope["dates"] = [dates[0].isoformat(), dates[1].isoformat()]
        parts.append(f"{dates[0]:%y.%m.%d}–{dates[1]:%y.%m.%d}")
    elif period is not None:
        start, end = int(period[0]), int(period[1])
        scope["period"] = [start, end]
        parts.append(f"{month_label(start)}–{month_label(end)}")
    else:
        parts.append(FULL_PERIOD_LABEL)
    return AlertScope(scope, " · ".join(parts))


def _json_value(value: object) -> str | int | float | None:
    """표 칸 하나를 JSON 값으로 — 빈 값(NaN · NA · NaT)은 None, 수는 파이썬 수, 그 밖은 글."""
    item = getattr(value, "item", None)
    native: object = item() if callable(item) and not isinstance(value, str) else value
    if native is None or native is pd.NA or native is pd.NaT:
        return None
    if isinstance(native, bool):
        return str(native)
    if isinstance(native, int):
        return native
    if isinstance(native, float):
        return native if math.isfinite(native) else None
    return str(native)


def alert_table(
    frame: pd.DataFrame,
    *,
    title: str,
    file_name: str,
    labels: ProcessLabels | None = None,
) -> alerts.AlertTable | None:
    """알림에 딸린 표. 칸 차례는 `frame` 그대로다(부르는 쪽이 표시순서로 칸을 세운 내보내기 프레임을
    준다). 행이 `alerts.TABLE_ROW_LIMIT` 를 넘으면 None — 본문 목록을 남기라는 뜻이다."""
    if len(frame) > alerts.TABLE_ROW_LIMIT:
        return None
    columns = [str(column) for column in frame.columns]
    rows = [
        [_json_value(value) for value in record]
        for record in frame.itertuples(index=False, name=None)
    ]
    shown: dict[str, dict[str, str]] = {}
    if labels and PROCESS_COLUMN in frame.columns:
        renamed = {
            str(value): labels.label(value)
            for value in frame[PROCESS_COLUMN].dropna().unique()
            if labels.label(value) != str(value)
        }
        if renamed:
            shown[PROCESS_COLUMN] = renamed
    return alerts.AlertTable(
        title=title,
        columns=columns,
        rows=rows,
        total=len(frame),
        file=file_name,
        shown=shown,
    )


def alert_page_error(message: str, *, code: str, tab: str = "") -> None:
    """화면을 그리지 못한 오류의 알림(자리 `st.error` 는 부르는 쪽 몫). 같은 코드 + 같은 글이면 같은
    id 라 이 브라우저 탭에 한 번만 뜬다. 이벤트 칸에 한 자리를 쓴다."""
    plain = alerts.plain_text(message)
    lead = alerts.plain_text(message.split("\n\n", 1)[0]) or plain
    alerts.emit(
        [
            alerts.event_note(
                code,
                text=lead,
                full=plain,
                tab=tab,
                alert_id="page-" + alerts.fingerprint(code, None, plain),
            )
        ]
    )
