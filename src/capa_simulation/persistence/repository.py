# Purpose: 시나리오와 공용 프로필의 저장 명령을 검증하고 잠금·트랜잭션 경계에서 실행한다.

"""시나리오·공용 프로필의 검증, 연결과 쓰기 트랜잭션을 소유하는 저장소."""

from __future__ import annotations

import threading
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

import duckdb
import pandas as pd

from capa_simulation.io.core_data_source import (
    build_source_column_profile,
    core_data_hash,
    core_data_schema_hash,
    load_core_data_contract,
    normalize_core_data,
)
from capa_simulation.persistence import (
    advance_load_store,
    advance_shipment_store,
    auto_official_update_store,
    display_order_store,
    execution_capacity_store,
    home_profile_store,
    key_process_store,
    past_data_store,
    process_rename_store,
    securement_threshold_store,
    sync_state,
)
from capa_simulation.persistence._sql_helpers import (
    connect,
    hash_tables,
    insert_frame,
    load_frame,
    load_profile_header,
    quote,
    require_tables,
    required_text,
    transaction,
)
from capa_simulation.persistence.display_order_store import (
    display_order_frames_equal,
    load_global_display_order_rules,
    prepare_global_display_order_rules,
)
from capa_simulation.persistence.migration_runner import SchemaAheadOfCode, apply_migrations
from capa_simulation.persistence.models import (
    AutoOfficialUpdateExclusion,
    AutoOfficialUpdateRun,
    AutoOfficialUpdateSettingChange,
    AutoOfficialUpdateSettings,
    GlobalAdvanceLoad,
    GlobalAdvanceShipment,
    GlobalComparisonScenario,
    GlobalDisplayOrder,
    GlobalExecutionCapacity,
    GlobalKeyProcess,
    GlobalPastData,
    GlobalProcessRename,
    GlobalSecurementThreshold,
    GlobalSummaryNote,
    GlobalTop5Band,
    OfficialReleaseSummary,
    RevisionSummary,
    ScenarioCreate,
    ScenarioPreset,
    ScenarioSnapshot,
    ScenarioSummary,
)
from capa_simulation.persistence.past_data_store import PAST_TABLES
from capa_simulation.persistence.preset_store import (
    insert_preset,
    load_preset,
    validate_preset_processes,
)
from capa_simulation.persistence.source_data_store import (
    insert_core_data,
    insert_source_profile,
    validate_declared_source_metadata,
    validate_immutable_source_code,
)
from capa_simulation.persistence.summaries import (
    OFFICIAL_RELEASE_SELECT,
    REVISION_SUMMARY_SELECT,
    SCENARIO_SUMMARY_SELECT,
    official_release_summary,
    revision_summary,
    scenario_summary,
)
from capa_simulation.persistence.voc_store import (
    delete_voc_post,
    insert_voc_post,
    insert_voc_reply,
    load_voc_posts,
    load_voc_replies,
    update_voc_post_resolved,
)
from capa_simulation.services.advance_load import prepare_advance_load
from capa_simulation.services.advance_shipment import prepare_advance_shipment
from capa_simulation.services.auto_official_update import (
    AutoUpdateConfig,
    TriggerKind,
    describe_config_change,
)
from capa_simulation.services.display_order_editor import ClashKey, DisplayOrderValueClashError
from capa_simulation.services.execution_capacity import prepare_execution_capacity
from capa_simulation.services.key_process import normalize_key_process_presets
from capa_simulation.services.past_data import prepare_past_table
from capa_simulation.services.process_rename import prepare_process_rename_rules
from capa_simulation.services.securement_threshold import (
    DEFAULT_SECURE_THRESHOLD,
    DEFAULT_WARNING_THRESHOLD,
    empty_securement_threshold_rows,
    validate_securement_thresholds,
)
from capa_simulation.services.top5_band import validate_top5_band
from capa_simulation.services.voc_board import normalize_post, normalize_reply

REFERENCE_TABLES: dict[str, str] = {
    "RQ_PKG_PLAN": "rq_pkg_plan",
    "RQ_YLD": "rq_yld",
    "RQ_CHIP_QTY": "rq_chip_qty",
    "RQ_CHIP_EQ": "rq_chip_eq",
    "RQ_DISPLAY_ORDER": "rq_display_order",
    "RQ_EQP_OWN": "rq_eqp_own",
    "RQ_EQP_LENT": "rq_eqp_lent",
    "RQ_EQP_AVBL": "rq_eqp_avbl",
    "RQ_UPEH": "rq_upeh",
    "RQ_RUN_RATE": "rq_run_rate",
    "RQ_VITAL": "rq_vital",
    "RQ_MODULE": "rq_module",
    "RQ_RUN_DAY": "rq_run_day",
    "RQ_LOT_RATIO": "rq_lot_ratio",
    "RQ_WF_RATIO": "rq_wf_ratio",
    "RQ_REQB": "rq_reqb",
}
REVISION_TABLES: dict[str, str] = {
    name: REFERENCE_TABLES[name]
    for name in (
        "RQ_PKG_PLAN",
        "RQ_YLD",
        "RQ_CHIP_QTY",
        "RQ_CHIP_EQ",
        "RQ_UPEH",
        "RQ_RUN_RATE",
        "RQ_VITAL",
        "RQ_RUN_DAY",
        "RQ_LOT_RATIO",
        "RQ_WF_RATIO",
        "RQ_REQB",
        "RQ_EQP_OWN",
        "RQ_EQP_LENT",
        "RQ_EQP_AVBL",
    )
}
# 데이터셋(`ref_data`)에만 사는 표 — 리비전 표가 아닌 나머지(`RQ_DISPLAY_ORDER`·`RQ_MODULE`).
# 리비전 표 14개는 리비전(`rev_data`)에만 적는다. 스냅샷은 그 14개를 `rev_data` 에서만 읽고
# 리비전은 불변이라, 데이터셋에 같은 사본을 두면 읽는 곳 없이 행만 늘었다(2026-10-06 사용자
# 결정 B3). 이 결정 전에 만든 데이터셋의 `ref_data` 사본은 리비전 1 과 행 단위로 같으면 마이그레이션
# `0033` 이 지웠고(2026-10-10 사용자 승인), 리비전 1 과 다른 사본만 읽는 곳 없이 남는다.
DATASET_TABLES: dict[str, str] = {
    name: table for name, table in REFERENCE_TABLES.items() if name not in REVISION_TABLES
}

# 시나리오가 소유한 행이 사는 스키마.
_OWNED_SCHEMAS = ("app_meta", "raw_data", "ref_data", "rev_data", "result_data")
# 공용 프로필은 시나리오에 종속되지 않는다 — 단일 행이고 `version` 으로 캐시를 가른다.
# 그런데 `global_comparison_scenario` 는 비교 대상을 가리키느라 `scenario_id` 컬럼을
# 가져서(마이그레이션 0020) 아래 자동 발견에 걸린다. 그대로 두면 시나리오 삭제가 그 단일
# 행을 **통째로 지워** 프로필 자체가 사라지고 `version` 도 올라가지 않아, 다른 세션이
# 낡은 비교 대상을 계속 쓴다. 소유가 아니라 참조이므로 자동 발견에서 빼고 삭제 경로가
# 보관과 같은 방식으로 명시적으로 비운다.
_GLOBAL_PROFILE_TABLES = frozenset({"global_comparison_scenario"})
# 한 표가 두 소유 컬럼을 함께 가지면 넓은 쪽으로 지운다. `app_meta.scenario_revision` 은
# `scenario_id` 로 한 번에 지우는 편이 리비전 목록을 미리 붙잡아 둘 필요를 없앤다.
_OWNER_COLUMNS = ("scenario_id", "dataset_id", "revision_id")


def _load_reference_frame(
    connection: duckdb.DuckDBPyConnection,
    logical_name: str,
    *,
    revision_id: str,
    dataset_id: str,
) -> pd.DataFrame:
    """리비전 하나가 보는 표 한 장 — 리비전 표는 `rev_data`, 나머지는 데이터셋의 `ref_data` 다."""
    if logical_name in REVISION_TABLES:
        return load_frame(
            connection,
            schema="rev_data",
            table_name=REVISION_TABLES[logical_name],
            owner_column="revision_id",
            owner_id=revision_id,
        )
    return load_frame(
        connection,
        schema="ref_data",
        table_name=REFERENCE_TABLES[logical_name],
        owner_column="dataset_id",
        owner_id=dataset_id,
    )


def _has_global_display_order(connection: duckdb.DuckDBPyConnection) -> bool:
    return (
        connection.execute(
            "SELECT profile_id FROM app_meta.global_display_order WHERE profile_id = 1"
        ).fetchone()
        is not None
    )


