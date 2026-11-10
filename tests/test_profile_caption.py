# Purpose: 공용 프로필 버전 캡션의 글자(여덟 저장 화면)와 제목 옆 한 줄 배치를 고정한다.

"""**캡션 한 줄이 여덟 곳에 따로 적혀 있었다.**

`공용 버전 v3 · 붙여넣기 · 2026-01-02 03:04` 은 저장 화면마다 같은 모양이어야 한다. 그런데
템플릿이 자리마다 복사되어 있어 한 곳만 고치면 화면끼리 조용히 갈렸다. 규칙을
`components/profile_caption.py` 하나로 옮기면서, **옮기기 전 여덟 자리가 내던 글자**를
여기 그대로 적어 둔다 — 실패하면 화면에 보이는 문구가 바뀐 것이다.

`version == 0`(미저장)·`updated_at is None`(옛 저장분)·둘 다 있는 경우의 세 갈래를 모두
본다. 변형도 함께 본다: 주요공정은 `{n}개 공정` 을 **출처 앞**에 끼운다. 공지는 꼬리 없이 다른 줄과
같다 — 「공지 중 · 내림」 꼬리는 바로 아래 글 칸과 같은 말이라 걷었다(2026-11-09 사용자 검수 g18).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

import pytest
from streamlit.proto.Block_pb2 import Block as BlockProto
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block, Caption, Markdown

from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.profile_caption import (
    HEADING_BASELINE_STYLE,
    HEADING_KEY_PREFIX,
    profile_version_caption,
)

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
            {"empty": "아직 공지를 올린 적이 없습니다"},
            "공용 버전 없음 · 아직 공지를 올린 적이 없습니다",
        ),
        (
            _Profile(2, "직접 입력", STAMP),
            {"empty": "아직 공지를 올린 적이 없습니다"},
            "공용 버전 v2 · 직접 입력 · 2026-01-02 03:04",
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


def test_empty_branch_ignores_detail() -> None:
    """미저장일 때는 `공용 버전 없음 · <빈 문구>` 두 토막만 나온다.

    옛 여덟 자리가 모두 그랬다 — `{n}개 공정` 은 저장된 뒤에만 뜻이 있다.
    """
    caption = profile_version_caption(
        _Profile(0, "직접 입력", STAMP),
        empty="아직 고른 주요공정이 없습니다",
        detail="0개 공정",
    )

    assert caption == "공용 버전 없음 · 아직 고른 주요공정이 없습니다"


def test_caption_reads_updated_at_even_without_a_source_change() -> None:
    """저장시각은 출처 **뒤** 맨 끝이다. 순서가 바뀌면 화면이 달라진다."""
    caption = profile_version_caption(
        _Profile(7, "붙여넣기", STAMP),
        empty="비었습니다",
        detail="상세",
    )

    assert caption == "공용 버전 v7 · 상세 · 붙여넣기 · 2026-01-02 03:04"


@pytest.mark.parametrize(
    ("source", "kwargs", "expected"),
    [
        ("", {}, "공용 버전 v14 · 2026-01-02 03:04"),
        ("   ", {}, "공용 버전 v14 · 2026-01-02 03:04"),
        (
            "",
            {"detail": "3개 공정"},
            "공용 버전 v14 · 3개 공정 · 2026-01-02 03:04",
        ),
    ],
)
def test_an_empty_source_is_skipped_instead_of_leaving_a_blank_between_separators(
    source: str, kwargs: dict[str, str], expected: str
) -> None:
    """출처가 비면(저장자·변경 메모를 모두 비운 저장) 그 자리를 건너뛴다.

    가용설비 현황 Preference 는 저장자·메모가 선택이라 둘 다 비운 저장의 출처가 빈 글자다 —
    날로 이으면 `공용 버전 v14 · · 2026-10-27 12:20` 처럼 구분자가 겹쳤다(2026-10-27 E2E).
    변경 메모가 출처인 다른 공용 프로필(확보율 보정 등)도 같은 길이다.
    """
    caption = profile_version_caption(_Profile(14, source, STAMP), empty="비었습니다", **kwargs)

    assert caption == expected


@pytest.mark.parametrize(
    "memo",
    [
        "26.07~12 확정 / 27.01~06 잠정 *검토* $1$",
        "A~B~C *강조* `코드`",
        "![x](http://example.invalid/a.png) # 제목 _밑줄_",
    ],
)
def test_a_memo_source_is_shown_letter_for_letter_in_markdown(memo: str) -> None:
    """출처는 사람이 적은 「변경 메모」 다 — 캡션은 `st.caption`(마크다운 자리)으로 그린다.

    날로 이으면 물결표 짝은 지움선, `*…*` 은 기울임, `$…$` 은 수식, 백틱은 코드로 그려져 적은 글자가
    사라졌다(2026-10-27 E2E — 판정 기준·선행 B/O·확보율 보정 버전 캡션). 막힌 글자 앞의 `\\` 를
    걷어 내면 적은 메모가 그대로 나와야 하고, 막히지 않은 마크다운 구두점이 남지 않아야 한다.
    """
    caption = profile_version_caption(
        _Profile(4, memo, STAMP), empty="비었습니다", detail="기본 확보 100%"
    )

    head = "공용 버전 v4 · 기본 확보 100% · "
    tail = " · 2026-01-02 03:04"
    assert caption.startswith(head) and caption.endswith(tail)
    shown = caption[len(head) : -len(tail)]
    assert shown == literal_markdown(memo)
    assert re.sub(r"\\(.)", r"\1", shown) == memo
    assert not re.search(r"(?<!\\)[~*$`!\[\]()#_]", shown), shown


HEADING_SCRIPT = r"""
from dataclasses import dataclass
from datetime import datetime

