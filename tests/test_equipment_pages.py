# Purpose: equipment pages 관련 정상·예외·회귀 동작을 검증한다.

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest
from test_floor_layout_profile import _png

from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_contract import (
    empty_downtime_schedule,
    empty_equipment_master,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 페이지는 스크립트로 실행되므로(`app_pages` 는 패키지가 아니다) 상수를 import 할 수 없다.
# 이 파일이 이미 `"equipment_baseline_draft_v3"` 를 그렇게 적고 있고, 값이 갈리면 아래
# 순회 테스트가 곧바로 실패하므로 조용히 어긋날 수는 없다.
MAIN_QUESTION_KEY = "equipment_main_question_v1"
SMALL_PROCESS_KEY = "equipment_dashboard_small_processes"
# 질문 하나에 답 하나. 표지는 **그 질문의 기본 보기**가 그리는 제목이다.
QUESTION_MARKERS = {
    "지금 몇 대가 어느 상태인가": "#### 호기 생애주기 상태 모니터링",
    "언제 몇 대가 쓸 수 있게 되나": "#### 주차별 설비 현황",
    "어디가 비가동인가": "#### 비가동 설비호기",
    "Qual 은 어디까지 왔나": "#### Qual 확정상태 실행관리",
    "공정별로는 어떤가": "#### 공정소분류별 현황",
    "기준정보와 맞나 (Static·Dynamic)": "#### 기준정보와 맞나",
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
    # 보는 곳(Main)·고르는 곳(Preference)·원천을 다루는 곳(RawData)을 가르고, 기준정보와
    # 맞대어 보는 곳만 따로 둔다. **Cut-off 탭은 `Preference` 안으로 들어갔다** — 한 번
    # 적고 마는 기준값이라 탭 하나를 상시 차지할 자리가 아니었다(정의서 2-2).
    # 라벨은 `stateful_tabs` 의 기억값에 묶이므로 바꾸면 여기도 고친다.
    assert [tab.label for tab in app.tabs] == [
        ":material/dashboard: Main",
        ":material/compare_arrows: Static/Dynamic",
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


def test_baseline_paste_import_needs_a_preview_before_it_applies(tmp_path: Path) -> None:
    """기존 보유대수도 호기 마스터·비가동 일정과 같은 미리보기 → 확정 순서를 탄다."""
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

    app.text_area[0].set_value("공정\t분류\t기존보유대수\t비고\nProcess-X\t전체\t7\t증설")
    app.run()
    app.button("equipment_baseline_clipboard_preview_v4").click().run()

    assert not app.exception
    assert any(element.value == "**기존 보유대수 Import 확인**" for element in app.markdown)

    app.button("confirm_baseline_import_v3").click().run()

    assert not app.exception
    assert any("기존 보유대수 붙여넣기 데이터 1행" in element.value for element in app.success)
    assert "Process-X" in app.session_state["equipment_baseline_draft_v3"]["공정"].tolist()


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
