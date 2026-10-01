# Purpose: 호기 마스터의 Space 위치 계약(레이아웃표시·동·층·좌표·크기 조합)을 경우별로 고정한다.

"""레이아웃표시는 「도면 대상」만 가르고 좌표를 강제하지 않는다(2026-10-01 사용자 결정).

Y 인데 좌표가 없으면 Space 편집기 트레이(미배치)에 뜨고, 크기만 있는 행은 트레이로 뺀 호기의
실제 치수를 지킨다. 지금 저장된 리비전이 다시 읽히는 검사라 **풀기만 하고 조이지 않는다** —
특히 N 행은 예전처럼 동·층 없이 좌표만 있어도 받는다.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from capa_simulation.services.equipment_contract import EQUIPMENT_COLUMNS
from capa_simulation.services.equipment_validation import prepare_equipment_master


def _row(**values: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "호기": "EQ-1",
        "공정소분류": "Die Attach",
        "장기보관여부": "N",
        "기존설비여부": "Y",
        "레이아웃표시": "Y",
        "동": None,
        "층": None,
        "X좌표": None,
        "Y좌표": None,
        "Xsize": None,
        "Ysize": None,
    }
    row.update(values)
    return row


def _prepare(
    *rows: dict[str, Any], canvases: dict[tuple[str, str], tuple[float, float]] | None = None
) -> pd.DataFrame:
    return prepare_equipment_master(
        pd.DataFrame(list(rows)).reindex(columns=EQUIPMENT_COLUMNS), floor_canvases=canvases
    )


PLACED = {"동": "C1", "층": "1F", "X좌표": 10.0, "Y좌표": 5.0, "Xsize": 12.0, "Ysize": 7.0}


@pytest.mark.parametrize(
    "values",
    [
        pytest.param({}, id="Y-층미정-좌표없음"),
        pytest.param({"동": "C1", "층": "1F"}, id="Y-층있음-좌표없음"),
        pytest.param({"Xsize": 12.0, "Ysize": 7.0}, id="Y-크기만"),
        pytest.param({"동": "C1", "층": "1F", "Xsize": 12.0, "Ysize": 7.0}, id="Y-층있음-크기만"),
        pytest.param({"레이아웃표시": "N", "Xsize": 3.0, "Ysize": 2.0}, id="N-크기만"),
        pytest.param(PLACED, id="Y-배치"),
        # 예전에 통과하던 모양 — 조이면 그런 행이 든 리비전이 열리지 않는다.
        pytest.param(
            {"레이아웃표시": "N", "X좌표": 1.0, "Y좌표": 1.0, "Xsize": 2.0, "Ysize": 2.0},
            id="N-좌표-층없음",
        ),
    ],
)
def test_the_contract_accepts(values: dict[str, Any]) -> None:
    prepared = _prepare(_row(**values))

    assert len(prepared) == 1
    assert prepared.loc[0, "레이아웃표시"] == values.get("레이아웃표시", "Y")


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"X좌표": 1.0}, "X좌표·Y좌표는 함께"),
        ({"Xsize": 3.0}, "Xsize·Ysize는 함께"),
        ({"동": "C1", "층": "1F", "X좌표": 1.0, "Y좌표": 1.0}, "Xsize·Ysize 도 넣어야"),
        ({"X좌표": 1.0, "Y좌표": 1.0, "Xsize": 2.0, "Ysize": 2.0}, "동·층도 넣어야"),
        ({**PLACED, "X좌표": -1.0}, "0 이상"),
        ({"Xsize": 0.0, "Ysize": 2.0}, "0 보다 커야"),
        ({"Xsize": 3.0, "Ysize": -2.0}, "0 보다 커야"),
    ],
)
def test_the_contract_rejects(values: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _prepare(_row(**values))


def test_the_canvas_bound_applies_to_placed_rows_only() -> None:
    canvases = {("C1", "1F"): (20.0, 20.0)}
    # 크기만 있는 행은 캔버스보다 커도 상한 검사를 받지 않는다 — 아직 어디에도 서 있지 않다.
    _prepare(_row(Xsize=50.0, Ysize=50.0), canvases=canvases)

    with pytest.raises(ValueError, match="캔버스 범위를 벗어났습니다"):
        _prepare(_row(**{**PLACED, "X좌표": 10.0, "Xsize": 12.0}), canvases=canvases)


@pytest.mark.parametrize(
    "values",
    [
        pytest.param({**PLACED, "X좌표": "12,5", "Y좌표": "3,0"}, id="쉼표-소수점"),
        pytest.param({**PLACED, "Xsize": "12m"}, id="단위-붙음"),
        pytest.param({"레이아웃표시": "N", "Xsize": "3\xa0", "Ysize": "2"}, id="줄바꿈없는-공백"),
    ],
)
def test_an_unreadable_coordinate_is_refused_not_blanked(values: dict[str, Any]) -> None:
    """좌표는 비어도 되는 칸이라, 못 읽는 글자를 빈칸으로 흘리면 붙여넣은 호기가 조용히 미배치로
    저장된다. 빈칸과 못 읽는 값을 가른다."""
    with pytest.raises(ValueError, match="숫자로 읽을 수 없습니다"):
        _prepare(_row(**values))


def test_blank_text_in_a_coordinate_is_still_blank() -> None:
    prepared = _prepare(_row(**{"X좌표": " ", "Y좌표": "", "Xsize": "12", "Ysize": "7"}))

    assert pd.isna(prepared.loc[0, "X좌표"]) and prepared.loc[0, "Xsize"] == 12.0


def test_a_unit_flush_with_the_canvas_edge_is_inside() -> None:
    """88.7 + 11.3 은 부동소수로 100.00000000000001 이다. 저장 정밀도로 견줘 「밖」이 아니다."""
    canvases = {("C1", "1F"): (100.0, 60.0)}
    _prepare(_row(**{**PLACED, "X좌표": 88.7, "Xsize": 11.3}), canvases=canvases)

    with pytest.raises(ValueError, match="100.1 × 60 이상"):
        _prepare(_row(**{**PLACED, "X좌표": 88.8, "Xsize": 11.3}), canvases=canvases)
