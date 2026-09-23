# Purpose: 월별 Plotly 영역과 동기화되는 Components v2 가로 스크롤바를 제공한다.

import streamlit as st

from capa_simulation.design import tokens

_SCROLLBAR_HTML = """
<div
  class="capa-scrollbar-track"
  role="scrollbar"
  aria-label="월별 데이터 가로 스크롤"
  aria-orientation="horizontal"
  aria-valuemin="0"
  aria-valuemax="100"
  aria-valuenow="0"
  tabindex="0"
>
  <div class="capa-scrollbar-thumb"></div>
</div>
"""

# **여기에 색을 적지 않는다.** `st.components.v2.component` 는 등록 시점의 CSS 를 그대로
# 쓰고 등록은 프로세스당 한 번이라, 토큰을 여기서 읽으면 이 모듈을 처음 읽은 테마의 색이
# 프로세스가 죽을 때까지 남는다. 새로고침도 테마 전환도 듣지 않고, 여럿이 쓰는 서버에서는
# 먼저 들어온 세션의 테마가 모두의 막대 색을 정한다. 색은 이름만 두고 값은 실행마다
# `data` 로 들어와 아래 JS 가 트랙에 얹는다.
_SCROLLBAR_CSS = """
:host {
  display: block;
  width: 100%;
}

.capa-scrollbar-track {
  position: relative;
  box-sizing: border-box;
  width: 100%;
  overflow: hidden;
  border-radius: 999px;
  background: var(--capa-scrollbar-track);
  cursor: pointer;
  touch-action: none;
  user-select: none;
}

.capa-scrollbar-thumb {
  position: absolute;
  inset-block: 0;
  inset-inline-start: 0;
  box-sizing: border-box;
  border: 2px solid var(--capa-scrollbar-track);
  border-radius: 999px;
  background: var(--capa-scrollbar-thumb);
  cursor: grab;
  will-change: transform;
}

.capa-scrollbar-thumb:hover {
  background: var(--capa-scrollbar-thumb-hover);
}

.capa-scrollbar-track.is-dragging .capa-scrollbar-thumb {
  background: var(--capa-scrollbar-thumb-active);
  cursor: grabbing;
}

.capa-scrollbar-track:focus-visible {
  outline: 2px solid var(--st-primary-color);
  outline-offset: 2px;
}
"""

