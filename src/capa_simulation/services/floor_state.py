# Purpose: Space 동·층 사용 상태의 모델·사유 글 검증·층 고르기 거르기·층별 호기 셈 규칙을 둔다.

"""Space 동·층 사용 상태(2026-10-24 사용자 결정 S1~S6).

저장은 설비 DB 의 `equipment_ops.floor_state_profile`·`floor_state`(설비 `0029`)이고 SQL 은
`persistence/floor_state_store.py` 가 갖는다. 이 모듈은 Streamlit·DB 를 모르는 규칙만 둔다.

- 층마다 「사용」(기본, 행 없음) 또는 「비활성」 하나다. 비활성에는 늘 사유가 붙는다 — 사람이
  직접 적는 글(앞뒤 공백을 뗀 20자까지, 제어 문자·줄바꿈 없음 — 2026-10-26 결정)을 `reason` 칸에
  그대로 저장한다. 비우고 끄면 `UNUSED`(사용 안 함)다. 옛 고르기 코드 `UNUSED`·`NOT_LINE`(생산라인
  아님)은 지금 글 그대로 보이고, 그 짧은 글이나 코드 글자를 그대로 적으면 그 코드로 저장한다
  (`floor_reason_code` — 저장된 글로는 옛 코드와 가를 수 없어 「UNUSED」 도 「사용 안 함」 으로
  보인다).
- 모두에게 같은 공용 현행값이고 설비 시나리오·설비 리비전과 무관하다(S6).
- **저장 검사는 그대로다**(S5) — 설비 마스터의 동·층 범위(C1~C5·1F~6F)는 비활성 층도 통과한다.
  비활성은 Space 목록·도면과 층 고르기(층 바로 가기·「다른 층으로 보내기」·설비 마스터 탭 동·층
  칸)에서만 숨긴다.
- 읽기는 관용이다 — 저장소가 읽은 행에 모르는 동·층이 있으면 버리고, 사유 글은 길이를 보지 않고
  그대로 그린다(`inactive_label` — 빈 사유만 「비활성」, 제어 문자는 빈칸). 편집표 칸만은 저장할
  글을 제어 문자까지 그대로 싣는다(`reason_cell_text` — `저장` 이 거절한 글을 칸에서 보고 고치게).
  저장 입구(`prepare_floor_states`)만 엄격하다. 사유 글은 사람 글이라 마크다운 자리에서는 그리는
  쪽이 막는다(`literal_markdown`) — 이 모듈은 글을 고치지 않는다(짝 없는 서로게이트만 뗀다 —
  `floor_reason_code`).
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import pandas as pd

from capa_simulation.services.equipment_contract import (
    EQUIPMENT_ID_COLUMN,
    LAYOUT_EXITED_COLUMN,
    VALID_BUILDINGS,
    VALID_FLOORS,
)
from capa_simulation.services.equipment_units import unit_keys
from capa_simulation.services.fab_layout import FLOOR_KEYS, floor_label
from capa_simulation.services.floor_layout_profile import FloorKey

__all__ = [
    "ACTIVE_STATE",
    "DEFAULT_FLOOR_REASON",
    "FLOOR_REASONS",
    "FLOOR_REASON_EXAMPLES",
    "FLOOR_REASON_LABELS",
    "FLOOR_REASON_MAX_CHARS",
    "FloorStates",
    "building_active_count",
    "building_state",
    "floor_reason_code",
    "floor_reason_refusal",
    "floor_states_fingerprint",
    "floor_unit_counts",
    "floors_by_building",
    "inactive_floor_summary",
    "inactive_floor_warnings",
    "inactive_label",
    "master_location_options",
    "newly_inactive",
    "prepare_floor_states",
    "present_location_values",
    "reason_cell_text",
    "selectable_floor_keys",
    "with_building",
]

# 고르기였던 때(2026-10-24 S1)의 사유 코드 — 지금도 동 머리 줄 값이고, 저장된 행은 아래 글로 보인다.
FLOOR_REASONS: Final = ("UNUSED", "NOT_LINE")
# 코드의 글 — 도면 블록·목록 표·편집표·풍선·배너가 다 이 글이다.
FLOOR_REASON_LABELS: Final[Mapping[str, str]] = {
    "UNUSED": "사용 안 함",
    "NOT_LINE": "생산라인 아님",
}
# 사유 글의 길이 상한(앞뒤 공백을 뗀 글자 수 — 2026-10-26 결정).
FLOOR_REASON_MAX_CHARS: Final = 20
# 편집표 사유 칸 도움말의 예시 두 문구(고르기였던 때의 두 고르기 글).
FLOOR_REASON_EXAMPLES: Final = ("사용 안 함", "생산라인 아님(사무·창고 등)")
# 사유를 비운 채 끈 층(편집표 `사용` 만 끈 칸)은 이 사유다 — 비활성에는 늘 사유가 있다(S1).
DEFAULT_FLOOR_REASON: Final = "UNUSED"
# 동 머리 줄의 「그 동 6개 층 모두 사용」 값. 같은 글을 사유로 적은 층과는 `building_state` 가
# 가른다(동 머리는 코드만 안다).
ACTIVE_STATE: Final = "ACTIVE"
# 빈 사유(손으로 넣은 행)의 글.
_UNKNOWN_REASON_LABEL: Final = "비활성"
# 사유 글에 넣을 수 없는 글자 갈래 — 제어(Cc)·서식(Cf, 방향 바꿈·폭 없는 글자)·줄/문단 나눔(Zl·Zp)·
# 짝 없는 서로게이트(Cs — UTF-8 로 못 싣는다. 편집표 칸에서 온 것은 `floor_reason_code` 가 먼저
# 뗀다).
_REFUSED_CATEGORIES: Final = frozenset({"Cc", "Cf", "Zl", "Zp", "Cs"})
# UTF-16 서로게이트 자리(U+D800~U+DFFF). 파이썬 글에 남은 것은 늘 짝이 없다.
_SURROGATES: Final = range(0xD800, 0xE000)
# 저장 미리보기 경고에 이름을 적는 호기 수.
_WARNING_NAME_LIMIT: Final = 5

FloorRow = tuple[str, str, str]


@dataclass(frozen=True)
class FloorStates:
    """동·층 사용 상태 한 벌. `version` 0 은 한 번도 저장하지 않은 것(모두 사용)이다.

    `rows` 는 비활성 층만의 (동, 층, 사유 — 옛 코드 또는 적은 글)이고 `FLOOR_KEYS` 차례다 — 캐시에
    실리도록 기본형 튜플로 둔다(AGENTS 5장 21). 아래 읽기 도우미는 `rows` 로 정해지는 값이라 필드가
    아니다(캐시는 init 필드만 싣는다).
    """

    rows: tuple[FloorRow, ...] = ()
    version: int = 0
    source: str = ""
    updated_at: datetime | None = None

    @property
    def inactive(self) -> dict[FloorKey, str]:
        """비활성 층 → 사유(옛 코드 또는 적은 글)."""
        return {(building, floor): reason for building, floor, reason in self.rows}

    def reason_of(self, key: FloorKey) -> str | None:
        """그 층의 사유(옛 코드 또는 적은 글). 사용이면 None."""
        return self.inactive.get(key)

    def is_active(self, key: FloorKey) -> bool:
        return key not in self.inactive

    @property
    def active_keys(self) -> tuple[FloorKey, ...]:
        """사용 층(`FLOOR_KEYS` 차례)."""
        inactive = self.inactive
        return tuple(key for key in FLOOR_KEYS if key not in inactive)


def _floor_key(value: object) -> FloorKey | None:
    """(동, 층) 짝이 FAB 의 30개 층이면 그 키, 아니면 None."""
    if not isinstance(value, tuple) or len(value) != 2:
        return None
    key = (str(value[0]), str(value[1]))
    return key if key in FLOOR_KEYS else None


def _refused(char: str) -> bool:
    return unicodedata.category(char) in _REFUSED_CATEGORIES


def _without_surrogates(text: str) -> str:
    return "".join(char for char in text if ord(char) not in _SURROGATES)


def inactive_label(reason: str) -> str:
    """저장된 사유 → 화면 글. 옛 코드는 그 글(「사용 안 함」·「생산라인 아님」), 그 밖의 글은 적은
    글 그대로다(길이는 보지 않는다 — 읽기에서 막지 않는다). 빈 사유는 「비활성」, 제어 문자는
    빈칸으로 그린다. 마크다운 자리에서는 그리는 쪽이 `literal_markdown` 으로 막는다."""
    label = FLOOR_REASON_LABELS.get(reason)
    if label is not None:
        return label
    text = "".join(" " if _refused(char) else char for char in str(reason)).strip()
    return text or _UNKNOWN_REASON_LABEL


def reason_cell_text(reason: str) -> str:
    """편집표 `사유` 칸에 그릴 글. 옛 코드는 그 글, 그 밖에는 저장할 글 그대로다 — 줄바꿈·탭 같은
    제어 문자도 빈칸으로 바꾸지 않는다(`inactive_label` 과 다르다). 바꿔 그리면 보이는 글에는 없는
    글자로 `저장` 이 거절해 무엇을 고칠지 알 수 없다. 빈 사유는 「비활성」, 짝 없는 서로게이트는
    뗀다(Arrow 가 UTF-8 로 싣지 못해 편집표가 깨진다)."""
    label = FLOOR_REASON_LABELS.get(reason)
    if label is not None:
        return label
    return _without_surrogates(str(reason)) or _UNKNOWN_REASON_LABEL


def floor_reason_code(value: object) -> str | None:
    """편집표 사유 칸 값 → 저장할 사유(검증 전). 짝 없는 서로게이트와 앞뒤 공백을 떼고, 비면
    None(사유 없음), 옛 코드의 글과 같으면 그 코드(「사용 안 함」 → `UNUSED`), 그 밖에는 뗀 글
    그대로다.

    서로게이트를 떼는 까닭 — Streamlit 1.63 글 칸의 `max_chars` 는 브라우저가 UTF-16 단위로 자른다.
    이모지(2단위)가 20번째 단위에 걸리면 반쪽만 서버로 오고, 그 글은 Arrow·DuckDB 가 UTF-8 로 싣지
    못한다(편집표가 깨지고 저장은 DB 를 무효로 만든다). 잘린 반쪽은 사람이 적은 글자가 아니다.
    옛 코드 글자(「UNUSED」·「NOT_LINE」)를 그대로 적어도 그 코드다 — 저장된 글로는 옛 코드와 가를
    수 없어 그 글(「사용 안 함」·「생산라인 아님」)로 보인다."""
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NA:
        return None
    text = _without_surrogates(str(value)).strip()
    if not text:
        return None
    for code, label in FLOOR_REASON_LABELS.items():
        if text == label:
            return code
    return text


def floor_reason_refusal(reason: str) -> str | None:
    """저장할 사유 글(앞뒤 공백을 뗀 것)을 받을 수 없으면 그 까닭, 받으면 None. 까닭 글에는 사람
    글을 싣지 않는다(마크다운 자리 알림으로 간다)."""
    if len(reason) > FLOOR_REASON_MAX_CHARS:
        return f"사유는 {FLOOR_REASON_MAX_CHARS}자까지입니다(지금 {len(reason)}자)"
    if any(_refused(char) for char in reason):
        return (
            "사유에 줄바꿈·탭 같은 제어 문자는 넣을 수 없습니다(보이지 않는 글자일 수 있습니다 — "
            "그 칸을 지우고 다시 적으세요)"
        )
    return None


def prepare_floor_states(raw: Mapping[FloorKey, object]) -> tuple[FloorRow, ...]:
    """저장 입구 검증. 비활성 층 → 사유를 `FLOOR_KEYS` 차례의 행으로 돌려준다.

    키는 FAB 의 30개 층이어야 하고, 값은 글이다 — 앞뒤 공백을 떼고 옛 코드의 글은 그 코드로 바꾼
    것(`floor_reason_code`)을 저장한다. 빈 값·None 은 「사용」 이라 행이 없다. 글이 아니거나 받을 수
    없는 글(`floor_reason_refusal`)은 조용히 버리지 않고 `ValueError` 다 — 글에는 층 이름과 까닭만
    싣는다.
    """
    prepared: dict[FloorKey, str] = {}
    for raw_key, value in raw.items():
        key = _floor_key(raw_key)
        if key is None:
            raise ValueError(f"FAB 의 층이 아닙니다: {raw_key!r}")
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"{floor_label(key)} 층 사용 사유는 글이어야 합니다.")
        reason = floor_reason_code(value)
        if reason is None:
            continue
        refusal = floor_reason_refusal(reason)
        if refusal is not None:
            raise ValueError(f"{floor_label(key)} {refusal}.")
        prepared[key] = reason
    return tuple((key[0], key[1], prepared[key]) for key in FLOOR_KEYS if key in prepared)


def floor_states_fingerprint(states: FloorStates) -> str:
    """비활성 층·사유의 지문(FAB 뷰어 epoch). version 은 넣지 않는다 — 같은 내용이면 같다. 사유는
    사람 글이라(가름표 `:`·`|` 가 들 수 있다) JSON 으로 묶는다."""
    payload = json.dumps(states.rows, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _building_keys(building: str) -> tuple[FloorKey, ...]:
    return tuple(key for key in FLOOR_KEYS if key[0] == building)


def building_state(draft: Mapping[FloorKey, str], building: str) -> str | None:
    """동 머리 줄의 지금 값 — 그 동 6개 층이 모두 사용이면 `ACTIVE_STATE`, 모두 같은 옛 코드
    (`FLOOR_REASONS`)면 그 코드, 섞였거나 직접 적은 사유면 None(동 머리는 코드만 고른다 — 「ACTIVE」
    라고 적은 사유가 「모두 사용」 으로 보이지 않는다)."""
    reasons = {draft.get(key) for key in _building_keys(building)}
    if len(reasons) != 1:
        return None
    (only,) = reasons
    if only is None:
        return ACTIVE_STATE
    return only if only in FLOOR_REASONS else None


def building_active_count(draft: Mapping[FloorKey, str], building: str) -> tuple[int, int]:
    """(사용 층 수, 그 동 층 수) — 섞인 동 머리 라벨 「사용 4/6」."""
    keys = _building_keys(building)
    return sum(1 for key in keys if key not in draft), len(keys)


def with_building(
    draft: Mapping[FloorKey, str], building: str, reason: str | None
) -> dict[FloorKey, str]:
    """그 동 6개 층을 한꺼번에 — None(또는 `ACTIVE_STATE`)은 모두 사용, 사유는 모두 그 사유. 다른
    동은 그대로다."""
    result = {key: value for key, value in draft.items() if key[0] != building}
    if reason is not None and reason != ACTIVE_STATE:
        result.update({key: reason for key in _building_keys(building)})
    return {key: result[key] for key in FLOOR_KEYS if key in result}


def newly_inactive(before: FloorStates, draft: Mapping[FloorKey, str]) -> tuple[FloorKey, ...]:
    """저장본에서 사용이던 층 가운데 초안에서 비활성인 것(`FLOOR_KEYS` 차례). 사유만 바꾼 층은
    들지 않는다 — 호기 있는 층 끄기 확인(S4)의 대상이다."""
    saved = before.inactive
    return tuple(key for key in FLOOR_KEYS if key in draft and key not in saved)


def floor_unit_counts(status: pd.DataFrame) -> dict[FloorKey, int]:
    """층마다 아직 그 층에 있는 **설비 대수**(끄기 확인의 n).

    동·층이 그 층이고 도면 이탈(`LAYOUT_EXITED_COLUMN`)이 아닌 행의 설비키 수다 — Main 설비로 묶은
    모듈 행은 1대, 레이아웃표시 Y·N 모두 센다. FAB 의 30개 층 밖 행은 버린다. 행이 없는 층은 키가
    없다. 목록 표 `배치대수`·`미배치대수`(기준일·필터 안·설비지분 합)와 기준이 다르다.
    """
    if status.empty or "동" not in status.columns or "층" not in status.columns:
        return {}
    frame = status
    if LAYOUT_EXITED_COLUMN in frame.columns:
        frame = frame.loc[~frame[LAYOUT_EXITED_COLUMN].fillna(False).astype(bool)]
    if frame.empty or EQUIPMENT_ID_COLUMN not in frame.columns:
        return {}
    keys = unit_keys(frame)
    buildings = frame["동"].astype("string").str.strip()
    floors = frame["층"].astype("string").str.strip()
    counts: dict[FloorKey, set[str]] = {}
    for building, floor, unit in zip(buildings, floors, keys, strict=True):
        if pd.isna(building) or pd.isna(floor) or pd.isna(unit) or not str(unit):
            continue
        key = (str(building), str(floor))
        if key in FLOOR_KEYS:
            counts.setdefault(key, set()).add(str(unit))
    return {key: len(counts[key]) for key in FLOOR_KEYS if key in counts}


def selectable_floor_keys(
    states: FloorStates, *, keep: FloorKey | None = None
) -> tuple[FloorKey, ...]:
    """고를 수 있는 층 = 사용 층 + `keep`(지금 연 층이 비활성이면 그 층). `FLOOR_KEYS` 차례.

    `층 바로 가기`·`다른 층으로 보내기` 가 같이 쓴다.
    """
    inactive = states.inactive
    return tuple(key for key in FLOOR_KEYS if key not in inactive or key == keep)


def floors_by_building(states: FloorStates) -> dict[str, tuple[str, ...]]:
    """동 → 사용 층(`VALID_FLOORS` 차례). 사용 층이 하나도 없는 동도 빈 튜플로 든다."""
    inactive = states.inactive
    return {
        building: tuple(
            floor
            for floor in VALID_FLOORS
            if (building, floor) in FLOOR_KEYS and (building, floor) not in inactive
        )
        for building in VALID_BUILDINGS
    }


def _present_values(present: pd.DataFrame, column: str, valid: Iterable[str]) -> set[str]:
    if present.empty or column not in present.columns:
        return set()
    values = set(present[column].dropna().astype("string").str.strip())
    return values & set(valid)


def present_location_values(present: pd.DataFrame) -> tuple[set[str], set[str]]:
    """표에 이미 있는 유효 동·층 값(C1~C5 · 1F~6F 안). 선택지가 꼭 품어야 하는 값이다."""
    return (
        _present_values(present, "동", VALID_BUILDINGS),
        _present_values(present, "층", VALID_FLOORS),
    )


def master_location_options(
    states: FloorStates, present: pd.DataFrame
) -> tuple[list[str], list[str]]:
    """설비 마스터 편집표 동·층 **칸 단위** 선택지(동 목록, 층 목록).

    동 = 사용 층이 하나라도 있는 동 ∪ 표에 이미 있는 유효 동, 층 = 어느 동에서든 사용인 층 ∪ 표에
    이미 있는 유효 층. 차례는 `VALID_BUILDINGS`·`VALID_FLOORS` 다. 표에 있는 값을 남기는 까닭 —
    Streamlit 1.63 은 선택지 밖 값을 칸 오류로 그린다(비활성 층에 남은 호기 행이 빨갛게 서면 안
    된다). 동·층이 따로인 칸이라 「C1 + 3F」 처럼 짝만 꺼진 층은 여기서 거르지 못한다.
    """
    active = states.active_keys
    buildings_in_use = {key[0] for key in active} | _present_values(present, "동", VALID_BUILDINGS)
    floors_in_use = {key[1] for key in active} | _present_values(present, "층", VALID_FLOORS)
    return (
        [building for building in VALID_BUILDINGS if building in buildings_in_use],
        [floor for floor in VALID_FLOORS if floor in floors_in_use],
    )


def _floor_runs(floors: Iterable[str]) -> str:
    """「1F·2F·3F·5F」 → 「1F~3F·5F」(`VALID_FLOORS` 차례로 이어진 층을 줄인다)."""
    order = {floor: index for index, floor in enumerate(VALID_FLOORS)}
    ranked = sorted({floor for floor in floors if floor in order}, key=order.__getitem__)
    parts: list[str] = []
    start = previous = None
    for floor in ranked:
        if previous is not None and order[floor] == order[previous] + 1:
            previous = floor
            continue
        if start is not None and previous is not None:
            parts.append(start if start == previous else f"{start}~{previous}")
        start = previous = floor
    if start is not None and previous is not None:
        parts.append(start if start == previous else f"{start}~{previous}")
    return "·".join(parts)


def inactive_floor_summary(states: FloorStates) -> str:
    """비활성 층을 동·사유마다 줄여 적은 글 — 「C1 3F(사용 안 함) · C5 1F~6F(생산라인 아님)」.
    비활성 층이 없으면 빈 글. 사유는 적은 글 그대로다(평문 — 마크다운 자리는 부르는 쪽이 막는다)."""
    parts: list[str] = []
    inactive = states.inactive
    for building in VALID_BUILDINGS:
        by_reason: dict[str, list[str]] = {}
        for key in _building_keys(building):
            reason = inactive.get(key)
            if reason is not None:
                by_reason.setdefault(inactive_label(reason), []).append(key[1])
        for label, floors in by_reason.items():
            parts.append(f"{building} {_floor_runs(floors)}({label})")
    return " · ".join(parts)


def _locations(frame: pd.DataFrame) -> dict[str, FloorKey | None]:
    """설비명 → (동, 층). 동·층이 비면 None."""
    if frame.empty or EQUIPMENT_ID_COLUMN not in frame.columns:
        return {}
    names = frame[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    buildings = (
        frame["동"].astype("string").str.strip()
        if "동" in frame.columns
        else pd.Series(pd.NA, index=frame.index, dtype="string")
    )
    floors = (
        frame["층"].astype("string").str.strip()
        if "층" in frame.columns
        else pd.Series(pd.NA, index=frame.index, dtype="string")
    )
    located: dict[str, FloorKey | None] = {}
    for name, building, floor in zip(names, buildings, floors, strict=True):
        if pd.isna(name) or not str(name):
            continue
        located[str(name)] = (
            None if pd.isna(building) or pd.isna(floor) else (str(building), str(floor))
        )
    return located


def inactive_floor_warnings(
    master: pd.DataFrame,
    saved: pd.DataFrame,
    states: FloorStates,
    *,
    escape: Callable[[str], str] = str,
) -> list[str]:
    """저장 미리보기 경고(막지 않는다). 편집본에서 동·층이 비활성 층이고 저장본과 다른(새 행 포함)
    호기를 한 줄로 말한다. 그대로인 호기는 세지 않는다 — 이미 그 층에 있던 호기다.

    사람 글(사유·호기 이름)은 `escape` 를 지나 끼운다 — 마크다운 자리에 그리는 화면이
    `literal_markdown` 을 넘긴다(이 모듈은 Streamlit 을 모른다)."""
    inactive = states.inactive
    if not inactive:
        return []
    before = _locations(saved)
    moved: dict[str, FloorKey] = {}
    for name, key in _locations(master).items():
        if key is None or key not in inactive:
            continue
        if name in before and before[name] == key:
            continue
        moved[name] = key
    if not moved:
        return []
    floors = [key for key in FLOOR_KEYS if key in set(moved.values())]
    where = " · ".join(
        f"{floor_label(key)} {escape(inactive_label(inactive[key]))}" for key in floors
    )
    names = list(moved)
    shown = ", ".join(escape(name) for name in names[:_WARNING_NAME_LIMIT])
    more = f" 외 {len(names) - _WARNING_NAME_LIMIT}대" if len(names) > _WARNING_NAME_LIMIT else ""
    return [
        f"비활성 층으로 옮긴 호기 {len(names)}대 — 저장은 되지만 Space 목록·도면에서 "
        f"숨습니다({where}): {shown}{more}"
    ]
