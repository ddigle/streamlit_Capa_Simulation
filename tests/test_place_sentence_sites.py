# Purpose: 화면 글(st.caption · st.info · st.markdown)의 서술형 문장 자리를 세어 허용 목록과 맞댄다.

"""화면 글 문장 그물(설계 규칙 UI-TXT-01 · 03 · 04 · 08, UI-NTF-02 — `docs/design_rules.md` 5-1).

화면 자리에 늘 두는 글은 값 · 표지뿐이고(UI-TXT-04), 설명 · 내역 · 길 안내 문장은 풍선
(`help=`) · Guide · 알림창으로 옮긴다(UI-TXT-01 · 02 · 03, UI-NTF-02 — 2026-11-04 설계 규칙 확인
보드 AMB-01 · AMB-02 (가) · AMB-06 (나)). 이 그물은 화면 코드(`app.py` · `app_pages/` ·
`src/capa_simulation/`)에서 `st.caption` · `st.info` · `st.markdown`(칸 · 사이드바 · 팝업의 같은
이름 부름 포함, 로거 밖)과 `st.write` · `st.text` · `st.html`(문자열 인자)에 넣는 글이 **서술형으로
끝나는**(「…니다」 · 「…세요」 · 「…다」 등)
부름을 (파일, 맨 바깥 함수 — 모듈 본문은 "") 마다 세어 허용 목록과 **정확히** 맞댄다
(`tests/test_alert_sites.py` 의 꼴). 글은 상수 · f-string · 이은 글 · 같은 함수의 지역 이름 · 모듈
상수 · 들여온 상수 · 글을 돌려주는 함수까지 푼다(`tests/source_sites.py`).

- 새 자리가 생기면 실패한다 — 설명 · 내역 · 길 안내면 옮기고(풍선 · Guide · `alerts.state` ·
  `flash.queue_flash`), 자리에 남을 글이면 `ALLOWED` 에 까닭과 함께 둔다. 까닭은 값 · 표지 · 빈
  결과 · 입력 곁 거부 · 미정리 가운데 하나다(`source_sites.PLACE_REASONS` — 데이터 때문에 못 그린
  자리는 글이 아니라 마크다).
- 자리가 줄면 실패한다 — 목록의 그 칸도 줄인다(옮긴 자리가 남아 다른 새 자리를 덮지 않게).
- 미정리(`UNSETTLED`)는 이 그물을 세울 때(2026-11-04) 이미 있던 설명 · 내역 · 길 안내 자리다 —
  새 자리에 쓰지 않는다. 미정리 수가 `UNSETTLED_SITES` 와 다르면 실패한다(늘면 옮기고, 줄면 수도
  줄인다).
- 문장으로 끝나지 않는 값 줄(「**라벨** · 값」), 매개변수로 받은 글, 풍선(`help=`)은 그물 밖이다.

까닭 칸은 부름 하나에 하나이고 함수 안 문서 차례다 — 한 함수에 갈래가 섞일 수 있다. 차례로 짝지은
부름과 까닭은 꼴도 맞댄다 — 값 · 표지 · 빈 결과 자리는 평문(`st.caption` · `st.markdown` ·
`st.write` · `st.text`)이고 파란 상자(`st.info`)가 아니다(UI-TXT-04 — 빈 결과는 평문 한 줄), 빈 결과
자리의 끝 글은 결론 꼴(「…없습니다」 · 「…같습니다」 등 — `EMPTY_ENDING`)이며, 세 갈래 모두 하는
법 · 길 안내 꼬리(「…세요」 · 「…에서 정합니다」 — `GUIDANCE_ENDING`)로 끝나지 않는다. 그래서 허용된
자리의 글을 상자 · 비결론 꼴(빈 결과 자리) · 길 안내 꼬리로 바꿔 넣으면 수가 같아도 실패한다. 그
밖의 설명 문장으로 바꾸는 것(값 · 표지 자리에 「…쌓이며 지울 수 없습니다」 처럼)은 이 그물이 잡지
않는다 — 수와 꼴만 맞대므로 글 뜻은 판단 질문(UI-TXT-04 「이 글은 값인가, 설명인가?」)이 본다.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

from source_sites import (
    BESIDE_INPUT,
    EMPTY,
    LOGGERS,
    MARKER,
    PLACE_REASONS,
    PROJECT_ROOT,
    UNSETTLED,
    VALUE,
    TextResolver,
    bare_tail,
    ends_as_sentence,
    first_text_argument,
    method,
    receiver,
    screen_calls,
    screen_files,
)

# 자리 글을 그리는 부름 — 상자(`st.info`)와 평문(`st.caption` · `st.markdown` · `st.write` ·
# `st.text` · `st.html`).
TEXT_METHODS = frozenset({"caption", "info", "markdown", "write", "text", "html"})
# 값 · 표지 · 빈 결과가 설 수 있는 꼴 — 평문 부름(상자 `st.info` 는 아니다).
PLAIN_METHODS = frozenset({"caption", "markdown", "write", "text"})
# 빈 결과 · 점검 결론의 끝 — 「…없습니다」 · 「…않습니다」 · 「…같습니다」 · 「…마쳤습니다」 ·
# 「…채워졌습니다」 · 「… 0 입니다」(끝 꾸밈은 걷고 본다).
EMPTY_ENDING = re.compile(r"(?:없습니다|않습니다|같습니다|마쳤습니다|채워졌습니다|0 입니다)[.!…]*$")
# 하는 법 · 길 안내 꼬리 — 값 · 표지 · 빈 결과 자리 글은 이렇게 끝나지 않는다(UI-TXT-03 · AMB-02
# (가)).
GUIDANCE_ENDING = re.compile(r"(?:세요|십시오|(?:정합|고칩|바꿉|입력합|켭|엽|누릅|봅)니다)[.!…]*$")
# 미정리 자리 수. 늘지 않는다 — 줄면 이 수도 줄인다.
UNSETTLED_SITES = 14

# (파일, 맨 바깥 함수) → 서술형 문장 부름마다 까닭(문서 차례).
ALLOWED: dict[tuple[str, str], tuple[str, ...]] = {
    # 사이드바 조건 패널 맨 위 「적용 전 편집 … — 시나리오·기간을 바꾸면 사라집니다」 — 바로 밑
    # 시나리오 · 기간 칸을 바꾸기 전에 알아야 하는 되돌릴 수 없는 결과다(UI-NTF-09).
    ("app.py", ""): (BESIDE_INPUT,),
    ("app_pages/admin_area.py", ""): (EMPTY,),
    ("app_pages/available_equipment_status.py", ""): (EMPTY,),
    ("app_pages/calculation_result.py", ""): (EMPTY,),
    ("app_pages/capa_chatbot.py", ""): (UNSETTLED, UNSETTLED),
    ("app_pages/constraint_simulation.py", ""): (
        BESIDE_INPUT,
        MARKER,
        EMPTY,
        EMPTY,
        EMPTY,
    ),
    ("app_pages/constraint_simulation.py", "product_ready"): (EMPTY,),
    ("app_pages/constraint_simulation.py", "render_held_picker"): (BESIDE_INPUT,),
    ("app_pages/internal_modules.py", ""): (EMPTY,),
    ("app_pages/load_conversion.py", "_virtual_product_dialog"): (EMPTY,),
    ("app_pages/process_capa_detail.py", ""): (EMPTY,),
    ("app_pages/reference_data.py", ""): (EMPTY,),
    ("app_pages/reference_data.py", "_render_step_view"): (EMPTY,),
    ("app_pages/reference_integrity.py", "_render_detail"): (EMPTY,),
    ("app_pages/reference_integrity.py", "_render_guide"): (
        UNSETTLED,
        UNSETTLED,
        UNSETTLED,
        UNSETTLED,
        UNSETTLED,
    ),
    ("app_pages/reference_integrity.py", "_render_pending_screen"): (UNSETTLED,),
    ("app_pages/reference_integrity.py", "_render_summary"): (EMPTY,),
    ("app_pages/required_shortening.py", ""): (EMPTY,),
    ("app_pages/space_status.py", "_render_unsaved_layout_panel"): (BESIDE_INPUT,),
    ("app_pages/standard_target_capa.py", ""): (BESIDE_INPUT, BESIDE_INPUT, EMPTY),
    ("app_pages/standard_target_capa.py", "_render_logic_analysis"): (EMPTY,),
    ("app_pages/static_capa.py", ""): (EMPTY, EMPTY),
    ("app_pages/voc.py", ""): (EMPTY, EMPTY),
    ("app_pages/wip_status.py", ""): (EMPTY, EMPTY, EMPTY, UNSETTLED),
    ("src/capa_simulation/components/alert_board.py", "render_alert_board"): (EMPTY,),
    ("src/capa_simulation/components/auto_official_update_tab.py", "_render_run_history"): (
        EMPTY,
        EMPTY,
    ),
    ("src/capa_simulation/components/auto_official_update_tab.py", "_render_setting_history"): (
        EMPTY,
    ),
    ("src/capa_simulation/components/auto_official_update_tab.py", "_render_settings_form"): (
        BESIDE_INPUT,
    ),
    ("src/capa_simulation/components/auto_official_update_tab.py", "_render_status"): (VALUE,),
    ("src/capa_simulation/components/availability_gap_panel.py", "_render_evidence"): (EMPTY,),
    # 짝 칸 이름 줄(「아래는 짝 칸 「…」의 호기입니다」 — 밑 표가 무엇인지)은 값이다. 부호의 뜻은
    # GAP 식 줄의 풍선(`GAP_SIGN_HELP`)이라 자리 글이 아니다(UI-TXT-01 · UI-TXT-02).
    ("src/capa_simulation/components/availability_gap_panel.py", "_render_gap_evidence"): (VALUE,),
    ("src/capa_simulation/components/availability_gap_panel.py", "_render_schedule_evidence"): (
        EMPTY,
    ),
    (
        "src/capa_simulation/components/availability_gap_panel.py",
        "_render_securement_cross_check",
    ): (EMPTY, EMPTY, EMPTY, EMPTY),
    ("src/capa_simulation/components/availability_gap_panel.py", "_render_unit_list"): (EMPTY,),
    ("src/capa_simulation/components/availability_gap_panel.py", "render_availability_gap_panel"): (
        EMPTY,
        EMPTY,
        EMPTY,
        EMPTY,
        EMPTY,
        MARKER,
        MARKER,
        EMPTY,
    ),
    ("src/capa_simulation/components/bigdataquery_registration.py", "_render_catalog_list"): (
        EMPTY,
        EMPTY,
        EMPTY,
    ),
    ("src/capa_simulation/components/constraint_simulation_view.py", "_render_schedule"): (
        EMPTY,
        EMPTY,
    ),
    ("src/capa_simulation/components/container_start_check.py", "render_container_start_check"): (
        VALUE,
    ),
    ("src/capa_simulation/components/cutoff_management.py", "render_cutoff_management"): (EMPTY,),
    ("src/capa_simulation/components/display_order_management.py", "_render_direct_editor"): (
        BESIDE_INPUT,
    ),
    ("src/capa_simulation/components/equipment_data_workspace.py", "_render_bulk_delete_status"): (
        BESIDE_INPUT,
    ),
    ("src/capa_simulation/components/equipment_data_workspace.py", "_render_history"): (
        EMPTY,
        EMPTY,
        EMPTY,
    ),
    ("src/capa_simulation/components/equipment_explorer.py", "_availability"): (EMPTY,),
    ("src/capa_simulation/components/equipment_explorer.py", "_render_result"): (EMPTY, EMPTY),
    ("src/capa_simulation/components/equipment_explorer.py", "_transitions"): (EMPTY,),
    (
        "src/capa_simulation/components/equipment_lifecycle_gantt.py",
        "render_equipment_lifecycle_gantt",
    ): (EMPTY,),
    ("src/capa_simulation/components/equipment_master_tab.py", "_render_notices"): (BESIDE_INPUT,),
    ("src/capa_simulation/components/equipment_master_tab.py", "_render_save_section"): (
        BESIDE_INPUT,
    ),
    # 옛 배포 흔적으로 막힌 쓰기 팝오버의 잠금 까닭 한 줄(`legacy_trace_lock_line`) — 푸는 길은 구획
    # 맨 위 옛 배포 흔적 칸 · 알림 · Guide 가 말한다(UI-TXT-03).
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_clear_layout"): (
        BESIDE_INPUT,
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_legacy_trace"): (
        BESIDE_INPUT,
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_load"): (
        BESIDE_INPUT,
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_restore"): (
        EMPTY,
        BESIDE_INPUT,
        EMPTY,
    ),
    (
        "src/capa_simulation/components/equipment_scenario_management.py",
        "render_equipment_scenario_management",
    ): (EMPTY, EMPTY),
    ("src/capa_simulation/components/equipment_scenario_status.py", "_render_dialog_body"): (
        EMPTY,
    ),
    ("src/capa_simulation/components/equipment_scenario_status.py", "_render_load"): (
        BESIDE_INPUT,
        EMPTY,
    ),
    ("src/capa_simulation/components/equipment_scenario_status.py", "_render_save"): (
        EMPTY,
        EMPTY,
    ),
    ("src/capa_simulation/components/grouped_monthly_table.py", "render_grouped_monthly_table"): (
        EMPTY,
        EMPTY,
    ),
    (
        "src/capa_simulation/components/hierarchical_monthly_table.py",
        "render_hierarchical_monthly_table",
    ): (EMPTY, EMPTY),
    ("src/capa_simulation/components/home_main_cases.py", "_render_case"): (EMPTY,),
    ("src/capa_simulation/components/home_preference.py", "_render_comparison_picker"): (
        EMPTY,
        EMPTY,
    ),
    ("src/capa_simulation/components/home_preference.py", "_render_execution_editor"): (
        EMPTY,
        BESIDE_INPUT,
    ),
    ("src/capa_simulation/components/home_preference.py", "_render_monthly_amount_editor"): (
        EMPTY,
    ),
    ("src/capa_simulation/components/home_preference.py", "_render_summary_note_editor"): (
        BESIDE_INPUT,
    ),
    ("src/capa_simulation/components/home_preference.py", "_render_top5_band_editor"): (
        BESIDE_INPUT,
    ),
    ("src/capa_simulation/components/home_preference.py", "render_threshold_editor"): (
        EMPTY,
        BESIDE_INPUT,
    ),
    ("src/capa_simulation/components/manual_downtime_tab.py", "_render_editor"): (BESIDE_INPUT,),
    ("src/capa_simulation/components/manual_downtime_tab.py", "_render_history"): (EMPTY,),
    ("src/capa_simulation/components/manual_downtime_tab.py", "render_manual_downtime_tab"): (
        EMPTY,
    ),
    ("src/capa_simulation/components/modification_schedule_view.py", "_render_body"): (EMPTY,),
    ("src/capa_simulation/components/modification_schedule_view.py", "_render_conditions"): (
        MARKER,
    ),
    ("src/capa_simulation/components/modification_schedule_view.py", "render_schedule_mode"): (
        EMPTY,
    ),
    ("src/capa_simulation/components/performance_actual_screen.py", "_render_actions"): (EMPTY,),
    ("src/capa_simulation/components/performance_actual_screen.py", "_render_detail"): (EMPTY,),
    ("src/capa_simulation/components/performance_actual_screen.py", "_render_summary"): (EMPTY,),
    (
        "src/capa_simulation/components/plan_comparison_dumbbell.py",
        "render_plan_comparison_dumbbell",
    ): (EMPTY,),
    ("src/capa_simulation/components/process_capa_view.py", "_render_route_factors"): (EMPTY,),
    ("src/capa_simulation/components/process_picker.py", "render_process_picker"): (EMPTY,),
    ("src/capa_simulation/components/process_rename_management.py", "_render_direct_editor"): (
        BESIDE_INPUT,
    ),
    ("src/capa_simulation/components/qual_deadline_calculator.py", "_render_inputs"): (MARKER,),
    ("src/capa_simulation/components/qual_deadline_calculator.py", "_render_results"): (EMPTY,),
    ("src/capa_simulation/components/required_shortening_panel.py", "_render_body"): (
        EMPTY,
        EMPTY,
    ),
    ("src/capa_simulation/components/required_shortening_panel.py", "_render_month_range"): (
        BESIDE_INPUT,
    ),
    ("src/capa_simulation/components/required_shortening_panel.py", "_render_progress"): (EMPTY,),
    ("src/capa_simulation/components/scenario_management.py", "_render_archived_scenarios"): (
        EMPTY,
    ),
    ("src/capa_simulation/components/scenario_management.py", "_render_list_management"): (EMPTY,),
    ("src/capa_simulation/components/scenario_management.py", "_render_official_history"): (
        EMPTY,
        VALUE,
    ),
    ("src/capa_simulation/components/scenario_management.py", "_render_detail"): (EMPTY,),
    ("src/capa_simulation/components/scenario_status.py", "_render_dialog_body"): (EMPTY,),
    ("src/capa_simulation/components/scenario_status.py", "_render_dialog_header"): (EMPTY,),
    ("src/capa_simulation/components/scenario_status.py", "_render_load"): (BESIDE_INPUT, EMPTY),
    ("src/capa_simulation/components/scenario_status.py", "_render_revision_save"): (
        BESIDE_INPUT,
        BESIDE_INPUT,
    ),
    ("src/capa_simulation/components/scenario_transform.py", "render_source_selector"): (EMPTY,),
    ("src/capa_simulation/components/securement_heatmap.py", "render_securement_heatmap"): (EMPTY,),
    ("src/capa_simulation/components/shortening_board.py", "_render_delayed"): (EMPTY,),
    ("src/capa_simulation/components/shortening_board.py", "_render_imminent"): (EMPTY,),
    ("src/capa_simulation/components/shortening_board.py", "render_highlight_notice"): (EMPTY,),
    ("src/capa_simulation/components/shortening_progress_panel.py", "_render_delete"): (
        BESIDE_INPUT,
    ),
    ("src/capa_simulation/components/source_quality.py", "render_source_quality"): (
        EMPTY,
        EMPTY,
    ),
    ("src/capa_simulation/components/space_floor_list.py", "_render_confirm"): (BESIDE_INPUT,),
    ("src/capa_simulation/components/space_shortening_view.py", "render_floor_layer_panel"): (
        EMPTY,
    ),
    # 명단이 비었을 때의 빈 결과 한 줄.
    ("src/capa_simulation/components/access_list_admin.py", "_render_people"): (EMPTY,),
    ("src/capa_simulation/components/sso_status.py", "render_sso_status"): (
        UNSETTLED,
        UNSETTLED,
        UNSETTLED,
        UNSETTLED,
        UNSETTLED,
    ),
    ("src/capa_simulation/components/table_view_controls.py", "render_table_view_controls"): (
        BESIDE_INPUT,
    ),
    (
        "src/capa_simulation/components/upeh_assumption_controls.py",
        "render_upeh_assumption_controls",
    ): (EMPTY, BESIDE_INPUT),
}


class SentenceCall(NamedTuple):
    """서술형 문장으로 끝나는 자리 글 부름 하나 — 줄 번호, 부른 이름, 끝 글(들)."""

    line: int
    method: str
    tails: tuple[str, ...]


def place_sentence_calls(
    paths: list[Path] | None = None, root: Path = PROJECT_ROOT
) -> dict[tuple[str, str], list[SentenceCall]]:
    """(파일, 맨 바깥 함수) 마다 서술형 문장으로 끝나는 자리 글 부름(문서 차례)."""
    resolver = TextResolver()
    found: dict[tuple[str, str], list[SentenceCall]] = {}
    for relative, outer, path, scope, call in screen_calls(paths or screen_files(), root):
        if method(call) not in TEXT_METHODS or receiver(call) in LOGGERS:
            continue
        argument = first_text_argument(call)
        if argument is None:
            continue
        tails = resolver.tails(argument, path, scope)
        known = tuple(tail for tail in tails if tail is not None)
        if any(ends_as_sentence(tail) for tail in known):
            found.setdefault((relative, outer), []).append(
                SentenceCall(call.lineno, method(call), known)
            )
    return found


def place_sentences(
    paths: list[Path] | None = None, root: Path = PROJECT_ROOT
) -> dict[tuple[str, str], list[int]]:
    """(파일, 맨 바깥 함수) 마다 서술형 문장으로 끝나는 자리 글 부름의 줄 번호(문서 차례)."""
    return {
        site: [call.line for call in calls]
        for site, calls in place_sentence_calls(paths, root).items()
    }


def _listing(sites: Mapping[tuple[str, str], object]) -> str:
    return "\n".join(f"{file} {func or '(본문)'}: {value}" for (file, func), value in sites.items())


def test_no_new_place_draws_a_sentence() -> None:
    """새 문장 자리는 옮기거나(풍선 · Guide · 알림), 자리에 남을 글이면 까닭과 함께 목록에 둔다."""
    found = place_sentences()
    new = {site: lines for site, lines in found.items() if len(lines) > len(ALLOWED.get(site, ()))}
    assert not new, (
        "자리에 서술형 문장을 늘 두는 새 자리입니다(줄 번호) — 설명 · 내역 · 길 안내면"
        " 풍선(help=) · Guide · 알림(alerts.state · flash.queue_flash)으로 옮기고, 데이터 때문에 못"
        " 그린 자리면 render_data_error 로, 값 · 표지 · 빈 결과 · 입력 곁 거부면"
        " tests/test_place_sentence_sites.py ALLOWED 에 까닭과 함께 두세요(미정리는 새로 쓰지"
        " 않습니다):\n" + _listing(new)
    )


def test_every_allowed_site_is_still_there_with_its_count() -> None:
    """옮긴 자리는 목록에서도 지운다 — 남은 칸이 다른 새 자리를 덮지 않게."""
    found = place_sentences()
    stale = {
        site: (len(reasons), len(found.get(site, [])))
        for site, reasons in ALLOWED.items()
        if len(found.get(site, [])) != len(reasons)
    }
    assert not stale, "허용 목록 수가 코드와 다릅니다(목록 수, 지금 수):\n" + _listing(stale)


def test_every_allowed_site_says_why() -> None:
    unknown = {
        site: reasons
        for site, reasons in ALLOWED.items()
        if not reasons or not set(reasons) <= PLACE_REASONS
    }
    assert not unknown, unknown


def _shape_problems(
    found: Mapping[tuple[str, str], list[SentenceCall]],
    allowed: Mapping[tuple[str, str], tuple[str, ...]],
) -> list[str]:
    """차례로 짝지은 (부름, 까닭)이 그 까닭의 꼴을 어기는 자리(모듈 설명)."""
    problems: list[str] = []
    for site, reasons in allowed.items():
        for call, reason in zip(found.get(site, []), reasons, strict=False):
            where = f"{site[0]}:{call.line} {site[1] or '(본문)'}"
            ending = [bare_tail(tail) for tail in call.tails if ends_as_sentence(tail)]
            if reason in (VALUE, MARKER, EMPTY) and call.method not in PLAIN_METHODS:
                problems.append(f"{where} — {call.method} 상자(평문 한 줄로)")
            if reason == EMPTY and not all(EMPTY_ENDING.search(tail) for tail in ending):
                problems.append(f"{where} — 빈 결과 · 결론 꼴이 아님: {ending}")
            if reason in (VALUE, MARKER, EMPTY) and any(
                GUIDANCE_ENDING.search(tail) for tail in ending
            ):
                problems.append(f"{where} — 하는 법 · 길 안내 꼬리: {ending}")
    return problems


def test_value_marker_and_empty_sites_are_plain_lines_without_guidance() -> None:
    """값 · 표지 · 빈 결과 자리는 평문 한 줄이고(상자 아님), 빈 결과는 결론 꼴로 끝나며, 하는 법 ·
    길 안내 꼬리를 달지 않는다 — 허용된 자리 글을 상자 · 비결론 꼴 · 길 안내 꼬리로 바꿔 넣으면 수가
    같아도 걸린다(다른 설명 문장으로 바꾸는 것은 판단 질문이 본다 — 모듈 설명)."""
    problems = _shape_problems(place_sentence_calls(), ALLOWED)
    assert not problems, "자리 글 까닭과 꼴이 맞지 않습니다:\n" + "\n".join(problems)


def test_unsettled_sites_do_not_grow() -> None:
    """미정리는 줄기만 한다 — 새 자리를 미정리로 들이지 않는다."""
    counted = Counter(reason for reasons in ALLOWED.values() for reason in reasons)
    assert counted[UNSETTLED] == UNSETTLED_SITES, (
        f"미정리 자리가 {counted[UNSETTLED]}곳입니다(기록 {UNSETTLED_SITES}) — 늘었으면 그 자리"
        " 글을 옮기고, 줄었으면 UNSETTLED_SITES 도 줄이세요."
    )


SAMPLE_PAGE = """
import logging

