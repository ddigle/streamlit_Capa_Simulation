# Purpose: HOME 의 LOB 표시 조건 카드·제목 줄과 Preference 탭 편집기를 그려 공용 프로필에 저장한다.

"""HOME 사이드바 `LOB 표시 조건` 카드, `Capa LOB 현황` 제목 줄, `Preference` 탭.

**화면을 보는 조건(선행 B/O·선행 입고·확보율 보정·GAP·상세·EDP·Past Data·제품별 비중 단위)은
사이드바 조건 카드**다(2026-09-29 사용자 결정 — 전에는 제목 줄과 Preference 의 `표시 기준` 상자에
흩어져 있었다). 탭에는 비교 시나리오·주요 Case(`home_main_cases`)·확보율 판정 기준·선행 B/O·선행
입고 실적·`Summary 공지`·Top5 대역·주요공정·확보율 보정 편집기가 있고, 저장은 모두 공용 프로필
교체다. 저장 버튼은 편집 칸 **위**다. 설명은 Guide(`guides/home.md`)다.

토글 **값은 계산보다 먼저** 필요하고 **위젯은 계산 뒤에** 그려진다. 그래서 `app_pages/home.py`
는 위젯이 쓰는 세션 키를 직접 읽고, 여기서는 같은 키로 위젯을 만든다. 키와 기본값은 UI
의존성이 없는 `home_state` 에서 가져온다.
"""

from __future__ import annotations

import html
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.components.condition_field import condition_field
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.home_main_cases import render_main_case_picker
from capa_simulation.components.literal_markdown import (
    literal_markdown,
    markdown_safe_tildes,
    quoted,
)
from capa_simulation.components.monthly_table_base import text_width_units
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.profile_caption import (
    HasProfileVersion as VersionedProfile,
)
from capa_simulation.components.profile_caption import profile_version_caption
from capa_simulation.components.revision_label import revision_label
from capa_simulation.components.tab_state import OpenTab
from capa_simulation.components.write_guard import is_own_profile_save, profile_save_marks
from capa_simulation.design import tokens
from capa_simulation.home_state import (
    ADVANCE_SHIPMENT_TOGGLE_KEY as ADVANCE_SHIPMENT_TOGGLE_KEY,
)
from capa_simulation.home_state import (
    ADVANCE_TOGGLE_KEY as ADVANCE_TOGGLE_KEY,
)
from capa_simulation.home_state import (
    COMPARISON_TOGGLE_KEY as COMPARISON_TOGGLE_KEY,
)
from capa_simulation.home_state import (
    EDP_TOGGLE_KEY as EDP_TOGGLE_KEY,
)
from capa_simulation.home_state import (
    EXECUTION_TOGGLE_KEY as EXECUTION_TOGGLE_KEY,
)
from capa_simulation.home_state import (
    HOME_TOGGLE_DEFAULTS,
    PRODUCT_SHARE_BASIS_DEFAULT,
)
from capa_simulation.home_state import (
    PAST_DATA_TOGGLE_KEY as PAST_DATA_TOGGLE_KEY,
)
from capa_simulation.home_state import (
    PLAN_DETAIL_CUSTOMER_KEY as PLAN_DETAIL_CUSTOMER_KEY,
)
from capa_simulation.home_state import (
    PRODUCT_SHARE_BASIS_KEY as PRODUCT_SHARE_BASIS_KEY,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    forget_page_dialogs,
    prune_choice,
)
from capa_simulation.persistence._sql_helpers import ProfileVersionConflict, pinned_connections
from capa_simulation.persistence.cache import (
    clear_global_advance_load_cache,
    clear_global_advance_shipment_cache,
    clear_global_comparison_scenario_cache,
    clear_global_execution_capacity_cache,
    clear_global_key_process_cache,
    clear_global_securement_threshold_cache,
    clear_global_summary_note_cache,
    clear_global_top5_band_cache,
    get_scenario_repository,
    load_global_comparison_scenario,
    load_global_key_process,
)
from capa_simulation.persistence.models import (
    GlobalAdvanceLoad,
    GlobalAdvanceShipment,
    GlobalExecutionCapacity,
    GlobalKeyProcess,
    GlobalSecurementThreshold,
    GlobalSummaryNote,
    GlobalTop5Band,
    RevisionSummary,
    ScenarioSummary,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import active_persisted_revision_id
from capa_simulation.services.advance_load import (
    ADVANCE_LOAD_ROW_LABEL,
    ADVANCE_LOAD_VALUE_COLUMN,
    merge_advance_load_edits,
)
from capa_simulation.services.advance_shipment import (
    ADVANCE_SHIPMENT_ROW_LABEL,
    advance_shipment_by_month,
    merge_advance_shipment_edits,
)
from capa_simulation.services.execution_capacity import (
    EXECUTION_CAPACITY_COLUMNS,
    empty_execution_capacity,
    prepare_execution_capacity,
)
from capa_simulation.services.key_process import (
    KEY_PROCESS_LIMIT,
    PRESET_NAME_LIMIT,
    normalize_preset_name,
    resolve_preset_name,
)
from capa_simulation.services.korean_particle import object_particle
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.monthly_amount import amounts_by_month
from capa_simulation.services.product_share import PRODUCT_SHARE_BASES
from capa_simulation.services.securement_threshold import (
    SECURE_COLUMN,
    WARNING_COLUMN,
    build_securement_thresholds,
    merge_securement_threshold_edits,
    reversed_threshold_months,
)
from capa_simulation.sidebar_status import condition_card, keeps_app_run_open

EXECUTION_EDITOR_KEY = "home_preference_execution_editor"
EXECUTION_NOTE_KEY = "home_preference_execution_note"
# 확보율 보정 편집을 시작한 회차가 본 공용 version. 저장 회차에 저장소가 대조한다(판정 기준과 같다).
EXECUTION_BASE_VERSION_KEY = "home_preference_execution_base_version"
# 이 세션이 한 확보율 보정 저장의 표지 이름(`write_guard.profile_save_marks`)과 성공 알림.
EXECUTION_SAVE_NAME = "home_preference_execution"
EXECUTION_SAVED_MESSAGE = "확보율 보정을 저장했습니다."
COMPARISON_SCENARIO_KEY = "home_preference_comparison_scenario"
COMPARISON_REVISION_KEY = "home_preference_comparison_revision"
ADVANCE_EDITOR_KEY = "home_preference_advance_editor"
ADVANCE_NOTE_KEY = "home_preference_advance_note"
ADVANCE_SHIPMENT_EDITOR_KEY = "home_preference_advance_shipment_editor"
ADVANCE_SHIPMENT_NOTE_KEY = "home_preference_advance_shipment_note"
ADVANCE_SHIPMENT_FLASH_KEY = "home_advance_shipment_flash"
THRESHOLD_EDITOR_KEY = "home_preference_threshold_editor"
THRESHOLD_NOTE_KEY = "home_preference_threshold_note"
THRESHOLD_CLEAR_OUTSIDE_KEY = "home_preference_threshold_clear_outside"
# 판정 기준 편집을 시작할 때 본 공용 version. 저장 회차에는 이 회차가 새로 읽은 version 이 아니라
# **앞 회차(사용자가 보고 고친 화면)** 의 version 을 대조해야 다른 세션의 먼저 저장을 잡는다.
THRESHOLD_BASE_VERSION_KEY = "home_preference_threshold_base_version"
THRESHOLD_FLASH_KEY = "home_threshold_flash"
# 이 세션이 한 판정 기준 저장의 표지 이름(`write_guard.profile_save_marks`)과 성공 알림.
THRESHOLD_SAVE_NAME = "home_preference_threshold"
THRESHOLD_SAVED_MESSAGE = "확보율 판정 기준을 공용 설정으로 저장했습니다."
# 판정 기준 입력이 빠진 자리(HOME 공정 필터 팝업 머리·Static Capa)에 남기는 한 줄. 두 화면이 같은
# 글자를 쓴다.
THRESHOLD_POINTER = "판정 기준은 HOME → Preference 에서 정합니다."
# Summary 공지·Top5 구간·주요공정 프리셋 편집을 시작한 회차가 본 공용 version 과 제 저장 표지
# 이름(`write_guard.profile_save_marks`). 판정 기준과 같은 버전 대조다 — 칸에 key 가 없어 남이 먼저
# 저장하면 제출 회차의 칸이 새 저장본으로 서서 이 화면의 입력이 버려지는데, 대조가 없으면 그 값을
# version 만 올려 다시 쓰고 「저장했습니다」 를 띄웠다(2026-10-26 E2E).
SUMMARY_BASE_VERSION_KEY = "home_preference_summary_base_version"
SUMMARY_SAVE_NAME = "home_preference_summary"
TOP5_BASE_VERSION_KEY = "home_preference_top5_base_version"
TOP5_SAVE_NAME = "home_preference_top5"
TOP5_SAVED_MESSAGE = "B/N Top5 확보율 구간을 저장했습니다."
# 주요공정 프리셋은 version 하나가 아니라 직전 회차가 그린 **고칠 프리셋**(version·이름·공정)을
# 둔다 — 다른 프리셋을 남이 고친 것은 이 화면의 쓰기가 다시 읽은 묶음 위에 남기므로 막지 않는다.
KEY_PROCESS_SEEN_KEY = "home_preference_key_process_seen"
KEY_PROCESS_SAVE_NAME = "home_preference_key_process"
KEY_PROCESS_FLASH_KEY = "home_key_process_flash"
# 빠른 두 번 누름의 둘째 회차가 다시 알리는 문구. 그 회차는 프리셋 고름이 첫 저장 뒤로 옮겨 가
# 어느 프리셋을 어떻게 바꿨는지 다시 지을 수 없어 이름 없이 말한다.
KEY_PROCESS_SAVED_MESSAGE = "주요공정 히트맵 프리셋을 저장했습니다."
# 주요공정 히트맵 프리셋. 사이드바에서 고른 프리셋(세션의 보는 조건)과 Preference 에서 고치는
# 프리셋은 다른 칸이다 — 고치려고 고른 것이 보는 화면을 바꾸면 안 된다. **위젯이 아닌 세션 값**이다
# (2026-10-10 — 사이드바 칸의 팝업이 적는다). 그래서 Preference 에서 이름을 바꿀 때도 곧바로 적는다.
KEY_PROCESS_PRESET_KEY = "home_key_process_preset"
# 팝업 안 라디오의 초안. 칸을 누를 때 지금 보는 프리셋으로 적는다.
KEY_PROCESS_PICK_KEY = "home_key_process_preset_pick"
KEY_PROCESS_FIELD_KEY = "home_key_process_field"
KEY_PROCESS_FIELD_LABEL = "주요공정 히트맵"
# `grid_view` 는 사이드바 `Space 현황` 링크 아이콘과 겹쳐 데이터 묶음을 뜻하는 `dataset` 이다.
KEY_PROCESS_ICON = ":material/dataset:"
KEY_PROCESS_EDIT_TARGET_KEY = "home_key_process_preset_edit"
NEW_KEY_PROCESS_PRESET = "＋ 새 프리셋"
DIMENSION_COLUMN = "구분"
# 구획 제목의 글자 크기와 앞 강조 막대의 치수. `home_rendering` 의 `Summary` 상자가 같은
# 값을 CSS 가상요소로 다시 그리므로 상수로 내보낸다 — 두 곳에 숫자를 따로 적으면 한쪽만
# 고쳐져 막대 크기가 어긋난다.
SECTION_TITLE_FONT_PX = 20
SECTION_BAR_WIDTH_PX = 4
SECTION_BAR_HEIGHT_PX = 18
SECTION_BAR_RADIUS_PX = 2
SECTION_BAR_GAP_PX = 8
STATUS_LEGEND_ROW_KEY = "home_status_legend"
# 범례 안쪽 div 의 클래스. 높이를 물려주는 CSS 가 이 이름을 읽는다.
STATUS_LEGEND_CLASS = "capa-status-legend"


# 마크다운·Streamlit 지시어·HTML 로 읽히는 글자 → 숫자 엔티티. 구획 제목에 사용자 이름이 들어간다.
_MARKDOWN_SAFE = str.maketrans(
    {char: f"&#{ord(char)};" for char in r"\`*_{}[]()#+-.!|~$:<>&'" + '"'}
)


def render_section_title_row(text: str, *, key: str) -> None:
    """구획 제목 줄. `Capa LOB 현황` 줄과 같은 높이·같은 모양이다.

    네 구획의 제목이 같은 컴포넌트로 그려져야 제목과 표 사이 간격이 하나로 맞는다.
    하나만 Plotly 주석으로 남겨 두면 그 구획만 간격이 다르다.
    """
    with st.container(key=key, horizontal=True, vertical_alignment="center", gap="medium"):
        # 줄 폭을 채워야 넘친 제목이 줄 안에서 말줄임된다(내용 폭이면 칸 밖으로 삐져나간다).
        st.markdown(section_title_markup(text), unsafe_allow_html=True, width="stretch")


def section_title_markup(text: str) -> str:
    """구획 제목 한 줄. Plotly 주석이 그리던 모양을 그대로 옮긴 것이다.

    앞의 강조 막대는 **글자가 아니라 그린 사각형**이다. `▍` 문자로 두면 막대 높이가 그
    글자가 상속한 글자 크기를 따라가는데, 제목 글자만 20px 로 키운 이 줄에서는 막대가
    본문 크기(작게)로 남고 `Summary` 상자처럼 제목 전체가 20px 인 곳에서는 크게 나온다.
    같은 막대가 화면마다 다른 크기로 보이던 이유가 그것이다. px 로 못 박으면 어디에 놓든
    같다.

    실제 `<h2>` 가 아니라 **역할만** 붙인다. Streamlit 제목은 `padding: 7.5px 0 15px` 와
    감싸개 `margin-bottom: -15px` 짝을 함께 끌고 와(`app.py` 의 제목 CSS) 이미 맞춰 둔 제목
    줄 높이가 다시 어긋난다. 레벨이 2 인 것은 페이지 제목이 h1 이고 상세 B/N 구획 안에 h4 가
    이미 있기 때문이다.

    **한 줄을 넘지 않는다.** 제목 줄은 높이를 못박은 줄이고 월 칸의 짝 빈 줄도 같은 높이다.
    프리셋 이름처럼 사용자가 정한 긴 글이 구분 칸(260px)에서 줄을 바꾸면 이 줄만 높아져 아래
    표의 행이 월 칸과 어긋났다(2026-10-01 사용자 보고). 넘치면 말줄임하고 전체 글은 풍선
    (`title`)으로 보인다. 글은 사용자가 정한 이름일 수 있어 이스케이프한다.
    """
    safe = html.escape(text)
    # 보이는 글은 `st.markdown` 을 거친다. HTML 이스케이프만 하면 `~`(취소선)·`*`(기울임)·`$`(수식)·
    # `:`(아이콘 지시어) 같은 마크다운 글자가 해석돼 프리셋 이름 글자가 사라진다 — 숫자 엔티티로.
    visible = text.translate(_MARKDOWN_SAFE)
    return (
        f'<span role="heading" aria-level="2" title="{safe}" '
        f'style="display:inline-flex;align-items:center;max-width:100%;min-width:0;'
        f"gap:{SECTION_BAR_GAP_PX}px;"
        f'font-size:{SECTION_TITLE_FONT_PX}px;font-weight:700;line-height:1.2">'
        f'<span aria-hidden="true" style="{section_accent_bar_css()}"></span>'
        f'<span style="min-width:0;overflow:hidden;white-space:nowrap;'
        f'text-overflow:ellipsis">{visible}</span></span>'
    )


def section_accent_bar_css() -> str:
    """강조 막대의 모양 선언. `st.markdown` 과 CSS 가상요소가 같은 값을 읽는다."""
    return (
        f"display:inline-block;flex:none;"
        f"width:{SECTION_BAR_WIDTH_PX}px;height:{SECTION_BAR_HEIGHT_PX}px;"
        f"border-radius:{SECTION_BAR_RADIUS_PX}px;background:{tokens.ACCENT}"
    )


def status_legend_markup() -> str:
    """확보·경고·부족 세 색이 무슨 뜻인지 한 줄로 적는다.

    이 앱은 확보율을 세 색으로 판정해 놓고 **그 색이 무슨 뜻인지 화면 어디에도 적지
    않았다.** 처음 보는 사람은 회색 막대가 좋은 것인지 나쁜 것인지 알 길이 없다.
    색만으로 뜻을 나르지 않으려면 이름이 같이 있어야 한다.

    **경계 숫자는 적지 않는다**(2026-10-06 사용자 결정). 판정 기준은 달마다 다를 수 있어
    (HOME → Preference 의 월별 기준) 숫자 한 짝으로 적으면 예외 달에서 거짓이 된다. 과거 구간
    칩도 두지 않는다 — 범례는 판정 세 색만 말한다.
    """
    chips: tuple[tuple[str, str], ...] = (
        (tokens.STATUS_SECURE, "확보"),
        (tokens.STATUS_WARNING, "경고"),
        (tokens.STATUS_SHORTAGE, "부족"),
    )
    swatches = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:14px">'
        # 테두리는 `LINE` 이다. 확보 색(`STATUS_SECURE`)은 밝은 테마에서 바탕과 대비가 낮아
        # 테두리 없이는 칩이 흐려진다 — 확보 막대가 트랙 위에서 같은 이유로 쓰는 선이다
        # (`tokens.BAR_OUTLINE_WIDTH_PX` 주석).
        f'<span style="width:11px;height:11px;border-radius:3px;background:{color};'
        f'border:1px solid {tokens.LINE};display:inline-block"></span>'
        f'<span style="font-size:12px;color:{tokens.TEXT_MUTED}">{label}</span>'
        f"</span>"
        for color, label in chips
    )
    # 높이를 **여기서 정하지 않는다.** 칩은 11px 사각형이고 토글은 위젯이라 줄상자 높이가
    # 서로 다른데, 이 div 가 자기 높이를 가지면 Streamlit 이 잡은 칸 위쪽에 붙어 토글보다
    # 아래로 처진다. 칸 높이를 그대로 물려받아 그 안에서 가운데로 모으는 일은
    # `home_rendering.dashboard_title_row_style()` 의 CSS 가 한다.
    return f'<div class="{STATUS_LEGEND_CLASS}">{swatches}</div>'


