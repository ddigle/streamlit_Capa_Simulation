# AGENTS 12장 — 변경 작업 체크리스트

## 12. 변경 작업 체크리스트

### 화면을 만들거나 바꿀 때

1. **화면을 만들거나 바꾸면 `docs/design_rules.md` 의 걸린 규칙 id 를 적고 자체 검토한다** — 설계 때 규칙 id 와 판단 질문을 적고,
   구현 뒤 규칙마다 통과 · 위반 · 예외(까닭) 한 줄. 규칙 밖 새 꼴은 만들기 전에 선택지 + 권장으로 묻는다(그 문서 2장 · PRC-07).

### 입력 테이블 또는 컬럼 변경

1. `config/data_contract.json`과 사내 DB 컬럼 매핑 확인
2. 서비스 필수 컬럼과 키 갱신
3. 활성 시나리오 editable 여부 결정
4. 월 필터와 화면 편집 Long/Wide 변환 확인
5. 누락·중복·범위 테스트 추가
6. 바뀐 규칙은 그 규칙을 맡은 파일 한 곳(`docs/rules/` · `docs/reference/files/` · `docs/design_rules.md`)에서 그 자리에서 고쳐 쓰고(덧붙이지 않는다) 다른 곳은 링크로 둔다. 모듈을 더하거나 옮기거나 지우면 `scripts/build_module_index.py` 로 색인을 다시 쓴다
7. **새 업무 키는 한 변경에** — 계약 · 변환 · 마이그레이션(값 불변 · 옛 리비전 계산 전후 같음 시험) · 계산 상수 · 리터럴
   조인 · 편집 차원 · 표시 차례 · 월 머지 · 부대공정 · 가상 제품 · 비교 GAP · `revision_compatibility` 안전망 · 확인 스크립트
   SQL 과 마이그레이션 전 사본 갈래(10-1 「0039 전 DB 사본」) · 기존 결과 대조 원천 맞춤. 반만 넣으면 두 값이 말없이
   접히거나 부하가 두 배가 된다(`CUSTOM` 선례 — 4장). 리터럴 표 시험은 손으로 칸을 더하지 않고 계약에서 칸을 붙이는
   도우미(`tests/custom_key_tables.py` 의 `with_blank_custom` · 두 부품 견본 `two_part_tables`)를 쓴다. 끝단 시험은 다른
   키로도 갈리는 꼴만 두지 않는다 — 다른 키(Capa Code 등)를 실은 키 목록의 새 키는 다른 키가 같은 꼴
   (`two_part_tables(split_capa_code=False)`)에서만 값으로 붙들린다. 새 키를 빼는 변이를 걸어 시험이 빨개지는지 본다.

### 계산식 변경

1. 계산 단위와 조인 키를 먼저 확정
2. `services/`의 순수 계산 함수 수정
3. `simulation_cache.py` 입력 계약 확인
4. 제외/오류 정책 확인
5. 정상·경계·누락 테스트 추가
6. 부하량부터 HOME까지 연쇄 결과 검증

### Streamlit 입력 변경

1. 편집 결과를 원본 Long Data로 복원
2. `apply_month_updates()`로 활성 시나리오 갱신
3. `revision` 증가와 `content_token` 재발급 확인
4. 다른 페이지에서 수정값 반영 확인
5. 페이지 왕복 후 입력값 유지 확인
6. **시나리오를 불러온 뒤에도 보던 탭과 조회 조건이 그대로인지 확인** — 사이드바의
   `st.rerun()` 이 페이지 본문을 건너뛰므로 `persist_state` 가 없는 위젯은 값을 잃는다
7. **새 보기 위젯은 다른 화면에 갔다가 화면 탭으로 돌아와도 남는가**(`persist_state="session"`) — 확인 체크·초안은
   남기지 않는다
8. **다른 화면으로 옮기는 새 단추·도우미는 전달 칸을 적기 전에 `refused_at_tab_limit` 을 부르는가**(9장 「팝업과
   콜백」) — 화면 링크는 `st.page_link` 로 두면 탭 줄 JS 가 막는다
9. 서버 재시작 후 유지 여부를 사용자 기대와 구분해 설명
10. **새 알림은 등록부 코드로 낸다**(9장 「알림 칸」) — 동작 결과는 `queue_flash`(성공은 알림창으로만, 그 자리에 고칠 입력이
    없는 경고는 `popup_only=True`), 조건 경고는
    `alerts.state`(자리에 그리지 않음 — 짧은 글은 무엇을 · 어디서 고치는지, 탭 안이면 `open_tab_name` 으로 열린 탭에서만 ·
    탭 이름과 함께), 데이터 때문에 화면을 그리지 못한 오류는 `data_error_mark.render_data_error`(자리에는 마크만), 자리 글이면
    `tests/test_alert_sites.py` 허용 목록에 `REASONS` 까닭과 함께
11. **화면 설정을 여는 새 단추는 본문이 아니라 사이드바 설정 상자인가**(`components/settings_box.py`, 9장 「사이드바·조건
    카드·본문」) — 상자를 더하면 화면 확인 `settings_boxes` 와 그 시험도 함께 고친다

### 코어 공개 창구(`module_api`) 변경

사외는 모듈을 볼 수 없다. 깨짐을 막는 것은 겉면 시험(`tests/test_module_api_surface.py`)·견본과 압축본의 판 분포 · 패키지
이름뿐이다 — 기대 글자를 고칠 때는 아래 1 · 2 가운데 어느 쪽인지 커밋에 적는다.

