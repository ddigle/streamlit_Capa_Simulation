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
3. **목록 조회 → 후보 고르기** — 새 코드가 없으면 「건너뜀」. 지금 남은 시나리오(보관본 포함)의
   원천 코드와 **자동 갱신이 한 번 받은 코드**(실행 기록)는 다시 받지 않는다 — 사람이 자동
   발행본을 지워 되돌려도 다음 날 같은 코드가 되살아나지 않는다. 다시 쓰려면 BigDataQuery 등록
   으로 손으로 받는다.
4. **상세 조회·등록** — 화면 등록과 같은 이름·창·메모로 리비전 1(원천 그대로, 전 공정)을 저장한다.
5. **확보율 판정** — 계산이 깨졌으면(Capa 계산 실패, 가용 행 없음 등) 발행하지 않는다.
6. **리비전 2 저장** — 포함 공정 = `RQ_REQB` 공정 − 자동 off − 이어받은 수동 off. 판정할 수 있는
   (확보율이 있는) 포함 공정이 0 개면 발행하지 않는다.
7. **공식버전 발행** — 발행 검사(`full_capacity_outcome`)를 지나야 발행한다. 회차를 시작할 때 본
   공식버전이 그 사이 바뀌었으면(사람이 다른 공식버전을 지정) 발행하지 않는다 — 옛 기준으로 고른
   코드가 더 새 공식버전을 덮지 않게 한다. 계산은 되지만 소요대수에 들지 않은 수요가 있으면 막지
   않고 그 건수 경고를 발행 기록의 사유 끝에 붙인다 — 화면 발행이 성공 문구 밑에 띄우는 것과 같은
   셈·문장이다. 「지금 실행」 결과는 그 경고를 사유에서 다시 갈라(`split_published_reason`) 화면
   발행과 같이 성공 알림 밑에 따로 띄운다.

어느 단계에서 멈춰도 이미 만든 시나리오·리비전은 남기고 그 단계와 사유를 기록한다.

**자동 off 와 수동 off 의 구분.** 직전 공식버전 프리셋에서 빠진 공정 가운데 자동 갱신이 뺀 것
(`AUTO` 기록)은 매번 다시 판정하고, 나머지는 사람이 뺀 것으로 이어받는다. `AUTO` 기록은 그
리비전과 조상(부모 사슬)에서 찾는다. 「현재 활성 편집본 복제」로 만든 시나리오는 부모가 없이
세션 프리셋을 그대로 싣기 때문에, 그 시나리오에서는 가장 최근 자동 회차(리비전 2 를 저장한
회차)의 `AUTO` 기록을 함께 본다.
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

from capa_simulation.components.capacity_gate import density_error
from capa_simulation.components.required_exclusion_notice import (
    FULL_SCOPE,
    UNCOUNTED_DEMAND_LEAD,
    required_exclusion_message,
)
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
from capa_simulation.persistence.repository import (
    REVISION_TABLES,
    DuckDBScenarioRepository,
    OfficialReleaseMoved,
)
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
    auto_off_mark,
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
from capa_simulation.services.required_equipment import required_exclusion_counts
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.simulation_cache import CapacityOutcome, full_capacity_outcome

_LOGGER = logging.getLogger(__name__)

BUSY_MESSAGE: Final = "다른 자동 갱신 회차가 아직 돌고 있습니다. 끝난 뒤 다시 실행하세요."
ALREADY_CLAIMED_MESSAGE: Final = "이 회차는 이미 돌았습니다 — 같은 날 예약 회차는 한 번만 돕니다."
INTERRUPTED_REASON: Final = "앱이 이 회차를 끝내기 전에 꺼져 중단됐습니다."
# 등록한 뒤 발행까지 가지 못한 회차의 사유 끝에 붙인다. 그 코드는 다시 받지 않는다.
REGISTERED_NOT_PUBLISHED_NOTE: Final = (
    "등록한 시나리오 「{name}」는 남겼습니다 — 같은 코드는 다시 받지 않으니 확인한 뒤 손으로 "
    "발행하세요."
)
# 「현재 활성 편집본 복제」가 만든 시나리오의 출처 종류. 부모 리비전이 없다.
CLONE_SOURCE_TYPE: Final = "DUCKDB_SCENARIO_CLONE"
# 발행한 회차의 사유 한 칸에 발행 줄과 소요대수에 들지 않은 수요 경고를 잇는 자리.
_WARNING_SEPARATOR: Final = ". "

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


