# Purpose: 공용 선행 입고 실적 프로필의 정규화·저장·편집기와 LOB 칸 글자의 계약을 고정한다.

from pathlib import Path

import duckdb
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components.home_preference import ADVANCE_SHIPMENT_EDITOR_KEY
from capa_simulation.persistence.migration_runner import load_migrations
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.advance_shipment import (
    advance_shipment_notes,
    empty_advance_shipment,
    merge_advance_shipment_edits,
    prepare_advance_shipment,
)

MONTHS = (202601, 202602, 202603)
SAVE_LABEL = "선행 입고 저장"


def _rows(values: dict[int, float]) -> pd.DataFrame:
    return pd.DataFrame({"생산계획년월": list(values), "선행 입고": list(values.values())})


def test_zero_and_blank_months_are_dropped_and_the_sign_is_kept() -> None:
    prepared = prepare_advance_shipment(
        pd.DataFrame(
            {
                "생산계획년월": [202603, 202601, 202602, 202604],
                "선행 입고": [-1.5, 2.0, 0.0, None],
            }
        )
    )

    assert prepared["생산계획년월"].tolist() == [202601, 202603]
    assert prepared["선행 입고"].tolist() == [2.0, -1.5]


def test_a_bad_month_or_a_repeated_month_is_rejected() -> None:
    with pytest.raises(ValueError, match="YYYYMM"):
        prepare_advance_shipment(_rows({202613: 1.0}))
    with pytest.raises(ValueError, match="두 번"):
        prepare_advance_shipment(
            pd.DataFrame({"생산계획년월": [202601, 202601], "선행 입고": [1.0, 2.0]})
        )


def test_editing_a_narrow_view_keeps_the_months_it_could_not_show() -> None:
    """조회기간을 좁힌 채 저장해도 보이지 않는 달의 입력은 남는다(선행 B/O 와 같은 규칙)."""
    stored = _rows({202512: 1.0, 202605: -2.0})

    merged = merge_advance_shipment_edits(stored, [202601, 202602], [3.0, None])

    assert merged["생산계획년월"].tolist() == [202512, 202601, 202605]
    assert merged["선행 입고"].tolist() == [1.0, 3.0, -2.0]


def test_the_shared_profile_round_trips_and_bumps_its_version(tmp_path: Path) -> None:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()

    unsaved = repository.load_global_advance_shipment()
    assert (unsaved.version, unsaved.updated_at, unsaved.rows.empty) == (0, None, True)

    saved = repository.replace_global_advance_shipment(
        _rows({202601: 1.25, 202603: -0.5}), source="웹 직접 편집"
    )
    assert saved.version == 1
    assert saved.rows["생산계획년월"].tolist() == [202601, 202603]
    assert saved.rows["선행 입고"].tolist() == [1.25, -0.5]

    cleared = repository.replace_global_advance_shipment(
        empty_advance_shipment(), source="전체 해제"
    )
    # 0건 저장도 정상이며 그림 캐시 키가 version 을 보므로 번호는 올라야 한다.
    assert cleared.version == 2
    assert cleared.rows.empty


def test_the_profile_lives_in_its_own_tables_without_owner_columns(tmp_path: Path) -> None:
    """소유 컬럼이 있으면 시나리오 삭제가 이 공용 프로필을 함께 지운다."""
    database = tmp_path / "scenario.duckdb"
    DuckDBScenarioRepository(database).initialize()
    assert any(migration.version == 31 for migration in load_migrations())

    with duckdb.connect(str(database), read_only=True) as connection:
        columns = {
            (str(table), str(column))
            for table, column in connection.execute(
                """
                SELECT table_name, column_name FROM information_schema.columns
                WHERE table_schema = 'app_meta' AND table_name LIKE 'global_advance_shipment%'
                """
            ).fetchall()
        }
    assert {table for table, _ in columns} == {
        "global_advance_shipment",
        "global_advance_shipment_month",
    }
    assert not {column for _, column in columns} & {"scenario_id", "dataset_id", "revision_id"}


def test_notes_follow_the_month_axis_and_skip_totals_and_invisible_zeros() -> None:
    rows = _rows({202512: 1.2, 202601: -0.5, 202602: 0.04, 202603: 1234.5})
    labels = ["25.12", "26.01", "26.02", "26.03", "26년"]

    notes = advance_shipment_notes(rows, labels)

    assert notes == [
        ("+1.2", "선행 입고 실적 +1.2억Gb"),
        ("-0.5", "선행 입고 실적 -0.5억Gb"),
        # 자릿수에서 0 으로 보이는 값은 적지 않는다.
        ("", ""),
        ("+1234.5", "선행 입고 실적 +1234.5억Gb"),
        # 연간 Total 칸에는 합계를 적지 않는다.
        ("", ""),
    ]


