# Purpose: managed 모드일 때만 동기화 기록을 켜고, 설정을 못 읽으면 앱은 띄운 채 꺼진 까닭을 남긴다.

"""앱 기동에서 한 번 판정하는 동기화 등록.

`sync_state` 는 등록된 경로에만 파일을 쓴다. 그 등록을 여기서 한다 — `sync_state` 자체가
설정을 읽으면 저장 경로가 `io` 와 설정 파일에 묶이고, 그 모듈은 COMMIT 직후에 불리는
자리라 그런 의존을 둘 수 없다.

설정을 읽지 못하면(`load_settings` 의 `ObjectStorageError` — 틀린 `CAPA_S3_SYNC_MODE`, 깨진
설정·능력 JSON) 동기화는 끄되 **조용히 local 로 강등하지 않는다**(2026-10-22 사용자 결정 (다)).
앱은 띄우고 까닭을 `sync_disabled_reason` 으로 남겨 상태 알림 `SY-01` 이 알린다 — 사용자가 저장이
올라간다고 믿지 않게. 까닭은 값 없는 고정 낱말이다 — 칸을 잘못 붙여 넣으면 값이 키일 수 있고,
알림은 로그인한 사람 모두가 본다.

모드 칸이 비어 `local` 로 뜬 서버는 시작 점검이 버킷에서 세대를 보았는지 결과 파일로 받는다
(`head_ignored`). 비어 있는 값은 유효해서 `SY-01` 이 서지 않으므로, 이 표지가 없으면 CI/CD 가 초록인
채 빈 시드 앱이 뜨고 저장이 다음 CI/CD 에 사라진다. 알림은 `SY-05` 다.

판정은 프로세스에 한 번이다. `app.py` 는 회차마다 부르지만 설정 파일을 회차마다 다시 읽지 않는다
(설정·환경변수를 바꾸면 앱을 다시 띄운다).

**부트 기록**(`data/temp/object_sync_boot.json`)은 시작 때의 받기(`sync_object_storage.py
boot-pull`)가 성공한 뒤 쓰고, 일꾼은 이 기록이 있을 때만 선다. 그래서 `app.py` 개발 실행 · 사내 PC
· 시험에서는 서지 않는다 — 환경변수를 하나 더 두지 않는다. 받기가 이 기록을 쓰지 못하면 실패로
끝나 앱이 뜨지 않는다 — 일꾼 없이 뜬 앱의 저장은 어디에도 안 올라간다.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final
from uuid import uuid4

from capa_simulation import settings
from capa_simulation.io.container_start_report import read_container_start_report
from capa_simulation.io.object_storage import (
    SETTINGS_UNREADABLE,
    ObjectStorageError,
    StorageSettingsError,
    load_settings,
)
from capa_simulation.persistence import sync_state
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH

# 이 파이썬 프로세스 하나를 가리키는 값. 앱 서버가 살아 있는 동안 바뀌지 않고, 다시 켜면
# 새로 생긴다. 사람에게 보여 줄 이름이 아니라 "같은 인스턴스인가" 만 가리는 표식이다.
INSTANCE_ID = uuid4().hex[:12]

MANAGED_PATHS = {DUCKDB_PATH: "simulation", EQUIPMENT_DUCKDB_PATH: "equipment"}
BOOT_RECORD_NAME: Final = "object_sync_boot.json"

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncBoot:
    """프로세스에 한 번 내린 동기화 판정."""

    managed: bool
    # 설정을 읽지 못해 동기화를 켜지 못한 까닭(짧게). 읽었으면 None 이다.
    disabled_reason: str | None = None
    # 이 자리의 DB 가 정본을 넘긴 사본이면 그 시각(사내 PC).
    handed_over_utc: str | None = None
    # 버킷에 세대가 있는데 모드가 비어 받지 않은 서버(시작 점검이 남긴 표지).
    head_ignored: bool = False


_BOOT_LOCK = threading.Lock()
_BOOT: SyncBoot | None = None


def _decide() -> SyncBoot:
    handed_over = sync_state.read_generation(
        sync_state.generation_path(DUCKDB_PATH)
    ).handed_over_utc
    try:
        storage = load_settings()
    except (ObjectStorageError, OSError, ValueError) as exc:
        reason = exc.label if isinstance(exc, StorageSettingsError) else SETTINGS_UNREADABLE
        _LOGGER.warning("오브젝트 스토리지 설정을 읽지 못해 동기화를 끕니다 — %s", reason)
        return SyncBoot(managed=False, disabled_reason=reason, handed_over_utc=handed_over)
    if storage.mode != "managed":
        return SyncBoot(
            managed=False, handed_over_utc=handed_over, head_ignored=_start_ignored_head()
        )
    sync_state.enable(MANAGED_PATHS)  # type: ignore[arg-type]
    return SyncBoot(managed=True, handed_over_utc=handed_over)


def _start_ignored_head() -> bool:
    report = read_container_start_report()
    return report is not None and report.sync is not None and report.sync.head_ignored


def _boot() -> SyncBoot:
    global _BOOT
    with _BOOT_LOCK:
        if _BOOT is None:
            _BOOT = _decide()
        return _BOOT


def enable_sync_state_if_managed() -> bool:
    """`mode` 가 managed 일 때만 등록하고 그 여부를 돌려준다. 판정은 프로세스에 한 번이다."""
    return _boot().managed


def is_managed() -> bool:
    return _boot().managed


def sync_disabled_reason() -> str | None:
    """설정을 못 읽어 동기화를 끈 까닭. 정상(local·managed)이면 None 이다."""
    return _boot().disabled_reason


def handed_over_utc() -> str | None:
    """이 자리의 DB 가 정본을 넘긴 사본인가 — 사내 PC 의 `init` 이 남긴 시각."""
    return _boot().handed_over_utc


def head_ignored() -> bool:
    """버킷에 세대가 있는데 모드가 비어 받지 않은 서버인가 — 이 앱의 저장은 어디에도 안 남는다."""
    return _boot().head_ignored


def sync_alerts_possible() -> bool:
    """이 프로세스에 동기화 알림이 설 수 있는가. 아니면 화면 쪽이 Streamlit 을 부르지 않는다.

    모두 프로세스에 한 번 정한 값이라 회차마다 달라지지 않는다.
    """
    boot = _boot()
    return (
        boot.managed
        or boot.head_ignored
        or boot.disabled_reason is not None
        or boot.handed_over_utc is not None
    )


def forget_boot_result() -> None:
    """테스트 전용. 프로세스에 한 번 내린 판정을 잊어 다음 호출이 설정을 다시 읽게 한다."""
    global _BOOT
    with _BOOT_LOCK:
        _BOOT = None


def heartbeat_if_managed() -> None:
    """앱이 이 PC 에서 돌고 있다는 표시를 사이드카에 남긴다.

    DuckDB 파일은 프로세스 배타 잠금이라, 앱이 떠 있는 동안 `sync_object_storage.py` 의
    pull·push 는 DB 를 열지 못하고 `duckdb.IOException` 으로 끝난다. 그 메시지만으로는
    원인이 "앱이 켜져 있다" 라는 것을 알 수 없다. 심장박동이 있으면 스크립트가 DB 를 열기
    전에 그 사실을 읽어 사람 말로 알릴 수 있다.

    `touch_heartbeat` 이 10초에 한 번만 실제로 쓰므로 rerun 마다 불러도 된다. 등록되지
    않은(=managed 가 아닌) 환경에서는 그 안에서 곧바로 돌아가 파일을 만들지 않는다.
    """
    for path in MANAGED_PATHS:
        sync_state.touch_heartbeat(path, instance_id=INSTANCE_ID)


@dataclass(frozen=True)
class BootRecord:
    """시작 때의 받기가 성공했다는 기록. 값은 갈래와 수뿐이다(주소 · 버킷 · 키 없음)."""

    action: str
    seq: int
    previous_upload_utc: str | None
    pull_seconds: float
    finished_at_utc: str
    total_bytes: int = 0


def boot_record_path() -> Path:
    """부트 기록 자리. 부를 때마다 `settings` 에서 읽는다 — 시험이 그 칸을 tmp 로 옮긴다."""
    return settings.DATA_DIR / "temp" / BOOT_RECORD_NAME


def write_boot_record(record: BootRecord) -> None:
    """쓰기 실패는 그대로 올린다 — 받기가 실패로 끝나야 일꾼 없는 앱이 뜨지 않는다."""
    path = boot_record_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(asdict(record), ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def clear_boot_record() -> None:
    boot_record_path().unlink(missing_ok=True)


def read_boot_record() -> BootRecord | None:
    """없거나 꼴이 어긋나면 None — 일꾼이 서지 않고 `SY-02` 가 알린다."""
    try:
        payload = json.loads(boot_record_path().read_text(encoding="utf-8"))
        previous = payload.get("previous_upload_utc")
        return BootRecord(
            action=str(payload["action"]),
            seq=int(payload["seq"]),
            previous_upload_utc=None if previous is None else str(previous),
            pull_seconds=float(payload["pull_seconds"]),
            finished_at_utc=str(payload["finished_at_utc"]),
            total_bytes=int(payload.get("total_bytes", 0)),
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
