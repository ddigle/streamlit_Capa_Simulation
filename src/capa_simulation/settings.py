from pathlib import Path

APP_NAME = "🏭S.PKG Capa Simulation"
MONTH_SELECTION_START = 202501
MONTH_SELECTION_END = 203012
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
TEMP_DIR = DATA_DIR / "temp"


def format_month(month: int) -> str:
    return f"{month // 100:04d}-{month % 100:02d}"


MONTH_SELECTION_OPTIONS = tuple(
    f"{year:04d}-{month:02d}"
    for year in range(MONTH_SELECTION_START // 100, MONTH_SELECTION_END // 100 + 1)
    for month in range(1, 13)
)
