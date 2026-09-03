# Purpose: 앱 이름·파일 경로·조회기간 등 프로젝트 공통 설정 상수를 정의한다.

from pathlib import Path

APP_NAME = "🏭S.PKG Capa Simulation"
MONTH_SELECTION_START = 202501
MONTH_SELECTION_END = 203012
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
TEMP_DIR = DATA_DIR / "temp"
DUCKDB_PATH = DATA_DIR / "capa_simulation.duckdb"
EQUIPMENT_DUCKDB_PATH = DATA_DIR / "equipment_availability.duckdb"
CORE_DATA_CSV_PATH = INPUT_DIR / "Core_Data.csv"


def format_month(month: int) -> str:
    return f"{month // 100:04d}-{month % 100:02d}"
