# Purpose: 모듈 점검이 규칙마다 금지 꼴을 잡고 견본을 통과시키며 결과 블록 꼴을 지킴을 본다.

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from capa_simulation import module_registry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "modules"
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import check_module  # noqa: E402
import inspect_real_data_checks  # noqa: E402
import module_check_rules as rules  # noqa: E402

ENVIRONMENT = rules.load_environment(PROJECT_ROOT)
HEADER = "# Purpose: 시험 화면.\n"
SMOKE = """# Purpose: 시험 모듈의 진입 스모크 시험.

from pathlib import Path

from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[1] / "{page}"


def test_page_renders() -> None:
    app = AppTest.from_file(str(PAGE)).run(timeout=60)
    assert not app.exception
"""


def _manifest(module_id: str, pages: Sequence[str], *, enabled: bool = True) -> str:
    declared = {
        "id": module_id,
        "name": "시험 모듈",
        "api": 1,
        "owner": "시험 담당",
        "enabled": enabled,
        "maturity": "L0",
        "pages": [
            {
                "slug": f"p{index}",
                "file": page,
                "title": f"시험 {module_id.replace('_', ' ')} {index}",
            }
            for index, page in enumerate(pages)
        ],
    }
    return json.dumps(declared, ensure_ascii=False)


def _module(
    root: Path,
    module_id: str,
    files: Mapping[str, str | bytes],
    *,
    pages: Sequence[str] = ("page.py",),
    enabled: bool = True,
    smoke: bool = True,
) -> Path:
    """tmp 모듈 한 벌. `files` 의 글은 그대로 쓴다(Purpose 헤더도 글에 적는다)."""
    folder = root / module_id
    folder.mkdir(parents=True)
    (folder / "module.json").write_text(
        _manifest(module_id, pages, enabled=enabled), encoding="utf-8"
    )
    for rel, content in files.items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    if smoke:
        test = folder / "tests" / f"test_{module_id}_smoke.py"
        test.parent.mkdir(exist_ok=True)
        test.write_text(SMOKE.format(page=pages[0]), encoding="utf-8")
    return folder


def _static(folder: Path, *, environment: rules.PackageEnvironment = ENVIRONMENT) -> list[str]:
    """정적 규칙만 — `<규칙> <등급> <경로>` 목록."""
    manifest = module_registry.read_manifest(folder)
    result = rules.check_module_folder(
        folder,
        module_id=manifest.id,
        pages=[page.file for page in manifest.pages],
        environment=environment,
        git=rules.git_view(folder, rules.module_files(folder)),
    )
    return [f"{item.rule} {item.level} {item.path}" for item in result.findings]


def _page_rules(
    tmp_path: Path,
    body: str,
    *,
    rel: str = "page.py",
    environment: rules.PackageEnvironment = ENVIRONMENT,
) -> set[tuple[str, str]]:
    """화면 `page.py` 가 있는 tmp 모듈의 `rel` 에 `body` 를 두고 그 파일에서 찾은 (규칙, 등급)."""
    files = {"page.py": HEADER + "import streamlit as st\n", rel: HEADER + body}
    folder = _module(tmp_path / "modules", "demo_x", files)
    result = rules.check_module_folder(
        folder, module_id="demo_x", pages=["page.py"], environment=environment, git=None
    )
    return {(item.rule, item.level) for item in result.findings if item.path == rel}


def _fixture_copy(root: Path, name: str, *, smoke: bool = True) -> Path:
    target = root / name
    shutil.copytree(FIXTURES / name, target)
    if smoke:
        manifest = module_registry.read_manifest(target)
        test = target / "tests" / f"test_{name}_smoke.py"
        test.parent.mkdir()
        test.write_text(SMOKE.format(page=manifest.pages[0].file), encoding="utf-8")
    return target


