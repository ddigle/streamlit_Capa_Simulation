# Purpose: 계산 페이지 공통 준비 절차의 조회기간 해석과 예외 계약을 검증한다.

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from capa_simulation import alerts, page_bootstrap, settings
from capa_simulation.io.reference_cache import NoActiveRevision
from capa_simulation.navigation import REFERENCE_DATA
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PageContext,
    bootstrap_error_message,
    calculation_stop_notice,
    resolve_effective_months,
)
from capa_simulation.reference_grid_keys import DATASETS
from capa_simulation.scenario_preset_state import MONTH_RANGE_KEY
from capa_simulation.scenario_state import pristine_content_token
from capa_simulation.services import unit_capacity
from capa_simulation.services.simulation_cache import outside_period_error


def _context(start: int, end: int) -> PageContext:
    return PageContext(
        reference_version=1,
        reference_tables={},
        display_order=None,
        active_scenario={
            "reference_version": 1,
            "revision": 0,
            "content_token": pristine_content_token(1),
            "tables": {},
        },
        selected_start_month=start,
        selected_end_month=end,
    )


def _source(months: list[int]) -> pd.DataFrame:
    return pd.DataFrame({"생산계획년월": months, "값": [1.0] * len(months)})


def test_effective_months_are_the_intersection_with_the_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applied: list[tuple[int, int]] = []
    monkeypatch.setattr(
        page_bootstrap, "show_applied_month_range", lambda s, e: applied.append((s, e))
    )

    result = resolve_effective_months(
        _context(202601, 202612),
        _source([202603, 202606, 202609]),
        "RQ_REQB",
        empty_message="없음",
    )

    assert result == (202603, 202609)
    assert applied == [(202603, 202609)]


def test_disjoint_ranges_raise_the_page_specific_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(page_bootstrap, "show_applied_month_range", lambda s, e: None)

    with pytest.raises(ValueError, match="선택 범위에 소요대수 산출 기준이 없습니다"):
        resolve_effective_months(
            _context(202701, 202712),
            _source([202601, 202602]),
            "RQ_REQB",
            empty_message="선택 범위에 소요대수 산출 기준이 없습니다.",
        )


def test_bootstrap_errors_cover_every_failure_the_entry_sequence_can_raise() -> None:
    """활성 리비전이 없으면 RuntimeError 다. 페이지마다 다른 조합을 잡으면 새어나간다.

    `duckdb.Error` 가 빠지면 파일 잠금이 원문 트레이스백으로 뜬다 — IOException 의 MRO 에
    OSError 가 없다는 것을 09-04 기준선이 실측했다.
    """
    import duckdb

    assert set(BOOTSTRAP_ERRORS) == {
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        duckdb.Error,
    }
    assert issubclass(duckdb.IOException, BOOTSTRAP_ERRORS)


def test_database_error_message_follows_who_holds_the_lock() -> None:
    """잠금을 쥔 쪽에 맞는 조치를 권한다(E2E G1-D0).

    이 앱 자신이 쥔 잠금에 「다른 창을 닫으라」고 하면 틀린 조치다 — 한 서버가 모든 창을
    받으므로 닫을 창이 없고, 새로고침이면 이어진다.
    """
    import os
    from pathlib import Path

    import duckdb

    def lock_error(pid: int) -> duckdb.IOException:
        return duckdb.IOException(
            'IO Error: Cannot open file "x.duckdb": ???\r\n\n'
            f"File is already open in \nC:\\Python310\\python.exe (PID {pid})"
        )

    own = page_bootstrap.bootstrap_error_message(lock_error(os.getpid()))
    assert "새로고침" in own
    assert "닫을 필요는 없습니다" in own
    assert "다른 창에서 실행 중" not in own

    other_pid = os.getpid() + 1
    other = page_bootstrap.bootstrap_error_message(lock_error(other_pid))
    assert f"PID {other_pid}" in other
    assert "브라우저 창·탭 여러 개로 여는 것은 원인이 아닙니다" in other

    # 쥔 프로세스를 적지 않은 열기 실패(권한·없는 폴더·공유 위반)는 열기 안내 그대로다.
    opening = page_bootstrap.bootstrap_error_message(
        duckdb.IOException('IO Error: Cannot open file "x.duckdb": Permission denied')
    )
    assert opening.startswith("데이터베이스를 열지 못했습니다.")
    assert "파일 권한과 경로" in opening
    assert "원문" not in opening

    # 어느 파일인지는 부르는 쪽이 정한다.
    equipment = Path("equipment_availability.duckdb")
    assert f"`{equipment}`" in page_bootstrap.bootstrap_error_message(
        lock_error(other_pid), database_paths=(equipment,)
    )
    assert page_bootstrap.bootstrap_error_message(ValueError("한국어 문장")) == "한국어 문장"


