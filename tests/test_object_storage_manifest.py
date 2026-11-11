# Purpose: 오브젝트 스토리지 세대 포인터 키 계약과 세대·분기·정리 판정을 검증한다.

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from capa_simulation.services import object_storage_manifest as manifest
from capa_simulation.services.object_storage_manifest import (
    BootDecision,
    ListedObject,
    Member,
    Pointer,
    PullDecision,
    PushDecision,
    WriterMark,
)

SHA_A = "a1b2c3d4" + "0" * 56
SHA_B = "b2c3d4e5" + "0" * 56
KEY_A = "generations/heads/000000000000__s000000000001__e000000000001__0000aaaa.json"
KEY_B = "generations/heads/000000000001__s000000000001__e000000000001__0000bbbb.json"
HEAD_TIME = datetime(2026, 11, 7, tzinfo=timezone.utc)


def _member(seq: int, dataset: manifest.DatasetName = "simulation", sha256: str = SHA_A) -> Member:
    return Member(
        seq=seq,
        snapshot_key=manifest.snapshot_key(
            dataset, seq, created_at_utc="2026-09-08T09:15:00Z", sha256=sha256
        ),
        sha256=sha256,
        md5_base64="bWQ1",
        size_bytes=21_524_480,
        source_db_bytes=67_383_296,
        migration_version=14,
    )


def _pointer(seq: int, *, token: str = "0000aaaa", origin: manifest.Origin = "app") -> Pointer:
    parent = None if seq == 1 else _pointer(seq - 1, token="0000bbbb")
    return manifest.next_pointer(
        parent,
        members={"simulation": _member(seq), "equipment": _member(1, "equipment", SHA_B)},
        origin=origin,
        token=token,
        app_version="0.9.0-demo",
        author="DEMO_USER@PC-1",
        created_at_utc="2026-09-08T09:15:00Z",
        note="리비전 저장",
    )


def _key(seq: int, simulation: int = 1, equipment: int = 1, token: str = "0000aaaa") -> str:
    return manifest.pointer_key(
        seq, simulation_seq=simulation, equipment_seq=equipment, token=token
    )


def _snapshot(dataset: manifest.DatasetName, seq: int) -> str:
    return manifest.snapshot_key(dataset, seq, created_at_utc="2026-09-08T09:15:00Z", sha256=SHA_A)


def test_descending_pointer_keys_sort_newest_first() -> None:
    """`list --max-keys N` 한 번이 항상 최신 N 개여야 한다. 그래서 내림차순이다."""
    keys = [_key(seq) for seq in (1, 2, 41, 42)]

    assert sorted(keys)[0] == _key(42)
    assert manifest.seq_from_pointer_key(sorted(keys)[0]) == 42


def test_pointer_key_round_trips_the_sequence_and_the_member_sequences() -> None:
    """정리는 포인터를 GET 하지 않는다 — 어느 스냅샷을 가리키는지 키에서 읽는다."""
    for seq in (0, 1, 999, 10**6, manifest.SEQUENCE_SPACE):
        key = _key(seq, simulation=7, equipment=3, token="0123abcd")
        assert manifest.seq_from_pointer_key(key) == seq
        assert manifest.member_seqs_from_pointer_key(key) == {"simulation": 7, "equipment": 3}


def test_snapshot_key_sorts_by_sequence_not_by_clock() -> None:
    """두 PC 의 시계가 어긋나도 목록 정렬이 저장 순서를 뒤집지 않아야 한다."""
    older_clock = manifest.snapshot_key(
        "simulation", 42, created_at_utc="2026-01-01T00:00:00Z", sha256=SHA_A
    )
    newer_clock = manifest.snapshot_key(
        "simulation", 41, created_at_utc="2030-01-01T00:00:00Z", sha256=SHA_B
    )

    assert sorted([older_clock, newer_clock])[-1] == older_clock
    assert manifest.parse_snapshot_key(older_clock)[0] == 42


def test_snapshot_key_rejects_a_malformed_timestamp() -> None:
    with pytest.raises(ValueError, match="UTC 시각 형식"):
        manifest.snapshot_key("simulation", 1, created_at_utc="2026-09-08 09:15", sha256=SHA_A)


def test_pointer_token_must_be_eight_hex_digits() -> None:
    """토큰이 자유 문자열이면 두 클라이언트가 같은 키를 만들 수 있다."""
    with pytest.raises(ValueError, match="16진수 8자리"):
        _key(1, token="not-hex!")


