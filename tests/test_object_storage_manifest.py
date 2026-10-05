# Purpose: 오브젝트 스토리지 포인터 키 계약과 세대·분기 판정을 검증한다.

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from capa_simulation.services import object_storage_manifest as manifest
from capa_simulation.services.object_storage_manifest import (
    Pointer,
    PullDecision,
    PushDecision,
    WriterMark,
)

SHA_A = "a1b2c3d4" + "0" * 56
SHA_B = "b2c3d4e5" + "0" * 56


def _pointer(seq: int, *, sha256: str = SHA_A, token: str = "0000aaaa") -> Pointer:
    return manifest.next_pointer(
        None if seq == 1 else _parent(seq - 1),
        dataset="simulation",
        token=token,
        sha256=sha256,
        md5_base64="bWQ1",
        size_bytes=21_524_480,
        source_db_bytes=67_383_296,
        migration_version=14,
        app_version="0.9.0-demo",
        author="DEMO_USER@PC-1",
        created_at_utc="2026-09-08T09:15:00Z",
        note="리비전 저장",
    )


def _parent(seq: int) -> Pointer:
    return Pointer(
        schema=1,
        database="simulation",
        seq=seq,
        pointer_key=manifest.pointer_key("simulation", seq, "0000bbbb"),
        snapshot_key=manifest.snapshot_key(
            "simulation", seq, created_at_utc="2026-09-07T09:15:00Z", sha256=SHA_B
        ),
        sha256=SHA_B,
        md5_base64="bWQ1",
        size_bytes=1,
        source_db_bytes=1,
        parent_seq=None,
        parent_sha256=None,
        migration_version=14,
        app_version="0.9.0-demo",
        author="DEMO_USER@PC-1",
        created_at_utc="2026-09-07T09:15:00Z",
        note="",
    )


def test_descending_pointer_keys_sort_newest_first() -> None:
    """`list --max-keys N` 한 번이 항상 최신 N 개여야 한다. 그래서 내림차순이다."""
    keys = [manifest.pointer_key("simulation", seq, "0000aaaa") for seq in (1, 2, 41, 42)]

    assert sorted(keys)[0] == manifest.pointer_key("simulation", 42, "0000aaaa")
    assert manifest.seq_from_pointer_key(sorted(keys)[0]) == 42


def test_pointer_key_round_trips_the_sequence() -> None:
    for seq in (0, 1, 999, 10**6, manifest.SEQUENCE_SPACE):
        key = manifest.pointer_key("equipment", seq, "0123abcd")
        assert manifest.seq_from_pointer_key(key) == seq


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
        manifest.pointer_key("simulation", 1, "not-hex!")


def test_head_selection_is_deterministic_when_two_pointers_share_a_sequence() -> None:
    """분기 상황에서도 모든 PC 가 같은 것을 HEAD 로 봐야 한다."""
    first = manifest.pointer_key("simulation", 42, "0000aaaa")
    second = manifest.pointer_key("simulation", 42, "ffffbbbb")

    assert manifest.select_head_key([second, first]) == first
    assert manifest.select_head_key([first, second]) == first


def test_fork_is_detected_only_at_the_top_sequence() -> None:
    top_a = manifest.pointer_key("simulation", 42, "0000aaaa")
    top_b = manifest.pointer_key("simulation", 42, "ffffbbbb")
    older = manifest.pointer_key("simulation", 41, "1111cccc")

    assert manifest.detect_fork([top_a, top_b, older]) == (top_a, top_b)
    assert manifest.detect_fork([top_a, older]) == ()
    assert manifest.detect_fork([]) == ()


def test_pointer_json_round_trips() -> None:
    pointer = _pointer(1)

    restored = manifest.pointer_from_json(
        manifest.pointer_to_json(pointer), pointer_key=pointer.pointer_key
    )

    assert restored == pointer


