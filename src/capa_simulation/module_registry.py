# Purpose: 모듈 폴더의 module.json 을 검증해 모듈마다 켜짐·꺼짐·실패와 까닭을 낸다.

"""모듈 찾기와 선언 검증(모델 2 — 2026-11-01 사용자 결정).

동료가 만든 화면은 사내 저장소의 `modules/<id>/` 에 두고 사이드바 별도 상자 「모듈」 로
띄운다. 이 모듈은 그 폴더들의 `module.json` 만 읽는다 — 모듈의 `.py` 는 import 하지 않는다(화면에
들어갈 때 Streamlit 이 그 파일을 실행한다). `scripts/` 의 모듈 점검 스크립트도 같은 검증을 쓰므로
아래 공개 이름·서명이 계약이다.

- **폴더마다 따로 본다.** 한 모듈의 어떤 예외도 다른 모듈과 앱 시작을 깨지 않는다(`scan_modules`).
- **프로세스마다 한 번 찾는다.** `discovered` 는 `lru_cache` 이고 키는 환경변수 글자와
  `settings.MODULES_DIR` 글자뿐이다 — 키를 만들 때 `resolve()`·`stat` 을 하지 않는다(Windows 는
  resolve 마다 핸들을 연다). 모듈을 넣거나 `module.json`·환경변수를 바꾸면 앱을 다시 띄워야 보인다.
- **Streamlit 캐시를 쓰지 않는다.** 아이콘 이름 검사(`streamlit.string_util`) 말고는 Streamlit
  을 부르지 않아 실행 문맥 없이 돈다.
"""

from __future__ import annotations

import functools
import json
import keyword
import os
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from capa_simulation import settings

MANIFEST_NAME: Final = "module.json"
MANIFEST_MAX_BYTES: Final = 65_536
# id 와 화면 slug 의 꼴 — 소문자로 시작하고 밑줄 하나로만 마디를 잇는다(밑줄 둘·끝 밑줄 금지).
# 키 접두가 `mod_<id>__` 라 id 에 밑줄 둘이 들면 모듈끼리 접두가 겹칠 수 있다. fullmatch 로 쓴다.
MODULE_ID_PATTERN: Final = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
MODULE_ID_LENGTH: Final = (2, 24)
PAGE_SLUG_PATTERN: Final = MODULE_ID_PATTERN
PAGE_SLUG_LENGTH: Final = (1, 24)
PAGE_FILE_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]*\.py")
MATURITY_LEVELS: Final = ("L0", "L1", "L2")
MATURITY_LABELS: Final = {"L0": "L0 Lab", "L1": "L1 연결", "L2": "L2 검증"}
# 사이드바 라벨에 「(구현중)」 을 달고 화면 탭에 「구현중」 표지를 세우는 성숙도.
IMPLEMENTING_LEVELS: Final = frozenset({"L0", "L1"})
API_MAJOR: Final = 1
API_MINOR: Final = 3
# 받는 큰 판. 큰 판을 올리면 옛 판을 남겨 두고, 압축본 판 분포에서 그 판이 0 이 된 다음 배포에 뺀다.
SUPPORTED_API_MAJORS: Final = frozenset({1})
# 모듈 뿌리를 바꾸는 환경변수. 비면 `settings.MODULES_DIR`, `off`(대소문자 무시)면 뿌리가 없다 —
# 사외와 같은 화면(상자·Admin 모듈 상태 팝오버·색인 캡션 모두 없음). 하위 프로세스까지 이어진다.
ROOT_ENV_VAR: Final = "CAPA_MODULES_ROOT"
ROOT_OFF: Final = "off"
# 운영에서 문제 모듈을 숨기는 스위치 — `*` 는 모두, `a,b` 는 그 id 들. 기록은 남는다(「꺼짐」).
DISABLED_ENV_VAR: Final = "CAPA_MODULES_DISABLED"
DATA_ROOT_ENV_VAR: Final = "CAPA_MODULES_DATA_ROOT"
# 모듈 시험(`scripts/check_module.py` 가 띄우는 감시 러너)이 켜는 표지. 켜져 있으면 창구 도우미
# (BigDataQuery 조회 · S3 올리기 · 받기 — `module_helpers`)가 밖에 닿지 않고 「쓸 수 없음」 이다 —
# 앱 관리자 PC 의 점검이 진짜 조회 · 버킷에 닿지 않게.
TEST_RUN_ENV_VAR: Final = "CAPA_MODULES_TEST_RUN"
DEFAULT_PAGE_ICON: Final = ":material/extension:"
PAGE_ICON_PATTERN: Final = re.compile(r":material/[a-z0-9_]+:")
# 화면 이름은 `st.Page`·`st.page_link` 가 Markdown 으로 그린다(`**`·`:red[]` 가 먹는다).
TITLE_FORBIDDEN_CHARS: Final = frozenset("*_`[]~\\#<>|$:")
# 그룹 상자 안 첫 링크(색인 화면)의 이름 — `app.py` 의 `GROUP_MAIN_LABEL` 과 같다(시험이 맞댄다).
GROUP_MAIN_TITLE: Final = "현황 요약"
MAX_PAGES: Final = 8
# 성숙도가 붙이는 표기 — 모듈 화면 이름에 직접 적지 않는다(`navigation.IMPLEMENTING_SUFFIX`).
IMPLEMENTING_MARK: Final = "(구현중)"

