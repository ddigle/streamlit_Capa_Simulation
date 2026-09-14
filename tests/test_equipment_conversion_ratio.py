# Purpose: 호기 마스터 환산비 컬럼의 정규화·검증·저장 왕복을 고정한다.

"""환산비 계약.

같은 공정에 생산성이 다른 설비 모델이 섞일 때 **한 대가 몇 대 몫을 하는지**다. 기준
모델이 1.0 이고 더 빠른 모델은 1 보다 크다.

    환산비 1.5 모델 2대 + 환산비 1.0 모델 2대
      → 설비대수 4대, 가용대수 5대

**설비대수와 가용대수를 가르는 값이다.** 설비대수는 세는 것이고 가용대수는 더하는 것이다.
아직 Capa 의 가용대수는 이 값을 보지 않는다 — 지금은 이력을 쌓기 위해 계약에만 넣는다.
그래서 여기서 고정하는 것은 「들어온 값이 온전히 저장되고 돌아오는가」까지다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from test_equipment_availability import _baseline, _downtime, _equipment

from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_contract import (
    CONVERSION_RATIO_COLUMN,
    DEFAULT_CONVERSION_RATIO,
    EQUIPMENT_COLUMNS,
    empty_equipment_master,
)
from capa_simulation.services.equipment_validation import prepare_equipment_master


def test_the_column_sits_at_the_very_end_of_the_contract() -> None:
    """중간에 끼우면 기존 붙여넣기 표의 열이 통째로 한 칸씩 밀린다."""
    assert EQUIPMENT_COLUMNS[-1] == CONVERSION_RATIO_COLUMN
    assert len(EQUIPMENT_COLUMNS) == 31


def test_the_empty_frame_types_it_as_a_number() -> None:
    """문자열로 두면 편집표에 처음 친 값이 글자로 들어온다."""
    assert empty_equipment_master()[CONVERSION_RATIO_COLUMN].dtype == "float64"


def _master(**overrides: object) -> pd.DataFrame:
    frame = _equipment().head(1).copy()
    for column, value in overrides.items():
        frame[column] = value
    return frame


def test_a_blank_becomes_the_baseline_model() -> None:
    """모델이 하나뿐인 공정은 적을 것이 없어 대개 비어 있다.

    이때 0 으로 읽으면 그 설비가 가용대수에서 통째로 사라진다.
    """
    for blank in ("", "   ", None):
        prepared = prepare_equipment_master(_master(환산비=blank))

        assert prepared.loc[0, CONVERSION_RATIO_COLUMN] == DEFAULT_CONVERSION_RATIO


def test_a_number_survives_as_entered() -> None:
    prepared = prepare_equipment_master(_master(환산비="1.5"))

    assert prepared.loc[0, CONVERSION_RATIO_COLUMN] == 1.5


def test_a_ratio_below_one_is_allowed() -> None:
    """기준보다 느린 모델도 있다. 1 이 상한이 아니라 기준점이다."""
    prepared = prepare_equipment_master(_master(환산비=0.8))

    assert prepared.loc[0, CONVERSION_RATIO_COLUMN] == 0.8


@pytest.mark.parametrize("unreadable", ["1,5", "1.5배", "약 2"])
def test_a_value_that_is_not_a_number_is_refused(unreadable: str) -> None:
    """**빈 칸과 함께 1.0 으로 채우면 안 된다.**

    둘 다 숫자 변환에서 NaN 이 되는데, 그렇게 묶으면 오타가 조용히 기준 모델로 내려앉아
    화면에는 아무 말도 없이 그 설비의 몫이 줄어든다.
    """
    with pytest.raises(ValueError, match="숫자로 읽을 수 없습니다"):
        prepare_equipment_master(_master(환산비=unreadable))


@pytest.mark.parametrize("not_positive", [0, 0.0, -1.5])
def test_zero_and_negative_are_refused(not_positive: float) -> None:
    """0 은 「이 설비는 없는 셈」이라는 뜻인데 그것은 비가동 일정이 맡는 일이다.

    음수는 다른 설비의 몫을 깎아 합계를 거짓으로 만든다.
    """
    with pytest.raises(ValueError, match="0보다 큰 숫자"):
        prepare_equipment_master(_master(환산비=not_positive))


def test_the_guidance_rows_without_an_equipment_id_never_trigger_an_error() -> None:
    """CSV 양식의 선택지 안내 행은 호기가 비어 있다. 검증 전에 버려져야 한다."""
    frame = _equipment().head(1).copy()
    blank_row = {column: None for column in EQUIPMENT_COLUMNS}
    frame = pd.concat([frame, pd.DataFrame([blank_row])], ignore_index=True)

    prepared = prepare_equipment_master(frame)

    assert len(prepared) == 1


# --------------------------------------------------------------------- 저장 왕복


def test_the_ratio_round_trips_through_the_equipment_database(tmp_path: Path) -> None:
    repository = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    assert repository.initialize()
    equipment = _equipment()
    equipment[CONVERSION_RATIO_COLUMN] = [1.5, 1.0, 0.8][: len(equipment)]

    saved = repository.save_snapshot(_baseline(), equipment, _downtime())
    reloaded = repository.load_snapshot(saved.revision.revision_id)

    assert (
        reloaded.equipment[CONVERSION_RATIO_COLUMN].tolist()
        == equipment[CONVERSION_RATIO_COLUMN].tolist()
    )


def test_a_revision_saved_before_the_column_existed_reads_as_the_baseline(
    tmp_path: Path,
) -> None:
    """이미 쌓인 리비전에는 이 값이 없다. 전부 기준 모델로 읽혀야 한다.

    `ADD COLUMN ... DEFAULT 1.0` 이 채워 주지만, 프레임에 컬럼이 있고 값이 NaN 이면
    NULL 로 들어가므로 읽는 쪽의 `COALESCE` 가 마지막 방어선이다.
    """
    database_path = tmp_path / "equipment.duckdb"
    repository = DuckDBEquipmentRepository(database_path)
    assert repository.initialize()
    saved = repository.save_snapshot(_baseline(), _equipment(), _downtime())

    import duckdb

    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            "UPDATE equipment_ops.equipment_master_snapshot SET conversion_ratio = NULL"
        )

    reloaded = DuckDBEquipmentRepository(database_path).load_snapshot(saved.revision.revision_id)

    assert (reloaded.equipment[CONVERSION_RATIO_COLUMN] == DEFAULT_CONVERSION_RATIO).all()


def test_the_future_availability_sum_is_not_wired_yet(tmp_path: Path) -> None:
    """**지금은 계산에 들어가지 않는다.**

    가용대수는 여전히 세는 값이다. 이 테스트는 그 사실을 못박아, 나중에 Σ(환산비) 로
    바꾸는 변경이 이 파일을 반드시 지나가게 한다.
    """
    from capa_simulation.services.equipment_availability import (
        build_weekly_equipment_availability,
    )

    equipment = _equipment()
    equipment[CONVERSION_RATIO_COLUMN] = 2.0
    prepared = prepare_equipment_master(equipment)

    weekly = build_weekly_equipment_availability(
        _baseline(),
        prepared,
        _downtime(),
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 16),
    )

    assert CONVERSION_RATIO_COLUMN not in weekly.columns
    assert (weekly["가용대수"] % 1 == 0).all(), "가용대수가 아직 정수여야 한다"