_SCROLLBAR_JS = """
export default function(component) {
  const { data, parentElement } = component
  const track = parentElement.querySelector('.capa-scrollbar-track')
  const thumb = parentElement.querySelector('.capa-scrollbar-thumb')
  // 색은 CSS 가 아니라 `data` 로 들어온다 — 컴포넌트 CSS 는 등록 시점에 굳어 테마를
  // 따라오지 못한다. 손잡이는 트랙의 자식이라 여기 얹은 속성을 그대로 물려받는다.
  // **아래 이른 반환보다 먼저 얹는다.** CSS 쪽 `var()` 에 폴백을 두지 않았으므로 값이
  // 없으면 막대가 투명해진다 — 손잡이를 못 찾아 물러나는 경로에서도 트랙은 보여야 한다.
  if (track) {
    track.style.setProperty('--capa-scrollbar-track', String(data?.trackColor || ''))
    track.style.setProperty('--capa-scrollbar-thumb', String(data?.thumbColor || ''))
    track.style.setProperty('--capa-scrollbar-thumb-hover', String(data?.thumbHoverColor || ''))
    track.style.setProperty('--capa-scrollbar-thumb-active', String(data?.thumbActiveColor || ''))
  }
  if (!track || !thumb) return

  // **Streamlit 은 `data` 가 바뀌면 앞 인스턴스를 정리하지 않고 이 모듈을 다시 실행한다.**
  // 돌려주는 정리 함수는 unmount 때 한 번만 불리고, HTML 은 다시 그리지 않아 track 이 같은
  // 노드다. 그래서 손수 끊지 않으면 리스너가 겹쳐 붙어 휠 한 칸이 두 칸·세 칸으로 움직이고,
  // 죽은 인스턴스의 `MutationObserver` 가 계속 남아 스크롤 위치를 자기 오프셋으로 되돌린다.
  //
  // `data` 가 고정이던 동안에는 이 경로가 아예 돌지 않았다. 조회기간·과거 구간에 따라
  // 변하는 `initialOffsetPx` 가 들어오면서 처음으로 살아났다.
  if (typeof track.__capaScrollbarTeardown === 'function') track.__capaScrollbarTeardown()

  const height = Math.max(4, Number(data?.height) || 12)
  const minThumbWidth = Math.max(height * 2, Number(data?.minThumbWidth) || 40)
  const targetSelector = String(data?.targetSelector || '')
  const initialOffsetPx = Math.max(0, Number(data?.initialOffsetPx) || 0)
  // 적용한 오프셋을 **대상 요소에** 적어 둔다. 이 모듈이 rerun 마다 다시 실행되더라도
  // 대상 DOM 이 살아 있으면 표시도 함께 살아남아, 사용자가 옮겨 둔 위치를 뺏지 않는다.
  // 값까지 적는 것은 조회기간이 바뀌어 오프셋 자체가 달라졌을 때는 다시 맞춰야 해서다.
  const INITIAL_OFFSET_MARK = 'capaInitialScrollOffset'
  track.style.height = `${height}px`

  let target = null
  let targetResizeObserver = null
  let pendingInitialOffset = false
  let dragPointerId = null
  let dragStartX = 0
  let dragStartScrollLeft = 0

  const scrollLimit = () => target ? Math.max(target.scrollWidth - target.clientWidth, 0) : 0

  const thumbMetrics = () => {
    if (!target) return { width: 0, travel: 0 }
    const trackWidth = track.clientWidth
    const contentWidth = Math.max(target.scrollWidth, 1)
    const proportionalWidth = trackWidth * target.clientWidth / contentWidth
    const width = Math.min(trackWidth, Math.max(minThumbWidth, proportionalWidth))
    return { width, travel: Math.max(trackWidth - width, 0) }
  }

  const applyInitialOffset = (limit) => {
    if (!pendingInitialOffset || !target) return
    // 차트가 아직 안 그려졌으면 한도가 0 이라 어디로도 못 간다. `ResizeObserver` 가
    // 폭을 잡은 뒤 다시 불러 주므로 이번에는 그냥 둔다.
    if (limit <= 0 && initialOffsetPx > 0) return
    pendingInitialOffset = false
    target.dataset[INITIAL_OFFSET_MARK] = String(initialOffsetPx)
    target.scrollLeft = Math.min(initialOffsetPx, limit)
  }

  const render = () => {
    if (!target) {
      track.hidden = true
      return
    }
    const limit = scrollLimit()
    applyInitialOffset(limit)
    track.hidden = limit <= 0
    if (limit <= 0) return

    const { width, travel } = thumbMetrics()
    const left = travel * target.scrollLeft / limit
    thumb.style.width = `${width}px`
    thumb.style.transform = `translateX(${left}px)`
    track.setAttribute('aria-valuenow', String(Math.round(100 * target.scrollLeft / limit)))
  }

  const detachTarget = () => {
    if (target) target.removeEventListener('scroll', render)
    if (targetResizeObserver) targetResizeObserver.disconnect()
    targetResizeObserver = null
    target = null
    // 떼어 낸 요소를 겨냥하던 예약은 함께 버린다. 남겨 두면 다음에 붙는 다른 요소가
    // 이 예약을 물려받는다.
    pendingInitialOffset = false
  }

  const attachTarget = () => {
    const nextTarget = document.querySelector(targetSelector)
    if (nextTarget === target) {
      render()
      return
    }
    detachTarget()
    if (!nextTarget) {
      render()
      return
    }
    target = nextTarget
    // 새로 그려진 요소는 스크롤이 0 에서 시작하므로 맞춰 준다. 같은 요소가 그대로면
    // 표시가 남아 있어 건드리지 않는다 — 그것이 곧 사용자가 보고 있던 위치다.
    pendingInitialOffset = target.dataset[INITIAL_OFFSET_MARK] !== String(initialOffsetPx)
    target.addEventListener('scroll', render, { passive: true })
    targetResizeObserver = new ResizeObserver(render)
    targetResizeObserver.observe(target)
    if (target.firstElementChild) targetResizeObserver.observe(target.firstElementChild)
    render()
  }

  const scrollToTrackPosition = (clientX) => {
    if (!target) return
    const { width, travel } = thumbMetrics()
    const bounds = track.getBoundingClientRect()
    const nextLeft = Math.min(Math.max(clientX - bounds.left - width / 2, 0), travel)
    target.scrollLeft = travel > 0 ? scrollLimit() * nextLeft / travel : 0
  }

  const onPointerDown = (event) => {
    if (!target || scrollLimit() <= 0) return
    event.preventDefault()
    track.focus({ preventScroll: true })
    if (event.target !== thumb) {
      scrollToTrackPosition(event.clientX)
    }
    dragPointerId = event.pointerId
    dragStartX = event.clientX
    dragStartScrollLeft = target.scrollLeft
    track.setPointerCapture(event.pointerId)
    track.classList.add('is-dragging')
  }

  const onPointerMove = (event) => {
    if (!target || event.pointerId !== dragPointerId) return
    const { travel } = thumbMetrics()
    if (travel <= 0) return
    target.scrollLeft = dragStartScrollLeft + (
      (event.clientX - dragStartX) * scrollLimit() / travel
    )
  }

  const finishDrag = (event) => {
    if (event.pointerId !== dragPointerId) return
    dragPointerId = null
    track.classList.remove('is-dragging')
    if (track.hasPointerCapture(event.pointerId)) track.releasePointerCapture(event.pointerId)
  }

  const onWheel = (event) => {
    if (!target || scrollLimit() <= 0) return
    event.preventDefault()
    target.scrollLeft += Math.abs(event.deltaX) > Math.abs(event.deltaY)
      ? event.deltaX
      : event.deltaY
  }

  const onKeyDown = (event) => {
    if (!target || scrollLimit() <= 0) return
    const pageStep = Math.max(target.clientWidth * 0.8, 80)
    const keyActions = {
      ArrowLeft: () => { target.scrollLeft -= 80 },
      ArrowRight: () => { target.scrollLeft += 80 },
      PageUp: () => { target.scrollLeft -= pageStep },
      PageDown: () => { target.scrollLeft += pageStep },
      Home: () => { target.scrollLeft = 0 },
      End: () => { target.scrollLeft = scrollLimit() },
    }
    const action = keyActions[event.key]
    if (!action) return
    event.preventDefault()
    action()
  }

  track.addEventListener('pointerdown', onPointerDown)
  track.addEventListener('pointermove', onPointerMove)
  track.addEventListener('pointerup', finishDrag)
  track.addEventListener('pointercancel', finishDrag)
  track.addEventListener('wheel', onWheel, { passive: false })
  track.addEventListener('keydown', onKeyDown)

  const trackResizeObserver = new ResizeObserver(render)
  trackResizeObserver.observe(track)
  const documentObserver = new MutationObserver(attachTarget)
  documentObserver.observe(document.body, { childList: true, subtree: true })
  attachTarget()

  const teardown = () => {
    if (track.__capaScrollbarTeardown === teardown) delete track.__capaScrollbarTeardown
    documentObserver.disconnect()
    trackResizeObserver.disconnect()
    detachTarget()
    track.removeEventListener('pointerdown', onPointerDown)
    track.removeEventListener('pointermove', onPointerMove)
    track.removeEventListener('pointerup', finishDrag)
    track.removeEventListener('pointercancel', finishDrag)
    track.removeEventListener('wheel', onWheel)
    track.removeEventListener('keydown', onKeyDown)
  }
  // 다음 실행이 찾아서 끊을 수 있도록 track 에 걸어 둔다. 돌려주기도 해야 unmount 경로가
  // 그대로 산다.
  track.__capaScrollbarTeardown = teardown
  return teardown
}
"""

