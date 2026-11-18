# Purpose: C-DEP 진입점의 런타임 전 길이 사용자 컴포넌트를 등록하는 화면 조각을 부르지 않게 지킨다.

"""Guard the pre-runtime import path of `capa_server.py`.

`capa_server.py` 는 `st.App` 을 만들기 **전에** 통합인증 · 감사 기록 · 동기화 일꾼을 세운다.
그때는 Streamlit 런타임이 없어서, 그 길에서 `st.components.v2.component(...)` 를 부르는 모듈을
불러오면 컴포넌트가 버리는 관리자에 등록되고 앱이 첫 화면에서 「Component … is not registered」 로
멈춘다. `app.py` 로 띄우는 개발 · 시험 · 화면 확인에서는 드러나지 않아 이 시험이 그물이다.

하위 프로세스가 진입 파일을 **그대로 import** 한다 — import 줄을 시험에 옮겨 적으면 진입 파일에 더한
줄이 그물 밖에 남는다(통합인증 · 명단 환경변수는 빼서 꺼짐 기동이다).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 진입 파일을 그대로 import 하고(모듈 수준 기동 전부) 감사 기동이 늦게 부르는 함수를 더 부른다.
PRE_RUNTIME = """
import json
import sys

import capa_server
from capa_simulation.audit.boot import deploy_version

deploy_version()
print(json.dumps(sorted(name for name in sys.modules if name.startswith("capa_simulation"))))
"""

COMPONENT_MARK = "components.v2.component("


def _loaded_modules() -> list[str]:
    env = {
        key: value for key, value in os.environ.items() if not key.startswith(("CAPA_", "ADFS_"))
    }
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    done = subprocess.run(
        [sys.executable, "-c", PRE_RUNTIME],
        capture_output=True,
        text=True,
        env=env,
        cwd=PROJECT_ROOT,
        timeout=120,
        check=True,
    )
    return list(json.loads(done.stdout.strip().splitlines()[-1]))


def _source(module: str) -> str:
    relative = Path(*module.split("."))
    for candidate in (
        PROJECT_ROOT / "src" / relative.with_suffix(".py"),
        PROJECT_ROOT / "src" / relative / "__init__.py",
    ):
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    return ""


def test_the_server_start_path_registers_no_custom_component_before_the_runtime() -> None:
    loaded = _loaded_modules()

    offenders = [module for module in loaded if COMPONENT_MARK in _source(module)]

    assert "capa_simulation.deploy_stamp" in loaded
    assert offenders == []


def test_the_deploy_stamp_is_read_without_screen_pieces() -> None:
    source = _source("capa_simulation.deploy_stamp")

    assert "streamlit" not in source
    assert "capa_simulation.components" not in source.split('"""', 2)[-1]
