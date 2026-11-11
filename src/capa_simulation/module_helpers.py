# Purpose: 모듈 창구 도우미의 속 — BigDataQuery 조회와 모듈 데이터 S3 올리기·받기를 코어가 한다.

"""모듈 창구 도우미(창구 1.3 — 2026-11-12 사용자 결정 「도우미 함수로」).

모듈은 자격(BigDataQuery 요청자 계정 · 토큰, S3 키)을 읽지 않고 창구 함수만 부른다
(`module_api.query_bigdataquery` · `s3_upload` · `s3_download`). 이 파일이 그 속이고, 공개 이름 ·
서명은 `module_api` 가 낸다(겉면 시험이 고정한다). 모듈은 이 파일을 import 하지 않는다(M06).

- **BigDataQuery** — 앱의 DB 등록 · 목록 조회와 같은 길(`load_bigdataquery_module` →
  `call_get_data`)이고 같은 실패 갈래(`BigDataQueryCallError.kind`)다. 요청자 계정은 그 길이
  환경에서 채운다. 기간을 주면 조회문의 `{start_date}` 에 시작 날, `{end_date}` 에 끝 날 다음 날을
  앱과 같은 꼴(`QueryWindow.sql_bounds` — 조회문은 `< '{end_date}'` 로 끝 날까지 담는다)로 채운다.
  결과는 캐시하지 않는다(모듈의 `cache.py` 몫 — M12).
- **S3** — 모듈 데이터 자리(`ctx.data_dir`) 아래 파일 하나를 버킷의 `modules/<id>/` 아래 같은
  이름으로 올리고 받는다. 언제 올리고 받을지는 모듈이 정한다 — 코어는 모듈 폴더를 대신
  동기화하지 않는다. 닿는 길은 접속 명단과 같은 작은 객체 경계(`io/s3_small` — 표준 라이브러리
  SigV4, 프로세스를 띄우지 않는다)이고 키 · 주소 · 버킷도 접속 명단의 한
  벌(`auth.runtime.config().access_s3`)이다 — 운영 진입 파일은 기동 때 그 키를 환경에서 빼므로
  환경을 다시 읽지 않는다. 동기화 모드가 `managed`(쓰는 쪽 운영 서버 하나)일 때만 연다 — 개발
  서버 · WebIDE · 사내 PC 앱이 같은 버킷에 쓰지 않게.
- **예외로 화면을 깨지 않는다(S3).** 쓸 수 없음 · 이름 거절 · 전송 실패 모두 `S3Result` 로 돌려준다.
  BigDataQuery 는 결과가 표라 실패를 `BigDataQueryError`(`kind` 가 갈래)로 던진다 — 모듈 캐시 함수가
  실패를 캐시하지 않게.
- **모듈 시험(감시 러너)에서는 밖에 닿지 않는다** — `module_registry.TEST_RUN_ENV_VAR` 가 켜져
  있으면 조회는 「쓸 수 없음」 으로 던지고 S3 는 「쓸 수 없음」 을 돌려준다.
- 돌려주는 까닭 · 로그에는 고정 낱말만 싣는다(버킷 · 주소 · 키 · 조회문 없음). 조회 실패의 글은 앱
  화면과 같은 안내(`BigDataQueryCallError` 의 글)다.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

import pandas as pd

from capa_simulation import module_registry
from capa_simulation.io import s3_small

if TYPE_CHECKING:
    from capa_simulation.io.s3_small import S3Target

_LOGGER = logging.getLogger("capa_simulation.modules")

# --- BigDataQuery ------------------------------------------------------------------------------
# 앱 경계의 실패 갈래(`company_bigdataquery_adapter.QUERY_FAILURE_*`)에 더하는 둘.
QUERY_UNAVAILABLE: Final = "쓸 수 없음"
QUERY_INPUT: Final = "입력"
# 조회문 글자 상한 — 붙여 넣은 표 · 파일을 조회문으로 넘기는 실수를 막는다.
MAX_QUERY_CHARS: Final = 100_000
# 기간 상한 — 앱의 목록 조회(`bigdataquery_catalog.MAX_CATALOG_WINDOW_DAYS`)와 같은 까닭(팩트 표
# 전면 조회 막기)이다.
MAX_QUERY_WINDOW_DAYS: Final = 366
_DATE_PLACEHOLDERS: Final = ("{start_date}", "{end_date}")

# --- S3 ----------------------------------------------------------------------------------------
# 파일 하나의 상한. 모듈 데이터는 메모리에 한 번 올려 보내고 받는다(운영 서버 메모리 1GiB).
S3_MAX_BYTES: Final = 8 * 1024 * 1024
# 전송 마감 — 연결 · 머리(`s3_small` 의 요청 마감)에 바닥 속도로 상한 크기를 보내는 시간을 더한다.
# 바닥 속도는 DB 정본 전송의 바닥(`object_storage.MIN_TRANSFER_MIB_PER_SECOND`)과 같다.
_MIN_MIB_PER_SECOND: Final = 0.3
S3_KEY_PREFIX: Final = "modules/"
# 이름 — `/` 로 나눈 마디 1 ~ 4개, 마디는 영문 · 숫자로 시작하고 영문 · 숫자 · `.` · `_` · `-` 만.
# `..` · 숨은 이름 · 빈 마디 · 역슬래시 · 절대 경로가 이 꼴에서 모두 빠진다.
S3_NAME_MAX_LENGTH: Final = 200
S3_NAME_MAX_PARTS: Final = 4
_NAME_PART: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_CONTENT_TYPE: Final = "application/octet-stream"

S3_UNAVAILABLE: Final = "쓸 수 없음"
S3_NAME_REJECTED: Final = "이름 거절"
S3_NOT_FOUND: Final = "파일 없음"
S3_TOO_LARGE: Final = "너무 큼"
S3_TRANSFER_FAILED: Final = "전송 실패"
S3_FILE_ERROR: Final = "파일 오류"
S3_REASONS: Final = (
    S3_UNAVAILABLE,
    S3_NAME_REJECTED,
    S3_NOT_FOUND,
    S3_TOO_LARGE,
    S3_TRANSFER_FAILED,
    S3_FILE_ERROR,
)
# 「쓸 수 없음」 의 자세히(고정 낱말).
UNAVAILABLE_TEST_RUN: Final = "모듈 시험"
UNAVAILABLE_NOT_MANAGED: Final = "동기화 모드 managed 아님"
UNAVAILABLE_SETTINGS: Final = "설정 읽기 실패"
UNAVAILABLE_NO_TARGET: Final = "키 · 주소 · 버킷 없음"
# 「파일 오류」 의 자세히 — 받을 자리에 폴더가 있다(그 밖은 예외 종류 이름).
S3_DETAIL_FOLDER: Final = "폴더가 있음"
# 「전송 실패」 의 자세히 — `s3_small` 의 까닭 분류 → 고정 낱말.
_TRANSFER_LABELS: Final = {
    s3_small.KIND_UNREACHABLE: "주소에 닿지 못함",
    s3_small.KIND_TIMEOUT: "시간 초과",
    s3_small.KIND_TLS: "인증서 확인 실패",
    s3_small.KIND_AUTH: "인증 거절",
    s3_small.KIND_NO_BUCKET: "버킷 없음",
    s3_small.KIND_OTHER: "그 밖의 응답",
}


class BigDataQueryError(RuntimeError):
    """`query_bigdataquery` 의 실패. `kind` 가 갈래이고 글은 앱 화면과 같은 안내다."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class S3Result:
    """S3 올리기 · 받기 한 번의 결과. 성공이면 `ok` 이고 `reason` 은 빈 글이다.

    `reason` 은 `S3_REASONS` 가운데 하나, `detail` 은 그 까닭의 고정 낱말(전송 실패의 분류 · 쓸 수
    없는 까닭 · 파일 오류의 예외 종류), `size` 는 옮긴 바이트 수(실패면 0)다.
    """

    ok: bool
    reason: str = ""
    detail: str = ""
    size: int = 0


