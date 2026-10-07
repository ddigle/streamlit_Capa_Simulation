# Purpose: 입장 화면 Summary 토글 셋의 값이 HOME 의 같은 토글과 같은 계산·형식인지 검증한다.

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import duckdb
import pandas as pd
import pytest

from capa_simulation.components import intro_summary
from capa_simulation.services.advance_load import (
    apply_advance_to_density,
    apply_advance_to_securement,
    apply_advance_to_wafer,
    build_advance_load_ratio,
    revert_advance_from_securement,
)
from capa_simulation.services.advance_shipment import advance_shipment_notes
from capa_simulation.services.dashboard import (
    build_monthly_bottleneck_ranking,
    build_monthly_bottlenecks_from_ranking,
    build_production_lob_summary,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.official_summary import (
    OfficialSummary,
    build_advance_summary,
    build_comparison_summary,
    build_official_summary,
)
from capa_simulation.services.plan_gap import (
    DENSITY_GAP_FORMAT,
    GAP_EPSILON,
    WAFER_GAP_FORMAT,
    WAFER_GAP_SCALE,
    format_gap,
    plan_gap_texts,
    visible_gap,
)
from capa_simulation.services.securement_threshold import SecurementThresholds

MONTHS = [202610, 202611, 202612, 202701, 202702, 202703]
LABELS = [month_label(month) for month in MONTHS]
INCLUDED = ["P-A", "P-B"]
THRESHOLDS = SecurementThresholds(1.095, 0.995)


def _density() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "년월": LABELS,
            "부하량": [14.97, 15.24, 14.8, 14.33, 0.5, 15.42],
        }
    )


def _wafer() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "년월": LABELS,
            "Wafer 부하량": [211000.0, 215000, 209000, 202000, 9000, 214000],
        }
    )


def _securement() -> pd.DataFrame:
    rows = []
    for index, month in enumerate(MONTHS):
        rows.append((month, "P-A", 0.98 + index * 0.01, 32.0, 33.0))
        rows.append((month, "P-B", 1.2 - index * 0.04, 50.0, 41.0))
    return pd.DataFrame(rows, columns=["생산계획년월", "공정", "확보율", "가용대수", "소요대수"])


def _volume() -> pd.DataFrame:
    rows = [(month, "PROD-A", 100.0, 500.0, False) for month in MONTHS]
    return pd.DataFrame(
        rows, columns=["생산계획년월", "제품정보", "Wafer 부하량", "생산수량", "과거"]
    )


def _summary() -> OfficialSummary:
    return build_official_summary(
        months=MONTHS,
        monthly_density=_density(),
        monthly_wafer=_wafer(),
        securement_rate=_securement(),
        product_volume=_volume(),
        slot_volume=_volume(),
        display_order=None,
        included_processes=INCLUDED,
    )


# 202612 에 +3 · 202701 에 -1.5 · 202702 는 계획(0.5)보다 큰 -2 라 반영하지 못한다 · 기간 밖 202801.
ADVANCE_ROWS = pd.DataFrame(
    {"생산계획년월": [202612, 202701, 202702, 202801], "선행 물량": [3.0, -1.5, -2.0, 4.0]}
)


def _home_advance_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """HOME 이 「선행 B/O」를 켰을 때 `Capa LOB 현황` 이 쓰는 프레임(`app_pages/home.py` 차례)."""
    ratio = build_advance_load_ratio(_density(), ADVANCE_ROWS)
    density = apply_advance_to_density(_density(), ratio)
    wafer = apply_advance_to_wafer(_wafer(), ratio)
    securement = apply_advance_to_securement(_securement(), ratio)
    bottlenecks = build_monthly_bottlenecks_from_ranking(
        build_monthly_bottleneck_ranking(securement, INCLUDED)
    )
    lob_summary = build_production_lob_summary(density, wafer, bottlenecks)
    baseline = build_production_lob_summary(
        _density(), _wafer(), revert_advance_from_securement(bottlenecks, ratio)
    )
    return lob_summary, baseline, bottlenecks


