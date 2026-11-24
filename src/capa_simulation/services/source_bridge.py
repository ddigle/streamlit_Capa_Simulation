# Purpose: 원천 CSV 를 「다리」 원천으로 가린다 — 불변 검사 · 「등록됨」 셈에서 빼는 판정 한 곳.

"""원천 CSV 는 DB 가 그 코드를 적재하기 전까지 건너는 「다리」 원천이다(사용자 물음 Q-C1
(나) — `docs/TODO.md` 2장 「BigDataQuery 어댑터·등록」).

- 원천 코드 불변 검사(`persistence/source_data_store.validate_immutable_source_code`)는 다리
  아닌 원천(DB 조회 등)을 받을 때 다리 원천의 해시를 견주지 않는다(`compared_source_hashes`) —
  다음 날 같은 코드가 DB 에 오면 CSV 원천과 바이트가 달라도 DB 등록이 선다. 다리 원천을 받을
  때는 지금처럼 모든 원천과 견준다(같은 코드의 CSV 원천은 한 벌이고, DB 원천이 먼저 있으면
  바이트가 같은 파일만 받는다).
- 「등록됨」 셈 — 공식버전 자동 갱신이 건너뛰는 코드와 DB 등록 탭 DB 목록의 등록여부 · 표시
  범위 — 은 다리 원천 시나리오를 빼고 센다(`settled_source_codes`). CSV 목록의 등록여부는 모든
  시나리오로 센다 — 앞선 원천이 어느 길이든 CSV 로 다시 받을 까닭이 없다.
- 원천 CSV 등록 칸의 시나리오명 처음 값 끝에 `BRIDGE_NAME_TAIL` 을 단다 — 다음 날 같은 코드를
  DB 로 받는 시나리오(「<원천명> (<코드>)」)와 이름이 겹치면 그 등록 · 자동 갱신 회차가 같은
  이름으로 멈춘다.

가르는 것은 원천 유형이 `CSV_CORE_DATA_UPLOAD` 와 같을 때뿐이다 — 초기 이관 스크립트의
`CSV_CORE_DATA_INITIAL_*` · 복제 · 파생은 다리가 아니다.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final, Protocol

from capa_simulation.io.source_csv import SOURCE_CSV_SOURCE_TYPE

BRIDGE_SOURCE_TYPES: Final[frozenset[str]] = frozenset({SOURCE_CSV_SOURCE_TYPE})
BRIDGE_NAME_TAIL: Final = " · CSV"


class SourceRecord(Protocol):
    """「등록됨」 셈이 읽는 두 칸 — 저장소 시나리오 요약(`ScenarioSummary`)이 맞는다."""

    @property
    def source_simulation_code(self) -> str: ...

    @property
    def source_type(self) -> str: ...


def is_bridge_source(source_type: str) -> bool:
    """다리 원천(원천 CSV 올림)인가 — 원천 유형이 글자 그대로 같을 때만."""
    return source_type in BRIDGE_SOURCE_TYPES


def compared_source_hashes(existing: Iterable[tuple[str, str]], incoming_type: str) -> set[str]:
    """원천 코드 불변 검사가 새 원천과 견줄 해시 — 같은 코드에 저장된 (원천 해시, 원천 유형) 가운데.

    다리 아닌 원천을 받으면 다리 원천의 해시를 빼고, 다리 원천을 받으면 모두 견준다.
    """
    if is_bridge_source(incoming_type):
        return {data_hash for data_hash, _ in existing}
    return {data_hash for data_hash, kind in existing if not is_bridge_source(kind)}


def settled_source_codes(scenarios: Iterable[SourceRecord]) -> frozenset[str]:
    """「등록됨」 으로 셀 원천 코드 — 다리 원천 시나리오를 뺀다(보관본은 부르는 쪽이 넣는다)."""
    return frozenset(
        str(scenario.source_simulation_code)
        for scenario in scenarios
        if not is_bridge_source(scenario.source_type)
    )
