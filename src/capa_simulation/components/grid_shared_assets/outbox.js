// 표 공용 조각 — 보낼 목록(순수). 설비 마스터 표와 시나리오 목록 표가 함께 쓴다. base 가 바뀔 때 무엇을 하는지는 표마다 다르다
// (설비 마스터는 `rebaseBox` 로 비우고 목록 표는 남겨 서버가 세어 알린다).

// <grid-outbox>
// 보낼 목록. seq 는 마운트 안에서 늘 늘고, ack 가 온 seq 이하는 뺀다. base 가 바뀌면 통째로 버린다.
function opCells(op) {
  if (op.op === 'paste') return (op.rows || []).reduce((sum, line) => sum + line.filter((v) => v !== null).length, 0)
  if (op.op === 'set') return (op.ids || []).length
  if (op.op === 'shift') return (op.ids || []).length * 2
  return 1
}

function createBox() {
  return { seq: 0, ops: [], base: null }
}

function boxCells(box) {
  return box.ops.reduce((sum, op) => sum + opCells(op), 0)
}

function queueOp(box, op, limit, now) {
  if (boxCells(box) + opCells(op) > limit) return null
  box.seq += 1
  const queued = Object.assign({}, op, { seq: box.seq, base: box.base, at: now })
  box.ops.push(queued)
  return queued
}

function ackBox(box, seq) {
  const before = box.ops.length
  box.ops = box.ops.filter((op) => op.seq > seq)
  return before - box.ops.length
}

function rebaseBox(box, base) {
  if (box.base === base) return false
  const had = box.base !== null
  box.base = base
  box.ops = []
  return had
}

// 아직 ack 가 오지 않은 같은 op(이름과 인자가 모두 같은 것)가 보낼 목록에 있는가. 띠 「넣기」·「밀기」, 상세 「되살리기」 같은
// 단추의 더블클릭은 둘째 누름이 첫 op 의 회차가 돌아오기 전(단추를 다시 그리기 전)에 닿는다 — 그 누름은 보내지 않는다.
function hasPendingOp(box, op) {
  const keys = Object.keys(op)
  return box.ops.some((queued) => keys.every((key) => JSON.stringify(queued[key]) === JSON.stringify(op[key])))
}
// </grid-outbox>
