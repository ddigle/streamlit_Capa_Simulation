# Purpose: 모듈 지침서가 창구·규칙·뼈대·예시·출력·환경변수·권한·사람용 안내서와 같은지 본다.

"""지침서(`docs/module_guide.md`)와 코드 맞대기.

지침서는 동료(담당자)의 에이전트가 받는 유일한 문서다. 사외는 모듈을 볼 수 없어, 지침서의
이름·예시·출력이 코드와 어긋나면 그 어긋남이 사내에서 처음 드러난다. 그래서 지침서에 옮겨 적은 것
가운데 코드로 따질 수 있는 것은 여기서 코드에 댄다 — 창구 이름(부록 A), 규칙 번호(부록 B ·
4장 · 7장), 뼈대 화면(3-7), 예시 모듈(3-8 · 3-9 · 3-10 — 정적 규칙을 통과해야 한다), 점검
출력 꼴(부록 B), 환경변수(9-2), 담당자 클론 설정(8-4)과 배포 적용 템플릿. 담당자(사람)가 읽는 안내서
(`docs/module_colleague_guide.md`)는 첫 지시 블록이 지침서 0장과, 점검 출력 예시 줄(8-2)이 부록 B 와
같은지만 본다.
"""

from __future__ import annotations

import dataclasses
import json
import re
import sys
import textwrap
from datetime import date
from pathlib import Path

import pytest

from capa_simulation import module_api, module_helpers, module_registry
from capa_simulation.io import company_bigdataquery_adapter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GUIDE_PATH = PROJECT_ROOT / "docs" / "module_guide.md"
COLLEAGUE_GUIDE_PATH = PROJECT_ROOT / "docs" / "module_colleague_guide.md"
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
_NAME_CELL = re.compile(r"^\| `([A-Za-z0-9_]+)` \|", re.M)
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


def test_the_guide_screens_put_no_introduction_in_the_header() -> None:
    """화면 머리에 소개 줄을 두지 않는다(설계 규칙 UI-TXT-01) — 창구 1.1 부터 `page_header` 의
    `description` 은 받기만 하고 그리지 않는다. 화면 계약(3-5)과 예시 화면(3-8 · 3-9)은 그 인자를
    넘기지 않고, 부록 A 가 그렇다고 적는다."""
    assert '`api.page_header(ctx, "<화면 이름>")`' in _section("3-5.")
    for purpose in ("데모 메모 모듈의 첫 화면", "데모 표 모듈의 첫 화면"):
        assert "description=" not in _python_block(purpose), purpose
    assert "`description` 은 받기만 하고 그리지 않는다" in _section("부록 A")


def test_the_guide_says_the_implementing_mark_is_not_a_badge_line() -> None:
    """창구 1.2 부터 `page_header` 는 성숙도 L0 · L1 의 「구현중」 배지 줄을 본문에 그리지 않는다
    (2026-11-10 보드 Q-5) — 성숙도 표(3-4) · 부록 A 가 그렇다고 적고, 부록 C 에 그 판 줄이 있다.
    작은 판으로 보는 까닭(이름 · 서명 그대로, 그리는 것만 줄임)은 9-4 가 적는다(s-api-minor)."""
    assert "사이드바 · 화면 탭" in _section("3-4.")
    assert "배지 줄을 세우지 않는다" in _section("3-4.")
    assert "「구현중」 배지 줄을 그리지 않는다" in _section("부록 A")
    assert "| v1.2 |" in _section("부록 C")
    assert "화면에 그리는 것만 줄이는 변경은 작은 판이다" in _section("9-4.")
    assert "description=" not in _python_block("데모 인사 모듈의 첫 화면")


