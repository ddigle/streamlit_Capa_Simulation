# Purpose: 런북 7장 화면 확인을 별도 포트 앱과 저장소 밖 Playwright 로 돌려 개수·있음/없음만 찍는다.

"""사내 배포 화면 확인 — 런북 7장(`docs/internal_update_runbook.md`)의 화면 확인을 코드로 고정한다.

사내 에이전트는 배포마다 7장의 화면 확인을 저장소 밖에 설치한 Playwright 와 이미 깔린 Chrome 으로
손수 해 왔다(`202610081500` 리뷰 「사외 요청」 4번). 그 요령 — 입장 화면 단추는 `#capa-intro-host`
안, 데이터 편집기 머리 칸은 `[role=columnheader]` 의 `aria-colindex` 를 가로로 굴려 찾기, Space
서랍 검색은 `type`(fill 은 반응이 없다) — 을 이 파일이 갖는다. 사외에서 만들며 더 찾은 넷도 있다 —
첫 방문의 테마 스크립트가 화면을 한 번 새로 읽어 그 사이 `evaluate` 가 끊긴다(`Screen.enter`), 접힌
사이드바 묶음을 펴는 동안 누른 링크는 이동하지 않는다(`Screen.open_page`), 컴포넌트(Space 편집기)는
shadow root 안이라 `document.querySelector` 로 닿지 않는다(로케이터로 잡은 요소에서 `evaluate`), CSS
선택자에 한글을 `json.dumps` 기본값(`\\uXXXX`)으로 넣으면 아무것도 못 찾는다(`_css_string`).
팝업(`st.dialog`)은 `document` 에서 `[role=dialog]` 로 찾는다 — 입장 화면 무대(shadow root 안)도
같은 역할이라 shadow 를 뚫는 로케이터는 그것까지 잡는다(`Screen.dialog_read`).

    uv pip install --target <저장소 밖>/pw playwright        # 처음 한 번. 브라우저는 받지 않는다
    uv run --no-sync python scripts/check_deploy_screens.py --playwright-dir <저장소 밖>/pw \\
        --output <저장소 밖>/screens.md
    uv run --no-sync python scripts/check_deploy_screens.py --list   # 항목 목록만(Playwright 없이)

1분 넘게 걸린다(사외 합성 표본에서 앱 기동·입장 화면 포함 약 1분, 사내 실데이터는 더). 에이전트는
앞단 호출 제한(10분)에 걸리지 않게 **백그라운드로** 돌리고 `--output` 파일을 읽는다.

**종료 코드.** 0 끝까지 돎 · 2 준비 안 됨·멈춤(경로·Playwright·포트·DB 를 열지 못함·앱 기동·
앱 오류 화면·브라우저·예산 넘음·예상 밖 예외 — 예외는 종류만 찍는다) · 3 미룸(사용자 앱이 떠 있거나,
떠 있는지 살피지 못함 — 앱을 끄지 않는다). 미룸을 1 로 두지 않는 것은 강제 종료와 파이썬의 처리 안
된 예외가 1 로 끝나기 때문이다. `--output` 은 경로 검사를 지나면 곧바로 「확인 시작 — 아직 항목
없음」으로 덮어쓰고(지난 실행의 블록이 남지 않게), 일찍 끝나면 「미룸 — …」·「멈춤 — …」 한 줄로,
항목이 돌면 그때마다 전체 블록으로 바꾼다.

**하는 일.** 사용자 앱이 떠 있는지 먼저 본다 — `streamlit run … app.py` 프로세스, 그리고
두 DuckDB 를 열 수 있는지. 있으면 「사용자 앱이 떠 있습니다 — 화면 확인은 미룹니다」 한 줄과
코드 3 으로 멈춘다(사용자 앱은 절대 끄지 않는다). 앱은 rerun 동안만 DB 를 쥐어 가만히 떠 있는
앱은 잠금 확인을 지나치므로 프로세스를 함께 본다(살피지 못하면 없다고 넘기지 않고 미룬다).
그다음 `127.0.0.1:--port` 에 이 저장소의 앱을 따로 띄우고(자식의 `PYTHONPATH` 맨 앞에 이
저장소의 `src` — 사전 확인과 같은 DB 를 여는지 띄우기 전에 견준다) `/_stcore/health` 를 기다린
뒤, 헤드리스 Chrome 으로 입장 화면을 넘긴다. 앱이 오류 화면(부트스트랩 실패)이면 항목을 돌리지
않는다. 끝나면(예외로 끝나도) 띄운 앱을 끄고, 띄우기 전과 뒤의 마이그레이션 번호를 견줘 이 확인이
건 마이그레이션 수를 머리에 적는다. 결과는 리뷰 문서에 그대로 붙이는 Markdown 블록이다.

**지키는 것.**

- **값을 찍지 않는다.** 결과 칸에는 개수·있음/없음·같음/다름·px 만 둔다. 공정·제품·설비·시나리오
  이름이나 코드처럼 화면에서 읽은 글자는 넣지 않는다 — 화면 글자는 판정에만 쓰고 버린다. 실패는
  예외 종류(클래스 이름)만 적는다. 이 앱의 오류 문구에는 식별값이 실린다.
- **DB 에 쓰지 않는다.** 쓰는 항목은 `writes=True` 로 등록하고, `--allow-writes` 없이는 돌리지 않고
  「안 함(허락 없음)」으로 찍는다. 쓰는 항목은 저장한 것을 같은 항목 안에서 지워 원상 복구하는 것만
  둔다.
- **경로는 저장소 밖만 받는다.** `--output`·`--shots`·`--playwright-dir` 가 저장소 안이거나
  장치·UNC 꼴(`\\\\?\\…`·`\\\\localhost\\C$\\…`)이면 거절한다. 스크린샷은 `--shots` 를 줄 때만
  찍는다(화면에 이름이 보이므로 리뷰 커밋 전에 지운다).
- **Playwright 는 이 저장소의 의존성이 아니다.** `--playwright-dir` 를 `sys.path` 끝에 붙여
  부를 때만 읽는다. 이 파일의 나머지(경로 검사·잠금 확인·앱 수명·결과 꼴)는 Playwright 없이
  돈다.
- **30분 안에 끝난다.** 사내 백그라운드 실행은 30분이면 죽는다. `--budget-minutes`(기본 15)는
  스크립트 시작부터 재고, 넘긴 뒤의 항목은 「미기록 — 시간 예산 넘음」으로 남긴다. `--output` 은
  항목마다 다시 써서 중간에 끊겨도 그때까지 돈 칸이 남는다. 스크립트가 강제로 끝나도 띄운 앱이
  남지 않게 Windows 는 Job Object, Linux 는 `PR_SET_PDEATHSIG` 로 묶는다.

**항목 더하는 법**(통합자가 배포마다 7장을 쓰며 더한다). 함수 하나를 쓰고 `ITEMS` 에 한 줄을 더한다.

    def check_new_thing(screen: Screen) -> str:
        screen.open_page(EQUIPMENT_PAGE)
        screen.open_tab("설비 마스터")
        open_bulk_import(screen)  # 「엑셀·CSV로 한꺼번에」 팝업
        try:
            return "있음" if screen.selectbox_value("등록할 표") is not None else "없음"
        finally:
            screen.close_dialog()

    ITEMS = (..., Item("new_thing", "새 확인", check_new_thing),)

함수는 `Screen`(공통 뼈대 — 페이지 이동·탭·사이드바 상자·선택 상자·스위치·팝업·데이터 편집기
머리 칸·행 읽기)만 쓰고, 결과 문자열은 고정 글자와 수로만 만든다. 항목 하나가 예외로 끝나도
나머지는 돈다. 돌기 전에 뼈대가 펼친 목록·열린 팝업·덮개(Summary)를 닫는다(`Screen.settle`).
화면을 바꾸는 토글은 항목 안에서 `try/finally` 로 되돌리고, 연 팝업은 `finally` 에서 `Esc` 로
닫는다(`Screen.close_dialog`).

사외에서 돈 수는 합성 표본의 `샘플 관측` 일 뿐이다(AGENTS.md 10-1).
"""

from __future__ import annotations

import argparse
import html
import importlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import IO, Any, Final, Protocol

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _use_utf8_stdout() -> None:
    # Windows 콘솔 기본 코드페이지(cp949)는 이 출력의 기호를 못 쓴다.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


# 앱 모듈을 못 부르면(가상환경·배포 어긋남) 종류만 찍고 2 로 끝낸다. 그냥 두면 traceback 과 함께
# 1 로 끝난다.
try:
    import duckdb

    from capa_simulation.components.theme_toggle import (  # noqa: E402
        GUIDE_BUTTON_ID,
        PRINT_BUTTON_ID,
        THEME_BUTTON_ID,
        TOOLBAR_BUTTON_ORDER,
    )
    from capa_simulation.persistence._sql_helpers import lock_holder_pid  # noqa: E402
    from capa_simulation.persistence.equipment_migration_runner import (  # noqa: E402
        load_equipment_migrations,
    )
    from capa_simulation.persistence.migration_runner import load_migrations  # noqa: E402
    from capa_simulation.settings import (  # noqa: E402
        DEPLOY_STATE_PATH,
        DUCKDB_PATH,
        EQUIPMENT_DUCKDB_PATH,
    )
except Exception as _import_error:  # noqa: BLE001 — 종류만 찍는다
    _use_utf8_stdout()
    print(f"앱 모듈을 불러오지 못했습니다 — {type(_import_error).__name__}")
    raise SystemExit(2) from None

EXIT_OK: Final = 0
# 미룬다 — 사용자 앱이 떠 있거나(프로세스·DB 잠금) 떠 있는지 살피지 못했다. 이 뜻에만 쓴다. 1 이
# 아닌 것은 강제 종료(`TerminateProcess`)와 처리 안 된 예외가 1 로 끝나기 때문이다.
EXIT_DEFERRED: Final = 3
# 그 밖 모두 — 경로·Playwright·포트·DB 를 열지 못함·앱 기동·앱 오류 화면·브라우저·예상 밖 예외.
EXIT_NOT_READY: Final = 2

DEFERRED_MESSAGE: Final = "사용자 앱이 떠 있습니다 — 화면 확인은 미룹니다"
SCAN_FAILED_MESSAGE: Final = (
    "프로세스를 살피지 못했습니다 — 런북 1-1 로 사용자 앱이 없는 것을 손수 확인한 뒤 "
    "--ignore-other-apps 로 다시 돌립니다"
)
INSTALL_HINT: Final = (
    "Playwright 가 없습니다 — 저장소 밖에 한 번 설치합니다"
    "(브라우저는 받지 않고 깔린 Chrome 을 씁니다):\n"
    "  uv pip install --target <저장소 밖 폴더> playwright\n"
    "그 폴더를 --playwright-dir 로 줍니다."
)
UNRECORDED: Final = "미기록"
SKIPPED_NO_PERMISSION: Final = "안 함(허락 없음)"
OVER_BUDGET: Final = f"{UNRECORDED} — 시간 예산 넘음"

DEFAULT_PORT: Final = 8551
DEFAULT_CHANNEL: Final = "chrome"
# 스크립트 시작부터 잰다. 사내 백그라운드 제한 30분 안이다.
DEFAULT_BUDGET_MINUTES: Final = 15.0
# 확인용 앱은 이 PC 안에서만 듣는다.
APP_ADDRESS: Final = "127.0.0.1"
VIEWPORT: Final = (1600, 1000)
# 앱이 health 에 답할 때까지, 입장 화면의 `Detail` 이 눌릴 수 있을 때까지(공식버전 요약을 다
# 받은 뒤다 — 사외 합성 표본에서 18초). 사내 실데이터는 더 걸린다.
START_TIMEOUT_SECONDS: Final = 180.0
INTRO_TIMEOUT_SECONDS: Final = 180.0
STOP_TIMEOUT_SECONDS: Final = 15.0
# 항목 하나 안의 Playwright 기다림(클릭·나타남) 기본값.
ACTION_TIMEOUT_MS: Final = 30_000

# 화면 계약. 바뀌면 `tests/test_check_deploy_screens.py` 가 자산·코드와 대조해 알린다.
# 입장 화면 호스트(`intro_overlay_assets/intro.js` 의 `HOST_ID`). 열린 shadow root 라 CSS 로 뚫린다.
INTRO_HOST_ID: Final = "capa-intro-host"
# 사이드바 머리칸의 앱 이름 라벨(`intro_overlay.SUMMARY_LABEL_ID`). 그 모듈을 부르면 Streamlit
# 캐시 경고가 수십 줄 찍혀 출력이 지저분해진다 — 값만 옮기고 테스트가 같은지 본다.
SUMMARY_LABEL_ID: Final = "capa-brand-label"
EQUIPMENT_PAGE: Final = "available_equipment_status"
SPACE_PAGE: Final = "space_status"
# `Space 현황` 경로 줄 첫 칸 `S.PKG FAB 전체` 단추의 위젯 키. FAB 전체면 주 단추, 층을 열었으면 보조
# 단추이고 누르면 FAB 로 돌아간다(콜백 — 세션의 연 층을 지운다).
SPACE_FAB_CRUMB_KEY: Final = "space_status_fab_breadcrumb"
# 설비 마스터 표(가용설비 현황 탭 ① — 개편 B1)의 「전체 39칸」 머리 칸 — 38열 개편(설비 마이그레이션
# 0023)의 새 이름 일곱과 설비 시나리오(0027)의 39번째 칸 「시나리오 메모」, 그리고 지운 컬럼 하나.
# 앱 모듈(`equipment_contract`)을 부르지 않고 값만 옮긴다 — 화면이 계약과 같은지 따로 보는 확인이라
# 계약에서 이름을 꺼내면 둘이 함께 틀려도 「같음」이다. 테스트가 계약과 같은지 본다.
EQUIPMENT_NEW_HEADERS: Final = (
    "Area Code",
    "반입실적",
    "반입상태",
    "Qual실적",
    "Qual상태",
    "정지일정",
    "반출/이설일정",
    "시나리오 메모",
)
EQUIPMENT_DROPPED_HEADER: Final = "설비가동현황"
# 설비 마스터 표 컴포넌트(Components v2 — 열린 그림자 DOM, Playwright 로케이터가 뚫는다)의 마운트
# key(`st-key-<key>` 칸)·단추 글·칸 묶음. 앱 모듈을 부르지 않고 값만 옮긴다(테스트가 앱과 같은지
# 본다). 시나리오 칸은 머리 둘째 줄 「시나리오」 표지로 센다.
EQUIPMENT_GRID_KEY: Final = "equipment_grid_table"
EQUIPMENT_LOADER_KEY: Final = "equipment_grid_loader"
BULK_IMPORT_BUTTON: Final = "엑셀·CSV로 한꺼번에"
BULK_IMPORT_TITLE: Final = "엑셀·CSV로 한꺼번에"
GRID_ALL_COLUMNS_SET: Final = "전체 39칸"
GRID_COLUMN_SETS: Final = 5
GRID_ALL_COLUMNS: Final = 39
GRID_SCENARIO_HEADERS: Final = 7
GRID_SCENARIO_MARK: Final = "시나리오"
# 칸 하나 고침·틀린 날짜를 넣어 볼 칸(공통 글 칸 · 시나리오 날짜 칸)과 넣을 글. 넣은 것은 끝에
# 「모두 버리기」 로 편집본째 버린다 — DB 에 쓰지 않는다.
GRID_TEXT_COLUMN: Final = "메모3"
GRID_DATE_COLUMN: Final = "반입일정"
GRID_TEXT_PROBE: Final = "화면 확인"
GRID_BAD_DATE: Final = "2026-13-45"
GRID_DISCARD_CONFIRM: Final = "모두 버리기 확인"
EQUIPMENT_SIDE_CHANGES: Final = "저장 전 변경"
EQUIPMENT_SIDE_KEY: Final = "equipment_master_side_v1"
EQUIPMENT_DISCARD_KEY: Final = "equipment_master_discard_v1"
TOOLBAR_LABELS: Final[dict[str, str]] = {
    GUIDE_BUTTON_ID: "Guide",
    PRINT_BUTTON_ID: "Print",
    THEME_BUTTON_ID: "테마",
}
SCENARIO_MANAGEMENT_PAGE: Final = "scenario_management"
ADMIN_AREA_PAGE: Final = "admin_area"
# 공정 Capa 상세(`app_pages/process_capa_detail.py`)와 그 화면의 컨테이너 key(`process_capa_view`·
# `process_detail_state`). 앱 모듈을 부르면 Streamlit 캐시 경고가 찍혀 값만 옮기고 테스트가 같은지
# 본다.
PROCESS_DETAIL_PAGE: Final = "process_capa_detail"
# 필요 단축 일정 — 가용설비 현황의 탭이던 것을 실행 관리 아래 별도 화면으로 뗐다(2026-10-18).
SHORTENING_PAGE: Final = "required_shortening"
PROCESS_DETAIL_KEYS: Final[dict[str, str]] = {
    "kpi": "process_detail_kpis",
    "canvas": "process_detail_summary_months",
    "scroll": "process_detail_canvas_scroll",
    "evidence": "process_detail_evidence",
    "absent": "process_detail_dynamic_absent",
}
# 월 그림에서 누를 칸의 세로 자리(px, 그림 위 끝부터) — 머리 36 + ① 제목 44(제목 칸 26 + 세부 글
# 한 줄 14 + 여백 4) + 값 27 × 3 + 반 줄. 확보율 줄의 가운데다(새 세션의 기본 — ① 은 펼치고 제품
# 행은 펼치지 않은 그림. 제목 끝 ▾/▸ 는 제목 줄 높이를 바꾸지 않는다).
PROCESS_DETAIL_RATE_ROW_PX: Final = 36 + 44 + 27 * 3 + 13
# 공정 Capa 상세 사이드바 조건 카드(접힘이 기본 — 안의 칸을 쓰려면 편다)와 그 끝 「이 세션만」 UPEH
# 가정 % 칸, 가정이 켜지면 ① 끝에 서는 세 줄의 라벨(`process_capa_canvas._assumption_rows` —
# 「UPEH 110% · 소요대수」 꼴)과 머리 배지 앞머리. 값만 옮기고 테스트가 앱과 같은지 본다.
PROCESS_DETAIL_CARD_KEY: Final = "condition_card_process_capa_detail"
UPEH_PERCENT_LABEL: Final = "UPEH 가정 (%)"
UPEH_TRIAL_PERCENT: Final = 110
UPEH_DEFAULT_PERCENT: Final = 100
UPEH_ROW_NAMES: Final = ("소요대수", "확보율", "확보기준 과부족")
# 표 도구 줄의 「구획」 칩(`st.pills` — 누른 칩이 펼친 구획, `aria-pressed`)과 칩 글자 차례. 밖에서
# 들어온 길이 다시 펴는 구획 — HOME 칸 → ①, 가용설비 현황 근거 카드 링크 → ④.
PROCESS_DETAIL_SECTIONS_KEY: Final = "process_detail_sections"
PROCESS_DETAIL_SECTION_LABELS: Final = ("① 공식", "② 일정 가용", "③ 단축", "④ 비가동")
# HOME `주요공정 확보율` 월 그림(칸을 누르면 그 공정·그 달로 공정 Capa 상세가 열린다). 표적
# 막대(trace 0) `customdata` 끝 일곱 칸이 이동 정보이고 그 첫 칸이 공정이다 — 과거 실적 칸은 비어
# 누르지 않는다.
HOME_KEY_PROCESS_CHART_KEY: Final = "key_process_heatmap_months"
HOME_CELL_LINK_FIELD_COUNT: Final = 7
# Streamlit 이 프래그먼트 콜백 안에서 요소를 그리면 콘솔에 남기는 경고의 앞머리(사내 리뷰 2227
# 후속 — HOME 칸 누름이 이 경고를 남기던 것을 고쳤다). 앱 콘솔 출력에서 이 글이 든 줄 수만 센다.
FRAGMENT_CALLBACK_WARNING: Final = "A fragment rerun was triggered"
# 확인용 앱 콘솔에서 줄 수를 세는 글 — 여기 없는 글은 세지 않는다(`ConsoleCounter`).
CONSOLE_NEEDLES: Final = (FRAGMENT_CALLBACK_WARNING,)
# 가용설비 현황 Static 대비 일정의 사이드바 `설비 조회 조건` 카드와 그 안의 `공정` 상자(처음 값
# `전체 합계`), 공정 하나일 때 근거 카드에 붙는 공정 Capa 상세 ④ 링크 글.
EQUIPMENT_CARD_KEY: Final = "condition_card_equipment"
GAP_PROCESS_KEY: Final = "equipment_gap_process_filter_v1"
GAP_ALL_PROCESSES: Final = "전체 합계"
GAP_DETAIL_LINK_LABEL: Final = "공정 Capa 상세 ④ 에서 비가동 화살표로 보기"
# 기준 정보(`app_pages/reference_data.py`) 첫 탭 UPEH 편집표의 월 칸 머리 도움말
# (`EDITOR_VALUE_HELP`)에서 찾는 글 둘. 풍선은 머리 칸 위에 마우스를 올려야 선다(Glide 캔버스 —
# 머리 칸 DOM 은 크기가 0).
REFERENCE_PAGE: Final = "reference_data"
UPEH_HELP_WORDS: Final = ("UPEH", "ST(분)")
# 제약 시뮬레이션(`app_pages/constraint_simulation.py`)과 그 화면의 컨테이너 key
# (`constraint_simulation_state`·`constraint_simulation_view`·페이지 까닭 카드). 값만 옮기고
# 테스트가 같은지 본다. 공정 Capa 상세 머리의 「이 공정 제약 시뮬레이션」 링크 글도 같다.
CONSTRAINT_PAGE: Final = "constraint_simulation"
CONSTRAINT_LINK_LABEL: Final = "이 공정 제약 시뮬레이션"
CONSTRAINT_KEYS: Final[dict[str, str]] = {
    "kpi": "constraint_sim_kpis",
    "chart": "constraint_sim_rate_chart",
    "sheet": "constraint_sim_sheet_chart",
    "steps": "constraint_sim_steps",
    "schedule": "constraint_sim_schedule",
    "absent": "constraint_sim_absent",
    "process": "constraint_sim_process",
    "detailProcess": "process_detail_process",
}
# HOME 링크를 감싼 사이드바 칸(`app.py`). HOME 은 기본 페이지라 주소 끝이 비어 `open_page` 로는
# 못 고른다.
HOME_LINK_KEY: Final = "home_navigation"
# 머리 띠 아래 화면 탭 줄(`page_tabs_state.PAGE_TABS_COMPONENT_KEY`·`MAX_TABS`). 값만 옮기고
# 테스트가 같은지 본다. 탭은 그림자 DOM 안의 목록 단추다 — 탭 역할을 쓰지 않아 `open_tab` 이 잡지
# 않는다.
PAGE_TABS_KEY: Final = "page_tabs_strip"
PAGE_TABS_MAX: Final = 10
HOME_MAIN_TAB: Final = "Main"
# 사이드바 「조회 조건」 통합 패널. 앱 모듈(`sidebar_status`·`condition_field`·`scenario_status`·
# `period_field`·`home_preference`)을 부르면 Streamlit 캐시 경고가 찍혀 값만 옮기고 테스트가 같은지
# 본다.
CONDITIONS_SECTION_KEY: Final = "sidebar_section_conditions"
CONDITIONS_SECTION_TITLE: Final = "조회 조건"
CONDITIONS_BOX_KEY: Final = "sidebar_conditions_box"
CONDITION_NAME_ROW_PREFIX: Final = "condition_name_"
CONDITION_CARD_PREFIX: Final = "condition_card_"
LOB_CARD_LABEL: Final = "LOB 표시 조건"
# 패널 줄 이름(정한 어휘)과 HOME Main 탭의 차례. 시나리오 줄 이름은 「시나리오 · rN」이다.
PANEL_ROW_NAMES: Final = ("시나리오", "조회기간", "공정 필터", "주요공정 히트맵")
# 설비 화면(가용설비 현황·필요 단축 일정·공정 Capa 상세·Space 현황)의 설비 시나리오 줄 이름. HOME
# 에는 서지 않는다(`navigation.PageSpec.equipment_scenario`).
EQUIPMENT_SCENARIO_ROW_NAME: Final = "설비 시나리오"
UNKNOWN_ROW_NAME: Final = "그 밖"
# 이번 배포에서 걷은 사이드바 상자 제목. 「시나리오·리비전」은 이제 팝업 제목이다(사이드바 밖).
OLD_BOX_TITLES: Final = ("B/N 집계 공정", "시나리오·리비전")
# 팝업을 여는 값 칸(위젯 key)과 팝업 제목·안의 글자.
SCENARIO_FIELD_KEY: Final = "sidebar_scenario_field"
PERIOD_FIELD_KEY: Final = "sidebar_period_field"
PROCESS_FIELD_KEY: Final = "dashboard_bottleneck_process_dialog_open"
SCENARIO_DIALOG_TITLE: Final = "시나리오·리비전"
SCENARIO_DIALOG_MODES: Final = ("불러오기", "새 리비전 저장")
REVISION_RADIO_LABEL: Final = "리비전"
PERIOD_DIALOG_TITLE: Final = "조회기간"
MONTH_INPUT_IDS: Final = ("capa-start-month", "capa-end-month")
MONTH_APPLY_ID: Final = "capa-month-apply"
MONTH_APPLY_LABEL: Final = "적용"
PROCESS_DIALOG_TITLE: Final = "공정 필터"
# 설비 시나리오 줄(`components/equipment_scenario_status.py`) — 값 칸 위젯 key·이름 줄 slug·팝업
# 제목·구획 둘(「저장」 은 편집본을 세우는 가용설비 현황·필요 단축 일정에만 선다).
EQUIPMENT_SCENARIO_FIELD_KEY: Final = "sidebar_equipment_scenario_field"
EQUIPMENT_SCENARIO_ROW_SLUG: Final = "equipment_scenario"
EQUIPMENT_SCENARIO_DIALOG_TITLE: Final = "설비 시나리오"
EQUIPMENT_SCENARIO_DIALOG_MODES: Final = ("불러오기", "저장")
# 사이드바 설비 시나리오 배지 종류(`equipment_status_badge` 가 낼 수 있는 모든 글 — 시험이 대 본다).
# 「가정 배치」 — 그리는 설비 시나리오 리비전의 배치가 공식과 다름(설비 시나리오 2단계 S3), 「일정
# 없이 엶」 — 옛 배포 흔적으로 일정 없이 연 세션.
EQUIPMENT_STATUS_BADGES: Final = (
    "공식 v",
    "최신 r",
    "가정 배치",
    "저장된 리비전",
    "미저장 변경",
    "일정 없이 엶",
)
THRESHOLD_POINTER: Final = "판정 기준은 HOME → Preference 에서 정합니다."
# 다른 화면의 패널 줄(`navigation.PageSpec.reads_*`) — (주소 끝, 결과에 찍는 화면 이름, 줄 이름).
# 줄 이름이 None 이면 패널이 서지 않는다(Space 현황은 조건 카드만 있어 구역 제목만 선다).
OTHER_PAGE_PANELS: Final[tuple[tuple[str, str, tuple[str, ...] | None], ...]] = (
    (SCENARIO_MANAGEMENT_PAGE, "시나리오 관리", ("시나리오", "조회기간")),
    (ADMIN_AREA_PAGE, "Admin Area", ("시나리오",)),
    # Space 현황은 색 기준이 필요 단축이 아니면 시나리오·조회기간을 읽지 않고 설비 시나리오 줄(고를
    # 수 있는 줄 — 그 시나리오의 배치를 그린다)만 선다(이 항목은 기본 색 기준에서 돈다).
    (SPACE_PAGE, "Space 현황", (EQUIPMENT_SCENARIO_ROW_NAME,)),
)
# 사이드바 계산 그룹 셋(2026-10-17 사용자 결정 — 약속 · 이행 · 실적) — (상자 slug, 상자 제목,
# 하위 화면 수), 사이드바 차례 그대로. 상자는 `st-key-<slug>_box`, 안의 링크는 머리(「현황 요약」)
# 하나와 하위다.
# 앱 선언(`navigation.SIDEBAR_GROUPS`)을 부르지 않고 값만 옮긴다 — 화면이 선언과 같은지 따로 보는
# 확인이라 선언에서 꺼내면 둘이 함께 틀려도 「같음」이다. 테스트가 선언과 같은지 본다.
SIDEBAR_GROUP_BOXES: Final[tuple[tuple[str, str, int], ...]] = (
    ("static_capa", "Static Capa", 4),
    ("execution_management", "실행 관리", 8),
    ("dynamic_capa", "Dynamic Capa", 1),
)
# 좁게 끈 사이드바 폭(px). Streamlit 1.63 이 끌어 주는 가장 좁은 폭이다(200~600px) — 이 폭에서도
# 그룹 상자 제목은 한 줄이고 넘치면 말줄임이다(2026-10-17 사용자 결정). 선 폭을 함께 적어 두어
# 이 값과 다르면 측정이 틀어진 것을 안다.
SIDEBAR_NARROW_WIDTH_PX: Final = 200
# 사이드바 앱 이름 라벨을 기본 폭 다음에 다시 재는 좁은 폭(px). 머리칸은 사이드바 − 55px 다
# (`intro_summary._LABEL_CSS`). 280 은 Summary 단추를 빼는 문턱(머리칸 222px — 사이드바 277px)
# 바로 위 — 단추가 다 서거나 둘째 줄로 통째로 빠져야 한다. 236 은 머리칸이 글꼴을 줄이는
# 문턱(190px) 바로 아래 — 줄인 두 줄이 다 보여야 한다. 마지막 가장 좁은 폭은 넓은 본문 글꼴이면
# 줄마다 말줄임으로 끝나는 것까지 정한 모양이라 말줄임은 세기만 하고, 말줄임 없이 잘리거나 단추가
# 반쯤 보이면 잘림이다.
LABEL_NARROW_WIDTHS_PX: Final = (280, 236, SIDEBAR_NARROW_WIDTH_PX)
# 가용설비 현황 「Static 대비 일정」 탭의 분류별 내역 9행 비교 시트(`availability_sheet_keys`·
# `availability_gap_panel`·`availability_sheet_canvas`). 앱 모듈을 부르지 않고 값만 옮긴다 — 화면이
# 정한 9행과 같은지 따로 보는 확인이라 앱에서 라벨을 꺼내면 둘이 함께 틀려도 「같음」이다. 테스트가
# 앱과 같은지 본다.
GAP_TAB: Final = "Static 대비 일정"
# 가용설비 현황 두 탭 개편(2026-10-24 사용자 결정) — 바깥 탭 둘(① 설비 마스터 ② Summary), Summary
# 안쪽 탭 둘(라벨 글자는 개편 전 그대로), 머리 「설정」 팝업(공정별 Cut-off), 필요 단축 일정 머리
# 「Qual 마감 계산기」 팝업, 시나리오 관리 「관리할 시나리오」 전환의 설비 시나리오 구획. 앱 모듈을
# 부르지 않고 값만 옮긴다(테스트가 앱과 같은지 본다).
EQUIPMENT_MASTER_TAB: Final = "설비 마스터"
EQUIPMENT_SUMMARY_TAB: Final = "Summary"
EQUIPMENT_SUMMARY_TABS: Final = ("Main", GAP_TAB)
# 개편 전 바깥 탭 이름 — 화면에 남았는지 센다.
EQUIPMENT_OLD_TABS: Final = ("RawData", "Preference", "Qual 마감 계산기", "설비 시나리오")
# 바깥 탭 묶음·Summary 안쪽 탭 묶음의 `st.tabs` key(`st-key-<key>` 칸) — 제 탭만 센다.
EQUIPMENT_TAB_KEY: Final = "equipment_active_tab"
EQUIPMENT_SUMMARY_TAB_KEY: Final = "equipment_summary_tab"
EQUIPMENT_SETTINGS_BUTTON_KEY: Final = "equipment_settings_open_v1"
EQUIPMENT_SETTINGS_TITLE: Final = "설정"
CUTOFF_EDITOR_ANCHOR: Final = "Cutoff일수"
QUAL_CALCULATOR_BUTTON_KEY: Final = "required_shortening_qual_calculator_v1"
QUAL_CALCULATOR_TITLE: Final = "Qual 마감 계산기"
QUAL_CALCULATOR_KPIS: Final = (
    "마감 낸 호기",
    "가장 이른 마감",
    "이미 지난 마감",
    "목표 대비 부족 달",
)
SCENARIO_KIND_KEY: Final = "scenario_management_kind_v1"
SCENARIO_KINDS: Final = ("시뮬레이션 시나리오", "설비 시나리오")
# 설비 시나리오 구획의 시나리오 표 머리 칸(`equipment_scenario_management.scenario_rows`).
EQUIPMENT_SCENARIO_TABLE_ANCHOR: Final = "설비 시나리오"
# 탭 안 두 전환(`st.segmented_control`)의 위젯 key 와 시트를 여는 선택지.
GAP_RESULT_VIEW_KEY: Final = "equipment_gap_result_view_v1"
GAP_SHEET_VIEW: Final = "분류별 내역"
GAP_DETAIL_MODE_KEY: Final = "equipment_gap_detail_mode_v2"
GAP_SHEET_MODE: Final = "시트"
# 월 그림(칸 선택)·라벨 그림·월 칸 스크롤 상자·근거 카드의 컨테이너 key.
GAP_SHEET_KEYS: Final[dict[str, str]] = {
    "chart": "equipment_gap_sheet_chart",
    "labels": "equipment_gap_sheet_labels",
    "scroll": "equipment_gap_sheet_canvas_scroll",
    "evidence": "equipment_gap_sheet_evidence",
}
# 닫힌 근거 카드의 안내 글(같은 칸을 다시 누르면 이 글로 돌아온다).
GAP_SHEET_CLOSED_TEXT: Final = "칸을 누르면 근거가 여기에 뜹니다"
# 위에서 아래로 그린 값 행 아홉 — (구획 제목, 행 라벨).
_GAP_STATIC_TITLE: Final = "Static · 기준정보"
_GAP_SCHEDULE_TITLE: Final = "설비 일정 기준"
_GAP_GAP_TITLE: Final = "GAP (설비 일정 − Static)"
GAP_SHEET_ROWS: Final[tuple[tuple[str, str], ...]] = (
    (_GAP_STATIC_TITLE, "보유"),
    (_GAP_STATIC_TITLE, "대여"),
    (_GAP_STATIC_TITLE, "가용"),
    (_GAP_SCHEDULE_TITLE, "보유"),
    (_GAP_SCHEDULE_TITLE, "대여 (비가동)"),
    (_GAP_SCHEDULE_TITLE, "가용"),
    (_GAP_GAP_TITLE, "보유"),
    (_GAP_GAP_TITLE, "대여"),
    (_GAP_GAP_TITLE, "가용"),
)
# 누를 설비 일정 기준 칸의 행 id(표적 `customdata[1]`)와 라벨 — 먼저 대여(비가동)가 0 아닌 칸(근거
# 표가 비가동이 깎은 호기 줄이다), 없으면 값이 있는 가용 칸.
GAP_SHEET_SCHEDULE_CELLS: Final[tuple[tuple[str, str], ...]] = (
    ("sched:lent", "대여 (비가동)"),
    ("sched:available", "가용"),
)


