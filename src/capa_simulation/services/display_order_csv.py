"""CSV serialization for the scenario-independent display-order profile."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from capa_simulation.services.display_order_editor import (
    DISPLAY_ORDER_COLUMNS,
    validate_display_order,
)


def display_order_to_csv(display_order: pd.DataFrame) -> bytes:
    """Return a validated UTF-8 CSV that can be imported without modification."""
    validated = validate_display_order(display_order)
    return validated.to_csv(index=False).encode("utf-8-sig")


def display_order_from_csv(content: bytes) -> pd.DataFrame:
    """Parse UTF-8 or CP949 display-order CSV and validate its complete contract."""
    if not content:
        raise ValueError("표시순서 CSV 파일이 비어 있습니다.")
    parsed: pd.DataFrame | None = None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            parsed = pd.read_csv(
                BytesIO(content),
                encoding=encoding,
                keep_default_na=False,
                na_values=[""],
            )
        except UnicodeDecodeError:
            continue
        break
    if parsed is None:
        raise ValueError("표시순서 CSV는 UTF-8 또는 CP949 인코딩이어야 합니다.")

    actual_columns = [str(column).strip() for column in parsed.columns]
    expected_columns = list(DISPLAY_ORDER_COLUMNS)
    if actual_columns != expected_columns:
        missing = [column for column in expected_columns if column not in actual_columns]
        extra = [column for column in actual_columns if column not in expected_columns]
        details: list[str] = []
        if missing:
            details.append(f"누락: {', '.join(missing)}")
        if extra:
            details.append(f"추가: {', '.join(extra)}")
        if not details:
            details.append("컬럼 순서가 양식과 다름")
        raise ValueError(f"표시순서 CSV 컬럼 계약이 일치하지 않습니다 ({'; '.join(details)}).")
    parsed.columns = expected_columns
    return validate_display_order(parsed)
