# Purpose: 서버 시각대(TZ)를 따르는 시각 부름을 화면 코드에서 AST 로 세어 허용 목록(까닭 · 수)과
# 맞댄다.

"""서버 시각대 그물(설계 규칙 UI-DAT-11 · UI-CON-04 — 화면 시각 한 곳 `korea_time`).

화면 · 알림 · 복사 글에 그리는 시각은 KST 다(`capa_simulation/korea_time.py` 모듈 설명). 이
그물은 화면 코드(`app.py` · `capa_server.py` · `app_pages/` · `src/capa_simulation/` · 앱이 서기
전 시작 임시 화면 `scripts/container_stage.py`)에서 서버 시각대를 따르는 부름을 (파일, 맨 바깥
함수 — 모듈 본문은 "", 갈래) 마다 세어 허용 목록과 **정확히** 맞댄다.

- 갈래 — `astimezone()`(인자 없음) · `time.localtime` · `time.strftime(꼴)`(지금 시각 한 인자) ·
  `time.ctime` · `time.asctime` · `time.mktime` · `fromtimestamp(초)`(시각대 없음) ·
  `datetime.now()` · `Timestamp.now()`(인자 없음) · `date.today()` · `datetime.today()` ·
  `Timestamp.today()`, 그리고 부르지 않고 값으로 넘긴 `datetime.now` · `date.today`(시계 기본값).
- 새 자리가 생기면 실패한다 — 사람이 읽는 시각이면 `korea_time.kst_clock`(또는 `KST`)으로 옮기고,
  아래 까닭 가운데 하나에 들면 목록에 둔다.
- 자리가 줄면 실패한다 — 목록의 수도 줄인다(옮긴 자리가 목록에 남아 다른 새 자리를 덮지 않게).

남은 자리는 시각대 없는(naive) 벽시계다 — 업무 「오늘」 과 DB 에 시각대 없이 적는 저장 시각 · 예약
시각이다. 저장 쪽은 DuckDB `current_timestamp` 기본값(마이그레이션 · 저장소 SQL)과 같은 기준이라
화면에서만 고치면 옛 행과 어긋난다 — C-DEP 이미지 시각대를 정한 뒤 한 번에 본다.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from source_sites import screen_calls, screen_files

PROJECT_ROOT = Path(__file__).resolve().parents[1]

TODAY = (
    "업무 「오늘」 — 계산 기준일 · 기본 기간 · 기준일 칸 · 파일 이름 날짜(시각이 아니라 날짜). 서버"
    " 날짜라 서버 시각대가 KST 가 아니면 KST 0 ~ 9시에 하루 앞이다 — C-DEP 시각대를 정한 뒤 한 번에"
)
WALL = (
    "저장 · 예약 벽시계 — DB 에 시각대 없이 적는 저장 시각(DuckDB `current_timestamp` 기본값과"
    " 같은 기준)과 매일 지정 시각 판정. 화면에서만 고치면 옛 행과 어긋난다 — C-DEP 시각대를 정한 뒤"
    " 한 번에"
)
SAMPLE = "합성 견본의 기준일 — 빈 저장소 · 데모 표본(운영 값이 아니다)"
FILE_NAME = "파일 이름 — 사람이 읽는 화면 시각이 아니다(서버 로그 · 파일 이름은 바꾸지 않음)"
REASONS = frozenset({TODAY, WALL, SAMPLE, FILE_NAME})

ALLOWED: dict[tuple[str, str, str], tuple[int, str]] = {
    ("app_pages/available_equipment_status.py", "", "today()"): (1, TODAY),
    ("app_pages/constraint_simulation.py", "", "today()"): (1, TODAY),
    ("app_pages/process_capa_detail.py", "", "today()"): (1, TODAY),
    ("app_pages/required_shortening.py", "", "today()"): (1, TODAY),
    ("app_pages/space_status.py", "", "today()"): (1, TODAY),
    ("app_pages/space_status.py", "_set_space_as_of", "today()"): (1, TODAY),
    ("app_pages/wip_status.py", "", "today()"): (1, TODAY),
    (
        "src/capa_simulation/auto_official_update_runner.py",
        "run_auto_official_update",
        "now (값)",
    ): (1, WALL),
    ("src/capa_simulation/auto_update_scheduler.py", "__init__", "now (값)"): (1, WALL),
    (
        "src/capa_simulation/components/auto_official_update_tab.py",
        "render_auto_official_update",
        "now (값)",
    ): (1, WALL),
    (
        "src/capa_simulation/components/bigdataquery_registration.py",
        "_queue_reference_conflict_report",
        "now()",
    ): (1, FILE_NAME),
    (
        "src/capa_simulation/components/bigdataquery_registration.py",
        "_render_catalog_form",
        "now()",
    ): (1, TODAY),
    (
        "src/capa_simulation/components/bigdataquery_registration.py",
        "_render_registration_form",
        "now()",
    ): (1, TODAY),
    ("src/capa_simulation/components/date_panel.py", "_day_field", "today()"): (1, TODAY),
    ("src/capa_simulation/components/date_panel.py", "_draw", "today()"): (1, TODAY),
    ("src/capa_simulation/components/date_panel.py", "_range_field", "today()"): (1, TODAY),
    (
        "src/capa_simulation/components/equipment_data_workspace.py",
        "_render_current_data_downloads",
        "today()",
    ): (1, TODAY),
    (
        "src/capa_simulation/components/equipment_data_workspace.py",
        "_render_history",
        "today()",
    ): (1, TODAY),
    (
        "src/capa_simulation/components/equipment_data_workspace.py",
        "build_import_review",
        "today()",
    ): (1, TODAY),
    (
        "src/capa_simulation/components/equipment_import_dialog.py",
        "_master_has_errors",
        "today()",
    ): (1, TODAY),
    (
        "src/capa_simulation/components/equipment_master_tab.py",
        "_rebuilt_materials",
        "today()",
    ): (1, TODAY),
    ("src/capa_simulation/components/intro_summary.py", "_current_month", "today()"): (1, TODAY),
    (
        "src/capa_simulation/components/period_field.py",
        "render_period_dialog_body",
        "today()",
    ): (1, TODAY),
    (
        "src/capa_simulation/io/company_bigdataquery_adapter.py",
        "default_query_window",
        "now()",
    ): (1, TODAY),
    (
        "src/capa_simulation/io/company_bigdataquery_adapter.py",
        "registration_detail_window",
        "now()",
    ): (1, TODAY),
    (
        "src/capa_simulation/persistence/equipment_repository.py",
        "_save_equipment",
        "today()",
    ): (1, TODAY),
    (
        "src/capa_simulation/persistence/equipment_repository.py",
        "save_shortening_baseline",
        "now()",
    ): (1, WALL),
    (
        "src/capa_simulation/services/equipment_samples.py",
        "sample_downtime_schedule",
        "today()",
    ): (1, SAMPLE),
    (
        "src/capa_simulation/services/equipment_samples.py",
        "sample_equipment_master",
        "today()",
    ): (1, SAMPLE),
    ("src/capa_simulation/services/wip_status.py", "build_wip_history_demo", "today()"): (
        1,
        SAMPLE,
    ),
}

_TIME_LOCAL = frozenset({"ctime", "asctime", "mktime"})
_NOW_OWNERS = frozenset({"datetime", "Timestamp"})
_TODAY_OWNERS = frozenset({"date", "datetime", "Timestamp"})


def call_kind(call: ast.Call) -> str | None:
    """서버 시각대를 따르는 부름이면 갈래 이름, 아니면 None."""
    func = call.func
    if isinstance(func, ast.Attribute):
        owner, name = ast.unparse(func.value).split(".")[-1], func.attr
    elif isinstance(func, ast.Name):
        owner, name = "", func.id
    else:
        return None
    bare = not call.args and not call.keywords
    if name == "astimezone" and bare:
        return "astimezone()"
    if name == "localtime" and owner in {"time", ""}:
        return "localtime"
    if name in _TIME_LOCAL and owner == "time":
        return name
    if name == "strftime" and owner == "time" and len(call.args) == 1:
        return "time.strftime(꼴)"
    keywords = {item.arg for item in call.keywords}
    if name == "fromtimestamp" and len(call.args) < 2 and "tz" not in keywords:
        return "fromtimestamp(시각대 없음)"
    if name == "now" and owner in _NOW_OWNERS and bare:
        return "now()"
    if name == "today" and owner in _TODAY_OWNERS and bare:
        return "today()"
    return None


def value_kinds(tree: ast.AST) -> list[tuple[str, str]]:
    """부르지 않고 값으로 넘긴 `datetime.now` · `date.today`(시계 기본값) — (맨 바깥 이름, 갈래)."""
    called = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    found: list[tuple[str, str]] = []

    def visit(node: ast.AST, outer: str) -> None:
        for child in ast.iter_child_nodes(node):
            name = outer
            # 맨 바깥 이름은 `source_sites.calls_by_outer` 와 같다(모듈 맨 위 함수 · 클래스 메서드).
            if not outer and isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                name = child.name
            if (
                isinstance(child, ast.Attribute)
                and id(child) not in called
                and isinstance(child.value, ast.Name)
                and (
                    (child.attr == "now" and child.value.id in _NOW_OWNERS)
                    or (child.attr == "today" and child.value.id in _TODAY_OWNERS)
                )
            ):
                found.append((outer, f"{child.attr} (값)"))
            visit(child, name)

    visit(tree, "")
    return found


def _files() -> list[Path]:
    # 시작 임시 화면은 앱 밖이지만 사람이 보는 화면이다(그 밖 `scripts/` 는 개발 · 사내 도구 출력과
    # 저장 꼴 — 시작 결과 파일의 시각은 시각대가 붙어 화면이 KST 로 옮긴다).
    return [
        *screen_files(),
        PROJECT_ROOT / "capa_server.py",
        PROJECT_ROOT / "scripts" / "container_stage.py",
    ]


def server_clock_sites() -> Counter[tuple[str, str, str]]:
    """(파일, 맨 바깥 함수 — 모듈 본문은 "", 갈래) → 수."""
    found: Counter[tuple[str, str, str]] = Counter()
    for relative, outer, _path, _scope, call in screen_calls(_files()):
        kind = call_kind(call)
        if kind is not None:
            found[(relative, outer, kind)] += 1
    for path in _files():
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        for outer, kind in value_kinds(ast.parse(path.read_text(encoding="utf-8"))):
            found[(relative, outer, kind)] += 1
    return found


def test_the_net_sees_every_kind() -> None:
    """그물이 갈래마다 실제로 잡는지 — 보기 소스 한 벌로 본다(빈 그물이 통과하지 않게)."""
    source = """
