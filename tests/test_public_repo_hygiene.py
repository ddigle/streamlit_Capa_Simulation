# Purpose: 공개 저장소에 사내 호스트·개인키·키/인증서 파일이 들어오지 않는지 감시한다.

"""공개 저장소 위생.

이 저장소의 사외 원격은 공개다. 통합인증을 붙이며 사내 값(ADFS 호스트 · C-DEP 서비스 주소 · 서명
인증서)이 대화로 오갔다 — 그 값은 C-DEP 환경변수 표에만 두고 파일 · 시험 · 문서 · 커밋에는 쓰지
않는다. 이 시험은 그중 파일을 지킨다(커밋 메시지 · 가지 이름은 못 본다 — 손 규칙, AGENTS 10장).

찾을 글자는 조각을 이어 만든다 — 이 파일 원문이 스스로 걸리지 않게. 회사 도메인 접미사(첫째)는 이
작업 전부터 있던 자리만 **파일별 수로 고정**해 허용한다(사내 BigDataQuery · 오브젝트 스토리지 · 사내
패키지 인덱스). 새 파일이나 늘어난 수는 실패, 줄어들면 「목록도 줄인다」 로 실패한다 — 목록이 낡지
않게. 사내에만 생기는 최상위(`review/` · `modules/` · `.deploy/`)는 보지 않는다 — 사내 리뷰 글이
사내 주소를 담아도 사내 관문이 깨지지 않게.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from test_repository_hygiene import _core_tracked, _tracked

PROJECT_ROOT = Path(__file__).resolve().parents[1]

COMPANY_SUFFIX = ("sams" + "ungds").encode("ascii")
SSO_SUFFIX = ("sec" + "sso").encode("ascii")
CDEP_HOST = b"cdep." + COMPANY_SUFFIX
PRIVATE_KEY_MARK = re.compile(b"-----BEGIN" + rb"[A-Z ]*" + b"PRIVATE" + rb" KEY-----")
KEY_FILE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".cer", ".crt", ".der", ".jks")

# 이 작업(2026-11-02) 전부터 있던 첫째 접미사 자리 — 파일별 수.
COMPANY_SUFFIX_ALLOWED = {
    "config/object_storage.json": 1,
    "docker/Dockerfile-prod": 1,
    "docs/bigdataquery_webide_setup.md": 1,
    "docs/objectstore_setup.md": 1,
    "requirements-company.txt": 2,
    "src/capa_simulation/io/object_storage.py": 1,
}


def _core_files() -> dict[str, bytes]:
    contents: dict[str, bytes] = {}
    for path in _core_tracked(_tracked()):
        target = PROJECT_ROOT / path
        if target.is_file():
            contents[path] = target.read_bytes().lower()
    return contents


def test_company_suffix_stays_in_the_fixed_places() -> None:
    found = Counter(
        {
            path: data.count(COMPANY_SUFFIX)
            for path, data in _core_files().items()
            if COMPANY_SUFFIX in data
        }
    )

    new_places = {
        path: count for path, count in found.items() if count > COMPANY_SUFFIX_ALLOWED.get(path, 0)
    }
    shrunk = {
        path: (allowed, found.get(path, 0))
        for path, allowed in COMPANY_SUFFIX_ALLOWED.items()
        if found.get(path, 0) < allowed
    }

    assert not new_places, (
        "사내 도메인이 새 자리에 들어왔습니다. 공개 저장소에는 사내 값을 쓰지 않습니다 — "
        f"환경변수로 받고 예시는 example.invalid 로 적습니다: {new_places}"
    )
    assert not shrunk, f"허용 자리가 줄었습니다. `COMPANY_SUFFIX_ALLOWED` 도 줄입니다: {shrunk}"


def test_sso_and_service_hosts_never_appear() -> None:
    files = _core_files()

    sso = sorted(path for path, data in files.items() if SSO_SUFFIX in data)
    service = sorted(path for path, data in files.items() if CDEP_HOST in data)

    assert not sso, f"통합인증 호스트 접미사가 들어왔습니다: {sso}"
    assert not service, f"C-DEP 서비스 호스트가 들어왔습니다: {service}"


def test_no_private_key_is_tracked() -> None:
    marked = sorted(
        path for path, data in _core_files().items() if PRIVATE_KEY_MARK.search(data.upper())
    )

    assert not marked, f"개인키 표지가 있는 파일입니다. 키는 실행 때 만듭니다: {marked}"


def test_no_key_or_certificate_file_is_tracked() -> None:
    files = sorted(
        path
        for path in _core_tracked(_tracked())
        if path.lower().endswith(KEY_FILE_SUFFIXES) or path.lower().startswith("cert/")
    )

    assert not files, f"키 · 인증서 파일은 커밋하지 않습니다(서명 인증서는 환경변수로): {files}"


def test_ignore_files_and_the_deploy_builder_block_key_files() -> None:
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from build_deploy_package import FORBIDDEN_SUFFIXES

    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for suffix in KEY_FILE_SUFFIXES:
        assert f"*{suffix}" in gitignore, suffix
        assert f"*{suffix}" in dockerignore, suffix
        assert suffix in FORBIDDEN_SUFFIXES, suffix
    assert "cert/" in gitignore and "cert/" in dockerignore


def test_the_needles_do_not_match_their_own_source() -> None:
    """조각으로 만든 글자가 이 파일 원문에 그대로 있지 않다(있으면 위 시험이 스스로 걸린다)."""
    source = Path(__file__).read_bytes().lower()

    assert COMPANY_SUFFIX not in source
    assert SSO_SUFFIX not in source
    assert not PRIVATE_KEY_MARK.search(source.upper())
