# Purpose: VOC 게시판 글·답글의 분류 목록과 입력값 검증을 담당한다.

"""VOC 자유 게시판.

**이 게시판은 계산에 닿지 않는다.** 시나리오·리비전 어디에도 매이지 않고, 질문과 답이
오가는 자리다. 그래서 시나리오를 지워도 그때 나온 질문은 남는다.

분류를 넷으로 고정한 것은 자유 입력이 곧 분류를 없애기 때문이다 — 같은 뜻을 세 사람이
세 가지로 적으면 필터가 무의미해진다. 넷이 모자라면 그때 늘린다.
"""

from __future__ import annotations

# 화면 필터와 저장값이 같은 목록을 본다. 순서는 게시판에서 실제로 많이 쓰일 차례다.
VOC_CATEGORIES: tuple[str, ...] = ("질문", "개선 요청", "오류 신고", "공지")

TITLE_MAX_LENGTH = 120
BODY_MAX_LENGTH = 4000
AUTHOR_MAX_LENGTH = 40


def normalize_author(value: str) -> str:
    """작성자 이름. 빈 이름은 막는다 — 누가 물었는지 모르면 답을 돌려줄 곳이 없다."""
    author = str(value).strip()
    if not author:
        raise ValueError("작성자를 입력하세요.")
    if len(author) > AUTHOR_MAX_LENGTH:
        raise ValueError(f"작성자는 {AUTHOR_MAX_LENGTH}자 이하로 입력하세요.")
    return author


def normalize_post(*, category: str, title: str, body: str, author: str) -> dict[str, str]:
    """글 하나의 저장 형태. 화면과 저장소가 같은 검증을 통과한다."""
    chosen = str(category).strip()
    if chosen not in VOC_CATEGORIES:
        raise ValueError(f"분류는 {', '.join(VOC_CATEGORIES)} 중 하나여야 합니다.")
    subject = str(title).strip()
    if not subject:
        raise ValueError("제목을 입력하세요.")
    if len(subject) > TITLE_MAX_LENGTH:
        raise ValueError(f"제목은 {TITLE_MAX_LENGTH}자 이하로 입력하세요.")
    content = str(body).strip()
    if not content:
        raise ValueError("내용을 입력하세요.")
    if len(content) > BODY_MAX_LENGTH:
        raise ValueError(f"내용은 {BODY_MAX_LENGTH}자 이하로 입력하세요.")
    return {
        "category": chosen,
        "title": subject,
        "body": content,
        "author": normalize_author(author),
    }


def normalize_reply(*, body: str, author: str) -> dict[str, str]:
    """답글 하나의 저장 형태. 답글에는 제목이 없다 — 글의 제목이 곧 주제다."""
    content = str(body).strip()
    if not content:
        raise ValueError("답변 내용을 입력하세요.")
    if len(content) > BODY_MAX_LENGTH:
        raise ValueError(f"답변은 {BODY_MAX_LENGTH}자 이하로 입력하세요.")
    return {"body": content, "author": normalize_author(author)}
