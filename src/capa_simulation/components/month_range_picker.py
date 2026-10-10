# Purpose: 조회기간 팝업의 월 입력 두 칸과 「적용」을 한 컴포넌트로 묶어 고른 범위를 보낸다.

from collections.abc import Mapping

import streamlit as st

# 칸 위 글자를 지운 자리는 `aria-label` 이 대신한다. `시작 월`·`종료 월` 두 줄은 팝업 제목
# (`조회기간`)과 화살표가 이미 말하고 있는 것을 한 번 더 적어 세로 26px 을 먹었다.
# 「적용」 단추가 **컴포넌트 안**이다(2026-10-11 병합 전 리뷰) — 아래 `_MONTH_RANGE_JS` 머리말.
_MONTH_RANGE_HTML = """
<div class="capa-month-root">
<div class="capa-month-range" lang="ko">
  <label class="capa-month-field" for="capa-start-month">
    <input id="capa-start-month" type="month" aria-label="시작 월" />
  </label>
  <span class="capa-month-separator" aria-hidden="true">→</span>
  <label class="capa-month-field" for="capa-end-month">
    <input id="capa-end-month" type="month" aria-label="종료 월" />
  </label>
</div>
<div class="capa-month-actions">
  <button id="capa-month-apply" type="button" class="capa-month-apply">적용</button>
  <span id="capa-month-message" class="capa-month-message" role="alert"></span>
</div>
</div>
"""

_MONTH_RANGE_CSS = """
.capa-month-root {
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

.capa-month-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  font-family: var(--st-font);
}

/* Streamlit primary 단추와 같은 결 — 면은 강조색, 글은 바탕색(두 테마에서 Streamlit 이 쓰는 짝). */
.capa-month-apply {
  height: 36px;
  padding: 0 16px;
  border: 1px solid var(--st-primary-color);
  border-radius: 8px;
  background: var(--st-primary-color);
  color: var(--st-background-color);
  font: inherit;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
}

.capa-month-apply:hover {
  filter: brightness(1.08);
}

.capa-month-apply:focus-visible {
  outline: 2px solid var(--st-primary-color);
  outline-offset: 2px;
}

.capa-month-message {
  min-width: 0;
  color: var(--st-text-color);
  font-size: 0.8rem;
  line-height: 1.3;
}
"""

# **「적용」은 컴포넌트 안에서 입력 칸의 지금 값을 읽어 범위와 함께 한 번에 보낸다**
# (2026-10-11 병합 전 리뷰). 전에는 월 칸이 바뀔 때마다 값을 따로 보내고(키 입력 뒤에는 600ms
# 기다렸다), 팝업의 Streamlit 「적용」 단추가 그 값을 읽었다. 그래서 키보드로 고친 뒤 600ms 안에
# 「적용」을 누르면 값이 아직 서버에 없어 옛 기간으로 닫혔고, 시작 > 끝으로 친 값은 아예 보내지
# 않아 「적용」이 아무 일도 하지 않았다(브라우저 재현). 이제 값과 누름이 한 트리거(`apply`)로 한
# 회차에 간다 — 시점과 무관하다.
# - 입력 칸 값은 보내지 않는다(초안). Enter 도 「적용」이다.
# - 온전하지 않은 월·범위 밖 월·시작 > 끝은 보내지 않고 단추 옆에 까닭을 적는다(조용히 바꾸지
#   않는다).
# - 서버가 보낸 범위가 바뀐 경우에만 칸에 다시 넣고, 포커스 중인 칸은 덮어쓰지 않는다.
#   `min`·`max` 는 값이 바뀔 때만 다시 넣는다(같은 값이라도 넣으면 Chrome 이 두 자리 월 입력을
#   끊는다 — 검토 실측).
# 예전의 「바깥으로 떠날 때 곧바로 보내지 않는다(사이드바 링크 이동과 경합)」 규칙은 이제 필요
# 없다 — 이 컴포넌트는 모달 팝업 안이라 링크가 가려지고, 칸 값은 「적용」 때만 보낸다.
# 입력 요소는 rerun 에서 교체되지 않으므로(실측) 회차를 넘는 상태는 요소에 단다.
_MONTH_RANGE_JS = """
export default function(component) {
  const { data, parentElement, setTriggerValue } = component
  const startInput = parentElement.querySelector('#capa-start-month')
  const endInput = parentElement.querySelector('#capa-end-month')
  const apply = parentElement.querySelector('#capa-month-apply')
  const message = parentElement.querySelector('#capa-month-message')
  if (!startInput || !endInput || !apply || !message) return

  const startValue = String(data?.start || data?.minMonth || '')
  const endValue = String(data?.end || data?.maxMonth || '')
  const minMonth = String(data?.minMonth || '')
  const maxMonth = String(data?.maxMonth || '')

  const isMonth = (text) =>
    /^[0-9]{4}-(0[1-9]|1[0-2])$/.test(text) &&
    (!minMonth || text >= minMonth) &&
    (!maxMonth || text <= maxMonth)
  const isFocused = (input) => input.getRootNode().activeElement === input

  const memo = startInput.__capaRange || (startInput.__capaRange = { seen: '' })
  const signature = startValue + '|' + endValue
  const refill = memo.seen !== signature
  memo.seen = signature
  for (const [input, committed] of [[startInput, startValue], [endInput, endValue]]) {
    if (input.min !== minMonth) input.min = minMonth
    if (input.max !== maxMonth) input.max = maxMonth
    if (refill && !isFocused(input)) input.value = committed
  }

  const say = (text) => { message.textContent = text }
  const submit = () => {
    const start = startInput.value
    const end = endInput.value
    if (!isMonth(start) || !isMonth(end)) {
      say('두 달을 끝까지, 고를 수 있는 범위 안으로 적어 주세요.')
      return
    }
    if (start > end) {
      say('시작 월이 종료 월보다 늦습니다 — 고친 뒤 적용하세요.')
      return
    }
    say('')
    setTriggerValue('apply', { start, end })
  }

  apply.onclick = submit
  for (const input of [startInput, endInput]) {
    input.oninput = () => say('')
    input.onkeydown = (event) => {
      if (event.key === 'Enter') {
        event.preventDefault()
        submit()
      }
    }
  }
}
"""

