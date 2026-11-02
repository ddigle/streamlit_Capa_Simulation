# Purpose: 통합인증(ADFS form_post) 연동 패키지 — 표준 라이브러리만 쓰는 꾸러미 머리.

"""통합인증(ADFS · OpenID form_post) 연동.

이 꾸러미 머리는 아무것도 내보내지 않는다. 시작 스크립트의 결과 파일(`container_start_report`)처럼
표준 라이브러리만 읽어야 하는 쪽이 `auth.names` 를 import 할 때 무거운 모듈(PyJWT · cryptography ·
Starlette)이 함께 딸려 오지 않게 하기 위해서다. Streamlit 은 이 꾸러미 어디에서도 import 하지 않는다
— 문지기(`gate`)는 Streamlit 바깥의 이벤트 루프에서 돈다.
"""
