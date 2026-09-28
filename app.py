# Purpose: Streamlit 앱의 공식 시나리오 활성화, 공통 사이드바·조회기간과 페이지 탐색을 구성한다.

import streamlit as st

from capa_simulation.components.app_header import render_app_header
from capa_simulation.components.month_range_picker import render_month_range_picker
from capa_simulation.components.page_guide import guide_toolbar_script, render_guide_base_style
from capa_simulation.components.scenario_status import (
    SCENARIO_BOX_KEY,
    render_scenario_controls,
)
from capa_simulation.components.sidebar_style import build_sidebar_stylesheet
from capa_simulation.components.tab_state import remembered_tab_key
from capa_simulation.components.theme_toggle import render_theme_toggle
from capa_simulation.design import theme
from capa_simulation.io.reference_cache import get_effective_reference_tables
from capa_simulation.navigation import CONDITIONS_SECTION, PageSpec, build_navigation_pages
from capa_simulation.page_bootstrap import bootstrap_error_message, forget_page_dialogs
from capa_simulation.persistence._sql_helpers import pinned_connections
from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import (
    MONTH_PICKER_KEY,
    MONTH_RANGE_KEY,
    apply_pending_scenario_preset,
)
from capa_simulation.services.scenario_month_bounds import scenario_month_bounds
from capa_simulation.settings import (
    APP_ABOUT,
    APP_BUG_REPORT_URL,
    APP_HELP_URL,
    APP_NAME,
    DUCKDB_PATH,
    MONTH_SELECTION_END,
    MONTH_SELECTION_START,
    format_month,
)
from capa_simulation.sidebar_status import (
    BOTTLENECK_BOX_KEY,
    forget_month_range_placeholder,
    register_month_range_placeholder,
    render_sidebar_section,
    show_selected_month_range,
    sidebar_expander,
)
from capa_simulation.sync_boot import enable_sync_state_if_managed, heartbeat_if_managed