def _store_with_scenarios(path: Path, *, archived: int, active: int) -> None:
    """내장 합성 시드로 시나리오를 만들어 앞 `archived` 개를 보관한다 — 공식버전은 없다."""
    from capa_simulation.persistence.models import ScenarioCreate, ScenarioPreset
    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.services.builtin_seed import (
        build_builtin_seed_dataset,
        load_builtin_display_order,
    )

    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    repository.initialize_global_display_order(load_builtin_display_order())
    prepared = build_builtin_seed_dataset()
    for number in range(archived + active):
        snapshot = repository.create_scenario(
            ScenarioCreate(
                scenario_name=f"DEMO 시나리오 {number}",
                source_simulation_code=f"DEMO-SIM-{number}",
                source_simulation_name="DEMO",
                source_type="BUILTIN_SEED",
                pipeline_version="test",
            ),
            prepared.reference_tables,
            ScenarioPreset(start_month=202601, end_month=202612, included_processes=()),
            source_data=prepared.source_data,
            revision_name="r1",
            note="",
        )
        if number < archived:
            repository.archive_scenario(snapshot.scenario.scenario_id)


def test_no_active_revision_over_a_store_of_archived_scenarios_points_at_the_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """시나리오가 모두 보관본이면 첫 접속이 불러올 것도, 목록에서 고를 것도 없다 — 「활성 DuckDB
    리비전 버전이 없습니다」 대신 보관함에서 되돌리라고 한다(2026-11-08 결정 a8)."""
    database = tmp_path / "archived.duckdb"
    _store_with_scenarios(database, archived=2, active=0)
    monkeypatch.setattr(settings, "DUCKDB_PATH", database)

    message = bootstrap_error_message(NoActiveRevision("활성 DuckDB 리비전 버전이 없습니다."))

    assert message == page_bootstrap.ARCHIVED_ONLY_MESSAGE
    assert "보관함" in message and "되돌리기" in message
    assert "DuckDB" not in message


@pytest.mark.parametrize(("archived", "active"), [(1, 1), (0, 0)], ids=["listed", "empty"])
def test_no_active_revision_keeps_its_message_unless_every_scenario_is_archived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, archived: int, active: int
) -> None:
    database = tmp_path / "store.duckdb"
    _store_with_scenarios(database, archived=archived, active=active)
    monkeypatch.setattr(settings, "DUCKDB_PATH", database)

    assert (
        bootstrap_error_message(NoActiveRevision("활성 DuckDB 리비전 버전이 없습니다."))
        == "활성 DuckDB 리비전 버전이 없습니다."
    )


