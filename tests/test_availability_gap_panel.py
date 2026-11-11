# Purpose: 비교 패널의 결과 선택·공정 필터·탭 복귀·9행 시트·근거 카드·표시명·안내를 검사한다.

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pandas as pd
import pytest
from alert_marks import active_state, data_error_texts, note_table, states, table_frame
from sheet_reader import has_sheet, open_cell, sheet_hovers, sheet_value
from streamlit.testing.v1 import AppTest

from capa_simulation.components.availability_gap_panel import (
    CROSS_CHECK_FALLBACK_HELP,
    CROSS_CHECK_MONTHS_HELP,
    DETAIL_CATEGORY_KEY,
    DETAIL_MODE_HELP,
    DETAIL_MODE_KEY,
    GAP_SIGN_HELP,
    PROCESS_FILTER_KEY,
    RESULT_VIEW_HELP,
    RESULT_VIEW_KEY,
    UNIT_LIST_HELP,
)
from capa_simulation.components.availability_sheet_canvas import GROUP_TITLES
from capa_simulation.components.availability_sheet_keys import (
    GAP_SHEET_CSV_KEY,
    GAP_SHEET_MENU_KEY,
    GAP_SHEET_XLSX_KEY,
    GAP_UNIT_LIST_CSV_KEY,
    GAP_UNIT_LIST_MENU_KEY,
    GAP_UNIT_LIST_XLSX_KEY,
)
from capa_simulation.components.availability_sheet_workbook import (
    GAP_SHEET_NAME,
    UNIT_LIST_SHEET,
)
from capa_simulation.components.table_toolbar import (
    CSV_DOWNLOAD_LABEL,
    DOWNLOAD_MENU_KEY_PREFIX,
    DOWNLOAD_MENU_LABEL,
    SHEET_XLSX_LABEL,
    render_csv_download,
    render_xlsx_download,
)
from capa_simulation.services.availability_sheet import (
    BREAKDOWN_LENT_COLUMN,
    GAP_ROWS,
    ROW_GAP_AVAILABLE,
    ROW_ITEMS,
    ROW_SCHEDULE_AVAILABLE,
    ROW_SCHEDULE_LENT,
    ROW_SCHEDULE_OWNED,
    ROW_STATIC_AVAILABLE,
    ROW_STATIC_LENT,
    ROW_STATIC_OWNED,
    SCHEDULE_ROWS,
    STATIC_ROWS,
)
from capa_simulation.services.undated_equipment import UNDATED_HELP

MONTH = 202610