def _run(argv: Sequence[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    capsys.readouterr()
    code = check_module.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _summary(out: str) -> str:
    return next(line for line in out.splitlines() if line.startswith(check_module.SUMMARY_LABEL))


# ------------------------------------------------------------------ 견본 · 상태


def test_the_good_fixture_passes_with_ruff_and_its_tests(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "modules"
    _fixture_copy(root, "demo_ok")

    code, out = _run(["demo_ok", "--root", str(root)], capsys)

    assert code == 0, out
    assert (
        "- m1 demo_ok 통과 · L0 · API 1.3 · 화면 2 · 오류 0 · 경고 0 · ruff ok · 시험 1 통과" in out
    )
    assert "제3자 패키지: pandas" in out


def test_a_disabled_module_is_off_not_failed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "modules"
    _fixture_copy(root, "demo_off")

    code, out = _run(["--all", "--root", str(root), "--no-tests"], capsys)

    assert code == 0, out
    assert "- m1 demo_off 꺼짐 · module.json enabled=false · L0 · API 1.0" in out
    assert "모듈 1 = 통과 0 + 꺼짐 1 + 실패 0" in _summary(out)


@pytest.mark.parametrize(
    ("name", "reason"),
    [("demo_bad_manifest", "모르는 칸: enable"), ("demo_future_api", "API 판 99")],
)
def test_broken_manifests_fail_as_m01_and_skip_everything_else(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    reason: str,
) -> None:
    root = tmp_path / "modules"
    _fixture_copy(root, name, smoke=False)
    monkeypatch.setattr(check_module, "run_ruff", _must_not_run)
    monkeypatch.setattr(check_module, "run_tests", _must_not_run)

    code, out = _run([name, "--root", str(root)], capsys)

    assert code == 1
    assert f"- m1 {name} 실패 · 선언 — " in out
    assert reason in out
    assert f"  m1 {name} 오류 M01 module.json" in out
    assert "ng m1 선언" in _summary(out)


def _titled_module(root: Path, module_id: str, titles: Sequence[str], *, order: int) -> Path:
    folder = _module(root, module_id, {"page.py": HEADER + "import streamlit as st\n"})
    declared = json.loads((folder / "module.json").read_text(encoding="utf-8"))
    declared["order"] = order
    declared["pages"] = [
        {"slug": f"p{index}", "file": "page.py" if index == 0 else f"p{index}.py", "title": title}
        for index, title in enumerate(titles)
    ]
    for page in declared["pages"][1:]:
        (folder / page["file"]).write_text(HEADER + "import streamlit as st\n", encoding="utf-8")
    (folder / "module.json").write_text(json.dumps(declared, ensure_ascii=False), encoding="utf-8")
    return folder


def test_a_title_clash_names_the_other_module_on_both_sides(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """차례가 앞인 새 모듈이 기존 모듈의 화면 이름을 쓰면 기존 모듈 전체가 실패한다. 새 모듈
    담당자의 점검은 통과로만 보이므로 그쪽에도 M01 경고를 단다 — 둘 다 상대 id 를 적는다."""
    root = tmp_path / "modules"
    _titled_module(root, "demo_port", ["개요", "상세"], order=100)
    _titled_module(root, "demo_table", ["개요"], order=50)

    code, out = _run(["demo_table", "--root", str(root), "--no-ruff", "--no-tests"], capsys)
    assert code == 0, out
    assert "- m1 demo_table 통과 · L0 · API 1.0 · 화면 1 · 오류 0 · 경고 1" in out
    assert (
        "  m1 demo_table 경고 M01 module.json 화면 이름 「개요」 — 차례가 뒤인 모듈 demo_port 도 "
        "같은 이름을 써서 그 모듈 전체가 실패합니다" in out
    ), out

    code, out = _run(["demo_port", "--root", str(root), "--no-ruff", "--no-tests"], capsys)
    assert code == 1, out
    assert "- m1 demo_port 실패 · 선언 — 화면 이름 겹침: 개요 — 차례가 앞인 모듈 demo_table" in out


def _must_not_run(*args: object, **kwargs: object) -> object:
    raise AssertionError("선언이 틀린 모듈에는 ruff·시험을 돌리지 않는다")


@pytest.mark.parametrize(
    "body",
    [
        'NAME = "proc"\n',
        'COLUMNS = {"proc": 1}\n',
        'PATH = "reports/proc/summary.csv"\n',
        'NAME = "notes.aws"\n',
        'from pathlib import Path\nPATH = Path("reports") / "proc" / "x.csv"\n',
        'from pathlib import Path\nPATH = Path("proc") / "x.csv"\n',
        "from capa_simulation import module_api as api\nctx = api.context(__file__)\n"
        'PATH = ctx.data_dir / "proc" / "x.csv"\n',
    ],
)
def test_words_that_only_look_like_a_key_place_pass(tmp_path: Path, body: str) -> None:
    """이 저장소에서 `proc` 은 공정을 뜻하는 흔한 낱말이다. 오류면 규칙을 믿지 않게 된다."""
    assert ("M07", "error") not in _page_rules(tmp_path, body)


def test_the_unwrapped_fixture_keys_are_caught(tmp_path: Path) -> None:
    folder = _fixture_copy(tmp_path / "modules", "demo_keys")
    assert "M08 error demo_keys_page.py" in _static(folder)


def test_the_crash_fixture_missing_package_is_caught_through_importlib(tmp_path: Path) -> None:
    """견본 demo_crash 는 없는 패키지를 `importlib.import_module("…")` 로 부른다.

    앱에서는 그 화면이 import 오류 카드가 된다 — 점검이 미리 M09 로 잡는다(글자 상수 동적 import).
    """
    folder = _fixture_copy(tmp_path / "modules", "demo_crash")
    assert "M09 error demo_crash_import.py" in _static(folder)


# ------------------------------------------------------------------ 규칙마다(정적)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('import streamlit as st\nst.set_page_config(layout="wide")\n', ("M02", "error")),
        ('import streamlit as st\nst.html("<b>x</b>")\n', ("M03", "error")),
        ('import streamlit as st\nst.iframe("https://example.invalid")\n', ("M03", "error")),
        ("LINK = \"<link rel='stylesheet' href='a.css'>\"\n", ("M03", "error")),
        ("import streamlit.components.v1 as components\n", ("M03", "error")),
        ("from streamlit import components\n", ("M03", "error")),
        ('import streamlit as st\nst.components.v1.html("x")\n', ("M03", "error")),
        (
            "import streamlit as st\nbody = str(1)\nst.markdown(body, unsafe_allow_html=True)\n",
            ("M03", "error"),
        ),
        (
            'import streamlit as st\nx = 1\nst.markdown(f"<b>{x}</b>", unsafe_allow_html=True)\n',
            ("M03", "error"),
        ),
        (
            'import streamlit as st\nst.markdown("<b>굵게</b>", unsafe_allow_html=True)\n',
            ("M03", "warning"),
        ),
        ('import streamlit as st\nst.sidebar.write("x")\n', ("M04", "error")),
        ("import streamlit as st\nwith st.sidebar:\n    pass\n", ("M04", "error")),
        ('import streamlit as st\nst.logo("a.png")\n', ("M04", "error")),
        ("import streamlit as st\nst.navigation([])\n", ("M05", "error")),
        ('import streamlit as st\nst.Page("x.py")\n', ("M05", "error")),
        ('import streamlit as st\nst.switch_page("x.py")\n', ("M05", "error")),
        ("import streamlit as st\nst.query_params.clear()\n", ("M05", "error")),
        ("import streamlit as st\nst.query_params.from_dict({})\n", ("M05", "error")),
        ('import streamlit as st\ndel st.query_params["mod_demo_x__a"]\n', ("M05", "error")),
        ('import streamlit as st\nst.set_option("client.toolbarMode", "x")\n', ("M05", "error")),
        ('import streamlit as st\nst.page_link("x.py")\n', ("M05", "warning")),
        ("from capa_simulation import settings\n", ("M06", "error")),
        ("import capa_simulation.navigation\n", ("M06", "error")),
        ("import capa_simulation\n", ("M06", "error")),
        ("from modules.other import helper\n", ("M06", "error")),
        ("import modules\n", ("M06", "error")),
        ("import app_pages.home\n", ("M06", "error")),
        ("from scripts import check_module\n", ("M06", "error")),
        # 창구 겉면(`module_api.__all__`) 밖 이름 — import·속성 어느 쪽으로도 코어 설정에 닿는다.
        ("from capa_simulation.module_api import module_registry\n", ("M06", "error")),
        (
            "from capa_simulation import module_api as api\n"
            "PATH = api.module_registry.settings.DUCKDB_PATH\n",
            ("M06", "error"),
        ),
        (
            "import capa_simulation.module_api\nPATH = capa_simulation.settings.DUCKDB_PATH\n",
            ("M06", "error"),
        ),
        # 창구 도우미의 속(키 · 버킷 한 벌을 쥔다)도 겉면 밖이다.
        ("from capa_simulation import module_helpers\n", ("M06", "error")),
        (
            "from capa_simulation import module_api as api\n"
            "TARGET = api._module_helpers._s3_target()\n",
            ("M06", "error"),
        ),
        (
            "from capa_simulation import module_api as api\n"
            'HELPERS = getattr(api, "_module_helpers")\n',
            ("M06", "error"),
        ),
        # 글자 상수로 부르는 동적 import 도 같은 규칙이다.
        (
            'import importlib\nimportlib.import_module("capa_simulation.settings")\n',
            ("M06", "error"),
        ),
        ('__import__("threading")\n', ("M10", "error")),
        (
            'from importlib import import_module\nimport_module("demo_not_installed_package")\n',
            ("M09", "error"),
        ),
        ('PATH = "data/input/Core_Data.csv"\n', ("M07", "error")),
        ('PATH = "data\\\\temp\\\\x.csv"\n', ("M07", "error")),
        ('NAME = "capa_simulation.duckdb"\n', ("M07", "error")),
        ('NAME = "equipment_availability.duckdb"\n', ("M07", "error")),
        ('NAME = ".deploy/applied.json"\n', ("M07", "error")),
        ('NAME = "~/.aws/credentials"\n', ("M07", "error")),
        ('import os\nFOLDER = os.path.expanduser("~/.aws")\n', ("M07", "error")),
        ('NAME = ".aws"\n', ("M07", "error")),
        ('NAME = "/proc/self/environ"\n', ("M07", "error")),
        ('NAME = "file:///proc/self/environ"\n', ("M07", "error")),
        (
            'from pathlib import Path\nPATH = Path("/") / "proc" / "self" / "environ"\n',
            ("M07", "error"),
        ),
        (
            'from pathlib import Path\nTEXT = Path("/proc/self/environ").read_bytes()\n',
            ("M07", "error"),
        ),
        ('from pathlib import Path\nPATH = Path("/proc") / "self" / "environ"\n', ("M07", "error")),
        (
            'from pathlib import Path\nPATH = Path.home() / ".aws" / "credentials"\n',
            ("M07", "error"),
        ),
        ('NAME = "data/sample.csv"\n', ("M07", "warning")),
        # 마디로 나눠 이은 코어 데이터 자리와 모듈 데이터 자리 밖으로 올라가기.
        (
            'from pathlib import Path\nPATH = Path(__file__).parents[2] / "data" / "input"\n',
            ("M07", "error"),
        ),
        ('import os\nPATH = os.path.join("data", "temp", "x.csv")\n', ("M07", "error")),
        (
            "from capa_simulation import module_api as api\nctx = api.context(__file__)\n"
            "PATH = ctx.data_dir.parent\n",
            ("M07", "error"),
        ),
        (
            "from capa_simulation import module_api as api\nctx = api.context(__file__)\n"
            'PATH = ctx.data_dir / ".." / "x.csv"\n',
            ("M07", "error"),
        ),
        ("import threading\n", ("M10", "error")),
        ("import subprocess\n", ("M10", "error")),
        ("from concurrent.futures import ThreadPoolExecutor\n", ("M10", "error")),
        ("import multiprocessing\n", ("M10", "error")),
        ('import os\nos.system("x")\n', ("M10", "error")),
        ("import sys\nsys.exit(1)\n", ("M10", "error")),
        ("exit()\n", ("M10", "error")),
        ("quit()\n", ("M10", "error")),
        ("import os\nos._exit(0)\n", ("M10", "error")),
        ("import argparse\n", ("M10", "warning")),
        ("import asyncio\n", ("M10", "warning")),
        (
            "import streamlit as st\n\n\n@st.fragment(run_every=5)\ndef tick() -> None:\n    "
            "pass\n",
            ("M10", "warning"),
        ),
        ("import pandas as pd\npd.options.mode.copy_on_write = True\n", ("M11", "error")),
        ('import pandas as pd\npd.set_option("display.max_rows", 5)\n', ("M11", "error")),
        ('import os\nos.chdir("..")\n', ("M11", "error")),
        ('import os\nos.environ["X"] = "1"\n', ("M11", "error")),
        ('import os\nos.environ.update({"X": "1"})\n', ("M11", "error")),
        ('import sys\nsys.path.append("x")\n', ("M11", "error")),
        ("import gc\ngc.disable()\n", ("M11", "error")),
        ('import sys\nsys.modules["x"] = sys\n', ("M11", "error")),
        (
            "import logging\nlogging.getLogger().addHandler(logging.NullHandler())\n",
            ("M11", "error"),
        ),
        ("import logging\nlogging.basicConfig(level=10)\n", ("M11", "error")),
        ("import builtins\nbuiltins.print = len\n", ("M11", "error")),
        ('import plotly.io as pio\npio.templates.default = "plotly_dark"\n', ("M11", "error")),
        ('import plotly.express as px\npx.defaults.template = "plotly_dark"\n', ("M11", "error")),
        ('import warnings\nwarnings.filterwarnings("ignore")\n', ("M11", "warning")),
        # 별명으로 비켜 간 캐시 장식자(화면 파일).
        (
            "import streamlit as st\ncache = st.cache_data\n\n\n@cache\ndef load() -> int:\n"
            "    return 1\n",
            ("M12", "error"),
        ),
        (
            "import streamlit as st\n\n\ndef boom() -> None:\n    pass\n\n\n"
            'st.button("x", key="mod_demo_x__b", on_click=boom)\n',
            ("M18", "error"),
        ),
        (
            'import streamlit as st\nst.button("x", key="mod_demo_x__b", on_click=lambda: None)\n',
            ("M18", "error"),
        ),
        # 위치로 넘긴 콜백(`st.button(label, key, help, on_click)`).
        (
            "import streamlit as st\n\n\ndef boom() -> None:\n    pass\n\n\n"
            'st.button("x", "mod_demo_x__b", None, boom)\n',
            ("M18", "error"),
        ),
        (
            "import streamlit as st\nst.dataframe([], use_container_width=True, "
            'key="mod_demo_x__t")\n',
            ("M19", "error"),
        ),
    ],
)
def test_each_forbidden_pattern_is_flagged(
    tmp_path: Path, body: str, expected: tuple[str, str]
) -> None:
    assert expected in _page_rules(tmp_path, body)


@pytest.mark.parametrize(
    "body",
    [
        "from capa_simulation import module_api as api\n",
        "from capa_simulation.module_api import context\n",
        "import capa_simulation.module_api\n",
        "from modules.demo_x import helper\n",
        "import modules.demo_x.helper\n",
        'import pandas as pd\nwith pd.option_context("display.max_rows", 5):\n    pass\n',
        "import streamlit as st\n\n\n@st.fragment\ndef tick() -> None:\n    pass\n",
        'import streamlit as st\nst.markdown("**굵게**")\n',
        'import os\nVALUE = os.environ.get("X", "")\n',
        "from capa_simulation.module_api import ModuleContext, palette\n",
        "from capa_simulation import module_api as api\nCOLORS = api.palette()\n",
        'import importlib\nPANDAS = importlib.import_module("pandas")\n',
        # 마디 경계에서만 맞댄다 — 모듈 데이터 자리 안의 `data/input.csv` 는 코어 자리가 아니다.
        (
            "from capa_simulation import module_api as api\nctx = api.context(__file__)\n"
            'PATH = ctx.data_dir / "data" / "input.csv"\n'
        ),
        "import streamlit as st\nstate = st.session_state\n",
    ],
)
def test_allowed_patterns_raise_nothing(tmp_path: Path, body: str) -> None:
    assert _page_rules(tmp_path, body) == set()


@pytest.mark.parametrize(
    ("body", "flagged"),
    [
        ('import streamlit as st\nst.text_input("x", key="x")\n', True),
        # 위치로 넘긴 키(`st.button(label, key, …)`·`st.checkbox(label, value, key)`).
        ('import streamlit as st\nst.button("x", "plain")\n', True),
        ('import streamlit as st\ncol = st.container()\ncol.checkbox("x", False, "plain")\n', True),
        ('import streamlit as st\nst.button("x", "mod_demo_x__go")\n', False),
        ('import streamlit as st\nst.text_input("x", "기본값")\n', False),
        (
            "import streamlit as st\nfrom capa_simulation import module_api as api\n"
            'ctx = api.context(__file__)\nst.text_input("x", key=ctx.key("x"))\n',
            False,
        ),
        ('import streamlit as st\nst.text_input("x", key="mod_demo_x__a")\n', False),
        # id 가 demo_x 인데 다른 모듈(demo)의 접두다.
        ('import streamlit as st\nst.text_input("x", key="mod_demo__a")\n', True),
        ('import streamlit as st\ni = 1\nst.text_input("x", key=f"row_{i}")\n', True),
        ('import streamlit as st\ni = 1\nst.text_input("x", key=f"mod_demo_x__row_{i}")\n', False),
        ('import streamlit as st\nKEY = "plain"\nst.text_input("x", key=KEY)\n', True),
        ('import streamlit as st\nst.session_state["x"] = 1\n', True),
        ('import streamlit as st\nvalue = st.session_state.get("x")\n', True),
        ('import streamlit as st\nflag = "x" in st.session_state\n', True),
        ("import streamlit as st\nvalue = st.session_state.plain\n", True),
        ('import streamlit as st\nstate = st.session_state\nstate["x"] = 1\n', True),
        ('import streamlit as st\nst.query_params["x"] = "1"\n', True),
        ("import streamlit as st\nst.session_state.clear()\n", True),
        ("import streamlit as st\nst.session_state.popitem()\n", True),
        ('import streamlit as st\nst.session_state.update({"mod_demo_x__a": 1})\n', True),
        (
            "import streamlit as st\nfor k in list(st.session_state):\n    del "
            "st.session_state[k]\n",
            True,
        ),
        (
            "import streamlit as st\nfrom capa_simulation import module_api as api\n"
            'ctx = api.context(__file__)\ndel st.session_state[ctx.key("x")]\n',
            False,
        ),
        # 판정할 수 없는 **읽기**는 넘긴다(지우기만 오류).
        ("import streamlit as st\nname = str(1)\nvalue = st.session_state[name]\n", False),
        # 다른 라이브러리의 key= 는 위젯 키가 아니다.
        ('import pandas as pd\ngrouper = pd.Grouper(key="월")\n', False),
        ("rows = sorted([3, 1], key=abs)\n", False),
    ],
)
def test_m08_judges_the_key_prefix(tmp_path: Path, body: str, flagged: bool) -> None:
    found = _page_rules(tmp_path, body)
    assert (("M08", "error") in found) is flagged, found


def test_m18_accepts_wrapped_and_literal_callbacks(tmp_path: Path) -> None:
    body = (
        "import streamlit as st\nfrom capa_simulation import module_api as api\n"
        "ctx = api.context(__file__)\n\n\ndef boom() -> None:\n    pass\n\n\n"
        'st.button("x", key=ctx.key("b"), on_click=ctx.callback(boom))\n'
        'st.text_input("y", key=ctx.key("y"), on_change="rerun")\n'
        "CALLBACK = ctx.callback(boom)\n"
        'st.button("z", key=ctx.key("z"), on_click=CALLBACK)\n'
    )
    assert ("M18", "error") not in _page_rules(tmp_path, body)


@pytest.mark.parametrize(("callback", "flagged"), [("ctx.callback(save)", False), ("save", True)])
def test_m18_follows_a_callback_named_inside_a_function(
    tmp_path: Path, callback: str, flagged: bool
) -> None:
    """화면을 `def main()` 으로 짜는 꼴 — 함수 안 이름에 담은 감싼 콜백은 통과, 맨 함수는 오류."""
    body = (
        "import streamlit as st\nfrom capa_simulation import module_api as api\n"
        "ctx = api.context(__file__)\n\n\ndef save() -> None:\n    pass\n\n\n"
        f"def main() -> None:\n    handler = {callback}\n"
        '    st.button("x", key=ctx.key("b"), on_click=handler)\n\n\nmain()\n'
    )
    assert (("M18", "error") in _page_rules(tmp_path, body)) is flagged


@pytest.mark.parametrize(
    "body",
    [
        'import sys\nFOUND = sys.modules.get("capa_simulation.auth.access_store")\n',
        'import sys\nFOUND = sys.modules["capa_simulation.auth.access_store"]\n',
        'from sys import modules\nFOUND = modules["capa_simulation.auth.access_store"]\n',
        'import os\nFOUND = os.sys.modules["capa_simulation.auth.access_store"]\n',
        'import sys\nFOUND = getattr(sys, "modules")\n',
        "import sys\nname = str(1)\nFOUND = getattr(sys, name)\n",
        'import importlib\nimportlib.import_module("capa_simulation.auth" + ".access_store")\n',
        "import importlib\nname = str(1)\nimportlib.import_module(name)\n",
        'import importlib\nimportlib.import_module(".x", package="capa_simulation.auth")\n',
        'import importlib\nFOUND = importlib.import_module("capa_simulation.module_api").auth\n',
        'import importlib\nload = importlib.import_module\nload("capa_simulation.auth")\n',
        'import importlib\nFOUND = getattr(importlib, "import_module")\n',
        "name = str(1)\n__import__(name)\n",
        'FOUND = __import__("capa_simulation.module_api").auth\n',
        "load = __import__\n",
        "from capa_simulation import module_api as api\nFOUND = api.context.__globals__\n",
        'from capa_simulation import module_api as api\nFOUND = getattr(api, "__globals__")\n',
        'from capa_simulation import module_api as api\nFOUND = getattr(api, "module_registry")\n',
        "from capa_simulation import module_api as api\nname = str(1)\nFOUND = getattr(api, name)",
        "from capa_simulation import module_api as api\nFOUND = vars(api)\n",
        "FOUND = __builtins__\n",
        'FOUND = globals()["__builtins__"]\n',
        "FOUND = print.__self__\n",
        "FOUND = ().__class__.__bases__[0].__subclasses__()\n",
        'exec("import capa_simulation.auth.access_store")\n',
        'FOUND = eval("1")\n',
        'FOUND = compile("1", "x", "eval")\n',
        'import builtins\nFOUND = builtins.eval("1")\n',
        "import sys\nFOUND = sys._getframe(1).f_globals\n",
        "import inspect\nFOUND = inspect.currentframe()\n",
        "import inspect\nfrom capa_simulation import module_api\nFOUND = inspect.getmembers(1)\n",
        "import gc\nFOUND = gc.get_objects()\n",
        'import importlib.util\nFOUND = importlib.util.spec_from_file_location("x", "y.py")\n',
        'import runpy\nrunpy.run_path("y.py")\n',
        'from pkgutil import resolve_name\nFOUND = resolve_name("capa_simulation.auth")\n',
        'import pydoc\nFOUND = pydoc.locate("capa_simulation.auth")\n',
    ],
)
def test_m06_catches_the_ways_around_the_window(tmp_path: Path, body: str) -> None:
    """모듈은 코어와 한 프로세스다 — 이 길로 세션 비밀 · S3 키 · 명단 쓰기 함수에 닿는다.

    판정할 수 없으면 오류다(점검이 무엇을 불러오는지 모른다). 시험 파일도 같다.
    """
    assert ("M06", "error") in _page_rules(tmp_path / "page", body)
    assert ("M06", "error") in _page_rules(tmp_path / "test", body, rel="tests/test_demo_x_more.py")


@pytest.mark.parametrize(
    "body",
    [
        "import sys\nFOUND = sys.version_info\n",
        'import importlib\nFOUND = importlib.import_module("json")\n',
        'import json\nFOUND = __import__("json")\n',
        'FOUND = getattr(str(1), "upper")\n',
        "name = str(1)\nFOUND = getattr(str(1), name)\n",
        "FOUND = vars(str)\n",
        'import re\nFOUND = re.compile("x")\n',
        'import pandas as pd\nFOUND = pd.DataFrame().eval("a")\n',
        'NOTE = "modules"\n',
        "import gc\nFOUND = gc.collect()\n",
        "from capa_simulation import module_api as api\nctx = api.context(__file__)\n",
    ],
)
def test_m06_leaves_ordinary_code_alone(tmp_path: Path, body: str) -> None:
    assert ("M06", "error") not in _page_rules(tmp_path, body)


_API = "from capa_simulation import module_api as api\n"
_CTX = _API + "ctx = api.context(__file__)\n"


@pytest.mark.parametrize(
    "body",
    [
        _API + 'OTHER = api.ModuleContext("demo_y", "y", "o", "L0", None, (1, 3))\n',
        _API + 'OTHER = api.ModuleContext(id="demo_y", name="y", owner="o", maturity="L0",'
        " folder=None, api_version=(1, 3))\n",
        "from capa_simulation.module_api import ModuleContext\n"
        'OTHER = ModuleContext("demo_y", "y", "o", "L0", None, (1, 3))\n',
        _API + "name = str(1)\nOTHER = api.ModuleContext(name, 'y', 'o', 'L0', None, (1, 3))\n",
        _API + "FIELDS = {}\nOTHER = api.ModuleContext(**FIELDS)\n",
        _CTX + 'import dataclasses\nOTHER = dataclasses.replace(ctx, id="demo_y")\n',
        _CTX + 'from dataclasses import replace\nOTHER = replace(ctx, id="demo_y")\n',
        _API + "import dataclasses\n\n\ndef other(ctx: api.ModuleContext, name: str) -> object:\n"
        "    return dataclasses.replace(ctx, id=name)\n",
        _CTX + "FIELDS = {}\nimport dataclasses\nOTHER = dataclasses.replace(ctx, **FIELDS)\n",
        _CTX + 'OTHER = type(ctx)("demo_y", "y", "o", "L0", None, (1, 3))\n',
        _CTX + 'OTHER = ctx.__class__(id="demo_y", name="y", owner="o", maturity="L0",'
        " folder=None, api_version=(1, 3))\n",
        _CTX + 'object.__setattr__(ctx, "id", "demo_y")\n',
        _API + "\n\ndef other(ctx: api.ModuleContext) -> object:\n"
        '    return api.ModuleContext(ctx.id, "y", "o", "L0", None, (1, 3))\n',
        _API + 'OTHER = api.ModuleContext(api.context("modules/demo_y/page.py").id, "y", "o", "L0",'
        " None, (1, 3))\n",
        _CTX + 'ctx = api.context("modules/demo_y/page.py")\n'
        'OTHER = api.ModuleContext(ctx.id, "y", "o", "L0", None, (1, 3))\n',
        _CTX + "for ctx in []:\n    pass\nimport dataclasses\n"
        "OTHER = dataclasses.replace(ctx, id=ctx.id)\n",
    ],
)
def test_m06_catches_a_hand_made_context_for_another_module(tmp_path: Path, body: str) -> None:
    """이름표를 손으로 지어 남의 id(또는 판정할 수 없는 id)를 쓰면 남의 데이터 자리 · 버킷을 읽고
    덮는다 — M06 오류다(2026-11-12 사용자 답 ④-4 (가)). 시험 파일도 같다."""
    assert ("M06", "error") in _page_rules(tmp_path / "page", body)
    assert ("M06", "error") in _page_rules(tmp_path / "test", body, rel="tests/test_demo_x_more.py")


@pytest.mark.parametrize(
    "body",
    [
        _CTX,
        _API + "\n\ndef title(ctx: api.ModuleContext) -> str:\n    return ctx.name\n",
        _API + "FOUND = isinstance(object(), api.ModuleContext)\n",
        _API + 'OWN = api.ModuleContext("demo_x", "x", "o", "L0", None, (1, 3))\n',
        _CTX + 'import dataclasses\nOWN = dataclasses.replace(ctx, name="다른 이름")\n',
        _CTX + 'import dataclasses\nOWN = dataclasses.replace(ctx, id="demo_x")\n',
        _CTX + 'OWN = api.ModuleContext(ctx.id, "x", "o", "L0", None, (1, 3))\n',
        _CTX + "import dataclasses\nOWN = dataclasses.replace(ctx, id=ctx.id)\n",
        _API + 'OWN = type(api.context(__file__))(api.context(__file__).id, "x", "o", "L0", None,'
        " (1, 3))\n",
        _CTX + 'object.__setattr__(ctx, "id", "demo_x")\n',
        "import dataclasses\n\n\n@dataclasses.dataclass\nclass Row:\n    id: str\n\n\n"
        'ROW = dataclasses.replace(Row("a"), id="b")\n',
        "FOUND = type(1)(2)\n",
        "import dataclasses\n\n\n@dataclasses.dataclass(frozen=True)\nclass Row:\n    id: str\n\n"
        "    def renamed(self, name: str) -> None:\n"
        '        object.__setattr__(self, "id", name)\n',
    ],
)
def test_m06_leaves_the_own_context_alone(tmp_path: Path, body: str) -> None:
    """`api.context(__file__)` · 꼴 표기 · 자기 id(글자 상수 — 모듈 시험의 대역 — 와
    `api.context(__file__)` 로만 묶은 이름표의 `.id`) · 이름표가 아닌 값의 `replace` ·
    `type(…)(…)` 은 넘긴다."""
    assert ("M06", "error") not in _page_rules(tmp_path, body)
    assert ("M06", "error") not in _page_rules(
        tmp_path / "test", body, rel="tests/test_demo_x_more.py"
    )


def test_the_way_around_the_window_stops_the_self_tests(tmp_path: Path) -> None:
    """그 코드를 실행하지 않는다 — M06 은 시험을 돌리기 전에 멈추는 규칙이다."""
    assert "M06" in rules.BLOCKING_RULES


def test_a_same_folder_bare_import_is_m06_not_m09(tmp_path: Path) -> None:
    folder = _module(
        tmp_path / "modules",
        "demo_x",
        {
            "page.py": HEADER + "import helper\nfrom config import THING\n",
            "helper.py": "# Purpose: 도움.\nVALUE = 1\n",
            "config/__init__.py": "# Purpose: 도움 묶음.\nTHING = 1\n",
        },
    )
    found = _static(folder)
    assert found.count("M06 error page.py") == 2
    assert not [item for item in found if item.startswith("M09")]


def test_a_relative_import_in_a_page_file_is_m06(tmp_path: Path) -> None:
    assert ("M06", "error") in _page_rules(tmp_path, "from . import helper\n")


def test_test_files_may_use_pytest_threads_and_monkeypatch(tmp_path: Path) -> None:
    body = (
        "import threading\n\nimport pytest\n\n\n"
        "def test_x(monkeypatch: pytest.MonkeyPatch) -> None:\n"
        '    monkeypatch.setenv("CAPA_MODULES_DATA_ROOT", "x")\n'
        "    assert threading.active_count() >= 1\n"
    )
    assert _page_rules(tmp_path, body, rel="tests/test_demo_x_more.py") == set()


def test_test_files_are_still_held_to_core_data_and_core_imports(tmp_path: Path) -> None:
    body = 'from capa_simulation import settings\n\nPATH = "data/input/x.csv"\n'
    found = _page_rules(tmp_path, body, rel="tests/test_demo_x_more.py")
    assert {("M06", "error"), ("M07", "error")} <= found


def test_helper_files_warn_about_shared_module_state(tmp_path: Path) -> None:
    body = (
        "ROWS: list[int] = []\nCOUNT = 0\n\n\n"
        "def add(value: int) -> None:\n    ROWS.append(value)\n\n\n"
        "def bump() -> None:\n    global COUNT\n    COUNT += 1\n"
    )
    found = _page_rules(tmp_path, body, rel="helper.py")
    assert found == {("M11", "warning")}


# ------------------------------------------------------------------ M09


def _packages(
    *,
    requirements: str,
    distributions: Mapping[str, Sequence[str]],
    company: str = "",
    module_packages: frozenset[str] = frozenset(),
) -> rules.PackageEnvironment:
    return rules.PackageEnvironment(
        requirements=rules.parse_requirements(requirements),
        company=rules.parse_name_list(company),
        module_packages=module_packages,
        distributions=distributions,
    )


REQUIREMENTS = """altair==6.2.2
    # via
    #   capa-simulation
    #   streamlit
pywin32==312 ; sys_platform == 'win32'
    # via xlwings
toml==0.10.2
    # via streamlit
watchdog==6.0.0 ; sys_platform != 'darwin'
    # via streamlit
odd==1.0 ; platform_machine == 'x86_64'
    # via capa-simulation
"""


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("import pandas\n", set()),
        ("import pytest\n", {("M09", "error")}),
        ("import yaml_not_installed_x\n", {("M09", "error")}),
        ("import tomllib\n", {("M09", "error")}),
        ("import toml\n", {("M09", "warning")}),
        # numpy 는 코어 직접 의존(`pyproject.toml`)이라 경고가 없다. 전이 의존 둘은 그대로 경고.
        ("import numpy as np\n", set()),
        ("import pyarrow\n", {("M09", "warning")}),
        ("from PIL import Image\n", {("M09", "warning")}),
    ],
)
def test_m09_with_the_real_requirements(
    tmp_path: Path, body: str, expected: set[tuple[str, str]]
) -> None:
    assert _page_rules(tmp_path, body) == expected


