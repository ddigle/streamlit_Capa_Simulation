# Purpose: 부대공정 판을 BDQ 기준정보 16표에 펼쳐 합치고(R-01 ~ R-07, 공정 단위 전부 아니면 전무)
# 옛 판 행을 걷는다.

"""부대공정 판 펼치기 · 합치기(설계 4-3 · 4-4 — 등록 이음매 ②와 ③ 사이).

**넣는 자리.** BDQ 조회 · 변환이 끝난 16표(`PreparedCoreDataset.reference_tables`)에 판을 펼쳐
덧붙인 **뒤** 프리셋을 만들고 저장한다(설계 D2 (라)). 원천(Core_Data)은 건드리지 않는다. 계산
서비스(부하량 → 대당 Capa → 소요대수 → 확보율)는 고치지 않는다.

**공정마다 전부 아니면 전무**(01 의 줄 차례):

- R-01 졸업 — 같은 이름(대소문자 무시)이 BDQ 표에 있으면 건너뛴다(BDQ 가 이긴다).
- R-02 참조 공정 — 따라가기 꼴은 참조 공정이 이번 `RQ_REQB` 에 있고 소요기준이 같아야 한다. 참조
  공정의 경로 줄을 (월 · 양산구분 · 제품 · Stack · Capa Code · Customer · CS · WF 구분)으로 고유하게
  접어 이어받는다 — 참조 공정에서 셈에 들지 않는 줄(PKG 의 Buffer 밖)도 함께 오고 수를 보고에
  싣는다.
- R-03 제품 — 지정 꼴은 (제품정보, Stack)이 계획에 있어야 하고, CHIP · WF 면 WF 구분이 그 제품의
  `RQ_CHIP_QTY` 에, PKG 면 그 제품의 `RQ_REQB` 에 소요기준 PKG · `WF 구분` Buffer 줄이 하나라도
  있어야 한다(설계 G6 — 2026-11-18 사용자 답 Q6 「경로 표」). WF 구분은 데이터 쪽 글자로 맞춘다.
  모든 줄이 0 행이면 공정을 뺀다.
- R-04 월 — 기간을 이번 데이터 `RQ_PKG_PLAN` 의 월로 자른다.
- R-05 값 표 — 펼친 경로마다 03 · 04 · 05 에서 값을 찾는다. 하나라도 없으면 공정을 뺀다.
- R-06 덧붙임 — 표마다 업무 키 중복을 한 번 더 본다.
- R-07 안전망 — 합친 표로 대당 Capa → 소요대수 → 확보율까지 돌린다. 멈추면 BDQ 만으로 한 번 더
  돌리고, BDQ 만으로는 서면 01 의 줄 차례로 한 공정씩 더해 멈추게 한 공정만 뺀다(설계 G10). BDQ
  만으로도 멈추면 부대공정 탓이 아니라 그대로 둔다.

**옛 판 걷기**(`strip_extra_processes`) — 「부대공정 얹기」 가 바탕 데이터셋의 출처 표로 옛 판
공정의 행을 16표에서 먼저 걷어 낸 뒤 새 판을 합친다(걷지 않으면 R-01 이 옛 판 행을 BDQ 로 잘못
본다). 걷는 것은 출처에 합침(MERGED)만 있는 공정이다(`split_previous`). 월 머지는 두 원본의 출처를
잇는다 — 한 원본에서 합침 · 다른 원본에서 BDQ 에 생김(GRADUATED)인 공정은 그 이름의 행에 판 행과
BDQ 행이 섞여 이름으로 걷으면 BDQ 행까지 지운다. 그런 공정은 걷지 않고 「섞임」 으로 가르고(같은
판 차례로 겹친 두 줄은 저장 전에 `MIXED_REASON` 뺌 줄 하나로 접는다 — `fold_outcomes`), 얹기는 그
바탕을 받지 않는다(`components/scenario_extra_overlay`). 출처에는 달 범위가 없어 한 원본에 그 공정의
줄이 아예 없을 때(판 없이 등록한 원본의 BDQ 행)는 가르지 못한다 — `docs/TODO.md` 부대공정 ②.

Streamlit 실행 문맥을 쓰지 않는 순수 함수다 — 자동 갱신 배경 스레드도 부른다.
"""

from __future__ import annotations

import calendar
import json
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Protocol

import pandas as pd

from capa_simulation.io.core_data_source import load_core_data_contract
from capa_simulation.services.extra_process_pack import (
    BUFFER_WORD,
    CLASS_EXPANSION,
    EquipmentRow,
    ExtraProcessPack,
    ProcessRow,
    ProductivityRow,
    RouteRow,
    wf_key,
)
from capa_simulation.services.frame_contracts import normalize_demand_basis
from capa_simulation.services.required_equipment import (
    PKG_UNCOUNTED_REASON,
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
)
from capa_simulation.services.securement_rate import calculate_securement_rate

if TYPE_CHECKING:
    from capa_simulation.services.simulation_cache import CapacityOutcome