@pytest.fixture(autouse=True)
def _no_scrollbar_component(monkeypatch: pytest.MonkeyPatch) -> None:
    """시트 위 가로 스크롤바는 Components v2 컴포넌트라 AppTest 에서 등록되지 않는다 — 시험 동안만
    빈 함수로 바꾼다(공정 Capa 상세 화면 시험과 같다)."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar

    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda **_: None)


def _panel_app() -> None:
    """DB 없이 호기·기준정보·소요대수 입력을 교체할 수 있는 패널 호스트."""
    from datetime import date
    from types import SimpleNamespace

    import pandas as pd
    import streamlit as st

    from capa_simulation.components.availability_gap_panel import render_availability_gap_panel
    from capa_simulation.components.process_labels import ProcessLabels
    from capa_simulation.services.manual_downtime import ManualDowntime
    from capa_simulation.services.process_cutoff import prepare_process_cutoff
    from capa_simulation.services.simulation_cache import frame_digest

    spans = pd.DataFrame(
        {
            "설비명": ["EQ-1", "EQ-2"],
            "공정소분류": ["Die Attach", "Etch"],
            "상태": ["가용", "가용"],
            "시작일": [date(2020, 1, 1)] * 2,
            "종료일": [date(2030, 1, 1)] * 2,
        }
    )
    # `held_die_attach`·`demand_scale` 은 한쪽 입력만 바꾼다 — 앞은 Dynamic(비교 키)만, 뒤는
    # 소요대수(시나리오 키)만.
    held = float(st.session_state.get("held_die_attach", 3.0))
    baseline = pd.DataFrame({"공정": ["Die Attach", "Etch"], "기존보유대수": [held, 5.0]})
    cutoff = prepare_process_cutoff(
        pd.DataFrame(
            {"공정": ["Die Attach", "Etch"], "Cutoff일수": [15.0, 15.0], "비고": [None, None]}
        )
    )
    static = pd.DataFrame(
        {
            "생산계획년월": [202610] * 3,
            "공정": ["Die Attach", "Etch", "Probe"],
            "가용대수": [6.0, 8.0, 20.0],
        }
    )
    # 보유 − 대여 = 가용(어긋남 없음). Static 세 표는 같은 저장 리비전에서 함께 온다.
    static_owned = static.rename(columns={"가용대수": "설비보유"}).assign(설비보유=[7.0, 8.0, 22.0])
    static_lent = static.rename(columns={"가용대수": "설비대여평가"}).assign(
        설비대여평가=[1.0, 0.0, 2.0]
    )
    # `downtime` 을 켜면 EQ-1(가용, 환산비 1.5)에 닷새 비가동, 셋업 호기 EQ-S 에 나흘 비가동을
    # 넣는다 — 반사실(비가동 비움) 구간을 따로 넘긴다. 셋업 호기의 비가동은 대여에 들지 않아야 한다.
    counterfactual = None
    if st.session_state.get("downtime", False):
        counterfactual = pd.concat(
            [
                spans,
                pd.DataFrame(
                    {
                        "설비명": ["EQ-S"],
                        "공정소분류": ["Die Attach"],
                        "상태": ["셋업 진행중"],
                        "시작일": [date(2020, 1, 1)],
                        "종료일": [date(2030, 1, 1)],
                    }
                ),
            ],
            ignore_index=True,
        )
        spans = pd.DataFrame(
            {
                "설비명": ["EQ-1", "EQ-1", "EQ-1", "EQ-2", "EQ-S", "EQ-S", "EQ-S"],
                "공정소분류": ["Die Attach"] * 3 + ["Etch"] + ["Die Attach"] * 3,
                "상태": ["가용", "운영 비가동", "가용", "가용"]
                + ["셋업 진행중", "운영 비가동", "셋업 진행중"],
                "시작일": [
                    date(2020, 1, 1),
                    date(2026, 10, 4),
                    date(2026, 10, 9),
                    date(2020, 1, 1),
                    date(2020, 1, 1),
                    date(2026, 10, 1),
                    date(2026, 10, 5),
                ],
                # 구간은 끝을 포함하고 다음 구간은 그다음 날 시작한다(생애주기 구간과 같은 꼴).
                "종료일": [
                    date(2026, 10, 3),
                    date(2026, 10, 8),
                    date(2030, 1, 1),
                    date(2030, 1, 1),
                    date(2026, 9, 30),
                    date(2026, 10, 4),
                    date(2030, 1, 1),
                ],
            }
        )
    scale = float(st.session_state.get("demand_scale", 1.0))
    required = pd.DataFrame(
        {
            "생산계획년월": [202610] * 3,
            "공정": ["Die Attach", "Etch", "Probe"],
            "소요대수": [10.0 * scale, 20.0 * scale, 40.0 * scale],
        }
    )
    if st.session_state.get("wire_bond_units", False):
        # 설비에만 있는 공정 — 기준정보(Static)·소요대수에 `Wire Bond` 가 없다.
        spans = pd.concat(
            [
                spans,
                pd.DataFrame(
                    {
                        "설비명": ["EQ-9"],
                        "공정소분류": ["Wire Bond"],
                        "상태": ["가용"],
                        "시작일": [date(2020, 1, 1)],
                        "종료일": [date(2030, 1, 1)],
                    }
                ),
            ],
            ignore_index=True,
        )
        cutoff = prepare_process_cutoff(
            pd.DataFrame(
                {
                    "공정": ["Die Attach", "Etch", "Wire Bond"],
                    "Cutoff일수": [15.0, 15.0, 15.0],
                    "비고": [None, None, None],
                }
            )
        )
    if st.session_state.get("empty_required", False):
        required = required.iloc[:0]
    if st.session_state.get("omit_etch", False):
        spans = spans.loc[spans["공정소분류"] != "Etch"]
        baseline = baseline.loc[baseline["공정"] != "Etch"]
        cutoff = cutoff.loc[cutoff["공정"] != "Etch"]
        static = static.loc[static["공정"] != "Etch"]
        required = required.loc[required["공정"] != "Etch"]

    units = None
    if st.session_state.get("undated_units", False):
        from capa_simulation.services.equipment_contract import EQUIPMENT_COLUMNS

        # 날짜가 빈 신규 호기 둘(Die Attach 반입 미정, Etch Qual 미정)과 일정이 다 있는 EQ-1.
        # `non_hbm_units` 를 켜면 사용기준이 HBM·EDP 가 아닌 호기 둘(공정마다 하나)을 더한다.
        rows: list[tuple[str, str, date | None, date | None, str | None, str | None]] = [
            ("EQ-1", "Die Attach", date(2020, 1, 1), date(2020, 1, 5), "완료", "HBM"),
            ("EQ-NEW", "Die Attach", None, None, None, "HBM"),
            ("EQ-ETCH", "Etch", date(2026, 9, 1), None, None, "HBM"),
        ]
        if st.session_state.get("non_hbm_units", False):
            rows += [
                ("EQ-DA-OTHER", "Die Attach", date(2020, 1, 1), date(2020, 1, 5), "완료", "범용"),
                ("EQ-ETCH-BLANK", "Etch", date(2020, 1, 1), date(2020, 1, 5), "완료", None),
            ]
        units = pd.DataFrame(
            [
                {
                    **{column: None for column in EQUIPMENT_COLUMNS},
                    "설비명": unit,
                    "공정소분류": process,
                    "사용기준": basis,
                    "반입일정": arrival,
                    "Qual일정": qual,
                    "Qual상태": confirm,
                    "보관유무": "N",
                    "기존설비여부": "N",
                    "레이아웃표시": "N",
                }
                for unit, process, arrival, qual, confirm, basis in rows
            ],
            columns=EQUIPMENT_COLUMNS,
        )

    # `renames` 는 설비 쪽 이름(설비명·공정소분류 값)을 갈아 낀다 — 물결표 이름 시험용.
    renames = st.session_state.get("renames")
    if renames:
        spans = spans.replace(renames)
        cutoff = cutoff.replace(renames)
        if counterfactual is not None:
            counterfactual = counterfactual.replace(renames)

    # 공정 표시명. 켜면 `Die Attach`·`Wire Bond` 만 표시명이 있다 — `Etch`·`Probe` 는 원본이다.
    # `label_map` 은 그 매핑을 갈아 낀다.
    label_map = st.session_state.get("label_map")
    if label_map is None and st.session_state.get("labels", False):
        label_map = {"Die Attach": "표시-DA", "Wire Bond": "표시-WB"}
    labels = ProcessLabels(version=1, labels=label_map) if label_map else None
    is_open = st.toggle("비교 탭 열기", value=True, key="test_gap_panel_open")

    st.session_state.setdefault("required_loads", 0)

    def load_required() -> pd.DataFrame:
        # 페이지처럼 로더로 넘긴다 — 부른 횟수를 세션에 적어 캐시가 빗나갈 때만 푸는지 본다.
        st.session_state["required_loads"] += 1
        return required

    required_source: pd.DataFrame | Callable[[], pd.DataFrame] = required
    if st.session_state.get("lazy_required", False):
        required_source = load_required
    render_availability_gap_panel(
        spans=spans,
        baseline=baseline,
        cutoff=cutoff.iloc[:0] if st.session_state.get("empty_cutoff", False) else cutoff,
        months=[] if st.session_state.get("empty_months", False) else [202610],
        static_availability=None if st.session_state.get("missing_static", False) else static,
        static_owned=None if st.session_state.get("missing_static", False) else static_owned,
        static_lent=None if st.session_state.get("missing_static", False) else static_lent,
        static_error="테스트 조회 실패" if st.session_state.get("missing_static", False) else None,
        span_bounds=(date(2026, 10, 1), date(2026, 10, 31))
        if st.session_state.get("short_span", False)
        else (date(2026, 9, 1), date(2026, 10, 31)),
        conversion_ratios={"EQ-1": 1.5},
        required_equipment=None
        if st.session_state.get("missing_required", False)
        else required_source,
        # 페이지처럼 소요대수를 낸 시나리오 키를 주면 교차검증을 캐시한다. 여기서는 그 키를 소요대수
        # 내용 지문으로 만든다 — 키가 내용을 정한다는 페이지의 약속과 같다.
        required_equipment_key=(0, "panel-" + frame_digest(required), 202610, 202610)
        if st.session_state.get("keyed_required", False)
        else None,
        owner_tab=SimpleNamespace(open=is_open),
        units=units,
        process_labels=labels,
        counterfactual_spans=counterfactual,
        # `manual_rows` 는 입력 비가동 칸((공정, 달, 대수) — Preference 공용 프로필)이다.
        manual_downtime=ManualDowntime(rows=tuple(st.session_state.get("manual_rows", ()))),
    )


def _run(**state: object) -> AppTest:
    app = AppTest.from_function(_panel_app, default_timeout=30)
    for key, value in state.items():
        app.session_state[key] = value
    app.run()
    assert not app.exception
    return app


def _select_view(app: AppTest, value: str) -> None:
    app.segmented_control(key=RESULT_VIEW_KEY).set_value(value).run()
    assert not app.exception


def _value(app: AppTest, row: str, month: int = MONTH) -> float | None:
    return sheet_value(app, month, row)


def _evidence(app: AppTest) -> list[pd.DataFrame]:
    """근거 카드의 표(시트 뒤에 선 `st.dataframe`)."""
    return [element.value for element in app.dataframe]


def _units(frame: pd.DataFrame) -> pd.DataFrame:
    """근거 카드 호기 표에서 맨 아래 합계 줄을 뺀 것."""
    marker = "구분" if "구분" in frame.columns else "설비명"
    return frame.loc[frame[marker].astype(str).ne("합계")]


def test_the_schedule_head_names_the_floored_cutoff_days() -> None:
    """분류별 내역 「설비 일정 기준」 머리가 Cut-off 를 적은 값(35.8일)으로 적었는데 계산은 35일
    창이고 다른 화면은 35일이었다(2026-10-26 E2E). 계산과 같은 일수로 적고 내림을 함께 둔다."""
    from capa_simulation.components.availability_gap_panel import _schedule_detail
    from capa_simulation.services.process_cutoff import prepare_process_cutoff

    cutoff = prepare_process_cutoff(
        pd.DataFrame({"공정": ["DAF", "DA"], "Cutoff일수": [35.8, 34.0], "비고": [None, None]})
    )

    assert _schedule_detail("DAF", cutoff) == "설비 DB · 환산대수 · Cut-off 35일(35.8일 내림)"
    assert _schedule_detail("DA", cutoff) == "설비 DB · 환산대수 · Cut-off 34일"
    assert _schedule_detail(None, cutoff) == "설비 DB · 환산대수 · Cut-off 공정별"


def test_only_the_selected_result_is_drawn_and_counts_keep_their_axes() -> None:
    """세 결과 가운데 고른 것만 그린다. 그림·시트·교차검증의 설비 일정 기준 가용은 같은 환산 값이다
    (EQ-1 환산비 1.5 — 기존보유 3 + 1.5 = 4.5)."""
    app = _run()
    assert app.segmented_control(key=RESULT_VIEW_KEY).value == "가용대수 비교"
    assert len(app.get("plotly_chart")) == 1
    assert not app.dataframe

    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    chart = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert {trace["name"]: trace["y"] for trace in chart["data"]} == {
        "기존보유": [3.0],
        "가용(일할·환산)": [1.5],
        "Static(기준정보)": [6.0],
    }
    # 그림 GAP 글자는 시트 GAP 가용 칸과 같은 꼴이다(마이너스 U+2212).
    assert chart["layout"]["annotations"][0]["text"] == "−1.50"

    _select_view(app, "분류별 내역")
    assert has_sheet(app)
    assert not app.dataframe
    assert _value(app, ROW_STATIC_OWNED) == 7.0
    assert _value(app, ROW_STATIC_LENT) == -1.0
    assert _value(app, ROW_STATIC_AVAILABLE) == 6.0
    assert _value(app, ROW_SCHEDULE_OWNED) == 4.5
    assert _value(app, ROW_SCHEDULE_LENT) == 0.0
    assert _value(app, ROW_SCHEDULE_AVAILABLE) == 4.5
    assert _value(app, ROW_GAP_AVAILABLE) == -1.5

    _select_view(app, "확보율 교차검증")
    assert not app.get("plotly_chart")
    assert len(app.dataframe) == 1
    row = app.dataframe[0].value.iloc[0]
    assert row["공정"] == "Die Attach"
    assert row["소요대수"] == 10.0
    assert row["Static가용대수"] == 6.0
    assert row["일정기준가용대수"] == 4.5
    assert row["Static확보율"] == 0.6
    assert row["일정기준확보율"] == 0.45
    # 차이는 % 수다(비율 −0.15 로 적어 다른 화면의 % 와 단위가 어긋났다 — 2026-10-26 E2E). 「%p」 가
    # 아니라 「%」 다(2026-11-01 사용자 결정).
    assert row["확보율차이"] == -15.0
    formats = {
        name: config.get("type_config", {}).get("format")
        for name, config in json.loads(app.dataframe[0].proto.columns).items()
    }
    assert formats["Static확보율"] == formats["일정기준확보율"] == "percent"
    assert formats["확보율차이"] == "%+.1f%%"

    _select_view(app, "가용대수 비교")
    assert len(app.get("plotly_chart")) == 1
    assert not app.dataframe
    assert app.selectbox(key=PROCESS_FILTER_KEY).value == "Die Attach"


@pytest.mark.parametrize("omit_etch", [False, True])
def test_the_keyed_cross_check_shows_what_the_uncached_one_shows(omit_etch: bool) -> None:
    """시나리오 키를 주면 교차검증이 캐시를 지나지만 화면은 캐시 없이 맞댄 것과 글자까지 같다.
    입력(공정 하나 빠짐)이 바뀌면 키도 바뀌어 새로 맞댄 표가 나온다."""
    from capa_simulation.services.simulation_cache import get_securement_cross_check

    get_securement_cross_check.clear()

    def shown(**state: object) -> tuple[list[str], list[str]]:
        app = _run(omit_etch=omit_etch, **state)
        _select_view(app, "확보율 교차검증")
        table = app.dataframe[0].value.to_json(force_ascii=False)
        notes = [item.value for item in app.caption] + [item.value for item in app.warning]
        return [table], notes

    uncached = shown()
    keyed = shown(keyed_required=True)
    again = shown(keyed_required=True)

    assert keyed == uncached
    assert again == uncached


def test_the_keyed_cross_check_follows_the_inputs() -> None:
    """같은 키 꼴이라도 입력이 다르면 다른 표 — 공정 하나를 뺀 입력이 옛 표를 받지 않는다."""
    from capa_simulation.services.simulation_cache import get_securement_cross_check

    get_securement_cross_check.clear()
    full = _run(keyed_required=True)
    _select_view(full, "확보율 교차검증")
    narrowed = _run(keyed_required=True, omit_etch=True)
    _select_view(narrowed, "확보율 교차검증")

    assert set(full.dataframe[0].value["공정"]) == {"Die Attach", "Etch"}
    assert set(narrowed.dataframe[0].value["공정"]) == {"Die Attach"}


def _cross_check_table(**state: object) -> str:
    app = _run(**state)
    _select_view(app, "확보율 교차검증")
    return str(app.dataframe[0].value.to_json(force_ascii=False))


@pytest.mark.parametrize(
    ("changed", "first", "second"),
    [
        # 소요대수만 다르다 → 시나리오 키만 다르다(Dynamic·Static 은 같아 비교 키는 같다).
        ("demand_scale", 1.0, 2.0),
        # Dynamic(기존보유)만 다르다 → 비교 키만 다르다(소요대수·시나리오 키는 같다).
        ("held_die_attach", 3.0, 9.0),
    ],
)
def test_the_panel_key_carries_both_the_comparison_and_the_scenario(
    changed: str, first: float, second: float
) -> None:
    """패널이 조립한 캐시 키가 두 성분을 다 싣는다 — 한쪽 입력만 바뀐 회차가 옛 표를 받지 않는다.

    키의 한 성분을 상수로 바꾸면 그 성분만 바뀐 두 번째 회차가 첫 회차 표를 받는다.
    """
    from capa_simulation.services.simulation_cache import get_securement_cross_check

    get_securement_cross_check.clear()
    keyed_first = _cross_check_table(keyed_required=True, **{changed: first})
    keyed_second = _cross_check_table(keyed_required=True, **{changed: second})

    assert keyed_first != keyed_second
    assert keyed_first == _cross_check_table(**{changed: first})
    assert keyed_second == _cross_check_table(**{changed: second})


def test_a_keyed_rerun_does_not_cross_check_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """보기를 열어 둔 rerun(같은 조건)은 다시 맞대지 않는다 — 패널이 키를 받으면 캐시를 쓴다."""
    from capa_simulation.services import simulation_cache
    from capa_simulation.services.securement_cross_check import cross_check_from_monthly

    simulation_cache.get_securement_cross_check.clear()
    calls: list[int] = []
    original = cross_check_from_monthly

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return original(*args, **kwargs)

    # 캐시 안과 캐시를 건너뛰는 길이 같은 함수(`securement_cross_check_result`)를 지난다.
    monkeypatch.setattr(simulation_cache, "cross_check_from_monthly", counting)
    app = _run(keyed_required=True)
    _select_view(app, "확보율 교차검증")
    app.run()
    app.run()

    assert not app.exception
    assert len(calls) == 1


def test_a_lazy_demand_is_read_only_when_the_cross_check_misses() -> None:
    """페이지처럼 소요대수를 로더로 넘기면 다른 보기는 풀지 않고, 교차검증도 빗나갈 때만 푼다.

    화면은 프레임을 넘긴 회차와 글자까지 같다.
    """
    from capa_simulation.services.simulation_cache import get_securement_cross_check

    get_securement_cross_check.clear()
    app = _run(keyed_required=True, lazy_required=True)
    _select_view(app, "분류별 내역")
    _select_view(app, "가용대수 비교")
    assert app.session_state["required_loads"] == 0

    _select_view(app, "확보율 교차검증")
    app.run()
    app.run()
    assert app.session_state["required_loads"] == 1
    lazy_table = app.dataframe[0].value.to_json(force_ascii=False)
    lazy_notes = [item.value for item in app.caption] + [item.value for item in app.warning]

    framed = _run(keyed_required=True)
    _select_view(framed, "확보율 교차검증")
    assert framed.dataframe[0].value.to_json(force_ascii=False) == lazy_table
    assert [item.value for item in framed.caption] + [
        item.value for item in framed.warning
    ] == lazy_notes


@pytest.mark.parametrize("keyed", [False, True])
@pytest.mark.parametrize(
    ("state", "notice"),
    [
        # 소요대수가 비면 Static 이 비었어도 소요대수 문구가 먼저다. 비었다는 것은 조회기간에
        # 없다는 것이라 읽지 못한 것(로더가 없음)과 문구가 갈린다.
        (
            {"empty_required": True, "missing_static": True},
            "선택 범위에 소요대수 산출 기준이 없습니다",
        ),
        ({"empty_required": True}, "선택 범위에 소요대수 산출 기준이 없습니다"),
        ({"missing_static": True}, "Static 가용대수가 없어"),
        ({"missing_required": True}, "소요대수를 읽지 못해"),
    ],
)
def test_the_cross_check_explains_what_is_missing_in_the_same_order(
    state: dict[str, bool], notice: str, keyed: bool
) -> None:
    """맞대지 못하는 까닭은 소요대수 → Static 차례로 하나만 알린다 — 캐시를 지나도(로더) 같다."""
    from capa_simulation.services.simulation_cache import get_securement_cross_check

    get_securement_cross_check.clear()
    lazy = {"keyed_required": True, "lazy_required": True} if keyed else {}
    app = _run(**state, **lazy)
    _select_view(app, "확보율 교차검증")

    # 비었다는 결론(소요대수 · Static 없음)은 평문 한 줄, 읽지 못한 것은 마크 + 알림 글이다 — 셋
    # 가운데 하나만.
    reasons = (
        "선택 범위에 소요대수 산출 기준이 없습니다",
        "Static 가용대수가 없어",
        "소요대수를 읽지 못해",
    )
    lines = [str(item.value) for item in (*app.info, *app.caption)] + data_error_texts(app)
    notices = [line for line in lines if line.startswith(reasons)]
    assert len(notices) == 1 and notices[0].startswith(notice), notices
    assert not app.dataframe


def test_unmatched_processes_stay_out_of_totals_and_fallback_rows() -> None:
    app = _run()
    _select_view(app, "분류별 내역")
    assert _value(app, ROW_SCHEDULE_AVAILABLE) == 10.5
    assert _value(app, ROW_STATIC_AVAILABLE) == 14.0
    assert _value(app, ROW_GAP_AVAILABLE) == -3.5
    assert not app.warning
    assert "Probe" in _alerts(app)
    # 전체 합계에서 뺀 공정의 수 · 이름은 상태 알림(`EQ-06`)이 말한다 — 자리 캡션으로 다시 적지
    # 않고(내역은 알림, 따로 보는 법은 Guide), 알림 전문이 「전체 합계」 에서 빠진다고 적는다.
    unmatched = active_state(app, "EQ-06")
    assert unmatched is not None
    assert "「전체 합계」 에서 빠집니다" in str(unmatched["full"])
    # 알림창만 본 사람도 지금 보는 합계에서 그 공정이 빠졌다는 것을 안다(짧은 글이 그 사실 먼저).
    assert str(unmatched["short"]).startswith("전체 합계에서 뺀 한쪽 공정 ")
    assert "…" not in str(unmatched["short"])
    assert not any("한쪽에만 있는 공정" in item.value for item in app.caption)

    _select_view(app, "확보율 교차검증")
    assert set(app.dataframe[0].value["공정"]) == {"Die Attach", "Etch"}
    # Static 값으로 채운 공정은 자리 줄이 아니라 한쪽 공정 알림(`EQ-06`)의 전문이 말한다(2026-11-09
    # 상단 띠 재고 — 같은 알림이 있어 자리만 걷음).
    assert not any("Static 값으로 채운" in item.value for item in app.caption)
    unmatched = active_state(app, "EQ-06")
    assert unmatched is not None
    assert "Static 값으로 채워 비교 표에서 뺍니다" in str(unmatched["full"])
    assert CROSS_CHECK_FALLBACK_HELP in str(unmatched["full"])
    # 기준정보에 없는 공정 수는 위 알림이 말한다 — 「위 경고를 봅니다」 길 안내 캡션은 없다.
    assert not any("위 경고" in item.value for item in app.caption)
    assert "Probe" in _alerts(app)

    app.selectbox(key=PROCESS_FILTER_KEY).select("Probe").run()
    assert not app.exception
    assert not app.dataframe
    assert "아직 맞대어 볼 수 있는 공정이 없습니다" in " ".join(item.value for item in app.caption)


def test_hidden_tab_skips_output_and_preserves_both_selections() -> None:
    app = _run()
    app.selectbox(key=PROCESS_FILTER_KEY).select("Etch").run()
    _select_view(app, "분류별 내역")

    app.toggle(key="test_gap_panel_open").set_value(False).run()
    assert not app.exception
    assert not app.selectbox
    assert not app.segmented_control
    assert not app.get("plotly_chart")
    assert not app.dataframe
    assert app.session_state[PROCESS_FILTER_KEY] == "Etch"
    assert app.session_state[RESULT_VIEW_KEY] == "분류별 내역"

    app.toggle(key="test_gap_panel_open").set_value(True).run()
    assert not app.exception
    assert app.selectbox(key=PROCESS_FILTER_KEY).value == "Etch"
    assert app.segmented_control(key=RESULT_VIEW_KEY).value == "분류별 내역"
    assert _value(app, ROW_SCHEDULE_AVAILABLE) == 6.0


def test_missing_static_keeps_dynamic_detail_and_explains_cross_check_limit() -> None:
    """Static 을 아예 못 읽으면 시트의 Static·GAP 은 「—」 이고 까닭은 「기준정보에 없는 공정」이
    아니라 「Static 을 읽지 못함」이다."""
    app = _run(missing_static=True)
    assert not app.warning
    assert "테스트 조회 실패" in _alerts(app)
    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    _select_view(app, "분류별 내역")
    assert _value(app, ROW_SCHEDULE_AVAILABLE) == 4.5
    hovers = sheet_hovers(app)
    for row in (*STATIC_ROWS, *GAP_ROWS):
        assert _value(app, row) is None
        assert "Static 을 읽지 못해" in hovers[(MONTH, row)]
        assert "기준정보(Static)에 없는" not in hovers[(MONTH, row)]
    assert "Static 을 읽지 못해 「Die Attach」 공정의 GAP" in " ".join(
        item.value for item in app.caption
    )

    _select_view(app, "확보율 교차검증")
    assert not app.dataframe
    assert not app.get("plotly_chart")
    assert "Static 가용대수가 없어" in " ".join(item.value for item in app.caption)
    assert "테스트 조회 실패" in _alerts(app)


def test_missing_demand_only_blocks_the_cross_check() -> None:
    app = _run(missing_required=True)
    assert len(app.get("plotly_chart")) == 1
    _select_view(app, "확보율 교차검증")
    assert not app.dataframe
    assert not app.get("plotly_chart")
    assert "소요대수를 읽지 못해" in " ".join(data_error_texts(app))


@pytest.mark.parametrize(
    ("state_key", "notice"),
    [("empty_cutoff", "공정별 Cut-off 가 없습니다"), ("empty_months", "조회기간에 월이 없습니다")],
)
def test_missing_input_is_explained_before_any_result(state_key: str, notice: str) -> None:
    app = _run(**{state_key: True})
    assert not app.dataframe
    assert not app.get("plotly_chart")
    # 빈 상태는 회색 평문 한 줄(상자 아님)이고 하는 법은 그 줄의 풍선이다(설계 규칙 UI-TXT-04).
    assert notice in " ".join(item.value for item in app.caption)
    assert not app.info
    if state_key == "empty_cutoff":
        (line,) = [item for item in app.caption if notice in item.value]
        assert "먼저 적어야" in str(line.proto.help)


def test_period_notices_do_not_direct_users_to_the_old_preference_tab() -> None:
    app = _run(short_span=True)
    assert "Cut-off 때문에" in _alerts(app)
    _select_view(app, "확보율 교차검증")
    # 「맞대어 본 달」 은 자리에 줄을 세우지 않고 「조회 결과」 줄 끝 풍선이 값과 범위 설명을 함께
    # 말한다(2026-11-09 사용자 보드 T2 — 표 제목 풍선).
    helps = " ".join(str(item.proto.help) for item in app.caption)
    notices = " ".join(item.value for item in [*app.caption, *app.warning]) + _alerts(app)
    assert "조회기간을 넓히면" in helps
    assert not any("맞대어 본 달" in item.value for item in app.caption)
    assert "Preference" not in notices


def test_removed_process_returns_to_total_without_losing_the_result_choice() -> None:
    app = _run()
    app.selectbox(key=PROCESS_FILTER_KEY).select("Etch").run()
    _select_view(app, "분류별 내역")

    app.session_state["omit_etch"] = True
    app.run()
    assert not app.exception
    assert app.selectbox(key=PROCESS_FILTER_KEY).value == "전체 합계"
    assert app.segmented_control(key=RESULT_VIEW_KEY).value == "분류별 내역"
    assert _value(app, ROW_SCHEDULE_AVAILABLE) == 4.5


# ------------------------------------------------------------------ 호기 목록


def test_the_unit_list_shows_every_contribution_behind_the_counts() -> None:
    """「호기 목록」은 상태 분류별 호기 기여다. 기존보유·가용의 환산대수를 더하면 시트의 설비 일정
    기준 가용이다."""
    app = _run()
    _select_view(app, "분류별 내역")
    assert app.segmented_control(key=DETAIL_MODE_KEY).value == "시트"
    available = _value(app, ROW_SCHEDULE_AVAILABLE)
    # 사용법 글(「상태별 대수는 호기 목록으로」 · 「칸을 누르면 …」)은 자리에 늘 두지 않는다 —
    # 칸 풍선 · Guide 가 말한다. `표시` 는 라벨 줄을 걷는다(2026-11-09 상단 띠 재고).
    detail = app.segmented_control(key=DETAIL_MODE_KEY)
    assert detail.proto.label_visibility.value == detail.proto.label_visibility.COLLAPSED
    sheet_captions = " ".join(item.value for item in app.caption)
    assert "상태별 대수" not in sheet_captions and "칸을 누르면 그 달" not in sheet_captions

    app.segmented_control(key=DETAIL_MODE_KEY).set_value("호기 목록").run()
    assert not app.exception
    assert not has_sheet(app)
    units = app.dataframe[0].value
    # Probe 는 한쪽에만 있어 시트에서 빠진다 — 목록도 같은 범위다.
    assert set(units["공정"]) == {"Die Attach", "Etch"}
    assert {"월", "분류", "설비명", "기여일수", "대수", "환산대수"} <= set(units.columns)
    assert set(units.loc[units["분류"].eq("기존보유"), "설비명"]) == {"기존보유 · 전체"}
    listed = units.loc[units["분류"].isin(["기존보유", "가용"]), "환산대수"].sum()
    assert listed == pytest.approx(available)
    assert any(button.label == "CSV 다운로드" for button in app.download_button)
    # 목록 칸의 읽는 법은 「분류」 고르기 풍선이다 — 자리 캡션으로 늘 띄우지 않는다.
    assert app.multiselect(key=DETAIL_CATEGORY_KEY).help == UNIT_LIST_HELP
    assert "`운영 비가동` 은 시트의 대여(비가동)와 다를 수" in UNIT_LIST_HELP
    assert not any("운영 비가동" in item.value for item in app.caption)

    app.multiselect(key=DETAIL_CATEGORY_KEY).set_value(["가용"]).run()
    assert set(app.dataframe[0].value["분류"]) == {"가용"}


def test_a_clicked_cell_lists_its_units_and_adds_up_to_the_cell() -> None:
    """설비 일정 기준 칸은 호기 줄(기존보유 줄 포함) — 줄을 더하면 칸. Static 칸은 출처, GAP 칸은
    식과 짝 호기다."""
    app = _run()
    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    _select_view(app, "분류별 내역")

    open_cell(app, MONTH, ROW_SCHEDULE_AVAILABLE)
    app.run()
    assert not app.exception
    (lines,) = _evidence(app)
    units = _units(lines)
    assert units["설비명"].tolist() == ["기존보유 · 전체", "EQ-1"]
    assert units["가용"].sum() == pytest.approx(4.5)
    assert lines["가용"].iloc[-1] == pytest.approx(4.5)  # 합계 줄

    # 빈 칸(기존보유 줄의 환산비·일수, 합계 줄의 일수)은 「None」 이 아니라 「—」 로 적힌다. 공정
    # 하나면 `공정` 칸은 없다.
    assert app.dataframe[0].proto.placeholder == "—"
    assert "공정" not in lines.columns
    days = lines["실제 기여일수"].isna()
    assert bool(days.iloc[0]) and bool(days.iloc[-1])  # 기존보유 줄 · 합계 줄

    open_cell(app, MONTH, ROW_SCHEDULE_OWNED)
    app.run()
    (lines,) = _evidence(app)
    assert _units(lines)["보유"].sum() == pytest.approx(4.5)
    # 보유 칸도 공정 하나면 공정 Capa 상세 ④ 로 가는 길을 적는다(AppTest 에는 페이지가 없어 캡션).
    links = [item.proto.label for item in app.get("page_link")]
    captions = " ".join(item.value for item in app.caption)
    assert any("비가동 화살표" in label for label in links) or "비가동 화살표" in captions

    # Static 칸은 기준정보라 호기 표가 없다(공정 하나면 식 한 줄과 출처).
    open_cell(app, MONTH, ROW_STATIC_AVAILABLE)
    app.run()
    assert not _evidence(app)
    markdown = " ".join(item.value for item in app.markdown)
    assert "보유 7.00 + 대여 −1.00 = 6.00 · 기준정보 가용 6.00" in markdown
    assert "RQ_EQP_OWN" in " ".join(item.value for item in app.caption)

    # GAP 칸은 식과 짝 칸(설비 일정 기준 가용)의 호기다. 부호의 뜻은 식 줄 풍선이고 그 밑에 줄로
    # 세우지 않는다(설계 규칙 UI-TXT-01 · UI-TXT-02).
    open_cell(app, MONTH, ROW_GAP_AVAILABLE)
    app.run()
    markdown = " ".join(item.value for item in app.markdown)
    assert "GAP 가용 = 설비 일정 4.50 − Static 6.00 = −1.50" in markdown
    (formula,) = [item for item in app.markdown if item.value.startswith("GAP 가용 = ")]
    assert formula.proto.help == GAP_SIGN_HELP
    assert "음수:" in GAP_SIGN_HELP and "양수:" in GAP_SIGN_HELP
    signs = [item.value for item in app.caption if "음수:" in item.value or "양수:" in item.value]
    assert not signs, signs
    (lines,) = _evidence(app)
    assert _units(lines)["가용"].sum() == pytest.approx(4.5)


def test_a_click_does_not_follow_the_table_into_another_scope() -> None:
    """고른 칸은 범위 지문과 함께 남는다. 공정을 바꾸면 지난 칸은 무시한다 — 다른 공정의 같은 자리
    칸을 열지 않는다."""
    app = _run()
    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    _select_view(app, "분류별 내역")
    open_cell(app, MONTH, ROW_SCHEDULE_AVAILABLE)
    app.run()
    assert len(_evidence(app)) == 1

    app.selectbox(key=PROCESS_FILTER_KEY).select("Etch").run()
    assert not app.exception
    assert not _evidence(app)
    # 빈 근거 칸은 이름과 값 한 줄 — 읽는 법은 이름의 풍선이다(설계 규칙 UI-TXT-01 · UI-LAY-10).
    (heading,) = [item for item in app.markdown if item.value == "**근거**"]
    assert "칸을 누르면 근거가 여기에 뜹니다" in str(heading.proto.help)
    assert "고른 칸이 없습니다." in [item.value for item in app.caption]


def test_the_unit_list_keeps_full_precision_so_thirds_add_up_to_one() -> None:
    """모듈 셋이 1/3 씩이면 0.333 으로 잘라 더해 0.999 가 되면 안 된다. 표시만 세 자리다."""
    from io import StringIO

    import pandas as pd

    from capa_simulation.components.availability_gap_panel import _unit_table

    thirds = pd.DataFrame(
        {
            "생산계획년월": [202610] * 3,
            "공정": ["Bonder"] * 3,
            "분류": ["가용"] * 3,
            "설비명": ["APW01A", "APW01B", "APW01C"],
            "설비키": ["APW01"] * 3,
            "기존보유분류": pd.Series([pd.NA] * 3, dtype="string"),
            "기여일수": [31] * 3,
            "구간일수": [31] * 3,
            "대수": [1 / 3] * 3,
            "환산대수": [1 / 3] * 3,
        }
    )

    table = _unit_table(thirds, with_month=True)

    assert table["대수"].sum() == pytest.approx(1.0, abs=1e-12)
    exported = pd.read_csv(StringIO(table.to_csv(index=False)))
    assert exported["대수"].sum() == pytest.approx(1.0, abs=1e-12)
    assert "설비" in table.columns


# ------------------------------------------------------------------ 한쪽에만 있는 공정


def test_a_process_only_in_the_equipment_side_shows_no_gap_and_says_why() -> None:
    """기준정보에 없는 공정을 골라도 GAP 을 「+설비 일정」으로 내지 않는다(2026-10-01 결정).

    시트는 9행 그대로이고 Static·GAP 칸이 「—」 다(풍선이 까닭).
    """
    app = _run(wire_bond_units=True)
    assert "Wire Bond" in _alerts(app)
    app.selectbox(key=PROCESS_FILTER_KEY).select("Wire Bond").run()
    assert not app.exception
    # 그림은 Static 과 설비 일정 기준을 맞대는 자리라 그리지 않고 까닭을 말한다.
    assert not app.get("plotly_chart")
    infos = " ".join(item.value for item in app.caption)
    assert not app.info
    assert "「Wire Bond」 공정은 기준정보(Static)에 없어 GAP 을 내지 않습니다" in infos
    # 까닭(값)만 적고 「있는 쪽 값은 분류별 내역에서」 길 안내는 붙이지 않는다(Guide 가 말한다).
    assert "분류별 내역" not in infos

    _select_view(app, "분류별 내역")
    assert _value(app, ROW_SCHEDULE_AVAILABLE) == 1.0
    hovers = sheet_hovers(app)
    for row in (*STATIC_ROWS, *GAP_ROWS):
        assert _value(app, row) is None
        assert "기준정보(Static)에 없는 공정" in hovers[(MONTH, row)]
    assert "GAP 을 내지 않습니다" in " ".join(item.value for item in app.caption)

    open_cell(app, MONTH, ROW_GAP_AVAILABLE)
    app.run()
    assert "기준정보(Static)에 없는 공정이라 맞대지 않습니다" in " ".join(
        item.value for item in app.caption
    )


def test_a_process_only_in_the_reference_side_shows_its_static_without_gap() -> None:
    app = _run()
    app.selectbox(key=PROCESS_FILTER_KEY).select("Probe").run()
    assert not app.get("plotly_chart")
    assert "「Probe」 공정은 설비 일정 기준이 나오지 않아" in " ".join(
        item.value for item in app.caption
    )

    _select_view(app, "분류별 내역")
    assert _value(app, ROW_STATIC_AVAILABLE) == 20.0
    assert _value(app, ROW_STATIC_LENT) == -2.0
    for row in (*SCHEDULE_ROWS, *GAP_ROWS):
        assert _value(app, row) is None


def test_the_cross_check_leaves_out_a_process_missing_from_the_reference() -> None:
    """기준정보에 없는 공정은 확보율 표에 빈 행으로 실리지 않고, 비교한 공정 수에도 없다."""
    app = _run(wire_bond_units=True)
    _select_view(app, "확보율 교차검증")
    assert set(app.dataframe[0].value["공정"]) == {"Die Attach", "Etch"}
    captions = " ".join(item.value for item in app.caption)
    assert "실제로 비교한 공정" not in captions
    # 기준정보에 없는 공정의 수 · 이름은 상태 알림(`EQ-06`)만 말한다 — 자리 캡션은 없다.
    assert "기준정보에 없는 공정 1개" in _alerts(app)
    assert "기준정보(Static)에 없는 공정" not in captions

    app.selectbox(key=PROCESS_FILTER_KEY).select("Wire Bond").run()
    assert not app.exception
    assert not app.dataframe
    infos = " ".join(item.value for item in app.caption)
    assert "「Wire Bond」 공정은 기준정보(Static)에 없어 확보율을 맞대지 않습니다" in infos

    # 맞댈 공정이 없으면 빈 결과 한 줄만 적는다 — 무엇을 채우면 나오는지(하는 법)는 붙이지 않고,
    # 이름이 어긋난 까닭은 상태 알림(`EQ-06`)이 말한다.
    app.selectbox(key=PROCESS_FILTER_KEY).select("Probe").run()
    assert not app.info
    assert "아직 맞대어 볼 수 있는 공정이 없습니다." in [item.value for item in app.caption]
    assert "Probe" in _alerts(app)


def _undated_captions(app: AppTest) -> list[str]:
    return [caption.value for caption in app.caption if "일정 미정" in caption.value]


def test_undated_units_are_a_state_alert_in_every_view() -> None:
    """날짜가 빈 신규 호기는 Dynamic 에 들지 않는다 — 자리 줄이 아니라 Main 과 같은 상태 알림
    (`EQ-20`)이다(2026-11-09 상단 띠 재고). 설비 마스터 전체를 세어 공정 · 조회 결과 고르기에 지문이
    기대지 않는다."""
    app = _run(undated_units=True)

    assert _undated_captions(app) == []
    note = active_state(app, "EQ-20")
    assert note is not None
    assert str(note["short"]).startswith("일정 미정 2대 (반입 미정 1 · Qual 미정 1)")
    assert UNDATED_HELP in str(note["full"])
    fingerprint = note["fp"]

    app.selectbox(key=PROCESS_FILTER_KEY).set_value("Die Attach").run()
    for view in ("분류별 내역", "확보율 교차검증"):
        _select_view(app, view)
        assert _undated_captions(app) == [], view
        again = active_state(app, "EQ-20")
        assert again is not None and again["fp"] == fingerprint, view


def _usage_captions(app: AppTest) -> list[str]:
    return [caption.value for caption in app.caption if "사용기준 HBM" in caption.value]


def test_non_hbm_units_are_a_state_alert_in_every_view() -> None:
    """사용기준이 HBM·EDP 가 아닌 호기는 가용대수에서 빠진다 — 자리 줄이 아니라 Main 과 같은 상태
    알림(`EQ-22`)이다(2026-11-09 상단 띠 재고)."""
    plain = _run(undated_units=True)
    assert active_state(plain, "EQ-22") is None and states(plain, "EQ-22")
    app = _run(undated_units=True, non_hbm_units=True)

    assert _usage_captions(app) == []
    note = active_state(app, "EQ-22")
    assert note is not None
    assert str(note["short"]).startswith("사용기준 HBM·EDP 밖 2대 제외")
    assert len(table_frame(note_table(note, "사용기준 밖 호기"))) == 2
    app.selectbox(key=PROCESS_FILTER_KEY).set_value("Die Attach").run()
    for view in ("분류별 내역", "확보율 교차검증"):
        _select_view(app, view)
        assert _usage_captions(app) == [], view
        assert active_state(app, "EQ-22") is not None, view


def test_no_undated_line_without_undated_units() -> None:
    app = _run()
    assert _undated_captions(app) == []
    assert active_state(app, "EQ-20") is None


def test_the_panel_head_has_no_section_title_or_label_rows() -> None:
    """탭 머리의 구획 제목(「Static · 설비 일정 기준 가용대수 비교」 — 안쪽 탭 이름과 같은 말)과
    「확보율 교차검증」 제목(고른 전환 값과 같은 말)은 두지 않고, 「조회 결과」 · 「표시」 전환
    단추는 라벨 줄을 걷는다(2026-11-09 상단 띠 재고 — 설계 규칙 UI-TXT-07)."""
    app = _run()
    result = app.segmented_control(key=RESULT_VIEW_KEY)
    assert result.proto.label_visibility.value == result.proto.label_visibility.COLLAPSED
    heads = " ".join(item.value for item in app.markdown)
    assert "Static · 설비 일정 기준 가용대수 비교" not in heads
    # 두 전환의 뜻은 줄 끝 빈 캡션의 풍선 하나다(라벨이 숨으면 위젯 풍선도 숨는다 — 1.63).
    assert _row_helps(app) == [RESULT_VIEW_HELP]
    _select_view(app, "분류별 내역")
    assert _row_helps(app) == [f"{RESULT_VIEW_HELP}\n\n{DETAIL_MODE_HELP}"]
    _select_view(app, "확보율 교차검증")
    assert not any("확보율 교차검증" in item.value for item in app.markdown)
    # 확보율 교차검증에는 표 제목이 없어 「맞대어 본 달」 이 줄 끝 풍선의 첫 단락이다(사용자 보드
    # T2 — 표 제목 풍선, 값이 설명에 묻히지 않게 맨 앞).
    (cross,) = _row_helps(app)
    assert cross.startswith("맞대어 본 달: ")
    assert cross.endswith(f"{CROSS_CHECK_MONTHS_HELP}\n\n{RESULT_VIEW_HELP}")


def _row_helps(app: AppTest) -> list[str]:
    """전환 줄 끝 빈 캡션의 풍선들."""
    return [str(item.proto.help) for item in app.caption if item.value == ""]


def _help_group(app: AppTest) -> Any:
    """줄 끝 풍선(빈 캡션)이 든 칸."""
    from streamlit.testing.v1.element_tree import Block

    found = []

    def walk(node: Any) -> None:
        for child in node.children.values():
            if isinstance(child, Block):
                if any(
                    type(item).__name__ == "Caption" and getattr(item, "value", None) == ""
                    for item in child.children.values()
                ):
                    found.append(child)
                walk(child)

    walk(app.main)
    (group,) = found
    return group


def test_the_row_help_shares_a_small_gap_cell_with_the_last_switch() -> None:
    """줄 끝 풍선은 마지막 전환과 작은 간격의 한 칸이다 — 전환끼리는 넓게 띄워도 풍선이 따로 떠
    보이지 않게 Main 머리 줄의 줄 끝 풍선과 같은 간격이다(설계 규칙 UI-CON-03)."""
    from streamlit.proto.GapSize_pb2 import GapSize

    app = _run()
    for view, last in (
        ("가용대수 비교", RESULT_VIEW_KEY),
        ("분류별 내역", DETAIL_MODE_KEY),
        ("확보율 교차검증", RESULT_VIEW_KEY),
    ):
        _select_view(app, view)
        group = _help_group(app)
        keys = [getattr(child, "key", None) for child in group.children.values()]
        assert keys[0] == last, view
        assert group.proto.flex_container.gap_config.gap_size == GapSize.SMALL, view
        assert group.proto.width_config.use_content, view


def test_the_sheet_downloads_are_one_menu_on_the_switch_row() -> None:
    """「시트 CSV」 · 「시트 엑셀」 은 「조회 결과 · 표시」 전환 줄 오른쪽 끝의 「내려받기 ▾」 메뉴
    하나다 — 시트 위에 단추가 따로 한 줄을 차지하지 않는다(2026-11-09 사용자 보드 T3 · 2026-11-10
    답 Q2-7 꼴, 시트 엑셀 넓히기 2). 호기 목록에는 시트 내려받기가 없고 목록 아래 제 메뉴(CSV ·
    시트 엑셀)다."""
    from streamlit.testing.v1.element_tree import Block

    app = _run()
    _select_view(app, "분류별 내역")
    assert [button.label for button in app.download_button] == ["시트 CSV", SHEET_XLSX_LABEL]
    (menu,) = [block for block in app.get("popover") if block.key == GAP_SHEET_MENU_KEY]
    assert menu.proto.popover.label == DOWNLOAD_MENU_LABEL
    assert [str(button.key) for button in menu.download_button] == [
        GAP_SHEET_CSV_KEY,
        GAP_SHEET_XLSX_KEY,
    ]
    (switch_row,) = [
        block
        for block in app.main.children.values()
        if isinstance(block, Block)
        and any(getattr(child, "key", None) == RESULT_VIEW_KEY for child in _descendants(block))
    ]
    keys = [getattr(child, "key", None) for child in _descendants(switch_row)]
    assert {RESULT_VIEW_KEY, DETAIL_MODE_KEY, GAP_SHEET_MENU_KEY} <= set(keys)
    # 메뉴 단추 높이는 곁 전환 단추(28px)와 같다 — 시트를 보는 회차에만 줄이 높아져 아래 본문이
    # 오르내리지 않게(설계 규칙 UI-CON-01 · UI-PRF-03). 높이는 `render_download_pair` 한 곳이 메뉴
    # key 접두어로 건다(2026-11-11 남은 물음 보드 C9 — `tests/test_table_toolbar.py`).
    assert GAP_SHEET_MENU_KEY.startswith(DOWNLOAD_MENU_KEY_PREFIX)
    assert GAP_UNIT_LIST_MENU_KEY.startswith(DOWNLOAD_MENU_KEY_PREFIX)

    app.segmented_control(key=DETAIL_MODE_KEY).set_value("호기 목록").run()
    assert not app.exception
    assert [button.label for button in app.download_button] == [
        CSV_DOWNLOAD_LABEL,
        SHEET_XLSX_LABEL,
    ]
    (unit_menu,) = [block for block in app.get("popover") if block.key == GAP_UNIT_LIST_MENU_KEY]
    assert [str(button.key) for button in unit_menu.download_button] == [
        GAP_UNIT_LIST_CSV_KEY,
        GAP_UNIT_LIST_XLSX_KEY,
    ]


def test_the_unit_list_excel_is_the_screen_table_with_the_screen_digits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """호기 목록 시트 엑셀은 화면 표 그대로 — 같은 열 · 행, 공정 표시명, 화면 숫자 꼴(대수 ·
    환산대수 「%.3f」 → `0.000`)의 숫자 칸, 맨 위 값 줄에 분류 거름. CSV 는 원본 공정명 그대로다."""
    from xlsx_read import read_workbook

    sheets = _record_sheet(monkeypatch)
    app = _run(labels=True)
    _select_view(app, "분류별 내역")
    app.segmented_control(key=DETAIL_MODE_KEY).set_value("호기 목록").run()
    assert not app.exception
    shown = app.dataframe[0].value
    book = read_workbook(sheets[GAP_UNIT_LIST_XLSX_KEY]["data"])
    assert list(book) == [UNIT_LIST_SHEET]
    sheet = book[UNIT_LIST_SHEET]
    labels = sheet.column(0)
    header = labels.index("월")
    heading = {str(sheet.row(index)[0]): str(sheet.row(index)[1]) for index in range(1, header - 1)}
    assert heading["공정"] == "전체 합계" and heading["분류"] == "전체"
    assert sheet.row(header) == list(shown.columns)
    body = [sheet.row(index) for index in range(header + 1, header + 1 + len(shown))]
    assert [row[list(shown.columns).index("공정")] for row in body] == list(shown["공정"])
    assert "표시-DA" in set(shown["공정"])
    count = list(shown.columns).index("대수")
    assert sheet.cells[(header + 1, count)].number_format == "0.000"
    assert sheet.cells[(header + 1, count)].numeric
    assert sheets[GAP_UNIT_LIST_XLSX_KEY]["file_name"].endswith(".xlsx")


def _record_sheet(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    """패널이 「내려받기 ▾」 메뉴에 넘긴 시트 엑셀(key → 바이트 · 파일 이름)을 적어 둔다."""
    sheets: dict[str, dict[str, Any]] = {}

    def record(*, data: bytes, file_name: str, key: str, label: str) -> None:
        sheets[key] = {"data": data, "file_name": file_name}
        render_xlsx_download(data=data, file_name=file_name, key=key, label=label)

    monkeypatch.setattr("capa_simulation.components.table_toolbar.render_xlsx_download", record)
    return sheets


def test_the_sheet_excel_is_the_screen_sheet_built_once_per_condition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """시트 엑셀은 지금 화면 시트 그대로(같은 칸 값 · 「—」) — 파일 이름은 시트 CSV 와 같고 확장자만
    `.xlsx`. 통은 조건이 바뀐 뒤 처음 그리는 회차에 한 번 짓는다 — 칸 누름 · 같은 조건 회차는 다시
    짓지 않고, 공정을 바꾸면 새로 짓는다(새 `st.cache_*` 없음 — 세션 몇 벌)."""
    from xlsx_read import read_workbook

    from capa_simulation.components.availability_sheet_workbook import (
        availability_sheet_workbook,
    )

    sheets = _record_sheet(monkeypatch)
    builds: list[str] = []

    def counted(request: Any) -> bytes:
        builds.append(request.process_label)
        return availability_sheet_workbook(request)

    monkeypatch.setattr(
        "capa_simulation.components.availability_gap_panel.availability_sheet_workbook", counted
    )
    app = _run()
    _select_view(app, "분류별 내역")
    assert builds == ["전체 합계"]
    book = read_workbook(sheets[GAP_SHEET_XLSX_KEY]["data"])
    sheet = book[GAP_SHEET_NAME]
    heading = {str(sheet.row(index)[0]): str(sheet.row(index)[1]) for index in (1, 2)}
    assert heading == {"공정": "전체 합계", "조회기간": "26.10–26.10"}
    assert sheets[GAP_SHEET_XLSX_KEY]["file_name"] == "Static_대비_일정_시트_202610_202610.xlsx"
    # 같은 이름(「가용」)이 Static 묶음에도 있다 — 설비 일정 기준 묶음 제목 뒤의 것이다.
    labels = sheet.column(0)
    title = labels.index(GROUP_TITLES["sched"])
    available = labels.index(ROW_ITEMS[ROW_SCHEDULE_AVAILABLE], title)
    assert sheet.cells[(available, 2)].value == _value(app, ROW_SCHEDULE_AVAILABLE)

    open_cell(app, MONTH, ROW_SCHEDULE_AVAILABLE)
    app.run()
    assert not app.exception
    assert builds == ["전체 합계"]
    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    assert not app.exception
    assert builds == ["전체 합계", "Die Attach"]


def _descendants(node: Any) -> list[Any]:
    from streamlit.testing.v1.element_tree import Block

    out: list[Any] = []
    for child in node.children.values():
        out.append(child)
        if isinstance(child, Block):
            out.extend(_descendants(child))
    return out


# ------------------------------------------------------------------ 공정 표시명(Proc Rename)


def test_process_display_names_label_the_screen_but_values_stay_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-10-10 사용자 결정 — 보이는 글자만 표시명이다.

    `공정` 선택지·시트 머리·근거 카드·호기 목록·확보율 교차검증 표는 표시명이고, 선택값(세션)·범위
    지문·CSV(시트·호기 목록)는 원본이다.
    """
    # 내려받는 바이트는 위젯 proto 에 실리지 않는다. 패널이 부르는 이름을 갈아 끼워 적어 둔다
    # (AppTest 는 같은 프로세스에서 돈다).
    exported: dict[str | None, bytes] = {}

    def record_csv(
        *, data: bytes, file_name: str, key: str | None = None, label: str = CSV_DOWNLOAD_LABEL
    ) -> None:
        exported[key] = data
        render_csv_download(data=data, file_name=file_name, key=key, label=label)

    # 시트 · 호기 목록 CSV 는 「내려받기 ▾」 메뉴(표 곁 한 쌍 도우미) 안이다.
    monkeypatch.setattr("capa_simulation.components.table_toolbar.render_csv_download", record_csv)
    sheets = _record_sheet(monkeypatch)
    plain = _run()
    assert plain.selectbox(key=PROCESS_FILTER_KEY).options == [
        "전체 합계",
        "Die Attach",
        "Etch",
        "Probe",
    ]

    app = _run(labels=True)
    picker = app.selectbox(key=PROCESS_FILTER_KEY)
    # 보이는 글자의 가나다순이다 — `표시-DA` 가 원본 이름 뒤로 간다. `전체 합계` 는 맨 앞이다.
    assert picker.options == ["전체 합계", "Etch", "Probe", "표시-DA"]

    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    assert not app.exception
    assert app.selectbox(key=PROCESS_FILTER_KEY).value == "Die Attach"
    assert app.session_state[PROCESS_FILTER_KEY] == "Die Attach"

    _select_view(app, "분류별 내역")
    sheet_csv = exported["download_equipment_gap_sheet_csv"].decode("utf-8-sig")
    assert "Die Attach" in sheet_csv and "표시-" not in sheet_csv
    # 시트 엑셀은 화면처럼 표시명이다(머리 글자 · 머리 값 줄 — 공정 Capa 상세 시트 엑셀과 같다).
    from xlsx_read import read_workbook

    excel = read_workbook(sheets[GAP_SHEET_XLSX_KEY]["data"])[GAP_SHEET_NAME]
    assert "구분 · 표시-DA" in excel.column(0)
    assert excel.row(1)[:2] == ["공정", "표시-DA"]
    open_cell(app, MONTH, ROW_SCHEDULE_AVAILABLE)
    app.run()
    assert not app.exception
    # 공정 하나면 근거 카드 표에 `공정` 칸이 없고 제목이 표시명을 적는다(사람이 적은 글이라 막는다).
    assert "공정" not in _evidence(app)[0].columns
    assert "표시\\-DA" in " ".join(item.value for item in app.markdown)

    # 전체 합계면 근거 카드 호기 표의 `공정` 칸이 표시명이다.
    app.selectbox(key=PROCESS_FILTER_KEY).select("전체 합계").run()
    open_cell(app, MONTH, ROW_SCHEDULE_AVAILABLE)
    app.run()
    assert not app.exception
    assert "표시-DA" in set(_units(_evidence(app)[0])["공정"])
    assert "Die Attach" not in set(_units(_evidence(app)[0])["공정"])
    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()

    app.segmented_control(key=DETAIL_MODE_KEY).set_value("호기 목록").run()
    assert not app.exception
    assert set(app.dataframe[0].value["공정"]) == {"표시-DA"}
    text = exported["download_equipment_gap_unit_list_csv"].decode("utf-8-sig")
    assert "Die Attach" in text and "표시-" not in text

    _select_view(app, "확보율 교차검증")
    assert set(app.dataframe[0].value["공정"]) == {"표시-DA"}
    assert app.session_state[PROCESS_FILTER_KEY] == "Die Attach"