def test_the_helper_section_matches_the_helpers(tmp_path: Path) -> None:
    """3-10(창구 1.3 도우미 — 2026-11-12 사용자 결정 「도우미 함수로」)은 결과 까닭 · 실패 갈래 ·
    상한 · 기간 상한 · 버킷 자리를 코드와 같게 적고, 예시 화면은 정적 규칙을 통과한다."""
    section = _section("3-10.")
    adapter_kinds = [
        value
        for name, value in vars(company_bigdataquery_adapter).items()
        if name.startswith("QUERY_FAILURE_")
    ]

    for reason in module_helpers.S3_REASONS:
        assert f"「{reason}」" in section, reason
    for kind in (module_helpers.QUERY_UNAVAILABLE, module_helpers.QUERY_INPUT, *adapter_kinds):
        assert f"「{kind}」" in section, kind
    assert f"{module_api.S3_MAX_BYTES // 1024 // 1024} MiB" in section
    assert f"최대 {module_helpers.MAX_QUERY_WINDOW_DAYS}일" in section
    assert f"`{module_helpers.S3_KEY_PREFIX}<id>/" in section
    # 도우미가 생긴 판(1.3)의 작은 판이다 — 다음 작은 판이 와도 3 그대로다.
    assert '"api_minor": 3' in section
    # 기간 자리 — `{end_date}` 에는 끝 날 다음 날이 들어간다(지침서의 예가 코드의 답과 같다).
    bounds = module_helpers.build_module_query(
        ">= '{start_date}' AND < '{end_date}'", date(2026, 1, 1), date(2026, 1, 31)
    )
    assert bounds == ">= '2026-01-01' AND < '2026-02-01'"
    assert f"`{bounds}`" in section and "start=date(2026, 1, 1), end=date(2026, 1, 31)" in section
    for text in (section, _section("부록 A")):
        assert "끝 날 다음 날" in text and "`>= '{start_date}' AND < '{end_date}'`" in text
    # 기다림 — 상한 크기를 가장 느린 속도로 옮기는 마감(초).
    longest = round(module_helpers._transfer_deadline(module_api.S3_MAX_BYTES))
    assert f"최대 약 {longest}초" in section
    assert "대신 올리거나 받지 않는다" in section and "M21" in section
    page = _python_block("데모 백업 모듈의 첫 화면")
    folder = _write(
        tmp_path / "modules" / "demo_backup",
        {
            "module.json": json.dumps(
                {
                    "id": "demo_backup",
                    "name": "데모 백업",
                    "api": 1,
                    "api_minor": module_api.API_VERSION[1],
                    "owner": "데모 담당",
                    "enabled": True,
                    "maturity": "L0",
                    "pages": [{"slug": "main", "file": "page.py", "title": "데모 백업"}],
                },
                ensure_ascii=False,
            ),
            "page.py": page,
            "tests/test_demo_backup_smoke.py": "# Purpose: 데모 백업 시험 자리.\n",
        },
    )
    assert [item.text() for item in _static_findings(folder)] == []


def test_rule_numbers_in_the_guide_are_the_checkers_rules() -> None:
    appendix_rules = set(_RULE_ROW.findall(_section("부록 B")))
    conflict_rules = set(re.findall(r"M\d{2}", _section("4. 부딪치지 않게")))
    blocking = re.search(r"정적 오류\(([^)]*)\)", _section("7. 시험과 확인"))

    assert appendix_rules == set(rules.RULES)
    assert conflict_rules <= set(rules.RULES)
    assert blocking is not None
    assert set(re.findall(r"M\d{2}", blocking[1])) == rules.BLOCKING_RULES


def test_the_guide_names_every_way_around_the_window_the_checker_refuses() -> None:
    """M06 이 오류로 보는 우회 이름은 지침서 표에 다 있다 — 담당자가 점검에서 처음 만나지 않게."""
    row = next(
        line
        for line in _section("부록 B").splitlines()
        if line.startswith("| M06 |") and "우회" in line
    )
    for name in sorted(rules.WINDOW_ESCAPE_NAMES):
        assert f"`{name}`" in row, name
    for form in rules.HAND_MADE_CONTEXT_FORMS:
        assert f"`{form}`" in row, form
    assert "`api.context(__file__)` 로만 받는다" in row
    assert "보증이 아니다" in row


def test_the_skeleton_section_shows_what_new_module_writes(tmp_path: Path) -> None:
    section = _section("3-7.")
    root = tmp_path / "modules"
    argv = ["demo_hello", "--name", "데모 인사", "--owner", "데모 담당", "--root", str(root)]

    assert new_module.main(argv) == 0
    assert 'new_module.py demo_hello --name "데모 인사" --owner "데모 담당"' in section
    page = (root / "demo_hello" / "page.py").read_text(encoding="utf-8")
    assert _python_block("데모 인사 모듈의 첫 화면") == page
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


