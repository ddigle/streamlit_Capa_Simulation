# Purpose: 공용 프로필의 버전·출처·저장시각 캡션 한 줄을 한 규칙으로 만든다.

"""공용 프로필 버전 캡션.

`GlobalAdvanceLoad`·`GlobalPastData`·`GlobalKeyProcess` 처럼 시나리오와 분리된 공용
프로필은 모두 `version`·`source`·`updated_at` 세 필드를 갖고, 저장 화면은 그 셋을 같은
모양의 한 줄로 적는다. 그 템플릿이 여덟 자리에 따로 적혀 있어 한 곳만 고치면 화면마다
문구가 갈렸다 — 규칙을 여기 하나로 둔다.

`empty` 문구만 프로필마다 다르다. 「아직 넣은 선행 물량이 없습니다」처럼 무엇이 비었는지
말해야 하고, 값을 끼워 만드는 자리도 있어 호출부가 완성해 넘긴다.

모델을 import 하지 않는다. `persistence.models` 를 붙잡으면 화면 조각 하나가 저장 계층을
끌고 들어오고, 프로필이 늘 때마다 이 모듈도 같이 고쳐야 한다. 구조적 타입(Protocol)으로
세 필드만 요구한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

VERSION_CAPTION_PREFIX = "공용 버전 "
CAPTION_SEPARATOR = " · "


class HasProfileVersion(Protocol):
    """버전 캡션을 만들 수 있는 공용 프로필의 최소 모양.

    **읽기 전용 `@property` 로 선언한다.** 평범한 속성 주석은 불변(invariant)이라
    `GlobalDisplayOrder.updated_at: datetime` 이 `datetime | None` 에 맞지 않아 mypy
    strict 가 거절한다. 읽기 전용이면 공변이라 둘 다 받는다.
    """

    @property
    def version(self) -> int: ...

    @property
    def source(self) -> str: ...

    @property
    def updated_at(self) -> datetime | None: ...


def profile_version_caption(
    profile: HasProfileVersion,
    *,
    empty: str,
    detail: str | None = None,
    suffix: str | None = None,
) -> str:
    """공용 프로필 한 줄 캡션.

    `version == 0` 은 **한 번도 저장하지 않은 상태**라 버전 대신 `empty` 문구를 적는다.
    저장된 뒤에는 `v{version} · [detail ·] source [· 저장시각] [· suffix]` 순으로 잇는다.
    `detail` 은 출처 앞(「3개 공정」), `suffix` 는 맨 뒤(「공지 중」)에 붙는다.
    """
    if profile.version == 0:
        return f"{VERSION_CAPTION_PREFIX}없음{CAPTION_SEPARATOR}{empty}"
    parts = [f"v{profile.version}"]
    if detail is not None:
        parts.append(detail)
    parts.append(profile.source)
    if profile.updated_at is not None:
        parts.append(format(profile.updated_at, "%Y-%m-%d %H:%M"))
    if suffix is not None:
        parts.append(suffix)
    return VERSION_CAPTION_PREFIX + CAPTION_SEPARATOR.join(parts)
