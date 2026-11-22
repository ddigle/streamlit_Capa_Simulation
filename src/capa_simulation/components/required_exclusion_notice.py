# Purpose: 소요대수에 들지 않은 수요·제외 기준정보의 상태 알림과 계획 쪽 제외 목록을 낸다.

"""**0 으로 접은 것을 말하지 않으면 확보율이 조용히 낙관 쪽으로 틀어진다.**

부하량에서 빠진 계획(기준정보 없음), 생산수량이 비어 계획 없음으로 본 계획, `RQ_REQB` 경로에 닿지
않은 계획 부하, 부하가 붙었는데 대당 Capa 가 없어 뺀 경로, 부하 예외 바탕이 없어 뺀 경로 — 모두
계산을 멈추지 않고 이어 가는 대신
그 수요가 어느 공정의 소요대수에도 들지 않는다. 그만큼 소요대수가 작아져 확보율이 실제보다 높게
나올 수 있다(빈 생산수량이 정말 계획 없음이면 그대로다). 그 제품에 그 소요기준·WF 구분 경로가
아예 없어 닿지 않은 부하(EDP-TSV 의 PKG 처럼 규칙상 쓰지 않는 조합)는 세지도 그리지도 않는다 — 세면
모두에게 늘 뜨는 경고가 되고, 확보율이 높게 나온다는 말도 그 경우 사실이 아니다.

그래서 같은 문장을 여러 자리에서 쓴다(HOME 에는 띄우지 않는다 — 2026-10-19 사용자 요청). 리비전
저장·공식 발행 검사는 허락하면서 경고, 공식버전 자동 갱신의 발행은 막지 않고 실행 기록 사유 끝에
붙인다(`auto_official_update_runner` — 「지금 실행」 결과는 화면 발행과 같이 성공 알림 밑의 경고로
따로 띄운다). 모두 시나리오 전체 기간이다. 경로 쪽 두 까닭(대당 Capa 없음 · 부하 예외 바탕
없음)은 고칠 곳이 달라(대당 Capa 기준정보 · 수율과 Chip 구성) 문장 안에서도 갈라
센다(`basis_missing_routes`). 그 저장 리비전 하나의 같은 셈
(`required_exclusion_counts`)을 같은 범위로 묶음 수와 행으로 보이는 자리가 시나리오 관리 › 목록
관리 「점검」 칸이라 그 경고의 목록 자리 · 「그 화면으로」 도 그 칸이다(`REQUIRED_LIST_NOTE` ·
`REQUIRED_TAB_GOTO` — 2026-11-11 입력 점검 검토 보드 F4 (나)). 산출 결과 소요대수 탭의 목록은
조회기간이라 수가 다를 수 있다. 경고를 내는 자리는 `required_check_target` 으로 그 리비전을 경고
줄에 실어, 누를 때마다 칸이 그 줄의 리비전을 고른 채 서게 한다(2026-11-11 다음 배포 물음 보드 F4 뒤
(a) — `services/revision_input_check.py` 는 이 문장을 쓰지 않는다).

계획을 고친 사람이 「고쳤는데 수가 안 바뀐다」 고 헷갈리지 않게 두 자리에도 같은 문장을 띄운다 —
PKG PLAN 적용 알림 칸 맨 아래(시나리오 전체 기간, 적용 알림이 서는 회차)와 Static Capa 현황 요약
맨 위(그 화면의 조회기간 — 미달 건수·필요대수가 그만큼 작게 나올 수 있다). 두 자리는 **계획 쪽
건수만** 싣는다(`plan_side_counts`) — 경로 쪽(대당 Capa · 부하 예외 바탕이 없어 뺀 부하 경로)은
기준정보 몫이라 계획을 고치지 않아도 늘 있을 수 있고(사내 리뷰 `202610271800` 보충 8-2X 에서 0 이
아니었다), 그대로 실으면 적용할 때마다·현황 요약을 열 때마다 서는 경고가 된다(HOME 에서 이 줄을 뺀
2026-10-19 결정과 같은 까닭). 경로 쪽은 위 자리들(저장·발행 검사 · 목록 관리 「점검」)이 그대로
말한다.

**화면 자리는 상태 알림이다**(2026-11-03 결정 보드 D2 (나)). Static Capa · 산출 결과 · 생산 계획은
이 경고를 자리에 그리지 않고 `alerts.state` 로 낸다 — 내용(건수)이 바뀔 때만 오른쪽 아래 알림창에
뜨고 Alarm 에 남으며 조건이 사라지면 「해소」 가 선다. 짧은 글은 무엇이(건수) 어디에(목록 자리)
있는지를 말한다. 코드는 `ST-01`(계획 쪽 · 조회기간 — Static Capa 와 산출 결과 소요대수 탭이 같은
코드 · 같은 범위라 한쪽에서 본 것은 다른 쪽에서 다시 뜨지 않는다), `ST-04`(PKG PLAN 적용 뒤 ·
시나리오 전체 기간), `ST-14`(대당 Capa 제외 기준정보), `ST-15`(대당 Capa 가 없어 소요대수에서 뺀
경로), `ST-21`(PKG 의 Buffer 밖 행 — 규칙이라 알림 단계), `ST-22`(부하 예외 바탕이 없어
소요대수에서 뺀 경로 — 고칠 곳이 수율 · Chip 구성이라 `ST-15` 와 가른다)다.

**목록도 그 알림의 Alarm 줄 표다**(2026-11-05 사용자 요청(검수표) — 「Alarm 안 표로 이동」).
조건의 내역이라 본문 접힘에 두지 않는다(설계 규칙 UI-TXT-04) — 줄의 「… 보기」 가 펼치고 CSV 를
내려받는다(화면은 표시명, 파일은 원본). 표 하나는 그 알림의 건수와 같은 행이다 — `ST-15` ·
`ST-21` · `ST-22` 는 사유로 가르고, `ST-01` · `ST-04` 는 고칠 곳이 다른 계획 쪽 두 목록을 두 표로
싣는다. 표가 알림에 싣기에 크면(`alerts.TABLE_ROW_LIMIT`) 그 목록만 산출 결과 소요대수 탭 본문
펼침에 남는다(`render_oversized_lists`). 고칠 곳은 까닭 칸(`누락 기준정보` · `제외사유`) 머리 풍선과
Guide 가 말한다(설계 규칙 UI-TXT-01 · 02 · 03).
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping, Sequence
from typing import Final, Literal, NamedTuple

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.edit_file_tail import edited_file_name
from capa_simulation.components.exclusion_table import exclusion_export, render_exclusion_table
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.scenario_list_state import (
    CHECK_TARGET_KIND,
    LIST_MODE,
    SIDE_CHECK,
)
from capa_simulation.components.scenario_management_tabs import CAPA_SCENARIO_TAB_NAME
from capa_simulation.components.state_alerts import (
    ALARM_ROW_PLACE,
    AlertScope,
    alarm_table_place,
    alert_table,
)
from capa_simulation.navigation import SCENARIO_MANAGEMENT
from capa_simulation.page_tabs_state import tab_label
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
from capa_simulation.services.route_load_exceptions import ROUTE_LOAD_BASIS_MISSING_REASON
from capa_simulation.session_slot import SessionSlot

# 문장의 범위 말. 저장·발행 검사와 PKG PLAN 적용 알림은 시나리오 전체 기간,
# Static Capa 현황 요약은 그 화면이 보는 조회기간으로 본다.
FULL_SCOPE = "시나리오 전체 기간"
PERIOD_SCOPE = "조회기간"
# 문장의 머리. 자동 갱신의 발행 줄 뒤에 이어 적힌 이 경고를 실행 기록 사유에서 다시 가를 때도 쓴다
# (`auto_official_update_runner.split_published_reason`).
UNCOUNTED_DEMAND_LEAD = "소요대수에 들지 않은 수요가 있습니다"
# 표가 커서 본문에 남은 계획 쪽 목록이 서는 자리 — 알림 짧은 글이 「어디서 보는지」 로 적는다.
REQUIRED_LIST_PLACE = "산출 결과 › 소요대수"
# 문장의 끝 — 목록을 어디서 보는지. 저장 · 지정 검사와 자동 갱신 기록의 경고는 같은 리비전 · 같은
# 범위(시나리오 전체 기간)로 묶음을 보이는 목록 관리 「점검」 칸을 가리킨다(2026-11-11 입력 점검
# 검토 보드 F4 (나)). 상태 알림(`ST-01` · `ST-04`)은 그 줄의 표나 산출 결과 소요대수 탭이다.
REQUIRED_LIST_NOTE = "목록은 시나리오 관리 → 목록 관리 「점검」 칸(같은 리비전 · 전체 기간)입니다."
REQUIRED_LIST_NOTE_THIS_ROW = "목록은 Alarm 의 이 줄에 딸린 표입니다."
REQUIRED_LIST_NOTE_ON_PAGE = "목록은 산출 결과 → 소요대수 탭에 있습니다."
# 저장 · 지정 · 복제 · 「지금 실행」 뒤의 이 경고(사건 알림)가 「그 화면으로」 로 열 자리 — 시나리오
# 관리 › Capa 시나리오 › 목록 관리 › 「점검」(이름, 주소, 탭 길 — 알림 칸이 탭 · 전환 단추를 차례로
# 누른다). 리비전은 경고 줄이 들고 간다(`required_check_target`).
REQUIRED_TAB_GOTO: Final = (
    tab_label(SCENARIO_MANAGEMENT),
    SCENARIO_MANAGEMENT.href,
    f"{CAPA_SCENARIO_TAB_NAME} › {LIST_MODE} › {SIDE_CHECK}",
)
# 제외 목록(Alarm 줄의 표) 이름. 2026-11-02 · 11-05 사용자 요청(검수표) 전에는 탭 본문 펼침이었다.
CAPACITY_EXCLUSION_TITLE = "제외 기준정보"
REQUIRED_EXCLUSION_TITLE = "소요대수 제외 기준정보"
PKG_UNCOUNTED_TITLE = "PKG Buffer 밖 행"
ROUTE_BASIS_MISSING_TITLE = "부하 예외 바탕 없는 경로"
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


def required_check_target(
    scenario_id: str | None, revision_id: str | None
) -> alerts.GotoTarget | None:
    """「소요대수에 들지 않은 수요」 경고(저장 · 지정 · 복제 · 「지금 실행」)가 들고 갈 대상 —
    경고가 말하는 리비전. 갈 곳(`REQUIRED_TAB_GOTO`)과 함께 `queue_flash(goto=, target=)` 에 준다.
    세션에는 아무것도 적지 않는다 — 그 줄의 「그 화면으로」 가 「점검」 칸에 닿았을 때만 알림 칸이
    서버에 보낸다(`scenario_list_state.queue_check_target`). 쓴 리비전을 모르면(빠른 둘째 누름이 첫
    쓰기를 이어받은 회차 따위) None — 갈 곳만 남고 「점검」 칸의 고름은 그대로다."""
    if not (scenario_id and revision_id):
        return None
    return alerts.GotoTarget(kind=CHECK_TARGET_KIND, scenario=scenario_id, revision=revision_id)


def plan_side_counts(counts: RequiredExclusionCounts) -> RequiredExclusionCounts:
    """계획 쪽 건수만 남긴다(경로 쪽 `excluded_routes` · `basis_missing_routes` 는 0) — PKG PLAN
    적용 알림·Static Capa 현황 요약처럼 「계획을 고쳤는데 수가 안 바뀐다」 를 말하는 자리가
    쓴다(모듈 설명)."""
    return counts._replace(excluded_routes=0, basis_missing_routes=0)


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
    capacity_routes = counts.excluded_routes - counts.basis_missing_routes
    if capacity_routes:
        parts.append(f"대당 Capa 가 없어 뺀 부하 경로 {capacity_routes:,}건")
    if counts.basis_missing_routes:
        parts.append(f"부하 예외 바탕 없음으로 뺀 부하 경로 {counts.basis_missing_routes:,}건")
    if not parts:
        return ""
    message = (
        f"{UNCOUNTED_DEMAND_LEAD}({scope}) — {' · '.join(parts)}. "
        "그만큼 소요대수가 작게, **확보율이 실제보다 높게** 나올 수 있습니다."
    )
    return f"{message} {list_note}"


# 제외 목록 알림 표(내보내기 표 → 알림 표) 기억 — 산출 결과는 탭 조건을 바꾸는 회차마다 같은 목록의
# 칸 차례 · 알림 표를 다시 지었다(합성 표본 소요대수 탭 회차의 약 15ms — 샘플 관측). 부르는 쪽이
# 목록 내용을 정하는 키(`memo` — 시나리오 결과 키 · 표시순서 지문)를 줄 때만 기억하고, 키는 거기에
# 목록 이름 · 파일 이름(고침 꼬리 포함) · 공정 표시명 판을 더한 것이다. 알림을 내는
# 일(`alerts.state`)은 기억하지 않는다 — 회차마다 제 이벤트 칸을 쓴다.
EXCLUSION_MEMO_KEY: Final = "required_exclusion_table_memo"
EXCLUSION_MEMO: Final = SessionSlot(EXCLUSION_MEMO_KEY, dict, dict)
EXCLUSION_MEMO_LIMIT: Final = 8


def remembered_alert_table(
    memo: Hashable | None,
    *,
    title: str,
    file_name: str,
    labels: ProcessLabels,
    build: Callable[[], alerts.AlertTable | None],
) -> alerts.AlertTable | None:
    """제외 목록의 알림 표 — `memo` 가 있으면 (memo, 목록 이름, 파일 이름, 표시명 판) 키로 이 세션에
    기억한 것을 꺼내고(없으면 지어 넣는다 — 오래된 것부터 `EXCLUSION_MEMO_LIMIT` 넘게는 버린다),
    없으면 늘 짓는다. 꺼낸 표는 겉 dict 를 새로 낸다(받은 쪽이 칸을 더해도 기억은 그대로다)."""
    if memo is None:
        return build()
    key = (memo, title, file_name, labels.version)
    held = EXCLUSION_MEMO.setdefault()
    if key in held:
        (table,) = held.pop(key)
    else:
        table = build()
        while len(held) >= EXCLUSION_MEMO_LIMIT:
            held.pop(next(iter(held)))
    held[key] = (table,)
    return None if table is None else table.copy()


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
    memo: Hashable | None = None,
) -> ExclusionList:
    helps = column_help or {}
    # 저장하지 않은 고침이 있으면 파일 이름에 고침 꼬리(`edit_file_tail`) — 본문 펼침 · Alarm 표가
    # 같은 이름을 쓴다.
    file_name = edited_file_name(file_name)
    return ExclusionList(
        title,
        frame,
        dimensions,
        file_name,
        key,
        helps,
        remembered_alert_table(
            memo,
            title=title,
            file_name=file_name,
            labels=labels,
            build=lambda: alert_table(
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
        ),
    )


def plan_exclusion_lists(
    load_exclusions: object,
    unrouted_loads: object,
    *,
    display_order: DisplayOrderInput,
    labels: ProcessLabels,
    file_suffix: str,
    memo: Hashable | None = None,
) -> tuple[ExclusionList, ...]:
    """계획 쪽 목록 둘(있는 것만) — 부하량에서 빠진 계획, 경로에 닿지 않은 계획 부하. 표는
    `alert_uncounted_demand(lists=…)` 가 싣는다. 입력은 프레임 또는 없음이다(결과 `attrs` 에서 꺼낸
    값). 고칠 곳은 까닭 칸 머리 풍선(`LOAD_EXCLUSION_HELP` · `UNROUTED_HELP`)이다.

    경로 쪽 제외(`REQUIRED_EXCLUSION_TITLE`)와 따로 둔다. 고칠 곳이 다르다 — 이쪽은 계획에 맞는
    수율·Chip 구성·경로가 없는 것이라 계획이나 그 기준정보를, 경로 쪽은 대당 Capa 기준정보를 본다.

    경로에 닿지 않은 부하는 건수와 같은 행(`counted_unrouted_loads`)만 싣는다. 규칙상 쓰지 않는
    조합(EDP-TSV 의 PKG 처럼 그 제품에 그 소요기준·WF 구분 경로가 없는 것)은 고칠 것이 없어 싣지
    않는다 — 실으면 늘 있는 목록이 되어 정작 고칠 행이 묻힌다.

    `memo` 는 두 목록 내용을 정하는 키다(주면 알림 표를 기억한다 — `remembered_alert_table`).
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
                memo=memo,
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
                    memo=memo,
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
        # 지문 내용은 계획 쪽 세 수와 경로 쪽 합(늘 0) 네 칸이다 — 경로 쪽 부분 수
        # (`basis_missing_routes`)는 합에 든 수라 넣지 않는다.
        content=[plan.excluded_plans, plan.blank_plans, plan.unrouted_loads, plan.excluded_routes],
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
    memo: Hashable | None = None,
) -> tuple[ExclusionList, ...]:
    """소요대수 산출에서 뺀 경로 — 대당 Capa 가 없는 것(`ST-15`, 대당 Capa 기준정보를 고칠 일),
    PKG 의 Buffer 밖 행(`ST-21`, 규칙대로 세지 않은 것 — 고칠 것이 없다), 부하 예외 바탕이 없는
    것(`ST-22`, 수율 · Chip 구성을 고치거나 겹친 원천을 다시 등록할 일). 사유를 한 문장에 섞으면
    고칠 것이 없는데 고치러 가거나 다른 표를 고치러 간다. 소요대수 탭이 열린 회차마다 셋 다
    부른다. 목록도 사유로 갈라 각 줄의 표로 싣고(표 행 수가 그 알림 건수다) 만든 목록을 돌려준다 —
    큰 것은 화면이 본문에 남긴다(`render_oversized_lists`). `memo` 는 `required_exclusions` 내용을
    정하는 키다(주면 알림 표를 기억한다)."""
    if required_exclusions.empty or "제외사유" not in required_exclusions.columns:
        uncounted_pkg = pd.Series(False, index=required_exclusions.index)
        basis_missing = pd.Series(False, index=required_exclusions.index)
    else:
        uncounted_pkg = required_exclusions["제외사유"].eq(PKG_UNCOUNTED_REASON)
        basis_missing = required_exclusions["제외사유"].eq(ROUTE_LOAD_BASIS_MISSING_REASON)
    capacity_missing = required_exclusions.loc[~uncounted_pkg & ~basis_missing]
    capacity_list = (
        _exclusion_list(
            capacity_missing,
            title=REQUIRED_EXCLUSION_TITLE,
            dimensions=RESULT_DIMENSIONS,
            file_name=f"Capa_Required_Equipment_Exclusions_{file_suffix}.csv",
            key="download_required_exclusions_csv",
            display_order=display_order,
            labels=labels,
            memo=memo,
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
            memo=memo,
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
    basis_rows = required_exclusions.loc[basis_missing]
    basis_list = (
        _exclusion_list(
            basis_rows,
            title=ROUTE_BASIS_MISSING_TITLE,
            dimensions=RESULT_DIMENSIONS,
            file_name=f"Capa_Required_Route_Exception_Basis_{file_suffix}.csv",
            key="download_required_route_basis_csv",
            display_order=display_order,
            labels=labels,
            memo=memo,
        )
        if not basis_rows.empty
        else None
    )
    basis_table = basis_list.table if basis_list is not None else None
    basis_count = len(basis_rows)
    basis_page = f"이 탭 「{ROUTE_BASIS_MISSING_TITLE}」"
    alerts.state(
        "ST-22",
        scope=scope.scope,
        content=basis_count,
        active=basis_count > 0,
        text=(
            f"부하 예외 바탕 없음 {basis_count:,}건 — 목록: "
            f"{ALARM_ROW_PLACE if basis_table is not None else basis_page}"
        ),
        full=(
            "부하 예외 산식의 바탕(Buffer Wafer 부하 · Core 구분_Chip)이 없거나 한 키에 둘이라 "
            f"소요대수 산출에서 {basis_count:,}건을 제외했습니다. 목록은 "
            + (
                alarm_table_place(ROUTE_BASIS_MISSING_TITLE)
                if basis_table is not None
                else basis_page
            )
            + " 입니다 — 그 제품의 수율 · Chip 구성(Buffer 행 · Core 구분_Chip)을 채우면 "
            "소요대수에 듭니다. 수율 · Chip 구성에 그 제품의 같은 WF 구분이 두 표기(대소문자만 "
            "다름)로 있으면 원천을 다시 등록합니다 — 목록의 WF 구분은 경로 쪽 표기라 겹침이 "
            "보이지 않습니다."
        ),
        scope_label=scope.label,
        tab=tab,
        tables=[basis_table],
    )
    return tuple(item for item in (capacity_list, pkg_list, basis_list) if item is not None)
