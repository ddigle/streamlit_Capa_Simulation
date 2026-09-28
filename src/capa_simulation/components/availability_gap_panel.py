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
    "matrix_table_key",
    "render_availability_gap_panel",
]

PROCESS_FILTER_KEY = "equipment_gap_process_filter_v1"
RESULT_VIEW_KEY = "equipment_gap_result_view_v1"
DETAIL_MODE_KEY = "equipment_gap_detail_mode_v1"
DETAIL_CATEGORY_KEY = "equipment_gap_detail_category_v1"
MATRIX_TABLE_KEY = "equipment_gap_matrix_table_v1"
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
) -> None:
    """비교 탭 본문.

    `spans` 는 `build_equipment_lifecycle_spans` 의 결과다. **호출자는 그 구간을
    `span_date_range` 가 알려 주는 범위로 만들어 넘겨야 한다** — Cut-off 가 크면 그 달의
    W/D 구간이 앞으로 크게 밀려, 조회기간만큼만 만든 구간으로는 첫 달이 조용히 모자라게
    세어진다. 그 범위를 여기서도 다시 재어 어긋나면 알린다.
    숨은 탭은 계산과 렌더링을 건너뛰고, 두 선택값은 세션에 남긴다.

    조회 조건 위젯(조회 결과·공정·표시·분류)은 `conditions`(사이드바 조건 카드)에 선다
    (2026-09-29). 주지 않으면 본문 제자리에 그린다 — 홀로 띄우는 테스트가 쓴다. 읽는 법(Static·
    Dynamic 의 뜻, 소계에 드는 분류)은 가용설비 현황 Guide 다.
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

    options = [_ALL_PROCESSES, *sorted(set(comparison.rows["공정"].dropna().astype(str)))]
    if (
        PROCESS_FILTER_KEY in st.session_state
        and st.session_state[PROCESS_FILTER_KEY] not in options
    ):
        st.session_state.pop(PROCESS_FILTER_KEY)
    with controls:
        result_view = st.segmented_control(
            "조회 결과",
            options=_RESULT_VIEWS,
            default=_RESULT_VIEWS[0],
            required=True,
            key=RESULT_VIEW_KEY,
            persist_state="session",
        )
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
        # 직접 고르면 한쪽짜리도 그대로 보이므로 감추는 것이 아니다.
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

    if result_view == "가용대수 비교":
        st.plotly_chart(
            build_availability_gap_figure(matrix),
            width="stretch",
            config=hover_chart_config(),
        )
        return

    with controls:
        detail_mode = st.segmented_control(
            "표시",
            options=_DETAIL_MODES,
            default=_DETAIL_MODES[0],
            required=True,
            key=DETAIL_MODE_KEY,
            persist_state="session",
        )
    # 전체 합계는 표와 같은 공정만 본다 — 한쪽에만 있는 공정을 뺀 범위다.
    scope = {process} if process is not None else set(scoped["공정"].dropna().astype(str))
    if detail_mode == "호기 목록":
        _render_unit_list(
            _scoped_contributions(spans, baseline, cutoff, months, conversion_ratios, scope),
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
                    spans, baseline, cutoff, months, conversion_ratios, scope
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
) -> pd.DataFrame:
    """표와 같은 범위의 호기별 기여. 목록을 볼 때만 만든다 — 대수 표만 보면 들지 않는 비용이다."""
    contributions = build_monthly_equipment_contributions(
        spans, baseline, cutoff, months, conversion_ratios=conversion_ratios
    )
    return contributions.loc[contributions["공정"].astype(str).isin(scope)].reset_index(drop=True)


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