@pytest.mark.parametrize(
    ("table", "name"),
    [("RQ_REQB", "「STEP 구성」"), ("RQ_EQP_AVBL", "「설비대수 가용」"), ("RQ_UPEH", "「UPEH」")],
)
def test_an_empty_route_table_names_its_screen_table_and_the_source_fix(
    table: str, name: str
) -> None:
    """경로 표가 빈 리비전(계획 행만 있는 원천)을 연 계산 화면은 조회기간을 정하다 「RQ_REQB에
    선택할 생산계획년월 데이터가 없습니다」 로만 멈췄다 — 화면의 표 이름과 원천을 고쳐 다시
    등록하라는 말로 바꾼다(검수 보드 st-month-text). 같은 리비전이 HOME 에서는 설비대수 가용으로
    멈춘다."""
    message = bootstrap_error_message(
        ValueError(f"{table}에 선택할 생산계획년월 데이터가 없습니다.")
    )

    assert message == f"{name} 표가 비어 계산이 멈춥니다 — 원천을 고쳐 다시 등록하세요."
    assert "RQ_" not in message


@pytest.mark.parametrize("table", ["RQ_PKG_PLAN", "RQ_LOT_RATIO", "RQ_TEST"])
def test_other_empty_tables_keep_their_month_message(table: str) -> None:
    """계획 표(경로 행만 있는 원천)와 측정률 표(비어도 계산이 선다)의 빈 표 글은 그대로다."""
    raw = f"{table}에 선택할 생산계획년월 데이터가 없습니다."

    assert bootstrap_error_message(ValueError(raw)) == raw


def test_no_active_revision_does_not_create_a_missing_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """글을 고르려고 없는 DB 를 만들지 않는다 — 판정은 있는 저장소만 읽는다."""
    database = tmp_path / "absent.duckdb"
    monkeypatch.setattr(settings, "DUCKDB_PATH", database)

    message = bootstrap_error_message(NoActiveRevision("활성 DuckDB 리비전 버전이 없습니다."))

    assert message == "활성 DuckDB 리비전 버전이 없습니다."
    assert not database.exists()


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(
            'IO Error: Could not write file "x.duckdb.wal": No space left on device',
            id="disk-full",
        ),
        pytest.param(
            'IO Error: Could not write to file "x.duckdb" - attempted to write 0 bytes: '
            "File too large",
            id="file-size-limit",
        ),
    ],
)
def test_a_write_failure_says_nothing_was_saved_instead_of_closing_other_programs(
    error: str,
) -> None:
    """저장 중 디스크 가득·파일 크기 한도는 잠금이 아니다 — 닫을 프로그램이 없다.

    DuckDB 가 영문으로 박아 둔 「Could not write」로 가른다. 원문(종류 이름 + 문구)을 붙여
    원인을 보인다.
    """
    import duckdb

    message = page_bootstrap.bootstrap_error_message(duckdb.IOException(error))

    assert message.startswith(
        "데이터베이스에 쓰지 못했습니다 — 저장되지 않았습니다. "
        "디스크 공간과 쓰기 권한을 확인하세요."
    )
    assert "다른 프로그램" not in message
    assert "열지 못했습니다" not in message
    assert f"- 원문: ` IOException: {error} `" in message


def test_a_failed_commit_is_a_write_failure_whatever_its_exception_kind() -> None:
    """커밋 실패는 `TransactionException` 등으로도 온다 — 종류가 아니라 「Failed to commit」
    으로 가른다."""
    import duckdb

    message = page_bootstrap.bootstrap_error_message(
        duckdb.TransactionException("TransactionContext Error: Failed to commit: disk I/O error")
    )

    assert message.startswith("데이터베이스에 쓰지 못했습니다 — 저장되지 않았습니다.")
    assert "TransactionException: TransactionContext Error: Failed to commit" in message