# ---------------------------------------------------------------------------------- 경로

# 경로 옵션(옵션 이름, argparse 속성).
_PATH_OPTIONS: Final = (
    ("--output", "output"),
    ("--shots", "shots"),
    ("--playwright-dir", "playwright_dir"),
)


def _device_or_unc(text: str) -> bool:
    """`\\\\?\\…`·`\\\\.\\…`·`\\\\localhost\\C$\\…` 같은 장치·UNC 꼴인가."""
    return text.startswith(("\\\\", "//"))


def _stream_or_link(path: Path) -> bool:
    """Windows 대체 데이터 스트림(`파일:스트림`) 꼴이거나, 이미 있는 파일인데 하드 링크가 둘
    이상인가.

    둘 다 저장소 밖 이름으로 저장소 안 파일을 가리킬 수 있다 — 스트림은 그 파일에 붙고, 하드 링크는
    같은 파일이다. 어느 저장소 파일과 이어졌는지 다 찾을 수 없으니 그 꼴이면 거절한다.
    """
    if sys.platform == "win32" and ":" in os.path.splitdrive(str(path))[1]:
        return True
    try:
        return path.is_file() and path.stat().st_nlink > 1
    except OSError:
        return False


def inside_repository(path: Path, root: Path = PROJECT_ROOT) -> bool:
    """거절할 경로인가 — 저장소 안(루트 포함)이거나 장치·UNC 꼴.

    장치·UNC 꼴은 앞머리가 다른 드라이브처럼 보여 문자열 비교를 빠져나가므로
    (`\\\\?\\C:\\<저장소>`, `\\\\localhost\\C$\\<저장소>`) 어디를 가리키든 거절한다 — 저장소 밖이면
    드라이브 경로로 주면 된다. 그 밖에는 ① 정규화한 문자열로 견주고(아직 없는 경로) ② 가장 깊은 있는
    조상과 그 위 조상들을 `os.path.samefile` 로 저장소 루트와 견준다(드라이브 별칭·연결 폴더).
    Windows 는 대소문자를 가리지 않으므로 `normcase` 로 견준다. `~` 는 풀지 않는다 — 옵션 값은
    `refused_paths` 가 한 번 풀어 둔 것을 쓰므로 검사와 쓰기가 같은 경로를 본다.
    """
    if _device_or_unc(str(path)):
        return True
    resolved = path.resolve()
    target = os.path.normcase(os.path.abspath(resolved))
    base = os.path.normcase(os.path.abspath(root.resolve()))
    if target == base or target.startswith(base.rstrip("\\/") + os.sep):
        return True
    try:
        existing = resolved
        while not existing.exists() and existing != existing.parent:
            existing = existing.parent
        candidates = (existing, *existing.parents)
    except OSError:
        return False
    for candidate in candidates:
        try:
            if os.path.samefile(candidate, root):
                return True
        except OSError:
            continue
    return False


def refused_paths(args: argparse.Namespace, root: Path = PROJECT_ROOT) -> list[str]:
    """경로 옵션을 한 번 정규화하고(`expanduser().resolve()`) 거절할 옵션 이름을 돌려준다.

    정규화한 값을 `args` 에 다시 넣는다 — 검사·폴더 만들기·쓰기·Playwright 가 모두 그 값을 쓴다
    (`~\\out.md` 를 검사할 때만 풀고 쓸 때는 글자 그대로 쓰면
    `<작업 폴더>\\~\\out.md` 가 된다). 경로 자체는 찍지 않는다.
    """
    refused: list[str] = []
    for flag, name in _PATH_OPTIONS:
        raw = getattr(args, name)
        if raw is None:
            continue
        if _device_or_unc(str(raw)) or _stream_or_link(Path(raw)):
            refused.append(flag)
            continue
        try:
            value = Path(raw).expanduser().resolve()
        except (OSError, RuntimeError):
            refused.append(flag)
            continue
        if _device_or_unc(str(value)) or _stream_or_link(value) or inside_repository(value, root):
            refused.append(flag)
            continue
        setattr(args, name, value)
    return refused


# ---------------------------------------------------------------------------------- 준비


def load_playwright(directory: Path) -> Any | None:
    """`playwright.sync_api` 모듈. 없으면 None.

    폴더는 `sys.path` **끝**에 붙인다 — `--target` 설치는 `typing_extensions` 같은 공용 패키지도
    함께 깔아서, 앞에 두면 이 저장소의 의존성을 가린다.
    """
    if not directory.is_dir():
        return None
    entry = str(directory.resolve())
    if entry not in sys.path:
        sys.path.append(entry)
    try:
        return importlib.import_module("playwright.sync_api")
    except ImportError:
        return None


# DuckDB 잠금 오류의 고정 문구. 「lock」 부분 문자열로는 가리지 않는다 — 깨진 파일 문구의
# 「… in block at location …」 과 경로 속 글자에도 걸린다.
_LOCK_PHRASES: Final = ("Could not set lock on file", "Conflicting lock")
# Windows 공유·잠금 위반(`ERROR_SHARING_VIOLATION`·`ERROR_LOCK_VIOLATION`).
_SHARING_ERRORS: Final = (32, 33)


def _sharing_violation(path: Path) -> bool:
    """Windows: 그 파일을 공유 셋 다 허락하고 열어 공유·잠금 위반이 나는가 — 다른 프로세스가 쥐었다.

    열리거나 다른 오류(액세스 거부·디렉터리 등)면 잠금이 아니다.
    """
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    generic_read, share_all, open_existing, normal = 0x80000000, 0x1 | 0x2 | 0x4, 3, 0x80
    handle = kernel32.CreateFileW(
        str(path), generic_read, share_all, None, open_existing, normal, None
    )
    if handle is None or handle == wintypes.HANDLE(-1).value:
        return ctypes.get_last_error() in _SHARING_ERRORS
    kernel32.CloseHandle(wintypes.HANDLE(handle))
    return False


def is_lock_error(exc: BaseException, path: Path | None = None) -> bool:
    """DuckDB 의 잠금 오류인가 — 다른 프로세스가 파일을 쥐었다.

    쥔 프로세스(`(PID n)`)를 적거나 DuckDB 잠금 고정 문구면 잠금이다. Windows 는 가끔 그것 없이
    「Cannot open file …」 만 주는데 액세스 거부·디렉터리도 같은 꼴이라, 경로를 알면 그 파일을 직접
    열어 공유 위반인지 본다. 그 밖(깨진 파일 등)은 잠금이 아니다 — 사용자 앱 탓이 아니다.
    """
    if not isinstance(exc, duckdb.IOException):
        return False
    if lock_holder_pid(exc) is not None:
        return True
    text = str(exc)
    if any(phrase in text for phrase in _LOCK_PHRASES):
        return True
    return path is not None and "Cannot open file" in text and _sharing_violation(path)


def locked_databases(
    paths: Sequence[Path], *, connect: Callable[..., Any] = duckdb.connect
) -> list[Path]:
    """다른 프로세스가 잡고 있는 DB. DuckDB 는 프로세스 배타 잠금이라 `read_only` 로도 못 연다.

    없는 파일은 건너뛴다(앱이 처음 열 때 만든다). 연 연결은 바로 닫는다 — 띄울 앱이 열어야 한다.
    잠금이 아닌 오류(깨진 파일·액세스 거부 등)는 그대로 올린다 — 사용자 앱 탓이 아니다.
    """
    locked: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        try:
            connection = connect(str(path), read_only=True)
        except duckdb.IOException as exc:
            if not is_lock_error(exc, path):
                raise
            locked.append(path)
            continue
        connection.close()
    return locked


def applied_versions(path: Path, table: str) -> frozenset[int]:
    """그 DB 에 걸린 마이그레이션 번호. 파일·표가 없으면 빈 집합."""
    if not path.exists():
        return frozenset()
    with closing(duckdb.connect(str(path), read_only=True)) as connection:
        try:
            rows = connection.execute(f"SELECT version FROM {table}").fetchall()
        except duckdb.CatalogException:
            return frozenset()
    return frozenset(int(row[0]) for row in rows)


# (DB, 적용 기록 표, 코드의 마이그레이션 번호)
def migration_targets() -> tuple[tuple[Path, str, frozenset[int]], ...]:
    return (
        (DUCKDB_PATH, "app_meta.schema_migration", frozenset(m.version for m in load_migrations())),
        (
            EQUIPMENT_DUCKDB_PATH,
            "equipment_meta.schema_migration",
            frozenset(m.version for m in load_equipment_migrations()),
        ),
    )


# `streamlit run … app.py` 꼴의 명령줄. 런북의 사람 규칙(「명령줄에 app.py 가 있으면 사용자
# 앱」)과 같다.
_APP_COMMAND = re.compile(r"streamlit.*\brun\b.*\bapp\.py\b", re.IGNORECASE)
# 그 명령줄을 돌리는 프로그램. 셸(`bash -c "… streamlit run app.py …"`)이나 그 글자를 찾는 명령은
# 앱이 아니다 — 파이썬·streamlit 실행 파일만 센다.
_APP_PROGRAM = re.compile(r"(python[\d.]*w?|streamlit)(\.exe)?", re.IGNORECASE)
# Windows 는 다른 프로세스의 작업 폴더를 볼 수 없어 명령줄만 읽는다(venv 의 python.exe 는 본
# 해석기를 자식으로 띄우므로 앱 하나가 두 줄로 나온다 — 하나라도 맞으면 된다). 여러 줄 명령줄은
# 한 줄로 접는다. PowerShell 의 기본 출력은 콘솔 코드페이지(cp949)라 한글 경로가 깨지므로
# UTF-8 로 내보내게 한다.
_WINDOWS_PROCESS_QUERY = (
    "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*streamlit*' } | "
    r"ForEach-Object { $_.CommandLine -replace '\s+', ' ' }"
)


def _program(command_line: str) -> str:
    """명령줄 첫 낱말의 파일 이름(따옴표 경로 포함)."""
    text = command_line.strip()
    if text.startswith('"'):
        end = text.find('"', 1)
        first = text[1:end] if end > 0 else text[1:]
    else:
        first = text.split(maxsplit=1)[0] if text else ""
    return re.split(r"[\\/]", first)[-1]


def is_app_command(command_line: str) -> bool:
    """파이썬·streamlit 이 `streamlit run … app.py` 를 돌리는 명령줄인가."""
    return bool(
        _APP_PROGRAM.fullmatch(_program(command_line)) and _APP_COMMAND.search(command_line)
    )


def _same_app(command_line: str, cwd: str | None, root: Path) -> bool:
    """그 명령줄의 `app.py` 가 이 저장소의 것인가. 작업 폴더를 모르면 같다고 본다(보수적으로)."""
    target = os.path.normcase(str((root / "app.py").resolve()))
    for token in re.split(r"[\s\"']+", command_line):
        if not token or Path(token).name.lower() != "app.py":
            continue
        candidate = Path(token)
        if not candidate.is_absolute():
            if cwd is None:
                return True
            candidate = Path(cwd) / candidate
        if os.path.normcase(str(candidate.resolve())) == target:
            return True
    return False


def _proc_commands() -> list[tuple[str, str | None]]:
    """Linux `/proc` 의 (명령줄, 작업 폴더). 남의 프로세스라 작업 폴더를 못 읽으면 None."""
    found: list[tuple[str, str | None]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        command = raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
        if not is_app_command(command):
            continue
        try:
            cwd: str | None = os.readlink(entry / "cwd")
        except OSError:
            cwd = None
        found.append((command, cwd))
    return found


def _windows_commands() -> list[tuple[str, str | None]]:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _WINDOWS_PROCESS_QUERY],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=True,
    )
    return [(line.strip(), None) for line in completed.stdout.splitlines() if line.strip()]


def running_app_count(
    root: Path = PROJECT_ROOT,
    *,
    list_commands: Callable[[], list[tuple[str, str | None]]] | None = None,
) -> int | None:
    """이 저장소의 앱으로 보이는 다른 프로세스 수. 살피지 못하면 None.

    DB 잠금만으로는 모자란다 — 앱은 rerun 동안만 DB 를 쥐므로(`_sql_helpers.pinned_connections`)
    가만히 떠 있는 사용자 앱은 잠금 확인을 지나친다. 그 사이 사용자가 누르면 그쪽 화면이 잠금 오류로
    선다. 이 스크립트가 띄울 앱보다 **먼저** 본다(제 자식을 세지 않게).
    """
    if list_commands is None:
        list_commands = _windows_commands if sys.platform == "win32" else _proc_commands
    try:
        commands = list_commands()
    except (OSError, subprocess.SubprocessError):
        return None
    return sum(
        1 for command, cwd in commands if is_app_command(command) and _same_app(command, cwd, root)
    )


def port_in_use(port: int, host: str = APP_ADDRESS) -> bool:
    """그 포트에 누가 듣고 있는가. 앱은 포트를 적어 띄우므로 그 포트를 이미 누가 쥐고 있으면
    「not available」 로 멈추고, 그 포트의 health 는 먼저 떠 있던 남의 앱이 답해 엉뚱한 앱을
    재게 되므로 띄우기 전에 막는다."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1.0)
        return probe.connect_ex((host, port)) == 0


def health_ok(url: str) -> bool:
    """`/_stcore/health` 가 200 인가. 사내 프록시 환경변수를 타지 않게 프록시 없이 묻는다."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=2.0) as response:
            return int(response.status) == 200
    except (OSError, ValueError):
        return False


def applied_stamp(path: Path = DEPLOY_STATE_PATH) -> str:
    """적용 기록의 배포 번호(`YYYYMMDDHHMM`). 그 밖의 글자는 옮기지 않는다."""
    try:
        stamp = json.loads(path.read_text(encoding="utf-8")).get("stamp")
    except (OSError, ValueError, AttributeError):
        return "적용 기록 없음"
    if isinstance(stamp, str) and re.fullmatch(r"\d{12}", stamp):
        return f"적용 배포 `{stamp}`"
    return "적용 기록 꼴 다름"


# ---------------------------------------------------------------------------------- 앱 수명


class AppStartError(RuntimeError):
    """띄운 앱이 서지 않았다. 문구에는 수와 고정 글자만 둔다."""


class Process(Protocol):
    """`subprocess.Popen` 에서 쓰는 만큼. 테스트가 가짜를 넣는다."""

    def poll(self) -> int | None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def send_signal(self, sig: int) -> None: ...


class ConsoleCounter:
    """확인용 앱의 콘솔 출력(stdout · stderr 를 한 파이프로)을 읽으며 정한 글이 든 줄 수만 센다.

    줄은 세고 버린다 — 파일에도 쓰지 않는다. 경고 · 예외 문구에 이름이 실릴 수 있고, 스크립트가
    강제로 끝나도(사내 백그라운드 30분) 남는 것이 없어야 한다. 파이프를 읽지 않으면 앱이 쓰다가
    막히므로 읽기는 앱이 끝나 파이프가 닫힐 때까지 이어 간다(배경 스레드 하나 — 데몬)."""

    def __init__(self, needles: Sequence[str]) -> None:
        self._counts = dict.fromkeys(needles, 0)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def feed(self, line: bytes) -> None:
        text = line.decode("utf-8", "replace")
        with self._lock:
            for needle in self._counts:
                if needle in text:
                    self._counts[needle] += 1

    def count(self, needle: str) -> int | None:
        """`needle` 이 든 줄 수. 세기로 정하지 않은 글이면 None."""
        with self._lock:
            return self._counts.get(needle)

    def attach(self, stream: IO[bytes] | None) -> None:
        """그 파이프를 끝까지 읽는 스레드를 세운다. 파이프가 없으면(가짜 프로세스) 그냥 둔다."""
        if stream is None:
            return

        def drain() -> None:
            try:
                for line in iter(stream.readline, b""):
                    self.feed(line)
            except (OSError, ValueError):
                return

        self._thread = threading.Thread(target=drain, name="capa-screens-console", daemon=True)
        self._thread.start()

    def join(self, timeout: float) -> None:
        if self._thread is not None:
            self._thread.join(timeout)


def app_command(port: int) -> list[str]:
    """확인용 앱 명령. 이 PC 안에서만 듣는다(`--server.address`)."""
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.address",
        APP_ADDRESS,
        "--server.port",
        str(port),
        "--server.headless",
        "true",
        "--server.fileWatcherType",
        "none",
        "--browser.gatherUsageStats",
        "false",
    ]


# 공식버전 자동 갱신 예약의 실행 줄 허락(`capa_simulation.auto_update_scheduler.ENV_VAR`). 확인용
# 자식 앱에는 넘기지 않는다 — 사용자 앱과 같은 DB 로 예약 회차를 돌려 시나리오를 등록·발행하면 안
# 된다.
AUTO_UPDATE_ENV_VAR: Final = "CAPA_AUTO_OFFICIAL_UPDATE"


