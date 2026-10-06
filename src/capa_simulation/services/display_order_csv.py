# Purpose: CSV serialization for the scenario-independent display-order profile.

"""CSV serialization for the scenario-independent display-order profile."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from capa_simulation.services.clipboard_table import (
    TEXT_TABLE_READ_OPTIONS,
    parse_clipboard_table,
)
from capa_simulation.services.display_order_editor import (
    DISPLAY_ORDER_COLUMNS,
    validate_display_order,
)
from capa_simulation.services.frame_contracts import require_exact_columns


def display_order_to_csv(
    display_order: pd.DataFrame, *, allow_value_clashes: bool = False
) -> bytes:
    """Return a validated UTF-8 CSV that can be imported without modification.

    저장된 프로필을 내려받을 때는 `allow_value_clashes` 를 켠다. 대소문자만 다른 분류값이 남은
    예전 프로필도 내려받아 Excel 에서 고칠 수 있어야 한다 — 그 파일은 겹친 값을 고쳐야 다시
    올라간다.
    """
    validated = validate_display_order(display_order, allow_value_clashes=allow_value_clashes)
    return validated.to_csv(index=False).encode("utf-8-sig")


def display_order_from_csv(content: bytes, *, allow_value_clashes: bool = False) -> pd.DataFrame:
    """Parse UTF-8 or CP949 display-order CSV and validate its complete contract.

    `allow_value_clashes` 는 기동 때 읽는 로컬 시드 파일(`data/input/RQ_DISPLAY_ORDER.csv`)만 켠다 —
    사용자가 지금 올리는 파일이 아니라 이미 놓여 있는 파일이라 그것으로 기동을 막지 않는다.
    """
    if not content:
        raise ValueError("표시순서 CSV 파일이 비어 있습니다.")
    parsed: pd.DataFrame | None = None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            # 같은 표가 파일로 오든 붙여넣기로 오든 같게 읽혀야 한다. 옵션은
            # `clipboard_table` 한 군데가 갖는다 — 여기에 손으로 베껴 두면 한쪽만 바뀐다.
            parsed = pd.read_csv(BytesIO(content), encoding=encoding, **TEXT_TABLE_READ_OPTIONS)
        except UnicodeDecodeError:
            continue
        break
    if parsed is None:
        raise ValueError("표시순서 CSV는 UTF-8 또는 CP949 인코딩이어야 합니다.")

    return validate_display_order_import(parsed, allow_value_clashes=allow_value_clashes)


def display_order_from_clipboard(content: str) -> pd.DataFrame:
    """Parse a header-inclusive Excel clipboard block for the global profile."""
    return validate_display_order_import(parse_clipboard_table(content, "표시순서"))


def validate_display_order_import(
    parsed: pd.DataFrame, *, allow_value_clashes: bool = False
) -> pd.DataFrame:
    """Validate the full display-order import contract independently of its transport."""
    require_exact_columns(
        parsed.columns,
        DISPLAY_ORDER_COLUMNS,
        "표시순서 입력 표 컬럼",
        check_order=True,
        strip=True,
    )
    parsed.columns = list(DISPLAY_ORDER_COLUMNS)
    return validate_display_order(parsed, allow_value_clashes=allow_value_clashes)
