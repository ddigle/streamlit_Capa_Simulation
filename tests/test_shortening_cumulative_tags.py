# Purpose: 누적 진척 「주차별」 까닭 꼬리표의 자리 · 겹침 0 · 세로축 · 그림 표지와 풍선을 본다.

"""누적 진척 「주차별」 꼬리표(`components/shortening_cumulative_tags.py` · `weekly_figure`).

예시는 보드 시안(2026-11-20 · 21 중간-1 「점 곁 곧은 꼬리표」)의 합성 기록 한 벌이다 — 26-W38 ~
W48 열한 주, 최종 목표 120일 · 26-W52, 주마다 까닭 합 = 지난 기록 대비. 공정 이름은 `PRC-xx`.
"""

from __future__ import annotations

import random

import pytest

from capa_simulation.components.shortening_cumulative import _weekly_layout, weekly_figure
from capa_simulation.components.shortening_cumulative_tags import (
    GOAL_LABEL_ROOM_PX,
    MARK_HALF_PX,
    MAX_TAGS,
    NARROW_PLOT_WIDTH_PX,
    THRESHOLD_DAYS,
    PlotFrame,
    Scene,
    TagWish,
    overlaps,
    place_tags,
    tag_size,
    value_range,
)
from capa_simulation.services.shortening_progress_log import (
    ProgressEntry,
    ProgressGoal,
    ProgressGoalState,
    ProgressLog,
    ProgressWeek,
)
from capa_simulation.services.shortening_progress_reasons import (
    TAG_NEED_EARLIER,
    TAG_NEW,
    TAG_QUAL_EARLIER,
    TAG_QUAL_LATER,
    TAG_RESOLVED,
    ReasonItem,
    WeekChange,
)

RECORDS = [236, 228, 221, 223, 209, 224, 216, 203, 209, 196, 192]
GOAL = ProgressGoal(120, ProgressWeek(2026, 52))
WEEKS = [ProgressWeek(2026, 38 + offset) for offset in range(len(RECORDS))]
# 주(기록 차례) → (공정, 꼬리표, 대수, 일수). 둘째 줄이 없는 주는 「그 밖」 없이 한 항목이다.
REASONS: dict[int, list[tuple[str, str, int, int]]] = {
    1: [("PRC-03", TAG_QUAL_EARLIER, 2, -6), ("PRC-08", TAG_QUAL_EARLIER, 1, -2)],
    2: [("PRC-11", TAG_RESOLVED, 1, -5), ("PRC-08", TAG_QUAL_EARLIER, 1, -2)],
    3: [("PRC-06", TAG_NEED_EARLIER, 1, 2)],
    4: [("PRC-05", TAG_QUAL_EARLIER, 3, -10), ("PRC-02", TAG_RESOLVED, 1, -4)],
    5: [("PRC-07", TAG_QUAL_LATER, 2, 11), ("PRC-09", TAG_NEW, 1, 4)],
    6: [("PRC-07", TAG_QUAL_EARLIER, 1, -6), ("PRC-08", TAG_QUAL_EARLIER, 1, -2)],
    7: [("PRC-12", TAG_RESOLVED, 2, -9), ("PRC-08", TAG_QUAL_EARLIER, 3, -4)],
    8: [("PRC-04", TAG_NEED_EARLIER, 1, 9), ("PRC-08", TAG_QUAL_EARLIER, 2, -3)],
    9: [("PRC-05", TAG_QUAL_EARLIER, 2, -8), ("PRC-01", TAG_RESOLVED, 1, -5)],
    10: [("PRC-10", TAG_QUAL_EARLIER, 1, -4)],
}
LABELS = {"PRC-07": "DEMO 본딩", "PRC-05": "DEMO 절단"}
WIDTHS = (NARROW_PLOT_WIDTH_PX, 480, 640, 900, 1200, 1600)


def _log(records: list[int] = RECORDS, goal: ProgressGoal | None = GOAL) -> ProgressLog:
    return ProgressLog(
        entries=tuple(
            ProgressEntry(week, days) for week, days in zip(WEEKS, records, strict=False)
        ),
        goal=ProgressGoalState(goal=goal, version=1 if goal else 0),
    )


def _changes() -> dict[ProgressWeek, WeekChange]:
    out: dict[ProgressWeek, WeekChange] = {}
    for position, rows in REASONS.items():
        items = tuple(
            ReasonItem(tag, days, units=units, process=process)
            for process, tag, units, days in sorted(rows, key=lambda row: -abs(row[3]))
        )
        change = RECORDS[position] - RECORDS[position - 1]
        assert sum(item.days for item in items) == change, position
        out[WEEKS[position]] = WeekChange(
            WEEKS[position], WEEKS[position - 1], change, items, balanced=True
        )
    return out


def _label(process: str) -> str:
    return LABELS.get(process, process)


