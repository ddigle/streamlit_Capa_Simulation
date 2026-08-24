import streamlit as st

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
  background: #ECEEF1;
  cursor: pointer;
  touch-action: none;
  user-select: none;
}

.capa-scrollbar-thumb {
  position: absolute;
  inset-block: 0;
  inset-inline-start: 0;
  box-sizing: border-box;
  border: 2px solid #ECEEF1;
  border-radius: 999px;
  background: #8F9399;
  cursor: grab;
  will-change: transform;
}

.capa-scrollbar-thumb:hover {
  background: #686D73;
}

.capa-scrollbar-track.is-dragging .capa-scrollbar-thumb {
  background: #52565C;
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
  if (!track || !thumb) return

  const height = Math.max(4, Number(data?.height) || 12)
  const minThumbWidth = Math.max(height * 2, Number(data?.minThumbWidth) || 40)
  const targetSelector = String(data?.targetSelector || '')
  track.style.height = `${height}px`

  let target = null
  let targetResizeObserver = null
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

  const render = () => {
    if (!target) {
      track.hidden = true
      return
    }
    const limit = scrollLimit()
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

  return () => {
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
) -> None:
    """Render a pixel-sized scrollbar synchronized with a page scroll container."""
    if height < 4:
        raise ValueError("스크롤바 높이는 4px 이상이어야 합니다.")
    _HORIZONTAL_SCROLLBAR(
        key=key,
        data={
            "targetSelector": target_selector,
            "height": height,
            "minThumbWidth": min_thumb_width,
        },
        width="stretch",
        height=height,
    )
