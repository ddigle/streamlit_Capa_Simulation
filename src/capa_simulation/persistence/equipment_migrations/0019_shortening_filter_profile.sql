-- Purpose: 필요단축일정 탭의 공용 조회 조건(시작 월·끝 월·공정 목록) 프로필을 리비전과 무관한 현행값으로 저장한다.

-- 한 행 헤더와 공정 자식 표다(시뮬레이션 DB 의 공용 주요공정 프로필과 같은 꼴). 모든 사용자가 같은
-- 행을 쓰고, 화면은 세션에 값이 없을 때만 이 값으로 심는다. 바꾸면 그 자리에서 갈아 쓰고 `version` 이
-- 오른다 — 설비 리비전은 만들지 않는다(같은 성격인 0009 Cut-off 처럼 「지금 쓰는 기준」이다).
--
-- 달은 `YYYYMM` 정수다. 둘 다 비면 아직 기간을 저장하지 않은 것이고 화면은 코드 기본값(조회기간 전체)을
-- 쓴다. 시작 월이 끝 월보다 늦어도 받는다 — 화면이 바꿔 읽는다. 공정은 원본 공정명(호기 마스터
-- `공정소분류` = 시나리오 `공정`)이고 표시명은 닿지 않는다. 공정 행이 없으면 「미선택 = 목표 미달 공정
-- 전체」다. `sort_order` 는 고른 차례다.
CREATE TABLE IF NOT EXISTS equipment_ops.shortening_filter_profile (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    start_month INTEGER CHECK (start_month IS NULL OR start_month % 100 BETWEEN 1 AND 12),
    end_month INTEGER CHECK (end_month IS NULL OR end_month % 100 BETWEEN 1 AND 12),
    version INTEGER NOT NULL CHECK (version > 0),
    source VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    CHECK ((start_month IS NULL) = (end_month IS NULL))
);

CREATE TABLE IF NOT EXISTS equipment_ops.shortening_filter_process (
    profile_id INTEGER NOT NULL CHECK (profile_id = 1),
    process_name VARCHAR NOT NULL CHECK (process_name <> ''),
    sort_order INTEGER NOT NULL CHECK (sort_order >= 0),
    PRIMARY KEY (profile_id, process_name)
);
