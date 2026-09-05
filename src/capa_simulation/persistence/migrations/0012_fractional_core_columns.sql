-- Purpose: 비율·모듈수 계열 원천 컬럼을 DOUBLE 로 넓혀 소수값을 잘리지 않게 받는다.

ALTER TABLE raw_data.core_data ALTER COLUMN "모듈수" TYPE DOUBLE;
ALTER TABLE raw_data.core_data ALTER COLUMN "Side반영률" TYPE DOUBLE;
ALTER TABLE raw_data.core_data ALTER COLUMN "MCP_Chip_Ratio" TYPE DOUBLE;
ALTER TABLE raw_data.core_data ALTER COLUMN "설비보유HCB" TYPE DOUBLE;
