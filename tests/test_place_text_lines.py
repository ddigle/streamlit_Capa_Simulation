# Purpose: 빈 결과 · 점검 결론의 평문 한 줄과 숨은 공정의 칸 머리 풍선이 규칙대로 서는지 본다.

"""자리 글 규칙(2026-11-04 설계 규칙 확인 보드 — UI-NTF-01 · UI-TXT-01 · AMB-02 (가)).

- 목록 구획이 빈 결과(「…이 없습니다」)와 점검 화면의 결론은 값이라 자리에 **평문 한 줄**로 둔다.
  초록 성공 상자(`st.success`)는 알림창 몫이라 쓰지 않고, 하는 법 · 길 안내를 붙이지 않는다 —
  Dynamic Capa 요약 · 실적 요약 · 실적 개선과제 · 원천 품질(Static Capa 는
  `test_static_capa_layout.py`).
- 숨은 데이터 안내는 칸 머리 표지 + 풍선이다 — 주요공정 프리셋에서 이 화면에 없는 공정은 칩의
  「· 이 화면에 없음」 이 표지이고 남는 까닭은 「공정」 칸 풍선이다(칸 밑 안내 문장 없음).
  선행 B/O · 선행 입고의 조회기간 밖 저장분은 `test_unchanged_profile_saves.py`, 판정 기준의
  조회기간 밖 월별 기준은 `test_threshold_editor.py` 가 본다.
- HOME 설정 팝업의 값 줄 · 입력 곁 경고에는 설명 꼬리를 두지 않는다(UI-TXT-01 · UI-TXT-02) —
  기본 프리셋은 「**기본 프리셋** · 이름」 값 줄 + 풍선, 확보율 보정의 짝 없는 행 · 0 에서 자른
  행은 건수 · 행만(남는 까닭 · 자르는 까닭은 Guide), Past Data 붙여넣기 칸의 표 설명은 글 칸
  풍선. 비교 시나리오 · 주요 Case 의 값 줄은 `test_comparison_profile_writeback.py` ·
  `test_home_main_cases_picker.py` 가 본다.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from alert_marks import flashed
from streamlit.testing.v1 import AppTest
from test_reference_integrity_page import TEST_SCRIPT as REFERENCE_INTEGRITY_SCRIPT

from capa_simulation.components import performance_actual_screen as screen
from capa_simulation.components.home_preference import (
    ABSENT_KEY_PROCESS_HELP,
    DEFAULT_PRESET_HELP,
    DEFAULT_PRESET_LABEL,
)
from capa_simulation.components.past_data_management import PAST_TABLE_SPECS
from capa_simulation.persistence.cache import (
    clear_global_key_process_cache,
    clear_scenario_repository,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.dynamic_capacity import (
    aggregate_dynamic_capacity,
    build_dynamic_capacity_demo,
)
from capa_simulation.services.performance_actuals import build_priority_table

ROOT = Path(__file__).resolve().parents[1]
# 빈 결과 · 점검 결론을 그리던 초록 상자 자리(V-15 — 이 갈래 몫).
PLAIN_LINE_FILES = (
    "app_pages/static_capa.py",
    "app_pages/reference_integrity.py",
    "src/capa_simulation/components/performance_actual_screen.py",
    "src/capa_simulation/components/source_quality.py",
)


def _success_calls(path: Path) -> list[int]:
    """`st.success(` · 칸`.success(` 호출 줄."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "success"
    ]


@pytest.mark.parametrize("relative", PLAIN_LINE_FILES)
def test_empty_results_and_verdicts_draw_no_success_box(relative: str) -> None:
    assert _success_calls(ROOT / relative) == []


def _lines(element_list: Any) -> list[str]:
    return [str(element.value) for element in element_list]


# ---------------------------------------------------------------------- Dynamic Capa 요약


def test_the_dynamic_capa_summary_says_no_process_in_one_plain_line() -> None:
    """개선 필요 공정이 없으면 요약 결론은 평문 한 줄이다(경고 · 성공 상자 없음)."""
    demo = build_dynamic_capacity_demo()
    summary = aggregate_dynamic_capacity(demo, ["공정"]).sort_values(
        ["Capa 실현률", "공정"], kind="stable"
    )
    summary["상태"] = "정상"
    app = AppTest.from_string(REFERENCE_INTEGRITY_SCRIPT, default_timeout=60)
    app.session_state["dynamic_capacity_demo_memo"] = (demo, summary)
    app.run()
    assert not app.exception, [item.message for item in app.exception]

    summary_tab = next(tab for tab in app.tabs if tab.label == "요약")
    assert not summary_tab.get("success") and not summary_tab.get("warning")
    lines = _lines(summary_tab.get("caption"))
    assert "Capa 실현률이 판정 기준을 밑도는 공정이 없습니다." in lines, lines


