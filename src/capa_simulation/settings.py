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
# 앱을 누가 만들었고 어떤 인증으로 배포되는지 알리는 메타다. ⋮ 메뉴의 About(공식 API)과
# 상단 글(`components/app_header.py`)이 **같은 값을 본다** — 두 자리에 따로 적으면 배포마다
# 버전이 어긋난다. 담당 조직과 문의처는 실제 값이고 인증번호·도움말 URL 은 아직 자리만 잡아
# 둔 표본이라, 사내 배포 전에 실제 값으로 바꾼다.
APP_VERSION = "0.9.0-demo"
APP_BUILD_DATE = "2026-09-08"
APP_OWNER_TEAM = "S.PKG 제조팀"
APP_CONTACT_EMAIL = "hoyeon.jeon@samsung.com"
APP_SECURITY_LEVEL = "DEMO-CONFIDENTIAL"
APP_AUTH_CODE = "DEMO-AUTH-0000"
APP_AUTH_EXPIRY = "2026-12-31"
APP_HANDLING_NOTE = "반출·사외 공유 금지"
APP_HELP_URL = "https://example.com/demo/capa-simulation/guide"
APP_BUG_REPORT_URL = "https://example.com/demo/capa-simulation/issues"
APP_ABOUT = f"""### {APP_NAME}

월별 생산계획을 부하량으로 환산해 공정별 Capa·확보율과 B/N 공정을 함께 보는 사내 도구다.

**빌드**
- 버전 `{APP_VERSION}` · 빌드일 {APP_BUILD_DATE}
- 실행 환경 Python 3.10.11 · Streamlit

**개발**
- 담당 {APP_OWNER_TEAM}
- 문의 {APP_CONTACT_EMAIL}

**인증**
- 보안등급 {APP_SECURITY_LEVEL}
- 인증번호 {APP_AUTH_CODE} (유효기간 {APP_AUTH_EXPIRY})
- {APP_HANDLING_NOTE}

현재 화면의 수치는 구조 검토용 합성 표본이며 운영 실적이 아니다.
"""
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
DUCKDB_PATH = DATA_DIR / "capa_simulation.duckdb"
EQUIPMENT_DUCKDB_PATH = DATA_DIR / "equipment_availability.duckdb"
CORE_DATA_CSV_PATH = INPUT_DIR / "Core_Data.csv"


def format_month(month: int) -> str:
    return f"{month // 100:04d}-{month % 100:02d}"
