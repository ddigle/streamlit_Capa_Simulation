# Purpose: 계산에서 빠진 BOX · PCB 소요기준 공정을 알리는 「계산 밖 n공정」 표지와 풍선 글을 짓는다.

"""계산 밖 표지 — 표 제목 줄 부가 설명 칸에 다는 짧은 글과 풍선(정식판 1.0 마감 2번 C — 2026-11-24
사용자 「권장안 그대로」: PCB 산식이 아니라 표지).

소요기준 BOX · PCB 경로는 산식이 정해질 때까지 대당 Capa · 소요대수 · 확보율 계산에서 빠진다
(`frame_contracts.UNIMPLEMENTED_BASES` — 제외가 아니라 추가 예정, AGENTS 11장). 그 공정은 표에 줄이
없거나 확보율 칸이 비어 까닭이 보이지 않는다. 그래서 조회기간에 그런 공정이 있으면 표 제목 줄에 짧은
표지를 달고 까닭 · 공정은 풍선이 말한다 — 숨은 데이터 안내는 칸 머리 표지 + 풍선(설계 규칙
UI-TXT-04)이다. 사용자가 고칠 수 없는데 늘 서는 상태라 경고 알림(`alerts.state`)으로 세우지 않는다
(UI-NTF-05). 그런 공정이 없으면 아무것도 짓지 않는다(UI-TXT-08).

- 표지 낱말은 「계산 밖」 하나다(UI-CON-02). 「추가 예정」 은 풍선 · Guide 가 까닭으로 말한다.
- 풍선 둘째 줄은 공정 표시명(UI-DAT-10 — 마크다운으로 그려도 글자 그대로 보이게 막는다)과 빠진
  소요기준이다. 조회기간 안 경로 일부만 빠진 공정(`whole` 거짓 — 한 공정 한 소요기준을 어긴 원천)은
  「— 일부 경로」 를 붙인다 — 그 공정은 남은 경로로 계산된다.
- 차례는 부르는 쪽이 준 원본 공정 차례(표시순서)이고 표시명은 차례를 정한 뒤에 붙인다. 차례에 없는
  공정은 받은 차례 그대로 뒤에 선다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Final, NamedTuple

from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.services.frame_contracts import UnimplementedProcess

# 표지 낱말 — 산출 결과 표 제목 줄 · 다른 화면의 계산 밖 표지가 같이 쓴다.
OUTSIDE_CALCULATION: Final = "계산 밖"
# 표 제목 줄 부가 설명 칸의 표지(값 — 조건이 있을 때만 선다).
MARK: Final = f"{OUTSIDE_CALCULATION} {{n}}공정"
# 풍선 첫 줄 — 까닭.
REASON: Final = (
    "소요기준 BOX · PCB 공정은 산식이 정해질 때까지 대당 Capa · 소요대수 · 확보율 계산에 넣지 "
    "않습니다(추가 예정)."
)
# 풍선 둘째 줄 머리와 경로 일부만 빠진 공정의 꼬리.
PERIOD_HEAD: Final = "이 기간: "
PARTIAL: Final = " — 일부 경로"
# 풍선에 이름을 싣는 공정 수 — 넘으면 「외 n공정」.
NAME_LIMIT: Final = 10


class OutsideCalculationMark(NamedTuple):
    """표 제목 줄 부가 설명 칸에 넘기는 표지 글(`caption`)과 그 풍선 글(`help`)."""

    caption: str
    help: str


def outside_calculation_mark(
    processes: Sequence[UnimplementedProcess],
    *,
    label: Callable[[object], str],
    order: Sequence[str] = (),
) -> OutsideCalculationMark | None:
    """조회기간 안 계산 밖 공정(`simulation_cache.get_unimplemented_basis_processes`)의 표지와 풍선.

    `label` 은 원본 공정명 → 화면 표시명(`ProcessLabels.label`), `order` 는 표시순서로 늘어놓은 원본
    공정명이다. 계산 밖 공정이 없으면 None 이다 — 부르는 쪽은 부가 설명을 넘기지 않는다.
    """
    if not processes:
        return None
    rank = {name: index for index, name in enumerate(order)}
    ordered = sorted(processes, key=lambda item: rank.get(item.process, len(rank)))
    names = [
        f"{literal_markdown(label(item.process))} "
        f"({' · '.join(item.bases)}{'' if item.whole else PARTIAL})"
        for item in ordered[:NAME_LIMIT]
    ]
    rest = len(ordered) - NAME_LIMIT
    line = PERIOD_HEAD + " · ".join(names) + (f" 외 {rest}공정" if rest > 0 else "")
    return OutsideCalculationMark(caption=MARK.format(n=len(ordered)), help=f"{REASON}\n\n{line}")
