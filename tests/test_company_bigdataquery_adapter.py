# Purpose: company bigdataquery adapter 관련 정상·예외·회귀 동작을 검증한다.

from __future__ import annotations

import importlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from capa_simulation.io import company_bigdataquery_adapter as adapter
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "config" / "data_contract.json"


def _module(get_data: object) -> SimpleNamespace:
    return SimpleNamespace(getData=get_data)


def test_the_requester_account_reaches_get_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """환경변수에 계정이 있으면 `user_name` 으로 실려야 한다.

    사내 WebIDE 에서 이 값이 안 실려 조회가 통째로 막혀 있었다 — 로그인도 토큰도 정상인데
    `parameter user_name is necessary.` 만 돌아왔다.
    """
    captured: dict[str, object] = {}
    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, "  AD_ACCOUNT  ")
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _: _module(lambda **kwargs: captured.update(kwargs) or pd.DataFrame({"a": [1]})),
    )

    adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert captured["user_name"] == "AD_ACCOUNT", "앞뒤 공백을 떼고 넘겨야 한다"


def test_no_requester_account_means_no_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    """값이 없으면 **인자를 아예 넘기지 않는다.**

    Windows 에서는 패키지가 로그인 이름으로 요청자를 스스로 식별해 지금도 인자 없이 돈다.
    빈 문자열이나 `None` 을 넣으면 그 경로를 새로 깨는데, 그렇게 넣었을 때 어떻게 되는지는
    아무도 재지 않았다.
    """
    captured: dict[str, object] = {}
    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _: _module(lambda **kwargs: captured.update(kwargs) or pd.DataFrame({"a": [1]})),
    )

    adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert "user_name" not in captured
    assert set(captured) == {"param", "convert_type", "verbose"}


def test_a_rejected_blank_account_names_the_variable_to_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """서버가 빈값을 거부하면 패키지 문구 대신 채울 환경변수를 알려야 한다."""

    def refuse(**_kwargs: object) -> pd.DataFrame:
        raise ValueError("Parameter user_name is necessary.")

    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(refuse))

    with pytest.raises(RuntimeError, match=adapter.BDQ_USER_NAME_ENV):
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")


def test_an_unrelated_failure_is_not_disguised(monkeypatch: pytest.MonkeyPatch) -> None:
    """계정과 상관없는 실패까지 계정 안내로 바꾸면 진짜 원인이 가려진다. 감싸도 원문과 원래 예외는
    남는다."""
    original = ValueError("table not found")

    def refuse(**_kwargs: object) -> pd.DataFrame:
        raise original

    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(refuse))

    with pytest.raises(adapter.BigDataQueryCallError, match="table not found") as raised:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert adapter.BDQ_USER_NAME_ENV not in str(raised.value)
    assert raised.value.__cause__ is original
    assert (raised.value.kind, raised.value.type_names) == (
        adapter.QUERY_FAILURE_SQL,
        ("ValueError",),
    )


class Error(Exception):
    """사내 패키지가 내는 꼴 — 이름이 `Error` 하나뿐이고 화면이 잡는 예외 튜플 밖이다."""


def _chained(outer: BaseException, cause: BaseException) -> BaseException:
    outer.__cause__ = cause
    return outer


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (TimeoutError(), adapter.QUERY_FAILURE_TIMEOUT),
        (ConnectionResetError(), adapter.QUERY_FAILURE_CONNECTION),
        (Error("Read timed out"), adapter.QUERY_FAILURE_TIMEOUT),
        (Error("connect timeout"), adapter.QUERY_FAILURE_TIMEOUT),
        (Error("Connection refused"), adapter.QUERY_FAILURE_CONNECTION),
        (Error("AnalysisException: Could not resolve table reference"), adapter.QUERY_FAILURE_SQL),
        (Error(""), adapter.QUERY_FAILURE_OTHER),
        (_chained(Error(""), TimeoutError()), adapter.QUERY_FAILURE_TIMEOUT),
        (_chained(Error(""), Error("TTransportException")), adapter.QUERY_FAILURE_CONNECTION),
    ],
)
def test_a_failure_is_sorted_by_its_chain_names_and_words(error: BaseException, kind: str) -> None:
    """사내 리뷰 202610200720 — 「조회 실패(Error)」 만으로는 시간 초과인지 가를 수 없었다."""
    assert adapter.classify_query_failure(error) == kind