@dataclass(frozen=True)
class _PublishedRelease:
    """발행 검사를 지나 쓴 공식버전과, 막지 않고 실행 기록에 남길 경고(없으면 빈 문자열)."""

    release: OfficialReleaseSummary
    warning: str = ""


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
        source_simulation_code=release.source_simulation_code,
        source_type="" if scenario is None else scenario.source_type,
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
    manual_token: str | None = None,
) -> AutoUpdateRunResult:
    """자동 갱신 한 회차를 돌리고 그 기록을 돌려준다.

    - `trigger`: `SCHEDULED`(예약 — `run_day` 의 날짜 키로 선점) 또는 `MANUAL`(「지금 실행」).
    - `run_day`: 예약 회차의 날짜. 없으면 `clock()` 의 날짜다.
    - `sources`: 목록·상세 조회. 없으면 사내 BigDataQuery 다.
    - `clock`: 지금 시각(OS 시계). 실행 기록의 시각과 상세 조회 창의 「오늘」이 이것을 따른다.
    - `after_publish`: 발행한 뒤 한 번 부른다(수동 발행과 같은 캐시 정리). 실패해도 회차는
      발행으로 남는다.
    - `manual_token`: 「지금 실행」 회차 키의 끝에 붙일 표. 화면이 회차 전에 세션에 적어 두고, 결과
      알림이 rerun 에 끊겨도 다음 회차에 그 표로 기록을 찾는다. 없으면 새로 만든다.

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
            else manual_run_key(started_at, manual_token or uuid4().hex[:12])
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
        except BaseException as exc:  # 배경 회차다. 기록 없이 죽으면 아무도 모른다.
            # `SystemExit` 처럼 Exception 밖의 것도 실제 사유로 남긴 뒤 다시 올린다 — 실행 흐름
            # 신호(KeyboardInterrupt·Streamlit 의 rerun/stop)를 삼키지 않는다. 배경 스레드는
            # 예약 쪽이 받아 스레드를 지킨다(`auto_update_scheduler`).
            _LOGGER.exception(
                "공식버전 자동 갱신 회차 %s 가 %s 단계에서 멈췄습니다.", run_id, log.stage
            )
            log.fail(exc)
            if not isinstance(exc, Exception):
                raise
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
        # 리비전 1 을 저장했으면 그 시나리오명. 발행까지 가지 못하고 끝나면 사유 끝에 적는다.
        self.registered_name: str | None = None

    def advance(self, stage: str, **values: object) -> None:
        self.stage = stage
        self._repository.update_auto_official_update_run(self.run_id, {"stage": stage, **values})

    def note(self, **values: object) -> None:
        self._repository.update_auto_official_update_run(self.run_id, values)

    def finish(self, status: RunStatus, reason: str, **values: object) -> None:
        if status != STATUS_PUBLISHED and self.registered_name is not None:
            note = REGISTERED_NOT_PUBLISHED_NOTE.format(name=self.registered_name)
            reason = f"{reason.rstrip().rstrip('.')}. {note}"
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
    existing_codes = {
        summary.source_simulation_code
        for summary in repository.list_scenarios(include_archived=True)
    }
    received = received_codes(repository)
    selection = select_candidate(
        catalog,
        keyword=config.keyword,
        registered_codes=existing_codes | received,
        baseline=baseline,
    )
    log.note(candidate_count=selection.newer)
    candidate = selection.chosen
    if candidate is None:
        reason = selection.skip_reason(config.keyword, baseline)
        listed_codes = set(catalog["simulation_code"].astype("string").str.strip().dropna())
        held_back = (received - existing_codes) & listed_codes
        if held_back:
            reason += (
                f" · 목록의 {len(held_back):,}건은 자동 갱신이 이미 받았다가 시나리오가 지워진 "
                "코드라 다시 받지 않았습니다(다시 쓰려면 BigDataQuery 등록으로 받으세요)"
            )
        log.finish(STATUS_SKIPPED, reason)
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
    log.registered_name = base.scenario.scenario_name

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
    # 확보율이 있어 판정할 수 있는 포함 공정. `RQ_REQB` 에만 있고 확보율 행이 없는 공정은 B/N 에
    # 나오지 않으므로, 그것만 남으면 B/N 이 빈 공식버전이 된다.
    judged_included = [process for process in included if process in minimums]
    if not judged_included:
        repository.record_auto_official_update_exclusions(exclusions)
        cause = (
            "공정 필터에 남는 공정이 없어"
            if not included
            else f"공정 필터에 남는 공정 {len(included)}개가 모두 확보율로 판정할 수 없는 "
            "공정(확보율 행 없음)이라"
        )
        log.finish(
            STATUS_PUBLISH_SKIPPED,
            f"{cause} 리비전 2 를 저장하지 않고 발행하지 않았습니다 — {memo}",
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
    try:
        published = _publish_filtered_revision(
            repository,
            filtered,
            release_name=official_release_name(filtered.scenario.scenario_name),
            note=memo,
            expected_latest_release_no=baseline.release_no,
        )
    except OfficialReleaseMoved as exc:
        log.finish(STATUS_PUBLISH_SKIPPED, str(exc))
        return
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
    release = published.release
    reason = (
        f"공식 v{release.release_no} 발행 · {week_label(candidate.week)} "
        f"{candidate.simulation_code} · {memo}"
    )
    if published.warning:
        reason = f"{reason}{_WARNING_SEPARATOR}{published.warning}"
    log.finish(
        STATUS_PUBLISHED,
        reason,
        official_release_id=release.official_release_id,
        official_release_no=release.release_no,
    )


def _publish_filtered_revision(
    repository: DuckDBScenarioRepository,
    snapshot: ScenarioSnapshot,
    *,
    release_name: str,
    note: str,
    expected_latest_release_no: int,
) -> _PublishedRelease | str:
    """발행 검사(공식 발행 화면과 같은 전체 기간 Capa 계산·Density 환산)를 지나면 발행한다. 실패하면
    그 오류 글.

    검사를 쓰기 **앞에** 부른다(`tests/test_capacity_gate.py` 가 이 차례를 지킨다). 판정 단계와 같은
    표를 한 번 더 계산한다 — 발행 검사를 판정 결과에 기대지 않고 수동 발행과 같은 문으로 지나게
    하려는 것이고, 배경 회차라 그 몇 초를 받아들인다. 최신 공식버전이 `expected_latest_release_no`
    에서 바뀌었으면 `OfficialReleaseMoved` 다(아무것도 쓰지 않는다).

    지나면 공식버전과 함께 소요대수에 들지 않은 수요 경고를 돌려준다. 화면 발행 검사
    (`capacity_gate._calculated_verdict`)와 같이 막지 않는다 — 부르는 쪽이 실행 기록 사유에 붙인다.
    공식버전 메모(`note`)에는 싣지 않는다 — 화면 발행도 메모는 지정한 사람의 글 그대로다.
    """
    # 화면 발행 검사(`official_publish_verdict`)와 같이 Capa 계산이 통과하면 Density 환산도 본다.
    outcome = full_capacity_outcome(snapshot.tables, snapshot.tables)
    error = outcome.error or density_error(snapshot.tables)
    if error is not None:
        return error
    warning = _uncounted_demand_warning(outcome)
    release = repository.publish_official_revision(
        snapshot.scenario.scenario_id,
        snapshot.revision.revision_id,
        release_name=release_name,
        note=note,
        expected_latest_release_no=expected_latest_release_no,
    )
    return _PublishedRelease(release, warning)


def _uncounted_demand_warning(outcome: CapacityOutcome) -> str:
    """발행 검사 결과의 소요대수에 들지 않은 수요 경고(시나리오 전체 기간). 없으면 빈 문자열.

    화면 발행 검사와 같은 셈(`required_exclusion_counts`)·문장(`required_exclusion_message`)이다.
    실행 기록 사유는 기록 표의 칸에도 그대로 실려 Markdown 굵게 표시(`**`)만 뗀다.
    """
    if outcome.required_equipment is None:
        return ""
    message = required_exclusion_message(
        required_exclusion_counts(outcome.required_equipment), scope=FULL_SCOPE
    )
    return message.replace("**", "")


def split_published_reason(reason: str) -> tuple[str, str]:
    """발행한 회차의 사유를 (발행 줄, 소요대수에 들지 않은 수요 경고)로 가른다. 경고가 없으면 빈 글.

    실행 기록에는 사유 한 칸뿐이라 회차가 둘을 이어 적는다(`_execute`). 「지금 실행」 결과는 화면
    발행과 같이 성공 알림 밑에 경고를 따로 띄우므로 다시 가른다 — 알림이 rerun 에 끊겨 기록에서
    찾은 회차도 기록 한 칸뿐이라 같은 길이다. 경고는 늘 그 문장의 머리(`UNCOUNTED_DEMAND_LEAD`)로
    시작하고, 발행 줄(공식 번호·주차·코드·자동 갱신 메모)에는 그 머리가 없다.
    """
    head, joint, rest = reason.partition(f"{_WARNING_SEPARATOR}{UNCOUNTED_DEMAND_LEAD}")
    if not joint:
        return reason, ""
    return head, f"{UNCOUNTED_DEMAND_LEAD}{rest}"


def _inherited_manual_off(
    repository: DuckDBScenarioRepository,
    baseline: OfficialBaseline,
    previous_preset: ScenarioPreset,
    processes: tuple[str, ...],
) -> tuple[str, ...]:
    """직전 공식버전에서 사람이 손으로 뺀 공정(새 데이터에도 있는 것).

    자동 갱신이 뺀 공정은 `_auto_exclusions` 가 찾는다 — 직전 공식 리비전과 **그 조상**의 `AUTO`
    기록(자동 리비전 2 에서 사람이 리비전 3 을 저장해 발행했어도 리비전 2 의 자동 off 는 자동으로
    남는다), 복제 시나리오면 가장 최근 자동 회차의 `AUTO` 기록까지.
    """
    previous_processes = reqb_process_names(
        repository.load_revision_table(baseline.revision_id, "RQ_REQB")
    )
    previous_auto = {
        exclusion.process
        for exclusion in _auto_exclusions(repository, baseline.scenario_id, baseline.revision_id)
    }
    return inherited_manual_off(
        previous_processes=previous_processes,
        previous_included=previous_preset.included_processes,
        previous_auto_off=previous_auto,
        current_processes=processes,
    )


def auto_off_marks(
    repository: DuckDBScenarioRepository, scenario_id: str, revision_id: str
) -> dict[str, str]:
    """리비전(과 그 조상)에서 자동 갱신이 확보율로 뺀 공정 → 표지(`자동 off(확보율 72%, 26.11)`).

    HOME 공정 필터 팝업이 연 회차에 한 번 부른다. 근거는 이어받은 수동 off 를 가를 때와 같은
    `_auto_exclusions` 다 — 조상까지, 복제 시나리오면 가장 최근 자동 회차까지. 가까운 리비전의
    기록이 먼저다.
    """
    marks: dict[str, str] = {}
    for exclusion in _auto_exclusions(repository, scenario_id, revision_id):
        marks.setdefault(exclusion.process, auto_off_mark(exclusion.min_rate, exclusion.min_month))
    return marks


def received_codes(repository: DuckDBScenarioRepository) -> set[str]:
    """자동 갱신이 한 번이라도 받아 시나리오로 등록한 원천 코드(실행 기록 기준).

    실행 기록은 시나리오를 지워도 남는다. 그래서 사람이 자동 발행본을 되돌리고 그 시나리오를 지워도
    다음 회차가 같은 코드를 다시 받지 않는다.
    """
    return {
        str(run.simulation_code)
        for run in repository.list_auto_official_update_runs()
        if run.created_scenario_id is not None and run.simulation_code
    }


def _auto_exclusions(
    repository: DuckDBScenarioRepository,
    scenario_id: str,
    revision_id: str,
) -> list[AutoOfficialUpdateExclusion]:
    """그 리비전의 공정 필터에서 자동 갱신이 뺀 공정의 `AUTO` 기록. 가까운 근거가 먼저다.

    1. 리비전과 그 조상(부모 사슬)의 기록 — 가까운 리비전 차례.
    2. 「현재 활성 편집본 복제」로 만든 시나리오(`CLONE_SOURCE_TYPE`)면 그 복제 **전에** 마지막으로
       저장된 자동 리비전 2 의 기록(`_auto_revision_before`). 복제는 부모 없이 세션 프리셋을 그대로
       실어, 자동 off 가 조상 기록 밖으로 빠진다 — 그대로 두면 다음 회차가 그 공정을 사람이 끈
       것으로 보고 영영 이어받는다.
    """
    lineage = _revision_lineage(repository, scenario_id, revision_id)
    order = {revision: index for index, revision in enumerate(lineage)}
    found = sorted(
        (
            exclusion
            for exclusion in repository.list_auto_official_update_exclusions(
                filtered_revision_ids=lineage
            )
            if exclusion.kind == EXCLUSION_AUTO
        ),
        key=lambda exclusion: order.get(str(exclusion.filtered_revision_id), len(order)),
    )
    scenario = next(
        (
            summary
            for summary in repository.list_scenarios(include_archived=True)
            if summary.scenario_id == scenario_id
        ),
        None,
    )
    if scenario is None or scenario.source_type != CLONE_SOURCE_TYPE:
        return found
    source_run = _auto_revision_before(repository, scenario.created_at)
    if source_run is None:
        return found
    return found + [
        exclusion
        for exclusion in repository.list_auto_official_update_exclusions(
            run_ids=[source_run.run_id]
        )
        if exclusion.kind == EXCLUSION_AUTO
    ]


def _auto_revision_before(
    repository: DuckDBScenarioRepository, moment: datetime
) -> AutoOfficialUpdateRun | None:
    """`moment`(복제 시나리오를 만든 시각) 전에 마지막으로 저장된 자동 리비전 2 의 회차.

    시각은 두 쪽 모두 DB 가 적은 저장 시각(시나리오·리비전의 `created_at`)으로 견준다 — 회차의 시작
    시각은 주입한 시계를 따를 수 있다. 리비전이 이미 지워진 회차는 건너뛴다(복제의 출처일 수
    있었어도 근거를 읽을 수 없다).
    """
    best: tuple[datetime, AutoOfficialUpdateRun] | None = None
    for run in repository.list_auto_official_update_runs():
        if run.filtered_revision_id is None or run.created_scenario_id is None:
            continue
        saved_at = next(
            (
                revision.created_at
                for revision in repository.list_revisions(run.created_scenario_id)
                if revision.revision_id == run.filtered_revision_id
            ),
            None,
        )
        if saved_at is None or saved_at > moment:
            continue
        if best is None or saved_at > best[0]:
            best = (saved_at, run)
    return None if best is None else best[1]


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