def _owned_tables(connection: duckdb.DuckDBPyConnection) -> list[tuple[str, str, str]]:
    """(스키마, 표, 소유 컬럼) 목록. 시나리오 뿌리 행은 마지막에 따로 지우므로 뺀다."""
    rows = connection.execute(
        """
        SELECT table_schema, table_name, list(column_name)
        FROM information_schema.columns
        WHERE table_schema IN (?, ?, ?, ?, ?)
        GROUP BY table_schema, table_name
        ORDER BY table_schema, table_name
        """,
        list(_OWNED_SCHEMAS),
    ).fetchall()
    owned: list[tuple[str, str, str]] = []
    for schema, table, columns in rows:
        if (schema, table) == ("app_meta", "scenario"):
            continue
        if schema == "app_meta" and table in _GLOBAL_PROFILE_TABLES:
            continue
        present = set(columns)
        owner = next((column for column in _OWNER_COLUMNS if column in present), None)
        if owner is not None:
            owned.append((str(schema), str(table), owner))
    return owned


def _require_not_latest_official(
    connection: duckdb.DuckDBPyConnection,
    scenario_id: str,
    action: str,
) -> None:
    """최신 공식버전이 가리키는 시나리오면 막는다. `action` 은 문구의 동사다."""
    latest_official = connection.execute(
        """
        SELECT scenario_id
        FROM app_meta.official_release
        ORDER BY release_no DESC
        LIMIT 1
        """
    ).fetchone()
    if latest_official is not None and str(latest_official[0]) == scenario_id:
        raise ValueError(
            f"현재 최신 공식버전의 시나리오는 {action}할 수 없습니다. "
            "다른 공식버전을 먼저 지정하세요."
        )


DUPLICATE_SCENARIO_NAME_MESSAGE = "같은 이름의 시나리오가 이미 있습니다. 이름을 바꿔 저장하세요."


def _require_unique_scenario_name(
    connection: duckdb.DuckDBPyConnection,
    scenario_name: str,
    *,
    except_scenario_id: str | None = None,
) -> None:
    """같은 이름의 시나리오가 있으면 막는다(2026-10-01 사용자 결정 — 이름 중복 금지).

    사이드바·보관함 선택지·영구 삭제 확인이 모두 이름만 보여 주어, 같은 이름이 둘이면 어느
    쪽을 고르는지 가릴 수 없다. **보관본까지 본다** — BigDataQuery 등록의 이름 검사
    (`list_scenarios(include_archived=True)`)와 같은 범위다. 보관본을 되돌리면 목록에 같은
    이름이 둘이 된다. 대조는 앞뒤 공백을 뗀 값의 완전 일치다(`required_text` 가 이미 뗀다).

    DB 제약(UNIQUE)이 아니라 쓰기 트랜잭션 안의 검사로 둔다. 이 규칙 전에 만든 DB 에는 같은
    이름이 이미 있을 수 있어 제약을 걸면 마이그레이션이 그 DB 에서 멈춘다. `except_scenario_id`
    는 이름 수정에서 자기 자신을 빼는 자리다 — 지금 이름 그대로 저장해도 막히지 않는다.
    """
    duplicate = connection.execute(
        """
        SELECT 1
        FROM app_meta.scenario
        WHERE scenario_name = ? AND scenario_id IS DISTINCT FROM ?
        LIMIT 1
        """,
        [scenario_name, except_scenario_id],
    ).fetchone()
    if duplicate is not None:
        raise ValueError(DUPLICATE_SCENARIO_NAME_MESSAGE)


_WRITE_LOCK = threading.RLock()


class _RunKeyTaken(Exception):
    """쓰기 트랜잭션 안에서 회차 키가 이미 잡혀 있었다. 아무것도 쓰지 않고 되돌리는 신호다."""


class OfficialReleaseMoved(ValueError):
    """발행하려는 사이 최신 공식버전이 바뀌었다(다른 사람이 먼저 지정). 아무것도 쓰지 않았다.

    `expected` 는 부르는 쪽이 보고 출발한 최신 번호(없었으면 0), `current` 는 쓰기 트랜잭션 안에서
    읽은 지금 번호다.
    """

    def __init__(self, expected: int, current: int) -> None:
        super().__init__(
            f"회차 도중 공식버전이 바뀌어(공식 v{expected} → v{current}) 발행하지 않았습니다."
        )
        self.expected = expected
        self.current = current


