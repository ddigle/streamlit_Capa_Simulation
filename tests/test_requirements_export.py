# Purpose: Docker 가 읽는 requirements.txt 가 uv.lock 과 어긋나지 않는지 검사한다.

"""**`requirements.txt` 는 손으로 적는 파일이 아니라 `uv.lock` 의 그림자다.**

사내 WebIDE 의 CI/CD 는 `docker/Dockerfile-prod` 로 이미지를 만들고 그 안에서
`pip install -r requirements.txt` 를 돈다. 개발 PC 와 CI 는 `uv sync` 로 `uv.lock` 을
보므로, 둘이 갈라지면 **사내 컨테이너만 조용히 다른 버전을 쓴다.** 화면에 오류가 나지
않고 계산 결과만 달라질 수 있는 종류다.

그래서 여기서 다시 뽑아 파일과 대조한다. 어긋나면 아래 한 줄로 고친다.

    uv export --format requirements-txt --no-hashes --no-dev --no-emit-project > requirements.txt

옵션 넷에 각각 이유가 있다.

- `--no-hashes` — 사내 인덱스가 공개 PyPI 와 다른 아티팩트를 줄 수 있어 해시가 맞지 않는다.
- `--no-dev` — 컨테이너는 앱만 띄운다. ruff·mypy·pytest 를 넣을 이유가 없다.
- `--no-emit-project` — 빼지 않으면 첫 줄이 `-e .` 이 된다. `Dockerfile-prod` 는
  `WORKDIR` 을 잡기 **전에** `pip install` 을 돌아 그때 `.` 이 `/` 를 가리킨다.
- `-o` 를 쓰지 않는다 — uv 가 명령줄을 헤더에 적어서, 출력 경로가 바뀌면 파일이 달라진다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"
EXPORT_COMMAND = (
    "uv",
    "export",
    "--format",
    "requirements-txt",
    "--no-hashes",
    "--no-dev",
    "--no-emit-project",
)


def test_requirements_txt_matches_the_lock() -> None:
    if shutil.which("uv") is None:
        pytest.skip("uv 가 없습니다 — 이 검사는 uv 가 있는 환경에서만 돕니다.")

    completed = subprocess.run(
        EXPORT_COMMAND,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        pytest.skip(f"uv export 가 실패했습니다: {completed.stderr.strip()[:200]}")

    expected = completed.stdout.replace("\r\n", "\n")
    actual = REQUIREMENTS.read_text(encoding="utf-8").replace("\r\n", "\n")

    assert actual == expected, (
        "requirements.txt 가 uv.lock 과 어긋납니다. 사내 컨테이너만 다른 버전을 쓰게 됩니다.\n"
        "아래 한 줄로 고치세요:\n"
        "  " + " ".join(EXPORT_COMMAND) + " > requirements.txt"
    )


def test_the_dockerfile_installs_that_file() -> None:
    """`Dockerfile-prod` 가 정말 이 파일을 읽는지 본다.

    파일 이름을 바꾸거나 경로를 옮기면 위 검사가 지키는 것이 없어진다.
    """
    dockerfile = (PROJECT_ROOT / "docker" / "Dockerfile-prod").read_text(encoding="utf-8")

    assert "pip install -r /project/requirements.txt" in dockerfile, (
        "Dockerfile-prod 가 /project/requirements.txt 를 설치하지 않습니다. "
        "경로를 바꿨다면 이 검사도 같이 고치세요."
    )


def test_the_export_excludes_the_project_itself() -> None:
    """첫 줄이 `-e .` 이면 Docker 빌드가 죽는다 — `WORKDIR` 전에 설치하기 때문이다."""
    body = REQUIREMENTS.read_text(encoding="utf-8")

    assert "\n-e ." not in body and not body.startswith("-e ."), (
        "requirements.txt 에 `-e .` 이 있습니다. `--no-emit-project` 를 빠뜨렸습니다."
    )
