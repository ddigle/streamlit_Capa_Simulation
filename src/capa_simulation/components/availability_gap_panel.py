# Purpose: Static·Dynamic 비교에서 선택한 가용대수·분류 내역·확보율 결과 하나를 그린다.

"""Static 대 Dynamic 가용대수 비교 탭.

이 탭만 **시뮬레이션 DB** 를 본다. 나머지 탭은 설비 운영 DB 만 열며, 이 페이지는 활성
시나리오가 없어도 열리는 유일한 계산 계열 화면이다. 그래서 Static 을 못 읽는 상황
(시나리오 없음·DB 잠김)은 **이 탭 안에서만** 알리고 다른 탭을 막지 않는다 — 페이지가
통째로 죽으면 Cut-off 를 적으러 들어올 수조차 없다.

가용대수 그림·분류별 표·확보율 교차검증 중 선택한 결과만 그린다.

**분류별 내역은 대수 뒤의 호기를 보인다.** `표시` 를 `호기 목록` 으로 바꾸면 같은 조건의
호기별 기여가 긴 표로 펼쳐지고(CSV), `대수` 표에서 칸 하나를 누르면 그 칸의 호기만 아래에
뜬다. 목록은 대수 표와 **같은 기여 줄**(`build_monthly_equipment_contributions`)에서 나와
같은 칸을 더하면 표의 값이다.

**분류별 내역은 호기 마스터의 컬럼으로 호기를 좁혀 더할 수 있다**(`호기 필터`, 2026-09-29 사용자
요청). 공정처럼 조건 카드에서 컬럼(라인구분·모델·동 …)과 값을 고르면 **그 호기만** 분류대로
다시 더한다 — 대수 표·칸의 호기·호기 목록이 모두 같은 호기 집합을 본다. 필터가 걸리면
`기존보유`(호기 마스터 밖의 집계 대수)와 `Static`·`GAP`(기준정보의 공정 단위 값)은 호기 속성이
없어 표에서 뺀다 — 걸러진 Dynamic 을 거르지 않은 Static 과 맞대면 GAP 이 거짓말을 한다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from datetime import date

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.components.availability_gap_figure import (
    build_availability_gap_figure,
    month_label,
)
from capa_simulation.components.plotly_layout import hover_chart_config
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.services.availability_gap import (
    DYNAMIC_SUBTOTAL_ROW,
    DYNAMIC_WEIGHTED_ROW,
    ROW_KIND_GAP,
    ROW_KIND_STATIC,
    GapComparison,
    build_availability_gap,
    gap_matrix,
)
from capa_simulation.services.equipment_units import format_unit_count
from capa_simulation.services.monthly_equipment_availability import (
    CATEGORIES,
    build_monthly_equipment_availability,
    build_monthly_equipment_contributions,
    processes_in,
    span_date_range,
)
from capa_simulation.services.securement_cross_check import (
    build_securement_cross_check,
    dynamic_available_equipment,
)

__all__ = [
    "DETAIL_CATEGORY_KEY",
    "DETAIL_MODE_KEY",
    "MATRIX_TABLE_KEY",
    "PROCESS_FILTER_KEY",
    "RESULT_VIEW_KEY",
    "UNIT_FILTER_COLUMNS",
    "UNIT_FILTER_COLUMNS_KEY",
    "matrix_table_key",
    "unit_filter_key",
    "render_availability_gap_panel",
]

PROCESS_FILTER_KEY = "equipment_gap_process_filter_v1"
RESULT_VIEW_KEY = "equipment_gap_result_view_v1"
DETAIL_MODE_KEY = "equipment_gap_detail_mode_v1"
DETAIL_CATEGORY_KEY = "equipment_gap_detail_category_v1"
MATRIX_TABLE_KEY = "equipment_gap_matrix_table_v1"
UNIT_FILTER_COLUMNS_KEY = "equipment_gap_unit_filter_columns_v1"
_UNIT_FILTER_KEY_PREFIX = "equipment_gap_unit_filter_v1"
# 분류별 내역을 더할 호기를 좁히는 호기 마스터 컬럼. 공정(`공정소분류`)은 위 `공정` 이 맡는다.
# 날짜·좌표·환산비처럼 호기마다 다른 연속값은 고를 값이 아니라 뺀다.
UNIT_FILTER_COLUMNS = (
    "공정대분류",
    "라인구분",
    "활용구분",
    "투자기준",
    "담당자",
    "Maker",
    "모델",
    "분류1",
    "분류2",
    "분류3",
    "동",
    "층",
    "확정상태",
    "장기보관여부",
    "기존설비여부",
    "모체호기",
    "호기",
)
_ALL_PROCESSES = "전체 합계"
_RESULT_VIEWS = ("가용대수 비교", "분류별 내역", "확보율 교차검증")
_DETAIL_MODES = ("대수", "호기 목록")
_CATEGORY_NAMES = tuple(category.name for category in CATEGORIES)
# 목록의 대수 표시 자릿수. **값은 반올림하지 않는다** — 1/3 지분 셋을 0.333 으로 잘라 더하면
# 0.999 가 되어 「같은 칸을 더하면 표의 값」이 깨진다. CSV 도 반올림 없이 나간다.
_UNIT_NUMBER_FORMAT = {
    column: st.column_config.NumberColumn(format="%.3f") for column in ("대수", "환산대수")
}
# 소계 두 행을 누르면 소계에 드는 분류의 호기를 보인다. Static·GAP 은 기준정보라 목록이 없다.
_SUBTOTAL_CATEGORIES = tuple(
    category.name for category in CATEGORIES if category.counts_as_available
)


def render_availability_gap_panel(
    *,
    spans: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    months: list[int],
    static_availability: pd.DataFrame | None,
    static_error: str | None = None,
    span_bounds: tuple[date, date] | None = None,
    conversion_ratios: Mapping[str, float] | None = None,
    required_equipment: pd.DataFrame | None = None,
    owner_tab: OpenTab | None = None,
    conditions: DeltaGenerator | None = None,
    units: pd.DataFrame | None = None,
) -> None:
    """비교 탭 본문.

    `spans` 는 `build_equipment_lifecycle_spans` 의 결과다. **호출자는 그 구간을
    `span_date_range` 가 알려 주는 범위로 만들어 넘겨야 한다** — Cut-off 가 크면 그 달의
    W/D 구간이 앞으로 크게 밀려, 조회기간만큼만 만든 구간으로는 첫 달이 조용히 모자라게
    세어진다. 그 범위를 여기서도 다시 재어 어긋나면 알린다.
    숨은 탭은 계산과 렌더링을 건너뛰고, 두 선택값은 세션에 남긴다.

    거르는 조건(공정·분류)은 `conditions`(사이드바 조건 카드)에 선다. 주지 않으면 본문 제자리에
    그린다 — 홀로 띄우는 테스트가 쓴다. `units` 는 `spans` 를 만든 호기 마스터이고, 주면 분류별
    내역에 `호기 필터` 가 선다. **무엇을 볼지 고르는 전환(조회 결과·표시)은 본문이다**
    — 탭 안의 하위 탭과 같은 것이라 카드에 넣으면 지금 어느 결과를 보는지 본문에서 사라진다
    (2026-09-29 사용자 결정). 읽는 법(Static·Dynamic 의 뜻, 소계에 드는 분류)은 가용설비 현황
    Guide 다.
    """
    if tab_is_hidden(owner_tab):
        return
    controls = conditions if conditions is not None else nullcontext()

    st.markdown("#### :material/compare_arrows: Static · Dynamic 가용대수 비교")

    if cutoff.empty:
        st.info("공정별 Cut-off 를 먼저 적어야 Dynamic 가용대수를 낼 수 있습니다.")
        return
    if not months:
        st.info("조회기간에 월이 없습니다.")
        return

    required = span_date_range(months, cutoff)
    if required is not None and span_bounds is not None and required[0] < span_bounds[0]:
        st.warning(
            f"Cut-off 때문에 {required[0]:%Y-%m-%d} 부터의 설비 상태가 필요한데 "
            f"조회기간이 {span_bounds[0]:%Y-%m-%d} 부터입니다. 첫 달이 모자라게 세어집니다 — "
            "조회기간의 시작일을 앞당기세요."
        )

    monthly = build_monthly_equipment_availability(
        spans, baseline, cutoff, months, conversion_ratios=conversion_ratios
    )
    # **`or` 를 쓰지 않는다.** 프레임에 `or` 를 걸면 `__bool__` 이 불려
    # 「truth value of a DataFrame is ambiguous」로 죽는다. 빈 프레임도 거짓이라
    # 값이 있는 쪽에서만 터지는데, 그 경로가 곧 실제 화면이다.
    static = pd.DataFrame() if static_availability is None else static_availability
    comparison = build_availability_gap(monthly, static, months)

    if static_error:
        st.warning(f"Static 가용대수를 읽지 못해 Dynamic 만 표시합니다 — {static_error}")

    _render_unmatched(comparison.dynamic_only, comparison.static_only)

    result_view = st.segmented_control(
        "조회 결과",
        options=_RESULT_VIEWS,
        default=_RESULT_VIEWS[0],
        required=True,
        key=RESULT_VIEW_KEY,
        persist_state="session",
    )
    options = [_ALL_PROCESSES, *sorted(set(comparison.rows["공정"].dropna().astype(str)))]
    if (
        PROCESS_FILTER_KEY in st.session_state
        and st.session_state[PROCESS_FILTER_KEY] not in options
    ):
        st.session_state.pop(PROCESS_FILTER_KEY)
    with controls:
        selected = st.selectbox(
            "공정",
            options=options,
            key=PROCESS_FILTER_KEY,
            persist_state="session",
        )
    process = None if selected == _ALL_PROCESSES else selected

    if result_view == "확보율 교차검증":
        _render_securement_cross_check(
            monthly=monthly,
            static_availability=static,
            required_equipment=required_equipment,
            process=process,
        )
        return

    if process is None:
        # **한쪽에만 있는 공정을 합계에서 뺀다.** 넣으면 「Cut-off 를 아직 안 적었다」가
        # 「수백 대 모자라다」로 읽힌다 — 경고 한 줄로는 그 인상을 못 지운다. 공정을
        # 직접 고르면 한쪽짜리도 있는 쪽 값은 보이므로 감추는 것이 아니다(GAP 만 없다).
        excluded = set(comparison.dynamic_only) | set(comparison.static_only)
        scoped = comparison.rows.loc[~comparison.rows["공정"].isin(excluded)]
        if excluded:
            st.caption(
                f"전체 합계에서 한쪽에만 있는 공정 {len(excluded)}개를 뺐습니다. "
                "그 공정은 조회 조건의 `공정` 에서 이름을 골라 따로 봅니다."
            )
    else:
        scoped = comparison.rows

    matrix = gap_matrix(scoped, process)
    if matrix.empty:
        st.info("표시할 값이 없습니다.")
        return

    if not processes_in(spans, baseline):
        st.caption("호기 마스터와 기존보유대수가 모두 비어 있어 Dynamic 이 0 입니다.")

    one_sided = _one_sided_reason(process, comparison)
    if result_view == "가용대수 비교":
        if one_sided is not None:
            # 그림은 Static 과 Dynamic 을 나란히 세우고 그 차이를 막대 위에 적는다. 한쪽이
            # 없으면 맞댈 것이 없고, 비운 GAP 을 그림이 0 으로 채워 「+0.00」이 붙는다.
            st.info(f"{one_sided} 있는 쪽 값은 `분류별 내역` 에서 봅니다.")
            return
        st.plotly_chart(
            build_availability_gap_figure(matrix),
            width="stretch",
            config=hover_chart_config(),
        )
        return

    detail_mode = st.segmented_control(
        "표시",
        options=_DETAIL_MODES,
        default=_DETAIL_MODES[0],
        required=True,
        key=DETAIL_MODE_KEY,
        persist_state="session",
    )
    if one_sided is not None:
        st.caption(f":material/info: {one_sided} 있는 쪽 값만 보입니다.")
    # 전체 합계는 표와 같은 공정만 본다 — 한쪽에만 있는 공정을 뺀 범위다.
    scope = {process} if process is not None else set(scoped["공정"].dropna().astype(str))
    chosen_units: set[str] | None = None
    if units is not None:
        with controls:
            chosen_units, applied = _render_unit_filters(units, scope)
        if chosen_units is not None:
            # 무엇으로 걸렀는지는 본문에도 남긴다 — 카드가 접혀 있으면 표만 보고는 알 수 없다.
            st.caption(
                ":material/filter_alt: 호기 필터 · "
                + " · ".join(applied)
                + f" — 호기 {len(chosen_units):,}개만 더합니다. 기존보유·Static·GAP 은 호기 "
                "속성이 없어 뺐습니다."
            )
            matrix = _unit_filtered_matrix(
                spans, cutoff, months, conversion_ratios, scope, chosen_units, process
            )
            if matrix.empty:
                st.info("호기 필터에 든 호기가 조회기간에 더할 대수가 없습니다.")
                return
    if detail_mode == "호기 목록":
        _render_unit_list(
            _scoped_contributions(
                spans, baseline, cutoff, months, conversion_ratios, scope, chosen_units
            ),
            controls=controls,
        )
        return

    display = matrix.copy()
    month_by_label = {month_label(int(column)): int(column) for column in display.columns}
    display.columns = pd.Index(list(month_by_label), name="월")
    # 칸 하나를 누르면 그 칸의 호기를 아래에 보인다. 선택은 (행 위치, 열 이름)으로 남으므로
    # 공정·기간이 바뀌면 같은 위치가 다른 분류를 가리킨다 — 키에 범위를 넣어 표를 새로 만든다.
    event = st.dataframe(
        display.round(2),
        width="stretch",
        key=matrix_table_key(process, months, list(display.index)),
        on_select="rerun",
        selection_mode="single-cell",
    )
    st.caption("칸을 누르면 그 달·분류에 든 호기를 아래에 보여 줍니다.")
    cells = list(event.selection.cells) if event is not None else []
    if cells:
        position, column = cells[0]
        if column in month_by_label and 0 <= int(position) < len(display):
            _render_cell_units(
                row=str(display.index[int(position)]),
                month=month_by_label[column],
                contributions=_scoped_contributions(
                    spans, baseline, cutoff, months, conversion_ratios, scope, chosen_units
                ),
            )


def matrix_table_key(process: str | None, months: Sequence[int], rows: Sequence[str]) -> str:
    """분류별 대수 표의 위젯 키. **범위가 바뀌면 키도 바뀐다.**

    칸 선택은 (행 위치, 열 이름)으로 남고 Streamlit 은 표 내용이 바뀌어도 선택을 들고
    있다. 공정을 바꾸면 전에 누른 위치가 **다른 분류**를 가리켜 누르지 않은 칸의 호기가
    뜬다(브라우저 실측). 빈 선택을 코드로 밀어 넣는 방법은 첫 번째 변경에만 먹는다 — 화면이
    같은 선택 값을 두 번째부터 무시한다. 그래서 범위마다 다른 표로 만든다. 같은 범위 안에서는
    키가 그대로라 누른 칸이 rerun 을 지나도 남는다.
    """
    scope = repr((process, tuple(int(month) for month in months), tuple(rows)))
    digest = hashlib.sha1(scope.encode("utf-8")).hexdigest()[:10]
    return f"{MATRIX_TABLE_KEY}_{digest}"


def _scoped_contributions(
    spans: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    months: list[int],
    conversion_ratios: Mapping[str, float] | None,
    scope: set[str],
    chosen_units: set[str] | None = None,
) -> pd.DataFrame:
    """표와 같은 범위의 호기별 기여. 목록을 볼 때만 만든다 — 대수 표만 보면 들지 않는 비용이다.

    `chosen_units` 가 있으면 그 호기만 남긴다. 기존보유 줄은 `호기` 가 비어 함께 빠진다 — 호기
    필터를 건 대수 표(`_unit_filtered_matrix`)와 같은 범위다.
    """
    contributions = build_monthly_equipment_contributions(
        spans, baseline, cutoff, months, conversion_ratios=conversion_ratios
    )
    kept = contributions["공정"].astype(str).isin(scope)
    if chosen_units is not None:
        kept &= contributions["호기"].isin(chosen_units).fillna(False).astype(bool)
    return contributions.loc[kept].reset_index(drop=True)


def unit_filter_key(column: str) -> str:
    """호기 필터 한 컬럼의 값 선택 칸."""
    return f"{_UNIT_FILTER_KEY_PREFIX}_{column}"


def _text_values(values: pd.Series) -> pd.Series:
    """필터가 대조하는 문자열. 호기 마스터는 자유 텍스트라 앞뒤 공백을 떼고 빈 칸은 값이 없다."""
    text = values.astype("string").str.strip()
    return text.mask(text.eq(""))


def _reset_unit_filters(columns: Sequence[str]) -> None:
    st.session_state[UNIT_FILTER_COLUMNS_KEY] = []
    for column in columns:
        st.session_state[unit_filter_key(column)] = []


def _drop_unchosen_values(columns: Sequence[str]) -> None:
    # 컬럼을 빼면 그 컬럼의 값 선택도 버린다. 남기면 다시 고를 때 잊은 조건이 되살아난다.
    chosen = st.session_state.get(UNIT_FILTER_COLUMNS_KEY) or []
    for column in columns:
        if column not in chosen:
            st.session_state[unit_filter_key(column)] = []


def _render_unit_filters(units: pd.DataFrame, scope: set[str]) -> tuple[set[str] | None, list[str]]:
    """분류별 내역을 더할 호기를 호기 마스터의 컬럼으로 좁힌다. 걸린 값이 없으면 `None`.

    컬럼을 먼저 고르고 그 컬럼의 값만 세운다 — 열일곱 컬럼을 다 세우면 사이드바가 필터로
    덮인다. 값 목록은 지금 범위(공정)의 호기에서 나오되, 이미 고른 값은 범위를 옮겨도 남긴다
    (다른 공정을 봤다 돌아와도 선택이 그대로다). 호기 마스터에 없는 값만 떨군다.
    """
    columns = [column for column in UNIT_FILTER_COLUMNS if column in units.columns]
    present = {column: _text_values(units[column]) for column in columns}
    offered = [column for column in columns if present[column].notna().any()]
    saved_columns = st.session_state.get(UNIT_FILTER_COLUMNS_KEY)
    if isinstance(saved_columns, list):
        st.session_state[UNIT_FILTER_COLUMNS_KEY] = [
            column for column in saved_columns if column in offered
        ]
    st.markdown("**호기 필터**")
    chosen_columns = st.multiselect(
        "필터할 컬럼",
        options=offered,
        key=UNIT_FILTER_COLUMNS_KEY,
        persist_state="session",
        placeholder="컬럼 선택 · 라인구분·모델·동 …",
        on_change=_drop_unchosen_values,
        args=(columns,),
    )
    if not chosen_columns:
        return None, []
    in_scope = (
        _text_values(units["공정소분류"]).isin(scope).fillna(False).astype(bool)
        if "공정소분류" in units.columns
        else pd.Series(False, index=units.index)
    )
    kept = pd.Series(True, index=units.index)
    applied: list[str] = []
    for column in chosen_columns:
        key = unit_filter_key(column)
        known = set(present[column].dropna())
        saved = st.session_state.get(key)
        selected_before = (
            [value for value in saved if value in known] if isinstance(saved, list) else []
        )
        st.session_state[key] = selected_before
        options = list(
            dict.fromkeys([*sorted(present[column].loc[in_scope].dropna()), *selected_before])
        )
        selected = st.multiselect(
            column,
            options=options,
            key=key,
            persist_state="session",
            placeholder="전체",
            select_all=True,
        )
        if selected:
            kept &= present[column].isin(selected).fillna(False).astype(bool)
            applied.append(f"{column}: {', '.join(selected)}")
    st.button(
        "호기 필터 초기화",
        icon=":material/filter_alt_off:",
        key="equipment_gap_unit_filter_reset_v1",
        width="stretch",
        on_click=_reset_unit_filters,
        args=(columns,),
    )
    if not applied:
        return None, []
    # 공정 범위 안의 호기만 돌려준다. 표는 어차피 범위로 다시 좁히지만, 본문 캡션이 이 수를
    # 「호기 N개만 더합니다」로 적는다 — 범위 밖 호기까지 세면 그 수가 표와 어긋났다(2026-10-01).
    unit_ids = _text_values(units["호기"]).loc[kept & in_scope]
    return set(unit_ids.dropna()), applied


def _unit_filtered_matrix(
    spans: pd.DataFrame,
    cutoff: pd.DataFrame,
    months: list[int],
    conversion_ratios: Mapping[str, float] | None,
    scope: set[str],
    chosen_units: set[str],
    process: str | None,
) -> pd.DataFrame:
    """호기 필터에 든 호기만 분류대로 다시 더한 행렬.

    대수 표와 같은 길(`build_monthly_equipment_availability` → `build_availability_gap` →
    `gap_matrix`)을 걷되 구간을 그 호기로 좁히고 기존보유를 넣지 않는다. Static 을 주지 않으므로
    모든 공정이 Dynamic 에만 있는 공정이 되어 GAP 이 나오지 않는다(한쪽짜리 공정은 GAP 을 내지
    않는다, 2026-10-01). 거르는 줄은 걸러진 Dynamic 을 거르지 않은 Static 과 맞대지 않는다는
    이 경로의 약속을 서비스 규칙과 따로 지킨다.
    """
    unit_ids = _text_values(spans["호기"])
    chosen_spans = spans.loc[unit_ids.isin(chosen_units).fillna(False).astype(bool)]
    monthly = build_monthly_equipment_availability(
        chosen_spans, pd.DataFrame(), cutoff, months, conversion_ratios=conversion_ratios
    )
    rows = build_availability_gap(monthly, pd.DataFrame(), months).rows
    rows = rows.loc[
        rows["공정"].astype(str).isin(scope) & ~rows["행종류"].isin((ROW_KIND_STATIC, ROW_KIND_GAP))
    ]
    return gap_matrix(rows, process)


def _one_sided_reason(process: str | None, comparison: GapComparison) -> str | None:
    """고른 공정이 한쪽에만 있으면 GAP 이 없는 까닭 한 문장. 양쪽에 다 있거나 전체 합계면 `None`.

    서비스가 한쪽짜리 공정의 GAP 을 내지 않는다(`services/availability_gap`). 화면은 GAP 이
    **왜** 없는지를 말한다 — 말하지 않으면 「차이 없음」이나 「계산 누락」으로 읽힌다.
    """
    if process is None:
        return None
    if process in comparison.dynamic_only:
        return f"「{process}」는 기준정보(Static)에 없는 공정이라 GAP 을 내지 않습니다."
    if process in comparison.static_only:
        return (
            f"「{process}」는 Dynamic 이 나오지 않은 공정(Cut-off·설비 없음)이라 GAP 을 내지 "
            "않습니다."
        )
    return None


def _unit_table(rows: pd.DataFrame, *, with_month: bool) -> pd.DataFrame:
    """화면에 얹는 호기 목록. 기존보유 줄은 호기 자리에 그 분류를 적는다.

    설비키는 모듈 행이 있을 때만 보인다(비모듈은 호기와 같은 값이라 칸만 는다).
    """
    table = rows.copy()
    is_baseline = table["호기"].isna()
    table["호기"] = (
        table["호기"]
        .astype("string")
        .mask(is_baseline, "기존보유 · " + table["기존보유분류"].astype("string").fillna("전체"))
    )
    columns = ["공정", "분류", "호기"]
    if bool(table["설비키"].notna().any() and table["설비키"].ne(rows["호기"]).fillna(False).any()):
        table = table.rename(columns={"설비키": "설비"})
        columns.append("설비")
    columns += ["기여일수", "구간일수", "대수", "환산대수"]
    if with_month:
        table.insert(0, "월", table["생산계획년월"].map(lambda month: month_label(int(month))))
        columns.insert(0, "월")
    return table.loc[:, columns]


def _render_cell_units(*, row: str, month: int, contributions: pd.DataFrame) -> None:
    """누른 칸 하나의 호기. 소계 행이면 소계에 드는 분류를 모아 보인다."""
    if row in _CATEGORY_NAMES:
        categories: tuple[str, ...] = (row,)
    elif row in (DYNAMIC_SUBTOTAL_ROW, DYNAMIC_WEIGHTED_ROW):
        categories = _SUBTOTAL_CATEGORIES
    else:
        st.info(f"「{row}」는 기준정보 값이라 호기 목록이 없습니다. 분류나 소계 칸을 누르세요.")
        return
    rows = contributions.loc[
        contributions["생산계획년월"].eq(month) & contributions["분류"].isin(categories)
    ]
    axis = "환산대수" if row == DYNAMIC_WEIGHTED_ROW else "대수"
    total = float(rows[axis].sum())
    st.markdown(
        f"##### {month_label(month)} · {row} · {len(rows):,}행 · 합계 {format_unit_count(total)}"
    )
    if rows.empty:
        st.caption("이 칸에 기여한 호기가 없습니다.")
        return
    st.dataframe(
        _unit_table(rows, with_month=False),
        hide_index=True,
        width="stretch",
        column_config=_UNIT_NUMBER_FORMAT,
    )


def _render_unit_list(
    contributions: pd.DataFrame, *, controls: AbstractContextManager[object]
) -> None:
    """같은 조건의 호기별 기여를 긴 표 하나로. 분류로 좁히고 CSV 로 내려받는다."""
    if contributions.empty:
        st.info("표시할 호기가 없습니다.")
        return
    present = [name for name in _CATEGORY_NAMES if name in set(contributions["분류"].astype(str))]
    with controls:
        chosen = st.multiselect(
            "분류",
            options=present,
            placeholder="전체 분류",
            key=DETAIL_CATEGORY_KEY,
            persist_state="session",
        )
    rows = contributions.loc[contributions["분류"].isin(chosen)] if chosen else contributions
    table = _unit_table(rows, with_month=True)
    st.dataframe(table, hide_index=True, width="stretch", column_config=_UNIT_NUMBER_FORMAT)
    months = sorted(int(month) for month in rows["생산계획년월"].unique())
    stamp = f"{months[0]}_{months[-1]}" if months else "empty"
    render_csv_download(
        data=table.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"Dynamic_가용대수_호기목록_{stamp}.csv",
        key="download_equipment_gap_unit_list_csv",
    )


def _render_securement_cross_check(
    *,
    monthly: pd.DataFrame,
    static_availability: pd.DataFrame,
    required_equipment: pd.DataFrame | None,
    process: str | None,
) -> None:
    """같은 소요대수에 두 가용대수를 각각 나눈 확보율.

    **HOME·B/N 은 그대로 Static 을 본다.** 여기는 기준정보 값을 교차검증하는 자리이고,
    값이 믿을 만해지고 Cut-off 가 채워진 뒤에 전역 전환을 정한다.
    """
    st.markdown("##### :material/fact_check: 확보율 교차검증")
    if required_equipment is None or required_equipment.empty:
        st.info("소요대수를 읽지 못해 확보율을 맞댈 수 없습니다.")
        return
    if static_availability.empty:
        st.info("Static 가용대수가 없어 맞댈 대상이 없습니다.")
        return

    try:
        check = build_securement_cross_check(
            static_availability,
            dynamic_available_equipment(monthly),
            required_equipment,
        )
    except (KeyError, ValueError) as exc:
        st.warning(f"확보율을 맞대지 못했습니다 — {exc}")
        return

    if check.months:
        st.caption(
            f"맞대어 본 달: {month_label(check.months[0])} ~ {month_label(check.months[-1])} "
            f"({len(check.months)}개월). **설비 조회기간이 덮는 달로 좁혔습니다** — "
            "시나리오 조회기간이 더 넓어도 그 달의 설비 상태를 만들지 않았으면 맞댈 수 "
            "없습니다. 조회기간을 넓히면 늘어납니다."
        )
    if check.fallback_processes:
        st.caption(
            f"Cut-off 가 없어 Static 값으로 채운 공정 {len(check.fallback_processes)}개는 "
            "**차이가 늘 0** 입니다 — 맞대어 본 것이 아니라 같은 값을 두 번 본 자리입니다. "
            f"실제로 비교한 공정은 {len(check.compared_processes)}개입니다."
        )
    # 기준정보에 없는 공정은 소요대수·Static 이 없어 행이 없다(서비스가 뺀다, 2026-10-01).
    # 빈 행을 싣던 때는 그 공정이 「실제로 비교한 공정」으로 세어졌다.
    if check.dynamic_only_processes:
        st.caption(
            f"기준정보(Static)에 없는 공정 {len(check.dynamic_only_processes)}개는 소요대수·"
            "Static 가용대수가 없어 맞대지 않았습니다 — 공정명은 위 경고를 봅니다."
        )
    if process is not None and process in check.dynamic_only_processes:
        st.info(f"「{process}」는 기준정보(Static)에 없는 공정이라 확보율을 맞대지 않습니다.")
        return

    rows = check.rows
    if process is not None:
        rows = rows.loc[rows["공정"] == process]
    # 채운 자리는 비교가 아니므로 기본으로 감춘다. 위 캡션이 개수를 이미 알린다.
    compared = rows.loc[~rows["Static대체"]]
    if compared.empty:
        st.info("아직 맞대어 볼 수 있는 공정이 없습니다. Cut-off 를 적으면 여기에 나타납니다.")
        return

    # **확보율 두 값을 같이 보인다.** 차이만 보이면 「29.5 차이」가 무슨 뜻인지 알 수 없다 —
    # 확보율은 비율이라 소요대수가 작은 공정에서 차이가 크게 나온다.
    display = compared.loc[
        :,
        [
            "생산계획년월",
            "공정",
            "소요대수",
            "Static가용대수",
            "Dynamic가용대수",
            "Static확보율",
            "Dynamic확보율",
            "확보율차이",
        ],
    ].copy()
    display["생산계획년월"] = display["생산계획년월"].map(month_label)
    st.dataframe(display.round(3), hide_index=True, width="stretch")


def _render_unmatched(dynamic_only: list[str], static_only: list[str]) -> None:
    """한쪽에만 있는 공정. **조용히 떨어지면 GAP 이 이유 없이 커 보인다.**"""
    if not dynamic_only and not static_only:
        return
    lines = []
    if dynamic_only:
        lines.append(
            f"- 설비에는 있는데 기준정보에 없는 공정 {len(dynamic_only)}개: "
            f"{', '.join(dynamic_only[:8])}{' …' if len(dynamic_only) > 8 else ''}"
        )
    if static_only:
        lines.append(
            f"- 기준정보에는 있는데 Dynamic 이 안 나온 공정 {len(static_only)}개: "
            f"{', '.join(static_only[:8])}{' …' if len(static_only) > 8 else ''}"
        )
    st.warning(
        "두 쪽의 공정명이 맞지 않는 자리가 있습니다. 호기 마스터의 `공정소분류` 와 "
        "기준정보의 `공정` 이 같은 값이어야 맞댈 수 있습니다.\n" + "\n".join(lines)
    )