def test_m09_allows_pytest_inside_tests(tmp_path: Path) -> None:
    assert _page_rules(tmp_path, "import pytest\n", rel="tests/test_demo_x_more.py") == set()


def test_m09_a_listed_module_package_is_not_warned(tmp_path: Path) -> None:
    environment = _packages(
        requirements=REQUIREMENTS,
        distributions={"toml": ["toml"]},
        module_packages=frozenset({"toml"}),
    )
    assert _page_rules(tmp_path, "import toml\n", environment=environment) == set()
    plain = _packages(requirements=REQUIREMENTS, distributions={"toml": ["toml"]})
    assert _page_rules(tmp_path / "again", "import toml\n", environment=plain) == {
        ("M09", "warning")
    }


@pytest.mark.parametrize(
    ("body", "distributions", "expected"),
    [
        ("import altair\n", {"altair": ["altair"]}, set()),
        # 표지가 Linux 에서 거짓 — 사내 Windows 에서는 통과하고 CD 에서는 import 오류.
        ("import win32com\n", {"win32com": ["pywin32"]}, {("M09", "error")}),
        ("import watchdog\n", {"watchdog": ["watchdog"]}, {("M09", "warning")}),
        # 따질 수 없는 표지는 경고.
        ("import odd\n", {"odd": ["odd"]}, {("M09", "warning")}),
        ("import bigdataquery\n", {"bigdataquery": ["bigdataquery"]}, {("M09", "warning")}),
        ("import missing_x\n", {"missing_x": ["missing-x"]}, {("M09", "error")}),
    ],
)
def test_m09_reads_markers_direct_dependencies_and_company_only_names(
    tmp_path: Path,
    body: str,
    distributions: Mapping[str, Sequence[str]],
    expected: set[tuple[str, str]],
) -> None:
    environment = _packages(
        requirements=REQUIREMENTS,
        distributions=distributions,
        company="--index-url https://example.invalid/simple\nbigdataquery==2.5.0\n",
    )
    assert _page_rules(tmp_path, body, environment=environment) == expected