def test_any_other_database_error_says_the_operation_failed_and_shows_the_original() -> None:
    """열기·잠금·쓰기가 아닌 실패(없는 표·깨진 파일 등)에 열기 조치를 권하지 않는다."""
    from pathlib import Path

    import duckdb

    error = duckdb.CatalogException(
        "Catalog Error: Table with name x does not exist!\n\nLINE 1: select * from x"
    )
    equipment = Path("equipment_availability.duckdb")
    message = page_bootstrap.bootstrap_error_message(error, database_paths=(equipment,))

    assert message.startswith("데이터베이스 작업이 실패했습니다.")
    assert f"- 파일: `{equipment}`" in message
    assert "파일 권한과 경로" not in message
    assert "다른 프로그램" not in message
    # 원문의 줄바꿈은 한 줄로 접는다 — 줄 머리의 글자가 마크다운 블록으로 읽히지 않게.
    assert (
        "- 원문: ` CatalogException: Catalog Error: Table with name x does not exist! "
        "LINE 1: select * from x `"
    ) in message


def test_the_original_text_is_cut_and_stays_literal_under_markdown() -> None:
    """원문은 종류 이름 + 앞 300자이고, 코드 표기라 `$`·`*`·`#` 가 수식·강조·제목이 되지 않는다.

    원문에 역따옴표가 있으면 그보다 긴 울타리로 싼다 — 같은 길이면 코드 표기가 중간에 닫힌다.
    """
    import duckdb

    long_message = page_bootstrap.bootstrap_error_message(duckdb.InternalException("가" * 1000))
    original = next(line for line in long_message.splitlines() if line.startswith("- 원문: "))
    assert original == f"- 원문: ` InternalException: {'가' * 300} … `"

    tricky = "Binder Error: `a` $x$ *b*\n# 제목\n- 목록 ``c``"
    message = page_bootstrap.bootstrap_error_message(duckdb.BinderException(tricky))
    lines = message.splitlines()
    original_lines = [line for line in lines if line.startswith("- 원문: ")]
    assert original_lines == [
        "- 원문: ``` BinderException: Binder Error: `a` $x$ *b* # 제목 - 목록 ``c`` ```"
    ]
    assert not any(line.startswith("#") for line in lines)


def _service_stop(status: int, table: str = "RQ_RUN_RATE", column: str = "CAPA_RUN_RATE") -> str:
    """계산이 실제로 내는 오류 글 — 글이 바뀌면 판정이 조용히 빗나가지 않게 여기서 받는다."""
    joined = pd.DataFrame({"공정": ["DEMO-P1"], "상태": [status]})
    check = unit_capacity._PendingCheck(table, column, ["공정"], "상태", None)
    with pytest.raises(ValueError) as error:
        unit_capacity._raise_on_unusable_values(joined, check)
    return str(error.value)


def _on_page(monkeypatch: pytest.MonkeyPatch, page: str = "HOME") -> None:
    monkeypatch.setattr(alerts, "current_page", lambda: (page, "home"))


@pytest.mark.parametrize(
    ("table", "column", "name"),
    [
        ("RQ_RUN_RATE", "CAPA_RUN_RATE", "효율"),
        ("RQ_VITAL", "편중률", "여유율"),
        ("RQ_RUN_DAY", "RUN_DAY", "일수"),
        ("RQ_LOT_RATIO", "Lot 측정률", "Lot측정률"),
    ],
)
def test_a_blank_stop_points_at_the_table_to_fill_on_the_reference_screen(
    monkeypatch: pytest.MonkeyPatch, table: str, column: str, name: str
) -> None:
    """빈 칸 멈춤은 무엇을 · 어디서 채우는지 말하고 「그 화면으로」 가 기준 정보의 그 표를 연다
    (UI-NTF-06 · UI-NTF-08). 전문은 어느 화면의 일인지부터 적고, 건수 · 예시 행은 남기되 표 이름은
    화면 이름이다."""
    _on_page(monkeypatch)
    stop = calculation_stop_notice(
        ValueError(_service_stop(unit_capacity._VALUE_BLANK, table, column))
    )

    assert stop is not None
    assert stop.text == f"대당 Capa 계산 멈춤 — 기준 정보 「{name}」 빈 칸 1건을 채움"
    assert DATASETS[table] == name
    assert stop.goto == ("기준 정보", REFERENCE_DATA.href, name)
    assert stop.message.startswith(
        f"HOME — 대당 Capa 계산이 멈췄습니다. 기준 정보 「{name}」 표의 "
    )
    assert "「변경사항 적용」" in stop.message
    assert f"「{name}」 표의 빈 칸: 1건, 예시 " in stop.message
    assert "'공정': 'DEMO-P1'" in stop.message
    assert table not in stop.message and column not in stop.message


