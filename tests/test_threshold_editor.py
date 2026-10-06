# Purpose: HOME Preference 판정 기준 편집기의 저장·월별 예외·거부 흐름을 고정한다.

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components.home_preference import (
    THRESHOLD_BASE_VERSION_KEY,
    THRESHOLD_EDITOR_KEY,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.securement_threshold import empty_securement_threshold_rows

MONTHS = (202601, 202602, 202603)
SAVE_LABEL = "판정 기준 저장"


def _script(database: Path, months: tuple[int, ...] = MONTHS) -> str:
    return f"""
from capa_simulation.components.home_preference import render_threshold_editor
from capa_simulation.persistence.cache import load_global_securement_threshold
from capa_simulation.services.month_columns import month_label

database = {str(database)!r}
months = list({months!r})
render_threshold_editor(
    months=months,
    month_labels=[month_label(month) for month in months],
    threshold_profile=load_global_securement_threshold(database),
    database_path=database,
)
"""


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "scenario.duckdb"
    DuckDBScenarioRepository(path).initialize()
    return path


def _app(database: Path, months: tuple[int, ...] = MONTHS) -> AppTest:
    from capa_simulation.persistence.cache import clear_scenario_repository

    # 캐시는 프로세스 공용이다. 앞 테스트의 DB 경로가 같은 이름일 수 있어 비우고 시작한다.
    clear_scenario_repository()
    app = AppTest.from_string(_script(database, months), default_timeout=60).run()
    assert not list(app.exception), [element.message for element in app.exception]
    return app


def _save(app: AppTest) -> AppTest:
    next(button for button in app.button if button.label == SAVE_LABEL).click()
    return app.run()


def _edit(app: AppTest, edited_rows: dict[int, dict[str, float | None]]) -> None:
    app.session_state[THRESHOLD_EDITOR_KEY] = {
        "edited_rows": edited_rows,
        "added_rows": [],
        "deleted_rows": [],
    }


def test_an_unsaved_profile_shows_the_default_it_falls_back_to(database: Path) -> None:
    app = _app(database)

    assert [(widget.label, widget.value) for widget in app.number_input] == [
        ("기본 확보 기준(%)", 109.5),
        ("기본 경고 기준(%)", 99.5),
    ]
    assert any("코드 기본값" in caption.value for caption in app.caption)
    assert app.session_state[THRESHOLD_BASE_VERSION_KEY] == 0


def test_saving_writes_the_defaults_and_only_the_months_that_were_filled(database: Path) -> None:
    app = _app(database)
    app.number_input[0].set_value(110.5)
    _edit(app, {0: {"26.02": 119.5}})
    app = _save(app)

    assert not list(app.exception), [element.message for element in app.exception]
    assert not list(app.error), [element.value for element in app.error]
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert profile.version == 1
    assert profile.default_secure == pytest.approx(1.105)
    assert profile.default_warning == pytest.approx(0.995)
    assert profile.rows["생산계획년월"].tolist() == [202602]
    assert profile.thresholds.for_month(202602) == pytest.approx((1.195, 0.995))
    assert profile.thresholds.for_month(202601) == pytest.approx((1.105, 0.995))
    # 저장 뒤 화면은 새 저장본을 그리고 플래시를 띄운다.
    assert any("저장했습니다" in element.value for element in app.success)
    assert app.session_state[THRESHOLD_BASE_VERSION_KEY] == 1


def test_a_reversed_month_is_rejected_with_its_name(database: Path) -> None:
    app = _app(database)
    _edit(app, {0: {"26.03": 95.0}})
    app = _save(app)

    assert not list(app.exception)
    assert any("26.03" in element.value for element in app.error)
    assert DuckDBScenarioRepository(database).load_global_securement_threshold().version == 0


def test_a_save_after_another_session_saved_is_rejected(database: Path) -> None:
    app = _app(database)
    # 이 화면이 v0 을 보고 있는 사이 다른 세션이 먼저 저장한다.
    DuckDBScenarioRepository(database).replace_global_securement_threshold(
        1.2, 1.0, empty_securement_threshold_rows(), source="다른 세션", expected_version=0
    )
    from capa_simulation.persistence.cache import clear_global_securement_threshold_cache

    clear_global_securement_threshold_cache()
    app = _save(app)

    assert not list(app.exception)
    assert any("먼저" in element.value for element in app.error)
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert (profile.version, profile.source) == (1, "다른 세션")


def test_months_outside_the_view_survive_a_save(database: Path) -> None:
    DuckDBScenarioRepository(database).replace_global_securement_threshold(
        1.095,
        0.995,
        pd.DataFrame({"생산계획년월": [202612], "확보 기준": [1.3], "경고 기준": [None]}),
        source="12월 예외",
        expected_version=0,
    )
    app = _app(database)
    assert any("조회기간 밖" in caption.value for caption in app.caption)

    _edit(app, {0: {"26.01": 120.0}})
    app = _save(app)

    assert not list(app.error), [element.value for element in app.error]
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert profile.rows["생산계획년월"].tolist() == [202601, 202612]


def test_an_official_preset_with_a_zero_threshold_still_opens_the_editor(tmp_path: Path) -> None:
    from test_securement_threshold import publish_official_preset

    database = tmp_path / "scenario.duckdb"
    publish_official_preset(database, 1.095, 0.0)

    app = _app(database)

    # 쓸 수 없는 레거시 짝 대신 코드 기본값을 그리고, 어디서 왔는지 캡션이 말한다.
    assert [widget.value for widget in app.number_input] == [109.5, 99.5]
    assert any("공식 v1 프리셋 값은 쓸 수 없어" in caption.value for caption in app.caption)


def test_the_editor_renders_a_zero_default_and_rejects_saving_it(database: Path) -> None:
    # 저장본이 무엇이든 칸은 그려져야 고칠 수 있다. 0 은 저장 검증이 거부한다.
    script = f"""
from capa_simulation.components.home_preference import render_threshold_editor
from capa_simulation.persistence.models import GlobalSecurementThreshold
from capa_simulation.services.securement_threshold import empty_securement_threshold_rows

render_threshold_editor(
    months=[202601],
    month_labels=["26.01"],
    threshold_profile=GlobalSecurementThreshold(
        version=0,
        source="",
        updated_at=None,
        default_secure=1.095,
        default_warning=0.0,
        rows=empty_securement_threshold_rows(),
        fallback="시험",
    ),
    database_path={str(database)!r},
)
"""
    app = AppTest.from_string(script, default_timeout=60).run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert [widget.value for widget in app.number_input] == [109.5, 0.0]
    app = _save(app)
    assert not list(app.exception)
    assert any("기본 경고 기준" in element.value for element in app.error)
    assert DuckDBScenarioRepository(database).load_global_securement_threshold().version == 0


def test_a_hidden_month_that_blocks_a_new_default_can_be_cleared(database: Path) -> None:
    DuckDBScenarioRepository(database).replace_global_securement_threshold(
        1.095,
        0.995,
        pd.DataFrame({"생산계획년월": [202612], "확보 기준": [1.0], "경고 기준": [None]}),
        source="12월 예외",
        expected_version=0,
    )
    app = _app(database)
    app.number_input[1].set_value(105.0)
    app = _save(app)

    # 표에 없는 26.12 가 새 기본 경고 105% 와 거꾸로 짝이다. 고칠 길까지 적어 거부한다.
    errors = [element.value for element in app.error]
    assert any("조회기간 밖 달 26.12" in text and "지우기" in text for text in errors), errors
    assert DuckDBScenarioRepository(database).load_global_securement_threshold().version == 1

    next(box for box in app.checkbox if "조회기간 밖 월별 기준" in box.label).check()
    app.number_input[1].set_value(105.0)
    app = _save(app)

    assert not list(app.error), [element.value for element in app.error]
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert profile.version == 2
    assert profile.rows.empty
    assert profile.default_warning == pytest.approx(1.05)
