# Purpose: 결번된 마이그레이션 번호를 다시 쓰지 못하게 막는다.

"""시뮬레이션 DB의 2·3번은 영구 결번이다.

설비 운영을 별도 DuckDB로 분리하면서 `0002_equipment_operations.sql` 과
`0003_equipment_baseline_double.sql` 파일만 저장소에서 사라지고, 개발 DuckDB의
`app_meta.schema_migration` 에는 적용 완료 기록이 그대로 남았다. 그 흔적으로 시뮬레이션
DB에 빈 `equipment_ops` 스키마가 남아 있다.

러너는 파일명이 아니라 **버전 번호로 체크섬을 대조**한다. 그래서 누구든 그 번호를 새로
쓰면, 이미 그 번호가 적용된 DB에서만 "이미 적용된 DuckDB 마이그레이션이 변경되었습니다"
로 앱이 시작조차 못 한다. 신규 체크아웃에서는 재현되지 않아 원인을 찾기 어렵다.

번호가 비어 있는 것 자체는 문제가 아니다. 러너는 빈 번호를 건너뛴다. 막아야 하는 것은
**그 번호를 재사용하는 것** 하나뿐이다.
"""

from pathlib import Path

from capa_simulation.persistence.migration_runner import load_migrations

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 개발 DuckDB 에 적용 기록만 남아 있는 번호. 파일로 되살리면 안 된다.
BURNED_VERSIONS = frozenset({2, 3})

CATALOG = PROJECT_ROOT / "docs" / "migration_catalog.md"


def test_burned_migration_versions_are_never_reused() -> None:
    reused = sorted(
        migration.name for migration in load_migrations() if migration.version in BURNED_VERSIONS
    )

    assert not reused, (
        "결번된 번호를 다시 썼습니다. 마지막 번호 다음을 쓰세요: "
        f"{reused} (결번 {sorted(BURNED_VERSIONS)})"
    )


def test_migration_versions_are_strictly_increasing() -> None:
    """번호가 겹치면 러너가 조용히 하나만 적용한다. 파일명 정렬과 번호 순서가 같아야 한다."""
    versions = [migration.version for migration in load_migrations()]

    assert versions == sorted(set(versions)), f"버전이 중복되거나 정렬이 어긋납니다: {versions}"


def test_catalog_records_the_burned_numbers() -> None:
    """카탈로그를 읽고 번호를 고르는 사람이 결번을 알 수 있어야 한다."""
    catalog = CATALOG.read_text(encoding="utf-8")

    assert "결번" in catalog
    assert "0002_equipment_operations.sql" in catalog
    assert "0003_equipment_baseline_double.sql" in catalog
