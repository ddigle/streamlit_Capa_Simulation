# Purpose: 등급 파일의 꼴 · 판정 · 못 읽을 때 · 두 객체 쓰는 차례 · 되돌림 이어짐을 지킨다.

"""등급 파일(`auth/grade_store.py` — 2026-11-18 접속 등급 결정 12 ~ 15).

저장소는 메모리 가짜 버킷이고(`grade_support.FakeBucket`) 값은 모두 합성(`demo.*`)이다. 모든 시험이
「운영 + 통합인증 켜짐 + S3 명단 켜짐」 판정을 거친다(`grade_support.operational_grades` 가 단언).
"""

from __future__ import annotations

import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from grade_support import (
    ADDED_AT,
    DEMO_DEVELOPER,
    DEMO_EDITOR,
    DEMO_MANAGER,
    DEMO_VIEWER,
    current_world,
    operational_grades,
    session_jar,
)
from sso_support import use_config

from capa_simulation.audit import recorder
from capa_simulation.auth import access_store, grade_store, grades, names, runtime
from capa_simulation.auth.access import (
    GRADE_ADMIN,
    GradeDocument,
    GradeLine,
    GradeSource,
    ListDocument,
)
from capa_simulation.auth.identity import Identity, identity_from_cookies
from capa_simulation.io import s3_small
from capa_simulation.services.object_storage_manifest import PRUNE_PREFIXES

# 얼린 앞 판 견본(`tests/fixtures/access_list_v1.py`) — 견본 폴더는 꾸러미가 아니라 길로 읽는다.
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))

import access_list_v1  # noqa: E402

NEWCOMER = "demo.newcomer"


def _identity(loginid: str) -> Identity:
    cfg = runtime.config()
    jar = session_jar(cfg, loginid)
    found = identity_from_cookies(jar, cfg, int(time.time()), renewals=True)
    assert isinstance(found, Identity)
    return found


def _world() -> tuple[object, object]:
    world = current_world()
    assert world is not None
    return world.cfg, world.bucket


@pytest.fixture()
def audit_on() -> list[dict[str, object]]:
    recorder.start(env="cdep", version="test", inst="i-test")
    return []


# ------------------------------------------------------------------ 꼴 · 자리
def test_the_document_round_trips_and_keeps_unknown_grades_as_viewer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = GradeDocument(
        revision=4,
        lines=(
            GradeLine(DEMO_EDITOR, "editor", ADDED_AT, DEMO_DEVELOPER, ADDED_AT),
            GradeLine(DEMO_VIEWER, "superuser", ADDED_AT, DEMO_DEVELOPER, ADDED_AT),
        ),
    )
    body = grade_store.render_document(document)
    assert b'"grades"' in body and b"\n " in body, "명단과 같은 꼴(들여쓰기 1)"
    parsed = grade_store.parse_document(body)
    assert parsed.revision == 4
    assert parsed.line_of(DEMO_VIEWER) == GradeLine(
        DEMO_VIEWER, "superuser", ADDED_AT, DEMO_DEVELOPER, ADDED_AT
    ), "모르는 값은 원문을 지킨다"

    cfg = operational_grades(monkeypatch)
    _, bucket = _world()
    bucket.put(None, grade_store.object_key(cfg), body)  # type: ignore[attr-defined]
    grade_store.read_at_start(cfg)
    assert grade_store.grade_of(cfg, DEMO_VIEWER) == grades.VIEWER, "판정만 열람"
    assert grade_store.grade_of(cfg, DEMO_EDITOR) == grades.EDITOR


@pytest.mark.parametrize(
    "body",
    [b"not json", b'{"format": 2, "revision": 1, "grades": []}', b'{"format": 1, "revision": -1}'],
)
def test_a_broken_document_is_unreadable(body: bytes) -> None:
    with pytest.raises(s3_small.S3Failure):
        grade_store.parse_document(body)


