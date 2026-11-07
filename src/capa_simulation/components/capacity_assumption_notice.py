# Purpose: 측정률 행이 없어 중립값으로 이어 간 건수를 한 문장으로 짓고 상태 알림으로 낸다.

"""**메운 것을 말하지 않으면 완화가 곧 조용한 오류다.**

`RQ_LOT_RATIO`·`RQ_WF_RATIO` 에 (경로 + 월) 행이 없으면 대당 Capa 는 중립값 1.0 으로
이어 간다(`unit_capacity._join_reference`). 예전에는 그 자리에서 `ValueError` 로 화면
전체가 멈췄는데, 어차피 부하량이 없어 빠질 행 하나 때문에 그 값을 고칠 편집기조차 못
여는 쪽이 더 나빴다.

대신 **오차의 방향이 실제 측정률에 달려 있다.** 측정률은 대당 Capa 식의 분모라, 실제가
1 보다 작은 경로에 1.0 을 쓰면 대당 Capa 과소 → 소요대수 과대 → **확보율 과소**(보수 쪽)이고,
1 보다 큰 경로에서만 확보율 과대(낙관 쪽)다. 어느 쪽이든 보는 사람이 모르면 숫자를 그대로
믿는다.

그래서 이 한 줄은 장식이 아니라 완화의 **조건**이다. 계산이 계속되는 대신 무엇을 가정했는지 같은
화면에서 말한다 — 2026-11-03(결정 보드 D2 (나))부터 자리에 그리지 않고 상태 알림 `HM-02` 로 낸다.
가정이 바뀔 때만 오른쪽 아래 알림창에 뜨고 Alarm 에 남는다. HOME 과 산출 결과 대당 Capa 가 같은 코드
· 같은 범위(활성 리비전 내용 — 시나리오 전체 기준이라 조회기간은 범위에 넣지 않는다)라 한 화면에서
본 가정은 다른 화면에서 다시 뜨지 않는다. 고칠 표는 기준 정보에 있어 Alarm 줄의 화면 칸과 「그
화면으로」 가 기준 정보이고(`goto`, 설계 규칙 UI-NTF-02 — 표가 하나면 그 종류 단추까지 연다), 어느
화면의 일인지는 전문 첫머리가 말한다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from capa_simulation import alerts
from capa_simulation.components.state_alerts import TAB_PATH, AlertScope
from capa_simulation.navigation import REFERENCE_DATA
from capa_simulation.page_tabs_state import tab_label
from capa_simulation.services.month_columns import iso_month_text
from capa_simulation.services.unit_capacity import CapacityAssumptions

# 표 이름을 화면 라벨로. 사용자가 여는 탭 이름과 같아야 어디를 고칠지 바로 안다.
_TABLE_LABELS: Mapping[str, str] = {
    "RQ_LOT_RATIO": "Lot측정률",
    "RQ_WF_RATIO": "WF측정률",
}
# 문장에 적는 달의 수. 넘으면 「외 N개월」로 줄인다.
MONTH_LIST_LIMIT = 6


def assumption_message(
    assumed: Mapping[str, int],
    months: Mapping[str, Sequence[int]] | None = None,
) -> str:
    """가정 건수와 그 달을 한 문장으로. 빈 값이면 빈 문자열이라 호출부가 분기를 줄인다.

    **시나리오 전체 기간 기준이다.** 대당 Capa 는 전체 기간을 한 번에 계산하므로 조회기간
    밖의 달도 센다. 그래서 달을 함께 적는다 — 건수만 말하면 어느 달 칸을 채울지 다시 찾아야
    하고, 보는 기간에 없는 달이면 왜 떴는지도 모른다.
    """
    parts = []
    for table, count in assumed.items():
        if not count:
            continue
        part = f"{_TABLE_LABELS.get(table, table)} {count:,}건"
        table_months = tuple((months or {}).get(table, ()))
        if table_months:
            part += f"({_month_list(table_months)})"
        parts.append(part)
    if not parts:
        return ""
    return (
        "측정률 행이 없어 **중립값 1.0 으로 계산한 경로가 있습니다**(시나리오 전체 기준) — "
        f"{' · '.join(parts)}. "
        "측정률은 대당 Capa 의 분모라 실제가 1 보다 작으면 **확보율이 실제보다 낮게**, "
        "1 보다 크면 높게 나옵니다. "
        "기준 정보 페이지의 해당 표에서 그 달 칸을 채우면 정확해집니다."
    )


def _month_list(months: Sequence[int], limit: int = MONTH_LIST_LIMIT) -> str:
    """앞 몇 달만 적고 나머지는 개수로 줄인다. 달이 많으면 문장이 표가 된다."""
    shown = ", ".join(iso_month_text(month) for month in months[:limit])
    rest = len(months) - limit
    return f"{shown} 외 {rest}개월" if rest > 0 else shown


def assumption_short(assumed: Mapping[str, int]) -> str:
    """알림창 짧은 글 — 무엇을(표 · 건수) 어디서(기준 정보) 고치는지."""
    parts = [
        f"{_TABLE_LABELS.get(table, table)} {count:,}건"
        for table, count in assumed.items()
        if count
    ]
    return f"측정률 빈 경로를 1.0 으로 계산({' · '.join(parts)}) — 기준 정보 그 표에서 채움"


def _table_to_open(assumed: Mapping[str, int]) -> str:
    """「그 화면으로」 가 고를 기준 정보 종류 단추 글 — 표가 둘이면 어느 쪽을 열지 정할 수 없어
    고르지 않는다."""
    tables = [table for table, count in assumed.items() if count]
    return _TABLE_LABELS.get(tables[0], "") if len(tables) == 1 else ""


def render_capacity_assumption_notice(
    assumptions: CapacityAssumptions, *, scope: AlertScope, tab: str = ""
) -> None:
    """측정률 가정 상태 알림(`HM-02`) — 이 조건을 보는 회차마다(가정이 없어도) 부른다. 자리에는
    그리지 않는다. `scope` 는 시나리오 전체 기간 범위(`state_alerts.simulation_scope(활성)`), `tab`
    은 그 화면 안 탭 이름이다 — 줄이 기준 정보를 가리키므로 전문 첫머리에만 든다."""
    message = assumption_message(assumptions.counts, assumptions.months)
    where = TAB_PATH.join(part for part in (alerts.current_page()[0], tab) if part)
    full = f"{where} — {alerts.plain_text(message)}" if where else alerts.plain_text(message)
    alerts.state(
        "HM-02",
        scope=scope.scope,
        content={
            table: [count, list(assumptions.months.get(table, ()))]
            for table, count in sorted(assumptions.counts.items())
            if count
        },
        active=bool(message),
        text=assumption_short(assumptions.counts) if message else None,
        full=full if message else None,
        scope_label=scope.label,
        tab=_table_to_open(assumptions.counts),
        goto=(tab_label(REFERENCE_DATA), REFERENCE_DATA.href),
    )