def test_a_wrapped_failure_keeps_the_chain_names_and_cuts_a_long_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(**_kwargs: object) -> pd.DataFrame:
        raise Error("x" * 1000) from TimeoutError()

    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(refuse))

    with pytest.raises(RuntimeError) as raised:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert isinstance(raised.value, adapter.BigDataQueryCallError)
    assert raised.value.type_names == ("Error", "TimeoutError")
    assert "시간 초과" in str(raised.value) and "다시" in str(raised.value)
    assert len(str(raised.value)) < 500


_PACKAGE_MISSING_TEXT = (
    "현재 환경에 bigdataquery 패키지가 없습니다. "
    "이 패키지는 사내 전용이라 pyproject.toml 의존성에 넣지 않습니다. "
    "사내 환경에서 `uv pip install bigdataquery` 로 따로 설치한 뒤 실행하세요."
)


def _installed_package(monkeypatch: pytest.MonkeyPatch, root: Path, init_body: str) -> None:
    """`root` 에 깔린 가짜 `bigdataquery` — 패키지는 있고 `__init__` 이 `init_body` 를 돈다."""
    package = root / "bigdataquery"
    package.mkdir()
    (package / "__init__.py").write_text(init_body, encoding="utf-8")
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.delitem(sys.modules, "bigdataquery", raising=False)


def test_a_missing_package_keeps_the_install_advice(monkeypatch: pytest.MonkeyPatch) -> None:
    """맨 `uv sync` 가 패키지를 지운 경우다. 점검 스크립트가 이 문구의 「패키지가 없습니다」로
    가른다."""
    monkeypatch.setitem(sys.modules, "bigdataquery", None)

    with pytest.raises(RuntimeError) as raised:
        adapter.load_bigdataquery_module()

    assert str(raised.value) == _PACKAGE_MISSING_TEXT
    assert isinstance(raised.value.__cause__, ModuleNotFoundError)


def test_a_failure_the_screen_catches_still_leaves_one_log_line(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """화면이 잡아 보여 주는 실패도 앱 로그에 한 줄 남는다 — 셸·화면을 볼 수 없는 C-DEP CD 에서는
    로그가 유일한 단서일 수 있다. 원문(계정 이름 등이 든다)은 화면에만 두고 로그에는 갈래·종류만."""
    secret_like = "AD user 'someone' at '/config/.credential/'"

    def refuse(**_kwargs: object) -> pd.DataFrame:
        raise ValueError(f"table not found {secret_like}")

    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(refuse))
    caplog.set_level("WARNING", logger=adapter.__name__)

    with pytest.raises(adapter.BigDataQueryCallError):
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    lines = [record.getMessage() for record in caplog.records]
    assert lines == [
        f"BigDataQuery 실패: 조회 실패 갈래={adapter.QUERY_FAILURE_SQL} 종류=ValueError"
    ]
    assert secret_like not in "\n".join(lines)

    caplog.clear()
    monkeypatch.undo()
    monkeypatch.setitem(sys.modules, "bigdataquery", None)
    with pytest.raises(RuntimeError):
        adapter.load_bigdataquery_module()
    assert [record.getMessage() for record in caplog.records] == [
        "BigDataQuery 실패: 패키지를 불러오지 못함(없는 모듈 bigdataquery)"
    ]


