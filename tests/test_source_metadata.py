# Purpose: Python·PowerShell 메타데이터 헤더와 SQL 마이그레이션 카탈로그 등록을 검증한다.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 소스 헤더와 불변 SQL sidecar 카탈로그의 자동 누락 검사를 추가함.

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORIES = ("app_pages", "scripts", "src", "tests")
HEADER_SUFFIXES = {".py", ".ps1"}
HEADER_FIELDS = ("Purpose", "Applied", "Agent", "Model", "Change")
APPLIED_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} KST$")
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


def test_all_source_files_have_current_change_metadata() -> None:
    errors: list[str] = []
    for path in _source_files():
        marker = "#"
        header = path.read_text(encoding="utf-8-sig").splitlines()[:5]
        relative_path = path.relative_to(PROJECT_ROOT)
        if len(header) < len(HEADER_FIELDS):
            errors.append(f"{relative_path}: 헤더가 5줄보다 짧습니다.")
            continue
        for index, field in enumerate(HEADER_FIELDS):
            prefix = f"{marker} {field}: "
            if not header[index].startswith(prefix) or not header[index][len(prefix) :].strip():
                errors.append(f"{relative_path}:{index + 1}: {prefix.strip()} 항목이 없습니다.")
        if header[1].startswith(f"{marker} Applied: "):
            applied = header[1].split(": ", 1)[1]
            if APPLIED_PATTERN.fullmatch(applied) is None:
                errors.append(f"{relative_path}:2: Applied는 YYYY-MM-DD KST 형식이어야 합니다.")

    assert not errors, "\n" + "\n".join(errors)


def test_all_immutable_sql_migrations_are_documented_without_modification() -> None:
    catalog = MIGRATION_CATALOG.read_text(encoding="utf-8")
    migrations = sorted((PROJECT_ROOT / "src" / "capa_simulation" / "persistence").rglob("*.sql"))

    missing = [
        _relative_posix(path) for path in migrations if f"`{_relative_posix(path)}`" not in catalog
    ]

    assert not missing, "SQL 마이그레이션 카탈로그 누락:\n" + "\n".join(missing)
