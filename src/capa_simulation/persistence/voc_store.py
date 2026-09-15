# Purpose: VOC 게시판 글·답글의 조회·삽입·삭제 SQL을 담당한다.

"""VOC 게시판의 조회·삽입·삭제 SQL."""

from __future__ import annotations

import duckdb
import pandas as pd

VOC_POST_COLUMNS = (
    "post_id",
    "category",
    "title",
    "body",
    "author",
    "resolved",
    "created_at",
)
VOC_REPLY_COLUMNS = ("reply_id", "post_id", "body", "author", "created_at")


def load_voc_posts(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """최신 글이 위다. 게시판은 마지막에 올라온 것을 먼저 보는 화면이다."""
    projection = ", ".join(VOC_POST_COLUMNS)
    return connection.execute(
        f"SELECT {projection} FROM app_meta.voc_post ORDER BY created_at DESC, post_id DESC"
    ).fetchdf()


def load_voc_replies(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """답글은 **오래된 것이 위**다. 주고받은 차례가 그대로 읽혀야 한다."""
    projection = ", ".join(VOC_REPLY_COLUMNS)
    return connection.execute(
        f"SELECT {projection} FROM app_meta.voc_reply ORDER BY created_at ASC, reply_id ASC"
    ).fetchdf()


def insert_voc_post(
    connection: duckdb.DuckDBPyConnection,
    *,
    post_id: str,
    category: str,
    title: str,
    body: str,
    author: str,
) -> None:
    connection.execute(
        """
        INSERT INTO app_meta.voc_post (post_id, category, title, body, author)
        VALUES (?, ?, ?, ?, ?)
        """,
        [post_id, category, title, body, author],
    )


def insert_voc_reply(
    connection: duckdb.DuckDBPyConnection,
    *,
    reply_id: str,
    post_id: str,
    body: str,
    author: str,
) -> None:
    connection.execute(
        """
        INSERT INTO app_meta.voc_reply (reply_id, post_id, body, author)
        VALUES (?, ?, ?, ?)
        """,
        [reply_id, post_id, body, author],
    )


def update_voc_post_resolved(
    connection: duckdb.DuckDBPyConnection,
    *,
    post_id: str,
    resolved: bool,
) -> None:
    connection.execute(
        "UPDATE app_meta.voc_post SET resolved = ? WHERE post_id = ?",
        [resolved, post_id],
    )


def delete_voc_post(connection: duckdb.DuckDBPyConnection, *, post_id: str) -> None:
    """글을 지우면 답글도 함께 지운다. 주인 없는 답글이 남으면 영영 보이지 않는다."""
    connection.execute("DELETE FROM app_meta.voc_reply WHERE post_id = ?", [post_id])
    connection.execute("DELETE FROM app_meta.voc_post WHERE post_id = ?", [post_id])