# ------------------------------------------------------------------------- 실적 요약 · 과제


def _performance_app() -> None:
    from capa_simulation.components.performance_actual_screen import (
        render_performance_actual_screen,
    )
    from capa_simulation.components.process_labels import ProcessLabels
    from capa_simulation.services.performance_actuals import EFFICIENCY_METRIC

    render_performance_actual_screen(
        EFFICIENCY_METRIC, key_prefix="plain_line", process_labels=ProcessLabels()
    )


@pytest.mark.parametrize(
    ("tab", "line"),
    [
        ("요약", "효율 기준을 석 달 넘게 못 맞춘 공정이 없습니다."),
        ("개선과제", "지금 기준으로는 개선과제가 필요한 공정이 없습니다."),
    ],
)
def test_the_performance_screen_says_no_process_in_one_plain_line(
    monkeypatch: pytest.MonkeyPatch, tab: str, line: str
) -> None:
    """모든 공정이 정상이면 요약 결론과 개선과제 구획은 평문 한 줄이다."""

    def all_normal(*args: Any, **kwargs: Any) -> pd.DataFrame:
        priority = build_priority_table(*args, **kwargs)
        priority["상태"] = "정상"
        return priority

    monkeypatch.setattr(screen, "build_priority_table", all_normal)
    app = AppTest.from_function(_performance_app, default_timeout=60)
    app.session_state["plain_line_active_tab"] = tab
    app.run()
    assert not app.exception, [item.message for item in app.exception]

    opened = next(item for item in app.tabs if item.label == tab)
    assert not opened.get("success") and not opened.get("warning")
    assert line in _lines(opened.get("caption"))
    # 과제가 붙는 규칙(설명)은 구획 제목 풍선이다 — 빈 결과 줄과 같은 회색 평문으로 붙지 않는다.
    assert not [text for text in _lines(opened.get("caption")) if "과제가 붙습니다" in text]


# ------------------------------------------------------------------------------ 원천 품질


def _source_quality_app() -> None:
    import pandas as pd

    from capa_simulation.components.source_quality import render_source_quality

    profile = pd.DataFrame(
        {
            "ordinal_position": [1, 2],
            "column_name": ["가", "나"],
            "source_dtype": ["object", "object"],
            "nullable_dtype": ["string", "string"],
            "null_count": [0, 0],
            "unique_count": [3, 4],
        }
    )
    render_source_quality(profile, 10)


def test_the_source_quality_verdict_is_one_plain_line() -> None:
    """모든 컬럼이 정상이면 점검 결론은 평문 한 줄이다(초록 상자 없음)."""
    app = AppTest.from_function(_source_quality_app, default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]

    assert not app.success and not app.warning
    assert "2개 컬럼 모두 값이 차 있고 상수 컬럼이 없습니다." in _lines(app.caption)
    # 등급 기준은 「등급」 칸 풍선이고 표 밑에는 기준 행 수 값 줄만 선다(설명 문장 없음 —
    # UI-TXT-01).
    assert "**기준 행 수** · 원천 10행" in _lines(app.caption)
    assert not [
        text for text in _lines(app.caption) if "색만으로" in text or "`상수` 입니다" in text
    ]
    grade = json.loads(app.dataframe[0].proto.columns)["등급"]
    assert "`비어 있음`" in grade["help"] and "`상수`" in grade["help"], grade


# ---------------------------------------------------------------- 주요공정 프리셋 숨은 공정


def _key_process_script(database: Path) -> str:
    return f"""
from capa_simulation.components.home_preference import _render_key_process_editor
from capa_simulation.components.process_labels import ProcessLabels

_render_key_process_editor(
    process_options=["DEMO-A", "DEMO-B"],
    process_labels=ProcessLabels(),
    database_path={str(database)!r},
)
"""


@pytest.fixture
def key_process_database(tmp_path: Path) -> Path:
    path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    repository.replace_global_key_process_presets(
        [("다른 라인 포함", ["DEMO-A", "ELSEWHERE"]), ("이 화면", ["DEMO-B"])], source="시험"
    )
    clear_scenario_repository()
    clear_global_key_process_cache()
    return path