def test_the_example_places_every_rise_and_no_tag_overlaps_at_any_width() -> None:
    """가장 좁은 그림 칸에서 정한 꼬리표는 겹침이 0 이고, 그 결정(줄 · 맞춤 · 단)을 넓은 칸에 옮겨도
    겹침 0 이다. 5일 이상 오른 주(+15 · +6)는 모두 선다. 5일 미만(+2 · −4)은 꼬리표가 없다."""
    layout = _weekly_layout(_log(), _changes(), _label)
    placed = layout.placed
    rises = {5, 8}
    assert rises <= set(placed), placed.keys()
    assert not {3, 10} & set(placed), "5일 미만 변동은 표지만"
    assert len(placed) >= 4
    for width in WIDTHS:
        frame = layout.narrow.resized(width)
        moved = place_tags(frame, layout.scene, layout.wishes, decided=placed)
        assert set(moved) == set(placed)
        assert overlaps(frame, layout.scene, moved) == [], width
    for position, tag in placed.items():
        assert tag.up == (RECORDS[position] > RECORDS[position - 1])
        x, start, end = tag.leader
        assert start == pytest.approx(layout.narrow.y(RECORDS[position]) + (
            -MARK_HALF_PX if tag.up else MARK_HALF_PX
        ))  # fmt: skip
        assert (end < start) == tag.up, "지시선은 오름이면 위 · 내림이면 아래로 곧게"
        assert 2 <= len(tag.lines) <= 3, "머리 + 항목 둘까지"


def test_the_value_axis_starts_below_the_goal_not_at_zero() -> None:
    """세로축은 목표(없으면 가장 낮은 기록) 아래부터다(보드 답 q-axis a) — 0 이 아니다. 위에는 세 줄
    꼬리표 자리가 있다."""
    layout = _weekly_layout(_log(), _changes(), _label)
    low, high = layout.y_range
    assert 0 < low < GOAL.days and high > max(RECORDS)
    assert layout.narrow.y(max(RECORDS)) >= tag_size(("▲ +15일", "가", "가"))[1]
    plain_low, _ = _weekly_layout(_log(goal=None), None, str).y_range
    assert 0 < plain_low < min(RECORDS)
    assert value_range([5], None, 280)[0] == 0.0, "목표가 없으면 0 아래로는 내려가지 않는다"
    figure = weekly_figure(_log(), _changes(), label=_label).to_plotly_json()
    assert "tickvals" not in figure["layout"]["yaxis"], "0 위의 축은 Plotly 자동 눈금"


@pytest.mark.parametrize("goal_days", [0, 10])
def test_a_goal_near_zero_keeps_its_name_inside_the_plot(goal_days: int) -> None:
    """목표가 0일이거나 기록보다 아주 낮아 세로축이 0 에서 잘리면 목표 이름 자리만큼만 0 아래로
    내린다 — 이름(선 아래 오른쪽)이 그림 칸 밖 가로축 눈금 글 위로 빠지지 않는다. 0 아래 칸에는
    눈금이 없다(0 부터 「n일」)."""
    goal = ProgressGoal(goal_days, ProgressWeek(2026, 52))
    layout = _weekly_layout(_log(goal=goal), _changes(), _label)
    low, _ = layout.y_range
    assert low < 0
    assert layout.narrow.height - layout.narrow.y(goal_days) >= GOAL_LABEL_ROOM_PX
    assert overlaps(layout.narrow, layout.scene, layout.placed) == []
    yaxis = weekly_figure(_log(goal=goal), _changes(), label=_label).to_plotly_json()["layout"][
        "yaxis"
    ]
    ticks = list(yaxis["tickvals"])
    assert ticks[0] == 0 and all(value >= 0 for value in ticks) and len(ticks) >= 3
    assert list(yaxis["ticktext"]) == [f"{value:,}일" for value in ticks]


def test_a_fall_to_the_lowest_record_without_a_goal_still_gets_its_tag() -> None:
    """목표가 없거나 기록이 목표 아래로 내려와 가장 낮은 값이 그 주 기록이어도, 아래 자리가 두 줄
    꼬리표만큼 있어 내림 꼬리표가 칸 밖으로 숨지 않는다."""
    week = WEEKS[1]
    change = WeekChange(
        week,
        WEEKS[0],
        -9,
        (ReasonItem(TAG_QUAL_EARLIER, -9, units=1, process="PRC-04"),),
        balanced=True,
    )
    for goal in (None, ProgressGoal(380, ProgressWeek(2026, 52))):
        layout = _weekly_layout(_log([384, 375], goal), {week: change}, str)
        assert set(layout.placed) == {1}, goal
        assert not layout.placed[1].up


