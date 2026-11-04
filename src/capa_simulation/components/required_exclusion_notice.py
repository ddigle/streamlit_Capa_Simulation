# Purpose: 소요대수에 들지 않은 수요·제외 기준정보의 상태 알림과 계획 쪽 제외 목록을 낸다.

"""**0 으로 접은 것을 말하지 않으면 확보율이 조용히 낙관 쪽으로 틀어진다.**

부하량에서 빠진 계획(기준정보 없음), 생산수량이 비어 계획 없음으로 본 계획, `RQ_REQB` 경로에 닿지
않은 계획 부하, 부하가 붙었는데 대당 Capa 가 없어 뺀 경로 — 모두 계산을 멈추지 않고 이어 가는 대신
그 수요가 어느 공정의 소요대수에도 들지 않는다. 그만큼 소요대수가 작아져 확보율이 실제보다 높게
나올 수 있다(빈 생산수량이 정말 계획 없음이면 그대로다). 그 제품에 그 소요기준·WF 구분 경로가
아예 없어 닿지 않은 부하(EDP-TSV 의 PKG 처럼 규칙상 쓰지 않는 조합)는 세지도 그리지도 않는다 — 세면
모두에게 늘 뜨는 경고가 되고, 확보율이 높게 나온다는 말도 그 경우 사실이 아니다.

그래서 같은 문장을 여러 자리에서 쓴다. Admin Area 「알림 모음」 탭이 한 줄로 모으고(HOME 에는
띄우지 않는다 — 2026-10-19 사용자 요청), 리비전 저장·공식 발행 검사는 허락하면서 경고, 공식버전 자동
갱신의 발행은 막지 않고 실행 기록 사유 끝에 붙인다(`auto_official_update_runner` — 「지금 실행」
결과는 화면 발행과 같이 성공 알림 밑의 경고로 따로 띄운다). 모두 시나리오 전체 기간이다. 목록은
산출 결과 → 소요대수 탭에 있다.

계획을 고친 사람이 「고쳤는데 수가 안 바뀐다」 고 헷갈리지 않게 두 자리에도 같은 문장을 띄운다 —
PKG PLAN 적용 알림 칸 맨 아래(시나리오 전체 기간, 적용 알림이 서는 회차)와 Static Capa 현황 요약
맨 위(그 화면의 조회기간 — 미달 건수·필요대수가 그만큼 작게 나올 수 있다). 두 자리는 **계획 쪽
건수만** 싣는다(`plan_side_counts`) — 경로 쪽(대당 Capa 가 없어 뺀 부하 경로)은 대당 Capa 기준정보
몫이라 계획을 고치지 않아도 늘 있을 수 있고(사내 리뷰 `202610271800` 보충 8-2X 에서 0 이 아니었다),
그대로 실으면 적용할 때마다·현황 요약을 열 때마다 서는 경고가 된다(HOME 에서 이 줄을 뺀 2026-10-19
결정과 같은 까닭). 경로 쪽은 위 자리들(알림 모음·저장·발행 검사)이 그대로 말한다.

**화면 자리는 상태 알림이다**(2026-11-03 결정 보드 D2 (나)). Static Capa · 산출 결과 · 생산 계획은
이 경고를 자리에 그리지 않고 `alerts.state` 로 낸다 — 내용(건수)이 바뀔 때만 오른쪽 아래 알림창에
뜨고 Alarm 에 남으며 조건이 사라지면 「해소」 가 선다. 짧은 글은 무엇이(건수) 어디에(목록 자리)
있는지를 말한다. 코드는 `ST-01`(계획 쪽 · 조회기간 — Static Capa 와 산출 결과 소요대수 탭이 같은
코드 · 같은 범위라 한쪽에서 본 것은 다른 쪽에서 다시 뜨지 않는다), `ST-04`(PKG PLAN 적용 뒤 ·
시나리오 전체 기간), `ST-14`(대당 Capa 제외 기준정보 — 목록은 Alarm 줄의 표), `ST-15`(대당 Capa 가
없어 소요대수에서 뺀 경로), `ST-21`(PKG 의 Buffer 밖 행 — 규칙이라 알림 단계)다. 계획 쪽
목록에서 고칠 곳은 펼침 안 자리 글이 아니라 까닭 칸(`누락 기준정보` · `제외사유`) 머리 풍선과
Guide 가 말한다(설계 규칙 UI-TXT-01 · 02 · 03).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.exclusion_table import render_exclusion_table
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.state_alerts import AlertScope
from capa_simulation.services.display_order import DisplayOrderInput
from capa_simulation.services.load_calculator import PLAN_QUANTITY_BLANK_REASON
from capa_simulation.services.required_equipment import (
    PKG_UNCOUNTED_REASON,
    UNROUTED_KEY_MISMATCH_REASON,
    UNROUTED_REASON_COLUMN,
    UNROUTED_UNKNOWN_PRODUCT_REASON,
    RequiredExclusionCounts,
    counted_unrouted_loads,
)

# 문장의 범위 말. 저장·발행 검사와 Admin Area 「알림 모음」·PKG PLAN 적용 알림은 시나리오 전체 기간,
# Static Capa 현황 요약은 그 화면이 보는 조회기간으로 본다.
FULL_SCOPE = "시나리오 전체 기간"
PERIOD_SCOPE = "조회기간"
# 문장의 머리. 자동 갱신의 발행 줄 뒤에 이어 적힌 이 경고를 실행 기록 사유에서 다시 가를 때도 쓴다
# (`auto_official_update_runner.split_published_reason`).
UNCOUNTED_DEMAND_LEAD = "소요대수에 들지 않은 수요가 있습니다"
# 계획 쪽 목록이 서는 자리 — 알림 짧은 글이 「어디서 보는지」 로 적는다.
REQUIRED_LIST_PLACE = "산출 결과 › 소요대수"
# 대당 Capa 제외 목록(Alarm 줄의 표) 이름. 2026-11-02 사용자 요청(검수표) 전에는 대당 Capa 탭 본문의
# 「제외 기준정보 확인」 펼침이었다.
CAPACITY_EXCLUSION_TITLE = "제외 기준정보"
# 계획 쪽 목록의 까닭 칸과 그 칸 머리 풍선 — 그 행을 어디서 고치는지(칸 하나의 뜻은 그 칸 곁 풍선 —
# 설계 규칙 UI-TXT-02).
LOAD_EXCLUSION_REASON_COLUMN = "누락 기준정보"
LOAD_EXCLUSION_HELP = (
    "이 칸의 기준정보 표를 채우면 그 계획이 부하량 · 소요대수에 듭니다(수율은 생산 계획 › "
    f"수율 탭). 「{PLAN_QUANTITY_BLANK_REASON}」 은 생산수량이 비어 계획 없음(0)으로 본 "
    "계획입니다 — 원천에서 수량이 빠진 것이면 다시 조회합니다."
)
UNROUTED_HELP = (
    f"「{UNROUTED_KEY_MISMATCH_REASON}」 — 같은 제품·Stack·소요기준의 경로가 다른 달·양산구분·"
    "Capa Code·Customer·CS 에는 있으니 계획 키를 봅니다. "
    f"「{UNROUTED_UNKNOWN_PRODUCT_REASON}」 — 그 제품·Stack 의 경로를 RQ_REQB 에서 봅니다."
)
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


def plan_side_counts(counts: RequiredExclusionCounts) -> RequiredExclusionCounts:
    """계획 쪽 건수만 남긴다(경로 쪽 `excluded_routes` 는 0) — PKG PLAN 적용 알림·Static Capa 현황
    요약처럼 「계획을 고쳤는데 수가 안 바뀐다」 를 말하는 자리가 쓴다(모듈 설명)."""
    return counts._replace(excluded_routes=0)


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
        f"{UNCOUNTED_DEMAND_LEAD}({scope}) — {' · '.join(parts)}. "
        "그만큼 소요대수가 작게, **확보율이 실제보다 높게** 나올 수 있습니다. "
        "목록은 산출 결과 → 소요대수 탭에 있습니다."
    )


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
    건수 경고는 자리에 그리지 않고 상태 알림 `ST-01` 이 말한다(`alert_uncounted_demand`) — 고칠 곳은
    까닭 칸 머리 풍선(`LOAD_EXCLUSION_HELP` · `UNROUTED_HELP`)이다.

    경로 쪽 제외(`소요대수 제외 기준정보`)와 따로 둔다. 고칠 곳이 다르다 — 이쪽은 계획에 맞는
    수율·Chip 구성·경로가 없는 것이라 계획이나 그 기준정보를, 경로 쪽은 대당 Capa 기준정보를 본다.

    경로에 닿지 않은 부하는 건수와 같은 행(`counted_unrouted_loads`)만 그린다. 규칙상 쓰지 않는
    조합(EDP-TSV 의 PKG 처럼 그 제품에 그 소요기준·WF 구분 경로가 없는 것)은 고칠 것이 없어 싣지
    않는다 — 실으면 늘 펼쳐지는 목록이 되어 정작 고칠 행이 묻힌다.
    """
    unrouted_loads = counted_unrouted_loads(unrouted_loads)
    if not load_exclusions.empty:
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
                column_help={LOAD_EXCLUSION_REASON_COLUMN: LOAD_EXCLUSION_HELP},
            )
    if not unrouted_loads.empty:
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
                column_help={UNROUTED_REASON_COLUMN: UNROUTED_HELP},
            )


