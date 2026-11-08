# Purpose: 기준 정보 편집 표 아홉을 범용 편집 그리드에 잇는다(규격·초안·작업 줄·오류·큰 표 상한).

"""기준 정보 화면과 범용 편집 그리드(`components/edit_grid.py`) 사이의 어댑터(편집 표 횡전개 —
2026-11-02 사용자 결정).

- **편집 표 아홉이 모두 그리드다**(`reference_grid_keys.EDIT_TABLES` — UPEH · 설비대수 보유·
  대여·가용 · 효율 · 여유율 · 일수 · Lot·WF측정률).
- **그리드 마운트는 하나**(`reference_grid_keys.GRID_HOST`) — 종류 단추로 표를 바꿔도 같은 key·같은
  자리에 표만 바꿔 싣는다. 읽기 보기(설비대수 현황·STEP 구성)를 고른 회차에는 표 없는 껍데기를 실어
  마운트만 남긴다(다시 마운트되면 보내지 않은 출납을 잃는다).
- **초안은 표마다 세션 칸**(업무 키 + 월 — `services/edit_grid`). 그리지 않는 표의 편집도 남고, 줄
  차례(공용 표시순서)만 바뀐 회차에도 같은 칸에 붙는다 — 그래서 사이드바 필터를 잠그지 않는다
  (브라우저가 feed `filters` 로 거른다).
- **공정은 화면들이 같이 쓰는 공용 공정 값으로 거른다**(2026-11-08 사용자 답 P1 — 공정 공유 1차 ·
  `GridTable.shared_screen`). 다른 화면에서 공정을 바꾸면 이 표도 따라 좁혀진다. 「표 조건」 카드의
  나머지 칸(양산 · Area 등)은 표마다 따로다. 거름에 가려 안 보이는 줄의 초안도 「변경사항 적용」 에
  들어가므로 작업 줄 아래 「거름 밖 n개」 표지를 단다(`outside_count`). 좁혀진 표의 여러 줄 붙여넣기
  막기는 feed `filters` 를 보는 그리드가 맡는다 — 공용 공정도 그 `filters` 에 실린다.
- **편집은 출납 콜백이 세션 inbox 에 쌓기만** 하고(`edit_grid.collect_outbox`) 본문이 원본 토큰을 본
  뒤 반영한다(`apply_grid_inbox`) — 원본이 바뀌어 초안·이력을 버린 회차에는 새 `gen` 이 서서 그 전에
  보낸 op 가 버려지고 수가 토스트로 간다. 지금 보이지 않는 표의 op 도 그 표 초안에 쓴다. 반영이 초안
  칸을 비우면 화면이 한 번 다시 돈다(본문보다 먼저 그린 칩·탭 점이 옛 칸으로 섰다).
- **오류의 자리는 둘이다.** 숫자·범위·해석 오류는 칸 안(빨강 + 상태 줄 문구 — 그리드가 그린다)이고
  「변경사항 적용」 을 누르면 고칠 칸 알림으로 멈춘다(`error_notice`). 업무 규칙 오류
  (`reference_consistency`)는 적용할 때 문장으로(오늘과 같다 — 화면이 쓴다).
- **큰 표 안전 상한**(명세 1-2 의 22). 칸 수가 `CAP_CELLS` 를 넘거나 껍데기 본문이 `CAP_BYTES` 를
  넘으면 사이드바 「표 조건」 필터를 서버에서 걸어 그 줄만 싣고, 필터가 없거나 걸러도 넘치면 앞
  `CAP_ROWS` 줄만 싣고 작업 줄 아래에 표지 한 줄 + 풍선을 둔다(바이트 상한을 넘는 표의 전체 본문은
  캐시에 두지 않는다 — `get_edit_grid_base_within`). 초안이 업무 키라 실은 줄이 바뀌어도 편집은
  제 줄에 남고, 적용은 언제나 **전체 양식**에 덮는다(`merged_template`). 합성 표본 최대는 UPEH
  2,660줄 × 30개월 = 79,800칸(샘플 관측)이라 걸리지 않는다. 사내 실데이터 크기는 런북 8장 8-11
  (`scripts/inspect_real_data_checks.py --only grid`)이 잰다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation import shared_process
from capa_simulation.components import edit_grid
from capa_simulation.components.column_filter import (
    PROCESS_COLUMN,
    apply_column_filters,
    column_filter_key,
)
from capa_simulation.components.flash import render_flash
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.month_editor import APPLY_NOTICE
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.reference_grid_keys import (
    APPLIED_KEY,
    DISCARDED_KEY,
    EDIT_TABLES,
    GRID_HOST,
    INBOX_KEY,
    TOAST_KEY,
    cells_key,
    history_key,
)
from capa_simulation.services.edit_grid import (
    DUPLICATE_SEPARATOR,
    KEY_SEPARATOR,
    GridIndex,
    GridSpec,
    Op,
    ValueFormat,
    build_index,
    change_counts,
    change_list,
    merge_into_template,
)
from capa_simulation.services.edit_grid_payload import EditGridBase, base_key, labels_digest
from capa_simulation.services.simulation_cache import (
    ScenarioCacheKey,
    get_edit_grid_base,
    get_edit_grid_base_within,
)

# 변경 목록 이름 — 변경 칩 · 변경 판 「적용 전 편집」·단추 「변경사항 적용」 과 같은 말.
CHANGES_LABEL: Final = "적용 전 변경"
KEYS: Final = edit_grid.GridKeys(
    inbox=INBOX_KEY, applied=APPLIED_KEY, toast=TOAST_KEY, discarded=DISCARDED_KEY
)
# 값 칸의 표시·다듬기 규칙(옛 `EDITOR_FORMATS` 를 옮김). 효율·측정률은 분수 1 이 상한, 일수는 정수만
# (옛 편집표는 소수를 말없이 버렸다 — 이제 칸 오류), 설비대수는 빈칸 = 0.
GRID_FORMATS: Final[Mapping[str, ValueFormat]] = {
    "RQ_UPEH": ValueFormat("sig", 6),
    "RQ_RUN_RATE": ValueFormat("percent", 2, max_value=1.0),
    "RQ_VITAL": ValueFormat("percent", 2),
    "RQ_RUN_DAY": ValueFormat("fixed", 0, integer=True),
    "RQ_EQP_OWN": ValueFormat("fixed", 2, blank_zero=True),
    "RQ_EQP_LENT": ValueFormat("fixed", 2, blank_zero=True),
    "RQ_EQP_AVBL": ValueFormat("fixed", 2, blank_zero=True),
    "RQ_LOT_RATIO": ValueFormat("percent", 2, max_value=1.0),
    "RQ_WF_RATIO": ValueFormat("percent", 2, max_value=1.0),
}
# 「변경사항 적용」 을 눌렀는데 칸 오류가 남았을 때(앞 `ERROR_PLACES` 곳을 함께 적는다).
ERRORS_NOTICE: Final = "고칠 칸 {n}개 — 빨간 칸을 고치거나 비우세요: {places}"
ERROR_PLACES: Final = 5
# 「Excel 붙여넣기」 팝업 첫 줄 — 그 표에 적용하지 않은 그리드 편집이 있을 때.
PASTE_DROPS_DRAFT_NOTICE: Final = (
    "이 표에 적용하지 않은 편집 {n}칸이 있습니다 — 붙여넣어 적용하면 그 편집은 버려집니다."
)
DISCARD_HELP: Final = "이 표에서 적용하지 않은 편집을 버립니다."
# 잠긴 「변경사항 적용」 의 풍선 — 왜 잠겼는지(풀린 동안은 `APPLY_NOTICE` 가 하는 일을 말한다).
APPLY_LOCKED_HELP: Final = "고친 칸이 있으면 누를 수 있습니다."
# 표 위 칸의 key — 작업 줄 칸 안의 단추 줄이 `ACTION_ROW` 다.
ACTIONS_BOX: Final = "reference_actions"
GRID_BOX: Final = "reference_grid_box"
ACTION_ROW: Final = "reference_action_row"
# 단추 줄과 표 도구 막대를 한 줄로 세우는 창 폭. 본문이 단추 줄(`ACTION_ROW_RESERVE_PX` 까지) 곁에
# 막대가 드는 폭이다(샘플 관측 — 사이드바 300 · 좌우 여백 35 · 단추 줄 429 · 막대 약 735). 그보다
# 좁으면 막대가 표 바로 위 제 줄로 내려앉는다(설계 규칙 UI-LAY-11 · UI-ACC-02).
ONE_LINE_MIN_WINDOW_PX: Final = 1560
ACTION_ROW_RESERVE_PX: Final = 460
# 한 줄로 설 때 막대를 단추 줄 높이로 올리고 이웃 단추와 같은 꼴로 맞춘다(UI-CON-01) — 값은 CSS
# 변수로 그림자 DOM 안 막대에 내려간다. `2.5rem` 은 단추 높이, `1rem` 은 세로 칸 간격이다. 왼쪽을
# 비워 둔 폭(`--eg-toolbar-reserve`)이 막대가 넘쳐도 단추를 덮지 않게 한다. 규칙은 단추 줄이 작업 줄
# 칸의 끝 자식일 때만 걸린다 — 표지 · 거부 칸이 서면 풀려 단추 → 그 칸 → 막대 → 표 차례로 쌓인다
# (UI-LAY-03). 단추 줄은 제 폭만 차지하고 그리드보다 위에 있어야 눌리고 막대도 눌린다.
ONE_LINE_STYLE: Final = f"""<style>
.st-key-{ACTION_ROW} {{
  width: fit-content;
  position: relative;
  z-index: 1;
}}
@media screen and (min-width: {ONE_LINE_MIN_WINDOW_PX}px) {{
  [data-testid="stLayoutWrapper"]:has(
      > .st-key-{ACTIONS_BOX} > :last-child > .st-key-{ACTION_ROW}
    ) + [data-testid="stLayoutWrapper"]:has(> .st-key-{GRID_BOX}) {{
    margin-top: -3.5rem;
    --eg-toolbar-justify: flex-end;
    --eg-toolbar-reserve: {ACTION_ROW_RESERVE_PX}px;
    --eg-tb-height: 2.5rem;
    --eg-tb-radius: 8px;
    --eg-tb-font: 0.875rem;
  }}
}}
</style>"""
# 큰 표 안전 상한(명세 1-2 의 22) — 칸 수 · 껍데기 본문 JSON 바이트 · 상한에 걸렸을 때 싣는 줄 수.
# 실데이터 센서스(`scripts/inspect_real_data_checks.py` 8-11)가 같은 값 · `GRID_FORMATS` 를
# 옮겨 둔다 — 바꾸면 `tests/test_inspect_real_data_checks.py` 가 잡는다.
CAP_CELLS: Final = 300_000
CAP_BYTES: Final = 400_000
CAP_ROWS: Final = 1_000
# 상한에 걸린 표의 표지(작업 줄 아래 한 줄 — 값)와 그 풍선. 숨은 줄이 있다는 것은 표지가, 고르는
# 법과 적용 범위는 풍선이 말한다(설계 규칙 UI-TXT-01 · 04 — 숨은 데이터 안내는 표지 + 풍선).
CAP_FILTERED_NOTICE: Final = (
    ":material/filter_alt: 큰 표 · 표 조건으로 고른 {shown:,}줄만 실음"
    "(전체 {rows:,}줄 · {cells:,}칸)"
)
CAP_HEAD_NOTICE: Final = (
    ":material/filter_alt: 큰 표 · 앞 {shown:,}줄만 실음(전체 {rows:,}줄 · {cells:,}칸)"
)
CAP_HELP: Final = (
    "칸이 아주 많은 표는 사이드바 「표 조건」 으로 고른 줄만, 고르지 않았으면 앞 줄만 싣습니다. "
    "「변경사항 적용」 은 싣지 않은 줄까지 표 전체에 덮습니다."
)
# 공용 공정 거름에 가려 이 표에 안 보이는 줄에도 적용하지 않은 편집이 있을 때의 표지(작업 줄 아래
# 한 줄 — 값)와 그 풍선(설계 규칙 UI-TXT-04 — 숨은 데이터 안내는 표지 + 풍선). 표지가 서면 작업 줄과
# 표 도구 막대가 한 줄에 서지 않고 단추 → 표지 → 막대 → 표 차례로 쌓인다(큰 표 표지와 같다).
OUTSIDE_NOTICE: Final = ":material/filter_alt_off: 거름 밖 {n}개"
OUTSIDE_HELP: Final = (
    "공정 거름에 가려 이 표에 보이지 않는 공정 {n}개에도 적용하지 않은 편집이 있습니다. "
    "「변경사항 적용」 은 그 편집까지 함께 적용합니다."
)
Labels = Mapping[str, Mapping[str, str]]


@dataclass(frozen=True, eq=False)
class GridTable:
    """그리드에 실을 표 하나 — 규격·편집표 key(작업 줄 단추·알림 이름)·양식·캐시한 색인과
    본문·지문."""

    spec: GridSpec
    editor_key: str
    template: pd.DataFrame
    base: EditGridBase
    base_key: str
    labels: Labels | None
    # 큰 표 상한에 걸려 일부 줄만 실었으면 그 표지(아니면 None — 본문 색인이 곧 전체 양식이다).
    cap_notice: str | None = None
    # 공용 공정 값을 따라가는 화면의 출처 이름(None 이면 공정도 표마다의 카드 선택으로 거른다).
    shared_screen: str | None = None

    @property
    def table(self) -> str:
        return self.spec.table

    @property
    def dimensions(self) -> tuple[str, ...]:
        return self.spec.key_columns

    @property
    def months(self) -> tuple[str, ...]:
        return self.spec.value_columns

    @property
    def slot(self) -> edit_grid.TableSlot:
        return edit_grid.TableSlot(
            self.base.index, self.spec, cells_key(self.table), history_key(self.table)
        )

    def full_index(self) -> GridIndex:
        """전체 양식의 색인 — 상한에 걸려 일부 줄만 실었을 때만 새로 짓는다(고칠 칸 알림)."""
        if self.cap_notice is None:
            return self.base.index
        return build_index(self.template, self.spec)


def grid_spec(
    table: str,
    title: str,
    template: pd.DataFrame,
    dimensions: Sequence[str],
    *,
    value_help: str | None = None,
) -> GridSpec:
    """양식(분류 칸 + 월 칸 표)의 그리드 규격 — 값 칸은 분류 칸이 아닌 칸 전부(표 차례)."""
    months = tuple(str(column) for column in template.columns if column not in dimensions)
    return GridSpec(table, title, tuple(dimensions), months, GRID_FORMATS[table], value_help)


def _capped_rows(
    template: pd.DataFrame,
    dimensions: Sequence[str],
    filter_prefix: str | None,
    shared_screen: str | None,
) -> tuple[pd.DataFrame, bool]:
    """상한에 걸린 표에서 실을 줄 — (줄, 사이드바 필터로 골랐는가). 필터로 골라도 칸 수가 넘치면
    그 앞 `CAP_ROWS` 줄이다. 공정은 `shared_screen` 이 있으면 공용 공정 값이다."""
    months = len(template.columns) - len(dimensions)
    if filter_prefix is not None:
        chosen = apply_column_filters(
            template, list(dimensions), key_prefix=filter_prefix, shared_screen=shared_screen
        )
        if len(chosen) < len(template):
            if len(chosen) * months <= CAP_CELLS:
                return chosen, True
            return chosen.head(CAP_ROWS), True
    return template.head(CAP_ROWS), False


def _rows_digest(rows: pd.DataFrame) -> str:
    """실은 줄(양식 줄 번호)의 지문 — 캐시 키·껍데기 지문에 더한다."""
    hashed = pd.util.hash_pandas_object(rows.index, index=False).to_numpy()
    return hashlib.sha1(hashed.tobytes()).hexdigest()[:12]


def build_grid_table(
    table: str,
    title: str,
    editor_key: str,
    template: pd.DataFrame,
    dimensions: Sequence[str],
    *,
    cache_key: ScenarioCacheKey,
    order_digest: str,
    value_labels: Labels | None,
    value_help: str | None = None,
    filter_prefix: str | None = None,
    shared_screen: str | None = None,
) -> GridTable:
    """표 하나를 그리드에 싣는 묶음 — 색인·본문은 내용 토큰·줄 차례·표시명 지문으로 캐시한다.

    `cache_key`·`order_digest` 는 `template` 을 만든 바로 그 키여야 한다(`get_reference_edit_table`
    과 같은 값 — 다르면 키와 내용이 어긋난다). 표가 큰 표 상한(`CAP_CELLS`·`CAP_BYTES`)을 넘으면
    `filter_prefix` 의 사이드바 필터 선택(세션 값)으로 고른 줄이나 앞 `CAP_ROWS` 줄만 싣는다.
    `shared_screen`(출처 이름)을 주면 공정은 화면들이 같이 쓰는 공용 공정 값으로 거른다."""
    spec = grid_spec(table, title, template, dimensions, value_help=value_help)
    labels = {
        column: mapping
        for column, mapping in (value_labels or {}).items()
        if column in spec.key_columns and mapping
    } or None
    digest = labels_digest(labels)
    content = "/".join(str(part) for part in cache_key)
    cells = len(template) * len(spec.value_columns)
    if cells <= CAP_CELLS:
        # 본문이 `CAP_BYTES` 를 넘는 표는 캐시가 본문 대신 None 을 담는다 — 넘는 표의 전체 본문을
        # 캐시에 두거나 크기만 보려고 회차마다 풀지 않는다.
        whole = get_edit_grid_base_within(
            cache_key,
            order_digest,
            table,
            digest,
            CAP_BYTES,
            _template=template,
            _spec=spec,
            _labels=labels,
        )
        if whole is not None:
            key = base_key(table, content, order_digest, digest)
            return GridTable(
                spec, editor_key, template, whole, key, labels, shared_screen=shared_screen
            )
    shown, filtered = _capped_rows(template, spec.key_columns, filter_prefix, shared_screen)
    rows_key = f"{digest}:{_rows_digest(shown)}"
    base = get_edit_grid_base(
        cache_key,
        order_digest,
        f"{table}#rows",
        rows_key,
        _template=shown,
        _spec=spec,
        _labels=labels,
    )
    notice = (CAP_FILTERED_NOTICE if filtered else CAP_HEAD_NOTICE).format(
        rows=len(template), cells=cells, shown=len(shown)
    )
    key = base_key(table, content, order_digest, rows_key)
    return GridTable(spec, editor_key, template, base, key, labels, notice, shared_screen)


def inbox_tables() -> set[str]:
    """inbox 에 쌓인 op 의 표 — 지금 그리지 않는 표라도 그 양식 색인이 있어야 반영한다."""
    pending = st.session_state.get(INBOX_KEY)
    if not isinstance(pending, list):
        return set()
    return {op.table for op in pending if isinstance(op, Op)}


def collect_outbox() -> None:
    """출납 콜백 — 새 op 를 inbox 에 쌓고(`edit_grid.collect_outbox`), 초안이 없던 표에는 빈 초안
    자리를 둔다.

    변경 칩 · 변경 판·화면 탭 점(`scenario_edit_bar.pending_edit_pages` — 세션 칸이 None
    이 아니면 센다)은 `app.py` 가 페이지 본문보다 **먼저** 그린다. op 는 본문이 반영하므로 빈 자리가
    없으면 첫 편집이 그 회차 칩에 서지 않고 다음 조작까지 늦는다(그리드는 첫 편집 뒤 다시
    보내지 않는다). 빈 자리(`{"cells": {}, "bad": {}}`)는 초안으로는 비어 있어(`draft_from` 이
    None) 「변경사항 적용」·단추 점·변경 수에 들지 않고, 같은 회차 본문의 반영이 진짜 초안(또는
    None)으로 덮는다.
    """
    edit_grid.collect_outbox(GRID_HOST, KEYS)
    for table in inbox_tables():
        if table in EDIT_TABLES and st.session_state.get(cells_key(table)) is None:
            st.session_state[cells_key(table)] = {"cells": {}, "bad": {}}


def apply_grid_inbox(tables: Mapping[str, GridTable]) -> bool:
    """inbox 의 op 를 표별 초안·이력에 반영한다(받을 표가 없는 op 는 버리고 수를 알린다).

    반영이 어느 표의 초안 칸을 **비웠으면** 참이다 — None 이 아니던 칸이 None 이 됨(Ctrl+Z 로
    0칸, 초안 없던 표의 첫 op 가 아무것도 바꾸지 않아 출납 콜백의 빈 자리를 걷음). 변경 칩·화면 탭
    점·테마 표지는 `app.py` 가 본문보다 먼저 그 칸으로 그렸으므로 부르는 쪽이 한 번 다시
    돈다(`st.rerun()` — 다음 회차엔 inbox 가 비어 거짓이라 되풀이되지 않는다)."""
    held = [name for name in tables if st.session_state.get(cells_key(name)) is not None]
    edit_grid.apply_inbox(KEYS, {name: table.slot for name, table in tables.items()})
    return any(st.session_state.get(cells_key(name)) is None for name in held)


def draft_pending(table: str) -> bool:
    """그 표에 적용하지 않은 그리드 편집이 있는가(「변경사항 적용」 을 켜는 조건 · 단추 점)."""
    return edit_grid.draft_pending(cells_key(table))


def draft_counts(table: str) -> tuple[int, int, int]:
    """(고친 칸, 고친 줄, 오류 칸)."""
    return change_counts(edit_grid.draft_of(cells_key(table)))


def discard_draft(table: str) -> None:
    """그 표의 초안·이력을 버린다(「편집 취소」 — 다음 회차에 새 `gen` 이 선다). 누름 직전에 보낸
    op 는 알림 없이 버린다(`edit_grid.discard_table` 의 `keys`)."""
    edit_grid.discard_table((cells_key(table), history_key(table)), KEYS)


def merged_template(table: GridTable) -> pd.DataFrame:
    """양식 사본에 그 표 초안을 업무 키로 덮은 전체 표 — 옛 편집표 적용과 같은 길로 넘긴다(칸 오류가
    남으면 ValueError — 부르기 전에 `error_notice` 로 멈춘다)."""
    return merge_into_template(
        table.template, table.spec, edit_grid.draft_of(cells_key(table.table))
    )


def draft_processes(table: GridTable) -> set[str]:
    """그 표 초안(고친 칸 · 오류 칸)이 걸린 줄의 공정(원본). 공정 칸이 없는 표는 빈 집합이다.

    초안 키는 업무 키(분류 칸 원값을 `KEY_SEPARATOR` 로 이은 글, 같은 키 둘째부터 꼬리표)라 공정
    자리만 떼어 읽는다 — 상한에 걸려 일부 줄만 실은 표도 전체 색인을 짓지 않는다."""
    if PROCESS_COLUMN not in table.dimensions:
        return set()
    draft = edit_grid.draft_of(cells_key(table.table))
    if draft is None:
        return set()
    position = table.dimensions.index(PROCESS_COLUMN)
    keys = {key for key, cells in draft["cells"].items() if cells}
    keys |= {key for key, cells in draft["bad"].items() if cells}
    processes: set[str] = set()
    for key in keys:
        parts = key.split(DUPLICATE_SEPARATOR, 1)[0].split(KEY_SEPARATOR)
        if position < len(parts):
            processes.add(parts[position])
    return processes


def outside_count(table: GridTable) -> int:
    """공용 공정 거름에 가려 이 표에 안 보이는 공정 가운데 초안이 있는 수(공용 값을 따라가지 않는
    표 · 걸린 값이 없으면 0)."""
    if table.shared_screen is None or PROCESS_COLUMN not in table.dimensions:
        return 0
    drafted = draft_processes(table)
    if not drafted:
        return 0
    options = table.template[PROCESS_COLUMN].dropna().drop_duplicates().tolist()
    return shared_process.count_outside(drafted, options)


def paste_notice(table: str) -> str | None:
    """「Excel 붙여넣기」 팝업 첫 줄 경고(그 표에 초안이 없으면 None)."""
    cells = draft_counts(table)[0]
    return PASTE_DROPS_DRAFT_NOTICE.format(n=f"{cells:,}") if cells else None


def filter_codes(table: GridTable, key_prefix: str) -> dict[int, list[int]] | None:
    """사이드바 「표 조건」 의 고른 값(세션 칸)을 껍데기 분류 사전 코드로 — 브라우저가 거른다.

    빈 선택은 「전체」 라 싣지 않는다. 고른 값이 사전에 하나도 없으면 빈 목록을 실어 줄이 없게
    거른다(필터가 행을 다 지운 것과 같다). 공용 공정 값을 따라가는 표(`shared_screen`)의 공정은 공용
    값 가운데 이 표에 있는 것이다 — 하나도 없으면 「전체」 다(`shared_process.applied`). 여기 실린
    거름이 곧 그리드의 「좁힌 표」 판정이라 공용 공정으로 좁혀진 표도 여러 줄 붙여넣기를 막는다."""
    dims = table.base.body.get("dims", [])
    filters: dict[int, list[int]] = {}
    for position, column in enumerate(table.dimensions):
        if position >= len(dims):
            continue
        selected: object
        if table.shared_screen is not None and column == PROCESS_COLUMN:
            selected = shared_process.applied(dims[position])
        else:
            selected = st.session_state.get(column_filter_key(key_prefix, column))
        if not isinstance(selected, list) or not selected:
            continue
        codes = {str(value): code for code, value in enumerate(dims[position])}
        filters[position] = [codes[str(value)] for value in selected if str(value) in codes]
    return filters or None


def error_notice(table: GridTable, process_label: Callable[[object], str]) -> str | None:
    """「변경사항 적용」 을 막는 칸 오류 알림(오류가 없으면 None) — 앞 몇 곳을 분류 표시명 ·
    월로. 알림은 마크다운(`st.error`)으로 그리므로 사람이 적은 분류 값·표시명은 칸마다
    `literal_markdown` 으로 막는다(「E2E~가정~A」 가 지움선이 되지 않게)."""
    draft = edit_grid.draft_of(cells_key(table.table))
    errors = change_counts(draft)[2]
    if not errors:
        return None
    places = []
    for entry in change_list(table.full_index(), draft):
        if entry.bad is None:
            continue
        row = table.template.iloc[entry.row]
        parts = [
            literal_markdown(process_label(row[column]) if column == "공정" else row[column])
            for column in table.dimensions
        ]
        places.append(f"{' · '.join(parts)} · {literal_markdown(entry.month)}")
        if len(places) == ERROR_PLACES:
            break
    return ERRORS_NOTICE.format(n=f"{errors:,}", places=", ".join(places))


def _shell(table: GridTable | None) -> dict[str, object]:
    if table is None:
        return edit_grid.shell_data(GRID_HOST, None, None, base_key="", changes_label=CHANGES_LABEL)
    shell = edit_grid.shell_data(
        GRID_HOST, table.base, table.spec, base_key=table.base_key, changes_label=CHANGES_LABEL
    )
    # 머리 글은 다른 기준 정보 표와 같은 짧은 이름(「양산구분」 → 「양산」). 껍데기는 회차마다 새
    # dict 라 고쳐도 캐시 본문은 그대로이고, 내용이 같으면 회차마다 같은 값이다.
    shell["keyCols"] = [
        {"name": column, "label": COLUMN_LABELS.get(column, column)} for column in table.dimensions
    ]
    return shell


def render_grid(
    table: GridTable | None, *, key_prefix: str | None = None, scope: str | None = None
) -> None:
    """그리드 자리 — 늘 같은 자리에서 부른다(표가 없으면 표 없는 껍데기로 마운트만 남긴다). `scope`
    는 표 아래 상태 줄의 편집 범위 글이다(`month_editor.scope_text`)."""
    filters = filter_codes(table, key_prefix) if table is not None and key_prefix else None
    feed = edit_grid.feed_data(
        GRID_HOST,
        table.slot if table is not None else None,
        KEYS,
        base_key=table.base_key if table is not None else "",
        filters=filters,
        scope=scope,
    )
    edit_grid.render_edit_grid(
        GRID_HOST,
        _shell(table),
        feed,
        on_outbox=collect_outbox,
        page_style=ONE_LINE_STYLE,
    )


@dataclass(frozen=True)
class Actions:
    """작업 줄 결과 — 「변경사항 적용」 이 눌렸는가와 그 바로 아래 알림 자리(적용 결과·오류)."""

    submitted: bool
    notice: DeltaGenerator


def paste_button_key(table: GridTable) -> str:
    """작업 줄 「Excel 붙여넣기」 단추 key — 팝업 호스트의 여는 콜백이 그 단추를 가리킨다."""
    return f"{table.editor_key}_open_paste"


def render_actions(table: GridTable, *, open_paste: Callable[[], None]) -> Actions:
    """표 위 작업 줄 — 「변경사항 적용」 · 「Excel 붙여넣기」 · 「편집 취소」(초안이 있을 때) ·
    「고칠 칸 n개」(칸 오류가 있을 때)와 그 아래 칸(거름 밖 표지 · 큰 표 표지 · 알림 자리). 기준
    창에서는 표 도구 막대가 이 줄 오른쪽에 함께 선다(`ONE_LINE_STYLE`). 고친 수는 표 도구 막대
    「적용 전 변경 (n)」 하나가 말한다(UI-TXT-07). key·글은 옛 편집표 작업 줄과 같다
    (`f"{editor_key}_apply"` 등).

    「변경사항 적용」 은 초안이 없으면 잠근다(같은 값 적용으로 리비전만 오르는 일을 막는 규칙). 첫
    편집은 그리드가 기다리지 않고 바로 보내므로 고친 뒤 한 회차 안에 켜진다."""
    cells, _, errors = draft_counts(table.table)
    pending = cells > 0
    with st.container(key=ACTION_ROW, horizontal=True, vertical_alignment="center", gap="small"):
        submitted = st.button(
            "변경사항 적용",
            icon=":material/check:",
            key=f"{table.editor_key}_apply",
            type="primary",
            help=APPLY_NOTICE if pending else APPLY_LOCKED_HELP,
            disabled=not pending,
        )
        st.button(
            "Excel 붙여넣기",
            icon=":material/content_paste:",
            key=paste_button_key(table),
            on_click=open_paste,
        )
        if pending:
            st.button(
                "편집 취소",
                icon=":material/undo:",
                key=f"{table.editor_key}_discard",
                on_click=discard_draft,
                args=(table.table,),
                help=DISCARD_HELP,
            )
            if errors:
                st.markdown(f":red[고칠 칸 {errors:,}개]")
    outside = outside_count(table) if pending else 0
    if outside:
        st.caption(OUTSIDE_NOTICE.format(n=outside), help=OUTSIDE_HELP.format(n=outside))
    if table.cap_notice is not None:
        st.caption(table.cap_notice, help=CAP_HELP)
    # 적용·붙여넣기 결과는 누른 자리 바로 아래 한 칸이다(`queue_reference_import_flash` 가 담은 것 —
    # 옛 편집표와 같은 칸 이름). 적용 오류·고칠 칸 알림도 같은 칸에 더 쓴다.
    return Actions(submitted, render_flash(f"{table.editor_key}_apply_flash"))
