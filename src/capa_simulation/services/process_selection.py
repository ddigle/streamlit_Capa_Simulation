# Purpose: B/N 집계에 포함할 공정 목록을 저장값·현재 옵션·직전 옵션에서 정한다.

"""포함 공정 판정.

저장되는 것은 **포함 목록**이라 "사용자가 끈 공정" 과 "이번에 처음 보는 공정" 이 구분되지
않는다. 직전 실행의 옵션 집합을 함께 들고 있다가 그때 없던 공정만 새 공정으로 보아 포함한다
— 시나리오를 바꾸거나 과거 구간을 넣어 공정이 늘었을 때 그것들이 조용히 빠지면 B/N 이 틀린다.

그 규칙에는 기준이 필요하다. 기준이 없는 첫 렌더에 같은 규칙을 쓰면 **모든 공정이 처음 보는
공정**이 되어 저장된 포함 목록이 통째로 덮인다.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def resolve_included_processes(
    saved: Iterable[str],
    options: Sequence[str],
    seen: Iterable[str] | None,
) -> list[str]:
    """이번 화면에서 포함할 공정. `options` 의 차례를 따른다.

    `seen` 이 `None` 이면 비교할 직전 옵션 집합이 없다는 뜻이다. 그때는 저장된 포함 목록을
    그대로 믿는다 — 공식버전이 저장해 둔 공정 필터가 새 세션의 첫 화면에서 사라지지 않도록.
    `seen` 이 빈 목록인 것과는 다르다. 그쪽은 "직전에 옵션이 하나도 없었다" 는 관측이다.
    """
    kept = {process for process in saved if process in options}
    if seen is None:
        return [process for process in options if process in kept]
    seen_processes = set(seen)
    return [process for process in options if process in kept or process not in seen_processes]
