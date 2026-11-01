# Purpose: 사내 모듈 뼈대가 제 폴더 안에만 넷을 만들고 거절하면 아무것도 쓰지 않음을 고정한다.

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from capa_simulation import module_registry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import check_module  # noqa: E402
import new_module  # noqa: E402

EXPECTED_FILES = {
    "module.json",
    "page.py",
    "tests/test_demo_new_smoke.py",
    "README.md",
}


def _tree(base: Path) -> set[str]:
    return {path.relative_to(base).as_posix() for path in base.rglob("*")}


def _make(tmp_path: Path, *extra: str, module_id: str = "demo_new") -> int:
    return new_module.main(
        [module_id, "--name", "데모 새 모듈", "--root", str(tmp_path / "modules"), *extra]
    )


def test_the_skeleton_writes_four_files_inside_its_own_folder_only(tmp_path: Path) -> None:
    (tmp_path / "elsewhere").mkdir()
    before = _tree(tmp_path)

    assert _make(tmp_path) == 0

    folder = tmp_path / "modules" / "demo_new"
    written = {path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()}
    assert written == EXPECTED_FILES
    outside = _tree(tmp_path) - before
    assert {item for item in outside if not item.startswith("modules/demo_new")} == {"modules"}
    assert not (tmp_path / "modules" / "demo_new" / "data").exists()
    for rel in EXPECTED_FILES:
        assert b"\r\n" not in (folder / rel).read_bytes(), f"{rel} 는 LF 로 쓴다"


def test_the_written_manifest_reads_as_an_enabled_l0_module(tmp_path: Path) -> None:
    assert _make(tmp_path, "--owner", "데모 담당", "--title", "데모 첫 화면") == 0

    folder = tmp_path / "modules" / "demo_new"
    manifest = module_registry.read_manifest(folder)
    assert manifest.id == "demo_new"
    assert manifest.enabled is True
    assert manifest.maturity == "L0"
    assert manifest.api == module_registry.API_MAJOR
    assert manifest.owner == "데모 담당"
    assert [(page.slug, page.file, page.title) for page in manifest.pages] == [
        ("main", "page.py", "데모 첫 화면")
    ]
    assert module_registry.page_problems(folder, manifest) == []
    scan = module_registry.scan_modules(tmp_path / "modules")
    assert [(record.folder_name, record.state) for record in scan.records] == [("demo_new", "on")]


def test_the_skeleton_shows_the_wrapped_callback_and_the_empty_data_root(tmp_path: Path) -> None:
    assert _make(tmp_path) == 0

    folder = tmp_path / "modules" / "demo_new"
    page = (folder / "page.py").read_text(encoding="utf-8")
    smoke = (folder / "tests" / "test_demo_new_smoke.py").read_text(encoding="utf-8")
    assert "on_click=ctx.callback(_greet)" in page
    assert page.startswith("# Purpose: ")
    assert 'monkeypatch.setenv("CAPA_MODULES_DATA_ROOT"' in smoke
    assert smoke.startswith("# Purpose: ")
    assert "docs/module_guide.md" in (folder / "README.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("module_id", ["Demo", "demo__x", "1abc", "a", "import", "demo_"])
def test_ids_outside_the_rule_are_refused_without_writing(tmp_path: Path, module_id: str) -> None:
    assert _make(tmp_path, module_id=module_id) == 2
    assert not (tmp_path / "modules").exists()


def test_an_existing_folder_is_refused_and_left_alone(tmp_path: Path) -> None:
    folder = tmp_path / "modules" / "demo_new"
    folder.mkdir(parents=True)
    (folder / "keep.txt").write_text("담당자 파일", encoding="utf-8")

    assert _make(tmp_path) == 2
    assert _tree(folder) == {"keep.txt"}


def test_a_root_not_named_modules_is_refused(tmp_path: Path) -> None:
    code = new_module.main(["demo_new", "--name", "데모", "--root", str(tmp_path / "plugins")])
    assert code == 2
    assert not (tmp_path / "plugins").exists()


@pytest.mark.parametrize("title", ["HOME", "생산 계획", module_registry.GROUP_MAIN_TITLE])
def test_titles_the_core_already_uses_are_refused(tmp_path: Path, title: str) -> None:
    assert _make(tmp_path, "--title", title) == 2
    assert not (tmp_path / "modules").exists()


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--title", "**굵게**"),
        ("--title", ":red[빨강]"),
        ("--title", "가" * 25),
        ("--name", "가" * 31),
        ("--owner", ""),
    ],
)
def test_names_and_titles_outside_the_manifest_rule_are_refused(
    tmp_path: Path, option: str, value: str
) -> None:
    assert _make(tmp_path, option, value) == 2
    assert not (tmp_path / "modules").exists()


def test_a_quote_in_the_title_still_gives_ruff_clean_files(tmp_path: Path) -> None:
    assert _make(tmp_path, "--title", '데모 "따옴표" 화면') == 0
    folder = tmp_path / "modules" / "demo_new"
    assert "'데모 \"따옴표\" 화면'" in (folder / "page.py").read_text(encoding="utf-8")
    assert (
        json.loads((folder / "module.json").read_text(encoding="utf-8"))["pages"][0]["title"]
        == '데모 "따옴표" 화면'
    )
    ruff = check_module.run_ruff(folder, PROJECT_ROOT)
    assert ruff.failure == ""
    assert ruff.total == 0, [finding.text() for finding in ruff.findings]


def test_the_skeleton_passes_check_module_with_ruff_and_its_smoke_test(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _make(tmp_path) == 0
    capsys.readouterr()

    code = check_module.main(["demo_new", "--root", str(tmp_path / "modules")])

    out = capsys.readouterr().out
    assert code == 0, out
    assert (
        "- m1 demo_new 통과 · L0 · API 1.0 · 화면 1 · 오류 0 · 경고 0 · ruff ok · 시험 1 통과"
        in out
    )
    assert "전송용 요약: 모듈 1 = 통과 1 + 꺼짐 0 + 실패 0; api1 1; 패키지 없음; ng 없음" in out
