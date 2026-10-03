# Purpose: 최신 공식버전의 6개월 요약을 입장 화면에 미리 보내고 툴바 Summary 단추를 세운다.

"""입장 화면 `Summary` 의 데이터와 툴바 단추.

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

**툴바 단추.** 원래 화면에서 요약으로 돌아오는 `Summary` 는 Guide 처럼 테마 버튼 iframe 의
스크립트(`summary_toolbar_script`)가 툴바에 끼워 넣고 칠한다 — Guide 와 같은 윤곽 단추에 앱 색 16px
웨이퍼. 보임과 눌렀을 때의 동작은 입장 화면 JS(`window.__capaIntro`)가 맡는다 — 요약 데이터와 장면을
가진 쪽이다.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import duckdb
import streamlit as st

from capa_simulation.components.home_figure_common import capacity_status
from capa_simulation.components.intro_overlay import SUMMARY_LABEL
from capa_simulation.components.page_guide import BUTTON_ID as GUIDE_BUTTON_ID
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.theme_toggle import (
    THEME_BUTTON_ID,
    THEME_STORAGE_PREFIX,
    THEME_STORAGE_SUFFIX,
)
from capa_simulation.design import tokens
from capa_simulation.io.reference_cache import reference_version_for_revision
from capa_simulation.persistence.cache import (
    get_scenario_repository,
    load_global_display_order,
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
from capa_simulation.services.simulation_cache import (
    build_home_simulation_cache_key,
    get_home_lob_without_edp,
    get_home_simulation,
    get_intro_summary_payload,
)
from capa_simulation.services.threshold_label import threshold_percent_label

# 컴포넌트 칸의 key 이자 숨김 규칙의 훅.
INTRO_SUMMARY_KEY = "capa_intro_summary"
# 툴바 단추 id. 입장 화면 JS 의 `SUMMARY_BUTTON_ID` 와 같아야 한다(테스트가 잡는다).
SUMMARY_BUTTON_ID = "capa-summary-button"
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
    secure_threshold: float,
    warning_threshold: float,
    process_label: Callable[[str], str],
) -> dict[str, Any]:
    """브라우저로 보낼 값. 반올림·차례를 고정해 같은 요약이면 늘 같은 값이 된다.

    색은 **테마와 무관한** 다크 팔레트다 — 입장 화면은 한 벌의 어두운 화면이고, 현재 테마의
    토큰을 읽으면 테마를 바꿀 때마다 값이 달라져 다시 보낸다.
    """
    colors = tokens.palette_value("dark", "PRODUCT_SHARE_COLORS")
    other = tokens.palette_value("dark", "PRODUCT_SHARE_OTHER")
    bottlenecks: list[dict[str, Any] | None] = []
    for month in summary.bottlenecks:
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
                "status": capacity_status(
                    month.rate,
                    secure_threshold=secure_threshold,
                    warning_threshold=warning_threshold,
                ),
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
        # 숫자는 기준선의 **자리**(정확한 값), `*_label` 은 범례·기준선 이름표에 적는 **글자**다 —
        # 사사오입한 정수 퍼센트(109.5 → 110%). 109.7% 확보 막대가 선 위에 서야 하므로 둘을 나눈다.
        "secure": round(secure_threshold * 100.0, 1),
        "warning": round(warning_threshold * 100.0, 1),
        "secure_label": threshold_percent_label(secure_threshold),
        "warning_label": threshold_percent_label(warning_threshold),
        "products": [
            {"name": name, "color": other if slot is None else colors[slot % len(colors)]}
            for name, slot in zip(summary.products, summary.product_slots, strict=True)
        ],
        "mix": [[[index, round(share, 4)] for index, share in month] for month in summary.mix],
    }


def _build(database_path: str, release: OfficialReleaseSummary) -> dict[str, Any]:
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
        secure_threshold=preset.secure_threshold,
        warning_threshold=preset.warning_threshold,
        process_label=get_process_labels().format_func(),
    )


def _build_or_unavailable(database_path: str, release: OfficialReleaseSummary) -> dict[str, Any]:
    """서버 캐시가 부르는 계산. 일시적일 수 있는 실패는 그대로 올려 캐시에 남기지 않고,
    그 밖의 실패(데이터 오류)는 「만들지 못함」으로 돌려 캐시에 남긴다."""
    try:
        return _build(database_path, release)
    except _TRANSIENT_ERRORS:
        raise
    except Exception as exc:  # 다시 해도 같은 결과다 — 회차마다 다시 계산하지 않게 남긴다
        return _unavailable(f"공식버전 요약을 만들지 못했습니다: {type(exc).__name__}: {exc}")


class _Transient(Exception):
    """이번 확인이 일시적 실패로 끝났다. 세션이 들고 있던 값을 지우지 않는다."""


def _look_up(database_path: str) -> dict[str, Any]:
    try:
        release = get_scenario_repository(database_path).latest_official_release()
        if release is None:
            return _unavailable("공식버전이 아직 없습니다.")
        cache_key = (
            release.official_release_id,
            # 시나리오 이름은 바꿔도 공식버전 id 가 그대로라 따로 넣는다(머리 줄 풍선이 쓴다).
            release.scenario_name,
            load_global_display_order(database_path).version,
            get_process_labels().version,
        )
        return get_intro_summary_payload(
            cache_key, _build=lambda: _build_or_unavailable(database_path, release)
        )
    except _TRANSIENT_ERRORS as exc:
        raise _Transient(f"{type(exc).__name__}: {exc}") from exc
    except Exception as exc:  # 모든 페이지 앞이다 — 어떤 실패든 이 화면 하나로 끝내야 한다
        return _unavailable(f"공식버전 요약을 만들지 못했습니다: {type(exc).__name__}: {exc}")


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
        data = _look_up(database_path)
    except _Transient as exc:
        # DB 잠금 같은 일시적 실패로 멀쩡한 요약을 지우지 않는다(지우면 툴바 Summary 가
        # 사라진다). 들고 있던 값을 그대로 두고, 다음 확인도 `RECHECK_SECONDS` 뒤에 한다 —
        # HOME 회차는 그대로 가볍다.
        kept = held.get("data") if isinstance(held, dict) else None
        data = (
            kept if isinstance(kept, dict) else _unavailable(f"공식버전을 읽지 못했습니다: {exc}")
        )
    st.session_state[_SESSION_KEY] = {"checked_at": now, "data": data}
    return dict(data)


def forget_intro_summary_check() -> None:
    """이 세션의 다음 회차가 공식버전을 곧바로 다시 확인하게 한다(공식버전을 지정한 뒤)."""
    st.session_state.pop(_SESSION_KEY, None)


def render_intro_summary(database_path: str) -> None:
    """공식버전 요약을 보낸다. `app.py` 가 부트스트랩 뒤·페이지 앞에서 **매 회차** 한 번 부른다.

    회차마다 같은 값이라 브라우저 쪽 JS 는 처음 한 번만 돈다. 어떤 실패도 앱을 멈추지 않는다.
    """
    st.html(_HIDE_STYLE)
    _SUMMARY(key=INTRO_SUMMARY_KEY, data=official_summary_data(database_path))


_TOOLBAR_SCRIPT = """
(function () {
  var parentWindow = window.parent;
  if (!parentWindow || parentWindow === window) return;
  var doc = parentWindow.document;

  // 테마는 테마 버튼과 같은 저장 키로 읽는다. 바꾸면 그 버튼이 새로고침하므로 한 번 읽으면 된다.
  function dark() {
    try {
      var key = "%(prefix)s" + parentWindow.location.pathname + "%(suffix)s";
      return JSON.parse(parentWindow.localStorage.getItem(key) || '"Light"') === "Dark";
    } catch (error) { return false; }
  }

  function place() {
    var slot = doc.querySelector('[data-testid="stToolbarActions"]');
    if (!slot) return false;
    var button = doc.getElementById("%(id)s");
    if (!button) {
      var colors = dark() ? %(dark)s : %(light)s;
      button = doc.createElement("button");
      button.id = "%(id)s";
      button.type = "button";
      button.innerHTML = colors.icon + "<span>%(label)s</span>";
      button.title = "공식버전 요약 보기";
      button.setAttribute("aria-label", button.title);
      // Guide 와 같은 윤곽 단추(본문 글꼴 13px/600 · 모서리 8px · 높이 27px)에 16px 웨이퍼 하나.
      // `display:none` 은 **맨 끝**이다 — 요약이 준비되면 입장 화면 JS 가 보이게 한다.
      button.style.cssText = [
        "font:inherit", "font-size:13px", "font-weight:600", "line-height:1",
        "align-items:center", "gap:6px", "box-sizing:border-box", "height:27px",
        "padding:0 12px 0 8px", "margin-right:6px", "border-radius:8px", "cursor:pointer",
        "white-space:nowrap", "background:transparent",
        "border:1px solid " + colors.border, "color:" + colors.text, "display:none"
      ].join(";");
      button.onclick = function () {
        var api = parentWindow.__capaIntro;
        if (api && typeof api.openSummary === "function") api.openSummary(button);
      };
      // Guide·테마 버튼보다 **왼쪽**에 선다.
      var first = doc.getElementById("%(guide)s") || doc.getElementById("%(theme)s");
      slot.insertBefore(button, first || slot.firstChild);
    }
    var api = parentWindow.__capaIntro;
    if (api && typeof api.decorate === "function") api.decorate(button);
    return true;
  }

  if (place()) return;
  var observer = new parentWindow.MutationObserver(function () {
    if (place()) observer.disconnect();
  });
  observer.observe(doc.body, { childList: true, subtree: true });
  parentWindow.setTimeout(function () { observer.disconnect(); }, 8000);
})();
"""


def _toolbar_icon(ring: str, die: str) -> str:
    """툴바용 16px 웨이퍼. 입장 화면 심볼(9칸)은 16px 에서 뭉개지고 가운데 주황은 앱에서 「경고」라,
    노치 있는 링과 2×2 다이로 다시 그려 앱 색으로 칠한다."""
    dies = "".join(
        f'<rect x="{x}" y="{y}" width="2.7" height="2.7" rx="0.5" fill="{die}"/>'
        for y in (4.9, 8.4)
        for x in (4.9, 8.4)
    )
    return (
        '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" '
        'style="display:block;flex:none">'
        f'<path d="M9 14.3 A6.4 6.4 0 1 0 7 14.3" fill="none" stroke="{ring}" '
        'stroke-width="1.5" stroke-linecap="round"/>'
        f"{dies}</svg>"
    )


def _toolbar_colors(mode: str) -> str:
    def value(name: str) -> str:
        return str(tokens.palette_value(mode, name))

    return json.dumps(
        {
            "border": value("BORDER"),
            "text": value("TEXT"),
            "icon": _toolbar_icon(value("TEXT_MUTED"), value("ACCENT")),
        }
    )


def summary_toolbar_script() -> str:
    """툴바에 `Summary` 단추를 세우고 칠하는 스크립트. 테마 버튼 iframe 에 Guide 와 함께 싣는다.

    **Guide 와 같은 윤곽 단추**에 앱 색으로 다시 그린 16px 웨이퍼 하나를 더한 모양이다(2026-10-03
    사용자 결정 — 입장 화면 옷을 입은 검은 알약이 툴바와 결이 맞지 않았다). 두 테마 값을 모두 싣고
    테마 버튼과 같은 저장 키로 고른다 — iframe 내용은 회차마다 같아야 하므로(`theme_toggle`) 지금
    테마를 따라 바뀌는 토큰을 넣지 않는다. 보임과 눌렀을 때의 동작은 입장 화면 JS 가 맡는다.
    """
    return _TOOLBAR_SCRIPT % {
        "id": SUMMARY_BUTTON_ID,
        "guide": GUIDE_BUTTON_ID,
        "theme": THEME_BUTTON_ID,
        "prefix": THEME_STORAGE_PREFIX,
        "suffix": THEME_STORAGE_SUFFIX,
        "label": SUMMARY_LABEL,
        "light": _toolbar_colors("light"),
        "dark": _toolbar_colors("dark"),
    }