class DuckDBScenarioRepository:
    """Persist immutable datasets and full editable-table revision snapshots."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path.resolve()
        self._schema_ahead: SchemaAheadOfCode | None = None

    @property
    def database_path(self) -> Path:
        return self._database_path

    @property
    def schema_ahead(self) -> SchemaAheadOfCode | None:
        """마지막 `initialize()` 가 본 「DB 가 이 코드보다 새 것」. 아니면 None.

        저장소는 프로세스마다 한 번 만들어 캐시하므로(`persistence.cache`) 화면은 rerun 마다
        이 속성만 읽는다 — DB 를 다시 열지 않는다.
        """
        return self._schema_ahead

    def initialize(self) -> tuple[int, ...]:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with _WRITE_LOCK, self._connect() as connection:
            outcome = apply_migrations(connection)
        self._schema_ahead = outcome.schema_ahead
        return outcome.applied

    def initialize_global_display_order(
        self,
        fallback: pd.DataFrame | Callable[[], pd.DataFrame],
    ) -> GlobalDisplayOrder:
        """Create the shared profile once, preferring an existing revision's rules.

        프로필이 이미 있으면 쓰기 트랜잭션을 열지 않는다. 열면 아무것도 쓰지 않아도 COMMIT
        뒤 동기화 dirty 가 서서, 기동만 한 사본이 다음 pull 에서 막히고 같은 세대를 다시
        올린다. 없다고 읽은 뒤의 경합은 store 가 트랜잭션 안에서 헤더를 다시 확인해 막는다.
        아래 보강 단계는 프로필이 있어도 매번 돈다.

        `fallback` 은 시드 프레임이나 시드를 읽는 함수다. 기동 길은 함수를 넘긴다 — 시드는 프로필이
        없을 때만 쓰이므로 그때만 읽고 검사한다. 프로필이 있는데 쓰지 않는 로컬 시드 파일이 검사에
        걸려 앱 전체가 기동하지 못하는 일을 막는다.
        """
        with self._connect() as connection:
            exists = load_profile_header(connection, "global_display_order") is not None
        if not exists:
            seed = fallback if isinstance(fallback, pd.DataFrame) else fallback()
            # 로컬 시드 CSV 에 대소문자만 다른 분류값이 있어도 막지 않는다(아래 저장된 프로필과
            # 같은 까닭).
            prepared_fallback = prepare_global_display_order_rules(seed, allow_value_clashes=True)
            with self._write_transaction() as connection:
                display_order_store.initialize_global_display_order(connection, prepared_fallback)
        profile = self.load_global_display_order()
        try:
            prepared = prepare_global_display_order_rules(profile.rules)
        except DisplayOrderValueClashError:
            # 저장 검증이 대소문자만 다른 분류값을 막기 **전에** 저장된 프로필이다. 여기서 죽으면
            # 앱이 기동하지 못한다. 보강은 미루고 그대로 둔다 — 그 범위를 쓰는 화면이 중복을
            # 알리고, Admin 표시순서 탭에서 고쳐 저장하면 그 저장이 보강까지 한다.
            return profile
        if not display_order_frames_equal(profile.rules, prepared):
            return self.replace_global_display_order(
                prepared,
                source="경로 식별 컬럼 하위 배치 자동 보강",
            )
        return profile

    def load_global_display_order(self) -> GlobalDisplayOrder:
        """Load the scenario-independent display-order profile."""
        with self._connect() as connection:
            return display_order_store.load_global_display_order(connection)

    def replace_global_display_order(
        self,
        rules: pd.DataFrame,
        *,
        source: str,
        tolerated_clashes: Collection[ClashKey] = (),
    ) -> GlobalDisplayOrder:
        """Atomically replace the shared profile without creating scenario revisions.

        `tolerated_clashes` 는 범위 하나를 고치는 직접 편집 저장만 준다 — 다른 범위에 이미 있던
        겹친 분류값(`display_order_editor.clashes_outside_scope`)이다. 비워 두면(붙여넣기·CSV·
        일괄 교체) 프로필 어디에든 겹침이 있으면 막는다.
        """
        prepared_rules = prepare_global_display_order_rules(
            rules, tolerated_clashes=tolerated_clashes
        )
        source_label = required_text(source, "표시순서 변경 출처")
        with self._write_transaction() as connection:
            display_order_store.replace_global_display_order(
                connection, prepared_rules, source=source_label
            )
        return self.load_global_display_order()

    def load_global_process_rename(self) -> GlobalProcessRename:
        """Load the scenario-independent process display-name profile.

        한 번도 저장하지 않은 상태가 정상이므로 표시순서와 달리 예외를 내지 않는다.
        여기서 예외를 내면 첫 저장 전까지 모든 화면이 죽는다.
        """
        with self._connect() as connection:
            return process_rename_store.load_global_process_rename(connection)

    def replace_global_process_rename(
        self,
        rules: pd.DataFrame,
        *,
        source: str,
        expected_version: int | None = None,
    ) -> GlobalProcessRename:
        """Atomically replace the shared profile without creating scenario revisions.

        표시순서와 같은 결로 현재본만 남기고 version 번호를 올린다. 이전 규칙은 보존하지
        않으므로 되돌리기 수단은 교체 전 CSV 다운로드뿐이다. 규칙 0건(전체 해제)도
        정상 저장이며 version 은 올라간다. 화면 편집은 `expected_version`(편집을 시작할 때 본
        version)을 넘기고, 쓰기 잠금 안에서 저장본과 다르면 `ProfileVersionConflict`(ValueError)로
        거부한다 — 판정 기준과 같은 버전 대조다.
        """
        prepared_rules = prepare_process_rename_rules(rules)
        source_label = required_text(source, "공정 표시명 변경 출처")
        with self._write_transaction() as connection:
            process_rename_store.replace_global_process_rename(
                connection,
                prepared_rules,
                source=source_label,
                expected_version=expected_version,
            )
        return self.load_global_process_rename()

    def load_global_execution_capacity(self) -> GlobalExecutionCapacity:
        """Load the scenario-independent execution-capacity profile.

        선행 B/O 프로필과 같은 이유로 예외를 내지 않는다. 한 번도 저장하지 않은 상태가
        정상이고 여기서 죽으면 첫 저장 전까지 HOME 이 열리지 않는다.
        """
        with self._connect() as connection:
            return execution_capacity_store.load_global_execution_capacity(connection)

    def replace_global_execution_capacity(
        self,
        rows: pd.DataFrame,
        *,
        source: str,
        expected_version: int | None = None,
    ) -> GlobalExecutionCapacity:
        """Atomically replace the shared execution-capacity profile.

        다른 공용 프로필과 같은 결로 현재본만 남기고 version 을 올린다. **행 0건(전체
        해제)도 정상 저장이며 version 은 올라간다** — 캐시 키가 version 을 보므로 해제도
        올라가야 무효화된다. 화면 편집은 `expected_version` 을 넘겨 판정 기준과 같은 버전 대조를
        받는다(다르면 `ProfileVersionConflict`).
        """
        prepared = prepare_execution_capacity(rows)
        source_label = required_text(source, "확보율 보정 출처")
        with self._write_transaction() as connection:
            execution_capacity_store.replace_global_execution_capacity(
                connection,
                prepared,
                source=source_label,
                expected_version=expected_version,
            )
        return self.load_global_execution_capacity()

    def load_global_top5_band(self) -> GlobalTop5Band:
        """Load the scenario-independent Top 5 securement band.

        다른 공용 프로필과 같은 이유로 예외를 내지 않는다. 한 번도 저장하지 않은 상태가
        정상이고 그때는 서비스 기본값을 돌려준다.
        """
        with self._connect() as connection:
            return home_profile_store.load_global_top5_band(connection)

    def replace_global_top5_band(
        self,
        min_rate: float,
        max_rate: float,
        *,
        source: str,
    ) -> GlobalTop5Band:
        """Atomically replace the shared Top 5 band. 교체마다 version 이 오른다."""
        low, high = validate_top5_band(min_rate, max_rate)
        source_label = required_text(source, "Top5 확보율 구간 출처")
        with self._write_transaction() as connection:
            home_profile_store.replace_global_top5_band(connection, low, high, source=source_label)
        return self.load_global_top5_band()

    def load_global_key_process(self) -> GlobalKeyProcess:
        """Load the scenario-independent key-process list for the HOME heatmap.

        다른 공용 프로필과 같은 이유로 예외를 내지 않는다. 한 번도 저장하지 않은 상태가
        정상이고, 여기서 죽으면 첫 저장 전까지 HOME 이 열리지 않는다.
        """
        with self._connect() as connection:
            return key_process_store.load_global_key_process(connection)

    def replace_global_key_process_presets(
        self,
        presets: Sequence[tuple[str, Sequence[str]]],
        *,
        source: str,
    ) -> GlobalKeyProcess:
        """Atomically replace every shared key-process preset.

        화면은 프리셋 하나를 고쳐도 **묶음 전체**를 넘긴다 — 차례(첫 프리셋이 기본)와 이름
        중복을 한 자리에서 검사하려면 전체가 있어야 한다. 0개(모두 지움)도 정상 저장이며
        version 은 올라간다.
        """
        normalized = normalize_key_process_presets(presets)
        source_label = required_text(source, "주요공정 프리셋 출처")
        with self._write_transaction() as connection:
            key_process_store.replace_global_key_process_presets(
                connection, normalized, source=source_label
            )
        return self.load_global_key_process()

    def list_voc_posts(self) -> pd.DataFrame:
        """VOC 글 전체. 최신이 위다.

        캐시를 두지 않는다. 게시판은 쓰기가 잦아 캐시를 두면 글마다 무효화를 손으로
        챙겨야 하고, 한 번만 빠뜨려도 방금 쓴 글이 안 보인다. 읽는 양도 작다.
        """
        with self._connect() as connection:
            return load_voc_posts(connection)

    def list_voc_replies(self) -> pd.DataFrame:
        """VOC 답글 전체. 주고받은 차례대로 오래된 것이 위다."""
        with self._connect() as connection:
            return load_voc_replies(connection)

    def create_voc_post(self, *, category: str, title: str, body: str, author: str) -> str:
        """글 하나를 남기고 그 id 를 돌려준다."""
        prepared = normalize_post(category=category, title=title, body=body, author=author)
        post_id = uuid4().hex
        with self._write_transaction() as connection:
            insert_voc_post(connection, post_id=post_id, **prepared)
        return post_id

    def create_voc_reply(self, *, post_id: str, body: str, author: str) -> str:
        """답글 하나를 남기고 그 id 를 돌려준다."""
        prepared = normalize_reply(body=body, author=author)
        reply_id = uuid4().hex
        with self._write_transaction() as connection:
            insert_voc_reply(connection, reply_id=reply_id, post_id=post_id, **prepared)
        return reply_id

    def set_voc_post_resolved(self, post_id: str, *, resolved: bool) -> None:
        """답변 완료 표시. 게시판에서 「아직 답이 없는 질문」을 걸러 보게 한다."""
        with self._write_transaction() as connection:
            update_voc_post_resolved(connection, post_id=post_id, resolved=resolved)

    def remove_voc_post(self, post_id: str) -> None:
        """글과 그 답글을 함께 지운다. 주인 없는 답글은 영영 보이지 않는다."""
        with self._write_transaction() as connection:
            delete_voc_post(connection, post_id=post_id)

    def load_global_summary_note(self) -> GlobalSummaryNote:
        """Load the scenario-independent HOME summary notice.

        다른 공용 프로필과 같은 이유로 예외를 내지 않는다. 한 번도 저장하지 않은 상태가
        정상이고 그때는 빈 공지다.
        """
        with self._connect() as connection:
            return home_profile_store.load_global_summary_note(connection)

    def replace_global_summary_note(self, note: str, *, source: str) -> GlobalSummaryNote:
        """Atomically replace the shared summary notice. 교체마다 version 이 오른다.

        **빈 문구를 막지 않는다.** 공지를 내리는 것도 저장해야 하는 결정이고, 그때도
        version 이 올라야 다른 세션의 캐시가 풀린다.
        """
        source_label = required_text(source, "Summary 공지 출처")
        with self._write_transaction() as connection:
            home_profile_store.replace_global_summary_note(connection, note, source=source_label)
        return self.load_global_summary_note()

    def load_global_comparison_scenario(self) -> GlobalComparisonScenario:
        """Load the scenario-independent GAP comparison target.

        다른 공용 프로필과 같은 이유로 예외를 내지 않는다. 한 번도 저장하지 않은 상태가
        정상이고 여기서 죽으면 첫 저장 전까지 HOME 이 열리지 않는다.
        """
        with self._connect() as connection:
            return home_profile_store.load_global_comparison_scenario(connection)

    def replace_global_comparison_scenario(
        self,
        scenario_id: str | None,
        revision_id: str | None,
        *,
        source: str,
    ) -> GlobalComparisonScenario:
        """Atomically replace the shared comparison target.

        다른 공용 프로필과 같은 결로 현재본만 남기고 version 을 올린다. **고르지 않음(둘 다
        `None`)도 정상 저장이며 version 은 올라간다.** 캐시는 경로 키이므로 version 으로
        무효화되지 않는다 — 저장한 호출부가 `clear_global_comparison_scenario_cache()` 로 비운다.

        리비전만 있고 시나리오가 없는 짝은 저장하지 않는다. 그 상태로는 어느 시나리오의
        리비전인지 알 수 없어 화면이 복원할 수 없다.
        """
        chosen_scenario = (
            None if scenario_id is None else required_text(scenario_id, "비교 시나리오")
        )
        chosen_revision = None if revision_id is None else required_text(revision_id, "비교 리비전")
        if chosen_revision is not None and chosen_scenario is None:
            raise ValueError("비교 리비전만 저장할 수 없습니다. 시나리오를 함께 주세요.")
        source_label = required_text(source, "비교 대상 변경 출처")
        with self._write_transaction() as connection:
            home_profile_store.replace_global_comparison_scenario(
                connection, chosen_scenario, chosen_revision, source=source_label
            )
        return self.load_global_comparison_scenario()

    def load_global_advance_load(self) -> GlobalAdvanceLoad:
        """Load the scenario-independent advance-load profile.

        표시명 프로필과 같은 이유로 예외를 내지 않는다. 한 번도 저장하지 않은 상태가
        정상이고 여기서 죽으면 첫 저장 전까지 HOME 이 열리지 않는다.
        """
        with self._connect() as connection:
            return advance_load_store.load_global_advance_load(connection)

    def replace_global_advance_load(
        self,
        rows: pd.DataFrame,
        *,
        source: str,
    ) -> GlobalAdvanceLoad:
        """Atomically replace the shared advance-load profile without a scenario revision.

        표시명·표시순서와 같은 결로 현재본만 남기고 version 번호를 올린다. 행 0건(전체
        해제)도 정상 저장이며 version 은 올라간다.
        """
        prepared_rows = prepare_advance_load(rows)
        source_label = required_text(source, "선행 B/O 변경 출처")
        with self._write_transaction() as connection:
            advance_load_store.replace_global_advance_load(
                connection, prepared_rows, source=source_label
            )
        return self.load_global_advance_load()

    def load_global_advance_shipment(self) -> GlobalAdvanceShipment:
        """Load the scenario-independent 선행 입고 실적 profile (display only).

        다른 공용 프로필과 같은 이유로 예외를 내지 않는다. 한 번도 저장하지 않은 상태가
        정상이고 여기서 죽으면 첫 저장 전까지 HOME 이 열리지 않는다.
        """
        with self._connect() as connection:
            return advance_shipment_store.load_global_advance_shipment(connection)

    def replace_global_advance_shipment(
        self,
        rows: pd.DataFrame,
        *,
        source: str,
    ) -> GlobalAdvanceShipment:
        """Atomically replace the shared 선행 입고 실적 profile without a scenario revision.

        선행 B/O 와 같은 결로 현재본만 남기고 version 을 올린다. 행 0건(전체 해제)도 정상
        저장이며 version 은 올라간다. 부호는 입력한 그대로 저장한다.
        """
        prepared_rows = prepare_advance_shipment(rows)
        source_label = required_text(source, "선행 입고 실적 변경 출처")
        with self._write_transaction() as connection:
            advance_shipment_store.replace_global_advance_shipment(
                connection, prepared_rows, source=source_label
            )
        return self.load_global_advance_shipment()

    def load_global_securement_threshold(self) -> GlobalSecurementThreshold:
        """Load the scenario-independent securement judgement thresholds.

        다른 공용 프로필과 같은 이유로 예외를 내지 않는다. 한 번도 저장하지 않았으면 기본값은
        **최신 공식버전 리비전 프리셋의 확보·경고 값**이고, 공식버전이 없으면 코드 기본값이다.
        이렇게 정한 값은 읽을 때만 쓰고 DB 에 쓰지 않는다 — 저장은 사용자가 Preference 에서 한다.
        """
        with self._connect() as connection:
            header = securement_threshold_store.load_securement_threshold_header(connection)
            if header is not None:
                version, source, updated_at, default_secure, default_warning = header
                return GlobalSecurementThreshold(
                    version=version,
                    source=source,
                    updated_at=updated_at,
                    default_secure=default_secure,
                    default_warning=default_warning,
                    rows=securement_threshold_store.load_securement_threshold_rows(connection),
                )
            fallback = connection.execute(
                """
                SELECT o.release_no, p.secure_threshold, p.warning_threshold
                FROM app_meta.official_release o
                JOIN app_meta.scenario_preset p ON p.revision_id = o.revision_id
                ORDER BY o.release_no DESC
                LIMIT 1
                """
            ).fetchone()
        code_default = GlobalSecurementThreshold(
            version=0,
            source="",
            updated_at=None,
            default_secure=DEFAULT_SECURE_THRESHOLD,
            default_warning=DEFAULT_WARNING_THRESHOLD,
            rows=empty_securement_threshold_rows(),
            fallback="코드 기본값",
        )
        if fallback is None:
            return code_default
        release = f"공식 v{int(fallback[0])} 프리셋"
        # 레거시 프리셋은 경고 0 이나 확보 = 경고를 허용했다(옛 사이드바 칸의 하한이 0 이었다).
        # 저장 경로와 같은 규칙에 어긋나는 짝은 기본값으로 쓰지 않는다 — 0 기준은 모든 공정을
        # 확보로 판정하고, 편집기 칸의 하한보다 낮아 Preference 탭이 그려지지도 않는다.
        try:
            secure, warning, _ = validate_securement_thresholds(
                fallback[1], fallback[2], empty_securement_threshold_rows()
            )
        except ValueError:
            return replace(code_default, fallback=f"코드 기본값({release} 값은 쓸 수 없어 대신)")
        return replace(
            code_default, default_secure=secure, default_warning=warning, fallback=release
        )

    def replace_global_securement_threshold(
        self,
        default_secure: float,
        default_warning: float,
        rows: pd.DataFrame,
        *,
        source: str,
        expected_version: int,
    ) -> GlobalSecurementThreshold:
        """Atomically replace the shared securement thresholds after a version check.

        다른 공용 프로필과 같은 결로 현재본만 남기고 version 을 올린다. 쓰기 잠금 안에서
        `expected_version`(편집을 시작할 때 본 version)과 저장본을 대조해 다르면
        `SecurementThresholdConflict`(ValueError)로 거부한다. 검증 — 모든 값 > 0, 기본값과 합친
        각 달의 경고 ≤ 확보 — 에 어긋나도 ValueError 로 어느 달인지 알린다.
        """
        secure, warning, prepared = validate_securement_thresholds(
            default_secure, default_warning, rows
        )
        source_label = required_text(source, "판정 기준 변경 출처")
        with self._write_transaction() as connection:
            securement_threshold_store.replace_global_securement_threshold(
                connection,
                default_secure=secure,
                default_warning=warning,
                prepared_rows=prepared,
                source=source_label,
                expected_version=expected_version,
            )
        return self.load_global_securement_threshold()

    def load_global_past_data(self) -> GlobalPastData:
        """Load the scenario-independent past-period profile.

        다른 공용 프로필과 같은 이유로 예외를 내지 않는다. 한 번도 저장하지 않은 상태가
        정상이고 여기서 죽으면 첫 저장 전까지 HOME 이 열리지 않는다.
        """
        with self._connect() as connection:
            return past_data_store.load_global_past_data(connection)

    def replace_global_past_data(
        self,
        tables: Mapping[str, pd.DataFrame],
        *,
        source: str,
    ) -> GlobalPastData:
        """Atomically replace the shared past-period profile without a scenario revision.

        세 표가 한 버전을 공유한다. 한 표만 고쳐도 나머지를 함께 다시 써야 하므로 호출자가
        세 표를 모두 준다 — 부분 저장을 허용하면 어느 표가 어느 버전인지 알 수 없다.
        """
        prepared = {
            name: prepare_past_table(tables[name], columns)
            for name, (_, columns) in PAST_TABLES.items()
        }
        source_label = required_text(source, "과거 구간 변경 출처")
        with self._write_transaction() as connection:
            past_data_store.replace_global_past_data(connection, prepared, source=source_label)
        return self.load_global_past_data()

    def load_auto_official_update_settings(self) -> AutoOfficialUpdateSettings:
        """공식버전 자동 갱신 설정. 한 번도 저장하지 않았으면 version 0 의 코드 기본값이다."""
        with self._connect() as connection:
            return auto_official_update_store.load_settings(connection)

    def replace_auto_official_update_settings(
        self,
        config: AutoUpdateConfig,
        *,
        expected_version: int,
        changed_by: str | None = None,
        source: str = "시나리오 관리 · 자동 갱신",
    ) -> AutoOfficialUpdateSettings:
        """버전을 대조해 설정을 교체하고 무엇을 바꿨는지 변경 기록에 남긴다.

        `expected_version` 은 편집을 시작할 때 본 version 이다. 저장본과 다르면
        `AutoOfficialUpdateSettingsConflict`(ValueError)로 거부한다. 바꾼 사람 이름은 선택이다
        (빈 글은 이름 없음). 비교 대상은 트랜잭션 안에서 읽은 저장본이다 — 화면이 본 값이 아니다.
        """
        source_label = required_text(source, "자동 갱신 설정 변경 출처")
        author = (changed_by or "").strip() or None
        with self._write_transaction() as connection:
            before = auto_official_update_store.load_settings(connection).config
            auto_official_update_store.replace_settings(
                connection,
                config=config,
                source=source_label,
                changed_by=author,
                change_text=describe_config_change(before, config),
                expected_version=expected_version,
            )
        return self.load_auto_official_update_settings()

    def list_auto_official_update_setting_changes(
        self, *, limit: int | None = None
    ) -> list[AutoOfficialUpdateSettingChange]:
        with self._connect() as connection:
            return auto_official_update_store.load_setting_changes(connection, limit=limit)

    def claim_auto_official_update_run(
        self,
        *,
        run_key: str,
        trigger_kind: TriggerKind,
        run_date: date,
        started_at: datetime,
        keyword: str,
        threshold: float,
        settings_version: int,
    ) -> str | None:
        """회차를 선점한다. 잡았으면 실행 id, 이미 잡힌 회차면 None.

        키 확인과 삽입을 한 쓰기 트랜잭션에서 한다 — 같은 프로세스의 다른 스레드는 쓰기 잠금으로
        차례를 기다리고, 유일 제약이 마지막 방어선이다. 이미 잡힌 회차는 아무것도 쓰지 않는다(변경
        신호도 내지 않는다).
        """
        run_id = str(uuid4())
        with self._connect() as connection:
            if auto_official_update_store.run_key_exists(connection, run_key):
                return None
        try:
            with self._write_transaction() as connection:
                if auto_official_update_store.run_key_exists(connection, run_key):
                    raise _RunKeyTaken
                auto_official_update_store.insert_run(
                    connection,
                    run_id=run_id,
                    run_key=run_key,
                    trigger_kind=trigger_kind,
                    run_date=run_date,
                    started_at=started_at,
                    keyword=keyword,
                    threshold=threshold,
                    settings_version=settings_version,
                )
        except (_RunKeyTaken, duckdb.ConstraintException):
            return None
        return run_id

    def update_auto_official_update_run(self, run_id: str, values: Mapping[str, object]) -> None:
        """회차 행의 진행 칸을 고쳐 쓴다(`auto_official_update_store.RUN_UPDATABLE_COLUMNS`)."""
        with self._write_transaction() as connection:
            auto_official_update_store.update_run(connection, run_id, values)

    def list_auto_official_update_runs(
        self, *, limit: int | None = None
    ) -> list[AutoOfficialUpdateRun]:
        """실행 기록. 최근에 시작한 것이 위다."""
        with self._connect() as connection:
            return auto_official_update_store.load_runs(connection, limit=limit)

    def auto_official_update_run_key_exists(self, run_key: str) -> bool:
        """그 회차 키가 이미 잡혔는가(예약 회차는 날짜마다 키 하나)."""
        with self._connect() as connection:
            return auto_official_update_store.run_key_exists(connection, run_key)

    def find_manual_auto_official_update_run(self, token: str) -> AutoOfficialUpdateRun | None:
        """「지금 실행」 회차를 부른 쪽의 표(`manual_run_key` 의 끝)로 찾는다. 없으면 None."""
        with self._connect() as connection:
            return auto_official_update_store.load_manual_run(connection, token)

    def load_auto_official_update_run(self, run_id: str) -> AutoOfficialUpdateRun:
        with self._connect() as connection:
            runs = auto_official_update_store.load_runs(connection, run_id=run_id)
        if not runs:
            raise KeyError(f"자동 갱신 실행 기록을 찾을 수 없습니다: {run_id}")
        return runs[0]

    def abandon_running_auto_official_update_runs(
        self,
        *,
        started_before: datetime,
        finished_at: datetime,
        reason: str,
    ) -> int:
        """도중에 앱이 꺼져 「실행 중」으로 남은 회차를 오류로 닫는다. 닫은 건수를 돌려준다."""
        with self._connect() as connection:
            pending = connection.execute(
                "SELECT count(*) FROM app_meta.auto_official_update_run "
                "WHERE status = 'RUNNING' AND started_at < ?",
                [started_before],
            ).fetchone()
        if pending is None or int(pending[0]) == 0:
            return 0
        with self._write_transaction() as connection:
            return auto_official_update_store.abandon_running_runs(
                connection,
                started_before=started_before,
                finished_at=finished_at,
                reason=required_text(reason, "중단 사유"),
            )

    def record_auto_official_update_exclusions(
        self, exclusions: Sequence[AutoOfficialUpdateExclusion]
    ) -> None:
        """한 회차가 공정 필터에서 뺀 공정을 남긴다. 빈 목록이면 아무것도 쓰지 않는다."""
        if not exclusions:
            return
        with self._write_transaction() as connection:
            auto_official_update_store.insert_exclusions(connection, exclusions)

    def list_auto_official_update_exclusions(
        self,
        *,
        run_ids: Collection[str] | None = None,
        filtered_revision_ids: Collection[str] | None = None,
    ) -> list[AutoOfficialUpdateExclusion]:
        with self._connect() as connection:
            return auto_official_update_store.load_exclusions(
                connection,
                run_ids=run_ids,
                filtered_revision_ids=filtered_revision_ids,
            )

    def create_scenario(
        self,
        metadata: ScenarioCreate,
        reference_tables: Mapping[str, pd.DataFrame],
        preset: ScenarioPreset,
        *,
        source_data: pd.DataFrame | None = None,
        revision_tables: Mapping[str, pd.DataFrame] | None = None,
        revision_name: str = "초기 리비전",
        note: str | None = None,
        virtual_products: Sequence[Mapping[str, str]] = (),
    ) -> ScenarioSnapshot:
        require_tables(reference_tables, tuple(REFERENCE_TABLES), "기준정보")
        revision_source = dict(reference_tables)
        if revision_tables is not None:
            revision_source.update(revision_tables)
        require_tables(revision_source, tuple(REVISION_TABLES), "리비전")
        validate_preset_processes(preset, revision_source["RQ_REQB"])

        scenario_id = str(uuid4())
        dataset_id = str(uuid4())
        revision_id = str(uuid4())
        revision_label = required_text(revision_name, "리비전명")
        reference_hash = hash_tables(revision_source, tuple(REVISION_TABLES))
        normalized_source = normalize_core_data(source_data) if source_data is not None else None
        source_profile = (
            build_source_column_profile(normalized_source)
            if normalized_source is not None
            else None
        )
        source_row_count = len(normalized_source) if normalized_source is not None else 0
        source_schema_hash = (
            core_data_schema_hash(normalized_source) if normalized_source is not None else None
        )
        source_data_hash = (
            core_data_hash(normalized_source) if normalized_source is not None else None
        )
        validate_declared_source_metadata(
            metadata,
            row_count=source_row_count,
            schema_hash=source_schema_hash,
            data_hash=source_data_hash,
        )

        with self._write_transaction() as connection:
            _require_unique_scenario_name(connection, metadata.scenario_name)
            if source_data_hash is not None:
                validate_immutable_source_code(
                    connection,
                    metadata.source_simulation_code,
                    source_data_hash,
                )
            connection.execute(
                """
                INSERT INTO app_meta.scenario (
                    scenario_id,
                    scenario_name,
                    source_simulation_code,
                    source_simulation_name,
                    status
                )
                VALUES (?, ?, ?, ?, 'ACTIVE')
                """,
                [
                    scenario_id,
                    metadata.scenario_name,
                    metadata.source_simulation_code,
                    metadata.source_simulation_name,
                ],
            )
            connection.execute(
                """
                INSERT INTO app_meta.dataset (
                    dataset_id,
                    scenario_id,
                    source_type,
                    source_registered_at,
                    source_row_count,
                    source_schema_hash,
                    source_data_hash,
                    pipeline_version,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'LOADING')
                """,
                [
                    dataset_id,
                    scenario_id,
                    metadata.source_type,
                    metadata.source_registered_at,
                    source_row_count,
                    source_schema_hash,
                    source_data_hash,
                    metadata.pipeline_version,
                ],
            )
            if normalized_source is not None and source_profile is not None:
                insert_core_data(connection, dataset_id, normalized_source)
                insert_source_profile(connection, dataset_id, source_profile)
            for logical_name, table_name in DATASET_TABLES.items():
                insert_frame(
                    connection,
                    schema="ref_data",
                    table_name=table_name,
                    owner_column="dataset_id",
                    owner_id=dataset_id,
                    frame=reference_tables[logical_name],
                    logical_name=logical_name,
                )
            self._insert_revision(
                connection,
                revision_id=revision_id,
                scenario_id=scenario_id,
                revision_no=1,
                revision_name=revision_label,
                parent_revision_id=None,
                note=note,
                reference_hash=reference_hash,
                revision_tables=revision_source,
                preset=preset,
                virtual_products=virtual_products,
            )
            connection.execute(
                "UPDATE app_meta.dataset SET status = 'READY' WHERE dataset_id = ?",
                [dataset_id],
            )
            connection.execute(
                """
                UPDATE app_meta.scenario
                SET active_revision_id = ?, updated_at = current_timestamp
                WHERE scenario_id = ?
                """,
                [revision_id, scenario_id],
            )

        return self.load_revision(revision_id)

    def load_source_data(self, scenario_id: str) -> pd.DataFrame:
        with self._connect() as connection:
            dataset = connection.execute(
                """
                SELECT d.dataset_id, d.source_row_count
                FROM app_meta.dataset d
                WHERE d.scenario_id = ?
                """,
                [scenario_id],
            ).fetchone()
            if dataset is None:
                raise KeyError(f"시나리오를 찾을 수 없습니다: {scenario_id}")
            if int(dataset[1]) <= 0:
                raise ValueError("이 시나리오에는 원천 Core Data가 저장되어 있지 않습니다.")
            columns = [column.name for column in load_core_data_contract().columns]
            projection = ", ".join(quote(column) for column in columns)
            return connection.execute(
                f"SELECT {projection} FROM raw_data.core_data "
                "WHERE dataset_id = ? ORDER BY source_row_no",
                [str(dataset[0])],
            ).fetchdf()

    def load_source_profile(self, scenario_id: str) -> pd.DataFrame:
        with self._connect() as connection:
            dataset = connection.execute(
                "SELECT dataset_id FROM app_meta.dataset WHERE scenario_id = ?",
                [scenario_id],
            ).fetchone()
            if dataset is None:
                raise KeyError(f"시나리오를 찾을 수 없습니다: {scenario_id}")
            return connection.execute(
                """
                SELECT ordinal_position, column_name, source_dtype, nullable_dtype,
                       null_count, unique_count
                FROM raw_data.source_column_profile
                WHERE dataset_id = ?
                ORDER BY ordinal_position
                """,
                [str(dataset[0])],
            ).fetchdf()

    def load_source_row_count(self, scenario_id: str) -> int:
        """원천 행 수. 결측률의 분모라 컬럼 프로필과 짝으로 쓴다.

        `load_source_data` 와 달리 78컬럼을 읽지 않는다 — 분모 하나를 얻으려고 수만 행을
        메모리에 올릴 이유가 없다. 원천이 없으면 0 이고, 호출부가 그때 결측률을 비운다.
        """
        with self._connect() as connection:
            dataset = connection.execute(
                "SELECT source_row_count FROM app_meta.dataset WHERE scenario_id = ?",
                [scenario_id],
            ).fetchone()
            if dataset is None:
                raise KeyError(f"시나리오를 찾을 수 없습니다: {scenario_id}")
            return max(int(dataset[0]), 0)

    def save_revision(
        self,
        scenario_id: str,
        revision_tables: Mapping[str, pd.DataFrame],
        preset: ScenarioPreset,
        *,
        revision_name: str,
        parent_revision_id: str | None = None,
        note: str | None = None,
        virtual_products: Sequence[Mapping[str, str]] = (),
    ) -> ScenarioSnapshot:
        require_tables(revision_tables, tuple(REVISION_TABLES), "리비전")
        revision_label = required_text(revision_name, "리비전명")
        reference_hash = hash_tables(revision_tables, tuple(REVISION_TABLES))
        revision_id = str(uuid4())

        with self._write_transaction() as connection:
            row = connection.execute(
                """
                SELECT s.active_revision_id,
                       COALESCE(MAX(r.revision_no), 0) AS latest_revision_no,
                       s.status
                FROM app_meta.scenario s
                LEFT JOIN app_meta.scenario_revision r ON r.scenario_id = s.scenario_id
                WHERE s.scenario_id = ?
                GROUP BY s.active_revision_id, s.status
                """,
                [scenario_id],
            ).fetchone()
            if row is None:
                raise KeyError(f"시나리오를 찾을 수 없습니다: {scenario_id}")
            active_revision_id, latest_revision_no, status = row
            if str(status) != "ACTIVE":
                raise ValueError("보관된 시나리오에는 새 리비전을 저장할 수 없습니다.")
            selected_parent_id = parent_revision_id or (
                str(active_revision_id) if active_revision_id else None
            )
            if selected_parent_id is not None:
                parent_owner = connection.execute(
                    """
                    SELECT scenario_id
                    FROM app_meta.scenario_revision
                    WHERE revision_id = ?
                    """,
                    [selected_parent_id],
                ).fetchone()
                if parent_owner is None or str(parent_owner[0]) != scenario_id:
                    raise ValueError(
                        f"상위 리비전이 현재 시나리오에 속하지 않습니다: {selected_parent_id}"
                    )
            validate_preset_processes(preset, revision_tables["RQ_REQB"])
            self._insert_revision(
                connection,
                revision_id=revision_id,
                scenario_id=scenario_id,
                revision_no=int(latest_revision_no) + 1,
                revision_name=revision_label,
                parent_revision_id=selected_parent_id,
                note=note,
                reference_hash=reference_hash,
                revision_tables=revision_tables,
                preset=preset,
                virtual_products=virtual_products,
            )
            connection.execute(
                """
                UPDATE app_meta.scenario
                SET active_revision_id = ?, updated_at = current_timestamp
                WHERE scenario_id = ?
                """,
                [revision_id, scenario_id],
            )

        return self.load_revision(revision_id)

    def list_scenarios(self, *, include_archived: bool = False) -> list[ScenarioSummary]:
        """누적 시나리오 목록. 사용자가 지정한 순서가 있으면 그 순서를 먼저 따른다.

        `list_order` 는 「목록 관리」에서 저장할 때만 채워진다. 한 번도 순서를 저장하지
        않았거나 그 뒤에 새로 만든 시나리오는 NULL 이므로 예전과 같이 최근 수정 순으로
        뒤에 붙는다.

        보관본은 기본으로 빠진다. 같은 원천 코드의 중복 등록을 막는 쪽처럼 **숨은 것까지
        봐야 하는 호출자만** `include_archived=True` 를 쓴다 — 그 판정이 보관본을 못 보면
        같은 코드로 시나리오가 하나 더 생긴다.
        """
        where_clause = "" if include_archived else "WHERE s.status = 'ACTIVE'"
        with self._connect() as connection:
            rows = connection.execute(
                SCENARIO_SUMMARY_SELECT
                + f" {where_clause}"
                + " ORDER BY s.list_order NULLS LAST, s.updated_at DESC, s.scenario_name"
            ).fetchall()
        return [scenario_summary(row) for row in rows]

    def archive_scenario(self, scenario_id: str) -> None:
        """시나리오를 목록에서 숨긴다. 행은 그대로 남아 되돌릴 수 있다.

        **파일 크기는 줄지 않는다** — 보관본의 기준정보·리비전·원천 행이 한 바이트도
        사라지지 않으므로 오히려 물리 삭제보다 크게 유지된다. 보관이 사는 것은 용량이
        아니라 실수를 되돌릴 여지다. 파일을 실제로 줄이려면 `delete_scenario` 로 지운 뒤
        `scripts/compact_duckdb.py` 로 재구축한다.
        """
        with self._write_transaction() as connection:
            _require_not_latest_official(connection, scenario_id, "보관")
            changed = connection.execute(
                """
                UPDATE app_meta.scenario
                SET status = 'ARCHIVED', updated_at = current_timestamp
                WHERE scenario_id = ? AND status = 'ACTIVE'
                RETURNING scenario_id
                """,
                [scenario_id],
            ).fetchone()
            if changed is None:
                raise KeyError(f"활성 시나리오를 찾을 수 없습니다: {scenario_id}")
            connection.execute(
                "UPDATE app_meta.dataset SET status = 'ARCHIVED' WHERE scenario_id = ?",
                [scenario_id],
            )
            home_profile_store.clear_global_comparison_scenario(connection, scenario_id)

    def restore_scenario(self, scenario_id: str) -> None:
        """보관을 풀어 목록으로 되돌린다."""
        with self._write_transaction() as connection:
            changed = connection.execute(
                """
                UPDATE app_meta.scenario
                SET status = 'ACTIVE', updated_at = current_timestamp
                WHERE scenario_id = ? AND status = 'ARCHIVED'
                RETURNING scenario_id
                """,
                [scenario_id],
            ).fetchone()
            if changed is None:
                raise KeyError(f"보관된 시나리오를 찾을 수 없습니다: {scenario_id}")
            connection.execute(
                "UPDATE app_meta.dataset SET status = 'READY' WHERE scenario_id = ?",
                [scenario_id],
            )

    def reorder_scenarios(self, scenario_ids: Sequence[str]) -> list[ScenarioSummary]:
        """목록의 누적 순서를 통째로 다시 매긴다.

        일부만 받아 부분 갱신하지 않는다. 남은 시나리오의 순서가 무엇이 되어야 하는지
        호출자가 모르는 채로 정하게 되고, 화면에서 본 순서와 저장된 순서가 어긋난다.
        """
        ordered = [str(scenario_id) for scenario_id in scenario_ids]
        if len(set(ordered)) != len(ordered):
            raise ValueError("목록 순서에 같은 시나리오가 두 번 들어 있습니다.")
        with self._write_transaction() as connection:
            # 목록이 보관본을 빼고 그리므로 대조 대상도 활성만이다. 전체와 대조하면
            # 보관본이 하나라도 있는 순간 「순서 저장」이 항상 실패한다.
            stored = {
                str(row[0])
                for row in connection.execute(
                    "SELECT scenario_id FROM app_meta.scenario WHERE status = 'ACTIVE'"
                ).fetchall()
            }
            if set(ordered) != stored:
                raise ValueError(
                    "목록 순서는 저장된 시나리오 전체를 한 번에 받아야 합니다. "
                    "화면을 새로 고쳐 최신 목록으로 다시 저장하세요."
                )
            for position, scenario_id in enumerate(ordered, start=1):
                connection.execute(
                    "UPDATE app_meta.scenario SET list_order = ? WHERE scenario_id = ?",
                    [position, scenario_id],
                )
        return self.list_scenarios()

    def list_revisions(self, scenario_id: str) -> list[RevisionSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                REVISION_SUMMARY_SELECT + " WHERE scenario_id = ? ORDER BY revision_no DESC",
                [scenario_id],
            ).fetchall()
        return [revision_summary(row) for row in rows]

    def rename_scenario(self, scenario_id: str, scenario_name: str) -> ScenarioSummary:
        """Rename mutable scenario metadata without changing immutable revisions."""
        label = required_text(scenario_name, "시나리오명")
        with self._write_transaction() as connection:
            _require_unique_scenario_name(connection, label, except_scenario_id=scenario_id)
            changed = connection.execute(
                """
                UPDATE app_meta.scenario
                SET scenario_name = ?, updated_at = current_timestamp
                WHERE scenario_id = ?
                RETURNING scenario_id
                """,
                [label, scenario_id],
            ).fetchone()
            if changed is None:
                raise KeyError(f"시나리오를 찾을 수 없습니다: {scenario_id}")
            # 비교 대상의 이름이 바뀐 것을 입장 화면 Summary GAP 이 알게 한다(그 값의 키가 version).
            home_profile_store.touch_global_comparison_scenario(connection, scenario_id)
        for scenario in self.list_scenarios():
            if scenario.scenario_id == scenario_id:
                return scenario
        raise KeyError(f"시나리오를 찾을 수 없습니다: {scenario_id}")

    def publish_official_revision(
        self,
        scenario_id: str,
        revision_id: str,
        *,
        release_name: str,
        note: str | None = None,
        expected_latest_release_no: int | None = None,
    ) -> OfficialReleaseSummary:
        """Append an official release pointer to one immutable revision.

        `expected_latest_release_no` 를 주면 쓰기 트랜잭션 안에서 지금 최신 공식버전 번호가 그것과
        같을 때만 발행한다. 다르면 `OfficialReleaseMoved` 로 거부하고 아무것도 쓰지 않는다 — 오래
        걸리는 배경 회차(공식버전 자동 갱신)가 출발할 때 본 공식버전 위에서만 발행하게 한다.
        """
        release_label = required_text(release_name, "공식버전명")
        official_release_id = str(uuid4())
        with self._write_transaction() as connection:
            owner = connection.execute(
                """
                SELECT s.status
                FROM app_meta.scenario_revision r
                JOIN app_meta.scenario s ON s.scenario_id = r.scenario_id
                WHERE r.revision_id = ? AND r.scenario_id = ?
                """,
                [revision_id, scenario_id],
            ).fetchone()
            if owner is None:
                raise ValueError("공식 지정할 리비전이 선택한 시나리오에 속하지 않습니다.")
            if str(owner[0]) != "ACTIVE":
                raise ValueError("보관된 시나리오는 공식버전으로 지정할 수 없습니다.")
            release_no_row = connection.execute(
                "SELECT COALESCE(MAX(release_no), 0) + 1 FROM app_meta.official_release"
            ).fetchone()
            if release_no_row is None:
                raise RuntimeError("다음 공식버전 번호를 계산하지 못했습니다.")
            release_no = int(release_no_row[0])
            if (
                expected_latest_release_no is not None
                and release_no - 1 != expected_latest_release_no
            ):
                raise OfficialReleaseMoved(expected_latest_release_no, release_no - 1)
            connection.execute(
                """
                INSERT INTO app_meta.official_release (
                    official_release_id, release_no, scenario_id, revision_id,
                    release_name, note
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    official_release_id,
                    release_no,
                    scenario_id,
                    revision_id,
                    release_label,
                    note.strip() if isinstance(note, str) and note.strip() else None,
                ],
            )
        release = self._official_release(official_release_id)
        if release is None:
            raise RuntimeError("저장한 공식버전을 다시 불러오지 못했습니다.")
        return release

    def latest_official_release(self) -> OfficialReleaseSummary | None:
        """Return the latest append-only official release pointer."""
        releases = self.list_official_releases(limit=1)
        return releases[0] if releases else None

    def list_official_releases(self, *, limit: int | None = None) -> list[OfficialReleaseSummary]:
        if limit is not None and limit <= 0:
            raise ValueError("공식버전 조회 건수는 1 이상이어야 합니다.")
        limit_clause = "" if limit is None else " LIMIT ?"
        parameters: list[object] = [] if limit is None else [limit]
        with self._connect() as connection:
            rows = connection.execute(
                OFFICIAL_RELEASE_SELECT + " ORDER BY o.release_no DESC" + limit_clause,
                parameters,
            ).fetchall()
        return [official_release_summary(row) for row in rows]

    def _official_release(self, official_release_id: str) -> OfficialReleaseSummary | None:
        with self._connect() as connection:
            row = connection.execute(
                OFFICIAL_RELEASE_SELECT + " WHERE o.official_release_id = ?",
                [official_release_id],
            ).fetchone()
        return official_release_summary(row) if row is not None else None

    def load_revision(
        self, revision_id: str, *, apply_global_display_order: bool = True
    ) -> ScenarioSnapshot:
        """일반 조회는 공용 표시순서를, 파생 시나리오 입력은 저장된 원본을 읽는다.

        리비전 확인과 표 16장·공용 표시순서를 한 읽기 트랜잭션에서 읽는다 — 그 사이 다른 세션이
        지우거나 표시순서를 바꿔도 한 시점의 것만 모인다.
        """
        with self._connect() as connection, transaction(connection):
            scenario_row = connection.execute(
                SCENARIO_SUMMARY_SELECT
                + """
                JOIN app_meta.scenario_revision selected_revision
                  ON selected_revision.scenario_id = s.scenario_id
                WHERE selected_revision.revision_id = ?
                """,
                [revision_id],
            ).fetchone()
            if scenario_row is None:
                raise KeyError(f"리비전을 찾을 수 없습니다: {revision_id}")
            scenario = scenario_summary(scenario_row)
            revision_row = connection.execute(
                REVISION_SUMMARY_SELECT + " WHERE revision_id = ?",
                [revision_id],
            ).fetchone()
            if revision_row is None:
                raise KeyError(f"리비전을 찾을 수 없습니다: {revision_id}")
            revision = revision_summary(revision_row)
            preset = load_preset(connection, revision_id)

            tables: dict[str, pd.DataFrame] = {
                logical_name: _load_reference_frame(
                    connection,
                    logical_name,
                    revision_id=revision_id,
                    dataset_id=scenario.dataset_id,
                )
                for logical_name in REFERENCE_TABLES
            }
            if apply_global_display_order and _has_global_display_order(connection):
                tables["RQ_DISPLAY_ORDER"] = load_global_display_order_rules(connection)
        return ScenarioSnapshot(
            scenario=scenario,
            revision=revision,
            preset=preset,
            tables=tables,
        )

    def load_revision_preset(self, revision_id: str) -> ScenarioPreset:
        """리비전의 프리셋 하나. 표를 읽지 않는다 — 공정 필터·레거시 기준만 필요한 쪽이 쓴다."""
        with self._connect() as connection:
            return load_preset(connection, revision_id)

    def load_revision_table(
        self,
        revision_id: str,
        logical_name: str,
        *,
        apply_global_display_order: bool = True,
    ) -> pd.DataFrame:
        """리비전의 표 한 장. `load_revision(...).tables[logical_name]` 과 같은 경로·프레임이다.

        리비전이 있는지 먼저 확인하고 없으면 `load_revision` 과 같은 `KeyError` 를 낸다. 리비전 표를
        `revision_id` 로 바로 읽으면 지운 리비전에서 행 0개 프레임이 예외 없이 돌아와, 비교 계획이면
        GAP 이 전부 감소로 그려진다. 확인과 읽기는 한 읽기 트랜잭션이다 — 확인 뒤 다른 세션이 지워도
        확인한 시점의 표를 읽는다(따로 된 두 문이면 그 틈에 지운 리비전의 행 0개가 돌아온다).
        """
        if logical_name not in REFERENCE_TABLES:
            raise ValueError(f"리비전 표가 아닙니다: {logical_name}")
        with self._connect() as connection, transaction(connection):
            owner_row = connection.execute(
                """
                SELECT d.dataset_id
                FROM app_meta.scenario_revision selected_revision
                JOIN app_meta.scenario s ON s.scenario_id = selected_revision.scenario_id
                JOIN app_meta.dataset d ON d.scenario_id = s.scenario_id
                WHERE selected_revision.revision_id = ?
                """,
                [revision_id],
            ).fetchone()
            if owner_row is None:
                raise KeyError(f"리비전을 찾을 수 없습니다: {revision_id}")
            if (
                logical_name == "RQ_DISPLAY_ORDER"
                and apply_global_display_order
                and _has_global_display_order(connection)
            ):
                return load_global_display_order_rules(connection)
            return _load_reference_frame(
                connection,
                logical_name,
                revision_id=revision_id,
                dataset_id=str(owner_row[0]),
            )

    def delete_scenario(self, scenario_id: str) -> None:
        """시나리오와 그것이 소유한 모든 행을 물리 삭제한다.

        지울 표를 손으로 적지 않고 `information_schema` 에서 소유 컬럼으로 찾는다.
        마이그레이션이 새 표를 더할 때마다 목록을 고치는 것을 잊으면 주인 없는 행이
        남는데, 그 누락은 삭제한 다음에야 드러나고 되돌릴 수 없다.

        DuckDB 는 지운 페이지를 파일에 되돌려주지 않는다. 행은 사라져도 파일 크기는 줄지
        않고 삭제 기록만큼 오히려 늘어난다. 실제로 줄이려면 별도 스냅샷 재작성이 필요하다.
        """
        with self._write_transaction() as connection:
            owner_row = connection.execute(
                """
                SELECT d.dataset_id
                FROM app_meta.scenario s
                JOIN app_meta.dataset d ON d.scenario_id = s.scenario_id
                WHERE s.scenario_id = ?
                """,
                [scenario_id],
            ).fetchone()
            if owner_row is None:
                raise KeyError(f"시나리오를 찾을 수 없습니다: {scenario_id}")
            dataset_id = str(owner_row[0])
            _require_not_latest_official(connection, scenario_id, "삭제")
            revision_ids = [
                str(row[0])
                for row in connection.execute(
                    "SELECT revision_id FROM app_meta.scenario_revision WHERE scenario_id = ?",
                    [scenario_id],
                ).fetchall()
            ]
            for schema, table, owner in _owned_tables(connection):
                qualified = f"{quote(schema)}.{quote(table)}"
                if owner == "scenario_id":
                    connection.execute(
                        f"DELETE FROM {qualified} WHERE scenario_id = ?", [scenario_id]
                    )
                elif owner == "dataset_id":
                    connection.execute(
                        f"DELETE FROM {qualified} WHERE dataset_id = ?", [dataset_id]
                    )
                elif revision_ids:
                    placeholders = ", ".join("?" for _ in revision_ids)
                    connection.execute(
                        f"DELETE FROM {qualified} WHERE revision_id IN ({placeholders})",
                        revision_ids,
                    )
            # 공용 프로필은 소유가 아니라 참조라 위 자동 발견에서 빠져 있다. 가리키고
            # 있었다면 여기서 비운다.
            home_profile_store.clear_global_comparison_scenario(connection, scenario_id)
            connection.execute("DELETE FROM app_meta.scenario WHERE scenario_id = ?", [scenario_id])

    def count_official_releases(self, scenario_id: str) -> int:
        """그 시나리오가 가진 공식 발행 이력 건수. 삭제 전 경고 문구가 쓴다."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT count(*) FROM app_meta.official_release WHERE scenario_id = ?",
                [scenario_id],
            ).fetchone()
        return 0 if row is None else int(row[0])

    def _insert_revision(
        self,
        connection: duckdb.DuckDBPyConnection,
        *,
        revision_id: str,
        scenario_id: str,
        revision_no: int,
        revision_name: str,
        parent_revision_id: str | None,
        note: str | None,
        reference_hash: str,
        revision_tables: Mapping[str, pd.DataFrame],
        preset: ScenarioPreset,
        virtual_products: Sequence[Mapping[str, str]] = (),
    ) -> None:
        connection.execute(
            """
            INSERT INTO app_meta.scenario_revision (
                revision_id, scenario_id, revision_no, revision_name,
                parent_revision_id, note, reference_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                revision_id,
                scenario_id,
                revision_no,
                revision_name,
                parent_revision_id,
                note,
                reference_hash,
            ],
        )
        for logical_name, table_name in REVISION_TABLES.items():
            insert_frame(
                connection,
                schema="rev_data",
                table_name=table_name,
                owner_column="revision_id",
                owner_id=revision_id,
                frame=revision_tables[logical_name],
                logical_name=logical_name,
            )
        insert_preset(connection, revision_id, preset)
        # 가상 제품은 실적과 대조할 수 없다. 어떤 제품이 어느 원본에서 복제됐는지
        # 리비전에 남겨야 공식버전 발행 시 확인할 수 있다.
        for record in virtual_products:
            connection.execute(
                """
                INSERT INTO app_meta.revision_virtual_product (
                    revision_id, "제품정보", "Stack", source_product, source_stack
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    revision_id,
                    record["product"],
                    record["stack"],
                    record["source_product"],
                    record["source_stack"],
                ],
            )

    def list_virtual_products(self, revision_id: str) -> pd.DataFrame:
        """리비전에 기록된 가상 제품 목록을 돌려준다. 공식버전 발행 전 확인용이다."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT "제품정보", "Stack", source_product, source_stack
                FROM app_meta.revision_virtual_product
                WHERE revision_id = ?
                ORDER BY "제품정보", "Stack"
                """,
                [revision_id],
            ).fetchall()
        return pd.DataFrame(rows, columns=["제품정보", "Stack", "원본 제품정보", "원본 Stack"])

    @contextmanager
    def _write_transaction(self) -> Iterator[duckdb.DuckDBPyConnection]:
        with _WRITE_LOCK, self._connect() as connection, transaction(connection):
            yield connection
        # COMMIT 이 끝나고 연결이 닫힌 뒤에만 표시한다. `sync_state` 는 등록되지 않은
        # 환경에서 아무 파일도 만들지 않으므로 개발 PC·CI 동작은 그대로다.
        sync_state.mark_dirty(self._database_path)

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return connect(self._database_path)
