# Purpose: 접속 등급 표 · 동작 표 · 사건 바닥 표 그물과 거절 글 · 예외 꼴 · 감사 사건을 지킨다.

"""접속 등급의 판정 한 곳(`auth/grades.py`)과 감사 사건 목록(2026-11-18 접속 등급).

동작 표는 확정 표 24줄을 동작 이름 26개로 가르고, 표지를 단 저장소 쓰기는 모두 사건 → 바닥 동작
표(`EVENT_FLOORS`)로 벽이 선다 — 표에 없는 사건은 닫힌 쪽(개발자)이라 새 쓰기가 등급 줄 없이 열리지
않는다. 이 시험이 그 표들과 거절 글 · 예외 꼴을 잠근다.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from capa_simulation.audit import events
from capa_simulation.audit.work import EVENT_ATTRIBUTE
from capa_simulation.auth import grades
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS
from capa_simulation.persistence import equipment_repository, repository

ROOT = Path(__file__).resolve().parents[1]
GRADES_FILE = ROOT / "src" / "capa_simulation" / "auth" / "grades.py"

# api_contract 1절의 동작 표 — 이름 · 필요 등급.
CONTRACT_ACTIONS = {
    "voc.post": grades.VIEWER,
    "voc.manage": grades.DEVELOPER,
    "scenario.revision_save": grades.EDITOR,
    "scenario.create": grades.EDITOR,
    "scenario.db_register": grades.EDITOR,
    "scenario.list_edit": grades.EDITOR,
    "scenario.archive": grades.EDITOR,
    "revision.rename": grades.EDITOR,
    "scenario.delete": grades.MANAGER,
    "official.publish": grades.MANAGER,
    "home.settings": grades.MANAGER,
    "shortening.baseline": grades.EDITOR,
    "shortening.filter_default": grades.MANAGER,
    "shortening.progress_log": grades.EDITOR,
    "shortening.progress_goal": grades.MANAGER,
    "target.availability": grades.MANAGER,
    "auto_update.view": grades.MANAGER,
    "auto_update.edit": grades.DEVELOPER,
    "equipment.save": grades.MANAGER,
    "equipment.downtime": grades.EDITOR,
    "equipment.manual_downtime": grades.EDITOR,
    "equipment.export": grades.MANAGER,
    "equipment.scenario": grades.MANAGER,
    "equipment.publish": grades.MANAGER,
    "equipment.cutoff": grades.MANAGER,
    "equipment.legacy_ack": grades.DEVELOPER,
    "diag.full": grades.DEVELOPER,
    "admin.area": grades.DEVELOPER,
    "screen.unfinished": grades.DEVELOPER,
}


def test_the_grades_are_four_in_low_to_high_order_without_admin() -> None:
    assert grades.GRADES == ("viewer", "editor", "manager", "developer")
    assert "admin" not in grades.GRADES and "admin" not in grades.STORED_GRADES
    assert grades.STORED_GRADES == ("editor", "manager")
    assert [grades.label_of(grade) for grade in grades.GRADES] == [
        "열람",
        "실무자",
        "관리자",
        "개발자",
    ]
    assert grades.label_of("admin") == "열람", "모르는 값은 열람이다"
    assert grades.rank("bogus") == 0
    assert grades.at_least("manager", "editor") and not grades.at_least("editor", "manager")
    assert grades.ENV_DEVELOPER_LABEL == "개발자(환경변수)"
    assert grades.APP_MANAGER_ROLE == "앱 관리자(개발자)"


def test_the_action_table_matches_the_contract() -> None:
    assert {key: action.need for key, action in grades.ACTIONS.items()} == CONTRACT_ACTIONS
    for key, action in grades.ACTIONS.items():
        assert action.key == key
        # 「…할」 꼴 — 끝 글자의 받침이 ㄹ 이다(할 · 쓸 · 볼 · 바꿀 · 지울 · 받을 …).
        last = ord(action.what[-1]) - 0xAC00
        assert 0 <= last < 11172 and last % 28 == 8, key
    with pytest.raises(KeyError):
        grades.need_of("no.such.action")


def test_every_event_floor_points_at_a_known_action() -> None:
    for event, action in grades.EVENT_FLOORS.items():
        assert action in grades.ACTIONS, (event, action)
        assert events.spec_of(event) is not None, f"감사 사건 목록에 없는 바닥 사건: {event}"
    assert grades.EVENT_FLOORS["data_equipment_save"] == "equipment.downtime", "바닥 — 안쪽 대조"
    assert grades.floor_of("data_unknown_event") == grades.UNMAPPED_ACTION == "admin.area"


def _marked_writes() -> list[tuple[str, object]]:
    found: list[tuple[str, object]] = []
    for owner in (
        repository.DuckDBScenarioRepository,
        equipment_repository.DuckDBEquipmentRepository,
    ):
        for name, member in inspect.getmembers(owner, predicate=inspect.isfunction):
            if getattr(member, EVENT_ATTRIBUTE, None) is not None or hasattr(
                member, grades.GATE_ATTRIBUTE
            ):
                found.append((f"{owner.__name__}.{name}", member))
    return found


def test_every_marked_repository_write_has_a_floor_or_an_action() -> None:
    """표지(`@audited` · `@audited_each` · `@gated`)를 단 저장소 쓰기는 모두 바닥 표에 있거나
    `action=` 을 준 것이다 — 닫힌 쪽(`UNMAPPED_ACTION`)으로 떨어진 표지가 없다."""
    marked = _marked_writes()
    assert len(marked) >= 40, "표지 찾기가 저장소 쓰기를 잡아야 한다"
    for name, member in marked:
        action = getattr(member, grades.GATE_ATTRIBUTE, None)
        assert action in grades.ACTIONS, name
        marker = getattr(member, EVENT_ATTRIBUTE, None)
        if marker is None:
            continue
        marker_events = (marker,) if isinstance(marker, str) else tuple(marker)
        mapped = [event for event in marker_events if event in grades.EVENT_FLOORS]
        assert mapped, f"{name} 의 사건 {marker_events} 가 바닥 표에 없다"


def test_refusal_texts_name_the_grade_and_never_use_percent_points() -> None:
    assert grades.refusal_text("official.publish") == "관리자부터 공식 지정을 할 수 있습니다"
    assert (
        grades.refusal_text("voc.manage") == "개발자만 VOC 답변 표시 · 글 지우기를 할 수 있습니다"
    )
    assert (
        grades.refusal_text("equipment.downtime") == "실무자부터 비가동 일정을 저장할 수 있습니다"
    )
    for key in grades.ACTIONS:
        text = grades.refusal_text(key)
        assert text.endswith("수 있습니다"), key
        assert "%p" not in text
    assert grades.stop_text("scenario.db_register", place="tab") == "실무자부터 여는 탭입니다"
    assert grades.stop_text("admin.area", place="page") == "개발자만 여는 화면입니다"
    assert grades.stop_text("auto_update.view", place="tab") == "관리자부터 여는 탭입니다"
    assert grades.SIGNED_OUT_TEXT == "로그인이 끝나 저장하지 않았습니다 — 다시 로그인하세요"


def test_the_refusals_are_plain_exceptions_outside_the_bootstrap_errors() -> None:
    """`PermissionError` 를 본뜨면 `OSError` 라 화면 공용 예외 튜플에 삼켜진다 — `Exception`
    직속."""
    for kind in grades.REFUSALS:
        assert kind.__bases__ == (Exception,)
        assert not issubclass(kind, OSError)
        assert not issubclass(kind, BOOTSTRAP_ERRORS)
    denied = grades.GradeDenied("official.publish", grades.MANAGER, grades.EDITOR)
    assert (denied.action, denied.need, denied.have) == ("official.publish", "manager", "editor")
    ended = grades.SignInEnded("scenario.create", "expired")
    assert (ended.action, ended.reason) == ("scenario.create", "expired")


def test_highest_and_require_all_pick_one_judgement() -> None:
    assert grades.highest(["scenario.create", "equipment.save", "voc.post"]) == "equipment.save"
    assert grades.highest([]) is None
    grades.require_all([])


def test_the_judge_module_imports_only_the_standard_library_and_the_recorder() -> None:
    """persistence 에서도 부를 수 있게 — 표준 라이브러리 + 감사 기록기만(돌고 도는 import 없음)."""
    tree = ast.parse(GRADES_FILE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    ours = {name for name in imported if name.startswith("capa_simulation")}
    assert ours == {"capa_simulation.audit"}, ours


def test_without_an_installed_judge_everything_passes() -> None:
    """판정기가 꽂히지 않은 프로세스(스크립트 · 저장소 시험)는 제한이 없다."""
    grades.install_caller_source(None)
    assert grades.caller().unrestricted
    for key in grades.ACTIONS:
        assert grades.allowed(key)
        grades.require(key)


def test_a_broken_judge_reads_as_viewer() -> None:
    def broken() -> grades.Caller:
        raise RuntimeError("boom")

    grades.install_caller_source(broken)
    assert grades.caller() == grades.Caller(grades.VIEWER)
    assert grades.allowed("voc.post")
    assert not grades.allowed("scenario.create")


def test_the_audit_event_list_carries_the_new_grade_events() -> None:
    assert events.GRADES == ("developer", "manager", "editor", "viewer", "system", "none")
    for name, keys in (
        ("authz_fail_grade", {"action", "need", "have"}),
        ("authz_fail_signin", {"action", "reason"}),
        ("data_shortening_filter_save", {"field", "rows"}),
        ("data_legacy_trace_ack", {"count"}),
        ("data_module_upload", {"result", "bytes"}),
        ("data_module_query", {"result", "rows"}),
        ("sys_grade_read_fail", {"reason", "status"}),
        ("sys_grade_save_fail", {"reason", "status"}),
    ):
        spec = events.spec_of(name)
        assert spec is not None, name
        assert spec.det_keys == frozenset(keys), name
    assert events.DET_LABELS["need"] == "필요 등급"
    assert events.DET_LABELS["have"] == "지금 등급"
    assert events.DET_LABELS["field"] == "칸"
    assert events.DET_LABELS["bytes"] == "바이트"
    assert events.DET_LABELS["admins"] == "개발자 수"
    assert events.DET_LABELS["admin_fp"] == "개발자 지문"
    assert events.label_of("authz_admin_config") == "개발자 구성"
    assert events.GRADE_VALUE_LABELS["admin"] == "개발자(옛 기록)"
    assert events.GRADE_VALUE_LABELS["user"] == "일반(옛 기록)"
