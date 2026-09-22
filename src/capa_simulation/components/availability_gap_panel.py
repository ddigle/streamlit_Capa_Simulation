# Purpose: Static·Dynamic 비교에서 선택한 가용대수·분류 내역·확보율 결과 하나를 그린다.

"""Static 대 Dynamic 가용대수 비교 탭.

이 탭만 **시뮬레이션 DB** 를 본다. 나머지 탭은 설비 운영 DB 만 열며, 이 페이지는 활성
시나리오가 없어도 열리는 유일한 계산 계열 화면이다. 그래서 Static 을 못 읽는 상황
(시나리오 없음·DB 잠김)은 **이 탭 안에서만** 알리고 다른 탭을 막지 않는다 — 페이지가
통째로 죽으면 Cut-off 를 적으러 들어올 수조차 없다.

가용대수 그림·분류별 표·확보율 교차검증 중 선택한 결과만 그린다.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import pandas as pd
import streamlit as st

from capa_simulation.components.availability_gap_figure import (
    build_availability_gap_figure,
    month_label,
)
from capa_simulation.components.plotly_layout import hover_chart_config
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.services.availability_gap import build_availability_gap, gap_matrix
from capa_simulation.services.monthly_equipment_availability import (
    build_monthly_equipment_availability,
    processes_in,
    span_date_range,
)
from capa_simulation.services.securement_cross_check import (
    build_securement_cross_check,
    dynamic_available_equipment,
)

__all__ = ["PROCESS_FILTER_KEY", "RESULT_VIEW_KEY", "render_availability_gap_panel"]

PROCESS_FILTER_KEY = "equipment_gap_process_filter_v1"
RESULT_VIEW_KEY = "equipment_gap_result_view_v1"
_ALL_PROCESSES = "전체 합계"
_RESULT_VIEWS = ("가용대수 비교", "분류별 내역", "확보율 교차검증")


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
) -> None:
    """비교 탭 본문.

    `spans` 는 `build_equipment_lifecycle_spans` 의 결과다. **호출자는 그 구간을
    `span_date_range` 가 알려 주는 범위로 만들어 넘겨야 한다** — Cut-off 가 크면 그 달의
    W/D 구간이 앞으로 크게 밀려, 조회기간만큼만 만든 구간으로는 첫 달이 조용히 모자라게
    세어진다. 그 범위를 여기서도 다시 재어 어긋나면 알린다.
    숨은 탭은 계산과 렌더링을 건너뛰고, 두 선택값은 세션에 남긴다.
    """
    if tab_is_hidden(owner_tab):
        return

    st.markdown("#### :material/compare_arrows: Static · Dynamic 가용대수 비교")
    st.caption(
        "Static 은 기준정보(RQ_EQP_AVBL)의 월별 가용대수이고, Dynamic 은 호기 마스터의 "
        "일정과 비가동을 공정별 Cut-off 로 **일할 계산**한 값입니다 — 그 달에 며칠 있었는지로 "
        "1대를 쪼개 셉니다. GAP 이 음수면 기준정보가 "
        "실제 확보보다 낙관적이라는 뜻입니다."
    )

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
    selected = st.selectbox(
        "공정",
        options=options,
        key=PROCESS_FILTER_KEY,
        persist_state="session",
        help="전체 합계는 **양쪽에 다 있는 공정만** 더합니다. 한쪽에만 있는 공정은 "
        "이름을 골라 따로 봅니다.",
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
                "그 공정은 위 목록에서 이름을 골라 따로 봅니다."
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

    display = matrix.copy()
    display.columns = pd.Index([month_label(int(column)) for column in display.columns], name="월")
    st.dataframe(display.round(2), width="stretch")
    st.caption(
        "**「환산비 반영」 행은 GAP 에 들어가지 않습니다.** Static 은 설비를 센 대수라 "
        "환산대수와 맞대면 단위가 어긋납니다 — 그 행은 월 Total Capa 를 낼 때 쓰는 축입니다."
    )
    st.caption(
        "「Dynamic 가용 소계」에 들어가는 것은 `기존보유` 와 `가용` 둘뿐입니다. "
        "나머지 분류는 왜 못 쓰는지를 보여 주는 참고 행이라 소계에 더하지 않습니다 — "
        "호기 상태는 서로 배타적이라 모두 더하면 가용대수가 아니라 보유 호기-일수가 됩니다."
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
    st.caption(
        "`확보율차이` 가 음수면 기준정보의 Static 가용대수가 실제 확보보다 큽니다 — "
        "그만큼 확보율이 낙관적으로 잡혀 있었다는 뜻입니다. "
        "Dynamic 가용대수는 호기별 환산비를 반영한 축입니다."
    )


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