1. 같은 큰 판 안에서는 **더하기만** 한다(새 함수 · 새 선택 인자 · 새 `PALETTE_KEYS` 항목 · `module.json` 의 새 선택 칸). 더하면 작은 판
   (`API_MINOR`)을 올리고 `docs/module_guide.md` 부록 C 「창구 변경 기록」 에 한 줄을 적는다. 새 이름을 쓰는 모듈은 `api_minor` 를 그 판으로 적는다.
2. 지우기 · 이름 바꾸기 · 서명 바꾸기 · 뜻 바꾸기는 큰 판을 올린다(`module.json` 칸의 뜻 · 필수 바꿈도 같다). 이름 · 서명을 그대로
   두고 인자를 폐기 예정으로 받기만 하거나 화면에 그리는 것만 줄이는 변경은 작은 판이다 — 넘기던 모듈이 고치지 않아도 돈다(창구
   1.1 `page_header(description=)` — 작은 결정 d1, 2026-11-09 보드 Q 의 s-api-minor 「작은 판 그대로」 · 1.2 「구현중」 배지 줄 —
   2026-11-10 보드 Q-5). 옛 큰 판은
   `SUPPORTED_API_MAJORS` 에 남겨 옛 겉면을 그대로 지원하고, **압축본 `모듈` 줄의 판 분포(`api<n> <수>`)에서 그 판이 0 이 된 다음 배포에
   뺀다** — 사외가 모듈을 보는 유일한 근거다. 날짜로 빼면 옮기지 못한 모듈이 CD 에서 한꺼번에 실패한다.
3. **창구 밖에서 모듈을 깨는 변경도 같은 무게로 본다** — 코어 의존성에서 패키지 빼기, pandas · Streamlit 등 큰 판 올림(Streamlit 마이너
   올림 포함 — `streamlit>=1.63,<1.64` 로 묶여 있다), 폐기 예정 인자의 실제 제거. 모듈이 「사외 요청」 으로 받은 패키지는
   `config/module_packages.json` 에 이름을 적고, 코어가 더는 쓰지 않아도 그 목록에 있으면 빼지 않는다.
4. 견본 `tests/fixtures/modules/demo_ok` 가 새 겉면으로 도는지 본다(겉면의 모든 이름을 쓴다 — 창구가 깨지면 사외 관문에서 떨어진다).
5. 1 · 2 · 3 의 변경은 다음 배포 7장에 「모듈 담당자에게 알릴 것」 한 줄로 적는다.
6. 창구 · 점검 규칙(`scripts/module_check_rules.py` 의 `RULES`) · 뼈대(`scripts/new_module.py`) · 점검 출력(`scripts/check_module.py`)을
   바꾸면 같은 변경에서 `docs/module_guide.md` 를 고친다 — 부록 A · B(출력 예시 포함) · 3-7 뼈대 화면 · 3-8 · 3-9 · 3-10 예시(정적 규칙을
   통과해야 한다) · 9-2 환경변수는 `tests/test_module_guide_sync.py` 가 코드와 맞댄다. 부록 B 의 「자세히」 예시 줄은 안내서
   (`docs/module_colleague_guide.md` 8-2)와 그 HTML 판(`site/module-guide/index.html`)에도 옮겨 적혀 있어 같이 고친다(같은 시험 ·
   `tests/test_site_index.py`).

### 통합인증 변경

1. 시각 판정은 `auth/tokens.session_end` 한 곳이다 — 문지기 · `app.py` · 갱신 경로 · 카드 경고 · 쿠키 `Max-Age` 가 같은 끝을 쓰는지,
   새 판정이 갱신 표를 볼 자리(핸드셰이크에 묶인 신원)인지 새 요청(쿠키 자신의 끝만)인지 가른다(5장 36). 접속 명단 판정은 `identity.session_check` 한 곳에 더하고 자리마다 두지 않는다(5장 37).
2. 새 경로는 `auth/names.SSO_PATHS` 에 둔다 — 문지기 공개 정확 일치 · `tests/test_sso_entry.py` 경로 목록 · `docs/sso_setup.md` 1장 ·
   3장 `capa_server.py` · `auth/` 줄과 9장의 경로 수를 같이 고친다.
3. 새 환경변수는 `auth/names.SSO_ENVIRONMENT` · `scripts/check_deploy_screens.py` 의 글자 튜플 · `docs/sso_setup.md` 2장 표 · 런북 3-3 ·
   `docs/bigdataquery_webide_setup.md` 「통합인증(SSO) 칸」 에 함께 적는다(이름만 — 값은 어디에도 적지 않는다, 10장). 비밀값이면 `names.SECRET_ENVIRONMENT` 에도 둔다 — 시작 스크립트의 하위 프로세스 제외 · 출력 가림과 `os.environ` 제거가 그 튜플을 따른다.
4. 화면 글은 「사내」 · 토큰 · 클레임 값 없이(`tests/test_app_text_wording.py` · `tests/test_sso_status.py`), 문서 · 시험 예시는
   `*.example.invalid`(`tests/test_public_repo_hygiene.py`).
5. Streamlit 판을 올리면 툴바 iframe 이 앱과 같은 출처인지 브라우저로 한 번 본다 — 갱신 POST 가 `204` + `Set-Cookie` 를 받는지
   (`docs/sso_setup.md` 8장 「갱신을 눈으로 보려면」). 같은 출처가 아니게 되면 쓰는 중에도 처음 로그인 뒤 유지 시간에 끊긴다.