import time
from datetime import date, datetime

def a(moment, value):
    moment.astimezone()
    time.localtime(value)
    time.strftime("%H:%M")
    time.ctime()
    datetime.fromtimestamp(value)
    datetime.now()
    date.today()
    clock = datetime.now
    moment.astimezone(KST)
    time.strftime("%H:%M", value)
    datetime.fromtimestamp(value, tz=KST)
    datetime.now(KST)
"""
    tree = ast.parse(source)
    kinds = [
        kind for node in ast.walk(tree) if isinstance(node, ast.Call) if (kind := call_kind(node))
    ]
    assert sorted(kinds) == sorted(
        [
            "astimezone()",
            "localtime",
            "time.strftime(꼴)",
            "ctime",
            "fromtimestamp(시각대 없음)",
            "now()",
            "today()",
        ]
    )
    assert value_kinds(tree) == [("a", "now (값)")]


def test_no_new_place_reads_the_server_time_zone() -> None:
    """새 자리는 사람이 읽는 시각이면 `korea_time.kst_clock`(또는 `KST`)으로, 날짜 · 저장 벽시계면
    이 목록에 까닭과 함께."""
    found = server_clock_sites()
    new = {site: count for site, count in found.items() if count > ALLOWED.get(site, (0, ""))[0]}
    assert not new, (
        "서버 시각대를 따르는 새 자리입니다 — 화면 · 알림 · 복사 글의 시각이면"
        " `korea_time.kst_clock(시각, 꼴)`(KST)로 옮기고, 업무 「오늘」 · 저장 벽시계면"
        " tests/test_server_clock_sites.py ALLOWED 에 까닭과 함께 두세요:\n"
        + "\n".join(
            f"{file} {func or '(본문)'} {kind}: {count}"
            for (file, func, kind), count in new.items()
        )
    )


def test_every_allowed_site_is_still_there_with_its_count() -> None:
    """옮긴 자리는 목록에서도 지운다 — 남은 수가 다른 새 자리를 덮지 않게."""
    found = server_clock_sites()
    stale = {
        site: (allowed, found.get(site, 0))
        for site, (allowed, _) in ALLOWED.items()
        if found.get(site, 0) != allowed
    }
    assert not stale, "허용 목록 수가 코드와 다릅니다(목록 수, 지금 수):\n" + "\n".join(
        f"{file} {func or '(본문)'} {kind}: {pair}" for (file, func, kind), pair in stale.items()
    )


def test_every_allowed_site_says_why() -> None:
    unknown = {site: reason for site, (_, reason) in ALLOWED.items() if reason not in REASONS}
    assert not unknown, unknown
    assert all(count > 0 for count, _ in ALLOWED.values())