def test_the_evidence_title_blocks_the_tildes_of_a_display_name() -> None:
    """공정 표시명은 사람이 적은 글이다 — 근거 카드 머리(마크다운)에서 「공정~표시~D」 의 가운데가
    지움선이 되지 않는다(공정 Capa 상세 「산출 근거」 머리와 같은 꼴)."""
    app = _run(label_map={"Die Attach": "공정~표시~D"})
    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    _select_view(app, "분류별 내역")
    open_cell(app, MONTH, ROW_SCHEDULE_AVAILABLE)
    app.run()
    assert not app.exception

    titles = [str(item.value) for item in app.markdown if str(item.value).startswith("#####")]
    assert titles and all(title.endswith("· 공정\\~표시\\~D") for title in titles), titles


def test_name_mismatch_notices_keep_the_original_process_names() -> None:
    """공정명이 어긋난 자리를 알리는 문구는 설비 마스터·기준정보에서 고칠 **원본** 이름이다.

    필요 단축 일정의 「맞대지 못한 공정」 과 같은 갈래다(AGENTS 8장 ③).
    """
    app = _run(wire_bond_units=True, labels=True)
    warnings = _alerts(app)
    assert "Wire Bond" in warnings and "표시-WB" not in warnings
    assert "표시-WB" in app.selectbox(key=PROCESS_FILTER_KEY).options

    app.selectbox(key=PROCESS_FILTER_KEY).select("Wire Bond").run()
    assert not app.exception
    infos = " ".join(item.value for item in app.caption)
    assert "「Wire Bond」 공정은 기준정보(Static)에 없어" in infos and "표시-WB" not in infos
    # 경고는 그 이름이 원본이라고 밝힌다 — 상자에는 표시명만 보이므로.
    assert "아래 이름은 공정 표시명이 아니라 원본 공정명입니다" in warnings


