# Purpose: 입장 화면 Summary 의 여섯 달 창(−·+ 로 옮기는 `<intro-window>` 구획)을 node 로 돌려
# 파이썬 값과 맞대 검증한다.

"""Summary 는 모든 달을 받고 브라우저가 여섯 달 창을 자른다(2026-11-02 사용자 요청(검수표) home-02).

`intro.js` 의 순수 구획 `<intro-window>` 를 node(또는 bun)로 돌린다 — 입력은 파이썬이 실제로 보내는
값 (`intro_summary.summary_payload` 와 토글 몫 셋)이다. node 가 없는 PC 에서는 bun 으로 돌고, 둘 다
없으면 건너뛴다 — GitHub Actions 에서는 건너뛰지 않고 실패한다(`test_intro_scene_behavior` 와 같은
규칙).
"""

from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd
from js_runner import run_js_json

from capa_simulation.components import intro_summary
from capa_simulation.components.intro_overlay import _ASSETS
from capa_simulation.services.advance_shipment import advance_shipment_notes
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.official_summary import (
    build_advance_summary,
    build_comparison_summary,
    build_official_summary,
    summary_months,
)
from capa_simulation.services.securement_threshold import SecurementThresholds

# 아홉 달 — 창(6)보다 길어 옮길 자리가 셋이다. 제품은 셋이라 달 수와도 창과도 다르다(목록 길이로 달
# 목록을 가려내는 맞대기가 제품 목록을 달 목록으로 잘못 읽지 않게).
MONTHS = summary_months(202608, 202704)
LABELS = [month_label(month) for month in MONTHS]
INCLUDED = ["P-A", "P-B"]
THRESHOLDS = SecurementThresholds(1.095, 0.995)


def _block() -> str:
    js = (_ASSETS / "intro.js").read_text(encoding="utf-8")
    match = re.search(r"// <intro-window>\n(?P<body>.*?)\n// </intro-window>", js, re.S)
    assert match, "intro.js 에 // <intro-window> 구획이 없습니다"
    return match.group("body")


def _run(script: str, data: Any) -> Any:
    return run_js_json(
        f"{_block()}\nconst DATA = {json.dumps(data)};\n{script}", what="Summary 창 구획 시험"
    )


def _payload() -> dict[str, Any]:
    """파이썬이 보내는 값 그대로 — 요약 + 토글 몫 셋. PROD-OLD 는 앞 두 달에만 있다(범례에서 빠지는
    제품)."""
    density = pd.DataFrame({"생산계획년월": MONTHS, "부하량": [10.0 + i for i in range(9)]})
    wafer = pd.DataFrame(
        {"생산계획년월": MONTHS, "Wafer 부하량": [150000.0 + 1000 * i for i in range(9)]}
    )
    rows = []
    for index, month in enumerate(MONTHS):
        rows.append((month, "P-A", 1.34 - index * 0.05, 30.0, 25.0))
        rows.append((month, "P-B", 1.6, 50.0, 31.0))
    securement = pd.DataFrame(
        rows, columns=["생산계획년월", "공정", "확보율", "가용대수", "소요대수"]
    )
    volume_rows = []
    for index, month in enumerate(MONTHS):
        volume_rows.append((month, "PROD-A", 100.0, 500.0, False))
        volume_rows.append((month, "PROD-B", 40.0, 200.0, False))
        if index < 2:
            volume_rows.append((month, "PROD-OLD", 30.0, 100.0, False))
    volume = pd.DataFrame(
        volume_rows, columns=["생산계획년월", "제품정보", "Wafer 부하량", "생산수량", "과거"]
    )
    summary = build_official_summary(
        months=MONTHS,
        monthly_density=density,
        monthly_wafer=wafer,
        securement_rate=securement,
        product_volume=volume,
        slot_volume=volume,
        display_order=None,
        included_processes=INCLUDED,
        thresholds=THRESHOLDS,
        past_months={202608},
    )
    payload = intro_summary.summary_payload(
        summary,
        release_name="공식 v1",
        scenario_name="DEMO",
        thresholds=THRESHOLDS,
        process_label=str,
    )
    advance = build_advance_summary(
        months=MONTHS,
        monthly_density=density,
        monthly_wafer=wafer,
        securement_rate=securement,
        included_processes=INCLUDED,
        # 26.09 는 계획을 0 아래로 내려 걸지 못한다(`unapplied`) — 창이 26.10 부터면 빠진다.
        advance_rows=pd.DataFrame(
            {"생산계획년월": [202609, 202612, 202701], "선행 물량": [-50.0, 3.0, 3.0]}
        ),
        thresholds=THRESHOLDS,
    )
    comparison = build_comparison_summary(
        months=MONTHS,
        monthly_density=density,
        monthly_wafer=wafer,
        comparison_density=density.assign(부하량=density["부하량"] + 0.5),
        comparison_wafer=wafer.assign(**{"Wafer 부하량": wafer["Wafer 부하량"] + 2000}),
    )
    shipment = pd.DataFrame({"생산계획년월": [202701], "선행 입고": [2.0]})
    payload["toggles"] = {
        "advance": intro_summary.advance_payload(
            MONTHS, advance, thresholds=THRESHOLDS, process_label=str
        ),
        "shipment": intro_summary.shipment_payload(
            [text for text, _hover in advance_shipment_notes(shipment, LABELS)]
        ),
        "comparison": intro_summary.comparison_payload(comparison, name="DEMO 비교 r2"),
    }
    payload["start"] = 2
    sent: dict[str, Any] = json.loads(json.dumps(payload, ensure_ascii=False))
    return sent


