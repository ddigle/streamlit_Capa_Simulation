# Purpose: 시나리오 관리 「부대공정 얹기」 — 저장 리비전에 활성 부대공정 판을 얹은 결과를 보이고 새
# 시나리오로 저장한다.

"""「부대공정 얹기」(설계 4-8 · D19 (가) — 파생 저장 길).

다음 BDQ 등록을 기다리지 않고 「저장 리비전 + 활성 판 → 새 시나리오」 를 만든다. 바탕은 고른 **저장
리비전**이라 미저장 편집이 섞이지 않는다. 바탕 데이터셋의 출처 표가 가리키는 옛 판 공정을 16표에서
먼저 걷고 활성 판을 합친다(`extra_process_merge.overlay_extra_processes`). 프리셋 포함 공정은 바탕
프리셋에서 걷은 공정을 빼고 새로 합친 부대공정을 더한다 — 바탕에서 끈 공정이 다시 켜지지 않는다.
저장은 연도 Shift · 월 머지와 같은 `render_derived_save` 이고(원본 리비전이 「편집 전」 —
`derived_save_verdict`), 새 데이터셋에 새 판의 출처 줄을 남긴다(D18).

합치기는 대당 Capa → 확보율까지 돌리는 등록 점검(R-07)을 품어 몇 초가 걸릴 수 있다. 그래서 (바탕
리비전, 판 차례)마다 한 번만 돌리고 결과를 세션 메모(`OVERLAY_MEMO_KEY`)에 둔다 — 메모 이름이
`PAGE_DIALOG_SUFFIX` 로 끝나 페이지를 떠나면 버린다. 활성 판이 없으면 이 작업은 목록에 서지
않는다(`scenario_management` — 설계 규칙 UI-TXT-08).
"""

from __future__ import annotations

from typing import Final

import pandas as pd
import streamlit as st

from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.scenario_management_tabs import CAPA_SCENARIO_TAB_NAME
from capa_simulation.components.scenario_transform import (
    render_derived_save,
    render_source_selector,
    source_description,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PAGE_DIALOG_SUFFIX,
    bootstrap_error_message,
)
from capa_simulation.persistence.models import ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_registration import load_active_extra_pack, provenance_records
from capa_simulation.services.extra_process_merge import (
    OUTCOME_DROPPED,
    OUTCOME_GRADUATED,
    OUTCOME_MERGED,
    ActiveExtraPack,
    MergeResult,
    overlay_extra_processes,
    overlay_included_processes,
)
from capa_simulation.services.scenario_transform import copy_scenario_tables
from capa_simulation.services.scenario_virtual_products import virtual_product_records

EXTRA_OVERLAY_MODE: Final = "부대공정 얹기"
# 바탕 리비전을 고르는 상자의 역할(`render_source_selector` 의 `key` — 원본 메모의 칸 이름).
EXTRA_SOURCE_ROLES: Final = ("extra_source",)
OVERLAY_OPERATION: Final = "SCENARIO_EXTRA_PROCESS"
OVERLAY_KEY: Final = "scenario_extra"
# (DB 경로, 바탕 리비전 id, 판 차례) → 합친 결과 · 걷은 공정. 페이지를 떠나면 버린다.
OVERLAY_MEMO_KEY: Final = f"scenario_extra_overlay{PAGE_DIALOG_SUFFIX}"
OUTCOME_LABELS: Final = {
    OUTCOME_MERGED: "합침",
    OUTCOME_DROPPED: "뺌",
    OUTCOME_GRADUATED: "BDQ 에 생김",
}
RESULT_TITLE: Final = "부대공정 판 {version} · {counts}"
STRIPPED_LINE: Final = "걷은 옛 판 공정 {count}개"


def forget_extra_overlay() -> None:
    """메모한 합친 결과를 버린다 — 다른 작업으로 옮길 때."""
    st.session_state.pop(OVERLAY_MEMO_KEY, None)


