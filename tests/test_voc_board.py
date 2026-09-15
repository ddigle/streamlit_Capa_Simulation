# Purpose: VOC 게시판의 입력 검증과 글·답글 저장 왕복을 검증한다.

from __future__ import annotations

from pathlib import Path

import pytest

from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.voc_board import (
    VOC_CATEGORIES,
    normalize_post,
    normalize_reply,
)


def _repository(tmp_path: Path) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()
    return repository


def test_a_post_needs_a_known_category_and_a_non_empty_body() -> None:
    with pytest.raises(ValueError, match="분류"):
        normalize_post(category="잡담", title="제목", body="내용", author="홍길동")
    with pytest.raises(ValueError, match="제목"):
        normalize_post(category=VOC_CATEGORIES[0], title="  ", body="내용", author="홍길동")
    with pytest.raises(ValueError, match="내용"):
        normalize_post(category=VOC_CATEGORIES[0], title="제목", body=" ", author="홍길동")


def test_an_author_is_required_because_an_answer_needs_somewhere_to_go() -> None:
    with pytest.raises(ValueError, match="작성자"):
        normalize_post(category=VOC_CATEGORIES[0], title="제목", body="내용", author="   ")
    with pytest.raises(ValueError, match="작성자"):
        normalize_reply(body="답변", author="")


def test_a_post_and_its_replies_round_trip(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    assert repository.list_voc_posts().empty

    post_id = repository.create_voc_post(
        category="질문",
        title="확보율이 100%를 넘는데 부족으로 나옵니다",
        body="산출 결과 화면에서 확인했습니다.",
        author="홍길동",
    )
    repository.create_voc_reply(post_id=post_id, body="경고 기준을 확인해 주세요.", author="담당자")

    posts = repository.list_voc_posts()
    replies = repository.list_voc_replies()

    assert list(posts["post_id"]) == [post_id]
    assert bool(posts["resolved"].iloc[0]) is False
    assert list(replies["post_id"]) == [post_id]
    assert replies["author"].iloc[0] == "담당자"


def test_resolving_and_deleting_a_post(tmp_path: Path) -> None:
    """글을 지우면 답글도 함께 사라진다. 주인 없는 답글은 영영 보이지 않는다."""
    repository = _repository(tmp_path)
    post_id = repository.create_voc_post(
        category="오류 신고", title="제목", body="내용", author="홍길동"
    )
    repository.create_voc_reply(post_id=post_id, body="답변", author="담당자")

    repository.set_voc_post_resolved(post_id, resolved=True)
    assert bool(repository.list_voc_posts()["resolved"].iloc[0]) is True

    repository.remove_voc_post(post_id)
    assert repository.list_voc_posts().empty
    assert repository.list_voc_replies().empty


def test_migration_is_registered() -> None:
    """0025 가 카탈로그에 등재돼 있어야 한다. 기존 SQL 은 한 글자도 고치지 않는다."""
    root = Path(__file__).resolve().parents[1]
    catalog = (root / "docs/migration_catalog.md").read_text(encoding="utf-8")

    assert "0025_voc_board.sql" in catalog