def test_unknown_pointer_schema_is_refused_instead_of_guessed() -> None:
    """앞으로 스키마가 바뀌면 옛 배포본이 조용히 잘못 읽는 것이 가장 나쁘다."""
    with pytest.raises(ValueError, match="포인터 스키마"):
        manifest.pointer_from_json(
            '{"schema": 2, "database": "simulation", "seq": 1}', pointer_key="k"
        )


def test_next_pointer_chains_the_parent_hash() -> None:
    """부모 해시가 체인의 근거다. 시계도 조건부 쓰기도 필요 없다."""
    child = _pointer(2)

    assert child.seq == 2
    assert child.parent_seq == 1
    assert child.parent_sha256 == SHA_B
    assert child.snapshot_key.startswith("simulation/snapshots/000000000002__")


def test_push_is_blocked_while_an_unpublished_snapshot_remains() -> None:
    """충돌을 쌓지 않는다. 사람이 한 번에 풀게 한다."""
    decision = manifest.decide_push(
        head=_pointer(1), forked=False, base_sha256=SHA_A, dirty=True, unpublished=True
    )

    assert decision is PushDecision.BLOCKED_UNPUBLISHED


def test_push_refuses_when_the_remote_moved_ahead() -> None:
    decision = manifest.decide_push(
        head=_pointer(1), forked=False, base_sha256=SHA_B, dirty=True, unpublished=False
    )

    assert decision is PushDecision.PARENT_MOVED


def test_push_publishes_only_when_dirty_and_parent_matches() -> None:
    head = _pointer(1)

    assert (
        manifest.decide_push(
            head=head, forked=False, base_sha256=head.sha256, dirty=True, unpublished=False
        )
        is PushDecision.PUBLISH
    )
    assert (
        manifest.decide_push(
            head=head, forked=False, base_sha256=head.sha256, dirty=False, unpublished=False
        )
        is PushDecision.UP_TO_DATE
    )


def test_push_does_not_seed_an_empty_remote() -> None:
    """최초 이관은 스크립트의 init 만 한다. 앱이 빈 저장소를 채우면 안 된다."""
    decision = manifest.decide_push(
        head=None, forked=False, base_sha256=None, dirty=True, unpublished=False
    )

    assert decision is PushDecision.REMOTE_EMPTY


def test_pull_never_overwrites_local_only_changes() -> None:
    head = _pointer(1)

    assert (
        manifest.decide_pull(
            head=head,
            forked=False,
            base_sha256=SHA_B,
            local_exists=True,
            dirty=True,
            unpublished=False,
        )
        is PullDecision.BLOCKED_DIRTY
    )
    assert (
        manifest.decide_pull(
            head=head,
            forked=False,
            base_sha256=SHA_B,
            local_exists=True,
            dirty=False,
            unpublished=True,
        )
        is PullDecision.BLOCKED_DIRTY
    )


def test_pull_is_ambiguous_when_the_local_generation_is_unknown() -> None:
    """세대를 모르는 로컬 DB 를 자동으로 덮으면 그 안의 리비전이 조용히 사라진다."""
    decision = manifest.decide_pull(
        head=_pointer(1),
        forked=False,
        base_sha256=None,
        local_exists=True,
        dirty=False,
        unpublished=False,
    )

    assert decision is PullDecision.AMBIGUOUS


def test_pull_decisions_for_the_ordinary_paths() -> None:
    head = _pointer(1)
    common = {"forked": False, "dirty": False, "unpublished": False}

    assert (
        manifest.decide_pull(head=head, base_sha256=head.sha256, local_exists=True, **common)
        is PullDecision.UP_TO_DATE
    )
    assert (
        manifest.decide_pull(head=head, base_sha256=SHA_B, local_exists=True, **common)
        is PullDecision.DOWNLOAD
    )
    assert (
        manifest.decide_pull(head=head, base_sha256=None, local_exists=False, **common)
        is PullDecision.LOCAL_MISSING
    )
    assert (
        manifest.decide_pull(head=None, base_sha256=None, local_exists=False, **common)
        is PullDecision.REMOTE_EMPTY
    )


