# Purpose: 앱 이름·파일 경로·조회기간 등 프로젝트 공통 설정 상수를 정의한다.

from pathlib import Path

# 탭 아이콘은 `st.set_page_config(page_icon=...)` 가 맡는다. 이름에 이모지를 붙이면
# 브라우저 탭에 아이콘이 두 번 나오고, 붙임표 없이 글자와 붙어 제목 줄이 지저분해진다.
APP_NAME = "S.PKG Capa Simulation"
# 사이드바 조회기간 선택기의 기본 범위다. 활성 시나리오의 실제 월이 이 범위 밖에
# 있으면 선택기의 허용 범위를 넓혀, 머지·연도 이동으로 만든 기간도 조회하게 한다.
MONTH_SELECTION_START = 202501
MONTH_SELECTION_END = 203012
# 앱의 버전·빌드일과 누가 만들었는지(담당 조직·문의처) 알리는 메타다. 보여 주는 곳은 모든 화면
# 사이드바 맨 아래의 앱 정보 카드(`components/app_credits.py`) 한 곳이다 — ⋮ 메뉴(About)는
# 감추고, 머리 띠는 적용 중인 시나리오를 싣는다. 담당 조직과 문의처는 실제 값이다.
APP_VERSION = "0.9.0-demo"
APP_BUILD_DATE = "2026-09-08"
APP_OWNER_TEAM = "S.PKG 제조팀"
APP_CONTACT_EMAIL = "hoyeon.jeon@samsung.com"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 브라우저 탭 아이콘. `:material/…:` 이름을 주면 프런트엔드가 fonts.gstatic.com 에서 받아 오는데
# 사내 WebIDE 는 그 주소에 못 나갈 수 있다. 저장소의 SVG 파일 경로를 주면 Streamlit 이 파일을 읽어
# `data:image/svg+xml;base64,…` 로 실어 보내므로 외부 주소도, 사내의 URL 경로 접두도 타지 않는다.
# 글리프는 Material Symbols Rounded `factory`(Apache-2.0 — 같은 폴더 `LICENSE-Apache-2.0.txt`)다.
FAVICON_PATH = PROJECT_ROOT / "static" / "icons" / "factory.svg"
DATA_DIR = PROJECT_ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
DUCKDB_PATH = DATA_DIR / "capa_simulation.duckdb"
EQUIPMENT_DUCKDB_PATH = DATA_DIR / "equipment_availability.duckdb"
CORE_DATA_CSV_PATH = INPUT_DIR / "Core_Data.csv"


def format_month(month: int) -> str:
    return f"{month // 100:04d}-{month % 100:02d}"
