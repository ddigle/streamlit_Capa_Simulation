# Purpose: Static Capa 의 판정 기준 카드·Guide·미포함 수요 알림·빈 결과 줄·표 칸 설정을 고정한다.

"""Static Capa — 판정 기준은 HOME 설정 → 판정 기준(2026-10-06), 설명은 Guide(2026-09-29 결정).

판정 기준 카드는 지금 기준 값 한 줄뿐이다 — 정하는 자리를 가리키던 글은 걷었고 바로 가기도 두지
않는다(2026-11-04 설계 규칙 UI-TXT-03 · AMB-06 (나)). 결과 상자가 비면 「…이 없습니다」 평문 한 줄이
값으로 선다(AMB-02 (가) — 초록 성공 상자를 쓰지 않는다).
"""

from __future__ import annotations

import ast
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from alert_marks import alert_notes, note_table, table_frame
from streamlit.testing.v1 import AppTest
from test_load_conversion_plan_apply import _isolated_custom_renderers  # noqa: F401
from test_reference_data_page import TEST_SCRIPT

from capa_simulation import alerts
from capa_simulation.components.page_guide import GUIDE_TRIGGER_KEY, load_guide
from capa_simulation.sidebar_status import CONDITION_CARD_PREFIX

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "app_pages" / "static_capa.py"
CARD_KEY = f"{CONDITION_CARD_PREFIX}static_capa"


def _script(database_path: Path) -> str:
    return f"""
from pathlib import Path

import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
apply_pending_scenario_preset()

exec(
    compile(Path({str(PAGE)!r}).read_text(encoding="utf-8"), {str(PAGE)!r}, "exec"),
    {{"__name__": "__main__"}},
)
"""


@pytest.fixture(scope="module")
def app_script(tmp_path_factory: pytest.TempPathFactory) -> str:
    return _script(tmp_path_factory.mktemp("static_capa_layout") / "scenario.duckdb")


def test_the_threshold_card_only_shows_the_threshold_in_use(app_script: str) -> None:
    """판정 기준 입력은 없앴다(2026-10-06 사용자 결정). 카드는 지금 기준 값만 보인다 — 「판정
    기준은 HOME 설정 → 판정 기준 탭에서 정합니다」 길 안내 글은 걷었고(2026-11-04 AMB-06 (나)),
    정하는 자리는 Guide 가 말한다(아래 시험)."""
    app = AppTest.from_string(app_script, default_timeout=300).run()
    assert not list(app.exception), [element.message for element in app.exception]

    assert list(app.number_input) == []
    captions = [element.value for element in app.sidebar.caption]
    assert not [text for text in captions if "에서 정합니다" in text or "→" in text], captions
    # 저장 전에는 공식버전 프리셋 값(109.5%·99.5%)을 사사오입 정수로 적는다. 월별 예외가 없으면
    # 예외 수를 덧붙이지 않는다.
    assert "확보 기준 110% · 경고 기준 100%" in captions
    # 바로 가기 단추도 두지 않는다(AMB-06 (나)).
    assert not [button for button in app.sidebar.button if "HOME 설정" in button.label]
    assert app.session_state[CARD_KEY] is False
    # 본문에는 결과 두 상자만 남는다 — 목적·계산식은 Guide 로 갔다.
    assert "추가 필요대수 계산 기준" not in {expander.label for expander in app.main.expander}
    assert app.button(key=GUIDE_TRIGGER_KEY)


def test_the_guide_carries_what_left_the_body() -> None:
    guide = load_guide("static_capa")
    for text in (
        "HOME 설정 → 판정 기준",
        "확보 기준",
        "경고 기준",
        "ceil(max(소요대수 × 경고 판정 경계 − 가용대수, 0))",
        "110% 면 109.5% 도",
        "경고까지 필요 + 확보까지 추가 = 총 추가 필요",
        "자원운영팀",
        "기술팀",
        "실행 관리",
        "도구 막대의 내려받기",
        "막대 끝은 기본 확보 기준과 그 표의 가장 큰 확보율 가운데 큰 쪽",
        "공정은 원본 이름으로",
        "`확보율` 은 원값",
    ):
        assert text in guide, text
    assert "각 표 아래" not in guide
    assert "**기본** 확보 기준까지의 거리" not in guide
    assert "공정은 화면의 표시명으로" not in guide