def app_environment(root: Path, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """자식 앱의 환경 — `PYTHONPATH` 맨 앞에 이 저장소의 `src`, 자동 갱신 예약 허락은 뺀다.

    editable 설치가 다른 작업 폴더(예: 본 저장소)를 가리켜도 자식이 이 저장소의 코드와 DB 를 쓴다
    (설정의 DB 경로는 `settings.py` 가 놓인 저장소에서 나온다). 사내는 이미 그렇다. 사용자 앱을 띄운
    창에서 이 스크립트를 돌려도 자식은 예약 스레드를 세우지 않는다(`AUTO_UPDATE_ENV_VAR`).
    """
    env = dict(os.environ if base is None else base)
    env.pop(AUTO_UPDATE_ENV_VAR, None)
    source = str(root / "src")
    rest = [part for part in env.get("PYTHONPATH", "").split(os.pathsep) if part and part != source]
    env["PYTHONPATH"] = os.pathsep.join([source, *rest])
    return env


_CHILD_PATHS_CODE = (
    "import capa_simulation.settings as s; "
    "print(s.DUCKDB_PATH.resolve()); print(s.EQUIPMENT_DUCKDB_PATH.resolve())"
)


def child_database_paths(env: Mapping[str, str], root: Path) -> tuple[Path, Path]:
    """그 환경으로 띄운 파이썬이 여는 두 DB 경로. 확인용 앱이 같은 DB 를 볼지 띄우기 전에 견준다."""
    completed = subprocess.run(
        [sys.executable, "-c", _CHILD_PATHS_CODE],
        cwd=str(root),
        env=dict(env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=True,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return Path(lines[-2]), Path(lines[-1])


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


# Windows Job Object — 확인용 앱을 이 스크립트의 수명에 묶는다. 스크립트가 강제로 끝나면(30분 제한·
# 작업 관리자) `finally` 가 돌지 못해 앱이 남고, 다음 실행이 그것을 사용자 앱으로 본다. 잡의 마지막
# 핸들이 닫히면(스크립트가 어떻게 끝나든) 잡 안의 프로세스가 모두 끝난다. venv 의 python.exe 는 본
# 해석기를 자식으로 띄우므로 그 자식까지 잡에 들게 앱을 멈춘 채 만들어 잡에 넣은 뒤 깨운다.
_CREATE_SUSPENDED = 0x00000004
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


def _create_kill_on_close_job() -> int | None:
    """닫히면 안의 프로세스를 끝내는 잡 핸들. Windows 가 아니거나 만들지 못하면 None."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class _Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _Io(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_uint64)
            for name in ("Read", "Write", "Other", "ReadBytes", "WriteBytes", "OtherBytes")
        ]

    class _Extended(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _Basic),
            ("IoInfo", _Io),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = _Extended()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(
        wintypes.HANDLE(job),
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        kernel32.CloseHandle(wintypes.HANDLE(job))
        return None
    return int(job)


def _adopt_and_resume(job: int, process: Any) -> bool:
    """멈춘 채 만든 프로세스를 잡에 넣고 깨운다. 잡에 넣지 못했거나 깨우지 못하면 False — 부른 쪽이
    그 프로세스를 끝낸다(잡 밖에서 앱을 돌리지 않는다). 깨우기는 `ntdll.NtResumeProcess` 다(문서에
    없는 진입점이지만 널리 쓰이고 테스트가 실제로 돌린다)."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    handle = wintypes.HANDLE(int(process._handle))
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if not kernel32.AssignProcessToJobObject(wintypes.HANDLE(job), handle):
        return False
    ntdll = ctypes.WinDLL("ntdll")
    return int(ntdll.NtResumeProcess(handle)) == 0


def _close_job(job: int) -> None:
    """잡 핸들을 닫는다 — 안에 남은 프로세스(예: venv 런처의 자식)가 함께 끝난다."""
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    ctypes.WinDLL("kernel32").CloseHandle(wintypes.HANDLE(job))


def _die_with_parent() -> None:
    """Linux: 이 스크립트가 끝나면 자식 앱도 SIGTERM 을 받는다(`PR_SET_PDEATHSIG`). 자식에서 돈다.

    걸지 못하면 예외를 올린다 — `Popen` 이 `SubprocessError` 로 끝나 앱이 묶이지 않은 채 돌지
    않는다.
    """
    import ctypes

    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM) != 0:
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_PDEATHSIG)")


class StreamlitApp:
    """확인용 앱 한 벌. `with` 를 나가면(예외여도) 끈다.

    띄우기 전에 그 환경의 파이썬이 여는 DB 가 사전 확인이 본 DB 와 같은지 견준다. 끌 때는 먼저
    Streamlit 이 받는 신호(Windows `CTRL_BREAK`, 그 밖 `SIGTERM`)로 서버를 멈춰 DuckDB 연결이 닫히게
    하고, `STOP_TIMEOUT_SECONDS` 안에 안 끝나면 죽인다. 스크립트가 강제로 끝나도 앱이 남지 않게
    Windows 는 Job Object, Linux 는 `PR_SET_PDEATHSIG` 로 묶는다(`contain`).
    """

    def __init__(
        self,
        port: int,
        *,
        root: Path = PROJECT_ROOT,
        expected_paths: tuple[Path, Path] = (DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH),
        popen: Callable[..., Process] = subprocess.Popen,
        probe: Callable[[str], bool] = health_ok,
        port_probe: Callable[[int], bool] = port_in_use,
        path_probe: Callable[[Mapping[str, str], Path], tuple[Path, Path]] = child_database_paths,
        start_timeout: float = START_TIMEOUT_SECONDS,
        contain: bool = True,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        console: ConsoleCounter | None = None,
    ) -> None:
        self.port = port
        self.root = root
        self.base_url = f"http://{APP_ADDRESS}:{port}/"
        self.process: Process | None = None
        self.started_seconds = 0.0
        self.port_released = True
        self.contained = False
        self._expected_paths = expected_paths
        self._popen = popen
        self._probe = probe
        self._port_probe = port_probe
        self._path_probe = path_probe
        self._start_timeout = start_timeout
        self._contain = contain
        self._job: int | None = None
        self._clock = clock
        self._sleep = sleep
        self._console = console

    def __enter__(self) -> StreamlitApp:
        began = self._clock()
        env = app_environment(self.root)
        try:
            seen = self._path_probe(env, self.root)
        except (OSError, subprocess.SubprocessError, IndexError) as exc:
            raise AppStartError(
                f"확인용 앱의 DB 경로를 읽지 못했습니다({type(exc).__name__})"
            ) from None
        if not all(_same_path(a, b) for a, b in zip(seen, self._expected_paths, strict=True)):
            raise AppStartError("확인용 앱이 사전 확인과 다른 DB 를 엽니다 — PYTHONPATH 를 봅니다")
        options: dict[str, Any] = {
            "cwd": str(self.root),
            "env": env,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if self._console is not None:
            # 콘솔 출력은 파이프 하나로 받아 줄 수만 센다(`ConsoleCounter`). 버퍼에 머물면 센 때
            # 아직 안 왔을 수 있다.
            env["PYTHONUNBUFFERED"] = "1"
            options["stdout"] = subprocess.PIPE
            options["stderr"] = subprocess.STDOUT
        if sys.platform == "win32":
            # `CTRL_BREAK` 는 프로세스 묶음 단위로 간다 — 자식을 따로 묶어야 이 스크립트가
            # 받지 않는다.
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            if self._contain:
                self._job = _create_kill_on_close_job()
                if self._job is None:
                    raise AppStartError("확인용 앱을 Job 에 넣지 못했습니다(잡을 만들지 못함)")
                options["creationflags"] |= _CREATE_SUSPENDED
        elif self._contain and sys.platform.startswith("linux"):
            options["preexec_fn"] = _die_with_parent
        try:
            self.process = self._popen(app_command(self.port), **options)
        except (OSError, subprocess.SubprocessError) as exc:
            self._release_job()
            raise AppStartError(f"확인용 앱을 띄우지 못했습니다({type(exc).__name__})") from None
        if self._console is not None:
            self._console.attach(getattr(self.process, "stdout", None))
        if self._job is not None:
            # 멈춘 채 만든 자식은 잡에 들어가 깨어날 때까지 아무 일도 하지 않는다. 그 사이 무엇이
            # 실패하든 그 자식을 끈다 — 잡 밖에서 앱을 돌리지 않는다.
            try:
                adopted = _adopt_and_resume(self._job, self.process)
            except BaseException:
                self.process.kill()
                self.stop()
                raise
            if not adopted:
                self.process.kill()
                self.stop()
                raise AppStartError("확인용 앱을 Job 에 넣지 못했습니다")
            self.contained = True
        elif self._contain and sys.platform.startswith("linux"):
            # `_die_with_parent` 가 실패했으면 `Popen` 이 위에서 이미 끝났다.
            self.contained = True
        try:
            self._wait_ready(began)
        except BaseException:
            self.stop()
            raise
        self.started_seconds = self._clock() - began
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop()

    def _wait_ready(self, began: float) -> None:
        assert self.process is not None
        health = f"{self.base_url}_stcore/health"
        while True:
            code = self.process.poll()
            if code is not None:
                raise AppStartError(f"앱이 뜨다가 끝났습니다(종료 코드 {code})")
            if self._probe(health):
                return
            if self._clock() - began > self._start_timeout:
                raise AppStartError(f"앱이 {self._start_timeout:.0f}초 안에 답하지 않았습니다")
            self._sleep(1.0)

    def _release_job(self) -> None:
        if self._job is not None:
            _close_job(self._job)
            self._job = None

    def stop(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            try:
                if sys.platform == "win32":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.terminate()
            except OSError:
                # 콘솔이 없는 셸에서는 `CTRL_BREAK` 를 보낼 수 없다 — 바로 끊는다.
                process.terminate()
            try:
                process.wait(timeout=STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=STOP_TIMEOUT_SECONDS)
        # 잡을 닫아 남은 자식(venv 런처가 띄운 본 해석기 등)까지 끝낸다.
        self._release_job()
        if process is None:
            return
        if self._console is not None:
            # 앱이 끝나면 파이프가 닫혀 읽기 스레드가 끝난다(데몬 — 남아도 스크립트를 잡지 않는다).
            self._console.join(timeout=STOP_TIMEOUT_SECONDS)
        # 띄운 쪽이 끝나도 자식이 포트를 잠깐 더 쥘 수 있어, 포트가 비는 것까지 본다.
        began = self._clock()
        while self._port_probe(self.port):
            if self._clock() - began > STOP_TIMEOUT_SECONDS:
                self.port_released = False
                break
            self._sleep(0.5)


# ---------------------------------------------------------------------------------- 공통 뼈대

_RUNNING_JS = """() => !!document.querySelector('[data-testid="stStatusWidget"]')"""
# 화면 탭 줄의 보이는 탭 — 지금 탭인가·닫기 단추가 있는가·고정인가. 이름은 찍지 않는다.
_PAGE_TABS_JS = """(key) => {
  const host = document.querySelector('.st-key-' + key);
  const holder = host && [...host.querySelectorAll('*')].find((e) => e.shadowRoot);
  const root = holder && holder.shadowRoot;
  if (!root) return null;
  return [...root.querySelectorAll('.capa-tabs-item')].filter((li) => !li.hidden).map((li) => ({
    active: li.querySelector('.capa-tabs-tab').getAttribute('aria-current') === 'page',
    closable: !li.querySelector('.capa-tabs-x').hidden,
    pinned: li.classList.contains('is-pinned'),
  }));
}"""
_PATH_JS = "() => location.pathname"
_INTRO_STATE_JS = """(id) => {
  const host = document.getElementById(id);
  if (!host) return "none";
  if (getComputedStyle(host).display === "none") return "hidden";
  const detail = host.shadowRoot && host.shadowRoot.querySelector(".btn.detail");
  return detail && !detail.disabled ? "ready" : "waiting";
}"""
_LISTBOX_OPEN_JS = """() => !!document.querySelector('[role="listbox"]')"""
# 사이드바 메뉴 링크 수와 본문의 오류 상자(`st.error`) 유무 — 부트스트랩 실패 화면을 가른다.
_APP_STATE_JS = """() => ({
  nav: document.querySelectorAll('[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]')
    .length,
  error: !!document.querySelector('[data-testid="stMain"] [data-testid="stAlertContentError"]'),
})"""
# 펼친 목록의 선택지 수. 긴 목록은 그린 것만 DOM 에 있어(가상화) 굴리며 센다. 글자는 밖으로
# 내지 않는다.
_COUNT_OPTIONS_JS = """async () => {
  const box = document.querySelector('[role="listbox"]');
  if (!box) return 0;
  const seen = new Set();
  const read = () => box.querySelectorAll('[role="option"]')
    .forEach((o) => seen.add(o.textContent));
  const scroller = [box, ...box.querySelectorAll("*")]
    .find((e) => e.scrollHeight > e.clientHeight + 1);
  read();
  if (scroller) {
    for (let step = 0; step < 200; step += 1) {
      const before = scroller.scrollTop;
      scroller.scrollTop += Math.max(40, scroller.clientHeight * 0.6);
      await new Promise((r) => setTimeout(r, 120));
      read();
      if (scroller.scrollTop === before) break;
    }
    scroller.scrollTop = 0;
  }
  return seen.size;
}"""
# 데이터 편집기·표(Glide)의 머리 칸. 그린 칸만 DOM 에 있어 가로로 굴리며 찾는다.
_FIND_COLUMN_JS = """async (root, header) => {
  const wanted = header.replace(/\\s+/g, " ").trim();
  const find = () => {
    const cell = [...root.querySelectorAll('[role="columnheader"]')].find(
      (h) => h.textContent.replace(/\\s+/g, " ").trim() === wanted);
    return cell ? Number(cell.getAttribute("aria-colindex")) : null;
  };
  let found = find();
  const scroller = root.querySelector(".dvn-scroller");
  if (found !== null || !scroller) return found;
  scroller.scrollLeft = 0;
  await new Promise((r) => setTimeout(r, 250));
  for (let step = 0; step < 200; step += 1) {
    found = find();
    if (found !== null) return found;
    const before = scroller.scrollLeft;
    scroller.scrollLeft += Math.max(80, scroller.clientWidth * 0.5);
    await new Promise((r) => setTimeout(r, 250));
    if (scroller.scrollLeft === before) return find();
  }
  return null;
}"""
# 표의 행을 위에서 아래로 굴리며 읽는다. 지금 가로 위치에 그려진 칸만 읽힌다 — 먼 칸은
# `column_index` 가 굴려 둔 뒤 부른다.
_GRID_ROWS_JS = """async (root, columns) => {
  const scroller = root.querySelector(".dvn-scroller");
  const rows = new Map();
  const read = () => root.querySelectorAll('[role="row"]').forEach((row) => {
    const cells = {};
    row.querySelectorAll('[role="gridcell"]').forEach((c) => {
      cells[c.getAttribute("aria-colindex")] = c.textContent.trim();
    });
    if (Object.keys(cells).length) {
      const picked = columns.map((i) => cells[String(i)] ?? null);
      rows.set(Number(row.getAttribute("aria-rowindex")), picked);
    }
  });
  if (scroller) scroller.scrollTop = 0;
  await new Promise((r) => setTimeout(r, 250));
  read();
  if (scroller) {
    for (let step = 0; step < 2000; step += 1) {
      const before = scroller.scrollTop;
      scroller.scrollTop += Math.max(60, scroller.clientHeight * 0.6);
      await new Promise((r) => setTimeout(r, 250));
      read();
      if (scroller.scrollTop === before) break;
    }
    scroller.scrollTop = 0;
  }
  return [...rows.entries()].sort((a, b) => a[0] - b[0]).map((e) => e[1]);
}"""
# 보이는 팝업(`st.dialog`). `document` 에서만 찾는다 — 입장 화면 무대(shadow root 안)도
# `role="dialog"` 라 shadow 를 뚫는 Playwright 로케이터는 그것까지 잡는다.
_FIND_DIALOGS = (
    """[...document.querySelectorAll('[role="dialog"]')]"""
    ".filter((d) => d.getBoundingClientRect().width > 0)"
)
_DIALOG_COUNT_JS = f"() => {_FIND_DIALOGS}.length"
# 팝업 제목(`st.dialog` 의 첫 인자). 앞의 아이콘 글자를 빼고 마크다운 칸만 읽는다.
_DIALOG_TITLE_JS = """(box) => {
  const title = box.querySelector('h2 [data-testid="stMarkdownContainer"]');
  return title ? title.innerText.trim() : "";
}"""


def _css_string(value: str) -> str:
    """CSS 속성 선택자의 따옴표 값. 한글을 `\\uXXXX` 로 바꾸면 CSS 는 그것을 못 읽는다."""
    return json.dumps(value, ensure_ascii=False)


def _overlay_closed(state: str) -> bool:
    """입장 화면·Summary 덮개가 걷혔는가(호스트가 숨었거나 아직 없다)."""
    return state in ("hidden", "none")


class Screen:
    """항목 함수가 쓰는 공통 뼈대. Playwright 페이지(`page`)를 감싼다.

    한 브라우저 세션 안에서 사이드바 링크로 옮겨 다닌다 — 주소로 가면 세션이 새로 서서 입장 화면을
    다시 넘겨야 한다.
    """

    def __init__(self, page: Any, base_url: str, *, shots: Path | None = None) -> None:
        self.page = page
        self.base_url = base_url
        self.shots = shots
        # 항목이 지금 하는 일(고정 글자). 항목이 예외로 끝나면 미기록 줄에 붙는다 — `step`.
        self.current_step: str | None = None
        # 확인용 앱의 콘솔 줄 세기(`_check` 가 단다). 항목은 정한 글이 든 줄 수만 본다
        # (`console_lines`) — 글은 어디에도 남지 않는다.
        self.console: ConsoleCounter | None = None

    def step(self, name: str) -> None:
        """항목 안의 단계 이름을 둔다. 예외로 끝나면 미기록 줄이 어느 기다림에서 멈췄는지 말한다
        (사내 리뷰 202610200720 — 페이더의 `TimeoutError` 가 어느 기다림인지 남지 않았다)."""
        self.current_step = name

    # -- 기다림

    def js(self, script: str, arg: object = None) -> Any:
        return self.page.evaluate(script, arg)

    def poll(
        self,
        read: Callable[[], Any],
        *,
        timeout: float,
        accept: Callable[[Any], bool] = bool,
        every: float = 0.25,
    ) -> Any:
        """`read()` 가 `accept` 를 넘을 때까지 읽는다. 시간이 다 되면 마지막 값을 돌려준다."""
        deadline = time.monotonic() + timeout
        while True:
            value = read()
            if accept(value) or time.monotonic() >= deadline:
                return value
            time.sleep(every)

    def wait_for(
        self, read: Callable[[], Any], *, timeout: float, accept: Callable[[Any], bool] = bool
    ) -> Any:
        """`poll` 과 같되 시간이 다 되면 `TimeoutError`."""
        value = self.poll(read, timeout=timeout, accept=accept)
        if not accept(value):
            raise TimeoutError("기다린 화면이 서지 않았다")
        return value

    def wait_stable(self, read: Callable[[], Any], *, timeout: float = 15.0) -> Any:
        """같은 값이 세 번 이어 읽힐 때까지(움직임이 끝날 때까지) 읽는다."""
        deadline = time.monotonic() + timeout
        last: Any = None
        same = 0
        while time.monotonic() < deadline:
            value = read()
            same = same + 1 if value == last and value is not None else 0
            if same >= 2:
                return value
            last = value
            time.sleep(0.25)
        raise TimeoutError("화면이 멈추지 않았다")

    def wait_idle(self, timeout: float = 90.0) -> None:
        """Streamlit 이 다 돌 때까지. 도는 표시가 1초 동안 없으면 끝난 것으로 본다."""
        time.sleep(0.3)
        deadline = time.monotonic() + timeout
        quiet = 0
        while time.monotonic() < deadline:
            quiet = 0 if self.js(_RUNNING_JS) else quiet + 1
            if quiet >= 4:
                return
            time.sleep(0.25)
        raise TimeoutError("앱이 계속 도는 중")

    # -- 입장·정리

    def intro_state(self) -> str:
        return str(self.js(_INTRO_STATE_JS, INTRO_HOST_ID))

    def _intro_state_through_reload(self) -> str:
        """첫 방문의 테마 스크립트가 화면을 한 번 새로 읽는다(`theme_toggle` 의 새로고침 표지).
        그 사이 `evaluate` 는 「실행 문맥이 사라졌다」로 끝나므로 그때는 「아직」으로 읽는다."""
        try:
            return self.intro_state()
        except Exception:  # noqa: BLE001 — 새로 읽는 중이다. 다음 회차에 다시 읽는다
            return "reloading"

    def enter(self, timeout: float = INTRO_TIMEOUT_SECONDS) -> float:
        """첫 화면을 열고 입장 화면의 `Detail` 로 들어간다. 걸린 초."""
        began = time.monotonic()
        try:
            self.page.goto(self.base_url, wait_until="domcontentloaded", timeout=timeout * 1000)
        except Exception:  # noqa: BLE001 — 첫 방문 새로고침이 이동을 끊을 수 있다. 아래가 기다린다
            pass
        # 같은 탭에서 이미 들어갔거나(세션 저장소의 표지) 입장 화면이 실패해 스스로 걷히면 덮개는
        # 숨은 채로 남는다 — 그때는 누를 것 없이 들어간 것이다.
        state = self.wait_for(
            self._intro_state_through_reload,
            timeout=timeout,
            accept=lambda state: state in ("ready", "hidden"),
        )
        if state == "hidden":
            # 숨은 채 생겨 곧 서는 호스트와 가르려고 잠깐 더 본다.
            state = self.poll(self.intro_state, timeout=2, accept=lambda state: state == "ready")
        if state == "ready":
            self.page.locator(f"#{INTRO_HOST_ID} .btn.detail").click()
        self.wait_for(self.intro_state, timeout=30, accept=_overlay_closed)
        self.wait_idle()
        return time.monotonic() - began

    def close_overlay(self) -> None:
        """Summary 덮개가 열려 있으면 닫는다. 여는 움직임 중에는 `Esc` 를 놓칠 수 있어 몇 번
        누르고, 그래도 서 있으면 머리 줄의 `Detail` 을 누른다(둘 다 같은 일을 한다)."""
        for _ in range(3):
            if _overlay_closed(self.intro_state()):
                return
            self.page.keyboard.press("Escape")
            if _overlay_closed(self.poll(self.intro_state, timeout=3, accept=_overlay_closed)):
                return
        detail = self.page.locator(f"#{INTRO_HOST_ID} .btn.detail")
        if detail.count() and detail.first.is_enabled():
            detail.first.click()
        self.wait_for(self.intro_state, timeout=15, accept=_overlay_closed)

    def app_problem(self, timeout: float = 15.0) -> str | None:
        """들어간 앱이 정상 화면인가. 부트스트랩이 실패하면(마이그레이션·DB 오류) 사이드바 메뉴 없이
        오류 상자만 선다 — 그 화면에서 항목을 돌리면 화면 결함으로 거짓 보고한다. 정상이면 None."""
        state = self.poll(
            lambda: self.js(_APP_STATE_JS), timeout=timeout, accept=lambda value: value["nav"] > 0
        )
        if state["nav"] > 0:
            return None
        return "앱 오류 화면 있음" if state["error"] else "사이드바 메뉴 없음"

    def settle(self) -> None:
        """항목 사이 정리 — 펼친 목록·팝업·덮개를 닫는다. 앞 항목이 중간에 끊겨도 다음 항목이 선다
        (열린 팝업은 뒤의 누름을 모두 가로챈다)."""
        if self.js(_LISTBOX_OPEN_JS):
            self.page.keyboard.press("Escape")
        if self.dialog_count():
            self.close_dialog()
        self.close_overlay()

    def shot(self, name: str) -> None:
        if self.shots is not None:
            self.page.screenshot(path=str(self.shots / f"{name}.png"))

    # -- 이동

    def path(self) -> str:
        """브라우저의 지금 주소 경로. `page.url` 은 Playwright 가 이동 사건으로 고쳐 두는 값이라
        `time.sleep` 으로 기다리는 동안에는 사건을 받지 못해 옛 주소에 머문다 — 링크마다 다시 누를
        때까지 10초씩 기다렸다(사내 리뷰 202610182227, 링크마다 약 72초). 페이지에 물어 읽는다."""
        return str(self.js(_PATH_JS))

    def page_tabs(self) -> list[dict[str, bool]]:
        """화면 탭 줄의 보이는 탭(`_PAGE_TABS_JS`). 탭 줄이 없으면 빈 목록."""
        return list(self.js(_PAGE_TABS_JS, PAGE_TABS_KEY) or [])

    def tab_item(self, index: int) -> Any:
        """화면 탭 줄의 `index` 번째 탭(그림자 DOM — Playwright CSS 가 뚫는다)."""
        return self.page.locator(f".st-key-{PAGE_TABS_KEY} .capa-tabs-item").nth(index)

    def make_tab_room(self) -> None:
        """탭이 상한(`PAGE_TABS_MAX`)이면 지금 탭이 아닌 닫을 수 있는 탭 하나를 닫는다.

        탭 줄은 상한을 넘는 화면을 열지 않는다(사이드바 링크 누름을 막고 알린다) — 항목들이 한
        세션에서 화면을 열 개 넘게 옮겨 다니므로 사이드바 링크를 누르기 전에 자리를 비운다. 닫아도
        그 화면의 보기 조건은 남는다(탭 줄 규칙)."""
        tabs = self.page_tabs()
        if len(tabs) < PAGE_TABS_MAX:
            return
        index = next(
            (i for i, tab in enumerate(tabs) if tab["closable"] and not tab["active"]), None
        )
        if index is None:
            return
        item = self.tab_item(index)
        item.hover()
        item.locator(".capa-tabs-x").click()
        self.poll(lambda: len(self.page_tabs()), timeout=10, accept=lambda n: n < len(tabs))
        self.wait_idle()

    def open_page(self, href_suffix: str) -> None:
        """사이드바 링크로 간다. 접힌 묶음(`details`) 안이면 묶음 머리부터 편다."""
        self.make_tab_room()
        link = self.page.locator(f'[data-testid="stSidebar"] a[href$="{href_suffix}"]').first

        def arrived() -> bool:
            return self.path().rstrip("/").endswith(href_suffix)

        if not link.is_visible():
            link.locator("xpath=ancestor::details[1]/summary").click()
            # 펴지는 동안 누른 링크는 이동하지 않는다 — 자리가 멈출 때까지 기다린다.
            self.wait_stable(link.bounding_box, timeout=10)
        for _ in range(3):
            link.click()
            if self.poll(arrived, timeout=10, accept=bool):
                break
        self.wait_for(arrived, timeout=5)
        self.wait_idle()

    def open_home(self) -> None:
        """HOME 으로 간다. 기본 페이지라 링크 주소 끝이 비어 `open_page` 로는 고를 수 없다 — HOME
        링크 칸(`HOME_LINK_KEY`)을 누른다. 이미 HOME 이면 누르지 않는다."""

        def arrived() -> bool:
            return self.path() in ("", "/")

        if not arrived():
            link = self.page.locator(f'[data-testid="stSidebar"] .st-key-{HOME_LINK_KEY} a').first
            for _ in range(3):
                link.click()
                if self.poll(arrived, timeout=10, accept=bool):
                    break
            self.wait_for(arrived, timeout=5)
        self.wait_idle()

    def open_space_overview(self) -> None:
        """`Space 현황` 을 FAB 전체(층 목록 표가 서는 화면)로 연다. 연 층은 위젯이 아니라 세션
        키라 다른 페이지를 거쳐 다시 와도 그 층 상세가 선다 — `space_drawer` 가 연 층에서
        `space_fader` 가 층 목록 표를 기다리다 첫 판 · 다시 돈 판 모두 `TimeoutError` 였다(사내
        리뷰 202610200720 발견 1). 경로 줄 `S.PKG FAB 전체` 가 보조 단추면(층이 열려 있다) 눌러
        FAB 로 돌아간다."""
        self.open_page(SPACE_PAGE)
        crumb = self.page.locator(f".st-key-{SPACE_FAB_CRUMB_KEY} button").first
        crumb.wait_for(state="visible", timeout=ACTION_TIMEOUT_MS)

        def at_fab() -> bool:
            return bool(crumb.get_attribute("data-testid") == "stBaseButton-primary")

        if not at_fab():
            crumb.click()
            self.wait_for(at_fab, timeout=30)
            self.wait_idle()

    def open_tab(self, name: str) -> None:
        """탭을 누른다. 탭 이름 앞의 아이콘 글자(`table_rows`)는 부분 일치로 넘긴다."""
        self.page.get_by_role("tab", name=name).first.click()
        self.wait_idle()

    def main_text(self) -> str:
        return str(
            self.js("""() => document.querySelector('[data-testid="stMain"]')?.innerText ?? "" """)
        )

    def sidebar_text(self) -> str:
        """사이드바의 보이는 글자. 판정에만 쓴다(팝업은 사이드바 밖에 그려진다)."""
        return str(
            self.js(
                """() => document.querySelector('[data-testid="stSidebar"]')?.innerText ?? "" """
            )
        )

    # -- 팝업(`st.dialog`)

    def dialog_count(self) -> int:
        return int(self.js(_DIALOG_COUNT_JS))

    def dialog_read(self, script: str, arg: object = None) -> Any:
        """보이는 팝업 요소에 `script`(`(box, arg) => …`)를 돌린 값. 팝업이 없으면 None."""
        wrapper = (
            f"(arg) => {{ const box = {_FIND_DIALOGS}[0]; "
            f"return box ? ({script})(box, arg) : null; }}"
        )
        return self.js(wrapper, arg)

    def dialog_title(self) -> str | None:
        """보이는 팝업의 제목. 판정에만 쓴다. 팝업이 없으면 None."""
        title = self.dialog_read(_DIALOG_TITLE_JS)
        return None if title is None else str(title)

    def open_dialog(self, selector: str, *, timeout: float = 30.0) -> None:
        """그 단추를 눌러 팝업이 보일 때까지 기다린다. 본문은 그 뒤에 차므로 항목이 따로
        기다린다."""
        self.page.locator(selector).first.click()
        self.wait_for(self.dialog_count, timeout=timeout, accept=lambda count: count > 0)

    def close_dialog(self, timeout: float = 10.0) -> bool:
        """열린 팝업을 `Esc` 로 닫는다 — 적용·불러오기·저장은 누르지 않는다. 닫혔으면 True.

        닫기는 `on_dismiss` 로 앱을 다시 돌리므로 그 회차가 끝날 때까지 기다린다.
        """
        for _ in range(2):
            if self.dialog_count() == 0:
                break
            self.page.keyboard.press("Escape")
            self.poll(self.dialog_count, timeout=timeout, accept=lambda count: count == 0)
        closed = self.dialog_count() == 0
        self.wait_idle()
        return closed

    # -- 위젯

    def selectbox(self, label: str) -> Any:
        return self.page.locator('[data-testid="stSelectbox"]').filter(
            has=self.page.locator(f"input[aria-label={_css_string(label)}]")
        )

    def selectbox_value(self, label: str) -> str | None:
        """선택 상자에 지금 보이는 값. 상자가 없으면 None. 값은 판정에만 쓴다."""
        box = self.selectbox(label)
        if box.count() == 0:
            return None
        return str(box.first.locator("input").input_value())

    def selectbox_option_count(self, label: str) -> int:
        """펼쳐 선택지 수를 세고 `Esc` 로 닫는다. 고르지 않는다."""
        field = self.selectbox(label).first.locator("input")
        field.click()
        self.wait_for(lambda: self.js(_LISTBOX_OPEN_JS), timeout=10)
        try:
            return int(self.js(_COUNT_OPTIONS_JS))
        finally:
            self.page.keyboard.press("Escape")

    def choose_by_typing(self, label: str, text: str) -> None:
        """선택 상자에 글자를 쳐서 고른다(긴 목록은 가상화라 누를 칸이 DOM 에 없을 수 있다)."""
        field = self.selectbox(label).first.locator("input")
        field.click()
        field.type(text, delay=20)
        self.page.keyboard.press("Enter")
        self.wait_idle()

    def switch(self, label: str, on: bool) -> bool:
        """`st.toggle` 을 켜거나 끈다. 숨은 input 대신 라벨을 누른다. 스위치가 없으면 False."""
        box = self.page.locator('[data-testid="stCheckbox"]').filter(
            has=self.page.locator(f"input[aria-label={_css_string(label)}]")
        )
        if box.count() == 0:
            return False
        if bool(box.first.locator("input").is_checked()) != on:
            box.first.locator("label").first.click()
            self.wait_idle()
        return True

    # -- 표(Glide)

    def grid_with_column(self, header: str, *, timeout: float = 30.0) -> tuple[Any, int]:
        """그 머리 칸이 있는 첫 표와 그 칸의 `aria-colindex`."""

        def find() -> tuple[Any, int] | None:
            grids = self.page.locator('[data-testid="stDataFrame"], [data-testid="stDataEditor"]')
            for index in range(grids.count()):
                grid = grids.nth(index)
                column = self.column_index(grid, header)
                if column is not None:
                    return grid, column
            return None

        found = self.wait_for(find, timeout=timeout, accept=lambda value: value is not None)
        grid, column = found
        return grid, int(column)

    def column_index(self, grid: Any, header: str) -> int | None:
        value = grid.evaluate(_FIND_COLUMN_JS, header)
        return None if value is None else int(value)

    def grid_rows(self, grid: Any, columns: Sequence[int]) -> list[list[str | None]]:
        """행마다 고른 칸의 글자(머리 행 제외). 판정에만 쓰고 결과에 옮기지 않는다."""
        rows = grid.evaluate(_GRID_ROWS_JS, list(columns))
        return [[None if cell is None else str(cell) for cell in row] for row in rows]


# ---------------------------------------------------------------------------------- 항목 실행


@dataclass(frozen=True)
class Item:
    """확인 항목 하나. `run` 은 결과 칸 글자(개수·있음/없음·같음/다름·px)를 돌려준다."""

    key: str
    title: str
    run: Callable[[Screen], str]
    writes: bool = False


@dataclass(frozen=True)
class Outcome:
    item: Item
    result: str
    seconds: float = 0.0

    @property
    def recorded(self) -> bool:
        return not (self.result.startswith(UNRECORDED) or self.result == SKIPPED_NO_PERMISSION)


def unrecorded(exc: BaseException, step: str | None = None) -> str:
    """예외 종류와 항목이 둔 단계 이름(고정 글자)만. 문구는 식별값을 실을 수 있어 옮기지 않는다."""
    where = f"({step})" if step else ""
    return f"{UNRECORDED} — {type(exc).__name__}{where}"


def _timed_out(exc: BaseException) -> bool:
    """기다림이 다 된 예외 — 이 파일의 `TimeoutError` 와 Playwright 의 같은 이름 예외(내장 것을 잇지
    않는다)."""
    return type(exc).__name__ == "TimeoutError"


def _run_once(screen: Screen, item: Item) -> tuple[str, BaseException | None]:
    screen.current_step = None
    try:
        screen.settle()
        return item.run(screen), None
    except Exception as exc:  # noqa: BLE001 — 항목 하나의 실패가 나머지를 막지 않는다
        return unrecorded(exc, screen.current_step), exc


def run_items(
    screen: Screen,
    items: Sequence[Item],
    *,
    allow_writes: bool,
    deadline: float,
    on_outcome: Callable[[Outcome], None] = lambda outcome: None,
    clock: Callable[[], float] = time.monotonic,
) -> list[Outcome]:
    """항목을 차례로 돌린다. 하나가 예외로 끝나도 나머지는 돈다. `deadline`(같은 `clock` 의 시각 —
    스크립트 시작에서 잰 전체 예산의 끝)을 넘긴 뒤의 항목은 돌리지 않는다."""
    outcomes: list[Outcome] = []
    for number, item in enumerate(items, start=1):
        started = clock()
        if item.writes and not allow_writes:
            outcome = Outcome(item, SKIPPED_NO_PERMISSION)
        elif started >= deadline:
            outcome = Outcome(item, OVER_BUDGET)
        else:
            result, error = _run_once(screen, item)
            # 첫 판의 기다림이 다 됐으면 쓰지 않는 항목만 한 번 더 돈다 — 페이더가 두 배포
            # 이어 첫 판에만 `TimeoutError` 였다(사내 리뷰 202610200720). 첫 판 줄은 남긴다.
            if error is not None and _timed_out(error) and not item.writes and clock() < deadline:
                first = result
                result, error = _run_once(screen, item)
                result = f"{result} · 첫 판 {first.removeprefix(f'{UNRECORDED} — ')} 뒤 다시 돎"
            try:
                screen.shot(f"{number:02d}_{item.key}")
            except Exception:  # noqa: BLE001 — 스크린샷은 덤이다
                pass
            outcome = Outcome(item, result, clock() - started)
        outcomes.append(outcome)
        on_outcome(outcome)
    return outcomes


# ---------------------------------------------------------------------------------- 결과 꼴

BLOCK_COMMENT: Final = (
    "<!-- check_deploy_screens.py — 아래 블록을 리뷰 문서 7장 화면 확인 절에 그대로 붙인다 -->"
)
BLOCK_TITLE: Final = "### 화면 확인 (에이전트 · `check_deploy_screens.py`)"


@dataclass
class RunFacts:
    """블록 머리 세 줄의 재료. 모두 수와 고정 글자다. 실행하며 채운다."""

    channel: str
    stamp: str
    allow_writes: bool
    # 사용자 앱 프로세스를 「봄」 또는 「무시」(--ignore-other-apps). 못 봤으면 여기까지 오지
    # 않는다.
    process_scan: str = "봄"
    # (시뮬레이션, 설비) — 띄우기 전 대기 중이던 마이그레이션 수와, 끝난 뒤 센 이 확인이 건 수.
    pending_migrations: tuple[int, int] | None = None
    applied_migrations: tuple[int, int] | None = None
    # 입장 뒤 앱이 오류 화면이면 그 꼴(「앱 오류 화면 있음」 등). 그때 항목은 돌지 않는다.
    app_problem: str | None = None
    # 앱을 띄운 뒤 멈춘 까닭(고정 글자와 예외 종류만). 그때 남은 항목은 돌지 않았다.
    stop_reason: str | None = None
    started_seconds: float = 0.0
    entered_seconds: float = 0.0
    elapsed_seconds: float = 0.0


def _browser_name(channel: str) -> str:
    return {"chrome": "Chrome", "msedge": "Edge"}.get(channel, "Chromium")


def _duration(seconds: float) -> str:
    whole = int(round(seconds))
    return f"{whole // 60}분 {whole % 60}초" if whole >= 60 else f"{whole}초"


def _migration_note(facts: RunFacts) -> str:
    if facts.applied_migrations is not None:
        simulation, equipment = facts.applied_migrations
        if simulation + equipment == 0:
            return "마이그레이션 — 이 확인이 건 것 없음"
        return (
            f"**마이그레이션 {simulation + equipment}개를 이 확인이 걸었다**"
            f"(시뮬레이션 {simulation} · 설비 {equipment})"
        )
    if facts.pending_migrations is not None:
        simulation, equipment = facts.pending_migrations
        if simulation + equipment:
            return (
                f"대기 마이그레이션 시뮬레이션 {simulation} · 설비 {equipment} — 확인용 앱이 건다"
            )
        return "대기 마이그레이션 없음"
    return "마이그레이션 — 세지 못함"


def over_budget_count(outcomes: Sequence[Outcome]) -> int:
    return sum(outcome.result == OVER_BUDGET for outcome in outcomes)


def render_block(outcomes: Sequence[Outcome], *, total: int, facts: RunFacts) -> str:
    """리뷰 문서에 그대로 붙이는 블록. 사전 확인을 지난 실행에만 쓴다(머리의 「DB 잠금 없음」 등은
    그 뒤에만 참이다). 앱 오류 화면·멈춤·예산 넘음·끊긴 실행이면 셋째 머리 줄이 그렇게 말한다."""
    recorded = sum(outcome.recorded for outcome in outcomes)
    skipped = sum(outcome.result == SKIPPED_NO_PERMISSION for outcome in outcomes)
    missing = len(outcomes) - recorded - skipped
    over = over_budget_count(outcomes)
    if facts.app_problem is not None:
        state = f"**{facts.app_problem} — 항목 안 돎**"
    elif facts.stop_reason is not None:
        state = f"**{facts.stop_reason}**"
    elif over:
        state = f"**예산 넘어 {over} 항목 안 돎**"
    elif len(outcomes) == total:
        state = "끝까지 돎"
    else:
        state = f"**중간에 끊김 — {len(outcomes)}/{total} 항목까지**"
    scan = "프로세스 봄" if facts.process_scan == "봄" else "프로세스 무시(--ignore-other-apps)"
    width, height = VIEWPORT
    lines = [
        BLOCK_COMMENT,
        "",
        BLOCK_TITLE,
        "",
        f"- 헤드리스 {_browser_name(facts.channel)} {width}×{height} · 별도 포트에 띄운 앱"
        f"({APP_ADDRESS}) · {facts.stamp} · "
        f"{'쓰기 허락 있음' if facts.allow_writes else '쓰기 허락 없음'}",
        f"- 사용자 앱 확인 — {scan} · DB 잠금 없음 · {_migration_note(facts)}",
        f"- 앱 기동 {_duration(facts.started_seconds)} · "
        f"입장 화면 {_duration(facts.entered_seconds)} · "
        f"항목 {total} — 기록 {recorded} · 미기록 {missing} · 안 함 {skipped} · "
        f"걸린 시간 {_duration(facts.elapsed_seconds)} · {state}",
        "",
        "| 항목 | 쓰기 | 결과 |",
        "|---|---|---|",
    ]
    for outcome in outcomes:
        writes = "씀(지워 되돌림)" if outcome.item.writes else "없음"
        cell = outcome.result.replace("|", "/").replace("\n", " ")
        lines.append(f"| {outcome.item.title} | {writes} | {cell} |")
    return "\n".join(lines) + "\n"


def status_block(line: str) -> str:
    """사전 확인 전·일찍 끝난 실행의 블록 — 머리와 고정 문구 한 줄뿐이다. 전체 머리(「DB 잠금 없음」
    등)는 그 확인을 지난 뒤에만 참이라 여기서는 쓰지 않는다."""
    return "\n".join([BLOCK_COMMENT, "", BLOCK_TITLE, "", f"- {line}"]) + "\n"


def render_item_list(items: Sequence[Item]) -> str:
    lines = ["| 키 | 항목 | 쓰기 |", "|---|---|---|"]
    lines.extend(
        f"| `{item.key}` | {item.title} | {'씀' if item.writes else '없음'} |" for item in items
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------------- 확인 항목
#
# 배포마다 바뀌는 자리다. 결과 문자열은 고정 글자와 수로만 만든다 — 화면에서 읽은 이름을
# 넣지 않는다.

_TOOLBAR_POSITIONS_JS = """(ids) => ids.map((id) => {
  const e = document.getElementById(id);
  if (!e) return null;
  const r = e.getBoundingClientRect();
  return r.width > 0 ? r.x : null;
})"""
# 글자 본래 폭(Range)이 제 칸 폭을 넘어도 되는 몫(px). 잘리지 않은 줄은 두 폭이 같고(배치 단위
# 1/64px 까지), 브라우저는 그보다 작은 넘침에도 말줄임을 그린다 — 0.5px 를 두면 그 안쪽 말줄임을
# 「다 보임」으로 읽는다. 칸이 둘레 상자 안에 있는가(위치)는 0.5px 를 그대로 둔다.
_RANGE_SLACK_PX: Final = 0.02
# 글자 잉크가 자르는 선을 넘어도 되는 몫(px). 그보다 작은 넘침은 화면에 서지 않는다.
_INK_SLACK_PX: Final = 0.1
# 라벨 글자 한 줄이 다 보이는가 — 글자 본래 폭(Range 는 말줄임 전 폭을 준다)이 제 칸에 들고, 칸이
# 둘레 상자 안에 있고, 글자 잉크(`inked`)가 잘리지 않는다. `scrollWidth` 는 정수로 반올림돼 1px
# 안쪽 넘침(말줄임이 이미 선 것)을 놓친다.
# `inked` 는 넘친 것을 자르는 조상(자기 포함 — shadow root 는 호스트로 건너간다)마다 테두리 안쪽
# 위·아래 끝(`overflow: clip` 이면 `overflow-clip-margin` 만큼 바깥)을 모아, 글자 잉크의 위·아래
# 끝이 그 안에 드는가를 본다. 칸 상자끼리만 견주면 라벨
# 테두리 안쪽에서 자르는 선과 줄 상자 밑으로 내려간 「g」 꼬리를 못 본다(사내 리뷰 202610182227 —
# 부제 칸 아래 끝과 라벨 아래 끝이 같아도 라벨이 테두리 1px 안쪽에서 잘랐다). 기준선은 글자 끝에
# 잠깐 붙인 0×0 인라인 블록의 아래 끝(인라인 블록은 내용이 없으면 아래 끝이 기준선)이고, 잉크
# 높이는 같은 글꼴의 캔버스 `measureText` 다. 글자가 없는 칸(Summary 단추)은 칸 상자를 본다.
_WHOLE_LINE_JS = f"""const parentOf = (node) => node.parentElement
    || (node.getRootNode && node.getRootNode().host) || null;
  const clipOf = (el, self) => {{
    let top = -Infinity;
    let bottom = Infinity;
    for (let node = self ? el : parentOf(el); node && node !== document.documentElement;
      node = parentOf(node)) {{
      const s = getComputedStyle(node);
      if (s.overflowY === "visible") continue;
      const b = node.getBoundingClientRect();
      const margin = s.overflowY === "clip"
        ? parseFloat((/-?[\\d.]+px/.exec(s.overflowClipMargin || "") || ["0"])[0]) : 0;
      top = Math.max(top, b.top + parseFloat(s.borderTopWidth) - margin);
      bottom = Math.min(bottom, b.bottom - parseFloat(s.borderBottomWidth) + margin);
    }}
    return {{ top, bottom }};
  }};
  const STRETCH = {{
    "50%": "ultra-condensed", "62.5%": "extra-condensed", "75%": "condensed",
    "87.5%": "semi-condensed", "112.5%": "semi-expanded", "125%": "expanded",
    "150%": "extra-expanded", "200%": "ultra-expanded",
  }};
  const inked = (el) => {{
    const text = (el.textContent || "").trim();
    if (!text) {{
      const r = el.getBoundingClientRect();
      const clip = clipOf(el, false);
      return r.top >= clip.top - 0.5 && r.bottom <= clip.bottom + 0.5;
    }}
    const probe = document.createElement("span");
    probe.style.cssText = "display:inline-block;width:0;height:0;margin:0;padding:0;border:0;"
      + "vertical-align:baseline";
    el.appendChild(probe);
    const baseline = probe.getBoundingClientRect().bottom;
    probe.remove();
    const s = getComputedStyle(el);
    const ctx = document.createElement("canvas").getContext("2d");
    ctx.font = `${{s.fontStyle}} ${{s.fontWeight}} ${{s.fontSize}} ${{s.fontFamily}}`;
    if ("fontStretch" in ctx) ctx.fontStretch = STRETCH[s.fontStretch] || "normal";
    const m = ctx.measureText(text);
    const clip = clipOf(el, true);
    return baseline - m.actualBoundingBoxAscent >= clip.top - {_INK_SLACK_PX}
      && baseline + m.actualBoundingBoxDescent <= clip.bottom + {_INK_SLACK_PX};
  }};
  const whole = (el, box) => {{
    const r = el.getBoundingClientRect();
    const range = document.createRange();
    range.selectNodeContents(el);
    return r.width > 0 && range.getBoundingClientRect().width <= r.width + {_RANGE_SLACK_PX}
      && r.left >= box.left - 0.5 && r.right <= box.right + 0.5
      && r.top >= box.top - 0.5 && r.bottom <= box.bottom + 0.5 && inked(el);
  }};"""
# 사이드바 라벨: 심볼 크기와 앱 이름 두 줄(`S.PKG CAPA` · `AX Management`)·Summary 단추. 단추는
# 좁은 사이드바에서 통째로 빠진다 — 컨테이너 질의로 감추거나(`display: none`), 들어가지 않아 라벨
# 높이 밖 둘째 줄로 내려간다(위 끝이 라벨 아래 끝 밑). 빠진 것은 잘린 것이 아니다.
_LABEL_MARK_JS = f"""(id) => {{
  const label = document.getElementById(id);
  const part = (name) => label && label.querySelector(name);
  const mark = part("svg");
  const word = part(".capa-brand-word");
  const sub = part(".capa-brand-sub");
  const hint = part(".capa-brand-hint");
  if (!mark || !word || !sub || !hint) return null;
  {_WHOLE_LINE_JS}
  const l = label.getBoundingClientRect();
  const m = mark.getBoundingClientRect();
  const hintGone = getComputedStyle(hint).display === "none"
    || hint.getBoundingClientRect().top >= l.bottom - 1;
  return {{
    w: Math.round(m.width * 10) / 10, h: Math.round(m.height * 10) / 10,
    fits: whole(word, l) && whole(sub, l) && (hintGone || whole(hint, l)),
    ready: label.getAttribute("aria-disabled") !== "true",
  }};
}}"""
# 사이드바를 `widths` 의 폭마다 좁혀 같은 라벨을 다시 잰다. 두 줄은 줄마다 `whole`(다 보임) ·
# `ellipsis`(칸이 라벨 안에 있고 말줄임으로 끝남) · `cut`, Summary 단추는 `gone`(빠짐) · `whole` ·
# `cut` 이다. 폭 전환(0.3초)을 끄고 두 프레임 기다려 컨테이너 질의가 선 뒤 재며, 끝나면 원래 폭으로
# 되돌린다(`_SIDEBAR_GROUPS_NARROW_JS` 와 같은 꼴).
_LABEL_NARROW_JS = f"""async ({{id, widths}}) => {{
  const side = document.querySelector('[data-testid="stSidebar"]');
  const label = document.getElementById(id);
  const part = (name) => label && label.querySelector(name);
  const word = part(".capa-brand-word");
  const sub = part(".capa-brand-sub");
  const hint = part(".capa-brand-hint");
  if (!side || !word || !sub || !hint) return null;
  {_WHOLE_LINE_JS}
  const line = (el, box) => {{
    if (whole(el, box)) return "whole";
    const r = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    const inside = r.width > 0 && r.left >= box.left - 0.5 && r.right <= box.right + 0.5
      && r.top >= box.top - 0.5 && r.bottom <= box.bottom + 0.5;
    return inside && inked(el) && style.overflowX !== "visible" && style.textOverflow === "ellipsis"
      ? "ellipsis" : "cut";
  }};
  const saved = side.getAttribute("style");
  const rows = [];
  try {{
    for (const width of widths) {{
      side.style.transition = "none";
      side.style.width = side.style.minWidth = side.style.maxWidth = `${{width}}px`;
      await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
      const l = label.getBoundingClientRect();
      const hintGone = getComputedStyle(hint).display === "none"
        || hint.getBoundingClientRect().top >= l.bottom - 1;
      rows.push({{
        width: Math.round(side.getBoundingClientRect().width),
        word: line(word, l),
        sub: line(sub, l),
        hint: hintGone ? "gone" : whole(hint, l) ? "whole" : "cut",
      }});
    }}
  }} finally {{
    if (saved === null) side.removeAttribute("style");
    else side.setAttribute("style", saved);
  }}
  return rows;
}}"""
# Summary 머리 줄: 심볼 크기와 라벨 두 줄. 두 줄은 머리 줄 높이 안이고 오른쪽 이웃 단추를
# 덮지 않는다. 이웃은 dock 의 첫 보이는 단추다 — Summary 에서는 Detail 왼쪽의 ← 단추(입장 화면으로
# 돌아가기), 그것이 없는 판이면 Detail 이다. Detail 만 보면 라벨이 ← 를 덮어도 「다 보임」이다.
_SUMMARY_MARK_JS = f"""(id) => {{
  const host = document.getElementById(id);
  if (!host || getComputedStyle(host).display === "none" || !host.shadowRoot) return null;
  const root = host.shadowRoot;
  const mark = [...root.querySelectorAll(".head > .logo svg")]
    .map((s) => s.getBoundingClientRect()).find((r) => r.width > 0);
  const head = root.querySelector(".head");
  const brand = root.querySelector(".head > .brand");
  const lines = brand ? [".brand-word", ".brand-sub"].map((name) => brand.querySelector(name)) : [];
  if (!mark || !head || lines.length < 2 || !lines.every(Boolean)) return null;
  {_WHOLE_LINE_JS}
  const h = head.getBoundingClientRect();
  const neighbor = [...root.querySelectorAll(".dock > button")]
    .map((el) => el.getBoundingClientRect()).find((r) => r.width > 0);
  const right = brand.getBoundingClientRect().right;
  const clear = !neighbor || right <= neighbor.left + 0.5;
  return {{
    size: [Math.round(mark.width * 10) / 10, Math.round(mark.height * 10) / 10],
    fits: lines.every((line) => whole(line, h)) && clear,
  }};
}}"""
_BOX_LEFT_JS = """(el) => el.getBoundingClientRect().x"""
# 서랍은 컴포넌트의 shadow root 안이라 `document.querySelector` 로는 닿지 않는다. Playwright
# 로케이터(`.sle-tray`, shadow 를 뚫는다)로 잡은 서랍 요소를 받아 그 root 에서 찾는다.
# 칩마다 편집기가 단 `__entry`(대표 호기와 함께 놓일 호기 목록)에서 층 미정 호기(`floorless` — 동이
# 비었거나 같은 동에 층만 빈 호기, 편집기가 「층 미정」 꼬리표를 다는 그것)와 묶음 모듈(`group`)을
# 센다. 층 목록 표 `미배치대수` 는 그 층 동·층이 적힌 호기만 설비지분으로 센다 — 서랍 N 에서 층
# 미정을 빼면 표 N 이고, 묶음 모듈은 서랍이 한 대씩 세어 표보다 클 수 있다. 칩 하나가 묶음 하나라
# (편집기 `trayEntries`) 이 층 몫 모듈이 든 묶음 칩 수 `groups` 도 센다 — 묶음 하나는 표에서 1대다.
# `__entry` 가 없는 칩이 하나라도 있으면(편집기 판이 다르면) 세 수는 null 이다.
_TRAY_JS = """(tray) => {
  if (tray.hidden) return null;
  const chips = [...tray.querySelectorAll(".sle-tray-list .sle-chip")];
  const names = chips.map((chip) => (chip.querySelector(".sle-chip-name") || {}).textContent || "");
  const order = new Intl.Collator("ko", { numeric: true, sensitivity: "base" });
  let violations = 0;
  for (let i = 1; i < names.length; i += 1) {
    if (order.compare(names[i - 1], names[i]) > 0) violations += 1;
  }
  const count = (tray.querySelector(".sle-tray-count") || {}).textContent || "";
  let floorless = 0;
  let modules = 0;
  let groups = 0;
  let readable = true;
  for (const chip of chips) {
    const list = chip.__entry && Array.isArray(chip.__entry.list) ? chip.__entry.list : null;
    if (!list) { readable = false; continue; }
    let grouped = 0;
    for (const unit of list) {
      if (unit.floorless) floorless += 1;
      else if (unit.group) grouped += 1;
    }
    modules += grouped;
    if (grouped) groups += 1;
  }
  return {
    chips: names.length, violations, count, first: names[0] || "",
    floorless: readable ? floorless : null, modules: readable ? modules : null,
    groups: readable ? groups : null,
  };
}"""
_TRAY_STATE_JS = """(tray) => {
  const root = tray.getRootNode();
  const search = root.querySelector(".sle-tray-search");
  const empty = root.querySelector(".sle-tray-empty");
  return {
    open: !tray.hidden,
    count: (tray.querySelector(".sle-tray-count") || {}).textContent || "",
    query: search ? search.value : null,
    empty: !!empty && !empty.hidden,
  };
}"""


def _px(size: Sequence[float]) -> str:
    return f"{size[0]:g}×{size[1]:g}px"


def check_toolbar_order(screen: Screen) -> str:
    """툴바 단추 차례 — 왼쪽부터 Guide · Print · 테마(`TOOLBAR_BUTTON_ORDER`)."""
    ids = list(TOOLBAR_BUTTON_ORDER)
    positions = screen.poll(
        lambda: screen.js(_TOOLBAR_POSITIONS_JS, ids),
        timeout=15,
        accept=lambda values: all(value is not None for value in values),
    )
    present = [(x, button) for x, button in zip(positions, ids, strict=True) if x is not None]
    if len(present) < len(ids):
        missing = [TOOLBAR_LABELS[b] for x, b in zip(positions, ids, strict=True) if x is None]
        return f"단추 {len(present)}/{len(ids)} — 없음: {', '.join(missing)}"
    order = [button for _, button in sorted(present)]
    verdict = "같음" if order == ids else "다름"
    return f"{' · '.join(TOOLBAR_LABELS[b] for b in order)} — 정한 차례와 {verdict}"


def label_narrow_findings(
    rows: Sequence[Mapping[str, Any]] | None,
) -> tuple[tuple[int, ...], int] | None:
    """좁은 폭 라벨 측정(`_LABEL_NARROW_JS`)에서 잘린 사이드바 폭들과, 가장 좁은 폭의 말줄임 줄 수.

    `LABEL_NARROW_WIDTHS_PX` 의 마지막(가장 좁은 폭)만 말줄임을 정한 모양으로 본다. 못 쟀으면 None.
    """
    if not rows or len(rows) != len(LABEL_NARROW_WIDTHS_PX):
        return None
    cut: list[int] = []
    ellipses = 0
    for asked, row in zip(LABEL_NARROW_WIDTHS_PX, rows, strict=True):
        lines = [str(row.get("word")), str(row.get("sub"))]
        last_resort = asked == SIDEBAR_NARROW_WIDTH_PX
        allowed = {"whole", "ellipsis"} if last_resort else {"whole"}
        if any(line not in allowed for line in lines) or row.get("hint") not in ("gone", "whole"):
            cut.append(int(row.get("width") or asked))
        elif last_resort:
            ellipses += lines.count("ellipsis")
    return tuple(cut), ellipses


def _label_verdict(fits: bool, narrow: tuple[tuple[int, ...], int] | None) -> str:
    """「라벨 글자」 판정 글. 기본 폭과 좁은 폭이 다 보이면 기본 폭만 재던 때와 같은 「다 보임」."""
    if narrow is None:
        return f"{'다 보임' if fits else '잘림'} · 좁은 폭 못 잼"
    cut, ellipses = narrow
    if cut:
        widths = "·".join(str(width) for width in cut)
        return f"잘림({'' if fits else '기본 폭 · '}좁은 폭 {widths}px)"
    if not fits:
        return "잘림"
    return "다 보임" + (
        f"(좁은 폭 {SIDEBAR_NARROW_WIDTH_PX}px 말줄임 {ellipses})" if ellipses else ""
    )


def check_sidebar_symbol(screen: Screen) -> str:
    """사이드바 라벨 심볼과 Summary 머리 줄 심볼(px), 라벨 글자가 다 보이는가.

    「라벨 글자」는 두 자리 라벨의 앱 이름 두 줄(`S.PKG CAPA` · `AX Management`)과 사이드바의
    Summary 단추다. 한 곳이라도 말줄임·잘림이면 「잘림」이다. 사이드바 라벨은 기본 폭 뒤에
    좁게 끈 폭(`LABEL_NARROW_WIDTHS_PX`)에서도 잰다 — 기본 폭만 재면 좁은 폭에서 앱 이름이 말줄임
    없이 잘려도 「다 보임」이다. 잘린 좁은 폭은 괄호에 적고, 가장 좁은 폭의 말줄임은 정한 모양이라
    「다 보임」 뒤에 그 수만 적는다.
    """
    side = screen.wait_for(
        lambda: screen.js(_LABEL_MARK_JS, SUMMARY_LABEL_ID),
        timeout=30,
        accept=lambda value: bool(value) and bool(value["ready"]),
    )
    narrow = label_narrow_findings(
        screen.js(
            _LABEL_NARROW_JS, {"id": SUMMARY_LABEL_ID, "widths": list(LABEL_NARROW_WIDTHS_PX)}
        )
    )
    screen.page.locator(f"#{SUMMARY_LABEL_ID}").click()
    try:
        summary = screen.wait_stable(lambda: screen.js(_SUMMARY_MARK_JS, INTRO_HOST_ID), timeout=30)
    finally:
        screen.close_overlay()
    side_size = (float(side["w"]), float(side["h"]))
    summary_size = (float(summary["size"][0]), float(summary["size"][1]))
    same = all(abs(a - b) < 0.5 for a, b in zip(side_size, summary_size, strict=True))
    fits = bool(side["fits"]) and bool(summary["fits"])
    return (
        f"사이드바 {_px(side_size)} · Summary {_px(summary_size)} — {'같음' if same else '다름'} · "
        f"라벨 글자 {_label_verdict(fits, narrow)}"
    )


def open_equipment_tab(screen: Screen, name: str) -> None:
    """가용설비 현황의 탭 하나를 누른다 — Summary 안쪽 탭이면 Summary 를 먼저 누른다."""
    if name in EQUIPMENT_SUMMARY_TABS:
        screen.open_tab(EQUIPMENT_SUMMARY_TAB)
    screen.open_tab(name)


def open_bulk_import(screen: Screen) -> None:
    """탭 ① 불러오기 줄의 「엑셀·CSV로 한꺼번에」(표 컴포넌트 단추 — 그림자 DOM)를 눌러 팝업이 보일
    때까지 기다린다."""
    loader = screen.page.locator(f'[data-testid="stMain"] .st-key-{EQUIPMENT_LOADER_KEY}')
    loader.get_by_role("button", name=BULK_IMPORT_BUTTON).first.click()
    screen.wait_for(screen.dialog_count, timeout=30, accept=lambda count: count > 0)


def check_bulk_import_target(screen: Screen) -> str:
    """`가용설비 현황` 설비 마스터 탭 「엑셀·CSV로 한꺼번에」 팝업의 `등록할 표` 기본값이 「설비
    마스터」인가, 옛 이름이 남았는가. 팝업은 `Esc` 로 닫는다(미리보기·넣기는 누르지 않는다)."""
    screen.open_page(EQUIPMENT_PAGE)
    open_equipment_tab(screen, EQUIPMENT_MASTER_TAB)
    open_bulk_import(screen)
    try:
        title = screen.dialog_title()
        box = screen.selectbox("등록할 표")
        screen.poll(box.count, timeout=30, accept=lambda count: count > 0)
        value = screen.selectbox_value("등록할 표")
        old_names = int(
            screen.dialog_read("(box) => (box.innerText.match(/호기 마스터/g) || []).length") or 0
        )
    finally:
        closed = screen.close_dialog()
    if value is None:
        return "`등록할 표` 상자 없음"
    shown = "있음" if value == "설비 마스터" else "없음(다른 값)"
    return (
        f"{_title_text(title, BULK_IMPORT_TITLE)} · 「등록할 표: 설비 마스터」 {shown} · 옛 이름 "
        f"「호기 마스터」 {old_names}곳 · {_closed_text(closed)}"
    )


def _grid(screen: Screen) -> Any:
    return screen.page.locator(f'[data-testid="stMain"] .st-key-{EQUIPMENT_GRID_KEY}')


def _grid_rows(screen: Screen) -> int:
    return int(_grid(screen).locator('.emg-body [role="row"]').count())


def _ensure_grid_rows(screen: Screen) -> int:
    """표에 불러온 줄 수 — 없으면 불러오기 「전체 N대 불러오기」(화면 조작 — DB 에 쓰지 않는다)."""
    grid = _grid(screen)
    grid.locator(".emg-grid").first.wait_for(state="attached", timeout=ACTION_TIMEOUT_MS)
    if _grid_rows(screen):
        return _grid_rows(screen)
    loader = screen.page.locator(f'[data-testid="stMain"] .st-key-{EQUIPMENT_LOADER_KEY}')
    whole = loader.get_by_role("button", name=re.compile(r"^전체 [\d,]+대 불러오기$"))
    if not whole.count():
        return 0
    whole.first.click()
    screen.wait_idle()
    return int(screen.poll(lambda: _grid_rows(screen), timeout=60, accept=bool) or 0)


def _press_column_set(screen: Screen, label: str) -> str | None:
    """표 칸 묶음 단추를 누르고 그 전에 눌려 있던 묶음 글을 돌려준다(브라우저 몫 — 회차 없음)."""
    seg = _grid(screen).locator(".emg-seg button")
    before = None
    for index in range(seg.count()):
        if seg.nth(index).get_attribute("aria-pressed") == "true":
            before = seg.nth(index).inner_text().strip()
    seg.filter(has_text=label).first.click()
    return before


def _grid_headers(screen: Screen) -> list[tuple[str, bool]]:
    """머리 칸 (이름, 시나리오 표지 있음) — 체크·빼기 칸은 이름이 없어 빠진다."""
    heads = _grid(screen).locator('.emg-head [role="columnheader"] .emg-hb')
    result: list[tuple[str, bool]] = []
    for index in range(heads.count()):
        head = heads.nth(index)
        name = head.locator("span").first.inner_text().strip()
        mark = head.locator("small")
        scenario = mark.count() > 0 and mark.first.inner_text().strip() == GRID_SCENARIO_MARK
        result.append((name, scenario))
    return result


def summarize_equipment_headers(found: Mapping[str, bool], dropped: bool) -> str:
    """머리 칸 확인 결과. 이름은 계약의 고정 글자(`EQUIPMENT_NEW_HEADERS`)만 적는다."""
    present = [name for name in EQUIPMENT_NEW_HEADERS if found.get(name, False)]
    missing = [name for name in EQUIPMENT_NEW_HEADERS if not found.get(name, False)]
    head = f"새 이름 {len(present)}/{len(EQUIPMENT_NEW_HEADERS)} 있음"
    if missing:
        head += f"(없음: {', '.join(missing)})"
    return f"{head} · 「{EQUIPMENT_DROPPED_HEADER}」 {'있음' if dropped else '없음'}"


def check_equipment_headers(screen: Screen) -> str:
    """`가용설비 현황` 설비 마스터 탭 표(개편 B1 — 표 컴포넌트)의 「전체 39칸」 머리 — 38열 개편의
    새 이름 일곱과 설비 시나리오의 「시나리오 메모」(39열)가 있고 지운 「설비가동현황」이 없는가,
    머리 칸 수와 시나리오 표지 수. 줄이 없으면 「전체 N대 불러오기」 로 불러오고(화면 조작), 칸
    묶음은 처음 것으로 되돌린다."""
    screen.open_page(EQUIPMENT_PAGE)
    open_equipment_tab(screen, EQUIPMENT_MASTER_TAB)
    if not _ensure_grid_rows(screen):
        return "불러올 호기 없음(설비 마스터 비어 있음)"
    before = _press_column_set(screen, GRID_ALL_COLUMNS_SET)
    try:
        headers = screen.poll(
            lambda: _grid_headers(screen),
            timeout=20,
            accept=lambda value: len(value) >= GRID_ALL_COLUMNS,
        )
    finally:
        if before and before != GRID_ALL_COLUMNS_SET:
            _press_column_set(screen, before)
    names = [name for name, _ in headers or []]
    found = {name: name in names for name in EQUIPMENT_NEW_HEADERS}
    dropped = EQUIPMENT_DROPPED_HEADER in names
    scenario = sum(1 for _, marked in headers or [] if marked)
    return (
        f"{summarize_equipment_headers(found, dropped)} · 머리 {len(names)}칸 · 시나리오 표지 "
        f"{scenario}칸"
    )


def _cell(screen: Screen, column: int) -> Any:
    """첫 줄의 그 칸(계약 자리 번호)."""
    return _grid(screen).locator(f'.emg-body .emg-c[data-col="{column}"]').first


def _cell_has(screen: Screen, column: int, name: str) -> bool:
    classes = _cell(screen, column).get_attribute("class") or ""
    return name in classes.split()


def _type_into(screen: Screen, column: int, text: str) -> None:
    """칸을 눌러 고치기 시작하고 글을 쳐 Enter 로 확정한다(출납 — 300ms 뒤 보낸다)."""
    _cell(screen, column).click()
    editor = _grid(screen).locator(".emg-ed").first
    editor.wait_for(state="visible", timeout=ACTION_TIMEOUT_MS)
    editor.fill(text)
    editor.press("Enter")
    screen.wait_idle()


def summarize_equipment_grid(
    sets: int, rows: int, changed: bool | None, error: bool | None, discarded: bool
) -> str:
    """표 확인 결과 — 칸 묶음 수·불러온 줄 있음·고친 칸 표지·오류 칸 표지·모두 버리기(수와
    있음/없음만)."""
    parts = [f"칸 묶음 {sets}/{GRID_COLUMN_SETS}", f"줄 {'있음' if rows else '없음'}"]
    if changed is not None:
        parts.append(f"고친 칸 표지 {'있음' if changed else '없음'}")
    if error is not None:
        parts.append(f"틀린 날짜 오류 {'있음' if error else '없음'}")
    elif rows:
        parts.append("틀린 날짜 칸 잠김")
    parts.append(f"모두 버리기 {'됨' if discarded else '안 됨'}")
    return " · ".join(parts)


def check_equipment_grid(screen: Screen) -> str:
    """`가용설비 현황` 설비 마스터 표 — 칸 묶음 다섯, 줄을 불러와 공통 글 칸 하나를 고쳐 「고친
    칸」 표지, 시나리오 날짜 칸에 틀린 날짜를 넣어 「오류」 표지(낡은 세션이면 잠김), 끝에 「저장
    전 변경」 의 「모두 버리기」 로 편집본째 버린다. **저장하지 않는다**(DB 에 쓰지 않는다).
    값·이름은 찍지 않는다."""
    screen.open_page(EQUIPMENT_PAGE)
    open_equipment_tab(screen, EQUIPMENT_MASTER_TAB)
    rows = _ensure_grid_rows(screen)
    sets = int(_grid(screen).locator(".emg-seg button").count())
    if not rows:
        return summarize_equipment_grid(sets, 0, None, None, False)
    before = _press_column_set(screen, GRID_ALL_COLUMNS_SET)
    changed: bool | None = None
    error: bool | None = None
    discarded = False
    try:
        headers = [name for name, _ in _grid_headers(screen)]
        text_column = _contract_index(headers, GRID_TEXT_COLUMN)
        date_column = _contract_index(headers, GRID_DATE_COLUMN)
        if text_column is not None and not _cell_has(screen, text_column, "is-locked"):
            _type_into(screen, text_column, GRID_TEXT_PROBE)
            changed = bool(
                screen.poll(lambda: _cell_has(screen, text_column, "is-changed"), timeout=20)
            )
        if date_column is not None and not _cell_has(screen, date_column, "is-locked"):
            _type_into(screen, date_column, GRID_BAD_DATE)
            error = bool(
                screen.poll(lambda: _cell_has(screen, date_column, "is-error"), timeout=20)
            )
    finally:
        if before and before != GRID_ALL_COLUMNS_SET:
            _press_column_set(screen, before)
        discarded = _discard_all(screen)
    return summarize_equipment_grid(sets, rows, changed, error, discarded)


def _contract_index(headers: Sequence[str], name: str) -> int | None:
    """「전체 39칸」 머리 차례(설비명 맨 앞 + 나머지 계약 차례)에서 계약 자리 번호를 낸다 — 표가
    칸 자리(`data-col`)를 계약 차례로 단다. 설비명은 계약 여섯째(자리 5)다."""
    if name not in headers:
        return None
    position = headers.index(name)
    name_spot = 5
    return position - 1 if position <= name_spot else position


def _discard_all(screen: Screen) -> bool:
    """오른쪽 칸을 「저장 전 변경」 으로 바꿔 「모두 버리기」 → 「모두 버리기 확인」, 오른쪽 칸
    고르기는 처음 것으로 되돌린다. 고친 것이 없어도 누른다(편집본을 저장본으로 다시 세울
    뿐이다)."""
    before = _choose_segment(screen, EQUIPMENT_SIDE_KEY, EQUIPMENT_SIDE_CHANGES)
    try:
        popover = screen.page.locator(f'[data-testid="stMain"] .st-key-{EQUIPMENT_DISCARD_KEY}')
        if not popover.count():
            return False
        popover.locator("button").first.click()
        confirm = screen.page.get_by_role("button", name=GRID_DISCARD_CONFIRM)
        confirm.first.wait_for(state="visible", timeout=ACTION_TIMEOUT_MS)
        confirm.first.click()
        screen.wait_idle()
        marked = ".emg-body .emg-c.is-changed, .emg-body .emg-c.is-error"
        return bool(screen.poll(lambda: not _grid(screen).locator(marked).count(), timeout=30))
    finally:
        if before and before != EQUIPMENT_SIDE_CHANGES:
            _choose_segment(screen, EQUIPMENT_SIDE_KEY, before)


def check_progress_box(screen: Screen) -> str:
    """`필요 단축 일정` 화면의 `진척 비교` 상자 — 있음·값·선택지 수·자리. 고르지 않는다."""
    screen.open_page(SHORTENING_PAGE)
    box = screen.selectbox("진척 비교")
    if screen.poll(box.count, timeout=60, accept=lambda count: count > 0) == 0:
        return "상자 없음"
    value = screen.selectbox_value("진척 비교")
    options = screen.selectbox_option_count("진척 비교")
    target = screen.selectbox("목표 확보율")
    if target.count() == 0:
        place = "목표 확보율 상자 없음"
    else:
        left = float(box.first.evaluate(_BOX_LEFT_JS)) < float(target.first.evaluate(_BOX_LEFT_JS))
        place = f"목표 확보율 {'왼쪽' if left else '오른쪽'}"
    current = "비교 안 함" if value == "비교 안 함" else "그 밖"
    return f"상자 있음({place}) · {current} · 선택지 {options}개"


def _number(text: str | None) -> float:
    try:
        return float(str(text).replace(",", "").strip())
    except ValueError:
        return 0.0


def check_space_drawer(screen: Screen) -> str:
    """Space 미배치 서랍 — 미배치가 가장 많은 층을 열어 대수(서랍 안 층 미정 따로)·이름 오름차순
    위반·검색(빈 알림·`Esc`).

    호기를 끌어 놓지 않고 `적용` 도 누르지 않는다. 층 이름·호기 이름은 고르는 데만 쓴다.
    """
    screen.step("페이지 열기")
    screen.open_space_overview()
    screen.step("층 목록")
    grid, unplaced_column = screen.grid_with_column("미배치대수")
    building_column = screen.column_index(grid, "동")
    floor_column = screen.column_index(grid, "층")
    if building_column is None or floor_column is None:
        return "층 목록 표의 `동`·`층` 칸 없음"
    rows = screen.grid_rows(grid, [building_column, floor_column, unplaced_column])
    floors = [(row[0], row[1], _number(row[2])) for row in rows if row[0] and row[1]]
    candidates = [floor for floor in floors if floor[2] > 0]
    if not candidates:
        return f"미배치 없음(층 {len(floors)}개 모두 0)"
    building, floor, unplaced = max(candidates, key=lambda floor: floor[2])
    screen.step("층 고르기")
    screen.choose_by_typing("층 바로 가기", f"{building} {floor}")
    if screen.selectbox_value("층 바로 가기") != f"{building} {floor}":
        raise RuntimeError("층을 열지 못했다")
    screen.step("서랍")
    if not screen.switch("배치 편집", True):
        return f"미배치 있는 층 {len(candidates)}개 · `배치 편집` 스위치 없음"
    try:
        return _read_drawer(screen, unplaced, len(candidates))
    finally:
        _close_drawer(screen)


def summarize_drawer_counts(
    floors: int,
    table: float,
    total: int,
    floorless: int | None,
    modules: int | None,
    groups: int | None,
) -> str:
    """서랍 머리 — 층 수 · 연 층 표 N · 서랍 N 과 그 안의 층 미정 · 이 층 몫을 표와 견준 것.

    서랍은 이 층 동·층의 미배치에 **층 미정 호기**(동이 비었거나 같은 동에 층만 빈 — 모든 층의
    서랍에 함께 뜬다)를 더해 싣는다. 그래서 기대는 `서랍 N ≥ 표 N` 이고 `서랍 N − 층 미정 = 이 층
    몫` 이 표 N 과 같다. 묶음 모듈은 서랍이 한 대씩, 표는 설비지분(묶음 하나가 1대)으로 세어 이 층
    몫이 표보다 클 수 있다 — 묶음 g개에 모듈 m대면 넘침은 m − g 대라 `이 층 a = 표 N + 묶음 넘침
    (m − g)` 가 서야 묶음으로 설명된다. 서면 그 식을 줄에 적어(`--check-summary` 가 옮겨 적은 수를
    다시 셈한다) 스스로 검산되고, 서지 않으면 `묶음으로 설명 안 됨` 이다(발견). 층 미정을 셀 수
    없으면(편집기 판이 다름) 견주지 않는다."""
    head = f"미배치 있는 층 {floors}개 · 연 층 표 {table:g}대 · 서랍 {total}대"
    if floorless is None or modules is None or groups is None or total < 0:
        return f"{head}(층 미정 못 셈)"
    own = total - floorless
    split = f"{head} = 이 층 {own}대 + 층 미정 {floorless}대"
    if abs(own - table) < 0.005:
        return f"{split} · 이 층 표와 같음"
    if not modules:
        return f"{split} · 이 층 표와 다름"
    surplus = modules - groups
    bundles = f"{split} · 이 층 표와 다름 · 묶음 {groups}개 모듈 {modules}대"
    if abs(own - surplus - table) < 0.005:
        return f"{bundles} · 이 층 {own}대 = 표 {table:g}대 + 묶음 넘침 {surplus}대"
    return f"{bundles} · 묶음으로 설명 안 됨"


def _read_drawer(screen: Screen, unplaced: float, floors: int) -> str:
    tab = screen.page.locator(".sle-drawer-tab").first
    tab.wait_for(state="visible", timeout=ACTION_TIMEOUT_MS)
    tab.click()
    box = screen.page.locator(".sle-tray").first
    tray = screen.wait_for(lambda: box.evaluate(_TRAY_JS), timeout=15)
    total_match = re.fullmatch(r"(\d+)대", str(tray["count"]).strip())
    total = int(total_match.group(1)) if total_match else -1
    head = (
        summarize_drawer_counts(
            floors, unplaced, total, tray["floorless"], tray["modules"], tray.get("groups")
        )
        + f" · 칩 {tray['chips']}개 오름차순 위반 {tray['violations']}"
    )
    first = str(tray["first"])
    if not first:
        return f"{head} · 검색 안 해 봄(칩 없음)"
    search = screen.page.locator(".sle-tray-search").first

    def state() -> Any:
        return box.evaluate(_TRAY_STATE_JS)

    def narrowed(value: Any) -> re.Match[str] | None:
        return re.fullmatch(r"(\d+)/(\d+)대", str(value["count"]).strip())

    def restored(value: Any) -> bool:
        return value["query"] == "" and str(value["count"]).strip() == f"{total}대"

    # 사내 요령: `fill` 은 반응이 없다 — 한 글자씩 친다.
    search.click()
    search.type(first[: min(3, len(first))], delay=40)
    found = narrowed(screen.poll(state, timeout=5, accept=lambda v: narrowed(v) is not None))
    searched = f"검색 됨({found.group(1)}/{found.group(2)}대)" if found else "검색 안 됨"
    search.press("Escape")
    cleared = restored(screen.poll(state, timeout=5, accept=restored))
    search.type("zzz", delay=40)
    empty = bool(screen.poll(state, timeout=5, accept=lambda v: bool(v["empty"]))["empty"])
    search.press("Escape")
    cleared = cleared and restored(screen.poll(state, timeout=5, accept=restored))
    return (
        f"{head} · {searched} · 빈 알림 {'있음' if empty else '없음'} · "
        f"Esc {'지움' if cleared else '안 지움'}"
    )


# Space 층 도면의 호기 상자 class 들(페이더가 바꾸는 판정 class 를 견준다). 상자는 컴포넌트 shadow
# root 안이라 페이더 요소의 뿌리에서 찾는다.
_UNIT_CLASSES_JS = """(fader) => [...fader.getRootNode().querySelectorAll(".sle-unit")]
  .map((unit) => unit.getAttribute("class") || "")"""
# 페이더 날짜 칩이 「오늘」인가(오늘 글자에 강조 class).
_FADER_TODAY_JS = """(fader) => {
  const rel = fader.getRootNode().querySelector(".sle-fader-rel");
  return !!rel && rel.classList.contains("is-today");
}"""
_LEGEND_DATE = re.compile(r"기준 (\d{4}-\d{2}-\d{2})")


def summarize_space_fader(
    placed: float,
    changed: int,
    legend_moved: bool | None,
    back_today: bool,
    *,
    pressed: int = 1,
) -> str:
    """페이더 확인 결과 — 개수·있음/없음만. 날짜·층·호기 이름은 판정에만 쓴다. PageUp 을 다시
    눌렀으면(첫 키가 사라졌으면) 끝에 적는다."""
    moved = "범례 없음" if legend_moved is None else "바뀜" if legend_moved else "안 바뀜"
    again = f" · PageUp {pressed}번(첫 키가 오늘로 돌아감)" if pressed > 1 else ""
    return (
        f"배치 최다 층 {placed:g}대 · +1개월에 class 바뀐 상자 {changed}개 · "
        f"놓은 뒤 범례 기준일 {moved} · 「오늘」 {'돌아옴' if back_today else '안 돌아옴'}{again}"
    )


def check_space_fader(screen: Screen) -> str:
    """Space 기준일 페이더 — 배치가 가장 많은 층을 열어 페이더에 초점을 두고 PageUp(+1개월) 하면
    호기 상자 class(반입 전·반출/이설 예정·숨김 …)가 바뀐 수, 키를 멈춘 뒤 머리 줄 범례의 「기준」
    날짜가 바뀌었는가, 「오늘」 단추로 오늘에 돌아오는가. 쓰지 않는다(기준일은 세션 값이다)."""
    screen.step("페이지 열기")
    screen.open_space_overview()
    screen.step("층 목록")
    grid, placed_column = screen.grid_with_column("배치대수")
    building_column = screen.column_index(grid, "동")
    floor_column = screen.column_index(grid, "층")
    if building_column is None or floor_column is None:
        return "층 목록 표의 `동`·`층` 칸 없음"
    rows = screen.grid_rows(grid, [building_column, floor_column, placed_column])
    floors = [(row[0], row[1], _number(row[2])) for row in rows if row[0] and row[1]]
    candidates = [floor for floor in floors if floor[2] > 0]
    if not candidates:
        return f"배치 없음(층 {len(floors)}개 모두 0)"
    building, floor, placed = max(candidates, key=lambda floor: floor[2])
    screen.step("층 고르기")
    screen.choose_by_typing("층 바로 가기", f"{building} {floor}")
    if screen.selectbox_value("층 바로 가기") != f"{building} {floor}":
        raise RuntimeError("층을 열지 못했다")
    screen.step("페이더")
    fader = screen.page.locator(".sle-fader-input").first
    try:
        fader.wait_for(state="visible", timeout=ACTION_TIMEOUT_MS)
    except Exception:  # noqa: BLE001 — 페이더가 없는 배포다. 있음/없음만 적는다
        return f"배치 최다 층 {placed:g}대 · 페이더 없음"
    today = screen.page.locator(".sle-fader-today").first

    def legend() -> str | None:
        found = _LEGEND_DATE.search(screen.main_text())
        return found.group(1) if found else None

    def at_today() -> bool:
        return bool(fader.evaluate(_FADER_TODAY_JS))

    before_legend = legend()
    before = fader.evaluate(_UNIT_CLASSES_JS)
    pressed = 0
    try:
        # 페이더가 오늘을 떠났는지 보고, 그대로면 한 번 더 누른다 — 층을 옮긴 회차의 늦은
        # 그림(새 epoch)이 누른 날을 오늘로 되돌리면 키가 사라진다.
        screen.step("PageUp")
        while pressed < 2 and (pressed == 0 or at_today()):
            if pressed:
                screen.wait_idle()
            fader.focus()
            fader.press("PageUp")
            pressed += 1
            screen.poll(at_today, timeout=3, accept=lambda value: not value)
        after = screen.poll(
            lambda: fader.evaluate(_UNIT_CLASSES_JS), timeout=5, accept=lambda v: v != before
        )
        changed = sum(1 for old, new in zip(before, after, strict=False) if old != new)
        screen.step("범례")
        moved_legend = screen.poll(legend, timeout=20, accept=lambda v: v != before_legend)
        screen.wait_idle()
        legend_moved = None if before_legend is None else moved_legend != before_legend
    finally:
        # 페이더가 오늘이면 「오늘」 단추는 꺼져 있다(`disabled`) — 누르면 켜지기를 30초 기다리다
        # `TimeoutError` 로 끝나 위 결과를 가린다. 켜져 있을 때만 누른다.
        failed_at = screen.current_step
        screen.step("「오늘」")
        if today.is_enabled():
            today.click()
        back = bool(screen.poll(at_today, timeout=10, accept=bool))
        back = back and screen.poll(legend, timeout=20, accept=lambda v: v == before_legend) == (
            before_legend
        )
        screen.wait_idle()
        # 위에서 예외가 났으면 미기록 칸은 그 단계를 말해야 한다.
        screen.current_step = failed_at
    return summarize_space_fader(placed, changed, legend_moved, back, pressed=pressed)


def _close_drawer(screen: Screen) -> None:
    """검색 칸·서랍을 비우고 `배치 편집` 을 끈다. 놓은 호기가 없으니 `처음 상태로` 는 필요 없다."""
    try:
        box = screen.page.locator(".sle-tray")
        if box.count() == 0:
            return
        current = box.first.evaluate(_TRAY_STATE_JS)
        if current["query"]:
            screen.page.locator(".sle-tray-search").first.press("Escape")
        if current["open"]:
            screen.page.locator(".sle-drawer-close").first.click()
    finally:
        screen.switch("배치 편집", False)


# 사이드바 「조회 조건」 구역 — 제목 글, 패널 줄의 이름 글(판정에만 쓴다), 그 이름의 조건 카드 수와
# 그 카드가 패널 아래에 섰는지.
_PANEL_JS = """(keys) => {
  const side = document.querySelector('[data-testid="stSidebar"]');
  if (!side) return null;
  const heading = side.querySelector(`.st-key-${keys.section} [data-testid="stCaptionContainer"]`);
  const panel = side.querySelector(`.st-key-${keys.box}`);
  const rows = panel
    ? [...panel.querySelectorAll(`[class*="st-key-${keys.row}"]`)].map((row) => {
        const caption = row.querySelector('[data-testid="stCaptionContainer"]');
        return caption ? caption.innerText.trim() : "";
      })
    : null;
  const cards = [...side.querySelectorAll(`[class*="st-key-${keys.card}"]`)].filter(
    (card) => (card.querySelector("summary") || card).innerText.includes(keys.label));
  const bottom = panel ? panel.getBoundingClientRect().bottom : null;
  return {
    title: heading ? heading.innerText.trim() : null,
    rows,
    cards: cards.length,
    below: cards.length > 0 && bottom !== null
      && cards[0].getBoundingClientRect().top >= bottom - 0.5,
  };
}"""
# 시나리오 팝업 — 구획 조절(`st.segmented_control`)의 선택지 글과 고른 것, 리비전 라디오 선택지 수.
_SCENARIO_DIALOG_JS = """(box, radio) => {
  const group = box.querySelector('[data-testid="stButtonGroup"] [role="radiogroup"]');
  const chosen = group && group.querySelector('[role="radio"][aria-checked="true"]');
  const list = [...box.querySelectorAll('[role="radiogroup"]')]
    .find((g) => g.getAttribute("aria-label") === radio);
  const modes = group ? [...group.querySelectorAll('[role="radio"]')] : [];
  return {
    modes: modes.map((button) => button.innerText.trim()),
    selected: chosen ? chosen.innerText.trim() : null,
    revisions: list ? list.querySelectorAll('input[type="radio"]').length : null,
  };
}"""
# 조회기간 팝업 — 월 입력 칸 수와 「적용」 단추(월 선택 컴포넌트 안인가). 컴포넌트는 그림자 DOM 으로
# 가두지 않아(`isolate_styles=False`) `querySelector` 로 닿는다.
_PERIOD_DIALOG_JS = """(box, ids) => {
  const months = ids.inputs
    .map((id) => box.querySelector(`#${id}`))
    .filter((input) => input && input.getAttribute("type") === "month");
  const apply = box.querySelector(`#${ids.apply}`);
  return {
    months: months.length,
    apply: apply ? apply.textContent.trim() : null,
    inComponent: !!(apply && apply.closest('[data-testid^="stBidiComponent"]')),
  };
}"""
# 공정 필터 팝업 — 판정 기준 안내 한 줄이 작업 줄(첫 단추)보다 위, 곧 머리에 섰는가.
_PROCESS_DIALOG_JS = """(box, pointer) => {
  const hit = [...box.querySelectorAll('[data-testid="stCaptionContainer"]')]
    .find((caption) => caption.innerText.trim() === pointer);
  if (!hit) return { pointer: "none" };
  const first = box.querySelector('[data-testid="stButton"]');
  if (!first) return { pointer: "head" };
  const head = hit.getBoundingClientRect().top < first.getBoundingClientRect().top;
  return { pointer: head ? "head" : "body" };
}"""


# 글 한 칸(문단)이 어떻게 잘리는지 — 넘쳤는지(`clipped`), 말줄임이 실제로 그려지는지
# (`ellipsis` — 계산값 `text-overflow` 만으로는 모른다. 문단이 `overflow` 를 보이게 두면 말줄임은
# 그려지지 않는다), 글이 `stop` 앞까지의 조상 중 잘라 내는 칸 밖으로 나갔는지(`cut` — 문단
# 안에서는 넘치지 않아도 조상이 글자를 반쯤 자른다). 글 끝은 글자 범위로 재고, 문단이 스스로
# 잘라 내면 문단 끝까지만 본다.
_TEXT_CLIP_JS = """(p, stop) => {
  const style = getComputedStyle(p);
  const ownClip = style.overflowX !== "visible";
  const range = document.createRange();
  range.selectNodeContents(p);
  const textRight = range.getBoundingClientRect().right;
  const right = ownClip ? Math.min(textRight, p.getBoundingClientRect().right) : textRight;
  let cut = false;
  for (let el = p.parentElement; el && el !== stop; el = el.parentElement) {
    const clips = getComputedStyle(el).overflowX !== "visible";
    if (clips && right > el.getBoundingClientRect().right + 1) {
      cut = true;
      break;
    }
  }
  return {
    clipped: p.scrollWidth > p.clientWidth + 1,
    ellipsis: style.textOverflow === "ellipsis" && ownClip,
    cut,
  };
}"""


# 사이드바 그룹 상자 — 화면 차례대로 상자마다 slug·제목 글(판정에만 쓴다)·링크 수, 그리고 제목이 한
# 줄인지(줄 상자 수)와 잘림 셋(`_TEXT_CLIP_JS` — 조상은 상자 앞까지 본다). 접힌 상자도 링크는 DOM 에
# 있다(`Screen.open_page` 가 그것을 찾아 편다).
_SIDEBAR_GROUPS_JS = (
    """(slugs) => {
  const textClip = """
    + _TEXT_CLIP_JS
    + """;
  const side = document.querySelector('[data-testid="stSidebar"]');
  if (!side) return null;
  const boxes = [...side.querySelectorAll(slugs.map((slug) => `.st-key-${slug}_box`).join(", "))];
  return boxes.map((box) => {
    const slug = slugs.find((name) => box.classList.contains(`st-key-${name}_box`));
    const label = box.querySelector('summary [data-testid="stMarkdownContainer"] p');
    let lines = 0;
    let clip = { clipped: false, ellipsis: false, cut: false };
    if (label) {
      const range = document.createRange();
      range.selectNodeContents(label);
      lines = new Set([...range.getClientRects()].map((r) => Math.round(r.top))).size;
      clip = textClip(label, box);
    }
    return {
      slug,
      title: label ? label.innerText.trim() : null,
      links: box.querySelectorAll('a[data-testid="stPageLink-NavLink"]').length,
      lines,
      ...clip,
    };
  });
}"""
)


# 사이드바를 `width` 로 좁혀 위와 같은 꼴로 재고 원래 폭으로 되돌린다. 실제로 선 폭(px)과,
# 사이드바 페이지 링크 글 중 말줄임 없이 잘린 수(`links_cut` — 넘쳤는데 말줄임이 없거나 링크까지의
# 조상이 자른다)를 함께 돌려준다. 링크는 접힌 그룹 안 것도 센다 — 같은 폭에서 펴면 그대로 보인다.
# 사이드바의 폭 전환(0.3초)을 끄고 재야 중간 폭을 읽지 않는다.
_SIDEBAR_GROUPS_NARROW_JS = (
    """async ({slugs, width}) => {
  const side = document.querySelector('[data-testid="stSidebar"]');
  if (!side) return null;
  const saved = side.getAttribute("style");
  side.style.transition = "none";
  side.style.width = side.style.minWidth = side.style.maxWidth = `${width}px`;
  await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
  const measure = """
    + _SIDEBAR_GROUPS_JS
    + """;
  const textClip = """
    + _TEXT_CLIP_JS
    + """;
  const boxes = measure(slugs);
  const links = side.querySelectorAll(
    'a[data-testid="stPageLink-NavLink"] [data-testid="stMarkdownContainer"] p'
  );
  const linksCut = [...links].filter((p) => {
    const link = p.closest('a[data-testid="stPageLink-NavLink"]');
    const clip = textClip(p, link.parentElement);
    return clip.cut || (clip.clipped && !clip.ellipsis);
  }).length;
  const shown = Math.round(side.getBoundingClientRect().width);
  if (saved === null) side.removeAttribute("style");
  else side.setAttribute("style", saved);
  return { width: shown, boxes, links_cut: linksCut };
}"""
)


def _sidebar_button(widget_key: str) -> str:
    """사이드바 위젯 key 의 단추 선택자(Streamlit 은 key 를 `st-key-<key>` 클래스로 단다)."""
    return f'[data-testid="stSidebar"] .st-key-{widget_key} button'


def panel_row_name(text: str) -> str:
    """패널 줄 이름 글을 정한 어휘(`PANEL_ROW_NAMES` 와 설비 시나리오 줄)로. 시나리오 줄은
    「시나리오 · rN」이라 앞머리로 가른다 — 리비전 번호는 값이라 옮기지 않는다. 어휘에 없으면
    「그 밖」."""
    head = text.strip()
    if head == EQUIPMENT_SCENARIO_ROW_NAME:
        return EQUIPMENT_SCENARIO_ROW_NAME
    for name in PANEL_ROW_NAMES:
        if head == name or head.startswith(f"{name} · "):
            return name
    return UNKNOWN_ROW_NAME


def _row_names(rows: Sequence[object] | None) -> tuple[str, ...] | None:
    return None if rows is None else tuple(panel_row_name(str(text)) for text in rows)


def _rows_text(names: Sequence[str]) -> str:
    return " · ".join(names) if names else "줄 없음"


def _panel_facts(screen: Screen) -> Any:
    return screen.js(
        _PANEL_JS,
        {
            "section": CONDITIONS_SECTION_KEY,
            "box": CONDITIONS_BOX_KEY,
            "row": CONDITION_NAME_ROW_PREFIX,
            "card": CONDITION_CARD_PREFIX,
            "label": LOB_CARD_LABEL,
        },
    )


def _closed_text(closed: bool) -> str:
    return "Esc 닫힘" if closed else "Esc 안 닫힘"


def _title_text(title: str | None, expected: str) -> str:
    return f"팝업 제목 「{expected}」 {'같음' if title == expected else '다름'}"


def summarize_panel(facts: Mapping[str, Any] | None, old_titles: int) -> str:
    """HOME Main 탭의 패널 — 구역 제목·줄 이름 차례와 수·옛 상자 제목 수·LOB 카드 자리."""
    if not facts or facts["rows"] is None:
        return f"「{CONDITIONS_SECTION_TITLE}」 패널 없음 · 옛 상자 제목 {old_titles}곳"
    names = _row_names(facts["rows"]) or ()
    heading = "있음" if facts["title"] == CONDITIONS_SECTION_TITLE else "없음"
    order = "같음" if names == PANEL_ROW_NAMES else "다름"
    if not facts["cards"]:
        card = "없음"
    else:
        card = "패널 아래 있음" if facts["below"] else "있음(패널 아래 아님)"
    return (
        f"「{CONDITIONS_SECTION_TITLE}」 제목 {heading} · 패널 {len(names)}줄({_rows_text(names)}) "
        f"— 정한 차례와 {order} · 옛 상자 제목 {old_titles}곳 · {LOB_CARD_LABEL} 카드 {card}"
    )


def summarize_other_pages(
    seen: Sequence[tuple[str, tuple[str, ...] | None, Sequence[object] | None]],
) -> str:
    """(화면 이름, 정한 줄 이름, 읽은 줄 이름 글) 마다 줄 수와 이름, 끝에 정한 대로인가."""
    parts: list[str] = []
    matched = True
    for title, expected, rows in seen:
        names = _row_names(rows)
        matched = matched and names == expected
        parts.append(
            f"{title} 패널 없음"
            if names is None
            else f"{title} {len(names)}줄({_rows_text(names)})"
        )
    return f"{' · '.join(parts)} — 정한 대로 {'같음' if matched else '다름'}"


def summarize_scenario_dialog(
    title: str | None, facts: Mapping[str, Any] | None, closed: bool
) -> str:
    if title is None:
        return "팝업 안 열림"
    modes = tuple(facts["modes"]) if facts else ()
    control = "있음" if modes == SCENARIO_DIALOG_MODES else "없음"
    selected = facts["selected"] if facts else None
    load, save = SCENARIO_DIALOG_MODES
    if selected == load:
        revisions = facts["revisions"] if facts else None
        listed = "리비전 목록 없음" if revisions is None else f"리비전 {int(revisions)}개"
    elif selected == save:
        listed = "저장 구획으로 열림(리비전 목록 안 셈)"
    else:
        listed = "구획 모름"
    # 구획 둘은 화면에서 「불러오기 | 새 리비전 저장」 한 조절이다. 결과 표는 `|` 를 `/` 로 바꾸므로
    # 이름을 따로 묶어 적는다.
    names = "·".join(f"「{mode}」" for mode in SCENARIO_DIALOG_MODES)
    return (
        f"{_title_text(title, SCENARIO_DIALOG_TITLE)} · 구획 {names} {control} · {listed} · "
        f"{_closed_text(closed)}"
    )


def summarize_period_dialog(
    title: str | None, facts: Mapping[str, Any] | None, closed: bool, same: bool
) -> str:
    if title is None:
        return "팝업 안 열림"
    months = int(facts["months"]) if facts else 0
    if not facts or facts["apply"] != MONTH_APPLY_LABEL:
        apply = "없음"
    else:
        apply = "컴포넌트 안 있음" if facts["inComponent"] else "있음(컴포넌트 밖)"
    return (
        f"{_title_text(title, PERIOD_DIALOG_TITLE)} · 월 칸 {months}개 · "
        f"「{MONTH_APPLY_LABEL}」 단추 {apply} · {_closed_text(closed)}(적용 안 함) · "
        f"값 칸 글자 {'같음' if same else '다름'}"
    )


def summarize_process_dialog(
    title: str | None, facts: Mapping[str, Any] | None, closed: bool
) -> str:
    if title is None:
        return "팝업 안 열림"
    place = facts["pointer"] if facts else "none"
    pointer = {"head": "머리에 있음", "body": "머리에 없음(아래에 있음)"}.get(place, "없음")
    return (
        f"{_title_text(title, PROCESS_DIALOG_TITLE)} · 판정 기준 안내 {pointer} · "
        f"{_closed_text(closed)}"
    )


def check_sidebar_panel(screen: Screen) -> str:
    """HOME Main 탭의 「조회 조건」 패널 — 줄 이름 차례·수, 옛 상자 제목, 아래 `LOB 표시 조건` 카드.

    공정 필터·주요공정 히트맵 줄은 HOME 계산 뒤에 차므로 네 줄이 설 때까지 기다린다.
    """
    screen.open_home()
    screen.open_tab(HOME_MAIN_TAB)
    facts = screen.poll(
        lambda: _panel_facts(screen),
        timeout=60,
        accept=lambda value: (
            bool(value) and value["rows"] is not None and len(value["rows"]) >= len(PANEL_ROW_NAMES)
        ),
    )
    old_titles = sum(screen.sidebar_text().count(title) for title in OLD_BOX_TITLES)
    return summarize_panel(facts, old_titles)


def check_panel_rows_other_pages(screen: Screen) -> str:
    """시나리오 관리(시나리오·조회기간)·Admin Area(시나리오)·Space 현황(설비 시나리오)의 패널 줄."""
    seen: list[tuple[str, tuple[str, ...] | None, Sequence[object] | None]] = []
    for page, title, expected in OTHER_PAGE_PANELS:
        screen.open_page(page)
        facts = _panel_facts(screen)
        seen.append((title, expected, facts["rows"] if facts else None))
    return summarize_other_pages(seen)


def check_scenario_popup(screen: Screen) -> str:
    """HOME 시나리오 칸의 팝업 — 제목·구획 조절·리비전 수. 불러오기·저장은 누르지 않고 `Esc` 로
    닫는다."""
    screen.open_home()
    screen.open_dialog(_sidebar_button(SCENARIO_FIELD_KEY))
    load = SCENARIO_DIALOG_MODES[0]
    try:
        title = screen.dialog_title()
        facts = screen.poll(
            lambda: screen.dialog_read(_SCENARIO_DIALOG_JS, REVISION_RADIO_LABEL),
            timeout=30,
            accept=lambda value: (
                bool(value)
                and bool(value["modes"])
                and (value["selected"] != load or value["revisions"] is not None)
            ),
        )
    finally:
        closed = screen.close_dialog()
    return summarize_scenario_dialog(title, facts, closed)


def check_period_popup(screen: Screen) -> str:
    """HOME 조회기간 칸의 팝업 — 월 칸·컴포넌트 안 「적용」. 적용하지 않고 `Esc` 로 닫은 뒤 칸
    글자를 견준다(글자는 기간 값이라 같음·다름만 찍는다)."""
    screen.open_home()
    selector = _sidebar_button(PERIOD_FIELD_KEY)
    before = str(screen.page.locator(selector).first.inner_text())
    screen.open_dialog(selector)
    try:
        title = screen.dialog_title()
        # 팝업이 먼저 서고 월 선택 컴포넌트는 그 뒤에 붙는다.
        facts = screen.poll(
            lambda: screen.dialog_read(
                _PERIOD_DIALOG_JS, {"inputs": list(MONTH_INPUT_IDS), "apply": MONTH_APPLY_ID}
            ),
            timeout=30,
            accept=lambda value: (
                bool(value) and value["months"] >= len(MONTH_INPUT_IDS) and bool(value["apply"])
            ),
        )
    finally:
        closed = screen.close_dialog()
    after = str(screen.page.locator(selector).first.inner_text())
    return summarize_period_dialog(title, facts, closed, before == after)


def check_process_popup(screen: Screen) -> str:
    """HOME 공정 필터 칸의 팝업 — 제목과 머리의 판정 기준 안내. 공정을 고르지 않고 `Esc` 로
    닫는다."""
    screen.open_home()
    selector = _sidebar_button(PROCESS_FIELD_KEY)
    field = screen.page.locator(selector).first
    field.wait_for(state="visible", timeout=60_000)
    if field.is_disabled():
        return "공정 필터 칸 잠김 — 팝업 안 열어 봄"
    screen.open_dialog(selector)
    try:
        title = screen.dialog_title()
        facts = screen.poll(
            lambda: screen.dialog_read(_PROCESS_DIALOG_JS, THRESHOLD_POINTER),
            timeout=30,
            accept=lambda value: bool(value) and value["pointer"] != "none",
        )
    finally:
        closed = screen.close_dialog()
    return summarize_process_dialog(title, facts, closed)


_PROCESS_DETAIL_JS = """(keys) => {
  const q = (selector) => document.querySelector(selector);
  const panel = q(`.st-key-${keys.evidence}`);
  const head = panel ? (panel.innerText.match(/산출 근거 · (\\d\\d\\.\\d\\d)/) || [])[1] : null;
  const scroll = q(`.st-key-${keys.scroll}`);
  const plot = q(`.st-key-${keys.canvas} .js-plotly-plot`);
  let point = null;
  if (scroll && plot) {
    const box = scroll.getBoundingClientRect();
    point = {x: box.left + 250, y: plot.getBoundingClientRect().top + keys.rowPx};
  }
  return {
    kpis: document.querySelectorAll(`.st-key-${keys.kpi} [data-testid="stMetric"]`).length,
    canvas: !!plot,
    month: head || null,
    cards: panel ? panel.querySelectorAll('.pcd-card').length : 0,
    absent: !!q(`.st-key-${keys.absent}`),
    point,
  };
}"""


def summarize_process_detail(before: Mapping[str, Any], after: Mapping[str, Any] | None) -> str:
    """공정 Capa 상세 한 줄 — 개수와 있음/없음, 칸을 누른 뒤 근거 패널의 달이 바뀌었는가."""
    schedule = "없음(까닭 카드)" if before.get("absent") else "있음"
    canvas = "있음" if before.get("canvas") else "없음"
    if after is None:
        clicked = "못 누름"
    else:
        clicked = "바뀜" if after.get("month") != before.get("month") else "그대로"
    return (
        f"KPI {before.get('kpis', 0)}개 · 결합 캔버스 {canvas} · "
        f"근거 카드 {before.get('cards', 0)}개 · 설비 일정 구획 {schedule} · "
        f"칸 누름 뒤 근거 달 {clicked}"
    )


def check_process_detail(screen: Screen) -> str:
    """`공정 Capa 상세` — 기본 공정으로 열어 KPI·결합 캔버스·근거 카드·설비 일정 구획을 세고, 월
    그림의 보이는 셋째 칸(확보율 줄)을 한 번 눌러 근거 패널의 달이 바뀌는지 본다. 공정·제품 이름은
    찍지 않는다(판정에만 쓰고 버린다). 칸 누름은 보는 조건이라 DB 에 쓰지 않는다."""
    screen.open_page(PROCESS_DETAIL_PAGE)
    keys = {**PROCESS_DETAIL_KEYS, "rowPx": PROCESS_DETAIL_RATE_ROW_PX}
    before = screen.wait_for(
        lambda: screen.js(_PROCESS_DETAIL_JS, keys),
        timeout=120,
        accept=lambda value: bool(value) and bool(value["canvas"]) and value["month"] is not None,
    )
    point = before.get("point")
    after: Mapping[str, Any] | None = None
    if point is not None:
        screen.page.mouse.click(float(point["x"]), float(point["y"]))
        screen.wait_idle()
        after = screen.poll(
            lambda: screen.js(_PROCESS_DETAIL_JS, keys),
            timeout=30,
            accept=lambda value: bool(value) and value["month"] != before["month"],
        )
    return summarize_process_detail(before, after)


# 공정 선택 상자가 지금 고른 값(표시명). Streamlit 1.63 selectbox 는 고른 값을 콤보 상자 `<input>`
# 의 `value` 에만 둔다 — 상자의 `innerText` 는 카드가 접혀 있으면 빈 글자, 펴 있으면 라벨 「공정」
# 뿐이다.
_SELECTED_VALUE_JS = """const selectedValue = (box) => {
    if (!box) return null;
    const input = box.querySelector('input');
    return input ? String(input.value || '').trim() : null;
  };"""

_CONSTRAINT_LINK_JS = (
    """(keys) => {
  """
    + _SELECTED_VALUE_JS
    + """
  const links = Array.from(document.querySelectorAll('[data-testid="stMain"] a'));
  const link = links.find((item) => item.innerText.includes(keys.label));
  const process = selectedValue(document.querySelector(`.st-key-${keys.detailProcess}`));
  const kpis = document.querySelectorAll(
    '.st-key-process_detail_kpis [data-testid="stMetric"]'
  ).length;
  if (!link) return {found: false, ready: kpis > 0, process};
  const disabled =
    link.getAttribute('aria-disabled') === 'true' ||
    link.hasAttribute('disabled') ||
    getComputedStyle(link).pointerEvents === 'none';
  return {found: true, disabled, ready: kpis > 0, process};
}"""
)

_CONSTRAINT_JS = (
    """(keys) => {
  """
    + _SELECTED_VALUE_JS
    + """
  const q = (selector) => document.querySelector(selector);
  const steps = q(`.st-key-${keys.steps}`);
  const month = steps ? (steps.innerText.match(/(\\d\\d\\.\\d\\d) · /) || [])[1] : null;
  const blocks = (root) =>
    root ? Array.from(root.querySelectorAll('[data-testid="stMarkdownContainer"]')) : [];
  const stepCount = blocks(steps).filter((item) => /^\\d · /.test(item.innerText.trim())).length;
  const lines = blocks(q(`.st-key-${keys.schedule}`)).filter(
    (item) => item.innerText.includes(' 몫 · ')
  ).length;
  const chart = q(`.st-key-${keys.chart} .js-plotly-plot`);
  let point = null;
  if (chart && month) {
    const ticks = Array.from(chart.querySelectorAll('.xtick text')).map(
      (item) => item.textContent
    );
    const drag =
      chart.querySelector('.nsewdrag[data-subplot="xy"]') || chart.querySelector('.nsewdrag');
    const index = ticks.findIndex((text) => text !== month);
    if (drag && index >= 0) {
      const box = drag.getBoundingClientRect();
      point = {
        x: box.left + (box.width * (index + 0.5)) / ticks.length,
        y: box.top + box.height / 2,
      };
    }
  }
  return {
    kpis: document.querySelectorAll(`.st-key-${keys.kpi} [data-testid="stMetric"]`).length,
    chart: !!chart,
    sheet: !!q(`.st-key-${keys.sheet} .js-plotly-plot`),
    steps: stepCount,
    schedule: lines,
    month: month || null,
    absent: !!q(`.st-key-${keys.absent}`),
    process: selectedValue(q(`.st-key-${keys.process}`)),
    point,
  };
}"""
)


def constraint_process_matches(
    link: Mapping[str, Any] | None, before: Mapping[str, Any]
) -> bool | None:
    """링크로 연 제약 시뮬레이션의 공정이 공정 Capa 상세에서 보던 공정과 같은가 — 두 공정 상자의
    지금 값(둘 다 같은 표시명 규칙 `unique_format_func`)끼리 견준다. 링크를 누르지
    않았으면(없음·꺼짐) None. 어느 쪽 값이든 읽지 못했으면 거짓이다(같다고 짐작하지 않는다)."""
    if link is None or not link.get("found") or link.get("disabled"):
        return None
    detail = str(link.get("process") or "").strip()
    here = str(before.get("process") or "").strip()
    return bool(detail) and detail == here


def summarize_constraint_simulation(
    link: Mapping[str, Any] | None,
    before: Mapping[str, Any],
    after: Mapping[str, Any] | None,
    same_process: bool | None,
) -> str:
    """제약 시뮬레이션 한 줄 — 공정 Capa 상세 머리 링크(켜짐·꺼짐), 넘어온 공정이 같은가,
    KPI·그림·표·계산 단계·개조 일정 줄 수, 그래프 칸을 누른 뒤 고른 달이 바뀌었는가. 공정·제품·달
    글자는 찍지 않는다."""
    if link is None or not link.get("found"):
        head = "링크 없음"
    elif link.get("disabled"):
        head = "링크 꺼짐(까닭)"
    else:
        head = "링크 켜짐"
    if same_process is not None:
        head += f" · 공정 {'같음' if same_process else '다름'}"
    if before.get("absent"):
        return f"{head} · 설비 일정 없음(까닭 카드)"
    if after is None:
        clicked = "못 누름"
    else:
        clicked = "바뀜" if after.get("month") != before.get("month") else "그대로"
    chart = "있음" if before.get("chart") else "없음"
    sheet = "있음" if before.get("sheet") else "없음"
    return (
        f"{head} · KPI {before.get('kpis', 0)}개 · 그림 {chart} · 표 {sheet} · "
        f"계산 {before.get('steps', 0)}단계 · 개조 일정 {before.get('schedule', 0)}줄 · "
        f"칸 누름 뒤 고른 달 {clicked}"
    )


def check_constraint_simulation(screen: Screen) -> str:
    """`제약 시뮬레이션` — 공정 Capa 상세(기본 공정) 머리 「이 공정 제약 시뮬레이션」 을 눌러 같은
    공정으로 열리는지 보고(링크가 꺼졌으면 사이드바로 연다), KPI·그래프·계산표·고른 달 계산·개조
    일정을 센 뒤 그래프의 다른 달 칸을 한 번 눌러 고른 달이 바뀌는지 본다. 저장하지 않는 화면이라 DB
    에 쓰지 않는다."""
    screen.open_page(PROCESS_DETAIL_PAGE)
    arg = {**CONSTRAINT_KEYS, "label": CONSTRAINT_LINK_LABEL}
    link = screen.wait_for(
        lambda: screen.js(_CONSTRAINT_LINK_JS, arg), timeout=120, accept=lambda v: bool(v["ready"])
    )
    if link.get("found") and not link.get("disabled"):

        def arrived() -> bool:
            return screen.path().rstrip("/").endswith(CONSTRAINT_PAGE)

        screen.page.locator(
            '[data-testid="stMain"] a', has_text=CONSTRAINT_LINK_LABEL
        ).first.click()
        screen.wait_for(arrived, timeout=30)
        screen.wait_idle()
    else:
        screen.open_page(CONSTRAINT_PAGE)
    before = screen.wait_for(
        lambda: screen.js(_CONSTRAINT_JS, CONSTRAINT_KEYS),
        timeout=120,
        accept=lambda value: (
            bool(value)
            and (bool(value["absent"]) or (bool(value["chart"]) and value["month"] is not None))
        ),
    )
    same_process = constraint_process_matches(link, before)
    after: Mapping[str, Any] | None = None
    point = before.get("point")
    if point is not None and not before.get("absent"):
        screen.page.mouse.click(float(point["x"]), float(point["y"]))
        screen.wait_idle()
        after = screen.poll(
            lambda: screen.js(_CONSTRAINT_JS, CONSTRAINT_KEYS),
            timeout=30,
            accept=lambda value: bool(value) and value["month"] != before["month"],
        )
    return summarize_constraint_simulation(link, before, after, same_process)


def summarize_page_tabs(
    opened: Sequence[Mapping[str, Any]],
    back_home: bool,
    closed: Sequence[Mapping[str, Any]],
) -> str:
    """화면 탭 줄 한 줄 — 사이드바로 한 화면을 연 뒤의 탭 수, 탭으로 HOME 에 돌아갔는가, × 로
    닫은 뒤 탭 수. 정한 동작은 「HOME(고정) + 연 화면 = 2 → HOME 탭으로 돌아감 → 닫으면 1」 이다."""
    active = sum(1 for tab in opened if tab.get("active"))
    pinned_home = bool(opened) and bool(opened[0].get("pinned")) and not opened[0].get("closable")
    same = len(opened) == 2 and active == 1 and pinned_home and back_home and len(closed) == 1
    return (
        f"연 뒤 탭 {len(opened)} · HOME 고정 {'있음' if pinned_home else '없음'} · "
        f"탭으로 HOME {'옮김' if back_home else '못 옮김'} · 닫은 뒤 탭 {len(closed)} — "
        f"정한 동작과 {'같음' if same else '다름'}"
    )


def _close_first_closable_tab(screen: Screen) -> bool:
    """닫을 수 있는 첫 탭을 × 로 닫는다. 닫을 탭이 없으면 False."""
    before = len(screen.page_tabs())
    index = next((i for i, tab in enumerate(screen.page_tabs()) if tab["closable"]), None)
    if index is None:
        return False
    item = screen.tab_item(index)
    item.hover()
    item.locator(".capa-tabs-x").click()
    screen.poll(lambda: len(screen.page_tabs()), timeout=10, accept=lambda n: n < before)
    screen.wait_idle()
    return True


def check_page_tabs(screen: Screen) -> str:
    """머리 띠 아래 화면 탭 줄 — HOME 에서 다른 탭을 모두 닫고, 사이드바로 한 화면을 연 뒤 탭 수,
    탭으로 HOME 에 돌아가는가, 그 화면 탭을 × 로 닫은 뒤 탭 수를 센다. 개수와 있음/없음만
    찍는다. 보는 조작이라 DB 에 쓰지 않는다."""
    screen.open_home()
    # 상한 자리 비우기(`make_tab_room`)와 같은 길로 닫을 수 있는 탭을 모두 닫는다.
    for _ in range(PAGE_TABS_MAX):
        if not _close_first_closable_tab(screen):
            break
    screen.open_page(SCENARIO_MANAGEMENT_PAGE)
    opened = screen.page_tabs()
    screen.tab_item(0).locator(".capa-tabs-tab").click()
    back_home = bool(screen.poll(lambda: screen.path() in ("", "/"), timeout=20, accept=bool))
    screen.wait_idle()
    other = screen.tab_item(1)
    other.hover()
    other.locator(".capa-tabs-x").click()
    closed = screen.poll(lambda: screen.page_tabs(), timeout=10, accept=lambda tabs: len(tabs) < 2)
    screen.wait_idle()
    return summarize_page_tabs(opened, back_home, closed)


def summarize_sidebar_groups(found: Sequence[Mapping[str, Any]] | None) -> str:
    """사이드바 그룹 상자 한 줄 — 상자마다 「제목 머리 + 하위 수」, 정한 차례·수와 같은지, 상자
    제목이 한 줄로 다 보이는지. 제목은 고정 어휘(`SIDEBAR_GROUP_BOXES`)에서 적고 화면 글자는
    같은지만 본다."""
    if not found:
        return "그룹 상자 없음"
    titles = {slug: title for slug, title, _ in SIDEBAR_GROUP_BOXES}
    parts: list[str] = []
    for box in found:
        slug = str(box.get("slug"))
        title = titles.get(slug, "그 밖")
        mark = "" if box.get("title") == title else "(제목 다름)"
        parts.append(f"{title}{mark} 머리 + {max(int(box.get('links') or 0) - 1, 0)}")
    seen = [(str(box.get("slug")), int(box.get("links") or 0) - 1) for box in found]
    expected = [(slug, count) for slug, _, count in SIDEBAR_GROUP_BOXES]
    same = seen == expected and all(
        box.get("title") == titles.get(str(box.get("slug"))) for box in found
    )
    missing = [title for slug, title, _ in SIDEBAR_GROUP_BOXES if slug not in dict(seen)]
    verdict = "정한 차례·수와 같음" if same else "정한 차례·수와 다름"
    if missing:
        verdict += f"(없음: {', '.join(missing)})"
    wrapped = [titles.get(str(box.get("slug")), "그 밖") for box in found if box.get("lines") != 1]
    clipped = [
        titles.get(str(box.get("slug")), "그 밖")
        for box in found
        if box.get("clipped") or box.get("cut")
    ]
    label = "상자 제목 한 줄 · 잘림 없음"
    if wrapped or clipped:
        notes = []
        if wrapped:
            notes.append(f"줄바꿈: {', '.join(wrapped)}")
        if clipped:
            notes.append(f"잘림: {', '.join(clipped)}")
        label = " · ".join(notes)
    return f"{' · '.join(parts)} — {verdict} · {label}"


def summarize_sidebar_narrow(narrow: Mapping[str, Any] | None) -> str:
    """좁게 끈 사이드바 한 조각 — 그 폭에서 그룹 상자 제목이 모두 한 줄이고 넘친 끝이 말줄임인가.
    말줄임은 정한 모양이라 결함이 아니고 그 수만 적는다. 결함은 줄바꿈(낱말 가운데서 접힌다)과
    말줄임 없이 잘림(넘쳤는데 말줄임이 없거나 조상 칸이 글자를 반쯤 자른다 — 그룹 제목과 페이지
    링크, 링크는 접힌 그룹 안 것도)이다."""
    boxes = narrow.get("boxes") if narrow else None
    if not narrow or not boxes:
        return "좁은 폭 못 잼"
    titles = {slug: title for slug, title, _ in SIDEBAR_GROUP_BOXES}
    width = int(narrow.get("width") or 0)
    wrapped = [titles.get(str(box.get("slug")), "그 밖") for box in boxes if box.get("lines") != 1]
    hard = [
        titles.get(str(box.get("slug")), "그 밖")
        for box in boxes
        if box.get("cut") or (box.get("clipped") and not box.get("ellipsis"))
    ]
    links_cut = int(narrow.get("links_cut") or 0)
    problems: list[str] = []
    if wrapped:
        problems.append(f"줄바꿈: {', '.join(wrapped)}")
    if hard:
        problems.append(f"말줄임 없이 잘림: {', '.join(hard)}")
    if links_cut:
        problems.append(f"링크 말줄임 없이 잘림 {links_cut}")
    if problems:
        return f"좁은 폭 {width}px " + " · ".join(problems)
    clipped = sum(1 for box in boxes if box.get("clipped"))
    return f"좁은 폭 {width}px 한 줄" + (f"(말줄임 {clipped})" if clipped else "")


def check_sidebar_groups(screen: Screen) -> str:
    """사이드바 계산 그룹 셋 — Static Capa · 실행 관리 · Dynamic Capa 가 그 차례로
    서고 상자마다 하위 화면 수가 정한 대로인가, 상자 제목이 줄바꿈·말줄임 없이 한 줄로 보이는가
    (「Dynamic Capa」 가 가장 길다). 어느 화면에서나 같은 사이드바라 HOME 에서 본다.
    상자를 펴지 않는다. 기본 폭에서 잰 뒤 사이드바를 가장 좁게 끈 폭(`SIDEBAR_NARROW_WIDTH_PX`)에서
    한 번 더 잰다 — 그 폭에서는 말줄임이 정한 모양이고 줄바꿈·말줄임 없이 잘림이 결함이다(페이지
    링크도 본다 — 접힌 그룹 안 것도). 잰 뒤 폭은 되돌린다."""
    screen.open_home()
    slugs = [slug for slug, _, _ in SIDEBAR_GROUP_BOXES]
    found = screen.wait_for(
        lambda: screen.js(_SIDEBAR_GROUPS_JS, slugs),
        timeout=30,
        accept=lambda value: bool(value) and all(box["title"] for box in value),
    )
    narrow = screen.js(
        _SIDEBAR_GROUPS_NARROW_JS, {"slugs": slugs, "width": SIDEBAR_NARROW_WIDTH_PX}
    )
    return f"{summarize_sidebar_groups(found)} · {summarize_sidebar_narrow(narrow)}"


# 본문 전환(`st.segmented_control`) 하나의 고른 선택지 글. 전환이 아직 없으면 null.
_SEGMENT_JS = """(key) => {
  const box = document.querySelector(`[data-testid="stMain"] .st-key-${key}`);
  if (!box) return null;
  const chosen = box.querySelector('[role="radio"][aria-checked="true"]');
  return chosen ? chosen.innerText.trim() : "";
}"""
# 비교 시트 — 라벨 그림의 주석(글·들임·글자 크기·세로 자리 — 판정에만 쓴다), 월 그림의 달 수, 표적
# 막대(trace 0, `customdata` = 달·행 id·풍선)마다 칸 가운데(`x = 열 + 0.5`, 같은 `y`)에 선 글자와
# 굵은가(고른 칸만 `<b>` 로 굵다), 칸 누름 세대(`layout.meta.generation`). 풍선(`customdata[2]`)은
# 옮기지 않는다.
_GAP_SHEET_JS = """(keys) => {
  const plot = document.querySelector(`.st-key-${keys.chart} .js-plotly-plot`);
  const labels = document.querySelector(`.st-key-${keys.labels} .js-plotly-plot`);
  if (!plot || !plot.data || !plot.data.length || !labels || !labels.layout) return null;
  const strip = (text) => String(text ?? "").replace(/<[^>]+>/g, "").trim();
  const spot = (x, y) => `${Math.round(x * 1000)}|${Math.round(y * 1000)}`;
  const written = new Map();
  plot.data.slice(1).filter((trace) => trace.mode === "text").forEach((trace) => {
    [...trace.x].forEach((x, i) => {
      written.set(spot(x - 0.5, trace.y[i]), String(trace.text[i] ?? ""));
    });
  });
  const target = plot.data[0];
  const data = [...(target.customdata || [])];
  return {
    notes: (labels.layout.annotations || []).map((note) => ({
      text: note.text, shift: note.xshift || 0, size: (note.font || {}).size || 0, y: note.y,
    })),
    months: new Set(data.map((point) => point[0])).size,
    cells: data.map((point, i) => {
      const text = written.get(spot(target.base[i], target.y[i]));
      return {
        month: point[0],
        row: point[1],
        text: text === undefined ? null : strip(text),
        bold: text !== undefined && /^\\s*<b>/i.test(text),
      };
    }),
    generation: plot.layout.meta ? plot.layout.meta.generation : null,
  };
}"""
# 누를 칸의 화면 자리(px). 그림이 화면 밖이면 가운데로 굴리고, 칸이 월 칸 스크롤 상자 밖이면 상자를
# 가로로 굴린 뒤 다시 잰다. 그림 여백이 0 이라 축 범위(달 수 × 높이)가 곧 그림 상자다.
_GAP_SHEET_POINT_JS = """({keys, month, row}) => {
  const plot = document.querySelector(`.st-key-${keys.chart} .js-plotly-plot`);
  if (!plot || !plot.data || !plot.data.length) return null;
  const target = plot.data[0];
  const data = [...(target.customdata || [])];
  const i = data.findIndex((point) => point[0] === month && point[1] === row);
  if (i < 0) return null;
  const count = new Set(data.map((point) => point[0])).size;
  const height = plot.layout.height;
  const place = () => {
    const box = plot.getBoundingClientRect();
    return {
      x: box.left + ((target.base[i] + 0.5) * box.width) / count,
      y: box.top + ((height - target.y[i]) * box.height) / height,
    };
  };
  let point = place();
  if (point.y < 0 || point.y > innerHeight) {
    plot.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" });
    point = place();
  }
  const scroll = document.querySelector(`.st-key-${keys.scroll}`);
  if (scroll) {
    const view = scroll.getBoundingClientRect();
    if (point.x < view.left + 10 || point.x > view.right - 10) {
      const left = scroll.scrollLeft + point.x - (view.left + view.width / 2);
      scroll.scrollTo({ left, behavior: "instant" });
      point = place();
    }
  }
  return { x: Math.round(point.x), y: Math.round(point.y) };
}"""
# 근거 카드 — 닫힘 안내 글이 있는가, 카드 제목(h5)이 누른 칸의 고정 앞머리(`heading`)로 시작하는가
# (제목 글은 돌려주지 않는다 — 뒤에 공정 이름이 든다), 카드 안 표(Glide)의 데이터 줄 수
# (`aria-rowcount` 는 머리 줄을 넣어 센다), 본문의 예외 상자 수.
_GAP_EVIDENCE_JS = """({keys, closed, heading}) => {
  const card = document.querySelector(`.st-key-${keys.evidence}`);
  const grid = card && card.querySelector('[data-testid="stDataFrame"] [aria-rowcount]');
  const title = card && card.querySelector("h5");
  const words = (text) => String(text ?? "").replace(/\\s+/g, " ").trim();
  return {
    card: !!card,
    closed: !!card && card.innerText.includes(closed),
    matches: !!title && !!heading && words(title.textContent).startsWith(words(heading)),
    rows: grid ? Number(grid.getAttribute("aria-rowcount")) - 1 : null,
    exceptions: document.querySelectorAll('[data-testid="stMain"] [data-testid="stException"]')
      .length,
  };
}"""
_HTML_TAG = re.compile(r"<[^>]+>")


def gap_sheet_row_labels(notes: Sequence[Mapping[str, Any]]) -> tuple[tuple[str, str], ...]:
    """라벨 그림 주석을 위에서 아래로 (구획 제목, 행 라벨)로 읽는다.

    행 라벨은 가장 덜 들인 글(머리·구획 제목)보다 들였고, 구획 제목의 세부 글은 글자가 작아 뺀다.
    머리 글(공정 이름이 든다)은 바로 뒤의 첫 구획 제목이 덮어 밖으로 나가지 않는다 — 읽은 글은
    판정에만 쓴다.
    """
    if not notes:
        return ()
    size = max(float(note.get("size") or 0) for note in notes)
    least = min(float(note.get("shift") or 0) for note in notes)
    rows: list[tuple[str, str]] = []
    title = ""
    for note in sorted(notes, key=lambda note: -float(note.get("y") or 0)):
        if float(note.get("size") or 0) < size:
            continue
        text = html.unescape(_HTML_TAG.sub("", str(note.get("text") or ""))).strip()
        if float(note.get("shift") or 0) > least:
            rows.append((title, text))
        else:
            title = text
    return tuple(rows)


def _cell_number(text: object) -> float | None:
    """칸 글자를 수로(「—」·빈 글자는 None). 부호 문자(U+2212)·`+`·⚠·쉼표를 정리한다."""
    cleaned = str(text or "").replace("⚠", "").replace(",", "").replace("−", "-").strip()
    try:
        return float(cleaned.replace("+", ""))
    except ValueError:
        return None


def gap_sheet_click_target(
    cells: Sequence[Mapping[str, Any]],
) -> tuple[tuple[int, str] | None, int]:
    """누를 설비 일정 기준 칸 (달, 행 id)과 대여(비가동)가 0 아닌 달 수.

    대여(비가동)가 0 아닌 첫 달의 그 칸을 누른다 — 근거 표가 비가동이 깎은 호기 줄이다. 그런 달이
    없으면 값이 있는 가용 칸(0 아닌 칸 먼저)의 첫 달이다. 칸 글자는 판정에만 쓴다.
    """
    (lent_row, _), (available_row, _) = GAP_SHEET_SCHEDULE_CELLS
    lent = sorted(
        int(cell["month"])
        for cell in cells
        if cell.get("row") == lent_row and _cell_number(cell.get("text")) not in (None, 0.0)
    )
    if lent:
        return (lent[0], lent_row), len(lent)
    available = sorted(
        (_cell_number(cell.get("text")) == 0.0, int(cell["month"]))
        for cell in cells
        if cell.get("row") == available_row and _cell_number(cell.get("text")) is not None
    )
    return ((available[0][1], available_row) if available else None), 0


def gap_evidence_heading(cell: tuple[int, str]) -> str:
    """누른 설비 일정 기준 칸의 근거 카드 제목(h5) 앞머리 — `YY.MM · 설비 일정 기준 <행 라벨> · `.

    카드 제목은 `<달> · <구획> <행 라벨> · <공정 표시명>` 이다. 뒤의 공정 이름은 보지 않고 고정
    어휘의 앞머리로 시작하는가만 본다. 달 표기는 앱의 `month_label` 을 옮겼다(테스트가 같은지 본다).
    """
    month, row = cell
    label = dict(GAP_SHEET_SCHEDULE_CELLS).get(row, row)
    return f"{month // 100 % 100:02d}.{month % 100:02d} · {_GAP_SCHEDULE_TITLE} {label} · "


def gap_sheet_bold_cells(cells: Sequence[Mapping[str, Any]]) -> list[tuple[int, str]]:
    """월 그림에서 글자가 굵은 칸(고른 칸) (달, 행 id) — 그림 차례대로."""
    return [(int(cell["month"]), str(cell["row"])) for cell in cells if cell.get("bold")]


def summarize_gap_sheet(
    rows: Sequence[tuple[str, str]] | None,
    months: int,
    lent_months: int,
    clicked: str | None,
    opened: bool,
    aimed: bool,
    lines: int | None,
    closed_again: bool | None,
    exceptions: int,
) -> str:
    """비교 시트 한 줄 — 9행이 정한 차례인가, 달 수, 대여(비가동)가 0 아닌 달 수, 설비 일정 기준
    칸을 누르면 그 칸의 근거 카드가 열리고(`aimed` — 카드 제목 앞머리와 굵은 칸이 누른 칸인가.
    아니면 「다른 칸 열림」) 표 줄이 몇인가(합계 줄 뺌), 같은 칸을 다시 누르면 닫히는가, 예외 상자
    수. 행 라벨은 고정 어휘(`GAP_SHEET_ROWS`)에서 적고 화면 글자는 같은지만 본다."""
    if rows is None:
        return f"비교 시트 없음 · 예외 {exceptions}"
    order = "같음" if tuple(rows) == GAP_SHEET_ROWS else "다름"
    head = (
        f"행 {len(rows)} — 정한 차례와 {order} · 달 {months}칸 · "
        f"대여(비가동) 0 아닌 달 {lent_months}"
    )
    if clicked is None:
        return f"{head} · 값 있는 {_GAP_SCHEDULE_TITLE} 칸 없음(안 누름) · 예외 {exceptions}"
    label = dict(GAP_SHEET_SCHEDULE_CELLS).get(clicked, "그 밖")
    body = f"「{_GAP_SCHEDULE_TITLE} {label}」 칸 누름 → "
    if not opened:
        body += "근거 카드 안 열림"
    else:
        if aimed:
            table = f"근거 표 {lines}줄(합계 뺌)" if lines else "근거 표 없음"
            body += f"근거 카드 열림 · {table}"
        else:
            body += "다른 칸 열림"
        if closed_again is not None:
            body += f" · 같은 칸 다시 누름 → {'닫힘' if closed_again else '안 닫힘'}"
    return f"{head} · {body} · 예외 {exceptions}"


def _choose_segment(screen: Screen, key: str, option: str) -> str | None:
    """본문 전환 `key` 에서 `option` 을 고르고, 고르기 전의 선택지 글을 돌려준다(전환이 서지 않으면
    None — 고르지 않는다). 이미 그것이면 누르지 않는다. 고른 것은 세션 값이라 DB 에 쓰지 않는다."""
    current = screen.poll(
        lambda: screen.js(_SEGMENT_JS, key), timeout=60, accept=lambda value: value is not None
    )
    if current is None:
        return None
    if current != option:
        options = screen.page.locator(f'[data-testid="stMain"] .st-key-{key} [role="radio"]')
        options.filter(has_text=option).first.click()
        screen.wait_idle()
    return str(current)


def _gap_sheet(screen: Screen, *, timeout: float = 30.0) -> Any:
    return screen.poll(
        lambda: screen.js(_GAP_SHEET_JS, GAP_SHEET_KEYS),
        timeout=timeout,
        accept=lambda value: bool(value) and bool(value["cells"]),
    )


def _gap_evidence(screen: Screen, heading: str = "") -> Any:
    return screen.js(
        _GAP_EVIDENCE_JS,
        {"keys": GAP_SHEET_KEYS, "closed": GAP_SHEET_CLOSED_TEXT, "heading": heading},
    )


def _click_gap_cell(screen: Screen, cell: tuple[int, str]) -> bool:
    """시트 칸 하나를 누르고 칸 누름 세대가 오를 때까지 기다린다. 올랐으면 True.

    세대는 누를 때마다 오르는 그림 `layout.meta.generation` 이다 — 같은 칸을 다시 눌러 닫는 것도
    새 그림이라 브라우저가 지난 선택을 들고 오지 않는다(`availability_gap_panel`).
    """
    before = (_gap_sheet(screen) or {}).get("generation")
    arg = {"keys": GAP_SHEET_KEYS, "month": cell[0], "row": cell[1]}
    if screen.js(_GAP_SHEET_POINT_JS, arg) is None:
        return False
    # 굴린 뒤 자리가 멈출 때까지 다시 잰다.
    point = screen.wait_stable(lambda: screen.js(_GAP_SHEET_POINT_JS, arg), timeout=10)
    screen.page.mouse.move(float(point["x"]), float(point["y"]))
    time.sleep(0.3)
    screen.page.mouse.click(float(point["x"]), float(point["y"]))
    moved = screen.poll(
        lambda: (screen.js(_GAP_SHEET_JS, GAP_SHEET_KEYS) or {}).get("generation"),
        timeout=30,
        accept=lambda generation: generation is not None and generation != before,
    )
    screen.wait_idle()
    return moved is not None and moved != before


def check_gap_sheet(screen: Screen) -> str:
    """가용설비 현황 → `Summary` › `Static 대비 일정` → `분류별 내역` 9행 비교 시트 — 행 라벨이 정한
    9행 차례와 같은가와 달 수, 설비 일정 기준 칸(대여(비가동)가 0 아닌 칸 먼저, 없으면 가용 칸)
    하나를 누르면 아래 근거 카드가 그 칸의 것으로 열리고(카드 제목 앞머리·굵은 칸) 표 줄이 몇인가,
    같은 칸을 다시 누르면 닫히는가, 예외 상자 수. 기본 범위(전체 합계)로 본다 — 공정을 고르지
    않는다. 칸 누름·전환은 세션 값이라 DB 에 쓰지 않고, 바꾼 전환은 끝에(읽다 깨져도) 되돌린다.
    공정·호기 이름과 칸 값·카드 제목은 판정에만 쓰고 찍지 않는다."""
    screen.open_page(EQUIPMENT_PAGE)
    open_equipment_tab(screen, GAP_TAB)
    changed: list[tuple[str, str]] = []
    try:
        for key, option in (
            (GAP_RESULT_VIEW_KEY, GAP_SHEET_VIEW),
            (GAP_DETAIL_MODE_KEY, GAP_SHEET_MODE),
        ):
            before = _choose_segment(screen, key, option)
            if before is not None and before != option:
                changed.append((key, before))
        sheet = _gap_sheet(screen, timeout=120)
        exceptions = int(_gap_evidence(screen)["exceptions"])
        if not sheet or not sheet["cells"]:
            return summarize_gap_sheet(None, 0, 0, None, False, False, None, None, exceptions)
        rows = gap_sheet_row_labels(sheet["notes"])
        cell, lent_months = gap_sheet_click_target(sheet["cells"])
        opened = False
        aimed = False
        lines: int | None = None
        closed_again: bool | None = None
        if cell is not None and _click_gap_cell(screen, cell):
            heading = gap_evidence_heading(cell)
            evidence = screen.poll(
                lambda: _gap_evidence(screen, heading),
                timeout=30,
                accept=lambda value: not value["closed"],
            )
            opened = bool(evidence["card"]) and not evidence["closed"]
            if opened:
                evidence = screen.poll(
                    lambda: _gap_evidence(screen, heading),
                    timeout=10,
                    accept=lambda value: value["rows"] is not None,
                )
                drawn = _gap_sheet(screen) or {}
                aimed = bool(evidence["matches"]) and gap_sheet_bold_cells(
                    drawn.get("cells") or []
                ) == [cell]
                lines = None if evidence["rows"] is None else max(int(evidence["rows"]) - 1, 0)
                exceptions = max(exceptions, int(evidence["exceptions"]))
                clicked_again = _click_gap_cell(screen, cell)
                after = screen.poll(
                    lambda: _gap_evidence(screen), timeout=30, accept=lambda value: value["closed"]
                )
                closed_again = clicked_again and bool(after["closed"])
                exceptions = max(exceptions, int(after["exceptions"]))
        return summarize_gap_sheet(
            rows,
            int(sheet["months"]),
            lent_months,
            None if cell is None else cell[1],
            opened,
            aimed,
            lines,
            closed_again,
            exceptions,
        )
    finally:
        for key, option in reversed(changed):
            _choose_segment(screen, key, option)


# 배포마다 바뀌는 확인 목록 — 항목 하나에 한 줄. 차례대로 돈다.
# 설비 시나리오 줄 — 이름 줄 캡션(이름·배지)과 값 칸 글자. 값 칸 단추에는 머티리얼 아이콘이 있어
# 단추 전체 `innerText` 에 아이콘 이름(「account_tree」)과 줄바꿈이 섞이므로 라벨 칸만 읽는다.
_EQUIPMENT_ROW_JS = """(keys) => {
  const side = document.querySelector('[data-testid="stSidebar"]');
  if (!side) return null;
  const row = side.querySelector(`.st-key-${keys.row}`);
  const field = side.querySelector(`.st-key-${keys.field} button`);
  const captions = row
    ? [...row.querySelectorAll('[data-testid="stCaptionContainer"]')].map((c) => c.innerText.trim())
    : [];
  const label = field ? field.querySelector('[data-testid="stMarkdownContainer"]') : null;
  return {
    name: captions.length ? captions[0] : null,
    badge: captions.length > 1 ? captions[1] : null,
    value: field ? (label || field).innerText.trim() : null,
    disabled: field ? field.disabled : null,
  };
}"""
# 값 칸 글자 꼴 — 「<시나리오 이름> · r<번호>」(이름은 값이라 찍지 않고 꼴만 본다).
_EQUIPMENT_VALUE_SHAPE: Final = re.compile(r"^.+ · r\d+$")


def equipment_field_text(value: object) -> str:
    """값 칸 글자 — 단추 전체 글을 읽었으면 아이콘 이름 줄을 떼고 마지막 줄만 둔다."""
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def summarize_equipment_scenario_line(
    row: Mapping[str, Any] | None,
    title: str | None,
    facts: Mapping[str, Any] | None,
    closed: bool,
) -> str:
    """가용설비 현황 사이드바 설비 시나리오 줄 한 줄 — 줄·값 칸 꼴·배지·팝업 구획·리비전 수·Esc.

    시나리오 이름·리비전 번호는 값이라 찍지 않는다 — 꼴이 맞는지(같음·다름)와 배지 종류만 적는다.
    """
    if not row or row.get("name") != EQUIPMENT_SCENARIO_ROW_NAME:
        return f"「{EQUIPMENT_SCENARIO_ROW_NAME}」 줄 없음"
    value = equipment_field_text(row.get("value"))
    shape = "같음" if _EQUIPMENT_VALUE_SHAPE.match(value) else "다름"
    badge_text = str(row.get("badge") or "")
    badge = next((kind for kind in EQUIPMENT_STATUS_BADGES if badge_text.startswith(kind)), None)
    badge_words = f"배지 「{badge}…」" if badge in ("공식 v", "최신 r") else f"배지 「{badge}」"
    head = f"「{EQUIPMENT_SCENARIO_ROW_NAME}」 줄 있음 · 값 칸 「이름 · rN」 꼴 {shape} · " + (
        badge_words if badge is not None else "배지 없음"
    )
    if title is None:
        return f"{head} · 팝업 안 열림"
    modes = tuple(facts["modes"]) if facts else ()
    control = "있음" if modes == EQUIPMENT_SCENARIO_DIALOG_MODES else "없음"
    revisions = facts["revisions"] if facts else None
    listed = "리비전 목록 없음" if revisions is None else f"리비전 {int(revisions)}개"
    names = "·".join(f"「{mode}」" for mode in EQUIPMENT_SCENARIO_DIALOG_MODES)
    return (
        f"{head} · {_title_text(title, EQUIPMENT_SCENARIO_DIALOG_TITLE)} · 구획 {names} "
        f"{control} · {listed} · {_closed_text(closed)}"
    )


def check_equipment_scenario_line(screen: Screen) -> str:
    """`가용설비 현황` 사이드바의 설비 시나리오 줄과 팝업 — 줄 이름·값 칸 꼴·배지, 팝업 제목·구획
    「불러오기」·「저장」·리비전 수. 불러오기·저장은 누르지 않고 `Esc` 로 닫는다(DB 쓰기 없음)."""
    screen.open_page(EQUIPMENT_PAGE)
    keys = {
        "row": f"{CONDITION_NAME_ROW_PREFIX}{EQUIPMENT_SCENARIO_ROW_SLUG}",
        "field": EQUIPMENT_SCENARIO_FIELD_KEY,
    }
    row = screen.poll(
        lambda: screen.js(_EQUIPMENT_ROW_JS, keys),
        timeout=60,
        accept=lambda value: bool(value) and value["name"] is not None and bool(value["value"]),
    )
    if not row or row.get("name") is None or row.get("disabled"):
        return summarize_equipment_scenario_line(row, None, None, False)
    screen.open_dialog(_sidebar_button(EQUIPMENT_SCENARIO_FIELD_KEY))
    load = EQUIPMENT_SCENARIO_DIALOG_MODES[0]
    try:
        title = screen.dialog_title()
        facts = screen.poll(
            lambda: screen.dialog_read(_SCENARIO_DIALOG_JS, REVISION_RADIO_LABEL),
            timeout=30,
            accept=lambda value: (
                bool(value)
                and bool(value["modes"])
                and (value["selected"] != load or value["revisions"] is not None)
            ),
        )
    finally:
        closed = screen.close_dialog()
    return summarize_equipment_scenario_line(row, title, facts, closed)


# Space 현황 사이드바의 설비 시나리오 줄(설비 시나리오 2단계 S3·S4) — 고를 수 있는 줄(잠근 꼴의
# 「(고정)」 없음)이고 팝업은 「불러오기」 구획 하나다(구획 전환이 서지 않는다 — 배치 저장은 본문
# 상자).
SPACE_SCENARIO_FIXED_TAIL: Final = "(고정)"
SPACE_SCENARIO_LOAD_BUTTON: Final = "불러오기"
_SPACE_SCENARIO_DIALOG_JS = """(box, args) => {
  const group = box.querySelector('[data-testid="stButtonGroup"] [role="radiogroup"]');
  const list = [...box.querySelectorAll('[role="radiogroup"]')]
    .find((g) => g.getAttribute("aria-label") === args.radio);
  const buttons = [...box.querySelectorAll('[data-testid="stButton"] button')]
    .map((button) => button.innerText.trim());
  return {
    modes: group ? [...group.querySelectorAll('[role="radio"]')].map((b) => b.innerText.trim()) :
    [], load: buttons.some((text) => text.endsWith(args.load)), revisions: list ?
    list.querySelectorAll('input[type="radio"]').length : null,
  };
}"""


def summarize_space_scenario_row(
    row: Mapping[str, Any] | None,
    title: str | None,
    facts: Mapping[str, Any] | None,
    closed: bool,
) -> str:
    """Space 현황 사이드바 설비 시나리오 줄 한 줄 — 줄·고를 수 있음·「(고정)」 없음·배지 종류·팝업
    「불러오기」 만·리비전 수·Esc. 시나리오 이름·번호는 값이라 찍지 않는다."""
    if not row or row.get("name") != EQUIPMENT_SCENARIO_ROW_NAME:
        return f"Space 「{EQUIPMENT_SCENARIO_ROW_NAME}」 줄 없음"
    value = equipment_field_text(row.get("value"))
    pickable = "고를 수 없음(잠김)" if row.get("disabled") else "고를 수 있음"
    fixed = f"「{SPACE_SCENARIO_FIXED_TAIL}」 " + (
        "있음" if SPACE_SCENARIO_FIXED_TAIL in value else "없음"
    )
    badge_text = str(row.get("badge") or "")
    badge = next((kind for kind in EQUIPMENT_STATUS_BADGES if badge_text.startswith(kind)), None)
    badge_words = (
        "배지 없음"
        if badge is None
        else f"배지 「{badge}…」"
        if badge in ("공식 v", "최신 r")
        else f"배지 「{badge}」"
    )
    head = f"Space 「{EQUIPMENT_SCENARIO_ROW_NAME}」 줄 있음 · {pickable} · {fixed} · {badge_words}"
    if title is None:
        return f"{head} · 팝업 안 열림"
    modes = list(facts["modes"]) if facts else []
    load = bool(facts and facts["load"])
    only = (
        "「불러오기」 만" if load and not modes else "구획 다름" if modes else "「불러오기」 없음"
    )
    revisions = facts["revisions"] if facts else None
    listed = "리비전 목록 없음" if revisions is None else f"리비전 {int(revisions)}개"
    return (
        f"{head} · {_title_text(title, EQUIPMENT_SCENARIO_DIALOG_TITLE)} · {only} · {listed} · "
        f"{_closed_text(closed)}"
    )


def check_space_scenario_row(screen: Screen) -> str:
    """`Space 현황` 사이드바의 설비 시나리오 줄과 팝업 — 고를 수 있는 줄(「(고정)」 없음)·배지 종류,
    팝업 제목·「불러오기」 구획 하나·리비전 수. 불러오기는 누르지 않고 `Esc` 로 닫는다(DB 쓰기
    없음)."""
    screen.open_page(SPACE_PAGE)
    keys = {
        "row": f"{CONDITION_NAME_ROW_PREFIX}{EQUIPMENT_SCENARIO_ROW_SLUG}",
        "field": EQUIPMENT_SCENARIO_FIELD_KEY,
    }
    row = screen.poll(
        lambda: screen.js(_EQUIPMENT_ROW_JS, keys),
        timeout=60,
        accept=lambda value: bool(value) and value["name"] is not None and bool(value["value"]),
    )
    if not row or row.get("name") is None or row.get("disabled"):
        return summarize_space_scenario_row(row, None, None, False)
    screen.open_dialog(_sidebar_button(EQUIPMENT_SCENARIO_FIELD_KEY))
    args = {"radio": REVISION_RADIO_LABEL, "load": SPACE_SCENARIO_LOAD_BUTTON}
    try:
        title = screen.dialog_title()
        facts = screen.poll(
            lambda: screen.dialog_read(_SPACE_SCENARIO_DIALOG_JS, args),
            timeout=30,
            accept=lambda value: bool(value) and value["revisions"] is not None,
        )
    finally:
        closed = screen.close_dialog()
    return summarize_space_scenario_row(row, title, facts, closed)


# Space 층 사용(2026-10-24 S1~S6) — 층 목록 표의 칸·스위치 이름과 편집표 칸. 머리 글은 완전 일치로
# 찾으므로 앱의 칸 이름을 바꾸면 여기도 바꾼다(`components/space_floor_list.py`).
SPACE_FLOOR_STATE_SWITCH: Final = "사용 편집"
SPACE_FLOOR_USE_COLUMN: Final = "사용"
SPACE_FLOOR_EDIT_COLUMNS: Final = ("사용", "사유", "호기")
_INACTIVE_COUNT = re.compile(r"비활성 층 (\d+)개")


def summarize_space_floor_state(
    rows: int | None,
    in_use: int,
    inactive: int | None,
    grey: int,
    edit_columns: bool | None,
) -> str:
    """층 사용 칸 확인 결과 — 개수·있음/없음만. 층 이름은 찍지 않는다.

    `rows` None 은 사용 칸 없음, `inactive` 는 「비활성 층 n개」 펼침의 n(없으면 0), `edit_columns`
    None 은 스위치 없음이다. 회색 블록 수와 비활성 n 이 다르면 그 차이를 적는다."""
    if rows is None:
        return "사용 칸 없음"
    folded = inactive or 0
    parts = [
        "사용 칸 있음",
        f"목록 {rows}줄(사용 {in_use})",
        f"비활성 층 {folded}개",
        f"회색 블록 {grey}개" if grey == folded else f"회색 블록 {grey} ≠ 비활성 {folded}",
    ]
    if edit_columns is None:
        parts.append("스위치 없음")
    elif edit_columns:
        parts.append(f"편집 칸 {'·'.join(SPACE_FLOOR_EDIT_COLUMNS)} 있음")
    else:
        parts.append("편집 칸 없음")
    return " · ".join(parts)


def check_space_floor_state(screen: Screen) -> str:
    """Space 층 사용 칸 — FAB 전체 층 목록 표의 `사용` 칸 줄 수·참 개수, 접힌 「비활성 층 n개」, FAB
    도면의 회색 블록 수, `사용 편집` 을 켠 편집표 칸(`사용`·`사유`·`호기`). **저장하지 않고** 끈다
    (세션만 — DB 쓰기 없음). 층 이름은 찍지 않는다."""
    screen.step("페이지 열기")
    screen.open_space_overview()
    screen.step("층 목록")
    try:
        grid, use_column = screen.grid_with_column(SPACE_FLOOR_USE_COLUMN, timeout=20)
    except TimeoutError:
        return summarize_space_floor_state(None, 0, None, 0, None)
    values = [row[0] for row in screen.grid_rows(grid, [use_column])]
    in_use = sum(1 for value in values if str(value).strip().lower() in ("true", "✓", "✔"))
    folded = screen.page.locator('[data-testid="stExpander"]').filter(has_text="비활성 층")
    inactive = 0
    if folded.count():
        found = _INACTIVE_COUNT.search(folded.first.inner_text())
        inactive = int(found.group(1)) if found else 0
    grey = screen.poll(
        lambda: screen.page.locator(".mark-block.is-inactive").count(),
        timeout=10,
        accept=lambda count: count == inactive,
    )
    screen.step("사용 편집")
    if not screen.switch(SPACE_FLOOR_STATE_SWITCH, True):
        return summarize_space_floor_state(len(values), in_use, inactive, int(grey), None)
    try:
        try:
            editor, _ = screen.grid_with_column("호기", timeout=20)
        except TimeoutError:
            edit_columns = False
        else:
            edit_columns = all(
                screen.column_index(editor, name) is not None for name in SPACE_FLOOR_EDIT_COLUMNS
            )
    finally:
        screen.switch(SPACE_FLOOR_STATE_SWITCH, False)
    return summarize_space_floor_state(len(values), in_use, inactive, int(grey), edit_columns)


# 본문 탭 이름(`role="tab"`) 전부 — 옛 탭 이름이 어디에든 남았는지 셀 때만. 아이콘 글자(`table_rows`
# 등)는 앞에 붙어 온다 — 끝 글자로 가른다.
_MAIN_TAB_NAMES_JS = """() => [...document.querySelectorAll('[data-testid="stMain"] [role="tab"]')]
  .map((tab) => tab.innerText.replace(/\\s+/g, " ").trim())"""
# key 를 준 탭 묶음 하나(`st.tabs(key=…)` — `st-key-<key>` 칸)의 제 탭 이름만. 그 칸 안 첫 탭
# 목록이 제 것이고(안쪽 탭 묶음의 탭 목록은 패널 안이라 뒤에 온다), 숨은 패널 안 탭도 innerText
# 가 남으므로 본문 전체에서 세면 다른 탭 묶음의 같은 이름(② 안 「Main」·「Static 대비 일정」 이나
# 다른 자리의 「설비 마스터」 탭)이 제 탭으로 잘못 셈에 든다.
_KEYED_TAB_NAMES_JS = """(key) => {
  const box = document.querySelector(`[data-testid="stMain"] .st-key-${key}`);
  const list = box ? box.querySelector('[role="tablist"]') : null;
  return list ? [...list.querySelectorAll('[role="tab"]')]
    .map((tab) => tab.innerText.replace(/\\s+/g, " ").trim()) : [];
}"""
# 보이는 팝업 안의 지표 카드 라벨(`st.metric`).
_DIALOG_METRIC_LABELS_JS = """(box) => [...box.querySelectorAll('[data-testid="stMetricLabel"]')]
  .map((label) => label.innerText.trim())"""


@dataclass(frozen=True)
class EquipmentTabNames:
    """가용설비 현황에서 읽은 탭 이름 — 바깥 탭 묶음, Summary 안쪽 탭 묶음, 본문 전체."""

    outer: Sequence[str]
    summary: Sequence[str]
    anywhere: Sequence[str]


def summarize_equipment_moves(
    tabs: EquipmentTabNames,
    settings: tuple[str | None, bool, bool] | None,
    calculator: tuple[str | None, int, bool] | None,
    section: tuple[bool, bool] | None,
) -> str:
    """개편 확인 결과 — 탭 이름은 정한 어휘(`EQUIPMENT_*`)만 적고, 팝업 제목·지표 라벨은 판정에만
    쓴다. 바깥 둘은 바깥 탭 묶음에서만, 안쪽 둘은 Summary 안쪽 탭 묶음에서만 센다(본문 전체에서
    세면 다른 탭 묶음의 같은 이름이 바깥 탭 대신 셈에 든다). 옛 탭 이름은 본문 어디에서든
    센다."""

    def has(names: Sequence[str], label: str) -> bool:
        return any(name.strip() == label or name.strip().endswith(f" {label}") for name in names)

    outer = [
        label for label in (EQUIPMENT_MASTER_TAB, EQUIPMENT_SUMMARY_TAB) if has(tabs.outer, label)
    ]
    inner = [label for label in EQUIPMENT_SUMMARY_TABS if has(tabs.summary, label)]
    old = [label for label in EQUIPMENT_OLD_TABS if has(tabs.anywhere, label)]
    parts = [
        f"탭 {len(outer)}/2 · Summary 안쪽 {len(inner)}/2 · 옛 탭 {len(old)}곳",
    ]
    if settings is None:
        parts.append("「설정」 단추 없음")
    else:
        title, editor, closed = settings
        parts.append(
            f"설정 — {_title_text(title, EQUIPMENT_SETTINGS_TITLE)} · Cut-off 표 "
            f"{'있음' if editor else '없음'} · {_closed_text(closed)}"
        )
    if calculator is None:
        parts.append("「Qual 마감 계산기」 단추 없음")
    else:
        title, kpis, closed = calculator
        parts.append(
            f"필요 단축 일정 — {_title_text(title, QUAL_CALCULATOR_TITLE)} · 지표 "
            f"{kpis}/{len(QUAL_CALCULATOR_KPIS)} · {_closed_text(closed)}"
        )
    if section is None:
        parts.append("「관리할 시나리오」 전환 없음")
    else:
        table, restored = section
        parts.append(
            f"시나리오 관리 — 설비 시나리오 구획 표 {'있음' if table else '없음'} · 전환 "
            f"{'되돌림' if restored else '못 되돌림'}"
        )
    return " · ".join(parts)


def _main_button(widget_key: str) -> str:
    """본문 위젯 key 의 **보이는** 단추 선택자(Streamlit 은 key 를 `st-key-<key>` 클래스로 단다).

    `help=` 를 준 단추는 숨은 사본이 같은 key 칸에 함께 있어(1.63 — 좁은 창에서는 숨은 쪽이 먼저
    잡힌다) Playwright 의 `:visible` 로 보이는 것만 고른다.
    """
    return f'[data-testid="stMain"] .st-key-{widget_key} button:visible'


def check_equipment_moves(screen: Screen) -> str:
    """가용설비 현황 두 탭 개편의 새 자리 — 바깥 탭 둘·Summary 안쪽 둘·옛 탭 이름 0곳, 머리 「설정」
    팝업의 Cut-off 표, 필요 단축 일정 머리 「Qual 마감 계산기」 팝업의 지표 넷, 시나리오 관리
    「관리할 시나리오」 의 「설비 시나리오」 구획 표. 팝업은 `Esc` 로 닫고(저장·채우기·넣기는 누르지
    않는다), 전환은 처음 값으로 되돌린다(세션 값 — DB 에 쓰지 않는다)."""
    screen.open_page(EQUIPMENT_PAGE)
    open_equipment_tab(screen, EQUIPMENT_SUMMARY_TABS[0])
    outer = screen.poll(
        lambda: screen.js(_KEYED_TAB_NAMES_JS, EQUIPMENT_TAB_KEY),
        timeout=30,
        accept=lambda value: bool(value),
    )
    tabs = EquipmentTabNames(
        outer=outer or [],
        summary=screen.js(_KEYED_TAB_NAMES_JS, EQUIPMENT_SUMMARY_TAB_KEY) or [],
        anywhere=screen.js(_MAIN_TAB_NAMES_JS) or [],
    )
    settings: tuple[str | None, bool, bool] | None = None
    if screen.page.locator(_main_button(EQUIPMENT_SETTINGS_BUTTON_KEY)).count():
        screen.open_dialog(_main_button(EQUIPMENT_SETTINGS_BUTTON_KEY))
        try:
            title = screen.dialog_title()
            editor = bool(
                screen.poll(
                    lambda: screen.dialog_read(
                        "(box, header) => [...box.querySelectorAll('[role=\"columnheader\"]')]"
                        ".some((cell) => cell.textContent.trim() === header)",
                        CUTOFF_EDITOR_ANCHOR,
                    ),
                    timeout=30,
                )
            )
        finally:
            closed = screen.close_dialog()
        settings = (title, editor, closed)
    screen.open_page(SHORTENING_PAGE)
    calculator: tuple[str | None, int, bool] | None = None
    if screen.page.locator(_main_button(QUAL_CALCULATOR_BUTTON_KEY)).count():
        screen.open_dialog(_main_button(QUAL_CALCULATOR_BUTTON_KEY))
        try:
            title = screen.dialog_title()
            labels = screen.poll(
                lambda: screen.dialog_read(_DIALOG_METRIC_LABELS_JS),
                timeout=30,
                accept=lambda value: bool(value) and len(value) >= len(QUAL_CALCULATOR_KPIS),
            )
            kpis = sum(1 for label in QUAL_CALCULATOR_KPIS if label in (labels or []))
        finally:
            closed = screen.close_dialog()
        calculator = (title, kpis, closed)
    screen.open_page(SCENARIO_MANAGEMENT_PAGE)
    section: tuple[bool, bool] | None = None
    before = _choose_segment(screen, SCENARIO_KIND_KEY, SCENARIO_KINDS[1])
    if before is not None:
        try:
            table = bool(
                screen.poll(
                    lambda: screen.js(
                        "(header) => [...document.querySelectorAll("
                        '\'[data-testid="stMain"] [role="columnheader"]\')]'
                        ".some((cell) => cell.textContent.trim() === header)",
                        EQUIPMENT_SCENARIO_TABLE_ANCHOR,
                    ),
                    timeout=60,
                )
            )
        finally:
            _choose_segment(screen, SCENARIO_KIND_KEY, before)
        restored = screen.js(_SEGMENT_JS, SCENARIO_KIND_KEY) == before
        section = (table, restored)
    return summarize_equipment_moves(tabs, settings, calculator, section)


# ------------------------------------------------------------------ Space 필요 단축 보기

# 색 기준 라디오 칸(사이드바 `Space 조건`)과 그 셋째 값·기본 값. 앱은 `navigation` 에 같은 글자를
# 둔다.
SPACE_COLOR_BASIS_KEY: Final = "space_color_basis"
SPACE_SHORTENING_BASIS: Final = "필요 단축"
SPACE_DEFAULT_BASIS: Final = "공정구분"
# Space 조건 카드 이름(`sidebar_status.condition_card(name=)` — 앱 `space_status.SPACE_CARD_NAME`).
SPACE_CARD_NAME: Final = "space"
# FAB 블록 풍선(`blockTip`)에 단축 줄(「단축 3대 · 최대 −18일」)이 실린 블록 수.
_SHORT_BLOCKS_JS = """(svg) => [...svg.querySelectorAll(".sle-mark title")]
  .filter((tip) => /단축 \\d+대/.test(tip.textContent || "")).length"""
# 층 보기의 배지 수, 그 가운데 모듈 묶음(누르는 호기 상자에 `is-module`) 배지 수, 고정 줄이
# 보이는가.
_SHORT_FLOOR_JS = """(svg) => {
  const root = svg.getRootNode();
  const badges = [...root.querySelectorAll(".sle-short-badge")];
  const modules = badges.filter((badge) => {
    const unit = [...root.querySelectorAll(".sle-unit")]
      .find((node) => node.dataset.id === badge.dataset.pick);
    return !!unit && unit.classList.contains("is-module");
  }).length;
  const pinned = root.querySelector(".sle-pinned");
  const fader = root.querySelector(".sle-fader");
  return {
    badges: badges.length,
    modules,
    pinned: !!pinned && getComputedStyle(pinned).display !== "none",
    fader: !!fader && getComputedStyle(fader).display !== "none",
  };
}"""


def _fader_back_text(fader_back: bool | None) -> str:
    """되돌린 뒤 층 도면의 페이더 — `None` 은 층을 열지 못해 보지 않은 것이다(있음으로 적지
    않는다)."""
    if fader_back is None:
        return "되돌린 뒤 페이더 확인 안 함(연 층 없음)"
    return f"되돌린 뒤 페이더 {'있음' if fader_back else '없음'}"


def summarize_space_shortening(
    blocks: int,
    floor: Mapping[str, Any] | None,
    fader_back: bool | None,
    *,
    stopped: str | None = None,
) -> str:
    """필요 단축 보기 한 줄 — 개수·있음/없음만. 층·호기·공정 이름은 찍지 않는다. `fader_back` 은
    색 기준을 되돌린 뒤 층 도면에서 본 페이더(층을 열지 못했으면 `None` — 「확인 안 함」)."""
    if stopped is not None:
        return f"{stopped} · {_fader_back_text(fader_back)}"
    if floor is None:
        head = f"단축 줄 블록 {blocks}개 · 단축 층 없음"
    else:
        head = (
            f"단축 줄 블록 {blocks}개 · 최다 층 배지 {floor.get('badges', 0)}개"
            f"(모듈 묶음 {floor.get('modules', 0)}) · 고정 줄 "
            f"{'있음' if floor.get('pinned') else '없음'}"
            f" · 페이더 {'숨음' if not floor.get('fader') else '보임'}"
        )
    return f"{head} · {_fader_back_text(fader_back)}"


def _choose_color_basis(screen: Screen, value: str) -> None:
    """사이드바 `Space 조건` 카드의 `색 기준` 라디오를 그 값으로. 카드는 기본 접힘이라 접혀 있으면
    먼저 편다."""
    option = screen.page.locator(f".st-key-{SPACE_COLOR_BASIS_KEY}").first.get_by_text(
        value, exact=True
    )
    if not option.first.is_visible():
        card = screen.page.locator(f".st-key-{CONDITION_CARD_PREFIX}{SPACE_CARD_NAME}").first
        card.locator("summary").first.click()
        option.first.wait_for(state="visible", timeout=ACTION_TIMEOUT_MS)
    option.first.click()
    screen.wait_idle()


def _open_most_placed_floor(screen: Screen) -> bool:
    """FAB 층 목록 표의 `배치대수` 가 가장 많은 층을 연다(`space_fader` 와 같은 고르기). 열었으면
    참."""
    grid, placed_column = screen.grid_with_column("배치대수")
    building_column = screen.column_index(grid, "동")
    floor_column = screen.column_index(grid, "층")
    if building_column is None or floor_column is None:
        return False
    rows = screen.grid_rows(grid, [building_column, floor_column, placed_column])
    candidates = [(row[0], row[1], _number(row[2])) for row in rows if row[0] and row[1]]
    candidates = [row for row in candidates if row[2] > 0]
    if not candidates:
        return False
    building, name, _placed = max(candidates, key=lambda row: row[2])
    screen.choose_by_typing("층 바로 가기", f"{building} {name}")
    return screen.selectbox_value("층 바로 가기") == f"{building} {name}"


def check_space_shortening(screen: Screen) -> str:
    """Space 「필요 단축」 보기 — FAB 에서 색 기준을 `필요 단축` 으로 골라 단축 줄이 선 블록 수, 층
    목록 표의 `단축 호기` 가 가장 많은 층을 열어 배지 수·모듈 묶음 배지 수·고정 줄(페이더 숨음),
    그리고 색 기준을 공정구분으로 **되돌린 뒤** 층 도면에 페이더가 있는가(되돌리지 않으면 같은
    세션의 다음 실행에서 `space_fader`·`panel_rows_other_pages` 가 고정 줄·늘어난 사이드바 줄을
    본다). 단축 층을 열지 못한 실행(Cut-off 먼저·못 읽음·단축 층 없음)은 되돌린 뒤 배치가 가장 많은
    층을 열어 본다 — 연 층이 없으면 「확인 안 함」 이다(본 것만 적는다). 쓰지 않는다(색 기준·목표는
    세션 값이다). Cut-off 가 비면 「Cut-off 먼저」 알림이 정상이다."""
    screen.step("페이지 열기")
    screen.open_space_overview()
    blocks, floor, stopped = 0, None, None
    try:
        screen.step("색 기준 필요 단축")
        _choose_color_basis(screen, SPACE_SHORTENING_BASIS)
        text = screen.main_text()
        if "Cut-off 를 먼저" in text:
            stopped = "Cut-off 먼저 알림"
        elif "필요 단축을 칠하지 못했습니다" in text:
            stopped = "못 읽음 알림"
        else:
            screen.step("FAB 블록")
            canvas = screen.page.locator(".sle-canvas").first
            blocks = int(
                screen.poll(
                    lambda: canvas.evaluate(_SHORT_BLOCKS_JS), timeout=15, accept=lambda v: v > 0
                )
                or 0
            )
            screen.step("층 목록")
            grid, short_column = screen.grid_with_column("단축 호기")
            building_column = screen.column_index(grid, "동")
            floor_column = screen.column_index(grid, "층")
            if building_column is not None and floor_column is not None:
                rows = screen.grid_rows(grid, [building_column, floor_column, short_column])
                ranked = [(row[0], row[1], _number(row[2])) for row in rows if row[0] and row[1]]
                ranked = [row for row in ranked if row[2] > 0]
                if ranked:
                    building, name, _count = max(ranked, key=lambda row: row[2])
                    screen.step("층 고르기")
                    screen.choose_by_typing("층 바로 가기", f"{building} {name}")
                    floor_canvas = screen.page.locator(".sle-canvas").first
                    floor = screen.poll(
                        lambda: floor_canvas.evaluate(_SHORT_FLOOR_JS),
                        timeout=20,
                        accept=lambda v: bool(v) and v.get("badges", 0) > 0,
                    )
    finally:
        failed_at = screen.current_step
        screen.step("공정구분으로 되돌림")
        _choose_color_basis(screen, SPACE_DEFAULT_BASIS)
        opened = floor is not None
        if not opened:
            screen.step("되돌린 뒤 층 열기")
            try:
                opened = _open_most_placed_floor(screen)
            except Exception:  # noqa: BLE001 — 열지 못했으면 「확인 안 함」 으로 적는다
                opened = False
        fader_back: bool | None = None
        if opened:
            fader_input = screen.page.locator(".sle-fader-input").first
            try:
                fader_input.wait_for(state="visible", timeout=ACTION_TIMEOUT_MS)
                fader_back = True
            except Exception:  # noqa: BLE001 — 있음/없음만 적는다
                fader_back = False
        screen.current_step = failed_at
    return summarize_space_shortening(blocks, floor, fader_back, stopped=stopped)


# --------------------------------------------------- 7-18 B 대행이 헤드리스로 못 세던 칸
#
# `202610231430` 리뷰 사외 요청 4 의 다섯 칸을 재는 항목들이다. 헤드리스에서 막히는 자리 넷을
# 피한다 — HOME 칸은 그림을 화면 가운데로 굴린 뒤 화면 안의 칸을 누른다(화면 밖 좌표는 눌리지
# 않는다). 근거 카드의 ④ 링크는 공정 하나를 골랐을 때만 선다(기본은 `전체 합계`). 영역 요소는
# 이름표만 눌림을 받는다(안쪽은 비워 둔다). 머리 칸 풍선은 머리 줄 좌표에 마우스를 올려 띄운다
# (Glide 캔버스라 머리 칸 DOM 은 크기 0). 모두 세션 값만 바꾸고 끝에(깨져도) 되돌린다.


# 누른 뒤 콘솔 경고 줄이 파이프로 건너오기를 기다리는 시간(초) — 늘지 않으면 그대로 센다.
CONSOLE_SETTLE_SECONDS: Final = 3.0


def console_lines(screen: Screen, needle: str) -> int | None:
    """확인용 앱 콘솔에서 `needle` 이 든 줄 수. 세지 않는 실행(`screen.console` 없음)이면 None."""
    return None if screen.console is None else screen.console.count(needle)


def settled_console_lines(screen: Screen, needle: str, before: int | None) -> int | None:
    """누른 뒤의 줄 수 — 늘 때까지 `CONSOLE_SETTLE_SECONDS` 만큼 기다린다(앱이 쓴 줄을 읽기 스레드가
    받기까지 틈이 있다). 늘지 않으면 그대로다."""
    if before is None:
        return None
    count: int | None = screen.poll(
        lambda: console_lines(screen, needle),
        timeout=CONSOLE_SETTLE_SECONDS,
        accept=lambda now: now is not None and now > before,
    )
    return count


@contextmanager
def opened_card(screen: Screen, key: str) -> Iterator[bool]:
    """사이드바 조건 카드(`details`)를 편 채로 안을 돌고, 접혀 있었으면 끝에 다시 접는다. 카드가
    없으면 False 를 내고 아무것도 하지 않는다."""
    card = screen.page.locator(f'[data-testid="stSidebar"] .st-key-{key} details').first
    if card.count() == 0:
        yield False
        return
    was_open = card.get_attribute("open") is not None
    if not was_open:
        card.locator("summary").first.click()
        screen.wait_idle()
    try:
        yield True
    finally:
        if not was_open and card.get_attribute("open") is not None:
            card.locator("summary").first.click()
            screen.wait_idle()


def _set_number(screen: Screen, field: Any, value: int) -> None:
    field.fill(str(value))
    field.press("Enter")
    screen.wait_idle()


# ① 끝 「UPEH n% · …」 라벨(그림 글자) — 라벨 칸 그림과 월 그림의 SVG 글자에서 앞머리로 찾는다.
_UPEH_ROWS_JS = """(prefix) => [
  ...document.querySelectorAll('[data-testid="stMain"] .js-plotly-plot text'),
].map((node) => (node.textContent || "").trim()).filter((text) => text.startsWith(prefix))"""
_KPI_COUNT_JS = (
    """(key) => document.querySelectorAll(`.st-key-${key} [data-testid="stMetric"]`).length"""
)


def summarize_upeh_rows(
    rows: Sequence[str] | None, badge: bool, rows_after: int | None, badge_after: bool
) -> str:
    """UPEH 가정 줄 한 줄 — 켠 뒤 ① 끝 가정 줄 수(정한 세 줄과 같은가)·배지, 100 으로 되돌린 뒤."""
    if rows is None:
        return "가정 구간 없음(조회기간에 이번 달 이후 달 없음) — 안 켬"
    prefix = f"UPEH {UPEH_TRIAL_PERCENT}% · "
    names = tuple(row[len(prefix) :] for row in rows)
    same = "정한 세 줄과 같음" if names == UPEH_ROW_NAMES else "정한 세 줄과 다름"
    after = "-" if rows_after is None else str(rows_after)
    shown = "있음" if badge else "없음"
    left = "남음" if badge_after else "사라짐"
    return (
        f"가정 줄 {len(rows)} — {same} · {UPEH_TRIAL_PERCENT} 배지 {shown} · "
        f"{UPEH_DEFAULT_PERCENT} 되돌린 뒤 가정 줄 {after} · 배지 {left}"
    )


def check_upeh_rows(screen: Screen) -> str:
    """공정 Capa 상세 — 조건 카드 「이 세션만」 UPEH 가정 % 를 110 으로 바꿔 ① 끝 가정 세
    줄(소요대수 · 확보율 · 확보기준 과부족)과 머리 배지를 세고 100 으로 되돌린다(세션 값 — DB 에
    쓰지 않는다). 세 줄은 그 달이 가정 구간 밖이어도 늘 선다(구간 밖 달은 빈칸) — 근거 카드의 가정
    한 줄은 고른 달이 구간 안일 때만 서므로 그것으로 세지 않는다."""
    screen.step("페이지 열기")
    screen.open_page(PROCESS_DETAIL_PAGE)
    screen.wait_for(
        lambda: screen.js(_KPI_COUNT_JS, PROCESS_DETAIL_KEYS["kpi"]), timeout=120, accept=bool
    )
    prefix = f"UPEH {UPEH_TRIAL_PERCENT}% · "
    screen.step("조건 카드")
    with opened_card(screen, PROCESS_DETAIL_CARD_KEY) as opened:
        if not opened:
            return "조건 카드 없음"
        field = screen.page.locator(
            f'[data-testid="stSidebar"] input[aria-label={_css_string(UPEH_PERCENT_LABEL)}]'
        ).first
        field.wait_for(state="visible", timeout=ACTION_TIMEOUT_MS)
        if "걸 구간이 없습니다" in screen.sidebar_text():
            return summarize_upeh_rows(None, False, None, False)
        start = _number(field.input_value()) or UPEH_DEFAULT_PERCENT
        try:
            screen.step(f"{UPEH_TRIAL_PERCENT} 넣기")
            _set_number(screen, field, UPEH_TRIAL_PERCENT)
            rows = screen.poll(
                lambda: screen.js(_UPEH_ROWS_JS, prefix),
                timeout=60,
                accept=lambda found: len(found or []) >= len(UPEH_ROW_NAMES),
            )
            badge = f"UPEH 가정 {UPEH_TRIAL_PERCENT}%" in screen.main_text()
        finally:
            screen.step("되돌리기")
            _set_number(screen, field, int(start))
        after = screen.poll(
            lambda: screen.js(_UPEH_ROWS_JS, "UPEH "), timeout=60, accept=lambda found: not found
        )
        badge_after = f"UPEH 가정 {UPEH_TRIAL_PERCENT}%" in screen.main_text()
    return summarize_upeh_rows(list(rows or []), badge, len(after or []), badge_after)


# 「구획」 칩의 (글자, 눌림) 차례.
_SECTIONS_JS = """(key) => {
  const box = document.querySelector(`.st-key-${key}`);
  if (!box) return null;
  return [...box.querySelectorAll("button[aria-pressed]")].map(
    (button) => [button.innerText.trim(), button.getAttribute("aria-pressed") === "true"]
  );
}"""
# HOME 주요공정 월 그림에서 누를 칸 — 표적 막대(trace 0) 가운데 공정이 실린 칸의 화면 좌표. 굴리는
# 칸(가로)과 창(세로) 안에 든 첫 칸이다. 좌표는 Plotly 축 변환(`l2p`)으로 낸다.
_HOME_CELL_JS = """({key, linkFields}) => {
  const plot = document.querySelector(`.st-key-${key} .js-plotly-plot`);
  if (!plot || !plot._fullLayout || !plot.data || !plot.data.length) return null;
  const trace = plot.data[0];
  const xa = plot._fullLayout.xaxis;
  const ya = plot._fullLayout.yaxis;
  const box = plot.getBoundingClientRect();
  let left = 0;
  let right = innerWidth;
  for (let node = plot.parentElement; node; node = node.parentElement) {
    if (["auto", "scroll", "hidden"].includes(getComputedStyle(node).overflowX)) {
      const rect = node.getBoundingClientRect();
      left = Math.max(left, rect.left);
      right = Math.min(right, rect.right);
    }
  }
  const custom = trace.customdata || [];
  let linked = 0;
  for (let i = 0; i < custom.length; i += 1) {
    const row = custom[i];
    if (!row || !row[row.length - linkFields]) continue;
    linked += 1;
    const base = Array.isArray(trace.base) ? trace.base[i] : trace.base || 0;
    const length = Array.isArray(trace.x) ? trace.x[i] : 1;
    const x = box.left + xa._offset + xa.l2p(base + length / 2);
    const y = box.top + ya._offset + ya.l2p(trace.y[i]);
    if (x > left + 2 && x < right - 2 && y > 2 && y < innerHeight - 2) return {linked, x, y};
  }
  return {linked, x: null, y: null};
}"""


def _sections(screen: Screen) -> list[bool] | None:
    found = screen.js(_SECTIONS_JS, PROCESS_DETAIL_SECTIONS_KEY)
    if not found:
        return None
    return [bool(pressed) for _, pressed in found]


def _wait_sections(screen: Screen) -> list[bool]:
    return list(
        screen.wait_for(lambda: _sections(screen), timeout=120, accept=lambda value: bool(value))
    )


def _set_sections(screen: Screen, wanted: bool | Sequence[bool]) -> bool:
    """「구획」 칩을 `wanted` 대로 둔다 — True/False 면 모두 펴거나 모두 접고, 목록이면 칩마다 그
    눌림으로(처음 그림으로 되돌릴 때). 칩 누름은 세션 값이다. 다 됐으면 True."""
    for _ in range(len(PROCESS_DETAIL_SECTION_LABELS) * 2):
        state = _wait_sections(screen)
        target = [wanted] * len(state) if isinstance(wanted, bool) else list(wanted)
        wrong = [index for index, pressed in enumerate(state) if pressed != target[index]]
        if not wrong:
            return True
        chips = screen.page.locator(f".st-key-{PROCESS_DETAIL_SECTIONS_KEY} button[aria-pressed]")
        chips.nth(wrong[0]).click()
        screen.wait_idle()
    return False


def opened_section_text(pressed: Sequence[bool] | None, target: int) -> str:
    """들어온 뒤 「구획」 칩 — 그 길의 구획만 펴졌는가(다른 구획의 접힘은 둔다)."""
    if not pressed:
        return "구획 칩 없음"
    label = PROCESS_DETAIL_SECTION_LABELS[target]
    others = sum(1 for index, value in enumerate(pressed) if value and index != target)
    if not pressed[target]:
        return f"{label} 접힌 채"
    return f"{label} 만 펼침" if others == 0 else f"{label} 펼침 · 다른 구획 {others}개도 펼침"


def summarize_entry_sections(
    collapsed: bool,
    home: str,
    warnings: int | None,
    gap: str,
    restored: bool,
) -> str:
    """들어온 길 한 줄 — 모두 접은 뒤 HOME 칸 → ①, 콘솔 경고 줄 수, 근거 카드 링크 → ④, 되돌림."""
    warned = "콘솔 경고 못 셈" if warnings is None else f"콘솔 경고 {warnings}줄"
    return (
        f"구획 {'모두 접음' if collapsed else '못 접음'} · HOME 칸 → {home} · {warned} · "
        f"근거 카드 링크 → {gap} · 구획 {'되돌림' if restored else '못 되돌림'}"
    )


def _click_home_cell(screen: Screen) -> str | None:
    """HOME 주요공정 칸 하나를 눌러 공정 Capa 상세로 간다. 못 갔으면 그 까닭(고정 글자)."""
    screen.open_home()
    arg = {"key": HOME_KEY_PROCESS_CHART_KEY, "linkFields": HOME_CELL_LINK_FIELD_COUNT}
    found = screen.poll(lambda: screen.js(_HOME_CELL_JS, arg), timeout=60, accept=bool)
    if not found:
        return "주요공정 그림 없음"
    if not found["linked"]:
        return "누를 칸 없음(과거 실적 칸뿐)"
    # 그림이 화면 아래에 있으면 좌표 누름이 화면 밖에 떨어진다 — 가운데로 굴린 뒤 다시 잰다.
    screen.page.locator(f".st-key-{HOME_KEY_PROCESS_CHART_KEY} .js-plotly-plot").first.evaluate(
        "(node) => node.scrollIntoView({block: 'center'})"
    )
    point = screen.wait_stable(lambda: screen.js(_HOME_CELL_JS, arg), timeout=10)
    if point.get("x") is None:
        return "화면 안에 누를 칸 없음"
    screen.page.mouse.move(float(point["x"]), float(point["y"]))
    time.sleep(0.3)
    screen.page.mouse.click(float(point["x"]), float(point["y"]))
    arrived = screen.poll(
        lambda: screen.path().rstrip("/").endswith(PROCESS_DETAIL_PAGE), timeout=30, accept=bool
    )
    screen.wait_idle()
    return None if arrived else "공정 Capa 상세로 안 감"


def _choose_gap_process(screen: Screen) -> bool:
    """`설비 조회 조건` 의 `공정` 에서 `전체 합계` 다음 선택지(첫 공정)를 고른다. 골랐으면 True."""
    field = screen.page.locator(f'[data-testid="stSidebar"] .st-key-{GAP_PROCESS_KEY} input').first
    field.wait_for(state="visible", timeout=ACTION_TIMEOUT_MS)
    screen.wait_stable(field.bounding_box, timeout=10)
    for _ in range(3):
        field.click()
        if screen.poll(lambda: screen.js(_LISTBOX_OPEN_JS), timeout=5, accept=bool):
            break
    if not screen.js(_LISTBOX_OPEN_JS):
        return False
    screen.page.keyboard.press("ArrowDown")
    screen.page.keyboard.press("Enter")
    screen.wait_idle()
    return bool(field.input_value() != GAP_ALL_PROCESSES)


def _restore_gap_process(screen: Screen) -> None:
    field = screen.page.locator(f'[data-testid="stSidebar"] .st-key-{GAP_PROCESS_KEY} input').first
    if field.count() and field.input_value() != GAP_ALL_PROCESSES:
        field.click()
        field.type(GAP_ALL_PROCESSES, delay=20)
        screen.page.keyboard.press("Enter")
        screen.wait_idle()


def _gap_link_entry(screen: Screen) -> str:
    """가용설비 현황 → Summary › Static 대비 일정에서 공정 하나를 골라 설비 일정 기준 칸을 누르고
    근거 카드의 ④ 링크로 공정 Capa 상세에 간다. 들어간 뒤 「구획」 칩 글, 못 갔으면 그 까닭."""
    screen.open_page(EQUIPMENT_PAGE)
    open_equipment_tab(screen, GAP_TAB)
    changed: list[tuple[str, str]] = []
    try:
        for key, option in (
            (GAP_RESULT_VIEW_KEY, GAP_SHEET_VIEW),
            (GAP_DETAIL_MODE_KEY, GAP_SHEET_MODE),
        ):
            before = _choose_segment(screen, key, option)
            if before is not None and before != option:
                changed.append((key, before))
        with opened_card(screen, EQUIPMENT_CARD_KEY) as opened:
            if not opened:
                return "설비 조회 조건 카드 없음"
            try:
                if not _choose_gap_process(screen):
                    return "공정 못 고름"
                sheet = _gap_sheet(screen, timeout=120)
                cell = gap_sheet_click_target(sheet["cells"])[0] if sheet else None
                if cell is None or not _click_gap_cell(screen, cell):
                    return "누를 칸 없음"
                link = screen.page.locator('[data-testid="stMain"] a').filter(
                    has_text=GAP_DETAIL_LINK_LABEL
                )
                if not screen.poll(link.count, timeout=30, accept=lambda count: count > 0):
                    return "링크 없음"
                link.first.click()
                arrived = screen.poll(
                    lambda: screen.path().rstrip("/").endswith(PROCESS_DETAIL_PAGE),
                    timeout=30,
                    accept=bool,
                )
                screen.wait_idle()
                if not arrived:
                    return "공정 Capa 상세로 안 감"
                return opened_section_text(_wait_sections(screen), 3)
            finally:
                if not screen.path().rstrip("/").endswith(EQUIPMENT_PAGE):
                    screen.open_page(EQUIPMENT_PAGE)
                    open_equipment_tab(screen, GAP_TAB)
                with opened_card(screen, EQUIPMENT_CARD_KEY):
                    _restore_gap_process(screen)
    finally:
        for key, option in reversed(changed):
            _choose_segment(screen, key, option)


def stopped_path(exc: BaseException) -> str:
    """한 길이 예외로 멈췄을 때 그 칸에 적는 글 — 예외 종류만(문구는 식별값을 실을 수 있다)."""
    return f"멈춤({type(exc).__name__})"


def _home_entry(screen: Screen) -> tuple[str, int | None]:
    """HOME 칸 → ① 길 — (그 칸 글, 그 사이 콘솔 경고 줄 수). 길이 예외로 멈춰도 `멈춤(종류)` 로
    적고 경고 줄은 그때까지를 센다 — 이 길 하나가 깨져도 ④ 길과 경고 칸을 잃지 않는다."""
    before = console_lines(screen, FRAGMENT_CALLBACK_WARNING)
    try:
        home = _click_home_cell(screen) or opened_section_text(_wait_sections(screen), 0)
    except Exception as exc:  # noqa: BLE001 — 이 길만 멈춤으로 적고 ④ 길은 돈다
        home = stopped_path(exc)
    after = settled_console_lines(screen, FRAGMENT_CALLBACK_WARNING, before)
    return home, None if before is None or after is None else after - before


def check_entry_sections(screen: Screen) -> str:
    """공정 Capa 상세 「구획」 칩을 모두 접은 뒤 밖에서 들어오면 그 길의 구획만 다시 펴지는가 —
    HOME `주요공정 확보율` 칸 → ①, 가용설비 현황 Static 대비 일정 근거 카드의 ④ 링크 → ④. HOME
    칸을 누르는 동안 앱 콘솔에 프래그먼트 콜백 경고가 몇 줄 섰는지도 센다(줄 수만). 두 길은 따로
    돈다 — HOME 쪽이 누를 칸이 없거나 예외로 멈춰도 공정 Capa 상세를 다시 열어 구획을 접고 ④ 길을
    잰다(멈춘 길은 `멈춤(종류)`). 칩 · 공정 상자 · 전환은 세션 값이고 끝에 되돌린다 — DB 에 쓰지
    않는다. 공정 이름은 찍지 않는다."""
    screen.step("페이지 열기")
    screen.open_page(PROCESS_DETAIL_PAGE)
    # 처음 그림(새 세션은 넷 다 펼침)으로 되돌린다 — 칩 수가 다르면 모두 편다.
    first = _wait_sections(screen)
    initial: bool | list[bool] = first if len(first) == len(PROCESS_DETAIL_SECTION_LABELS) else True
    home = gap = "안 해 봄"
    warnings: int | None = None
    collapsed = restored = False
    try:
        screen.step("구획 모두 접기")
        collapsed = _set_sections(screen, False)
        if collapsed:
            screen.step("HOME 칸 누르기")
            home, warnings = _home_entry(screen)
            screen.step("구획 다시 접기")
            if not screen.path().rstrip("/").endswith(PROCESS_DETAIL_PAGE):
                screen.open_page(PROCESS_DETAIL_PAGE)
            if _set_sections(screen, False):
                screen.step("근거 카드 링크")
                try:
                    gap = _gap_link_entry(screen)
                except Exception as exc:  # noqa: BLE001 — 이 길만 멈춤으로 적는다
                    gap = stopped_path(exc)
            else:
                gap = "다시 못 접음"
    finally:
        screen.step("구획 되돌리기")
        if not screen.path().rstrip("/").endswith(PROCESS_DETAIL_PAGE):
            screen.open_page(PROCESS_DETAIL_PAGE)
        restored = _set_sections(screen, initial)
    return summarize_entry_sections(collapsed, home, warnings, gap, restored)


# 데이터 편집기(Glide)의 보이는 첫 표 — 그 상자 좌표. 머리 칸 풍선은 머리 줄 위에 마우스가 있을 때만
# 선다(`stDataFrameTooltipContent`).
_FIRST_GRID_JS = """() => {
  const main = document.querySelector('[data-testid="stMain"]');
  const selector = '[data-testid="stDataFrame"], [data-testid="stDataEditor"]';
  const grids = [...(main ? main.querySelectorAll(selector) : [])].filter(
    (grid) => grid.getBoundingClientRect().width > 0
  );
  if (!grids.length) return null;
  const rect = grids[0].getBoundingClientRect();
  return {left: rect.left, top: rect.top, width: rect.width};
}"""
_GRID_TOOLTIP_JS = """() => {
  const tip = document.querySelector('[data-testid="stDataFrameTooltipContent"]');
  return tip ? (tip.innerText || "").trim() : "";
}"""
# 머리 줄의 세로 자리(표 위 끝부터, px)와 훑는 가로 걸음.
GRID_HEADER_PROBE_Y_PX: Final = 17
GRID_HEADER_PROBE_STEP_PX: Final = 60


def summarize_upeh_help(text: str | None) -> str:
    """UPEH 월 칸 머리 풍선 — 섰는가와 정한 낱말(UPEH · ST(분))을 밝히는가. 풍선 글은 찍지
    않는다."""
    if text is None:
        return "UPEH 편집표 없음"
    if not text:
        return "월 칸 머리 풍선 없음"
    missing = [word for word in UPEH_HELP_WORDS if word not in text]
    if missing:
        return f"월 칸 머리 풍선 있음 · 없는 낱말 {len(missing)}개"
    return "월 칸 머리 풍선 있음 · Main UPEH · MI ST(분) 밝힘"


def check_upeh_help(screen: Screen) -> str:
    """기준 정보 → UPEH 편집표의 월 칸 머리에 마우스를 올려 도움말 풍선이 서는지, 그 글이 Main
    UPEH · MI ST(분)를 밝히는지. 머리 칸 DOM 은 크기가 0 이라(Glide 캔버스) 머리 줄 좌표를 오른쪽
    끝(월 칸)부터 왼쪽으로 훑는다. 칸은 고치지 않는다."""
    screen.step("페이지 열기")
    screen.open_page(REFERENCE_PAGE)
    screen.open_tab("UPEH")
    grid = screen.page.locator(
        '[data-testid="stMain"] [data-testid="stDataFrame"], '
        '[data-testid="stMain"] [data-testid="stDataEditor"]'
    )
    if not screen.poll(grid.count, timeout=120, accept=lambda count: count > 0):
        return summarize_upeh_help(None)
    grid.first.scroll_into_view_if_needed()
    screen.step("머리 줄 훑기")
    box = screen.wait_stable(lambda: screen.js(_FIRST_GRID_JS), timeout=15)
    y = float(box["top"]) + GRID_HEADER_PROBE_Y_PX
    right = float(box["left"]) + float(box["width"]) - 20
    text = ""
    x = right
    while x > float(box["left"]) and not text:
        screen.page.mouse.move(x, y)
        text = str(screen.poll(lambda: screen.js(_GRID_TOOLTIP_JS), timeout=1.5, accept=bool))
        x -= GRID_HEADER_PROBE_STEP_PX
    screen.page.mouse.move(float(box["left"]), max(y - 60, 1.0))
    return summarize_upeh_help(text)


# 배치 편집기 영역 요소(그림자 DOM — 로케이터가 뚫는다). 영역은 이름표만 눌림을 받는다.
ZONE_SELECTOR: Final = ".sle-mark.mark-zone"
ZONE_TAG_SELECTOR: Final = ".sle-mark.mark-zone .sle-zone-tag"
ZONE_FIELDS: Final = (".sle-mark-border", ".sle-mark-align")
# 영역 요소가 선 층을 찾을 때 여는 층 수의 상한(층 목록 표 `배치대수` 차례).
ZONE_FLOOR_LIMIT: Final = 12
# 층을 고른 뒤 편집기가 그 층 그림(머리 이름 = 고른 층)으로 서기를 기다리는 시간(초).
ZONE_FLOOR_DRAW_SECONDS: Final = 30
# 편집기 그림 뿌리(그림자 DOM 안 — 로케이터가 뚫는다). 그 뿌리의 머리 이름(`.sle-title`, 보기
# 화면에서는 숨지만 글은 층 이름 「동 층」 이다)이 고른 층일 때만 영역 수를 낸다. 아니면 null.
ZONE_CANVAS_SELECTOR: Final = ".sle-canvas"
_ZONE_COUNT_JS = f"""(canvases, label) => {{
  for (const svg of canvases) {{
    const title = svg.getRootNode().querySelector(".sle-title");
    if (title && (title.textContent || "").trim() === label) {{
      return svg.querySelectorAll("{ZONE_SELECTOR}").length;
    }}
  }}
  return null;
}}"""


def _zone_count(canvases: Any, label: str) -> int | None:
    """`label` 층 그림으로 선 편집기의 영역 요소 수. 그 층 그림이 아직 없으면 None."""
    found = canvases.evaluate_all(_ZONE_COUNT_JS, label)
    return None if found is None else int(found)


def summarize_space_zone_fields(
    looked: int,
    found_at: int | None,
    fields: Sequence[bool] | None,
    switched_off: bool,
    *,
    missed: int = 0,
) -> str:
    """영역 칸 한 줄 — 영역이 선 층을 몇째에 찾았나, 고른 영역의 `테두리` · `글자 정렬` 칸. 영역을
    못 찾았으면 연 층 수와, 그 가운데 편집기가 그 층 그림으로 서지 않아 못 본 층 수(`missed`)."""
    if found_at is None:
        unseen = f" · 못 본 층 {missed}개" if missed else ""
        return f"영역 없음(층 {looked}개 봄{unseen})"
    if fields is None:
        return f"영역 있는 층 {found_at}번째 · `배치 편집` 스위치 없음"
    border, align = fields
    return (
        f"영역 있는 층 {found_at}번째 · 테두리 칸 {'있음' if border else '없음'} · 글자 정렬 칸 "
        f"{'있음' if align else '없음'} · 적용 안 함{'' if switched_off else ' · 편집 못 끔'}"
    )


def check_space_zone_fields(screen: Screen) -> str:
    """Space 층 상세 배치 편집기에서 영역 요소 하나를 골라 선택 칸에 `테두리` · `글자 정렬` 이
    서는지. 층 목록 표의 `배치대수` 차례로 층을 열어(상한 `ZONE_FLOOR_LIMIT`) 영역이 선 첫 층에서
    본다. 영역은 이름표를 눌러 고른다(안쪽은 눌림을 받지 않아 누르면 기다림이 다 된다). 값은
    바꾸지 않고 `Esc` 로 풀고 `적용` 없이 `배치 편집` 을 끈다 — DB 에 쓰지 않는다. 층 이름은 찍지
    않는다."""
    screen.step("페이지 열기")
    screen.open_space_overview()
    screen.step("층 목록")
    grid, placed_column = screen.grid_with_column("배치대수")
    building_column = screen.column_index(grid, "동")
    floor_column = screen.column_index(grid, "층")
    if building_column is None or floor_column is None:
        return "층 목록 표의 `동`·`층` 칸 없음"
    rows = screen.grid_rows(grid, [building_column, floor_column, placed_column])
    floors = sorted(
        ((row[0], row[1], _number(row[2])) for row in rows if row[0] and row[1]),
        key=lambda floor: -floor[2],
    )[:ZONE_FLOOR_LIMIT]
    canvases = screen.page.locator(ZONE_CANVAS_SELECTOR)
    found_at: int | None = None
    missed = 0
    screen.step("영역 있는 층 찾기")
    for position, (building, floor, _) in enumerate(floors, start=1):
        label = f"{building} {floor}"
        screen.choose_by_typing("층 바로 가기", label)
        # 고른 층이 맞고 편집기가 그 층 그림으로 섰을 때만 영역 수를 믿는다 — 앞 층 그림이 남은 채
        # 세면 영역이 있는 층을 「없음」 으로 건너뛴다(호기가 많은 층은 그림이 늦게 선다).
        if screen.selectbox_value("층 바로 가기") != label:
            missed += 1
            continue

        def count_here(chosen: str = label) -> int | None:
            return _zone_count(canvases, chosen)

        drawn = screen.poll(
            count_here, timeout=ZONE_FLOOR_DRAW_SECONDS, accept=lambda count: count is not None
        )
        if drawn is None:
            missed += 1
            continue
        if drawn or screen.poll(count_here, timeout=2, accept=bool):
            found_at = position
            break
    if found_at is None:
        return summarize_space_zone_fields(len(floors), None, None, True, missed=missed)
    screen.step("배치 편집")
    if not screen.switch("배치 편집", True):
        return summarize_space_zone_fields(len(floors), found_at, None, True)
    fields: list[bool] = []
    try:
        screen.step("영역 고르기")
        tag = screen.page.locator(ZONE_TAG_SELECTOR).first
        tag.wait_for(state="visible", timeout=ACTION_TIMEOUT_MS)
        tag.click()
        for selector in ZONE_FIELDS:
            field = screen.page.locator(selector).first
            fields.append(bool(screen.poll(field.is_visible, timeout=5, accept=bool)))
        screen.page.keyboard.press("Escape")
    finally:
        switched_off = screen.switch("배치 편집", False)
    return summarize_space_zone_fields(len(floors), found_at, fields, switched_off)


ITEMS: tuple[Item, ...] = (
    Item("toolbar", "툴바 단추 차례", check_toolbar_order),
    Item("symbol", "사이드바 심볼 크기", check_sidebar_symbol),
    Item("bulk_import_target", "설비 마스터 엑셀·CSV 등록할 표", check_bulk_import_target),
    Item("progress_box", "필요 단축 일정 진척 비교 상자", check_progress_box),
    Item("space_drawer", "Space 미배치 서랍", check_space_drawer),
    Item("sidebar_panel", "HOME 조회 조건 패널", check_sidebar_panel),
    Item("panel_rows_other_pages", "다른 화면 패널 줄", check_panel_rows_other_pages),
    Item("scenario_popup", "시나리오 팝업", check_scenario_popup),
    Item("period_popup", "조회기간 팝업", check_period_popup),
    Item("process_popup", "공정 필터 팝업", check_process_popup),
    Item("process_detail", "공정 Capa 상세", check_process_detail),
    Item("equipment_headers", "설비 마스터 표 머리(39열)", check_equipment_headers),
    Item("sidebar_groups", "사이드바 그룹 셋", check_sidebar_groups),
    Item("space_fader", "Space 기준일 페이더", check_space_fader),
    Item("gap_sheet", "Static 대비 일정 비교 시트", check_gap_sheet),
    Item("equipment_scenario_line", "설비 시나리오 줄·팝업", check_equipment_scenario_line),
    Item("space_floor_state", "Space 층 사용 칸", check_space_floor_state),
    Item("page_tabs", "화면 탭 줄", check_page_tabs),
    Item("equipment_moves", "가용설비 현황 탭 둘·옮긴 자리", check_equipment_moves),
    Item("constraint_sim", "제약 시뮬레이션", check_constraint_simulation),
    Item("space_scenario_row", "Space 설비 시나리오 줄·팝업", check_space_scenario_row),
    Item("equipment_grid", "설비 마스터 표 칸 고치기", check_equipment_grid),
    Item("space_shortening", "Space 필요 단축 보기", check_space_shortening),
    Item("upeh_rows", "공정 Capa 상세 UPEH 가정 줄", check_upeh_rows),
    Item("entry_sections", "공정 Capa 상세 들어온 길 구획", check_entry_sections),
    Item("upeh_help", "기준 정보 UPEH 월 칸 도움말", check_upeh_help),
    Item("space_zone_fields", "Space 배치 편집기 영역 칸", check_space_zone_fields),
)


# ---------------------------------------------------------------------------------- 실행


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="사내 배포 화면 확인(런북 7장). 별도 포트 앱을 헤드리스 Chrome 으로 본다."
    )
    parser.add_argument(
        "--playwright-dir",
        type=Path,
        default=None,
        help="`uv pip install --target` 로 Playwright 를 깐 저장소 밖 폴더",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="확인용 앱 포트")
    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Playwright 브라우저 채널(기본 chrome — 깔린 Chrome). 빈 글자면 내장 Chromium",
    )
    parser.add_argument(
        "--items", default=None, help="돌릴 항목 키를 쉼표로(--list 로 본다). 비우면 전부"
    )
    parser.add_argument("--list", action="store_true", help="항목 목록만 찍고 끝낸다")
    parser.add_argument(
        "--allow-writes",
        action="store_true",
        help="DB 에 쓰는 항목도 돌린다(저장 뒤 지워 되돌리는 항목만 있다). 사용자 허락이 있을 때만",
    )
    parser.add_argument(
        "--output", type=Path, default=None, help="같은 블록을 이 파일에도 쓴다(저장소 밖)"
    )
    parser.add_argument(
        "--shots", type=Path, default=None, help="항목마다 스크린샷을 둘 폴더(저장소 밖)"
    )
    parser.add_argument(
        "--budget-minutes",
        type=float,
        default=DEFAULT_BUDGET_MINUTES,
        help="스크립트 시작부터 이 시간을 넘으면 남은 항목은 돌리지 않는다(사내 제한 30분)",
    )
    parser.add_argument(
        "--start-timeout", type=float, default=START_TIMEOUT_SECONDS, help="앱 기동을 기다릴 초"
    )
    parser.add_argument(
        "--ignore-other-apps",
        action="store_true",
        help=(
            "떠 있는 다른 `streamlit run app.py` 를 보지 않는다(DB 잠금은 그대로 본다). "
            "사용자 앱이 없는 것을 손수 확인했을 때, 또는 다른 저장소의 앱이 늘 떠 있는 사외 "
            "개발 PC 에서만 — "
            "쓰면 블록 머리에 「프로세스 무시」가 찍힌다"
        ),
    )
    return parser.parse_args(argv)


def select_items(spec: str | None, items: Sequence[Item]) -> list[Item] | None:
    """`--items` 로 고른 항목(등록 차례). 모르는 키가 있으면 None."""
    if spec is None:
        return list(items)
    keys = [key.strip() for key in spec.split(",") if key.strip()]
    known = {item.key for item in items}
    if not keys or any(key not in known for key in keys):
        return None
    return [item for item in items if item.key in keys]


def _progress(message: str) -> None:
    """진행 줄은 stderr 로 — stdout 에는 블록만 남는다. 항목 이름과 초만 찍는다."""
    print(message, file=sys.stderr, flush=True)


@contextmanager
def open_browser(sync_api: Any, channel: str) -> Iterator[Any]:
    """헤드리스 브라우저의 새 페이지. 나갈 때 브라우저를 닫는다.

    `Ctrl+C`(KeyboardInterrupt)가 Playwright 호출 안에서 나면 `browser.close()` 가 끝나지 않는
    기다림에 빠져 뒤의 앱 끄기까지 막는다(사외 재현). 그때는 닫지 않고 `sync_playwright` 의 정리에
    넘긴다 — 드라이버가 브라우저를 함께 끝낸다. 보통 예외와 정상 끝에서만 닫는다.
    """
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=channel or None, headless=True)
        try:
            context = browser.new_context(
                viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]}, locale="ko-KR"
            )
            context.set_default_timeout(ACTION_TIMEOUT_MS)
            yield context.new_page()
        except Exception:
            browser.close()
            raise
        browser.close()


