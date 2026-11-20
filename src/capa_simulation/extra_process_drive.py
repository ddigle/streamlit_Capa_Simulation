# Purpose: 부대공정 S3 Drive 가져오기 원천 — 놓는 자리의 낱장 CSV 여섯을 받아 한 판으로 묶고 머리를
# 본다(C-DEP 진입 파일이 꽂는다).

"""S3 Drive 가져오기 원천(설계 A6 — 2026-11-20 보드 결정-2 (가) 「낱장 CSV 여섯」).

**자리.** 버킷의 `extra_process/` 아래 정해진 이름 여섯(`PACK_HEADERS` — `00_info.csv` ~
`05_rate_vital.csv`, 소문자 · `.csv`)이다. 사람이 S3 Drive 웹에서 그 여섯을 놓아 덮어쓴다(사내 확인
부대 6 · 11 — 같은 버킷 · 놓는 자리 맨 위 · 정해진 이름 덮어쓰기 됨, `.zip` 은 웹이 막음). 앱은
정해진 키만 받는다(GET · HEAD) — 목록(LIST)은 앱 열쇠로 재지 않은 능력이라 쓰지 않아, 다른 이름으로
놓인 파일 · 남는 파일은 보지 않고 그 이름의 장은 「파일 없음」 으로 거절된다. 이 접두 밖 키는 다루지
않는다.

**받기(`fetch`).** 여섯을 차례로 받고(빠진 장은 건너뜀) 바로 머리를 한 번 더 본다. 그다음
`extra_process_pack.bundle_pack_files` 로 판 한 벌(ZIP — 앱 안의 판 꼴)로 묶어 넘긴다 — 판정 ·
미리보기 · 적용은 받은 꼴과 상관없이 같은 길이다. 판정:

- 여섯 다 없으면 「없음」(`SourceNotReady` — 실패 아님, 알림 `EP-01` 없음).
- **놓는 중**(`SourceNotReady` 「놓는 중」) — 받은 뒤 다시 본 머리의 ETag 가 받은 것과 다르거나(받는
  동안 바뀜), 가장 늦게 놓인 장이 저장소 시각(`Date` — 앱 시계가 아님)으로 `SETTLE_SECONDS` 안이다.
  여섯은 한 번에 바뀌지 않으므로(객체 하나만 원자적) 놓기가 끝나기를 기다린다.
- 일부만 빠짐은 묶어 넘긴다 — 접수 검증이 빠진 장마다 「파일 없음」 거절 표를 낸다.
- 일부만 바뀜(다른 장은 앞 판 그대로)은 한 판으로 읽는다 — `00_info.csv` 의 판 번호를 올리지
  않았으면 판 번호 규칙(판 번호가 적용한 가장 큰 판 이하인데 내용이 다름 → 거절)이 막고, 올렸으면 새
  판이다(지금 판과의 차이는 값 줄이 센다). 그래서 사람은 `00_info.csv` 를 마지막에 놓는다(Guide) —
  그 전에 가져오면 판 번호 규칙이 거절한다.
- 상한은 여섯 장 합 `PACK_MAX_BYTES`(8 MiB — 설계 3-1), 마감은 받기 전체에
  하나(`FETCH_DEADLINE_SECONDS` — 바닥 속도로 상한을 받는 시간)다. 닿지 못함 · 인증 거절 같은 실패는
  첫 장에서 멈춘다.

**ETag.** 여섯 장의 ETag 를 하나로 묶은 값(`set_etag` — 장 이름 · ETag, 없는 장은 `-`)이 판 이력의
`s3_etag` 와 머리 보기(`head`)의 값이다. 저장소가 ETag 를 주지 않은 장이 있으면 「바뀌었나」 를 알
수 없으므로 받기는 ETag 없이(기준이 되지 않음) 넘기고, 머리 보기는 「읽지 못함(ETag 없음)」 이다.

**머리 보기(`head`).** 새 파일 감지(`EP-02`)가 5분에 한 번 부른다. 여섯 HEAD 가 마감 하나
(`HEAD_DEADLINE_SECONDS` — 요청 하나의 마감)를 나눠 쓰고 첫 실패에서 멈춘다 — 닿지 않는 저장소가
그 회차를 여섯 배 묶지 않게.

**닿을 곳**은 C-DEP 꼴(동기화 `managed` + 앱이 기동 때 읽은 S3 명단 키 —
`runtime.config().access_s3`)에서만 있다(`extra_process_intake.production_place` 와 같은 조건). 그
밖에는 「쓸 수 없음」 이다. Streamlit 을 import 하지 않는다 — `capa_server.py` 가 런타임 전에
꽂는다.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Final

from capa_simulation.extra_process_intake import (
    RemoteHead,
    SourceFailure,
    SourceFetch,
    SourceNotReady,
    install_source,
)
from capa_simulation.io import s3_small
from capa_simulation.io.s3_small import S3Target
from capa_simulation.services.extra_process_pack import (
    PACK_HEADERS,
    PACK_MAX_BYTES,
    bundle_pack_files,
)

DRIVE_PREFIX: Final = "extra_process/"
DRIVE_PLACE: Final = "S3 Drive"
DRIVE_LABEL: Final = "S3 Drive 에서 가져오기"
DRIVE_FILES: Final = tuple(PACK_HEADERS)
DRIVE_KEYS: Final = tuple(f"{DRIVE_PREFIX}{name}" for name in DRIVE_FILES)
# 가장 늦게 놓인 장이 이만큼 지나야 받는다(저장소 시각 기준) — 여섯을 하나씩 놓는 동안 가져오지
# 않게.
SETTLE_SECONDS: Final = 120
# 바닥 속도(DB 정본 전송의 바닥과 같다 — 모듈 도우미와 같은 셈)로 상한을 받는 시간 + 요청 하나의
# 마감.
_MIN_MIB_PER_SECOND: Final = 0.3
FETCH_DEADLINE_SECONDS: Final = s3_small.REQUEST_DEADLINE_SECONDS + PACK_MAX_BYTES / (
    _MIN_MIB_PER_SECOND * 1024 * 1024
)
HEAD_DEADLINE_SECONDS: Final = s3_small.REQUEST_DEADLINE_SECONDS

MISSING_WORD: Final = "없음"
PLACING_WORD: Final = "놓는 중"
MISSING_REASON: Final = "S3 Drive extra_process/ 에 부대공정 파일이 없습니다"
PLACING_REASON: Final = (
    "S3 Drive 에 부대공정 파일을 놓는 중입니다 — 마지막 파일을 놓고 "
    f"{SETTLE_SECONDS // 60}분 뒤 다시 가져오세요"
)
UNAVAILABLE: Final = "쓸 수 없음(운영 서버 접속 정보 없음)"
TOO_LARGE: Final = f"너무 큼(여섯 장 합 {PACK_MAX_BYTES // (1024 * 1024)} MiB 까지)"
ETAG_UNKNOWN: Final = "ETag 없음"
# `s3_small` 의 까닭 분류 → 고정 낱말(모듈 도우미 `_TRANSFER_LABELS` 와 같은 말).
TRANSFER_LABELS: Final[Mapping[str, str]] = {
    s3_small.KIND_UNREACHABLE: "주소에 닿지 못함",
    s3_small.KIND_TIMEOUT: "시간 초과",
    s3_small.KIND_TLS: "인증서 확인 실패",
    s3_small.KIND_AUTH: "인증 거절",
    s3_small.KIND_NO_BUCKET: "버킷 없음",
    s3_small.KIND_TOO_LARGE: TOO_LARGE,
    s3_small.KIND_OTHER: "그 밖의 응답",
}


def app_target() -> S3Target | None:
    """C-DEP 꼴의 닿을 곳 — 동기화 `managed` 이고 앱이 기동 때 읽은 S3 명단 키가 있을 때만."""
    from capa_simulation.auth import runtime
    from capa_simulation.io import object_storage

    try:
        mode = object_storage.load_settings().mode
    except object_storage.StorageSettingsError:
        return None
    if mode != object_storage.MODE_MANAGED:
        return None
    return runtime.config().access_s3


def set_etag(etags: Mapping[str, str | None]) -> str | None:
    """여섯 장의 ETag 를 하나로 — 장 이름 · ETag(없는 장은 `-`)를 이은 sha256 앞 32자.

    여섯 다 없으면 None(파일 없음), 있는 장 가운데 ETag 를 모르는(빈 글) 장이 있으면 빈 글 —
    「바뀌었나」 를 알 수 없으므로 기준으로 쓰지 않는다.
    """
    present = {name: etag for name, etag in etags.items() if etag is not None}
    if not present:
        return None
    if any(not etag for etag in present.values()):
        return ""
    joined = "\n".join(f"{name}:{etags.get(name) or '-'}" for name in DRIVE_FILES)
    return "set-" + hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


class DriveSource:
    """S3 Drive 의 낱장 여섯 — 받기 · 머리 보기. 닿을 곳 · 시계는 시험이 갈아 끼운다."""

    label = DRIVE_LABEL
    place = DRIVE_PLACE

    def __init__(
        self,
        target: Callable[[], S3Target | None] = app_target,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._target = target
        self._clock = clock

    def _reach(self) -> S3Target:
        target = self._target()
        if target is None:
            raise SourceFailure(UNAVAILABLE)
        return target

    def _left(self, deadline: float) -> float:
        """남은 마감 — 지났으면 「시간 초과」."""
        left = deadline - self._clock()
        if left <= 0:
            raise SourceFailure(TRANSFER_LABELS[s3_small.KIND_TIMEOUT])
        return left

    def _get(
        self, target: S3Target, key: str, room: int, deadline: float
    ) -> s3_small.S3Object | None:
        left = self._left(deadline)
        try:
            return s3_small.get_object(target, key, max_bytes=room, deadline_seconds=left)
        except s3_small.S3Failure as failure:
            reason = _failure_label(failure)
        raise SourceFailure(reason)

    def _head(self, target: S3Target, key: str, deadline: float) -> s3_small.S3Head | None:
        left = self._left(deadline)
        try:
            return s3_small.head_meta(target, key, deadline_seconds=left)
        except s3_small.S3Failure as failure:
            reason = _failure_label(failure)
        raise SourceFailure(reason)

    def fetch(self) -> SourceFetch:
        target = self._reach()
        deadline = self._clock() + FETCH_DEADLINE_SECONDS
        found: dict[str, s3_small.S3Object] = {}
        total = 0
        for name, key in zip(DRIVE_FILES, DRIVE_KEYS, strict=True):
            got = self._get(target, key, PACK_MAX_BYTES - total, deadline)
            if got is None:
                continue
            found[name] = got
            total += len(got.body)
        if not found:
            raise SourceNotReady(MISSING_REASON, MISSING_WORD)
        heads = {
            name: self._head(target, key, deadline)
            for name, key in zip(DRIVE_FILES, DRIVE_KEYS, strict=True)
        }
        for name in DRIVE_FILES:
            before = found.get(name)
            after = heads[name]
            if (before is None) != (after is None) or (
                before is not None and after is not None and before.etag != after.etag
            ):
                raise SourceNotReady(PLACING_REASON, PLACING_WORD)
        placed = [item.last_modified for item in found.values() if item.last_modified is not None]
        newest = max(placed) if placed else None
        if newest is not None and _settling(newest, _server_now(found, heads)):
            raise SourceNotReady(PLACING_REASON, PLACING_WORD)
        etag = set_etag({name: found[name].etag if name in found else None for name in DRIVE_FILES})
        return SourceFetch(
            data=bundle_pack_files({name: item.body for name, item in found.items()}),
            place=DRIVE_PLACE,
            key=DRIVE_PREFIX,
            etag=etag or None,
            last_modified=newest,
        )

    def head(self) -> RemoteHead:
        target = self._reach()
        deadline = self._clock() + HEAD_DEADLINE_SECONDS
        etags: dict[str, str | None] = {}
        placed: list[datetime] = []
        for name, key in zip(DRIVE_FILES, DRIVE_KEYS, strict=True):
            meta = self._head(target, key, deadline)
            etags[name] = None if meta is None else meta.etag
            if meta is not None and meta.last_modified is not None:
                placed.append(meta.last_modified)
        etag = set_etag(etags)
        if etag == "":
            raise SourceFailure(ETAG_UNKNOWN)
        return RemoteHead(etag, max(placed) if placed else None)


def _failure_label(failure: s3_small.S3Failure) -> str:
    return TRANSFER_LABELS.get(failure.kind, TRANSFER_LABELS[s3_small.KIND_OTHER])


def _server_now(
    found: Mapping[str, s3_small.S3Object], heads: Mapping[str, s3_small.S3Head | None]
) -> datetime:
    """저장소가 마지막으로 답한 시각 — 머리가 없으면 앱 시계(UTC)."""
    times = [item.server_time for item in found.values() if item.server_time is not None]
    times += [item.server_time for item in heads.values() if item and item.server_time]
    return max(times) if times else datetime.now(timezone.utc)


def _settling(newest: datetime, now: datetime) -> bool:
    return now - newest < timedelta(seconds=SETTLE_SECONDS)


def install_drive_source() -> None:
    """C-DEP 진입 파일(`capa_server.py`)이 부른다 — 받기 · 머리 보기는 누를 때 닿을 곳을 고른다."""
    install_source(DriveSource())