def _calculated_script(*, unrouted: bool) -> str:
    """계산을 실제로 돌리는 작은 시나리오의 Static Capa.

    `unrouted` 면 경로 없는 계획 한 줄을 더한다."""
    script = (
        TEST_SCRIPT.replace('PAGE_NAME = "reference_data.py"', 'PAGE_NAME = "static_capa.py"')
        .replace("STUB_CALCULATIONS = True", "STUB_CALCULATIONS = False")
        .replace(
            '"test-capacity-standards-page"',
            f'"test-static-capa-uncounted-{"unrouted" if unrouted else "clean"}"',
        )
    )
    if unrouted:
        script = script.replace("ADD_UNROUTED_PLAN = False", "ADD_UNROUTED_PLAN = True")
    assert 'PAGE_NAME = "static_capa.py"' in script
    return script


def _uncounted(app: AppTest) -> dict[str, Any]:
    """현황 요약의 소요대수에 들지 않은 수요 상태 알림(`ST-01`) 표지 하나."""
    (note,) = [note for note in alert_notes(app) if note.get("code") == "ST-01"]
    return note


def test_the_summary_says_how_much_demand_the_required_count_left_out() -> None:
    """경로에 닿지 않은 계획 부하는 소요대수에 들지 않아 미달 건수·필요대수가 그만큼 작다 — 산출
    결과에만 있던 그 건수를 현황 요약에서도 조회기간으로 알린다(E2E r2 static — PKG PLAN 을 고쳤는데
    현황 요약 수가 그대로라 헷갈렸다). 2026-11-03(결정 보드 D2 (나))부터 자리에 그리지 않는 상태
    알림이다 — 들지 않은 수요가 없어도 「없음」 표지를 낸다(해소)."""
    app = AppTest.from_string(_calculated_script(unrouted=True), default_timeout=120).run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert not app.main.warning
    note = _uncounted(app)
    assert note["active"] is True and note["level"] == "check"
    assert "소요대수에 들지 않은 수요가 있습니다(조회기간)" in note["full"]
    assert "RQ_REQB 경로에 닿지 않은 계획 부하 1건" in note["full"]
    assert "목록은 Alarm 의 이 줄에 딸린 표입니다" in note["full"]
    assert note["short"] == "소요대수에 안 든 계획 수요 1건(조회기간) — 목록: Alarm › 이 줄"
    # 산출 결과 소요대수 탭과 같은 표 — 현황 요약에서 본 줄도 그 자리에서 목록을 펼친다.
    assert table_frame(note_table(note, "경로에 닿지 않은 계획 부하"))["제외사유"].tolist() == [
        "경로 키 어긋남"
    ]

    clean = AppTest.from_string(_calculated_script(unrouted=False), default_timeout=120).run()
    assert not list(clean.exception), [element.message for element in clean.exception]
    quiet = _uncounted(clean)
    assert quiet["active"] is False and quiet["fp"] == ""
    assert quiet["scope"] != note["scope"]