def _migration_snapshot() -> tuple[frozenset[int], ...] | None:
    """두 DB 에 걸린 마이그레이션 번호. 읽지 못하면 None(머리 줄에 「세지 못함」)."""
    try:
        return tuple(applied_versions(path, table) for path, table, _ in migration_targets())
    except duckdb.Error:
        return None


def _pending(snapshot: tuple[frozenset[int], ...]) -> tuple[int, int]:
    counts = [
        len(code - applied)
        for (_, _, code), applied in zip(migration_targets(), snapshot, strict=True)
    ]
    return counts[0], counts[1]


def preflight(args: argparse.Namespace) -> tuple[int, str] | None:
    """띄우기 전 확인 — 사용자 앱(프로세스·DB 잠금)과 포트. 막히면 (종료 코드, `--output` 한 줄),
    아니면 None.

    사용자 앱은 끄지 않는다. 다른 사람이 쓰고 있을 수 있다(런북 7장). 프로세스를 살피지 못하면
    없다고 넘기지 않는다 — 가만히 떠 있는 앱은 DB 잠금에 안 잡힌다.
    """
    if not args.ignore_other_apps:
        running = running_app_count()
        if running is None:
            print(SCAN_FAILED_MESSAGE)
            return EXIT_DEFERRED, "미룸 — 프로세스를 살피지 못했습니다"
        if running:
            print(DEFERRED_MESSAGE)
            return EXIT_DEFERRED, "미룸 — 사용자 앱이 떠 있습니다"
    try:
        locked = locked_databases((DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH))
    except duckdb.Error as exc:
        print(f"DB 를 열지 못했습니다 — {type(exc).__name__}")
        return EXIT_NOT_READY, f"멈춤 — DB 를 열지 못했습니다({type(exc).__name__})"
    if locked:
        print(DEFERRED_MESSAGE)
        return EXIT_DEFERRED, "미룸 — 사용자 앱이 떠 있습니다"
    if port_in_use(args.port):
        print(f"포트 {args.port} 를 이미 누가 쓰고 있습니다 — --port 로 빈 포트를 줍니다")
        return EXIT_NOT_READY, f"멈춤 — 포트 {args.port} 를 이미 누가 쓰고 있습니다"
    return None