def test_name_mismatch_notices_keep_the_original_names_as_plain_text() -> None:
    """한쪽에만 있는 공정 경고(마크다운)는 원본 공정명을 날로 실어 「E2E~공정~X」 를
    「E2E<del>공정</del>X」 로 그렸다(2026-10-26 E2E r5). 이제 상태 알림(`EQ-06`)이고 알림창 ·
    패널은 평문(`textContent`)이라 이름을 막지 않고 글자 그대로 싣는다(2026-11-03 D2)."""
    app = _run(wire_bond_units=True, renames={"Wire Bond": "E2E~공정~X"})

    assert not [item for item in app.warning if "맞지 않는" in str(item.value)]
    warning = _alerts(app)
    assert "설비에는 있는데 기준정보에 없는 공정 1개: E2E~공정~X" in warning, warning
    assert "\\~" not in warning


def test_the_original_name_notes_appear_only_when_a_listed_name_is_relabelled() -> None:
    """표시명이 하나도 없으면 경고·캡션이 예전 문장 그대로다 — 「상자에는 표시명으로 보입니다」 를
    적을 까닭이 없다(2026-10-10 재검증)."""
    plain = _run(wire_bond_units=True)
    warnings = _alerts(plain)
    captions = " ".join(item.value for item in plain.caption)
    assert "Wire Bond" in warnings and "표시명" not in warnings
    assert "표시명" not in captions

    # 나열된 이름(Wire Bond·Probe)에 표시명이 없으면 다른 공정에 표시명이 있어도 적지 않는다.
    app = _run(wire_bond_units=True, label_map={"Die Attach": "표시-DA"})
    assert "표시명" not in _alerts(app)
    assert "표시명" not in " ".join(item.value for item in app.caption)

    # 상자 글자가 표시명이라는 말은 알림 전문에만 있다 — 자리에 「뺐습니다」 캡션을 두지 않는다.
    labelled = _run(wire_bond_units=True, labels=True)
    assert "상자에는 표시명으로 보입니다" in _alerts(labelled)
    assert not any("뺐습니다" in item.value for item in labelled.caption)


