# Purpose: 공용 선행 입고 실적 프로필의 정규화·저장·편집기와 LOB 칸 글자의 계약을 고정한다.

import json
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
import pytest
from streamlit.testing.v1 import AppTest

import capa_simulation.components.home_preference as home_preference
from capa_simulation.components.home_preference import ADVANCE_SHIPMENT_EDITOR_KEY
from capa_simulation.components.monthly_table_base import text_width_units
from capa_simulation.components.plotly_layout import add_fixed_table_row, flush_layout_items
from capa_simulation.design import tokens
from capa_simulation.persistence.migration_runner import load_migrations
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.advance_load import ADVANCE_LOAD_ROW_LABEL
from capa_simulation.services.advance_shipment import (
    ADVANCE_SHIPMENT_ROW_LABEL,
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


def test_the_note_stands_at_the_value_height_on_the_right_edge() -> None:
    """선행 입고 실적은 칸 **오른쪽 끝, 값과 같은 높이**에 12px 로 선다(2026-10-07 사용자 결정).

    「같은 높이」는 줄 상자가 아니라 **글리프 가운데**다. 값과 이 글자는 서체·크기가 달라 줄 상자
    가운데에서 글리프 가운데가 내려앉는 거리가 다르다 — 값의 `yshift` 를 그대로 쓰면 이 글자가
    모형상 2.2px 위로 뜬다. 그래서 각자 제 보정을 빼서 맞춘다. 크기는 줄이지 않는다(값이 길면
    겹친다).
    """
    from capa_simulation.components.home_dimensions import (
        CORNER_NOTE_RIGHT_PADDING_PX,
        NUMERIC_INK_OFFSET_RATIO,
        TEXT_INK_OFFSET_RATIO,
    )

    value_size = 20
    figure = go.Figure()
    add_fixed_table_row(
        figure,
        domain=(0.2, 0.6),
        values=["1,233.46", "12,345.67"],
        fill_color="#FFFFFF",
        font_size=value_size,
        bold=False,
        gaps=["+12.34", ""],
        corner_notes=[("+12.3", "선행 입고 실적 +12.3억Gb"), ("+1234.5", "h")],
    )
    flush_layout_items(figure)
    annotations = list(figure.layout.annotations)
    values = [a for a in annotations if a.font.size == value_size]
    notes = [a for a in annotations if a.xanchor == "right"]
    assert [str(a.text) for a in notes] == ["+12.3", "+1234.5"]

    for index, (value, note) in enumerate(zip(values, notes, strict=True)):
        # 오른쪽 끝 — 칸 오른쪽 경계에서 `CORNER_NOTE_RIGHT_PADDING_PX` 안쪽.
        assert note.x == pytest.approx((index + 1) / 2)
        assert note.xshift == -CORNER_NOTE_RIGHT_PADDING_PX
        # 같은 높이 — 두 글리프 가운데가 같은 y 다(같은 기준 y·같은 세로 기준점).
        assert note.y == value.y
        assert note.yanchor == value.yanchor == "middle"
        value_ink_centre = value.yshift - value_size * TEXT_INK_OFFSET_RATIO
        note_ink_centre = note.yshift - tokens.DELTA_FONT_SIZE_PX * NUMERIC_INK_OFFSET_RATIO
        assert note_ink_centre == pytest.approx(value_ink_centre)
        # 크기는 고정이다 — 값이 길어도 줄이지 않는다.
        assert note.font.size == tokens.DELTA_FONT_SIZE_PX
        assert note.font.color == tokens.ADVANCE_SHIPMENT_TEXT
        # 겹치면 위에 서도록 값보다 뒤에 그린다.
        assert annotations.index(note) > annotations.index(value)
    # 같은 칸 값 위 증감(선행 B/O)과는 다른 높이다.
    (delta,) = [a for a in annotations if str(a.text) == "+12.34"]
    assert delta.yshift > notes[0].yshift


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


def test_the_row_name_column_fits_the_longest_name_of_both_editors(database: Path) -> None:
    """`구분` 칸이 두 상자(선행 B/O·선행 입고 실적)의 가장 긴 행 이름을 다 보인다.

    `small`(75px)이면 「선행 입고 실적」이 「선행 입고 실ㅈ」로 잘린다. 두 상자는 같은 폼이라
    같은 폭이고, 달 칸은 폭을 정하지 않아 남는 폭을 나눠 쓴다.
    """
    app = _editor_app(database)
    (editor,) = app.dataframe
    columns = json.loads(editor.proto.columns)

    width = columns["구분"]["width"]
    assert width == home_preference._MONTHLY_AMOUNT_LABEL_WIDTH_PX
    # 표 글자는 14px 이고 한글 한 자가 그만큼이다. 칸 좌우 여백(8px 씩)을 더해도 들어가야 한다.
    for label in (ADVANCE_LOAD_ROW_LABEL, ADVANCE_SHIPMENT_ROW_LABEL):
        assert width >= text_width_units(label) * 14 + 16, label
    assert all("width" not in columns[month] for month in ("26.01", "26.02", "26.03"))
