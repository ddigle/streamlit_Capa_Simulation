# Purpose: 공용 확보율 판정 기준의 정규화·검증·실효 기준·버전 대조 저장·미저장 기본값을 고정한다.

from pathlib import Path

import pandas as pd
import pytest

from capa_simulation.persistence.models import ScenarioCreate, ScenarioPreset
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.persistence.securement_threshold_store import SecurementThresholdConflict
from capa_simulation.services.securement_threshold import (
    DEFAULT_SECURE_THRESHOLD,
    DEFAULT_WARNING_THRESHOLD,
    SECUREMENT_THRESHOLD_COLUMNS,
    SecurementThresholds,
    build_securement_thresholds,
    effective_securement_thresholds,
    empty_securement_threshold_rows,
    merge_securement_threshold_edits,
    prepare_securement_threshold_rows,
    validate_securement_thresholds,
)


def _rows(*rows: tuple[int, float | None, float | None]) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=list(SECUREMENT_THRESHOLD_COLUMNS))


def test_a_month_with_both_cells_blank_is_not_an_exception() -> None:
    prepared = prepare_securement_threshold_rows(
        _rows((202603, 1.195, None), (202601, None, None), (202602, None, 1.0))
    )

    assert prepared["생산계획년월"].tolist() == [202602, 202603]
    assert prepared["확보 기준"].isna().tolist() == [True, False]
    assert prepared["경고 기준"].isna().tolist() == [False, True]


@pytest.mark.parametrize("value", [0.0, -1.0, float("inf")])
def test_a_non_positive_or_infinite_month_value_is_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="26.02"):
        prepare_securement_threshold_rows(_rows((202602, value, None)))


def test_a_repeated_month_is_rejected() -> None:
    with pytest.raises(ValueError, match="같은 달"):
        prepare_securement_threshold_rows(_rows((202602, 1.2, None), (202602, 1.3, None)))


def test_a_blank_month_falls_back_to_the_default_per_item() -> None:
    thresholds = build_securement_thresholds(
        1.095, 0.995, _rows((202607, 1.195, None), (202608, None, 1.05))
    )

    # 저장값은 사사오입 정수 % 의 T/100 으로 읽는다(2026-11-01 — 1.095 → 1.1, 0.995 → 1.0).
    assert thresholds.for_month(202606) == (1.1, 1.0)
    # 확보만 적은 달의 경고는 기본값이다.
    assert thresholds.for_month(202607) == (1.2, 1.0)
    assert thresholds.for_month(202608) == (1.1, 1.05)
    assert thresholds.exception_months == (202607, 202608)
    assert thresholds.exception_months_within([202606, 202607]) == (202607,)

    table = effective_securement_thresholds(thresholds, [202608, 202606, 202607])
    assert table["생산계획년월"].tolist() == [202606, 202607, 202608]
    assert table["확보 기준"].tolist() == [1.1, 1.2, 1.1]
    assert table["경고 기준"].tolist() == [1.0, 1.0, 1.05]


def test_the_value_is_hashable_and_its_digest_follows_the_content() -> None:
    first = build_securement_thresholds(1.095, 0.995, _rows((202607, 1.195, None)))
    same = build_securement_thresholds(1.095, 0.995, _rows((202607, 1.195, None)))
    other = build_securement_thresholds(1.095, 0.995, _rows((202607, 1.21, None)))
    # 같은 정수 % 로 읽히는 저장값(1.195 와 1.2, 1.095 와 1.1)은 같은 판정이라 지문도 같다.
    rounded_same = build_securement_thresholds(1.1, 1.0, _rows((202607, 1.2, None)))

    assert hash(first) == hash(same)
    assert first.digest == same.digest
    assert first.digest != other.digest
    assert first.digest == rounded_same.digest
    assert SecurementThresholds(1.095, 0.995).digest != first.digest


def test_validation_merges_with_the_default_and_names_the_reversed_month() -> None:
    """확보만 낮춰 적은 달도 기본 경고와 합치면 거꾸로 짝이다. 어느 달인지 말한다."""
    with pytest.raises(ValueError, match=r"26\.07\(경고 100% > 확보 95%\)"):
        validate_securement_thresholds(1.095, 0.995, _rows((202607, 0.95, None)))

    with pytest.raises(ValueError, match="기본 경고 기준"):
        validate_securement_thresholds(1.0, 1.1, empty_securement_threshold_rows())

    with pytest.raises(ValueError, match="0 보다 큰"):
        validate_securement_thresholds(0.0, 0.0, empty_securement_threshold_rows())

    secure, warning, prepared = validate_securement_thresholds(
        1.095, 0.995, _rows((202607, 1.195, None))
    )
    # 새 저장은 정수 % 의 T/100 이다(2026-11-01 사용자 결정).
    assert (secure, warning) == (1.1, 1.0)
    assert prepared["생산계획년월"].tolist() == [202607]
    assert prepared["확보 기준"].tolist() == [1.2]

    # 사사오입해 0 이 되는 기준(0.4%)은 0 기준이라 거부한다.
    with pytest.raises(ValueError, match="0 보다 큰"):
        validate_securement_thresholds(1.1, 0.004, empty_securement_threshold_rows())
    with pytest.raises(ValueError, match="26.07"):
        validate_securement_thresholds(1.1, 1.0, _rows((202607, None, 0.004)))


