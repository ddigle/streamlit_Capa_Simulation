# Purpose: Capa 데이터를 근거로 답하는 대화형 분석 화면의 답변 구조를 대본으로 보여 준다.

"""Capa Chatbot.

LLM 을 붙이기 전에 정할 것은 모델이 아니라 **답변의 모양**이다. 결론 한 줄, 근거 표,
쓴 조건과 산식, 못 하는 것 — 이 네 칸이 비면 답이 그럴듯해도 쓸 수가 없다. 빈 대화창을
띄워 두면 그 네 칸을 합의할 자리가 없다.

그래서 대본을 그린다. 추천 질문을 누르면 실제 데이터로 만든 답이 네 칸에 들어찬다.
연결할 때 바꾸는 것은 대본을 만드는 자리 하나뿐이고 화면은 그대로다.

공정 이름은 옆 화면(효율 실적)과 같은 공용 표시명이다 — 결론·질문·조건은 대본이 표시명으로
적고, 근거 표는 화면 복사본에 입힌다(AGENTS 8장 「화면은 표시명, 파일은 원본」).
"""

from __future__ import annotations

from dataclasses import replace

import streamlit as st

from capa_simulation.components.page_header import (
    MATURITY_BADGES,
    page_badges,
    pending_badge,
    render_page_header,
)
from capa_simulation.components.process_labels import ProcessLabels, get_process_labels
from capa_simulation.components.sample_data import (
    render_pending_source,
    render_sample_switch,
)
from capa_simulation.services.chatbot_samples import SampleAnswer, build_sample_answers

SOURCE = "LLM API · Capa 데이터"
# 대화 기록 — 물은 답의 `SampleAnswer.key` 차례. 질문 글자는 공정 표시명을 따라 바뀌어 적지 않는다.
TRANSCRIPT_KEY = "capa_chatbot_transcript"
# 추천 질문 버튼은 개수만큼 생긴다. 접두를 상수로 두어야 겹침 검사가 기준 키를 본다.
EXAMPLE_KEY = "capa_chatbot_example"
# 대본 답(세션 칸, `(표시명 프로필 버전, 답 목록)`). `_sample_answers`.
ANSWERS_MEMO_KEY = "capa_chatbot_sample_answers"


def _sample_answers(process_labels: ProcessLabels) -> list[SampleAnswer]:
    """대본 답 네 개. 날짜·난수를 읽지 않는 결정적 데모(`build_monthly_actual_demo`)에서 나오므로
    표시명 프로필 버전마다 세션에 한 번만 만든다 — 결론·질문 글자가 표시명을 담아, Admin 에서
    표시명을 바꾸면 새로 만든다. 근거 표는 표시명을 입힌 사본을 준다 — 받은 쪽이 고쳐도 기억한
    답이 바뀌지 않는다. 연결 뒤 실제 질의로 바꾸면 이 칸은 버린다."""
    memo = st.session_state.get(ANSWERS_MEMO_KEY)
    if not (
        isinstance(memo, tuple)
        and len(memo) == 2
        and memo[0] == process_labels.version
        and isinstance(memo[1], list)
        and memo[1]
        and all(isinstance(answer, SampleAnswer) for answer in memo[1])
    ):
        memo = (process_labels.version, build_sample_answers(process_labels.label))
        st.session_state[ANSWERS_MEMO_KEY] = memo
    return [
        replace(answer, evidence=process_labels.frame(answer.evidence).copy()) for answer in memo[1]
    ]


def _ask(key: str) -> None:
    """추천 질문 단추 콜백. 본문보다 먼저 돌아 그 회차에 답과 꺼진 단추가 함께 선다 — 본문에서
    덧붙이고 `st.rerun()` 하면 한 번 누를 때 화면이 두 번 돈다."""
    transcript = list(st.session_state.get(TRANSCRIPT_KEY) or [])
    if key not in transcript:
        st.session_state[TRANSCRIPT_KEY] = [*transcript, key]


def _reset_transcript(first_key: str) -> None:
    """`대화 비우기` 콜백. 첫 답 하나만 남긴다."""
    st.session_state[TRANSCRIPT_KEY] = [first_key]


def _render_answer(answer: SampleAnswer) -> None:
    """답 하나를 네 칸으로 그린다. 칸 이름을 화면에 적어 두면 그대로 연결 요구사항이 된다."""
    with st.chat_message("user", avatar=":material/person:"):
        st.write(answer.question)
    with st.chat_message("assistant", avatar=":material/smart_toy:"):
        st.markdown(answer.conclusion)
        with st.expander(":material/table_view: 근거", expanded=True):
            st.caption(answer.evidence_caption)
            st.dataframe(answer.evidence, hide_index=True, width="stretch")
        with st.expander(":material/rule: 사용한 조건과 산식", expanded=False):
            st.markdown("\n".join(f"- {item}" for item in answer.conditions))
        if answer.limits:
            st.caption(
                ":material/warning: " + " ".join(answer.limits),
                width="stretch",
            )


