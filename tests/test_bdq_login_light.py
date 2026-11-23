# Purpose: BDQ 로그인 하위 프로세스의 가벼운 불러오기 길 시험 — 판 고정 · 전체로 돌아감 · 길 칸.

"""가벼운 불러오기 길 시험(`io/bdq_login_child.py` · `io/bdq_login.py`).

가벼운 길은 진짜 하위 프로세스로만 태운다 — 시험 프로세스 안에서 돌리면 빈 꾸러미와
`pyarrow` 막음이 시험 프로세스의 `sys.modules` 에 심긴다. 가짜 패키지는
`tests/bdq_light_support.py` 가 시험마다 임시 자리에 짓는다. 값은 모두 합성이다.
"""

from __future__ import annotations

import io
import os
import sys
import types
from collections.abc import Iterator
from pathlib import Path

import pytest
from bdq_light_support import OTHER_VERSION, build_light_package
from bdq_login_support import (
    ACCOUNT,
    ADMIN_ID,
    PASSWORD,
    FakeBdq,
    running_mock,
    switch_on,
    target_of,
    use_fake_bdq,
)
from s3_mock_store import MockStore

from capa_simulation.audit import events
from capa_simulation.io import bdq_login, bdq_login_child
from capa_simulation.io import bdq_login_store as store
from capa_simulation.io import container_start_report as report_contract
from capa_simulation.io.s3_small import S3Target

POSIX_ONLY = pytest.mark.skipif(os.name != "posix", reason="시그널 죽음은 POSIX 의 것")
# 끄개 — 문서에 적힌 이름 그대로.
SWITCH = "CAPA_BDQ_LOGIN_LIGHT"
# 가벼운 길이 판 하위 꾸러미 `__init__` 을 거치지 않고 `server_auth` 를 불러온 흔적.
LIGHT_LOADED = "server_auth ready=0 pyarrow=blocked"
# 전체 길(판 하위 꾸러미 `__init__` 다음)에서 `pyarrow` 막음 없이 불러온 흔적.
FULL_LOADED = "server_auth ready=1 pyarrow=open"


@pytest.fixture(autouse=True)
def _fresh_state() -> Iterator[None]:
    bdq_login.forget_state()
    yield
    bdq_login.forget_state()


@pytest.fixture()
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeBdq:
    found = use_fake_bdq(monkeypatch, tmp_path)
    monkeypatch.delenv(SWITCH, raising=False)
    return found


@pytest.fixture()
def mock_s3() -> Iterator[tuple[MockStore, S3Target]]:
    with running_mock() as (mock, endpoint):
        yield mock, target_of(mock, endpoint)


def light_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    version: str | None = None,
    folder: bool = True,
    nest: bool = True,
) -> Path:
    """가짜 패키지를 짓고 하위 프로세스가 그 자리만 찾게 한다."""
    root = tmp_path / "light-site"
    if version is None:
        build_light_package(root, folder=folder, nest=nest)
    else:
        build_light_package(root, version=version, folder=folder, nest=nest)
    monkeypatch.setenv("PYTHONPATH", str(root))
    return root


def scene(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    monkeypatch.setenv("FAKE_BDQ_SCENE", ",".join(names))


def traces(fake: FakeBdq) -> list[str]:
    if not fake.log.is_file():
        return []
    return fake.log.read_text(encoding="utf-8").splitlines()


# --- 가벼운 길 -----------------------------------------------------------------------------


def test_the_pinned_version_logs_in_on_the_light_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake: FakeBdq
) -> None:
    """판이 맞고 판 폴더가 있으면 꾸러미 `__init__` 둘을 돌리지 않고 `server_auth` 만 불러와
    로그인한다 — `nest_asyncio.apply()` 는 부르고 `pyarrow` 는 막는다. 진단에 길이 실린다."""
    light_package(monkeypatch, tmp_path)
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD)
    assert result.outcome == bdq_login.OUTCOME_OK
    seen = traces(fake)
    assert "package_init" not in seen and "version_init" not in seen
    assert seen.count("nest_apply") == 1 and LIGHT_LOADED in seen
    assert {"sibling config", "sibling meta", "sibling util", "sibling exceptions"} <= set(seen)
    assert fake.logins() == 1
    assert result.diag is not None
    assert (result.diag.stage, result.diag.load) == ("time", bdq_login_child.LOAD_LIGHT)
    assert result.diag.bigdataquery == bdq_login_child.LIGHT_VERSION


