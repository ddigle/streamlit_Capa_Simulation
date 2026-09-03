# Purpose: 모든 소스 모듈이 AGENTS.md 파일별 책임에 등재되어 있는지 검사한다.

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENTS = PROJECT_ROOT / "AGENTS.md"


def _tracked_modules() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "*.py"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=True,
    ).stdout.split()
    return [
        path
        for path in listed
        if (path == "app.py" or path.startswith(("app_pages/", "src/capa_simulation/")))
        and not path.endswith("__init__.py")
    ]


def test_agents_documents_every_source_module() -> None:
    """§3 파일별 책임을 손으로 유지하면 반드시 뒤처진다. 누락을 자동으로 잡는다.

    경로 전체(`src/...`)로 적어도 되고 디렉터리를 줄인 표기(`persistence/repository.py`)나
    파일명만(`load_calculator.py`) 적어도 된다. 어떤 형태로든 언급만 되어 있으면 통과한다.
    """
    document = AGENTS.read_text(encoding="utf-8")
    missing = [
        module
        for module in _tracked_modules()
        if module not in document and Path(module).name not in document
    ]

    assert not missing, (
        "AGENTS.md 3장 「파일별 책임」에 등재되지 않은 모듈이 있습니다. "
        "새 모듈을 만들면 같은 변경에서 문서도 갱신합니다:\n" + "\n".join(missing)
    )
