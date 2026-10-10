# Purpose: 사이드바 조회기간 필드와, 월 범위를 고르고 「적용」해야 바뀌는 조회기간 팝업을 그린다.

"""사이드바 「조회 조건」 패널의 조회기간 줄과 그 팝업(2026-10-10 사용자 결정 — 팝업 칸).

값 칸에는 지금 조회기간(「26.07 → 28.12」), 이름 줄 오른쪽에는 그 화면이 실제로 읽은 기간이 선다
(「선택 · …」·「✓ 적용 · …」·「계산 멈춤」·「데이터 없음」·「과거 밖 · …부터」 — 페이지가 계산 뒤에
`sidebar_status.show_*` 로 채운다). 값 칸을 누르면 작은 팝업에 월 선택과 「적용」이 뜬다.

**「적용」을 눌러야 조회기간이 바뀐다.** 전에는 사이드바의 월 선택이 고르는 즉시 조회기간을 바꿨다.
팝업 안에서 고르는 동안은 초안이라 서버에 오지 않고(브라우저의 입력 칸에만 있다), 닫으면 버린다.
「적용」은 월 선택 컴포넌트 안의 단추라 입력 칸 값과 누름이 한 트리거로 한 회차에 온다. 조회기간의
정본은 위젯이 아닌 `MONTH_RANGE_KEY` 하나다 — 리비전 프리셋이 그 칸을 저장·복원한다.

팝업은 시나리오 팝업처럼 세션 키로 연다(`PERIOD_DIALOG_KEY`). Components v2 월 선택이 팝업 안에서
마운트되고 트리거가 팝업(프래그먼트) 재실행으로 돌아오는 것을 1.63 브라우저에서 확인했다.
"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

# 테스트·벤치마크가 `month_range_picker.render_month_range_apply` 를 갈아끼운다(Components v2 는
# AppTest 에 없다). 이름을 직접 import 하면 교체를 무시하므로 부를 때 모듈에서 찾는다.
import capa_simulation.components.month_range_picker as month_range_picker
from capa_simulation.components.condition_field import condition_field
from capa_simulation.components.scenario_edit_bar import pending_edit_labels
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.page_bootstrap import PAGE_DIALOG_SUFFIX, forget_page_dialogs
from capa_simulation.scenario_preset_state import MONTH_PICKER_KEY, MONTH_RANGE_KEY
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.scenario_month_bounds import scenario_month_bounds
from capa_simulation.settings import MONTH_SELECTION_END, MONTH_SELECTION_START, format_month
from capa_simulation.sidebar_status import (
    register_month_range_placeholder,
    show_selected_month_range,
)

PERIOD_FIELD_KEY = "sidebar_period_field"
PERIOD_FIELD_LABEL = "조회기간"
PERIOD_FIELD_ICON = ":material/date_range:"
PERIOD_DIALOG_KEY = f"sidebar_period{PAGE_DIALOG_SUFFIX}"
# 고를 수 있는 월 범위를 기준정보 버전마다 한 번만 계산해 두는 칸 — `(버전, (최소, 최대))`. 조회기간
# 줄은 모든 계산 화면의 회차마다 서므로, 표를 훑는 계산을 회차마다 하지 않는다.
PERIOD_BOUNDS_KEY = "sidebar_period_bounds"


def current_month_range() -> tuple[str, str]:
    """지금 조회기간(`YYYY-MM` 두 개). 칸이 비었거나 깨졌으면 앱 기본 범위다."""
    default = (format_month(MONTH_SELECTION_START), format_month(MONTH_SELECTION_END))
    value = st.session_state.get(MONTH_RANGE_KEY, default)
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return default
    start, end = (str(value[0]), str(value[1]))
    if not (_is_month(start) and _is_month(end)):
        return default
    return start, end


def _is_month(text: str) -> bool:
    parts = text.split("-")
    return len(parts) == 2 and all(part.isdigit() for part in parts) and 1 <= int(parts[1]) <= 12


def _month_number(text: str) -> int:
    return int(text.replace("-", ""))


def period_value_label(start: str, end: str) -> str:
    """값 칸 글자 — 「26.07 → 28.12」."""
    return f"{month_label(_month_number(start))} → {month_label(_month_number(end))}"


def month_selection_bounds() -> tuple[int, int]:
    """고를 수 있는 월 범위 — 기본 조회기간과 활성 기준정보 월의 합집합(`scenario_month_bounds`).

    현재 선택만 보면 기간을 좁힌 다음 바깥 월을 다시 고를 수 없다. 활성 표의 실제 월을 기준으로
    넓혀 Shift 등으로 2031년 이후를 저장해도 계속 조회할 수 있게 한다. 기준정보 버전마다 한 번만
    계산한다. 공식·활성 리비전이 없는 저장소에서도 관리 화면과 기본 조회기간은 연다.
    """
    try:
        version: int | None = get_effective_reference_version()
        tables = get_effective_reference_tables()
    except RuntimeError:
        version, tables = None, {}
    held = st.session_state.get(PERIOD_BOUNDS_KEY)
    if isinstance(held, tuple) and len(held) == 2 and held[0] == version and version is not None:
        bounds = held[1]
        if isinstance(bounds, tuple) and len(bounds) == 2:
            return int(bounds[0]), int(bounds[1])
    bounds = scenario_month_bounds(tables, MONTH_SELECTION_START, MONTH_SELECTION_END)
    st.session_state[PERIOD_BOUNDS_KEY] = (version, bounds)
    return bounds


def render_period_field() -> None:
    """패널의 조회기간 줄. 이름 줄 오른쪽 칸을 적용 기간 자리표시자로 등록한다.

    그 칸에는 먼저 고른 범위를 중립 「선택 · …」으로 적어 둔다. 조회기간을 실제로 읽는 화면이 계산
    뒤에 「✓ 적용 · …」 등으로 덮는다(`sidebar_status.show_*`).

    **고를 수 있는 범위 밖의 조회기간은 매 회차 범위 끝으로 끼운다**(2026-10-11 병합 전 리뷰).
    전에는 사이드바의 월 선택이 매 회차 그 일을 했다(범위 밖 시작은 최소 월, 범위 밖 끝은 최대 월).
    월 선택이 팝업으로 들어간 뒤에도 같은 값을 쓰도록 여기서 한다. 위젯이 아닌 칸이라 언제 적어도
    된다.
    """
    start, end = current_month_range()
    minimum_month, maximum_month = month_selection_bounds()
    clamped = month_range_picker.clamp_month_range(
        start, end, format_month(minimum_month), format_month(maximum_month)
    )
    if clamped != (start, end):
        st.session_state[MONTH_RANGE_KEY] = clamped
        start, end = clamped
    condition_field(
        PERIOD_FIELD_LABEL,
        period_value_label(start, end),
        slug="period",
        key=PERIOD_FIELD_KEY,
        icon=PERIOD_FIELD_ICON,
        on_click=open_period_dialog,
        on_row=_register_status_slot,
    )
    show_selected_month_range(_month_number(start), _month_number(end))


def _register_status_slot(row: DeltaGenerator) -> None:
    register_month_range_placeholder(row.empty())


def open_period_dialog() -> None:
    """값 칸의 콜백. 다른 팝업 칸을 비우고, 앞서 고르다 만 초안을 버리고, 팝업을 연다."""
    forget_page_dialogs()
    # 닫힌 팝업 안 컴포넌트는 브라우저에 없으니 지워도 되돌아올 옛 값이 없다. 다시 열면 지금
    # 조회기간에서 시작한다.
    st.session_state.pop(MONTH_PICKER_KEY, None)
    st.session_state[PERIOD_DIALOG_KEY] = True


def close_period_dialog() -> None:
    st.session_state.pop(PERIOD_DIALOG_KEY, None)


def period_dialog_is_open() -> bool:
    return PERIOD_DIALOG_KEY in st.session_state


@st.dialog(
    PERIOD_FIELD_LABEL,
    width="small",
    icon=PERIOD_FIELD_ICON,
    on_dismiss=close_period_dialog,
)
def show_period_dialog(page_file: str | None) -> None:
    """팝업 껍데기. 열림 키가 있는 동안 `app.py` 가 매 회차 부른다."""
    render_period_dialog_body(page_file=page_file)


def render_period_dialog_body(*, page_file: str | None) -> None:
    """월 선택과 「적용」(한 컴포넌트 — `month_range_picker.render_month_range_apply`).

    「적용」을 누른 회차에만 컴포넌트가 입력 칸의 지금 값을 범위로 돌려준다. 값과 누름이 한 회차에
    오므로 키보드로 고친 직후에 눌러도 그 값이 적용된다(2026-10-11 병합 전 리뷰 — 전에는 600ms 안에
    누르면 옛 기간으로 닫혔다).

    **적용 전 편집 목록을 비우지 않는다**(같은 리뷰). 고른 범위가 바뀌어도 데이터가 있는 달(화면이
    실제로 쓰는 기간)이 그대로면 편집표의 원본도 그대로라 편집이 남는다 — 목록을 비우면 그 회차에
    패널 경고와 저장 확인이 사라진다. 정말 버려지는 경우 경고가 한 회차 더 남는 편이 낫다.
    """
    pending_edits = pending_edit_labels(page_file)
    start, end = current_month_range()
    minimum_month, maximum_month = month_selection_bounds()
    _render_pending_notice(pending_edits)
    st.caption(
        f"고를 수 있는 범위 · {month_label(minimum_month)}–{month_label(maximum_month)} · "
        "「적용」을 눌러야 화면이 이 기간으로 바뀝니다."
    )
    applied = month_range_picker.render_month_range_apply(
        start=start,
        end=end,
        min_month=format_month(minimum_month),
        max_month=format_month(maximum_month),
        key=MONTH_PICKER_KEY,
    )
    if applied is None:
        return
    if applied != (start, end):
        st.session_state[MONTH_RANGE_KEY] = applied
    close_period_dialog()
    st.rerun()


def _render_pending_notice(pending_edits: Sequence[str]) -> None:
    """편집표의 월 칸은 기간이 정한다. 화면에 나오는 달이 바뀌면 적용하지 않은 편집이 버려진다."""
    if pending_edits:
        st.warning(
            ":orange-badge[적용 전 편집] 기간을 바꿔 편집표의 달이 달라지면 "
            + ", ".join(pending_edits)
            + " 의 적용하지 않은 편집이 사라집니다.",
            icon=":material/warning:",
        )
