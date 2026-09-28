# Purpose: 리비전 저장·공식 발행 전에 시나리오 전체 기간 Capa 계산이 되는지 검사한다.

"""**오류를 만든 사람이 그 자리에서 보게 한다.**

계산 페이지는 시나리오 어느 달이든 기준정보 오류가 있으면 멈춘다(`simulation_cache`). 그것만
있으면 오류는 HOME 을 연 사람 — 대개 고칠 수 없는 사람 — 이 처음 본다. 쓰는 순간과 보는
순간이 갈라져 있으면, 쓸 때 통과한 것이 볼 때 터지는 일이 쌓인다(표시순서 대소문자,
0014 TOP 누락, 빈 UPEH 의 측정률 짝이 모두 그 모양이었다).

그래서 같은 전체 기간 계산을 **저장·발행 순간**에 한 번 돌린다.

- **리비전 저장:** 편집본이 계산되지 않는데 편집 전 리비전은 계산되면 → 이 편집이 깨뜨린
  것이므로 막는다. 편집 전부터 계산되지 않았으면 → 저장은 허락하고 경고한다. 막으면 오류가
  여럿일 때 하나씩 고쳐 가며 저장할 길이 없어진다.
- **공식 발행:** 계산되지 않으면 막는다. 공식버전은 모든 사용자의 첫 화면이라, 지정하는 순간
  모두의 HOME 이 멈춘다.

BigDataQuery 등록과 내장 시드 부트스트랩은 검사하지 않는다 — 들어온 원천을 앱 안에서 고칠
길을 막지 않기 위해서다. 등록한 원천의 오류는 계산 페이지와 발행 검사가 드러낸다.

검사는 계산 페이지와 **같은 캐시 칸**을 쓴다. 발행이 통과하면 그 리비전의 HOME 계산이 이미
데워져 있다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

import pandas as pd

from capa_simulation.io.reference_cache import reference_version_for_revision
from capa_simulation.persistence.cache import load_scenario_snapshot
from capa_simulation.scenario_state import ActiveScenario, pristine_content_token
from capa_simulation.services.simulation_cache import get_full_capacity_outcome


class GateVerdict(NamedTuple):
    """막을지와 그 이유. 허락하면서 경고할 때도 `message` 가 있다."""

    allowed: bool
    message: str | None = None


def revision_save_verdict(
    reference_version: int,
    active_scenario: ActiveScenario,
    reference_tables: Mapping[str, pd.DataFrame],
) -> GateVerdict:
    """편집본을 새 리비전으로 저장해도 되는지."""
    edited = get_full_capacity_outcome(
        (reference_version, active_scenario["content_token"]),
        _scenario_tables=active_scenario["tables"],
        _reference_tables=reference_tables,
    ).error
    if edited is None:
        return GateVerdict(True)
    base_token = pristine_content_token(reference_version)
    # 편집 전 상태는 세션 기준정보(= 활성 리비전 스냅샷)다. 계산 페이지가 같은 키로 이미
    # 계산해 두었으면 캐시에서 바로 나온다.
    base = (
        edited
        if active_scenario["content_token"] == base_token
        else get_full_capacity_outcome(
            (reference_version, base_token),
            _scenario_tables=reference_tables,
            _reference_tables=reference_tables,
        ).error
    )
    if base is None:
        return GateVerdict(
            False,
            "이 편집으로 Capa 계산이 실패해 저장하지 않았습니다. 편집 전 리비전은 계산되므로 "
            f"이번 편집이 깨뜨린 것입니다 — 고친 뒤 다시 저장하세요. 오류: {edited}",
        )
    return GateVerdict(
        True,
        "편집 전부터 있던 Capa 계산 오류가 아직 남아 있습니다. 이 리비전은 공식버전으로 "
        f"지정할 수 없습니다 — 남은 오류를 고쳐 다시 저장하세요. 오류: {edited}",
    )


def official_publish_verdict(database_path: str, revision_id: str) -> GateVerdict:
    """저장된 리비전을 공식버전으로 지정해도 되는지."""
    snapshot = load_scenario_snapshot(database_path, revision_id)
    reference_version = reference_version_for_revision(revision_id)
    error = get_full_capacity_outcome(
        (reference_version, pristine_content_token(reference_version)),
        _scenario_tables=snapshot.tables,
        _reference_tables=snapshot.tables,
    ).error
    if error is None:
        return GateVerdict(True)
    return GateVerdict(
        False,
        "이 리비전은 Capa 계산이 실패해 공식버전으로 지정할 수 없습니다. 공식버전은 모든 "
        "사용자가 처음 여는 화면이라, 지정하면 모두의 HOME 이 멈춥니다. 기준 정보 페이지에서 "
        f"고친 뒤 새 리비전으로 저장하고 그 리비전을 지정하세요. 오류: {error}",
    )