OUTCOME_MERGED: Final = "MERGED"
OUTCOME_DROPPED: Final = "DROPPED"
OUTCOME_GRADUATED: Final = "GRADUATED"
RULE_GRADUATED: Final = "R-01"
RULE_REFERENCE: Final = "R-02"
RULE_PRODUCT: Final = "R-03"
RULE_VALUES: Final = "R-05"
RULE_DUPLICATE: Final = "R-06"
RULE_STOP: Final = "R-07"
# 월 머지 데이터셋의 같은 공정이 한 원본에서 합침 · 다른 원본에서 BDQ 에 생김 — 출처 뺌 줄 까닭.
MIXED_REASON: Final = "월 머지로 판 · BDQ 행이 섞임 — 걷지 않음"
# 연도 Shift 가 출처 줄 메모에 다는 머리(「연도 Shift +1년」) — 달이 판과 어긋난 데이터셋을 가른다.
YEAR_SHIFT_NOTE: Final = "연도 Shift"
# 등록 이음매가 판을 합치지 못한 때(예외)의 메모 낱말 — 판 없이 BDQ 만으로 등록한다.
MERGE_FAILED_WORD: Final = "합치지 못함"
# 부대공정 행을 싣는 표 — 공정 칸이 있는 기준정보 표 열하나(계획 · 수율 · Chip · 표시순서는 BDQ
# 그대로).
PROCESS_TABLES: Final = (
    "RQ_REQB",
    "RQ_UPEH",
    "RQ_LOT_RATIO",
    "RQ_WF_RATIO",
    "RQ_RUN_RATE",
    "RQ_VITAL",
    "RQ_RUN_DAY",
    "RQ_EQP_OWN",
    "RQ_EQP_LENT",
    "RQ_EQP_AVBL",
    "RQ_MODULE",
)
_VARIANT_KEYS: Final = (
    "생산계획년월",
    "양산구분",
    "제품정보",
    "Stack",
    "Capa Code",
    "Customer",
    "CS",
)
_FOLLOW_KEYS: Final = (*_VARIANT_KEYS, "WF 구분")
_PATH_KEYS: Final = (
    "생산계획년월",
    "Area_Name",
    "공정",
    "STEP_SEQ",
    "MCP_SEQ",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
)

CapacityCheck = Callable[[Mapping[str, pd.DataFrame]], str | None]


def capacity_outcome(tables: Mapping[str, pd.DataFrame]) -> CapacityOutcome:
    """세션 없는 전체 기간 계산(`simulation_cache.full_capacity_outcome`). 그 모듈은 캐시 래퍼를
    만들며 Streamlit 을 끌어오므로 부를 때만 import 한다 — 이 모듈을 import 하는 등록 길 · 사내
    스크립트가 Streamlit 없이 서게(실행 문맥 없는 캐시 경고가 표준 오류에 찍히지 않게). 미리보기는
    한 번 계산해 `process_rows_frame` · `load_lines` 에 함께 넘긴다."""
    from capa_simulation.services.simulation_cache import full_capacity_outcome

    return full_capacity_outcome(tables, tables)


@dataclass(frozen=True)
class ExtraPackVersion:
    """출처에 남길 판 — 판 이력 차례 · 판 번호 · 본문 sha256."""

    seq: int
    version_no: int
    sha256: str


@dataclass(frozen=True)
class ActiveExtraPack:
    """DB 의 활성 판과 그 내용(등록 · 얹기가 S3 를 읽지 않고 합친다)."""

    version: ExtraPackVersion
    pack: ExtraProcessPack


