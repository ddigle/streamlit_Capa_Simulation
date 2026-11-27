# Purpose: 부대공정 판 들이기 · 내보내기 — 가져오기 원천 · 내보내기 자리를 꽂는 자리 · 받은 파일
# 판정 · 미리보기 시험 계산 · S3 Drive 쓰기 견줌 · 쓰는 곳 판정을 세션 없이 둔다.

"""부대공정 판 들이기(Admin 「부대공정」 탭의 화면 밖 몸통 — 설계 3-4 · A7).

**가져오기 원천은 꽂는 자리 하나다**(`ExtraProcessSource` · `install_source` — 받기 `fetch()` 와
머리 보기 `head()`). 정한 원천은 S3 Drive 의 놓는 자리 `extra_process/` 의 낱장 CSV
여섯이다(2026-11-20 보드 결정-2 (가) — `extra_process_drive.DriveSource`). C-DEP 진입
파일(`capa_server.py`)만 꽂고 개발 · 사내 PC · WebIDE(`app.py`)는 꽂지 않는다 — 꽂힌 것이 없으면
탭의 가져오기 단추는 서지 않는다. 받기가 아직 받을 것이 없다고 하면(`SourceNotReady` — 여섯 다 없음
· 놓는 중) 실패가 아니라 상태 줄 낱말과 알림창 안내 하나다(`EP-01` 없음). 시험은 가짜 원천 · 가짜 S3
로 꽂는다.

**받은 파일**(`stage_pack`)은 접수 검증(`extra_process_pack.read_pack_zip`)과 판 번호
판정(`judge_pack` — 바뀐 것 없음 · 다시 켜기 · 적용 · 뒤로 감)과 지금 판과의 차이 · 앞 판 값으로
되돌리는 칸 수(G12 — `pack_changes`, 계산 없이 센다)를 함께 든다 — 화면은 「적용」 위에 그 값 줄을
늘 세운다. 판정은 받은 때의 판 이력 마지막 차례 (`seen_seq`)를 들고 있어 적용이 그 차례와
대조한다(설계 규칙 UI-STA-05). 편집기가 만든 판(`stage_editor_pack`)도 같은 자리에 실린다 — 차례는
펼친 때의 것이고(`EditorOrigin`), 거절 표 한 줄은 접은 줄 출처로 편집기 자리를 되짚는다.

**미리보기**(`preview_pack`)는 지금 활성 시나리오의 표에 이 판을 4장 규칙대로 합쳐 본다(저장하지
않는다) — 공정마다 합침/뺌과 월별 소요대수 · 확보율 · 부하 0 경로 수. 합친 표의 전체 기간 계산은
한 번 돌려 두 셈이 함께 쓴다.

**쓰는 곳**(`production_place`)은 C-DEP(동기화 `managed` + 접속 정보)이다 — 꺼진 곳(사내 PC · WebIDE
· 사외 `app.py`)은 화면(`components/extra_process_admin.write_lock_reason`)이 쓰는 단추를 모두
잠근다(설계 D16 (다)).

**내보내기도 꽂는 자리 하나다**(`ExtraProcessSink` · `install_sink` — 설계 3-1 · 3-5 · A6 의 PUT).
「이 리비전 값을 새 판으로」 가 DB 에 새 판을 넣은 뒤 S3 Drive 파일을 덮는 길이고, 놓는 꼴이 낱장
여섯으로 바뀐 뒤(2026-11-20) 여섯은 덮지 않기로 해 **앱 코드는 꽂지 않는다 — 시험만 꽂는다**.
꽂힌 것이 없으면 「새 판으로」 는 DB 새 판만 넣고 S3 를 건드리지 않으며, 「S3 에 다시 쓰기」 · 알림
`EP-05`(덮지 못함)도 서지 않는다 — 원천이 꽂혀 있으면 그 대신 판 어긋남 알림 `EP-06`(「S3 Drive
파일은 판 n 그대로 — 양식 내려받기로 새 판을 받아 놓으세요」)이 선다. 편집기 판(원천 자리 「앱
입력」)은 S3 Drive 에 쓸 몫이 아니라(`owes_drive`) 내보내기가 꽂혀 있어도 이 셋 밖이다 — 다만 사람이
그 판 양식을 그대로 놓아 가져오면 「놓인 파일 같음」 은 적는다(`unplaced` — 기준 ETag 가 옛 파일에
머물면 그 파일이 「새 파일」 `EP-02` 로 남는다). 가져오지 않은 새 파일
(`EP-02`)은 원천의 `head()` 만으로 선다(2026-11-19 보드 답 — 내보내기와 묶지 않음). 쓰기
(`write_back`)는 PUT 바로 앞 HEAD 의 ETag 를 기준 ETag(`ExtraProcessState.baseline` — 앱이
적용했거나 쓴 마지막 파일)와 견줘 같거나 파일이 없을 때만 덮는다 — 다르면 적용하지 않은 사람
파일이라 덮지 않는다(설계 G5). HEAD 와 PUT 사이 틈은 조건부 쓰기(`If-Match`)가 재어지기 전에는
닫히지 않아, 덮으면 「앱이 덮음 · 판 · 시각」 을 알림창과 판 이력에 남긴다.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Protocol

import pandas as pd

from capa_simulation.persistence.models import (
    EXTRA_EDITOR_PLACE,
    EXTRA_KIND_OFF,
    EXTRA_KIND_REVISION,
    EXTRA_WRITE_FAILED,
    EXTRA_WRITE_KEPT,
    EXTRA_WRITE_WRITTEN,
    ExtraProcessS3Write,
    ExtraProcessState,
    ExtraProcessVersion,
)
from capa_simulation.services.extra_process_editor import Canonical, Folded
from capa_simulation.services.extra_process_merge import (
    ActiveExtraPack,
    ExtraMergeReport,
    ExtraPackVersion,
    capacity_outcome,
    inherited_capacity_gaps,
    load_lines,
    overlay_extra_processes,
    process_rows_frame,
)
from capa_simulation.services.extra_process_pack import (
    JUDGE_APPLY,
    JUDGE_UNCHANGED,
    ExtraProcessPack,
    PackChanges,
    PackJudgement,
    PackReading,
    RatioCounts,
    judge_pack,
    pack_changes,
    read_pack_zip,
)
from capa_simulation.services.extra_process_revision import KeptProcess
from capa_simulation.services.route_load_exceptions import RouteLoadDeclaration


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


class SourceNotReady(SourceFailure):
    """받을 것이 아직 없다 — 여섯 다 없음 · 놓는 중. 실패가 아니다: 상태 줄 낱말(`word`)과 알림창
    안내(`reason`) 하나이고 `EP-01` 을 세우지 않는다. 지난 판으로 계속 간다."""

    def __init__(self, reason: str, word: str) -> None:
        super().__init__(reason)
        self.word = word


class ExtraProcessSource(Protocol):
    """가져오기 원천 — 단추 글 · 자리 이름 · 받기 · 머리 보기(새 파일 감지 `EP-02`)."""

    @property
    def label(self) -> str: ...

    @property
    def place(self) -> str: ...

    def fetch(self) -> SourceFetch: ...

    def head(self) -> RemoteHead:
        """놓인 파일의 ETag(받기의 `SourceFetch.etag` 와 같은 꼴 — 없으면 None)와 놓인 시각."""
        ...


_SOURCE: ExtraProcessSource | None = None


def install_source(source: ExtraProcessSource | None) -> None:
    """가져오기 원천을 꽂는다(`None` 이면 뺀다). C-DEP 진입 파일이 S3 Drive 원천을 꽂는다
    (`extra_process_drive.install_drive_source`)."""
    global _SOURCE
    _SOURCE = source


def installed_source() -> ExtraProcessSource | None:
    return _SOURCE


@dataclass(frozen=True)
class RemoteHead:
    """S3 Drive 자리의 HEAD — ETag(None 이면 파일 없음)와 놓인 시각."""

    etag: str | None
    last_modified: datetime | None = None


class ExtraProcessSink(Protocol):
    """내보내기 자리 — 자리 이름 · HEAD · PUT(덮어쓰기). 실패는 `SourceFailure`(까닭 낱말)."""

    @property
    def place(self) -> str: ...

    def head(self) -> RemoteHead: ...

    def put(self, data: bytes) -> str:
        """`data` 로 덮어 쓰고 저장소가 돌려준 ETag 를 돌려준다."""
        ...


_SINK: ExtraProcessSink | None = None


def install_sink(sink: ExtraProcessSink | None) -> None:
    """내보내기 자리를 꽂는다(`None` 이면 뺀다). 앱 코드는 꽂지 않는다 — 낱장 여섯은 덮지 않기로
    해 시험만 꽂는다."""
    global _SINK
    _SINK = sink


def installed_sink() -> ExtraProcessSink | None:
    return _SINK


@dataclass(frozen=True)
class WriteOutcome:
    """S3 Drive 쓰기 한 번의 결과 — 기록 칸(`repository.record_extra_process_write`)과 상태 줄
    낱말(설계 3-4 의 1번 · 3-5 의 5번)."""

    result: str
    word: str
    etag: str | None = None
    seen_etag: str | None = None
    stage: str | None = None
    reason: str | None = None


WRITE_STAGE_HEAD: Final = "HEAD"
WRITE_STAGE_PUT: Final = "PUT"
NEW_FILE_WORD: Final = "새 파일"
OLD_VERSION_WORD: Final = "옛 판"
MISSING_WORD: Final = "없음"
# PUT 이 ETag 를 돌려주지 않은 쓰기의 까닭 낱말(실패로 남긴다 — `write_back`).
ETAG_MISSING: Final = "ETag 없음"


def written_word(now: datetime) -> str:
    return f"같음 — 앱이 씀 {now:%H:%M}"


def write_back(
    sink: ExtraProcessSink,
    data: bytes,
    *,
    baseline: str | None,
    now: datetime,
    known: Mapping[str, str] | None = None,
) -> WriteOutcome:
    """PUT 바로 앞 HEAD 로 견주고 덮는다(설계 3-1 「덮기 전 다시 읽기」 · G5).

    - HEAD 의 ETag 가 기준 ETag 와 같거나 파일이 없으면 덮는다 — 「씀」.
    - 다르면 덮지 않는다 — 「덮지 않음」. 상태 줄 낱말은 그 ETag 가 마지막으로 가져온 파일의
      것이면(`known` — ETag → 낱말) 그 낱말, 아니면 「새 파일」(판은 가져와야 안다).
    - HEAD 실패는 「읽지 못함(까닭)」, PUT 실패는 HEAD 로 본 파일이 있었으면 「옛 판」 · 없었으면
      「없음」 이다. 꽂이가 `SourceFailure` 로 감싸지 못한 예외도 같은 실패다(까닭은 예외 종류
      이름만 — 글에 주소 · 열쇠가 섞일 수 있어 싣지 않는다). 부르는 쪽은 DB 에 새 판을 넣은 뒤라,
      새면 쓰기 기록 없이 화면 오류가 된다.
    - PUT 이 빈 ETag 를 돌려주면 실패(PUT · `ETAG_MISSING`)다 — 「씀」 기록은 ETag 를 들어야 하고
      (기준 ETag 가 된다), 빈 값으로 넣으면 기록이 거절된다.
    """
    try:
        head = sink.head()
    except Exception as exc:  # noqa: BLE001 — 꽂이의 어떤 실패도 「읽지 못함」 기록으로 남긴다.
        reason = failure_reason(exc)
        return WriteOutcome(
            EXTRA_WRITE_FAILED,
            f"읽지 못함({reason})",
            stage=WRITE_STAGE_HEAD,
            reason=reason,
        )
    if head.etag is not None and head.etag != baseline:
        word = (known or {}).get(head.etag, NEW_FILE_WORD)
        return WriteOutcome(EXTRA_WRITE_KEPT, word, seen_etag=head.etag)
    failed_word = OLD_VERSION_WORD if head.etag is not None else MISSING_WORD
    try:
        etag = sink.put(data)
    except Exception as exc:  # noqa: BLE001 — 꽂이의 어떤 실패도 「쓰지 못함」 기록으로 남긴다.
        return WriteOutcome(
            EXTRA_WRITE_FAILED, failed_word, stage=WRITE_STAGE_PUT, reason=failure_reason(exc)
        )
    if not isinstance(etag, str) or not etag.strip():
        return WriteOutcome(
            EXTRA_WRITE_FAILED, failed_word, stage=WRITE_STAGE_PUT, reason=ETAG_MISSING
        )
    return WriteOutcome(EXTRA_WRITE_WRITTEN, written_word(now), etag=etag)


def failure_reason(exc: BaseException) -> str:
    """S3 Drive 자리 실패의 까닭 낱말 — `SourceFailure` 면 그 낱말, 아니면 예외 종류 이름만(쓰기 ·
    새 파일 감지 HEAD 가 함께 쓴다)."""
    if isinstance(exc, SourceFailure):
        return exc.reason
    return f"예상하지 못한 오류({type(exc).__name__})"


SAME_WORD: Final = "같음"


def head_word(etag: str | None, state: ExtraProcessState, known: Mapping[str, str]) -> str:
    """HEAD 로 본 ETag 의 상태 줄 낱말(설계 3-4 의 1번) — 없음 · 같음(기준 ETag 가 활성 판과 같은
    내용 파일의 것) · 옛 판(「새 판으로」 가 아직 쓰지 못해 기준이 앞 판에서 이어진 동안의 같은
    ETag) · 마지막으로 가져온 파일의 낱말(`known`) · 새 파일. 판은 sha 로 견준다 — 끄기 → 다시 켜기
    뒤에도 같은 판이다."""
    if etag is None:
        return MISSING_WORD
    baseline, owner = state.baseline
    if etag == baseline:
        active = state.active
        owner_sha = next((item.sha256 for item in state.history if item.seq == owner), None)
        same = active is not None and owner_sha is not None and owner_sha == active.sha256
        return SAME_WORD if same else OLD_VERSION_WORD
    return known.get(etag, NEW_FILE_WORD)


def owes_drive(version: ExtraProcessVersion) -> bool:
    """그 판 줄의 내용을 앱이 S3 Drive 에 써야 하나 — 「새 판으로」 판(갈래 「새 판」 · 원천 자리
    「리비전」)만이다. 편집기 판(원천 자리 「앱 입력」)은 쓸 몫이 아니다 — `EP-05` · `EP-06` · 「S3
    에 다시 쓰기」 밖이고, 내보내기가 꽂혀 있어도 쓰지 않는다."""
    return version.kind == EXTRA_KIND_REVISION and not version.editor_made


def _unwritten(
    state: ExtraProcessState, made: Callable[[ExtraProcessVersion], bool]
) -> ExtraProcessS3Write | None | bool:
    """활성 판 내용을 앱이 만들었고(`made` — 같은 sha 의 어느 판 줄이든) S3 Drive 에 그 파일이 아직
    없으면 그 내용의 마지막 쓰기 기록(쓴 적 없으면 None), 아니면 False."""
    active = state.active
    if active is None or active.sha256 is None:
        return False
    same = {item.seq for item in state.history if item.sha256 == active.sha256}
    if not any(made(item) for item in state.history if item.seq in same):
        return False
    if any(
        item.s3_etag and item.kind != EXTRA_KIND_OFF for item in state.history if item.seq in same
    ):
        return False
    writes = [item for item in state.writes if item.version_seq in same]
    if any(item.result == EXTRA_WRITE_WRITTEN for item in writes):
        return False
    return writes[-1] if writes else None


def pending_write(state: ExtraProcessState) -> ExtraProcessS3Write | None | bool:
    """활성 판을 S3 Drive 에 아직 쓰지 못했으면 그 내용의 마지막 쓰기 기록(쓴 적 없으면 None),
    쓸 것이 없으면 False.

    쓸 것은 「새 판으로」 가 만든 내용이다(`owes_drive` — 편집기 판은 들지 않는다) — 활성 줄이 그
    「새 판」 이거나, 끄기 → 다시 켜기로 같은 내용(sha)이 다시 활성이 된 때다. 같은 sha 의 어느 판
    줄에든 「씀」 기록이 있으면 S3 에 이미 있다(판은 sha 로 견준다) — 사람이 놓은 같은 파일을 적은
    줄(`placed_matches`)도 「씀」 이다. 같은 sha 의 판 줄이 S3 Drive 에서 가져온 파일의 ETag 를 들고
    있어도(끈 동안 그 새 판 파일을 놓아 가져와 다시 켬 — `baseline` 이 그 ETag 를 기준으로 삼는 줄)
    S3 에 이미 있다."""
    return _unwritten(state, owes_drive)


def needs_write(state: ExtraProcessState) -> bool:
    """활성 판(「새 판으로」 가 만든 내용)을 S3 Drive 에 아직 쓰지 못했나 — 알림 `EP-05` 와 「S3 에
    다시 쓰기」 의 조건(꽂힌 내보내기가 있을 때만 부른다), 내보내기가 없으면 판 어긋남 `EP-06` 의
    조건."""
    return pending_write(state) is not False


def unplaced(state: ExtraProcessState) -> bool:
    """활성 판이 앱이 만든 내용(갈래 「새 판」 — 「새 판으로」 · 편집기)이고 S3 Drive 에 그 파일이
    아직 없나 — 「놓인 파일 같음」 적기(`placed_matches`)의 조건. 편집기 판은 쓸 몫이 아니어도
    든다 — 사람이 그 판 양식을 그대로 놓았는데 적지 않으면 기준 ETag 가 옛 파일에 머물러, 다른
    세션의 머리 보기가 그 파일을 「새 파일」(`EP-02`)로 본다."""
    return _unwritten(state, lambda item: item.kind == EXTRA_KIND_REVISION) is not False


def placed_matches(state: ExtraProcessState, staged: StagedPack) -> bool:
    """받은 파일이 아직 S3 Drive 에 없는 활성 판(앱이 만든 「새 판」 — `unplaced`)과 같은 내용인가
    — 사람이 양식 내려받기로 받은 그 판을 놓은 것이다. 그러면 그 파일의 ETag 를 「놓인 파일
    같음」 으로 적어 기준을 옮긴다 — 「새 판으로」 판이면 판 어긋남(`EP-06`) · 「S3 에 다시
    쓰기」 도 풀린다. 보통의 「바뀐 것 없음」(적용한 파일을 다시 가져옴)은 아무것도 적지
    않는다(설계 3-2). 받은 때의 판정(`judgement`)만 믿지 않고 `state` 의 활성 판 sha 와 받은 판
    sha 를 다시 견준다 — 적는 쪽이 다시 읽은 판 이력으로 부를 때 그사이 다른 판이 활성이 되었으면
    적지 않는다."""
    active = state.active
    judgement = staged.judgement
    etag = staged.fetch.etag
    return (
        active is not None
        and active.sha256 is not None
        and active.sha256 == staged.reading.sha256
        and judgement is not None
        and judgement.verdict == JUDGE_UNCHANGED
        and staged.revision is None
        and staged.editor is None
        and bool(etag)
        and etag != state.baseline[0]
        and unplaced(state)
    )


@dataclass(frozen=True)
class RevisionOrigin:
    """리비전에서 만든 판의 바탕 — 시나리오 · 리비전과 화면 글, 옮긴 · 옮기지 못한 공정, 경로가
    판과 다른 공정."""

    scenario_id: str
    revision_id: str
    label: str
    moved: tuple[str, ...] = ()
    kept: tuple[KeptProcess, ...] = ()
    route_differs: tuple[str, ...] = ()


@dataclass(frozen=True)
class EditorOrigin:
    """편집기에서 만든 판의 바탕 — 펼친 때의 판 이력 마지막 차례(적용이 이 차례와 대조한다 — 누른
    때의 차례를 쓰면 펼친 뒤 남이 적용한 판을 말없이 지운다), 펼친 판의 sha(판이 하나도 없었으면
    None), 거절 표 한 줄을 편집기 자리로 되짚을 접은 줄(`extra_process_editor.locate`), 판에 들지
    않은 칸 입력 수(`extra_process_editor.ignored_cells` — 값 줄 「창 밖 고친 칸 n」)."""

    seen_seq: int
    base_sha: str | None
    folded: Folded
    ignored: int = 0


@dataclass(frozen=True)
class StagedPack:
    """받아 검사한 판 — 아직 적용하지 않았다. `revision` 이 있으면 원천 파일이 아니라 저장
    리비전에서 거꾸로 만든 판(「이 리비전 값을 새 판으로」), `editor` 가 있으면 편집기에서 만든
    판이다."""

    fetch: SourceFetch
    reading: PackReading
    judgement: PackJudgement | None
    seen_seq: int
    staged_at: datetime
    # 지금 판 · 앞 판과의 차이(받은 판이 읽혔을 때만).
    changes: PackChanges | None = None
    revision: RevisionOrigin | None = None
    editor: EditorOrigin | None = None

    @property
    def applicable(self) -> bool:
        return self.reading.accepted and self.judgement is not None and self.judgement.applicable


def stage_pack(
    state: ExtraProcessState,
    fetched: SourceFetch,
    *,
    now: datetime,
    current: ExtraProcessPack | None = None,
    before: ExtraProcessPack | None = None,
) -> StagedPack:
    """받은 파일을 접수 검증하고 판 이력과 견준다. `current` · `before` 는 활성 판 · 그 앞 내용 판
    (`previous_content`)의 내용이다 — 차이 · 되돌리는 칸 수를 받는 때 한 번 센다."""
    reading = read_pack_zip(fetched.data)
    judgement = None
    changes = None
    if reading.pack is not None:
        changes = pack_changes(reading.pack, current, before)
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
    return StagedPack(fetched, reading, judgement, state.last_seq, now, changes)


def stage_editor_pack(
    built: Canonical,
    origin: EditorOrigin,
    *,
    now: datetime,
    base: ExtraProcessPack | None,
    before: ExtraProcessPack | None = None,
) -> StagedPack:
    """편집기가 만든 판(`extra_process_editor.canonical` — 정규 바이트와 그 읽기)을 받은 판 자리에
    싣는다(쓰지 않는다). 판정은 「새 판」 하나다 — 판 번호는 편집기가 마지막 내용 판 + 1 로
    지었고, 그사이 판 이력이 움직였으면 적용이 펼친 차례(`origin.seen_seq`)와 대조해 막는다.
    차이는 펼친 판(`base` — 활성 판, 끈 동안은 마지막 내용 판)과 견주므로 「뺀 공정」 은 편집기에서
    지운 공정이고, `before` 는 그 앞 내용 판(G12)이다. 거절이면 판정 · 차이 없이 거절 표만
    선다."""
    reading = built.reading
    pack = reading.pack
    return StagedPack(
        fetch=SourceFetch(data=built.data, place=EXTRA_EDITOR_PLACE),
        reading=reading,
        judgement=(
            None if pack is None else PackJudgement(JUDGE_APPLY, f"새 판 {pack.info.version_no}")
        ),
        seen_seq=origin.seen_seq,
        staged_at=now,
        changes=None if pack is None else pack_changes(pack, base, before),
        editor=origin,
    )


def previous_content(state: ExtraProcessState) -> ExtraProcessVersion | None:
    """지금 판(활성 판, 끈 동안은 마지막 내용 판 — 세 길이 차이를 견주는 판)의 바로 앞 내용 판
    (sha 가 다른 마지막 내용 줄) — 되돌리는 칸 수(G12)의 견줌 대상."""
    current = state.active or state.latest_content
    if current is None:
        return None
    for item in reversed(state.history):
        if item.seq >= current.seq or item.sha256 is None:
            continue
        if item.sha256 != current.sha256:
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
    # 따라가는 공정 쪽 「대당 Capa 없음 · 0 이하」 줄을 이어받은 수(R-02).
    capacity_gaps: Mapping[str, int] = field(default_factory=dict)


def preview_pack(
    tables: Mapping[str, pd.DataFrame],
    previous_extra: Collection[str],
    pack: ExtraProcessPack,
    *,
    seq: int,
    route_exceptions: RouteLoadDeclaration,
    current: ExtraProcessPack | None = None,
    before: ExtraProcessPack | None = None,
    changes: PackChanges | None = None,
) -> PackPreview:
    """지금 활성 시나리오의 표(`tables`)에 판을 합쳐 본다 — 그 시나리오에 이미 든 부대공정
    (`previous_extra` — 출처에 합침만 있는 것, `split_previous`)은 먼저 걷는다(얹기와 같은 길).
    저장하지 않는다. `seq` 는 미리보기에 쓸 판 차례(아직 적용 전이면 다음 차례)다. `changes` 는
    받은 때 센 차이(`StagedPack.changes`)이고 없으면 `current` · `before` 로 센다.
    `route_exceptions` 는 부르는 화면이 읽은 부하 예외 선언 판이다 — 미리보기 대당 Capa · 부하 줄이
    계산 화면과 같은 판으로 돈다."""
    active = ActiveExtraPack(ExtraPackVersion(seq, pack.info.version_no, pack.sha256), pack)
    result = overlay_extra_processes(tables, previous_extra, active)
    merged = result.report.merged_processes()
    outcome = capacity_outcome(result.tables, route_exceptions=route_exceptions)
    return PackPreview(
        changes=changes if changes is not None else pack_changes(pack, current, before),
        ratio=pack.ratio,
        report=result.report,
        rates=process_rows_frame(
            result.tables, merged, route_exceptions=route_exceptions, outcome=outcome
        ),
        lines=load_lines(result.tables, merged, route_exceptions=route_exceptions, outcome=outcome),
        capacity_gaps=inherited_capacity_gaps(pack, merged, outcome=outcome),
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
