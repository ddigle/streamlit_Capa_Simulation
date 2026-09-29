-- Purpose: HOME 주요공정 히트맵의 공정 목록을 이름 붙은 프리셋 여럿으로 공용 프로필에 저장한다.

-- 헤더(`app_meta.global_key_process`, 0024)는 그대로 쓴다 — 저장마다 version 이 오르고 캐시가 그
-- 값을 본다. 소유 컬럼을 두지 않아 시나리오 삭제·보관이 건드리지 않는다.

-- `프리셋순서` 가 선택 목록의 차례이고 **0 번이 기본 프리셋**이다(새 세션이 처음 보는 것).
CREATE TABLE IF NOT EXISTS app_meta.global_key_process_preset (
    profile_id INTEGER NOT NULL CHECK (profile_id = 1),
    "프리셋" VARCHAR NOT NULL CHECK ("프리셋" <> ''),
    "프리셋순서" INTEGER NOT NULL CHECK ("프리셋순서" >= 0),
    PRIMARY KEY (profile_id, "프리셋")
);

-- `표시순서` 는 그 프리셋의 히트맵 행 순서다. 한 공정이 여러 프리셋에 들 수 있다.
CREATE TABLE IF NOT EXISTS app_meta.global_key_process_preset_item (
    profile_id INTEGER NOT NULL CHECK (profile_id = 1),
    "프리셋" VARCHAR NOT NULL CHECK ("프리셋" <> ''),
    "공정" VARCHAR NOT NULL CHECK ("공정" <> ''),
    "표시순서" INTEGER NOT NULL CHECK ("표시순서" >= 0),
    PRIMARY KEY (profile_id, "프리셋", "공정")
);

-- 0024 의 단일 목록은 「기본」 프리셋으로 옮긴다. 비어 있으면(전체 해제로 저장했거나 한 번도
-- 저장하지 않았으면) 프리셋을 만들지 않는다. 옛 표는 지우지 않는다 — 옛 배포로 되돌려도
-- HOME 이 열리게 둔다. 0028 뒤로는 아무도 읽지 않는다.
INSERT INTO app_meta.global_key_process_preset (profile_id, "프리셋", "프리셋순서")
SELECT 1, '기본', 0
WHERE EXISTS (SELECT 1 FROM app_meta.global_key_process_item WHERE profile_id = 1)
  AND NOT EXISTS (SELECT 1 FROM app_meta.global_key_process_preset WHERE profile_id = 1);

INSERT INTO app_meta.global_key_process_preset_item (profile_id, "프리셋", "공정", "표시순서")
SELECT item.profile_id, '기본', item."공정", item."표시순서"
FROM app_meta.global_key_process_item AS item
WHERE item.profile_id = 1
  AND NOT EXISTS (SELECT 1 FROM app_meta.global_key_process_preset_item WHERE profile_id = 1);