def test_a_row_missing_from_the_reference_table_is_the_same_empty_cell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """연결값 없음도 빠진 입력이다 — 기준 정보 표의 같은 빈 칸을 채워 푼다."""
    _on_page(monkeypatch)
    stop = calculation_stop_notice(ValueError(_service_stop(unit_capacity._VALUE_NO_MATCH)))

    assert stop is not None
    assert stop.text == "대당 Capa 계산 멈춤 — 기준 정보 「효율」 빈 칸 1건을 채움"


def test_a_stop_outside_the_period_keeps_saying_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """조회기간 밖 달의 빈 칸도 같은 곳에서 채운다 — 글 끝의 머리를 찾고 기간 말은 전문에 남는다."""
    _on_page(monkeypatch)
    error = outside_period_error(202601, 202612, _service_stop(unit_capacity._VALUE_BLANK))

    stop = calculation_stop_notice(ValueError(error))

    assert stop is not None
    assert stop.text == "대당 Capa 계산 멈춤 — 기준 정보 「효율」 빈 칸 1건을 채움"
    assert "밖의 달에 기준정보 오류가 있어" in stop.message
    assert "RQ_RUN_RATE" not in stop.message


def test_a_stop_without_a_page_name_starts_from_the_stop_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _on_page(monkeypatch, "")
    stop = calculation_stop_notice(ValueError(_service_stop(unit_capacity._VALUE_BLANK)))

    assert stop is not None and stop.message.startswith("대당 Capa 계산이 멈췄습니다.")


def _service_nonpositive(table: str, column: str) -> str:
    """0 이하로 멈춘 계산이 실제로 내는 오류 글(`unit_capacity._assert_positive`). 한 칸이 세 계산
    경로에 붙은 꼴이다 — 글의 건수가 행이 아니라 고칠 칸이어야 「0 이하 칸 1건」 이 맞는다."""
    joined = pd.DataFrame(
        {"공정": ["DEMO-P1"] * 3, "제품정보": ["DEMO-A", "DEMO-B", "DEMO-C"], column: [0.0] * 3}
    )
    with pytest.raises(ValueError) as error:
        unit_capacity._assert_positive(joined, column, table, ["공정"])
    return str(error.value)


def _service_upeh_stop(area: str, upeh: float | None, st_minutes: float | None) -> str:
    """UPEH 표의 Main · MI 행 값으로 멈춘 계산이 실제로 내는 오류 글(`_prepare_performance`)."""
    row: dict[str, object] = dict.fromkeys(unit_capacity.PERFORMANCE_KEYS, "DEMO")
    row.update(
        {
            "생산계획년월": 202601,
            "Area_Name": area,
            "소요기준": "WF",
            "UPEH": upeh,
            "ST": st_minutes,
        }
    )
    with pytest.raises(ValueError) as error:
        unit_capacity._prepare_performance(pd.DataFrame([row]))
    return str(error.value)


