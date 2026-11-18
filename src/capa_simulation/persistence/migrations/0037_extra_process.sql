-- Purpose: 부대공정(BDQ 밖) 생산성 기준정보의 판 내용 · 판 이력과 데이터셋마다 합친 판의 출처를 저장한다.

-- 판 내용 — 적용한 양식 ZIP 그대로(본문 sha256 이 키). 같은 내용을 다시 켜거나 다시 적용해도 한 벌만
-- 둔다. 자동 갱신 스레드 · 「다시 켜기」 · 「양식 내려받기」 · 「부대공정 얹기」 가 S3 를 읽지 않고 이
-- 표에서 판을 다시 읽는다.
CREATE TABLE IF NOT EXISTS app_meta.extra_process_content (
    sha256 VARCHAR PRIMARY KEY CHECK (length(sha256) = 64),
    pack_bytes BLOB NOT NULL,
    byte_size BIGINT NOT NULL CHECK (byte_size > 0),
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

-- 판 이력 — 넣기만 한다(append-only). 마지막 줄이 지금 상태다: `OFF` 면 활성 판이 없고, 그 밖이면 그
-- 줄의 판이 활성이다. `OFF` 줄은 판 번호 · sha 가 없다. 소유 칸(`scenario_id` · `dataset_id` ·
-- `revision_id`)을 두지 않는다 — 두면 시나리오 삭제가 판 이력을 함께 지운다. 「새 판으로」 의 바탕
-- 시나리오 · 리비전은 `base_*_ref` 로 가리키기만 한다.
CREATE TABLE IF NOT EXISTS app_meta.extra_process_version (
    seq INTEGER PRIMARY KEY CHECK (seq > 0),
    kind VARCHAR NOT NULL CHECK (kind IN ('APPLY', 'OFF', 'RESUME', 'REVISION')),
    version_no INTEGER CHECK (version_no IS NULL OR version_no > 0),
    sha256 VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    applied_by VARCHAR,
    process_count INTEGER CHECK (process_count IS NULL OR process_count >= 0),
    row_counts VARCHAR,
    source_place VARCHAR,
    s3_key VARCHAR,
    s3_etag VARCHAR,
    s3_last_modified TIMESTAMP,
    byte_size BIGINT CHECK (byte_size IS NULL OR byte_size > 0),
    base_scenario_ref VARCHAR,
    base_revision_ref VARCHAR,
    s3_write_result VARCHAR,
    CHECK ((kind = 'OFF') = (sha256 IS NULL)),
    CHECK ((kind = 'OFF') = (version_no IS NULL))
);

-- 데이터셋 출처 — 데이터셋 하나에 어느 판의 어느 공정을 합쳤나 · 뺐나. 같은 시나리오의 리비전은
-- 데이터셋이 하나라 저절로 따라간다. `dataset_id` 칸이 있어 시나리오를 지우면 함께 지워진다.
-- 월 머지는 두 원본의 판을 모두 적어 한 공정이 두 판을 가질 수 있다.
CREATE TABLE IF NOT EXISTS app_meta.dataset_extra_process (
    dataset_id VARCHAR NOT NULL,
    process_name VARCHAR NOT NULL,
    version_seq INTEGER NOT NULL,
    version_no INTEGER NOT NULL CHECK (version_no > 0),
    sha256 VARCHAR NOT NULL,
    outcome VARCHAR NOT NULL CHECK (outcome IN ('MERGED', 'DROPPED', 'GRADUATED')),
    rule VARCHAR,
    reason VARCHAR,
    row_counts VARCHAR,
    note VARCHAR,
    PRIMARY KEY (dataset_id, process_name, version_seq)
);
