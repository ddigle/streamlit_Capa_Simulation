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

오류(`st.error`)와 안내(`st.info`)는 이 그물 밖이다 — 오류는 그 자리 입력의 거부 · 누른 동작의
실패만 자리에 남고(D3), 데이터 때문에 못 그린 자리는 「데이터 Error」
마크다(`tests/test_data_error_mark.py` 가 `st.error` 전부를 자리 · 까닭으로 맞댄다). 안내는 대개
자리 글이다. 2단계는 상태 알림 후보를 옮길 때 같은 자리의 오류 · 안내도 함께 보았다.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from source_sites import TextResolver, called_name, receiver, screen_calls, screen_files

from capa_simulation import alerts
from capa_simulation.navigation import ALL_SPECS

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
PLACE_DETAIL = (
    "고른 대상(층 · 칸 · 시나리오)의 설명 — 고를 때마다 바뀌어 상태 알림이면 오갈 때마다 다시 뜬다"
)
PLACE_VERDICT = (
    "화면 결론 — 「없음」 평문 한 줄(남은 자리는 성공 상자)과 짝인 요약 판정(화면의 일부, 설계 2-2"
    " 상태 알림 목록 밖)"
)
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
        PLACE_DETAIL,
        PLACE_VERDICT,
        PLACE_KEPT,
    }
)

