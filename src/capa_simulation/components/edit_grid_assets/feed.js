// 범용 편집 그리드 feed — 작은 등록 `capa_edit_grid_feed` 의 JS. data(초안·오류·ack·수·토스트·필터)를 window.__capaEditGrid[host].feed
// 칸에 두고 'capa-edit-grid' 이벤트를 쏜다. 무거운 그리드 JS 가 마운트 때 칸을 읽고 이 이벤트를 듣는다(차례에 기대지 않는다).
export default function ({ data }) {
  if (!data || typeof data.host !== 'string' || !/^[\w-]+$/.test(data.host)) return
  const store = (window.__capaEditGrid = window.__capaEditGrid || {})
  const slot = (store[data.host] = store[data.host] || {})
  slot.feed = data
  window.dispatchEvent(new CustomEvent('capa-edit-grid', { detail: data.host }))
}
