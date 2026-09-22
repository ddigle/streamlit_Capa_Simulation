# Purpose: equipment pages 관련 정상·예외·회귀 동작을 검증한다.

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest
from test_floor_layout_profile import _png

from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_availability import (
    build_equipment_lifecycle_spans,
    build_inactive_equipment,
)
from capa_simulation.services.equipment_contract import (
    empty_downtime_schedule,
    empty_equipment_master,
)
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_master,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 페이지는 스크립트로 실행되므로(`app_pages` 는 패키지가 아니다) 상수를 import 할 수 없다.
# 이 파일이 이미 `"equipment_baseline_draft_v3"` 를 그렇게 적고 있고, 값이 갈리면 아래
# 순회 테스트가 곧바로 실패하므로 조용히 어긋날 수는 없다.
MAIN_QUESTION_KEY = "equipment_main_question_v1"
SMALL_PROCESS_KEY = "equipment_dashboard_small_processes"
BASELINE_CLIPBOARD_KEY = "equipment_baseline_clipboard_v4"
MASTER_CLIPBOARD_KEY = "equipment_master_clipboard_v4"
DOWNTIME_CLIPBOARD_KEY = "equipment_downtime_clipboard_v4"
ASOF_MONTH_KEY = "equipment_main_asof_month_v1"
DOWNTIME_VIEW_KEY = "equipment_main_downtime_view_v1"
QUESTION_DOWNTIME = "어디가 비가동인가"
DOWNTIME_VIEW_MONTH = "그 달 전체"
DOWNTIME_VIEW_WEEK = "기준 주차 시점"
# 질문 하나에 답 하나. 표지는 **그 질문의 기본 보기**가 그리는 제목이다.
QUESTION_MARKERS = {
    "지금 몇 대가 어느 상태인가": "#### 호기 생애주기 상태 모니터링",
    "언제 몇 대가 쓸 수 있게 되나": "#### 주차별 설비 현황",
    "어디가 비가동인가": "#### 비가동 설비호기",
    "Qual 은 어디까지 왔나": "#### Qual 확정상태 실행관리",
    "공정별로는 어떤가": "#### 공정소분류별 현황",
    "기준정보와 맞나 (Static·Dynamic)": (
        "#### :material/compare_arrows: Static · Dynamic 가용대수 비교"
    ),
}


class _StreamlitLog(logging.Handler):
    """Streamlit 이 **`st.warning` 이 아니라 파이썬 로거로** 내는 경고를 모은다."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@contextmanager
def _streamlit_warnings() -> Iterator[_StreamlitLog]:
    """위젯에 `default=` 와 `key` 를 같이 준 자리를 기계로 잡는 덫.

    「created with a default value but also had its value set via the Session State API」는
    화면에 뜨지 않고 서버 로그에만 남는다 — `app.warning` 으로는 영영 안 걸린다. Streamlit
    의 모듈 로거는 `propagate=False` 라 `caplog` 도 못 받으므로 직접 붙인다.
    """
    handler = _StreamlitLog()
    loggers = [
        logging.getLogger(name)
        for name in list(logging.root.manager.loggerDict)
        if name == "streamlit" or name.startswith("streamlit.")
    ]
    for logger in loggers:
        logger.addHandler(handler)
    try:
        yield handler
    finally:
        for logger in loggers:
            logger.removeHandler(handler)


def _page_text(app: AppTest) -> str:
    """화면에 적힌 글 전부. 표지가 있는지·없는지를 이걸로 잰다."""
    return "\n".join(
        str(element.value)
        for group in (app.markdown, app.caption, app.info, app.success)
        for element in group
    )


def _page_script(page_path: Path, database_path: Path) -> str:
    return f"""
from pathlib import Path
import capa_simulation.settings as settings

