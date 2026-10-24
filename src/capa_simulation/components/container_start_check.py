# Purpose: Admin Area 탭 위에 CD 컨테이너 시작 점검 결과를 결과 파일이 있을 때만 펼침으로 보인다.

"""서버 시작 점검.

CD 서버에는 셸도 로그도 없어(시작 명령도 못 바꾼다) 시작 스크립트(`scripts/container_start.py`)의
결과를 이 펼침에서 읽는다. 결과 파일이 없는 개발·사내 PC 에서는 아무것도 그리지 않는다.

파일은 작은 JSON 하나라 회차마다 읽고 DB 는 열지 않는다. 비밀값은 파일에 원래 없다(스크립트가
가렸다). 사람이 넣은 값에서 나온 글(까닭·pip 출력)은 표·코드 칸에 그대로 싣고, 캡션에 넣는 값은
`literal_markdown` 으로 싣는다.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.io.container_start_report import (
    BDQ_USER_NAME_ENV,
    STATUS_LABELS,
    STEP_LABELS,
    STEPS,
    ContainerStartReport,
    read_container_start_report,
    report_verdict,
)

# 펼침 key. 탭 묶음 위에 서므로 자리를 key 로 고정한다(9장 「조건부 알림 뒤 key 없는 펼침」).
EXPANDER_KEY = "admin_area_container_start_check"
GUIDE_DOCUMENT = "docs/bigdataquery_webide_setup.md"


def build_step_table(report: ContainerStartReport) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "단계": [STEP_LABELS[step] for step in STEPS],
            "결과": [STATUS_LABELS[report.steps[step].status] for step in STEPS],
            "까닭": [report.steps[step].reason for step in STEPS],
        }
    )


def fact_lines(report: ContainerStartReport) -> list[str]:
    """표 아래 한 줄씩 — 깔린 판·토큰 파일·요청자 계정. 값은 마크다운에 글자 그대로 싣는다."""
    version = report.bigdataquery_version
    if report.token_file_exists is None:
        token = "계정을 몰라 보지 않음"
    elif report.token_file_exists:
        token = f"있음 · 수정 {literal_markdown(report.token_file_modified_at or '알 수 없음')}"
    else:
        token = "없음"
    account = report.user_name_masked
    return [
        f"bigdataquery 판: {literal_markdown(version) if version else '없음'}",
        f"로그인 토큰 파일: {token}",
        f"`{BDQ_USER_NAME_ENV}`: {f'있음({literal_markdown(account)})' if account else '없음'}",
    ]


def render_container_start_check() -> None:
    report = read_container_start_report()
    if report is None:
        return
    with st.expander(
        f"서버 시작 점검 · {report_verdict(report)}",
        icon=":material/rocket_launch:",
        key=EXPANDER_KEY,
    ):
        st.caption(
            f"C-DEP CD 컨테이너가 {literal_markdown(report.written_at or '알 수 없는 때')} 에 "
            "시작하며 `scripts/container_start.py` 로 남긴 결과입니다. 넣을 환경변수와 토큰 값 "
            f"얻는 법은 `{GUIDE_DOCUMENT}` 의 「C-DEP CD(배포 서버)」 절에 있습니다."
        )
        st.dataframe(build_step_table(report), hide_index=True, width="stretch")
        st.caption("  \n".join(fact_lines(report)))
        if report.missing_environment:
            names = " · ".join(f"`{name}`" for name in report.missing_environment)
            st.caption(f"시작 때 비어 있던 CD 환경변수: {names}")
        if report.pip_tail:
            st.caption("pip 출력 끝(자격증명은 가렸습니다)")
            st.code("\n".join(report.pip_tail), language=None)
