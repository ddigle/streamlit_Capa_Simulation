# AGENTS 3장 — 파일별 책임 > 실행과 UI

### 실행과 UI

- `app.py` — 앱 스크립트. 개발 · 사내 WebIDE · 시험 · 화면 확인은 이것을 바로 띄우고(`streamlit run app.py`), C-DEP 운영은 아래
  `capa_server.py` 가 이것을 감싼다. 공식 시나리오 부트스트랩·공통 사이드바·조회기간을 세우고 페이지를 돌린다.
  - 차례 「통합인증 확인(`sso_identity.require_signed_in` — 꺼짐이면 아무것도 그리지 않는다) → 입장 화면(`intro_overlay.py`) →
    껍데기 스타일 → 서체 → 툴바 → 부트스트랩(최신 공식 리비전 활성화) →
    자동 갱신 예약 → 요약(`intro_summary.py`) → 올라온 시나리오 최신 확인(`check_active_scenario_latest`) → 사이드바 → 조건
    팝업 칸 → 화면 탭 줄 → 페이지(모듈 화면이면 `module_runtime.run_module_page` 로 돈다)」는 `test_app_navigation.py`·
    `test_page_tabs.py` 가 지킨다. 페이지가 `st.stop()` 해도 닿아야 할 것은 모두 그 앞이다. 탭 아이콘
    `static/icons/capa_mark.svg` 는 `test_settings.py` 가 본다. 그 차례 맨 앞(실행 표지 · 세션 첫 표지 바로 뒤, 어떤 요소보다
    앞)에서 늦게 온 옛 화면 회차를 옮겨 간 화면으로 다시 보낸다(`stale_page_guard` — 9장 「화면 탭 줄」, 자리는
    `test_stale_page_guard.py` 가 본다).
  - 화면 탭 줄(`components/page_tabs.py`, 상태 `page_tabs_state.py`)의 훅은 세 자리다 — (a) `st.navigation()` 바로 뒤
    이동 대기·상한 처리(`route_page_tabs`), (b) 직전 화면 주소를 바꾼 바로 뒤 지금 화면을 목록에 더함
    (`note_current_page`), (c) 조건 팝업 칸 바로 뒤 탭 줄 그리기(`render_page_tabs`). 점 판정(`page_unsaved_marks`)은
    한 번 내어 테마 표지와 탭 줄이 함께 쓴다.
  - 사이드바는 `navigation.py` 선언을 그리기만 한다(CSS `sidebar_style.py`, 상자·카드 `sidebar_status.py`). 순번 고정 —
    그룹 상자 → `Support`·앱 카드(`app_credits.py`, `apply_deploy_package.py` 가 쓴 `.deploy/applied.json` — 통합인증이 켜진
    서버만 셋째 줄 「이름 · 부서 · 로그아웃」) → 조회 조건.
  - 조건 패널(`condition_field.py`)의 시나리오(`scenario_status.py`)·조회기간(`period_field.py`)·설비 시나리오
    (`equipment_scenario_status.py`)·공정(`components/process_field.py` — 공용 공정 칸, 2026-11-08 공정 공유 1차) 팝업은 키 붙은 호스트 프래그먼트가 매 전체 실행 빠짐없이 부른다. 공통 줄은 읽는 화면에만
    서고 기간 범위는 `scenario_month_bounds.py` 다. 설비 시나리오 칸은 빈 블록 칸만 세우고 줄은 페이지가 그린다 — `app.py`
    는 설비 DB 를 열지 않는다(9장).
  - 운영 서버의 개발자가 아닌 회차(`sso_identity.unfinished_hidden` — 「이 등급으로 보기」 동안 포함, 운영 + 통합인증 꺼짐은
    모두)는 구현 중 화면(`navigation.PageSpec.unfinished`)을 사이드바에서 빼고(`build_navigation_pages(hide_unfinished=True)` —
    등록은 `NavigationPages.unlisted` 로 그대로), 주소 · 탭 · 알림으로 그 화면에 든 회차(`locked`)는 화면 파일 대신
    `grade_ui.stop_unless("screen.unfinished", place="page")` 를 `run_core_page` 로 돌린다(Admin Area 와 같은 멈춤). 그 회차는 조회
    조건 구역 · 패널 · 설비 시나리오 칸을 세우지 않고 알림 칸에 화면 선언을 넘기지 않는다(「합성 샘플」 표지 · 공정 칩 짐작 없음).
    화면 탭은 선다. 개발 · WebIDE · 사내 PC · 시험(운영 아님)은 그대로다(2026-11-24 정식판 마감 2-A — 9장 「접속 등급」).
- `capa_server.py` — C-DEP 운영 진입점(`streamlit run capa_server.py` — 앱 스크립트는 `app.py` 하나 그대로). `app.py` 를
  `st.App` 으로 감싸 통합인증 경로 여섯과 문지기를 같은 프로세스에 붙인다. 모듈 수준 `app = st.App(...)` 리터럴 대입이어야 Streamlit 이 찾는다(함수가 만든 App 은
  조용히 빈 화면 — `test_sso_entry.py`). 개발 · WebIDE · 시험 · 화면 확인은 `streamlit run app.py` 그대로다. 통합인증 기동 바로 뒤
  BigDataQuery 자동 로그인 기동(`io/bdq_login.start_in_app` — 키를 쥐고 환경에서 빼고 저장 객체를 한 번 읽는다, 실패해도 앱은 뜬다)을 부른다.
  이 파일의 import · 기동은 Streamlit 런타임 **전**이라 `st.components.v2.component(...)` 를 부르는 모듈과 그것을 머리에서 읽는 모듈
  (`components/` 화면 조각 · `grade_ui` · `sso_identity`)을 부르지 않는다 — 부르면 등록이 사라져 모든 사람의 첫 화면이 「Component … is not
  registered」 로 멈춘다. 접속 등급 판정기도 여기서 꽂지 않고 `app.py` 가 매 회차 꽂는다. `tests/test_server_pre_runtime_imports.py` 가 이
  파일을 그대로 import 해 지킨다(import 줄을 시험에 옮겨 적지 않는다).
- `src/capa_simulation/audit/` — 접속 · 작업 감사 기록(Admin Area 「접속 · 작업 기록」). 두 DB 밖에 쌓는다 — 메모리 큐 →
  로컬 스풀 → 버킷 `audit/` 접두사의 새 객체(5장 40). 통합인증이 켜진 C-DEP 기동에서만 켜지고(`recorder.enabled()`) 꺼진 곳은
  호출 0 이다. 사건 이름 · 갈래 · 한글 표시명 · 허용 상세 키는 `audit/events.py`, 글 다듬기(줄바꿈 · 제어 문자 · 길이 · 토큰 꼴
  가림, 통합인증 로그 칸 `log_field` 도 여기 — `auth/runtime.py` 가 쓴다)는 `audit/text.py`, 해시 사슬(정규화 · 해시 · 검증)은
  `audit/chain.py`, 기록기(넣기만 · 상한 20,000줄 · 버린 수 · 행위자 해석기 · 시간 묶음 · 통합인증 사건 대응표
  `from_sso_event`)는 `audit/recorder.py` 다. 비우기(잠금 하나 안에서 사슬을 이어 `<스풀 뿌리>/spool/<UTC날짜>__<inst>.jsonl`
  에 덧붙이고 fsync · 올림 표지 `.shipped` · 일별 파일이 미러에 든 날짜만 지우기)는 `audit/spool.py`(뿌리 기본
  `data/temp/audit`, 시험은 conftest 가 세션 임시 폴더로 옮기고 저장소에 새로 생기면 실패), 버킷 키 · 미러 자리 · gzip 꼴은
  `audit/layout.py`, 화면이 읽는 길(스풀 · 미러만 — S3 를 부르지 않는다, KST +09:00 고정, 같은 (inst, seq) 하나만, 다시 읽지
  않을 지문)은 `audit/read.py` 다. 넷 다 표준 라이브러리만 쓴다(문지기가 `recorder` 를 부른다 —
  `tests/test_audit_recorder.py` 가 Streamlit · DuckDB · PyJWT 가 딸려 오지 않는지 본다). 버킷 쪽(스풀 → `seg` 새 객체 ·
  조건부 쓰기, 지원 확인 전이면 HEAD 뒤 쓰기 · 최근 14일 일별 묶음 `daily/…p<n>` 과 앞 manifest sha256 잇기 · 14일 넘게 늦은
  조각 `audit_late_segment` · 400일 미러 · 새 인스턴스의 `audit_chain_link` · 시계 차이 `sys_clock_skew` · `AD-12`/`AD-13`
  까닭)은 `audit/shipper.py` 다(동기화 일꾼이 부른다, 시험은 `tests/test_audit_shipper.py` — `aws` 없이 인자 배열을 가짜 S3
  에 서명한 요청으로 옮기는 `tests/s3_mock_runner.py` 위). 사내 PC 운영 도구(`sync_object_storage.py` 의 rollback · init ·
  fetch-copy · prune · keep · unkeep)는 기록기를 켜지 않고 명령마다 한 줄 조각을 `audit/v1/tool/…` 에 바로 올린다(`audit/tool.py` — 행위자는
  OS 사용자, `verified` 거짓, 건너뛴 명령 · 빈 설정 · 할 일이 없던 명령은 남기지 않음, 올리지 못해도 종료 코드 그대로). 개발자 행위(명단 추가 · 삭제
  — 대상 loginid 마다 한 줄, 답을 못 받으면 `unknown`(시도한 판), 쓰지 못한 실패 `fail` 은 판 전 = 후 — `access_store._audit_revisions`, 기록 보기 상세는
  「판 n(그대로)」 — `audit_log_view.detail_text` · 토큰 넣기 — 결과와 만료만 · 지금 올리기 · 자동 갱신 설정 — 바뀐 칸
  이름과 판만 · 자동 갱신 수동 실행)는 그 함수 · 콜백이 `recorder.record` 를 부른다. 데이터 작업은 두 저장소의 쓰기 함수에 단
  표지 `@audited`(`audit/work.py` — 돌아온 뒤(COMMIT 뒤) 한 줄, 예외면 `out=fail` 한 줄을 넣고 예외는 그대로, 꺼진 프로세스는
  원래 함수만, 표지 단 함수 안의 표지 단 함수는 바깥 한 줄만)이고, 대상 id · 이름표 · 상세(값 원문 · 메모 · VOC 본문 없음,
  손입력 이름은 `claimed`)는 `persistence/work_audit.py` 가 짓는다(시험 `tests/test_audit_work_events.py` 가 설계서 2-3 표의
  함수 → 사건을 맞댄다 — 설비 저장은 낸 공식 발행 번호 · 함께 넣은 시나리오 수, 보관은 같이 비운 HOME 지정 수도 싣는다). 켜는 곳은 `audit/boot.py` 하나다 —
  `capa_server.py` 가 `start_sso()` 바로 뒤에 부르고 통합인증 모드가 켜짐일 때만 켜며 `sys_startup` · `authz_admin_config`(「개발자 구성」 — 개발자
  수 · 목록 지문 8자) · `sys_boot_pull` 을 남기고 등급 판정기(`grade_store.grade_of` — 개발자 · 관리자 · 실무자 · 열람)를 꽂는다. 설정 읽기와 S3 명단의 기동 읽기는 `start_sso()`
  안이라 기록기보다 먼저 돈다 — 같은 자리에서 그 사건을 따라잡는다. 만료가 30일 안인 서명 인증서마다 `sys_cert_expiring` 한 줄
  (`_note_expiring_certs` — 서버 로그 `cert_expiring` 과 한 판정 `runtime.expiring_certs`, 기동 때만), 그 읽기가 실패한 서버면
  `sys_access_read_fail` 한 줄(`_note_list_read_at_start`).
  자가 회복 실패(`access_retry_failed`)는 대응표 밖이다(누계만).
  통합인증 사건은 `auth/runtime.record_event` 가 잠금 밖에서 대응표(`from_sso_event`)로 넘기고(로그인 성공의 이름은 감사
  줄에만 — `audit=` 칸, 서버 로그 · 고리에는 싣지 않는다), 갱신 누계는 시간 묶음으로 센다.
  - `components/audit_log_view.py` — Admin Area 「접속 · 작업 기록」 탭. 사이드바 「기록 조건」 카드(기간 — KST,
    `date_range_field` · 사람 · 사건 갈래 · 결과 · 필터 초기화, 키 `admin_area_log_*`, `persist_state="session"`)와 「요약 |
    기록」 종류 단추(탭 안 탭 아님) 두 보기. 로컬 스풀 · 미러만 읽고(`audit.read` — S3 안 부름) 읽은 줄은 세션 칸에 지문을
    키로 둔다(새 `st.cache_*` 없음). 요약은 오늘 값 칸 넷(기간에 오늘이 없거나 오늘 줄이 없으면 「—」)과 날짜별 표(조건에
    맞는 줄이 없는 날은 빈칸 — 기록기 멈춤을 뜻하지 않는다), 기록은 새것 먼저 한 줄씩(상세 키는 `events.DET_LABELS` 한글). 설명
    글은 Guide · 풍선이고 빈 결과는 평문 한 줄이다. 닫힌 탭이면 부르지 않는다(카드도 서지 않는다). 감사 알림 `AD-12`(보관
    안 됨) · `AD-13`(14일 넘게 늦은 조각)은 앱 정보 카드 뒤 `sso_status.render_audit_alerts` 가 켜진 서버의 매 회차 갈래
    없이 두 자리를 쓰고 개발자 회차에만 세운다(꺼진 서버는 호출 0). 감사가 켜진 서버의 「통합인증 점검」 은 사람
    단위 사건 표(최근 사건 · 명단 밖 로그인)를 그리지 않고 그 둘은 누계 줄과 리뷰용 「복사」 글로만 남긴다(설계 AU19 —
    로그인 전 실패 표 · 앱 시작 실패 줄은 그린다, 2026-11-14 보드 decided-login 5 · boot-record).
  - `components/audit_actor.py` — 감사 기록의 앱 쪽. 스크립트 스레드 행위자 해석기(`resolve` — 쿠키를 **지금** 다시 검증한
    `sso_identity.verified_identity`, 실행 문맥이 없으면 `None`), 세션 첫 회차의 `session_created`(`note_session` — `sid8` ·
    `tab8` = Streamlit 세션 id 의 SHA-256 앞 8자), 부트스트랩 뒤 비우기(`drain`). `app.py` 는 신원이 있는 회차(통합인증 켜짐)에만
    부른다 — 꺼짐은 호출 0(`tests/test_app_navigation.py`).
- `src/capa_simulation/auth/` — 통합인증(ADFS · form_post). Streamlit 을 import 하지 않는다(문지기는 이벤트 루프에서
  돈다). 환경변수 이름 · 경로 · 쿠키 이름은 `auth/names.py`(표준 라이브러리만), 모드(꺼짐 · 켜짐 · 막힘) 판정과 검증된 설정은
  `auth/config.py`, ID 토큰(RS256 — aud · iss · nonce 를 반드시 본다) · 세션 토큰(HS256 — `sid` · `auth_time` 을 싣고 갱신은 새
  `jti` 로 다시 서명, 끝 시각 규칙은 `session_end` 한 곳) · 상태 토큰(HS256)은 `auth/tokens.py`, 쿠키 → 신원은
  `auth/identity.py`(문지기와 앱 스크립트가 같은 함수), 접속 명단(목록 글 → loginid → 등급 맵 · `AccessList.allows` · loginid 꼴 `LOGINID_PATTERN` · S3 파일 몫을 얹는 `compose_access` — 표준 라이브러리만)은
  `auth/access.py`, S3 명단 파일(꼴 판정 · 기동 때 읽기 · 자가 회복 `retry_unread` · 개발자만 쓰는 `save_changes`(넣기 · 빼기 · 개발자 등급 — 저장 값 `user` · `admin` 그대로) · `reread` · 거절 표 신원으로 쓰는 `register_self` — 5장 37)은 `auth/access_store.py`, 접속 등급의 판정 한 곳(등급 넷 `VIEWER` · `EDITOR` · `MANAGER` · `DEVELOPER` · 화면 글 `GRADE_LABELS` · 동작 표 `ACTIONS` · 감사 사건 → 바닥 동작 `EVENT_FLOORS`(표에 없는 사건은 `admin.area` 로 닫힘) · 거절 예외 `GradeDenied` · `SignInEnded`(`Exception` 직속 — `BOOTSTRAP_ERRORS` 밖, `REFUSALS`) · `require` · `require_all` · `gated` · 판정기 꽂기 `install_caller_source` — 표준 라이브러리 + `audit.recorder` 만이라 persistence 도 부른다, 5장 41)은 `auth/grades.py`, 등급 파일(명단 곁 `grades.json` + 표지 `grades_seen.json` — 꼴 · 판정 `grade_of` · 기동 읽기 · 로그인 때 다시 읽기 `retry_unread` · 쓰는 차례 `change_grades` · `add_people` · `remove_people`, 5장 41)은 `auth/grade_store.py`, 프로세스 상태(설정 한 벌 · 지금 명단 한 벌 `current_access` · 문지기 표지 · 세션 폐기(`sid`) · 로그인 갱신 표 ·
  갱신 누계 · 로그인 시작 · 돌아옴 누계(`login_flow_counts` — 시작은 브라우저 문서 탐색만, 돌아옴은 검증한 상태 쿠키와 처음 온 콜백만 · 돌아옴이 적으면 ADFS 화면에서 멈춤) · 진단 · 사건 · 명단 밖 로그인 표 · 마지막 로그인의 클레임 이름 · 로거)는 `auth/runtime.py`, 경로 여섯(`/auth/callback` · `/auth/sso/login` · `/auth/sso/logout` ·
  `/auth/sso/error` · `POST /auth/sso/refresh` · `POST /auth/sso/register` — 거절 화면 「접속 권한 신청」) · 로그인 시작 · 거절 표(15분 HttpOnly — 본인 계정 표시 · 신청의 유일한 신원) · 로그인 실패 갈래(`failure_kind` — 잠시 · 설정 · 쿠키 없음, 설정 문제 · 쿠키 없음은 시도 쿠키를 지운다 · 상태 쿠키는 토큰(10분)보다 긴 1시간이라 10분 넘게 머문 콜백은 쿠키 없음이 아니라 시간 지남, 실패 사건에 진단 번호 앞 8자 `diag`) · 시도 쿠키(「시작 횟수.마지막 시작 시각」 — 되풀이 화면의 기다릴 시각이 밀리지 않음) · 처음 가려던 화면(`next` — 상태 토큰 · 로그아웃 링크 `?next=` · 오류 주소, 읽을 때마다 `sanitize_next`) · 화면은 `auth/web.py`, 앱 밖 화면의 공통 틀(거절 갈래 · 포털 거절 · 로그인 실패 셋 · 되풀이 · 로그아웃 · 설정 막힘 — 위는 누구나 읽는 글, 바닥 「참고 사유 코드 · 시각 UTC(· 진단 번호)」, 접힌 「개발자용 진단」(머리 줄 · 줄 · 표 · 다시 접힌 칸 하나 — 칸 안은 표 · 이름표 | 값 표 · 줄, 환경변수 이름 칸은 `_` 뒤 `<wbr>`), 사람이 읽는 「○시 ○분」 은 KST — 순수 HTML · 토큰 팔레트 · 스크립트 없음)은 `auth/page_frame.py`, 순수 ASGI 문지기는 `auth/gate.py`(`BaseHTTPMiddleware` 는
  websocket 을 넘겨 쓰지 않는다), 진입 파일 창구는 `auth/server.py`, 운영 서버의 공지 물음 경로(`GET /capa/notice` — 공개 목록 밖이라 켜짐이면
  문지기가 쿠키를 보고 신원이 없으면 탐색으로 보지 않고 늘 401(앞단이 Sec-Fetch-* 를 떼도 로그인 시작을 내지 않음), 꺼짐은 처리기가 그대로 냄 ·
  켜짐인데 문지기 없음 · 막힘은 503, 메모리 읽기만 · `no-store` JSON — `notice_board.payload` 그대로)는
  `auth/notice_poll.py` 다. PyJWT 는 함수 안에서 import 한다 — 꺼짐(`ADFS_CLIENT_ID`
  없음)은 그 패키지 없이도 뜬다. 신원은 세션 상태가 아니라 HttpOnly 쿠키에서 매번 다시 검증한다(`?token=` · 세션 상태 보관 안
  씀). Streamlit 자체 `/auth/login` · `/auth/logout` · `/oauth2callback` 이름은 피한다. 개발용 가짜 IdP 는
  `scripts/sso_mock_idp.py`, 시험은 `tests/test_sso_*.py`(ASGI 운전기 `tests/asgi_driver.py`, 실행 때 만든 키
  `tests/sso_support.py`) · 공개 저장소 감시 `tests/test_public_repo_hygiene.py` 다. 운영 · 개발 안내는 `docs/sso_setup.md`.
  - 로그인은 `response_type=id_token` · `response_mode=form_post` 로 ID 토큰만 받아 코드 교환이 없다(`auth/web.py`) — 포털이 준 Client Secret 은 쓰지 않고, 넣을 환경변수 자리도 없다.
  - 「접속 권한 신청」 단추 라벨은 상수 `auth/web.REGISTER_LABEL` 하나다 — 거절 화면(`auth/web.py`) · 앱 안 멈춤 판(`components/sso_identity.py`) · 띠(`components/sso_reconnect.py`)의 단추가 그 상수를 불러 쓴다. 시작 임시 화면의 잃은 신청 글(`scripts/container_stage.py` 의 `NOTE_REGISTER_LOST`)은 같은 이름을 글자로 적고 `tests/test_container_stage.py` 가 그 상수와 맞댄다.
  - `components/sso_identity.py` — 앱 스크립트 쪽 두 번째 벽. `app.py` 가 `theme.begin_run()` 바로 뒤 · 입장 화면 앞에서 부르는
    `require_signed_in()` 이 매 회차 `st.context.cookies` 의 세션 쿠키를 다시 검증한다(만료 · 다른 탭 로그아웃 · 계정 바뀜 · 문지기
    없이 뜬 서버는 멈춤 화면 + `st.stop()`). 문지기 없이 뜬 서버는 경고 「지금은 앱을 열 수 없습니다(서버 시작 설정)」 · 문의 캡션 · 참고 줄 ·
    접힌 「개발자용 진단」(`diagnostic_copy.ADMIN_DIAGNOSTIC_LABEL` — 실행 명령 · 설정 문제 이름 · 안내 문서, 복사 부품은 함수 안에서 import)이고
    단추가 없다. 접힌 진단은 개발자 몫(`admin_view.developer_notes_visible` — 앱 시작 실패 판과 한 판정, `admin_view` 는 순환이라 함수 안에서 import)에만
    서고 판정이 실패하면 없다 — 운영 서버의 일반 사용자 · 막힌 운영 서버에는 참고 줄 사유 낱말 `sso_no_gate` 만이다. 앱 정보 카드의 로그아웃 링크는 지금 화면을 `?next=` 로 싣는다(`logout_url` — `/` 면 없음). 로그인 끝남 · 계정 바뀜 멈춤은 앱 안 멈춤 판(`components/stop_panel.py`)이다 — 경고
    한 줄 · 같은 탭 주 단추 꼴 링크(`primary_link` — `st.link_button` 은 새 탭이고 `st.rerun` 은 앞 계정의 세션을 잇는다. 역할은
    링크 그대로 — `role="button"` 은 Space 로 열리지 않는다) · 「문의 <메일> · <창구 글>」 캡션(`CAPA_ACCESS_CONTACT` 는 로그인 ·
    접속 멈춤만 넘긴다 — 둘 다 비면 없음) · 「참고 <사유 낱말> · <UTC 분>」(만료 `sso_expired` · 로그아웃 `sso_revoked` · 쿠키 없음 · 위조 `sso_missing` · 명단 밖 `not_on_list` · 명단 못 읽음 `list_unread` — 뒤 둘은 거절 화면과 같은 낱말 · 계정 바뀜 `sso_account_changed`). 접힌 진단은 없다 — 로그인이 끝난 회차에는 검증된 신원이 없어 개발자 몫이 서지 않는다. 단추는 까닭(`gate.ended_reason` — 띠와 같은 낱말)으로 가른다: 명단에서 빠짐 「접속 권한 신청」, 명단 못 읽음
    `cloud_off` + 「다시 로그인」, 계정 바뀜은 새 계정 이름 + 「새로고침」(풍선 `REFRESH_TIP`). 위젯 콜백(본문보다 먼저 돈다)과 프래그먼트 회차(`app.py` 를 돌리지 않는다)는 이
    벽을 지나지 않는다 — 열린 탭의 만료 · 로그아웃은 문지기가 websocket 메시지마다 막는다(`gate._WatchedSocket`, 9장). 접속 등급의 신원 → 등급도 여기다 — 쓰는 순간의 벽이 보는 실제 등급 `real_caller`(쿠키만 — 운영 아님 · `as_system` = 제한 없음, 운영 + 통합인증 꺼짐 = 관리자, 실행 문맥 없는 낯선 스레드 = 열람, 운영 + 켜짐 = 신원 등급 · 신원 없음 = 로그인 끝남)와 그리기 판정 `screen_grade` · `viewer_can(action)`(실제 개발자이고 운영 + 켜짐일 때만 「이 등급으로 보기」 `GRADE_PREVIEW_KEY` 를 따른다), 두 번째 벽 `developer_wall_locked`, C-DEP 운영 자리 쓰기 잠금 `production_write_lock_reason`(Admin 「부대공정」 · 「부하 예외」 의 쓰는 단추가 함께 쓰는 한 판정 — C-DEP 꼴(`extra_process_intake.production_place`)이 아니면 `NOT_PRODUCTION_REASON`, 실제 개발자가 아니면 등급 거절 글), 카드 셋째 줄 등급 표지(열람 · 실무자만 — 미리 보기 중 「<등급> 화면으로 보는 중」 + 「끝내기」 `end_preview`) — 5장 41 · 9장 「접속 등급」. 개발자 회차 판정 `viewer_is_developer`(지금 다시 검증한 신원 — 켜짐이 아니면 거짓, 환경변수 개발자 ∪ 명단 개발자 등급, `AD-10`) · Admin Area 잠금 판정 `admin_area_locked`(운영 서버 `SsoConfig.operational` 이고 개발자가 아님 — `app.py` 가 Support 상자의 Admin Area 링크를 빼고 `app_pages/admin_area.py` 가 「개발자만 여는 화면입니다」 + 「HOME 으로」 뒤 멈춘다, 개발 · WebIDE · 사내 PC 는 연다)과 앱 정보 카드 셋째 줄(`sso_credit_line`)도 여기서 짓는다 — 「다시 로그인」 · 「로그아웃」
    은 같은 탭에서 여는 원문 HTML 링크(`target="_self"`, 이름 · 부서는 `literal_markdown`)다. 끝 30분 전 경고는 갱신 표까지 본 끝
    (`identity.session_end_of`)으로 세고, 최대 시간이 정한 끝이면 `CAP_WARNING_SUFFIX`, 쓰지 않아 끝나 가면 `IDLE_WARNING_SUFFIX` 다.
    최대 시간이 정한 끝 10분 안의 첫 회차에는 `components/sso_expiry.py` 가 사건 알림 `AD-20`(「로그인 최대 시간까지 n분 — 저장해
    두세요」)을 한 번 담는다 — 세션 칸(그 sid)과 고정 id(`alerts.event` 의 `alert_id` — sid 지문)로 같은 탭에 한 번이다. 전문 끝 줄
    「로그아웃 뒤 다시 로그인하면 시간이 새로 셉니다」 는 로그아웃(sid 폐기 · 쿠키 지움) 뒤 ADFS 콜백이 새 sid · 새 `auth_time` 을 내는
    경로 그대로다 — 로그인한 채 로그인 경로를 다시 여는 것은 끝을 늘리지 않는다(`tests/test_sso_expiry.py`). `app.py` 가
    신원이 있을 때만 부르고 담기만 한다(요소 순번 그대로). 어느 화면의 일도 아니라 화면 · 주소 없이 싣는다(`alerts.event` 의
    `pageless` — 이번 회차의 화면은 `app.py` 가 그 뒤에 적는다).
    멈춤 화면은 `st.stop()` 앞에서 껍데기 스타일(`app_header.render_shell_style` — ⋮ 메뉴 · Deploy 감춤)과 툴바 단추 감춤
    (`_STOP_TOOLBAR_STYLE` — 툴바 iframe 이 세운 Guide · Print · 테마)을 스스로 보낸다(`_render_stop_chrome`) — 앞 회차 iframe 이
    세운 단추는 듣개가 죽어 눌러도 아무 일도 없다. 알림 칸이 세운 변경 칩 · Alarm 은 듣개가 살아 있어 둔다(변경 칩은 새로고침하면
    비는 그 세션 변경 목록을 볼 마지막 자리) — 다만 판 안 「그 화면으로」 는 옮기지 못하고 판만 닫는다. 정상 회차 요소 차례는
    그대로다. 시험은 `tests/test_sso_streamlit.py`.
    구현 중 화면 숨김 판정 `unfinished_hidden` 도 여기다 — 동작 `screen.unfinished`(개발자 몫, `admin_area_locked` 와 한 뿌리 ·
    「이 등급으로 보기」 를 따름)를 화면 등급으로 할 수 없으면 참이고, `app.py` 가 그 값으로 사이드바에서 구현 중 화면
    (`navigation.PageSpec.unfinished`)을 빼고 주소 · 탭 · 알림으로 연 회차를 멈추며, 실행 관리 머리가 같은 값으로 목차의 그 화면
    카드와 이행 현황판 자리를 걷는다(2026-11-24 정식판 마감 2-A — 9장 「접속 등급」, 시험 `tests/test_grade_ui_core.py`). 입장 화면
    Introduce 티저도 같은 동작으로 가린다(`intro_summary.teaser_payload` — 가져오기 고리라 `grade_hooks.viewer_can` 으로).
  - `components/sso_reconnect.py` — 끊긴 탭의 띠 스크립트 하나(같은 틱 · 같은 물음 — `probeKind`). 툴바 iframe(`render_theme_toggle` 의
    `extra_scripts`)에 늘 싣는다 — 연결 상태 표지가 끊김인 채 3초가 지나면 같은 출처 host-config 를 묻고, 401 이면(통합인증이 켜진 서버만)
    「다시 로그인」 띠 + 같은 탭 링크(지금 경로 · 질의로 돌아옴 — 띠 글은 문지기가 그 401 에 단 까닭 낱말 머리(`names.REASON_HEADER` —
    `denied` · `unread` · `other`, `gate.ended_reason`)로 셋을 가르고(`band_texts`), 머리가 없으면 옛 글이다. 까닭이 바뀌면 띠를 다시
    세운다)를, 503 + `X-Capa-Stage`(시작 임시 응답)면 `/_capa_stage` 셋째 줄의 짧은 글을
    실은 링크 없는 재시작 띠를, 답 없음(연결 실패 · 물음 8초 넘김 `PROBE_TIMEOUT_MS`)이면 「서버 응답을 기다리는 중입니다」(답 없음 20초 넘으면
    「서버에 닿지 않습니다 — 다시 붙는 중」)를 연결 오류 창 위에 세우고 그 영어 창(401 · 5xx · 시간 넘김 · not responding · localhost 의
    still running)과 머리 상태 글(`STATUS_WIDGET_SELECTOR` — 「CONNECTING」)을 같은 표지 · 같은 지켜보기로 감춘다(띠를 걷으면 되돌리고, 띠가
    없을 때의 창 · 상태 글은 건드리지 않는다). 표 없는 5xx 는 같은 뿌리 health 를 한 번 더 물어 앱의 답(표 없는 2xx — `appAnswers`)이 아니면(앞단 502 · 504 ·
    Streamlit 준비 전) 기다림이고, 앱의 답이면 host-config 를 다시 물어 그래도 표 없는 5xx(`stillRefused` — 앱이 떠서 거절, 통합인증 설정 막힘의
    503)면 같은 자리에 설정 막힘 띠(`BLOCKED_NOTICE` — 설정 막힘 화면 `CONFIG_TITLE` 과 같은 낱말 + 지금 문서를 다시 여는 「새로고침」
    링크, 풍선 `REFRESH_TIP` — 2026-11-14 보드 english), 다시 물을 때 앱이 답하면(넘김 틈) 띠를 걷는다. 로그인 띠가 서 있으면 재시작 자리의 띠는 서지 않는다.
    꺼짐이면 재시작 갈래만(`restart_script` — 물음은 지금 경로의 폴더 기준)이라 꺼짐 툴바 iframe 에도 스크립트 하나가 실린다. IdP 로 저절로 보내지 않는다
    (로그아웃을 조용히 되돌리지 않게). 띠 색은 두 팔레트(`band_styles`)를 함께 싣고 띠를 세우는 순간 `capaTheme` 으로 앱 테마를
    골라 칠하며, 양옆 12px 안에서 내용 폭으로 가운데 선다(`left`/`right` 12px + `margin-inline:auto` + `width:fit-content`).
    띠 글은 앱 밖 공통 틀 글처럼 띄어쓰기에서만 줄을 바꾸고(`word-break: keep-all`) 띄어쓰기 없는 긴 메일 · 주소만 접는다
    (`overflow-wrap: anywhere` — 390 창에서 낱말이 가운데서 갈리던 것, 2026-11-14 보드 english 리뷰).
    바깥 화면(거절 · 로그아웃 — 공통 틀)의 보조 링크는 강조 토큰 색이다(`auth/page_frame.py`). 시험은 `tests/test_sso_reconnect.py`(판정 구획 node).
    **같은 틱에 공지 물음 갈래**(`_NOTICE_POLL` — 2026-11-17 공지 보드 q-speed)를 문지기가 있는 서버(`runtime.gate_installed()` —
    `capa_server.py`, 켜짐 · 꺼짐 모두)에만 끼운다(`app.py` 실행에는 없음 — 공지는 앱 전체 회차의 알림 칸 data 로만). 연결 표지가 `CONNECTED`
    인 동안 붙은 지 · 지난 물음에서 10초(`NOTICE_POLL_MS`)마다 같은 뿌리의 `GET /capa/notice` 를 묻고(쿠키 · `no-store` · 겹쳐 묻지 않음),
    표지 + 판(`noticeRead`)이 지난번 넘긴 것과 다르면 부모 문서의 `window.__capaAlerts.notice(payload)` 에 넘긴다(칸이 아직 없으면 쥐고 있다가
    다음 틱 — 사건 대기열 `__capaAlertQueue` 는 쓰지 않음). 첫 401 에서 멈추고(`noticeStep` — 만료 탭이 문지기를 두드리지 않게) 끊겼다가 다시
    붙으면 푼다. 그 밖 실패 · 앞단 HTML 은 다음 차례. 시험 `tests/test_notice_poll.py`(경로 · 문지기 · 판정 구획 · 가짜 창 통째).
  - `components/sso_refresh.py` — 앱 화면의 사람 입력(누름 · 키 · 휠 · 터치, `isTrusted`)이 있고 직전 갱신 뒤 5분이 지났을 때만
    `POST /auth/sso/refresh`. 타이머 없음 · 로그아웃 링크 제외 · 부모 창에 차례 상태. 통합인증이 켜진 서버만 툴바 iframe 에 싣는다.
    시험 `tests/test_sso_refresh.py`(판정 구획 node).
  - `components/access_list_admin.py` — Admin Area 「접속 명단」 펼침. 통합인증 · S3 명단이 켜진 서버의 개발자 회차에만 서고(그 밖에는 Streamlit 호출 0) 범용 편집 그리드의 줄 규칙 표(`components/access_list_grid`)와 그 위 작업 줄(저장 · 편집 취소(고친 것이 있을 때) · 다시 읽기 · 「고칠 칸 n개」, 끝에 판 · 명단 n · 개발자 n(환경변수 n) 값 — 「명단」 은 파일의 사람 수, 넓은 창에서는 표 도구 막대가 같은 줄 오른쪽 — `ONE_LINE_STYLE`)을 그리고, 안쪽 탭 줄 오른쪽 끝에 「이 등급으로 보기」 팝오버(운영 + 켜짐의 실제 개발자에게만 — 세션 칸 `sso_identity.GRADE_PREVIEW_KEY`, 화면만 · 저장은 실제 등급, 끝내기는 앱 정보 카드)를 그린다. 「저장」(2026-11-18 구현 확인 보드 「고칠 것」 — 사용자 답 「추가 · 지우기까지 표 안에서」)은 **잠그지 않는다**(등급을 고르자마자 · 새 줄 칸 편집기를 연 채 누른 첫 누름이 잠긴 단추에 닿아 버려졌다 — 2026-11-19 확인 거리 답 「권장대로」, 9장 「잠긴(disabled) 위젯」 · 풍선은 늘 `SAVE_HELP`). 콜백이 출납을 먼저 거두고(`collect` · `apply`) 초안이 없으면 아무것도 하지 않은 채 끝나고(S3 쓰기 · 감사 줄 · 알림 없음 — 빠른 둘째 누름도 이 꼴, `access_list_grid.draft_pending`), 있으면 쓰는 순간의 실제 등급을 다시 본 뒤 저장 판(`services/access_list_plan`)을 읽어 문제(빨간 칸 · 계정이 빔 · 꼴이 아님 · 머리 글 `loginid` · `계정` · 겹침 · 등급이 빔 · 잠긴 줄)가 있으면 아무것도 쓰지 않고 작업 줄 바로 아래 곁 한 줄(고칠 입력이 표에 있다)로, 없으면 지금 저장 함수로 좁히는 차례 — `grade_store.remove_people` → `change_grades` → `add_people`(등급마다 한 번, 새 줄의 이름 · 부서는 `profiles`) — 를 쓴다(`_write_plan`). 앞 쓰기가 남고 뒤가 막히면 남은 수 + 막힌 까닭을 알림창 · Alarm 한 번에 내고 저장한 사람 · 새 줄의 초안만 걷는다(`access_list_grid.forget`). 저장 · 다시 읽기의 실패 · 거부와 둘째 쓰기 실패는 알림창 · Alarm 에만(`popup_only` — UI-NTF-03). 등급 파일을 못 읽으면 `AD-25`. 접속 명단 알림 `AD-08` · `AD-09` · `AD-19` 의 「그 화면으로」 가 이 펼침을 연다(`open_access_list` — 알림 칸 받는 쪽 `access_list`). 쓰기는 그 회차의 쿠키를 다시 검증한 신원(`sso_identity.verified_identity`)을 넘기고 `auth/grade_store` · `auth/access_store` 가 다시 본다. 알림에는 수 · 까닭만 싣는다. 펼침 차례는 작업 줄 칸(`ACTIONS_BOX` — 단추 줄 + 곁 알림 칸) → 그리드 칸(`GRID_BOX` — 명단을 못 읽은 회차는 표 없는 껍데기로 마운트만) → 접힌 「최근 등록 · 빼기(30일)」(`recent_changes_table` — 파일의 고친 기록에서 스스로 등록 · 개발자가 넣음 · 뺌만, 새것 먼저, 읽기 전용 — 보드 p0-admin-list)다. 시험은 `tests/test_access_list_grid.py` · `tests/test_sso_access_s3.py`.
  - `components/access_list_grid.py` — 「접속 명단」 편집 표 어댑터. 줄은 명단 사람(파일 차례) 뒤에 빈 새 줄 `FRESH_ROWS` 개(채운 새 줄 뒤로 늘 그만큼 — `fresh_count`), 업무 키는 견주는 꼴 loginid · 새 줄 `+n`(`id_column` `_id` — 보이지 않음), 맨 앞 분류 칸 `No.` 는 차례 글(새 줄 「새 n」), 줄 이름 `_label`(상태 줄 · 변경 목록). 칸 계정(loginid 꼴 `ACCOUNT_PATTERN` — `access.LOGINID_PATTERN` + 글자 · 숫자 하나 · 64자) · 이름 · 부서(`MAX_PROFILE_LENGTH`) · 등록일(KST 날짜 `date_text`) · 등록 길(`VIA_SELF_LABEL` · `VIA_ADMIN_LABEL` — 「최근 등록 · 빼기」 의 「한 일」 과 같은 상수) · 등급(고르기 — `access_list_plan.GRADE_OPTIONS`). 줄 규칙 `RULE_KINDS` — 명단 사람(계정 · 이름 · 부서 · 등록일 · 등록 길 잠김 `LISTED_WHY`) · 나 자신(모든 칸 · 줄 지우기 잠김 `SELF_WHY`) · 환경변수 개발자(`ENV_WHY`) · 새 줄(등록일 · 등록 길 잠김, 지우기는 칸 비움). 명단 사람 · 나 · 환경변수 줄은 「계정」 이 그 줄을 가리킨다(`anchor`) — 붙인 덩어리의 계정이 그 줄과 다르면 그 줄은 등급까지 건너뛰고(토스트 「계정 칸이 다른 줄 n개는 건너뛰었습니다」), 저장 판도 명단 사람 줄의 잠긴 칸 초안을 잠긴 줄로 센다(`LISTED_LOCKED_COLUMNS`). 표는 이 회차의 명단 한 벌로 짓고 캐시하지 않는다(사람 값을 프로세스 전역 캐시에 두지 않음 — `baseKey` 는 본문 지문). 초안 · 이력 세션 칸 `CELLS_KEY` · `HISTORY_KEY`, 명단 사람 줄의 처음 (등급, 등록 시각) `ORIGINS`(처음 고칠 때 브라우저가 본 값 — 앞 회차에 그린 표 `SHOWN`) — 저장 판이 지금 명단과 다르면 「그 사이 바뀐 줄」 로 막고 「다시 읽기」 가 그 줄의 고침을 걷는다(`drop_stale` — 같은 프로세스의 먼저 쓰기는 저장소 대조가 못 잡는다), 그리드 호스트 `admin-access-grid`(줄 규칙 등록 `capa_edit_grid_rows`).
  - `services/access_list_plan.py` — 편집 표 초안 → 저장 판(`plan_changes` — 빼기 · 등급 바꿈 · 넣기와 문제 수 `Problems`, 값은 문제 글에 싣지 않음). 지운 줄은 빼기가 이기고, 표에 없는 키(그 사이 명단에서 빠진 사람)는 읽지 않으며, 새 줄 계정은 `access.entry_key` 로 견주는 꼴. 시험 `tests/test_access_list_plan.py`.
  - `components/grade_ui.py` — 접속 등급의 화면 쪽 창구(9장 「접속 등급」). `install`(판정기 꽂기 — `app.py` 맨 앞 매 회차,
    같은 함수면 그대로 — `capa_server.py` 는 꽂지 않는다) · `emit`(알림 칸 곁 거절 알림 한 자리 `GRADE_FLASH_KEY`) · `refuse`(알림창 · Alarm 한 번 — FL-04 꼴) · 받는 자리
    `on_press`(위젯 콜백 — 받고 돌아온다, 프래그먼트 회차의 콜백이면 표지 `PENDING_KEY` 를 세우고 콜백 끝에서 앱 전체로 올려 알림) ·
    `in_fragment`(`st.fragment` · `st.dialog` 함수 — 받고 `st.rerun(scope="app")`, 남은 거절 표지는 본문을 다 그린 뒤 본다 — 9장 「구역 회차 규칙」 R1) · 주소 · 알림으로 연 등급 밖 화면 · 탭 멈춤 `stop_unless`(경고 한 줄 + 「HOME 으로」 +
    `st.stop()`, 탭은 `tab_key` · `first_label` 짝으로 한 번 뒤 첫 탭) · 표 도구 막대 내려받기 단추 · 그림 막대 감춤 `toolbar_scope`(칸 key 접두
    `HIDDEN_TOOLS_PREFIX` + `app.py` 가 보내는 `TOOLBAR_STYLE` 한 벌 — 표 막대는 「Download as CSV」 단추만, 찾기 · 크게 보기는 남음, Altair 그림 막대는 「Download as PNG」 · 「Copy Vega-Lite spec」(`CHART_EXPORT_LABELS` — 2026-11-19 E2E E2-3, 「Show data」 · 크게 보기는 남음)) · `chart_config`(Plotly 그림 저장 · 표로 보기 끄기). 화면 본문의 거절은
    `page_failure_card.run_core_page` 가 받는다(다시 그리기 한 번 — 누름 없이 같은 거절이 또 오면 알림을 낸 채 멈춤). 시험
    `tests/test_grade_ui_core.py` · 도우미 `tests/grade_support.py`.
  - `components/fragment_scope.py` — 편집기 구역 회차 도우미(9장 「구역 회차 규칙」). `fragment(key)`(구역 프래그먼트 — 편집기 구역은
    `@st.fragment(key=…)` 대신 이것을 단다. 부를 때마다 끄개 `settings.editor_scopes_enabled` 를 보고 끔이면 본문을 앱 전체 회차 안에서
    그냥 그린다 — 9장 「구역 회차 규칙」 끄개) · `editor_scope(key, head=, token=, one_shot=,
    box=, page=, href=)`(구역 본문 감싸기 — `@fragment_scope.fragment(…)` · `@grade_ui.in_fragment` 아래, 머리 표지 · 저장 토큰 찍기 · 견주기, 본문 뒤
    올리기, 작은 인자 검사, 오류 카드, 구역 칸) · `escalates(key)`(콜백 끝 올리기 — `on_press` 위) · `escalate` · `escalate_if_moved` ·
    `scope_moved` · `check_small_args` · `fragment_only_run` · `in_callback` · `box_key` · `scope_box` · `SCOPE_RUN_STYLE`(머리 띠
    스타일이 싣는 구역 회차 규칙). 머리에서 화면 모듈을 읽지 않는다(`grade_ui` · `page_failure_card` 는 부르는 순간). 시험
    `tests/test_fragment_scope.py`(프래그먼트 회차 대역 · 본문 앞 올리기 금지 · 구역이 모두 끄개를 거치는지 정적 시험 · 끈 꼴).
  - `components/edit_file_tail.py` — 저장하지 않은 기준 정보 · 생산 계획 고침이 있는 동안(`scenario_activation.has_unsaved_scenario_changes()`)
    계산 화면이 그리는 내려받기 파일 이름 끝에 붙이는 꼬리 `_unsaved`(공정 Capa 상세 UPEH 가정 꼬리와 같은 꼴 — 2026-11-17 정한 것). 모든 등급
    같다. 꼬리는 계산 화면이 파일 이름을 넘기는 자리(`edited_file_name`)에서만 붙인다 — 공용 표 부품(`table_toolbar` · `shortening_board` ·
    `hierarchical_monthly_table` · `exclusion_table` · `monthly_table_workbook`)은 설비 화면도 쓰므로 그 안에서 짓는 이름에는 붙지 않는다. Static
    Capa 는 앱이 그리는 내려받기가 없다. Streamlit 표 도구 막대가 짓는 파일 이름은 바꿀 수 없다.
  - `components/grade_hooks.py` — 계산 · 시나리오 · HOME 부품이 접속 등급 창구(`grade_ui.on_press` · `in_fragment` · `sso_identity.viewer_can` ·
    `admin_view.diagnostic_message`)를 부를 때 쓰는 늦게 읽는 얇은 대리. `sso_identity` 가 모듈 머리에서 `app_header` 를 읽고 그 길이 입장 화면 →
    HOME 그리기 → `home_preference` · `home_main_cases` · `past_data_management` 까지 닿아, 그 부품이 머리에서 창구 이름을 꺼내면 덜 읽힌
    모듈로 앱이 서지 않는다. 이 모듈은 머리에서 화면 모듈을 읽지 않고 부르는 순간 창구를 읽어 넘긴다 — 동작 · 데코레이터 이름이 창구와 같아
    받는 자리 그물(`grade_support.assert_refusals_caught`)이 그대로 본다. 시험 `tests/test_grade_ui_calc.py`. 입장 화면 요약
    (`intro_summary` — `app_header` 가 머리에서 읽는다)도 티저 값의 판정을 이것으로 부른다(2026-11-24 정식판 마감 2-A).
  - `components/sso_status.py` — Admin Area 「통합인증 점검」 펼침(꺼짐이고 운영이 아니면 그리지 않음 — `APP_ENV=prod` 면 꺼짐이어도
    선다. 다만 운영 서버의 Admin Area 는 개발자 전용이라 꺼진 운영 서버에서는 화면에 닿지 않는다 — 켜기 전 미리 보기 길은 없고 켜려다 막히면 설정 화면이 같은 표로 말한다, `docs/sso_setup.md` 5장. 운영인데 꺼짐 `AD-02` 는 이 펼침이 아니라 Admin Area 가 잠금 판정 앞에서 낸다 — `render_off_in_production_alert`, 잠긴 회차에도 Alarm 으로 닿게)과 「서버 시작 점검」 표 넷째 줄 「통합인증」(결과 파일이 아니라 지금 설정에서 판정). 비밀값 · client id 값은 싣지 않는다
    (비밀값은 검사 통과 여부, client id 는 있음/없음, 계정은 앞 두 글자). **예외로 글자 그대로 싣는 것** — redirect_uri
    (`CAPA_PUBLIC_URL` 바탕) · `ADFS_ISSUER` · 서명 인증서 지문(x5t · SHA-256 앞 16자)은 포털 등록값과 한 글자씩 대 보려고 보인다.
    이 셋도 사외 리뷰 압축본 · 전문에는 옮기지 않는다(`docs/dual_env_workflow.md`). 최근 사건 표와 「명단 밖 로그인」(계정마다 한 줄 · 횟수,
    `runtime.denied_accounts` · 누계 `denied_total`)과 「로그인 전 실패」(무인증 실패 —
    따로 둔 고리와 사유별 누계, `runtime.ANONYMOUS_EVENTS`)를 나눠 보인다. 로그인 실패 줄의 사유 코드 칸 끝은 `진단 <앞 8자>`(`_event_code` — 실패 화면 참고 줄의 진단 번호와 맞추는 열쇠). 통합인증이 켜진 서버는 감사 기록이 켜져 펼침이 최근 사건 · 명단 밖 표를 그리지 않고(「접속 · 작업 기록」 탭이 사람 단위로 보인다 — 그 둘의 줄은 「복사」 글 `status_text` 에만) 「로그인 전 실패」 표는 그대로 그린다 — 감사 줄에는 그 실패가 한 시간 건수뿐이라 겹치지 않는다(보드 decided-login 5). 사실 줄은 「라벨 · 값」 꼴이다 — 「로그인 유지 · 마지막 사용 뒤 n시간 · 최대 n시간」,
    켜짐이면 그 아래 「로그인 시작 · 돌아옴」 누계(`runtime.login_flow_counts` — 시작은 브라우저 문서 탐색을 IdP 로 보낸 수(`web.browser_navigation`), 돌아옴은 그 로그인이 검증한 상태 쿠키와 처음 온 콜백(실패 · 거절 · IdP 오류 포함, 꼴이 틀린 POST · 다시 보냄은 빼고), 돌아옴이 시작보다 훨씬
    적으면 ADFS 화면에서 멈춘 것 — 풍선 `LOGIN_FLOW_HELP`)와 「로그인 갱신」 누계(`runtime.refresh_counts` — 다시 발급 · 건너뜀 · 로그인 없음 · 출처·머리 거절 · 꼴 거절,
    재시작하면 0)를 한 줄씩 보인다(둘 다 사건 고리에 적지 않는다). 접속 명단은 사실 줄에 개수만(`access_line` — 개발자 · 관리자 · 실무자 · 열람 · 읽지 못함, S3 명단을 쓰지 않거나 아직 켜지지 않은 서버는 개발자 · 그 밖 — 등급 이름은 「접속 명단」 표와 같다), 그 아래 「S3 명단」 줄(`access_s3_line` — 꺼짐 · 정상 · 실패와 까닭 분류 · HTTP 상태 · 명단 n · 버전 · 쓰기 칸, 있으면 `모르는 등급 값 n` · `스스로 등록 실패 n`, 키 · 주소 · 값 없음이라 리뷰 압축본에 옮길 수 있다), 그 아래 마지막 로그인의 클레임 이름(값 없음,
    `runtime.last_login_claims` — 그룹 클레임이 오는지 보는 길)을 싣는다. 감사 기록이 켜진 서버는 최근 사건 표 대신 앱 시작 실패 줄(`boot_failure_line` — 「앱 시작 실패 · <갈래> · <오류 종류> · <처음 시각>」, 고리 전체(50줄)의 `boot_fail` 마다 한 줄 · 시각은 판의 참고 줄과 같은 UTC 분)을 늘 싣는다 — 감사 대응표 밖이라 「접속 · 작업 기록」 탭에 없다(보드 boot-record). 감사가 꺼진 서버는 최근 사건 표가 같은 줄을 싣는다. 시험은 `tests/test_sso_status.py` · `tests/test_sso_access.py`.
  - `scripts/s3_mock_store.py` — 개발 · 시험용 가짜 S3(서명을 받은 요청 그대로 다시 지어 검증 · 메모리만 · 루프백만 · env 파일이 작업 트리 안이면 거절). S3 명단 시험과 `docs/sso_setup.md` 8장이 쓴다.
  - `scripts/sso_mock_idp.py` — 개발 · 시험용 가짜 IdP(실행 때 RSA 키를 메모리에만 만든다, `APP_ENV` 가 운영이면 · 루프백이 아닌
    `--host` 면 · env 파일이 작업 트리 안이면 거절). 실제 ADFS 없이 로컬 · 사내 WebIDE 에서 로그인 흐름을 끝까지 돌린다. `--app-url` 이 루프백이 아니면 env 파일에 `--loginid` 를 개발자 목록으로 적는다(접속 명단이 켜지므로).
- `app_pages/home.py` — HOME 대시보드(공정 필터 「선택 공정 적용」 은 좁힌 공정을 `shared_process.publish_from_home` 으로 다른 화면의 공용 공정 칸에 복사만 한다 — 다른 화면 값은 B/N 판정 · 리비전 저장값 `PROCESS_SELECTION_KEY` 에 들지 않는다, 2026-11-08 답 P1 · P2-1. 팝업 단추 글자는 표시명 `unique_format_func` 라 겹친 표시명도 갈린다). 탭 없이 한 화면(계획·LOB·주요공정·B/N Figure)이고 공용 설정(Preference 공용 프로필
  편집기·`Past Data` — `past_data_management.py`)은 사이드바 「HOME 설정」 상자가 여는 큰 팝업이다(`components/home_settings.py`,
  2026-11-02 사용자 요청 — 전에는 Main·Preference·Past Data 세 탭). 팝업 안은 쓰는 묶음 다섯 탭 `비교 · 주요 Case` · `판정 기준` ·
  `선행 · 보정` · `Capa 요약 · 표시` · `Past Data` 다(2026-11-04 사용자 검수 home-u01 — 라벨은 `home_state`, 앞 넷은
  `home_preference.render_home_preference` 가 탭을 라벨로 받아 상자를 놓는다). 설명은 `guides/home.md`.
  - 보는 조건(토글 일곱·제품별 비중 단위)은 조건 카드 `LOB 표시 조건`, 키·기본값은 `home_state.py` 한 곳이다. 시나리오를
    바꾸면 토글을 기본값으로 적어 푼다(`scenario_activation.py`·`test_scenario_activation.py`). 공정 필터는 패널 칸이다.
  - 패널 칸 팝업(공정 필터 · 주요공정 히트맵)의 머리에는 설명 글을 두지 않는다(2026-11-04 검수 의견 home-20 · home-21).
    공정 필터는 머리 「선택 n / N」 한 줄이고 무엇을 고르는지 · 기간 · 확보 기준은 그 줄의 풍선, 판정 기준을 정하는 자리와
    프리셋을 고치는 자리(HOME 설정 → `판정 기준` · `Capa 요약 · 표시` 탭)는 Guide 가 말한다. 화면 확인 `process_popup` 이 머리 설명 0줄을 본다.
  - 공정 필터 팝업 작업 줄 아래 둘째 줄이 공정 그룹 단추다(`show_process_filter_dialog(group_buttons=)`). 누르면 초안이 그 그룹 공정만
    남고(「전체 ON」 과 같은 초안 콜백) 판정 대상은 「선택 공정 적용」 이 바꾼다. 대응은 여는 회차에만 읽고(`_process_filter_dialog` →
    `process_group_buttons`, 읽기 실패는 빈 대응) 대응 없는 그룹은 단추가 없으며, 이번 선택지에 그 그룹 공정이 없으면 잠그고 까닭
    풍선(`PROCESS_GROUP_ABSENT_HELP`)을 단다 — 켜진 단추에는 `help` 를 달지 않는다(다시 그리는 팝업에 풍선이 열린 채 남는다).
  - 공정 필터 팝업 「확보율 없음」 구역의 계산 밖 공정(경로가 모두 소요기준 BOX · PCB — 11장) 단추는 이름 오른쪽 「계산 밖」 과 풍선 줄
    「소요기준 BOX — 산식이 정해질 때까지 계산 밖입니다(추가 예정).」 이다(2026-11-24 사용자 「권장안 그대로」). 목록은 산출 결과 표
    제목 줄 표지와 같은 칸(`get_unimplemented_basis_processes` — 선언을 접지 않은 내용 토큰 + 계산 조회기간)이고 여는 회차에만
    고른다(`_process_filter_dialog` → `whole_outside_bases` — 원본 공정 키, `show_process_filter_dialog(outside_bases=)`). 구역 · 켜고 끄기 ·
    판정은 그대로다(`tests/test_home_page.py` 의 `only_box_routes_says_outside_calculation_in_the_process_filter`).
  - 「상세 B/N 공정」 제목 줄 오른쪽 끝에는 조회기간에 계산 밖 공정(소요기준 BOX · PCB 경로가 있는 공정 — 11장)이 있을 때만 작은 회색
    「계산 밖 n공정 ⓘ」 가 선다(2026-11-24 사용자 답 — B/N 순위가 그 공정 없이 정해지는 자리). 앱 전체 회차가 같은 목록 칸을 읽어
    `outside_calculation_mark`(풍선 차례는 공정 필터 선택지와 같은 확보율 탭 표시순서 — 세션 메모 `home_sort_memo` 의
    `outside_order` 칸)로 짓고 `render_home_figures(bottleneck_mark=)` 로 넘긴다. n 은 공정 필터와 상관없이 조회기간 전체의 수이고,
    그림이 아니라 제목 줄 글이라 Figure 캐시 키 · `HOME_FIGURE_SCHEMA_VERSION` 은 그대로다(`tests/test_home_page.py` 의
    `bottleneck_title_row_carries_the_outside_calculation_mark`).
  - 카드는 HOME 에서 늘 서고(2026-11-02 — 전에는 `Main` 탭에서만) 계산이 `BOOTSTRAP_ERRORS` 로 멈춘 회차에도 그린 뒤
    멈춘다 — 오류문이 시키는 `EDP 포함` 켜기·`GAP` 끄기를 그 자리에서 한다(2026-10-22, `test_home_page.py` 의
    `stopped_home`). 그 회차의 「HOME 설정」 상자는 잠긴 채 같은 자리에 서고(팝업 본문이 계산 결과를 쓴다) 열려 있던
    팝업은 닫으며, 미지정 주요 Case 칩도 잠근다(`home_main_case_chips.stopped_chips`).
  - 얹기 규칙(EDP 제외 범위·확보율 보정 → 선행 `advance_load.py`·GAP 기준)은 6장, 판정 기준은 `securement_threshold.py`.
    비교 대상 프로필은 바뀔 때만 쓴다(`test_comparison_profile_writeback.py`·`test_summary_recheck_paths.py`).
  - 세션의 비교 짝은 HOME 첫머리에서 **걷고**(`forget_unlisted_comparison` — 가리키는 시나리오가 보관·영구 삭제됐으면) 바로
    심는다(`seed_comparison_selection` — 걷었으면 같은 회차에 공용 프로필 값으로 선다). 비교 피커는 팝업을 연 회차에만 돌아 그 몫을 맡을 수 없다(전에는 숨은 HOME 본문 `Preference` 탭이
    매 회차 걷었다 — 2026-11-02 검토). 목록은 비교 대상 프로필과 같은 쓰기 세대의 캐시
    (`persistence/cache.listed_comparison_candidates` — 보관·삭제가 그 세대를 올린다)이고, 캐시에 없을 때만 DB 목록으로 한 번
    더 본 뒤 걷는다(새 시나리오는 세대를 올리지 않는다). `tests/test_home_page.py` 의 `removed_elsewhere` ·
    `newer_than_the_cached_list`. GAP 이 켜진 회차의 비교 짝 확인(그 리비전이 그 시나리오 것인가)도 같은 세대로 캐시한 리비전
    목록에서 본다(`persistence/cache.scenario_has_revision` — 목록에 없으면 DB 로 한 번 더 본다, 회차마다 DB 를 열지 않는다).
  - **토글 회차는 그림과 상관없는 정렬 · 합치기를 다시 하지 않는다** — 세션 메모(`SessionSlot` `home_sort_memo` — 칸 이름은
    `home_state.HOME_SORT_MEMO_KEY`, 이름마다 두 벌)에 표시순서 준비(키 = HOME 계산 키의 표시순서 지문) · 공정 선택지 차례(공정
    이름들, 지문) · 「상세 B/N 공정」 표지 풍선의 계산 밖 공정 차례(계산 밖 공정 이름들, 지문) · 과거 열을 붙인 계획 세부수량(HOME
    계산 키 — 계산 토큰 · 기간 · 지문, EDP, 거래선 칸, 과거 프로필 version) ·
    과거 열 · 조각의 부품 판정(`product_parts.multi_part_products` — 키 = HOME 계산 키의 계산 토큰(5장 44 — 판정은 그 앞머리 내용 토큰이 정한다), 계획 세부수량 과거 열과 제품별 비중 과거 조각이 한 칸)을 기억한다(`home._remembered`). 키는 결과를 정하는 입력 전부이고 꺼낸 표는 사본, 공정 목록은 새 list 다. 붙일 과거 열이 없으면
    규칙을 보지 않고, 표시순서 오류는 같은 try 가 받는다(기억하지 않는다). 시나리오를 바꾸면 `_STALE_VALUE_KEYS` 가 지운다.
  - Figure: 옵션과 무관한 행 높이·글자 크기, 조정 0건이면 조정 전과 같은 JSON(`test_bar_corner_radius.py`), 숨은 탭
    금지(`test_hidden_tab_rendering.py`). 제품별 비중(`product_share.py`)의 색 구분은 `test_categorical_palettes.py`.
  - 계획 세부수량 · 상세 B/N 구획은 토글(옛 「계획·B/N 상세표 표시」)로 늦게 만들지 않는다.
  - 제품별 비중 도넛은 같은 제품의 양산 · ER 을 더해 비중을 낸다(분모는 Wafer 면 `Wafer 계획` 행, PKG 면 그 달 PKG 생산수량 전체). 색 칸은 화면 전체에서 한 번 정해 달 · 단위 · EDP · Past Data 토글과 상관없이 같은 제품이 같은 색이다. 칸은 여섯이라 넘치면 PKG 생산수량이 작은 제품부터 「기타」 로 접고(이름 칸 다섯 + 기타 — `PRODUCT_SHARE_SLOT_COUNT`), 과거 구간 달의 Wafer 도넛은 제품별 Wafer 를 몰라 비운다(`past_product_volume`).
  - 제품별 비중은 부품(`CUSTOM`)이 둘 이상인 제품만 부품마다 조각 · 색 칸 · 범례 이름표다(8장 「합쳐 보는 화면의 부품
    이름표」 — 조각 합은 그대로 `Wafer 계획`). 판정은 HOME 캐시 두 함수(`get_home_simulation` · `get_home_lob_without_edp`)가
    받은 리비전 계획 전체(`_tables["RQ_PKG_PLAN"]`)로 하고 수량 프레임의 `CUSTOM` 칸에 접힌 값으로 싣는다 — 캐시 키 ·
    반환 꼴은 그대로다. 과거 구간 조각은 `past_product_volume(multi_part=)` 가 「제품 (-)」 로 채운다 — 그 과거 전용
    조각은 칸 배정을 마친 뒤 같은 제품의 부품 가운데 이름 있는 칸을 받은 첫 부품의 색 칸을 빌린다(2026-11-24 그림 보드 3
    답 q7-past-slice (나) — `ProductSlots.lenders`, 칸 수 · 다른 제품 칸 · `기타` 접힘 그대로, 그 제품의 부품이 모두 접혔으면
    지금 규칙, 빌려 준 부품과 한 도넛에 함께 서면 그 칸만 `ProductSlots.fallback`). 그 조각이 그려진 화면(Past Data 를 켠
    PKG 단위)의 범례는 빌려 준 부품 줄 곁에 같은 칸 번호(같은 색)로 「제품 (-)」 줄을 하나 더 둔다 — 그 제품의 그려진 부품 줄
    가운데 마지막 줄 바로 뒤, 끄면 없음(같은 날 그림 보드 4 답 q7-past-legend (나) — `product_share_legend`). 범례는 두 칸 ×
    네 줄(여덟 항목)까지이고 넘치면 더한 「(-)」 줄부터 뒤에서 뺀다 — 그려진 색과 `기타` 는 늘 제 줄이 있다
    (`_legend_rows_within_limit`). 범례 줄임은 `_fit_part_label` 이다(더한 줄도 제품 쪽을 줄여 「DEMO-H… (-)」 · 풍선에 온전한
    이름 — `tests/test_product_share_parts.py`). `기타` 풍선은 늘 첫 줄 「달 · 기타 비중 · 수량」, 둘째
    줄부터 모인 이름이다 — 이름은 줄이지 않고 다 적되 한 줄에 셋, 넘긴 줄 끝에 쉼표, 이름 줄 넷(이름 열둘)을 넘는
    이름만 마지막 줄 끝 「외 N」(`_other_member_lines` · `_PRODUCT_SHARE_HOVER_NAME_LINES` — 같은 날 그림 보드 4 답
    q7-hover-cap (나), `tests/test_product_share.py`). 이름에 부품 이름표가 끼든 말든 한 꼴이다
    (2026-11-24 그림 보드 3 답 q7-other-hover (나) — LOB · PKG · 과거 달 도넛이 같은 `_product_share_hover`, 입장 화면
    Summary 조각 풍선은 이름 · 비중 한 줄의 따로 그리기라 해당 없음). `기타` 는 늘 마지막 조각이라 Plotly 가 풍선을
    왼쪽으로 펴고, 가로 스크롤 칸 안이라 넓은 풍선의 앞머리가 왼쪽 고정 구분 칸 밑에서 잘린다 — 한 줄 이름을 셋으로
    짧게 둔다. 풍선은 조각 기준점 위아래로 반씩 펴져 그림 아래 밖은 잘린다 — 이름 줄 상한이 그 몫이고, 기타가 도넛
    절반을 크게 넘는 달은 상한 안에서도 아래가 잘린다(규칙집 6-41 q7-hover-rest).
  - 계획 세부수량 · 비교 덤벨도 같은 판정으로 그 제품만 부품마다 줄이다 — 분류 차원이 (제품정보, `CUSTOM`, Stack[, Customer])
    이고 HOME 캐시 네 함수(`get_home_simulation` · `get_home_lob_without_edp` · `get_home_plan_detail` ·
    `get_home_comparison_plan`)가 받은 리비전 계획 전체로 판정해 `build_production_dashboard(multi_part=)` 에 넘긴다. 비교
    계획은 **현재** 리비전 판정으로 접혀 짝을 못 찾은 행만 「제품 (-)」 줄이고, 과거 열은 `past_plan_detail_to_wide(multi_part=)`
    가 채운다. 캐시 키 · 반환 꼴은 그대로다(`tests/test_dashboard.py` · `test_plan_detail_figures.py` 의 HOME 진입 ·
    `test_lob_summary_gaps.py`).
  - HOME 맨 위에는 결론 줄(최저 확보율 공정·기준 미달 수)도 「소요대수에 들지 않은 수요」 줄도 두지 않는다 — 리비전마다
    계산에서 빠진 행은 시나리오 관리 › 목록 관리 「점검」(`components/scenario_input_check.py`)이 저장 리비전 전체 기간으로
    센다(2026-11-11 입력 점검 보드 q7). 측정률 가정 한 줄은 남는다.
  - 주요 Case 칩 셋(`공식 vN`·`Case1`·`Case2` — `components/home_main_case_chips.py`, 2026-10-23)은 `LOB 표시 조건`
    카드 맨 위 항목이다(2026-11-02 — 전에는 본문 제목 줄 끝). 카드는 그래서 HOME 에서 처음 펼친 채 선다
    (`condition_card(default=True)`). 제목 줄에는 끝 칸이 없어 본문이 화면 탭 줄 바로 밑에서 「Capa 요약」 으로 시작한다.
    팝업 열림 칸·안쪽 탭 key·라벨은 `home_state.py`(칩이 미지정 Case 를 누르면 팝업을 `비교 · 주요 Case` 탭으로 열고 그 Case
    칸을 한 번 강조한다 — `home_main_cases.focus_main_case`).
  - **「HOME 설정」 팝업이 열린 회차에는 팝업을 열기 전 그림을 그대로 쓴다**(`HOME_DRAWN_CONDITIONS_KEY` 의 네 묶음 —
    `home_rendering.take_home_figure_set`). 팝업은 저장 뒤에도 열려 있어 그 회차에 공용 프로필 version 이 바뀌어도 모달
    뒤 그림을 만들지 않고, 닫는 회차(`on_dismiss` — 앱 전체)에 지금 조건으로 한 번 만든다(전에는 숨은 Main 탭이 같은 몫을
    했다 — `tests/test_home_settings_kept_figures.py`). 월 축·과거 칸·덤벨 상자도 그 그림의 조건에서 읽는다. 꺼낼 묶음이
    하나라도 없으면 평소처럼 만든다.
- `app_pages/load_conversion.py` — `생산 계획` 화면. `환산`·`PKG PLAN`·`수율` 탭으로 계획·수율을 편집하고
  부하량 환산을 보인다. 조건 카드·Guide(`page_guide.py`, `guides/load_conversion.md`)를 처음 적용한 화면이다.
  - 환산 조건은 조건 카드이고 환산은 그 탭이 열렸을 때만 한다. 카드 차례는 소요기준 → 집계 기준(segmented_control
    `monthly_volume_aggregation` — 「산출 기준 총량」(기본) | 「HOME 집계 기준」, 값은 `load_calculator.MONTHLY_AGGREGATIONS`) →
    상세 · EDP 다. 집계 기준은 Chip · Wafer 에만 뜻이 있어 PKG · Density 에서는 숨기지 않고 잠그고(까닭 풍선 `AGGREGATION_LOCKED_HELP`)
    그 동안 계산 · 제목 기준 글 · CSV 이름은 늘 총량이다(칸에 남은 값이 파일 이름에 새거나 캐시 칸을 늘리지 않게 — 한 값
    `aggregation` 을 셋이 읽는다). Chip · Wafer 표 제목 줄 부가 설명은 「단위: … · <기준>」 이고 HOME 집계 기준일 때만 그 글
    풍선(`table_toolbar.render_table_heading(caption_help=)`)이 뺀 `WF 구분` 이름(`DUMMY_SERIES_DIVISIONS_BY_PRODUCT_TYPE` 에서
    읽음)을 말하며 CSV 파일 이름 꼬리 `_HOME` 이 붙는다. 표 · CSV 분류 칸은 `CLASSIFICATION_COLUMNS`(상세면 `WF 구분` 더함)에서
    낸다 — 계산이 분류 칸을 더하면 저절로 따라간다(`tests/test_load_conversion_aggregation.py`). 작업 줄(적용·붙여넣기·가상 제품 등록)은 표 위, 붙여넣기와
    등록은 세션 키 팝업이다. PKG PLAN 붙여넣기는 탭에만 올리고 전역 반영은 적용 한 곳이며, 수율 붙여넣기는 바로 적용한다. 붙여넣기 창 · 거부 · 적용
    알림의 표 이름은 화면 이름(`PKG_PLAN_TAB_NAME` · `YIELD_TAB_NAME`)이고, 대기 표 달 칸은 숫자로 읽어 0 을 빈칸으로 그린다.
  - **PKG PLAN · 수율 표는 범용 편집 그리드다**(2026-11-12 보드 답 k-a1 · k-a2 — `components/plan_grid.py`, 이름은
    `plan_grid_keys.py`). 탭마다 그리드 하나(호스트 `plan_grid` · `yield_grid`)이고, 탭 본문은 작업 줄 칸 → 그리드 칸(둘 다 key 붙은
    늘 서 있는 칸 — `plan_grid.LAYOUTS`) 차례다. **두 칸은 표마다 편집기 구역이다**(9장 「구역 회차 규칙」 — 키 붙은 프래그먼트
    `load_conversion_plan_scope` · `load_conversion_yield_scope`, PKG PLAN 구역은 적용 뒤 수요 알림 자리까지). 칸 고치기는 그 구역 회차로
    돌고, 구역 밖이 그리는 값(표마다 초안 칸 있음 · 적용할 초안 있음, 붙여넣기 대기 · 열린 팝업 · 스스로 적용한 표 · 고른 탭 · 활성
    시나리오 내용 · 조회기간 — `plan_grid.scope_head`)이 바뀌면 출납 · 작업 줄 단추 콜백 끝(`scope_key` — 「⋯」 메뉴는 닫기까지 마친
    뒤) · 본문 뒤에서 앱 전체 회차로 올린다. 팝업 둘은 구역 밖(탭 안 구역 뒤)이라 여는 콜백이 올려 그린다. 앱 전체 회차의 출납 반영은
    표 탭 점보다 먼저 대본이 하고(반영이 초안 칸을 비우면 한 번 더 돈다), 구역 회차는 구역 본문이 그 표 출납을 반영한다
    (`_scope_grid`). 구역 회차의 표 · 인자는 마지막 앱 전체 회차의 것이다(원본을 바꾸는 조작은 머리 표지가 올린다 — 원본은 세션의
    활성 시나리오라 저장 토큰 견주기는 없다). 구역 회차는 `app.py` 의 실행 핀 밖이라 PKG PLAN 구역 본문이 시나리오 DB 핀
    (`pinned_connections`)을 스스로 잡는다 — 적용 알림 창 안의 수요 알림이 공정 표시명을 캐시가 빈 회차에 DB 에서 읽는다(수율 구역
    본문은 DB 를 열지 않는다). 이 세션에 한 번도 연 적 없는 탭은 그리드를 세우지 않고(`plan_grid.mounted` — 그리드
    요소는 등록 JS · CSS 를 싣는다), 연 적 있는 탭이 닫힌 회차에는 양식을 짓지 않고 앞서 보낸 껍데기 · feed 를 그대로 다시 보내(해시
    참조 — `plan_grid_keys.last_key`) 마운트만 남는다. 열린 탭인데 수율 표를 세우지 못한 회차는 표 없는 껍데기다(진입
    전송량은 옛 편집표보다 줄고, 각 탭을 처음 열 때 그리드 요소를 받는다). inbox 에 op 가 쌓인 표와 적용이 눌린 표는
    닫힌 탭이어도 양식을 짓는다. PKG PLAN 양식은 붙여넣기 대기 표가 있으면 그 표이고(내용 지문에 대기 표 지문을 더한다), 달 칸을
    수로 읽어 0 을 빈칸으로 싣는다(`plan_grid.zero_as_blank` — 비운 칸은 적용 때 `plan_from_edit_table` 이 0 으로 읽는다). 값 형식은
    `plan_grid.FORMATS`(PKG PLAN 천 단위 · 소수 없이 · 0 이상, 수율 percent · 상한 1). 「변경사항 적용」 은 **잠그지 않는다**(고친 칸이
    서버에 닿기 전 — 편집기를 연 채 · Enter 직후 — 의 누름이 잠긴 단추에 닿아 버려지던 E2E E1-D2, 2026-11-19 아침 확인 보드
    m19-e2e-first-apply (가) — 풍선은 늘 하는 일이고 잠긴 까닭 풍선이 없다). 칸 오류가 남았으면 고칠 칸
    알림(`plan_grid.error_notice`)으로 멈추고, 아니면 양식에 초안을 업무 키로 덮어(`plan_grid.merged`) 옛 적용 길(`plan_from_edit_table` → `attach_plan_attributes` → `apply_month_updates` · `_apply_yield`)을
    탄다. **적용은 단추 콜백이다**(`_apply_plan_click` · `_apply_yield_click` — 본문보다 먼저 돌아 누름 하나에 회차 하나가 새 계획으로
    그린다, `st.rerun` 없음). 콜백은 그 표 출납을 먼저 받아 초안에 반영하고(`plan_grid.settle_inbox` — 단추 콜백이 그리드 출납
    콜백보다 먼저 돈다, 같은 seq 는 한 번), 고친 칸 · 붙여넣기 대기가 없으면 아무것도 하지 않는다(알림도 없다 — 같은 값 적용으로 리비전만
    오르지 않게). 편집 직후의 누름은 그 편집까지 적용한다 — 그리드가 편집기 blur · 표 밖 focusout 에서 그 op 를 click 보다 먼저 보내고
    누름의 rerun 은 그 출납 값을 함께 싣는다(9장 「범용 편집 그리드」). 칸 오류 · 업무 규칙 오류는 글로
    담아(`plan_grid.refuse` — 세션 칸 `SessionSlot` `plan_grid_apply_refusal`) 그 표 작업 줄 아래 알림 칸 한 곳이 같은 회차에
    그린다(`plan_grid.render_actions` — `Actions.notice` 자리, 까닭은 「누른 동작의 실패」 UI-NTF-03). 쓰기 차례는 `apply_month_updates`
    → 완료 표지(`_queue_done`) → 붙여넣기 대기 비움 → `mark_own_change` 이고 「계산 안 된 수요」(`ST-04`)는 그 회차 그리드 뒤에
    센다. 콜백은 앞 회차에 그린 단추의 인자로 불리므로 단추를 그린 원본(이 화면 원본 토큰 · 활성 시나리오 내용 토큰 · 고른
    조회기간 · PKG PLAN 붙여넣기 대기 표)과 지금 원본이 다르면 쓰지 않는다(`_still_drawn` — 팝업이 원본을 바꾼 뒤 앱 회차가 단추에
    닿기 전 누름, 같은 단추의 빠른 둘째 누름). 활성 시나리오는 소유 모듈 창구 `scenario_state.ACTIVE_SCENARIO` 로 읽고, 시나리오를
    세션에서 빼는 길(`scenario_activation.clear_persisted_scenario_activation`)은 이 화면 원본 토큰 칸도 지우므로(`_STALE_VALUE_KEYS`)
    시나리오가 없는 세션은 그 칸 대조가 거른다. 다른 팝업이 리비전만 올린 바로 뒤 그 틈의 누름은 쓰이지 않는다 — 초안 · 단추가
    그대로라 다시 누르면 적용된다(`docs/TODO.md` 2장 「성능」 C1). 기준 정보 「변경사항 적용」 은 아직 본문 길이다(단추가
    `reference_grid.render_actions` 안이라 `on_click` 자리가 없다). 「편집 취소」 는 초안(과 PKG PLAN 이면 붙여넣기 대기)을 버린다. PKG PLAN 작업 줄 글은 「변경사항 적용」 · 「Excel 붙여넣기」 ·
    「⋯」(풍선 「더 보기」 — 안에 「가상 제품 등록」, 2026-11-12 보드 답 n2 나) 차례이고 수율은 「변경사항 적용」 · 「Excel 붙여넣기」 다(같은 화면의 같은 일 한
    이름 — 2026-11-12 남은 물음 보드 ③-9 (가)).
  - 원본이 바뀌어 편집을 버린 회차는 칩 · 탭 점이 버리기 전 값으로 섰으므로 한 번 다시 돈다. 그리드 초안 · 이력과 붙여넣기 대기는
    업무 키 · 제 차례라 줄 차례만 바뀐 회차에 남는다(`order_free_keys` — 이 화면에서는 `ST-09` 가 서지 않는다). **활성 리비전만 바뀐
    회차**(다른 화면의 적용 — `scenario_edit_bar.only_revision_changed`)에는 기준 정보 그리드와 같은 꼴로 초안이 있는 표마다 이 적용 뒤
    그릴 양식의 내용 지문을 초안을 둔 때의 지문(`plan_grid_keys.TEMPLATE_DIGESTS_KEY` — 양식 키가 바뀐 회차에만 다시 잰다,
    `_remember_grid_digests`)과 견줘 같으면 초안 · 이력을 남기고(`_grid_survivors`), 다르거나 지문이 없으면 버린다. 붙여넣기 대기는 이런
    회차에 늘 버리므로 PKG PLAN 은 시나리오 표 양식으로 견준다(대기 표 위 초안은 함께 버려진다). 버린 것(「PKG PLAN 3칸」 · 「PKG PLAN
    붙여넣기」)은 다시 돌지 정해진 뒤 PKG PLAN 작업 줄 알림 칸(`GRID_DROPPED_FLASH_KEY`)이 알림창 · Alarm 으로만 한 번 알린다 — 글은
    기준 정보와 같은 `scenario_edit_bar.OTHER_APPLY_DROPPED_NOTICE`, 버린 표가 닫힌 탭일 수 있어 `popup_only`(2026-11-12 검토 — 전에는
    어느 화면의 적용이든 두 표 초안을 말없이 버렸다).
  - 가상 제품 등록(기준정보 복제, `virtual_product.py`)은 미적용 편집을 버리므로 먼저 알린다 — 창 맨 위는 경고 상자가 아니라 값 줄
    (고친 칸 수 · 붙여넣기 대기 칸 수, 2026-11-07 g3-19 — 기준 정보 STEP 창도 같다)이고 남기는 법은 등록 단추 풍선이다. 값이 비거나
    범위 밖인 수율 행은 잠가 원본 그대로 되붙이고, 0 이하·100% 초과는 계산을 멈춘다(숨기지 않는다).
  - 상태 알림(9장 「알림 칸」): 환산에서 빠진 계획 `ST-05`(환산 탭이 열린 회차), 값을 뺀 수율 행 `ST-06`(수율 탭이 열린
    회차), PKG PLAN 적용 뒤 소요대수에 들지 않은 수요 `ST-04`(적용 알림이 서는 회차 — 시나리오 전체 기간). `ST-05` · `ST-06` 목록은 크기와
    상관없이 그 Alarm 줄의 표다 — 상한을 넘으면 앞부분만 싣고(`alert_table(clip=True)`) 글이 「앞 n건 · 전체 m건」 과 전체 자리를
    부르며, 전체는 그 탭 맨 아래 CSV 단추 하나(환산 `download_excluded_plans_csv` · 수율 `download_locked_yield_csv` — 그 탭이 열린 회차만)다. 고칠
    곳은 까닭 칸(`누락 기준정보` · `사유`) 머리 풍선이다(펼침 안 설명 문장 없음 — `docs/design_rules.md` UI-TXT-01 · 02). 줄 차례가 바뀌어 편집을 버린 회차는 사건 알림 `ST-09`. 수율 붙여넣기 팝업이 이 알림
    자리들 뒤라 셋 다 갈래와 상관없이 이벤트 칸 한 자리를 쓴다(조건이 없거나 탭이 닫히면 `alerts.flush`).
  - 편집표 원본은 `simulation_cache` 가 시나리오 키 + 표시순서 지문으로 캐시한다(`test_plan_edit_table_cache.py`).
- `app_pages/reference_data.py` — `기준 정보` 화면. Capa 산출 입력(UPEH·설비대수·효율·여유율·일수·측정률·STEP 구성)을
  월별로 편집한다. 설명은 `guides/reference_data.md`.
  - **탭 대신 종류 단추 한 줄 + 큰 편집 표 하나**(2026-11-02 사용자 결정 — 편집 표 횡전개). 단추는 네이티브
    `st.segmented_control`(`reference_grid_keys.DATASET_KEY`, 선택지 = `DATASETS` 열 개 — 옛 탭·설비대수 안쪽 탭을 옛 차례로
    편 것, 기본 UPEH, `persist_state="session"`, 기본값은 위젯 `default=` 가 아니라 세션에 심는다)이다. 설비대수 세 표의 단추
    글은 「보유대수」 · 「대여대수」 · 「가용대수」 다(2026-11-12 보드 답 k-b1 — 화면 글만, 표 이름 · 표시순서 범위 · DB 키는 그대로). 그 아래 늘 서 있는 칸
    차례가 계약이다 — 작업 줄 칸(`reference_actions`) → 그리드 자리(`reference_grid_box` — 범용 편집 그리드 마운트 하나,
    `reference_grid_keys.GRID_HOST`) → 읽기 보기 칸(`reference_view` — 「STEP 구성」 을 골랐을 때만 채운다). 세 표를 합쳐 보던
    「설비대수 현황」 보기는 없다(같은 답 k-b1). 작업 줄 칸 · 그리드 자리는 **편집기 구역**(9장 「구역 회차 규칙」 — 키 붙은
    프래그먼트 `reference_data_grid_scope`, 대본 앞쪽의 늘 서 있는 칸 안에 대본 끝에서 부른다)이다. 칸 고치기는 그 구역 회차로 돌고,
    구역 밖이 그리는 값(표마다 초안 칸 있음 · 적용할 초안 있음, 고른 종류 · 그 종류의 「표 조건」 고른 값 · 공용 공정 값, 열린 팝업 ·
    스스로 적용한 표 · 활성 시나리오 내용 · 조회기간 — `reference_grid.scope_head`)이 바뀌면 본문 뒤(출납) · 콜백 끝(「Excel
    붙여넣기」 · 「편집 취소」 — `scope_key`)에서 앱 전체 회차로 올린다. **출납 콜백은 올리지 않는다**(9장 「구역 회차 규칙」 R8
    의 예외) — 「변경사항 적용」 은 본문이 누른 회차에 판정하는 단추라 같은 상호작용의 콜백 끝 올리기(`st.rerun()`)가 그 누름을
    버린다. 그래서 첫 칸의 초안 있음 표지도 본문 뒤에서 올라, ack 를 그린 구역 회차와 앱 전체 회차 사이 틈은 탭 줄 붙들기의
    조용함(`HOLD_QUIET_MS`)만 가린다(적용을 콜백으로 옮기면 걷힌다 — 생산 계획 꼴). 구역 회차의 적용은 머리 표지가 본문
    뒤에서, 앱 전체 회차의 적용은 대본이 붙여넣기 호스트를 그린 뒤 다시 돈다. 「Excel 붙여넣기」 는 구역 안 여는 콜백이 호스트만
    다시 돌리고(`rerun_fragment_if_alone`), 그러지 못하면 열림 칸이 바뀐 머리 표지가 앱 전체로 올린다. 사이드바 「표 조건」 카드는
    구역에 넣지 않는다(바꾸면 앱 전체 회차). 구역 본문은 DB 를 열지 않아 DB 핀을 잡지 않는다(적용도 세션의 활성 시나리오에만 쓴다).
    그리드 마운트는 종류와 상관없이 같은 자리에서 그린다(읽기 보기를 골랐으면 표 없는 껍데기 — 다시 마운트되면 보내지 않은
    출납을 잃는다). 작업 줄 칸 안 단추 줄은 key `reference_action_row`(`reference_grid.ACTION_ROW`)이고, 기준 창(창 폭
    `ONE_LINE_MIN_WINDOW_PX` 1221 이상 — 고칠 칸 두 자리로 잰 문턱, 사내 보고 창 1283 포함)에서는 표 도구 막대가 그 줄 오른쪽에 함께 서 표 위가 한 줄이다(`ONE_LINE_STYLE` — 2026-11-07
    답 table-top, 설계 규칙 UI-LAY-11). 표지 · 거부 칸이 서면 풀려 단추 → 그 칸 → 막대 → 표 차례로 쌓인다. 편집 표를 고른 회차에는
    그리드 아래에 아무것도 없다(편집 범위는 그리드 상태 줄 글이다)(표 아래 단추에 초점이 가면 본문이 내려가 머리·도구
    막대가 탭 줄 밑으로 숨는다).
  - **편집 표 아홉이 모두 범용 편집 그리드다**(`reference_grid_keys.EDIT_TABLES` — UPEH · 보유대수 · 대여대수 · 가용대수 · 효율 ·
    여유율 · 일수 · Lot·WF측정률). 그 회차에는 고른 표와 inbox 에 op 가 쌓인 표의 양식만 만든다(양식·색인·껍데기는 캐시).
    작업 줄(적용·Excel 붙여넣기·편집 취소·변경 수 — key 는 `f"{editor_key}_apply"` 등 표마다 같은 꼴)을 `reference_actions`
    에 그리고 그리드에 싣는다. 「변경사항 적용」 은 잠그지 않고(`reference_grid.apply_button_key` — 생산 계획과 같은 까닭, 2026-11-19
    보드 m19-e2e-first-apply (가)) 누른 회차에 본다 — 초안이 없으면 아무것도 하지 않고(알림 없음), 칸 오류가 남았으면 고칠 칸 알림으로
    멈추고, 아니면 양식에 초안을 업무 키로 덮어(`merged_template`) `_apply_edit` 길(`to_rows` 업무 규칙 검사 → `apply_month_updates`)을
    탄다. 누름과 함께 온 편집은 출납 콜백이 회차 맨 앞에서 inbox 에 쌓고 본문이 단추보다 먼저 반영하므로(`apply_grid_inbox`) 그
    적용에 든다. 측정률 표가
    통째로 비면 작업 줄 칸에 빈 결과 한 줄(「이 기간에 … 행이 없습니다」 — 1.0 계산은 그 줄의 풍선)을 쓰고 그리드는 빈
    표(머리만)를 싣는다(필터는 서지 않는다). STEP 추가·삭제는
    UPEH·Lot·WF 의 초안·이력을 버리고(팝업이 먼저 경고, 완료 알림에 버린 표) 다른 표 초안은 남긴다.
  - **공정은 사이드바 조회 조건 패널의 공용 공정 칸이다**(`SCREEN` = 「기준 정보」, 2026-11-08 답 P1 — 공정 공유 1차). 편집 표 아홉이 다른 화면의 공정을 따라가고 STEP 구성은 잇지 않는다. 공정 밖 칸(양산 · Area 등)은 「표 조건」 카드(표마다 따로)이고 거를 칸이 공정뿐인 표(일수 · 보유대수 · 대여대수 · 가용대수)에는 카드가 서지 않는다(`GridTable.card_columns`). 거름에 가려 안 보이는 공정의 초안은 작업 줄 아래 「거름 밖 n개」 표지 + 풍선(`reference_grid.outside_count` · `OUTSIDE_NOTICE` — n 은 가려진 공정 수)이고, 「변경사항 적용」 은 그 편집까지 표 전체에 덮는다. 공용 공정으로 좁혀진 표의 여러 줄 붙여넣기 막기는 feed `filters` 가 맡는다. 「Excel 붙여넣기」 는 키 붙은 팝업 호스트 `DIALOG_HOST`(`DialogHost("reference_data_dialog_host", DIALOG_KEY)`)가 불러 여닫아도 페이지를 다시 계산하지 않는다(답 U5) — 호스트는 매 앱 전체 회차에 여는 단추 뒤 · 「변경사항 적용」 앞에 서고, STEP 추가 · 삭제는 같은 열림 칸을 쓰되 페이지가 부른다. 공정 공유를 되돌릴 때 걷을 줄은 `shared_screen=SCREEN` 세 곳과 `reference_grid` 의 `shared_process` 사용 자리다.
  - 적용 검사는 계산이 멈추는 조건과 같게 `reference_consistency.py` 에 두고 페이지는 행만 만든다. 빈칸 뜻은 표마다
    다르고(경로 없음·1.0·0 대·중립값 없음), UPEH 검사는 적용 전 활성 시나리오와 견준다. 격자·붙여넣기는 한 길이다.
  - 편집표와 적용은 같은 적용 기간(선택기간 ∩ 활성 리비전 UPEH 범위)을 쓴다. 필터는 보기만 좁힌다(고른 값은 feed
    `filters` 로 가 브라우저가 거른다 — `reference_grid.filter_codes`).
  - STEP 표·팝업은 「STEP 구성」 을 골랐거나 팝업이 열린 회차에만 만들고 팝업 값은 경로 키다
    (`test_reference_data_perf.py`).
  - UPEH 왕복은 고친 칸만 원본 위에 덮는다 — 원본 표기를 정규화해 저장하면 STEP 목록의 REQB 일치가 끊긴다.
  - UPEH 그리드는 값을 유효숫자 여섯 자리(`GRID_FORMATS` 의 `sig 6`)로 다루고, 월 칸 머리 풍선(`EDITOR_VALUE_HELP` → 규격
    `value_help` → 껍데기 `valueHelp`, `role="tooltip"`)이 Main 행 UPEH · MI 행 ST(분)를 밝힌다 — 0.01분보다 작은 ST 도 잘리지
    않는다.
  - 적용하지 않은 편집이 남은 종류 단추의 주황 점(`tab_marks.mark_pending_segments`)은 원본 토큰으로 편집을 비우고 그리드
    inbox 를 반영한 뒤에 정한다(`reference_grid.draft_pending`).
  - **원본이 바뀐 회차의 그리드 초안**: 기준정보 버전·기간이 바뀌면 아홉 표 초안·이력을 모두 버리고(줄 차례만 바뀌면 남긴다 —
    업무 키 — 머리가 센 초안을 버린 회차는 한 번 다시 돈다, `head_is_stale`), 이 화면 자신의 적용은 그 표만 버린다(`mark_own_change`). **활성 리비전만 바뀐 회차**(다른 화면의 적용 —
    `scenario_edit_bar.only_revision_changed`)에는 초안이 있는 표마다 지금 양식의 내용 지문(`frame_digest`)을 초안을 둔 때의
    지문(`reference_grid_keys.TEMPLATE_DIGESTS_KEY` — 양식 키가 바뀐 회차에만 다시 잰다)과 견줘 같으면 초안·이력을 남기고, 다르거나 지문이
    없으면 그 표만 버리고 작업 줄 칸에 한 번 알린다(`scenario_edit_bar.OTHER_APPLY_DROPPED_NOTICE` — 생산 계획과 같은 글, 2026-11-03 리뷰: 전에는 어느 화면의 적용이든 아홉 표
    초안을 말없이 모두 버렸다). 사이드바 「편집 되돌리기」 는 모든 화면의 편집을 버리므로 그리드 칸(`SESSION_KEYS`)을 따로 지운다
    (`scenario_activation.discard_unsaved_scenario_changes`). 「고칠 칸」 알림은 마크다운이라 분류 값을 칸마다 `literal_markdown`
    으로 막는다. 「Excel 붙여넣기」 도 그리드와 같은 하한·상한·정수 규칙(일수 — `ValueFormat.integer`)을 지난다
    (`reference_csv.assert_edit_value_range(integer=…)`).
  - 설비대수 세 편집표(보유 · 대여 · 가용)도 현황 표 · 다른 편집 탭과 같은 표시순서(`apply_display_order`)로 행을 세운다 —
    공정 이름순이 아니다.
- `app_pages/calculation_result.py` — `산출 결과` 화면. `대당 Capa`·`소요대수`·`확보율` 탭(언패킹 순서 = `TAB_NAMES`)과
  제외 목록을 보인다. 설명은 `guides/calculation_result.md`.
  - 대당 Capa·소요대수 프레임을 풀지 않는다 — 요약은 `get_scenario_result_summary`, 표는 키 전용 캐시에서 그 탭이
    열린 회차에만 꺼내고 오류도 그 탭에만 띄운다(`test_calculation_result_tabs.py`). `STEP별` 은 공정을 골라야 계산한다 —
    고르지 않으면 표 자리에 빈 결과 평문 한 줄(`STEP_VIEW_EMPTY`)만 서고, 고르는 법은 `표시 방식` 풍선 · 공정 필터 자리 글 ·
    Guide, STEP별에서 잠긴 `집계 수준` 은 까닭 풍선이다(설계 규칙 UI-TXT-01 · 04 · UI-INP-07).
  - 표 조건 카드 하나를 세 탭이 쓰고 열린 탭 것만 그린다. 대당 Capa `표시 방식` 은 카드 첫 칸이다(「하위 보기 전환은 본문」 의
    예외 — 2026-11-02 사용자 요청(검수표), 9장). 대당 Capa 탭 본문에는 표만 선다(표 위 그림은 두지 않는다 — 같은 요청).
    측정률 가정(`HM-02` — 줄의 화면 칸과 「그 화면으로」 는 기준 정보(`goto`)이고 어느 화면의 일인지는 전문 첫머리, 표가 하나면 그 종류 단추까지 연다 — 둘 이상이면 기준 정보까지)과 제외(`ST-14`)는 상태 알림이고, `제외 기준정보` 목록(내보내기 프레임 `exclusion_export`)은 ST-14
    알림에 딸린 표다 — Alarm 줄에서 펼치고 CSV 는 브라우저 안에서 만든다(같은 사용자 요청 — 「알림과 제외 기준정보는 우하단
    팝업(통일된 양식)으로 뜨고 누적 알람에서 제외 기준정보를 확인할 수 있게」, 9장 「알림 칸」). 표가 `alerts.TABLE_ROW_LIMIT` 를
    넘으면 본문 `제외 기준정보 확인` 펼침(기억 칸 `unit_capacity_exclusions_expander`)이 남는다.
  - 소요대수 탭은 경로 쪽 제외(`ST-15` · PKG Buffer 밖 `ST-21` · 부하 예외 바탕 없음 `ST-22`)와 계획 쪽(`ST-01` — Static Capa
    와 같은 코드 · 범위)을 상태 알림으로 내고 목록은 그 알림에 딸린 표다(2026-11-05 사용자 요청(검수표) — 「Alarm 안 표로
    이동」) — `ST-15` 「소요대수 제외 기준정보」 · `ST-21` 「PKG Buffer 밖 행」 · `ST-22` 「부하 예외 바탕 없는 경로」(사유로 갈라
    표 행 수가 그 알림 건수다), `ST-01` 「부하량에서 빠진 계획」 · 「경로에 닿지 않은 계획 부하」 둘. 고칠 곳은 까닭 칸
    (`누락 기준정보` · `제외사유`) 머리 풍선(`alert_table(column_help=…)`)이다(설계 규칙
    UI-TXT-01 · 02 · 03). 표가 `alerts.TABLE_ROW_LIMIT` 를 넘으면 그 목록만 표 위 같은 이름 펼침에 남는다
    (`render_oversized_lists`). 알림은 그 탭이 열린 회차에만 낸다. 저장 · 지정 · 복제 · 자동 갱신 경고의 목록 안내
    (`REQUIRED_LIST_NOTE`)와 「그 화면으로」(`REQUIRED_TAB_GOTO`)는 이 탭(조회기간)이 아니라 같은 리비전 · 전체 기간인 시나리오 관리 ›
    목록 관리 「점검」 칸이다(2026-11-11 입력 점검 검토 보드 F4 (나)).
  - 대당 Capa · 소요대수 표 제목 줄에 CSV 와 「시트 엑셀」(시트 엑셀 넓히기 1 — 공정 Capa
    상세 선례, TODO 3장 「계산 결과 Excel 다운로드 — 닫음」)을 묶은 「내려받기 ▾」 메뉴 하나가 선다(`table_toolbar.render_download_pair` — 2026-11-10 답 Q2-7). 지금 화면 상태(보기 · 집계 수준 · 공용 공정 거름 · 상세 ·
    `표 조건` 거름 · 조회기간 달 · 공정 표시명 — CSV 는 원본 이름)의 표를 화면 서식째
    (`components/monthly_table_workbook.py`) 낸다. 파일 이름은 같은 메뉴의 CSV 와 같고 확장자만 `.xlsx`, 맨 위 머리 값 줄은 시나리오 ·
    조회기간(`sheet_download.scenario_period_rows`) · 보기 · 거름이다. 통은 조건 키(대당 Capa — 시나리오 캐시 키 · 표시순서
    지문 · 보기 · 수준 · 공정, 소요대수 — CSV 키의 표 지문, 둘 다 표시명 판 · 머리 값 · 시트 꼴 판)로 세션 칸
    `calculation_result_sheet_memo` 에 몇 벌 기억한다(`sheet_download.remembered_bytes` — 새 `st.cache_*` 없음). 소요대수
    상세 「표시 범위」 는 화면만 나누고 시트는 CSV 처럼 거른 행 전부다(`tests/test_calculation_result_sheet.py`).
  - **탭 전환 · 표 조건 회차는 CSV · 제외 목록 알림 표를 다시 짓지 않는다.** 대당 Capa · 확보율 내려받기 CSV 는 같은
    `remembered_bytes`(콜러블 아님 — 9장 「편집표와 내려받기」)로 시트와 따로 된 세션 칸 `calculation_result_csv_memo`
    (`CSV_MEMO_KEY` — 시트 칸과 나누면 CSV 가 시트 통을 밀어낸다)에 기억한다. 키는 표를 정하는 것 전부다 — 대당 Capa (탭, 결과 키,
    표시순서 지문, 보기, 수준, 고른 공정), 확보율 (탭, 결과 키, 지문, 공용 공정 거름 뒤 남은 공정 차례). 파일 이름(고침 꼬리)은
    키 밖이다. 제외 목록 알림 표(소요대수 `ST-15` · `ST-21` · `ST-22` · 대당 Capa `ST-14`)는 `required_exclusion_notice.remembered_alert_table` 이 결과
    키 · 지문을 받아 기억하고(`memo=`), 알림을 내는 일(`alerts.state`)은 회차마다 한다. 접힌 「히트맵」 상자 안 그림은 그대로
    짓는다 — 상자 여닫기가 빈 구역 회차라 본문이 돌지 않아, 펼 때만 지으려면 펼침이 앱 회차를 불러야 한다(`docs/TODO.md` 2장
    「성능」 C3 결정 거리).
  - 조회기간에 소요기준 BOX · PCB 경로가 있는 공정(계산 밖 — 11장)이 있으면 세 표 제목 줄(대당 Capa 공정별 · STEP별 · 소요대수 ·
    확보율)의 부가 설명 칸에 「계산 밖 n공정」 표지가 서고 까닭 · 공정 표시명 · 빠진 소요기준은 그 풍선(`caption_help`)이다
    (`components/outside_calculation_mark.py` — 2026-11-24 사용자 「권장안 그대로」, 설계 규칙 UI-TXT-04). 경고 알림이 아니다 —
    고칠 수 없는데 늘 서는 상태다(UI-NTF-05). 목록은 `simulation_cache.get_unimplemented_basis_processes`(선언을 접지 않은 내용
    토큰 + 계산과 같은 유효 조회기간) 한 번이고 풍선 차례는 공정 칸 선택지와 같은 표시순서다. n 은 공용 공정 거름과 상관없이
    조회기간 전체의 수라 세 탭이 같고, 없으면 그리지 않는다(UI-TXT-08). 「STEP별로 그릴 공정이 없습니다」 빈 결과 · CSV · 시트
    머리 값에는 싣지 않는다(`tests/test_calculation_result_tabs.py`).
- `app_pages/process_capa_detail.py` — `공정 Capa 상세`(실행 관리 첫 화면). 정체성은 **어느 화면에서든 공정 하나를 눌러
  바로 깊게 보는 목적지**다(Guide 첫 단락, 2026-10-22). 공정 하나의 산출 근거 → 부족한 달 → 그 달을 메우는 설비 일정을 잇는다.
  본문 프래그먼트는 `process_capa_view.py`, 설명은 `guides/process_capa_detail.md`.
  - 공정·달은 상자보다 먼저 정한다(HOME 전달 → 주소 → 세션 → 최저 확보율 공정의 첫 미달 달). 공정 상자로 바꾼 회차는 ◀▶ 처럼
    그 공정의 첫 미달 달(`anchor[0] != process`), 미달이 없으면 보던 달이다(2026-11-07 g4-26 — 설계 규칙 UI-STA-03 예외). 확보율은
    키 전용 캐시다.
  - 설비 DB 는 읽기만 하고 필요 단축 일정의 공용 조회 조건·기준선·세션 칸은 읽지 않는다(5장 9). 판정을 통과한 공정만
    계획·설비 일정을 받고, 아니면 데이터 Error 마크 한 칸(채울 입력이 빠짐) 또는 회색 평문 한 줄(HBM·EDP 호기 없음 빈 상태)이다.
  - 사용기준이 HBM·EDP 가 아니어서 이 공정의 가용 · 단축 후보에서 뺀 호기는 자리 표지 없이 상태 알림 `PD-04` 로만 낸다(`report_usage_excluded`). 범위는 이 화면의 설비 기준 · 공정이고, 내용은 설비명 목록이며, 짧은 글은 「사용기준 제외 n대 — <공정> 가용 · 단축 후보에서 뺌」 이다. 설비 일정을 세우지 못한 회차에도 해소로 부른다.
  - 설비는 **방문 기준**이다 — HOME 칸으로 들어온 방문은 ◀▶ 뒤에도 그 방문 동안 공식 설비 시나리오(사이드바 줄은 잠근
    꼴, 출처 띠 끝 「설비는 공식 vN 기준」), 그 밖의 길은 세션 설비 시나리오다(`process_detail_state`). 설비 시나리오는 공정·
    달을 정한 바로 뒤에 읽는다 — 출처 띠를 자리(`st.empty`)에 다시 쓰지 않게(9장 placeholder 시험). 설비 DB 가 코드보다
    새면 상태 알림(`render_schema_ahead_warning` — `GL-06`), 옛 배포 흔적이면 흔적 알림(`SB-19`)을 낸다(자리에는 그리지
    않는다 — 9장 「알림 칸」). 팝업은 「불러오기」 만이다.
  - 필요 단축 일정 카드에서 왔으면(`from=shortening`) **주소 인자만** 읽어 그 카드의 목표·기간·단축/신규 대수로 출처
    띠(대수가 다를 수 있다는 말은 띠의 풍선 `SHORTENING_BAND_HELP` — 자리 글이 아니다)와 「← 필요 단축 일정」 을 낸다. 필요 단축
    일정으로 옮기는 단추는 모두 그 화면의 「강조 공정」 칸만 적는다 — 공정 필터(0019 세션 칸)는 심지 않는다.
  - HOME 표시 확보율 줄은 HOME 과 같은 함수(`home_display_rates`)·같은 캐시 키로 낸다. 「구획」·「제품별 소요대수」·
    「분류」는 「상세는 카드」의 예외로 본문 표 도구 줄이다. 출처 띠는 캡션 한 줄이다(`docs/design_system.md` 2-3).
  - 밖에서 들어온 회차는 그 길(`from`)의 구획을 다시 편다(HOME → ①, `gap` → ⑤, `shortening` → ④). 머리 ◀▶ 는 미달
    공정을 최저 확보율 차례로 넘기고(세션 값, 공정별 요약은 세션 칸에 한 벌 — 단추 라벨은 접근 이름 「다음 미달 공정: …」
    이고 화면에서는 그 글을 sr-only 로 숨긴 채 기호를 `::before` 생성 글로 그린다), 근거 패널은 고른 달의 부족 원인마다
    다음 화면(보유 → 투자 검토 대상·산출 결과, 불일치 → 가용설비 현황, 일정 → 필요 단축 일정)을 단다 — KPI 아래 같은 줄은
    2026-11-10 보드 c2-picked 로 걷었다(원인별 달 수는 KPI 「부족 원인」).
  - 표 도구 줄 오른쪽 끝 「내려받기 ▾」 메뉴(2026-11-10 답 Q2-7 — 호기 CSV · 「시트 엑셀」, 호기 CSV 가 없으면 메뉴 없이 시트
    엑셀 단추 하나)의 「시트 엑셀」(늘 — 2026-11-10 보드 c2-picked)은 지금 화면 상태 그대로의 결합 캔버스를 화면 서식째
    xlsx 로 낸다(`components/process_capa_workbook.py` · `io/xlsx_small.py` — 새 의존성 없음). 페이지는 머리 값 줄(공정 ·
    시나리오 · 조회기간 · 설비 시나리오 · 설비 일정 · UPEH 가정 — `sheet_heading`)과 호기 CSV 표(`units_export`)를 넘긴다.
    두 파일 이름(`process_capa_view.detail_file_names`)은 `process_capa_detail[_units]_<첫 달>_<끝 달>` 뒤 UPEH 가정 꼬리
    (`_upeh<%>_<구간 첫 달>_<끝 달>`, 켰을 때만), 끝에 화면의 공정 이름(공정 값 칸 · 고르기 판과 같은 글자 — 표시명이고, 이
    화면 선택지에서 원본이 다른 공정과 표시명이 겹치면 「표시명 (원본)」(`ProcessLabels.unique_format_func` — 2026-11-11 다음
    배포 물음 보드 B3 뒤 (나) · 2차 보드 Q2-18), 못 쓰는 글자 · 빈칸은 `table_toolbar.file_name_part` 가 `_` 로)이다(2026-11-11
    남은 물음 보드 B3 (가) — 공정이 달라도 이름이 같던 것). 머리 · 시트 머리 값 줄의 공정은 표시명 그대로다.
  - UPEH 가정(조건 카드 끝 「이 세션만」)이 켜지면 가정 요약(이미 받은 확보율 행에 ÷f — 캐시 밖)과 가정 계획(계획 키 끝
    칸 토큰 → 가정 칸)을 더 세운다. **판정은 한 기준**이다 — 부족 띠·KPI·원인과 ② · ③ 의 소요는 가정, 가정 전 값은
    ① Static 줄과 KPI 회색 줄 「가정 전 n」 에만(이름은 2026-11-12 사용자 답 q2 (가) — Core Data 숫자는 「Static」, 가정과
    견주는 값은 「가정 전」, 발행본 이름은 그대로). 머리 배지·효과 한 줄(그 화면의 목표·기간)·카드의 역산 둘(「이
    값으로」)·호기 CSV 표지가 선다. 기본 공정·달·◀▶·HOME 표시 확보율은 Static 이다.
  - 진입(판정 기준·공통 진입·유효 기간·시나리오 키·확보율·공정 선택지)은 `page_bootstrap.process_page_inputs` 로 제약
    시뮬레이션과 나눈다 — 두 화면이 같은 계획 칸을 같은 키로 받는다. 머리 ◀▶ 뒤 「이 공정 제약 시뮬레이션」
    (`st.page_link` + 주소 `?process=`)은 늘 보이고 설비 일정이 서지 않는 공정이면 꺼진 채 풍선이 까닭을 말한다(D11).
    HOME 칸 방문(공식 잠금)이고 세션이 공식 발행 쌍이 아니면 링크 판정만 세션 스냅샷으로 한 번 더 낸다(제약
    시뮬레이션은 늘 세션 설비 시나리오다 — 캐시된 스냅샷의 거르기뿐).
  - 고른 공정의 경로가 조회기간 안에서 모두 소요기준 BOX · PCB(계산 밖 — 11장)면 `ProcessDetailView.outside_basis` 에 그
    소요기준(「BOX」 · 「BOX · PCB」)을 실어 ③ 판정 카드가 「소요 없음」 대신 「계산 밖(소요기준 BOX) — 판정하지 않습니다」 를
    쓴다(2026-11-24 사용자 「권장안 그대로」). 목록은 산출 결과 표 제목 줄 표지와 같은 칸(`get_unimplemented_basis_processes` —
    선언을 접지 않은 내용 토큰 + 유효 조회기간)이고 공정 하나 고르기는 `outside_calculation_mark.whole_outside_basis`(`whole` 공정만 —
    경로 일부만 빠진 공정은 남은 경로로 판정이 서서 None)다. 경고 알림이 아니고 숫자 · 그림 · 시트는 그대로다
    (`tests/test_process_capa_detail_page.py`).
- `app_pages/capa_chatbot.py` — 활성 시나리오 Capa 를 근거로 답하는 대화 화면의 답 모양(결론·근거 표·조건과 산식·한계)을
  대본으로 보여 준다. 설명은 `guides/capa_chatbot.md` 다 — 답의 네 칸(2026-11-10 보드 Q-9)과 「연결 방식」(오른쪽 카드는 제목과
  목록만 — 2차 보드 Q2-24)도 거기서 말한다. 머리에 배지 줄이 없고 「샘플 데이터」 는 조회 조건 패널 줄이다 — 공통
  줄을 읽지 않는 화면이라 이 줄이 패널을 세운다(9장 「사이드바·조건 카드·본문」, 2026-11-09 보드 T8).
  - 대본은 `chatbot_samples.py` 한 곳이고 LLM 을 붙일 때 바꾸는 자리도 거기 하나다. 공정 표시명 프로필 버전마다 세션에
    한 번 만든다 — 결론·질문·조건의 공정 이름은 대본이 페이지가 넘긴 `ProcessLabels.label` 로 적고(조사도 그 글자로
    고른다), 근거 표는 화면 복사본에 표시명을 입힌다(8장 ④). 대화 기록은 답 이름(`SampleAnswer.key`)이다 — 질문
    글자는 표시명을 따라 바뀐다.
  - 추천 질문·`대화 비우기` 는 `on_click` 콜백이다. LLM API·권한·대화 이력은 연결하지 않는다. 「추천 질문」 카드는 머리와
    단추뿐이고 단추 차례의 뜻 · 누르면 어떻게 되는지는 Guide 「추천 질문」 단락이다(2026-11-21 확인 보드 q-chatbot a —
    규칙집 6-39 횡전개 2 ④).
- `app_pages/static_capa.py` — `Static Capa` 머리. 확보·경고 기준별 월간 설비 부족대수와 추가 필요대수(산식 6장)를 보인다.
  - 하위 화면은 사이드바로만 간다. 판정 기준은 HOME Preference 공용 프로필이고 카드는 읽기 전용이며, 판정 적용은
    캐시하지 않고 매 회차 한다. 부서별 활용과 계산식 설명은 `guides/static_capa.md` 다. 두 부족 표의 내려받기는 표 도구 막대 한
    곳이고(별도 CSV 단추 없음) 파일은 공정 원본 · `확보율` 원값이다. 공정 칸은 읽기 전용 `SelectboxColumn`(값 원본 · 글자 표시명 — 8장 ④ 끝)이다.
    `ProgressColumn` 은 값을 `max_value` 로 잘라 파일로 내보내므로(Streamlit 1.63, 글자는 원값) 막대 끝은 `max(기본 확보 기준, 그 표의 확보율 최댓값)` 이다 — 표
    안의 거리를 보이는 눈금이라 표마다 다를 수 있고, 판정 · 필요대수 · 막대 색(구획마다 한 색)은 여기에 기대지 않는다.
  - 확보율은 키 전용 캐시로 꺼내고 오류는 `check_scenario_capacity` 로 「계산 멈춤」과 검증 오류를 가른다.
  - 소요대수에 들지 않은 수요(계획 쪽 · 조회기간)는 두 상자 위에 그리지 않고 상태 알림 `ST-01` 로 낸다(산출 결과 소요대수
    탭과 같은 코드 · 범위). 화면을 그리지 못한 오류는 자리 「데이터 Error」 마크 + `ST-20`(`data_error_mark.render_data_error`).
- `app_pages/execution_management.py` — `실행 관리` 머리. 세 영역 비교·하위 화면 목차를 데이터를 읽지 않고 그린다(정의·업무 활용
  목적·부서별 Gap · A/Item·로드맵은 본문 머리가 아니라 Guide 첫 단락 — 2026-11-09 사용자 규칙 「상단 여백 · 문구 최소화」).
  - `PageSpec` 이 시나리오·조회기간을 읽지 않고 조건 카드·설비 DB 핀이 없다. 목차 카드는 화면 이름 링크 하나이고 화면마다
    보는 것은 카드 밑 회색 줄이 아니라 Guide 「이 영역의 화면」 이다(설계 규칙 UI-TXT-01 · 02 — 규칙집 6-39) — 하위 화면이
    늘면 그 목록에 사이드바 차례대로 `- **이름**` 한 줄을 더한다(실적 셋은 묶음 줄 하나 — 빠지면
    `test_execution_management_page.py::test_every_subpage_has_its_own_line_in_the_guide_screen_list` 가 깨진다). 설명은
    `guides/execution_management.md`.
  - 이행 현황판 숫자는 다음 판이다. 넣을 때는 `PageSpec` 의 `reads_*`·`uses_equipment_db` 와 `test_app_navigation.py` 의
    설비 DB 단언부터 본다.
  - 운영 서버의 개발자가 아닌 회차(`sso_identity.unfinished_hidden` — 사이드바에서 구현 중 화면을 빼는 판정과 같은 하나를 한 번
    부른다)에는 맨 아래 이행 현황판 점선 자리를 그리지 않고, 목차에서 구현 중 화면(`PageSpec.unfinished` — 실적 셋) 카드를 빼
    다섯이다. 세 영역의 Dynamic Capa 는 카드를 걷지 않고 이름 · 풍선만 남긴다(「열기」 없음 — UI-INP-07 예외 「값만」). 선언
    `EXECUTION_MANAGEMENT_SUBPAGES` 는 그대로다 — Guide 목록 대조가 선언 전체를 본다. Guide 는 보는 사람마다 다를 수 없어 자리를
    가리키지 않고 실적 셋 · Dynamic 이 운영 서버에서는 개발자에게만 보인다고 적는다(2026-11-24 정식판 마감 2-A — 시험
    `test_execution_management_page.py` · `test_grade_ui_core.py`).
- `app_pages/production_progress.py` — `생산 진도` 머리(실행 관리와 Dynamic Capa 사이 그룹, 2026-11-02 사용자 요청). 보일 내용은
  모듈이 맡아(2026-11-03 사용자) 머리말(배지 줄 없음 — 2026-11-09 보드 T8) 아래에 모듈 화면이 들어올 넓은 점선 자리(높이 max(360px, 100vh − 270px) — 아래 끝을 지킨다)(제목 「모듈 화면 자리」 · 표지
  「모듈 연결 대기」 — `st.html` 하나, 색은 그 회차 테마 토큰) 하나만 그린다(데이터를 읽지 않음 — `PageSpec` 이 시나리오·조회기간을
  읽지 않아 공통 조건 줄도 조건 카드도 없다). 그리는 것은 `components/module_slot.py` 의 `render_module_slot_page` 한 벌이고 이 파일은
  제 이름 한 줄만 넘긴다. 모듈이 이 자리에 그리는 길(`module_api` · `module.json` 선언 · 모듈 규칙 · 지침서)은 아직 없다 —
  `docs/TODO.md` 2장 「생산 진도 화면 내용」. 그래서 자리 표지는 약속 문장이 아니라 원천 미연결 화면과 같은 「… 연결 대기」
  꼴이다(UI-LAY-10 · UI-CON-03, 2026-11-24 정식판 마감 2-A). 하위 샘플 셋이 있어 사이드바 상자는 다른 계산 그룹처럼 펼침 상자이고 이 화면은 그 안
  「현황 요약」 이다. 시험은 `tests/test_production_progress_page.py`.
- `app_pages/production_sample_1.py` · `production_sample_2.py` · `production_sample_3.py` — 생산 진도 하위 「샘플 페이지 1 · 2 · 3」
  (2026-11-04 검수 의견 prog-01 「생산진도 상자 내에 샘플 페이지 1,2,3 넣고 펼치는 상자로 반영」 · prog-02 「샘플페이지 1,2,3 화면에
  이대로 임시 반영」). **임시**다 — 머리 화면과 이름만 다른 같은 꼴(`render_module_slot_page("샘플 페이지 n")` 한 줄)이고 데이터를
  읽지 않는다(`navigation.PRODUCTION_PROGRESS_SUBPAGES` — 공통 조건 줄 · 조건 카드 · 설비 DB 핀 없음). 모듈이 그 자리에 그리는 길이
  생기면 바꾼다(`docs/TODO.md` 2장 「생산 진도 화면 내용」). 시험은 머리와 같은 `tests/test_production_progress_page.py`.
- `app_pages/reference_integrity.py` — `Dynamic Capa` 머리(주소 `dynamic_capa`). 실행 관리가 모은 실적으로 표준 Capa 의
  실현 Capa·손실을 다시 내는 데모 프로토타입이다(요약·공정 상세·산식 가이드 탭).
  - 손실 목차가 효율 → UPEH → 수율 실적 → 재공 현황 → 가용설비 현황을 `page_link.py` 로 잇는다. 카드는 손실 이름 · 「열기」
    뿐이고 워터폴의 자리(「표준 → 효율 반영」 등)는 Guide 「손실을 파고드는 화면」 표다(규칙집 6-39).
  - 데모는 샘플 스위치(조회 조건 패널 줄 — 공통 줄을 읽지 않아 이 줄이 패널을 세운다)로 끄고 세션에 한 번만 만든다(실DB 를
    붙이면 그 칸 키에 원천 적재 시각을 넣는다). 머리에 배지 줄이 없다(2026-11-09 보드 T8).
  - 부서별 Gap·A/Item 로드맵은 실행 관리 Guide 첫 단락이다(`guides/execution_management.md`) — 맨 위 「실행 관리」 되돌아가기
    링크는 두지 않는다(화면 탭 줄 · 사이드바가 같은 길, 2026-11-09 보드 T4).
  - 판정 기준 · 그림 읽는 법 · 손실 차례 · 결론(실현률이 가장 낮은 공정)은 늘 서는 캡션이 아니라 「개선 필요」 칸과 구획 제목의
    풍선이다(설계 규칙 UI-TXT-01 · 02 · 04 — 화면 소개는 `guides/reference_integrity.md`). 공정별 수량 단위의 뜻은 공정 상세
    「표준 Capa」 칸 풍선(`STANDARD_CAPA_HELP`)이다. 재공 현황의 격자 읽는 법도 같다(소개는 `guides/wip_status.md`).
  - 세 탭은 `stateful_tabs` 다. 닫힌 탭의 그림과 정적 산식 가이드는 그리지 않는다. 공정 상세의 조회 조건(조회일 · 공정 · 제품 ·
    Stack · WF 속성)은 사이드바 「Dynamic Capa 조건」 카드이고 그 탭이 열린 회차에만 선다(위젯은 `persist_state` — 탭을
    오가도 값이 남는다, 2026-11-09 보드 T8). 카드는 처음 펼친 채다(2026-11-10 보드 Q-7).
- `app_pages/required_shortening.py` — `필요 단축 일정`(실행 관리 둘째 화면). 정체성은 **단축이 필요한 공정 전부의 진척
  관리 한 페이지**다(머리말, 2026-10-22). 설비 저장본·Cut-off·소요대수를 모아 `required_shortening_panel.py` 에 넘긴다.
  계산 규칙은 `services/required_shortening.py` 다.
  - 사이드바 팝업 상자 「Qual 마감 계산기」(`render_settings_box` 꼴 — 상자 = 단추 → 같은 제목 팝업, 상자 key
    `sidebar_dialog_box_qual_calculator`, 단추 key 는 옮기기 전 그대로 `required_shortening_qual_calculator_v1`)가 큰 팝업을
    연다(2026-10-24 — 가용설비 현황의 탭이던 것, 2026-11-09 사용자 검수 g03-1 로 머리 끝 단추에서 조회 조건 패널 밑 · 조건 카드
    위로 — 설정이 아니라 도구지만 팝업을 여는 사이드바 상자 꼴은 하나다). 상자는 데이터를 읽기 전에 서 멈춘 회차에도 같은 자리다. 팝업은 화면 팝업 호스트(`DialogHost("required_shortening_dialog_host", required_shortening_open_dialog)` — 값
    `qual_calculator`, 답 U5)가 열고 닫는다 — 여닫아도 페이지를 다시 계산하지 않고, 닫기는 붙여넣기 글 칸 초안만 지운다(계산기
    입력은 남는다). 호스트는 머리 바로 뒤·데이터를 읽기 전이라 호기가 없어 화면이 `st.stop()` 해도 열리고,
    이벤트 칸에 늘 한 자리(열렸으면 팝업, 아니면 빈 스타일)를 쓴다 — 계산기 본문은 이벤트 칸에 쓰지 않는다
    (`qual_deadline_calculator.calculator_style_markup`). 그 뒤 기준선 결과 알림 표지 자리(머리 · 본문 프래그먼트 안)가 팝업을
    여닫을 때 밀리지 않는다(`test_qual_deadline_calculator.py` 가 연 회차·닫은 회차의 이벤트 칸 자리 수를 견준다).
  - **누적 진척**(2026-11-20 보드 답 누적-1 A · 누적-2 c 손으로 적기 · 누적-3 a · 누적-4 「한 줄 기록」 · 누적-5 a — 규칙집 6-37):
    본문 맨 위 한 줄 띠와 사이드바 「누적 진척 설정」 상자(Qual 마감 계산기 상자 밑 · 조건 카드 위) → 같은 제목 팝업이다
    (`components/shortening_cumulative.py` — 페이지는 `CumulativeProgress(host=DIALOG_HOST, …)` 하나를 세워 상자 · 호스트 팝업 · 띠를 부르는
    줄만 둔다). 띠는 진척 비교와 상관없이 KPI(또는 진척 요약) 위에 서고 호기가 없거나 계획이 멈춘 회차에도 선다 — 값은 적은 기록
    기준이라 계획을 읽지 않는다. 「이번 주 값 넣기」 가 읽는 지금 화면 합계는 패널 `_render_body` 가 회차마다 적는다(`remember_screen_total` — 계산은
    `services/shortening_progress_log.screen_shortening_days` 하나, `_render_view` 머리에서 지우고 다시 적어 멈춘 회차에 앞 값이 남지
    않는다). 합계는 현재 일정 기준 전환이 고른 계획(`plan.basis` — 풍선에 그 기준)이고, 진척 비교가 기준선과 같은 다른 기준의
    계획(`_Plan.plan_for`)을 그려도 바뀌지 않고, 진척 비교가 「필요 시점 지남」 · 「기준 바뀜」 을 합계에서 빼도 그대로다(어느 기준선과도
    상관없다 — 시험이 맞댄다). 기록 · 목표는 설비 DB `0036` 공용 현행값이다(넣기 스냅숏은 `0037` — 아래).
    - **「주차별」 오르내림 까닭**(2026-11-20 · 21 보드 답 q-look (a) → 2차 q2-look 중간-1 「점 곁 곧은 꼬리표」 · q-source (a)
      「자동 + 사람이 고침」 의 1단계 자동 · q-axis (a) 목표 아래부터 — 규칙집 6-43): 「이번 주 값 넣기」 로 저장한 주는 그 화면의
      호기 표 스냅숏(고른 목표 · 범위 공정의 당긴 호기 · 추가N, 범위 공정 · Cut-off · 기준 · 오늘 · 달 · 출처)이 기록 줄과 같은 쓰기
      트랜잭션에 남는다(설비 DB `0037` — 기록 지우기가 함께 지움, 손으로 적은 주는 없음). 값은 여전히 사람이 적은 수이고 선은 기록
      수만 잇는다(누적-4 「한 줄 기록」 을 넓힘 — 규칙집 7-1). 「주차별」 을 편 회차에만 스냅숏을 읽어 바로 앞 기록 주와 진척 비교
      짝짓기로 견줘 까닭을 센다 — 저장하지 않는다(`services/shortening_progress_reasons.explain_week_changes`). 띠 프래그먼트는
      페이지 전체 회차에도 다시 돌아 센 까닭은 캐시 경계 `equipment_cache.load_shortening_progress_reasons`(기록 · 스냅숏과 같은 쓰기
      세대 · DB stat — 맞으면 스냅숏 표도 읽지 않음)에 담고, 그리는 쪽이 까닭의 앞 주 · 증감을 그리는 기록과 다시 맞춘다
      (`_matching_reason`). 두 주 모두 스냅숏이 있고 항목 합 = 지난 기록 대비가 맞는
      주만 근거가 있고, 그런 주가 5일 이상 오르내렸으면 점 곁 꼬리표(`components/shortening_cumulative_tags.py`) · 큰 ▲ · ▼ ·
      오른 주만 들어오는 구간 굵은 주황 선이다. 근거 없는 주는 늘어난 주 ▲ 와 「+n일」 · 줄어든 주 ● 다. 점 · 꼬리표를 가리키면 그 주 까닭
      전부(여섯 넘으면 앞 다섯 + 「그 밖 k건」) · 합 「합 −n일 = 지난 기록 대비 −n일」 · 덧말(n주 사이 · 추가 호기 대수 · 호기 이름이
      바뀌었을 수 있는 공정 · 입력 바뀜 — 조회 달 · Cut-off · 리비전)이 풍선이다(Plotly `hovertext` — 풍선 1초 지연은 앱 전체 풍선 규칙이 맡는다). 세로축은
      목표 아래부터(0 아님), 목표 이름은 선 아래 오른쪽, 끝 값 글은 점 오른쪽 위다. 꼬리표 글(그림 위 항목)은 사용자가 고른 그림
      글이라 UI-TXT-04 예외다. 사람이 까닭을 고치는 칸(2단계)은 아직 없다(`docs/TODO.md` 2장 열린 줄). 스냅숏을 못 읽으면 까닭 없이
      그린다(`BOOTSTRAP_ERRORS`).
  - **머리 · 조건 카드**(2026-11-08 그림 메모 g03): 머리 소개 줄은 없고 정체성은 Guide 첫 단락이다. 목표 확보율은 사이드바 조회
    조건 패널 줄(값 칸 + 팝업 — Space 「필요 단축」 보기와 같은 부품 `components/target_level_field.py`, 2차 보드 Q2-26)이고 페이지가
    팝업 호스트 바로 뒤 · 데이터를 읽기 전에 세워(`required_shortening_panel.LEVEL_FIELD.render`) 멈춘 회차에도 서고 고를 수 있다(호기가
    없는 회차는 같은 자리, 설비 DB 를 못 읽은 회차는 그 앞 「설비 시나리오」 줄이 서지 않아 한 줄만큼 위) — 값 칸을
    누르면 같은 화면 팝업 호스트(`SHORTENING_DIALOG_HOST`)만 돌아 다섯 목표 라디오와 그 밑 직접 입력 칸(2026-11-11 사용자 고칠 것
    Q2-26 — 50 ~ 300% 정수 %, − · + 단추와 지우기 ⊗ 는 숨기고 Enter · 칸 떠남으로만 적용 — 남은 물음 보드 Q226-stepper (나))이
    열리고, 고르거나 넣으면 세션 칸(`SHORTENING_LEVEL_KEY` — 위젯 key 가 아니다)에 적고 닫히며 앱
    전체를 한 번 다시 돌린다(값 칸 글이 프래그먼트 밖이라 본문만 다시 돌리지 않는다). 다섯 밖 값은 `_prepare` 가 그 값 하나를 더
    계산해 계획에 더하고(`load_official_shortening(level=)`), 그 목표로 진척 비교를 고르면 견주지 않고 빈 결과 한 줄이다(기준선은
    다섯만 얼린다 — `_render_missing_baseline_level`). 진척 비교는
    사이드바 「필요 단축 일정 조건」 카드 맨 위 칸이고(카드는 처음 펼친 채 — 한 번 접으면 기억 칸), 바꾸면
    본문 프래그먼트(`VIEW_FRAGMENT_KEY` · `_rerun_view`)만 다시 그린다. 본문 프래그먼트는 회차마다 목표 세션 칸을 읽고, 기준선 목록이 카드가 세운 id 들
    (`_Plan.shown_baselines` · `_view_choices`)과 다르면 앱 전체 회차로 올린다(UI-DAT-11). 보던 기준선이 다른 곳(다른 사용자 · 다른
    탭)에서 지워져 「비교 안 함」 으로 돌아가는 회차에는 사건 알림 `RS-06`(알림 단계 — 짧은 글 「보던 기준선 「…」이 지워져 진척
    비교를 껐습니다」)을 한 번 내고 화면 자리에는 글을 달지 않는다(남은 물음 보드 D4 (나) — `shortening_progress_panel.render_compare_select`). 일정 미정 · 사용기준 밖 · 입력 비가동
    반영은 자리에 표지를 세우지 않고 상태 알림 `RS-03` ~ `RS-05`(`_report_status_alerts`)만이다 — 짧은 글이 건수, 전문이 뜻 ·
    내역이다(2026-11-09 사용자 규칙 「상단 여백 · 문구 최소화」, 설계 규칙 UI-NTF-02 · UI-TXT-07). 본문 맨 위는 KPI 이고 기준 값
    「설비 일정 기준 가용(환산) · 오늘」 은 따로 줄을 세우지 않고 CSV 작업 줄 오른쪽 끝 작은 글이다(`_render_basis` — 값 글
    `profile_caption.render_row_value` 의 `"push"`, 2026-11-09 사용자 보드 T2). CSV 줄이 서지 않는 회차(멈춤 마크 · 빈 상태 글)에는 그 줄 오른쪽 끝이고, 자리가 모자라면 글이 통째로 다음
    줄 오른쪽 끝으로 내려간다(서식은 그 캡션 마크다운 안 — 프래그먼트 이벤트 칸을 쓰지 않는다).
  - KPI 아래·카드 위에 공정 진척 보드·기한 임박·이행 지연(`components/shortening_board.py` — 처음 접힌 기억 상자, 편 상태는
    기억한다, 그림 메모 g03 ④)이 서고 카드마다 「공정 Capa
    상세에서 근거 보기」 와 그 옆 「도면에서 보기」(Space 현황 필요 단축 보기 — 그 공정의 층·같은 목표, 층은 본문이 공정 전부를
    한 번에 고른다 `shortening_space_floors`, 비활성 층 뺌 — 그래서 페이지가 층 사용 상태 `load_floor_states` 를 읽는다)다(주소
    인자, 샘플 fleet 이면 둘 다 숨김). 수요·달·계획 꺼내기는 Space 보기와 같은 `components/shortening_source.py` 다. 카드 차례·기한 임박 날수·강조 공정은 세션 값이고 DB 에 쓰지
    않는다.
  - 저장본·미저장 편집은 `equipment_data_workspace.py` 세션 칸(가용설비·Space 와 같은 토큰)에서, Cut-off 는 저장된
    값만 읽는다(고치는 곳은 가용설비 현황 사이드바 「가용설비 설정」 팝업). 조건 카드는 `shortening` 이다.
  - 소요대수 프레임은 넘기지 않고 시나리오 키와 로더를 넘긴다. 계산은 DB 에 쓰지 않고 패널이 공용 조회 조건(`0019`)과
    진척 비교 기준선(`0021`)만 쓴다. 기준선 저장 · 지우기 결과는 알림창 · Alarm 한 꼴이다(`flash.queue_flash` · `render_flash`
    — 이벤트 칸 한 자리, 성공은 알림창으로만, 거절 · 실패는 `popup_only` — 알림 칸이 머리 밑이라 단추 곁이 아니다, 칸 셋에 빈
    칸부터 담아 앞 알림을 덮지 않는다 — `test_shortening_baseline_notice.py`).
  - UPEH 가정은 이 화면에 걸지 않는다 — 조건 카드에 공정 Capa 상세와 같은 세션 칸을 그릴 뿐 가정 계획을 세우지 않고,
    공식 대 가정 비교 보기도 없다(효과는 공정 Capa 상세). 가정이 켜졌음은 머리 변경 칩이 알리고(자리에 적지 않는다 —
    2026-11-04 설계 규칙 UI-TXT-01), 그동안 기준선 저장은 거절한다. 보기·CSV·진척 비교는 늘 공식 계획이다(Guide 가 말한다).
  - 설비는 **세션 설비 시나리오**다(`resolve_equipment_session`). 기준선 저장은 세션이 공식 발행 쌍일 때만이고(거부 까닭은
    「가정 설비 시나리오」·「발행하지 않은 리비전」 둘), 기준선에는 공통 rN + 설비 시나리오·rN·공식 vN 출처가 실린다. 진척
    비교는 늘 보이고, 세션이 공식 발행 쌍이 아니면 머리에 「지금 = 셋업 실무 r4 · 기준선 = 공식」 을 적는다. 카드 링크는
    표시용 `eq`(그 카드가 본 설비 시나리오)를 싣는다.
- `app_pages/constraint_simulation.py` — `제약 시뮬레이션`(실행 관리 셋째 화면, 2026-10-24 사용자 결정). 정체성은 **공정
  하나에 미래 제약(제약 제품 전용 설비)이 생기면 제약 제품에 먼저 떼어 준 뒤 기존 제품 확보율이 언제부터 얼마나 떨어지는가**
  다. **저장하지 않는다** — 조건은 세션에만 있고 어느 DB 에도 쓰지 않는다. 계산은 `services/constraint_simulation.py`, 본문은
  `components/constraint_simulation_view.py`, 설명은 `guides/constraint_simulation.md`.
  - 입력은 새 무거운 계산이 없다 — 공통 진입은 공정 Capa 상세와 같은 `page_bootstrap.process_page_inputs`, 소요는 계획의
    `소요대수`(공정 합)와 `get_process_product_demand(split="제품정보", limit=CONSTRAINT_PRODUCT_LIMIT)`(제품별 — 「그 밖」 이
    생기지 않는 상한), 가용은 공정 Capa 상세 ②~④ 와 **같은 계획 칸·같은 키**(`load_required_shortening_for_target` 공식 칸,
    목표는 키 맞춤용 HOME 확보 기준)의 단축 전 `가용대수` 다. 설비는 늘 **세션 설비 시나리오**(HOME 칸 방문 공식 잠금을
    잇지 않는다 — D6. 잠긴 상세의 머리 링크로 넘어온 방문은 `CONSTRAINT_LOCKED_ARRIVAL_KEY`(공정, `page_visit()`)에 적어
    세션이 공식 발행 쌍이 아니면 그 공정·그 방문 동안 상태 알림 `CS-03`(「설비는 세션의 「…」 기준입니다 — 공정 Capa 상세는
    HOME 칸에서 열어 설비가 공식 고정이었습니다」 — 자리에 그리지 않는다, 설계 규칙 UI-NTF-02)이 선다 — 모드 분기 앞이라
    「개조 일정」 모드에도 서고, 판정은 상세의 방문 기준 칸 `PROCESS_DETAIL_EQUIPMENT_BASIS_KEY` 를 읽기만)이고, 필요 단축 일정의 공용 조회 조건(`0019`)·기준선(`0021`)·세션
    칸은 읽지도 쓰지도 않는다. UPEH
    가정·HOME 얹기는 걸지 않는다(UPEH 가정이 켜진 세션이면 상태 알림 `CS-06` — 두 모드 같음, 아래).
  - **공정은 조회 조건 패널의 공용 공정 칸(하나 고름 — `process_field.render_process_choice`)이고 두 모드가 나눠 쓴다**(2026-11-08
    답 P1 · P2-2). 공용 값을 받고(`shared_process.follow_single` — 값이 바뀐 뒤 처음 그리는 회차에 공용 값이 하나이고
    목록에 있으면 그 공정, 여럿이면 보던 공정) 주소 `process`(공정 Capa 상세 머리 링크)가 이긴다. 사이드바 공정 칸 팝업에서 직접
    고른 공정만 공용 값으로 보낸다(2026-11-09 보드 C2 (가) — 넘겨받은 공정 · 기본 공정은 보내지 않는다). 머리 줄은 멈춘 갈래의
    공정 · 배지뿐이고(계산이 선 회차에는 서지 않는다 — 맨 위 「← 공정 Capa 상세」 되돌아가기
    링크는 두지 않는다, 화면 탭 줄 · 사이드바가 같은 길 — 2026-11-09 보드 T4) 조건
    줄 · 출처 띠 · 계산표 범례는 Guide 다(그림 메모 g12). 첫날이 지난 개조 창 · 신규 대기는 상태 알림 `CS-04`(`report_late_starts`)다.
    계획이 건 입력 비가동(가용설비 현황 › Preference)은 머리 줄 표지가 아니라 상태 알림 `CS-05`(확인 필요 —
    `constraint_equipment_plan.report_manual_downtime`, 2026-11-10 보드 Q-4)다 — 필요 단축 일정 `RS-05` 와 같은 꼴(짧은 글 = 합
    대수 띠 · 고칠 자리, 전문 = 화면 · 공정 · 뜻 · 넘친 달, 「그 화면으로」 = 가용설비 현황 › Preference 탭)이고, 두 모드가
    `render_equipment_plan` 바로 뒤 한 자리에서 부른다(계획이 없으면 「해소」 — 조회기간에 확보율을 낼 공정 · 달이 없어 그 앞에서
    멈추는 갈래도 `active=False` 로 불러 앞 줄은 「범위 바뀜」 으로 닫힌다). 범위는 활성 리비전 · 조회기간 · 세션 설비 · 공정이고
    모드는 들지 않는다(모드를 바꿔도 다시 뜨지 않는다). UPEH 가정을 켠 세션(공정 Capa 상세 · 필요 단축 일정의 % 칸이 100 이 아닌
    정수)이면 상태 알림 `CS-06`(확인 필요 — `constraint_equipment_plan.report_upeh_not_applied`, 2차 보드 Q2-13)이다 — 같은 꼴(짧은
    글 = 가정 % 미적용 · 고칠 화면, 전문 = 화면 · 뜻, 「그 화면으로」 = 공정 Capa 상세)이고 머리 줄에는 아무것도 서지 않는다.
    페이지가 모드 분기 앞 한 자리에서 늘 부르고(가정이 꺼지면 「해소」), 범위는 활성 리비전뿐이다 — 조건이 공정 · 설비 · 조회기간
    · 모드에 기대지 않아 그것을 바꿔도 다시 뜨지 않는다.
  - 주소 `?process=` 는 무엇보다 먼저 꺼내고 그 키 하나만 지운다(`take_constraint_process_request` — 테마 인자는 남는다). 한 번
    적용한 값은 `CONSTRAINT_QUERY_SEEN_KEY`((값, 페이지 방문 차례) — 새 방문이면 같은 값도 다시 적용해 공용 공정을 이긴다)에 남겨 지운 것이 브라우저에 닿기 전 옛 주소를 실은 회차가 사용자가 그 뒤 고른 공정을
    덮지 않게 하고, 인자가 걷힌 회차에 비운다(공정 Capa 상세 `PROCESS_DETAIL_QUERY_SEEN_KEY` 와 같은 막이). 공정
    선택지는 공정 Capa 상세와 같은 전 공정이고(D12) 공정 칸이 비었거나 선택지에 없는 회차(사이드바로 처음 열기 등)의 기본은
    설비 일정이 서는 첫 공정(`constraint_equipment_plan.first_ready_process` — 멈춘 자리와 같은 `dynamic_readiness`, 없으면
    첫 공정)이다. 설비 일정이 서지 않으면 머리 배지 + 데이터 Error 마크 한 칸(`absent_note` — 까닭은 `CS-01` 알림 전문, 고치는
    화면은 Alarm 줄 「그 화면으로」 `EQUIPMENT_SCREEN`, 판정을 지나도 계획에 없는 공정은 「계획에 공정 없음」·「Cut-off 미기재」)으로
    멈춘다. 저장본 없음은 설비 DB 전체의 일이라 글에 공정을 넣지 않고, HBM·EDP 호기 없음 빈 상태는 배지 + 회색 평문 한 줄이다.
  - 오류는 넷으로 가른다 — 공통 진입(카드 캡션 — 조회 조건 패널의 공정 줄은 `process_field.render_stopped_process_field()` 의
    잠긴 값 칸 「계산 멈춤」 으로 자리를 지킨다, 산출 결과 · 공정 Capa 상세와 같은 꼴 — 2차 보드 Q2-28. 「설비 시나리오」 줄도 공정
    Capa 상세처럼 잠그지 않고 세워 정상 회차와 같은 높이다 — `equipment_scenario_status.render_stopped_equipment_scenario_row`,
    2026-11-11 보드 C1), 제품별 소요 받기(카드 캡션 + 본문 「제품별 소요를 읽지 못했습니다 — {글}」 —
    「소요가 있는 제품이 없다」 안내와 가른다), 계획 받기(「설비 일정을 계산하지 못했습니다」 + 두 DB 경로), 어댑터·서비스의
    `ValueError`·`KeyError`(「제약 시뮬레이션을 계산하지 못했습니다 — {글}」). `BOOTSTRAP_ERRORS` 에 `KeyError`·`ValueError`
    가 들어 있어 한 `try` 로 묶으면 뒤의 글이 앞의 글로 둔갑한다.
  - 조건 카드 「제약 시뮬레이션 조건」 은 맨 위 모드 전환 「제약 영향 | 개조 일정」(라벨을 숨긴 칸이라 뜻은 같은 줄 끝 ⓘ
    `MODE_SWITCH_HELP` — 2026-11-10 보드 Q-8, 처음 펼친 채 — 그림 메모 g12, 페이지가 한 번
    세워 두 모드가 채운다) 뒤에 대상(제약 제품·제약 시작·제약 끝 상자 둘 — 공정은 조회 조건 패널. 제약 제품 선택지는
    `constraint_product_choices` — 부품(`CUSTOM`)을 가르는 제품은 이름만 쓴 제품 전체 한 줄 뒤에 부품마다 「제품 (부품)」 줄이고
    세션 값은 그 이름표 글이라 부품을 싣기 전에 남은 제품 이름도 같은 뜻(제품 전체)으로 산다, 고른 이름표는 그래프 제목 ·
    머리 줄에 그대로 지나고 어댑터 · 첫 소요 달에는 (제품정보, 부품)으로 넘긴다 — 2026-11-23 보드 답 D3 (나))과 「이 세션만」 의 확보율(제약 확보율·
    기준 확보율)·개조(토글·개조 기간·보유 제약 호기 고르기·목록에 없는 보유 제약 설비·「신규 설비는 개조 없이」 토글과 신규
    기준일·Cut-off 읽기만) 세 묶음이다
    (D2). 버튼 + 직접 입력은 `preset_number_field.py`(D10 — 기준 확보율 칸은 정수 %(1% 단위, 처음은 HOME 기본의 정수 T, 직접 입력
    50 ~ 300% — `GENERAL_INPUT_RANGE` 가 HOME 판정 기준 저장 범위 `THRESHOLD_RANGE` 와 한 값, 2026-11-02 사용자 결정)다 —
    2026-11-01 사용자 결정으로 D18 의 0.5% 단위를 대신한다, Guide 도 그렇게 적는다. 기준 확보율 · 제약 확보율 칸은 소수를 받아
    사사오입한 정수로 읽는다 — `decimal_entry`, 109.5 → 110, 같은 날 밤 결정 — 8장 「판정 기준은 정수 %」). 보유 제약 호기 고르기(multiselect — 「전체 선택」 없음 `select_all=False`, 2026-11-05 답 r4 (가),
    2026-11-01 결정 B3)·목록에 없는 보유 제약 설비(환산 대수 숫자 칸, 기본 0 — B3-3 「같이 둠」)·신규 토글(기본 끔)·기준일
    (날짜 칸, 기본 오늘)은 2판 옵션이다 — 늘 서고 개조 끔이면 잠기며 그때는 서비스에 넘기지 않는다(고름·값은 세션에 남는다).
    목록에 없는 보유 대수는 사실 값이라 D10 버튼을 두지 않는다. **호기 고르기** 선택지는 그 공정 세션 설비 시나리오의 호기
    (`process_equipment_timeline.held_unit_choices` — 보관 N · 사용기준 HBM·EDP 이고 기존설비 Y 또는 Qual 있음, 축에 하루라도
    있는 설비키, 호기 번호 차례)를 같은 마스터 지문의 가벼운 캐시(`simulation_cache.get_process_held_units`, 키는
    `process_timeline_key_from_shortening` 그대로)로 받고, 계획을 받은 뒤 카드 안 자리(`held_slot`)에 그린다 — 계획 앞에서
    멈추는 갈래는 잠긴 빈 칸을 그린다(카드 모양이 같게). 정본은 위젯 아닌 칸 하나에 공정마다(`CONSTRAINT_HELD_KEY` —
    `{공정: [설비키]}`)이고 위젯 칸은 위젯 앞에서 매 회차 다시 적는다(`settle_held_units` — 글자가 바뀌어도 브라우저가 새
    글자를 받게). 지금 선택지에 없는 호기는 빼고 맨 위 한 줄로 알린다(B3-2 — 같은 공정 · 같은 선택지인 동안 남고 고름을 바꾸면
    걷힌다). 고른 호기는 `HeldUnit` 으로 `ConstraintConditions.held_units` 에 실리고 신규 후보에서 빠진다
    (`new_unit_availability(excluded=)`). 신규를 켠 회차에만 공정 Capa 상세 ④·⑤ 와 같은 설비 일정 칸(`get_process_equipment_
    timeline`, 같은 키)을 받아 기준일로 거르고 고른 호기를 뺀 호기마다의 기여 시작 · 환산 대수 · 반출(묶음은 첫 모듈과 모듈마다의
    기여 시작 — `new_unit_availability` → `NewUnit(modules=)`)을 `simulate_constraint(new_units=)` 에 넘긴다 — 어느 증가에
    붙일지(개조 일수 안 · 신규 대기)와 남은 보유가 남은 증가를 덮으면 그 증가부터 신규를 붙이지 않는 것(B1 — 증가마다)은
    서비스가 정한다(기준일·고름은 어떤 캐시 키에도 들지 않는다). 그 계산이 터지면 계획과 같은 「설비 일정을 계산하지 못했습니다」 갈래다. 카드 끝에 기준일 이후 신규
    호기 수·이름 한 줄(`new_units_slot` 블록)이 서고, 붙인 호기·일반 설비가 된 호기는 본문 개조 창 카드가 말한다. 그 밑 「견주기」 묶음의
    「비중 배분 비교」 토글(`CONSTRAINT_PROPORTIONAL_KEY` · `persist_state="session"`, 풍선은 짧게 — 뜻 · 식은 Guide)은 본문 위 보기
    줄이 아니라 카드다(2026-11-09 보드 C3 — 페이지 상단 문구 최소화) — 바꾸면 앱 전체 회차이고 본문 프래그먼트는 세션 값을 읽는다
    (`constraint_simulation_view.proportional_on`).
  - **모드 둘**(2026-10-26 결정 3) — 사이드바 조건 카드 맨 위 「제약 영향 | 개조 일정」(`components/modification_schedule_view.
    render_mode_switch`, `segmented_control` · `persist_state` — 카드에 무엇이 설지 정하는 전환이라 조건 카드에 두는 예외(9장),
    앱 전체 회차. 뜻은 같은 줄 끝 ⓘ). 「개조 일정」 이면 공통 진입·설비 세션·공정 칸 정리 뒤 `render_schedule_mode` 하나가 카드·설비 일정 확인·계획·계산·
    본문을 그리고 페이지는 멈춘다(제약 영향 모드의 카드·본문은 서지 않는다 — 1판은 두 모드를 함께 쓰지 않는다). 머리 한 줄·까닭
    머리 그리기(`render_header`)는 분기 앞에 두고 컴포넌트에 넘긴다. 설비 일정 확인(판정 · 멈춘 자리)과
    계획 칸 받기는 두 모드가 같은 함수(`components/constraint_equipment_plan.render_equipment_plan` — 입력 묶음
    `EquipmentPlanSource` 는 페이지가 설비 세션 뒤 한 번 만든다)이고, 제약 영향 모드는 그 사이 제품 갈래를 `before_plan` 으로
    넘기고 설비 일정 칸(`with_timeline` — 신규를 켠 회차)·호기 고르기 선택지(`with_held_units`)를 같은 `try` 안에서 받는다(멈추는
    갈래 차례 그대로). 개조 일정 모드는 둘 다 받지 않는다. 두 모드는 공정 칸(`CONSTRAINT_PROCESS_KEY`)
    ·기준 확보율 정본(`CONSTRAINT_GENERAL_KEY`)을 나누고 계획은 같은 키로 받는다(`tests/test_modification_schedule_page.py`).
    2판 옵션(보유 제약 호기·목록에 없는 보유 제약 설비·「신규 설비는 개조 없이」·신규 기준일)은 제약 영향 모드 카드에만 선다 —
    개조 일정 모드는 그 칸을 읽지 않는다(호기 고르기 정본은 위젯 아닌 칸이라 모드를 오가도 남는다).
- `app_pages/available_equipment_status.py` — `가용설비 현황`. 설비 운영 DB 의 입력·조회·Static 비교를 **탭 셋**으로 다룬다
  (2026-10-24 사용자 결정 — 두 탭 개편, 2026-10-27 셋째 탭): ① `설비 마스터`(처음 여는 탭 — 설비 마스터 표·작은 편집표 둘·오른쪽 칸 호기 상세/
  새 호기/저장 전 변경/저장 이력, 개편 B1·C — `components/equipment_master_tab.py`, 개편 전 `RawData`) ②
  `Summary`(안쪽 탭 `Main`·`Static 대비 일정` — 라벨 글자는 개편 전 그대로) ③ `Preference`(공정 × 생산월 **입력 비가동대수** —
  `components/manual_downtime_tab.py`, 설비 `0032` 공용 프로필. 개편 전 같은 이름 탭은 Cut-off 표였다 — 그것은 지금 「가용설비
  설정」 팝업이다). 공정별 Cut-off 는 사이드바 「가용설비 설정」 상자의 팝업(`equipment_settings_dialog.py` — 2026-11-03 부터
  사이드바 설정 상자 `components/settings_box.py`, 그 전에는 제목 줄 끝 「설정」 단추, 개편 전 `Preference` 탭), Qual 마감
  계산기는 필요 단축 일정 머리의 팝업, 설비 시나리오 목록·리비전·발행은 시나리오 관리 › 설비 시나리오다. 설명은
  `guides/available_equipment_status.md`.
  - 탭 선언은 `navigation`(`EQUIPMENT_TABS`·`EQUIPMENT_SUMMARY_TABS`, 안쪽 탭은 `ConditionTabs.sub` = `SubTabs`)이고 페이지는
    그 목록 그대로 `stateful_tabs` 를 세운다. 안쪽 탭은 바깥 Summary 블록 안에서 **늘** 부른다(위젯 값이 남아 사이드바가
    읽는다). 바깥이 숨으면 안쪽 고른 탭의 `open` 도 참이라, 본문 갈래와 두 부품(`render_equipment_explorer`·
    `render_availability_gap_panel`)의 `owner_tab` 은 바깥·안쪽을 합친 `tab_state.NestedTab` 이다 — ① 을 보는 회차에 Main
    탐색·Static 대비 일정 계산이 돌지 않는다. 바깥 key(`equipment_active_tab`)는 그대로라 옛 기억 값은 첫 탭으로 열린다.
  - ① 은 **열린 회차에만 그린다**(개편 B1 — 9장 「숨은 탭에서도 입력 위젯은 그린다」 의 예외). 표 편집은 세션 칸(편집본·출납
    기억)에 살아 숨은 회차에 그릴 까닭이 없고, 그 모듈(`equipment_master_tab`)은 표 컴포넌트를 등록하므로 열린 회차에만 불러온다.
    숨은 회차에 버려지는 것은 작은 편집표 둘의 적용 전 편집(화면 탭 줄 떠나기 확인이 묻는다)·변경 메모(입력 초안)이고 저장자는
    `persist_state` 로 남는다. 작은 편집표 제출은 그 탭의 모든 위젯을 그린 뒤 `st.rerun()` 으로
    끝나므로 **코드 차례는 Summary 블록 뒤**다(9장 「`st.rerun()` 은 그 화면의 모든 편집표를 그린 뒤에만」 — 화면 차례는
    `stateful_tabs` 목록이 정한다). 저장하지 않은 설비 편집(편집본·FAB 대기)이나 작은 편집표의 적용 전 편집
    (`small_editor_edits`)이 있으면 ① 탭 이름 옆에 점(`tab_marks`, 화면 탭 줄의 점과 같은 판정)을 찍는다.
  - ③ 은 **숨은 회차에도 폼을 그린다**(9장 — 적은 칸이 버려지지 않게. 저장 이력 표만 열린 회차). 코드 차례는 Summary 뒤·① 앞이다
    (① 의 작은 편집표 `st.rerun()` 이 ③ 폼을 건너뛰지 않게). 행은 지금 설비 시나리오 저장본의 공정(`processes_in` — 샘플 fleet 은
    쓰지 않는다) + 값만 남은 공정, 열은 사이드바 조회기간의 달이다 — 사이드바는 ③ 에서 **조회기간 줄만** 세운다
    (`ConditionTabs.period_labels` → `PageSpec.reads_period_only_on`, `app.py`). 가정 설비 시나리오면 표를 잠근다
    (`MANUAL_DOWNTIME_LOCK_MESSAGE` — Cut-off 와 같은 E3).
  - 진입은 `resolve_equipment_session` 이고 계산은 `calculation_drafts()` 다(일정 없음 호기를 뺌 — 「일정 없음 n대」 한 줄).
    계산 사본의 설비 마스터 지문(`equipment_data_workspace.calculation_digest`)은 Summary 조회 탭이 열린 회차(`viewing_tab_open`)에만
    내어 Main 의 일정 미정 · 사용기준 밖 · 미확인(공식 스냅샷 포함) · 주차 집계(거르는 조건이 없을 때만)와 Static 대비 일정의
    구간 키 둘 · 상태 알림 캐시 키에 넘긴다(`equipment_digest` 등 — 3장 `simulation_cache.py`) — 설비 마스터 탭 칸 고치기 회차는
    내지 않는다. 샘플 fleet 은 넘기지 않는다.
    가정 설비 시나리오면 Main 미확인은 **공식 스냅샷의 미확인**을 화면 호기로 좁혀 쓰고(꼬리표 「공식 일정 기준」),
    「가용설비 설정」 팝업의 Cut-off 는 읽기 전용(「설비 공정으로 채우기」 꺼짐)이다. 설비 시나리오 줄은 두 탭 모두 선다.
  - 「가용설비 설정」 상자는 조회 조건 패널 바로 밑 · `설비 조회 조건` 카드 **위**다(페이지가 카드보다 먼저 부른다 — 9장
    「사이드바·조건 카드·본문」 의 설정 상자 규칙). 탭에 매이지 않은 화면 설정이라 세 탭 모두 같은 자리에 서고, 설비 DB 를 읽지
    못한 회차(오류를 알리고 멈춤)에는 잠긴 채 같은 자리에 선다. 제목 줄은 큰 제목 하나다(끝 칸 없음).
  - 「가용설비 설정」·「엑셀·CSV로 한꺼번에」 팝업: 열림 칸은 페이지 한 칸(`available_equipment_open_dialog`, 값 `settings`·`import`)이고
    호스트(`render_equipment_dialog_host(import_dialog=)`)는 이벤트 칸에 늘 한 자리다(열렸으면 팝업, 아니면 빈 스타일). 새 방문
    회차에는 붙여넣기 미리보기를 거둔다(`withdraw_preview_on_new_visit` — 페이지가 매 회차 부른다). Cut-off 저장·「설비 공정으로 채우기」 뒤에도 팝업은 열려 있다(9장 「팝업과
    콜백」 의 예외). 첫 데이터 안내의 Cut-off 줄은 건수만이다(본문 설정 단추 없음 — 설계 규칙 UI-LAY-01). Static 대비 일정은 저장된 Cut-off 를 캐시 경계
    (`load_process_cutoff`)에서 직접 읽는다 — 팝업이 돌려준 값을 받지 않는다.
  - 첫 데이터 안내(「설비 데이터 입력」 단추 — 하는 법은 그 풍선 — 와 건수 줄)·샘플 스위치·`설비 조회 조건` 카드는 Summary 의 안쪽 탭이 보일 때만 선다
    (`viewing_tab_open`). 「설비 마스터 탭에서 붙여넣기」·「설비 데이터 입력」 은 ① 을 기억하고 「엑셀·CSV로 한꺼번에」 팝업을
    연다(첫 데이터도 그 팝업으로 넣고 「저장 전 변경」 에서 저장한다).
  - Main·① 은 설비 DB 만 쓰고 `Static 대비 일정` 만 시뮬레이션 DB 를 읽는다 — 못 읽어도 그 탭 안에서만 알린다
    (`test_equipment_scenario_demand.py`). ① 은 원본 이름(`test_process_label_boundaries.py`).
  - 조건은 탭마다 따로다 — `Static 대비 일정` 은 Main 의 공정소분류·추가 조건 키를 읽지 않고, 비교 범위는 이 탭의
    `공정`·`호기 필터` 만 정한다.
  - Main 틀은 `equipment_explorer.py`, 일정 미정 · 미확인 · 사용기준 밖 판정은 `undated_equipment.py`·`schedule_confirmation.py`·
    `usage_basis.py`(자리 줄이 아니라 상태 알림 `EQ-20` · `EQ-21` · `EQ-22` — 설비 마스터 전체, 9장 「알림 칸」),
    대수 축은 `equipment_units.py`, 월별 안분은 `wd_window.py`(규칙은 6장). Cut-off 는 리비전 없이 표를 통째 갈아 끼운다.
  - 편집본은 `ensure_equipment_drafts` 한 곳이 씨뿌린다(Space 와 버퍼 공유). 입력 표를 더하면 draft 키 이름을 올리고
    Import·버퍼 교체 때 그 편집표를 `discard_editor` 로 버린다(9장). ① 본문은 `equipment_master_tab.py`, 편집본 경계·작은 편집표·
    저장은 `equipment_data_workspace.py` 다(옛 입력·직접 편집·저장 이력 폼은 개편 D 에서 걷었다).

- `app_pages/actual_efficiency.py`, `app_pages/actual_upeh.py`, `app_pages/yield_actual.py` — 실행 관리의 효율·UPEH·
  수율 실적 비교·개선관리 하위 페이지 셋이다.
  - 화면은 `components/performance_actual_screen.py` 한 벌이고 이 파일들은 `MetricSpec` 과 머리말만 갖는다 — 머리에 배지 줄을
    두지 않는다(`show_status=False` — 구현 중 표지는 화면 탭 이름 곁, 합성 샘플 표지는 머리 띠, 2026-11-09 보드 T8). 소개는
    `guides/actual_efficiency.md` · `guides/actual_upeh.md` · `guides/yield_actual.md`.
  - 생산이력·수율 실적 DB 와 `RQ_RUN_RATE`·`RQ_UPEH`·`RQ_YLD` 연결은 아직 없다. 샘플 스위치(사이드바 조회 조건 패널 줄)를 끄면
    연결 뒤 계산할 것을 적은 자리표시자만 남는다.
- `app_pages/wip_status.py` — Dynamic Capa 의 `표준 대비 재공 현황` 하위 페이지로, 오늘 −7~+3일의 공정·제품·
  STEP별 재공·유입·Flow 를 제품별 일 표준 가능량과 견준다(재공 값은 결정론적 데모, 재공 DB 연결은 미구현).
  - 머리에 배지 줄이 없다(2026-11-09 보드 T8). 「샘플 데이터」 는 조회 조건 패널 줄(시나리오 줄 밑 페이지 칸), 공정 · 제품
    고르기와 「조건 적용」 은 사이드바 「재공 현황 조건」 카드(처음 펼친 채 — 2026-11-10 보드 Q-7)의 폼(적용형 — 설계 규칙
    UI-INP-04)이고 카드 맨 위 값 한 줄이
    기준일 · 조회 구간(오늘 −7 ~ +3일)이다. 공정 · 제품 칸은 이름 줄 + 적용한 값 한 줄 팝오버(「WF 입고검사 외 4개」 —
    `process_field.first_and_rest`, 풍선은 전체 목록)이고 다중 선택 칸은 그 안이다 — 300px 카드에서 칩이 한 줄에 하나씩 쌓여
    칸 높이 상한에 잘리고 「조건 적용」 이 1283 창 첫 화면 밖으로 밀렸다(UI-LAY-06, 필요 단축 일정 카드 공정 칸과 같은 꼴 —
    UI-CON-04). 선택지 차례는 Guide 다. 본문은 지표 넷과 격자다.
  - 소요대수에서 나오는 준비물(`services/wip_status.prepare_wip_route_choices`)은 세션에 한 벌 두고 키는
    `scenario_cache_key`·`display_order_digest(RQ_DISPLAY_ORDER)` 다. 가용대수는 다른 세션이 바꾸는 현행값이라
    매 회차 읽는다.
- `app_pages/space_status.py` — 실행 관리의 Space 현황으로, `S.PKG FAB 전체 → 층 상세` 2단 도면(`space_layout_editor.py`
  뷰어)에서 셋업 이행을 공간·호기로 본다. 상태별 대수·단계 전환은 가용설비 현황 몫이다(`guides/space_status.md`).
  - **사이드바 「Space 도면」 상자**(2026-11-03 사용자 요청 — 레이아웃 위 요소 넷을 사이드바 조회 조건 상자 꼴로, 9장
    「사이드바·조건 카드·본문」 의 화면 조작 상자): 조회 조건 패널 바로 밑 · `Space 조건` 카드 **위**에 이 화면을 볼 때만 선다
    (`page_box_key("space")` — `render_equipment_scenario_row` 바로 뒤, 첫 `condition_card` 보다 먼저 자리만 세우고 안은 옛 경로 줄
    자리에서 `with space_box:` 로 채운다 — 호기 없는 화면도 같다). 안은 제목 「Space 도면」 · 자리 줄 `FAB 전체`
    (`space_status_fab_breadcrumb`, FAB 이면 primary)·`층 바로 가기`(`space_status_floor_jump_<fab|C1-1F>`) · 도면 줄
    `배치 편집`(층 `space_layout_edit_mode`·잠기거나 설비 저장본이 없는 층이면 꺼진 짝 `space_layout_edit_mode_locked` — 풍선이
    까닭 / FAB `space_fab_edit_mode`, 줄마다 위젯 하나 · 가로 줄은 자리 줄 하나 — 2026-11-12 Space 보드 답 1-4 「캔버스 편집버튼은
    지우고 · 간격 일정하게」, 캔버스는 배치 편집 왼쪽 칸 「캔버스」) · FAB·가정이면 `공식으로 바꾸기`(세션 옮기기라 모든 등급 — 가정 여부는 `equipment_session.is_assumption` 으로 본다, 등급으로 꺼지는 `edit_mode.fab` 으로 가르지 않는다) · 잠금 줄(`_render_edit_lock_line` —
    표지 + 「최신 rM 불러오기」·빨리 감기 표지, 편집본이 있는 회차) · `공식과 견주기` 토글 · `반입 일정` 토글
    (`space_arrival_dates_v1`, 층 배치 편집 중 · FAB 이면 꺼진 짝 `space_arrival_dates_locked_v1` — 2026-11-12 Space 보드 답
    1-4 · 1-6 · A5, 켠 회차에만 뷰어 data `arrivalDates`)이다 — **상자에는 조작만 둔다**
    (줄 이름 「자리」 · 「도면」 도 달지 않는다 — 2026-11-09 사용자 검수 P1-5).
    상자 끝에 서던 배치 줄 · 일정 없는 호기 줄은 상태 알림이다(2026-11-04 Space 결정 보드 답 — 「인터페이스에 설명 문구를 다는
    걸 지양」, 9장 「알림 칸」): 배치 차이 `EQ-13`(알림 — `space_layout_notices` 의 `LayoutNotice` — 짧은 글 「가정 배치 · 공식과
    다른 호기 n대 · 도면 요소 m개」 등, 전문 · 지문 재료 `content` 는 실효 수 · 저장된 행 수, 아래 「보기」 문단) · 모듈 구성이
    바뀐 묶음 `EQ-14`(조치 필요 — 묶음 이름 목록) · 지운 호기의 차이 `EQ-15`(알림 — 행 수) · 일정 없는 호기 `EQ-04`(확인 필요 —
    가용설비 현황과 **같은 함수** `equipment_scenario_status.report_unscheduled_units` 로 낸다 — 같은 코드 · 범위 · 내용(설비명
    목록) · 글이라 화면을 옮겨도 다시 뜨지 않고, 「그 화면으로」 는 늘 고칠 자리인 가용설비 현황 › 설비 마스터(`alerts.state(goto=)`)
    라 어느 화면이 먼저 내도 줄이 같다, 전문은 `unscheduled_notice`, 공식 발행 쌍은 「공식 일정 없음 n대 — …」). 넷 모두 회차마다
    조건이 없어도(샘플 화면도) 본문 `notices` 칸에서 같은 차례로 부른다(표지 자리 수가 회차마다 같다 — 배치 알림 셋은
    `space_floor_layout.report_layout_notices`). 범위는 `state_alerts.equipment_scope`(세션 리비전 쌍), 배치 알림 셋의
    「그 화면으로」 는 Space 다. 넷은 걷은 경고 짝 그물(`tests/test_withdrawn_warning_alerts.py` `WITHDRAWN` — 설계 규칙 V-09)에
    있다.
    알림 글은 평문이라 시나리오 이름의 마크다운 글자를 막지 않는다(「「…」 시나리오가 가정이던 때의 배치안입니다」).
    위젯 key 는 옮기기 전 그대로다(세션 값·화면 확인이 산다). 본문에서는 경로 줄(`space_path`)·테두리 상자·머리 줄
    (`space_fab_head`·`space_floor_head`)·편집 캡션 두 줄을 걷었고 도면은 늘 서는 칸 `space_fab_stage`·`space_floor_stage` 안이다
    (순번이 밀려 다시 마운트되지 않게). 시험은 `tests/test_space_sidebar_box.py`.
  - **공정소분류는 조회 조건 패널의 공용 공정 칸이다**(`process_field.render_process_filter(options, screen="Space", labels=None)` —
    원본 글자, 2026-11-08 답 P1). 「이 층 공정」 칩 · 호기 추가 공정은 잇지 않고, 「도면에서 보기」 도착 알림은 공용 값으로 견준다
    (`consume_layer_link(filter_values=)`). 미배치 칸 머리 「(모듈 n)」 은 묶음 칩의 모듈만 세고 접힌 단추 수는 설비 대수다(d13).
  - 연 층은 세션 키 `space_status_selected_building`·`_floor` 가 먼저이고 주소 `?floor=` 는 `floor` 만 넣고
    지운다(`st.query_params.clear()` 금지). 자리 이동은 모두 콜백이다. 브라우저 뒤로/앞으로는 층 이동이 아니다.
    **예외 하나** — 필요 단축 일정 「도면에서 보기」 주소(`?layer=short&floor=…&proc=…&target=…`)는 페이지 맨 앞에서 한 번 받아
    (`space_shortening_view.consume_layer_link`) 그 층이 세션 층을 **덮고**(`floor` 가 없거나 비활성 층이면 세션 층을 지워 FAB
    전체), 색 기준·목표·그 층 공정 칩을 적고 배치 편집 토글을 끈 뒤 남길 인자만 `from_dict` 한 번으로 다시 싣고 회차를 한 번 더
    돈다(사이드바 줄을 맞추려고 — 아직 그린 편집기가 없는 자리). 그 주소를 테마 인자 없이(다른 브라우저 등) 처음 열어 테마
    새로고침이 걸리면, 지운 링크 인자는 테마 스크립트가 문서를 연 주소에서 되살려 새 세션이 다시 받는다(`theme_toggle` 의
    `<theme-reopen>`).
  - **색 기준 「필요 단축」**(2026-10-24 결정 — 라디오 셋째 값, `services/space_shortening_layer.py`·
    `components/space_shortening_view.py`). 켠 동안만 필요 단축 일정과 같은 계획(같은 키·같은 칸, 설비는 세션 시나리오 — LY6)을
    꺼내고(5장 9), 목표 확보율은 사이드바 조회 조건 패널 페이지 칸(`target_level_field.LEVEL_SLOT` 1 — 첫 칸은 공용 공정 칸,
    2026-11-08 그림 메모 g05)의 이름 줄 + 값 칸(`condition_field` — 칸 key `condition_field_space_target`, 값 칸 key
    `space_shortening_level_field`, `render_level_field` — 필요 단축 일정과 같은 부품 `TargetLevelField`)이다. 값 칸을 누르면 Space 화면 팝업 호스트(`space_shortening_view.SPACE_DIALOG_HOST`
    — 화면당 하나, 본문 끝이 매 회차 부르고 `LEVEL_DIALOGS` 는 보기를 그리는 회차에만 넘긴다)가 다섯 목표 라디오 + 직접 입력 칸 팝업을 열고(부품이
    하나라 필요 단축 일정의 직접 입력 — 2026-11-11 Q2-26 · − · + · ⊗ 숨김 Q226-stepper (나) — 이 여기에도 선다, 다섯 밖 값은 `load_space_layer` 가 같은 길로 더한다), 고르거나 넣으면
    세션 칸(`SPACE_SHORT_LEVEL_KEY` — 위젯 key 가 아니다)에 적고 곧바로 닫혀 다시 그린다(HOME 주요공정 히트맵 팝업과 같은 꼴 — 검수
    보드 p-target-form, 옛 전환 단추 다섯 · 한 줄 서식은 걷었다). 배치 편집으로 쉬는 회차에도 값 칸은 잠근 채 서며 까닭은 그 칸 풍선이다. 「단축 없는
    호기 흐리게」(`render_dim_field`)와 기준 달 한 줄(`render_layer_basis` — 풍선이 설비 · 시뮬레이션(미저장 편집 포함) · 오늘)은
    `Space 조건` 카드의 「색 기준」 밑(필요 단축 기준의 그룹 체크 자리 — 2026-11-09 사용자 검수 g05, 쉬는 회차에도 흐리게 칸은 선다),
    맞대지 못한 공정은 필요 단축 일정과 **같은 함수** `required_shortening_panel.report_unmatched_processes`(`RS-02` — 같은 계획 · 범위 ·
    내용이라 화면을 옮겨도 다시 뜨지 않는다, 보기를 그린 회차에만 부르고 그 밖의 회차는 같은 자리에서 `alerts.flush()`), 공정 필터 밖
    단축 대수는 FAB 요약 · 층 보기 칸 머리 줄 끝 「필터 밖 n대」 다. 「도면에서 보기」 로 온 공정이 공정 필터 밖이면 도면 위 표지 줄
    대신 도착한 회차에 사건 알림 `EQ-24` 한 번이다(`report_arrival_filter` — 그 앞 `RS-02` 상태 · `flush` 자리가 같은 회차에 보낸다,
    2026-11-09 사용자 보드 T10). **본문 자리**(늘 서는 `space_shortening_toolbar` — 못 읽음 마크 · FAB 편집
    「필요 단축 보기 쉼」 뿐, 도면 위에 글 줄을 두지 않는다)·FAB 블록 셋째 줄·층 목록 칸 넷·요약·추가 호기 상자(늘 서는
    `space_shortening_fab_slot`)·층 보기 칸(늘 서는 테두리 없는 `space_shortening_slot` 안 — 공정 칩·「이 층에서 단축할 호기」·
    도면에 자리가 없는 호기·누른 호기 상세)을 그린다. 켠 회차의 기준일은 오늘로 고정이다(세션 기준일은 지우지도 쓰지도 않는다 —
    뷰어 `asOfPinned` 고정 줄). 배치 편집 중은 쉰다(라디오 값 그대로, 그리는 색은 공정구분 기본 —
    `effective_choice` 를 편집기·범례가 같이 쓴다). 쉬는 까닭 한 줄(`_render_layer_rest_caption`)은 한 화면에 한 번이다 — 층
    상세는 편집기 위 캡션, FAB 편집은 편집기 캡션이 없어 본문 자리가 적는다. 비활성 층 상세에서는 쉬지 않고 배너 아래
    그대로 서되 추가N 을 붙이지 않는다(층 사용 명세 8-2). 층 보기 칸이 세는 행은 그 층에 **오늘 그려지는** 행이다(뷰어 roster 의 페이더 범위 합집합이 아니다 — FAB 층
    대수와 같은 축). 계획을 못 읽은 켠 회차의 범례는 채우기 칸 없이 테·덧표시만이다(뷰어가 지연·보관 면을 끈다 — D12). 상세 단추 「필요 단축 일정에서 이 공정 보기」 는 대기 칸만 적고 다음 회차
    본문 맨 앞(`switch_to_queued_shortening`)이 옮긴다. epoch 는 바뀌지 않는다(레이어·목표·칩·흐림은 epoch 밖). 사이드바
    시나리오·조회기간 줄은 그 값일 때만 선다(`navigation.SPACE_STATUS.condition_tabs` — 보기 값으로 가른다). 공정 칩은
    `release_process_chip` 이 칩 위젯·도면 payload 전에 푼다(None 을 적는다) — 목표를 바꿔(층마다 칩을 마지막으로 본 목표
    `space_shortening_chip_levels` 와 다르다) 칩 공정이 「단축 없음」 이 됐거나, 그 회차에 도면에서 칩 밖 공정 호기를 눌렀을 때다
    (뷰어 누르기 콜백 `_pick_unit` 이 `note_unit_pick` 표지를 남기고 층 상세가 `take_unit_pick` 으로 거둔다). 링크가 정한 칩은
    목표를 바꾼 것으로 보지 않는다.
  - 기준일(`space_status_as_of`)은 층 도면 위 페이더가 손을 뗄 때 한 번 보내고 끄는 동안은 브라우저가 경계 날짜로
    칠한다(`services/space_unit_state.py` 와 같은 식, 날짜는 epoch 밖, 성능은 `scripts/check_deploy_screens.py`).
    분기 눈금 글자는 트랙 폭에 맞춰 솎는다(editor.js 순수 구획 `<fader-ticks>` — 「오늘」 은 늘 서고, 트랙 밖이거나 이웃과
    2px 안으로 붙는 글자는 `is-crowded` 로 숨김, 회차마다·크기가 바뀔 때 다시 잼, `tests/test_space_fader_ticks_js.py`).
    기준일 줄 폭 560px 아래(390px 창)에서는 날짜 칩이 13.5rem → 8.5rem 고정 폭이다(CSS 컨테이너 `sle-daterow`) — 390px
    창에서 트랙이 68px 로 줄어 글자 7쌍이 겹쳤다(E2E 결함, 고친 뒤 146px). 768·1400px 창은 예전 그대로다.
  - 보기는 **사이드바에서 고른 설비 시나리오**의 배치다(설비 시나리오 2단계 S3 — LY3, `PageSpec.equipment_scenario="session"`·
    `uses_equipment_db=True`). 그리는 한 벌은 세션 스냅샷(`resolve_equipment_session(...).snapshot.calculation_frames()`)
    하나이고 가정이면 그 리비전의 호기 배치 차이가 얹혀 있다. 층 도면 요소·Main 설비명 위치는 **모두**
    `components/space_floor_layout.effective_floor_layout`(공식 층 현행값 ⊕ 그 리비전의 요소·이름표 차이)을 지난다 — 뷰어·
    편집기·「그대로인가」 판정·층 대조 기준 지문·저장 안 한 상자의 겹침 경고(공식 현행값 직접 읽기 0 — 시험이 소스를
    훑는다). 배치 알림은 **그리는 스냅샷**으로 정한다(`space_layout_notices` — 알림마다 등록부 코드 `code`, 알림창 짧은 글
    `short`, 전문 `text`, 지문 재료 `content`. 아래 「」 안은 전문이다 — 「가정 배치 · 공식과 다른 호기 n대 · 도면 요소 m개 · Main
    설비명 위치 k개」(짧은 글도 같은 앞머리), 차이 없는 가정은 「가정 설비 시나리오 · 배치는 공식과 같습니다」(짧은 글 「가정 배치
    · 공식과 같음」), 공식 시나리오의 가정이던 때 리비전도 알림을 낸다 — 실효 차이가 있으면 「이 리비전은 공식과 다른 배치(…)를
    담고 있습니다」(짧은 글 「가정이던 때 배치 · …」), 저장된 차이가 모두 지금 공식과 같으면 「이 리비전에 저장된 배치 차이(…)는
    지금 공식과 같습니다」 하나(짧은 글 「가정이던 때 배치 · 지금 공식과 같음」) — 모두 `EQ-13` 한 코드다. 옛 리비전은 불변이고
    정리는 최신에서 하므로 그 글에는 「다음 저장·지정 때 정리됩니다」 꼬리를 달지 않는다(E2E r5). 묶음 다시 맞춤은 `EQ-14`,
    버린 차이는 `EQ-15`). 그 시나리오에 일정이 없는 호기는 그리지 않는다(`unscheduled_notice` — 공식 발행
    쌍이면 「공식 일정 없음 n대」). 미확인은 가정이면 공식 일정 기준(가용설비 현황과 같은 `official_confirmation_master`),
    층 캔버스 줄이기 검사는 공식 배치 마스터다. 기준일 상태 · 오늘 상태 · 미확인 셈의 캐시 키에는 스냅샷 계산 프레임의 지문
    (`equipment_data_workspace.snapshot_digest`)을 넘긴다 — 편집본 · 후보 표 · 가정 세션의 공식 기준 마스터는 넘기지 않는다. 뷰어 epoch 는 편집 가능 여부와 떼어 늘 쌍 토큰을 담는다(샘플만 「sample」 —
    잠긴 두 쌍을 오갈 때 옛 좌표가 남지 않게, 검토 F1).
  - **「공식과 견주기」**(설계 시나리오 2단계 S4 — 설계 8-3). 사이드바 「Space 도면」 상자에 **늘 서는** 토글
    (`space_compare_official_v1`, `persist_state="session"`)이고, 해당 없는 회차(공식 배치·호기 차이 없음·층 배치 편집 중·샘플·
    일정 없이 엶)에는 다른 key(`space_compare_official_locked_v1`)의 끈 채 잠근 토글을 같은 자리에 세운다 — 조건부로 생겼다
    사라지면 상자 줄이 흔들린다(옛 경로 줄 자리에서는 아래 뷰어 순번이 밀려 다시 마운트되고 배율을 잃었다 — 검토 L11). 견줄 것은 **그리는 스냅샷**의 호기 차이
    (`layout_official_places` — 배치 알림 `EQ-13` 과 같은 재료, 공식 스냅샷을 따로 읽지 않는다). 켜면 층 상세 뷰어 payload `compare`
    (`components/space_floor_layout.compare_payload` ← `services/layout_overlay.layout_compare` — **epoch 밖**이라 켜고 꺼도 다시
    마운트하지 않는다)가 공식 자리가 이 층인 차이 호기의 점선 상자(같은 층으로 옮겼으면 지금 상자와 가는 선, 다른 층이면
    「→ C2 3F」 — 비활성 층이면 「→ C2 3F(비활성 층)」(`inactive`), 레이아웃표시 N 이면 「도면 제외(가정)」, 좌표가 없으면
    「미배치(가정)」)와 다른 층(또는 공식 미배치)에서 온 호기
    꼬리표(「← C1 2F」·「← 공식 미배치」)를 싣고 편집기 JS 새 층 `sle-compare`(보기 전용·눌림 없음·겹쳐 숨기기와 무관, 순수
    `compareShapes` — `// <view-compare>` 구획, node 시험)가 그린다. 이웃한 꼬리표가 겹치면 뒤 꼬리표를 한 줄씩 위로 올린다
    (글자 폭 어림 — 한글·화살표 1em). 공정 필터·일정 없음으로 그리지 않는 호기는 견주지 않는다.
    편집기에는 보내지 않는다. FAB 전체는 층 목록 표 끝 「공식과 다름」 칸(`space_floor_list.FloorListColumn` — 그 층에서 나갔거나
    들어왔거나 그 층 안에서 옮긴 설비 수, 묶음은 1대 — `unit_differences_by_floor`)과 층 블록 풍선 한 줄 「가정 배치 n대 다름」
    (`floor_block_stats(layout_differences=)` → `linkStats.layout`)이다. 그 줄 끝에 공식과 자리가 다른 호기가 든 겹친 쌍 수
    「· 겹침 n쌍」 이 붙는다(`space_floor_layout.floor_moved_overlaps` — `layout_overlay.moved_unit_names` 의 호기만 그 층의 다른
    호기와 견주는 `space_layout_edit.overlap_counts_touching`, 「겹친 호기」 경고와 같은 판정 — 개선 I74). FAB 셈도 층 상세와 같이 그리는 호기(공정소분류 필터를
    지난 것 — `floor_unit_differences(session, shown=)`)만 센다 — 같은 표의 배치대수와 어긋나지 않게. 도면 요소·Main 설비명 위치 차이는 배치 알림(`EQ-13`)의 수만이다(2026-11-04 Space 결정 보드 답 — 견주기는 지금대로 호기 자리만).
    데이터 꼴은 기준 쪽/보는 쪽 이름이라 반대 방향(공식 세션에서 고른 가정 시나리오를 점선으로)도 받을 수 있다(구현은 범위 밖).
  - **편집 권한은 `equipment_scenario_activation.space_edit_mode(session, stamped_role=)` 한 판정**(설계 8-4 표 — 설비
    마스터 탭 배치 칸·붙여넣기도 같은 `layout`). 공식 시나리오는 공식 배치(낡아도 — 위치는 공통, 새 호기 폼만 꺼짐), 공식
    시나리오의 가정이던 때 리비전은 잠금, 가정 최신은 그 시나리오의 배치 차이(새 호기 폼 켬 — Q1), 가정·낡음은 그 시나리오
    최신의 배치 지문이 이 리비전과 같으면 빨리 감기(캡션 — 저장소가 최신의 일정 위에 받는다) 다르면 잠금(「최신 rM
    불러오기」), 찍힌 역할 ≠ 지금 역할이면 잠금(「배치 변경만 버리기」), 일정 없이 엶은 잠금이다. FAB 전체·층 캔버스·배경
    도면·층 사용(0029)은 공식 시나리오에서만 편집한다(G5·Q3 — 꺼진 단추의 풍선이 까닭, FAB 자리에 「공식으로 바꾸기」 — 일정
    없이 연 세션에는 세우지 않는다, 공식으로 옮겨도 같은 까닭으로 합쳐지지 않는다). 찍힌 역할이 바뀐 잠금 글은 화면이 둘이다 —
    Space 는 그 자리의 「배치 변경만 버리기」, 설비 마스터 탭(`SpaceEditMode.master_tab_lock_reason`)은 그 단추가 있는 Space
    현황 저장 안 한 배치 변경 상자를 가리킨다. 「공식으로 바꾸기」·「최신 rM 불러오기」 실패는 저장 오류와 따로
    (`SWITCH_ERROR_KEY`) 잠금 줄 자리에 「설비 시나리오를 바꾸지 못했습니다」 로 선다. 편집기 「캔버스」 칸은
    `canvas_editable=False` 면 JS 가 끄고 서버도 적용의 캔버스 값을 거부한다(두 겹 — 까닭은 칸을 감싼 묶음 풍선, 빨간 글 없음). JS 잠금(캔버스 칸·새 호기 단추)은
    회차마다 받은 값대로 켜고 끈다(`lockCanvasControls`·`lockNewUnitToggle` — 편집기 key 는 시나리오가 바뀌어도 같아 같은 DOM
    이 남는다). 사이드바 설비 시나리오 줄은 편집본을 세운 **뒤에** 그린다(남의 저장 뒤 배지가 한 회차 늦지 않게). FAB 대기분
    저장은 어느 세션에서나 된다(대기분은 공식 세션에서만 생기고 FAB 은 시나리오 없는 공용 값 — 가정 세션 저장 상자에 한 줄).
    1단계의 「공식 발행 쌍에서만 편집 — [공식으로 바꾸기]」 잠금과 `space_editing_allowed` 는 걷었다. 편집본은 실제
    저장본이면 늘 세션 토큰으로 세운다(세션 토큰 하나라 다른 화면 편집을 버리는 갈림이 없다).
  - 배치를 바꾸는 적용(호기·숨은 모듈·새 호기·캔버스·요소·Main 설비명 위치)은 그때의 역할을 찍는다(`stamp_layout_role` —
    설계 6-2). 층 배치가 잠긴 회차에 남은 배치 변경은 상자의 「배치 저장」 을 끄고 「배치 변경만 버리기」(`discard_layout_edits`
    — 배치 일곱 칸·층 대기분·편집기 모듈 모양·찍힌 역할만 버리고 공통·일정 편집·이름 바꿈·FAB 대기분은 남김)를 세운다.
    버린 뒤 편집본이 저장본 사본과 내용까지 같고 이름 바꿈·표 칸 초안이 없으면 저장본으로 돌아온 세대로 적어(`_note_if_back_to_saved`) 「미저장 변경」
    배지·탭 점·불러오기의 「변경을 버리고」 체크가 꺼지고, 알림도 「저장 안 한 설비 편집은 이제 없습니다」 다(버리기도 세대를
    올려 세대 판정이 편집이 남았다고 봤다 — 2026-10-27 E2E). 잠금이 「최신 rM 불러오기」(`lock_action == "latest"`)이고
    상자에 이름 바꿈·설비 마스터의 다른 편집·곁표 편집이 없으면 곁에 「배치 변경 버리고 최신 rM 불러오기」
    (`_discard_layout_and_load_latest` — 버리고 남은 편집이 없을 때만 `_switch_scenario` 로 잇고, 남았으면 불러오지 않고
    알린다 — 개선 I72)가 선다.
        저장 상자는 머리 줄 하나다 — 건수 · 「변경 내용」 팝오버 · `배치 저장` · 「버리기」(`_render_unsaved_layout_panel`). 배치 편집 중에는 저장할
    변경이 없어도 같은 줄을 잠근 채 세워 높이를 잡는다(`_render_idle_save_row` — 표지 「저장할 변경 없음」, UI-PRF-03). 변경 메모 · 저장자
    칸(`render_saved_by_field`) · 바뀐 호기 · 이름 바꿈은 「변경 내용」 팝오버 안이고 저장 칸 체크는 없다(2026-11-05 사용자 결정, 함께 넣기 ·
    발행은 늘 한다). 그 메모 · 저장자는 팝오버 **밖** `배치 저장` 이 읽어서 Esc 로 닫아도 값이 서버로 가게 `popover_field_commit`
    칸(`ESC_COMMIT_PREFIX`)에 둔다. 어디로 저장되나는 `배치 저장` 풍선 앞머리다(이름 바꿈은 공통 대장 — 이름만 바꿨으면 그 한 줄만, 이름
    바꿈은 어느 시나리오에서나 같은 호기의 이름이라 가정 배치 리비전을 만들지 않는다. 적용 알림의 「가정 배치로 들어가고」 도 배치를 바꾼
    적용에만, E2E r6). 「버리기」 팝오버의 뜻은 「모두 버리기」 풍선이다. 겹침 · 덮음 · 같은 층 FAB 블록은 상자에 적지 않고 상태 알림 `EQ-17`
    이다(`report_layout_warnings` — 저장 안 한 배치가 아니라 편집본 전체를 말하고, 겹침을 재지 못한 회차에는 해소로 닫지 않는다). 층 배치
    잠금 줄은 사이드바 「Space 도면」 상자의 `배치 편집` 바로 아래에 그린다(본문 늘 서는 칸 `space_edit_lock_slot` 에는 시나리오 바꾸기
    실패·저장 오류만). 자리에는 표지 「배치 잠김」(`LAYOUT_LOCK_MARK`) 한 마디이고 잠금 까닭(`lock_reason`)은 그 풍선이다 — 상자는 표지
    「배치 저장 잠김」(풍선이 「배치 편집이 잠겨 이 배치 변경은 저장하지 않습니다 — …」 + 잠금 까닭, 까닭이 없을 때만 「최신을 불러온 뒤 다시
    고칩니다」 — 설계 규칙 UI-INP-07 · UI-TXT-04)와 「배치 변경만 버리기」 만(E2E r2). 저장 범위(세션에만 있음 · 함께 저장되는 다른 편집 ·
    FAB 은 따로)는 `배치 저장` 풍선이고(저장이 늘 하는 일은 Guide · 결과 알림), 함께 저장되는 설비 마스터 다른 편집 · 곁표 편집은 상자 머리
    줄 끝 값이다(UI-NTF-09). 배치 빨리 감기 글(`notice` — 「rM 이 더 새롭지만 배치는 같습니다 — …」)도 사이드바 상자 잠금 줄 자리의 표지
    「최신 일정에 저장」(`FAST_FORWARD_MARK`) 풍선에만 적는다(E2E r3).
  - 배치 편집은 설비 마스터 탭과 같은 편집본에 저장 검사를 거쳐 얹고 `save_equipment_buffer` 로 저장한다(「배치 저장」 — 공통·일정이 모두 그대로면 층 값만 쓰고 리비전을 만들지 않는다). 도면 상자 앞 칸
    (`space_unsaved_layout_slot`)은 늘 세운다 — 순번이 밀리면 편집기가 다시 마운트된다.
  - 층의 Main 설비명 위치(대기분 `pending_floor_group_labels`, 없으면 `effective_floor_layout` 의 합친 값)를 편집기·뷰어에
    넘기고, 적용은 `next_group_labels`(실린 묶음의 모듈 수 `module_group_sizes` 로 처음 위치를 가른다)로 층 위치
    목록을 만들어 저장값과 다르면 `stage_floor_group_labels` 로 둔다. 편집기·뷰어 epoch 와 층 대조
    (`FloorLayoutBase`)는 요소와 위치를 함께 본 `floor_layout_fingerprint` 다.
  - 적용이 옮기거나 빼거나 보낸 모듈 묶음(이 적용의 `changes`·`hidden_moves` 에 모듈이 든 묶음)의 적용 뒤 모양
    (`module_layouts`)을 `stage_editor_module_layouts` 로 둔다 — 저장의 모듈 묶음 좌표·크기 검사가 그 모양 그대로인
    묶음을 편집기 결과로 통과시킨다(`equipment_data_workspace.saved_master_violations`).
  - 층 상세 범례는 편집기 왼쪽 칸 「범례」 다 — 페이지가 `space_legend_entries`·`shortening_legend_entries` 칸 목록과
    「기준 YYYY-MM-DD」 를 뷰어 data `legend` 로 넘긴다(epoch 밖, 편집은 채우기 뜻만). 저장 안 한 배치 상자를 그렸는지
    (`_render_unsaved_layout_panel` 이 돌려준다)는 뷰어·편집기 data `pendingSave` 로 넘긴다(화면 고정 중 상태 줄 한 줄).
  - **「호기 정보」 창**(2026-11-03 사용자 요청 — 옛 층 상세 아래 호기 표를 도면 위 창으로, 거꾸로 칸 필터 → 맞는 호기 목록 →
    도면 강조). 표 재료는 `services/space_unit_sheet.unit_sheet`(칸 `space_layout.FLOOR_TABLE_COLUMNS` 21칸 — 2026-10-23 요청 차례,
    칸 이름은 설비 마스터 그대로, 「단계」는 기준일 상태 — + 끝 「도면」 배치·미배치·레이아웃 제외)이고 뷰어·층 편집기 data
    `sheet`(epoch 밖)로 싣는다. 층 보기는 `_view_sheet`(이 층 행 — 공정 필터 뒤 — 가운데 기준일에 도면에서 빠지지 않은 것, 도면에
    선 행은 배치), 배치 편집은 `_edit_sheet`(편집본의 이 층 행 + 편집기 호기 — 층 미정 미배치 포함, 공정 필터와 상관없이)다. 새 DB
    읽기는 없다(그리는 프레임 그대로). 창·거르기·강조는 편집기 JS 몫이다(`space_layout_editor` 항목). 층 CSV 도 창 안이다
    (2026-11-04 Space 결정 보드 답 — 페이지 아래 내려받기 줄을 걷음): 창 제목 줄 「CSV」 펼침의 「도면에 선 호기 · 모든 칸」 은 data
    `sheet.csv`(`space_unit_sheet.floor_csv` — 그 층 도면에 선 호기(공정 필터 뒤)의 모든 칸 `to_csv(index=False)` 글 + 파일 이름
    `space_동_층.csv`, 보기 · 편집 모두 같은 저장본 글 — 창의 미배치 · 레이아웃 제외 줄은 없어 「층 전체」 라 부르지 않는다)이고 브라우저가 BOM 을 붙여 UTF-8 Blob 으로 내려받는다 — 옛 내려받기와 같은
    바이트다. 「보이는 줄」 은 지금 탭의 줄을 창의 칸으로 JS `sheetCsv`(`// <unit-sheet>` — QUOTE_MINIMAL · LF)가 짓는다. 크기는
    표와 같은 차례(층당 수백 줄 — 샘플 관측: 검수 샘플 사본 C1 1F 74줄 · 50칸 · 22KB)라 회차마다 실어도 된다. 뷰어 호기 누르기(`on_pick` 콜백 → 세션 `space_status_picked_unit` = (동, 층, 설비명))는
    색 기준 「필요 단축」 칸의 누른 호기 상세만 쓴다 — 뷰어는 그 보기를 켠 동안만 보내고(`pick_to_server`, 사양 D11 — 누를 때마다
    앱 전체가 돌지 않게) 그 보기가 서지 않은 회차(끈 층 보기·배치 편집)에는 페이지가 그 세션 값을 푼다. 다른 층·FAB 로 옮기거나 그
    층 행에 없으면(필터·이름 바꿈) 푼다. 뷰어 호기에는 설비지분 `share`(기준일 보유 지분
    `space_layout.row_unit_shares` — 범례·배치 대수와 같은 칸, 일부 모듈만 반입한 묶음의 반입 전 모듈은 0)를 싣는다.
  - **창 칸 고치기**(배치 편집 — 2026-11-12 Space 시안 보드 답 5-4 ~ 5-6): `_render_layout_editor` 가 설비 마스터 탭과 같은
    표 조건(`equipment_master_tab.grid_context` — 세션 · 저장 기준 · 배치 판정 · 캔버스 · 오늘)과 줄마다 잠금 갈래(`space_sheet_edit.
    unit_lock_kinds`)로 data `sheetEdit` 를 싣는다. 적용값 `cells` 는 `parse_editor_apply(sheet_ids=)` 가 꼴만 읽고 차례는
    `apply_layout_edits` → `check_sheet_cells`(표와 같은 인자 — 캔버스 · 오늘) → `apply_name_changes` → `prepare_equipment_master`
    다(칸은 옛 이름으로 온다). 막힌 칸이 있으면 적용 전체를 받지 않고 판정을 세션 `space_sheet_refused_v1` 에 두어 같은 epoch
    편집기 data `sheetRefused` 로 돌려주며 사건 `EQ-25` 를 담고 한 번 더 돈다(편집기 아래 오류 글 없음). 창에서 고친 칸을
    브라우저가 잠깐 모아 보내는 「확인만」(칸 떠남 · 「적용」 직전 · 떠나기 신호 때는 곧바로 — 2026-11-20 사용자 결정 Q3, 3장
    `space_layout_editor.py` 「호기 정보」 창)은 콜백(`on_sheetCheck_change` → `_check_sheet_request` — 그린 회차의 편집본 · 표 조건 · 잠금 · 캔버스 · 오늘을 쥔
    `partial`, 편집본 세대가 바뀌었으면 버림)이 본문보다 먼저 같은 `check_sheet_cells` 로 판정해 세션 `space_sheet_verdict_v1`
    에 두고(다음 회차 data `sheetVerdict`) 새로 막힌 칸(설비명 · 칸 · 글 · 규칙이 앞 판정에 없던 것)만 `EQ-25` 로 낸다 — 편집본에는
    넣지 않는다. 앞 판정은 요청의 `base`(브라우저에서 고친 칸이 마지막으로 빈 seq)보다 뒤의 seq 일 때만 쓴다 — 칸을 비운 뒤 같은
    막힌 값을 다시 치면 다시 알린다. 그 밖의 적용 거부(층 · FAB 편집기의 「적용하지 못했습니다」 · 다시 서는 사이의 누름)도 편집기 아래 글 상자 대신
    `_refuse_apply`(알림창 · Alarm `FL-04` · `FL-03` + 한 번 더 돎)다(설계 규칙 UI-NTF-03 예외). 받은 적용은 쓴
    (설비명, 칸)(따라간 묶음 형제 포함)을 작업 공간 `stage_sheet_cells`(이번 이름 바꿈을 따라감)에 두고 세션
    `space_sheet_applied_v1` 를 올린다 — epoch 에 들어 같은 값으로 다듬어진 적용도 새 epoch 로 브라우저 칸을 비운다. 칸
    고침은 배치가 아니라 `moved_layout` 에 넣지 않는다(역할 찍기 · 가정 배치 글 없음). 저장 상자는 그 칸 가운데 지금도 저장본과
    다른 칸을 「호기 정보 칸 n건」 으로 세어 관문 · 머리 값 줄에 넣고(`changed_cell_count`), 「설비 마스터 다른 편집」 셈에서 뺀다
    (`other_change_count(skip=)`). 칸만 있는 저장도 리비전을 만드는 저장이라 메모 칸이 선다.
  - **층 사용 상태**(설비 `0029`, 2026-10-24 결정 S1~S6 — `load_floor_states`, 설비 시나리오와 무관한 공용 현행값). FAB 아래 층
    목록 자리는 `components/space_floor_list.py` 다(사용 층 표 + 접힌 「비활성 층 n개」, 표 머리 `사용 편집`). 비활성 층 블록은
    FAB 도면에서 회색 빗금 + 사유로 그려 눌러도·Enter 로도 열지 않는다(사유는 사람이 직접 적은 글 — 블록 안 줄은 8글자를
    넘으면 「…」 로 줄이고 풍선·선택 줄에는 다 싣는다, `editor.js` `clipOff`·`textContent` 만. 테는 흐린 글자색 굵은 점선이고
    사유 줄이 빠질 만큼 작은 블록은 이름 앞에 「⊘」 를 남긴다 — `blockTextLayout` 의 `off`, 390px 에서 사용 층과 갈리지
    않았다, 개선 I76) — 뷰어 epoch 에 상태
    지문(`floor_states_fingerprint`, 배율은 그대로)을 넣고 편집기 epoch 에는 넣지 않으며(적용 전 FAB 편집을 지킨다), 뷰어·편집기 `on_open` 은 그린 회차의
    비활성 층을 서버에서도 거른다(`_open_unless_inactive`). `층 바로 가기`·배치 편집기 `다른 층으로 보내기` 선택지는
    `selectable_floor_keys(keep=연 층)` 이다(글자는 「C1 3F」 그대로 — 상태는 배너). 주소 `?floor=` 가 비활성 층이어도 열고
    늘 서는 칸(`space_floor_inactive_notice_slot`)에 배너를 세운다(사유는 `literal_markdown`). 적용 검사(`parse_editor_apply(floors=ALL_FLOORS)`)·
    `valid_location_pairs`·`floor_placements` 는 30개 그대로이고, 목록이 줄기 전에 비활성 층으로 보낸 적용은 받고 flash 끝에
    알린다. FAB 요약은 모든 층 합 그대로에 「 · 비활성 층 n대」 를 붙인다.
- `app_pages/admin_area.py` — 사이드바 맨 아래 자기 상자의 운영 관리 화면으로 `Proc Rename`·`표시순서 관리`·
  `원천 품질` · `부대공정` · `공정 그룹` 다섯 탭(`TAB_NAMES` = `navigation.ADMIN_AREA_TABS`, `stateful_tabs`)을 모은다. 감사 기록이 켜진 서버의 개발자
  회차(`sso_identity.viewer_can_audit`)에만 여섯째 「접속 · 작업 기록」(`navigation.ADMIN_AREA_LOG_TAB` —
  `components/audit_log_view.py`)이 선다 — 다른 회차는 탭 다섯과 「부하 예외」 · 맨 끝 「공지」 그대로다(라벨 밖 세션 값은 첫 라벨로 새로 적는다, pop 없음).
  「공지」 바로 앞(기록 탭이 서면 그 바로 뒤) 「부하 예외」(`navigation.ADMIN_AREA_ROUTE_EXCEPTION_TAB` — `components/route_load_exception_admin.py`)는
  늘 서는 입력 탭(공정 고르기 칸)이라 닫혀 있어도 그리고(닫힌 회차는 공용 프로필 캐시만 — 판 이력 표는 열린 회차에만), DB 를 열지 못하면 열린 회차에
  「데이터 Error」 마크가 선다. 서수로 부르는 앞 여섯(넷째 「부대공정」 · 여섯째 기록 탭 — `extra_process_admin.TAB_LABEL = ADMIN_AREA_TABS[3]`)이
  그대로이게 `ADMIN_AREA_TABS` 밖 상수이고 페이지는 `opened_tabs[-2]` 로 받는다.
  맨 끝 「공지」(`navigation.ADMIN_AREA_NOTICE_TAB` — `components/notice_admin.py`, 2026-11-17 공지 보드 답 decided 2)는 Admin Area 를
  여는 회차마다 서는 입력 탭이라 닫혀 있어도 늘 그리고, DB 를 쓰지 않아 DB 를 열기 앞에서 그린다.
  탭 묶음은 DB 를 열기 **앞**이다(설계 AU20) — DB 를 못 열면 DB 를 쓰는 탭 가운데 열린 탭 안에만 「데이터 Error」 마크(`AD-07`)가 서고
  기록 탭 · 공지 탭은 열린다. 사이드바는 `ADMIN_AREA` 선언(`ConditionTabs` — 앞 다섯 탭과 「부하 예외」(고르는 공정 목록이 활성 리비전 소요기준)만
  시나리오 줄, 기록 탭만 「기록 조건」 카드, 공지 탭은 둘 다 없음)을 읽는다. 셋째는 `components/source_quality.py`, 넷째는 `components/extra_process_admin.py`,
  다섯째는 `components/process_group_editor.py`(활성 시나리오 `RQ_MODULE` 이 줄 — 편집 표라 닫혀 있어도 그리고 닫힌 회차는 공용 프로필 캐시만, 저장 벽은 `home.settings`)를 그린다. 계산 알림을
  모으는 탭은 두지 않는다 — 리비전마다 계산에서 빠진 행은 시나리오 관리 › 목록 관리 「점검」 이 센다(2026-11-11 입력 점검
  보드 q7 — 탭과 탭 이름 곁 수 표지를 함께 걷었다, 설계 규칙 7-1).
  - 앞 두 탭(입력 폼)은 늘 그린다. `원천 품질`(위젯 없는 표 — 원천 읽기에 캐시가 없다)과 `부대공정`(위젯이 단추 · 내려받기 · 확인
    칸뿐이라 버릴 값이 없다 — 판 이력 읽기에 캐시가 없다)은 닫혀 있으면 건너뛴다(`tab_is_hidden`, `tests/test_admin_area_page.py`) — 둘이
    Admin 회차의 DB 읽기라 열린 회차에만 DuckDB 를 연다. 조건 패널은 시나리오 줄만 선다.
  - 두 편집 탭의 붙여넣기 팝업 칸은 페이지에 하나(`components/admin_dialog.py`, 값 `PASTE_DIALOG` 가 탭을 가른다)다.
    「서버 시작 점검」 의 「토큰 넣기」 팝업(`components/bdq_token_admin.py` — 호스트 `DialogHost`)도 같은 칸을 값으로 쓴다.
  - 탭 위에는 C-DEP CD 서버에서만 「서버 시작 점검」 펼침(`components/container_start_check.py`)이 선다 — 결과 파일도
    CD 전용 환경변수도 없는 개발·사내 PC 에서는 아무것도 그리지 않는다. 그 펼침의 표 끝 「DuckDB 메모리 한도」 줄과 사실 줄 끝 메모리 값
    줄(RSS · 세션 · `cache_data` · DB 마다 DuckDB 회차 끝 표본 — `components/memory_diagnostic.py`)과 그 뒤 부하 값 줄 셋(화면 응답 · CPU 5분 평균 · 동시 세션 —
    `components/load_diagnostic.py`, 값은 `load_metrics`)은 이 프로세스의 지금 값이다. 그 뒤 `managed` 서버면 「DB 동기화」 펼침
    (`components/object_sync_status.py`), 그 뒤에 「통합인증 점검」 펼침(`components/sso_status.py`)이 선다 — 켜짐 · 막힘이거나 `APP_ENV=prod` 면(꺼짐이어도 「주소를 아는 사람은 누구나 들어옵니다」
    캡션과 「켜면 막힐 문제」) 그리고, 꺼짐이고 운영이 아니면 그리지 않는다. 알릴 조건(서버 시작 결과 없음 · 못 읽음 · 실패한 단계 `AD-01` — 토큰 줄 실패는 `AD-10` 몫, C-DEP 에서 `app.py` 가 개발자 몫(`admin_view.developer_notes_visible`)의 모든 화면 회차에 내고 이 펼침은 따로 내지 않는다(2026-11-14 보드 카드 p2-sync),
    운영인데 꺼짐 `AD-02` — 잠금 판정 앞에서 내 잠긴 회차에도 닿는다, 서명 인증서 만료 임박 `AD-03`, S3 명단을 읽지 못함 `AD-08`(할 일이 두 갈래 — 잠시 뒤 풀리는 까닭이면 「다시 읽기」, 다시 해도 같은 까닭이면 설정 · 권한 · 파일을 먼저 고침, `access_store.needs_admin_fix` — 보드 p0-unread) · 명단 파일이 없어 환경변수 첫 버전을 씀 `AD-09` · 새 스스로 등록(최근 30일 「새 등록 n명」) `AD-19` — 셋 다 그 명단을 쓰는 서버에서 앱 정보 카드가 개발자의 모든 화면 회차에 내고 「그 화면으로」 는 Admin Area 의 「접속 명단」 펼침까지(대상 `access_list` — 설계 규칙 UI-NAV-01), 2026-11-08 답 U4, BigDataQuery 토큰 실패 `AD-10` · 만료 1시간 전 `AD-11` · 자동 로그인 멈춤 `AD-23`(`AD-17` · `AD-18` 은 걷은 번호) — C-DEP 에서 `app.py` 가 시작 점검 알림 `AD-01` 뒤에 개발자의 모든 화면 회차에 낸다, 코어 화면의 처리 못 한 오류 `AD-22` — 같은 서버에서 `app.py` 가 토큰 알림 뒤에 내고 「그 화면으로」 는 그 화면, 서버 부하가 신호표 문턱(화면 응답 느린 쪽 3초 · CPU 5분 평균 0.7코어 · 연결 25)을 넘음 `AD-26` — 같은 서버에서 `app.py` 가 `AD-22` 뒤에 내고 지문은 넘은 문턱 이름, 「그 화면으로」 는 이 펼침까지, 로그인 갱신이 출처 · 머리 검사에서만 거절됨(기동 뒤 「출처·머리 거절」 1 이상 · 「다시 발급」 · 「건너뜀」 0) `AD-21` — 통합인증이 켜진 서버의 앱 정보 카드가 개발자의 모든 화면 회차에 내고(`components/sso_refresh_alert.py` — 지문은 고정 값, 다른 회차는 글 없는 해소) 「그 화면으로」 는 Admin 「통합인증 점검」 펼침까지 — 대상 `sso_status`)은 펼침 안 캡션과 함께 상태 알림으로 낸다(9장 「알림 칸」 — 상태 줄 ·
    점검 펼침). 편 상태는 기억 칸(`remembered_expander`)이라
    다른 화면에 다녀와도 접히지 않는다. 그 바로 뒤에 「접속 명단」 펼침(`components/access_list_admin.py`)이 개발자 회차에만 선다.
    「서버 시작 점검」 바로 뒤에는 `managed` + 키(`CAPA_BDQ_SECRET_KEY`) 서버의 개발자 회차에만 「BDQ 자동 로그인」 펼침
    (`components/bdq_login_admin.py` — 계정 넣기 · 지우기 · 상태 줄)이 선다. 예비 「토큰 넣기」 는 「서버 시작 점검」 펼침 안 그대로다.
  - 「모듈 상태」(`components/module_status.py`)는 탭 위 펼침이 아니라 안쪽 탭 줄 오른쪽 끝 팝오버다(2026-11-10 보드 Q-6 — T7 과
    같은 꼴, 설계 규칙 UI-LAY-13). 세 탭은 칸 `TABS_BOX_KEY` 안이고, 그 칸을 DB 를 열기 전에 세워 맨 앞에 `render_module_status(
    box_key=TABS_BOX_KEY)` 를 부른다 — 서식이 단추 칸을 그 칸 오른쪽 위에 절대 위치로 얹고 탭 줄은 그 폭만큼 오른쪽을 비운다(새 줄
    없음). DB 를 못 열어 멈추는 회차(`AD-07`)에도 탭 묶음이 그 칸에 서고 단추는 탭 줄 끝이다.
  - 거래선 정렬은 따로 없다 — `표시순서 관리` 에 `분류컬럼 = Customer` 규칙을 넣는다. 설명은 `guides/admin_area.md`.
- `app_pages/internal_modules.py` — 사이드바 「모듈」 상자의 머리(현황 요약) — 켜진 모듈과 화면 링크, 꺼짐·실패 수. 켜진 모듈이 없으면 상자가 없다(주소로는 열린다). 설명은 `guides/internal_modules.md`.
- `app_pages/voc.py` — `Admin Area` 아래의 자유 게시판(질문·개선 요청·오류 신고와 답글)이다.
  - 계산에 닿지 않는다 — 시나리오·조회기간을 읽지 않고 `load_page_context()` 를 부르지 않는다.
  - 본문·답글은 `st.text` 로 그리고 게시판 읽기는 캐시하지 않는다. 폼은 `clear_on_submit` 없이 콜백이 성공한
    때만 비우고 작성자 이름은 폼 밖이다. 필터는 조건 카드 `VOC 필터`, 설명은 `guides/voc.md`.
  - 새 글 폼의 제목·내용은 올리기 전에는 서버가 몰라 화면 이동·테마 전환(새로고침)에 사라졌다 — 폼 바로 뒤(폼과 간격
    없는 한 칸 — 높이 0 컴포넌트가 따로 서면 세로 간격을 한 칸 더 먹는다)의 `components/voc_draft_keeper.py`(Components v2, 그림자 DOM 없음)가 두 칸(`st-key-voc_post_title`·`_body`)의 글을
    브라우저 탭(`sessionStorage` — 서버·다른 사람에게 가지 않음)에 적고, 두 칸이 모두 빈 회차에 되살려(원래 setter +
    `input` 사건 — 폼 안이라 올릴 때 간다) 알림 칸에 사건 알림 `VO-02` 를 낸다(`window.__capaAlerts.raise` — 화면
    탭 줄 JS 와 같은 길, 폼 아래 제 꼴의 줄 없음 — 설계 규칙 UI-NTF-01). 같은 세션 표지(세션마다 새로 뽑음)에서 폼 세대가 오르면(글을
    올렸다) 버린다. 판정은 순수 구획 `// <voc-draft>`(node 시험 `tests/test_voc_draft_keeper.py`), AppTest 는 conftest
    대역(개선 I84). 같은 모듈이 적어 둔 답변 키 `KEPT_REPLY_KEY` · `kept_reply_count`(화면 탭 점 · 머리 변경 칩 keep 묶음 ·
    테마 · 떠나기 확인 표지의 판정)도 맡는다.
  - 쓰기(새 글·답변·답변 완료 표시·글 삭제)는 모두 콜백이고 본문 `st.rerun()` 이 없다 — 끊긴 회차가 아래 글의
    「삭제 확인」 값을 버려 단추가 사라졌다. 새 글·답변 폼과 답변 완료 단추는 key 세대, 글 삭제는 지운 글 id 로
    빠른 두 번 누름을 거른다(9장, `tests/test_voc_page.py`). 세대 비교와 쓰기는 `components/write_guard.write_once` 라
    두 회차에 겹쳐 오는 더블클릭도 같은 입력(지문 — 분류·제목·내용·작성자)이면 한 번만 쓴다 — 입력은 그 앞에서 읽고
    세대 올리기는 뒷정리의 맨 끝이다. 쓴 뒤 끊긴 회차 다음에 글을 고쳐 누른 올리기는 지문이 달라 새로 올린다. 느린 두 번
    누름이 방금 비운 새 폼에 닿은 빈 제출은 `write_guard.just_written` 으로 걸러 성공을 다시 알린다. 아주 빠른 둘째
    누름이 옛 화면의 단추에 닿은 회차(지나간 세대·이미 지운 글)도 쓰기 직후면 성공을 다시 알린다(9장).
  - 그 사이 다른 세션이 지운 글의 답변·답변 완료 표시는 저장소가 같은 쓰기 잠금 안에서 글을 확인해
    `VocPostGoneError` 로 거절한다(`voc_reply.post_id` 에 외래 키가 없어 막지 않으면 주인 없는 답글이 남는다).
    아무것도 쓰지 않았고 그 자리에 고칠 입력이 없어(지운 글 상자는 다시 그리지 않는다) 거절은 알림창 · Alarm 에만
    낸다(`voc._refuse_gone_press` — `queue_flash(…, popup_only=True)`, `FL-03`, 설계 규칙 UI-NTF-03). 적어 둔 답변은
    알림이 아니라 사용자의 글이라 머리 알림 칸에 남겨 복사해 가게 한다(세션 칸 `voc_kept_reply` — 거절된 차례의 글 튜플).
    「닫기」(`voc_kept_reply_close` — 되돌릴 수 없어 풍선)까지 다른 글 처리 · 작성자 변경 · 화면 이동에도 남고, 또 거절되면 빈
    줄 하나로 이어 붙이며 겹쳐 온 같은 글은 붙이지 않는다. 답변을 적어 둔 거절의 알림은 그 자리를 말한다(「적어 둔 답변은
    화면 맨 위에 둡니다.」 — `SHORT_LIMIT` 안). 남지 못한 답변은 그 회차에 글 상자가 설 때만 곁 칸(`POST_ERROR_KEY`)이다 —
    저장소는 입력(작성자 빈칸)을 글 확인보다 먼저 봐 지운 글의 거절도 입력 거절로 오므로 화면이 다시 가른다
    (`voc._refuse_reply`): 글이 지워졌으면 `_refuse_gone_press`(`FL-03`), 글은 있는데 VOC 필터에서 빠졌거나 목록을 못 읽으면
    `_refuse_boxless_reply`(`FL-04`, `popup_only`)로 알리고 적은 글은 「적어 둔 답변」 에 둔다. 필터 판정은 본문과 콜백이
    `_filtered_posts` 하나를 쓴다. 적어 둔 답변은 세션 칸이라 새로고침 · 테마 전환 · 탭 닫기에 사라진다
    — 그래서 화면 탭 VOC 주황 점 · 머리 변경 칩 「저장 안 함」 · 테마 단추와 떠나기 확인 표지에 든다(키 `KEPT_REPLY_KEY` 와 판정
    `kept_reply_count` 는 `components/voc_draft_keeper.py`, 2026-11-08 답 X1) (`tests/test_voc_page.py`). 「답변 완료로 표시」 ·
    「미답변으로 되돌리기」 는 알림창에 결과를 낸다(작은 결정 a2). 옛 화면의 「글
    삭제」 도 같다 — 저장소 `remove_voc_post` 가 지울 것이 없었으면 거짓을 돌려주고 화면은 「글을 지웠습니다.」 대신
    「그 사이 지운 글입니다」(`VOC_POST_GONE_ON_DELETE`)를 알림창 · Alarm 에 낸다. 쓰기 직후 창 안이면(`held_notice` —
    겹쳐 온 제 누름이 먼저 지웠다) 그 알림 그대로다.
  - 글 상자 라벨의 제목·작성자와 답글 caption 의 작성자는 마크다운으로 그려지는 자리라
    `components/literal_markdown.py` 로 ASCII 구두점을 escape 해 적은 글자 그대로 싣는다(`tests/test_voc_page.py`).
- `app_pages/scenario_management.py` — `Capa 시나리오`·`설비 시나리오`·`DB 등록`·`자동 갱신` 탭 넷으로 시나리오 목록·복제·월
  머지·연도 Shift·설비 시나리오·원천 등록·자동 갱신을 맡는다. 설명은 `guides/scenario_management.md`.
  - 탭 묶음은 `stateful_tabs`(`SCENARIO_MANAGEMENT_TABS_KEY`)이고 Capa 시나리오 · DB 등록 · 자동 갱신은 늘 그린다(form 입력 보존 — 설비
    탭이 열린 회차에 숨은 Capa 본문은 24~41ms, 샘플 관측 — 그 값은 페이지 주석). 「설비 시나리오」 탭(`equipment_scenario_management.render_equipment_scenario_section`)만 그 탭이 열린 회차에 그린다
    — 설비 DB 를 여는 것은 그 회차뿐이고(`tab.open`, `tests/test_equipment_scenario_screens.py`) 못 읽으면 그 탭 안에서만 알린다. 대가로 그
    탭 입력 칸에 적던 글은 다른 탭으로 옮기면 버려진다(작업 전환과 같은 성질 — Guide 도 그렇게 적는다). 목록·리비전 편집표의 미저장
    편집은 위젯이 아니라 행 id 초안이라 탭을 오가도 남는다. 다른 화면에서 그 탭으로 데려가는 길은 단추와 `scenario_management_tabs.open_scenario_management_tab`
    이다 — 기억 칸만 적어 그 탭을 연다(옛 배포 흔적 경고의 단추는 설비 시나리오, 시나리오 팝업의 두 단추는 Capa 시나리오). 링크는 기억된 탭을 여니 특정 탭을 가리키는 길에 쓰지
    않는다. 탭 이름과 알림의 `tab`(`*_TAB_NAME`)도 그 모듈 한 곳이고, 탭 본문의 오류 알림(`SC-02`)과 변경 칩 「목록 편집 저장 안 함」 은 제 탭 이름을 싣는다(`tests/test_scenario_management_tabs.py`). 옛 세션의 목록 밖 탭 값은 Streamlit 이 첫 탭으로 되돌린다. 이 화면에는 사이드바 설비
    시나리오 줄이 서지 않는다(시나리오 표 「올라와 있음」 칸 「● rN」 과 세션 알림 — 탭 머리 줄은 없다). 그 탭이 닫힌 회차에는 세션을 풀지 않으므로 세션 이동 알림(`SB-14`)은
    그 탭을 여는 회차에 뜬다. 설비 DB 핀을 선언하지만(`uses_equipment_db`) 게으른 핀이라 다른 탭을 보는 회차에는 열지 않는다.
  - Capa 시나리오 탭 맨 위에 작업 전환(목록 관리 · 복제 · 월 머지 · 연도 Shift — 보이는 글 없음, 접근성 라벨 「시나리오 작업」)이
    바로 선다. 옛 세션의 작업 이름은 위젯 앞에서 버린다. 지금 올라와 있는 리비전과 공식 표지는 사이드바 시나리오 칸 · 머리 띠, 최신
    공식은 목록 표 `공식버전` 칸 · 오른쪽 「공식 이력」 이 말한다. 공식버전 없음은 상태 알림 `SC-01` — 활성 시나리오가 0건이고
    보관본만 있으면 글을 갈라 보관함 › 「되돌리기」 를 가리킨다(내용 값 `archived_only` — 검수 보드 st-sc01, 작은 결정 a8 과 같은 꼴).
    시나리오가 하나도 없으면(보관본도 없음 — 빈 디스크로 뜬 운영 서버) 글을 갈라 「DB 등록」 을 가리키고 「그 화면으로」 가 그 탭을
    연다(내용 값 `empty` — 2026-11-14 물음 보드 seed (nopub), 계산 화면의 `no_revision_message` 와 같은 판정).
    표지는 불러온 리비전 없이 멈춘 계산 화면과 한 벌(`page_bootstrap.missing_official_note`)이라 어느 화면이 내도 Alarm 줄 하나 ·
    알림창 한 번이고, 해소는 공식버전을 확인한 회차의 알림 칸 data 가 낸다(2026-11-14 물음 보드 decided 5). 글의 할 일 절은 화면 등급마다
    그 등급에 있는 단추만 가리킨다 — 「공식으로 지정…」 은 관리자부터, DB 등록 · 「되돌리기」 는 실무자부터, 열람은 「공식 지정은 관리자부터」 뿐이고
    「그 화면으로」 가 DB 등록 탭이 아니라 Capa 시나리오다(UI-INP-07 예외 — 지문은 같다).
  - 시나리오 · 리비전 ID 를 보이는 전용 칸 · 값 줄은 두지 않는다(Admin Area 에도 두지 않는다) — 장애 신고 · 문의는 시나리오 이름 + rN 으로 가리킨다. 파생 작업(월 머지 · 연도 Shift · 부대공정 얹기)의 「저장될 출처 메모」 · 변경 메모 글은 원본 ID 를 싣는다(`components/scenario_transform.source_description`).
  - 목록 관리는 안 3(2026-11-06 사용자 결정 — 옛 C안의 편집표 둘 · 카드를 대신한다)이다 — 설비 마스터와 같은 두 칸 틀(`components/side_panel.py`) 안 왼쪽 시나리오
    표(브라우저 표 `components/scenario_list_grid.py` — 손잡이 · 순서 · 시나리오명 · 최신 · 공식버전 · 최근 수정), 오른쪽 칸 「상세 · 점검 · 저장 전 변경 · 공식 이력 · 보관함」(점검은 `components/scenario_input_check.py`).
    상세는 리비전 표(r · 리비전명 · 상태)가 맨 위에 서서 머리가 왼쪽 표 머리와 윗선이 같고(사용자 요청 2026-11-07), 그 아래 연 시나리오의 제목 · 원천 코드 · 최근 수정과 고른 리비전의 값 줄(메모 · 저장일 · 부모 — 같은 마운트가 그려 줄을 누르면 회차 전에 바뀐다), 「선택한 리비전 불러오기」 ·
    「공식으로 지정…」(확인 팝업 `OFFICIAL_DIALOG_KEY`) · 「보관…」. 저장 전 변경은 수 넷 · 옛 값 → 새 값 · 줄 되돌리기 · 「모두 버리기」(확인 팝오버) · 「변경 저장」 **한 곳**.
    고침은 행 id 초안이다(`services/scenario_list_edits.ListDraft`, 세션 칸 `components/scenario_list_state.py`) — 리비전명 고침은 리비전 id 라 다른 시나리오를 열어도
    남는다. 이동 단추가 표 안으로 들어가고 저장 단추 풍선을 걷어 「이동 단추 풍선이 떠 있는 채 남는」 꼴이 없다.
    표 카드 단추 key 에 시나리오 id 를 싣는다(`CARD_LOAD_KEY` · `CARD_OFFICIAL_KEY`) — 다른 줄을 연 회차가 서버에서 끝난 뒤 브라우저의 옛 카드 단추에 닿은 누름은 옛 key 의 콜백으로 돌아 옛
    시나리오를 인자로 받아 대조(`OPENED_MOVED_MESSAGE`)에 걸린다. 고정 key 면 새 시나리오 인자로 돌아 대조를 지나 그 시나리오를 올린다(불러오기에는 확인 팝업이 없다).
  - 목록 관리 두 칸은 편집기 구역이다(`scenario_list_state.LIST_SCOPE` — `_render_list_scope`, 9장 「구역 회차 규칙」). 줄 고르기 · 이름 · 차례 고침 ·
    오른쪽 칸 안 조작은 앱 전체가 아니라 그 구역만 돌고 사이드바 · 머리 띠 · 숨은 탭(설비 시나리오 · DB 등록 · 자동 갱신)은 그 회차에 돌지 않는다.
    앱 전체 회차는 탭 머리가 맨 위 알림 앞에서 맞춘 재료를 스레드 칸(`_HANDOFF`)으로 넘겨 쓰고(구역 인자로 넘기지 않는다 — R3), 구역 회차는 출납을
    접고 저장본에 다시 맞춘다(`_settle_in_scope` — 남의 보관 · 이름 바꿈은 `reconcile`, 남의 공식 지정은 최신 공식 번호로 안다). 구역 회차는 `app.py`
    의 실행 핀 밖이라 구역 본문이 DB 핀(`pinned_connections`)을 스스로 잡는다 — 그 회차의 읽기가 인스턴스 하나를 나눠 쓴다. 구역 회차에 목록을 읽지
    못하면(`BOOTSTRAP_ERRORS` — 잠깐의 잠금 포함) 올리지 않고 코어 화면 카드(R6)가 그 구역 자리에 서서 멈춤으로 끝난다 — 멈춘 회차는 서버 세션에서
    그리지 못한 구역 위젯의 출납 상태 값을 지우지 않아 받은 op 가 세션에 남는다. 브라우저는 그 구역에서 다시 그리지 않은 목록 마운트를 걷어 다음에 표를
    그리는 회차에 새 마운트로 세우므로 옛 마운트 op 의 ack 는 받을 부품이 없다(9장 R6 — 「카드 + 멈춤이면 ack 가 산다」 에 기대지 않는다). 구역 위젯을
    그리기 전 올리기는 R1 금지다(서버 세션의 그 값마저 지운다). 머리 표지(`_list_head`)는
    고침 있음/없음 · 알약 있음/없음과 최신 공식 번호 · 이 회차의 오른쪽 칸 · 올라와 있는 시나리오 · 리비전 · 맨 위 알림 칸이 낼 결과 알림이다 — 바뀌면
    콜백 끝(받기 · 변경 저장 · 모두 버리기 · 불러오기 · 공식 지정 열기)이나 본문 뒤(오른쪽 칸 고르기)에서 앱 전체로 올린다. 「점검」 칸 「그 화면으로」
    는 늘 올린다(탭 · 화면 · 사이드바 팝업 — `scenario_input_check._go`). 「저장 전 변경 n건」 알약은 구역이 「시나리오 작업」 줄의 바깥 칸에 쓴다
    (`_render_badge` — 앱 전체 회차가 그린 칸에만, 서고 사라짐은 앱 전체 회차). 공식 지정 · 「넓게 보기」 팝업은 구역 회차의 누름이어도 호스트만
    돌고(`_open_host` — 2026-11-08 U5), 호스트만 돌 수 없으면 콜백 끝에서 올린다. 오른쪽 칸 본문은 칸 · 갈래와 상관없이 이벤트 칸 한 자리다
    (`SIDE_EVENT_FILLER`, R5). 보관 · 되돌리기 · 영구 삭제의 본문 `st.rerun()` 은 앱 전체 회차다. 시험은 `tests/test_scenario_list_scope.py`.
  - 「점검」 칸(2026-11-11 입력 점검 보드 q1 ~ q7)은 고른 리비전 하나의 계산에서 빠진 행을 묶음으로 센다(`components/scenario_input_check.py` ·
    `services/revision_input_check.py`). 오른쪽 칸 갈래는 이름으로 가른다(`SIDES` 다섯 — 끝 갈래도 `SIDE_ARCHIVE` 로 묻는다). 「상세」 · 「점검」 은 같은
    씨앗 머리(`_opened_revisions` — `ACTION_OWNER_KEY` · `REVISION_SEED_KEY` · `_seed_revision_pick`)와 같은 `ListDraft.picked` 를 쓰고, 「점검」 은
    전용 리비전 표 마운트(`CHECKS_KEY`)에 「계산」 칸을 단다(상세 표에는 칸을 더하지 않는다). 셈은 그 칸이 선 회차에 고른 리비전만이다 — Capa 시나리오
    탭이 닫힌 회차(`counting=False`)와 「상세」 칸 고름은 세지 않는다(UI-PRF-01). 다른 줄을 열어도 「점검」 · 「저장 전 변경」 칸은 그대로다(`_fold_outboxes`,
    `to_detail` 만 「상세」). 「넓게 보기」 팝업은 공식 지정 팝업과 같은 호스트(`OFFICIAL_HOST`)를 열림 값의 꼴로 가르고(`wide_target` — 다섯 칸 튜플,
    입력 위젯 없음, 칸이 그 단추를 그리는 동안만 남는다), 점검 결과 칸(`CHECK_NOTICE_KEY`)은 칸이 안 서는 회차에 `_notices_without_a_place` 가 꺼낸다.
  - 저장은 콜백이고 하나라도 거부되면 아무것도 쓰지 않는다(`apply_scenario_list_edits(revision_renames=)` — 한 쓰기 트랜잭션, `BatchEditRefused`, 거부는 「변경 저장」
    바로 아래 칸). 차례: 출납 접기 → 지문(저장본에 맞추기 **앞** 초안 — `draft_fingerprint`) → `save_once` 안에서 지금 값 읽기 · 맞추기 · 쓰기 → 표지 → 후속(`_after_list_save`) → 세대 올리기.
    첫 콜백이 쓴 뒤 끊겨도 같은 지문의 둘째 누름이 저장소에 다시 가지 않고 뒷정리를 잇고, 창이 지났으면 맞추기가 낸 「같아진 고침」(`Reconciled.settled`) 이 제 저장 짝일 때 뒷정리한다 —
    머리 띠 이름표가 옛 이름으로 남지 않는다. 이름은 비교 후 쓰기, 순서는 처음 옮길 때의 저장 차례와 지금 차례가 같을 때만 쓴다.
    목록 차례는 `list_order NULLS LAST, created_at DESC`(`repository._SCENARIO_LIST_ORDER`, 목록과 저장 대조가 같은 글)다 —
    순서를 저장한 적 없는 행은 만든 시각 차례라 이름 변경·새 리비전 저장(「최근 수정」)으로 움직이지 않고 새 시나리오는
    맨 위에 선다. 이름만 바꾼 「변경 저장」은 `list_order` 를 쓰지 않는다(쓰면 그 뒤 새 시나리오가 맨 아래로 간다 —
    `tests/test_scenario_list_edits.py`).
  - 이름의 비교 대상은 그 칸을 처음 고칠 때 **브라우저가 든** 이름(`NameEdit.seen`)이다 — 마지막 회차에 다시 읽은 이름과 대조하면 남이 먼저 바꾼 뒤 회차가 한 번만 돌아도 대조가
    통과해 남의 이름을 덮었다(2026-10-22 리뷰). 먼저 바뀐 이름은 저장 전에 그 칸 막힘 · 풍선 · 「막힘」 수로 보이고(`list_problems` — 저장소와 같은 판정 · 같은 글, 표 아래 경고 상자 없음),
    거부되면 그 줄의 고침만 빼(`without_edits`, `BatchEditRefused.moved_names`) 지금 이름을 다시 보인다.
  - 결과 알림 칸(`LIST_NOTICE_KEY` · `CARD_NOTICE_KEY`)은 그 칸이 선 회차에만 그려지므로, 안 서는 쪽 키는 맨 위 칸이 알림창 · Alarm 으로 꺼낸다(`_notices_without_a_place` — 칸이 옮겨도 거부 · 성공이
    잠자지 않는다). 사라진 고침 알림은 맨 위 알림 **앞**에서 맞춰 그 회차에 뜨고, 콜백이 본문보다 먼저 맞춘 「변경 저장」 은 저장 콜백이 같은 글을 낸다(`_warn_gone`). 이 세션의 보관 · 되돌리기 · 삭제는 쓰기 전에 그 시나리오의 리비전 id 를 읽어 고침을 말없이 빼고
    순서 고침의 본 차례를 옮긴다(`_draft_settler`). 이 세션이 시나리오를 더한 길(복제 · 월 머지 · 연도 Shift · DB 등록)도 본 차례를 옮긴다(`scenario_list_state.follow_created_scenario` — 그 줄을 빼면 본 차례와 같을 때만, 남이 바꾼 차례는 그대로 막힌다).
    「자동 갱신」 탭의 「지금 실행」 은 예약 회차와 같은 함수라 옮기지 않는다(「다른 곳에서」 로 막힌다).
  - 어긋난 누름은 하지 않고 그 자리에 알린다 — 옛 카드 「선택한 리비전 불러오기」 는 지금 목록 · 고른 리비전의 소속을 다시 보고, 옛 카드 「공식으로 지정…」 은 다음 그리기가 팝업 칸을 비우며 알린다(`_refuse_stale_official_press`). 보관 확인 체크 key 는 시나리오마다다(`archive_confirm_key`) — 칸을 지워도 브라우저가 옛 값을 다시 보낸다. 「모두 버리기」 는 버릴 것이 없으면 세대를 올리지 않는다.
  - 새 리비전 저장은 사이드바 시나리오 팝업 한 곳이다 — 이 페이지에는 「리비전 저장」 모드가 없고 그 길은 Guide 가
    말한다(모드 줄 아래 길 안내 줄은 두지 않는다 — 설계 규칙 UI-TXT-03).
  - `자동 갱신`(`components/auto_official_update_tab.py`)과 BigDataQuery 사내 조회는 버튼을 누른 회차에만 돈다. 자동 갱신
    탭은 「지금 상태」 칸부터 선다(소제목 없음). 닫힌 탭의 읽기 실패는 마크 · 알림을 내지 않고(`_report_read_failure` 한 길),
    공식버전이 없으면 값 줄 「현재 공식버전 · 없음」 이다(g2-22). 닫힌 탭(`alert_tab` None)은 탭 맨 끝 설정 변경 기록만
    읽지도 그리지도 않는다 — 「지금 상태」 의 DB 값 줄(다음 실행 · 현재 공식버전)은 설정 칸 · 「지금 실행」 **위**라 닫힌 탭에도
    읽어 그리고(9장 숨은 탭 규칙 — 입력 위의 표는 건너뛰지 않는다), 실행 기록도 「off 공정 목록」 접는 상자의 펼침이 남게 그린다.
    회차 안의 BigDataQuery 조회 실패는 「마지막 확인」 이 아니라 실행 기록 「사유」 칸에 남으므로(`_RunLog.fail`) 그 칸도 「마지막 확인」 과
    같이 `grade_hooks.diagnostic_message` 를 지난다 — 개발자가 아니면 앞머리와 갈래 · 할 일만(「경고」 칸은 원문 사유로 가른다, 시험
    `test_a_bigdataquery_failed_round_reason_follows_the_developer_view`).
    보관은 숨길 뿐 파일을 줄이지 않는다(회수는 영구 삭제 뒤 `scripts/compact_duckdb.py`).
  - 월 머지·연도 Shift 는 원본을 바꾸지 않고 새 시나리오로 저장하며 `capacity_gate` 파생 검사를 먼저 돈다. 무월 표
    규칙은 `scenario_month_merge.NON_MONTHLY_SUPPLEMENT_KEYS` 한 곳이다(`docs/scenario_merge_shift_implementation.md`).
    Chip 두 표의 보충 키는 부품 단위(`SUPPLEMENT_PRODUCT_KEYS` — 제품정보 · Stack · CUSTOM)이고 계획 결손 점검
    `plan_key_gaps` 도 같은 키다 — 머지는 부품을 다시 짝짓지 않아 옛 리비전(빈 값 표지)과 부품 값이 있는 리비전을 섞으면
    결손으로 드러난다. 결손 줄의 「제품 n개」 는 부품을 접어 제품(제품정보 · Stack)을 센다(`PlanKeyGap.products`) — 키 예시는
    부품마다다. 겹침은 고를 칸 곁 값 하나이고 합치기 거부는 그 칸 바로 아래에 선다(표 뒤면 첫 화면 밖이다). 빈 달 · 가상/실제 섞임은 값 줄(뜻은
    풍선)이고, 막힌 동안에도 저장 칸은 잠긴 단추로 남는다(`_render_locked_save`). 부대공정도 값 줄 둘이다 — 「부대공정 판 섞임」(두
    원본이 다른 판 — 저장 뒤 「부대공정 얹기」 로 맞춤)과 「부대공정 · BDQ 행 섞임」(한 원본 달은 판 행 · 다른 원본 달은 BDQ 행 —
    `extra_process_merge.month_merge_mixing`, 설계 A14 · D20). 뒤의 것은 저장 출처를 섞임 뺌 줄로 접어(`carried_extra_process(mixed=…)`)
    얹기가 그 공정을 걷지 않게 하고, 덧붙인 쪽 출처 메모에 달 범위를 적는다.
  - 가상 제품 이력이 있는 리비전의 공식 지정은 폼 밖 확인 체크를 받는다(CLI 는 `--allow-virtual-products` —
    `scripts/bootstrap_initial_duckdb_scenario.py`·`tests/test_bootstrap_initial_duckdb_scenario.py`).
- `app_pages/standard_target_capa.py` — Static 하위에서 월간 공정별 대당 Capa 를 일로 풀고 주차별 가용대수를 곱한
  일 표준 가능량을 표·로직 분석·CSV 로 낸다(조건 카드 `표준 목표 조건`, 설명 `guides/standard_target_capa.md`). 「가용설비
  붙여넣기」 는 화면 팝업 호스트 `standard_target_dialog_host`(`DialogHost`)가 부르고(답 U5 — 여닫아도 다시 계산하지 않는다),
  「입력 초기화」 는 같은 열림 칸으로 페이지가 부른다. 「예외 처리 공정」 의 현재 조회범위 제외 행 수는 공정 칸 머리 풍선
  (`exception_process_help` — 작은 결정 d8)이다. 「표시 항목」 줄 오른쪽 끝 작업 단추 칸(`ACTION_ROW_KEY`)에 양식 단추가
  없다 — 양식은 붙여넣기 창 한 곳이고 `template_csv` 는 창을 연 회차에만 짓는다.
  - 주차 계산은 `simulation_cache.get_weekly_standard_target_capacity`(PKG `get_pkg_equivalent_standard_target`)가
    키만 해시한다 — 소요대수를 해시 인자로 넘기지 않는다(`tests/test_standard_target_weekly_cache.py`). 재공 현황도
    제품 선택을 키에 실어 같은 캐시를 부른다.
  - 공정 필터는 전체 공정 결과(`get_standard_target_weekly_result`)를 거르고, 전체 계산 실패·공백 공정명·빈 결과일
    때만 고른 공정만 계산한다. 결과와 무관한 조작은 소요대수를 다시 풀지 않는다(`get_standard_target_split`).
  - 이 캐시들은 프로세스 전역이라 화면 테스트가 테스트마다 비운다(`tests/test_standard_target_capa_page.py`).
  - 저장된 주차별 가용설비가 0건이면 가용대수를 곱하는 표시 항목(`AVAILABILITY_BASED_METRICS` — 일 표준 가능량·가용대수)만
    빈 결과 평문 한 줄(`AVAILABILITY_EMPTY` — 넣는 곳은 Guide)로 멈추고, 지울 것이 없는 `입력 초기화` 는 잠긴 채 까닭 풍선이다. 대당 일 Capa·로직 분석은 그대로 선다 — 계산(`build_weekly_standard_target_capacity`)은 빈
    가용설비를 가용대수 빈칸으로 받는다(「행이 없습니다」 거절은 붙여넣기·저장 경로의 몫).
  - 가용대수가 없어 빈칸인 공정·주차는 상태 알림 `ST-17`(범위 = 활성 리비전 + 조회일, 내용 = (공정, 주차) 목록)이고
    목록은 그 알림에 딸린 표 「누락 공정·주차」(2026-11-05 사용자 요청(검수표) — 화면은 표시명, CSV 는 원본)다. 표시명이 입혀진
    동안 그 표의 공정 칸 머리 풍선이 붙여넣기에는 원본 공정명(CSV 양식)을 쓴다고 말한다. 표가 `alerts.TABLE_ROW_LIMIT` 를
    넘을 때만 결과 상자 안 늘 서 있는 칸(`availability_notice_slot`)에 「누락 공정·주차 확인」 펼침이 선다.
  - 붙여넣기 · 입력 초기화 팝업은 공통 부품(`components/paste_form` — 9장 「붙여넣기 · 양식 창」)이다 — 덮어쓰는 규칙과
    되돌릴 수 없다는 것은 창을 연 회차의 알림 `PA-01`(`PASTE_OPENING` · `CLEAR_OPENING`)이고 창 안에는 글 · 칸 풍선이 없다
    (설계 규칙 UI-TXT-01 · UI-NTF-09, 2026-11-05 검수 static-37). 로직 분석의 일곱 칸은 앞 칸이 빌 때 잠기고 까닭 풍선을 달며,
    다 고르기 전에는 빈 결과 한 줄(`LOGIC_EMPTY`)이다.
  - 「제품·WF 속성별 Mix 산출 근거」 표 위 캡션 「`●` 선택한 분류」 는 표의 ● 하나만 말하는 표지 한 줄이라 늘 서는 설명 줄 걷기(UI-TXT-01) 밖이고 그 자리에 남긴다 — 조화가중으로 읽는 법은 Guide 몫이다(UI-TXT-04).
  - 로직 분석 식 세 줄(대당 Capa·대당 일 Capa·일 표준 가능량)도 **적힌 수로 다시 셈해도 적힌 결과**가 나와야 한다(제약
    시뮬레이션 고른 달 계산과 같은 규칙) — 결과는 원값의 둘째 자리 그대로 두고, 깎은 인수로 어긋날 때만 더 적는 자리 수의 합이
    가장 작게(같으면 오른 인수 먼저) 인수를 한 자리씩, 여섯째 자리까지 더 적는다(`formula_text.consistent_places` — 「54,698.63
    ÷ 1.49386 = 36,615.63」, 2026-10-26 E2E 3회차에 「÷ 1.49」 로 0.26% 어긋났다). 그래도 못 맞추면 처음 자리로 적고 등호를
    「≈」 로 둔다(8장 「화면 숫자는 검산되어야 한다」). 세 줄 글은 같은 파일의 순수 함수 `logic_formula_text`(줄 하나는
    `_formula_line`)가 짓고, 인수 글자 꼴(`_operand_text` — `_format_metric` 자리, 늘린 자리의 뒤 0 은 뗀다)과 적힌 글자로
    다시 셈하기(`_recomputed`, `Decimal`)는 이 화면 것이라 페이지에 둔다.
- `src/capa_simulation/components/paste_form.py` (+ `paste_window_assets/` CSS · JS) — 잠긴 적용은 감싼 칸이 탭 자리 · `aria-label` 을 맡아 풍선이 `:focus-visible` 로도 선다. 붙여넣기 · 양식 창의 공통 부품(9장
  「붙여넣기 · 양식 창」). 글 칸(`paste_text_area`) · 창 제목 옆 작업 줄(`paste_action_row` — 왼쪽 적용 · 오른쪽 양식) · 창 크기와 「적용」 잠금을 맡는 숨은
  컴포넌트(`render_paste_window`) · 창을 연 회차의 알림(`announce_on_open`) · 거부 · 안내(`refuse_paste` · `tell_paste`)와 이를
  묶은 본문 `render_paste_form`. 빈 칸 까닭 풍선은 `empty_why` 로 창마다 줄 수 있다(기본 `PASTE_EMPTY_WHY` — 제 글을 쓰던 접속
  명단 추가 창은 2026-11-18 편집 표로 걷었다). 판정 구획(`// <paste-window-core>`)은 node 로 떼어 시험한다(`tests/test_paste_form.py`).
- `src/capa_simulation/components/reference_csv_tools.py` — 입력 RQ 월별 Wide 표의 UTF-8 CSV 양식 내려받기와 Excel
  붙여넣기 팝업 본문·적용 알림을 공통 제공한다(`render_reference_clipboard_form` 은 공통 부품 위에 양식 · 검증을 얹는다).
- `src/capa_simulation/components/horizontal_scrollbar.py` — HOME 월별 영역과 동기화되는 Components v2 가로 스크롤바다.
  - `initial_offset_px` 는 처음 그릴 때 한 번만 건다 — 적용 표시를 대상 요소의 `dataset` 에 남겨 리런이 사용자가
    옮긴 위치를 되돌리지 않게 하고, 적용은 `ResizeObserver` 가 폭을 잡은 뒤로 미룬다.
- `src/capa_simulation/components/month_range_picker.py` — 조회기간 팝업(`components/period_field.py`)의 달 고르기 —
  해 넘김(`‹ 2026년 ›`) · 열두 달 격자(세 칸 네 줄, 시작 달 → 끝 달 두 번 누름이 띠를 칠함) · 빠른 선택(이번 달부터 6 · 12 ·
  24개월 · 지난달부터 6개월 · 전체) · 「적용」을 한 Components v2 컴포넌트로 묶는다(2026-11-04 검수 의견 home-19 — 월 입력 두
  칸을 걷었다. `render_month_range_apply` 는 적용한 회차에만 범위를 준다). 조각은 `month_range_picker_assets/` 세 파일이다.
  - 고르는 동안은 초안이고 「적용」 때만 트리거 하나로 보낸다. 끝 달을 기다리거나 지금 기간 그대로면 「적용」 이 잠기고,
    다르면 맨 아래 「지금 …」 줄이 선다 — 설명 글 없이 단추 상태로 「적용 전에는 그대로」 를 말한다. 고를 수 없는 달은
    흐리게 잠긴다. 키보드는 방향키(한 달 · 세 달) · PageUp/PageDown · Home/End · Enter — 범위를 고른 자리(띠의 시작 · 끝
    칸이나 그 범위를 놓은 빠른 선택 칩)에서 Enter 를 한 번 더 누르면 「적용」 이다(`enterApplies` — 키 누름에서만, Space ·
    마우스는 그 달에서 새 범위 시작, 2026-11-04 재검 b-3). 판정 구획(`// <month-range-core>`)은
    순수 함수라 node 로 시험한다(`tests/test_month_range_picker.py`). 팝업 포커스 때문에 그림자 DOM 에 가두지 않는다
    (`isolate_styles=False`), 색은 `--st-*` 테마 변수뿐이다. 부르는 쪽은 모듈 속성으로 부른다(테스트가 갈아끼운다).
- `src/capa_simulation/components/date_panel.py` — 앱의 날짜 고르기 한 꼴(2026-11-05 검수 static-35). 값 칸(달력 표식 · 값 · `⇕`) +
  누르면 뜨는 기간 판(`‹‹ ‹ 2026년 11월 › ››` · 일 격자 · 빠른 선택 · 「적용」)을 한 Components v2 컴포넌트로 묶는다. 범위 칸
  `date_range_field` · `optional_date_range_field`, 한 날 칸 `date_field` · `optional_date_field`(`optional_*` 는 판에 `비움`).
  조각은 `date_panel_assets/` 세 파일이고 해 넘김 · 칩 · 바닥 줄 서식은 `month_range.css` 를 이름만 옮겨 쓴다(`DATE_PANEL_CSS`).
  - 값의 정본은 세션 칸(`date` · 비면 `None`)이고 「적용」 콜백이 쓴다 — 위젯이 아니라 언제든 쓸 수 있고 리비전 프리셋 키도
    그대로다. 범위 밖 · 거꾸로인 칸은 그리기 전에 맞춰 되적고, 끝을 주지 않은 칸은 오늘 앞뒤 십 년(값이 그 밖이면 값까지)이다.
  - 판은 HTML `<dialog>` 라 여닫기 · 고르기가 회차 0 이다 — 서버로 가는 길은 `apply` 트리거 하나다. `st.dialog` 안 칸도 되고
    Esc 는 판만 닫는다. **`st.form` 안에는 두지 않는다**(폼 안 트리거는 제출 때까지 서버에 오지 않는다). 위젯 키는
    `panel_key`(Components v2 키는 `__` 를 받지 않는다). 판정 구획(`// <date-panel-core>`)은 node 로 시험하고
    (`tests/test_date_panel.py`), 그 시험이 화면 코드의 `st.date_input` 0 곳도 지킨다. AppTest 대역은 `conftest.date_panels` 다.
- `src/capa_simulation/components/condition_field.py` — 사이드바 통합 조건 패널의 한 줄(이름 줄 `condition_name_row`
  과 팝업을 여는 값 칸 `condition_field`)을 그린다.
  - 컨테이너 key 접두어(`condition_field_<slug>`·`condition_name_<slug>`)로 `sidebar_style.py` 가 서식을 건다.
    `with` 안에서는 `st.*` 로만 그린다 — `st.sidebar.*` 는 `with` 를 따르지 않아 패널 밖으로 샌다.
- `src/capa_simulation/components/period_field.py` — 패널의 조회기간 줄과 그 팝업(`sidebar_period_open_dialog`)을 그린다.
  - 팝업 안 달 고르기는 초안이고 「적용」해 범위가 실제로 바뀔 때만 `MONTH_RANGE_KEY` 를 쓴다. 고를 수 있는 범위는
    매 회차 `month_selection_bounds()` 로 읽고 범위 밖 조회기간은 `clamp_month_range` 로 끝에 끼워 되적는다. 빠른 선택의
    기준 달은 `date.today()` 다. 팝업 머리에 설명 글을 두지 않는다(적용 전 편집 경고만 — 2026-11-04 home-19).
- `src/capa_simulation/components/scenario_status.py` — 사이드바 조건 패널의 시나리오 줄과 불러오기·새 리비전 저장·
  편집 되돌리기 팝업(`SCENARIO_DIALOG_KEY`)이다. 이름 변경·발행·삭제·신규 생성은 `시나리오 관리` 페이지 몫이고, 불러오기
  구획 끝 단추가 그 화면 Capa 시나리오 탭으로 간다(「시나리오 관리에서 이름 바꾸기」 — 그 페이지에서 연 팝업이면, 그리고 이름을 바꿀 수 없는 화면 등급(`scenario.list_edit` — 실무자부터)이면 서지 않는다).
  - 줄은 세션만 읽고 저장소는 팝업을 연 동안에만 읽는다(팝업 프래그먼트는 `app.py` 의 실행 핀 밖이라
    `pinned_connections` 를 스스로 잡는다). `tests/test_scenario_sidebar.py`·`test_app_navigation.py` 가 고정한다.
  - 배지는 미저장 → 공식 vN → **최신 rN 있음** → 저장된 리비전 차례다(머리 띠 `header_lines` 도 같다, E2E #102). 낡음은
    `app.py` 가 공식버전 요약 뒤·머리 띠 앞에서 `scenario_activation.check_active_scenario_latest` 로 **30초에 한 번**(다른
    시나리오를 불러온 회차는 곧바로) 보관본까지 목록을 읽어 세션에 적은 최신 번호를 이름표 번호와 견준 것
    (`newer_active_revision_no` — 세션만 읽음)이다. 팝업은 연 회차에 읽은 목록으로 그 값을 고쳐 적는다
    (`remember_active_scenario_latest`). 제 저장 뒤에는 이름표 번호가 확인 값 이상이라 서지 않는다.
  - 올라온 리비전이 없으면 줄 값 칸은 「시나리오명 · rN」 대신 「올라온 리비전 없음」 이다.
  - **적용하지 않은 편집은 시나리오에 없다** — 누른 회차에 `pending_edit_labels` 를 다시 세어 폼 밖 체크를 받는다.
    저장 폼은 성공 회차에만 key 세대(`SAVE_FORM_GENERATION_KEY`)를 올려 비운다.
  - 「신규 리비전 저장」 구획은 화면 등급 실무자부터 서고, 제출 단추 key 는 고정(`SAVE_SUBMIT_KEY` — `SessionSlot` `SAVE_SUBMIT`)이다.
    화면을 연 뒤 등급이 내려가 구획이 서지 않는 회차에 앞 회차 단추의 누름이 오면 말없이 「불러오기」 로 바꾸지 않고
    `_refuse_hidden_save` 가 실제 등급으로 다시 본다(`grades.require` — 감사 「등급 때문에 막힘」 한 줄 · 팝업 `in_fragment` 가 알림창 ·
    Alarm 한 번, 규칙집 6-34 decided-2 · 2026-11-19 E2E E1-D3). 적어 둔 리비전명은 구획과 함께 사라진다.
  - 저장은 부모 리비전의 가상 제품 이력에 세션 등록을 더해 넘긴다(`inherit_virtual_product_records`, 활성화 전에 읽음).
    `skip_unchanged=True` 로 넘겨 최신 리비전과 내용이 같으면 쓰지 않는다 — `RevisionUnchanged` 를 받으면 팝업 안 info
    (`revision_unchanged_notice`)를 적고 칸은 그대로 둔다(개선 I5, 5장 8).
  - 올라와 있는 시나리오가 목록(보관본 빼고)에 없으면 — 이 세션이 보관하면 활성화를 풀므로 다른 세션이 그 사이 보관·영구
    삭제한 것이다 — 저장 구획은 보관본까지 읽어(`list_scenarios(include_archived=True)`) 까닭과 길(보관함에서 목록으로
    되돌리기·「복제」·다른 시나리오 불러오기)을 적고 시나리오 관리 링크를 세운다(`missing_scenario_notice`, E2E #55).
  - **리비전 불러오기는 `load_saved_revision` 한 길이다** — 팝업 「불러오기」와 HOME 주요 Case 칩이 함께 쓴다(옛 리비전
    호환 검사 → 활성화 → 필드 알림·적용 전 편집 목록 비우기·팝업 닫기, 다시 돌리기는 부르는 쪽 — 팝업은 `st.rerun()`,
    칩은 콜백). `open_scenario_dialog_on` 은 팝업을 불러오기 구획·주어진 짝으로 연다(칩이 편집이 있을 때 같은 확인을
    거치는 길).
- `src/capa_simulation/components/space_layout.py` — Space 배치 집계(대수·점유율·층별 배치 `floor_placements`), 호기
  상자 면·글자(`unit_appearance`), 층 상세 범례(`space_legend_counts`), 층 상세 「호기 정보」 창의 칸(`FLOOR_TABLE_COLUMNS`)·
  누른 호기 줄(`picked_unit_rows` — 필요 단축 칸, 편집기 JS `pickedRows` 와 같은 규칙)과 영역·금지 색을 만든다. 색 기준 「필요 단축」 은 블록 셋째 줄(`floor_block_stats(short_lines=)` — 비활성
  층에는 싣지 않음)·구간 얹기(`apply_layer_looks` — 표시 호기 면을 비워 브라우저가 구간 변수로 칠함)·범례
  (`shortening_legend_entries` — 구간 넷·임박 테·흐림 + 테·덧표시 칸, 채우기 칸 없음)다.
  - 층 상세 범례는 칸 목록이다(`space_legend_entries`·`shortening_legend_entries` → `[{label, css, inner}]`, 끝 줄은
    `legend_as_of` 「기준 YYYY-MM-DD」) — 편집기 왼쪽 칸 「범례」 가 `css` 를 `style.cssText`, 글을 `textContent` 로만 단다
    (2026-11-03 — 머리 줄 범례를 옮겼다). `css` 는 토큰으로 만든 견본 꼴이라 사용자 글이 들지 않는다. `*_markup` 은 그 목록
    위의 얇은 HTML 감싸기로 남아 시험·읽기용이다.
  - 경계 날짜는 인자로 받는다(층 상세는 `simulation_cache.get_space_unit_boundaries` 로 한 번 구해 나눠 쓴다).
    Plotly 를 쓰지 않고 동·층 정의는 `services/fab_layout.py` 다. 층 블록 글자는 배치·미배치 대수뿐이고, 비활성 층
    블록은 그 대신 사유다(`floor_block_stats(inactive=)` — 그 층 칸에만 `inactive`, 대수 칸은 풍선에 남는다).
    블록 글자 줄 크기는 편집기 JS `// <block-text>` 구획의 순수 `blockTextLayout`(node 시험 `test_space_block_text_js.py`)
    이 정한다 — 단축 줄은 **폭 때문에** 이름·대수 줄을 끌어내리지 않고 제 폭으로 따로 작아지며, 많이 줄면 「 · 」 경계에서
    두 줄로 나뉘고 6px 아래면 그 줄만 숨는다(E2E r1 — 이름이 6~7px 이 되던 것). 높이는 단축 줄 몫도 나누므로 높이가
    모자란 블록(화면 약 63px 밑)은 줄 수 몫으로 이름·대수 줄도 조금 작아진다(1500 폭 낮은 층에서 13 → 약 12px — node 시험
    `test_a_low_block_keeps_the_name_size_instead_of_splitting_the_short_line` 이 그 크기를 고정한다). 세 줄로는 위 줄이 7px 아래인 낮은 블록도
    단축 줄부터 빼고, 이름·대수 두 줄로도 7px 아래일 때만 이름 줄 하나로 접는다(2026-11-02 E2E — 키 23 ~ 34px 블록에서
    「필요 단축」 을 켜면 대수 줄까지 사라졌다).
  - 층 캔버스는 `equipment_ops.floor_layout_profile` 의 층별 값이고, 캔버스 밖 호기 상태 알림 `EQ-18`
    (`space_floor_layout.report_canvas_outside` — `services/equipment_validation.floors_outside_canvas` 가 저장된 마스터 전체
    (`snapshot.equipment`, 일정 없는 호기 포함)를 전 층 한 번에 훑고 `simulation_cache.get_floors_outside_canvas` 가 스냅샷 토큰 +
    캔버스로 캐시, 지문은 [층, [캔버스 폭, 높이], 설비명 목록])도 같은 캔버스로 판정한다. 층 화면 맨 위 경고 상자는 걷었다
    (2026-11-07 답 place-box). 편집기 모듈을 import 하지 않는다(그쪽은 읽을 때 컴포넌트를 등록한다).
- `src/capa_simulation/components/space_floor_list.py` — Space FAB 전체 아래 **층 목록**(2026-10-24 결정 S1~S6). 보기는
  사용 층 표(`사용` 칸, 행 고르기 = 층 열기)와 늘 서는 자리 칸 안의 접힌 「비활성 층 n개」 표(거기서도 연다), 표 머리
  `사용 편집` 토글을 켜면 저장 줄 · 끄기 확인 · 알림 · 동 머리 줄(`st.segmented_control` 다섯 — 값은 회차마다 초안에서
  세션에 적고 `default=`·세대 꼬리 없음) · 30줄 편집표다.
  - 편집 중인가(`FLOOR_EDITING` — 2026-11-19 보드 m19-e2e-space-leave (나))·초안(「C1 3F」 → 사유 — 옛 코드 또는 적은 글)·편집
    시작 저장본 `(version, rows)`·확인 대기·단추 세대는 위젯 밖 세션 칸이고(`사용 편집` 토글 값은 그리기 전에 회차마다
    `FLOOR_EDITING` 으로 적는다 — 화면을 떠나 위젯 상태가 걷혀도 돌아오면 켜진 채 선다),
    편집표 칸 편집은 회차마다·콜백 첫머리·편집표 `on_change`(`_fold_from_editor` — 고친 직후 화면 탭 · 사이드바 링크로 떠나도 남게, 초안만 적고 새 위젯 세우기 · 단추 세대 올림은 본문 몫 — 같은 회차 단추 누름이 옛 세대로 버려지지 않게)에 초안으로 접는다(`_fold` — 빈 사유는 「사용 안 함」, 사용 층에 사유를 적으면
    끄기). 접는 바탕은 늘 그 위젯이 그린 초안(`FLOOR_DRAWN` · `_fold_base` — 동 머리 · 편집표를 그리기 바로 앞에 둔다)이다 — 콜백이
    접어 세션 초안이 바뀐 회차에 본문 · 단추 콜백 · 머리 수가 같은 편집을 다시 접어도 같은 값이다(접은 값 위에 다시 접으면 사유를 친
    채 켠 줄 등이 뒤집혔다). 브라우저 뒤로가기 바로 앞에 고친 칸은 Navigation API 가 없는 브라우저에서 그 편집 회차가 서버에 닿지 않아
    남지 않을 수 있다(앞서 접힌 초안은 남는다 — Guide · 런북 7-5). Chrome · Edge 는 탭 줄 뒤로 지킴이가 칸을 확정해 그 회차를 먼저 돌린 뒤
    옮긴다(`page_tabs.py` 「뒤로 · 앞으로 지킴이」 — 층 사용 편집 칸은 사외 시범 밖이고 같은 glide 편집표인 입력 비가동으로 쟀다). 칸을 고친 직후 화면 탭을 누르면 브라우저가 옛 Space 위젯 값을 실은 메시지를 다른 화면을 돈 뒤
    한 번 더 보내고, 그 사이 위젯 상태가 걷혀 Streamlit 이 바뀐 것으로 보고 콜백을 부른다 — 토글 콜백(`_toggle_changed`)은
    `FLOOR_EDITING` 과 견줘 실제로 바뀐 때만(켜짐은 편집 중이 아닐 때, 끄기는 값이 꺼짐일 때) 움직이고, 동 머리 콜백은 그린 머리 값과
    같은 값을 받지 않는다(받으면 초안을 저장본으로 다시 세우거나 같은 메시지의 칸 편집을 덮었다). 그 메시지가 Space 를 다시
    세우지는 않는다 — `app.py` 가 회차 맨 앞에서 옮겨 간 화면으로 다시 보낸다(`stale_page_guard`, 9장 「화면 탭 줄」). 칸 편집은 위젯에 남아 접은 초안을 그린 위에 얹혀 보이므로, 다시 세우는 것(`discard_editor`)은 그렇게 보일 값이
    접은 값과 다를 때뿐이다(비활성 층의 사유 지움, 「UNUSED」 처럼 그린 글과 다르게 접히는 글, 이모지 반쪽이 남은 글 등 —
    견주기는 보이는 칸 글로 한다) — 끄기·켜기·사유 적기는 같은 위젯이라 보던 스크롤·초점이 남는다.
    `사유` 칸은 `string` 으로 고정한다(9장 「편집표와 내려받기」). 쓰기 단추는 그린 회차의 세대를 인자로 받아 옛 누름을 거른다.
  - **`사유` 는 직접 적는 글 칸**이다(2026-10-26 결정 — S1 의 고르기를 바꿈): `TextColumn(max_chars=20)`, 도움말에 예시 두
    문구(`FLOOR_REASON_EXAMPLES`). 칸 글은 `floor_reason_code` 로 읽는다 — 짝 없는 서로게이트와 앞뒤 공백을 떼고, 비면
    사유 없음(끄면 「사용 안 함」), 옛 코드의 글(「사용 안 함」·「생산라인 아님」)이나 코드 글자(「UNUSED」·「NOT_LINE」)는
    그 코드라 그린 글을 그대로 되적으면 바뀌지 않은 것이다(저장된 글로는 옛 코드와 가를 수 없어 코드 글자도 그 글로 보인다).
    편집표는 `reason_cell_text`(옛 코드 → 그 글, 적은 글 → 저장할 글 그대로 — 줄바꿈·탭도 빈칸으로 바꾸지 않는다)를
    그린다 — 도면·배너의 `inactive_label` 처럼 바꿔 그리면 칸을 새로 세운 뒤 `저장` 이 거절하는 까닭이 보이지 않는다.
    브라우저 칸은 **UTF-16 단위로** 20에서 끊는다(붙여넣기도 — Streamlit 1.63 `max_chars`). 그래서 이모지(2단위)는 2자로
    세고, 20번째 단위에 걸린 이모지는 반쪽(짝 없는 서로게이트)만 온다 — Arrow·DuckDB 가 UTF-8 로 싣지 못해 편집표가 깨지고
    저장은 DB 를 무효로 만드므로(`FatalException`) `floor_reason_code` 가 떼고 `_REFUSED_CATEGORIES` 에 Cs 도 둔다.
    `저장` 이 `prepare_floor_states` 로 먼저 보고 받을 수 없는 글(길이·제어 문자)은 알림 칸 `st.error` 로 거절한다(쓰지
    않고 편집은 남는다 — 제어 문자 거절 글은 「그 칸을 지우고 다시 적으세요」 를 붙인다). 동 머리는 옛 코드 둘만 고른다 — 직접 적은 사유로 끈 동은 고른 것 없음 + 「C2 · 사용 0/6」(`building_state`).
    성공 알림은 사유마다 층 수이고 사유를 `literal_markdown` 으로 막는다(다섯 가지 넘으면 「외 n가지」).
  - 호기가 남은 층을 새로 끄면 막지 않고 확인한다(호기 수는 편집 모드 본문이 센 `floor_unit_counts` 를 콜백 인자로).
    확인을 띄우기 전에 저장소의 지금 version 을 캐시 없이 읽어(`_stored_version`) 편집 시작 version 과 다르면 확인 없이
    곧장 쓰기에 보낸다 — 대조가 거부(또는 겹쳐 온 제 저장)를 알려 헛된 확인을 한 번 덜 받는다(못 읽으면 전처럼 확인).
    저장은 `save_floor_states(expected_version=…)` → 성공이면 `clear_floor_state_cache`·flash·토글 끄기, 충돌이면 알림
    칸 `st.warning` 과 초안을 최신으로 다시 세움, 같은 내용이면 `st.info`. 충돌은 거부 표지(`note_profile_conflict`)를 초안을
    다시 세우기 **전에** 적는다 — 창 안의 저장은 쓰지 않고 초안을 최신으로 다시 세운 채 거부를 다시 알리고, 동 머리 콜백은
    옛 화면의 동 머리 값(빠른 둘째 누름이 다시 실어 온 내 옛 변경)을 받지 않으며, 알림 칸은 담아 둔 알림이 없으면 그 거부를
    다시 그린다(2026-10-26 E2E 5회차 — 「끄고 저장」 두 번에 알림이 사라지고 다음 저장이 남의 저장을 덮었다,
    `tests/test_space_floor_state_page.py`). 편집을 끈 채 그려지는 회차는 남은 초안 조각을 지운다. 초안은 화면을 떠나도
    남지만(위) 같은 화면 안에서 다른 층 열기는 그대로 먼저 묻는다(2026-11-19 사용자
    요청 — 앱에 있던 꼴만, 보드 m19-guard-floor 「좋음」): FAB 뷰어 · 편집기는 data `openConfirm`(`floor_open_confirm` — 초안이 있을 때만
    `FLOOR_OPEN_CONFIRM`, 탭 줄 떠나기 확인과 같은 꼴의 브라우저 확인 창, epoch 밖)으로 블록 누름 · 선택 칸 [열기] 앞에
    묻고 「확인」 을 `navigate` 의 `discard` 로 함께 보내며, 사이드바 `층 바로 가기` 는 팝오버 안 「변경을 버리고 열기」
    체크(`FLOOR_OPEN_DISCARD_LABEL` — 「변경을 버리고 불러오기」 와 같은 꼴) 뒤에만 고른다. 서버 거름은
    `floor_open_allowed`(`space_status._open_floor` 첫머리) — 묻지 않고 온 열기(확인 글이 닿기 전 누른 블록)는 초안을 두고
    열지 않으며 층 목록 알림 칸에 경고 한 줄. 주소로 여는 층(새 문서 — 새로고침 확인이 묻는다)은 이 거름을 지나지 않는다(층 열기는
    브라우저 기록을 쌓지 않아 「같은 화면 안의 뒤로가기」 는 없다 — E2E E2-1). `floor_state_draft_count()` · `floor_state_draft_pending()` 은 세션만 읽는
    Space 탭 점 · 머리 변경 칩(「저장 안 함」 묶음 「층 사용 편집 저장 안 함」 — 그 화면으로, 층 수는 싣지 않는다 — 2026-11-20 사용자
    결정, 머리가 첫 편집 · 마지막 되돌림에만 바뀐다) · 테마 · 새로고침 표지다
    (`page_tabs.page_unsaved_marks` · `change_summary.session_changes` — **어느 화면에서나**, 탭 줄 떠나기 확인 `leave_notice` 에는
    넣지 않는다 — 떠나도 잃지 않는다, 층 사용을 고칠 수 없는 화면 등급이면 0) — `app.py` 가
    페이지보다 먼저 부르므로 이 회차 편집표 위젯 상태의 칸 편집까지 (적지 않고) 접어 저장본과 견준다.
  - **되살아난 초안의 거름**은 `settle_floor_state_draft` 다(Space FAB 회차마다 층 목록 · 층 바로 가기보다 먼저). 더는 고칠 수
    없으면(등급 · 가정 설비 시나리오 · 샘플 화면 — `editable`) 편집을 끄고 초안을 버리고, 다른 화면에서 돌아온 회차(편집 중인데
    토글 위젯 상태가 켜져 있지 않다)에 초안이 출발한 version 과 저장본이 다르면 남의 저장이면 최신 저장본으로 다시 세운다(편집은
    켜진 채 — 제 저장이 끊긴 것은 `is_own_save` 로 저장 뒷정리). 바뀐 층이 있던 초안을 버린 회차는 그 수(`FLOOR_DROPPED_SAVED` ·
    `FLOOR_DROPPED_LOCKED`)를 Space 가 회차 끝(모든 위젯 뒤, 다른 다시 돌기보다 먼저)에 층 목록 알림 칸에 담고
    (`queue_floor_state_notice`) 앱 전체를 한 번 더 돈다 — 머리 점 · 칩은 페이지보다 먼저 옛 초안으로 섰다(입력 비가동
    `_settle_draft` 와 같은 까닭). 화면에 머문 채 남이 저장하면 전처럼 「저장」 이 거부하며 다시 세운다(화면에 머문 회차는 거르지
    않는다 — 칸 편집 회차에 초안을 버리지 않게). 공식 설비 시나리오 안의 리비전만 바뀐 것은 거르지 않는다(층 사용은 리비전과
    무관 — S6). 「도면에서 보기」 처럼 층 상세로 바로 온 회차는 거르지 않고 FAB 에 와서 거른다.
  - **공식 설비 시나리오에서만 연다**(설비 시나리오 2단계 Q3 — 건물·층은 가정 시나리오가 없다, FAB 전체와 같은 까닭). 가정
    세션과 샘플 fleet 화면에서는 잠근다(값도 끈다 — `locked_reason` 풍선). 끄기 확인은 값 줄 하나와 단추이고(호기 남은 층 · 공식 배치 수 — 뜻은
    `끄고 저장` 풍선), 공식 배치의 호기 수에 더해 가정 설비 시나리오의 배치에서 그 층에 놓인 호기 수를 덧줄로 적는다(`equipment_cache.load_layout_overlay_floor_counts` — 층 사용은
    공통이라 그 시나리오 목록·도면에서도 숨는다, 설계 13-2). 공식 배치에는 호기가 없어도 가정 배치가 그 층에 호기를 두었으면
    확인 대상이다(값 줄 호기 0대 + 가정 배치 덧줄 — 배치안이 빈 층을 쓰는 경우). 초안이 있는데 사이드바 팝업에서
    가정 설비 시나리오를 고르면 「변경을 버리고 불러오기」 를 묻고(설계 9장), 불러온 회차에 팝업이 토글·초안을 걷는다
    (`discard_floor_state_draft` — Space 가 잠그며 버리기를 기다리면 그 앞의 `app.py` 탭 점·떠나기 확인이 버린 초안을 한 회차
    더 센다). 이 모듈에는 Streamlit 캐시를 두지 않는다.
  - 보기 표의 덧붙임 칸은 `extra_columns`(`FloorListColumn` — 칸 이름·층마다 값·칸 설정·`active_only`) 한 인자다. 「공식과
    견주기」 의 「공식과 다름」 은 사용·비활성 두 표에, 색 기준 「필요 단축」 을 켠 동안의 칸 넷(`단축 호기`·`최대 단축(일)`·
    `기한 지남`·`추가 호기` — `layer_columns`, `active_only=True`)은 사용 층 표에만 선다(비활성 층에는 층 대수를 싣지 않는다).
    둘 다 켜면 넘긴 차례(「공식과 다름」 → 칸 넷)로 기본 칸 뒤에 선다.
- `src/capa_simulation/components/space_floor_layout.py` — Space 가 그리는 층 도면 요소·Main 설비명 위치의 한 곳(설비 시나리오
  2단계 S3). `effective_floor_layout(db, 층, 세션)` = 공식 층 현행값(`load_floor_layout_marks`·`load_floor_group_labels` — 쓰기
  세대 캐시) ⊕ 세션 리비전의 요소·이름표 차이(`load_schedule_layout_overlay` — 일정 id 키 불변 칸, 차이 없으면 질의 없음)를
  회차마다 합친다(층 하나·수십 요소 — 캐시하지 않는다, 이 모듈에 캐시 데코레이터 없음). `floor_layout_differences` 는 배치
  알림의 실효 요소·이름표 수, `space_layout_notices` 는 Space 배치 상태 알림(`LayoutNotice` — 등록부 코드 `EQ-13`~`EQ-15` ·
  전문 · 짧은 글 · 지문 재료, 그리는 스냅샷 기준 — 설계 8-2, 2026-11-04 Space 결정 보드 답으로 사이드바 상자 줄에서 알림으로)이고
  `report_layout_notices` 가 그 셋을 회차마다 같은 차례로 낸다(없는 코드는 해소). 「공식과 견주기」(S4)
  재료 `compare_payload`(층 상세 뷰어 `compare`)·`floor_unit_differences`(FAB 층 목록 칸·블록 풍선)도 여기다 — 둘 다 그리는 세션
  스냅샷의 합친 본문과 마스터만 읽는다.
- Space 층·FAB 캔버스 폭·높이는 따로 여는 팝업이 없다(2026-11-12 Space 보드 답 1-4 — 「캔버스 편집」 팝업 · 사이드바 단추를
  걷었다) — 층·FAB 「배치 편집」 왼쪽 칸 「캔버스」 → 적용 → 「배치 저장」 이다. 칸의 하한은 놓인 호기·요소, 도면에 안 보이는 이
  층 호기(`EditorInputs.reserved_extent`)와 다른 가정 설비 시나리오의 이 층 배치 차이(`LayoutOverlayExtent.scenario_extents`,
  공식 세션 회차에만 `canvasLimits.overlay`)이고 막은 글이 닿은 까닭을 말한다(editor.js `canvasLimitWords`). 가정 배치 하한은
  적용 길도 다시 본다(`LayoutOverlayExtent.scenarios_outside` — 낡은 편집기 · 옛 화면이 그보다 작게 보낸 캔버스를 거부). 적용의
  「캔버스 밖」 검사는 그 층만 본다(`equipment_validation.require_floor_inside_canvas` — 두 층 이상이 밖(`EQ-18`)이어도 층마다
  넓혀 두고 「배치 저장」 이 마스터 전체를 본다. 글은 저장 글의 층 조각에 적용 자리의 고칠 곳만 붙인다). 옛 판이 올린 도면 그림은 설비 DB `image_*` 칸에 남고 읽지도 그리지도 않는다(마이그레이션
  없음). 알림 `EQ-16`(옛 팝업의 밖 알림)은 비워 둔 번호다.
- `src/capa_simulation/components/space_layout_editor.py` — Space 층·FAB 도면의 Components v2 편집기와 보기 전용 뷰어
  (`render_space_layout_viewer`·`render_fab_layout_viewer`·`render_fab_layout_editor`)다.
  - 「필요 단축」 payload(층 보기만, 값이 있을 때만 키 — 끈 동안 payload 그대로): 호기 `layer`(`s|m|l|x`)·`dim`,
    `shortBadges`(설비키마다 하나 — `ids` 는 그 층에 그린 모듈), `asOfPinned`(고정 줄 뒷글). 팔레트 `short-*` 칸은 늘 싣는다
    (CSS 변수는 모두 팔레트에 — 시험). JS 배지 자리는 `// <short-badge>` 구획의 순수 `badgeSpot`·`settleBadges`(배지끼리
    겹치면 뒤 배지가 한 칸 위로, 그래도 겹치면 그 배율에서 숨음)이다(node 시험). 배지를 다시 그릴 때 초점을 쥔 배지는 같은
    key(`data-key`)의 새 배지로 돌려준다(키보드로 고를 때 초점이 문서 처음으로 빠지지 않게). 「공식과 견주기」(`compare`)와
    함께 켜지면 견주기 층 `sle-compare` 가 흐린 상자·배지 층 `sle-short-badges` 위에 선다(눌림이 없어 배지 누르기는 그대로) —
    꼬리표와 배지가 서로 비키지는 않는다. FAB 블록 풍선은 단축 줄(`short`) 뒤에 견주기 줄(`layout`)이다.
  - HTML·CSS·JS 는 `space_layout_editor_assets/` 파일이고 모듈을 읽을 때 한 번 등록한다(`_EDITOR` — AppTest 는 JS 를
    못 돌려 `tests/conftest.py` 가 말 없는 대역을 깐다).
  - 편집기 단추 서식(`.sle button:where(…) { display: inline-flex }`)은 브라우저의 `[hidden]` 기본 규칙보다 세다 — JS 가
    `hidden` 을 다는 단추마다 그 단추의 `[hidden] { display: none }` 규칙을 둔다(`tests/test_space_layout_editor_assets.py` 가
    머리에서 쥔 단추를 모두 본다). 「호기 정보」 창 「CSV」 는 설비 화면 내려받기 등급 밖이면 파이썬이 `sheet.csvHidden` 을 싣고
    「모든 칸」 글을 싣지 않으며, 단추 · 펼침 · 「보이는 줄」 내려받기가 한 판정 `sheetCsvHidden`(`// <unit-sheet>`)을 본다.
  - **편집기 몸은 가로 세 칸**(2026-11-03 사용자 요청 — 좌우로 긴 화면의 여백을 두 옆 칸에): `.sle-body` grid 다섯 칸
    [왼쪽 칸 `.sle-side.is-left`][칸막이][무대][칸막이][오른쪽 칸 `.sle-side.is-right`] — 칸마다 `grid-column` 을 박아 숨은 칸이
    있어도 밀리지 않는다. 왼쪽 칸은 FAB 보기에만 없고(층 보기는 「범례」 묶음 하나, 편집은 「도구」 — 범례·도면 요소·선택·
    서식·격자·캔버스 묶음, 묶음 머리를 누르면 접힘), 오른쪽 칸(옛 미배치 서랍 — `.sle-tray`·`.sle-drawer-tab`·
    `.sle-drawer-close` class 는 그대로)은 층 편집에만 있다. 칸 상자는 `position: absolute; inset: 0` 이라 내용이 줄 높이를
    늘리지 않고 머리 아래가 굴러간다. 폭 한계·저장값·칸막이 키·무대 몫·고정 높이·놓기 판정은 순수 구획 `// <side-panels>`
    (`panelBounds`·`clampPanel`·`storedPanels`·`splitKey`·`fitPanels`·`dragLimit`·`lockHeight`·`lockTop`·`insideRect` —
    `tests/test_space_editor_panels_js.py` 가 node 로 돌린다). 칸 폭: 편집 칸 기본 clamp(220, 편집기 폭 × 0.18, 300)·최소 200·
    최대 min(480, × 0.4), 층 보기 범례 칸 기본 200·최소 160·최대 min(360, × 0.3), 무대 최소 360(두 칸을 다 넓히면 마지막에 끈
    칸부터 줄인다). 칸막이(`role=separator`)는 끌기·두 번 누르기 = 기본 폭·←/→(Shift 64)·Home·End·Enter 접기이고 키는 도면
    단축키로 새지 않는다(설비 마스터 오른쪽 칸 칸막이와 같은 꼴). 접으면 칸 자리가 0 이 되어 도면이 넓어지고 접힌 단추
    (`.sle-side-strip`)가 무대 가장자리 8px 안쪽 위에 뜬다(왼쪽 칸은 왼쪽, 오른쪽 칸은 오른쪽 — 검수 eqp-side-01, 옛 미배치 서랍 단추 꼴: `.sle button` 27px · 13px 600 · 모서리 8px · 테두리 BORDER · 면 SURFACE · 그림자 없음, 화살표 없음 — 설비 마스터 `.ess-rail` 과 같은 생김이고 `tests/test_fold_button_look.py` 가 맞댄다). 폭·접힘은 `capa.space.panels.v1`(범위·모드별
    — `floor.edit`·`floor.view`·`fab.edit`), 묶음 접힘은 `capa.space.sections.v1` 에만 둔다(파이썬·epoch 밖 — 9장 「브라우저
    전용 보기 상태」). 편집기 폭 900px(`NARROW_PX`) 아래에서는 두 칸이 무대 위 겹침 서랍(한 번에 하나, 처음엔 접힌 단추)이고 옛 서랍
    동작(`trayReserve`·`revealFromTray`·서랍 밖으로 끌면 비침)은 그 꼴에서만 돈다. 미배치 칸이 360px 이상이면 칩이 두 열(CSS
    컨테이너 `sle-tray`)이고 칸 안에 도움말 글이 없다 — 칩 키는 도구 줄 「단축키」 판(`SHORTCUTS`), 값 설명은 Guide 다. **도면의 호기를 오른쪽 칸(접힌 단추 포함)에 끌어 놓으면
    미배치**다(`S.drag.toTray` — 놓으면 끈 자리를 처음으로 돌린 뒤 호기만 `removeItems`, 도면 요소는 제자리, 되돌리기 한 번).
    범례는 data `legend`(epoch 밖 — `_clean_legend`)를 `textContent`·`style.cssText` 로만 단다. 층 편집의 기준일 고정은 옛
    「편집 중 고정」 줄 대신 도구 줄 칩(`sle-pinchip`, 결정 D12)이고 기준일 페이더 줄(`sle-daterow`)은 층 보기에만 선다. 단축키는
    도구 줄 「호기 정보」 옆 「단축키」 판(`.sle-keys-toggle`·`.sle-keys`, z-index 5 — 몸 안에 겹쳐 단추 아래 `placeKeys`, Esc·판 밖 누르기·단추·×
    로 닫음, 파이썬으로 보내지 않음)이고 표는 순수 구획 `// <shortcuts>` 한 곳이다(`SHORTCUTS`·`shortcutRows` — 화면 넷 `vf`·`vb`·`ef`·`eb`,
    「키조합 : 기능」, `tests/test_space_editor_shortcuts_js.py` — 키를 더하거나 고치면 표도 고친다, 검수 equip-61). 상태 줄(`updateStatus`)은
    값 · 표지만이고 하는 법은 그 판 · 풍선 · Guide 다. 꺼진 도구 줄 단추는 감싼 칸 `.sle-tiphost` 와 풍선 `.sle-tip`(`lockWith` · `setTip`)이 잠긴 동안 까닭을 말하고
    키보드 초점도 칸과 단추 사이를 따라간다 — 「적용」 의 sticky 는 감싼 칸 `.sle-apply-host` 쪽이다. 호기에 덮인 영역 이름표는 호기 위 겹 `sle-zone-tags`(`sle-marks` 와 `sle-group-names` 사이)에 다시 세운다 — 위 변 바로 바깥, 도면 위 끝이면 제자리(`zoneTagLift`), 누르기 안 받음 · 얇은 테, 영역 겹의 제 이름표는 숨김(UI-ACC-04). 도구 줄 제목(`sle-title`)은 보기에도
    서서 지금 층(FAB 은 `FAB_TITLE`)을 말한다. 도구 줄이 넘치면 `fitToolbar` 가 창 폭으로만 정하는 접는 차례를 더한다 — FAB 보기
    ①~③ 다음 ⑥(둘째 줄 — ④ · ⑤ 의 말줄임 단계는 없다, 2026-11-07 답 narrow), 층 보기 ⑥, 편집 `is-efit1`(「호기 정보」·「단축키」·「화면 고정」 아이콘만 · 기준일 칩 날짜만 — 낭독기 글은 남김) → ⑥(빈 칸 뒤 「호기
    정보」·「화면 고정」·「적용」 을 둘째 줄로, 글 다시 섬). 무대 높이를 재기 전에 접는다(둘째 줄이 무대를 내린다 — 검토 browser-1:
    사이드바를 연 1100px 창 층 편집에서 「화면 고정」 이 줄 밖이라 화면 고정을 켤 수 없었다). 편집은 무대 기본 높이를 영역 비율로 줄이지 않는다(옆 칸이 무대 높이를 같이 쓴다).
  - **화면 고정**(도구 줄 「화면 고정」 `sle-lock`, `aria-pressed`): 켜면 본문 스크롤 칸을 굴려 편집기 맨 위를 화면 탭 줄 아래
    끝 + 8px(`lockTop`)에 맞추고 무대를 창 높이에 맞춘 뒤(`lockHeight` — 고른 높이·기억은 그대로, 높이 손잡이 숨김)
    `<html data-space-lock="1">` 을 단다. 본문 스크롤을 막는 규칙은 페이지 서식 `space_lock_style()`(Space 현황이 `st.html`
    로 그림 — 스타일만 들어 이벤트 칸)이라 다른 화면으로 가면 정리 함수가 돌지 않아도 풀린다. 고정 중 맨 휠은 도면 이동
    (Shift 가로)·Ctrl+휠 확대이고 늘 막는다. 위 칸이 서고 사라지면 본문 내용 상자 관찰자(`S.mainRo`)와 회차마다 다시 맞춘다.
    고정은 마운트에만 둔다(`S.lock` — 다시 마운트되면 풀린 채, 새 마운트는 앞에서 남은 속성을 걷는다) — 층·FAB 바꾸기·배치
    편집 켜고 끄기도 다른 key 라 풀린다. 고정 중 data `pendingSave`(위 「저장 안 한 배치」 상자를 그린 회차)면 「화면 고정」 단추에
    점(`sle-lock-dot`)이 서고 풍선 앞에 「저장 안 한 배치가 있습니다 …」 가 붙는다(`showLockMark` — 표지 + 풍선). Streamlit DOM 에 기대는 곳(1.63 — 판올림에서 다시
    본다): `section[data-testid="stMain"]`(본문 스크롤 칸), `.st-key-page_tabs_strip`(sticky 화면 탭 줄),
    `[data-testid="stMainBlockContainer"]`, 컴포넌트가 같은 문서라 `document` 를 본다.
  - **「호기 정보」 창**(층 보기·편집, FAB 없음 — 2026-11-03 사용자 요청): 편집기 몸 안 겹친 창 `.sle-sheet`(`role=region`,
    z-index 4, 몸 안으로 묶음 — 순수 `clampSheet`, 최소 360×200, 처음 무대 왼쪽 아래 720×320). 도구 줄 「호기 정보」
    (`sle-sheet-toggle`, `aria-pressed`)나 호기 두 번 누르기(보기는 `svg.ondblclick` 의 `unitAt` — 빈 곳은 확대 그대로. 편집은 눌린 상자를 끌 준비로 맨 위에 다시 붙여 dblclick 이 서지 않아 `svg.onpointerup` 이 움직이지 않은 누름 둘을 `isDoublePress` 로 잡는다)로 연다.
    제목 줄 끌기 = 옮기기, 오른쪽 아래 손잡이 = 크기, `–`(제목 줄 두 번 누르기도) = 접기, `×`·Esc = 닫기. 창이 열린 동안 Esc 는
    편집기 어디에 초점이 있든 창 차례(`escapeSheet` — CSV · 칸 필터 펼침 → 창)를 쓴다 — 도구 줄 「단축키」 판이 맨 앞이고(창 안에서도), 끌기 취소 · 서식 붓과 Esc 를 스스로 쓰는 칸
    (이름 칸 되돌리기 · 미배치 검색어 지우기 · 갤러리 접기)이 그 앞, 고른 것 풀기가 그 뒤이고, 그 밖의 입력 칸(체크박스 · 숫자 · 글자)에서는
    칸의 값을 건드리지 않고 창만 닫는다. 초점 못 받는 자리를 누르거나 칸의 Enter · Esc 가 초점을 빼면 초점을 창에 둔다(`keepKeysInSheet`). 탭 둘 — 「고른 호기」
    (보기 `pickedRows` — 파이썬 `picked_unit_rows` 와 같은 규칙, 편집 `pickedRowsMany` — 고른 차례로 이음)와 「필터」(칸 머리 ▾ →
    엑셀 자동 필터 꼴 펼침 `.sle-sheet-menu` — 값 목록 체크·개수·찾기·모두 고르기/풀기, 날짜·숫자 칸은 「부터·까지」. 칸 안 OR ·
    칸끼리 AND, 대소문자 무시, 빈 값 「(빈칸)」, 값 목록은 다른 칸 필터만 지난 줄에서 — `sheetMatch(rows, columns, filters, skip)`·
    `distinctValues`·`inRange`·`sheetActive`·`sheetHits`). 판정은 순수 구획 `// <unit-sheet>`(`tests/test_space_unit_sheet_js.py`
    가 `// <module-tiling>` 의 `naturalCompare` 와 함께 node 로 돌림)이다. 필터가 걸리고 「도면에서 강조」 가 켜진 동안(창 열림 —
    접힘 포함) 맞는 호기 `is-filter-hit`(새 부품 `.sle-filter-ring` — 보기·편집 모두 만들고 `FILTER_GAP_PX` 5 로 선택 후광 밖, 토큰
    `SPACE_FILTER_RING`), 나머지 `is-filter-out`(`SPACE_FILTER_DIM_OPACITY` — 필요 단축 `is-dim` 과 함께면 `calc` 로 곱함)이고 편집
    오른쪽 칸 칩도 `is-filter-hit` + 칸 머리 「필터 맞음 n」(`.sle-tray-hits`). 닫으면 강조를 끄고 필터는 남는다. 목록 줄 누르기
    (`goToUnit`) = 고르기(칸을 고치는 배치 편집의 「고른 호기」 탭은 고른 것을 두고 누른 호기를 기준으로만 — `sheetRowPick`, 보이는
    줄이 그대로라 표를 다시 그리지 않아 두 번 누름이 끊기지 않는다) + `zoomToBox`(보기는 `notePick` 도) + 창이 덮으면 덮지 않은 가장
    넓은 띠로 밀기(`clearOfSheet`), 편집의
    미배치 호기는 오른쪽 칸을 펴 그 칩으로 굴려 깜빡임, 그 밖은 창 아래 한 줄. 편집에서 도면에 선 묶음의 좌표 없는 모듈(`trayKeep` 이 서랍에서 뺌)은 그 모듈을 고른
    채 화면을 그 묶음의 도면에 선 모듈로(같은 `zoomToBox` · `clearOfSheet`) 옮기고 창 아래 「<id> — 도면에 없음 · Main 설비 <묶음>」
    이다. 창 아래 한 줄은 편집 기록(`pushUndo`)마다 지운다. 줄 누르기로 고른 것이 바뀌거나(`attractPicked` — 화면을 다 옮긴 뒤)
    사람이 걸러 맞음이 바뀌면(`refreshHits(fromUser)` — 칸 필터 · 칩 · 모두 지우기 · 「도면에서 강조」, 펼침 안 체크는 닫을 때 `settleAttract`)
    그 테에 알림 칸과 같은 시선 끌기를 한 번 건다(`attractTo` — 무대 안 층 `.sle-attract`, 2026-11-12 Space 시안 보드 답 5-2 · 5-3,
    설계 규칙 UI-NAV-02). 대상 판정은 순수 구획 `// <attract-pick>`(`tests/test_space_attract_pick_js.py`) — 묶음 열쇠로 세고(모듈 묶음 1대)
    이 층 도면에 보이는 대상이 5대(`ATTRACT_MOST`)를 넘거나 앞과 같으면 걸지 않는다. 화면 밖 테는 빼고, 확대 · 이동 · 크기 바뀜
    (`applyView`) · 새 epoch 에 걷는다(`stopAttract`). 움직임 줄이기 설정이면 윤곽(`sle-attract-still`)이다. 배치 편집의 「도면」 칸은 적용 전 편집으로 덮어
    쓴다(`sheetRows` — 트레이 = 미배치, 보낸 호기 「→ 층」). 창 안 키는 도면 단축키로 새지 않는다(`sheetBox.onkeydown` 이 멈춤).
    배치 편집의 Ctrl(⌘)+Z 만은 입력 칸 밖이면 「되돌리기」 단추와 같은 `undo()` 다(순수 판정 `sheetEditUndoKey` — 편집기 몸과 같은
    판정).
    상태는 브라우저에만 — 자리·크기·접힘 localStorage `capa.space.sheet.win.v1`, 열림·탭·필터·강조 sessionStorage
    `capa.space.sheet.state.v1`(탭 안 기억, 층·편집을 오가도 남음 — 필터는 칸 이름으로 남아 새 층의 값으로 다시 센다). 받은 표는
    지문(`S.sheetDataKey`)이 바뀐 회차에만 다시 그리고, 상태 줄을 고칠 때마다(`updateStatus` 끝) 같은 그림이면 고른 줄 표시만
    고친다. 끄는 동안(`S.drag`)은 쉰다. 빈 표는 결론 한 줄(「맞는 호기가 없습니다」 · 「이 층에 호기가 없습니다」 · 「고른 호기가
    없습니다」), 잘린 줄은 값 「n줄 더 있음」(모든 줄을 받는 `CSV` 펼침은 풍선)이다 — 하는 법 꼬리를 달지 않는다(설계 규칙
    UI-TXT-03 · UI-TXT-04).
  - **창 칸 고치기**(배치 편집만 — 2026-11-12 Space 시안 보드 답 5-4 ~ 5-6): data `sheetEdit`(epoch 밖 — 파이썬
    `space_sheet_edit.sheet_edit_data`)가 있을 때 칸마다 `data-col` · `data-shown` 을 달고 `paintSheetCell` 이 고친 칸
    (`is-edited` — 설비 마스터 「바뀐 칸」 꼴, 묶음 형제의 같이 바뀐 칸 포함) · 잠긴 칸(`is-locked` + 까닭 풍선) · 막힌 칸
    (`is-blocked` + 까닭 풍선) · 칸 커서(`is-cursor`, 묶음 줄의 같이 바뀌는 칸이면 「묶음」 표지)를 칠한다. 판정은 순수 구획
    `// <sheet-edit>`(잠금 · 원래 글 · 고르기 값 · 고친 칸 지도 · 판정 열쇠 — `tests/test_space_unit_sheet_js.py`)이고 칸끼리 ·
    줄끼리 규칙은 파이썬에만 있다. 칸 한 번 누름 = 칸 커서 + `goToUnit`, 같은 칸 두 번 누름(`isDoublePress` — 표를 다시 그려도
    칸 열쇠로 견줌) · F2 · Enter · 글자 = 열기(고르기 칸은 `<select>`, 그 밖은 글 칸 — 날짜도 글), Enter · Tab 확정, Esc 취소,
    Delete 비우기. 칸 안 키는 도면 · 창 단축키로 새지 않는다. 고친 칸 `S.sheetCells` 는 적용 전 편집이라 「적용 안 한 변경」
    셈 · 「적용」(적용값 `cells` — **보내기 전에 지우지 않는다**, 새 epoch · 「처음 상태로」 에서만 비움) · 되돌리기 op `cell`
    에 든다. 칸을 연 채 「처음 상태로」 · 「되돌리기」 를 누르면 누름 시작(`onpointerdown` — 칸을 확정하는 blur 보다 먼저)에서
    열린 칸을 확정 없이 닫는다(`dropOpenSheetCell` — 버릴 글이 「확인만」 으로 나가 `EQ-25` 가 서지 않게). 「되돌리기」
    는 친 글이 칸을 바꾸는 글이었으면 그 누름의 click 을 삼켜(`S.undoSwallow` — 순수 판정 `sheetUndoPress`) 앞 고침까지
    되돌리지 않는다. 표지는 pointerdown 마다 새로 정하고 pointerleave 로 풀지 않으며(터치는 손을 떼면 pointerleave 가 click
    보다 먼저다), 키보드 click(detail 0)은 삼키지 않는다. 잠긴 두 단추는 누름을 받지 않아(`.sle-tiphost > button:disabled` 의
    pointer-events 없음) 다른 곳 누름처럼 칸을 확정하고, 확정이 단추를 풀어도 click 은 감싼 칸에 가 단추 동작은 없다. 「고른 호기」 탭의 그림 열쇠는 보이는 줄 id 모음(정렬)이라 같은 묶음 안 누르기로 표를 다시 만들지 않고, 열린 칸이
    있으면 다시 그리기를 닫을 때까지 미룬다. 칸을 확정하거나(Delete 포함) 칸 되돌리기마다 트리거 `sheetCheck`({mount — 편집기가
    설 때마다 새 id `S.sheetMount`, epoch, seq — 오르기만 함, base — 고친 칸이 마지막으로 빈 seq `S.sheetBase`, cells — 고친 칸
    전부})로 「확인만」 묻는다(`sheetEditSend` — 고친 칸이 없으면 묻지 않고 판정을 걷으며 그 seq 가 다음 base 다. 「처음
    상태로」(`resetSheetEdit`)도 seq 를 올려 그 자리를 잡는다). **잇달아 고친 칸은 묶어 묻는다**(2026-11-20 사용자 결정 Q3 —
    설계 규칙집 7-1, 순수 구획 `// <sheet-send>` · node 시험 `tests/test_space_sheet_send_js.py`): 마지막 고침 뒤 쉼
    `SHEET_SEND_MS`(data `sheetSendMs` — `grid_shared.batch_ms`, 개발 · 측정 사본만 실행 줄 `CAPA_DEV_BATCH_MS`)에 한 번이고, 첫 칸 ·
    칸 되돌리기 · 창 밖으로 초점이 나감(`sheetLeftSoon` — 입력 칸 blur · 창 focusout, 처리기가 끝난 뒤 지금 초점으로 봄 — 창 안
    Enter · Tab · 다른 칸 누름은 묶음) · 「적용」 직전(적용 트리거와 같은 틱이라 한 요청) · 떠나기 신호(`joinLeaving` — 등록 글
    머리에 `grid_shared.leave_js()`) · 창 숨김은 곧바로다. 트리거라 회차 끝 창에서 잃을 수 있어, 보낸 seq 의 판정이
    `SHEET_RETRY_MS` 안에 오지 않으면 회차가 끝나고 `SHEET_QUIET_MS`(화면 탭 줄 `LOST_QUIET_MS` 와 같은 0.6초) 동안 조용한 뒤에
    같은 요청을 한 번만 다시 보내고(회차 표지가 바뀐 때는 마운트에 하나인 뿌리 감시 `S.sheetRunWatch` 가 적는다) 그것도 오지
    않으면 걷는다 — 보낼 것이 남았거나 판정을 기다리는 동안이 떠나기 명부의 busy 다. 「적용」 을 보내면 기다리던 확인의 다시
    보냄을 `SHEET_RETRY_MS` 뒤로 미루고(`sheetSendDefer`), 막힌 칸으로 거부한 판정이 오면 「적용」 때 seq(`S.sheetApplySeq`)까지의
    기다림을 걷는다 — 거부 뒤에 다시 보낸 확인이 같은 막힌 칸을 `EQ-25` 로 한 번 더 내지 않게. 서버는 같은 편집기 · epoch ·
    마운트의 같은 · 옛 seq 를 거른다(`_dispatch_sheet_check` — 세션 칸 `SHEET_CHECK_SEEN_KEY`). 판정은 data
    `sheetVerdict`({epoch, mount, seq, blocked, follow})를 **이 마운트가 마지막으로 보낸 seq** 일 때만 받는다. 막힌 칸으로 거부한
    적용은 data `sheetRefused`({epoch, nonce, blocked, follow})를 nonce 마다 한 번 받는다. 둘 다 막힌 칸(판정한 글이 지금 친 글과
    같을 때만)을 빨갛게 짚고 「적용」 을 잠근다(까닭 「「호기 정보」 막힌 칸 n개」). 색은 팔레트 `cell-*`(설비 마스터 표 토큰
    `GRID_*`)다.
  - 보기(층 · FAB) 도구 줄의 선택 줄(`.sle-pick`)은 고른 것이 없으면 비어 있다 — 누르기 · 키보드 · 확대 안내는 그 빈 칸의
    풍선(`pickTip` → `title`)이고 자리에 글로 세우지 않는다(설계 규칙 UI-TXT-01, Guide 「층 열기」 · 「호기 정보」).
  - 편집 상태는 브라우저가 쥐고 `적용` 때 한 번 보내며 검증은 서비스(`parse_editor_apply`)다. epoch(내용 지문)가
    같으면 편집·배율을 지키고, 옛 epoch 로 온 적용·블록 열기(`on_navigate_change`)·호기 누르기(`on_pick_change`)는
    버린다. 옛 epoch 의 적용이 방금 받아들인 적용과 같은 입력이면(새 epoch 를 받기 전 같은 「적용」 의 둘째 누름)
    경고 없이 버리고 첫 성공 알림이 남는다(`write_guard.just_submitted`).
  - FAB 블록 글자 `linkStats` 의 `inactive`(비활성 층의 짧은 사유)가 있으면 JS 가 그 블록을 `is-inactive` 로 —
    팔레트 `block-off` 면 + `#sle-hatch` 빗금 + `muted` 글자(고른 색·「글자 색」 인라인을 달지 않는다)로 그리고, 보기에서는
    `opensFloor` 가 거짓이라 열지도 고르지도 않으며(누름 갈래는 블록 종류로 `lastViewOnBlock`) 초점·역할을 걷는다. 편집에서는
    옮기기·연결은 되고 `[열기]` 만 꺼진다(`syncInspector`).
  - 호기 값은 `_clean_items`·첫 회차 `readUnit`·같은 epoch 합치기 세 경로를 모두 지난다. CSS 의 `--sle-*` 는 모두
    `_palette()` 에 둔다(블록 색 대비는 `tests/test_design_tokens.py`). 보기 높이는 localStorage 에만 둔다.
  - **반입 일정**(층 보기만 — data `arrivalDates` 를 실은 회차, 2026-11-12 Space 보드 답 1-1 ~ 1-6): 그날 반입 전이고
    보이는 호기(`arrivalShown` — 칠한 `is-pre` · `__visible`)에 `27.05.09` · 「지연」(굵은 tspan) · 「미정」 을 쓴다. 순수
    함수는 `// <view-arrival>` 구획(`arrivalWords` · `groupArrivalMode` · `arrivalBoxLines` · `arrivalPill`, node 시험
    `tests/test_space_arrival_js.py`)이다. 낱 호기와 글이 다른 묶음('each')은 상자 안 이름 아래(`syncArrival` — 이름 0.82배,
    7px 아래면 숨음), 글이 모두 같은 묶음('once')은 Main 설비명 알약 둘째 줄이다(`drawGroupNames` 가 묶음마다 `S.arrivalModes`
    를 정하고 모듈 상자를 다시 맞춘다 — 가운데 이름 글자 상한은 두 줄 높이 `ARRIVAL_PILL_TALL`, 위 알약이면 「필요 단축」
    배지가 그만큼 더 비킨다). 같은 epoch 에서 켜고 끄면(`S.lastArrival`) 묶음 자리와 모든 호기를 다시 맞춘다. 반입 전 호기
    풍선은 토글과 상관없이 「반입 일정 …」 을 붙인다(`arrivalTipWords`).
  - **Main 설비 모듈 묶음**(편집기 모듈 + 숨은 모듈이 둘 이상, 2026-10-23 사용자 요청)은 묶음 범위(이 층 도면에 선
    모듈의 바깥 상자)만 고치고 안은 바둑판 자동 배치다 — 모듈 2·3 은 가로 한 줄(열 n·행 1), 넷부터 ⌈√n⌉ 열(넷이면
    2×2, 2026-10-23 사용자 답). 바둑판 순수 함수는 `// <module-tiling>` 구획(`moduleGrid`·`moduleCells`·
    `tileModuleGroup`·`assignModuleCells`·`tileDeviation`·`relaidGroup`·`groupLabelDefault`)이고 파이썬 정본
    `space_layout_edit` 과 같은 규칙이다(`tests/test_space_module_group.py` 가 node 로 대조). 서랍에서 여러 덩이를 한
    번에 놓을 때 덩이끼리의 격자(`trayPlan`)는 이것과 따로 ⌈√n⌉ 열 그대로다(셋이면 2×2). 모듈 하나만 옮기거나 키우는 길은 없다 — 끌기·방향키·
    X·Y 칸은 `movePlan`(묶음은 범위), 크기(폭·높이 칸·Ctrl+방향키)는 `setSizes`, 범위 테두리 손잡이는
    `mode: 'range'`(`sle-range-handle`, 모듈 상자 손잡이는 `is-module` 로 숨김)이고 셋 모두 `relayGroup` 으로 다시
    놓는다. 선택은 묶음당 한 대(`onePerGroup`), 고른 묶음 범위 안의 빈 칸을 눌러도 그 묶음을 끈다(`pickedRangeAt`),
    빼기·다른 층 보내기·서랍 놓기는 묶음째다. 층 보기에서 고른 묶음(이 층에 그린 모듈 둘 이상 — `viewBundled`)은 모듈
    후광 없이 묶음 둘레 실선 `is-bundle` 하나이고(2026-11-12 Space 시안 보드 답 5-1), 그린 모듈이 하나뿐인 묶음은 낱 호기처럼
    후광이다. 묶음 조작 하나가 되돌리기 한 번이다.
    - 칸 자리는 지금 자리를 지킨다(`assignModuleCells` — 이미 바둑판이면 이름 차례와 상관없이 제 칸, 옛 묶음은 가까운
      칸). 자연 정렬은 서랍에서 새로 놓을 때(`naturalSlots`)와 좌표 없던 형제에만 쓴다. 「n등분이 아님」 판정도 칸
      모양(`tileDeviation`)이다.
    - 바둑판이 아닌 옛 묶음은 읽을 때 바꾸지 않고, 범위가 실제로 바뀌는 첫 조작(또는 「범위에 맞춰 n등분」)에 그 범위로
      다시 놓는다. 범위가 눈금까지 그대로인 조작(벽에 막힌 방향키·제자리에서 뗀 끌기·같은 숫자)은 다시 놓지 않는다.
      1·2차 규칙(셋도 2×2)으로 놓인 모듈 셋 묶음도 이 옛 묶음이다(「3등분이 아님」 — 처음 만질 때 한 줄로 선다).
    - 숨은 모듈(`data.ghosts` → `S.ghosts`, 파이썬 `EditorInputs.ghosts`)은 그리지 않고 고르지 않지만 칸 수·자리에 들고
      (고른 묶음에서 점선 `sle-ghost-cell`) 묶음과 함께 옮겨져 적용값 `ghosts` 로 간다. 되돌리기·끌기 취소는 `itemOf` 로
      숨은 모듈도 되돌리고, 묶음 이름을 바꿔도 처음 Main 설비 이름(`groupKeyOf`)으로 이어진다. 보기 화면은 그대로다.
      묶음째 도면에서 빠지면(빼기·Delete·다른 층 보내기) 숨은 모듈은 처음(편집기에 실린) 자리로 돌아간다
      (`restoreGhosts`, 빼기·보내기와 같은 되돌리기 기록) — 옮기지 않고 바로 뺀 것과 같다.
  - **편집 조작 넷**(2026-10-23 사용자 요청, 층·FAB 편집 공통). 순수 판정은 `// <edit-tools>` 구획(`nearestSnap`·
    `guideSegments`·`namePrefix`·`borrowedSize`·`trayRangeIds`·`pasteShift`·`freeLinks`)이고
    `tests/test_space_editor_tools.py` 가 node 로 돌린다(둘레 함수는 선언 그대로 떼어 돌린다).
    - 정렬선: 끌기·크기(`alignDrag`)·서랍·팔레트 놓기·붙여넣기(`dropSpot`)에서 움직이는 것(모듈 묶음은 범위 — 1차 규칙)의
      왼·가운데·오른 x 와 아래·가운데·위 y 가 화면(viewBox)에 걸친 다른 호기·요소(묶음은 범위, `guideTargets`)의 선과 화면
      6px 안이면 그 선에 붙는다. 격자보다 먼저이고 Alt 면 붙지 않는다. 선은 맨 위 `sle-guides` 층에 긋고(색 `guide` =
      `tokens.SPACE_GUIDE`) 놓으면 지운다. 크기 바꾸기는 움직이는 변만 본다.
    - 크기 불러오기: 서랍에서 크기 없는 호기만, 같은 앞 3자리(공백은 파이썬 `str.strip` 의 것)·같은 종류(모듈 / 그 밖 —
      모듈은 편집본 전체에서 Main 설비 행이 둘 이상, `newUnit.moduleParents`) 가운데 이번 편집에서 마지막으로 놓은
      것(`S.placedLog`, 지금도 서 있고 층 가운데 크기 어림이 아닌 것) → 편집본에서 설비명 자연 정렬이 가장 뒤인 것
      (`newUnit.prefixSizes` = 파이썬 `prefix_sizes`) → 이 층 가운데 크기(`defaultSize`). 빌린 크기는 `sizeGuessed`·
      `sizeFrom` 이고 상태 줄에 「크기를 … 에서 불러옴」을 쓴다(`trayPlan`).
      「마지막으로 놓은 것」 기록(`S.placedLog`)은 적용 뒤에도 지우지 않고 같은 편집기 화면(마운트)이 이어 쓴다. 기록은
      `host.__sle` 에 있고, 적용 뒤 다시 맞춘 새 epoch 가 상태를 비울 때도 이 기록은 건드리지 않는다 — 「이번 편집」 은 적용
      한 번이 아니라 같은 편집기 화면이 마운트된 동안이다.
    - 서랍 Shift 범위(`pickChip`): 기준 칩(마지막으로 그냥·Ctrl 로 누른 칩, `S.trayAnchor`)부터 누른 칩까지 지금 보이는
      차례, Ctrl+Shift 는 더하기, 묶음 칩은 한 칸.
  - **키보드**(2026-10-26 E2E — 마우스 없이는 호기 하나를 고르거나 칩을 놓을 길이 없었다). 호기 상자(편집·층 보기)와 편집의
    도면 요소는 Tab 자리(`tabindex`·`role=button`·`aria-pressed`)이고 Enter·Space 가 누르기다(`host.onkeydown` — 편집은
    그것 하나, Ctrl·Shift 는 `toggleSelected`; 층 보기는 `select` + `notePick`). 서랍 칩은 이름(`sle-chip-name`)이 단추라
    「×」 와 나란하다 — Enter 는 보이는 도면 가운데(서랍 몫 `trayReserve` 를 뺀)에 놓고 초점을 놓은 호기로(`placeChipByKey`),
    Space 는 `pickChip`. 초점 테는 화면 px 로 띄운 rect(`sle-focus-ring`, `FOCUS_GAP_PX`)다 — SVG 안의 outline 은 배율로
    커진다. `renderItems` 는 그리기 전 초점(`focusSpot`)을 같은 id 의 새 노드로 돌려주고(`restoreFocus`), 칩이 사라졌으면
    (「×」 추가 취소 — 낭독 이름은 「<호기> 추가 취소」) 같은 자리의 이웃 칩, 없으면 검색 칸에 둔다(BODY 로 빠지지 않게). 시험은
    `tests/test_space_editor_keyboard.py`(되돌리기는 node).
    - 도면 요소 복사·붙여넣기(`copyMarks`·`pasteMarks`): 호기는 복사하지 않는다. 클립보드는 범위별 sessionStorage
      (`capa.space.clipboard.<floor|fab>`) + 페이지 안 쪽지(`window.__capaSpaceClipboard`)이고 모든 읽기·쓰기가 try 안이다.
      마우스가 도면 위면 그 자리가 묶음 가운데(`dropSpot`), 아니면 원본에서 max(격자, 1)씩 비켜(거듭하면 더) 붙인다. 영역
      안으로 밀고 새 id·되돌리기 한 번이며 층 블록은 빈 층(`freeLinks`)을 가리킨다. 글 칸 입력 중에는 가로채지 않는다.
      사본이 같은 종류 요소와 자리·크기까지 똑같이 겹치지 않는다(`stacksOnMarks`) — 마우스 자리가 원본 그대로면 비켜
      붙이기로 넘기고, 비켜 붙일 때 영역 끝에 막힌 축은 반대쪽으로 비키며(`pasteShift`), 그래도 겹치면 붙이지 않고 알린다.
      복사·붙여넣기 알림(`S.flash`)은 새 epoch 에서 지운다.
  - **모양·저장 셋**(2026-10-23 사용자 요청, 층·FAB 공통 — 3번째는 층만). 자리 계산은 `// <layout-look>` 구획
    (`zoneTagX`·`groupNameSpot`·`groupNameSize`·`shownRange`)이고 `tests/test_space_editor_tools.py` 가 node 로 돌린다.
    - 영역 테두리 모양(`borderStyle` 점선·실선)·이름표 정렬(`labelAlign` 왼쪽·가운데·오른쪽, 위 변 꼬리표)은 처음 값이 지금
      모습(점선·왼쪽)이고 영역 선택 칸의 `테두리`·`글자 정렬` 로 고른다. 고른 영역의 강조는 테두리 모양을 바꾸지 않고
      바깥 강조 테(`sle-zone-select`)로 따로 보인다. 읽기·바뀜 판정·적용값·복사·되돌리기 기록에 모두 든다.
    - 반입 예정(실물 없음) 테는 3.5px 점선(범례 견본 3px, `space_layout._mark_swatches`), TEST 면은 연한 남색에 검정
      글자다(`tokens.SPACE_LINE_TYPE_FILLS`·`_INKS` — 다른 면과의 ΔE 는 `tests/test_design_tokens.py`).
    - Main 설비명: 모듈 묶음(편집기 모듈 + 숨은 모듈 둘 이상, `moduleGroups`)의 범위에 `sle-group-names` 층(눌림 없음)으로
      알약 바탕 + 모듈 이름보다 굵은 글자를 그린다. 위치는 가운데(범위 정가운데)·위·아래(범위 바깥 바로 위·아래)이고,
      고른 위치(저장된 행 포함)는 묶음 열쇠(`groupKeyOf`)마다 `S.groupLabels` 에 쥔다. 고른 적이 없는 묶음은 모양의 처음
      위치(`groupLabelDefault` — 한 줄 묶음(모듈 2·3)은 위, 그 밖은 가운데, 2026-10-24 결정 (e))다. 모듈 수는 편집기는
      숨은 모듈까지(`groupCounts` = 파이썬 `module_group_sizes`), 보기 화면은 그리는 모듈만 센다(숨은 모듈을 받지 않아 드물게
      다를 수 있다). 묶음을 고르면 선택 칸
      `Main 설비명` 에서 바꾼다(되돌리기 한 번, `op: 'groupLabel'` — 처음 고른 것을 되돌리면 「고른 적 없음」으로). 적용값 `groupLabels` 는 이 층에 남는 묶음마다 [{group: 열쇠, position}](다른 층으로 보낸 묶음은
      빠짐)이다. `drawSelectionBox` 가 부르므로 옮기기·크기·배율을 따라가고, 보기 화면은 기준일에 묶음의 모듈이 하나도
      보이지 않으면(`__visible`) 이름도 숨기며 일부만 보이면 보이는 모듈의 바깥 상자(`shownRange`)에 세운다. 글자는 화면
      12px × 글자 배율 s(아래 「배율 글자」)에서 범위 폭에 맞춰 줄고 가운데는 범위 높이의 0.16 배까지이며 7px(`UNIT_LABEL_MIN_PX`) 아래면 숨는다 — 다만
      모듈 칸 이름표가 하나도 서 있지 않은 묶음의 가운데 이름은 7px 알약이 범위 안에 들면 7px 로 선다. 위·아래 알약이
      영역 위·아래 끝을 넘으면 범위 안쪽 띠로 뒤집는다(`groupNameSpot`). 반입 일정 두 줄 알약은 바깥으로 더 자라는 둘째 줄
      높이(fd × 1.25 — `extra`)까지 넣어 잰다 — 들지 않으면 안쪽 띠로 뒤집는다.
  - **베이·머리 크기·배율 글자**(2026-11-03 사용자 요청 — 사양 (나)). 순수 판정은 `// <mark-look>`(모양 값 `cleanLook`·`lookText`·
    `lookValue`, 그리기 `arrowShape`·`bayShape`·`placeLocal`·`bayAutoSize`, `bayNumber`·`lineDash`)와 `// <text-scale>`
    (`textScale`·`calloutScale`·`scaledText`) 구획이고 `tests/test_space_mark_look_js.py` 가 node 로 돌려 파이썬
    `floor_layout_mark.mark_look`·`bay_label` 과 대조한다.
    - 베이(`bay`, 층만 — FAB 에는 없다): 0° 는 여는 쪽이 왼쪽인 ⊃ 꼴(팔 y = lh/4 · 3lh/4)이고 머리는 아래 팔 왼쪽 끝에서 왼쪽을
      향한다. 90° 돌리기(`rotateMark`)와 좌우 뒤집기(`look.flip` — 돌리기 앞 가운데 축 거울)·상하 뒤집기(180° 돌림 + 좌우
      뒤집기, 같은 상자)로 여덟 방향이다. 가운데 글은 「B<번호>」 — 이름표 칸에 번호만 쥐고(`bayNumber` = 파이썬 `bay_label`,
      「B80」·「b 80」·「BB80」 → 「80」 — 앞의 B 는 모두 떼서 다시 거쳐도 같다, 10자) 그릴 때 「B」 를 붙인다. 글은 머리를 비킨 두 팔 사이 틈 가운데에 돌리지 않고 가로로 서고
      (자동은 틈 맞춤 — 고를 수 있는 가장 큰 크기 24 의 배율 크기까지), 막는 요소가 아니며 상자 전체가 잡힌다(동선과 같다).
    - 모양 값 `look`(동선·베이): 머리 크기 `head`(「너비·길이」 S·M·L — 동선의 MM 이 옛 그림 그대로), 선 색 `line`(강조색·진하게·
      영역 색 키 — 테마 토큰), 굵기 `lineWidth`(화면 px, 동선은 처음 값 없이 상자 높이를 따름), 모양 `lineStyle`. 처음 값인 키는 쥐지
      않고(`cleanLook`) 바꿀 때마다 새 객체로 갈아 끼운다 — 읽기·처음 값 기록(`snapshot`)·바뀜 판정(`lookText`)·적용값·복사·새 요소·
      되돌리기에 모두 든다. 선택 칸 「머리 크기」(3×3 갤러리 — 행 너비 좁게·보통·넓게, 열 길이 짧게·보통·길게)·선 색·굵기·선 모양·
      뒤집기는 고른 것 가운데 동선·베이 모두에 걸고 되돌리기 한 번이다(`setLooks`·`flipMarks`). 뒤집기 단추는 선 칸이 아니라
      아래 「도형」 의 돌리기·뒤집기 줄(`.sle-turns`)이다.
    - 배율 글자: 도면에 붙은 글자(요소 이름표·글자 요소·층 블록 글·베이 글·호기 이름표 상한 14·Main 설비명 상한 12)는 화면 px =
      기준 크기 × s, s = 도면 1칸당 화면 px(ppu) ÷ 8(위 2배)이고 화면 6px 아래면 숨긴다(영역은 꼬리표 상자째) — 다만
      호기 이름표·Main 설비명은 지금처럼 7px(`UNIT_LABEL_MIN_PX`) 아래에서 숨는다. 고른 글자 크기는 「도면
      1칸이 화면 8px 일 때의 크기」 다(저장값은 그대로). 표지(필요 단축 배지·견주기 꼬리표)는 s 를 0.75~1.25 로 묶고 크기로는 숨기지
      않는다. 손잡이·초점 테·「!」·겹침 꼭지·선 굵기는 화면 px 그대로다. 확대·이동마다 `applyView` → `position` → `drawMark`·
      `drawSelectionBox` 가 다시 잰다.
  - **도형**(2026-11-03 사용자 요청 — 사양 (나2), 층·FAB). 한 종류 `shape` 에 프리셋 키 `look.shape` 아홉(사각형·원·ㄴ자·ㄷ자·
    테·삼각형·마름모·십자·블록 화살표 — `SHAPE_PRESETS`, 넣는 크기·모양 조절 값 [하한, 상한, 처음 값]·이름·돌림 뜻이 프리셋마다)
    이다. 순수 판정은 `// <mark-look>`(프리셋 표·`cleanLook` 의 `adj`·`fillAlpha`·도형 선 색, `shapeOf`·`shapeAdj`·
    `shapeFillOf`)와 `// <shape-geometry>`(경로 `shapePath` → {d, rule, pts} — 테만 evenodd, 노란 손잡이 `shapeHandles`·값
    되돌림 `handleValue`·`unplaceLocal`, Shift 비율 유지 `keepAspect`, 손잡이 비키기 `nudgeHandle`)이고
    `tests/test_space_shape_js.py` 가 node 로 돌려 파이썬 `mark_look`·`SHAPE_ADJUST` 와 대조한다.
    - **모양 조절 값의 기준**(2026-11-04 Space 결정 보드 답 — 「ㄴ자의 오른쪽으로 뻗은 부분의 길이만 늘이는 편집」): 두께·둥글기·
      머리 길이는 엑셀처럼 **짧은 변** min(lw, lh) 의 비율이다 — ㄴ자 세로 · 가로 팔, ㄷ자 등 · 팔, 블록 화살표 머리 길이(처음 값
      0.7 — 넣는 크기 10×5 에서 옛 폭 기준 0.35 와 같은 그림), 사각형 둥글기 · 테 · 십자는 처음부터 그랬다. 삼각형 꼭짓점 자리는
      폭, 블록 화살표 몸통 두께는 높이(머리 너비) 기준 그대로다. 무엇의 비율인가는 프리셋 표의 `base`(파이썬 `SHAPE_ADJUST_BASE`
      — `min` · `min-w` · `min-h` · `w` · `h`)다.
      - **상한은 그 축 길이까지**(재검 c-4 — 짧은 변에 상한 0.95 를 그대로 두면 넓은 ㄴ자의 굵은 세로 팔 · 긴 블록 화살표의 긴
        머리를 못 그렸다): `min-w` · `min-h`(ㄴ자 두 팔 · ㄷ자 등 · 팔 · 블록 화살표 머리)는 상한이 상한 × 그 축 ÷ 짧은 변이다
        (`adjCap` — 엑셀처럼). 저장 꼴은 상한 × `SHAPE_STRETCH_MAX`(100)까지 받고(파이썬 `_shape_adjust` 도 같다), 그릴 때
        상자의 상한으로 묶는다(`fitAdj` — 칸으로 상자를 좁혀 상한이 줄어도 늘 상자 안, 저장 값은 그대로). 노란 손잡이 값 ·
        선택 칸 %(입력 상한 · 보이는 값은 묶은 값)는 0.01 단위로 내린 상한(`adjTop`)까지다.
      - **크기를 바꿔도 두께 그대로**(재검 b-1 · c-1 — 짧은 쪽 팔을 늘이면 짧은 변이 바뀌어 두 팔이 함께 굵어졌다): 비율 없이
        크기를 바꾸면(변 · 모서리 손잡이, 폭 · 높이 칸, Ctrl+방향키, 서식 붙이기의 크기) 짧은 변 기준 값을 옛 짧은 변 ÷ 새 짧은
        변 배로 다시 셈해(`resizedAdj` — 하한 ~ 새 상자 상한, 0.01 단위) 그린 두께 · 둥글기 · 머리 길이를 지킨다(`sizedLook` —
        끌기는 늘 처음 상태에서 다시 세고, 되돌리기 한 번에 크기와 함께 돌아온다). 짧은 변이 그대로면 값도 그대로다. 0.01
        단위라 두께는 새 짧은 변의 0.005 배 안에서 지킨다(눈금 0.1 아래). Shift 모서리 비율 유지는 모두 같은 배율이라 값을 그대로
        두어 두께도 함께 커진다. 폭 · 높이 기준 값(삼각형 꼭짓점 · 블록 화살표 몸통)은 비율 그대로다.
      - 저장 꼴(`look.adj`)은 그대로다 — 뜻만 바뀌었다(옛 폭 · 높이 기준 값을 옮겨 적지 않는다. 마지막 사내 배포 202610271800
        에는 도형이 없어 사내 저장분이 없다. 사본 · 검수 샘플에 이 기준 전에 저장한 비정사각 도형은 ㄴ자 · ㄷ자 두께 · 블록 화살표
        머리가 달라 보일 수 있다).
    - 꾸밈이다 — 막는 요소(`blocks`)·겹침 경고에 들지 않고 **호기 아래 층**(`sle-zones`, 영역과 같은 층 — `onZoneLayer`)에
      그린다. 잡기는 경로 그대로(`sle-shape-hit` — 채우기·빗금이 있으면 안쪽과 12px 테 띠, 없으면 테 띠만 — 빈 안쪽 끌기는 고르기
      사각형)이고 상자의 빈 귀·`sle-mark-box` 는 잡히지 않는다. 이름표는 가운데 가로(돌리지 않음, 자동은 상자 맞춤 — 24 의 배율
      크기까지)이고 잡힌다.
    - 호기 아래 층(영역·도형)에서 하나만 고른 것의 손잡이는 맨 위 층 `sle-overlay` 에 다시 세운다(`proxyHandles` — `data-for`,
      제 그룹 안의 것은 CSS 가 감춘다) — 호기가 덮은 귀·변에서도 잡힌다. 고른 도형 하나의 노란 손잡이(`sle-adjust`, 토큰
      `SPACE_ADJUST` + 도면 글자색 테)는 끌기 `mode: 'adjust'` — 잡은 자리 차이(`grab`)를 지켜 포인터를 제자리 좌표로 되돌려
      값을 내고(`adjustedLook`), 놓을 때 바뀌었으면 되돌리기 한 번이다. 크기 손잡이와 겹치면 축을 따라 비켜 그린다.
    - 선택 칸 「도형 서식」(`syncShapeProps` — 여럿이면 모두에, `setShapes` 되돌리기 한 번): 「도형」 바꾸기 갤러리(`look.shape`
      만 바꾸고 `adj` 를 새 프리셋 처음 값으로 — 크기·채우기·선·글자 그대로), 모양 조절 %(한 프리셋일 때만), 채우기 색(요소
      `color` — 영역 색 여섯 · `ink` · `surface`), 투명도(엑셀처럼 100 − `fillAlpha`), 선 색(`auto` 채우기 색의 진한 쪽 ·
      `none` · `ink` · 여섯)·굵기·모양, 빗금(`hatch`). 도형 모서리 Shift 끌기는 비율 유지다(Shift 를 누른 채 손잡이를 잡아도 더하기
      고르기가 아니다).
    - **돌리기·뒤집기 줄**(`.sle-turns`, 2026-11-04 Space 결정 보드 답 — 「도형 반전 기능도 추가하자」: 뒤집기가 도형 서식 칸 맨 끝 ·
      베이 선 칸 끝에 있어 찾지 못했다)은 요소 속성 칸(이름표) 바로 밑 · 선 · 도형 서식 칸 앞이다 — `90° 돌리기`(돌릴 수 있는 요소
      하나 — 대칭 도형은 숨김)와 `좌우 뒤집기` · `상하 뒤집기`(그림 + 키 풍선, 고른 것 가운데 뒤집을 것 `canFlip` — 도면에 선 베이 ·
      비대칭 도형 — 이 하나라도 있으면, 여럿이어도)이고 아무것도 없으면 줄째 숨는다(`syncTurns`). `flipMarks(axis)` 가 고른 것
      가운데 `canFlip` 모두를 되돌리기 한 번에 뒤집는다(좌우 = `look.flip`, 상하 = 180° 돌림 + 좌우, 같은 상자). 키는 `Shift+H` ·
      `Shift+V`(순수 `// <flip-key>` `flipKeyOf` — 수정 키는 Shift 하나만 · 글쇠 자리 code KeyH·KeyV · IME 조합 중 비킴 — 서식 키
      Alt/Ctrl+Shift+V · 요소 복사 Ctrl+V 와 겹치지 않는다, `tests/test_space_flip_js.py`)이고 `host.onkeydown` 의 서식 키 뒤 · 요소
      복사 앞이다. 뒤집을 것이 없으면 키를 막지 않는다. 보기 화면에는 없다. 뒤집기는 서식이 아니다(서식 붓이 옮기지 않는다).
    - 넣기는 도면 요소 칸 「도형 ▾」 갤러리 — 누르면 보이는 가운데, 끌면 놓은 자리(`ghostDrag`·`dropSpot`), 키보드 click 도.
      읽기(`readMark` — 모르는 채우기 색은 파랑)·바뀜 판정·적용값·복사(`clipOf`)·되돌리기에 모양 값·색·빗금이 함께 간다.
  - **발자국**(2026-11-12 Space 시안 보드 6-1 ~ 6-6 — 층·FAB). 종류 `footprints` 는 길을 따라 놓은 발 모양 줄이고 **선 꼴 요소**다
    — 상자의 한 축이 길이, 다른 축이 띠(3칸 고정 — 발 크기는 상자를 따르지 않는다). 순수 판정은 `// <foot-geometry>`(모양 여섯의
    윤곽 자료 · `footCount` — max(1, ⌊길이 ÷ 걸음⌋), 걸음 좁게 2.6 · 보통 3.5 · 넓게 4.8 · `footprintsShape` — 첫 발은 시작 끝에서 반
    걸음, 남는 길이는 끝 쪽이라 늘이면 앞 발은 그대로이고 새 발이 끝에 는다 · `footLineEnds` · `footFitted`)이고
    `tests/test_space_footprints_js.py` 가 node 로 돌려 모든 모양 × 간격 × 길이가 띠 · 길이 안인지(곡선 조절점까지) 본다.
    - 선 꼴 편집: 손잡이는 걷는 축 두 끝만 둥글게 서고(`positionHandles` — 작아도 숨기지 않는다) 끌면 길이만 바뀐다(`resizeTo` —
      `FOOT_MIN_LENGTH` 아래로 줄지 않음). 띠는 `fit` 한 곳에서 묶는다(`footFitted` — 숫자 칸 · Ctrl+방향키 · 서식 크기 · 붙여넣기 ·
      넣기 · 돌리기가 모두 지난다 — 띠 쪽 값은 바뀐 것이 없어 되돌리기 기록도 늘지 않는다). 고르면 점선 상자 대신 가운데 축 점선
      (`sle-foot-axis`)이다. 발자국 하나를 고르면 숫자 칸이 X · Y · 「길이」 셋이다(띠 칸 숨김 — `footSyncFields`). 자유 각도는 없다
      — 90° 돌리기 · 좌우/상하 뒤집기(`canFlip`, 뒤집으면 걷는 쪽이 거꾸로)이고 꺾인 길은 조각 여럿으로 잇는다.
    - 선택 칸: 선 색은 동선 · 베이와 같은 칸(`isLined` — 발자국만이면 머리 크기 · 굵기 · 선 모양 숨김, 섞어 고르면 그 셋은 동선 · 베이
      값만 본다), 그 아래 「발자국 서식」(`footSyncProps` — 발 모양 그림 판 `sle-foot-gallery` · 간격 목록, `setLooks` 되돌리기
      한 번). 이름 줄은 「발자국 · 발 n개」(`markTitle`). 겹은 동선처럼 호기 위(`onZoneLayer` 밖)이고 막는 요소가 아니다.
    - 서식 붓: 발자국끼리는 길이 · 선 색 · 간격을 옮기고 발 모양 · 뒤집기는 옮기지 않는다. 동선 · 베이 · 도형과는 선 색만 오간다
      (발자국 서식은 굵기 · 선 모양을 담지 않아 동선의 자동 굵기를 건드리지 않는다).
  - **겹친 순서**(2026-11-12 Space 요청 7 — 보드 7-2 ~ 7-5, 1단 요소 차례 · 2단 호기끼리 · 호기 위로(설비 `0034`), 층·FAB 편집).
    그리는 겹은 셋이고(호기 아래 `sle-zones` 영역·도형 → 호기 `sle-items` → 호기 위 `sle-marks` 그 밖의 요소 · FAB 층 블록 · 호기 위로
    올린 영역·도형 `raised`) 겹 안 차례가 `S.items` 차례다 — 요소는 저장 차례(`source_row_no`), 호기는 파이썬이 층 순서 표로 줄 세워
    보낸 차례(`floor_layout_stack.ordered_items`), 올림은 요소 payload 의 `raised`(`readMark` — 복사본 · 새 요소는 처음 겹, `clipOf`
    가 싣지 않는다). 그리는 층은 `onZoneLayer`(영역·도형이고 올리지 않은 것)이다. 순수 판정은 `// <stack-order>` 이고
    `tests/test_space_stack_order_js.py` 가 node 로 돌린다 — 종류 → 겹 한 곳(`STACK_TIERS` · `tierOf`, 올린 것은 위 겹), 호기 겹
    (`stackUnits` — 모듈 묶음째 덩이, 설계 A (가)), 요소 겹(`stackDeck` — 아래 겹 · 호기 겹 하나 · 위 겹을 한 줄로 보고 올릴 수 있는
    영역·도형 `raisable` 만 호기 겹을 넘는다, 설계 C (가); FAB 은 `raisable` 이 없어 겹 안만, 설계 F (가)), 둘을 합친 새 차례 ·
    올림(`stackPlan` — 「앞으로 · 뒤로」 는 그 쪽에서 겹친 것 하나를 넘고 「맨 앞 · 맨 뒤」 는 끝으로, 그 쪽에 겹친 것이 없으면
    null. 예외 하나 — 고른 것에 올린 영역·도형이 있으면 막혀도 「뒤로」 는 그것을 아래 겹 맨 위로, 「맨 뒤로」 는 고른 영역·도형을
    아래 겹 맨 아래로 내려 올림을 푼다(`stackDeck` 의 `stuck`, 2026-11-13 확인 보드 1 (가) — 올림은 그림에 안 보이는 저장 상태라
    남으면 나중에 밑으로 온 호기를 덮는다)), 위 겹 요소가 호기 · 아래 요소 위에 막혀 내리지 못함(`stackPinned` → 풍선 `KEEP_ABOVE_REASON`), 순서 키(`orderKeyOf`)다.
    선택 칸 「순서」 줄(`.sle-order` — 돌리기·뒤집기 줄 밑, 단추 넷 `sle-order-step`)은 고른 것에 호기나 도면 요소가 있을 때 서고, 끝에
    닿은 쪽 단추와 `data.orderEditable` 거짓(가정 설비 시나리오 — `orderLock` 풍선)은 `lockWith` 로 잠근다(`syncOrder`). 단추·키
    (`Ctrl+Shift+]` · `Ctrl+]` · `Ctrl+[` · `Ctrl+Shift+[`, 서식 · 뒤집기 키 뒤)는 `stackOrder` 한 길이고 되돌리기 한 번(`op: 'order'`
    — 차례와 올림 `raised` 를 함께)이다. 겹마다의 요소 차례 · 호기 차례 · 올림 가운데 하나라도 처음과 다르면 `markChangeCount` 가
    한 건을 더하고(`markOrderChanged`), 적용이 새 차례의 `marks` 를, 호기 차례 · 올림이 바뀌었으면(`stackChanged`) `stack`
    (`{units: 도면 위 호기 아래 → 위, raised}` — FAB 은 없음, 새 호기는 `changes` 와 같은 지금 이름이고 열쇠가 아니다)을 함께
    보낸다. 올린 도형은 `is-raised` 라 안쪽 누르기가 지나간다(`.sle-mark.is-raised .sle-shape-hit` — 설계 D (가), 영역과 같다).
    지운 요소 되돌리기는 지운 자리(`op.at` → `restoreItem`)이고, 누를 때 끌 준비로 겹 맨 위에 붙인 호기 · 요소는 손을 떼면 제 차례로 돌아간다(`restackMarks`). 올린 영역은 이름표 덮임 판정
    (`syncZoneTag`)을 하지 않는다(호기 위라 늘 제자리).
  - **서식 복사·붙여넣기**(2026-11-03 사용자 요청 — 사양 (다), 층·FAB 편집). 엑셀 서식 붓이다. 순수 판정은 `// <format-paint>`
    (`formatOf` — 서식 {kind, module, size(자기 방향), paint, text}, `formatPatch` — 받는 쪽에 붙일 {size, fields, look} 또는 null,
    `patchedLook`, 저장소에서 읽은 서식 거르기 `formatFrom`)이고 `tests/test_space_format_paint_js.py` 가 `// <mark-look>` 과 함께
    node 로 돌려 종류 × 종류 × 붙일 것 체크 모든 쌍을 사양 5-1 표 모형과 견주고 붙인 요소가 파이썬 검증을 지나는지 본다.
    - 키: `Alt+Shift+C`(macOS ⌥+⇧) = 고른 것의 기준(`S.selected`) 하나를 담기, `Alt+Shift+V` = 지금 고른 것 모두(도면에 선 것, 담은
      원본 하나는 빼고 — `formatOrigin`)에 붙이기. `Ctrl(⌘)+Shift+C/V` 도 브라우저가 넘겨주면 같은 갈래다(둘 다 — 사양 D3, 2026-11-04
      사용자 「권장대로」: 실제 Chrome 에서 Ctrl+Shift+C 는 개발자 도구 검사가 먼저 가져갈 수 있어 기본 키를 Alt+Shift 로 옮겼다).
      판정은 순수 `// <format-key>` 의 `formatKeyOf`(Shift 필수 · Ctrl(⌘)과 Alt 가운데 **하나만**(AltGr = Ctrl+Alt 는 아님) · 글쇠
      자리 `code` KeyC·KeyV — Alt 조합의 `key` 는 macOS 「Ç」 처럼 바뀐다, 다른 자리일 때만 `key` · IME 조합 중 `isComposing` 은
      비킴)이고 `tests/test_space_format_paint_js.py` 가 node 로 돌린다. `host.onkeydown` 에서 글 칸 가드(`typing`) 뒤·요소 복사 갈래
      **앞**이고, 요소 복사 Ctrl+C/V 는 Shift 가 없을 때만이라 겹치지 않는다. Esc 는 든 붓을 먼저 내린다. Windows 의 Alt+Shift(입력
      언어 바꾸기)와 부딪치면 Ctrl+Shift+C/V 나 붓 단추를 쓰라고 Guide 에 적는다(단축키 판은 두 키를 한 줄에).
    - 왼쪽 칸 「서식」 묶음(`data-sec="format"`, 선택 다음): 붓 `서식 복사`(`aria-pressed`, 한 번 = 담고 들어 한 번 붙이고 내림,
      두 번(`click` 의 `detail` 2) = 잠금 — Esc·붓 단추·새 epoch 에 내림, 고른 것이 없으면 앞서 담은 서식으로 듦), `붙이기`, 붙일 것
      체크 셋(크기·색·선·글자 — `capa.space.formatPaint.v1`), 담은 서식 한 줄. 붓을 든 `svg.onpointerdown` 은 끌기·손잡이보다
      먼저 누른 것(`paintTargetAt` — 맨 위 층 손잡이·묶음 범위 안 빈 칸 포함)에 붙이고(`paintOnto` — 붙인 것을 고름), 빈 곳은
      `mode: 'marquee', paint: true` 사각형이라 놓을 때 그 안 전부에 붙인다(누르기만 하면 고른 것을 지킴). 무대 커서는 copy.
    - 붙는 칸: 크기는 같은 종류끼리만(요소는 같은 kind, 호기는 낱 호기끼리·Main 설비 모듈 묶음끼리 — 묶음은 범위 크기, 돌린 요소는
      자기 방향 길이·두께로), 면 색은 영역·도형·층 블록 사이(받는 쪽에 없는 값은 건너뜀), 도형 투명도, 선 색·굵기·모양은 도형·
      동선·베이 사이(동선 자동 굵기는 동선에만), 영역 테두리 ↔ 선 모양(점은 영역에 안 감), 머리 크기는 동선·베이, 빗금은 영역·
      도형, 글자 크기·색은 모든 요소, 정렬은 영역끼리. 자리·이름표 글·회전·뒤집기·도형 꼴·모양 조절 값·설비 금지·연결 층은 넣지
      않고 호기에는 크기만이다.
    - `applyFormat` 은 칸·모양 값을 바꾸고 크기는 `sizeEntries`(`setSizes` 의 기록 없는 몸 — 모듈 묶음은 범위째 바둑판)로 바꿔 바뀐
      것 모두를 `pushUndo` 한 번에 담는다(되돌리기 한 번). 붙인 것은 지금 바뀜 판정(`isChanged`)·적용값·저장으로 그대로 간다. 담은
      서식은 sessionStorage `capa.space.formatClip.v1`(층·FAB 공용) + 페이지 안 쪽지 `window.__capaSpaceFormat` 이고 회차마다
      `S.formatClip` 으로 한 번 읽는다 — 파이썬으로 보내지 않는다.
  - **층 상세 보기 둘**(2026-10-23 사용자 요청 3·8, 보기 전용 층 뷰어만 — FAB·배치 편집기는 그대로).
    - 호기 누르기: 끌지 않고 누른 뒤·Esc 뒤 `notePick` 이 고른 호기(호기가 아니면 null)를 트리거 `pick`
      (`{epoch, id}`)으로 보낸다 — 같은 값은 다시 보내지 않고, data `pickToServer`(필요 단축 보기를 켠 동안만 참 — 사양 D11)가
      거짓이면 보내지 않는다. 파이썬 `_dispatch_pick` 이 epoch 를 대조해 `on_pick` 을 부른다. `data.picked`(파이썬이 쥔 값)가
      바뀐 회차에 `syncPick` 이 도면의 고르기를 맞추고 새로 선 도면은 다시 고른다. 보내지 않는 동안은 파이썬 값을 잊고, 다시
      보내기 시작한 회차에 이미 고른 호기를 한 번 보낸다(`queueMicrotask` 뒤로).
      문턱(3px)을 넘은 끌기(`drag.travelled` — 전체 보기에서 화면이 움직이지 않아도)는 누르기가 아니다.
    - 겹친 반입 예정 숨기기: 기준일에 반입 전인 호기가 그날 보이는(반입했고 안 빠진) 다른 호기와 넓이가 0 보다 크게
      겹치면 `is-covered`(visibility hidden)다. 판정은 `// <view-cover>` 구획(`coveredBy`·`coveredWithMates`·`unitCountText`,
      `tests/test_space_viewer_pick.py` 가 node 로 돌림)이고 이웃은 겹침 짝(`overlapPairs`, `renderItems` 가 칠하기 전에
      비움)이다. 반입 전끼리·같은 Main 설비 묶음 모듈끼리는 숨기지 않는다. 모듈은 묶음째다(`coveredWithMates`, 형제는
      `groupMates` — 겹침 짝과 같이 비움) — 반입 전 모듈 하나라도 덮이면 그 묶음의 반입 전 모듈을 모두 숨기고 반입한 모듈은
      남긴다(2026-11-12 사용자 요청 4). 숨김은 `__visible` 에 들어 Main 설비명·겹침 꼭지가 따라가고, 판정이 바뀐 호기의 겹침
      이웃과 그 둘의 묶음 형제도 다시 칠한다(`paintUnits`). 숨긴 호기의 설비지분(`share`) 합은
      `showSummary` 가 요약 끝에 「겹쳐 숨긴 반입 예정 n대」로 붙인다(파이썬 범례 대수는 그대로). 지분은 파이썬 기준일의
      것이라(같은 epoch 회차에도 `unitLook` 으로 새로 받음) 페이더를 끄는 동안에는 숨김(그날)과 지분(직전 날)이 섞인다.
      묶음째 숨김의 예외 — 이 층에 그린 같은 묶음 모듈 가운데 「필요 단축」 표시(`layer`)가 하나라도 있으면 그 묶음은
      숨기지 않는다. 표시 없는 반입 전 형제가 덮여도 보인다(`coveredWithMates` 의 `mates.some((m) => m.layer)`).
- `src/capa_simulation/components/dynamic_capacity_dashboard.py` — Dynamic Capa 공정 비교·Capa 손실 Waterfall·일별
  표준·실효·실적 추이 Figure 를 만든다. 공정 간 단위가 다르면 수량을 합치지 않고 비율만 견준다.
- `src/capa_simulation/components/sample_data.py` — 원천이 붙지 않은 화면의 샘플 표시 스위치와 끈 상태의 자리표시자
  (`render_pending_source`)다. 세션 키 `dynamic_capa_sample_data` 하나를 미연결 화면 전체가 공유한다. 구현 중 화면(실적 셋 ·
  Dynamic Capa · 재공 · Chatbot)의 스위치는 사이드바 조회 조건 패널 줄 `render_sample_row`(이름 줄 + 오른쪽 끝 스위치, 뜻 ·
  「실적 아님」 은 이름 풍선 `sample_switch_help` — 필드 key `SAMPLE_FIELD_KEY`)이고 본문 머리에 배지 줄 · 「합성 샘플 실적
  아님」 상자가 없다(2026-11-09 보드 T8 — 구현 중 표지는 화면 탭 이름 곁, 합성 샘플 표지는 머리 띠가 `sample_switch_on` 으로
  읽는다). 설비 화면(가용설비 · 필요 단축 일정 · Space)은 아직 본문 상자 `render_sample_switch` 다 — 켠 쪽만 표지를 달고 끈 쪽은
  스위치만 선다. 끈 상태의 자리표시자는 제목 + 점선 자리(`module_slot.slot_html`) + 표지 「<source> 연결 대기」 한 줄이고, `expects`
  와 `more_help` 는 제목 풍선이다(2026-11-07 답 desc-blocks). 호기 없이 끈 화면은 표지 「조회할 호기 없음」(`NO_UNITS_MARK`)이다.
  처음 값은 `sample_default` 한 함수다 — 운영 서버(`SsoConfig.operational` — 내장 시드 막이 `builtin_seed_allowed` 와 같은 뿌리, 등급은
  보지 않음)는 끔, 개발 PC · 사내 WebIDE · 사내 PC · 시험은 켜짐(2026-11-24 정식판 마감 2-A). 스위치를 그리기 전에 읽는 자리는 세션 칸을
  직접 읽지 않고 `sample_switch_on` 을 부른다(시험 `tests/test_sample_switch_default.py`).
- `src/capa_simulation/components/performance_actual_screen.py` — 효율·UPEH·수율 실적 화면 한 벌로 `MetricSpec` 만
  갈아 끼운다.
  - 요약·상세 분석·개선과제 탭은 `stateful_tabs` 이고 숨은 탭은 그리지 않는다. 상세 분석의 조회 조건(분석 기간 · 공정 ·
    제품)은 사이드바 「<지표> 실적 조건」 카드(`detail_card_label` — 처음 펼친 채, 2026-11-10 보드 Q-7)이고 그 탭이 열린
    회차에만 선다(위젯은 `persist_state` — 2026-11-09 보드 T8). 상세 분석 `공정` 상자는 겹친 표시명을 가르고 매 회차 값을 다시 적는다(8장 ②). 요약의 결론(가장 시급한
    공정)은 「개선 필요 공정」 칸 풍선(`needs_action_help`)이다.
- `src/capa_simulation/components/table_view_controls.py` — 편집표의 볼 컬럼·행 필터를 고르게 하고 거른 편집분을
  원본 전체에 되머지한다(가용설비 현황 설비 마스터 탭 세 표, 「가용설비 설정」 팝업 Cut-off 표). 고르는 칸은 표 작업 줄
  끝 「표 보기 ▾」 팝오버(`view_popover_key` — 부르는 쪽이 작업 줄 가로 칸 안에서 부른다, 접힘 줄 없음 — 2026-11-09
  사용자 보드 T5)이고, 필터가 걸린 동안은 단추 글 끝 표지 「필터」 + 풍선(`FILTERED_NOTICE`)이 행 추가 · 삭제 잠김을
  말한다(표 위 · 아래 설명 줄 없음). 표지는 편집표에 **건** 보기를 따른다 — 폼 밖 작은 편집표는 고르는 즉시 회차가 돌아
  고름과 적용이 갈리므로 건 보기의 `filtered` 를 `applied_filtered` 로 넘기고(`equipment_data_workspace._editor_view`),
  넘기지 않으면(첫 회차 · 제출이 곧 적용인 Cut-off 폼) 그리기 전 세션 값으로 `view_of` 와 같은 판정이다(`_filtered_in_state`,
  설계 규칙 UI-DAT-11).
  - 행 필터 중에는 `num_rows="fixed"` 다 — 이 표들은 편집 결과가 곧 다음 리비전 전부다. 거른 편집인지는 호출자가
    `merge_edited_rows` 의 `filtered` 로 알려 준다(`tests/test_table_view_controls.py`). 모든 행이 남는 거름(「Select
    all」·한 호기뿐인 표의 「표에서 고치기」)은 원본(RangeIndex)을 그대로 돌려준다 — `.loc` 의 일반 정수 Index 를
    행 추가가 열린 편집표에 넘기면 Streamlit 1.63 이 `hide_index=True` 를 무시하고 머리 없는 인덱스 칸을 세운다.
  - 보이는 행이 바뀌면 `discard_editor` 로 새 위젯을 세운다. 보기 설정 위젯은 `st.form` 밖이고 `value_labels` 는
    보이는 글자만 바꾼다.
- `src/capa_simulation/components/securement_heatmap.py` — `산출 결과` 의 공정 × 월 확보율 상태 3색 격자다(범례 없이
  hover·칸 안 숫자가 값을 말한다). 칸 안 숫자는 정수 % 이고 정수로 0 이 되는 0 아닌 값은 유효 숫자 둘로 적는다(`cell_text`).
  - 경계는 공용 판정 기준 프로필(`load_global_securement_threshold`)이고 두 축 모두 범주, 모든 행에 공정 이름이다. 축 값은
    원본 공정이고 눈금 · hover 글자만 표시명이다(`category_axis`, hover 는 customdata 쌍) — 같은 표시명의 두 공정을 한 줄로 합치지 않는다.
  - HOME `주요공정 확보율`(`home_figures.build_key_process_heatmap_figures`)과는 다른 그림이고 판정 경계의 뜻만 같다.
    HOME 쪽은 별도 영역이 아니라 같은 분할 격자의 구획이라 `go.Heatmap` 을 쓰지 않는다(쓰면 칸 폭이 100px 월 격자와 어긋난다). 이 히트맵은 HOME 주요공정 목록을 공유하지 않고 확보율 표와 같은 행(표 조건 카드의 필터를 거친 표)을 그린다.
- `src/capa_simulation/components/capacity_gate.py` — 리비전 저장·복제·파생 저장·공식 발행 **전에** 시나리오 전체
  기간 Capa 계산(대당 Capa·소요대수 + HOME Density 환산 `density_error`)이 되는지 검사한다.
  - 저장은 편집이 새로 깨뜨렸으면 막고 원래 안 되면 경고하며 허락한다(파생 저장은 원본이 「편집 전」). 발행은 막는다.
    소요대수에 들지 않은 수요는 막지 않고 건수를 경고한다(그 판정은 `GateVerdict.exclusion` 이 참 — 계산은 통과). 사이드바
    리비전 저장 · 시나리오 관리 복제 · 공식 지정 · 월 머지 · 연도 Shift 저장 뒤 경고는 소요대수 제외 · 남은 계산 오류 모두
    버튼 곁(시나리오 칸 · 저장 단추 밑)에 그리지 않고 `queue_flash(…, popup_only=True)` 로 알림창 · Alarm 에만 낸다
    (2026-11-04 검수 의견 home-18 · 설계 규칙 확인 보드 AMB-05 (나)). 화면은 `exclusion` 으로 갈래를 가르지 않는다 —
    판정 시험(`tests/test_capacity_gate.py`)만 두 경고를 가른다. 파생 저장 경고는 결과(공식버전으로 지정할 수 없음)를
    앞에 둔다 — 알림창 짧은 글이 앞 60자 안팎이다(UI-NTF-06).
  - 계산 페이지와 같은 캐시 칸(`pristine_content_token`)을 쓰고 BigDataQuery 등록·내장 시드는 검사하지 않는다. 새
    쓰기 경로는 `tests/test_capacity_gate.py` 목록에 더한다(`density_error` 는 `tests/test_gate_density_coverage.py`).
  - 판정 함수 넷(`revision_save_verdict` · `official_publish_verdict` · `input_check_verdict` · `derived_save_verdict`)은 부하 예외
    선언을 스스로 읽지 않고 부르는 화면이 그 회차에 읽은 판(`route_exceptions` — 기본값 없음)을 받는다 — 키와 계산이 그 한 판으로
    접혀 계산 페이지와 같은 칸이다(5장 44 · 45). 부르는 화면은 그 DB 경로로 읽은 판(`page_bootstrap.route_exceptions_of`)을
    넘긴다.
  - 자동 갱신 발행은 순수 코어 `simulation_cache.full_capacity_outcome` 로 같은 검사를 하고 경고를 실행 기록에 붙인다.
  - 입력 점검(`input_check_verdict(database_path, scenario_id, revision_id)` — 시나리오 관리 › 목록 관리 「점검」)도 같은 멈춤 판정
    (`_stop_error` — Capa 오류가 먼저, 통과하면 Density)을 쓰고 `tests/test_gate_density_coverage.py` 그물 안이다. 고른 리비전마다
    부르므로 위 「같은 캐시 칸」 이 아니라 입력 점검 요약 칸(`simulation_cache.get_revision_input_check`, 5장 39)에 두고, 계산은 공유 칸을
    밀지 않는 길(저장소에서 캐시 없이 읽은 표시순서 없는 스냅샷 · 원천 행, 캐시 없는 `full_capacity_outcome`)이다. 경로 키가 없는 옛 리비전은 계산을 부르지 않고
    그 까닭으로 멈춘다(`revision_block_reason`). 저장된 리비전 그대로를 세고 미저장 편집은 보지 않는다. 받은 부하 예외 선언 판으로
    「부하 예외로 바꾼 경로」 · 「이번 데이터에 없는 선언 공정」 재료(`revision_input_check.route_exception_check` — 그 리비전 `RQ_REQB`
    공정 · 같은 계산 결과)도 짓는다.
  - 모듈수(`RQ_MODULE`) 멈춤 안내(`module_fix_hint`)는 오류 예시의 공정 칸(`stop_examples.example_processes` — 글자 일부가
    아니라 칸 값 그대로)에 그 시나리오 데이터셋의 부대공정이 있으면 「판을 고쳐 다시 놓고 적용한 뒤 부대공정 얹기」 를 권한다(설계
    A11 — 월 머지는 베이스의 옛 판 모듈수가 이겨 풀지 못한다). 판을 적용하는 Admin 「부대공정」 은 개발자만 열어 그 밖의 화면
    등급(`sso_identity.viewer_can("admin.area")`)에는 「개발자가 판을 고쳐 적용한 뒤 부대공정 얹기」 로 할 수 있는 일만 적는다(규칙
    6-34 SC-01). 출처는 모듈수 오류일 때만 읽는다(`_scenario_extras` · `_active_extras` — 다섯 부르는 곳이 시나리오를 넘긴다).
- `src/capa_simulation/components/outside_calculation_mark.py` — 소요기준 BOX · PCB 경로가 계산에서 빠진 공정(계산 밖 — 11장)을
  알리는 표 제목 줄 표지 「계산 밖 n공정」 과 그 풍선 글(까닭 + 「이 기간: 표시명 (BOX) · …」, 경로 일부만 빠진 공정은 「— 일부
  경로」, 열 개 넘으면 「외 n공정」)을 짓는 순수 함수 `outside_calculation_mark` 다. 공정 차례는 부르는 쪽이 준 원본 공정 표시순서이고
  표시명은 차례를 정한 뒤 붙이며 마크다운 글자를 막는다(`literal_markdown`). 없으면 None — 표지 낱말은 「계산 밖」 하나다
  (`OUTSIDE_CALCULATION`, 설계 규칙 UI-CON-02). 부르는 곳은 산출 결과 세 표 제목 줄과 HOME 「상세 B/N 공정」 제목 줄이다
  (`tests/test_outside_calculation_mark.py`).
  - 표지는 앞에 아이콘을 달지 않고 끝 ⓘ 하나다(이웃 제목 줄 부가 설명 꼴 — Static 대비 일정 「한쪽 공정 · GAP 없음」 표지와 같은 꼴, 설계 규칙 UI-TXT-04). 계산 밖을 말하는 Guide 는 세 파일 네 자리다 — 산출 결과 「계산 밖 공정」 단락 · HOME 「공정 필터」 · 「대시보드」 · 공정 Capa 상세 ③ 판정 카드 뜻.
  - 공정 하나를 말하는 자리의 글도 여기다 — `whole_outside_basis`(목록과 원본 공정명 → 경로가 모두 계산 밖이면 빠진 소요기준 글,
    둘이면 「BOX · PCB」, 아니면 None)와 `BASIS_MARK`(「계산 밖(소요기준 BOX)」). 부르는 곳은 공정 Capa 상세 ③ 판정 카드다
    (`process_capa_view._unjudged_text`).
  - 공정마다 단추가 서는 자리는 `whole_outside_bases`(선택지 원본 공정 → 그 글, 글이 선 공정만)와 풍선 줄 `BASIS_REASON`(「소요기준 BOX —
    산식이 정해질 때까지 계산 밖입니다(추가 예정).」)을 쓴다. 부르는 곳은 HOME 공정 필터 팝업이다(`process_picker`).
- `src/capa_simulation/components/capacity_assumption_notice.py` — 측정률 행이 없어 중립값 1.0 으로 이어 간 건수와
  달(조회기간 밖 포함)을 HOME·`산출 결과` 대당 Capa 탭에 상태 알림 `HM-02` 로 낸다(자리에 그리지 않는다, `goto` 는 기준 정보 — 9장 「알림 칸」).
  두 화면이 같은 코드 · 같은 범위(활성 리비전 내용 — 시나리오 전체 기준이라 조회기간은 넣지 않는다)라 한쪽에서 본 가정은
  다른 쪽에서 다시 뜨지 않는다. 짧은 글(`assumption_short`)은 표 · 건수와 고칠 곳(기준 정보)을 말한다. 시나리오 관리 › 목록
  관리 「점검」 은 같은 셈(`capacity_assumptions`)으로 저장 리비전 전체 기간의 표 · 경로 수 · 달을 센다(6장 대당 Capa). 가정이 없어도
  부른다(해소).
- `src/capa_simulation/components/required_exclusion_notice.py` — 소요대수에 들지 않은 수요의 건수 문장
  (`required_exclusion_message`), 소요대수 쪽 제외 목록(`ExclusionList` — 알림에 딸린 표와, 표가 커서 None 일 때의 본문 펼침
  `render_oversized_lists`. 계획 쪽 둘은 `plan_exclusion_lists` — 고칠 곳은 까닭 칸 머리 풍선 `LOAD_EXCLUSION_HELP` ·
  `UNROUTED_HELP`), 그리고 화면 자리의 상태 알림 함수(`alert_uncounted_demand` · `alert_capacity_exclusions` ·
  `alert_required_exclusions`)를 낸다. 계획 쪽 두 목록의 분류 칸(`_LOAD_EXCLUSION_DIMENSIONS` · `_UNROUTED_DIMENSIONS`)은
  Stack 뒤에 `CUSTOM` 을 싣고, 경로 쪽 세 목록(`ST-15` · `ST-21` · `ST-22`)은 산출 결과 소요대수 표와 같은
  `required_equipment.RESULT_DIMENSIONS` 로 분류 칸을 세운다(차원 상수의 CUSTOM 은 Stack 뒤 — 화면 칸 자리는 표시순서 규칙
  차례다, 8장).
  - 문장은 `capacity_gate`·자동 갱신이 모두 시나리오 전체 기간(`FULL_SCOPE`)으로 쓴다 — HOME 에는 띄우지
    않는다. 목록 관리 「점검」 은 이 문장을 쓰지 않고 같은 셈의 묶음 수 · 행을 보인다 — 그래서 저장 · 지정 · 복제 · 자동 갱신
    경고의 끝 문장(`REQUIRED_LIST_NOTE`)과 「그 화면으로」(`REQUIRED_TAB_GOTO`)가 그 칸을 가리키고 경고를 낸
    자리가 그 리비전을 경고 줄에 싣는다(`required_check_target` → `queue_flash(target=)` — 2026-11-11 검토 보드 F4 (나) · 다음 배포 물음
    보드 F4 뒤 (a): 줄이 들고 다녀 누를 때마다 그 줄의 리비전, 손으로 연 「점검」 은 고름을 옮기지 않는다 — 9장 「알림 칸」 의 대상). 경로 쪽 `소요대수 제외 기준정보` 와 따로 둔다. 계획을 고친 사람이 「고쳤는데 수가 안 바뀐다」 고 헷갈리지
    않게 화면 세 자리도 같은 셈의 **상태 알림**이다(2026-11-03 결정 보드 D2 (나) — 자리에 그리지 않는다): 생산 계획 PKG PLAN
    적용 알림이 서는 회차(쓰기 알림 표지 창의 다시 그리기 포함)의 `ST-04`(`FULL_SCOPE`, `get_full_capacity_outcome` —
    HOME·산출 결과가 같은 결과를 쓴다. 셈은 PKG PLAN 편집표를 그린 **뒤**에 하고 스피너는 그 알림 칸에 선다 — 앞에서 하면 그
    계산이 끝날 때까지 편집표가 서지 않는다), Static Capa 현황 요약과 산출 결과 소요대수 탭의 `ST-01`(`PERIOD_SCOPE` — 산출
    결과 요약 캐시 `get_scenario_result_summary` 의 조회기간 목록을 `count_required_exclusions` 로 센다 — 같은 코드 · 같은
    범위라 한쪽에서 본 것은 다른 쪽에서 다시 뜨지 않는다). 짧은 글은 건수와 목록 자리(「Alarm › 이 줄」 — 세 자리 모두 계획 쪽
    목록 둘을 그 줄의 표로 싣는다, 커서 못 실으면 「산출 결과 › 소요대수」)를 말한다.
    셋 다 **계획 쪽 건수만** 싣는다(`plan_side_counts`) — 경로 쪽(대당 Capa · 부하 예외 바탕이 없어 뺀 부하 경로)은 계획을 고치지
    않아도 늘 있을 수 있어(사내 실데이터에서 0 이 아니었다) 늘 서는 경고가 된다(HOME 에서 이 줄을 뺀 2026-10-19 결정과 같은 까닭).
  - 경로 쪽은 산출 결과가 따로 낸다 — 대당 Capa 제외 `ST-14`(지문 내용 = 건수 + 제외사유별 건수, 딸린 표 = 「제외 기준정보」),
    대당 Capa 가 없어 소요대수에서 뺀 경로 `ST-15`(확인 필요 — 기준정보를 고칠 일, 딸린 표 = 「소요대수 제외 기준정보」), PKG 의
    Buffer 밖 행 `ST-21`(알림 — 규칙이라 고칠 것이 없다, 딸린 표 = 「PKG Buffer 밖 행」), 부하 예외 바탕이 없어 소요대수에서 뺀
    경로 `ST-22`(확인 필요 — 수율 · Chip 구성을 고치거나 겹친 원천을 다시 등록할 일, 딸린 표 = 「부하 예외 바탕 없는 경로」 —
    6장 「공정별 부하 산출 예외」). 세 사유를 한 알림에 섞지 않는다.
  - 알림에 딸린 표는 부르는 쪽이 키를 주면 기억한다(`remembered_alert_table` — `alert_required_exclusions` · `plan_exclusion_lists` 의
    `memo` 인자). 키는 (부르는 쪽 키, 목록 이름, 파일 이름 — 고침 꼬리 포함, 공정 표시명 판)이고 세션 칸(`SessionSlot`
    `required_exclusion_table_memo`, `EXCLUSION_MEMO_LIMIT` 여덟 벌)에 두며 꺼낸 표는 겉 dict 를 새로 낸다. 키를 주는 곳은 산출
    결과(결과 키 · 지문 — 소요대수 `ST-15` · `ST-21` · `ST-22` · 대당 Capa `ST-14`)뿐이고 생산 계획 `ST-04` · Static Capa `ST-01` 은 주지 않아 늘
    짓는다. 알림을 내는 일(`alerts.state`)은 기억하지 않는다 — 회차마다 제 이벤트 칸을 쓴다.
- `src/capa_simulation/components/object_sync_status.py` — Admin 「DB 동기화」 펼침(올릴 것 · 마지막 올림 · 세대 · 갈래 — 기준 세대가 시작 펜스면 세대 번호 뒤 `(시작 펜스)`, 일꾼 상태의 `origin` 으로 — 펼침이 서 있는 동안 늘 `run_every` 프래그먼트(`LIVE_FRAGMENT_KEY` · 5초)로 갱신하고, 판정 제목 · 「지금 올리기」 잠금이 그린 때와 달라지면 앱 회차로 돌아가 함께 고친다 — 그린 순간 값에 머물면 연 채 둔 화면이 다른 회차의 저장 뒤에도 초록 「CI/CD 눌러도 됨」 을 보였다(E2E C-11), 그 페이지의 여닫기는 앱 전체로 돈다(`note_periodic_fragment` — 9장 「여닫을 때…」))과 개발자용 「지금 올리기」, 동기화 상태 알림 `SY-01` ~ `SY-06`(`app.py` 가 `GL-02` 곁 한 자리에서 부른다 — 짧은 글은 누구나 꼴(`SY-02` · `SY-03` 일반 사용자는 「— 개발자에게 알려 주세요」), 개발자 지시 · 런북 · 갈래는 개발자 몫 전문에만, 개발자 줄의 「그 화면으로」 는 Admin 이 펼침까지(줄이 대상을 들고 가 다른 화면에서 눌려도 연다 — `open_sync_panel` · 알림 칸 받는 쪽 `object_sync`, 설계 규칙 UI-NAV-01), `SY-06` 은 개발자 몫에만, 일꾼이 없으면 개발자 전문 끝 `WORKER_ABSENT_LINE`)과 머리 띠 「정본 아님」 표지의 코드(`not_canonical_code` — 9장 「알림 칸」). 펼침 제목 끝은 CI/CD 판정 배지 하나(`CICD_VERDICTS` — 일꾼 판정 제목마다 초록 「CI/CD 눌러도 됨」 · 주황 「기다리세요」 · 빨강 「누르면 저장 잃음」, 복사 글은 평문 낱말 — 2026-11-14 보드 카드 p2-sync). `managed` 가 아니면 Streamlit 호출이 없다.
- `src/capa_simulation/components/admin_view.py` — 개발자 몫 알림 · 전문 · 접힌 「개발자용 진단」 을 이 회차에 보일지 한 곳(`developer_notes_visible` — 개발자(`sso_identity.viewer_is_developer`)면 참, 아니면 통합인증이 켜짐이 아니고 운영 서버(`SsoConfig.operational` — Admin Area 잠금 `admin_area_locked` 와 한 뿌리)가 아닐 때만 누구에게나). 그래서 운영 서버에서 통합인증이 꺼진 동안은 아무에게도 서지 않고(Admin Area 가 모두에게 잠긴 것과 같다 — 참인 회차에는 Admin Area 가 늘 열려 「그 화면으로」 가 잠긴 화면을 가리키지 않는다), 개발 `app.py` · 사내 WebIDE · 사내 PC 는 누구에게나다. 이것을 부르는 자리 — 시작 점검 `AD-01` · 접속 명단 `AD-08` · `AD-09` · `AD-19` · 로그인 갱신 거절 `AD-21` · 코어 화면 오류 `AD-22` · 동기화 `SY-*` 개발자 전문 · DB 실패 전문(`data_error_mark`) · DB 등록 BigDataQuery 실패 곁 글 · `AD-04` 전문 · CUSTOM 원천 표 잠금 풍선(`bigdataquery_registration`) · 코어 화면 오류 카드 · 앱 시작 실패 판 · 문지기 없이 뜬 앱 판(`sso_identity`)의 「개발자용 진단」. 아래 등급에게도 한 줄을 남기는 자리(설비 저장 실패 · 자동 갱신 진단 「마지막 확인」 · 실행 기록 「사유」 칸 · DB 등록 조회 · 저장 실패 곁 글)는 `diagnostic_message` 로 짓는다 — 개발자 몫이면 원문, 아니면 DB 실패 글은 `page_bootstrap.screen_error_public`, BigDataQuery 실패 글은 `company_bigdataquery_adapter.public_failure_text` 로 줄인 꼴이다. DB 등록 `AD-04` 전문은 개발자가 아니면 CUSTOM 원천 표 줄 · 서버 시작 점검 단락을 빼고 지문(`content`)은 그대로다(「이 등급으로 보기」 를 켜고 꺼도 다시 뜨지 않게). BigDataQuery 토큰 알림(`AD-10` · `AD-11` · `AD-23`)은 밖이다 — 통합인증이 꺼진 C-DEP 에서는 아무에게도 띄우지 않는다(규칙집 결정 ad10-nosso, `viewer_is_developer` 그대로). 보이기만 가르고 쓰기 · 개발자 단추의 두 번째 벽은 그 자리 판정(`viewer_is_developer`) 그대로다(2026-11-14 보드 리뷰 반영 「개발자 회차에만 은 꺼진 서버에서 아무도 못 본다」). 그 가운데 서버 상태 알림(`AD-01` · `AD-08` · `AD-09` · `AD-19` · `AD-21` · `AD-22` · `AD-25` · `AD-26` · `SY-*` 전문)을 세울지는 `developer_alerts_visible` 이다 — 같은 판정이되 「이 등급으로 보기」 를 따르지 않는다(켜고 끄는 사이 서 있던 알림이 해소 · 다시 뜸으로 흔들리지 않게 — 감사 `AD-12` · `AD-13` 도 실제 개발자 `viewer_is_developer`, 시험 `tests/test_grade_ui_core.py`). 시험은 `tests/test_admin_view.py`(설정 × 개발자 진리표 · Admin Area 잠금과 맞댐). 개발자에게만 서는 상태 알림(이 판정의 `AD-01` · `AD-08` · `AD-09` · `AD-19` · `AD-21` · `AD-22` · `AD-26` · `SY-06`, 토큰 셋, 감사 `AD-12` · `AD-13`)은 그 밖의 회차를 해소(`active=False`)로 부르고 짧은 글 · 전문을 싣지 않는다 — 숨은 표지(`[data-capa-alerts]`)에는 등록부 이름만 실린다(시험 `tests/test_admin_alert_resolved_markers.py` 가 앱 정보 카드 · 동기화 알림의 일곱 — `AD-08` · `AD-09` · `AD-19` · `AD-12` · `AD-13` · `AD-21` · `SY-06` — 을 본다). 누구에게나 서는 운영인데 꺼짐 `AD-02` 도 해소 표지에는 글을 싣지 않는다 — Admin Area 가 잠금 앞에서 부르므로 켜진 서버에서 주소로 Admin Area 를 연 일반 회차에도 그 표지가 실린다(시험 `tests/test_sso_status.py`).
- `src/capa_simulation/components/container_start_check.py` — Admin Area 탭 위 「서버 시작 점검」 펼침. C-DEP CD 시작
  스크립트의 결과 파일(`io/container_start_report.py`)이 있을 때만 단계 표(설치·로그인 토큰 파일·요청자 계정 + 넷째 줄 「통합인증」
  — 결과 파일이 아니라 지금 설정에서 `sso_status.sso_start_step` 으로 판정, client id 발급 전의 「건너뜀」 은 정상 + `managed` 서버의 「BDQ 자동
  로그인」 줄 `login_rows`(시작 때 결과 — `container_start_report.login_step`) + S3 키 · `managed` 가 있는 서버의
  동기화 줄 다섯 `sync_rows` — AWS 프로필 · aws CLI · ECS 연결 · 버킷 목록 · DB 받기 + 「CUSTOM 원천 표」 — 이 프로세스의 지금 환경변수
  `CAPA_BDQ_CUSTOM_TABLE` 을 상세 조회와 같은 판정 `company_bigdataquery_adapter.custom_source_problem` 으로 본 줄 `custom_table_step`, 없거나
  꼴이 틀리면 「실패」(까닭은 변수 이름과 막히는 것뿐 — 값 없음), CUSTOM 원천 끄개(`CAPA_BDQ_CUSTOM_SOURCE=off`)를 내렸으면 변수와 상관없이
  「건너뜀」(`CUSTOM_SOURCE_SKIPPED_REASON` — 실패가 아니라 `AD-01` 에 들지 않는다), 시작 스크립트 결과 파일에는 칸을 두지 않는다 + 끝 줄 「DuckDB 메모리 한도」
  — 지금 연결 설정의 한도 칸 판정 `memory_diagnostic.memory_limit_step`. 지금 판정한 두 줄(`live_steps`)이 「실패」 면 제목 판정
  `start_verdict` 와 `AD-01` 에 든다)와 「시작 때 있던
  통합인증 환경변수」 캡션(이름만)·디스크 · pod · 한도 · DuckDB 기본값 · 다운 시간 값(`sync_fact_lines`)·깔린 판·
  토큰 파일 수정 시각·자리·실행 사용자·HOME·시작 자동 로그인이 하위 프로세스를 띄웠으면 그 진단 값 줄(「BDQ 자동 로그인 진단」 —
  `LoginStart.child`)·비어 있던 환경변수·사실 줄 끝 메모리 값 줄(`memory_diagnostic.memory_lines` — 이 프로세스의
  지금)과 그 뒤 부하 값 줄 셋(`load_diagnostic.load_lines`)·pip 출력 끝을 싣는다. 결과 파일이 없는데 CD 전용
  환경변수(`CD_ONLY_ENVIRONMENT`)가 앱에 있으면 「결과 없음」 펼침으로 스크립트가 돌지 않았거나 결과를 쓰지 못했음을
  알린다(`missing_report_notice`). 파일은 있는데 읽지 못하면(빈 파일·JSON 아님·모르는 꼴 — `report_file_exists`)
  환경변수와 상관없이 「결과 파일을 읽지 못함」 펼침이다(`UNREADABLE_REPORT_NOTICE` — BigDataQuery 안내도 같은 글). 회차마다 그 작은 JSON 만 읽고 DB 를 열지 않는다.
  시작 점검 개발자 알림 `AD-01`(`render_start_check_alert` — `app.py` 가 토큰 알림 앞에서 모든 화면 회차에 부른다, 2026-11-14 「앱 대신 뜨는
  화면」 보드 카드 p2-sync 「AD-01 범위를 넓힘」)은 결과 없음 · 못 읽음 · 실패한 단계(`failed_start_steps` — 토큰 줄은 `AD-10` 몫이라 뺀다 —
  와 지금 설정에서 실패한 단계 `live_failed_steps` — 표 차례로 CUSTOM 원천 표 환경변수가 없거나 꼴이 틀림 · DuckDB 메모리 한도 칸이 틀림)를
  개발자 몫(`admin_view.developer_notes_visible`)에 조치 알림으로 낸다 — 지문은 (제목, 실패 단계 이름들), 「그 화면으로」 는 Admin Area 의 이 펼침까지(줄이 대상을 들고 가 다른 화면에서 눌려도 연다 — `open_start_check` · 알림 칸 받는 쪽 `start_check`, 설계 규칙 UI-NAV-01). 결과 파일도
  CD 전용 환경변수도 없는 프로세스(`start_check_alert_possible` — 프로세스 동안 그대로)는 Streamlit 호출이 없다. Admin 펼침은 이 알림을 따로
  내지 않는다.
  BigDataQuery 토큰 실패 개발자 알림 `AD-10`(`render_token_alert` — `app.py` 가 동기화 알림 곁에서 모든 화면 회차에 부른다, 2026-11-12 리뷰
  202611111500 보드 N8 (가))도 여기다 — 결과 파일이 있는 서버(C-DEP)에서만 부르고(없으면 Streamlit 호출 0), 시작 점검 토큰 줄 「실패」 나
  어댑터의 프로세스 표지(`company_bigdataquery_adapter.last_query_failed_on_token` — 조회가 토큰 갈래로 실패하면 서고 조회가 성공하면
  내린다, 예약 스레드도 같은 값을 쓴다)가 있으면 개발자(`sso_identity.viewer_is_developer` — 통합인증이 켜짐이 아니면 아무도 아니다) 회차에
  조치 알림으로 선다. 지문은 그 두 참거짓뿐이고 「그 화면으로」 는 Admin Area 다. 만료 전에 미리 갱신하지 않는다 — 대신 C-DEP 자동 로그인(2026-11-16 사용자 결정
  D1 ~ D11, 아래 `io/bdq_login.py`)이 회복한다: 계정은 Admin Area 개발자 폼에서만 넣고(환경변수 표에 비밀번호 없음) 버킷
  `secrets/bdq_login.json` 에 키 `CAPA_BDQ_SECRET_KEY` 로 감싸 두며, 저장된 계정이 조회 · 토큰 파일 이름 · 남은 시간 모두의
  계정 하나의 원천이다. 시작마다 한 번 로그인하고, 조회가 토큰 파일 없음(패키지 종류 `TokenNotFoundException`)이나 만료 · 무효 토큰(안쪽
  문구 「You have invalid token」 — 실측의 응답 코드는 400 이고 판정은 코드를 보지 않는다, 둘이 같은 사슬이고 패키지 종류가 아니다,
  2026-11-16 사내 실측 · 사용자 결정)으로 실패하면
  다시 로그인해 같은 조회를 한 번만 다시 한다(WebIDE 가 같은 계정으로 로그인해 운영 토큰이 죽어도 D11 대로 이 길로 돌아온다 — 운영
  로그인이 WebIDE 토큰을 초기화하는 것은 감수).
  로그인 거절 · 다시 한 조회도 토큰 오류 · 그 밖의 애매한 실패는 다시 시도하지 않고 멈춤을 객체에 적어 재시작에도 시도하지 않으며(개발자
  `AD-23` — 폼에서 다시 넣어 성공해야 풀린다), 요청을 보내기 전 연결 단계의 양의 증거만 「닿지 못함」 으로(패키지를 불러오지 못하면 시도
  자체가 없어) 멈추지 않는다(개발자 `AD-24` — 성공 없이 3번이면 멈춤). 계정 잠김 방지가 불변식이다 — 폼 한 번에 시도 한 번 · 자동 시도
  앞의 시도 표시(쓰지 못하면 로그인 없음) · 자동 연속 3번 상한 · 재시작을 건너는 닿지 못함 · 확인 못 함 3번 상한 · 닿지 못함 뒤 5분 쉼 ·
  프로세스 잠금 하나 · 새 배경 스레드 없음. 키도 객체도 없는 서버는 시작 · 조회가 지금과 같다(「토큰 넣기」 · `CAPA_BDQ_TOKEN` 예비 길). 할 일 글은 시작 점검 실패면 그 까닭 고치기 + CI/CD, 조회 실패면 「토큰 넣기」 +
  CD 환경변수 값 바꿔 두기다 — 패키지가 환경변수 `BIGDATAQUERY_LOGIN_TOKEN` 을 읽는 서버(넣기가 잠긴다)면 그 값 바꾸기 + CI/CD
  (`bdq_token.environment_token_set` — 값은 보지 않는다, 글은 `AD-11` 과 같은 `bdq_token_admin.ENVIRONMENT_FIX`), 자동 로그인이 켜졌는데
  (`managed` + 키) 저장된 계정이 없으면 Admin Area 「BDQ 자동 로그인」 에 계정 넣기다(`bdq_token_admin.AUTO_LOGIN_FIX`), 저장된 계정이
  있으면(정상 · 멈춤) 그 자리에서 다시 넣기(곧바로 새 토큰 — `RELOGIN_FIX`)를 먼저, 「토큰 넣기」 를 그다음으로 적는다. 같은 함수 끝에서 만료 알림
  `AD-11`(`bdq_token_admin.expiry_alert_note` — 자동 로그인이 서 있는 동안은 해소)과 자동 로그인 멈춤 알림 `AD-23`(`login_stop_note` —
  개발자 회차, 지문은 (멈춘 까닭, 멈춘 시각), 「그 화면으로」 Admin Area 「BDQ 자동 로그인」 펼침까지 — 대상 `bdq_login`, 다시 넣어 성공하면 풀린다 — 2026-11-16 결정 D3 · D4.
  하위 프로세스가 표지 없이 끝난 멈춤(`bdq_login.UNCONFIRMED_REJECT_REASONS` — `no_marker`)은 짧은 글이 「… 멈춤 — 로그인 확인 못 함」 이고
  전문이 비밀번호가 틀렸는지 모른다는 것과 진단 줄을 먼저 말한다 — 2026-11-17 사내 리뷰 `202611162130` 발견 4 · 사외요청 1),
  보내기 전 끊김이 다시 시도 상한을 넘긴 멈춤(`cut_limit`)은 짧은 글이 「… 멈춤 — 다시 시도 3/3 끊김」 이고 전문이 계정 잠김이 아니라
  다시 시도를 다 썼다는 것과 진단 줄을 말한다(2026-11-20),
  자동 로그인이 멈추지 않은 채 서지 못함 알림 `AD-24`(`login_trouble_note` — 시작 · 조회 중 닿지 못함 · 확인 못 함 · 못 함, 지문은 갈래
  낱말 하나 — 보내기 전 끊김 `import_killed` 은 짧은 글 · 지문에 「다시 시도 n/3」(`bdq_login.retry_text`)이 붙고 전문이 다음 시도 시각을
  말한다, 같은 대상 — D6 「알림만」)도 부른다 — `AD-10` 도 할 일이 계정 넣기 · 다시 넣기인 갈래(`_token_alert_target` — 꺼짐 아니고 시작
  점검 실패 · 토큰 환경변수 아님)에서는 같은 대상을 들고 간다. 결과 파일이 있는 서버는 회차마다 이벤트 칸 네 자리다(넷의 표지는 `token_alert_notes` 한
  벌이 짓는다). 자동 로그인 상태는 S3 에 묻지 않고 읽는다(`login_view` → `bdq_login.current_view` — 무엇이 나도 `off` 로 물러선다). 조회 실패 ·
  조회 중 자동 로그인의 멈춤은 화면 본문의 조회(DB 등록 단추 · 모듈 조회)에서 생기는데 넷은 화면 앞에서 낸다 — 그 회차의 앞 표지는 해소라
  실패 글을 본 그 자리에서 Alarm 을 열어도 없었다(사내 리뷰 `202611181400` 발견 3). 그래서 `render_token_alert` 가 낸 표지(코드 · 조건 · 지문)를
  돌려주고 `app.py` 가 화면이 끝까지 돈 회차의 끝에서 `render_token_alert_late` 에 넘긴다 — 같은 짓기로 다시 지어 달라진 것만 이벤트 칸 한
  자리에 싣는다(없으면 빈 칸, 결과 파일이 있는 서버는 늘 한 자리 — 회차의 마지막 칸이라 앞 칸 순번을 밀지 않는다, 담아 둔 사건 알림은 꺼내지
  않는다 `alerts.emit(drain=False)`). 덮지 못하는 회차는 둘이다 — 화면이 `st.stop()` 으로 멈춘 회차(더 쓸 수 없다)와 프래그먼트 · 팝업
  본문만 다시 도는 회차(`app.py` 가 돌지 않아 앞 · 끝 표지가 모두 없다 — 모듈이 `@st.fragment` · `@st.dialog` 안에서 `query_bigdataquery` 를
  부르는 꼴)이고 둘 다 다음 전체 회차의 앞 표지가 낸다(프래그먼트 · 팝업을 처음 그리는 전체 회차 안의 조회는 끝 표지가 덮는다). 알림 칸 JS 는 한 번 훑을 때
  같은 상태 칸의 마지막 표지만 받는다(`latestStateNotes` — 앞 표지가 줄을 닫고 끝 표지가 새 줄을 여는 되풀이를 막는다). 시험
  `tests/test_bdq_login_alerts.py` · `tests/test_bdq_login_stop_alert_flow.py`(실제 개발자 쿠키 · 조회 중 멈춤 · 재시작 뒤 멈춤 · 같은 회차).
- `src/capa_simulation/components/memory_diagnostic.py` — Admin 「서버 시작 점검」 의 메모리 값 줄과 표 끝 「DuckDB 메모리 한도」 줄(사내
  리뷰 202611162130 사외요청 3 — 사내가 메모리 줄이기 앞뒤를 잰다). 값 줄은 「**메모리 지금** · RSS · 최고 · 세션 연결 n · 전체 n ·
  cache_data」(RSS 는 `/proc/self/status` 의 `VmRSS` · `VmHWM`, 없으면 최고만 `resource` · Windows 는 「모름」, 세션은 Streamlit 내부 `Runtime`
  세션 관리자, `cache_data` 는 `get_data_cache_stats_provider` 의 저장된 pickle 길이 합 — 내부 API 는 감싸 무엇이 나도 「모름」)와 DB 마다
  「**DuckDB <시뮬레이션 · 설비> 회차 끝** · 마지막 · 최고 · 임시 파일 최고 · 한도」(`persistence/duckdb_memory.memory_sample` — 아직 못 쟀으면
  「모름」)다. 세션 표 · `cache_resource` · 세션 상태의 크기를 깊이 재지 않는다(잠긴 표에 `memory_usage(deep=True)` 를 부르지 않는다 —
  `tests/test_memory_diagnostic.py` 가 막고 돈다). 화면에는 값 줄만 두고 뜻은 Guide 「서버 시작 점검」 이다. 한도 줄은 지금 연결 설정
  (`_sql_helpers.DUCKDB_MEMORY_LIMIT`)의 판정 — 없음 「건너뜀」 · 받은 값 「정상」(DB 마다 그 값) · 틀린 값 「실패」(꼴 · 범위, 기본 그대로).
  틀린 값의 까닭은 값 없는 고정 낱말(`꼴이 틀림` · `64MiB ~ 1TiB 밖`)이고 그 값의 글은 싣지 않는다 — 옆 칸(비밀 키 · 토큰)을 잘못 붙여 넣은
  값일 수 있고 이 줄은 복사 글 · `AD-01` 전문으로 리뷰에 옮긴다(`io/object_storage.py` 의 「모드 값 틀림」 과 같은 관례).
- `src/capa_simulation/components/load_diagnostic.py` — Admin 「서버 시작 점검」 의 부하 값 줄 셋과 신호표 문턱 넘음 판정 글(`docs/TODO.md`
  2장 「Streamlit 에 남는 조건 셋」 ②). 값 줄은 「**화면 응답** · 최근 1시간 n회 · 느린 쪽 · 최고」(초) · 「**CPU** · 5분 평균 · 기동 뒤 최고(시각)」(코어) ·
  「**동시 세션** · 지금 · 기동 뒤 최고(시각)」(연결된 세션 — `memory_diagnostic.session_counts`)이고 못 잰 값은 「모름」, 시각은 KST
  `sso_status.CLOCK_FORMAT` 이다. 화면에는 값 줄만 두고 뜻은 Guide 「서버 시작 점검」 이다. `load_signal` 은 넘은 문턱 이름(지문 — 값은 싣지
  않는다) · 짧은 글 · 전문을 내고 개발자 알림 `AD-26` 은 `container_start_check.render_load_alert` 가 낸다(시작 점검 알림과 같은 판정의
  서버만 이벤트 칸 한 자리, 개발자 아닌 회차는 글 없는 해소). 회차 끝 기록 `note_run_end` 는 `app.py` 가 끝까지 돈 회차의 끝(정상 끝 ·
  페이지가 스스로 멈춘 `st.stop()` — `AppRun.finish_stopped` 가 참)에서 부르고 무엇이 나도 회차를 멈추지 않는다. 시험
  `tests/test_load_diagnostic.py`.
- `src/capa_simulation/components/bdq_token_admin.py` — Admin 「서버 시작 점검」 펼침 표 아래 「지금 토큰」 값 줄(`token_line` — 패키지가
  다음 조회에 읽을 토큰의 자리 · 파일 수정 시각 · 만료, 토큰 글 없음 — 복사 글에도 싣는다)과 개발자 회차의 「토큰 넣기」 단추 · 팝업
  (2026-11-12 사용자 결정). 단추는 개발자(`sso_identity.viewer_is_developer`)에게만 서고 — 등급 밖 기능이라 접속 명단처럼 숨긴다(9장 「접속 등급」) —
  `BIGDATAQUERY_LOGIN_TOKEN` 이 있거나 계정이 없으면 잠그고 까닭 풍선(`io/bdq_token.blocked_reason`)을 단다. 팝업은 Admin Area 열림 칸
  (`admin_dialog.ADMIN_DIALOG_KEY` — 접속 명단 「추가」 와 값으로 가른다)의 `DialogHost`(`admin_area_bdq_token_dialog_host`)가 열고,
  폼 안 비밀 칸(`type="password"` · `autocomplete="new-password"` · 라벨 접음) 하나와 「넣기」 뿐이다. 받은 회차에 세션 칸을 곧바로
  떼고(`tests/test_flash_messages.py` 허용 목록), 누른 회차에 신원을 다시 검증해 개발자일 때만 쓴다. 거절은 칸 아래 한 줄
  (`tests/test_data_error_mark.py` BESIDE — 토큰 글 · 길이 없음), 넣음 · 같음은 알림창이고 넣으면 `HOST.finish` 로 닫는다. 만료 1시간
  전 개발자 알림 `AD-11`(`expiry_alert_note` — 지문은 만료 시각 하나, 지난 것도 선다, 「그 화면으로」 Admin Area)은
  `container_start_check.render_token_alert` 가 낸다(회차 끝 다시 내기 `render_token_alert_late` 도 같은 짓기). 만료를 못 읽으면 서지 않고, BigDataQuery 자동 로그인이 서 있는 동안(`standing`)도
  서지 않는다(`io/bdq_token.token_expiry` — JWT `exp` 만).
  `app.py` 가 모든 화면 회차에 부르는 자리라 지금 토큰을 읽다 무엇이 나도(`read_current`) 값 줄은 「확인하지 못함」, 알림은 해소로
  물러서고, 시각대로 못 옮기는 시각은 「알 수 없음」(`_clock`)이다 — 넣기는 쓴 뒤 무엇이 나도 넣음으로 끝난다.
  토큰 알림의 걷은 번호 `AD-17`(자동 갱신 멈춤 · 실패) · `AD-18`(갱신 토큰 80일)은 다시 쓰지 않는다 — 자동 로그인 멈춤은 새 번호 `AD-23`,
  서지 못함은 `AD-24` 다.
  시험 `tests/test_bdq_token_admin.py`.
- `src/capa_simulation/components/extra_process_admin.py` — Admin Area 넷째 탭 「부대공정」(설계 A7 1단계). 상태 줄 값 한 줄(판 번호 ·
  공정 수 · 적용 시각, 끈 동안 「꺼짐 · 마지막 판 n」, 원천을 봤으면 「<자리> <낱말>(hh:mm 에 봄)」) · 가져오기(원천이 꽂혔을 때만) ·
  양식 내려받기(마지막 내용 판 — 끈 동안에도, 없으면 빈 양식) · 끄기 / 다시 켜기(같은 자리) · 받은 판의 거절 표 또는 값 줄(지금 판과의
  차이 · 앞 판 값으로 되돌리는 칸 G12 · 측정률 칸 — 받는 때 `stage_pack` 이 센다, 계산 없음)과 미리보기(「시험 계산」 을 누른 회차에만
  돌고 (sha, 계산 토큰 — 내용 토큰에 그 회차의 부하 예외 선언을 접은 것)마다 세션에 둔다 — 선언을 저장하면 메모가 빗나간다,
  시나리오를 못 읽으면 단추 자리에 「데이터 Error」 마크 `AD-07`) · 적용(되돌리는 칸이
  있으면 확인 칸을 채워야 열림 — UI-NTF-09) · 판 이력 표(적용한 사람 앞 두 글자) · 열린 회차의 상태 알림 `EP-03` · `EP-04`. 닫힌
  탭은 `admin_area` 가 그리지 않는다(위젯이 단추 · 내려받기 · 확인 칸뿐 — 닫힌 회차는 DB 를 읽지 않는다). 받은 판을 판정하다 난
  예외는 원천 실패와 같은 `EP-01` 길이다. 세션 칸은 `SessionSlot`(`STAGED` · `SEEN` — `peek`, 메모 `PREVIEW` · `TEMPLATE`). 쓰는
  단추는 `write_lock_reason`(C-DEP 판정 + 실제 개발자 — 「부하 예외」 탭과 한 판정 `sso_identity.production_write_lock_reason` 을 부르는 얇은 감쌈이고 시험이 이 이름을 바꿔 끼운다)이 열 때만이고 잠긴 동안 풍선에 까닭(UI-INP-07), 누른
  회차에도 다시 판정하며 쓰기는 본문(콜백 아님) · 저장소 `admin.area` 벽 · 판 이력 마지막 차례 대조다. 시험
  `tests/test_extra_process_admin.py`.
  - **「이 리비전 값을 새 판으로」**(2단계 — 설계 3-5 · A15): 사이드바에 올라와 있는 **저장 리비전**(미저장 편집은 들지 않음 — G1)의
    값으로 다음 판(P + 1)을 거꾸로 만들어(`services/extra_process_revision.pack_from_revision`) 받은 판 자리(`STAGED` — `revision`
    칸)에 둔다. 같은 거절 표 · 값 줄 · 시험 계산을 지나고 값 줄에 「옮긴 공정 · 옮기지 못한 공정 · 경로가 판과 다름」 수와 옮기지 못한
    공정의 까닭 표가 붙는다. 바뀐 칸이 없으면 알리기만 한다. 누를 수 없는 까닭(꺼짐 · 판 없음 · 다른 판으로 만든 리비전 · 섞인 판 ·
    연도 Shift · 부대공정 없음 — G4, 판은 sha 로 견줌)은 풍선이다. 「새 판 적용」 은 DB 에 갈래 「새 판」(`revise_extra_process` — 바탕
    시나리오 · 리비전 id)을 먼저 넣고, 내보내기 자리가 꽂혀 있으면 그 뒤 S3 Drive 파일을 덮는다(`_write_active` → `write_back` —
    결과는 0038 쓰기 기록 · 알림창 「앱이 덮음 · 판 n · 시각」 / 덮지 않음 경고 / 실패 오류 · 판 이력 「S3 쓰기」 칸). 활성 「새 판」 을
    아직 쓰지 못했으면 상태 알림 `EP-05` 와 단추 「S3 에 다시 쓰기」(누른 회차에 판 이력을 다시 읽어 이미 썼으면 쓰지 않음)가 서고,
    가져오기 원천이 꽂혀 있으면 5분에 한 번 원천의 머리 보기(`head`)로 「가져오지 않은 새 파일」(`EP-02`)을 본다(`HEAD_SEEN` —
    내보내기와 묶지 않음, 2026-11-19 보드 답). 가져오기 · 적용이
    성공하면 그 메모를 비워 다음 회차가 다시 본다 — 같은 세션이 가져와 적용한 파일을 5분 동안 「새 파일」 로 잇지 않고 상태
    줄도 그 회차 낱말이다(2026-11-19 E2E e3-D2, 설계 규칙 UI-NTF-02 — 조건이 사라지면 해소). 내보내기가 꽂히지
    않은 지금 판(운영 포함)은 DB 새 판만 넣고 `EP-05` · 다시 쓰기 단추가 서지 않는다 — 원천이 꽂힌 C-DEP 는 그 대신 판 어긋남
    상태 알림 `EP-06`(「S3 Drive 파일은 판 n 그대로 — 양식 내려받기로 새 판을 받아 놓으세요」, 판은 기준 ETag 를 가진 판) 하나가
    선다. 사람이 그 새 판을 놓아 가져오면 「바뀐 것 없음」 판정에서 `placed_matches` 가 참이라 `_note_placed` 가 쓰기 기록에
    「놓인 파일 같음」(결과 「씀」 + 까닭 낱말 `EXTRA_WRITE_PLACED_REASON` — 마이그레이션 없음, 감사 결과 `PLACED`)을 넣고 그
    ETag 가 기준이 되어 `EP-06` 이 풀린다 — 보통의 「바뀐 것 없음」(적용한 파일을 다시 가져옴)은 아무것도 적지 않는다. 적는 회차는
    판 이력을 다시 읽어 활성 판 sha 가 받은 판 sha 와 다르면(그사이 바뀜) 적지 않는다. 끈 동안 그 새 판 파일을 놓아 가져와 다시 켜면
    그 「다시 켜기」 줄의 ETag 로 S3 Drive 에 있는 것으로 보아(`pending_write`) `EP-06` 이 풀린다. 받을 것이
    아직 없으면(`SourceNotReady` — 여섯 다 없음 · 놓는 중) 알림창 안내와 상태 줄 낱말뿐이다(`EP-01` 아님). 판 이력 표의 「바탕」
    칸은 새 판의 「시나리오 r번호」 다. 시험 `tests/test_extra_process_revision_admin.py`(가짜 내보내기 · 가짜 원천).
- `src/capa_simulation/components/extra_process_notice.py` — 부대공정 판을 합친 결과 알림 한 꼴. 짧은 글은 「부대공정 2 합침」 ·
  「부대공정 1 합침 · 1 뺌」, 까닭은 Alarm 전문 — 뺀 · BDQ 에 생긴 공정이 있으면 경고, 모두 합쳤으면 알리기만(`popup_only`). 조건이 남는
  동안의 상태 알림 `EP-03`(최신 공식버전에서 뺀 부대공정) · `EP-04`(BDQ 에 같은 이름이 생겨 건너뜀)는 Admin 「부대공정」 탭이 열린 회차에
  최신 공식버전 데이터셋의 출처 표로 판정한다 — 자동 갱신(화면 없음)이 뺀 것도 잡는다.
- `src/capa_simulation/components/scenario_extra_overlay.py` — 시나리오 관리 작업 「부대공정 얹기」(D19 — 파생 저장 길). 활성 판이
  있을 때만 작업 줄에 선다. 바탕 저장 리비전의 데이터셋 출처가 가리키는 옛 판 공정(합침만 있는 것 — `split_previous`)을 걷고 활성
  판을 합친 결과 표를 보이고 `render_derived_save` 로 저장한다(원천 종류 `SCENARIO_EXTRA_PROCESS`, 포함 공정 = 바탕 프리셋 − 걷은
  공정 + 새로 합친 부대공정 — 바탕에서 꺼 둔 옛 부대공정은 꺼진 채, 새 판 출처). 월 머지로 판 행과 BDQ 행이 섞인 공정이 있는
  바탕은 거부 한 줄 + 그 공정 표만 서고 합치지 · 저장하지 않는다(걷으면 BDQ 행까지 지우고, 두면 옛 판 행이 BDQ 로 셈된다). 합친
  결과는 (DB, 바탕 리비전, 판 차례)마다 세션 메모 한 벌(`OVERLAY_MEMO` — `PAGE_DIALOG_SUFFIX`)이다.
- `src/capa_simulation/components/bdq_login_admin.py` — Admin Area 「BDQ 자동 로그인」 펼침(`BDQ_LOGIN_LABEL` — 「서버 시작 점검」 표 줄과
  같은 이름, 2026-11-16 결정 D1 · D2 · D5 · D7). 동기화 모드 `managed` + 쓸 수 있는 키(`bdq_login_store.availability` — 앱은 기동 때 키를 쥐고
  환경에서 빼므로 환경을 넘기지 않는다)인 서버의 개발자(`sso_identity.viewer_is_developer` — 「토큰 넣기」 와 같은 문지기) 회차에만 「서버 시작 점검」
  바로 뒤에 서고, 그 밖에는 Streamlit 호출이 없다. 값 줄 둘 — 상태(없음 · 정상 · 멈춤(까닭) · 확인하지 못함(읽지 못함 — 「없음」 과 가른다)) ·
  넣은 사람(개발자 앱 ID 앞 두 글자) · 넣은 시각 · 멈춘 시각, 그리고 이 프로세스의 마지막 시도(시각 · 자동/넣기 · 결과 · 남은 시간)와 그
  시도가 하위 프로세스를 띄웠으면 바로 아래 「진단」 값 줄(`diag_line` — 종료 코드 · 시그널 · 걸린 초 · 닿은 단계 · 패키지를 불러온 길(알 때만 —
  「불러오기 light / full」) · 표준 오류 마지막 예외
  종류 · bigdataquery · getpass_asterisk 판 · 하위 프로세스 앞뒤와 그 하위의 메모리 단서 「cgroup 앞→뒤/한도MiB · oom_kill 앞→뒤 · 한도 닿음 앞→뒤 · 앱 RSS 앞→뒤MiB · 하위
  최고 nMiB」(하위 최고는 그 하위 하나의 값, OOM 종료 수를 앞뒤 모두 모르면 「oom_kill 모름(파일 없음 · 줄 없음 · 못 읽음 가운데 하나)」 — 읽은 자리는 칸 `oom_src` 에만, 「한도 닿음」(컨테이너 메모리가 한도에 닿은 횟수)은 하나라도 읽었을 때만) · 띄우기 바로 앞 프로세스 단서 「앱 뜬 지 n.n시간 · 스레드 n · 열린 파일 n · pids n/한도 · 프로세스 n · 좀비 n」(2026-11-21 —
  막 뜬 pod 는 되고 오래 떠 있던 pod 는 import 중 끊기는 갈래를 가를 값, 재었을 때만 붙고 옛 기록은 지금 줄 그대로), 못 읽은 값은 「모름」 — `io/memory_probe`,
  `container_start_report.ChildDiag.text`) — BDQ 계정 ID 는 보이지 않는다.
  비밀번호를 보내기 전 끊김(`import_killed`)이 있으면 상태 줄 끝에 기다리는 차례 「다시 시도 n/3」(끊김 n번 뒤 — 기다리는 중이면 「다음 시각」,
  상한으로 멈췄으면 「3/3」)이, 끊긴 다시 시도의 진단 줄 끝(「서버 시작 점검」 진단 줄도 — 결과 칸 `retry`)에 그 시도 자신의 차례(처음 시도는
  꼬리 없음)가 같은 짧은 꼴(`bdq_login.retry_text` — `AD-24` 와 같은 낱말)로 붙고, 감사 상세 `retry` 는 넣기 때 걸려 있던
  차례(「n/3」 — 저장되면 넣기가 셈을 비웠다)다(2026-11-20). 폼은 `st.form(clear_on_submit=True)` 안 계정 칸 · 비밀번호 칸(`type="password"` · 라벨 접음 · 자리표시 글이 이름) ·
  「넣기」. 「넣기」 콜백(`_on_submit`)이 두 칸 값을 읽자마자 세션 칸을 빈 글로 바꾸고(본문 · 뒤 회차 어디에도 값이 없다) 누른 회차의 신원을
  다시 검증해 개발자일 때만 `bdq_login.login_from_form` 한 번 — 저장까지 되면 알림창(「BigDataQuery 로그인 됨 · 남은 n시간 n분」 · 멈춤 풀림 ·
  떠 있는 앱의 계정 원천이 곧바로 새 ID), 로그인 실패는 저장 없이 폼 아래 한 줄 + Alarm(「로그인 실패 — 저장 안 함」 · 「서버에 닿지 못함 —
  저장 안 함」 · 「로그인 확인 못 함(남은 시간 모름 · 7시간 이하 · 결과 표지 없음) — 저장 안 함」 · 「패키지 없음 — 저장 안 함」(패키지를 불러오지 못함 하나 — 하위 프로세스를 띄우지 못함 · 입력을 읽지 못함은 「로그인하지 않음(까닭) — 저장 안 함」 으로 「서버 시작 점검」 줄 · `AD-24` 와 같은 까닭 낱말) · 그 밖의 시도 전 거절은
  「로그인하지 않음(까닭) — 저장 안 함」 — 하위 프로세스가 표지 없이 끝난 거절 `no_marker` 는 「로그인 실패」 가 아니다, 비밀번호를 의심해
  되풀이하지 않게. 보내기 전 끊김은 「로그인하지 않음(불러오는 중 끊김) — 저장 안 함」 이고 폼은 다시 하지 않는다), 로그인은 됐는데 저장 실패는
  알림창 오류, 빈 칸 · 개발자 아님은 시도 없이 폼 아래 거부(`write_guard.queue_refusal` → `take_refusal`, `tests/test_data_error_mark.py`
  BESIDE). 같은 세션의 겹쳐 온 둘째 누름은 같은 값이면 시도하지 않는다(`write_guard.save_once` — 출발점은 값의 HMAC 지문, 키는 프로세스마다
  새로 · 빈 꼬리 누름은 `just_written`). 저장된 계정이 있을 때만 상태 줄 곁에 「정말 지웁니다」 확인 체크 + 「지우기」(체크 전 잠김 · 까닭
  풍선 `paste_form.PASTE_CONFIRM_WHY`, 켜면 되돌릴 수 없음 · 예비 길 풍선 — 페이지 안 확인 한 번, 브라우저 대화상자 아님)가 선다. 감사 줄
  `admin_bdq_login_set`(결과 · 까닭 코드 · 하위 프로세스 진단 칸 `exit` · `signal` · `sec` · `stage` · `stderr` · `bigdataquery` ·
  `getpass_asterisk` · `load`(알 때만) 와 메모리 단서 칸 열하나 `container_start_report.MEMORY_FIELDS` · 프로세스 단서 칸 일곱 `PROCESS_FIELDS` — `ChildDiag.fields`) · `admin_bdq_login_delete`(결과)에는
  계정 · 비밀번호가 없다. 알림 「그 화면으로」 받는 쪽
  `open_bdq_login`(대상 `bdq_login` — `AD-23` · `AD-24` · 계정 넣기 · 다시 넣기 갈래의 `AD-10`). 「토큰 넣기」(바로 위 펼침 안)는 예비로 남고 같은 결과의 단추가
  아니다(토큰 값 ↔ 계정 — UI-LAY-12). 시험 `tests/test_bdq_login_admin.py`(가짜 패키지 하위 프로세스 · 가짜 S3, 장면마다 `login()` 수).
- `src/capa_simulation/components/route_load_exception_admin.py` — Admin Area 「부하 예외」 탭(공정별 부하 산출 예외 선언 — 6장 (i)). 상태 줄 값
  한 줄(`status_line` — 「부하 예외 · 판 n · 공정 k · MM-DD HH:MM」, 저장한 적이 없으면 「부하 예외 · 선언 없음」, 공정 이름은 싣지 않음) · 산식
  (`ROUTE_LOAD_FORMULAS`)마다 다중 선택 하나(선택지는 활성 리비전 `RQ_REQB` 원본 공정명 — 견줌 키가 같은 표기는 하나, 화면 글자는 표시명이 있으면
  「표시명 (원본)」(UI-DAT-10), 이번 데이터에 없는 선언 · 고른 공정은 선택지에 남기고 「(이번 데이터에 없음)」 — 빠지면 다음 저장이 지운다, 겹친 글자는
  「 (2)」) · 「저장」 · 열린 회차의 판 이력 표(판 · 언제 · 누가 앞 두 글자 · 공정 표시명 · 산식 — 판마다 공정 한 줄, 비움 판은 빈 한 줄). 고르기 칸은
  지금 선언으로 채우며 그 판을 본 판(`SEEDED`)으로 둔다 — 남이 새 판을 저장하면 고친 것 없는 칸만 다음 회차에 다시 채우고, 고친 칸으로 누른 저장은
  `RouteLoadExceptionMoved` 로 쓰지 않고 새 판으로 다시 채운 뒤 알림창 · 곁에 알린다(UI-STA-05). 겹친 둘째 누름은 제 저장 짝
  (`write_guard.save_remembered` · `is_own_save`)으로 성공을 다시 알리며 칸을 저장된 판으로 다시 채우고, 거부를 보기 전에 닿은 둘째 누름(옛 고른 값 · 다시
  채운 본 판)은 거부 표지(`note_profile_conflict` · `held_profile_conflict`)로 쓰지 않으며, 지금 선언과 견줌 키가 같은 저장은 새 판 없이 「바뀐 것이 없습니다」(UI-STA-01),
  모두 뺀 저장은 비움 판 한 줄이라 확인 창이 없다(UI-STA-02). 저장 뒤 공용 프로필을 비우고(`clear_global_route_load_exceptions_cache`) 입장 Summary 확인을
  잊게 한 뒤(`forget_intro_summary_check`) 알림창 한 줄이다(UI-NTF-03). 쓰기는 본문(콜백 아님) · `write_lock_reason`(`sso_identity.production_write_lock_reason`
  — 「부대공정」 과 한 판정, 잠긴 동안 고르기 · 단추를 잠그고 풍선에 까닭 UI-INP-07) · 누른 회차에 다시 판정 · 저장소 `admin.area` 벽이다. 세션 칸은
  `SessionSlot`(`SEEDED`, 고르기 칸 `pick_slot`). 시험 `tests/test_route_load_exception_admin.py`, 화면 확인 `route_exception_tab`.
- `src/capa_simulation/components/notice_admin.py` — Admin Area 맨 끝 안쪽 탭 「공지」(2026-11-17 공지 보드 답 decided 1 ~ 6). 서 있는
  공지 카드(글 — 평문 · 값 줄 `notice_board.stamp_line` 「개발자 · 17:40 보냄 · 18:20 까지」 · 「거두기」) → 글 상자(라벨 접음 · 자리표
  「공지 글」 · 300자) → 끝 시각(`st.time_input` 10분 걸음 — 칸이 없을 때(Admin Area 를 처음 열 때 · 다른 화면에 다녀와 위젯 값이 걷힌 뒤)
  기본값 `notice_board.default_until` 을 심고 그 끝(날짜까지)을 `SEEDED_KEY` 에 적는다. 손대지 않은 기본값이 지나면 그리기 앞 · 「보내기」
  콜백에서 새 기본값으로 간다(`stale_seed` — 그대로면 「내일 그 시각」, 사람이 고른 시각은 그대로) · 「보내기」.
  「보내기」 콜백이 Admin Area 잠금 판정(`sso_identity.admin_area_locked`)을 다시 보고 글 · 끝을 검사해(빈 글 · 300자 넘음은 단추 아래 거부
  한 줄 — `write_guard.queue_refusal` → `take_refusal`, `tests/test_data_error_mark.py` BESIDE) 연 순간의 값(글 · 끝 ISO · 그때 서 있던 공지
  id — `PENDING_KEY`)을 쥐고 확인 팝업 「공지 보내기」(`admin_dialog` 한 칸의 값 `notice_send`)를 연다 — 값 한 줄 `confirm_line`(`끝 18:20` ·
  다음 날이면 `끝 내일 09:00` · 서 있었으면 ` · 서 있는 공지 바뀜`, `st.caption`) · 「보내기」(primary · `:material/campaign:`) · 「취소」.
  팝업의 「보내기」(`submit_notice`)는 다시 판정한 뒤 쥔 값 그대로 `notice_board.send(…, expected=…)` 한 번(`write_guard.save_once`) —
  팝업이 열린 사이 서 있는 공지가 바뀌었으면(`NoticeChanged` — 갈음 · 거둠 · 끝 시각으로 걷힘) 보내지 않고 팝업을 닫아 바뀐 카드를 다시
  보인다(글 상자는 그대로). 알림 글 · 감사 결과는 까닭 둘(`ended` — 「서 있던 공지가 끝났거나 거둬졌습니다」 · `result=ended` / 갈음 —
  「서 있는 공지가 바뀌었습니다」 · `result=changed`)이고 사람을 지목하지 않는다.
  결과는 모두 `queue_flash`(성공 「공지 보냄 · 18:20 까지」(끝이 다음 날이면 「11-18 09:00 까지」) · 「공지 거둠」 은 알림창으로만, 막힘 ·
  바뀜은 `popup_only`) — 보낸 뒤 다음 앱 전체 회차가 글 상자 · 끝 시각을 비운다(`CLEAR_KEY` — 팝업 회차에서 바깥 위젯 칸을 건드리지 않는다). 「거두기」 콜백(`withdraw_notice`)도
  다시 판정하고 그린 회차의 공지가 아직 서 있을 때만 걷는다(확인 없음). 감사 사건 `admin_notice_send`(결과 · 끝 시각) ·
  `admin_notice_withdraw`(결과) — 대상은 공지 id(`tgt`), 글은 어느 칸에도 없다(감사 불변조건). 시험 `tests/test_notice_admin.py`.
- `src/capa_simulation/components/module_status.py` — Admin Area 안쪽 탭 줄 오른쪽 끝 「모듈 상태」 팝오버(2026-11-10 보드 Q-6 — 켜짐·꺼짐·실패 수는 닫힌 단추 글 `status_title`, 그 안에 복사 · 까닭, 마지막 오류·회차 시간 표 — 칸 「마지막 회차 시간(ms)」 에 ms 정수, 정렬이 값 차례인 숫자 칸 `Int64` · `localized` — · 환경변수 줄). 탭 묶음을 담은 칸의 key 를 받으면 단추 칸을 그 칸 오른쪽 위에 얹는다(`tools_style` — 탭이 없는 회차는 흐름 안). 모듈 폴더가 없으면(사외 · `CAPA_MODULES_ROOT=off`) 그리지 않는다.
- `src/capa_simulation/components/module_failure_card.py` — 모듈 오류 카드. 자리에는 누구나 읽는 머리 한 줄(「「<모듈>」 화면에 오류가 났습니다 — 다른 화면은 그대로 쓸 수 있습니다」 · 가드 자리 · 앞 동작이면 그 범위의 말)과 값 줄 「담당 <이름>」 만, 개발자용 정보(형식·첫 줄, import 꼴 안내, 끄는 법, 모듈 폴더 안 프레임만)는 접힌 「담당자용 진단」 안 코드 칸 + 복사 단추다(`DIAGNOSTIC_LABEL` — 복사 key 는 카드마다 새로, 2026-11-14 「앱 대신 뜨는 화면」 보드 카드 p2-rare). 코드 칸은 평문이라 앱이 짓는 안내 줄(끄는 법 · import 안내)에 코드 표지(백틱)를 쓰지 않고, 줄을 꺾는다(`wrap_lines` — 앱 안 멈춤 판의 접힌 진단 · Admin 「서버 시작 점검」 pip 출력 끝과 같은 꼴, 설계 규칙 UI-CON-04). `module_runtime`(화면·콜백)과 `module_api` 의 `guard`(제자리)가 함께 쓴다.
- `src/capa_simulation/components/page_failure_card.py` — 코어 화면 감싸기(`run_core_page` — `app.py` 가 모듈이 아닌 화면의 `navigation.run()` 을 이것으로 부른다, `module_runtime` 과 같은 예외 사다리: 제어 예외 · `KeyboardInterrupt` 는 다시 던지고 `FragmentHandledException` 은 적기만, 그 밖 `BaseException` 은 카드 — 처리한 실패는 둘 다 `st.stop()` 으로 끝내 `app.py` 의 멈춤 길(`finish_stopped`)을 탄다. 정상으로 돌아오면 Streamlit 이 그 회차를 끝까지 돈 것으로 보고 오류 자리 아래에서 이번에 그리지 못한 위젯의 미저장 값을 지운다). 처리 못 한 오류는 Streamlit 기본 오류 상자(경로 · traceback) 대신 그 화면 자리 카드 하나 — 앱 안 멈춤 판의 한 꼴(`stop_panel`, 보드 stop-panels): 「이 화면에 오류가 났습니다 — 다른 화면은 그대로 쓸 수 있습니다」 → 주 단추 「다시 시도」(`RETRY_KEY` — 회차 하나) → 「문의 <메일>」 → 「참고 <참고 번호 8자> · <UTC 분> · <오류 종류>」(UTC 분은 실패를 적은 순간 `PageFailure.epoch` — `AD-22` 의 시각과 같은 순간) → 개발자 몫(`stop_panel.admin_fold_visible`)에만 접힌 「개발자용 진단」(맨 위 참고 줄 · 화면 · 첫 줄 · 이 저장소 안 프레임 · 복사 — C-DEP 에는 로그가 없다). 실패는 `page_failures` 에 적고 서버 로그에 참고 번호와 원문을 남긴다. 개발자 상태 알림 `AD-22`(`render_page_failure_alert` — `app.py` 가 토큰 알림 곁에서 부른다)는 프로세스 기록에서 낸다 — 오류가 난 탭이 개발자의 탭이 아니어서다. 이벤트 칸 수가 프로세스 동안 같도록 시작 점검 알림 `AD-01` 과 같은 판정(`start_check_alert_possible`)이 참인 서버만 회차마다 한 자리(실패가 없거나 개발자가 아니면 해소)이고 그 밖(개발 · 사내 PC · 시험)은 Streamlit 호출이 없다 — 그 서버는 운영이 아니고 통합인증이 꺼져 카드의 「개발자용 진단」 이 누구에게나 선다. 지문은 프로세스에서 난 (화면, 종류) 쌍 모두, 건수는 최근 줄 상한과 따로 센다. HOME 의 「그 화면으로」 주소는 빈 글자다. 시험은 `conftest` 가 감싸기를 걷어(`app.py` 를 도는 시험이 실패를 놓치지 않게) 보고, 감싸기 자체는 `@pytest.mark.page_failure_card`(`tests/test_page_failure_card.py`). 화면 확인(`check_deploy_screens` 의 예외 세기)도 이 카드 칸(`CARD_KEY`)을 예외로 센다. 운영 이미지는 감싸지 못한 자리(위젯 콜백 · 프래그먼트만 도는 회차)의 Streamlit 기본 오류 상자에 오류 종류 이름만 싣는다(`docker/Dockerfile-prod` 의 `STREAMLIT_CLIENT_SHOW_ERROR_DETAILS=type` — 보드 d12 (가)).
- `src/capa_simulation/components/missing_page.py` — 없는 화면 주소(꺼진 · 실패한 모듈 화면 · 옛 주소 · 남이 보낸 링크)로 들어와 HOME 을 도는 회차를 가려 사건 알림 하나(「없는 화면 주소 — HOME 을 열었습니다」, 꺼진 · 실패한 모듈이면 「「<모듈>」 은 꺼져 있습니다 · 담당 <이름>」 — `module_registry.discovered`). 판정은 Streamlit 페이지 개발자가 받은 주소 이름(`intended_page_name`)과 `st.navigation()` 이 고른 주소의 맞댐이고 같은 주소는 세션에 한 번이다. `app.py` 가 이번 화면을 적은 뒤 · 알림 칸 앞에서 부른다. 코드는 등록부 「동작 결과 — 안내」(`FL-02`)이고 영어 「Page not found」 팝업은 감추지 않는다(2026-11-14 보드 카드 p2-rare).
- `src/capa_simulation/components/exclusion_table.py` — `산출 결과` 의 제외 목록 가운데 표가 커서 알림에 싣지 못한 것(대당
  Capa `제외 기준정보 확인` · 소요대수 탭 목록)을 본문에 그리는 단일 렌더러다(`column_help` — 칸 머리 풍선). 화면은
  표시명 복사본, CSV 는 원본이고,
  캐시된 `attrs` 유래 입력을 제자리에서 고치지 않는다. 내보내기 프레임(`exclusion_export` — 분류 칸을 공용 표시순서로
  세운 원본)은 제외 알림에 딸린 표(`state_alerts.alert_table`)도 쓴다.
- `src/capa_simulation/components/plan_comparison_dumbbell.py` — 두 시나리오의 기간 계획 물량 차이를 분류별 덤벨로
  그린다. 한쪽에만 있는 분류는 다른 쪽을 0 으로 보고 연결선은 `DELTA_*` 다.
  - 그림은 `build_plan_comparison_dumbbell` 이 만들고 `render_plan_comparison_dumbbell` 은 받은 그림만 그린다(HOME 은
    계획 세부수량 Figure 묶음에 함께 캐시한다).
  - 분류에 `CUSTOM` 이 있으면 줄 이름의 제품 자리에 녹인다(`product_parts.part_merged_columns` — 「제품 (부품) · Stack」).
- `src/capa_simulation/components/source_quality.py` — 활성 시나리오 원천 78컬럼의 결측률·카디널리티 표다.
  `load_source_profile` 의 값만 써 새 조인이 없고 등급을 글자로도 적는다. 결측률 막대는 `percent_progress_column`(8장 「표의 % 칸」).
- `src/capa_simulation/components/percent_cells.py` — 표의 % 칸을 소수 둘째 자리 고정 글로 보이게 하는 한 벌 도우미(8장 「표의 %
  칸」 — 설계 규칙 UI-DAT-12). 읽기 표는 `percent_column` 으로 칸을 적고 `percent_table` 이 (Styler, 칸 설정)을 돌려준다 — 그 칸의
  `format` 을 빼고 표시 글 `percent_cell_text`(그리드 쌍둥이 `services.edit_grid.fixed_percent_text` 를 부름)를 걸며, 같은 표의 꼴 없는
  실수 칸에는 Streamlit 기본 꼴 글을 건다. % 칸이 없거나 Styler 상한(`styler.render.max_elements`)을 넘는 표는 받은 그대로, Styler
  id 는 칸 이름으로 지어 회차마다 같다. 막대 칸은 `percent_progress_column`(`step` = `PERCENT_STEP` 0.0001 — 글 자릿수만).
- `src/capa_simulation/components/equipment_lifecycle_gantt.py` — 호기별 생애주기 구간 Gantt 를 그리기만 한다(구간은
  `services/equipment_availability.build_equipment_lifecycle_spans`). Plotly 구간 끝이 배타적이라 끝날에 하루를 더한다.
- `src/capa_simulation/components/wip_status_dashboard.py` — 제품 행 × STEP·공정 열(`P → T`, 숫자 구간 오름차순)의
  고정 셀 Plotly 재공 격자(재공·유입·Flow 막대와 표준 가능량 기준선)를 만든다.
  - 화면은 `remembered_wip_status_grid_figure` 로 부른다 — 직전 Figure 한 벌을 세션에 두고 입력이 `DataFrame.equals`
    로 같으면 다시 쓴다. Streamlit 캐시가 아니라 캐시 경계 밖이다.
  - 칸 높이(`WIP_GRID_CELL_HEIGHT_PX`)와 줄 사이(`WIP_GRID_ROW_GAP_PX`)는 px 고정이고 그림 높이·줄 사이 비율은 그 둘에서
    셈한다(`wip_grid_height_px`·`wip_grid_vertical_spacing`) — 줄 사이는 아래 칸의 두 줄 제목과 위 칸의 -45° 날짜 눈금을 함께
    담고도 사이가 떠야 한다. 범례도 첫 줄 칸 위로 px 고정이다(`wip_grid_legend_y`) — 범례 y 를 축 영역 비율로 고정하면 1줄
    격자에서 첫 줄 제목과 겹치고, 4줄부터는 위 여백을 넘어 plotly 가 여백을 늘린다.
  - 지금 값은 줄 사이 80px 이다(64px 는 눈금과 제목 사이가 2px 만 떠 제목이 위 칸 것으로 읽혔다). 범례 아래 끝은 첫 줄 칸 위 50px 이다. 값과 까닭의 정본은 두 상수(`WIP_GRID_ROW_GAP_PX` · `_GRID_LEGEND_LIFT_PX`)의 주석이다.
- `src/capa_simulation/components/grouped_monthly_table.py` — 환산 결과처럼 편집하지 않는 월별 표를 고정 분류 영역 +
  스크롤 월 영역 Plotly 표로 그린다. 계층 그룹·제품/양산구분 Total·전체 합계 행을 넣고 같은 구조의 CSV 프레임을
  만든다. 계산 원본은 바꾸지 않는다.
- `src/capa_simulation/components/hierarchical_monthly_table.py` — 대당 Capa·확보율·소요대수처럼 합계행 없는 월별
  결과를 같은 고정 분류 + 스크롤 월 Plotly 표로 그린다(반복값 생략·계층 경계, 숫자/퍼센트 모드, 큰 표는 페이지 단위).
  표시 모드는 원본 값을 바꾸지 않고, 화면과 같은 꼴의 CSV 프레임을 만든다. 큰 표의 「표시 범위」 칸은 표 제목 줄 내려받기(CSV 단추 또는 「내려받기 ▾」 메뉴) 곁이고
  (`page_slot` — 부르는 쪽이 `table_toolbar.table_heading_row` 안에 만들어 넘긴다, 2026-11-07 답 table-top), 값 글에 전체 행 수가
  든다(「1–80행 / 153행」). 행 수가 바뀐 회차에는 고른 차례를 새 쪽 수 안으로 잘라 다시 적고, 마지막으로 그린 (행 수, 차례)를
  `<key>_page_shown` 에 둔다 — 늦게 떠난 회차가 싣고 온 옛 글(새 보기에 없는 값 글)은 그 차례로 되돌린다
  (`_refit_range_on_new_total`).