def test_threshold_and_the_tag_limit() -> None:
    """5일 미만 바람은 놓지 않고, 놓는 꼬리표는 `MAX_TAGS` 까지다(오름 먼저 · 큰 변동 먼저)."""
    points = tuple((float(position), 100.0 + 20 * (position % 2)) for position in range(16))
    scene = Scene(points=points)
    frame = PlotFrame(2400, 280, (-0.5, 15.5), value_range([p[1] for p in points], None, 280))
    wishes = [
        TagWish(position, 20 if position % 2 else -20, (("▲ +20일", "PRC-01 Qual 밀림 1대"),))
        for position in range(1, 16)
    ]
    wishes.append(TagWish(0, THRESHOLD_DAYS - 1, (("▲ +4일", "PRC-01 Qual 밀림 1대"),)))
    placed = place_tags(frame, scene, wishes)
    assert len(placed) == MAX_TAGS and 0 not in placed
    assert all(tag.up for tag in placed.values()), "오름 먼저"


def test_a_change_of_exactly_the_threshold_gets_a_tag() -> None:
    """문턱은 5일 이상이다(`THRESHOLD_DAYS` — 시안 원고 「이 일수 미만은 표지만」) — 지난 기록 대비
    +5일 · −5일 주에는 꼬리표가 서고 −4일 주에는 서지 않는다."""
    records = [200, 200 + THRESHOLD_DAYS, 200, 200 - (THRESHOLD_DAYS - 1)]
    changes: dict[ProgressWeek, WeekChange] = {}
    for position in range(1, len(records)):
        change = records[position] - records[position - 1]
        tag = TAG_QUAL_LATER if change > 0 else TAG_QUAL_EARLIER
        changes[WEEKS[position]] = WeekChange(
            WEEKS[position],
            WEEKS[position - 1],
            change,
            (ReasonItem(tag, change, units=1, process="PRC-01"),),
            balanced=True,
        )
    layout = _weekly_layout(_log(records, goal=None), changes, str)
    assert set(layout.placed) == {1, 2}
    assert layout.placed[1].lines[0] == "▲ +5일" and layout.placed[2].lines[0] == "▼ −5일"


@pytest.mark.parametrize("seed", range(4))
def test_random_records_never_overlap_when_moved_to_wider_plots(seed: int) -> None:
    """겹침 0 성질 — 합성 기록 스무 벌(길이 · 목표 · 까닭 무작위)에서 좁은 칸 결정을 넓은 칸들로
    옮겨도 다시 잰 겹침이 없다."""
    rng = random.Random(seed)
    for _ in range(20):
        length = rng.randint(4, len(WEEKS))
        records = [rng.randint(150, 260)]
        for _step in range(length - 1):
            records.append(max(0, records[-1] + rng.randint(-18, 14)))
        changes: dict[ProgressWeek, WeekChange] = {}
        for position in range(1, length):
            change = records[position] - records[position - 1]
            if change == 0 or rng.random() < 0.2:
                continue
            first = round(change * rng.uniform(0.5, 1.0)) or change
            secure = TAG_QUAL_LATER if first > 0 else TAG_QUAL_EARLIER
            process = f"PRC-{rng.randint(1, 12):02d}"
            items = [ReasonItem(secure, first, units=rng.randint(1, 3), process=process)]
            rest = change - first
            if rest:
                side = TAG_NEW if rest > 0 else TAG_RESOLVED
                items.append(ReasonItem(side, rest, units=1, process="PRC-08"))
            changes[WEEKS[position]] = WeekChange(
                WEEKS[position], WEEKS[position - 1], change, tuple(items), balanced=True
            )
        goal = (
            ProgressGoal(rng.randint(60, 140), ProgressWeek(2026, 52))
            if rng.random() < 0.8
            else None
        )
        layout = _weekly_layout(_log(records, goal), changes, str)
        assert overlaps(layout.narrow, layout.scene, layout.placed) == []
        for width in WIDTHS[1:]:
            frame = layout.narrow.resized(width)
            moved = place_tags(frame, layout.scene, layout.wishes, decided=layout.placed)
            assert overlaps(frame, layout.scene, moved) == [], (seed, width, records)