def alert_uncounted_demand(
    counts: RequiredExclusionCounts,
    *,
    code: str,
    scope: AlertScope,
    scope_name: str,
    tab: str = "",
) -> None:
    """소요대수에 들지 않은 수요(계획 쪽 건수만 — `plan_side_counts`) 상태 알림. 그 조건을 보는
    회차마다(없어도) 부른다 — `ST-01`(`scope_name` 은 `PERIOD_SCOPE`) · `ST-04`(`FULL_SCOPE`)."""
    plan = plan_side_counts(counts)
    message = required_exclusion_message(plan, scope=scope_name)
    total = plan.excluded_plans + plan.blank_plans + plan.unrouted_loads
    alerts.state(
        code,
        scope=scope.scope,
        content=list(plan),
        active=bool(message),
        text=(
            f"소요대수에 안 든 계획 수요 {total:,}건({scope_name}) — 목록: {REQUIRED_LIST_PLACE}"
            if message
            else None
        ),
        full=alerts.plain_text(message) if message else None,
        scope_label=scope.label,
        tab=tab,
    )


def capacity_exclusion_content(exclusions: pd.DataFrame) -> list[object]:
    """대당 Capa 제외의 지문 내용 — 건수와 제외사유별 건수(글이 아니라 구조 값)."""
    if exclusions.empty or "제외사유" not in exclusions.columns:
        return [len(exclusions)]
    reasons = exclusions["제외사유"].astype("string").fillna("").value_counts()
    return [len(exclusions), sorted((str(reason), int(count)) for reason, count in reasons.items())]