def _month_lists(part: dict[str, Any], total: int) -> set[str]:
    return {key for key, value in part.items() if isinstance(value, list) and len(value) == total}


def test_every_monthly_list_python_sends_is_cut_by_the_window() -> None:
    """파이썬 값의 달마다 하나씩인 목록은 모두 `WINDOW_FIELDS` 에 있다 — 빠지면 창을 옮겨도 그
    목록은 처음 여섯 달을 그린다(다른 달의 값이 엇갈려 선다). 새 목록을 더하면 여기서 걸린다."""
    payload = _payload()
    fields = _run("process.stdout.write(JSON.stringify(WINDOW_FIELDS))", payload)
    total = len(MONTHS)
    assert len(payload["products"]) not in (total, 6)
    assert _month_lists(payload, total) == set(fields["summary"])
    for key in ("advance", "shipment", "comparison"):
        part = payload["toggles"][key]
        assert part["available"] is True, key
        assert _month_lists(part, total) == set(fields[key]), key


def test_a_window_is_the_six_month_summary_the_scene_drew_before() -> None:
    """창 하나는 예전 여섯 달 값과 같은 모양이다 — 달마다의 목록이 같은 자리에서 잘리고, 범위·달
    수는 창의 것이다."""
    payload = _payload()
    out = _run("process.stdout.write(JSON.stringify(windowedSummary(DATA, 2)))", payload)
    window = slice(2, 8)
    assert out["months"] == LABELS[window]
    assert (out["start"], out["total"], out["count"]) == (2, 9, 6)
    assert out["period"] == "26.10–27.03"
    for field in ("density", "wafer", "bn", "secure", "warning", "secure_label", "warning_label"):
        assert out[field] == payload[field][window], field
    assert out["past"] == [False] * 6
    assert (
        out["toggles"]["comparison"]["density_gap"]
        == (payload["toggles"]["comparison"]["density_gap"][window])
    )
    assert out["toggles"]["shipment"]["notes"] == payload["toggles"]["shipment"]["notes"][window]
    advance = out["toggles"]["advance"]
    assert advance["density"] == payload["toggles"]["advance"]["density"][window]
    # 반영하지 못한 달(26.09)은 창 밖이라 빠진다 — 첫 창(26.08~)에서는 남는다.
    assert payload["toggles"]["advance"]["unapplied"] == ["26.09"]
    assert advance["unapplied"] == []
    first = _run("process.stdout.write(JSON.stringify(windowedSummary(DATA, 0)))", payload)
    assert first["toggles"]["advance"]["unapplied"] == ["26.09"]
    assert first["past"][0] is True
    # 받은 값은 건드리지 않는다(창을 다시 잘라도 같은 값).
    assert payload == _payload()


