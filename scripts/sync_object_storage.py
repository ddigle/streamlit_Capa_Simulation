# Purpose: 오브젝트 스토리지의 DuckDB 스냅샷을 진단·초기화하고 필요할 때 수동으로 받거나 올린다.

"""사내 S3 호환 스토리지와 DuckDB 파일을 주고받는 운영 도구.

판정 로직은 한 줄도 여기 두지 않는다. 키 계약과 판정은 `services/object_storage_manifest.py`,
유실을 막는 차례는 `object_sync_engine.py`, 스냅샷 만들기·설치는 `persistence/snapshot_export.py`,
`aws` 호출은 `io/object_storage.py` 가 맡는다. 여기서는 인자를 읽고 결과를 찍기만 한다.

**두 DB 는 한 쌍이다.** `init` · `pull` · `push` · `resolve` · `adopt` 는 늘 둘을 함께 다룬다.
`--dataset` 은 `status` · `doctor` 표시 거르기로만 남았다.

**정본의 쓰는 쪽은 운영 앱 하나다.** `init` 이 그 PC 를 넘긴 쪽으로 표시하고(`handed_over_utc`),
운영 앱이 포인터를 낸 뒤(`origin` 이 `app` · `boot` · `rollback`)에는 `push` · `resolve --keep mine`
· `adopt --source local` 을 거절한다 — `--override-writer` 만 통과한다. 사내 PC 가 읽을 때는
`fetch-copy` 로 사본을 받는다.

**앱을 끈 상태에서 쓴다.** DuckDB 파일은 프로세스 배타 잠금이라 앱이 떠 있으면 설치가 실패한다.
`status` · `generations` · `doctor` · `probe` · `fetch-copy` · `rollback` · `prune` · `keep` ·
`unkeep` 은 앱이 떠 있어도 안전하다. `boot-pull` 은 컨테이너 시작 스크립트가 앱을 띄우기 전에
부르고, 값 없는 결과 한 줄(JSON)을 찍는다. 확인이 실제 내려받기로 넘어가면 `--download-mark` 로
받은 자리에 빈 표지 파일을 남긴다 — 시작 임시 화면이 그 표지를 보고서야 「n번째 받는 중」 을
보인다.

**주소 · 버킷 · 프로필은 환경변수(또는 인자)로만 받는다** — 사내 값이라 저장소에 기본값이 없다.
비었으면 `aws` 를 부르기 전에 넣을 환경변수 이름을 대고 멈춘다(`docs/objectstore_setup.md` 6장).
꺾쇠 · 공백 · 따옴표가 든 값(자리표째 넣었거나 다음 줄까지 붙여 넣은 값)도 `aws` 를 부르기 전에
그 값이 온 자리(인자 이름 또는 환경변수 이름)만 대고 멈춘다 — 값은 찍지 않는다.

**끝에 「전송용 요약」 한 줄을 찍는다**(`profile` · `boot-pull` 밖). 사람이 리뷰에 옮기는 줄이라
갈래 낱말 · 세대 번호 · 크기 · 초 · 종료 코드만 싣는다 — 주소 · 버킷 · 프로필 · 폴더 · 계정 ·
서버 글은 싣지 않는다.

**그 위의 출력도 주소 · 버킷 · 프로필 · 작성자를 가린다**(`profile` 밖 — 셸에 붙여 넣을 블록이라
값이 든다). `doctor` 의 값 줄은 버킷을 앞 두 글자 … 뒤 두 글자 · 글자 수로, 주소 · 프로필은
있음/없음으로 찍고, 진단 글(오류 첫 줄 · 「실행한 명령」 — `io/object_storage.py` 가 원격 진단용으로
값째 만든다) 안의 값은 받아 찍는 자리에서 `<주소>` · `<버킷>` · `<프로필>` 로 바꾼다. 세대 줄의
작성자는 `<작성자>` 다. 원값을 보는 옵션은 없다 — 값은 C-DEP 환경변수 표와 사용자 창의 변수에만
있다. 내 PC 경로(받은 폴더 · 백업 · 「로컬 DB 가 없습니다」 · 진단 글의 파일 인자 · `probe --write`
의 기록 파일)의 홈 폴더 앞부분은 `%USERPROFILE%` 로 찍는다(리뷰에 옮길 때 계정 이름이 나가지 않게
— 여닫는 경로 값은 그대로다). 표준 오류도 같다 — 도는 동안 어느 모듈의 로거 글이든
(`_masked_logging`), 잡지 못한 예외의 트레이스백도(`_masked_excepthook`) 같은 가림을 지난다.
불러오는 동안 Streamlit 캐시 래퍼가 찍는 「No runtime found」 경고(수십 줄)만 끈다 — 결과와
상관없는 줄이고, 끄는 것은 그 불러오기 동안뿐이다.

**세대 지킴**(`keep` · `unkeep`)은 버킷에 기한 있는 표지(`generations/keep/`)를 두거나 지운다.
정리가 기한까지 그 세대와 두 멤버를 비켜 간다. 포인터는 그대로라 표지를 모르는 코드도 같은
버킷을 읽고, 기한이 지나면 표지는 저절로 아무것도 붙잡지 않는다. `generations` 는 지킨 세대에
그 기한을 단다.

**정본을 바꾸는 손 동작은 감사 조각을 남긴다.** `rollback` · `init` · `fetch-copy` · `prune` ·
`keep` · `unkeep` 은 끝에 그 버킷의 `audit/v1/tool/…` 에 한 줄짜리 조각을 새로 올린다
(`audit/tool.py` — 행위자는 OS 사용자, 미검증). `--dry-run` · `--yes` 없이 건너뛴 명령 · 빈
설정 · 할 일이 없던 명령은 남기지 않는다. 올리지 못해도 명령의 종료 코드는 그대로다.
`audit-list` 는 그 날짜 · 달의 조각 · 일별 파일 수만 찍는다(값 없음).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
import traceback
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import TracebackType
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capa_simulation import object_sync_engine as engine  # noqa: E402
from capa_simulation import sync_boot  # noqa: E402
from capa_simulation.audit import layout as audit_layout  # noqa: E402
from capa_simulation.audit.tool import upload_tool_piece  # noqa: E402
from capa_simulation.io import object_storage  # noqa: E402
from capa_simulation.io.object_storage import (  # noqa: E402
    ObjectStorageClient,
    ObjectStorageError,
    StorageSettings,
    StorageSettingsError,
)
from capa_simulation.persistence import snapshot_export, sync_state  # noqa: E402
from capa_simulation.services import object_storage_manifest as manifest  # noqa: E402
from capa_simulation.services.korean_particle import (  # noqa: E402
    with_direction_particle,
    with_subject_particle,
)
from capa_simulation.services.object_storage_manifest import (  # noqa: E402
    DATASET_LABELS,
    FAILURE_CONFIG,
    FAILURE_FORKED,
    FAILURE_LABELS,
    FAILURE_OTHER,
    DatasetName,
    PullDecision,
    PushDecision,
)
from capa_simulation.settings import (  # noqa: E402
    DUCKDB_PATH,
    EQUIPMENT_DUCKDB_PATH,
)

# `page_bootstrap` 은 Streamlit 캐시 래퍼 모듈을 함께 불러온다. 실행 문맥 밖이라 래퍼마다 「No
# runtime found」 경고가 표준 오류에 한 줄씩(수십 줄) 결과 줄보다 먼저 찍혀 사용자 창을 덮으므로
# 불러오는 동안만 끈다. 끝나면 불러오기 전 단계로 되돌린다 — 명령이 도는 동안의 로거 글
# (`_masked_logging`)과 오류는 그대로 표준 오류에 닿는다.
_LOGGING_DISABLED = logging.root.manager.disable
logging.disable(max(_LOGGING_DISABLED, logging.WARNING))
try:
    from capa_simulation.page_bootstrap import (  # noqa: E402
        BOOTSTRAP_ERRORS,
        bootstrap_error_message,
    )
finally:
    logging.disable(_LOGGING_DISABLED)

DATASET_PATHS: dict[DatasetName, Path] = {
    "simulation": DUCKDB_PATH,
    "equipment": EQUIPMENT_DUCKDB_PATH,
}
MIB = 1024 * 1024
# 감사 조각을 남기는 명령 → 사건. 명령이 채우는 상세(`_AUDIT_DETAIL`)와 건너뜀 표지를
# main 이 읽는다.
AUDITED_COMMANDS: dict[str, str] = {
    "rollback": "admin_sync_rollback",
    "init": "admin_sync_init",
    "fetch-copy": "admin_fetch_copy",
    "prune": "admin_sync_prune",
    "keep": "admin_sync_keep",
    "unkeep": "admin_sync_unkeep",
}
_AUDIT_DETAIL: dict[str, object] = {}
_AUDIT_SKIP = "skip"

# 버킷 · 주소 · 프로필에 들 수 없는 글자 — 꺾쇠 자리표(`"<…>"`)째 넣은 값, 따옴표째 붙인 값,
# 묻는 줄이 뒤에 붙은 명령 줄을 값으로 먹은 경우(공백)가 여기에 걸린다.
_MALFORMED_VALUE = re.compile(r"[<>\"'\u2018\u2019\u201c\u201d\s]")
SETTINGS_MALFORMED = "설정 값 꼴 틀림"
# (설정 칸, 인자, 환경변수) — 멈출 때 값이 온 자리를 이 이름으로 댄다.
_SETTING_SOURCES = (
    ("endpoint_url", "--endpoint-url", object_storage.ENDPOINT_ENV),
    ("bucket", "--bucket", object_storage.BUCKET_ENV),
    ("profile", "--profile", object_storage.PROFILE_ENV),
)

SUMMARY_LABEL = "전송용 요약:"
# 요약 줄을 찍지 않는 하위 명령 — `profile` 출력은 셸에 그대로 붙여 넣고, `boot-pull` 의 끝줄은 시작
# 스크립트가 JSON 으로 읽는다.
NO_SUMMARY = frozenset({"profile", "boot-pull"})
# 스크립트가 받지 않은 요청(없는 세대 · 운영 DB 자리 · 빈 원격 등) — 엔진의 `ValueError`.
STOP_REQUEST = "요청 거절"
_CLI_VERSION = re.compile(r"aws-cli/[0-9][0-9.]*")


@dataclass
class _Summary:
    """전송용 요약 한 줄의 칸. 하위 명령이 갈래 낱말과 수만 채운다."""

    facts: list[str] = field(default_factory=list)
    stop: str | None = None

    def reset(self) -> None:
        self.facts.clear()
        self.stop = None


_SUMMARY = _Summary()


def _fact(text: str) -> None:
    _SUMMARY.facts.append(text)


def _stopped(kind: str) -> None:
    """멈춘 갈래 — 처음 것만 남긴다(뒤의 것은 그 갈래가 낳은 것이다)."""
    if _SUMMARY.stop is None:
        _SUMMARY.stop = kind


def failure_kind(error: BaseException) -> str:
    """멈춘 갈래 낱말. 설정을 못 읽은 것은 그 꼬리표(값 없는 고정 낱말), 그 밖은 실패 갈래 낱말."""
    if isinstance(error, StorageSettingsError):
        return error.label
    return FAILURE_LABELS[object_storage.classify_failure(error)]


def summary_line(command: str, code: int) -> str:
    """`전송용 요약: <명령> 통과|멈춤 <갈래>; 종료 <n>; <칸>…` — 값 없는 한 줄."""
    state = "통과" if code == 0 else f"멈춤 {_SUMMARY.stop or FAILURE_LABELS[FAILURE_OTHER]}"
    cells = [f"{command} {state}", f"종료 {code}", *_SUMMARY.facts]
    return f"{SUMMARY_LABEL} {'; '.join(cells)}"


def _seq_fact(label: str, seq: int | None, *, none: str) -> None:
    _fact(f"{label} {none if seq is None else f'seq {seq}'}")


def _cli_label(version: str) -> str:
    """aws 판만 — 판 글의 나머지(파이썬 · OS 꼬리)는 싣지 않는다."""
    found = _CLI_VERSION.search(version)
    return "판 모름" if found is None else found.group(0)


# --------------------------------------------------------------------------- 가림
ENDPOINT_TAG = "<주소>"
BUCKET_TAG = "<버킷>"
PROFILE_TAG = "<프로필>"
AUTHOR_TAG = "<작성자>"
# 내 PC 경로 앞부분(`C:\Users\<계정>`) — 셸 변수 꼴로 둔다(읽는 사람이 어디인지는 안다).
HOME_TAG = "%USERPROFILE%"
# 버킷을 이 글자 수 이하면 글자 수만 찍는다 — 앞 두 글자와 뒤 두 글자가 값 전부가 된다.
SHORT_BUCKET = 4


@dataclass
class _Redaction:
    """이 실행이 쓰는 주소 · 버킷 · 프로필을 이름표로 바꾸는 한 벌. 긴 꼴부터 맞춰 겹친 값도 가린다.

    대소문자를 가리지 않는다 — 서버 글은 호스트를 소문자로 찍기도 한다.
    """

    pattern: re.Pattern[str] | None = None
    tags: list[str] = field(default_factory=list)

    def load(self, settings: StorageSettings) -> None:
        pairs: dict[str, str] = {}
        for value, tag in (
            *((form, ENDPOINT_TAG) for form in endpoint_forms(settings.endpoint_url)),
            (settings.bucket, BUCKET_TAG),
            (settings.profile, PROFILE_TAG),
        ):
            if value:
                pairs.setdefault(value, tag)
        ordered = sorted(pairs.items(), key=lambda pair: len(pair[0]), reverse=True)
        self.tags = [tag for _, tag in ordered]
        self.pattern = (
            re.compile("|".join(f"({re.escape(value)})" for value, _ in ordered), re.IGNORECASE)
            if ordered
            else None
        )

    def clear(self) -> None:
        self.pattern = None
        self.tags = []

    def apply(self, text: str) -> str:
        if self.pattern is None:
            return text
        tags = self.tags
        return self.pattern.sub(lambda found: tags[(found.lastindex or 1) - 1], text)


_REDACTION = _Redaction()


def endpoint_forms(endpoint: str) -> tuple[str, ...]:
    """주소가 글에 나오는 꼴 — 넣은 그대로 · 끝 `/` 를 뗀 것 · `호스트:포트` · 호스트."""
    forms = [endpoint, endpoint.rstrip("/")]
    try:
        parts = urlsplit(endpoint if "//" in endpoint else f"//{endpoint}")
        forms += [parts.netloc, parts.hostname or ""]
    except ValueError:
        pass
    return tuple(dict.fromkeys(form for form in forms if form))


# 홈 폴더 경로 뒤에 올 수 있는 글자 — 이 앞에서 끝나야 그 폴더다(`…\ab` 가 `…\abc` 를 먹지 않게).
_PATH_END = r"(?=$|[\\/'\"\s)])"
# 홈 값이 무엇이든 남는 꼴 — 짧은 8.3 이름(`ABCDEF~1`) · `/` 구분자 · 대소문자 · 다른 계정의 홈 ·
# 겹 구분자(오류 글이 경로를 `repr` 로 실어 `\\` 가 둘씩 선다). 계정 칸은 다음 구분자 · 따옴표 · 줄
# 끝 · 닫는 괄호 앞까지다(이름에 빈칸이 들어도 다 가린다). 드라이브 글자 앞이 글자 · 숫자면 주소의
# `scheme://` 라 건드리지 않는다.
_USERS_FOLDER = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]+Users[\\/]+[^\\/'\"\r\n)]+", re.IGNORECASE
)


def _home_forms() -> tuple[str, ...]:
    r"""`USERPROFILE` 이 글에 나오는 꼴 — 넣은 그대로 · `/` 구분자 · `\` 구분자 · `\\` 겹 구분자
    (오류 글의 `repr`, 끝 구분자는 뗀다). 값이 없거나 드라이브 뿌리 같은 꼴(구분자가 없음)이면
    비운다."""
    home = os.environ.get("USERPROFILE", "").strip().rstrip("\\/")
    if not re.search(r"[\\/]", home):
        return ()
    back = home.replace("/", "\\")
    forms = (home, home.replace("\\", "/"), back, back.replace("\\", "\\\\"))
    return tuple(sorted(dict.fromkeys(forms), key=len, reverse=True))


def mask_home(text: str) -> str:
    r"""글 안의 내 PC 홈 폴더(`C:\Users\<계정>`)를 `%USERPROFILE%` 로 — 그 뒤의 경로는 그대로 둔다.

    출력에만 쓴다 — 실제로 여닫는 경로 값은 바꾸지 않는다. 설정을 못 읽은 실행에서도 가린다(주소 ·
    버킷 · 프로필 가림과 따로)."""
    for form in _home_forms():
        pattern = re.compile(re.escape(form) + _PATH_END, re.IGNORECASE)
        text = pattern.sub(lambda _found: HOME_TAG, text)
    return _USERS_FOLDER.sub(lambda _found: HOME_TAG, text)


def masked(text: str) -> str:
    """받아 찍는 글 안의 사내 값 · 내 PC 홈 폴더를 이름표로 — 진단 글 · 엔진이 감싼 실패 글이
    지난다."""
    return mask_home(_REDACTION.apply(text))


def _stop_line(error: BaseException) -> str:
    return f"[중단] {masked(str(error))}"


class _MaskedLogHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """로거 글을 표준 오류로 — 형식을 마친 글(트레이스백까지)이 `masked()` 를 지난다."""

    def format(self, record: logging.LogRecord) -> str:
        return masked(super().format(record))


@contextmanager
def _masked_logging() -> Iterator[None]:
    """명령이 도는 동안 뿌리 로거에 가리는 처리기를 단다. 이 프로세스의 다른 모듈(감사 조각 ·
    사이드카 · 엔진)의 로거 글도 뿌리까지 올라오므로 이 길을 지난다 — 처리기가 없으면 Python 이
    가림 없이 표준 오류에 찍는다(`logging.lastResort`)."""
    handler = _MaskedLogHandler(sys.stderr)
    handler.setLevel(logging.WARNING)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield
    finally:
        root.removeHandler(handler)


def _masked_excepthook(
    kind: type[BaseException], error: BaseException, trace: TracebackType | None
) -> None:
    """잡지 못한 예외(코드 결함)도 트레이스백 · 종료 1 그대로 끝나되 그 글은 가림을 지난다."""
    sys.stderr.write(masked("".join(traceback.format_exception(kind, error, trace))))


def _load_redaction(args: argparse.Namespace) -> None:
    """가릴 값을 이 실행이 쓰는 설정에서 채운다. 설정을 못 읽으면 까닭이 무엇이든 비우고 넘긴다 —
    명령이 같은 읽기를 다시 해 제 자리(`[중단]` · 전송용 요약 · 시작 줄)에서 멈추고, 그 글에는
    값이 없다. 여기서 새면 그 자리를 건너뛰고 트레이스백으로 끝난다(UTF-8 이 아닌 설정 파일 등)."""
    _REDACTION.clear()
    try:
        _REDACTION.load(build_settings(args))
    except BOOTSTRAP_ERRORS:
        return


def presence(value: str) -> str:
    return "있음" if value else "없음"


def bucket_shape(bucket: str) -> str:
    """버킷 대보기 꼴 — 앞 두 글자 … 뒤 두 글자 · 글자 수(C-DEP 표 값과 사람이 맞대 본다)."""
    if not bucket:
        return "없음"
    if len(bucket) <= SHORT_BUCKET:
        return f"{len(bucket)}자"
    return f"{bucket[:2]} … {bucket[-2:]} · {len(bucket)}자"


# --------------------------------------------------------------------------- 인자
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", help="AWS CLI 프로필. 생략하면 환경변수 CAPA_S3_PROFILE.")
    parser.add_argument("--bucket", help="버킷 이름. 생략하면 환경변수 CAPA_S3_BUCKET.")
    parser.add_argument(
        "--endpoint-url", help="엔드포인트. 생략하면 환경변수 CAPA_S3_ENDPOINT_URL."
    )
    parser.add_argument(
        "--dataset",
        choices=("simulation", "equipment", "all"),
        default="all",
        help="status·doctor 에 보일 DB. 기본 all.",
    )
    parser.add_argument("--dry-run", action="store_true", help="실제로 올리거나 받지 않는다.")
    parser.add_argument(
        "--override-writer",
        action="store_true",
        help="정본을 넘긴 뒤에도 쓰기 명령을 통과시킨다. 운영 앱의 저장을 덮을 수 있다.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("profile", help="사내 PC 에 넣을 aws configure 블록을 출력한다.")
    sub.add_parser("doctor", help="설정·연결·권한을 점검한다.")

    probe = sub.add_parser("probe", help="스토리지가 실제로 무엇을 지원하는지 실측한다.")
    probe.add_argument("--write", type=Path, help="결과를 이 경로에 JSON 으로 쓴다.")

    init = sub.add_parser("init", help="빈 저장소에 두 DB 의 첫 세대를 올리고 정본을 넘긴다.")
    init.add_argument("--note", default="최초 이관", help="포인터에 남길 메모.")
    init.add_argument(
        "--keep-writer",
        action="store_true",
        help="이 PC 를 넘긴 쪽으로 표시하지 않는다(개발 버킷 시험용).",
    )

    sub.add_parser("status", help="원격 세대와 로컬 상태를 비교해 보여 준다.")

    pull = sub.add_parser("pull", help="원격 최신 세대를 내려받아 설치한다.")
    pull.add_argument("--force", action="store_true", help="세대를 모르는 로컬 DB 도 덮는다.")

    push = sub.add_parser("push", help="로컬 변경을 새 세대로 올린다.")
    push.add_argument("--note", default="수동 저장", help="포인터에 남길 메모.")

    resolve = sub.add_parser("resolve", help="게시하지 못한 세대를 해소한다.")
    resolve.add_argument(
        "--keep",
        choices=("mine", "remote"),
        required=True,
        help="mine 이면 내 세대를 새 세대로 올리고, remote 면 내 것을 버리고 원격을 받는다.",
    )

    adopt = sub.add_parser("adopt", help="세대를 모르는 로컬 DB 의 기준을 정한다.")
    adopt.add_argument("--source", choices=("local", "remote"), required=True)

    prune = sub.add_parser("prune", help="오래된 세대를 지운다.")
    prune.add_argument(
        "--keep-last",
        type=int,
        default=manifest.KEEP_LAST_GENERATIONS,
        help="남길 최신 세대 수(멤버 쌍이 다른 세대로 센다).",
    )
    prune.add_argument(
        "--keep-days",
        type=int,
        default=manifest.KEEP_DAYS,
        help="HEAD 나이 기준으로 남길 일수.",
    )
    prune.add_argument(
        "--include-orphans",
        action="store_true",
        help="기준 일수를 넘긴 고아 스냅샷도 후보에 넣는다. 경합에서 진 데이터라 기본은 보호한다.",
    )
    prune.add_argument("--yes", action="store_true", help="확인 없이 실제로 지운다.")

    fetch = sub.add_parser("fetch-copy", help="세대 하나를 사본 폴더로 받는다(앱이 떠 있어도 됨).")
    fetch.add_argument("--to", type=Path, required=True, help="저장소 밖 폴더.")
    fetch.add_argument("--seq", type=int, help="받을 세대. 생략하면 HEAD.")
    fetch.add_argument("--token", help="같은 세대에 포인터가 둘일 때 고를 키 꼬리 8자리.")

    rollback = sub.add_parser("rollback", help="앞 세대의 멤버로 새 HEAD 를 낸다(지우지 않는다).")
    rollback.add_argument("--to", type=int, required=True, help="이어 갈 세대.")
    rollback.add_argument("--token", help="같은 세대에 포인터가 둘일 때 고를 키 꼬리 8자리.")
    rollback.add_argument("--note", default="세대 되돌림", help="포인터에 남길 메모.")
    rollback.add_argument("--yes", action="store_true", help="확인 없이 실제로 낸다.")

    generations = sub.add_parser("generations", help="되돌릴 세대를 고를 목록을 찍는다.")
    generations.add_argument("--limit", type=int, default=30, help="찍을 세대 수. 기본 30.")

    keep = sub.add_parser("keep", help="세대 하나를 기한까지 정리에서 지킨다(표지만 둔다).")
    target = keep.add_mutually_exclusive_group(required=True)
    target.add_argument("--head", action="store_true", help="지금 HEAD 세대를 지킨다.")
    target.add_argument("--seq", type=int, help="지킬 세대.")
    keep.add_argument(
        "--days",
        type=int,
        default=engine.PIN_DAYS_DEFAULT,
        help=f"지킬 일수({engine.PIN_DAYS_MIN} ~ {engine.PIN_DAYS_MAX}). "
        f"기본 {engine.PIN_DAYS_DEFAULT}.",
    )
    keep.add_argument("--note", default="세대 지킴", help="표지에 남길 메모.")

    unkeep = sub.add_parser("unkeep", help="세대의 지킴 표지를 지운다(세대는 지우지 않는다).")
    unkeep.add_argument("--seq", type=int, required=True, help="표지를 풀 세대.")
    unkeep.add_argument("--yes", action="store_true", help="확인 없이 실제로 푼다.")

    boot_pull = sub.add_parser("boot-pull", help="컨테이너 시작의 받기 — 결과 한 줄을 찍는다.")
    boot_pull.add_argument(
        "--download-mark",
        type=Path,
        help="실제 내려받기로 넘어가면 남길 표지 파일(시작 스크립트가 시도마다 준다).",
    )
    audit_list = sub.add_parser(
        "audit-list", help="감사 기록 조각 · 일별 파일 수를 날짜(또는 달)로 센다(값 없음)."
    )
    audit_list.add_argument("--date", help="UTC 날짜 YYYY-MM-DD 또는 today")
    audit_list.add_argument("--month", help="UTC 달 YYYY-MM")
    return parser.parse_args(argv)


def build_settings(args: argparse.Namespace) -> StorageSettings:
    """인자 > 환경변수 한 벌. 꼴이 틀린 값이 있으면 `aws` 를 부르기 전에 그 자리 이름만 대고 멈춘다.

    `boot-pull` 은 C-DEP 환경변수 표의 값이라 손으로 친 줄이 아니다 — 가르지 않고 지금처럼 `aws` 가
    가린다(시작 스크립트가 읽는 한 줄의 갈래가 바뀌지 않게).
    """
    base = object_storage.load_settings()
    settings = StorageSettings(
        mode=base.mode,
        endpoint_url=args.endpoint_url or base.endpoint_url,
        bucket=args.bucket or base.bucket,
        profile=args.profile or base.profile,
        region=base.region,
        capabilities=base.capabilities,
    )
    malformed = () if args.command == "boot-pull" else malformed_sources(args, settings)
    if malformed:
        raise StorageSettingsError(
            "꺾쇠 · 공백 · 따옴표가 든 값이 있습니다 — "
            + " · ".join(malformed)
            + ". aws 를 부르지 않았습니다(값은 찍지 않습니다). 그 값을 넣는 줄부터 다시 칩니다.",
            label=SETTINGS_MALFORMED,
        )
    return settings


def malformed_sources(args: argparse.Namespace, settings: StorageSettings) -> tuple[str, ...]:
    """꺾쇠 · 공백 · 따옴표가 든 값이 온 자리 — 인자로 줬으면 인자 이름, 아니면 환경변수 이름."""
    return tuple(
        flag if getattr(args, field) else environment
        for field, flag, environment in _SETTING_SOURCES
        if _MALFORMED_VALUE.search(getattr(settings, field))
    )


def build_client(args: argparse.Namespace) -> ObjectStorageClient:
    """빈 사내 값이 있으면 여기서 멈춘다 — 스냅샷 내보내기 같은 긴 일을 하기 전에."""
    settings = build_settings(args)
    object_storage.require_settings(settings)
    return ObjectStorageClient(settings=settings)


def _missing_line(names: tuple[str, ...]) -> str:
    """빈 사내 값 — 넣을 이름 한 줄과, 이 스크립트에서만 되는 인자 길 한 줄."""
    return (
        f"[중단] {object_storage.missing_settings_message(names)}\n"
        "        사내 PC 는 사용자 환경변수로 넣는다(docs/objectstore_setup.md 6장 0단계) — "
        "--endpoint-url · --bucket · --profile 인자로도 준다."
    )


def datasets(args: argparse.Namespace) -> list[DatasetName]:
    return list(DATASET_PATHS) if args.dataset == "all" else [args.dataset]


def sync_paths() -> engine.SyncPaths:
    return engine.SyncPaths(DATASET_PATHS)


# --------------------------------------------------------------------------- 조회 도우미
def local_state(dataset: DatasetName) -> sync_state.SyncState | None:
    return sync_state.read_state(DATASET_PATHS[dataset])


def _head_pointer(client: ObjectStorageClient) -> manifest.Pointer | None:
    remote = engine.read_remote_head(client)
    return None if remote.head_key is None else engine.read_pointer(client, remote.head_key)


def _writer_refusal(args: argparse.Namespace, client: ObjectStorageClient, action: str) -> bool:
    """정본을 넘긴 뒤의 쓰기를 거절한다. `--override-writer` 만 통과한다."""
    if args.override_writer:
        print("[주의] --override-writer — 운영 앱의 저장을 덮을 수 있습니다.")
        return False
    handed_over = sync_state.read_generation(sync_paths().generation).handed_over_utc
    if handed_over is not None:
        print(f"[중단] 이 PC 는 {handed_over} 에 정본을 넘겼습니다 — {action} 하지 않습니다.")
        _stopped("정본 넘김")
        return True
    head = _head_pointer(client)
    if manifest.writer_taken_over(head):
        assert head is not None
        print(f"[중단] 운영 앱이 정본을 쓰고 있습니다(seq {head.seq}) — {action} 하지 않습니다.")
        _stopped("정본 넘김")
        return True
    return False


# --------------------------------------------------------------------------- 명령
def command_profile(args: argparse.Namespace) -> int:
    """사내 PC 에서 한 번 실행할 설정 블록. 손으로 옮겨 적지 않게 설정에서 만든다.

    주소 · 프로필 이름은 사내 값이라 환경변수(또는 인자)에서 온다 — 비었으면 블록을 찍지 않는다.
    """
    settings = build_settings(args)
    missing = object_storage.missing_environment(settings, bucket=False)
    if missing:
        print(_missing_line(missing))
        _stopped(object_storage.SETTINGS_MISSING)
        return 1
    print("# 사내 PC 에서 한 번만 실행합니다.")
    print("# 마지막 줄이 키 둘을 차례로 묻습니다 — 묻는 자리에 붙여 넣으세요.")
    print("# 네임스페이스는 프로필(자격증명)에 매여 있어 명령 인자로 넘기지 않습니다.")
    print("# 체크섬 두 줄은 AWS CLI 2.23+ 와 ECS 의 비호환 우회입니다(Dell KB 000299507).")
    print(f'$PROF = "{settings.profile}"')
    for name, value in object_storage.profile_settings(settings):
        print(f"aws configure set {name} {value} --profile $PROF")
    # 묻는 줄은 맨 끝 한 줄이다 — 블록째 붙여 넣으면 묻는 자리가 그 뒤에 붙은 줄을 값으로 먹는다.
    print(
        'aws configure set aws_access_key_id (Read-Host "액세스 키") --profile $PROF; '
        'aws configure set aws_secret_access_key (Read-Host "비밀 키") --profile $PROF'
    )
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    settings = build_settings(args)
    print(f"모드          : {settings.mode}")
    print(f"엔드포인트    : {presence(settings.endpoint_url)}")
    print(f"버킷          : {bucket_shape(settings.bucket)}")
    print(f"프로필        : {presence(settings.profile)}")
    print("네임스페이스  : 프로필에 매여 있음(명령 인자가 아님)")
    missing = object_storage.missing_environment(settings)
    if missing:
        print(_missing_line(missing))
        _stopped(object_storage.SETTINGS_MISSING)
        return 1
    # 클라이언트는 다른 명령과 똑같이 `build_client` 를 지난다. 여기서만 따로 만들면
    # 실행기를 갈아끼운 테스트가 이 경로만 못 덮는다.
    client = build_client(args)
    try:
        version = client.cli_version()
        print(f"CLI           : {version}")
        _fact(f"CLI {_cli_label(version)}")
        print(f"주소 스타일   : {client.check_addressing_style()}")
        head = _head_pointer(client)
    except ObjectStorageError as exc:
        print(_stop_line(exc))
        _stopped(failure_kind(exc))
        return 1
    print(f"원격 세대     : {'비어 있음' if head is None else _generation_line(head)}")
    _seq_fact("원격", None if head is None else head.seq, none="비어 있음")
    base = sync_state.read_generation(sync_paths().generation).base_seq
    print(f"로컬 세대     : {'세대 미상' if base is None else f'seq {base}'}")
    _seq_fact("로컬", base, none="세대 미상")
    for dataset in datasets(args):
        changed = "변경 있음" if sync_state.treat_as_dirty(DATASET_PATHS[dataset]) else "변경 없음"
        print(f"{DATASET_LABELS[dataset]:<8}로컬 : {changed}")
        _fact(f"{DATASET_LABELS[dataset]} {changed}")
    return 0


def _generation_line(pointer: manifest.Pointer) -> str:
    """작성자(`계정@PC 이름`)는 이름표로만 — 갈래(`origin`)가 누가 냈는지를 말한다."""
    return f"seq {pointer.seq} · {pointer.origin} · {AUTHOR_TAG}"


def command_probe(args: argparse.Namespace) -> int:
    """스토리지 능력을 실측한다. 확인하지 못한 것은 false 로 남긴다."""
    client = build_client(args)
    scratch = snapshot_export.prepare_scratch()
    sample = scratch / "probe.txt"
    sample.write_text("capa probe", encoding="utf-8")
    key = f"_probe/scratch-{uuid.uuid4().hex[:8]}.txt"
    results: dict[str, object] = {
        "_확인일": snapshot_export.utc_timestamp(),
        "_확인자": snapshot_export.author_label(),
    }
    try:
        _, md5_hex, md5_base64, _ = snapshot_export.digest_file(sample)
        outcome = client.put_file(key, sample, content_md5_base64=md5_base64)
        results["single_put_etag_is_md5"] = bool(
            outcome.etag and "-" not in outcome.etag and outcome.etag.lower() == md5_hex.lower()
        )
        print(f"업로드 ETag   : {outcome.etag or '(없음)'}")

        try:
            client.put_file(key, sample, content_md5_base64="AAAAAAAAAAAAAAAAAAAAAA==")
            results["content_md5_rejects_mismatch"] = False
        except ObjectStorageError:
            results["content_md5_rejects_mismatch"] = True

        forced = StorageSettings(
            mode=client.settings.mode,
            endpoint_url=client.settings.endpoint_url,
            bucket=client.settings.bucket,
            profile=client.settings.profile,
            region=client.settings.region,
            capabilities={"conditional_put_if_none_match_star": True},
        )
        conditional = ObjectStorageClient(settings=forced)
        try:
            second = conditional.put_file(key, sample, if_none_match=True)
            # 이미 있는 키인데 통과했다면 조건이 무시된 것이다 — 지원한다고 보면 안 된다.
            results["conditional_put_if_none_match_star"] = second.precondition_failed
        except ObjectStorageError as exc:
            print(f"조건부 쓰기   : 거부됨 — {masked(str(exc))}")
            results["conditional_put_if_none_match_star"] = False
    except ObjectStorageError as exc:
        print(_stop_line(exc))
        _stopped(failure_kind(exc))
        return 1
    finally:
        try:
            client.delete(key)
        except ObjectStorageError:
            print(f"[건너뜀] 정리 실패 — {key} 객체를 손으로 지워야 할 수 있습니다.")
        sample.unlink(missing_ok=True)

    shown = {**results, "_확인자": AUTHOR_TAG}
    print(json.dumps(shown, ensure_ascii=False, indent=1))
    if args.write:
        args.write.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"기록          : {masked(str(args.write))}")
    return 0


def _report_progress(event: engine.PublishProgress) -> None:
    """게시 도중의 한 줄 — 어디까지 왔는지 사람이 본다."""
    label = DATASET_LABELS[event.dataset]
    if isinstance(event, engine.SnapshotExported):
        result = event.export
        print(
            f"{label} 스냅샷 : {result.source_bytes / MIB:.1f} MiB → "
            f"{result.size_bytes / MIB:.1f} MiB, {result.elapsed_seconds:.2f}초"
        )
        _fact(
            f"{label} {result.source_bytes / MIB:.1f}→{result.size_bytes / MIB:.1f}MiB "
            f"{result.elapsed_seconds:.2f}초"
        )
    else:
        print(f"{label} 업로드 : {event.snapshot_key}")


def _report_outcome(outcome: engine.PublishOutcome) -> int:
    """게시 결과를 찍고 종료 코드를 돌려준다. 판정 글은 판정이 낸 그대로다."""
    if outcome.settled is not None:
        print(f"앞 회차 세대를 마무리했습니다 : seq {outcome.settled.seq}")
        _fact(f"마무리 seq {outcome.settled.seq}")
    if outcome.pending_pointer is not None:
        print(f"앞 회차가 남긴 포인터 : {outcome.pending_pointer}")
        print("[건너뜀] --dry-run 이라 마무리하지 않습니다.")
        _fact("건너뜀 dry-run 앞 회차 포인터")
        return 0
    if outcome.dry_run:
        print(f"[건너뜀] --dry-run 이라 올리지 않습니다. 예정 seq {outcome.seq}")
        _fact(f"건너뜀 dry-run 예정 seq {outcome.seq}")
        return 0
    if outcome.published:
        print(f"게시          : seq {outcome.seq}")
        _fact(f"게시 seq {outcome.seq}")
        return 0
    if outcome.confirm_deferred:
        print("[중단] 포인터가 들어갔는지 확인하지 못했습니다 — 다시 실행하면 가립니다.")
        _stopped("포인터 확인 못 함")
        return 1
    if outcome.stop is engine.PublishStop.LOCAL_MISSING:
        print("[중단] 로컬 DB 가 없습니다.")
        _stopped("로컬 DB 없음")
        return 1
    if outcome.stop is engine.PublishStop.REMOTE_MOVED:
        print(
            "[중단] 업로드 도중 원격이 앞섰습니다. 스냅샷은 보존했습니다 — "
            "resolve --keep mine 으로 승격하거나 --keep remote 로 버리세요."
        )
        _stopped("원격이 앞섬")
        return 1
    if outcome.stop is engine.PublishStop.FORKED:
        print("[중단] 원격이 갈라졌습니다 — rollback 으로 이어 갈 세대를 정하세요.")
        _stopped(FAILURE_LABELS[FAILURE_FORKED])
        return 1
    message = manifest.decision_message(outcome.decision, head_seq=outcome.head_seq)
    print(f"[건너뜀] {message}")
    if outcome.decision in manifest.BLOCKING_PUSH:
        _stopped(f"판정 {outcome.decision.value}")
        return 1
    _fact(f"건너뜀 판정 {outcome.decision.value}")
    return 0


def command_init(args: argparse.Namespace) -> int:
    client = build_client(args)
    paths = sync_paths()
    for dataset, database_path in DATASET_PATHS.items():
        if _blocked_by_running_app(dataset, "스냅샷을 내보내"):
            return 1
        if not database_path.exists():
            shown = masked(str(database_path))
            print(f"[중단] {DATASET_LABELS[dataset]} 로컬 DB 가 없습니다: {shown}")
            _stopped("로컬 DB 없음")
            return 1
    outcome = engine.init_generation(
        client,
        paths,
        exporter=engine.offline_exporter(paths),
        note=args.note,
        keep_writer=args.keep_writer,
        dry_run=args.dry_run,
        report=_report_progress,
    )
    if outcome.decision is PushDecision.UP_TO_DATE or outcome.dry_run:
        _AUDIT_DETAIL[_AUDIT_SKIP] = True
    if outcome.decision is PushDecision.UP_TO_DATE:
        print(f"[건너뜀] 원격에 이미 {with_subject_particle(f'seq {outcome.head_seq}')} 있습니다.")
        _fact(f"건너뜀 원격 seq {outcome.head_seq}")
        return 0
    if outcome.published:
        _AUDIT_DETAIL.update(seq_to=outcome.seq, datasets=sorted(outcome.uploaded))
    return _report_outcome(outcome)


def command_status(args: argparse.Namespace) -> int:
    client = build_client(args)
    decision, remote, state, dirty = engine.plan_push(client, sync_paths())
    tail = _head_tail(client, remote)
    remote_text = "비어 있음" if remote.head_seq is None else f"seq {remote.head_seq}{tail}"
    print(f"원격 : {remote_text}")
    _fact(f"원격 {remote_text}")
    print(f"로컬 : {'세대 미상' if state.base_seq is None else f'seq {state.base_seq}'}")
    _seq_fact("로컬", state.base_seq, none="세대 미상")
    for dataset in datasets(args):
        print(f"{DATASET_LABELS[dataset]} 변경 : {'있음' if dirty[dataset] else '없음'}")
        _fact(f"{DATASET_LABELS[dataset]} 변경 {'있음' if dirty[dataset] else '없음'}")
    if state.pending is not None:
        print(f"올리는 중 : {state.pending.pointer_key}")
        _fact("올리는 중 있음")
    if state.unpublished is not None:
        print(f"미게시 : {state.unpublished.reason}")
        _fact("미게시 있음")
    if remote.forked:
        print(f"분기 : {', '.join(remote.forked)}")
        _fact(f"분기 {len(remote.forked)}")
    if state.handed_over_utc is not None:
        print(f"정본 넘김 : {state.handed_over_utc}")
    _fact(f"넘김 {'있음' if state.handed_over_utc is not None else '없음'}")
    _fact(f"판정 {decision.value}")
    if state.handed_over_utc is not None and decision is PushDecision.PARENT_MOVED:
        print("판정 : 정본은 운영 앱에 있습니다 — 읽을 때는 fetch-copy 로 사본을 받으세요.")
        return 0
    print(f"판정 : {manifest.decision_message(decision, head_seq=remote.head_seq)}")
    return 0


def _head_tail(client: ObjectStorageClient, remote: engine.RemoteHead) -> str:
    """원격 HEAD 가 시작 펜스면 ` (시작 펜스)` — HEAD 포인터를 한 번 받는다. 받거나 읽지 못하면 꼬리
    없이 둔다(세대 번호 · 판정은 목록 한 번으로 이미 났다)."""
    if remote.head_key is None:
        return ""
    try:
        head = engine.read_pointer(client, remote.head_key)
    except (ObjectStorageError, ValueError, KeyError, TypeError, OSError):
        # 본문이 깨진 꼴(`seq` 없음 · null)을 파서는 ValueError 말고 KeyError · TypeError 로도 낸다
        # (일꾼의 `base_origin` 도 이 셋을 받는다). 받을 작업 폴더를 못 만들면 OSError 다.
        return ""
    return manifest.origin_tail(head.origin)


def command_generations(args: argparse.Namespace) -> int:
    """되돌릴 세대를 고르는 목록. 멤버 번호가 깨진 세대와 다른 세대가 되돌릴 자리다.

    지킨 세대는 줄 끝에 기한을 단다 — 정리가 지금 그 표지로 붙잡지 않으면(기한이 HEAD 날짜
    앞) 「지킴 지남」 이다. `--limit` 밖의 지킨 세대도 끝에 따로 찍고, 포인터가 없는 표지는 한
    줄로 말한다. 포인터 · 표지 모두 목록만 읽는다(GET 없음).
    """
    client = build_client(args)
    rows = engine.list_generations(client)
    deadlines = manifest.latest_pin_deadlines(engine.list_pins(client))
    _fact(f"세대 {len(rows)}")
    seqs = {row.seq for row in rows}
    if not rows:
        print("원격 : 비어 있음")
    else:
        _fact(f"HEAD seq {rows[0].seq}")
        head_moment = rows[0].last_modified
        for index, row in enumerate(rows[: args.limit]):
            pin = _pin_tail(deadlines.get(row.seq), head_moment)
            print(_generation_row(row, head=index == 0) + pin)
        if len(rows) > args.limit:
            print(f"… {len(rows) - args.limit}개 더 있습니다(--limit 로 늘립니다).")
            for row in rows[args.limit :]:
                if row.seq in deadlines:
                    print(
                        _generation_row(row, head=False)
                        + _pin_tail(deadlines[row.seq], head_moment)
                    )
        held = [
            seq
            for seq, until in deadlines.items()
            if seq in seqs and manifest.pin_holds(until, head_moment)
        ]
        if deadlines:
            _fact(f"지킴 {len(held)}")
    for seq in deadlines:
        if seq not in seqs:
            print(f"지킴 표지 seq {seq} — 세대 없음")
    return 0


def _generation_row(row: engine.GenerationRow, *, head: bool) -> str:
    members = " · ".join(f"{DATASET_LABELS[name]} {seq}" for name, seq in row.members.items())
    moment = "시각 모름" if row.last_modified is None else row.last_modified.isoformat()
    return f"seq {row.seq} · {members} · {row.token} · {moment}{' · HEAD' if head else ''}"


def _pin_tail(until: date | None, head_moment: datetime | None) -> str:
    """세대 줄 끝의 지킴 꼬리 — 표지가 없으면 빈 글."""
    if until is None:
        return ""
    word = "지킴" if manifest.pin_holds(until, head_moment) else "지킴 지남"
    return f" · {word} ~{until.isoformat()}"


def command_keep(args: argparse.Namespace) -> int:
    """세대 하나에 기한 있는 지킴 표지를 둔다. 붙잡는 일이라 `--yes` 를 받지 않는다.

    끝 줄에 지킨 seq · 두 멤버의 세대 · 마이그레이션 판 · 기한을 싣는다 — 되돌릴 날의 옛 도구는
    표지를 모르므로 리뷰에 옮긴 이 줄이 지킨 세대의 기록이다. 메모는 표지 본문에만 둔다.
    """
    if not engine.PIN_DAYS_MIN <= args.days <= engine.PIN_DAYS_MAX:
        _AUDIT_DETAIL[_AUDIT_SKIP] = True
        print(
            f"[중단] --days 는 {engine.PIN_DAYS_MIN} ~ {engine.PIN_DAYS_MAX} 입니다 — "
            "aws 를 부르지 않았습니다."
        )
        _stopped(STOP_REQUEST)
        return 1
    if args.dry_run:
        _AUDIT_DETAIL[_AUDIT_SKIP] = True
        print("[건너뜀] --dry-run 이라 표지를 두지 않습니다.")
        _fact("건너뜀 dry-run")
        return 0
    client = build_client(args)
    try:
        outcome = engine.keep_generation(
            client, seq=None if args.head else args.seq, days=args.days, note=args.note
        )
    except ValueError as exc:
        print(_stop_line(exc))
        _stopped(STOP_REQUEST)
        return 1
    pointer = outcome.pointer
    until = outcome.marker.until.isoformat()
    simulation = pointer.members["simulation"]
    equipment = pointer.members["equipment"]
    _AUDIT_DETAIL.update(seq_to=pointer.seq, keep_until=until)
    print(f"지킴 : seq {pointer.seq} · 기한 ~{until}")
    print(
        f"멤버 : {DATASET_LABELS['simulation']} {simulation.seq}(판 {simulation.migration_version})"
        f" · {DATASET_LABELS['equipment']} {equipment.seq}(판 {equipment.migration_version})"
    )
    _fact(f"지킴 seq {pointer.seq}")
    _fact(f"멤버 S{simulation.seq} E{equipment.seq}")
    _fact(f"판 S{simulation.migration_version} E{equipment.migration_version}")
    _fact(f"기한 {until}")
    return 0


def command_unkeep(args: argparse.Namespace) -> int:
    """그 seq 의 지킴 표지만 지운다. 세대 · 스냅샷은 건드리지 않는다."""
    if not args.yes:
        _AUDIT_DETAIL[_AUDIT_SKIP] = True
        print(f"[건너뜀] seq {args.seq} 의 지킴 표지를 풀려면 --yes 를 함께 주세요.")
        _fact("건너뜀 --yes 없음")
        return 0
    if args.dry_run:
        _AUDIT_DETAIL[_AUDIT_SKIP] = True
        print("[건너뜀] --dry-run 이라 표지를 풀지 않습니다.")
        _fact("건너뜀 dry-run")
        return 0
    removed = engine.release_generation(build_client(args), seq=args.seq)
    if not removed:
        _AUDIT_DETAIL[_AUDIT_SKIP] = True
        print(f"[건너뜀] seq {args.seq} 에는 지킴 표지가 없습니다.")
        _fact("건너뜀 표지 없음")
        return 0
    _AUDIT_DETAIL["seq_to"] = args.seq
    print(f"풀림 : seq {args.seq} · 표지 {len(removed)}")
    _fact(f"풀림 seq {args.seq} · 표지 {len(removed)}")
    return 0


def _app_is_running(dataset: DatasetName) -> str | None:
    """앱이 이 PC 에서 이 DB 를 잡고 있으면 그 인스턴스 id.

    DuckDB 파일은 프로세스 배타 잠금이라 앱이 떠 있는 동안 스냅샷을 내보내지도, 받은
    파일로 덮지도 못한다. 막지 않으면 `duckdb.IOException` 원문이 그대로 나오고 — Windows
    로캘에서는 한글까지 깨져 — 사용자는 원인이 "앱이 켜져 있다" 라는 것을 알 수 없다.

    심장박동은 앱이 10초에 한 번 남기고 90초 지나면 죽은 것으로 본다. 끄고 바로 돌리면
    잠깐 남아 있을 수 있으나, 그때는 안내를 보고 다시 실행하면 된다 — 조용히 실패하는
    것보다 낫다.
    """
    return sync_state.live_instance(DATASET_PATHS[dataset])


def _blocked_by_running_app(dataset: DatasetName, action: str) -> bool:
    instance = _app_is_running(dataset)
    if instance is None:
        return False
    _stopped("앱 실행 중")
    print(
        f"[중단] {DATASET_LABELS[dataset]} — 앱이 이 PC 에서 실행 중입니다"
        f"(인스턴스 {instance}). DuckDB 는 프로세스 배타 잠금이라 앱을 끄지 않으면 "
        f"{action} 할 수 없습니다."
    )
    return True


def command_pull(args: argparse.Namespace) -> int:
    client = build_client(args)
    paths = sync_paths()
    if any(_blocked_by_running_app(dataset, "받은 파일로 덮어") for dataset in DATASET_PATHS):
        return 1
    plan = engine.plan_pull(client, paths, force=args.force)
    if plan.forced:
        print("[주의] 세대를 모르지만 --force 라 덮습니다.")
    if not plan.proceeds:
        print(f"[건너뜀] {manifest.decision_message(plan.decision, head_seq=plan.remote.head_seq)}")
        blocked = plan.decision in (PullDecision.BLOCKED_DIRTY, PullDecision.BLOCKED_FORKED)
        return 1 if blocked else 0
    if args.dry_run:
        print(f"[건너뜀] --dry-run 이라 받지 않습니다. 예정 seq {plan.remote.head_seq}")
        return 0
    outcome = engine.apply_pull(client, paths, plan)
    for dataset, install in outcome.installs.items():
        backup = install.database_backup or install.backup_dir
        shown = masked(str(backup))
        print(f"{DATASET_LABELS[dataset]} 설치 : seq {outcome.seq} (이전 파일 백업 {shown})")
    return 0


def command_push(args: argparse.Namespace) -> int:
    client = build_client(args)
    paths = sync_paths()
    if any(_blocked_by_running_app(dataset, "스냅샷을 내보내") for dataset in DATASET_PATHS):
        return 1
    if _writer_refusal(args, client, "올리기를"):
        return 1
    outcome = engine.publish_generation(
        client,
        paths,
        exporter=engine.offline_exporter(paths),
        origin="manual",
        note=args.note,
        dry_run=args.dry_run,
        report=_report_progress,
    )
    return _report_outcome(outcome)


def command_resolve(args: argparse.Namespace) -> int:
    client = build_client(args)
    paths = sync_paths()
    state = sync_state.read_generation(paths.generation)
    if state.unpublished is None:
        print("[건너뜀] 해소할 미게시 세대가 없습니다.")
        return 0
    if args.keep == "remote":
        if any(_blocked_by_running_app(dataset, "내 세대 버리기를") for dataset in DATASET_PATHS):
            return 1
        if args.dry_run:
            print("[건너뜀] --dry-run 이라 버리지 않습니다.")
            return 0
        engine.resolve_keep_remote(paths)
        print("내 세대를 버렸습니다. pull 로 원격을 받으세요.")
        return 0
    if _writer_refusal(args, client, "승격을"):
        return 1
    if args.dry_run:
        print("[건너뜀] --dry-run 이라 승격하지 않습니다.")
        return 0
    pointer = engine.resolve_keep_mine(client, paths)
    print(f"{with_direction_particle(f'seq {pointer.seq}')} 승격했습니다.")
    if sync_state.read_generation(paths.generation).base_pointer_key != pointer.pointer_key:
        print("[주의] 그 사이 앞선 DB 는 원격 것을 이어 적었습니다 — pull 로 받으세요.")
    return 0


def command_adopt(args: argparse.Namespace) -> int:
    client = build_client(args)
    if args.source == "remote":
        print("[안내] pull --force 로 원격을 받으세요.")
        return 0
    if _writer_refusal(args, client, "기준 정하기를"):
        return 1
    head = _head_pointer(client)
    if head is None:
        print("[중단] 원격이 비어 있습니다. init 이 먼저입니다.")
        return 1
    engine.adopt_local(sync_paths(), head)
    print("로컬을 기준으로 잡았습니다. push 로 올리세요.")
    return 0


def command_prune(args: argparse.Namespace) -> int:
    client = build_client(args)
    options = {
        "keep_last": args.keep_last,
        "keep_days": args.keep_days,
        "include_orphans": args.include_orphans,
    }
    plan = engine.plan_prune(client, **options)
    print(
        f"정리 후보 : 스냅샷 {len(plan.snapshots)} · 포인터 {len(plan.pointers)} · "
        f"남길 세대 {plan.kept_generations} · 지킨 고아 {plan.protected_orphans}"
    )
    for key in (*plan.snapshots, *plan.pointers):
        print(f"   {key}")
    if plan.deferred:
        print(f"   상한을 넘어 다음 번으로 넘긴 수 {plan.deferred}")
    if not plan.total:
        _AUDIT_DETAIL[_AUDIT_SKIP] = True
        return 0
    if args.dry_run or not args.yes:
        _AUDIT_DETAIL[_AUDIT_SKIP] = True
        print("   [건너뜀] 실제로 지우려면 --yes 를 함께 주세요.")
        return 0
    outcome = engine.prune(client, **options)
    _AUDIT_DETAIL["deleted"] = outcome.deleted
    print(f"   {outcome.deleted}개를 지웠습니다.")
    if outcome.interrupted:
        print("   [중단] 판정 뒤 HEAD 가 움직였습니다 — 다시 돌리면 새 판정으로 잇습니다.")
        return 1
    return 0


def command_fetch_copy(args: argparse.Namespace) -> int:
    client = build_client(args)
    try:
        outcome = engine.fetch_copy(client, sync_paths(), args.to, seq=args.seq, token=args.token)
    except ValueError as exc:
        print(_stop_line(exc))
        _stopped(STOP_REQUEST)
        return 1
    _AUDIT_DETAIL["seq_to"] = outcome.pointer.seq
    print(f"받음 : seq {outcome.pointer.seq} · {masked(str(outcome.folder))}")
    _fact(f"받음 seq {outcome.pointer.seq}")
    return 0


def command_rollback(args: argparse.Namespace) -> int:
    if not args.yes:
        _AUDIT_DETAIL[_AUDIT_SKIP] = True
        print(f"[건너뜀] seq {args.to} 멤버로 새 HEAD 를 내려면 --yes 를 함께 주세요.")
        _fact("건너뜀 --yes 없음")
        return 0
    client = build_client(args)
    try:
        pointer = engine.rollback(client, to_seq=args.to, token=args.token, note=args.note)
    except ValueError as exc:
        # 포인터를 낸 뒤의 멤버 확인 실패는 aws 진단 글을 감싸 온다(값이 든다).
        print(_stop_line(exc))
        _stopped(STOP_REQUEST)
        return 1
    _AUDIT_DETAIL.update(seq_from=args.to, seq_to=pointer.seq)
    print(f"새 HEAD : seq {pointer.seq} — seq {args.to} 의 멤버를 이어 갑니다.")
    _fact(f"새 HEAD seq {pointer.seq} · 이은 세대 seq {args.to}")
    return 0


def _boot_line(outcome: engine.BootOutcome) -> str:
    """시작 스크립트가 읽는 한 줄. 값은 갈래 · 수 · DB 이름뿐이다(주소 · 버킷 · 키 · 서버 글
    없음) — 머문 까닭의 수 · 이름은 시작 임시 화면의 접힌 진단이 싣는다."""
    return json.dumps(
        {
            "kind": outcome.kind,
            "action": outcome.action,
            "seq": outcome.seq,
            "previous_upload_utc": outcome.previous_upload_utc,
            "last_save_utc": outcome.last_save_utc,
            "total_bytes": outcome.total_bytes,
            "seconds": round(outcome.elapsed_seconds, 2),
            "needed_bytes": outcome.needed_bytes,
            "free_bytes": outcome.free_bytes,
            "datasets": list(outcome.datasets),
            "file_version": outcome.file_version,
            "code_version": outcome.code_version,
        },
        ensure_ascii=False,
    )


def _download_noter(mark: Path | None) -> Callable[[], None] | None:
    """실제 내려받기로 넘어간 순간 `mark` 를 남기는 것 — 시작 스크립트의 임시 화면이 그 표지를 보고
    「n번째 받는 중」 을 보인다. 표지는 화면 몫이라 쓰지 못해도 받기를 실패시키지 않는다."""
    if mark is None:
        return None

    def note() -> None:
        try:
            mark.parent.mkdir(parents=True, exist_ok=True)
            mark.touch()
        except OSError:
            return

    return note


def command_boot_pull(args: argparse.Namespace) -> int:
    """앱이 뜨기 전 받기. 종료 코드 0 일 때만 시작 스크립트가 앱을 띄운다.

    주소 · 버킷 · 프로필 가운데 빈 것이 있으면 `aws` 를 부르지 않고 `config` 로 머문다 — 기본값이
    없으니 고를 곳도 없다. 부트 기록을 쓰지 못해도 실패다 — 일꾼 없이 뜬 앱의 저장은 어디에도 안
    올라간다.
    """
    if object_storage.missing_environment(build_settings(args)):
        print(_boot_line(engine.BootOutcome(kind=FAILURE_CONFIG)))
        return 1
    client = build_client(args)
    sync_boot.clear_boot_record()
    outcome = engine.boot_pull(
        client, sync_paths(), on_download=_download_noter(args.download_mark)
    )
    if outcome.ok:
        assert outcome.action is not None and outcome.seq is not None
        sync_boot.write_boot_record(
            sync_boot.BootRecord(
                action=outcome.action,
                seq=outcome.seq,
                previous_upload_utc=outcome.previous_upload_utc,
                last_save_utc=outcome.last_save_utc,
                pull_seconds=outcome.elapsed_seconds,
                finished_at_utc=snapshot_export.utc_timestamp(),
                total_bytes=outcome.total_bytes,
            )
        )
    print(_boot_line(outcome))
    return 0 if outcome.ok else 1


def _audit_days(args: argparse.Namespace) -> list[date]:
    if args.month:
        first = datetime.strptime(args.month, "%Y-%m").date()
        days = []
        day = first
        while day.month == first.month:
            days.append(day)
            day += timedelta(days=1)
        return days
    if not args.date or args.date == "today":
        return [datetime.now(timezone.utc).date()]
    return [datetime.strptime(args.date, "%Y-%m-%d").date()]


def command_audit_list(args: argparse.Namespace) -> int:
    """날짜마다 조각(seg · tool) · 일별 파일 수 — 사람 값 · 키는 찍지 않는다."""
    try:
        days = _audit_days(args)
    except ValueError:
        print("[중단] --date 는 YYYY-MM-DD 또는 today, --month 는 YYYY-MM 입니다.")
        return 1
    client = build_client(args)
    daily = [
        audit_layout.parse_daily(record.key)
        for record in client.list_all_objects(audit_layout.DAILY_PREFIX)
    ]
    daily_days = {found[0] for found in daily if found is not None and found[2] == "jsonl.gz"}
    with_files = 0
    for day in days:
        text = day.isoformat()
        seg = len(client.list_all_objects(audit_layout.piece_prefix("seg", text)))
        tool = len(client.list_all_objects(audit_layout.piece_prefix("tool", text)))
        has_daily = text in daily_days
        with_files += 1 if (seg or tool or has_daily) else 0
        print(f"{text} : 조각 seg {seg} · tool {tool} · 일별 {'있음' if has_daily else '없음'}")
    if len(days) > 1:
        print(f"합계 : {len(days)}일 가운데 기록 있는 날 {with_files}")
    return 0


def _leave_tool_piece(args: argparse.Namespace, code: int) -> None:
    """정본을 바꾸는 명령의 감사 조각(`audit/tool.py`).

    건너뛴 명령 · 빈 설정 · 꼴이 틀린 설정은 남기지 않는다.
    """
    event = AUDITED_COMMANDS.get(args.command)
    if event is None or _AUDIT_DETAIL.get(_AUDIT_SKIP):
        return
    try:
        settings = build_settings(args)
    except StorageSettingsError:
        return
    if object_storage.missing_environment(settings):
        return
    detail = {key: value for key, value in _AUDIT_DETAIL.items() if key != _AUDIT_SKIP}
    detail["result"] = "ok" if code == 0 else "fail"
    key = upload_tool_piece(
        build_client(args),
        event,
        out="success" if code == 0 else "fail",
        det=detail,
        scratch=Path(tempfile.gettempdir()) / "capa-audit-tool",
    )
    if key is None:
        print("[경고] 감사 기록 조각을 올리지 못했습니다 — 명령의 결과는 그대로입니다.")


COMMANDS = {
    "profile": command_profile,
    "doctor": command_doctor,
    "probe": command_probe,
    "init": command_init,
    "status": command_status,
    "pull": command_pull,
    "push": command_push,
    "resolve": command_resolve,
    "adopt": command_adopt,
    "prune": command_prune,
    "fetch-copy": command_fetch_copy,
    "rollback": command_rollback,
    "generations": command_generations,
    "keep": command_keep,
    "unkeep": command_unkeep,
    "boot-pull": command_boot_pull,
    "audit-list": command_audit_list,
}


def _use_utf8_output() -> None:
    # Windows(한국어 로캘)의 콘솔·파이프 기본 인코딩(cp949)은 이 출력의 「—」 같은 기호를 못 쓴다.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> int:
    _use_utf8_output()
    args = parse_args(argv)
    _SUMMARY.reset()
    with _masked_logging():
        code = _run_command(args)
    if args.command not in NO_SUMMARY:
        print(summary_line(args.command, code))
    return code


def _run_command(args: argparse.Namespace) -> int:
    handler = COMMANDS[args.command]
    # 사이드카 기록은 등록된 경로에만 쓴다. 스크립트는 이 파일들의 주인이므로 여기서 등록한다.
    # `--dataset` 과 상관없이 둘 다다 — 두 DB 는 한 쌍이다.
    sync_state.enable(sync_paths().registry)
    _AUDIT_DETAIL.clear()
    _load_redaction(args)
    code = 1
    try:
        code = int(handler(args))
        return code
    except ObjectStorageError as exc:
        _stopped(failure_kind(exc))
        if args.command == "boot-pull":
            print(_boot_line(engine.BootOutcome(kind=object_storage.classify_failure(exc))))
        elif isinstance(exc, StorageSettingsError) and exc.label == object_storage.SETTINGS_MISSING:
            print(_missing_line(object_storage.missing_environment(build_settings(args))))
        else:
            print(_stop_line(exc))
        return 1
    except BOOTSTRAP_ERRORS as exc:
        # `duckdb.Error` 는 RuntimeError 가 아니다. 이걸 잡지 않으면 앱을 켜 둔 채 돌렸을 때
        # 원문 트레이스백이 나오고 Windows 로캘에서는 한글까지 깨진다.
        _stopped(FAILURE_LABELS[FAILURE_OTHER])
        if args.command == "boot-pull":
            print(_boot_line(engine.BootOutcome(kind=FAILURE_OTHER)))
        else:
            print(f"[중단] {masked(bootstrap_error_message(exc, markdown=False))}")
        return 1
    finally:
        try:
            _leave_tool_piece(args, code)
        except Exception:  # noqa: BLE001 — 기록 실패가 운영 명령의 결과를 바꾸지 않는다
            print("[경고] 감사 기록 조각을 올리지 못했습니다 — 명령의 결과는 그대로입니다.")


if __name__ == "__main__":
    sys.excepthook = _masked_excepthook
    sys.exit(main())
