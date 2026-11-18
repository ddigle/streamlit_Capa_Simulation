# Purpose: 부대공정 판 들이기 — 가져오기 원천을 꽂는 자리 · 받은 파일 판정 · 미리보기 시험 계산 ·
# 쓰는 곳 판정을 세션 없이 둔다.

"""부대공정 판 들이기(Admin 「부대공정」 탭의 화면 밖 몸통 — 설계 3-4 · A7).

**가져오기 원천은 꽂는 자리 하나다**(`ExtraProcessSource` · `install_source`). 정한 원천은 S3 Drive
의 고정 자리 `extra_process/current.zip` 이지만(설계 3-1), 사내 확인 부대 5(DRM) · 6(같은 버킷)의
답이 오기 전이라 1단계는 원천을 꽂지 않는다 — 꽂힌 것이 없으면 탭의 가져오기 단추는 서지 않는다. 답
뒤 S3 Drive 가져오기(A6)가 `fetch()` 하나를 갖춘 원천을 꽂으면 같은 판정 · 미리보기 · 적용 길을
지난다. 시험은 가짜 원천을 꽂는다.

**받은 파일**(`stage_pack`)은 접수 검증(`extra_process_pack.read_pack_zip`)과 판 번호
판정(`judge_pack` — 바뀐 것 없음 · 다시 켜기 · 적용 · 뒤로 감)을 함께 든다. 판정은 받은 때의 판 이력
마지막 차례 (`seen_seq`)를 들고 있어 적용이 그 차례와 대조한다(설계 규칙 UI-STA-05).

**미리보기**(`preview_pack`)는 지금 활성 시나리오의 표에 이 판을 4장 규칙대로 합쳐 본다(저장하지
않는다) — 지금 판과의 차이 · 앞 판 값으로 되돌리는 칸 수(G12) · 측정률 칸 수 · 공정마다 합침/뺌과
월별 소요대수 · 확보율 · 부하 0 경로 수.

**쓰는 곳**(`production_place`)은 C-DEP(동기화 `managed` + 접속 정보)이다 — 꺼진 곳(사내 PC · WebIDE
· 사외 `app.py`)은 화면(`components/extra_process_admin.write_lock_reason`)이 쓰는 단추를 모두
잠근다(설계 D16 (다)).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

import pandas as pd

from capa_simulation.persistence.models import ExtraProcessState, ExtraProcessVersion
from capa_simulation.services.extra_process_merge import (
    ActiveExtraPack,
    ExtraMergeReport,
    ExtraPackVersion,
    load_lines,
    overlay_extra_processes,
    process_rows_frame,
)
from capa_simulation.services.extra_process_pack import (
    ExtraProcessPack,
    PackChanges,
    PackJudgement,
    PackReading,
    RatioCounts,
    judge_pack,
    pack_changes,
    read_pack_zip,
)


@dataclass(frozen=True)
class SourceFetch:
    """원천에서 받은 파일 한 벌과 메타(S3 키 · ETag · 놓인 시각)."""

    data: bytes
    place: str
    key: str | None = None
    etag: str | None = None
    last_modified: datetime | None = None


class SourceFailure(Exception):
    """원천에서 받지 못했다 — 까닭 낱말(닿지 못함 · 없음 · 너무 큼 …). 지난 판으로 계속 간다."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ExtraProcessSource(Protocol):
    """가져오기 원천 — 단추 글 · 자리 이름 · 받기 하나."""

    @property
    def label(self) -> str: ...

    @property
    def place(self) -> str: ...

    def fetch(self) -> SourceFetch: ...


_SOURCE: ExtraProcessSource | None = None


def install_source(source: ExtraProcessSource | None) -> None:
    """가져오기 원천을 꽂는다(`None` 이면 뺀다). 1단계는 꽂지 않는다 — S3 Drive 원천은 사내 답
    뒤."""
    global _SOURCE
    _SOURCE = source


def installed_source() -> ExtraProcessSource | None:
    return _SOURCE


@dataclass(frozen=True)
class StagedPack:
    """받아 검사한 판 — 아직 적용하지 않았다."""

    fetch: SourceFetch
    reading: PackReading
    judgement: PackJudgement | None
    seen_seq: int
    staged_at: datetime

    @property
    def applicable(self) -> bool:
        return self.reading.accepted and self.judgement is not None and self.judgement.applicable


def stage_pack(state: ExtraProcessState, fetched: SourceFetch, *, now: datetime) -> StagedPack:
    """받은 파일을 접수 검증하고 판 이력과 견준다."""
    reading = read_pack_zip(fetched.data)
    judgement = None
    if reading.pack is not None:
        latest = state.latest_content
        active = state.active
        judgement = judge_pack(
            reading.sha256,
            reading.pack.info.version_no,
            active_sha=None if active is None else active.sha256,
            latest_version_no=None if latest is None else latest.version_no,
            latest_sha=None if latest is None else latest.sha256,
            off=state.off,
        )
    return StagedPack(fetched, reading, judgement, state.last_seq, now)


def previous_content(state: ExtraProcessState) -> ExtraProcessVersion | None:
    """활성 판의 바로 앞 내용 판(sha 가 다른 마지막 내용 줄) — 되돌리는 칸 수(G12)의 견줌 대상."""
    active = state.active
    if active is None:
        return None
    for item in reversed(state.history):
        if item.seq >= active.seq or item.sha256 is None:
            continue
        if item.sha256 != active.sha256:
            return item
    return None


@dataclass(frozen=True)
class PackPreview:
    """미리보기 한 벌 — 차이 · 측정률 칸 수 · 합치기 보고 · 월별 시험 계산 · 경로 수."""

    changes: PackChanges
    ratio: RatioCounts
    report: ExtraMergeReport
    rates: pd.DataFrame
    lines: Mapping[str, tuple[int, int]] = field(default_factory=dict)


def preview_pack(
    tables: Mapping[str, pd.DataFrame],
    previous_extra: Collection[str],
    pack: ExtraProcessPack,
    *,
    seq: int,
    current: ExtraProcessPack | None,
    before: ExtraProcessPack | None = None,
) -> PackPreview:
    """지금 활성 시나리오의 표(`tables`)에 판을 합쳐 본다 — 그 시나리오에 이미 든 부대공정
    (`previous_extra`)은 먼저 걷는다(얹기와 같은 길). 저장하지 않는다. `seq` 는 미리보기에 쓸 판
    차례(아직 적용 전이면 다음 차례)다."""
    active = ActiveExtraPack(ExtraPackVersion(seq, pack.info.version_no, pack.sha256), pack)
    result = overlay_extra_processes(tables, previous_extra, active)
    merged = result.report.merged_processes()
    return PackPreview(
        changes=pack_changes(pack, current, before),
        ratio=pack.ratio,
        report=result.report,
        rates=process_rows_frame(result.tables, merged),
        lines=load_lines(result.tables, merged),
    )


def production_place() -> bool:
    """C-DEP 꼴인가 — 동기화 `managed` 이고 앱이 기동 때 읽은 S3 접속 정보가 있다(모듈 도우미 ·
    BDQ 자동 로그인과 같은 조건)."""
    from capa_simulation.auth import runtime
    from capa_simulation.io import object_storage

    try:
        mode = object_storage.load_settings().mode
    except object_storage.StorageSettingsError:
        return False
    return mode == object_storage.MODE_MANAGED and runtime.config().access_s3 is not None
