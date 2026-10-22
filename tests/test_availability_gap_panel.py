# Purpose: 비교 패널의 결과 선택·공정 필터·탭 복귀·9행 시트·근거 카드·표시명·안내를 검사한다.

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pandas as pd
import pytest
from sheet_reader import has_sheet, open_cell, sheet_hovers, sheet_value
from streamlit.testing.v1 import AppTest

from capa_simulation.components.availability_gap_panel import (
    DETAIL_CATEGORY_KEY,
    DETAIL_MODE_KEY,
    PROCESS_FILTER_KEY,
    RESULT_VIEW_KEY,
)
from capa_simulation.components.table_toolbar import CSV_DOWNLOAD_LABEL, render_csv_download
from capa_simulation.services.availability_sheet import (
    BREAKDOWN_LENT_COLUMN,
    GAP_ROWS,
    ROW_GAP_AVAILABLE,
    ROW_SCHEDULE_AVAILABLE,
    ROW_SCHEDULE_LENT,
    ROW_SCHEDULE_OWNED,
    ROW_STATIC_AVAILABLE,
    ROW_STATIC_LENT,
    ROW_STATIC_OWNED,
    SCHEDULE_ROWS,
    STATIC_ROWS,
)

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
    assert row["확보율차이"] == -0.15

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

    infos = [str(item.value) for item in app.info]
    assert len(infos) == 1 and infos[0].startswith(notice), infos
    assert not app.dataframe


def test_unmatched_processes_stay_out_of_totals_and_fallback_rows() -> None:
    app = _run()
    _select_view(app, "분류별 내역")
    assert _value(app, ROW_SCHEDULE_AVAILABLE) == 10.5
    assert _value(app, ROW_STATIC_AVAILABLE) == 14.0
    assert _value(app, ROW_GAP_AVAILABLE) == -3.5
    assert "Probe" in " ".join(item.value for item in app.warning)
    assert "한쪽에만 있는 공정 1개" in " ".join(item.value for item in app.caption)

    _select_view(app, "확보율 교차검증")
    assert set(app.dataframe[0].value["공정"]) == {"Die Attach", "Etch"}
    assert "Static 값으로 채운 공정 1개" in " ".join(item.value for item in app.caption)
    assert "Probe" in " ".join(item.value for item in app.warning)

    app.selectbox(key=PROCESS_FILTER_KEY).select("Probe").run()
    assert not app.exception
    assert not app.dataframe
    assert "아직 맞대어 볼 수 있는 공정이 없습니다" in " ".join(item.value for item in app.info)


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
    assert "테스트 조회 실패" in " ".join(item.value for item in app.warning)
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
    assert "Static 가용대수가 없어" in " ".join(item.value for item in app.info)
    assert "테스트 조회 실패" in " ".join(item.value for item in app.warning)


def test_missing_demand_only_blocks_the_cross_check() -> None:
    app = _run(missing_required=True)
    assert len(app.get("plotly_chart")) == 1
    _select_view(app, "확보율 교차검증")
    assert not app.dataframe
    assert not app.get("plotly_chart")
    assert "소요대수를 읽지 못해" in " ".join(item.value for item in app.info)


@pytest.mark.parametrize(
    ("state_key", "notice"),
    [("empty_cutoff", "공정별 Cut-off 를 먼저"), ("empty_months", "조회기간에 월이 없습니다")],
)
def test_missing_input_is_explained_before_any_result(state_key: str, notice: str) -> None:
    app = _run(**{state_key: True})
    assert not app.dataframe
    assert not app.get("plotly_chart")
    assert notice in " ".join(item.value for item in app.info)


def test_period_notices_do_not_direct_users_to_the_old_preference_tab() -> None:
    app = _run(short_span=True)
    assert "Cut-off 때문에" in " ".join(item.value for item in app.warning)
    _select_view(app, "확보율 교차검증")
    notices = " ".join(item.value for item in [*app.caption, *app.warning])
    assert "조회기간을 넓히면" in notices
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
    assert "`운영 비가동` 은 시트의 대여(비가동)와 다를 수" in " ".join(
        item.value for item in app.caption
    )

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

    # GAP 칸은 식과 짝 칸(설비 일정 기준 가용)의 호기다.
    open_cell(app, MONTH, ROW_GAP_AVAILABLE)
    app.run()
    markdown = " ".join(item.value for item in app.markdown)
    assert "GAP 가용 = 설비 일정 4.50 − Static 6.00 = −1.50" in markdown
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
    assert "칸을 누르면 근거가 여기에 뜹니다" in " ".join(item.value for item in app.markdown)


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
    assert "Wire Bond" in " ".join(item.value for item in app.warning)
    app.selectbox(key=PROCESS_FILTER_KEY).select("Wire Bond").run()
    assert not app.exception
    # 그림은 Static 과 설비 일정 기준을 맞대는 자리라 그리지 않고 까닭을 말한다.
    assert not app.get("plotly_chart")
    infos = " ".join(item.value for item in app.info)
    assert "「Wire Bond」 공정은 기준정보(Static)에 없어 GAP 을 내지 않습니다" in infos

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
        item.value for item in app.info
    )