render_page_header(
    "Capa Chatbot (구현중)",
    description=(
        "활성 시나리오의 Capa 데이터와 계산 결과를 근거로 데이터 조회, 부족 공정 파악과 "
        "원인 탐색을 지원하는 대화형 분석 화면입니다."
    ),
    badges=page_badges(MATURITY_BADGES["prototype"], pending_badge(SOURCE)),
)

if not render_sample_switch(key="capa_chatbot_sample_switch", source=SOURCE):
    render_pending_source(
        subject="Capa Chatbot",
        source=SOURCE,
        expects=(
            "**승인된 조회 도구** — 모델에 데이터를 재학습시키지 않고, 활성 시나리오와 "
            "계산 결과를 도구 호출로 읽게 합니다",
            "질문 → 도구 → 근거 표로 이어지는 **감사 가능한 경로**",
            "권한 범위 정의 — 사용자가 볼 수 없는 시나리오는 도구가 거부해야 합니다",
            "대화 저장 범위와 민감정보 마스킹 정책",
        ),
    )
    st.stop()

# 공정 표시명은 화면 글자 전용이다. 순위·Gap 은 대본이 원본 공정명으로 셈한다.
answers = _sample_answers(get_process_labels())
answers_by_key = {answer.key: answer for answer in answers}
# 처음 들어온 사람에게 빈 대화창을 보이지 않는다. 첫 답이 이 화면의 설명이다. 모르는 칸(옛 꼴의
# 질문 글자 등)은 걸러 낸다.
transcript = [
    key for key in list(st.session_state.get(TRANSCRIPT_KEY) or []) if key in answers_by_key
] or [answers[0].key]
st.session_state[TRANSCRIPT_KEY] = transcript

chat_column, guide_column = st.columns([3, 1], gap="medium")

with chat_column:
    with st.container(border=True):
        st.markdown("#### :material/chat: Capa 분석 대화")
        st.caption(
            "답은 네 칸으로 옵니다 — 결론 · 근거 표 · 사용한 조건과 산식 · 한계. "
            "연결 뒤에도 이 네 칸은 그대로입니다."
        )
        for key in transcript:
            _render_answer(answers_by_key[key])
        st.chat_input(
            "연결 전에는 아래 추천 질문으로만 답합니다.",
            key="capa_chatbot_prompt",
            disabled=True,
        )

    with st.container(border=True):
        st.markdown("#### :material/lightbulb: 추천 질문")
        st.caption("무엇이 나쁜가 → 왜 나쁜가 → 무엇부터 할까 → 더 내려가면 어디인가.")
        with st.container(horizontal=True, gap="small", horizontal_alignment="left"):
            for index, answer in enumerate(answers):
                st.button(
                    answer.question,
                    key=f"{EXAMPLE_KEY}_{index}",
                    disabled=answer.key in transcript,
                    on_click=_ask,
                    args=(answer.key,),
                )
        if len(transcript) > 1:
            st.button(
                "대화 비우기",
                key="capa_chatbot_reset",
                icon=":material/restart_alt:",
                on_click=_reset_transcript,
                args=(answers[0].key,),
            )

with guide_column:
    with st.container(border=True):
        st.markdown("#### :material/analytics: 답변 범위")
        st.markdown(
            "- PKG·Chip·Wafer·Density 부하량\n"
            "- 공정별 대당 Capa·소요대수\n"
            "- 확보율과 B/N 공정\n"
            "- 효율·UPEH·수율 실적 Gap\n"
            "- 기준정보 누락과 제외 진단"
        )

    with st.container(border=True):
        st.markdown("#### :material/fact_check: 답변 원칙")
        st.markdown(
            "- 활성 시나리오와 조회기간 명시\n"
            "- 사용한 지표·단위·산식 표시\n"
            "- 근거 테이블과 필터 조건 제공\n"
            "- 권한 범위 밖 데이터는 차단\n"
            "- 추정과 확정 결과를 구분"
        )

    with st.container(border=True):
        st.markdown("#### :material/security: 연결 방식")
        st.caption(
            "Capa 데이터를 매번 모델에 재학습시키지 않습니다. 활성 시나리오와 계산 결과를 "
            "승인된 조회 도구로 전달해 근거가 있는 답변을 만듭니다. 대화 저장 범위·권한· "
            "민감정보 마스킹·감사 이력은 연결 전에 별도 정책으로 확정합니다."
        )
