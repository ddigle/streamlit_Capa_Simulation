-- Purpose: 공정 × 생산월 입력 비가동 대수(설비 일정 기준 가용에서 빼는 환산 대수)를 리비전과 무관한 공용 현행값으로 저장하는 머리·칸·저장 이력 표를 만든다.

-- 모든 설비 시나리오가 함께 쓰는 공용 현행값 하나다(Cut-off 0009·층 사용 상태 0029 와 같은 성격 — 소유 칸이 없어 설비 시나리오
-- 복제·보관·영구 삭제가 건드리지 않는다). 머리 한 행(`profile_id = 1`)의 `version` 이 저장마다 1 씩 오르고 화면이 편집을 시작할 때
-- 본 값과 대조한다. 한 번도 저장하지 않았으면 행이 없고 version 은 0 으로 본다(0019·0029 와 같은 꼴). 저장자·메모는 마지막 저장의
-- 것이다(이력은 아래 표).
CREATE TABLE IF NOT EXISTS equipment_ops.manual_downtime_profile (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    version INTEGER NOT NULL CHECK (version > 0),
    saved_by VARCHAR,
    note VARCHAR,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

-- 칸 하나 = (공정, 생산월)의 입력 비가동 대수(환산 대수, 소수). 공정은 원본 공정명(설비 마스터 `공정소분류` = 시나리오 `공정`)이고
-- 달은 `YYYYMM` 정수(생산월 — Cut-off W/D 월)다. 빈칸·0 은 행을 두지 않는다(서비스가 거른다). 저장은 바뀐 칸만 고친다 — 비운 칸은
-- DELETE, 값만 바꾼 칸은 키 아닌 칸 UPDATE, 새 칸은 INSERT 라 한 트랜잭션에서 같은 키를 지웠다 다시 넣는 일이 없어 PK 를 둔다(0029
-- 와 같은 꼴). 외래 키는 없다. 0 이상 말고 다른 범위는 서비스(`services/manual_downtime.py`)가 본다.
CREATE TABLE IF NOT EXISTS equipment_ops.manual_downtime (
    process_name VARCHAR NOT NULL CHECK (process_name <> ''),
    production_month INTEGER NOT NULL CHECK (production_month % 100 BETWEEN 1 AND 12),
    units DOUBLE NOT NULL CHECK (units >= 0),
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (process_name, production_month)
);

-- 저장 한 번 = 한 행(넣기만 한다). version 은 그 저장이 낸 머리 version 이다. 바뀐 칸 수·저장 뒤 채운 칸 수·대수 합만 남기고 칸 값의
-- 옛 모습은 남기지 않는다(되돌리기는 하지 않는다 — 화면 「저장 이력」 목록의 재료).
CREATE TABLE IF NOT EXISTS equipment_ops.manual_downtime_save (
    version INTEGER PRIMARY KEY CHECK (version > 0),
    saved_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    saved_by VARCHAR,
    note VARCHAR,
    changed_cells INTEGER NOT NULL CHECK (changed_cells >= 0),
    filled_cells INTEGER NOT NULL CHECK (filled_cells >= 0),
    total_units DOUBLE NOT NULL CHECK (total_units >= 0)
);