def test_moved_conditions_keep_their_value_across_screens(tmp_path: Path) -> None:
    """독립 앱의 사이드바 조건은 화면을 옮겨도 남는다. 본문으로 옮긴 위젯은 `persist_state` 가
    없으면 화면을 옮겼다 오면 처음 값이다 — 3-9 의 옮긴 꼴과 「라우터 앱」 공용 조건이 그 꼴을
    보이고(같은 `ctx.key` · `persist_state="session"`), 4장 · 5장이 까닭을 적는다."""
    page = _python_block("데모 표 모듈의 첫 화면")
    common = _python_block("데모 실적판 모듈의 공용 조건")
    moving = _section("3-9.")

    assert 'key=ctx.key("kind"), persist_state="session")' in page
    assert 'key=ctx.key("region"), persist_state="session")' in common
    for section in (moving, _section("4. 부딪치지 않게"), _section("5. 화면 일관성")):
        assert 'persist_state="session"' in section
    assert "라우터 앱" in moving and "바로 아래" in moving
    screen = (
        "# Purpose: 데모 실적판 모듈의 {name} 화면.\n\n"
        "from capa_simulation import module_api as api\n"
        "from modules.demo_port import common\n\n"
        "ctx = api.context(__file__)\n"
        'api.page_header(ctx, "{name}")\n'
        "region = common.conditions(ctx)\n"
    )
    folder = _write(
        tmp_path / "modules" / "demo_port",
        {
            "module.json": json.dumps(
                {
                    "id": "demo_port",
                    "name": "데모 실적판",
                    "api": 1,
                    "owner": "데모 담당",
                    "enabled": True,
                    "maturity": "L0",
                    "pages": [
                        {"slug": "main", "file": "overview.py", "title": "개요"},
                        {"slug": "detail", "file": "detail.py", "title": "상세"},
                    ],
                },
                ensure_ascii=False,
            ),
            "common.py": common,
            "overview.py": screen.format(name="개요"),
            "detail.py": screen.format(name="상세"),
            "tests/test_demo_port_smoke.py": "# Purpose: 데모 실적판 시험 자리.\n",
        },
    )

    assert [item.text() for item in _static_findings(folder)] == []


def test_the_title_clash_reason_in_the_guide_is_the_registrys() -> None:
    """3-3 이 「차례가 뒤인 모듈 전체」 가 실패한다고 적고, 그 까닭 꼴이 런타임 · 점검과 같다."""
    declaration = _section("3-3.")

    for clash in (
        module_registry.TitleClash("<이름>", "<id>"),
        module_registry.TitleClash("<이름>", ""),
    ):
        reason = module_registry.clash_reason(clash).removeprefix("화면 이름 겹침: <이름> ")
        assert reason in declaration, reason
    assert "뒤인 모듈 전체" in declaration
    assert "나중에 넣은 쪽이 아니다" in declaration


def test_the_line_width_rule_counts_wide_characters() -> None:
    """ruff 의 E501 은 화면 폭으로 센다(한글 2칸) — 「100자」 로 적으면 한글 줄이 60자 안팎에서
    걸린다."""
    conflicts = _section("4. 부딪치지 않게")

    assert f"폭 {new_module.LINE_WIDTH}칸" in conflicts
    assert "한 자가 2칸" in conflicts
    assert "100자" not in GUIDE
    assert new_module._width("가" * 50) == new_module.LINE_WIDTH


def test_transitive_packages_named_in_the_guide_warn_and_numpy_is_direct() -> None:
    """6장 「경고」 에 적은 이름은 지금 `requirements.txt` 에서 직접 의존이 아니다(경고가 난다).
    pandas 와 늘 함께 쓰는 numpy 는 코어 직접 의존이라 「바로 써도 되는 것」 에 든다 — 담당자가
    numpy 경고를 찾아 헤매지 않는다."""
    dependencies = _section("6. 의존성")
    usable = dependencies.partition("바로 써도 되는 것:")[2].partition("경고가 나는 것:")[0]
    warned = dependencies.partition("경고가 나는 것:")[2].partition("오류가 나는 것:")[0]

    assert "`numpy`" in usable and "numpy" not in warned
    assert ENVIRONMENT.requirements["numpy"].direct
    for name in ("pyarrow", "pillow", "toml", "requests"):
        requirement = ENVIRONMENT.requirements[rules.normalize_name(name)]
        assert not requirement.direct, name
    for shown in ("`pyarrow`", "`PIL`(pillow)", "`toml`", "`requests`"):
        assert shown in warned, shown


