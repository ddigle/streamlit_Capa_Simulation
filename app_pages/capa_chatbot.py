# Purpose: 활성 Capa 데이터를 대상으로 할 LLM 질의 서비스의 대화형 화면과 근거 표시 구조를 제공한다.

import streamlit as st

st.title("Capa Chatbot (구현중)")
st.caption(
    "활성 시나리오의 Capa 데이터와 계산 결과를 근거로 데이터 조회, 부족 공정 파악과 "
    "원인 탐색을 지원하는 대화형 분석 화면입니다."
)
st.markdown(":gray-badge[화면 초안] :blue-badge[LLM·Capa 데이터 미연결]")

with st.container(horizontal=True):
    st.metric("LLM API", "미연결", border=True)
    st.metric("Capa 데이터", "미연결", border=True)
    st.metric("활성 시나리오", "미연결", border=True)
    st.metric("답변 근거", "미생성", border=True)

st.info(
    "운영 단계에서는 Capa 데이터를 매번 모델에 재학습시키기보다, 활성 시나리오와 계산 "
    "결과를 승인된 조회 도구 또는 검색 증강 방식으로 전달해 근거가 있는 답변을 생성합니다.",
    icon=":material/info:",
)

chat_column, guide_column = st.columns([3, 1])

with chat_column:
    with st.container(border=True):
        st.markdown("#### :material/chat: Capa 분석 대화")
        with st.chat_message("assistant", avatar=":material/smart_toy:"):
            st.write(
                "안녕하세요. Capa Chatbot 화면 초안입니다. 데이터와 LLM API가 연결되면 "
                "선택한 시나리오와 조회기간을 기준으로 질문에 답변합니다."
            )
        st.chat_input(
            "LLM API와 Capa 데이터 연결 후 질문할 수 있습니다.",
            key="capa_chatbot_prompt",
            disabled=True,
        )

    with st.container(border=True):
        st.markdown("#### :material/lightbulb: 추천 질문")
        st.caption("연결 후 아래와 같은 질문을 바로 실행할 수 있도록 구성할 예정입니다.")
        with st.container(horizontal=True, gap="small"):
            st.button(
                "월별 부족 공정 알려줘",
                disabled=True,
                key="capa_chatbot_example_shortage",
            )
            st.button(
                "B/N 원인을 분석해줘",
                disabled=True,
                key="capa_chatbot_example_bottleneck",
            )
            st.button(
                "제품별 부하량을 비교해줘",
                disabled=True,
                key="capa_chatbot_example_load",
            )
            st.button(
                "기준정보 누락을 확인해줘",
                disabled=True,
                key="capa_chatbot_example_reference",
            )

with guide_column:
    with st.container(border=True):
        st.markdown("#### :material/analytics: 답변 범위")
        st.markdown(
            "- PKG·Chip·Wafer·Density 부하량\n"
            "- 공정별 대당 Capa·소요대수\n"
            "- 확보율과 B/N 공정\n"
            "- 제품·Stack·WF 속성 상세\n"
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
        st.markdown("#### :material/history: 대화 관리")
        st.caption(
            "대화 저장 범위, 사용자 권한, 민감정보 마스킹과 감사 이력은 LLM 연결 전에 "
            "별도 정책으로 확정합니다."
        )
