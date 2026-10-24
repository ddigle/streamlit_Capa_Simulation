# Purpose: Streamlit 앱의 공식 시나리오 활성화, 공통 사이드바·조회기간과 페이지 탐색을 구성한다.

from contextlib import AbstractContextManager, nullcontext
from pathlib import Path

import streamlit as st
from streamlit.runtime.scriptrunner_utils.exceptions import StopException

from capa_simulation.auto_update_scheduler import ensure_auto_update_scheduler
from capa_simulation.components.app_credits import render_app_credits
from capa_simulation.components.app_header import (
    remembered_equipment_suffix,
    render_app_header,
    render_shell_style,
)
from capa_simulation.components.availability_sheet_keys import GAP_SHEET_CHART_KEY
from capa_simulation.components.equipment_scenario_status import (
    close_equipment_scenario_dialog,
    equipment_scenario_dialog_is_open,
    show_equipment_scenario_dialog,
)
from capa_simulation.components.home_rendering import HOME_CELL_CHART_KEYS
from capa_simulation.components.intro_overlay import render_intro_overlay
from capa_simulation.components.intro_summary import (
    render_intro_summary,
    summary_label_script,
    warm_intro_summary,
)
from capa_simulation.components.page_guide import guide_toolbar_script, render_guide_base_style
from capa_simulation.components.page_tabs import (
    leave_notice,
    page_unsaved_marks,
    render_page_tabs,
    route_page_tabs,
)
from capa_simulation.components.period_field import (
    close_period_dialog,
    period_dialog_is_open,
    render_period_field,
    show_period_dialog,
)
from capa_simulation.components.plotly_touch_scroll import plotly_touch_scroll_script
from capa_simulation.components.print_button import print_toolbar_script
from capa_simulation.components.scenario_edit_bar import pending_edit_labels, pending_edits_notice
from capa_simulation.components.scenario_status import (
    close_scenario_dialog,
    render_scenario_field,
    scenario_dialog_is_open,
    show_scenario_dialog,
)
from capa_simulation.components.sidebar_style import build_sidebar_stylesheet
from capa_simulation.components.theme_toggle import render_theme_toggle, unsaved_edits_marker
from capa_simulation.components.typography import render_typography_style
from capa_simulation.design import theme
from capa_simulation.navigation import CONDITIONS_SECTION, PageSpec, build_navigation_pages
from capa_simulation.page_bootstrap import (
    bootstrap_error_message,
    count_page_visit,
    forget_page_dialogs,
    render_schema_ahead_warning,
)
from capa_simulation.page_tabs_state import note_current_page
from capa_simulation.persistence._sql_helpers import pinned_connections
from capa_simulation.persistence.cache import get_scenario_repository
from capa_simulation.process_detail_state import PROCESS_DETAIL_CANVAS_CHART_KEY
from capa_simulation.scenario_activation import (
    bootstrap_latest_official_scenario,
    has_unsaved_scenario_changes,
)
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset
from capa_simulation.settings import (
    APP_NAME,
    DUCKDB_PATH,
    EQUIPMENT_DUCKDB_PATH,
    FAVICON_PATH,
)
from capa_simulation.sidebar_status import (
    CONDITION_DIALOG_FRAGMENT_KEY,
    CONDITION_DIALOG_SINK_KEY,
    CONDITIONS_BOX_KEY,
    PAGE_CONDITION_SLOT_COUNT,
    SIDEBAR_TOGGLE_SINK_KEY,
    begin_app_run,
    forget_month_range_placeholder,
    forget_page_condition_slots,
    on_box_toggle,
    register_equipment_scenario_slot,
    register_page_condition_slots,
    render_box_toggle_sink,
    render_sidebar_section,
    sidebar_expander,
)
from capa_simulation.sync_boot import enable_sync_state_if_managed, heartbeat_if_managed

# 그룹 상자 **안**에서 그 그룹의 대표 페이지를 부르는 이름. 머리글이 이미 그룹 이름을
# 말하므로 안에서까지 되풀이하지 않고 그 그룹 안에서의 자리로 부른다.
GROUP_MAIN_LABEL = "현황 요약"
ADMIN_BOX_KEY = "sidebar_admin_box"
# 직전 회차가 그린 페이지 주소. 그룹 상자는 **페이지가 바뀐 회차에만** 「지금 보는 페이지가
# 든 그룹」으로 되돌리고, 같은 페이지 안에서는 사용자가 여닫은 대로 둔다.
SIDEBAR_PAGE_KEY = "sidebar_last_page"