def test_head_selection_is_deterministic_when_two_pointers_share_a_sequence() -> None:
    """분기 상황에서도 모든 PC 가 같은 것을 HEAD 로 봐야 한다."""
    first = _key(42, token="0000aaaa")
    second = _key(42, token="ffffbbbb")

    assert manifest.select_head_key([second, first]) == first
    assert manifest.select_head_key([first, second]) == first


def test_fork_is_detected_only_at_the_top_sequence() -> None:
    top_a = _key(42, token="0000aaaa")
    top_b = _key(42, token="ffffbbbb")
    older = _key(41, token="1111cccc")

    assert manifest.detect_fork([top_a, top_b, older]) == (top_a, top_b)
    assert manifest.detect_fork([top_a, older]) == ()
    assert manifest.detect_fork([]) == ()


def test_keys_of_another_shape_are_not_pointers() -> None:
    assert manifest.select_head_key(["generations/heads/x.json", "access/access_list.json"]) is None


def test_pointer_json_round_trips() -> None:
    pointer = _pointer(1)

    restored = manifest.pointer_from_json(
        manifest.pointer_to_json(pointer), pointer_key=pointer.pointer_key
    )

    assert restored == pointer


def test_unknown_pointer_schema_is_refused_instead_of_guessed() -> None:
    """앞으로 스키마가 바뀌면 옛 배포본이 조용히 잘못 읽는 것이 가장 나쁘다."""
    with pytest.raises(ValueError, match="포인터 스키마"):
        manifest.pointer_from_json('{"schema": 1, "seq": 1}', pointer_key="k")


def test_a_pointer_without_both_members_is_refused() -> None:
    """두 DB 는 한 쌍이다. 한쪽만 가리키는 세대를 받으면 어긋난 쌍이 선다."""
    text = manifest.pointer_to_json(_pointer(1)).replace('"equipment"', '"other"')

    with pytest.raises(ValueError, match="두 DB 멤버"):
        manifest.pointer_from_json(text, pointer_key="k")


def test_next_pointer_chains_the_parent_pointer_key() -> None:
    """부모 키가 체인의 근거다. 시계도 조건부 쓰기도 필요 없다."""
    child = _pointer(2)

    assert child.seq == 2
    assert child.parent_seq == 1
    assert child.parent_pointer_key == _pointer(1, token="0000bbbb").pointer_key
    assert manifest.member_seqs_from_pointer_key(child.pointer_key) == {
        "simulation": 2,
        "equipment": 1,
    }


def test_writer_takeover_follows_the_origin_of_the_head() -> None:
    """운영 앱이 포인터를 낸 뒤에는 사내 PC 가 쓰지 못한다 — 시작 펜스부터다."""
    assert manifest.writer_taken_over(None) is False
    assert manifest.writer_taken_over(_pointer(1, origin="init")) is False
    assert manifest.writer_taken_over(_pointer(1, origin="manual")) is False
    assert manifest.writer_taken_over(_pointer(1, origin="boot")) is True
    assert manifest.writer_taken_over(_pointer(1, origin="app")) is True
    assert manifest.writer_taken_over(_pointer(1, origin="rollback")) is True


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"unpublished": True, "forked": True, "head_key": None}, PushDecision.BLOCKED_UNPUBLISHED),
        ({"forked": True, "head_key": None}, PushDecision.FORKED),
        ({"head_key": None, "base_pointer_key": None}, PushDecision.REMOTE_EMPTY),
        ({"base_pointer_key": None}, PushDecision.UNKNOWN_BASE),
        ({"base_pointer_key": KEY_B}, PushDecision.PARENT_MOVED),
        ({"dirty": False}, PushDecision.UP_TO_DATE),
        ({}, PushDecision.PUBLISH),
    ],
)
def test_push_decision_order_is_the_contract(
    kwargs: dict[str, object], expected: PushDecision
) -> None:
    """판정 차례가 계약이다. 세대를 모르는 DB 가 HEAD 를 덮지 않고, 빈 원격은 앱이 채우지 않는다."""
    arguments: dict[str, object] = {
        "head_key": KEY_A,
        "forked": False,
        "base_pointer_key": KEY_A,
        "dirty": True,
        "unpublished": False,
        **kwargs,
    }

    assert manifest.decide_push(**arguments) is expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"head_key": None}, PullDecision.REMOTE_EMPTY),
        ({"forked": True}, PullDecision.BLOCKED_FORKED),
        ({"dirty": True, "base_pointer_key": KEY_B}, PullDecision.BLOCKED_DIRTY),
        ({"unpublished": True}, PullDecision.BLOCKED_DIRTY),
        ({"local_exists": False, "base_pointer_key": None}, PullDecision.LOCAL_MISSING),
        ({"base_pointer_key": None}, PullDecision.AMBIGUOUS),
        ({"base_pointer_key": KEY_A}, PullDecision.UP_TO_DATE),
        ({"base_pointer_key": KEY_B}, PullDecision.DOWNLOAD),
    ],
)
def test_pull_never_overwrites_local_only_changes(
    kwargs: dict[str, object], expected: PullDecision
) -> None:
    arguments: dict[str, object] = {
        "head_key": KEY_A,
        "forked": False,
        "base_pointer_key": KEY_A,
        "local_exists": True,
        "dirty": False,
        "unpublished": False,
        **kwargs,
    }

    assert manifest.decide_pull(**arguments) is expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"local_exists": False, "base_pointer_key": None}, BootDecision.DOWNLOAD),
        ({"base_pointer_key": KEY_A, "dirty": False}, BootDecision.KEEP),
        ({"base_pointer_key": KEY_B, "dirty": False}, BootDecision.DOWNLOAD),
        ({"base_pointer_key": KEY_A, "dirty": True}, BootDecision.KEEP),
        ({"base_pointer_key": KEY_B, "dirty": True}, BootDecision.DIVERGED),
        ({"base_pointer_key": None, "dirty": True}, BootDecision.DOWNLOAD),
        ({"head_key": None}, BootDecision.REMOTE_EMPTY),
        ({"forked": True}, BootDecision.FORKED),
    ],
)
def test_boot_decision_table(kwargs: dict[str, object], expected: BootDecision) -> None:
    """받기 표 8갈래. 세대 없는 DB 는 빈 시드뿐이라 덮고, 변경이 있는데 어긋나면 머문다."""
    arguments: dict[str, object] = {
        "head_key": KEY_A,
        "forked": False,
        "base_pointer_key": KEY_A,
        "local_exists": True,
        "dirty": False,
        "state_unreadable": False,
        **kwargs,
    }

    assert manifest.decide_boot(**arguments) is expected  # type: ignore[arg-type]