@pytest.mark.parametrize(
    ("init_body", "original"),
    [
        (
            'raise ImportError("DLL load failed while importing _jpype: 모듈이 없습니다.")\n',
            "DLL load failed while importing _jpype",
        ),
        ("from importlib import capa_bdq_no_such_name\n", "cannot import name"),
        (
            "raise AttributeError(\"module 'numpy' has no attribute 'float'\")\n",
            "has no attribute 'float'",
        ),
    ],
    ids=["dll-load", "cannot-import-name", "numpy-attribute"],
)
def test_a_package_that_fails_to_import_is_reported_where_the_screens_catch_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, init_body: str, original: str
) -> None:
    """패키지는 깔렸는데 불러오다 깨지면(DLL·numpy 판·이름 없음) 화면이 잡는 `RuntimeError` 로 온다.
    `ImportError`·`AttributeError` 는 `BOOTSTRAP_ERRORS` 밖이라 그대로 두면 목록 조회·저장이
    traceback 으로 멈춘다. 「패키지가 없습니다」라고 하면 틀린 조치다."""
    _installed_package(monkeypatch, tmp_path, init_body)

    with pytest.raises(RuntimeError) as raised:
        adapter.load_bigdataquery_module()

    text = str(raised.value)
    assert isinstance(raised.value, BOOTSTRAP_ERRORS)
    assert "불러오지 못했습니다" in text and original in text
    assert "패키지가 없습니다" not in text
    assert isinstance(raised.value.__cause__, ImportError | AttributeError)


def test_a_missing_dependency_names_that_module_not_the_package(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """빠진 것이 패키지가 쓰는 모듈이면 그 이름을 알린다. 같은 화면 배너는 패키지를 확인했다고
    띄운다."""
    _installed_package(monkeypatch, tmp_path, "import capa_bdq_missing_dependency\n")

    with pytest.raises(RuntimeError) as raised:
        adapter.load_bigdataquery_module()

    text = str(raised.value)
    assert "capa_bdq_missing_dependency" in text and "불러오지 못했습니다" in text
    assert "패키지가 없습니다" not in text
    assert adapter.failure_type_names(raised.value) == ("RuntimeError", "ModuleNotFoundError")


def test_unconfigured_query_is_rejected_before_package_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = False

    def fake_import(_: str) -> object:
        nonlocal imported
        imported = True
        return object()

    monkeypatch.setattr(importlib, "import_module", fake_import)
    # 모듈 기본 SQL 은 사내 조회문으로 채워져 있다. 미설정 경로를 보려면 표식이 남은
    # 템플릿을 명시로 준다.
    provider = adapter.BigDataQueryCoreDataProvider(
        "사내 조회",
        query_template=f"SELECT {adapter.UNCONFIGURED_MARKER} WHERE x = '{{simulation_code}}'",
    )

    with pytest.raises(RuntimeError, match="SQL이 아직 설정되지 않았습니다"):
        provider.fetch("SIM-001")

    assert not imported


def test_provider_returns_renamed_dataframe_without_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_get_data(*, param: str, convert_type: bool, verbose: bool) -> pd.DataFrame:
        captured.update(
            param=param,
            convert_type=convert_type,
            verbose=verbose,
        )
        # `fetch` 는 MPGA TEST 예외를 적용하므로 원천에 `공정`·`모듈수` 가 있어야 한다.
        return pd.DataFrame({"db_product": ["Product*_A"], "공정": ["ASSY"], "모듈수": [2]})

    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _: SimpleNamespace(getData=fake_get_data),
    )
    provider = adapter.BigDataQueryCoreDataProvider(
        "사내 조회",
        query_template="SELECT * FROM source WHERE simulation_code = '{simulation_code}'",
        column_mapping={"db_product": "제품정보"},
    )

    batch = provider.fetch("SIM-001")

    assert batch.source_type == "BIGDATAQUERY"
    assert batch.frame.columns.tolist() == ["제품정보", "공정", "모듈수"]
    assert captured == {
        "param": "SELECT * FROM source WHERE simulation_code = 'SIM-001'",
        "convert_type": True,
        "verbose": True,
    }


@pytest.mark.parametrize("code", ["SIM 001", "SIM'001", "한글코드"])
def test_provider_rejects_unsafe_simulation_code(code: str) -> None:
    with pytest.raises(ValueError, match="영문·숫자"):
        adapter.build_query("SELECT '{simulation_code}'", code)


