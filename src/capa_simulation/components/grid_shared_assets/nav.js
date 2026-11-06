// 표 공용 조각 — 옆·위아래 칸 찾기(순수). 설비 마스터 표와 시나리오 목록 표가 함께 쓴다. DOM 을 모르므로 node 시험이 떼어 돌린다.

// <grid-nav>
// 옆·위아래 칸. 잠긴 칸·지운 줄은 건너뛰고 한 방향으로 `limit` 칸까지만 찾는다.
function nextCell(rowCount, colCount, from, dir, editable, limit) {
  let row = from.row
  let col = from.col
  const most = Number.isInteger(limit) ? limit : 80
  for (let step = 0; step < most; step += 1) {
    if (dir === 'right') col += 1
    else if (dir === 'left') col -= 1
    else if (dir === 'down') row += 1
    else row -= 1
    if (row < 0 || row >= rowCount || col < 0 || col >= colCount) return null
    if (editable(row, col)) return { row, col }
  }
  return null
}

// 화살표가 옮겨 갈 칸(행 id·칸 번호). `ids` 는 **화면 차례의 모든 줄**이다 — 지운 줄도 줄이라, 지운 줄에 남은
// 초점에서 ↓ 는 아랫줄로 가고(맨 첫 줄로 뛰지 않는다) 화살표로 지운 줄에 돌아와 Space 로 되살릴 수 있다. 지금 칸을
// 못 찾으면 움직이지 않는다.
function moveFocus(ids, cols, at, dir) {
  const from = { row: ids.indexOf(at.id), col: cols.indexOf(at.col) }
  if (from.row < 0 || from.col < 0) return null
  const next = nextCell(ids.length, cols.length, from, dir, () => true, 1)
  return next ? { id: ids[next.row], col: cols[next.col] } : null
}
// </grid-nav>
