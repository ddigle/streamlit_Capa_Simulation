# Purpose: 사내 모듈 지침서가 창구·점검 규칙·뼈대·예시·점검 출력·환경변수·권한 설정과 같은지 본다.

"""지침서(`docs/module_guide.md`)와 코드 맞대기.

지침서는 동료(담당자)의 에이전트가 받는 유일한 문서다. 사외는 사내 모듈을 볼 수 없어, 지침서의
이름·예시·출력이 코드와 어긋나면 그 어긋남이 사내에서 처음 드러난다. 그래서 지침서에 옮겨 적은 것
가운데 코드로 따질 수 있는 것은 여기서 코드에 댄다 — 창구 이름(부록 A), 규칙 번호(부록 B ·
4장 · 7장), 뼈대 화면(3-7), 예시 모듈(3-8 · 3-9 — 정적 규칙을 통과해야 한다), 점검 출력 꼴(부록 B),
환경변수(9-2), 담당자 클론 설정(8-4)과 배포 적용 템플릿.
"""

from __future__ import annotations

import dataclasses
import json
import re
import sys
import textwrap
from pathlib import Path

import pytest

from capa_simulation import module_api, module_registry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GUIDE_PATH = PROJECT_ROOT / "docs" / "module_guide.md"
SETTINGS_TEMPLATE = PROJECT_ROOT / "docs" / "internal_claude_settings.json"
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import check_deploy_screens  # noqa: E402
import check_module  # noqa: E402
import module_check_rules as rules  # noqa: E402
import new_module  # noqa: E402

GUIDE = GUIDE_PATH.read_text(encoding="utf-8")
ENVIRONMENT = rules.load_environment(PROJECT_ROOT)
_FENCE = re.compile(r"^(?P<indent>[ ]*)```(?P<lang>\w*)\n(?P<body>.*?)^(?P=indent)```", re.S | re.M)
_RULE_ROW = re.compile(r"^\| (M\d{2}) \|", re.M)
_NAME_CELL = re.compile(r"^\| `([A-Za-z_]+)` \|", re.M)
# 부록 B 의 점검 출력 예시에서 고장 난 모듈 — 뼈대 화면 끝에 폐기 예정 인자 한 줄을 더한 것이다.
_DRAFT_EXTRA_LINE = 'st.dataframe({"값": [1, 2]}, use_container_width=True)\n'


def _headings() -> list[tuple[int, int, str]]:
    """(줄 번호, 층위, 제목) — 코드 블록 안의 `#` 줄(파이썬 주석 등)은 머리가 아니다."""
    found: list[tuple[int, int, str]] = []
    fenced = False
    for index, line in enumerate(GUIDE.splitlines()):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            found.append((index, level, line.lstrip("#").strip()))
    return found


def _section(heading: str) -> str:
    """`heading` 으로 시작하는 머리부터 같거나 높은 층위의 다음 머리 앞까지."""
    lines = GUIDE.splitlines(keepends=True)
    headings = _headings()
    position = next(n for n, (_, _, title) in enumerate(headings) if title.startswith(heading))
    start, level, _ = headings[position]
    end = next(
        (index for index, depth, _ in headings[position + 1 :] if depth <= level), len(lines)
    )
    return "".join(lines[start:end])


def _blocks(text: str, lang: str) -> list[str]:
    """`text` 안의 `lang` 코드 블록(목록 안이라 들여 쓴 것은 들여쓰기를 걷는다)."""
    return [
        textwrap.dedent(match["body"]) for match in _FENCE.finditer(text) if match["lang"] == lang
    ]


def _python_block(purpose_start: str) -> str:
    """첫 줄이 `# Purpose: <purpose_start>…` 인 파이썬 블록 하나."""
    found = [
        block
        for block in _blocks(GUIDE, "python")
        if block.startswith(f"# Purpose: {purpose_start}")
    ]
    assert len(found) == 1, (purpose_start, len(found))
    return found[0]


