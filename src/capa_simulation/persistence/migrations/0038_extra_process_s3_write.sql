-- Purpose: 부대공정 판을 S3 Drive 파일로 다시 쓴 결과(씀 · 덮지 않음 · 실패)를 넣기만 하는 기록으로 남긴다.

-- 판 이력(0037 `extra_process_version`)은 넣기만 하고, 「이 리비전 값을 새 판으로」 는 DB 에 새 판을
-- 먼저 넣은 뒤 S3 Drive 의 `extra_process/current.zip` 을 덮는다. 쓰기 결과는 그 뒤에야 알고
-- 「S3 에 다시 쓰기」 가 나중에 바꾸므로 판 이력 줄을 고치지 않고 이 표에 한 줄씩 넣는다. 마지막
-- 「씀」 줄의 ETag 가 다음 쓰기의 기준 ETag 가 된다(사람이 놓은 파일을 앱이 덮지 않게 견준다).
-- `version_seq` 는 판 이력의 차례를 가리키기만 한다(소유 칸이 아니다 — 시나리오를 지워도 남는다).
CREATE TABLE IF NOT EXISTS app_meta.extra_process_s3_write (
    seq INTEGER PRIMARY KEY CHECK (seq > 0),
    version_seq INTEGER NOT NULL CHECK (version_seq > 0),
    result VARCHAR NOT NULL CHECK (result IN ('WRITTEN', 'KEPT', 'FAILED')),
    etag VARCHAR,
    seen_etag VARCHAR,
    stage VARCHAR CHECK (stage IS NULL OR stage IN ('HEAD', 'PUT')),
    reason VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    written_by VARCHAR,
    CHECK ((result = 'WRITTEN') = (etag IS NOT NULL)),
    CHECK ((result = 'FAILED') = (stage IS NOT NULL))
);
