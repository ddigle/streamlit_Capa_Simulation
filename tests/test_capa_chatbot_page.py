# Purpose: Capa Chatbot 추천 질문·대본 메모와 답의 공정 표시명을 검증한다.

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import capa_simulation.components.process_labels as process_labels_module
from capa_simulation.components import page_header
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.services import chatbot_samples
from capa_simulation.services.chatbot_samples import SampleAnswer, build_sample_answers
from capa_simulation.services.performance_actuals import build_monthly_actual_demo

PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "capa_chatbot.py"
TRANSCRIPT_KEY = "capa_chatbot_transcript"
# 받은 답의 근거 표를 고치는 화면 — 페이지를 돌린 뒤 받은 답마다 근거 표의 행을 지운다(제자리 고침).
EDITING_SCRIPT = f"""
from pathlib import Path

page = Path({str(PAGE)!r})
exec(compile(page.read_text(encoding="utf-8"), str(page), "exec"))
for answer in answers:
    answer.evidence.drop(index=answer.evidence.index[:1], inplace=True)
"""


@pytest.fixture(autouse=True)
def labels(monkeypatch: pytest.MonkeyPatch) -> dict[str, ProcessLabels]:
    """화면이 읽는 공용 공정 표시명. 시험이 `labels["now"]` 를 갈아 Admin 저장을 흉내 낸다 — 공용
    프로필(DB)을 열지 않는다."""
    holder = {"now": ProcessLabels()}
    monkeypatch.setattr(process_labels_module, "get_process_labels", lambda: holder["now"])
    return holder


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

    def counting(*args: Any, **kwargs: Any) -> list[SampleAnswer]:
        calls.append(1)
        return build_sample_answers(*args, **kwargs)

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
    assert app.session_state[TRANSCRIPT_KEY] == [answers[0].key, answers[1].key]
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
    assert app.session_state[TRANSCRIPT_KEY] == [first.key]
    assert _shown_conclusions(app) == [first.conclusion]
    assert not [button for button in app.button if button.key == "capa_chatbot_reset"]


def test_a_caller_that_edits_the_evidence_leaves_the_answers_intact(
    answer_builds: list[int],
) -> None:
    """근거 표는 사본으로 나간다 — 받은 쪽이 제자리에서 고쳐도 다음 회차의 근거 표는 새로 만든
    대본과 같다."""
    app = AppTest.from_string(EDITING_SCRIPT, default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]
    for index in (1, 2, 3):
        app.button(key=f"capa_chatbot_example_{index}").click().run()
        assert not app.exception, [item.message for item in app.exception]
    answers = build_sample_answers()

    assert len(answer_builds) == 1
    shown = [frame.value for frame in app.dataframe]
    assert len(shown) == len(answers)
    for frame, answer in zip(shown, answers, strict=True):
        pd.testing.assert_frame_equal(
            frame.reset_index(drop=True), answer.evidence.reset_index(drop=True)
        )


def _renamed_every_process() -> ProcessLabels:
    """데모 공정 전부에 원본과 글자가 겹치지 않는 표시명을 단다(표본 공정명을 리터럴로 두지
    않는다)."""
    processes = sorted(build_monthly_actual_demo()["공정"].astype(str).unique().tolist())
    return ProcessLabels(
        version=7, labels={process: f"표시공정{index}" for index, process in enumerate(processes)}
    )


def _shown_texts(app: AppTest) -> list[str]:
    """화면의 마크다운(질문·결론·조건)과 추천 질문 단추 글자, 근거 표의 `공정` 칸."""
    texts = [str(item.value) for item in app.markdown]
    texts += [str(button.label) for button in app.button]
    for frame in app.dataframe:
        if "공정" in frame.value.columns:
            texts += [str(value) for value in frame.value["공정"]]
    return texts


def test_the_answers_use_the_shared_process_display_names(labels: dict[str, ProcessLabels]) -> None:
    """결론·질문·조건·근거 표의 공정은 옆 화면(효율 실적)과 같은 표시명이다(2026-10-25 E2E).

    Chatbot 만 공용 표시명을 읽지 않아 효율 실적이 「TCB」 일 때 「TC Bonding」 으로 답했고,
    「효율 실적 화면의 우선순위 표와 같은 값입니다.」 캡션의 표와 글자가 어긋났다.
    """
    renamed = _renamed_every_process()
    labels["now"] = renamed
    app = _start()
    for index in (1, 2, 3):
        app.button(key=f"capa_chatbot_example_{index}").click().run()
        assert not app.exception, [item.message for item in app.exception]

    shown = _shown_texts(app)
    expected = build_sample_answers(renamed.label)
    for answer in expected:
        assert answer.conclusion in shown
        assert answer.question in shown
    # 「왜 부족해?」 는 질문 글자에 공정 이름이 든다 — 단추와 대화의 질문 줄이 표시명이다.
    assert "표시공정" in expected[1].question
    for original in renamed.labels:
        assert not [text for text in shown if original in text], original
    evidence = [frame.value for frame in app.dataframe if "공정" in frame.value.columns]
    assert evidence
    assert all(value.startswith("표시공정") for frame in evidence for value in frame["공정"])


def test_a_new_display_name_rebuilds_the_answers_and_keeps_the_conversation(
    labels: dict[str, ProcessLabels], answer_builds: list[int]
) -> None:
    """Admin 에서 표시명을 바꾸면 다음 회차의 답이 새 글자다. 대화 기록은 답 이름이라 질문 글자가
    바뀌어도 남는다."""
    app = _start()
    app.button(key="capa_chatbot_example_1").click().run()
    before = build_sample_answers()
    assert _shown_conclusions(app) == [before[0].conclusion, before[1].conclusion]

    renamed = _renamed_every_process()
    labels["now"] = renamed
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    after = build_sample_answers(renamed.label)
    shown = [str(item.value) for item in app.markdown]
    assert [after[0].conclusion, after[1].conclusion] == [
        text for text in shown if text in {answer.conclusion for answer in after}
    ]
    assert app.session_state[TRANSCRIPT_KEY] == [after[0].key, after[1].key]
    assert app.button(key="capa_chatbot_example_1").label == after[1].question
    assert app.button(key="capa_chatbot_example_1").disabled
    assert len(answer_builds) == 2
