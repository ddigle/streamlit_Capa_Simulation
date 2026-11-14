# Purpose: 명단 파일의 이름·부서·등급 칸과 스스로 등록·등급 바꿈 쓰기(합침·규칙·감사)를 지킨다.

"""S3 명단의 스스로 등록 · 관리자 등급(`auth/access_store`).

값은 모두 합성(`demo.*`)이고 저장소는 서명을 검증하는 가짜 S3(`scripts/s3_mock_store.py`)다.
겹침 시험은 가짜 S3 의 답 늦추기(`answer_delay`)로 두 쓰기가 실제로 겹치게 하고, 메모리가 아니라
**저장소의 객체**를 본다.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from test_sso_access_s3 import (
    ADMIN,
    GONE,
    OBJECT,
    OTHER,
    USER,
    file_body,
    identity_of,
    problem_of,
    requests_named,
    s3_config,
    started,
)

from capa_simulation.audit import recorder
from capa_simulation.auth import access_store, names, runtime
from capa_simulation.auth.access import (
    GRADE_ADMIN,
    GRADE_USER,
    VIA_ADMIN,
    VIA_SELF,
    ListDocument,
    ListEntry,
)
from capa_simulation.components import sso_status
from capa_simulation.io import s3_small
from capa_simulation.io.s3_small import S3Failure

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from s3_mock_store import MockStore, start_mock  # noqa: E402

NEWCOMER = "demo.newcomer"


@pytest.fixture()
def mock_s3() -> Iterator[tuple[MockStore, str]]:
    store = MockStore()
    server, endpoint = start_mock(store)
    yield store, endpoint
    server.shutdown()
    server.server_close()


def stored_users(store: MockStore) -> dict[str, dict[str, str]]:
    payload = json.loads(store.objects[OBJECT].decode("utf-8"))
    return {item["loginid"]: item for item in payload["users"]}


def stored_revision(store: MockStore) -> int:
    return int(json.loads(store.objects[OBJECT].decode("utf-8"))["revision"])


@pytest.fixture()
def audit_on() -> Iterator[None]:
    """감사 기록기를 켠다 — 끄기는 공용 고정 장치(`conftest._audit_recorder_off`)가 한다."""
    recorder.start(env="cdep", version="test", inst="abcabcabcabc")
    yield


def audit_lines(event: str) -> list[dict[str, object]]:
    return [line for line in recorder.take_pending() if line["ev"] == event]


# --- 파일 꼴 --------------------------------------------------------------------------------------


def test_the_new_fields_go_round_and_keep_format_one() -> None:
    document = ListDocument(
        revision=3,
        entries=(
            ListEntry(USER, USER, "2026-11-14T00:00:00Z", name="데모", dept="부서", via=VIA_SELF),
            ListEntry(OTHER, ADMIN, "2026-11-14T00:00:00Z", grade=GRADE_ADMIN),
        ),
    )

    body = access_store.render_document(document)

    assert access_store.parse_document(body) == document
    payload = json.loads(body)
    assert payload["format"] == 1, "판을 올리면 옛 ZIP 이 「모르는 형식」 — 관리자만 들어온다"
    users = {item["loginid"]: item for item in payload["users"]}
    assert users[USER]["via"] == VIA_SELF and users[USER]["name"] == "데모"
    assert users[OTHER]["grade"] == GRADE_ADMIN


def test_an_old_file_without_the_new_fields_reads_as_before() -> None:
    """옛 명단 파일(지금 꼴 — loginid · grade · added_by · added_at)은 그대로 읽힌다."""
    parsed = access_store.parse_document(file_body(USER, OTHER, revision=4))

    assert [entry.loginid for entry in parsed.entries] == [USER, OTHER]
    assert all(entry.via == VIA_ADMIN and entry.grade == GRADE_USER for entry in parsed.entries)
    assert all(entry.name == "" and entry.dept == "" for entry in parsed.entries)
    assert parsed.revision == 4 and parsed.demoted == 0


def test_an_old_reader_sees_an_admin_grade_as_a_user() -> None:
    """옛 코드는 `grade` 가 `user` 가 아니면 사용자로 읽었다 — 되돌려도 관리자가 생기지 않는다."""
    body = access_store.render_document(
        ListDocument(revision=1, entries=(ListEntry(OTHER, grade=GRADE_ADMIN),))
    )
    item = json.loads(body)["users"][0]

    assert item["grade"] != "user", "옛 코드의 판정(`!= user` 면 사용자로 내림)과 맞물리는 값"
    assert set(item) >= {"loginid", "grade", "added_by", "added_at"}


def test_control_characters_and_long_names_are_trimmed_on_read() -> None:
    body = json.dumps(
        {
            "format": 1,
            "revision": 1,
            "users": [{"loginid": USER, "name": "a\u0000b" + "x" * 300, "dept": 7}],
        }
    ).encode()

    (entry,) = access_store.parse_document(body).entries

    assert "\u0000" not in entry.name and len(entry.name) == access_store.MAX_PROFILE_LENGTH
    assert entry.dept == ""


# --- 스스로 등록 ----------------------------------------------------------------------------------


def test_self_registration_adds_a_user_with_name_dept_and_route(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)

    result = access_store.register_self(cfg, NEWCOMER, name="새 사람", dept="새 부서")

    assert result.added and result.revision == 2
    item = stored_users(store)[NEWCOMER]
    assert (item["grade"], item["via"], item["name"], item["dept"]) == (
        GRADE_USER,
        VIA_SELF,
        "새 사람",
        "새 부서",
    )
    assert item["added_by"] == NEWCOMER and item["added_at"].endswith("Z")
    assert problem_of(cfg, NEWCOMER) is None, "재시작 없이 들어온다"
    assert not access_store.is_admin(cfg, NEWCOMER)


def test_pressing_twice_writes_once(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)

    first = access_store.register_self(cfg, "Demo.Newcomer")
    puts = requests_named(store, "PUT")
    second = access_store.register_self(cfg, "demo.newcomer")

    assert first.added and not second.added
    assert requests_named(store, "PUT") == puts, "두 번째는 쓰지 않는다"
    assert stored_revision(store) == 2
    assert list(stored_users(store)).count(NEWCOMER) == 1


def test_an_admin_pressing_register_keeps_the_admin_grade(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    access_store.save_changes(cfg, identity_of(cfg, ADMIN), grades={USER: GRADE_ADMIN})
    puts = requests_named(store, "PUT")

    result = access_store.register_self(cfg, USER, name="바뀐 이름")

    assert not result.added
    assert requests_named(store, "PUT") == puts
    assert stored_users(store)[USER]["grade"] == GRADE_ADMIN
    assert stored_users(store)[USER]["name"] == ""
    assert access_store.is_admin(cfg, USER)


def test_registering_again_after_removal_is_a_plain_user(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    admin = identity_of(cfg, ADMIN)
    access_store.save_changes(cfg, admin, grades={USER: GRADE_ADMIN})
    access_store.save_changes(cfg, admin, remove=[USER])
    assert problem_of(cfg, USER) is not None

    result = access_store.register_self(cfg, USER)

    assert result.added
    assert stored_users(store)[USER]["grade"] == GRADE_USER
    assert not access_store.is_admin(cfg, USER)


def test_a_key_the_list_cannot_hold_is_refused_without_writing(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)

    with pytest.raises(access_store.RegisterRefusedError):
        access_store.register_self(cfg, "---")

    assert requests_named(store, "PUT") == 0


def test_the_first_file_is_made_by_a_registration_with_the_seed_users(
    mock_s3: tuple[MockStore, str],
) -> None:
    """빈 버킷 · 환경변수 첫 판 — 등록이 첫 판 + 그 사람으로 파일과 표지를 만든다."""
    store, endpoint = mock_s3
    cfg = s3_config(store, endpoint, CAPA_ACCESS_USERS=OTHER)
    access_store.read_at_start(cfg)
    source = runtime.access_source()
    assert source is not None and source.seeded

    result = access_store.register_self(cfg, NEWCOMER)

    assert result.revision == 1
    assert set(stored_users(store)) == {OTHER, NEWCOMER}
    assert names.ACCESS_SEEDED_OBJECT in store.objects
    payload = json.loads(store.objects[OBJECT])
    assert payload["changes"][0]["what"].startswith(access_store.CHANGE_SEED)
    assert problem_of(cfg, OTHER) is None and problem_of(cfg, NEWCOMER) is None


def test_a_vanished_file_is_not_recreated_by_a_registration(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    del store.objects[OBJECT]

    with pytest.raises(S3Failure) as caught:
        access_store.register_self(cfg, NEWCOMER)

    assert caught.value.kind == access_store.KIND_FILE_GONE
    assert OBJECT not in store.objects
    assert problem_of(cfg, USER) is None, "메모리 명단은 그대로다"


def test_a_registration_merges_onto_a_file_changed_elsewhere(
    mock_s3: tuple[MockStore, str],
) -> None:
    """그 사이 다른 곳이 바꾼 파일을 덮지 않고 그 위에 얹는다(관리자 저장은 「그 사이 바뀜」)."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    store.put(
        OBJECT,
        json.dumps(
            {
                "format": 1,
                "revision": 9,
                "users": [
                    {"loginid": USER, "grade": GRADE_USER},
                    {"loginid": GONE, "grade": GRADE_ADMIN},
                ],
            }
        ).encode(),
    )

    result = access_store.register_self(cfg, NEWCOMER)

    assert result.revision == 10
    users = stored_users(store)
    assert set(users) == {USER, GONE, NEWCOMER}
    assert users[GONE]["grade"] == GRADE_ADMIN, "다른 곳이 준 관리자 등급을 잃지 않는다"


