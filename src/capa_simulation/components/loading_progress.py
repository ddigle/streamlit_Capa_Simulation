# Purpose: 계산이 오래 걸리는 페이지가 본문에 진행 단계와 퍼센트를 띄우는 공용 표시기다.

"""본문 로딩 진행 표시기.

Streamlit 이 우상단에 띄우는 실행 표시는 작고 화면 밖에 있을 때가 많다. 30초가 걸리는지
멈춘 것인지 구분되지 않아 사람이 새로고침을 누른다. 본문 맨 위에 지금 어느 단계이고 몇
퍼센트인지 적어 그 판단을 대신한다.

단계 목록을 미리 선언한다. 호출부가 퍼센트 숫자를 직접 적으면 단계를 더하거나 뺄 때
누적값이 어긋나고, 그 어긋남은 화면에서만 드러난다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from streamlit.delta_generator import DeltaGenerator


@dataclass(frozen=True)
class LoadingStage:
    """한 단계와 그 단계를 끝냈을 때의 누적 진행률.

    `percent` 는 측정된 소요 시간의 비율에 맞춰 정한다. 단계 수로 균등 분할하면 실제로는
    한 단계가 대부분의 시간을 쓰는데도 막대가 빨리 찼다가 멈춰 선 것처럼 보인다.
    """

    label: str
    percent: int


class LoadingProgress:
    """선언한 단계를 차례로 넘기며 본문 진행 막대를 갱신한다.

    막대는 **직전 단계까지의 누적 퍼센트**와 **지금 하는 일의 이름**을 함께 적는다. 끝난
    양과 하는 일을 한 줄에서 읽게 하려는 것이다.
    """

    def __init__(self, placeholder: DeltaGenerator, stages: Sequence[LoadingStage]) -> None:
        if not stages:
            raise ValueError("진행 단계가 하나도 없습니다.")
        self._placeholder = placeholder
        self._stages = tuple(stages)
        self._index = 0
        self._closed = False
        self._render()

    def advance(self) -> None:
        """현재 단계를 끝내고 다음 단계로 넘어간다. 마지막 단계 뒤에는 표시를 지운다."""
        if self._closed:
            return
        self._index += 1
        if self._index >= len(self._stages):
            self.close()
            return
        self._render()

    def close(self) -> None:
        """진행 표시를 지운다. 오류로 화면을 멈출 때도 반드시 지나야 하는 자리다."""
        if self._closed:
            return
        self._closed = True
        self._placeholder.empty()

    def _render(self) -> None:
        stage = self._stages[self._index]
        completed = 0 if self._index == 0 else self._stages[self._index - 1].percent
        self._placeholder.progress(completed / 100, text=f"{stage.label} · {completed}%")