@dataclass(frozen=True)
class ProcessOutcome:
    """공정 하나의 합치기 결과 — 합침 · 뺌 · 졸업, 규칙 · 까닭, 표별 행 수, 경로 수."""

    process: str
    outcome: str
    rule: str | None = None
    reason: str = ""
    row_counts: Mapping[str, int] = field(default_factory=dict)
    route_rows: int = 0
    zero_lines: int = 0
    inherited_uncounted: int = 0

    def row_counts_json(self) -> str:
        return json.dumps(dict(self.row_counts), ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class ExtraMergeReport:
    """판 하나를 합친 보고 — 등록 결과 알림 · 리비전 메모 · 출처 표 · 미리보기가 같이 쓴다."""

    version: ExtraPackVersion | None = None
    outcomes: tuple[ProcessOutcome, ...] = ()
    # BDQ 만으로도 R-07 이 멈춰 부대공정을 그대로 둔 때의 까닭(부대공정 탓이 아니다).
    base_stop: str | None = None
    # 판을 합치지 못해(예외) BDQ 만으로 둔 때의 예외 갈래 이름 — `merge_registration_dataset`.
    failed: str | None = None

    def _with(self, kind: str) -> tuple[ProcessOutcome, ...]:
        return tuple(item for item in self.outcomes if item.outcome == kind)

    @property
    def merged(self) -> tuple[ProcessOutcome, ...]:
        return self._with(OUTCOME_MERGED)

    @property
    def dropped(self) -> tuple[ProcessOutcome, ...]:
        return self._with(OUTCOME_DROPPED)

    @property
    def graduated(self) -> tuple[ProcessOutcome, ...]:
        return self._with(OUTCOME_GRADUATED)

    def merged_processes(self) -> tuple[str, ...]:
        return tuple(item.process for item in self.merged)

    def counts_text(self) -> str:
        """「2 합침 · 1 뺌 · 1 BDQ 에 생김」 — 0 인 갈래는 뺀다. 합치지 못했으면 「합치지 못함」."""
        if self.failed is not None:
            return MERGE_FAILED_WORD
        parts = [
            f"{len(self.merged)} 합침",
            *([f"{len(self.dropped)} 뺌"] if self.dropped else []),
            *([f"{len(self.graduated)} BDQ 에 생김"] if self.graduated else []),
        ]
        return " · ".join(parts)

    def memo(self) -> str:
        """리비전 메모 · 공식 발행 메모 · 실행 기록의 조각 — 판이 없으면 빈 글. 값 · 이름은 없다."""
        if self.version is None:
            return ""
        return f"부대공정 판 {self.version.version_no} · {self.counts_text()}"

    def flash_text(self) -> str:
        """등록 결과 알림창 짧은 글 — 「부대공정 2 합침」 · 「부대공정 1 뺌」(설계 3-4 등록 쪽)."""
        return "" if self.version is None else f"부대공정 {self.counts_text()}"

    def detail_lines(self) -> list[str]:
        """뺀 · BDQ 에 생긴 공정과 까닭 — 알림 전문(Alarm)에 싣는다. 합치지 못했으면 그 예외
        갈래(판 없이 BDQ 만으로 등록함)."""
        if self.failed is not None:
            return [f"부대공정 판을 {MERGE_FAILED_WORD} — {self.failed} · BDQ 만으로 등록"]
        return [
            f"{item.process} — {item.rule} {item.reason}".rstrip()
            for item in (*self.dropped, *self.graduated)
        ]


@dataclass(frozen=True)
class MergeResult:
    tables: dict[str, pd.DataFrame]
    report: ExtraMergeReport


def capacity_stop(tables: Mapping[str, pd.DataFrame]) -> str | None:
    """대당 Capa → 소요대수 → 확보율까지 돌려 멈추면 그 글(자동 갱신 판정과 같은 길)."""
    outcome = capacity_outcome(tables)
    if outcome.error is not None:
        return outcome.error
    if outcome.required_equipment is None:
        return "소요대수를 계산하지 못했습니다."
    try:
        calculate_securement_rate(tables["RQ_EQP_AVBL"], outcome.required_equipment)
    except ValueError as exc:
        return str(exc)
    return None


def merge_extra_processes(
    tables: Mapping[str, pd.DataFrame],
    active: ActiveExtraPack | None,
    *,
    check: CapacityCheck = capacity_stop,
) -> MergeResult:
    """판을 16표에 펼쳐 합친 표와 보고. 판이 없으면 받은 표 묶음을 그대로 돌려준다(묶음은 새 dict).

    표를 제자리에서 고치지 않는다 — 더한 표는 새로 이어 붙이고(`_appended`) 나머지는 받은 표
    그대로라 돌려준 묶음은 받은 표와 프레임을 함께 쓴다(얹기 · 미리보기는 걷기가 이미 사본이다)."""
    base = dict(tables)
    if active is None:
        return MergeResult(base, ExtraMergeReport())
    expander = _Expander(base, active.pack)
    outcomes: dict[str, ProcessOutcome] = {}
    additions: dict[str, dict[str, pd.DataFrame]] = {}
    for process in active.pack.processes:
        outcome, added = expander.process(process)
        outcomes[process.name] = outcome
        if added is not None:
            additions[process.name] = added
    merged = _appended(base, additions.values())
    base_stop: str | None = None
    if additions and check(merged) is not None:
        base_stop = check(base)
        if base_stop is None:
            merged = base
            for name, added in additions.items():
                candidate = _appended(merged, (added,))
                stop = check(candidate)
                if stop is None:
                    merged = candidate
                    continue
                outcomes[name] = ProcessOutcome(
                    name,
                    OUTCOME_DROPPED,
                    RULE_STOP,
                    f"이 공정을 더하면 계산이 멈춤 — {stop}",
                    route_rows=outcomes[name].route_rows,
                    zero_lines=outcomes[name].zero_lines,
                    inherited_uncounted=outcomes[name].inherited_uncounted,
                )
    report = ExtraMergeReport(
        active.version,
        tuple(outcomes[process.name] for process in active.pack.processes),
        base_stop,
    )
    return MergeResult(merged, report)


def overlay_extra_processes(
    tables: Mapping[str, pd.DataFrame],
    previous: Collection[str],
    active: ActiveExtraPack,
    *,
    check: CapacityCheck = capacity_stop,
) -> MergeResult:
    """「부대공정 얹기」 — 바탕 리비전 표에서 옛 판 공정(`previous` — 바탕 데이터셋 출처의 합친
    공정)을 먼저 걷고 활성 판을 합친다(설계 4-8 · D19)."""
    return merge_extra_processes(strip_extra_processes(tables, previous), active, check=check)


def overlay_included_processes(
    base_included: Sequence[str], previous: Collection[str], report: ExtraMergeReport
) -> tuple[str, ...]:
    """얹기의 프리셋 포함 공정 — 바탕 프리셋의 포함 공정에서 걷은 옛 판 공정을 빼고 새로 합친
    부대공정을 더한다. 바탕에서 끈 공정은 다시 켜지지 않는다(설계 4-8) — 바탕에서 꺼 둔 옛 판
    부대공정을 새 판으로 다시 합쳐도 꺼진 채다."""
    included = {name.strip() for name in base_included}
    stripped = {name.strip() for name in previous}
    switched_off = stripped - included
    kept = [name for name in base_included if name.strip() not in stripped]
    added = [
        name
        for name in report.merged_processes()
        if name not in kept and name.strip() not in switched_off
    ]
    return tuple([*kept, *added])


def strip_extra_processes(
    tables: Mapping[str, pd.DataFrame], processes: Collection[str]
) -> dict[str, pd.DataFrame]:
    """고른 공정의 행을 공정 칸이 있는 표마다 걷어 낸 사본(STEP 을 더한 행까지 이름으로 걷는다)."""
    names = {name.strip() for name in processes}
    result = {name: frame.copy() for name, frame in tables.items()}
    if not names:
        return result
    for name in PROCESS_TABLES:
        frame = result.get(name)
        if frame is None or "공정" not in frame.columns:
            continue
        keep = ~frame["공정"].astype("string").str.strip().isin(names).fillna(False)
        result[name] = frame.loc[keep].reset_index(drop=True)
    return result


class _Provenance(Protocol):
    """출처 줄의 읽는 칸(`persistence.models.ExtraProcessProvenance`)."""

    @property
    def process_name(self) -> str: ...

    @property
    def outcome(self) -> str: ...

    @property
    def reason(self) -> str | None: ...

    @property
    def sha256(self) -> str: ...


@dataclass(frozen=True)
class PreviousExtras:
    """바탕 데이터셋의 옛 판 공정 — 걷을 것(합침만)과 판 · BDQ 행이 섞여 걷지 않는 것."""

    stripped: tuple[str, ...] = ()
    mixed: tuple[str, ...] = ()


def split_previous(records: Iterable[_Provenance]) -> PreviousExtras:
    """출처 줄 → 걷을 공정 · 섞인 공정(이름 차례는 처음 나온 차례). 합침 줄이 있고 같은 공정에 BDQ
    에 생김 줄이나 섞임 뺌 줄(`MIXED_REASON`)이 있으면 섞임이다(모듈 설명 「옛 판 걷기」)."""
    merged: dict[str, None] = {}
    graduated: set[str] = set()
    mixed: dict[str, None] = {}
    for record in records:
        name = record.process_name
        if record.outcome == OUTCOME_MERGED:
            merged[name] = None
        elif record.outcome == OUTCOME_GRADUATED:
            graduated.add(name)
        elif record.reason == MIXED_REASON:
            mixed[name] = None
    for name in merged:
        if name in graduated:
            mixed[name] = None
    return PreviousExtras(
        stripped=tuple(name for name in merged if name not in mixed), mixed=tuple(mixed)
    )


@dataclass(frozen=True)
class MonthMergeMixing:
    """월 머지 결과의 부대공정 섞임(설계 4-9 · D20 · A14) — 공정 이름(처음 나온 차례).

    `versions` 는 두 원본이 서로 다른 판(sha)의 부대공정 행을 결과에 실은 공정이다 — 「부대공정
    얹기」 로 한 판으로 다시 맞춘다(옛 판 행은 이름으로 걷으면 된다). `bdq` 는 한 원본의 달에는 판
    행, 다른 원본의 달에는 BDQ 행(그 원본 출처에 합침이 없음)이 실린 공정이다 — 이름으로 걷으면 BDQ
    행까지 지워 얹기가 그 바탕을 받지 않는다(`MIXED_REASON`).
    """

    versions: tuple[str, ...] = ()
    bdq: tuple[str, ...] = ()


def month_merge_mixing(
    reqb: pd.DataFrame,
    month_origin: Mapping[int, str],
    provenance: Mapping[str, Sequence[_Provenance]],
) -> MonthMergeMixing:
    """결과 `RQ_REQB`(`reqb`) · 달마다 고른 원본(`month_origin` — 달 → 원본 이름) · 원본마다
    데이터셋 출처로 섞임을 가른다. 출처에 달이 없어 걷기만으로는 가르지 못하던 「판 없이 등록한
    원본의 BDQ 행」 을 결과 행의 달로 가른다(`docs/TODO.md` 부대공정 ④)."""
    names = list(
        dict.fromkeys(record.process_name for records in provenance.values() for record in records)
    )
    process = reqb["공정"].astype("string").str.strip()
    months = pd.to_numeric(reqb["생산계획년월"], errors="coerce")
    versions: list[str] = []
    bdq: list[str] = []
    for name in names:
        kinds: set[str] = set()
        shas: set[str] = set()
        for origin, records in provenance.items():
            origin_months = [month for month, picked in month_origin.items() if picked == origin]
            if not origin_months:
                continue
            present = bool((process.eq(name) & months.isin(origin_months)).fillna(False).any())
            if not present:
                continue
            own = [record for record in records if record.process_name == name]
            if any(record.reason == MIXED_REASON for record in own):
                kinds.update({"extra", "bdq"})
            elif any(record.outcome == OUTCOME_MERGED for record in own):
                kinds.add("extra")
                shas.update(record.sha256 for record in own if record.outcome == OUTCOME_MERGED)
            else:
                kinds.add("bdq")
        if {"extra", "bdq"} <= kinds:
            bdq.append(name)
        elif len(shas) > 1:
            versions.append(name)
    return MonthMergeMixing(tuple(versions), tuple(bdq))


def fold_outcomes(outcomes: Collection[str]) -> tuple[str, bool]:
    """같은 (공정, 판 차례)로 겹친 출처 줄들의 결과 하나와 섞임 여부 — 합침 · BDQ 에 생김이 함께면
    섞임(뺌 + `MIXED_REASON`), 아니면 합침 → BDQ 에 생김 → 뺌 차례로 남는 것(그 이름의 행이 있는
    쪽을 남긴다)."""
    kinds = set(outcomes)
    if {OUTCOME_MERGED, OUTCOME_GRADUATED} <= kinds:
        return OUTCOME_DROPPED, True
    for kind in (OUTCOME_MERGED, OUTCOME_GRADUATED):
        if kind in kinds:
            return kind, False
    return OUTCOME_DROPPED, False


def process_rows_frame(
    tables: Mapping[str, pd.DataFrame],
    processes: Collection[str],
    *,
    outcome: CapacityOutcome | None = None,
) -> pd.DataFrame:
    """미리보기 시험 계산 — 고른 공정의 월별 소요대수 · 가용대수 · 확보율(멈추면 빈 표).
    `outcome` 은 같은 표로 이미 돌린 전체 기간 계산이다(없으면 여기서 돌린다)."""
    if outcome is None:
        outcome = capacity_outcome(tables)
    columns = ["공정", "생산계획년월", "소요대수", "가용대수", "확보율"]
    if outcome.required_equipment is None:
        return pd.DataFrame(columns=columns)
    try:
        rate = calculate_securement_rate(tables["RQ_EQP_AVBL"], outcome.required_equipment)
    except ValueError:
        return pd.DataFrame(columns=columns)
    names = {name.strip() for name in processes}
    picked = rate.loc[rate["공정"].astype("string").str.strip().isin(names).fillna(False)]
    return picked[columns].sort_values(["공정", "생산계획년월"]).reset_index(drop=True)


def load_lines(
    tables: Mapping[str, pd.DataFrame],
    processes: Collection[str],
    *,
    outcome: CapacityOutcome | None = None,
) -> dict[str, tuple[int, int]]:
    """공정마다 (부하가 붙은 경로 수, 부하 0 경로 수) — 미리보기 · 입력 점검이 센다(설계 4-4 끝).
    `outcome` 은 `process_rows_frame` 과 같다."""
    if outcome is None:
        outcome = capacity_outcome(tables)
    counts: dict[str, tuple[int, int]] = {name: (0, 0) for name in processes}
    required = outcome.required_equipment
    if required is None:
        return counts
    rows = [required[["공정", "부하량"]]]
    excluded = required.attrs.get(REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR)
    if isinstance(excluded, pd.DataFrame) and not excluded.empty:
        rows.append(excluded.loc[excluded["제외사유"].ne(PKG_UNCOUNTED_REASON), ["공정", "부하량"]])
    lines = pd.concat(rows, ignore_index=True)
    for name in processes:
        picked = lines.loc[lines["공정"].astype("string").str.strip().eq(name).fillna(False)]
        loaded = int(picked["부하량"].fillna(0).gt(0).sum())
        counts[name] = (loaded, len(picked) - loaded)
    return counts


# 대당 Capa 가 없거나 0 이하라 소요대수에서 빠진 경로의 까닭(`required_equipment` 의 제외 줄).
CAPACITY_GAP_REASONS: Final = frozenset({"대당 Capa 없음", "대당 Capa 0 이하"})


def inherited_capacity_gaps(
    pack: ExtraProcessPack,
    processes: Collection[str],
    *,
    outcome: CapacityOutcome,
) -> dict[str, int]:
    """공정마다 따라가는 공정 쪽 「대당 Capa 없음 · 0 이하」 로 빠지는 경로를 이어받은 수(설계 4-3
    R-02 · 3-4 의 5번).

    따라가기 꼴은 참조 공정의 경로 줄을 그대로 이어받는다 — 참조 공정이 대당 Capa 결손으로
    소요대수에 들지 않는 줄도 부대공정에서는 자기 생산성(공통 값)으로 세어 두 공정의 셈이 갈린다.
    빼지는 않고 수만 센다. `outcome` 은 그 표로 이미 돌린 전체 기간 계산(미리보기 · 입력 점검)이고,
    줄은 참조 공정의 제외 줄을 (월 · 양산구분 · 제품 · Stack · Capa Code · Customer · CS · WF
    구분)으로 접어 경로 기간 안의 것만 센다. PKG 의 Buffer 밖 줄은
    `ProcessOutcome.inherited_uncounted` 가 센다.
    """
    counts: dict[str, int] = {name: 0 for name in processes}
    required = outcome.required_equipment
    excluded = None if required is None else required.attrs.get(REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR)
    if not isinstance(excluded, pd.DataFrame) or excluded.empty:
        return counts
    gaps = excluded.loc[excluded["제외사유"].isin(CAPACITY_GAP_REASONS).fillna(False)]
    if gaps.empty:
        return counts
    gap_process = gaps["공정"].astype("string").str.strip()
    for route in pack.routes:
        if route.process not in counts or not route.follows:
            continue
        picked = gaps.loc[gap_process.eq(route.reference.strip()).fillna(False)]
        if picked.empty:
            continue
        folded = picked[list(_FOLLOW_KEYS)].drop_duplicates()
        months = pd.to_numeric(folded["생산계획년월"], errors="coerce").dropna().astype("int64")
        counts[route.process] += sum(1 for month in months if route.period.covers(int(month)))
    return counts


def _appended(
    base: Mapping[str, pd.DataFrame], additions: Iterable[Mapping[str, pd.DataFrame]]
) -> dict[str, pd.DataFrame]:
    result = dict(base)
    extra = list(additions)
    for name in PROCESS_TABLES:
        frames = [frame[name] for frame in extra if name in frame and not frame[name].empty]
        if frames:
            result[name] = pd.concat([base[name], *frames], ignore_index=True)
    return result


class _Refused(Exception):
    """공정 하나를 뺀다 — 규칙과 까닭."""

    def __init__(self, rule: str, reason: str) -> None:
        super().__init__(rule, reason)
        self.rule = rule
        self.reason = reason


class _Expander:
    """판 한 벌을 이번 BDQ 표에 펼친다(공정 하나씩)."""

    def __init__(self, tables: Mapping[str, pd.DataFrame], pack: ExtraProcessPack) -> None:
        self.tables = tables
        self.pack = pack
        plan = tables["RQ_PKG_PLAN"]
        self.months = sorted({int(month) for month in plan["생산계획년월"].dropna()})
        self.month_set = set(self.months)
        variants = plan[list(_VARIANT_KEYS)].drop_duplicates()
        self.variants = variants.assign(
            생산계획년월=variants["생산계획년월"].astype("int64")
        ).reset_index(drop=True)
        reqb = tables["RQ_REQB"]
        self.reqb = reqb.assign(
            _process=reqb["공정"].astype("string").str.strip(),
            _basis=normalize_demand_basis(reqb["소요기준"]),
            _wf=reqb["WF 구분"].astype("string").str.strip().str.casefold(),
        )
        self.bdq_names = _process_names(tables)
        self.contract_keys = load_core_data_contract().derived_keys

    def process(self, process: ProcessRow) -> tuple[ProcessOutcome, dict[str, pd.DataFrame] | None]:
        if process.name.casefold() in self.bdq_names:
            return (
                ProcessOutcome(
                    process.name,
                    OUTCOME_GRADUATED,
                    RULE_GRADUATED,
                    "BDQ 에 같은 이름의 공정이 있어 BDQ 값으로 셈",
                ),
                None,
            )
        routes = [route for route in self.pack.routes if route.process == process.name]
        zero_lines = 0
        inherited = 0
        frames: list[pd.DataFrame] = []
        try:
            for route in routes:
                rows, uncounted = self._expand(process, route)
                inherited += uncounted
                if rows.empty:
                    zero_lines += 1
                    continue
                frames.append(rows)
            if not frames:
                raise _Refused(RULE_PRODUCT, "모든 경로 줄이 이번 계획 · 경로와 맞물리지 않음")
            reqb = pd.concat(frames, ignore_index=True)
            added = self._values(process, reqb)
            self._check_unique(added)
        except _Refused as refused:
            return (
                ProcessOutcome(
                    process.name,
                    OUTCOME_DROPPED,
                    refused.rule,
                    refused.reason,
                    zero_lines=zero_lines,
                    inherited_uncounted=inherited,
                ),
                None,
            )
        return (
            ProcessOutcome(
                process.name,
                OUTCOME_MERGED,
                reason=(f"계획과 맞물리지 않은 경로 줄 {zero_lines}개" if zero_lines else ""),
                row_counts={name: len(frame) for name, frame in added.items()},
                route_rows=len(added["RQ_REQB"]),
                zero_lines=zero_lines,
                inherited_uncounted=inherited,
            ),
            added,
        )

    # ---- R-02 · R-03 · R-04 경로 펼치기
    def _expand(self, process: ProcessRow, route: RouteRow) -> tuple[pd.DataFrame, int]:
        if route.follows:
            variants, uncounted = self._follow(process, route)
        else:
            variants, uncounted = self._specified(process, route), 0
        if variants.empty:
            return variants, uncounted
        in_period = variants["생산계획년월"].map(
            lambda month: int(month) in self.month_set and route.period.covers(int(month))
        )
        variants = variants.loc[in_period.astype(bool)]
        if variants.empty:
            return variants, uncounted
        rows = variants.assign(
            Area_Name=process.area,
            공정=process.name,
            STEP_SEQ=route.step,
            MCP_SEQ=route.mcp,
            소요기준=process.basis,
        )
        return rows.reset_index(drop=True), uncounted

    def _follow(self, process: ProcessRow, route: RouteRow) -> tuple[pd.DataFrame, int]:
        reference = route.reference.strip()
        picked = self.reqb.loc[self.reqb["_process"].eq(reference).fillna(False)]
        if picked.empty:
            picked = self.reqb.loc[
                self.reqb["_process"].str.casefold().eq(reference.casefold()).fillna(False)
            ]
        if picked.empty:
            raise _Refused(RULE_REFERENCE, f"참조 공정 {reference} 이 이번 경로(RQ_REQB)에 없음")
        bases = set(picked["_basis"].dropna())
        if bases != {process.basis}:
            raise _Refused(RULE_REFERENCE, f"참조 공정 {reference} 의 소요기준이 다름")
        folded = picked[list(_FOLLOW_KEYS)].drop_duplicates()
        folded = folded.assign(생산계획년월=folded["생산계획년월"].astype("int64"))
        uncounted = 0
        if process.basis == "PKG":
            in_months = folded["생산계획년월"].map(
                lambda month: int(month) in self.month_set and route.period.covers(int(month))
            )
            wf = folded["WF 구분"].astype("string").str.strip().str.casefold()
            uncounted = int((in_months.astype(bool) & wf.ne(BUFFER_WORD).fillna(True)).sum())
        return folded.reset_index(drop=True), uncounted

    def _specified(self, process: ProcessRow, route: RouteRow) -> pd.DataFrame:
        product = self.variants.loc[
            self.variants["제품정보"].astype("string").eq(route.product).fillna(False)
            & self.variants["Stack"].astype("string").str.strip().eq(route.stack).fillna(False)
        ]
        if product.empty:
            return product.assign(**{"WF 구분": pd.Series(dtype="string")})
        if process.basis == "PKG":
            spelled = self._pkg_buffer(route)
        else:
            spelled = self._chip_division(route)
        if spelled is None:
            return product.iloc[0:0].assign(**{"WF 구분": pd.Series(dtype="string")})
        return product.assign(**{"WF 구분": spelled}).reset_index(drop=True)

    def _pkg_buffer(self, route: RouteRow) -> str | None:
        """그 제품의 `RQ_REQB` 에 PKG · Buffer 줄이 있으면 데이터 쪽 글자(설계 G6 · Q6)."""
        rows = self.reqb.loc[
            self.reqb["제품정보"].astype("string").eq(route.product).fillna(False)
            & self.reqb["Stack"].astype("string").str.strip().eq(route.stack).fillna(False)
            & self.reqb["_basis"].eq("PKG").fillna(False)
            & self.reqb["_wf"].eq(BUFFER_WORD).fillna(False)
        ]
        if rows.empty:
            return None
        return str(rows["WF 구분"].iloc[0])

    def _chip_division(self, route: RouteRow) -> str | None:
        """그 제품의 `RQ_CHIP_QTY` 에 있는 WF 구분이면 데이터 쪽 글자."""
        chip = self.tables["RQ_CHIP_QTY"]
        rows = chip.loc[
            chip["제품정보"].astype("string").eq(route.product).fillna(False)
            & chip["Stack"].astype("string").str.strip().eq(route.stack).fillna(False)
            & chip["WF 구분"].astype("string").str.strip().str.casefold().eq(wf_key(route.wf))
        ]
        if rows.empty:
            return None
        return str(rows["WF 구분"].iloc[0])

    # ---- R-05 값 표
    def _values(self, process: ProcessRow, reqb: pd.DataFrame) -> dict[str, pd.DataFrame]:
        upeh: dict[tuple[object, ...], dict[str, object]] = {}
        lot: dict[tuple[object, ...], dict[str, object]] = {}
        wafer: dict[tuple[object, ...], dict[str, object]] = {}
        for raw in reqb.to_dict("records"):
            record = {str(key): value for key, value in raw.items()}
            month = int(str(record["생산계획년월"]))
            found = self._productivity(process, record, month)
            key_values = {key: record[key] for key in _PATH_KEYS}
            key_values["생산계획년월"] = month
            key = tuple(key_values[name] for name in _PATH_KEYS)
            upeh.setdefault(
                key,
                {
                    **key_values,
                    "소요기준": process.basis,
                    "UPEH": found.upeh if process.area == "Main" else None,
                    "ST": found.st if process.area == "MI" else None,
                },
            )
            lot.setdefault(
                key,
                {**key_values, "Lot 측정률": 1.0 if found.lot_ratio is None else found.lot_ratio},
            )
            wafer.setdefault(
                key,
                {**key_values, "WF측정률": 1.0 if found.wf_ratio is None else found.wf_ratio},
            )
        classes = sorted(
            {(int(str(row["생산계획년월"])), str(row["양산구분"])) for row in upeh.values()}
        )
        months = sorted({month for month, _ in classes})
        run_rate, vital = [], []
        for month, mass_class in classes:
            rate = self._rate_vital(process, month, mass_class)
            run_rate.append(
                {
                    "생산계획년월": month,
                    "공정": process.name,
                    "양산구분": mass_class,
                    "CAPA_RUN_RATE": rate[0],
                }
            )
            vital.append(
                {
                    "생산계획년월": month,
                    "공정": process.name,
                    "양산구분": mass_class,
                    "편중률": rate[1],
                }
            )
        run_day, own, lent, available = [], [], [], []
        for month in months:
            equipment = self._equipment(process, month)
            days = (
                calendar.monthrange(month // 100, month % 100)[1]
                if equipment.run_day is None
                else equipment.run_day
            )
            lent_value = 0.0 if equipment.lent is None else equipment.lent
            base = {"생산계획년월": month, "공정": process.name}
            run_day.append({**base, "RUN_DAY": days})
            own.append({**base, "설비보유": equipment.owned})
            lent.append({**base, "설비대여평가": lent_value})
            available.append({**base, "가용대수": equipment.owned - lent_value})
        records: dict[str, list[dict[str, object]]] = {
            "RQ_REQB": [
                {str(key): value for key, value in row.items()} for row in reqb.to_dict("records")
            ],
            "RQ_UPEH": list(upeh.values()),
            "RQ_LOT_RATIO": list(lot.values()),
            "RQ_WF_RATIO": list(wafer.values()),
            "RQ_RUN_RATE": run_rate,
            "RQ_VITAL": vital,
            "RQ_RUN_DAY": run_day,
            "RQ_EQP_OWN": own,
            "RQ_EQP_LENT": lent,
            "RQ_EQP_AVBL": available,
            "RQ_MODULE": [{"공정": process.name, "모듈수": process.modules}],
        }
        return {name: self._typed(name, rows) for name, rows in records.items()}

    def _productivity(
        self, process: ProcessRow, record: Mapping[str, object], month: int
    ) -> ProductivityRow:
        mass_class = str(record["양산구분"])
        step, mcp = str(record["STEP_SEQ"]), str(record["MCP_SEQ"])
        product = (str(record["제품정보"]), str(record["Stack"]), wf_key(str(record["WF 구분"])))
        for row in self.pack.productivity:
            if (row.process, row.step, row.mcp) != (process.name, step, mcp):
                continue
            if mass_class not in CLASS_EXPANSION[row.mass_class] or not row.period.covers(month):
                continue
            if row.common or (row.product, row.stack, wf_key(row.wf)) == product:
                return row
        raise _Refused(RULE_VALUES, f"생산성(03) 값이 없는 경로가 있음({month} · {mass_class})")

    def _rate_vital(self, process: ProcessRow, month: int, mass_class: str) -> tuple[float, float]:
        for row in self.pack.rate_vital:
            if (
                row.process == process.name
                and mass_class in CLASS_EXPANSION[row.mass_class]
                and row.period.covers(month)
            ):
                return row.run_rate, row.vital
        raise _Refused(
            RULE_VALUES, f"효율 · 여유율(05) 값이 없는 달이 있음({month} · {mass_class})"
        )

    def _equipment(self, process: ProcessRow, month: int) -> EquipmentRow:
        for row in self.pack.equipment:
            if row.process == process.name and row.period.covers(month):
                return row
        raise _Refused(RULE_VALUES, f"가동일수 · 설비(04) 값이 없는 달이 있음({month})")

    def _typed(self, name: str, rows: Sequence[Mapping[str, object]]) -> pd.DataFrame:
        """BDQ 표와 같은 칸 · 차례 · 형식으로(저장의 칸 집합 대조 — `require_exact_columns`)."""
        template = self.tables[name]
        frame = pd.DataFrame(list(rows), columns=list(template.columns))
        return frame.astype(template.dtypes.to_dict())

    # ---- R-06
    def _check_unique(self, added: Mapping[str, pd.DataFrame]) -> None:
        for name, frame in added.items():
            keys = list(self.contract_keys.get(name, ()))
            if not keys:
                continue
            combined = pd.concat([self.tables[name][keys], frame[keys]], ignore_index=True)
            if bool(combined.duplicated().any()):
                raise _Refused(RULE_DUPLICATE, f"{name} 업무 키가 겹침(같은 경로를 두 번 적음)")


def _process_names(tables: Mapping[str, pd.DataFrame]) -> set[str]:
    """BDQ 표의 공정 이름(대소문자 무시) — 졸업 판정(R-01)이 견준다."""
    names: set[str] = set()
    for name in PROCESS_TABLES:
        frame = tables.get(name)
        if frame is None or "공정" not in frame.columns:
            continue
        values = frame["공정"].dropna().astype("string").str.strip().str.casefold()
        names.update(str(value) for value in values.unique())
    return names


def provenance_rows(report: ExtraMergeReport) -> list[dict[str, object]]:
    """출처 표 줄의 값(판이 없으면 빈 목록) — 저장소 모델로 바꾸는 쪽이 쓴다."""
    if report.version is None:
        return []
    return [
        {
            "process_name": item.process,
            "version_seq": report.version.seq,
            "version_no": report.version.version_no,
            "sha256": report.version.sha256,
            "outcome": item.outcome,
            "rule": item.rule,
            "reason": item.reason or None,
            "row_counts": item.row_counts_json() if item.row_counts else None,
        }
        for item in report.outcomes
    ]