def _editor_script(database: Path, months: tuple[int, ...] = MONTHS) -> str:
    return f"""
from capa_simulation.components.home_preference import render_advance_shipment_editor
from capa_simulation.persistence.cache import load_global_advance_shipment
from capa_simulation.services.month_columns import month_label

database = {str(database)!r}
months = list({months!r})
render_advance_shipment_editor(
    months=months,
    month_labels=[month_label(month) for month in months],
    advance_shipment_profile=load_global_advance_shipment(database),
    database_path=database,
)
"""


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "scenario.duckdb"
    DuckDBScenarioRepository(path).initialize()
    return path


def _editor_app(database: Path, months: tuple[int, ...] = MONTHS) -> AppTest:
    from capa_simulation.persistence.cache import clear_scenario_repository

    # 캐시는 프로세스 공용이다. 앞 테스트의 DB 경로가 같은 이름일 수 있어 비우고 시작한다.
    clear_scenario_repository()
    app = AppTest.from_string(_editor_script(database, months), default_timeout=60).run()
    assert not list(app.exception), [element.message for element in app.exception]
    return app


def test_the_editor_saves_the_visible_months_and_shows_them_again(database: Path) -> None:
    DuckDBScenarioRepository(database).replace_global_advance_shipment(
        _rows({202512: 0.7}), source="과거 달"
    )
    app = _editor_app(database)
    # 기간 밖 저장분은 표에 없지만 남는다고 알린다.
    assert any("조회기간 밖" in caption.value for caption in app.caption)

    app.session_state[ADVANCE_SHIPMENT_EDITOR_KEY] = {
        "edited_rows": {0: {"26.01": 1.25, "26.03": -2.5}},
        "added_rows": [],
        "deleted_rows": [],
    }
    next(button for button in app.button if button.label == SAVE_LABEL).click()
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert not list(app.error), [element.value for element in app.error]
    profile = DuckDBScenarioRepository(database).load_global_advance_shipment()
    assert profile.version == 2
    assert dict(zip(profile.rows["생산계획년월"], profile.rows["선행 입고"], strict=True)) == {
        202512: 0.7,
        202601: 1.25,
        202603: -2.5,
    }
    assert any("선행 입고 실적을 공용 설정으로 저장했습니다" in item.value for item in app.success)

    # 다시 그리면 저장본이 칸에 돌아온다.
    reloaded = _editor_app(database)
    (editor,) = reloaded.dataframe
    table = editor.value
    assert table.iloc[0]["구분"] == "선행 입고 실적"
    assert table.iloc[0][["26.01", "26.02", "26.03"]].tolist() == [1.25, 0.0, -2.5]
    assert any("v2" in caption.value for caption in reloaded.caption)


def test_the_note_keeps_the_delta_size_until_it_would_touch_the_centred_delta() -> None:
    """칸 오른쪽 위 글자는 12px 에서 시작해 들어가지 않을 때만 줄인다(행 전체가 한 크기).

    칸은 100px, 가운데에 선행 B/O 증감이 선다. 숫자 폭은 Calibri 실측(12px `+12.34` 33.3px)과 같다.
    """
    from capa_simulation.components.home_dimensions import (
        CORNER_NOTE_MIN_FONT_SIZE_PX,
        corner_note_font_size_px,
        numeric_text_width_px,
    )

    assert numeric_text_width_px("+12.34", 12) == pytest.approx(33.3, abs=0.2)
    # 흔한 크기(B/O +12.34 · 입고 +12.3)는 그대로 12px 이다.
    assert (
        corner_note_font_size_px(
            ["+12.3", "", "-12.3"], ["+12.34", "", "-12.34"], cell_width_px=100
        )
        == 12
    )
    # 증감이 없으면 칸 왼쪽까지 쓸 수 있다.
    assert corner_note_font_size_px(["+1,234.5"], None, cell_width_px=100) == 12
    # 한 칸이라도 들어가지 않으면 행 전체를 줄인다.
    assert (
        corner_note_font_size_px(["+12.3", "+123.4"], ["+12.34", "+12.34"], cell_width_px=100) == 9
    )
    # 하한 아래로는 줄이지 않는다.
    assert (
        corner_note_font_size_px(["+12,345.6"], ["+12,345.67"], cell_width_px=100)
        == CORNER_NOTE_MIN_FONT_SIZE_PX
    )