def test_the_file_sits_beside_the_list_and_outside_the_prune_prefixes() -> None:
    cfg = use_config()
    assert cfg.access_object_key == names.DEFAULT_ACCESS_OBJECT == "access/access_list.json"
    assert grade_store.object_key(cfg) == "access/grades.json"
    assert grade_store.mark_key(cfg) == "access/grades_seen.json"
    for key in (grade_store.object_key(cfg), grade_store.mark_key(cfg)):
        assert not any(key.startswith(prefix) for prefix in PRUNE_PREFIXES), key
    custom = replace(cfg, access_object_key="team/acl/list.json")
    assert grade_store.object_key(custom) == "team/acl/grades.json"


# ------------------------------------------------------------------ 판정
def test_a_line_counts_only_while_the_registration_time_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = operational_grades(monkeypatch)
    source = runtime.grade_source()
    assert source is not None and source.document is not None
    moved = replace(
        source.document,
        lines=(GradeLine(DEMO_EDITOR, grades.EDITOR, "2026-11-01T00:00:00Z", DEMO_DEVELOPER),),
    )
    runtime.publish_grade_source(replace(source, document=moved))
    assert grade_store.grade_of(cfg, DEMO_EDITOR) == grades.VIEWER
    assert grade_store.grade_of(cfg, DEMO_MANAGER) == grades.VIEWER, "줄 없음"
    assert grade_store.grade_of(cfg, DEMO_DEVELOPER) == grades.DEVELOPER, "개발자는 명단이 정한다"


def test_without_the_s3_list_only_developers_are_above_viewer() -> None:
    cfg = use_config({names.ENV_ACCESS_ADMINS: DEMO_DEVELOPER, names.ENV_ACCESS_USERS: DEMO_EDITOR})
    assert not access_store.is_on(cfg)
    assert grade_store.grade_of(cfg, DEMO_DEVELOPER) == grades.DEVELOPER
    assert grade_store.grade_of(cfg, DEMO_EDITOR) == grades.VIEWER
    assert grade_store.read_problem(cfg) is None


def test_no_file_and_no_mark_is_no_grades_yet_without_an_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = operational_grades(monkeypatch, grade_file=False)
    assert grade_store.read_problem(cfg) is None
    assert not grade_store.is_unread(cfg)
    assert grade_store.grade_of(cfg, DEMO_MANAGER) == grades.VIEWER
    assert grade_store.grade_of(cfg, DEMO_DEVELOPER) == grades.DEVELOPER
    _, bucket = _world()
    assert grade_store.object_key(cfg) not in bucket.objects, "첫 부팅에 적어 두지 않는다"  # type: ignore[attr-defined]


def test_a_mark_without_the_file_is_unreadable_and_narrows_to_viewer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = operational_grades(monkeypatch)
    _, bucket = _world()
    del bucket.objects[grade_store.object_key(cfg)]  # type: ignore[attr-defined]
    runtime.publish_grade_source(replace(runtime.grade_source() or GradeSource()))
    runtime.publish_grade_source(GradeSource())
    grade_store.read_at_start(cfg)

    problem = grade_store.read_problem(cfg)
    assert problem is not None and problem.kind == access_store.KIND_FILE_GONE
    assert grade_store.is_unread(cfg)
    assert grade_store.grade_of(cfg, DEMO_MANAGER) == grades.VIEWER
    assert grade_store.grade_of(cfg, DEMO_DEVELOPER) == grades.DEVELOPER


def test_after_one_good_read_a_vanished_file_keeps_the_remembered_grades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = operational_grades(monkeypatch)
    _, bucket = _world()
    del bucket.objects[grade_store.object_key(cfg)]  # type: ignore[attr-defined]
    with access_store._IO_LOCK:
        problem = grade_store._read_locked(cfg, int(time.time()))
    assert problem is not None and problem.kind == access_store.KIND_FILE_GONE
    assert not grade_store.is_unread(cfg)
    assert grade_store.grade_of(cfg, DEMO_MANAGER) == grades.MANAGER


