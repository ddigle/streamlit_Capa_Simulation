# Purpose: S3 호환 오브젝트 스토리지를 AWS CLI 로 호출하는 유일한 경계이며 명령 실행기를 주입받는다.

"""사내 S3 호환 스토리지(Dell ECS 로 추정)에 붙는 하나뿐인 경계.

`boto3` 가 아니라 `aws` CLI 를 `subprocess` 로 부른다. 엔드포인트·자격증명·CA 인증서 설정이
이미 CLI 프로필에 잡혀 있어 앱이 그것을 다시 짊어지지 않아도 되고, WebIDE 이관에서 걸림돌인
파이썬 의존성 용량도 늘지 않는다.

**모든 명령에 `--profile` 을 붙인다.** 네임스페이스가 프로필(자격증명)에 매여 있어서,
프로필이 빠지면 다른 네임스페이스를 보게 된다. 명령을 조립하는 자리를 `_argv()` 하나로
두어 빠질 수 없게 했다.

명령 실행기를 주입받는 이유는 `aws` 가 없는 개발 PC 에서도 **조립된 인자 배열을 그대로
검사**하기 위해서다. 사내에 옮겨 심기 전에 명령 형태만큼은 여기서 확정한다.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Literal, Protocol

from capa_simulation.settings import PROJECT_ROOT

# ---------------------------------------------------------------------------
# 사내 환경 설정 영역
#
# 1) 값은 환경변수로 덮어쓴다. WebIDE 로 옮겨 프로필명이 바뀌어도 코드를 고치지 않는다.
# 2) 버킷명에 대문자·언더바가 있어 경로 스타일 주소가 아니면 서명이 어긋난다.
# ---------------------------------------------------------------------------
DEFAULT_ENDPOINT_URL: Final = "http://s3.dataplatform.samsungds.net:9020"
DEFAULT_BUCKET: Final = "Capa_simulation_project"
DEFAULT_PROFILE: Final = "hoyeon.jeon-org-system_package_mfg_team"
DEFAULT_REGION: Final = "us-east-1"
# 네임스페이스는 프로필에 매여 있어 명령 인자로 넘기는 자리가 없다. 진단 출력에만 쓴다.
NAMESPACE_NOTE: Final = "org-system_package_mfg_team"

CONFIG_PATH: Final = PROJECT_ROOT / "config" / "object_storage.json"
CAPABILITIES_PATH: Final = PROJECT_ROOT / "config" / "object_storage_capabilities.json"

# AWS CLI 2.23.0 이상은 ECS 에서 `Missing required header for this request: Content-MD5` 로
# 실패한다(Dell KB 000299507). 체크섬 계산을 끄면 우회되는 경우가 있고, 안 되면 CLI 를
# 2.22.x 로 내려야 한다. 이 두 값이 이 경계에서 가장 먼저 확인할 항목이다.
FORCED_ENV: Final[Mapping[str, str]] = {
    "AWS_S3_ADDRESSING_STYLE": "path",
    "AWS_REQUEST_CHECKSUM_CALCULATION": "when_required",
    "AWS_RESPONSE_CHECKSUM_VALIDATION": "when_required",
    "AWS_DEFAULT_REGION": DEFAULT_REGION,
    "AWS_EC2_METADATA_DISABLED": "true",
    "AWS_PAGER": "",
    "AWS_RETRY_MODE": "standard",
    "AWS_MAX_ATTEMPTS": "3",
}

EXIT_CODE_MEANING: Final[Mapping[int, str]] = {
    0: "성공",
    1: "S3 전송 실패",
    2: "일부 파일이 전송에서 제외되었습니다(성공으로 보지 않습니다)",
    124: "제한 시간을 넘겼습니다",
    127: "aws 실행 파일을 찾지 못했습니다",
    130: "사용자 중단",
    252: "명령 문법 오류",
    253: "인자 오류",
    254: "서비스가 오류를 반환했습니다",
    255: "일반 오류",
}

DEFAULT_TIMEOUT_SECONDS: Final = 300.0
SMALL_TIMEOUT_SECONDS: Final = 60.0

SyncMode = Literal["local", "managed"]


@dataclass(frozen=True)
class StorageSettings:
    """이 경계가 쓰는 설정 한 벌."""

    mode: SyncMode
    endpoint_url: str
    bucket: str
    profile: str
    region: str
    capabilities: Mapping[str, object]


def load_settings(*, environ: Mapping[str, str] | None = None) -> StorageSettings:
    """환경변수 > `config/object_storage.json` > 모듈 상수 순으로 설정을 만든다.

    설정 파일이 있는데 읽지 못하면 `local` 로 강등하지 않는다 — 조용히 동기화를 꺼 버리면
    사용자는 저장이 올라간다고 믿는다.
    """
    env = os.environ if environ is None else environ
    file_config = _read_json(CONFIG_PATH, label="오브젝트 스토리지 설정")
    capabilities = _read_json(CAPABILITIES_PATH, label="스토리지 능력 파일") or {}
    values = file_config or {}
    mode_text = str(env.get("CAPA_S3_SYNC_MODE") or values.get("mode") or "local").strip()
    if mode_text not in ("local", "managed"):
        raise ObjectStorageError(
            f"CAPA_S3_SYNC_MODE 는 local 또는 managed 여야 합니다: {mode_text!r}"
        )
    mode: SyncMode = "managed" if mode_text == "managed" else "local"
    return StorageSettings(
        mode=mode,
        endpoint_url=str(
            env.get("CAPA_S3_ENDPOINT_URL") or values.get("endpoint_url") or DEFAULT_ENDPOINT_URL
        ),
        bucket=str(env.get("CAPA_S3_BUCKET") or values.get("bucket") or DEFAULT_BUCKET),
        profile=str(env.get("CAPA_S3_PROFILE") or values.get("profile") or DEFAULT_PROFILE),
        region=str(env.get("CAPA_S3_REGION") or values.get("region") or DEFAULT_REGION),
        capabilities=capabilities,
    )


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float


class CommandRunner(Protocol):
    def run(
        self, argv: Sequence[str], env: Mapping[str, str], *, timeout_seconds: float
    ) -> CommandResult: ...


@dataclass(frozen=True)
class SubprocessCommandRunner:
    """실제 `aws` 를 부르는 실행기. 이 저장소에서 `subprocess` 를 쓰는 유일한 자리다."""

    executable: str = "aws"

    def run(
        self, argv: Sequence[str], env: Mapping[str, str], *, timeout_seconds: float
    ) -> CommandResult:
        started = time.perf_counter()
        merged = {**os.environ, **env}
        try:
            completed = subprocess.run(  # noqa: S603 - 인자는 전부 코드가 만든다(shell=False)
                list(argv),
                env=merged,
                capture_output=True,
                text=True,
                check=False,
                shell=False,
                timeout=timeout_seconds,
            )
        except FileNotFoundError:
            return CommandResult(
                tuple(argv),
                127,
                "",
                "aws 실행 파일을 찾지 못했습니다.",
                time.perf_counter() - started,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                tuple(argv), 124, "", "제한 시간을 넘겼습니다.", time.perf_counter() - started
            )
        return CommandResult(
            tuple(argv),
            completed.returncode,
            completed.stdout or "",
            completed.stderr or "",
            time.perf_counter() - started,
        )


class ObjectStorageError(RuntimeError):
    """이 경계의 모든 실패. `BOOTSTRAP_ERRORS` 가 잡을 수 있도록 RuntimeError 를 상속한다."""

    def __init__(self, message: str, *, result: CommandResult | None = None) -> None:
        super().__init__(message)
        self._result = result

    @property
    def result(self) -> CommandResult | None:
        return self._result


@dataclass(frozen=True)
class ObjectRecord:
    key: str
    size_bytes: int
    etag: str
    last_modified: datetime | None


@dataclass(frozen=True)
class PutOutcome:
    key: str
    etag: str
    precondition_failed: bool


@dataclass(frozen=True)
class ObjectStorageClient:
    """S3 호환 스토리지에 붙는 클라이언트. 명령 조립은 전부 `_argv` 를 지난다."""

    settings: StorageSettings
    runner: CommandRunner = field(default_factory=SubprocessCommandRunner)
    sleep: Callable[[float], None] = time.sleep

    # ------------------------------------------------------------------ 진단
    def cli_version(self) -> str:
        result = self.runner.run(
            ["aws", "--version"], dict(FORCED_ENV), timeout_seconds=SMALL_TIMEOUT_SECONDS
        )
        if result.returncode != 0:
            raise ObjectStorageError(explain_failure(result), result=result)
        return (result.stdout or result.stderr).strip()

    def check_addressing_style(self) -> str:
        """경로 스타일 설정을 확인한다. 네트워크를 쓰지 않는다.

        버킷명에 대문자·언더바가 있어 가상 호스트 스타일로는 표현할 수 없다. 설정이 없으면
        환경변수로 강제하고 있음을 알린다.
        """
        result = self.runner.run(
            ["aws", "configure", "get", "s3.addressing_style", "--profile", self.settings.profile],
            dict(FORCED_ENV),
            timeout_seconds=SMALL_TIMEOUT_SECONDS,
        )
        configured = result.stdout.strip()
        return configured or "(설정 없음 · AWS_S3_ADDRESSING_STYLE=path 로 강제합니다)"

    # ------------------------------------------------------------------ 조회
    def list_objects(self, prefix: str, *, max_keys: int = 1000) -> tuple[ObjectRecord, ...]:
        result = self._run(
            self._argv(
                "list-objects-v2",
                "--prefix",
                prefix,
                "--max-keys",
                str(max_keys),
            ),
            timeout_seconds=SMALL_TIMEOUT_SECONDS,
        )
        payload = _parse_json(_required(result))
        contents = payload.get("Contents") or []
        records = []
        for item in contents:
            if not isinstance(item, dict):
                continue
            records.append(
                ObjectRecord(
                    key=str(item.get("Key", "")),
                    size_bytes=int(item.get("Size", 0)),
                    etag=str(item.get("ETag", "")).strip('"'),
                    last_modified=_parse_timestamp(item.get("LastModified")),
                )
            )
        return tuple(records)

    def head(self, key: str) -> ObjectRecord | None:
        result = self._run(
            self._argv("head-object", "--key", key),
            timeout_seconds=SMALL_TIMEOUT_SECONDS,
            allow_missing=True,
        )
        if result is None:
            return None
        payload = _parse_json(result)
        return ObjectRecord(
            key=key,
            size_bytes=int(payload.get("ContentLength", 0)),
            etag=str(payload.get("ETag", "")).strip('"'),
            last_modified=_parse_timestamp(payload.get("LastModified")),
        )

    def get_text(self, key: str, *, scratch_dir: Path) -> str:
        scratch_dir.mkdir(parents=True, exist_ok=True)
        destination = scratch_dir / f"download-{abs(hash(key)) % 10**8:08d}.json"
        self.get_file(key, destination)
        try:
            return destination.read_text(encoding="utf-8")
        finally:
            destination.unlink(missing_ok=True)

    def get_file(self, key: str, destination: Path) -> ObjectRecord:
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = self._run(
            self._argv("get-object", "--key", key, str(destination)),
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        )
        payload = _parse_json(_required(result))
        return ObjectRecord(
            key=key,
            size_bytes=int(payload.get("ContentLength", destination.stat().st_size)),
            etag=str(payload.get("ETag", "")).strip('"'),
            last_modified=_parse_timestamp(payload.get("LastModified")),
        )

    # ------------------------------------------------------------------ 쓰기
    def put_text(
        self, key: str, text: str, *, scratch_dir: Path, if_none_match: bool = False
    ) -> PutOutcome:
        scratch_dir.mkdir(parents=True, exist_ok=True)
        source = scratch_dir / f"upload-{abs(hash(key)) % 10**8:08d}.json"
        source.write_text(text, encoding="utf-8")
        try:
            return self.put_file(key, source, content_md5_base64=None, if_none_match=if_none_match)
        finally:
            source.unlink(missing_ok=True)

    def put_file(
        self,
        key: str,
        source: Path,
        *,
        content_md5_base64: str | None = None,
        metadata: Mapping[str, str] | None = None,
        if_none_match: bool = False,
    ) -> PutOutcome:
        args = ["put-object", "--key", key, "--body", str(source)]
        if content_md5_base64:
            args += ["--content-md5", content_md5_base64]
        if metadata:
            pairs = ",".join(
                f"{name}={sanitize_metadata_value(value)}"
                for name, value in sorted(metadata.items())
            )
            args += ["--metadata", pairs]
        if if_none_match:
            if not self.supports_conditional_put():
                raise ObjectStorageError(
                    "조건부 쓰기(--if-none-match)를 쓸 수 있는지 확인되지 않았습니다. "
                    "config/object_storage_capabilities.json 을 probe 로 먼저 채우세요."
                )
            args += ["--if-none-match", "*"]
        result = self._run(
            self._argv(*args),
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            allow_precondition_failed=True,
        )
        if result is None:
            return PutOutcome(key=key, etag="", precondition_failed=True)
        payload = _parse_json(result)
        return PutOutcome(
            key=key, etag=str(payload.get("ETag", "")).strip('"'), precondition_failed=False
        )

    def delete(self, key: str) -> None:
        self._run(self._argv("delete-object", "--key", key), timeout_seconds=SMALL_TIMEOUT_SECONDS)

    # ------------------------------------------------------------------ 능력
    def supports_conditional_put(self) -> bool:
        """확인하지 못한 능력은 없는 것으로 본다."""
        return bool(self.settings.capabilities.get("conditional_put_if_none_match_star", False))

    # ------------------------------------------------------------------ 내부
    def _argv(self, operation: str, *args: str) -> list[str]:
        """`aws s3api` 명령 하나를 조립한다. **`--profile` 이 빠질 수 없는 유일한 자리다.**"""
        return [
            "aws",
            "s3api",
            operation,
            "--bucket",
            self.settings.bucket,
            "--endpoint-url",
            self.settings.endpoint_url,
            "--profile",
            self.settings.profile,
            "--output",
            "json",
            *args,
        ]

    def _run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float,
        retries: int = 2,
        allow_missing: bool = False,
        allow_precondition_failed: bool = False,
    ) -> CommandResult | None:
        last: CommandResult | None = None
        for attempt in range(retries + 1):
            result = self.runner.run(argv, dict(FORCED_ENV), timeout_seconds=timeout_seconds)
            last = result
            if result.returncode == 0:
                return result
            if allow_missing and _is_not_found(result):
                return None
            if allow_precondition_failed and _is_precondition_failed(result):
                return None
            if not _is_retryable(result) or attempt == retries:
                break
            self.sleep(min(2.0**attempt, 8.0))
        assert last is not None
        raise ObjectStorageError(explain_failure(last), result=last)


def explain_failure(result: CommandResult) -> str:
    """실패를 사람이 읽는 한 줄로 바꾼다. ECS 비호환은 원인을 짚어 준다."""
    meaning = EXIT_CODE_MEANING.get(result.returncode, f"종료코드 {result.returncode}")
    detail = (result.stderr or result.stdout).strip().splitlines()
    head = detail[0] if detail else ""
    message = f"오브젝트 스토리지 명령이 실패했습니다({meaning}). {head}"
    if result.argv:
        # 사내에서 원격으로 진단할 때 이 한 줄이 있고 없고가 크다. 인자에 자격증명이
        # 들어가지 않으므로 그대로 보여도 된다.
        message += "\n  실행한 명령: " + command_line(result.argv)
    if "Content-MD5" in (result.stderr or ""):
        message += (
            " · AWS CLI 2.23.0 이상과 ECS 의 알려진 비호환일 수 있습니다(Dell KB 000299507). "
            "체크섬 옵트아웃이 적용됐는지 확인하고, 그래도 나면 CLI 를 2.22.x 로 내리세요."
        )
    return message


def command_line(argv: Sequence[str]) -> str:
    """진단 출력용 문자열. 자격증명이 인자에 들어가지 않으므로 그대로 보여도 된다."""
    return " ".join(shlex.quote(item) for item in argv)


def sanitize_metadata_value(value: str) -> str:
    """`x-amz-meta-*` 는 ASCII 만 받는다. 한글 메모가 들어가면 요청 자체가 거부된다."""
    return "".join(character if 32 <= ord(character) < 127 else "_" for character in value)


def assert_single_put_etag(etag: str, *, local_md5_hex: str) -> None:
    """단일 PUT 의 ETag 는 MD5 다. 다르면 전송 중 내용이 바뀐 것이다.

    멀티파트 업로드의 ETag 는 `-` 를 포함하고 MD5 가 아니므로 검사를 건너뛴다.
    """
    if "-" in etag:
        return
    if etag and etag.lower() != local_md5_hex.lower():
        raise ObjectStorageError(
            f"업로드한 객체의 ETag({etag})가 로컬 MD5({local_md5_hex})와 다릅니다."
        )


def _required(result: CommandResult | None) -> CommandResult:
    """성공만 돌려주는 경로에서 `None` 이 올 수 없음을 타입으로도 못박는다."""
    if result is None:
        raise ObjectStorageError("명령이 결과 없이 끝났습니다.")
    return result


def _read_json(path: Path, *, label: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObjectStorageError(f"{label}을 읽지 못했습니다: {path}") from exc
    if not isinstance(payload, dict):
        raise ObjectStorageError(f"{label}이 JSON 객체가 아닙니다: {path}")
    return payload


def _parse_json(result: CommandResult) -> dict[str, Any]:
    text = result.stdout.strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ObjectStorageError("aws 응답을 JSON 으로 읽지 못했습니다.", result=result) from exc
    return payload if isinstance(payload, dict) else {}


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_not_found(result: CommandResult) -> bool:
    text = (result.stderr or "") + (result.stdout or "")
    return "404" in text or "Not Found" in text or "NoSuchKey" in text


def _is_precondition_failed(result: CommandResult) -> bool:
    text = (result.stderr or "") + (result.stdout or "")
    return "PreconditionFailed" in text or "412" in text or "409" in text


def _is_retryable(result: CommandResult) -> bool:
    """다시 걸어 볼 만한 실패인지. 설정·문법 오류는 몇 번을 걸어도 같다."""
    if result.returncode in (127, 252, 253):
        return False
    text = (result.stderr or "").lower()
    if "credential" in text or "access denied" in text or "invalidaccesskeyid" in text:
        return False
    return True