def test_mpga_test_module_count_exception_normalizes_to_one() -> None:
    """MPGA TEST 의 0.95~0.96 모듈수는 1로 본다.

    원천 산정 규칙이 확정될 때까지 두는 예외이므로(`docs/TODO.md` 결정 기록, 옛 3-7) 동작을 고정해
    조용히 사라지지 않게 한다. 같은 값이라도 공정이 다르면 손대지 않는다.
    """
    frame = pd.DataFrame(
        {
            "공정": ["MPGA TEST", "MPGA TEST", "MPGA TEST", "ASSY"],
            "모듈수": [0.955, 0.94, 2, 0.955],
        }
    )

    provider = adapter.BigDataQueryCoreDataProvider(
        "사내 조회",
        query_template="SELECT '{simulation_code}'",
        column_mapping={},
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            importlib,
            "import_module",
            lambda _: SimpleNamespace(getData=lambda **_kwargs: frame),
        )
        batch = provider.fetch("SIM-001")

    assert batch.frame["모듈수"].tolist() == [1, 0.94, 2, 0.955]


@pytest.mark.parametrize("missing_column", ["공정", "모듈수"])
def test_provider_reports_missing_columns_before_source_adjustment(
    monkeypatch: pytest.MonkeyPatch, missing_column: str
) -> None:
    frame = pd.DataFrame({"공정": ["MPGA TEST"], "모듈수": [0.955]}).drop(columns=missing_column)
    monkeypatch.setattr(
        adapter, "load_bigdataquery_module", lambda: _module(lambda **_kwargs: frame)
    )
    provider = adapter.BigDataQueryCoreDataProvider("사내 조회", column_mapping={})

    with pytest.raises(ValueError, match=f"필요한 컬럼이 없습니다: {missing_column}"):
        provider.fetch("SIM-001")


def test_provider_reports_mapping_collisions_before_source_adjustment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = pd.DataFrame({"공정": ["MPGA TEST"], "모듈수": [0.955], "module_count": [2]})
    monkeypatch.setattr(
        adapter, "load_bigdataquery_module", lambda: _module(lambda **_kwargs: frame)
    )
    provider = adapter.BigDataQueryCoreDataProvider(
        "사내 조회", column_mapping={"module_count": "모듈수"}
    )

    with pytest.raises(ValueError, match="중복 컬럼이 있습니다: 모듈수"):
        provider.fetch("SIM-001")

    assert frame["모듈수"].tolist() == [0.955]


def _contract_columns() -> list[str]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return [column["name"] for column in contract["source"]["columns"]]


def _query_aliases() -> list[str]:
    select_clause = adapter.QUERY_TEMPLATE.split("FROM", 1)[0]
    aliases: list[str] = []
    for line in select_clause.splitlines():
        item = line.strip().rstrip(",")
        if not item or item.upper() == "SELECT":
            continue
        assert " AS " in item, f"별칭이 없는 SELECT 항목: {item}"
        aliases.append(item.rsplit(" AS ", 1)[1].strip().strip("`"))
    return aliases


def test_query_aliases_match_the_core_data_contract() -> None:
    """SELECT 별칭이 78컬럼 계약과 한 글자라도 다르면 정규화에서 통째로 실패한다.

    실제로 `Module/Comp`·`Plan_Chip(k개)`·`WF측정룰` 세 개가 대소문자·철자만 달라
    사내 조회가 통째로 막혔었다. 눈으로는 걸러지지 않아 여기서 잡는다.
    """
    assert _query_aliases() == _contract_columns()


def test_column_mapping_only_targets_contract_columns() -> None:
    """대문자가 섞인 계약 컬럼은 소문자 키가 모두 있어야 한다.

    드라이버가 컬럼명을 소문자로 돌려주는 경우를 위한 매핑이므로, 하나라도 빠지면 그
    컬럼만 계약과 어긋난다.
    """
    expected = _contract_columns()
    assert [
        value for value in adapter.SOURCE_COLUMN_MAPPING.values() if value not in expected
    ] == []
    needs_key = [name for name in expected if name.lower() != name]
    assert [name for name in needs_key if name.lower() not in adapter.SOURCE_COLUMN_MAPPING] == []


