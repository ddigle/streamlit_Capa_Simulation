# Purpose: VOC 새 글 초안 보관의 판정 구획을 node 로, VOC 화면이 넘기는 값과 듣개 계약을 고정한다.

"""VOC 새 글 초안 보관(`components/voc_draft_keeper.py` — 개선 I84).

새 글 폼의 제목·내용은 올리기 전에는 서버가 몰라, 화면 이동·테마 전환(새로고침)에 말없이
사라졌다(2026-10-26 E2E). 브라우저 탭에 두었다가 빈 폼에 되살린다. AppTest 는 그 JS 를 못 돌리므로
DOM 을 모르는 판정 구획(`// <voc-draft>`)은 node(없으면 bun)로 떼어 돌리고, 화면이 넘기는 값(세션
표지·폼 세대·칸 선택자)은 컴포넌트 대역으로 본다. 브라우저 동작은 사본 앱으로 본다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from alert_marks import successes
from streamlit.testing.v1 import AppTest
from test_voc_page import _script

from capa_simulation import alerts
from capa_simulation.components import voc_draft_keeper
from capa_simulation.components.voc_draft_keeper import _JS, DRAFT_STORAGE_KEY


def _node(runner: str) -> Any:
    match = re.search(r"// <voc-draft>\n(?P<body>.*?)\n// </voc-draft>", _JS, re.S)
    assert match, "voc_draft_keeper 스크립트에 // <voc-draft> 구획이 없습니다"
    runtime = shutil.which("node") or shutil.which("bun")
    if runtime is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("CI 러너에 node 가 없다 — VOC 초안 판정 구획 시험을 건너뛸 수 없다")
        pytest.skip("node·bun 이 없다 — CI 에서 돈다")
    completed = subprocess.run(
        [runtime, "-e", match.group("body") + "\n" + runner],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_the_draft_is_restored_into_an_empty_form_and_forgotten_after_posting() -> None:
    """빈 폼이면 되살리고(새로고침으로 선 세션 · 같은 세션의 화면 이동), 칸에 글이 있으면 덮지
    않는다. 같은 세션에서 폼 세대가 올랐으면(글을 올렸다) 버린다 — 새로고침으로 선 세션은 세대가
    0 으로 돌아가므로 세대만으로 가르지 않는다. 올린 뒤 옛 값 회차가 빈 새 폼에 되살린 초안(두 칸이
    올린 글 그대로)은 칸까지 비운다."""
    cases = {
        "reload": [{"session": "a", "generation": 2, "title": "T", "body": "B"}, "b", 0, {}],
        "page_trip": [{"session": "a", "generation": 0, "title": "", "body": "B"}, "a", 0, {}],
        "typed": [
            {"session": "a", "generation": 0, "title": "T", "body": "B"},
            "a",
            0,
            {"title": "새로 친 글"},
        ],
        "posted": [{"session": "a", "generation": 0, "title": "T", "body": "B"}, "a", 1, {}],
        "posted_refilled": [
            {"session": "a", "generation": 0, "title": "T", "body": "B"},
            "a",
            1,
            {"title": "T", "body": "B"},
        ],
        "empty": [{"session": "a", "generation": 0, "title": "", "body": ""}, "b", 0, {}],
        "none": [None, "a", 0, {}],
        "broken": ["글자", "a", 0, {}],
    }
    runner = f"""
const cases = {json.dumps(cases, ensure_ascii=False)}
const out = {{}}
for (const [name, [stored, session, generation, current]] of Object.entries(cases)) {{
  out[name] = draftAction(stored, session, generation, {{ title: '', body: '', ...current }})
}}
process.stdout.write(JSON.stringify(out))
"""
    assert _node(runner) == {
        "reload": "restore",
        "page_trip": "restore",
        "typed": "none",
        "posted": "forget",
        "posted_refilled": "forget-clear",
        "empty": "none",
        "none": "none",
        "broken": "none",
    }


def test_the_script_keeps_one_input_listener_and_sets_values_react_can_see() -> None:
    """듣개는 문서에 하나다(회차마다 옛 것을 떼고 새로 단다 — 그 회차의 세대를 쓴다). 되살린 값은
    원래 setter 로 넣고 `input` 사건을 내야 React 칸이 받는다. 탭 칸을 못 써도 막지 않는다."""
    assert "doc.removeEventListener('input', previous, true)" in _JS
    assert "win.__capaVocDraftInput = onInput" in _JS
    assert "descriptor.set.call(element, value)" in _JS
    assert "element.dispatchEvent(new Event('input', { bubbles: true }))" in _JS
    assert "win.sessionStorage" in _JS and "localStorage" not in _JS
    assert "innerHTML" not in _JS


def test_a_restored_draft_is_told_through_the_alert_center_not_a_line_under_the_form() -> None:
    """되살렸으면 같은 문서의 알림 칸(`window.__capaAlerts.raise` — 칸이 아직 없으면 줄)에 사건
    알림을 낸다 — 폼 아래에 제 꼴의 줄을 두지 않는다(설계 규칙 UI-NTF-01, 화면 탭 줄 JS 와 같은
    길)."""
    assert "center.raise(note)" in _JS and "__capaAlertQueue" in _JS
    assert "raiseAlert(data.alert)" in _JS
    assert "textContent" not in _JS and "hidden = false" not in _JS
    assert voc_draft_keeper._HTML == "<span hidden></span>"


def test_the_voc_page_hands_the_form_keys_and_generation_to_the_keeper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VOC 화면은 폼 두 칸의 선택자와 지금 폼 세대, 세션 표지를 넘긴다. 세션 표지는 회차를 건너
    같고, 글을 올리면 세대가 올라 브라우저가 초안을 버린다."""
    sent: list[dict[str, Any]] = []

    def record(**kwargs: Any) -> None:
        sent.append(kwargs["data"])

    monkeypatch.setattr(voc_draft_keeper, "_DRAFT_KEEPER", record)
    app = AppTest.from_string(_script(tmp_path / "voc.duckdb"), default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]

    first = sent[-1]
    assert first["storageKey"] == DRAFT_STORAGE_KEY
    # 되살림 알림은 등록부의 사건 코드다 — 짧은 글 · 전문(보관 범위)을 싣는다.
    alert = first["alert"]
    assert alert["code"] == "VO-02" and alert["level"] == "info", alert
    assert alerts.spec(alert["code"]).kind == "event"
    assert "되살렸습니다" in alert["short"] and "탭을 닫으면 사라집니다" in alert["full"], alert
    assert first["titleSelector"] == ".st-key-voc_post_title input"
    assert first["bodySelector"] == ".st-key-voc_post_body textarea"
    assert first["generation"] == 0
    token = first["session"]
    assert isinstance(token, str) and token

    app.text_input(key="voc_author").input("홍길동")
    app.text_input(key="voc_post_title").input("제목")
    app.text_area(key="voc_post_body").input("내용")
    next(item for item in app.button if item.label == "글 올리기").click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert "글을 올렸습니다." in [message.value for message in successes(app)]

    assert sent[-1]["session"] == token
    assert sent[-1]["generation"] == 1