def render_home_view_card(*, comparison_ready: bool) -> None:
    """사이드바 조건 카드 `LOB 표시 조건`. Main 탭이 열렸을 때만 선다(2026-09-29 사용자 결정).

    예외는 계산이 멈춘 회차 하나다 — 탭이 없어도 `home.py` 의 `except` 가 그려, 오류문이 시키는
    `EDP 포함` 켜기·`GAP` 끄기를 그 자리에서 하게 한다(2026-10-22 사용자 결정).

    토글은 값을 바꾸기만 하고 아무것도 계산하지 않는다. 다음 실행에서 `home.py` 가 이 키를
    읽어 계산에 반영한다. 안 그려진 회차(다른 탭)에도 값은 `persist_state` 가 지킨다. 토글은
    조건 패널 팝업에 넣지 않고 패널 밑 카드로 둔다 — 바로 보이고 한 번에 눌려야 쓸모가 있다.

    **토글의 기본값은 위젯 `value=` 가 아니라 세션에 심는다.** 시나리오를 바꾸면
    `scenario_activation` 이 토글 칸에 기본값을 **적어** 브라우저에 밀어 넣는데(지우기만 하면
    브라우저가 옛 값을 들고 있다가 되보낸다), `value=` 로 켬(`Past Data 포함`)을 준 위젯에 세션
    값까지 적으면 Streamlit 이 둘을 함께 썼다고 경고한다. 칸이 없을 때만 심으므로 사용자가 바꾼
    값과 `persist_state` 가 지킨 값은 건드리지 않는다.

    비교 시나리오를 고르지 않았으면 「GAP」 을 누를 수 없다. 켤 수는 있는데 아무것도 바뀌지
    않으면 고장으로 읽힌다 — 그래서 막힌 까닭만은 툴팁으로 남긴다. 각 토글의 뜻은 Guide 다.
    """
    for key, default in HOME_TOGGLE_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default
    with condition_card("LOB 표시 조건", name="home"):
        # 「선행 B/O」 는 계획 밖 B/O 재공을 부하에 더하고(확보율이 그만큼 낮아진다), 「선행 입고」
        # 는 계획 안의 선행 입고 실적을 Density 칸에 적기만 한다(2026-10-06 사용자 결정).
        st.toggle(
            "선행 B/O",
            key=ADVANCE_TOGGLE_KEY,
            persist_state="session",
        )
        st.toggle(
            "선행 입고",
            key=ADVANCE_SHIPMENT_TOGGLE_KEY,
            persist_state="session",
        )
        # 기준정보 밖 변수(비가동·UPEH·재공)를 확보율에 %p 로 더하고 빼는 손입력 보정. 화면 이름만
        # 「확보율 보정」이고 세션 키·공용 프로필(`global_execution_capacity`)은 `execution`
        # 그대로다.
        st.toggle(
            "확보율 보정",
            key=EXECUTION_TOGGLE_KEY,
            persist_state="session",
        )
        st.toggle(
            "GAP",
            key=COMPARISON_TOGGLE_KEY,
            persist_state="session",
            disabled=not comparison_ready,
            help=None if comparison_ready else "Preference 탭에서 비교 시나리오를 먼저 고르세요.",
        )
        st.toggle(
            "상세 계획",
            key=PLAN_DETAIL_CUSTOMER_KEY,
            persist_state="session",
        )
        # 기본은 **끔**이다. LOB 로 읽는 수치는 EDP 를 뺀 값이 기준이다.
        st.toggle(
            "EDP 포함",
            key=EDP_TOGGLE_KEY,
            persist_state="session",
        )
        # 기본은 **켬**이다. 과거 이력까지 이어 보는 것이 이 화면의 기본 쓰임이다.
        st.toggle(
            "Past Data 포함",
            key=PAST_DATA_TOGGLE_KEY,
            persist_state="session",
        )
        # `Capa LOB 현황` 맨 아래 `제품별 비중` 행의 분모. Wafer 는 같은 표의 `Wafer 계획`,
        # PKG 는 그 달 PKG 생산수량 전체다. 비워 둘 수 없는 선택이라 `required` 다 — 선택된
        # 칸을 다시 눌러 비우면 한 회차 동안 값이 없어 행이 깜박인다.
        st.segmented_control(
            "제품별 비중 단위",
            options=PRODUCT_SHARE_BASES,
            default=PRODUCT_SHARE_BASIS_DEFAULT,
            required=True,
            key=PRODUCT_SHARE_BASIS_KEY,
            persist_state="session",
            width="stretch",
        )


def render_lob_title_row(
    *,
    unapplied_months: Sequence[int],
) -> None:
    """`Capa LOB 현황` 제목과 오른쪽 끝의 판정 색 범례.

    **범례가 이 줄 안에 있는 이유.** 제목 줄과 Figure 사이 간격은 스크롤바 높이를 뺀
    나머지(`DASHBOARD_PANEL_TITLE_GAP_PX`)뿐이라 거의 0 이다. 범례를 두 줄 사이에 독립
    블록으로 끼우면 바로 아래 월 영역 위에 얹힌 가로 스크롤바와 겹친다. 제목 줄은 이미
    높이가 못박힌 가로 컨테이너라 여기에 넣으면 세로 자리를 새로 먹지 않는다.
    """
    with st.container(
        key="lob_title_row",
        horizontal=True,
        vertical_alignment="center",
        gap="medium",
    ):
        st.markdown(section_title_markup("Capa LOB 현황"), unsafe_allow_html=True)
        # 판정 색의 뜻. 경계 숫자는 Top5 막대에 그은 기준선이 말한다.
        # 아래 CSS 의 `margin-left:auto` 가 이 칸만 오른쪽 끝으로 민다.
        with st.container(key=STATUS_LEGEND_ROW_KEY):
            st.markdown(status_legend_markup(), unsafe_allow_html=True)
    if unapplied_months:
        labels = _month_labels(unapplied_months)
        st.warning(
            f"선행 B/O 반영 계획이 0 이하가 되어 적용하지 못한 달이 있습니다: {labels}. "
            "해당 달은 기존 계획 그대로 그립니다.",
            icon=":material/report:",
        )


def render_home_preference(
    *,
    months: Sequence[int],
    month_labels: Sequence[str],
    threshold_profile: GlobalSecurementThreshold,
    advance_profile: GlobalAdvanceLoad,
    advance_shipment_profile: GlobalAdvanceShipment,
    execution_profile: GlobalExecutionCapacity,
    top5_band_profile: GlobalTop5Band,
    summary_profile: GlobalSummaryNote,
    process_options: Sequence[str],
    process_labels: ProcessLabels,
    unmatched_execution: pd.DataFrame,
    clamped_execution: pd.DataFrame,
    database_path: str,
    owner_tab: OpenTab | None = None,
) -> None:
    """비교 시나리오·주요 Case 선택과 판정 기준·선행 B/O·선행 입고 실적·Summary 공지·Top5 대역·
    주요공정·실행 Capa 입력 시트.

    보는 조건(EDP·Past Data 포함 등)은 사이드바 `LOB 표시 조건` 카드다(`render_home_view_card`).
    주요공정 프리셋은 인자로 받지 않는다 — 그 카드는 프래그먼트라 회차마다 공용 프로필을 스스로
    읽는다(`_render_key_process_editor`). `owner_tab` 은 이 `Preference` 탭이다 — 주요 Case 상자가
    숨은 회차에 DB 를 읽지 않으려고 본다(`home_main_cases`).
    """
    _render_comparison_picker(database_path)
    render_main_case_picker(database_path, owner_tab=owner_tab)
    render_threshold_editor(
        months=months,
        month_labels=month_labels,
        threshold_profile=threshold_profile,
        database_path=database_path,
    )
    _render_advance_editor(
        months=months,
        month_labels=month_labels,
        advance_profile=advance_profile,
        database_path=database_path,
    )
    render_advance_shipment_editor(
        months=months,
        month_labels=month_labels,
        advance_shipment_profile=advance_shipment_profile,
        database_path=database_path,
    )
    _render_summary_note_editor(
        summary_profile=summary_profile,
        database_path=database_path,
    )
    _render_top5_band_editor(
        top5_band_profile=top5_band_profile,
        database_path=database_path,
    )
    _render_key_process_editor(
        process_options=process_options,
        process_labels=process_labels,
        database_path=database_path,
    )
    _render_execution_editor(
        months=months,
        execution_profile=execution_profile,
        process_options=process_options,
        process_labels=process_labels,
        unmatched=unmatched_execution,
        clamped=clamped_execution,
        database_path=database_path,
    )