def test_an_unreadable_state_file_is_not_the_same_as_a_missing_one() -> None:
    """깨진 상태 파일은 「모름」 이 아니다. 변경이 있을 수 있어 덮지 않고 머문다."""
    decision = manifest.decide_boot(
        head_key=KEY_A,
        forked=False,
        base_pointer_key=None,
        local_exists=True,
        dirty=False,
        state_unreadable=True,
    )

    assert decision is BootDecision.DIVERGED


def test_migration_version_comparison_flags_a_newer_file() -> None:
    """받은 파일이 더 최신이면 이 배포본은 그 DB 를 열면 안 된다."""
    assert manifest.compare_migration_version(file_version=15, code_version=14) == "newer"
    assert manifest.compare_migration_version(file_version=13, code_version=14) == "older"
    assert manifest.compare_migration_version(file_version=14, code_version=14) == "ok"


def _listed(key: str, days_old: float = 0.0) -> ListedObject:
    return ListedObject(key, HEAD_TIME - timedelta(days=days_old))


def _generations(
    count: int, *, days_each: float = 1.0
) -> tuple[list[ListedObject], list[ListedObject]]:
    """세대 1 ~ count — 세대마다 시뮬만 바뀌고 설비는 세대 1 을 이어 적는다."""
    pointers = []
    snapshots = [_listed(_snapshot("equipment", 1), (count - 1) * days_each)]
    for seq in range(1, count + 1):
        age = (count - seq) * days_each
        pointers.append(_listed(_key(seq, simulation=seq, equipment=1), age))
        snapshots.append(_listed(_snapshot("simulation", seq), age))
    return pointers, snapshots


def test_prune_keeps_head_the_latest_generations_and_seven_days() -> None:
    pointers, snapshots = _generations(12)

    plan = manifest.prune_generations(pointers=pointers, snapshots=snapshots)

    # 12세대가 하루 간격이면 HEAD 기준 7일 안은 세대 5 ~ 12 이다. 최신 5세대는 그 안에 있다.
    assert plan.kept_generations == 8
    assert plan.snapshots == tuple(_snapshot("simulation", seq) for seq in range(1, 5))
    assert plan.pointers == tuple(_key(seq, seq, 1) for seq in range(1, 5))


def test_prune_keeps_five_generations_even_when_they_are_all_old() -> None:
    """한동안 저장이 없어도 최신 5세대는 남는다. 나이는 HEAD 에서 재므로 시계가 흘러도 그대로다."""
    pointers, snapshots = _generations(8, days_each=30.0)

    plan = manifest.prune_generations(pointers=pointers, snapshots=snapshots)

    assert plan.kept_generations == 5
    assert plan.pointers == tuple(_key(seq, seq, 1) for seq in range(1, 4))


