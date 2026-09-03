# Purpose: Python·PowerShell 파일의 Purpose 헤더와 SQL 마이그레이션 카탈로그 등록을 검증한다.

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORIES = ("app_pages", "scripts", "src", "tests")
HEADER_SUFFIXES = {".py", ".ps1"}
PURPOSE_PREFIX = "# Purpose: "
MIGRATION_CATALOG = PROJECT_ROOT / "docs" / "migration_catalog.md"


def _source_files() -> list[Path]:
    files = [PROJECT_ROOT / "app.py"]
    for directory in SOURCE_DIRECTORIES:
        files.extend(
            path
            for path in (PROJECT_ROOT / directory).rglob("*")
            if path.is_file() and path.suffix.lower() in HEADER_SUFFIXES
        )
    return sorted(set(files))


def _relative_posix(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def test_all_source_files_declare_a_purpose() -> None:
    errors: list[str] = []
    for path in _source_files():
        header = path.read_text(encoding="utf-8-sig").splitlines()[:1]
        relative_path = path.relative_to(PROJECT_ROOT)
        if not header:
            errors.append(f"{relative_path}: 파일이 비어 있어 Purpose 헤더가 없습니다.")
            continue
        if not header[0].startswith(PURPOSE_PREFIX) or not header[0][len(PURPOSE_PREFIX) :].strip():
            errors.append(f"{relative_path}:1: {PURPOSE_PREFIX.strip()} 항목이 없습니다.")

    assert not errors, "\n" + "\n".join(errors)


def test_all_immutable_sql_migrations_are_documented_without_modification() -> None:
    catalog = MIGRATION_CATALOG.read_text(encoding="utf-8")
    migrations = sorted((PROJECT_ROOT / "src" / "capa_simulation" / "persistence").rglob("*.sql"))

    missing = [
        _relative_posix(path) for path in migrations if f"`{_relative_posix(path)}`" not in catalog
    ]

    assert not missing, "SQL 마이그레이션 카탈로그 누락:\n" + "\n".join(missing)