@pytest.mark.parametrize(
    ("marker", "expected"),
    [
        ("", True),
        ("sys_platform == 'win32'", False),
        ("sys_platform != 'darwin'", True),
        ("platform_system == 'Linux' and os_name == 'posix'", True),
        ("sys_platform == 'win32' or sys_platform == 'linux'", True),
        ("python_version < '3.11'", True),
        ("python_full_version >= '3.12'", False),
        ("platform_machine == 'x86_64'", None),
    ],
)
def test_markers_are_judged_for_linux(marker: str, expected: bool | None) -> None:
    assert rules.marker_on_linux(marker) is expected


def test_the_requirements_parser_reads_via_groups() -> None:
    parsed = rules.parse_requirements(REQUIREMENTS)
    assert parsed["altair"].direct is True
    assert parsed["toml"].direct is False
    assert parsed["pywin32"].marker == "sys_platform == 'win32'"


# ------------------------------------------------------------------ M12


def test_a_cache_in_a_page_file_is_an_error(tmp_path: Path) -> None:
    body = (
        "import streamlit as st\n\n\n@st.cache_data(ttl=60)\n"
        "def load(name: str) -> str:\n    return name\n"
    )
    assert ("M12", "error") in _page_rules(tmp_path, body)


def test_a_bounded_cache_in_cache_py_passes(tmp_path: Path) -> None:
    body = (
        "from pathlib import Path\n\nimport streamlit as st\n\n\n@st.cache_data(ttl=60)\n"
        "def load(folder: Path, name: str) -> bytes:\n    return (folder / name).read_bytes()\n\n\n"
        "def forget() -> None:\n    load.clear()\n"
    )
    assert _page_rules(tmp_path, body, rel="cache.py") == set()


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            "import streamlit as st\n\n\n@st.cache_data\ndef load() -> int:\n    return 1\n",
            ("M12", "error"),
        ),
        (
            "import streamlit as st\n\n\n@st.cache_resource()\ndef load() -> int:\n    return 1\n",
            ("M12", "error"),
        ),
        (
            "import streamlit as st\nfrom capa_simulation import module_api as api\n\n"
            "ctx = api.context(__file__)\n\n\n@st.cache_data(max_entries=4)\n"
            'def load() -> bytes:\n    return (ctx.data_dir / "a").read_bytes()\n',
            ("M12", "error"),
        ),
        (
            "import streamlit as st\nfrom capa_simulation import module_api as api\n\n\n"
            "@st.cache_data(max_entries=4)\n"
            "def load() -> str:\n    return api.context(__file__).id\n",
            ("M12", "error"),
        ),
        ("import streamlit as st\nst.cache_data.clear()\n", ("M12", "error")),
        ("import streamlit as st\nst.cache_resource.clear()\n", ("M12", "error")),
        (
            "import streamlit as st\nfrom capa_simulation import module_api as api\n\n\n"
            "@st.cache_data(ttl=60)\n"
            'def colors() -> str:\n    return api.palette()["accent"]\n',
            ("M12", "warning"),
        ),
    ],
)
def test_m12_cache_rules_in_cache_py(tmp_path: Path, body: str, expected: tuple[str, str]) -> None:
    assert expected in _page_rules(tmp_path, body, rel="cache.py")