NAME_LENGTH: Final = (1, 30)
OWNER_LENGTH: Final = (1, 30)
TITLE_LENGTH: Final = (1, 24)
DESCRIPTION_MAX: Final = 120
ORDER_RANGE: Final = (0, 999)
API_MINOR_RANGE: Final = (0, 99)
DEFAULT_ORDER: Final = 100

State = Literal["on", "off", "failed"]
STATE_LABELS: Final[Mapping[str, str]] = {"on": "켜짐", "off": "꺼짐", "failed": "실패"}

_MANIFEST_FIELDS: Final = frozenset(
    {
        "id",
        "name",
        "api",
        "api_minor",
        "owner",
        "enabled",
        "maturity",
        "description",
        "order",
        "pages",
    }
)
_MANIFEST_REQUIRED: Final = ("id", "name", "api", "owner", "enabled", "maturity", "pages")
_PAGE_FIELDS: Final = frozenset({"slug", "file", "title", "icon", "order"})
_PAGE_REQUIRED: Final = ("slug", "file", "title")
_FOLDER_SEARCH_DEPTH: Final = 4


def key_prefix(module_id: str) -> str:
    """모듈 세션 키의 접두 — `mod_<id>__`(밑줄 둘). 코어 키는 `mod_` 로 시작하지 않는다."""
    return f"mod_{module_id}__"


def page_url_path(module_id: str, slug: str) -> str:
    """모듈 화면 주소 — `mod-<id>-<slug>`. 코어 주소(파일 이름)는 하이픈이 없어 겹치지 않는다."""
    return f"mod-{module_id}-{slug}"


def is_valid_module_id(value: str) -> bool:
    """id 규칙 — 꼴(`MODULE_ID_PATTERN`)·길이 2 ~ 24·파이썬 예약어 아님."""
    low, high = MODULE_ID_LENGTH
    return (
        isinstance(value, str)
        and low <= len(value) <= high
        and MODULE_ID_PATTERN.fullmatch(value) is not None
        and not keyword.iskeyword(value)
    )