def test_a_held_process_keeps_its_value_when_its_text_changes_in_the_browser() -> None:
    """브라우저는 고른 **글자**를 들고 있다가 되보낸다(일반 AppTest 는 이 결함을 못 본다).

    `Die Attach` 의 표시명이 `Etch` 인데 Etch 가 없을 때 고른 뒤 Etch 가 들어오면, 그 선택의 글자가
    「Etch (Die Attach)」 로 바뀐다. 잡은 값을 매 회차 세션에 다시 적지 않으면 브라우저가 옛 글자
    `Etch` 를 되보내 다음 조작에 원본 Etch 로 조용히 바뀌었다(2026-10-10 재검증 S1a).
    """
    from widget_browser import BrowserChoice

    app = AppTest.from_function(_panel_app, default_timeout=30)
    app.session_state["label_map"] = {"Die Attach": "Etch"}
    app.session_state["omit_etch"] = True
    browser = BrowserChoice(app, "selectbox", PROCESS_FILTER_KEY)
    browser.start()
    browser.pick("Etch")
    browser.run()
    assert app.session_state[PROCESS_FILTER_KEY] == "Die Attach"

    app.session_state["omit_etch"] = False
    for _ in range(3):
        browser.run()
        assert not app.exception
        assert app.session_state[PROCESS_FILTER_KEY] == "Die Attach"
    assert browser.wire == "Etch (Die Attach)"


