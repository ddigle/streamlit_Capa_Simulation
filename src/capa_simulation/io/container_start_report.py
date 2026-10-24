# Purpose: CD 시작 스크립트와 앱이 함께 쓰는 환경변수 이름·결과 파일 꼴과 화면 안내를 정한다.

"""C-DEP CD 컨테이너 시작 점검 결과.

CD 서버는 시작 명령을 바꿀 수 없고 셸에 들어갈 수도 없다. 그래서 이미지의 시작 스크립트
(`scripts/container_start.py`)가 C-DEP 배포 설정의 환경변수(key·value 표)만으로 사내
`bigdataquery` 설치(0)·로그인 토큰 파일(1)·요청자 계정(2)을 갖추고, 단계마다 결과를
`settings.CONTAINER_START_REPORT_PATH` 에 남긴다. 로그도 볼 수 없다고 보아 **앱 화면이 진단
창구다** — Admin Area 「서버 시작 점검」과 BigDataQuery 안내(`company_bigdataquery_adapter`)가
이 파일을 읽는다.

**비밀값은 파일에 없다.** 스크립트가 Artifactory 토큰·BDQ 토큰·URL 의 자격증명을 가리고, 계정은
앞 두 글자만 남긴다(`mask_account`). 이 모듈은 표준 라이브러리와 `settings` 만 읽는다 — 시작
스크립트가 앱 의존성을 불러오기 전에 쓰기 때문이다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from capa_simulation import settings

# C-DEP 배포 설정의 환경변수 표에 넣는 key. 값은 사람마다 다르고 비밀이라 저장소·배포 ZIP 에
# 두지 않는다.
ARTIFACTORY_USER_ENV: Final = "CAPA_ARTIFACTORY_USER"
ARTIFACTORY_TOKEN_ENV: Final = "CAPA_ARTIFACTORY_TOKEN"
BDQ_TOKEN_ENV: Final = "CAPA_BDQ_TOKEN"
# 조회 요청자의 사내 계정. 사람마다 다른 값이라 저장소에 두지 않는다 — 배포 ZIP 을 받은 다른
# 사람이 남의 계정으로 조회하게 된다. 어댑터(`getData(user_name=…)`)와 시작 스크립트(토큰 파일
# 이름)가 함께 읽는다.
BDQ_USER_NAME_ENV: Final = "CAPA_BDQ_USER_NAME"
CD_ENVIRONMENT: Final = (
    ARTIFACTORY_USER_ENV,
    ARTIFACTORY_TOKEN_ENV,
    BDQ_TOKEN_ENV,
    BDQ_USER_NAME_ENV,
)

REPORT_VERSION: Final = 1
STEP_INSTALL: Final = "install"
STEP_TOKEN: Final = "token"
STEP_USER_NAME: Final = "user_name"
STEPS: Final = (STEP_INSTALL, STEP_TOKEN, STEP_USER_NAME)
STEP_LABELS: Final[Mapping[str, str]] = {
    STEP_INSTALL: "bigdataquery 설치",
    STEP_TOKEN: "로그인 토큰 파일",
    STEP_USER_NAME: "요청자 계정",
}
# 단계마다 그 단계가 읽는 환경변수. 화면 안내는 빠진 것 가운데 그 단계 몫만 「넣을 것」으로
# 적는다 — 설치 안내에 `CAPA_BDQ_USER_NAME` 이 섞이면 점검 스크립트
# (`inspect_real_data_checks._bdq_failure`)가 그 이름으로 「요청자 계정 필요」를 가른다.
STEP_ENVIRONMENT: Final[Mapping[str, tuple[str, ...]]] = {
    STEP_INSTALL: (ARTIFACTORY_USER_ENV, ARTIFACTORY_TOKEN_ENV),
    STEP_TOKEN: (BDQ_TOKEN_ENV, BDQ_USER_NAME_ENV),
    STEP_USER_NAME: (BDQ_USER_NAME_ENV,),
}

STATUS_OK: Final = "ok"
STATUS_SKIPPED: Final = "skipped"
STATUS_FAILED: Final = "failed"
STATUS_LABELS: Final[Mapping[str, str]] = {
    STATUS_OK: "정상",
    STATUS_SKIPPED: "건너뜀",
    STATUS_FAILED: "실패",
}


@dataclass(frozen=True)
class StartStep:
    status: str
    reason: str


@dataclass(frozen=True)
class ContainerStartReport:
    """시작 스크립트가 남긴 한 번의 결과. 값은 모두 이미 가린 꼴이다."""

    written_at: str
    steps: Mapping[str, StartStep]
    bigdataquery_version: str | None
    token_file_exists: bool | None
    token_file_modified_at: str | None
    user_name_masked: str | None
    missing_environment: tuple[str, ...]
    pip_tail: tuple[str, ...]


def mask_account(name: str) -> str:
    """계정은 앞 두 글자만 남긴다(`fakeaccount` → `fa***`)."""
    return f"{name[:2]}***"


def report_path() -> Path:
    """결과 파일 자리. 부를 때마다 `settings` 에서 읽는다 — 시험이 그 칸을 tmp 로 옮긴다."""
    return settings.CONTAINER_START_REPORT_PATH


def read_container_start_report(path: Path | None = None) -> ContainerStartReport | None:
    """결과 파일을 읽는다. 없거나 꼴이 어긋나면 `None` — 개발·사내 PC 는 늘 `None` 이다.

    화면 회차마다 불러도 되는 크기(작은 JSON 하나)라 캐시하지 않는다. DB 를 열지 않는다.
    """
    target = report_path() if path is None else path
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return parse_report(data)


def parse_report(data: object) -> ContainerStartReport | None:
    if not isinstance(data, dict) or not isinstance(data.get("steps"), dict):
        return None
    steps: dict[str, StartStep] = {}
    for name in STEPS:
        step = data["steps"].get(name)
        if not isinstance(step, dict):
            return None
        status, reason = step.get("status"), step.get("reason")
        if status not in STATUS_LABELS or not isinstance(reason, str):
            return None
        steps[name] = StartStep(status=str(status), reason=reason)
    token_file = _mapping(data.get("token_file"))
    user_name = _mapping(data.get("user_name"))
    missing = data.get("missing_environment")
    tail = data.get("pip_tail")
    exists = token_file.get("exists")
    return ContainerStartReport(
        written_at=str(data.get("written_at") or ""),
        steps=steps,
        bigdataquery_version=_text_or_none(data.get("bigdataquery_version")),
        token_file_exists=exists if isinstance(exists, bool) else None,
        token_file_modified_at=_text_or_none(token_file.get("modified_at")),
        user_name_masked=_text_or_none(user_name.get("masked")),
        missing_environment=tuple(
            str(name) for name in (missing if isinstance(missing, list) else [])
        ),
        pip_tail=tuple(str(line) for line in (tail if isinstance(tail, list) else [])),
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def missing_for_step(report: ContainerStartReport, step: str) -> tuple[str, ...]:
    """그 단계가 읽는데 시작 때 비어 있던 환경변수."""
    return tuple(name for name in STEP_ENVIRONMENT[step] if name in report.missing_environment)


def step_hint(report: ContainerStartReport, step: str) -> str:
    """BigDataQuery 안내에 덧붙일 한 단락 — 그 단계의 결과와 넣을 환경변수."""
    result = report.steps[step]
    line = f"서버 시작 점검 — {STEP_LABELS[step]} {STATUS_LABELS[result.status]}: {result.reason}."
    missing = missing_for_step(report, step)
    if missing:
        names = "·".join(f"`{name}`" for name in missing)
        line += (
            f" 넣을 CD 환경변수: {names} — C-DEP 배포 설정의 환경변수 표에 넣고 CI/CD 를 다시 "
            "돌리세요."
        )
    elif step == STEP_TOKEN and result.status == STATUS_OK:
        line += (
            " 토큰이 만료됐을 수 있습니다 — WebIDE 에서 다시 로그인해 "
            f"`{BDQ_TOKEN_ENV}` 값을 바꾸고 CI/CD 를 다시 돌리세요."
        )
    elif result.status == STATUS_FAILED:
        line += " 자세한 결과는 Admin Area 「서버 시작 점검」 에 있습니다."
    return line


def start_check_hint(step: str, path: Path | None = None) -> str | None:
    """결과 파일이 있으면 그 단계의 안내 한 단락, 없으면 `None`(지금 문구 그대로)."""
    report = read_container_start_report(path)
    return None if report is None else step_hint(report, step)


def report_verdict(report: ContainerStartReport) -> str:
    """펼침 제목 끝에 붙는 한마디 — 실패가 하나라도 있으면 실패, 다음은 건너뜀."""
    statuses = {step.status for step in report.steps.values()}
    if STATUS_FAILED in statuses:
        return "실패 있음"
    if STATUS_SKIPPED in statuses:
        return "건너뜀 있음"
    return "모두 정상"
