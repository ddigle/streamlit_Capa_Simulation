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
산출 결과 → 소요대수 탭을 열면 서는 Alarm 줄의 표다(`REQUIRED_LIST_NOTE`).

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
시나리오 전체 기간), `ST-14`(대당 Capa 제외 기준정보), `ST-15`(대당 Capa 가 없어 소요대수에서 뺀
경로), `ST-21`(PKG 의 Buffer 밖 행 — 규칙이라 알림 단계)다.

**목록도 그 알림의 Alarm 줄 표다**(2026-11-05 사용자 요청(검수표) — 「Alarm 안 표로 이동」).
조건의 내역이라 본문 접힘에 두지 않는다(설계 규칙 UI-TXT-04) — 줄의 「… 보기」 가 펼치고 CSV 를
내려받는다(화면은 표시명, 파일은 원본). 표 하나는 그 알림의 건수와 같은 행이다 — `ST-15` · `ST-21`
은 사유로 가르고, `ST-01` · `ST-04` 는 고칠 곳이 다른 계획 쪽 두 목록을 두 표로 싣는다. 표가 알림에
싣기에 크면(`alerts.TABLE_ROW_LIMIT`) 그 목록만 산출 결과 소요대수 탭 본문 펼침에 남는다
(`render_oversized_lists`). 고칠 곳은 까닭 칸(`누락 기준정보` · `제외사유`) 머리 풍선과 Guide 가
말한다(설계 규칙 UI-TXT-01 · 02 · 03).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, NamedTuple

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.exclusion_table import exclusion_export, render_exclusion_table
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.state_alerts import (
    ALARM_ROW_PLACE,
    AlertScope,
    alarm_table_place,
    alert_table,
)
from capa_simulation.services.display_order import DisplayOrderInput
from capa_simulation.services.display_order_scopes import PAGE_CALCULATION, TAB_REQUIRED
from capa_simulation.services.load_calculator import PLAN_QUANTITY_BLANK_REASON
from capa_simulation.services.required_equipment import (
    PKG_UNCOUNTED_REASON,
    RESULT_DIMENSIONS,
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
# 표가 커서 본문에 남은 계획 쪽 목록이 서는 자리 — 알림 짧은 글이 「어디서 보는지」 로 적는다.
REQUIRED_LIST_PLACE = "산출 결과 › 소요대수"
# 문장의 끝 — 목록을 어디서 보는지. 알림 칸 밖의 글(Admin 「알림 모음」 · 저장 · 발행 검사 · 자동
# 갱신 기록)은 그 탭을 열어야 줄이 선다는 것까지 말한다.
REQUIRED_LIST_NOTE = "목록은 산출 결과 → 소요대수 탭을 열면 서는 Alarm 줄의 표입니다."
REQUIRED_LIST_NOTE_THIS_ROW = "목록은 Alarm 의 이 줄에 딸린 표입니다."
REQUIRED_LIST_NOTE_ON_PAGE = "목록은 산출 결과 → 소요대수 탭에 있습니다."
# 제외 목록(Alarm 줄의 표) 이름. 2026-11-02 · 11-05 사용자 요청(검수표) 전에는 탭 본문 펼침이었다.
CAPACITY_EXCLUSION_TITLE = "제외 기준정보"
REQUIRED_EXCLUSION_TITLE = "소요대수 제외 기준정보"
PKG_UNCOUNTED_TITLE = "PKG Buffer 밖 행"
LOAD_EXCLUSION_TITLE = "부하량에서 빠진 계획"
UNROUTED_TITLE = "경로에 닿지 않은 계획 부하"
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


class ExclusionList(NamedTuple):
    """소요대수 탭의 제외 목록 하나 — 알림에 딸린 표(`table`)와, 그 표가 커서 None 일 때 본문 펼침을
    그릴 재료(`render_oversized_lists`)."""

    title: str
    frame: pd.DataFrame
    dimensions: tuple[str, ...] | list[str]
    file_name: str
    key: str
    column_help: Mapping[str, str]
    table: alerts.AlertTable | None


def plan_side_counts(counts: RequiredExclusionCounts) -> RequiredExclusionCounts:
    """계획 쪽 건수만 남긴다(경로 쪽 `excluded_routes` 는 0) — PKG PLAN 적용 알림·Static Capa 현황
    요약처럼 「계획을 고쳤는데 수가 안 바뀐다」 를 말하는 자리가 쓴다(모듈 설명)."""
    return counts._replace(excluded_routes=0)


def required_exclusion_message(
    counts: RequiredExclusionCounts, *, scope: str, list_note: str = REQUIRED_LIST_NOTE
) -> str:
    """건수가 하나라도 있으면 한 문장, 없으면 빈 문자열이라 호출부가 분기를 줄인다. `list_note` 는
    끝 문장(목록 자리)이다 — 그 줄에 표가 딸린 알림은 「이 줄」 을 가리킨다."""
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
        f"{list_note}"
    )