@pytest.mark.parametrize(
    ("error", "cell"),
    [
        (_service_nonpositive("RQ_VITAL", "편중률"), "「여유율」 0 이하 칸 1건"),
        (_service_nonpositive("RQ_RUN_DAY", "RUN_DAY"), "「일수」 0 이하 칸 1건"),
        (
            _service_stop(unit_capacity._VALUE_NOT_NUMERIC),
            "「효율」 숫자 아닌 칸 1건",
        ),
        (
            _service_stop(unit_capacity._VALUE_NOT_NUMERIC, "RQ_LOT_RATIO", "Lot 측정률"),
            "「Lot측정률」 숫자 아닌 칸 1건",
        ),
        (_service_upeh_stop("MI", 1.0, 0.0), "「UPEH」 MI 행 ST 0 이하 칸"),
        (_service_upeh_stop("MI", 1.0, None), "「UPEH」 MI 행 ST 빈 칸 · 숫자 아닌 칸"),
        (_service_upeh_stop("Main", None, None), "「UPEH」 Main 행 UPEH 빈 칸 · 숫자 아닌 칸"),
    ],
    ids=[
        "vital-zero",
        "run-day-zero",
        "run-rate-text",
        "lot-text",
        "st-zero",
        "st-text",
        "upeh-text",
    ],
)
def test_a_value_to_correct_points_at_the_reference_table_too(
    monkeypatch: pytest.MonkeyPatch, error: str, cell: str
) -> None:
    """0 이하 · 숫자 아닌 값도 기준 정보 표의 칸을 고쳐 푼다 — 무엇을 · 어디서 고치는지 말하고
    「그 화면으로」 가 기준 정보를 연다(UI-NTF-06 · UI-NTF-08). 전문에도 내부 표 이름이 없다."""
    _on_page(monkeypatch)
    stop = calculation_stop_notice(ValueError(error))

    assert stop is not None
    assert stop.text == f"대당 Capa 계산 멈춤 — 기준 정보 {cell}을 고침"
    assert len(stop.text) <= alerts.SHORT_LIMIT
    name, _, what = cell.partition(" ")
    assert stop.goto == ("기준 정보", REFERENCE_DATA.href, name.strip("「」"))
    what = what.removesuffix(" 1건")
    assert stop.message.startswith(
        f"HOME — 대당 Capa 계산이 멈췄습니다. 기준 정보 {name} 표의 {what}을 0보다 큰 값으로 "
        "고치고 「변경사항 적용」 뒤 새 리비전으로 저장하세요.\n\n"
    )
    assert f"{name} 표의 " in stop.message.partition("\n\n")[2]
    assert "RQ_" not in stop.message


def test_a_value_to_correct_outside_the_period_keeps_saying_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """조회기간 밖 달의 0 이하도 같은 곳에서 고친다 — 기간 말은 전문에 남는다."""
    _on_page(monkeypatch)
    error = outside_period_error(202601, 202612, _service_nonpositive("RQ_VITAL", "편중률"))

    stop = calculation_stop_notice(ValueError(error))

    assert stop is not None
    assert stop.text == "대당 Capa 계산 멈춤 — 기준 정보 「여유율」 0 이하 칸 1건을 고침"
    assert "밖의 달에 기준정보 오류가 있어" in stop.message
    assert "RQ_VITAL" not in stop.message


@pytest.mark.parametrize(
    ("error", "cell"),
    [
        (
            _service_stop(unit_capacity._VALUE_BLANK, "RQ_MODULE", "모듈수"),
            "빈 칸 1건",
        ),
        (
            _service_stop(unit_capacity._VALUE_NO_MATCH, "RQ_MODULE", "모듈수"),
            "빈 칸 1건",
        ),
        (
            _service_stop(unit_capacity._VALUE_NOT_NUMERIC, "RQ_MODULE", "모듈수"),
            "숫자 아닌 칸 1건",
        ),
        (_service_nonpositive("RQ_MODULE", "모듈수"), "0 이하 칸 1건"),
    ],
    ids=["blank", "no-match", "text", "zero"],
)
def test_a_module_count_stop_says_the_app_cannot_fix_it(
    monkeypatch: pytest.MonkeyPatch, error: str, cell: str
) -> None:
    """모듈수는 기준 정보에 표가 없어 앱에서 고칠 수 없다 — 「그 화면으로」 를 달지 않고(멈춘 화면
    그대로) 원천을 다시 등록하라고 말한다. 건수 · 예시 행은 전문에 남고 표 이름은 쓰지 않는다."""
    _on_page(monkeypatch)
    stop = calculation_stop_notice(ValueError(error))

    assert stop is not None
    assert stop.text == (
        f"대당 Capa 계산 멈춤 — 모듈수 {cell} · 앱에서 고칠 수 없음 — 원천을 다시 등록"
    )
    assert len(stop.text) <= alerts.SHORT_LIMIT
    assert stop.goto is None
    assert stop.message.startswith(
        "HOME — 대당 Capa 계산이 멈췄습니다. 모듈수는 앱에서 고칠 수 없어 새 리비전으로는 풀리지 "
        "않습니다 — 원천의 모듈수를 고쳐 다시 등록하세요.\n\n"
    )
    assert f"모듈수 표의 {cell.removesuffix(' 1건')}: 1건, 예시 " in stop.message
    assert "'공정': 'DEMO-P1'" in stop.message
    assert "RQ_MODULE" not in stop.message and "기준 정보" not in stop.message