# **그림자 DOM 으로 가두지 않는다**(`isolate_styles=False`). 팝업(`st.dialog`)은 포커스를 팝업
# 안에서 돌리는데 그 순서는 그림자 DOM 안을 보지 못한다 — 가둔 채로는 월 칸에서 Tab 을 누르면 다음
# 월 칸·「적용」이 아니라 팝업의 닫기 단추로 가서, Tab·Enter 가 고친 기간을 버리고 팝업을 닫았다
# (2026-10-11 브라우저 실측). 서식은 `capa-month-*` 클래스로만 걸어 앱의 다른 요소에 새지 않는다.
_MONTH_RANGE_APPLY = st.components.v2.component(
    "capa_month_range_apply",
    html=_MONTH_RANGE_HTML,
    css=_MONTH_RANGE_CSS,
    js=_MONTH_RANGE_JS,
    isolate_styles=False,
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


def clamp_month_range(start: str, end: str, min_month: str, max_month: str) -> tuple[str, str]:
    """고를 수 있는 범위 밖·깨진 값을 범위 끝으로 끼운다. 시작 > 끝이면 끝을 시작에 맞춘다."""
    clamped_start = _valid_month(start, min_month, max_month) or min_month
    clamped_end = _valid_month(end, min_month, max_month) or max_month
    if clamped_start > clamped_end:
        clamped_end = clamped_start
    return clamped_start, clamped_end


def render_month_range_apply(
    *,
    start: str,
    end: str,
    min_month: str,
    max_month: str,
    key: str,
) -> tuple[str, str] | None:
    """월 입력 두 칸과 「적용」. 「적용」을 누른 회차에만 검증한 `(YYYY-MM, YYYY-MM)` 를 돌려준다.

    그 밖의 회차는 `None` 이다 — 칸에서 고르는 동안의 값은 서버에 오지 않는다(초안).
    """
    shown_start, shown_end = clamp_month_range(start, end, min_month, max_month)
    result = _MONTH_RANGE_APPLY(
        key=key,
        data={
            "start": shown_start,
            "end": shown_end,
            "minMonth": min_month,
            "maxMonth": max_month,
        },
        on_apply_change=lambda: None,
        width="stretch",
    )
    applied = getattr(result, "apply", None)
    if not isinstance(applied, Mapping):
        return None
    applied_start = _valid_month(applied.get("start"), min_month, max_month)
    applied_end = _valid_month(applied.get("end"), min_month, max_month)
    if applied_start is None or applied_end is None or applied_start > applied_end:
        return None
    return applied_start, applied_end
