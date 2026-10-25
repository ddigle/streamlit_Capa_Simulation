# Purpose: 설비 마스터 저장 칸(저장자·함께 넣기 두 체크·공식 발행)과 저장 출발점 값을 둔다.

"""설비 마스터를 저장하는 세 자리(가용설비 현황 설비 마스터 탭 「저장 전 변경」 의 「리비전 저장」·
사이드바 설비 시나리오 팝업 「저장」·Space 「배치 저장」)가 함께 쓰는 저장 칸(설계 6-4 — 개편 B
전에는
옛 설비 마스터 폼의 두 저장까지 네 자리).

- **폼 안에서는 세 체크를 늘 세우고 수를 적지 않는다** — 폼을 그린 회차의 편집본에는 같은 제출의
  새 호기가 아직 없다. 실제로 퍼진 수·목록과 발행 여부는 저장 결과 알림이 적는다. 미리보기 후보가
  있는 자리(팝업)만 수를 미리 적는다(`counts`).
- 기본값 셋은 아래 상수 한 곳이다(질문 1 — 공식 발행 기본 켬, F6·F2 — 함께 넣기 기본 켬). 답이
  바뀌면 이 상수만 고친다.
- **가정 세션의 Space 「배치 저장」**(`assumption=True` — 설비 시나리오 2단계 Q1)은 「새 호기를 다른
  설비 시나리오에도 넣기」 가 **기본 끔**이다(배치 검토용 가상 호기가 공식 일정·가용대수에 들지
  않게). 켜면 공식 가용대수에 센다는 경고와, 그때만 「함께 넣은 공식 리비전 발행」 체크가 선다. key
  는 공식 자리와 가른다(같은 key 의 기본값이 세션 역할로 바뀌지 않게).
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

# 질문 1 권장안(설계 9장) — 공식 설비 시나리오에 새 일정 리비전이 생기는 저장은 기본으로 공식 발행.
DEFAULT_PUBLISH_OFFICIAL = True
# F6 — 새 호기를 넣을 때 「다른 시나리오에도 같은 일정으로 넣기」 기본 켬.
DEFAULT_PROPAGATE_NEW_UNITS = True
# F2 — 비가동을 넣을 때 「모든 시나리오에 넣기」 기본 켬.
DEFAULT_PROPAGATE_NEW_DOWNTIME = True

PROPAGATE_UNITS_LABEL = "새로 넣은 호기를 다른 설비 시나리오에도 같은 일정으로 넣기"
PROPAGATE_DOWNTIME_LABEL = "새로 넣은 비가동을 모든 설비 시나리오에 넣기"
PUBLISH_OFFICIAL_LABEL = "공식 설비 시나리오에 새 일정 리비전이 생기면 공식으로 발행"
# 가정 세션 Space 저장 상자(Q1).
DEFAULT_ASSUMPTION_PROPAGATE_NEW_UNITS = False
ASSUMPTION_PROPAGATE_UNITS_LABEL = "새 호기를 다른 설비 시나리오에도 넣기"
ASSUMPTION_PROPAGATE_WARNING = (
    "켜면 새 호기가 공식 설비 시나리오에 자리 없는 새 호기로 들어가 공식 가용대수에 셉니다."
)
ASSUMPTION_PUBLISH_LABEL = "함께 넣은 공식 리비전 발행"
_ASSUMPTION_SUFFIX = "_assumption"
# 발행이 하나도 없을 때 발행 체크 대신 서는 한 줄 — 저장소가 첫 일정 리비전을 늘 공식 v1 로 낸다.
FIRST_RELEASE_NOTE = "아직 공식 발행이 없어 이 저장의 일정 리비전이 공식 v1 이 됩니다."
SAVED_BY_LABEL = "저장자(선택)"


@dataclass(frozen=True)
class EquipmentSaveFields:
    """저장 칸에서 받은 값. 기본값은 위 상수다(칸을 그리지 않는 저장 — 시험·래퍼 대신 쓰는 길)."""

    saved_by: str | None = None
    propagate_new_units: bool = DEFAULT_PROPAGATE_NEW_UNITS
    propagate_new_downtime: bool = DEFAULT_PROPAGATE_NEW_DOWNTIME
    publish_official: bool = DEFAULT_PUBLISH_OFFICIAL


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


@dataclass(frozen=True)
class SaveCandidateCounts:
    """저장 전에 셀 수 있을 때(팝업)만 적는 함께 넣기 후보 수."""

    new_units: int = 0
    new_downtime: int = 0


def render_equipment_save_fields(
    prefix: str,
    *,
    counts: SaveCandidateCounts | None = None,
    show_publish: bool = True,
    release_exists: bool = True,
    assumption: bool = False,
    persist_saved_by: bool = False,
) -> EquipmentSaveFields:
    """저장자 칸과 세 체크를 그리고 지금 값을 돌려준다(변경 메모 칸은 자리마다 따로 둔다).

    `prefix` 로 칸 key 를 가른다 — 같은 화면의 두 자리(폼 안·팝업)가 서로의 값을 덮지 않게. 저장자는
    세션에 남아 다음 저장에 그대로 선다(같은 사람이 이어 저장한다). `show_publish` 가 거짓이면(공식
    시나리오가 아닌 세션) 발행 체크를 그리지 않고 기본값을 돌려준다 — 그 저장이 공식 시나리오에 새
    리비전을 만드는 길은 함께 넣기뿐이라 결과 알림이 말한다. `release_exists` 가 거짓이면(공식
    발행이 하나도 없음) 체크 대신 「공식 v1 이 됩니다」 한 줄을 둔다 — 저장소가 첫 일정 리비전을 늘
    공식으로 내므로 끌 수 있는 체크를 두면 거짓말이 된다.

    `assumption` 이면 가정 세션 Space 저장 상자다(모듈 설명 — 함께 넣기 기본 끔, 발행 체크는 켰을
    때만).

    `persist_saved_by` 면 저장자 칸에 `persist_state="session"` 을 준다 — 그 칸을 그리지 않는 회차가
    있는 자리(가용설비 현황 탭 ① 은 숨은 회차에 그리지 않는다, 개편 명세 2-3)에서도 위 약속(세션에
    남음)을 지킨다. 세 체크는 기본값이 늘 같아 그대로 둔다.
    """
    saved_by = (
        st.text_input(
            SAVED_BY_LABEL,
            key=f"{prefix}_saved_by",
            placeholder="예: 홍길동",
            max_chars=40,
            persist_state="session",
        )
        if persist_saved_by
        else st.text_input(
            SAVED_BY_LABEL, key=f"{prefix}_saved_by", placeholder="예: 홍길동", max_chars=40
        )
    )
    if assumption:
        propagate_units = st.checkbox(
            ASSUMPTION_PROPAGATE_UNITS_LABEL,
            value=DEFAULT_ASSUMPTION_PROPAGATE_NEW_UNITS,
            key=f"{prefix}_propagate_units{_ASSUMPTION_SUFFIX}",
        )
        propagate_downtime = st.checkbox(
            PROPAGATE_DOWNTIME_LABEL,
            value=DEFAULT_PROPAGATE_NEW_DOWNTIME,
            key=f"{prefix}_propagate_downtime",
        )
        publish = False
        if propagate_units:
            st.caption(f":material/warning: {ASSUMPTION_PROPAGATE_WARNING}")
            if release_exists:
                publish = st.checkbox(
                    ASSUMPTION_PUBLISH_LABEL,
                    value=DEFAULT_PUBLISH_OFFICIAL,
                    key=f"{prefix}_publish{_ASSUMPTION_SUFFIX}",
                )
            else:
                st.caption(f":material/verified: {FIRST_RELEASE_NOTE}")
                publish = True
        return EquipmentSaveFields(
            saved_by=(saved_by.strip() or None) if isinstance(saved_by, str) else None,
            propagate_new_units=bool(propagate_units),
            propagate_new_downtime=bool(propagate_downtime),
            publish_official=bool(publish),
        )
    units_label = PROPAGATE_UNITS_LABEL
    downtime_label = PROPAGATE_DOWNTIME_LABEL
    if counts is not None:
        units_label = f"{PROPAGATE_UNITS_LABEL} · 후보 {counts.new_units:,}대"
        downtime_label = f"{PROPAGATE_DOWNTIME_LABEL} · 후보 {counts.new_downtime:,}건"
    propagate_units = st.checkbox(
        units_label, value=DEFAULT_PROPAGATE_NEW_UNITS, key=f"{prefix}_propagate_units"
    )
    propagate_downtime = st.checkbox(
        downtime_label, value=DEFAULT_PROPAGATE_NEW_DOWNTIME, key=f"{prefix}_propagate_downtime"
    )
    publish = DEFAULT_PUBLISH_OFFICIAL
    if show_publish and not release_exists:
        st.caption(f":material/verified: {FIRST_RELEASE_NOTE}")
    elif show_publish:
        publish = st.checkbox(
            PUBLISH_OFFICIAL_LABEL, value=DEFAULT_PUBLISH_OFFICIAL, key=f"{prefix}_publish"
        )
    return EquipmentSaveFields(
        saved_by=(saved_by.strip() or None) if isinstance(saved_by, str) else None,
        propagate_new_units=bool(propagate_units),
        propagate_new_downtime=bool(propagate_downtime),
        publish_official=bool(publish),
    )


def save_fields_from_state(prefix: str, *, assumption: bool = False) -> EquipmentSaveFields:
    """`render_equipment_save_fields(prefix)` 가 세운 칸의 지금 값을 세션에서 읽는다 — 저장이 단추
    콜백(Space 「배치 저장」)이라 그리는 회차의 돌려준 값을 쓸 수 없을 때. 칸이 아직 없으면
    기본값. `assumption` 이면 가정 세션 칸(함께 넣기 기본 끔, 발행은 함께 넣기를 켰을 때만)."""

    def flag(suffix: str, default: bool) -> bool:
        value = st.session_state.get(f"{prefix}_{suffix}", default)
        return value if isinstance(value, bool) else default

    saved_by = st.session_state.get(f"{prefix}_saved_by")
    if assumption:
        units = flag(f"propagate_units{_ASSUMPTION_SUFFIX}", DEFAULT_ASSUMPTION_PROPAGATE_NEW_UNITS)
        return EquipmentSaveFields(
            saved_by=(saved_by.strip() or None) if isinstance(saved_by, str) else None,
            propagate_new_units=units,
            propagate_new_downtime=flag("propagate_downtime", DEFAULT_PROPAGATE_NEW_DOWNTIME),
            publish_official=units
            and flag(f"publish{_ASSUMPTION_SUFFIX}", DEFAULT_PUBLISH_OFFICIAL),
        )
    return EquipmentSaveFields(
        saved_by=(saved_by.strip() or None) if isinstance(saved_by, str) else None,
        propagate_new_units=flag("propagate_units", DEFAULT_PROPAGATE_NEW_UNITS),
        propagate_new_downtime=flag("propagate_downtime", DEFAULT_PROPAGATE_NEW_DOWNTIME),
        publish_official=flag("publish", DEFAULT_PUBLISH_OFFICIAL),
    )
