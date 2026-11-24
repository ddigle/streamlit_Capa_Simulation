# Purpose: 0039 전 DB 사본 시험 도우미가 코드의 0039 뒤 마이그레이션을 모두 아는지 고정한다.

"""`tests/before_custom_copy.py` 의 짝.

도우미는 `0039` 의 칸만 걷고 최고 번호를 38 로 돌린다. 코드에 `0039` 뒤 번호가 더해지면 그 번호가
만든 물체를 가진 채 최고 번호만 38 인 사본이 되어, 실제 0038 사본에서 멈출 「그 표가 없으면」 갈래를
확인 스크립트 시험이 타지 않는다. 그래서 번호가 더해지는 첫 회차에 이 시험이 먼저 깨진다.
"""

from __future__ import annotations

from before_custom_copy import KNOWN_LATER_MIGRATIONS

from capa_simulation.persistence.migration_runner import load_migrations
from capa_simulation.services.revision_compatibility import CUSTOM_MIGRATION


def test_the_helper_knows_every_migration_from_the_custom_column_on() -> None:
    """코드의 0039 와 그 뒤 번호 = 도우미가 물체를 걷는 번호. 다르면 그 번호가 만든 표 · 칸도 걷게
    `database_before_custom` 을 넓히고 `KNOWN_LATER_MIGRATIONS` 에 더한다."""
    later = tuple(
        sorted(
            migration.version
            for migration in load_migrations()
            if migration.version >= CUSTOM_MIGRATION
        )
    )

    assert later == KNOWN_LATER_MIGRATIONS, (
        f"코드의 0039 와 그 뒤 마이그레이션 {later} ≠ 도우미 {KNOWN_LATER_MIGRATIONS} — "
        "before_custom_copy 가 더한 번호의 물체를 걷게 넓힌다"
    )