class ManifestError(ValueError):
    """`module.json` 을 못 읽었거나 칸이 틀렸다. `reason`(= `str(e)`)이 보일 까닭 한 줄이다."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ModulePage:
    slug: str
    file: str
    title: str
    icon: str
    order: int


@dataclass(frozen=True)
class ModuleManifest:
    id: str
    name: str
    api: int
    owner: str
    enabled: bool
    maturity: str
    # order → slug 차례로 정렬해 둔다.
    pages: tuple[ModulePage, ...]
    description: str = ""
    order: int = DEFAULT_ORDER
    api_minor: int = 0


def _is_int(value: object) -> bool:
    # JSON 의 true/false 는 파이썬 bool 이고 bool 은 int 의 하위 형이다 — 수 칸에서 막는다.
    return isinstance(value, int) and not isinstance(value, bool)


def _text(raw: Mapping[str, Any], name: str, limits: tuple[int, int], where: str = "") -> str:
    value = raw[name]
    label = f"{where}{name}"
    if not isinstance(value, str):
        raise ManifestError(f"글자여야 하는 칸입니다: {label}")
    low, high = limits
    if len(value) > high or (low > 0 and not value.strip()):
        raise ManifestError(f"{low} ~ {high}자여야 하는 칸입니다: {label}")
    if value != value.strip():
        raise ManifestError(f"앞뒤에 공백이 있는 칸입니다: {label}")
    return value


def _number(
    raw: Mapping[str, Any], name: str, limits: tuple[int, int], default: int, where: str = ""
) -> int:
    if name not in raw:
        return default
    value = raw[name]
    low, high = limits
    if not _is_int(value) or not low <= value <= high:
        raise ManifestError(f"{low} ~ {high} 사이 정수여야 하는 칸입니다: {where}{name}")
    return int(value)


def _fields(raw: object, allowed: frozenset[str], required: tuple[str, ...], where: str) -> None:
    if not isinstance(raw, dict):
        raise ManifestError(f"JSON 객체({{…}})가 아닙니다: {where.rstrip('.') or '선언'}")
    unknown = sorted(str(name) for name in raw if name not in allowed)
    if unknown:
        raise ManifestError(f"{where}모르는 칸: {', '.join(unknown)}")
    missing = [name for name in required if name not in raw]
    if missing:
        raise ManifestError(f"{where}빠진 칸: {', '.join(missing)}")


def _page(raw: object, index: int) -> ModulePage:
    where = f"pages[{index}]."
    _fields(raw, _PAGE_FIELDS, _PAGE_REQUIRED, where)
    assert isinstance(raw, dict)
    slug = raw["slug"]
    low, high = PAGE_SLUG_LENGTH
    if (
        not isinstance(slug, str)
        or not low <= len(slug) <= high
        or PAGE_SLUG_PATTERN.fullmatch(slug) is None
    ):
        raise ManifestError(
            f"{where}slug 가 규칙(소문자·숫자·밑줄 하나, {low} ~ {high}자)에 맞지 않습니다"
        )
    file = raw["file"]
    if not isinstance(file, str) or PAGE_FILE_PATTERN.fullmatch(file) is None:
        raise ManifestError(
            f"{where}file 은 모듈 폴더 바로 아래의 소문자 .py 이름이어야 합니다(하위 폴더 안 됨)"
        )
    title = _text(raw, "title", TITLE_LENGTH, where)
    forbidden = sorted({char for char in title if char in TITLE_FORBIDDEN_CHARS})
    if forbidden:
        raise ManifestError(f"{where}title 에 Markdown 글자를 넣지 않습니다: {' '.join(forbidden)}")
    if IMPLEMENTING_MARK in title:
        raise ManifestError(
            f"{where}title 에 {IMPLEMENTING_MARK} 을 넣지 않습니다(성숙도가 붙인다)"
        )
    icon = raw.get("icon", DEFAULT_PAGE_ICON)
    if not isinstance(icon, str) or PAGE_ICON_PATTERN.fullmatch(icon) is None:
        raise ManifestError(
            f"{where}icon 은 :material/<이름>: 꼴이어야 합니다(이모지·앞뒤 공백 안 됨)"
        )
    order = _number(raw, "order", ORDER_RANGE, index * 10, where)
    return ModulePage(slug=slug, file=file, title=title, icon=icon, order=order)


def parse_manifest(raw: bytes, *, folder_name: str) -> ModuleManifest:
    """`module.json` 바이트를 읽어 칸·값·id == 폴더 이름을 본다. 틀리면 `ManifestError`.

    UTF-8 이고 BOM 이 있는 UTF-8 도 받는다(Windows PowerShell 이 붙인다). 모르는 칸이 있으면
    실패다 — `enable` 같은 오타를 잡는다.
    """
    if len(raw) > MANIFEST_MAX_BYTES:
        raise ManifestError(f"{MANIFEST_NAME} 파일이 64 KB 를 넘습니다")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ManifestError(f"{MANIFEST_NAME} 파일이 UTF-8 이 아닙니다") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ManifestError(
            f"{MANIFEST_NAME} 파일이 JSON 이 아닙니다 — {error.lineno}줄 {error.colno}칸"
        ) from None
    _fields(data, _MANIFEST_FIELDS, _MANIFEST_REQUIRED, "")
    assert isinstance(data, dict)
    module_id = data["id"]
    if not isinstance(module_id, str) or not is_valid_module_id(module_id):
        raise ManifestError(
            "id 가 규칙(소문자·숫자·밑줄 하나, 2 ~ 24자, 파이썬 예약어 아님)에 맞지 않습니다"
        )
    if module_id != folder_name:
        raise ManifestError(f"id 와 폴더 이름이 다릅니다: id {module_id} · 폴더 {folder_name}")
    name = _text(data, "name", NAME_LENGTH)
    api = data["api"]
    if not _is_int(api):
        raise ManifestError("api 는 정수여야 합니다")
    api_minor = _number(data, "api_minor", API_MINOR_RANGE, 0)
    owner = _text(data, "owner", OWNER_LENGTH)
    enabled = data["enabled"]
    if not isinstance(enabled, bool):
        raise ManifestError('enabled 는 true 또는 false 여야 합니다(글자 "true" 안 됨)')
    maturity = data["maturity"]
    if maturity not in MATURITY_LEVELS:
        raise ManifestError(f"maturity 는 {' · '.join(MATURITY_LEVELS)} 가운데 하나여야 합니다")
    description = (
        "" if "description" not in data else _text(data, "description", (0, DESCRIPTION_MAX))
    )
    order = _number(data, "order", ORDER_RANGE, DEFAULT_ORDER)
    pages_raw = data["pages"]
    if not isinstance(pages_raw, list) or not 1 <= len(pages_raw) <= MAX_PAGES:
        raise ManifestError(f"pages 는 화면 1 ~ {MAX_PAGES}개의 배열이어야 합니다")
    pages = [_page(item, index) for index, item in enumerate(pages_raw)]
    for attribute, label in (("slug", "slug"), ("file", "file"), ("title", "title")):
        values = [getattr(page, attribute) for page in pages]
        repeated = sorted({value for value in values if values.count(value) > 1})
        if repeated:
            raise ManifestError(f"모듈 안에서 겹치는 화면 {label}: {', '.join(repeated)}")
    return ModuleManifest(
        id=module_id,
        name=name,
        api=int(api),
        owner=owner,
        enabled=enabled,
        maturity=str(maturity),
        pages=tuple(sorted(pages, key=lambda page: (page.order, page.slug))),
        description=description,
        order=order,
        api_minor=api_minor,
    )


def read_manifest(folder: Path) -> ModuleManifest:
    """폴더의 `module.json` 을 읽어(크기·UTF-8/BOM) `parse_manifest` 한다. 틀리면 예외."""
    path = folder / MANIFEST_NAME
    try:
        if not path.is_file():
            raise ManifestError(f"{MANIFEST_NAME} 파일이 없습니다")
        if path.stat().st_size > MANIFEST_MAX_BYTES:
            raise ManifestError(f"{MANIFEST_NAME} 파일이 64 KB 를 넘습니다")
        raw = path.read_bytes()
    except OSError as error:
        raise ManifestError(
            f"{MANIFEST_NAME} 파일을 읽지 못했습니다 — {type(error).__name__}"
        ) from None
    return parse_manifest(raw, folder_name=folder.name)


def page_problems(folder: Path, manifest: ModuleManifest) -> list[str]:
    """화면 파일이 폴더 바로 아래의 보통 파일인지·디스크 철자(대소문자까지)·아이콘 이름을 본다.

    빈 목록이면 통과다. 철자는 `os.listdir` 에 그 이름이 그대로 있는지로 본다 — Windows 는
    `Page.py` 를 `page.py` 로도 열어 주지만 Linux CD 는 못 연다.
    """
    from streamlit.string_util import validate_icon_or_emoji

    problems: list[str] = []
    try:
        names = set(os.listdir(folder))
    except OSError as error:
        return [f"모듈 폴더를 읽지 못했습니다 — {type(error).__name__}"]
    lowered = {name.lower(): name for name in names}
    inside = folder.resolve()
    for page in manifest.pages:
        if page.file not in names:
            disk = lowered.get(page.file.lower())
            if disk is not None:
                problems.append(
                    f"화면 파일 이름의 대소문자가 다릅니다: 디스크 {disk} · 선언 {page.file}"
                )
            else:
                problems.append(f"화면 파일이 없습니다: {page.file}")
            continue
        path = folder / page.file
        if path.is_symlink():
            problems.append(f"화면 파일이 심볼릭 링크입니다: {page.file}")
            continue
        if not path.is_file():
            problems.append(f"화면 파일이 보통 파일이 아닙니다: {page.file}")
            continue
        if path.resolve().parent != inside:
            problems.append(f"화면 파일이 모듈 폴더 밖을 가리킵니다: {page.file}")
            continue
        try:
            validate_icon_or_emoji(page.icon)
        except Exception:  # Streamlit 의 아이콘 검사 오류(StreamlitAPIException) 하나다
            problems.append(f"아이콘 이름이 Material 에 없습니다: {page.icon}")
    return problems


@dataclass(frozen=True)
class TitleClash:
    """화면 이름 겹침 — 겹친 이름과 그 이름을 먼저 차지한 쪽(모듈 id, 코어면 빈 글자)."""

    title: str
    owner: str


def clash_reason(clash: TitleClash) -> str:
    """겹침 까닭 한 줄 — 상대(코어 · 차례가 앞인 모듈)를 함께 적는다."""
    holder = "코어 화면" if not clash.owner else f"차례가 앞인 모듈 {clash.owner}"
    return f"화면 이름 겹침: {clash.title} — {holder}"


@dataclass(frozen=True)
class ModuleRecord:
    folder_name: str
    path: Path
    state: State
    # 켜짐이면 빈 글자다.
    reason: str
    # 선언을 못 읽었으면 None.
    manifest: ModuleManifest | None
    # 화면 이름 겹침으로 실패했으면 그 겹침(점검이 차례가 앞인 모듈에 경고를 단다).
    clash: TitleClash | None = None


@dataclass(frozen=True)
class ModuleScan:
    # None 은 `CAPA_MODULES_ROOT=off` 다.
    root: Path | None
    root_exists: bool
    # 모듈 order → id 차례.
    records: tuple[ModuleRecord, ...]
    # 끄는 환경변수의 원문(빈 글자 가능).
    disabled_value: str
    # 환경변수에 있으나 폴더가 없는 id.
    unknown_disabled: tuple[str, ...]
    # 뿌리 목록을 못 읽은 까닭.
    root_error: str = ""

    @functools.cached_property
    def active(self) -> tuple[ModuleRecord, ...]:
        """켜진 모듈 — scan 객체마다 한 번만 계산한다."""
        return tuple(record for record in self.records if record.state == "on")


def _root_from(value: str, default: Path) -> Path | None:
    text = value.strip()
    if not text:
        return default
    if text.lower() == ROOT_OFF:
        return None
    # 글자만 다룬다(`resolve()` 하지 않는다) — 상대 경로는 지금 폴더 기준 절대 경로로.
    return Path(os.path.abspath(text))


def modules_root() -> Path | None:
    """`CAPA_MODULES_ROOT` 를 따른 모듈 뿌리. `off` 면 None, 비면 `settings.MODULES_DIR`."""
    return _root_from(os.environ.get(ROOT_ENV_VAR, ""), settings.MODULES_DIR)


def parse_disabled(value: str | None) -> tuple[bool, frozenset[str]]:
    """끄는 환경변수 값 → (모두 끔?, 끈 id 들). 쉼표로 나누고 앞뒤 공백은 버린다."""
    parts = [part.strip() for part in (value or "").split(",")]
    ids = frozenset(part for part in parts if part)
    return "*" in ids, ids - {"*"}


@dataclass
class _Draft:
    folder_name: str
    path: Path
    state: State
    reason: str
    manifest: ModuleManifest | None
    clash: TitleClash | None = None

    @property
    def sort_key(self) -> tuple[int, str]:
        order = self.manifest.order if self.manifest is not None else DEFAULT_ORDER
        return order, self.folder_name


def _examine(folder: Path, *, all_off: bool, disabled_ids: frozenset[str]) -> _Draft:
    """폴더 하나의 1 ~ 4·6·7 단계(이름 겹침 5 는 `scan_modules` 가 차례대로 본다)."""
    name = folder.name
    if not is_valid_module_id(name):
        return _Draft(name, folder, "failed", "폴더 이름이 규칙에 맞지 않음", None)
    try:
        manifest = read_manifest(folder)
    except ManifestError as error:
        return _Draft(name, folder, "failed", error.reason, None)
    if manifest.api not in SUPPORTED_API_MAJORS:
        majors = ", ".join(str(major) for major in sorted(SUPPORTED_API_MAJORS))
        return _Draft(
            name,
            folder,
            "failed",
            f"API 판 {manifest.api} — 이 코어는 {majors} 만 받는다",
            manifest,
        )
    if manifest.api_minor > API_MINOR:
        return _Draft(
            name,
            folder,
            "failed",
            f"API {manifest.api}.{manifest.api_minor} 필요 — 이 코어는 {API_MAJOR}.{API_MINOR}",
            manifest,
        )
    problems = page_problems(folder, manifest)
    if problems:
        return _Draft(name, folder, "failed", problems[0], manifest)
    if not manifest.enabled:
        return _Draft(name, folder, "off", f"{MANIFEST_NAME} enabled=false", manifest)
    if all_off or name in disabled_ids:
        return _Draft(name, folder, "off", f"환경변수 {DISABLED_ENV_VAR}", manifest)
    return _Draft(name, folder, "on", "", manifest)


def scan_modules(
    root: Path | None,
    *,
    disabled: str | None = None,
    reserved_titles: Collection[str] = (),
) -> ModuleScan:
    """모듈 뿌리 바로 아래 폴더를 하나씩 보고 상태와 까닭을 낸다. 캐시도 환경변수 읽기도 없다.

    `disabled` 는 끄는 환경변수 값 글자(None 이면 아무것도 끄지 않는다)이고, `reserved_titles`
    는 모듈 화면이 쓸 수 없는 이름(코어 화면 이름에서 「(구현중)」 을 뗀 것)이다. 화면 이름
    겹침은 켜질 모듈만 보고 **차례(order → id)가 뒤인 모듈 전체가** 실패한다 — 먼저 돌던
    모듈이라도 차례가 뒤면 빠진다. 까닭에는 상대(코어 · 차례가 앞인 모듈 id)를 적는다. 꺼질 모듈은
    겹침을 보지 않고 다른 모듈을 막지도 않는다.
    """
    disabled_value = disabled or ""
    all_off, disabled_ids = parse_disabled(disabled_value)
    if root is None or not root.is_dir():
        return ModuleScan(
            root=root,
            root_exists=False,
            records=(),
            disabled_value=disabled_value,
            unknown_disabled=tuple(sorted(disabled_ids)),
        )
    try:
        with os.scandir(root) as entries:
            folders = sorted(
                (Path(entry.path) for entry in entries if _is_module_folder(entry)),
                key=lambda path: path.name,
            )
    except OSError as error:
        return ModuleScan(
            root=root,
            root_exists=True,
            records=(),
            disabled_value=disabled_value,
            unknown_disabled=tuple(sorted(disabled_ids)),
            root_error=f"모듈 전체 폴더를 읽지 못했습니다 — {type(error).__name__}",
        )
    drafts: list[_Draft] = []
    for folder in folders:
        try:
            drafts.append(_examine(folder, all_off=all_off, disabled_ids=disabled_ids))
        except Exception as error:  # 한 모듈의 어떤 예외도 다른 모듈과 앱 시작을 깨지 않는다
            drafts.append(
                _Draft(folder.name, folder, "failed", f"검사 중 예외 {type(error).__name__}", None)
            )
    drafts.sort(key=lambda draft: draft.sort_key)
    # 이름 → 먼저 차지한 쪽(코어는 빈 글자, 모듈은 id).
    taken = dict.fromkeys((*reserved_titles, GROUP_MAIN_TITLE), "")
    for draft in drafts:
        if draft.state != "on" or draft.manifest is None:
            continue
        titles = [page.title for page in draft.manifest.pages]
        title = next((title for title in titles if title in taken), None)
        if title is not None:
            draft.clash = TitleClash(title, taken[title])
            draft.state, draft.reason = "failed", clash_reason(draft.clash)
            continue
        taken.update(dict.fromkeys(titles, draft.folder_name))
    names = {draft.folder_name for draft in drafts}
    return ModuleScan(
        root=root,
        root_exists=True,
        records=tuple(
            ModuleRecord(
                draft.folder_name,
                draft.path,
                draft.state,
                draft.reason,
                draft.manifest,
                draft.clash,
            )
            for draft in drafts
        ),
        disabled_value=disabled_value,
        unknown_disabled=tuple(sorted(disabled_ids - names)),
    )


def _is_module_folder(entry: os.DirEntry[str]) -> bool:
    """`.`·`_` 로 시작하는 이름(`__pycache__` 등)과 파일(`README.md` 등)은 모듈이 아니다."""
    if entry.name.startswith((".", "_")):
        return False
    try:
        return entry.is_dir()
    except OSError:
        return False


@functools.lru_cache(maxsize=8)
def _discovered(
    root_value: str, modules_dir: str, disabled: str, reserved_titles: tuple[str, ...]
) -> ModuleScan:
    return scan_modules(
        _root_from(root_value, Path(modules_dir)),
        disabled=disabled,
        reserved_titles=reserved_titles,
    )


def discovered(*, reserved_titles: tuple[str, ...] = ()) -> ModuleScan:
    """프로세스 캐시를 둔 `scan_modules` — 키는 뿌리·끄는 환경변수 글자와 `settings.MODULES_DIR`.

    모듈이 없으면 첫 호출이 `is_dir()` 한 번만 하고, 그 뒤 회차는 캐시 적중뿐이다.
    """
    return _discovered(
        os.environ.get(ROOT_ENV_VAR, ""),
        os.fspath(settings.MODULES_DIR),
        os.environ.get(DISABLED_ENV_VAR, ""),
        tuple(reserved_titles),
    )


def clear_discovery_cache() -> None:
    """찾기 캐시와 선언 캐시를 비운다(시험용)."""
    _discovered.cache_clear()
    _manifest_at.cache_clear()


def module_folder_for(file: str | os.PathLike[str]) -> Path:
    """파일 자리에서 위로 올라가며 `module.json` 이 있는 첫 폴더(최대 4단계). 없으면 예외."""
    folder = Path(os.path.abspath(file)).parent
    for _ in range(_FOLDER_SEARCH_DEPTH):
        if (folder / MANIFEST_NAME).is_file():
            return folder
        if folder.parent == folder:
            break
        folder = folder.parent
    raise ManifestError(
        f"이 파일 위 {_FOLDER_SEARCH_DEPTH}단계 안에 {MANIFEST_NAME} 파일이 없습니다"
    )


@functools.lru_cache(maxsize=64)
def _manifest_at(path: str, mtime_ns: int, size: int) -> ModuleManifest:
    return read_manifest(Path(path).parent)


def cached_manifest(folder: Path) -> ModuleManifest:
    """(경로, mtime_ns, 크기) 키로 캐시한 `read_manifest` — 회차마다 stat 한 번이다."""
    path = folder / MANIFEST_NAME
    try:
        stat = path.stat()
    except OSError:
        raise ManifestError(f"{MANIFEST_NAME} 파일이 없습니다") from None
    return _manifest_at(os.fspath(path), stat.st_mtime_ns, stat.st_size)


def data_root() -> Path:
    """모듈 데이터 뿌리 — `CAPA_MODULES_DATA_ROOT` 가 있으면 그것, 없으면 설정의 자리."""
    value = os.environ.get(DATA_ROOT_ENV_VAR, "").strip()
    return Path(value) if value else settings.MODULES_DATA_DIR