def _recheck_intro_summary() -> None:
    """이 세션의 다음 회차가 입장 화면 Summary 를 곧바로 다시 확인하게 한다.

    Summary 는 판정 기준·선행 B/O·선행 입고 실적·비교 대상 공용 프로필을 쓴다. 이 세션이 들고
    있는 요약은 `RECHECK_SECONDS` 동안 그대로 보내므로, 그 프로필을 저장한 직후 부른다 — 다른
    세션은 다음 확인 때 새 version 의 키로 새 값을 받는다. 함수 안에서 들인다 —
    `intro_summary` → `intro_overlay` → `home_rendering` 이 이 모듈을 들이므로 모듈 머리에 두면
    순환한다.
    """
    from capa_simulation.components.intro_summary import forget_intro_summary_check

    forget_intro_summary_check()


def seed_comparison_selection(database_path: str) -> None:
    """비교 대상 공용 프로필을 세션에 심는다. 이미 세션 값이 있으면 덮지 않는다.

    **`Preference` 탭이 그려질 때가 아니라 HOME 진입 첫 줄에서 불러야 한다.** 이 함수가
    피커 안에만 있으면, 프로필에 비교 대상이 저장돼 있어도 첫 화면에서는 세션이 비어
    있어 「GAP」 토글이 꺼진 채로 뜬다. 탭을 한 번 다녀와야 켜지는데 그 왕복이 사용자에게는
    고장으로 읽힌다.

    세션 값이 있으면 그쪽이 최신이므로 덮지 않는다 — 이번 실행에서 사용자가 고른 값이다.
    """
    if COMPARISON_SCENARIO_KEY in st.session_state:
        return
    try:
        profile = load_global_comparison_scenario(database_path)
    except BOOTSTRAP_ERRORS:
        # 심기에 실패해도 화면은 떠야 한다. 피커가 열릴 때 같은 오류를 사용자에게 알린다.
        return
    if profile.scenario_id is None:
        return
    st.session_state[COMPARISON_SCENARIO_KEY] = profile.scenario_id
    if profile.revision_id is not None:
        st.session_state[COMPARISON_REVISION_KEY] = profile.revision_id


def _render_comparison_picker(database_path: str) -> None:
    """GAP 의 비교 대상. 시나리오와 리비전까지 골라 그 리비전의 계획을 쓴다.

    **지금 활성인 시나리오도 고를 수 있다.** 리비전이 달라지며 계획이 얼마나 바뀌었는지가
    비교의 중요한 쓰임이고, 시나리오가 하나뿐이면 그것을 빼는 순간 고를 것이 없어진다.
    지금 활성인 리비전을 그대로 고르면 자기와 견주는 셈이라 증감이 전부 0 이므로, 상자
    아래 캡션으로 알린다(`_comparison_active_note`).

    **선택지 라벨에는 활성 상태를 붙이지 않는다.** Streamlit 1.63 선택 상자는 고른 항목의 라벨
    글자를 주고받는다. 라벨이 활성 리비전에 따라 바뀌면(전에는 「· 현재 활성」·「· 현재
    시나리오」를 붙였다) 시나리오를 불러온 뒤 브라우저가 옛 라벨을 되보내고, 서버는 그것을
    바뀐 값으로 읽어 다음 조작 하나를 앱 전체 재실행으로 만들고 저장 콜백이
    그 **라벨 글자**를 리비전 id 자리에 공용 프로필로 저장했다(2026-10-08 안정화 점검 계측).
    """
    with st.container(border=True):
        st.markdown("#### :material/compare_arrows: 비교 시나리오")
        repository = get_scenario_repository(database_path)
        seed_comparison_selection(database_path)
        try:
            scenarios = repository.list_scenarios()
        except BOOTSTRAP_ERRORS as exc:
            st.error(bootstrap_error_message(exc))
            return
        if not scenarios:
            st.info("저장된 시나리오가 없습니다.")
            st.session_state.pop(COMPARISON_SCENARIO_KEY, None)
            st.session_state.pop(COMPARISON_REVISION_KEY, None)
            return
        scenario_by_id = {scenario.scenario_id: scenario for scenario in scenarios}
        # 지운 시나리오가 세션에 남아 있으면 위젯이 옵션에 없는 값을 만나 죽는다.
        if st.session_state.get(COMPARISON_SCENARIO_KEY) not in scenario_by_id:
            st.session_state.pop(COMPARISON_SCENARIO_KEY, None)
            st.session_state.pop(COMPARISON_REVISION_KEY, None)
        elif COMPARISON_SCENARIO_KEY in st.session_state:
            # 선택지 글자는 시나리오 이름이라 다른 세션의 이름 바꾸기로 바뀐다. 고른 값을 매 회차
            # 다시 적어야 브라우저가 새 글자를 받는다 — 적지 않으면 옛 이름을 되보내 다음 회차에
            # 그 글자가 id 자리에 들어간다(AGENTS 9장 「글자가 바뀌는 것을 피할 수 없는 상자」).
            # 무효일 때 리비전 칸도 함께 지워야 해서 `prune_choice` 는 쓰지 않는다.
            st.session_state[COMPARISON_SCENARIO_KEY] = st.session_state[COMPARISON_SCENARIO_KEY]
        scenario_id = st.selectbox(
            "비교 시나리오",
            options=[None, *scenario_by_id],
            format_func=lambda value: _comparison_label(scenario_by_id, value),
            key=COMPARISON_SCENARIO_KEY,
            persist_state="session",
            on_change=_save_comparison_scenario,
            args=(database_path,),
        )
        if scenario_id is None:
            st.session_state.pop(COMPARISON_REVISION_KEY, None)
            return
        try:
            revisions = repository.list_revisions(str(scenario_id))
        except BOOTSTRAP_ERRORS as exc:
            st.error(bootstrap_error_message(exc))
            return
        revision_by_id = {revision.revision_id: revision for revision in revisions}
        if not revision_by_id:
            st.session_state.pop(COMPARISON_REVISION_KEY, None)
            st.info("선택한 시나리오에 저장된 리비전이 없습니다.")
            return
        # 시나리오를 바꾸면 앞서 고른 리비전은 남의 것이 된다. 위젯을 만들기 전에 그 시나리오의
        # 첫 리비전(선택 상자의 기본값)으로 **적는다.** 칸을 지우기만 하면 서버는 기본값을 쓰지만
        # 브라우저는 그 사실을 듣지 못해 앞 시나리오의 리비전 이름을 계속 보여 준다(2026-10-05 E2E).
        # 목록에 있는 값도 **매 회차** 다시 적는다 — 선택지 글자의 리비전명은 다른 세션이 바꿀 수
        # 있고, 적지 않으면 브라우저가 옛 글자를 되보내 1.63 이 첫 리비전으로 조용히 되돌린다
        # (AGENTS 9장 「글자가 바뀌는 것을 피할 수 없는 상자」). 적기는 `on_change` 를 부르지 않아
        # 공용 프로필을 다시 쓰지 않는다.
        prune_choice(
            COMPARISON_REVISION_KEY, list(revision_by_id), default=next(iter(revision_by_id))
        )
        active_revision_id = active_persisted_revision_id()
        st.selectbox(
            "비교 리비전",
            options=list(revision_by_id),
            format_func=lambda value: revision_label(revision_by_id[value]),
            key=COMPARISON_REVISION_KEY,
            persist_state="session",
            on_change=_save_comparison_revision,
            args=(database_path,),
        )
        # **위젯 기본값은 `on_change` 를 부르지 않는다.** 시나리오만 고르면 그 시점의
        # 콜백은 리비전 위젯이 생기기 전이라 `revision_id=None` 으로 저장하고, 뒤이어
        # 잡히는 리비전 기본값은 세션에만 들어간다. 그러면 다음 세션에서 짝이 맞지 않아
        # 「GAP」 토글이 꺼진 채로 뜨고, Preference 를 한 번 다녀와야 켜진다.
        _persist_comparison_choice(database_path, revision_by_id.keys())
        note = _comparison_active_note(
            selected_revision_id=st.session_state.get(COMPARISON_REVISION_KEY),
            active_revision=(
                revision_by_id.get(active_revision_id) if active_revision_id is not None else None
            ),
        )
        if note is not None:
            st.caption(note)


def _comparison_active_note(
    *,
    selected_revision_id: object,
    active_revision: RevisionSummary | None,
) -> str | None:
    """고른 비교 대상과 지금 화면에 올라온 리비전의 관계를 상자 아래 한 줄로 적는다.

    선택지 라벨에 붙이던 활성 표시를 여기로 옮겼다. `active_revision` 은 비교 시나리오의 리비전
    가운데 지금 활성인 것이다 — 비교 시나리오가 활성 시나리오가 아니면 없다.
    """
    if active_revision is None:
        return None
    if selected_revision_id == active_revision.revision_id:
        return (
            "지금 화면이 쓰고 있는 리비전입니다. 자기와 견주는 셈이라 증감이 모두 0 으로 나옵니다."
        )
    return (
        f"지금 화면에는 이 시나리오의 {literal_markdown(revision_label(active_revision))} "
        "리비전이 올라와 있습니다."
    )


def _persist_comparison_choice(database_path: str, revision_ids: Collection[str]) -> None:
    """프로필의 리비전 칸이 **그 시나리오의 것이 아닐 때만** 뒤늦게 메운다.

    선택 위젯의 기본값은 콜백을 부르지 않는다. 시나리오만 고른 순간의 콜백은 리비전
    위젯이 생기기 전이라 `revision_id=None` 으로 저장하고, 뒤이어 잡히는 리비전 기본값은
    세션에만 들어간다. 그 한 칸을 여기서 채운다 — 위젯이 다 그려진 뒤라 기본값이 보인다.

    시나리오 상자의 콜백(`_save_comparison_scenario`)도 리비전 칸을 비운 채 저장하므로, 그 칸을
    채우는 것이 이 함수다. 비어 있는 것만 메우지 않고 **「그 시나리오의 리비전 집합 안에
    있는가」**로 판정한다 — 프로필에 어긋난 짝(그 시나리오의 것이 아닌 리비전)이 남아 있으면 그것도
    바로잡는다. 집합은 피커가 이미 읽어 둔 것을 받으므로 DB 를 더 읽지 않는다.

    **그 밖의 불일치는 쓰지 않는다.** 프로필은 시나리오에 딸리지 않은 공용 값이라 다른
    사용자도 같은 행을 쓴다. 「세션과 다르다」를 「세션이 최신이다」로 읽으면, 남이 방금
    고른 값을 이쪽 세션의 옛 값으로 되쓰게 된다. HOME 은 `st.tabs` 라 숨은 Preference
    탭도 매 rerun 실행되므로, 두 사람이 서로의 선택을 계속 뒤집는 핑퐁이 된다. 아무도
    아무것도 고르지 않아도 쓰기가 일어나 `version` 이 오르고 DB 가 dirty 로 표시된다.

    사용자가 실제로 고른 값은 두 상자의 콜백(`_save_comparison_scenario`·
    `_save_comparison_revision`)이 맡는다. 여기는 메우는 일만 한다.

    **저장에 실패해도 화면을 멈추지 않는다.** 이번 화면은 세션 값으로 이미 동작하고,
    남기지 못한 것은 다음 세션에서 기본값이 안 뜨는 정도의 일이다.
    """
    scenario_id = st.session_state.get(COMPARISON_SCENARIO_KEY)
    revision_id = st.session_state.get(COMPARISON_REVISION_KEY)
    if scenario_id is None or revision_id is None:
        return
    current = (str(scenario_id), str(revision_id))
    try:
        profile = load_global_comparison_scenario(database_path)
        if profile.scenario_id != current[0] or profile.revision_id in revision_ids:
            return
        get_scenario_repository(database_path).replace_global_comparison_scenario(
            current[0],
            current[1],
            source="HOME 비교 대상 선택",
        )
    except (*BOOTSTRAP_ERRORS, ValueError):
        return
    clear_global_comparison_scenario_cache()
    _recheck_intro_summary()


