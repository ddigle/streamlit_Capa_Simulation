# Purpose: 산출 결과 「시트 엑셀」 이 CSV 곁에서 지금 화면 상태 그대로의 표를 내는지 본다.

"""산출 결과 「시트 엑셀」(TODO 2장 「계산 결과 Excel 다운로드」 첫 넓히기 — 공정 Capa 상세 선례).

- 대당 Capa · 소요대수 표 제목 줄에 CSV 와 「내려받기 ▾」 메뉴 하나로 선다(2026-11-10 답 Q2-7 —
  공정 Capa 상세와 같은 도우미). 파일 이름은 CSV 와 같고 확장자만 `.xlsx`.
- 내용은 지금 화면 상태 — 보기 · 집계 수준 · 공용 공정 거름 · 상세 · 조회기간 달 · 공정 표시명(CSV
  는 원본 이름 그대로). 맨 위에 시나리오 · 조회기간 · 보기 · 거름 머리 값 줄.
- 통은 조건이 바뀐 뒤 처음 그리는 회차에 한 번 짓고 세션에 몇 벌 기억한다 — 같은 조건 회차 · 닫힌
  탭은 짓지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_process_field import share
from test_reference_data_page import (
    REQUIRED_TAB,
    SECUREMENT_TAB,
    STEP_VIEW,
    TWO_PROCESS_RESULT_SCRIPT,
    _open_calc_tab,
    _renamed,
)
from xlsx_read import ReadSheet, read_workbook

import capa_simulation.components.monthly_table_workbook as monthly_table_workbook
from capa_simulation.components.sheet_download import SHEET_MEMO_LIMIT
from capa_simulation.components.table_toolbar import (
    DOWNLOAD_MENU_LABEL,
    SHEET_XLSX_LABEL,
    download_menu_key,
)

UNIT_CSV = "download_unit_capacity_csv"
UNIT_XLSX = "download_unit_capacity_xlsx"
SUMMARY_CSV = "download_required_equipment_summary_csv"
SUMMARY_XLSX = "download_required_equipment_summary_xlsx"
DETAIL_CSV = "download_required_equipment_detail_csv"
DETAIL_XLSX = "download_required_equipment_detail_xlsx"
MEMO_KEY = "calculation_result_sheet_memo"
# 표시명을 입힌 픽스처는 캐시 키 토큰을 따로 둔다(계산 결과는 같아도 다른 회차 몫).
RENAMED_SCRIPT = _renamed(TWO_PROCESS_RESULT_SCRIPT)
# 둘째 공정의 MCP 를 「2A」 로 — 소요대수 상세 `표 조건` 카드의 MCP 칸에 값이 둘이라 하나를 고르면
# 본문이 실제로 준다. 계산 캐시는 프로세스 전역이라 토큰도 따로 둔다.
_SECOND_PROCESS_ROW = '        second_row["공정"] = "Process-B"\n'
TWO_MCP_SCRIPT = TWO_PROCESS_RESULT_SCRIPT.replace(
    _SECOND_PROCESS_ROW,
    _SECOND_PROCESS_ROW + '        if "MCP_SEQ" in second_row:\n'
    '            second_row["MCP_SEQ"] = "2A"\n',
).replace('"test-capacity-two-process-page"', '"test-capacity-two-mcp-page"')
assert '"MCP_SEQ"] = "2A"' in TWO_MCP_SCRIPT and '"test-capacity-two-mcp-page"' in TWO_MCP_SCRIPT
# 상세에만 있는 카드 칸 · 요약에도 있는 카드 칸 — key 는 `column_filter_key` 꼴
# (`required_equipment_filter_<열>`).
DETAIL_ONLY_FILTER = "required_equipment_filter_MCP_SEQ"
SUMMARY_FILTER = "required_equipment_filter_Area_Name"
FILTER_RESET = "required_equipment_filter_reset"
# 카드 거름이 없을 때 소요대수 시트의 머리 값 줄(공용 공정 칸은 늘 한 줄).
REQUIRED_HEADING = ["시나리오", "조회기간", "상세", "공정"]


def _app(script: str = TWO_PROCESS_RESULT_SCRIPT) -> AppTest:
    app = AppTest.from_string(script, default_timeout=60).run()
    assert not app.exception
    return app


def _captured(app: AppTest, key: str) -> dict[str, Any]:
    downloads = app.session_state["captured_downloads"]
    assert key in downloads, sorted(downloads)
    return dict(downloads[key])


def _keys(app: AppTest) -> list[str]:
    return [str(button.key) for button in app.download_button]


def _menu_keys(app: AppTest, csv_key: str) -> list[str]:
    """그 CSV 의 「내려받기 ▾」 메뉴 안 단추 key 차례(2026-11-10 답 Q2-7)."""
    (menu,) = [block for block in app.get("popover") if block.key == download_menu_key(csv_key)]
    assert menu.proto.popover.label == DOWNLOAD_MENU_LABEL
    return [str(button.key) for button in menu.download_button]


def _sheet(app: AppTest, key: str, name: str) -> ReadSheet:
    return read_workbook(bytes(_captured(app, key)["data"]))[name]


def _heading(sheet: ReadSheet) -> dict[str, str]:
    rows: dict[str, str] = {}
    index = 1
    while sheet.row(index):
        name, value = sheet.row(index)[:2]
        rows[str(name)] = str(value)
        index += 1
    return rows


def _body(sheet: ReadSheet) -> pd.DataFrame:
    """머리 값 줄 · 빈 줄 다음 표 머리부터 — 칸 값 그대로."""
    header = 1 + len(_heading(sheet)) + 1
    names = [str(value) for value in sheet.row(header)]
    rows = []
    row = header + 1
    while (row, 0) in sheet.cells:
        rows.append([sheet.cells[(row, column)].value for column in range(len(names))])
        row += 1
    return pd.DataFrame(rows, columns=names)


def _csv(app: AppTest, key: str) -> pd.DataFrame:
    return pd.read_csv(BytesIO(bytes(_captured(app, key)["data"])), encoding="utf-8-sig")


def _same_values(sheet: pd.DataFrame, csv: pd.DataFrame) -> None:
    """시트 칸 = CSV 칸(분류 글 · 화면 자릿수의 값, 빈 칸은 None/NaN) — 같은 표다."""
    assert list(sheet.columns) == list(csv.columns)
    assert len(sheet) == len(csv)
    for column in csv.columns:
        for ours, theirs in zip(sheet[column], csv[column], strict=True):
            if ours is None:
                assert pd.isna(theirs) or theirs == "", (column, ours, theirs)
            else:
                assert ours == theirs, (column, ours, theirs)


def test_the_unit_capacity_sheet_stands_beside_the_csv_with_the_same_table() -> None:
    app = _app()

    keys = _keys(app)
    assert keys.index(UNIT_XLSX) == keys.index(UNIT_CSV) + 1
    assert _menu_keys(app, UNIT_CSV) == [UNIT_CSV, UNIT_XLSX]
    xlsx = next(button for button in app.download_button if button.key == UNIT_XLSX)
    assert xlsx.label == SHEET_XLSX_LABEL
    csv = _captured(app, UNIT_CSV)
    assert _captured(app, UNIT_XLSX)["file_name"] == csv["file_name"].replace(".csv", ".xlsx")

    sheet = _sheet(app, UNIT_XLSX, "대당 Capa")
    assert sheet.row(0) == ["공정별 대당 Capa"]
    heading = _heading(sheet)
    assert list(heading) == ["시나리오", "조회기간", "표시 방식", "집계 수준", "공정"]
    assert heading["조회기간"].startswith("26.08")
    assert (heading["표시 방식"], heading["집계 수준"], heading["공정"]) == (
        "공정별",
        "공정",
        "전체",
    )
    _same_values(_body(sheet), _csv(app, UNIT_CSV))


def test_the_sheet_uses_the_screen_process_names_while_the_csv_keeps_the_source() -> None:
    """시트는 화면 그대로(공정 표시명), 곁 CSV 는 오늘처럼 원본 이름이다."""
    app = _app(RENAMED_SCRIPT)

    sheet = _body(_sheet(app, UNIT_XLSX, "대당 Capa"))
    csv = _csv(app, UNIT_CSV)
    assert "가공" in set(sheet["공정"]) and "Process-A" not in set(sheet["공정"])
    assert "Process-A" in set(csv["공정"])


def test_a_narrowed_process_filter_narrows_the_sheet_and_keeps_the_file_name() -> None:
    app = _app()
    before = _captured(app, UNIT_XLSX)["file_name"]

    share(app, ["Process-B"])
    app.run()
    assert not app.exception
    sheet = _sheet(app, UNIT_XLSX, "대당 Capa")
    assert set(_body(sheet)["공정"].dropna()) == {"Process-B"}
    assert _heading(sheet)["공정"] == "Process-B"
    assert _captured(app, UNIT_XLSX)["file_name"] == before
    _same_values(_body(sheet), _csv(app, UNIT_CSV))


def test_the_step_view_sheet_follows_the_view_and_waits_for_a_process() -> None:
    app = AppTest.from_string(TWO_PROCESS_RESULT_SCRIPT, default_timeout=60)
    app.session_state["unit_capacity_view_mode"] = STEP_VIEW
    app.run()
    assert not app.exception
    # 공정을 고르기 전에는 표가 없어 CSV · 시트 엑셀 둘 다 서지 않는다.
    assert UNIT_XLSX not in _keys(app) and UNIT_CSV not in _keys(app)

    share(app, ["Process-A"])
    app.run()
    assert not app.exception
    sheet = _sheet(app, UNIT_XLSX, "대당 Capa")
    assert sheet.row(0) == ["STEP별 대당 Capa"]
    heading = _heading(sheet)
    assert heading["표시 방식"] == "STEP별" and "집계 수준" not in heading
    _same_values(_body(sheet), _csv(app, UNIT_CSV))


def test_the_required_sheet_follows_the_detail_toggle_and_the_filter() -> None:
    app = _open_calc_tab(_app(), REQUIRED_TAB)

    keys = _keys(app)
    assert keys.index(SUMMARY_XLSX) == keys.index(SUMMARY_CSV) + 1
    assert _menu_keys(app, SUMMARY_CSV) == [SUMMARY_CSV, SUMMARY_XLSX]
    assert _captured(app, SUMMARY_XLSX)["file_name"] == _captured(app, SUMMARY_CSV)[
        "file_name"
    ].replace(".csv", ".xlsx")
    sheet = _sheet(app, SUMMARY_XLSX, "소요대수")
    assert sheet.row(0) == ["소요대수"]
    heading = _heading(sheet)
    assert (heading["상세"], heading["공정"]) == ("끔", "전체")
    _same_values(_body(sheet), _csv(app, SUMMARY_CSV))

    share(app, ["Process-B"])
    app.run()
    assert not app.exception
    sheet = _sheet(app, SUMMARY_XLSX, "소요대수")
    assert set(_body(sheet)["공정"].dropna()) == {"Process-B"}
    assert _heading(sheet)["공정"] == "Process-B"

    app.session_state["required_equipment_detail"] = True
    app.run()
    assert not app.exception
    assert DETAIL_XLSX in _keys(app) and SUMMARY_XLSX not in _keys(app)
    assert _menu_keys(app, DETAIL_CSV) == [DETAIL_CSV, DETAIL_XLSX]
    sheet = _sheet(app, DETAIL_XLSX, "소요대수")
    assert _heading(sheet)["상세"] == "켬"
    _same_values(_body(sheet), _csv(app, DETAIL_CSV))


def test_the_required_sheet_heading_lists_each_card_filter_on_screen() -> None:
    """소요대수 `표 조건` 카드에서 값을 고른 칸마다 시트 머리 값에 (카드에 보이는 칸 글자,
    고른 값) 한 줄이 선다 — 본문은 그 거름의 CSV 와 같다. 상세를 끄면 상세에만 있는 칸의 줄은
    빠지고(선택은 세션에 남아도 요약 표에는 걸리지 않는다), 「필터 초기화」 뒤에는 카드 줄이
    없다."""
    app = _open_calc_tab(_app(TWO_MCP_SCRIPT), REQUIRED_TAB)
    app.session_state["required_equipment_detail"] = True
    app.run()
    assert not app.exception
    mcp = app.multiselect(key=DETAIL_ONLY_FILTER)
    assert mcp.options == ["1A", "2A"]
    mcp_label = str(mcp.label)
    assert list(_heading(_sheet(app, DETAIL_XLSX, "소요대수"))) == REQUIRED_HEADING

    mcp.set_value(["1A"]).run()
    assert not app.exception
    sheet = _sheet(app, DETAIL_XLSX, "소요대수")
    heading = _heading(sheet)
    assert list(heading) == [*REQUIRED_HEADING, mcp_label]
    assert (heading["상세"], heading["공정"], heading[mcp_label]) == ("켬", "전체", "1A")
    body = _body(sheet)
    assert set(body["공정"].dropna()) == {"Process-A"}
    _same_values(body, _csv(app, DETAIL_CSV))

    app.multiselect(key=DETAIL_ONLY_FILTER).set_value(["1A", "2A"]).run()
    assert not app.exception
    assert _heading(_sheet(app, DETAIL_XLSX, "소요대수"))[mcp_label] == "1A · 2A"

    app.session_state["required_equipment_detail"] = False
    app.run()
    assert not app.exception
    assert DETAIL_ONLY_FILTER not in [str(box.key) for box in app.multiselect]
    sheet = _sheet(app, SUMMARY_XLSX, "소요대수")
    assert list(_heading(sheet)) == REQUIRED_HEADING
    _same_values(_body(sheet), _csv(app, SUMMARY_CSV))

    area = app.multiselect(key=SUMMARY_FILTER)
    area_label = str(area.label)
    area.set_value(["Main"]).run()
    assert not app.exception
    heading = _heading(_sheet(app, SUMMARY_XLSX, "소요대수"))
    assert list(heading) == [*REQUIRED_HEADING, area_label]
    assert heading[area_label] == "Main"

    app.button(key=FILTER_RESET).click().run()
    assert not app.exception
    assert list(_heading(_sheet(app, SUMMARY_XLSX, "소요대수"))) == REQUIRED_HEADING


def _count_builds(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """시트 통을 지은 차례(시트 이름)를 적는다 — 짓는 것은 그대로 한다. 페이지는 exec 때 이름을
    집는다."""
    built: list[str] = []
    original: Callable[..., bytes] = monthly_table_workbook.monthly_table_workbook

    def counting(request: Any) -> bytes:
        built.append(str(request.sheet_name))
        return original(request)

    monkeypatch.setattr(monthly_table_workbook, "monthly_table_workbook", counting)
    return built


def test_the_sheet_is_built_once_per_condition_and_not_in_a_closed_tab(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """통은 조건이 바뀐 회차에 한 번 짓고 세션에 기억한다 — 같은 조건으로 돌아오면 다시 짓지 않고,
    닫힌 탭의 통은 짓지 않는다(공정 Capa 상세 선례 — 새 `st.cache_*` 없음)."""
    built = _count_builds(monkeypatch)
    app = _app()
    assert built == ["대당 Capa"]

    app.run()
    assert built == ["대당 Capa"]

    app.selectbox(key="unit_capacity_detail_level").set_value("제품").run()
    assert not app.exception
    assert built == ["대당 Capa", "대당 Capa"]
    assert _heading(_sheet(app, UNIT_XLSX, "대당 Capa"))["집계 수준"] == "제품"

    app.selectbox(key="unit_capacity_detail_level").set_value("공정").run()
    assert built == ["대당 Capa", "대당 Capa"]

    _open_calc_tab(app, SECUREMENT_TAB)
    assert built == ["대당 Capa", "대당 Capa"]
    _open_calc_tab(app, REQUIRED_TAB)
    assert built == ["대당 Capa", "대당 Capa", "소요대수"]
    assert len(app.session_state[MEMO_KEY]) <= SHEET_MEMO_LIMIT
