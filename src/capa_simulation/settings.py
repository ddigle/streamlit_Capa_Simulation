# Purpose: 앱 이름·파일 경로·조회기간 등 프로젝트 공통 설정 상수를 정의한다.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 파일 목적 및 최신 변경 출처 헤더를 표준화함; 이전 이력은 Git 기록을 참조함.

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


MONTH_SELECTION_OPTIONS = tuple(
    f"{year:04d}-{month:02d}"
    for year in range(MONTH_SELECTION_START // 100, MONTH_SELECTION_END // 100 + 1)
    for month in range(1, 13)
)