import streamlit as st

from capa_simulation.page_bootstrap import NO_DEMAND_MESSAGE

logger = logging.getLogger(__name__)
HOW_TO = "표를 고르면 근거가 여기에 뜹니다."


def _dropped_line(count: int) -> str:
    return f"호기 {count}대를 뺐습니다."


def render(count: int, label: str) -> None:
    st.caption("판정 기준은 HOME 설정에서 정합니다.")
    st.info(f"{count}건을 저장했습니다.")
    st.markdown(HOW_TO)
    st.sidebar.caption(NO_DEMAND_MESSAGE)
    note = _dropped_line(count)
    st.caption(note)
    st.markdown("<div>표가 <b>비었습니다.</b></div>", unsafe_allow_html=True)
    st.caption("저장 뒤 확인하세요" if count else "없음")
    st.caption(f"**공정** · {label}")
    st.caption(label)
    st.info("확인 필요")
    st.caption("필요 단축 일정", help="고칠 곳은 Guide 가 말합니다.")
    logger.info("저장했습니다.")
"""


def test_the_net_reads_sentences_through_names_helpers_and_markup(tmp_path: Path) -> None:
    """상수 · f-string · 모듈 상수 · 들여온 상수 · 지역 이름 → 글을 돌려주는 함수 · HTML 꼬리표 ·
    갈래 글의 문장은 세고, 값 줄 · 매개변수 · 낱말 표지 · 풍선 · 로거는 세지 않는다."""
    page = tmp_path / "page.py"
    page.write_text(SAMPLE_PAGE, encoding="utf-8")

    found = place_sentences([page], tmp_path)

    assert {site: len(lines) for site, lines in found.items()} == {("page.py", "render"): 7}


SHAPE_PAGE = """
import streamlit as st


