# Purpose: 저장하지 않은 기준 정보 · 생산 계획 고침이 있는 동안 계산 화면 내려받기 파일 이름 끝에
# 「_unsaved」 꼬리를 단다.

"""고침 꼬리(2026-11-18 접속 등급 결정 — 「내 화면에서 계산해 보기」 의 내려받기).

열람도 기준 정보 · 생산 계획을 고쳐 자기 화면에서 계산해 볼 수 있다(저장 안 함). 그 회차에 받은
파일은 저장된 리비전의 값이 아니다 — 받은 사람이 파일 이름만 보고도 가를 수 있게 확장자 앞에
`_unsaved` 를 붙인다(공정 Capa 상세 `detail_file_names` 의 UPEH 가정 꼬리와 같은 꼴). 모든 등급이
같다. 판정은 사이드바 시나리오 칸의 「저장 안 함」 과 같은 `has_unsaved_scenario_changes` 하나다.

앱이 그리는 계산 화면 내려받기 단추(`render_csv_download` · `st.download_button` · 시트 엑셀)의 파일
이름만 바꾼다. Streamlit 표 도구 막대가 짓는 파일 이름은 바꿀 수 없다. 설비 화면(가용설비 현황 ·
Space 현황 · Cut-off)의 파일과 공용 부품 안에서 짓는 이름은 바꾸지 않는다 — 부르는 자리가 넘긴다.
"""

from __future__ import annotations

from typing import Final

from capa_simulation.scenario_activation import has_unsaved_scenario_changes

UNSAVED_TAIL: Final = "_unsaved"


def with_unsaved_tail(file_name: str) -> str:
    """확장자 앞에 `_unsaved` 를 붙인 이름(확장자가 없으면 끝에). 이미 붙었으면 그대로."""
    stem, dot, extension = file_name.rpartition(".")
    if not dot or not stem:
        stem, extension = file_name, ""
    if stem.endswith(UNSAVED_TAIL):
        return file_name
    return f"{stem}{UNSAVED_TAIL}.{extension}" if extension else f"{stem}{UNSAVED_TAIL}"


def edited_file_name(file_name: str) -> str:
    """저장하지 않은 기준 정보 · 생산 계획 고침이 있으면 꼬리를 단 이름, 없으면 그대로."""
    return with_unsaved_tail(file_name) if has_unsaved_scenario_changes() else file_name
