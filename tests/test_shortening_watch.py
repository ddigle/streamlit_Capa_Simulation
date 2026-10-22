# Purpose: 필요 단축 일정 진척 보드·카드 차례·기한 임박·이행 지연·호기 마스터 표 규칙을 본다.

"""`services/shortening_watch.py` — 계획(`LevelPlan`)과 진척 비교 행, 설비 마스터로 낸 표.

값은 합성이다(`DEMO_*`). 계획은 손으로 짠 `LevelPlan` 이라 계산 규칙(`required_shortening`)과
무관하게 보드·차례·목록 규칙만 본다. 설비 마스터는 `test_required_shortening` 의 행 도우미로 만든다.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest
from test_required_shortening import _master, _unit

from capa_simulation.services.required_shortening import (
    KIND_NEW,
    KIND_SHORTENED,
    PROCESS_MONTH_COLUMNS,
    UNIT_PLAN_COLUMNS,
    LevelPlan,
)
from capa_simulation.services.shortening_progress import PROGRESS_COLUMNS
from capa_simulation.services.shortening_watch import (
    BOARD_COLUMNS,
    BOARD_ORDERS,
    DELAYED_COLUMNS,
    IMMINENT_COLUMNS,
    MASTER_MISSING,
    ORDER_DISPLAY,
    ORDER_EARLIEST_QUAL,
    ORDER_LARGEST_GAP,
    ORDER_WORSENED_FIRST,
    TREND_IMPROVED,
    TREND_RESOLVED,
    TREND_UNCHANGED,
    TREND_WORSENED,
    board_order,
    delayed_units,
    first_shortage_month,
    imminent_units,
    process_board,
    process_counts,
    progress_trend,
    unit_managers,
    unit_qual_status,
)

TODAY = date(2026, 5, 10)
A, B, C = "DEMO_A", "DEMO_B", "DEMO_C"


def _months_frame(rows: list[tuple[str, int, float]]) -> pd.DataFrame:
    """(공정, 달, 과부족) — 다른 칸은 계산과 무관한 값으로 채운다."""
    records = []
    for process, month, gap in rows:
        record: dict[str, object] = dict.fromkeys(PROCESS_MONTH_COLUMNS, 0.0)
        record.update({"공정": process, "생산계획년월": month, "과부족": gap, "상태": "-"})
        records.append(record)
    return pd.DataFrame(records, columns=list(PROCESS_MONTH_COLUMNS))


def _units_frame(rows: list[tuple[str, str, str, date, int | None]]) -> pd.DataFrame:
    """(공정, 호기, 구분, 목표 Qual, 단축일수)."""
    records = []
    for process, unit, kind, target, days in rows:
        record: dict[str, object] = dict.fromkeys(UNIT_PLAN_COLUMNS)
        record.update(
            {
                "공정": process,
                "호기": unit,
                "구분": kind,
                "목표 Qual": target,
                "기존 Qual": None if kind == KIND_NEW else target + timedelta(days=days or 0),
                "단축일수": days,
                "모듈 수": 1,
            }
        )
        records.append(record)
    return pd.DataFrame(records, columns=list(UNIT_PLAN_COLUMNS))


def _level() -> LevelPlan:
    """A: 6월부터 −1.5(단축 둘·신규 하나), B: 5월 −0.4(단축 하나), C: 모자람 없음."""
    return LevelPlan(
        level=1.1,
        process_months=_months_frame(
            [
                (A, 202605, 0.2),
                (A, 202606, -1.5),
                (A, 202607, -0.5),
                (B, 202605, -0.4),
                (B, 202606, 0.1),
                (C, 202605, 0.3),
            ]
        ),
        units=_units_frame(
            [
                (A, "DEMO-A1", KIND_SHORTENED, date(2026, 6, 20), 30),
                (A, "DEMO-A2", KIND_SHORTENED, date(2026, 5, 25), 12),
                (A, "추가1", KIND_NEW, date(2026, 7, 1), None),
                (B, "DEMO-B1", KIND_SHORTENED, date(2026, 5, 12), 5),
            ]
        ),
    )


def test_the_board_has_one_row_per_process_in_the_given_order() -> None:
    board = process_board(_level(), [B, A, C], today=TODAY)

    assert list(board.columns) == list(BOARD_COLUMNS)
    assert list(board["공정"]) == [B, A, C]
    rows = board.set_index("공정")
    assert rows.at[A, "첫 부족 달"] == 202606
    assert rows.at[A, "월 최대 부족"] == pytest.approx(1.5)
    assert (rows.at[A, "당길 호기"], rows.at[A, "신규"]) == (2, 1)
    assert (rows.at[A, "단축일 합계"], rows.at[A, "최대 단축"]) == (42, 30)
    # 가장 이른 목표 Qual 은 가상 호기까지 본다 — A 는 A2(5/25), 오늘부터 15일.
    assert rows.at[A, "가장 이른 목표 Qual"] == date(2026, 5, 25)
    assert rows.at[A, "남은 일수"] == 15
    # 모자람이 없는 공정은 빈 줄이다.
    assert pd.isna(rows.at[C, "첫 부족 달"]) and rows.at[C, "월 최대 부족"] == 0
    assert rows.at[C, "가장 이른 목표 Qual"] is None and pd.isna(rows.at[C, "남은 일수"])
    # 진척 비교가 없으면 기준선 칸은 비어 있다.
    assert board["기준선 대비"].isna().all() and board["이행 지연"].isna().all()


def test_the_first_shortage_month_and_counts_match_the_card() -> None:
    level = _level()
    assert first_shortage_month(level, A) == 202606
    assert first_shortage_month(level, A, [202607]) == 202607
    assert first_shortage_month(level, C) is None
    assert process_counts(level, A) == (2, 1)
    assert process_counts(level, C) == (0, 0)


@pytest.mark.parametrize(
    ("order", "expected"),
    [
        (ORDER_DISPLAY, [C, B, A]),
        # 목표 Qual 이 없는 공정(C)은 뒤.
        (ORDER_EARLIEST_QUAL, [B, A, C]),
        (ORDER_LARGEST_GAP, [A, B, C]),
        # 진척 비교가 없으면 「악화 먼저」 는 표시순서다.
        (ORDER_WORSENED_FIRST, [C, B, A]),
    ],
)
def test_the_card_order_follows_the_chosen_rule(order: str, expected: list[str]) -> None:
    board = process_board(_level(), [C, B, A], today=TODAY)
    assert board_order(board, order, compared=False) == expected


def test_the_orders_are_four_fixed_options() -> None:
    assert BOARD_ORDERS == (
        "표시순서",
        "목표 Qual 이른 순",
        "최대 부족 큰 순",
        "기준선 대비 악화 먼저",
    )


def _progress(rows: list[dict[str, object]]) -> pd.DataFrame:
    records = []
    for row in rows:
        record: dict[str, object] = dict.fromkeys(PROGRESS_COLUMNS)
        record.update(row)
        records.append(record)
    frame = pd.DataFrame(records, columns=list(PROGRESS_COLUMNS))
    for column in ("과거 단축일수", "현재 단축일수", "단축일수 증감", "모듈 수"):
        frame[column] = pd.array(frame[column].tolist(), dtype="Int64")
    return frame


def _pair(
    process: str,
    unit: str,
    *,
    past: int | None,
    now: int | None,
    status: str,
    kind: str = KIND_SHORTENED,
    past_need: date | None = date(2026, 6, 1),
) -> dict[str, object]:
    return {
        "공정": process,
        "호기": unit,
        "구분": kind,
        "상태": status,
        "과거 필요 시점": past_need if past is not None else None,
        "과거 단축일수": past,
        "현재 필요 시점": date(2026, 6, 1) if now is not None else None,
        "현재 단축일수": now,
        "단축일수 증감": (now or 0) - (past or 0),
        "모듈 수": 1,
    }


def test_the_progress_trend_reads_improved_worsened_resolved_and_unchanged() -> None:
    improved = progress_trend(_progress([_pair(A, "U1", past=20, now=8, status="개선")]))
    assert (improved.label, improved.change) == (TREND_IMPROVED, -12)
    assert improved.text() == "개선 −12일"
    worse = progress_trend(_progress([_pair(A, "U1", past=3, now=8, status="악화")]))
    assert (worse.label, worse.text()) == (TREND_WORSENED, "악화 +5일")
    resolved = progress_trend(_progress([_pair(A, "U1", past=6, now=None, status="해소")]))
    assert (resolved.label, resolved.text()) == (TREND_RESOLVED, "해소")
    same = progress_trend(_progress([_pair(A, "U1", past=4, now=4, status="변동 없음")]))
    assert same.label == TREND_UNCHANGED
    # 일수가 같아도 추가N 이 늘면 악화다.
    more_new = progress_trend(
        _progress(
            [
                _pair(A, "U1", past=4, now=4, status="변동 없음"),
                _pair(A, "추가1", past=None, now=0, status="신규 필요", kind=KIND_NEW),
            ]
        )
    )
    assert more_new.label == TREND_WORSENED and "신규 0→1" in more_new.text()


def test_with_progress_rows_the_board_fills_the_baseline_columns_and_orders_worse_first() -> None:
    rows = _progress(
        [
            _pair(A, "DEMO-A1", past=10, now=30, status="악화"),
            _pair(B, "DEMO-B1", past=20, now=5, status="개선"),
        ]
    )
    delayed = pd.DataFrame({"공정": [B, B], "호기": ["DEMO-B1", "DEMO-B9"]})
    board = process_board(_level(), [B, A], today=TODAY, progress_rows=rows, delayed=delayed)
    by = board.set_index("공정")
    assert by.at[A, "기준선 대비"] == "악화 +20일" and by.at[A, "단축일 증감"] == 20
    assert by.at[B, "기준선 대비"] == "개선 −15일" and by.at[B, "이행 지연"] == 2
    assert by.at[A, "이행 지연"] == 0
    assert board_order(board, ORDER_WORSENED_FIRST, compared=True) == [A, B]


def test_imminent_units_are_those_due_within_n_days_both_kinds() -> None:
    managers = {"DEMO-A2": "DEMO 담당"}
    frame = imminent_units(_level(), [A, B], today=TODAY, days=15, managers=managers)

    assert list(frame.columns) == list(IMMINENT_COLUMNS)
    # B1(5/12, 2일) → A2(5/25, 15일 — 끝 날 포함). A1(6/20)·추가1(7/1)은 밖.
    assert list(frame["호기"]) == ["DEMO-B1", "DEMO-A2"]
    assert list(frame["남은 일수"]) == [2, 15]
    assert frame.loc[1, "담당자"] == "DEMO 담당" and pd.isna(frame.loc[0, "담당자"])
    wide = imminent_units(_level(), [A], today=TODAY, days=60)
    assert "추가1" in set(wide["호기"])
    assert pd.isna(wide.loc[wide["호기"].eq("추가1"), "단축일수"].iloc[0])
    # 범위 밖 공정은 세지 않는다.
    assert imminent_units(_level(), [C], today=TODAY, days=365).empty


def _equipment() -> pd.DataFrame:
    """Qual 완료 단일 호기 하나, 미완료 단일 하나, 모듈 둘 가운데 하나만 완료인 묶음 하나."""
    done = _unit("DEMO-D1", date(2026, 4, 20), confirmation="완료", attributes={"담당자": "갑"})
    done["Qual실적"] = date(2026, 4, 20)
    open_unit = _unit("DEMO-D2", date(2026, 4, 25), attributes={"담당자": "을"})
    first = _unit("DEMO-M1A", date(2026, 4, 22), parent="DEMO-M1", confirmation="완료")
    first["Qual실적"] = date(2026, 4, 22)
    second = _unit("DEMO-M1B", date(2026, 4, 28), parent="DEMO-M1", confirmation="계획")
    return _master([done, open_unit, first, second])


def test_the_unit_status_groups_modules_and_is_done_only_when_every_module_is() -> None:
    status = unit_qual_status(_equipment()).set_index("호기")

    assert list(status.index) == ["DEMO-D1", "DEMO-D2", "DEMO-M1"]
    assert bool(status.at["DEMO-D1", "완료"]) is True
    assert status.at["DEMO-D1", "Qual실적"] == date(2026, 4, 20)
    assert status.at["DEMO-D1", "담당자"] == "갑"
    assert bool(status.at["DEMO-D2", "완료"]) is False
    assert status.at["DEMO-D2", "Qual실적"] is None
    # 모듈 하나라도 실적·완료가 아니면 묶음은 완료가 아니다. Qual일정은 가장 늦은 모듈이다.
    assert bool(status.at["DEMO-M1", "완료"]) is False
    assert status.at["DEMO-M1", "Qual일정"] == date(2026, 4, 28)
    assert status.at["DEMO-M1", "Qual상태"] == "완료, 계획"
    # 비었거나 검증을 못 넘는 마스터는 빈 표다.
    assert unit_qual_status(pd.DataFrame()).empty


def test_delayed_units_are_past_baseline_targets_without_a_finished_qual() -> None:
    rows = _progress(
        [
            # 기준선 목표가 지났고 마스터 미완료 → 지연.
            _pair(
                A, "DEMO-D2", past=5, now=None, status="필요 시점 지남", past_need=date(2026, 5, 1)
            ),
            # 지났지만 완료 → 지연 아님.
            _pair(
                A, "DEMO-D1", past=5, now=None, status="필요 시점 지남", past_need=date(2026, 4, 1)
            ),
            # 모듈 묶음 하나 미완료 → 지연.
            _pair(
                A, "DEMO-M1", past=3, now=None, status="필요 시점 지남", past_need=date(2026, 5, 9)
            ),
            # 마스터에 없는 호기 → 지연(「마스터에 없음」).
            _pair(A, "DEMO-GONE", past=2, now=None, status="해소", past_need=date(2026, 4, 30)),
            # 오늘이 목표인 호기는 아직 지나지 않았다.
            _pair(A, "DEMO-D3", past=2, now=2, status="변동 없음", past_need=TODAY),
            # 가상 호기·범위 밖 공정은 보지 않는다.
            _pair(
                A,
                "추가1",
                past=0,
                now=None,
                status="해소",
                kind=KIND_NEW,
                past_need=date(2026, 4, 1),
            ),
            _pair(C, "DEMO-D2", past=5, now=None, status="해소", past_need=date(2026, 4, 1)),
        ]
    )
    frame = delayed_units(rows, unit_qual_status(_equipment()), today=TODAY, processes=[A, B])

    assert list(frame.columns) == list(DELAYED_COLUMNS)
    # 지난 일수가 긴 차례.
    assert list(frame["호기"]) == ["DEMO-GONE", "DEMO-D2", "DEMO-M1"]
    assert list(frame["지난 일수"]) == [10, 9, 1]
    by = frame.set_index("호기")
    assert by.at["DEMO-GONE", "Qual상태"] == MASTER_MISSING
    assert by.at["DEMO-D2", "담당자"] == "을"
    assert by.at["DEMO-D2", "Qual일정"] == date(2026, 4, 25)


def test_managers_come_from_the_plan_first_then_the_unit_master() -> None:
    plan_master = pd.DataFrame({"호기": ["U1", "U2"], "담당자": ["계획쪽", None]})
    status = pd.DataFrame({"호기": ["U1", "U2", "U3"], "담당자": ["마스터쪽", "을", "  "]})
    assert unit_managers(plan_master, status) == {"U1": "계획쪽", "U2": "을"}
    assert unit_managers(pd.DataFrame()) == {}