def test_the_skeleton_section_says_when_to_give_a_title() -> None:
    skeleton = _section("3-7.")
    _, title_max = module_registry.TITLE_LENGTH
    _, name_max = module_registry.NAME_LENGTH

    assert f"{name_max}자까지" in skeleton and f"{title_max}자까지" in skeleton
    assert "`--title` 을 함께 준다" in skeleton


def test_data_modules_is_read_only_for_the_owner_agent() -> None:
    """2장은 `data/modules/<id>/` 에 손으로 넣지 않는다고 한다 — 첫 지시(0장)와 담당자 클론 설정
    (8-4)도 같은 말을 해야 에이전트가 「내 PC 에서만 되는」 데이터를 만들지 않는다."""
    first_order = _blocks(_section("0. 에이전트에게"), "text")[0]
    settings = json.loads(_blocks(_section("8-4."), "json")[0])

    editable = next(line for line in first_order.splitlines() if line.startswith("1. "))
    assert "data/modules/<id>/ 는 화면이 실행 중에 쓰는 자리라 읽기만 한다" in editable
    assert not any("data/modules" in rule for rule in settings["permissions"]["allow"])


def test_the_first_instruction_and_upload_section_go_through_a_pull_request() -> None:
    """사내 main 은 PR 로만 바뀐다(2026-11-02 — 사내 GitHub 에서 PR · 가지 보호를 쓴다).
    첫 지시는 번호 줄 앞에서 PR 길을 먼저 말하고, 8-2 는 「PR 을 못 쓰면 직접 커밋」 갈래 없이
    앱 관리자의 PR 점검(런북 4-6) 뒤 합침으로 끝난다 — 담당자 에이전트가 사내 main 에 바로
    올리는 길을 찾지 않는다."""
    first_order = _blocks(_section("0. 에이전트에게"), "text")[0].splitlines()
    numbered = next(n for n, line in enumerate(first_order) if line.startswith("1. "))
    upload = _section("8-2.")
    runbook = (PROJECT_ROOT / "docs" / "internal_update_runbook.md").read_text(encoding="utf-8")

    assert any("PR 로만 main 에 들어간다" in line for line in first_order[:numbered])
    assert "PR 을 쓸 수 없으면" not in upload and "직접 커밋" not in upload
    assert "git switch -c module/<id>/<주제>" in upload and "Squash and merge" in upload
    assert "런북 4-6" in upload and "### 4-6. 모듈 PR 점검" in runbook
    assert "안 되면 자기 폴더만 바꾸는 직접 커밋" not in _section("8-3.")