def test_a_failed_start_read_retries_on_login_once_a_minute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = operational_grades(monkeypatch)
    _, bucket = _world()
    runtime.publish_grade_source(GradeSource())
    bucket.fail("get", grade_store.object_key(cfg))  # type: ignore[attr-defined]
    grade_store.read_at_start(cfg, now=1000)
    assert grade_store.is_unread(cfg)

    bucket.heal()  # type: ignore[attr-defined]
    grade_store.retry_unread(cfg, now=1030)
    assert grade_store.is_unread(cfg), "60초 안에는 다시 읽지 않는다"
    grade_store.retry_unread(cfg, now=1061)
    assert not grade_store.is_unread(cfg)
    assert grade_store.grade_of(cfg, DEMO_EDITOR) == grades.EDITOR


def test_a_read_failure_leaves_a_system_audit_line(
    monkeypatch: pytest.MonkeyPatch, audit_on: list[object]
) -> None:
    cfg = operational_grades(monkeypatch)
    _, bucket = _world()
    bucket.fail("get", grade_store.object_key(cfg))  # type: ignore[attr-defined]
    grade_store.read_at_start(cfg)
    lines = [line for line in recorder.take_pending() if line["ev"] == "sys_grade_read_fail"]
    assert lines and lines[-1]["det"]["reason"] == s3_small.KIND_UNREACHABLE


# ------------------------------------------------------------------ 쓰는 차례
def test_between_viewer_editor_and_manager_only_the_grade_file_is_written(
    monkeypatch: pytest.MonkeyPatch, audit_on: list[object]
) -> None:
    cfg = operational_grades(monkeypatch)
    listed = runtime.access_source()
    assert listed is not None and listed.document is not None
    before = listed.document.revision

    result = grade_store.change_grades(
        cfg, _identity(DEMO_DEVELOPER), {DEMO_VIEWER: grades.MANAGER, DEMO_EDITOR: grades.VIEWER}
    )

    assert result.graded == 2 and result.second_failed is None
    assert grade_store.grade_of(cfg, DEMO_VIEWER) == grades.MANAGER
    assert grade_store.grade_of(cfg, DEMO_EDITOR) == grades.VIEWER
    source = runtime.grade_source()
    assert source is not None and source.document is not None
    assert source.document.line_of(DEMO_EDITOR) is None, "열람 = 줄 없음"
    after = runtime.access_source()
    assert after is not None and after.document is not None and after.document.revision == before
    changed = [line for line in recorder.take_pending() if line["ev"] == "user_grade_changed"]
    assert sorted(
        (line["tgt"]["id"], line["det"]["grade_from"], line["det"]["grade_to"]) for line in changed
    ) == [
        (DEMO_EDITOR, "editor", "viewer"),
        (DEMO_VIEWER, "viewer", "manager"),
    ]


def test_to_developer_writes_only_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = operational_grades(monkeypatch)
    grade_before = runtime.grade_source()
    assert grade_before is not None and grade_before.document is not None

    grade_store.change_grades(cfg, _identity(DEMO_DEVELOPER), {DEMO_EDITOR: grades.DEVELOPER})

    assert grade_store.grade_of(cfg, DEMO_EDITOR) == grades.DEVELOPER
    after = runtime.grade_source()
    assert after is not None and after.document == grade_before.document, "등급 줄은 둔다"


def test_developer_down_writes_the_grade_file_first_then_the_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = operational_grades(monkeypatch)
    grade_store.change_grades(cfg, _identity(DEMO_DEVELOPER), {DEMO_EDITOR: grades.DEVELOPER})

    result = grade_store.change_grades(
        cfg, _identity(DEMO_DEVELOPER), {DEMO_EDITOR: grades.MANAGER}
    )

    assert result.graded == 1 and result.second_failed is None
    assert grade_store.grade_of(cfg, DEMO_EDITOR) == grades.MANAGER


def test_a_failed_list_write_after_the_grade_file_keeps_the_developer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = operational_grades(monkeypatch)
    _, bucket = _world()
    grade_store.change_grades(cfg, _identity(DEMO_DEVELOPER), {DEMO_EDITOR: grades.DEVELOPER})
    bucket.fail("put", cfg.access_object_key)  # type: ignore[attr-defined]

    result = grade_store.change_grades(
        cfg, _identity(DEMO_DEVELOPER), {DEMO_EDITOR: grades.MANAGER}
    )

    assert result.second_failed is not None
    assert grade_store.grade_of(cfg, DEMO_EDITOR) == grades.DEVELOPER, "앞 상태"