def render(count: int) -> None:
    st.caption("저장된 시나리오가 없습니다.")
    st.info("선택한 시나리오에 저장된 리비전이 없습니다.")
    st.caption("판정 기준은 HOME 설정 → 판정 기준 탭에서 정합니다.")
    st.write("지금 올라와 있는 저장 리비전이 없습니다.")
    st.text("저장하지 않고 닫으면 고친 칸은 사라집니다.")
    st.caption("등록된 호기가 없습니다. 샘플 데이터를 켜세요.")
"""


def test_the_shape_check_catches_boxes_guidance_and_non_conclusions(tmp_path: Path) -> None:
    """빈 결과 까닭을 든 자리가 상자(`st.info`)이거나, 결론 꼴이 아니거나, 길 안내 꼬리를 달면
    걸리고, `st.write` · `st.text` 의 문장도 센다."""
    page = tmp_path / "page.py"
    page.write_text(SHAPE_PAGE, encoding="utf-8")

    found = place_sentence_calls([page], tmp_path)
    site = ("page.py", "render")
    assert [call.method for call in found[site]] == [
        "caption",
        "info",
        "caption",
        "write",
        "text",
        "caption",
    ]

    problems = _shape_problems(found, {site: (EMPTY, EMPTY, EMPTY, EMPTY, UNSETTLED, EMPTY)})

    assert [problem.split(" — ")[0] for problem in problems] == [
        "page.py:7 render",
        "page.py:8 render",
        "page.py:8 render",
        "page.py:11 render",
        "page.py:11 render",
    ]
