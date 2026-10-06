# Purpose: company bigdataquery adapter 관련 정상·예외·회귀 동작을 검증한다.

from __future__ import annotations

import importlib
import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from capa_simulation.io import company_bigdataquery_adapter as adapter

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
    """계정과 상관없는 실패까지 계정 안내로 바꾸면 진짜 원인이 가려진다."""

    def refuse(**_kwargs: object) -> pd.DataFrame:
        raise ValueError("table not found")

    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    monkeypatch.setattr(importlib, "import_module", lambda _: _module(refuse))

    with pytest.raises(ValueError, match="table not found"):
        adapter.call_get_data(adapter.load_bigdataquery_module(), "SELECT 1")


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

    원천 산정 규칙이 확정될 때까지 두는 예외이므로(`docs/TODO.md` 3-7) 동작을 고정해
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
    """종료일 당일 적재분이 빠지던 결함의 회귀선(docs/TODO.md 3-7).

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
