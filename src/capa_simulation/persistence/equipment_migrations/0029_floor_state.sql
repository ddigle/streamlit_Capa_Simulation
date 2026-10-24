-- Purpose: Space 동·층의 비활성(사용 안 함·생산라인 아님)을 설비 시나리오·리비전과 무관한 공용 현행값으로 저장하는 머리 표와 층 표를 만든다.

-- 모두에게 같은 공용 설정이다(FAB 전체 도면 0013 과 같은 성격). 설비 마스터의 동·층 값과 저장 검사는 건드리지 않는다 — 이 표는
-- Space 목록·도면·층 고르기에서 그 층을 숨길지만 정한다. 머리 한 행(`profile_id = 1`)의 `version` 이 저장마다 1 씩 오르고 화면이
-- 편집을 시작할 때 본 값과 대조한다. 한 번도 저장하지 않았으면 행이 없고 version 은 0 으로 본다(0019 와 같은 꼴).
CREATE TABLE IF NOT EXISTS equipment_ops.floor_state_profile (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    version INTEGER NOT NULL CHECK (version > 0),
    source VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

-- 비활성 층만 한 행이다 — 행이 없는 층은 사용이다(기본값: 모두 사용). 사유는 코드 글(`UNUSED` 사용 안 함 · `NOT_LINE` 생산라인
-- 아님)이고 허용값·동·층 범위는 서비스(`services/floor_state.prepare_floor_states`)가 본다 — DuckDB 는 CHECK 를 고칠 수 없어 목록을
-- DDL 에 박지 않는다. 저장은 바뀐 층만 고친다 — 다시 켠 층은 DELETE, 사유를 바꾼 층은 키 아닌 칸 UPDATE, 새로 끈 층은 INSERT 라
-- 한 트랜잭션에서 같은 키를 지웠다 다시 넣는 일이 없어 PK 를 둔다(키 아닌 칸 UPDATE 는 0019 머리 표와 같은 꼴). 외래 키는 없다.
CREATE TABLE IF NOT EXISTS equipment_ops.floor_state (
    building VARCHAR NOT NULL,
    floor_name VARCHAR NOT NULL,
    reason VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (building, floor_name)
);
