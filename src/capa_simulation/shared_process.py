# Purpose: 화면들이 세션 동안 같이 쓰는 공정 값 하나와 그 값을 읽고 쓰는 규칙을 한 곳에 가둔다.

"""공용 공정 칸(2026-11-08 사용자 답 P1 · P2 — 공정 공유 1차).

HOME 에서 좁힌 공정이 기준 정보 · 산출 결과 · 가용설비 Main · Space 표에도 걸리게 하는 값 하나다.
**앱을 연 동안만 산다** — DB · 리비전 · 공용 프로필에 쓰지 않고, 새로고침하면 사라진다(조회기간과
같은 꼴 · 설계 규칙 UI-STA-04 「작업 대상 · 도구 입력은 세션까지」).

**이 모듈 밖에서 세션 키를 만지지 않는다.** 화면은 아래 공개 함수만 부른다(값 칸 · 팝업 · 본문 칩은
`components/process_field.py`). 사용자 메모(2026-11-08) — 「공정 선택을 공용화하는게 앞으로 기능
추가할때도 주의깊게 봐야하는 요소일것같은데, 계속 모니터링해보고 적절치 않다고 판단되면 다른 구조로
바꾸거나 원복을 검토해야겠음」. 되돌릴 때는 이 모듈 · `process_field.py` 와 그 둘을 부르는 줄만 걷고
화면마다 고르는 칸을 되살린다.

값과 읽는 법:

- 값은 **원본 공정명**의 차례 있는 목록이다. 빈 목록이면 「고르지 않음」 — 화면은 전체를 보인다.
- 화면은 「그 화면에 있는 공정」 만 읽는다(`applied`). 글자(표시명 · Space 원본)는 그 화면 규칙을
  따른다. 그 화면에 없는 공정은 **지우지 않는다** — 그 화면은 전체를 보이고 「없는 공정」 표지를
  단다(`missing`). 리비전을 바꿔 사라진 공정이 돌아오면 다시 걸린다.
- 칩 칸 같은 위젯 key 에 값을 넣어 주지 않는다. 시제품(2026-11-07)에서 그 칸이 없는 화면을 지나면
  위젯이 값을 깎아 화면끼리 어긋났다 — 이 값은 위젯이 아닌 세션 칸이라 어느 화면을 지나도 그대로다.

잇는 규칙(P2 다섯 · 2026-11-08):

1. **HOME 은 보내기만** — HOME 「선택 공정 적용」 뒤 `publish_from_home(included, options)` 를
   부른다. 모두 켰으면 값을 지우고, 좁혔으면 그 공정을 복사한다. 다른 화면에서 고른 값은 HOME B/N
   판정과 리비전 저장값(`PROCESS_SELECTION_KEY`)에 들지 않는다 — HOME 은 이 값을 읽지 않는다.
2. **여러 개 따라감**(표를 거르는 칸 — 기준 정보 편집 표 · 설비대수 현황 · 산출 결과 셋 · 가용설비
   Main · Space) — 그리는 회차마다 `applied(options)` 로 거르고, 그 화면 팝업의 「적용」 은
   `apply_from_screen(chosen, options, screen)` 이다(이 화면에 없는 값은 남긴다). 이 화면 공정을
   모두 켜고 적용하면 이 화면 몫은 고르지 않은 것(전체)이다 — HOME 「적용」 과 같은 규칙. 값 칸 ·
   팝업은 `process_field.render_process_filter` 가 한 벌로 그린다.
3. **하나 따라감 — 받기만**(공정 Capa 상세 · 제약 시뮬레이션) — 공정 · 달을 정하는 자리에서
   `follow_single(screen, options, entered=…)` 를 부른다. 값이 바뀐 뒤 처음 그 화면을 그리는 회차에,
   공용 값이 **하나**이고 그 화면 목록에 있으면 그 공정을 돌려준다(여럿이면 None — 보던 공정을
   둔다). HOME 그림 칸 · 카드 링크 · 주소 `process` 로 들어온 회차(`entered=True`)는 들어온 길이
   이기고 이번 값은 본 것으로 친다. 이 화면에서 고른 공정은 값을 바꾸지 않는다(한 공정을 들여다본
   일로 3공정 거름이 사라지지 않게). 값 칸은 `process_field.render_process_choice`.
4. **저장 기본값은 건드리지 않는다** — 필요 단축 일정 공정 필터(설비 `0019`)와 표준 목표 저장 칸에
   값을 넣지 않는다(AGENTS 5장 9 · 12). 2차에서 잇는 화면도 「강조로만 · 표만 좁힘」 이다.
5. **Static Capa 는 전체, 실적 셋 · Dynamic · 재공은 데이터 연결 뒤**(3차) — 잇지 않는다.

표지: 걸린 화면은 사이드바 값 칸 강조와 본문 위 칩(「공정 Mold · HOME 에서」, 누르면 `clear`)으로
알린다. 출처 글은 값이 그 화면에 실제로 걸렸을 때만 단다(`origin_for`). 편집 표가 거름 밖 초안을 셀
때는 `count_outside(processes, options)` 다(기준 정보 「거름 밖 n개」).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

import streamlit as st

# 세션 칸. 이 모듈 밖에서 읽거나 쓰지 않는다.
_VALUES_KEY = "shared_process_values"
_ORIGIN_KEY = "shared_process_origin"
# 값이 바뀔 때마다 오르는 수 — 하나 고름 화면이 「바뀐 뒤 처음 그리는 회차」 를 가른다.
_VERSION_KEY = "shared_process_version"
# 하나 고름 화면마다 마지막으로 본 판(`{화면: 판}`)과 따라 연 공정(`{화면: 공정}`).
_SEEN_KEY = "shared_process_seen"
_FOLLOWED_KEY = "shared_process_followed"

# HOME 이 보낸 값의 출처 이름(칩 · 이름 줄의 「HOME 에서」).
HOME = "HOME"


def values() -> tuple[str, ...]:
    """지금 공용 값(원본 공정명, 고른 차례). 비었으면 고르지 않은 것이다."""
    saved = st.session_state.get(_VALUES_KEY)
    if not isinstance(saved, (list, tuple)):
        return ()
    return tuple(str(value) for value in saved)


def origin() -> str:
    """값을 마지막으로 정한 화면 이름. 값이 비었으면 빈 글자다."""
    saved = st.session_state.get(_ORIGIN_KEY)
    return str(saved) if values() and isinstance(saved, str) else ""


def version() -> int:
    saved = st.session_state.get(_VERSION_KEY, 0)
    return saved if isinstance(saved, int) else 0


def publish(chosen: Iterable[object], screen: str) -> None:
    """공용 값을 `chosen` 으로 바꾼다(겹친 값은 하나로). 빈 값이면 지운 것이다."""
    cleaned = [
        text for text in dict.fromkeys(str(value).strip() for value in chosen if value is not None)
    ]
    cleaned = [text for text in cleaned if text]
    if cleaned == list(values()) and (not cleaned or origin() == screen):
        return
    st.session_state[_VALUES_KEY] = cleaned
    st.session_state[_ORIGIN_KEY] = screen if cleaned else ""
    st.session_state[_VERSION_KEY] = version() + 1


def clear() -> None:
    """공용 값을 지운다 — 본문 칩 · 팝업 「전체」."""
    publish((), "")


def publish_from_home(included: Iterable[object], options: Sequence[object]) -> None:
    """HOME 「선택 공정 적용」 뒤 — 이번 선택지 가운데 켠 공정을 복사한다(한쪽 방향).

    모두 켰으면 지운다(전체). 이번 조회기간에 보이지 않던 공정(HOME 세션 값에만 남은 것)은 보내지
    않는다 — HOME 화면에서 고른 것만 보낸다.
    """
    allowed = [str(option) for option in options]
    picked = {str(value) for value in included}
    chosen = [option for option in allowed if option in picked]
    publish([] if len(chosen) >= len(allowed) else chosen, HOME)


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


def apply_from_screen(chosen: Iterable[object], options: Iterable[object], screen: str) -> None:
    """여러 개 따라감 화면의 팝업 「적용」. 이 화면에 없어 건드릴 수 없었던 값은 남긴다.

    이 화면 공정을 모두 켰으면 이 화면 몫은 고르지 않은 것(전체)이다 — `publish_from_home` 처럼
    모두 켠 목록을 값으로 남기지 않는다. 명시 목록으로 남으면 리비전을 바꿔 새로 들어온 공정이
    따라가는 화면마다 걸러져 보이지 않는다. 남길 값도 없으면 공용 값이 지워진다.
    """
    allowed = {str(option) for option in options}
    picked = [str(value) for value in chosen if str(value) in allowed]
    if allowed and allowed <= set(picked):
        picked = []
    publish([*picked, *missing(allowed)], screen)


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


def single_applied(screen: str, selected: object) -> bool:
    """하나 고름 화면에서 지금 공정이 공용 값을 따라 연 공정인가 — 표지(강조 · 칩 · 출처)를 다는
    조건. 이 화면에서 다른 공정을 고르거나 들어온 길로 열었으면 거짓이다."""
    if selected is None:
        return False
    process = str(selected)
    return _screen_map(_FOLLOWED_KEY).get(screen) == process and process in values()


def count_outside(processes: Iterable[object], options: Iterable[object]) -> int:
    """`processes`(초안이 있는 공정 등) 가운데 지금 걸린 공용 값에 가려 이 화면에 안 보이는 수.

    걸린 값이 없으면(전체를 보이면) 0 이다 — 기준 정보 편집 표의 「거름 밖 n개」 표지.
    """
    shown = set(applied(options))
    if not shown:
        return 0
    return len({str(process) for process in processes} - shown)
