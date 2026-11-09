# Purpose: 설비 마스터 저장의 저장자 칸 · 저장 단추 풍선 · 저장 출발점 값을 둔다.

"""설비 마스터를 저장하는 세 자리(가용설비 현황 설비 마스터 탭 「저장 전 변경」 의 「리비전 저장」·
사이드바 설비 시나리오 팝업 「저장」·Space 「배치 저장」)가 함께 쓰는 칸(설계 6-4).

- **저장 자리에는 체크가 없다**(2026-11-05 사용자 결정 — 검수표 11/02 equip-13). 세 자리 모두 새
  호기를 다른 설비 시나리오에 같은 일정으로 넣고, 새 비가동을 모든 설비 시나리오에 넣고, 공식 설비
  시나리오에 새 일정 리비전이 생기면 공식으로 발행한다 — 저장소 `EquipmentSaveRequest` 기본값
  그대로다. 「새 호기」 칸에도 호기마다의 고름이 없다(2026-11-05 사용자 답). 지우는 호기가 다른 설비
  시나리오에 일정이 있어도 묻지 않는다. 일어난 일은 저장 결과 알림이 한 번에
  적고(`equipment_data_workspace.save_result_message`), 늘 하는 일의 말은 Guide 에만 둔다 — 저장
  단추 풍선은 어디로 저장되나 한 줄이다(그림 검수표 equip-13 「일일히 설명을 넣는건 부적절함」).
  갈래를 고를 일이 생기면 그때 기능으로 짓는다.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from capa_simulation.components.saved_note import field_placeholder

SAVED_BY_LABEL = "저장자(선택)"
# 저장자 칸 안 안내 글 — 이름 줄 없이 이 글이 칸 이름과 예를 말한다(변경 메모 칸과 한 꼴 「<이름> ·
# 예: <예>」 — `saved_note.field_placeholder`, 2026-11-09 사용자 규칙 「페이지 상단 최소화」 · 꼴은
# 앱 세션이 정함(검수 전), 설계 규칙 UI-TXT-01 예외). 라벨 「저장자(선택)」 은 접근성 이름으로
# 남는다.
SAVED_BY_PLACEHOLDER = field_placeholder("저장자", "홍길동")


@dataclass(frozen=True)
class EquipmentSaveBasis:
    """저장이 어느 설비 시나리오에 가는지와 화면이 본 공식 번호 — 페이지가 세션에서 만든다.

    - `release_no` 는 화면이 본 최신 공식 번호(발행이 없었으면 0)다 — 이번 저장이 발행할 때만
      저장소가 대조한다(`EquipmentSaveRequest.expected_release_no`).
    - `stale` 은 세션 리비전이 그 시나리오 최신이 아니라는 뜻이다 — 일정 칸·행 추가·일정이 바뀌는
      붙여넣기를 막는다(설계 4-2). `latest_revision_no` 는 그 최신 번호다.
    """

    equipment_scenario_id: str
    scenario_name: str
    release_no: int = 0
    stale: bool = False
    revision_no: int | None = None
    latest_revision_no: int | None = None
    official_scenario: bool = True


def render_saved_by_field(
    prefix: str, *, persist: bool = False, width: int | None = None
) -> str | None:
    """저장자 칸을 그리고 지금 값(비면 None)을 돌려준다(변경 메모 칸은 자리마다 따로 둔다). 이름
    줄은 없고(접근성 이름으로 남는다) 칸 안 안내 글 `SAVED_BY_PLACEHOLDER` 가 이름이다.

    `prefix` 로 칸 key 를 가른다 — 세 저장 자리가 서로의 값을 덮지 않게. 저장자는 세션에 남아 다음
    저장에 그대로 선다(같은 사람이 이어 저장한다). `persist` 면 칸에 `persist_state="session"` 을
    준다 — 그 칸을 그리지 않는 회차가 있는 자리(가용설비 현황 탭 ① 은 숨은 회차에 그리지 않는다,
    개편 명세 2-3)에서도 그 약속을 지킨다. `width` 는 한 줄에 칸을 나란히 두는 자리(Space)의 칸
    너비다.
    """
    saved_by = (
        st.text_input(
            SAVED_BY_LABEL,
            key=f"{prefix}_saved_by",
            placeholder=SAVED_BY_PLACEHOLDER,
            max_chars=40,
            persist_state="session",
            width="stretch" if width is None else width,
            label_visibility="collapsed",
        )
        if persist
        else st.text_input(
            SAVED_BY_LABEL,
            key=f"{prefix}_saved_by",
            placeholder=SAVED_BY_PLACEHOLDER,
            max_chars=40,
            width="stretch" if width is None else width,
            label_visibility="collapsed",
        )
    )
    return _cleaned(saved_by)


def saved_by_from_state(prefix: str) -> str | None:
    """`render_saved_by_field(prefix)` 칸의 지금 값을 세션에서 읽는다 — 저장이 단추 콜백(설비 마스터
    탭 「리비전 저장」·Space 「배치 저장」)이라 그리는 회차의 돌려준 값을 쓸 수 없을 때."""
    return _cleaned(st.session_state.get(f"{prefix}_saved_by"))


def _cleaned(value: object) -> str | None:
    return (value.strip() or None) if isinstance(value, str) else None
