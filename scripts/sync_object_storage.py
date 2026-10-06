# Purpose: 오브젝트 스토리지의 DuckDB 스냅샷을 진단·초기화하고 필요할 때 수동으로 받거나 올린다.

"""사내 S3 호환 스토리지와 DuckDB 파일을 주고받는 운영 도구.

판정 로직은 한 줄도 여기 두지 않는다. 키 계약과 pull·push 판정은
`services/object_storage_manifest.py`, 스냅샷 만들기·설치는 `persistence/snapshot_export.py`,
`aws` 호출은 `io/object_storage.py` 가 맡는다. 데이터 유실을 좌우하는 판단은 IO 와 떼어
순수 함수로 두어야 단위 테스트가 그대로 부를 수 있다. 여기서는 인자를 읽고 그 판정과
IO 를 잇기만 한다.

**앱을 끈 상태에서 쓴다.** DuckDB 파일은 프로세스 배타 잠금이라 앱이 떠 있으면 설치가
실패한다. `status`·`doctor`·`probe` 는 앱이 떠 있어도 안전하다.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capa_simulation.io import object_storage  # noqa: E402
from capa_simulation.io.object_storage import (  # noqa: E402
    ObjectStorageClient,
    ObjectStorageError,
    StorageSettings,
)
from capa_simulation.page_bootstrap import (  # noqa: E402
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
)
from capa_simulation.persistence import snapshot_export, sync_state  # noqa: E402
from capa_simulation.services import object_storage_manifest as manifest  # noqa: E402
from capa_simulation.services.korean_particle import (  # noqa: E402
    with_direction_particle,
    with_topic_particle,
)
from capa_simulation.services.object_storage_manifest import (  # noqa: E402
    DATASET_LABELS,
    DatasetName,
    PullDecision,
    PushDecision,
)
from capa_simulation.settings import (  # noqa: E402
    APP_VERSION,
    DUCKDB_PATH,
    EQUIPMENT_DUCKDB_PATH,
)

DATASET_PATHS = {
    "simulation": DUCKDB_PATH,
    "equipment": EQUIPMENT_DUCKDB_PATH,
}
MIB = 1024 * 1024


# --------------------------------------------------------------------------- 인자
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", help="AWS CLI 프로필. 생략하면 설정·환경변수를 따른다.")
    parser.add_argument("--bucket", help="버킷 이름. 생략하면 설정·환경변수를 따른다.")
    parser.add_argument("--endpoint-url", help="엔드포인트. 생략하면 설정·환경변수를 따른다.")
    parser.add_argument(
        "--dataset",
        choices=("simulation", "equipment", "all"),
        default="all",
        help="대상 DB. 기본 all.",
    )
    parser.add_argument("--dry-run", action="store_true", help="실제로 올리거나 받지 않는다.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("profile", help="사내 PC 에 넣을 aws configure 블록을 출력한다.")
    sub.add_parser("doctor", help="설정·연결·권한을 점검한다.")

    probe = sub.add_parser("probe", help="스토리지가 실제로 무엇을 지원하는지 실측한다.")
    probe.add_argument("--write", type=Path, help="결과를 이 경로에 JSON 으로 쓴다.")

    init = sub.add_parser("init", help="빈 저장소에 최초 스냅샷을 올린다.")
    init.add_argument("--note", default="최초 이관", help="포인터에 남길 메모.")

    sub.add_parser("status", help="원격 세대와 로컬 상태를 비교해 보여 준다.")

    pull = sub.add_parser("pull", help="원격 최신 스냅샷을 내려받아 설치한다.")
    pull.add_argument("--force", action="store_true", help="세대를 모르는 로컬 DB 도 덮는다.")

    push = sub.add_parser("push", help="로컬 변경을 새 스냅샷으로 올린다.")
    push.add_argument("--note", default="수동 저장", help="포인터에 남길 메모.")

    resolve = sub.add_parser("resolve", help="게시하지 못한 스냅샷이나 분기를 해소한다.")
    resolve.add_argument(
        "--keep",
        choices=("mine", "remote"),
        required=True,
        help="mine 이면 내 스냅샷을 새 세대로 올리고, remote 면 내 것을 버리고 원격을 받는다.",
    )

    adopt = sub.add_parser("adopt", help="세대를 모르는 로컬 DB 의 기준을 정한다.")
    adopt.add_argument("--source", choices=("local", "remote"), required=True)

    prune = sub.add_parser("prune", help="오래된 스냅샷을 지운다.")
    prune.add_argument("--keep-last", type=int, default=10, help="남길 최신 스냅샷 수.")
    prune.add_argument(
        "--include-orphans",
        action="store_true",
        help="포인터가 없는 고아 스냅샷도 후보에 넣는다. 경합에서 진 데이터라 기본은 보호한다.",
    )
    prune.add_argument("--yes", action="store_true", help="확인 없이 실제로 지운다.")
    return parser.parse_args(argv)


def build_settings(args: argparse.Namespace) -> StorageSettings:
    base = object_storage.load_settings()
    return StorageSettings(
        mode=base.mode,
        endpoint_url=args.endpoint_url or base.endpoint_url,
        bucket=args.bucket or base.bucket,
        profile=args.profile or base.profile,
        region=base.region,
        capabilities=base.capabilities,
    )


def build_client(args: argparse.Namespace) -> ObjectStorageClient:
    return ObjectStorageClient(settings=build_settings(args))


def datasets(args: argparse.Namespace) -> list[str]:
    return list(DATASET_PATHS) if args.dataset == "all" else [args.dataset]


# --------------------------------------------------------------------------- 조회 도우미
def read_head(client: ObjectStorageClient, dataset: str) -> manifest.Pointer | None:
    """원격 HEAD 포인터. 없으면 None."""
    records = client.list_objects(manifest.head_prefix(dataset), max_keys=8)
    key = manifest.select_head_key([record.key for record in records])
    if key is None:
        return None
    text = client.get_text(key, scratch_dir=snapshot_export.prepare_scratch())
    return manifest.pointer_from_json(text, pointer_key=key)


def read_fork(client: ObjectStorageClient, dataset: str) -> tuple[str, ...]:
    records = client.list_objects(manifest.head_prefix(dataset), max_keys=8)
    return manifest.detect_fork([record.key for record in records])


def local_state(dataset: str) -> sync_state.SyncState | None:
    return sync_state.read_state(DATASET_PATHS[dataset])


# --------------------------------------------------------------------------- 명령
def command_profile(args: argparse.Namespace) -> int:
    """사내 PC 에서 한 번 실행할 설정 블록. 손으로 옮겨 적지 않게 상수에서 만든다."""
    settings = build_settings(args)
    print("# 사내 PC 에서 한 번만 실행합니다(키 두 줄은 실제 값으로 바꾸세요).")
    print(f'$PROF = "{settings.profile}"')
    print("aws configure set aws_access_key_id     <키>   --profile $PROF")
    print("aws configure set aws_secret_access_key <비밀> --profile $PROF")
    for name, value in (
        ("region", settings.region),
        ("endpoint_url", settings.endpoint_url),
        ("request_checksum_calculation", "when_required"),
        ("response_checksum_validation", "when_required"),
        ("s3.addressing_style", "path"),
    ):
        print(f"aws configure set {name} {value} --profile $PROF")
    print()
    print(f"# 네임스페이스({object_storage.NAMESPACE_NOTE})는 프로필에 매여 있습니다.")
    print("# 체크섬 두 줄은 AWS CLI 2.23+ 와 ECS 의 비호환 우회입니다(Dell KB 000299507).")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    settings = build_settings(args)
    print(f"모드          : {settings.mode}")
    print(f"엔드포인트    : {settings.endpoint_url}")
    print(f"버킷          : {settings.bucket}")
    print(f"프로필        : {settings.profile}")
    print(f"네임스페이스  : {object_storage.NAMESPACE_NOTE} (프로필에 매여 있음)")
    if settings.endpoint_url.startswith("http://"):
        print("[주의] 평문 HTTP 입니다. 파일 내용이 사내망에 그대로 흐릅니다.")
    # 클라이언트는 다른 명령과 똑같이 `build_client` 를 지난다. 여기서만 따로 만들면
    # 실행기를 갈아끼운 테스트가 이 경로만 못 덮는다.
    client = build_client(args)
    try:
        print(f"CLI           : {client.cli_version()}")
        print(f"주소 스타일   : {client.check_addressing_style()}")
    except ObjectStorageError as exc:
        print(f"[중단] {exc}")
        return 1
    failures = 0
    for dataset in datasets(args):
        label = DATASET_LABELS[dataset]
        try:
            head = read_head(client, dataset)
        except ObjectStorageError as exc:
            print(f"[중단] {label} 조회 실패 — {exc}")
            failures += 1
            continue
        generation = "비어 있음" if head is None else f"seq {head.seq} · {head.author}"
        print(f"{label:<8}원격 : {generation}")
        state = local_state(dataset)
        if state is None:
            print(f"{label:<8}로컬 : 사이드카 없음(세대 미상)")
        else:
            dirty = sync_state.treat_as_dirty(DATASET_PATHS[dataset])
            changed = "변경 있음" if dirty else "변경 없음"
            print(f"{label:<8}로컬 : seq {state.base_seq} · {changed}")
    return 1 if failures else 0


def command_probe(args: argparse.Namespace) -> int:
    """스토리지 능력을 실측한다. 확인하지 못한 것은 false 로 남긴다."""
    client = build_client(args)
    scratch = snapshot_export.prepare_scratch()
    sample = scratch / "probe.txt"
    sample.write_text("capa probe", encoding="utf-8")
    key = f"_probe/scratch-{uuid.uuid4().hex[:8]}.txt"
    results: dict[str, object] = {
        "_확인일": snapshot_export.utc_timestamp(),
        "_확인자": snapshot_export.author_label(),
    }
    try:
        _, md5_hex, md5_base64, _ = snapshot_export.digest_file(sample)
        outcome = client.put_file(key, sample, content_md5_base64=md5_base64)
        results["single_put_etag_is_md5"] = bool(
            outcome.etag and "-" not in outcome.etag and outcome.etag.lower() == md5_hex.lower()
        )
        print(f"업로드 ETag   : {outcome.etag or '(없음)'}")

        try:
            client.put_file(key, sample, content_md5_base64="AAAAAAAAAAAAAAAAAAAAAA==")
            results["content_md5_rejects_mismatch"] = False
        except ObjectStorageError:
            results["content_md5_rejects_mismatch"] = True

        forced = StorageSettings(
            mode=client.settings.mode,
            endpoint_url=client.settings.endpoint_url,
            bucket=client.settings.bucket,
            profile=client.settings.profile,
            region=client.settings.region,
            capabilities={"conditional_put_if_none_match_star": True},
        )
        conditional = ObjectStorageClient(settings=forced)
        try:
            second = conditional.put_file(key, sample, if_none_match=True)
            # 이미 있는 키인데 통과했다면 조건이 무시된 것이다 — 지원한다고 보면 안 된다.
            results["conditional_put_if_none_match_star"] = second.precondition_failed
        except ObjectStorageError as exc:
            print(f"조건부 쓰기   : 거부됨 — {exc}")
            results["conditional_put_if_none_match_star"] = False
    except ObjectStorageError as exc:
        print(f"[중단] {exc}")
        return 1
    finally:
        try:
            client.delete(key)
        except ObjectStorageError:
            print(f"[건너뜀] 정리 실패 — {key} 를 손으로 지워야 할 수 있습니다.")
        sample.unlink(missing_ok=True)

    print(json.dumps(results, ensure_ascii=False, indent=1))
    if args.write:
        args.write.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"기록          : {args.write}")
    return 0


def _publish(
    client: ObjectStorageClient,
    dataset: str,
    *,
    parent: manifest.Pointer | None,
    note: str,
    dry_run: bool,
) -> int:
    """스냅샷을 올리고 포인터를 게시한다. 순서가 유실 방지의 전부다."""
    database_path = DATASET_PATHS[dataset]
    label = DATASET_LABELS[dataset]
    if not database_path.exists():
        print(f"[중단] {label} 로컬 DB 가 없습니다: {database_path}")
        return 1
    scratch = snapshot_export.prepare_scratch()
    export_path = scratch / f"{dataset}-export.duckdb"
    result = snapshot_export.export_snapshot(database_path, export_path)
    print(
        f"{label} 스냅샷 : {result.source_bytes / MIB:.1f} MiB → "
        f"{result.size_bytes / MIB:.1f} MiB, {result.elapsed_seconds:.2f}초"
    )
    pointer = manifest.next_pointer(
        parent,
        dataset=dataset,
        token=uuid.uuid4().hex[:8],
        sha256=result.sha256_hex,
        md5_base64=result.md5_base64,
        size_bytes=result.size_bytes,
        source_db_bytes=result.source_bytes,
        migration_version=result.migration_version,
        app_version=APP_VERSION,
        author=snapshot_export.author_label(),
        created_at_utc=snapshot_export.utc_timestamp(),
        note=note,
    )
    if dry_run:
        print(f"[건너뜀] --dry-run 이라 올리지 않습니다. 예정 키 {pointer.snapshot_key}")
        export_path.unlink(missing_ok=True)
        return 0

    outcome = client.put_file(
        pointer.snapshot_key,
        export_path,
        content_md5_base64=result.md5_base64,
        metadata={"sha256": result.sha256_hex, "seq": str(pointer.seq)},
    )
    object_storage.assert_single_put_etag(outcome.etag, local_md5_hex=result.md5_hex)
    print(f"{label} 업로드 : {pointer.snapshot_key}")

    # 스냅샷을 올린 뒤 다시 확인한다. 이 사이에 남이 올렸으면 포인터를 게시하지 않는다.
    current = read_head(client, dataset)
    moved = (current.sha256 if current else None) != (parent.sha256 if parent else None)
    if moved:
        sync_state.mark_unpublished(
            database_path,
            snapshot_key=pointer.snapshot_key,
            sha256=result.sha256_hex,
            reason="업로드 도중 원격이 앞섰습니다",
        )
        print(
            f"[중단] {label} 업로드 도중 원격이 앞섰습니다. 스냅샷은 보존했습니다 — "
            f"resolve --keep mine 으로 승격하거나 --keep remote 로 버리세요."
        )
        export_path.unlink(missing_ok=True)
        return 1

    client.put_text(
        pointer.pointer_key,
        manifest.pointer_to_json(pointer),
        scratch_dir=scratch,
        if_none_match=client.supports_conditional_put(),
    )
    forked = read_fork(client, dataset)
    if forked:
        sync_state.mark_unpublished(
            database_path,
            snapshot_key=pointer.snapshot_key,
            sha256=result.sha256_hex,
            reason="같은 세대에 포인터가 둘입니다",
        )
        print(f"[중단] {label} 이 갈라졌습니다: {', '.join(forked)}")
        export_path.unlink(missing_ok=True)
        return 1

    sync_state.adopt_generation(
        database_path,
        dataset=dataset,  # type: ignore[arg-type]
        seq=pointer.seq,
        sha256=result.sha256_hex,
        snapshot_key=pointer.snapshot_key,
    )
    print(f"{label} 게시   : seq {pointer.seq}")
    export_path.unlink(missing_ok=True)
    return 0


def command_init(args: argparse.Namespace) -> int:
    client = build_client(args)
    failures = 0
    for dataset in datasets(args):
        head = read_head(client, dataset)
        if head is not None:
            print(f"[건너뜀] {DATASET_LABELS[dataset]} 원격에 이미 seq {head.seq} 이 있습니다.")
            continue
        failures += _publish(client, dataset, parent=None, note=args.note, dry_run=args.dry_run)
    return 1 if failures else 0


def command_status(args: argparse.Namespace) -> int:
    client = build_client(args)
    for dataset in datasets(args):
        label = DATASET_LABELS[dataset]
        database_path = DATASET_PATHS[dataset]
        head = read_head(client, dataset)
        forked = read_fork(client, dataset)
        state = local_state(dataset)
        dirty = sync_state.treat_as_dirty(database_path)
        decision = manifest.decide_push(
            head=head,
            forked=bool(forked),
            base_sha256=None if state is None else state.base_sha256,
            dirty=dirty,
            unpublished=bool(state and state.unpublished_snapshot_key),
        )
        print(f"── {label}")
        print(f"   원격 : {'비어 있음' if head is None else f'seq {head.seq} · {head.author}'}")
        print(f"   로컬 : {'세대 미상' if state is None else f'seq {state.base_seq}'}")
        print(f"   변경 : {'있음' if dirty else '없음'}")
        if state and state.unpublished_snapshot_key:
            print(f"   미게시: {state.unpublished_snapshot_key} ({state.unpublished_reason})")
        if forked:
            print(f"   분기 : {', '.join(forked)}")
        print(f"   판정 : {manifest.decision_message(decision, dataset, head=head)}")
    return 0


def _app_is_running(dataset: DatasetName) -> str | None:
    """앱이 이 PC 에서 이 DB 를 잡고 있으면 그 인스턴스 id.

    DuckDB 파일은 프로세스 배타 잠금이라 앱이 떠 있는 동안 스냅샷을 내보내지도, 받은
    파일로 덮지도 못한다. 막지 않으면 `duckdb.IOException` 원문이 그대로 나오고 — Windows
    로캘에서는 한글까지 깨져 — 사용자는 원인이 "앱이 켜져 있다" 라는 것을 알 수 없다.

    심장박동은 앱이 10초에 한 번 남기고 90초 지나면 죽은 것으로 본다. 끄고 바로 돌리면
    잠깐 남아 있을 수 있으나, 그때는 안내를 보고 다시 실행하면 된다 — 조용히 실패하는
    것보다 낫다.
    """
    return sync_state.live_instance(DATASET_PATHS[dataset])


def _blocked_by_running_app(dataset: DatasetName, action: str) -> bool:
    instance = _app_is_running(dataset)
    if instance is None:
        return False
    print(
        f"[중단] {DATASET_LABELS[dataset]} — 앱이 이 PC 에서 실행 중입니다"
        f"(인스턴스 {instance}). DuckDB 는 프로세스 배타 잠금이라 앱을 끄지 않으면 "
        f"{action} 할 수 없습니다."
    )
    return True


def command_pull(args: argparse.Namespace) -> int:
    client = build_client(args)
    failures = 0
    for dataset in datasets(args):
        label = DATASET_LABELS[dataset]
        database_path = DATASET_PATHS[dataset]
        if _blocked_by_running_app(dataset, "받은 파일로 덮어"):
            failures += 1
            continue
        head = read_head(client, dataset)
        forked = read_fork(client, dataset)
        state = local_state(dataset)
        decision = manifest.decide_pull(
            head=head,
            forked=bool(forked),
            base_sha256=None if state is None else state.base_sha256,
            local_exists=database_path.exists(),
            dirty=sync_state.treat_as_dirty(database_path) if database_path.exists() else False,
            unpublished=bool(state and state.unpublished_snapshot_key),
        )
        if decision is PullDecision.AMBIGUOUS and args.force:
            print(f"[주의] {label} 세대를 모르지만 --force 라 덮습니다.")
        elif decision not in (PullDecision.DOWNLOAD, PullDecision.LOCAL_MISSING):
            print(f"[건너뜀] {manifest.decision_message(decision, dataset, head=head)}")
            if decision in (PullDecision.BLOCKED_DIRTY, PullDecision.BLOCKED_FORKED):
                failures += 1
            continue
        assert head is not None
        if args.dry_run:
            print(f"[건너뜀] --dry-run 이라 받지 않습니다. 예정 {head.snapshot_key}")
            continue
        scratch = snapshot_export.prepare_scratch()
        download = scratch / f"{dataset}-download.duckdb"
        client.get_file(head.snapshot_key, download, expected_bytes=head.size_bytes)
        snapshot_export.verify_snapshot(
            download,
            dataset=dataset,  # type: ignore[arg-type]
            expected_sha256=head.sha256,
            expected_size=head.size_bytes,
            code_version=snapshot_export.code_migration_version(dataset),  # type: ignore[arg-type]
        )
        backup = snapshot_export.install_snapshot(download, database_path)
        sync_state.adopt_generation(
            database_path,
            dataset=dataset,  # type: ignore[arg-type]
            seq=head.seq,
            sha256=head.sha256,
            snapshot_key=head.snapshot_key,
        )
        print(f"{label} 설치   : seq {head.seq} (이전 파일 백업 {backup})")
    return 1 if failures else 0


def command_push(args: argparse.Namespace) -> int:
    client = build_client(args)
    failures = 0
    for dataset in datasets(args):
        database_path = DATASET_PATHS[dataset]
        if _blocked_by_running_app(dataset, "스냅샷을 내보내"):
            failures += 1
            continue
        head = read_head(client, dataset)
        forked = read_fork(client, dataset)
        state = local_state(dataset)
        decision = manifest.decide_push(
            head=head,
            forked=bool(forked),
            base_sha256=None if state is None else state.base_sha256,
            dirty=sync_state.treat_as_dirty(database_path),
            unpublished=bool(state and state.unpublished_snapshot_key),
        )
        if decision is not PushDecision.PUBLISH:
            print(f"[건너뜀] {manifest.decision_message(decision, dataset, head=head)}")
            if decision in (
                PushDecision.PARENT_MOVED,
                PushDecision.FORKED,
                PushDecision.BLOCKED_UNPUBLISHED,
            ):
                failures += 1
            continue
        failures += _publish(client, dataset, parent=head, note=args.note, dry_run=args.dry_run)
    return 1 if failures else 0


def command_resolve(args: argparse.Namespace) -> int:
    client = build_client(args)
    failures = 0
    for dataset in datasets(args):
        label = DATASET_LABELS[dataset]
        database_path = DATASET_PATHS[dataset]
        state = local_state(dataset)
        if state is None or not state.unpublished_snapshot_key:
            print(f"[건너뜀] {label} 에 해소할 미게시 스냅샷이 없습니다.")
            continue
        if args.keep == "remote":
            sync_state.clear_unpublished(database_path)
            print(f"{label} : 내 스냅샷을 버렸습니다. pull 로 원격을 받으세요.")
            continue
        head = read_head(client, dataset)
        if args.dry_run:
            print("[건너뜀] --dry-run 이라 승격하지 않습니다.")
            continue
        # 내 스냅샷은 이미 올라가 있다. 그것을 가리키는 새 세대 포인터만 만든다.
        # 크기는 반드시 원격에서 다시 읽는다 — 0 으로 두면 나중에 pull 이 그 포인터를
        # 크기 불일치로 거부해 복구한 세대를 못 받는다.
        remote = client.head(state.unpublished_snapshot_key)
        if remote is None:
            print(f"[중단] {label} 미게시 스냅샷을 원격에서 찾지 못했습니다.")
            failures += 1
            continue
        pointer = manifest.next_pointer(
            head,
            dataset=dataset,  # type: ignore[arg-type]
            token=uuid.uuid4().hex[:8],
            sha256=state.unpublished_sha256 or "",
            md5_base64="",
            size_bytes=remote.size_bytes,
            source_db_bytes=0,
            migration_version=snapshot_export.code_migration_version(dataset),  # type: ignore[arg-type]
            app_version=APP_VERSION,
            author=snapshot_export.author_label(),
            created_at_utc=snapshot_export.utc_timestamp(),
            note="미게시 스냅샷 승격",
        )
        promoted = manifest.Pointer(
            **{**pointer.__dict__, "snapshot_key": state.unpublished_snapshot_key}
        )
        client.put_text(
            promoted.pointer_key,
            manifest.pointer_to_json(promoted),
            scratch_dir=snapshot_export.prepare_scratch(),
        )
        sync_state.adopt_generation(
            database_path,
            dataset=dataset,  # type: ignore[arg-type]
            seq=promoted.seq,
            sha256=promoted.sha256,
            snapshot_key=promoted.snapshot_key,
        )
        print(f"{label} : {with_direction_particle(f'seq {promoted.seq}')} 승격했습니다.")
    return 1 if failures else 0


def command_adopt(args: argparse.Namespace) -> int:
    client = build_client(args)
    for dataset in datasets(args):
        label = DATASET_LABELS[dataset]
        database_path = DATASET_PATHS[dataset]
        if args.source == "remote":
            print(f"[안내] {with_topic_particle(label)} pull --force 로 원격을 받으세요.")
            continue
        head = read_head(client, dataset)
        if head is None:
            print(f"[중단] {label} 원격이 비어 있습니다. init 이 먼저입니다.")
            return 1
        # 로컬을 기준으로 삼는다 = 원격 세대를 부모로 기록하고 변경 있음으로 둔다.
        sync_state.adopt_generation(
            database_path,
            dataset=dataset,  # type: ignore[arg-type]
            seq=head.seq,
            sha256=head.sha256,
            snapshot_key=head.snapshot_key,
        )
        sync_state.mark_dirty(database_path)
        print(f"{label} : 로컬을 기준으로 잡았습니다. push 로 올리세요.")
    return 0


def command_prune(args: argparse.Namespace) -> int:
    client = build_client(args)
    for dataset in datasets(args):
        label = DATASET_LABELS[dataset]
        pointer_records = client.list_objects(manifest.head_prefix(dataset), max_keys=1000)
        pointers = []
        for record in pointer_records:
            text = client.get_text(record.key, scratch_dir=snapshot_export.prepare_scratch())
            pointers.append(manifest.pointer_from_json(text, pointer_key=record.key))
        snapshots = [
            record.key
            for record in client.list_objects(manifest.snapshot_prefix(dataset), max_keys=1000)
        ]
        candidates = manifest.prune_candidates(
            snapshot_keys=snapshots,
            pointers=pointers,
            keep_last=args.keep_last,
            include_orphans=args.include_orphans,
            protected=(),
        )
        print(f"── {label} 정리 후보 {len(candidates)}개")
        for key in candidates:
            print(f"   {key}")
        if not candidates:
            continue
        if args.dry_run or not args.yes:
            print("   [건너뜀] 실제로 지우려면 --yes 를 함께 주세요.")
            continue
        for key in candidates:
            client.delete(key)
        print(f"   {len(candidates)}개를 지웠습니다.")
    return 0


COMMANDS = {
    "profile": command_profile,
    "doctor": command_doctor,
    "probe": command_probe,
    "init": command_init,
    "status": command_status,
    "pull": command_pull,
    "push": command_push,
    "resolve": command_resolve,
    "adopt": command_adopt,
    "prune": command_prune,
}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    handler = COMMANDS[args.command]
    # 사이드카 기록은 등록된 경로에만 쓴다. 스크립트는 이 파일들의 주인이므로 여기서
    # 등록한다 — 빼먹으면 `mark_unpublished`·`clear_unpublished` 가 조용히 아무 일도
    # 하지 않아, 경합에서 진 스냅샷의 복구 정보가 사라진다.
    sync_state.enable({DATASET_PATHS[name]: name for name in datasets(args)})
    try:
        return int(handler(args))
    except ObjectStorageError as exc:
        print(f"[중단] {exc}")
        return 1
    except BOOTSTRAP_ERRORS as exc:
        # `duckdb.Error` 는 RuntimeError 가 아니다. 이걸 잡지 않으면 앱을 켜 둔 채 돌렸을 때
        # 원문 트레이스백이 나오고 Windows 로캘에서는 한글까지 깨진다.
        print(f"[중단] {bootstrap_error_message(exc)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
