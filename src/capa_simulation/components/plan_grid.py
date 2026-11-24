# Purpose: 생산 계획 PKG PLAN · 수율 표를 범용 편집 그리드에 잇는다(규격·초안·작업 줄·한 줄 꼴).

"""생산 계획 화면과 범용 편집 그리드(`components/edit_grid.py`) 사이의 어댑터 — 2026-11-12 시안 보드
답 k-a1 · k-a2 · n2(기준 정보와 같은 편집기를 생산 계획에도).

- **탭마다 그리드 하나**(`plan_grid_keys.HOSTS`). 이 세션에 한 번도 연 적 없는 탭은 그리드를 세우지
  않는다(`mounted` — 그리드 요소는 등록 JS · CSS 를 함께 싣는다). 연 적 있는 탭이 닫힌 회차에는
  양식을 짓지 않고 앞서 보낸 껍데기 · feed 를 그대로 다시 보내(해시 참조) 마운트를 남기며, 그 표의
  op 가 inbox 에 쌓였을 때만 양식 색인을 짓는다(기준 정보의 「고른 표만」 과 같은 꼴).
- **초안은 표마다 세션 칸**(업무 키 + 월 — `services/edit_grid`). 편집은 출납 콜백이 세션 inbox 에
  쌓기만 하고(`collect`) 본문이 원본을 본 뒤 반영한다(`apply_inbox`).
- **값 꼴**: PKG PLAN 은 천 단위 · 소수 없이 보이고 0 이상만 받는다. 양식의 0 은 빈칸으로 싣는다 —
  칸을 비우면 빈칸이고 적용 때 0 이다(`plan_from_edit_table` 이 빈칸을 0 으로 읽는다). 수율은 % 로
  보이고(88% · 0.88 둘 다 받음) 100% 를 넘으면 틀린 칸이다. 분류 칸은 왼쪽에 고정되어 잠긴다.
- **작업 줄**(`render_actions`)은 표 위 · 단추 줄 key 는 표마다 따로다. 기준 창에서는 표 도구 막대가
  그 줄 오른쪽에 함께 선다(`edit_grid.one_line_style` — 문턱은 표마다 고친 뒤 단추 줄 폭으로 잰 값).
- **「변경사항 적용」 도 콜백이다**(AGENTS 9장 「세션 상태를 바꾸는 조작은 콜백」). 콜백이
  본문보다 먼저 그 표 출납을 받아 초안에 반영하고(`settle_inbox` — 단추 콜백이 그리드 출납
  콜백보다 먼저 돈다) 적용한 뒤, 같은 회차 하나가 새 원본으로 그린다(전에는 누른 회차가 옛
  원본으로 다 돈 뒤 `st.rerun()` 해 회차가 둘이었다). 막힌 적용의 글은 콜백이 그릴 수 없어 한 번
  쓰는 칸(`refuse`)에 담고 작업 줄 아래 알림 칸이 그 회차에 그린다.
- **편집기 구역**(AGENTS 9장 「구역 회차 규칙」) — 화면이 표마다 작업 줄 칸 · 그리드 칸을 키 붙은
  프래그먼트(`components/fragment_scope.editor_scope`)로 묶어 칸 고치기를 그 구역 회차로 돌린다.
  작업 줄 · 그리드의 콜백은 `scope_key` 를 주면 `fragment_scope.escalates` 로 감싸 콜백 끝에
  구역 밖이 그린 값(`scope_head`)이 바뀌었으면 앱 전체 회차로 올린다 — 「⋯」 메뉴 단추는 메뉴
  닫기(`_closing`)까지 마친 뒤 올린다.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.components import edit_grid, fragment_scope
from capa_simulation.components.flash import render_flash
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.components.widget_generation import bump, widget_key
from capa_simulation.plan_grid_keys import (
    HOSTS,
    MOUNTED_KEY,
    PLAN_TABLE,
    YIELD_TABLE,
    applied_key,
    cells_key,
    discarded_key,
    history_key,
    inbox_key,
    last_key,
    toast_key,
)
from capa_simulation.scenario_preset_state import MONTH_RANGE_KEY
from capa_simulation.services.edit_grid import (
    GridSpec,
    Op,
    ValueFormat,
    change_counts,
    change_list,
    merge_into_template,
)
from capa_simulation.services.edit_grid_payload import EditGridBase, base_key
from capa_simulation.services.simulation_cache import get_edit_grid_base
from capa_simulation.session_slot import SessionSlot

# 변경 목록 이름 — 기준 정보와 같은 말.
CHANGES_LABEL: Final = "적용 전 변경"
# 값 칸의 표시·다듬기 규칙. PKG PLAN 은 소수를 받되 보이는 자리는 정수다(옛 편집표 「%,.0f」 와
# 같음).
FORMATS: Final[Mapping[str, ValueFormat]] = {
    PLAN_TABLE: ValueFormat("fixed", 0),
    YIELD_TABLE: ValueFormat("percent", 2, max_value=1.0),
}
# 「변경사항 적용」 을 눌렀는데 칸 오류가 남았을 때(앞 `ERROR_PLACES` 곳을 함께 적는다 — 기준 정보와
# 같은 글).
ERRORS_NOTICE: Final = "고칠 칸 {n}개 — 빨간 칸을 고치거나 비우세요: {places}"
ERROR_PLACES: Final = 5
# 「⋯」 메뉴 단추의 풍선(2026-11-12 보드 답 n2 나).
MORE_HELP: Final = "더 보기"
# 「⋯」 팝오버 key 의 세대 칸 꼬리 — 메뉴 안 단추를 누르면 세대를 올려 메뉴를 닫는다.
MORE_GENERATION_SUFFIX: Final = "_generation"
# 「변경사항 적용」 콜백이 막힌 까닭(표, 글, 아이콘) — 콜백은 그리지 못해 담아 두고 그 표 작업 줄의
# 알림 칸이 같은 회차에 한 번 그린다(`refuse` · `render_actions`).
APPLY_REFUSAL_KEY: Final = "plan_grid_apply_refusal"
APPLY_REFUSAL: Final = SessionSlot(APPLY_REFUSAL_KEY, tuple)


@dataclass(frozen=True)
class Layout:
    """표 위 칸의 key 와 한 줄 꼴 값 — 작업 줄 칸(`actions_box`) 안 단추 줄(`action_row`), 그 바로
    뒤 그리드 칸(`grid_box`), 한 줄이 서는 창 폭과 왼쪽 비움."""

    actions_box: str
    action_row: str
    grid_box: str
    min_window_px: int
    reserve_px: int

    @property
    def style(self) -> str:
        return edit_grid.one_line_style(
            self.actions_box,
            self.action_row,
            self.grid_box,
            min_window_px=self.min_window_px,
            reserve_px=self.reserve_px,
        )


# 한 줄 문턱은 칸을 고친 뒤의 단추 줄(편집 취소 · 고칠 칸 포함)로 잰 값이다 — 고치기 전 폭으로
# 잡으면 첫 칸을 고치는 순간 표가 한 줄만큼 내려앉는다. 왼쪽 비움 = 고친 뒤 단추 줄 폭 + 16px(샘플
# 관측 — 사이드바 펼침 · 라이트 · 합성 표본: PKG PLAN 단추 줄 491(고칠 칸 두 자리 498) · 수율 429).
# 문턱은 본문 세로 스크롤 막대(10px)를 켠 Chrome · 글꼴 흉내로 1px 이분 탐색한 값이고, 고칠 칸 ·
# 「적용 전 (n)」 의 n 이 두 자리일 때 잰 값이다(그림 단추 막대 416 — 찾기 칸 140 · 「적용 전
# (10)」). 그래서 n 이 한두 자리면 문턱부터 막대 끝 「전체 화면」 까지 한 줄로 서고 그보다 좁으면
# 막대가 표 위 제 줄로 내려앉는다(꺾이는 창이 없다). n 이 세 자리면 막대가 7px 넓어 문턱부터 7px
# 창은 「전체 화면」 하나가 둘째 줄로 꺾인다(겹침 · 잘림 없음). 같은 막대 · 같은 사이드바라 문턱 −
# 왼쪽 비움은 기준 정보까지 세 그리드가 같다. 사내 보고 창 1283 은 둘 다 한 줄이다(설계 규칙집
# 4장 머리 · 「생산 계획 표 위 한 줄」).
LAYOUTS: Final[Mapping[str, Layout]] = {
    PLAN_TABLE: Layout("pkg_plan_actions", "pkg_plan_action_row", "pkg_plan_grid_box", 1268, 507),
    YIELD_TABLE: Layout("yield_actions", "yield_action_row", "yield_grid_box", 1206, 445),
}


@dataclass(frozen=True, eq=False)
class PlanGrid:
    """그리드에 실을 표 하나 — 규격 · 양식(그리드가 보는 꼴 — PKG PLAN 은 0 을 빈칸으로) · 캐시한
    색인과 본문 · 지문."""

    spec: GridSpec
    template: pd.DataFrame
    base: EditGridBase
    base_key: str

    @property
    def table(self) -> str:
        return self.spec.table

    @property
    def slot(self) -> edit_grid.TableSlot:
        return edit_grid.TableSlot(
            self.base.index, self.spec, cells_key(self.table), history_key(self.table)
        )


def grid_keys(table: str) -> edit_grid.GridKeys:
    return edit_grid.GridKeys(
        inbox=inbox_key(table),
        applied=applied_key(table),
        toast=toast_key(table),
        discarded=discarded_key(table),
    )


def zero_as_blank(table: pd.DataFrame, dimensions: Sequence[str]) -> pd.DataFrame:
    """달 칸을 수로 읽고 0 을 빈칸으로 — PKG PLAN 그리드 양식. 붙여넣기 대기 표의 글 칸도 같은
    `to_numeric` 으로 읽는다(붙여넣기 검증 `plan_from_edit_table` 이 이미 통과시킨 값이다)."""
    shown = table.copy()
    months = [column for column in shown.columns if column not in dimensions]
    values = shown[months].apply(pd.to_numeric, errors="coerce").astype(float)
    shown[months] = values.mask(values.eq(0))
    return shown


def build(
    table: str,
    title: str,
    template: pd.DataFrame,
    dimensions: Sequence[str],
    *,
    content_key: str,
    order_digest: str,
) -> PlanGrid:
    """표 하나를 그리드에 싣는 묶음 — 색인 · 본문은 (내용 지문 · 줄 차례 · 표) 로 캐시한다.
    `content_key` 는 `template` 내용을 가르는 값이어야 한다(붙여넣기 대기 표는 그 표 지문을
    더한다)."""
    months = tuple(str(column) for column in template.columns if column not in dimensions)
    spec = GridSpec(table, title, tuple(dimensions), months, FORMATS[table])
    base = get_edit_grid_base(
        content_key, order_digest, table, "-", _template=template, _spec=spec, _labels=None
    )
    return PlanGrid(spec, template, base, base_key(table, content_key, order_digest, "-"))


# ------------------------------------------------------------------ 세션


def inbox_tables() -> set[str]:
    """inbox 에 op 가 쌓인 표 — 탭이 닫혀도 그 양식 색인이 있어야 반영한다."""
    tables: set[str] = set()
    for table in HOSTS:
        pending = st.session_state.get(inbox_key(table))
        if isinstance(pending, list) and any(isinstance(op, Op) for op in pending):
            tables.add(table)
    return tables


def mounted(open_tables: Iterable[str]) -> frozenset[str]:
    """그리드를 세울 표 — 지금 열린 탭(`open_tables`), 이 세션에 연 적 있는 탭, inbox 에 op 가 쌓인
    표.

    한 번도 열지 않은 탭에 그리드를 세우면 화면에 들어오는 회차에 그리드 요소(등록 JS · CSS 포함)를
    탭마다 보낸다. 한 번 세운 그리드는 탭이 닫혀도 같은 자리에 남긴다 — 다시 세우면 보내지 않은
    출납을 잃는다."""
    saved = st.session_state.get(MOUNTED_KEY)
    before = {str(table) for table in saved} if isinstance(saved, list) else set()
    tables = (before | set(open_tables) | inbox_tables()) & set(HOSTS)
    if tables != before:
        st.session_state[MOUNTED_KEY] = sorted(tables)
    return frozenset(tables)


def collect(table: str) -> None:
    """출납 콜백 — 새 op 를 그 표 inbox 에 쌓고, 초안이 없던 표에는 빈 초안 자리를 둔다(머리 칩 ·
    탭 점이 본문보다 먼저 그리는 회차에도 첫 편집이 서게 — `reference_grid.collect_outbox` 와 같은
    까닭)."""
    edit_grid.collect_outbox(HOSTS[table], grid_keys(table))
    if table in inbox_tables() and st.session_state.get(cells_key(table)) is None:
        st.session_state[cells_key(table)] = {"cells": {}, "bad": {}}


def apply_inbox(grids: Mapping[str, PlanGrid | None]) -> bool:
    """inbox 의 op 를 표별 초안 · 이력에 반영한다(받을 표가 없으면 버리고 수를 알린다). 반영이 어느
    표의 초안 칸을 **비웠으면** 참 — 앞서 그린 칩 · 탭 점이 옛 칸이라 부르는 쪽이 한 번 다시
    돈다."""
    cleared = False
    for table, grid in grids.items():
        held = st.session_state.get(cells_key(table)) is not None
        slots = {table: grid.slot} if grid is not None else {}
        edit_grid.apply_inbox(grid_keys(table), slots)
        cleared = cleared or (held and st.session_state.get(cells_key(table)) is None)
    return cleared


def settle_inbox(table: str, grid: PlanGrid) -> bool:
    """「변경사항 적용」 콜백 몫 — 그 표 출납을 inbox 로 받고(`collect` — seq 기억이라 출납
    콜백이 뒤에 또 받아도 한 번) 그 표 초안에 반영한다. 단추 콜백은 그리드 출납 콜백보다
    **먼저** 돌므로(Streamlit 1.63 — 콜백 하나 단추가 콜백 여럿 컴포넌트 앞) 누름과 함께 온
    편집도 이 적용에 든다. 반영이 초안 칸을 비웠으면 참(`apply_inbox` 와 같은 뜻)."""
    collect(table)
    return apply_inbox({table: grid})


def refuse(table: str, message: str, *, icon: str | None = None) -> None:
    """막힌 적용의 글을 담는다 — 그 표 작업 줄(`render_actions`)이 같은 회차 알림 칸에 오류로
    그린다."""
    APPLY_REFUSAL.set((table, message, icon))


def _take_refusal(table: str) -> tuple[str, str | None] | None:
    """그 표에 담아 둔 막힌 적용의 (글, 아이콘)을 꺼낸다(다른 표 것은 그대로 둔다)."""
    refusal = APPLY_REFUSAL.peek()
    if refusal is None or len(refusal) != 3 or refusal[0] != table:
        return None
    APPLY_REFUSAL.clear()
    _, message, icon = refusal
    return str(message), icon if isinstance(icon, str) else None


def scope_head(
    *, staged_key: str, dialog_key: str, own_change_key: str, tab_key: str
) -> tuple[Hashable, ...]:
    """편집기 구역 밖이 그리는 값(AGENTS 9장 「구역 회차 규칙」 R2 — 머리 표지)을 세션 칸에서만
    읽는다 — 구역 규칙표는 프로세스 공용이라 페이지 회차의 값을 잡지 않는다. 화면이 칸 이름을 묶어
    넘긴다.

    표마다 초안 칸이 있는가(머리 띠 변경 칩 · 화면 탭 점 · 떠나기 확인) · 적용할 초안이 있는가(표 탭
    점), 붙여넣기 대기 표(`staged_key`) · 열린 팝업(`dialog_key` — 팝업은 구역 밖에서 그린다) · 방금
    스스로 적용한 표(`own_change_key`) · 고른 탭(`tab_key` — 같은 틱에 구역 회차에 실려 온 탭
    고르기), 활성 시나리오 내용(적용 · 등록) · 조회기간."""
    return (
        tuple(edit_grid.draft_present(cells_key(table)) for table in HOSTS),
        tuple(draft_pending(table) for table in HOSTS),
        edit_grid.head_value(staged_key),
        edit_grid.head_value(dialog_key),
        edit_grid.head_value(own_change_key),
        edit_grid.head_value(tab_key),
        edit_grid.scenario_mark(),
        edit_grid.head_value(MONTH_RANGE_KEY),
    )


def counts(table: str) -> tuple[int, int, int]:
    """(고친 칸, 고친 줄, 오류 칸)."""
    return change_counts(edit_grid.draft_of(cells_key(table)))


def draft_pending(table: str) -> bool:
    return edit_grid.draft_pending(cells_key(table))


def discard(table: str) -> None:
    """그 표의 초안 · 이력을 버린다(「편집 취소」 · 붙여넣기 — 누름 직전에 보낸 op 는 알림 없이
    버린다)."""
    edit_grid.discard_table((cells_key(table), history_key(table)), grid_keys(table))


def own_keys(table: str) -> tuple[str, str]:
    """적용으로 다음 회차에 비울 그 표의 편집 상태 — 초안 · 이력 세션 칸(`mark_own_change`)."""
    return (cells_key(table), history_key(table))


def merged(grid: PlanGrid) -> pd.DataFrame:
    """양식 사본에 그 표 초안을 업무 키로 덮은 전체 표(칸 오류가 남으면 ValueError — 부르기 전에
    `error_notice` 로 멈춘다)."""
    return merge_into_template(grid.template, grid.spec, edit_grid.draft_of(cells_key(grid.table)))


def error_notice(grid: PlanGrid) -> str | None:
    """「변경사항 적용」 을 막는 칸 오류 알림(오류가 없으면 None) — 앞 몇 곳을 분류 값 · 월로.
    알림은 마크다운이라 칸 값은 `literal_markdown` 으로 막는다."""
    draft = edit_grid.draft_of(cells_key(grid.table))
    errors = change_counts(draft)[2]
    if not errors:
        return None
    places = []
    for entry in change_list(grid.base.index, draft):
        if entry.bad is None:
            continue
        row = grid.template.iloc[entry.row]
        parts = [literal_markdown(row[column]) for column in grid.spec.key_columns]
        places.append(f"{' · '.join(parts)} · {literal_markdown(entry.month)}")
        if len(places) == ERROR_PLACES:
            break
    return ERRORS_NOTICE.format(n=f"{errors:,}", places=", ".join(places))


# ------------------------------------------------------------------ 그리기


def _shell(table: str, grid: PlanGrid | None) -> dict[str, object]:
    host = HOSTS[table]
    if grid is None:
        return edit_grid.shell_data(host, None, None, base_key="", changes_label=CHANGES_LABEL)
    shell = edit_grid.shell_data(
        host, grid.base, grid.spec, base_key=grid.base_key, changes_label=CHANGES_LABEL
    )
    # 머리 글은 다른 표와 같은 짧은 이름(「양산구분」 → 「양산」).
    shell["keyCols"] = [
        {"name": column, "label": COLUMN_LABELS.get(column, column)}
        for column in grid.spec.key_columns
    ]
    return shell


def render_grid(
    table: str, grid: PlanGrid | None, *, hidden: bool = False, scope_key: str | None = None
) -> None:
    """그리드 자리 — 늘 같은 자리에서 부른다. `scope_key`(편집기 구역 key)를 주면 출납 콜백 끝에
    구역 밖이 그린 값이 바뀌었으면 앱 전체 회차로 올린다(`fragment_scope.escalates`).

    표가 있으면 그 표를 싣고 보낸 껍데기 · feed 를 세션에 적어 둔다(`last_key`). 닫힌
    탭(`hidden`)이라 표를 짓지 않은 회차에는 적어 둔 껍데기 · feed 를 **그대로** 다시 보낸다 — 같은
    dict 라 ForwardMsg 해시 참조로 가고(그리드 요소는 등록 JS · CSS 를 함께 싣는다 — 다른 data 를
    보내면 그 몫을 다시 보낸다), 보이지 않는 표라 낡아도 탭을 열면 지금 표로 바뀐다. 적어 둔 것이
    없거나 열린 탭인데 표를 세우지 못한 회차는 표 없는 껍데기로 마운트만 남긴다."""
    host = HOSTS[table]
    sent = st.session_state.get(last_key(table))
    if grid is None and hidden and isinstance(sent, tuple) and len(sent) == 2:
        shell, feed = sent
    else:
        feed = edit_grid.feed_data(
            host,
            grid.slot if grid is not None else None,
            grid_keys(table),
            base_key=grid.base_key if grid is not None else "",
        )
        shell = _shell(table, grid)
        if grid is not None:
            st.session_state[last_key(table)] = (shell, feed)
    edit_grid.render_edit_grid(
        host,
        shell,
        feed,
        on_outbox=_rising(scope_key)(lambda: collect(table)),
        page_style=LAYOUTS[table].style,
    )


def _rising(scope_key: str | None) -> Callable[[Callable[[], None]], Callable[[], None]]:
    """콜백 감싸기 — 편집기 구역 key 가 있으면 `fragment_scope.escalates`(콜백 끝 올리기), 없으면
    그대로."""
    if scope_key is None:
        return lambda callback: callback
    return fragment_scope.escalates(scope_key)


@dataclass(frozen=True)
class Button:
    """작업 줄 단추 하나 — 글 · 아이콘 · key · 누를 때 콜백(「변경사항 적용」 도 콜백 — 본문보다
    먼저 적용해 누름 하나에 회차 하나다)."""

    label: str
    icon: str
    key: str
    on_click: Callable[[], None] | None = None


def _closing(callback: Callable[[], None] | None, counter: str) -> Callable[[], None]:
    """메뉴 안 단추 콜백 — 제 일을 한 뒤 팝오버 세대를 올린다(다음 회차에 메뉴가 닫혀 선다)."""

    def run() -> None:
        if callback is not None:
            callback()
        bump(counter)

    return run


@dataclass(frozen=True)
class Actions:
    """작업 줄 결과 — 「변경사항 적용」 이 눌렸는가와 그 바로 아래 알림 자리(적용 결과 · 오류 — 막힌
    적용의 글은 `render_actions` 가 이미 그렸다)."""

    submitted: bool
    notice: DeltaGenerator


def render_actions(
    table: str,
    *,
    apply: Button,
    apply_help: str,
    paste: Button,
    more: Sequence[Button] = (),
    more_key: str = "plan_grid_more",
    discard_help: str,
    discard_click: Callable[[], None],
    discard_key: str,
    staged: bool = False,
    flash_keys: Sequence[str],
    scope_key: str | None = None,
) -> Actions:
    """표 위 작업 줄 — 「변경사항 적용」 · 「Excel 붙여넣기」 · (「⋯」 메뉴) · 「편집 취소」(고친
    칸이나 붙여넣기 대기가 있을 때) · 「고칠 칸 n개」(칸 오류가 있을 때)와 그 아래 알림 칸. 고친
    수는 표 도구 막대 「적용 전 (n)」 하나가 말한다(UI-TXT-07).

    「변경사항 적용」 은 잠그지 않는다 — 고친 칸이 서버에 닿기 전(편집기를 연 채 · Enter
    직후)의 누름도 받아야 하므로, 고친 칸도 붙여넣기 대기(`staged`)도 없는 누름은 적용 콜백이
    누른 회차에 보고 아무것도 하지 않는다(같은 값 적용으로 리비전만 오르는 일을 막는 규칙 —
    설계 규칙 UI-INP-07 「누른 회차에 판정」, 2026-11-19 아침 확인 보드 m19-e2e-first-apply
    (가)). 「⋯」 는 「Excel 붙여넣기」 바로 뒤라 고치기 전 · 뒤에 같은 자리다. 그 표의 적용
    콜백이 막혀 담아 둔 글(`refuse`)은 알림 칸에 오류로 그린다. `scope_key`(편집기 구역 key)를
    주면 단추 콜백마다 끝에서 구역 밖이 그린 값이 바뀌었으면 앱 전체 회차로 올린다."""
    cells, _, errors = counts(table)
    pending = cells > 0 or staged
    rise = _rising(scope_key)
    with st.container(
        key=LAYOUTS[table].action_row, horizontal=True, vertical_alignment="center", gap="small"
    ):
        submitted = st.button(
            apply.label,
            icon=apply.icon,
            key=apply.key,
            type="primary",
            help=apply_help,
            on_click=None if apply.on_click is None else rise(apply.on_click),
        )
        st.button(
            paste.label,
            icon=paste.icon,
            key=paste.key,
            on_click=None if paste.on_click is None else rise(paste.on_click),
        )
        if more:
            # 메뉴 안 단추를 누르면 메뉴를 닫는다 — 팝오버 key 의 세대를 올려 다음 회차에 새(닫힌)
            # 팝오버로 선다. 열린 채 두면 그 단추가 여는 창 위에 메뉴가 떠 있다.
            counter = f"{more_key}{MORE_GENERATION_SUFFIX}"
            with st.popover(
                "", icon=":material/more_horiz:", help=MORE_HELP, key=widget_key(more_key, counter)
            ):
                for item in more:
                    st.button(
                        item.label,
                        icon=item.icon,
                        key=item.key,
                        on_click=rise(_closing(item.on_click, counter)),
                        width="stretch",
                    )
        if pending:
            st.button(
                "편집 취소",
                icon=edit_grid.DISCARD_ICON,
                key=discard_key,
                on_click=rise(discard_click),
                help=discard_help,
            )
            if errors:
                st.markdown(f":red[고칠 칸 {errors:,}개]")
    notice = render_flash(*flash_keys)
    refusal = _take_refusal(table)
    if refusal is not None:
        notice.error(refusal[0], icon=refusal[1])
    return Actions(submitted, notice)
