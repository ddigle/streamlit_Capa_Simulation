# Purpose: 공용 공정 표시명의 정규화·1:1 검증·저장 왕복과 화면 적용 경계를 검증한다.

from pathlib import Path

import pandas as pd
import pytest

from capa_simulation.components.process_labels import (
    ProcessLabels,
    apply_process_label,
    process_labels_from_rules,
)
from capa_simulation.persistence import DuckDBScenarioRepository
from capa_simulation.services.process_rename import (
    PROCESS_RENAME_COLUMNS,
    drop_blank_process_rename_rows,
    empty_process_rename_rules,
    normalize_process_text,
    prepare_process_rename_rules,
    process_rename_from_clipboard,
    process_rename_to_csv,
    validate_process_rename_frame,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NO_BREAK_SPACE = " "


def _rules(pairs: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(pairs, columns=list(PROCESS_RENAME_COLUMNS))


def _labels(pairs: list[tuple[str, str]], version: int = 1) -> ProcessLabels:
    return process_labels_from_rules(_rules(pairs), version)


# ---------------------------------------------------------------- 정규화·검증


def test_normalization_strips_whitespace_and_no_break_space() -> None:
    """CSV·웹 표에서 긁어 온 값의 U+00A0 가 매칭을 어긋나게 하면 안 된다."""
    assert normalize_process_text(f"{NO_BREAK_SPACE} SAW{NO_BREAK_SPACE}A ") == "SAW A"
    assert normalize_process_text(None) == ""
    assert normalize_process_text(float("nan")) == ""


def test_stored_rules_keep_normalized_values() -> None:
    prepared = prepare_process_rename_rules(
        _rules([(f" SAW{NO_BREAK_SPACE}A ", f"{NO_BREAK_SPACE}절단 ")])
    )

    assert prepared["공정"].tolist() == ["SAW A"]
    assert prepared["표시명"].tolist() == ["절단"]
    assert NO_BREAK_SPACE not in "".join(prepared["표시명"].tolist())


def test_duplicate_display_name_is_rejected_at_input() -> None:
    with pytest.raises(ValueError, match="표시명이\\(가\\) 중복"):
        validate_process_rename_frame(_rules([("SAW", "절단"), ("MOLD", "절단")]))


def test_duplicate_source_process_is_rejected_at_input() -> None:
    with pytest.raises(ValueError, match="원본 공정명이\\(가\\) 중복"):
        validate_process_rename_frame(_rules([("SAW", "절단"), ("SAW", "쏘잉")]))


def test_duplicate_detection_sees_through_no_break_space() -> None:
    """정규화 뒤 같은 값이면 중복이다. 안 그러면 DB UNIQUE 가 대신 터진다."""
    with pytest.raises(ValueError, match="중복"):
        validate_process_rename_frame(_rules([("SAW", "절단"), (f"SAW{NO_BREAK_SPACE}", "쏘잉")]))


def test_blank_value_is_rejected() -> None:
    with pytest.raises(ValueError, match="표시명은\\(는\\) 비어 있을 수 없습니다"):
        validate_process_rename_frame(_rules([("SAW", "  ")]))


def test_empty_mapping_is_a_normal_state() -> None:
    """전체 해제를 허용해야 한다. 표시순서와 갈리는 유일한 검증 차이다."""
    validate_process_rename_frame(empty_process_rename_rules())

    assert prepare_process_rename_rules(empty_process_rename_rules()).empty


def test_blank_editor_rows_are_dropped_before_validation() -> None:
    edited = _rules([("SAW", "절단"), ("", "")])

    assert drop_blank_process_rename_rows(edited)["공정"].tolist() == ["SAW"]


def test_clipboard_import_normalizes_and_validates() -> None:
    parsed = process_rename_from_clipboard(f"공정\t표시명\nSAW{NO_BREAK_SPACE}A\t 절단 ")

    assert parsed["공정"].tolist() == ["SAW A"]
    assert parsed["표시명"].tolist() == ["절단"]


def test_clipboard_import_rejects_a_wrong_column_contract() -> None:
    with pytest.raises(ValueError, match="컬럼 계약"):
        process_rename_from_clipboard("공정\t별칭\nSAW\t절단")


def test_csv_round_trip_keeps_the_paste_contract() -> None:
    csv_bytes = process_rename_to_csv(_rules([("SAW", "절단")]))
    text = csv_bytes.decode("utf-8-sig")

    assert text.splitlines()[0] == "공정,표시명"
    assert process_rename_from_clipboard(text.replace(",", "\t"))["표시명"].tolist() == ["절단"]


# ---------------------------------------------------------------- 라벨 적용


def test_unmapped_process_keeps_its_original_name() -> None:
    labels = _labels([("SAW", "절단")])

    assert labels.label("SAW") == "절단"
    assert labels.label("MOLD") == "MOLD"


def test_display_name_for_an_unowned_process_is_ignored_not_an_error() -> None:
    labels = _labels([("SAW", "절단"), ("없는공정", "유령")])

    assert labels.label("SAW") == "절단"
    assert labels.unmatched(["SAW", "MOLD"]) == ["없는공정"]


def test_display_name_colliding_with_another_owned_process_is_counted() -> None:
    """1:1 검증은 규칙 안만 본다. 매핑 밖 원본명과 겹치는 표시명은 여기서 센다."""
    labels = _labels([("SAW", "MOLD")])

    assert labels.owned_name_collisions(["SAW", "MOLD", "CURE"]) == ["MOLD"]


def test_owned_name_collision_skips_self_and_renamed_away_processes() -> None:
    """자기 이름 그대로거나 그 공정이 다시 다른 이름이 되면 화면에서 겹치지 않는다."""
    labels = _labels([("SAW", "SAW"), ("MOLD", "CURE"), ("CURE", "경화")])

    assert labels.owned_name_collisions(["SAW", "MOLD", "CURE"]) == []


def test_owned_name_collision_skips_rules_whose_source_is_not_owned() -> None:
    """보유하지 않은 공정의 규칙은 화면에 나타나지 않아 겹칠 대상이 없다.

    세면 `unmatched()` 의 "무시합니다" 안내와 "같은 이름으로 보입니다" 경고가
    같은 화면에 함께 떠 서로 모순된다.
    """
    labels = _labels([("없는공정", "MOLD")])

    assert labels.owned_name_collisions(["SAW", "MOLD"]) == []


def test_lookup_normalizes_the_incoming_value() -> None:
    """화면 표는 공백을 U+00A0 으로 바꿔 그린다. 그 값으로도 매칭돼야 한다."""
    labels = _labels([("SAW A", "절단")])

    assert labels.label(f"SAW{NO_BREAK_SPACE}A") == "절단"


def test_empty_profile_leaves_every_value_untouched() -> None:
    assert apply_process_label("SAW", {}) == "SAW"
    assert ProcessLabels().label("SAW") == "SAW"
    assert ProcessLabels().value_labels() == {}


def test_value_labels_only_target_the_named_column() -> None:
    labels = _labels([("SAW", "절단")])

    assert labels.value_labels() == {"공정": labels.labels}
    assert "제품정보" not in labels.value_labels()


# ---------------------------------------------------------------- 저장 왕복


def _repository(database_path: Path) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    return repository


def test_profile_is_absent_until_the_first_save(tmp_path: Path) -> None:
    """한 번도 저장하지 않은 상태가 정상이다. 예외를 내면 모든 화면이 죽는다."""
    profile = _repository(tmp_path / "scenario.duckdb").load_global_process_rename()

    assert profile.version == 0
    assert profile.updated_at is None
    assert profile.rules.empty
    assert list(profile.rules.columns) == list(PROCESS_RENAME_COLUMNS)


def test_save_and_reload_round_trip(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")

    first = repository.replace_global_process_rename(
        _rules([("SAW", "절단"), ("MOLD", "성형")]),
        source="테스트 붙여넣기",
    )

    assert first.version == 1
    assert first.source == "테스트 붙여넣기"
    assert first.rules["표시명"].tolist() == ["절단", "성형"]

    second = repository.replace_global_process_rename(
        _rules([("SAW", "SAW-1")]),
        source="테스트 직접 편집",
    )

    assert second.version == 2
    assert second.rules["공정"].tolist() == ["SAW"]
    assert repository.load_global_process_rename().rules["표시명"].tolist() == ["SAW-1"]


def test_clearing_every_rule_still_raises_the_version(tmp_path: Path) -> None:
    """전체 해제도 캐시 무효화 대상이라 version 이 올라야 한다."""
    repository = _repository(tmp_path / "scenario.duckdb")
    repository.replace_global_process_rename(_rules([("SAW", "절단")]), source="초기")

    cleared = repository.replace_global_process_rename(
        empty_process_rename_rules(),
        source="전체 해제",
    )

    assert cleared.version == 2
    assert cleared.rules.empty
    assert repository.load_global_process_rename().rules.empty


def test_one_to_one_violation_is_rejected_before_it_reaches_the_database(tmp_path: Path) -> None:
    """DB UNIQUE 는 마지막 방어선이다. 화면 오류로 바뀌는 ValueError 가 먼저 나야 한다."""
    repository = _repository(tmp_path / "scenario.duckdb")

    with pytest.raises(ValueError):
        repository.replace_global_process_rename(
            _rules([("SAW", "절단"), ("MOLD", "절단")]),
            source="테스트",
        )

    assert repository.load_global_process_rename().version == 0


# ---------------------------------------------------------------- 경계 강제


def test_services_never_import_the_substitution_helper() -> None:
    """치환 헬퍼는 렌더 계층 한 모듈에만 둔다. 이 금지가 금지 목록 전체를 지킨다.

    `services/` 가 표시명을 다루기 시작하면 왕복 CSV·클립보드, 예외 메시지, 프리셋
    저장값에 표시명이 새고 `공정` 조인이 조용히 어긋난다.
    """
    offenders = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in (PROJECT_ROOT / "src/capa_simulation/services").rglob("*.py")
        if "components.process_labels" in path.read_text(encoding="utf-8")
        or "components import process_labels" in path.read_text(encoding="utf-8")
    ]

    assert not offenders, f"services 는 표시명 치환 헬퍼를 쓰지 않는다: {offenders}"


def test_persistence_stores_the_original_process_column_name() -> None:
    """화면 라벨 때문에 `Core_Data` 계약 컬럼명을 바꾸지 않는다."""
    sql = (
        PROJECT_ROOT / "src/capa_simulation/persistence/migrations/0015_global_process_rename.sql"
    ).read_text(encoding="utf-8")

    assert '"공정" VARCHAR NOT NULL' in sql
    assert sql.splitlines()[0].startswith("-- Purpose: ")