def _exclusion_list(
    frame: pd.DataFrame,
    *,
    title: str,
    dimensions: tuple[str, ...] | list[str],
    file_name: str,
    key: str,
    display_order: DisplayOrderInput,
    labels: ProcessLabels,
    column_help: Mapping[str, str] | None = None,
) -> ExclusionList:
    helps = column_help or {}
    return ExclusionList(
        title,
        frame,
        dimensions,
        file_name,
        key,
        helps,
        alert_table(
            exclusion_export(
                frame,
                dimensions=dimensions,
                display_order=display_order,
                page=PAGE_CALCULATION,
                tab=TAB_REQUIRED,
            ),
            title=title,
            file_name=file_name,
            labels=labels,
            column_help=helps,
        ),
    )


def plan_exclusion_lists(
    load_exclusions: object,
    unrouted_loads: object,
    *,
    display_order: DisplayOrderInput,
    labels: ProcessLabels,
    file_suffix: str,
) -> tuple[ExclusionList, ...]:
    """계획 쪽 목록 둘(있는 것만) — 부하량에서 빠진 계획, 경로에 닿지 않은 계획 부하. 표는
    `alert_uncounted_demand(lists=…)` 가 싣는다. 입력은 프레임 또는 없음이다(결과 `attrs` 에서 꺼낸
    값). 고칠 곳은 까닭 칸 머리 풍선(`LOAD_EXCLUSION_HELP` · `UNROUTED_HELP`)이다.

    경로 쪽 제외(`REQUIRED_EXCLUSION_TITLE`)와 따로 둔다. 고칠 곳이 다르다 — 이쪽은 계획에 맞는
    수율·Chip 구성·경로가 없는 것이라 계획이나 그 기준정보를, 경로 쪽은 대당 Capa 기준정보를 본다.

    경로에 닿지 않은 부하는 건수와 같은 행(`counted_unrouted_loads`)만 싣는다. 규칙상 쓰지 않는
    조합(EDP-TSV 의 PKG 처럼 그 제품에 그 소요기준·WF 구분 경로가 없는 것)은 고칠 것이 없어 싣지
    않는다 — 실으면 늘 있는 목록이 되어 정작 고칠 행이 묻힌다.
    """
    lists: list[ExclusionList] = []
    if isinstance(load_exclusions, pd.DataFrame) and not load_exclusions.empty:
        lists.append(
            _exclusion_list(
                load_exclusions,
                title=LOAD_EXCLUSION_TITLE,
                dimensions=_LOAD_EXCLUSION_DIMENSIONS,
                file_name=f"Capa_Load_Exclusions_{file_suffix}.csv",
                key="download_load_exclusions_csv",
                display_order=display_order,
                labels=labels,
                column_help={LOAD_EXCLUSION_REASON_COLUMN: LOAD_EXCLUSION_HELP},
            )
        )
    if isinstance(unrouted_loads, pd.DataFrame):
        counted = counted_unrouted_loads(unrouted_loads)
        if not counted.empty:
            lists.append(
                _exclusion_list(
                    counted,
                    title=UNROUTED_TITLE,
                    dimensions=_UNROUTED_DIMENSIONS,
                    file_name=f"Capa_Unrouted_Loads_{file_suffix}.csv",
                    key="download_unrouted_loads_csv",
                    display_order=display_order,
                    labels=labels,
                    column_help={UNROUTED_REASON_COLUMN: UNROUTED_HELP},
                )
            )
    return tuple(lists)