def test_query_window_upper_bound_includes_the_end_date() -> None:
    """종료일 당일 적재분이 빠지던 결함의 회귀선(docs/TODO.md 결정 기록, 옛 3-7).

    화면 라벨이 '포함' 이므로 배타 상한(`<`)을 다음 날로 민다.
    """
    window = adapter.QueryWindow(start_date=date(2026, 6, 10), end_date=date(2026, 9, 8))

    assert window.sql_bounds() == ("2026-06-10", "2026-09-09")
    assert window.days == 91
    assert window.label() == "2026-06-10 ~ 2026-09-08"


def test_query_window_rejects_a_reversed_period() -> None:
    with pytest.raises(ValueError, match="시작일은 종료일보다"):
        adapter.QueryWindow(start_date=date(2026, 9, 9), end_date=date(2026, 9, 8))


def test_build_query_uses_the_given_window() -> None:
    window = adapter.QueryWindow(start_date=date(2026, 9, 1), end_date=date(2026, 9, 8))

    query = adapter.build_query(adapter.QUERY_TEMPLATE, "SIM-001", window=window)

    assert "'2026-09-01'" in query
    assert "'2026-09-09'" in query
    assert "{" not in query


def test_build_query_without_a_window_keeps_the_default_window() -> None:
    """기존 호출부(위치 인자 2개)가 그대로 돌아야 한다."""
    today = date(2026, 9, 8)
    expected = adapter.default_query_window(today=today).sql_bounds()

    query = adapter.build_query(adapter.QUERY_TEMPLATE, "SIM-001")

    assert adapter.DEFAULT_QUERY_WINDOW_DAYS == 90
    assert len(expected[0]) == 10
    assert "impala_insert_time" in query


def test_the_detail_window_defaults_to_a_few_days_around_the_registration_date() -> None:
    """상세 조회 기본 창은 원천 등록일 7일 전 ~ 3일 뒤다(2026-09-29 사용자 결정 A+B).

    예전에는 기본 90일 ∪ 목록 기간 ∪ 등록일 7일 전~오늘이라 옛 코드일수록 창이 길어져 사내
    조회가 오래 걸렸다. 몇 달 전 코드도 이제 등록일 앞뒤 11일치만 읽는다.
    """
    today = date(2026, 9, 29)
    registered = date(2026, 3, 10)

    window = adapter.registration_detail_window(registered, today=today)

    assert window.start_date == registered - timedelta(days=adapter.DETAIL_WINDOW_DAYS_BEFORE)
    assert window.end_date == registered + timedelta(days=adapter.DETAIL_WINDOW_DAYS_AFTER)
    assert (adapter.DETAIL_WINDOW_DAYS_BEFORE, adapter.DETAIL_WINDOW_DAYS_AFTER) == (7, 3)
    assert window.days == 11


def test_provider_passes_the_window_into_the_query(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_get_data(*, param: str, convert_type: bool, verbose: bool) -> pd.DataFrame:
        captured["param"] = param
        return pd.DataFrame({"제품정보": ["Product-A"], "공정": ["ASSY"], "모듈수": [2]})

    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _: SimpleNamespace(getData=fake_get_data),
    )
    provider = adapter.BigDataQueryCoreDataProvider(
        "사내 조회",
        query_template=(
            "SELECT '{simulation_code}' WHERE t >= '{start_date}' AND t < '{end_date}'"
        ),
        column_mapping={},
        window=adapter.QueryWindow(start_date=date(2026, 9, 1), end_date=date(2026, 9, 8)),
    )

    provider.fetch("SIM-001")

    assert captured["param"] == "SELECT 'SIM-001' WHERE t >= '2026-09-01' AND t < '2026-09-09'"


def test_empty_result_is_rejected_before_the_module_count_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """0행 가드가 rename 뒤에 있으면 `KeyError('모듈수')` 로 먼저 터진다."""
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _: SimpleNamespace(getData=lambda **_kwargs: pd.DataFrame()),
    )
    provider = adapter.BigDataQueryCoreDataProvider(
        "사내 조회",
        query_template="SELECT '{simulation_code}'",
        column_mapping={},
    )

    with pytest.raises(ValueError, match="0행"):
        provider.fetch("SIM-001")


