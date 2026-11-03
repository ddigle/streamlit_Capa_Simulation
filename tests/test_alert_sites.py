# Purpose: 상태 경고를 자리에 직접 그리는 자리(`.warning(`)를 AST 로 세어 허용 목록(까닭 · 수)과
# 맞댄다.

"""상태 알림 그물(2026-11-03 결정 보드 D2 (나) — 알림 체계 1단계).

상태 알림(조건이 남아 있는 동안 회차마다 다시 그리던 경고)은 자리에 그리지 않고 `alerts.state(...)`
로 낸다 — 지문이 바뀔 때만 알림창에 뜨고 Alarm 에 쌓인다(`capa_simulation/alerts.py` 모듈 설명). 이
그물은 화면 코드(`app.py` · `app_pages/` · `src/capa_simulation/`, `flash.py` · `alerts.py` 밖)에서
경고 상자를 직접 그리는 호출(`st.warning(` · 칸`.warning(` — 로거의 `warning` 은 뺀다)을 (파일, 맨
바깥 함수 — 모듈 본문은 "") 마다 세어 허용 목록과 **정확히** 맞댄다.

- 새 자리가 생기면 실패한다 — 상태 알림이면 `alerts.state(...)` 로, 동작 결과면
  `flash.queue_flash(…, kind= "warning")`(버튼 곁에도 남는다), 자리 글(팝업 · 폼 안 검증 · 잠금 까닭
  · 멈춤 화면)이면 이 목록에 까닭과 함께 둔다.
- 자리가 줄면 실패한다 — 목록의 수도 줄인다(옮긴 자리가 목록에 남아 다른 새 자리를 덮지 않게).
- 남은 자리는 모두 자리 글이다(2단계 a · b 가 상태 경고를 `alerts.state` 로 옮긴 뒤). 까닭은 아래
  `PLACE_*` 가운데 하나여야 한다(`REASONS`).

오류(`st.error`)와 안내(`st.info`)는 이 그물 밖이다 — 오류는 버튼 곁 실패 · 화면을 못 그리는 오류라
자리에 남고(D3 · 설계 2-2), 안내는 대개 자리 글이다. 2단계는 상태 알림 후보를 옮길 때 같은 자리의
오류 · 안내도 함께 보았다.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 경고를 직접 그려도 되는 두 모듈 — 알림의 한 길이다.
OWNERS = ("src/capa_simulation/components/flash.py", "src/capa_simulation/alerts.py")
_LOGGERS = frozenset({"logger", "logging", "log", "LOGGER", "_LOG", "_LOGGER", "warnings"})

PLACE_FORM = "자리 글 — 팝업 · 폼 안 검증. 고칠 입력이 그 자리에 있다(알림창 · 기록 없음, 설계 2-2)"
PLACE_BOARD = (
    "자리 글 — Admin 「알림 모음」 판. 알림을 한곳에 모아 보이는 것이 그 화면 자체다(시나리오 전체"
    " 기간으로 다시 계산한 목록 — 쌓이는 기록이 아니다)"
)
PLACE_STOP = (
    "멈춤 화면 — 앱이 서지 못해 알림 칸이 없다(통합인증 두 번째 벽, 설계 2-2 GL-01 과 같은 꼴)"
)
PLACE_RESULT = (
    "동작 결과의 거부 · 경고 — 누른 단추 곁에 남긴다(D3 (가) — 고칠 입력이 그 자리에 있다)"
)
PLACE_CONFIRM = (
    "확인 창 — 되돌리기 어려운 동작 앞에서 무엇이 바뀌는지 적고 체크 · 단추와 함께 선다(설계 2-2)"
)
PLACE_EMPTY = "빈 상태 · 멈춤 — 화면이 이 글로 끝난다(그릴 것이 없다, 설계 2-2 「빈 상태」)"
PLACE_BLOCKED = (
    "보기 하나를 못 그린 자리 — 그 보기의 전부라 자리에 남긴다(설계 2-2 화면을 못 그리는 오류)"
)
PLACE_DETAIL = (
    "고른 대상(층 · 칸 · 시나리오)의 설명 — 고를 때마다 바뀌어 상태 알림이면 오갈 때마다 다시 뜬다"
)
PLACE_VERDICT = "화면 결론 — 성공 상자와 짝인 요약 판정(화면의 일부, 설계 2-2 상태 알림 목록 밖)"
PLACE_REPORT = "점검 보고 — 결과 표 · 내려받기와 한 몸(BigDataQuery 등록의 기준정보 충돌 보고)"
PLACE_KEPT = (
    "닫을 때까지 남는 사건 — 남의 저장이 내 편집을 버렸다(「알림 닫기」 와 한 몸, E2E #66 · "
    "알림창은 EQ-05)"
)

REASONS = frozenset(
    {
        PLACE_FORM,
        PLACE_BOARD,
        PLACE_STOP,
        PLACE_RESULT,
        PLACE_CONFIRM,
        PLACE_EMPTY,
        PLACE_BLOCKED,
        PLACE_DETAIL,
        PLACE_VERDICT,
        PLACE_REPORT,
        PLACE_KEPT,
    }
)

# (파일, 맨 바깥 함수) → (경고 호출 수, 까닭).
ALLOWED: dict[tuple[str, str], tuple[int, str]] = {
    ("app_pages/load_conversion.py", "_plan_paste_dialog"): (1, PLACE_FORM),
    ("app_pages/load_conversion.py", "_virtual_product_dialog"): (2, PLACE_FORM),
    ("app_pages/load_conversion.py", "_yield_paste_dialog"): (1, PLACE_FORM),
    ("app_pages/reference_data.py", "_step_dialog"): (1, PLACE_FORM),
    ("app_pages/reference_integrity.py", "_render_summary"): (1, PLACE_VERDICT),
    ("app_pages/space_status.py", ""): (1, PLACE_DETAIL),
    ("app_pages/space_status.py", "_render_fab_editor"): (1, PLACE_RESULT),
    ("app_pages/space_status.py", "_render_layout_editor"): (1, PLACE_RESULT),
    ("app_pages/standard_target_capa.py", "_clear_dialog"): (1, PLACE_FORM),
    ("app_pages/voc.py", ""): (1, PLACE_RESULT),
    ("app_pages/wip_status.py", ""): (3, PLACE_EMPTY),
    ("src/capa_simulation/components/alert_board.py", "render_alert_board"): (1, PLACE_BOARD),
    ("src/capa_simulation/components/auto_official_update_tab.py", "_render_run_now"): (
        1,
        PLACE_RESULT,
    ),
    (
        "src/capa_simulation/components/availability_gap_panel.py",
        "_render_securement_cross_check",
    ): (1, PLACE_BLOCKED),
    ("src/capa_simulation/components/availability_gap_panel.py", "_render_static_evidence"): (
        1,
        PLACE_DETAIL,
    ),
    (
        "src/capa_simulation/components/bigdataquery_registration.py",
        "_render_reference_conflict_report",
    ): (1, PLACE_REPORT),
    ("src/capa_simulation/components/constraint_simulation_view.py", "_render_month_steps"): (
        1,
        PLACE_VERDICT,
    ),
    ("src/capa_simulation/components/cutoff_management.py", "render_cutoff_management"): (
        2,
        PLACE_RESULT,
    ),
    ("src/capa_simulation/components/display_order_management.py", "_draw_label_warnings"): (
        1,
        PLACE_RESULT,
    ),
    ("src/capa_simulation/components/display_order_management.py", "_render_label_warnings"): (
        1,
        PLACE_RESULT,
    ),
    ("src/capa_simulation/components/equipment_data_workspace.py", "_render_bulk_delete_status"): (
        1,
        PLACE_CONFIRM,
    ),
    ("src/capa_simulation/components/equipment_data_workspace.py", "render_reopen_notices"): (
        1,
        PLACE_KEPT,
    ),
    ("src/capa_simulation/components/equipment_data_workspace.py", "render_small_editor"): (
        1,
        PLACE_FORM,
    ),
    ("src/capa_simulation/components/equipment_import_dialog.py", "_render_review"): (
        1,
        PLACE_FORM,
    ),
    ("src/capa_simulation/components/equipment_master_tab.py", "_render_notices"): (2, PLACE_FORM),
    ("src/capa_simulation/components/equipment_master_tab.py", "_render_save_section"): (
        1,
        PLACE_CONFIRM,
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_clear_layout"): (
        1,
        PLACE_CONFIRM,
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_legacy_trace"): (
        1,
        PLACE_FORM,
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_restore"): (
        1,
        PLACE_CONFIRM,
    ),
    (
        "src/capa_simulation/components/equipment_scenario_management.py",
        "render_equipment_scenario_management",
    ): (2, PLACE_CONFIRM),
    ("src/capa_simulation/components/equipment_scenario_status.py", "_render_save"): (
        2,
        PLACE_FORM,
    ),
    ("src/capa_simulation/components/floor_layout_upload.py", "_floor_layout_dialog"): (
        4,
        PLACE_FORM,
    ),
    ("src/capa_simulation/components/home_main_cases.py", "_draw"): (1, PLACE_FORM),
    ("src/capa_simulation/components/home_preference.py", "_render_execution_notices"): (
        2,
        PLACE_FORM,
    ),
    ("src/capa_simulation/components/month_editor.py", "paste_dialog"): (1, PLACE_FORM),
    ("src/capa_simulation/components/performance_actual_screen.py", "_render_summary"): (
        1,
        PLACE_VERDICT,
    ),
    ("src/capa_simulation/components/period_field.py", "_render_pending_notice"): (1, PLACE_FORM),
    ("src/capa_simulation/components/required_shortening_panel.py", "_render_scenario_error"): (
        1,
        PLACE_BLOCKED,
    ),
    ("src/capa_simulation/components/scenario_management.py", "_render_delete"): (1, PLACE_CONFIRM),
    ("src/capa_simulation/components/scenario_management.py", "_render_list_toolbar"): (
        1,
        PLACE_FORM,
    ),
    ("src/capa_simulation/components/scenario_management.py", "_render_official"): (
        1,
        PLACE_CONFIRM,
    ),
    ("src/capa_simulation/components/scenario_management.py", "_render_scenario_actions"): (
        2,
        PLACE_CONFIRM,
    ),
    ("src/capa_simulation/components/scenario_month_merge.py", "_render_merge"): (6, PLACE_FORM),
    ("src/capa_simulation/components/scenario_status.py", "_render_revision_save"): (3, PLACE_FORM),
    ("src/capa_simulation/components/scenario_transform.py", "render_derived_save"): (
        1,
        PLACE_RESULT,
    ),
    ("src/capa_simulation/components/shortening_progress_panel.py", "load_selected_baseline"): (
        1,
        PLACE_BLOCKED,
    ),
    ("src/capa_simulation/components/source_quality.py", "render_source_quality"): (
        1,
        PLACE_VERDICT,
    ),
    ("src/capa_simulation/components/space_floor_list.py", "_render_confirm"): (2, PLACE_FORM),
    ("src/capa_simulation/components/space_floor_list.py", "_render_notices"): (1, PLACE_RESULT),
    ("src/capa_simulation/components/space_shortening_view.py", "render_layer_stop"): (
        1,
        PLACE_BLOCKED,
    ),
    ("src/capa_simulation/components/sso_identity.py", "_stop_account_changed"): (1, PLACE_STOP),
    ("src/capa_simulation/components/sso_identity.py", "_stop_signed_out"): (1, PLACE_STOP),
}


def _scanned() -> list[Path]:
    files = [PROJECT_ROOT / "app.py"]
    for base in ("app_pages", "src/capa_simulation"):
        files.extend(sorted((PROJECT_ROOT / base).rglob("*.py")))
    return [path for path in files if path.relative_to(PROJECT_ROOT).as_posix() not in OWNERS]


def _count(node: ast.AST, outer: str, relative: str, counts: Counter[tuple[str, str]]) -> None:
    for child in ast.iter_child_nodes(node):
        name = outer
        if not outer and isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            name = child.name
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "warning"
            and ast.unparse(child.func.value).split(".")[-1] not in _LOGGERS
        ):
            counts[(relative, outer)] += 1
        _count(child, name, relative, counts)


def direct_warnings() -> Counter[tuple[str, str]]:
    """(파일, 맨 바깥 함수) 마다 경고 상자를 직접 그리는 호출 수."""
    counts: Counter[tuple[str, str]] = Counter()
    for path in _scanned():
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        _count(ast.parse(path.read_text(encoding="utf-8")), "", relative, counts)
    return counts


def test_no_new_place_draws_a_state_warning_directly() -> None:
    """새 경고 자리는 상태 알림이면 `alerts.state`, 동작 결과면 `queue_flash`, 자리 글이면 이 목록에
    까닭과 함께."""
    found = direct_warnings()
    new = {site: count for site, count in found.items() if count > ALLOWED.get(site, (0, ""))[0]}
    assert not new, (
        "경고 상자를 직접 그리는 새 자리입니다 — 상태 알림이면 `alerts.state(...)`(지문이 바뀔"
        ' 때만 알림창 · Alarm), 동작 결과면 `flash.queue_flash(…, kind="warning")`, 자리 글이면'
        " tests/test_alert_sites.py ALLOWED 에 까닭과 함께 두세요:\n"
        + "\n".join(f"{file} {func or '(본문)'}: {count}" for (file, func), count in new.items())
    )


def test_every_allowed_site_is_still_there_with_its_count() -> None:
    """옮긴 자리는 목록에서도 지운다 — 남은 수가 다른 새 자리를 덮지 않게(2단계 갈래가 목록을
    줄인다)."""
    found = direct_warnings()
    stale = {
        site: (allowed, found.get(site, 0))
        for site, (allowed, _) in ALLOWED.items()
        if found.get(site, 0) != allowed
    }
    assert not stale, "허용 목록 수가 코드와 다릅니다(목록 수, 지금 수):\n" + "\n".join(
        f"{file} {func or '(본문)'}: {pair}" for (file, func), pair in stale.items()
    )


def test_every_allowed_site_says_why() -> None:
    """남은 자리는 모두 자리 글 까닭 하나를 든다 — 「2단계가 가른다」 같은 미룬 까닭은 없다."""
    unknown = {site: reason for site, (_, reason) in ALLOWED.items() if reason not in REASONS}
    assert not unknown, unknown
    assert all(count > 0 for count, _ in ALLOWED.values())