def test_a_process_only_in_the_reference_side_shows_its_static_without_gap() -> None:
    app = _run()
    app.selectbox(key=PROCESS_FILTER_KEY).select("Probe").run()
    assert not app.get("plotly_chart")
    assert "「Probe」 공정은 설비 일정 기준이 나오지 않아" in " ".join(
        item.value for item in app.info
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
    assert "실제로 비교한 공정은 2개입니다" in captions
    assert "기준정보(Static)에 없는 공정 1개는" in captions

    app.selectbox(key=PROCESS_FILTER_KEY).select("Wire Bond").run()
    assert not app.exception
    assert not app.dataframe
    infos = " ".join(item.value for item in app.info)
    assert "「Wire Bond」 공정은 기준정보(Static)에 없어 확보율을 맞대지 않습니다" in infos

    # 맞댈 공정이 없을 때 이름이 어긋난 공정이 있으면 이름도 까닭으로 든다.
    app.selectbox(key=PROCESS_FILTER_KEY).select("Probe").run()
    infos = " ".join(item.value for item in app.info)
    assert "공정명을 기준정보와 맞추면" in infos


def _undated_captions(app: AppTest) -> list[str]:
    return [caption.value for caption in app.caption if "일정 미정" in caption.value]


def test_undated_units_are_named_in_the_scope_the_counts_use() -> None:
    """날짜가 빈 신규 호기는 Dynamic 에 들지 않는다 — 둘러싼 대수와 같은 범위로 한 줄 알린다."""
    app = _run(undated_units=True)

    assert _undated_captions(app) == [
        ":material/event_busy: 일정 미정 2대 (반입 미정 1 · Qual 미정 1) — 날짜가 들어올 때까지 "
        "가용대수에 세지 않습니다."
    ]

    app.selectbox(key=PROCESS_FILTER_KEY).set_value("Die Attach").run()
    assert [text.split(" — ")[0] for text in _undated_captions(app)] == [
        ":material/event_busy: 일정 미정 1대 (반입 미정 1)"
    ]

    for view in ("분류별 내역", "확보율 교차검증"):
        _select_view(app, view)
        assert len(_undated_captions(app)) == 1, view


def _usage_captions(app: AppTest) -> list[str]:
    return [caption.value for caption in app.caption if "사용기준이 HBM" in caption.value]


def test_non_hbm_units_are_named_in_every_view_in_the_scope_the_counts_use() -> None:
    """사용기준이 HBM·EDP 가 아닌 호기는 가용대수에서 빠진다 — 세 결과 모두 같은 범위로 한 줄
    알린다."""
    assert _usage_captions(_run(undated_units=True)) == []
    app = _run(undated_units=True, non_hbm_units=True)

    assert _usage_captions(app) == [
        ":material/filter_alt_off: 사용기준이 HBM·EDP 가 아닌 2대(설비 마스터 기준)는 가용대수에서 "
        "뺐습니다 — 배치·호기 목록에는 그대로 있습니다."
    ]
    app.selectbox(key=PROCESS_FILTER_KEY).set_value("Die Attach").run()
    assert [text.split("(")[0] for text in _usage_captions(app)] == [
        ":material/filter_alt_off: 사용기준이 HBM·EDP 가 아닌 1대"
    ]
    for view in ("분류별 내역", "확보율 교차검증"):
        _select_view(app, view)
        assert len(_usage_captions(app)) == 1, view


def test_no_undated_line_without_undated_units() -> None:
    assert _undated_captions(_run()) == []


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

    monkeypatch.setattr(
        "capa_simulation.components.availability_gap_panel.render_csv_download", record_csv
    )
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
    open_cell(app, MONTH, ROW_SCHEDULE_AVAILABLE)
    app.run()
    assert not app.exception
    # 공정 하나면 근거 카드 표에 `공정` 칸이 없고 제목이 표시명을 적는다.
    assert "공정" not in _evidence(app)[0].columns
    assert "표시-DA" in " ".join(item.value for item in app.markdown)

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


def test_name_mismatch_notices_keep_the_original_process_names() -> None:
    """공정명이 어긋난 자리를 알리는 문구는 설비 마스터·기준정보에서 고칠 **원본** 이름이다.

    필요 단축 일정의 「맞대지 못한 공정」 과 같은 갈래다(AGENTS 8장 ③).
    """
    app = _run(wire_bond_units=True, labels=True)
    warnings = " ".join(item.value for item in app.warning)
    assert "Wire Bond" in warnings and "표시-WB" not in warnings
    assert "표시-WB" in app.selectbox(key=PROCESS_FILTER_KEY).options

    app.selectbox(key=PROCESS_FILTER_KEY).select("Wire Bond").run()
    assert not app.exception
    infos = " ".join(item.value for item in app.info)
    assert "「Wire Bond」 공정은 기준정보(Static)에 없어" in infos and "표시-WB" not in infos
    # 경고는 그 이름이 원본이라고 밝힌다 — 상자에는 표시명만 보이므로.
    assert "아래 이름은 공정 표시명이 아니라 원본 공정명입니다" in warnings


def test_the_original_name_notes_appear_only_when_a_listed_name_is_relabelled() -> None:
    """표시명이 하나도 없으면 경고·캡션이 예전 문장 그대로다 — 「상자에는 표시명으로 보입니다」 를
    적을 까닭이 없다(2026-10-10 재검증)."""
    plain = _run(wire_bond_units=True)
    warnings = " ".join(item.value for item in plain.warning)
    captions = " ".join(item.value for item in plain.caption)
    assert "Wire Bond" in warnings and "표시명" not in warnings
    assert "한쪽에만 있는 공정 2개를 뺐습니다" in captions and "표시명" not in captions

    # 나열된 이름(Wire Bond·Probe)에 표시명이 없으면 다른 공정에 표시명이 있어도 적지 않는다.
    app = _run(wire_bond_units=True, label_map={"Die Attach": "표시-DA"})
    assert "표시명" not in " ".join(item.value for item in app.warning)
    assert "표시명" not in " ".join(item.value for item in app.caption)

    labelled = _run(wire_bond_units=True, labels=True)
    assert "상자에는 공정 표시명으로 보입니다" in " ".join(item.value for item in labelled.caption)


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
    assert "가용을 깎지 않은 비가동 1호기(EQ-S" in captions


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
