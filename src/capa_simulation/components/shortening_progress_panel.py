# Purpose: 필요단축일정 진척 비교의 기준선 고르기·저장·지우기와 요약·호기 두 줄 카드를 그린다.

"""필요단축일정 탭의 진척 비교(2026-10-08 사용자 요청, 시안 B 「호기마다 과거·현재 두 줄」).

`required_shortening_panel` 이 부른다. 이 모듈은 고르고 그리기만 한다 — 짝짓기·요약은
`services/shortening_progress.py`, 기준선 모델은 `services/shortening_baseline.py`, 저장은 설비 DB
0021 이다.

- **진척 비교**(본문 머리, 목표 확보율 옆)는 세션 값이다. `비교 안 함` 이 기본이고 그때는 이 모듈의
  요약·카드를 하나도 그리지 않는다 — 기존 화면 그대로다. 기준선 목록만 캐시에서 읽는다.
- **기준선 저장**은 CSV 단추 줄의 팝오버다. 지금 화면이 보던 계획(목표 다섯)을 그대로 얼려 공용
  목록에 남긴다. 샘플 fleet·미저장 시나리오 편집에서는 저장하지 않는다 — 고칠 수 없는 공용 기록이
  합성값이나 남이 볼 수 없는 편집본에서 나오면 안 된다. 미저장 설비 편집은 막지 않는다(계산은 설비
  저장본만 읽는다).
- **기준선 지우기**는 고른 기준선이 있을 때만 서고, 그 기준선마다 다른 확인 칸을 체크해야 지운다.
- 비교 화면은 요약(단축 필요일수 합계 과거 → 현재, 호기 변동, 신규 투자) → CSV 줄 → 범위가 다르면
  한 줄 → 공정 카드다. 카드는 호기마다 **과거**(회색: ◀ 필요 시점 ── ○ 확보 시점)와 **현재**(진하게:
  ◀ ━━ ●) 두 줄이 같은 달 축 위에 선다. 늘어난 호기·새로 필요한 호기의 현재 줄은 증가색이다.

색은 모두 `design/tokens` 에서 실행마다 읽는다(밝은·어두운 테마). 줄임·해소는 `ACCENT`, 늘어남·
신규 필요는 `DELTA_INCREASE`(증감 글자색), 변동 없음·신규 유지·범위 밖·필요 시점 지남은
`TEXT_MUTED` 다. 호기·공정 이름은 사용자가 적은 글이라 모두 이스케이프한다. 공정 이름은 화면만 공정
표시명이고 짝짓기·CSV 는 원본이다.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date

import pandas as pd
import streamlit as st

import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.shortening_timeline import (
    month_day,
    timeline_axis,
    timeline_grid_lines,
    timeline_position,
)
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.design import tokens
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS
from capa_simulation.persistence.equipment_cache import (
    clear_shortening_baseline_cache,
    get_equipment_repository,
    load_shortening_baseline,
    load_shortening_baselines,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.required_shortening import (
    KIND_NEW,
    ShorteningPlan,
    level_percent,
)
from capa_simulation.services.shortening_baseline import (
    BASELINE_NAME_MAX_LENGTH,
    BASELINE_SAVED_BY_MAX_LENGTH,
    BaselineProvenance,
    ShorteningBaseline,
    ShorteningBaselineSummary,
    baseline_label,
    default_baseline_name,
    freeze_plan,
    normalize_saved_by,
)
from capa_simulation.services.shortening_progress import (
    PROGRESS_IMPROVED,
    PROGRESS_KEPT_NEW,
    PROGRESS_LAPSED,
    PROGRESS_NEW,
    PROGRESS_OUT_OF_SCOPE,
    PROGRESS_RESOLVED,
    PROGRESS_UNCHANGED,
    PROGRESS_WORSENED,
    ProgressSummary,
    ScopeDifference,
    scope_difference,
    summarize_progress,
)

__all__ = [
    "NO_COMPARISON",
    "SHORTENING_COMPARE_KEY",
    "BaselineSaveContext",
    "ProgressView",
    "load_baseline_options",
    "load_selected_baseline",
    "progress_card_markup",
    "progress_style",
    "progress_summary_markup",
    "progress_view",
    "render_baseline_controls",
    "render_baseline_notice",
    "render_compare_select",
    "render_progress_csv",
    "scope_note",
]

SHORTENING_COMPARE_KEY = "equipment_shortening_compare_v1"
NO_COMPARISON = "-"
"""「비교 안 함」. 기준선 id 는 uuid hex 라 이 글자와 겹치지 않는다."""

_BASELINE_FORM_KEY = "equipment_shortening_baseline_form"
_BASELINE_NAME_KEY = "equipment_shortening_baseline_name"
_BASELINE_SAVED_BY_KEY = "equipment_shortening_baseline_saved_by"
_BASELINE_FORM_GENERATION_KEY = "equipment_shortening_baseline_form_generation"
_BASELINE_DELETE_CONFIRM_KEY = "equipment_shortening_baseline_delete_confirm"
_BASELINE_DELETE_KEY = "equipment_shortening_baseline_delete"
_BASELINE_NOTICE_KEY = "equipment_shortening_baseline_notice"
_PROGRESS_CSV_KEY = "equipment_shortening_progress_csv"

# 호기 줄: 이름·배지 · 「과거/현재」 · 두 줄 타임라인 · 줄마다 「기존 → 필요 −N일」.
_NAME_PX = 230
_TAG_PX = 34
_RESULT_PX = 196
_TRACK_MIN_PX = 420
_LANE_PX = 18
_LANE_CENTER_PX = _LANE_PX / 2
_LANE_GAP_PX = 4
_MAX_AXIS_LABELS = 12


@dataclass(frozen=True)
class BaselineSaveContext:
    """「기준선 저장」 이 얼릴 계획과 머리에 남길 출처. `refusal` 이 있으면 저장하지 않는다."""

    database_path: str
    plan: ShorteningPlan
    today: date
    provenance: BaselineProvenance
    refusal: str | None = None


@dataclass(frozen=True)
class ProgressView:
    """비교 화면에 세울 카드. 지금 범위의 공정(화면 차례)과 기준선에만 있던 공정."""

    rows: pd.DataFrame
    cards: tuple[str, ...]
    outside: tuple[str, ...]
    summary: ProgressSummary

    @property
    def csv_processes(self) -> tuple[str, ...]:
        return (*self.cards, *self.outside)


# ------------------------------------------------------------------ 고르기·저장·지우기


def load_baseline_options(
    database_path: str | None,
) -> tuple[ShorteningBaselineSummary, ...] | None:
    """「진척 비교」 선택지. 설비 DB 경로가 없는 자리(컴포넌트만 띄운 곳)면 None — 상자를 세우지
    않는다. 못 읽으면 빈 목록이다(화면은 떠야 한다)."""
    if database_path is None:
        return None
    try:
        return load_shortening_baselines(database_path)
    except BOOTSTRAP_ERRORS:
        return ()


def render_compare_select(baselines: Sequence[ShorteningBaselineSummary]) -> str:
    """「진척 비교」 상자. 고른 기준선 id, 고르지 않았으면 `NO_COMPARISON`.

    세션에 값이 없거나 고른 기준선이 목록에서 사라졌으면(누가 지웠으면) `비교 안 함` 을 **적는다**
    (pop 하면 브라우저가 옛 선택을 계속 보인다 — AGENTS 9장). 라벨은 「이름 · 저장일」 이라 회차마다
    바뀌지 않는다(기준선은 고칠 수 없다).
    """
    options = [NO_COMPARISON, *(summary.baseline_id for summary in baselines)]
    if st.session_state.get(SHORTENING_COMPARE_KEY) not in options:
        st.session_state[SHORTENING_COMPARE_KEY] = NO_COMPARISON
    labels = {summary.baseline_id: baseline_label(summary) for summary in baselines}
    value = st.selectbox(
        "진척 비교",
        options=options,
        format_func=lambda option: labels.get(option, "비교 안 함"),
        key=SHORTENING_COMPARE_KEY,
        persist_state="session",
        help=(
            "저장해 둔 기준선(과거 시점의 계획 결과)을 고르면 지금 결과와 호기마다 두 줄로 "
            "견줍니다."
        ),
    )
    return str(value)


def load_selected_baseline(
    database_path: str | None, baseline_id: str
) -> ShorteningBaseline | None:
    """고른 기준선 한 벌(캐시). 비교 안 함이거나 못 읽으면 None — 못 읽으면 까닭을 한 줄 적는다."""
    if database_path is None or baseline_id == NO_COMPARISON:
        return None
    try:
        return load_shortening_baseline(database_path, baseline_id)
    except BOOTSTRAP_ERRORS as exc:
        st.warning(f"기준선을 읽지 못해 진척 비교를 하지 않았습니다 — {exc}")
        return None


def render_baseline_notice() -> None:
    """저장·지우기 콜백이 남긴 알림 한 번. 토스트라 아래 위젯의 자리를 밀지 않는다."""
    notice = st.session_state.pop(_BASELINE_NOTICE_KEY, None)
    if not isinstance(notice, tuple) or len(notice) != 2:
        return
    kind, message = notice
    st.toast(
        str(message),
        icon=":material/check_circle:" if kind == "success" else ":material/block:",
    )


def render_baseline_controls(
    save: BaselineSaveContext | None, selected: ShorteningBaselineSummary | None
) -> None:
    """CSV 단추 줄의 「기준선 저장」 팝오버와, 고른 기준선이 있으면 「기준선 지우기」 팝오버."""
    if save is None:
        return
    with st.popover("기준선 저장", icon=":material/bookmark_add:"):
        _render_save_form(save)
    if selected is not None:
        with st.popover("기준선 지우기", icon=":material/bookmark_remove:"):
            _render_delete(save.database_path, selected)


def _render_save_form(save: BaselineSaveContext) -> None:
    st.caption(
        "지금 계획의 다섯 목표 결과(호기별 필요·확보 시점과 단축일수)를 그대로 얼려 모든 사용자의 "
        "「진척 비교」 목록에 남깁니다. 저장한 기준선은 고칠 수 없습니다."
    )
    if save.refusal is not None:
        st.info(save.refusal, icon=":material/block:")
        return
    # 이름 칸은 저장에 성공할 때마다 key 세대를 올려 새 칸으로 세운다. 닫힌 팝오버 안의 칸은 세션에
    # 적은 값을 받지 못해 방금 저장한 이름을 들고 있다가 되보낸다(사이드바 저장 폼과 같은 까닭).
    name_key = _name_key()
    with st.form(_BASELINE_FORM_KEY, border=False):
        st.text_input(
            "기준선 이름",
            value=default_baseline_name(save.today),
            key=name_key,
            max_chars=BASELINE_NAME_MAX_LENGTH,
            help="목록에서 이 이름으로 고릅니다. 비우거나 이미 있는 이름이면 저장하지 않습니다.",
        )
        st.text_input(
            "저장한 사람 (선택)",
            key=_BASELINE_SAVED_BY_KEY,
            persist_state="session",
            max_chars=BASELINE_SAVED_BY_MAX_LENGTH,
            placeholder="예: 홍길동 / 제조기술",
        )
        # 단추는 잠그지 않는다 — 누른 회차에 콜백이 판정해 알린다(AGENTS 9장).
        st.form_submit_button(
            "기준선 저장",
            icon=":material/bookmark_add:",
            width="stretch",
            on_click=_save_baseline,
            args=(save, name_key),
        )


def _render_delete(database_path: str, selected: ShorteningBaselineSummary) -> None:
    st.caption(
        f"「{selected.name}」 기준선을 지웁니다. 모든 사용자의 목록에서 사라지고 되돌릴 수 "
        "없습니다."
    )
    # 확인 칸은 기준선마다 다르다 — 한 기준선에서 체크해 둔 채 다른 기준선을 고르면 한 번에 지워지지
    # 않게. `persist_state` 를 주지 않는다(AGENTS 9장 — 확인용 체크박스).
    confirm_key = _confirm_key(selected.baseline_id)
    st.checkbox("정말 지웁니다", key=confirm_key)
    st.button(
        "기준선 지우기",
        icon=":material/delete:",
        key=_BASELINE_DELETE_KEY,
        on_click=_delete_baseline,
        args=(database_path, selected.baseline_id, selected.name),
    )


def _generation() -> int:
    value = st.session_state.get(_BASELINE_FORM_GENERATION_KEY, 0)
    return value if isinstance(value, int) else 0


def _name_key() -> str:
    generation = _generation()
    return _BASELINE_NAME_KEY if generation == 0 else f"{_BASELINE_NAME_KEY}__g{generation}"


def _confirm_key(baseline_id: str) -> str:
    return f"{_BASELINE_DELETE_CONFIRM_KEY}__{baseline_id}"


def _notice(kind: str, message: str) -> None:
    st.session_state[_BASELINE_NOTICE_KEY] = (kind, message)


def _save_baseline(save: BaselineSaveContext, name_key: str) -> None:
    """「기준선 저장」 콜백. 위젯보다 먼저 돌아 새 기준선이 그 회차의 「진척 비교」 목록에 바로
    선다.

    얼리는 계획은 단추를 그린 회차의 것 — 사용자가 보던 화면이다. 이름이 비었거나 겹치면 쓰지 않고
    알린다(이름 칸은 그대로 남아 고쳐 다시 누른다).
    """
    if save.refusal is not None:
        _notice("warning", save.refusal)
        return
    provenance = replace(
        save.provenance, saved_by=normalize_saved_by(st.session_state.get(_BASELINE_SAVED_BY_KEY))
    )
    try:
        draft = freeze_plan(save.plan, name=st.session_state.get(name_key), provenance=provenance)
        summary = get_equipment_repository(save.database_path).save_shortening_baseline(draft)
    except BOOTSTRAP_ERRORS as exc:
        _notice("warning", f"기준선을 저장하지 않았습니다 — {exc}")
        return
    clear_shortening_baseline_cache()
    st.session_state[_BASELINE_FORM_GENERATION_KEY] = _generation() + 1
    _notice(
        "success",
        f"기준선을 저장했습니다 — 「{summary.name}」. 「진척 비교」에서 고르면 지금 결과와 "
        "견줍니다.",
    )


def _delete_baseline(database_path: str, baseline_id: str, name: str) -> None:
    """「기준선 지우기」 콜백. 확인 칸을 체크하지 않았으면 지우지 않는다. 지우면 비교를 끈다."""
    if not st.session_state.get(_confirm_key(baseline_id)):
        _notice("warning", "「정말 지웁니다」를 체크한 뒤 지우세요.")
        return
    try:
        deleted = get_equipment_repository(database_path).delete_shortening_baseline(baseline_id)
    except BOOTSTRAP_ERRORS as exc:
        _notice("warning", f"기준선을 지우지 못했습니다 — {exc}")
        return
    clear_shortening_baseline_cache()
    st.session_state[SHORTENING_COMPARE_KEY] = NO_COMPARISON
    _notice(
        "success",
        f"기준선을 지웠습니다 — 「{name}」."
        if deleted
        else f"이미 지워진 기준선입니다 — 「{name}」.",
    )


# ------------------------------------------------------------------ 데이터 고르기


def progress_view(
    rows: pd.DataFrame,
    *,
    ordered: Sequence[str],
    scope: Sequence[str],
    selected: bool,
) -> ProgressView:
    """비교 화면의 카드 목록과 요약.

    공정을 고르면 그 공정을 모두 카드로 세운다(두 시점 모두 단축할 호기가 없어도). 고르지 않으면
    지금 맞댄 공정 가운데 **어느 한 시점이라도** 단축할 호기가 있는 공정, 그 뒤에 기준선에만 있던
    공정(「지금 범위 밖」, 접어 둔다)이다. 요약은 지금 범위(`scope`)만 센다 — 범위 밖 공정은 견줄
    짝이 없다.
    """
    present = set(rows.loc[rows["상태"].ne(PROGRESS_OUT_OF_SCOPE), "공정"])
    cards = (
        tuple(scope) if selected else tuple(process for process in ordered if process in present)
    )
    outside = (
        ()
        if selected
        else tuple(dict.fromkeys(rows.loc[rows["상태"].eq(PROGRESS_OUT_OF_SCOPE), "공정"]))
    )
    return ProgressView(
        rows=rows,
        cards=cards,
        outside=tuple(str(process) for process in outside),
        summary=summarize_progress(rows, scope),
    )


def render_progress_csv(
    key: simulation_cache.RequiredShorteningCacheKey,
    baseline: ShorteningBaseline,
    view: ProgressView,
    level: float,
    today: date,
) -> None:
    """「진척 비교 CSV」 — 고른 목표, 화면의 카드 차례(범위 밖 공정은 뒤). 파일 이름의 둘째 날짜는
    계획의 오늘(`today`)이다."""
    data = simulation_cache.get_shortening_progress_csv(
        key,
        baseline.summary.baseline_id,
        float(level),
        view.csv_processes,
        _rows=view.rows,
    )
    render_csv_download(
        data=data,
        file_name=(
            f"required_shortening_progress_{level_percent(level)}pct_"
            f"{baseline.summary.saved_at:%Y%m%d}_vs_{today:%Y%m%d}.csv"
        ),
        key=_PROGRESS_CSV_KEY,
        label="진척 비교 CSV",
    )


def scope_note(
    baseline: ShorteningBaseline,
    plan: ShorteningPlan,
    months: Sequence[int],
    labels: ProcessLabels,
    *,
    lapsed: int = 0,
) -> str | None:
    """기준선과 지금의 조회 달·맞댄 공정이 다르거나 필요 시점이 지난 호기(`lapsed` 대)가 있으면 그
    알림. 둘 다 없으면 None."""
    difference = scope_difference(
        baseline_months=(baseline.summary.start_month, baseline.summary.end_month),
        baseline_processes=baseline.processes,
        months=months,
        processes=plan.processes,
    )
    parts = []
    if difference.differs:
        parts.append(_scope_text(difference, labels))
    if lapsed:
        parts.append(
            f"기준선의 그날 오늘({baseline.summary.plan_today:%Y-%m-%d}) 뒤로 오늘"
            f"({plan.today:%Y-%m-%d})이 지나, 필요 시점이 이미 지난 호기 {lapsed}대는 견주지 "
            "않습니다(지금 계획은 오늘보다 앞으로 당길 수 없어 줄어든 날수가 진척이 아닙니다)."
        )
    if not parts:
        return None
    return ":material/info: " + "  \n:material/info: ".join(parts)


def _scope_text(difference: ScopeDifference, labels: ProcessLabels) -> str:
    parts: list[str] = []
    if difference.months_differ:
        parts.append(
            f"조회 달이 기준선 {_span(difference.baseline_months)}, 지금 "
            f"{_span(difference.current_months)} 입니다"
        )
    if difference.added:
        parts.append("지금만 맞댄 공정 " + _names(difference.added, labels))
    if difference.removed:
        parts.append("기준선에만 있던 공정 " + _names(difference.removed, labels))
    return (
        " · ".join(parts)
        + " — 범위 차이로 생긴 변동이 섞여 있을 수 있습니다(끝 달의 부족이 새로 들거나 "
        "빠진다)."
    )


def _span(months: tuple[int, int]) -> str:
    return f"{month_label(months[0])}–{month_label(months[1])}"


def _names(processes: Sequence[str], labels: ProcessLabels, limit: int = 4) -> str:
    shown = ", ".join(labels.label(process) for process in processes[:limit])
    rest = len(processes) - limit
    return f"{len(processes)}개({shown}{f' 외 {rest}개' if rest > 0 else ''})"


# ------------------------------------------------------------------ 글자 모양


def _escape(text: object) -> str:
    return html.escape(str(text))


def _whole(value: object) -> int | None:
    number = pd.to_numeric(pd.Series([value], dtype="object"), errors="coerce").iloc[0]
    return None if pd.isna(number) else int(number)


def _day(value: object) -> date | None:
    return value if isinstance(value, date) else None


def _signed_days(days: int) -> str:
    return f"+{days}일" if days > 0 else f"−{abs(days)}일"


def _change_text(change: int) -> tuple[str, str]:
    """(글, 색) — 줄임은 `ACCENT`, 늘어남은 `DELTA_INCREASE`, 같으면 `TEXT_MUTED`."""
    if change < 0:
        return f"{-change}일 줄임", tokens.ACCENT
    if change > 0:
        return f"{change}일 늘어남", tokens.DELTA_INCREASE
    return "변동 없음", tokens.TEXT_MUTED


def progress_style() -> str:
    """진척 비교의 서식. `required_shortening_panel._style` 의 `shk-*` 위에 얹는다(실행마다
    만든다)."""
    display = tokens.FONT_FAMILY_DISPLAY
    return f"""