def alert_capacity_exclusions(
    exclusions: pd.DataFrame,
    *,
    scope: AlertScope,
    tab: str,
    table: alerts.AlertTable | None,
) -> None:
    """대당 Capa 산출에서 뺀 기준(`ST-14`) — 대당 Capa 탭이 열린 회차마다 부른다. 목록은 `table`
    (Alarm 줄의 「제외 기준정보」 표 · CSV)이다. 표가 알림에 싣기에 크면(None) 화면이 본문 목록을
    남기고 짧은 글이 그 자리를 말한다."""
    count = len(exclusions)
    reasons = ""
    if count and "제외사유" in exclusions.columns:
        reasons = " · ".join(
            f"{reason} {number:,}"
            for reason, number in exclusions["제외사유"].astype("string").value_counts().items()
        )
    place = (
        f"Alarm › 이 줄 「{CAPACITY_EXCLUSION_TITLE}」"
        if table is not None
        else f"이 탭 「{CAPACITY_EXCLUSION_TITLE} 확인」"
    )
    alerts.state(
        "ST-14",
        scope=scope.scope,
        content=capacity_exclusion_content(exclusions),
        active=count > 0,
        text=f"대당 Capa 산출에서 기준 {count:,}개를 뺐습니다 — 목록: {place}",
        full=(
            f"대당 Capa 산출에서 {count:,}개 기준을 제외했습니다"
            + (f"({reasons})" if reasons else "")
            + f". 무엇이 왜 빠졌는지는 {place} 표의 제외사유 칸과 CSV 가 말합니다 — 기준 정보 "
            "화면에서 그 경로의 값을 고치면 다시 듭니다."
        ),
        scope_label=scope.label,
        tab=tab,
        table=table,
    )


