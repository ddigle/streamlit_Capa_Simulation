# Purpose: 누적 진척 「주차별」 까닭 가름의 꼬리표 규칙 · 항목 합 맞춤 · 상쇄 · 근거 없는 주를 본다.

"""누적 진척 「주차별」 까닭(`services/shortening_progress_reasons.py` — 2026-11-20 · 21 보드 답).

스냅숏은 손으로 만든 합성 호기 표(공정 `PRC-xx` · 호기 `EQ-xx`)이고 날짜는 손으로 셀 수 있게
잡았다 — 단축일수 = 확보 시점(기존 Qual) − 필요 시점(목표 Qual). 기록 일수는 스냅숏 합(넣기)이고,
손 고침 시험만 기록을 따로 적는다.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from capa_simulation.services.required_shortening import KIND_NEW, KIND_SHORTENED
from capa_simulation.services.shortening_baseline import BaselineProvenance
from capa_simulation.services.shortening_progress_log import (
    ProgressEntry,
    ProgressLog,
    ProgressWeek,
    screen_shortening_days,
)
from capa_simulation.services.shortening_progress_reasons import (
    DRAWN_ITEMS_MAX,
    LISTED_ITEMS_MAX,
    SNAPSHOT_UNIT_COLUMNS,
    TAG_BASIS,
    TAG_LAPSED,
    TAG_MANUAL,
    TAG_NEED_EARLIER,
    TAG_NEED_LATER,
    TAG_NEW,
    TAG_OTHER,
    TAG_QUAL_EARLIER,
    TAG_QUAL_LATER,
    TAG_RESOLVED,
    TAG_SCOPE,
    ProgressSnapshot,
    ProgressSnapshotDraft,
    ReasonItem,
    WeekChange,
    explain_week_changes,
    snapshot_digest,
    snapshot_draft,
    snapshot_units_total,
)

BASIS = "Static"
OTHER_BASIS = "설비 마스터"
TODAY = date(2027, 1, 4)
"""손으로 만든 표의 모든 필요 시점보다 앞 — 「기한 지남」 시험만 따로 오늘을 옮긴다."""
W40, W41, W42 = ProgressWeek(2026, 40), ProgressWeek(2026, 41), ProgressWeek(2026, 42)
NEED = date(2027, 3, 1)


def _real(process: str, unit: str, need: date, secure: date | None) -> dict[str, object]:
    return {
        "공정": process,
        "호기": unit,
        "구분": KIND_SHORTENED,
        "기존 Qual": secure,
        "목표 Qual": need,
        "단축일수": None if secure is None else (secure - need).days,
        "모듈 수": 1,
    }


def _virtual(process: str, unit: str, need: date) -> dict[str, object]:
    return {
        "공정": process,
        "호기": unit,
        "구분": KIND_NEW,
        "기존 Qual": None,
        "목표 Qual": need,
        "단축일수": None,
        "모듈 수": 1,
    }


def _draft(
    rows: list[dict[str, object]],
    processes: tuple[str, ...] | None = None,
    *,
    level: int = 100,
    basis: str = BASIS,
    today: date = TODAY,
    provenance: BaselineProvenance | None = None,
    months: tuple[int, int] = (202701, 202706),
    cutoff_days: dict[str, int] | None = None,
) -> ProgressSnapshotDraft:
    frame = pd.DataFrame(rows, columns=list(SNAPSHOT_UNIT_COLUMNS))
    scope = processes if processes is not None else tuple(dict.fromkeys(frame["공정"]))
    return snapshot_draft(
        frame,
        scope,
        level_percent=level,
        basis=basis,
        selected=False,
        today=today,
        months=months,
        cutoff_days=cutoff_days,
        provenance=provenance,
    )


def _explain(
    past: ProgressSnapshotDraft,
    current: ProgressSnapshotDraft,
    *,
    days: tuple[int, int] | None = None,
    weeks: tuple[ProgressWeek, ProgressWeek] = (W40, W41),
) -> WeekChange:
    before, after = days if days is not None else (past.days, current.days)
    log = ProgressLog(entries=(ProgressEntry(weeks[0], before), ProgressEntry(weeks[1], after)))
    snapshots = {
        weeks[0]: ProgressSnapshot(weeks[0], past),
        weeks[1]: ProgressSnapshot(weeks[1], current),
    }
    changes = explain_week_changes(log, snapshots)
    assert set(changes) == {weeks[1]}, "첫 기록은 까닭이 없다"
    return changes[weeks[1]]


def _tags(change: WeekChange) -> list[tuple[str, int, int, str | None]]:
    return [(item.tag, item.days, item.units, item.process) for item in change.items]


def _day(offset: int) -> date:
    return NEED + timedelta(days=offset)


def test_a_qual_moved_earlier_or_later_is_tagged_on_the_secure_side() -> None:
    """확보 시점(기존 Qual)만 움직인 호기 — 「Qual 당김」(−) · 「Qual 밀림」(+), 양은 단축일수
    차이."""
    past = _draft(
        [_real("PRC-03", "EQ-01", NEED, _day(30)), _real("PRC-03", "EQ-02", NEED, _day(20))]
    )
    current = _draft(
        [_real("PRC-03", "EQ-01", NEED, _day(24)), _real("PRC-03", "EQ-02", NEED, _day(31))]
    )
    change = _explain(past, current)
    assert change.change == 5 and change.balanced
    assert _tags(change) == [
        (TAG_QUAL_LATER, 11, 1, "PRC-03"),
        (TAG_QUAL_EARLIER, -6, 1, "PRC-03"),
    ]


def test_a_need_moved_is_tagged_on_the_need_side() -> None:
    """필요 시점(목표 Qual)만 움직인 호기 — 늦춰지면 「필요 늦춰짐」(−), 앞당겨지면 「필요
    당겨짐」(+)."""
    past = _draft(
        [_real("PRC-04", "EQ-01", NEED, _day(30)), _real("PRC-04", "EQ-02", NEED, _day(30))]
    )
    current = _draft(
        [
            _real("PRC-04", "EQ-01", _day(12), _day(30)),
            _real("PRC-04", "EQ-02", _day(-9), _day(30)),
        ]
    )
    change = _explain(past, current)
    assert _tags(change) == [
        (TAG_NEED_LATER, -12, 1, "PRC-04"),
        (TAG_NEED_EARLIER, 9, 1, "PRC-04"),
    ]
    assert change.total == change.change == -3


def test_the_larger_share_names_the_unit_and_moving_together_is_not_progress() -> None:
    """상쇄 꼴(진척 비교 시험의 둘 다 +20일 모양) — 확보 · 필요가 같은 날수만큼 함께 움직인 호기는
    순 0 이라 항목이 없고, 실제로 움직인 호기 하나만 남는다. 꼬리표는 |몫| 이 큰 쪽이다."""
    past = _draft(
        [
            _real("PRC-03", "EQ-14", NEED, _day(25)),
            _real("PRC-03", "EQ-15", NEED, _day(40)),
            _real("PRC-03", "EQ-16", NEED, _day(40)),
        ]
    )
    current = _draft(
        [
            _real("PRC-03", "EQ-14", _day(20), _day(45)),
            _real("PRC-03", "EQ-15", NEED, _day(28)),
            # 확보 −10 · 필요 +3 → 확보 쪽이 커 「Qual 당김」(−13 전체).
            _real("PRC-03", "EQ-16", _day(3), _day(30)),
        ]
    )
    change = _explain(past, current)
    assert _tags(change) == [(TAG_QUAL_EARLIER, -25, 2, "PRC-03")]
    assert change.balanced and change.change == -25


def test_units_only_on_one_side_are_new_or_resolved_and_the_scope_change_is_one_item() -> None:
    """한쪽에만 있는 당긴 호기 — 「신규 필요」(+이 주 일수) · 「해소」(−앞 일수). 한쪽 범위에만 있는
    공정은 「범위 바뀜」 한 항목이고 공정별 몫을 든다."""
    past = _draft(
        [
            _real("PRC-05", "EQ-01", NEED, _day(10)),
            _real("PRC-11", "EQ-02", NEED, _day(28)),
            _real("PRC-12", "EQ-03", NEED, _day(7)),
        ],
        ("PRC-05", "PRC-11", "PRC-12"),
    )
    current = _draft(
        [
            _real("PRC-05", "EQ-01", NEED, _day(10)),
            _real("PRC-05", "EQ-09", NEED, _day(30)),
            _real("PRC-15", "EQ-04", NEED, _day(14)),
        ],
        ("PRC-05", "PRC-11", "PRC-15"),
    )
    change = _explain(past, current)
    assert _tags(change) == [
        (TAG_NEW, 30, 1, "PRC-05"),
        (TAG_RESOLVED, -28, 1, "PRC-11"),
        (TAG_SCOPE, 7, 2, None),
    ]
    scope = change.items[-1]
    assert scope.parts == (("PRC-15", 14), ("PRC-12", -7))
    assert change.balanced and change.total == change.change == 9


def test_a_basis_or_target_change_is_one_first_item_without_unit_split() -> None:
    """현재 일정 기준이나 목표 확보율이 다른 두 주 — 호기별로 가르지 않고 「기준 바뀜」 한
    항목(스냅숏 합 차이)이 늘 첫 자리다. 손 고침만 따로 붙는다."""
    past = _draft([_real("PRC-07", "EQ-01", NEED, _day(40))])
    current = _draft(
        [_real("PRC-07", "EQ-01", NEED, _day(20)), _real("PRC-07", "EQ-02", NEED, _day(5))],
        level=120,
        basis=OTHER_BASIS,
    )
    change = _explain(past, current, days=(past.days, current.days + 50))
    assert [item.tag for item in change.items] == [TAG_BASIS, TAG_MANUAL], "조건 바뀜이 첫 자리"
    basis = change.items[0]
    assert basis.days == -15
    assert "현재 일정 기준 Static → 설비 마스터" in basis.note and "목표 100% → 120%" in basis.note
    assert change.items[1] == ReasonItem(TAG_MANUAL, 50)
    assert change.balanced and change.change == 35


def test_a_lapsed_need_and_a_spare_unit_getting_a_date_are_not_progress() -> None:
    """앞 주 필요 시점이 이 주 오늘보다 앞이면 「기한 지남」, 한 시점에만 현재 일정이 없는
    호기(Static 의 남는 호기)는 「기준 바뀜」(현재 일정 없음 ↔ 있음) — 둘 다 공정과 상관없이 항목
    하나다."""
    early = TODAY + timedelta(days=3)
    past = _draft(
        [
            _real("PRC-02", "EQ-01", early, early + timedelta(days=12)),
            _real("PRC-02", "EQ-02", NEED, None),
        ]
    )
    current = _draft(
        [
            _real("PRC-02", "EQ-01", early + timedelta(days=6), early + timedelta(days=12)),
            _real("PRC-02", "EQ-02", NEED, _day(8)),
        ],
        today=early + timedelta(days=5),
    )
    change = _explain(past, current)
    assert _tags(change) == [(TAG_BASIS, 8, 1, None), (TAG_LAPSED, -6, 1, None)]
    assert change.items[0].note == "현재 일정 없음 ↔ 있음"
    assert change.balanced and change.total == change.change == 2


def test_a_hand_edit_after_the_fill_is_its_own_item() -> None:
    """넣기 뒤 칸을 고쳐 저장했거나 나중에 손으로 고친 몫 — (이 주 기록 − 이 주 스냅숏 합) − (앞
    기록 − 앞 스냅숏 합) 이 「손 고침」 이다. 그래서 항목 합은 화면 합계가 아니라 기록 차이와
    맞는다."""
    past = _draft([_real("PRC-01", "EQ-01", NEED, _day(30))])
    current = _draft([_real("PRC-01", "EQ-01", NEED, _day(22))])
    change = _explain(past, current, days=(33, 20))
    assert _tags(change) == [(TAG_QUAL_EARLIER, -8, 1, "PRC-01"), (TAG_MANUAL, -5, 0, None)]
    assert change.change == -13 and change.balanced


def test_weeks_without_a_snapshot_or_with_a_stale_one_have_no_reasons() -> None:
    """근거 — 두 주 모두 그 기록과 같은 쓰기에서 선 스냅숏이 있을 때만 낸다. 손으로 적은 주(스냅숏
    없음)에 닿는 두 구간은 항목이 없고(0 이 아니다), 더 앞 스냅숏으로 건너 견주지 않는다. 스냅숏의
    기록 시각이 지금 기록 줄과 다르면(옛 코드가 그 주를 고침) 없는 것으로 본다. 건너뛴 주는 바로
    앞 기록 주와 한 구간이다."""
    one = _draft([_real("PRC-01", "EQ-01", NEED, _day(30))])
    two = _draft([_real("PRC-01", "EQ-01", NEED, _day(26))])
    stamp = datetime(2026, 10, 12, 9, 0)
    w44 = ProgressWeek(2026, 44)
    log = ProgressLog(
        entries=(
            ProgressEntry(W40, 30, updated_at=stamp),
            ProgressEntry(W41, 29),
            ProgressEntry(W42, 26, updated_at=stamp),
            ProgressEntry(w44, 26, updated_at=stamp),
        )
    )
    snapshots = {
        W40: ProgressSnapshot(W40, one, log_updated_at=stamp),
        W42: ProgressSnapshot(W42, two, log_updated_at=stamp),
        w44: ProgressSnapshot(w44, two, log_updated_at=stamp + timedelta(seconds=1)),
    }
    assert explain_week_changes(log, snapshots) == {}
    snapshots[w44] = ProgressSnapshot(w44, two, log_updated_at=stamp)
    changes = explain_week_changes(log, snapshots)
    assert set(changes) == {w44}, "W41 은 손으로 적은 주 — 그 앞뒤 구간은 근거가 없다"
    assert changes[w44].previous == W42 and changes[w44].weeks_between == 2
    assert changes[w44].items == () and changes[w44].balanced


def test_drawn_items_follow_the_week_direction_and_skip_a_possible_rename() -> None:
    """그림 꼬리표 항목 — 그 주 변동과 같은 쪽만, 둘째부터는 변동의 1/4 이상, 둘까지. 한 공정에 해소
    · 신규 필요가 함께면(호기 이름이 바뀌었을 수 있음) 그 둘은 그림에 올리지 않고 풍선만이다."""
    change = WeekChange(
        W41,
        W40,
        15,
        (
            ReasonItem(TAG_QUAL_LATER, 11, units=2, process="PRC-07"),
            ReasonItem(TAG_NEW, 4, units=1, process="PRC-09"),
            ReasonItem(TAG_QUAL_EARLIER, -3, units=1, process="PRC-02"),
            ReasonItem(TAG_NEED_EARLIER, 3, units=1, process="PRC-04"),
        ),
        balanced=True,
    )
    assert [item.process for item in change.drawn()] == ["PRC-07", "PRC-09"]
    assert len(change.drawn()) <= DRAWN_ITEMS_MAX
    small = WeekChange(
        W41,
        W40,
        20,
        (
            ReasonItem(TAG_QUAL_LATER, 17, process="PRC-07"),
            ReasonItem(TAG_NEW, 3, process="PRC-09"),
        ),
        balanced=True,
    )
    assert [item.process for item in small.drawn()] == ["PRC-07"], "둘째가 변동의 1/4 아래"
    renamed = WeekChange(
        W41,
        W40,
        8,
        (
            ReasonItem(TAG_NEW, 30, units=1, process="PRC-07"),
            ReasonItem(TAG_RESOLVED, -28, units=1, process="PRC-07"),
            ReasonItem(TAG_QUAL_LATER, 6, units=1, process="PRC-03"),
        ),
        balanced=True,
        renamed=("PRC-07",),
    )
    assert [item.tag for item in renamed.drawn()] == [TAG_QUAL_LATER]
    unbalanced = WeekChange(W41, W40, 9, change.items, balanced=False)
    assert unbalanced.drawn() == ()


def test_the_rename_suspect_is_found_from_the_pairing() -> None:
    """같은 공정에 당긴 호기의 해소와 신규 필요가 함께 — `renamed` 에 그 공정이 선다(합에는
    든다)."""
    past = _draft([_real("PRC-07", "EQ-OLD", NEED, _day(28))])
    current = _draft([_real("PRC-07", "EQ-NEW", NEED, _day(30))])
    change = _explain(past, current)
    assert change.renamed == ("PRC-07",)
    assert {item.tag for item in change.items} == {TAG_NEW, TAG_RESOLVED}
    assert change.balanced and change.drawn() == ()


def test_listed_items_fold_the_tail_into_one_other_line() -> None:
    """풍선 항목 — `LISTED_ITEMS_MAX` 이하면 전부, 넘으면 앞 다섯과 나머지 합 「그 밖 k건」."""
    items = tuple(
        ReasonItem(TAG_QUAL_EARLIER, -(10 - index), units=1, process=f"PRC-{index:02d}")
        for index in range(LISTED_ITEMS_MAX + 2)
    )
    change = WeekChange(W41, W40, sum(item.days for item in items), items, balanced=True)
    listed = change.listed()
    assert len(listed) == LISTED_ITEMS_MAX
    assert listed[:-1] == items[: LISTED_ITEMS_MAX - 1]
    other = listed[-1]
    assert other.tag == TAG_OTHER and other.count == 3
    assert other.days == sum(item.days for item in items[LISTED_ITEMS_MAX - 1 :])
    assert sum(item.days for item in listed) == change.change
    few = WeekChange(W41, W40, -9, items[:2], balanced=True)
    assert few.listed() == items[:2]


def test_extra_virtual_units_and_input_revisions_are_notes_outside_the_sum() -> None:
    """추가N 은 일수가 없어 합 밖 — 대수 변화만 덧말이다. 두 스냅숏의 계산 입력(시나리오 · 설비 일정
    · 공통 대장 리비전)이 다르면 그 글도 덧말이다(모르는 출처는 바뀜으로 보지 않는다)."""
    past = _draft(
        [_real("PRC-06", "EQ-01", NEED, _day(10)), _virtual("PRC-06", "추가1", NEED)],
        provenance=BaselineProvenance(scenario_revision_id="DEMO-r12", scenario_revision_no=12),
    )
    current = _draft(
        [
            _real("PRC-06", "EQ-01", NEED, _day(10)),
            _virtual("PRC-06", "추가1", NEED),
            _virtual("PRC-06", "추가2", NEED),
        ],
        provenance=BaselineProvenance(
            scenario_revision_id="DEMO-r13",
            scenario_revision_no=13,
            equipment_schedule_revision_ref="DEMO-s4",
        ),
    )
    change = _explain(past, current)
    assert change.items == () and change.change == 0 and change.balanced
    assert change.virtual == (1, 2)
    assert change.inputs == ("시나리오 리비전 r12 → r13",)


def test_a_month_range_or_cutoff_change_is_an_input_note_outside_the_sum() -> None:
    """조회 달 · 범위 공정의 Cut-off 가 다른 두 주 — 가름은 그대로(늘어난 끝 달로 든 호기는 「신규
    필요」)이고, 바뀐 입력은 합 밖 덧말이다(진척 비교 「조회 달 다름」 과 같은 결). Cut-off 는 두
    범위에 함께 있고 둘 다 아는 공정만 견준다. 시나리오 리비전 id 를 모르면 `reference_version` 이
    그 대신이다."""
    past = _draft(
        [_real("PRC-01", "EQ-01", NEED, _day(10))],
        ("PRC-01", "PRC-02", "PRC-03"),
        cutoff_days={"PRC-01": 10, "PRC-03": 4},
        provenance=BaselineProvenance(reference_version=11),
    )
    current = _draft(
        [_real("PRC-01", "EQ-01", NEED, _day(10)), _real("PRC-02", "EQ-02", NEED, _day(52))],
        ("PRC-01", "PRC-02", "PRC-03"),
        months=(202701, 202709),
        cutoff_days={"PRC-01": 12, "PRC-02": 7},
        provenance=BaselineProvenance(reference_version=12),
    )
    change = _explain(past, current)
    assert _tags(change) == [(TAG_NEW, 52, 1, "PRC-02")] and change.balanced
    assert change.inputs == ("조회 달 27.01–27.06 → 27.01–27.09", "시나리오 리비전")
    assert change.cutoffs == (("PRC-01", 10, 12),)
    same = _explain(past, _draft([_real("PRC-01", "EQ-01", NEED, _day(10))],
                                 ("PRC-01", "PRC-02", "PRC-03"),
                                 cutoff_days={"PRC-01": 10, "PRC-03": 4},
                                 provenance=BaselineProvenance(reference_version=11)))  # fmt: skip
    assert (same.inputs, same.cutoffs) == ((), ())


def test_the_draft_keeps_only_scope_rows_and_its_days_are_the_screen_total() -> None:
    """넣기 스냅숏 — 범위 공정 행만 새 표로 옮기고(넘겨받은 표는 고치지 않음) 합은 화면 합계
    (`screen_shortening_days`)와 같다. 구성 글은 같은 구성이면 오늘 · 출처와 상관없이 같다."""
    units = pd.DataFrame(
        [
            _real("PRC-01", "EQ-01", NEED, _day(12)),
            _real("PRC-01", "EQ-02", NEED, None),
            _virtual("PRC-01", "추가1", NEED),
            _real("PRC-02", "EQ-03", NEED, _day(40)),
            _real("PRC-03", "EQ-04", NEED, _day(9)),
        ],
        columns=list(SNAPSHOT_UNIT_COLUMNS),
    )
    before = units.copy()
    scope = ("PRC-03", "PRC-01")
    draft = snapshot_draft(
        units, scope, level_percent=110, basis=BASIS, selected=True, today=TODAY,
        months=(202701, 202703), cutoff_days={"PRC-01": 10},
    )  # fmt: skip
    pd.testing.assert_frame_equal(units, before)
    assert draft.processes == scope and draft.cutoff_days == (None, 10)
    assert list(draft.units["공정"]) == ["PRC-03", "PRC-01", "PRC-01", "PRC-01"]
    assert draft.days == screen_shortening_days(units, list(scope)) == 21
    assert draft.days == snapshot_units_total(draft.units)
    later = snapshot_draft(
        units, scope, level_percent=110, basis=BASIS, selected=True,
        today=TODAY + timedelta(days=3), months=(202701, 202703),
        provenance=BaselineProvenance(scenario_revision_id="DEMO-r2"),
    )  # fmt: skip
    assert later.digest == draft.digest == snapshot_digest(draft)
    moved = units.copy()
    moved.loc[0, "기존 Qual"] = _day(11)
    moved.loc[0, "단축일수"] = 11
    other = snapshot_draft(
        moved, scope, level_percent=110, basis=BASIS, selected=True, today=TODAY,
        months=(202701, 202703),
    )  # fmt: skip
    assert other.digest != draft.digest


def _random_rows(rng: random.Random, processes: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for process in processes:
        for number in rng.sample(range(1, 7), rng.randint(0, 4)):
            need = TODAY + timedelta(days=rng.randint(-20, 120))
            roll = rng.random()
            if roll < 0.15:
                rows.append(_real(process, f"EQ-{number:02d}", need, None))
            elif roll < 0.25:
                rows.append(_virtual(process, f"추가{number}", need))
            else:
                rows.append(
                    _real(process, f"EQ-{number:02d}", need, need + timedelta(rng.randint(0, 60)))
                )
    return rows


@pytest.mark.parametrize("seed", range(6))
def test_the_items_always_sum_to_the_record_change(seed: int) -> None:
    """맞춤 성질 — 넣기 · 손 고침 · 범위 · 기준 · 목표 · 오늘이 어떻게 바뀌어도 항목 합은 지난 기록
    대비와 정수로 같다(`balanced`). 합성 표를 씨앗마다 마흔 벌 견준다."""
    rng = random.Random(seed)
    pool = [f"PRC-{index:02d}" for index in range(1, 7)]
    for _ in range(40):
        before_scope = rng.sample(pool, rng.randint(1, 5))
        after_scope = rng.sample(pool, rng.randint(1, 5))
        past = _draft(
            _random_rows(rng, before_scope),
            tuple(before_scope),
            level=rng.choice((100, 110)),
            basis=rng.choice((BASIS, BASIS, OTHER_BASIS)),
        )
        current = _draft(
            _random_rows(rng, after_scope),
            tuple(after_scope),
            level=rng.choice((100, 100, 110)),
            basis=rng.choice((BASIS, BASIS, OTHER_BASIS)),
            today=TODAY + timedelta(days=rng.choice((0, 0, 14, 40))),
        )
        days = (past.days + rng.randint(-5, 5), current.days + rng.randint(-5, 5))
        change = _explain(past, current, days=days)
        assert change.balanced, (seed, change)
        assert change.total == change.change == days[1] - days[0]
        assert all(item.days != 0 for item in change.items), "0 항목은 버린다"
        assert sum(item.days for item in change.listed()) == change.change
