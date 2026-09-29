# Purpose: HOME 주요공정 히트맵이 그릴 공정 목록·프리셋의 상한과 정규화를 담당한다.

"""주요공정 목록.

**주요공정은 「무엇을 볼 것인가」이지 「무엇을 계산할 것인가」가 아니다.** 이 목록은
계산에 들어가지 않고 HOME 대시보드의 한 구획이 어떤 행을 그릴지만 정한다. 그래서
시나리오에 종속되지 않는 공용 프로필이고, 바뀌어도 `content_token` 을 재발급하지 않는다.

**고른 차례가 곧 행 순서다.** 확보율이 낮은 순으로 다시 정렬하지 않는다 — 그러면 매달
행이 뛰어다녀 「이 공정이 언제 무너지나」를 가로로 훑을 수가 없다. 순서를 바꾸는 것은
사용자의 결정이고, 그 결정은 저장된 차례에 남는다.

상한이 있는 것은 이 구획이 **계획 세부수량과 상세 B/N 사이에 끼어 있기** 때문이다.
행이 늘면 아래 구획이 그만큼 화면 밖으로 밀린다. 칸마다 확보율 숫자를 적으므로 주석
수도 `공정 수 × 월 수` 로 늘어난다.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

# 히트맵 행 수의 상한. 구획 높이(행당 29px)와 주석 수를 여기 하나로 묶어 둔다.
KEY_PROCESS_LIMIT = 15


def normalize_key_processes(values: Iterable[str]) -> tuple[str, ...]:
    """저장·적용 공용 정규화. 빈 값과 중복을 버리고 첫 등장 차례를 지킨다.

    빈 목록은 오류가 아니라 **「하나도 고르지 않는다」는 결정**이다. 그때 HOME 은 구획을
    안내 문구 한 줄로 남긴다.
    """
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        process = str(value).strip()
        if not process or process in seen:
            continue
        seen.add(process)
        normalized.append(process)
    if len(normalized) > KEY_PROCESS_LIMIT:
        raise ValueError(f"주요공정은 최대 {KEY_PROCESS_LIMIT}개까지 고를 수 있습니다.")
    return tuple(normalized)


# 프리셋(2026-09-29 사용자 요청). 「A 그룹은 A·B·C·D, B 그룹은 D·E·F·G」처럼 이름 붙인 공정 묶음을
# 여럿 저장해 두고 HOME 사이드바에서 골라 본다. 한 공정이 여러 프리셋에 들어갈 수 있다.
KEY_PROCESS_PRESET_LIMIT = 20
PRESET_NAME_LIMIT = 30

Preset = tuple[str, tuple[str, ...]]


def normalize_preset_name(value: str) -> str:
    """프리셋 이름. 앞뒤 공백을 떼고, 비었거나 너무 길면 막는다."""
    name = str(value).strip()
    if not name:
        raise ValueError("프리셋 이름을 적으세요.")
    if len(name) > PRESET_NAME_LIMIT:
        raise ValueError(f"프리셋 이름은 {PRESET_NAME_LIMIT}자까지입니다.")
    return name


def normalize_key_process_presets(
    presets: Iterable[tuple[str, Iterable[str]]],
) -> tuple[Preset, ...]:
    """저장 전 프리셋 묶음 정규화. 차례를 지키고 이름 중복·빈 프리셋·상한을 막는다.

    **빈 프리셋은 막는다.** 단일 목록 시절의 「전체 해제」는 이제 프리셋을 지우는 것이다 —
    이름만 있고 공정이 없는 프리셋은 고르면 히트맵이 비어 고장으로 읽힌다.
    """
    normalized: list[Preset] = []
    seen: set[str] = set()
    for raw_name, raw_processes in presets:
        name = normalize_preset_name(raw_name)
        if name in seen:
            raise ValueError(f"같은 이름의 프리셋이 이미 있습니다: {name}")
        processes = normalize_key_processes(raw_processes)
        if not processes:
            raise ValueError(f"프리셋 「{name}」에 공정을 하나 이상 고르세요.")
        seen.add(name)
        normalized.append((name, processes))
    if len(normalized) > KEY_PROCESS_PRESET_LIMIT:
        raise ValueError(f"프리셋은 최대 {KEY_PROCESS_PRESET_LIMIT}개까지 저장할 수 있습니다.")
    return tuple(normalized)


def resolve_preset_name(names: Sequence[str], chosen: object) -> str | None:
    """지금 볼 프리셋. 고른 것이 없거나 지워졌으면 **첫 프리셋(기본)** 이다. 없으면 None."""
    if isinstance(chosen, str) and chosen in names:
        return chosen
    return names[0] if names else None
