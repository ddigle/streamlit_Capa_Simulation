# Purpose: 앱 이름·파일 경로·조회기간 등 프로젝트 공통 설정 상수를 정의한다.

from pathlib import Path

# 탭 아이콘은 `st.set_page_config(page_icon=...)` 가 맡는다. 이름에 이모지를 붙이면
# 브라우저 탭에 아이콘이 두 번 나오고, 붙임표 없이 글자와 붙어 제목 줄이 지저분해진다.
APP_NAME = "S.PKG Capa Simulation"
# 사이드바 조회기간 선택기의 상·하한이다. 데이터에서 읽지 않고 못박은 업무 상수라,
# 2031년 이후 생산계획년월이 들어오면 DB 에는 있는데 화면에서 고를 수 없다. 그때는
# 이 값을 넓혀야 한다 — 조용히 조회 범위가 좁혀지는 형태로만 드러난다.
MONTH_SELECTION_START = 202501
MONTH_SELECTION_END = 203012
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
DUCKDB_PATH = DATA_DIR / "capa_simulation.duckdb"
EQUIPMENT_DUCKDB_PATH = DATA_DIR / "equipment_availability.duckdb"
CORE_DATA_CSV_PATH = INPUT_DIR / "Core_Data.csv"


def format_month(month: int) -> str:
    return f"{month // 100:04d}-{month % 100:02d}"
