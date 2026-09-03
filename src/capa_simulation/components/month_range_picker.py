# Purpose: 브라우저 월 입력을 공통 Streamlit 조회기간 상태와 연결한다.

from collections.abc import Mapping
from typing import Any, cast

import streamlit as st

_MONTH_RANGE_HTML = """
<div class="capa-month-range" lang="ko">
  <label class="capa-month-field" for="capa-start-month">
    <span>시작 월</span>
    <input id="capa-start-month" type="month" />
  </label>
  <span class="capa-month-separator" aria-hidden="true">→</span>
  <label class="capa-month-field" for="capa-end-month">
    <span>종료 월</span>
    <input id="capa-end-month" type="month" />
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
  align-items: end;
  box-sizing: border-box;
  width: 100%;
  padding: 2px 0;
  color: var(--st-text-color);
  font-family: var(--st-font);
}

.capa-month-field {
  display: grid;
  min-width: 0;
  gap: 5px;
}

.capa-month-field span {
  color: var(--st-text-color);
  font-size: 0.78rem;
  font-weight: 650;
}

.capa-month-field input {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  height: 38px;
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
  outline: 2px solid color-mix(in srgb, var(--st-primary-color) 22%, transparent);
  outline-offset: 1px;
}

.capa-month-separator {
  display: grid;
  height: 38px;
  place-items: center;
  color: color-mix(in srgb, var(--st-text-color) 58%, transparent);
  font-size: 0.95rem;
  font-weight: 700;
}
"""

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

  startInput.min = minMonth
  startInput.max = maxMonth
  endInput.min = minMonth
  endInput.max = maxMonth
  if (startInput.value !== startValue) startInput.value = startValue
  if (endInput.value !== endValue) endInput.value = endValue

  const emitRange = (changedField) => {
    let start = startInput.value
    let end = endInput.value
    if (!start || !end) return

    if (start > end) {
      if (changedField === 'start') {
        end = start
        endInput.value = end
      } else {
        start = end
        startInput.value = start
      }
    }
    setStateValue('value', { start, end })
  }

  startInput.onchange = () => emitRange('start')
  endInput.onchange = () => emitRange('end')
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
        height=68,
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