def active_condition_tab(spec: PageSpec) -> str | None:
    """공통 조건을 탭별로 가르는 화면에서 **이번 회차에 열릴** 탭 라벨.

    사이드바는 페이지보다 먼저 그려진다. 그래도 탭을 누른 회차에는 위젯 값이 이미 세션에
    들어와 있고, 다른 화면에 갔다 온 회차에는 위젯 값이 버려졌어도 `stateful_tabs` 가 적어 둔
    기억 칸이 남아 있다 — 페이지가 그 기억으로 탭을 되돌리므로 여기서도 같은 칸을 본다.
    둘 다 없으면 첫 탭이다. 바깥 탭이 안쪽 탭을 품은 탭(`SubTabs.parent`)이면 안쪽 탭 라벨을 같은
    길로 정해 돌려준다(`ConditionTabs.active_label`).
    """
    if spec.condition_tabs is None:
        return None
    return spec.condition_tabs.active_label(st.session_state)


@st.fragment(key=CONDITION_DIALOG_FRAGMENT_KEY)
def render_condition_dialogs(
    page_file: str | None,
    shows_scenario: bool,
    shows_period: bool,
    shows_equipment: bool = False,
) -> None:
    """조건 패널의 시나리오·조회기간·설비 시나리오 팝업을 여닫는 호스트 프래그먼트.

    키는 `sidebar_status.CONDITION_DIALOG_FRAGMENT_KEY` 다. 한 실행에 팝업은 하나뿐이고(여는 콜백이
    다른 칸을 비운다), 이 화면에 그 줄이 서지 않으면(탭을 옮겨 공통 조건을 읽지 않게 된 회차) 칸을
    버린다. 값 칸의 여는 콜백이 이 프래그먼트만 다시 돌리고, 팝업이 이 안에서 만들어지므로
    닫기(`on_dismiss`)도 이 프래그먼트만 다시 돌린다 — 둘 다 페이지를 다시 계산하지 않는다.
    프래그먼트만 도는 회차의 인자는 직전 전체 실행의 값이다. 화면·탭이 바뀌는 조작은 모두 전체
    실행이라 그 값이 낡지 않는다.

    **어느 갈래든 이벤트 칸(본문 밖 최상위 칸)에 정확히 한 자리를 쓴다** — 팝업이면 팝업 블록,
    아니면 빈 스타일 자리표시자다. 프래그먼트만 다시 돌 때 Streamlit 은 이벤트 칸의 쓰기 위치를
    전체 실행에서 이 프래그먼트를 부른 자리로 되돌리고, 브라우저는 그 자리의 요소를 갈아 끼운다.
    전체 실행에서 아무것도 쓰지 않으면 그 자리는 페이지의 첫 이벤트 요소(스타일만 든 `st.html` —
    툴바 Guide 단추를 보이게 하는 규칙, 재공 현황 지표 줄 폭 등)가 차지하고, 팝업을 여는 회차가
    그것을 덮어 다음 전체 실행까지 돌아오지 않는다. 팝업 본문도 이벤트 칸에 따로 쓰지 않는다
    (스타일만 든 `st.html`·`st.toast` 를 두지 않는다).
    """
    if shows_scenario and scenario_dialog_is_open():
        show_scenario_dialog(page_file)
    elif shows_period and period_dialog_is_open():
        show_period_dialog(page_file)
    elif shows_equipment and equipment_scenario_dialog_is_open():
        # 셋째 갈래. 팝업이 설비 DB 를 읽는 것은 연 동안뿐이다 — 이 호스트는 열림 키만 본다.
        show_equipment_scenario_dialog(page_file)
    else:
        close_scenario_dialog()
        close_period_dialog()
        close_equipment_scenario_dialog()
        # 스타일만 든 `st.html` 은 이벤트 칸으로 간다 — 본문 자리를 차지하지 않는다.
        st.html("<style></style>")


# 칸 선택(`on_select`)을 켠 그림 전부. 선택을 켜면 그림 위 터치 스크롤이 막히므로 막이에 넘긴다 —
# 선택을 켠 그림을 더하면 여기에도 더한다.
CELL_SELECT_CHART_KEYS = (
    *HOME_CELL_CHART_KEYS,
    PROCESS_DETAIL_CANVAS_CHART_KEY,
    GAP_SHEET_CHART_KEY,
)

# 이번 실행이 끝까지 돌았는지의 표지(`sidebar_status.begin_app_run`). **메시지를 보내는 첫
# Streamlit 호출보다 앞이다** — 그런 호출은 다른 요청이 이 실행을 끊는 자리라, 그 앞에서 끊긴
# 실행이 앞 실행의 「끝났다」를 남겨 두면 상자 여닫기·조건 패널 값 칸이 페이지 없이 프래그먼트만
# 돌린다.
app_run = begin_app_run()
st.set_page_config(
    page_title=APP_NAME,
    # 문자열 경로여야 한다 — Streamlit 은 `.svg` 로 끝나는 **파일**만 읽어 data URI 로 싣는다.
    page_icon=str(FAVICON_PATH),
    layout="wide",
    # `menu_items` 는 적지 않는다. ⋮ 메뉴는 통째로 감추고(`render_shell_style`), 앱 버전·개발 정보는
    # 모든 화면 사이드바 맨 아래의 앱 정보 카드(`components/app_credits.py`)가 보여 준다.
)
# 사이드바 상자를 여닫을 때 앱 전체 대신 다시 도는 빈 프래그먼트(`sidebar_status.on_box_toggle`).
# `st.stop()` 이 걸릴 수 있는 어떤 곳보다도 앞에서 등록한다.
with st.container(key=SIDEBAR_TOGGLE_SINK_KEY):
    render_box_toggle_sink()