def _prepare_folders(args: argparse.Namespace) -> bool:
    """`--output` 의 부모와 `--shots` 를 미리 만든다. 못 만들면 False."""
    folders = []
    if args.output is not None:
        folders.append(Path(args.output).parent)
    if args.shots is not None:
        folders.append(Path(args.shots))
    for folder in folders:
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"출력 폴더를 만들지 못했습니다 — {type(exc).__name__}")
            return False
    return True


class OutputFile:
    """`--output` 쓰기. 처음에 「확인 시작」으로 덮어써서 지난 실행의 블록이 남지 않게 하고, 일찍
    끝나면 고정 한 줄로, 항목이 돌면 그때마다 전체 블록으로 바꾼다. 쓰지 못하면 stderr 한 줄만."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.failed = False

    def write_block(self, block: str) -> None:
        if self.path is None or self.failed:
            return
        try:
            self.path.write_bytes(block.encode("utf-8"))
        except OSError as exc:
            self.failed = True
            _progress(
                f"--output 에 쓰지 못했습니다 — {type(exc).__name__}(블록은 stdout 에 찍는다)"
            )

    def note(self, line: str) -> None:
        self.write_block(status_block(line))


def run(argv: Sequence[str] | None = None) -> int:
    began = time.monotonic()
    args = parse_args(argv)
    if args.list:
        print(render_item_list(ITEMS))
        return EXIT_OK
    items = select_items(args.items, ITEMS)
    if items is None:
        print(f"모르는 항목: {args.items} — 고를 수 있는 키: {', '.join(i.key for i in ITEMS)}")
        return EXIT_NOT_READY
    refused = refused_paths(args)
    if refused:
        print(
            "저장소 안이거나 장치·UNC·스트림·하드 링크 경로라 받지 않습니다 — "
            f"{', '.join(refused)} 에 저장소 밖 드라이브 경로를 줍니다"
        )
        return EXIT_NOT_READY
    if not _prepare_folders(args):
        return EXIT_NOT_READY
    output = OutputFile(args.output)
    output.note("확인 시작 — 아직 항목 없음")
    try:
        return _check(args, items, began, output)
    except Exception as exc:  # noqa: BLE001 — 문구 대신 종류만
        print(f"예상 밖 오류로 멈췄습니다 — {type(exc).__name__}")
        output.note(f"멈춤 — 예상 밖 오류({type(exc).__name__})")
        return EXIT_NOT_READY


def _check(args: argparse.Namespace, items: list[Item], began: float, output: OutputFile) -> int:
    sync_api = load_playwright(args.playwright_dir) if args.playwright_dir is not None else None
    if sync_api is None:
        print(INSTALL_HINT)
        output.note("멈춤 — Playwright 없음")
        return EXIT_NOT_READY
    blocked = preflight(args)
    if blocked is not None:
        code, line = blocked
        output.note(line)
        return code

    deadline = began + args.budget_minutes * 60
    before = _migration_snapshot()
    facts = RunFacts(
        channel=args.channel,
        stamp=applied_stamp(),
        allow_writes=args.allow_writes,
        process_scan="무시" if args.ignore_other_apps else "봄",
        pending_migrations=None if before is None else _pending(before),
    )
    outcomes: list[Outcome] = []

    def emit() -> str:
        """지금까지의 블록. `--output` 은 항목마다 다시 써서 중간에 끊겨도 돈 칸이 남는다."""
        facts.elapsed_seconds = time.monotonic() - began
        block = render_block(outcomes, total=len(items), facts=facts)
        output.write_block(block)
        return block

    def record(outcome: Outcome) -> None:
        outcomes.append(outcome)
        _progress(f"· {outcome.item.title} — {outcome.seconds:.1f}초")
        emit()

    code = EXIT_OK
    _progress(f"확인용 앱을 {APP_ADDRESS}:{args.port} 에 띄웁니다 …")
    # 앱 콘솔은 정한 경고 글이 든 줄 수만 센다(`ConsoleCounter` — 글은 파일에도 남기지 않는다).
    console = ConsoleCounter(CONSOLE_NEEDLES)
    try:
        with StreamlitApp(args.port, start_timeout=args.start_timeout, console=console) as app:
            facts.started_seconds = app.started_seconds
            _progress(f"앱이 섰습니다({app.started_seconds:.1f}초). 브라우저로 들어갑니다 …")
            emit()
            try:
                with open_browser(sync_api, args.channel) as page:
                    screen = Screen(page, app.base_url, shots=args.shots)
                    screen.console = console
                    facts.entered_seconds = screen.enter()
                    facts.app_problem = screen.app_problem()
                    if facts.app_problem is not None:
                        for item in items:
                            record(Outcome(item, f"{UNRECORDED} — {facts.app_problem}"))
                        code = EXIT_NOT_READY
                    else:
                        run_items(
                            screen,
                            items,
                            allow_writes=args.allow_writes,
                            deadline=deadline,
                            on_outcome=record,
                        )
            except Exception as exc:  # noqa: BLE001 — 브라우저·입장 실패는 까닭 종류만 알린다
                print(f"브라우저로 들어가지 못했습니다 — {type(exc).__name__}")
                facts.stop_reason = f"멈춤 — 브라우저로 들어가지 못했습니다({type(exc).__name__})"
                code = EXIT_NOT_READY
    except AppStartError as exc:
        print(f"앱이 뜨지 않았습니다 — {exc}")
        output.note(f"멈춤 — 앱이 뜨지 않았습니다: {exc}")
        return EXIT_NOT_READY
    if not app.port_released:
        _progress(
            f"확인용 앱 프로세스가 남았을 수 있습니다 — 포트 {args.port} 가 아직 열려 있습니다"
        )
    if over_budget_count(outcomes):
        code = EXIT_NOT_READY
    after = _migration_snapshot()
    if before is not None and after is not None:
        applied = [len(now - then) for now, then in zip(after, before, strict=True)]
        facts.applied_migrations = (applied[0], applied[1])
    print(emit())
    return code


def main(argv: Sequence[str] | None = None) -> int:
    """종료 코드 — 0 끝까지 돎 · 2 준비 안 됨·멈춤 · 3 미룸(사용자 앱이 떠 있거나 살피지 못함).

    미룸을 1 로 두지 않는 것은 강제 종료(Windows `TerminateProcess`)와 파이썬의 처리 안 된 예외가
    1 로 끝나기 때문이다. 예상 밖 예외는 종류만 찍고 2 로 끝낸다(문구에는 식별값이 실릴 수 있다).
    `Ctrl+C` 는 그대로 올린다 — 띄운 앱은 그 사이 `with` 가 끈다.
    """
    _use_utf8_stdout()
    try:
        return run(argv)
    except Exception as exc:  # noqa: BLE001 — 문구 대신 종류만
        print(f"예상 밖 오류로 멈췄습니다 — {type(exc).__name__}")
        return EXIT_NOT_READY


if __name__ == "__main__":
    raise SystemExit(main())