def test_a_held_process_survives_a_new_display_name_in_the_browser() -> None:
    """Admin 에서 표시명을 바꾸면 브라우저의 옛 글자가 선택지에 없어 한 조작 뒤 선택이 빠졌다."""
    from widget_browser import BrowserChoice

    app = AppTest.from_function(_panel_app, default_timeout=30)
    app.session_state["label_map"] = {"Die Attach": "표시-DA"}
    browser = BrowserChoice(app, "selectbox", PROCESS_FILTER_KEY)
    browser.start()
    browser.pick("표시-DA")
    browser.run()
    for new_label in ("표시-DA2", "Probe"):
        app.session_state["label_map"] = {"Die Attach": new_label}
        for _ in range(2):
            browser.run()
            assert not app.exception
            assert app.session_state[PROCESS_FILTER_KEY] == "Die Attach"
    assert browser.wire == "Probe (Die Attach)"


def test_a_display_name_equal_to_another_process_still_picks_the_right_process() -> None:
    """Streamlit 1.63 selectbox 는 같은 글자 둘 중 **마지막**으로 돌아온다.

    `Etch` 의 표시명이 원본 `Probe` 와 같으면 Etch 를 골라도 Probe 를 계산했다(병합 전 리뷰
    재현). 「표시명 (원본)」 으로 가른다.
    """
    app = _run()
    app.session_state["label_map"] = {"Etch": "Probe"}
    app.run()
    picker = app.selectbox(key=PROCESS_FILTER_KEY)
    assert picker.options == ["전체 합계", "Die Attach", "Probe", "Probe (Etch)"]

    app.selectbox(key=PROCESS_FILTER_KEY).select("Etch").run()
    assert not app.exception
    assert app.session_state[PROCESS_FILTER_KEY] == "Etch"
    app.selectbox(key=PROCESS_FILTER_KEY).select("Probe").run()
    assert app.session_state[PROCESS_FILTER_KEY] == "Probe"