def test_a_module_count_stop_outside_the_period_drops_the_screen_to_fix_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """조회기간 밖 달의 모듈수 멈춤 — 기간 글의 「기준 정보 페이지에서 고친 뒤 새 리비전으로
    저장」 은 첫머리의 「새 리비전으로는 풀리지 않습니다」 와 맞부딪치므로 빼고, 기간 말과 오류는
    남긴다."""
    _on_page(monkeypatch)
    error = outside_period_error(
        202601, 202612, _service_stop(unit_capacity._VALUE_BLANK, "RQ_MODULE", "모듈수")
    )

    stop = calculation_stop_notice(ValueError(error))

    assert stop is not None and stop.goto is None
    assert "밖의 달에 기준정보 오류가 있어" in stop.message
    assert "어느 달이든 고쳐야 풀립니다. 오류: 모듈수 표의 빈 칸: 1건, 예시 " in stop.message
    assert stop.message.count("새 리비전") == 1
    assert "기준 정보" not in stop.message and "생산 계획" not in stop.message


@pytest.mark.parametrize(
    "error",
    [
        _service_stop(unit_capacity._VALUE_BLANK, "RQ_MODULE", "모듈수"),
        "RQ_MODULE의 연결 키가 중복되었습니다: 1건, 예시 []",
    ],
    ids=["blank", "broken"],
)
def test_the_outside_period_message_of_a_module_count_stop_points_at_the_source(
    error: str,
) -> None:
    """조회기간 밖 모듈수 멈춤의 서비스 글도 앱에서 고칠 수 없다고 말한다 — 계산 멈춤 알림을 거치지
    않는 화면(표가 깨진 꼴 · 공정 Capa 상세 따위)은 이 글을 그대로 싣는다(2026-11-08 결정 a10)."""
    message = outside_period_error(202601, 202612, error)

    assert "밖의 달에 기준정보 오류가 있어 계산을 멈췄습니다" in message
    assert (
        "어느 달이든 고쳐야 풀립니다 — 모듈수는 앱에서 고칠 수 없어 새 리비전으로는 풀리지 "
        "않습니다 — 원천의 모듈수를 고쳐 다시 등록하세요. 오류: RQ_MODULE"
    ) in message
    assert "기준 정보" not in message and "생산 계획" not in message


def test_the_outside_period_message_of_other_tables_keeps_the_screen_to_fix_them() -> None:
    message = outside_period_error(
        202601, 202612, _service_stop(unit_capacity._VALUE_BLANK, "RQ_VITAL", "편중률")
    )

    assert (
        "오류가 가리키는 화면(수율·PKG PLAN 은 생산 계획, 그 밖은 기준 정보 페이지)에서 고친 뒤 새 "
        "리비전으로 저장하세요. 오류: RQ_VITAL"
    ) in message


