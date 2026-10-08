# Purpose: 최신 공식버전의 6개월 요약을 입장 화면에 미리 보내고 사이드바 S.PKG CAPA 라벨을 세운다.

"""입장 화면 `Summary` 의 데이터와 그것을 여는 사이드바 라벨.

**선제 로딩.** 요약은 입장 화면의 로딩에 포함된다(2026-10-02 사용자 결정). `app.py` 가 공식
시나리오 부트스트랩 바로 뒤, 페이지를 그리기 **전**에 `render_intro_summary` 를 부른다. 그 회차의
값이 Components v2 `capa_intro_summary` 의 `data` 로 브라우저에 닿고, 입장 화면 JS 가 받아 워커에
넘겨 글꼴·배치까지 미리 마친다 — Summary 를 누른 뒤에는 그리기만 한다. 입장 화면 오버레이의
`data` 로 보내지 않는 것은 그쪽이 회차마다 같은 값이어야 하기 때문이다(`intro_overlay`).

**무엇을 보내는가.** `services/official_summary.py` 가 정한 값이다 — 최신 공식버전 하나, 그
시나리오 시작월부터 여섯 달, HOME 토글 기본값. `get_home_simulation` 에 공식 리비전의 결정적
키(`reference_version_for_revision`·`pristine_content_token`)를 넘기므로 **무거운 시나리오 전체 Capa
계산(`get_full_capacity_outcome`)은 HOME·공식 발행 검사와 한 칸을 나눠 쓴다.** 여섯 달로 자른
결과는 HOME 의 조회기간과 대개 달라 따로 캐시된다(가벼운 부분이다).

**HOME 을 무겁게 하지 않는다**(2026-10-03 사용자 결정 — 주 업무가 HOME 이다).
완성된 요약은 서버에 한 벌만 둔다(`simulation_cache.get_intro_summary_payload` —
모든 사용자가 같은 공식버전을 본다). 같은 세션의 회차는 지난번 값을 그대로 보내고,
공식버전이 바뀌었는지는 `RECHECK_SECONDS` 에 한 번만 확인한다. 그래서 HOME 의 회차
(다시 실행·시나리오 전환)가 치르는 값은 세션에서 한 번 읽는 것뿐이고, 새 탭·F5·테마
전환도 서버에 이미 있는 값을 꺼낸다. 회차마다 같은 값이라 Streamlit 은 다시 그리지
않고 브라우저 JS 도 다시 돌지 않는다. 컴포넌트 칸은 회차마다 같은 자리에 둔다 —
빼면 그 뒤 본문 요소의 자리가 밀려 HOME 이 다시 그려진다.

**실패해도 앱은 선다.** 이 값은 모든 페이지 앞에서 보내므로 어떤 예외도 밖으로 내보내지 않는다 —
공식버전이 없거나 계산이 멈추면 `available: false` 와 까닭을 보낸다. 입장 화면은 Summary 를 끄고
Detail 만 남긴다. 데이터 오류로 만들지 못한 결과는 서버 캐시에 남겨 회차마다 다시 계산하지 않는다
(고치려면 새 공식버전을 지정해야 하고 그때 키가 바뀐다). DB 잠금 같은 일시적 실패는 남기지 않고
다음 확인 때(`RECHECK_SECONDS` 뒤) 다시 해 본다.

**토글 셋의 값도 함께 보낸다.** Summary 머리 줄의 「선행 B/O」·「선행 입고」·「GAP」은
브라우저 안에서만 켜고 끈다(rerun 이 없다). 그래서 세 갈래의 값을 요약과 함께 미리 만들어
`toggles` 로 싣는다 — HOME 의 같은 토글과 같은 함수다(`services/official_summary.py`). 쓰는
공용 프로필(선행 B/O·선행 입고 실적·비교 시나리오)은 공식버전을 확인할 때(`RECHECK_SECONDS` 에
한 번)만 캐시된 로더로 읽고, 각 프로필의 version 과 비교 대상을 서버 캐시 키에 넣어 프로필이
바뀌면 새로 만든다. 켤 수 없는 토글은 까닭을 단다(`available: false`) — 요약 기간에 입력이
없거나, 비교 대상이 없거나 지워졌거나 공식버전 자신일 때다. 한 토글의 값을 만들다 데이터 오류가
나도 그 토글만 끄고 요약은 그대로 보낸다.

**최신 공식버전을 함께 기억한다.** 공식버전을 확인할 때 본 그 리비전 id·번호를 세션에 같이
둔다(`latest_official_revision`). 머리 띠(`app_header`)가 「공식 vN」을 적을 때 그것만 읽어
회차마다 DB 를 다시 보지 않는다.

**사이드바 라벨.** 원래 화면에서 요약으로 돌아오는 길은 사이드바 머리칸의 `S.PKG CAPA` 라벨이다
(2026-10-06 사용자 결정 — 툴바의 `Summary` 단추를 걷었다). 테마 버튼 iframe 의 스크립트
(`summary_label_script`)가 머리칸에 끼워 넣고 칠한다. 누를 수 있는지와 눌렀을 때의 동작은 입장 화면
JS(`window.__capaIntro`)가 맡는다 — 요약 데이터와 장면을 가진 쪽이다.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, NamedTuple

import duckdb
import pandas as pd
import streamlit as st

from capa_simulation.components.intro_overlay import (
    BRAND,
    MARK_DIE_ORIGINS,
    MARK_RING_PATH,
    SUMMARY_LABEL,
    SUMMARY_LABEL_ARIA,
    SUMMARY_LABEL_ID,
    SUMMARY_LABEL_WAITING,
)
from capa_simulation.components.process_labels import ProcessLabels, get_process_labels
from capa_simulation.components.theme_toggle import SIDEBAR_HEADER_SLOT
from capa_simulation.design import tokens
from capa_simulation.io.reference_cache import reference_version_for_revision
from capa_simulation.persistence.cache import (
    get_scenario_repository,
    load_global_advance_load,
    load_global_advance_shipment,
    load_global_comparison_scenario,
    load_global_display_order,
    load_global_securement_threshold,
    load_scenario_plan,
    load_scenario_snapshot,
)
from capa_simulation.persistence.models import (
    GlobalAdvanceLoad,
    GlobalAdvanceShipment,
    GlobalComparisonScenario,
    OfficialReleaseSummary,
)
from capa_simulation.scenario_state import pristine_content_token
from capa_simulation.services.advance_shipment import advance_shipment_notes
from capa_simulation.services.dashboard import PRODUCTION_DETAIL_DIMENSIONS
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.month_filter import available_month_range
from capa_simulation.services.official_summary import (
    AdvanceSummary,
    BottleneckMonth,
    ComparisonSummary,
    OfficialSummary,
    build_advance_summary,
    build_comparison_summary,
    build_official_summary,
    summary_months,
)
from capa_simulation.services.securement_threshold import SecurementThresholds
from capa_simulation.services.simulation_cache import (
    IntroSummaryCacheKey,
    build_home_simulation_cache_key,
    get_home_comparison_plan,
    get_home_lob_without_edp,
    get_home_simulation,
    get_intro_summary_payload,
    shared_intro_toggle_store,
)
from capa_simulation.services.threshold_label import threshold_percent_label

# 컴포넌트 칸의 key 이자 숨김 규칙의 훅.
INTRO_SUMMARY_KEY = "capa_intro_summary"
# 이 세션이 마지막으로 보낸 요약과 그때 확인한 시각. HOME 이 주 업무 화면이라 이 부가
# 기능이 HOME 의 회차를 무겁게 하면 안 된다(2026-10-03 사용자 결정). 그래서 같은 세션의
# 회차는 이 값을 그대로 보내고, 공식버전이 바뀌었는지는 `RECHECK_SECONDS` 에 한 번만
# 본다(그 조회가 회차마다 7~9ms 였다). 이 세션에서 공식버전을 지정하면
# `forget_intro_summary_check` 가 곧바로 다시 보게 한다.
_SESSION_KEY = "intro_official_summary"
# 이 세션이 요약을 한 번이라도 보냈는가. 아직이면 입장 화면이 로딩을 덮는 때라 GAP 도 페이지 앞에서
# 함께 만든다. 공식버전을 지정한 뒤 확인을 비워도(`forget_intro_summary_check`) 이 표지는 남는다 —
# 저장한 회차에 HOME 앞에서 무거운 GAP 을 만들지 않게.
_SEEN_KEY = "intro_official_summary_seen"
# 입장 화면이 Summary 를 열며 「준비 중」 몫을 다시 받아 오라 했다(`_refresh_requested`). 그 회차는
# 미루지 않는다 — 사용자가 덮개 위에서 그 값을 기다리고 있고, 앞 회차의 페이지 뒤 데우기는 그
# trigger 의 rerun 에 끊겼을 수 있다(그리는 도중에 열면 Streamlit 이 그 회차를 끊고 새로 돈다).
_REFRESH_KEY = "intro_official_summary_refresh"
RECHECK_SECONDS = 30.0
# 일시적일 수 있는 실패. 이것만 서버 캐시에 남기지 않고 다음 확인 때(`RECHECK_SECONDS` 뒤)
# 다시 해 본다. 그 밖의 실패는 다시 해도 같은 결과(데이터 오류)라 「만들지 못함」을 서버
# 캐시에 남긴다 — 고치려면 새 공식버전을 지정해야 하고 그때 키가 바뀐다.
_TRANSIENT_ERRORS = (duckdb.Error, OSError, MemoryError)

# 켤 수 없는 토글의 까닭. Summary 머리 줄 토글의 풍선에 한 줄로 단다.
ADVANCE_OFF_EMPTY = "요약 기간에 넣은 선행 B/O 가 없습니다 (HOME → Preference)"
ADVANCE_OFF_UNAPPLICABLE = "선행 B/O 를 더하면 계획이 0 이하가 되는 달뿐이라 반영할 수 없습니다"
SHIPMENT_OFF_EMPTY = "요약 기간에 넣은 선행 입고 실적이 없습니다 (HOME → Preference)"
COMPARISON_OFF_NONE = "비교 시나리오를 고르지 않았습니다 (HOME → Preference)"
COMPARISON_OFF_MISSING = (
    "고른 비교 리비전을 찾을 수 없습니다 (HOME → Preference 에서 다시 고릅니다)"
)
COMPARISON_OFF_SELF = "비교 대상이 이 공식버전 자신이라 차이가 없습니다"
COMPARISON_OFF_UNCOVERED = "비교 시나리오에 요약 기간의 계획이 없습니다"
# 비교 값을 아직 서버에 만들어 두지 않아 이번 회차에는 보내지 못한 때(`_toggle_parts`). 페이지를 다
# 그린 뒤 만들어 두고 다음 회차에 싣는다 — 켜 둔 GAP 은 끄지 않는다(intro.js `syncToggles`).
COMPARISON_PENDING = "비교 시나리오 값을 준비하는 중입니다 — 화면이 다시 그려지면 켤 수 있습니다"
# 서버 캐시에 든 요약 값에서 토글 몫이 쓸 재료를 담는 칸. 브라우저로 보내기 전에 뗀다.
_CONTEXT = "_context"


class ToggleProfiles(NamedTuple):
    """Summary 토글 셋이 쓰는 공용 프로필. 공식버전을 확인할 때만 읽는다(캐시된 로더)."""

    advance: GlobalAdvanceLoad
    shipment: GlobalAdvanceShipment
    comparison: GlobalComparisonScenario


def load_toggle_profiles(database_path: str) -> ToggleProfiles:
    """세 공용 프로필. 모두 `persistence/cache` 의 캐시된 로더라 저장한 뒤에만 DB 를 연다."""
    return ToggleProfiles(
        advance=load_global_advance_load(database_path),
        shipment=load_global_advance_shipment(database_path),
        comparison=load_global_comparison_scenario(database_path),
    )


# 받은 값을 입장 화면 JS 에 넘기기만 한다. 오버레이가 아직 없으면 창에 두고 뜰 때 읽는다.
#
# **다시 받아 오기 한 길만 파이썬으로 보낸다.** 입장 화면이 Summary 를 열 때 「준비 중」 몫(페이지
# 뒤에서 만드는 GAP)이 있으면 `window.__capaSummaryRefresh` 를 부른다(intro.js — 한 번 열 때 한 번).
# 그 trigger 가 rerun 한 번을 부르고(덮개가 앱을 가리고 있다), 그 회차가 페이지 뒤에서 만들어 둔
# 값을 보낸다(`_refresh_requested`). 그 밖에는 아무것도 보내지 않는다 — rerun 은 첫 실행 도중이면 그
# 실행을 끊는다.
_REFRESH = "refresh"
_JS = """
export default function (component) {
  const data = component.data || null;
  window.__capaSummary = data;
  window.__capaSummaryRefresh = () => component.setTriggerValue("REFRESH", Date.now());
  const api = window.__capaIntro;
  if (api && typeof api.setSummary === "function") api.setSummary(data);
}
""".replace("REFRESH", _REFRESH)

_SUMMARY = st.components.v2.component("capa_intro_summary", js=_JS)

_HIDE_STYLE = (
    "<style>"
    f'[data-testid="stLayoutWrapper"]:has(> .st-key-{INTRO_SUMMARY_KEY}),'
    f".st-key-{INTRO_SUMMARY_KEY}"
    "{display:none !important;}"
    "</style>"
)


def _unavailable(reason: str) -> dict[str, Any]:
    return {"available": False, "reason": reason}


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def _density_payload(values: Sequence[float | None]) -> list[float | None]:
    return [_round(value, 2) for value in values]


def _wafer_payload(values: Sequence[float | None]) -> list[int | None]:
    """Wafer 는 HOME 칸과 같은 글자(`{:,.0f}K`)의 숫자 — 천 매 단위 정수로 보낸다.

    소수로 보내고 브라우저가 다시 반올림하면 두 번 반올림한다(148,460매가 HOME 「148K」, 요약
    「149K」였다). 파이썬 형식으로 한 번만 반올림해 HOME 과 같은 정수를 싣는다.
    """
    return [None if value is None else int(f"{value / 1_000:.0f}") for value in values]


def _bottleneck_payload(
    months: Sequence[int],
    bottlenecks: Sequence[BottleneckMonth | None],
    *,
    thresholds: SecurementThresholds,
    process_label: Callable[[str], str],
) -> list[dict[str, Any] | None]:
    """달마다 B/N 하나. 판정은 그 달의 실효 기준이다."""
    result: list[dict[str, Any] | None] = []
    for calendar_month, month in zip(months, bottlenecks, strict=True):
        if month is None:
            result.append(None)
            continue
        result.append(
            {
                "process": str(process_label(month.process)),
                "rate": round(month.rate * 100.0, 1),
                "need": _round(month.required, 1),
                "have": _round(month.available, 1),
                "short": month.short_units,
                "status": thresholds.status(month.rate, calendar_month),
            }
        )
    return result


def summary_payload(
    summary: OfficialSummary,
    *,
    release_name: str,
    scenario_name: str,
    thresholds: SecurementThresholds,
    process_label: Callable[[str], str],
) -> dict[str, Any]:
    """브라우저로 보낼 값. 반올림·차례를 고정해 같은 요약이면 늘 같은 값이 된다.

    판정 기준은 시나리오와 무관한 공용 프로필(HOME → Preference)이다. B/N 막대 색과 기준선은
    **달마다 그 달의 실효 기준**을 쓴다 — 기준 네 목록(`secure`·`warning`·`*_label`)이 `months` 와
    같은 차례·같은 길이다.

    색은 **테마와 무관한** 다크 팔레트다 — 입장 화면은 한 벌의 어두운 화면이고, 현재 테마의
    토큰을 읽으면 테마를 바꿀 때마다 값이 달라져 다시 보낸다.
    """
    colors = tokens.palette_value("dark", "PRODUCT_SHARE_COLORS")
    other = tokens.palette_value("dark", "PRODUCT_SHARE_OTHER")
    bottlenecks = _bottleneck_payload(
        summary.months, summary.bottlenecks, thresholds=thresholds, process_label=process_label
    )
    labels = summary.labels
    return {
        "available": True,
        "release": release_name,
        "scenario": scenario_name,
        "period": f"{labels[0]}–{labels[-1]}" if labels else "",
        "count": len(labels),
        "months": list(labels),
        "density": _density_payload(summary.density),
        "wafer": _wafer_payload(summary.wafer),
        "bn": bottlenecks,
        # 숫자는 기준선의 **자리**(정확한 값), `*_label` 은 기준선 이름표에 적는 **글자**다 —
        # 사사오입한 정수 퍼센트(109.5 → 110%). 109.7% 확보 막대가 선 위에 서야 하므로 둘을 나눈다.
        # 달마다 하나씩이다. 값이 같은 달이 이어지면 JS 가 한 구간으로 묶어 긋는다.
        "secure": [round(thresholds.secure_for(month) * 100.0, 1) for month in summary.months],
        "warning": [round(thresholds.warning_for(month) * 100.0, 1) for month in summary.months],
        "secure_label": [
            threshold_percent_label(thresholds.secure_for(month)) for month in summary.months
        ],
        "warning_label": [
            threshold_percent_label(thresholds.warning_for(month)) for month in summary.months
        ],
        "products": [
            {"name": name, "color": other if slot is None else colors[slot % len(colors)]}
            for name, slot in zip(summary.products, summary.product_slots, strict=True)
        ],
        "mix": [[[index, round(share, 4)] for index, share in month] for month in summary.mix],
    }


def advance_payload(
    months: Sequence[int],
    advance: AdvanceSummary,
    *,
    thresholds: SecurementThresholds,
    process_label: Callable[[str], str],
) -> dict[str, Any]:
    """「선행 B/O」를 켠 값. 요약과 같은 반올림·같은 모양이라 JS 가 달마다 그 사이를 잇는다.

    소요·가용·부족 대수는 HOME 처럼 그대로다 — 선행 B/O 는 확보율만 변동률만큼 옮긴다.
    """
    if not advance.applied:
        return _unavailable(ADVANCE_OFF_UNAPPLICABLE if advance.unapplied else ADVANCE_OFF_EMPTY)
    return {
        "available": True,
        "density": _density_payload(advance.density),
        "wafer": _wafer_payload(advance.wafer),
        "bn": _bottleneck_payload(
            months, advance.bottlenecks, thresholds=thresholds, process_label=process_label
        ),
        "density_delta": list(advance.density_delta),
        "wafer_delta": list(advance.wafer_delta),
        "rate_delta": list(advance.rate_delta),
        "unapplied": [month_label(month) for month in advance.unapplied],
    }


def shipment_payload(notes: Sequence[str]) -> dict[str, Any]:
    """「선행 입고」를 켠 값 — 달마다 Density 옆에 적을 글자(HOME 과 같은 `+#.#`, 없으면 빈칸)."""
    texts = [str(text) for text in notes]
    if not any(texts):
        return _unavailable(SHIPMENT_OFF_EMPTY)
    return {"available": True, "notes": texts}


def comparison_payload(comparison: ComparisonSummary, *, name: str) -> dict[str, Any]:
    """「GAP」을 켠 값 — 비교 시나리오 쪽 값(유령 표식 자리)과 HOME 과 같은 GAP 글자."""
    if not comparison.covered:
        return _unavailable(COMPARISON_OFF_UNCOVERED)
    return {
        "available": True,
        "name": name,
        "density": _density_payload(comparison.density),
        "wafer": _wafer_payload(comparison.wafer),
        "density_gap": list(comparison.density_gap),
        "wafer_gap": list(comparison.wafer_gap),
    }


def _guarded(name: str, build: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """토글 하나의 값. 데이터 오류는 그 토글만 끄고, 일시적 실패는 올려 캐시에 남기지 않는다."""
    try:
        return build()
    except _TRANSIENT_ERRORS:
        raise
    except Exception as exc:  # 요약 전체를 잃지 않는다 — 그 토글만 까닭을 달고 끈다
        return _unavailable(f"{name} 값을 만들지 못했습니다: {type(exc).__name__}: {exc}")


ComparisonPlanLoader = Callable[[str], tuple[pd.DataFrame, pd.DataFrame]]


def comparison_part(
    database_path: str,
    release: OfficialReleaseSummary,
    profile: GlobalComparisonScenario,
    *,
    months: Sequence[int],
    monthly_density: pd.DataFrame,
    monthly_wafer: pd.DataFrame,
    load_plan: ComparisonPlanLoader,
) -> dict[str, Any]:
    """비교 대상을 확인하고 GAP 값을 만든다.

    HOME 의 `_owned_comparison_revision` 과 같은 확인(그 리비전이 아직 그 시나리오 것인가)을 하되,
    DB 오류는 잡지 않고 올린다 — 일시적 실패로 GAP 을 끈 결과가 서버에 남지 않게 한다.
    `monthly_density`·`monthly_wafer` 는 요약의 계획(EDP 제외, 선행 전)이고, `load_plan` 은
    리비전 id 로 비교 계획의 월별 Density·Wafer 를 낸다.
    """
    if profile.scenario_id is None or profile.revision_id is None:
        return _unavailable(COMPARISON_OFF_NONE)
    if profile.revision_id == release.revision_id:
        return _unavailable(COMPARISON_OFF_SELF)
    repository = get_scenario_repository(database_path)
    revision = next(
        (
            item
            for item in repository.list_revisions(profile.scenario_id)
            if item.revision_id == profile.revision_id
        ),
        None,
    )
    if revision is None:
        return _unavailable(COMPARISON_OFF_MISSING)
    scenario_name = next(
        (
            item.scenario_name
            for item in repository.list_scenarios(include_archived=True)
            if item.scenario_id == profile.scenario_id
        ),
        "",
    )
    comparison_density, comparison_wafer = load_plan(revision.revision_id)
    comparison = build_comparison_summary(
        months=months,
        monthly_density=monthly_density,
        monthly_wafer=monthly_wafer,
        comparison_density=comparison_density,
        comparison_wafer=comparison_wafer,
    )
    return comparison_payload(comparison, name=f"{scenario_name} r{revision.revision_no}".strip())


def _build(
    database_path: str, release: OfficialReleaseSummary, thresholds: SecurementThresholds
) -> dict[str, Any]:
    """요약 한 벌(토글 몫 없이). 토글 몫이 쓸 재료를 `_context` 로 함께 둔다 — 보내기 전에 뗀다.

    재료는 요약을 만든 바로 그 프레임(계획은 EDP 제외)이다. 토글 몫은 이것만으로 만들어 서버
    캐시에 든 요약·리비전 스냅샷을 다시 풀지 않는다.
    """
    snapshot = load_scenario_snapshot(database_path, release.revision_id)
    tables = snapshot.tables
    preset = snapshot.preset
    source_start, source_end = available_month_range(tables["RQ_PKG_PLAN"], "RQ_PKG_PLAN")
    months = summary_months(preset.start_month, source_start, source_end)
    if not months:
        return _unavailable("공식버전의 시작월 뒤로 생산계획이 없습니다.")
    # 공식 리비전은 편집되지 않은 원본이라 키가 결정적이다 — HOME·공식 발행 검사와 같은 칸이다.
    reference_version = reference_version_for_revision(release.revision_id)
    display_order = tables["RQ_DISPLAY_ORDER"]
    cache_key = build_home_simulation_cache_key(
        reference_version=reference_version,
        scenario_token=pristine_content_token(reference_version),
        start_month=months[0],
        end_month=months[-1],
        display_order=display_order,
    )
    _density, _detail, _wafer, securement_rate, _assumed, slot_volume = get_home_simulation(
        cache_key=cache_key,
        _tables=tables,
        _display_order=display_order,
        _reference_tables=tables,
    )
    monthly_density, _detail, monthly_wafer, product_volume = get_home_lob_without_edp(
        cache_key=cache_key,
        _tables=tables,
        _display_order=display_order,
    )
    summary = build_official_summary(
        months=months,
        monthly_density=monthly_density,
        monthly_wafer=monthly_wafer,
        securement_rate=securement_rate,
        product_volume=product_volume,
        slot_volume=slot_volume,
        display_order=display_order,
        included_processes=preset.included_processes,
    )
    payload = summary_payload(
        summary,
        release_name=release.release_name,
        scenario_name=release.scenario_name,
        thresholds=thresholds,
        process_label=get_process_labels().format_func(),
    )
    payload[_CONTEXT] = {
        "months": list(months),
        "included": list(preset.included_processes),
        "home_key": cache_key,
        "density": monthly_density,
        "wafer": monthly_wafer,
        "securement": securement_rate,
    }
    return payload


def _build_or_unavailable(
    database_path: str, release: OfficialReleaseSummary, thresholds: SecurementThresholds
) -> dict[str, Any]:
    """서버 캐시가 부르는 계산. 일시적일 수 있는 실패는 그대로 올려 캐시에 남기지 않고,
    그 밖의 실패(데이터 오류)는 「만들지 못함」으로 돌려 캐시에 남긴다."""
    try:
        return _build(database_path, release, thresholds)
    except _TRANSIENT_ERRORS:
        raise
    except Exception as exc:  # 다시 해도 같은 결과다 — 회차마다 다시 계산하지 않게 남긴다
        return _unavailable(f"공식버전 요약을 만들지 못했습니다: {type(exc).__name__}: {exc}")


def _advance_part(
    context: Mapping[str, Any],
    profile: GlobalAdvanceLoad,
    thresholds: SecurementThresholds,
    process_label: Callable[[str], str],
) -> dict[str, Any]:
    """선행 B/O 몫 — 요약을 만든 프레임에 HOME 과 같은 함수로 선행 B/O 를 건다."""
    if profile.rows.empty:
        return _unavailable(ADVANCE_OFF_EMPTY)
    months = list(context["months"])
    outcome = build_advance_summary(
        months=months,
        monthly_density=context["density"],
        monthly_wafer=context["wafer"],
        securement_rate=context["securement"],
        included_processes=context["included"],
        advance_rows=profile.rows,
    )
    return advance_payload(months, outcome, thresholds=thresholds, process_label=process_label)


def _shipment_part(context: Mapping[str, Any], profile: GlobalAdvanceShipment) -> dict[str, Any]:
    """선행 입고 몫 — HOME `Capa LOB 현황` 이 Density 칸에 적는 글자 그대로."""
    labels = [month_label(int(month)) for month in context["months"]]
    return shipment_payload([text for text, _hover in advance_shipment_notes(profile.rows, labels)])


def _comparison_part(
    database_path: str,
    release: OfficialReleaseSummary,
    profile: GlobalComparisonScenario,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    """GAP 몫. 비교 계획을 공식버전 기준정보로 환산하는 데에만 리비전 스냅샷이 든다(그때만 푼다)."""

    def load_plan(revision_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        tables = load_scenario_snapshot(database_path, release.revision_id).tables
        # HOME GAP 과 같은 함수다 — 비교 리비전의 계획만 가져와 공식버전의 기준정보로 환산한다.
        density, wafer, _detail = get_home_comparison_plan(
            cache_key=context["home_key"],
            _tables=tables,
            _comparison_plan=load_scenario_plan(database_path, revision_id),
            _display_order=tables["RQ_DISPLAY_ORDER"],
            comparison_revision_id=revision_id,
            include_edp=False,
            detail_dimensions=tuple(PRODUCTION_DETAIL_DIMENSIONS),
        )
        return density, wafer

    return comparison_part(
        database_path,
        release,
        profile,
        months=list(context["months"]),
        monthly_density=context["density"],
        monthly_wafer=context["wafer"],
        load_plan=load_plan,
    )


def _pending() -> dict[str, Any]:
    return {"available": False, "pending": True, "reason": COMPARISON_PENDING}


def _toggle_parts(
    database_path: str,
    release: OfficialReleaseSummary,
    thresholds: SecurementThresholds,
    context: Mapping[str, Any],
    *,
    order_version: int,
    labels: ProcessLabels,
    defer: bool,
) -> tuple[dict[str, Any], bool]:
    """토글 셋의 값과, 이번에 「준비 중」으로 남긴 몫이 있는지.

    몫마다 따로 서버에 한 벌씩 둔다(`shared_intro_toggle_store`). 키는 공식버전 id 와 그 몫이 쓰는
    것뿐이라 선행 B/O 를 저장해도 요약·다른 몫은 그대로 꺼낸다. 선행 B/O·선행 입고는 요약 재료만으로
    수 ms 라 바로 만든다. GAP 은 처음 만들 때 비교 리비전 계획을 읽고 환산해야 해서(합성 사본 약
    1.4초) `defer` 면 HOME 페이지 **앞**에서 치르지 않고 「준비 중」으로 보낸 뒤 페이지를 그린 다음
    `warm_intro_summary` 가 만든다. 일시적 실패도 「준비 중」으로 두고 남기지 않는다. 표시순서·공정
    표시명 판은 요약 키를 만들 때 읽은 그 값(`order_version`·`labels`)이다 — 따로 다시 읽으면 그
    사이 저장된 판이 요약과 몫에 갈라 들어간다.
    """
    store = shared_intro_toggle_store()
    profiles = load_toggle_profiles(database_path)
    official = release.official_release_id
    comparison = profiles.comparison
    specs: list[tuple[str, str, tuple[Any, ...], Callable[[], dict[str, Any]], bool]] = [
        (
            "advance",
            "선행 B/O",
            ("advance", official, order_version, labels.version, thresholds.digest)
            + (profiles.advance.version,),
            lambda: _advance_part(context, profiles.advance, thresholds, labels.format_func()),
            False,
        ),
        (
            "shipment",
            "선행 입고",
            ("shipment", official, profiles.shipment.version),
            lambda: _shipment_part(context, profiles.shipment),
            False,
        ),
        (
            "comparison",
            "GAP",
            ("comparison", official, order_version, comparison.version)
            + (comparison.scenario_id or "", comparison.revision_id or ""),
            lambda: _comparison_part(database_path, release, comparison, context),
            # 비교 대상이 없거나 공식버전 자신이면 까닭만 내면 된다(DB·환산 없음) — 미루지 않는다.
            bool(comparison.scenario_id and comparison.revision_id)
            and comparison.revision_id != release.revision_id,
        ),
    ]
    parts: dict[str, Any] = {}
    pending = False
    for name, title, key, build, deferrable in specs:
        blob = store.get(key)
        if blob is not None:
            parts[name] = json.loads(blob)
            continue
        if deferrable and defer:
            parts[name] = _pending()
            pending = True
            continue
        try:
            part = _guarded(title, build)
        except _TRANSIENT_ERRORS:
            parts[name] = _pending()
            pending = True
            continue
        store.put(key, json.dumps(part, ensure_ascii=False).encode("utf-8"))
        parts[name] = part
    return parts, pending


class _Transient(Exception):
    """이번 확인이 일시적 실패로 끝났다. 세션이 들고 있던 값을 지우지 않는다."""


def _official_identity(release: OfficialReleaseSummary | None) -> dict[str, Any] | None:
    if release is None:
        return None
    return {"revision_id": release.revision_id, "release_no": release.release_no}


def _look_up(
    database_path: str, *, defer: bool = True
) -> tuple[dict[str, Any], dict[str, Any] | None, bool]:
    """보낼 요약, 그때 본 최신 공식버전(리비전 id·번호 — 없으면 `None`), 「준비 중」 몫이 있는지.

    공식버전을 읽은 뒤의 실패로 요약을 만들지 못해도 공식버전 자체는 돌려준다 — 머리 띠의
    「공식 vN」과 사이드바 배지가 서로 다른 말을 하지 않게 한다. `defer` 가 거짓이면(이 세션이 아직
    요약을 받은 적이 없다 — 입장 화면이 로딩을 덮는 때, 또는 페이지 뒤 데우기) GAP 도 함께 만든다.
    """
    identity: dict[str, Any] | None = None
    try:
        release = get_scenario_repository(database_path).latest_official_release()
        if release is None:
            return _unavailable("공식버전이 아직 없습니다."), None, False
        identity = _official_identity(release)
        # 판정 기준은 공용 프로필이다(시나리오 프리셋 값이 아니다). 키에는 version 이 아니라 **내용
        # 지문**을 넣는다 — 저장 전에는 version 이 0 이지만 기본값은 최신 공식버전 프리셋을 따른다.
        thresholds = load_global_securement_threshold(database_path).thresholds
        order_version = load_global_display_order(database_path).version
        labels = get_process_labels()
        cache_key: IntroSummaryCacheKey = (
            release.official_release_id,
            # 시나리오 이름은 바꿔도 공식버전 id 가 그대로라 따로 넣는다(머리 줄 풍선이 쓴다).
            release.scenario_name,
            order_version,
            labels.version,
            thresholds.digest,
        )
        payload = get_intro_summary_payload(
            cache_key, _build=lambda: _build_or_unavailable(database_path, release, thresholds)
        )
        context = payload.pop(_CONTEXT, None)
        if not payload.get("available") or not isinstance(context, Mapping):
            return payload, identity, False
        toggles, pending = _toggle_parts(
            database_path,
            release,
            thresholds,
            context,
            order_version=order_version,
            labels=labels,
            defer=defer,
        )
        payload["toggles"] = toggles
        return payload, identity, pending
    except _TRANSIENT_ERRORS as exc:
        raise _Transient(f"{type(exc).__name__}: {exc}") from exc
    except Exception as exc:  # 모든 페이지 앞이다 — 어떤 실패든 이 화면 하나로 끝내야 한다
        return (
            _unavailable(f"공식버전 요약을 만들지 못했습니다: {type(exc).__name__}: {exc}"),
            identity,
            False,
        )


def official_summary_data(database_path: str) -> dict[str, Any]:
    """이 회차에 보낼 요약.

    같은 세션에서 `RECHECK_SECONDS` 안이면 지난번 값을 그대로 쓴다(DB·캐시를 보지 않는다). 그 밖이면
    공식버전을 확인해 서버 캐시에서 꺼낸다 — 처음 만드는 것은 서버 전체에서 그 키로 한 번뿐이다.
    """
    now = time.monotonic()
    held = st.session_state.get(_SESSION_KEY)
    if (
        isinstance(held, dict)
        and isinstance(held.get("data"), dict)
        and now - float(held.get("checked_at", -RECHECK_SECONDS)) < RECHECK_SECONDS
    ):
        return dict(held["data"])
    pending = False
    try:
        refresh = bool(st.session_state.pop(_REFRESH_KEY, False))
        data, official, pending = _look_up(
            database_path, defer=bool(st.session_state.get(_SEEN_KEY)) and not refresh
        )
    except _Transient as exc:
        # DB 잠금 같은 일시적 실패로 멀쩡한 요약을 지우지 않는다(지우면 사이드바 라벨이 Summary
        # 를 열지 못한다). 들고 있던 값을 그대로 두고, 다음 확인도 `RECHECK_SECONDS` 뒤에 한다 —
        # HOME 회차는 그대로 가볍다.
        kept = held.get("data") if isinstance(held, dict) else None
        data = (
            kept if isinstance(kept, dict) else _unavailable(f"공식버전을 읽지 못했습니다: {exc}")
        )
        kept_official = held.get("official") if isinstance(held, dict) else None
        official = kept_official if isinstance(kept_official, dict) else None
    st.session_state[_SESSION_KEY] = {
        "checked_at": now,
        "data": data,
        "official": official,
        "pending": pending,
    }
    st.session_state[_SEEN_KEY] = True
    return dict(data)


def warm_intro_summary(database_path: str) -> None:
    """이번 회차에 「준비 중」으로 보낸 토글 몫(GAP)을 **페이지를 다 그린 뒤** 만들어 둔다.

    `app.py` 가 `navigation.run()` 뒤(페이지가 `st.stop()` 한 때도)에 부른다. 만든 값은 서버에
    남고 이 세션의 요약도 고쳐 두어 다음 회차에 브라우저로 간다 — 이번 회차의 요약은 이미 보냈다.
    「준비 중」이 없으면 아무것도 하지 않고(세션 하나 읽기), 실패하면 `RECHECK_SECONDS` 뒤 다시 해
    본다. 어떤 실패도 밖으로 내보내지 않는다 — 페이지는 이미 그렸다.
    """
    held = st.session_state.get(_SESSION_KEY)
    if not isinstance(held, dict) or not held.get("pending"):
        return
    now = time.monotonic()
    if now - float(held.get("warmed_at", -RECHECK_SECONDS)) < RECHECK_SECONDS:
        return
    try:
        data, official, pending = _look_up(database_path, defer=False)
    except Exception:  # 페이지는 이미 그렸다 — 다음 확인에 맡긴다
        held["warmed_at"] = now
        return
    st.session_state[_SESSION_KEY] = {
        "checked_at": now,
        "data": data,
        "official": official,
        "pending": pending,
        # 다시 해도 「준비 중」이면(일시적 실패) 이 확인 주기 동안은 더 하지 않는다.
        "warmed_at": now if pending else -RECHECK_SECONDS,
    }


def latest_official_revision() -> tuple[str, int] | None:
    """이 세션이 마지막으로 확인한 최신 공식버전의 (리비전 id, 공식버전 번호). 모르면 `None`.

    `official_summary_data` 가 요약과 함께 `RECHECK_SECONDS` 에 한 번 본 값을 세션에서만 읽는다 —
    머리 띠가 「공식 vN」을 적으려고 회차마다 DB 를 보지 않게 한다. `app.py` 는 요약을 머리 띠보다
    먼저 보내므로 같은 회차의 값이다. 이 세션에서 공식버전을 지정하면 `forget_intro_summary_check`
    로 다음 회차에 곧바로 다시 본다.
    """
    held = st.session_state.get(_SESSION_KEY)
    official = held.get("official") if isinstance(held, dict) else None
    if not isinstance(official, dict):
        return None
    revision_id = official.get("revision_id")
    release_no = official.get("release_no")
    if not isinstance(revision_id, str) or not isinstance(release_no, int):
        return None
    return revision_id, release_no


def forget_intro_summary_check() -> None:
    """이 세션의 다음 회차가 공식버전을 곧바로 다시 확인하게 한다(공식버전을 지정한 뒤)."""
    st.session_state.pop(_SESSION_KEY, None)


def _refresh_requested() -> None:
    """입장 화면이 「준비 중」 몫을 다시 받아 오려 한다(Summary 를 열 때 한 번).

    페이지 뒤 데우기가 끝났으면 세션 값이 이미 새 값이라 이번 회차가 그대로 보낸다. 아직 「준비
    중」이면 이번 회차에 곧바로 다시 확인하고 **미루지 않고** 만든다 — 사용자가 덮개 위에서
    기다리고, 앞 회차의 페이지 뒤 데우기는 이 rerun 에 끊겼을 수 있다(그 회차를 그리는 도중에 열면).
    """
    held = st.session_state.get(_SESSION_KEY)
    if isinstance(held, dict) and held.get("pending"):
        held["checked_at"] = -RECHECK_SECONDS
        held.pop("warmed_at", None)
        st.session_state[_REFRESH_KEY] = True


def render_intro_summary(database_path: str) -> None:
    """공식버전 요약을 보낸다. `app.py` 가 부트스트랩 뒤·페이지 앞에서 **매 회차** 한 번 부른다.

    회차마다 같은 값이라 브라우저 쪽 JS 는 처음 한 번만 돈다. 어떤 실패도 앱을 멈추지 않는다.
    """
    st.html(_HIDE_STYLE)
    _SUMMARY(
        key=INTRO_SUMMARY_KEY,
        data=official_summary_data(database_path),
        on_refresh_change=_refresh_requested,
    )


# 사이드바 머리칸의 `S.PKG CAPA` 라벨. 누르면 Summary 가 열린다. 테마 버튼 iframe 에 실려 한
# 번만 돈다.
#
# - **자리**: 사이드바 머리칸(`theme_toggle.SIDEBAR_HEADER_SLOT`) 맨 앞. 오른쪽 끝은 접기
#   버튼이다. 머리칸은 React 가 다시 그릴 수 있어 라벨이 빠지면 다시 끼운다(관찰자를 끊지
#   않는다 — 하는 일은 id 조회 한 번이다).
# - **색**: 앱 테마를 따른다(입장 화면·Summary 와 달리). 두 테마의 스타일을 모두 싣고 테마
#   버튼과 같은 규칙(`capaTheme.resolve`)으로 하나를 고른다 — iframe 내용은 회차마다 같아야
#   한다(`theme_toggle`). 테마를 바꾸면 새로고침이라 한 번 고르면 된다.
# - **누를 수 있는가**: 입장 화면 JS(`window.__capaIntro.decorate`)가 정한다 — 요약 데이터를
#   가진 쪽이다. 누를 수 없을 때는 `aria-disabled` 와 풍선(`title`)에 까닭을 단다. 초점은
#   받는다(Tab 으로 까닭을 읽을 수 있게). 입장 화면 JS 가 아직 없으면 준비 중으로 선다.
# - **글꼴**: 입장 화면 워드마크와 같은 Archivo 800 · 폭 75% 부분 글꼴. 입장 화면 JS 가 본
#   문서에 등록한 `CapaIntroDisplay` 를 그대로 쓴다(파일을 두 번 싣지 않는다). `S.PKG CAPA` 는
#   그 부분 글꼴의 글자 목록(`intro_overlay.FONT_SUBSET_TEXT`)에 들어 있다.
# - **움직임**: 심볼의 C 링이 12초마다 「반동 스핀」을 한 번 하고(첫 바퀴는 2초 뒤), 올리거나
#   Tab 초점이 닿으면 「살짝 감기」를 한다(2026-10-07 사용자 결정). 둘 다 CSS @keyframes 뿐이다 —
#   타이머도 rerun 도 없다. 라벨은 한 번 만든 단추를 계속 쓰고, 머리칸이 다시 그려져 다시 끼울
#   때만 주기가 처음(2초 뒤 첫 바퀴)부터 다시 돈다. 움직임 줄이기를 켠 사용자에게는 걸지 않는다.
_LABEL_SCRIPT = """
(function () {
  var parentWindow = window.parent;
  if (!parentWindow || parentWindow === window) return;
  var doc = parentWindow.document;

  function dark() {
    return typeof capaTheme !== "undefined" && capaTheme.resolve(parentWindow).choice === "Dark";
  }

  function addStyle() {
    if (doc.getElementById("%(id)s-style")) return;
    var style = doc.createElement("style");
    style.id = "%(id)s-style";
    style.textContent = dark() ? %(dark)s : %(light)s;
    (doc.head || doc.body).appendChild(style);
  }

  function place() {
    var slot = doc.querySelector('%(slot)s');
    if (!slot) return false;
    addStyle();
    var label = doc.getElementById("%(id)s");
    if (!label) {
      label = doc.createElement("button");
      label.id = "%(id)s";
      label.type = "button";
      label.innerHTML = %(icon)s
        + '<span class="capa-brand-word">%(brand)s</span>'
        + '<span class="capa-brand-hint">%(hint)s</span>';
      label.setAttribute("aria-label", "%(aria)s");
      label.setAttribute("aria-disabled", "true");
      label.title = "%(waiting)s";
      label.onclick = function () {
        if (label.getAttribute("aria-disabled") === "true") return;
        var api = parentWindow.__capaIntro;
        if (api && typeof api.openSummary === "function") api.openSummary(label);
      };
    }
    if (label.parentNode !== slot) slot.insertBefore(label, slot.firstChild);
    var api = parentWindow.__capaIntro;
    if (api && typeof api.decorate === "function") api.decorate(label);
    return true;
  }

  place();
  var observer = new parentWindow.MutationObserver(function () {
    var slot = doc.querySelector('%(slot)s');
    if (!slot) return;
    var label = doc.getElementById("%(id)s");
    if (!label || label.parentNode !== slot) place();
  });
  observer.observe(doc.body, { childList: true, subtree: true });
})();
"""

# 사이드바 머리칸 띠(`app_header`)는 높이 3.75rem 이다. 라벨은 그 안에 한 줄로 선다. 심볼은
# 입장 화면·Summary 머리 심볼(`intro.css` 의 `.logo`)과 같은 30px, 글자와의 틈 10px, 글자 18px
# 다(2026-10-08 사용자 요청 — 같은 크기로). 오른쪽 끝
# 접기 버튼 자리(28px + 틈 — 2.25rem)는 비우고, 사이드바를 좁게 끌면 안내 글자부터 줄어든다.
_LABEL_CSS = """
#__ID__ {
  display: inline-flex; align-items: center; gap: 7px; flex: 0 1 auto; min-width: 0;
  max-width: calc(100% - 2.25rem); height: 34px; margin: 0 auto 0 0; padding: 0 8px 0 6px;
  box-sizing: border-box; border: 1px solid transparent; border-radius: 8px;
  background: transparent; color: __TEXT__; cursor: pointer; white-space: nowrap; overflow: hidden;
  font-family: __FONT_FAMILY__;
}
#__ID__ svg { width: 30px; height: 30px; flex: none; display: block; margin-right: 3px; }
#__ID__ svg .capa-mark-turn, #__ID__ svg .capa-mark-spin {
  transform-box: view-box; transform-origin: 50px 50px;
}
#__ID__ svg .capa-mark-breathe, #__ID__ svg .capa-mark-pop {
  transform-box: fill-box; transform-origin: center;
}
#__ID__ .capa-brand-word {
  font-family: "CapaIntroDisplay", __FONT_FAMILY__; font-weight: 800; font-stretch: 75%;
  font-size: 18px; line-height: 1; letter-spacing: 0.01em; flex: none;
}
#__ID__ .capa-brand-hint {
  font-size: 11px; font-weight: 600; color: __TEXT_MUTED__; overflow: hidden;
  text-overflow: ellipsis; min-width: 0;
}
#__ID__:hover:not([aria-disabled="true"]) { background: __SURFACE__; border-color: __BORDER__; }
#__ID__:hover:not([aria-disabled="true"]) .capa-brand-hint { color: __ACCENT__; }
#__ID__:focus-visible { outline: 2px solid __ACCENT__; outline-offset: 2px; }
#__ID__[aria-disabled="true"] { cursor: not-allowed; }
#__ID__[aria-disabled="true"] .capa-brand-hint { opacity: 0.6; }
@media (prefers-reduced-motion: no-preference) {
  #__ID__ .capa-mark-spin { animation: capa-mark-spin 12s 2s infinite; }
  #__ID__ .capa-mark-pop { animation: capa-mark-pop 12s linear 2s infinite; }
  #__ID__:hover:not([aria-disabled="true"]) .capa-mark-turn,
  #__ID__:focus-visible .capa-mark-turn { animation: capa-mark-nudge 0.52s; }
  #__ID__:hover:not([aria-disabled="true"]) .capa-mark-breathe,
  #__ID__:focus-visible .capa-mark-breathe { animation: capa-mark-breathe 0.52s linear; }
}
@keyframes capa-mark-spin {
  0% { transform: rotate(0deg) scale(1); animation-timing-function: cubic-bezier(.3,0,.6,1); }
  1.875% {
    transform: rotate(-30deg) scale(.94); animation-timing-function: cubic-bezier(.25,.9,.3,1);
  }
  7.75% {
    transform: rotate(374deg) scale(1.02); animation-timing-function: cubic-bezier(.4,0,.6,1);
  }
  9.5% { transform: rotate(354deg) scale(1); animation-timing-function: cubic-bezier(.4,0,.6,1); }
  11% { transform: rotate(364deg) scale(1); animation-timing-function: cubic-bezier(.4,0,.6,1); }
  12.5%, 100% { transform: rotate(360deg) scale(1); }
}
@keyframes capa-mark-pop {
  0%, 7.75% { transform: scale(1); }
  8.75% { transform: scale(1.35); }
  9.75% { transform: scale(.92); }
  10.75%, 100% { transform: scale(1); }
}
@keyframes capa-mark-nudge {
  0% { transform: rotate(0deg); animation-timing-function: cubic-bezier(.3,0,.5,1); }
  30% { transform: rotate(-30deg); animation-timing-function: cubic-bezier(.3,1.7,.5,1); }
  100% { transform: rotate(0deg); }
}
@keyframes capa-mark-breathe {
  0%, 20% { transform: scale(1); }
  45% { transform: scale(1.25); }
  70%, 100% { transform: scale(1); }
}
"""


def _label_icon() -> str:
    """메인 심볼 — C 링 + 3×3 다이(`intro_overlay.MARK_RING_PATH` · `MARK_DIE_ORIGINS`, 입장 화면
    `intro.js` 의 `brandMark` 와 같은 모양). 링은 글자색, 다이는 앱 강조색이고 가운데 다이는
    주황(`BRAND_DIE_WARM`)이다 — 상태색이 아니라 심볼의 고정 강조색이라 입장 화면과 같은 자리에
    같은 색 계열을 둔다(2026-10-07 사용자 결정).

    링은 `<g>` 두 겹에 싼다 — 바깥(`capa-mark-turn`)은 올렸을 때의 「살짝 감기」, 안
    (`capa-mark-spin`)은 12초마다의 「반동 스핀」이 transform 을 따로 가져 서로 덮지 않는다. 가운데
    다이도 같은 까닭으로 두 겹이다(`capa-mark-breathe` · `capa-mark-pop`). 다이는 돌지 않는다."""
    dies: list[str] = []
    for row, y in enumerate(MARK_DIE_ORIGINS):
        for col, x in enumerate(MARK_DIE_ORIGINS):
            rect = f'x="{x}" y="{y}" width="12" height="12" rx="2"'
            if (row, col) == (1, 1):
                dies.append(
                    f'<g class="capa-mark-breathe"><rect class="capa-mark-pop" {rect} '
                    'fill="var(--capa-brand-core)"/></g>'
                )
            else:
                dies.append(f'<rect {rect} fill="var(--capa-brand-die)"/>')
    return (
        '<svg viewBox="0 0 100 100" aria-hidden="true">'
        '<g class="capa-mark-turn"><g class="capa-mark-spin">'
        f'<path d="{MARK_RING_PATH}" fill="none" stroke="currentColor" stroke-width="9" '
        'stroke-linecap="round"/></g></g>'
        f"{''.join(dies)}</svg>"
    )


def _label_css(mode: str) -> str:
    def value(name: str) -> str:
        return str(tokens.palette_value(mode, name))

    css = (
        _LABEL_CSS.replace("__ID__", SUMMARY_LABEL_ID)
        .replace("__FONT_FAMILY__", tokens.FONT_FAMILY)
        .replace("__TEXT_MUTED__", value("TEXT_MUTED"))
        .replace("__TEXT__", value("TEXT"))
        .replace("__SURFACE__", value("SURFACE"))
        .replace("__BORDER__", value("BORDER"))
        .replace("__ACCENT__", value("ACCENT"))
    )
    return css + (
        f"#{SUMMARY_LABEL_ID} {{ --capa-brand-die: {value('ACCENT')}; "
        f"--capa-brand-core: {value('BRAND_DIE_WARM')}; }}\n"
    )


def summary_label_script() -> str:
    """사이드바 머리칸에 `S.PKG CAPA` 라벨을 세우는 스크립트. 테마 버튼 iframe 에 Guide·Print
    와 함께 싣는다.

    툴바의 `Summary` 단추를 대신한다(2026-10-06 사용자 결정 — 툴바는 Guide·테마·Print). 누르면 그
    단추가 하던 일 그대로 입장 화면 JS 의 `openSummary` 를 부르고, Summary 를 닫으면 초점이 라벨로
    돌아온다(`openFromApp` 이 연 단추를 기억한다). iframe 내용은 회차마다 같아야 하므로 두 테마의
    스타일을 모두 싣고 테마 버튼과 같은 키 규칙으로 고른다.
    """
    return _LABEL_SCRIPT % {
        "id": SUMMARY_LABEL_ID,
        "slot": SIDEBAR_HEADER_SLOT,
        "icon": json.dumps(_label_icon()),
        "brand": BRAND,
        "hint": SUMMARY_LABEL,
        "aria": SUMMARY_LABEL_ARIA,
        "waiting": SUMMARY_LABEL_WAITING,
        "light": json.dumps(_label_css("light")),
        "dark": json.dumps(_label_css("dark")),
    }
