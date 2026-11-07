# Purpose: 화면이 상태 알림·화면 오류 알림을 낼 때 쓰는 공용 조각(범위·딸린 표·오류 표지)을 둔다.

"""알림 체계 2단계(2026-11-03 결정 보드 D2 (나)) — 화면 쪽 공용 조각. 규칙은 `alerts` 모듈 설명이다.

- `simulation_scope` — 시뮬레이션 상태 알림의 범위(지문 재료 — 활성 리비전 `content_token` 과,
  조회기간을 보는 알림이면 그 기간)와 로그의 범위 줄(「시나리오 · rN · 26.01–26.12」). **세션만
  읽는다** — 시나리오나 조회기간을 바꾸면 수가 같아도 새 알림이다.
- `equipment_scope` — 설비 상태 알림의 범위(세션이 든 (공통 대장, 일정) 리비전 쌍 — 설비 시나리오나
  리비전을 바꾸면 같은 조건이라도 새 알림이다)와 로그의 범위 줄(「설비 「이름」 rN」).
- `alert_table` — 본문에서 뺀 목록을 알림에 싣는 표(`alerts.AlertTable` — Alarm 줄에서 펼쳐 보고
  CSV 로 내려받는다). 값은 JSON 값으로 바꾸고(NaN → 빈칸) 공정 칸은 표시명을 화면에만 입힌다(CSV
  는 원본 — `exclusion_table` 과 같은 규칙), 칸 머리 풍선(`column_help`)은 있는 칸에만 싣는다.
  `alerts.TABLE_ROW_LIMIT` 를 넘으면 None 이라 화면이 본문 목록을 그대로 둔다. `clip=True` 면 None
  대신 앞부분만 싣는다(`table_clipped` · `clipped_label` — 전체는 그 화면 맨 아래 CSV 단추 하나이고
  알림 글이 그 자리를 부른다).
- `ALARM_ROW_PLACE` · `alarm_table_place` — 목록이 딸린 표일 때 알림 글이 그 자리를 부르는 말.
- `alert_page_error` — 화면을 그리지 못한 오류의 알림만 이벤트 칸으로 보낸다. 보통은 마크와 알림을
  한 칸에 싣는 `components/data_error_mark.render_data_error` 를 쓰고, 이 함수는 한 오류의 마크가 탭
  여럿에 서서(`render_data_error_mark`) 알림을 그 밖에서 한 번 보내는 자리(산출 결과)만 쓴다.
- `missing_handover_text` — 넘겨받은 공정을 열지 못한 사건 알림(`PD-02` · `CS-02`)의 글(평문 —
  이름을 막지 않는다).
- `tab_name` · `open_tab_name` — 탭 안 상태 알림의 `tab`(「그 화면으로」 가 그 탭까지 연다 — 탭 안
  탭은 바깥 → 안 차례로 ` › ` 로 잇는다). `open_tab_name` 은 닫힌 탭이면 None 이다 — 그 회차에는 그
  탭의 상태 알림을 내지 않는다(설계 2-3 「숨은 자리는 세지 않는다」 — 숨은 탭에서 난 알림창은 어디
  것인지 모른다).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import date
from typing import NamedTuple

import pandas as pd

from capa_simulation import alerts
from capa_simulation.components.data_error_mark import ErrorGoto, data_error_note
from capa_simulation.components.process_labels import PROCESS_COLUMN, ProcessLabels
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.equipment_scenario_activation import EquipmentSession
from capa_simulation.scenario_activation import active_scenario_label
from capa_simulation.scenario_state import ActiveScenario, is_pristine_content_token
from capa_simulation.services.korean_particle import object_particle, topic_particle
from capa_simulation.services.month_columns import month_label

# 범위 줄에서 기간을 보지 않는 알림(대당 Capa 의 측정률 가정 · 적용 뒤 전체 기간 셈)의 말.
FULL_PERIOD_LABEL = "시나리오 전체 기간"
# 활성 리비전에 저장하지 않은 편집이 든 회차의 범위 줄 꼬리.
UNSAVED_LABEL = "미저장 편집"
# 탭 안 탭의 `tab` 이음 — 알림 칸 JS 의 `TAB_PATH` 와 같은 글이다(바깥 칸부터 한 칸씩 연다).
TAB_PATH = " › "
# 탭 단추 글 앞 아이콘(`:material/…:`) — 알림의 탭 이름은 아이콘 없이 단추 글의 끝과 맞댄다.
_ICON_PATTERN = re.compile(r"^:material/[a-z0-9_]+:\s*")
# 목록이 알림에 딸린 표일 때 그 자리를 부르는 말 — 짧은 글은 이것만, 전문은 표 이름까지 적는다
# (`alarm_table_place`). 표가 커서 본문에 남으면 부르는 쪽이 그 펼침 자리를 적는다.
ALARM_ROW_PLACE = "Alarm › 이 줄"


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


def equipment_scope(session: EquipmentSession) -> AlertScope:
    """설비 세션의 (공통 대장 리비전, 일정 리비전) 쌍 토큰으로 범위를 짓는다. 스냅샷이 없으면(설비
    데이터 없음) 토큰이 None 이다."""
    token = session.snapshot.token if session.snapshot is not None else None
    label = ""
    if session.scenario_name is not None:
        revision = f" r{session.revision_no}" if session.revision_no is not None else ""
        label = f"설비 「{session.scenario_name}」{revision}"
    return AlertScope({"equipment": token}, label)


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


def alarm_table_place(title: str) -> str:
    """전문이 목록 자리로 쓰는 말 — 이 줄에 딸린 표 「이름」."""
    return f"{ALARM_ROW_PLACE} 「{title}」"


def alert_table(
    frame: pd.DataFrame,
    *,
    title: str,
    file_name: str,
    labels: ProcessLabels | None = None,
    column_help: Mapping[str, str] | None = None,
    clip: bool = False,
) -> alerts.AlertTable | None:
    """알림에 딸린 표. 칸 차례는 `frame` 그대로다(부르는 쪽이 표시순서로 칸을 세운 내보내기 프레임을
    준다). `column_help` 는 칸 머리 풍선(칸 이름 → 글 — 없는 칸은 뺀다)이다. 행이
    `alerts.TABLE_ROW_LIMIT` 를 넘으면 None — 본문 목록을 남기라는 뜻이다. `clip` 이면 None 대신 앞
    `TABLE_ROW_LIMIT` 행만 싣고 `total` 에 원래 행 수를 둔다(`table_clipped`)."""
    if len(frame) > alerts.TABLE_ROW_LIMIT and not clip:
        return None
    columns = [str(column) for column in frame.columns]
    rows = [
        [_json_value(value) for value in record]
        for record in frame.head(alerts.TABLE_ROW_LIMIT).itertuples(index=False, name=None)
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
        help={column: text for column, text in (column_help or {}).items() if column in columns},
    )


def table_clipped(table: alerts.AlertTable) -> bool:
    """앞부분만 실은 표인가(`alert_table(clip=True)`) — 그러면 전체는 화면 CSV 단추가 맡는다."""
    return len(table["rows"]) < table["total"]


def clipped_label(table: alerts.AlertTable) -> str:
    """앞부분만 실은 표의 크기 말 — 알림 전문이 쓰고 Alarm 표 머리(`table_rows_clipped`)와 같은
    꼴이다."""
    return f"앞 {len(table['rows']):,}건 · 전체 {table['total']:,}건"


def alert_page_error(
    message: str,
    *,
    code: str,
    tab: str = "",
    text: str | None = None,
    goto: ErrorGoto | None = None,
) -> None:
    """화면을 그리지 못한 오류의 알림(글 · 같은 글 한 번 · `goto` 는 `data_error_note`). 자리
    마크는 부르는 쪽 몫이고 이벤트 칸에 한 자리를 쓴다."""
    alerts.emit([data_error_note(message, code=code, tab=tab, text=text, goto=goto)])


def tab_name(*labels: str) -> str:
    """탭 단추 글(아이콘 포함 그대로 — 바깥 → 안)을 알림의 `tab` 으로 — 아이콘을 떼고 ` › ` 로
    잇는다."""
    return TAB_PATH.join(_ICON_PATTERN.sub("", label).strip() for label in labels)


def open_tab_name(tab: OpenTab | None, *labels: str) -> str | None:
    """열린 탭이면 `tab_name(*labels)`, 닫힌 탭이면 None — 닫힌 탭 안의 상태 알림은 그 회차에 내지
    않는다(부르는 쪽이 None 이면 `alerts.state` 를 건너뛴다)."""
    return None if tab_is_hidden(tab) else tab_name(*labels)


def missing_handover_text(missing: str, opened: str | None, *, fallback: str) -> str:
    """넘겨받은 공정(`missing` — 표시명)이 시나리오 · 조회기간에 없어 다른 공정으로 연 사건 알림의
    글. `opened` 는 대신 연 공정 표시명이고 None 이면 `fallback`(「기본 공정을」 · 「공정
    없이」)이다. 알림창 · 패널은 평문(`textContent`)이라 이름을 막지 않는다 — 마크다운 자리에 그리지
    않는다."""
    target = fallback if opened is None else f"「{opened}」{object_particle(opened)}"
    lead = f"넘겨받은 공정 「{missing}」{topic_particle(missing)}"
    return f"{lead} 시나리오·조회기간에 없어 {target} 엽니다"
