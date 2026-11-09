# Purpose: 알림 등록부의 코드·단계 계약과 사건·상태 알림 표지(이벤트 칸 한 자리·지문)를 시험한다.

"""`capa_simulation/alerts.py` — 등록부 · 표지 · 지문. 알림 칸 JS 는
`tests/test_alert_center_assets.py` 가 본다."""

from __future__ import annotations

import re

import pytest
from alert_marks import alert_notes
from streamlit.testing.v1 import AppTest

from capa_simulation import alerts


def test_registry_codes_are_unique_well_formed_and_levelled() -> None:
    """코드는 `AB-01` 꼴의 고정 id 이고 겹치지 않는다. 단계는 넷 · 갈래는 둘 가운데 하나다."""
    codes = [spec.code for spec in alerts.SPECS]
    assert len(codes) == len(set(codes))
    assert all(re.fullmatch(r"[A-Z]{2,4}-\d{2}", code) for code in codes)
    assert all(spec.level in alerts.LEVELS for spec in alerts.SPECS)
    assert all(spec.kind in ("event", "state") for spec in alerts.SPECS)
    assert all(spec.title for spec in alerts.SPECS)
    assert set(alerts.REGISTRY) == set(codes)


@pytest.mark.parametrize(
    ("code", "level", "title"),
    [
        ("EQ-19", "check", "설비 마스터 — 다른 사용자가 일정을 저장해 최신 리비전이 있음"),
        ("RS-03", "check", "필요 단축 일정 — 일정 미정 호기"),
        ("RS-04", "info", "필요 단축 일정 — 사용기준(HBM · EDP) 밖 호기를 셈에서 뺌"),
        ("RS-05", "check", "필요 단축 일정 — 입력 비가동 반영 · 가용 넘침"),
        ("EQ-20", "check", "가용설비 Summary — 반입 · Qual 일정이 빈 호기(일정 미정)"),
        ("EQ-21", "check", "가용설비 Main — 일정이 지났는데 실적이 빈 호기(미확인)"),
        ("EQ-22", "info", "가용설비 Summary — 사용기준이 HBM · EDP 밖이라 뺀 호기"),
        ("EQ-23", "info", "Static 대비 일정 — 입력 비가동을 일정기준 가용에서 뺌"),
    ],
)
def test_state_codes_for_the_screen_bundles_are_registered(
    code: str, level: str, title: str
) -> None:
    """설비 마스터 남의 저장 표지 · 필요 단축 일정 머리 표지가 낼 상태 알림 코드는 등록부에 먼저
    선다 —
    부르는 자리를 짓는 쪽이 이 코드로 낸다."""
    spec = alerts.spec(code)
    assert (spec.level, spec.kind, spec.title) == (level, "state", title)


def test_the_registry_refuses_a_duplicate_or_malformed_code() -> None:
    first = alerts.AlertSpec("ZZ-01", "info", "event", "시험")
    with pytest.raises(ValueError, match="겹칩니다"):
        alerts._registry([first, first])
    with pytest.raises(ValueError, match="꼴"):
        alerts._registry([alerts.AlertSpec("zz-1", "info", "event", "시험")])


def test_levels_carry_names_and_popup_times() -> None:
    """단계 넷 — 알림 · 확인 필요 · 조치 필요 · 오류. 알림창은 알림 8초 · 나머지 15초(설계 7장 끝
    기본값)."""
    assert alerts.LEVELS == ("info", "check", "action", "error")
    assert list(alerts.LEVEL_LABELS) == list(alerts.LEVELS)
    assert list(alerts.LEVEL_LABELS.values()) == [
        "알림",
        "확인 필요",
        "조치 필요",
        "오류",
    ]
    assert dict(alerts.POPUP_SECONDS) == {"info": 8, "check": 15, "action": 15, "error": 15}
    assert (alerts.POPUP_LIMIT, alerts.REPEAT_WINDOW_SECONDS, alerts.ATTENTION_MS) == (3, 60, 450)
    assert alerts.ATTENTION_EASING == "cubic-bezier(0.5, 1, 0.89, 1)"
    assert (alerts.HISTORY_ROWS, alerts.HISTORY_HOURS, alerts.SHORT_LIMIT) == (200, 12, 60)


