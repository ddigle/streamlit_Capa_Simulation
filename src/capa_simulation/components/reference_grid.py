# Purpose: 기준 정보 편집 표 아홉을 범용 편집 그리드에 잇는다(규격·초안·작업 줄·오류·큰 표 상한).

"""기준 정보 화면과 범용 편집 그리드(`components/edit_grid.py`) 사이의 어댑터(편집 표 횡전개 —
2026-11-02 사용자 결정).

- **편집 표 아홉이 모두 그리드다**(`reference_grid_keys.EDIT_TABLES` — UPEH · 설비대수 보유·
  대여·가용 · 효율 · 여유율 · 일수 · Lot·WF측정률).
- **그리드 마운트는 하나**(`reference_grid_keys.GRID_HOST`) — 종류 단추로 표를 바꿔도 같은 key·같은
  자리에 표만 바꿔 싣는다. 읽기 보기(설비대수 현황·STEP 구성)를 고른 회차에는 표 없는 껍데기를 실어
  마운트만 남긴다(다시 마운트되면 보내지 않은 출납을 잃는다).
- **초안은 표마다 세션 칸**(업무 키 + 월 — `services/edit_grid`). 그리지 않는 표의 편집도 남고, 줄
  차례(공용 표시순서)만 바뀐 회차에도 같은 칸에 붙는다 — 그래서 사이드바 「표 조건」 필터를 잠그지
  않는다(브라우저가 feed `filters` 로 거른다).
- **편집은 출납 콜백이 세션 inbox 에 쌓기만** 하고(`edit_grid.collect_outbox`) 본문이 원본 토큰을 본
  뒤 반영한다(`apply_grid_inbox`) — 원본이 바뀌어 초안·이력을 버린 회차에는 새 `gen` 이 서서 그 전에
  보낸 op 가 버려지고 수가 토스트로 간다. 지금 보이지 않는 표의 op 도 그 표 초안에 쓴다. 반영이 초안
  칸을 비우면 화면이 한 번 다시 돈다(본문보다 먼저 그린 사이드바·탭 점이 옛 칸으로 섰다).
- **오류의 자리는 둘이다.** 숫자·범위·해석 오류는 칸 안(빨강 + 상태 줄 문구 — 그리드가 그린다)이고
  「변경사항 적용」 을 누르면 고칠 칸 알림으로 멈춘다(`error_notice`). 업무 규칙 오류
  (`reference_consistency`)는 적용할 때 문장으로(오늘과 같다 — 화면이 쓴다).
- **큰 표 안전 상한**(명세 1-2 의 22). 칸 수가 `CAP_CELLS` 를 넘거나 껍데기 본문이 `CAP_BYTES` 를
  넘으면 사이드바 「표 조건」 필터를 서버에서 걸어 그 줄만 싣고, 필터가 없거나 걸러도 넘치면 앞
  `CAP_ROWS` 줄만 싣고 작업 줄 아래에 알린다(바이트 상한을 넘는 표의 전체 본문은 캐시에 두지
  않는다 — `get_edit_grid_base_within`). 초안이 업무 키라 실은 줄이 바뀌어도 편집은 제 줄에
  남고, 적용은 언제나 **전체 양식**에 덮는다(`merged_template`). 합성 표본 최대는 UPEH 2,660줄 ×
  30개월 = 79,800칸(샘플 관측)이라 걸리지 않는다. 사내 실데이터 크기는 다음 배포에 잰다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.components import edit_grid
from capa_simulation.components.column_filter import apply_column_filters, column_filter_key
from capa_simulation.components.flash import render_flash
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.month_editor import APPLY_NOTICE, render_scope
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

# 변경 목록 이름 — 사이드바 「적용 전 편집」·단추 「변경사항 적용」 과 같은 말.
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
# 큰 표 안전 상한(명세 1-2 의 22) — 칸 수 · 껍데기 본문 JSON 바이트 · 상한에 걸렸을 때 싣는 줄 수.
CAP_CELLS: Final = 300_000
CAP_BYTES: Final = 400_000
CAP_ROWS: Final = 1_000
CAP_FILTERED_NOTICE: Final = (
    "표가 커서(전체 {rows:,}줄 · {cells:,}칸) 사이드바 「표 조건」 으로 고른 {shown:,}줄만"
    " 실었습니다 — 「변경사항 적용」 은 표 전체에 덮습니다."
)
CAP_HEAD_NOTICE: Final = (
    "표가 커서(전체 {rows:,}줄 · {cells:,}칸) 앞 {shown:,}줄만 실었습니다 — 사이드바 「표 조건」"
    " 으로 좁히면 고른 줄을 싣습니다. 「변경사항 적용」 은 표 전체에 덮습니다."
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
    # 큰 표 상한에 걸려 일부 줄만 실었으면 그 알림(아니면 None — 본문 색인이 곧 전체 양식이다).
    cap_notice: str | None = None

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
    template: pd.DataFrame, dimensions: Sequence[str], filter_prefix: str | None
) -> tuple[pd.DataFrame, bool]:
    """상한에 걸린 표에서 실을 줄 — (줄, 사이드바 필터로 골랐는가). 필터로 골라도 칸 수가 넘치면
    그 앞 `CAP_ROWS` 줄이다."""
    months = len(template.columns) - len(dimensions)
    if filter_prefix is not None:
        chosen = apply_column_filters(template, list(dimensions), key_prefix=filter_prefix)
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
) -> GridTable:
    """표 하나를 그리드에 싣는 묶음 — 색인·본문은 내용 토큰·줄 차례·표시명 지문으로 캐시한다.

    `cache_key`·`order_digest` 는 `template` 을 만든 바로 그 키여야 한다(`get_reference_edit_table`
    과 같은 값 — 다르면 키와 내용이 어긋난다). 표가 큰 표 상한(`CAP_CELLS`·`CAP_BYTES`)을 넘으면
    `filter_prefix` 의 사이드바 필터 선택(세션 값)으로 고른 줄이나 앞 `CAP_ROWS` 줄만 싣는다."""
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
            return GridTable(spec, editor_key, template, whole, key, labels)
    shown, filtered = _capped_rows(template, spec.key_columns, filter_prefix)
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
    return GridTable(spec, editor_key, template, base, key, labels, notice)


def inbox_tables() -> set[str]:
    """inbox 에 쌓인 op 의 표 — 지금 그리지 않는 표라도 그 양식 색인이 있어야 반영한다."""
    pending = st.session_state.get(INBOX_KEY)
    if not isinstance(pending, list):
        return set()
    return {op.table for op in pending if isinstance(op, Op)}


def collect_outbox() -> None:
    """출납 콜백 — 새 op 를 inbox 에 쌓고(`edit_grid.collect_outbox`), 초안이 없던 표에는 빈 초안
    자리를 둔다.

    사이드바 「적용 전 편집」·화면 탭 점(`scenario_edit_bar.pending_edit_pages` — 세션 칸이 None
    이 아니면 센다)은 `app.py` 가 페이지 본문보다 **먼저** 그린다. op 는 본문이 반영하므로 빈 자리가
    없으면 첫 편집이 그 회차 사이드바에 서지 않고 다음 조작까지 늦는다(그리드는 첫 편집 뒤 다시
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
    0칸, 초안 없던 표의 첫 op 가 아무것도 바꾸지 않아 출납 콜백의 빈 자리를 걷음). 사이드바 「적용
    전 편집」·화면 탭 점·테마 표지는 `app.py` 가 본문보다 먼저 그 칸으로 그렸으므로 부르는 쪽이 한
    번 다시 돈다(`st.rerun()` — 다음 회차엔 inbox 가 비어 거짓이라 되풀이되지 않는다)."""
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


def paste_notice(table: str) -> str | None:
    """「Excel 붙여넣기」 팝업 첫 줄 경고(그 표에 초안이 없으면 None)."""
    cells = draft_counts(table)[0]
    return PASTE_DROPS_DRAFT_NOTICE.format(n=f"{cells:,}") if cells else None


def filter_codes(table: GridTable, key_prefix: str) -> dict[int, list[int]] | None:
    """사이드바 「표 조건」 의 고른 값(세션 칸)을 껍데기 분류 사전 코드로 — 브라우저가 거른다.

    빈 선택은 「전체」 라 싣지 않는다. 고른 값이 사전에 하나도 없으면 빈 목록을 실어 줄이 없게
    거른다(필터가 행을 다 지운 것과 같다)."""
    dims = table.base.body.get("dims", [])
    filters: dict[int, list[int]] = {}
    for position, column in enumerate(table.dimensions):
        selected = st.session_state.get(column_filter_key(key_prefix, column))
        if not isinstance(selected, list) or not selected or position >= len(dims):
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


def render_grid(table: GridTable | None, *, key_prefix: str | None = None) -> None:
    """그리드 자리 — 늘 같은 자리에서 부른다(표가 없으면 표 없는 껍데기로 마운트만 남긴다)."""
    filters = filter_codes(table, key_prefix) if table is not None and key_prefix else None
    feed = edit_grid.feed_data(
        GRID_HOST,
        table.slot if table is not None else None,
        KEYS,
        base_key=table.base_key if table is not None else "",
        filters=filters,
    )
    edit_grid.render_edit_grid(
        GRID_HOST,
        _shell(table),
        feed,
        on_outbox=collect_outbox,
    )


@dataclass(frozen=True)
class Actions:
    """작업 줄 결과 — 「변경사항 적용」 이 눌렸는가와 그 바로 아래 알림 자리(적용 결과·오류)."""

    submitted: bool
    notice: DeltaGenerator


def render_actions(
    table: GridTable, visible: pd.DataFrame, *, open_paste: Callable[[], None]
) -> Actions:
    """표 위 작업 줄 — 「변경사항 적용」 · 「Excel 붙여넣기」 · 「편집 취소」(초안이 있을 때) ·
    변경 수, 그 아래 편집 범위 줄과 알림 자리. key·글은 옛 편집표 작업 줄과 같다
    (`f"{editor_key}_apply"` 등).

    「변경사항 적용」 은 초안이 없으면 잠근다(같은 값 적용으로 리비전만 오르는 일을 막는 규칙). 첫
    편집은 그리드가 기다리지 않고 바로 보내므로 고친 뒤 한 회차 안에 켜진다."""
    cells, rows, errors = draft_counts(table.table)
    pending = cells > 0
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        submitted = st.button(
            "변경사항 적용",
            icon=":material/check:",
            key=f"{table.editor_key}_apply",
            type="primary",
            help=APPLY_NOTICE,
            disabled=not pending,
        )
        st.button(
            "Excel 붙여넣기",
            icon=":material/content_paste:",
            key=f"{table.editor_key}_open_paste",
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
            fix = f" · :red[고칠 칸 {errors:,}개]" if errors else ""
            st.markdown(f"**변경사항 확인** &nbsp;{cells:,}개 값 · {rows:,}개 행{fix}")
    render_scope(table.template, visible, table.months)
    if table.cap_notice is not None:
        st.info(table.cap_notice, icon=":material/filter_alt:")
    # 적용·붙여넣기 결과는 누른 자리 바로 아래 한 칸이다(`queue_reference_import_flash` 가 담은 것 —
    # 옛 편집표와 같은 칸 이름). 적용 오류·고칠 칸 알림도 같은 칸에 더 쓴다.
    return Actions(submitted, render_flash(f"{table.editor_key}_apply_flash"))