def _failed(reason: str, detail: str = "") -> S3Result:
    return S3Result(ok=False, reason=reason, detail=detail)


def in_module_test_run() -> bool:
    """모듈 시험(감시 러너) 안인가."""
    return bool(os.environ.get(module_registry.TEST_RUN_ENV_VAR, "").strip())


# --- BigDataQuery ------------------------------------------------------------------------------


def _day(value: date) -> date:
    """시각이 든 값(`datetime`)은 그 날로 — 앱의 조회 기간은 날 단위다."""
    return value.date() if isinstance(value, datetime) else value


def build_module_query(sql: object, start: object, end: object) -> str:
    """보낼 조회문 하나. 입력이 틀리면 `BigDataQueryError(QUERY_INPUT)`."""
    from capa_simulation.io.company_bigdataquery_adapter import QueryWindow

    if not isinstance(sql, str) or not sql.strip():
        raise BigDataQueryError(QUERY_INPUT, "조회문이 비었습니다.")
    if len(sql) > MAX_QUERY_CHARS:
        raise BigDataQueryError(QUERY_INPUT, f"조회문은 {MAX_QUERY_CHARS:,}자까지입니다.")
    present = [placeholder in sql for placeholder in _DATE_PLACEHOLDERS]
    if start is None and end is None:
        if any(present):
            raise BigDataQueryError(
                QUERY_INPUT,
                "조회문에 {start_date} · {end_date} 자리가 있는데 기간(start · end)이 없습니다.",
            )
        return sql
    if not isinstance(start, date) or not isinstance(end, date):
        raise BigDataQueryError(QUERY_INPUT, "기간은 start · end 를 날짜(date)로 함께 줍니다.")
    try:
        window = QueryWindow(start_date=_day(start), end_date=_day(end))
    except ValueError as error:
        raise BigDataQueryError(QUERY_INPUT, str(error)) from None
    if not all(present):
        raise BigDataQueryError(
            QUERY_INPUT,
            "기간을 주면 조회문에 {start_date} · {end_date} 자리가 둘 다 있어야 합니다.",
        )
    if window.days > MAX_QUERY_WINDOW_DAYS:
        raise BigDataQueryError(
            QUERY_INPUT,
            f"기간은 최대 {MAX_QUERY_WINDOW_DAYS}일입니다. 기간을 줄여 다시 조회하세요.",
        )
    start_bound, end_bound = window.sql_bounds()
    # `str.format` 을 쓰지 않는다 — 조회문의 다른 중괄호(JSON 함수 등)를 건드리지 않게.
    return sql.replace("{start_date}", start_bound).replace("{end_date}", end_bound)