def test_a_failed_grade_file_write_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = operational_grades(monkeypatch)
    _, bucket = _world()
    bucket.fail("put", grade_store.object_key(cfg))  # type: ignore[attr-defined]

    with pytest.raises(s3_small.S3Failure):
        grade_store.change_grades(cfg, _identity(DEMO_DEVELOPER), {DEMO_VIEWER: grades.EDITOR})

    assert grade_store.grade_of(cfg, DEMO_VIEWER) == grades.VIEWER


def test_self_and_environment_developers_cannot_go_below_developer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = operational_grades(monkeypatch)
    grade_store.change_grades(cfg, _identity(DEMO_DEVELOPER), {DEMO_EDITOR: grades.DEVELOPER})
    with pytest.raises(access_store.SelfChangeError):
        grade_store.change_grades(cfg, _identity(DEMO_EDITOR), {DEMO_EDITOR: grades.MANAGER})
    with pytest.raises(access_store.EnvAdminError):
        grade_store.change_grades(
            cfg,
            _identity(DEMO_EDITOR),
            {DEMO_VIEWER: grades.EDITOR, DEMO_DEVELOPER: grades.MANAGER},
        )
    assert grade_store.grade_of(cfg, DEMO_VIEWER) == grades.VIEWER, "섞이면 통째 거절"