def test_a_failed_put_leaves_memory_and_says_why(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    store.force["PUT"] = (403, "AccessDenied")

    with pytest.raises(S3Failure):
        access_store.register_self(cfg, NEWCOMER)

    assert problem_of(cfg, NEWCOMER) is not None
    source = runtime.access_source()
    assert source is not None and source.save_problem is not None


def test_a_put_with_no_answer_is_unconfirmed(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    store.answer_delay["PUT"] = 1.0
    monkeypatch.setattr(s3_small, "READ_TIMEOUT_SECONDS", 0.2)

    with pytest.raises(access_store.SaveUnconfirmedError):
        access_store.register_self(cfg, NEWCOMER)

    assert problem_of(cfg, NEWCOMER) is not None, "메모리는 그대로다"


def test_without_the_s3_list_a_registration_is_refused() -> None:
    from sso_support import use_config

    cfg = use_config()

    assert not access_store.can_register(cfg)
    with pytest.raises(access_store.StoreUnreadError):
        access_store.register_self(cfg, NEWCOMER)


def test_an_unread_list_takes_no_registration(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    store.force["GET"] = (503, "SlowDown")
    cfg = started(store, endpoint)

    assert access_store.is_unread(cfg)
    assert not access_store.can_register(cfg)
    with pytest.raises(access_store.StoreUnreadError):
        access_store.register_self(cfg, NEWCOMER)


def test_the_server_log_and_event_ring_carry_no_registrant(
    mock_s3: tuple[MockStore, str], caplog: pytest.LogCaptureFixture
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    caplog.set_level("INFO", logger=names.LOGGER_NAME)

    access_store.register_self(cfg, NEWCOMER, name="새 사람")
    store.force["PUT"] = (403, "AccessDenied")
    with pytest.raises(S3Failure):
        access_store.register_self(cfg, "demo.second")

    assert NEWCOMER not in caplog.text and "demo.second" not in caplog.text
    assert "새 사람" not in caplog.text
    for item in runtime.recent_events():
        assert NEWCOMER not in str(item.fields) and "demo.second" not in str(item.fields)


# --- 등급 바꿈 규칙 -------------------------------------------------------------------------------


def test_an_admin_gives_and_takes_the_admin_grade(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    admin = identity_of(cfg, ADMIN)

    given = access_store.save_changes(cfg, admin, grades={USER: GRADE_ADMIN})
    assert given.graded == 1 and access_store.is_admin(cfg, USER)
    assert stored_users(store)[USER]["grade"] == GRADE_ADMIN

    same = access_store.save_changes(cfg, admin, grades={USER: GRADE_ADMIN})
    assert not same.changed and same.already == 1

    taken = access_store.save_changes(cfg, admin, grades={USER: GRADE_USER})
    assert taken.graded == 1 and not access_store.is_admin(cfg, USER)


def test_a_list_admin_can_grade_others_but_not_take_their_own(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER)
    access_store.save_changes(cfg, identity_of(cfg, ADMIN), grades={USER: GRADE_ADMIN})
    list_admin = identity_of(cfg, USER)

    access_store.save_changes(cfg, list_admin, grades={OTHER: GRADE_ADMIN})
    with pytest.raises(access_store.SelfChangeError):
        access_store.save_changes(cfg, list_admin, grades={USER: GRADE_USER})
    with pytest.raises(access_store.SelfChangeError):
        access_store.save_changes(cfg, list_admin, remove=[USER])

    assert stored_users(store)[USER]["grade"] == GRADE_ADMIN
    assert access_store.is_admin(cfg, OTHER)


def test_an_environment_admin_cannot_be_taken_down_on_screen(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, ADMIN)
    access_store.save_changes(cfg, identity_of(cfg, ADMIN), grades={USER: GRADE_ADMIN})
    puts = requests_named(store, "PUT")

    with pytest.raises(access_store.EnvAdminError):
        access_store.save_changes(cfg, identity_of(cfg, USER), grades={ADMIN: GRADE_USER})

    assert requests_named(store, "PUT") == puts
    assert access_store.is_admin(cfg, ADMIN)


def test_only_two_grades_exist(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)

    with pytest.raises(ValueError):
        access_store.save_changes(cfg, identity_of(cfg, ADMIN), grades={USER: "owner"})


def test_a_plain_user_cannot_change_grades(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER)

    with pytest.raises(access_store.NotAdminError):
        access_store.save_changes(cfg, identity_of(cfg, USER), grades={OTHER: GRADE_ADMIN})


# --- 겹침(잃은 갱신 없음) ---------------------------------------------------------------------


def _together(*calls: Callable[[], object]) -> list[BaseException]:
    failures: list[BaseException] = []

    def run(call: Callable[[], object]) -> None:
        try:
            call()
        except BaseException as exc:  # noqa: BLE001 — 시험이 모은다
            failures.append(exc)

    threads = [threading.Thread(target=run, args=(call,)) for call in calls]
    for thread in threads:
        thread.start()
        time.sleep(0.02)
    for thread in threads:
        thread.join(timeout=30)
    return failures


def test_two_registrations_at_the_same_time_both_land(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    store.answer_delay["PUT"] = 0.3

    failures = _together(
        lambda: access_store.register_self(cfg, "demo.first"),
        lambda: access_store.register_self(cfg, "demo.second"),
    )

    assert failures == []
    assert {USER, "demo.first", "demo.second"} <= set(stored_users(store))
    assert stored_revision(store) == 3


@pytest.mark.parametrize("registration_first", [True, False])
def test_a_registration_and_a_grade_change_together_lose_nothing(
    mock_s3: tuple[MockStore, str], registration_first: bool
) -> None:
    """두 차례 모두 — 등록한 사람은 남고, 관리자 등급은 지워지지도 되살아나지도 않는다."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER)
    admin = identity_of(cfg, ADMIN)
    access_store.save_changes(cfg, admin, grades={OTHER: GRADE_ADMIN})
    store.answer_delay["PUT"] = 0.3
    register = lambda: access_store.register_self(cfg, NEWCOMER)  # noqa: E731
    grade = lambda: access_store.save_changes(  # noqa: E731
        cfg, admin, grades={USER: GRADE_ADMIN, OTHER: GRADE_USER}
    )

    failures = _together(*((register, grade) if registration_first else (grade, register)))

    assert failures == []
    users = stored_users(store)
    assert NEWCOMER in users and users[NEWCOMER]["grade"] == GRADE_USER
    assert users[USER]["grade"] == GRADE_ADMIN, "준 관리자 등급이 지워지지 않는다"
    assert users[OTHER]["grade"] == GRADE_USER, "뺀 관리자 등급이 되살아나지 않는다"
    assert stored_revision(store) == 4


# --- 감사 기록 ------------------------------------------------------------------------------------


@pytest.mark.usefixtures("audit_on")
def test_a_registration_is_audited_with_the_person_as_actor(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    recorder.take_pending()

    access_store.register_self(cfg, NEWCOMER)
    access_store.register_self(cfg, NEWCOMER)

    (line,) = audit_lines("user_self_registered")
    assert (line["actor"], line["verified"], line["out"]) == (NEWCOMER, True, "success")
    assert line["tgt"] == {"type": "loginid", "id": NEWCOMER}
    assert line["det"] == {"rev_from": 1, "rev_to": 2}


@pytest.mark.usefixtures("audit_on")
def test_a_failed_registration_is_audited_as_a_failure(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    store.force["PUT"] = (403, "AccessDenied")
    recorder.take_pending()

    with pytest.raises(S3Failure):
        access_store.register_self(cfg, NEWCOMER)

    (line,) = audit_lines("user_self_registered")
    assert line["out"] == "fail"


@pytest.mark.usefixtures("audit_on")
def test_a_grade_change_is_audited_per_person(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER)
    recorder.take_pending()

    access_store.save_changes(
        cfg, identity_of(cfg, ADMIN), grades={USER: GRADE_ADMIN, OTHER: GRADE_USER}
    )

    (line,) = audit_lines("user_grade_changed")
    assert (line["actor"], line["verified"]) == (ADMIN, True)
    assert line["tgt"] == {"type": "loginid", "id": USER}
    assert line["det"] == {"grade_from": "user", "grade_to": "admin", "rev_from": 1, "rev_to": 2}


def test_recent_self_registrations_count_and_mark_only_new_ones(
    mock_s3: tuple[MockStore, str],
) -> None:
    """알림 지문은 고친 기록의 가장 새 스스로 등록 시각 — 사람을 빼도 줄지 않는다."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    now = int(time.time())
    access_store.register_self(cfg, NEWCOMER, now=now)
    access_store.register_self(cfg, "demo.second", now=now + 5)
    source = runtime.access_source()
    assert source is not None and source.document is not None

    count, latest = access_store.recent_self_registrations(source.document, now=now + 5, days=30)
    assert count == 2 and latest

    access_store.save_changes(cfg, identity_of(cfg, ADMIN), remove=["demo.second"])
    source = runtime.access_source()
    assert source is not None and source.document is not None
    after, latest_after = access_store.recent_self_registrations(
        source.document, now=now + 5, days=30
    )
    assert after == 1 and latest_after == latest
    old, _ = access_store.recent_self_registrations(source.document, now=now + 40 * 86400, days=30)
    assert old == 0


# --- 옛 판 · 되풀이 · 딸린 일 ---------------------------------------------------------------------


def _serve_once(monkeypatch: pytest.MonkeyPatch, body: bytes) -> list[str]:
    """다음 명단 GET 한 번만 `body`(옛 판)를 돌려주는 저장소 — 덮어쓴 직후 옛 판을 주는 꼴."""
    real_get = s3_small.get_object
    served: list[str] = []

    def stale_once(
        target: s3_small.S3Target, key: str, *, moment: float | None = None
    ) -> s3_small.S3Object | None:
        if key == OBJECT and not served:
            served.append(key)
            return s3_small.S3Object(body=body, etag="stale")
        return real_get(target, key, moment=moment)

    monkeypatch.setattr(access_store, "get_object", stale_once)
    return served


@pytest.mark.parametrize("returning", [False, True])
def test_a_stale_read_neither_writes_nor_revives_a_removed_grade_or_person(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch, returning: bool
) -> None:
    """다시 받은 판이 메모리 판보다 오래되면 얹지도(쓰기) 올리지도(「이미 있음」) 않는다 — 방금 뺀
    관리자 등급 · 사람이 S3 와 메모리 어디에서도 되살아나지 않는다(리뷰 데이터 렌즈 1)."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER)
    admin = identity_of(cfg, ADMIN)
    access_store.save_changes(cfg, admin, grades={OTHER: GRADE_ADMIN})
    stale = store.objects[OBJECT]
    if returning:
        access_store.save_changes(cfg, admin, remove=[OTHER])
    else:
        access_store.save_changes(cfg, admin, grades={OTHER: GRADE_USER})
    revision = stored_revision(store)
    puts = requests_named(store, "PUT")
    served = _serve_once(monkeypatch, stale)

    with pytest.raises(access_store.StoreConflictError):
        access_store.register_self(cfg, OTHER if returning else NEWCOMER)

    assert served, "옛 판을 받은 시도다"
    assert requests_named(store, "PUT") == puts, "옛 판 위에 쓰지 않는다"
    assert stored_revision(store) == revision
    assert not access_store.is_admin(cfg, OTHER)
    source = runtime.access_source()
    assert source is not None and source.document is not None
    assert source.document.revision == revision, "옛 판을 메모리에 올리지 않는다"
    if returning:
        assert problem_of(cfg, OTHER) is not None, "뺀 사람이 옛 판으로 돌아오지 않는다"
        assert OTHER not in stored_users(store)
    else:
        assert stored_users(store)[OTHER]["grade"] == GRADE_USER


@pytest.mark.usefixtures("audit_on")
def test_a_failed_registration_stays_out_of_the_ring_and_the_automatic_lines(
    mock_s3: tuple[MockStore, str],
) -> None:
    """명단 밖 사람의 되풀이는 다른 사건을 밀어내지 못한다 — 누계만 세고, 그 사람의 누름이 자동
    행위 줄(`sys_access_save_fail` · `system:sso`)을 만들지 않는다(리뷰 데이터 렌즈 2 · 4)."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    store.force["PUT"] = (403, "AccessDenied")
    ring = len(runtime.recent_events(anonymous=False))
    recorder.take_pending()

    for _ in range(5):
        with pytest.raises(S3Failure):
            access_store.register_self(cfg, NEWCOMER)

    assert len(runtime.recent_events(anonymous=False)) == ring
    assert runtime.self_register_failures() == 5
    assert " · 스스로 등록 실패 5" in sso_status.access_s3_line(cfg), "누계는 「S3 명단」 줄에"
    pending = recorder.take_pending()
    assert [line["ev"] for line in pending].count("user_self_registered") == 5
    assert not [line for line in pending if line["ev"] == "sys_access_save_fail"]


@pytest.mark.usefixtures("audit_on")
def test_what_a_registration_rewrites_on_the_side_is_an_automatic_line(
    mock_s3: tuple[MockStore, str],
) -> None:
    """스스로 등록이 다시 쓰며 못 읽은 항목이 빠지면 그 수를 자동 행위로 남긴다(리뷰 데이터
    렌즈 3)."""
    store, endpoint = mock_s3
    store.put(
        OBJECT,
        json.dumps(
            {
                "format": 1,
                "revision": 4,
                "users": [{"loginid": USER, "grade": GRADE_USER}, {"loginid": "DOMAIN\\x"}],
            }
        ).encode(),
    )
    store.put(names.ACCESS_SEEDED_OBJECT, b'{"format": 1}')
    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)
    recorder.take_pending()

    access_store.register_self(cfg, NEWCOMER)

    (dropped,) = audit_lines("user_bulk_dropped")
    assert (dropped["actor"], dropped["verified"]) == (recorder.SYSTEM_SSO, False)
    assert dropped["det"] == {"count": 1, "rev_from": 4, "rev_to": 5}


def test_a_registration_drops_unreadable_entries_and_counts_them_without_the_audit_log(
    mock_s3: tuple[MockStore, str],
) -> None:
    """감사 기록기가 꺼진 서버에서도 — 스스로 등록이 다시 쓰며 못 읽은 항목은 파일에서 빠지고, 빠진
    수가 파일의 고친 기록(`drop_unreadable n`)과 서버 사건(`access_self_registered` 의 `dropped`)에
    남는다(물음 보드 「정한 것」 9). 사건에는 계정이 없다."""
    store, endpoint = mock_s3
    store.put(
        OBJECT,
        json.dumps(
            {
                "format": 1,
                "revision": 4,
                "users": [
                    {"loginid": USER, "grade": GRADE_USER},
                    {"loginid": "DOMAIN\\x"},
                    "demo.flat",
                ],
            }
        ).encode(),
    )
    store.put(names.ACCESS_SEEDED_OBJECT, b'{"format": 1}')
    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)
    assert runtime.current_access(cfg).unreadable_count == 2

    access_store.register_self(cfg, NEWCOMER)

    saved = json.loads(store.objects[OBJECT].decode("utf-8"))
    assert [item["loginid"] for item in saved["users"]] == [NEWCOMER, USER]
    assert [item["what"] for item in saved["changes"]] == ["self_add", "drop_unreadable 2"]
    assert runtime.current_access(cfg).unreadable_count == 0
    (event,) = [item for item in runtime.recent_events() if item.event == "access_self_registered"]
    assert event.value("dropped") == "2"
    assert event.value("revision") == "5"
    assert NEWCOMER not in " ".join(value for _key, value in event.fields)

    access_store.register_self(cfg, "demo.newcomer2")

    latest = runtime.recent_events()[0]
    assert (latest.event, latest.value("dropped")) == ("access_self_registered", "0")


@pytest.mark.usefixtures("audit_on")
def test_the_first_file_seeded_by_a_registration_is_an_automatic_line(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = s3_config(store, endpoint, CAPA_ACCESS_USERS=OTHER)
    access_store.read_at_start(cfg)
    recorder.take_pending()

    access_store.register_self(cfg, NEWCOMER)

    pending = recorder.take_pending()
    (seeded,) = [line for line in pending if line["ev"] == "user_seeded"]
    assert (seeded["actor"], seeded["verified"]) == (recorder.SYSTEM_SSO, False)
    (own,) = [line for line in pending if line["ev"] == "user_self_registered"]
    assert (own["actor"], own["verified"]) == (NEWCOMER, True)


def test_an_already_listed_press_clears_an_unconfirmed_write(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """답이 끊긴 등록이 실제로 들어갔고 다시 눌러 「이미 있음」 이면, 읽기와 같이 「쓰기 결과 모름」
    을 걷는다(리뷰 데이터 렌즈 6)."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    store.answer_delay["PUT"] = 1.0
    monkeypatch.setattr(s3_small, "READ_TIMEOUT_SECONDS", 0.2)
    with pytest.raises(access_store.SaveUnconfirmedError):
        access_store.register_self(cfg, NEWCOMER)
    time.sleep(1.0)
    store.answer_delay.clear()
    source = runtime.access_source()
    assert source is not None and source.save_problem is not None
    assert source.save_problem.unconfirmed
    assert NEWCOMER in stored_users(store), "답은 끊겼지만 들어갔다"

    again = access_store.register_self(cfg, NEWCOMER)

    assert not again.added
    source = runtime.access_source()
    assert source is not None and source.save_problem is None
    assert problem_of(cfg, NEWCOMER) is None
