# Purpose: 모든 소스 모듈과 한 벌로 둔 공용 도우미가 AGENTS.md 에 등재되어 있는지 검사한다.

import importlib
import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENTS = PROJECT_ROOT / "AGENTS.md"

# 화면 모듈이 사본을 두지 않고 부르는 한 벌 도우미(모듈, 이름). 문서가 이 이름을 적지 않으면 다음
# 기여자가 문서만 보고 사본을 다시 만든다 — 사본 넷을 하나로 모은 뒤에도 문서가 옛 한 벌만 적어
# 두었던 일이 있다(2026-11-02 조립 리뷰). 새로 한 벌로 모으면 여기와 AGENTS 를 함께 고친다.
SHARED_HELPERS = (
    ("capa_simulation.settings", "format_month"),
    ("capa_simulation.services.month_columns", "month_label"),
    ("capa_simulation.services.month_columns", "iso_month_text"),
    ("capa_simulation.services.frame_contracts", "require_exact_columns"),
    ("capa_simulation.services.frame_contracts", "blank_cell"),
    ("capa_simulation.home_state", "home_toggle"),
)


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


def test_agents_names_every_shared_helper() -> None:
    """한 벌 도우미는 코드에 있고 AGENTS 에 이름으로 적혀 있다."""
    document = AGENTS.read_text(encoding="utf-8")
    for module_name, helper in SHARED_HELPERS:
        assert callable(getattr(importlib.import_module(module_name), helper)), helper
    missing = [
        f"{module_name}.{helper}"
        for module_name, helper in SHARED_HELPERS
        if not re.search(rf"\b{re.escape(helper)}\b", document)
    ]
    assert not missing, (
        "AGENTS.md 가 한 벌 도우미를 적지 않았습니다. 사본을 하나로 모으면 같은 변경에서 그 이름을 "
        "규칙 자리에 적습니다:\n" + "\n".join(missing)
    )
