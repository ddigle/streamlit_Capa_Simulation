# Purpose: 편집 화면의 원본·줄 차례를 토큰으로 식별해 바뀌면 편집기를 비우고, 미적용 편집을 알린다.

"""편집 화면(생산 계획·기준 정보)이 함께 쓰는 원본 식별과 편집기 초기화.

예전에는 본문 맨 위에 「활성 시나리오 · 수정본 N」 줄과 원본 초기화 버튼도 그렸다. 그 줄은
사이드바 시나리오 줄의 미저장 배지와 같은 말을 했고, 초기화는 모든 화면의 편집을 버리는
시나리오 단위 동작이라 사이드바 시나리오 팝업의 「편집 되돌리기」로 옮겼다(2026-09-29 사용자 결정).
적용하지 않은 편집이 남은 곳은 사이드바 조건 패널 맨 위 한 줄이 알린다(`pending_edits_notice`).

**원본 토큰에는 줄 차례도 든다.** `st.data_editor` 의 편집은 줄 위치(`edited_rows`)로 남는다. 두
화면은 공용 표시순서로 줄을 세우는데 표시순서는 기준정보 버전·리비전을 바꾸지 않고 바뀌므로, 토큰에
그 지문이 없으면 적용 전 편집이 다른 공정 줄에 붙은 채 「적용」이 그대로 저장한다. 차례가 바뀌어
편집을 버린 회차는 화면이 한 번 알린다(`show_row_order_reset`) — 틀린 저장 대신 적용 전 편집만
잃는다(2026-10-24 사용자 결정). 줄 위치로 남지 않는 상태(붙여넣기 대기처럼 제 줄 차례를 들고 있는
표, 키로 고르는 선택 상자)는 차례만 바뀐 회차에 버리지 않는다(`order_free_keys`).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.components.editor_state import discard_editor, editor_has_edits
from capa_simulation.scenario_state import ActiveScenario

# 화면마다 「적용하지 않은 편집이 남을 수 있는 곳」의 목록. 사이드바가 저장·불러오기 전에 읽는다.
_PENDING_REGISTRY_KEY = "scenario_pending_edit_registry"
# 원본 토큰에서 줄 차례 지문이 시작하는 표지. 토큰 앞부분(버전·리비전·기간)에는 나오지 않는 글자다.
_ROW_ORDER_MARK = "|order:"


def source_token(
    reference_version: int,
    active_scenario: ActiveScenario,
    start_month: int,
    end_month: int,
    *,
    row_order: str,
) -> str:
    """편집기가 지금 보고 있는 원본을 한 문자열로 식별한다.

    기준정보 버전·활성 리비전·조회기간 중 하나라도 달라지면 표의 행과 월 구성이 달라진다.
    페이지마다 같은 f-string 을 다시 적으면 한쪽만 구성 요소가 늘어 편집기가 안 갈린다.

    `row_order` 는 **그 화면이 줄을 세우는 데 실제로 쓰는 값의 지문**이다 — 두 화면은 공용 표시순서
    (`simulation_cache.display_order_digest(reference_tables["RQ_DISPLAY_ORDER"])`, 편집표 캐시 키와
    같은 값)로 줄을 세운다. 차례가 바뀌면 이 값이 바뀌어 편집표가 비워진다(모듈 설명).
    """
    return (
        f"duckdb:{reference_version}:{active_scenario['revision']}:{start_month}:{end_month}"
        f"{_ROW_ORDER_MARK}{row_order}"
    )


def _row_order_of(token: object) -> str | None:
    """토큰의 줄 차례 지문. 그 칸이 없는 토큰(첫 회차·시나리오 전환 뒤·옛 형식)은 `None` 이다."""
    if not isinstance(token, str) or _ROW_ORDER_MARK not in token:
        return None
    return token.rpartition(_ROW_ORDER_MARK)[2]


def _source_of(token: object) -> object:
    """토큰에서 줄 차례 지문을 뺀 앞부분(기준정보 버전·리비전·기간). 지문이 없는 토큰은 그대로다."""
    if not isinstance(token, str) or _ROW_ORDER_MARK not in token:
        return token
    return token.rpartition(_ROW_ORDER_MARK)[0]


@dataclass(frozen=True)
class SourceReset:
    """`reset_editors_on_source_change` 의 결과.

    `changed` 는 원본이 바뀌어 무엇이든 비웠는가, `row_order_dropped` 는 **줄 차례가 바뀐 탓에**
    버린 적용 전 편집의 이름(화면이 준 `names` 의 값)이다 — 차례가 그대로였다면 남았을 것만 든다.
    비어 있으면 알릴 것이 없다. 시나리오 불러오기·저장처럼 사용자가 버린다고 확인한 변경과, 기간처럼
    차례와 상관없이 모두 버리는 변경은 여기 들지 않는다.
    """

    changed: bool
    row_order_dropped: tuple[str, ...] = ()


def row_order_reset_message(names: Sequence[str]) -> str:
    """줄 차례가 바뀌어 적용 전 편집을 버린 회차의 알림 한 줄."""
    return (
        "공용 표시순서가 바뀌어 표의 줄 차례가 달라졌습니다. 적용하지 않은 편집"
        f"({' · '.join(names)})을 다른 줄에 붙지 않게 버렸습니다 — 다시 입력하세요."
    )


def show_row_order_reset(slot: DeltaGenerator, reset: SourceReset) -> None:
    """줄 차례가 바뀌어 편집을 버린 회차에만 `slot` 에 한 번 알린다. 다음 회차에는 그리지 않는다.

    `slot` 은 화면이 탭 묶음 **위에 늘 세워 두는** 알림 칸이다 — 알림이 생기고 사라질 때 탭 묶음
    자리가 밀리지 않게(가용설비 현황의 버림 알림과 같은 꼴·아이콘).
    """
    if reset.row_order_dropped:
        slot.warning(
            row_order_reset_message(reset.row_order_dropped), icon=":material/sync_problem:"
        )


def register_pending_edits(
    page: str,
    title: str,
    editors: Mapping[str, str],
    staged: Mapping[str, str] | None = None,
    *,
    own_change_key: str | None = None,
) -> None:
    """이 화면의 편집표(`editors`: 키 → 이름)와 붙여넣기 대기(`staged`: 키 → 이름)를 적어 둔다.

    **적용하지 않은 편집은 시나리오에 들어 있지 않다.** 그래서 사이드바 「신규 리비전 저장」은 그
    편집을 저장하지 못하고, 저장·불러오기가 원본을 바꾸는 순간 편집표와 함께 사라진다(2026-09-29
    2차 리뷰에서 브라우저로 재현). 사이드바는 페이지보다 먼저 그려지므로 **앞 회차에 적어 둔**
    목록을 읽는다 — `pending_edit_labels`.

    `page` 는 그 화면의 파일 이름이다(`app_pages/<page>`). 편집표의 편집은 위젯 상태라 다른
    화면으로 옮기면 버려지므로 지금 화면의 것만 센다. 붙여넣기 대기는 위젯이 아닌 세션 칸이라
    화면을 옮겨도 남으므로 어느 화면에서나 센다.

    `own_change_key` 는 그 화면이 `mark_own_change` 에 넘기는 칸이다. 사이드바가 방금 적용한 표를
    빼고 세는 데 쓴다(`pending_edit_labels`).
    """
    registry = dict(st.session_state.get(_PENDING_REGISTRY_KEY) or {})
    registry[page] = (title, dict(editors), dict(staged or {}), own_change_key)
    st.session_state[_PENDING_REGISTRY_KEY] = registry


def pending_edit_labels(current_page: str | None) -> list[str]:
    """적용하지 않은 편집이 남은 곳 — 「기준 정보 · UPEH」. 없으면 빈 목록이다.

    **방금 적용한 표는 세지 않는다.** 적용한 회차는 `st.rerun()` 으로 끝나고, 다음 회차에는 이
    함수(사이드바)가 페이지보다 먼저 돈다. 그 편집표를 버리는 일(`reset_editors_on_source_change`)
    은 페이지 본문에서 뒤에 도므로, 그 사이에는 적용한 편집이 아직 위젯 상태에 남아 있다. 그것을
    세면 사이드바와 저장 팝업이 방금 적용한 표를 「적용 전 편집」으로 띄우고, 버릴 것도 없는 확인
    체크를 요구하며 「신규 리비전 저장」을 잠갔다(2026-10-01 브라우저 E2E 에서 재현). 페이지가
    `mark_own_change` 로 적어 둔 표·붙여넣기 대기는 그 적용이 버릴 것이므로 뺀다.
    """
    registry = st.session_state.get(_PENDING_REGISTRY_KEY)
    if not isinstance(registry, dict):
        return []
    labels: list[str] = []
    for page, (title, editors, staged, *rest) in registry.items():
        # 서버를 띄운 채 코드를 바꾸면 세션에 `own_change_key` 가 없는 세 칸짜리 기록이 남아 있다.
        # 여기서 풀다 멈추면 페이지가 새로 적기 전에 사이드바가 매 회차 멈춘다.
        own_change_key = rest[0] if rest else None
        just_applied = st.session_state.get(own_change_key) if own_change_key else None
        skipped = set(just_applied) if isinstance(just_applied, list) else set()
        if page == current_page:
            labels += [
                f"{title} · {name}"
                for key, name in editors.items()
                if key not in skipped and editor_has_edits(key)
            ]
        labels += [
            f"{title} · {name}"
            for key, name in staged.items()
            if key not in skipped and st.session_state.get(key) is not None
        ]
    return labels


def forget_pending_edits() -> None:
    """리비전을 바꾸는 동작(사이드바 시나리오 팝업의 불러오기·저장·되돌리기)이 성공한 뒤 부른다.

    **조회기간 「적용」에서는 일부러 부르지 않는다**(2026-10-11 병합 전 리뷰). 고른 범위가 바뀌어도
    데이터가 있는 달이 그대로면 편집표 원본도 그대로라 편집이 남는데, 목록을 비우면 그 회차에 패널
    경고와 저장 확인이 사라진다. 리비전을 바꾸는 동작은 원본 토큰이 늘 바뀌므로 안전하다.

    적용하지 않은 편집은 원본이 바뀌면 다음 회차에 페이지가 비운다
    (`reset_editors_on_source_change`). 그런데 사이드바(`app.py`)는 페이지보다 먼저 돌아, 그
    회차에는 아직 비우기 전의 편집표를 「적용 전 편집」으로 센다. 전에는 사이드바 버튼이 앱 전체
    실행 한가운데서 `st.rerun()` 해 페이지 위젯 값이 버려졌으므로 드러나지 않았는데, 팝업
    (프래그먼트) 안의 동작은 페이지 위젯을 건드리지 않아 패널 맨 위 경고가 한 회차 남았다
    (2026-10-10 브라우저 실측). 목록을 비워 두면 페이지가 다음 회차에 비운 뒤 다시 적는다 — 그 사이
    사이드바는 버려질 편집을 세지 않는다.
    """
    st.session_state.pop(_PENDING_REGISTRY_KEY, None)


def pending_edits_notice(labels: Sequence[str]) -> str:
    """사이드바 조건 패널 맨 위 주황 한 줄. 시나리오·조회기간 두 줄이 함께 쓴다.

    저장·불러오기·기간 변경 모두 원본을 바꿔 적용하지 않은 편집을 버린다. 무엇을 하면 사라지는지만
    말하고, 확인은 각 팝업이 받는다.
    """
    return (
        ":orange-badge[적용 전 편집] " + ", ".join(labels) + " — 시나리오·기간을 바꾸면 사라집니다"
    )


def mark_own_change(own_change_key: str, keys: Sequence[str]) -> None:
    """이 화면이 방금 **스스로** 적용한 편집을 적어 둔다. 적용한 뒤 `st.rerun()` 직전에 부른다.

    적용은 활성 리비전을 올려 원본 토큰을 바꾼다. 그대로 두면 다음 회차에 **모든** 편집표가
    비워져, 다른 탭에서 고치고 아직 적용하지 않은 편집까지 조용히 사라진다(2026-09-29 리뷰에서
    재현). 여기 적은 편집표·상태만 버리고 나머지는 그대로 두게 한다. `keys` 는 이 적용으로 행
    구성이 바뀐 편집표와 함께 비울 상태다. 페이지보다 먼저 도는 사이드바도 이 목록을 읽어, 버리기
    전인 그 표를 「적용 전 편집」으로 세지 않는다(`pending_edit_labels`).
    """
    st.session_state[own_change_key] = list(keys)


def reset_editors_on_source_change(
    token_key: str,
    token: str,
    editor_keys: Sequence[str],
    *,
    other_keys: Sequence[str] = (),
    own_change_key: str | None = None,
    names: Mapping[str, str] | None = None,
    order_free_keys: Collection[str] = (),
) -> SourceReset:
    """원본이 바뀌었으면 편집기·임시 상태를 비우고 새 토큰을 기록한다.

    편집표(`editor_keys`)는 `discard_editor` 로 **브라우저까지** 버린다 — 세션 칸만 지우면
    브라우저가 옛 편집을 다시 보낸다. 편집표가 아닌 상태(`other_keys` — 붙여넣기 대기, 선택
    위젯)는 칸만 지운다.

    바뀐 원본이 이 화면 자신의 적용이면(`mark_own_change`) 적어 둔 것만 비운다. **줄 차례가 함께
    바뀌었으면 그 예외를 두지 않는다** — 남겨 둔 다른 표의 편집이 다른 줄에 붙기 때문이다.

    `order_free_keys` 는 줄 차례가 바뀌어도 뜻이 그대로인 편집표·상태다 — 제 줄 차례를 들고 있는
    붙여넣기 대기 표와 그 표를 원본으로 그린 편집표, 줄 위치가 아니라 키로 고르는 선택 상자. 원본은
    그대로이고 **차례만** 바뀐 회차(또는 이 화면 자신의 적용과 겹친 회차)에 이것은 남긴다. 기준정보
    버전·리비전·기간이 바뀐 회차에는 지금처럼 함께 버린다(행·월 구성이 달라진다).

    `names` 는 알림에 적을 이름(편집표·붙여넣기 대기 키 → 이름, `register_pending_edits` 와 같은
    값)이다. 앞 토큰이 있고 그 줄 차례 지문이 지금과 다를 때, **차례가 그대로였다면 남았을** 적용 전
    편집의 이름만 `SourceReset.row_order_dropped` 에 싣는다 — 방금 이 화면이 적용한 표, 차례와
    상관없는 것(`order_free_keys`), 원본이 함께 바뀌어 어차피 버릴 것은 빠진다.

    `token_key` 는 페이지가 소유한다 — 두 편집 화면이 한 칸을 나눠 쓰면 한쪽을 열었다는
    이유로 다른 쪽 편집기가 안 갈린다.
    """
    previous = st.session_state.get(token_key)
    previous_order = _row_order_of(previous)
    row_order_changed = previous_order is not None and previous_order != _row_order_of(token)
    own = st.session_state.pop(own_change_key, None) if own_change_key else None
    own_keys = [str(key) for key in own] if isinstance(own, list) else None
    if own_keys is None and previous == token:
        return SourceReset(changed=False)
    every_key = [*editor_keys, *other_keys]
    # 줄 차례가 그대로였다면 남았을 것 — 이 화면 자신의 적용이면 그 적용이 건드리지 않은 것,
    # 원본은 같고 차례만 바뀌었으면 전부, 그 밖에 원본이 바뀌었으면 없다.
    if own_keys is not None:
        kept = [key for key in every_key if key not in own_keys]
    elif row_order_changed and _source_of(previous) == _source_of(token):
        kept = every_key
    else:
        kept = []
    lost_to_order: set[str] = set()
    if row_order_changed:
        lost_to_order = {key for key in kept if key not in order_free_keys}
        kept = [key for key in kept if key in order_free_keys]
    dropped = tuple(
        name
        for key, name in (names or {}).items()
        if key in lost_to_order
        and (editor_has_edits(key) if key in editor_keys else st.session_state.get(key) is not None)
    )
    for key in [*every_key, *(key for key in own_keys or () if key not in every_key)]:
        if key in kept:
            continue
        if key in editor_keys:
            discard_editor(key)
        else:
            st.session_state.pop(key, None)
    st.session_state[token_key] = token
    return SourceReset(changed=True, row_order_dropped=dropped)
