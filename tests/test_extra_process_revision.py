# Purpose: 「이 리비전 값을 새 판으로」 의 거꾸로 만들기 — 값 겹치기 · 기간 접기 · 옮기지 못한
# 공정 · 경로 다름 · 누를 수 없는 까닭과 판 → 리비전 → 고침 → 새 판 → 다시 합침 왕복을 본다.

"""거꾸로 만들기(`services/extra_process_revision.py` — 설계 3-5 · A15).

견본 판을 내장 합성 시드(2026년 12달)에 합친 표를 「리비전」 으로 보고 칸을 고친 뒤 새 판을 만든다.
바탕 판 줄에서 시작하므로 고치지 않은 리비전은 바뀐 칸이 0 이고, 고친 달만 쪼개지며 열린 끝은 열린
채다. 새 판을 같은 시드에 다시 합치면 고친 값이 그대로 나와야 한다(왕복).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
import pytest
from extra_process_fixtures import AOI, BOND, template_files

from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.extra_process_merge import (
    MIXED_REASON,
    OUTCOME_DROPPED,
    OUTCOME_MERGED,
    ActiveExtraPack,
    ExtraPackVersion,
    merge_extra_processes,
)
from capa_simulation.services.extra_process_pack import (
    BOTH_CLASSES,
    ENGINEERING,
    MASS,
    ExtraProcessPack,
    Period,
    pack_changes,
    read_pack_files,
)
from capa_simulation.services.extra_process_revision import (
    AVAILABLE_REASON,
    SPLIT_PRODUCTS_REASON,
    RevisionPack,
    merged_processes,
    pack_from_revision,
    revision_refusal,
)

Tables = dict[str, pd.DataFrame]
VERSION = ExtraPackVersion(1, 1, "")


def _base() -> ExtraProcessPack:
    reading = read_pack_files(template_files())
    assert reading.pack is not None
    return reading.pack


def _revision() -> Tables:
    seed = {
        name: frame.copy() for name, frame in build_builtin_seed_dataset().reference_tables.items()
    }
    base = _base()
    version = ExtraPackVersion(1, 1, base.sha256)
    return merge_extra_processes(
        seed, ActiveExtraPack(version, base), check=lambda _tables: None
    ).tables


def _edit(
    tables: Tables,
    name: str,
    column: str,
    value: float,
    where: Callable[[pd.DataFrame], pd.Series],
) -> Tables:
    copy = {key: frame.copy() for key, frame in tables.items()}
    frame = copy[name]
    frame.loc[where(frame), column] = value
    return copy


def _process(name: str) -> Callable[[pd.DataFrame], pd.Series]:
    return lambda frame: frame["공정"].eq(name)


def _month(name: str, month: int) -> Callable[[pd.DataFrame], pd.Series]:
    return lambda frame: frame["공정"].eq(name) & frame["생산계획년월"].eq(month)


def _build(tables: Tables) -> RevisionPack:
    base = _base()
    return pack_from_revision(
        base,
        tables,
        (BOND, AOI),
        version=ExtraPackVersion(1, 1, base.sha256),
        version_no=2,
        written_at="2026-11-19T01:00:00+09:00",
        memo="앱 — DEMO r2 에서",
    )


def test_an_unedited_revision_gives_the_same_values_with_a_new_version_number() -> None:
    result = _build(_revision())

    assert result.reading.pack is not None, [item.text() for item in result.reading.problems]
    pack = result.reading.pack
    assert pack.info.version_no == 2
    assert pack.info.memo == "앱 — DEMO r2 에서"
    assert pack.info.author == ""
    assert pack_changes(pack, _base()).changed_cells == 0
    assert result.moved == (BOND, AOI)
    assert result.kept == () and result.route_differs == ()


def test_an_edited_month_splits_only_that_row_and_keeps_the_open_end() -> None:
    tables = _edit(_revision(), "RQ_UPEH", "UPEH", 60000.0, _month(BOND, 202609))

    pack = _build(tables).reading.pack

    assert pack is not None
    bond = [(row.period, row.upeh) for row in pack.productivity if row.process == BOND]
    assert bond == [
        (Period(202601, 202606), 54000.0),
        (Period(202607, 202608), 58000.0),
        (Period(202609, 202609), 60000.0),
        (Period(202610, None), 58000.0),
    ]
    assert all(row.mass_class == BOTH_CLASSES for row in pack.productivity if row.process == BOND)
    assert pack_changes(pack, _base()).changed_cells > 0


def test_an_edit_on_the_last_revision_month_keeps_later_months_on_the_base_value() -> None:
    tables = _edit(_revision(), "RQ_UPEH", "UPEH", 61000.0, _month(BOND, 202612))

    pack = _build(tables).reading.pack

    assert pack is not None
    bond = [(row.period, row.upeh) for row in pack.productivity if row.process == BOND]
    assert bond[-2:] == [(Period(202612, 202612), 61000.0), (Period(202701, None), 58000.0)]


def test_a_class_edited_alone_splits_a_both_row_into_mass_and_er() -> None:
    def er_only(frame: pd.DataFrame) -> pd.Series:
        return frame["공정"].eq(BOND) & frame["양산구분"].eq(ENGINEERING)

    tables = _edit(_revision(), "RQ_RUN_RATE", "CAPA_RUN_RATE", 0.7, er_only)

    pack = _build(tables).reading.pack

    assert pack is not None
    rates = {
        (row.mass_class, row.period.start, row.period.end): row.run_rate
        for row in pack.rate_vital
        if row.process == BOND
    }
    assert rates[(MASS, 202601, 202612)] == 0.85
    assert rates[(ENGINEERING, 202601, 202612)] == 0.7
    assert rates[(BOTH_CLASSES, 202701, None)] == 0.85


def test_blank_ratios_lent_and_calendar_days_keep_their_file_spelling() -> None:
    result = _build(_revision())

    pack = result.reading.pack
    assert pack is not None
    aoi = [row for row in pack.productivity if row.process == AOI]
    assert all(row.wf_ratio is None for row in aoi)
    assert all(row.run_day is None for row in pack.equipment)


def test_an_edited_run_day_equal_to_the_month_length_is_written_as_calendar() -> None:
    tables = _edit(_revision(), "RQ_RUN_DAY", "RUN_DAY", 20, _month(AOI, 202605))

    pack = _build(tables).reading.pack

    assert pack is not None
    aoi = [(row.period, row.run_day) for row in pack.equipment if row.process == AOI]
    assert aoi == [
        (Period(202603, 202604), None),
        (Period(202605, 202605), 20),
        (Period(202606, None), None),
    ]


def test_split_product_values_on_a_follow_route_keep_the_process_on_the_base() -> None:
    # 시드에서 따라가는 제품은 양산구분마다 하나라, 같은 양산구분의 다른 제품 줄을 하나 더해
    # 제품마다 값이 갈린 리비전을 만든다.
    tables = _revision()
    upeh = tables["RQ_UPEH"]
    other = upeh.loc[upeh["공정"].eq(BOND) & upeh["제품정보"].eq("DEMO PRODUCT A")].assign(
        제품정보="DEMO PRODUCT C", UPEH=70000.0
    )
    tables["RQ_UPEH"] = pd.concat([upeh, other], ignore_index=True)

    result = _build(tables)

    assert [(item.process, item.reason) for item in result.kept] == [(BOND, SPLIT_PRODUCTS_REASON)]
    assert result.moved == (AOI,)
    assert result.reading.pack is not None
    assert pack_changes(result.reading.pack, _base()).changed_cells == 0


def test_an_available_count_edited_apart_from_owned_and_lent_is_not_moved() -> None:
    tables = _edit(_revision(), "RQ_EQP_AVBL", "가용대수", 1.0, _month(AOI, 202604))

    result = _build(tables)

    assert [(item.process, item.reason) for item in result.kept] == [(AOI, AVAILABLE_REASON)]


def test_owned_edited_with_its_available_count_moves() -> None:
    tables = _edit(_revision(), "RQ_EQP_OWN", "설비보유", 5.0, _month(AOI, 202604))
    tables = _edit(tables, "RQ_EQP_AVBL", "가용대수", 4.5, _month(AOI, 202604))

    pack = _build(tables).reading.pack

    assert pack is not None
    owned = [(row.period, row.owned) for row in pack.equipment if row.process == AOI]
    assert (Period(202604, 202604), 5.0) in owned


def test_a_step_added_in_the_app_is_counted_and_not_moved() -> None:
    tables = _revision()
    reqb = tables["RQ_REQB"]
    added = reqb.loc[reqb["공정"].eq(BOND)].assign(STEP_SEQ="DEMO-P999")
    tables["RQ_REQB"] = pd.concat([reqb, added], ignore_index=True)

    result = _build(tables)

    assert result.route_differs == (BOND,)
    assert result.reading.pack is not None
    steps = {row.step for row in result.reading.pack.productivity if row.process == BOND}
    assert steps == {"DEMO-P150"}


def test_the_new_pack_merges_back_to_the_edited_values() -> None:
    """왕복(설계 9-2 기준) — 두 공정(따라가기 꼴 · 지정 꼴) × 값 표 열 모두를 고친 리비전으로 새
    판을 만들어 같은 시드에 다시 합치면 고친 값이 그대로 나온다(`모두` 쪼개기 · 달력 · 대여 · 측정률
    0 포함)."""

    def er(name: str) -> Callable[[pd.DataFrame], pd.Series]:
        return lambda frame: frame["공정"].eq(name) & frame["양산구분"].eq(ENGINEERING)

    def mass_month(name: str, month: int) -> Callable[[pd.DataFrame], pd.Series]:
        return lambda frame: (
            frame["공정"].eq(name) & frame["생산계획년월"].eq(month) & frame["양산구분"].eq(MASS)
        )

    tables = _edit(_revision(), "RQ_UPEH", "UPEH", 60000.0, _month(BOND, 202609))
    tables = _edit(tables, "RQ_WF_RATIO", "WF측정률", 0.95, _month(BOND, 202603))
    tables = _edit(tables, "RQ_RUN_RATE", "CAPA_RUN_RATE", 0.7, er(BOND))
    tables = _edit(tables, "RQ_VITAL", "편중률", 1.1, mass_month(AOI, 202608))
    tables = _edit(tables, "RQ_UPEH", "ST", 2.0, _month(AOI, 202607))
    tables = _edit(tables, "RQ_LOT_RATIO", "Lot 측정률", 0.0, _month(AOI, 202609))
    tables = _edit(tables, "RQ_EQP_LENT", "설비대여평가", 1.0, _month(AOI, 202605))
    tables = _edit(tables, "RQ_EQP_AVBL", "가용대수", 2.0, _month(AOI, 202605))
    tables = _edit(tables, "RQ_EQP_OWN", "설비보유", 9.0, _month(BOND, 202610))
    tables = _edit(tables, "RQ_EQP_AVBL", "가용대수", 9.0, _month(BOND, 202610))
    tables = _edit(tables, "RQ_RUN_DAY", "RUN_DAY", 25, _month(BOND, 202611))

    result = _build(tables)
    pack = result.reading.pack
    assert pack is not None, [item.text() for item in result.reading.problems]
    assert result.moved == (BOND, AOI) and result.kept == ()
    seed = {
        name: frame.copy() for name, frame in build_builtin_seed_dataset().reference_tables.items()
    }
    again = merge_extra_processes(
        seed, ActiveExtraPack(ExtraPackVersion(2, 2, pack.sha256), pack), check=lambda _t: None
    ).tables

    for name, values in _VALUES.items():
        keys = [column for column in tables[name].columns if column not in values]
        for process in (BOND, AOI):
            left = tables[name].loc[tables[name]["공정"].eq(process)].sort_values(keys)
            right = again[name].loc[again[name]["공정"].eq(process)].sort_values(keys)
            pd.testing.assert_frame_equal(
                left.reset_index(drop=True),
                right.reset_index(drop=True),
                check_dtype=False,
                obj=f"{name} {process}",
            )


_VALUES = {
    "RQ_UPEH": ("UPEH", "ST"),
    "RQ_LOT_RATIO": ("Lot 측정률",),
    "RQ_WF_RATIO": ("WF측정률",),
    "RQ_RUN_RATE": ("CAPA_RUN_RATE",),
    "RQ_VITAL": ("편중률",),
    "RQ_RUN_DAY": ("RUN_DAY",),
    "RQ_EQP_OWN": ("설비보유",),
    "RQ_EQP_LENT": ("설비대여평가",),
    "RQ_EQP_AVBL": ("가용대수",),
    "RQ_MODULE": ("모듈수",),
}


@dataclass(frozen=True)
class _Record:
    process_name: str
    version_no: int
    sha256: str
    outcome: str
    reason: str | None = None
    note: str | None = None


def test_refusal_reasons_follow_the_design_order() -> None:
    merged = _Record(BOND, 1, "a" * 64, OUTCOME_MERGED)

    def refusal(*records: _Record, off: bool = False, sha: str | None = "a" * 64) -> str | None:
        return revision_refusal(off=off, active_sha=sha, active_version_no=3, records=list(records))

    assert refusal(merged) is None
    assert refusal(merged, off=True) is not None and "다시 켜기" in str(refusal(merged, off=True))
    # 판 이력이 아예 없음(끈 것이 아님) — 「다시 켜기」 단추가 서지 않으므로 그것을 시키지 않는다.
    assert refusal(sha=None) == "적용한 부대공정 판이 없습니다"
    assert "합친 부대공정이 없습니다" in str(refusal(_Record(BOND, 1, "a" * 64, OUTCOME_DROPPED)))
    mixed = _Record(AOI, 1, "a" * 64, OUTCOME_DROPPED, reason=MIXED_REASON)
    assert "섞인" in str(refusal(merged, mixed))
    other = _Record(AOI, 2, "b" * 64, OUTCOME_MERGED)
    assert "섞인" in str(refusal(merged, other))
    shifted = _Record(BOND, 1, "a" * 64, OUTCOME_MERGED, note="연도 Shift +1년")
    assert "연도 Shift" in str(refusal(shifted))
    # 판은 sha 로 견준다 — 끄기 → 다시 켜기로 판 이력 차례가 달라져도 같은 판이다.
    assert "판 1로 만든 리비전" in str(refusal(merged, sha="c" * 64))
    assert merged_processes([merged, mixed, other]) == (BOND, AOI)


@pytest.mark.parametrize(
    ("version_no", "expected"),
    [
        (1, "판 1로 만든 리비전입니다 — 활성 판 1로 얹거나"),
        (2, "판 2로 만든 리비전입니다 — 활성 판 2로 얹거나"),
        (3, "판 3으로 만든 리비전입니다 — 활성 판 3으로 얹거나"),
        (6, "판 6으로 만든 리비전입니다 — 활성 판 6으로 얹거나"),
        (10, "판 10으로 만든 리비전입니다 — 활성 판 10으로 얹거나"),
    ],
)
def test_the_other_version_refusal_picks_the_particle_by_the_number(
    version_no: int, expected: str
) -> None:
    """판 번호 뒤 「(으)로」 는 번호의 끝소리로 고른다 — 일(ㄹ) · 이는 「로」, 삼 · 육 · 십은
    「으로」."""
    merged = _Record(BOND, version_no, "a" * 64, OUTCOME_MERGED)

    refusal = revision_refusal(
        off=False, active_sha="c" * 64, active_version_no=version_no, records=[merged]
    )

    assert refusal is not None and refusal.startswith(expected), refusal