def _write(folder: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return folder


def _static_findings(folder: Path) -> list[rules.Finding]:
    manifest = module_registry.read_manifest(folder)
    result = rules.check_module_folder(
        folder,
        module_id=manifest.id,
        pages=[page.file for page in manifest.pages],
        environment=ENVIRONMENT,
        git=None,
    )
    return result.findings


def _demo_memo(root: Path) -> Path:
    """3-8 의 다섯 파일을 그대로 옮긴 모듈(선언은 3-3 의 예시)."""
    return _write(
        root / "demo_memo",
        {
            "module.json": _blocks(_section("3-3."), "json")[0],
            "store.py": _python_block("데모 메모 모듈의 메모 파일"),
            "cache.py": _python_block("데모 메모 모듈의 캐시"),
            "page.py": _python_block("데모 메모 모듈의 첫 화면"),
            "tests/test_demo_memo_page.py": _python_block("데모 메모 화면이"),
        },
    )


def test_appendix_a_lists_the_module_api_surface_in_order() -> None:
    appendix = _section("부록 A")
    surface, _, members = appendix.partition("`ModuleContext` 의 칸과 메서드")

    assert _NAME_CELL.findall(surface) == module_api.__all__
    fields = [field.name for field in dataclasses.fields(module_api.ModuleContext)]
    methods = [
        name
        for name in vars(module_api.ModuleContext)
        if not name.startswith("_") and name not in fields
    ]
    assert _NAME_CELL.findall(members) == [*fields, *methods]
    assert f"`{module_api.API_VERSION!r}`" in surface
    assert "`" + repr(module_api.PALETTE_KEYS).replace("'", '"') + "`" in surface
    assert f'`"{module_api.IMPLEMENTING_SUFFIX}"`' in surface


def test_appendix_c_first_version_names_every_surface_name() -> None:
    record = _section("부록 C")
    major, minor = module_api.API_VERSION

    assert f"| v{major}.{minor} |" in record
    for name in [*module_api.__all__, "key", "data_dir", "callback", "guard"]:
        assert f"`{name}`" in record, name


def test_rule_numbers_in_the_guide_are_the_checkers_rules() -> None:
    appendix_rules = set(_RULE_ROW.findall(_section("부록 B")))
    conflict_rules = set(re.findall(r"M\d{2}", _section("4. 부딪치지 않게")))
    blocking = re.search(r"정적 오류\(([^)]*)\)", _section("7. 시험과 확인"))

    assert appendix_rules == set(rules.RULES)
    assert conflict_rules <= set(rules.RULES)
    assert blocking is not None
    assert set(re.findall(r"M\d{2}", blocking[1])) == rules.BLOCKING_RULES


def test_the_skeleton_section_shows_what_new_module_writes(tmp_path: Path) -> None:
    section = _section("3-7.")
    root = tmp_path / "modules"
    argv = ["demo_hello", "--name", "데모 인사", "--owner", "데모 담당", "--root", str(root)]

    assert new_module.main(argv) == 0
    assert 'new_module.py demo_hello --name "데모 인사" --owner "데모 담당"' in section
    page = (root / "demo_hello" / "page.py").read_text(encoding="utf-8")
    assert _python_block("데모 인사 사내 모듈의 첫 화면") == page
    written = sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    )
    for rel in written:
        assert f"`modules/{rel}`" in section, rel


def test_the_guide_example_modules_pass_the_static_rules(tmp_path: Path) -> None:
    """3-8 은 「이 문서의 규칙을 모두 지키는 꼴」 이고 3-9 는 옮긴 꼴이다 — 둘 다 오류도 경고도
    없어야 한다(예시가 경고를 내면 담당자 에이전트가 예시를 그대로 따르다 막힌다)."""
    root = tmp_path / "modules"
    memo = _demo_memo(root)
    table = _write(
        root / "demo_table",
        {
            "module.json": json.dumps(
                {
                    "id": "demo_table",
                    "name": "데모 표",
                    "api": 1,
                    "owner": "데모 담당",
                    "enabled": True,
                    "maturity": "L0",
                    "pages": [{"slug": "main", "file": "page.py", "title": "데모 표"}],
                },
                ensure_ascii=False,
            ),
            "cache.py": _python_block("데모 표 모듈의 캐시"),
            "page.py": _python_block("데모 표 모듈의 첫 화면"),
            "tests/test_demo_table_smoke.py": "# Purpose: 데모 표 시험 자리.\n",
        },
    )

    for folder in (memo, table):
        assert [item.text() for item in _static_findings(folder)] == [], folder.name