def _save_comparison_scenario(database_path: str) -> None:
    """비교 **시나리오** 상자의 콜백. 고른 시나리오를 리비전 칸을 비운 채 공용 프로필에 남긴다.

    선택 위젯이라 저장 버튼을 따로 두지 않는다 — 고르는 것이 곧 결정이고, 버튼을 한 번 더
    누르게 하면 눌렀는지 아닌지가 화면에 남지 않는다.

    **리비전은 여기서 정하지 않는다.** 시나리오를 바꾼 순간 세션의 리비전은 앞 시나리오의 것이다.
    같은 회차에 피커가 그 시나리오의 리비전(세션 값이 그 시나리오의 것이 아니면 첫 리비전)을 잡고,
    `_persist_comparison_choice` 가 비운 칸을 그 값으로 메운다. 두 상자가 콜백 하나를 나눠 쓰던
    때는 앞 시나리오의 리비전이 함께 와서, 공용 프로필이 이미 그 시나리오의 다른 리비전을 가리키면
    고른 것이 저장되지 않았다(2026-10-08 적대적 리뷰 F1).

    **저장에 실패해도 화면을 멈추지 않는다.** 비교 대상은 이번 화면에서 이미 세션 값으로
    동작하고, 남기지 못한 것은 다음 세션에서 기본값이 안 뜨는 정도의 일이다. 그것 때문에
    대시보드가 서면 손해가 더 크다.
    """
    scenario_id = st.session_state.get(COMPARISON_SCENARIO_KEY)
    if scenario_id is None:
        # 시나리오를 비우면 리비전은 남의 것이 된다. 짝을 맞춰 함께 비운다.
        st.session_state.pop(COMPARISON_REVISION_KEY, None)
    _replace_comparison_profile(
        database_path, lambda repository: _scenario_choice(repository, scenario_id)
    )


def _save_comparison_revision(database_path: str) -> None:
    """비교 **리비전** 상자의 콜백. 고른 리비전이 고른 시나리오의 것일 때만 공용 프로필에 남긴다."""
    scenario_id = st.session_state.get(COMPARISON_SCENARIO_KEY)
    revision_id = st.session_state.get(COMPARISON_REVISION_KEY)
    _replace_comparison_profile(
        database_path,
        lambda repository: _revision_choice(repository, scenario_id, revision_id),
    )


def _replace_comparison_profile(
    database_path: str,
    choose: Callable[[DuckDBScenarioRepository], tuple[str | None, str | None] | None],
) -> None:
    """`choose` 가 낸 짝을 공용 프로필에 쓴다. 짝이 없거나 프로필과 같으면 쓰지 않는다.

    콜백은 Streamlit 이 「바뀌었다」고 본 회차마다 불리는데, 브라우저가 같은 항목을 다른 글자로
    되보낸 경우에도 그렇게 본다. 공용 프로필이라 쓸 때마다 `version` 이 오르고 DB 가 dirty 가
    되므로 같은 짝은 다시 쓰지 않는다.

    콜백은 `app.py` 의 실행 핀 밖(스크립트 본문 전)에서 돈다. 유효성 확인(`choose` 의 목록 읽기)·
    프로필 읽기·쓰기가 연결마다 DuckDB 인스턴스를 새로 만들지 않게 여기서 핀을 잡는다. 핀은 첫
    연결 때 잡히고 이 블록이 끝나면 풀린다 — 목록은 캐시 없이 DB 에서 읽는다.
    """
    with pinned_connections(Path(database_path)):
        try:
            repository = get_scenario_repository(database_path)
            chosen = choose(repository)
            if chosen is None:
                return
            profile = load_global_comparison_scenario(database_path)
            if (profile.scenario_id, profile.revision_id) == chosen:
                return
            repository.replace_global_comparison_scenario(
                chosen[0], chosen[1], source="HOME 비교 대상 선택"
            )
        except (*BOOTSTRAP_ERRORS, ValueError):
            return
    clear_global_comparison_scenario_cache()
    _recheck_intro_summary()


def _scenario_choice(
    repository: DuckDBScenarioRepository, scenario_id: object
) -> tuple[str | None, str | None] | None:
    """시나리오 상자가 받은 값의 저장할 짝. 실제 시나리오 id 가 아니면(라벨 글자 등) `None`."""
    if scenario_id is None:
        return None, None
    chosen = str(scenario_id)
    if chosen not in {scenario.scenario_id for scenario in repository.list_scenarios()}:
        return None
    return chosen, None


def _revision_choice(
    repository: DuckDBScenarioRepository, scenario_id: object, revision_id: object
) -> tuple[str | None, str | None] | None:
    """리비전 상자가 받은 값의 저장할 짝. 고른 시나리오의 실제 리비전이 아니면 `None`."""
    if scenario_id is None or revision_id is None:
        return None
    chosen_scenario, chosen_revision = str(scenario_id), str(revision_id)
    revision_ids = {revision.revision_id for revision in repository.list_revisions(chosen_scenario)}
    if chosen_revision not in revision_ids:
        return None
    return chosen_scenario, chosen_revision


def _comparison_label(scenarios: dict[str, ScenarioSummary], value: str | None) -> str:
    """비교 시나리오 선택지의 글. 활성 상태와는 무관하지만 시나리오 이름 바꾸기로 바뀔 수 있어
    `_render_comparison_picker` 가 고른 값을 매 회차 되쓴다."""
    if value is None:
        return "선택 안 함"
    return scenarios[value].scenario_name


def render_threshold_editor(
    *,
    months: Sequence[int],
    month_labels: Sequence[str],
    threshold_profile: GlobalSecurementThreshold,
    database_path: str,
) -> None:
    """확보율 판정 기준 — 기본 확보·경고 두 칸과 월별 예외 표(2026-10-06 사용자 결정).

    판정 기준은 시나리오와 무관한 공용 정책값이고 **여기 한 곳**에서만 정한다(사이드바 입력은
    없앴다). 월별 표의 빈칸은 그 달 그 항목이 기본값을 따른다. 입력은 퍼센트(119.5)이고 저장은
    비율(1.195)이다. 저장은 공용 프로필 교체이며 편집을 시작할 때 본 version 과 대조한다.
    """
    submitted_base = st.session_state.get(THRESHOLD_BASE_VERSION_KEY)
    with st.container(border=True):
        st.markdown("#### :material/rule: 확보율 판정 기준")
        st.caption(
            profile_version_caption(
                threshold_profile,
                empty=(
                    f"아직 저장하지 않아 {threshold_profile.fallback} 값"
                    f"(확보 {_exact_percent(threshold_profile.default_secure)} · 경고 "
                    f"{_exact_percent(threshold_profile.default_warning)})을 씁니다"
                ),
                detail=_threshold_detail(threshold_profile),
            )
        )
        stored = _thresholds_by_month(threshold_profile)
        outside = sorted(set(stored) - set(months))
        with st.form("home_threshold_form"):
            # 작업 줄(저장·메모)은 표 **위**다 — 선행 B/O 편집기와 같은 결이다.
            with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
                submitted = st.form_submit_button(
                    "판정 기준 저장",
                    icon=":material/save:",
                    type="primary",
                )
                note = st.text_input(
                    "변경 메모",
                    placeholder="예: 27년 이후 확보 기준 120% 적용",
                    key=THRESHOLD_NOTE_KEY,
                )
            # 저장 결과(성공·오류)는 누른 버튼 바로 아래 한 자리다.
            notice = st.container()
            with notice:
                render_flash(THRESHOLD_FLASH_KEY)
            # **`key` 를 두지 않는다.** Top5 대역과 같은 이유다 — 키가 붙은 칸은 한 번 그려진 뒤
            # 세션 값을 써서, 다른 사람이 바꾼 기본값을 이 화면이 못 본 채 저장 한 번으로 되돌린다.
            secure_column, warning_column = st.columns(2)
            with secure_column:
                default_secure = st.number_input(
                    "기본 확보 기준(%)",
                    value=_percent_value(threshold_profile.default_secure),
                    # 하한은 0 이다. 칸은 저장본·공식버전 프리셋이 무엇이든 그려져야 고칠 수 있고,
                    # 0 이하 값은 저장 검증이 어느 칸인지 적어 거부한다.
                    min_value=0.0,
                    step=0.1,
                    format="%.1f",
                    help=(
                        "확보율이 이 값 이상이면 확보입니다. 월별 표에서 비워 둔 달은 이 값을 "
                        "씁니다."
                    ),
                )
            with warning_column:
                default_warning = st.number_input(
                    "기본 경고 기준(%)",
                    value=_percent_value(threshold_profile.default_warning),
                    min_value=0.0,
                    step=0.1,
                    format="%.1f",
                    help="이 값 미만은 부족, 이 값 이상·확보 기준 미만은 경고입니다.",
                )
            edited: pd.DataFrame | None = None
            if months:
                table = pd.DataFrame(
                    [
                        [label, *[_cell_percent(stored.get(month), index) for month in months]]
                        for index, label in enumerate((SECURE_COLUMN, WARNING_COLUMN))
                    ],
                    columns=[DIMENSION_COLUMN, *month_labels],
                    # 달 칸은 늘 float64 다 — 두 줄 모두 빈 달이 Arrow null 이면 남의 저장으로 첫
                    # 값이 들어온 회차에 데이터 서명이 바뀌어 폼 안의 보내지 않은 편집이 사라진다.
                ).astype({label: "float64" for label in month_labels})
                edited = st.data_editor(
                    table,
                    key=THRESHOLD_EDITOR_KEY,
                    hide_index=True,
                    num_rows="fixed",
                    width="stretch",
                    # 빈칸은 「기본값을 따른다」는 뜻이라 `None` 글자가 아니라 빈칸으로 그린다.
                    placeholder="",
                    disabled=[DIMENSION_COLUMN],
                    column_config={
                        DIMENSION_COLUMN: st.column_config.TextColumn(
                            DIMENSION_COLUMN, width="small"
                        ),
                        **{
                            label: st.column_config.NumberColumn(label, step=0.1, format="%.1f")
                            for label in month_labels
                        },
                    },
                )
            else:
                st.caption(
                    "조회기간에 계획이 있는 달이 없어 월별 칸이 없습니다. 기본값만 저장합니다."
                )
            # 표에 보이지 않는 달은 여기서 고칠 수 없다. 그 달이 새 기본값과 거꾸로 짝이 되어 저장을
            # 막을 때 조회기간을 바꾸지 않고도 풀 수 있게, 기간 밖 예외를 지우는 길을 둔다.
            clear_outside = bool(
                outside
                and st.checkbox(
                    f"조회기간 밖 월별 기준 {len(outside):,}개월 지우기({_month_labels(outside)})",
                    key=THRESHOLD_CLEAR_OUTSIDE_KEY,
                    help=(
                        "체크하고 저장하면 표에 보이지 않는 달의 월별 기준을 지워 기본값을 "
                        "따르게 합니다."
                    ),
                )
            )
        if not submitted:
            st.session_state[THRESHOLD_BASE_VERSION_KEY] = threshold_profile.version
            _render_threshold_out_of_range_notice(months, threshold_profile)
            return
        expected_version = (
            submitted_base if isinstance(submitted_base, int) else threshold_profile.version
        )
        # 결과가 무엇이든 다음 저장은 이 회차가 그린 저장본에서 출발한다.
        st.session_state[THRESHOLD_BASE_VERSION_KEY] = threshold_profile.version
        # 표지 dict 는 저장 전에 받아 둔다 — 저장 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
        save_marks = profile_save_marks()
        try:
            saved = _save_thresholds(
                database_path,
                months=months,
                month_labels=month_labels,
                edited=edited,
                default_secure=float(default_secure),
                default_warning=float(default_warning),
                threshold_profile=threshold_profile,
                expected_version=expected_version,
                source=note.strip() or "웹 직접 편집",
                clear_outside=clear_outside,
            )
        except BOOTSTRAP_ERRORS as exc:
            # 충돌이면 다른 세션이 저장한 것이 아직 이 화면에 없을 수 있다. 다음 회차가 최신
            # 저장본을 그리게 캐시를 비운다.
            clear_global_securement_threshold_cache()
            if isinstance(exc, ProfileVersionConflict) and is_own_profile_save(
                THRESHOLD_SAVE_NAME, exc.expected, exc.stored
            ):
                # 같은 단추의 빠른 두 번 누름이다 — 첫 누름이 이미 저장했다(write_guard).
                queue_flash(THRESHOLD_FLASH_KEY, THRESHOLD_SAVED_MESSAGE)
                st.rerun(scope="app")
            # 검증 실패(어느 달인지)와 버전 충돌은 ValueError 이고 원문이 고칠 곳을 말한다.
            notice.error(str(exc) if isinstance(exc, ValueError) else bootstrap_error_message(exc))
        else:
            save_marks[THRESHOLD_SAVE_NAME] = (expected_version, saved.version)
            queue_flash(THRESHOLD_FLASH_KEY, THRESHOLD_SAVED_MESSAGE)
            st.rerun(scope="app")


