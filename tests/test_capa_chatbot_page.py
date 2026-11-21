# Purpose: Capa Chatbot 추천 질문·대본 메모와 답의 공정 표시명을 검증한다.

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from percent_display import shown_texts
from streamlit.testing.v1 import AppTest

import capa_simulation.components.process_labels as process_labels_module
from capa_simulation.components import page_header
from capa_simulation.components.percent_cells import TABLE_PERCENT_DIGITS, percent_cell_text
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.services import chatbot_samples
from capa_simulation.services.chatbot_samples import SampleAnswer, build_sample_answers
from capa_simulation.services.performance_actuals import build_monthly_actual_demo

PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "capa_chatbot.py"
TRANSCRIPT_KEY = "capa_chatbot_transcript"
# 받은 답의 근거 표를 고치는 화면 — 페이지를 돌린 뒤 받은 답마다 근거 표의 행을 지운다(제자리 고침).
EDITING_SCRIPT = f"""
import json
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


def test_the_head_has_no_badge_line_and_the_switch_is_a_sidebar_row() -> None:
    """머리에는 배지 줄(「구현중 · 인터랙티브 프로토타입 · … 미연결」)이 없고 「샘플 데이터」 는
    사이드바 조회 조건 패널 줄이다 — 구현 중 표지는 화면 탭 이름 곁, 합성 샘플 표지는 머리 띠다
    (2026-11-09 보드 T8). 끄면 자리 표지 「… 연결 대기」 가 무엇을 기다리는지 말한다."""
    from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY

    app = _start()
    assert not _badge_lines(app)
    assert not app.main.toggle
    switch = app.toggle(key=SAMPLE_TOGGLE_KEY)
    assert switch in list(app.sidebar.toggle)

    switch.set_value(False).run()
    assert not app.exception, [item.message for item in app.exception]
    assert not _badge_lines(app)
    assert [item for item in app.get("html") if "연결 대기</strong>" in item.proto.body]


def test_the_four_parts_of_an_answer_are_told_by_the_guide_not_the_chat_card() -> None:
    """첫 카드 「Capa 분석 대화」 에는 답의 네 칸을 말하는 설명 글이 없고 그 말은 Guide 가 한다
    (2026-11-10 보드 Q-9 — 화면에 설명 글을 달지 않는다, 설계 규칙 UI-TXT-01)."""
    from capa_simulation.components.page_guide import load_guide

    app = _start()
    assert not [item for item in app.main.caption if "네 칸" in str(item.value)]
    guide = " ".join(load_guide("capa_chatbot").replace("**", "").split())
    assert "답은 네 칸으로 옵니다 — 결론 · 근거 표 · 사용한 조건과 산식 · 한계" in guide
    assert "연결 뒤에도 이 네 칸은 그대로입니다" in guide


def test_the_suggested_questions_card_has_no_order_line_and_the_guide_tells_the_order() -> None:
    """「추천 질문」 카드는 머리와 단추뿐이다 — 단추 차례의 뜻(무엇이 나쁜가 → … → 더 내려가면
    어디인가)과 누르면 어떻게 되는지는 머리 밑 회색 줄이 아니라 Guide 가 말한다(2026-11-21 확인
    보드 q-chatbot a — 2차 보드 Q2-25 「그대로」 를 바꿈, 설계 규칙 UI-TXT-01 · UI-TXT-02).
    Guide 가 말하는 차례는 실제 단추 차례이고, 첫 답이 대화에 있어 첫 단추는 꺼져 있다."""
    from capa_simulation.components.page_guide import load_guide

    app = _start()
    captions = [str(item.value) for item in app.main.caption]
    assert not [text for text in captions if "무엇이 나쁜가" in text], captions
    assert not [item for item in app.main.markdown if "무엇이 나쁜가" in str(item.value)]
    guide = " ".join(load_guide("capa_chatbot").replace("**", "").split())
    assert "추천 질문 — 단추 넷은 실제로 묻게 되는 차례로 놓여 있습니다." in guide
    assert (
        "무엇이 나쁜가(기준 미달인 공정) → 왜 나쁜가(가장 나쁜 공정이 왜 부족한지) → "
        "무엇부터 할까(개선 차례) → 더 내려가면 어디인가(제품까지 내려간 문제)."
    ) in guide
    assert "단추를 누르면 그 답이 아래에 더해지며 이미 물은 질문의 단추는 꺼집니다." in guide
    assert "`대화 비우기` 는 첫 답만 남깁니다." in guide

    answers = build_sample_answers()
    assert [answer.key for answer in answers] == ["shortfall", "cause", "priority", "reference"]
    buttons = [item for item in app.main.button if str(item.key).startswith("capa_chatbot_example")]
    labels = [str(item.label) for item in buttons]
    assert len(labels) == 4, labels
    fixed = [answers[0].question, answers[2].question, answers[3].question]
    assert [labels[0], labels[2], labels[3]] == fixed
    assert labels[1].endswith("— 왜 부족해?"), labels[1]
    assert [item.disabled for item in buttons] == [True, False, False, False]


def test_the_connection_card_keeps_a_title_and_a_list_and_the_guide_tells_why() -> None:
    """오른쪽 「연결 방식」 카드에는 제목과 목록만 서고 회색 설명 세 문장은 Guide 가 말한다(2차
    보드 Q2-24 — 화면에 설명 글을 달지 않는다, 설계 규칙 UI-TXT-01). 그 문장은 화면 글 문장 그물이
    「미정리」 로 세던 이 화면의 마지막 자리였다."""
    from capa_simulation.components.page_guide import load_guide

    app = _start()
    captions = [str(item.value) for item in app.main.caption]
    assert not [text for text in captions if "재학습" in text or "별도 정책" in text]
    connection = [str(item.value) for item in app.main.markdown if "재학습 없음" in str(item.value)]
    assert len(connection) == 1
    assert all(line.startswith("- ") for line in connection[0].splitlines())
    guide = " ".join(load_guide("capa_chatbot").replace("**", "").split())
    assert "연결 방식 — Capa 데이터를 매번 모델에 재학습시키지 않습니다." in guide
    assert "승인된 조회 도구로 전달해 근거가 있는 답변을 만듭니다." in guide
    assert "감사 이력은 연결 전에 별도 정책으로 확정합니다." in guide


def _badge_lines(app: AppTest) -> list[str]:
    marks = ("인터랙티브 프로토타입", "미연결", "-badge[")
    return [
        str(item.value)
        for item in app.main.markdown
        if any(mark in str(item.value) for mark in marks)
    ]


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


def test_evidence_numbers_read_like_the_actual_screens() -> None:
    """근거 표 숫자 칸은 옆 실적 화면과 같은 꼴이다 — 서식 없이 내면 Gap 이 분수(-0.1093)로
    나와 결론의 「-10.9%」·조건의 「Gap … (%)」 와 어긋났고 기준·실적도 0.82 · 0.7107
    이었다(2026-10-30 E2E). 실수 칸은 모두 서식이 있거나 % 표 칸(소수 둘째 자리 고정 글 —
    2026-11-19 보드 m19-e2e-percent)이고 Gap 은 % 표 칸에 칸 이름이 단위를 단다(`Gap (%)`).
    지표마다 단위가 다른 「왜 부족해?」 표는 미리 지은 글이고 % 글은 % 표 칸과 같은 소수 둘째
    자리 고정이다(UPEH 값은 대수 글). Gap 단위는 셈(빼기 · 비율)과 상관없이 「%」 다(「%p」 를 쓰지
    않는다 — 2026-11-01 사용자 결정)."""
    app = _start()
    for index in (1, 2, 3):
        app.button(key=f"capa_chatbot_example_{index}").click().run()
    answers = build_sample_answers()
    frames = list(app.dataframe)
    assert len(frames) == len(answers)

    for frame, answer in zip(frames, answers, strict=True):
        config = json.loads(frame.proto.columns or "{}")
        shown = frame.value
        for column in shown.columns:
            if pd.api.types.is_float_dtype(shown[column]):
                own = config.get(column, {}).get("type_config", {}).get("format")
                assert own or _fixed_percent(shown_texts(frame, column)), (answer.key, column)
        if "Gap" in shown.columns and pd.api.types.is_float_dtype(shown["Gap"]):
            assert config["Gap"]["label"] == "Gap (%)"
            assert _fixed_percent(shown_texts(frame, "Gap")), answer.key

    cause = frames[[answer.key for answer in answers].index("cause")].value
    assert "단위" not in cause.columns
    # 미리 지은 글 칸도 % 글은 표의 % 칸과 같은 소수 둘째 자리 고정이다(UI-DAT-12) — 효율 · 수율
    # 값과 세 지표의 Gap. UPEH 값은 대수 글이다.
    gaps = dict(zip(cause["지표"], cause["Gap"], strict=True))
    for name in ("효율", "UPEH", "수율"):
        assert re.fullmatch(r"-?[\d,]+\.\d{2}%", gaps[name]), gaps
    for name in ("효율", "수율"):
        row = cause.loc[cause["지표"].eq(name)].iloc[0]
        for column in ("기준", "실적"):
            assert re.fullmatch(r"-?[\d,]+\.\d{2}%", str(row[column])), (name, column, row[column])
    upeh = cause.loc[cause["지표"].eq("UPEH")].iloc[0]
    assert "%" not in str(upeh["기준"]) + str(upeh["실적"])
    # 같은 공정의 같은 값은 첫 답 % 칸 글과 같은 글이다(82.00% 와 82.0% 로 갈리지 않는다).
    keys = [answer.key for answer in answers]
    first = answers[keys.index("shortfall")].evidence.set_index("공정")
    target = answers[keys.index("cause")].question.split(" — ")[0]
    efficiency = answers[keys.index("cause")].evidence.set_index("지표").loc["효율"]
    assert target in first.index
    for column, source in (("기준", "기준 효율"), ("실적", "실적 효율"), ("Gap", "Gap")):
        assert efficiency[column] == percent_cell_text(first.loc[target, source]), column
    assert chatbot_samples._TABLE_PERCENT_DIGITS == TABLE_PERCENT_DIGITS


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


def test_no_particle_follows_a_process_name_in_the_answers() -> None:
    """공정 이름 바로 뒤에 조사를 붙이지 않는다 — 라틴 이름은 끝소리를 몰라 「은(는)」·「(으)로」
    같은 겸용 조사가 됐다(「TC Bonding은(는) 왜 부족해?」 — E2E r2 #90)."""
    answers = build_sample_answers(lambda _process: "Latin Name")

    assert answers[1].question == "Latin Name — 왜 부족해?"
    for answer in answers:
        for text in (answer.question, answer.conclusion):
            assert not [mark for mark in ("은(는)", "이(가)", "(으)로", "을(를)") if mark in text]


def test_the_answers_block_the_markdown_in_display_names(
    labels: dict[str, ProcessLabels],
) -> None:
    """질문·결론·조건은 대화 줄과 추천 질문 단추 라벨(마크다운)에 실린다 — 사람이 적은 표시명의
    물결표가 지움선이 되지 않게 막는다(E2E r2 #71 — 개선 거리 I11)."""
    processes = sorted(build_monthly_actual_demo()["공정"].astype(str).unique().tolist())
    tilde_labels = {process: f"표시~공정~{index}" for index, process in enumerate(processes)}
    labels["now"] = ProcessLabels(version=11, labels=tilde_labels)
    app = _start()
    app.button(key="capa_chatbot_example_1").click().run()
    assert not app.exception, [item.message for item in app.exception]

    shown = _shown_texts(app)
    assert any(r"표시\~공정\~" in text for text in shown), shown
    markdown = [str(item.value) for item in app.markdown] + [str(b.label) for b in app.button]
    assert not [text for text in markdown if "표시~공정~" in text]


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


def _column_formats(frame: Any) -> dict[str, tuple[str | None, str | None]]:
    """표 칸 설정(`st.column_config`)에서 칸 → (머리, 숫자 서식)."""
    config = json.loads(frame.proto.columns or "{}")
    return {
        column: (
            settings.get("label"),
            (settings.get("type_config") or {}).get("format"),
        )
        for column, settings in config.items()
    }


def _fixed_percent(texts: list[str]) -> bool:
    """보이는 글이 모두 소수 둘째 자리 고정 % 글(빈칸 제외)이다."""
    filled = [text for text in texts if text]
    return bool(filled) and all(re.fullmatch(r"-?[\d,]+\.\d{2}%", text) for text in filled)


def test_the_evidence_ratios_use_the_same_percent_format_as_the_actual_screens() -> None:
    """근거 표 비율이 0.82·-0.1093 소수로 보였는데 캡션은 「효율 실적 화면의 우선순위 표와 같은
    값」 이다 — 그 표는 82%·-10.93% 꼴이라 서식을 맞춘다(E2E r1). 단위가 줄마다 다른 「왜
    부족해?」 근거는 그 지표 화면의 꼴로 적은 글자다."""
    app = _start()
    for index in (1, 2, 3):
        app.button(key=f"capa_chatbot_example_{index}").click().run()
    shortfall, cause, priority, reference = list(app.dataframe)

    # % 칸은 실적 화면 표와 같은 % 표 칸 — 칸 설정에서 꼴을 빼고 소수 둘째 자리 고정 글을 단다
    # (82.00% · -10.93% — 2026-11-19 보드 m19-e2e-percent).
    assert _column_formats(shortfall)["기준 효율"] == (None, None)
    assert _column_formats(shortfall)["Gap"] == ("Gap (%)", None)
    assert _column_formats(priority)["영향 비중"] == (None, None)
    assert _column_formats(reference)["실적 효율"] == (None, None)
    assert _fixed_percent(shown_texts(shortfall, "기준 효율"))
    assert _fixed_percent(shown_texts(shortfall, "Gap"))
    assert _fixed_percent(shown_texts(priority, "영향 비중"))
    assert _fixed_percent(shown_texts(reference, "실적 효율"))
    efficiency = cause.value.set_index("지표")
    assert str(efficiency.loc["효율", "기준"]).endswith("%")
    assert str(efficiency.loc["효율", "Gap"]).endswith("%")
    assert not str(efficiency.loc["효율", "Gap"]).endswith("%p")
    assert not str(efficiency.loc["UPEH", "기준"]).endswith("%")


def test_the_shortfall_conclusion_names_what_it_counts() -> None:
    """「효율이 기준에 못 미치는 공정은 4개」 는 기간 평균 Gap 이 음수인 정상 공정까지 세면 5개라
    헷갈렸다(E2E r1). 결론은 센 기준(마지막 달까지 연속 미달 — 상태 「개선 필요」·「관찰」)을 밝히고
    그 수는 근거 표 줄 수다."""
    answer = build_sample_answers()[0]

    assert "효율이 기준에 못 미치는 공정은" not in answer.conclusion
    assert "마지막 달까지 연속 미달인 공정(상태 「개선 필요」·「관찰」)은 " in answer.conclusion
    assert f"은 {len(answer.evidence)}개입니다." in answer.conclusion
    assert set(answer.evidence["상태"]) <= {"개선 필요", "관찰"}
