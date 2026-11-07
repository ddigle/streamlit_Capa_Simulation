# Purpose: 사람이 적은 이름을 낫표 없이 늘어놓는 알림·캡션이 이름의 마크다운 글자를 막는지 검증한다.

"""마크다운 자리의 이름 목록.

「Cut-off 를 적지 않은 공정 3개는 … — A, B, C」 처럼 이름을 낫표 없이 늘어놓는 알림·캡션은
`literal_markdown.quoted` 그물(「{이름}」)에 걸리지 않아, 물결표 둘인 이름(「A~B~C」)의 가운데가
지움선이 되고 `*`·`_` 는 꾸밈이 됐다(E2E r2 #71 — 개선 거리 I11). 이름마다
`literal_names`·`literal_markdown` 으로 막는다 — 화면을 열어 그려진 글을 본다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from alert_marks import active_state
from streamlit.testing.v1 import AppTest

from capa_simulation.components.literal_markdown import literal_markdown, literal_names
from capa_simulation.services.performance_actuals import (
    EFFICIENCY_METRIC,
    build_monthly_actual_demo,
    build_priority_table,
)

TILDE = "공정~가~A"
STAR = "모델*별*B"


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _texts(app: AppTest, kind: str) -> list[str]:
    return [str(item.value) for item in getattr(app, kind)]


def test_literal_names_blocks_each_name_and_keeps_the_separator() -> None:
    assert literal_names([TILDE, STAR]) == r"공정\~가\~A, 모델\*별\*B"
    assert literal_names(iter([TILDE, "C"]), " · ") == r"공정\~가\~A · C"
    assert literal_names([]) == ""


def _cutoff_screen(database_path: str) -> None:
    from pathlib import Path

    from capa_simulation.components.cutoff_management import render_cutoff_management
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

    render_cutoff_management(
        DuckDBEquipmentRepository(Path(database_path)),
        equipment_processes=["공정~가~A", "모델*별*B", "평범"],
    )


def test_the_missing_cutoff_warning_blocks_the_process_names(tmp_path: Path) -> None:
    """물결표만 막으면(옛 `markdown_safe_tildes`) 「모델*별*B」 의 별표 짝이 기울임이 된다 —
    이름마다 막는다(「설정」 팝업 안 경고 — 고칠 표 곁 자리 글)."""
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

    path = tmp_path / "equipment.duckdb"
    DuckDBEquipmentRepository(path).initialize()

    app = _ok(AppTest.from_function(_cutoff_screen, args=(str(path),), default_timeout=30).run())

    warnings = _texts(app, "warning")
    assert any(
        literal_markdown(TILDE) in text and literal_markdown(STAR) in text for text in warnings
    ), warnings
    assert not [text for text in warnings if TILDE in text or STAR in text]


def _rename_screen(database_path: str, available: list[str]) -> None:
    from pathlib import Path

    from capa_simulation.components.process_rename_management import (
        render_process_rename_management,
    )
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    render_process_rename_management(DuckDBScenarioRepository(Path(database_path)), available)


def test_proc_rename_notices_block_the_listed_names(tmp_path: Path) -> None:
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    # 보유하지 않은 공정의 표시명 하나(보유 공정 밖 표지의 풍선)와, 다른 보유 공정의 원본과 같은
    # 표시명 하나(겹침 경고).
    repository.replace_global_process_rename(
        pd.DataFrame({"공정": ["없는~공정~C", "보유"], "표시명": ["무엇", STAR]}), source="시험"
    )

    app = _ok(
        AppTest.from_function(
            _rename_screen, args=(str(path), ["보유", STAR]), default_timeout=30
        ).run()
    )

    # 보유 공정 밖 이름은 표 머리 표지의 풍선(마크다운)에 막아 싣는다.
    helps = [str(item.proto.help) for item in app.caption if "보유 공정 밖" in str(item.value)]
    assert any(literal_markdown("없는~공정~C") in text for text in helps), helps
    assert not [text for text in helps if "없는~공정~C" in text]
    # 겹침은 상태 알림(`AD-06`, 평문 — 이름 그대로)이다.
    assert not _texts(app, "warning")
    note = active_state(app, "AD-06")
    assert note is not None and STAR in note["full"], note


def _unmatched_screen() -> None:
    from capa_simulation.components.availability_gap_panel import _report_unmatched
    from capa_simulation.components.process_labels import ProcessLabels

    _report_unmatched(["공정~가~A"], ["모델*별*B"], ProcessLabels(), None)


def test_the_unmatched_process_alert_keeps_the_raw_names_verbatim() -> None:
    """한쪽에만 있는 공정은 상태 알림(`EQ-06`, 평문)이다 — 이름을 막지 않고 글자 그대로 싣는다."""
    app = _ok(AppTest.from_function(_unmatched_screen).run())

    assert not _texts(app, "warning")
    note = active_state(app, "EQ-06")
    assert note is not None and TILDE in note["full"] and STAR in note["full"], note


def _performance_screen(labels: dict[str, str]) -> None:
    from capa_simulation.components.performance_actual_screen import (
        render_performance_actual_screen,
    )
    from capa_simulation.components.process_labels import ProcessLabels
    from capa_simulation.services.performance_actuals import EFFICIENCY_METRIC

    render_performance_actual_screen(
        EFFICIENCY_METRIC,
        key_prefix="name_lists",
        process_labels=ProcessLabels(version=1, labels=labels),
    )


def test_the_performance_summary_conclusion_blocks_the_display_name() -> None:
    priority = build_priority_table(build_monthly_actual_demo(), EFFICIENCY_METRIC, ["공정"])
    worst = str(priority.loc[priority["상태"].eq("개선 필요"), "공정"].iloc[0])

    app = _ok(
        AppTest.from_function(_performance_screen, args=({worst: TILDE},), default_timeout=60).run()
    )

    captions = _texts(app, "caption")
    assert any(text.startswith(f"**{literal_markdown(TILDE)}** — ") for text in captions), captions
