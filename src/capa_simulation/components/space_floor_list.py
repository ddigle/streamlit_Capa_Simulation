# Purpose: Space FAB 층 목록 표(사용 칸·비활성 층 접힘)와 층 사용 편집·끄기 확인·저장을 그린다.

"""Space FAB 전체 아래 층 목록과 층 사용 편집(2026-10-24 사용자 결정 S1~S6).

- **보기**(`사용 편집` 꺼짐): 사용 층 표(행을 고르면 그 층을 연다)와, 비활성 층이 있으면 그 아래
  접힌 「비활성 층 n개」 — 거기서도 행을 골라 연다(호기가 남은 층 대비, S3).
- **편집**(`사용 편집` 켜짐): 위에서 아래로 저장 줄 · 끄기 확인 · 알림 · 동 머리 줄 · 30줄 편집표.
  초안은 세션(층 이름 → 사유 코드, 비활성 층만)이고 편집을 시작할 때 본 저장본 `(version, rows)` 를
  함께 둔다 — 저장은 그 version 으로 대조한다(`ProfileVersionConflict`). 편집표의 칸 편집은
  회차마다(그리고 단추 콜백 첫머리에서) 초안에 **접는다** — 편집표는 늘 접은 초안을 그린다.
- 칸 편집은 위젯에 남은 채(같은 위젯 — 보던 스크롤·초점이 남는다) 접은 초안 위에 다시 얹혀
  보인다. 새 위젯으로 세우는 것은 그렇게 보일 값이 접은 값과 다를 때뿐이다(비활성 층의 사유를
  지움 등). `사유` 칸은 `string` 으로 고정한다 — 모두 비어도 Arrow 타입이 같아야 첫 끄기에 위젯
  서명(Streamlit 1.63 은 칸 타입을 넣는다)이 바뀌지 않는다.
- 동 머리(`st.segmented_control`)는 key 위젯이라 처음 만든 뒤 `default=` 를 보지 않는다(정체가
  key + `click_mode` 뿐). 그래서 그리기 전에 **회차마다** 초안의 그 동 상태를 세션에 적는다 —
  세대를 올리지 않는 칸 편집 뒤에도 머리가 맞는다.
- 호기가 남은 층을 새로 끄면 막지 않고 확인한다(S4). 호기 수는 편집 모드 본문이 센 값을 콜백
  인자로 받는다 — 콜백은 본문보다 먼저 돌아 그 회차 상태 프레임이 아직 없다. 공식 배치에는
  호기가 없어도 가정 설비 시나리오의 배치가 그 층에 호기를 두었으면 확인한다(그 셈은 저장소
  캐시 `load_layout_overlay_floor_counts`).
- 성공 문구는 flash(`st.success`), 충돌·검증 오류·「바뀐 층이 없습니다」 는 같은 상자 안 알림
  칸이다.
- 설비 시나리오·설비 리비전과 무관한 공용 현행값이다(S6). 그래서 **공식 설비 시나리오에서만**
  고친다(설비 시나리오 2단계 Q3 — FAB 전체와 같은 까닭, 건물·층은 가정 시나리오가 없다). 가정 세션과
  샘플 fleet 화면에서는 잠근다(값도 끈다 — 까닭은 풍선). 끄기 확인은 공식 배치의 호기 수에 더해
  가정 설비 시나리오의 배치에서 그 층에 놓인 호기 수를 덧줄로 적는다(설계 13-2).

Streamlit 캐시는 두지 않는다 — DB 는 `equipment_cache.load_floor_states`·`get_equipment_repository`
로만 연다.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from functools import partial

import pandas as pd
import streamlit as st

from capa_simulation.components.editor_state import discard_editor, editor_widget_key
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.space_layout import FloorPlacement
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence._sql_helpers import ProfileVersionConflict
from capa_simulation.persistence.equipment_cache import (
    clear_floor_state_cache,
    get_equipment_repository,
    load_floor_states,
    load_layout_overlay_floor_counts,
)
from capa_simulation.services.equipment_contract import VALID_BUILDINGS
from capa_simulation.services.fab_layout import FLOOR_KEYS, floor_from_label, floor_label
from capa_simulation.services.floor_layout_profile import FloorKey
from capa_simulation.services.floor_state import (
    ACTIVE_STATE,
    DEFAULT_FLOOR_REASON,
    FLOOR_REASON_CHOICES,
    FLOOR_REASON_LABELS,
    FLOOR_REASONS,
    FloorStates,
    building_active_count,
    building_state,
    inactive_label,
    newly_inactive,
)
from capa_simulation.settings import EQUIPMENT_DUCKDB_PATH

__all__ = [
    "EDIT_TOGGLE_KEY",
    "FLOOR_TABLE_KEY",
    "INACTIVE_TABLE_KEY",
    "floor_state_draft_pending",
    "render_space_floor_list",
]

# 사용 층 표·비활성 층 표의 위젯 key. 층을 열면 FAB 화면은 그려지지 않아 표 선택은 그 회차에
# 버려진다(그리지 않은 위젯 상태는 버려진다).
FLOOR_TABLE_KEY = "space_status_floor_table"
INACTIVE_TABLE_KEY = "space_status_floor_table_inactive"
INACTIVE_EXPANDER_KEY = "space_floor_inactive_expander"
# 표 머리 `사용 편집` 토글. `value=` 를 주지 않는다 — 저장 콜백·샘플 잠금이 세션에 적는다.
EDIT_TOGGLE_KEY = "space_floor_state_edit"
# 초안(「C1 3F」 → 사유 코드, 비활성 층만)과 편집을 시작할 때 본 저장본 (version, rows).
DRAFT_KEY = "space_floor_state_draft_v1"
BASE_KEY = "space_floor_state_base_v1"
# 동 머리·확인·저장 단추 콜백이 받는 세대. 편집표 위젯 key 세대(`editor_widget_key`)와 늘 함께
# 오른다.
GENERATION_KEY = "space_floor_state_gen_v1"
# 끄기 확인 대기 (세대, ((「C1 3F」, 호기 수), …)).
CONFIRM_KEY = "space_floor_state_confirm_v1"
# 성공 flash 칸과 그 밖의 알림 칸 (종류, 글) — 같은 상자 안에 그린다.
FLASH_KEY = "space_floor_state_flash"
NOTICE_KEY = "space_floor_state_notice_v1"
EDITOR_KEY = "space_floor_state_editor"
_BULK_PREFIX = "space_floor_state_bulk_"
SAVE_BUTTON_KEY = "space_floor_state_save"
REVERT_BUTTON_KEY = "space_floor_state_revert"
CONFIRM_BUTTON_KEY = "space_floor_state_confirm_save"
CANCEL_BUTTON_KEY = "space_floor_state_confirm_cancel"
SOURCE = "space_status"

_USE_COLUMN = "사용"
_REASON_COLUMN = "사유"
_UNITS_COLUMN = "호기"
_BULK_LABELS = {ACTIVE_STATE: "사용", **FLOOR_REASON_LABELS}
_REASON_BY_TEXT = {
    **{code: code for code in FLOOR_REASONS},
    **{label: code for code, label in FLOOR_REASON_LABELS.items()},
    **{label: code for code, label in FLOOR_REASON_CHOICES.items()},
}

SAMPLE_LOCKED = "샘플 데이터를 보는 중에는 층 사용 설정을 바꾸지 않습니다."
_TOGGLE_HELP = (
    "층마다 사용·비활성(사용 안 함·생산라인 아님)을 고칩니다. 모두에게 같은 공용 설정이고 설비 "
    "시나리오와 상관없습니다. 끈 층은 FAB 도면에서 회색 빗금으로 흐려지고 층 목록 맨 아래 「비활성 "
    "층」 으로 내려갑니다. 저장하지 않고 스위치를 끄면 고친 것은 버립니다."
)
_PLACED_HELP = "도면에 그린 설비입니다. Main 설비로 묶은 모듈 행은 합쳐 1대입니다."
_UNPLACED_HELP = "레이아웃표시 Y 인데 좌표가 없어 도면에 그리지 못한 설비입니다."
_OCCUPANCY_HELP = (
    "도면에 그린 호기 사각형 면적 합 ÷ 캔버스 면적. 캔버스 단위의 상대값이며 "
    "겹친 자리는 두 번 셉니다."
)
_DRAWING_HELP = "그 층에 배경 도면 이미지를 올렸는지입니다."
_USE_HELP = "끈 층(비활성)은 FAB 도면에서 흐려지고 층 고르기에서 빠집니다. 호기는 그대로입니다."
_UNITS_HELP = (
    "이 층에 동·층이 적힌 설비 수(오늘 기준·공정 필터 무관·레이아웃 N 포함). 배치대수와 다를 수 "
    "있습니다."
)
# 층 목록 표의 대수·비율 칸. 대수는 설비지분 합이라 모듈 설비가 있으면 소수가 나온다.
_TABLE_COLUMNS = {
    _USE_COLUMN: st.column_config.CheckboxColumn(help=_USE_HELP),
    "배치대수": st.column_config.NumberColumn(format="localized", help=_PLACED_HELP),
    "미배치대수": st.column_config.NumberColumn(format="localized", help=_UNPLACED_HELP),
    "점유율": st.column_config.NumberColumn(format="percent", help=_OCCUPANCY_HELP),
    "배치 도면": st.column_config.TextColumn(help=_DRAWING_HELP),
}

# 색 기준 「필요 단축」 을 켠 동안만 사용 층 표에 붙는 칸 넷(설비 대수 — 모듈 묶음 한 대). 비활성 층
# 표에는 붙이지 않는다(층 대수를 싣지 않는다 — 층 사용 0029 규칙).
_LAYER_COLUMNS = {
    "단축 호기": st.column_config.NumberColumn(
        format="localized",
        help="고른 목표에서 Qual 을 당겨야 하는 호기(필요 단축 일정과 같은 계획).",
    ),
    "최대 단축(일)": st.column_config.NumberColumn(
        format="localized", help="이 층 단축 호기 가운데 가장 많이 당기는 일수."
    ),
    "기한 지남": st.column_config.NumberColumn(
        format="localized", help="목표 Qual 이 오늘 앞인 단축 호기."
    ),
    "추가 호기": st.column_config.NumberColumn(
        format="localized",
        help="기존 호기를 다 당겨도 모자라 새로 들여야 하는 대수(그 공정 호기가 그려진 층마다).",
    ),
}

Draft = dict[FloorKey, str]
Base = tuple[int, tuple[tuple[str, str, str], ...]]
# 끄기 확인 목록에서 공식 배치에는 호기가 없고 가정 설비 시나리오 배치에만 호기가 있는 층의 꼬리.
_OVERLAY_ONLY = "공식 배치 호기 없음(가정 배치에만)"


# ---------------------------------------------------------------- 세션 초안


def _stored_draft() -> Draft | None:
    held = st.session_state.get(DRAFT_KEY)
    if not isinstance(held, Mapping):
        return None
    draft: Draft = {}
    for label, reason in held.items():
        key = floor_from_label(label)
        if key is not None and isinstance(reason, str) and reason:
            draft[key] = reason
    return draft


def _store_draft(draft: Mapping[FloorKey, str]) -> None:
    st.session_state[DRAFT_KEY] = {
        floor_label(key): draft[key] for key in FLOOR_KEYS if key in draft
    }


def _stored_base() -> Base | None:
    held = st.session_state.get(BASE_KEY)
    if (
        isinstance(held, tuple)
        and len(held) == 2
        and isinstance(held[0], int)
        and isinstance(held[1], tuple)
    ):
        rows = tuple(
            (str(row[0]), str(row[1]), str(row[2]))
            for row in held[1]
            if isinstance(row, tuple) and len(row) == 3
        )
        return held[0], rows
    return None


def _base_of(states: FloorStates) -> Base:
    return states.version, tuple(states.rows)


def _base_draft(base: Base) -> Draft:
    return {(building, floor): reason for building, floor, reason in base[1]}


def _generation() -> int:
    return int(st.session_state.get(GENERATION_KEY, 0))


def _remount() -> None:
    """편집표를 새 위젯으로 세우고 단추 세대를 올린다(초안을 먼저 적고 부른다)."""
    discard_editor(EDITOR_KEY)
    st.session_state[GENERATION_KEY] = _generation() + 1


def _start(states: FloorStates) -> None:
    """초안 = 저장본, base = 저장본 (version, rows). 확인 대기는 버린다."""
    _store_draft(states.inactive)
    st.session_state[BASE_KEY] = _base_of(states)
    st.session_state.pop(CONFIRM_KEY, None)
    _remount()


def _forget() -> None:
    """초안·base·확인을 지운다(편집을 끈 회차 — 저장하지 않은 변경은 버린다)."""
    for key in (DRAFT_KEY, BASE_KEY, CONFIRM_KEY):
        st.session_state.pop(key, None)


def floor_state_draft_pending() -> bool:
    """`사용 편집` 이 켜져 있고 초안이 편집을 시작할 때 본 저장본과 다른가 — 세션만 읽는다(테마 전환
    미저장 표지, AGENTS 5장 23). 토글이 꺼진 세션의 남은 초안은 세지 않는다.

    `app.py` 는 페이지보다 먼저 돌아 이 회차의 칸 편집이 아직 초안에 접히지 않았다 — 위젯 상태의
    칸 편집까지 (적지 않고) 접어 본다. 끈 칸을 다시 켜 저장본과 같아졌으면 남은 편집이 있어도
    거짓이다."""
    if not st.session_state.get(EDIT_TOGGLE_KEY):
        return False
    draft, base = _stored_draft(), _stored_base()
    if draft is None or base is None:
        return False
    folded, _ = _folded(draft, _widget_edits())
    return folded != _base_draft(base)


# ---------------------------------------------------------------- 편집표 접기


def _reason_code(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return _REASON_BY_TEXT.get(text, DEFAULT_FLOOR_REASON) if text else None


def _widget_edits() -> dict[int, Mapping[str, object]]:
    state = st.session_state.get(editor_widget_key(EDITOR_KEY))
    rows = state.get("edited_rows") if isinstance(state, Mapping) else None
    if not isinstance(rows, Mapping):
        return {}
    return {
        int(position): change for position, change in rows.items() if isinstance(change, Mapping)
    }


def _folded_row(base: str | None, change: Mapping[str, object]) -> str | None:
    """편집표 한 줄의 칸 편집을 접은 사유(None = 사용). `base` 는 지난 회차 위젯이 그린 값(접은
    초안)이다 — 칸 편집은 다시 세우기 전까지 위젯에 남아 회차마다 다시 접히므로, 그린 값과 같은 칸은
    바뀌지 않은 것으로 본다.

    - `사용` 을 켰으면 사용(사유 없음).
    - 사용 층의 `사유` 를 골랐으면 그 사유로 끈다 — 사유를 고른 뜻이 끄기다.
    - `사용` 을 껐는데 사유가 비었으면 「사용 안 함」(비활성에는 늘 사유가 있다 — S1).
    두 칸이 그린 값과 함께 달라졌으면 켜기가 먼저다."""
    use_value = change.get(_USE_COLUMN)
    use_changed = _USE_COLUMN in change and bool(use_value) != (base is None)
    reason = _reason_code(change[_REASON_COLUMN]) if _REASON_COLUMN in change else base
    reason_changed = _REASON_COLUMN in change and reason != base
    if use_changed and bool(use_value):
        return None
    if reason_changed and reason is not None:
        return reason
    if use_changed:
        return reason or base or DEFAULT_FLOOR_REASON
    if reason_changed:
        # 비활성 층의 사유를 지웠다 — 사유는 늘 있다.
        return DEFAULT_FLOOR_REASON if base is not None else None
    return base


def _shown_after_fold(after: str | None, change: Mapping[str, object]) -> tuple[bool, str | None]:
    """다음 회차 위젯이 보일 (사용, 사유 코드) — 접은 값 `after` 를 그린 위에 남은 칸 편집을
    얹은 것. 다시 세우지 않으면 칸 편집은 위젯에 그대로 남아 접은 초안을 그린 데이터 위에 얹혀
    보인다."""
    use = bool(change[_USE_COLUMN]) if _USE_COLUMN in change else after is None
    reason = _reason_code(change[_REASON_COLUMN]) if _REASON_COLUMN in change else after
    return use, reason


def _folded(draft: Draft, edits: Mapping[int, Mapping[str, object]]) -> tuple[Draft, bool]:
    """초안에 칸 편집을 접은 값과, 새 위젯으로 세워야 하는가 — 세션을 고치지 않는다.

    다시 세우는 것은 다음 회차에 보일 값(접은 값 + 남은 편집)이 접은 값과 다를 때뿐이다 — 비활성
    층의 사유를 지움(보이는 빈 사유 ≠ 「사용 안 함」), 사유를 고른 줄을 다시 켬 등. 끄기(빈 사유는
    그린 데이터가 채운다)·켜기·사용 층의 사유 고르기는 같은 위젯이라 보던 스크롤·초점이 남는다.
    같은 편집을 두 번 접어도 같다(남은 편집은 회차마다 다시 접힌다)."""
    folded = dict(draft)
    remount = False
    for position, change in edits.items():
        if not 0 <= position < len(FLOOR_KEYS):
            continue
        key = FLOOR_KEYS[position]
        after = _folded_row(draft.get(key), change)
        if after is None:
            folded.pop(key, None)
        else:
            folded[key] = after
        if _shown_after_fold(after, change) != (after is None, after):
            remount = True
    return folded, remount


def _fold() -> Draft:
    """편집표의 칸 편집을 초안에 접어 적고, 보일 값이 접은 값과 다르면 새 위젯으로 세운다."""
    draft = _stored_draft() or {}
    edits = _widget_edits()
    if not edits:
        return draft
    folded, remount = _folded(draft, edits)
    _store_draft(folded)
    if remount:
        _remount()
    return folded


# ---------------------------------------------------------------- 콜백


def _toggle_changed(database_path: str) -> None:
    """`사용 편집` 토글. 켜면 초안 = 저장본, 끄면 초안·base·확인을 버린다."""
    if st.session_state.get(EDIT_TOGGLE_KEY):
        _start(load_floor_states(database_path))
    else:
        _forget()


def _bulk_changed(building: str, generation: int) -> None:
    """동 머리 콜백 — 그 동 6개 층을 한꺼번에. 받은 값이 None(같은 칸을 다시 눌러 풀림)이면 아무것도
    바꾸지 않는다(다음 회차의 세션 적기가 원래 값으로 되세운다)."""
    if generation != _generation():
        return
    draft = _fold()
    value = st.session_state.get(f"{_BULK_PREFIX}{building}")
    if value not in _BULK_LABELS:
        return
    others = {key: reason for key, reason in draft.items() if key[0] != building}
    if value != ACTIVE_STATE:
        others.update({key: str(value) for key in FLOOR_KEYS if key[0] == building})
    _store_draft(others)
    _remount()


def _revert(generation: int) -> None:
    """`되돌리기` — 초안 = 편집을 시작할 때 본 저장본."""
    if generation != _generation():
        return
    base = _stored_base()
    if base is None:
        return
    _store_draft(_base_draft(base))
    st.session_state.pop(CONFIRM_KEY, None)
    _remount()


def _overlay_units_on(database_path: str, key: FloorKey) -> int:
    """가정 설비 시나리오들의 배치에서 그 층에 놓인 호기 행 수의 합(덧줄 재료와 같은 셈). 못 읽으면
    0 이다 — 확인을 막지 않는다(덧줄도 같은 까닭으로 빠진다)."""
    try:
        return sum(count for _, count in load_layout_overlay_floor_counts(database_path, *key))
    except BOOTSTRAP_ERRORS:
        return 0


def _risky(
    draft: Draft, base: Base, counts: Mapping[str, int], database_path: str
) -> tuple[tuple[str, int], ...]:
    """새로 끄는 층 가운데 호기가 남은 층 — (「C1 3F」, 공식 배치의 호기 수).

    공식 배치에는 호기가 없어도 가정 설비 시나리오의 배치가 그 층에 호기를 두었으면 든다(수 0 —
    확인 상자의 덧줄이 그 시나리오와 대수를 적는다). 층 사용은 공통이라 그 호기도 그 시나리오의
    목록·도면에서 숨는다 — 배치안이 빈 층을 쓰는 것이 바로 그 경우다(설계 13-2·Q3)."""
    before = FloorStates(rows=base[1], version=base[0])
    risky: list[tuple[str, int]] = []
    for key in newly_inactive(before, draft):
        official = int(counts.get(floor_label(key), 0))
        if official > 0 or _overlay_units_on(database_path, key) > 0:
            risky.append((floor_label(key), official))
    return tuple(risky)


def _notice(kind: str, text: str) -> None:
    st.session_state[NOTICE_KEY] = (kind, text)


def _saved_message(draft: Mapping[FloorKey, str]) -> str:
    if not draft:
        return "층 사용 설정을 저장했습니다 — 모든 층 사용."
    by_reason = [
        f"{label} {sum(1 for reason in draft.values() if reason == code)}"
        for code, label in FLOOR_REASON_LABELS.items()
        if any(reason == code for reason in draft.values())
    ]
    return f"층 사용 설정을 저장했습니다 — 비활성 {len(draft)}개({' · '.join(by_reason)})."


def _write(database_path: str, draft: Draft, base: Base) -> None:
    """저장소에 쓴다 — 성공이면 캐시를 비우고 flash·토글 끄기, 충돌이면 초안을 최신으로 다시
    세운다."""
    repository = get_equipment_repository(database_path)
    try:
        wrote = repository.save_floor_states(draft, expected_version=base[0], source=SOURCE)
    except ProfileVersionConflict as exc:
        clear_floor_state_cache()
        _start(load_floor_states(database_path))
        _notice(
            "warning",
            f"{exc} 편집표를 최신 저장본으로 다시 세웠습니다 — 다시 고친 뒤 저장하세요.",
        )
        return
    except BOOTSTRAP_ERRORS as exc:
        _notice(
            "error",
            "층 사용 설정을 저장하지 못했습니다: "
            + bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,)),
        )
        return
    if not wrote:
        st.session_state.pop(CONFIRM_KEY, None)
        _notice("info", "바뀐 층이 없습니다.")
        return
    clear_floor_state_cache()
    queue_flash(FLASH_KEY, _saved_message(draft))
    # 콜백은 본문보다 먼저 돈다 — 토글을 그리기 전이라 값을 적을 수 있다.
    st.session_state[EDIT_TOGGLE_KEY] = False
    _forget()


def _save(database_path: str, generation: int, counts: Mapping[str, int]) -> None:
    """`저장` 콜백. 호기가 남은 층을 새로 끄면 확인을 띄우고 끝낸다(S4)."""
    if generation != _generation():
        return
    draft = _fold()
    base = _stored_base()
    if base is None:
        return
    risky = _risky(draft, base, counts, database_path)
    if risky:
        st.session_state[CONFIRM_KEY] = (_generation(), risky)
        return
    st.session_state.pop(CONFIRM_KEY, None)
    _write(database_path, draft, base)


def _confirm_save(
    database_path: str,
    generation: int,
    shown: tuple[tuple[str, int], ...],
    counts: Mapping[str, int],
) -> None:
    """`끄고 저장` — 다시 접어 확인한 목록과 같을 때만 쓴다(그 사이 초안이 바뀌었으면 확인을
    새로)."""
    if generation != _generation():
        return
    draft = _fold()
    base = _stored_base()
    if base is None:
        return
    risky = _risky(draft, base, counts, database_path)
    if risky and risky != shown:
        st.session_state[CONFIRM_KEY] = (_generation(), risky)
        return
    st.session_state.pop(CONFIRM_KEY, None)
    _write(database_path, draft, base)


def _cancel_confirm() -> None:
    st.session_state.pop(CONFIRM_KEY, None)


def _open_from_table(
    table_key: str, keys: tuple[FloorKey, ...], on_open: Callable[[FloorKey], None]
) -> None:
    """층 목록 표의 행 고르기 콜백. 키보드로 층을 여는 길이기도 하다(행에 초점을 두고
    Shift+Space)."""
    state = st.session_state.get(table_key)
    if state is None:
        return
    try:
        rows = list(state["selection"]["rows"])
    except (KeyError, TypeError):
        return
    if rows and 0 <= int(rows[0]) < len(keys):
        on_open(keys[int(rows[0])])


# ---------------------------------------------------------------- 그리기


def _table_rows(
    placements: Sequence[FloorPlacement],
    floors_with_image: Collection[FloorKey],
    canvas_text: Callable[[FloorKey], str],
    states: FloorStates,
    *,
    inactive: bool,
    extra_columns: Mapping[FloorKey, Mapping[str, object]] | None = None,
) -> pd.DataFrame:
    rows = []
    for placement in placements:
        reason = states.reason_of(placement.key)
        if (reason is not None) != inactive:
            continue
        row: dict[str, object] = {
            "동": placement.key[0],
            "층": placement.key[1],
            _USE_COLUMN: reason is None,
        }
        if inactive:
            row[_REASON_COLUMN] = inactive_label(str(reason))
        row.update(
            {
                "배치대수": placement.placed,
                "미배치대수": placement.unplaced,
                "점유율": placement.occupancy,
                "배치 도면": "등록" if placement.key in floors_with_image else "미등록",
                "캔버스": canvas_text(placement.key),
            }
        )
        if extra_columns is not None and not inactive:
            row.update(extra_columns.get(placement.key, {}))
        rows.append(row)
    return pd.DataFrame(rows)


def _render_tables(
    placements: Sequence[FloorPlacement],
    floors_with_image: Collection[FloorKey],
    canvas_text: Callable[[FloorKey], str],
    states: FloorStates,
    on_open: Callable[[FloorKey], None],
    extra_columns: Mapping[FloorKey, Mapping[str, object]] | None = None,
) -> None:
    """보기 — 사용 층 표와 접힌 「비활성 층 n개」(늘 서는 자리 칸 안). `extra_columns` 는 사용 층
    표에만 붙는다."""
    active = [placement for placement in placements if states.is_active(placement.key)]
    active_keys = tuple(placement.key for placement in active)
    st.dataframe(
        _table_rows(
            placements,
            floors_with_image,
            canvas_text,
            states,
            inactive=False,
            extra_columns=extra_columns,
        ),
        hide_index=True,
        width="stretch",
        column_config={**_TABLE_COLUMNS, **(_LAYER_COLUMNS if extra_columns is not None else {})},
        key=FLOOR_TABLE_KEY,
        on_select=partial(_open_from_table, FLOOR_TABLE_KEY, active_keys, on_open),
        selection_mode="single-row",
    )
    # 자리 칸은 늘 선다 — 비활성 층이 생기고 사라질 때 뒤 key 묶음이 밀리지 않게.
    with st.container(key="space_floor_inactive_slot"):
        inactive = [placement for placement in placements if not states.is_active(placement.key)]
        if not inactive:
            return
        st.caption(
            ":material/block: FAB 도면에서는 회색 빗금으로 흐리고 눌러도 열리지 않습니다. 호기는 "
            "그대로이고 여기서 열어 볼 수 있습니다."
        )
        with st.expander(f"비활성 층 {len(inactive)}개", expanded=False, key=INACTIVE_EXPANDER_KEY):
            st.dataframe(
                _table_rows(placements, floors_with_image, canvas_text, states, inactive=True),
                hide_index=True,
                width="stretch",
                column_config=_TABLE_COLUMNS,
                key=INACTIVE_TABLE_KEY,
                on_select=partial(
                    _open_from_table,
                    INACTIVE_TABLE_KEY,
                    tuple(placement.key for placement in inactive),
                    on_open,
                ),
                selection_mode="single-row",
            )


def _render_notices() -> None:
    """성공 flash 와 그 밖의 알림(충돌·검증 오류·바뀐 층 없음). 그린 뒤 지운다."""
    render_flash(FLASH_KEY)
    held = st.session_state.pop(NOTICE_KEY, None)
    if not (isinstance(held, tuple) and len(held) == 2):
        return
    kind, text = held
    if kind == "warning":
        st.warning(str(text), icon=":material/sync_problem:")
    elif kind == "error":
        st.error(str(text))
    else:
        st.info(str(text))


def _render_confirm(database_path: str, counts: Mapping[str, int]) -> None:
    held = st.session_state.get(CONFIRM_KEY)
    if not (isinstance(held, tuple) and len(held) == 2 and held[0] == _generation()):
        if held is not None:
            st.session_state.pop(CONFIRM_KEY, None)
        return
    shown: tuple[tuple[str, int], ...] = tuple((str(a), int(b)) for a, b in held[1])
    total = sum(count for _, count in shown)
    with st.container(border=True):
        if len(shown) == 1:
            label, count = shown[0]
            there = (
                f"이 층에 호기 {count}대가 있습니다"
                if count
                else "공식 배치에는 이 층에 호기가 없지만 가정 설비 시나리오의 배치에 호기가 "
                "있습니다"
            )
            st.warning(
                f"**{label}** — {there} — 호기는 그대로 남고 목록·도면에서만 숨습니다.",
                icon=":material/warning:",
            )
        else:
            head = (
                f"끄려는 층에 호기 {total}대가 있습니다"
                if total
                else "끄려는 층의 가정 설비 시나리오 배치에 호기가 있습니다"
            )
            st.warning(
                f"{head} — 호기는 그대로 남고 목록·도면에서만 숨습니다.\n\n"
                + "\n".join(
                    f"- {label} · 호기 {count}대" if count else f"- {label} · {_OVERLAY_ONLY}"
                    for label, count in shown
                ),
                icon=":material/warning:",
            )
        for line in _overlay_lines(database_path, shown):
            st.caption(f":material/layers: {line}")
        st.caption("설비 마스터의 동·층 값은 바뀌지 않습니다. 다시 켜면 그대로 보입니다.")
        with st.container(horizontal=True, gap="small"):
            st.button(
                "끄고 저장",
                type="primary",
                key=CONFIRM_BUTTON_KEY,
                on_click=_confirm_save,
                args=(database_path, _generation(), shown, dict(counts)),
            )
            st.button("취소", key=CANCEL_BUTTON_KEY, on_click=_cancel_confirm)


def _overlay_lines(database_path: str, shown: Sequence[tuple[str, int]]) -> list[str]:
    """끄기 확인의 덧줄 — 가정 설비 시나리오의 배치에서 그 층에 놓인 호기(층 사용은 공통이라 그
    시나리오 목록·도면에서도 숨는다). 못 읽으면 덧줄 없이 둔다(확인을 막지 않는다)."""
    lines: list[str] = []
    for label, _ in shown:
        key = floor_from_label(label)
        if key is None:
            continue
        try:
            counts = load_layout_overlay_floor_counts(database_path, *key)
        except BOOTSTRAP_ERRORS:
            continue
        for name, count in counts:
            lines.append(
                f"가정 설비 시나리오 「{name}」 의 배치에서 {label} 에 놓인 호기 {count}대도 그 "
                "시나리오 목록·도면에서 숨습니다."
            )
    return lines


def _render_buildings(draft: Draft) -> None:
    """동 머리 줄 — 동마다 「사용 · 사용 안 함 · 생산라인 아님」. 값은 회차마다 초안에서 세션에
    적는다(`default=` 없음, key 에 세대 없음). 섞인 동은 고른 것 없음 + 「사용 4/6」."""
    generation = _generation()
    with st.container(
        horizontal=True,
        gap="medium",
        vertical_alignment="bottom",
        key="space_floor_state_buildings",
    ):
        for building in VALID_BUILDINGS:
            key = f"{_BULK_PREFIX}{building}"
            state = building_state(draft, building)
            st.session_state[key] = state
            if state is None:
                active, total = building_active_count(draft, building)
                label = f"{building} · 사용 {active}/{total}"
            else:
                label = building
            st.segmented_control(
                label,
                options=list(_BULK_LABELS),
                format_func=_BULK_LABELS.__getitem__,
                key=key,
                on_change=_bulk_changed,
                args=(building, generation),
            )


def _render_editor(
    draft: Draft,
    counts: Mapping[FloorKey, int],
    placements: Mapping[FloorKey, FloorPlacement],
) -> None:
    """30줄 편집표. 줄 차례는 `FLOOR_KEYS` 고정이고 늘 접은 초안을 그린다. `사유` 칸은 `string` 으로
    고정한다 — 모든 층이 사용이면 None 뿐이라 Arrow `null` 이 되고, 첫 끄기에 `string` 으로 바뀌면
    위젯 서명이 달라져 새 위젯이 선다(보던 스크롤·초점이 사라진다)."""
    frame = pd.DataFrame(
        [
            {
                "동": key[0],
                "층": key[1],
                _USE_COLUMN: key not in draft,
                _REASON_COLUMN: (
                    FLOOR_REASON_CHOICES.get(draft[key], inactive_label(draft[key]))
                    if key in draft
                    else None
                ),
                _UNITS_COLUMN: int(counts.get(key, 0)),
                "배치대수": placements[key].placed if key in placements else 0.0,
                "미배치대수": placements[key].unplaced if key in placements else 0.0,
            }
            for key in FLOOR_KEYS
        ]
    ).astype({_REASON_COLUMN: "string"})
    st.data_editor(
        frame,
        key=editor_widget_key(EDITOR_KEY),
        hide_index=True,
        width="stretch",
        num_rows="fixed",
        placeholder="",
        disabled=["동", "층", _UNITS_COLUMN, "배치대수", "미배치대수"],
        column_config={
            _USE_COLUMN: st.column_config.CheckboxColumn(help=_USE_HELP),
            _REASON_COLUMN: st.column_config.SelectboxColumn(
                options=list(FLOOR_REASON_CHOICES.values()),
                help="비활성 층의 사유입니다. 사용 층에서 사유를 고르면 그 사유로 끕니다.",
            ),
            _UNITS_COLUMN: st.column_config.NumberColumn(format="%d", help=_UNITS_HELP),
            "배치대수": st.column_config.NumberColumn(format="localized", help=_PLACED_HELP),
            "미배치대수": st.column_config.NumberColumn(format="localized", help=_UNPLACED_HELP),
        },
    )


def _render_edit(
    database_path: str,
    placements: Sequence[FloorPlacement],
    unit_counts: Callable[[], Mapping[FloorKey, int]],
) -> None:
    """편집 — 저장 줄 · 확인 칸 · 알림 · 동 머리 · 편집표(적용·저장 단추는 편집표 위)."""
    if _stored_base() is None or _stored_draft() is None:
        # 토글을 거치지 않고 켜진 세션(시험·옛 세션) — 지금 저장본으로 시작한다.
        _start(load_floor_states(database_path))
    draft = _fold()
    base = _stored_base()
    assert base is not None
    counts = dict(unit_counts())
    count_labels = {floor_label(key): count for key, count in counts.items()}
    saved = _base_draft(base)
    changed = sum(1 for key in FLOOR_KEYS if draft.get(key) != saved.get(key))
    with st.container(
        horizontal=True, gap="small", vertical_alignment="center", key="space_floor_state_save_row"
    ):
        # 잠가 그리지 않는다 — 칸을 고친 회차와 누른 회차가 같으면 잠긴 단추의 누름을 버린다(9장).
        st.button(
            "저장",
            type="primary",
            icon=":material/save:",
            key=SAVE_BUTTON_KEY,
            on_click=_save,
            args=(database_path, _generation(), count_labels),
        )
        st.button(
            "되돌리기",
            icon=":material/undo:",
            key=REVERT_BUTTON_KEY,
            on_click=_revert,
            args=(_generation(),),
        )
        st.caption(
            f"바뀐 층 {changed}개 · 저장하면 모두의 Space 화면에 반영됩니다(설비 리비전은 만들지 "
            "않습니다). 도면은 저장하면 바뀝니다. 저장하지 않고 층을 열면 고친 것은 버려집니다.",
            width="content",
        )
    with st.container(key="space_floor_state_confirm_slot"):
        _render_confirm(database_path, count_labels)
    # 알림 칸은 늘 선다(성공·충돌·오류가 생기고 사라질 때 아래 묶음이 밀리지 않게).
    with st.container(key="space_floor_state_notices"):
        _render_notices()
    _render_buildings(draft)
    _render_editor(draft, counts, {placement.key: placement for placement in placements})


def render_space_floor_list(
    *,
    database_path: str,
    placements: Sequence[FloorPlacement],
    floors_with_image: Collection[FloorKey],
    canvas_text: Callable[[FloorKey], str],
    states: FloorStates,
    unit_counts: Callable[[], Mapping[FloorKey, int]],
    editable: bool,
    on_open: Callable[[FloorKey], None],
    locked_reason: str | None = None,
    extra_columns: Mapping[FloorKey, Mapping[str, object]] | None = None,
) -> None:
    """FAB 전체 아래 층 목록. `states` 는 이 회차에 읽은 층 사용 상태(보기 표·도면과 같은 값)이고,
    `unit_counts` 는 편집 모드 본문에서만 부른다(층별 설비 대수 — 공식 배치 기준, 끄기 확인의 n).
    `editable` 이 거짓이면(샘플 fleet·가정 설비 시나리오) `사용 편집` 을 잠그고 값도 끈다 —
    `locked_reason` 이 풍선이다(없으면 샘플 문구). `extra_columns` 는 색 기준 「필요 단축」 을 켠
    동안만 사용 층 표에 붙는 칸 넷(층 → 칸 → 값)이다 — 끈 동안 None 이라 표가 그대로다."""
    with st.container(
        horizontal=True, gap="small", vertical_alignment="center", key="space_floor_list_head"
    ):
        st.caption("층 목록 · 행을 고르면 그 층이 열립니다.", width="content")
        st.space("stretch")
        if not editable:
            # 켜진 채 잠그면 스위치와 화면이 서로 다른 말을 한다(FAB `배치 편집` 과 같은 까닭).
            st.session_state[EDIT_TOGGLE_KEY] = False
        editing = (
            st.toggle(
                "사용 편집",
                key=EDIT_TOGGLE_KEY,
                disabled=not editable,
                on_change=_toggle_changed,
                args=(database_path,),
                help=(locked_reason or SAMPLE_LOCKED) if not editable else _TOGGLE_HELP,
            )
            and editable
        )
    if not editing:
        # 토글은 FAB 화면을 그리지 않는 회차(층을 열었을 때·다른 페이지)에 위젯 상태가 버려져 꺼진
        # 채 돌아온다 — 남은 초안을 지워 「저장 안 한 편집」 표지가 거짓을 말하지 않게.
        _forget()
    if editing:
        _render_edit(database_path, placements, unit_counts)
        return
    # 알림 칸은 늘 선다(저장 flash 가 생기고 사라질 때 아래 표가 밀리지 않게).
    with st.container(key="space_floor_state_notices"):
        _render_notices()
    _render_tables(
        placements, floors_with_image, canvas_text, states, on_open, extra_columns=extra_columns
    )