def test_the_same_cached_page_source_in_two_modules_fails_both(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "modules"
    page = (
        HEADER + "import pandas as pd\nimport streamlit as st\n"
        "from capa_simulation import module_api as api\n\n"
        "ctx = api.context(__file__)\n\n\n@st.cache_data(ttl=600, max_entries=8)\n"
        "def load(name: str) -> pd.DataFrame:\n    return pd.read_csv(ctx.data_dir / name)\n"
    )
    _module(root, "demo_a", {"page.py": page})
    _module(root, "demo_b", {"page.py": page.replace("demo_a", "demo_b")})

    code, out = _run(["--all", "--root", str(root), "--no-ruff", "--no-tests"], capsys)

    assert code == 1
    for number, name in ((1, "demo_a"), (2, "demo_b")):
        line = next(item for item in out.splitlines() if item.startswith(f"- m{number} {name} "))
        assert "실패" in line and "M12" in line, line


# ------------------------------------------------------------------ M13 · M14


def test_m13_file_rules(tmp_path: Path) -> None:
    folder = _module(
        tmp_path / "modules",
        "demo_x",
        {
            "page.py": HEADER + "import streamlit as st\n",
            "no_header.py": "VALUE = 1\n",
            "legacy.py": "# Purpose: 옛 글.\nVALUE = '가'\n".encode("cp949"),
            "notes.txt": "가나다".encode("cp949"),
            "run.ps1": "Write-Host x\n",
            "local.duckdb": b"",
            "model.pkl": b"",
            "style.css": "body {}\n",
            "page.html": "<p></p>\n",
            "rows.csv": "a,b\n",
            "assets/sample.csv": "a,b\n",
            "Upper.py": "# Purpose: 대문자.\n",
            "writer.py": (
                "# Purpose: 쓰기.\nfrom pathlib import Path\n\nHERE = Path(__file__).parent\n\n\n"
                'def save() -> None:\n    (HERE / "out.txt").write_text("x", encoding="utf-8")\n'
                '    with open(Path(__file__).parent / "log.txt", "a", encoding="utf-8") as f:\n'
                '        f.write("x")\n'
            ),
        },
    )
    found = _static(folder)

    for expected in [
        "M13 error no_header.py",
        "M13 error legacy.py",
        "M13 error notes.txt",
        "M13 error run.ps1",
        "M13 error local.duckdb",
        "M13 error model.pkl",
        "M13 error style.css",
        "M13 error page.html",
        "M13 error rows.csv",
        "M13 warning assets/sample.csv",
        "M13 error Upper.py",
        "M13 warning writer.py",
    ]:
        assert expected in found, (expected, found)
    assert found.count("M13 warning writer.py") == 2
    assert "M13 error page.py" not in found
    assert "M13 error README.md" not in found


def test_m13_writing_into_ctx_data_dir_is_not_a_code_folder_write(tmp_path: Path) -> None:
    """문맥은 `api.context(__file__)` 로 만들지만 `ctx.data_dir` 는 데이터 자리다 — 지침서가
    권하는 쓰기(`(ctx.data_dir / "x").write_bytes(…)`)에 「코드 폴더에 쓴다」 경고를 내면 안
    된다. `ctx.folder` 로 쓰는 것만 경고다."""
    body = (
        "from capa_simulation import module_api as api\n\n"
        "ctx = api.context(__file__)\n"
        "TARGET = ctx.data_dir / 'b.csv'\n\n\n"
        "def save() -> None:\n"
        '    (ctx.data_dir / "a.csv").write_bytes(b"x")\n'
        '    TARGET.write_text("x", encoding="utf-8")\n'
        '    (ctx.folder / "c.csv").write_text("x", encoding="utf-8")\n'
    )
    folder = _module(tmp_path / "modules", "demo_x", {"page.py": HEADER + body})
    result = rules.check_module_folder(
        folder, module_id="demo_x", pages=["page.py"], environment=ENVIRONMENT, git=None
    )
    writes = [item for item in result.findings if item.rule == "M13" and item.level == "warning"]

    assert [item.line for item in writes] == [11], [item.text() for item in writes]


def test_m13_a_relative_path_write_lands_in_the_working_folder(tmp_path: Path) -> None:
    """상대 경로 쓰기는 앱에서 작업 폴더(운영 체크아웃 뿌리)에 말없이 남는다 — 글자 · 모듈 수준
    이름 · `Path(…)` · `Path(…) / …` · 표 쓰기 모두 경고다. `ctx.data_dir` · 절대 경로 · 읽기는
    넘기고, `data/` 로 시작하는 글자는 M07 이 알린다."""
    body = (
        "from pathlib import Path\n\n"
        "import pandas as pd\n\n"
        "from capa_simulation import module_api as api\n\n"
        "ctx = api.context(__file__)\n"
        'NOTE_PATH = "probe_notes.txt"\n\n\n'
        "def save(frame: pd.DataFrame) -> None:\n"
        '    with open(NOTE_PATH, "a", encoding="utf-8") as handle:\n'
        '        handle.write("x")\n'
        '    Path("out.txt").write_text("x", encoding="utf-8")\n'
        '    (Path("out") / "x.txt").write_text("x", encoding="utf-8")\n'
        '    frame.to_csv("rows.csv")\n'
        '    (ctx.data_dir / "a.csv").write_bytes(b"x")\n'
        '    Path("/srv/x.txt").write_text("x", encoding="utf-8")\n'
        '    open(NOTE_PATH, encoding="utf-8").close()\n'
        '    Path("data/x.txt").write_text("x", encoding="utf-8")\n'
    )
    folder = _module(tmp_path / "modules", "demo_x", {"page.py": HEADER + body})
    result = rules.check_module_folder(
        folder, module_id="demo_x", pages=["page.py"], environment=ENVIRONMENT, git=None
    )
    writes = sorted(
        (item for item in result.findings if item.rule == "M13" and item.level == "warning"),
        key=lambda item: item.line,
    )

    assert [item.line for item in writes] == [13, 15, 16, 17], [item.text() for item in writes]
    assert "상대 경로 `probe_notes.txt`" in writes[0].message
    assert 'ctx.data_dir / "<이름>"' in writes[0].message
    assert ("M07", "warning") in {(item.rule, item.level) for item in result.findings}


def test_m13_a_python_310_syntax_error(tmp_path: Path) -> None:
    assert ("M13", "error") in _page_rules(tmp_path, "def broken(:\n    pass\n")


def test_m13_a_source_with_a_null_byte_is_an_error_not_a_crash(tmp_path: Path) -> None:
    """`ast.parse` 는 널 글자에 `SyntaxError` 가 아니라 `ValueError` 를 낸다 — 점검이 죽으면 런북
    4-5 의 블록·요약이 통째로 없어진다."""
    assert ("M13", "error") in _page_rules(tmp_path, "x = 1\x00\n")


def test_one_module_crashing_the_checker_does_not_hide_the_others(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "modules"
    _fixture_copy(root, "demo_ok")
    _module(root, "demo_x", {"page.py": HEADER + "import streamlit as st\n"})
    real = rules.check_module_folder

    def flaky(folder: Path, **kwargs: object) -> rules.StaticResult:
        if folder.name == "demo_x":
            raise RuntimeError("점검 안 예외")
        return real(folder, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(rules, "check_module_folder", flaky)

    code, out = _run(["--all", "--root", str(root), "--no-ruff", "--no-tests"], capsys)

    assert code == 1, out
    assert "- m1 demo_ok 통과" in out
    assert "  m2 demo_x 오류 M13 * 점검 중 예외 RuntimeError" in out
    assert "모듈 2 = 통과 1 + 꺼짐 0 + 실패 1" in _summary(out)


def test_m14_a_module_without_tests(tmp_path: Path) -> None:
    folder = _module(
        tmp_path / "modules",
        "demo_x",
        {"page.py": HEADER + "import streamlit as st\n"},
        smoke=False,
    )
    assert "M14 error tests" in _static(folder)


def _git(repository: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repository), *args], check=True, capture_output=True)


def _git_repository(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "demo@example.invalid")
    _git(path, "config", "user.name", "demo")
    _git(path, "config", "commit.gpgsign", "false")
    return path


def test_m13_git_ignored_files_and_case_only_renames(tmp_path: Path) -> None:
    repository = _git_repository(tmp_path / "repo")
    (repository / ".gitignore").write_text("*.log\n", encoding="utf-8")
    folder = _module(
        repository / "modules",
        "demo_x",
        {
            "page.py": HEADER + 'LOG = "assets/sample.log"\n',
            "Other.py": "# Purpose: 대문자로 커밋한 파일.\n",
            "assets/sample.log": "x\n",
        },
    )
    _git(repository, "add", ".gitignore", "modules")
    _git(repository, "commit", "-q", "-m", "견본")
    # Windows 의 core.ignorecase 에서 `git mv` 없이 이름을 바꾼 꼴 — 인덱스는 옛 철자다.
    (folder / "Other.py").rename(folder / "other.py")

    found = _static(folder)

    assert "M13 warning assets/sample.log" in found
    assert "M13 error page.py" in found
    assert "M13 error other.py" in found


def test_git_checks_are_skipped_outside_a_work_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "modules"
    _module(root, "demo_x", {"page.py": HEADER + "import streamlit as st\n"})
    _, out = _run(["--all", "--root", str(root), "--no-ruff", "--no-tests"], capsys)
    assert "git 검사 건너뜀(사본)" in out


# ------------------------------------------------------------------ M20

# 첫 회차에 스스로 연 닫을 수 없는 팝업 — 처음 들어온 사람에게는 입장 화면 밑에 숨어 앱을 묶는다.
LOCKED_POPUP = """import streamlit as st

from capa_simulation import module_api as api

ctx = api.context(__file__)


@st.dialog("데모 안내", dismissible=False)
def _notice() -> None:
    with ctx.guard():
        st.write("합성 안내 42")


_notice()
"""


@pytest.mark.parametrize(
    "body",
    [
        LOCKED_POPUP,
        'import streamlit as st\nflag = len("x") > 1\nnotice = st.dialog("x", dismissible=flag)\n',
        'from streamlit import dialog\n\n\n@dialog("x", dismissible=0)\ndef notice() -> None:\n'
        "    pass\n",
    ],
)
def test_m20_warns_about_a_popup_that_cannot_be_closed(tmp_path: Path, body: str) -> None:
    assert _page_rules(tmp_path, body) == {("M20", "warning")}


@pytest.mark.parametrize(
    "body",
    [
        'import streamlit as st\n\n\n@st.dialog("x")\ndef notice() -> None:\n    pass\n',
        'import streamlit as st\n\n\n@st.dialog("x", dismissible=True)\ndef notice() -> None:\n'
        "    pass\n",
    ],
)
def test_m20_passes_a_popup_that_can_be_closed(tmp_path: Path, body: str) -> None:
    assert _page_rules(tmp_path, body) == set()


def test_m20_does_not_look_at_module_tests(tmp_path: Path) -> None:
    assert _page_rules(tmp_path, LOCKED_POPUP, rel="tests/test_demo_x_more.py") == set()


def test_m20_is_a_warning_that_keeps_the_module_passing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "modules"
    _module(root, "demo_popup", {"page.py": "# Purpose: 데모 팝업 화면.\n\n" + LOCKED_POPUP})

    code, out = _run(["demo_popup", "--root", str(root), "--no-ruff", "--no-tests"], capsys)

    assert code == 0, out
    assert "- m1 demo_popup 통과 · L0 · API 1.0 · 화면 1 · 오류 0 · 경고 1 · " in out
    detail = next(line for line in out.splitlines() if " M20 " in line)
    assert detail.startswith("  m1 demo_popup 경고 M20 page.py:")
    assert "`st.dialog(dismissible=False)`" in detail and "입장 화면" in detail
    assert _summary(out).endswith("ng 없음")


# ------------------------------------------------------------------ M21


# 자격 · 비밀(2026-11-12 사용자 결정 「도우미 함수로」) — 계정 · 토큰 · 키는 코어가 쥐고 모듈은
# 도우미만 부른다. 환경변수 이름은 글자 전체가 이름 꼴일 때, 토큰 파일 자리는 경로 마디일 때
# 잡는다(열 이름 · 설명 글 안의 낱말은 아니다 — 오류라 시험을 막으므로 넓게 잡지 않는다).
@pytest.mark.parametrize(
    "body",
    [
        'import os\nKEY = os.environ["CAPA_S3_SECRET_KEY"]\n',
        'import os\nUSER = os.environ.get("CAPA_BDQ_USER_NAME", "")\n',
        'import os\nMODE = os.getenv("CAPA_S3_SYNC_MODE")\n',
        'import os\nKEY = os.getenv("aws_secret_access_key")\n',
        'from os import environ\nSECRET = environ["JWT_SECRET_KEY"]\n',
        'import os\nCLIENT = os.environ["ADFS_CLIENT_ID"]\n',
        'import os\nPREFIX = "CAPA_S3_"\nNAMES = [n for n in os.environ if n.startswith(PREFIX)]\n',
        'import os\npart = "KEY"\nKEY = os.environ[f"CAPA_S3_{part}"]\n',
        'import os\nTEXT = os.path.expandvars("${AWS_PROFILE}")\n',
        'TOKEN = "/config/.credential/bigdataquery.token.demo"\n',
        'from pathlib import Path\nFOLDER = Path("/config") / ".credential"\n',
        'NAME = "bigdataquery.token.demo"\n',
        'user = "demo"\nNAME = f"bigdataquery.token.{user}"\n',
        'FOLDER = "C:\\\\Users\\\\demo\\\\.credential"\n',
        'FOLDER = "~/.credential/"\n',
    ],
)
def test_m21_blocks_credential_names_and_token_places(tmp_path: Path, body: str) -> None:
    assert ("M21", "error") in _page_rules(tmp_path, body)


@pytest.mark.parametrize(
    "body",
    [
        'import os\nROOT = os.environ.get("CAPA_MODULES_DATA_ROOT", "")\n',
        'LABEL = "AWS 계정은 코어가 쥔다"\n',
        'COLUMN = "aws"\n',
        'NAME = "credentials.csv"\n',
        'NAME = "MY_AWS_KEY"\n',
        'SQL = "SELECT * FROM db.credential_log"\n',
        '"""토큰(.credential) 을 읽지 않는다."""\n',
        'NAME = "user.credentials"\n',
        'NAME = "demo/.credentials/x"\n',
        'TEXT = "bigdataquery.token 은 코어가 쥔다"\n',
        'COLUMN = "bigdataquery.tokens"\n',
    ],
)
def test_m21_leaves_other_text_alone(tmp_path: Path, body: str) -> None:
    assert ("M21", "error") not in _page_rules(tmp_path, body)


def test_m21_looks_at_module_tests_too(tmp_path: Path) -> None:
    body = 'def test_x(monkeypatch) -> None:\n    monkeypatch.setenv("CAPA_S3_BUCKET", "x")\n'
    assert ("M21", "error") in _page_rules(tmp_path, body, rel="tests/test_demo_x_more.py")


def test_m21_is_blocking_and_names_the_helpers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "modules"
    body = 'import os\n\nUSER = os.environ.get("CAPA_BDQ_USER_NAME", "")\n'
    _module(root, "demo_x", {"page.py": HEADER + body})
    monkeypatch.setattr(check_module, "run_tests", _must_not_run)

    code, out = _run(["demo_x", "--root", str(root), "--no-ruff"], capsys)

    assert code == 1
    assert "M21" in rules.BLOCKING_RULES
    assert "시험 안 돎 — 정적 오류 먼저" in out
    detail = next(line for line in out.splitlines() if " M21 " in line)
    assert detail.startswith("  m1 demo_x 오류 M21 page.py:4 ")
    assert "`CAPA_BDQ_USER_NAME`" in detail and "`api.query_bigdataquery`" in detail


HELPER_TESTS = """# Purpose: 모듈 시험 안에서 코어 도우미가 밖에 닿지 않는지 본다.

import pytest

from capa_simulation import module_api as api


def test_the_helpers_stay_inside() -> None:
    ctx = api.context(__file__)
    (ctx.data_dir / "x.csv").write_text("a\\n", encoding="utf-8")
    assert api.s3_upload(ctx, "x.csv") == api.S3Result(False, "쓸 수 없음", "모듈 시험")
    assert api.s3_download(ctx, "x.csv").detail == "모듈 시험"
    with pytest.raises(api.BigDataQueryError) as caught:
        api.query_bigdataquery(ctx, "SELECT 1")
    assert caught.value.kind == "쓸 수 없음"
"""


def test_m17_module_tests_run_with_the_helpers_kept_inside(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """앱 관리자 PC 의 점검(런북 4-5 · 4-6)이 모듈 시험으로 진짜 조회 · 버킷에 닿지 않는다."""
    root = tmp_path / "modules"
    folder = _module(root, "demo_x", {"page.py": HEADER + "import streamlit as st\n"})
    (folder / "tests" / "test_demo_x_helpers.py").write_text(HELPER_TESTS, encoding="utf-8")

    code, out = _run(["demo_x", "--root", str(root), "--no-ruff"], capsys)

    assert code == 0, out
    assert "시험 2 통과" in out


def test_m09_points_a_direct_bigdataquery_import_at_the_helper(tmp_path: Path) -> None:
    """직접 import 는 2026-11-01 결정대로 경고 그대로다 — 글만 창구 도우미를 가리킨다."""
    environment = _packages(
        requirements=REQUIREMENTS,
        distributions={"bigdataquery": ["bigdataquery"]},
        company="bigdataquery==2.5.0\n",
    )
    files = {"page.py": HEADER + "import bigdataquery\n"}
    folder = _module(tmp_path / "modules", "demo_x", files)
    result = rules.check_module_folder(
        folder, module_id="demo_x", pages=["page.py"], environment=environment, git=None
    )
    [finding] = [item for item in result.findings if item.rule == "M09"]
    assert finding.level == "warning"
    assert "`api.query_bigdataquery`" in finding.message


# ------------------------------------------------------------------ ruff · 시험


def test_m15_and_m16_count_ruff_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "modules"
    long_line = "VALUE = " + repr("x" * 120) + "\n"
    _module(root, "demo_x", {"page.py": HEADER + long_line + "y=1\n"})

    code, out = _run(["demo_x", "--root", str(root), "--no-tests"], capsys)

    assert code == 1
    assert "  m1 demo_x 오류 M15 page.py:2 E501" in out
    assert "  m1 demo_x 오류 M16 page.py" in out
    line = next(item for item in out.splitlines() if item.startswith("- m1 "))
    assert "ruff 2" in line


def test_m17_a_failing_module_test(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "modules"
    folder = _module(root, "demo_x", {"page.py": HEADER + "import streamlit as st\n"})
    (folder / "tests" / "test_demo_x_fail.py").write_text(
        "# Purpose: 일부러 실패.\n\n\ndef test_fails() -> None:\n    assert 1 == 2\n",
        encoding="utf-8",
    )

    code, out = _run(["demo_x", "--root", str(root), "--no-ruff"], capsys)

    assert code == 1
    assert "시험 실패 1/2" in out
    assert "  m1 demo_x 오류 M17 시험 실패 test_demo_x_fail.py::test_fails" in out
    assert "시험실패1/2" in _summary(out)


SECRET_READING_TESTS = """# Purpose: 일부러 키 자리를 연다.

from pathlib import Path


def test_reads_the_aws_folder() -> None:
    folder = Path.home() / (".a" + "ws")
    assert (folder / "credentials").read_text(encoding="utf-8")
"""


def test_m17_the_watch_stops_a_module_test_reading_the_aws_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """정적 규칙을 피해 돌리는 길로 열어도 막는다. `~/.aws` 에는 운영 DB 를 지우는 키가 있다."""
    home = tmp_path / "home"
    folder = home / ".aws"
    folder.mkdir(parents=True)
    (folder / "credentials").write_text("[demo]\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    root = tmp_path / "modules"
    module = _module(root, "demo_x", {"page.py": HEADER + "import streamlit as st\n"})
    (module / "tests" / "test_demo_x_keys.py").write_text(SECRET_READING_TESTS, encoding="utf-8")

    code, out = _run(["demo_x", "--root", str(root), "--no-ruff"], capsys)

    assert code == 1
    assert "감시가 막은 접근" in out
    assert "test_demo_x_keys.py::test_reads_the_aws_folder" in out


ENVIRONMENT_READING_TESTS = """# Purpose: 일부러 환경의 커널 사본을 연다.

from pathlib import Path


def test_reads_the_kernel_copy() -> None:
    assert Path("/pr" + "oc/self/environ").read_bytes()
"""


@pytest.mark.skipif(not Path("/proc/self/environ").exists(), reason="리눅스 전용 자리")
def test_m17_the_watch_stops_a_module_test_reading_the_kernel_copy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "modules"
    module = _module(root, "demo_x", {"page.py": HEADER + "import streamlit as st\n"})
    (module / "tests" / "test_demo_x_env.py").write_text(
        ENVIRONMENT_READING_TESTS, encoding="utf-8"
    )

    code, out = _run(["demo_x", "--root", str(root), "--no-ruff"], capsys)

    assert code == 1
    assert "감시가 막은 접근" in out


def test_the_process_environment_file_is_on_the_watch_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """시작 스크립트가 넘긴 키는 `os.environ` 에서 지워도 커널 사본에 남는다."""
    seen: list[Sequence[Path]] = []

    def record(
        folder: Path, *, root: Path, tree: Path, protect: Sequence[Path], timeout: int
    ) -> check_module.TestResult:
        seen.append(protect)
        return check_module.TestResult(state="skipped")

    monkeypatch.setattr(check_module, "run_tests", record)
    root = tmp_path / "modules"
    _module(root, "demo_x", {"page.py": HEADER + "import streamlit as st\n"})

    _run(["demo_x", "--root", str(root), "--no-ruff"], capsys)

    assert Path("/proc/self/environ") in seen[0]
    assert Path.home() / ".aws" in seen[0]
    assert Path("/config/.credential") in seen[0]


def test_m17_is_not_run_when_a_blocking_static_error_exists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "modules"
    _module(root, "demo_x", {"page.py": HEADER + 'PATH = "data/input/x.csv"\n'})
    monkeypatch.setattr(check_module, "run_tests", _must_not_run)

    code, out = _run(["demo_x", "--root", str(root), "--no-ruff"], capsys)

    assert code == 1
    assert "시험 안 돎 — 정적 오류 먼저" in out
    assert "ng m1 오류1.시험안돎" in _summary(out)


def test_the_module_test_imports_the_checked_copy_of_its_helpers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "modules"
    folder = _module(
        root,
        "demo_helper",
        {
            "page.py": HEADER + "from modules.demo_helper import helper\n\nVALUE = helper.VALUE\n",
            "helper.py": "# Purpose: 도움.\nVALUE = 1\n",
        },
    )
    (folder / "tests" / "test_demo_helper_where.py").write_text(
        "# Purpose: 도움 코드를 어디서 부르는지 본다.\n\nimport os\nfrom pathlib import Path\n\n"
        "from modules.demo_helper import helper\n\n\n"
        "def test_the_helper_comes_from_the_checked_root() -> None:\n"
        "    expected = Path(__file__).resolve().parents[1] / 'helper.py'\n"
        "    assert Path(helper.__file__).resolve() == expected\n"
        f'    assert os.environ["CAPA_MODULES_ROOT"] == {str(root)!r}\n'
        '    data = Path(os.environ["CAPA_MODULES_DATA_ROOT"])\n'
        "    assert data.is_dir()\n"
        f"    assert {str(PROJECT_ROOT)!r} not in str(data)\n",
        encoding="utf-8",
    )

    code, out = _run(["demo_helper", "--root", str(root), "--no-ruff"], capsys)

    assert code == 0, out
    assert "시험 2 통과" in out


def test_the_module_test_environment_points_at_the_checked_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("CAPA_S3_SECRET_KEY", "CAPA_BDQ_USER_NAME", "AWS_PROFILE", "JWT_SECRET_KEY"):
        monkeypatch.setenv(name, "demo-value")
    monkeypatch.setenv("adfs_client_id", "demo-value")
    root = tmp_path / "modules"
    data = tmp_path / "data-root"
    environment = check_module.module_test_environment(root=root, tree=PROJECT_ROOT, data_root=data)
    front = environment["PYTHONPATH"].split(":" if sys.platform != "win32" else ";")
    assert front[:2] == [str(tmp_path), str(PROJECT_ROOT / "src")]
    assert environment["CAPA_MODULES_DATA_ROOT"] == str(data)
    assert environment["CAPA_MODULES_ROOT"] == str(root)
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
    assert "CAPA_MODULES_DISABLED" not in environment
    # 모듈 시험은 자격 이름(M21)의 변수를 받지 않고, 창구 도우미가 밖에 닿지 않게 표지를 켠다.
    assert not [
        name for name in environment if name.upper().startswith(rules.CREDENTIAL_ENV_PREFIXES)
    ]
    assert environment[module_registry.TEST_RUN_ENV_VAR] == "1"


# ------------------------------------------------------------------ 결과 블록 · 요약 · 종료 코드


def test_the_block_shape_numbers_and_summary_without_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "modules"
    _fixture_copy(root, "demo_ok", smoke=False)
    _fixture_copy(root, "demo_off", smoke=False)
    _fixture_copy(root, "demo_keys", smoke=False)

    code, out = _run(["--all", "--root", str(root), "--no-ruff", "--no-tests"], capsys)

    lines = out.splitlines()
    assert code == 1
    assert lines[0] == f"모듈 점검 — 뿌리 {root.as_posix()}/ · 3개 = 통과 0 + 꺼짐 1 + 실패 2"
    # 모듈 order → id 차례(demo_ok 10 · demo_keys 30 · demo_off 100).
    assert [line.split()[1:3] for line in lines if line.startswith("- m")] == [
        ["m1", "demo_ok"],
        ["m2", "demo_keys"],
        ["m3", "demo_off"],
    ]
    assert "판 분포: api1 3" in lines
    assert "제3자 패키지: pandas" in lines
    summary = _summary(out)
    assert summary == (
        "전송용 요약: 모듈 3 = 통과 0 + 꺼짐 1 + 실패 2; api1 3; 패키지 pandas; ng m1 오류1, m2 "
        "오류2"
    )
    for name in ("demo_ok", "demo_keys", "demo_off"):
        assert name not in summary
    assert inspect_real_data_checks.check_transcript([summary]) == []


def test_worktree_counts_include_an_unstaged_first_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = _git_repository(tmp_path / "operational")
    page = repository / "modules" / "demo_x" / "page.py"
    page.parent.mkdir(parents=True)
    page.write_text(HEADER, encoding="utf-8")
    _git(repository, "add", "modules")
    _git(repository, "commit", "-q", "-m", "견본")
    # 첫 레코드가 스테이징 안 된 수정(` M modules/…`)이다 — 앞 칸을 strip() 하면 경로가 깨진다.
    page.write_text(HEADER + "VALUE = 1\n", encoding="utf-8")
    (repository / "modules" / "demo_x" / "new_a.py").write_text(HEADER, encoding="utf-8")
    (repository / "modules" / "demo_y").mkdir()
    (repository / "modules" / "demo_y" / "new_b.py").write_text(HEADER, encoding="utf-8")
    state = check_module.worktree_state(repository)
    assert state.modified == ("modules/demo_x/page.py",)

    root = tmp_path / "copy" / "modules"
    _module(root, "demo_x", {"page.py": HEADER + "import streamlit as st\n"})
    code, out = _run(
        ["--all", "--root", str(root), "--worktree-of", str(repository), "--no-ruff", "--no-tests"],
        capsys,
    )

    assert code == 0, out
    assert "운영 체크아웃 modules/ — 커밋 안 한 수정 1 · 추적 안 된 파일 2" in out
    assert "작업트리 1+2" in _summary(out)
    assert "  운영 체크아웃 커밋 안 한 수정 modules/demo_x/page.py" in out


def test_a_root_not_named_modules_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "plugins").mkdir()
    code, _ = _run(["--all", "--root", str(tmp_path / "plugins")], capsys)
    assert code == 2


def test_ids_and_all_are_mutually_exclusive_and_unknown_ids_are_usage_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "modules"
    root.mkdir()
    assert _run(["--root", str(root)], capsys)[0] == 2
    assert _run(["demo_x", "--all", "--root", str(root)], capsys)[0] == 2
    assert _run(["demo_x", "--root", str(root)], capsys)[0] == 2


@pytest.mark.parametrize("exists", [True, False])
def test_an_empty_or_missing_root_reports_no_modules(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], exists: bool
) -> None:
    root = tmp_path / "modules"
    if exists:
        root.mkdir()
    code, out = _run(["--all", "--root", str(root)], capsys)
    assert code == 0
    assert _summary(out) == "전송용 요약: 모듈 없음"
    assert out.splitlines()[0].endswith("모듈 없음" if exists else " 없음")


def test_environment_switches_are_reported_but_not_followed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "modules"
    _module(root, "demo_x", {"page.py": HEADER + "import streamlit as st\n"})
    monkeypatch.setenv("CAPA_MODULES_DISABLED", "demo_x")

    code, out = _run(["--all", "--root", str(root), "--no-ruff", "--no-tests"], capsys)

    assert code == 0, out
    assert "환경변수 " in out and "CAPA_MODULES_DISABLED=demo_x" in out
    assert "- m1 demo_x 통과" in out


def test_the_output_option_writes_the_same_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "modules"
    _module(root, "demo_x", {"page.py": HEADER + "import streamlit as st\n"})
    target = tmp_path / "module_check.md"

    _, out = _run(
        ["--all", "--root", str(root), "--no-ruff", "--no-tests", "--output", str(target)], capsys
    )

    assert target.read_text(encoding="utf-8") == out


def test_the_rule_table_lists_m01_to_m21() -> None:
    assert list(rules.RULES) == [f"M{number:02d}" for number in range(1, 22)]
    assert rules.BLOCKING_RULES == {"M01", "M06", "M07", "M10", "M11", "M21"}


def test_a_regular_package_file_at_the_modules_root_is_warned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "modules"
    _module(root, "demo_x", {"page.py": HEADER + "import streamlit as st\n"})
    (root / "__init__.py").write_text("", encoding="utf-8")

    code, out = _run(["--all", "--root", str(root), "--no-ruff", "--no-tests"], capsys)

    assert code == 0, out
    assert "경고 M13 modules/__init__.py 가 있습니다" in out