def test_the_seven_day_edge_is_kept() -> None:
    pointers = [_listed(_key(1, 1, 1), 7), _listed(_key(2, 2, 1), 0)]
    snapshots = [_listed(_snapshot("simulation", 1), 7)]

    plan = manifest.prune_generations(pointers=pointers, snapshots=snapshots, keep_last=1)

    assert plan.pointers == ()


def test_a_carried_member_outlives_the_generation_that_made_it() -> None:
    """이어 적은 설비 스냅샷은 그 세대가 지워져도 남은 세대가 가리키면 지킨다."""
    pointers, snapshots = _generations(12)

    plan = manifest.prune_generations(pointers=pointers, snapshots=snapshots)

    assert _snapshot("equipment", 1) not in plan.snapshots


def test_orphans_are_kept_unless_explicitly_included_and_old() -> None:
    """고아 스냅샷이 '유실 불가' 의 근거다. 정리가 그것부터 지우면 안 된다."""
    pointers, snapshots = _generations(2)
    young = _snapshot("simulation", 90)
    old = _snapshot("simulation", 91)
    snapshots += [_listed(young, 2), _listed(old, 8)]

    protected = manifest.prune_generations(pointers=pointers, snapshots=snapshots)
    included = manifest.prune_generations(
        pointers=pointers, snapshots=snapshots, include_orphans=True
    )

    assert protected.snapshots == ()
    assert protected.protected_orphans == 2
    assert included.snapshots == (old,)
    assert included.protected_orphans == 1


def test_generations_of_the_same_pair_count_once() -> None:
    """저장 없는 시작이 되풀이되면 같은 멤버의 펜스 세대만 쌓인다. 그것으로 5세대가 차지 않는다."""
    pointers = [_listed(_key(seq, seq, 1), 40) for seq in range(1, 5)]
    pointers += [_listed(_key(seq, 4, 1), 30) for seq in range(5, 15)]
    snapshots = [_listed(_snapshot("simulation", seq), 40) for seq in range(1, 5)]
    pointers[-1] = _listed(_key(14, 4, 1), 0)

    plan = manifest.prune_generations(pointers=pointers, snapshots=snapshots)

    assert (
        _key(1, 1, 1)
        in manifest.prune_generations(pointers=pointers, snapshots=snapshots, keep_last=3).pointers
    )
    assert plan.snapshots == ()


def test_a_forked_remote_is_not_pruned() -> None:
    """갈라진 원격은 사람이 볼 물증이다."""
    pointers, snapshots = _generations(12)
    pointers.append(_listed(_key(12, 12, 1, token="ffffbbbb")))

    assert manifest.prune_generations(pointers=pointers, snapshots=snapshots).total == 0


def test_prune_works_from_a_long_listing_within_the_delete_limit() -> None:
    """지울 것이 상한을 넘으면 나눠 지운다. 포인터는 그 스냅샷이 다 지워질 때만 함께 간다."""
    pointers, snapshots = _generations(2345)

    plan = manifest.prune_generations(pointers=pointers, snapshots=snapshots)

    assert len(plan.snapshots) + len(plan.pointers) == manifest.PRUNE_DELETE_LIMIT
    assert plan.pointers == ()
    assert plan.deferred == 2 * (2345 - 8) - manifest.PRUNE_DELETE_LIMIT


def test_a_snapshot_is_deleted_before_its_pointer_within_one_plan() -> None:
    pointers, snapshots = _generations(100)

    plan = manifest.prune_generations(pointers=pointers, snapshots=snapshots, limit=150)

    assert len(plan.snapshots) == 92
    seqs = {manifest.seq_from_pointer_key(key) for key in plan.pointers}
    gone = {manifest.parse_snapshot_key(key)[0] for key in plan.snapshots}
    assert seqs <= gone


def test_a_snapshot_sharing_a_generation_number_is_never_doomed() -> None:
    """경합에서 진 쪽의 스냅샷도 같은 번호다. 키에는 번호뿐이라 어느 쪽이 참조인지 모른다."""
    pointers, snapshots = _generations(12)
    winner = _snapshot("simulation", 2)
    loser = manifest.snapshot_key(
        "simulation", 2, created_at_utc="2026-01-01T00:00:00Z", sha256="b" * 64
    )
    assert loser != winner
    snapshots.append(_listed(loser, 10))

    plan = manifest.prune_generations(pointers=pointers, snapshots=snapshots)

    assert winner not in plan.snapshots
    assert loser not in plan.snapshots
    assert _snapshot("simulation", 1) in plan.snapshots
    assert plan.protected_orphans == 2