def render_scenario_extra_overlay(repository: DuckDBScenarioRepository, database_path: str) -> None:
    # 구획 이름은 바로 위 전환 단추가 말한다(설계 규칙 UI-TXT-07). 무엇을 걷고 합치는지는 Guide 가
    # 말한다(UI-TXT-01 · UI-TXT-02).
    try:
        _render(repository, database_path)
    except BOOTSTRAP_ERRORS as exc:
        render_data_error(
            bootstrap_error_message(exc),
            code="SC-02",
            tab=CAPA_SCENARIO_TAB_NAME,
            text="부대공정 얹기를 그리지 못했습니다",
        )


def _render(repository: DuckDBScenarioRepository, database_path: str) -> None:
    active = load_active_extra_pack(repository)
    if active is None:
        return
    source = render_source_selector(
        repository, database_path, label="바탕", key=EXTRA_SOURCE_ROLES[0]
    )
    if source is None:
        return
    previous = _previous_extra_processes(repository, source)
    with st.spinner("부대공정 판을 얹고 계산을 점검하는 중입니다..."):
        result = _overlay(database_path, source, previous, active)
    report = result.report
    st.caption(
        RESULT_TITLE.format(version=active.version.version_no, counts=report.counts_text())
        + (f" · {STRIPPED_LINE.format(count=len(previous))}" if previous else "")
    )
    st.dataframe(_outcome_frame(result), hide_index=True, width="stretch")
    if not report.merged:
        return
    virtual_products = virtual_product_records(
        repository.list_virtual_products(source.revision.revision_id)
    )
    render_derived_save(
        repository,
        tables=result.tables,
        source=source,
        operation=OVERLAY_OPERATION,
        provenance=_provenance_text(source, active, result, len(previous)),
        default_name=f"{source.scenario.scenario_name} · 부대공정 판 {active.version.version_no}",
        key=OVERLAY_KEY,
        request=(source.revision.revision_id, f"extra-{active.version.seq}"),
        virtual_products=virtual_products,
        extra_process=provenance_records(report),
        included_processes=overlay_included_processes(
            source.preset.included_processes, previous, report
        ),
        extra_report=report,
    )


def _previous_extra_processes(
    repository: DuckDBScenarioRepository, source: ScenarioSnapshot
) -> tuple[str, ...]:
    """바탕 데이터셋에 이미 합쳐진 옛 판 공정 — 출처 표가 없는 바탕(구현 전)은 빈 묶음이다."""
    records = repository.load_scenario_extra_process(source.scenario.scenario_id)
    return tuple(
        dict.fromkeys(record.process_name for record in records if record.outcome == OUTCOME_MERGED)
    )


def _overlay(
    database_path: str,
    source: ScenarioSnapshot,
    previous: tuple[str, ...],
    active: ActiveExtraPack,
) -> MergeResult:
    memo_key = (database_path, source.revision.revision_id, active.version.seq)
    memo = st.session_state.get(OVERLAY_MEMO_KEY)
    if isinstance(memo, tuple) and len(memo) == 2 and memo[0] == memo_key:
        cached = memo[1]
        if isinstance(cached, MergeResult):
            return cached
    result = overlay_extra_processes(copy_scenario_tables(source.tables), previous, active)
    st.session_state[OVERLAY_MEMO_KEY] = (memo_key, result)
    return result


def _outcome_frame(result: MergeResult) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "공정": item.process,
                "결과": OUTCOME_LABELS.get(item.outcome, item.outcome),
                "규칙": item.rule or "",
                "까닭": item.reason,
                "경로": item.route_rows,
                "맞물리지 않은 경로 줄": item.zero_lines,
            }
            for item in result.report.outcomes
        ],
        columns=["공정", "결과", "규칙", "까닭", "경로", "맞물리지 않은 경로 줄"],
    )


def _provenance_text(
    source: ScenarioSnapshot, active: ActiveExtraPack, result: MergeResult, stripped: int
) -> str:
    """새 시나리오 리비전 메모의 출처 — 개수와 판만(공정 이름 · 값은 싣지 않는다)."""
    return (
        f"부대공정 얹기\n바탕: {source_description(source)}\n"
        f"부대공정 판 {active.version.version_no} (sha {active.version.sha256[:8]})\n"
        f"걷은 옛 판 공정: {stripped}개\n"
        f"{result.report.memo()}"
    )