@pytest.mark.parametrize(
    ("version", "folder", "nest", "names", "switch", "tried"),
    [
        pytest.param(OTHER_VERSION, True, True, (), "", False, id="other_version"),
        pytest.param(None, False, True, (), "", False, id="no_version_folder"),
        pytest.param(None, True, True, (), " OFF ", False, id="switch_off"),
        pytest.param(None, True, True, ("light_no_login",), "", True, id="no_login"),
        pytest.param(
            None, True, True, ("light_login_not_callable",), "", True, id="login_not_callable"
        ),
        pytest.param(None, True, True, ("light_no_token_time",), "", True, id="no_token_time"),
        pytest.param(None, True, False, (), "", False, id="no_nest_asyncio"),
    ],
)
def test_without_every_light_condition_the_child_takes_the_full_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake: FakeBdq,
    version: str | None,
    folder: bool,
    nest: bool,
    names: tuple[str, ...],
    switch: str,
    tried: bool,
) -> None:
    """판 · 판 폴더 · 끄개 · `login`/`getTokenTime` · `nest_asyncio` 가운데 하나라도 어긋나면 같은
    프로세스에서 지금처럼 전체 import 로 로그인한다. `tried` 는 가벼운 길이 `server_auth` 까지
    불러 보았는지다."""
    light_package(monkeypatch, tmp_path, version=version, folder=folder, nest=nest)
    scene(monkeypatch, *names)
    if switch:
        monkeypatch.setenv(SWITCH, switch)
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD)
    assert result.outcome == bdq_login.OUTCOME_OK
    seen = traces(fake)
    assert "package_init" in seen and "version_init" in seen and FULL_LOADED in seen
    assert (LIGHT_LOADED in seen) is tried
    assert fake.logins() == 1
    assert result.diag is not None and result.diag.load == bdq_login_child.LOAD_FULL


def test_a_server_auth_import_failure_clears_the_shells_and_loads_the_real_package(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake: FakeBdq
) -> None:
    """가벼운 길의 `server_auth` import 가 예외면 심은 빈 꾸러미와 `pyarrow` 막음을 걷고 전체 길로
    간다 — 빈 꾸러미가 남았으면 `login` 이 없어 `login()` 의 try 안에서 터져 거절이 된다."""
    light_package(monkeypatch, tmp_path)
    scene(monkeypatch, "light_import_raises")
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD)
    assert result.outcome == bdq_login.OUTCOME_OK
    seen = traces(fake)
    assert seen.index(LIGHT_LOADED) < seen.index("package_init") < seen.index(FULL_LOADED)
    assert fake.logins() == 1
    assert result.diag is not None and result.diag.load == bdq_login_child.LOAD_FULL


@POSIX_ONLY
def test_a_kill_while_loading_on_the_light_path_is_still_cut_before_sending(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake: FakeBdq
) -> None:
    """가벼운 길의 불러오기 중 바깥 SIGKILL 도 마지막 단계 줄이 `import` 라 「불러오는 중 끊김」
    이다 — 비밀번호를 보내기 전이다."""
    light_package(monkeypatch, tmp_path)
    scene(monkeypatch, "light_import_kill")
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD)
    assert (result.outcome, result.reason) == (
        bdq_login.OUTCOME_UNAVAILABLE,
        bdq_login.REASON_IMPORT_KILLED,
    )
    assert fake.logins() == 0
    assert result.diag is not None
    assert (result.diag.exit_code, result.diag.stage, result.diag.load) == (
        -9,
        "import",
        bdq_login_child.LOAD_LIGHT,
    )


