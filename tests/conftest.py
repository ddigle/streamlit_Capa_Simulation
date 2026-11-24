# Purpose: 시험 공용 자동 복원·권한 비트·명령줄·붙잡기 보호·운영 DB 문지기·등급 판정기·화면 대역.

"""AppTest 스크립트가 갈아끼운 모듈 속성을 테스트마다 되돌린다.

AppTest 는 같은 프로세스에서 스크립트를 실행하므로 스크립트 안의
`settings.DUCKDB_PATH = ...` 가 그대로 남는다. 되돌리지 않으면 뒤에 도는 테스트가 앞
테스트의 tmp_path DB 를 조용히 보게 된다 — 실제로 네 파일이 그 상태였다. 스크립트마다
`try/finally` 를 넣는 대신 여기서 한 번 복원한다. 스크립트가 도중에 예외로 멈춰도 복원된다.
"""

import os
import stat
import subprocess
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
import grade_support
import pytest
from capture_guard import keep_capture_tolerant
from js_runner import refuse_overlong_command_line
from streamlit.runtime.scriptrunner import ScriptRunnerEvent
from streamlit.testing.v1.local_script_runner import LocalScriptRunner

import capa_simulation.settings as settings
from capa_simulation import (
    load_metrics,
    module_failures,
    module_registry,
    notice_board,
    page_failures,
)
from capa_simulation.audit import recorder as audit_recorder
from capa_simulation.audit import shipper as audit_shipper
from capa_simulation.audit import spool as audit_spool
from capa_simulation.auth import grades as access_grades
from capa_simulation.auth import names as sso_names
from capa_simulation.auth import runtime as sso_runtime
from capa_simulation.components import (
    alert_center,
    date_panel,
    diagnostic_copy,
    edit_grid,
    equipment_master_grid,
    page_failure_card,
    page_tabs,
    paste_form,
    process_field,
    scenario_list_grid,
    side_panel,
    space_layout_editor,
    voc_draft_keeper,
)
from capa_simulation.io import bdq_login, bdq_token, company_bigdataquery_adapter, object_storage
from capa_simulation.io.container_start_report import BDQ_SECRET_KEY_ENV, CD_ONLY_ENVIRONMENT
from capa_simulation.persistence import _sql_helpers as sql_helpers
from capa_simulation.persistence.duckdb_memory import MemoryLimitSetting


def script_stopped_with_its_data(self: LocalScriptRunner) -> bool:
    """SHUTDOWN 이 목록에 들어오고 **그 이벤트의 데이터까지** 들어온 뒤에만 끝났다고 본다.

    Streamlit 1.63 AppTest 의 경쟁 상태를 막는다. 스크립트 스레드의 기록기는 `events` 에 먼저 넣고
    `event_data` 에 나중에 넣는데, 기다리는 쪽(`require_widgets_deltas`)은 `events` 에 SHUTDOWN 이
    보이는 순간 돌아가 `event_data[-1]["client_state"]` 를 읽는다. 그 사이에 데이터가 아직 안
    들어왔으면 직전 이벤트의 데이터를 읽어 `KeyError: 'client_state'` 로 죽는다 — 바쁜 PC 에서만
    드물게 난다(사내 202610061748 리뷰, `test_scenario_shift_ui`). 두 목록 길이가 같아질 때까지
    기다리게 바꾼다. Streamlit 을 올리면 이 대역이 아직 필요한지 다시 본다.
    """
    events = list(self.events)
    return ScriptRunnerEvent.SHUTDOWN in events and len(self.event_data) >= len(events)


# AppTest 가 쓰는 확인 함수를 위 판정으로 바꿔 끼운다. 모든 AppTest 가 같은 클래스를 쓰므로
# 한 번이면 된다.
LocalScriptRunner.script_stopped = script_stopped_with_its_data  # type: ignore[method-assign]


_popen_init = subprocess.Popen.__init__


def _popen_within_the_windows_limit(
    self: subprocess.Popen[Any], args: Any, *rest: Any, **kwargs: Any
) -> None:
    """자식 프로세스 명령줄을 사내 Windows 상한으로 잰다 — Linux 는 넘겨도 떠 사내에서야 깨진다."""
    refuse_overlong_command_line(args)
    _popen_init(self, args, *rest, **kwargs)


subprocess.Popen.__init__ = _popen_within_the_windows_limit  # type: ignore[method-assign]

keep_capture_tolerant()


# 공식버전 자동 갱신 예약의 실행 줄 허락(`auto_update_scheduler.ENV_VAR`). 그 모듈을 여기서 읽으면
# 모든 시험이 수집 단계에서 러너·저장소까지 불러오므로 이름만 적는다 —
# `tests/test_auto_update_scheduler.py` 가 같은 이름인지 본다.
AUTO_UPDATE_ENV_VAR = "CAPA_AUTO_OFFICIAL_UPDATE"

# 저장소의 실제 DB 자리. 테스트가 경로를 갈아끼우기 **전** 값을 잡아 둔다.
_REPOSITORY_DATABASES = (settings.DUCKDB_PATH, settings.EQUIPMENT_DUCKDB_PATH)
_REPOSITORY_DATA_DIR = settings.DATA_DIR
_REPOSITORY_AUDIT_SPOOL = settings.DATA_DIR / "temp" / "audit"
_EXISTED_AT_START: dict[str, bool] = {}

# 시험이 운영 DB 자리를 연 기록 — 연 시험의 끝(`_no_operational_database_opened`)과 세션 끝에서
# 실패로 바꾼다. 여는 쪽 코드가 `duckdb.Error` · 화면 예외 튜플로 거절을 삼켜도 실패가 남게 한다.
_OPERATIONAL_OPENS: list[str] = []
_duckdb_connect = duckdb.connect


