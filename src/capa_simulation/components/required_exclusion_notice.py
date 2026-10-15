# Purpose: 소요대수에 들지 않은 수요의 건수 경고와 계획 쪽 제외 목록을 그린다.

"""**0 으로 접은 것을 말하지 않으면 확보율이 조용히 낙관 쪽으로 틀어진다.**

부하량에서 빠진 계획(기준정보 없음), 생산수량이 비어 계획 없음으로 본 계획, `RQ_REQB` 경로에 닿지
않은 계획 부하, 부하가 붙었는데 대당 Capa 가 없어 뺀 경로 — 모두 계산을 멈추지 않고 이어 가는 대신
그 수요가 어느 공정의 소요대수에도 들지 않는다. 그만큼 소요대수가 작아져 확보율이 실제보다 높게
나올 수 있다(빈 생산수량이 정말 계획 없음이면 그대로다).

그래서 같은 문장을 세 자리에서 쓴다. HOME 은 결론 위에 한 줄(조회기간 기준), 리비전 저장·공식
발행 검사는 허락하면서 경고(시나리오 전체 기간)다. 목록은 산출 결과 → 소요대수 탭에 있다.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.components.exclusion_table import render_exclusion_table
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.services.display_order import DisplayOrderInput
from capa_simulation.services.load_calculator import PLAN_QUANTITY_BLANK_REASON
from capa_simulation.services.required_equipment import RequiredExclusionCounts

# 문장의 범위 말. 같은 결과를 HOME 은 조회기간으로 자르고 저장·발행 검사는 전체 기간으로 본다.
PERIOD_SCOPE = "조회기간 기준"
FULL_SCOPE = "시나리오 전체 기간"
# 목록 표의 분류 컬럼(표시순서가 거는 차례). 월은 표 앞에 그대로 둔다.
_LOAD_EXCLUSION_DIMENSIONS = ("제품정보", "Stack", "WF 구분")
_UNROUTED_DIMENSIONS = (
    "양산구분",
    "제품정보",
    "Stack",
    "Capa Code",
    "Customer",
    "CS",
    "WF 구분",
    "소요기준",
)


def required_exclusion_message(counts: RequiredExclusionCounts, *, scope: str) -> str:
    """건수가 하나라도 있으면 한 문장, 없으면 빈 문자열이라 호출부가 분기를 줄인다."""
    parts = []
    if counts.excluded_plans:
        parts.append(f"기준정보가 없어 부하량에서 빠진 계획 {counts.excluded_plans:,}건")
    if counts.blank_plans:
        parts.append(f"생산수량이 비어 계획 없음으로 본 계획 {counts.blank_plans:,}건")
    if counts.unrouted_loads:
        parts.append(f"RQ_REQB 경로에 닿지 않은 계획 부하 {counts.unrouted_loads:,}건")
    if counts.excluded_routes:
        parts.append(f"대당 Capa 가 없어 뺀 부하 경로 {counts.excluded_routes:,}건")
    if not parts:
        return ""
    return (
        f"소요대수에 들지 않은 수요가 있습니다({scope}) — {' · '.join(parts)}. "
        "그만큼 소요대수가 작게, **확보율이 실제보다 높게** 나올 수 있습니다. "
        "목록은 산출 결과 → 소요대수 탭에 있습니다."
    )


def render_required_exclusion_notice(counts: RequiredExclusionCounts) -> None:
    """건수가 있을 때만 그린다. 없는 날에 자리를 차지하면 다음에는 아무도 안 읽는다."""
    message = required_exclusion_message(counts, scope=PERIOD_SCOPE)
    if message:
        st.warning(message, icon=":material/link_off:")


def render_plan_exclusion_lists(
    load_exclusions: pd.DataFrame,
    unrouted_loads: pd.DataFrame,
    *,
    display_order: DisplayOrderInput,
    page: str,
    tab: str,
    labels: ProcessLabels,
    file_suffix: str,
) -> None:
    """산출 결과 소요대수 탭의 계획 쪽 목록 둘 — 부하량에서 빠진 계획, 경로에 닿지 않은 계획 부하.

    경로 쪽 제외(`소요대수 제외 기준정보`)와 따로 둔다. 고칠 곳이 다르다 — 이쪽은 계획에 맞는
    수율·Chip 구성·경로가 없는 것이라 계획이나 그 기준정보를, 경로 쪽은 대당 Capa 기준정보를 본다.
    """
    if not load_exclusions.empty:
        reasons = load_exclusions["누락 기준정보"]
        blank = int(reasons.eq(PLAN_QUANTITY_BLANK_REASON).sum())
        missing = len(load_exclusions) - blank
        sentences = []
        if missing:
            sentences.append(
                f"기준정보가 없어 부하량에서 빠진 계획이 {missing:,}건 있습니다 — 그 계획은 "
                "소요대수에 들지 않습니다. 「누락 기준정보」 칸의 표를 채우면 반영됩니다"
                "(수율은 생산 계획 → 수율 탭)."
            )
        if blank:
            sentences.append(
                f"생산수량이 빈 계획 {blank:,}건은 계획 없음(0)으로 봤습니다 — 원천에서 수량이 "
                "빠진 것이면 다시 조회해야 합니다."
            )
        st.warning(" ".join(sentences), icon=":material/link_off:")
        with st.expander("부하량에서 빠진 계획", expanded=False):
            render_exclusion_table(
                load_exclusions,
                dimensions=_LOAD_EXCLUSION_DIMENSIONS,
                display_order=display_order,
                page=page,
                tab=tab,
                labels=labels,
                file_name=f"Capa_Load_Exclusions_{file_suffix}.csv",
                key="download_load_exclusions_csv",
            )
    if not unrouted_loads.empty:
        st.warning(
            f"RQ_REQB 경로에 닿지 않은 계획 부하가 {len(unrouted_loads):,}건 있습니다 — 그 부하는 "
            "어느 공정의 소요대수에도 들지 않습니다. 같은 양산구분·제품·Stack·Capa Code·Customer·CS"
            "(PKG 외에는 WF 구분까지)의 경로가 RQ_REQB 에 있는지 보세요.",
            icon=":material/link_off:",
        )
        with st.expander("경로에 닿지 않은 계획 부하", expanded=False):
            render_exclusion_table(
                unrouted_loads,
                dimensions=_UNROUTED_DIMENSIONS,
                display_order=display_order,
                page=page,
                tab=tab,
                labels=labels,
                file_name=f"Capa_Unrouted_Loads_{file_suffix}.csv",
                key="download_unrouted_loads_csv",
            )