def test_orphans_sharing_a_number_can_still_be_cleared_on_request() -> None:
    """가리키는 포인터가 사라지면 진짜 고아다. 기본은 지키고 사람이 고르면 지운다."""
    pointers, snapshots = _generations(12)
    gone = _snapshot("simulation", 90)
    twin = manifest.snapshot_key(
        "simulation", 90, created_at_utc="2026-01-01T00:00:00Z", sha256="b" * 64
    )
    snapshots += [_listed(gone, 30), _listed(twin, 30)]

    kept = manifest.prune_generations(pointers=pointers, snapshots=snapshots)
    cleared = manifest.prune_generations(
        pointers=pointers, snapshots=snapshots, include_orphans=True
    )

    assert gone not in kept.snapshots and twin not in kept.snapshots
    assert gone in cleared.snapshots and twin in cleared.snapshots


def test_keys_outside_the_generation_shapes_are_never_touched() -> None:
    """접속 명단 · 모듈 데이터(모듈이 창구 도우미로 올린 `modules/<id>/` — 2026-11-12 「도우미
    함수로」)는 목록에 섞여 들어와도 지우지 않는다."""
    pointers, snapshots = _generations(12)
    snapshots.append(_listed("access/access_list.json", 400))
    snapshots.append(_listed("modules/demo_x/a.csv", 400))

    plan = manifest.prune_generations(pointers=pointers, snapshots=snapshots, include_orphans=True)

    assert "access/access_list.json" not in plan.snapshots
    assert "modules/demo_x/a.csv" not in plan.snapshots
    assert all(prefix.endswith("/") for prefix in manifest.PRUNE_PREFIXES)
    for kept in ("access", "modules"):
        assert not any(prefix.startswith(kept) for prefix in manifest.PRUNE_PREFIXES)


def test_no_head_means_nothing_to_prune() -> None:
    assert manifest.prune_generations(pointers=[], snapshots=[]).total == 0


def test_prune_rejects_keeping_nothing() -> None:
    with pytest.raises(ValueError, match="1 이상"):
        manifest.prune_generations(pointers=[], snapshots=[], keep_last=0)


def test_writer_age_uses_server_time_only() -> None:
    """PC 시계가 어긋나면 조언이 거짓말이 된다. 인자에 클라이언트 시각 자리가 없다."""
    mark = WriterMark(
        schema=1,
        database="simulation",
        owner="DEMO_USER@PC-77",
        instance_id="abc",
        started_at_utc="2026-09-08T09:00:00Z",
        app_version="0.9.0-demo",
    )
    now = datetime(2026, 9, 8, 9, 12, tzinfo=timezone.utc)

    message = manifest.writer_age_message(
        mark, last_modified=now - timedelta(minutes=12), server_now=now
    )

    assert "12분 전" in message
    assert "PC-77" in message
    assert manifest.writer_age_message(None, last_modified=now, server_now=now) == ""


def test_decision_messages_are_korean_and_name_the_generation() -> None:
    message = manifest.decision_message(PushDecision.PARENT_MOVED, head_seq=1)

    assert "seq 1" in message
    assert "로컬 저장은 그대로" in message


def test_pull_messages_pick_the_particle_by_the_last_sound() -> None:
    """값 뒤 조사는 끝소리로 고른다 — 「seq 2 을」·「seq 3 로」가 아니다."""
    assert "원격 seq 2로 내려받습니다" in manifest.decision_message(
        PullDecision.DOWNLOAD, head_seq=2
    )
    assert "원격 seq 3으로 내려받습니다" in manifest.decision_message(
        PullDecision.DOWNLOAD, head_seq=3
    )
    assert "원격 seq 2를 받습니다" in manifest.decision_message(
        PullDecision.LOCAL_MISSING, head_seq=2
    )


def test_push_and_pull_messages_do_not_collide_on_shared_enum_values() -> None:
    """두 열거형은 `str` 을 섞은 Enum 이라 값이 같으면 사전 키가 충돌한다.

    `up_to_date`·`remote_empty` 가 양쪽에 있어, 한 사전에 담으면 push 판정에 pull 문구가
    나온다. `status` 는 push 판정을 찍으므로 사용자가 "받을 것이 없다"로 오해한다.
    """
    push = manifest.decision_message(PushDecision.UP_TO_DATE, head_seq=1)
    pull = manifest.decision_message(PullDecision.UP_TO_DATE, head_seq=1)

    assert push == "두 DB 는 원격과 같습니다(원격 seq 1)."
    assert pull == "두 DB 는 이미 원격 seq 1 입니다."