# (파일, 맨 바깥 함수) → (경고 호출 수, 까닭).
ALLOWED: dict[tuple[str, str], tuple[int, str]] = {
    ("app_pages/load_conversion.py", "_virtual_product_dialog"): (2, PLACE_FORM),
    ("app_pages/reference_data.py", "_step_dialog"): (1, PLACE_FORM),
    ("app_pages/reference_integrity.py", "_render_summary"): (1, PLACE_VERDICT),
    ("app_pages/space_status.py", ""): (1, PLACE_DETAIL),
    ("app_pages/space_status.py", "_render_fab_editor"): (1, PLACE_RESULT),
    ("app_pages/space_status.py", "_render_layout_editor"): (1, PLACE_RESULT),
    ("src/capa_simulation/components/alert_board.py", "render_alert_board"): (1, PLACE_BOARD),
    ("src/capa_simulation/components/auto_official_update_tab.py", "_render_run_now"): (
        1,
        PLACE_RESULT,
    ),
    ("src/capa_simulation/components/availability_gap_panel.py", "_render_static_evidence"): (
        1,
        PLACE_DETAIL,
    ),
    ("src/capa_simulation/components/constraint_simulation_view.py", "_render_month_steps"): (
        1,
        PLACE_VERDICT,
    ),
    ("src/capa_simulation/components/cutoff_management.py", "_render_missing_cutoffs"): (
        1,
        PLACE_FORM,
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
    ("src/capa_simulation/components/equipment_data_workspace.py", "render_reopen_notices"): (
        1,
        PLACE_KEPT,
    ),
    ("src/capa_simulation/components/equipment_data_workspace.py", "render_small_editor"): (
        1,
        PLACE_FORM,
    ),
    ("src/capa_simulation/components/equipment_master_tab.py", "_render_notices"): (2, PLACE_FORM),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_clear_layout"): (
        1,
        PLACE_CONFIRM,
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_restore"): (
        1,
        PLACE_CONFIRM,
    ),
    # 고른 시나리오의 옛 코드 흔적 줄과, 지울 배치 차이가 없어져 단추째 사라진 회차의 체크 풀림 줄.
    (
        "src/capa_simulation/components/equipment_scenario_management.py",
        "render_equipment_scenario_management",
    ): (2, PLACE_DETAIL),
    ("src/capa_simulation/components/equipment_scenario_status.py", "_render_save"): (
        2,
        PLACE_FORM,
    ),
    ("src/capa_simulation/components/home_main_cases.py", "_draw"): (1, PLACE_FORM),
    ("src/capa_simulation/components/home_preference.py", "_render_execution_notices"): (
        2,
        PLACE_FORM,
    ),
    ("src/capa_simulation/components/performance_actual_screen.py", "_render_summary"): (
        1,
        PLACE_VERDICT,
    ),
    ("src/capa_simulation/components/period_field.py", "_render_pending_notice"): (1, PLACE_FORM),
    ("src/capa_simulation/components/scenario_management.py", "_render_delete"): (1, PLACE_CONFIRM),
    ("src/capa_simulation/components/scenario_management.py", "_render_official"): (
        1,
        PLACE_CONFIRM,
    ),
    ("src/capa_simulation/components/scenario_management.py", "_render_detail"): (
        1,
        PLACE_CONFIRM,
    ),
    ("src/capa_simulation/components/scenario_month_merge.py", "_render_merge"): (2, PLACE_FORM),
    ("src/capa_simulation/components/scenario_status.py", "_render_revision_save"): (3, PLACE_FORM),
    ("src/capa_simulation/components/source_quality.py", "render_source_quality"): (
        1,
        PLACE_VERDICT,
    ),
    ("src/capa_simulation/components/space_floor_list.py", "_render_notices"): (1, PLACE_RESULT),
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


# 알림 글이 말해도 고칠 곳으로 읽히지 않는 이름 — 「HOME 설정」 · 「모듈」 은 화면 안 낱말이다.
_NOT_A_DESTINATION = frozenset({"HOME", "모듈"})
SCREEN_NAMES = frozenset(spec.title for spec in ALL_SPECS) - _NOT_A_DESTINATION
SAME_SCREEN = "제 화면의 탭을 말한다 — 「그 화면으로」 가 이미 그 화면이다"
COMPARED = "다른 화면을 견주어 말할 뿐 고칠 곳이 아니다"
TWO_PLACES = "고칠 곳이 둘이라 한 화면으로 보낼 수 없다"
LIST_HERE = "내역 표가 이 화면 탭에 있다 — 탭으로 먼저 가고 고칠 화면은 글이 말한다"
OPEN_GOTO = "미정리 — `goto` 를 달 자리(이 표를 줄인다)"
# (파일, 맨 바깥 함수) → 글이 다른 화면을 말하는데 `goto` 가 없는 상태 알림의 까닭.
NAMED_WITHOUT_GOTO: dict[tuple[str, str], str] = {
    ("app_pages/constraint_simulation.py", "report_locked_arrival"): COMPARED,
    (
        "src/capa_simulation/components/availability_gap_panel.py",
        "render_availability_gap_panel",
    ): TWO_PLACES,
    ("src/capa_simulation/components/cutoff_management.py", "report_missing_cutoffs"): SAME_SCREEN,
    (
        "src/capa_simulation/components/equipment_scenario_management.py",
        "report_layout_traces",
    ): SAME_SCREEN,
    (
        "src/capa_simulation/components/equipment_scenario_status.py",
        "render_legacy_trace_warning",
    ): OPEN_GOTO,
    (
        "src/capa_simulation/components/required_exclusion_notice.py",
        "alert_capacity_exclusions",
    ): LIST_HERE,
    ("src/capa_simulation/components/scenario_management.py", "_report_missing_official"): (
        SAME_SCREEN
    ),
}


def state_alerts_naming_a_screen_without_goto() -> set[tuple[str, str]]:
    """상태 알림(`alerts.state`) 가운데 짧은 글 · 전문이 화면 이름을 말하고 `goto` 가 없는 자리."""
    resolver = TextResolver()
    found: set[tuple[str, str]] = set()
    for relative, outer, path, scope, call in screen_calls(screen_files(exclude=OWNERS)):
        if called_name(call) != "state" or receiver(call) != "alerts":
            continue
        keywords = {item.arg: item.value for item in call.keywords}
        if "goto" in keywords:
            continue
        texts = [
            text
            for name in ("text", "full")
            if name in keywords
            for text in resolver.wholes(keywords[name], path, scope)
        ]
        if any(screen in text for screen in SCREEN_NAMES for text in texts):
            found.add((relative, outer))
    return found


def test_a_state_alert_that_names_another_screen_goes_there() -> None:
    """고칠 입력이 다른 화면이면 줄의 「그 화면으로」 가 그 화면을 연다(`goto` — 설계 규칙 UI-NTF-08 ·
    AGENTS 9장 「알림 칸」). 글로 화면 이름만 말하는 새 자리는 실패한다 — `goto` 를 주거나 고칠 곳이
    아니면 `NAMED_WITHOUT_GOTO` 에 까닭과 함께 둔다."""
    assert state_alerts_naming_a_screen_without_goto() == set(NAMED_WITHOUT_GOTO)


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


def _alert_text_strings() -> list[tuple[str, int, str]]:
    """`alerts.state(...)` 의 `text` · `full` 인자에 든 문자열 조각을 (파일, 줄, 글)로 모은다."""
    found: list[tuple[str, int, str]] = []
    for path in sorted((PROJECT_ROOT / "src").rglob("*.py")) + sorted(
        (PROJECT_ROOT / "app_pages").rglob("*.py")
    ):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "state":
                continue
            for keyword in node.keywords:
                if keyword.arg not in {"text", "full"}:
                    continue
                for piece in ast.walk(keyword.value):
                    if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                        relative = path.relative_to(PROJECT_ROOT).as_posix()
                        found.append((relative, piece.lineno, piece.value))
    return found


def test_alert_text_has_no_markdown_marks() -> None:
    """알림창 · Alarm 은 글을 그대로 그린다 — 코드 표시 기호가 화면에 글자로 남는다."""
    strings = _alert_text_strings()
    assert strings, "alerts.state 의 글을 하나도 찾지 못했다 — 이 시험이 아무것도 보지 않는다"
    assert [item for item in strings if "`" in item[2]] == []


def test_registered_alert_text_is_plain() -> None:
    """등록부의 기본 글도 그대로 그려진다 — 표시 기호 없이 평문이어야 한다."""
    written = [(spec.code, text) for spec in alerts.SPECS for text in (spec.short, spec.full)]
    assert [(code, text) for code, text in written if alerts.plain_text(text) != text] == []