_HORIZONTAL_SCROLLBAR = st.components.v2.component(
    "capa_horizontal_scrollbar",
    html=_SCROLLBAR_HTML,
    css=_SCROLLBAR_CSS,
    js=_SCROLLBAR_JS,
)


def render_horizontal_scrollbar(
    *,
    target_selector: str,
    height: int,
    key: str,
    min_thumb_width: int = 40,
    initial_offset_px: float = 0.0,
) -> None:
    """Render a pixel-sized scrollbar synchronized with a page scroll container.

    `initial_offset_px` 는 **처음 그려질 때 한 번만** 걸리는 시작 위치다. 왼쪽 끝이
    언제나 맞는 자리는 아니다 — HOME 은 과거 구간을 앞에 붙여 그리므로 그만큼 지나야
    DB 계산 구간의 첫 달이 왼쪽에 선다.

    **리런마다 다시 걸지 않는다.** 대상 요소에 적용값을 적어 두고, 같은 요소가 살아
    있으면 건너뛴다. 그러지 않으면 사용자가 옮겨 둔 위치를 리런이 계속 되돌린다.
    """
    if height < 4:
        raise ValueError("스크롤바 높이는 4px 이상이어야 합니다.")
    if initial_offset_px < 0:
        raise ValueError("스크롤 시작 위치는 0 이상이어야 합니다.")
    _HORIZONTAL_SCROLLBAR(
        key=key,
        data={
            "targetSelector": target_selector,
            "height": height,
            "minThumbWidth": min_thumb_width,
            "initialOffsetPx": float(initial_offset_px),
            # 토큰을 **여기서** 읽는다. 실행마다 도는 자리라야 테마를 따라온다 —
            # 모듈 최상위에서 읽으면 처음 읽은 테마의 색이 프로세스에 굳는다.
            "trackColor": tokens.SCROLLBAR_TRACK,
            "thumbColor": tokens.SCROLLBAR_THUMB,
            "thumbHoverColor": tokens.SCROLLBAR_THUMB_HOVER,
            "thumbActiveColor": tokens.SCROLLBAR_THUMB_ACTIVE,
        },
        width="stretch",
        height=height,
    )