def test_the_sample_check_output_is_the_checkers_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """부록 B 의 출력 예시 = 3-8 의 `demo_memo`(시험 2 통과) + 뼈대 화면 끝에 폐기 예정 인자 한 줄을
    더한 `demo_draft`(시험 1 통과)를 담당자 클론(git 검사 함)에서 본 블록."""
    monkeypatch.delenv(module_registry.ROOT_ENV_VAR, raising=False)
    monkeypatch.delenv(module_registry.DISABLED_ENV_VAR, raising=False)
    root = tmp_path / "modules"
    _demo_memo(root)
    assert new_module.main(["demo_draft", "--name", "데모 초안", "--root", str(root)]) == 0
    with (root / "demo_draft" / "page.py").open("a", encoding="utf-8") as page:
        page.write(_DRAFT_EXTRA_LINE)
    scan = module_registry.scan_modules(root)
    passed = {"demo_draft": 1, "demo_memo": 2}
    results = []
    for number, record in enumerate(scan.records, 1):
        manifest = record.manifest
        assert manifest is not None
        static = rules.check_module_folder(
            record.path,
            module_id=manifest.id,
            pages=[page.file for page in manifest.pages],
            environment=ENVIRONMENT,
            git=None,
        )
        count = passed[record.folder_name]
        results.append(
            check_module.ModuleResult(
                number=number,
                record=record,
                findings=static.findings,
                third_party=static.third_party,
                ruff=check_module.RuffResult(ran=True),
                tests=check_module.TestResult(state="passed", passed=count, total=count),
            )
        )
    block = check_module.build_block(
        results,
        root=check_module.PROJECT_ROOT / "modules",
        worktree=None,
        git_checked=True,
        root_warning=False,
    )

    assert _blocks(_section("부록 B"), "text") == ["\n".join(block) + "\n"]


def test_environment_variables_in_the_guide_are_the_registrys() -> None:
    table = _section("9-2.")
    named = set(re.findall(r"^\| `(CAPA_[A-Z_]+)` \|", table, re.M))

    assert named == {
        module_registry.ROOT_ENV_VAR,
        module_registry.DISABLED_ENV_VAR,
        module_registry.DATA_ROOT_ENV_VAR,
    }
    assert f"`{module_registry.ROOT_OFF}`" in table
    assert check_deploy_screens.MODULES_ROOT_ENV_VAR == module_registry.ROOT_ENV_VAR


def test_the_owner_clone_settings_block_is_default_mode_with_powershell_twins() -> None:
    settings = json.loads(_blocks(_section("8-4."), "json")[0])
    permissions = settings["permissions"]
    rules_text = [*permissions["allow"], *permissions["deny"]]

    assert permissions["defaultMode"] == "default"
    for rule in rules_text:
        if rule.startswith("Bash("):
            assert "PowerShell(" + rule.removeprefix("Bash(") in rules_text, rule
    assert not any("new_module.py" in rule for rule in permissions["allow"])
    assert not any("pytest" in rule for rule in permissions["allow"])


def test_the_deploy_agent_template_does_not_allow_the_module_check() -> None:
    """런북 4-5 는 담당자 시험 코드를 실행하는 줄이라 매번 묻는다 — allow 에 넣지 않는다."""
    template = json.loads(SETTINGS_TEMPLATE.read_text(encoding="utf-8"))

    assert not any("check_module.py" in rule for rule in template["permissions"]["allow"])
    assert "Edit(modules/**)" in template["permissions"]["deny"]
