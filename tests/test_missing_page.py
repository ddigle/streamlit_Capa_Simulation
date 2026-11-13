# Purpose: 없는 화면 주소로 들어온 회차가 한 번 알리고 꺼진 모듈이면 모듈 · 담당을 싣는지 시험한다.

"""없는 화면 주소(`components/missing_page.py` — 2026-11-14 「앱 대신 뜨는 화면」 보드 카드
p2-rare)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alert_marks import alert_notes
from streamlit.testing.v1 import AppTest

from capa_simulation import module_registry
from capa_simulation.components import missing_page

SCRIPT = """
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.missing_page import notice_missing_page

alerts.note_page("HOME", "")
notice_missing_page(st.session_state.get("landed", ""))
alerts.flush()
"""


def _requested(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    monkeypatch.setattr(missing_page, "requested_path", lambda: path)


def test_an_unknown_address_is_told_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """등록되지 않은 주소로 들어와 HOME 을 돌면 안내 알림 하나 — 같은 주소는 이 세션에 한 번이다."""
    _requested(monkeypatch, "old_screen")

    app = AppTest.from_string(SCRIPT).run()

    (note,) = [note for note in alert_notes(app) if note["code"] == missing_page.MISSING_CODE]
    assert note["short"] == "없는 화면 주소 — HOME 을 열었습니다"
    assert "/old_screen" in note["full"] and note["cause"] == missing_page.MISSING_CAUSE
    app.run()
    assert not [note for note in alert_notes(app) if note["code"] == missing_page.MISSING_CODE]


@pytest.mark.parametrize("path", ["", "static_capa"])
def test_a_registered_or_root_address_says_nothing(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """요청한 주소가 이번에 도는 화면이면(첫 화면 포함) 알리지 않는다."""
    _requested(monkeypatch, path)

    at = AppTest.from_string(SCRIPT)
    at.session_state["landed"] = path
    app = at.run()

    assert not [note for note in alert_notes(app) if note["code"] == missing_page.MISSING_CODE]


def test_a_switched_off_module_address_names_the_module_and_its_owner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """꺼진 모듈 화면 주소면 「「<모듈>」 은 꺼져 있습니다 · 담당 <이름>」 이다."""
    manifest = module_registry.ModuleManifest(
        id="demo_off",
        name="데모 꺼짐",
        api=1,
        owner="데모 담당",
        enabled=False,
        maturity="L0",
        pages=(),
    )
    record = module_registry.ModuleRecord(
        folder_name="demo_off", path=tmp_path, state="off", reason="꺼짐", manifest=manifest
    )
    scan = module_registry.ModuleScan(
        root=tmp_path, root_exists=True, records=(record,), disabled_value="", unknown_disabled=()
    )
    monkeypatch.setattr(module_registry, "discovered", lambda **_: scan)

    short, full = missing_page.missing_text("mod-demo_off-main")

    assert short == "「데모 꺼짐」은 꺼져 있습니다 · 담당 데모 담당"
    assert "/mod-demo_off-main" in full
    assert missing_page.missing_text("mod-unknown-main")[0] == missing_page.UNKNOWN_TEXT