def _save_thresholds(
    database_path: str,
    *,
    months: Sequence[int],
    month_labels: Sequence[str],
    edited: pd.DataFrame | None,
    default_secure: float,
    default_warning: float,
    threshold_profile: GlobalSecurementThreshold,
    expected_version: int,
    source: str,
    clear_outside: bool = False,
) -> GlobalSecurementThreshold:
    """표에 보이는 달만 갈아 끼우고 조회기간 밖 저장분은 그대로 둔다(선행 B/O 와 같은 규칙).

    `clear_outside` 면 조회기간 밖 월별 기준을 지운 뒤 합친다.
    """
    rows = threshold_profile.rows
    if clear_outside:
        rows = rows.loc[rows["생산계획년월"].isin([int(month) for month in months])]
    if edited is not None and months:
        secure_row = edited.iloc[0]
        warning_row = edited.iloc[1]
        rows = merge_securement_threshold_edits(
            rows,
            list(months),
            [_ratio_or_none(secure_row[label]) for label in month_labels],
            [_ratio_or_none(warning_row[label]) for label in month_labels],
        )
    _reject_hidden_reversed_months(months, default_secure / 100.0, default_warning / 100.0, rows)
    saved = get_scenario_repository(database_path).replace_global_securement_threshold(
        default_secure / 100.0,
        default_warning / 100.0,
        rows,
        source=source,
        expected_version=expected_version,
    )
    clear_global_securement_threshold_cache()
    # 입장 화면 Summary 도 같은 기준으로 판정한다(새 기준의 지문으로 새로 만든다).
    _recheck_intro_summary()
    return saved


def _reject_hidden_reversed_months(
    months: Sequence[int],
    default_secure: float,
    default_warning: float,
    rows: pd.DataFrame,
) -> None:
    """새 기본값과 합쳐 거꾸로 짝이 되는 달이 표에 보이지 않으면 고칠 길까지 적어 거부한다.

    저장 검증도 같은 달을 거부하지만 그 문구만으로는 표에 없는 달을 어디서 고칠지 알 수 없다.
    기본값 자체가 잘못된 경우는 저장 검증의 문구가 더 정확하므로 여기서는 보지 않는다.
    """
    if not 0 < default_warning <= default_secure:
        return
    visible = {int(month) for month in months}
    hidden = [
        month
        for month in reversed_threshold_months(
            build_securement_thresholds(default_secure, default_warning, rows)
        )
        if month not in visible
    ]
    if hidden:
        raise ValueError(
            f"조회기간 밖 달 {_month_labels(hidden)}은(는) 이 기본값과 합치면 경고 기준이 확보 "
            "기준보다 큽니다. 표에 보이지 않는 달이라 조회기간을 넓혀 그 달을 고치거나, "
            "「조회기간 밖 월별 기준 지우기」를 체크하고 저장하세요."
        )


def _render_threshold_out_of_range_notice(
    months: Sequence[int],
    threshold_profile: GlobalSecurementThreshold,
) -> None:
    """조회기간 밖에 남아 있는 월별 기준. 보이지 않는 값이 판정에 남는 것을 알린다."""
    outside = sorted(set(_thresholds_by_month(threshold_profile)) - set(months))
    if not outside:
        return
    st.caption(
        f"조회기간 밖에 월별 기준이 저장된 달이 {len(outside):,}개 있습니다"
        f"({_month_labels(outside)}). 표에는 보이지 않지만 그대로 보존되며, 저장해도 지워지지 "
        "않습니다. 지우려면 「조회기간 밖 월별 기준 지우기」를 체크하고 저장하세요."
    )


def _threshold_detail(threshold_profile: GlobalSecurementThreshold) -> str:
    """버전 캡션의 앞머리. 기본값과 월별 예외 수를 함께 적는다."""
    base = (
        f"기본 확보 {_exact_percent(threshold_profile.default_secure)} · "
        f"경고 {_exact_percent(threshold_profile.default_warning)}"
    )
    count = len(threshold_profile.rows)
    return f"{base} · 월별 예외 {count:,}개월" if count else base


def _thresholds_by_month(
    threshold_profile: GlobalSecurementThreshold,
) -> dict[int, tuple[float | None, float | None]]:
    return {
        month: (secure, warning) for month, secure, warning in threshold_profile.thresholds.monthly
    }


def _percent_value(ratio: float) -> float:
    """비율을 입력 칸의 퍼센트로. 1.195 × 100 = 119.49999… 가 칸에 그대로 보이지 않게 다듬는다."""
    return round(float(ratio) * 100.0, 6)


def _exact_percent(ratio: float) -> str:
    """캡션용 정확한 퍼센트. 입력한 값(119.5)을 그대로 보여 준다."""
    return f"{_percent_value(ratio):g}%"


def _cell_percent(pair: tuple[float | None, float | None] | None, index: int) -> float | None:
    if pair is None:
        return None
    value = pair[index]
    return None if value is None else _percent_value(value)


def _ratio_or_none(value: object) -> float | None:
    """표 칸(퍼센트)을 비율로. 빈칸은 None — 그 달 그 항목은 기본값이다."""
    numeric = pd.to_numeric(pd.Series([value], dtype="object"), errors="coerce").iloc[0]
    return None if pd.isna(numeric) else float(numeric) / 100.0


@dataclass(frozen=True)
class _MonthlyAmountEditor:
    """월별 억Gb 한 줄 편집기(선행 B/O·선행 입고 실적)의 글자와 키.

    두 편집기는 모양·저장 규칙(`services/monthly_amount`)이 같고 이름과 저장 자리만 다르다. 폼을
    두 벌 적으면 한쪽만 고쳐져 두 상자가 다르게 움직인다. 키는 편집기마다 따로다 — 선행 B/O 의
    키는 예전 이름 그대로 둬 남아 있는 세션 값이 이어진다.
    """

    title: str
    empty: str
    form_key: str
    save_label: str
    note_key: str
    placeholder: str
    flash_key: str
    editor_key: str
    row_label: str
    saved_message: str


_ADVANCE_LOAD_EDITOR = _MonthlyAmountEditor(
    title="#### :material/fast_forward: 선행 B/O",
    empty="아직 넣은 선행 B/O 가 없습니다",
    form_key="home_advance_load_form",
    save_label="선행 B/O 저장",
    note_key=ADVANCE_NOTE_KEY,
    placeholder="예: 26.07 선행 B/O 재공 반영",
    flash_key="home_advance_flash",
    editor_key=ADVANCE_EDITOR_KEY,
    row_label=ADVANCE_LOAD_ROW_LABEL,
    saved_message="선행 B/O 를 공용 설정으로 저장했습니다.",
)
_ADVANCE_SHIPMENT_EDITOR = _MonthlyAmountEditor(
    title="#### :material/local_shipping: 선행 입고 실적",
    empty="아직 넣은 선행 입고 실적이 없습니다",
    form_key="home_advance_shipment_form",
    save_label="선행 입고 저장",
    note_key=ADVANCE_SHIPMENT_NOTE_KEY,
    placeholder="예: 26.03 선행 입고 실적 반영",
    flash_key=ADVANCE_SHIPMENT_FLASH_KEY,
    editor_key=ADVANCE_SHIPMENT_EDITOR_KEY,
    row_label=ADVANCE_SHIPMENT_ROW_LABEL,
    saved_message="선행 입고 실적을 공용 설정으로 저장했습니다.",
)
# 두 편집기가 같이 쓰는 `구분` 칸 폭(px). 두 상자의 행 이름 가운데 가장 긴 것에 맞춘다 —
# `small`(75px)이면 「선행 입고 실적」이 「선행 입고 실ㅈ」로 잘린다. 폭이 하나라 두 상자의 달
# 칸이 같은 자리에 선다. 글자 폭은 분류 칸과 같은 셈(`text_width_units` × 글자 단위 px)이고,
# 칸 좌우 여백을 더한다.
_MONTHLY_AMOUNT_LABEL_PADDING_PX = 20
_MONTHLY_AMOUNT_LABEL_WIDTH_PX = round(
    max(
        text_width_units(text)
        for text in (
            DIMENSION_COLUMN,
            _ADVANCE_LOAD_EDITOR.row_label,
            _ADVANCE_SHIPMENT_EDITOR.row_label,
        )
    )
    * tokens.CLASSIFICATION_TEXT_UNIT_PX
    + _MONTHLY_AMOUNT_LABEL_PADDING_PX
)


def _render_advance_editor(
    *,
    months: Sequence[int],
    month_labels: Sequence[str],
    advance_profile: GlobalAdvanceLoad,
    database_path: str,
) -> None:
    """선행 B/O — 계획 밖으로 앞서 만든 B/O 재공(억Gb). 「선행 B/O」 토글을 켠 화면의 계획에
    더한다."""

    def save(values: Sequence[object], source: str) -> None:
        frame = merge_advance_load_edits(advance_profile.rows, list(months), values)
        get_scenario_repository(database_path).replace_global_advance_load(frame, source=source)
        clear_global_advance_load_cache()
        _recheck_intro_summary()

    _render_monthly_amount_editor(
        _ADVANCE_LOAD_EDITOR,
        months=months,
        month_labels=month_labels,
        profile=advance_profile,
        stored=amounts_by_month(advance_profile.rows, ADVANCE_LOAD_VALUE_COLUMN),
        save=save,
    )


def render_advance_shipment_editor(
    *,
    months: Sequence[int],
    month_labels: Sequence[str],
    advance_shipment_profile: GlobalAdvanceShipment,
    database_path: str,
) -> None:
    """선행 입고 실적 — 계획보다 앞서 입고한 물량(억Gb).

    계산은 바꾸지 않고 「선행 입고」 토글을 켜면 Density 칸 오른쪽 끝, 값과 같은 높이(값이 길면 겹칠
    수 있음 — 2026-10-07 사용자 결정)에 적는다.

    `months` 는 HOME `Capa LOB 현황` 월 축의 달 그대로다 — Past Data 를 켰으면 과거 구간 달도
    든다(실적이라 지난 달에 넣는 값이다). 조회기간 밖 저장분은 선행 B/O 처럼 보존한다.
    """

    def save(values: Sequence[object], source: str) -> None:
        frame = merge_advance_shipment_edits(advance_shipment_profile.rows, list(months), values)
        get_scenario_repository(database_path).replace_global_advance_shipment(frame, source=source)
        clear_global_advance_shipment_cache()
        _recheck_intro_summary()

    _render_monthly_amount_editor(
        _ADVANCE_SHIPMENT_EDITOR,
        months=months,
        month_labels=month_labels,
        profile=advance_shipment_profile,
        stored=advance_shipment_by_month(advance_shipment_profile.rows),
        save=save,
    )


def _render_monthly_amount_editor(
    editor: _MonthlyAmountEditor,
    *,
    months: Sequence[int],
    month_labels: Sequence[str],
    profile: VersionedProfile,
    stored: Mapping[int, float],
    save: Callable[[Sequence[object], str], None],
) -> None:
    """월별 억Gb 한 줄 편집기. 저장은 **표에 보이는 달만** 갈아 끼운다(`save` 가 병합한다).

    보이지 않는 달까지 함께 지우면 조회기간을 좁힌 채 저장한 사람이 다른 달의 입력을 모르는 새
    날린다.
    """
    with st.container(border=True):
        st.markdown(editor.title)
        st.caption(profile_version_caption(profile, empty=editor.empty))
        if not months:
            st.info("조회기간에 계획이 있는 달이 없어 입력할 칸이 없습니다.")
            return
        table = pd.DataFrame(
            [[editor.row_label, *[stored.get(month, 0.0) for month in months]]],
            columns=[DIMENSION_COLUMN, *month_labels],
        )
        with st.form(editor.form_key):
            # 작업 줄(저장·메모)은 표 **위**다 — 표를 고친 뒤 버튼을 찾지 않게 한다. 버튼이
            # 왼쪽이다 — 오른쪽 끝에 두면 표 위에 떠오르는 도구 막대(보기·내려받기·검색)에 가린다.
            with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
                submitted = st.form_submit_button(
                    editor.save_label,
                    icon=":material/save:",
                    type="primary",
                )
                note = st.text_input(
                    "변경 메모",
                    placeholder=editor.placeholder,
                    key=editor.note_key,
                )
            # 저장 결과(성공·오류)는 누른 버튼 바로 아래 한 자리다.
            notice = st.container()
            with notice:
                render_flash(editor.flash_key)
            edited = st.data_editor(
                table,
                key=editor.editor_key,
                hide_index=True,
                num_rows="fixed",
                width="stretch",
                # 결측 칸은 `None` 글자가 아니라 빈칸으로 그린다(`month_editor` 와 같은 규칙).
                placeholder="",
                disabled=[DIMENSION_COLUMN],
                column_config={
                    DIMENSION_COLUMN: st.column_config.TextColumn(
                        DIMENSION_COLUMN, width=_MONTHLY_AMOUNT_LABEL_WIDTH_PX
                    ),
                    **{
                        label: st.column_config.NumberColumn(label, step=0.01, format="%.2f")
                        for label in month_labels
                    },
                },
            )
        if not submitted:
            _render_out_of_range_notice(months, stored)
            return
        row = edited.iloc[0]
        try:
            save([row[label] for label in month_labels], note.strip() or "웹 직접 편집")
        except BOOTSTRAP_ERRORS as exc:
            notice.error(bootstrap_error_message(exc))
        else:
            queue_flash(editor.flash_key, editor.saved_message)
            st.rerun()


