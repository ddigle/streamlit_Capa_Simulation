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
    이름마다 막는다."""
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
    # 보유하지 않은 공정의 표시명 하나(무시 알림)와, 다른 보유 공정의 원본과 같은 표시명 하나(겹침
    # 경고).
    repository.replace_global_process_rename(
        pd.DataFrame({"공정": ["없는~공정~C", "보유"], "표시명": ["무엇", STAR]}), source="시험"
    )

    app = _ok(
        AppTest.from_function(
            _rename_screen, args=(str(path), ["보유", STAR]), default_timeout=30
        ).run()
    )

    infos = _texts(app, "info")
    warnings = _texts(app, "warning")
    assert any(literal_markdown("없는~공정~C") in text for text in infos), infos
    assert any(literal_markdown(STAR) in text for text in warnings), warnings
    assert not [text for text in [*infos, *warnings] if "없는~공정~C" in text or STAR in text]


def _unmatched_screen() -> None:
    from capa_simulation.components.availability_gap_panel import _render_unmatched
    from capa_simulation.components.process_labels import ProcessLabels

    _render_unmatched(["공정~가~A"], ["모델*별*B"], ProcessLabels())


def test_the_unmatched_process_warning_blocks_the_raw_names() -> None:
    app = _ok(AppTest.from_function(_unmatched_screen).run())

    warnings = _texts(app, "warning")
    assert any(
        literal_markdown(TILDE) in text and literal_markdown(STAR) in text for text in warnings
    ), warnings


def _key_process_notice(labels: dict[str, str]) -> None:
    from capa_simulation.components.home_preference import _render_key_process_notice
    from capa_simulation.components.process_labels import ProcessLabels

    _render_key_process_notice(["P1", "P2"], ProcessLabels(version=1, labels=labels))


def test_the_absent_key_process_caption_blocks_the_display_names() -> None:
    app = _ok(AppTest.from_function(_key_process_notice, args=({"P1": TILDE, "P2": STAR},)).run())

    captions = _texts(app, "caption")
    assert any(
        f"{literal_markdown(TILDE)}, {literal_markdown(STAR)}" in text for text in captions
    ), captions


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


def test_the_performance_summary_warning_blocks_the_display_name() -> None:
    priority = build_priority_table(build_monthly_actual_demo(), EFFICIENCY_METRIC, ["공정"])
    worst = str(priority.loc[priority["상태"].eq("개선 필요"), "공정"].iloc[0])

    app = _ok(
        AppTest.from_function(_performance_screen, args=({worst: TILDE},), default_timeout=60).run()
    )

    warnings = _texts(app, "warning")
    assert any(text.startswith(f"**{literal_markdown(TILDE)}** — ") for text in warnings), warnings
