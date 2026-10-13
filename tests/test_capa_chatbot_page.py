# Purpose: Capa Chatbot 추천 질문이 한 번 실행으로 답을 더하고 대본을 세션에 한 번만 만드는지 본다.

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components import page_header
from capa_simulation.services import chatbot_samples
from capa_simulation.services.chatbot_samples import SampleAnswer, build_sample_answers

PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "capa_chatbot.py"
TRANSCRIPT_KEY = "capa_chatbot_transcript"


@pytest.fixture
def runs(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """페이지 본문이 돈 횟수(머리말을 그린 횟수)."""
    calls: list[int] = []
    original = page_header.render_page_header

    def counting(*args: object, **kwargs: object) -> None:
        calls.append(1)
        original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(page_header, "render_page_header", counting)
    return calls


@pytest.fixture
def answer_builds(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []

    def counting() -> list[SampleAnswer]:
        calls.append(1)
        return build_sample_answers()

    monkeypatch.setattr(chatbot_samples, "build_sample_answers", counting)
    return calls


def _start() -> AppTest:
    app = AppTest.from_file(str(PAGE), default_timeout=60)
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _shown_conclusions(app: AppTest) -> list[str]:
    expected = {answer.conclusion for answer in build_sample_answers()}
    return [item.value for item in app.markdown if item.value in expected]


def test_a_suggested_question_adds_its_answer_in_one_run(
    runs: list[int], answer_builds: list[int]
) -> None:
    app = _start()
    answers = build_sample_answers()
    assert _shown_conclusions(app) == [answers[0].conclusion]
    runs.clear()

    app.button(key="capa_chatbot_example_1").click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert len(runs) == 1
    assert app.session_state[TRANSCRIPT_KEY] == [answers[0].question, answers[1].question]
    assert _shown_conclusions(app) == [answers[0].conclusion, answers[1].conclusion]
    assert app.button(key="capa_chatbot_example_1").disabled
    # 대본 답은 세션에 한 번만 만든다.
    assert len(answer_builds) == 1


def test_the_answers_show_the_same_evidence_as_a_fresh_build() -> None:
    app = _start()
    for index in (1, 2, 3):
        app.button(key=f"capa_chatbot_example_{index}").click().run()
    answers = build_sample_answers()

    assert _shown_conclusions(app) == [answer.conclusion for answer in answers]
    shown = [frame.value for frame in app.dataframe]
    assert len(shown) == len(answers)
    for frame, answer in zip(shown, answers, strict=True):
        pd.testing.assert_frame_equal(
            frame.reset_index(drop=True), answer.evidence.reset_index(drop=True)
        )


def test_clearing_the_conversation_keeps_only_the_first_answer(runs: list[int]) -> None:
    app = _start()
    app.button(key="capa_chatbot_example_2").click().run()
    runs.clear()

    app.button(key="capa_chatbot_reset").click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert len(runs) == 1
    first = build_sample_answers()[0]
    assert app.session_state[TRANSCRIPT_KEY] == [first.question]
    assert _shown_conclusions(app) == [first.conclusion]
    assert not [button for button in app.button if button.key == "capa_chatbot_reset"]
