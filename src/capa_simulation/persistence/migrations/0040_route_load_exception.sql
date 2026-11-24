-- Purpose: 공정별 부하 산출 예외 선언(공정 → 산식 id)의 판 이력을 넣기만 하는 공용 표로 둔다.

-- 판 이력은 넣기만 한다(append-only). 마지막 줄이 지금 선언이고, 모두 뺀 저장(비움)도 한 줄이다
-- (`{}` · 0 · 빈 지문). 소유 칸(`scenario_id` · `dataset_id` · `revision_id`)을 두지 않는다 — 선언은
-- 모든 시나리오에 걸리는 공용 값이라 시나리오를 지워도 남는다. 선언 항목은 원본 공정명 그대로의 JSON
-- 글이고, 산식 id 를 나열한 CHECK 는 두지 않는다 — 고칠 수 없는 표라 산식을 더할 때 막히지 않게
-- 검증은 저장소가 쓰기 앞에서 한다. 지문은 견줌 키로 줄인 선언의 지문이고 비움만 빈 글이다.
CREATE TABLE IF NOT EXISTS app_meta.route_load_exception_version (
    seq INTEGER PRIMARY KEY CHECK (seq > 0),
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    applied_by VARCHAR,
    source_place VARCHAR,
    entries_json VARCHAR NOT NULL,
    entry_count INTEGER NOT NULL CHECK (entry_count >= 0),
    digest VARCHAR NOT NULL,
    CHECK ((entry_count = 0) = (digest = ''))
);
