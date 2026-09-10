-- Purpose: 동·층별 배치 도면 이미지와 캔버스 치수를 리비전과 무관한 단일 저장값으로 보관한다.
CREATE TABLE IF NOT EXISTS equipment_ops.floor_layout_profile (
    building VARCHAR NOT NULL,
    floor_name VARCHAR NOT NULL,
    canvas_width DOUBLE NOT NULL CHECK (canvas_width > 0),
    canvas_height DOUBLE NOT NULL CHECK (canvas_height > 0),
    image_mime VARCHAR,
    image_name VARCHAR,
    image_payload BLOB,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (building, floor_name)
);
