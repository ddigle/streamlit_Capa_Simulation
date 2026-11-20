-- Purpose: 필요 단축 일정 누적 진척의 손 기록(ISO 주차마다 단축 필요일수 한 줄)과 최종 목표(일수 · 주차) 공용 현행값 표를 만든다.

-- 기록 한 줄 = ISO 주차 하나(해 · 주를 함께 — 해 넘김 W52 → W01 차례가 (해, 주)로 맞는다)의 단축 필요일수다. 사람이 적은
-- 수이고 화면 계산과 잇지 않는다(그 주에 무엇을 보고 적었는지는 남기지 않는다 — 한 줄 기록). 리비전 · 설비 시나리오와 무관한
-- 공용 현행값이라 소유 칸이 없다(0019 · 0032 와 같은 성격). 저장은 그 주 한 줄만 넣거나 고치거나 지운다 — 같은 키를 한
-- 트랜잭션에서 지웠다 다시 넣지 않아 PK 를 둔다(0029 · 0032 와 같은 꼴). 저장자는 마지막으로 그 줄을 쓴 사람이 적은 이름(선택)이다.
-- 주가 그 해에 있는지(53주차가 없는 해)는 서비스(`services/shortening_progress_log.py`)가 본다.
CREATE TABLE IF NOT EXISTS equipment_ops.shortening_progress_log (
    iso_year INTEGER NOT NULL CHECK (iso_year BETWEEN 2000 AND 2999),
    iso_week INTEGER NOT NULL CHECK (iso_week BETWEEN 1 AND 53),
    shortening_days INTEGER NOT NULL CHECK (shortening_days >= 0),
    recorded_by VARCHAR,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (iso_year, iso_week)
);

-- 최종 목표 — 머리 한 행(`profile_id = 1`). 목표 일수와 목표 주차는 함께 있거나 함께 없다. 한 번도 저장하지 않았으면 행이 없고
-- version 은 0 으로 본다(목표선 없음 — 0019 · 0032 와 같은 꼴). 지우기는 행을 남기고 세 칸을 비운 채 version 을 올린다 — 화면이
-- 편집을 시작할 때 본 version 과 대조한다.
CREATE TABLE IF NOT EXISTS equipment_ops.shortening_progress_goal (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    goal_days INTEGER CHECK (goal_days IS NULL OR goal_days >= 0),
    goal_year INTEGER CHECK (goal_year IS NULL OR goal_year BETWEEN 2000 AND 2999),
    goal_week INTEGER CHECK (goal_week IS NULL OR goal_week BETWEEN 1 AND 53),
    version INTEGER NOT NULL CHECK (version > 0),
    saved_by VARCHAR,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    CHECK ((goal_days IS NULL) = (goal_year IS NULL) AND (goal_year IS NULL) = (goal_week IS NULL))
);