def test_the_colleague_guide_hands_over_the_first_instruction_unchanged() -> None:
    """담당자는 첫 지시를 사람용 안내서(3장)에서 복사해 붙인다 — 그 블록이 지침서 0장과 한 글자라도
    다르면 옛 지시가 에이전트에게 간다. 지침서 0장을 고치면 안내서 3장의 블록도 같은 글로 고친다.
    지침서 · 안내서 모두 「사내」 를 쓰지 않는다(2026-11-03 사용자 — 앱은 회사 안에서 쓰는 것이
    기본이라 「사내 모듈」 은 「모듈」 이고 「사내 main」 은 「main」 이다). CLAUDE.md 머리의 세션
    가름 줄도 첫 지시와 같은 이름을 쓴다."""
    colleague = COLLEAGUE_GUIDE_PATH.read_text(encoding="utf-8")
    first_order = _blocks(_section("0. 에이전트에게"), "text")[0]
    claude_md = (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    routing = next(line for line in claude_md.splitlines() if "세션이 누구인지" in line)

    assert _blocks(colleague, "text").count(first_order) == 1
    assert "사내" not in colleague and "사내" not in GUIDE
    assert "앱의 모듈 <id> 를 맡은 에이전트다" in first_order
    assert "첫 지시가 「모듈 `<id>` 를 맡은 에이전트」" in routing


def test_the_colleague_guides_check_line_is_the_guides_appendix_b_line() -> None:
    """안내서 8-2 는 부록 B 점검 출력의 「자세히」 줄을 옮겨 적고 그 파일 · 줄을 풀어
    읽는다 — 뼈대가 바뀌어 부록 B 의 줄 번호가 바뀌면(부록 B 는 실제 점검 출력과 맞댄다)
    안내서의 예시 줄과 「n번째 줄」 도 같이 고친다."""
    colleague = COLLEAGUE_GUIDE_PATH.read_text(encoding="utf-8")
    appendix = _blocks(_section("부록 B"), "text")[0]
    wanted = next(line.strip() for line in appendix.splitlines() if line.startswith("  m1 "))
    location = re.search(r" (\w+\.py):(\d+) ", wanted)
    assert location is not None

    assert [block.strip() for block in _blocks(colleague, "text")].count(wanted) == 1
    assert f"파일과 줄(`{location[1]}` {location[2]}번째 줄)" in colleague


def test_the_runbook_module_checks_always_guard_the_operational_data() -> None:
    """런북 4-5(배포 때) · 4-6(PR 점검) · 4-7(배포 사이에 올리기)의 `check_module.py` 줄은 모두
    `--worktree-of .` 를 단다 — 그래야 감시 러너가 사본의 `data/` 에 더해 운영 저장소의 `data/`(운영
    DB)도 모듈 시험에서 막는다. 4-6 은 아직 아무도 보지 않은 PR 의 시험 코드를 돌리는 자리다."""
    runbook = (PROJECT_ROOT / "docs" / "internal_update_runbook.md").read_text(encoding="utf-8")
    for start in ("### 4-5.", "### 4-6.", "### 4-7."):
        body = re.split(r"\n#{2,3} ", runbook.partition(start)[2], maxsplit=1)[0]
        lines = [
            line
            for line in body.replace("\\", "/").splitlines()
            if "scripts/check_module.py" in line
        ]
        assert lines, start
        assert all("--worktree-of ." in line for line in lines), (start, lines)


def _runbook_pr_patterns(body: str) -> list[str]:
    """런북 4-6 본문의 PowerShell · bash 찾는 줄 패턴."""
    return re.findall(r"Select-String '([^']+)'", body) + re.findall(r"grep -E '([^']+)'", body)


def test_the_pr_check_merges_only_the_head_it_checked() -> None:
    """런북 4-6 — PR 의 합치는 단추는 누른 때의 머리를 합친다. 그래서 점검한 머리의 7자를 알리고,
    합치기 앞에 PR 화면의 마지막 커밋이 그것과 같을 때만 합친다(점검 뒤 더 올린 커밋이 점검 없이
    들어가지 않게). 성숙도 `L2` 줄은 `:` 둘레 빈칸이 없는 JSON 도 잡고 지운 줄 · 다른 단계는
    넘긴다."""
    runbook = (PROJECT_ROOT / "docs" / "internal_update_runbook.md").read_text(encoding="utf-8")
    body = re.split(r"\n#{2,3} ", runbook.partition("### 4-6.")[2], maxsplit=1)[0]
    report = body.partition("\n4. ")[2]

    assert "git rev-parse --short=7 $pr" in report
    assert "마지막 커밋 7자가 그 7자와 같은지" in report and "1 부터 다시 한다" in report
    patterns = [pattern for pattern in _runbook_pr_patterns(body) if "maturity" in pattern]
    assert len(patterns) == 2, patterns
    for pattern in patterns:
        assert re.search(pattern, '+  "maturity": "L2",'), pattern
        assert re.search(pattern, '+  "maturity":"L2",'), pattern
        assert not re.search(pattern, '-  "maturity": "L2",'), pattern
        assert not re.search(pattern, '+  "maturity": "L1",'), pattern


def test_the_pr_check_looks_for_credential_reads_the_static_rules_do_not_see() -> None:
    """런북 4-6 — 통합 검수 D6 (가)는 키를 앱 환경변수로 넘기는 구조를 두는 대신 PR 점검으로 본다.
    `check_module.py` 는 자격 이름 · 토큰 파일 자리(M21) 밖의 환경변수 **읽기**를 보지 않으므로 두
    셸의 찾는 줄이 PR 이 더한 줄에서 읽는 꼴 · `bigdataquery` 직접 import(2026-11-12 「도우미
    함수로」 — 찾는 글을 넓힘)를 찍어야 하고, 지운 줄 · 무관한 줄은 찍지 않는다. 런북이 말한 규칙
    번호는 지침서와 같다."""
    runbook = (PROJECT_ROOT / "docs" / "internal_update_runbook.md").read_text(encoding="utf-8")
    body = re.split(r"\n#{2,3} ", runbook.partition("### 4-6.")[2], maxsplit=1)[0]
    patterns = [pattern for pattern in _runbook_pr_patterns(body) if "CAPA_S3_" in pattern]
    assert len(patterns) == 2 and patterns[0] == patterns[1], patterns

    for pattern in patterns:
        for reads in (
            '+    key = os.environ["CAPA_S3_SECRET_KEY"]',
            "+from os import environ",
            '+    os.getenv("AWS_SECRET_ACCESS_KEY")',
            '+    Path.home() / ".aws" / "credentials"',
            "+import boto3",
            "+import bigdataquery",
            "+from bigdataquery import getData",
            '+    user = os.environ["CAPA_BDQ_USER_NAME"]',
            '+NAME = "CAPA_BDQ_USER_NAME"',
            '+    token = Path("/config/.credential") / name',
            '+TOKEN = "/config/.credential/x"',
        ):
            assert re.search(pattern, reads), reads
        assert not re.search(pattern, '-    key = os.environ["CAPA_S3_SECRET_KEY"]')
        assert not re.search(pattern, '+    return ctx.data_dir / "result.csv"')
        assert not re.search(pattern, "+    rows = api.query_bigdataquery(ctx, SQL)")

    assert "**읽기는 보지 않는다**" in body and "통합 검수 D6 (가)" in body
    for rule, word in (
        ("M07", "`.aws/`"),
        ("M11", "`os.environ` 쓰기"),
        ("M21", "`CAPA_BDQ_`"),
        ("M21", "`.credential`"),
    ):
        assert rule in body and word in body
        assert any(line.startswith(f"| {rule} |") and word in line for line in GUIDE.splitlines())


def test_a_merged_module_reaches_the_app_between_deploys_through_runbook_four_seven() -> None:
    """지침서 8-2 끝 · 9-2 의 1 은 합친 모듈이 다음 배포 전에도 오른다고 말한다 — 그 길은 런북 4-7
    하나다(2026-11-03). 4-7 은 점검한 `origin/main` 그대로를 빨리 감기로만 받고, 받은 HEAD 와 CI/CD
    앞의 사내 main 이 점검한 7자와 같은지 본다 — 점검 뒤 합쳐진 PR 이 점검 없이 앱에 오르지 않게."""
    runbook = (PROJECT_ROOT / "docs" / "internal_update_runbook.md").read_text(encoding="utf-8")
    body = re.split(r"\n#{2,3} ", runbook.partition("### 4-7.")[2], maxsplit=1)[0]

    for heading in ("8-2.", "9-2."):
        assert "런북 4-7" in " ".join(_section(heading).split()), heading
    assert 'git archive --format=zip -o "$mtree.zip" origin/main' in body
    assert "git merge --ff-only origin/main" in body and "git pull --rebase` 는" in body
    assert body.count("3 의 7자") >= 2 and "git rev-list --count origin/main..HEAD" in body


def _agents_bullet(start: str) -> str:
    """AGENTS.md 에서 `- <start>` 로 여는 글머리 하나(두 칸 들여 쓴 이어진 줄까지)."""
    lines = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8").splitlines()
    first = next(n for n, line in enumerate(lines) if line.startswith(f"- {start}"))
    end = next(
        (n for n in range(first + 1, len(lines)) if not lines[n].startswith("  ")), len(lines)
    )
    return "\n".join(lines[first:end])


def test_agents_defaults_bullet_is_the_guides_three_defaults_only() -> None:
    """AGENTS 1장의 「메인 세션이 정한 기본값 셋」 은 지침서 8-3 의 셋 그대로다. 사용자가 직접
    「권장대로」 로 정한 사양 10장 답(v1 은 운영 모듈 데이터를 백업하지 않는다 — 10장 5)은 그 묶음에
    넣지 않고 따로 적는다 — 묶음에 섞으면 사용자 결정이 「바꿀 수 있는 기본값」 으로 읽힌다."""
    defaults = _agents_bullet("**메인 세션이 「권장대로」 로 정한 기본값 셋")

    assert re.findall("[①②③④⑤]", defaults) == ["①", "②", "③"]
    assert len(re.findall(r"^\d+\. ", _section("8-3."), re.M)) == 3
    assert "백업" not in defaults and "백업" not in _section("8-3.")
    backup = _agents_bullet("**v1 은 운영 모듈 데이터를 백업하지 않는다**")
    assert "사용자 「권장대로」" in backup and "10장 5" in backup


def test_the_query_example_passes_the_static_rules(tmp_path: Path) -> None:
    """3-10 의 조회 예(2026-11-12 사용자 「담당자에게 보낼 내용은 모듈 개발 가이드에
    반영」)는 창구 1.3 을 적고 정적 규칙을 오류도 경고도 없이 통과한다 — 캐시 함수는
    `ctx` 를 밑줄 인자로 받는다(M12)."""
    section = _section("3-10.")
    cache = _python_block("데모 조회 모듈의 캐시")
    page = _python_block("데모 조회 모듈의 첫 화면")
    folder = _write(
        tmp_path / "modules" / "demo_query",
        {
            "module.json": json.dumps(
                {
                    "id": "demo_query",
                    "name": "데모 조회",
                    "api": 1,
                    "api_minor": 3,
                    "owner": "데모 담당",
                    "enabled": True,
                    "maturity": "L0",
                    "pages": [{"slug": "main", "file": "page.py", "title": "데모 조회"}],
                },
                ensure_ascii=False,
            ),
            "cache.py": cache,
            "page.py": page,
            "tests/test_demo_query_smoke.py": "# Purpose: 데모 조회 시험 자리.\n",
        },
    )

    assert [item.text() for item in _static_findings(folder)] == []
    assert "def daily(_ctx: api.ModuleContext" in cache
    assert "WORK_DATE >= '{start_date}' AND WORK_DATE < '{end_date}'" in cache
    assert "except api.BigDataQueryError as error:" in page
    assert '`monkeypatch.setattr(api, "query_bigdataquery", <대역 함수>)`' in section


def test_the_move_section_says_when_what_and_how_the_owner_moves_a_direct_query() -> None:
    """3-11 — 직접 조회하던 모듈 옮기기(배포 전 미리 확인 9, 2026-11-12). 도우미가 든
    판을 적용한 뒤에만 옮길 수 있고(옛 코어는 「API 1.3 필요」 · PR 점검 실패), 걷는 꼴은
    M21 의 두 꼴이며, 바꾼 꼴은 3-10 과 같다. 안내서 8-2 는 사람에게 그 절을 가리킨다."""
    section = _section("3-11.")
    colleague = COLLEAGUE_GUIDE_PATH.read_text(encoding="utf-8")
    m21 = next(line for line in _section("부록 B").splitlines() if line.startswith("| M21 |"))

    assert section.startswith("### 3-11. 직접 조회하던 모듈을 도우미로 옮기기 — 점검 오류 M21")
    assert "적용했다고 알린 뒤에 시작한다" in section and "「API 1.3 필요」" in section
    for word in ("`CAPA_BDQ_`", "`.credential`", "`bigdataquery.token`"):
        assert word in section and word in m21, word
    for form in (
        "`api.query_bigdataquery(ctx, sql, start=…, end=…)`",
        "`>= '{start_date}' AND < '{end_date}'`",
        "`api.BigDataQueryError`",
        "`error.kind`",
        "밑줄 인자(`_ctx`)",
        '`"api_minor": 3`',
        '`monkeypatch.setattr(api, "query_bigdataquery", <대역 함수>)`',
        "「Squash and merge」",
        "(9-2)",
    ):
        assert form in section, form
    assert "지침서 3-11 대로 BigDataQuery 조회를 앱 도우미로" in colleague.replace("\n", "")
    assert "M21)입니다 — 이미 그렇게 쓰던 모듈은 8-2 끝을 봅니다." in colleague


def test_module_data_on_the_deploy_server_is_outside_the_db_sync_in_every_guide() -> None:
    """배포 서버의 모듈 데이터는 재배포마다 비워지고 DB 동기화 밖이다 — 지침서 2장 ·
    3-10 · 안내서 6장이 같은 말을 하고, S3 도우미는 DB 동기화를 켠 뒤에만 된다(배포 전
    미리 확인 8, 2026-11-12)."""
    colleague = COLLEAGUE_GUIDE_PATH.read_text(encoding="utf-8").replace("\n", "")

    assert "재배포(CI/CD)마다" in _section("2. 쓸 수 있는 자리").replace("\n  ", "")
    assert "DB 동기화를 켜기(이관) 전에는 「쓸 수 없음」" in _section("3-10.").replace("\n  ", "")
    assert "DB 동기화가 켜진 뒤에도 모듈 데이터는 그 밖입니다" in colleague
    assert "앱 관리자가 DB 동기화를 켠 뒤에만 되고" in colleague
