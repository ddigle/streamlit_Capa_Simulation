-- Purpose: 공정별 Cut-off(그 공정 이후 입고까지의 표준 납기) 일수를 현행값으로 저장한다.

-- Cut-off 는 어떤 달의 생산에 기여하려면 설비가 얼마나 먼저 있어야 하는지를 정한다.
-- 업무 정의는 「해당 공정 이후의 공정~입고(마지막 공정)까지 TAT 누적 합」이지만, 저장소에
-- TAT 도 공정 간 선후관계도 없다. 그래서 지금은 파생값이 아니라 **사람이 적는 원장**이다.
-- 나중에 TAT 가 들어오면 그때 입력값과 계산값을 어떻게 맞출지 정한다.
--
-- 리비전을 만들지 않는다. 호기 마스터·비가동과 달리 이것은 과거 어느 시점의 스냅샷이
-- 아니라 「지금 쓰는 기준」이고, 같은 성격인 0005 가 이미 비리비전 현행값 표다.
--
-- `product_scope` 는 **나중에 제품 축이 붙을 자리**다. 지금은 모든 행이 `'*'`(공정 전체)
-- 이고 화면도 그것만 만든다. 표준 대비 재공 현황에 차수별 표준 Capa 를 넣을 때 같은
-- 공정 안에서 제품별로 Cut-off 가 갈리는데, 그때 이 컬럼에 제품 값이 들어간다. 키를
-- 미리 열어 두지 않으면 그 시점에 표를 다시 만들어야 한다.
--
-- `cutoff_days` 가 DOUBLE 인 것은 입력을 소수점으로 받기 때문이다. 다만 날짜 단위까지만
-- 다루는 지금은 `services/wd_window.py` 가 내림해서 쓴다 — 반올림하면 같은 Cut-off 가
-- 달마다 다른 구간 길이를 내어 연간 365일 불변조건이 깨진다.

CREATE TABLE IF NOT EXISTS equipment_ops.process_cutoff (
    process_name VARCHAR NOT NULL,
    product_scope VARCHAR NOT NULL DEFAULT '*',
    cutoff_days DOUBLE NOT NULL,
    note VARCHAR,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (process_name, product_scope)
);
