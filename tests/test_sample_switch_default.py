# Purpose: 「샘플 데이터」 처음 값 — 운영 서버는 끔 · 그 밖은 켜짐 · 켜고 끈 값은 화면을 건너 남음.

"""「샘플 데이터」 스위치의 처음 값(2026-11-24 정식판 마감 2-A — 사용자가 고른 정식판 마감 2번
권장안 A 「샘플은 기본 끔」).

운영 서버(`SsoConfig.operational`)에서는 처음 값이 끔이고, 개발 PC · 사내 WebIDE · 사내 PC ·
시험은 켜짐 그대로다. 판정은 `sample_data.sample_default` 하나이고 내장 시드 막이
(`scenario_activation.builtin_seed_allowed`)와 같은 뿌리다 — 등급을 보지 않아 개발자도 처음엔
끔이다. 운영 서버 시험은 「운영 + 통합인증 켜짐」 판정(`grade_support.operational_grades`)을
거친다. 그리는 길 둘(구현 중 화면의 사이드바 패널 줄 `render_sample_row` · 설비 화면의 본문 상자
`render_sample_switch`)과 스위치를 그리기 전에 처음 값을 읽는 자리 둘(머리 띠 「합성 샘플」 표지 ·
탭 「구현중」 풍선)을 다 본다. 값은 모두 합성(`demo.*`)이다. 설계 규칙: UI-LAY-10 · UI-LAY-05 ·
UI-STA-03 · UI-NTF-05.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from grade_support import as_grade, unrestricted
from streamlit.testing.v1 import AppTest

from capa_simulation.auth import grades, runtime
from capa_simulation.components import alert_center, page_tabs
from capa_simulation.components.sample_data import (
    NO_UNITS_MARK,
    SAMPLE_TOGGLE_KEY,
    sample_default,
)
from capa_simulation.navigation import (
    AVAILABLE_EQUIPMENT_STATUS,
    DYNAMIC_CAPA,
    EQUIPMENT_MAIN_TAB,
    EQUIPMENT_SUMMARY_TAB,
    EQUIPMENT_SUMMARY_TAB_KEY,
    EQUIPMENT_TAB_KEY,
    WIP_STATUS,
)
from capa_simulation.scenario_activation import builtin_seed_allowed

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def real_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[], AppTest]:
    """빈 DuckDB 를 보는 실제 `app.py` — 브라우저로 보내는 컴포넌트만 바꿔 끼운다
    (`tests/test_grade_ui_core.py` 와 같은 꼴)."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.components.month_range_picker as month_range_picker
    import capa_simulation.settings as settings

    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    monkeypatch.setattr(
        month_range_picker, "_MONTH_RANGE_APPLY", lambda **kwargs: SimpleNamespace(apply=None)
    )
    return lambda: AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)