def _render_out_of_range_notice(months: Sequence[int], stored: Mapping[int, float]) -> None:
    """조회기간 밖에 남아 있는 입력분. 보이지 않는 값이 화면에 남는 것을 알린다."""
    outside = sorted(set(stored) - set(months))
    if not outside:
        return
    labels = _month_labels(outside)
    st.caption(
        f"조회기간 밖에 저장된 달이 {len(outside):,}개 있습니다({labels}). 표에는 보이지 "
        "않지만 그대로 보존되며, 저장해도 지워지지 않습니다."
    )


def _month_labels(months: Sequence[int]) -> str:
    """차트 월 칸과 같은 `YY.MM` 표기. 안내 문구가 표와 같은 낱말을 써야 찾을 수 있다."""
    return ", ".join(month_label(month) for month in months)


def _render_summary_note_editor(
    *,
    summary_profile: GlobalSummaryNote,
    database_path: str,
) -> None:
    """HOME 맨 위에 띄우는 공지 문구.

    계산에 들어가지 않는 **화면 문구**다. 그래서 공용 프로필 중 유일하게 캐시를 비운 뒤
    `st.rerun` 을 부르지 않아도 되지만, 부르지 않으면 저장한 사람만 옛 문구를 본다.

    **빈 문구도 저장한다.** 공지를 내리는 것도 결정이고, 지우고 저장하면 화면에서
    사라지는 것이 지우기의 뜻이다. 저장은 **버전 대조**다(판정 기준과 같다) — 편집을 시작한
    회차의 version 을 세션(`SUMMARY_BASE_VERSION_KEY`)에 두고 저장 회차에 넘긴다.
    """
    submitted_base = st.session_state.get(SUMMARY_BASE_VERSION_KEY)
    with st.container(border=True):
        st.markdown("#### :material/campaign: Summary 공지")
        st.caption(
            profile_version_caption(
                summary_profile,
                empty="아직 공지를 올린 적이 없습니다",
                suffix="공지 중" if summary_profile.is_visible else "내림",
            )
        )
        with st.form("home_summary_note_form"):
            submitted = st.form_submit_button(
                "Summary 저장",
                icon=":material/save:",
                type="primary",
            )
            # 저장 결과(성공·오류)는 누른 버튼 바로 아래 한 자리다.
            notice = st.container()
            with notice:
                render_flash("home_summary_note_flash")
            # **`key` 를 두지 않는다.** 키가 붙은 위젯은 한 번 그려진 뒤 `value` 를 무시하고
            # 세션 값을 쓴다. Preference 는 숨은 탭에서도 위젯을 그리므로 HOME 첫 진입의
            # 공지(대개 빈 문구)가 세션에 박히고, 그 뒤 다른 사람이 올린 공지를 이 화면은
            # 영영 못 본 채 저장 버튼 한 번으로 덮어쓴다. 값은 폼 반환값으로 받으면 된다.
            note = st.text_area(
                "Summary",
                value=summary_profile.note,
                height=180,
                placeholder="예: 9월 물량 확정 전 잠정 계획입니다. B/N 은 SAM 기준.",
            )
        if not submitted:
            st.session_state[SUMMARY_BASE_VERSION_KEY] = summary_profile.version
            return
        expected_version = (
            submitted_base if isinstance(submitted_base, int) else summary_profile.version
        )
        # 결과가 무엇이든 다음 저장은 이 회차가 그린 저장본에서 출발한다.
        st.session_state[SUMMARY_BASE_VERSION_KEY] = summary_profile.version
        message = (
            "Summary 공지를 저장했습니다." if str(note).strip() else "Summary 공지를 내렸습니다."
        )
        # 표지 dict 는 저장 전에 받아 둔다 — 저장 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
        save_marks = profile_save_marks()
        try:
            saved = get_scenario_repository(database_path).replace_global_summary_note(
                str(note),
                source="웹 직접 편집",
                expected_version=expected_version,
            )
        except BOOTSTRAP_ERRORS as exc:
            # 충돌이면 남이 저장한 것이 아직 이 화면에 없을 수 있다. 다음 회차가 최신 저장본을
            # 그리게 캐시를 비운다.
            clear_global_summary_note_cache()
            if isinstance(exc, ProfileVersionConflict) and is_own_profile_save(
                SUMMARY_SAVE_NAME, exc.expected, exc.stored
            ):
                # 같은 단추의 빠른 두 번 누름이다 — 첫 누름이 이미 저장했다(write_guard).
                queue_flash("home_summary_note_flash", message)
                st.rerun(scope="app")
            notice.error(bootstrap_error_message(exc))
            return
        save_marks[SUMMARY_SAVE_NAME] = (expected_version, saved.version)
        clear_global_summary_note_cache()
        queue_flash("home_summary_note_flash", message)
        st.rerun(scope="app")


def _render_top5_band_editor(
    *,
    top5_band_profile: GlobalTop5Band,
    database_path: str,
) -> None:
    """B/N Top5 막대가 표현하는 확보율 구간. 저장은 버전 대조다(Summary 공지와 같다)."""
    submitted_base = st.session_state.get(TOP5_BASE_VERSION_KEY)
    with st.container(border=True):
        st.markdown("#### :material/straighten: B/N Top5 확보율 구간")
        st.caption(
            profile_version_caption(
                top5_band_profile,
                empty=(
                    f"기본값 {top5_band_profile.min_rate:.0%}~"
                    f"{top5_band_profile.max_rate:.0%} 을 씁니다"
                ),
            )
        )
        with st.form("home_top5_band_form"):
            submitted = st.form_submit_button(
                "확보율 구간 저장",
                icon=":material/save:",
                type="primary",
            )
            # 저장 결과(성공·오류)는 누른 버튼 바로 아래 한 자리다.
            notice = st.container()
            with notice:
                render_flash("home_top5_band_flash")
            # **`key` 를 두지 않는다.** 바로 위 Summary 공지와 같은 이유다 — 키가 붙은 위젯은
            # 한 번 그려진 뒤 `value` 를 무시하고 세션 값을 쓴다. Preference 는 숨은 탭에서도
            # 그려지므로 HOME 첫 진입의 구간이 세션에 박히고, 그 뒤 다른 사람이 바꾼 구간을
            # 이 화면은 못 본 채 저장 한 번으로 되돌린다. 위의 `공용 버전 v…` 캡션만 새 번호로
            # 바뀌어 화면이 스스로 모순이 된다. 값은 폼 반환값으로 받으면 된다.
            min_column, max_column = st.columns(2)
            with min_column:
                minimum = st.number_input(
                    "하한(%)",
                    value=top5_band_profile.min_rate * 100,
                    step=10.0,
                    format="%.0f",
                )
            with max_column:
                maximum = st.number_input(
                    "상한(%)",
                    value=top5_band_profile.max_rate * 100,
                    step=10.0,
                    format="%.0f",
                )
        if not submitted:
            st.session_state[TOP5_BASE_VERSION_KEY] = top5_band_profile.version
            return
        expected_version = (
            submitted_base if isinstance(submitted_base, int) else top5_band_profile.version
        )
        # 결과가 무엇이든 다음 저장은 이 회차가 그린 저장본에서 출발한다.
        st.session_state[TOP5_BASE_VERSION_KEY] = top5_band_profile.version
        # 표지 dict 는 저장 전에 받아 둔다 — 저장 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
        save_marks = profile_save_marks()
        try:
            saved = get_scenario_repository(database_path).replace_global_top5_band(
                float(minimum) / 100,
                float(maximum) / 100,
                source="웹 직접 편집",
                expected_version=expected_version,
            )
        except BOOTSTRAP_ERRORS as exc:
            # 충돌이면 다음 회차가 최신 저장본을 그리게 캐시를 비운다(Summary 공지와 같다).
            clear_global_top5_band_cache()
            if isinstance(exc, ProfileVersionConflict) and is_own_profile_save(
                TOP5_SAVE_NAME, exc.expected, exc.stored
            ):
                # 같은 단추의 빠른 두 번 누름이다 — 첫 누름이 이미 저장했다(write_guard).
                queue_flash("home_top5_band_flash", TOP5_SAVED_MESSAGE)
                st.rerun(scope="app")
            notice.error(bootstrap_error_message(exc))
            return
        save_marks[TOP5_SAVE_NAME] = (expected_version, saved.version)
        clear_global_top5_band_cache()
        queue_flash("home_top5_band_flash", TOP5_SAVED_MESSAGE)
        st.rerun(scope="app")


def _apply_pending_selection(key: str) -> None:
    """저장 뒤에 고를 값을 위젯을 만들기 **전**에 넣는다(만든 뒤에는 세션에 쓸 수 없다)."""
    pending = st.session_state.pop(f"{key}__pending", None)
    if isinstance(pending, str):
        st.session_state[key] = pending


def _queue_selection(key: str, value: str) -> None:
    st.session_state[f"{key}__pending"] = value


def render_key_process_field(
    profile: GlobalKeyProcess,
    *,
    process_labels: ProcessLabels,
    process_options: Sequence[str],
) -> None:
    """사이드바 조건 패널의 `주요공정 히트맵` 줄 — 볼 프리셋을 고르는 팝업 칸(2026-10-10).

    B/N 판정 대상(공정 필터)과 **따로** 서는 줄이다. 공정 필터는 판정에 넣을 공정이고, 이것은
    히트맵이 **보여 줄** 행이다. 고른 값은 이 세션의 보는 조건이라 공용 프로필에 쓰지 않는다 —
    프리셋 자체만 공용이다. 아직 고르지 않았거나 고른 프리셋이 지워졌으면 첫 프리셋(기본)이다.
    프리셋이 없으면 칸을 잠그고 어디서 만드는지 이름 줄에 적는다. 부르는 쪽이 페이지 칸 안으로
    들어간 뒤에 부른다.
    """
    names = list(profile.preset_names)
    if not names:
        condition_field(
            KEY_PROCESS_FIELD_LABEL,
            "프리셋 없음",
            slug="key_process",
            key=KEY_PROCESS_FIELD_KEY,
            icon=KEY_PROCESS_ICON,
            status="Preference 탭에서 만듭니다",
            disabled=True,
        )
        return
    applied = resolve_preset_name(names, st.session_state.get(KEY_PROCESS_PRESET_KEY))
    previews = [
        key_process_preview(profile.processes_of(name), process_labels, process_options)
        for name in names
    ]
    shown_count = sum(
        1 for process in profile.processes_of(applied) if process in set(process_options)
    )
    if condition_field(
        KEY_PROCESS_FIELD_LABEL,
        # 값 칸은 버튼 라벨(마크다운)이다 — 프리셋 이름의 「A~B」 가 지움선이 되지 않게 막는다.
        f"{literal_markdown(applied)} · {shown_count}공정",
        slug="key_process",
        key=KEY_PROCESS_FIELD_KEY,
        icon=KEY_PROCESS_ICON,
        on_click=_open_key_process_dialog,
        args=(applied,),
    ):
        show_key_process_dialog(names, previews)


def key_process_preview(
    processes: Sequence[str], process_labels: ProcessLabels, process_options: Sequence[str]
) -> str:
    """프리셋 하나의 공정 미리보기 — 「2공정 · A · B」, 이 화면에 없는 공정은 따로 적는다.

    공용 프리셋이라 다른 시나리오에는 있는 공정이다. 세어 넣으면 격자와 수가 맞지 않는다. 글은
    팝업 라디오 캡션(마크다운)으로 가므로 공정 표시명을 `literal_markdown` 으로 막는다 —
    「CoW~검사~A」 의 물결표가 지움선이 되었다(2026-10-26 E2E).
    """
    known = set(process_options)
    shown = [
        literal_markdown(process_labels.label(process)) for process in processes if process in known
    ]
    absent = [
        literal_markdown(process_labels.label(process))
        for process in processes
        if process not in known
    ]
    text = f"{len(shown)}공정 · " + " · ".join(shown) if shown else "그릴 공정 없음"
    if absent:
        text += " · 이 화면에 없음: " + ", ".join(absent)
    return text


