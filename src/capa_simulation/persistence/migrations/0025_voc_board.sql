-- Purpose: 사용자 질문과 답변을 남기는 VOC 자유 게시판의 글·답글 표를 만든다.

-- 소유 컬럼(`scenario_id`·`dataset_id`·`revision_id`)을 두지 않는다. 두면 `_owned_tables`
-- 자동 발견이 시나리오 소유로 판정해 시나리오 삭제가 게시글을 함께 지운다. VOC 는 어느
-- 시나리오에도 매이지 않는다 — 시나리오를 지워도 그때 나온 질문은 남아야 한다.
CREATE TABLE IF NOT EXISTS app_meta.voc_post (
    post_id VARCHAR PRIMARY KEY,
    category VARCHAR NOT NULL CHECK (category <> ''),
    title VARCHAR NOT NULL CHECK (title <> ''),
    body VARCHAR NOT NULL CHECK (body <> ''),
    author VARCHAR NOT NULL CHECK (author <> ''),
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS app_meta.voc_reply (
    reply_id VARCHAR PRIMARY KEY,
    post_id VARCHAR NOT NULL,
    body VARCHAR NOT NULL CHECK (body <> ''),
    author VARCHAR NOT NULL CHECK (author <> ''),
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);