def test_the_summary_leaves_the_route_side_count_to_the_alert_board(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """현황 요약의 알림은 계획 쪽 건수만 싣는다 — 경로 쪽(대당 Capa 가 없어 뺀 부하 경로)은 계획을
    고치지 않아도 늘 있을 수 있어(사내 실데이터에서 0 이 아니었다) 열 때마다 서는 경고가 된다. 경로
    쪽만 있으면 알림이 없고, 함께 있으면 계획 쪽만 적는다(페이지는 exec 때 이름을 집으므로 모듈
    속성을 바꾸면 그 셈이 들어간다)."""
    import capa_simulation.services.required_equipment as required_equipment

    counts = [required_equipment.RequiredExclusionCounts(excluded_routes=7)]

    def counted(*_lists: object) -> required_equipment.RequiredExclusionCounts:
        return counts[0]

    monkeypatch.setattr(required_equipment, "count_required_exclusions", counted)
    routes_only = AppTest.from_string(_calculated_script(unrouted=False), default_timeout=120).run()
    assert not list(routes_only.exception), [item.message for item in routes_only.exception]
    assert _uncounted(routes_only)["active"] is False

    counts[0] = required_equipment.RequiredExclusionCounts(unrouted_loads=2, excluded_routes=7)
    both = AppTest.from_string(_calculated_script(unrouted=False), default_timeout=120).run()
    assert not list(both.exception), [item.message for item in both.exception]
    note = _uncounted(both)
    assert "RQ_REQB 경로에 닿지 않은 계획 부하 2건" in note["full"]
    assert "대당 Capa 가 없어 뺀 부하 경로" not in note["full"]


def test_a_plan_list_too_large_for_the_alarm_is_pointed_at_on_the_result_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """표가 `alerts.TABLE_ROW_LIMIT` 를 넘으면 이 줄에 싣지 못해 글이 본문 자리(산출 결과 소요대수
    탭)를 가리킨다 — 이 화면에 펼침을 세우지는 않는다."""
    monkeypatch.setattr(alerts, "TABLE_ROW_LIMIT", 0)
    app = AppTest.from_string(_calculated_script(unrouted=True), default_timeout=120).run()
    assert not list(app.exception), [element.message for element in app.exception]
    note = _uncounted(app)
    assert "tables" not in note
    assert note["short"].endswith("목록: 산출 결과 › 소요대수")
    assert "산출 결과 → 소요대수 탭에 있습니다" in note["full"]
    assert not list(app.expander)


def _fill_shortfalls(
    monkeypatch: pytest.MonkeyPatch,
    *,
    warning: list[tuple[str, float]],
    secure: list[tuple[str, float]],
) -> None:
    """두 결과 상자의 표를 (공정, 확보율) 행으로 채운다. 페이지는 exec 때 이름을 집으므로 모듈
    속성을 바꾸면 이 행이 든다."""
    import capa_simulation.services.securement_rate as securement_rate

    original = securement_rate.build_securement_shortfall_tables

    def frame(rows: list[tuple[str, float]], columns: pd.Index) -> pd.DataFrame:
        filled = [
            {
                "생산계획년월": 202601,
                "공정": process,
                "확보율": rate,
                "가용대수": 1.0,
                "소요대수": 2.0,
                "경고기준 필요대수": 2,
                "확보기준 추가대수": 3,
                "확보목표 총 필요대수": 5,
            }
            for process, rate in rows
        ]
        return pd.DataFrame(filled).reindex(columns=columns)

    def both_filled(rate: pd.DataFrame, **kwargs: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
        warning_frame, secure_frame = original(rate, **kwargs)
        return frame(warning, warning_frame.columns), frame(secure, secure_frame.columns)

    monkeypatch.setattr(securement_rate, "build_securement_shortfall_tables", both_filled)


def test_the_two_result_boxes_keep_their_tables_and_carry_no_csv_button(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """경고 기준 미달 · 확보 기준 추가 확보 표에 CSV 단추를 두지 않는다 — 내려받기는 표 도구 막대 한
    곳이다(2026-11-05 사용자 요청 — 기능 중복). 두 표는 그대로 선다."""
    _fill_shortfalls(monkeypatch, warning=[("DEMO-P1", 0.5)], secure=[("DEMO-P1", 0.5)])
    app = AppTest.from_string(_calculated_script(unrouted=False), default_timeout=120).run()
    assert not list(app.exception), [element.message for element in app.exception]

    tables = [frame for frame in app.main.dataframe if "확보율" in frame.value.columns]
    assert len(tables) == 2
    assert "경고기준 필요대수" in tables[0].value.columns
    assert "경고기준 필요대수" not in tables[1].value.columns
    assert not app.get("download_button")


def _page_function(name: str) -> Callable[..., Any]:
    """페이지는 import 하면 화면을 그리므로 함수 하나만 떼어 실행한다."""
    tree = ast.parse(PAGE.read_text(encoding="utf-8"))
    node = next(
        item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name
    )
    namespace: dict[str, Any] = {"np": np, "pd": pd}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(PAGE), "exec"), namespace)
    function: Callable[..., Any] = namespace[name]
    return function


@pytest.mark.parametrize(
    ("rates", "top"),
    [
        pytest.param([], 1.1, id="빈 표"),
        pytest.param([None, float("nan")], 1.1, id="값이 모두 빔"),
        pytest.param([0.5, 1.09], 1.1, id="기본 기준 아래면 기본 기준"),
        pytest.param([0.5, 1.12], 1.12, id="기본 기준 위면 표 최댓값"),
        pytest.param([None, 1.5], 1.5, id="빈 값은 건너뜀"),
        pytest.param([float("inf"), 0.5], 1.1, id="무한대는 끝을 정하지 않음"),
    ],
)
def test_the_bar_top_is_the_larger_of_the_default_threshold_and_the_table_peak(
    rates: list[float | None], top: float
) -> None:
    """`ProgressColumn` 은 값을 `max_value` 로 잘라 CSV 로 내보낸다 — 끝이 표 최댓값 아래면 월별
    기준이 기본보다 높은 달의 행이 파일에서 잘린다(화면 112% · 파일 1.1). 칸 설정은 JSON 이라
    무한대를 싣지 못한다."""
    bar_top = _page_function("_bar_top")
    series = pd.Series(rates, dtype="object")
    assert bar_top(series, secure_threshold=1.1) == top
    assert bar_top(series.astype("float64"), secure_threshold=1.1) == top


def test_the_tables_hand_the_original_process_and_the_raw_rate_to_the_toolbar_csv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """화면은 표시명, 파일은 원본이다(UI-DAT-10 · 2026-11-06 사용자 답). 프레임은 원본 공정을 들고
    칸이 글자만 표시명으로 그린다 — 칸은 읽기 전용이다. 막대 끝은 표마다 정해져 그 표의 어느 값도
    잘리지 않는다. 값이 빈 표도 멈추지 않고 끝이 기본 확보 기준에 남는다."""
    _fill_shortfalls(
        monkeypatch,
        warning=[("Process-A", 1.12), ("Process-B", 0.5), ("Process-A", 0.7)],
        secure=[("Process-A", float("nan"))],
    )
    script = _calculated_script(unrouted=False).replace(
        "APPLY_RENAME = False", "APPLY_RENAME = True"
    )
    assert "APPLY_RENAME = True" in script
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not list(app.exception), [element.message for element in app.exception]

    warning, secure = [frame for frame in app.main.dataframe if "확보율" in frame.value.columns]

    assert warning.value["공정"].tolist() == ["Process-A", "Process-B", "Process-A"]
    assert warning.value["확보율"].tolist() == [1.12, 0.5, 0.7]
    columns = json.loads(warning.proto.columns)
    assert columns["공정"]["disabled"] is True
    assert columns["공정"]["type_config"] == {
        "type": "selectbox",
        "options": [
            {"value": "Process-A", "label": "가공"},
            {"value": "Process-B", "label": "Process-B"},
        ],
    }
    assert columns["확보율"]["type_config"]["type"] == "progress"
    assert columns["확보율"]["type_config"]["max_value"] == 1.12

    assert secure.value["공정"].tolist() == ["Process-A"]
    secure_columns = json.loads(secure.proto.columns)
    assert secure_columns["공정"]["disabled"] is True
    assert secure_columns["확보율"]["type_config"]["max_value"] == 1.1


def test_a_blank_stop_sends_the_alarm_to_the_reference_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """빈 칸 때문에 멈춘 계산은 채울 표를 말하고 「그 화면으로」 가 기준 정보를 연다(설계 규칙
    UI-NTF-08, 공용 판정 `calculation_stop_notice`)."""
    import capa_simulation.services.simulation_cache as simulation_cache

    def stopped(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError(
            "RQ_RUN_RATE의 CAPA_RUN_RATE 값이 빈 대당 Capa 기준이 있습니다: 2건, 예시 []"
        )

    monkeypatch.setattr(simulation_cache, "get_scenario_securement_rate", stopped)
    app = AppTest.from_string(_calculated_script(unrouted=False), default_timeout=120).run()
    assert not list(app.exception), [element.message for element in app.exception]

    (note,) = [item for item in alert_notes(app) if item.get("keep")]
    assert note["code"] == "ST-20"
    assert note["short"] == "대당 Capa 계산 멈춤 — 기준 정보 「효율」 빈 칸 2건을 채움"
    assert note["page"] == "기준 정보"
    assert "RQ_RUN_RATE" not in note["full"]


def test_an_empty_result_box_says_so_in_one_plain_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """두 결과 상자가 비면 표 대신 「…이 없습니다」 평문 한 줄이 선다 — 「없음」 이라는 값이다.
    초록 성공 상자는 알림창 몫이라 쓰지 않고(UI-NTF-01), 하는 법 · 길 안내도 붙이지 않는다
    (2026-11-04 AMB-02 (가)). 페이지는 exec 때 이름을 집으므로 모듈 속성을 바꾸면 빈 표가 든다."""
    import capa_simulation.services.securement_rate as securement_rate

    original = securement_rate.build_securement_shortfall_tables

    def emptied(*args: Any, **kwargs: Any) -> tuple[Any, Any]:
        warning, secure = original(*args, **kwargs)
        return warning.iloc[0:0], secure.iloc[0:0]

    monkeypatch.setattr(securement_rate, "build_securement_shortfall_tables", emptied)
    app = AppTest.from_string(_calculated_script(unrouted=False), default_timeout=120).run()
    assert not list(app.exception), [element.message for element in app.exception]

    assert not app.main.success
    lines = [str(element.value) for element in app.main.caption]
    assert "선택 기간에 경고 기준 미달 공정이 없습니다." in lines, lines
    assert "선택 기간에 경고 이상·확보 기준 미달 공정이 없습니다." in lines, lines
    assert not [frame for frame in app.main.dataframe if "확보율" in frame.value.columns]