def _open(app: AppTest, path: str) -> AppTest:
    app.switch_page(path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    return app


def _open_equipment_main(app: AppTest) -> AppTest:
    """가용설비 현황 Summary › Main — 설비 마스터가 비면 본문 스위치 상자가 서는 탭."""
    app.switch_page(AVAILABLE_EQUIPMENT_STATUS.path)
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_SUMMARY_TAB
    app.session_state[EQUIPMENT_SUMMARY_TAB_KEY] = EQUIPMENT_MAIN_TAB
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    return app


def _switch(app: AppTest) -> bool:
    """이 회차에 그린 「샘플 데이터」 위젯의 값(세션 값이 아니라 위젯 — 브라우저에 그린 값)."""
    (toggle,) = [element for element in app.toggle if element.key == SAMPLE_TOGGLE_KEY]
    return bool(toggle.value)


def _pending_marks(app: AppTest) -> list[str]:
    """연결 전 점선 자리의 표지(「… 연결 대기」)."""
    return [
        str(element.proto.body)
        for element in app.main.get("html")
        if "pending-source-slot" in str(element.proto.body)
    ]


def _no_units_marks(app: AppTest) -> list[str]:
    captions = (*app.sidebar.caption, *app.main.caption)
    return [str(item.value) for item in captions if str(item.value) == NO_UNITS_MARK]


def _recording(monkeypatch: pytest.MonkeyPatch, module: ModuleType, name: str) -> list[Any]:
    """`module.name` 이 돌려준 data 를 부를 때마다 적는다 — 그리는 컴포넌트는 그대로다
    (`tests/test_grade_ui_core.py` 의 알림 칸 기록과 같은 꼴)."""
    sent: list[Any] = []
    real = getattr(module, name)

    def recording(*args: Any, **kwargs: Any) -> Any:
        data = real(*args, **kwargs)
        sent.append(data)
        return data

    monkeypatch.setattr(module, name, recording)
    return sent


def _first_open_marks(
    real_app: Callable[[], AppTest], monkeypatch: pytest.MonkeyPatch
) -> tuple[list[bool], list[str]]:
    """HOME 에서 Dynamic Capa 를 처음 연 회차의 머리 띠 「합성 샘플」 표지(`sample`)와 그 탭의
    「구현중」 풍선 — 둘 다 페이지가 스위치를 그리기 **전에** `sample_switch_on` 을 읽는다. 아직
    스위치를 그리지 않은 세션이라 처음 값이 그대로 드러난다(그 뒤 회차는 스위치가 적은 세션 값을
    읽는다)."""
    sent = _recording(monkeypatch, alert_center, "alert_center_data")
    tabs = _recording(monkeypatch, page_tabs, "tabs_data")
    app = real_app().run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert SAMPLE_TOGGLE_KEY not in app.session_state
    sent.clear()
    tabs.clear()
    _open(app, DYNAMIC_CAPA.path)
    marks = [bool(data["sample"]) for data in sent]
    titles = [
        str(tab["wip"]) for data in tabs for tab in data["tabs"] if tab["id"] == DYNAMIC_CAPA.path
    ]
    assert marks and titles, (marks, titles)
    return marks, titles


def _wip_title(*, sample: bool) -> str:
    source = page_tabs.WIP_SOURCE.format(source=DYNAMIC_CAPA.pending_source)
    return page_tabs.WIP_TITLE + source + (page_tabs.WIP_SAMPLE if sample else "")


def test_the_operational_server_starts_with_the_sample_off(
    real_app: Callable[[], AppTest], monkeypatch: pytest.MonkeyPatch
) -> None:
    """운영 서버(통합인증 켜짐)의 새 세션은 「샘플 데이터」 가 꺼진 채 선다 — 개발자가 처음 연
    구현 중 화면의 사이드바 패널 줄은 끔이고 본문은 「… 연결 대기」 점선 자리다. 스위치를 그리기
    전에 처음 값을 읽는 머리 띠 「합성 샘플」 표지와 탭 「구현중」 풍선 꼬리도 그 첫 회차부터 서지
    않는다(UI-LAY-05). 설비 마스터가 빈 가용설비 현황의 본문 스위치도 실무자에게 끔이고 「조회할
    호기 없음」 이 선다. 처음 값은 내장 시드 막이와 같은 판정이다(UI-LAY-10 — 빈 자리를 먼저
    세움)."""
    as_grade(monkeypatch, grades.DEVELOPER)
    assert runtime.config().operational
    assert sample_default() is False
    assert sample_default() is builtin_seed_allowed()

    marks, titles = _first_open_marks(real_app, monkeypatch)
    assert marks == [False] * len(marks), "처음 연 회차에 머리 띠 「합성 샘플」 표지가 섰다"
    assert titles == [_wip_title(sample=False)] * len(titles)

    app = _open(real_app().run(), DYNAMIC_CAPA.path)
    assert SAMPLE_TOGGLE_KEY in [toggle.key for toggle in app.sidebar.toggle]
    assert _switch(app) is False
    assert app.session_state[SAMPLE_TOGGLE_KEY] is False
    assert _pending_marks(app), "샘플을 끈 구현 중 화면은 연결 전 점선 자리다"

    as_grade(monkeypatch, grades.EDITOR)
    app = _open_equipment_main(real_app().run())
    assert _switch(app) is False
    assert _no_units_marks(app), "샘플을 끈 빈 설비 화면은 「조회할 호기 없음」 이다"


def test_off_the_operational_server_the_sample_starts_on(
    real_app: Callable[[], AppTest], monkeypatch: pytest.MonkeyPatch
) -> None:
    """운영 아님(개발 `app.py` · 사내 WebIDE · 사내 PC · 시험)은 지금처럼 켜짐으로 선다 — 처음 연
    회차부터 머리 띠 「합성 샘플」 표지 · 탭 풍선 꼬리가 서고, 같은 두 화면이 켜짐이고 연결 전
    자리 · 「조회할 호기 없음」 이 없다."""
    unrestricted(monkeypatch)
    assert sample_default() is True
    assert sample_default() is builtin_seed_allowed()

    marks, titles = _first_open_marks(real_app, monkeypatch)
    assert marks == [True] * len(marks)
    assert titles == [_wip_title(sample=True)] * len(titles)

    app = _open(real_app().run(), DYNAMIC_CAPA.path)
    assert _switch(app) is True
    assert not _pending_marks(app)

    app = _open_equipment_main(real_app().run())
    assert _switch(app) is True
    assert not _no_units_marks(app)


def test_a_turned_switch_keeps_its_value_across_screens_on_the_operational_server(
    real_app: Callable[[], AppTest], monkeypatch: pytest.MonkeyPatch
) -> None:
    """운영 서버에서도 한 번 켜면 그 세션 동안 켜짐이다 — 재공 현황에서 켠 값이 Dynamic Capa 의
    패널 줄과 가용설비 현황의 본문 스위치로 넘어가고, 다시 끈 값도 넘어간다(같은 공유 키 —
    UI-STA-03). 처음 값은 아직 스위치를 그리지 않은 세션에만 걸린다."""
    as_grade(monkeypatch, grades.DEVELOPER)
    app = _open(real_app().run(), WIP_STATUS.path)
    assert _switch(app) is False

    app.toggle(key=SAMPLE_TOGGLE_KEY).set_value(True).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _switch(app) is True
    assert _switch(_open(app, DYNAMIC_CAPA.path)) is True
    assert _switch(_open_equipment_main(app)) is True

    app.toggle(key=SAMPLE_TOGGLE_KEY).set_value(False).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _switch(_open(app, WIP_STATUS.path)) is False
    assert _pending_marks(app)


def test_every_default_reads_one_function() -> None:
    """처음 값을 박아 둔 자리가 남지 않는다 — 화면 코드는 세션 값을 직접 읽지 않고
    `sample_switch_on` 을, 두 스위치는 `sample_default` 를 부른다(새 자리가 켜짐을 다시 박지
    않게)."""
    sources = [
        ROOT / "app.py",
        *sorted((ROOT / "app_pages").glob("*.py")),
        *sorted((ROOT / "src" / "capa_simulation").rglob("*.py")),
    ]
    planted = re.compile(r"SAMPLE_TOGGLE_KEY,\s*True|default=True,\s*owner")
    found = [
        path.relative_to(ROOT).as_posix()
        for path in sources
        if planted.search(path.read_text(encoding="utf-8"))
    ]
    assert found == []
    owner = ROOT / "src" / "capa_simulation" / "components" / "sample_data.py"
    text = owner.read_text(encoding="utf-8")
    assert text.count("default=sample_default(), owner=key") == 2
    assert "return not sso_runtime.config().operational" in text
    direct = [
        path.relative_to(ROOT).as_posix()
        for path in sources
        if path != owner
        and "session_state.get(SAMPLE_TOGGLE_KEY" in path.read_text(encoding="utf-8")
    ]
    assert direct == []