# 사이드바 박스 key 이자 CSS 훅. 확장 패널의 펼침 상태도 이 key 로 오가고, Admin 의
# `order` 와 요약 줄 서식이 같은 이름을 읽는다.
MONTH_BOX_KEY = "sidebar_month_box"
# 조회기간 상자의 **요약 줄 위에 얹는** 적용 기간 한 줄. 상자 안이 아니라 바로 앞에 선
# 빈 칸이고, 접히든 펴지든 자리가 흔들리지 않게 CSS 가 그 칸을 요약 줄로 민다.
MONTH_APPLIED_BOX_KEY = "sidebar_month_applied_box"
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
    둘 다 없으면 첫 탭이다(`None`).
    """
    if spec.condition_tabs is None:
        return None
    key = spec.condition_tabs.key
    for value in (st.session_state.get(key), st.session_state.get(remembered_tab_key(key))):
        if isinstance(value, str):
            return value
    return None


st.set_page_config(
    page_title=APP_NAME,
    page_icon=":material/factory:",
    layout="wide",
    # 헤더에 직접 글을 넣는 공식 API 는 없다. 개발자·인증 정보는 ⋮ 메뉴의 About 에 싣는다.
    menu_items={
        "Get help": APP_HELP_URL,
        "Report a bug": APP_BUG_REPORT_URL,
        "About": APP_ABOUT,
    },
)
# 이 실행이 쓸 테마를 먼저 정한다. **토큰을 하나라도 읽기 전**이어야 한다 — 색을 읽는
# 쪽은 여기서 담아 둔 값을 본다. 바뀌었으면 그 세션의 Figure 캐시도 여기서 비운다.
theme.begin_run()

# managed 모드에서만 동기화 표시를 켠다. local 모드(개발 PC·기본값)에서는 아무 일도 하지
# 않으므로 이 호출이 있어도 동작이 바뀌지 않는다.
enable_sync_state_if_managed()
# 앱이 이 PC 에서 돌고 있다는 표시. DuckDB 는 프로세스 배타 잠금이라 앱이 떠 있는 동안
# 동기화 스크립트는 DB 를 열지 못한다 — 그 사실을 사람 말로 알릴 근거가 이 기록이다.
# 10초에 한 번만 실제로 쓴다.
heartbeat_if_managed()

# rerun 한 번 동안 시나리오 DB 인스턴스를 잡아 둔다. 사이드바가 rerun 마다 여는 연결 3개가
# 각자 인스턴스를 다시 만들지 않게 하는 것이 전부이고, rerun 이 끝나면 풀린다.
with pinned_connections(DUCKDB_PATH):
    try:
        bootstrap_latest_official_scenario(str(DUCKDB_PATH.resolve()))
    except Exception as exc:  # 어떤 실패든 원인을 읽을 수 있게 바꿔야 한다
        # DuckDB 파일은 프로세스 배타 잠금이다. 서버가 이미 떠 있는데 한 번 더 실행하면
        # 화면이 한 줄도 그려지기 전에 예외가 그대로 노출되고, Windows 로캘 탓에 원본
        # 메시지의 한글이 깨져 나온다. 사용자가 원인을 알 방법이 없어 안내로 바꾼다.
        st.error(bootstrap_error_message(exc), icon=":material/database_off:")
        with st.expander("원본 오류"):
            st.code(f"{type(exc).__name__}: {exc}")
        st.stop()
    apply_pending_scenario_preset()

    pages = build_navigation_pages()
    navigation = st.navigation(pages.ordered, position="hidden")
    # 지금 어느 페이지에 있는지는 **파이썬에서** 가른다. 활성 링크에 `aria-current` 도
    # 안정적인 클래스도 없고(emotion 해시뿐) CSS 만으로는 판정할 수 없다. `st.navigation()`
    # 이 이번 rerun 에 그릴 페이지를 그대로 돌려주므로 그 주소로 선택자를 만든다.
    #
    # `href` 가 곧 `url_path` 다. HOME 은 기본 페이지라 늘 빈 문자열이고, 그것도 이 한
    # 페이지만 가리키므로 선택자로 쓸 수 있다.
    active_href = navigation.url_path

    st.html(
        build_sidebar_stylesheet(
            pages.groups,
            active_href,
            scenario_box_key=SCENARIO_BOX_KEY,
            month_box_key=MONTH_BOX_KEY,
            month_applied_key=MONTH_APPLIED_BOX_KEY,
            bottleneck_box_key=BOTTLENECK_BOX_KEY,
            admin_box_key=ADMIN_BOX_KEY,
        )
    )
    render_app_header()
    # 헤더 오른쪽 Deploy 왼쪽 자리에 밝게/어둡게 버튼을 얹는다. Streamlit 이 테마를
    # 기억하는 자리를 그대로 쓰므로 위젯과 우리 Figure 가 함께 바뀐다. 그 왼쪽의 `Guide`
    # 버튼도 같은 iframe 에 싣는다. 기본은 감춰 두고 가이드를 단 페이지만 보이게 한다.
    render_guide_base_style()
    render_theme_toggle(extra_scripts=(guide_toolbar_script(),))
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
    if page_changed:
        # 떠난 페이지의 팝업 열림 상태를 버린다. 닫지 않고 떠나면 돌아왔을 때 팝업이 저절로 뜬다.
        forget_page_dialogs()
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
            on_change="rerun",
        ):
            st.page_link(group.main, label=GROUP_MAIN_LABEL, width="stretch")
            for page in group.subpages:
                st.page_link(page, width="stretch")

    # 여기서부터 상자들은 다른 화면으로 가는 목록이 아니라 **지금 화면의 계산 조건**이다.
    # 그 경계에 구역 제목 한 줄을 세운다. 시나리오 상자 **앞**이어야 한다 — 아래 적용 기간
    # 자리표시자와 조회기간 상자 사이에 끼면 자리표시자가 제 상자의 요약 줄에 얹히지 못한다.
    #
    # **지금 화면이 읽는 공통 조건만 세운다**(2026-09-29 사용자 결정). 무엇을 읽는지는
    # `navigation.PageSpec` 의 선언이 말한다. 세우지 않은 상자의 선택은 사라지지 않는다 —
    # 시나리오 선택 상자는 `persist_state` 로, 조회기간은 위젯이 아닌 `MONTH_RANGE_KEY` 로
    # 남아 그 조건을 읽는 화면으로 돌아오면 그대로 선다.
    current_spec = pages.spec_for(navigation.url_path)
    reads_common_here = current_spec is None or current_spec.reads_common_conditions_on(
        active_condition_tab(current_spec)
    )
    shows_scenario = reads_common_here and (current_spec is None or current_spec.reads_scenario)
    shows_period = reads_common_here and (current_spec is None or current_spec.reads_period)
    has_cards = current_spec is not None and current_spec.has_condition_cards
    if shows_scenario or shows_period or has_cards:
        render_sidebar_section(CONDITIONS_SECTION)
    if shows_scenario:
        render_scenario_controls()

    # 적용 범위는 상자를 **접어도** 보여야 하는 한 조각이다. 그런데 그 값은 페이지가
    # 계산을 끝낸 뒤(`navigation.run()` 안의 `resolve_effective_months`)에야 정해지고,
    # 페이지가 `st.stop()` 하면 `navigation.run()` 뒤의 코드는 아예 돌지 않는다 — 그
    # 뒤에 그리면 상자를 통째로 잃는다. 확장 패널의 제목은 문자열 하나라 나중에 다시
    # 쓸 수도 없다. 그래서 자리표시자 기제는 그대로 두고 **자리만** 상자 바로 앞으로
    # 옮기고, 요약 줄 위로 얹는 일은 CSS 가 한다. 접히든 펴지든 이 칸은 늘 같은 자리다.
    if shows_period:
        with st.sidebar.container(key=MONTH_APPLIED_BOX_KEY):
            register_month_range_placeholder(st.empty())
        # 다른 화면과 같은 낱말을 쓴다. 여기만 "조회 기간" 으로 띄어져 있었다.
        with sidebar_expander("조회기간", key=MONTH_BOX_KEY, icon=":material/date_range:"):
            default_month_range = (
                format_month(MONTH_SELECTION_START),
                format_month(MONTH_SELECTION_END),
            )
            current_month_range = st.session_state.get(MONTH_RANGE_KEY, default_month_range)
            if not isinstance(current_month_range, (list, tuple)) or len(current_month_range) != 2:
                current_month_range = default_month_range
            try:
                month_source_tables = get_effective_reference_tables()
            except RuntimeError:
                # 공식·활성 리비전이 없는 저장소에서도 관리 화면과 기본 조회기간은 연다.
                month_source_tables = {}
            minimum_month, maximum_month = scenario_month_bounds(
                month_source_tables, MONTH_SELECTION_START, MONTH_SELECTION_END
            )
            # 현재 선택만 보면 기간을 좁힌 다음 바깥 월을 다시 고를 수 없다. 활성 표의 실제
            # 월을 기준으로 넓혀 Shift 등으로 2031년 이후를 저장해도 계속 조회할 수 있게 한다.
            selected_start_label, selected_end_label = render_month_range_picker(
                start=str(current_month_range[0]),
                end=str(current_month_range[1]),
                min_month=format_month(minimum_month),
                max_month=format_month(maximum_month),
                key=MONTH_PICKER_KEY,
            )
            st.session_state[MONTH_RANGE_KEY] = (
                selected_start_label,
                selected_end_label,
            )
            # 여기서는 **고른 범위**만 중립으로 적는다. 조회기간을 실제로 읽는 화면이 그 뒤에
            # 「✓ 적용」으로 덮는다(`resolve_effective_months`·HOME). 조회기간과 무관한 화면에서는
            # 이 문구가 그대로 남는다.
            show_selected_month_range(
                int(selected_start_label.replace("-", "")),
                int(selected_end_label.replace("-", "")),
            )
    else:
        # 안 세운 회차에는 적용 기간 자리표시자도 없다. 앞 회차에 등록한 칸을 지워야 이 화면이
        # 사라진 칸에 「✓ 적용」을 쓰지 않는다.
        forget_month_range_placeholder()

    # 관리 기능이라 조회 컨트롤보다 아래, 사이드바에서 가장 먼 곳에 둔다. 페이지가 자기
    # 사이드바 요소를 더하는 것은 `navigation.run()` 안이라 파이썬 차례로는 뒤에 둘 수
    # 없다 — 맨 아래를 지키는 것은 위 CSS 의 `order` 다.
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

    navigation.run()
