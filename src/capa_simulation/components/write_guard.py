# Purpose: 쓰기 단추의 빠른 두 번 누름이 한 번만 쓰고 저장과 거부를 뒤바꿔 알리지 않게 한다.

"""빠른 두 번 누름이 **겹쳐** 올 때의 거름.

쓰기 단추는 그린 회차의 key 세대를 콜백 인자로 받아 지금 세대와 다르면 쓰지 않는다
(AGENTS 9장). 그 비교만으로는 둘째 누름이 **첫 쓰기의 뒷정리가 끝난 뒤** 닿을 때만
막힌다. 브라우저 더블클릭은 그렇지 않다 — Streamlit 1.63 은 `runner.fastReruns`(기본
켜짐)로 둘째 누름이 닿는 순간 돌던 회차에 멈춤을 걸고 새 회차를 세운다. 두 회차는
스레드가 다르고 세션 칸 잠금(`SafeSessionState`)도 회차마다 따로라, 두 콜백이 수 ms
차이로 같은 세대를 보고 둘 다 썼다(2026-10-25 E2E — VOC 글·답변이 두 건). 멈춤을 받은
첫 콜백은 DB 에 쓴 뒤 다음 세션 칸 접근에서 `StopException` 으로 끊겨 세대도 못 올린다.

그래서 `write_once` 는 세 가지를 한다.

- 세대 비교와 쓰기를 **그 세션의 잠금** 안에서 한다. 같은 세션의 둘째 콜백은 첫 쓰기가 끝날
  때까지 기다린다. 막을 것은 같은 세션의 겹친 두 회차뿐이라 잠금도 세션마다 하나다 — 몇 초짜리
  쓰기(사이드바 리비전 저장·시나리오 복제·기준선 얼리기)가 다른 사용자의 쓰기를 세우지 않는다.
  세션이 달라도 같은 DB 에 쓰는 일은 저장소의 쓰기 잠금이 따로 줄 세운다.
- 「이 세대는 썼다」 는 세션 칸이 아니라 **세션에 걸어 둔 dict 하나**에 적는다. 세션 칸
  쓰기는 멈춤을 받은 회차에서 그 자리에서 끊기지만 dict 칸 쓰기는 Streamlit 을 거치지
  않아 끊기지 않는다. 첫 콜백이 세대를 못 올리고 끊겨도 둘째 콜백이 그 표지를 보고 쓰지
  않은 채 뒷정리(알림·비우기·세대 올리기)만 한다.
- 표지는 세대와 함께 **입력 지문**(`fingerprint` — 쓴 이름·글·대상 리비전·편집본 토큰 같은 그
  쓰기의 입력)을 든다. 같은 누름이 겹쳐 오면 둘째 회차의 입력도 같아 쓰지 않는다. 쓴 뒤 둘째 누름이
  아닌 조작(스피너 중 다른 단추·팝업 닫기·페이지 이동)이 회차를 끊으면 표지는 남고 세대는 그대로라,
  세대만 보면 그 뒤 **다른 내용**을 적어 누른 저장도 「이미 썼다」 로 보고 쓰지 않은 채 옛 결과로
  성공을 알렸다(2026-10-26 리뷰). 지문이 다르면 새 쓰기다 — 쓰고 표지를 바꾼다.

`write` 는 잠금 안에서 표지를 적기 전에 돈다. 그 안에서 세션 칸을 읽지 않는다 — 세션 칸
접근도 끊기는 자리라, 입력(지문 포함)은 부르기 전에 읽어 둔다.

**비교 후 쓰기**(CAS — 공용 프로필 version(공정 표시명·표시순서·판정 기준·확보율 보정·HOME Summary
공지·Top5 구간·주요공정 프리셋)·Cut-off
지문·리비전명·공식 번호·설비 리비전 짝)는 세 가지를 이 모듈 한 길로 한다.

- **본 값**(`remember_seen`·`seen`·`forget_seen`). 저장소에 넘길 대조 값은 사용자가 **본** 화면의
  값이다. 본문에서 저장하는 폼은 폼을 제출하지 않은 회차(그린 화면이 곧 본 화면)에만 그 회차가 그린
  저장본의 토큰을 적고, 제출 회차는 적은 값을 그대로 넘긴다 — 칸이 없다고 지금 값으로 대체하지
  않는다(대체하면 남의 저장 뒤 한 회차만 돌아도 대조가 지나 그 저장을 모르는 채 덮는다). 칸이 없으면
  저장하지 않고 「다시 불러와」 를 알린다(`SEEN_MISSING_MESSAGE`). 충돌·실패 회차에도 올리지 않는다
  — 충돌을 받은 회차는 거부를 담아(`queue_refusal`) 앱을 다시 돌리고, 그 다음 회차(제출 아님)가
  최신을 그리며 적는다. 초안을 세울 때 출발점을 함께 두는 편집(Cut-off·층 사용·설비 편집본)은 초안을
  세우는 자리에서 적는다. 콜백 쓰기는 그린 회차의 값을 콜백 인자로 받으므로 따로 적지 않는다. 토큰은
  `int`·`str`·`tuple` 어느 것이든 된다(이름 붙은 묶음은 `dict`).
- **제 저장 판정**(`own_save_marks`·`remember_own_save`·`is_own_save`). 둘째 누름의 회차가 첫 저장의
  rerun 회차(또는 첫 콜백의 뒷정리)를 끊으면 본 값이 저장 전 그대로라 저장소가 거부하고, 화면은 방금
  한 제 저장을 「다른 사용자가 먼저 저장」 이라 알렸다(2026-10-26 E2E). 저장 전에 `own_save_marks`
  로 받아 둔 dict 에 성공한 `(본 값, 저장된 값)` 짝을 적고, 거부의 `(본 값, 지금 값)` 이 **정확히**
  그 짝이면 오류 대신 성공을 다시 알린다 — 그 사이 남이 저장했으면 지금 값이 짝과 달라 그대로 거부를
  알린다. 짝은 저장 성공 때만 바꾼다. 옛 이름 `profile_save_marks`·`is_own_profile_save` 는 얇은
  별칭이다. 겹쳐 도는 둘째 회차가 첫 쓰기 뒤·짝 적기 전의 틈에 거부되지 않게 쓰기와 짝 적기를 그
  세션의 잠금 안에서 함께 하는 길(`save_remembered`)과 그 잠금을 거쳐 판정하는 길
  (`is_own_save_settled`)을 둔다.
- **남의 저장에 거부된 누름의 둘째 누름.** 사용자가 거부 뒤 화면을 보기도 전에 닿은 둘째 누름은 옛
  화면의 입력을 든다. 거부 회차가 본 값을 올리지 않으므로 그 누름은 다시 거부되고, 거부 뒤 다음
  회차가 최신을 그린 직후에 닿은 누름은 `profile_conflict_marks` 로 받아 둔 dict 의 거부 표지가
  거른다 — 거부를 받으면 그 알림과 시각을 곧바로 적고(`note_profile_conflict`),
  `TRAILING_PRESS_SECONDS` 안의 다음 제출은 저장하지 않고 그 거부를 다시
  알린다(`held_profile_conflict`). 창이 지나면 새 화면을 보고 다시 누른 저장이라 평소대로
  대조한다(2026-10-26 E2E — 판정 기준·공정 표시명·표시순서·확보율 보정, HOME Summary 공지·Top5
  구간·주요공정 프리셋도 같은 길). 그 둘째 누름이 거부 뒤
  회차(제출 아님 — 본 값을 적는 자리)를 끊으면 그 회차가 적지 못하므로, 거부를 다시 알리는 회차가
  자기가 그린 최신 저장본의 토큰을 본 값으로 적는다 — 적지 않으면 최신을 보고 창 뒤에 한 번 누른
  저장이 옛 본 값으로 또 거부됐다(2026-10-26·27 E2E — 판정 기준·확보율 보정·공정 표시명·표시순서·
  자동 갱신 설정). 거부 회차가 초안과 출발점을 함께 다시 세우는 편집(Cut-off·층 사용)은 그 회차가
  이미 적었다.

**아주 빠른** 두 번 누름(0.05~0.15초)은 둘째 누름이 아직 옛 화면의 단추에 닿는다. 그 회차는
쓰지 않고(지나간 세대·이미 지운 글·잠긴 단추) 끝나는데, 첫 쓰기의 성공 알림은 앞 회차가 이미 꺼내
그렸다 — 둘째 회차가 화면을 다시 그리며 알림이 사라져, 한 건 쓰였는데 아무 알림도 남지 않았다
(2026-10-26 E2E — VOC 글 올리기·Preference 프리셋 삭제). 세대 쓰기는 `just_written` 으로 그 꼬리를
알아보고 성공을 다시 알린다. 누름이 회차에 닿지 않는 단추(잠긴 단추는 Streamlit 이 값을 버린다)는
쓰기 전에 `notice_marks` 로 받아 둔 dict 에 알림과 시각을 적고(`note_notice`), 그 창 안의 회차가
`held_notice` 로 다시 그린다.

**토글 단추**(누르면 같은 자리에 반대 동작의 단추가 선다)의 더블클릭은 둘째 누름이 새 세대의 반대
단추에 닿아 세대 거름을 지나 첫 쓰기를 되돌렸다(2026-10-27 E2E — VOC 답변 완료 표시). 그 콜백은
바로 앞 세대 쓰기의 창 안에 온 누름(`pressed_on_replacement`)을 쓰지 않는다.

**본문이 받는 컴포넌트 제출**(Space 배치 편집기 「적용」)은 받아들인 회차가 세션에 얹고 `st.rerun()`
으로 편집기를 새 epoch 로 다시 세운다. 브라우저가 새 값을 받기 전에 같은 단추를 한 번 더
누르면(0.2~0.6초) 둘째 제출은 옛 epoch 를 들어 「다시 서는 사이에 누른 적용이라 반영하지
않았습니다」 경고만 남고 첫 적용의 성공 알림은 사라졌다 — 실제로는 적용됐다(2026-10-27 E2E).
받아들인 제출은 그 입력 지문과 시각을 적고(`note_submission`), 옛 epoch 의 제출이
`TRAILING_PRESS_SECONDS` 안에 **같은 입력**으로 오면(`just_submitted`) 경고하지 않는다. 첫 적용의
성공 알림은 `note_notice` 로 적어 그 회차가 다시 그린다. 입력이 다르면 옛 화면에서 더 고친 것이라
전처럼 경고한다.

**출발점 대조 저장**(설비 편집본 — 설비 마스터 「리비전 저장」·Space 「배치 저장」·사이드바
팝업 저장, FAB 전체 배치)은 콜백에서 저장하고 뒷정리로 편집본을 비워 출발점을 옮긴다. 둘째
누름의 회차가 첫 콜백을 DB 쓰기 뒤에 끊으면 출발점이 그대로라, 둘째 콜백이 옛 출발점으로 다시
저장하다 저장소에 거부되고 제 저장을 「다른 사용자가 먼저 저장」 이라 알렸다(2026-10-26 E2E).
`save_once` 는 저장과 「이 출발점은 저장했다」 표지를 그 세션의 잠금 안에서 하고, 같은 출발점의 둘째
누름에는 저장하지 않고 첫 저장의 결과를 돌려준다 — 부르는 쪽은 그 결과로 뒷정리·알림을 잇는다.
설비 편집본 저장은 그 창을 지나 저장소에 거부된 둘째 누름도 위 제 저장 판정으로 알아본다.

**버전 대조가 없는 공용 저장 폼**(Preference Summary 공지·Top5 구간·주요공정 프리셋 저장·선행 B/O·
선행 입고 실적)도 `save_once` 를 지난다 — 출발점 자리에 **저장할 입력**(글·구간·이름과 공정·달과
값)을 준다. 저장소가 편집 시작 version 을 대조하지 않아, 같은 내용을 빠르게 두 번 누르면 공용
버전만 두 번 올랐다(2026-10-25 E2E — Summary v5→v7·프리셋 v3→v5). 창 안의 같은 입력은 쓰지 않고
첫 결과로 뒷정리·성공 알림을 잇고, 다른 입력은 창 안이라도 쓴다. 버전을 대조하되 같은 내용이면
쓰지 않는(`None`) 저장(가용설비 현황 Preference 입력 비가동)도 같은 꼴로 지난다 — 첫 저장 뒤 새로
그린 표에서 온 같은 입력의 둘째 누름이 「바뀐 칸이 없어」 로 성공 알림 자리를 차지했다(2026-10-27
리뷰).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Hashable, Mapping
from typing import Any, TypeAlias, TypeVar, cast

import streamlit as st

# 본 값·제 저장 짝의 토큰 — 프로필 version(int)·지문·이름(str)·여러 값의 짝(tuple)·편집본 출발점처럼
# 이름 붙은 값 묶음(dict).
SeenToken: TypeAlias = int | str | tuple[object, ...] | dict[str, object]

# 쓰기를 마친 세대의 표지(세대 칸 이름 → (그 세대, 입력 지문)). 세션마다 하나이고 처음 쓰는
# 콜백이 잠금 안에서 건다.
WRITE_MARKS_KEY = "write_guard_marks"

# 그 세션의 쓰기 잠금(`threading.Lock`). 처음 쓰는 회차가 건다.
WRITE_LOCK_KEY = "write_guard_lock"

# 세대를 쓴 시각(세대 칸 이름 → `time.monotonic()`). `write_once` 가 표지와 함께 적는다.
RECENT_WRITES_KEY = "write_guard_recent_writes"
# 쓰기 직후 이 안에 들어온 **빈** 제출은 같은 단추의 느린 두 번 누름의 꼬리로 본다. 사람 더블클릭
# 간격(Windows 기본 0.5초)에 회차 한 번의 여유를 더한 값이다.
TRAILING_PRESS_SECONDS = 1.0

# 이 세션이 마지막으로 한 비교 후 쓰기(저장 이름 → (본 값, 저장된 값)). 옛 이름이 버전 대조라 칸
# 이름이 `profile_saves` 다.
PROFILE_SAVES_KEY = "write_guard_profile_saves"

# 충돌·본 값 없음으로 거부한 회차가 다음 회차에 그릴 거부 알림(저장 이름 → 알림 글). 거부 회차는
# 본 값을 올리지 않고 앱을 다시 돌린다 — 그 회차(제출 아님)가 최신을 그리며 본 값을 적고 이 글을
# 그린다.
REFUSALS_KEY = "write_guard_refusals"

# 본 값 칸이 없어(편집을 시작한 저장본을 모른다 — 이 칸이 생기기 전에 열린 창 등) 저장하지
# 않았을 때의 알림.
SEEN_MISSING_MESSAGE = (
    "편집을 시작한 저장본을 알 수 없어 저장하지 않았습니다 — 화면을 다시 불러왔으니 최신 값을 "
    "확인한 뒤 다시 저장하세요."
)

# 이 세션이 마지막으로 받은 버전 충돌 거부(저장 이름 → (거부 알림 글, 받은 시각)). 시각은
# `time.monotonic()` 이다.
PROFILE_CONFLICTS_KEY = "write_guard_profile_conflicts"

# 이 세션이 마지막으로 낸 쓰기 알림(알림 칸 이름 → (알림 글, 쓴 시각 `time.monotonic()`, 아이콘,
# 종류)).
RECENT_NOTICES_KEY = "write_guard_recent_notices"
# 쓰기 알림 표지 한 칸 — (알림 글, 쓴 시각, 아이콘 — 아이콘 없는 알림은 None, 알림 종류 — `flash` 의
# 종류 글자, 보통 "success").
NoticeMark: TypeAlias = tuple[str, float, str | None, str]

# 이 세션이 마지막으로 마친 출발점 대조 저장(저장 이름 → (출발점, 결과, 쓴 시각)).
# `save_once` 가 적는다.
OWN_SAVES_KEY = "write_guard_own_saves"

# 이 세션이 마지막으로 받아들인 컴포넌트 제출(제출 이름 → (입력 지문, 받은 시각)).
# `note_submission` 이 적는다.
RECENT_SUBMISSIONS_KEY = "write_guard_recent_submissions"

_Outcome = TypeVar("_Outcome")

# 처음 쓰는 두 회차가 세션의 잠금·표지 dict 를 따로 만들어 한쪽이 지워지지 않게 하는 프로세스
# 잠금. 두 회차의 세션 칸 잠금(`SafeSessionState`)이 따로라 이 자리는 세션 밖에 둔다. 잠그는
# 동안 하는 일은 세션 칸 하나를 읽고 (없으면) 적는 것뿐이다 — 쓰기는 이 잠금 밖, 세션의 잠금
# 안에서 돈다.
_SLOT_LOCK = threading.Lock()
_LOCK_TYPE = type(threading.Lock())


def current_generation(counter_key: str) -> int:
    """세대 칸의 지금 값. 아직 없거나 정수가 아니면 0 이다."""
    value = st.session_state.get(counter_key, 0)
    return value if isinstance(value, int) else 0


def _session_dict(key: str) -> dict[str, object]:
    """세션 칸 `key` 의 dict — 없으면 만들어 건다. 겹친 두 회차가 따로 만들지 않게 잠근다."""
    with _SLOT_LOCK:
        found = st.session_state.get(key)
        if not isinstance(found, dict):
            found = {}
            st.session_state[key] = found
        return found


def _session_lock() -> threading.Lock:
    """그 세션의 쓰기 잠금 — 없으면 만들어 건다."""
    with _SLOT_LOCK:
        found = st.session_state.get(WRITE_LOCK_KEY)
        if not isinstance(found, _LOCK_TYPE):
            found = threading.Lock()
            st.session_state[WRITE_LOCK_KEY] = found
        return found


def write_once(
    counter_key: str,
    generation: int,
    write: Callable[[], object],
    *,
    fingerprint: Hashable,
) -> bool:
    """그린 회차의 세대(`generation`)로 `write` 를 **같은 입력마다 한 번만** 부른다.

    `fingerprint` 는 그 쓰기의 입력(적은 글·이름·대상 리비전·편집본 토큰 등 — 다른 내용의 저장이면
    달라야 하고, 같은 누름이 겹쳐 오면 같아야 한다)이다. 부르기 전에 읽은 값으로 짓는다.
    시각·난수처럼 회차마다 바뀌는 값은 넣지 않는다 — 겹쳐 온 둘째 누름이 새 쓰기가 된다.

    - `False` — 지나간 화면의 누름이다(지금 세대가 다르다). 쓰지 않았다. 부르는 쪽은
      알리지 않고, 옛 화면이 함께 보낸 입력은 이미 쓴 것이라 비우기만 한다.
    - `True` — 이 세대의 이 입력 쓰기가 끝났다. 이 누름이 썼거나, 겹쳐 온 같은 누름이 쓰고
      뒷정리 전에 끊겼다. 부르는 쪽은 뒷정리를 하고 **세대 올리기를 맨 끝에** 둔다 — 그
      앞에서 끊기면 다음 누름이 표지를 보고 뒷정리를 잇는다. 같은 세대라도 지문이 다른 누름은
      새로 쓴다(끊긴 쓰기 뒤 다른 내용을 적어 누른 저장).

    `write` 가 던진 예외는 그대로 나간다. 표지를 남기지 않으므로 다시 누르면 다시 쓴다.
    """
    mark = (generation, fingerprint)
    with _session_lock():
        if generation != current_generation(counter_key):
            return False
        marks = _session_dict(WRITE_MARKS_KEY)
        recent = _session_dict(RECENT_WRITES_KEY)
        if marks.get(counter_key) != mark:
            write()
            marks[counter_key] = mark
            recent[counter_key] = time.monotonic()
    return True


def save_once(
    name: str,
    start: object,
    save: Callable[[], _Outcome],
    *,
    wrote: Callable[[_Outcome], bool],
) -> _Outcome:
    """출발점 `start` 의 `name` 저장을 한 번만 하고, 겹쳐 온 둘째 누름에는 첫 결과를 돌려준다.

    `start` 는 저장이 끝나면 뒷정리가 옮기는 값이다(설비 편집본이면 `buffer_base` — 저장본 쌍
    토큰과 씨뿌린 세대). 첫 콜백이 DB 에 쓴 뒤 뒷정리 전에 끊기면 출발점이 그대로 남는다. 그
    출발점으로 다시 부르면 `save` 를 부르지 않고 첫 결과를 돌려준다 — 옛 출발점으로 저장소에 다시
    가면 남의 저장으로 거부된다. `wrote(결과)` 가 참일 때만 표지를 남긴다(아무것도 쓰지 않은
    저장은 뒷정리도 출발점을 옮기지 않으므로 다음 누름이 다시 저장해야 한다).

    표지는 `TRAILING_PRESS_SECONDS` 안에서만 본다 — 겹쳐 온 둘째 누름은 첫 쓰기가 끝나자마자
    이 잠금을 얻으므로 그 안이고, 오래 뒤 같은 출발점이 다시 오는 일(같은 FAB 배치를 되돌려 다시
    적용 등)은 표지로 막지 않는다. `save` 가 던진 예외는 그대로 나가고 표지도 남지 않는다.
    `save` 안에서 세션 칸을 읽지 않는다(`write_once` 와 같은 까닭).
    """
    with _session_lock():
        marks = _session_dict(OWN_SAVES_KEY)
        recorded = marks.get(name)
        if (
            isinstance(recorded, tuple)
            and len(recorded) == 3
            and recorded[0] == start
            and time.monotonic() - recorded[2] < TRAILING_PRESS_SECONDS
        ):
            return cast(_Outcome, recorded[1])
        outcome = save()
        if wrote(outcome):
            marks[name] = (start, outcome, time.monotonic())
        return outcome


def note_written(counter_key: str) -> None:
    """세대 쓰기 표지 없이 세션만 바꾸는 누름(설비 마스터 「한 단계 되돌리기」)이 지금 한 일을
    적는다 — `just_written` 이 그 창을 본다. 표지는 끊기지 않는 세션 dict 칸이다."""
    _session_dict(RECENT_WRITES_KEY)[counter_key] = time.monotonic()


def just_written(counter_key: str) -> bool:
    """`counter_key` 의 쓰기가 `TRAILING_PRESS_SECONDS` 안에 있었는가.

    느린 두 번 누름(0.15~0.3초)은 둘째 누름이 첫 쓰기 뒤 **새로 그린 빈 폼**의 단추에 닿는다. 세대가
    같아 `write_once` 는 정상 제출로 보고, 빈 입력이 거절되어 방금 성공한 쓰기 자리에 「제목을
    입력하세요.」가 남았다(2026-10-26 E2E). 부르는 쪽은 입력이 **모두 빈** 제출이 이 안에 오면 쓰지
    않고 방금 성공을 다시 알린다 — 적은 것이 하나라도 있으면 정상 제출이다.
    """
    recent = st.session_state.get(RECENT_WRITES_KEY)
    if not isinstance(recent, dict):
        return False
    moment = recent.get(counter_key)
    return isinstance(moment, float) and time.monotonic() - moment < TRAILING_PRESS_SECONDS


def pressed_on_replacement(counter_key: str, generation: int) -> bool:
    """`generation` 세대 단추의 누름이 바로 앞 세대 쓰기의 `TRAILING_PRESS_SECONDS` 안에 왔는가.

    누르면 같은 자리에 반대 동작의 단추가 서는 토글(VOC 「답변 완료로 표시」 ↔ 「미답변으로
    되돌리기」)은 첫 쓰기의 회차가 약 0.2초 안에 끝나 새 세대의 단추가 같은 자리에 선다. 0.2~0.45초
    간격 더블클릭의 둘째 누름은 그 새 단추에 닿아 세대가 맞으므로 `write_once` 가 정상 누름으로 보고
    첫 쓰기를 되돌렸다(2026-10-27 E2E). 부르는 쪽은 이 창 안의 누름을 쓰지 않는다 — 일부러
    되돌리려면 창이 지난 뒤 다시 누른다. 첫 콜백이 쓴 뒤 세대를 못 올리고 끊긴 겹친 누름은 표지의
    세대가 같아 여기 걸리지 않고 `write_once` 가 뒷정리를 잇게 한다.
    """
    marks = st.session_state.get(WRITE_MARKS_KEY)
    if not isinstance(marks, dict) or not just_written(counter_key):
        return False
    mark = marks.get(counter_key)
    return isinstance(mark, tuple) and mark[0] == generation - 1


def note_submission(name: str, fingerprint: Hashable) -> None:
    """`name` 제출(본문이 받는 컴포넌트 값 — 편집기 「적용」)을 받아들였다고 적는다 — 입력 지문과
    지금 시각. 세션에 얹은 **뒤**, 화면을 다시 세우기(`st.rerun()`) 전에 부른다. dict 칸 쓰기라 둘째
    누름의 회차가 멈춤을 건 자리에서도 끊기지 않는다."""
    _session_dict(RECENT_SUBMISSIONS_KEY)[name] = (fingerprint, time.monotonic())


def just_submitted(name: str, fingerprint: Hashable) -> bool:
    """`name` 제출을 같은 입력(`fingerprint`)으로 `TRAILING_PRESS_SECONDS` 안에 받아들였는가.

    그렇다면 지금 온 옛 화면(지나간 epoch)의 제출은 같은 단추를 한 번 더 누른 꼬리다 — 그 입력은
    이미 얹었다. 부르는 쪽은 「반영하지 않았습니다」 를 알리지 않고 넘긴다(첫 제출의 성공 알림은
    `note_notice` 로 적어 `flash.render_flash` 가 다시 그린다). 입력이 다르면 거짓이다 — 옛 화면에서
    더 고친 제출이다.
    """
    marks = st.session_state.get(RECENT_SUBMISSIONS_KEY)
    if not isinstance(marks, dict):
        return False
    entry = marks.get(name)
    if not isinstance(entry, tuple) or len(entry) != 2:
        return False
    recorded, moment = entry
    return (
        recorded == fingerprint
        and isinstance(moment, float)
        and time.monotonic() - moment < TRAILING_PRESS_SECONDS
    )


def remember_seen(name: str, token: SeenToken) -> None:
    """`name` 의 본 값을 `token` 으로 적는다(세션 칸 `name`).

    본문에서 저장하는 폼은 **폼을 제출하지 않은 회차에만** 부른다 — 그 회차가 그린 저장본이 사용자가
    본 화면이다. 제출 회차·충돌 회차·실패 회차에는 부르지 않는다(저장에 성공한 rerun 회차가 새 값을
    적는다). 예외 하나 — 거부 표지에 걸려 저장하지 않고 끝나는 제출 회차(`held_profile_conflict`)는
    그 회차가 그린 최신 저장본의 토큰을 적는다(그 누름이 끊은 거부 뒤 회차 몫). 초안과 출발점을 함께
    세우는 편집은 초안을 세우는 자리에서 부른다.
    """
    st.session_state[name] = token


def seen(name: str) -> SeenToken | None:
    """`name` 의 본 값. 적은 적이 없거나 토큰 꼴이 아니면 None 이다 — 지금 값으로 대체하지 않는다.

    부르는 쪽은 None 이면 저장하지 않고 `SEEN_MISSING_MESSAGE` 를 알린다(`queue_refusal` 뒤 rerun —
    그 회차가 본 값을 적는다).
    """
    value = st.session_state.get(name)
    if isinstance(value, bool) or not isinstance(value, int | str | tuple | dict):
        return None
    return value


def forget_seen(name: str) -> None:
    """`name` 의 본 값을 지운다 — 초안을 버리는 자리(편집을 끈 회차 등)."""
    st.session_state.pop(name, None)


def own_save_marks() -> dict[str, tuple[SeenToken, SeenToken]]:
    """비교 후 쓰기의 제 저장 표지 dict(저장 이름 → (본 값, 저장된 값)).

    저장 **전에** 받아 두고 저장에 성공하면 `remember_own_save` 로 이 dict 칸에 적는다. 세션 칸
    쓰기는
    둘째 누름의 회차가 멈춤을 건 자리에서 끊기지만 dict 칸 쓰기는 끊기지 않는다(위 `write_once` 의
    표지와 같은 까닭).
    """
    return cast("dict[str, Any]", _session_dict(PROFILE_SAVES_KEY))


def remember_own_save(
    name: str,
    expected: SeenToken,
    stored: SeenToken,
    marks: dict[str, tuple[SeenToken, SeenToken]] | None = None,
) -> None:
    """`name` 저장이 본 값 `expected` 에서 `stored` 를 썼다고 적는다 — 저장에 **성공한** 뒤에만
    부른다.

    저장 전에 받아 둔 `marks` 를 주면 세션 칸을 읽지 않는다(저장 직후는 끊길 수 있는 자리다).
    저장소 쓰기 **바로 뒤**, 세션 칸을 건드리는 뒷정리(입장 화면 확인 비우기·세션 표시순서 갈아
    끼우기 등) **앞**에 부른다 — 뒷정리에서 끊기면 짝이 적히지 않아 둘째 누름이 제 저장을 「다른
    사용자가 먼저 저장」 으로 알린다(2026-10-26 E2E). 저장 도우미가 뒷정리까지 하면 `marks` 를
    도우미에 넘겨 그 안에서 부른다.
    """
    target = own_save_marks() if marks is None else marks
    target[name] = (expected, stored)


def is_own_save(
    name: str,
    expected: SeenToken | None,
    stored: SeenToken | None,
    marks: Mapping[str, tuple[SeenToken, SeenToken]] | None = None,
) -> bool:
    """대조 거부 `(본 값 expected, 지금 값 stored)` 가 이 세션이 방금 한 `name` 저장 그것인가.

    그렇다면 같은 단추를 빠르게 두 번 누른 것이다 — 첫 누름이 이미 저장했고 그 뒤 아무도 저장하지
    않았다. 부르는 쪽은 거부 대신 저장 성공을 알린다. 짝이 **정확히** 같을 때만 참이다 — 넓게 잡으면
    남의 저장 뒤 충돌을 성공으로 알린다. 저장 전에 받아 둔 표지 dict(`marks`)를 주면 세션 칸을 읽지
    않는다 — 거부 직후는 둘째 누름의 회차에 끊길 수 있는 자리다.
    """
    if expected is None or stored is None:
        return False
    found = st.session_state.get(PROFILE_SAVES_KEY) if marks is None else marks
    return isinstance(found, Mapping) and found.get(name) == (expected, stored)


def save_remembered(
    name: str,
    expected: SeenToken,
    save: Callable[[], _Outcome],
    *,
    stored: Callable[[_Outcome], SeenToken | None],
    marks: dict[str, tuple[SeenToken, SeenToken]],
) -> _Outcome:
    """비교 후 쓰기 `save` 와 그 제 저장 짝 적기를 그 세션의 잠금 안에서 함께 한다 — 짝은
    `remember_own_save(name, expected, stored(결과))` 다.

    쓰기와 짝 적기 사이가 비면 겹쳐 온 같은 누름의 둘째 회차가 그 틈에 저장소에 가 첫 쓰기에
    거부되고, 짝이 아직 없어 제 저장을 「다른 사용자가 먼저」 로 알렸다(2026-10-26 E2E — 설비
    「공식으로 발행」, 고부하에서 1~2ms 차로 뒤집혔다). 같은 세션의 둘째 회차는 이 잠금을 첫 쓰기와
    짝 적기가 모두 끝난 뒤에 얻으므로 그 회차의 쓰기가 거부되면 짝이 이미 있다. `stored(결과)` 가
    None 이면(아무것도 쓰지 않음) 적지 않는다. `marks` 는 쓰기 전에 받아 둔 `own_save_marks()` 다.
    `save` 안에서 세션 칸을 읽지 않는다(`write_once` 와 같은 까닭). `save` 가 던진 예외는 그대로
    나가고 짝도 적지 않는다.
    """
    with _session_lock():
        outcome = save()
        token = stored(outcome)
        if token is not None:
            remember_own_save(name, expected, token, marks)
        return outcome


def is_own_save_settled(
    name: str,
    expected: SeenToken | None,
    stored: SeenToken | None,
    marks: Mapping[str, tuple[SeenToken, SeenToken]],
) -> bool:
    """`is_own_save` 를 이 세션에서 돌던 쓰기(`save_remembered`·`save_once`·`write_once`)가
    끝난 뒤에 본다.

    저장소에 가기 **전에** 첫 쓰기가 낸 새 값을 보고 거절하는 자리(설비 발행의 확인 글 대조 —
    목록이 첫 커밋 뒤 DB 지문으로 새로 읽힌다)는 첫 회차가 아직 짝을 적기 전일 수 있다. 잠금을
    거쳐 그 쓰기와 짝 적기가 끝난 뒤에 본다. 저장소 거부를 잡는 자리(`save_remembered` 밖의
    except)는 이미 그 뒤라 `is_own_save` 로 된다.
    """
    with _session_lock():
        return is_own_save(name, expected, stored, marks)


# 옛 이름(버전 대조 저장만 쓰던 때). 새 자리는 위 이름을 쓴다.
profile_save_marks = own_save_marks
is_own_profile_save = is_own_save


def queue_refusal(name: str, message: str) -> None:
    """`name` 저장의 거부 알림(`message`)을 다음 회차에 그리게 담는다 — 충돌·본 값 없음으로 거부한
    회차가 본 값을 올리지 않고 `st.rerun()` 하기 직전에 부른다. dict 칸 쓰기라 끊기지 않는다."""
    refusals = _session_dict(REFUSALS_KEY)
    refusals[name] = message


def take_refusal(name: str) -> str | None:
    """담아 둔 `name` 의 거부 알림을 꺼낸다(한 번만 그린다). 없으면 None."""
    refusals = st.session_state.get(REFUSALS_KEY)
    if not isinstance(refusals, dict):
        return None
    message = refusals.pop(name, None)
    return message if isinstance(message, str) and message else None


def profile_conflict_marks() -> dict[str, tuple[str, float]]:
    """버전 대조 저장의 충돌 표지 dict(저장 이름 → (거부 알림 글, 받은 시각)).

    `profile_save_marks` 와 같이 저장 **전에** 받아 두고, 남의 저장 때문에 거부되면 곧바로
    `note_profile_conflict` 로 적는다(dict 칸 쓰기는 끊기지 않는다).
    """
    return cast("dict[str, Any]", _session_dict(PROFILE_CONFLICTS_KEY))


def note_profile_conflict(marks: dict[str, tuple[str, float]], name: str, message: str) -> None:
    """`name` 저장이 남의 저장 때문에 거부됐다고 적는다 — 그 거부 알림 글(`message`)과 지금 시각."""
    marks[name] = (message, time.monotonic())


def held_profile_conflict(marks: Mapping[str, tuple[str, float]], name: str) -> str | None:
    """`name` 저장이 `TRAILING_PRESS_SECONDS` 안에 남의 저장 때문에 거부됐으면 그 거부 알림 글.

    그렇다면 이번 제출은 거부된 누름과 같은 단추의 둘째 누름이다 — 옛 화면의 입력을 들었고, 거부한
    회차가 올려 둔 편집 시작 version 으로는 대조를 지난다. 부르는 쪽은 저장하지 않고 이 글을 다시
    알린다 — 다만 이 회차가 `take_refusal` 로 같은 글을 이미 그렸으면 다시 그리지 않는다(둘째 누름이
    거부 뒤 회차를 글을 꺼내기 전에 끊으면 그 글이 이 회차로 넘어와, 같은 상자 둘이 겹쳐 섰다 —
    2026-10-26 E2E). 창이 지난 제출은 새 화면을 보고 다시 누른 저장이라 `None` 이다.
    """
    entry = marks.get(name)
    if not isinstance(entry, tuple) or len(entry) != 2:
        return None
    message, moment = entry
    if not isinstance(message, str) or not isinstance(moment, float):
        return None
    return message if time.monotonic() - moment < TRAILING_PRESS_SECONDS else None


def notice_marks() -> dict[str, NoticeMark]:
    """쓰기 알림 표지 dict(알림 칸 이름 → (알림 글, 쓴 시각, 아이콘)).

    쓰기 **전에** 받아 두고 쓰기에 성공하면 곧바로 `note_notice` 로 적는다(dict 칸 쓰기는 끊기지
    않는다 — 그 뒤 `queue_flash` 같은 세션 칸 쓰기는 둘째 누름의 회차에 끊길 수 있다).
    """
    return cast("dict[str, Any]", _session_dict(RECENT_NOTICES_KEY))


def note_notice(
    marks: dict[str, NoticeMark],
    key: str,
    message: str,
    *,
    icon: str | None = None,
    kind: str = "success",
) -> None:
    """`key` 칸에 낼 쓰기 알림(`message`)과 지금 시각을 적는다. `icon`·`kind` 는 그 알림의 아이콘과
    종류(`flash` 의 종류 글자 — 작은 편집표 삭제 알림은 "info")다 — 다시 그릴 때 첫 알림과 같은 꼴로
    선다."""
    marks[key] = (message, time.monotonic(), icon, kind)


def held_flash(key: str) -> tuple[str, str | None, str] | None:
    """`key` 칸의 쓰기 알림이 `TRAILING_PRESS_SECONDS` 안에 났으면 (그 글, 아이콘, 종류).

    그 창 안의 회차는 같은 단추의 빠른 둘째 누름일 수 있다 — 쓰지 않고 끝나 첫 쓰기의 알림을 지운다.
    부르는 쪽(`flash.render_flash`)은 담아 둔 알림이 없을 때 이 알림을 그 자리에 같은 꼴로 다시
    그린다. 아이콘·종류 없이 적은 옛 꼴(글, 시각[, 아이콘])도 읽는다(종류는 성공).
    """
    marks = st.session_state.get(RECENT_NOTICES_KEY)
    if not isinstance(marks, dict):
        return None
    entry = marks.get(key)
    if not isinstance(entry, tuple) or len(entry) not in (2, 3, 4):
        return None
    message, moment, *rest = entry
    icon = rest[0] if rest else None
    kind = rest[1] if len(rest) > 1 else "success"
    if (
        not isinstance(message, str)
        or not isinstance(moment, float)
        or not (icon is None or isinstance(icon, str))
        or not isinstance(kind, str)
    ):
        return None
    return (message, icon, kind) if time.monotonic() - moment < TRAILING_PRESS_SECONDS else None


def held_notice(key: str) -> str | None:
    """`key` 칸의 쓰기 알림이 `TRAILING_PRESS_SECONDS` 안에 났으면 그 글(`held_flash` 의 글)."""
    held = held_flash(key)
    return None if held is None else held[0]
