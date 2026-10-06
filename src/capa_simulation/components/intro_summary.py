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
from collections.abc import Callable
from typing import Any

import duckdb
import streamlit as st

from capa_simulation.components.intro_overlay import (
    BRAND,
    SUMMARY_LABEL,
    SUMMARY_LABEL_ARIA,
    SUMMARY_LABEL_ID,
    SUMMARY_LABEL_WAITING,
)
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.theme_toggle import SIDEBAR_HEADER_SLOT
from capa_simulation.design import tokens
from capa_simulation.io.reference_cache import reference_version_for_revision
from capa_simulation.persistence.cache import (
    get_scenario_repository,
    load_global_display_order,
    load_global_securement_threshold,
    load_scenario_snapshot,
)
from capa_simulation.persistence.models import OfficialReleaseSummary
from capa_simulation.scenario_state import pristine_content_token
from capa_simulation.services.month_filter import available_month_range
from capa_simulation.services.official_summary import (
    OfficialSummary,
    build_official_summary,
    summary_months,
)
from capa_simulation.services.securement_threshold import SecurementThresholds
from capa_simulation.services.simulation_cache import (
    build_home_simulation_cache_key,
    get_home_lob_without_edp,
    get_home_simulation,
    get_intro_summary_payload,
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
RECHECK_SECONDS = 30.0
# 일시적일 수 있는 실패. 이것만 서버 캐시에 남기지 않고 다음 확인 때(`RECHECK_SECONDS` 뒤)
# 다시 해 본다. 그 밖의 실패는 다시 해도 같은 결과(데이터 오류)라 「만들지 못함」을 서버
# 캐시에 남긴다 — 고치려면 새 공식버전을 지정해야 하고 그때 키가 바뀐다.
_TRANSIENT_ERRORS = (duckdb.Error, OSError, MemoryError)

# 받은 값을 입장 화면 JS 에 넘기기만 한다. 오버레이가 아직 없으면 창에 두고 뜰 때 읽는다.
_JS = """
export default function (component) {
  const data = component.data || null;
  window.__capaSummary = data;
  const api = window.__capaIntro;
  if (api && typeof api.setSummary === "function") api.setSummary(data);
}
"""

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
    bottlenecks: list[dict[str, Any] | None] = []
    for calendar_month, month in zip(summary.months, summary.bottlenecks, strict=True):
        if month is None:
            bottlenecks.append(None)
            continue
        bottlenecks.append(
            {
                "process": str(process_label(month.process)),
                "rate": round(month.rate * 100.0, 1),
                "need": _round(month.required, 1),
                "have": _round(month.available, 1),
                "short": month.short_units,
                "status": thresholds.status(month.rate, calendar_month),
            }
        )
    labels = summary.labels
    return {
        "available": True,
        "release": release_name,
        "scenario": scenario_name,
        "period": f"{labels[0]}–{labels[-1]}" if labels else "",
        "count": len(labels),
        "months": list(labels),
        "density": [_round(value, 2) for value in summary.density],
        "wafer": [_round(None if value is None else value / 1_000, 1) for value in summary.wafer],
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


def _build(
    database_path: str, release: OfficialReleaseSummary, thresholds: SecurementThresholds
) -> dict[str, Any]:
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
    return summary_payload(
        summary,
        release_name=release.release_name,
        scenario_name=release.scenario_name,
        thresholds=thresholds,
        process_label=get_process_labels().format_func(),
    )


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


class _Transient(Exception):
    """이번 확인이 일시적 실패로 끝났다. 세션이 들고 있던 값을 지우지 않는다."""


def _official_identity(release: OfficialReleaseSummary | None) -> dict[str, Any] | None:
    if release is None:
        return None
    return {"revision_id": release.revision_id, "release_no": release.release_no}


def _look_up(database_path: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """보낼 요약과, 그때 본 최신 공식버전(리비전 id·번호 — 없으면 `None`).

    공식버전을 읽은 뒤의 실패로 요약을 만들지 못해도 공식버전 자체는 돌려준다 — 머리 띠의
    「공식 vN」과 사이드바 배지가 서로 다른 말을 하지 않게 한다.
    """
    identity: dict[str, Any] | None = None
    try:
        release = get_scenario_repository(database_path).latest_official_release()
        if release is None:
            return _unavailable("공식버전이 아직 없습니다."), None
        identity = _official_identity(release)
        # 판정 기준은 공용 프로필이다(시나리오 프리셋 값이 아니다). 키에는 version 이 아니라 **내용
        # 지문**을 넣는다 — 저장 전에는 version 이 0 이지만 기본값은 최신 공식버전 프리셋을 따른다.
        thresholds = load_global_securement_threshold(database_path).thresholds
        cache_key = (
            release.official_release_id,
            # 시나리오 이름은 바꿔도 공식버전 id 가 그대로라 따로 넣는다(머리 줄 풍선이 쓴다).
            release.scenario_name,
            load_global_display_order(database_path).version,
            get_process_labels().version,
            thresholds.digest,
        )
        payload = get_intro_summary_payload(
            cache_key, _build=lambda: _build_or_unavailable(database_path, release, thresholds)
        )
        return payload, identity
    except _TRANSIENT_ERRORS as exc:
        raise _Transient(f"{type(exc).__name__}: {exc}") from exc
    except Exception as exc:  # 모든 페이지 앞이다 — 어떤 실패든 이 화면 하나로 끝내야 한다
        return (
            _unavailable(f"공식버전 요약을 만들지 못했습니다: {type(exc).__name__}: {exc}"),
            identity,
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
    try:
        data, official = _look_up(database_path)
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
    st.session_state[_SESSION_KEY] = {"checked_at": now, "data": data, "official": official}
    return dict(data)


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


def render_intro_summary(database_path: str) -> None:
    """공식버전 요약을 보낸다. `app.py` 가 부트스트랩 뒤·페이지 앞에서 **매 회차** 한 번 부른다.

    회차마다 같은 값이라 브라우저 쪽 JS 는 처음 한 번만 돈다. 어떤 실패도 앱을 멈추지 않는다.
    """
    st.html(_HIDE_STYLE)
    _SUMMARY(key=INTRO_SUMMARY_KEY, data=official_summary_data(database_path))


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

# 사이드바 머리칸 띠(`app_header`)는 높이 3.75rem 이다. 라벨은 그 안에 한 줄로 선다. 오른쪽 끝
# 접기 버튼 자리(28px + 틈 — 2.25rem)는 비우고, 사이드바를 좁게 끌면 안내 글자부터 줄어든다.
_LABEL_CSS = """
#__ID__ {
  display: inline-flex; align-items: center; gap: 8px; flex: 0 1 auto; min-width: 0;
  max-width: calc(100% - 2.25rem); height: 34px; margin: 0 auto 0 0; padding: 0 8px 0 6px;
  box-sizing: border-box; border: 1px solid transparent; border-radius: 8px;
  background: transparent; color: __TEXT__; cursor: pointer; white-space: nowrap; overflow: hidden;
  font-family: __FONT_FAMILY__;
}
#__ID__ svg { width: 22px; height: 22px; flex: none; display: block; }
#__ID__ .capa-brand-word {
  font-family: "CapaIntroDisplay", __FONT_FAMILY__; font-weight: 800; font-stretch: 75%;
  font-size: 19px; line-height: 1; letter-spacing: 0.01em; flex: none;
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
"""


def _label_icon() -> str:
    """입장 화면 심볼과 같은 모양 — 노치 있는 링과 3×3 다이(`intro.js` 의 `waferLogo`). 링은 글자색,
    다이는 앱 강조색이다. 가운데 다이도 강조색이다 — 앱에서 주황은 「경고」라 입장 화면처럼 칠하지
    않는다."""
    dies = "".join(
        f'<rect x="{x}" y="{y}" width="13" height="13" rx="2" fill="var(--capa-brand-die)"/>'
        for y in (27, 43.5, 60)
        for x in (27, 43.5, 60)
    )
    return (
        '<svg viewBox="0 0 100 100" aria-hidden="true">'
        '<path d="M53 93.9 A44 44 0 1 0 47 93.9 L50 90.6 Z" fill="none" '
        'stroke="currentColor" stroke-width="6"/>'
        f"{dies}</svg>"
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
    return css + f"#{SUMMARY_LABEL_ID} {{ --capa-brand-die: {value('ACCENT')}; }}\n"


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
