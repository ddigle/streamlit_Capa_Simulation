# Purpose: 입장 화면 장면을 node(또는 bun)로 돌려 Summary 토글 셋의 그리기 동작을 검증한다.

"""소스 문자열이 아니라 **돌려 본 결과**로 지키는 것들.

`tests/js/intro_scene_harness.mjs` 가 `intro.js` 의 `scene()` 을 가짜 캔버스로 돌리고 그리기 호출을
(이름, 인자, 그 순간 상태)로 기록한다. node 가 없는 PC 에서는 bun 으로 돌고, 둘 다 없으면 건너뛴다
(CI 러너에는 node 가 있다).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from capa_simulation.components import intro_summary
from capa_simulation.components.intro_overlay import _ASSETS
from capa_simulation.design import tokens
from capa_simulation.services.advance_shipment import advance_shipment_notes
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.official_summary import (
    build_advance_summary,
    build_comparison_summary,
    build_official_summary,
)
from capa_simulation.services.securement_threshold import SecurementThresholds

HARNESS = Path(__file__).with_name("js") / "intro_scene_harness.mjs"
MONTHS = [202610, 202611, 202612, 202701, 202702, 202703]
LABELS = [month_label(month) for month in MONTHS]
INCLUDED = ["P-A", "P-B"]
THRESHOLDS = SecurementThresholds(1.095, 0.995)


def _runtime() -> str | None:
    return shutil.which("node") or shutil.which("bun")


def _frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    density = pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "년월": LABELS,
            "부하량": [10.36, 11.05, 13.23, 14.97, 15.24, 14.8],
        }
    )
    wafer = pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "년월": LABELS,
            "Wafer 부하량": [149100.0, 160400, 187200, 211500, 215000, 209000],
        }
    )
    rows = []
    for index, month in enumerate(MONTHS):
        rows.append((month, "P-A", 1.34 - index * 0.08, 30.0, 25.0))
        rows.append((month, "P-B", 1.6, 50.0, 31.0))
    columns = ["생산계획년월", "공정", "확보율", "가용대수", "소요대수"]
    securement = pd.DataFrame(rows, columns=columns)
    return density, wafer, securement


def _payload() -> dict[str, Any]:
    density, wafer, securement = _frames()
    volume = pd.DataFrame(
        [(month, "PROD-A", 100.0, 500.0, False) for month in MONTHS],
        columns=["생산계획년월", "제품정보", "Wafer 부하량", "생산수량", "과거"],
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
        advance_rows=pd.DataFrame(
            {"생산계획년월": [202612, 202701, 202702], "선행 물량": [3.0, 3.0, -6.0]}
        ),
    )
    comparison_density = density.assign(부하량=[10.48, 11.13, 14.06, 15.34, 19.71, 16.86])
    comparison_wafer = wafer.assign(
        **{"Wafer 부하량": [150400.0, 164100, 200500, 223400, 285300, 240000]}
    )
    comparison = build_comparison_summary(
        months=MONTHS,
        monthly_density=density,
        monthly_wafer=wafer,
        comparison_density=comparison_density,
        comparison_wafer=comparison_wafer,
    )
    shipment = pd.DataFrame({"생산계획년월": [202701, 202702], "선행 입고": [2.0, 1.3]})
    payload["toggles"] = {
        "advance": intro_summary.advance_payload(
            MONTHS, advance, thresholds=THRESHOLDS, process_label=str
        ),
        "shipment": intro_summary.shipment_payload(
            [text for text, _hover in advance_shipment_notes(shipment, LABELS)]
        ),
        "comparison": intro_summary.comparison_payload(comparison, name="DEMO 비교 r2"),
    }
    return payload


@pytest.fixture(scope="module")
def scene_results(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    runtime = _runtime()
    if runtime is None:
        pytest.skip("node·bun 이 없다 — CI 에서 돈다")
    folder = tmp_path_factory.mktemp("intro-scene")
    payload_path = folder / "payload.json"
    palette_path = folder / "palette.json"
    payload_path.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")
    palette_path.write_text(json.dumps(dict(tokens.INTRO_PALETTE)), encoding="utf-8")
    completed = subprocess.run(
        [runtime, str(HARNESS), str(_ASSETS / "intro.js"), str(payload_path), str(palette_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result: dict[str, Any] = json.loads(completed.stdout.strip().splitlines()[-1])
    return result


def test_toggles_off_draw_exactly_the_summary_without_toggles(
    scene_results: dict[str, Any],
) -> None:
    """기본(셋 다 꺼짐)은 토글 값이 없던 요약과 같은 그리기다 — 조립 중에도 끝에도."""
    for at in (300, 1200, 3000):
        assert scene_results[f"off_equals_plain_{at}"] is True, at


def test_turning_everything_off_returns_to_the_same_picture(scene_results: dict[str, Any]) -> None:
    assert scene_results["back_to_base"] is True
    # 켜면 GAP(값 아래)·선행 입고(값 옆) 글자가 실제로 그려진다.
    texts = scene_results["on_texts"]
    assert "+2.0" in texts and "+1.3" in texts
    assert any(text.startswith("-") and text.endswith("K") for text in texts)


def test_pressing_again_mid_motion_continues_from_where_it_is(
    scene_results: dict[str, Any],
) -> None:
    """선행 B/O 를 끄다가 다시 켜도 점 위 값이 한 프레임에 크게 튀지 않는다(지금 값에서 이어
    간다)."""
    series = [row for row in scene_results["label_series"] if len(row) == len(MONTHS)]
    assert len(series) > 40
    for month in range(len(MONTHS)):
        values = [row[month] for row in series]
        steps = [abs(b - a) for a, b in zip(values, values[1:], strict=False)]
        # 한 달 B/O 6억Gb 를 0.6초(약 37프레임)에 옮긴다. ease-out 첫 프레임이 가장 빠르다.
        assert max(steps) < 1.2, (month, values)
    # 끄는 쪽으로 실제로 움직였다가 다시 켠 값으로 돌아온다(가운데 달 — 202612 +3).
    third = [row[2] for row in series]
    assert min(third) < third[0] and third[-1] == pytest.approx(third[0])


def test_reduced_motion_has_no_frame_loop_and_draws_on_messages(
    scene_results: dict[str, Any],
) -> None:
    """B4: 움직임을 줄였으면 프레임을 예약하지 않고, 쉬는 동안 그리지 않으며, 토글 메시지에 한 번
    그린다."""
    assert scene_results["reduce_queued"] == 0
    assert scene_results["reduce_idle_calls"] == 0
    assert scene_results["reduce_drawn_on_view"] is True
    assert scene_results["reduce_queued_after_view"] == 0


def test_narrow_windows_draw_with_every_toggle_on(scene_results: dict[str, Any]) -> None:
    for width in (390, 768, 1100):
        assert scene_results[f"narrow_{width}"] > 100, width