def test_migration_version_comparison_flags_a_newer_file() -> None:
    """받은 파일이 더 최신이면 이 배포본은 그 DB 를 열면 안 된다."""
    assert manifest.compare_migration_version(file_version=15, code_version=14) == "newer"
    assert manifest.compare_migration_version(file_version=13, code_version=14) == "older"
    assert manifest.compare_migration_version(file_version=14, code_version=14) == "ok"


def test_orphan_snapshots_are_the_ones_no_pointer_references() -> None:
    keys = ["simulation/snapshots/a", "simulation/snapshots/b"]

    assert manifest.orphan_snapshot_keys(keys, ["simulation/snapshots/a"]) == (
        "simulation/snapshots/b",
    )


def test_prune_protects_orphans_unless_explicitly_included() -> None:
    """고아 스냅샷이 '유실 불가' 의 유일한 근거다. 정리 명령이 그것부터 지우면 안 된다."""
    pointers = [_parent(1), _parent(2)]
    snapshots = [pointer.snapshot_key for pointer in pointers] + ["simulation/snapshots/orphan"]

    protected = manifest.prune_candidates(
        snapshot_keys=snapshots,
        pointers=pointers,
        keep_last=1,
        include_orphans=False,
        protected=(),
    )
    included = manifest.prune_candidates(
        snapshot_keys=snapshots,
        pointers=pointers,
        keep_last=1,
        include_orphans=True,
        protected=(),
    )

    assert "simulation/snapshots/orphan" not in protected
    assert "simulation/snapshots/orphan" in included


def test_prune_keeps_the_requested_number_of_recent_snapshots() -> None:
    pointers = [_parent(seq) for seq in (1, 2, 3)]
    snapshots = [pointer.snapshot_key for pointer in pointers]

    candidates = manifest.prune_candidates(
        snapshot_keys=snapshots,
        pointers=pointers,
        keep_last=2,
        include_orphans=False,
        protected=(),
    )

    assert candidates == (pointers[0].snapshot_key,)


def test_prune_rejects_keeping_nothing() -> None:
    with pytest.raises(ValueError, match="1 이상"):
        manifest.prune_candidates(
            snapshot_keys=[], pointers=[], keep_last=0, include_orphans=False, protected=()
        )


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


def test_decision_messages_are_korean_and_name_the_dataset() -> None:
    head = _pointer(1)

    message = manifest.decision_message(PushDecision.PARENT_MOVED, "simulation", head=head)

    assert "시뮬레이션" in message
    assert "seq 1" in message
    assert "로컬 저장은 그대로" in message


def test_pull_messages_pick_the_object_particle_by_the_last_sound() -> None:
    """이름 뒤 목적격 조사는 끝소리로 고른다 — 「가용설비 을」·「seq 2 을」이 아니다."""
    head = _pointer(2)

    assert manifest.decision_message(PullDecision.DOWNLOAD, "equipment", head=head).startswith(
        "가용설비를 원격 seq 2 으로"
    )
    assert manifest.decision_message(PullDecision.DOWNLOAD, "simulation", head=head).startswith(
        "시뮬레이션을 원격"
    )
    assert "원격 seq 2를 받습니다" in manifest.decision_message(
        PullDecision.LOCAL_MISSING, "simulation", head=head
    )


def test_push_and_pull_messages_do_not_collide_on_shared_enum_values() -> None:
    """두 열거형은 `str` 을 섞은 Enum 이라 값이 같으면 사전 키가 충돌한다.

    `up_to_date`·`remote_empty` 가 양쪽에 있어, 한 사전에 담으면 push 판정에 pull 문구가
    나온다. `status` 는 push 판정을 찍으므로 사용자가 "받을 것이 없다"로 오해한다.
    """
    head = _pointer(1)

    push = manifest.decision_message(PushDecision.UP_TO_DATE, "simulation", head=head)
    pull = manifest.decision_message(PullDecision.UP_TO_DATE, "simulation", head=head)

    assert push == "시뮬레이션 은 원격과 같습니다(원격 seq 1)."
    assert pull == "시뮬레이션 은 이미 원격 seq 1 입니다."