def test_the_legend_keeps_only_products_inside_the_window_with_their_colors() -> None:
    payload = _payload()
    names = [product["name"] for product in payload["products"]]
    assert "PROD-OLD" in names
    first = _run("process.stdout.write(JSON.stringify(windowedSummary(DATA, 0)))", payload)
    later = _run("process.stdout.write(JSON.stringify(windowedSummary(DATA, 2)))", payload)
    assert [product["name"] for product in first["products"]] == names
    kept = [product for product in payload["products"] if product["name"] != "PROD-OLD"]
    assert later["products"] == kept
    # 조각의 제품 번호는 새 범례 차례를 가리키고 비중은 그대로다.
    for month_out, month_in in zip(later["mix"], payload["mix"][2:8], strict=True):
        assert [(later["products"][index]["name"], share) for index, share in month_out] == [
            (payload["products"][index]["name"], share) for index, share in month_in
        ]


def test_the_window_start_is_clamped_remembered_or_the_python_default() -> None:
    """기억한 첫 달이 있으면 그 달부터, 없거나 새 값에 없으면 파이썬 기본(`start`)이다. 끝에서는 더
    옮기지 않는다."""
    payload = _payload()
    script = """
const out = {};
out.clamp = [clampWindowStart(-3, 9, 6), clampWindowStart(2, 9, 6), clampWindowStart(7, 9, 6),
  clampWindowStart(NaN, 9, 6), clampWindowStart(4, 3, 6)];
out.start = [windowStartFor(DATA, ""), windowStartFor(DATA, "26.09"), windowStartFor(DATA, "27.04"),
  windowStartFor(DATA, "24.01"), windowStartFor({ ...DATA, start: "x" }, ""),
  windowStartFor({ ...DATA, start: 99 }, "")];
const at = (start) => windowedSummary(DATA, start);
out.shift = [shiftedWindowStart(at(0), -1, 6), shiftedWindowStart(at(0), 1, 6),
  shiftedWindowStart(at(3), 1, 6), shiftedWindowStart(at(3), -1, 6)];
out.size = [windowSize({ window: 4 }), windowSize({}), windowSize({ window: 0 })];
const short = { ...DATA, months: DATA.months.slice(0, 3), mix: DATA.mix.slice(0, 3) };
out.short = [windowStartFor(short, "26.10"), windowedSummary(short, 5).count];
process.stdout.write(JSON.stringify(out));
"""
    out = _run(script, payload)
    assert out["clamp"] == [0, 2, 3, 0, 0]
    # 기본 2 · 기억 26.09 → 1 · 27.04(마지막 달) → 끝 창 3 · 없는 달 → 기본 · 못 읽는 기본 → 0 ·
    # 넘친 기본 → 끝 창.
    assert out["start"] == [2, 1, 3, 2, 0, 3]
    assert out["shift"] == [0, 1, 3, 2]
    assert out["size"] == [4, 6, 6]
    assert out["short"] == [0, 3]


def test_unavailable_or_pending_toggles_pass_through_untouched() -> None:
    """켤 수 없거나 「준비 중」인 몫은 자를 목록이 없다 — 그대로 넘겨 토글 단추가 까닭을 그대로
    단다."""
    payload = _payload()
    payload["toggles"]["comparison"] = {
        "available": False,
        "pending": True,
        "reason": intro_summary.COMPARISON_PENDING,
    }
    payload["toggles"]["shipment"] = {"available": False, "reason": "없음"}
    out = _run("process.stdout.write(JSON.stringify(windowedSummary(DATA, 1)))", payload)
    assert out["toggles"]["comparison"] == payload["toggles"]["comparison"]
    assert out["toggles"]["shipment"] == payload["toggles"]["shipment"]
    del payload["toggles"]
    bare = _run("process.stdout.write(JSON.stringify(windowedSummary(DATA, 1)))", payload)
    assert "toggles" not in bare
