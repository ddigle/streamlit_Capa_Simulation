# Purpose: 브라우저 월 입력을 공통 Streamlit 조회기간 상태와 연결한다.

from collections.abc import Mapping
from typing import Any, cast

import streamlit as st

# 칸 위 글자를 지운 자리는 `aria-label` 이 대신한다. `시작 월`·`종료 월` 두 줄은 박스
# 제목(`조회기간`)과 화살표가 이미 말하고 있는 것을 한 번 더 적어 세로 26px 을 먹었다.
_MONTH_RANGE_HTML = """
<div class="capa-month-range" lang="ko">
  <label class="capa-month-field" for="capa-start-month">
    <input id="capa-start-month" type="month" aria-label="시작 월" />
  </label>
  <span class="capa-month-separator" aria-hidden="true">→</span>
  <label class="capa-month-field" for="capa-end-month">
    <input id="capa-end-month" type="month" aria-label="종료 월" />
  </label>
</div>
"""

_MONTH_RANGE_CSS = """
:host {
  display: block;
  width: 100%;
}

.capa-month-range {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 18px minmax(0, 1fr);
  gap: 6px;
  align-items: center;
  box-sizing: border-box;
  width: 100%;
  padding: 0;
  color: var(--st-text-color);
  font-family: var(--st-font);
}

.capa-month-field {
  display: grid;
  min-width: 0;
}

.capa-month-field input {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  height: 36px;
  padding: 0 7px;
  border: 1px solid color-mix(in srgb, var(--st-text-color) 22%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--st-background-color) 94%, white);
  color: var(--st-text-color);
  font: inherit;
  font-size: 0.84rem;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
}

.capa-month-field input:hover {
  border-color: color-mix(in srgb, var(--st-primary-color) 65%, transparent);
}

.capa-month-field input:focus-visible {
  border-color: var(--st-primary-color);
  /* 사이드바 활성 링크의 링(ACCENT 14%)과 같은 세기다. */
  outline: 3px solid color-mix(in srgb, var(--st-primary-color) 14%, transparent);
  outline-offset: 0;
}

.capa-month-separator {
  display: grid;
  height: 36px;
  place-items: center;
  color: var(--st-primary-color);
  font-size: 0.95rem;
  font-weight: 700;
}
"""

# **키보드로 고치는 도중의 값은 보내지 않는다(2026-10-01, E2E G1-S2b).** 월 입력은 연도 칸에
# 숫자를 칠 때마다 `0002-12`·`0020-12` 같은 중간값으로 change 를 낸다. 예전에는 그때마다
# rerun 을 걸었고, 파이썬이 범위 밖 중간값을 버린 값으로 다시 그리며 **포커스 중인 칸까지
# 덮어써** 연도를 타이핑할 수 없었다. 화살표를 빠르게 누르면 한 칸만 반영됐고, 중간 회차의
# 기간이 다른 화면(표준 목표 시작일)을 잘라 두기도 했다. 그래서
# - 범위 안의 온전한 `YYYY-MM` 만 보낸다.
# - 키를 누른 직후의 변경은 잠깐(`SETTLE_MS`) 멈춘 뒤 한 번, Enter 나 다른 월 칸으로 옮길 때는
#   곧바로 보낸다. **바깥(사이드바 링크 등)으로 떠날 때는 곧바로 보내지 않고 걸린 타이머에
#   맡긴다** — 곧바로 보내면 그 값을 실은 요청이 링크의 페이지 이동을 덮어 화면이 제자리에
#   남았다(검토 실측).
# - `min`·`max` 는 값이 바뀔 때만 다시 넣는다. 같은 값이라도 다시 넣으면 Chrome 이 월 칸의
#   두 자리 입력을 끊어 `1`·`1` 이 11월이 아니라 1월로 확정됐다(검토 실측).
#   마우스로 달력에서 고른 것은 키 입력이 없으므로 예전처럼 곧바로 보낸다.
# - 포커스 중인 칸은 다시 그릴 때 덮어쓰지 않는다. 칸을 떠날 때 값이 온전하지 않으면 적용된
#   값으로 되돌린다.
# 입력 요소는 rerun 에서 교체되지 않으므로(실측) 회차를 넘는 상태는 요소에 단다.
_MONTH_RANGE_JS = """
export default function(component) {
  const { data, parentElement, setStateValue } = component
  const startInput = parentElement.querySelector('#capa-start-month')
  const endInput = parentElement.querySelector('#capa-end-month')
  if (!startInput || !endInput) return

  const value = data?.value || {}
  const startValue = String(value.start || data?.minMonth || '')
  const endValue = String(value.end || data?.maxMonth || '')
  const minMonth = String(data?.minMonth || '')
  const maxMonth = String(data?.maxMonth || '')
  const TYPING_WINDOW_MS = 1000
  const SETTLE_MS = 600

  const isMonth = (text) =>
    /^[0-9]{4}-(0[1-9]|1[0-2])$/.test(text) &&
    (!minMonth || text >= minMonth) &&
    (!maxMonth || text <= maxMonth)
  const isFocused = (input) => input.getRootNode().activeElement === input

  const memo = startInput.__capaRange || (startInput.__capaRange = { timer: 0, sent: '' })
  // 파이썬이 지금 쥔 값. 같은 값을 다시 보내 헛 rerun 을 만들지 않는다.
  memo.sent = startValue + '|' + endValue

  for (const [input, committed] of [[startInput, startValue], [endInput, endValue]]) {
    if (input.min !== minMonth) input.min = minMonth
    if (input.max !== maxMonth) input.max = maxMonth
    input.__capaCommitted = committed
    if (!isFocused(input) && input.value !== committed) input.value = committed
  }

  const cancelPending = () => {
    clearTimeout(memo.timer)
    memo.timer = 0
  }

  // `settled` 는 타이머가 보내는 경우다 — 사용자가 아직 치는 중일 수 있다. 그때는 시작 > 종료를
  // 반대쪽 칸을 당겨 맞추지 않고 보내지도 않는다. 월 칸에 `1` 을 치면 두 번째 숫자를 기다리는
  // 동안 값이 이미 1월이라, 타이머가 먼저 보내면 시작 월이 1월로 끌려 내려간 채 남았다
  // (2026-10-01 최종 재점검). 확정(Enter·다른 월 칸으로 이동·달력 선택)에서만 맞춘다.
  const emitRange = (changedField, settled = false) => {
    cancelPending()
    let start = startInput.value
    let end = endInput.value
    if (!isMonth(start) || !isMonth(end)) return
    if (settled && start > end) return

    if (start > end) {
      if (changedField === 'start') {
        end = start
        endInput.value = end
      } else {
        start = end
        startInput.value = start
      }
    }
    const signature = start + '|' + end
    if (signature === memo.sent) return
    memo.sent = signature
    setStateValue('value', { start, end })
  }

  const bind = (input, field) => {
    input.onkeydown = (event) => {
      input.__capaKeyAt = Date.now()
      if (event.key === 'Enter') emitRange(field)
    }
    input.onchange = () => {
      cancelPending()
      if (!isMonth(input.value)) return
      if (Date.now() - (input.__capaKeyAt || 0) < TYPING_WINDOW_MS) {
        memo.timer = setTimeout(() => emitRange(field, true), SETTLE_MS)
      } else {
        emitRange(field)
      }
    }
    input.onblur = (event) => {
      const next = event.relatedTarget
      if (memo.timer && (next === startInput || next === endInput)) emitRange(field)
      if (!isMonth(input.value)) input.value = input.__capaCommitted
    }
  }
  bind(startInput, 'start')
  bind(endInput, 'end')
}
"""