def _operational_place(database: object) -> bool:
    """`duckdb.connect` 에 온 자리가 이 저장소의 운영 DB 자리인가 — 판정은 앱 · 점검 스크립트와 같은
    `settings.is_operational_database_place` 이고, 시험이 갈아끼우기 전 저장소 경로로 본다(시험이
    `settings.DATA_DIR` 을 tmp 로 바꿔도 그 tmp 는 운영 자리가 아니다). 메모리 DB 는 아니다."""
    if not isinstance(database, (str, os.PathLike)):
        return False
    text = os.fspath(database)
    if not isinstance(text, str) or not text or text.startswith((":memory:", "md:", "motherduck:")):
        return False
    return settings.is_operational_database_place(
        Path(text), _REPOSITORY_DATABASES, data_dir=_REPOSITORY_DATA_DIR
    )


def _refuse_operational_database(*args: Any, **kwargs: Any) -> duckdb.DuckDBPyConnection:
    """시험은 운영 DB 자리(저장소 `data/` · 저장소 DB 와 같은 파일 · git 작업 트리 안)를 열지
    않는다 — 있는 운영 DB 를 여는 것도, 없는 자리에 새로 만드는 것도. 사내 관문(런북 4-3)이 운영
    저장소에서 돌아 열면 사내 DB 를 읽고 마이그레이션을 건다(2026-11-12 사용자 답 ⑤-6 (가) — 사내 DB
    를 Claude 가 읽지 않는다는 11-11 결정을 시험에서도). 연 자리는 적고 열지 않은 채 멈춘다."""
    database = args[0] if args else kwargs.get("database", ":memory:")
    if _operational_place(database):
        _OPERATIONAL_OPENS.append(os.fspath(database))
        raise PermissionError("시험이 운영 DB 자리를 열려 했습니다 — tmp_path 의 DB 로 바꿉니다")
    return _duckdb_connect(*args, **kwargs)


# 같은 프로세스의 모든 `duckdb.connect`(AppTest 스크립트 스레드 포함)가 이 문지기를 지난다. 시험이
# 띄운 하위 프로세스(스크립트 실행)는 지나지 않는다 — 그 길은 세션 끝의 「새로 만들었으면 실패」 가
# 받친다.
duckdb.connect = _refuse_operational_database


@pytest.fixture(autouse=True)
def _no_operational_database_opened() -> Iterator[None]:
    """이 시험(또는 앞선 모듈 · 세션 준비)이 운영 DB 자리를 열려 했으면 실패로 끝낸다."""
    yield
    if _OPERATIONAL_OPENS:
        places = ", ".join(sorted(set(_OPERATIONAL_OPENS)))
        _OPERATIONAL_OPENS.clear()
        pytest.fail(f"시험이 운영 DB 자리를 열려 했습니다(열지 않음): {places}", pytrace=False)


@pytest.fixture(scope="session")
def keeps_permission_bits(tmp_path_factory: pytest.TempPathFactory) -> bool:
    """이 파일 체계가 0600·0700 을 담는지 — 권한 비트를 단언하는 시험이 함께 쓴다.

    Windows 의 chmod 는 읽기 전용 표시 하나만 바꿔 이 비트를 담지 못한다(사내 4관문 · CI
    `windows-pytest`) — 거기서는 비트를 보지 않는다. 운영 CD 컨테이너는 Linux 라 비트가 살고, Linux
    CI 에서 담지 못하면 건너뛰지 않고 실패한다.
    """
    folder = tmp_path_factory.mktemp("permission-probe")
    probe = folder / "probe"
    probe.write_bytes(b"")
    probe.chmod(0o600)
    folder.chmod(0o700)
    kept = (
        stat.S_IMODE(probe.stat().st_mode) == 0o600 and stat.S_IMODE(folder.stat().st_mode) == 0o700
    )
    if not kept and os.name != "nt" and os.environ.get("GITHUB_ACTIONS") == "true":
        pytest.fail("CI 러너의 파일 체계가 권한 비트를 담지 못한다 — 권한 시험을 건너뛸 수 없다")
    return kept


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "page_failure_card: 코어 화면 감싸기(`page_failure_card.run_core_page`)를 걷지 않고 "
        "그대로 본다",
    )


def _run_core_page_plainly(run: Any, *, page: str, href: str) -> None:
    """코어 화면 감싸기를 걷은 꼴 — 처리 못 한 오류가 그대로 `app.exception` 에 남는다."""
    run()