<style>
.shk-prog-summary {{display:flex;flex-wrap:wrap;gap:12px}}
.shk-prog-summary > .shk-kpi {{flex:1 1 220px;min-width:0}}
.shk-prog-summary > .shk-prog-total {{flex:2 1 400px;flex-direction:row;align-items:center;
  gap:18px}}
.shk-prog-total-figure {{display:flex;flex-direction:column;gap:2px;flex:none}}
.shk-prog-bars {{flex:1 1 140px;display:flex;flex-direction:column;gap:6px;min-width:120px}}
.shk-prog-bar-row {{display:flex;align-items:center;gap:8px;font-size:12px;
  color:{tokens.TEXT_MUTED};font-variant-numeric:tabular-nums}}
.shk-prog-bar-row.now {{color:{tokens.TEXT};font-weight:700}}
.shk-prog-bar-tag {{width:30px;flex:none}}
.shk-prog-bar-track {{flex:1;height:10px;position:relative}}
.shk-prog-bar {{position:absolute;left:0;top:0;bottom:0;border-radius:5px}}
.shk-prog-bar-value {{flex:none;min-width:48px;text-align:right}}
.shk-prog-change {{font-family:{display};font-weight:800;font-size:18px;white-space:nowrap}}
.shk-prog-line {{font-size:13px;color:{tokens.TEXT};line-height:1.6}}
.shk-prog-line b {{font-family:{display};font-weight:800;white-space:nowrap}}
.shk-prog-head-sum {{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;font-size:13px;
  color:{tokens.TEXT_MUTED};font-variant-numeric:tabular-nums}}
