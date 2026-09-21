# Purpose: 공용 프로필 버전 캡션이 여덟 저장 화면에서 글자 단위로 같은지 고정한다.

"""**캡션 한 줄이 여덟 곳에 따로 적혀 있었다.**

`공용 버전 v3 · 붙여넣기 · 2026-01-02 03:04` 은 저장 화면마다 같은 모양이어야 한다. 그런데
템플릿이 자리마다 복사되어 있어 한 곳만 고치면 화면끼리 조용히 갈렸다. 규칙을
`components/profile_caption.py` 하나로 옮기면서, **옮기기 전 여덟 자리가 내던 글자**를
여기 그대로 적어 둔다 — 실패하면 화면에 보이는 문구가 바뀐 것이다.

`version == 0`(미저장)·`updated_at is None`(옛 저장분)·둘 다 있는 경우의 세 갈래를 모두
본다. 변형 둘도 함께 본다: 주요공정은 `{n}개 공정` 을 **출처 앞**에, Summary 공지는
`공지 중`/`내림` 을 **맨 뒤**에 끼운다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest

from capa_simulation.components.profile_caption import profile_version_caption

STAMP = datetime(2026, 1, 2, 3, 4)


@dataclass(frozen=True)
class _Profile:
    """세 필드만 갖는 최소 프로필. Protocol 이 구조로만 맞추는 것을 함께 확인한다."""

    version: int
    source: str
    updated_at: datetime | None


@pytest.mark.parametrize(
    ("profile", "kwargs", "expected"),
    [
        (
            _Profile(0, "붙여넣기", None),
            {"empty": "아직 넣은 선행 물량이 없습니다"},
            "공용 버전 없음 · 아직 넣은 선행 물량이 없습니다",
        ),
        (
            _Profile(1, "붙여넣기", None),
            {"empty": "아직 넣은 선행 물량이 없습니다"},
            "공용 버전 v1 · 붙여넣기",
        ),
        (
            _Profile(2, "붙여넣기", STAMP),
            {"empty": "아직 넣은 선행 물량이 없습니다"},
            "공용 버전 v2 · 붙여넣기 · 2026-01-02 03:04",
        ),
        (
            _Profile(0, "직접 입력", None),
            {"empty": "기본값 50%~200% 을 씁니다"},
            "공용 버전 없음 · 기본값 50%~200% 을 씁니다",
        ),
        (
            _Profile(0, "직접 입력", None),
            {"empty": "아직 고른 주요공정이 없습니다", "detail": "3개 공정"},
            "공용 버전 없음 · 아직 고른 주요공정이 없습니다",
        ),
        (
            _Profile(1, "직접 입력", None),
            {"empty": "아직 고른 주요공정이 없습니다", "detail": "3개 공정"},
            "공용 버전 v1 · 3개 공정 · 직접 입력",
        ),
        (
            _Profile(2, "직접 입력", STAMP),
            {"empty": "아직 고른 주요공정이 없습니다", "detail": "3개 공정"},
            "공용 버전 v2 · 3개 공정 · 직접 입력 · 2026-01-02 03:04",
        ),
        (
            _Profile(0, "직접 입력", None),
            {"empty": "아직 공지를 올린 적이 없습니다", "suffix": "공지 중"},
            "공용 버전 없음 · 아직 공지를 올린 적이 없습니다",
        ),
        (
            _Profile(1, "직접 입력", None),
            {"empty": "아직 공지를 올린 적이 없습니다", "suffix": "공지 중"},
            "공용 버전 v1 · 직접 입력 · 공지 중",
        ),
        (
            _Profile(2, "직접 입력", STAMP),
            {"empty": "아직 공지를 올린 적이 없습니다", "suffix": "내림"},
            "공용 버전 v2 · 직접 입력 · 2026-01-02 03:04 · 내림",
        ),
        (
            _Profile(3, "기준정보", STAMP),
            {"empty": "아직 저장한 표시순서가 없습니다"},
            "공용 버전 v3 · 기준정보 · 2026-01-02 03:04",
        ),
    ],
)
def test_profile_version_caption_matches_the_screen_text(
    profile: _Profile,
    kwargs: dict[str, str],
    expected: str,
) -> None:
    assert profile_version_caption(profile, **kwargs) == expected


def test_empty_branch_ignores_detail_and_suffix() -> None:
    """미저장일 때는 `공용 버전 없음 · <빈 문구>` 두 토막만 나온다.

    옛 여덟 자리가 모두 그랬다 — `{n}개 공정`·`공지 중` 은 저장된 뒤에만 뜻이 있다.
    """
    caption = profile_version_caption(
        _Profile(0, "직접 입력", STAMP),
        empty="아직 고른 주요공정이 없습니다",
        detail="0개 공정",
        suffix="내림",
    )

    assert caption == "공용 버전 없음 · 아직 고른 주요공정이 없습니다"


def test_caption_reads_updated_at_even_without_a_source_change() -> None:
    """저장시각은 출처 **뒤**, 꼬리말 **앞**이다. 순서가 바뀌면 화면이 달라진다."""
    caption = profile_version_caption(
        _Profile(7, "붙여넣기", STAMP),
        empty="비었습니다",
        detail="상세",
        suffix="꼬리",
    )

    assert caption == "공용 버전 v7 · 상세 · 붙여넣기 · 2026-01-02 03:04 · 꼬리"
