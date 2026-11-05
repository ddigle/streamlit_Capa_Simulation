# Purpose: 시험이 알림 표지(이벤트 칸 `st.html`)에서 알림창 알림과 버튼 곁 결과 알림을 읽는 도우미.

"""알림 표지 읽기(`capa_simulation.alerts`).

버튼 곁 결과 알림(`flash.queue_flash`)의 성공 · 안내는 2026-11-03 결정 보드 D3 (가)부터 버튼 곁 칸에
그리지 않고 알림창 표지로만 낸다 — `app.success` · `app.info` 에 들지 않는다. 시험은 이 도우미로
표지에 실린 알림을 읽는다. `successes` · `infos` 는 화면에 그린 `st.success` · `st.info` 와 표지의
같은 종류 결과 알림을 함께 돌려준다(그린 것 먼저, 표지 차례) — 옛 `app.success` 자리를 그대로 바꿔
넣을 수 있게 `.value` 를 단다. 그린 글은 마크다운 그대로, 표지 글은 평문이다(`alerts.plain_text` —
마크다운 꾸밈을 걷는다).

다시 보낸 표지(`again` — 끊긴 회차를 덮는 같은 id 의 둘째 표지)는 브라우저가 다시 띄우지 않으므로
세지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import ElementTree

from capa_simulation.alerts import MARKER_ATTRIBUTE, marker_notes


@dataclass(frozen=True)
class Shown:
    """그린 알림 · 표지 알림 하나 — `value` 는 글(표지는 버튼 곁 원문 마크다운), `icon` 은 아이콘,
    `note` 는 표지 JSON(그린 것은 None). 옛 `element.proto.icon` · `.proto.body` 자리를 그대로 읽게
    `proto` 가 자기 자신이다."""

    value: str
    icon: str = ""
    note: dict[str, Any] | None = None

    @property
    def code(self) -> str:
        return "" if self.note is None else str(self.note.get("code", ""))

    @property
    def body(self) -> str:
        return self.value

    @property
    def proto(self) -> Shown:
        return self


def alert_notes(app: AppTest | ElementTree, *, again: bool = False) -> list[dict[str, Any]]:
    """표지에 실린 알림(문서 차례). `again=True` 면 다시 보낸 표지도 넣는다."""
    tree = app._tree if isinstance(app, AppTest) else app
    notes: list[dict[str, Any]] = []
    for element in tree.get("html"):
        body = getattr(getattr(element, "proto", None), "body", "")
        if isinstance(body, str):
            notes.extend(marker_notes(body))
    return [note for note in notes if again or not note.get("again")]


def flashed(app: AppTest, kind: str | None = None) -> list[Shown]:
    """표지에 실린 버튼 곁 결과 알림(`flash` 종류 — success · info · warning · error)."""
    return [
        Shown(str(note.get("markdown", note.get("full", ""))), str(note.get("icon", "")), note)
        for note in alert_notes(app)
        if "flash" in note and (kind is None or note.get("flash") == kind)
    ]


def successes(app: AppTest, *, sidebar: bool = False) -> list[Shown]:
    """그린 `st.success`(마크다운 그대로 — `sidebar` 면 사이드바 것만) + 표지의 성공 결과
    알림(평문).

    표지는 이벤트 칸에 서서 어느 칸(본문 · 사이드바)의 알림인지 가리지 않는다 — 칸 key 는
    `note["origin"]`."""
    drawn = app.sidebar.success if sidebar else app.success
    return [
        *(Shown(str(element.value), str(element.proto.icon)) for element in drawn),
        *flashed(app, "success"),
    ]


def infos(app: AppTest, *, sidebar: bool = False) -> list[Shown]:
    """그린 `st.info` + 표지의 안내 결과 알림."""
    drawn = app.sidebar.info if sidebar else app.info
    return [
        *(Shown(str(element.value), str(element.proto.icon)) for element in drawn),
        *flashed(app, "info"),
    ]


def page_html(app: AppTest) -> list[Any]:
    """`app.get("html")` 에서 알림 표지(`data-capa-alerts`)와 빈 표지 자리(`<style></style>`)를 뺀
    것 — 표지는 `render_flash` · `alerts.state` 가 부를 때마다 한 자리를 쓴다."""
    return [
        element
        for element in app.get("html")
        if not (
            str(element.proto.body) == "<style></style>"
            or MARKER_ATTRIBUTE in str(element.proto.body)
        )
    ]


def shown(app: AppTest, kind: str) -> list[Shown]:
    """옛 `getattr(app, kind)` 자리 — 성공 · 안내는 그린 것 + 표지(`successes` · `infos`), 그
    밖(경고 · 오류 · 캡션 · 마크다운)은 그린 것만(경고 · 오류 결과 알림은 버튼 곁에도 그려 표지를
    더하면 두 번 센다)."""
    if kind == "success":
        return successes(app)
    if kind == "info":
        return infos(app)
    return [Shown(str(element.value)) for element in getattr(app, kind)]


def texts(shown: list[Shown]) -> list[str]:
    return [item.value for item in shown]


def states(app: AppTest | ElementTree, code: str | None = None) -> list[dict[str, Any]]:
    """표지의 상태 알림(`alerts.state`) — `code` 를 주면 그 코드만(문서 차례). 조건이 없는 회차의
    해소 표지(`active` 거짓)도 든다."""
    return [
        note
        for note in alert_notes(app)
        if note.get("kind") == "state" and (code is None or note.get("code") == code)
    ]


def active_state(app: AppTest | ElementTree, code: str) -> dict[str, Any] | None:
    """`code` 상태 알림 가운데 조건이 있는(`active`) 마지막 표지. 없으면 None."""
    found = [note for note in states(app, code) if note.get("active")]
    return found[-1] if found else None


def note_table(note: Mapping[str, Any], title: str) -> dict[str, Any]:
    """알림 표지에 딸린 표(`alerts.AlertTable`) 가운데 이름이 `title` 인 것 하나."""
    (table,) = [table for table in note.get("tables", []) if table["title"] == title]
    return dict(table)


def table_frame(table: Mapping[str, Any]) -> pd.DataFrame:
    """딸린 표의 원본 값 프레임 — CSV 가 싣는 값과 칸이다."""
    return pd.DataFrame(table["rows"], columns=table["columns"])


def events(app: AppTest | ElementTree, code: str) -> list[dict[str, Any]]:
    """표지의 사건 알림 가운데 `code` 인 것(버튼 곁 결과 알림이 아닌 `alerts.event`)."""
    return [
        note
        for note in alert_notes(app)
        if note.get("kind") == "event" and note.get("code") == code
    ]