def test_advance_values_come_from_the_same_functions_as_home() -> None:
    """같은 달·같은 입력에서 HOME 「선행 B/O」의 Density·Wafer·B/N 확보율·증감 글자와 같다."""
    base = _summary()
    advance = build_advance_summary(
        months=MONTHS,
        monthly_density=_density(),
        monthly_wafer=_wafer(),
        securement_rate=_securement(),
        included_processes=INCLUDED,
        advance_rows=ADVANCE_ROWS,
        base=base,
    )
    lob_summary, baseline, bottlenecks = _home_advance_frames()

    assert list(advance.density) == pytest.approx(list(lob_summary["부하량"]))
    assert list(advance.wafer) == pytest.approx(list(lob_summary["Wafer 부하량"]))
    rates = [month.rate if month else None for month in advance.bottlenecks]
    assert rates == pytest.approx(list(bottlenecks["확보율"]))
    # 공정은 바뀌지 않는다(한 달 안의 모든 공정에 같은 수를 곱한다). 소요·가용대수도 HOME 처럼
    # 그대로다.
    assert [m.process for m in advance.bottlenecks if m] == [
        m.process for m in base.bottlenecks if m
    ]
    assert [m.short_units for m in advance.bottlenecks if m] == [
        m.short_units for m in base.bottlenecks if m
    ]
    # 증감 글자는 HOME 이 값 위에 적는 것과 같은 함수·형식이다.
    home_density = plan_gap_texts(lob_summary, baseline, "부하량", DENSITY_GAP_FORMAT)
    home_wafer = plan_gap_texts(
        lob_summary, baseline, "Wafer 부하량", WAFER_GAP_FORMAT, scale=WAFER_GAP_SCALE
    )
    assert list(advance.density_delta) == home_density
    assert list(advance.wafer_delta) == home_wafer
    assert advance.density_delta[2] == "+3.00" and advance.density_delta[3] == "-1.50"
    # HOME B/N 막대 안 증감과 같은 글자(`{:+.0f}%`).
    third = base.bottlenecks[2]
    assert third is not None and advance.bottlenecks[2] is not None
    expected = f"{(advance.bottlenecks[2].rate - third.rate) * 100:+.0f}%"
    assert advance.rate_delta[2] == expected and advance.rate_delta[0] == ""
    # 계획이 0 이하가 되는 달은 반영하지 못한다(HOME 경고와 같은 규칙). 기간 밖 입력은 보지 않는다.
    assert advance.applied == (202612, 202701)
    assert advance.unapplied == (202702,)


def test_the_advance_payload_judges_each_month_and_keeps_the_summary_shape() -> None:
    base = _summary()
    advance = build_advance_summary(
        months=MONTHS,
        monthly_density=_density(),
        monthly_wafer=_wafer(),
        securement_rate=_securement(),
        included_processes=INCLUDED,
        advance_rows=ADVANCE_ROWS,
        base=base,
    )
    payload = intro_summary.advance_payload(
        base, advance, thresholds=THRESHOLDS, process_label=lambda process: process
    )
    plain = intro_summary.summary_payload(
        base,
        release_name="공식 v1",
        scenario_name="DEMO",
        thresholds=THRESHOLDS,
        process_label=lambda process: process,
    )

    assert payload["available"] is True
    assert json.loads(json.dumps(payload)) == payload
    # 요약과 같은 반올림·같은 모양이라 JS 가 달마다 그 사이를 잇는다.
    assert len(payload["density"]) == len(plain["density"]) == len(MONTHS)
    assert set(payload["bn"][2]) == set(plain["bn"][2])
    assert payload["density"][2] == pytest.approx(round(14.8 + 3.0, 2))
    assert payload["bn"][2]["status"] == THRESHOLDS.status(advance.bottlenecks[2].rate, 202612)  # type: ignore[union-attr]
    assert payload["unapplied"] == ["27.02"]


def test_advance_without_an_applied_month_is_off_with_a_reason() -> None:
    base = _summary()
    for rows, reason in (
        (
            pd.DataFrame({"생산계획년월": [202801], "선행 물량": [1.0]}),
            intro_summary.ADVANCE_OFF_EMPTY,
        ),
        (
            pd.DataFrame({"생산계획년월": [202702], "선행 물량": [-5.0]}),
            intro_summary.ADVANCE_OFF_UNAPPLICABLE,
        ),
    ):
        advance = build_advance_summary(
            months=MONTHS,
            monthly_density=_density(),
            monthly_wafer=_wafer(),
            securement_rate=_securement(),
            included_processes=INCLUDED,
            advance_rows=rows,
            base=base,
        )
        payload = intro_summary.advance_payload(
            base, advance, thresholds=THRESHOLDS, process_label=str
        )
        assert payload == {"available": False, "reason": reason}


