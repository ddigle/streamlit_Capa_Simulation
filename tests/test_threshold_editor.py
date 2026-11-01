# Purpose: HOME Preference 판정 기준 편집기의 저장·월별 예외·거부 흐름을 고정한다.

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.home_preference import (
    THRESHOLD_BASE_VERSION_KEY,
    THRESHOLD_EDITOR_KEY,
    THRESHOLD_NOTE_KEY,
    THRESHOLD_SAVED_MESSAGE,
    THRESHOLD_UNCHANGED_MESSAGE,
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

    # 판정 기준은 정수 % 다(2026-11-01 사용자 결정) — 칸은 1 단위 정수이고 코드 기본값은 110·100.
    assert [(widget.label, widget.value) for widget in app.number_input] == [
        ("기본 확보 기준(%)", 110),
        ("기본 경고 기준(%)", 100),
    ]
    assert [widget.step for widget in app.number_input] == [1, 1]
    assert any("코드 기본값" in caption.value for caption in app.caption)
    assert app.session_state[THRESHOLD_BASE_VERSION_KEY] == 0


def test_saving_writes_the_defaults_and_only_the_months_that_were_filled(database: Path) -> None:
    app = _app(database)
    app.number_input[0].set_value(111)
    _edit(app, {0: {"26.02": 120.0}})
    app = _save(app)

    assert not list(app.exception), [element.message for element in app.exception]
    assert not list(app.error), [element.value for element in app.error]
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert profile.version == 1
    # 새 저장은 정수 % 의 T/100 이다.
    assert profile.default_secure == pytest.approx(1.11)
    assert profile.default_warning == pytest.approx(1.0)
    assert profile.rows["생산계획년월"].tolist() == [202602]
    assert profile.thresholds.for_month(202602) == pytest.approx((1.2, 1.0))
    assert profile.thresholds.for_month(202601) == pytest.approx((1.11, 1.0))
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
    assert [widget.value for widget in app.number_input] == [110, 100]
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
    assert [widget.value for widget in app.number_input] == [110, 0]
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
    app.number_input[1].set_value(105)
    app = _save(app)

    # 표에 없는 26.12 가 새 기본 경고 105% 와 거꾸로 짝이다. 고칠 길까지 적어 거부한다.
    errors = [element.value for element in app.error]
    assert any("조회기간 밖 달 26.12" in text and "지우기" in text for text in errors), errors
    assert DuckDBScenarioRepository(database).load_global_securement_threshold().version == 1

    next(box for box in app.checkbox if "조회기간 밖 월별 기준" in box.label).check()
    app.number_input[1].set_value(105)
    app = _save(app)

    assert not list(app.error), [element.value for element in app.error]
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert profile.version == 2
    assert profile.rows.empty
    assert profile.default_warning == pytest.approx(1.05)


def test_month_cells_are_float_even_when_no_month_is_filled(database: Path) -> None:
    """두 줄 모두 빈 달도 float64 칸이다 — Arrow null 칸이면 남의 저장으로 첫 값이 들어온 회차에
    키 있는 fixed 편집표의 데이터 서명이 바뀌어 폼 안의 보내지 않은 편집이 사라진다."""
    from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df

    app = _app(database)
    (editor,) = app.get("dataframe")
    drawn = convert_arrow_bytes_to_pandas_df(editor.proto.arrow_data.data)

    assert drawn.loc[:, ["26.01", "26.02", "26.03"]].dtypes.astype(str).tolist() == ["float64"] * 3


def test_month_cells_take_a_decimal_point_and_save_the_rounded_whole_percent(
    database: Path,
) -> None:
    """월별 표 칸은 소수점을 받고 사사오입한 정수 % 로 보인다(2026-11-01 E2E). 칸의 `step` 이 1
    이면 Glide 숫자 편집기가 소수점 키를 버려(소수 자리 0) 「109.5」 를 친 칸이 1095 가 되어 아무
    경고 없이 1095% 로 저장됐다. 저장은 사사오입 정수 % 다(109.5 → 110)."""
    import json

    app = _app(database)
    (editor,) = app.get("dataframe")
    month_columns = {
        name: config["type_config"]
        for name, config in json.loads(editor.proto.columns).items()
        if name in ("26.01", "26.02", "26.03")
    }

    assert len(month_columns) == 3
    for config in month_columns.values():
        # 정수 step 은 편집기의 소수 자리를 0 으로 둔다 — 소수 한 자리를 받는 step 이어야 한다.
        assert not float(config["step"]).is_integer()
        assert config["format"] == "%.0f"

    _edit(app, {0: {"26.02": 109.5}})
    app = _save(app)

    assert not list(app.error), [element.value for element in app.error]
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert profile.rows["확보 기준"].tolist() == pytest.approx([1.1])


def test_a_double_press_of_save_reports_the_save_not_a_conflict(database: Path) -> None:
    """「판정 기준 저장」을 사람 더블클릭 간격으로 두 번 누르면 성공 하나만 알린다(2026-10-26 E2E).

    둘째 누름의 회차가 첫 저장의 rerun 회차를 끊어 편집 시작 version 이 저장 전 그대로 남았고,
    저장소가 그 누름을 거부해 방금 한 제 저장을 「다른 사용자가 먼저 저장」이라 알렸다. AppTest 는
    두 요청을 겹칠 수 없어, 누른 화면의 위젯 값과 끊긴 회차가 남긴 편집 시작 version 을 되살려
    한 번 더 보낸다. 그 뒤 남이 저장했으면 여전히 거부를 알린다.
    """
    app = _app(database)
    app.number_input[0].set_value(110.5)
    next(button for button in app.button if button.label == SAVE_LABEL).click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert DuckDBScenarioRepository(database).load_global_securement_threshold().version == 1

    app.session_state[THRESHOLD_BASE_VERSION_KEY] = 0
    app._run(widget_state=pressed)

    assert not list(app.exception), [element.message for element in app.exception]
    assert not list(app.error), [element.value for element in app.error]
    assert [element.value for element in app.success] == [
        "확보율 판정 기준을 공용 설정으로 저장했습니다."
    ]
    assert DuckDBScenarioRepository(database).load_global_securement_threshold().version == 1

    DuckDBScenarioRepository(database).replace_global_securement_threshold(
        1.3, 1.0, empty_securement_threshold_rows(), source="다른 세션", expected_version=1
    )
    from capa_simulation.persistence.cache import clear_global_securement_threshold_cache

    clear_global_securement_threshold_cache()
    app.session_state[THRESHOLD_BASE_VERSION_KEY] = 0
    app._run(widget_state=pressed)

    assert any("다른 사용자가 먼저" in element.value for element in app.error)
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert (profile.version, profile.source) == (2, "다른 세션")


@pytest.mark.parametrize(("window", "trailing"), [(3600.0, True), (0.0, False)])
def test_a_double_press_after_another_session_saved_keeps_the_refusal(
    database: Path, monkeypatch: pytest.MonkeyPatch, window: float, trailing: bool
) -> None:
    """B 가 먼저 저장한 뒤 A 가 옛 화면에서 「판정 기준 저장」을 빠르게 두 번 누른다
    (2026-10-26 E2E).

    첫 누름은 거부되지만 그 회차가 편집 시작 version 을 최신으로 올려, 둘째 누름이 대조를 지나
    저장했다 — A 가 적은 값은 버려지고(키 없는 칸이 새 기본값으로 섰다) 거부 대신 「저장했습니다」만
    남았다. 거부 직후(`TRAILING_PRESS_SECONDS`)의 둘째 누름은 저장하지 않고 그 거부를 다시 알린다.
    창이 지난 누름은 새 화면을 보고 다시 누른 저장이라 평소대로 대조를 지난다 — 그 화면은 B 의 값을
    그렸고(키 없는 칸) 그대로 누른 것이라 바뀐 것이 없어 새 버전을 만들지 않는다(2026-11-01 개선
    I5). AppTest 의 두 회차 사이 시간이 들쭉날쭉해 창은 시험이 정한다.
    """
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", window)
    app = _app(database)
    DuckDBScenarioRepository(database).replace_global_securement_threshold(
        1.17, 1.0, empty_securement_threshold_rows(), source="다른 세션", expected_version=0
    )
    from capa_simulation.persistence.cache import clear_global_securement_threshold_cache

    clear_global_securement_threshold_cache()
    app.number_input[0].set_value(122.0)
    next(button for button in app.button if button.label == SAVE_LABEL).click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert any("다른 사용자가 먼저" in element.value for element in app.error)

    app._run(widget_state=pressed)

    assert not list(app.exception), [element.message for element in app.exception]
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    if trailing:
        errors = [element.value for element in app.error]
        assert len(errors) == 1 and "다른 사용자가 먼저" in errors[0], errors
        assert not app.success
        assert (profile.version, profile.source) == (1, "다른 세션")
    else:
        assert not list(app.error), [element.value for element in app.error]
        assert [element.value for element in app.info] == [THRESHOLD_UNCHANGED_MESSAGE]
        assert (profile.version, profile.source) == (1, "다른 세션")
    clear_global_securement_threshold_cache()


def test_a_single_press_after_a_held_double_press_saves_from_the_latest_version(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """남의 저장 뒤 옛 화면에서 두 번 누르면 둘 다 거부된다. 그 뒤 최신 화면을 보고 새 값을 적어
    한 번 누른 저장은 저장된다(2026-10-26 E2E).

    둘째 누름의 회차가 거부 뒤 회차(제출 아님 — 본 version 을 적는 자리)를 끊고, 그 둘째 누름은
    거부 표지에 걸려 본 version 을 적지 않고 끝났다. 최신 저장본을 그린 그 회차를 보고 4초 뒤 누른
    저장이 「편집 시작 v0 · 지금 v1」 로 또 거부됐다. 끊긴 회차는 본 version 을 옛 값으로 되살려
    흉내 낸다.
    """
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    app = _app(database)
    DuckDBScenarioRepository(database).replace_global_securement_threshold(
        1.17, 1.0, empty_securement_threshold_rows(), source="다른 세션", expected_version=0
    )
    from capa_simulation.persistence.cache import clear_global_securement_threshold_cache

    clear_global_securement_threshold_cache()
    app.number_input[0].set_value(122.0)
    next(button for button in app.button if button.label == SAVE_LABEL).click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert any("다른 사용자가 먼저" in element.value for element in app.error)

    app.session_state[THRESHOLD_BASE_VERSION_KEY] = 0
    app._run(widget_state=pressed)
    assert any("다른 사용자가 먼저" in element.value for element in app.error)
    assert DuckDBScenarioRepository(database).load_global_securement_threshold().version == 1

    # 거부 표지의 창이 지났다 — 최신 화면을 보고 다시 누른 저장이다.
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    app.number_input[0].set_value(173.0)
    app = _save(app)

    assert not list(app.exception), [element.message for element in app.exception]
    assert not list(app.error), [element.value for element in app.error]
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert profile.version == 2
    assert abs(profile.default_secure - 1.73) < 1e-9
    clear_global_securement_threshold_cache()


def _saved_once(database: Path) -> None:
    """v1 — 비율이 퍼센트 칸을 오가는 값(112%)과 반 칸 낮춘 옛 관례 값(0.995·1.195 — 저장이 정수 %
    100·120 으로 맞춘다), 월별 예외 하나."""
    DuckDBScenarioRepository(database).replace_global_securement_threshold(
        1.12,
        0.995,
        pd.DataFrame({"생산계획년월": [202602], "확보 기준": [1.195], "경고 기준": [None]}),
        source="처음 저장",
        expected_version=0,
    )
    from capa_simulation.persistence.cache import clear_global_securement_threshold_cache

    clear_global_securement_threshold_cache()


def test_a_save_without_changes_makes_no_new_version(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """바꾼 것 없는 「판정 기준 저장」 은 새 버전을 만들지 않고 「바뀐 것이 없습니다」 를
    알린다(2026-11-01 개선 I5 — E2E #41: v2→v3→v4). 칸이 정수 퍼센트를 오가는 것(1.12 → 112 → 112 ÷
    100)은 바뀐 것이 아니다. 변경 메모만 적은 저장도 같고, 값을 고치면 평소대로 저장한다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    _saved_once(database)
    app = _app(database)
    assert app.number_input[0].value == 112

    app = _save(app)
    assert not list(app.exception), [element.message for element in app.exception]
    assert [element.value for element in app.info] == [THRESHOLD_UNCHANGED_MESSAGE]
    assert not app.success and not app.error

    app.text_input(key=THRESHOLD_NOTE_KEY).set_value("메모만 적음")
    app = _save(app)
    assert [element.value for element in app.info] == [THRESHOLD_UNCHANGED_MESSAGE]
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert (profile.version, profile.source) == (1, "처음 저장")

    _edit(app, {0: {"26.03": 121.0}})
    app = _save(app)
    assert not app.info and not app.error, [element.value for element in app.info]
    assert [element.value for element in app.success] == [THRESHOLD_SAVED_MESSAGE]
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert profile.version == 2
    assert profile.rows["생산계획년월"].tolist() == [202602, 202603]


def test_the_first_save_of_an_unsaved_profile_writes_the_values_it_shows(database: Path) -> None:
    """저장본이 없으면(v0 — 보이는 값은 공식버전 프리셋·코드 기본값) 고치지 않은 저장도 그 값을 공용
    기준으로 고정한다 — 바꾼 것 없는 저장 판정(개선 I5)은 저장본이 있을 때만이다."""
    app = _save(_app(database))

    assert not app.info and not app.error, [element.value for element in app.info]
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert profile.version == 1
    # 보이는 값은 정수 % 110·100 이고 저장은 그 T/100 이다(2026-11-01 사용자 결정 N1).
    assert (profile.default_secure, profile.default_warning) == pytest.approx((1.1, 1.0))


def test_a_slow_second_press_of_save_repeats_the_success(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """느린 두 번 누름(둘째 누름이 첫 저장 뒤 새로 그린 칸에 닿는다 — 같은 값이라 바뀐 것이 없다)은
    「바뀐 것이 없습니다」 로 방금 성공을 덮지 않는다(write_guard.held_notice 창 안)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    _saved_once(database)
    app = _app(database)
    app.number_input[0].set_value(115)
    app = _save(app)
    assert DuckDBScenarioRepository(database).load_global_securement_threshold().version == 2

    app = _save(app)

    assert not list(app.exception), [element.message for element in app.exception]
    assert not app.info and not app.error, [element.value for element in app.info]
    assert [element.value for element in app.success] == [THRESHOLD_SAVED_MESSAGE]
    assert DuckDBScenarioRepository(database).load_global_securement_threshold().version == 2


def test_a_save_without_changes_keeps_the_note_on_months_outside_the_view(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「바뀐 것이 없습니다」 회차는 쓰지 않아 다시 돌지 않는다 — 누르지 않은 회차와 같은 화면이게
    조회기간 밖 월별 기준 줄도 그대로 선다(개선 I5)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    DuckDBScenarioRepository(database).replace_global_securement_threshold(
        1.095,
        0.995,
        pd.DataFrame({"생산계획년월": [202612], "확보 기준": [1.3], "경고 기준": [None]}),
        source="12월 예외",
        expected_version=0,
    )
    app = _app(database)
    assert any("조회기간 밖" in caption.value for caption in app.caption)

    app = _save(app)

    assert not list(app.exception), [element.message for element in app.exception]
    assert [element.value for element in app.info] == [THRESHOLD_UNCHANGED_MESSAGE]
    assert any("조회기간 밖" in caption.value for caption in app.caption)
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert (profile.version, profile.source) == (1, "12월 예외")


def test_a_stored_half_step_threshold_opens_as_its_whole_percent_and_saves_as_it(
    database: Path,
) -> None:
    """옛 관례로 반 칸 낮춰 저장한 1.095·0.995·1.195 는 칸에 110·100·120 으로 서고, 다른 칸을 고쳐
    저장하면 손대지 않은 칸도 정수 % 의 T/100 으로 저장된다(2026-11-01 사용자 결정 — 판정은
    그대로다). 아무것도 고치지 않은 저장은 같은 기준이라 쓰지 않는다(2026-11-01 개선 I5)."""
    from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df

    from capa_simulation.persistence import securement_threshold_store
    from capa_simulation.persistence.cache import clear_global_securement_threshold_cache

    # 옛 저장본 그대로 — 저장 검증(이제 T/100 으로 맞춘다)을 거치지 않고 저장소 SQL 로
    # 반 칸 낮춘 값을 쓴다.
    repository = DuckDBScenarioRepository(database)
    with repository._write_transaction() as connection:
        securement_threshold_store.replace_global_securement_threshold(
            connection,
            default_secure=1.095,
            default_warning=0.995,
            prepared_rows=pd.DataFrame(
                {
                    "생산계획년월": pd.Series([202602], dtype="int64"),
                    "확보 기준": pd.Series([1.195], dtype="float64"),
                    "경고 기준": pd.Series([None], dtype="float64"),
                }
            ),
            source="옛 저장",
            expected_version=0,
        )
    stored = repository.load_global_securement_threshold()
    assert (stored.default_secure, stored.default_warning) == (1.095, 0.995)
    assert stored.rows["확보 기준"].tolist() == [1.195]
    clear_global_securement_threshold_cache()
    app = _app(database)

    assert [widget.value for widget in app.number_input] == [110, 100]
    (editor,) = app.get("dataframe")
    drawn = convert_arrow_bytes_to_pandas_df(editor.proto.arrow_data.data)
    assert drawn.loc[0, "26.02"] == 120.0
    assert any("확보 110% · 경고 100%" in caption.value for caption in app.caption)

    app = _save(app)

    assert not list(app.error), [element.value for element in app.error]
    assert [element.value for element in app.info] == [THRESHOLD_UNCHANGED_MESSAGE]
    unchanged = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert (unchanged.version, unchanged.default_secure) == (1, 1.095)

    app.number_input[1].set_value(99)
    app = _save(app)

    assert not list(app.error), [element.value for element in app.error]
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert profile.version == 2
    assert (profile.default_secure, profile.default_warning) == pytest.approx((1.1, 0.99))
    assert profile.rows["확보 기준"].tolist() == pytest.approx([1.2])


def test_the_default_fields_take_a_decimal_point_and_save_the_rounded_whole_percent(
    database: Path,
) -> None:
    """기본 확보 · 경고 칸도 월별 칸처럼 소수를 받아 사사오입한 정수 % 로 읽는다(2026-11-01 사용자
    결정 — 109.5 → 110, 99.5 → 100). 정수 숫자 칸(`%d`)은 브라우저가 친 글을 `parseInt` 로, 서버가
    `int()` 로 읽어 109.5 를 말없이 109 로 버렸다 — 같은 109.5 를 월별 칸은 110 으로 읽었다. 칸은
    소수 칸이고 보이는 꼴은 반을 올리는 `%.0f` 다."""
    from streamlit.proto.NumberInput_pb2 import NumberInput as NumberInputProto

    app = _app(database)
    assert [widget.proto.data_type for widget in app.number_input] == [NumberInputProto.FLOAT] * 2
    assert [widget.proto.format for widget in app.number_input] == ["%.0f", "%.0f"]

    app.number_input[0].set_value(109.5)
    app.number_input[1].set_value(99.5)
    app = _save(app)

    assert not list(app.error), [element.value for element in app.error]
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert profile.version == 1
    assert (profile.default_secure, profile.default_warning) == pytest.approx((1.1, 1.0))

    # 반은 늘 올린다 — 짝수 쪽으로 가르지 않는다(108.5 → 109, 파이썬 `round` 면 108).
    app.number_input[0].set_value(108.5)
    app = _save(app)

    assert not list(app.error), [element.value for element in app.error]
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert profile.version == 2
    assert profile.default_secure == pytest.approx(1.09)


def _threshold_rows_in_db(database: Path) -> tuple[int, int]:
    """(헤더 version, 월별 행 수) — 저장소 SQL 그대로 센다(캐시를 거치지 않는다)."""
    import duckdb

    with duckdb.connect(str(database), read_only=True) as connection:
        header = connection.execute(
            "SELECT version FROM app_meta.global_securement_threshold WHERE profile_id = 1"
        ).fetchone()
        count = connection.execute(
            "SELECT COUNT(*) FROM app_meta.global_securement_threshold_month"
        ).fetchone()
    return (0 if header is None else int(header[0]), 0 if count is None else int(count[0]))


@pytest.mark.parametrize(
    ("field", "value", "named"),
    [
        ("month_secure", 1095.0, "26.02 확보 기준 1095%"),
        ("month_secure", 301.0, "26.02 확보 기준 301%"),
        ("month_warning", 49.0, "26.02 경고 기준 49%"),
        ("default_secure", 1095.0, "기본 확보 기준 1095%"),
        ("default_warning", 49.0, "기본 경고 기준 49%"),
    ],
)
def test_a_threshold_outside_the_range_is_refused_naming_the_cell_and_the_range(
    database: Path, field: str, value: float, named: str
) -> None:
    """판정 기준 값이 50 ~ 300% 밖이면 저장하지 않고 저장 단추 아래에 어느 칸(달 · 항목 · 값)인지와
    받는 범위를 적는다(2026-11-01 사용자 결정 「제약 확보율처럼 50 ~ 300% 밖은 저장을 막음」 — 1095
    같은 오타가 그대로 저장됐다). 저장소의 헤더 version 과 월별 행 수가 그대로다."""
    DuckDBScenarioRepository(database).replace_global_securement_threshold(
        1.1,
        1.0,
        pd.DataFrame({"생산계획년월": [202603], "확보 기준": [1.2], "경고 기준": [None]}),
        source="처음 저장",
        expected_version=0,
    )
    from capa_simulation.persistence.cache import clear_global_securement_threshold_cache

    clear_global_securement_threshold_cache()
    before = _threshold_rows_in_db(database)
    app = _app(database)
    if field == "month_secure":
        _edit(app, {0: {"26.02": value}})
    elif field == "month_warning":
        _edit(app, {1: {"26.02": value}})
    elif field == "default_secure":
        app.number_input[0].set_value(value)
    else:
        app.number_input[1].set_value(value)
    app = _save(app)

    assert not list(app.exception), [element.message for element in app.exception]
    errors = [element.value for element in app.error]
    assert len(errors) == 1, errors
    assert named in errors[0] and "50% \\~ 300%" in errors[0], errors
    assert "저장하지 않았습니다" in errors[0]
    assert not app.success
    assert _threshold_rows_in_db(database) == before == (1, 1)


def test_the_range_ends_are_saved(database: Path) -> None:
    """300 과 50 은 범위 안이다(양 끝 포함). 49.5 는 사사오입한 정수 50 으로 읽어 든다 — 범위도
    저장할 정수 % 로 견준다."""
    app = _app(database)
    _edit(app, {0: {"26.02": 300.0}, 1: {"26.03": 50.0, "26.01": 49.5}})
    app = _save(app)

    assert not list(app.error), [element.value for element in app.error]
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert profile.version == 1
    assert profile.thresholds.for_month(202602) == pytest.approx((3.0, 1.0))
    assert profile.thresholds.for_month(202603) == pytest.approx((1.1, 0.5))
    assert profile.thresholds.for_month(202601) == pytest.approx((1.1, 0.5))


def test_an_out_of_range_month_outside_the_view_points_to_the_clear_box(database: Path) -> None:
    """조회기간 밖 달에 범위 밖 옛 저장본(2026-11-01 E2E 의 1095% 오타)이 남아 있으면 그 달을 적고
    고칠 길(조회기간 넓히기 · 「조회기간 밖 월별 기준 지우기」)까지 적어 거부한다. 지우기를 체크하면
    저장된다. 읽기 · 판정은 막지 않는다 — 옛 저장본은 그대로 그려진다."""
    from capa_simulation.persistence import securement_threshold_store
    from capa_simulation.persistence.cache import clear_global_securement_threshold_cache

    repository = DuckDBScenarioRepository(database)
    with repository._write_transaction() as connection:
        securement_threshold_store.replace_global_securement_threshold(
            connection,
            default_secure=1.1,
            default_warning=1.0,
            prepared_rows=pd.DataFrame(
                {
                    "생산계획년월": pd.Series([202612], dtype="int64"),
                    "확보 기준": pd.Series([10.95], dtype="float64"),
                    "경고 기준": pd.Series([None], dtype="float64"),
                }
            ),
            source="오타 저장",
            expected_version=0,
        )
    clear_global_securement_threshold_cache()
    app = _app(database)
    _edit(app, {0: {"26.02": 120.0}})
    app = _save(app)

    errors = [element.value for element in app.error]
    assert len(errors) == 1, errors
    assert "26.12 확보 기준 1095%" in errors[0]
    assert "조회기간 밖 달 26.12" in errors[0] and "지우기" in errors[0]
    assert _threshold_rows_in_db(database) == (1, 1)

    next(box for box in app.checkbox if "조회기간 밖 월별 기준" in box.label).check()
    _edit(app, {0: {"26.02": 120.0}})
    app = _save(app)

    assert not list(app.error), [element.value for element in app.error]
    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()
    assert profile.version == 2
    assert profile.rows["생산계획년월"].tolist() == [202602]
