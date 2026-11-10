# Purpose: 화면들이 세션 동안 같이 쓰는 공정 값 하나와 그 값을 읽고 쓰는 규칙을 한 곳에 가둔다.

"""공용 공정 칸(2026-11-08 사용자 답 P1 · P2 — 공정 공유 1차).

HOME 에서 좁힌 공정이 기준 정보 · 산출 결과 · 가용설비 Main · Space 표에도 걸리게 하는 값 하나다.
**앱을 연 동안만 산다** — DB · 리비전 · 공용 프로필에 쓰지 않고, 새로고침하면 사라진다(조회기간과
같은 꼴 · 설계 규칙 UI-STA-04 「작업 대상 · 도구 입력은 세션까지」).

**이 모듈 밖에서 세션 키를 만지지 않는다.** 화면은 아래 공개 함수만 부른다(값 칸 · 팝업 · 머리 띠
칩 · 화면 탭 표지의 글과 data 는 `components/process_field.py`). 사용자 메모(2026-11-08) — 「공정
선택을 공용화하는게 앞으로 기능 추가할때도 주의깊게 봐야하는 요소일것같은데, 계속 모니터링해보고
적절치 않다고 판단되면 다른 구조로 바꾸거나 원복을 검토해야겠음」. 되돌릴 때는 이 모듈 ·
`process_field.py` 와 그 둘을 부르는 줄만 걷고 화면마다 고르는 칸을 되살린다.

값과 읽는 법:

- 값은 **원본 공정명**의 차례 있는 목록이다. 빈 목록이면 「고르지 않음」 — 화면은 전체를 보인다.
  보내는 화면이 보이는 글자(표시명)를 함께 주면 표시명 화면의 머리 띠 칩이 그 글자로
  읽는다(`labels` — 없으면 공용 표시명 프로필, `process_field._label_of`). 원본
  이름으로 그리는 화면(`ORIGINAL_NAME_SCREENS` — Space)에서는 칩 · 판 · 그 탭 풍선도 원본이다(한
  화면 한 이름).
- 화면은 「그 화면에 있는 공정」 만 읽는다(`applied`). 글자(표시명 · Space 원본)는 그 화면 규칙을
  따른다. 그 화면에 없는 공정은 **지우지 않는다** — 그 화면은 전체를 보이고 「없는 공정」 표지를
  단다(`missing`). 리비전을 바꿔 사라진 공정이 돌아오면 다시 걸린다.
- 칩 칸 같은 위젯 key 에 값을 넣어 주지 않는다. 시제품(2026-11-07)에서 그 칸이 없는 화면을 지나면
  위젯이 값을 깎아 화면끼리 어긋났다 — 이 값은 위젯이 아닌 세션 칸이라 어느 화면을 지나도 그대로다.

잇는 규칙(P2 다섯 · 2026-11-08, 3 은 2026-11-09 보드 C2 (가)로 고침):

1. **HOME 은 보내기만** — HOME 「선택 공정 적용」 뒤 `publish_from_home(included, options)` 를
   부른다. 모두 켰으면 값을 지우고, 좁혔으면 그 공정을 복사한다. 다른 화면에서 고른 값은 HOME B/N
   판정과 리비전 저장값(`PROCESS_SELECTION_KEY`)에 들지 않는다 — HOME 은 이 값을 읽지 않는다.
2. **여러 개 따라감**(표를 거르는 칸 — 기준 정보 편집 표 · 설비대수 현황 · 산출 결과 셋 · 가용설비
   Main · Space) — 그리는 회차마다 `applied(options)` 로 거르고, 그 화면 팝업의 「적용」 은
   `apply_from_screen(chosen, options, screen)` 이다(이 화면에 없는 값은 남긴다). 이 화면 공정을
   모두 켜고 적용하면 이 화면 몫은 고르지 않은 것(전체)이다 — HOME 「적용」 과 같은 규칙. 값 칸 ·
   팝업은 `process_field.render_process_filter` 가 한 벌로 그린다.
3. **하나 따라감 — 직접 고른 것만 보낸다**(공정 Capa 상세 · 제약 시뮬레이션) — 공정 · 달을 정하는
   자리에서 `follow_single(screen, options, entered=…)` 를 부른다. 값이 바뀐 뒤 처음 그 화면을
   그리는 회차에, 공용 값이 **하나**이고 그 화면 목록에 있으면 그 공정을 돌려준다(여럿이면 None —
   보던 공정을 둔다). HOME 그림 칸 · 카드 링크 · 주소 `process` 로 들어온 회차(`entered=True`)는
   들어온 길이 이기고 이번 값은 본 것으로 친다. **사이드바 「공정」 칸 팝업에서 사용자가 직접 고른
   공정만** 공용 값을 그 하나로 바꾼다(`pick_single` — 2026-11-09 보드 C2 (가)). 들어온 길 · 처음 열
   때의 기본 공정 · 따라 연 공정 · ◀▶ 넘김은 보내지 않는다 — 한 공정을 들여다본 일로 3공정 거름이
   사라지지 않게. 값 칸은 `process_field.render_process_choice`.
4. **저장 기본값은 건드리지 않는다** — 필요 단축 일정 공정 필터(설비 `0019`)와 표준 목표 저장 칸에
   값을 넣지 않는다(AGENTS 5장 9 · 12). 2차에서 잇는 화면도 「강조로만 · 표만 좁힘」 이다.
5. **Static Capa 는 전체, 실적 셋 · Dynamic · 재공은 데이터 연결 뒤**(3차) — 잇지 않는다.

표지(2026-11-09 보드 C1 (라)): 걸린 화면은 사이드바 값 칸 강조로, 앱 전체는 머리 띠 「공정」 칩
(누르면 판 — 「모든 화면에서 해제」 는 `clear`)과 화면 탭 표지로 알린다. 따라가는 화면은 이 모듈의
선언 한 곳(`FOLLOWERS` — 페이지 파일 → 출처 이름 · 갈래)이고, 탭 표지는 그 화면이 마지막으로 그린
선택지(`note_drawn` → `screen_mark`)로 없는 공정을 가른다. 출처 글은 값이 그 화면에 실제로 걸렸을
때만 단다(`origin_for`). 편집 표가 거름 밖 초안을 셀 때는 `count_outside(processes, options)`
다(기준 정보 「거름 밖 n개」).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

import streamlit as st

# 세션 칸. 이 모듈 밖에서 읽거나 쓰지 않는다.
_VALUES_KEY = "shared_process_values"
_ORIGIN_KEY = "shared_process_origin"
# 보내는 화면이 준 보이는 글자(`{원본: 글자}` — 지금 값의 것만).
_LABELS_KEY = "shared_process_labels"
# 값이 바뀔 때마다 오르는 수 — 하나 고름 화면이 「바뀐 뒤 처음 그리는 회차」 를 가른다.
_VERSION_KEY = "shared_process_version"
# 하나 고름 화면마다 마지막으로 본 판(`{화면: 판}`)과 따라 연 공정(`{화면: 공정}`).
_SEEN_KEY = "shared_process_seen"
_FOLLOWED_KEY = "shared_process_followed"
# 따라가는 화면마다 마지막으로 그린 선택지(`{화면: Drawn}`) — 화면 탭 표지 · 머리 칩이 읽는다.
_DRAWN_KEY = "shared_process_drawn"

# HOME 이 보낸 값의 출처 이름(칩 · 이름 줄의 「HOME 에서」).
HOME = "HOME"

# 따라가는 갈래 — 여러 개 따라감(표를 거름)과 하나 따라감(공정 하나를 봄).
MULTI: Final = "multi"
SINGLE: Final = "single"

# 공용 값을 따라가는 화면의 선언 한 곳 — 페이지 파일 → (출처 이름, 갈래). 화면 탭 표지 · 머리 띠
# 칩이 이 선언으로 따라가는 화면을 가른다. 출처 이름은 그 화면이 값 칸에 주는 `screen` 과 같다(그물
# `tests/test_shared_process.py`). 새 화면을 이으면 여기에 한 줄을 더한다.
FOLLOWERS: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        "app_pages/reference_data.py": ("기준 정보", MULTI),
        "app_pages/calculation_result.py": ("산출 결과", MULTI),
        "app_pages/available_equipment_status.py": ("가용설비", MULTI),
        "app_pages/space_status.py": ("Space", MULTI),
        "app_pages/process_capa_detail.py": ("공정 Capa 상세", SINGLE),
        "app_pages/constraint_simulation.py": ("제약 시뮬레이션", SINGLE),
    }
)
# 따라가는 화면 가운데 공정을 원본 이름으로 그리는 화면(페이지 파일 — 값 칸을 `labels` 없이
# 그린다). 그 화면에서는 머리 띠 칩 · 칩 판도 보낸 화면의 표시명이 아니라 원본 이름으로
# 적는다(2026-11-10 보드 Q-3 — 한 화면 한 이름, 설계 규칙 UI-CON-02). 그물
# `tests/test_shared_process.py`.
ORIGINAL_NAME_SCREENS: Final[frozenset[str]] = frozenset({"app_pages/space_status.py"})


@dataclass(frozen=True)
class Drawn:
    """한 화면이 마지막으로 그린 공정 칸 — 갈래 · 선택지(원본) · 하나 고름이면 지금 공정."""

    mode: str
    options: tuple[str, ...]
    selected: str | None = None


@dataclass(frozen=True)
class ScreenMark:
    """지금 공용 값이 한 화면에 어떻게 걸리나 — 화면 탭 표지 · 머리 칩의 근거.

    - `drawn` — 이 세션에 그 화면을 그린 적이 있나(없으면 아래 둘은 짐작이다 — 탭 표지는 청록).
    - `follows` — 지금 값이 그 화면이 따르는 꼴인가(여러 개 따라감은 늘, 하나 따라감은 값이 하나일
      때).
    - `on` — 그 화면에 실제로 걸리나(여러 개는 걸리는 공정이 있을 때, 하나는 그 공정을 보고 있을
      때).
    - `inside` · `missing` — 그 화면 선택지에 있는 값 · 없는 값(원본, 고른 차례).
    """

    screen: str
    drawn: bool
    follows: bool
    on: bool
    inside: tuple[str, ...]
    missing: tuple[str, ...]


def values() -> tuple[str, ...]:
    """지금 공용 값(원본 공정명, 고른 차례). 비었으면 고르지 않은 것이다."""
    saved = st.session_state.get(_VALUES_KEY)
    if not isinstance(saved, (list, tuple)):
        return ()
    return tuple(str(value) for value in saved)


def labels() -> tuple[str, ...]:
    """지금 값의 보이는 글자(`values` 와 같은 차례). 보낸 화면이 글자를 주지 않은 값은 원본이다."""
    saved = st.session_state.get(_LABELS_KEY)
    mapping = saved if isinstance(saved, Mapping) else {}
    return tuple(str(mapping.get(value) or value) for value in values())


def origin() -> str:
    """값을 마지막으로 정한 화면 이름. 값이 비었으면 빈 글자다."""
    saved = st.session_state.get(_ORIGIN_KEY)
    return str(saved) if values() and isinstance(saved, str) else ""


def version() -> int:
    saved = st.session_state.get(_VERSION_KEY, 0)
    return saved if isinstance(saved, int) else 0


def publish(
    chosen: Iterable[object], screen: str, *, labels: Mapping[str, str] | None = None
) -> None:
    """공용 값을 `chosen` 으로 바꾼다(겹친 값은 하나로). 빈 값이면 지운 것이다.

    `labels` 는 보내는 화면의 보이는 글자(`{원본: 글자}`)다. 주지 않은 값은 앞서 받은 글자를 잇고,
    그것도 없으면 원본이다.
    """
    cleaned = [
        text for text in dict.fromkeys(str(value).strip() for value in chosen if value is not None)
    ]
    cleaned = [text for text in cleaned if text]
    saved = st.session_state.get(_LABELS_KEY)
    known = dict(saved) if isinstance(saved, Mapping) else {}
    known.update({str(key): str(text) for key, text in (labels or {}).items() if text})
    st.session_state[_LABELS_KEY] = {value: known[value] for value in cleaned if value in known}
    if cleaned == list(values()) and (not cleaned or origin() == screen):
        return
    st.session_state[_VALUES_KEY] = cleaned
    st.session_state[_ORIGIN_KEY] = screen if cleaned else ""
    st.session_state[_VERSION_KEY] = version() + 1


def clear() -> None:
    """공용 값을 지운다 — 머리 띠 칩 판 「모든 화면에서 해제」 · 팝업 「전체」."""
    publish((), "")


def publish_from_home(
    included: Iterable[object],
    options: Sequence[object],
    *,
    labels: Mapping[str, str] | None = None,
) -> None:
    """HOME 「선택 공정 적용」 뒤 — 이번 선택지 가운데 켠 공정을 복사한다(한쪽 방향).

    모두 켰으면 지운다(전체). 이번 조회기간에 보이지 않던 공정(HOME 세션 값에만 남은 것)은 보내지
    않는다 — HOME 화면에서 고른 것만 보낸다. `labels` 는 HOME 팝업의 보이는 글자다.
    """
    allowed = [str(option) for option in options]
    picked = {str(value) for value in included}
    chosen = [option for option in allowed if option in picked]
    publish([] if len(chosen) >= len(allowed) else chosen, HOME, labels=labels)


def inside(options: Iterable[object]) -> list[str]:
    """공용 값 가운데 이 화면 목록에 있는 것(목록 차례)."""
    held = set(values())
    return [text for text in dict.fromkeys(str(option) for option in options) if text in held]


def missing(options: Iterable[object]) -> list[str]:
    """공용 값 가운데 이 화면 목록에 없는 것(고른 차례)."""
    allowed = {str(option) for option in options}
    return [value for value in values() if value not in allowed]


def applied(options: Iterable[object]) -> list[str]:
    """여러 개 따라감 화면이 거는 공정. 빈 목록이면 전체다 — 걸리는 것이 없어도 빈 화면을 만들지
    않는다."""
    return inside(options)


def apply_from_screen(
    chosen: Iterable[object],
    options: Iterable[object],
    screen: str,
    *,
    labels: Mapping[str, str] | None = None,
) -> None:
    """여러 개 따라감 화면의 팝업 「적용」. 이 화면에 없어 건드릴 수 없었던 값은 남긴다.

    이 화면 공정을 모두 켰으면 이 화면 몫은 고르지 않은 것(전체)이다 — `publish_from_home` 처럼
    모두 켠 목록을 값으로 남기지 않는다. 명시 목록으로 남으면 리비전을 바꿔 새로 들어온 공정이
    따라가는 화면마다 걸러져 보이지 않는다. 남길 값도 없으면 공용 값이 지워진다.
    """
    allowed = {str(option) for option in options}
    picked = [str(value) for value in chosen if str(value) in allowed]
    if allowed and allowed <= set(picked):
        picked = []
    publish([*picked, *missing(allowed)], screen, labels=labels)


def origin_for(screen: str) -> str | None:
    """이 화면에 걸린 값의 출처 이름 — 다른 화면에서 왔을 때만. 부르는 쪽이 걸렸는지 먼저 본다."""
    source = origin()
    return source if source and source != screen else None


def _screen_map(key: str) -> dict[str, object]:
    saved = st.session_state.get(key)
    return dict(saved) if isinstance(saved, Mapping) else {}


def follow_single(screen: str, options: Sequence[object], *, entered: bool) -> str | None:
    """하나 고름 화면이 공정을 정하기 **전에** 부른다. 따라 열 공정이면 그 공정, 아니면 None.

    - `entered` — 이 회차에 HOME 그림 칸 · 카드 링크 · 주소로 공정이 들어왔다. 들어온 길이 이긴다:
      이번 값은 본 것으로 치고 따라 연 표지도 걷는다.
    - 값이 바뀐 뒤 이 화면을 처음 그리는 회차에, 공용 값이 **하나**이고 이 화면 목록에 있으면 그
      공정이다(P2-2 「공용 값이 하나일 때 그 공정을 열고, 여럿이면 보던 공정을 둡니다」 — 이 화면에
      걸리는 것이 하나뿐이어도 값이 여럿이면 열지 않는다). 아니면 None(보던 공정). 하나인데 목록에
      없으면 본 것으로 치지 않아 목록이 바뀌어(리비전 전환) 그 공정이 들어오면 그때 연다.
    """
    seen = _screen_map(_SEEN_KEY)
    followed = _screen_map(_FOLLOWED_KEY)
    current = version()
    if entered:
        seen[screen] = current
        followed.pop(screen, None)
        st.session_state[_SEEN_KEY] = seen
        st.session_state[_FOLLOWED_KEY] = followed
        return None
    if seen.get(screen) == current:
        return None
    held = values()
    if len(held) != 1:
        return None
    if held[0] not in {str(option) for option in options}:
        return None
    seen[screen] = current
    followed[screen] = held[0]
    st.session_state[_SEEN_KEY] = seen
    st.session_state[_FOLLOWED_KEY] = followed
    return held[0]


def pick_single(screen: str, process: object, *, labels: Mapping[str, str] | None = None) -> None:
    """하나 고름 화면의 사이드바 「공정」 칸 팝업에서 **사용자가 직접 고른** 공정을
    보낸다(2026-11-09 보드 C2 (가)). 공용 값이 그 하나가 되고(출처 = 이 화면), 이 화면은 그 값을 본
    것 · 따라 연 것으로 친다 — 다음 회차에 같은 공정을 다시 「따라 열지」 않고, 값 칸 강조 · 머리
    칩이 이 화면에 걸린 것으로 읽는다. 들어온 길 · 기본 공정 · 따라 연 공정은 이 함수를 부르지
    않는다."""
    picked = str(process)
    publish([picked], screen, labels=labels)
    seen = _screen_map(_SEEN_KEY)
    followed = _screen_map(_FOLLOWED_KEY)
    seen[screen] = version()
    followed[screen] = picked
    st.session_state[_SEEN_KEY] = seen
    st.session_state[_FOLLOWED_KEY] = followed


def single_applied(screen: str, selected: object) -> bool:
    """하나 고름 화면에서 지금 공정이 공용 값을 따라 연(또는 여기서 보낸) 공정인가 — 표지(강조 ·
    출처)를 다는 조건. 이 화면에서 다른 공정으로 넘기거나 들어온 길로 열었으면 거짓이다."""
    if selected is None:
        return False
    process = str(selected)
    return _screen_map(_FOLLOWED_KEY).get(screen) == process and process in values()


def note_drawn(
    screen: str, mode: str, options: Iterable[object], selected: object | None = None
) -> None:
    """따라가는 화면이 공정 칸을 그린 회차에 그 선택지를 적는다 — 화면 탭 표지가 「그 화면이
    마지막으로 그린 선택지」 로 없는 공정을 가른다. 같은 것이면 쓰지 않는다."""
    drawn = Drawn(
        mode=mode,
        options=tuple(dict.fromkeys(str(option) for option in options)),
        selected=None if selected is None else str(selected),
    )
    record = _screen_map(_DRAWN_KEY)
    if record.get(screen) == drawn:
        return
    record[screen] = drawn
    st.session_state[_DRAWN_KEY] = record


def screen_mark(screen: str, mode: str) -> ScreenMark | None:
    """지금 공용 값이 이 화면에 어떻게 걸리나. 값이 없으면 None 이다.

    그 화면을 아직 그리지 않았으면 선택지를 몰라 「모두 있음」 으로 짐작한다(`drawn=False`). 하나
    따라감은 값이 하나일 때만 따르고, 그 값을 아직 보지 않았으면(값이 바뀐 뒤 그 화면을 그리지 않음)
    목록에 있는지로, 보았으면 지금 보는 공정이 그 값인지(`single_applied`)로 건다.
    """
    held = values()
    if not held:
        return None
    follows = mode == MULTI or len(held) == 1
    saved = _screen_map(_DRAWN_KEY).get(screen)
    if not isinstance(saved, Drawn):
        return ScreenMark(screen, False, follows, follows, held if follows else (), ())
    allowed = set(saved.options)
    absent = tuple(value for value in held if value not in allowed)
    if mode == MULTI:
        hits = tuple(inside(saved.options))
        return ScreenMark(screen, True, True, bool(hits), hits, absent)
    if not follows:
        return ScreenMark(screen, True, False, False, (), absent)
    if _screen_map(_SEEN_KEY).get(screen) == version():
        on = single_applied(screen, saved.selected)
    else:
        on = held[0] in allowed
    return ScreenMark(screen, True, True, on, (held[0],) if on else (), absent)


def count_outside(processes: Iterable[object], options: Iterable[object]) -> int:
    """`processes`(초안이 있는 공정 등) 가운데 지금 걸린 공용 값에 가려 이 화면에 안 보이는 수.

    걸린 값이 없으면(전체를 보이면) 0 이다 — 기준 정보 편집 표의 「거름 밖 n개」 표지.
    """
    shown = set(applied(options))
    if not shown:
        return 0
    return len({str(process) for process in processes} - shown)