def test_only_developers_write(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = operational_grades(monkeypatch)
    with pytest.raises(access_store.NotAdminError):
        grade_store.change_grades(cfg, _identity(DEMO_MANAGER), {DEMO_VIEWER: grades.EDITOR})
    with pytest.raises(access_store.NotAdminError):
        grade_store.change_grades(cfg, None, {DEMO_VIEWER: grades.EDITOR})


def test_adding_people_writes_the_list_then_the_grade_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = operational_grades(monkeypatch)
    result = grade_store.add_people(cfg, _identity(DEMO_DEVELOPER), [NEWCOMER], grades.EDITOR)
    assert result.added == 1 and result.second_failed is None
    assert grade_store.grade_of(cfg, NEWCOMER) == grades.EDITOR

    developer = grade_store.add_people(
        cfg, _identity(DEMO_DEVELOPER), ["demo.second"], grades.DEVELOPER
    )
    assert developer.added == 1
    assert grade_store.grade_of(cfg, "demo.second") == grades.DEVELOPER


def test_a_failed_grade_write_after_adding_reads_as_viewer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = operational_grades(monkeypatch)
    _, bucket = _world()
    bucket.fail("put", grade_store.object_key(cfg))  # type: ignore[attr-defined]

    result = grade_store.add_people(cfg, _identity(DEMO_DEVELOPER), [NEWCOMER], grades.MANAGER)

    assert result.added == 1 and result.second_failed is not None
    assert access_store.is_admin(cfg, NEWCOMER) is False
    assert grade_store.grade_of(cfg, NEWCOMER) == grades.VIEWER, "좁은 쪽"


def test_removing_people_clears_their_lines_and_a_failed_clear_is_harmless(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = operational_grades(monkeypatch)
    _, bucket = _world()
    bucket.fail("put", grade_store.object_key(cfg))  # type: ignore[attr-defined]

    result = grade_store.remove_people(cfg, _identity(DEMO_DEVELOPER), [DEMO_MANAGER])

    assert result.removed == 1 and result.second_failed is not None
    bucket.heal()  # type: ignore[attr-defined]
    grade_store.add_people(cfg, _identity(DEMO_DEVELOPER), [DEMO_MANAGER], grades.VIEWER)
    assert grade_store.grade_of(cfg, DEMO_MANAGER) == grades.VIEWER, "다시 들면 옛 줄을 버린다"


@pytest.mark.parametrize("grade", [grades.VIEWER, grades.EDITOR])
def test_a_person_readded_in_the_same_second_never_inherits_the_leftover_line(
    monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    """관리자로 넣고 · 빼기의 둘째 쓰기(줄 지움)가 실패해 줄이 남은 채 · 같은 초에 다시 넣으면 등록
    시각(초 단위 글)이 옛 줄과 같다 — 그래도 옛 관리자를 이어받지 않는다(넣기가 남은 줄을 명단 쓰기
    앞에서 먼저 지운다)."""
    cfg = operational_grades(monkeypatch)
    _, bucket = _world()
    moment = int(time.time())
    developer = _identity(DEMO_DEVELOPER)
    grade_store.add_people(cfg, developer, [NEWCOMER], grades.MANAGER, now=moment)
    assert grade_store.grade_of(cfg, NEWCOMER) == grades.MANAGER
    bucket.fail("put", grade_store.object_key(cfg))  # type: ignore[attr-defined]
    removed = grade_store.remove_people(cfg, developer, [NEWCOMER], now=moment)
    assert removed.second_failed is not None, "남은 줄을 짓는다"
    bucket.heal()  # type: ignore[attr-defined]

    result = grade_store.add_people(cfg, developer, [NEWCOMER], grade, now=moment)

    assert result.added == 1 and result.second_failed is None
    assert grade_store.grade_of(cfg, NEWCOMER) == grade, "옛 관리자를 이어받지 않는다"


def test_a_failed_leftover_clear_adds_nobody(monkeypatch: pytest.MonkeyPatch) -> None:
    """남은 줄을 먼저 지우지 못하면 아무도 넣지 않는다(앞 상태 — 명단 · 등급 파일 그대로)."""
    cfg = operational_grades(monkeypatch)
    _, bucket = _world()
    bucket.fail("put", grade_store.object_key(cfg))  # type: ignore[attr-defined]
    grade_store.remove_people(cfg, _identity(DEMO_DEVELOPER), [DEMO_MANAGER])
    listed = runtime.access_source()
    assert listed is not None and listed.document is not None
    before = listed.document.revision

    with pytest.raises(s3_small.S3Failure):
        grade_store.add_people(cfg, _identity(DEMO_DEVELOPER), [DEMO_MANAGER], grades.VIEWER)

    after = runtime.access_source()
    assert after is not None and after.document is not None
    assert after.document.revision == before
    assert DEMO_MANAGER not in {entry.loginid for entry in after.document.entries}


def test_people_added_or_self_registered_always_carry_a_registration_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """옛 파일 · 환경변수 첫 판 항목은 등록 시각이 빈 글자이고 그 사람의 등급 줄도 빈 글자로
    적힌다. 빠졌다 다시 드는 길(「명단에 넣기」 · 「접속 권한 신청」)은 늘 새 시각을 매기므로 빈
    글자 줄이 다시 맞지 않는다."""
    cfg = operational_grades(monkeypatch)
    for loginid in ("demo.again", NEWCOMER):
        grade_store.add_people(cfg, _identity(DEMO_DEVELOPER), [loginid], grades.VIEWER)
    access_store.register_self(cfg, "demo.self")
    listed = runtime.access_source()
    assert listed is not None and listed.document is not None
    stamps = {entry.loginid: entry.added_at for entry in listed.document.entries}
    assert all(stamps[key] for key in ("demo.again", NEWCOMER, "demo.self")), stamps


def test_self_registration_reads_as_viewer(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = operational_grades(monkeypatch)
    access_store.register_self(cfg, NEWCOMER)
    assert grade_store.grade_of(cfg, NEWCOMER) == grades.VIEWER


def test_the_mark_is_left_by_the_first_grade_file_write(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = operational_grades(monkeypatch, grade_file=False)
    _, bucket = _world()
    assert grade_store.mark_key(cfg) not in bucket.objects  # type: ignore[attr-defined]

    grade_store.change_grades(cfg, _identity(DEMO_DEVELOPER), {DEMO_EDITOR: grades.EDITOR})

    assert grade_store.mark_key(cfg) in bucket.objects  # type: ignore[attr-defined]
    assert grade_store.grade_of(cfg, DEMO_EDITOR) == grades.EDITOR


def test_reread_reads_the_list_and_the_grade_file(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = operational_grades(monkeypatch)
    _, bucket = _world()
    changed = GradeDocument(
        revision=9, lines=(GradeLine(DEMO_VIEWER, grades.MANAGER, ADDED_AT, DEMO_DEVELOPER),)
    )
    bucket.put(None, grade_store.object_key(cfg), grade_store.render_document(changed))  # type: ignore[attr-defined]

    listed, graded = grade_store.reread(cfg, _identity(DEMO_DEVELOPER))

    assert listed is None and graded is None
    assert grade_store.grade_of(cfg, DEMO_VIEWER) == grades.MANAGER
    with pytest.raises(access_store.NotAdminError):
        grade_store.reread(cfg, _identity(DEMO_MANAGER))


# ------------------------------------------------------------------ 되돌림
def _old_code_rewrites(cfg: object, document: ListDocument) -> None:
    """앞 판 코드가 명단 파일을 다시 쓴 꼴 — 등급 파일은 건드리지 않는다."""
    world = current_world()
    assert world is not None
    world.bucket.put(None, world.cfg.access_object_key, access_list_v1.render_document(document))
    access_store.reread(world.cfg, _identity(DEMO_DEVELOPER))


def test_after_a_rollback_rewrite_the_same_registration_keeps_its_grade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """앞 코드가 user → admin → user 로 바꾼 사람은 등록 시각이 같아 옛 줄로 돌아온다."""
    cfg = operational_grades(monkeypatch)
    listed = runtime.access_source()
    assert listed is not None and listed.document is not None
    moment = int(time.time())
    promoted = access_list_v1.changed_document(
        listed.document, DEMO_DEVELOPER, moment=moment, grades={DEMO_EDITOR: GRADE_ADMIN}
    )
    demoted = access_list_v1.changed_document(
        promoted, DEMO_DEVELOPER, moment=moment, grades={DEMO_EDITOR: "user"}
    )
    _old_code_rewrites(cfg, demoted)
    assert grade_store.grade_of(cfg, DEMO_EDITOR) == grades.EDITOR


def test_after_a_rollback_a_removed_and_readded_person_starts_as_viewer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = operational_grades(monkeypatch)
    listed = runtime.access_source()
    assert listed is not None and listed.document is not None
    later = int(time.time()) + 3600
    removed = access_list_v1.changed_document(
        listed.document, DEMO_DEVELOPER, moment=later, remove=[DEMO_MANAGER]
    )
    readded = access_list_v1.changed_document(
        removed, DEMO_DEVELOPER, moment=later + 60, add=[DEMO_MANAGER]
    )
    joined = access_list_v1.register_self(readded, NEWCOMER, moment=later + 120)
    _old_code_rewrites(cfg, joined)
    assert grade_store.grade_of(cfg, DEMO_MANAGER) == grades.VIEWER
    assert grade_store.grade_of(cfg, NEWCOMER) == grades.VIEWER
    assert grade_store.grade_of(cfg, DEMO_EDITOR) == grades.EDITOR, "다른 사람은 그대로"


def test_the_new_code_never_writes_new_grade_values_into_the_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """명단 파일의 등급 칸은 `user` · `admin` 그대로다 — 앞 코드가 읽을 수 있게."""
    cfg = operational_grades(monkeypatch)
    _, bucket = _world()
    grade_store.change_grades(cfg, _identity(DEMO_DEVELOPER), {DEMO_VIEWER: grades.MANAGER})
    grade_store.add_people(cfg, _identity(DEMO_DEVELOPER), [NEWCOMER], grades.EDITOR)
    body, _ = bucket.objects[cfg.access_object_key]  # type: ignore[attr-defined]
    document = access_store.parse_document(body)
    assert {entry.grade for entry in document.entries} <= {"user", "admin"}
    assert document.demoted == 0
