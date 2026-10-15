# Purpose: 공식버전 자동 갱신 한 회차(조회→등록→판정→리비전 2→발행)를 세션 없이 돌리고 기록한다.

"""공식버전 자동 갱신 한 회차. 규칙은 `services/auto_official_update.py`, 여기는 차례와 기록이다.

**세션이 없는 배경 스레드에서 돈다.** 그래서 `st.cache_data` 래퍼와 `st.session_state` 를 쓰지
않는다 — 계산은 순수 코어(`full_capacity_outcome`·`calculate_securement_rate`)를, 등록은 세션
없는 `scenario_registration`·`full_data_scenario_preset` 을 부른다. 화면의 「지금 실행」도 같은
함수를 부른다.

한 회차의 차례(단계 이름은 실행 기록 `stage` 에 남는다):

1. **회차 선점** — 예약은 날짜 키, 「지금 실행」은 누를 때마다 새 키. 같은 날 예약은 한 번만
   돈다. 같은 프로세스에서 회차가 겹치면(예약과 「지금 실행」) 뒤의 것은 선점하지 않고 돌아간다.
2. **현재 공식버전 확인** — 주차(W##)가 없으면 오류로 끝낸다(아무것도 하지 않는다).
3. **목록 조회 → 후보 고르기** — 새 코드가 없으면 「건너뜀」.
4. **상세 조회·등록** — 화면 등록과 같은 이름·창·메모로 리비전 1(원천 그대로, 전 공정)을 저장한다.
5. **확보율 판정** — 계산이 깨졌으면(Capa 계산 실패, 가용 행 없음 등) 발행하지 않는다.
6. **리비전 2 저장** — 포함 공정 = `RQ_REQB` 공정 − 자동 off − 이어받은 수동 off. 0 개면
   발행하지 않는다.
7. **공식버전 발행** — 발행 검사(`full_capacity_outcome`)를 지나야 발행한다.

어느 단계에서 멈춰도 이미 만든 시나리오·리비전은 남기고 그 단계와 사유를 기록한다.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Final
from uuid import uuid4

import duckdb
import pandas as pd

from capa_simulation.io.bigdataquery_catalog import fetch_simulation_catalog
from capa_simulation.io.company_bigdataquery_adapter import (
    BigDataQueryCoreDataProvider,
    QueryWindow,
    registration_detail_window,
)
from capa_simulation.io.core_data_source import CoreDataProvider
from capa_simulation.persistence.models import (
    AutoOfficialUpdateExclusion,
    AutoOfficialUpdateRun,
    OfficialReleaseSummary,
    ScenarioPreset,
    ScenarioSnapshot,
)
from capa_simulation.persistence.repository import REVISION_TABLES, DuckDBScenarioRepository
from capa_simulation.scenario_preset_state import full_data_scenario_preset
from capa_simulation.scenario_registration import registration_note, save_bigdataquery_scenario
from capa_simulation.services.auto_official_update import (
    CATALOG_WINDOW_DAYS,
    EXCLUSION_AUTO,
    EXCLUSION_INHERITED,
    FILTERED_REVISION_NAME,
    STAGE_LABELS,
    STATUS_ERROR,
    STATUS_PUBLISH_SKIPPED,
    STATUS_PUBLISHED,
    STATUS_SKIPPED,
    TRIGGER_SCHEDULED,
    AutoUpdateConfig,
    MissingOfficialWeek,
    OfficialBaseline,
    ProcessMinimum,
    RunStatus,
    TriggerKind,
    auto_off_processes,
    auto_update_memo,
    included_after_off,
    inherited_manual_off,
    manual_run_key,
    missing_official_message,
    official_release_name,
    process_minimum_rates,
    reqb_process_names,
    resolve_official_baseline,
    scheduled_run_key,
    select_candidate,
    week_label,
)
from capa_simulation.services.bigdataquery_catalog_view import registration_prefill
from capa_simulation.services.core_data_pipeline import fetch_core_data_dataset
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.simulation_cache import full_capacity_outcome

_LOGGER = logging.getLogger(__name__)

BUSY_MESSAGE: Final = "다른 자동 갱신 회차가 아직 돌고 있습니다. 끝난 뒤 다시 실행하세요."
ALREADY_CLAIMED_MESSAGE: Final = "이 회차는 이미 돌았습니다 — 같은 날 예약 회차는 한 번만 돕니다."
INTERRUPTED_REASON: Final = "앱이 이 회차를 끝내기 전에 꺼져 중단됐습니다."

# 같은 프로세스 안에서 회차가 겹치지 않게 한다. 기다리지 않는다 — 겹친 쪽은 선점하지 않고 돌아간다.
_RUN_LOCK = threading.Lock()


@dataclass(frozen=True)
class DetailRequest:
    """상세 조회 공급자를 만들 때 넘기는 값. 화면 등록 폼의 칸과 같은 뜻이다."""

    simulation_code: str
    simulation_name: str
    registered_at: datetime
    window: QueryWindow


CatalogFetcher = Callable[[QueryWindow], pd.DataFrame]
DetailProviderFactory = Callable[[DetailRequest], CoreDataProvider]
Clock = Callable[[], datetime]


def bigdataquery_detail_provider(request: DetailRequest) -> CoreDataProvider:
    """사내 BigDataQuery 상세 조회 공급자. 화면 등록과 같은 인자로 만든다."""
    return BigDataQueryCoreDataProvider(
        simulation_name=request.simulation_name,
        source_registered_at=request.registered_at,
        window=request.window,
    )


@dataclass(frozen=True)
class AutoUpdateSources:
    """원천 두 갈래. 사외 시험은 가짜를 넣는다 — 사외에서는 BigDataQuery 를 부를 수 없다."""

    fetch_catalog: CatalogFetcher = fetch_simulation_catalog
    detail_provider: DetailProviderFactory = bigdataquery_detail_provider


@dataclass(frozen=True)
class AutoUpdateRunResult:
    """한 번 부른 결과. 회차를 잡지 못했으면 `run` 이 없고 `not_run_reason` 이 까닭이다."""

    run: AutoOfficialUpdateRun | None
    not_run_reason: str | None = None


def current_official_baseline(repository: DuckDBScenarioRepository) -> OfficialBaseline:
    """현재 최신 공식버전과 그 주차. 공식버전이 없거나 주차를 읽을 수 없으면 `MissingOfficialWeek`.

    화면이 자동 갱신을 켤 때도 이것으로 먼저 막는다(「공식버전에 n주차(W##) 표시가 있어야 합니다」).
    """
    release = repository.latest_official_release()
    if release is None:
        raise MissingOfficialWeek(missing_official_message())
    scenario = next(
        (
            summary
            for summary in repository.list_scenarios(include_archived=True)
            if summary.scenario_id == release.scenario_id
        ),
        None,
    )
    return resolve_official_baseline(
        release_no=release.release_no,
        release_name=release.release_name,
        scenario_id=release.scenario_id,
        revision_id=release.revision_id,
        scenario_name=release.scenario_name,
        source_simulation_name="" if scenario is None else scenario.source_simulation_name,
        source_registered_at=None if scenario is None else scenario.source_registered_at,
        published_at=release.published_at,
    )


def catalog_window(today: date) -> QueryWindow:
    """목록 조회 기간 — 오늘 포함 `CATALOG_WINDOW_DAYS` 일 전부터(화면 등록의 기본 기간과 같다)."""
    return QueryWindow(start_date=today - timedelta(days=CATALOG_WINDOW_DAYS), end_date=today)


def run_auto_official_update(
    repository: DuckDBScenarioRepository,
    *,
    trigger: TriggerKind,
    run_day: date | None = None,
    sources: AutoUpdateSources | None = None,
    clock: Clock = datetime.now,
    after_publish: Callable[[], None] | None = None,
) -> AutoUpdateRunResult:
    """자동 갱신 한 회차를 돌리고 그 기록을 돌려준다.

    - `trigger`: `SCHEDULED`(예약 — `run_day` 의 날짜 키로 선점) 또는 `MANUAL`(「지금 실행」).
    - `run_day`: 예약 회차의 날짜. 없으면 `clock()` 의 날짜다.
    - `sources`: 목록·상세 조회. 없으면 사내 BigDataQuery 다.
    - `clock`: 지금 시각(OS 시계). 실행 기록의 시각과 상세 조회 창의 「오늘」이 이것을 따른다.
    - `after_publish`: 발행한 뒤 한 번 부른다(수동 발행과 같은 캐시 정리). 실패해도 회차는
      발행으로 남는다.

    설정(키워드·기준 확보율)은 회차를 잡을 때 DB 에서 읽고 그 값을 기록에 남긴다. 켜짐 여부와
    실행 줄 허락은 부르는 쪽(예약·화면)이 본다 — 이 함수는 부르면 돈다.
    """
    if not _RUN_LOCK.acquire(blocking=False):
        return AutoUpdateRunResult(None, BUSY_MESSAGE)
    try:
        started_at = clock()
        settings = repository.load_auto_official_update_settings()
        day = run_day or started_at.date()
        run_key = (
            scheduled_run_key(day)
            if trigger == TRIGGER_SCHEDULED
            else manual_run_key(started_at, uuid4().hex[:12])
        )
        run_id = repository.claim_auto_official_update_run(
            run_key=run_key,
            trigger_kind=trigger,
            run_date=day,
            started_at=started_at,
            keyword=settings.config.keyword,
            threshold=settings.config.threshold,
            settings_version=settings.version,
        )
        if run_id is None:
            return AutoUpdateRunResult(None, ALREADY_CLAIMED_MESSAGE)
        log = _RunLog(repository, run_id, clock)
        try:
            _execute(
                repository,
                log,
                settings.config,
                sources or AutoUpdateSources(),
                clock,
                after_publish,
            )
        except Exception as exc:  # 배경 회차다. 기록 없이 죽으면 아무도 모른다.
            _LOGGER.exception(
                "공식버전 자동 갱신 회차 %s 가 %s 단계에서 멈췄습니다.", run_id, log.stage
            )
            log.fail(exc)
        return AutoUpdateRunResult(repository.load_auto_official_update_run(run_id))
    finally:
        _RUN_LOCK.release()


def abandon_interrupted_runs(
    repository: DuckDBScenarioRepository, *, started_before: datetime, now: datetime
) -> int:
    """앱이 회차 도중에 꺼져 「실행 중」으로 남은 기록을 오류로 닫는다. 기동한 뒤 한 번 부른다."""
    return repository.abandon_running_auto_official_update_runs(
        started_before=started_before, finished_at=now, reason=INTERRUPTED_REASON
    )


class _RunLog:
    """회차 행을 단계마다 고쳐 쓴다. 지금 단계를 기억해 실패 사유 앞에 붙인다."""

    def __init__(self, repository: DuckDBScenarioRepository, run_id: str, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock
        self.run_id = run_id
        self.stage = "claim"

    def advance(self, stage: str, **values: object) -> None:
        self.stage = stage
        self._repository.update_auto_official_update_run(self.run_id, {"stage": stage, **values})

    def note(self, **values: object) -> None:
        self._repository.update_auto_official_update_run(self.run_id, values)

    def finish(self, status: RunStatus, reason: str, **values: object) -> None:
        payload: dict[str, object] = {
            "status": status,
            "reason": reason,
            "finished_at": self._clock(),
            **values,
        }
        if status == STATUS_PUBLISHED:
            payload["stage"] = "done"
        self._repository.update_auto_official_update_run(self.run_id, payload)

    def fail(self, exc: BaseException) -> None:
        """예상하지 못한 실패를 그 단계 이름과 함께 남긴다. 남기지 못하면 로그만 남긴다."""
        label = STAGE_LABELS.get(self.stage, self.stage)
        try:
            self.finish(STATUS_ERROR, f"{label} 단계에서 멈췄습니다 — {_error_text(exc)}")
        except Exception:
            _LOGGER.exception("자동 갱신 회차 %s 의 실패를 기록하지 못했습니다.", self.run_id)


def _error_text(exc: BaseException) -> str:
    """사유에 적을 글. 이 저장소가 한국어 문구로 올리는 예외는 문구만, 나머지는 종류도 적는다."""
    if isinstance(exc, KeyError) and exc.args:
        return str(exc.args[0])
    if isinstance(exc, (ValueError, RuntimeError, KeyError)) and not isinstance(exc, duckdb.Error):
        return str(exc) or type(exc).__name__
    return f"{type(exc).__name__}: {exc}"


def _execute(
    repository: DuckDBScenarioRepository,
    log: _RunLog,
    config: AutoUpdateConfig,
    sources: AutoUpdateSources,
    clock: Clock,
    after_publish: Callable[[], None] | None,
) -> None:
    log.advance("baseline")
    try:
        baseline = current_official_baseline(repository)
    except MissingOfficialWeek as exc:
        log.finish(STATUS_ERROR, str(exc))
        return
    log.note(baseline_release_no=baseline.release_no, baseline_week=baseline.week)

    log.advance("catalog")
    today = clock().date()
    window = catalog_window(today)
    catalog = sources.fetch_catalog(window)

    log.advance("select")
    registered_codes = {
        summary.source_simulation_code
        for summary in repository.list_scenarios(include_archived=True)
    }
    selection = select_candidate(
        catalog,
        keyword=config.keyword,
        registered_codes=registered_codes,
        baseline=baseline,
    )
    log.note(candidate_count=selection.newer)
    candidate = selection.chosen
    if candidate is None:
        log.finish(STATUS_SKIPPED, selection.skip_reason(config.keyword, baseline))
        return
    log.note(
        simulation_code=candidate.simulation_code,
        simulation_name=candidate.row.simulation_name,
        simulation_week=candidate.week,
        source_registered_at=candidate.registered_at,
    )

    log.advance("register")
    detail_window = registration_detail_window(
        candidate.first_registered_on, candidate.last_registered_on, today=today
    )
    log.note(detail_window=detail_window.label())
    prefill = registration_prefill(candidate.row, catalog_window_label=window.label())
    provider = sources.detail_provider(
        DetailRequest(
            simulation_code=candidate.simulation_code,
            simulation_name=prefill.source_name,
            registered_at=candidate.registered_at,
            window=detail_window,
        )
    )
    prepared = fetch_core_data_dataset(
        provider, candidate.simulation_code, repository.load_global_display_order().rules
    )
    previous_preset = repository.load_revision_preset(baseline.revision_id)
    base = save_bigdataquery_scenario(
        repository,
        prepared,
        # 레거시 확보·경고 값은 직전 공식버전 프리셋에서 실어 온다. 판정 기준 프로필을 한 번도
        # 저장하지 않은 DB 는 그 기본값을 최신 공식버전 프리셋에서 읽기 때문이다 — 코드 기본값을
        # 실으면 발행하는 순간 모든 화면의 판정 기준이 바뀐다.
        full_data_scenario_preset(
            prepared.reference_tables,
            secure_threshold=previous_preset.secure_threshold,
            warning_threshold=previous_preset.warning_threshold,
        ),
        scenario_name=prefill.scenario_name,
        revision_name=prefill.revision_name,
        note=registration_note(f"자동 갱신 등록 · {prefill.note}", detail_window),
    )
    log.note(
        created_scenario_id=base.scenario.scenario_id,
        created_scenario_name=base.scenario.scenario_name,
        base_revision_id=base.revision.revision_id,
    )

    log.advance("judge")
    outcome = full_capacity_outcome(base.tables, base.tables)
    if outcome.error is not None or outcome.required_equipment is None:
        log.finish(
            STATUS_PUBLISH_SKIPPED,
            "Capa 계산이 실패해 확보율을 판정하지 못했습니다 — 발행하지 않았습니다. "
            f"{outcome.error}",
        )
        return
    try:
        securement = calculate_securement_rate(
            base.tables["RQ_EQP_AVBL"], outcome.required_equipment
        )
    except ValueError as exc:
        log.finish(
            STATUS_PUBLISH_SKIPPED,
            f"확보율 계산이 실패해 판정하지 못했습니다 — 발행하지 않았습니다. {exc}",
        )
        return
    processes = reqb_process_names(base.tables["RQ_REQB"])
    minimums = {minimum.process: minimum for minimum in process_minimum_rates(securement)}
    inherited = _inherited_manual_off(repository, baseline, previous_preset, processes)
    # 사람이 뺀 공정은 이번 판정에서 기준 미만이어도 「이어받은 수동 off」로 둔다. 자동 off 로
    # 적으면 다음 주에 확보율이 오른 순간 사람의 결정과 상관없이 되살아난다.
    auto_off = tuple(
        minimum
        for minimum in auto_off_processes(minimums.values(), config.threshold, processes)
        if minimum.process not in inherited
    )
    included = included_after_off(processes, {minimum.process for minimum in auto_off}, inherited)
    exclusions = _exclusions(log.run_id, auto_off, inherited, minimums)
    memo = auto_update_memo(
        threshold=config.threshold,
        auto_off_count=len(auto_off),
        inherited_off_count=len(inherited),
    )
    log.note(auto_off_count=len(auto_off), inherited_off_count=len(inherited))
    if not included:
        repository.record_auto_official_update_exclusions(exclusions)
        log.finish(
            STATUS_PUBLISH_SKIPPED,
            f"공정 필터에 남는 공정이 없어 리비전 2 를 저장하지 않고 발행하지 않았습니다 — {memo}",
        )
        return

    log.advance("revision")
    filtered = repository.save_revision(
        base.scenario.scenario_id,
        {name: base.tables[name] for name in REVISION_TABLES},
        replace(base.preset, included_processes=included),
        revision_name=FILTERED_REVISION_NAME,
        parent_revision_id=base.revision.revision_id,
        note=memo,
    )
    filtered_revision_id = filtered.revision.revision_id
    repository.record_auto_official_update_exclusions(
        [replace(exclusion, filtered_revision_id=filtered_revision_id) for exclusion in exclusions]
    )
    log.note(filtered_revision_id=filtered_revision_id)

    log.advance("publish")
    published = _publish_filtered_revision(
        repository,
        filtered,
        release_name=official_release_name(filtered.scenario.scenario_name),
        note=memo,
    )
    if isinstance(published, str):
        log.finish(
            STATUS_PUBLISH_SKIPPED,
            f"발행 검사에서 Capa 계산이 실패해 발행하지 않았습니다. {published}",
        )
        return
    if after_publish is not None:
        try:
            after_publish()
        except Exception:
            _LOGGER.exception("자동 갱신 발행 뒤 캐시 정리가 실패했습니다.")
    log.finish(
        STATUS_PUBLISHED,
        f"공식 v{published.release_no} 발행 · {week_label(candidate.week)} "
        f"{candidate.simulation_code} · {memo}",
        official_release_id=published.official_release_id,
        official_release_no=published.release_no,
    )


def _publish_filtered_revision(
    repository: DuckDBScenarioRepository,
    snapshot: ScenarioSnapshot,
    *,
    release_name: str,
    note: str,
) -> OfficialReleaseSummary | str:
    """발행 검사(공식 발행 화면과 같은 전체 기간 Capa 계산)를 지나면 발행한다. 실패하면 그 오류 글.

    검사를 쓰기 **앞에** 부른다(`tests/test_capacity_gate.py` 가 이 차례를 지킨다).
    """
    error = full_capacity_outcome(snapshot.tables, snapshot.tables).error
    if error is not None:
        return error
    return repository.publish_official_revision(
        snapshot.scenario.scenario_id,
        snapshot.revision.revision_id,
        release_name=release_name,
        note=note,
    )


def _inherited_manual_off(
    repository: DuckDBScenarioRepository,
    baseline: OfficialBaseline,
    previous_preset: ScenarioPreset,
    processes: tuple[str, ...],
) -> tuple[str, ...]:
    """직전 공식버전에서 사람이 손으로 뺀 공정(새 데이터에도 있는 것).

    자동 갱신이 뺀 공정은 직전 공식 리비전과 **그 조상**의 `AUTO` 기록에서 찾는다 — 자동
    리비전 2 에서 사람이 리비전 3 을 저장해 발행했어도 리비전 2 의 자동 off 는 자동으로 남는다.
    """
    previous_processes = reqb_process_names(
        repository.load_revision_table(baseline.revision_id, "RQ_REQB")
    )
    lineage = _revision_lineage(repository, baseline.scenario_id, baseline.revision_id)
    previous_auto = {
        exclusion.process
        for exclusion in repository.list_auto_official_update_exclusions(
            filtered_revision_ids=lineage
        )
        if exclusion.kind == EXCLUSION_AUTO
    }
    return inherited_manual_off(
        previous_processes=previous_processes,
        previous_included=previous_preset.included_processes,
        previous_auto_off=previous_auto,
        current_processes=processes,
    )


def _revision_lineage(
    repository: DuckDBScenarioRepository, scenario_id: str, revision_id: str
) -> tuple[str, ...]:
    """리비전과 그 조상(부모를 따라 올라간 차례)."""
    parents: Mapping[str, str | None] = {
        revision.revision_id: revision.parent_revision_id
        for revision in repository.list_revisions(scenario_id)
    }
    chain: list[str] = []
    current: str | None = revision_id
    while current is not None and current not in chain:
        chain.append(current)
        current = parents.get(current)
    return tuple(chain)


def _exclusions(
    run_id: str,
    auto_off: tuple[ProcessMinimum, ...],
    inherited: tuple[str, ...],
    minimums: Mapping[str, ProcessMinimum],
) -> list[AutoOfficialUpdateExclusion]:
    """기록할 off 공정. 두 묶음은 겹치지 않는다(겹치면 이어받은 쪽이다). 이어받은 공정도 이번 판정의
    최저 확보율이 있으면 함께 적는다."""
    rows = [
        AutoOfficialUpdateExclusion(
            run_id=run_id,
            filtered_revision_id=None,
            process=minimum.process,
            kind=EXCLUSION_AUTO,
            min_rate=minimum.min_rate,
            min_month=minimum.month,
        )
        for minimum in auto_off
    ]
    for process in inherited:
        minimum = minimums.get(process)
        rows.append(
            AutoOfficialUpdateExclusion(
                run_id=run_id,
                filtered_revision_id=None,
                process=process,
                kind=EXCLUSION_INHERITED,
                min_rate=None if minimum is None else minimum.min_rate,
                min_month=None if minimum is None else minimum.month,
            )
        )
    return rows