import streamlit as st

from capa_simulation.components.profile_caption import render_profile_heading


@dataclass(frozen=True)
class Profile:
    version: int
    source: str
    updated_at: datetime | None


st.caption("앞 본문")
render_profile_heading(
    "#### :material/rule: 확보율 판정 기준",
    Profile(3, "26.07~12 확정 *검토*", datetime(2026, 1, 2, 3, 4)),
    key="demo_threshold",
    empty="아직 저장하지 않았습니다",
    detail="기본 확보 100% · 경고 <90%",
    help="판정 기준 풍선",
)
render_profile_heading(
    "#### 선행 B/O",
    Profile(0, "", None),
    key="demo_advance",
    empty="아직 넣은 선행 B/O 가 없습니다",
)
"""


def _rows(app: AppTest) -> list[Block]:
    return [
        block
        for block in app.main.children.values()
        if isinstance(block, Block)
        and block.proto.flex_container.direction == BlockProto.FlexContainer.Direction.HORIZONTAL
    ]


def test_the_heading_puts_the_version_line_beside_the_title() -> None:
    """제목과 공용 버전 줄은 한 가로 칸의 두 칸이다(2026-11-08 사용자 그림 메모 g18) — 제목 풍선은
    제목에, 버전 줄은 `profile_version_caption` 글(출처는 막힌 글)이다. 칸이 좁으면 줄을 바꾼다."""
    app = AppTest.from_string(HEADING_SCRIPT, default_timeout=30).run()

    assert not app.exception
    first, second = _rows(app)
    assert first.proto.flex_container.wrap
    assert f"{HEADING_KEY_PREFIX}demo_threshold" in first.proto.id
    assert f"{HEADING_KEY_PREFIX}demo_advance" in second.proto.id
    title, caption = (first.children[index] for index in sorted(first.children))
    assert isinstance(title, Markdown) and not isinstance(title, Caption)
    assert title.value == "#### :material/rule: 확보율 판정 기준"
    assert title.proto.help == "판정 기준 풍선"
    assert isinstance(caption, Caption)
    assert caption.value == (
        "공용 버전 v3 · 기본 확보 100% · 경고 &lt;90% · "
        + literal_markdown("26.07~12 확정 *검토*")
        + " · 2026-01-02 03:04"
        + HEADING_BASELINE_STYLE
    )
    second_caption = second.children[max(second.children)]
    assert isinstance(second_caption, Caption)
    assert second_caption.value == (
        "공용 버전 없음 · 아직 넣은 선행 B/O 가 없습니다" + HEADING_BASELINE_STYLE
    )


def test_the_version_line_carries_its_baseline_rule_without_raw_html() -> None:
    """두 글을 글자 밑줄에 맞추는 규칙은 버전 줄과 한 마크다운에 실린다(이벤트 칸을 쓰지 않는다). 그
    캡션은 HTML 을 받으므로 사람 글의 `<` 는 `literal_markdown` 이, 앱 글의 맨 `<` 는 글자 참조가
    막아 태그로 읽히지 않는다."""
    app = AppTest.from_string(HEADING_SCRIPT, default_timeout=30).run()

    first, _ = _rows(app)
    caption = first.children[max(first.children)]
    assert isinstance(caption, Caption)
    assert caption.proto.allow_html
    assert HEADING_BASELINE_STYLE == (
        f'<style>[class*="st-key-{HEADING_KEY_PREFIX}"]{{align-items:baseline}}</style>'
    )
    body = caption.value.removesuffix(HEADING_BASELINE_STYLE)
    assert re.findall(r"(?<!\\)<", body) == []


STYLE_SCRIPT = r"""
import streamlit as st

from capa_simulation.components.profile_caption import render_profile_heading


class Profile:
    version = 0
    source = ""
    updated_at = None


render_profile_heading(
    "#### 확보율 보정",
    Profile(),
    key="demo_execution",
    empty="아직 넣은 확보율 보정이 없습니다",
    style=".st-key-demo_save_row { padding-right: 120px; }",
)
"""


def test_the_version_line_carries_the_section_style_too() -> None:
    """`style=` 은 그 구획의 다른 칸에 거는 서식이다 — 팝업 본문(HOME 설정)은 스타일만 든 `st.html`
    을 쓸 수 없어(이벤트 칸) 버전 줄 캡션 끝에 `<style>` 로 함께 싣는다. 본문 칸이 하나 더 서지
    않는다."""
    app = AppTest.from_string(STYLE_SCRIPT, default_timeout=30).run()

    assert not app.exception
    (row,) = _rows(app)
    assert len(row.children) == 2
    caption = row.children[max(row.children)]
    assert isinstance(caption, Caption)
    assert caption.value == (
        "공용 버전 없음 · 아직 넣은 확보율 보정이 없습니다"
        + HEADING_BASELINE_STYLE
        + "<style>.st-key-demo_save_row { padding-right: 120px; }</style>"
    )
    assert len(app.main.children) == 1