# 이 실행이 쓸 테마를 먼저 정한다. **토큰을 하나라도 읽기 전**이어야 한다 — 색을 읽는
# 쪽은 여기서 담아 둔 값을 본다. 바뀌었으면 그 세션의 Figure 캐시도 여기서 비운다.
theme.begin_run()
# 탭을 처음 연 사용자에게 첫 로딩을 덮는 입장 화면. 무거운 부트스트랩보다 **먼저** 보내야
# 그동안을 덮는다. 토큰을 읽으므로 `theme.begin_run()` 뒤다. 매 회차 같은 자리에 같은 내용으로
# 그려야 첫 실행 도중의 rerun 에도 덮개가 내려가지 않는다 — 이미 들어간 탭이면 브라우저 쪽에서
# 아무것도 하지 않는다.
render_intro_overlay()
# 헤더 오른쪽 툴바 슬롯에 밝게/어둡게 버튼을 얹는다. Streamlit 이 테마를 기억하는 자리를
# 그대로 쓰므로 위젯과 우리 Figure 가 함께 바뀐다. 테마를 바꾸는 길은 이 버튼 하나다(⋮ 메뉴는
# 감춘다). `Guide` · `Print` 버튼도 같은 iframe 에 싣고, 툴바 차례는 `Guide · Print · 테마`다
# (`theme_toggle.TOOLBAR_BUTTON_ORDER`). Guide 는 기본은 감춰 두고 가이드를 단 페이지만 보이게
# 한다. `Print` 는 감춘 메뉴의 인쇄를 대신한다. 사이드바
# 머리칸의 앱 이름 라벨도 같은 iframe 이 세운다 — 원래 화면에서 공식버전 요약(Summary)으로
# 돌아오는 길이고, 요약이 준비돼야 입장 화면 JS 가 누를 수 있게 한다. 칸 선택을 켠 그림(HOME 두
# 월 그림·공정 Capa 상세 결합 캔버스·가용설비 비교 시트 — `CELL_SELECT_CHART_KEYS`) 위에서 시작한
# 터치가 화면을 스크롤하게 하는 막이(`plotly_touch_scroll`)도 여기 싣는다.
#
# **입장 화면 바로 뒤, 부트스트랩보다 앞이다.** 첫 방문·테마 키가 어긋난 로드는 이 iframe 의
# 스크립트가 새로고침하고 그 세션은 버려진다. 앞에서 보내야 버려질 세션이 부트스트랩·요약을 돌기
# 전에 새로고침이 걸린다. 입장 화면이 먼저인 것은 그것이 무엇보다 먼저 화면을 덮어야 해서다.
# ⋮ 메뉴·Deploy 감춤과 인쇄 규칙(사이드바·머리 띠·덮개 빼기)을 담은 껍데기 스타일도 여기서 보낸다 —
# 머리 띠(`render_app_header`)는 부트스트랩 뒤라, 거기에 두면 부트스트랩 오류 화면에 메뉴가
# 남고 그 화면을 인쇄하면 사이드바가 찍히며, 새로 읽을 때마다 메뉴가 잠깐 보였다 사라진다.
render_shell_style()
# 페이지 제목·상자 제목·큰 숫자의 Archivo 부분 글꼴(정적 서빙)과 그 자리 규칙. 색이 없는 고정
# 문자열이라 테마와 무관하고, 부트스트랩 오류 화면의 제목도 같은 서체로 서도록 여기서 보낸다.
render_typography_style()
render_guide_base_style()
render_theme_toggle(
    extra_scripts=(
        guide_toolbar_script(),
        summary_label_script(),
        print_toolbar_script(),
        plotly_touch_scroll_script(CELL_SELECT_CHART_KEYS),
    )
)

# managed 모드에서만 동기화 표시를 켠다. local 모드(개발 PC·기본값)에서는 아무 일도 하지
# 않으므로 이 호출이 있어도 동작이 바뀌지 않는다.
enable_sync_state_if_managed()
# 앱이 이 PC 에서 돌고 있다는 표시. DuckDB 는 프로세스 배타 잠금이라 앱이 떠 있는 동안
# 동기화 스크립트는 DB 를 열지 못한다 — 그 사실을 사람 말로 알릴 근거가 이 기록이다.
# 10초에 한 번만 실제로 쓴다.
heartbeat_if_managed()

