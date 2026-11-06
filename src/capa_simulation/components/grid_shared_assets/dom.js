// 표 공용 조각 — DOM 도우미. 설비 마스터 표와 시나리오 목록 표가 함께 쓴다. 데이터 글은 textContent 로만 넣고 innerHTML 은 고정 아이콘에만 쓴다.

const ICONS = {
  search: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="M20 20l-3.5-3.5"></path></svg>',
  close: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"></path></svg>',
  minus: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M5 12h14"></path></svg>',
  undo: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 14L4 9l5-5"></path><path d="M4 9h10a6 6 0 0 1 0 12h-3"></path></svg>',
  down: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"></path></svg>',
}

function el(tag, className, text) {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text !== undefined && text !== null) node.textContent = String(text)
  return node
}

// 글 칸 편집기 — 줄바꿈이 든 값(엑셀 Alt+Enter 칸을 가져온 것)은 여러 줄 칸(textarea)으로 연다. 한 줄 칸(input)은 줄바꿈을
// 지워 「첫째⏎둘째」 가 「첫째둘째」 로 들어가, 끝에 한 글자만 붙여도(호기 상세는 Enter 만 눌러도) 줄바꿈이 말없이 빠진 값이 바뀐
// 칸으로 남았다(2026-10-27 E2E). Enter 는 두 칸 모두 확정이다 — 줄을 새로 넣는 길은 없고 있던 줄바꿈을 지킨다.
function textEditor(className, value) {
  const lines = String(value || '').split('\n').length
  const node = el(lines > 1 ? 'textarea' : 'input', className)
  if (lines > 1) node.rows = Math.min(lines, 6)
  node.value = value
  return node
}

function button(className, text, onClick) {
  const node = el('button', className, text)
  node.type = 'button'
  if (onClick) node.addEventListener('click', onClick)
  return node
}

function icon(name, label, onClick) {
  const node = button('emg-icon', null, onClick)
  node.innerHTML = ICONS[name]
  node.setAttribute('aria-label', label)
  node.title = label
  return node
}

function newMount() {
  return 'm-' + Math.random().toString(36).slice(2, 8) + Date.now().toString(36).slice(-4)
}

function listen(S, target, type, handler, options) {
  target.addEventListener(type, handler, options)
  S.listeners.push([target, type, handler, options])
}

function cssEscape(text) {
  return String(text).replace(/["\\]/g, '\\$&')
}

// 그림자 DOM 안에서는 document.activeElement 가 호스트다 — 그 칸이 든 뿌리의 activeElement 를 본다.
function activeIn(node) {
  const root = node.getRootNode ? node.getRootNode() : document
  return root.activeElement || null
}

function stopKeys(event) {
  // 칸·찾기 칸의 키는 문서로 올려 보내지 않는다 — Streamlit 문서 단축키(r 다시 실행·c 캐시)가 글자를 먹는다.
  event.stopPropagation()
}