def alert_required_exclusions(
    required_exclusions: pd.DataFrame, *, scope: AlertScope, tab: str
) -> None:
    """소요대수 산출에서 뺀 경로 — 대당 Capa 가 없는 것(`ST-15`, 기준정보를 고칠 일)과 PKG 의 Buffer
    밖 행(`ST-21`, 규칙대로 세지 않은 것 — 고칠 것이 없다). 두 사유를 한 문장에 섞으면 고칠 것이
    없는데 고치러 간다. 소요대수 탭이 열린 회차마다 둘 다 부른다."""
    if required_exclusions.empty or "제외사유" not in required_exclusions.columns:
        uncounted_pkg = pd.Series(False, index=required_exclusions.index)
    else:
        uncounted_pkg = required_exclusions["제외사유"].eq(PKG_UNCOUNTED_REASON)
    capacity_missing = required_exclusions.loc[~uncounted_pkg]
    positive = (
        int(capacity_missing["부하량"].gt(0).sum()) if "부하량" in capacity_missing.columns else 0
    )
    alerts.state(
        "ST-15",
        scope=scope.scope,
        content=[len(capacity_missing), positive],
        active=not capacity_missing.empty,
        text=(
            f"대당 Capa 가 없어 소요대수에서 뺀 경로 {len(capacity_missing):,}건 — 목록: 이 탭 "
            "「소요대수 제외 기준정보」"
        ),
        full=(
            f"대당 Capa가 없어 소요대수 산출에서 {len(capacity_missing):,}건을 제외했습니다(부하량 "
            f"발생 {positive:,}건). 목록은 산출 결과 → 소요대수 탭의 「소요대수 제외 기준정보」 "
            "이고 제외사유 칸이 까닭입니다 — 그 경로의 대당 Capa 기준정보를 채우면 소요대수에 "
            "듭니다."
        ),
        scope_label=scope.label,
        tab=tab,
    )
    pkg_count = int(uncounted_pkg.sum())
    alerts.state(
        "ST-21",
        scope=scope.scope,
        content=pkg_count,
        active=pkg_count > 0,
        text=f"소요기준 PKG 는 Buffer 로만 셉니다 — Core·Top·Dummy 등 {pkg_count:,}건 뺌",
        full=(
            f"소요기준 PKG 는 Buffer 로만 셉니다. Core·Top·Dummy 등 {pkg_count:,}건은 Buffer 에 "
            "쌓여 있어 소요대수에 넣지 않았습니다(규칙 — 고칠 것이 없습니다). 목록은 「소요대수 "
            "제외 기준정보」 의 제외사유 칸입니다."
        ),
        scope_label=scope.label,
        tab=tab,
    )