def test_editing_a_narrow_view_keeps_the_months_it_could_not_show() -> None:
    stored = _rows((202601, 1.2, None), (202612, 1.3, 1.1))

    merged = merge_securement_threshold_edits(stored, [202601, 202602], [None, 1.25], [None, ""])

    # 보인 1월은 비워서 지워지고 2월이 들어왔다. 보이지 않던 12월은 그대로다.
    assert merged["생산계획년월"].tolist() == [202602, 202612]
    assert merged["확보 기준"].tolist() == [1.25, 1.3]


def test_an_unsaved_profile_uses_the_code_default_without_an_official_release(
    tmp_path: Path,
) -> None:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()

    profile = repository.load_global_securement_threshold()

    assert profile.version == 0
    assert (profile.default_secure, profile.default_warning) == (
        DEFAULT_SECURE_THRESHOLD,
        DEFAULT_WARNING_THRESHOLD,
    )
    assert profile.rows.empty
    assert profile.fallback == "코드 기본값"


def publish_official_preset(database: Path, secure: float, warning: float) -> None:
    """프리셋 판정 기준이 `secure`·`warning` 인 시나리오를 공식 v1 로 발행한다."""
    from capa_simulation.services.builtin_seed import (
        BUILTIN_SEED_MONTHS,
        build_builtin_seed_dataset,
        builtin_seed_processes,
    )

    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    prepared = build_builtin_seed_dataset()
    snapshot = repository.create_scenario(
        ScenarioCreate(
            scenario_name="판정 기준 시나리오",
            source_simulation_code="USER-SCENARIO-THRESHOLD",
            source_simulation_name="사용자 원천",
            source_type="TEST",
            pipeline_version="test-v1",
        ),
        prepared.reference_tables,
        ScenarioPreset(
            min(BUILTIN_SEED_MONTHS),
            max(BUILTIN_SEED_MONTHS),
            builtin_seed_processes(),
            secure_threshold=secure,
            warning_threshold=warning,
        ),
        source_data=prepared.source_data,
    )
    repository.publish_official_revision(
        snapshot.scenario.scenario_id, snapshot.revision.revision_id, release_name="공식"
    )


def test_an_unsaved_profile_follows_the_latest_official_preset(tmp_path: Path) -> None:
    database = tmp_path / "scenario.duckdb"
    publish_official_preset(database, 1.195, 0.995)
    repository = DuckDBScenarioRepository(database)

    profile = repository.load_global_securement_threshold()

    assert profile.version == 0
    # 옛 프리셋의 반 칸 낮춘 값도 정수 % 로 읽는다(1.195 → 120%, 0.995 → 100%).
    assert (profile.default_secure, profile.default_warning) == (1.2, 1.0)
    assert profile.fallback == "공식 v1 프리셋"
    # 읽기만 했다 — 사용자가 저장하기 전에는 DB 에 쓰지 않는다.
    with repository._connect() as connection:
        stored = connection.execute(
            "SELECT COUNT(*) FROM app_meta.global_securement_threshold"
        ).fetchone()
    assert stored == (0,)


@pytest.mark.parametrize(("secure", "warning"), [(1.095, 0.0), (0.0, 0.0)])
def test_an_unusable_official_preset_falls_back_to_the_code_default(
    tmp_path: Path, secure: float, warning: float
) -> None:
    # 레거시 프리셋은 경고 0 을 허용했다(옛 사이드바 칸의 하한이 0). 저장 규칙에 어긋나는 짝을
    # 기본값으로 쓰면 모든 공정이 확보로 판정되고 Preference 편집기 칸도 그려지지 않는다.
    database = tmp_path / "scenario.duckdb"
    publish_official_preset(database, secure, warning)

    profile = DuckDBScenarioRepository(database).load_global_securement_threshold()

    assert profile.version == 0
    assert (profile.default_secure, profile.default_warning) == (
        DEFAULT_SECURE_THRESHOLD,
        DEFAULT_WARNING_THRESHOLD,
    )
    assert profile.fallback.startswith("코드 기본값")
    assert "공식 v1 프리셋" in profile.fallback