def test_catalog_sql_is_not_mixed_into_the_detail_template() -> None:
    """상세 SQL 은 78별칭 대조를 받는다. 목록 문장을 여기 합치면 그 검사가 깨진다."""
    assert "{simulation_code}" in adapter.QUERY_TEMPLATE
    assert "SELECT DISTINCT" not in adapter.QUERY_TEMPLATE


def test_package_probe_does_not_import_the_module(monkeypatch: pytest.MonkeyPatch) -> None:
    imported = False

    def fake_import(_: str) -> object:
        nonlocal imported
        imported = True
        return object()

    monkeypatch.setattr(importlib, "import_module", fake_import)

    adapter.is_bigdataquery_package_available()

    assert not imported


def test_valid_simulation_code_predicate_matches_the_validator() -> None:
    assert adapter.is_valid_simulation_code("DEMO-A_001.2") is True
    assert adapter.is_valid_simulation_code("DEMO 공백") is False
    assert adapter.is_valid_simulation_code("   ") is False


def test_the_detail_window_covers_every_registration_the_catalog_saw() -> None:
    """목록에 같은 코드의 등록일이 여러 날 보였으면 기본 창이 그 사이를 자르지 않는다."""
    window = adapter.registration_detail_window(
        date(2026, 3, 1), date(2026, 3, 20), today=date(2026, 9, 29)
    )

    assert window.start_date == date(2026, 2, 22)
    assert window.end_date == date(2026, 3, 23)


def test_the_detail_window_never_ends_after_today() -> None:
    """날짜 입력의 상한이 오늘이다. 등록일이 어제거나 (시계가 어긋나) 내일이어도 창이 선다."""
    today = date(2026, 9, 29)

    yesterday = adapter.registration_detail_window(today - timedelta(days=1), today=today)
    tomorrow = adapter.registration_detail_window(today + timedelta(days=1), today=today)

    assert yesterday.start_date == today - timedelta(days=8)
    assert yesterday.end_date == today
    assert tomorrow.start_date <= tomorrow.end_date <= today


def _start_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    install: tuple[str, str] = ("skipped", "CD 환경변수 CAPA_ARTIFACTORY_USER 없음"),
    token: tuple[str, str] = ("skipped", "CD 환경변수 CAPA_BDQ_TOKEN 없음"),
    user_name: tuple[str, str] = ("skipped", "CD 환경변수 CAPA_BDQ_USER_NAME 없음"),
    missing: tuple[str, ...] = ("CAPA_ARTIFACTORY_USER", "CAPA_BDQ_TOKEN", "CAPA_BDQ_USER_NAME"),
) -> None:
    """C-DEP CD 시작 스크립트가 남기는 결과 파일(`settings.CONTAINER_START_REPORT_PATH`)."""
    import capa_simulation.settings as settings

    path = tmp_path / "container_start.json"
    steps = {"install": install, "token": token, "user_name": user_name}
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "written_at": "2026-10-24T09:00:00+09:00",
                "steps": {
                    name: {"status": status, "reason": reason}
                    for name, (status, reason) in steps.items()
                },
                "bigdataquery_version": None,
                "token_file": {"exists": None, "modified_at": None},
                "user_name": {"present": False, "masked": None},
                "missing_environment": list(missing),
                "pip_tail": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", path)


