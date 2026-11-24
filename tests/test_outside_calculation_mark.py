# Purpose: 「계산 밖 n공정」 표지와 풍선 글의 공정 차례 · 표시명 · 일부 경로 · 이름 상한을 잰다.

"""계산 밖 표지(`components/outside_calculation_mark.py`) — 설계 규칙 UI-TXT-04(숨은 데이터는 표지 +
풍선) · UI-TXT-08(없으면 아무것도) · UI-CON-02(「계산 밖」 한 이름) · UI-DAT-10(풍선은 표시명)."""

from __future__ import annotations

from capa_simulation.components.outside_calculation_mark import (
    OutsideCalculationMark,
    outside_calculation_mark,
)
from capa_simulation.services.frame_contracts import UnimplementedProcess

REASON = (
    "소요기준 BOX · PCB 공정은 산식이 정해질 때까지 대당 Capa · 소요대수 · 확보율 계산에 넣지 "
    "않습니다(추가 예정)."
)
LABELS = {"DEMO_BOX_A": "포장", "DEMO_MIX": "DEMO_MIX*2"}


def _label(value: object) -> str:
    return LABELS.get(str(value), str(value))


def test_no_outside_process_builds_no_mark() -> None:
    assert outside_calculation_mark((), label=_label) is None


def test_the_mark_counts_processes_and_the_balloon_names_them_in_display_order() -> None:
    """표지는 공정 수, 풍선은 까닭 + 표시순서 차례의 표시명 · 빠진 소요기준이다. 경로 일부만 빠진
    공정은 「— 일부 경로」 를 붙이고, 표시명의 마크다운 글자는 막는다. 차례에 없는 공정은 받은
    차례 그대로 뒤에 선다."""
    processes = (
        UnimplementedProcess(process="DEMO_BOX_A", bases=("BOX", "PCB"), whole=True),
        UnimplementedProcess(process="DEMO_MIX", bases=("BOX",), whole=False),
        UnimplementedProcess(process="DEMO_PCB_Z", bases=("PCB",), whole=True),
        UnimplementedProcess(process="DEMO_PCB_Y", bases=("PCB",), whole=True),
    )

    mark = outside_calculation_mark(processes, label=_label, order=("DEMO_MIX", "DEMO_BOX_A"))

    assert mark == OutsideCalculationMark(
        caption="계산 밖 4공정",
        help=(
            f"{REASON}\n\n이 기간: DEMO\\_MIX\\*2 (BOX — 일부 경로) · 포장 (BOX · PCB) · "
            "DEMO\\_PCB\\_Z (PCB) · DEMO\\_PCB\\_Y (PCB)"
        ),
    )


def test_the_balloon_names_ten_processes_and_counts_the_rest() -> None:
    processes = tuple(
        UnimplementedProcess(process=f"BOX{index:02d}", bases=("BOX",), whole=True)
        for index in range(12)
    )

    mark = outside_calculation_mark(processes, label=_label)

    assert mark is not None
    assert mark.caption == "계산 밖 12공정"
    names = " · ".join(f"BOX{index:02d} (BOX)" for index in range(10))
    assert mark.help == f"{REASON}\n\n이 기간: {names} 외 2공정"