def test_flash_kinds_map_to_registered_event_codes() -> None:
    assert set(alerts.FLASH_CODES) == {"success", "info", "warning", "error"}
    for code in alerts.FLASH_CODES.values():
        assert alerts.spec(code).kind == "event"
    assert [alerts.spec(alerts.FLASH_CODES[kind]).level for kind in ("warning", "error")] == [
        "check",
        "error",
    ]


def test_the_fingerprint_is_code_scope_and_content_regardless_of_key_order() -> None:
    """지문 = 코드 + 범위 + 내용(구조 값). 사전 키 차례는 지문을 바꾸지 않고 셋 가운데 하나만 달라도
    바뀐다."""
    scope = {"token": "t1", "period": ["2026-01", "2026-12"]}
    same = {"period": ["2026-01", "2026-12"], "token": "t1"}
    base = alerts.fingerprint("ST-01", scope, ["A", "B"])
    assert alerts.fingerprint("ST-01", same, ["A", "B"]) == base
    assert alerts.fingerprint("ST-02", scope, ["A", "B"]) != base
    assert alerts.fingerprint("ST-01", {**scope, "token": "t2"}, ["A", "B"]) != base
    assert alerts.fingerprint("ST-01", scope, ["A"]) != base


def test_short_text_folds_lines_and_ellipsizes_past_the_limit() -> None:
    assert alerts.short_text("한 줄\n두 줄   셋") == "한 줄 두 줄 셋"
    long = "가" * 80
    assert alerts.short_text(long) == "가" * 59 + "…"
    assert len(alerts.short_text(long)) == alerts.SHORT_LIMIT


@pytest.mark.parametrize(
    ("markdown", "plain"),
    [
        (":material/check: **「A\\~B」** 를 저장했습니다.", "「A~B」 를 저장했습니다."),
        (":orange-badge[적용 전 편집] `UPEH` *기울임*", "적용 전 편집 UPEH 기울임"),
        ("r3 \\(가정\\) 2\\*3", "r3 (가정) 2*3"),
        ("a*b*c 그대로", "a*b*c 그대로"),
    ],
)
def test_plain_text_strips_markdown_decoration(markdown: str, plain: str) -> None:
    """알림창 · 패널은 글을 `textContent` 로 넣는다 — 버튼 곁 마크다운 꾸밈이 글자로 보이지 않게
    걷는다."""
    assert alerts.plain_text(markdown) == plain


def test_a_marker_round_trips_quotes_and_angle_brackets() -> None:
    note = alerts.AlertNote(code="FL-01", kind="event", short='"<b>&', full="'전문'")
    body = f'<style {alerts.MARKER_ATTRIBUTE}="'
    import html
    import json

    body += html.escape(json.dumps([note], ensure_ascii=False), quote=True) + '"></style>'
    assert alerts.marker_notes(body) == [dict(note)]
    assert alerts.marker_notes("<style></style>") == []


STATE = """
import streamlit as st

from capa_simulation import alerts

alerts.note_page("Static Capa", "static_capa")
alerts.state(
    "ZZ-02",
    scope={"token": "t1", "period": ["2026-01", "2026-12"]},
    content=sorted(st.session_state.get("missing", [])),
    active=bool(st.session_state.get("missing")),
    text=f"빠진 수요 {len(st.session_state.get('missing', []))}건",
    scope_label="DEMO 시나리오 · r1 · 26.01–26.12",
)
st.button("뒤", key="after")
"""


@pytest.fixture
def state_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    """시험용 상태 코드(`ZZ-02`)를 등록부에 잠깐 싣는다 — 등록하지 않은 코드로는 알리지 않는다."""
    registry = dict(alerts.REGISTRY)
    registry["ZZ-02"] = alerts.AlertSpec("ZZ-02", "check", "state", "시험 상태 알림")
    monkeypatch.setattr(alerts, "REGISTRY", registry)