def test_a_preset_process_absent_here_is_a_chip_marker_with_a_field_tooltip(
    key_process_database: Path,
) -> None:
    """이 화면에 없는 공정은 칩의 「· 이 화면에 없음」 과 「공정」 칸 풍선으로만 말한다 — 칸 밑에
    이름을 늘어놓던 안내 문장(「이번 시나리오·조회기간에 없어 그리지 않는 공정: …」)은 없다. 그런
    공정이 없는 프리셋에는 풍선도 없다."""
    app = AppTest.from_string(_key_process_script(key_process_database), default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]

    (field,) = app.multiselect
    assert field.label == "공정"
    assert field.help == ABSENT_KEY_PROCESS_HELP
    assert "ELSEWHERE · 이 화면에 없음" in field.options
    assert not [text for text in _lines(app.caption) if "그리지 않는" in text]

    app.selectbox(key="home_key_process_preset_edit").set_value("이 화면").run()
    assert not app.exception, [item.message for item in app.exception]
    (field,) = app.multiselect
    assert not field.help
    assert not [option for option in field.options if "이 화면에 없음" in option]


def test_the_default_preset_is_a_value_line_with_its_meaning_in_a_tooltip(
    key_process_database: Path,
) -> None:
    """「고칠 프리셋」 밑 기본 프리셋은 「**기본 프리셋** · 「이름」」 값 줄이다 — 「기본」 의
    뜻(새로 연 HOME 이 처음 보는 것)은 풍선이고 줄에 괄호 설명을 붙이지 않는다."""
    app = AppTest.from_string(_key_process_script(key_process_database), default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]

    head = f"**{DEFAULT_PRESET_LABEL}**"
    lines = [item for item in app.caption if str(item.value).startswith(head)]
    assert [str(item.value) for item in lines] == [f"{head} · 「다른 라인 포함」"]
    assert lines[0].help == DEFAULT_PRESET_HELP
    assert "처음 보는" in DEFAULT_PRESET_HELP
    assert not [text for text in _lines(app.caption) if "처음 보는" in text]


# ------------------------------------------------------------ HOME 설정 확보율 보정 경고


def _execution_notices() -> None:
    import pandas as pd

    from capa_simulation.components.home_preference import _render_execution_notices
    from capa_simulation.components.process_labels import ProcessLabels

    _render_execution_notices(
        pd.DataFrame({"생산계획년월": [202703], "공정": ["HBOND"]}),
        pd.DataFrame({"생산계획년월": [202702, 202705], "공정": ["DEMO-A", "DEMO-B"]}),
        ProcessLabels(),
    )


def test_the_execution_notices_name_rows_and_the_guide_says_why() -> None:
    """확보율 보정의 짝 없는 행 · 0 에서 자른 행 경고는 팝업 안 입력 곁 자리 글이고(2026-11-03
    결정) 건수 · 행만 적는다 — 저장이 남아 다른 시나리오에서 쓰인다는 것과 0 에서 자르는 까닭은
    Guide 가 말한다."""
    app = AppTest.from_function(_execution_notices, default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]

    assert _lines(app.warning) == [
        "이번 시나리오·조회기간에 짝이 없어 반영되지 않은 행 1건: 27.03·HBOND",
        "조정 결과가 0% 아래로 내려가 0 에서 자른 행 2건",
    ]
    guide = (ROOT / "src/capa_simulation/guides/home.md").read_text(encoding="utf-8")
    assert "그 공정이 있는 시나리오에서는 그대로 적용됩니다" in guide
    assert "0 에서 자르고" in guide


# ---------------------------------------------------------- HOME 설정 Past Data 붙여넣기 칸


def _past_paste_form() -> None:
    import pandas as pd

    from capa_simulation.components.past_data_management import (
        PAST_TABLE_SPECS,
        _render_paste_form,
    )

    spec = PAST_TABLE_SPECS[0]
    _render_paste_form(":memory:", 0, spec, pd.DataFrame(columns=list(spec.columns)), {})


def test_the_past_data_paste_box_says_its_table_rules_by_alert() -> None:
    """붙여넣기 칸에는 글 · 칸 풍선이 없고, 되돌릴 수 없는 덮어쓰기와 그 표에 넣을 것(단위 · 받지
    않는 글자)은 칸을 편 회차의 알림이다(UI-NTF-09, 2026-11-05 검수 static-37)."""
    app = AppTest.from_function(_past_paste_form, default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]

    spec = PAST_TABLE_SPECS[0]
    (area,) = app.text_area
    assert not area.help
    assert not _lines(app.caption)
    (opening,) = flashed(app, "warning")
    assert "통째로 바뀝니다" in opening.value and spec.caption in opening.value