.shk-prog-head-sum b {{color:{tokens.TEXT};font-family:{display};font-weight:800}}
.shk-prog-delta {{font-weight:700}}
.shk-prog-unit {{display:grid;grid-template-columns:{_NAME_PX}px {_TAG_PX}px
  minmax({_TRACK_MIN_PX}px,1fr) {_RESULT_PX}px;align-items:center;column-gap:10px;
  background:{tokens.SURFACE_SUBTLE};border:1px solid {tokens.BORDER};border-radius:8px;
  padding:4px 10px}}
.shk-prog-unit.shk-unit-axis {{background:none;border:none;padding:0 10px}}
.shk-prog-label {{display:flex;flex-direction:column;gap:3px;min-width:0}}
.shk-prog-meta {{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:11px;
  color:{tokens.TEXT_MUTED};white-space:nowrap}}
.shk-prog-badge {{font-size:11px;font-weight:700;padding:0 7px;border-radius:999px;
  border:1px solid;line-height:16px;white-space:nowrap}}
.shk-prog-tags {{display:flex;flex-direction:column;gap:{_LANE_GAP_PX}px;font-size:11px;
  color:{tokens.TEXT_MUTED};text-align:right;line-height:{_LANE_PX}px}}
.shk-prog-tags .now {{color:{tokens.TEXT};font-weight:700}}
.shk-prog-tracks {{position:relative;display:flex;flex-direction:column;gap:{_LANE_GAP_PX}px}}
.shk-prog-lane {{position:relative;height:{_LANE_PX}px}}
.shk-prog-results {{display:flex;flex-direction:column;gap:{_LANE_GAP_PX}px;align-items:flex-end;
  font-size:12px;white-space:nowrap;font-variant-numeric:tabular-nums;line-height:{_LANE_PX}px}}