def _comparison_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    # 202703 은 비교 시나리오에 없다. 202611 은 같은 값이라 GAP 을 적지 않는다.
    months = MONTHS[:5]
    density = pd.DataFrame(
        {
            "생산계획년월": months,
            "년월": [month_label(month) for month in months],
            "부하량": [14.0, 15.24, 15.8, 14.33 - 1e-4, 1.5],
        }
    )
    wafer = pd.DataFrame(
        {
            "생산계획년월": months,
            "년월": [month_label(month) for month in months],
            "Wafer 부하량": [200000.0, 215030, 219000, 202000, 9000],
        }
    )
    return density, wafer


def test_gap_is_the_raw_plan_minus_the_comparison_like_home() -> None:
    """HOME 은 GAP 을 선행 **전** 요약에서 잰다(`build_lob_summary_figures` 의 `raw_summary`)."""
    base = _summary()
    comparison_density, comparison_wafer = _comparison_frames()
    comparison = build_comparison_summary(
        months=MONTHS,
        base=base,
        comparison_density=comparison_density,
        comparison_wafer=comparison_wafer,
    )
    # HOME 의 같은 계산: 월 축 라벨로 맞춘 원 요약과 비교 표의 차이.
    raw = build_production_lob_summary(
        _density(),
        _wafer(),
        pd.DataFrame({"생산계획년월": MONTHS, "확보율": [1.0] * len(MONTHS)}),
    ).set_index("년월")
    aligned_density = comparison_density.set_index("년월").reindex(LABELS)
    aligned_wafer = comparison_wafer.set_index("년월").reindex(LABELS)
    home_density = plan_gap_texts(raw, aligned_density, "부하량", DENSITY_GAP_FORMAT)
    home_wafer = plan_gap_texts(
        raw, aligned_wafer, "Wafer 부하량", WAFER_GAP_FORMAT, scale=WAFER_GAP_SCALE
    )

    assert list(comparison.density_gap) == home_density
    assert list(comparison.wafer_gap) == home_wafer
    assert comparison.density_gap[0] == "+0.97" and comparison.density_gap[2] == "-1.00"
    # 0 으로 보이는 차이(1e-4 억Gb, 30 매)와 비교 쪽에 없는 달은 적지 않는다.
    assert comparison.density_gap[3] == "" and comparison.wafer_gap[1] == ""
    assert comparison.density[-1] is None and comparison.density_gap[-1] == ""
    payload = intro_summary.comparison_payload(comparison, name="DEMO r3")
    assert payload["available"] is True and payload["name"] == "DEMO r3"
    assert payload["wafer"][0] == pytest.approx(200.0)


def test_gap_without_any_comparison_month_is_off() -> None:
    base = _summary()
    empty = pd.DataFrame({"생산계획년월": [202801], "년월": ["28.01"], "부하량": [1.0]})
    empty_wafer = empty.rename(columns={"부하량": "Wafer 부하량"})
    comparison = build_comparison_summary(
        months=MONTHS, base=base, comparison_density=empty, comparison_wafer=empty_wafer
    )
    assert not comparison.covered
    assert intro_summary.comparison_payload(comparison, name="x") == {
        "available": False,
        "reason": intro_summary.COMPARISON_OFF_UNCOVERED,
    }


def test_shipment_notes_are_home_corner_notes() -> None:
    rows = pd.DataFrame(
        {"생산계획년월": [202611, 202701, 202702, 202801], "선행 입고": [1.234, 0.04, -0.5, 9.0]}
    )
    notes = [text for text, _hover in advance_shipment_notes(rows, LABELS)]
    payload = intro_summary.shipment_payload(notes)

    assert payload == {"available": True, "notes": ["", "+1.2", "", "", "-0.5", ""]}
    # 0 으로 보이는 값(`+0.0`)만 남았거나 기간에 입력이 없으면 끈다.
    only_zero = pd.DataFrame({"생산계획년월": [202701], "선행 입고": [0.04]})
    assert intro_summary.shipment_payload(
        [text for text, _hover in advance_shipment_notes(only_zero, LABELS)]
    ) == {"available": False, "reason": intro_summary.SHIPMENT_OFF_EMPTY}