def _open_key_process_dialog(applied: str | None) -> None:
    """칸의 콜백. 다른 팝업 칸을 비우고 라디오 초안을 지금 보는 프리셋으로 적는다."""
    forget_page_dialogs()
    st.session_state[KEY_PROCESS_PICK_KEY] = applied


@st.dialog(KEY_PROCESS_FIELD_LABEL, width="small", icon=KEY_PROCESS_ICON)
def show_key_process_dialog(names: list[str], previews: list[str]) -> None:
    """칸을 누른 회차에만 연다(버튼 반환값). 본문은 아래 함수다."""
    render_key_process_dialog_body(names, previews)


def render_key_process_dialog_body(names: Sequence[str], previews: Sequence[str]) -> None:
    """프리셋 라디오와 프리셋마다의 공정 미리보기. **고르면 곧바로 적용하고 닫힌다.**

    라디오 조작은 팝업(프래그먼트)만 다시 돌린다. 그래서 돌려받은 값을 지금 보는 프리셋과 견주어
    다르면 세션에 적고 앱 전체를 다시 돌린다 — 그 회차에는 칸이 눌리지 않아 팝업이 다시 불리지
    않는다(닫힘). 견주는 값은 **세션의 지금 값**이다 — 적은 뒤 다시 도는 회차에 같아져 되풀이되지
    않는다.
    """
    st.caption(
        "히트맵이 보여 줄 공정 묶음입니다. 고르면 바로 바뀝니다. "
        "프리셋은 Preference 탭에서 고칩니다."
    )
    choice = st.radio(
        "프리셋",
        options=list(names),
        # 선택지 글은 마크다운이다 — 값은 이름 그대로 두고 보이는 글만 막는다.
        format_func=literal_markdown,
        captions=list(previews),
        key=KEY_PROCESS_PICK_KEY,
        label_visibility="collapsed",
    )
    applied = resolve_preset_name(list(names), st.session_state.get(KEY_PROCESS_PRESET_KEY))
    if choice is not None and choice != applied:
        st.session_state[KEY_PROCESS_PRESET_KEY] = choice
        st.rerun(scope="app")


@st.fragment
@keeps_app_run_open
def _render_key_process_editor(
    *,
    process_options: Sequence[str],
    process_labels: ProcessLabels,
    database_path: str,
) -> None:
    """HOME `주요공정 확보율` 격자의 **프리셋**을 만들고 고치는 시트(2026-09-29 사용자 요청).

    「A 그룹은 A·B·C·D, B 그룹은 D·E·F·G」처럼 이름 붙인 공정 묶음을 공용 프로필에 여럿 둔다.
    보는 사람은 HOME 사이드바 `주요공정 히트맵` 카드에서 그중 하나를 고른다. **맨 앞 프리셋이
    기본**이다 — 새로 연 화면이 그것을 본다(`기본으로` 가 맨 앞으로 옮긴다).

    저장은 언제나 **묶음 전체**의 교체다(version+1). 이름을 바꾸면 사이드바에서 그 프리셋을
    보고 있던 선택도 새 이름으로 옮긴다 — 그 선택은 위젯이 아닌 세션 값이라 곧바로 적는다.

    **공정·이름 위젯에 `key` 를 두지 않는다.** `Preference` 탭은 숨어 있어도 그려지므로 `key` 를
    두면 첫 진입 값이 세션에 박혀 다른 사람이 저장한 프리셋을 영영 못 본다. 고칠 프리셋이 바뀌면
    기본값이 바뀌어 위젯이 새로 선다.

    **프래그먼트다.** 「고칠 프리셋」 선택·삭제 확인·이름·공정 입력과 폼 제출은 이 카드만 다시
    돌린다 — 앱 전체(HOME 계산·Figure 직렬화)를 돌릴 까닭이 없는 조작이다. 저장·기본으로·삭제는
    지금처럼 `st.rerun(scope="app")` 으로 앱 전체를 다시 돌려 사이드바 `주요공정 히트맵` 줄과
    히트맵 묶음 키가 새 프로필을 본다. 카드가 도는 동안은 실행 표지를 「끝나지 않음」으로 내려
    둔다(`keeps_app_run_open`) — 저장 도중 사이드바 값 칸·상자를 눌러 이 실행이 끊겨도 그 클릭은
    앱 전체를 다시 돌린다.

    **프로필은 인자로 받지 않고 여기서 회차마다 다시 읽는다.** 프래그먼트 회차는 직전 앱 전체
    회차의 인자를 그대로 쓰는데, 저장·기본으로·삭제는 늘 묶음 **전체의 교체**라 인자로 받은
    묶음으로 만들면 그 사이 다른 세션이 저장한 프리셋을 낡은 묶음으로 덮는다(lost update —
    `tests/test_home_key_process_fragment.py`). 공용 캐시라 적중이면 값싸고, 누가 저장하면
    `clear_global_key_process_cache` 가 프로세스 전역으로 비운다. 공정 목록·표시명은 앱 전체
    회차에서만 바뀌므로 인자 그대로 쓴다.

    다시 읽어도 **고칠 프리셋**은 따로 대조한다. 칸에 key 가 없어 남이 먼저 고친 프리셋(공정·이름)은
    제출 회차에 새 값으로 서서 이 화면의 입력이 버려지고, 이름이 바뀌었으면 「고칠 프리셋」 이 다른
    프리셋으로 넘어간다. 그대로 쓰면 남의 값이나 다른 프리셋을 「저장했습니다」 로 다시
    썼다(2026-10-26 E2E). 그래서 직전 회차(사용자가 보고 고친 화면)가 그린 고칠 프리셋을
    세션(`KEY_PROCESS_SEEN_KEY`)에 두고, 그것이 바뀌었으면 저장·기본으로·삭제를
    거부한다(`_stale_key_process_target`). 쓰기는 이 회차가 읽은 version 을 넘겨 읽기와 쓰기 사이의
    남의 저장도 막는다.
    """
    seen = st.session_state.get(KEY_PROCESS_SEEN_KEY)
    try:
        profile = load_global_key_process(database_path)
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return
    with st.container(border=True):
        st.markdown("#### :material/dataset: 주요공정 히트맵 프리셋")
        st.caption(
            profile_version_caption(
                profile,
                empty="아직 만든 프리셋이 없습니다",
                detail=f"{len(profile.presets)}개 프리셋",
            )
        )
        names = list(profile.preset_names)
        targets = [*names, NEW_KEY_PROCESS_PRESET]
        _apply_pending_selection(KEY_PROCESS_EDIT_TARGET_KEY)
        if st.session_state.get(KEY_PROCESS_EDIT_TARGET_KEY) not in targets:
            st.session_state[KEY_PROCESS_EDIT_TARGET_KEY] = targets[0]
        # 선택지 라벨에 「· 기본」을 붙이지 않는다. 기본(맨 앞)은 `기본으로`·삭제로 바뀌는데, 라벨이
        # 따라 바뀌면 브라우저가 옛 라벨을 되보내 바뀐 값으로 읽힌다(AGENTS 9장 — 선택 상자 라벨에
        # 회차마다 바뀌는 상태를 넣지 않는다). 무엇이 기본인지는 아래 캡션이 말한다.
        target = st.selectbox(
            "고칠 프리셋",
            options=targets,
            key=KEY_PROCESS_EDIT_TARGET_KEY,
            # 보는 프리셋은 다른 화면(탭)에 갔다 와도 남는다. 위에서 세션에 먼저 적으므로 `index=`
            # 를 주지 않는다.
            persist_state="session",
        )
        if names:
            st.caption(f"기본 프리셋(새로 연 HOME 이 처음 보는 것)은 {quoted(names[0])}입니다.")
        is_new = target == NEW_KEY_PROCESS_PRESET
        current = () if is_new else profile.processes_of(target)
        stale = _stale_key_process_target(seen, profile, target, current)
        # 결과가 무엇이든 다음 쓰기는 이 회차가 그린 저장본에서 출발한다.
        st.session_state[KEY_PROCESS_SEEN_KEY] = (profile.version, target, tuple(current))
        known_options = set(process_options)
        # 이 시나리오·조회기간에 없는 공정도 **선택지에 남긴다**(표시만 「이 화면에 없음」). 빼 두면
        # 저장이 그 공정을 공용 프리셋에서 조용히 지웠고, 공정이 모두 없는 프리셋은 이름조차 못
        # 바꿨다(2026-09-29 리뷰에서 재현). 빼려면 목록에서 직접 지운다.
        absent = [process for process in current if process not in known_options]
        # 값은 원본이고 글자만 표시명이다. 보이는 글자가 겹치면 「표시명 (원본)」 으로 가른다
        # (`unique_format_func`) — 같은 글자면 multiselect 가 첫 선택지로 돌아와 고른 것과 다른
        # 공정이 공용 프리셋에 저장됐다. 이 상자는 key 가 없어 위젯 id 에 보이는 글자가 들어가므로,
        # 글자가 바뀌면 새 위젯으로 서서 프리셋 값(`default`)을 다시 읽는다 — 매 회차 세션에 다시
        # 적을 칸이 없고 적을 까닭도 없다.
        base_format = process_labels.unique_format_func([*process_options, *absent])
        with st.form("home_key_process_form"):
            # 작업 줄(저장·이름)은 위다. 버튼이 왼쪽이다.
            with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
                submitted = st.form_submit_button(
                    "프리셋 저장",
                    icon=":material/save:",
                    type="primary",
                )
                name = st.text_input(
                    "프리셋 이름",
                    value="" if is_new else target,
                    max_chars=PRESET_NAME_LIMIT,
                    placeholder="예: A 그룹",
                )
            # 저장 결과(성공·오류)는 누른 버튼 바로 아래 한 자리다.
            notice = st.container()
            with notice:
                render_flash(KEY_PROCESS_FLASH_KEY)
            selected = st.multiselect(
                "공정",
                options=[*process_options, *absent],
                default=list(current),
                format_func=lambda process: (
                    base_format(process)
                    if process in known_options
                    else f"{base_format(process)} · 이 화면에 없음"
                ),
                max_selections=KEY_PROCESS_LIMIT,
                # 몇 개까지 되는지는 고르기 전에 알아야 해 자리 글자에 둔다. 고른 차례가 행 순서다.
                placeholder=f"공정을 고르세요 (최대 {KEY_PROCESS_LIMIT}개 · 고른 차례가 행 순서)",
            )
        if not is_new:
            _render_key_process_notice(absent, process_labels)
            _render_key_process_preset_actions(profile, target, database_path, stale=stale)
        if not submitted:
            return
        if stale is not None:
            _reject_key_process_write(stale, notice)
            return
        # 표지 dict 는 저장 전에 받아 둔다 — 저장 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
        save_marks = profile_save_marks()
        try:
            new_name = normalize_preset_name(name)
            entry = (new_name, tuple(selected))
            presets = (
                [*profile.presets, entry]
                if is_new
                else [
                    entry if preset == target else (preset, processes)
                    for preset, processes in profile.presets
                ]
            )
            saved = get_scenario_repository(database_path).replace_global_key_process_presets(
                presets, source="웹 직접 편집", expected_version=profile.version
            )
        except BOOTSTRAP_ERRORS as exc:
            _reject_key_process_write(exc, notice)
            return
        save_marks[KEY_PROCESS_SAVE_NAME] = (profile.version, saved.version)
        clear_global_key_process_cache()
        _queue_selection(KEY_PROCESS_EDIT_TARGET_KEY, new_name)
        if not is_new and st.session_state.get(KEY_PROCESS_PRESET_KEY) == target:
            st.session_state[KEY_PROCESS_PRESET_KEY] = new_name
        queue_flash(
            KEY_PROCESS_FLASH_KEY,
            f"프리셋 {quoted(new_name)}{object_particle(new_name)} 저장했습니다.",
        )
        st.rerun(scope="app")