def test_a_missing_package_in_the_cd_container_adds_the_start_check_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CD 서버에는 셸이 없어 설치 안내(`uv pip install …`)를 따를 수 없다. 시작 스크립트가 남긴 설치
    단계 결과와 넣을 환경변수를 덧붙인다. 첫 문장은 점검 스크립트가 가르는 문구라 그대로다."""
    _start_report(tmp_path, monkeypatch, install=("failed", "설치 시도 실패 — pip 종료 코드 1"))
    monkeypatch.setitem(sys.modules, "bigdataquery", None)

    with pytest.raises(RuntimeError) as raised:
        adapter.load_bigdataquery_module()

    text = str(raised.value)
    assert text.startswith(_PACKAGE_MISSING_TEXT)
    assert "서버 시작 점검" in text and "pip 종료 코드 1" in text
    assert adapter.BDQ_USER_NAME_ENV not in text

    _start_report(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError) as raised:
        adapter.load_bigdataquery_module()
    assert "`CAPA_ARTIFACTORY_USER`" in str(raised.value)


class TokenNotFoundException(Exception):
    """사내 패키지가 로그인 토큰이 없을 때 내는 꼴(`docs/bigdataquery_webide_setup.md` 1단계)."""


def _missing_token(**_kwargs: object) -> pd.DataFrame:
    raise TokenNotFoundException(
        "There is no bigdataquery token issued for AD user 'fake' at '/config/.credential/' "
        "on 'Linux'."
    )


def test_a_missing_login_token_in_the_cd_container_adds_the_start_check_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """토큰이 없다는 패키지 예외에는 토큰 파일 단계 결과와 `CAPA_BDQ_TOKEN` 을 덧붙인다. 갈래·종류
    이름(점검 스크립트가 찍는 것)은 결과 파일이 있든 없든 같다."""
    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, "fake")
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(_missing_token))

    with pytest.raises(adapter.BigDataQueryCallError) as plain:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")
    assert "서버 시작 점검" not in str(plain.value)

    _start_report(tmp_path, monkeypatch)
    with pytest.raises(adapter.BigDataQueryCallError) as hinted:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    text = str(hinted.value)
    assert text.startswith(str(plain.value))
    assert "서버 시작 점검" in text and "`CAPA_BDQ_TOKEN`" in text
    assert (hinted.value.kind, hinted.value.type_names) == (
        plain.value.kind,
        plain.value.type_names,
    )


def test_a_written_token_that_is_still_refused_points_at_expiry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, "fake")
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(_missing_token))
    _start_report(tmp_path, monkeypatch, token=("ok", "토큰 파일을 씀"), missing=())

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert "만료" in str(raised.value) and "WebIDE" in str(raised.value)


def test_a_missing_account_in_the_cd_container_adds_the_start_check_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def refuse(**_kwargs: object) -> pd.DataFrame:
        raise ValueError("Parameter user_name is necessary.")

    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(refuse))
    _start_report(tmp_path, monkeypatch)

    with pytest.raises(RuntimeError) as raised:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    text = str(raised.value)
    assert text.startswith("BigDataQuery 조회에 요청자의 사내 계정이 필요합니다.")
    assert "서버 시작 점검" in text and "C-DEP" in text


def test_an_unrelated_failure_gets_no_start_check_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def refuse(**_kwargs: object) -> pd.DataFrame:
        raise ValueError("table not found")

    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, "fake")
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(refuse))
    _start_report(tmp_path, monkeypatch)

    with pytest.raises(adapter.BigDataQueryCallError) as raised:
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")

    assert "서버 시작 점검" not in str(raised.value)


def test_a_cd_server_without_a_start_report_says_so_after_the_missing_package_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CD 환경변수는 들어왔는데 결과 파일이 없으면(스크립트가 돌지 않음) 첫 문장 뒤에 그 사실을
    덧붙인다. 첫 문장과 점검 스크립트가 가르는 이름은 그대로다."""
    import capa_simulation.settings as settings

    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", tmp_path / "없음.json")
    monkeypatch.setenv("CAPA_ARTIFACTORY_TOKEN", "FAKE-artifactory-token")
    monkeypatch.setitem(sys.modules, "bigdataquery", None)

    with pytest.raises(RuntimeError) as raised:
        adapter.load_bigdataquery_module()

    text = str(raised.value)
    assert text.startswith(_PACKAGE_MISSING_TEXT)
    assert "서버 시작 점검 결과가 없습니다" in text and "돌지 않은 것으로" in text
    assert adapter.BDQ_USER_NAME_ENV not in text
    assert "FAKE-artifactory-token" not in text