.shk-prog-results .past {{color:{tokens.TEXT_MUTED}}}
.shk-prog-results .now {{color:{tokens.TEXT}}}
.shk-prog-results b {{font-family:{display};font-weight:800}}
.shk-prog-out {{background:{tokens.SURFACE};border:1px dashed {tokens.BORDER_STRONG};
  border-radius:12px;color:{tokens.TEXT}}}
.shk-prog-out > summary {{cursor:pointer;padding:10px 18px;display:flex;align-items:baseline;
  gap:10px;flex-wrap:wrap;font-size:13px;color:{tokens.TEXT_MUTED}}}
.shk-prog-out > summary .shk-card-name {{font-size:16px;color:{tokens.TEXT}}}
</style>
"""


# ------------------------------------------------------------------ 요약


def progress_summary_markup(
    view: ProgressView,
    baseline: ShorteningBaseline,
    level: float,
    *,
    selected: bool,
) -> str:
    """요약 세 칸 — 단축 필요일수 합계(과거 → 현재 막대 두 줄), 호기 변동, 기준선."""
    summary = view.summary
    top = max(summary.past_days, summary.current_days, 1)
    change, color = _change_text(summary.change)
    bars = "".join(
        f'<div class="shk-prog-bar-row{css}"><span class="shk-prog-bar-tag">{tag}</span>'
        '<span class="shk-prog-bar-track"><span class="shk-prog-bar" '
        f'style="width:{days / top * 100:.1f}%;background:{fill}"></span></span>'
        f'<span class="shk-prog-bar-value">{days:,}일</span></div>'
        for tag, css, days, fill in (
            ("과거", "", summary.past_days, tokens.TEXT_MUTED),
            ("현재", " now", summary.current_days, tokens.TEXT),
        )
    )
    scope = "고른 공정" if selected else "지금 맞댄 공정"
    lapsed_note = (
        f'<span class="shk-kpi-note">필요 시점 지난 {summary.lapsed}대(현재 '
        f"{summary.lapsed_current_days:,}일) 빼고 견줌</span>"
        if summary.lapsed
        else ""
    )
    total = (
        '<div class="shk-kpi shk-prog-total">'
        '<div class="shk-prog-total-figure"><span class="shk-kpi-label">단축 필요일수 합계</span>'
        f'<span class="shk-kpi-value">{summary.current_days:,}일</span>'
        f'<span class="shk-kpi-note">목표 {level_percent(level)}% · {scope} · 당긴 호기의 합'
        f"</span>{lapsed_note}</div>"
        f'<div class="shk-prog-bars">{bars}</div>'
        f'<span class="shk-prog-change" style="color:{color}">{_escape(change)}</span></div>'
    )
    counts = [
        _count("개선", summary.improved, tokens.ACCENT),
        _count("악화", summary.worsened, tokens.DELTA_INCREASE),
        _count("변동 없음", summary.unchanged, tokens.TEXT_MUTED),
        _count("신규", summary.new, tokens.DELTA_INCREASE),
        _count("해소", summary.resolved, tokens.ACCENT),
    ]
    if summary.kept_new:
        counts.append(_count("신규 유지", summary.kept_new, tokens.TEXT_MUTED))
    if summary.lapsed:
        counts.append(_count("필요 시점 지남", summary.lapsed, tokens.TEXT_MUTED))
    units = (
        '<div class="shk-kpi"><span class="shk-kpi-label">호기 변동</span>'
        f'<span class="shk-prog-line">{" · ".join(counts)}</span>'
        '<span class="shk-kpi-label">신규 투자(추가N)</span>'
        f'<span class="shk-prog-line"><b>{summary.past_virtual}</b>대 → '
        f"<b>{summary.current_virtual}</b>대</span></div>"
    )
    head = baseline.summary
    source = [
        f"저장 {head.saved_at:%Y-%m-%d %H:%M}" + (f" · {head.saved_by}" if head.saved_by else "")
    ]
    source.append(
        f"그날 오늘 {head.plan_today:%Y-%m-%d} · 조회 {_span((head.start_month, head.end_month))}"
    )
    origin = []
    if head.equipment_revision_no is not None:
        origin.append(f"설비 r{head.equipment_revision_no}")
    if head.scenario_name:
        revision = f" r{head.scenario_revision_no}" if head.scenario_revision_no is not None else ""
        origin.append(f"시나리오 {head.scenario_name}{revision}")
    if origin:
        source.append(" · ".join(origin))
    detail = "".join(f'<span class="shk-kpi-note">{_escape(line)}</span>' for line in source)
    reference = (
        '<div class="shk-kpi"><span class="shk-kpi-label">기준선</span>'
        f'<span class="shk-prog-line"><b>{_escape(head.name)}</b></span>{detail}</div>'
    )
    return (
        '<div class="shk-prog-summary" role="group" aria-label="진척 비교 요약">'
        f"{total}{units}{reference}</div>"
    )


def _count(label: str, value: int, color: str) -> str:
    style = f' style="color:{color}"' if value else ""
    return f"<b{style}>{_escape(label)} {value}</b>"


# ------------------------------------------------------------------ 공정 카드


def progress_card_markup(
    process: str,
    display_name: str,
    cutoff_days: int | None,
    view: ProgressView,
    months: Sequence[int],
    *,
    today: date,
    outside: bool = False,
) -> str:
    """공정 카드 하나 — 머리에 공정 합계 과거 → 현재와 증감, 호기마다 두 줄.

    `outside` 면 기준선에만 있던 공정이다 — 「지금 범위 밖」 으로 접어 둔다(`<details>`). 제목은
    공정 표시명이고 다르면 풍선에 원본을 남긴다.
    """
    rows = view.rows.loc[view.rows["공정"].eq(process)]
    summary = summarize_progress(rows)
    name = _escape(display_name)
    original = f' title="원본 공정명 {_escape(process)}"' if display_name != process else ""
    cutoff = (
        f'<span class="shk-card-cutoff">Cut-off {cutoff_days}일</span>'
        if cutoff_days is not None
        else ""
    )
    body = _units_markup(rows, months, today=today)
    if outside:
        return (
            f'<details class="shk-prog-out" aria-label="진척 {name}"><summary>'
            f'<span class="shk-card-name"{original}>{name}</span>{cutoff}'
            f"<span>지금 범위 밖 · 기준선 단축 {summary.past_days:,}일 · 호기 {len(rows)}대 — "
            "지금 계획이 맞대지 않는 공정이라 견줄 짝이 없습니다</span></summary>"
            f"{body}</details>"
        )
    change, color = _change_text(summary.change)
    head_sum = (
        f'<span class="shk-prog-head-sum">과거 {summary.past_days:,}일 → '
        f"<b>현재 {summary.current_days:,}일</b>"
        f'<span class="shk-prog-delta" style="color:{color}">{_escape(change)}</span></span>'
    )
    return (
        f'<section class="shk-card shk-prog" aria-label="진척 {name}">'
        '<div class="shk-card-head"><div>'
        f'<span class="shk-card-name"{original}>{name}</span>{cutoff}</div>{head_sum}</div>'
        f"{body}</section>"
    )


def _units_markup(rows: pd.DataFrame, months: Sequence[int], *, today: date) -> str:
    legend = (
        '<div class="shk-units-legend">호기마다 두 줄 — 과거(기준선, 회색) ◀ 필요 시점 ── ○ 확보 '
        "시점 · 현재(진하게) ◀ ━━ ● · ◌ 신규 필요 · 칸은 달 · 점선은 오늘 · 오른쪽은 기존 → 필요 "
        "시점과 단축일수</div>"
    )
    if rows.empty or not months:
        return (
            f'<div class="shk-units">{legend}<div class="shk-empty">'
            "두 시점 모두 이 목표에서 단축할 호기가 없습니다.</div></div>"
        )
    axis = timeline_axis(months)
    lines = timeline_grid_lines(months, axis)
    today_mark = (
        f'<span class="shk-today" title="오늘" '
        f'style="left:{timeline_position(today, axis):.3f}%"></span>'
        if axis[0] <= today < axis[1]
        else ""
    )
    step = max(1, -(-len(months) // _MAX_AXIS_LABELS))
    labels = "".join(
        f'<span style="position:absolute;left:'
        f'{timeline_position(date(m // 100, m % 100, 1), axis):.3f}%;padding-left:3px">'
        f"{month_label(m)}</span>"
        for m in months[::step]
    )
    head = (
        '<div class="shk-prog-unit shk-unit-axis" aria-hidden="true"><span></span><span></span>'
        f'<div class="shk-axis">{labels}</div><span></span></div>'
    )
    units = "".join(
        _unit_markup(
            {str(key): value for key, value in record.items()}, axis, lines + today_mark, today
        )
        for record in rows.to_dict("records")
    )
    width = _NAME_PX + _TAG_PX + _TRACK_MIN_PX + _RESULT_PX + 70
    return (
        f'<div class="shk-units">{legend}<div class="shk-scroll"><div style="min-width:{width}px;'
        f'display:flex;flex-direction:column;gap:4px">{head}{units}</div></div></div>'
    )


def _badge(row: dict[str, object], virtual: bool) -> tuple[str, str]:
    """(배지 글, 색)."""
    status = row["상태"]
    delta = _whole(row["단축일수 증감"]) or 0
    if status == PROGRESS_IMPROVED:
        return f"{abs(delta)}일 줄임", tokens.ACCENT
    if status == PROGRESS_WORSENED:
        return f"{delta}일 늘어남", tokens.DELTA_INCREASE
    if status == PROGRESS_NEW:
        return "신규 필요", tokens.DELTA_INCREASE
    if status == PROGRESS_RESOLVED:
        return ("해소 · 신규 불필요" if virtual else "해소"), tokens.ACCENT
    if status == PROGRESS_KEPT_NEW:
        return "신규 유지", tokens.TEXT_MUTED
    if status == PROGRESS_OUT_OF_SCOPE:
        return "지금 범위 밖", tokens.TEXT_MUTED
    if status == PROGRESS_LAPSED:
        return "필요 시점 지남", tokens.TEXT_MUTED
    assert status == PROGRESS_UNCHANGED, status
    return "변동 없음", tokens.TEXT_MUTED


def _movement(row: dict[str, object]) -> str:
    """「필요 +18일 · 확보 −13일」 — 움직인 시점만. 둘 다 그대로면 빈 글."""
    parts = []
    for label, column in (("필요", "필요 시점 이동(일)"), ("확보", "확보 시점 이동(일)")):
        days = _whole(row[column])
        if days:
            parts.append(f"{label} {_signed_days(days)}")
    return " · ".join(parts)


def _unit_markup(row: dict[str, object], axis: tuple[date, date], lines: str, today: date) -> str:
    virtual = row["구분"] == KIND_NEW
    status = row["상태"]
    badge, badge_color = _badge(row, virtual)
    movement = _movement(row)
    modules = _whole(row["모듈 수"]) or 1
    past_need, past_secure = _day(row["과거 필요 시점"]), _day(row["과거 확보 시점"])
    now_need, now_secure = _day(row["현재 필요 시점"]), _day(row["현재 확보 시점"])
    past_days, now_days = _whole(row["과거 단축일수"]), _whole(row["현재 단축일수"])
    now_color = (
        tokens.DELTA_INCREASE if status in (PROGRESS_WORSENED, PROGRESS_NEW) else tokens.ACCENT
    )
    past_lane = _lane(past_need, past_secure, axis, virtual=virtual, past=True, color="")
    now_lane = _lane(now_need, now_secure, axis, virtual=virtual, past=False, color=now_color)
    if now_need is None:
        gone = (
            "범위 밖"
            if status == PROGRESS_OUT_OF_SCOPE
            else "신규 불필요"
            if virtual
            else "단축 불필요"
        )
        now_text = f'<span style="color:{badge_color}">{gone}</span>'
    else:
        now_text = _lane_text(now_need, now_secure, now_days, virtual=virtual, today=today)
    past_text = (
        "—"
        if past_need is None
        else _lane_text(past_need, past_secure, past_days, virtual=virtual, today=today)
    )
    name = str(row["호기"])
    details = [name, f"상태 {badge}"]
    for tag, need, secure, days in (
        ("과거", past_need, past_secure, past_days),
        ("현재", now_need, now_secure, now_days),
    ):
        details.append(f"{tag} " + _detail(need, secure, days, virtual=virtual))
    if movement:
        details.append(movement)
    if modules > 1:
        details.append(f"모듈 {modules}")
    meta = (
        f'<span class="shk-prog-badge" style="color:{badge_color};border-color:{badge_color}">'
        f"{_escape(badge)}</span>" + (f"<span>{_escape(movement)}</span>" if movement else "")
    )
    return (
        f'<div class="shk-prog-unit" title="{_escape(" · ".join(details))}">'
        f'<div class="shk-prog-label"><span class="shk-unit-name">{_escape(name)}</span>'
        f'<span class="shk-prog-meta">{meta}</span></div>'
        '<div class="shk-prog-tags"><span>과거</span><span class="now">현재</span></div>'
        f'<div class="shk-prog-tracks">{lines}'
        f'<div class="shk-prog-lane">{past_lane}</div>'
        f'<div class="shk-prog-lane">{now_lane}</div></div>'
        f'<div class="shk-prog-results"><span class="past">{past_text}</span>'
        f'<span class="now">{now_text}</span></div></div>'
    )


def _detail(need: date | None, secure: date | None, days: int | None, *, virtual: bool) -> str:
    if need is None:
        return "없음"
    if virtual or secure is None:
        return f"신규 필요 Qual {need:%Y-%m-%d}"
    return f"기존 Qual {secure:%Y-%m-%d} → 목표 Qual {need:%Y-%m-%d} · −{days or 0}일"


def _lane_text(
    need: date, secure: date | None, days: int | None, *, virtual: bool, today: date
) -> str:
    """줄 오른쪽 글 — 「기존 MM.DD → 필요 MM.DD −N일」, 가상 호기는 「필요 MM.DD 신규」."""
    if virtual or secure is None:
        return f"필요 {month_day(need, today=today)} <b>신규</b>"
    return (
        f"{month_day(secure, today=today)} → {month_day(need, today=today)} <b>−{days or 0}일</b>"
    )


def _lane(
    need: date | None,
    secure: date | None,
    axis: tuple[date, date],
    *,
    virtual: bool,
    past: bool,
    color: str,
) -> str:
    """한 줄의 표지. 과거는 회색 가는 선·빈 원, 현재는 굵은 선·찬 원이다. 가상 호기는 ◌ 하나."""
    if need is None:
        return ""
    center = _LANE_CENTER_PX
    left = timeline_position(need, axis)
    muted = tokens.TEXT_MUTED
    if virtual or secure is None:
        border, fill = (muted, tokens.SURFACE) if past else (tokens.TEXT, tokens.STATUS_SHORTAGE)
        return (
            f'<span style="position:absolute;top:{center - 7:g}px;left:calc({left:.3f}% - 7px);'
            f"width:14px;height:14px;border-radius:50%;border:2px dashed {border};"
            f'background:{fill};box-sizing:border-box"></span>'
        )
    right = timeline_position(secure, axis)
    stroke = muted if past else color
    thickness = 2 if past else 3
    dot = (
        f"width:10px;height:10px;top:{center - 5:g}px;left:calc({right:.3f}% - 5px);"
        f"border:2px solid {muted};background:{tokens.SURFACE_SUBTLE}"
        if past
        else f"width:12px;height:12px;top:{center - 6:g}px;left:calc({right:.3f}% - 6px);"
        f"border:2px solid {tokens.SURFACE_SUBTLE};background:{stroke}"
    )
    return (
        f'<span style="position:absolute;top:{center - thickness / 2:g}px;height:{thickness}px;'
        f"border-radius:2px;background:{stroke};left:{left:.3f}%;"
        f'width:{max(right - left, 0):.3f}%"></span>'
        f'<span style="position:absolute;top:{center - 5:g}px;left:calc({left:.3f}% - 2px);'
        "width:0;height:0;border-top:5px solid transparent;border-bottom:5px solid transparent;"
        f'border-right:8px solid {stroke}"></span>'
        f'<span style="position:absolute;border-radius:50%;box-sizing:border-box;{dot}"></span>'
    )
