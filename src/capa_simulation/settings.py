# Purpose: 앱 이름·파일 경로·조회기간 등 프로젝트 공통 설정 상수와 운영 DB 자리 판정을 정의한다.

import os
from collections.abc import Iterable
from pathlib import Path

# 탭 아이콘은 `st.set_page_config(page_icon=...)` 가 맡는다. 이름에 이모지를 붙이면
# 브라우저 탭에 아이콘이 두 번 나오고, 붙임표 없이 글자와 붙어 제목 줄이 지저분해진다.
# 메인 라벨 `S.PKG CAPA` + 부제 `AX Management` 다(2026-10-17 사용자 결정). 두 덩이를 따로 그리는
# 곳은 입장 화면 타이틀 두 줄(`intro_overlay.TITLE_LINES`), 사이드바·입장 화면 머리 줄의 심볼 옆
# 라벨 두 줄(`intro_overlay.BRAND`·`BRAND_SUBTITLE` — 둘 다 `tests/test_intro_overlay.py` 가 맞대
# 본다)과 시나리오가 없을 때의 머리 띠 두 줄(`app_header.header_lines`)이다.
APP_LABEL = "S.PKG CAPA"
APP_SUBTITLE = "AX Management"
APP_NAME = f"{APP_LABEL} {APP_SUBTITLE}"
# 사이드바 조회기간 선택기의 기본 범위다. 활성 시나리오의 실제 월이 이 범위 밖에
# 있으면 선택기의 허용 범위를 넓혀, 머지·연도 이동으로 만든 기간도 조회하게 한다.
MONTH_SELECTION_START = 202501
MONTH_SELECTION_END = 203012
# 앱의 버전·빌드일과 누가 만들었는지(담당 조직·문의처) 알리는 메타다. 보여 주는 곳은 모든 화면
# 사이드바 맨 아래의 앱 정보 카드(`components/app_credits.py`) 한 곳이다 — ⋮ 메뉴(About)는
# 감추고, 머리 띠는 적용 중인 시나리오를 싣는다. 담당 조직과 문의처는 실제 값이다.
APP_VERSION = "0.9.0-demo"
APP_OWNER_TEAM = "S.PKG 제조팀"
APP_CONTACT_EMAIL = "hoyeon.jeon@samsung.com"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 브라우저 탭 아이콘. `:material/…:` 이름을 주면 프런트엔드가 fonts.gstatic.com 에서 받아 오는데
# 사내 WebIDE 는 그 주소에 못 나갈 수 있다. 저장소의 SVG 파일 경로를 주면 Streamlit 이 파일을 읽어
# `data:image/svg+xml;base64,…` 로 실어 보내므로 외부 주소도, 사내의 URL 경로 접두도 타지 않는다.
# 그림은 앱의 메인 심볼(C 링 + 3×3 다이 — `intro_overlay.MARK_RING_PATH`)이다. 파일 안의
# `<style>` 이 탭 바탕의 밝기(`prefers-color-scheme`)에 따라 링·다이 색을 두 테마 토큰 값으로
# 바꾼다.
FAVICON_PATH = PROJECT_ROOT / "static" / "icons" / "capa_mark.svg"
# 사내에서 배포 ZIP 을 적용하면 `scripts/apply_deploy_package.py` 가 남기는 적용 기록. 앱 정보
# 카드가 여기서 적용된 배포 번호(`stamp`)를 읽는다 — 사외(개발 PC)에는 없다.
DEPLOY_STATE_PATH = PROJECT_ROOT / ".deploy" / "applied.json"
DATA_DIR = PROJECT_ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
DUCKDB_PATH = DATA_DIR / "capa_simulation.duckdb"
EQUIPMENT_DUCKDB_PATH = DATA_DIR / "equipment_availability.duckdb"
CORE_DATA_CSV_PATH = INPUT_DIR / "Core_Data.csv"
# C-DEP CD 컨테이너가 시작할 때 `scripts/container_start.py` 가 남기는 점검 결과(사내
# bigdataquery 설치·로그인 토큰 파일·요청자 계정). CD 서버에는 셸도 로그도 없어 앱 화면(Admin
# Area 「서버 시작 점검」·BigDataQuery 안내)이 이 파일을 읽는다. 개발·사내 PC 에는 없다.
# `data/temp/` 라 git·이미지에 실리지 않는다.
CONTAINER_START_REPORT_PATH = DATA_DIR / "temp" / "container_start.json"


def format_month(month: int) -> str:
    return f"{month // 100:04d}-{month % 100:02d}"


def _same_file(first: Path, second: Path) -> bool:
    """두 경로가 같은 파일·폴더인가 — 장치와 파일 번호(`os.stat`)로 본다. 읽지 못하면 아니다.

    번호가 0 이면(파일 번호를 주지 않는 파일 시스템) 같다고 보지 않는다 — 서로 다른 파일이 0 으로
    겹친다.
    """
    try:
        a, b = os.stat(first), os.stat(second)
    except OSError:
        return False
    return a.st_ino != 0 and (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def is_operational_database_place(
    path: Path, operational: Iterable[Path] = (DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH)
) -> bool:
    r"""사용자 앱이 여는 운영 DB 자리인가 — 사본 전용 스크립트는 열기 전에 거절하고, 운영 DB 를 여는
    점검 스크립트는 앱 프로세스를 먼저 본다(사내 런북 6-3 · 8-0).

    경로 글자만 견주면 비켜 가는 길이 있다 — Windows 의 `\\?\` 접두(`realpath` 가 남긴다)·UNC 관리
    공유(`\\localhost\C$\…`)·하드링크. 그래서 셋 가운데 하나면 운영 자리로 본다.

    1. 운영 DB 파일(`operational`)과 같은 파일 — 글자(`resolve`)나 장치·파일 번호가 같다.
    2. 운영 data 폴더(운영 DB 들의 폴더와 `DATA_DIR`) 그 자체나 그 아래 — 조상 폴더마다 글자나
       번호로 견준다.
    3. git 작업 트리 안 — 조상 폴더에 `.git` 이 있다. 사본은 저장소 밖에 둔다(런북 6-3 —
       `git archive` 사본 트리에는 `.git` 이 없다). 스크립트는 제가 든 트리의 `data/` 만 알아,
       사본 트리의 스크립트에 다른 저장소의 `data/` 를 주는 길을 1·2 로는 못 막는다.
    """
    files = [Path(item) for item in operational]
    folders = {DATA_DIR, *(item.parent for item in files)}
    given = Path(os.path.abspath(Path(path).expanduser()))
    resolved = given.resolve()
    if any(resolved == item.resolve() or _same_file(given, item) for item in files):
        return True
    resolved_folders = {folder.resolve() for folder in folders}
    for candidate in (given, resolved):
        for place in (candidate, *candidate.parents):
            if place in resolved_folders or any(_same_file(place, f) for f in folders):
                return True
            if os.path.lexists(place / ".git"):
                return True
    return False