def query_bigdataquery(
    module_id: str, sql: object, *, start: object = None, end: object = None
) -> pd.DataFrame:
    """모듈 `module_id` 의 조회 한 번 — 앱의 DB 등록과 같은 길로 묻고 표를 돌려준다(0행도)."""
    from capa_simulation.io import company_bigdataquery_adapter as adapter

    query = build_module_query(sql, start, end)
    if in_module_test_run():
        raise BigDataQueryError(
            QUERY_UNAVAILABLE,
            "모듈 시험에서는 BigDataQuery 를 부르지 않습니다 — 시험에서는 "
            "api.query_bigdataquery 를 갈아 끼웁니다(지침서 3-10).",
        )
    try:
        package = adapter.load_bigdataquery_module()
        frame = adapter.call_get_data(cast(adapter.BigDataQueryModule, package), query)
    except adapter.BigDataQueryCallError as error:
        _LOGGER.warning("모듈 %s BigDataQuery 실패 갈래=%s", module_id, error.kind)
        raise BigDataQueryError(error.kind, str(error)) from error
    except RuntimeError as error:
        # 패키지 없음 · 불러오기 실패 · 서버의 요청자 계정 없음 — 앱 관리자가 고칠 설정이다.
        _LOGGER.warning("모듈 %s BigDataQuery 쓸 수 없음", module_id)
        raise BigDataQueryError(QUERY_UNAVAILABLE, str(error)) from error
    if not isinstance(frame, pd.DataFrame):
        raise BigDataQueryError(
            adapter.QUERY_FAILURE_OTHER,
            "bigdataquery.getData() 반환값은 pandas DataFrame이어야 합니다.",
        )
    return frame


# --- S3 ----------------------------------------------------------------------------------------


def s3_object_key(module_id: str, name: str) -> str:
    """버킷 안 자리 — `modules/<id>/<name>`."""
    return f"{S3_KEY_PREFIX}{module_id}/{name}"


def valid_s3_name(name: object) -> bool:
    """모듈 데이터 파일 이름의 꼴(`_NAME_PART` 마디를 `/` 로 이은 것)."""
    if not isinstance(name, str) or not 0 < len(name) <= S3_NAME_MAX_LENGTH:
        return False
    parts = name.split("/")
    return len(parts) <= S3_NAME_MAX_PARTS and all(
        _NAME_PART.fullmatch(part) is not None for part in parts
    )


def _local_path(module_id: str, data_dir: Path, name: object) -> Path | S3Result:
    """`data_dir` 아래 그 이름의 자리, 또는 거절한 결과.

    꼴이 틀렸거나 따라간 자리(심볼릭 링크)가 밖이거나 링크가 고리를 이루면 「이름 거절」, 경로를
    따라가다 막히면(권한 등) 「파일 오류」 다.
    """
    if not module_registry.is_valid_module_id(module_id) or not valid_s3_name(name):
        return _failed(S3_NAME_REJECTED)
    assert isinstance(name, str)
    try:
        root = data_dir.resolve()
        place = (root / name).resolve()
    except RuntimeError:
        # 3.10 의 `Path.resolve` 는 링크 고리를 `RuntimeError` 로 알린다.
        return _failed(S3_NAME_REJECTED)
    except OSError as error:
        return _failed(S3_FILE_ERROR, type(error).__name__)
    if place == root or not place.is_relative_to(root):
        return _failed(S3_NAME_REJECTED)
    return place


