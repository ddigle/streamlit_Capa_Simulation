# Purpose: 공개 저장소에 사내 호스트·S3 값·사람 이름·개인키·키/인증서 파일이 안 들어오게 감시한다.

"""공개 저장소 위생.

이 저장소의 사외 원격은 공개다. 통합인증을 붙이며 사내 값(ADFS 호스트 · C-DEP 서비스 주소 · 서명
인증서)이 대화로 오갔다 — 그 값은 C-DEP 환경변수 표에만 두고 파일 · 시험 · 문서 · 커밋에는 쓰지
않는다. 이 시험은 그중 파일을 지킨다(커밋 메시지 · 가지 이름은 못 본다 — 손 규칙, AGENTS 10장).

찾을 글자는 조각을 이어 만든다 — 이 파일 원문이 스스로 걸리지 않게. 회사 도메인 접미사(첫째)는
사내 빌드가 실제로 쓰는 두 줄(운영 이미지 기반 · 사내 패키지 인덱스)만 **파일별 수로 고정**해
허용한다. 새 파일이나 늘어난 수는 실패, 줄어들면 「목록도 줄인다」 로 실패한다 — 목록이 낡지 않게.
사내에만 생기는 최상위(`review/` · `modules/` · `.deploy/`)는 보지 않는다 — 사내 리뷰 글이 사내
주소를 담아도 사내 관문이 깨지지 않게.

사내 오브젝트 스토리지 값(저장소 호스트 · 버킷 이름 접두 · 네임스페이스)과 사람 이름 · 회사 메일
도메인도 같은 꼴로 지킨다(2026-11-12 사용자 결정 — 문서는 자리표, 코드는 환경변수로만). 사람 이름 ·
메일 도메인 바늘은 이 파일에 새로 적지 않고 앱 연락 메일(`settings.APP_CONTACT_EMAIL`)에서 읽으며,
허용은 그 한 자리뿐이다. 이름은 앞자리 통째와, 구분자(`.` · `_` · `-`)로 나눈 조각 가운데 여섯 자
이상인 것을 따로 본다 — 구분자 · 차례가 다른 꼴로 들어와도 걸리게. 바늘은 base64 그림 안에서 우연히
맞지 않게 여섯 자 이상으로 잡았고, 실패 글에는 바늘 값 대신 이름만 싣는다(공개 CI 기록에 값이 남지
않게). 연락 메일을 걷을 때는(범위 밖 따로 물음) 이름 · 도메인 바늘을 위 셋처럼 조각 잇기로 이 파일에
옮긴다 — 바늘째 지우면 이름 그물이 없어진다.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from test_repository_hygiene import _core_tracked, _tracked

from capa_simulation import settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]

COMPANY_SUFFIX = ("sams" + "ungds").encode("ascii")
SSO_SUFFIX = ("sec" + "sso").encode("ascii")
CDEP_HOST = b"cdep." + COMPANY_SUFFIX
# 사내 값 바늘 — 이름 → (소문자 글자, 허용 자리 · 수). 앞 셋은 조각을 잇고 뒤 둘은 연락 메일에서
# 읽는다.
_CONTACT_LOCAL, _CONTACT_DOMAIN = settings.APP_CONTACT_EMAIL.lower().split("@", 1)
_CONTACT_PLACE = {"src/capa_simulation/settings.py": 1}
# 바늘의 가장 짧은 길이 — 이보다 짧으면 base64 그림 · 흔한 낱말에 우연히 맞는다.
NEEDLE_MIN_LENGTH = 6
_NAME_PIECES = [
    piece
    for piece in re.split(r"[._-]", _CONTACT_LOCAL)
    if len(piece) >= NEEDLE_MIN_LENGTH and piece != _CONTACT_LOCAL
]
IN_HOUSE_NEEDLES: dict[str, tuple[bytes, dict[str, int]]] = {
    "저장소 호스트": (("data" + "platform").encode("ascii"), {}),
    "버킷 이름 접두": (("spkg" + "capa").encode("ascii"), {}),
    "네임스페이스": (("system" + "_package").encode("ascii"), {}),
    "사람 이름": (_CONTACT_LOCAL.encode("ascii"), _CONTACT_PLACE),
    **{
        f"사람 이름 조각 {index}": (piece.encode("ascii"), _CONTACT_PLACE)
        for index, piece in enumerate(_NAME_PIECES, 1)
    },
    "회사 메일 도메인": (_CONTACT_DOMAIN.encode("ascii"), _CONTACT_PLACE),
}
PRIVATE_KEY_MARK = re.compile(b"-----BEGIN" + rb"[A-Z ]*" + b"PRIVATE" + rb" KEY-----")
KEY_FILE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".cer", ".crt", ".der", ".jks")

# 이 작업(2026-11-02) 전부터 있던 첫째 접미사 자리 — 파일별 수.
COMPANY_SUFFIX_ALLOWED = {
    "docker/Dockerfile-prod": 1,
    "requirements-company.txt": 1,
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


def test_in_house_storage_values_and_people_stay_out() -> None:
    """사내 S3 값 · 사람 이름이 추적 파일에 다시 들어오면 실패한다. 허용 자리가 줄어도 실패한다."""
    files = _core_files()
    new_places: dict[str, dict[str, int]] = {}
    shrunk: dict[str, dict[str, tuple[int, int]]] = {}
    for label, (needle, allowed) in IN_HOUSE_NEEDLES.items():
        found = {path: data.count(needle) for path, data in files.items() if needle in data}
        grown = {path: count for path, count in found.items() if count > allowed.get(path, 0)}
        fewer = {
            path: (count, found.get(path, 0))
            for path, count in allowed.items()
            if found.get(path, 0) < count
        }
        if grown:
            new_places[label] = grown
        if fewer:
            shrunk[label] = fewer

    assert not new_places, (
        "사내 값이 추적 파일에 들어왔습니다. 문서는 자리표(<사내 S3 주소> 꼴)로, 코드는 "
        f"환경변수로만 받습니다(docs/objectstore_setup.md 1 · 2장): {new_places}"
    )
    assert not shrunk, f"허용 자리가 줄었습니다. `IN_HOUSE_NEEDLES` 도 줄입니다: {shrunk}"


def test_the_in_house_needles_are_long_enough_to_mean_something() -> None:
    """짧은 바늘은 그림 · 낱말에 우연히 맞아 허용 목록이 늘어난다. 이름 조각도 하나는 있다."""
    short = [
        label for label, (needle, _) in IN_HOUSE_NEEDLES.items() if len(needle) < NEEDLE_MIN_LENGTH
    ]

    assert not short, f"바늘이 너무 짧습니다: {short}"
    assert _NAME_PIECES, "연락 메일 앞자리에서 여섯 자 이상 이름 조각을 찾지 못했습니다"


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
        # .dockerignore 의 `*.pem` 은 뿌리에만 걸린다 — 모든 깊이는 `**/` 꼴이어야 한다.
        assert f"**/*{suffix}" in dockerignore, suffix
        assert suffix in FORBIDDEN_SUFFIXES, suffix
    assert "cert/" in gitignore and "**/cert/" in dockerignore


def _docker_pattern(pattern: str) -> re.Pattern[str]:
    """`.dockerignore` 한 줄 → Docker(moby patternmatcher)와 같은 뜻의 정규식.

    빌드 컨텍스트 뿌리에서 시작하고, `*` · `?` 는 `/` 를 넘지 않으며, `**` 는 몇 단(0단 포함)의
    폴더든 된다. 끝 `/` 는 지운다(Go `filepath.Clean`).
    """
    text = pattern.strip().removeprefix("./").rstrip("/")
    out = ""
    index = 0
    while index < len(text):
        if text.startswith("**/", index):
            out += "(?:.*/)?"
            index += 3
        elif text.startswith("**", index):
            out += ".*"
            index += 2
        elif text[index] == "*":
            out += "[^/]*"
            index += 1
        elif text[index] == "?":
            out += "[^/]"
            index += 1
        else:
            out += re.escape(text[index])
            index += 1
    return re.compile(f"^{out}$")


def _docker_excludes(path: str, lines: list[str]) -> bool:
    """경로나 그 위 폴더 하나가 패턴에 맞으면 빠진다(뒤의 `!` 가 되살린다)."""
    parts = path.split("/")
    candidates = ["/".join(parts[: index + 1]) for index in range(len(parts))]
    excluded = False
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        regex = _docker_pattern(line[1:] if negate else line)
        if any(regex.match(each) for each in candidates):
            excluded = not negate
    return excluded


def test_dockerignore_keeps_key_files_out_at_any_depth() -> None:
    """`.dockerignore` 의 `*.pem` · `cert/` 는 뿌리에만 걸린다 — 모듈 · 설정 폴더 안의 키 파일도
    이미지에 실리지 않아야 한다(`COPY . /project/`)."""
    lines = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    for path in (
        "cert/token.cer",
        "private.pem",
        "modules/demo/cert/k.pem",
        "config/cert/x.pem",
        "src/capa_simulation/auth/token.cer",
        "modules/demo/keys/server.key",
        "docs/a/b/c.p12",
    ):
        assert _docker_excludes(path, lines), path
    for path in ("app.py", "capa_server.py", "src/capa_simulation/auth/names.py", "modules/x.py"):
        assert not _docker_excludes(path, lines), path


def test_the_needles_do_not_match_their_own_source() -> None:
    """조각으로 만든 글자가 이 파일 원문에 그대로 있지 않다(있으면 위 시험이 스스로 걸린다)."""
    source = Path(__file__).read_bytes().lower()

    assert COMPANY_SUFFIX not in source
    assert SSO_SUFFIX not in source
    for label, (needle, _allowed) in IN_HOUSE_NEEDLES.items():
        assert needle not in source, label
    assert len(_CONTACT_LOCAL) >= 6, "연락 메일 앞자리가 짧으면 바늘이 우연히 맞는다"
    assert not PRIVATE_KEY_MARK.search(source.upper())
