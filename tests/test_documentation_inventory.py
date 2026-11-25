# Purpose: 소스 모듈 · 한 벌 공용 도우미의 문서 등재와 모듈 색인이 생성기 출력과 같은지 검사한다.

import importlib
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_module_index import main, render_index, tracked_modules  # noqa: E402

AGENTS = PROJECT_ROOT / "AGENTS.md"
RULES_DIR = PROJECT_ROOT / "docs" / "rules"
FILE_REFERENCE_DIR = PROJECT_ROOT / "docs" / "reference" / "files"
MODULE_INDEX = PROJECT_ROOT / "docs" / "reference" / "module_index.md"

# 화면 모듈이 사본을 두지 않고 부르는 한 벌 도우미(모듈, 이름). 문서가 이 이름을 적지 않으면 다음
# 기여자가 문서만 보고 사본을 다시 만든다 — 사본 넷을 하나로 모은 뒤에도 문서가 옛 한 벌만 적어
# 두었던 일이 있다(2026-11-02 조립 리뷰). 새로 한 벌로 모으면 여기와 그 이름을 적는 손 글
# 문서를 함께 고친다.
SHARED_HELPERS = (
    ("capa_simulation.settings", "format_month"),
    ("capa_simulation.services.month_columns", "month_label"),
    ("capa_simulation.services.month_columns", "iso_month_text"),
    ("capa_simulation.services.frame_contracts", "require_exact_columns"),
    ("capa_simulation.services.frame_contracts", "blank_cell"),
    ("capa_simulation.home_state", "home_toggle"),
    ("capa_simulation.components.constraint_simulation_figures", "percent_or_none"),
    ("capa_simulation.components.constraint_simulation_figures", "axis_bounds"),
    ("capa_simulation.components.profile_caption", "render_row_value"),
    ("capa_simulation.components.profile_caption", "render_heading_value"),
    ("capa_simulation.components.table_toolbar", "file_name_part"),
    ("capa_simulation.korea_time", "kst_clock"),
    ("capa_simulation.components.percent_cells", "percent_column"),
    ("capa_simulation.components.percent_cells", "percent_table"),
    ("capa_simulation.components.percent_cells", "percent_progress_column"),
    ("capa_simulation.services.product_parts", "product_part_label"),
    ("capa_simulation.services.product_parts", "part_merged_columns"),
)


def _tracked_modules() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "*.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=PROJECT_ROOT,
        check=True,
    ).stdout.split()
    return [
        path
        for path in listed
        if (path == "app.py" or path.startswith(("app_pages/", "src/capa_simulation/")))
        and not path.endswith("__init__.py")
    ]


def _hand_written_documents() -> list[Path]:
    """손 글 개발 문서 — AGENTS.md 색인 · 규칙(`docs/rules/`) · 파일별 책임
    (`docs/reference/files/`). 폴더마다 정렬해 잇는다. 폴더가 비면 읽을 글이 줄어 조용히
    통과하므로 멈춘다.
    """
    rules = sorted(RULES_DIR.glob("*.md"))
    references = sorted(FILE_REFERENCE_DIR.glob("*.md"))
    assert rules, "docs/rules/*.md 를 찾지 못했습니다."
    assert references, "docs/reference/files/*.md 를 찾지 못했습니다."
    return [AGENTS, *rules, *references]