def test_gap_text_rules_are_shared_with_home() -> None:
    """HOME `home_lob_figures` 와 Summary 가 같은 형식·숨김 규칙을 쓴다(같은 모듈)."""
    from capa_simulation.components import home_lob_figures

    assert vars(home_lob_figures)["plan_gap_texts"] is plan_gap_texts
    assert vars(home_lob_figures)["GAP_EPSILON"] is GAP_EPSILON
    assert format_gap(0.004, DENSITY_GAP_FORMAT) == ""
    assert format_gap(-0.006, DENSITY_GAP_FORMAT) == "-0.01"
    assert format_gap(40.0, WAFER_GAP_FORMAT, scale=WAFER_GAP_SCALE) == ""
    assert format_gap(60.0, WAFER_GAP_FORMAT, scale=WAFER_GAP_SCALE) == "+0.1K"
    assert format_gap(None, DENSITY_GAP_FORMAT) == ""
    assert visible_gap("-0.00") == ""


# --------------------------------------------------------------- 비교 대상 확인과 비활성 까닭


class _Repo:
    def __init__(self, revisions: list[str], *, fail: Exception | None = None) -> None:
        self.revisions = revisions
        self.fail = fail
        self.calls = 0

    def list_revisions(self, scenario_id: str) -> list[SimpleNamespace]:
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        return [
            SimpleNamespace(revision_id=revision, revision_no=index + 1)
            for index, revision in enumerate(self.revisions)
        ]

    def list_scenarios(self, *, include_archived: bool = False) -> list[SimpleNamespace]:
        return [SimpleNamespace(scenario_id="S-CMP", scenario_name="DEMO 비교")]


def _profile(scenario_id: str | None, revision_id: str | None) -> SimpleNamespace:
    return SimpleNamespace(version=3, scenario_id=scenario_id, revision_id=revision_id)


def _part(monkeypatch: pytest.MonkeyPatch, repo: _Repo, profile: SimpleNamespace) -> dict[str, Any]:
    monkeypatch.setattr(intro_summary, "get_scenario_repository", lambda path: repo)
    release = SimpleNamespace(revision_id="R-OFFICIAL")
    return intro_summary.comparison_part(
        "db",
        release,  # type: ignore[arg-type]
        profile,  # type: ignore[arg-type]
        summary=_summary(),
        load_plan=lambda revision_id: _comparison_frames(),
    )


def test_gap_is_off_when_there_is_nothing_to_compare(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _Repo(["R-1", "R-2"])
    cases = {
        intro_summary.COMPARISON_OFF_NONE: _profile(None, None),
        intro_summary.COMPARISON_OFF_SELF: _profile("S-CMP", "R-OFFICIAL"),
        intro_summary.COMPARISON_OFF_MISSING: _profile("S-CMP", "R-GONE"),
    }
    for reason, profile in cases.items():
        assert _part(monkeypatch, repo, profile) == {"available": False, "reason": reason}
    # 비교 대상이 없거나 공식버전 자신이면 DB 를 보지 않는다.
    assert repo.calls == 1
    ready = _part(monkeypatch, repo, _profile("S-CMP", "R-2"))
    assert ready["available"] is True and ready["name"] == "DEMO 비교 r2"


def test_a_db_failure_while_checking_the_comparison_is_not_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DB 잠금으로 GAP 을 끈 결과가 서버 캐시에 남으면 다음 확인 때도 GAP 이 꺼져 있다 — 올린다."""
    repo = _Repo([], fail=duckdb.IOException("잠김"))
    with pytest.raises(duckdb.IOException):
        intro_summary._guarded("GAP", lambda: _part(monkeypatch, repo, _profile("S-CMP", "R-1")))


def test_a_data_error_turns_off_only_that_toggle() -> None:
    def broken() -> dict[str, Any]:
        raise ValueError("선행 물량 모양")

    payload = intro_summary._guarded("선행 B/O", broken)
    assert payload["available"] is False
    assert payload["reason"].startswith("선행 B/O 값을 만들지 못했습니다: ValueError")