@pytest.fixture(autouse=True)
def _core_page_errors_still_raise(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """`app.py` 를 도는 시험이 화면의 처리 못 한 오류를 놓치지 않게 코어 화면 감싸기를 걷는다.

    감싸기는 그 오류를 화면 안 카드로 바꿔 `app.exception` 을 비운다 — 그러면 「예외 없이 그렸다」
    를 보는 시험 수백이 실패를 보지 못한다. 감싸기 자체를 보는 시험은
    `@pytest.mark.page_failure_card` 로 걷지 않는다. 앞 시험의 실패 기록(프로세스 값 — 관리자 알림
    `AD-22`)도 넘기지 않는다.
    """
    page_failures.forget_failures()
    if request.node.get_closest_marker("page_failure_card") is None:
        monkeypatch.setattr(page_failure_card, "run_core_page", _run_core_page_plainly)
    yield
    page_failures.forget_failures()


def pytest_sessionstart(session: pytest.Session) -> None:
    for path in _REPOSITORY_DATABASES:
        _EXISTED_AT_START[str(path)] = path.exists()
    _EXISTED_AT_START[str(_REPOSITORY_AUDIT_SPOOL)] = _REPOSITORY_AUDIT_SPOOL.exists()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """테스트가 운영 DB 자리를 열려 했거나(시험 밖 — 세션 준비 · 정리에서) 저장소의
    `data/*.duckdb` 를 **새로 만들었으면** 실패로 끝낸다. 같은 프로세스의 여는 길은 문지기
    (`_refuse_operational_database`)가 열기 전에 막고, 여기서는 그 기록과 하위 프로세스가 만든
    파일을 본다.

    격리를 빠뜨린 AppTest 스크립트는 오류 없이 저장소 DB 를 열고 마이그레이션까지 건다. 앱이 떠
    있는 main 에서는 잠금 오류로, 꺼진 main 에서는 실제 DB 변경으로 나타나 어느 쪽도 원인을
    가리키지 않는다. 처음에 없던 파일이 생겼을 때만 잡을 수 있으므로 DB 가 없는 작업 폴더·CI
    에서 걸린다. 만든 파일은 지워 다음 실행도 같은 조건에서 보게 한다.

    누가 만들었는지는 가리지 못한다 — 세션 중에 같은 트리에 뜬 앱이 만든 DB 도 지우고 실패로 끝난다.
    그 앱은 재시작 전까지 빈 DB 를 본다. 앱을 띄우는 확인은 `git archive` 사본(자기 `data/`)에서
    돌린다.
    """
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if _OPERATIONAL_OPENS:
        places = ", ".join(sorted(set(_OPERATIONAL_OPENS)))
        if reporter is not None:
            reporter.write_line(
                f"시험이 운영 DB 자리를 열려 했습니다(열지 않음): {places}", red=True
            )
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
    if not _EXISTED_AT_START.get(str(_REPOSITORY_AUDIT_SPOOL), True) and (
        _REPOSITORY_AUDIT_SPOOL.exists()
    ):
        if reporter is not None:
            reporter.write_line(
                f"시험이 저장소에 감사 스풀을 만들었습니다: {_REPOSITORY_AUDIT_SPOOL}", red=True
            )
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
    created = [
        path
        for path in _REPOSITORY_DATABASES
        if not _EXISTED_AT_START.get(str(path), True) and path.exists()
    ]
    if not created:
        return
    for path in created:
        for leftover in (path, path.with_name(path.name + ".wal")):
            leftover.unlink(missing_ok=True)
    if reporter is not None:
        names = ", ".join(str(path) for path in created)
        reporter.write_line(f"테스트가 저장소 DB 를 만들었습니다(지웠음): {names}", red=True)
    session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_fixture_post_finalizer(
    fixturedef: pytest.FixtureDef[Any], request: pytest.FixtureRequest
) -> None:
    """정리 뒤 사라진 시험 `tmp_path` 자리에 빈 폴더를 다시 둔다 — 그 이름을 세션 안에서 다시
    내주지 않게 하는 자동 복원이다.

    보존 정책 `failed`(`tmp_path_retention_policy` — 조각 실행기가 쓴다)는 call 이 통과한 시험과
    call 까지 가지 못한 시험의 `tmp_path` 를 정리 단계에서 지운다. 지운 채 두면 pytest 가 같은
    이름(시험 이름 앞 30자 + 번호)을 다음 시험에 다시 내준다. 경로를 키로 쓰는 프로세스 캐시
    (`get_scenario_repository` · `get_equipment_repository` 와 경로 · 쓰기 세대만 키인
    `st.cache_data`)가 그 경로에 앞 시험의 저장소 · 값을 돌려줘, 새 빈 DB 를 연 시험이 데이터
    오류로 멈추거나 앞 시험 값을 조용히 본다. 빈 폴더는 번호만 붙잡고 파일은 지워진 채다.

    pytest 는 준비 하나의 정리(보존 정책의 지우기 포함)를 다 돌린 뒤, 값을 비우기 전에 이 훅을
    부른다. 그래서 같은 시험의 다른 준비가 정리에서 오류를 내도, `tmp_path` 를
    `request.getfixturevalue` 로 늦게 받았어도, 준비 오류로 본문까지 못 갔어도 본다. 시험 정리 훅
    (`pytest_runtest_teardown`)은 앞의 오류에 막히고 `item.funcargs` 에 든 것만 봐 셋을 놓친다.
    기본 보존에서는 할 일이 없다. 다시 불려 값이 이미 비었거나 준비가 실패해 값이 없으면 넘긴다.

    빈 폴더를 둘 수 없으면(지우다 만 자리 · 권한) 조용히 넘긴다 — 여기서 예외가 나면 pytest 가 준비
    값을 비우지 못해 뒤 시험이 모두 같은 `tmp_path` 를 받고, 같은 정리의 다른 오류도 묻힌다.
    """
    if fixturedef.argname != "tmp_path" or fixturedef.cached_result is None:
        return
    path = fixturedef.cached_result[0]
    if not isinstance(path, Path):
        return
    try:
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return


@pytest.fixture(autouse=True)
def _without_auto_update_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """공식버전 자동 갱신 예약의 실행 줄 허락(`CAPA_AUTO_OFFICIAL_UPDATE`)을 뺀다.

    사내 런북은 앱을 띄운 창에 이 환경변수를 넣는다. 같은 창에서 pytest 를 돌리면 `app.py` 를 도는
    AppTest 가 tmp DB 로 예약 스레드를 세우고(시험이 끝나도 남는다), 「꺼짐」 안내를 보는 시험이
    실패한다. 허락이 필요한 시험은 `environ=` 를 따로 넘긴다.
    """
    monkeypatch.delenv(AUTO_UPDATE_ENV_VAR, raising=False)


@pytest.fixture(autouse=True)
def _without_container_start_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """CD 컨테이너 시작 점검 결과(`settings.CONTAINER_START_REPORT_PATH`)를 없는 자리로 돌린다.

    그 파일이 있으면 BigDataQuery 안내에 한 단락이 붙고 Admin Area 에 펼침이 선다. 작업 트리에서
    `scripts/container_start.py` 를 한 번 돌려 `data/temp/` 에 남으면 「지금 문구 그대로」를 보는
    시험이 그 트리에서만 깨진다. 결과 파일이 필요한 시험은 자리를 따로 옮긴다. CD 전용 환경변수도
    지운다 — 결과 파일이 없을 때 그 key 가 있으면 「결과 없음」 안내가 붙는다.
    """
    absent = tmp_path_factory.getbasetemp() / "absent-container-start.json"
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", absent)
    for name in CD_ONLY_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    # 자동 로그인 키도 — 있으면 `managed` 시험에서 그 기능이 저절로 선다.
    monkeypatch.delenv(BDQ_SECRET_KEY_ENV, raising=False)
    # 토큰 파일 자리도 없는 곳으로 — 시험이 이 PC 의 진짜 토큰(WebIDE `/config/.credential`)을 읽지
    # 않게 한다. 패키지가 파일보다 먼저 읽는 환경변수도 지운다.
    monkeypatch.setattr(
        bdq_token, "CREDENTIAL_DIR", tmp_path_factory.getbasetemp() / "absent-credential"
    )
    monkeypatch.delenv(bdq_token.LOGIN_TOKEN_ENV, raising=False)
    bdq_token.forget_expiry_memo()


@pytest.fixture(autouse=True)
def _without_bdq_login_state() -> Iterator[None]:
    """BigDataQuery 자동 로그인의 프로세스 상태(연속 시도 · 쉬는 시간 · 프로세스 안 멈춤 · 마지막
    시도)와 저장 객체 기억 · 기동 때 쥔 키를 다음 시험에 넘기지 않는다 — 계정 원천(`bdq_token`
    파일 이름)과 알림(`AD-23` · `AD-11`)이 그 기억을 읽는다."""
    bdq_login.forget_state()
    yield
    bdq_login.forget_state()


@pytest.fixture(autouse=True)
def _without_notice() -> Iterator[None]:
    """앞 시험이 보낸 공지(프로세스 메모리 — 알림 칸 data 의 공지 칸 · 머리 칩)를 다음 시험에 넘기지
    않는다."""
    notice_board.reset()
    yield
    notice_board.reset()


@pytest.fixture(autouse=True)
def _fresh_load_metrics() -> Iterator[None]:
    """앞 시험의 회차 시간 · CPU 표본 · 세션 최고(프로세스 메모리 — 「서버 시작 점검」 부하 값 줄 ·
    개발자 알림 `AD-26`)를 다음 시험에 넘기지 않는다. `app.py` 를 도는 AppTest 마다 회차가 쌓이고
    pytest 프로세스는 바빠 CPU 5분 평균이 문턱을 넘을 수 있어, 시험마다 CPU 첫 표본을 지금으로 다시
    둔다(5분을 덮기 전이라 「모름」)."""
    load_metrics.reset()
    yield
    load_metrics.reset()


@pytest.fixture(autouse=True)
def _without_token_failure_mark() -> Iterator[None]:
    """앞 시험의 조회 토큰 실패 표지(프로세스 값 — 관리자 알림 `AD-10`)를 다음 시험에 넘기지
    않는다."""
    company_bigdataquery_adapter.forget_token_failure()
    yield
    company_bigdataquery_adapter.forget_token_failure()


@pytest.fixture(autouse=True)
def _without_sso_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """통합인증 환경변수(`auth.names.SSO_ENVIRONMENT`)를 지우고 통합인증 프로세스 상태를 비운다.

    C-DEP 처럼 `ADFS_CLIENT_ID` 가 있는 창에서 pytest 를 돌리면 진짜 `app.py` 를 도는 AppTest 가
    「문지기 없이 시작됨」 으로 멈추고, 앞 시험이 읽어 둔 설정 · 로그아웃 폐기 목록이 뒤 시험에
    남는다. 통합인증이 필요한 시험은 `tests/sso_support.py` 의 `use_config` 로 따로 세운다.
    """
    for name in sso_names.SSO_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    sso_runtime.reset()
    yield
    sso_runtime.reset()


# 시험이 늘 쓰는 CUSTOM 원천 표 이름 — 합성 값이다(실제 표 이름은 환경변수로만 받는다). 두 조회
# 가짜(어댑터 · DB 등록 · 자동 갱신 시험)도 이 상수를 읽어 둘째 조회를 가른다.
DEMO_CUSTOM_TABLE = "demo_schema.demo_custom"


@pytest.fixture(autouse=True)
def _with_demo_custom_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """CUSTOM 원천 표 환경변수(`company_bigdataquery_adapter.BDQ_CUSTOM_TABLE_ENV`)를 합성 값으로
    두고 CUSTOM 원천 끄개(`BDQ_CUSTOM_SOURCE_ENV`)는 지운다.

    사내 pytest 창에 실제 값 · 끄개가 있어도 덮어 결과가 같다. 표 이름을 지우지 않는 까닭 — 없으면
    DB 등록이 「변수 없음」 으로 멈추고 그 판정을 읽는 화면 · 점검 시험이 뜻 없이 바뀐다. 「없음」
    갈래와 끄개를 내린 갈래는 그 시험이 직접 바꾼다(`monkeypatch.delenv` · `setenv`).
    """
    monkeypatch.setenv(company_bigdataquery_adapter.BDQ_CUSTOM_TABLE_ENV, DEMO_CUSTOM_TABLE)
    monkeypatch.delenv(company_bigdataquery_adapter.BDQ_CUSTOM_SOURCE_ENV, raising=False)


@pytest.fixture(autouse=True)
def _without_grade_judge() -> Iterator[None]:
    """접속 등급의 판정기(`grades.install_caller_source` — `app.py` 를 도는 AppTest · 등급 시험이
    꽂는다)와 등급 시험 한 벌(`grade_support`)을 앞뒤로 비운다 — 앞 시험의 판정기가 뒤 시험의 저장소
    쓰기를 가르지 않게(꽂힌 것이 없으면 제한 없음). `grade_support` 는 이 파일 맨 위에서 읽는다 —
    시험마다 걷히기 전의 실제 화면 감싸기(`REAL_RUN_CORE_PAGE`)를 붙잡게."""
    access_grades.install_caller_source(None)
    grade_support.forget_world()
    yield
    access_grades.install_caller_source(None)
    grade_support.forget_world()


@pytest.fixture(autouse=True, scope="session")
def _audit_spool_outside_repository(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    """감사 스풀 뿌리를 세션 임시 폴더로 — 기록기를 켠 시험이 저장소 `data/temp/` 에 쓰지 않는다.

    그물은 둘이다. 여기서 기본 뿌리를 옮기고, 세션 끝(`pytest_sessionfinish`)에 저장소의 기본
    뿌리가 새로 생겼는지 본다.
    """
    audit_spool.configure(tmp_path_factory.mktemp("audit-spool"))
    yield
    audit_spool.configure(None)


@pytest.fixture(autouse=True)
def _audit_recorder_off() -> Iterator[None]:
    """감사 기록기를 끈 채로 시작하고 끝에 비운다 — 켜는 시험은 `start` 를 스스로 부른다.

    앞 시험이 켠 기록기 · 큐 · 해석기 · 사슬 · 스풀 뿌리가 뒤 시험에 남으면 꺼짐 회차의
    「호출 0」 이 깨진다.
    """
    root = audit_spool.configured()
    audit_recorder.reset()
    audit_spool.reset()
    audit_shipper.reset()
    yield
    audit_recorder.reset()
    audit_spool.reset()
    audit_shipper.reset()
    audit_spool.configure(root)


@pytest.fixture(autouse=True)
def _without_object_storage_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """오브젝트 스토리지 설정 환경변수(`object_storage.SETTINGS_ENVIRONMENT`)를 지운다.

    사내 값(주소 · 프로필 이름)은 사내 PC 사용자 환경변수이고, 이관 창에는 모드를 넣는다
    (`docs/objectstore_setup.md` 6장). 같은 창에서 pytest 를 돌리면 「값이 없을 때」 ·
    `local` 기본을 보는 시험이 그 값을 읽어 사내에서만 깨진다. 값이 필요한 시험은
    `monkeypatch.setenv` · `environ=` 로 따로 준다.
    """
    for name in object_storage.SETTINGS_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _without_duckdb_memory_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """화면이 읽는 DuckDB 메모리 한도 칸 판정(`_sql_helpers.DUCKDB_MEMORY_LIMIT`)을 「없음」 으로
    둔다.

    그 판정은 import 때 환경변수 `CAPA_DUCKDB_MEMORY_LIMIT` 를 한 번 읽어 정한다(같은 파일의 연결은
    설정이 같아야 한다). 그 값을 넣은 창에서 pytest 를 돌려도 「서버 시작 점검」 표 · 제목 · `AD-01`
    을 보는 시험이 값이 없을 때를 보게 한다. 값이 필요한 시험은 이 칸을 따로 덮는다.
    """
    monkeypatch.setattr(sql_helpers, "DUCKDB_MEMORY_LIMIT", MemoryLimitSetting(raw=None))


@pytest.fixture(autouse=True)
def _without_handed_over_mark(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[None]:
    """동기화 판정(`sync_boot`)이 넘긴 표지를 읽는 시뮬레이션 DB 자리를 없는 tmp 자리로
    돌리고, 판정 기억을 앞뒤로 비운다.

    판정은 그 DB 옆 세대 사이드카의 넘긴 표지(`handed_over_utc` — 이관 `init` 이 남긴다)를
    읽는다. 표지가 있으면 `local` 이어도 `SY-04` 가 서고 그 회차에는 해소 표지(`SY-01` ·
    `SY-02` · `SY-06` …)도 함께 나간다. 이관을 한 사내 PC 의 작업 트리에서 pytest 를 돌리면
    진짜 표지를 읽어 「평범한 로컬 프로세스에는 동기화 알림이 없다」 를 보는 시험이 그
    PC 에서만 깨진다. `sync_boot` 는 그 자리를 import 때 이름으로 쥐어
    `settings.DUCKDB_PATH` 를 tmp 로 바꾼 시험도 진짜 자리를 읽으므로 그 이름을 돌린다.
    등록 자리(`sync_boot.MANAGED_PATHS`)는 그대로다. 표지가 필요한 시험은
    `monkeypatch.setattr(sync_boot, "DUCKDB_PATH", …)` 로 다시 돌린다. 모듈은 여기서
    읽어 수집 단계에 저장소까지 불러오지 않는다.
    """
    from capa_simulation import sync_boot

    absent = tmp_path_factory.getbasetemp() / "absent-sync-place" / _REPOSITORY_DATABASES[0].name
    monkeypatch.setattr(sync_boot, "DUCKDB_PATH", absent)
    sync_boot.forget_boot_result()
    yield
    sync_boot.forget_boot_result()


@pytest.fixture(autouse=True)
def _without_app_contact_email(monkeypatch: pytest.MonkeyPatch) -> None:
    """앱 정보 카드의 문의처 환경변수(`settings.APP_CONTACT_EMAIL_ENV`)를 지운다.

    사내 PC · C-DEP 는 이 값을 넣어 둔다. 같은 창에서 pytest 를 돌려도 사외와 같은 「문의처 없음」
    을 보게 한다. 문의처가 필요한 시험은 `monkeypatch.setenv` 로 가짜 값(`…@example.invalid`)을
    준다.
    """
    monkeypatch.delenv(settings.APP_CONTACT_EMAIL_ENV, raising=False)


# 시험이 띄우는 가짜 서버(가짜 S3 · 가짜 IdP · 임시 응답 · 앱)에 붙는 루프백 이름.
# urllib 은 IPv6 주소를 괄호 꼴(`[::1]`)로 맞춘다.
LOOPBACK_NO_PROXY = ("127.0.0.1", "[::1]", "localhost")
NO_PROXY_NAMES = ("NO_PROXY", "no_proxy")


def with_loopback_no_proxy(value: str) -> str:
    """`NO_PROXY` 값 뒤에 빠진 루프백 이름을 붙인다.

    `*`(모두 우회)는 그대로 둔다 — urllib 은 값 전체가 `*` 일 때만 그 뜻으로 읽는다.
    """
    if value == "*":
        return value
    present = {part.strip().lower() for part in value.split(",")}
    missing = [name for name in LOOPBACK_NO_PROXY if name not in present]
    return ",".join(part for part in (value.strip().strip(","), *missing) if part)


def _append_loopback_no_proxy(patch: pytest.MonkeyPatch) -> None:
    """`NO_PROXY` · `no_proxy` 에 루프백 셋을 덧붙여 루프백 요청이 창의 프록시를 거치지 않게 한다.

    사내 PC 창에는 `HTTP(S)_PROXY` 가 있고 `NO_PROXY` 에 `127.0.0.1` 이 없을 수 있다. 파이썬의
    우회 판정은 이름을 글자 끝으로만 맞춰 `localhost` 가 `127.0.0.1` 을 덮지 않으므로, 127.0.0.1
    에서 듣는 가짜 서버로 가는 요청이 프록시로 가 403 을 받는다.
    있던 값은 두고 뒤에 붙인다. 두 이름을 다 쓴다 — Linux 의 urllib 는 소문자가 이기고, 한쪽만
    있던 창은 다른 쪽도 그 값에서 시작한다. Windows 는 두 이름이 한 변수다. 환경변수라 시험이
    띄우는 하위 프로세스(aws · 앱)까지 이어진다.
    """
    before = {name: os.environ.get(name, "") for name in NO_PROXY_NAMES}
    fallback = next((value for value in before.values() if value.strip()), "")
    for name, value in before.items():
        patch.setenv(name, with_loopback_no_proxy(value if value.strip() else fallback))


@pytest.fixture(autouse=True, scope="session")
def _loopback_skips_proxy_from_the_start() -> Iterator[None]:
    """세션 처음에 한 번 덧붙인다 — 모듈 · 세션 범위 준비는 함수 범위 준비보다 먼저 서므로, 그때
    띄우는 하위 프로세스(가짜 서버 · aws · 앱)도 루프백 셋이 든 환경을 받게 한다."""
    with pytest.MonkeyPatch.context() as patch:
        _append_loopback_no_proxy(patch)
        yield


@pytest.fixture(autouse=True)
def _loopback_skips_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """시험마다 다시 덧붙인다 — 앞 시험이 값을 바꿨어도 루프백 셋에서 시작한다."""
    _append_loopback_no_proxy(monkeypatch)


@pytest.fixture(autouse=True)
def _without_internal_modules(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[None]:
    """모듈 뿌리(`CAPA_MODULES_ROOT`)를 없는 자리로, 모듈 데이터 뿌리를 tmp 로 돌린다.

    사내 저장소에는 `modules/` 가 있다. 진짜 `app.py` 를 도는 AppTest 와 시험이 하위 프로세스로
    띄우는 앱(`test_check_deploy_screens` 의 Popen 등)이 그것을 찾으면 사이드바에 「모듈」
    상자가 더 서서 사내에서만 시험이 깨진다. 속성(`settings.MODULES_DIR`)이 아니라 **환경변수**로
    돌린다 — 하위 프로세스까지 이어진다. 끄는 스위치(`CAPA_MODULES_DISABLED`)는 지우고, 찾기
    캐시와 실행 기록은 앞뒤로 비운다. 견본이 필요한 시험은 `monkeypatch.setenv(ROOT_ENV_VAR, …)`
    로 다시 돌린다(캐시 키에 환경변수 값이 들어 있어 따로 비울 필요가 없다).
    """
    base = tmp_path_factory.getbasetemp()
    monkeypatch.setenv(module_registry.ROOT_ENV_VAR, str(base / "absent-modules"))
    monkeypatch.setenv(module_registry.DATA_ROOT_ENV_VAR, str(base / "module-data"))
    monkeypatch.delenv(module_registry.DISABLED_ENV_VAR, raising=False)
    module_registry.clear_discovery_cache()
    module_failures.clear_records()
    yield
    module_registry.clear_discovery_cache()
    module_failures.clear_records()


@pytest.fixture(autouse=True)
def _restore_settings_paths() -> Iterator[None]:
    original = (settings.DUCKDB_PATH, settings.EQUIPMENT_DUCKDB_PATH)
    yield
    settings.DUCKDB_PATH, settings.EQUIPMENT_DUCKDB_PATH = original


@pytest.fixture(autouse=True)
def _fresh_standard_target_availability() -> None:
    """주차별 가용대수 읽기 캐시(`equipment_cache.load_standard_target_availability`)를 테스트마다
    비운다.

    표준 목표·재공 현황 화면 대본 여럿이 설비 저장소를 가짜로 갈아끼우되 DB 경로는 저장소의 실제
    자리 그대로다. 캐시 키(경로·stat·쓰기 세대)가 테스트 사이에 같아, 비우지 않으면 앞 테스트의 가짜
    가용대수가 뒤 테스트에 적중한다(빈 표 안내를 보는 시험이 채운 표를 받는다). 모듈은 여기서 읽어
    수집 단계에 저장소까지 불러오지 않는다.
    """
    from capa_simulation.persistence import equipment_cache

    equipment_cache.clear_standard_target_availability_cache()


@pytest.fixture(autouse=True)
def _stub_space_layout_editor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Space 편집기 컴포넌트(`_EDITOR`)를 아무것도 보내지 않는 대역으로 바꾼다.

    Space 첫 화면(FAB 전체)부터 이 컴포넌트다. AppTest 는 그 JS 를 못 돌리고, 한 프로세스의 두
    번째 AppTest 에서 진짜 컴포넌트를 부르면 「not registered」로 죽는다 — 페이지를 그리기만 하는
    테스트(전 페이지 렌더·내비게이션)도 그래서 대역이 필요하다. 받은 값을 보는 테스트는 제
    `monkeypatch.setattr` 로 이 위에 다시 덮는다."""

    def _silent(**_: Any) -> SimpleNamespace:
        return SimpleNamespace(apply=None, navigate=None)

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _silent)


@pytest.fixture(autouse=True)
def date_panels(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    """날짜 칸 컴포넌트(`date_panel._DATE_PANEL`)를 아무것도 보내지 않는 대역으로 바꾼다.

    Space 편집기와 같은 까닭이다 — AppTest 는 JS 를 못 돌리고, 한 프로세스의 두 번째 AppTest 에서
    진짜 컴포넌트를 부르면 「not registered」로 죽는다. 값의 정본은 세션 칸이라 시험은 그 칸을 읽고
    쓴다. 돌려주는 사전은 위젯 키(`date_panel.panel_key`)마다 마지막에 보낸 `data` 다 — 칸이
    섰는지 · 잠겼는지 · 지금 값을 본다."""
    sent: dict[str, dict[str, Any]] = {}

    def _silent(*, key: str, data: dict[str, Any], **_: Any) -> SimpleNamespace:
        sent[key] = data
        return SimpleNamespace(apply=None)

    monkeypatch.setattr(date_panel, "_DATE_PANEL", _silent)
    return sent


@pytest.fixture(autouse=True)
def _stub_page_tabs(monkeypatch: pytest.MonkeyPatch) -> None:
    """화면 탭 줄 컴포넌트(`page_tabs._PAGE_TABS`)를 아무것도 보내지 않는 대역으로 바꾼다.

    `app.py` 가 매 회차 그린다. Space 편집기와 같은 까닭이다 — AppTest 는 JS 를 못 돌리고, 한
    프로세스의 두 번째 AppTest 에서 진짜 컴포넌트를 부르면 「not registered」로 죽는다. 받은 값을
    보는 시험(`tests/test_page_tabs.py`)은 제 `monkeypatch.setattr` 로 이 위에 다시 덮는다."""

    def _silent(**_: Any) -> SimpleNamespace:
        return SimpleNamespace(select=None, close=None, pin=None)

    monkeypatch.setattr(page_tabs, "_PAGE_TABS", _silent)


@pytest.fixture(autouse=True)
def _stub_alert_center(monkeypatch: pytest.MonkeyPatch) -> None:
    """알림 칸 컴포넌트(`alert_center._ALERT_CENTER`)를 아무것도 보내지 않는 대역으로 바꾼다.

    `app.py` 가 매 회차 그린다. 탭 줄과 같은 까닭이다 — AppTest 는 JS 를 못 돌리고, 한 프로세스의 두
    번째 AppTest 에서 진짜 컴포넌트를 부르면 「not registered」로 죽는다. 받은 값을 보는
    시험(`tests/test_alert_center.py`)은 제 `monkeypatch.setattr` 로 이 위에 다시 덮는다."""

    def _silent(**_: Any) -> None:
        return None

    monkeypatch.setattr(alert_center, "_ALERT_CENTER", _silent)


@pytest.fixture(autouse=True)
def _stub_equipment_master_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    """설비 마스터 표 컴포넌트(`equipment_master_grid._GRID` · 표 feed `_FEED`)를 아무것도 보내지
    않는 대역으로 바꾼다.

    Space 편집기 대역과 같은 까닭이다 — AppTest 는 그 JS 를 못 돌리고, 한 프로세스의 두 번째 AppTest
    에서 진짜 컴포넌트를 부르면 「not registered」로 죽는다. 받은 값을 보는 시험은 제
    `monkeypatch.setattr` 로 이 위에 다시 덮는다(세션 칸에 넣어 둔 값을 `st.session_state[key]` 에
    적고 받은 `on_<이름>_change` 콜백을 부르는 꼴 — `tests/test_equipment_master_grid.py`)."""

    def _silent(**_: Any) -> SimpleNamespace:
        return SimpleNamespace(
            outbox=None,
            load=None,
            clear=None,
            new=None,
            dialog=None,
            open=None,
            unload=None,
            goto=None,
        )

    def _silent_feed(**_: Any) -> None:
        return None

    monkeypatch.setattr(equipment_master_grid, "_GRID", _silent)
    monkeypatch.setattr(equipment_master_grid, "_FEED", _silent_feed)


@pytest.fixture(autouse=True)
def _stub_edit_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    """범용 편집 그리드의 등록(`edit_grid._GRID` 껍데기 · 줄 규칙 표 껍데기 `_GRID_ROWS` · `_FEED`
    feed)을 아무것도 보내지 않는 대역으로 바꾼다 — 설비 마스터 표 대역과 같은 까닭(AppTest 는 그
    JS 를 못 돌리고, 한 프로세스의 두 번째 AppTest 에서 진짜 컴포넌트를 부르면 「not registered」로
    죽는다). 받은 값을 보는 시험은
    `tests/edit_grid_fake.install_fake_edit_grid` 로 이 위에 다시 덮는다."""

    def _silent_grid(**_: Any) -> SimpleNamespace:
        return SimpleNamespace(outbox=None)

    def _silent_feed(**_: Any) -> None:
        return None

    monkeypatch.setattr(edit_grid, "_GRID", _silent_grid)
    monkeypatch.setattr(edit_grid, "_GRID_ROWS", _silent_grid)
    monkeypatch.setattr(edit_grid, "_FEED", _silent_feed)


@pytest.fixture(autouse=True)
def _stub_scenario_list_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    """시나리오 목록 표(`scenario_list_grid._GRID`)를 아무것도 보내지 않는 대역으로 바꾼다 — 표
    대역과 같은 까닭이다. 받은 data · 출납을 보는 시험은 제 대역을
    쓴다(`tests/scenario_list_fake.py`)."""

    def _silent(**_: Any) -> SimpleNamespace:
        return SimpleNamespace(outbox=None)

    monkeypatch.setattr(scenario_list_grid, "_GRID", _silent)


@pytest.fixture(autouse=True)
def _stub_side_splitter(monkeypatch: pytest.MonkeyPatch) -> None:
    """편집기 오른쪽 칸 칸막이(`side_panel._SPLITTER`)를 아무것도 보내지 않는
    대역으로 바꾼다 — 표 대역과 같은 까닭(AppTest 는 그 JS 를 못 돌리고, 한 프로세스의 두 번째
    AppTest 에서 진짜 컴포넌트를 부르면 「not registered」로 죽는다). 받는 값이 없는 칸이다.
    자리·data 를 보는 시험은 제 `monkeypatch.setattr` 로 이 위에 다시 덮는다
    (`tests/test_equipment_side_panel.py`)."""

    def _silent(**_: Any) -> None:
        return None

    monkeypatch.setattr(side_panel, "_SPLITTER", _silent)


@pytest.fixture(autouse=True)
def _stub_voc_draft_keeper(monkeypatch: pytest.MonkeyPatch) -> None:
    """VOC 새 글 초안 보관 컴포넌트(`voc_draft_keeper._DRAFT_KEEPER`)를 아무것도 보내지 않는
    대역으로 바꾼다 — Space 편집기 대역과 같은 까닭(AppTest 는 그 JS 를 못 돌리고, 한 프로세스의
    두 번째 AppTest 에서 진짜 컴포넌트를 부르면 「not registered」로 죽는다). 받은 값을 보는 시험은
    제 `monkeypatch.setattr` 로 이 위에 다시 덮는다(`tests/test_voc_draft_keeper.py`)."""

    def _silent(**_: Any) -> None:
        return None

    monkeypatch.setattr(voc_draft_keeper, "_DRAFT_KEEPER", _silent)


@pytest.fixture(autouse=True)
def diagnostic_copies(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """진단 글 복사 컴포넌트(`diagnostic_copy._COPY`)를 아무것도 보내지 않는 대역으로 바꾼다 —
    Space 편집기 대역과 같은 까닭(AppTest 는 그 JS 를 못 돌리고, 한 프로세스의 두 번째 AppTest 에서
    진짜 컴포넌트를 부르면 「not registered」로 죽는다). 돌려주는 사전은 위젯 키마다 마지막에 보낸
    복사 글이다."""
    sent: dict[str, str] = {}

    def _silent(*, key: str, data: dict[str, Any], **_: Any) -> None:
        sent[key] = data["text"]

    monkeypatch.setattr(diagnostic_copy, "_COPY", _silent)
    return sent


@pytest.fixture(autouse=True)
def _stub_paste_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """붙여넣기 창 컴포넌트(`paste_form._PASTE_WINDOW`)를 아무것도 보내지 않는 대역으로 바꾼다 —
    Space 편집기 대역과 같은 까닭(AppTest 는 그 JS 를 못 돌리고, 한 프로세스의 두 번째 AppTest 에서
    진짜 컴포넌트를 부르면 「not registered」로 죽는다). 받은 값을 보는 시험은 제
    `monkeypatch.setattr` 로 이 위에 다시 덮는다(`tests/test_paste_form.py`)."""

    def _silent(**_: Any) -> None:
        return None

    monkeypatch.setattr(paste_form, "_PASTE_WINDOW", _silent)


@pytest.fixture(autouse=True)
def _stub_process_board(monkeypatch: pytest.MonkeyPatch) -> None:
    """공정 고르기 판(`process_field._PROCESS_PICKER`)을 아무것도 보내지 않는 대역으로 바꾼다 —
    필요 단축 일정 조건 카드 「공정」 팝오버가 매 회차 그린다. Space 편집기 대역과 같은 까닭(AppTest
    는 그 JS 를 못 돌리고, 한 프로세스의 두 번째 AppTest 에서 진짜 컴포넌트를 부르면 「not
    registered」로 죽는다). 판을 누르는 시험은 `tests/process_board_press.live_board` 로 회차 안에서
    진짜 판을 등록해 이 위에 다시 덮는다."""

    def _silent(**_: Any) -> SimpleNamespace:
        return SimpleNamespace(apply=None)

    monkeypatch.setattr(process_field, "_PROCESS_PICKER", _silent)


@pytest.fixture(autouse=True)
def _editor_scopes_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """편집기 구역 끄개(`settings.EDITOR_SCOPES_ENV`)를 시험 창에서 걷는다 — 사내 창에 끄개가 남아
    있어도 시험은 기본(켬) 꼴로 돈다. 끈 꼴을 보는 시험은 제 `monkeypatch.setenv` 로 이 위에 다시
    넣는다."""
    monkeypatch.delenv(settings.EDITOR_SCOPES_ENV, raising=False)