def test_the_figure_draws_tags_marks_rising_segments_and_full_reasons_on_hover() -> None:
    """꼬리표가 선 주는 큰 ▲ · ▼ 이고 오른 주만 들어오는 구간이 굵은 주황 선이다. 꼬리표 글은 「▲
    +15일」 과 표시명 항목, 점 · 꼬리표 풍선은 그 주 까닭 전부와 합이다. 꼬리표 없는 근거 있는 주는
    작은 표지만 (「+N일」 글 없음)이고, 목표 이름은 선 아래 · 끝 값 글은 점 오른쪽 위다."""
    figure = weekly_figure(_log(), _changes(), label=_label).to_plotly_json()
    layout = _weekly_layout(_log(), _changes(), _label)
    line = figure["data"][0]
    for position in range(1, len(RECORDS)):
        if position in layout.placed:
            up = layout.placed[position].up
            assert line["marker"]["symbol"][position] == ("triangle-up" if up else "triangle-down")
            assert line["marker"]["size"][position] == 17
    assert line["marker"]["symbol"][3] == "triangle-up" and line["marker"]["size"][3] == 12
    assert not any(trace.get("mode") == "text" for trace in figure["data"]), (
        "근거 있는 주는 「+N일」 없음"
    )
    thick = [trace for trace in figure["data"] if trace.get("line", {}).get("width") == 3.6]
    assert len(thick) == 1
    rises = sorted(position for position, tag in layout.placed.items() if tag.up)
    expected: list[int | None] = []
    for position in rises:
        expected += [layout.xs[position - 1], layout.xs[position], None]
    assert list(thick[0]["x"]) == expected

    notes = {note["text"]: note for note in figure["layout"]["annotations"]}
    tag_texts = [text for text in notes if "▲ +15일" in text]
    assert len(tag_texts) == 1 and "DEMO 본딩 Qual 밀림 2대" in tag_texts[0]
    w43 = line["hovertext"][5]
    assert "26-W43 · 224일 · 지난 기록 대비 +15일" in w43
    assert "▲ DEMO 본딩 Qual 밀림 2대 +11일" in w43 and "▲ PRC-09 신규 필요 1대 +4일" in w43
    assert "합 +15일 = 지난 기록 대비 +15일" in w43
    assert notes[tag_texts[0]]["hovertext"] == w43
    goal_note = next(note for text, note in notes.items() if text.startswith("최종 목표"))
    assert goal_note["yanchor"] == "top"
    end_note = next(note for text, note in notes.items() if "(26-W48)" in text)
    assert (end_note["xanchor"], end_note["yanchor"]) == ("left", "bottom")
    assert figure["layout"]["yaxis"]["range"][0] > 0


def test_an_other_bucket_that_nets_to_zero_has_no_up_or_down_mark() -> None:
    """풍선 「그 밖」 묶음의 합이 0일이면 ▲ · ▼ 를 붙이지 않는다(UI-ACC-03 · UI-DAT-05 — ▼ 는
    줄어듦 표지다). 항목 일곱 가운데 여섯째 · 일곱째가 +3일 · −3일인 주다."""
    rows = [
        ("PRC-01", TAG_QUAL_LATER, 10),
        ("PRC-02", TAG_QUAL_LATER, 8),
        ("PRC-03", TAG_NEW, 6),
        ("PRC-04", TAG_NEED_EARLIER, 4),
        ("PRC-05", TAG_QUAL_LATER, 2),
        ("PRC-06", TAG_QUAL_LATER, 3),
        ("PRC-07", TAG_QUAL_EARLIER, -3),
    ]
    items = tuple(ReasonItem(tag, days, units=1, process=process) for process, tag, days in rows)
    change = sum(days for _, _, days in rows)
    week = WEEKS[1]
    reason = WeekChange(week, WEEKS[0], change, items, balanced=True)
    figure = weekly_figure(_log([200, 200 + change], goal=None), {week: reason}).to_plotly_json()
    lines = figure["data"][0]["hovertext"][1].split("<br>")
    assert "그 밖 2건 0일" in lines, lines
    assert lines[1].startswith("▲ PRC-01 Qual 밀림 1대 +10일"), lines


def test_weeks_without_reasons_keep_the_old_marks_and_say_why_on_hover() -> None:
    """근거 없는 주(넣기 스냅숏이 없음)는 늘어난 주 ▲ 와 「+N일」 · 줄어든 주 ● 이고, 풍선은
    까닭 근거가 없다고 말한다. 까닭 합이 맞지 않는 주는 꼬리표 없이 풍선이 그 사실을 말한다."""
    changes = _changes()
    broken = changes[WEEKS[5]]
    changes[WEEKS[5]] = WeekChange(broken.week, broken.previous, broken.change, broken.items[:1],
                                   balanced=False)  # fmt: skip
    del changes[WEEKS[8]]
    figure = weekly_figure(_log(), changes, label=_label).to_plotly_json()
    line = figure["data"][0]
    assert line["marker"]["symbol"][5] == "triangle-up" and line["marker"]["size"][5] == 12
    assert line["marker"]["symbol"][8] == "triangle-up" and line["marker"]["size"][8] == 12
    (plain,) = [trace for trace in figure["data"] if trace.get("mode") == "text"]
    assert list(plain["text"]) == ["+15일", "+6일"]
    assert "까닭 근거가 지난 기록 대비와 맞지 않아 싣지 않습니다" in line["hovertext"][5]
    assert "까닭 근거 없음" in line["hovertext"][8]
    assert not any("▲ +15일" in note["text"] for note in figure["layout"]["annotations"])