def _transfer_deadline(size: int) -> float:
    return s3_small.REQUEST_DEADLINE_SECONDS + size / (_MIN_MIB_PER_SECOND * 1024 * 1024)


def _s3_target() -> tuple[S3Target | None, str]:
    """닿을 곳 한 벌 또는 쓸 수 없는 까닭(고정 낱말)."""
    from capa_simulation.auth import runtime
    from capa_simulation.io import object_storage

    if in_module_test_run():
        return None, UNAVAILABLE_TEST_RUN
    try:
        mode = object_storage.load_settings().mode
    except object_storage.StorageSettingsError:
        return None, UNAVAILABLE_SETTINGS
    if mode != object_storage.MODE_MANAGED:
        return None, UNAVAILABLE_NOT_MANAGED
    target = runtime.config().access_s3
    if target is None:
        return None, UNAVAILABLE_NO_TARGET
    return target, ""


def _transfer_failure(module_id: str, failure: s3_small.S3Failure, action: str) -> S3Result:
    if failure.kind == s3_small.KIND_TOO_LARGE:
        return _failed(S3_TOO_LARGE)
    label = _TRANSFER_LABELS.get(failure.kind, _TRANSFER_LABELS[s3_small.KIND_OTHER])
    _LOGGER.warning("모듈 %s S3 %s 실패: %s", module_id, action, label)
    return _failed(S3_TRANSFER_FAILED, label)


def s3_upload(module_id: str, data_dir: Path, name: object) -> S3Result:
    """`data_dir/<name>` 파일 하나를 버킷 `modules/<id>/<name>` 으로 올린다(있으면 덮는다)."""
    place = _local_path(module_id, data_dir, name)
    if isinstance(place, S3Result):
        return place
    assert isinstance(name, str)
    target, unavailable = _s3_target()
    if target is None:
        return _failed(S3_UNAVAILABLE, unavailable)
    try:
        if not place.is_file():
            return _failed(S3_NOT_FOUND)
        if place.stat().st_size > S3_MAX_BYTES:
            return _failed(S3_TOO_LARGE)
        body = place.read_bytes()
    except OSError as error:
        return _failed(S3_FILE_ERROR, type(error).__name__)
    if len(body) > S3_MAX_BYTES:
        return _failed(S3_TOO_LARGE)
    try:
        s3_small.put_object(
            target,
            s3_object_key(module_id, name),
            body,
            content_type=_CONTENT_TYPE,
            max_bytes=S3_MAX_BYTES,
            deadline_seconds=_transfer_deadline(len(body)),
        )
    except s3_small.S3Failure as failure:
        return _transfer_failure(module_id, failure, "올리기")
    return S3Result(ok=True, size=len(body))


def s3_download(module_id: str, data_dir: Path, name: object) -> S3Result:
    """버킷 `modules/<id>/<name>` 을 받아 `data_dir/<name>` 에 둔다(있으면 바꾼다).

    다 받은 뒤 같은 폴더의 임시 파일에서 한 번에 바꾼다 — 받다 끊겨도 있던 파일은 그대로다. 버킷에
    없으면 「파일 없음」 이고 로컬 파일은 건드리지 않는다.
    """
    place = _local_path(module_id, data_dir, name)
    if isinstance(place, S3Result):
        return place
    assert isinstance(name, str)
    target, unavailable = _s3_target()
    if target is None:
        return _failed(S3_UNAVAILABLE, unavailable)
    try:
        if place.is_dir():
            return _failed(S3_FILE_ERROR, S3_DETAIL_FOLDER)
    except OSError as error:
        return _failed(S3_FILE_ERROR, type(error).__name__)
    try:
        found = s3_small.get_object(
            target,
            s3_object_key(module_id, name),
            max_bytes=S3_MAX_BYTES,
            deadline_seconds=_transfer_deadline(S3_MAX_BYTES),
        )
    except s3_small.S3Failure as failure:
        return _transfer_failure(module_id, failure, "받기")
    if found is None:
        return _failed(S3_NOT_FOUND)
    try:
        place.parent.mkdir(parents=True, exist_ok=True)
        _replace_atomically(place, found.body)
    except OSError as error:
        return _failed(S3_FILE_ERROR, type(error).__name__)
    return S3Result(ok=True, size=len(found.body))


def _replace_atomically(place: Path, body: bytes) -> None:
    handle, temporary = tempfile.mkstemp(prefix=f".{place.name}.", dir=place.parent)
    staged = Path(temporary)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(body)
        os.replace(staged, place)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
