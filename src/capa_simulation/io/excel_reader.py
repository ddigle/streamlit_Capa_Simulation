"""Read saved Excel Table values from an XLSB workbook with xlwings."""

from pathlib import Path

import pandas as pd
import xlwings as xw

REFERENCE_TABLES = (
    "RQ_PKG_PLAN",
    "RQ_YLD",
    "RQ_CHIP_QTY",
    "RQ_CHIP_EQ",
    "RQ_DISPLAY_ORDER",
)


def _read_table(workbook: xw.Book, table_name: str) -> pd.DataFrame:
    for sheet in workbook.sheets:
        if table_name not in [table.name for table in sheet.tables]:
            continue

        values = sheet.tables[table_name].range.value
        if not values:
            raise ValueError(f"Excel Table이 비어 있습니다: {table_name}")

        headers = [str(value).strip() if value is not None else "" for value in values[0]]
        if not all(headers):
            raise ValueError(f"빈 헤더가 존재합니다: {table_name}")

        return pd.DataFrame(values[1:], columns=headers)

    raise ValueError(f"Excel Table을 찾을 수 없습니다: {table_name}")


def load_reference_tables(workbook_path: Path) -> dict[str, pd.DataFrame]:
    """Open a workbook read-only and return the required reference tables."""
    if not workbook_path.is_file():
        raise FileNotFoundError(workbook_path)

    with xw.App(visible=False, add_book=False) as app:
        app.display_alerts = False
        app.screen_updating = False
        workbook = app.books.open(str(workbook_path), update_links=False, read_only=True)
        try:
            return {name: _read_table(workbook, name) for name in REFERENCE_TABLES}
        finally:
            workbook.close()