def test_a_display_name_equal_to_the_total_marker_keeps_the_default() -> None:
    """표시명이 `전체 합계` 와 같으면 다음 회차의 기본값이 그 공정으로 바뀌었다(리뷰 재현)."""
    app = _run()
    app.session_state["label_map"] = {"Etch": "전체 합계"}
    for _ in range(3):
        app.run()
        assert not app.exception
        assert app.session_state[PROCESS_FILTER_KEY] == "전체 합계"
    assert "전체 합계 (Etch)" in app.selectbox(key=PROCESS_FILTER_KEY).options

    app.selectbox(key=PROCESS_FILTER_KEY).select("Etch").run()
    assert app.session_state[PROCESS_FILTER_KEY] == "Etch"


def test_a_held_process_survives_a_colliding_display_name() -> None:
    app = _run()
    app.selectbox(key=PROCESS_FILTER_KEY).select("Probe").run()
    app.session_state["label_map"] = {"Etch": "Probe"}
    for _ in range(2):
        app.run()
        assert not app.exception
        assert app.session_state[PROCESS_FILTER_KEY] == "Probe"


# ------------------------------------------------------------------ 비가동(반사실)


def test_downtime_is_lent_only_where_it_cut_availability() -> None:
    """EQ-1(가용) 비가동은 대여로 깎이고, 셋업 호기 EQ-S 의 비가동은 대여에 들지 않는다 — 근거
    카드가 그 호기를 「가용을 깎지 않은 비가동」으로 따로 적는다. 칸마다 보유 + 대여 = 가용."""
    app = _run(downtime=True)
    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    _select_view(app, "분류별 내역")
    owned = _value(app, ROW_SCHEDULE_OWNED)
    lent = _value(app, ROW_SCHEDULE_LENT)
    available = _value(app, ROW_SCHEDULE_AVAILABLE)
    assert owned == 4.5
    assert lent is not None and lent < 0
    assert available is not None
    assert owned + lent == pytest.approx(available, abs=0.011)

    open_cell(app, MONTH, ROW_SCHEDULE_LENT)
    app.run()
    assert not app.exception
    (lines,) = _evidence(app)
    units = _units(lines)
    assert units["설비명"].tolist() == ["EQ-1"]
    assert units[BREAKDOWN_LENT_COLUMN].sum() == pytest.approx(lent, abs=0.005)
    assert units["손실 기여일수"].tolist() == [5]
    captions = " ".join(item.value for item in app.caption)
    # 설비명은 이름마다 막는다(`literal_names` — 「-」 도 「\-」 로 막혀 화면 글은 같다).
    assert "가용을 깎지 않은 비가동 1호기(EQ\\-S" in captions


