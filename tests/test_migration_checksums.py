# Purpose: 이미 적용된 마이그레이션 SQL 이 바뀌지 않았는지와 러너가 바뀐 체크섬을 거부하는지 지킨다.

"""적용된 마이그레이션은 한 글자도 고치지 않는다 — 그 규칙을 기계로 지킨다.

러너(`persistence/_migration_core.py`)는 이미 적용된 버전의 체크섬이 지금 파일과 다르면
「이미 적용된 … 마이그레이션이 변경되었습니다」로 멈춘다. 그런데 그 거부는 **그 버전이 이미
적용된 DB** 에서만 난다. 시험은 늘 새 DB 를 만들므로 적용된 SQL 에 주석 한 줄을 더해도 전체
pytest 가 통과하고, 사내가 배포 ZIP 을 적용한 뒤 앱이 시작 단계에서 멈출 때에야 드러난다.

그래서 두 가지를 본다.

- 지금 파일의 체크섬을 버전별로 고정한 표와 견준다. **새 번호를 더하면 이 표에 한 줄을
  더한다** — 빠졌으면 실패 문구가 붙여 넣을 줄을 찍어 준다. 표의 값은 러너가 내는
  `Migration.checksum` 그대로다. 러너는 `read_text` 로 읽어 줄끝을 LF 로 맞춘 뒤 해시를 내므로
  체크아웃의 줄끝과 관계없이 같은 값이 나온다.
- 거부 줄 자체가 도는지 본다. 그 비교가 리팩토링으로 빠지면 고친 SQL 이 말없이 건너뛰어지고,
  위 표만으로는 그것을 잡지 못한다.

두 마이그레이션 디렉터리는 번호가 서로 독립이라 표도 따로 둔다.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import duckdb
import pytest

from capa_simulation.persistence.equipment_migration_runner import (
    apply_equipment_migrations,
    load_equipment_migrations,
)
from capa_simulation.persistence.migration_runner import (
    Migration,
    MigrationOutcome,
    apply_migrations,
    load_migrations,
)

# 시뮬레이션 DB(`persistence/migrations`). 2·3 은 영구 결번이라 없다.
_SIMULATION_CHECKSUMS: dict[int, str] = {
    1: "c086bdecc6c84f37f88c39cd2da4fd2a01046fb96abe9b7155e61fbc3740916c",
    4: "70c412e879a00d2abd8365581abb635c521084f98d0d16197e5de65920a433d4",
    5: "6738f16207abbe1d33f572f02392809cbe65b79dac8bd45d463709c8abf7086f",
    6: "de1eb4cccd0b251113fd854eab2e05cfc7cbf2e88e6dd8db5ce93975783ebb2d",
    7: "a0de7480086bb349233371d0e991b68adf7521f9a5e622e45861b5c083ddd155",
    8: "6011b7ea2f41aaa7fb274ad72ed3be28edabb7d3f5d6cbb07ac12ddf7e568ecc",
    9: "31d60c95474c1851594349e2e5049e710626769807afe3040b5ceca727fbb37a",
    10: "9c5884d6f87194a8f6b8c35566964865c3bf478267debcdedc98ed06fe8cdc4e",
    11: "5d3419a6cf4d82dcd10313693af69c1bcc42fe25507a28c365b4e410c16a81e1",
    12: "5f6041674d5382345af69080b330a6def94139b6e1e141383c7fa59763fb3cf6",
    13: "46dda1f68b8e184f21a8a0c545714a25f79d3da56bececfc7d5bd2f484e4a951",
    14: "b24278beeb47478a00f77dc12d91f7f78115c16a7d15572b13489bff6a0a77e1",
    15: "8949dd025e89edc7f250cf91fd05acfefb60aa63a598474b36c6bf6e51a908ca",
    16: "478ee5008e18cec8d7ee9e4f8564cccdba52d1edd48a6a8e8a983632c317f100",
    17: "bf77ce5510e25e7b31d341cf39ef4b324a89778632e8b8262c4376f60199bfea",
    18: "54b8823f7181d41bcd8d9bf1a6d715de8b5e7780467de4373cccaf1b62395e8d",
    19: "e15e95cf052f73ca5fd33265a24079db359eb11d0a627cd05c634320c6b28693",
    20: "240cfc2392bf0b37741808ab06bf3282a5fd4b69fc6ea21ca1af93c15d99b7f5",
    21: "1e9b4891339c03e203881ad276a13584bccc71c85257862de9064538dcac707b",
    22: "7cf901feecc3e61c42e54373beab5d0a5f0df46039e622ea3cbd80be43c5a3e8",
    23: "340b8bc10983da331255cee2721d992c27ae48703aaa4f1c799d7b0a8f2a3cab",
    24: "283a0f30764ea56c75b0294a07def42852791bfe8ab83692dad75174683b1020",
    25: "5e63265803583e310a672eb7b18016f557c5ab38a1f6c0fac9f288db63468818",
    26: "ba9d9d582dd2079889ef63c2e94465d203a194bc24766ca9d3be633f76e29e62",
    27: "ecccf1e34fd831a1b08c217e04809fd025a1b27e86250c4c30d73d4fb8f17763",
    28: "ff7177e80a80d41f4bd4589399866acb7fa3f42c311c4ef1bc9df8fc1ecca786",
    29: "42f0cc7cfdce892fe22fb9ca5e55b59518212688cda17718932190819c2026e2",
    31: "920a5d3f4857f82497f9ab603a73eda6948635d2388efbe9803ce804f2e67356",
    33: "26fd9e3c2dd3ac5b313f52c523e0ddeafe16bc33274f89947b6e98c57fc7278d",
    35: "09e582a1d1e2acada0325c0b1dd5ece8a7e9f24d306695363d325b1b0e02326e",
    36: "bc81808dd203b84697af7fb6803c339e5096df4471056a34bca929ed12e1635d",
}

# 가용설비 DB(`persistence/equipment_migrations`).
_EQUIPMENT_CHECKSUMS: dict[int, str] = {
    1: "a38269a327ca5aaa6dbbc8390105ece91438b93d3887133074129265177a1794",
    2: "16f7cbdf507ef16b7adf728c4fce7d04d9218db79b5b6474145f4a0688784075",
    3: "b7555c61e956695b5cddf4c1c50e77f6b9e60cd3efa017dbef629c6a5ce2794b",
    4: "a249fde784fbf34812ddf76c921e218b484dd0ec090dbba1b9e7793e5cc9ed93",
    5: "3787fcc65bb66a4e2112a5bebe49394b5bfd813d4c767c587fa1535183699b55",
    6: "afa24a8e45ad17d174518cb14371dc16ae1e857981649ff15f3a746b02f94dad",
    7: "9e17379a569f88dcc453908be511508d1886663d4dd3db3f54c62ff94646bb33",
    8: "25ce5062661daf48b64f41ee8524b54838d175c3f8bde7837196ad652b600a1c",
    9: "a4aa439722e3913b8ee3019c3d2b2fbaa8f3bb096705280f292156d94e920632",
    10: "2feac43ce8053c9a375cf0a9391658bf0d981e8e2ada54763e96249865762b83",
    11: "606ee9a40506dc8b1bd7ff5c4972f824880ba3eed1201679fd10f9ae889625d1",
    13: "ccee15f66d1357cd738e6f8db1e687a56f4fd31c24e49796c77774a8004a0083",
    15: "4b6e42d0c7f31516c59b3f07afa6b43e689a70241a16d7560366808748e3bd2d",
    17: "33bdea549333cc57879c560ac3648bce6471200b056ae03f3f1ad36827fc53da",
    19: "a14665ebf14436dd2a94bade44b4ccdcfd4599dd8cbe8a75458ed2dfefce80b4",
    21: "ba537d93470581499a300c9dea6fb39d0a00e64ced4279b96bc6dd7c96d0139f",
    23: "9db213a9dd7f41261b0ee5daed2d82b1ed8cf673f6020229087d02806d4f7b60",
    25: "fe4a15c67aabceac834fbcad801e1eac5d0fc67c72c442eb71b8b0e0df45b30e",
    27: "6fea88ce74ab6e3d1303d700b6fd87c605cad59ff02be0e649c5540eb9c23d33",
    29: "9ee8a08a23e5d51f77fbf6568b6af10c69a955c60e4a693175a09d043ac6b408",
}

Loader = Callable[[], tuple[Migration, ...]]
Runner = Callable[[duckdb.DuckDBPyConnection], MigrationOutcome]

_PINNED = [
    pytest.param(load_migrations, _SIMULATION_CHECKSUMS, "_SIMULATION_CHECKSUMS", id="simulation"),
    pytest.param(
        load_equipment_migrations, _EQUIPMENT_CHECKSUMS, "_EQUIPMENT_CHECKSUMS", id="equipment"
    ),
]


@pytest.mark.parametrize(("loader", "pinned", "table_name"), _PINNED)
def test_applied_migrations_keep_their_pinned_checksums(
    loader: Loader, pinned: dict[int, str], table_name: str
) -> None:
    current = {migration.version: migration for migration in loader()}
    changed = sorted(
        current[version].name
        for version, checksum in pinned.items()
        if version in current and current[version].checksum != checksum
    )
    missing = sorted(version for version in pinned if version not in current)

    assert not changed, (
        f"적용된 마이그레이션 SQL 이 바뀌었습니다: {changed}. 그 번호가 적용된 DB 에서는 앱이 "
        "시작하지 못합니다. 되돌리고, 바꿀 것은 새 번호의 마이그레이션으로 더하세요"
        "(docs/migration_catalog.md). 아직 어디에도 배포하지 않은 번호라면 "
        f"{table_name} 의 값을 새 체크섬으로 바꿉니다(AGENTS.md 0장)."
    )
    assert not missing, (
        f"적용된 마이그레이션 파일이 사라졌습니다: 버전 {missing}. 새 DB 에는 그 스키마가 생기지 "
        "않습니다. 되돌리세요. 정말 걷어 낸 것이면 그 번호를 결번으로 적고"
        f"(docs/migration_catalog.md) {table_name} 에서 뺍니다."
    )


@pytest.mark.parametrize(("loader", "pinned", "table_name"), _PINNED)
def test_every_migration_is_pinned(loader: Loader, pinned: dict[int, str], table_name: str) -> None:
    unpinned = [migration for migration in loader() if migration.version not in pinned]

    assert not unpinned, (
        f"체크섬 표에 없는 마이그레이션이 있습니다: {[m.name for m in unpinned]}. "
        f"tests/test_migration_checksums.py 의 {table_name} 끝에 아래 줄을 더하세요 — "
        "그 뒤로 그 파일은 고치지 않습니다.\n"
        + "\n".join(f'    {m.version}: "{m.checksum}",' for m in unpinned)
    )


_RUNNERS = [
    pytest.param(apply_migrations, load_migrations, "app_meta", "DuckDB", id="simulation"),
    pytest.param(
        apply_equipment_migrations,
        load_equipment_migrations,
        "equipment_meta",
        "설비 DB",
        id="equipment",
    ),
]


@pytest.mark.parametrize(("apply", "loader", "schema", "label"), _RUNNERS)
def test_runner_refuses_an_applied_migration_whose_checksum_changed(
    apply: Runner, loader: Loader, schema: str, label: str
) -> None:
    """적용 기록의 체크섬 한 칸을 바꿔 「파일이 바뀐 DB」를 만들고, 러너가 멈추는지 본다.

    맨 끝 번호의 기록도 지워 아직 적용되지 않은 것처럼 둔다. 거부는 맨 앞 번호에서 나므로
    그 뒤의 번호를 적용하지 않고 멈춰야 한다.
    """
    migrations = loader()
    tampered, pending = migrations[0], migrations[-1]

    with duckdb.connect(":memory:") as connection:
        assert apply(connection).applied == tuple(migration.version for migration in migrations)
        # 파일이 그대로면 다시 불러도 거부하지 않는다 — 아래 거부가 기록을 바꾼 탓임을 가른다.
        assert apply(connection).applied == ()

        connection.execute(
            f"UPDATE {schema}.schema_migration SET checksum = 'tampered' WHERE version = ?",
            [tampered.version],
        )
        connection.execute(
            f"DELETE FROM {schema}.schema_migration WHERE version = ?", [pending.version]
        )

        with pytest.raises(
            RuntimeError,
            match=re.escape(f"이미 적용된 {label} 마이그레이션이 변경되었습니다: {tampered.name}"),
        ):
            apply(connection)

        recorded = connection.execute(
            f"SELECT version FROM {schema}.schema_migration ORDER BY version"
        ).fetchall()

    assert pending.version not in {int(version) for (version,) in recorded}
