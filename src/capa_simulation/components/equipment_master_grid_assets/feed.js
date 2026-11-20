// 설비 마스터 표 feed — 작은 등록 `capa_equipment_master_grid_feed` 의 JS. data(ack · 껍데기 뒤 바뀐 줄 · 수 · 옮김 · 연 줄)를
// window.__capaEquipmentGrid[host].feed 칸에 두고 'capa-equipment-grid' 이벤트를 쏜다. 표 JS 가 마운트 때 칸을 읽고 이 이벤트를
// 듣는다(차례에 기대지 않는다 — feed 의 shell 이 껍데기와 다르면 칸에 둔 채 그 껍데기가 오면 그때 쓴다).
export default function ({ data }) {
  if (!data || typeof data.host !== 'string' || !/^[\w-]+$/.test(data.host)) return
  const store = (window.__capaEquipmentGrid = window.__capaEquipmentGrid || {})
  const slot = (store[data.host] = store[data.host] || {})
  slot.feed = data
  window.dispatchEvent(new CustomEvent('capa-equipment-grid', { detail: data.host }))
}