@pytest.mark.parametrize(
    "error",
    [
        duckdb.IOException("Could not set lock on file: Conflicting lock is held"),
        duckdb.CatalogException("Table with name RQ_RUN_RATE does not exist"),
        OSError("읽지 못함"),
        RuntimeError("활성 리비전이 없습니다."),
        KeyError("RQ_REQB"),
        ValueError("선택 범위에 소요대수 산출 기준이 없습니다. (데이터 범위 26.01–26.12)"),
        ValueError("RQ_YLD의 수율 값이 비었습니다: 1건"),
        ValueError("RQ_CHIP_EQ.구분_EQ 값은 0보다 커야 합니다."),
        ValueError("RQ_PKG_PLAN.생산수량에 숫자가 아닌 값이 있습니다: 1행, 예시 []"),
        ValueError("RQ_VITAL의 연결 키가 중복되었습니다: 1건, 예시 []"),
        ValueError("RQ_RUN_DAY의 생산계획년월은 YYYYMM 형식이어야 합니다: 1행, 예시 []"),
        ValueError("보유 설비대수에 숫자가 아닌 값 또는 누락값이 있습니다."),
        duckdb.Error("RQ_RUN_RATE의 CAPA_RUN_RATE 값이 빈 대당 Capa 기준이 있습니다: 1건, 예시 []"),
    ],
)
def test_other_failures_have_no_screen_to_fill_and_keep_the_plain_message(
    error: BaseException,
) -> None:
    """DB 잠금 · 읽기 실패 · 자료 없는 달은 같은 `except` 로 오지만 채울 화면이 없다. 표 자체가
    깨진 꼴(연결 키 · 월 형식)과 기준 정보 편집표 밖의 표도 기준 정보로 보내지 않는다 — 부르는 쪽이
    지금 글을 그대로 쓴다."""
    assert calculation_stop_notice(error) is None


def test_month_range_falls_back_when_the_widget_state_is_missing_or_broken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`st.session_state` 전역을 교체하면 AppTest 기반 페이지 테스트를 오염시킨다.

    실제 Streamlit 런타임 없이 검증해야 하므로 모듈이 참조하는 `st` 만 바꿔치기한다.
    """

    class _FakeStreamlit:
        def __init__(self, state: dict[str, object]) -> None:
            self.session_state = state

    broken_states: tuple[dict[str, object], ...] = (
        {},
        {MONTH_RANGE_KEY: "202601"},
        {MONTH_RANGE_KEY: ("2026-01",)},
    )
    for broken in broken_states:
        monkeypatch.setattr(page_bootstrap, "st", _FakeStreamlit(broken))
        start, end = page_bootstrap.selected_month_range()
        assert start < end

    monkeypatch.setattr(
        page_bootstrap,
        "st",
        _FakeStreamlit({MONTH_RANGE_KEY: ("2026-03", "2026-08")}),
    )
    assert page_bootstrap.selected_month_range() == (202603, 202608)


def test_prune_list_selection_drops_values_the_current_options_no_longer_have(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """옵션이 계산 결과라 시나리오·조회기간이 바뀌면 옛 선택이 옵션 밖으로 나간다."""

    class _FakeStreamlit:
        def __init__(self, state: dict[str, object]) -> None:
            self.session_state = state

    state: dict[str, object] = {"filter": ["A", "Z"]}
    monkeypatch.setattr(page_bootstrap, "st", _FakeStreamlit(state))
    assert page_bootstrap.prune_list_selection("filter", ["A", "B"]) == ["A"]
    assert state["filter"] == ["A"]

    # 아직 아무것도 고르지 않은 세션에는 기본값을 심는다.
    state.clear()
    assert page_bootstrap.prune_list_selection("filter", ["A", "B"], default=["B"]) == ["B"]
    assert state["filter"] == ["B"]

    # 값이 리스트가 아니면(앞 리비전이 남긴 찌꺼기) 기본값으로 되돌린다.
    state["filter"] = "A"
    assert page_bootstrap.prune_list_selection("filter", ["A", "B"]) == []
    assert state["filter"] == []