def _joined(paths: list[Path]) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def test_agents_documents_every_source_module() -> None:
    """파일별 책임을 손으로만 유지하면 반드시 뒤처진다. 누락을 자동으로 잡는다.

    읽는 곳은 손 글 문서와 생성 색인 `docs/reference/module_index.md` 다. 색인 생성기는 이
    시험과 따로 모듈을 거르므로, 생성기가 모듈을 빠뜨리면 여기서 잡힌다(색인이 최신인지는
    아래 시험이 본다).
    경로 전체(`src/...`)로 적어도 되고 디렉터리를 줄인 표기(`persistence/repository.py`)나
    파일명만(`load_calculator.py`) 적어도 된다. 어떤 형태로든 언급만 되어 있으면 통과한다.
    """
    document = _joined([*_hand_written_documents(), MODULE_INDEX])
    modules = _tracked_modules()
    assert modules, "추적 소스 모듈을 찾지 못했습니다."
    missing = [
        module for module in modules if module not in document and Path(module).name not in document
    ]

    assert not missing, (
        "개발 문서(AGENTS.md · docs/rules · docs/reference/files · 모듈 색인)에 등재되지 "
        "않은 모듈이 있습니다. 새 모듈을 만들면 같은 변경에서 scripts/build_module_index.py 로 "
        "색인을 갱신합니다:\n" + "\n".join(missing)
    )


def test_the_module_index_is_the_generators_output() -> None:
    """생성 색인은 지금 추적 모듈로 다시 만든 글과 바이트까지 같다.

    모듈을 더하거나 지우거나 옮기고 생성기를 돌리지 않으면 여기서 실패한다. 생성기의 거르기는
    이 파일의 `_tracked_modules()` 와 같아야 한다.
    """
    modules = tracked_modules()
    assert modules, "생성기가 추적 모듈을 찾지 못했습니다."
    assert modules == sorted(_tracked_modules()), "생성기의 거르기가 이 시험의 거르기와 다릅니다."
    assert MODULE_INDEX.read_bytes() == render_index(modules).encode("utf-8"), (
        "docs/reference/module_index.md 가 추적 모듈 목록과 다릅니다. "
        "scripts/build_module_index.py 를 돌려 함께 커밋합니다."
    )
    assert main(["--check"]) == 0


def _git(root: Path, *argv: str) -> None:
    subprocess.run(["git", *argv], cwd=root, check=True, capture_output=True)


def test_the_module_index_generator_writes_then_check_passes_and_a_new_module_fails(
    tmp_path: Path,
) -> None:
    for name in (
        "app.py",
        "app_pages/demo_page.py",
        "src/capa_simulation/__init__.py",
        "src/capa_simulation/demo_core.py",
        "scripts/demo_tool.py",
        "tests/test_demo.py",
    ):
        place = tmp_path / name
        place.parent.mkdir(parents=True, exist_ok=True)
        place.write_text("# Purpose: 합성 견본.\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")

    assert tracked_modules(tmp_path) == [
        "app.py",
        "app_pages/demo_page.py",
        "src/capa_simulation/demo_core.py",
    ]
    assert main(["--check"], root=tmp_path) == 1
    assert main([], root=tmp_path) == 0
    assert main(["--check"], root=tmp_path) == 0

    (tmp_path / "src/capa_simulation/demo_more.py").write_text(
        "# Purpose: 합성 견본.\n", encoding="utf-8"
    )
    _git(tmp_path, "add", "src/capa_simulation/demo_more.py")
    assert main(["--check"], root=tmp_path) == 1


def test_agents_names_every_shared_helper() -> None:
    """한 벌 도우미는 코드에 있고 손 글 개발 문서에 이름으로 적혀 있다.

    생성 색인은 읽지 않는다 — 사람이 규칙 자리에 그 이름을 적었는지를 보는 시험이다.
    """
    document = _joined(_hand_written_documents())
    for module_name, helper in SHARED_HELPERS:
        assert callable(getattr(importlib.import_module(module_name), helper)), helper
    missing = [
        f"{module_name}.{helper}"
        for module_name, helper in SHARED_HELPERS
        if not re.search(rf"\b{re.escape(helper)}\b", document)
    ]
    assert not missing, (
        "개발 문서(AGENTS.md · docs/rules · docs/reference/files)가 한 벌 도우미를 적지 "
        "않았습니다. 사본을 하나로 모으면 같은 변경에서 그 이름을 규칙 자리에 적습니다:\n"
        + "\n".join(missing)
    )