def test_the_idle_downtime_note_blocks_the_tildes_of_the_unit_names() -> None:
    """근거 카드의 「가용을 깎지 않은 비가동」 줄(캡션)은 설비명을 날로 실었다 — 「EQ~S~R」 의
    가운데가 지움선이 된다(2026-10-26 E2E r5 와 같은 결함류). 물결표를 막는다."""
    app = _run(downtime=True, renames={"EQ-S": "EQ~S~R"})
    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    _select_view(app, "분류별 내역")
    open_cell(app, MONTH, ROW_SCHEDULE_LENT)
    app.run()
    assert not app.exception

    notes = [str(item.value) for item in app.caption if "가용을 깎지 않은 비가동" in item.value]
    assert notes and all("1호기(EQ\\~S\\~R)" in note for note in notes), notes


def test_the_idle_downtime_note_keeps_the_stars_of_the_unit_names() -> None:
    """물결표만 막으면 「EQ*S*R」 의 별표 짝이 기울임이 되어 「EQSR」 로 보인다 — 설비명 목록은
    이름마다 막는다(개선 거리 I11, AGENTS 9장 설비명 목록 규칙)."""
    app = _run(downtime=True, renames={"EQ-S": "EQ*S*R"})
    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    _select_view(app, "분류별 내역")
    open_cell(app, MONTH, ROW_SCHEDULE_LENT)
    app.run()
    assert not app.exception

    notes = [str(item.value) for item in app.caption if "가용을 깎지 않은 비가동" in item.value]
    assert notes and all("1호기(EQ\\*S\\*R)" in note for note in notes), notes


def _detail_link_app() -> None:
    import streamlit as st

    import capa_simulation.components.availability_gap_panel as panel

    original = st.page_link

    def record(page: str, **kwargs: object) -> None:
        st.session_state["test_link"] = {"page": page, **kwargs}

    st.page_link = record  # type: ignore[assignment]
    try:
        panel._render_detail_link("DEMO_Die_Attach", 202611)
    finally:
        st.page_link = original


def test_the_detail_link_opens_that_month_with_the_downtime_section() -> None:
    """「④ 에서 비가동 화살표로 보기」 는 `from=gap` 을 싣는다 — 공정 Capa 상세가 ④ 를 접어 두었어도
    다시 펴 링크 글이 거짓이 되지 않게. 테마 인자는 지금 값을 함께 싣는다."""
    app = AppTest.from_function(_detail_link_app)
    app.query_params["theme"] = "dark"
    app.run()

    assert not app.exception, [element.message for element in app.exception]
    link = app.session_state["test_link"]
    assert link["page"] == "app_pages/process_capa_detail.py"
    assert link["query_params"] == {
        "process": "DEMO_Die_Attach",
        "month": "202611",
        "from": "gap",
        "theme": "dark",
    }


def _alerts(app: AppTest) -> str:
    """머리 상태 알림(`EQ-06` 두 쪽 공정명 · `EQ-07` 조회 시작 · `EQ-08` Static 못 읽음)의 전문 —
    자리에는 경고 상자를 그리지 않는다(2026-11-03 D2)."""
    return " ".join(str(note["full"]) for note in states(app) if note.get("active"))


def test_the_sheet_heading_names_the_equipment_scenario_like_the_header_band(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """시트 엑셀 맨 위 「설비 시나리오」 값은 머리 띠 꼬리 글(공정 Capa 상세 시트와 같은 꼴)이고,
    띠가 아직 없으면 알림 범위 이름, 둘 다 없으면 줄을 뺀다. 「시나리오」(Static 세 행이 온 활성
    시나리오)는 공정 다음 — 공정 Capa 상세 · 산출 결과 시트와 같은 머리 띠 위 줄이고, 올라온
    리비전이 없으면 뺀다."""
    import capa_simulation.components.availability_gap_panel as panel

    monkeypatch.setattr(
        panel, "remembered_equipment_suffix", lambda: "설비 시나리오 · 운영 일정 · r3 · 공식 v3"
    )
    monkeypatch.setattr(panel, "scenario_line", lambda: "정기 검토 · r2 기준 · 공식 v4")
    heading = panel._sheet_heading(
        "전체 합계", (202611, 202702), alert_label="설비 「운영 일정」 r3", unit_filter=False
    )
    assert heading == (
        ("공정", "전체 합계"),
        ("시나리오", "정기 검토 · r2 기준 · 공식 v4"),
        ("조회기간", "26.11–27.02"),
        ("설비 시나리오", "운영 일정 · r3 · 공식 v3"),
    )
    monkeypatch.setattr(panel, "scenario_line", lambda: None)
    monkeypatch.setattr(panel, "remembered_equipment_suffix", lambda: None)
    assert panel._sheet_heading(
        "Etch", (202611,), alert_label="설비 「운영 일정」 r3", unit_filter=False
    )[-1] == ("설비 시나리오", "「운영 일정」 r3")
    assert [
        name
        for name, _ in panel._sheet_heading("Etch", (202611,), alert_label="", unit_filter=False)
    ] == [
        "공정",
        "조회기간",
    ]


def test_the_sheet_scenario_line_is_the_calculation_sheets_scenario_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Static 대비 일정 시트의 「시나리오」 값은 공정 Capa 상세 · 산출 결과
    시트(`scenario_period_rows`)의 그 값과 같은 글이다. 올라온 리비전이 없으면 None — 머리 띠가
    그때 적는 앱 이름을 시나리오로 싣지 않는다."""
    from datetime import datetime

    import capa_simulation.components.sheet_download as sheet_download
    from capa_simulation.scenario_activation import ActiveScenarioLabel

    monkeypatch.setattr(sheet_download, "latest_official_revision", lambda: ("rev-2", 4))
    monkeypatch.setattr(sheet_download, "has_unsaved_scenario_changes", lambda: False)
    monkeypatch.setattr(sheet_download, "newer_active_revision_no", lambda: None)
    monkeypatch.setattr(sheet_download, "active_scenario_label", lambda: None)
    assert sheet_download.scenario_line() is None

    label = ActiveScenarioLabel(
        scenario_id="scn-1",
        revision_id="rev-2",
        scenario_name="DEMO 정기 검토",
        simulation_code="DEMO-SIM",
        source_type="builtin",
        registered_at=datetime(2026, 11, 1, 9, 0),
        revision_no=2,
        revision_name="기준",
        saved_at=datetime(2026, 11, 2, 9, 0),
        first_month=202611,
        last_month=202702,
    )
    monkeypatch.setattr(sheet_download, "active_scenario_label", lambda: label)
    expected = dict(
        sheet_download.scenario_period_rows(selected=(202611, 202702), applied=(202611, 202702))
    )
    assert sheet_download.scenario_line() == expected["시나리오"]
    assert sheet_download.scenario_line() == "DEMO 정기 검토 · r2 기준 · 공식 v4"