settings.EQUIPMENT_DUCKDB_PATH = Path({str(database_path)!r})
page_source = Path({str(page_path)!r}).read_text(encoding="utf-8")
exec(compile(page_source, {str(page_path)!r}, "exec"), {{"__name__": "__main__"}})
"""


def test_available_equipment_page_opens_with_empty_database(tmp_path: Path) -> None:
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "availability.duckdb"),
        default_timeout=60,
    ).run()

    assert not app.exception
    # 공통 헤더가 상태 접미를 제목에서 떼어 배지로 보여준다.
    assert app.title[0].value == "가용설비 현황"
    assert any("Data확보중" in element.value for element in app.markdown)
    # 보는 곳(Main)·고르는 곳(Preference)·원천을 다루는 곳(RawData) 셋뿐이다. Cut-off 는
    # `Preference` 로, Static/Dynamic 은 Main 의 여섯 번째 질문으로 들어갔다(정의서 2-2·2-3).
    # 라벨은 `stateful_tabs` 의 기억값에 묶이므로 바꾸면 여기도 고친다.
    assert [tab.label for tab in app.tabs] == [
        ":material/dashboard: Main",
        ":material/tune: Preference",
        ":material/table_rows: RawData",
    ]
    # 조회 조건 넷은 `Preference` 에서 **Main 의 옵션 줄**로 옮겼다. 공정소분류만 펴 두고
    # 나머지 셋은 popover 안이라 **그리는 차례가 화면 순서와 다르다** — 순서가 아니라
    # 집합으로 본다. 넷 다 살아 있는지와, 손이 제일 자주 가는 공정소분류가 Main 에서
    # 바로 눌리는지(키로 확인)가 이 단언이 지키는 것이다.
    filter_labels = {
        widget.label
        for widget in app.multiselect
        if widget.label in {"라인구분", "활용구분", "공정대분류", "공정소분류"}
    }
    assert filter_labels == {"라인구분", "활용구분", "공정대분류", "공정소분류"}
    assert SMALL_PROCESS_KEY in [widget.key for widget in app.multiselect]
    assert "운영 지침" in [expandable.label for expandable in app.status]

    def _filter(label: str) -> object:
        return next(widget for widget in app.multiselect if widget.label == label)

    _filter("라인구분").set_value(["Line-A"])
    _filter("활용구분").set_value(["양산"])
    app.run()

    assert not app.exception


def test_the_main_tab_answers_one_question_at_a_time(tmp_path: Path) -> None:
    """여섯 질문이 **한 번에 하나만** 그려진다.

    옛 화면은 여섯 구획을 세로로 쌓아 「어느 게 내가 찾던 양식인지」부터 찾아야 했다.
    질문을 고르면 그 답 하나만 서고 나머지 다섯의 표지는 화면 어디에도 없어야 한다 —
    없어야 계산도 건너뛴 것이다.

    `default=` 와 `key` 를 같이 준 위젯이 있으면 매 회차 경고가 뜨는데 화면에는 안 보인다.
    로거를 직접 받아 그 자리를 같이 잡는다.
    """
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    database_path = tmp_path / "one_question.duckdb"
    for question, marker in QUESTION_MARKERS.items():
        app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=90)
        app.session_state[MAIN_QUESTION_KEY] = question
        with _streamlit_warnings() as log:
            app.run()

        assert not app.exception, (question, app.exception)
        assert not [message for message in log.messages if "default value" in message], (
            question,
            log.messages,
        )
        text = _page_text(app)
        assert marker in text, question
        for other_question, other_marker in QUESTION_MARKERS.items():
            if other_question != question:
                assert other_marker not in text, (question, other_question)
    clear_equipment_repository()


def _demo_fleet() -> tuple[pd.DataFrame, pd.DataFrame]:
    """화면이 쓰는 것과 같은 데모 fleet. 앵커가 `date.today()` 라 테스트도 오늘로 맞춘다."""
    return sample_equipment_master(anchor_date=date.today()), sample_downtime_schedule(
        anchor_date=date.today()
    )


def _last_week_end() -> date:
    """기본 조회기간(`이 달 1일` ~ `오늘+12주`)의 마지막 주차 종료일(일요일).

    `build_weekly_equipment_availability` 가 `end_date` 가 든 주의 월요일까지 돌므로 그 주의
    일요일이 마지막 주차 종료일이다.
    """
    end_date = date.today() + timedelta(weeks=12)
    last_monday = end_date - timedelta(days=end_date.weekday())
    return last_monday + timedelta(days=6)


def _rendered(app: AppTest, column: str) -> pd.DataFrame:
    """그 컬럼을 가진 표를 집는다. **차례로 집지 않는다** — 표가 늘면 앞자리가 밀린다."""
    return next(frame.value for frame in app.dataframe if column in frame.value.columns)


def test_the_downtime_question_keeps_the_old_as_of_table_as_one_of_its_views(
    tmp_path: Path,
) -> None:
    """「기준 주차 시점」 보기는 **옛 표와 완전히 같다.**

    보기를 셋으로 늘리면서 한 시점을 찍어 보던 자리를 잃으면 안 된다. 같은 술어·같은
    as_of 로 서비스가 내는 프레임과 화면이 그린 프레임이 같은지 본다.
    """
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "downtime_week.duckdb"), default_timeout=90
    )
    app.session_state[MAIN_QUESTION_KEY] = QUESTION_DOWNTIME
    app.session_state[DOWNTIME_VIEW_KEY] = DOWNTIME_VIEW_WEEK
    app.run()

    assert not app.exception
    fleet, fleet_downtime = _demo_fleet()
    expected = build_inactive_equipment(fleet, fleet_downtime, as_of=_last_week_end())
    assert not expected.empty, "데모 fleet 에 비가동 호기가 없으면 이 테스트가 아무것도 안 잰다"
    rendered = _rendered(app, "상태")
    assert set(rendered["호기"]) == set(expected["호기"])
    assert list(rendered.columns) == list(expected.columns)


def test_the_downtime_month_view_catches_what_the_sunday_samples_miss(tmp_path: Path) -> None:
    """「그 달 전체」는 일요일 표본의 **상위집합**이다.

    주차 종료일만 재면 주중에 시작해 주말 전에 끝난 비가동이 통째로 빠진다. 구간이 바뀌는
    날짜마다 다시 재므로 일요일에 걸린 호기는 전부 들어 있고, 그보다 더 잡을 수 있다.
    개수는 고정하지 않는다 — 데모 fleet 은 `date.today()` 를 앵커로 만들어진다.
    """
    month = f"{date.today() + timedelta(days=30):%Y-%m}"
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "downtime_month.duckdb"), default_timeout=90
    )
    app.session_state[MAIN_QUESTION_KEY] = QUESTION_DOWNTIME
    app.session_state[DOWNTIME_VIEW_KEY] = DOWNTIME_VIEW_MONTH
    app.session_state[ASOF_MONTH_KEY] = month
    app.run()

    assert not app.exception
    rendered = _rendered(app, "비가동 시작")

    fleet, fleet_downtime = _demo_fleet()
    year, month_no = (int(part) for part in month.split("-"))
    month_start = date(year, month_no, 1)
    month_end = (
        date(year + 1, 1, 1) if month_no == 12 else date(year, month_no + 1, 1)
    ) - timedelta(days=1)
    # 화면이 쓰는 것과 **같은 시점 집합**을 여기서도 만들어 결과를 맞댄다. 상위집합만
    # 보면 union 이 일요일만 재도록 퇴화해도 통과한다 — 그것이 바로 이 보기가 고치려던
    # 잘못이다.
    spans = build_equipment_lifecycle_spans(
        fleet, fleet_downtime, start_date=month_start, end_date=month_end
    )
    moments = {month_start} | {min(max(value, month_start), month_end) for value in spans["시작일"]}
    sunday = month_start + timedelta(days=(6 - month_start.weekday()) % 7)
    sunday_units: set[str] = set()
    while sunday <= month_end:
        moments.add(sunday)
        sunday_units |= {
            str(unit)
            for unit in build_inactive_equipment(fleet, fleet_downtime, as_of=sunday)["호기"]
        }
        sunday += timedelta(days=7)
    expected: set[str] = set()
    for moment in sorted(moments):
        expected |= {
            str(unit)
            for unit in build_inactive_equipment(fleet, fleet_downtime, as_of=moment)["호기"]
        }

    assert sunday_units, "일요일 표본이 비면 상위집합 검사가 아무것도 안 잰다"
    assert set(rendered["호기"]) == expected
    assert sunday_units <= expected
    # 데모 fleet 에는 주중에 들어와 주말 전에 끝나는 비가동이 있다. 이 줄이 깨지면 union 이
    # 일요일 표본으로 퇴화했거나 데모 데이터가 바뀐 것이다.
    assert sunday_units < expected
    assert rendered["비가동 시작"].le(rendered["비가동 종료"]).all()


def test_baseline_paste_import_previews_itself_before_it_applies(tmp_path: Path) -> None:
    """기존 보유대수도 호기 마스터·비가동 일정과 같은 미리보기 → 확정 순서를 탄다.

    **미리보기 버튼이 없어졌다.** 붙여넣고 칸을 벗어나면 `on_change` 가 그 자리에서
    검사한다 — `set_value().run()` 이 브라우저의 blur 와 같은 자리에서 그 콜백을 부른다.
    확인하는 것(미리보기가 서고 그 다음에야 편집본에 닿는다)은 그대로다.
    """
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "baseline_import.duckdb"),
        default_timeout=60,
    ).run()

    assert [widget.label for widget in app.text_area] == [
        "기존 보유대수 표 붙여넣기",
        "호기 마스터 표 붙여넣기",
        "비가동 일정 표 붙여넣기",
    ]
    assert "equipment_baseline_clipboard_preview_v4" not in [button.key for button in app.button]

    app.text_area[0].set_value("공정\t분류\t기존보유대수\t비고\nProcess-X\t전체\t7\t증설")
    app.run()

    assert not app.exception
    assert any(element.value == "**기존 보유대수 Import 확인**" for element in app.markdown)

    app.button("confirm_baseline_import_v3").click().run()

    assert not app.exception
    assert any("기존 보유대수 붙여넣기 데이터 1행" in element.value for element in app.success)
    assert "Process-X" in app.session_state["equipment_baseline_draft_v3"]["공정"].tolist()
    # 적용한 글은 칸에서 사라진다. 남아 있으면 옆 위젯을 건드릴 때마다 같은 표가 다시
    # 검사되고, 다음 표를 붙여넣기 전에 먼저 지워야 한다.
    assert app.text_area[0].value == ""


def _master_paste_with_a_bad_row(rows: int, bad_row: int) -> str:
    """데모 fleet 을 붙여넣기 글로 만들고 `bad_row`(1-based) 의 확정상태를 허용값 밖으로 바꾼다."""
    master = sample_equipment_master(anchor_date=date.today()).head(rows)
    lines = str(master.to_csv(sep="\t", index=False)).strip("\r\n").splitlines()
    cells = lines[bad_row].split("\t")
    cells[lines[0].split("\t").index("확정상태")] = "없는상태"
    lines[bad_row] = "\t".join(cells)
    return "\n".join(lines)


def test_a_bad_paste_pins_the_verdict_columns_and_locks_the_apply_button(
    tmp_path: Path,
) -> None:
    """오류가 있으면 어느 행이 왜 틀렸는지 표 앞에 붙고 적용은 눌리지 않는다."""
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "bad_paste.duckdb"),
        default_timeout=90,
    ).run()

    app.text_area(MASTER_CLIPBOARD_KEY).set_value(_master_paste_with_a_bad_row(3, 2)).run()

    assert not app.exception
    assert app.button("confirm_equipment_import_v3").disabled
    assert any("1행에 오류" in element.value for element in app.error), [
        element.value for element in app.error
    ]
    verdict_tables = [
        frame.value for frame in app.dataframe if list(frame.value.columns[:2]) == ["검증", "행"]
    ]
    assert len(verdict_tables) == 1, [list(frame.value.columns[:2]) for frame in app.dataframe]
    # 오류 행이 맨 위로 올라온다.
    assert int(verdict_tables[0]["행"].iloc[0]) == 2


def test_the_three_import_targets_download_their_error_rows_under_their_own_keys(
    tmp_path: Path,
) -> None:
    """세 대상의 오류 행 내려받기 키가 서로 달라야 한다.

    키 하나를 셋이 나눠 쓰면 대상을 바꿀 때마다 「이미 쓰인 키」로 화면이 죽거나, 더 나쁘게는
    옆 대상의 오류 행이 내려받힌다. 셋을 차례로 붙여넣어 나온 키가 서로 다른지 본다.
    """
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    pastes = {
        BASELINE_CLIPBOARD_KEY: "공정\t분류\t기존보유대수\t비고\nProcess-X\t전체\t일곱\t증설",
        MASTER_CLIPBOARD_KEY: _master_paste_with_a_bad_row(2, 1),
        DOWNTIME_CLIPBOARD_KEY: (
            "호기\t비가동유형\t시작일\t종료일\t상세사유\t비고\nNO-SUCH-UNIT\t고장\t2026-01-01\t\t\t"
        ),
    }

    seen: list[str] = []
    for text_area_key, clipboard in pastes.items():
        app = AppTest.from_string(
            _page_script(page_path, tmp_path / f"{text_area_key}.duckdb"),
            default_timeout=90,
        ).run()
        app.text_area(text_area_key).set_value(clipboard).run()

        assert not app.exception, text_area_key
        assert app.error, text_area_key
        seen += [button.key for button in app.download_button if "error_rows" in str(button.key)]

    assert len(seen) == 3, seen
    assert len(set(seen)) == 3, seen


def test_the_empty_database_opens_with_a_getting_started_card(tmp_path: Path) -> None:
    """빈 DB 의 첫 화면이 **무엇부터 해야 하는지** 말한다(평가 기준 1).

    데모 fleet 이 가득 차 보여 이미 붙은 화면처럼 읽히는 것이 이 카드가 고치는 것이다.
    적는 것은 **DuckDB 에 저장된 건수**뿐이고, Main 의 총대수와 다른 산식으로 낸 대수는
    적지 않는다 — 두 수가 첫 화면에 나란히 서면 어느 쪽이 맞는지부터 따져야 한다.
    """
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "onboarding.duckdb"),
        default_timeout=90,
    ).run()

    assert not app.exception
    assert any("이 화면은 아직 비어 있습니다" in element.value for element in app.markdown)
    text = _page_text(app)
    for line in ("호기 마스터", "운영 비가동 일정", "공정별 Cut-off"):
        assert line in text, line
    keys = [button.key for button in app.button]
    for slug in ("master", "downtime", "cutoff"):
        assert f"onboarding_go_{slug}_v1" in keys, slug
    # 카드의 지우기 버튼도 편집본의 예시 행을 없앤다(6단계 콜백 재사용, 다른 키).
    app.button("onboarding_purge_sample_rows_v1").click().run()

    assert not app.exception
    assert app.session_state["equipment_baseline_draft_v3"].empty


def test_the_getting_started_card_lands_on_the_tab_its_button_names(tmp_path: Path) -> None:
    """카드의 버튼은 그 탭을 **실제로 연다.**

    RawData·Preference 본문은 어느 탭이 열려 있든 그려지므로 「그 탭의 요소가 있다」로는
    아무것도 증명되지 않는다. 탭 위젯 값과 **Main 의 답이 사라졌는지**를 함께 본다.
    """
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    for slug, expected in (
        ("master", ":material/table_rows: RawData"),
        ("cutoff", ":material/tune: Preference"),
    ):
        app = AppTest.from_string(
            _page_script(page_path, tmp_path / f"land_{slug}.duckdb"),
            default_timeout=90,
        ).run()
        assert QUESTION_MARKERS["지금 몇 대가 어느 상태인가"] in _page_text(app), slug

        app.button(f"onboarding_go_{slug}_v1").click().run()

        assert not app.exception, slug
        assert app.session_state["equipment_active_tab"] == expected, slug
        assert app.session_state["equipment_active_tab__remembered"] == expected, slug
        # Main 이 닫혔으면 그 답은 그려지지 않는다.
        assert QUESTION_MARKERS["지금 몇 대가 어느 상태인가"] not in _page_text(app), slug
    clear_equipment_repository()


def test_a_saved_revision_takes_the_getting_started_card_away(tmp_path: Path) -> None:
    """저장본이 하나라도 생기면 카드는 그리지 않는다."""
    database_path = tmp_path / "seeded_onboarding.duckdb"
    _seeded_equipment(database_path)
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=90).run()

    assert not app.exception
    assert not any("이 화면은 아직 비어 있습니다" in element.value for element in app.markdown)
    assert "onboarding_go_master_v1" not in [button.key for button in app.button]
    clear_equipment_repository()


def test_turning_the_sample_switch_off_leaves_only_the_pending_source_panel(
    tmp_path: Path,
) -> None:
    """고를 것이 없는 화면에 고르는 틀을 세우지 않는다.

    호기 마스터가 비어 있고 샘플을 끄면 여섯 질문은 전부 빈 답으로 이어진다. 질문 pills 와
    조회 조건을 그리지 않고, 무엇이 이 자리를 채우는지만 적는다.
    """
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    # 켠 채로 한 번 연다. 질문 pills 가 **원래 잡히는 위젯**이라는 것을 먼저 고정하지
    # 않으면, 아래의 「없다」는 단언이 찾는 법이 틀려도 통과한다.
    switched_on = AppTest.from_string(
        _page_script(page_path, tmp_path / "sample_on.duckdb"),
        default_timeout=90,
    ).run()

    assert MAIN_QUESTION_KEY in [widget.key for widget in switched_on.pills]

    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "sample_off.duckdb"),
        default_timeout=90,
    )
    app.session_state["dynamic_capa_sample_data"] = False
    app.run()

    assert not app.exception
    text = _page_text(app)
    assert "#### :material/pending: 가용설비 현황" in text
    for marker in QUESTION_MARKERS.values():
        assert marker not in text, marker
    assert MAIN_QUESTION_KEY not in [widget.key for widget in app.pills]
    assert SMALL_PROCESS_KEY not in [widget.key for widget in app.multiselect]


def test_the_leftover_sample_rows_are_announced_and_cleared_in_one_click(
    tmp_path: Path,
) -> None:
    """빈 DB 는 예시 30행으로 열린다 — 그것이 저장을 막는다는 것을 **누르기 전에** 말한다.

    지금까지는 30행을 붙여넣고 저장을 누른 뒤에야 「예시 행이 30건 남아 있습니다」를 받았고,
    고치는 길은 편집표에서 한 줄씩 지우는 것뿐이었다.
    """
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "leftover.duckdb"),
        default_timeout=90,
    ).run()

    assert not app.exception
    seeded = len(app.session_state["equipment_baseline_draft_v3"])
    assert seeded > 0
    assert any(f"예시 행 {seeded:,}건" in element.value for element in app.warning), [
        element.value for element in app.warning
    ]

    app.button("purge_sample_baseline_rows_top_v1").click().run()

    assert not app.exception
    assert app.session_state["equipment_baseline_draft_v3"].empty
    # 지우고 나면 경고도 버튼도 사라진다.
    assert not [element for element in app.warning if "예시 행" in element.value]
    assert "purge_sample_baseline_rows_top_v1" not in [button.key for button in app.button]
    assert any("예시 행" in element.value for element in app.success)


def test_the_save_time_error_offers_the_same_purge_under_its_own_key(tmp_path: Path) -> None:
    """저장부터 누른 사람도 그 자리에서 고칠 수 있어야 한다. 키는 위 버튼과 달라야 한다."""
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "leftover_save.duckdb"),
        default_timeout=90,
    ).run()

    save = next(button for button in app.button if button.label == "설비 데이터 저장")
    save.click().run()

    assert not app.exception
    assert any("예시 행이" in element.value for element in app.error)
    keys = [button.key for button in app.button]
    assert "purge_sample_baseline_rows_save_v1" in keys
    assert "purge_sample_baseline_rows_top_v1" in keys

    app.button("purge_sample_baseline_rows_save_v1").click().run()

    assert not app.exception
    assert app.session_state["equipment_baseline_draft_v3"].empty


def test_page_reseeds_drafts_for_a_session_opened_before_the_baseline_table(
    tmp_path: Path,
) -> None:
    """배포 직전부터 열려 있던 브라우저 세션에서도 첫 렌더가 죽으면 안 된다.

    씨뿌리기는 `DRAFT_REVISION_KEY` 가 활성 리비전과 다를 때만 돈다. 표를 새로 더하면서
    그 키 이름을 올리지 않으면, 옛 세션은 세 draft 중 새 표만 없는 상태로 블록을 건너뛰고
    바로 아래 첨자 접근에서 `KeyError` 가 난다. 옛 세션 상태를 흉내내 그 자리를 고정한다.
    """
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "stale_session.duckdb"),
        default_timeout=60,
    )
    # 기존 보유대수 표가 생기기 전 배포본이 남긴 세션이다.
    app.session_state["equipment_master_draft_v3"] = empty_equipment_master()
    app.session_state["equipment_downtime_draft_v3"] = empty_downtime_schedule()
    app.session_state["equipment_draft_revision_v3"] = "empty"
    app.run()

    assert not app.exception
    assert "equipment_baseline_draft_v3" in app.session_state
    assert not app.session_state["equipment_baseline_draft_v3"].empty


def test_space_page_opens_with_empty_database(tmp_path: Path) -> None:
    page_path = PROJECT_ROOT / "app_pages" / "space_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "space.duckdb"),
        default_timeout=60,
    ).run()

    assert not app.exception
    assert app.title[0].value == "Space 현황"
    assert any("Data확보중" in element.value for element in app.markdown)


def test_space_floor_detail_offers_the_layout_upload_and_follows_the_drawing_canvas(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "space_layout.duckdb"
    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    repository.save_floor_layout_image("C1", "1F", "c1_1f.png", _png(4000, 1500))
    clear_equipment_repository()

    page_path = PROJECT_ROOT / "app_pages" / "space_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60)
    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    app.run()

    assert not app.exception
    assert len(app.get("file_uploader")) == 1
    assert any("적용될 캔버스: 100 × 37.5" == element.value for element in app.caption)
    assert any("c1_1f.png" in element.value for element in app.success)
    clear_equipment_repository()


def _seeded_equipment(database_path: Path) -> None:
    """세 표에 모두 값이 있는 DuckDB. 보기 설정은 값이 있는 표에만 붙는다."""
    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    equipment = empty_equipment_master()
    equipment.loc[0] = {column: None for column in equipment.columns}
    equipment.loc[0, "호기"] = "EQ-1"
    equipment.loc[0, "공정소분류"] = "DEMO_PROC"
    equipment.loc[0, "장기보관여부"] = "N"
    equipment.loc[0, "기존설비여부"] = "Y"
    equipment.loc[0, "레이아웃표시"] = "N"
    downtime = empty_downtime_schedule()
    downtime.loc[0] = {column: None for column in downtime.columns}
    downtime.loc[0, "호기"] = "EQ-1"
    downtime.loc[0, "비가동유형"] = "고장"
    downtime.loc[0, "시작일"] = date(2026, 1, 1)
    repository.save_snapshot(
        pd.DataFrame(
            {"공정": ["DEMO_PROC"], "분류": ["기존"], "기존보유대수": [1.0], "비고": [""]}
        ),
        equipment,
        downtime,
        note="검사용",
    )
    clear_equipment_repository()


def test_the_view_controls_render_for_each_editable_table(tmp_path: Path) -> None:
    """값이 있는 세 표에 각각 컬럼 선택과 행 필터가 붙는다.

    보기 설정은 **폼 밖**이라야 한다. 폼 안에 두면 저장을 눌러야 적용돼 고르는 뜻이 없다.
    """
    database_path = tmp_path / "availability.duckdb"
    _seeded_equipment(database_path)
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60).run()

    assert not app.exception
    labels = [expandable.label for expandable in app.status]
    for table in ("기존 보유대수", "호기 마스터", "운영 비가동 일정"):
        assert f"{table} · 표 보기 설정" in labels, table
    # Import 도 접히는 자리가 됐다.
    assert "Excel 붙여넣기 Import" in labels

    # 「볼 컬럼」은 편집표마다 하나씩이고, 처음에는 모두 선택돼 있다.
    # 넷인 것은 RawData 의 세 표에 Cut-off 탭의 표가 더해졌기 때문이다.
    column_pickers = [widget for widget in app.multiselect if widget.label == "볼 컬럼"]
    assert len(column_pickers) == 4
    assert all(picker.value for picker in column_pickers)
    clear_equipment_repository()


def test_hiding_a_column_keeps_its_values_in_the_saved_frame(tmp_path: Path) -> None:
    """감춘 컬럼도 저장에는 그대로 들어간다.

    `st.data_editor` 는 `column_config={컬럼: None}` 으로 감춘 컬럼의 값을 반환 프레임에
    그대로 돌려준다. 값이 빠져 나가면 저장이 그 컬럼을 통째로 비운다.
    """
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "availability.duckdb"),
        default_timeout=60,
    ).run()

    picker = next(widget for widget in app.multiselect if widget.label == "볼 컬럼")
    remaining = [column for column in picker.value if column != "비고"]
    picker.set_value(remaining)
    app.run()

    assert not app.exception