def test_the_profile_round_trips_and_rejects_a_stale_save(tmp_path: Path) -> None:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()

    saved = repository.replace_global_securement_threshold(
        1.095,
        0.995,
        _rows((202607, 1.195, None), (202608, None, 1.0)),
        source="첫 저장",
        expected_version=0,
    )

    assert saved.version == 1
    assert saved.source == "첫 저장"
    assert saved.fallback == ""
    assert saved.thresholds.for_month(202607) == (1.2, 1.0)
    assert saved.thresholds.for_month(202608) == (1.1, 1.0)
    # 저장소에도 정수 % 의 T/100 으로 들어간다.
    assert (saved.default_secure, saved.default_warning) == (1.1, 1.0)
    assert saved.rows["확보 기준"].tolist()[0] == 1.2
    # 빈칸은 NULL 로 저장되어 그대로 빈칸으로 돌아온다.
    assert saved.rows["경고 기준"].isna().tolist() == [True, False]

    # 같은 v0 에서 출발한 두 번째 저장은 다른 세션이 먼저 저장한 것이라 거부한다.
    with pytest.raises(SecurementThresholdConflict, match="먼저"):
        repository.replace_global_securement_threshold(
            1.2, 1.0, empty_securement_threshold_rows(), source="늦은 저장", expected_version=0
        )
    assert repository.load_global_securement_threshold().version == 1

    cleared = repository.replace_global_securement_threshold(
        1.2, 1.0, empty_securement_threshold_rows(), source="예외 비움", expected_version=1
    )
    assert cleared.version == 2
    assert cleared.rows.empty
    assert (cleared.default_secure, cleared.default_warning) == (1.2, 1.0)


def test_a_reversed_month_is_not_written(tmp_path: Path) -> None:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()

    with pytest.raises(ValueError, match="26.07"):
        repository.replace_global_securement_threshold(
            1.095, 0.995, _rows((202607, 0.9, None)), source="거꾸로", expected_version=0
        )

    assert repository.load_global_securement_threshold().version == 0


def test_the_threshold_range_is_one_value_shared_with_the_constraint_target() -> None:
    """판정 기준 저장 범위와 제약 시뮬레이션 제약 확보율 검증은 한 값(50 ~ 300%)이다(2026-11-01
    사용자 결정 「제약 확보율처럼 50 ~ 300% 밖은 저장을 막음」 — 둘째 범위를 따로 두지 않는다)."""
    from capa_simulation.services import constraint_simulation
    from capa_simulation.services.securement_threshold import THRESHOLD_RANGE, threshold_range_text

    assert THRESHOLD_RANGE == (0.5, 3.0)
    assert constraint_simulation.TARGET_RANGE is THRESHOLD_RANGE
    assert threshold_range_text() == "50% ~ 300%"


def test_the_general_target_field_range_is_the_threshold_range() -> None:
    """제약 시뮬레이션 · 개조 일정의 「기준 확보율」 직접 입력 칸 범위도 판정 기준 저장 범위와 한 값
    (50 ~ 300%)이다(2026-11-02 사용자 결정 — Preference 에 저장한 기준을 칸에 그대로 칠 수 있다)."""
    from capa_simulation.services import constraint_simulation
    from capa_simulation.services.securement_threshold import THRESHOLD_RANGE

    assert constraint_simulation.GENERAL_INPUT_RANGE is THRESHOLD_RANGE


def test_out_of_range_cells_are_named_by_place_and_whole_percent() -> None:
    """범위는 사사오입한 정수 % 로 견준다 — 49.5% 는 50 이라 들고 300.5% 는 301 이라 밖이다. 빈칸 ·
    값이 아닌 칸은 보지 않는다(저장 검증이 따로 거부한다)."""
    from capa_simulation.services.securement_threshold import (
        out_of_range_thresholds,
        require_threshold_range,
    )

    rows = _rows((202602, 10.95, None), (202603, 3.0, 0.495), (202604, 3.005, 0.49))
    cells = out_of_range_thresholds(1.1, 0.4, rows)

    assert [cell.label for cell in cells] == [
        "기본 경고 기준 40%",
        "26.02 확보 기준 1095%",
        "26.04 확보 기준 301%",
        "26.04 경고 기준 49%",
    ]
    with pytest.raises(ValueError, match="50% ~ 300% 안의 정수 %") as raised:
        require_threshold_range(1.1, 0.4, rows)
    assert "26.02 확보 기준 1095%" in str(raised.value)
    assert out_of_range_thresholds(3.0, 0.5, _rows((202602, 0.495, None))) == ()
    require_threshold_range(1.1, 1.0, empty_securement_threshold_rows())
