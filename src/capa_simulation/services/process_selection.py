# Purpose: B/N 집계에 포함할 공정 목록을 저장값·현재 옵션·이미 아는 공정에서 정한다.

"""포함 공정 판정.

저장되는 것은 **포함 목록**이라 "사용자가 끈 공정" 과 "이번에 처음 보는 공정" 이 구분되지
않는다. 이 세션이 이미 아는 공정(`seen`)을 함께 들고 있다가 거기 없던 공정만 새 공정으로 보아
포함한다 — 시나리오를 바꾸거나 과거 구간을 넣어 공정이 늘었을 때 그것들이 조용히 빠지면 B/N 이
틀린다.

그 규칙에는 기준이 필요하다. 기준이 없는 첫 렌더에 같은 규칙을 쓰면 **모든 공정이 처음 보는
공정**이 되어 저장된 포함 목록이 통째로 덮인다.

두 가지를 지킨다(2026-10-15 공식버전 자동 갱신 리뷰).

- **보이지 않는 공정은 지우지 않는다.** 조회기간 안에 가용 행이 없거나 확보율 표에 없는 공정은
  이번 선택지(`options`)에 없다. 사람이 토글할 수 없었던 공정이므로 저장값에 있던 대로 남긴다 —
  지우면 그 세션이 저장한 리비전 프리셋에서 조용히 빠져, 공식버전 자동 갱신이 그 공정을 「사람이 끈
  공정」으로 이어받는다.
- **아는 공정은 쌓는다.** `seen` 은 직전 회차의 선택지가 아니라 이 세션이 지금까지 안 공정 전부다
  (프리셋을 걸면 지운다). 처음에는 리비전의 `RQ_REQB` 공정에서 출발한다. 그래서 조회기간을 좁혔다
  넓혀 다시 보인 공정은 새 공정이 아니라 저장값을 따른다 — 프리셋이 뺀 공정이 되살아나지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

import pandas as pd


def resolve_included_processes(
    saved: Iterable[str],
    options: Sequence[str],
    seen: Iterable[str] | None,
) -> list[str]:
    """이번 화면에서 포함할 공정. `options` 의 차례를 따르고, 그 뒤에 `options` 밖 저장값을 둔다.

    `seen` 이 `None` 이면 비교할 기준이 없다는 뜻이다. 그때는 저장된 포함 목록을 그대로 믿는다 —
    공식버전이 저장해 둔 공정 필터가 새 세션의 첫 화면에서 사라지지 않도록. `seen` 이 빈 목록인
    것과는 다르다. 그쪽은 "아는 공정이 하나도 없었다" 는 관측이다.

    `options` 밖의 저장값은 지우지 않고 저장 차례대로 뒤에 둔다(이번 화면에서 토글할 수 없었다).
    화면의 집계는 `options` 안의 것만 읽는다(`visible_processes`).
    """
    saved_list = list(dict.fromkeys(str(process) for process in saved))
    kept = set(saved_list)
    option_set = set(options)
    if seen is None:
        fresh: set[str] = set()
    else:
        seen_processes = set(seen)
        fresh = {process for process in options if process not in seen_processes}
    inside = [process for process in options if process in kept or process in fresh]
    outside = [process for process in saved_list if process not in option_set]
    return inside + outside


def remember_known_processes(
    seen: Iterable[str] | None,
    options: Sequence[str],
    universe: Iterable[str] = (),
) -> list[str]:
    """다음 회차의 `seen` — 이미 알던 공정에 이번 선택지를 더한다(이번 선택지 먼저, 그 뒤 옛 차례).

    `seen` 이 `None`(프리셋을 건 직후·새 세션)이면 `universe`(지금 리비전의 `RQ_REQB` 공정)에서
    출발한다. 프리셋은 그 공정 전부를 두고 정한 것이라, 지금 조회기간에 보이지 않아도 이미 아는
    공정이다.
    """
    base = list(universe) if seen is None else [str(process) for process in seen]
    option_set = set(options)
    return list(options) + [process for process in dict.fromkeys(base) if process not in option_set]


def visible_processes(selection: Iterable[str], options: Sequence[str]) -> list[str]:
    """포함 목록 가운데 이번 선택지에 있는 것(선택 차례). 화면의 B/N·그림·결론이 읽는 목록이다."""
    option_set = set(options)
    return [str(process) for process in selection if process in option_set]


def apply_dialog_selection(
    chosen: Iterable[str],
    options: Sequence[str],
    current: Iterable[str],
) -> list[str]:
    """팝업에서 고른 공정(`options` 차례)에 지금 포함 목록의 `options` 밖 공정을 그대로 붙인다.

    팝업은 이번 선택지만 보여 준다. 보이지 않는 공정까지 「전체 OFF」로 지우면 안 된다.
    """
    chosen_set = {str(process) for process in chosen}
    option_set = set(options)
    hidden = [process for process in dict.fromkeys(current) if process not in option_set]
    return [process for process in options if process in chosen_set] + hidden


def revision_processes(tables: Mapping[str, pd.DataFrame]) -> list[str]:
    """리비전 표의 `RQ_REQB` 공정(공백 제거·중복 제거·이름 차례). 표가 없으면 빈 목록."""
    reqb = tables.get("RQ_REQB")
    if not isinstance(reqb, pd.DataFrame) or "공정" not in reqb.columns:
        return []
    names = reqb["공정"].astype("string").str.strip().dropna().unique().tolist()
    return sorted(str(name) for name in names if str(name))