@pytest.mark.usefixtures("state_spec")
def test_a_state_alert_writes_one_event_slot_whether_or_not_the_condition_holds() -> None:
    """상태 알림은 그 조건을 보는 회차마다 부르고 이벤트 칸에 늘 한 자리를 쓴다 — 조건이 없어도
    `active=False` 표지다(해소를 알린다). 자리(본문)에는 아무것도 그리지 않는다(D2 (나))."""
    app = AppTest.from_string(STATE).run()
    assert not app.exception
    (quiet,) = alert_notes(app)
    assert (quiet["kind"], quiet["active"], quiet["fp"]) == ("state", False, "")
    assert (quiet["page"], quiet["href"]) == ("Static Capa", "static_capa")
    main_count = len(app.main.children)

    app.session_state["missing"] = ["DEMO-A", "DEMO-B"]
    app.run()
    (loud,) = alert_notes(app)
    assert loud["active"] is True and loud["level"] == "check"
    assert loud["short"] == "빠진 수요 2건" and loud["scope_label"].startswith("DEMO 시나리오")
    assert loud["scope"] == quiet["scope"]
    assert loud["fp"] == alerts.fingerprint(
        "ZZ-02", {"token": "t1", "period": ["2026-01", "2026-12"]}, ["DEMO-A", "DEMO-B"]
    )
    assert len(app.main.children) == main_count
    assert not app.warning


EVENT = """
import streamlit as st

from capa_simulation import alerts

if st.session_state.get("go"):
    st.session_state["go"] = False
    alerts.event("FL-01", text="저장했습니다.", cause="「저장」 누름")
st.session_state["outbox_after_event"] = len(st.session_state.get(alerts.OUTBOX_KEY, []))
alerts.flush()
"""


def test_an_event_is_queued_without_drawing_and_sent_by_the_next_marker() -> None:
    """사건 알림은 담기만 한다 — 이벤트 칸을 쓰지 않아 어느 갈래에서 불러도 된다. 같은 회차의 다음
    표지 자리(`flush`)가 보낸다. 알릴 것이 없는 `flush` 는 빈 스타일 한 자리다."""
    app = AppTest.from_string(EVENT).run()
    assert [element.proto.body for element in app.get("html")] == ["<style></style>"]
    app.session_state["go"] = True
    app.run()
    assert app.session_state["outbox_after_event"] == 1
    (note,) = alert_notes(app)
    assert (note["code"], note["kind"], note["level"], note["cause"]) == (
        "FL-01",
        "event",
        "info",
        "「저장」 누름",
    )
    assert note["id"] and alerts.OUTBOX_KEY not in app.session_state
    assert len(app.get("html")) == 1


def test_an_unregistered_code_is_refused() -> None:
    app = AppTest.from_string(
        "from capa_simulation import alerts\nalerts.event('NO-99', text='글')"
    ).run()
    assert app.exception


def test_the_server_analysis_record_is_only_a_placeholder() -> None:
    """분석 기록(L2)은 usage-log 1단계와 함께 만든다(D6 (가)) — 지금은 아무것도 쓰지 않는 자리
    하나다."""
    alerts.record_server_event({"code": "FL-01"})
    assert "open" not in alerts.record_server_event.__code__.co_names
    assert alerts.ALERT_LOG_SWITCH == "CAPA_USAGE_LOG"


TABLED = """
import streamlit as st

from capa_simulation import alerts

active = bool(st.session_state.get("rows"))
alerts.state(
    "ZZ-02",
    scope={"token": "t1"},
    content=len(st.session_state.get("rows", [])),
    active=active,
    text="뺀 기준 2개",
    tab="대당 Capa",
    tables=[
        alerts.AlertTable(
            title="제외 기준정보",
            columns=["공정"],
            rows=[["DEMO-P1"], ["DEMO-P2"]],
            total=2,
            file="x.csv",
            shown={},
            help={},
        ),
        None,
    ],
)
"""


@pytest.mark.usefixtures("state_spec")
def test_a_state_alert_carries_its_tab_and_a_table_only_while_the_condition_holds() -> None:
    """`tab` 은 그 화면 안 탭 이름(「그 화면으로」 가 연다), `tables` 는 Alarm 줄에서 펼칠 표들 —
    조건이 있을 때만 싣고(없음 표지에 표를 싣지 않는다) 커서 None 인 칸은 뺀다."""
    app = AppTest.from_string(TABLED)
    app.session_state["rows"] = [1, 2]
    app.run()
    (loud,) = alert_notes(app)
    assert loud["tab"] == "대당 Capa"
    assert [table["rows"] for table in loud["tables"]] == [[["DEMO-P1"], ["DEMO-P2"]]]
    app.session_state["rows"] = []
    app.run()
    (quiet,) = alert_notes(app)
    assert quiet["active"] is False and "tables" not in quiet and quiet["tab"] == "대당 Capa"