_MONTH_RANGE_PICKER = st.components.v2.component(
    "capa_month_range_picker",
    html=_MONTH_RANGE_HTML,
    css=_MONTH_RANGE_CSS,
    js=_MONTH_RANGE_JS,
)


def _valid_month(value: object, minimum: str, maximum: str) -> str | None:
    if not isinstance(value, str):
        return None
    parts = value.split("-")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    year, month = (int(part) for part in parts)
    normalized = f"{year:04d}-{month:02d}"
    if month < 1 or month > 12 or normalized < minimum or normalized > maximum:
        return None
    return normalized


def _component_value(key: str) -> object:
    component_state = st.session_state.get(key)
    if isinstance(component_state, Mapping):
        return component_state.get("value")
    return getattr(component_state, "value", None)


def render_month_range_picker(
    *,
    start: str,
    end: str,
    min_month: str,
    max_month: str,
    key: str,
) -> tuple[str, str]:
    """Render two native month inputs and return a validated YYYY-MM range."""
    fallback_start = _valid_month(start, min_month, max_month) or min_month
    fallback_end = _valid_month(end, min_month, max_month) or max_month
    if fallback_start > fallback_end:
        fallback_end = fallback_start

    raw_value = _component_value(key)
    state_value = cast(Mapping[str, Any], raw_value) if isinstance(raw_value, Mapping) else {}
    selected_start = _valid_month(state_value.get("start"), min_month, max_month)
    selected_end = _valid_month(state_value.get("end"), min_month, max_month)
    selected_start = selected_start or fallback_start
    selected_end = selected_end or fallback_end
    if selected_start > selected_end:
        selected_end = selected_start

    current_value = {"start": selected_start, "end": selected_end}
    result = _MONTH_RANGE_PICKER(
        key=key,
        data={
            "value": current_value,
            "minMonth": min_month,
            "maxMonth": max_month,
        },
        default={"value": current_value},
        on_value_change=lambda: None,
        width="stretch",
        # 칸 위 글자를 지운 만큼 낮춘다. 남는 높이를 두면 박스 아래가 빈다.
        height=40,
    )
    result_value = getattr(result, "value", current_value)
    returned_value = (
        cast(Mapping[str, Any], result_value)
        if isinstance(result_value, Mapping)
        else current_value
    )
    returned_start = _valid_month(returned_value.get("start"), min_month, max_month)
    returned_end = _valid_month(returned_value.get("end"), min_month, max_month)
    returned_start = returned_start or selected_start
    returned_end = returned_end or selected_end
    if returned_start > returned_end:
        returned_end = returned_start
    return returned_start, returned_end