# rerun 한 번 동안 시나리오 DB 인스턴스를 잡아 둔다. 그 회차의 연결들이 각자 인스턴스를 다시
# 만들지 않게 하는 것이 전부이고, rerun 이 끝나면 풀린다. 핀은 그 회차의 **첫 연결 때** 잡히므로
# DB 를 한 번도 읽지 않는 회차(캐시만 쓰는 화면의 재실행)는 인스턴스를 열지 않는다.
with pinned_connections(DUCKDB_PATH):
    try:
        bootstrap_latest_official_scenario(str(DUCKDB_PATH.resolve()))
    except Exception as exc:  # 어떤 실패든 원인을 읽을 수 있게 바꿔야 한다
        # DuckDB 파일은 프로세스 배타 잠금이다. 서버가 이미 떠 있는데 한 번 더 실행하면
        # 화면이 한 줄도 그려지기 전에 예외가 그대로 노출되고, Windows 로캘 탓에 원본
        # 메시지의 한글이 깨져 나온다. 사용자가 원인을 알 방법이 없어 안내로 바꾼다.
        # 머리 띠도 이 화면에 세운다 — 아래 `st.stop()` 뒤의 자리에는 닿지 않는다. 세션만 읽으므로
        # 실패한 부트스트랩을 다시 건드리지 않고, 올라온 시나리오가 없으면 앱 이름 두 줄(메인 라벨·
        # 부제)이다.
        render_app_header()
        st.error(bootstrap_error_message(exc), icon=":material/database_off:")
        with st.expander("원본 오류"):
            st.code(f"{type(exc).__name__}: {exc}")
        st.stop()
    apply_pending_scenario_preset()
    # 공식버전 자동 갱신 예약 — 이 프로세스에 배경 스레드 하나(`auto_update_scheduler`). 실행 줄
    # 허락 (`CAPA_AUTO_OFFICIAL_UPDATE=1`)이 없으면 환경변수만 보고 돌아가고, 있으면 첫 회차에 한 번
    # 세운다. 부트스트랩 **뒤**다 — 마이그레이션이 끝난 DB 에서 돈다. 실패해도 화면은 막지 않는다.
    ensure_auto_update_scheduler(str(DUCKDB_PATH.resolve()))
    # 입장 화면 Summary 가 그릴 최신 공식버전 요약. 로딩에 포함되도록 페이지보다 **먼저**
    # 보낸다 — 페이지가 `st.stop()` 하면 그 뒤로는 아무것도 브라우저에 닿지 않는다. 회차마다
    # 같은 값이라 한 번만 실제로 오가고, 시나리오 전체 Capa 계산은 HOME 과 한 칸을 나눠 쓴다.
    render_intro_summary(str(DUCKDB_PATH.resolve()))

    pages = build_navigation_pages()
    navigation = st.navigation(pages.ordered, position="hidden")
    # 지금 어느 페이지에 있는지는 **파이썬에서** 가른다. 활성 링크에 `aria-current` 도
    # 안정적인 클래스도 없고(emotion 해시뿐) CSS 만으로는 판정할 수 없다. `st.navigation()`
    # 이 이번 rerun 에 그릴 페이지를 그대로 돌려주므로 그 주소로 선택자를 만든다.
    #
    # `href` 가 곧 `url_path` 다. HOME 은 기본 페이지라 늘 빈 문자열이고, 그것도 이 한
    # 페이지만 가리키므로 선택자로 쓸 수 있다.
    active_href = navigation.url_path
    current_spec = pages.spec_for(navigation.url_path)
    page_file = None if current_spec is None else Path(current_spec.path).name
    # 탭 줄 콜백이 적어 둔 이동(다른 탭 고르기·지금 탭 닫기)과 탭 상한(10개). 상한은 옮기기 전에
    # 막고(탭 줄 JS·`refused_at_tab_limit`), 그래도 들어온 화면(뒤로가기로 닫은 탭의 기록)만 여기서
    # 직전 화면으로 되돌린다. 사이드바·머리 띠를 보내기 전에 끊는다. 직전 화면 주소는 아래에서
    # 이번 화면으로 바뀐다.
    route_page_tabs(current_spec, pages=pages, previous_url=st.session_state.get(SIDEBAR_PAGE_KEY))
    # 이 화면에 적용하지 않은 편집이 남았는가. 저장·불러오기·기간 변경은 그 편집을 버린다 —
    # 적용하지 않은 편집은 시나리오에 들어 있지 않다(`scenario_edit_bar.register_pending_edits`).
    # 세션만 읽는다. 조건 패널 맨 위 줄이 이 값을 쓴다.
    pending_edits = pending_edit_labels(page_file)
    # 탭에 점을 찍을 화면(저장·적용하지 않은 편집)과 지금 화면을 떠나면 사라지는 편집표 편집. 세션만
    # 읽는다. 아래 테마 표지와 탭 줄이 같은 값을 쓴다(`components/page_tabs.py`).
    unsaved_marks = page_unsaved_marks(page_file)

    st.html(
        build_sidebar_stylesheet(
            pages.groups,
            active_href,
            admin_box_key=ADMIN_BOX_KEY,
        )
        # 테마 버튼은 새로고침으로 테마를 바꾼다(새 세션). 저장하지 않은 시나리오 편집이나 탭에
        # 점을 찍는 편집(설비 편집본·Space FAB 배치 대기·Space 층 사용 편집 초안·적용 전 편집·Past
        # Data 초안·시나리오 관리 표 초안)이 있으면 묻게 표지를 단다 — 어느 페이지에서 눌러도 같은
        # 표지를 본다. 판정은 탭 점과 한 벌이다.
        + unsaved_edits_marker(has_unsaved_scenario_changes() or bool(unsaved_marks))
    )
    # 머리 띠의 「공식 vN」은 위 요약이 이 회차에 확인한 값을 읽는다 — 요약보다 뒤여야 한다.
    # 설비 시나리오를 읽는 화면은 아래 줄 끝에 설비 시나리오 꼬리를 단다 — 그 글은 페이지가 지난
    # 회차에 남긴 세션 값이다(설비 DB 를 읽지 않는다). 그 회차에 바뀌면 페이지가 띠를 다시 그린다.
    active_tab = None if current_spec is None else active_condition_tab(current_spec)
    render_app_header(
        equipment_suffix=(
            remembered_equipment_suffix()
            if current_spec is not None and current_spec.reads_equipment_scenario_on(active_tab)
            else None
        )
    )
    with st.sidebar.container(key="home_navigation"):
        st.page_link(pages.home, width="stretch")

    # 박스 목록은 `navigation.SIDEBAR_GROUPS` 하나에서 나온다. 위 CSS 선택자도 같은 선언을
    # 읽으므로, 그룹을 더할 때 이 파일에서 고칠 것이 없다.
    #
    # **`expanded=` 는 처음 그릴 때만 읽힌다.** 링크로 페이지를 옮기는 것은 새로고침이 아니라
    # 같은 화면 안의 rerun 이라, 프런트엔드는 이미 그려 둔 확장 패널의 여닫힘을 그대로 두고
    # 바뀐 `expanded` 값을 무시한다(브라우저 실측 — Static Capa 에서 Dynamic Capa 로 옮겨도
    # Static 이 펴진 채 남고 Dynamic 은 접힌 채였다. `main` 도 같았다). 「지금 보는 페이지가
    # 든 그룹만 편다」는 규칙을 실제로 지키려면 `key` 로 위젯을 만들고 **페이지가 바뀐
    # 회차에만** 세션 값을 그 규칙대로 되돌려야 한다. 같은 페이지 안에서 사용자가 여닫은
    # 것은 그대로 남는다 — 매 회차 덮어쓰면 방금 누른 클릭을 지운다.
    page_changed = st.session_state.get(SIDEBAR_PAGE_KEY) != navigation.url_path
    st.session_state[SIDEBAR_PAGE_KEY] = navigation.url_path
    # 지금 화면을 탭 목록에 더한다(이미 있으면 차례 그대로). 사이드바·HOME 칸·카드 링크·뒤로가기·
    # 주소, 어느 길로 들어왔든 이 한 줄로 탭이 된다. 페이지보다 앞이라 「이미 연 탭으로 들어옴」
    # 표지가 그 화면 본문보다 먼저 선다(`page_tabs_state.reentered_open_tab`).
    if current_spec is not None:
        note_current_page(current_spec.path, page_changed=page_changed)
    if page_changed:
        # 떠난 페이지의 팝업 열림 상태를 버린다. 닫지 않고 떠나면 돌아왔을 때 팝업이 저절로 뜬다.
        forget_page_dialogs()
        # 입력 위젯에서 나온 미리보기를 두는 화면이 「다시 들어왔다」를 알아보는 수다.
        count_page_visit()
    for group in pages.groups:
        # 하위가 없어도 **상자에 넣는다.** 묶을 것이 없으니 테두리가 필요 없다고 봤는데,
        # 사이드바에 상자가 다섯이고 이 둘만 맨몸으로 서니 목록이 두 층으로 읽혔다.
        # 테두리는 「묶음」만 뜻하는 것이 아니라 **한 칸**이라는 뜻이기도 하다.
        if not group.subpages:
            with st.sidebar.container(border=True, key=f"{group.slug}_box"):
                st.page_link(group.main, width="stretch")
            continue
        # 지금 보고 있는 페이지가 든 그룹만 편다. `url_path` 는 `st.navigation()` 이
        # 돌아야 채워지므로(그 전에는 `AttributeError`) 이 자리가 반드시 그 뒤여야 한다.
        group_paths = {page.url_path for page in (group.main, *group.subpages)}
        # `key` 는 곧 `st-key-…` 클래스다. 상자였을 때 걸어 둔 CSS 훅이 그대로 산다.
        group_key = f"{group.slug}_box"
        if page_changed or group_key not in st.session_state:
            st.session_state[group_key] = navigation.url_path in group_paths
        with st.sidebar.expander(
            group.main.title,
            icon=group.main.icon,
            key=group_key,
            on_change=on_box_toggle,
            args=(group_key,),
        ):
            st.page_link(group.main, label=GROUP_MAIN_LABEL, width="stretch")
            for page in group.subpages:
                st.page_link(page, width="stretch")

    # `Support` 상자와 앱 정보 카드는 **조회 조건 구역보다 먼저** 그린다. 화면에서는 둘 다
    # 사이드바 맨 아래다 — 관리 기능과 앱 정보라 계산 조건보다 아래, 가장 먼 곳이다. 그 자리는
    # 파이썬 차례가 아니라 CSS 의 `order` 가 지킨다(`sidebar_style`). 페이지가 더하는 조건 카드는
    # `navigation.run()` 안에서 그려져 파이썬 차례로는 어차피 이 둘보다 뒤다.
    # 파이썬 차례를 여기로 당기는 까닭은 **화면마다 같은 순번**에 서게 하는 것이다. Streamlit 은
    # 사이드바 요소를 key 가 아니라 순번으로 맞춰 갈아 끼운다. 아래 조건 상자는 화면마다 수가
    # 달라 그 뒤에 그리면 페이지를 옮길 때 이 둘의 순번이 밀리고, 지난 회차의 같은 상자가 옛
    # 순번에 흐린 사본으로 실행이 끝날 때까지 남는다. CSS 의 `order`·`sticky` 는 그 사본까지 맨
    # 아래로 끌어내려 `Support` 와 카드가 두 벌로 겹쳐 보였다(브라우저 실측). 이 앞에는 화면마다
    # 수가 같은 것(HOME 링크와 그룹 상자)만 세운다.
    # **다른 상자와 완전히 같은 양식이다.** 테두리도 요약 줄 글자도 아이콘도 페이지
    # 그룹과 같게 둔다 — 계산 흐름 밖이라는 것은 서식이 아니라 위 CSS 가 지키는 맨 아래라는
    # 자리와 그 앞 간격이 말한다.
    # 이름은 `Support` 다. 전에는 `Preference` 였는데 HOME·가용설비 현황 본문의 같은 이름
    # 탭(그 화면의 표시 설정, 아이콘 `tune`)과 낱말·아이콘이 모두 겹쳐, 링크 목록인 이
    # 상자를 설정으로 읽게 했다. 안에 선 두 화면 — 공용 설정을 고치는 `Admin Area` 와
    # 질문·요청·오류 신고를 받는 VOC — 은 모두 앱을 쓰는 사람을 돕는 자리다. 아이콘은
    # 사이드바에서 아무도 쓰지 않는 `support` 다. 상수 `ADMIN_BOX_KEY` 는 그대로다 — 값을
    # 바꾸면 세션이 기억하던 펼침 상태만 새 칸으로 갈린다.
    # 이 상자 안의 화면(Admin Area·VOC)으로 **들어온 회차에만** 상자를 편다. 접혀 있으면
    # 「지금 여기」 표시가 상자 안에 가려져 사이드바 어디에도 지금 자리가 보이지 않는다.
    # 떠날 때 억지로 접지 않는다 — 조회 컨트롤 상자는 사용자가 여닫은 대로 기억한다
    # (`sidebar_expander`). 위젯을 만들기 **전**에 써야 한다. 만든 뒤에 쓰면 Streamlit 이
    # 예외를 낸다.
    support_paths = {pages.admin_area.url_path, *(page.url_path for page in pages.admin_box_pages)}
    if page_changed and navigation.url_path in support_paths:
        st.session_state[ADMIN_BOX_KEY] = True
    with sidebar_expander("Support", key=ADMIN_BOX_KEY, icon=":material/support:"):
        with st.container(key="admin_area_navigation"):
            st.page_link(pages.admin_area, width="stretch")
            # VOC 는 계산 화면이 아니라 사람이 쓰는 자리다. 계산 그룹 어디에도 속하지 않아
            # 이 상자에 함께 세운다 — 「말할 곳」을 찾는 사람은 맨 아래를 본다. **하위가
            # 아니라 같은 층위**다. 관리 화면과 게시판은 서로를 포함하지 않으므로 들여쓰기도
            # 계층선도 두지 않는다.
            for page in pages.admin_box_pages:
                st.page_link(page, width="stretch")

    # 앱 이름·버전·빌드와 개발 팀·문의처 두 줄. **페이지보다 먼저** 그린다 — 페이지가 `st.stop()`
    # 하면 그 뒤로는 아무것도 브라우저에 닿지 않는다. 사이드바 맨 아래 자리와 바닥 고정(목록이 길면
    # 그 밑으로 지나간다)은 CSS 가 이 카드의 key 로 지킨다.
    render_app_credits()

    # 여기서부터는 다른 화면으로 가는 목록이 아니라 **지금 화면의 계산 조건**이다. 그 경계에 구역
    # 제목 한 줄을 세우고, 바로 아래에 **늘 펼친 통합 패널 하나**를 세운다(2026-10-10 사용자 결정).
    #
    # **지금 화면이 읽는 공통 조건만 세운다**(2026-09-29 사용자 결정). 무엇을 읽는지는
    # `navigation.PageSpec` 의 선언이 말한다. 세우지 않은 줄의 값은 사라지지 않는다 — 시나리오는
    # 세션의 활성 리비전, 조회기간은 위젯이 아닌 `MONTH_RANGE_KEY` 라 그 조건을 읽는 화면으로
    # 돌아오면 그대로 선다.
    reads_common_here = current_spec is None or current_spec.reads_common_conditions_on(active_tab)
    shows_scenario = reads_common_here and (current_spec is None or current_spec.reads_scenario)
    shows_period = reads_common_here and (current_spec is None or current_spec.reads_period)
    # 설비 시나리오 줄은 공통 조건과 따로 선언한다(`PageSpec.equipment_scenario`·
    # `equipment_scenario_tabs`).
    # **여기서는 칸만 세운다** — 줄은 페이지가 `resolve_equipment_session` 뒤에 그린다. `app.py` 는
    # 설비 DB 를 열지 않는다(사이드바가 그리는 동안 저장소 호출 0).
    shows_equipment = current_spec is not None and current_spec.reads_equipment_scenario_on(
        active_tab
    )
    has_cards = current_spec is not None and current_spec.has_cards_on(active_tab)
    # 제목은 **늘 페이지보다 먼저, 같은 자리에** 세운다 — 회차마다 지웠다 다시 세우면 rerun 동안
    # 제목이 사라지고 아래 상자가 한 줄 올라갔다 내려온다. 카드만 세우는 화면이 카드 전에 멈추는
    # 드문 오류 경로(VOC·설비 DB 를 못 읽음)에서 제목만 남는 것은 사이드바 CSS 가 감춘다 — 제목
    # 아래에 설 상자가 사이드바에 하나도 없으면 제목을 숨긴다(`sidebar_style`, 홀로 남은 제목).
    if shows_scenario or shows_period or shows_equipment or has_cards:
        render_sidebar_section(CONDITIONS_SECTION)
    if shows_scenario or shows_period or shows_equipment:
        # **패널은 늘 같은 순번에 선다.** 안의 줄은 한 모양(이름 줄 + 팝업을 여는 값 칸,
        # `components/condition_field.py`)이고 값은 세션만 읽는다 — 저장소는 팝업을 연 동안에만
        # 읽는다. 패널 안 차례: 적용 전 편집 한 줄 → 시나리오 → 조회기간 → 설비 시나리오 칸 →
        # 페이지 칸.
        with st.sidebar.container(border=True, key=CONDITIONS_BOX_KEY):
            # 적용 전 편집 경고는 시나리오·기간 두 줄이 함께 쓰는 한 줄이다(전에는 두 상자에 각각
            # 적었다). 늘 서 있는 한 칸 안에 그려 생기고 사라질 때 아래 줄의 자리를 밀지 않는다.
            with st.container():
                if pending_edits:
                    st.caption(pending_edits_notice(pending_edits))
            if shows_scenario:
                render_scenario_field()
            if shows_period:
                render_period_field()
            # 설비 시나리오 칸 — 페이지 칸과 같은 블록이다(빈 칸은 그려지지 않는다). 페이지가
            # 그 회차 목록을 읽은 뒤 줄을 그리므로 배지가 한 회차 늦지 않는다.
            register_equipment_scenario_slot(st.container(gap=None) if shows_equipment else None)
            # 페이지가 계산 뒤에 채우는 칸(HOME 의 공정 필터·주요공정 히트맵). 적용 기간처럼 그
            # 값은 `navigation.run()` 안에서야 정해지고, 페이지가 `st.stop()` 하면 그 뒤 코드는
            # 돌지 않는다 — 칸을 여기서 미리 세워 둔다. **칸은 `st.empty` 가 아니라 블록이다**
            # (2026-10-11 병합 전 리뷰). 빈 요소는 회차가 시작되자마자 앞 회차의 줄을 지워, HOME
            # 계산이 끝날 때까지(약 1초) 공정 필터·히트맵 줄이 사라지고 패널 아래 카드가 위로
            # 튀었다. 블록은 프런트엔드가 같은 자리의 앞 회차 줄을 페이지가 다시 보낼 때까지 남긴다.
            # 쓰지 않은 칸은 그려지지 않아 높이·간격이 없다 — 1.63 `st.container()` 는
            # `allow_empty=False` 라 빈 블록을 프런트엔드가 그리지 않는다(CSS 규칙이 아니다). 칸에
            # `border`·`height` 를 주면 `allow_empty` 가 켜져 빈 칸이 그려지므로 주지 않는다.
            register_page_condition_slots(
                [st.container(gap=None) for _ in range(PAGE_CONDITION_SLOT_COUNT)]
            )
    else:
        forget_page_condition_slots()
        register_equipment_scenario_slot(None)
    if not shows_period:
        # 안 세운 회차에는 적용 기간 자리표시자도 없다. 앞 회차에 등록한 칸을 지워야 이 화면이
        # 사라진 칸에 「✓ 적용」을 쓰지 않는다.
        forget_month_range_placeholder()
    # 열려 있는 팝업의 호스트 프래그먼트. 두 줄이 다 서지 않는 화면에서도 **매 전체 실행
    # 빠짐없이**, 페이지(`st.stop()` 이 걸릴 수 있는 곳)보다 앞에서 부른다 — 이번 실행에 등록되지
    # 않은 프래그먼트는 여는 콜백(`st.rerun(<key>)`)도 팝업 닫기도 겨눌 수 없다. 팝업과 그
    # 자리표시자는 본문 밖(이벤트 칸)에 서고 이 칸은 늘 비어 있어 CSS 가 숨긴다(상자 여닫기 칸과
    # 같다).
    with st.container(key=CONDITION_DIALOG_SINK_KEY):
        render_condition_dialogs(page_file, shows_scenario, shows_period, shows_equipment)
    # 머리 띠 아래 화면 탭 줄(`components/page_tabs.py`). **이 앞의 본문 칸은 모두 늘 서는
    # 칸이다** — 순번이 회차마다 같아야 컴포넌트가 다시 마운트되지 않는다. 생겼다 사라지는 것
    # (스키마 경고)은 뒤에 둔다.
    render_page_tabs(current_spec, pages=pages, marks=unsaved_marks, leave=leave_notice(page_file))

    # 설비 DB 를 rerun 한 번에 여러 번 여는 화면(`PageSpec.uses_equipment_db`)에서만 그 회차
    # 동안 설비 DB 에도 핀을 건다. 위 시나리오 DB 핀과 수명·게으름이 같다 — 첫 연결 때 잡히고,
    # 페이지가 끝나거나 `st.stop()`·`st.rerun()` 으로 빠져나가면 풀린다. 다른 화면에는 걸지 않는다.
    equipment_pin: AbstractContextManager[None] = (
        pinned_connections(EQUIPMENT_DUCKDB_PATH)
        if current_spec is not None and current_spec.uses_equipment_db
        else nullcontext()
    )
    # 시뮬레이션 DB 가 이 코드보다 새 버전이면(예전 배포로 되돌린 상태) 모든 화면 본문 맨 위에
    # 경고 한 줄을 세운다. 막지는 않는다. 값은 위 부트스트랩이 만든 캐시 저장소의 속성이라
    # rerun 마다 DB 를 열지 않는다. 설비 DB 는 그 DB 를 여는 화면이 각자 세운다 — 여기서 열면
    # 설비 DB 를 안 보는 화면(HOME 등)까지 그 DB 의 마이그레이션·잠금에 묶인다.
    render_schema_ahead_warning(get_scenario_repository(str(DUCKDB_PATH.resolve())).schema_ahead)
    # 끝까지 돈 실행 뒤에만 상자 여닫기가 본문을 건너뛴다. 페이지가 `st.stop()` 으로 멈춘 것도
    # 끝까지 돈 것이다 — 그 화면은 멈춘 자리까지가 전부다. 새 상호작용이 끊은 실행은 같은 멈춤
    # 예외로 끝나도 끝까지 돈 것이 아니다(`AppRun.finish_stopped`).
    # 입장 화면 Summary 의 GAP 몫이 「준비 중」으로 나갔으면 페이지를 다 그린 **뒤**에 만들어 둔다 —
    # 비교 대상을 바꾼 회차에 HOME 보다 먼저 비교 계획을 환산하지 않게(다음 회차에 싣는다). 페이지가
    # `st.stop()` 해도 한다. rerun 으로 끊긴 회차에서는 하지 않는다.
    try:
        with equipment_pin:
            navigation.run()
    except StopException as stop:
        app_run.finish_stopped(stop)
        warm_intro_summary(str(DUCKDB_PATH.resolve()))
        raise
    app_run.finish()
    warm_intro_summary(str(DUCKDB_PATH.resolve()))
