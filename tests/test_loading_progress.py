# Purpose: 본문 로딩 진행 표시기가 누적 퍼센트와 단계 이름을 어떻게 넘기는지 고정한다.

from typing import Any

import pytest

from capa_simulation.components.loading_progress import LoadingProgress, LoadingStage

STAGES = (
    LoadingStage("첫 단계", 20),
    LoadingStage("둘째 단계", 70),
    LoadingStage("셋째 단계", 100),
)


class _RecordingPlaceholder:
    """`st.empty()` 자리에 넣는 기록용 대역. 호출 순서를 그대로 남긴다."""

    def __init__(self) -> None:
        self.calls: list[tuple[float, str]] = []
        self.emptied = 0

    def progress(self, value: float, text: str = "") -> None:
        self.calls.append((value, text))

    def empty(self) -> None:
        self.emptied += 1


def _progress() -> tuple[LoadingProgress, _RecordingPlaceholder]:
    placeholder = _RecordingPlaceholder()
    return LoadingProgress(_as_placeholder(placeholder), STAGES), placeholder


def _as_placeholder(recorder: _RecordingPlaceholder) -> Any:
    """타입만 맞춰 넘긴다. 표시기는 `progress`·`empty` 두 가지만 쓴다."""
    return recorder


def test_the_bar_shows_finished_percent_next_to_the_running_stage() -> None:
    """막대는 끝난 양을 보이고 글자는 지금 하는 일을 적는다. 둘을 한 줄에서 읽게 한다."""
    progress, placeholder = _progress()

    progress.advance()
    progress.advance()

    assert placeholder.calls == [
        (0.0, "첫 단계 · 0%"),
        (0.2, "둘째 단계 · 20%"),
        (0.7, "셋째 단계 · 70%"),
    ]
    assert placeholder.emptied == 0


def test_advancing_past_the_last_stage_clears_the_bar() -> None:
    """마지막 단계까지 넘기면 스스로 사라진다. 100% 막대를 남겨 두지 않는다."""
    progress, placeholder = _progress()

    for _ in range(len(STAGES)):
        progress.advance()

    assert placeholder.emptied == 1
    # 닫힌 뒤의 호출은 아무것도 그리지 않는다. 오류 경로가 close() 를 한 번 더 부른다.
    progress.advance()
    progress.close()
    assert placeholder.emptied == 1
    assert len(placeholder.calls) == len(STAGES)


def test_closing_early_removes_the_bar_so_an_error_is_not_read_under_it() -> None:
    """계산이 예외로 끝나면 멈춰 선 막대가 오류 문구 위에 남으면 안 된다."""
    progress, placeholder = _progress()

    progress.advance()
    progress.close()

    assert placeholder.emptied == 1
    assert placeholder.calls[-1] == (0.2, "둘째 단계 · 20%")


def test_an_empty_stage_list_is_rejected() -> None:
    """단계가 없으면 퍼센트를 셀 근거가 없다. 조용히 0% 막대를 그리지 않는다."""
    with pytest.raises(ValueError, match="진행 단계"):
        LoadingProgress(_as_placeholder(_RecordingPlaceholder()), ())