def render_oversized_lists(
    lists: Sequence[ExclusionList], *, display_order: DisplayOrderInput, labels: ProcessLabels
) -> None:
    """알림에 싣기에 큰(`table` 이 None) 목록만 소요대수 탭 본문 펼침으로 남긴다 — 닫힌 탭에서는
    부르지 않는다."""
    for item in lists:
        if item.table is None:
            with st.expander(item.title, expanded=False, key=f"{item.key}_list"):
                render_exclusion_table(
                    item.frame,
                    dimensions=item.dimensions,
                    display_order=display_order,
                    page=PAGE_CALCULATION,
                    tab=TAB_REQUIRED,
                    labels=labels,
                    file_name=item.file_name,
                    key=item.key,
                    column_help=item.column_help,
                )


def alert_uncounted_demand(
    counts: RequiredExclusionCounts,
    *,
    code: Literal["ST-01", "ST-04"],
    scope: AlertScope,
    scope_name: str,
    lists: Sequence[ExclusionList],
    tab: str = "",
) -> None:
    """소요대수에 들지 않은 수요(계획 쪽 건수만 — `plan_side_counts`) 상태 알림. 그 조건을 보는
    회차마다(없어도) 부른다 — `ST-01`(`scope_name` 은 `PERIOD_SCOPE`) · `ST-04`(`FULL_SCOPE`).
    `lists` 는 그 범위의 계획 쪽 목록(`plan_exclusion_lists`)이고 표는 이 줄에 딸린다 — 하나라도
    커서 표가 없으면 글이 본문 자리(산출 결과 소요대수 탭)를 가리킨다."""
    plan = plan_side_counts(counts)
    carried = bool(lists) and all(item.table is not None for item in lists)
    message = required_exclusion_message(
        plan,
        scope=scope_name,
        list_note=REQUIRED_LIST_NOTE_THIS_ROW if carried else REQUIRED_LIST_NOTE_ON_PAGE,
    )
    total = plan.excluded_plans + plan.blank_plans + plan.unrouted_loads
    place = ALARM_ROW_PLACE if carried else REQUIRED_LIST_PLACE
    alerts.state(
        code,
        scope=scope.scope,
        content=list(plan),
        active=bool(message),
        text=(
            f"소요대수에 안 든 계획 수요 {total:,}건({scope_name}) — 목록: {place}"
            if message
            else None
        ),
        full=alerts.plain_text(message) if message else None,
        scope_label=scope.label,
        tab=tab,
        tables=[item.table for item in lists],
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
    남기고 글이 그 자리를 말한다."""
    count = len(exclusions)
    reasons = ""
    if count and "제외사유" in exclusions.columns:
        reasons = " · ".join(
            f"{reason} {number:,}"
            for reason, number in exclusions["제외사유"].astype("string").value_counts().items()
        )
    page_place = f"이 탭 「{CAPACITY_EXCLUSION_TITLE} 확인」"
    alerts.state(
        "ST-14",
        scope=scope.scope,
        content=capacity_exclusion_content(exclusions),
        active=count > 0,
        text=(
            f"대당 Capa 산출에서 기준 {count:,}개를 뺐습니다 — 목록: "
            f"{ALARM_ROW_PLACE if table is not None else page_place}"
        ),
        full=(
            f"대당 Capa 산출에서 {count:,}개 기준을 제외했습니다"
            + (f"({reasons})" if reasons else "")
            + ". 무엇이 왜 빠졌는지는 "
            + (alarm_table_place(CAPACITY_EXCLUSION_TITLE) if table is not None else page_place)
            + " 표의 제외사유 칸과 CSV 가 말합니다 — 기준 정보 화면에서 그 경로의 값을 고치면 다시 "
            "듭니다."
        ),
        scope_label=scope.label,
        tab=tab,
        tables=[table],
    )


def alert_required_exclusions(
    required_exclusions: pd.DataFrame,
    *,
    scope: AlertScope,
    tab: str,
    display_order: DisplayOrderInput,
    labels: ProcessLabels,
    file_suffix: str,
) -> tuple[ExclusionList, ...]:
    """소요대수 산출에서 뺀 경로 — 대당 Capa 가 없는 것(`ST-15`, 기준정보를 고칠 일)과 PKG 의 Buffer
    밖 행(`ST-21`, 규칙대로 세지 않은 것 — 고칠 것이 없다). 두 사유를 한 문장에 섞으면 고칠 것이
    없는데 고치러 간다. 소요대수 탭이 열린 회차마다 둘 다 부른다. 목록도 사유로 갈라 각 줄의 표로
    싣고(표 행 수가 그 알림 건수다) 만든 목록을 돌려준다 — 큰 것은 화면이 본문에 남긴다
    (`render_oversized_lists`)."""
    if required_exclusions.empty or "제외사유" not in required_exclusions.columns:
        uncounted_pkg = pd.Series(False, index=required_exclusions.index)
    else:
        uncounted_pkg = required_exclusions["제외사유"].eq(PKG_UNCOUNTED_REASON)
    capacity_missing = required_exclusions.loc[~uncounted_pkg]
    capacity_list = (
        _exclusion_list(
            capacity_missing,
            title=REQUIRED_EXCLUSION_TITLE,
            dimensions=RESULT_DIMENSIONS,
            file_name=f"Capa_Required_Equipment_Exclusions_{file_suffix}.csv",
            key="download_required_exclusions_csv",
            display_order=display_order,
            labels=labels,
        )
        if not capacity_missing.empty
        else None
    )
    positive = (
        int(capacity_missing["부하량"].gt(0).sum()) if "부하량" in capacity_missing.columns else 0
    )
    capacity_table = capacity_list.table if capacity_list is not None else None
    capacity_page = f"이 탭 「{REQUIRED_EXCLUSION_TITLE}」"
    alerts.state(
        "ST-15",
        scope=scope.scope,
        content=[len(capacity_missing), positive],
        active=not capacity_missing.empty,
        text=(
            f"대당 Capa 가 없어 소요대수에서 뺀 경로 {len(capacity_missing):,}건 — 목록: "
            f"{ALARM_ROW_PLACE if capacity_table is not None else capacity_page}"
        ),
        full=(
            f"대당 Capa가 없어 소요대수 산출에서 {len(capacity_missing):,}건을 제외했습니다(부하량 "
            f"발생 {positive:,}건). 목록은 "
            + (
                alarm_table_place(REQUIRED_EXCLUSION_TITLE)
                if capacity_table is not None
                else capacity_page
            )
            + " 이고 제외사유 칸이 까닭입니다 — 그 경로의 대당 Capa 기준정보를 채우면 소요대수에 "
            "듭니다."
        ),
        scope_label=scope.label,
        tab=tab,
        tables=[capacity_table],
    )
    pkg_rows = required_exclusions.loc[uncounted_pkg]
    pkg_list = (
        _exclusion_list(
            pkg_rows,
            title=PKG_UNCOUNTED_TITLE,
            dimensions=RESULT_DIMENSIONS,
            file_name=f"Capa_Required_PKG_Uncounted_{file_suffix}.csv",
            key="download_required_pkg_uncounted_csv",
            display_order=display_order,
            labels=labels,
        )
        if not pkg_rows.empty
        else None
    )
    pkg_table = pkg_list.table if pkg_list is not None else None
    pkg_count = len(pkg_rows)
    alerts.state(
        "ST-21",
        scope=scope.scope,
        content=pkg_count,
        active=pkg_count > 0,
        text=f"소요기준 PKG 는 Buffer 로만 셉니다 — Core·Top·Dummy 등 {pkg_count:,}건 뺌",
        full=(
            f"소요기준 PKG 는 Buffer 로만 셉니다. Core·Top·Dummy 등 {pkg_count:,}건은 Buffer 에 "
            "쌓여 있어 소요대수에 넣지 않았습니다(규칙 — 고칠 것이 없습니다). 목록은 "
            + (
                alarm_table_place(PKG_UNCOUNTED_TITLE)
                if pkg_table is not None
                else f"이 탭 「{PKG_UNCOUNTED_TITLE}」"
            )
            + " 입니다."
        ),
        scope_label=scope.label,
        tab=tab,
        tables=[pkg_table],
    )
    return tuple(item for item in (capacity_list, pkg_list) if item is not None)
