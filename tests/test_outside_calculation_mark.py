# Purpose: 「계산 밖 n공정」 표지 · 풍선 글과 공정 하나의 계산 밖 소요기준 글을 잰다.

"""계산 밖 표지(`components/outside_calculation_mark.py`) — 설계 규칙 UI-TXT-04(숨은 데이터는 표지 +
풍선) · UI-TXT-08(없으면 아무것도) · UI-CON-02(「계산 밖」 한 이름) · UI-DAT-10(풍선은 표시명)."""

from __future__ import annotations

from capa_simulation.components.outside_calculation_mark import (
    OutsideCalculationMark,
    outside_calculation_mark,
    whole_outside_bases,
    whole_outside_basis,
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


def test_only_a_process_whose_routes_are_all_outside_names_its_basis() -> None:
    """공정 하나를 말하는 자리(공정 Capa 상세 ③ 판정 카드)는 경로가 모두 계산 밖인 공정에만
    소요기준 글을 받는다 — 둘이면 풍선과 같은 「BOX · PCB」. 경로 일부만 빠진 공정 · 목록에 없는
    공정은 None."""
    processes = (
        UnimplementedProcess(process="DEMO_BOX_A", bases=("BOX", "PCB"), whole=True),
        UnimplementedProcess(process="DEMO_MIX", bases=("BOX",), whole=False),
        UnimplementedProcess(process="DEMO_PCB_Z", bases=("PCB",), whole=True),
    )

    assert whole_outside_basis(processes, "DEMO_BOX_A") == "BOX · PCB"
    assert whole_outside_basis(processes, " DEMO_PCB_Z ") == "PCB"
    assert whole_outside_basis(processes, "DEMO_MIX") is None
    assert whole_outside_basis(processes, "DEMO_PKG") is None
    assert whole_outside_basis((), "DEMO_BOX_A") is None


def test_the_tile_picker_gets_the_outside_basis_of_each_option_by_its_original_key() -> None:
    """공정마다 단추가 서는 자리(HOME 공정 필터)는 선택지 전부에 같은 판정을 한 번에 건다 — 키는
    받은 원본 공정 글자 그대로이고 경로가 모두 계산 밖인 공정만 든다. 목록이 비면 빈 사전이다."""
    processes = (
        UnimplementedProcess(process="DEMO_BOX_A", bases=("BOX", "PCB"), whole=True),
        UnimplementedProcess(process="DEMO_MIX", bases=("BOX",), whole=False),
        UnimplementedProcess(process="DEMO_PCB_Z", bases=("PCB",), whole=True),
    )

    assert whole_outside_bases(
        processes, ["DEMO_PKG", "DEMO_BOX_A", "DEMO_MIX", " DEMO_PCB_Z"]
    ) == {
        "DEMO_BOX_A": "BOX · PCB",
        " DEMO_PCB_Z": "PCB",
    }
    assert whole_outside_bases((), ["DEMO_BOX_A"]) == {}
    assert whole_outside_bases(processes, []) == {}