def test_a_name_error_inside_a_light_login_is_rejected_and_the_next_entry_goes_light_again(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake: FakeBdq,
    mock_s3: tuple[MockStore, S3Target],
) -> None:
    """가벼운 길의 `login()` 안 구조 오류(꾸러미 전역을 기대한 `NameError`)도 지금 규칙대로
    거절이다 — 비밀번호가 이미 갔을 수 있다. Admin 에서 다시 넣으면 다음 하위도 가벼운 길로 간다
    (하위는 지난 시도를 모른다). 끄개를 넣으면 전체 길로 성공해 저장된다."""
    _, target = mock_s3
    switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    light_package(monkeypatch, tmp_path)
    scene(monkeypatch, "light_login_name_error")
    for turn in (1, 2):
        outcome = bdq_login.login_from_form(ACCOUNT, PASSWORD, ADMIN_ID)
        assert not outcome.saved
        result = outcome.result
        assert (result.outcome, result.reason, result.error_kind) == (
            bdq_login.OUTCOME_REJECTED,
            bdq_login.REASON_LOGIN_RAISED,
            "builtins.NameError",
        )
        assert result.diag is not None
        assert (result.diag.stage, result.diag.load) == ("login", bdq_login_child.LOAD_LIGHT)
        assert fake.logins() == turn
    monkeypatch.setenv(SWITCH, "off")
    outcome = bdq_login.login_from_form(ACCOUNT, PASSWORD, ADMIN_ID)
    assert outcome.saved and outcome.result.outcome == bdq_login.OUTCOME_OK
    assert outcome.result.diag is not None
    assert outcome.result.diag.load == bdq_login_child.LOAD_FULL


# --- 하위 본문(프로세스 안 — 패키지를 심지 않는다) ----------------------------------------------


def _token_time(_account: str) -> dict[str, int]:
    return {"remaining_hours": 8, "remaining_minutes": 0}


def _emitted(lines: list[str]) -> list[tuple[str, str]]:
    found = [bdq_login.parse_step(line.encode()) for line in lines]
    return [(step.stage, step.load) for step in found]


def test_a_light_miss_emits_the_import_step_again_on_the_full_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """가벼운 길이 실패해 전체로 돌아가면 `import` 단계 줄을 한 번 더(길 = 전체) 낸다 — 부르는
    쪽은 마지막 단계 줄을 읽는다."""
    module = types.ModuleType("bigdataquery")
    module.__dict__.update(login=lambda: None, getTokenTime=_token_time)
    monkeypatch.setitem(sys.modules, "bigdataquery", module)
    monkeypatch.setattr(bdq_login_child, "light_folder", lambda _found, _environ: (["d"], "d/p"))
    monkeypatch.setattr(bdq_login_child, "load_light", lambda _places, _folder: None)
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{ACCOUNT}\n"))
    lines: list[str] = []
    marker = bdq_login_child.run(lines.append)
    assert marker == bdq_login_child.marker_line("done", minutes=480)
    light, full = bdq_login_child.LOAD_LIGHT, bdq_login_child.LOAD_FULL
    assert _emitted(lines) == [("import", light), ("import", full), ("login", full), ("time", full)]
    assert bdq_login.parse_step("\n".join(lines).encode()).load == full


def test_a_light_hit_carries_the_light_load_on_every_step_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    bound = types.SimpleNamespace(login=lambda: calls.append("login"), getTokenTime=_token_time)
    monkeypatch.setattr(bdq_login_child, "light_folder", lambda _found, _environ: (["d"], "d/p"))
    monkeypatch.setattr(bdq_login_child, "load_light", lambda _places, _folder: bound)
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{ACCOUNT}\n"))
    lines: list[str] = []
    assert bdq_login_child.run(lines.append) == bdq_login_child.marker_line("done", minutes=480)
    light = bdq_login_child.LOAD_LIGHT
    assert _emitted(lines) == [("import", light), ("login", light), ("time", light)]
    assert calls == ["login"]