def _render_key_process_preset_actions(
    profile: GlobalKeyProcess,
    target: str,
    database_path: str,
    *,
    stale: ProfileVersionConflict | None = None,
) -> None:
    """고르고 있는 프리셋의 `기본으로`·`삭제`. 둘 다 묶음 전체를 다시 쓴다.

    `stale` 은 단추를 그린 화면이 본 고칠 프리셋이 그 사이 바뀌었다는 거부다(편집 카드가 넘긴다).
    있으면 쓰지 않는다 — 이름이 바뀌었으면 단추가 다른 프리셋에 닿는다.
    """
    names = list(profile.preset_names)
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        make_default = st.button(
            "기본으로",
            icon=":material/vertical_align_top:",
            key="home_key_process_preset_default",
            disabled=names[0] == target,
            help="맨 앞 프리셋이 새로 연 HOME 이 처음 보는 프리셋입니다.",
        )
        # 라벨에 이름을 넣어 프리셋마다 다른 칸이 되게 한다 — 다른 프리셋으로 옮기면 체크가 풀린다.
        confirmed = st.checkbox(f"{quoted(target)} 삭제 확인")
        delete = st.button(
            "프리셋 삭제",
            icon=":material/delete:",
            key="home_key_process_preset_delete",
            disabled=not confirmed,
        )
    if not (make_default or delete):
        return
    if make_default:
        presets = [
            *(entry for entry in profile.presets if entry[0] == target),
            *(entry for entry in profile.presets if entry[0] != target),
        ]
        message = f"{quoted(target)}{object_particle(target)} 기본 프리셋으로 옮겼습니다."
    else:
        presets = [entry for entry in profile.presets if entry[0] != target]
        message = f"프리셋 {quoted(target)}{object_particle(target)} 지웠습니다."
    if stale is not None:
        _reject_key_process_write(stale, st.container())
        return
    save_marks = profile_save_marks()
    try:
        saved = get_scenario_repository(database_path).replace_global_key_process_presets(
            presets, source="웹 직접 편집", expected_version=profile.version
        )
    except BOOTSTRAP_ERRORS as exc:
        _reject_key_process_write(exc, st.container())
        return
    save_marks[KEY_PROCESS_SAVE_NAME] = (profile.version, saved.version)
    clear_global_key_process_cache()
    queue_flash(KEY_PROCESS_FLASH_KEY, message)
    st.rerun(scope="app")


def _stale_key_process_target(
    seen: object, profile: GlobalKeyProcess, target: str, current: Sequence[str]
) -> ProfileVersionConflict | None:
    """직전 회차가 그린 고칠 프리셋(`seen`)이 그 사이 남의 저장으로 바뀌었으면 그 거부.

    묶음의 **다른** 프리셋이 바뀐 것은 막지 않는다 — 쓰기는 이 회차가 다시 읽은 묶음에 고칠 프리셋만
    갈아 끼우므로 남의 저장이 남는다(`tests/test_home_key_process_fragment.py`). 고칠 프리셋의
    공정이 바뀌었거나 그 이름이 없어져 「고칠 프리셋」 이 다른 프리셋으로 넘어갔으면 거부한다. 첫
    회차(`seen` 없음)와 version 이 그대로인 회차는 대조할 것이 없다.
    """
    if not (isinstance(seen, tuple) and len(seen) == 3 and isinstance(seen[0], int)):
        return None
    seen_version, seen_target, seen_processes = seen
    if seen_version == profile.version:
        return None
    if seen_target == target and tuple(seen_processes) == tuple(current):
        return None
    return ProfileVersionConflict(
        "다른 사용자가 먼저 주요공정 프리셋을 저장해 이번 저장은 반영하지 않았습니다"
        f"(편집 시작 v{seen_version} · 지금 v{profile.version}). 최신 저장본을 확인한 뒤 다시 "
        "저장하세요.",
        expected=seen_version,
        stored=profile.version,
    )


def _reject_key_process_write(exc: BaseException, notice: DeltaGenerator) -> None:
    """주요공정 프리셋 쓰기(저장·기본으로·삭제)가 거부된 뒤. 버전 충돌이면 캐시를 비운다.

    충돌이 이 세션의 빠른 두 번 누름이면(`is_own_profile_save`) 거부 대신 저장을 다시 알린다.
    """
    if not isinstance(exc, ProfileVersionConflict):
        # 이름 중복 거부(「같은 이름의 프리셋이 이미 있습니다: …」)는 사람이 적은 이름을 싣는다.
        notice.error(markdown_safe_tildes(bootstrap_error_message(exc)))
        return
    # 다음 회차가 최신 저장본을 그리게 비운다 — 앱 밖의 쓰기면 이 회차가 읽은 것도 낡았다.
    clear_global_key_process_cache()
    if is_own_profile_save(KEY_PROCESS_SAVE_NAME, exc.expected, exc.stored):
        # 첫 누름이 남긴 이름 있는 알림이 아직 그려지지 않았으면 그것을 둔다.
        if not st.session_state.get(KEY_PROCESS_FLASH_KEY):
            queue_flash(KEY_PROCESS_FLASH_KEY, KEY_PROCESS_SAVED_MESSAGE)
        st.rerun(scope="app")
    notice.error(bootstrap_error_message(exc))


def _render_key_process_notice(absent: Sequence[str], process_labels: ProcessLabels) -> None:
    """이 프리셋에 저장돼 있으나 이번 화면에서는 그릴 수 없는 공정을 알린다.

    **프리셋에서 지우지 않는다.** 공용 설정이라 다른 시나리오·조회기간에는 그 공정이
    있고, 여기서 조용히 걷어내면 그 화면의 히트맵이 함께 비어 버린다. 선택지에 「이 화면에
    없음」으로 남아 있어 저장해도 그대로 남고, 빼려면 목록에서 직접 지운다.
    """
    if not absent:
        return
    names = ", ".join(literal_markdown(process_labels.label(process)) for process in absent)
    st.caption(
        f":material/info: 이번 시나리오·조회기간에 없어 그리지 않는 공정: {names}. "
        "공용 설정이라 저장해도 프리셋에 그대로 남고, 해당 공정이 있는 화면에서는 그려집니다. "
        "빼려면 목록에서 지우세요."
    )


def _render_execution_editor(
    *,
    months: Sequence[int],
    execution_profile: GlobalExecutionCapacity,
    process_options: Sequence[str],
    process_labels: ProcessLabels,
    unmatched: pd.DataFrame,
    clamped: pd.DataFrame,
    database_path: str,
) -> None:
    """확보율 보정 — 기준정보 밖에서 생긴 변수를 확보율에 퍼센트포인트로 얹는 입력 표.

    저장은 **버전 대조**다 — 편집을 시작한 회차의 version 을 세션(`EXECUTION_BASE_VERSION_KEY`)에
    두고 저장 회차에 넘긴다. 그 사이 다른 사람이 저장했으면 저장소가 거부한다.
    """
    submitted_base = st.session_state.get(EXECUTION_BASE_VERSION_KEY)
    with st.container(border=True):
        st.markdown("#### :material/exposure: 확보율 보정")
        st.caption(
            profile_version_caption(execution_profile, empty="아직 넣은 확보율 보정이 없습니다")
        )
        if not months or not process_options:
            st.info("조회기간에 계산된 공정이 없어 입력할 칸이 없습니다.")
            return
        table = _execution_editor_frame(execution_profile)
        with st.form("home_execution_capacity_form"):
            # 작업 줄(저장·메모)은 표 **위**, 버튼이 왼쪽이다(오른쪽 끝은 표 도구 막대에 가린다).
            with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
                submitted = st.form_submit_button(
                    "확보율 보정 저장",
                    icon=":material/save:",
                    type="primary",
                )
                note = st.text_input(
                    "변경 메모",
                    placeholder="예: 26.07 Wafer Mount 비가동 3대",
                    key=EXECUTION_NOTE_KEY,
                )
            # 저장 결과(성공·오류)는 누른 버튼 바로 아래 한 자리다.
            notice = st.container()
            with notice:
                render_flash("home_execution_flash")
            edited = st.data_editor(
                table,
                key=EXECUTION_EDITOR_KEY,
                hide_index=True,
                num_rows="dynamic",
                width="stretch",
                # 결측 칸은 `None` 글자가 아니라 빈칸으로 그린다(`month_editor` 와 같은 규칙).
                placeholder="",
                column_config={
                    "생산계획년월": st.column_config.SelectboxColumn(
                        "년월",
                        options=list(months),
                        # 저장은 YYYYMM 정수다. 표시만 `26.07` 로 바꾼다.
                        format_func=_month_option_label,
                        required=True,
                    ),
                    "공정": st.column_config.SelectboxColumn(
                        "공정",
                        options=list(process_options),
                        # **값은 원본 공정명이고 보이는 글자만 표시명이다.** 표시명으로
                        # 저장하면 Proc Rename 을 바꾸는 순간 매칭이 끊긴다. 편집표 칸은 값을
                        # 글자가 아니라 옵션 `value` 로 주고받아(고르기·붙여넣기·복사 모두) 겹친
                        # 글자로 다른 공정이 들지는 않는다. 다만 목록에서 둘을 가려 고를 수
                        # 있도록 보이는 글자가 겹치면 「표시명 (원본)」 으로 가른다.
                        format_func=process_labels.unique_format_func(process_options),
                        required=True,
                    ),
                    "증감 확보율": st.column_config.NumberColumn(
                        "증감 확보율(%p)",
                        step=0.1,
                        format="%.1f",
                        required=True,
                    ),
                    "비고": st.column_config.TextColumn("비고", width="medium"),
                },
            )
        if not submitted:
            st.session_state[EXECUTION_BASE_VERSION_KEY] = execution_profile.version
            _render_execution_notices(unmatched, clamped, process_labels)
            return
        expected_version = (
            submitted_base if isinstance(submitted_base, int) else execution_profile.version
        )
        # 결과가 무엇이든 다음 저장은 이 회차가 그린 저장본에서 출발한다.
        st.session_state[EXECUTION_BASE_VERSION_KEY] = execution_profile.version
        # 표지 dict 는 저장 전에 받아 둔다 — 저장 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
        save_marks = profile_save_marks()
        try:
            saved = _save_execution_capacity(
                database_path,
                edited=edited,
                source=note.strip() or "웹 직접 편집",
                expected_version=expected_version,
            )
        except ProfileVersionConflict as exc:
            # 앱 밖의 쓰기면 이 회차가 그린 저장본도 낡았을 수 있다. 다음 회차가 최신 저장본을
            # 그리고 그 version 에서 출발하게 캐시와 출발점을 비운다.
            clear_global_execution_capacity_cache()
            st.session_state.pop(EXECUTION_BASE_VERSION_KEY, None)
            if is_own_profile_save(EXECUTION_SAVE_NAME, exc.expected, exc.stored):
                # 같은 단추의 빠른 두 번 누름이다 — 첫 누름이 이미 저장했다(write_guard).
                queue_flash("home_execution_flash", EXECUTION_SAVED_MESSAGE)
                st.rerun(scope="app")
            notice.error(str(exc))
            return
        except BOOTSTRAP_ERRORS as exc:
            notice.error(bootstrap_error_message(exc))
            return
        except ValueError as exc:
            notice.error(str(exc))
            return
        save_marks[EXECUTION_SAVE_NAME] = (expected_version, saved.version)
        queue_flash("home_execution_flash", EXECUTION_SAVED_MESSAGE)
        st.rerun(scope="app")


def _month_option_label(value: str | int | float | bool) -> str:
    """`SelectboxColumn` 은 스칼라 합집합을 넘긴다. 저장값은 YYYYMM 정수다."""
    return month_label(int(value))


def _execution_editor_frame(execution_profile: GlobalExecutionCapacity) -> pd.DataFrame:
    """저장분을 그대로 보여준다. 한 행도 없으면 빈 표로 시작한다."""
    rows = execution_profile.rows
    if rows.empty:
        return empty_execution_capacity()
    return rows.loc[:, list(EXECUTION_CAPACITY_COLUMNS)].copy()


def _save_execution_capacity(
    database_path: str,
    *,
    edited: pd.DataFrame,
    source: str,
    expected_version: int,
) -> GlobalExecutionCapacity:
    frame = edited.loc[:, list(EXECUTION_CAPACITY_COLUMNS)].copy()
    saved = get_scenario_repository(database_path).replace_global_execution_capacity(
        prepare_execution_capacity(frame),
        source=source,
        expected_version=expected_version,
    )
    clear_global_execution_capacity_cache()
    return saved


def _render_execution_notices(
    unmatched: pd.DataFrame,
    clamped: pd.DataFrame,
    process_labels: ProcessLabels,
) -> None:
    """넣었는데 화면이 그대로인 이유와, 0 에서 잘린 행을 알린다."""
    if not unmatched.empty:
        examples = ", ".join(
            f"{month_label(int(month))}·{literal_markdown(process_labels.label(process))}"
            for month, process in zip(
                unmatched["생산계획년월"].head(5),
                unmatched["공정"].head(5),
                strict=True,
            )
        )
        st.warning(
            f"이번 시나리오·조회기간에 짝이 없어 반영되지 않은 행 {len(unmatched)}건: "
            f"{examples}. 공용 설정이라 저장은 남아 있고, 해당 공정이 있는 시나리오에서는 "
            "그대로 적용됩니다.",
            icon=":material/link_off:",
        )
    if not clamped.empty:
        st.warning(
            f"조정 결과가 0% 아래로 내려가 0 에서 자른 행이 {len(clamped)}건 있습니다. "
            "막대 길이와 순위가 의미를 잃지 않도록 자릅니다.",
            icon=":material/vertical_align_bottom:",
        )
