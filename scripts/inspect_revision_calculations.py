# Purpose: 저장된 모든 리비전의 Capa 계산을 읽기 전용으로 다시 돌려 상태와 개수만 찍는다.

"""전 리비전 계산 집계 — 사내 런북 6-3(실 DB 사본 확인)이 부른다.

사내가 배포 `202610120655` 뒤 실 DB 사본으로 손수 잰 「전 리비전 54 계산: 멈춤 1 ·
원천 등록 44 · 복제 4 · 연도 이동 3 · 공식버전 정상 · 확보율 오류 0」을 배포마다 같은
꼴로 다시 잴 수 있게 스크립트로 둔다(그 리뷰 3장 요청). 리뷰 문서에 **그대로 붙이는
Markdown 블록**을 찍는다.

    uv run --no-sync python scripts/inspect_revision_calculations.py \\
        --database <DB 사본> --output <저장소 밖 파일>

**리비전마다 하는 일.** 앱이 리비전을 읽는 길(`repository._load_reference_frame` —
리비전 표 14장은 `rev_data`, 데이터셋 표 둘은 `ref_data`)로 16표를 읽어, 앱의 전체
기간 계산과 같은 차례로 돌린다 — 대당 Capa(`calculate_unit_capacity`) → 소요대수
(`calculate_required_equipment`) → 확보율(`calculate_securement_rate`, `RQ_EQP_AVBL`
÷ 소요대수). 경로 키가 없는 옛 리비전은 앱이 불러오기를 막으므로
(`revision_compatibility`) 계산하지 않고 「불러오기 막힘」으로 센다.

소요대수까지 서면 **저장·발행 검사가 그다음에 보는 Density 환산**도 돌린다
(`capacity_gate.density_error` — HOME 의 `RQ_PKG_PLAN` × `RQ_CHIP_EQ` 를 조회기간이 아닌
시나리오 전체 기간으로, EDP 계획까지). 대당 Capa·소요대수는 `구분_EQ` 를 쓰지 않아 `계산` 이
`됨` 인 리비전도 여기서 멈출 수 있고, 멈추면 그 리비전은 저장할 때 경고가 붙고 공식버전으로
지정할 수 없다. 확보율과는 서로 기대지 않아 둘 다 재고, `계산` 칸과 따로 `Density` 칸에
적는다(「Density 멈춤」).

계산이 끝나면 세 가지를 센다.

- **소요대수에 닿지 않은 계획 줄** — 생산수량이 0 보다 큰 `RQ_PKG_PLAN` 행 가운데,
  그 계획 줄(월·양산구분·제품정보·Stack·Capa Code·Customer·CS)이 부하량이 0 보다 큰
  소요대수 행에 하나도 없는 행. 부하량 환산에서 빠졌거나(Chip·수율 기준 없음) 이어질
  `RQ_REQB` 경로가 없는 계획이다 — 소요대수에서 흔적 없이 빠지면 확보율이 낙관된다
  (정적 감사 P1·P2·E3). 제외 목록에 남았는지와 상관없이 결과 표만 보고 센다.
- **겹친 경로 키** — 소요대수 결과에서 `RQ_REQB` 업무 키 13 이 같은 행 가운데
  둘째부터의 수. 표기만 다른 두 행이 같은 부하를 두 번 받는 자리다(P4).
- **제외 행** — 대당 Capa·소요대수 결과가 `attrs` 로 들고 있는 제외 목록의 행 수.

**지키는 것** — `inspect_real_data_checks.py` 와 같다.

- **읽기만 한다.** DB 를 `read_only=True` 로 열고 저장소(Repository)를 만들지 않는다
  — `initialize()` 는 마이그레이션을 건다(쓰기다).
- **사본에만 돌린다.** `--database` 는 기본값이 없다. 앱은 연산마다 연결을 열고 닫아 쉬는
  동안에는 운영 DB 도 열리지만, 이 스크립트가 수 분 동안 쥐는 사이 사용자 앱의 연결은 다른
  프로세스 잠금으로 곧바로 실패한다. 그래서 **사본** 경로를 늘 적어 준다(런북 6-3).
- **값을 찍지 않는다.** 개수·상태·초만 찍는다. 시나리오·리비전은 이름 대신 차례
  번호(`S3`·`r2`)로 적는다. 예외는 종류(클래스 이름)와 그 문구에 든 **계약 표
  이름(`RQ_*` 16개)** 만 적는다 — 이 앱의 오류 문구에는 공정·제품 이름이 실린다.

사외에서 돌린 수는 합성 표본의 `샘플 관측` 일 뿐 업무 사실이 아니다(AGENTS.md 10-1).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final, TextIO

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capa_simulation.persistence.repository import (  # noqa: E402
    REFERENCE_TABLES,
    _load_reference_frame,
)
from capa_simulation.services.required_equipment import (  # noqa: E402
    REQB_COLUMNS,
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
    calculate_required_equipment,
)
from capa_simulation.services.revision_compatibility import (  # noqa: E402
    route_key_incompatible_tables,
)
from capa_simulation.services.securement_rate import calculate_securement_rate  # noqa: E402
from capa_simulation.services.unit_capacity import (  # noqa: E402
    CAPACITY_EXCLUSIONS_ATTR,
    calculate_unit_capacity,
)

# `capacity_gate` 는 Streamlit 캐시 래퍼 모듈을 함께 불러온다. 실행 문맥 밖이라 래퍼마다 「No
# runtime found」 경고가 표준 오류에 한 줄씩(수십 줄) 찍혀 사내 창을 덮으므로 불러오는 동안만 끈다.
# 끝나면 불러오기 전 단계로 되돌린다 — `benchmark_home.py` 는 로그를 끈 채 이 모듈을 불러온다.
_LOGGING_DISABLED: Final = logging.root.manager.disable
logging.disable(max(_LOGGING_DISABLED, logging.WARNING))
try:
    from capa_simulation.components.capacity_gate import density_error  # noqa: E402
finally:
    logging.disable(_LOGGING_DISABLED)

# 원천 종류(`app_meta.dataset.source_type`, 앱이 적는 값)를 묶어 부르는 이름. 표 차례다.
SOURCE_GROUPS: Final[tuple[tuple[str, str], ...]] = (
    ("BIGDATAQUERY", "원천 등록(BigDataQuery)"),
    ("CSV_CORE_DATA", "원천 등록(CSV)"),
    ("BUILTIN_SYNTHETIC_SEED", "내장 시드"),
    ("DUCKDB_SCENARIO_CLONE", "복제"),
    ("SCENARIO_YEAR_SHIFT", "연도 이동"),
    ("SCENARIO_MONTH_MERGE", "월 병합"),
)
# 계획 줄 — `RQ_PKG_PLAN` 업무 키에서 Pack Code 를 뺀 것. 부하량이 이 단위로 접힌다.
PLAN_LINE_KEYS: Final[tuple[str, ...]] = (
    "생산계획년월",
    "양산구분",
    "제품정보",
    "Stack",
    "Capa Code",
    "Customer",
    "CS",
)
CALCULATED: Final = "됨"
STOPPED: Final = "멈춤"
SECUREMENT_STOPPED: Final = "확보율 멈춤"
BLOCKED: Final = "불러오기 막힘"
UNREADABLE: Final = "읽지 못함"
STATUSES: Final[tuple[str, ...]] = (CALCULATED, STOPPED, SECUREMENT_STOPPED, BLOCKED, UNREADABLE)
# `계산` 칸과 따로 세는 저장·발행 검사의 Density 환산 멈춤. 집계 표의 칸 이름이기도 하다.
DENSITY_STOPPED: Final = "Density 멈춤"
DENSITY_STAGE: Final = "Density"

_HEADER: Final = "<!-- inspect_revision_calculations.py — 아래 블록을 리뷰 문서에 붙인다 -->\n"
_LOCK_MESSAGE: Final = (
    "DB 를 열지 못했습니다 — 다른 프로세스가 지금 쥐고 있다. 운영 DB 는 앱이 쉬는 동안 열리기도 "
    "하지만 그동안 사용자 앱의 연결이 막힌다 — 런북 6-3 대로 사본을 떠 `--database` 로 준다."
)


@dataclass(frozen=True)
class RevisionRow:
    """한 리비전의 자리 — 이름은 들고 다니지 않는다."""

    scenario_no: int
    revision_no: int
    revision_id: str
    dataset_id: str | None
    source_group: str
    archived: bool
    official: tuple[int, ...]


@dataclass
class Outcome:
    """한 리비전을 돌린 결과. 실패는 단계·예외 종류·문구 속 계약 표 이름만 든다."""

    status: str
    stage: str | None = None
    kind: str | None = None
    tables: tuple[str, ...] = ()
    plan_lines: int | None = None
    unreached_lines: int | None = None
    duplicate_route_keys: int | None = None
    capacity_exclusions: int | None = None
    required_exclusions: int | None = None
    # 저장·발행 검사의 Density 환산 — `CALCULATED` 나 `STOPPED`. Capa 계산이 서지 않아 재지
    # 않았으면 None 이다. 멈추면 예외 종류와 문구 속 계약 표 이름만 든다.
    density: str | None = None
    density_kind: str | None = None
    density_tables: tuple[str, ...] = ()
    seconds: float = 0.0


@dataclass
class Totals:
    """원천 묶음 하나의 합."""

    scenarios: set[int] = field(default_factory=set)
    revisions: int = 0
    statuses: Counter[str] = field(default_factory=Counter)
    density_stopped: int = 0
    unreached_revisions: int = 0
    duplicate_revisions: int = 0


def source_group(source_type: str | None) -> str:
    text = str(source_type or "")
    for prefix, label in SOURCE_GROUPS:
        if text.startswith(prefix):
            return label
    return f"그 밖(`{text}`)" if text else "그 밖(빈 값)"


def contract_tables_in(message: str) -> tuple[str, ...]:
    """문구에 든 계약 표 이름만. 그 밖의 글자(공정·제품 이름)는 버린다."""
    return tuple(name for name in REFERENCE_TABLES if name in message)


def _line_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """계획 줄 키를 계산과 같은 꼴로 맞춘다 — 월은 정수, 글자는 앞뒤 공백을 뗀다."""
    prepared = frame.loc[:, list(PLAN_LINE_KEYS)].copy()
    month = pd.to_numeric(prepared["생산계획년월"], errors="coerce")
    prepared["생산계획년월"] = month.astype("Int64")
    for column in PLAN_LINE_KEYS[1:]:
        prepared[column] = prepared[column].astype("string").str.strip()
    return prepared


def unreached_plan_lines(plan: pd.DataFrame, required: pd.DataFrame) -> tuple[int, int]:
    """(생산수량 > 0 인 계획 행 수, 그 가운데 계획 줄이 소요대수에 닿지 않은 행 수).

    닿았다는 것은 그 계획 줄의 소요대수 행이 하나라도 부하량 > 0 이라는 뜻이다.
    """
    quantity = pd.to_numeric(plan["생산수량"], errors="coerce")
    planned = _line_frame(plan.loc[quantity.gt(0)])
    if planned.empty:
        return 0, 0
    load = pd.to_numeric(required["부하량"], errors="coerce")
    reached = _line_frame(required.loc[load.gt(0)]).drop_duplicates()
    joined = planned.merge(reached, on=list(PLAN_LINE_KEYS), how="left", indicator=True)
    return len(planned), int(joined["_merge"].eq("left_only").sum())


def duplicate_route_keys(required: pd.DataFrame) -> int:
    """`RQ_REQB` 업무 키 13 이 같은 소요대수 행 가운데 둘째부터의 수."""
    if required.empty:
        return 0
    return int(required.duplicated(subset=REQB_COLUMNS).sum())


def _exclusion_rows(frame: pd.DataFrame, attr: str) -> int:
    excluded = frame.attrs.get(attr)
    return len(excluded) if isinstance(excluded, pd.DataFrame) else 0


def _failed(stage: str, exc: BaseException) -> tuple[str, str, tuple[str, ...]]:
    return stage, type(exc).__name__, contract_tables_in(str(exc))


def density_check(tables: Mapping[str, pd.DataFrame]) -> tuple[str, str | None, tuple[str, ...]]:
    """(상태, 예외 종류, 문구 속 계약 표 이름) — 저장·발행 검사의 Density 환산.

    검사 함수(`capacity_gate.density_error`)를 그대로 부른다 — 검사가 바뀌면 이 집계도 따라간다.
    그 함수는 `ValueError` 를 잡아 문구로 돌려준다. 그 밖의 예외도 다음 리비전을 재도록 종류로만
    남긴다(그 예외는 앱의 검사도 멈춘다).
    """
    try:
        error = density_error(tables)
    except Exception as exc:  # 문구는 찍지 않는다
        return STOPPED, type(exc).__name__, contract_tables_in(str(exc))
    if error is None:
        return CALCULATED, None, ()
    return STOPPED, ValueError.__name__, contract_tables_in(error)


def calculate(tables: dict[str, pd.DataFrame]) -> Outcome:
    """앱의 전체 기간 계산과 같은 차례로 돌린다. 예외는 단계와 종류로만 남긴다."""
    blocked = route_key_incompatible_tables(tables)
    if blocked:
        return Outcome(BLOCKED, stage="경로 키 없음", tables=tuple(blocked))
    try:
        unit_capacity = calculate_unit_capacity(
            upeh=tables["RQ_UPEH"],
            run_rate=tables["RQ_RUN_RATE"],
            vital=tables["RQ_VITAL"],
            module=tables["RQ_MODULE"],
            run_day=tables["RQ_RUN_DAY"],
            lot_ratio=tables["RQ_LOT_RATIO"],
            wf_ratio=tables["RQ_WF_RATIO"],
        )
    except Exception as exc:  # 한 리비전이 멈춰도 다음 리비전은 잰다. 문구는 찍지 않는다
        stage, kind, named = _failed("대당 Capa", exc)
        return Outcome(STOPPED, stage=stage, kind=kind, tables=named)
    try:
        required = calculate_required_equipment(
            reqb=tables["RQ_REQB"],
            plan=tables["RQ_PKG_PLAN"],
            yield_data=tables["RQ_YLD"],
            chip_qty=tables["RQ_CHIP_QTY"],
            unit_capacity=unit_capacity,
        )
    except Exception as exc:  # 위와 같다
        stage, kind, named = _failed("소요대수", exc)
        return Outcome(STOPPED, stage=stage, kind=kind, tables=named)
    plan_lines, unreached = unreached_plan_lines(tables["RQ_PKG_PLAN"], required)
    outcome = Outcome(
        CALCULATED,
        plan_lines=plan_lines,
        unreached_lines=unreached,
        duplicate_route_keys=duplicate_route_keys(required),
        capacity_exclusions=_exclusion_rows(unit_capacity, CAPACITY_EXCLUSIONS_ATTR),
        required_exclusions=_exclusion_rows(required, REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR),
    )
    # 저장·발행 검사(`capacity_gate._gate_check`)와 같이 Capa 계산이 서면 Density 환산을 본다.
    # 확보율과는 서로 기대지 않아 둘 다 잰다 — 한쪽이 멈춰도 다른 쪽을 가리지 않는다.
    outcome.density, outcome.density_kind, outcome.density_tables = density_check(tables)
    try:
        calculate_securement_rate(tables["RQ_EQP_AVBL"], required)
    except Exception as exc:  # 위와 같다
        outcome.status = SECUREMENT_STOPPED
        outcome.stage, outcome.kind, outcome.tables = _failed("확보율", exc)
    return outcome


def list_revisions(
    connection: duckdb.DuckDBPyConnection, *, active_only: bool
) -> list[RevisionRow]:
    """시나리오는 만든 차례, 리비전은 번호 차례.

    `active_only` 면 시나리오마다 활성 리비전과 공식버전이 가리키는 리비전만 남긴다.
    """
    official: dict[str, list[int]] = {}
    for release_no, revision_id in connection.execute(
        "SELECT release_no, revision_id FROM app_meta.official_release ORDER BY release_no"
    ).fetchall():
        official.setdefault(str(revision_id), []).append(int(release_no))
    rows = connection.execute(
        """
        SELECT s.scenario_id, s.status, s.active_revision_id, d.dataset_id, d.source_type,
               r.revision_id, r.revision_no
        FROM app_meta.scenario AS s
        JOIN app_meta.scenario_revision AS r ON r.scenario_id = s.scenario_id
        LEFT JOIN app_meta.dataset AS d ON d.scenario_id = s.scenario_id
        ORDER BY s.created_at, s.scenario_id, r.revision_no
        """
    ).fetchall()
    numbers: dict[str, int] = {}
    revisions: list[RevisionRow] = []
    for scenario_id, status, active_id, dataset_id, source_type, revision_id, revision_no in rows:
        scenario_no = numbers.setdefault(str(scenario_id), len(numbers) + 1)
        releases = tuple(official.get(str(revision_id), ()))
        if active_only and str(revision_id) != str(active_id) and not releases:
            continue
        revisions.append(
            RevisionRow(
                scenario_no=scenario_no,
                revision_no=int(revision_no),
                revision_id=str(revision_id),
                dataset_id=None if dataset_id is None else str(dataset_id),
                source_group=source_group(source_type),
                archived=str(status) != "ACTIVE",
                official=releases,
            )
        )
    return revisions


def load_tables(
    connection: duckdb.DuckDBPyConnection, revision: RevisionRow
) -> dict[str, pd.DataFrame]:
    if revision.dataset_id is None:
        raise LookupError("데이터셋 없음")
    return {
        name: _load_reference_frame(
            connection, name, revision_id=revision.revision_id, dataset_id=revision.dataset_id
        )
        for name in REFERENCE_TABLES
    }


def inspect_revision(connection: duckdb.DuckDBPyConnection, revision: RevisionRow) -> Outcome:
    started = time.perf_counter()
    try:
        tables = load_tables(connection, revision)
    except Exception as exc:  # 읽지 못한 리비전도 다음 리비전은 잰다
        outcome = Outcome(UNREADABLE, stage="읽기", kind=type(exc).__name__)
    else:
        outcome = calculate(tables)
    outcome.seconds = time.perf_counter() - started
    return outcome


# ------------------------------------------------------------------------------------ 출력


def _count(value: int | None) -> str:
    return "-" if value is None else f"{value:,}"


def _table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def describe(outcome: Outcome) -> str:
    """리비전 한 줄의 계산 칸."""
    if outcome.status == CALCULATED:
        return CALCULATED
    named = ", ".join(outcome.tables) or None
    detail = " · ".join(part for part in (outcome.kind, named) if part is not None)
    stage = outcome.stage or ""
    return f"{outcome.status} — {stage}" + (f"({detail})" if detail else "")


def describe_density(outcome: Outcome) -> str:
    """리비전 한 줄의 Density 칸. Capa 계산이 서지 않아 재지 않았으면 `-` 다."""
    if outcome.density is None:
        return "-"
    if outcome.density == CALCULATED:
        return CALCULATED
    named = ", ".join(outcome.density_tables) or None
    detail = " · ".join(part for part in (outcome.density_kind, named) if part is not None)
    return f"{outcome.density}" + (f"({detail})" if detail else "")


def _totals(revisions: Sequence[RevisionRow], outcomes: Sequence[Outcome]) -> dict[str, Totals]:
    order = [label for _, label in SOURCE_GROUPS]
    groups: dict[str, Totals] = {}
    for revision, outcome in zip(revisions, outcomes, strict=True):
        totals = groups.setdefault(revision.source_group, Totals())
        totals.scenarios.add(revision.scenario_no)
        totals.revisions += 1
        totals.statuses[outcome.status] += 1
        totals.density_stopped += int(outcome.density == STOPPED)
        totals.unreached_revisions += int(bool(outcome.unreached_lines))
        totals.duplicate_revisions += int(bool(outcome.duplicate_route_keys))
    known = [label for label in order if label in groups]
    others = sorted(label for label in groups if label not in order)
    return {label: groups[label] for label in (*known, *others)}


def _totals_row(label: str, totals: Totals) -> list[str]:
    return [
        label,
        _count(len(totals.scenarios)),
        _count(totals.revisions),
        *(_count(totals.statuses[status]) for status in STATUSES),
        _count(totals.density_stopped),
        _count(totals.unreached_revisions),
        _count(totals.duplicate_revisions),
    ]


def _official_line(revisions: Sequence[RevisionRow], outcomes: Sequence[Outcome]) -> str:
    official = [
        (revision, outcome)
        for revision, outcome in zip(revisions, outcomes, strict=True)
        if revision.official
    ]
    if not official:
        return "- 공식버전 — 이력 없음"
    latest, latest_outcome = max(official, key=lambda pair: max(pair[0].official))
    statuses = Counter(outcome.status for _, outcome in official)
    counted = " · ".join(
        f"{status} {statuses[status]:,}" for status in STATUSES if statuses[status]
    )
    # 0 이어야 하는 값이라 0 이어도 적는다(읽는 법).
    density_stopped = sum(outcome.density == STOPPED for _, outcome in official)
    return (
        f"- 공식버전 — 이력이 가리키는 리비전 {len(official):,}개: {counted} · "
        f"{DENSITY_STOPPED} {density_stopped:,} · 최신 공식 "
        f"v{max(latest.official)}(S{latest.scenario_no} r{latest.revision_no}) "
        f"{describe(latest_outcome)} · {DENSITY_STAGE} {describe_density(latest_outcome)}"
    )


def summary_lines(
    revisions: Sequence[RevisionRow], outcomes: Sequence[Outcome], *, active_only: bool
) -> list[str]:
    groups = _totals(revisions, outcomes)
    overall = Totals()
    for totals in groups.values():
        overall.scenarios |= totals.scenarios
        overall.revisions += totals.revisions
        overall.statuses.update(totals.statuses)
        overall.density_stopped += totals.density_stopped
        overall.unreached_revisions += totals.unreached_revisions
        overall.duplicate_revisions += totals.duplicate_revisions
    scope = (
        "시나리오마다 활성 리비전과 공식버전이 가리키는 리비전(`--active-only`)"
        if active_only
        else "모든 리비전(보관 포함)"
    )
    headers = (
        "원천",
        "시나리오",
        "리비전",
        *STATUSES,
        DENSITY_STOPPED,
        "닿지 않은 계획 줄이 있는 리비전",
        "겹친 경로 키가 있는 리비전",
    )
    rows = [
        *(_totals_row(label, totals) for label, totals in groups.items()),
        _totals_row("**합계**", overall),
    ]
    lines = [
        f"- 범위 — {scope}",
        "",
        *_table(headers, rows),
        "",
        _official_line(revisions, outcomes),
    ]
    stops = Counter(
        (
            outcome.status,
            outcome.stage or "",
            outcome.kind or "-",
            ", ".join(outcome.tables) or "-",
        )
        for outcome in outcomes
        if outcome.status != CALCULATED
    )
    stops.update(
        (
            DENSITY_STOPPED,
            DENSITY_STAGE,
            outcome.density_kind or "-",
            ", ".join(outcome.density_tables) or "-",
        )
        for outcome in outcomes
        if outcome.density == STOPPED
    )
    if stops:
        lines.extend(
            [
                "- 멈춘 리비전의 갈래 — 단계 · 예외 종류 · 문구에 든 계약 표 이름(문구는 찍지 "
                "않는다). `Density 멈춤` 은 `계산` 칸과 따로 세어, 확보율에서도 멈춘 리비전은 "
                "두 줄에 든다",
                "",
                *_table(
                    ("상태", "단계", "예외 종류", "문구가 가리키는 표", "리비전"),
                    (
                        [status, stage, kind, named, _count(count)]
                        for (status, stage, kind, named), count in sorted(stops.items())
                    ),
                ),
            ]
        )
    return lines


REVISION_HEADERS: Final[tuple[str, ...]] = (
    "시나리오",
    "리비전",
    "원천",
    "보관",
    "공식",
    "계산",
    "Density(저장·발행 검사)",
    "계획 줄(닿지 않음 / 생산수량 > 0)",
    "겹친 경로 키",
    "제외 행(대당 Capa · 소요대수)",
    "초",
)


def revision_row(revision: RevisionRow, outcome: Outcome) -> list[str]:
    """리비전 표 한 줄. 끝나는 대로 찍는다."""
    lines = (
        "-"
        if outcome.plan_lines is None
        else f"{_count(outcome.unreached_lines)} / {_count(outcome.plan_lines)}"
    )
    exclusions = (
        "-"
        if outcome.capacity_exclusions is None
        else f"{_count(outcome.capacity_exclusions)} · {_count(outcome.required_exclusions)}"
    )
    return [
        f"S{revision.scenario_no}",
        f"r{revision.revision_no}",
        revision.source_group,
        "보관" if revision.archived else "-",
        ", ".join(f"v{number}" for number in revision.official) or "-",
        describe(outcome),
        describe_density(outcome),
        lines,
        _count(outcome.duplicate_route_keys),
        exclusions,
        f"{outcome.seconds:.1f}",
    ]


READING_GUIDE: Final[tuple[str, ...]] = (
    "",
    "- 읽는 법 — `멈춤` 은 앱의 계산 페이지·저장 검사·발행 검사가 멈추는 리비전이다"
    "(대당 Capa 나 소요대수에서 기준정보 계약을 어겼다). `확보율 멈춤` 은 소요대수까지 "
    "섰는데 가용대수(`RQ_EQP_AVBL`)가 없는 공정·달이 있는 리비전이다. `불러오기 막힘` 은 "
    "경로 키 계약보다 앞서 저장돼 앱이 불러오지 않는 리비전이다.",
    "- `Density` 칸은 저장·발행 검사가 Capa 계산 다음에 보는 HOME 의 Density 환산"
    "(`RQ_PKG_PLAN` × `RQ_CHIP_EQ`)이다 — 조회기간이 아니라 시나리오 전체 기간이고 EDP 계획도 "
    "넣는다. `계산` 이 `됨` 이어도 여기서 멈추면(대개 계획이 있는 제품의 `구분_EQ`·`구분_Chip` "
    "이 0 이하) 그 리비전은 저장할 때 경고가 붙고 공식버전으로 지정할 수 없다. `-` 는 Capa "
    "계산이 서지 않아 재지 않은 것이다.",
    "- **공식버전 줄의 `Density 멈춤` 은 0 이어야 한다.** 0 이 아니면 그 공식버전에서 이어 "
    "저장하는 리비전마다 경고가 붙고 공식 발행이 거절된다(고칠 때까지) — 최신 공식의 "
    "`Density` 칸과 갈래 표의 `Density 멈춤` 줄을 그대로 옮긴다.",
    "- `닿지 않음` 은 생산수량이 있는데 소요대수 결과에 그 계획 줄이 하나도 없는 계획 "
    "행 수다 — 부하량 환산에서 빠졌거나 이어질 경로가 없다. `겹친 경로 키` 는 같은 "
    "`RQ_REQB` 업무 키가 두 번 이상 계산된 행 수다. 둘 다 0 이 아니어도 계산은 선다 — "
    "수를 그대로 옮긴다.",
    "- 시나리오·리비전은 만든 차례 번호다(이름이 아니다). 같은 DB 를 다시 돌리면 같은 "
    "번호가 나온다.",
)


class _Sink:
    """조각이 끝나는 대로 화면과 `--output` 파일에 쓴다 — 중간에 멈춰도 앞 조각은 남는다."""

    def __init__(self, path: Path | None) -> None:
        self._file: TextIO | None = (
            None if path is None else path.open("w", encoding="utf-8", newline="\n")
        )

    def emit(self, text: str) -> None:
        print(text, flush=True)
        if self._file is not None:
            self._file.write(text + "\n")
            self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="전 리비전 Capa 계산 집계(읽기 전용). 운영 DB 는 사본으로 준다 — 런북 6-3."
    )
    parser.add_argument(
        "--database",
        type=Path,
        required=True,
        help="시뮬레이션 DuckDB 사본(런북 6-3). 운영 DB 를 주면 그동안 사용자 앱이 막힌다",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="시나리오마다 활성 리비전과 공식버전 대상 리비전만 돌린다(오래 걸릴 때)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="같은 출력을 이 파일에도 쓴다(UTF-8). 저장소 밖 경로를 준다",
    )
    return parser.parse_args(argv)


def _use_utf8_stdout() -> None:
    # Windows 콘솔 기본 코드페이지(cp949)는 이 출력의 기호를 못 쓴다.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass


def _open_read_only(path: Path) -> tuple[duckdb.DuckDBPyConnection | None, str | None, int]:
    """(연결, 실패 한 줄, 종료 코드). 파일 경로는 찍지 않는다 — 이름만."""
    if not path.exists():
        return None, f"`{path.name}` 파일이 없다", 2
    try:
        return duckdb.connect(str(path), read_only=True), None, 0
    except duckdb.IOException:
        return None, _LOCK_MESSAGE, 1
    except duckdb.Error as exc:
        return None, f"`{path.name}` 을 열지 못했다 — {type(exc).__name__}", 2


def main(argv: Sequence[str] | None = None) -> int:
    _use_utf8_stdout()
    args = parse_args(argv)
    # `--output` 은 먼저 비우고 머리 한 줄부터 쓴다 — 일찍 끝나도 지난 실행의 파일이
    # 새것처럼 남지 않는다.
    sink = _Sink(None if args.output is None else Path(args.output))
    try:
        sink.emit(_HEADER)
        return _run(args, sink)
    finally:
        sink.close()


def _run(args: argparse.Namespace, sink: _Sink) -> int:
    path = Path(args.database)
    connection, failure, code = _open_read_only(path)
    if connection is None:
        sink.emit(str(failure))
        return code
    started = time.perf_counter()
    outcomes: list[Outcome] = []
    try:
        revisions = list_revisions(connection, active_only=bool(args.active_only))
    except duckdb.Error as exc:
        connection.close()
        sink.emit(
            f"리비전 목록을 읽지 못했다 — {type(exc).__name__}"
            "(앱이 한 번도 열지 않아 표가 없는 DB 일 수 있다)"
        )
        return 2
    try:
        scenarios = len({revision.scenario_no for revision in revisions})
        archived = len({revision.scenario_no for revision in revisions if revision.archived})
        sink.emit(
            "\n".join(
                [
                    "### 전 리비전 계산 (`inspect_revision_calculations.py`)",
                    "",
                    f"- 실행 {datetime.now():%Y-%m-%d %H:%M} · DB `{path.name}` · 시나리오 "
                    f"{scenarios:,}(보관 {archived:,}) · 리비전 {len(revisions):,}",
                    "",
                    *_table(REVISION_HEADERS, ()),
                ]
            )
        )
        # 리비전마다 끝나는 대로 한 줄 — 중간에 멈춰도 그때까지의 줄이 남는다.
        for revision in revisions:
            outcome = inspect_revision(connection, revision)
            outcomes.append(outcome)
            sink.emit("| " + " | ".join(revision_row(revision, outcome)) + " |")
    except KeyboardInterrupt:
        sink.emit(f"\n- 멈췄다 — 중단(KeyboardInterrupt) · 리비전 {len(outcomes):,}개까지 잼\n")
        raise
    finally:
        connection.close()
    sink.emit(
        "\n".join(
            [
                "",
                *summary_lines(revisions, outcomes, active_only=bool(args.active_only)),
                *READING_GUIDE,
                f"- 걸린 시간 {time.perf_counter() - started:.1f}초",
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