def test_the_light_gate_reads_the_switch_version_and_folder_without_loading(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """가벼운 길 문은 끄개 · 설치 판 · 이미 불러옴 · 꾸러미 자리 · 판 폴더만 본다 — 맨 위 이름의
    자리 찾기는 꾸러미 코드를 돌리지 않는다."""
    root = build_light_package(tmp_path / "site")
    other = build_light_package(tmp_path / "other", folder=False)
    pinned = bdq_login_child.LIGHT_VERSION
    monkeypatch.delitem(sys.modules, "bigdataquery", raising=False)
    monkeypatch.syspath_prepend(str(root))
    found = bdq_login_child.light_folder(pinned, {})
    assert found is not None
    places, folder = found
    assert Path(folder) == root / "bigdataquery" / bdq_login_child.version_package()
    assert [Path(place) for place in places] == [root / "bigdataquery"]
    assert "bigdataquery" not in sys.modules
    assert bdq_login_child.light_folder(OTHER_VERSION, {}) is None
    assert bdq_login_child.light_folder(pinned, {SWITCH: "Off"}) is None
    monkeypatch.setitem(sys.modules, "bigdataquery", types.ModuleType("bigdataquery"))
    assert bdq_login_child.light_folder(pinned, {}) is None
    monkeypatch.delitem(sys.modules, "bigdataquery")
    monkeypatch.syspath_prepend(str(other))
    assert bdq_login_child.light_folder(pinned, {}) is None


def test_the_switch_reads_off_like_the_other_switches_and_reaches_the_child() -> None:
    assert bdq_login_child.LIGHT_SWITCH_ENV == SWITCH
    assert bdq_login_child.light_switch_on({})
    assert bdq_login_child.light_switch_on({SWITCH: "no"})
    assert not bdq_login_child.light_switch_on({SWITCH: " OFF "})
    assert bdq_login.child_environment({SWITCH: "off"})[SWITCH] == "off"


# --- 단계 줄 · 진단의 길 칸 --------------------------------------------------------------------


def test_every_step_line_parses_with_its_load() -> None:
    """단계 줄의 길 칸과 부르는 쪽 정규식이 맞물린다 — 모르는 칸이면 단계가 빈 글이 되어 import
    단계 끊김이 「불러오는 중 끊김」 으로 읽히지 않는다."""
    versions = {"bigdataquery": "2.5.0", "getpass_asterisk": "-"}
    for stage in bdq_login_child.STEP_STAGES:
        for load in bdq_login_child.STEP_LOADS:
            line = bdq_login_child.step_line(stage, versions, load)
            assert bdq_login.parse_step(line.encode()) == bdq_login.StepLine(stage, load, versions)
            assert bdq_login.parse_steps(line.encode()) == (stage, versions)
    light_import = bdq_login_child.step_line("import", versions, bdq_login_child.LOAD_LIGHT)
    assert bdq_login.killed_before_send(-9, bdq_login.parse_steps(light_import.encode())[0])
    assert bdq_login_child.step_line("login", versions).endswith(
        f" load={bdq_login_child.LOAD_FULL}"
    )
    odd = light_import.replace(" load=light", " load=half")
    assert bdq_login.parse_step(odd.encode()) == bdq_login.StepLine()
    assert bdq_login.parse_steps(odd.encode()) == ("", {})
    assert tuple(bdq_login_child.STEP_LOADS) == report_contract.CHILD_LOADS


def test_the_diag_carries_the_load_only_when_known() -> None:
    spec = next(item for item in events.SPECS if item.name == "admin_bdq_login_set")
    diag = report_contract.ChildDiag(-9, "SIGKILL", 2.9, "import", "", "2.5.0", "-", load="light")
    fields = diag.fields()
    assert fields["load"] == "light" and set(fields) <= spec.det_keys
    assert "load" in events.DET_LABELS
    assert diag.text == (
        "종료 -9(SIGKILL) · 2.9초 · 단계 import · stderr - · bigdataquery 2.5.0 · "
        "getpass_asterisk - · 불러오기 light"
    )
    assert diag.code.endswith(" getpass_asterisk=- load=light")
    assert report_contract.parse_child(fields) == diag
    unknown = report_contract.ChildDiag(-9, "SIGKILL", 2.9, "import", "", "2.5.0", "-")
    assert "load" not in unknown.fields() and "불러오기" not in unknown.text
    odd = report_contract.parse_child({**fields, "load": "half"})
    assert odd is not None and odd.load == ""
