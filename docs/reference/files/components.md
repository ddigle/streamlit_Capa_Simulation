# AGENTS 3장 — 파일별 책임 > 화면 공통 계층

### 화면 공통 계층

- `src/capa_simulation/navigation.py` — 사이드바 페이지 목록·그룹 상자·구역 제목을 선언하고 `st.Page` 묶음을
  만드는 단일 선언 지점이다. 페이지 추가·제목 변경·새 그룹은 여기서만 한다.
  - `PageSpec`·`SIDEBAR_GROUPS`·`SIDEBAR_SECTIONS`(`section.key` 가 컨테이너 key·CSS 선택자의 근거)·`ADMIN_AREA`·
    `ADMIN_BOX_PAGES`. 상태 접미는 `IMPLEMENTING_SUFFIX` 하나다 — 구현 중 화면은 머리 배지 없이 화면 탭 이름 곁 표지가
    말한다(`show_status=False` — 코어 2026-11-09 보드 T8, 모듈 L0 · L1 화면 2026-11-10 보드 Q-5 · 창구 1.2). 원천
    미연결 화면은 `PageSpec.pending_source`(그 화면이 스위치 · 머리 띠 표지 · 탭 풍선에 주는 원천 이름)를 선언하고,
    `PageSpec.implementing`(라벨 `(구현중)` · 그 선언 · 만드는 중 선언 `in_progress` — Dynamic Capa 는 그룹 머리라 라벨에 달지
    않는다, 생산 진도 · 샘플 페이지 셋은 원천도 접미도 없어 `in_progress`)이 화면 탭 「구현중」 표지의, `pending_source` 가 머리 띠
    「합성 샘플」 표지의 근거다(2026-11-09 보드 T8 (가) — 그물 `tests/test_page_tabs.py`). 운영 서버에서 개발자에게만 세우는 화면은
    `PageSpec.unfinished`(코어 화면이고 `pending_source` 또는 `in_progress` — 라벨 `(구현중)` 은 보지 않아 L0 · L1 모듈 화면은
    밖)이고, `build_navigation_pages(hide_unfinished=True)` 는 그 화면을 그릴 상자에서 빼(머리가 그런 그룹은 상자째)
    `NavigationPages.unlisted` 로 옮긴다 — 등록은 그대로라 주소가 산다(빼면 Streamlit 「Page not found」). 이 모듈은 `sso_identity`
    를 읽지 않고 `app.py` 가 판정 값을 넘긴다(2026-11-24 정식판 마감 2-A, 시험 `tests/test_app_navigation.py`).
  - `PageSpec` 이 화면이 `app.py` 에 바라는 공통 조건(`reads_*`·`condition_tabs`·`has_condition_cards`)과
    설비 DB 핀(`uses_equipment_db`)·설비 시나리오(`equipment_scenario` — `"session"`/`"official"`, `equipment_scenario_tabs`,
    `reads_equipment_scenario_on`)를 선언한다. `app.py` 는 선언만 따르고 화면 이름으로 가르지 않는다. 미룬 패널 화면(실적 셋 ·
    Dynamic · 재공)은 카드를 세워도 `has_condition_cards` 를 선언하지 않는다 — 선언 대신 패널 줄이 제목을 세운다(9장
    「공통 줄이 없는 화면도 제 줄은 같은 패널에 그린다」). 가용설비 현황 탭
    라벨(바깥 `EQUIPMENT_TABS`·Summary 안쪽 `EQUIPMENT_SUMMARY_TABS`)도 사이드바가 열린 탭을 보므로 여기 둔다. 안쪽 탭을
    품은 바깥 탭은 `ConditionTabs.sub`(`SubTabs`)로 적고, 사이드바는 `ConditionTabs.active_label`(위젯 값 → 기억 칸 → 첫
    탭, 라벨 목록 밖의 옛 값은 첫 탭)로 **가장 안쪽 라벨**을 본다 — `labels`·`card_labels` 도 안쪽 라벨로 적는다.
- `src/capa_simulation/module_registry.py` — 모듈(`modules/<id>/`) 찾기·`module.json` 검증·상태(켜짐·꺼짐·실패와 까닭). Streamlit 실행 문맥 없이 돌고 프로세스마다 한 번 찾는다(`discovered` — 키는 뿌리·끄는 환경변수). `scripts/check_module.py` 가 같은 검증을 쓴다. 모듈끼리 화면 이름이 겹치면 차례(order → id)가 뒤인 모듈 전체가 실패하고 까닭에 상대(코어 · 앞 모듈 id)를 적는다(`ModuleRecord.clash` — 점검은 앞 모듈에 M01 경고를 단다).
- `src/capa_simulation/module_api.py` — 모듈이 import 하는 **유일한** 코어 창구 v1(문맥·키 접두·머리말·색, 코어 데이터 없음 — 창구
  1.1 부터 `page_header(description=)` 은 받기만 하고 그리지 않는다, 작은 결정 d1. 1.2 부터 `page_header` 는 L0 · L1 의 「구현중」
  배지 줄도 그리지 않는다 — 화면 탭 표지가 말한다, 2026-11-10 보드 Q-5. 1.3 부터 바깥 자리 도우미 `query_bigdataquery` ·
  `s3_upload` · `s3_download` 와 `BigDataQueryError` · `S3Result` · `S3_MAX_BYTES` — 2026-11-12 사용자 결정 「도우미 함수로」). 하위 호환으로만 바꾸며 `tests/test_module_api_surface.py` 가 겉면을 고정한다(12장 「코어 공개 창구 변경」).
- `src/capa_simulation/module_helpers.py` — 창구 도우미의 속(모듈은 import 하지 않는다 — M06). BigDataQuery 는 앱과 같은 길
  (`load_bigdataquery_module` → `call_get_data`)로 묻고 실패 갈래를 `BigDataQueryError.kind` 로 옮긴다(기간 자리 `{start_date}` ·
  `{end_date}` 는 `str.replace` — 최대 366일). S3 는 `io/s3_small` 로 `modules/<id>/<이름>` 을 주고받는다(이름은 마디 넷 ·
  영숫자 꼴, 링크로 데이터 자리 밖을 가리키면 거절, 받기는 임시 파일에서 한 번에 바꿈). 키 · 주소 · 버킷은
  `auth.runtime.config().access_s3`(운영 진입 파일이 환경에서 뺀 뒤에도 남는 한 벌), 모드는 `object_storage.load_settings`.
  모듈 시험 표지(`module_registry.TEST_RUN_ENV_VAR`)면 밖에 닿지 않는다. 까닭 · 로그는 고정 낱말뿐이다.
- `src/capa_simulation/korea_time.py` — 화면 · 알림 · 복사 글에 그리는 시각의 시각대 한 곳(`KST` — +09:00 고정 ·
  `kst_clock(시각대 붙은 시각 · UNIX 초, 꼴)` — 시각대 없는 시각은 `ValueError`, 먼 시각은 넘침을 그대로 올림). 표준 라이브러리만
  쓴다 — `audit/read.KST` · `auth/page_frame.KST` 는 이 상수 그대로다. 규칙은 8장 「화면 시각은 KST」.
- `src/capa_simulation/notice_board.py` — 개발자가 보낸 공지 하나(2026-11-17 공지 보드 답 q-use — 프로세스 메모리 · 잠금 하나 ·
  재시작하면 걷힘 · 서버 한 대 전제). `Notice`(짧은 무작위 id · 글 · 보낸 시각 · 끝 시각(KST) · 보낸 이 「개발자」 — `SENDER_LABEL`) · `current` · `revision`
  (보냄 · 거둠 · 끝남마다 오름) · `send`(갈음 · 같은 글 + 같은 끝은 한 번 · `expected` 대조는 잠금 안 — 어긋나면 `NoticeChanged`, `ended` 는 서 있던 공지가 없어졌는가(끝남 · 거둠) · 거짓이면 갈음) ·
  `withdraw`(그 id 일 때만) · `check`(빈 글 · 300자 넘음 · 끝 ≤ 지금 · 24시간 넘음은 `NoticeInvalid` — `ValueError`, `message` 는 미리 정한 글뿐이라 화면이 `str(exc)` 없이 싣는다) · `default_until`(지금 + 1시간 10분 올림) ·
  `until_from_time`(지난 시각이면 내일) · `until_text`(끝 글 — 보낸 날의 다음 날이면 `11-18 09:00`, 판 · 전문 · 카드 · 보냄 알림창이 같은 글) ·
  `payload`(프로세스 표지 `PROCESS_MARK` · 판 · 공지 칸 `NoticeView`(KST 시각 글 · 끝 epoch ms) ·
  상태 표지 `GL-09` — `alerts.state_note(…, pageless=True)` 그대로, 없어도 active 거짓) · `reset`(시험 — `conftest._without_notice`). 끝 시각은
  읽을 때 본다(배경 스레드 · `st.cache_resource` 없음). Streamlit 을 읽지 않고 등록부(`alerts`)는 `payload` 가 부를 때 들인다 — 문지기 쪽
  물음 처리기가 부를 자리다. UI 없음. 시험 `tests/test_notice_board.py`.
- `src/capa_simulation/page_failures.py` — 코어 화면 실패 기록(참고 번호 · 시각(KST) · 화면 이름 · 주소 · 예외 형식 이름 — 본문은 적지 않는다, 최근 20건과 따로 건수 · 난 (화면, 종류) 쌍, 재시작하면 빔). UI 없음. `page_failure_card` 가 적고 `AD-22` 가 읽는다.
- `src/capa_simulation/load_metrics.py` — 부하 계측(배경 스레드 없음 · Streamlit import 없음 · 재시작하면 빔). `app.py` 가 전체 회차 맨
  앞에서 `begin_run` 으로 시각을 쥐고 끝까지 돈 회차 끝에서 `finish_run`(스크립트 시간 · `time.process_time` · 연결 세션)을 적는다. 화면 응답은
  최근 1시간 · 많으면 5,000회 창의 느린 쪽(p95 가까운 순위 — 20회 전에는 모름) · 최고(정렬은 읽을 때, 5초 다시 씀), CPU 5분 평균은 5초에 한 번까지의
  CPU 시간 표본(첫 표본은 import 때)에서 5분 전 값을 곧게 이어 읽은 (지금 − 5분 전) ÷ 300초(기동 뒤 5분 전에는 모름)와 기동 뒤 최고 · 시각,
  동시 세션은 기동 뒤 최고 · 시각(같은 값이면 처음 시각 — 「기동 뒤」 는 모듈을 처음 불러온 `app.py` 첫 회차부터). 세지 않는 회차 · 몫 —
  상호작용이 끊은 회차 · `st.rerun()` 끝 · 페이지 앞 멈춤 · 프래그먼트만 도는 회차 · 스크립트보다 먼저 도는 위젯 콜백 · 회차 뒤 GC. 문턱 판정 `crossed`(느린 쪽 3초 · CPU 0.7코어 · **지금** 연결 25 — 모두 이상, 제안값). 화면 응답 판정은 기동 뒤 5분(`SLOW_SETTLE_SECONDS` — 제안값) 뒤
  회차만의 느린 쪽(`ResponseView.signal_seconds`)이다 — 막 띄운 서버의 첫 그리기가 작은 창의 p95 를 정해 배포 날마다 `AD-26` 이 서지 않게(값 줄은 모든 회차). 회차당 비용은 기록
  약 2µs · 알림 판정 약 3µs, 5,000회 창 정렬 약 0.2ms(5초에 한 번까지 — 샘플 관측, 개발 WSL). 시험 `tests/test_load_metrics.py`(conftest 가
  시험마다 `reset`).
- `src/capa_simulation/module_failures.py` — 모듈 실행 기록(마지막 실패와 자리 · 재시작까지 뺀 화면 · 회차 시간 · 접두 없는 키). Streamlit 실행 문맥 없이 돌고 UI 를 부르지 않는다. `module_api`·`module_runtime`·`navigation` 이 함께 적는다(순환 막기).
- `src/capa_simulation/module_runtime.py` — 모듈 화면 실행 감싸기(그 화면만 오류 카드 · `StopException`·`RerunException` 은 다시 던지고 `SystemExit`·`FragmentHandledException` 은 적고 정상으로 돌아옴 · 앞선 콜백 실패 카드 · 접두 없는 세션 키의 새로·바꿈·지움 알림 — 상태 알림 `MO-02`, 범위는 모듈 id. 화면 앞에서는 넘긴 것이 없어도 `alerts.flush` 한 자리).
- `src/capa_simulation/page_bootstrap.py` — 계산 페이지 공통 진입 절차(활성 리비전·표시순서·활성 시나리오·
  조회기간과 원천 유효 구간 확정, 지금 부하 예외 선언 판)다. 페이지는 `BOOTSTRAP_ERRORS` 를 잡는다.
  - `PageContext.route_exceptions` 는 그 회차의 부하 예외 선언 판(`current_route_exceptions` — 부를 때의 `settings.DUCKDB_PATH`
    공용 프로필, 쓰기 세대 키 칸)이고 계산 키는 `.declaration` 을 빌더에 넘긴다. `PageContext` 를 쓰지 않는 HOME · 표준 대비 재공도
    `current_route_exceptions` 로, DB 경로를 쥔 화면(사이드바 리비전 저장 · 공식 지정 · 입력 점검 · 복제 · 파생 저장 · 부대공정
    미리보기)은 그 경로로 읽는다(`route_exceptions_of`). 읽은 판은 세션에도 적는다 — 편집본 칸 걷기가 그 판으로 접은 키를
    걷는다(5장 45). 공용 프로필 로더는 부를 때 `persistence.cache` 모듈에서 찾는다 — 페이지 시험이 그
    속성을 바꾼다.
  - 잡은 예외의 화면 문구는 `bootstrap_error_message` 한 곳이다. `duckdb.Error` 는 갈래마다 조치를 바꾼다 — 쥔 PID 가
    적힌 잠금(이 앱 자신이면 새로고침, 다른 프로그램이면 그것을 닫기), 쓰기 실패(DuckDB 영문 고정 문구 `Could not
    write`·`Failed to commit` — 「저장되지 않았습니다. 디스크 공간과 쓰기 권한」), 그 밖의 열기 실패(`IOException` 의
    `Cannot open`·`Could not set lock` — 다른 프로그램·파일 권한과 경로), 어느 것도 아니면 「데이터베이스 작업이
    실패했습니다」다. 쓰기 실패와 그 밖에는 원문(종류 이름 + 앞 300자, 줄바꿈을 접은 코드 표기)을 붙인다. 그 밖의
    예외는 서비스가 만든 한국어 문장에서 **물결표만 막아**(`markdown_safe_tildes`) 돌려준다 — 저장소·서비스 예외 글은
    사람이 지은 이름을 날로 담고 돌려준 글은 거의 다 알림 상자·캡션(마크다운)으로 간다. 이미 막힌 `\~` 는 다시 막지
    않는다. 마크다운이 아닌 자리(콘솔 — `scripts/sync_object_storage.py`, JSON·`st.code`·Plotly 풍선·`html.escape` 한
    HTML)만 `markdown=False` 로 원문을 받는다. `database_paths`(어느 DB 인지는 부르는 쪽이 안다)는 화면 수십 곳이 같은
    꼴로 부른다.
  - `scenario_capacity_and_demand`·`stop_calculation_on_error` 는 계산이 멈추면(ValueError) 사이드바를 「계산
    멈춤」으로 바꾸고 다시 던진다(뒤의 것은 시나리오 수준 오류만 나는 호출에만). 계산 함수는 부를 때
    `simulation_cache` 모듈에서 찾는다 — 페이지 테스트가 그 속성을 바꾼다.
  - `no_demand_message` 는 `resolve_effective_months` 를 거치지 않고 소요대수가 빈 것으로 「조회기간에 소요대수가
    없다」를 아는 자리(필요 단축 일정, Static 대비 일정의 확보율 교차검증)의 안내다 — 다른 계산 화면과 같은 문구에
    활성 시나리오 `RQ_REQB` 의 데이터 범위를 붙인다. 소요대수를 읽지 못한 갈래의 문구와 섞지 않는다.
  - `prune_list_selection`·`prune_choice` 가 위젯 값 정리다. 둘은 위젯 앞에서 매 회차
    세션에 되쓴다(`pop` 하지 않는다). `prune_choice` 는 글자 선택지 전용이다(`str(saved) in options`) — 정수 달 상자는
    제 화면이 잡는다(`constraint_simulation_state.settle_period`). `prune_named_choice` 는 쓰기 단추의 대상을 고르는
    상자의 짝이다(9장 「글자가 바뀌는 것을 피할 수 없는 상자」). `render_schema_ahead_warning` 은 DB 가 코드보다 새
    버전인지 상태 알림으로 낸다(시뮬레이션 DB `GL-02` — `app.py`, 설비 DB `GL-06` — 그 DB 를 여는 화면. 자리에는 그리지
    않고, 새 판이 아니어도 부른다 — 해소 · 이벤트 칸 한 자리).
  - `process_page_inputs(database_path)` 는 공정 하나를 보는 두 화면(공정 Capa 상세·제약 시뮬레이션)의 공통 진입이다 —
    판정 기준 → 공통 진입 → 유효 기간(`RQ_REQB`) → 시나리오 키 → 확보율(멈추면 「계산 멈춤」) → 달·공정 선택지를 **같은
    차례**로 내 두 화면의 계획 캐시 키가 같다. 카드 캡션·마크·`st.stop` 은 페이지가 쥐고, DB 경로는 페이지가 그 회차의
    `settings` 에서 읽어 넘긴다(시험이 설정을 바꾼다).
  - `forget_page_dialogs`·`count_page_visit` 은 `app.py` 가 페이지가 바뀐 회차에 부른다(팝업 열림 칸 버림·방문
    차례 올림). 앞의 것은 팝업 여는 콜백도 부르지만 뒤의 것은 그 회차에만 부른다 — `page_visit` 으로 「다시
    들어왔다」를 아는 화면이 같은 페이지의 rerun 에서 위젯 아닌 칸을 거두지 않게.
- `src/capa_simulation/settings.py`, `sidebar_status.py` — 앱 이름·판·경로·조회기간 상수, 배포 번호를 붙인 앱 판(`settings.app_version`)과 운영 DB 자리 판정
  (`settings.is_operational_database_place` — 사본 전용 스크립트의 거절과 점검 스크립트의 앱 프로세스 확인이 쓴다)과, 사이드바의
  구역 제목·조건 패널 칸·조회기간 상태 표시·접힘을 기억하는 상자·조건 카드(`sidebar_status`)다. 편집기 구역 끄개 읽기는
  `settings.editor_scopes_enabled` 다(9장 「구역 회차 규칙」 끄개).
  - 월 표기 `YYYY-MM` 은 `settings.format_month` 한 벌이다. 조건 패널의 페이지 칸(`page_condition_slot`)은
    세션에 둔다 — 모듈 전역에 두면 세션끼리 나눠 쓴다. 공통 줄이 없는 화면은 칸 대신 미룬 패널(`defer_page_condition_slots`)을
    적고, 페이지가 칸을 처음 쓸 때 제목 · 패널이 선다(9장 「사이드바·조건 카드·본문」).
  - `sidebar_expander`·`condition_card` 는 `key` + 상태 추적 `on_change` 로 펼침을 기억한다(`expanded=` 없음).
    조건 카드 key 는 `condition_card_<이름>` 이고 `sidebar_style.py` 가 그 접두어 하나로 서식을 건다.
  - 상자 여닫기는 9장 **여닫을 때 본문을 다시 돌리지 않는다**의 구현이다(`on_box_toggle`·`rerun_fragment_if_alone`·
    `keeps_app_run_open`·`lowers_app_run`·`begin_app_run`). 진짜 프래그먼트 회차는 `tests/fragment_browser.py` 대역으로 돌린다. 「이번 상호작용에서
    그 위젯만 바뀌었나」(`_only_this_widget_changed`)는 Components v2 부품의 트리거 모음 칸(1.63 `_make_trigger_id(<부품 id>,
    "events")` — `own_widget_ids`)도 그 위젯으로 센다 — 화면 탭 줄 고정·차례가 이 길로 페이지를 다시 돌리지 않는다(2026-11-02).
    내부 이름이 바뀌면 그 칸이 「다른 위젯」 으로 세어져 앱 전체 회차로 물러난다.
- `src/capa_simulation/design/tokens.py` — 색·서체·표 치수를 역할 이름으로 단일 정의하고 지금 테마의 값을
  돌려준다(규칙 `docs/design_system.md`). Figure 공통 유틸은 `components/plotly_layout.py` 다.
  - 두 팔레트(`_LIGHT`·`_DARK`)를 `__getattr__`(PEP 562)로 골라 쓰는 쪽은 `tokens.SURFACE` 그대로다. 두 팔레트의
    이름은 정확히 같아야 한다(`tests/test_design_tokens.py`). 별칭·계산값은 `_complete()` 가 팔레트에서 만든다.
    알파가 없는 자리(엑셀 칠)로 반투명 토큰을 옮길 때는 `opaque_over(색, 바탕)` 다(rgba 글자를 화면 코드에 두지 않는다).
  - 타입은 `if TYPE_CHECKING:` 블록이 알린다(`.pyi` 스텁은 mypy 가 무시한다). 테마를 타지 않는 치수는 팔레트 밖이다.
- `src/capa_simulation/design/theme.py` — 세션이 보는 테마를 실행 한 번에 한 번만 정해 스레드 칸에 담는다(모듈
  전역 아님). `app.py` 가 토큰을 하나라도 읽기 전에 `begin_run()` 을 부른다.
  - 프래그먼트만 도는 회차는 세션(`_capa_theme_mode`)의 직전 전체 회차 테마를 잇는다 — 프래그먼트 본문에서
    `begin_run()` 을 부르지 않는다(`tests/test_shortening_view_fragment.py`).
  - 보는 사람의 테마와 상관없이 늘 같은 색이어야 하는 산출물(공정 Capa 상세 시트 엑셀 — 밝게)은 `pinned_mode(mode)` 안에서
    만든다 — 스레드 칸을 잠시 바꾸고 나오면 되돌린다.
- `src/capa_simulation/components/page_header.py` — 모든 페이지의 제목·상태 배지다(상태 접미는 사이드바
  라벨과 같은 문자열). **큰 제목은 키 칸(`PAGE_TITLE_KEY`)에 담아 화면에서만 sr-only 로 숨기고**(화면 탭 줄이 이름을
  말한다 — 2026-10-24) 인쇄·읽기 도구에 남긴다. 배지 줄을 그리는 화면은 지금 없다(`badges` 인자를 넘기는 화면도 없다) —
  구현 중 화면은 배지 없이 화면 탭이 표지를 단다(`show_status=False` — 코어 2026-11-09 보드 T8, 모듈 L0 · L1 화면 2026-11-10
  보드 Q-5). 화면 머리에 설명 줄을 두지 않고 소개는 그 화면 Guide 가 맡는다 — `description` 인자를 넘기는 자리는 없다(모듈
  창구는 1.1 부터 받기만 하고, 필요 단축 일정 머리말은 Guide 첫 단락으로 — 6-11 d1 · g03), `tests/test_page_header_description.py`
  가 호출 자리를 맞댄다(2026-11-07 답 head-desc). `render_page_header_with_status` 는 진행
  표시 자리(`STATUS_SLOT_KEY` 안 `st.empty()`)를
  돌려주고, 그 자리를 머리 띠에 고정하는 것은 `app_header` 의 CSS 다. 두 함수 모두 `trailing` 을 주면 제목 줄 끝 칸에
  그것을 그린다(지금은 쓰는 화면이 없다 — 설정 단추 · 도구 단추는 이 칸에 두지 않고 사이드바 팝업 상자다(`settings_box.py`,
  9장). HOME 주요 Case 칩은 2026-11-02, 가용설비 현황 「설정」 은 2026-11-03, 필요 단축 일정 「Qual 마감 계산기」 는 2026-11-09 에
  사이드바로 옮겼다 — `_render_title_row` 한 벌) — 제목과 끝 칸은 `st.columns` 다(가로 컨테이너는 `h1` 여백을 지운다 — 9장). 두 칸의 폭은
  비율이 아니라 글자 폭이다(`TITLE_ROW_KEY` 컨테이너 바로 밑 칸만 고르는 CSS). 화면에서는 제목이 숨어(흐름에서 빠진다) 끝
  칸만 오른쪽 끝에 선다. 제목이 보이는 인쇄에서는 한 줄에 안 들면 끝 칸이 통째로 제목 밑 오른쪽으로 내려가고 제목은 접히지
  않는다(비율로 나누면 사이드바를 편 800~900px 에서 제목이 접히고 칩 줄이 넘쳤다).
- `src/capa_simulation/components/equipment_master_tab.py` — 가용설비 현황 탭 ① 「설비 마스터」 본문(개편 B1-c·d — 옛 RawData
  폼을 대신한다). 맨 위 줄(표 고르기 `equipment_master_table_v1` — 라벨 줄 없이 곁 빈 캡션 풍선 `head_help` 가 표의 뜻과 공통 ·
  시나리오 · 배치 칸의 저장 자리를 말한다 · 「일정 없이 엶」 · 「저장 전 변경 n건」 · 「일정 잠김」 — 설비 시나리오 · 리비전 알약은
  사이드바 줄 · 머리 띠와 같은 값이라 두지 않는다, 2026-11-09 상단 띠 재고) → 알림 칸 →
  테두리 하나의 편집기 영역 `equipment_master_frame` 안 두 칸(key 가로 칸 `equipment_master_split` › 왼쪽 `equipment_master_left` 표 구획(따로 테두리 없음) 또는 작은 편집표 · 오른쪽
  `equipment_master_right` 칸막이 마운트 → 오른쪽 칸 고르기 `equipment_master_side_v1` 「호기 상세 · 새 호기 · 저장 전 변경 · 저장
  이력」(「새 호기」 는 설비 마스터를, 「저장 전 변경」 은 비가동 일정이라도 고치는 등급에만 — 열람은 「호기 상세 · 저장 이력」) → 본문 칸 `equipment_master_side_body`(고른 칸 — 패널·저장 구획·저장 이력 전부)). 두 고르기는 `persist_state="session"`
  이고 콜백이 값을 적으므로 `default=` 없이 위젯 앞에서 칸이 없을 때만 심는다
  (`required=True`). 받기 콜백이 오른쪽 칸을 바꿀 때는 그 칸을 바로 적지 않고 `_SIDE_NEXT_KEY` 에 두어 다음 고르기 **앞**에서
  적는다(진짜 콜백은 회차 맨 앞이라 같은 회차 — 시험 대역은 고르기 뒤 마운트에서 부르므로 위젯을 만든 뒤 적는 오류를 피한다).
  - **탭 진입**(`render_equipment_master` → `render_equipment_master_scope`): 페이지는 그 회차 재료(`MasterMaterials` — DB 자리 ·
    저장소 · 세션(합친 스냅숏) · 캔버스 · 배치 편집 권한 · 오늘 · 확인용 공식 스냅숏)를 스레드 칸으로 넘기고 자리(`_MasterPlace` —
    DB 자리 · 스냅숏과 한 회차 알림을 뺀 세션 · 두 스냅숏의 (공통 대장, 일정) 리비전 id 쌍, 세션 칸 `equipment_master_place_v1`)를
    적는다. 탭 본문은 작은 인자(한 번만 쓰는 `drafts_replaced`)만 받고, 넘긴 재료가 없는 회차(탭 본문만 다시 도는 회차)는 그
    자리로 캐시에서 같은 재료를 다시 세운다(`_rebuilt_materials` — 리비전 내용은 불변이라 쌍 id 캐시, 캔버스 · 배치 편집 권한 ·
    오늘은 지금 값). 다시 세우기는 세션을 옮기거나 편집본을 세우지 않는다 — 그 일은 페이지 회차의 `resolve_equipment_session` ·
    `ensure_equipment_drafts` 몫이다. 탭 밖이 본 값과 견줄 재료는 둘이다 — 저장 토큰 `saved_pair_token`((공통 대장 최신, 세션
    설비 시나리오의 최신 일정) 리비전 — 쓰기 세대 · DB stat 을 키로 둔 캐시라 바뀐 것이 없으면 DB 를 열지 않는다)과 머리 표지
    `master_head`(미저장 편집 · FAB 배치 대기 · 작은 편집표 적용 전 편집 · 편집본 출발점 · 저장본 사본 리비전 · 팝업 열림 칸 ·
    찍힌 배치 역할 · 세션이 든 설비 시나리오 쌍 · 제 저장의 뒷정리 대기 `own_save_unsettled`). 시험
    `tests/test_equipment_master_scope.py`.
  - **편집기 구역**(9장 「구역 회차 규칙」 — `MASTER_SCOPE` `equipment_master_scope`): 탭 본문은
    `@fragment_scope.fragment(MASTER_SCOPE)` · `@grade_ui.in_fragment` · `_pinned_in_scope`(구역 회차만 설비 DB 핀 — 저장 토큰 읽기와
    본문이 한 핀) · `@fragment_scope.editor_scope(head=master_head, token=_scope_token, one_shot=("drafts_replaced",))` 로
    감싼다. 칸 고치기 · 「새 호기」 초안 · 불러오기(설비명 · 공정 · 조건 · 일정 확인 · 전체) · 「목록 비우기」 · 목록에서 빼기 ·
    줄 열기 · 가져오기 · 「한 단계 되돌리기」 · 표 고르기 · 오른쪽 칸 고르기 · 작은 편집표 칸 · 변경 메모 · 저장자는 이 구역만
    돌고 사이드바 · 머리 띠 · 다른 탭은 돌지 않는다(표 칸 정렬 · 칸 묶음은 브라우저 몫이라 서버 회차가 없다). 표 고르기 ·
    오른쪽 칸 · 상태와 상관없이 이벤트 칸에 같은 수의 자리를 쓴다(R5 — 작은 편집표 몫 `SMALL_EDITOR_EVENT_SLOTS` · 저장 구획
    몫 `SAVE_SECTION_EVENT_SLOTS` 를 그리지 않는 갈래는 빈 서식으로 채운다 `_fill_event_slots`, 시험이 열두 갈래를 맞댄다). 앱
    전체로 오르는 자리는 셋이다 — ① 받기 콜백 · 「한 단계 되돌리기」 는 끝에서 머리 표지(`master_head`)가 바뀌었으면
    올린다(`fragment_scope.escalates` — 깨끗한 편집본의 첫 칸 · 저장본으로 돌아온 칸 · 끊긴 제 저장 뒤 칸은 그
    상호작용이 앱 전체 회차가 되어 ack 가 그 회차에 실린다). 작은 편집표 칸도 적용 전 편집이 서거나 걷히면 편집표
    `on_change` 끝에서 올린다(`render_small_editor(rise=…)` — 편집표는 떠나기 명부 밖이라 탭 줄 붙들기가 새 data 를
    0.4초만 기다려, 본문 뒤에서 올리면 구역 회차가 그보다 길 때 그 뒤 앱 전체 회차와의 틈에 놓인다 — 9장 R8. 같은 요청에
    그 표의 작업 줄 · 삭제 확인 단추 누름이 실리면 콜백 끝 올리기가 그 누름을 버리므로 올리지 않고 ③ 이 올린다),
    ② 「리비전 저장」 · 「모두 버리기」 · 「엑셀·CSV로 한꺼번에」
    팝업 열기(메뉴 · 첫 화면) · 「최신 rN 불러오기(변경 버림)」(옮겼을 때 — `equipment_scenario_status._load_latest`)는 하는
    일이 탭 밖(페이지가 세우는 세션 · 편집본, 팝업 호스트)에 닿아 콜백 끝에서 늘 올린다(`_to_app_run` — `on_press` 위),
    ③ 본문 뒤 — 남의 저장(저장 토큰이 다름 — R4), 본문이 바꾼 표지(미룬 출납 · 제 저장 뒤 다시 얹은 칸 · 단추 누름과 한
    요청에 실린 작은 편집표 칸). 구역 회차는 페이지 끝의
    `rerun_if_head_stale` 을 지나지 않는다 — 본문이 단 표지는 머리 표지가 바뀌어 올라간 다음 앱 전체 회차의 편집본
    세우기가 거둔다. 저장 토큰(`_scope_token`)은 앱 전체 회차면 페이지가 편집본을 세운 쌍(`_seen_pair_token` — 자리의 공통 대장
    리비전 · 그 회차 목록의 최신 일정 리비전), 구역 회차면 지금 값(`saved_pair_token`)이다. 남의 저장을 본 구역 회차의 작은
    편집표 제출은 거절한다(`_drafts_outdated` — 한 번만 쓰는 `drafts_replaced` 가 꺼진 구역 회차에서 다시 판정한다, 제 저장의
    뒷정리 대기는 빼고). 시험 `tests/test_equipment_master_scope_runs.py`(fragment_browser 대역 · 진짜 상태 값 · 트리거).
  - **오른쪽 칸 폭·접기·높이 상한**(2026-11-02 사용자 결정 — 「늘이고 줄이거나, 최소화」 · 「너비에 한계를 두고 … 스크롤」, 2026-11-05 검수 —
    편집기 영역 안의 서브페이지 · 접기 단추는 칸 머리 · 접으면 떠 있는 단추):
    두 칸 경계선(왼쪽 감싸개의 오른쪽 테두리 — 줄 높이로 늘어 영역 끝까지 간다) 위 칸막이(`side_panel.render_side_splitter` — 작은 별도 등록)를 끌어 폭을 바꾸고(두 번 누르면 처음
    폭, 키보드 ←·→ 16px · Shift 64px · Home 최대 · End 최소 · Enter 접기), 칸 머리 오른쪽 끝 › 로 접으면 칸 자리가 0 이 되어 표가 줄을 다 쓰고 옛 Space 미배치 서랍 탭과 같은 생김의 단추(지금 칸 이름)가 영역 오른쪽 위에서 8px 들어앉아
    떠 있다 — 누르면 편다. 단추는 페이지를 내려도 붙어 있고(표 머리 위 · 고르는 칸 · 목록 아래 — 글 편집 칸은 머리 밑이라 단추 밑) 접은 동안 표 위 작업 줄이 그 자리를 비운다(`SIDE_REOPEN_RESERVE_PX`). 폭 한계는 `clamp(min(360px, 40%), 저장 폭 또는 30% − 28px, min(760px, 60%, 100% − 239px))`(영역 안 줄 1,137px 에서 360~682, 처음
    360 — 최소는 칸 머리 한 줄 + 칸막이 곁 여백, 239 는 왼쪽 안쪽 224 + 여백 14 + 경계선 1)이고 창 폭이 바뀌어도 페이지 CSS 가 JS 없이 지킨다. 본문 칸은 `max(360px, 100vh − 붙는 높이 − 200px)`(붙는 높이 = 화면
    탭 줄이 붙었을 때의 아래 끝 + 8px, 1.63 에서 97px — 950 창 653px · 800 창 503px) 안에서 스크롤하고(`overflow-y: auto` — 페이지를 늘리지 않는다, 스크롤 막대 자리는 영역 안쪽 여백으로 내보내 내용 끝이 머리 단추와 맞는다), 오른쪽
    칸은 그 높이에 붙고(sticky) 내용이 짧아도 머리 + 상한만큼 높이를 잡는다(칸을 바꿔도 영역이 뛰지 않고 칸막이를 잡을 자리가 있다). 접어도 패널은 `display:none` 으로 그대로 그려 두어 다시 마운트되지 않고 보내지 않은 출납을
    잃지 않는다. 폭·접힘은 브라우저에만 둔다(9장 「브라우저 전용 보기 상태」). 받기 콜백이 오른쪽 칸을 열면(`_switch_side` —
    표 설비명·첫 화면 「+ 새 호기」·가져오기·「호기 추가」·저장 전 변경의 고칠 것 줄) 연 수 `SIDE_REVEAL_KEY` 를 올려 칸막이 data
    `reveal` 로 보내고, 칸막이는 그 수가 오르면 접힌 칸을 펴고 본문 칸을 맨 위로 올린다(누른 것이 보이게 — 본문 칸은 key 칸이라
    다른 호기를 그려도 스크롤 자리가 남아 새 호기 이름 머리가 칸 위로 나가 있었다). 칸 안 너비 560px 이상이면 상세·새 호기 칸
    묶음이 3열(`grid.css` container query)이다. 「저장 전 변경」 목록 `max-height 420px`(본문 칸 안 겹 스크롤)은 그대로 둔다.
    창 폭 640px 이하는 위아래로 쌓고(칸막이·접기 없음) 인쇄는 상한·sticky 를 풀고 접힘도 펼친 꼴이다. Streamlit 1.63 DOM
    (`stLayoutWrapper` 감싸개 · key 가로 칸 `overflow`)에 기대므로 Streamlit 을 올리면 이 CSS(`side_layout_style`)를 다시 본다.
  - **새 호기**(개편 단계 C): 오른쪽 「새 호기」 칸은 세션 초안(`NEW_UNIT_DRAFT_KEY` — {번호, 39칸 글}, 저장해도
    남는다)을 그 회차 편집본 위에서 `new_unit_check` 로 보고 그린다(합성 3천 대 한 번 약 0.05 s — 샘플 관측, 칸 결과처럼
    메모하지 않는다). 브라우저는 칸을 확정할 때마다 번호를 올려 초안을 모아 두기만 하고, 칸을 떠날 때 · 쉼(`SEND_MS`) 뒤 ·
    「호기 추가」 직전 · 표 밖 · 창 숨김 · 내릴 때 마지막 초안 하나를 상태 값 `draft` 로 보낸다(「양식 비우기」 는 곧바로 — 2026-11-20
    사용자 결정 Q4, 체크 상자 · 칸 오류는 그 회차에 선다). 「호기 추가」 는 모아 둔 초안을 먼저 보내고 그 마지막 초안을 실은 `add`
    op 를 보내며 파이썬이 그 초안으로 다시 판정해 넣는다. 받기 콜백은 번호가 세션 초안보다 작지 않을 때만 적는다. 출납을 얹을 때 세션 초안 번호를 `GridState.draft_seq` 로 넘긴다(옛 번호의 `add` 는 서비스가 버림). 「호기
    추가」(`add` op) 뒤에는 마지막 호기를 「호기 상세」 로 열며, 초안은 번호를 올려 공정소분류·동·층만 남긴다. 막히면 받은 초안을
    세션 초안으로 둔다 — 세션 초안보다 번호가 작은 `add`(버린 두 번 누름)는 보지 않는다(다음 회차에 따로 온 둘째 누름이 넣은 뒤
    초안을 옛 초안으로 덮지 않게). 호기마다의 함께 넣기 고름은 없다(2026-11-05 사용자 답 — 옛 체크 · 경고를 걷었다): 새 호기는 어느 길로
    들든 저장 때 다른 설비 시나리오에 함께 넣고 결과 알림이 대수를 적는다. 옛 세션의 초안 · `add` op · 고름 칸(`propagate` · `equipment_new_unit_propagate_v1`)은 읽지 않는다. 가져오기(`copy` 트리거 — 상세 「이 호기로 새 호기 만들기」 는 빈 초안에,
    「비슷한 호기에서 값 가져오기」 는 브라우저 초안 위에)와 첫 화면 「+ 새 호기」(`new`)가 이 칸을 연다(불러오기 줄에는 두지 않는다 — 칸 고르기 「새 호기」 와 같은 일이다). 가정 설비 시나리오면 칸
    위에 새 호기 자리 안내(공식 배치에는 자리 없이 — Q1)를 싣는다. 지우기 결과는 알림창 값 한 줄(`_delete_toast` — 저장본 호기 「n대 지울 목록에 넣음」, 지울 목록에 들지 않고 바로 빠지는 새 호기
    「새 호기 n대 뺌」, 섞이면 둘을 「 · 」 로 잇는다 — 되돌리기는 「저장 전 변경」 의 「한 단계 되돌리기」)이고
    저장해야 지워진다 · 모든 설비 시나리오에서 빠진다는 말은 지우기 단추 풍선(`DELETE_TIP`, UI-NTF-09)과 Guide 다.
  - **CCv2 마운트 앞의 자리는 고정한다** — 낡음 경고·잠금 줄·이름 바꿈 목록·비활성 층 경고는 늘 서 있는 칸 안, 알약 「저장 전
    변경」 도 늘 서 있는 칸 안이다(순번이 밀리면 표가 다시 마운트되어 보내지 않은 출납·고름을 잃는다 — 9장).
  - 한 회차에 표 모양(`build_view` → `equipment_grid.build_grid_view`)을 한 번 내고 세 마운트 data 를 그것에서 낸다. 칸 결과
    (`equipment_master_issues` — 저장과 같은 인자: 캔버스·오늘)는 편집본 세대·`buffer_base`·오늘·캔버스 열쇠로 세션 메모
    (`GRID_MEMO_KEY`, 결과는 튜플로 풂 — 다음 칸 고치기의 재료 `issue_state` 는 아래)에 한 번. 표 글자(`text_matrix` — 편집본은 편집본 세대·`buffer_base`, 저장본은 저장본 사본 토큰
    열쇠 → `GridSource.texts`)와 메뉴 「엑셀·CSV」 현재 데이터 바이트(`_render_current_data_downloads(memo_keys=)` — 표마다)도 같은 메모 칸이다 —
    고친 편집본이 있는 세션의 바뀐 것 없는 회차가 3천 대 × 39칸 글자·직렬화를 다시 내지 않는다(개편 명세 8장 「payload 메모」).
    편집본 열쇠가 바뀐 회차(칸 고치기)도 처음부터 내지 않는다 — 칸 결과(`_issues`)는 같은 메모 칸의 재료(`issue_state` —
    `equipment_validation.MasterIssueState`)에서 바뀐 칸 · 그 칸을 보는 규칙만 다시 보고(`equipment_master_issues_since` — 결과 차례
    규칙 → 칸 → 줄 그대로), 편집본 글자 행렬(`_texts`)은 직전 행렬(`buffer_texts_matrix` — `equipment_grid.TextMatrix`)에서 바뀐 칸 ·
    줄만 갈아 끼운다(`text_matrix_since`, 저장본 행렬은 그대로). 「리비전 저장」 판정(`_blocking_count`)은 메모를 거치지 않고 늘
    처음부터 본다 — 저장이 막힌다 ⇔ 막는 결과. **표별 세대**(`table_generations` — 편집본 세 표마다 그 표를 바꿀 수 있는 쓰기에서만
    오른다, 층 배치 대기분은 세 표 밖이라 오르지 않는다)로 한 표만 보는 일을 그 표 열쇠(`_table_key` — 그 표 세대 · 출발점 · 저장본
    사본 쌍 토큰)에 둔다: 표 단위 오류 앞 셋(기존 보유대수 둘 — 그 표 열쇠, 비가동 일정 정규화 — 그 표 열쇠 + 설비 마스터 설비명),
    다른 두 표의 바뀐 행 수, 메뉴 「엑셀·CSV」 현재 데이터 바이트(표마다 `memo_keys`) — 설비 마스터 칸 하나를 고친 회차는 다른 두
    표의 일을 다시 하지 않는다. 양식 바이트도 회차 메모에 한 번이다. 일정 확인 갈래 글(`_alerts`)은 판정 칸(설비명 · 단계 일정 ·
    실적 · 상태 — `CONFIRMATION_INPUT_COLUMNS`)을 앞 회차 재료와 줄마다 견주어(`equipment_grid.changed_positions`) 바뀐 줄만 다시
    판정한다(`schedule_confirmation.row_confirmation_words` — 통째 목록과 같은 판정, 날짜 칸이 날짜 형이 아니면 통째로 —
    `rowwise_confirmation`, 출발점 · 저장본 토큰 · 오늘이 바뀌거나 줄 수가 바뀌면 처음부터). 모두 같은 회차 메모(창구 `GRID_MEMO`,
    `_remembered` — 짓는 사이 적힌 칸을 덮지 않는다)다. 묶음 바둑판 · 가정 묶음 거부 · 낡은 세션의 지운 호기 · 층 배치 · FAB
    대기분은 편집본 밖 칸을 보아 회차마다 보고, 표 모양(`build_grid_view`)은 맥락 전체가 입력이되 「바뀐 칸」 은 편집본 · 저장본 글
    줄이 그대로인 줄의 앞 회차 것을 쓴다(`GridSource.changed_memo` — 출발점 · 저장본 토큰 열쇠로 회차 메모 `changed_rows`). 메모의 재료 두 벌(`MasterIssueState` · `TextMatrix`)은 DataFrame 사본을 든 인스턴스라 「모델 인스턴스를 세션에 두지
    않는다」 관례 밖이다 — 핫리로드 뒤에는 꼴이 달라 처음부터 보고, 기본형으로 풀지는 `docs/TODO.md` 2장 「성능」 결정 거리다.
    편집본을 이 두 함수(`replace_equipment_buffer`·`apply_master_grid_result`) 밖에서 세대를 올리지 않고 바꾸면 메모가 옛 글자를
    그린다 — 시험도 `BUFFER_GENERATION_KEY` 를 함께 올린다. 미저장 표시(머리 변경 칩·사이드바 「미저장 변경」·머리 띠·탭 점·떠나기 확인 — 모두 `has_unsaved_equipment_edits`)는
    「편집본 세대 > 세운 세대」 이되 저장본으로 돌아온 세대(`_CLEAN_GENERATION_KEY`)는 뺀다 — 넣었다 지운 새 호기·되돌린 칸·다 되살린 호기는 세대만 올랐지 저장할 것이 없다(2026-11-06).
    편집본·층 대기분을 바꾼 길(표 출납·`_remember_edits`·`_store_changed_buffer`·`stage_floor_*`·`discard_layout_edits`)이 끝에 `_note_if_back_to_saved` 를 부르고, 세 표가 저장본 사본과 내용까지 같고
    이름 바꿈·칸 초안·층 대기분이 없을 때만 그 세대를 적는다. 세운 세대를 옮기지 않는다 — `buffer_base` 라 옮기면 표시가 걷히기 전에 보낸 op(「새 호기 뺌」 바로 뒤 「되돌리기」)가 버려진다.
    `tests/test_equipment_unsaved_mark.py`. 표 단위로 막는 것(기존 보유대수·비가동 일정 검증·예시 행·모듈 바둑판·가정 묶음 거부·
    낡은 세션의 지운 호기·낡기 전에 고친 시나리오 칸 — `stale_scenario_edit_spots`, 칸을 되돌리면 공통 칸은 저장된다)은 「저장하기 전에
    고칠 것」 줄이다. 낡은 세션의 두 줄은 버려질 호기·칸 이름을 앞 셋까지 적고(「버려질 칸: EQ-01 반입일정·Qual일정, … 외 n대」),
    세 저장 자리(탭 저장 구획·팝업 「저장」·Space 저장 오류 곁)에 「최신 rN 불러오기(변경 버림)」 단추가 선다
    (`equipment_scenario_status.render_load_latest_button` — 팝업 「불러오기」 와 같은 `select_equipment_scenario`, 공통 칸 편집도
    버린다고 풍선이 말한다. 팝업 안(`in_dialog`)은 콜백이 아니라 본문에서 옮기고 `st.rerun()` 으로 앱 전체를 다시 돌린다 —
    팝업은 조건 팝업 호스트 프래그먼트 안이라 콜백이면 그 프래그먼트만 다시 돌아 페이지가 낡은 세션 그대로 남는다). 낡은 세션의 뒤 둘은 세 저장 길이 한 판정(`equipment_data_workspace.stale_save_reasons`)을 쓴다 — 탭은 이
    고칠 것 줄로, 사이드바 팝업 「저장」 은 경고 글로(`stale_save_refusal`) 보이고, 저장은 `save_equipment_buffer` 의 설비 쪽
    저장 전 검사(`_save_equipment_frames` 첫머리 — FAB 전체 배치 대기분은 별도 쓰기라 그 앞에서 저장되고 거부 글이 함께
    말한다)가 같은 글로 막는다(Space 「배치 저장」 도 — 저장소의 「다른 사용자가 먼저 …」 거부는 고칠 칸을 말하지 않고 다시
    불러오면 공통 편집까지 잃는다, `tests/test_equipment_save_preflight.py`).
  - **받기**: 표·오른쪽 칸 두 마운트의 출납을 `apply_outbox` 하나가 `pending_ops`(마운트별 seq 기억 `equipment_grid_applied_v1`)·
    `apply_ops`(그린 회차의 `GridContext` 를 콜백 인자로 묶는다)·`apply_master_grid_result` 로 반영하고, 결과 글은 알림창으로(`GRID_RESULT_KEY` —
    탭 끝 `render_flash(LOAD_RESULT_KEY, GRID_RESULT_KEY)` 칸이 꺼내 낸다), 각 마운트 data 에는 제 `ack` 를 싣는다. 배치·설비명·Main 설비 칸을 바꾼 op 와
    `official`·`undo`(되돌리기가 걷힌 배치 편집을 되살릴 수 있다 — 「한 단계 되돌리기」 단추도)·`add`(새 호기 자리는 배치 편집 —
    붙여넣기 새 행·엑셀·CSV 넣기와 같다) 뒤에만 배치 편집 판정(`buffer_has_layout_edits` 메모)으로 역할을 찍는다
    (`stamp_layout_role`). 트리거(불러오기·목록 비우기·열기·빼기·goto·팝업)는 목록·상세 id·표 고르기 칸만 적는다. 콜백 안에서
    `st.rerun()` 을 부르지 않는다. 브라우저는 base 가 바뀌어도 op 를 빼지 않는다(`rebaseBox` — 목록 표와 같은 한 길). 칸을
    연 채 base 가 바뀌면 친 글도 옛 base op 로 보낸다(`queueOpenEdit`). 저장 · 모두 버리기 콜백이 편집본을 비운 틈에 온 출납은
    `apply_outbox` 가 건드리지 않고 `OUTBOX_HELD_KEY` 를 남기며, 편집본을 다시 세운 `render_equipment_master_tab` 이 세어
    알린다(다시 세우는 길이 결과 알림 칸을 비우므로). 같은 틈의 한 단계 되돌리기 · 불러오기 · 가져오기는 넘긴다.
  - **제 저장 이음**(rerun-1120 바탕 결함 c6 — 「리비전 저장」 직후 친 칸이 버려지고, 바쁜 서버에서는 제 저장을 「다른 사용자가 …
    저장해 … 버렸습니다」 로 알렸다): 「리비전 저장」 콜백은 DB 쓰기 **전에** 이음 표지(`OWN_SAVE_CARRY_KEY` — 그 편집본 출발점 ·
    저장 뒤 행 id 지도 `save_id_map` · 마운트별 저장에 든 seq)를 적고, 쓰기는 `_save_equipment_frames` 가 그 dict 에만 적는다(뒤
    세션 칸 접근은 fastReruns 에 끊길 수 있다). 쓰지 않았으면 콜백 끝이 걷는다(`settle_own_save_carry`). 그 편집본을 쓰는
    중이거나(`writing` — 저장소 쓰기가 도는 동안만, 썼으면 `written` 을 먼저 적고 걷는다) 이미 쓴(`written`) 표지는 같은
    출발점의 둘째 「리비전 저장」 누름이 새로 적지 않는다 — 둘째 누름은 첫 저장의 결과를 잇기만 하므로(`write_guard.save_once` ·
    제 저장 짝) 덮어쓰면 그 사이 친 칸이 「저장에 든 seq」 로 걸러져 사라진다(첫 쓰기가 도는 중에 다른 스레드로 선 누름도, 쓰기
    뒤 끊긴 뒤의 누름도). 뒷정리 전에 끊긴
    회차(`own_save_unsettled` — 그 출발점 그대로이거나 새 일정 리비전으로 세션을 옮길 회차가 남음)의 출납은 seq 를 적기 **전에**
    미루고, 끊긴 제 저장은 알림 창이 지나도 이음 표지로 알아본다(`_settle_own_save`). 제 저장 뒤 다시 세운 편집본(세션을 옮겨 한 번
    더 다시 세운 것도)에 이음 표지가 이어지고(`_bind_own_save_carry`), 그 전 출발점의 op 는 행 id 를 저장 뒤 id 로 옮겨(지운 호기를
    가리키면 버림) 지금 `base` 로 얹는다(`_carried` · `equipment_grid.moved_op` — 저장에 든 seq 이하는 빼 넣기 · 붙여넣기가 두 번 들지
    않는다). Streamlit 1.63 은 저장 콜백이 쓰는 사이 닿은 출납의 회차를 다른 스레드로 세워 그 op 를 곧 버려질 옛 편집본에 얹고
    ack 를 그린다 — 받기가 이음 표지를 적은 편집본에 얹는 op 를 그 dict 에 남기고(`note_late_ops`), 이음 표지를 이은 회차의 탭이
    한 번 꺼내 다시 얹는다(`take_late_ops` — 남기는 창은 표지를 적고 `LATE_OPS_WINDOW_SECONDS` 60초, 쓰기 전에 끊겨 이어지지
    않는 표지에 끝없이 쌓지 않게). 끊긴 저장이 새 일정 리비전을 써 세션을 옮기며 한 번 더 다시 세울 회차(`own_save_unsettled`)에는
    꺼내지 않고 옮긴 뒤의 편집본에서 꺼낸다(옮기기 전 편집본에 얹으면 그 다시 세움이 지운다). 그 옮기기 전 편집본은 저장 본
    값(`_BASE_KEY`)을 남기지 않는다 — 일정만 쓴 저장이면 그 본 값이 저장 전 짝 그대로라 다음 회차의 `_settle_own_save` 가 같은
    저장을 한 번 더 이어 뒷정리하며 이음 표지를 걷는다(그 편집본은 저장하지 않는다). 탭 본문에서 얹은 출납(미뤄 둔 것 · 다시
    얹은 것)이 미저장 표시를 바꾸면 페이지 끝에서 한 번 다시 돌아 머리 띠 칩 · 탭 점 · 떠나기 확인을 맞춘다(`head_stale_if_unsaved_changed` → `rerun_if_head_stale`). 그 밖의 다시 세움(모두 버리기 · 불러오기 · 세션 옮김 — `reset_equipment_drafts` 가 걷는다, 남의 저장 — 걷고 그 옛
    출발점을 `FOREIGN_ORIGINS_KEY` 에 적는다)에는 얹지 않고, 버린 op 는 까닭대로 센다(`FOREIGN_DROPPED_TOAST` · `DROPPED_TOAST`).
    `tests/test_equipment_master_save_race.py`.
  - **오른쪽 칸 자리 거부 한 줄은 실어 보낸 마운트가 사라지면 거둔다**(`settle_grid_toasts` — 대상은 `detail` · `new` 뿐, 탭 끝에
    그린 마운트 이름으로, 탭이 숨은 회차에는 빈 것으로 부른다). 브라우저의 닫은 번호는 마운트마다 새로 시작해 표 고르기·탭·오른쪽 칸
    왕복에 닫은 한 줄이 되살아났다. 아직 실어 보내지 않은 한 줄(숨은 동안 쌓인 것)은 처음 마운트할 때 보인다(실어 보낸 번호
    `GRID_TOAST_SHOWN_KEY`).
  - 불러오기 · 목록 비우기 결과는 표 안 띠가 아니라 알림창이고(`LOAD_RESULT_KEY`, `render_flash` 칸은 탭 맨 끝 — 편집기 영역 자리를 지킨다), 고른 줄 띠는 고르는 동안
    표 위 작업 줄(불러오기 줄 · 메뉴 「엑셀·CSV」) 자리에 같은 높이로 대신 서는 흐름 밖 막대다(`.emg-sel` absolute, 자리는 `placeBand`
    가 불러오기 칸 `loaderKey` 에서 잰다 — ResizeObserver, 고르는 동안 `<html data-emg-sel>` 로 `tools_menu_style` 이 그 줄을
    visibility 로 숨기되 자리는 남긴다 — 상속 변수 `--emd-sel-hide`, 설계 규칙 UI-PRF-03, 2026-11-08 그림 메모 g01 (가)). 띠에는
    「선택 n대 · 값 넣기 ▾ · 일정 밀기 ▾ · 선택 n대 지우기 · 선택 풀기」 를 두고 값 넣기 · 일정 밀기는 팝업(`popover(…, 'bulk')` —
    `bulkSetPanel` · `bulkShiftPanel`, 넣거나 밀면 닫힌다)이다. 표 브라우저 한 줄(`emg-note is-float`)은 볼 칸 줄 위에 떠 표를
    밀지 않는다. Tab · ↓ 로 연 칸은 나가는 칸의 글자 자리를 넘겨받지 않는다(`keptCaret` — 옛 값 통째 고름, 답 X1). 호기 상세의
    확정 안 한 글도 base 가 바뀌면 옛 base op 로 보낸다(`queueOpenDrafts` — 작은 결정 c4). 잠긴 단추는 `tipWrap` · `lockButton` 으로
    감싼 칸이 까닭 풍선을 맡고 다 불러온 「전체 n대 불러오기」 는 잠근다.
  - **저장 구획**(「저장 전 변경」 아래): 변경 메모(옛 `_NOTE_KEY` — 저장 성공의 비움 표지 그대로)·저장자 칸·옛 배포 흔적 줄
    (어디로 저장되나는 「리비전 저장」 풍선 `save_button_help`, 체크 · 확인 칸은 없다)·「한 단계 되돌리기」(잠그지 않고 누른 회차에 판정한다 — 단계 수는 서버 값이고 출납을 묶어 보내므로 회차 값이 브라우저보다 늦다, `undo` op — 더블클릭은 한 단계다. 그린 회차의 누름 세대 `UNDO_PRESS_KEY` 를 콜백 인자로
    받아 지금 세대와 다르면(첫 회차가 단추를 다시 그리기 전의 옛 화면) 거르고, 다시 그린 단추에 닿은 둘째 누름은 첫 되돌리기의
    `TRAILING_PRESS_SECONDS` 창 안이면(`write_guard.note_written`·`just_written`) 거른다 — 거른 누름은 되돌리지도 알리지도
    않는다. 세대·시각은 되돌리기 전에 적는다)·「모두 버리기」(확인 팝오버 — `reset_equipment_drafts(keep_fab=True)`)·
    「리비전 저장」. 「리비전 저장」 은 **잠그지 않는다**(출납은 묶어 보낸다 — 마지막 회차의 판정은 브라우저보다 늦다): 콜백이 그린
    회차의 `base` 가 지금과 다르면(저장 뒤 옛 누름) 아무것도 하지 않고, 출납을 먼저 반영한 뒤 오류 수(칸 결과·초안·표 단위)·
    바뀐 것 없음을 판정해 단추 아래 한 줄로 알린다. 저장 전에 「지금 id → 저장 뒤 id」 지도(`save_id_map`)를 만들어 성공하면 목록·
    상세 id 를 옮긴다.
  - 가정 설비 시나리오 편집 회차(`layout == "overlay"`)면 `GridContext.official_places`(`_official_places_by_name` — 공식과 다른
    호기의 공식 일곱 칸)를 넘겨 호기 상세 위치 묶음에 「공식: …」 한 줄과 「공식 자리로 되돌리기」(`official` op — 모듈이면 묶음
    통째)를 세운다(설비 시나리오 2단계 설계 13-1). 되돌리기는 **공식 원래 값**(`GridContext.official_cells` —
    `official_layout_cells`, 공식 스냅샷의 그 호기 칸 그대로)을 적는다 — `official_places` 는 견줄 꼴(`CANVAS_DECIMALS` 반올림)이라
    그대로 적으면 공식 좌표 12.25 가 12.2 로 들어가 모듈 묶음 바둑판이 어긋나 저장이 막힌다. 원래 값이 견줄 꼴과 맞지 않으면(낡은
    세션 등) 견줄 꼴을 적는다. 공식 층이 다른 호기를 한 묶음으로 묶는 고침의 「저장하기 전에 고칠 것」 줄은 `official_places` 가
    비어도(배치 차이가 없는 가정 시나리오) 판정한다.
  - **불러오기 줄 끝 메뉴 「엑셀·CSV」**(`_render_data_menu`): 표 위 작업 단추는 한 줄이다 — 찾기 칸 · 「공정별」 · 「조건별」 · 「일정 확인 n대」 · 메뉴(줄인 말의 원래 뜻은 풍선 · 패널 접근성 이름). 메뉴는 맨 위 「엑셀·CSV로 한꺼번에」(팝업) + 양식 셋 + 현재 데이터 셋(`_render_current_data_downloads`)이고 내려받기가 파이썬 위젯이라 Streamlit 팝오버로 남았다.
    그림자 DOM 불러오기와 한 flex 줄에 넣지 못해 메뉴 칸(`TOOLS_KEY`)을 왼쪽 칸 기준 절대 위치로 띄우고(흐름 높이 0, 불러오기 **뒤** 차례 — 키보드 차례는 불러오기 줄 → 값 줄 다음이 메뉴) 불러오기 줄 `.emg-lb` 만 CSS 변수 `--emd-tools-reserve` 로 비운다(`tools_menu_style` — 값 줄 · 빈 안내는 폭을 그대로 쓴다). 폭은 팝오버 `width` 로 고정이라 글꼴과 무관하고, 접은 동안은 떠 있는 단추 자리(`SIDE_REOPEN_RESERVE_PX`)만큼 더 비운다. 단추 셋(`.emg-lb-picks`)은 한 덩이로 줄을 바꿔 찾기 칸 곁에 낱개로 남지 않는다. 왼쪽 칸이 찾기 칸 한 줄(`SEARCH_LINE_PX` 300) + 메뉴 자리보다 좁으면 메뉴가 찾기 칸을 누르지 않게 불러오기 줄이 `--emd-tools-drop` 만큼 내려가 메뉴가 같은 자리에 혼자 서고(`data-lb="stack"`), 300 보다도 좁으면 「불러오기」 가 입력 칸 아래로 내려간다(`tight`). 고르는 쪽은 불러오기 JS 의 `ResizeObserver`(`loaderFit` · `watchLoaderFit` — 파이썬 회차 없음, UI-PRF-04)이고 표지는 그림자 안 마운트의 `data-lb` 라 `<html>` 을 건드리지 않는다. `container-type` 은 쌓임 문맥 · fixed 기준이 바뀌어 쓰지 않는다. 입력 칸 180px 가 들도록 오른쪽 칸 최대가 왼쪽 안쪽 224px 를 남긴다(`side_panel.SIDE_LEFT_MIN_PX`, 두 편집기 공통 — 줄이 아주 좁으면 오른쪽 칸 최소가 이긴다). 메뉴 단추는 곁 `.emg-btn` 과 같은 사이 6px · 양옆 13px · 초점 표시이고(`tools_menu_style`, 폭 `TOOLS_MENU_WIDTH_PX`) 한 줄에 다 드는 것은 창 1363 부터다(오른쪽 칸 처음 폭 · 사이드바 열림) — 그 구간 입력 칸은 102px 부터고 안 A 의 한 줄이 먼저다. Streamlit 1.63 DOM(`stLayoutWrapper` · `stPopoverButton` · 그 안 첫 `div`)에 기대므로 올리면 다시 본다.
    「엑셀·CSV로 한꺼번에」 는 팝오버 세대(`DATA_MENU_GENERATION_KEY`)를 올려 메뉴를 닫은 채 다시 세운다(`on_change` 로 여닫힘을 받으면 메뉴를 열 때마다 회차가 돈다). 팝업이 닫힌 회차(`dialogClosed`)에 메뉴로 연 팝업이면(`dialogFromMenu`) 초점을 메뉴 단추로, 첫 화면 단추로 열었으면 그 단추(넣어서 사라졌으면 메뉴 단추)로 돌린다 — 표 컴포넌트가 `menuKey` 로 그림자 DOM 밖 단추를 찾는다. 저장된 데이터가 없는 첫 화면에는 「엑셀·CSV로 한꺼번에」 · 「+ 새 호기」 단추가 남는다.
- `src/capa_simulation/components/equipment_import_dialog.py` — 가용설비 현황 「엑셀·CSV로 한꺼번에」 팝업(옛 입력 탭을 옮김, 개편
  명세 4-8). 열림 값 `import`(「가용설비 설정」 과 한 열림 칸·한 호스트 — `render_equipment_dialog_host(import_dialog=)`), 여는 콜백은
  `forget_page_dialogs()` 부터. 미리보기는 옛 입력 탭 그대로(`build_import_review` + 낡은 세션 거절 + 배치 잠금·가정 묶음 거절 +
  CSV 시나리오 주의, 가정 세션 「배치 칸도 붙여넣기」 기본 끔 — Q2) — 머리 「바뀔 행」·「기존 대체」 와 넣기 토스트의 행 수는 넣으면
  실제로 바뀌는 줄만 센다(`equipment_csv.import_preview_changed_rows` — 같은 값 그대로인 대체 줄은 「변경 없음」). 끝 단추는
  **「편집본에 넣기」 하나**(D7 — 사용자 R4):
  `ImportReview.matches` 가 참이면 `apply_import_review` — 통째 되돌리기 단계(`whole_step`) 하나·`replace_equipment_buffer`·칸 초안
  비움·새로 든 설비명을 목록 맨 위로·결과 알림(`queue_grid_result`)·넣은 편집본에 배치 편집이 있으면 그때의 역할 찍기(`stamp_layout_role` —
  넣고 나중에 저장하므로 그 사이 역할이 바뀌면 저장소가 막는다, 설계 6-2) — 뒤 열림 칸을 지우고 앱을 다시 돌린다. 팝업을 닫으면
  (`_close_dialog` — on_dismiss) 미리보기도 거두고, 여는 콜백(`open_equipment_import` — 표 불러오기 줄 `dialog` 트리거도)도 남은
  미리보기를 거둔다(닫힌 회차에 입력 칸이 버려져 다시 열면 빈 입력에 옛 미리보기만 남는다). `_close_dialog` 는 닫힌 수
  (`IMPORT_CLOSED_KEY`)도 올린다 — 표 불러오기 data `dialogClosed` 로 실려, 그 불러오기 단추로 연 팝업이 닫힌 회차에 초점이
  아무 데도 없으면 여는 단추로 돌린다(Streamlit 은 그림자 DOM 안 단추로 돌려주지 못해 BODY 로 빠진다). 팝업 안 폼 제출은 앱 범위
  `st.rerun()` 이다(앱 회차에서 `scope="fragment"` 는 오류). 팝업 알림은 작은 편집표 알림 칸과 가른 제 칸(`IMPORT_*_KEY`)이고 모두
  알림창 · Alarm 으로 간다 — 연 회차의 맞대는 규칙(`IMPORT_OPENING`)·미리보기의 알림 · 주의(`_queue_review_alerts`)·거부
  (`popup_only`). 창 꼴은 공통 부품(9장 「붙여넣기 · 양식 창」)이고 작업 줄 오른쪽 양식은 고른 표의 것이다(`IMPORT_TEMPLATES` — 등록할
  표를 고르면 팝업이 다시 돌아 따라온다). 폼을 쓰지 않는다.
  새 방문 회차의 미리보기 거두기는 페이지가 매 회차 부르는 `withdraw_preview_on_new_visit`.
  「편집본에 넣기」 는 묶음 같이 쓰기(`plan_group_writes`)를 지나지 않는다 — 파일은 줄마다 값을 적는 길이라 적은 값 그대로 넣고 같은 Main 설비의 형제 줄에 퍼뜨리지 않는다(형제를 같이 바꾸는 길은 표 칸 · 호기 상세 · 붙여넣기 · 값 넣기 · Space 「호기 정보」 창이다).
- `src/capa_simulation/components/equipment_master_grid.py` (+ `equipment_master_grid_assets/` HTML·CSS·JS) — 가용설비 현황
  「설비 마스터」 탭 표(Components v2, 그림자 DOM, 개편 B1)의 등록·그리기·받기. 탭 본문(`equipment_master_tab`)이 부르고, 페이지는
  그 탭이 열린 회차에만 그 모듈을 불러온다 — 모듈을 읽을 때 등록한다(`test_benchmark_home.py`).
  상태 칸(반입상태 · Qual상태)은 색 배지가 아니라 다른 칸과 같은 글자로 그린다 — 배지를 두면 그 색이 상태색 토큰과 겹쳐 대비 시험이 늘어난다.
  - 한 등록을 세 자리에 다른 key 로 마운트한다 — 불러오기 `LOADER_KEY`·표 `GRID_KEY`·오른쪽 칸 `side_key(panel)`(호기 상세·새
    호기·저장 전 변경). key 가 정체라 data 가 바뀌어도 다시 마운트되지 않지만 앞 형제 순번이 밀리면 다시 마운트되어 보내지 않은 출납을
    잃는다 — 탭 본문은 마운트 앞의 생겼다 사라지는 칸을 늘 서 있는 칸 안에 둔다(9장 「key 가 있어도 자리는 고정한다」).
  - **오른쪽 칸 칸막이**(칸막이 · 칸 머리 접기 단추 · 접었을 때 떠 있는 단추)는 시나리오 목록 관리와 함께 쓰는 공용 부품이다(`components/side_panel.py` — 이 화면 스펙 `MASTER_SIDE`, 등록 `capa_side_splitter` · `side_panel_assets/splitter.js`·`splitter.css`,
    대역 `tests/conftest.py`). data 는 팔레트(`splitter_palette` — `--ess-*`)·지금 칸 이름·`reveal`·폭 한계
    (`side_bounds` — 페이지 CSS 와 같은 수)·두 칸·본문 칸 key·저장소 · `<html>` 표지 이름·화면 탭 줄 선택자뿐이라 거의 늘 같다. 상태 값·트리거가 없다 — 폭·접힘은
    브라우저 저장소 `capa-equipment-side-v1` `{w, min}`(try 안)과 `<html>` 의 CSS 변수 `--emd-side-w`·`--emd-top`·속성
    `data-emd-side="min"` 에만 둔다. 저장소 읽기·쓰기가 한 번이라도 막히면(사내 DRM 등) `<html>` 에 표(`__essLocalOnly`)를 달고 그 뒤
    마운트는 저장값 대신 `<html>` 에 걸린 이 문서의 폭·접힘을 그대로 둔다 — 안쪽 탭·화면을 옮겨 다시 마운트돼도 남고 새로 읽으면
    처음이다. 끌기는 rAF 로 한 프레임에 한 번(회차 0), 끌기 시작에서 `preventDefault`(글자 고름 없음).
    칸막이 마운트는 절대 위치(흐름 높이 0 — 경계선부터 칸 오른쪽 끝까지 덮고 눌림은 `pointer-events` 로 칸막이·단추만 받는다)라 오른쪽 칸 차례(칸막이 → 고르기 → 본문 칸)를 바꾸지 않는다. 배치 서식은 회차마다 같은 글의
    스타일만 든 `st.html` 하나(`side_layout_style` — 이벤트 칸 한 자리, 1,000B 이상이라 해시 참조, CSS 주석 없음)다 — 가로 칸
    flex 항목은 `stLayoutWrapper:has(> .st-key-…)` 한 겹으로 고르고(`:has` 를 겹치면 규칙이 버려진다), `wrap=False` 가로 칸에
    `overflow: visible` 을 건다(아니면 sticky 가 줄 기준으로 잡힌다). 순수 구획 `// <splitter-…>`(폭 식·끌기·키)와 마운트(가짜
    DOM)는 `tests/test_equipment_side_panel.py` 가 node 로 돌린다.
  - 등록 글은 표 공용 조각(`components/grid_shared.py` · `grid_shared_assets/` — 칸 상태 · 변경 칸 CSS, 칸 찾기 · 보낼 목록 · DOM 도우미 · 떠나기 신호 JS) 뒤에 이 표의 파일을 잇는다(`registered_js` · `registered_css`). 칸 상태 규칙은 특이도가 같아 차례로 이기므로 공용 조각을 앞에 둔다.
  - **표 마운트는 두 등록**(범용 편집 그리드와 같은 꼴 — CCv2 는 data 가 바뀐 회차마다 등록 JS · CSS 를 요소와 함께 다시
    보낸다): 표 요소 `_GRID`(껍데기 — 칸 하나를 고친 회차에도 앞 껍데기를 그대로 다시 내 해시 참조로 간다, 탭이 회차 메모
    `grid_shell` 에 둔다)와 바로 앞의 작은 요소 `_FEED`(`capa_equipment_master_grid_feed` · `feed.js` — key `feed_key()`, 페이지
    CSS 는 `tools_menu_style` 덩이에 든다)다. feed JS 는 `window.__capaEquipmentGrid[host].feed` 칸에 두고 `capa-equipment-grid`
    이벤트를 쏘며, 표 JS 는 그 껍데기 지문의 feed 만 이어 그린다(`takeShell` · `takeFeed` · `joinGridData` — 다른 껍데기의 feed 는
    기다림, 껍데기 · 바뀐 줄이 그대로인 feed 에는 정렬한 표 모양을 다시 짓지 않음, 내릴 때 칸의 feed 를 비움). 지문 없는 data 는
    예전처럼 바로 그린다. 칸 하나 고칠 때 받는 바이트는 합성 표본에서 약 471KB → 36KB 다(샘플 관측 — rr1120 B 측정).
    시험 대역(`tests/grid_fake.py`)은 두 요소를 받아 이은 data 를 표 key 로 적는다.
  - **묶어 보내기 쉼**은 파이썬 결정값 한 줄이다(`SEND_MS` 0.8초 → data `sendMs` — `grid_shared.batch_ms`, 브라우저
    `schedule`). 깨끗한 편집본(data `clean` — 표 feed · 호기 상세)의 첫 칸 고침은 쉼 없이 곧바로 가고(`sendsAtOnce`), 여러 칸
    붙여넣기 · 단추 op · 표 밖 누름 · 창 숨김도 곧바로다. 개발 · 측정 사본만 실행 줄 `CAPA_DEV_BATCH_MS` 로 덮어쓴다(9장
    「구역 회차 규칙」 묶음 길이 — 운영 `APP_ENV` 는 읽지 않고, 운영 실행 줄 · C-DEP 환경변수 표에 두지 않는다). 떠나기 신호
    (9장 R8)를 받는다 — 마운트(불러오기 · 표 · 오른쪽 칸)마다 처리기를 한 번 다는 자리에서 편집기 명부에 오르고(`joinLeaving` —
    뿌리는 편집기 상태를 단 `.emg` 요소), 신호를 받으면 묶음 타이머를 멈추고 보낼 목록 · 확정해 둔 「새 호기」 초안을 곧바로
    보낸다(`leaveNow`). 보낼 목록에 op 가 남은 동안(보내지 않았거나 ack 가 오지 않음 — `gridBusy`) busy 이고, 신호 뒤 칸 고침 ·
    초안 확정은 묶지 않으며 ack 로 목록이 비면 다시 묶는다. 「새 호기」 초안은 ack 가 없는 상태 값이라 busy 에 들지 않는다.
  - data 는 `services/equipment_grid` 의 dict + 팔레트(`grid_shared.grid_palette` — CSS 의 `--emg-*` 는 모두 여기, 새 토큰 `GRID_*` 열(배치 머리 `GRID_LAYOUT_HEAD` 포함) —
    대비는 `test_design_tokens`)다. 편집본을 바꾸는 조작은 상태 값 `outbox` 하나(9장 「스크립트와 컴포넌트」 — 「호기 추가」 도
    `add` op), 상태 값은 그 밖에 「새 호기」 초안 `draft`(편집본을 바꾸지 않는다 — `draft_value` 가 거른다) 하나다. 트리거는
    불러오기 `load`·`clear`·`new`·`dialog`, 표 `open`·`unload`, 오른쪽 칸 `open`·`goto`·`copy`(`copy_request`) 이다. 받기 콜백이 꼴을 거르고(표 트리거는
    그린 회차의 `view` 와 같을 때만) 화면 쪽 처리 함수에 넘긴다 — 출납 처리 함수는 `outbox_value` 로 두 마운트를 함께 읽는다.
  - 브라우저: 불러오기(설비명 부분 일치·목록 같음/앞부분·못 찾음, 공정, 조건 — 사용자 R1, 일정 확인, 전체), 칸 묶음·정렬·
    고름(브라우저 몫 — 칸 묶음만 localStorage), 가상 스크롤(줄 34px), 칸 고치기 키(Enter·Esc·Tab·↑↓·F2 — 줄바꿈이 든 값은 표 칸·
    호기 상세·「새 호기」 칸 모두 여러 줄 칸(`textEditor` — textarea)으로 열어 줄바꿈을 지킨다, Enter 는 확정이고 줄을 새로 넣는
    키는 없다), 엑셀 여러 칸 붙여넣기
    (`paste` 이벤트의 `clipboardData` 만 — 설비명 칸에서 붙이면 옆 칸부터 펴고, 설비명 옆 칸까지 붙인 덩이는 줄을 보이는 차례가
    아니라 붙인 첫 열의 설비명으로 맞댄다(`pasteRowsByName` — 앞뒤 공백만 뗀 글자 그대로, 설비명 열은 열쇠라 넣지 못한 칸으로
    세지 않는다. 빈 이름 · 보이는 줄에 없음 · 보이는 줄에 같은 이름 둘 · 붙인 글에 두 번이 하나라도 있으면 op 없이 한 줄
    `namePasteRefusal`. 설비명만 붙이면 넣지 못한 칸으로 세고 「설비명은 붙여 넣지 않습니다」), 엑셀이 따옴표로 감싼
    칸(줄바꿈·탭이 든 칸, 안의 `""`)은 한 칸으로 읽는다 — `parseClipboard`), 값 넣기·날짜 밀기·
    지우기·되살리기·되돌리기, 상세 칸·저장 전 변경의 칸/호기 되돌리기. 업무 검증은 하지 않는다. 데이터 글은 `textContent` 로만,
    처리한 키는 `stopPropagation`(Streamlit 단축키가 글자를 먹는다).
  - **보이는 줄 차례는 브라우저가 정한다**(2026-11-20 사용자 요청 — Qual 일정 오름차순에서 같은 날 호기가 가나다 차례로) — 불러온
    목록 차례(새로 든 호기가 위)는 파이썬 몫 그대로이고, 표는 처음부터 설비명 오름차순이다. 차례는 순수 구획 `// <grid-sort>` 한
    곳이다: 설비명은 파이썬 `space_layout_edit.natural_name_key`(「전체 불러오기」 상한 · 조건 값 목록 차례)와 같은 자연 차례
    (`nameKey` · `compareNameKeys` — 숫자 덩이는 수로, 글 덩이는 소문자 코드 포인트, Space 편집기 `naturalCompare` 와 같은 꼴 —
    한글 음절은 가나다, 영문이 한글 앞, 시험이 파이썬과 맞댄다). **글 칸 모두**(글 · 메모 · 고르기 — 수 · 날짜 칸 밖 모든 칸,
    `textSorted`)의 머리 정렬도 이 비교 하나다(2026-11-20 결과 보드 여쭘-2 a — 조건 값 목록 `_sorted_values` 와 같은 차례, 시험이
    파이썬과 맞댄다). 예외는 칸 정의의 정렬 표지 하나다 — `GridColumn.sort`(`columns_payload` 의 `sort`)가 `capa` 인 투자Capa 는
    칸 꼴이 글 그대로(고치기 · 붙여넣기 · 호기 상세)이고 머리 정렬만 수 차례다(2026-11-21 확인 보드 q-invest-sort a — `gridModel`
    이 표지를 칸 꼴보다 먼저 본다). 수 읽기 `capaNumber` 는 Space 색 기준 `space_color_basis.capa_number` 와 같은 읽기(숫자 · 쉼표 ·
    소수 + 꼬리 K 천 · M 백만, 공백은 파이썬 `str.isspace` 벌 — 시험이 BMP 글자로 맞댄다. 꼬리는 지수로 붙여 한 번에 읽어 같은
    십진수 「1.005K」 · 「1,005」 가 같은 수다)이고, 차례는 수 → 못 읽는 글(글 차례) →
    빈 값, 같은 수(「322K」 · 「322,000」)는 둘째 열쇠로 간다(`compareCapaKeys`). 내림차순은 빈 값만 빼고 뒤집는다(못 읽는 글이
    위). 수 칸은 수로, 날짜 칸과 수 칸의 수 아닌 값은 `localeCompare('ko')` 그대로다. 머리 정렬(`sortOrder`)은 그 칸
    값 다음 둘째 열쇠가 늘 설비명 오름차순(내림차순에서도)이고 빈 값 · 빈 이름은 늘 아래다. 머리 누름(`nextSort`)은 다른
    칸이 오름 → 내림 → 처음 차례, 설비명 칸이 처음 차례 ↔ 내림이다(설비명 오름은 늘 `S.sort = null`). 처음 차례의 설비명 머리는 ▲ 없이 `aria-sort` 만 단다(설계 규칙
    UI-TXT-05). 고름 · 기준 줄 · 키 이동 · 붙여넣기 범위는 모두 이 보이는 차례(`model.live` · `model.ordered`)다 — 설비명 칸에서
    붙인 덩이만 붙인 설비명으로 줄을 맞댄다(위 `pasteRowsByName` — 설비명 밖 칸에서 시작한 덩이는 보이는 차례 그대로다). 목록 지문이
    바뀌어 처음으로 돌린 회차에 오른쪽 칸에 연 줄이 이 회차에 새로 든 줄이면(「호기 추가」 · 「저장 전 변경」 에서 목록 밖 호기
    열기 — `freshOpen`: 앞 목록 줄이 모두 남은 채 늘기만 했고 연 줄이 앞 회차에 연 줄이 아닐 때) 그 줄을 표 머리 바로 아래로
    굴린다 — 그 밖의 불러오기(「목록 비우기」 뒤 연 상세를 둔 채 다시 불러오기 포함) · 저장(새 호기 id 가 바뀜) · 첫 그리기는
    맨 위다(UI-PRF-03). 목록을 지킨 회차(같은 목록 · 옮김만)에 앞 그리기에서 창 안에 보이던 연 줄이 그대로 열려 있으면 그 줄이
    새 차례에서 옮겨 가도(호기 상세로 설비명을 바꿈 · 정렬한 칸 값을 바꿈) 창 안 같은 높이로 따라간다(`openSlot` →
    `keptRowShift`) — 창 밖이던 연 줄은 따라가지 않고 스크롤 그대로다. 끼운 형제 줄도 설비명 차례 자리에 선다(`keptRowShift` 가
    보던 줄을 지킨다).
  - 자리에 남는 한 줄은 표와 오른쪽 칸이 저마다 그린다(`fillNote` — 브라우저 한 줄(칸 수 상한 · 이름 붙여넣기 거부 · 잠긴 칸
    붙여넣기 거부(넣을 칸이 모두 잠겼으면 op 를 보내지 않고 잠금 까닭 — `lockNote`) · 「붙여넣는 중」)과 오른쪽 칸의 파이썬 자리
    거부). 화면 등급 잠금(`read_only_data`)은 모든 칸 번호를 `lockSets["grade"]` 에 싣고 줄 잠금 갈래 맨 앞에 둔다. 「붙여넣는
    중」 은 그 op 의 ack 가 돌아오면 거둔다(`noteSeq`). 동작 결과는 알림창이다.
    `undo` op 는 맨 위 단계를 되돌린다. `moved` 는 목록 지문(`view`)으로 고름·스크롤을 처음으로 돌리기 **전에** 얹는다. 불러오기
    회차가 돌아와도 초점이 표 등 불러오기 밖에 있으면 찾기 칸으로 가져오지 않는다(`focusIsFree`). 팝오버는 화면 오른쪽 밖으로
    나가면 왼쪽으로 당긴다(`popoverShift`). 팝오버를 열면 초점을 패널 안 첫 칸으로 옮기고(`enterPanel` — 공정은 찾기 칸, 조건은
    첫 조건 칸) Esc 는 패널에서도, 열린 채 돌아온 여는 단추에서도 닫는다(닫히면 초점은 여는 단추 — 닫힌 단추의 Esc 는 막지 않는다).
    초점이 패널·여는 단추 밖으로 나가면(Tab) 닫는다 — 초점은 옮겨 간 칸에 두고, 받을 칸 없는 나감(다시 지으며 지운 칸·창 밖)은 닫지 않는다.
    패널 안 글자·여백 누름이 낸 나감도 닫지 않는다 — 감싸개의 누름 표를 그 일 동안만 둔다. 패널은 초점을 받아(`tabIndex -1`,
    Tab 정지 아님) 그 누름의 초점이 본문 `stMain` 으로 빠지지 않고 패널에 머물러 Esc 가 닫는다(2026-10-27 E2E).
    패널 안에서 불러오면(공정 하나·「맞는 n대 불러오기」) 바로 닫고 초점은 여는 단추(`data-fk` `pop-…`)로, 불러오기 줄의 다른 단추
    (다른 팝오버 여는 단추 포함)를 누르면 패널만 닫는다(`closeOtherPress` — 누른 단추가 지워지면 click 이 서지 않아 다시 짓지 않는다).
    표 본문의 Tab 정지는 초점 칸 하나(체크·「−」 는 `tabIndex -1`, 칸 위 Space = 그 줄의 체크 칸 — 산 줄은 고르기, 지운 줄은
    되살리기). 화살표는 화면 차례의 모든 줄을 걷는다(`moveFocus` — 지운 줄도 줄이다, 지금 칸을 못 찾으면 움직이지 않는다). 고른 줄
    띠를 닫는 단추(「선택 n대 지우기」·「선택 풀기」)는 누른 단추가 사라지므로 초점을 표의 초점 칸으로 돌린다(`refocusTable`).
    「새 호기」 칸(`drawNew`)은 브라우저 초안을 들고(받은 초안은 번호가 클 때만 — `adoptDraft`), 체크 상자 칸은 판정이 지금 초안의
    것이면 그 판정, 아니면 칸이 찼는지만 보이고(`tierDone`), 칸 오류는 그 칸을 만졌거나 값이 있을 때만 — 다만 늘 필수인 칸이
    아니면(다른 칸 값 때문에 막는 칸) 만지지 않아도 보이고(`showsError`), 「호기 추가」 는 필수 칸이 찼고 지금 초안의 판정이 막지
    않을 때 켠다(`canAdd` — 판정 전이면 켜 두고 파이썬이 `add` op 를 다시 본다). 판정 글(`hint` — 막힌 까닭 · 가용대수에 아직 안 드는 칸, 더
    말할 것이 없으면 빈 글)은 칸에 늘 두지 않고 그 단추의 풍선이다(`addTip`, `role="tooltip"` · `aria-describedby`, `.emg-tip` — 편집 표 풍선과
    같은 꼴, 300ms). 꺼진 단추는 마우스 · 초점을 받지 않아 감싼 칸(`.emg-tip-host`)이 호버를 받고 꺼진 동안 탭 자리와 `data-fk` 를 맡는다(UI-TXT-01 ·
    UI-INP-07). 판정 전 풍선은 둘로 갈린다 — 확정한 초안의 판정을 기다리면 「고친 칸을 확인하는 중입니다」, 아직 확정하지 않은 글(확정은 칸을 벗어나거나 Enter)은 아무 확인도
    돌지 않으므로 빈 필수 칸 이름(판정과 같은 말)이거나 「칸을 벗어나면 확인합니다」 다. 확정한 초안은 모아 두었다가 칸을 떠날
    때 · 쉼 뒤 · 「호기 추가」 직전 · 표 밖 · 창 숨김 · 내릴 때 하나만 보낸다(`commitDraft` · `flushDraft`, 가져오기는 초안을 싣으므로
    모아 둔 것을 버린다 — `dropQueuedDraft`). 눌러서 거절될 때의 자리 거부 한 줄은 같은 판정 글 그대로다. 칸을 통째로 다시 그리는 칩·함께 넣기 체크·「양식
    비우기」(상세 칩도)는 `data-fk` 를 달아 초점이 돌아온다(키보드로 채우는 동안 칸 처음으로 가지 않게). 칸 아래쪽에서 누른 조작이 연
    다른 칸(「호기 추가」 → 상세, 「이 호기로 새 호기 만들기」 → 새 호기 칸)은 그 칸이 처음 선 회차에만 칸 머리를 보인다(data 표지
    `revealHead` · `revealHead`·`needsReveal`, `.emg-side` `scroll-margin-top` 이 머리 띠를 비킨다 — 칸 안에서 고치다 받은 거절 한 줄로
    쓰던 자리를 잃지 않게, 「이 호기 지우기」 는 칸 머리로 올리지 않는다). 칸 머리가 넘치는 스크롤 칸(오른쪽 칸 본문 칸) 안이면 먼저
    그 칸만 칸 머리까지 올리고(`scrollBoxOf` — 그림자 DOM 밖으로 건너 올라가 `stMain` 앞에서 멈춘다 · `boxScrollFor`), 그래도 머리 띠 아래로
    가려 있을 때만 `scrollIntoView` 한다 — 바로 `scrollIntoView` 하면 Chrome 이 붙은(sticky) 자리가 아니라 원래 흐름 자리로 셈해
    바깥 페이지까지 밀어 왼쪽 표가 튄다. 상세 「비가동 일정 표에서 고치기」 는 누를 때 두 칸 줄(그림자 DOM 밖
    `stHorizontalBlock`)의 머리가 가린 높이 위로 나가 있으면 머리 띠·화면 탭 줄 아래로 올린다(`revealColumnsTop` — 그 표는 왼쪽
    칸 맨 위에 선다. 가린 높이는 sticky 화면 탭 줄 `PAGE_TABS_STRIP` 의 아래 끝 + 8px, 없으면 머리 띠 72px + 8px). 표지 색은 새 토큰 없이 팔레트(오류 선·강조·배치 머리 면·머리
    면)이고 글자(필수·가용대수·도면)가 함께 간다.
    자리표시 글은 `--emg-muted`(TEXT_MUTED)로 그린다 — 브라우저 기본 #757575 는 테마를 몰라 어두운 바탕에서 4.5:1 에 못 미친다(Space
    배치 편집기 입력도 `--sle-muted`). 옅은 바탕 호버는 칠하지 않은 단추(`.emg-btn:not(.is-primary)`)에만 걸고 칠한 단추는 제 바탕에 `filter: brightness(1.08)` 만 건다 — 대비는 `docs/design_system.md` 2-2. 빈 날짜 칸 자리표시는 꼴(`DATE_PLACEHOLDER` — `YYYY-MM-DD`)이다(실제 날짜는 값처럼 읽힌다).
    새 호기 칸 막힘 힌트의 칸 이름은 체크 상자 차례(에러 없이 → Y/N → 가용대수 → 도면) 다음 표 차례다. 고른 줄 띠의 「반입·Qual
    일정 [n] 일 밀기」 는 한 덩이(`emg-shift`)로 줄을 바꾼다.
    표 본문을 다시 그린 뒤 초점을 돌려줄 때(`paintWindow` → `focusTarget`) 스크롤을 끌지 않는다(`preventScroll`) — 키 손짓이 부른
    그리기(`S.keying` — 세로는 `ensureVisible`, 가로를 따라감)만 기본 focus 다. 끌면 휠마다 초점 칸 자리로 되돌아와 칸을 누른 뒤
    휠이 제자리에서 헛돌았다(2026-11-12 사용자 요청 2). 친 글이 든 칸이 그린 창(`BUFFER_ROWS`) 밖으로 나가면 그 자리에서 확정하고
    (`settleEdit` — 칸이 사라지면 focusout 이 오지 않는다), 초점 칸이 밖으로 나가 문서로 떨어진 초점은 다른 곳이 잡지 않은 동안 돌아오면
    되돌려 준다(`S.heldFocus`). 고르기 창(`.emg-dd`)은 칸 안 자식 그대로 화면 자리에 뜬다(`position: fixed` — `placeChoice` ·
    `choicePlace`, 아래가 모자라면 위로 · 그래도 모자라면 창 안 스크롤 — 같은 칸의 앞 창 스크롤을 이어 받고 고른 값이 창 안에
    보이게 맞춘다(`listScroll`), 오른쪽 끝은 `popoverShift`). 표 상자 안 절대 자리였을 때는
    상자에 잘리고 상자를 넘치게 해 줄이 적은 표에서 머리가 밀려 사라졌다. 놓은 칸이 표 · 페이지 스크롤 · 창 크기로 움직이면
    고르지 않은 채 닫는다(`choiceMoved` — 연 뒤 늦게 온 scroll 은 칸이 그 자리라 닫지 않는다). 칸을 열면 그 줄을 머리 밑에서
    꺼내고(`startEdit` 의 `ensureVisible`), 글 편집 칸은 머리 아래 층(공용 `cells.css` z 5 — 시나리오 목록 표도), 고르는 칸만
    머리 위(`is-choosing`)다. 창을 칸 밖으로 옮기지 않는다 — 칸 밖 초점 판정(focusout)과 본문 위임 누르기(`data-pick`)가 거기에 기댄다.
    순수 구획 `// <grid-…>` 은 `tests/test_equipment_master_grid_assets.py` 가 node 로 돌린다.
- `src/capa_simulation/components/edit_grid.py` (+ `edit_grid_assets/` HTML·CSS·JS) — 범용 편집 그리드(Components v2, 그림자
  DOM)의 두 등록·그리기·받기와 세션 몫. 기준 정보 9표와 생산 계획 PKG PLAN · 수율이 쓴다(편집 표 횡전개 — 설비 마스터 표는
  아직 제 등록 그대로). 표 위 단추 줄과 표 도구 막대를 한 줄로 세우는 페이지 CSS 는 `one_line_style`(작업 줄 칸 · 단추 줄 ·
  그리드 칸 key 와 창 폭 문턱 · 왼쪽 비움)이다.
  - **표 도구 꼴**(2026-11-12 보드 답 q1 가 — 모든 그리드 공통): 되돌리기 · 다시 실행 · 칸 폭 맞춤 · 전체 화면은 Material Symbols
    그림 단추(`TB_GLYPH` — 이름은 aria-label, 풍선은 이름 · 단축키 · 하는 일, 단축키 그대로)이고 단추 줄 높이와 같은 정사각형이다.
    찾기 칸은 140px 이고(2026-11-12 남은 물음 보드 ③-10 (가) — 세 그리드 공용 150 → 140) 위아래 화살표 · 찾은 수는 찾는 글이
    있을 때만 선다(`has-q`). 변경 목록 단추는 글 단추 「적용 전 (n)」(`CHANGES_BUTTON` — 열한 그리드 공통)이고 원래 이름(부르는 쪽
    `changes_label` — 「적용 전 변경」)은 그 단추 풍선(`title` 만 — 보이는 글이 이름)과 서랍 제목 · 빈 글이 쓴다(사내 리뷰
    202611131000 보드 카드 4 (나) — 줄이는 차례 셋째, 설계 규칙 UI-LAY-11). 막대 글에 「변경」 을 쓰지 않는 것은 머리 띠 칩
    「변경 n」(이 세션의 변경 건수)과 한 화면에 같은 낱말이 다른 수로 서지 않게다(UI-CON-02 — 2026-11-14 사용자 답). 이 글로도
    스크롤 막대를 켠 Chrome 의 사내 보고 창 1283 에서 세 그리드 표 위가 모두 한 줄이다(PKG PLAN 문턱 1268 — 설계 규칙 4장
    「생산 계획 표 위 한 줄」).
    작업 줄 「편집 취소」(초안 전체 버림)의 그림은 `DISCARD_ICON`(`:material/delete_sweep:` — 설비 마스터 · 시나리오 목록
    「모두 버리기」 와 같은 그림)이라 표 도구 「되돌리기」(한 칸 · `undo` 화살표)와 다르다(2026-11-12 남은 물음 보드 ③-11 (가)).
    같은 답의 메모 「다른 편집기에도 공통 적용」 은 이 부품을 쓰는 표 열하나로 끝난다 — Streamlit 편집표(`st.data_editor` 열 곳)는
    Streamlit 표 도구 막대(이미 그림 단추 · 풍선 이름)이고, 설비 마스터 · 시나리오 목록 표에는 되돌리기 · 다시 실행 · 칸 폭 맞춤 ·
    전체 화면 · 칸 찾기 도구가 없다(설비 마스터의 설비명 칸은 불러오기 — 범용 그리드로 옮길 때 함께, 설계 규칙 4장 「편집 그리드
    표 도구 막대」).
  - **바탕**(2026-11-12 보드 답 k-b2): 팔레트 `surface` 는 페이지 바탕색(`SURFACE_PAGE`)이다 — 둘레 · 칸 · 칸 입력 칸 · 적용 전 변경
    판 · 전체 화면 판. 표 도구 단추 · 찾기 칸은 `control`(`SURFACE` — 화면의 다른 단추와 같은 꼴), 고친 칸 · 틀린 칸 · 잠긴 칸은 제 토큰.
  모듈을 읽을 때 세 컴포넌트를 등록한다 — 쓰는 페이지 대본이 늘 import 한다.
  - **줄 규칙 표의 등록**(`ROWS_COMPONENT` `capa_edit_grid_rows` — 2026-11-18 접속 명단): 껍데기에 `fmts` · `ids` · `locks` ·
    `rowOps` 가 있으면(`uses_rows`) 줄 갈래 `eg_rows.js` · `eg_rows.css` 를 eg_core 앞에 더 실은 등록(`ROWS_JS_PARTS` ·
    `ROWS_CSS_PARTS`)으로 그린다 — 그 밖의 표가 받는 등록 JS 는 그대로다(예산 121 KB, 줄 규칙 등록 131 KB — 맨 앞 공용 떠나기 조각 `leave_js` 는 그리드 몫 밖 2 KB 이하로 따로 센다). 줄 갈래는 글 · 고르기
    칸 다듬기(`// <eg-kinds>` — eg_pure 의 `KINDS` 에 단다, Python 과 쌍둥이), 줄 규칙 잠금(core 의 `S.lockAt` — 편집 시작 · 한 칸
    붙여넣기는 까닭 한 줄로 막고 미리보기는 잠긴 칸을 건너뛴다), 표 도구 막대 「줄 지우기」 · 「줄 되살리기」(고른 줄 — 지울 수 없는
    줄은 빼고 까닭 풍선, 모두 지운 줄이면 되살리기), 지운 줄 지움선 · 잠긴 칸 바탕 + 까닭 풍선(`title`) · 글 칸 왼쪽 맞춤(`paintCell`), 고르기 칸
    편집 중 칸 아래 항목 목록(누르면 그 항목 · ↑ ↓ 가 항목을 옮김 — 칸 아래가 보이는 창 밖이면 칸 위로), 붙일 덩어리가 표 끝(빈 새 줄)을
    넘으면 잘라 붙이지 않고 통째로 거절하는 `pasteGuard`(select 가 paste 갈고리보다 먼저 부름 — 글 `freshShort`)다. 표 없는 껍데기와 줄 규칙 표를 오가는
    호스트는 `render_edit_grid(rows=True)` 로 늘 이 등록이다(같은 key 의 등록이 바뀌면 옛 JS 가 줄 규칙 표를 그린다 — 접속 명단). 변경 목록은 지운 줄을 맨 앞 「줄 지움」 으로 싣고 ✕ 가
    `restore` 다. 시험 `tests/test_edit_grid_rows_js.py`. 시험 대역은 `_GRID_ROWS` 도 바꾼다.
  - **두 등록**: 무거운 `capa_edit_grid`(등록 JS·CSS + 껍데기 data — 표가 같으면 회차마다 같은 dict 라 ForwardMsg 해시 참조로 간다)와
    작은 `capa_edit_grid_feed`(JS 3 KB 이하 + 초안·오류·ack). 둘은 `window.__capaEditGrid[host].feed` 칸과 `window` 이벤트
    `capa-edit-grid` 로 잇고(비공식 — 화면 탭 줄의 `window.__capaHistoryGuard` 선례), 무거운 JS 는 차례에 기대지 않는다(feed 의
    `baseKey` 가 껍데기와 다르면 칸에 둔 채 껍데기가 오면 쓴다). `render_edit_grid` 가 늘 같은 자리에서 feed → 무거운 요소 차례로
    그리고(둘 다 key 고정 — `feed_key(host)` = `<host>-feed` — CCv2 key 에는 `__` 를 쓸 수 없다, 트리거 id 구분자), feed 칸은 스타일만 든 `st.html`(이벤트 칸 — 자리를 먹지 않는다)로
    숨긴다(`hide_feed_style`). 호스트 key 는 ASCII `[A-Za-z0-9_-]+` 만(feed JS 와 같은 글자), `__` 없이.
  - **편집은 상태 값 `outbox` 하나**(`STATE_NAMES`, 트리거 없음 — 9장). 콜백 몸통 `collect_outbox` 는 새 op 만 세션 inbox 에
    쌓고 마운트별 seq 를 올린다. 반영은 본문의 `apply_inbox`(표별로 나눠 `TableSlot` 의 색인·규격·세션 칸에 — 지금 그리지 않는
    표도 op 의 `table` 로)이고, `feed_data` 의 ack 는 그 마운트별 seq 기억이다. 브라우저는 ack 를 표와 상관없이 그 마운트의 것으로
    받는다(표 없는 껍데기 — 읽기 보기 — 나 다른 표의 feed 에서도 출납을 비운다). 보내기(`sendNow` — 묶음 쉼·첫 op·붙여넣기·줄 지우기 단추·되돌리기·다시 실행·focusout·
    visibilitychange·정리 함수)는 **아직 한 번도 보내지 않은 op 가 있을 때만** 반영 안 된 op 전부를 싣는다 — 이미 보낸 op 만 남은
    출납을 다시 보내면 같은 값으로 앱 회차가 하나 더 돌았다(2026-11-03 마지막 검토 C3). 묶음 쉼은 결정값 상수 `edit_grid.SEND_MS`
    하나가 정하고 껍데기 `limits.sendMs` 로 JS 에 간다(`shell_limits` — `grid_shared.batch_ms`, `eg_core.js` 의 `EG_SEND_MS` 는 그 칸이 없을 때만 쓰는 대비 값,
    시험 `tests/test_edit_grid_send_js.py`). 개발 · 측정 사본만 실행 줄 `CAPA_DEV_BATCH_MS` 로 덮어쓴다(9장 「구역 회차 규칙」 묶음 길이 —
    운영 `APP_ENV` 에서는 읽지 않는다). 편집기 구역 머리 표지 도우미 `draft_present`(초안 칸 있음 — 칩 · 탭 점이 세는 값) ·
    `head_value`(세션 칸 값을 해시 가능한 꼴로) · `scenario_mark`(활성 시나리오 내용 토큰)는 세션 칸만 읽는다 — 어댑터의 `scope_head`
    가 쓴다(구역 회차 시험 `tests/test_grid_scopes.py`). 세션 칸 이름은 부르는 쪽이 `GridKeys`·`TableSlot`
    으로 정한다. 이력은 `history_of` 가 없으면 새 `gen` 으로 세우고, 초안을 버리는 길(`discard_table`)은 이력도 함께 지운다.
    사용자가 일부러 버린 길(「편집 취소」 — `discard_table(…, keys)`, `GridKeys.discarded` 칸)은 버린 `gen` 을 적어(최근
    `DISCARDED_GENS` 개) 그 직전 출납 묶음의 op 를 `apply_inbox` 가 토스트 없이 버린다(빈 초안 자리도 걷는다). 세대가 바뀌어도
    옛 세대 op 를 보낼 목록에서 빼지 않는다 — 서버(`apply_inbox`)가 버리면서 세어 토스트로 알리고(`DROPPED_TOAST`) ack 가
    지운다(`boxStale` 은 미리보기만 걷는다). 묶음이 든 op 도 서버까지 가고, 보낸 op 도 다음 보냄에 함께 실려 합쳐진 회차에서
    수가 빠지지 않는다. 필터가 걸린 동안 여러 줄 붙여넣기는 막고 상태 줄(`pasteFiltered`)로 알린다 — 판정은 feed `filters` 다
    (큰 표는 서버가 줄을 좁혀 `view.filtered` 로 알 수 없다, `eg_select.js` `selNarrowed` · `selOnPaste`).
  - 글(`texts` — 오류 문구는 그 표 형식의 하한·상한으로 채움, 「적용 전 변경」 같은 변경 목록 이름은 부르는 쪽이, 막대 단추 글
    「적용 전」 은 `CHANGES_BUTTON` 하나 — 표 없는 껍데기 `texts_for_empty` 도 같은 두 글)과 팔레트
    (`palette` — CSS 의 `var(--eg-*)` 는 모두 여기, 찾기 일치 칸 새 토큰 `GRID_MATCH_FILL`)는 회차마다 껍데기에 싣는다.
  - 자산: 등록 JS 는 기능별 파일을 `JS_PARTS` 차례(`eg_pure` → `eg_select` → `eg_fill` → `eg_toolbar` → `eg_core`)로 잇고 주석만 든
    줄을 걷는다(`registered_js`). 맨 앞에는 공용 떠나기 신호 조각(`grid_shared_assets/leave.js` 의 `LEAVE_SECTIONS` — `<capa-leave>` ·
    `<capa-leave-window>`, 9장 「구역 회차 규칙」 R8)을 잇는다(`leave_js`). 마운트는 `egBind` 에서 편집기 명부에 오르고
    (`joinLeaving` — busy 는 보낼 목록에 op 가 남음, flush 는 `sendNow`) 정리 함수가 내린다. `capa-leaving` 을 받으면 묶음 타이머를
    멈추고 남은 op 를 곧바로 보내며, 신호 뒤 op 는 묶지 않고(`queueOp` 의 `leavingNow`) ack 로 목록이 비면 다시 묶는다
    (`egTakeAcks` 의 `settleLeaving`). 시험 `tests/test_edit_grid_send_js.py` · bind-once `tests/test_ccv2_hygiene.py`(`BIND_ONCE`). `eg_pure.js` 는 순수 구획 `// <eg-codes>`·`<eg-format>`·`<eg-outbox>`·`<eg-nav>`·`<eg-view>`·
    `<eg-layout>`·`<eg-changes>` 과 기능 갈고리 표(`feature(def)` — init·keydown·pointerdown·paintCell·paintOverlay·onFeed·onSelect·
    onLayout·cleanup, 차례 select → fill → toolbar)이고, `eg_core.js` 가 마운트·가상 스크롤(줄 30px)·여러 열쇠 칸 고정(누적 폭이 표
    폭의 45% 를 넘는 칸부터 풀림 — 첫 칸은 늘 고정)·칸 편집(Enter·F2·글자 입력, 확정 Enter/Shift+Enter/Tab, 취소 Esc)·한 칸
    붙여넣기(기능이 처리하지 않은 `paste`)·이동 키(화살표·Ctrl+화살표·PageUp/Down·Alt+PageUp/Down·Home/End·Ctrl+Home/End·Tab)·
    Delete·Ctrl+Z/Y·머리 정렬(보기만)·필터 보기(feed `filters`)·값 칸 머리 풍선(`role="tooltip"`, 300ms)·칸 오류(빨강 + 상태 줄 문구)·
    바뀐 칸 표시·토스트·상태 줄을 맡는다. 고른 범위는 고정 모서리(`S.origin` — 없으면 지금 칸)와 맞은편 모서리(`S.focus`)이고
    지금 칸(`S.anchor`)은 그 안 어디든 있다 — Ctrl+A·Shift+Space·Ctrl+Space 는 지금 칸을 지킨 채 범위만 넓힌다(엑셀, 이어 친 값·
    Ctrl+Enter 가 그 칸에서). 보기 차례가 바뀌면(정렬·필터) 한 원본 줄 안의 고름만 그 줄을 따라가고 여러 줄 고름은 지금 칸 하나로
    접고 기능(요약)에 알린다. 고정 칸으로 옮기는 이동(Home·Ctrl+Home)은 가로 스크롤을 0 으로. 높이(`egLayout`)는 창 크기·frame
    크기·본문 블록(`stMainBlockContainer` — 표 위 알림이 서고 걷힘)의 ResizeObserver 로 다시 잰다. 표(모델)를 바꾸면 앞 표의
    토스트·상태 글을 걷는다. Ctrl 단축키 글자는 모두 `shortcutLetter(key, code)`(한글 자판이면 자판 자리 — `<eg-nav>`)다. 칸
    편집기는 z 1 — 굴리면 머리 줄(4)·고정 칸(2) 아래로 숨는다. 기능이 부르는 내부
    함수 이름(`paint`·`setRange`·`queueOp`·`sendOnce` 등)은 바꾸지 않는다(`test_edit_grid_assets` 가 본다). 순수 구획은 node 로
    돈다(`tests/edit_grid_node.py`), AppTest 대역은 `tests/edit_grid_fake.py`(`early=True` 면 출납 콜백을 진짜처럼 회차 맨 앞에서
    부른다 — 페이지 앞에서 그린 사이드바·탭 점의 때맞춤을 본다, `deliver_ops`), 시험 앱은 `tests/edit_grid_demo_app.py`(앱 화면에는
    없다).
  - `eg_select.js`·`eg_select.css`(고르기)는 끌어 고르기(스크롤 칸 pointer capture + rAF 자동 스크롤 — 창 밖으로 멀수록 빨리
    `min(4 + 거리 × 0.5, 80)`px/프레임, 값 칸에서 시작한 끌기는 고정 칸 위에서 먼저 왼쪽으로 다 굴린 뒤에 분류 칸을 고른다)·
    Shift+누름·Shift+이동 키(화살표·Ctrl+화살표·Page·Home/End)·Ctrl+A·Shift+Space(줄)·Ctrl+Space(칸)·Ctrl+C·Delete(고른 범위의
    값 칸 `clear` 하나 — 분류 칸은 건너뜀)·기준 칸 붙여넣기(고른 범위 왼쪽 위부터 덩어리 그대로 `write` 하나 — 분류 칸에 걸린 칸은
    건너뛰고 표 끝을 넘은 칸은 버림, `limits.paste` 칸 상한)·Ctrl+X 안내·복사 점선(Esc·칸 편집·Delete 에 지움 — 고름을 옮겨도
    남는다, 엑셀처럼)·범위 표지(지금 칸은 칠하지 않음)·고른 칸 머리 밑줄을 맡는다. **복사는 Ctrl+C keydown 을 막지 않고**(페이지
    글 고름만 지운다) 브라우저가 초점 칸(스크롤 칸)에 쏘는 동기 `copy` 이벤트에서 `clipboardData` 에 엑셀 따옴표 TSV(줄 사이 CRLF,
    마지막 줄이 빈 글이면 끝 CRLF 하나 더)를 싣는다 — 수 칸은 원값(`rawText` — percent 는 분수), 분류 칸은 표시명, 보기 차례.
    칸 편집기 안의 복사·붙여넣기는 브라우저 기본이다. 다른 기능이 쓰는 창구: `selDrag(S, event, {move, end})`(채우기 손잡이 끌기)와
    갈고리 `paste(S, matrix, event)`(true 면 기준 칸 붙여넣기를 건너뜀 — 채우기의 되풀이 붙여넣기 자리). 순수 구획
    `// <eg-rect>`·`// <eg-clip>` 과 가짜 DOM 동작은 `tests/test_edit_grid_select_js.py` 가 본다. 끌기(고르기·채우기 손잡이) 중
    Esc 는 끌기만 거둔다 — 복사 점선이 떠 있어도 먼저이고(손잡이 끌기는 놓아도 채우지 않는다), 점선은 그다음 Esc 가 지운다.
  - `eg_fill.js`·`eg_fill.css`(붙여넣기·채우기)는 `paste` 갈고리(값 하나 → 고른 범위 전체, 고른 범위가 덩어리의 정수 배면 되풀이,
    아니면 기준 칸부터)·채우기 손잡이(고른 범위 오른쪽 아래 7px — 세로·가로 가운데 더 멀리 끈 쪽 하나로 원본 덩어리를 되풀이,
    수열 외삽 없음)·Ctrl+D/Ctrl+R·편집 중 Ctrl+Enter(고른 범위 전체에 그 값)를 맡는다. 채우기는 값을 싣지 않고 `fill` op 를 보내
    서버가 지금 원본 칸 값에서 되풀이한다. 순수 구획 `// <eg-paste>`·`// <eg-fill>` 과 사례 표(`tests/fixtures/edit_grid_cases.json`)
    는 `tests/test_edit_grid_fill_js.py` 가 본다.
  - `eg_toolbar.js`·`eg_toolbar.css`(도구 막대)는 찾기(Ctrl+F·F3·Enter/Shift+Enter·Esc)·되돌리기/다시 실행 단추·칸 폭 맞춤·머리
    경계 끌어 폭 바꾸기(40~480px, 표마다 브라우저 저장)·적용 전 변경 서랍·전체 화면(그림자 DOM 안 `<dialog>.showModal()`)·상태 줄
    선택 범위 요약(개수 · 합계 · 평균)을 맡는다. 되돌리기·다시 실행·칸 폭 맞춤·「적용 전 (n)」·찾기 ▲▼ 를 마우스로 누르면 초점이
    표로 돌아간다(`tbGridCommand` — 이어 누르는 Ctrl+Z·화살표·Ctrl+C/V 가 표에 간다, 자판으로 누르면 단추에 남는다, 찾을 글이 없어
    찾기 칸에 초점을 준 ▲▼ 는 돌리지 않는다). 순수 구획 `// <eg-search>`·`// <eg-summary>`·
    `// <eg-width>` 과 가짜 DOM 동작은 `tests/test_edit_grid_toolbar_js.py` 가 본다.
- `src/capa_simulation/components/page_tabs.py` (+ `page_tabs_assets/` HTML·CSS·JS) — 머리 띠 아래 화면 탭 줄
  (Components v2, 그림자 DOM)이다. **`app.py` 에서만 불러온다**(모듈이 컴포넌트를 등록한다 — `test_benchmark_home.py`).
  조건 팝업 호스트 칸 바로 뒤·페이지 앞에서 고정 key 로 매 앱 전체 회차 그리고 프래그먼트로 감싸지 않는다(9장 「스크립트와
  컴포넌트」). data 는 세션 목록·`PageSpec` 상수뿐이고 DB 를 읽지 않는다. 트리거 넷(`select`·`close`·`pin`·`move`)의 콜백은
  목록 칸·이동 대기 칸만 적는다. 탭 이름은 사이드바 라벨에서 「(구현중)」만 뗀 글, 아이콘은 사이드바 Material 아이콘이다.
  이름 곁 표지 둘(2026-11-09 보드 C1 (라) · T8)은 data 의 `proc`(공용 공정을 따라가는 화면 — `shared_process.FOLLOWERS`, 지금
  값이 그 화면이 따르는 꼴일 때 깔때기 · 그 화면이 마지막으로 그린 선택지에 없는 공정이 있으면 주황 · 풍선 「공정 Mold ·
  Underfill — 산출 결과 에서」 + 「PMC 는 이 화면에 없음」 — `process_field.tab_mark`)와 `wip`(구현 중 화면의 「구현중」 표지
  풍선 — `wip_title`, 원천 이름 · 샘플을 켠 동안 「합성 샘플로 미리 봄」)이다. 깔때기는 알림 칸 공정 칩과 같은 선 꼴 path
  상수(사이드바 `filter_alt` 꼴)이고, 「구현중」 은 보이는 탭 어느 하나라도 이름이 말줄임되면 흐린 고리 점으로 줄어 이름 자리를 먼저 지킨다(JS
  `fitWip` · `wipShrink` — 제 이름만 보지 않는다: 줄지 않는 지금 탭의 글 표지 폭을 이웃 탭이 떠안는다,
  그릴 때 · 목록 폭이 바뀔 때 다시 잼, 글은 읽기 도구 · 풍선에 남음, UI-ACC-02). 지금 탭의 공정 표지는 알림 칸 JS 가 회차 끝에
  값 칸 표지를 읽어 보내는 문서 사건(`capa-process-here`)으로 바로잡는다 — 탭 줄은 페이지보다 먼저 그려진다.
  가리킬 수 있는 기기에서 지금 탭이 아닌 고정 안 한 탭의 × 는 가리키거나 초점이 들 때만 보이고 누름을 받으며, 그 자리는 평소
  이름에 내준다(× 가 먼저 줄어든다 — 탭 10칸 · 1283px 에서 이름이 한 음절로 줄던 것, 2026-11-07 답 narrow · UI-ACC-02). 칸 폭은
  그대로라 가리켜도 이웃 탭이 밀리지 않는다. 터치 기기(`hover: none`)는 × 가 늘 보인다(`page_tabs.css`).
  - 점(`page_unsaved_marks`)은 세션만 읽는다 — 붙여넣기 대기·표 초안(기준 정보 그리드)·설비 편집본(가용설비·Space 두 탭)·Past Data 초안·시나리오
    관리 표 초안·VOC 적어 둔 답변(`voc_draft_keeper.kept_reply_count` — VOC 탭에)·가용설비 현황 Preference 입력 비가동
    초안(`manual_downtime_tab.manual_downtime_draft_pending` — 가용설비 현황 탭에, 2026-11-19)·Space 층 사용 편집 초안(`floor_state_draft_pending` — 편집 중인가 ·
    초안 모두 위젯 밖 칸, Space 탭에, 2026-11-19 보드 m19-e2e-space-leave (나))은 어느 화면에서나, 편집표의 적용 전 편집과 가용설비 현황 설비 마스터 탭 작은 편집표 둘의 적용 전 편집
    (`small_editor_edits` — 시나리오 편집 등록부에는 넣지 않는다, 시나리오 저장 경고가 아니다)은 지금 탭에만 찍는다. 지금 화면의 그 둘이 있으면 다른 탭
    누름·지금 탭 × · 사이드바 화면 링크 · 브라우저 뒤로·앞으로가기(Navigation API — 아래 「뒤로 · 앞으로 지킴이」)에서 `confirm` 으로 묻는다(`leave_notice`). 시나리오 미저장·
    Cut-off 초안·Qual 계산기는 점 대상이 아니다. 테마 단추의 「저장 안 함」 표지도 이 판정 하나를 쓴다.
    - 문서를 떠날 때(새로고침·브라우저 탭 닫기·주소 바꾸기)는 브라우저 확인 창이다(순수 구획 `<tabs-unload>`, 개선 거리 I3 —
      2026-11-01 사용자 결정). 탭 줄이 문서에 `beforeunload` 처리기를 하나 걸고(`installUnloadGuard` — `window.__capaUnloadGuard`,
      걸고 풀지 않는다) 떠나는 순간 테마 단추의 저장 안 함 표지(`--capa-unsaved-edits` — `theme_toggle.UNSAVED_EDITS_CSS_VARIABLE`,
      `app.py` 가 `has_unsaved_scenario_changes()` 또는 탭 점으로 단다)가 '1' 일 때만 `preventDefault`·`returnValue` 로 묻는다.
      편집이 없으면 묻지 않는다. 테마 단추는 제 확인 창으로 이미 물었으므로 새로 읽기 직전에 부모 창에
      `theme_toggle.RELOAD_ASKED_FLAG`(`__capaReloadAsked`)를 달고 처리기는 그것과 열릴 때의 테마 키 맞추기 새로고침
      (`__capaThemeReloading`)을 보고 지나간다 — 두 번 묻지 않는다. 창의 글은 브라우저가 정한다(사이트 글을 싣지 못하고, Chrome
      은 그 문서에서 사람이 한 번이라도 누른 뒤에만 띄운다). 떠나기는 기다려 주지 않아 붙들 수 없다 — 칸 편집기에 쓰는 중(Enter
      전)인 글은 표지가 서기 전이라 묻지 않는다. Playwright 드라이버(`check_deploy_screens`·가이드 생성기)는 새 문맥·한 번
      들어가기라 이 창에 걸리지 않는다 — 편집을 남긴 채 같은 쪽에서 `goto`·`reload` 하는 드라이버는 `dialog` 를 받아 넘겨야 한다.
    - 묻기는 앞 회차 data 의 `leave` 로 정하므로, 편집표 칸을 쓰는 중이거나 막 적용(Enter)한 직후의 누름은 그 편집을 실은
      회차가 돌아올 때까지 붙든다(`page_tabs.js` 의 순수 구획 `<tabs-hold>` — 누를 때 포커스가 편집표였거나 마지막 편집표
      입력이 5초 안이면, 앱 회차가 끝나고 새 data 가 오거나 0.4초가 지날 때까지, 최대 `BUSY_MS`). 붙들지 않으면 확인
      없이 옮기고 편집이 말없이 사라졌다(E2E 결함). 편집표는 glide 격자(`stDataFrame`)와 칸 편집기 틀(`gdg-clip-region`),
      그리고 그림자 DOM Components v2 편집 칸(가용설비 현황 설비 마스터 표·오른쪽 칸과 기준 정보 · 생산 계획 · 접속 명단 편집 그리드
      `reference_grid_keys.GRID_HOST` · `plan_grid_keys.HOSTS` · `page_tabs.ACCESS_LIST_GRID_HOST`, 시나리오 목록 표 — `page_tabs.EDIT_HOST_KEYS`, 탭 줄 data
      `grids`)의 바깥 key 칸(`.st-key-<key>`)으로 알아본다(순수 구획 `<tabs-grid>`). 문서 capture 단계에서는 그림자 DOM 안
      칸 편집기의 focusin·keydown 대상이 호스트로 바뀌어 안쪽 클래스로는 맞지 않는다 — 빠졌을 때 설비 마스터 칸에 쓰는 중
      (Enter 전) 누른 테마 단추가 그 편집 회차(누름 뒤 약 0.1초)보다 먼저 와 확인 없이 새로 읽었다(E2E 결함 — 칸 편집기는
      초점이 표 밖으로 나가는 순간 보낸다). 초점이 나갈 때 보내 그 회차가 누름보다 늦게 오는 편집 칸을 새로 두면 그 key 를
      `EDIT_HOST_KEYS` 에 더한다(`equipment_master_grid` 의 key 와 같은지는 `test_page_tabs_assets` 가 본다). 탭 줄 밖의 떠나기인 머리 툴바의 테마 단추도 같은 붙들기를 지난다 — 탭 줄이 그릴 때마다
      `window.__capaLeaveGate`(`press` — 단추 pointerdown 에서 편집표 포커스를 적는다, `go(fn)` — 붙든 뒤 `fn` 을
      부른다, `hold(fn)` — 붙들었는지 돌려준다)를 걸고, 테마 단추는 붙들기가 끝난 뒤 그때의 저장 안 함 표지로 묻는다. 탭 줄이 없는 화면(부트스트랩 오류)은
      곧바로 묻는다. 붙든 동안 탭을 누르면 테마 누름은 버려지고 단추가 제 기다림 표지를 걷는다
      (`theme_toggle.LEAVE_HOLD_RESET_MS`). 칸 편집기에 쓰는 중(Enter 전)에 누른 Dark 가 표지가 서기 전에 묻지 않고
      새로 읽던 틈을 막는다(E2E #94·#101, 개선 거리 I4).
      사이드바 화면 링크도 같은 붙들기를 지난다(`S.onLink` — click 을 막았다가 그 회차 뒤 같은 링크를 다시 누른다, 상한 거름은 다시 누를 때 한 번) — 터치 톡은 초점이 빠지며 나간 표의
      출납 회차와 거의 함께 닿아 그 회차가 지금 화면 주소로 돌며 이동을 덮었다(2026-11-07 E2E). 링크 누름도 탭 줄과 같은 떠나기 확인(`leave` — 가용설비 현황 작은 편집표 둘 포함)을
      다시 누를 때 한 번 묻는다(취소하면 상한 거름의 열기 표지를 되돌린다, 지금 화면의 링크는 묻지 않는다). 떠나는 누름은 모두 붙들기 판정 전에 떠나기 신호 `capa-leaving` 을 쏘고
      명부의 편집기가 busy 면 손을 뗀 지 오래된 누름도 붙든다(9장 「구역 회차 규칙」 R8 — busy 였다가 걷힌 붙들기는 새 data 를 0.4초 기다리지 않고 회차 끝 뒤 조용함 `HOLD_QUIET_MS` 를 기다린다). 붙든 누름(탭 · 닫기 · 테마 · 링크)은 누른 때의
      주소(`path`)를 들고, 놓을 때 주소가 달라졌으면 보내지 않고 버린다(`holdVerdict` 의 `drop`) — 지나 보낸 뒤로가기 · 본문 `st.switch_page` 는 붙듦을 비우지
      않아, 다시 누르기가 옮겨 간 화면을 덮었다(2026-11-07 E2E).
    - **뒤로 · 앞으로 지킴이**(`page_tabs.js` 의 순수 구획 `<tabs-nav>` · 거는 구획 `<tabs-nav-install>`, 2026-11-23 — 편집기에서 고친 뒤 브라우저
      뒤로를 누르면 그 편집이 말없이 사라지던 결함). Streamlit 1.63 은 `popstate` 를 받자마자 앱 칸 값만 실은 이동 요청을 보낸다 — 그 처리기가 탭 줄보다
      먼저 걸려 캡처 단계 popstate 처리기로도 막지 못하고(이동 요청이 이미 나간 뒤다), 뒤로는 초점을 옮기지 않아 칸 편집기가 쓰던 글을 확정하지 않는다.
      그래서 묶음 창 안의 op · 열린 칸 글이 서버에 가기 전에 화면이 바뀌었다. 탭 줄이 그릴 때 문서에 Navigation API `navigate` 처리기를 하나 걸고
      (`installNavGuard` — `window.__capaNavGuard`, 걸고 풀지 않는다, `window.navigation` 이 없으면 걸지 않는다) 같은 문서 · 막을 수 있는 `traverse`
      만 손댄다 — traverse 가 아님 · `cancelable` 거짓 · 다른 문서 · 같은 화면의 해시만 다름은 지나 보낸다. 손댈 때는 막기 전에 정한다: 깊은 활성 요소가
      편집표(`<tabs-grid>`) 안이면 먼저 `blur()`(칸이 제 focusout 길로 확정해 보낸다) → 사건 때의 `window.__capaLeaveGate.hold(fn)`(떠나기 신호 · 붙들기 —
      탭 줄 · 테마 단추 · 사이드바 링크와 같은 함수, 새 길을 두지 않는다)에 묻고, 기다릴 것은 없어도 떠나면 사라지는 편집(`gate.loses` — data `leave`)이
      있으면 곧바로 놓는 붙들기로 둔다. glide 칸 편집기(`st.data_editor` — 작은 편집표 · 입력 비가동 · Space 층 사용 편집 등, 틀 `.gdg-clip-region`)는
      blur 로 확정하지 않는다 — 문서 capture 단계 바깥 누름(`pointerdown` · `contextmenu`)과 Enter · Tab 으로만 확정한다(Streamlit 1.63
      `data-grid-overlay-editor`). 탭 줄 누름은 그 pointerdown 이 확정하지만 뒤로는 누름이 없어 쓰던 글이 확정 없이 사라졌다(사외 시범 — 입력 비가동
      칸, 칸 입력 창을 넘긴 뒤면 붙들지도 않았다). 그래서 활성 요소가 그 틀 안이면 body 에 바깥 누름
      (`PointerEvent`, 없으면 `Event`)을 보내 지금 값으로 확정시키고(glide 는 격자로 초점을 돌린다) 그 초점도 뺀 뒤 `gate.blurred(typed)` 를 부른다 — 코드
      blur 는 focusin 이 없어 탭 줄 초점 표지(`gridFocused`)를 지금 활성 요소로 다시 맞추고(남으면 다음 탭 · 링크 · 테마 누름이 까닭 없이 0.4초
      붙든다), 칸 편집기를 닫았으면 쓰는 중에 누른 것(`pressFromGrid`)으로 적어 칸 입력 창(`EDIT_MS`)을 넘겨 쓰던 글도 붙든다. 격자에만 초점이 있으면
      바깥 누름도 붙들기 표지도 없다(쉬는 표의 지연 0 그대로). 탭 고르기가 날아가는 동안(`<tabs-queue>` 의 `flight` — 보낼 때 이미 떠나기 확인을
      지났다) 그 고르기가 물은 떠나기 글과 같으면 `loses` · `ask` 는 다시 묻지 않는다(`navLeaveAsked` — 그 고르기가 닿기 전 탭 줄 data 는 옛 화면
      것이라 같은 편집을 또 물었다). 붙들었을 때만 `preventDefault` 한다 — 쉬는 편집기 · 열린 칸 없음이면 지연이 없다. 놓이면(ack · 회차 끝, 길어야
      `BUSY_MS`) 탭 줄과 같은 떠나기 확인(`gate.ask` — `leaveOk`, 떠나면 사라지는 편집이 있을 때만 묻는다)을 지나 표지(목적지 key)를 달고
      `navigation.traverseTo(key)` 로 다시 간다 — 표지가 맞는 사건은 지나 보내며 걷는다. 취소면 아무것도 하지 않는다(이미 막았으니 주소 · 본문 그대로).
      다시 가기가 거절되면 표지를 걷고 `history.go(delta)` 로 한 번(칸 차이를 모르면 — `delta` 0 — 부르지 않는다, `go(0)` 은 새로고침이라 지키려던
      편집과 그 접속의 편집이 모두 사라진다), 그것도 안 되면 끝이고, 표지는 다시 간 이동이 닿거나 약속이 끝나거나
      `NAV_REPLAY_MS` 가 지나면 걷는다(남으면 같은 칸으로 가는 다음 뒤로를 놓친다). 붙든 동안 또 온 traverse 는 막고 붙들기에 다시 묻는다 — 목적지는
      마지막 것 하나이고 붙들기도 하나다(탭 · 링크 누름이 붙들기를 갈아 끼웠으면 낡은 몫은 놓여도 번호가 달라 아무것도 하지 않는다 — 지금 탭이 아닌
      탭 닫기는 화면을 떠나지 않아 붙듦을 버리지 않는다). 막을 수 없는 이동(사용자 활성 없이 잇달아 누른 브라우저 뒤로 등)이 지나가면 기다리던 다시
      가기를 걷는다. 브라우저 UI 의 뒤로(툴바 · `Alt+←`)를 막으면 그 창의 기록 이동 활성을 써 버리므로(HTML 규격) 페이지를 다시 누르지 않고 곧바로 또
      누른 브라우저 뒤로(붙든 동안 거듭 누름 · 확인을 취소한 뒤 다시 누름)는 막을 수 없게 와서 지나갈 수 있다(그때 잃는 것은 지킴이 전과 같다).
      Navigation API 가 없거나 사건을
      막을 수 없으면 지금처럼 지나 보낸다(나빠지지 않는다 — 사내 Chrome · Edge 는 API 가 있다, 사외 시범은 Chrome 하나). 상한 거름은 지나지 않는다(아래
      `route_page_tabs` 되돌림 그대로).
    - **붙들기가 끝난 뒤 떠나는 화면이 보내는 메시지는 서버가 거른다**(`stale_page_guard`, 2026-11-19 — 칸을 고치자마자 누른
      화면 탭이 Space 로 되돌아오던 수). 편집표가 고친 칸을 바탕 표에 접어 다시 그리는 화면(Space 층 사용 편집 · 입력
      비가동)은 그 편집 회차가 끝난 뒤 프런트 편집표가 바탕과 같아진 편집을 걷고 걷은 상태를 0.15초 뒤에 한 번 더 보낸다
      (Streamlit 1.63 `st.data_editor` — 회차 표지로는 보이지 않는다). 붙들기는 편집 회차의 끝까지만 기다리므로 그 사이 나간
      고르기 · 링크 이동 뒤에 이 메아리가 떠나는 화면 주소(프런트는 옮긴 화면의 `new_session` 을 받기 전까지 앞 화면을
      싣는다)로 가, 옮긴 화면 회차를 끊거나(옮긴 화면이 이미 섰음) `st.switch_page` 요청과 합쳐져 주소를 덮었다(아직 서기
      전) — 합성 표본 사본에서 칸을 고치자마자 누른 탭이 사유를 친 채 · `Enter` 직후 · 사용 칸 Space 모두에서 Space 에 남았다
      (JS 는 옮긴 화면의 data 를 기다리다 `BUSY_MS` 동안 다음 누름까지 줄 세웠다). 붙들기를 시계로 늘리지 않는다(느린 PC 에서
      다시 샌다) — `app.py` 회차 맨 앞에서 「이번 회차 화면이 들인(또는 탭이 옮기러 간) 화면과 다르고 그 화면 본문 위젯의 값을
      실었는가」 로 가르고(프런트의 옮기는 요청 — 사이드바 링크 · 뒤로·앞으로가기 — 는 앱 칸 값만 싣는다) 옮겨 간 화면으로
      다시 보낸다. 떠난 화면 위젯 콜백(편집표 `on_change` 의 초안 접기)은 Streamlit 이 그 앞에서 돌려 고친 칸은 남는다.
      `st.navigation()` 앞이라 떠난 화면 주소가 기록에 쌓이지 않고, 옮긴 화면이 이미 섰던 갈래는 본문이 한 번 다시 선다.
      탭 고르기 · 지금 탭 닫기 · 알림 칸 「그 화면으로」 · 사이드바 링크 모두 이 한 판정이다. 페이지 본문이 스스로 부르는
      `st.switch_page`(HOME 칸 · 다음 화면 단추)는 옮기러 간 화면을 적지 않는다 — 그 회차가 서기 전에 합쳐진 메아리만 남는다.
      사이드바 링크도 서버가 옮기러 간 화면을 미리 모른다 — 링크 요청이 회차를 세우기 전에 메아리와 합쳐지는 갈래는 남는다(붙들기가
      편집 회차 끝까지 기다려 링크 요청은 쉬는 서버에 닿아 곧바로 선다 — 합성 표본 60번에서 보지 못했다).
    - 탭 줄은 페이지보다 먼저 그리므로 「이번 회차에 그 편집표를 그리는가」 를 위젯 값으로 미리 본다 — 작은 편집표는 바깥 탭이
      ① 이고 표 고르기(`equipment_data_workspace.MASTER_TABLE_KEY`)가 그 표일 때만 센다. 고르기를 바꾼 회차에는 편집표 위젯
      상태가 회차 끝까지 세션에 남아, 그대로 세면 이미 사라진 편집에 「사라집니다 — 떠날까요?」 를 한 회차 동안 물었다.
      편집표를 숨기는 고르기를 새로 두면 판정에 그 고르기를 같이 넣는다.
  - 새로 읽은 문서의 「설비 시나리오가 공식으로 돌아왔습니다」(순수 구획 `<tabs-return>`) — 문서를 떠날 때(`pagehide`, 문서에
    처리기 하나) 떠나는 까닭에 맞는 띠 CSS 변수(테마 단추면 `--capa-equipment-return` — `app_header.EQUIPMENT_RETURN_VARIABLE`,
    새로고침이면 `--capa-equipment-return-reload` — `EQUIPMENT_RELOAD_RETURN_VARIABLE`)에 이름이 있으면 탭의
    `sessionStorage`(`capa-equipment-return`)에 `{label, cause}` 를 적고, 새 문서의 첫 그리기에서 한 번 알림 칸(오른쪽 아래
    알림창 · Alarm — 코드 `TAB-02` 새로고침 · `TAB-03` 테마 전환, 단계 「확인 필요」 15초)에 낸다(전문 `TEXT["returned"]`·
    `TEXT["themed"]`, 짧은 글 `RETURN_SHORT`·`THEME_RETURN_SHORT`). 알린 칸은 3초 뒤 지운다 — 그 전에 문서가 떠나면(테마 키 맞추기 새로고침) 다음
    문서가 다시 알린다. 떠날 때 이름이 없으면 적지 않는다(알리기 전에 떠난 문서의 몫을 지우지 않는다). 테마 단추의 표지
    (`theme_toggle.THEME_SWITCH_STORAGE_KEY`)는 떠날 때 읽고 지우며, 탭 줄이 없던 문서(부트스트랩 오류)에서 눌러 남은 표지는 새
    문서의 첫 그리기가 지운다 — 남기면 그 문서의 다음 새로고침을 테마 전환 글로 알린다.
  - 기록 한 칸(`page_tabs.js` 의 순수 구획 `<tabs-history>`, `tests/test_page_tabs_assets.py` 가 node 로 돌린다) — 문서의
    `history.pushState` 를 한 번 감싸(`window.__capaHistoryGuard`) 지금 경로와 같은 경로의 쌓기를 **늘** 칸
    바꾸기(`replaceState`)로 돌린다. 거는 것(`<tabs-history-install>` 의 `installHistoryGuard`)은 회차 맨 앞의 입장 화면
    JS 가 모듈을 읽는 순간 먼저 하고(`history_guard.py`) 탭 줄은 안전망으로 부른다 — 탭 줄은 페이지 바로 앞이라, 새 브라우저
    탭으로 링크 인자 화면에 들어오면 첫 회차의 인자 지우기가 탭 줄 JS 보다 먼저 닿아 기록이 한 칸 더 쌓였다(2026-10-26 E2E). Streamlit 1.63 프런트는 서버의 주소 인자 바꾸기(`page_info_changed`)마다 지금 경로로
    한 칸 쌓는다 — `st.switch_page` 가 떠나는 화면 경로로 먼저 쌓는 한 칸, 링크 인자를 받아 지우는 화면이 인자 달린 칸
    뒤에 또 쌓는 칸(뒤로가기로 인자 달린 칸에 닿으면 다시 지우며 또 쌓아 그 화면을 떠나지 못했다). 걸고 풀지 않는다.
    `st.switch_page` 의 첫 쌓기는 떠나는 칸 주소를 옮길 화면 인자로 바꾸므로(HOME 칸 → `/?process=…&from=home`), 인자를
    지우지 않은 칸 바꾸기 뒤 `LEAVE_MS`(1초) 안에 같은 인자로 다른 경로를 쌓으면 떠나는 칸을 원래 주소로 되돌리고 쌓는다 —
    남겨 두면 뒤로가기로 돌아온 그 칸에서 사이드바로 옮길 때 그 인자가 따라가 링크처럼 적용됐다. 인자를 지운 칸 바꾸기는
    되돌리지 않는다.
  - 화면을 옮기는 누름(다른 탭 고르기·지금 탭 ×)은 트리거를 보내기 **전에** 누름 기다림을 건다(순수 구획 `<tabs-queue>`).
    한 번에 하나 — 옮긴 화면의 탭 줄(지금 탭이 바뀐 data)이 오고, 그 회차가 다 돌거나(Streamlit 뿌리 `stApp` 의
    `data-test-script-state`) 탭 줄이 온 뒤 `MOVED_GRACE_MS`(1초)가 지나기 전에 누른 탭은 보내지 않고 마지막 하나만
    기다렸다 보낸다(`BUSY_MS` 가 지나면 그때 보낸다). 옮기기 전에 보낸 누름은 프런트가 아직 떠나는 화면에 있다고 믿고 그
    화면 주소로 회차를 청한다. 회차 끝까지만 기다리면 옮긴 화면이 오래 돌 때(HOME 첫 계산) 누른 탭이 그 계산과 브라우저
    그리기(사외 사본 약 2초 — 그동안 프런트 표지가 「돈다」)가 끝날 때까지 묶였다(사내 리뷰 202610271800 발견 3). 회차가 도는
    중에 보낸 누름도 서버는 곧바로 새 회차로 받는다 — `runner.fastReruns`(기본 켜짐)는 돌던 회차에 멈춤만 걸고 새 회차를
    세우며, 돌던 회차는 다음 메시지·`st.session_state` 자리에서 멈춘다(HOME 은 그림 묶음을 넣고 꺼낼 때마다 세션 칸을 읽는다).
    그래서 무거운 화면에 끊는 자리를 따로 둘 일은 없다. 남는 한계는 Streamlit 캐시의 키별 계산 잠금이다 — 돌던 회차가 아직
    계산 중인 캐시 값(같은 시나리오의 대당 Capa 등)을 새 화면도 쓰면 그 계산이 끝날 때 함께 받는다. 다른 탭 닫기·고정은
    기다리지 않는다.
  - **앞 회차 끝 직후의 고르기는 닿지 않을 수 있다 — 한 번 다시 보낸다**(`<tabs-queue>` 의 `lostSelect` · `resendTarget`).
    1.63 프런트는 `script_finished` 를 받으면 그 그리기를 마친 뒤 지금 요소에 없는 위젯 칸을 지운다
    (`removeInactiveWidgetState`). Components v2 트리거 칸(`…__events`)은 요소 id 가 아니라, 그 사이(끝을 받은 뒤 CPU 1배
    약 5~10ms · 4배 약 25ms)에 쓴 트리거는 회차 요청(`setTimeout` 0 뒤)이 나가기 전에 지워진다 — 요청은 트리거 없이 나가
    서버는 지금 화면을 다시 돌았고, 탭 줄은 옮긴 화면을 `BUSY_MS` 기다리다 말없이 놓았다(모듈 단추 · Capa Chatbot 추천
    질문 직후의 탭, 2026-11-20 측정 T1). 차례 묶음의 받음 번호(`seq` · `MOVE_LOST_MS`)는 차례 그림만 다시 담고 고르기는
    다시 보내지 않으며, 트리거 없는 회차는 같은 data 라 탭 줄이 다시 불리지도 않는다. 그래서 탭 줄이 뿌리 회차 표지
    (`data-test-script-state`)가 바뀐 때를 `MutationObserver` 로 적고(100ms 마다 보는 `settle` 은 수십 ms 회차를 놓친다),
    보낸 뒤 선 회차가 끝나 `LOST_QUIET_MS`(0.6초) 동안 조용한데 옮긴 화면의 탭 줄이 오지 않았으면(보낸 뒤 표지가 한 번도
    바뀌지 않았으면 `LOST_IDLE_MS` 2초) 그 사이 누른 마지막 탭, 없으면 그 고르기를 한 번만 다시 보낸다. 닿은 고르기는
    `st.switch_page` 로 그 회차를 일찍 끝내 옮긴 화면 회차가 곧 서고 그 사이 「돌지 않음」 은 회차 끝 GC 한 번이다.
    주소가 바뀌었으면(뒤로가기 · 링크) 보내지 않고, 화면은 그대로라 앞서 물어 지나온 떠나기는 다시 묻지 않는다. 같은
    고르기를 두 번 받아도 서버는 같은 화면으로 옮길 뿐이다(`_on_select` — id 로 정한다). 지금 탭 닫기 · 고정 · 차례는
    다시 보내지 않는다.
  - 닫기·고정 누름은 곧 목록을 움직인다(닫은 탭은 누르자마자 숨겨 이웃이 당겨 오고, 고정한 탭은 다음 data 에서 왼쪽으로
    간다). 그 뒤 `DOUBLE_PRESS_MS`(0.5초) 안에 `DOUBLE_PRESS_PX`(8px) 안의 같은 자리로 온 포인터 누름이 **다른 탭**에 닿으면
    버린다(순수 구획 `<tabs-press>`) — × 더블클릭의 둘째 누름이 밀려 온 이웃 탭을 닫거나(같은 프레임의 'close' 둘은 마지막
    것만 서버에 닿아 누른 탭은 남았다) 지금 탭을 고정했다(2026-10-26 E2E). 같은 탭의 둘째 누름(핀 두 번)과 키보드 누름
    (`detail` 0 — 좌표가 없다)은 그대로다.
  - 상한(10개) — JS 가 사이드바·본문 화면 링크(`stPageLink-NavLink`) 누름을 문서 capture 단계에서 먼저 받아, 열린 탭이
    아닌 화면이면 막고 알린다(data 의 `max`·`pages` — 모든 화면의 주소 → 탭 이름). 알림은 탭 줄 칸이 아니라 같은 문서의
    알림 칸에 낸다(코드 `TAB-01`, 단계 「조치 필요」 — `page_tabs.js` 의 `raiseAlert` → `window.__capaAlerts.raise`, 알림
    칸이 아직 서지 않았으면 `window.__capaAlertQueue`). 옛 탭 줄 알림 칸(`.capa-tabs-notice`)은 걷었다 — 한 칸이라 뒤 알림이
    앞 알림을 덮었다. 알림 칸 「그 화면으로」 는 `capa-open-page` 사건({href, opened})으로 와 탭 줄 이동 길을 탄다(열린 탭이면
    `select` — 떠나기 확인 · 한 번에 하나, 아니면 그 화면 링크 누름 — 상한 거름). 그 누름의 이동을 실제로 보낼 때(이미 그 탭이거나
    그 탭으로 가는 중이면 곧바로)만 `opened` 를 부르고 붙들기 · 줄 서기를 지나도 그 누름의 것만 들고 간다(`S.waitOpen` · `S.linkOpened`)
    — 알림 칸이 그때만 닿은 화면에서 탭 길 · 대상을 잇는다. 지나 보낸 링크가 여는 탭은
    그 탭이 data 에 올 때까지(같은 `epoch`, 길어야 `BUSY_MS`) 열린 탭으로 센다(순수 구획 `<tabs-links>`) — 세지 않으면 탭
    9개에서 링크 둘을 0.05~0.1초 간격으로 누를 때 둘째 누름이 앞 회차 data 의 탭 9개로 세어 거름을 지났고, 서버 되돌림이
    두 화면을 기록에 쌓아 뒤로가기가 갇혔다(2026-10-27 E2E). 그래도 들어온 이동(뒤로·
    앞으로가기 — 뒤로 지킴이는 편집을 보내려 붙들 뿐 상한으로 거르지 않는다)은 `route_page_tabs` 가 직전 화면으로 되돌리고
    HOME 칸 전달 칸을 버린 뒤 탭 줄 아래에 알린다. 이 되돌림은 기록을 쌓으므로 정상 길로 쓰지 않는다. 탭 데이터에는
    2단계(떠 있는 창) 대비로 화면 주소(`href`)를 싣는다.
  - 핀 단추 이름은 고정 여부와 상관없이 「… 고정」 하나이고 상태는 `aria-pressed` 가 말한다. 지금 탭이 아닌 고정 안 한 탭의
    핀은 가리킬 때만 보이고 숨은 동안 누름을 받지 않는다(`pointer-events: none` — 터치로 탭 이름 오른쪽을 누르면 고정이
    됐다). 가리킬 수 없는 기기(`hover: none`)에서는 그 핀을 두지 않는다. 640px 이하 창에서는 고정하지 않은 지금 탭의 핀도
    두지 않는다(이름 자리). 지금 탭은 줄지 않는다(`flex-shrink: 0` — 이름이 다 보이는 제 폭, 길어야 15rem) — 탭이 많아 모두
    최소 폭(5.5rem)으로 줄면 지금 탭 이름이 핀·× 에 밀려 「A.」 로 줄었다. 지금 탭 최소 폭을 넓히지는 않는다 — 탭이 적을
    때도 HOME 처럼 짧은 지금 탭이 넓어져 탭을 옮길 때마다 뒤 탭들이 옆으로 밀렸다. 고정 탭도 줄지 않는다(같은
    `flex-shrink: 0`) — × 가 없고 핀이 늘 서서 내줄 닫기 자리가 없어 1600px · 탭 10개 · 지금 탭이 구현 중일 때 HOME 이
    「H…」 로 잘렸다(통합 재측정).
  - 목록이 옆으로 넘치면 탭이 더 있는 쪽 가장자리를 흐리고(목록 `mask-image`, 2rem) 누름을 받지 않는 화살표 표지를 단다
    (`page_tabs.js` 의 순수 구획 `<tabs-edges>` 가 `has-more-start`·`has-more-end` 를 정한다 — 굴릴 때·목록 폭이 바뀔 때·data
    가 바뀔 때). 지금 탭을 보이게 굴릴 때는 흐림 폭만큼(`EDGE_PX`) 띄운다(같은 구획의 `revealScroll`). 지금 탭까지
    굴리는 것은 탭을 옮길 때와 **목록 폭이 바뀔 때**(`ResizeObserver` — 사이드바 접기·펴기, 창 폭)다 — 폭만 바뀌면 굴린
    위치가 그대로라 지금 탭이 목록 밖에 남았다(2026-10-30 E2E). data 가 다시 올 뿐이면 사람이 굴려 둔 위치를 둔다.
  - 키보드 초점은 탭 줄 안에 남긴다(순수 구획 `<tabs-focus>`) — 키보드 초점(`:focus-visible`)이 있던 탭을 닫으면 숨기기
    전에 이웃 탭(서버가 지금 탭을 닫고 옮겨 가는 이웃과 같은 규칙 — 오른쪽, 없으면 왼쪽)으로 옮기고(마우스로 누른 × 는
    옮기지 않는다 — 이웃 탭의 숨은 핀이 `:focus-within` 으로 드러나 남았다), 키보드(`click` 의 `detail` 0)로 옮긴
    화면이 다 선 뒤 초점이 body 로 빠졌으면 — 그 사이 다른 키·포인터 입력이 없을 때만 — 지금 탭으로 돌려준다. 기다리던
    누름은 옮긴 화면 회차가 끝나기 전에도 보내므로(`MOVED_GRACE_MS`) 초점은 그 회차 끝을 따로 기다린다(길어야 `BUSY_MS`).
    로빙 tabindex(탭마다 Tab 세 번 멈춤 줄이기)는 아직이다(TODO — 끌기의 키보드 대안이 화살표 홀로를 비워 두었다).
  - **화면을 옮기지 않는 누름은 페이지를 다시 돌리지 않는다**(2026-11-02 사용자 요청 — 핀 고정에 HOME 진행 막대가 떴다). 고정·
    끌어서 차례·지금 탭이 아닌 탭 닫기는 JS 가 누르자마자 서버와 같은 규칙(순수 구획 `<tabs-order>` — `pinned_to`·`moved`·
    `closable`·`arranged` 와 같은 표를 node 시험이 맞댄다)으로 탭 줄을 고쳐 그리고, 그린 차례(`order`)·고정(`pins`)·그림
    번호(`seq`)를 트리거에 싣는다(차례 바꾸기는 아래 「묶어 보낸다」). 콜백은 그 차례를 목록에 입힌 뒤(`_adopted` —
    `arranged`, 고르기·닫기도 같다) 마지막 줄 `_settle_drawn` 이 서버 목록과 같으면 상자 여닫기와 같은 빈 프래그먼트만 다시 돌리고
    (`rerun_fragment_if_alone(SIDEBAR_TOGGLE_FRAGMENT_KEY, PAGE_TABS_COMPONENT_KEY)` — 직전 앱 전체 회차가 끝나지 않았거나 다른
    위젯도 바뀌었으면 앱 전체 회차), 다르면 `resync_strip` 으로 epoch 를 올려 앱 전체 회차의 data 로 다시 그리게 한다. 탭 줄
    data 는 다음 앱 전체 회차가 같은 목록으로 싣는다. 사본 측정(HOME, 고정·풀기 12번) — 바탕 델타 258 · 진행 막대 12/12 · 본문
    흐림 표지 12/12(약 0.1초) → 델타 1 · 막대 0/12 · 흐림 표지 5/12(한두 프레임 — 콜백 회차가 앱 전체 회차로 시작하는 틈, 상자
    여닫기도 같다). 다른 탭 고르기·지금 탭 닫기는 화면을 옮기므로 앱 전체 회차 그대로다. 지금 탭이 아닌 탭을 닫으면 JS 가 그
    `li` 를 숨기기만 해(`hidden`) 다음 앱 전체 회차까지 DOM 에 남는다 — 탭 줄을 세는 드라이버(`check_deploy_screens` 의
    `page_tabs()`·`tab_item`)는 둘 다 숨긴 탭을 빼고 센다(숨긴 탭까지 센 `tab_item` 이 둘째 닫기부터 숨은 탭을 집어 30초
    기다리다 끝났다 — 2026-11-02 반박 검토).
  - **고정하지 않은 탭은 끌어서 차례를 바꾼다**(순수 구획 `<tabs-drag>`, 2026-11-02 사용자 요청). HTML5 끌어 놓기가 아니라
    포인터 이벤트다 — 마우스·펜은 가로 `DRAG_SLOP_PX`(5px)를 넘어야 끌기이고(그 전의 누름은 고르기·고정·× 그대로, 세로만
    움직이면 끌지 않는다 — 세로 떼어 내기는 떠 있는 창 몫), 터치는 `TOUCH_HOLD_MS`(350ms) 길게 누른 뒤에야 끌기다(그 전에
    움직이면 목록 굴리기). 끄는 동안 그 탭이 포인터를 따라가고(`translateX`) 놓을 자리에 세로 막대(`.capa-tabs-drop`)가 서며,
    목록 가장자리(`EDGE_PX`)에서는 목록을 굴린다. 놓을 자리는 고정 탭 수 아래로 내려가지 않는다. 끄는 탭이 끝(고정 묶음 바로
    뒤·목록 끝)에 묶이면 그 끝 자리이고(`dragLeft` 의 `bound`), 그 사이는 끄는 탭 가운데가 지난 다른 탭 가운데 수다(`dropSlot`) —
    가운데만 보면 끄는 탭이 이웃보다 넓거나 같을 때(넘친 줄은 탭이 같은 폭으로 준다) 끝 자리에 못 놓였다(2026-11-02 반박
    검토). 놓을 때 DOM 차례를 한 번 바꾸고 그 그림을 묶음에 담는다(아래 「묶어 보낸다」). Esc·포인터 취소는
    제자리, 끈 뒤 `DRAG_CLICK_MS` 안의 click 은 고르기로 보내지 않는다(화면을 옮기지 않는다). 그 창은 놓은 자리의 포인터
    click 몫이다 — 새 포인터 누름(`pointerdown`)이 창을 닫고(놓은 자리의 click 이 오지 않은 끌기가 다음 × · 핀 · 고르기를
    삼키지 않게) 키보드로 누른 단추(`detail` 0)는 거르지 않는다(`dragClick` 의 `detail`). Esc·끄는 중 새 data 로 접은
    끌기는 포인터가 아직 눌려 있어 그 포인터를 놓는 순간부터 같은 창을 다시 연다(`heldRelease` — 창 처리기 `RELEASE_EVENTS`
    는 그동안만 단다). 접은 시각부터만 세면 손떨림 뒤 0.4초 넘어 놓은 click 이 그 탭으로 화면을 옮겼다. 끄는 중 새 data 가
    오면 끌기를 접는다. 키보드 대안은 고정하지 않은
    탭 단추의 `Ctrl+Shift+←/→`(한 칸, 고정 묶음을 넘지 않음 — 단추에 `aria-keyshortcuts`, 옮긴 뒤 `role="status"` 칸에
    「… 탭을 n번째로 옮겼습니다」)이고, 초점은 옮긴 탭에 남는다. 차례는 다른 탭 상태처럼 세션에만 산다.
  - **차례 바꾸기는 묶어 보낸다**(순수 구획 `<tabs-batch>`, 2026-11-03 사용자 검수 frame-u03 — 「몇 번 연속으로 좌우로
    움직이는 경우 불필요한 로딩이 발생하거나 멈추는 경우」). 끌기·키보드 한 칸은 곧바로 다시 그리고(`arrange`) 그 그림을
    담기만 한다(`dueMove`). 서버에는 마지막 그림만 쉼(`MOVE_SEND_MS` 0.4초 — 새로 옮기면 다시 잰다) 뒤, 앱 회차·화면을 옮기는
    누름(`<tabs-queue>` 비행)·붙든 누름·끌기가 없을 때(길어야 `BUSY_MS`) `move`(`{order, pins, seq}`)로 한 번 보낸다
    (`flushMove`). 서버가 아는 차례(`knownOrder` — data 가 아직 따라오지 않은 보낸 그림, 없으면 data)와 같으면 보내지 않는다
    (왼쪽 갔다 되돌아옴). 고정·닫기는 늘, 고르기는 담긴 그림이 있을 때 지금 그림과 번호를 함께 실어(`claimDrawn`) 담긴 차례를
    데려간다 — 서버는 어느 트리거든 그 차례를 먼저 입힌다(`_adopted`). 닫기는 숨기기 전에 그림을 담아 닫는 탭이 제자리에
    있다 — 지금 탭을 옮긴 직후 닫아도 이웃은 보이는 차례의 오른쪽 이웃이고(`closed` 는 입힌 목록에서 고른다), 지금 탭이 아닌
    탭 닫기는 그 탭을 뺀 그림으로 맞대 빈 프래그먼트만 돈다(`_on_close`). 한 칸씩(`{id, before}`)이 아니라 그림 전체라 그 사이 빠진
    누름이 있어도 마지막 그림이 선다. data 는 서버가 받은 마지막 번호(`seq`)를 싣고, JS 는 그보다 뒤에 보낸 그림·담긴 그림을
    새 data 목록에 입혀 놓는다(`shownOrder` — 처음부터 그 차례로 놓아 옮기던 탭의 초점이 data 차례로 밀렸다 돌아오며 빠지지
    않는다). 받은 흔적 없이 `MOVE_LOST_MS`(2초) 지난 data 가 오면 다시 담아 보낸다. 고치기 전(바탕 6aef702)은 누를 때마다
    `move` 를 보내 누름마다 앱 전체 회차가 서고(빈 프래그먼트로 바뀌기 전의 틈 — 프런트가 본문 전체를 흐림 표지로 둔다) 회차 끝
    GC(`runner.postScriptGC`)를 두 번 돌려 서버가 누름을 따라가지 못했다. 회차가 도는 중에 보낸 트리거는 가끔 빈 채로 닿아
    (프런트 요청에 트리거 칸이 비었다) 앱 전체 회차로 HOME 을 다시 돌리고 그 누름을 잃었다. 사본 측정(검수 샘플 DB · 헤드리스
    Chrome, 탭 7개 HOME): 150ms 간격 8번 — 회차 요청 8 → 1, 앞 꼴 8번 되풀이에서 HOME 진행 막대 5/8(길게 2.8초)·마지막
    차례 틀림 3/8 → 0/8 · 0/8, 50ms 간격 20번 — 요청 20 → 0(제자리로 끝남), 회차 표지 0.7~1.4초 → 0, HOME 이 도는 중의
    누름 100ms 6번 — 진행 막대 2.5초 → 0. 화면 확인 `page_tabs_frame` 이 「키보드 5번 회차 1 · 차례·초점 맞음」 을 본다.
- `src/capa_simulation/components/theme_toggle.py` — 헤더 툴바 슬롯에 밝게/어둡게 버튼을 얹고, 툴바·사이드바
  머리칸에 단추를 다는 다른 스크립트(Guide·Print·사이드바 라벨·터치 스크롤·HOME 칸 둘째 누름 거름·꺼진 링크 표지)를 같은 iframe 에
  싣는다(`extra_scripts`).
  - 앱 안 테마 전환 API 가 없어 `localStorage` 테마 키를 적고 새로고침한다. 정본은 앱 키 `capa-theme`
    (`THEME_APP_KEY`), 규칙은 `THEME_RULE_SCRIPT`(`capaTheme`) 한 벌이고 다른 스크립트는 이것만 부른다.
    저장소(`localStorage`)가 막힌 브라우저는 키를 적지 못해 `?theme` 만 밝게 맞춘다 — 그런 브라우저에서 OS 가 어두울 때 생기는 테마 어긋남은 고치지 않는다.
  - 열릴 때의 새로고침(키를 고쳐 적었거나 `?theme` 이 다를 때 — `reloadOnOpen`)은 **문서를 연 주소**에서 빠진 인자를
    되살린다(`<theme-reopen>`, 연 주소는 `performance` 탐색 항목 — `history.replaceState` 로 바뀌지 않는다). 버려지는 첫
    세션도 링크 인자를 받아 주소에서 지우므로(Space `?layer=short…`·공정 Capa 상세 `?process=…`·제약 시뮬레이션), 지금
    주소에 테마만 붙이면 그 지우기가 먼저 닿은 때 새 세션이 링크 없이 열렸다(E2E 결함 — 사본 CPU 6배 느리게 9번 중 8번).
    같은 출처·경로일 때 빠진 이름만 싣고 지금 주소의 값은 그대로 둔다. 단추를 눌러 바꿀 때(`syncParam`)는 지금 주소
    그대로다. node 로 스크립트 셋을 가짜 부모 창에서 돌리는 시험이 `tests/test_theme_reopen_link.py` 다.
  - 툴바 차례는 `TOOLBAR_BUTTON_ORDER` 한 벌(공정 칩 · 합성 샘플 · 「정본 아님」 · 변경 칩 · 「공지」 칩 · Guide · Alarm · Print ·
    테마 — 2026-11-03, 2026-11-09 보드 C1 (라) · T8 로 맨 앞 둘을 더함, 2026-11-14 「앱 대신 뜨는 화면」 보드 d13 (가) 로 합성
    샘플 다음에 「정본 아님」, 2026-11-17 공지 보드 답 q-look 으로 Guide 바로 왼쪽에 「공지」 칩. 공정 칩 `PROCESS_CHIP_ID` ·
    합성 샘플 `SAMPLE_MARK_ID` · 「정본 아님」 `CANON_MARK_ID` · 변경 칩 `CHANGES_CHIP_ID` · 「공지」 칩 `NOTICE_CHIP_ID` · Alarm
    `ALARM_BUTTON_ID` 는 알림 칸 JS 가 세운다), 선택자 상수(`TOOLBAR_SLOT`·`THEME_BUTTON_ID`·
    `SIDEBAR_HEADER_SLOT`)는 이 모듈 한 곳이다. iframe 내용은 회차마다 같아야 한다(`tests/test_theme_toggle.py`).
  - 툴바에 단추를 더하거나 바꾸면 `TOOLBAR_BUTTON_ORDER`(와 `check_deploy_screens.TOOLBAR_LABELS` — 바뀐 것이 있을 때만
    서면 `TOOLBAR_OPTIONAL` 에도)에 넣는다. 머리 띠 두 줄 · 진행 막대 자리의 오른쪽 비움은 알림 칸 JS 가 잰 툴바 실제
    폭(`--capa-toolbar-width` · `data-capa-toolbar`)을 읽어 다시 잴 것이 없다(`app_header._MEASURED_HEADER_RULES`·
    `_MEASURED_STATUS_SLOT_TEMPLATE`). rem 고정값(`_NARROW_HEADER_RULES` · `_status_slot_css`)은 그 표지가 서기 전
    첫 프레임 몫이다.
  - 전환은 새 세션이라 미저장 시나리오·설비 편집이 있으면 `confirm` 으로 묻는다(표지 `unsaved_edits_marker`). 새로 읽기
    직전에 부모 창에 `RELOAD_ASKED_FLAG` 를 달아 탭 줄의 새로고침 확인 창(`page_tabs.js` 의 `<tabs-unload>`)이 다시 묻지 않게
    한다. 같은 표지를 그 확인 창도 읽는다.
    시나리오 밖의 것 — 설비 편집본·Space FAB 전체 배치 대기분(설비 편집본 세대 밖)·Space 층 사용 편집 초안·적용 전
    편집(편집표·붙여넣기 대기·표 초안)·Past Data 초안·시나리오 관리 표 초안·VOC 적어 둔 답변·입력 비가동 초안 — 은 `app.py` 가 같은 회차의 탭 점
    판정(`page_tabs.page_unsaved_marks`)으로 넣는다.
- `src/capa_simulation/components/page_guide.py` — 헤더 툴바 맨 왼쪽 `Guide` 버튼과 화면별 사용 안내
  대화상자다. 원문은 패키지 안 `guides/<페이지 파일 이름>.md` 다.
  - 툴바 버튼이 본문의 숨은 버튼(`page_guide_trigger`)을 대신 누르고 파이썬이 `st.dialog` 로 연다.
    `render_page_guide` 를 부른 화면에만 버튼이 보인다. 대화상자 본문은 키 붙은 칸(`GUIDE_BODY_KEY`)에 들고, 기본 규칙
    (`_BASE_STYLE`)이 그 칸의 표를 제 폭 안에서 옆으로 굴린다(`display: block`·`overflow: auto` — 고정 폭 캔버스를 여는
    `scroll_shell` 셸이 아니다) — 좁은 창(390px)에서 넓은 표가 대화상자를 밀어 오른쪽 열이 잘리고 가로 바퀴로도 못 보던
    것(2026-10-26 E2E).
  - 따라하기 가이드를 단 화면(`render_page_guide(..., howto=<가이드>)` — 지금은 HOME 의 `lob`)은 `find_howto_guide`
    가 사내판 `static/guides/local/<가이드>.html`(git 무시) → 예시판 `static/guides/howto/<가이드>.html`(추적) → md
    대화상자 차례로 고른다. 고른 주소(문서 기준 상대 `app/static/guides/…` — WebIDE `/proxy/<포트>/` 접두에서도 맞다)를
    버튼 규칙의 CSS 변수(`GUIDE_HREF_VARIABLE`)로 싣고, 툴바 버튼이 누르는 순간 그 주소로 이름 붙은 좁은 옆 창
    (`capa-guide`, 폭 520)을 연다 — 파이썬 회차를 거치면 사용자 몸짓이 사라져 팝업 막이에 걸린다. 이미 열린 창은
    다시 읽지 않고 앞으로 부르며, 창을 못 열면 대화상자로 물러선다. md 원문은 창 머리 「설정 사전」 단추가
    `window.opener` 의 숨은 버튼을 눌러 앱 창에 연다(선택자 사본은 틀 `template.html`, `tests/test_page_guide.py`).
- `src/capa_simulation/guides/howto/` — 따라하기 가이드 뼈대(사외 정본): 원고 `<가이드>/content.json` · 촬영 계획
  `plan.json` · ID 장부 `ids.json` · 형식 `schema/*.json` · 틀 `template.html` · 사내가 찍지 않는 상태의 합성 예시 그림
  `<가이드>/example/`(WebP · `shots.json`). 사내는 `review/guide/` 의 글 덮어쓰기 · 매개값만 얹는다(git 무시).
  - 결과 자리: 합성 예시판 `static/guides/howto/<가이드>.html`(추적, 공개 저장소 — 그림 밖 글에 실 담당 조직 · 문의처
    · 이메일이 없음을 `tests/test_page_guide.py` 가 본다)과 사내판 `static/guides/local/<가이드>.html`(git 무시, 사내가
    저장소 밖 결과를 손으로 복사). 둘 다 Streamlit 정적 서빙으로 `app/static/…` 에 서고 1.63 은 `.html` 을
    `text/html` 로 내보낸다. 원고 판(`version`)을 올리면 예시판과 `example/` 을 같은 변경에서 다시 만든다. 틀만 고쳐도
    예시판을 다시 조립한다(`--example --assemble-only`, 작업 폴더가 없으면 촬영부터) — 데이터 자리 밖이 틀과 같은지와 창이
    앱 테마 값(`capa-theme` 의 `"Dark"`·`"Light"`)을 대소문자 없이 따르는지를 `tests/test_page_guide_theme.py` 가 본다.
  - 생성기 `scripts/build_page_guide.py` 가 앱 사본을 띄워 찍고(`page_guide_capture.py` + 페이지 도우미
    `page_guide_helpers.js`, Playwright 는 저장소 밖) 조립한다(`page_guide_core.py` — 자르기 · 상자 % · 덮어쓰기 ·
    매개값 · 리뷰 한 줄). `--example` 은 `git archive` 사본 + 검수용 합성 샘플 시드(`scripts/generate_review_sample.py --out <사본>
    --no-csv --skip-inspect` — 사본 뿌리에 두 DB, 모듈은 자식 앱 환경이 끈다), `--internal` 은 런북 6-3 사본 트리에서만 돈다(사내판 —
    2026-11-02 부터 쉼, 다시 열 때를 위해 둔다). 결과는 늘 저장소 밖(`--dist`)에 쓰고, 예시판은 사람이 정본 자리로 복사해 커밋한다.
  - 사내 1단계는 쓰기 등급(`writes`)이 사슬에 `db` · `shared` 인 상태를 건너뛰고 예시 그림으로 대신하며, 사본 두 DB 의
    크기 · sha256 이 앞뒤로 같아야 한다. 「앞」은 그 `--work` 의 첫 촬영 앞에 적은 기준 지문(`db_baseline.json`)이고, 같은
    `--work` 로 다시 돌 때도(`--states` 여부와 상관없이) 그것과 견줘 사본이 이미 다르면 앱을 띄우지 않고 멈춘다 — 바뀐 DB 를
    새 기준으로 삼지 않는다. 앱 오류 · 예외로 멈출 때도 판정을 `run.json` 에 적는다. 점검기 `scripts/check_page_guide.py` 가
    같은 리뷰 한 줄을 다시 낸다.
  - **바뀐 자리만 검수**(2026-10-25 사용자 결정 — 명세는 쇼케이스 `guide/handoff/guide-review-diff.md`, 끝 절은 2026-10-26 결정).
    점검기 `--accepted review/guide/accepted.json` 이 원고 자리(`step:` · `thumb:` · `map:` · `concept:` — `lob` 은 38, 사내
    1단계가 견주는 것은 예시 넷을 뺀 34)마다 표적 자리 · 크기(화면 안으로 자른 정수) · 자르기 틀 · 원고 · 덮어쓰기 · 촬영 동작의
    지문을 지난번 검수를 마친 판과 견줘 리뷰 칸 `바뀜 n/N` 과 stderr `바뀜 <자리> <까닭>` 을 낸다(`page_guide_core.compare_accepted`).
    기준을 못 읽으면 멈추지 않고 `바뀜 na`(0) 다. 그 판은 점검기 `--accept` 만 쓰고(인자 모자람 · 자리가 아님 · 판 다름 · DB 변화
    있음 · 조립 기록 없음 · 조립 뒤 바뀜 · 쓰지 못함이면 2), 생성기는 조립할 때마다 조립 도장 `--work/assembled.json` 만 남긴다. 데이터
    자리(`DATA_SHAPED` — 실데이터가 자리 · 크기를 정하는 `named:` 표적을 쓰는 자리)는 좌표를 남기지 않고 늘 목록에 든다. 화면 글자 ·
    매개값의 값 · 그림은 읽지도 남기지도 않는다. 상자 · 틀 그리기 식(`pct` · `frame_around` · 지도 칸 보정 · 틀 `template.html` 의
    상자)을 바꾸면 `ACCEPT_RULES` 를 올리고, 앱 화면을 바꿔 사내가 그 상태를 다시 보게 하려면 계획 상태의 `look` 을 올린다(형식
    `schema/accepted.schema.json` · `plan.schema.json`).
- `src/capa_simulation/components/print_button.py` — 헤더 툴바의 `Print` 버튼 스크립트다(감춘 ⋮ 메뉴의 인쇄를
  대신). 실행 중이면 멈출 때까지 기다렸다 인쇄하고, 어두운 테마면 `DARK_PRINT_CONFIRM` 으로 먼저 묻는다.
- `src/capa_simulation/components/plotly_touch_scroll.py` — 칸 선택(`on_select`)을 켠 Plotly 그림 위에서 시작한
  터치가 화면을 스크롤하게 하는 스크립트다. 대상 key 는 `app.py` 의 `CELL_SELECT_CHART_KEYS` 다.
- `src/capa_simulation/components/cell_press_guard.py` — 누르면 공정 Capa 상세로 옮기는 HOME 세 월 그림
  (`HOME_CELL_CHART_KEYS`)의 둘째 누름을 옮기는 동안 거르는 스크립트다(테마 버튼 iframe 의 `extra_scripts`).
  - 칸 더블클릭(0.08~0.15초)의 둘째 누름은 아직 떠 있는 HOME 그림에 닿아 **떠나는 HOME 프래그먼트의 회차**를 HOME
    주소로 청했다. 그 회차는 옮긴 화면 회차 뒤에 돌며 화면이 바뀌었다는 새 세션 메시지로 프런트가 본문을 비우고(1.63
    `clearAppState`), 프래그먼트는 이제 없어(「Couldn't find fragment」) 공정 Capa 상세 본문이 빈 채 남았다(2026-10-27
    E2E). 프래그먼트 회차에서는 앱 스크립트가 돌지 않아 서버가 거를 자리가 없다.
  - 부모 문서 캡처 단계에서 그 그림들 위의 `mousedown` 이 창을 열고, 그 뒤 `HOLD_MIN_MS`(0.5초) 안이거나 앱 회차가 도는
    동안(`stApp` 의 `data-test-script-state`, 길어야 `HOLD_MAX_MS`) 그 그림들 위의 누름(`pointerdown`·`mousedown`·
    `dblclick`)을 Plotly 까지 내려보내지 않는다. 첫 누름의 `mouseup`·`click` 은 건드리지 않는다. 판정은 순수 구획
    `<cell-press-hold>`(node 시험 `tests/test_cell_press_guard.py`). 화면을 옮기는 칸 선택 그림을 더하면 여기에도 넘긴다.
- `src/capa_simulation/components/boot_stop.py` — 앱이 데이터를 열지 못한 회차의 앱 안 멈춤 판(`app.py` 의 부트스트랩
  `except` 가 머리 띠 뒤에 부르고 곧바로 `st.stop()`). 갈래(`classify_boot_failure`)는 잠김(남 · 자기 — 쥔 PID 가 적힘. 남이 쥔 잠김은 경고 끝이 「— 개발자에게 알려 주세요」(`HELD_LINE` — 뒤 회차 DB 실패 알림의 `page_bootstrap.ADMIN_TAIL` 과 같은 일, 카드 p1-no-revision), 자기 잠김은 다시 하면 풀려 꼬리가 없다. 아래 열기 · 쓰기 실패와 그 밖도 남이 쥔 잠김과 같은 꼬리에 까닭을 괄호로 싣는다 — 「지금은 데이터를 열 수 없습니다(디스크가 가득 참) — 개발자에게 알려 주세요」 + 「다시 시도」, 그 밖은 괄호 없이(`io_line` — 뒤 회차 DB 실패 알림의 짧은 글과 같은 꼴, 보드 decided-login 7)) →
  판 올리기 실패(`_migration_core.MigrationFailed` — 이미 적용된 SQL 의 체크섬이 바뀜(`MigrationChanged`) · 새 SQL 이 SQL · 데이터
  오류로 실패함, 「다시 시도」 없음) → 디스크 가득(errno · 영문 고정 문구) → 파일 권한 → 열 수 없음(`Cannot open`·`Could not set
  lock`) → 그 밖이다. 진단의 원문은 판 올리기 실패가 감싼 DuckDB 오류(`__cause__`)다.
  판은 쉬운 경고 한 줄(`st.error` — UI-NTF-08 예외) · 주 단추 「다시 시도」(누름이 회차 하나 — 부트스트랩은 성공한 회차에만
  「해 봤다」 표지) · 「문의 <메일>」 · 「참고 <갈래 키> · <UTC 분> · <오류 종류>」(오류 종류 이름은 누구에게나 — 보드 d12 (가)) ·
  접힌 「개발자용 진단」(복사 단추 · 지금의 `bootstrap_error_message` 글 — PID · 파일 경로 · 조치 — 와 원문)이다. 접힌 진단은
  개발자 몫(`admin_view.developer_notes_visible`)에만 선다 — 접어도 누구나 펼치므로 접힘으로 가리지 않고, 판정이 무엇을 내도 진단
  없음으로 물러선다(마지막 자리). 운영 서버에서 통합인증이 꺼진 동안은 아무에게도 서지 않는다. 공용 조각은 `components/stop_panel.py`(앱 안 멈춤 판 셋 —
  앱 시작 실패 · 접속 멈춤 · 한 화면 오류 — 의 한 꼴: 경고 띠 → 주 단추 하나 → 문의 줄 → 참고 줄 → 접힌 진단. 띠와 주 단추는 부르는 쪽이, 뒤 셋은
  `render_stop_footer` 가 같은 차례로 그리고 개발자 몫 판정 `admin_fold_visible` 이 셋의 물러섬을 한 곳에 둔다. 문의 줄 메일은 그 회차 테마의 `ACCENT` 링크로 사이드바 앱 정보 카드 · 앱 밖 화면의 문의처와 같은 색이다 — 줄은 원문 HTML 문단 하나(`contact_markup` — 마크다운 줄 안의 `<a>` 는 GFM 자동 링크가 메일 글을 한 번 더 감싸 색이 빠진다), 보이는 글은 평문 `contact_caption` 과 같다. 시험 `tests/test_stop_panel.py`). 서버 기록에는 갈래와 종류 이름만 남긴다. 입장 화면이 읽는 스타일 표지(`BOOT_STOP_ATTRIBUTE` — 값은 경고 한 줄)를
  함께 보낸다(자리를 먹지 않는다). 시험은 `tests/test_boot_stop.py`.
  개발자가 참고 줄과 짝을 맞출 자리로 Admin 「통합인증 점검」 최근 사건 고리에 사건 `boot_fail`(사유 코드 = 갈래 키 · `kind` = 오류 종류 — 표의 사유 코드 칸은 「<갈래> · <종류>」)을 한 줄 남긴다(`auth.runtime.note_boot_failure`, 보드 boot-record — C-DEP 에는 서버 로그 창구가 없다). 같은 갈래가 이어지면 처음 한 번만(회차 · 「다시 시도」 · 다른 사람의 새 탭마다 쌓지 않는다)이고 `app.py` 가 부트스트랩이 저장소를 열고 끝낸 회차(공식버전이 없어도 — 「해 봤다」 표지 `OFFICIAL_BOOTSTRAP_ATTEMPTED_KEY` 가 그 회차에 새로 선다. 이미 올라온 세션 · 해 본 세션의 회차는 저장소를 열지 않아 끊지 않는다)에 `note_boot_success` 로 이어짐을 끊는다. 이어짐 표지는 통합인증 프로세스 상태(`runtime.reset` 이 비운다)에 있다. 새 알림 번호 · 감사 대응은 없다.
- `src/capa_simulation/components/intro_overlay.py` — 탭을 처음 연 사용자의 첫 로딩을 덮는 입장 화면이다. 다
  그려지면 `Detail`(원래 화면)·`Summary`(최신 공식버전 여섯 달 요약)로 들이고 같은 탭에서는 다시 띄우지 않는다.
  실행이 끝났을 때 앱 시작 실패 표지(`boot_stop.BOOT_STOP_ATTRIBUTE`)가 있으면 「준비 완료」 대신 상태 낱말 「열지 못함」, 끝낸
  단계까지만 끝남 · 멈춘 칸은 실패 색(`die-short`) + 「멈춤」, 상태 줄 아래 까닭 한 줄(풍선이 아니라 글)이다. Summary 단추는
  잠근 채 까닭 풍선(경고 한 줄 — 요약이 오지 않는다, UI-INP-07)이고, 장면에는 끝남 대신 멈춤(`progress.halted` — 신호로 끝낸
  단계만큼만 덮고 검사 원을 멈춤)을 보낸다. 표지는 그릴 때마다 다시 읽는다(「다시 시도」 로 붙으면 걷혀 풍선 · 펼침이 돌아온다).
  Summary 머리 줄 Detail 왼쪽의 ← 가 입장 화면(커버)으로 되돌린다 — 장면 메시지 `summary-off` 가 차트를 걷고 웨이퍼
  색·그늘을 입장 모습으로 돌리며, 다시 보낼 자리에서 `summary-on` 을 대신한다. 커버 셋째 단추 `Introduce` 는 40초
  티저(`intro_overlay_assets/capa-teaser.html`, `INTRODUCE_TEASER_PATH`)를 오버레이 안 전체 화면 틀(blob 주소)에 띄운다
  — 단추에서 원이 퍼지고 ←·Esc 는 그 단추로 접히며, 티저 머리 `Detail` 은 곧장 앱이다. 셋 모두 티저의 `TEASER.pause()`
  로 재생을 멈춘다 — 티저는 재생 때 남은 소리를 미리 잡아 두므로 층만 숨기면 40초 끝까지 소리가 난다. 다시 열면 멈춘 자리에
  서 있고 티저 안 `Space` 로 잇는다. 티저가 덮은 동안 장면 워커는 쉬고, Summary 처럼 들어갈 준비가 끝나면 선다.
  운영 서버에서는 `Introduce` 단추가 화면 등급 개발자에게만 선다 — 다른 사람의 커버는 `Detail` · `Summary` 두 단추다
  (2026-11-24 정식판 마감 2-A 의 티저 몫 — 합성 수치가 든 대회 사본, 판정은 `intro_summary.teaser_payload` · JS 는
  `teaser.available` 만 본다).
  `site/contest-deck/index.html`(GitHub Pages 발표 덱)은 앱이 쓰지 않는다.
  - Components v2 하나이고 자산은 `intro_overlay_assets/`(`intro.html`·`intro.css`·`intro.js`)다. 움직임은 워커
    OffscreenCanvas 에서 돈다 — 워커로 가는 `scene()`·`summaryGrid()` 는 그 파일의 다른 이름을 쓰지 않는다.
  - 등록 JS·`data` 는 회차마다 같고 색은 테마와 무관한 `tokens.INTRO_PALETTE` 다. 파이썬으로 가는 길은
    `intro_summary` 의 trigger 둘뿐이다 — 「준비 중」 GAP 다시 받기(`refresh`)와 Introduce 티저 받기(`teaser`).
  - 부분 글꼴 둘(`archivo-capa.woff2`·`archivo-capa-number.woff2`, `OFL.txt`)에 없는 글자를 쓰면
    `FONT_SUBSET_TEXT` 를 고치고 다시 만든다. 심볼 넷(`static/icons/capa_mark.svg` 포함)은 `test_intro_overlay` 가 맞춘다.
  - 입장 화면 타이틀(앱 이름 두 줄 `TITLE_LINES`)은 `intro.css` `.title` 의 `text-transform: uppercase` 로 대문자(「S.PKG CAPA / AX MANAGEMENT」)로 보인다 — 글자는 앱 이름 표기 그대로이고 부분 글꼴에 대문자도 든다. 사이드바 · 머리 줄 앱 이름 라벨은 표기 그대로다.
  - 등록 JS 맨 앞에 브라우저 기록 지킴이(`history_guard.history_guard_script()`)가 실려 모듈을 읽는 순간 건다 — 회차 맨
    앞 요소라 링크 인자 화면이 첫 회차에 인자를 지우는 주소 메시지보다 먼저다(3장 `page_tabs.py` 「기록 한 칸」).
  - 앱으로 들어갈 때 초점 — 사이드바 라벨로 연 Summary 는 그 라벨로 돌려주고, 연 단추가 없는 입장(처음 입장 화면·거기서
    연 Summary·티저)은 화면 탭 줄의 지금 탭(그림자 DOM 안), 탭 줄이 없으면 본문 첫 제목에 둔다(`LANDING_FOCUS` — 탭 줄
    key·`aria-current` 표지를 `data.landing` 으로 받는다). 두지 않으면 body 에 남았다.
  - 덮개 밑에 뜬 Streamlit 팝업은 덮개가 닫는다(순수 구획 `<intro-dialogs>`). 없는 화면 주소(꺼진 모듈 화면·주소를 바꾼 옛
    화면)로 처음 오면 Streamlit 이 「Page not found」 팝업을 연다. 1.63 팝업(react-aria 모달)은 body 의 다른 자식을 inert 로
    묶어, body 직속인 덮개 호스트가 눈으로는 맨 위인데 누름을 받지 못했다 — 첫 누름이 보이지 않는 팝업 바탕으로 가 팝업만
    닫고 Detail 을 두 번 눌러야 들어갔다(키보드 Enter 는 팝업에 갇혔다, E2E 결함). 덮개가 보이는 동안은 앱이 inert 라 사람이 연
    팝업일 수 없으므로, 호스트에 inert·aria-hidden 이 붙으면(`MutationObserver`) 팝업(`stDialog`)마다 그 대화 상자에 Esc 를
    보내 닫는다 — 첫 누름이 하던 일이라 팝업 글은 전처럼 보이지 않고 HOME 이 열린다. 보낸 Esc 는 덮개 키 처리(Summary 의
    Esc)가 지나친다. 덮개를 감춘 문서(같은 탭에서 이미 들어간 뒤)에서는 건드리지 않는다 — 그때 팝업은 보이고 사람이 닫는다.
    글이 아니라 팝업 자리로 고르므로 Streamlit 을 올리면 팝업이 호스트를 묶는 꼴(속성 이름)을 다시 본다.
  - 무대(`.stage`)는 옆으로 넘치지 않는다 — 읽기 도구용 표는 1px 칸(`div.sr`) 안에 둔다(표에 바로 1px 를 주면 내용 폭으로
    늘어 390px 무대가 639px 로 넘쳤다). 520px 이하에서는 머리 칩(공식버전 이름)이 토글 셋과 함께 둘째 줄(`.tail`)로 내려
    남는 폭을 쓴다 — 넓은 창에서 `.tail` 은 `display: contents` 라 머리 줄은 그대로다. 머리 칩은 어느 폭에서도 자르지
    않는다 — 두 줄까지 접히고 그 끝에서만 줄인다(기간 글자는 줄지 않는다 — 아래 요약 기간). 360px 아래에서는 토글이 짧은
    이름이다(2026-10-30 E2E — 761 ~ 990px·320px 에서 칩이 잘렸다).
  - 요약 기간 −·+(2026-11-02 사용자 요청(검수표) home-02). 값은 공식버전의 모든 달이고 화면은 여섯 달 창이다 — 창 자르기·
    옮기기는 순수 구획 `<intro-window>`(`WINDOW_FIELDS`·`windowedSummary`·`windowStartFor` — node 시험
    `tests/test_intro_window.py` 가 파이썬 값의 달 목록을 모두 맞대 본다)이고 파이썬으로 아무것도 보내지 않는다(rerun 없음).
    기본 창은 파이썬의 `start`(지난달부터), 옮긴 창은 첫 달 이름으로 이 탭 sessionStorage `capa-summary-window`(입장 화면
    「들어갔음」 표지와 같은 범위)와 `api.summaryWindow` 에 남아 사이드바 라벨로 다시 열어도·새로고침해도 그대로다. 단추는 머리
    칩 오른쪽 `.window`(기간 글자 + 18px 네모 둘)이고 끝에서는 `aria-disabled` + 풍선 까닭, 옮긴 뒤 `live` 칸이 새 기간을 읽는다.
    기간 글자는 줄지 않고 칩이 줄며 접힌다. 760px 이하는 둘째 줄(토글 줄) 오른쪽 끝, 520px 이하는 생산계획 이름 띠 오른쪽
    끝(`summaryGrid` 좁은 창 첫 줄 띠 96px — 머리 줄 위 여백 18px 에 맞춘 자리라 그 둘을 바꾸면 함께 본다)이다. 범례는 창 안에
    조각이 있는 제품만이고 색은 그대로다. 부품이 둘 이상인 제품은 HOME 과 같은 이름표(「제품 (부품)」)마다 한 항목이다. 과거 구간 달은 도넛 자리에 「과거 구간」, 풍선·낭독 표에 「과거 구간 입력값」 이다.
  - B/N 확보율 판의 기준선 이름표는 막대 칸(판 위 ~ 막대 바닥, 그 아래 50px 는 공정 이름·상태 띠) 안에서 막대·확보율
    글자·「최저」·기준선·다른 이름표를 피하는 자리를 고르고, 없으면 글자만 피하는 자리에 바탕을 깔아 단다 — 그것도 없으면
    쓰지 않는다. 「최저」 도 판 위로 나가면 쓰지 않는다(낮은 휴대폰 창에서 막대 축이 몇십 px 라 확보율 글자와 기준선이 한 줄에
    몰렸다 — 2026-10-30 E2E, `test_intro_scene_behavior`).
- `src/capa_simulation/components/history_guard.py` — 탭 줄 JS(`page_tabs.js`)의 기록 지킴이 두 구획(`<tabs-history>`·
  `<tabs-history-install>`)을 떼어 입장 화면 등록 JS 앞에 싣는 글로 낸다. 글은 탭 줄 자산 한 벌이다(옮기지 않는다 — 두 벌이면
  한쪽만 고쳐 다른 지킴이가 먼저 걸린다). 컴포넌트를 등록하지 않아 `page_tabs` 를 불러오지 않는 모듈이 쓸 수 있다.
- `src/capa_simulation/components/intro_summary.py` — 입장 화면 Summary 의 값(최신 공식버전 요약 + 토글 셋
  `toggles`)과 Introduce 티저 칸(`teaser`)을 `capa_intro_summary` 로 보내고 사이드바 앱 이름 라벨을 세운다. 계산은
  `services/official_summary.py`.
  - 티저 본문(약 1MB)은 입장 화면이 `teaser` trigger 로 달라고 한 회차에만 읽어 싣는다(`teaser_payload`) — 받은 값
    JS 가 `teaser` 를 떼어 따로 넘기므로 워커로 가는 요약에는 티저가 없다. Streamlit 정적 경로는 HTML 을 글자로 보내
    쓸 수 없어 이 길이다. 운영 서버에서는 구현 중 화면 숨김(`sso_identity.unfinished_hidden`)과 같은 동작
    `screen.unfinished` 를 할 수 없는 회차에 달라고 해도 `available: false` 다(표지는 그 회차에 걷음 — 2026-11-24 정식판 마감
    2-A 의 티저 몫). 등급 창구는 늦게 읽는 대리 `grade_hooks` 로 부른다(`sso_identity` → `app_header` → 이 모듈 고리).
  - 모든 페이지 앞에서 돌므로 어떤 예외도 내보내지 않는다(`available: false` 와 까닭). 공식 리비전의 결정적
    키로 HOME 과 같은 캐시를 쓰고, 판정 기준은 공용 프로필(`load_global_securement_threshold`)이다.
  - 값은 공식버전의 **모든 달**이다 — HOME 기본 조회기간(`settings.MONTH_SELECTION_*`)으로 `display_month_range`(HOME 과 같은
    함수)가 낸 범위라 공식 시나리오를 기본 조회기간으로 연 HOME 과 `get_home_simulation` 키가 같다. 과거 구간(`GlobalPastData`)은
    HOME 기본(켬)처럼 이어(`official_summary.merge_summary_past`) 그 version 이 요약·세 몫의 서버 키에 든다 — 과거 구간 저장
    (`past_data_management.save_past_tables`)도 `forget_intro_summary_check` 를 부른다. 기본 창 차례 `start`(지난달부터 —
    `default_window_start`, 서버 날짜 `_current_month`)는 날짜로 바뀌어 서버 캐시 밖(`_look_up`)에서 싣는다.
  - 서버 캐시는 요약(`get_intro_summary_payload`)과 토글 몫(`simulation_cache.shared_intro_toggle_store`) 둘이다.
    GAP 몫이 없으면 「준비 중」으로 보내고 페이지 뒤 `warm_intro_summary` 가 만든다.
  - 부하 예외 선언은 공식버전 확인 때 공용 프로필로 읽어 판 **지문**이 요약 키 `IntroSummaryCacheKey` 의 일곱째 칸 · 선행 B/O 몫
    키에 든다(빈 선언은 빈 글 — 선언 없음과 비움 판이 같은 칸). 요약 계산(`_build`)은 그 판을 HOME 계산 키에 접어 HOME 과 칸을 나눈다.
    선행 입고 · GAP 몫은 Wafer · Density 만 써 지문을 넣지 않는다. 지우기(`clear()`)는 없다 — 키가 판을 말한다(5장 45).
  - 확인 주기는 `RECHECK_SECONDS` 이고 무효화는 `forget_intro_summary_check`(`tests/test_summary_recheck_paths.py`)다.
    확인 때 본 `latest_official_revision` 을 머리 띠가 읽는다(이름까지 든 같은 값 `latest_official_identity` 는 HOME 공식
    칩). 라벨 id 는 `intro_overlay.SUMMARY_LABEL_ID` 하나다.
- `src/capa_simulation/services/official_summary.py` — Summary 가 그리는 공식버전 요약(생산계획·B/N·부족
  대수·제품 비중 — 모든 달, 화면은 여섯 달 창)의 순수 계산이다. HOME 토글 기본값(과거 구간 포함)과 같은 화면이고 B/N 은 HOME 과
  같은 순위 함수다. 달은 `summary_months`(빈 달도 칸), 기본 창은 `default_window_start`(지난달부터 — 데이터 밖이면 가장 가까운
  여섯 달), 과거 구간은 `merge_summary_past`(계산이 있는 달은 계산이 이긴다, 과거 확보율 행은 대수가 없어 부족 대수가 빈다).
  부족 대수는 B/N 공정이 그 달 실효 경고 기준까지 모자란 정수 대수다(6장 「경고 기준 필요대수」와 같은 식).
  - 토글 값은 `build_advance_summary`(HOME 「선행 B/O」와 같은 차례)·`build_comparison_summary`(선행 전 − 비교)다.
- `src/capa_simulation/services/plan_gap.py` — 계획 증감 글자(선행 B/O 전후·비교 GAP)의 형식과 0 근처를 적지
  않는 규칙(`GAP_EPSILON`·`visible_gap`·`format_gap`)이다. HOME `home_lob_figures` 와 Summary 가 함께 쓴다.
  비교 계획을 현재 수율 · Chip 표로 환산하기 전에 계획 행의 CUSTOM 을 현재 표에 다시 짝짓는 순수 함수
  (`repair_comparison_plan_custom` — 현재 계획의 같은 Capa Code → 현재 표의 제품 하나 → 원래 값)도 여기 둔다.
  `get_home_comparison_plan` 이 비교 계획을 환산하기 전에 부른다 — 짝이 없는 행은 환산 제외 목록이 센다.
- `src/capa_simulation/components/admin_dialog.py` — Admin Area 편집 탭들이 함께 쓰는 팝업 칸
  (`admin_area_open_dialog`) 하나를 여닫는 콜백이다. 탭마다 칸을 두면 한 회차에 팝업이 둘 뜰 수 있다.
- `src/capa_simulation/components/app_header.py` — 맨 위 띠에 이 세션의 적용 시나리오 두 줄과 진행 막대 자리를
  싣고, 껍데기 스타일(⋮ 메뉴·Deploy·제목 링크 감춤, 사이드바 접기 버튼, 폼 안 알림이 없는 칸과 본문 빈 칸의 간격
  지움(`EMPTY_FORM_SLOT_SELECTOR` · `EMPTY_SLOT_SELECTOR`), 풍선 지연(`tip_delay` — 맨 앞 값 · 애니메이션, 화면 덩어리 끝 규칙),
  인쇄 규칙)을 보낸다.
  - 두 줄은 `stHeader` 가상요소의 글자다. 회차마다 DB 를 보지 않고 세션에 떠 둔 `active_scenario_label`·
    `intro_summary.latest_official_revision`·`scenario_activation.newer_active_revision_no`(「최신 rN 있음」) 만 읽는다
    (`tests/test_app_navigation.py`). 사용자 글은 `css_string` 으로
    이스케이프한다. 설비 시나리오를 읽는 화면은 아랫줄 끝에 「설비 시나리오 · 운영 일정 · r12 · 공식 v3」(상태 차례는 사이드바
    배지와 같다 — 「가정 배치」 포함)을 단다 — 꼬리는 페이지가 정해 `refresh_equipment_header` 로 그 회차에 한 번 더 보낸다(9장).
  - 같은 띠 CSS 가 **늘** 두 변수를 정한다 — 테마 단추 몫 `EQUIPMENT_RETURN_VARIABLE`(`--capa-equipment-return`)은 세션 설비
    시나리오가 최신 공식 발행 쌍이 아니면(공식 시나리오의 다른 리비전 포함) 「「셋업 B」 r8」(퍼센트 인코딩 글,
    `equipment_return_mark` 의 `label`), 새로고침 몫 `EQUIPMENT_RELOAD_RETURN_VARIABLE`(`--capa-equipment-return-reload`)은
    그 가운데 가정 설비 시나리오일 때만 같은 글(`assumed`), 아니면 `none` 이다(가름 「테마 단추는 정확히, F5 는 직전이 가정이었을
    때만」). 그리는 쪽(잠근 꼴은 공식)이
    아니라 세션 라벨(`equipment_scenario_activation.remembered_equipment_label`)로 정하고, `app.py` 와 사이드바 설비 시나리오 줄
    (같은 회차에 띠를 다시 보낸다)이 함께 넘긴다. 테마 단추·새로고침은 새 세션이라 공식으로 돌아가는데(E5), 탭 줄 JS 가 문서를
    떠날 때(`pagehide`) 이 값을 탭의 `sessionStorage` 에 적고 새로 읽은 문서가 알림 칸(알림창 · Alarm)에 한 번 알린다
    (`page_tabs.js` `<tabs-return>` — 테마 단추면 `theme_toggle.THEME_SWITCH_STORAGE_KEY` 표지로 테마 몫과 테마 글). 서버에 아무것도 남기지
    않고, 앞 세션이 공식 발행 쌍이었으면(새로고침은 가정이 아니었으면) 알리지 않는다 — 새 세션마다 알리지 않는다(개선 거리 I1).
  - `app.py` 가 입장 화면 요약 뒤에 한 번 부르고, 껍데기 스타일(`render_shell_style()`)은 부트스트랩 앞에서
    보낸다(그보다 앞서 멈추는 통합인증 멈춤 화면은 `sso_identity._render_stop_chrome` 이 따로 보낸다). 인쇄 규칙은 그 안 `@media print` 한 덩어리다(탭 줄도 뺀다). 화면 덩어리(`@media screen`)의 규칙은 여섯이다 — 화면
    탭 줄을 머리 띠 밑에 붙이는 sticky(`PAGE_TABS_SELECTOR`, z-index 100 — 펼침 목록·팝업 아래. `top` 은 머리 띠 높이
    `tokens.HEADER_BAND_REM` 이고, 제자리를 그 자리와 같게 `margin-top: tokens.PAGE_TABS_LIFT_REM`(-0.25rem)으로 끌어올린다 —
    제자리는 본문 위 여백 `MAIN_TOP_PADDING_REM` + 그 앞 높이 0 테마 iframe 과의 요소 간격 `BLOCK_GAP_REM` 이라 3.5px 아래였고,
    스크롤을 처음 내리는 동안 탭 줄이 따라 올라갔다 — 2026-11-02 사용자 요청 「스크롤 아래로 내릴 때 틀이 살짝 움직임」.
    `tests/test_app_header.py` 가 「위 여백 + 간격 + 끌어올림 = sticky 자리」 를 맞댄다), 큰 제목 칸 sr-only
    (`PAGE_TITLE_SELECTOR`), 모달 동안 탭 줄 흐림(`#root[inert]` — 1.63 은 `st.dialog` 가 열리면 앱 뿌리에 `inert` 를 단다,
    탭 줄 누름이 말없이 먹혔다), 풍선 글이 마우스를 받지 않음(`TOOLTIP_TEXT_SELECTOR`), 폼 안 · 본문 빈 칸 간격 지움, 풍선
    지연(`tip_delay.TIP_SCREEN_CSS` — 덩어리 끝). 인쇄에는 제목이 보인다.
  - 툴바 비움 폭과 진행 막대 자리(`_status_slot_css`)는 툴바 실측값이다(`tests/test_app_header.py`).
  - 회차마다 소켓으로 다시 가는 스타일이라 CSS 안에 주석을 두지 않는다 — 규칙 설명은 그 조각 바로 위 파이썬 주석이다
    (9장 「스크립트와 컴포넌트」).
- `src/capa_simulation/components/tip_delay.py` — 마우스를 올리면 뜨는 풍선의 앱 전체 지연 한 곳(1초 — 2026-11-21 사용자
  결정, 설계 규칙 UI-NAV-04). 값 `TIP_DELAY_MS` · 사용자 정의 속성 `TIP_DELAY_VARIABLE`(`--capa-tip-delay`)과 애니메이션
  `capa-tip-in`(opacity 와 visibility 를 함께 — 기다리는 동안 Playwright `visible=true` · 읽기 도구가 세지 않게)을 껍데기 스타일
  맨 앞(`TIP_ROOT_CSS`, `@media` 밖 — 그림자 뿌리도 사용자 정의 속성은 물려받는다)에, 거는 규칙 넷(`TIP_SCREEN_RULES` —
  Streamlit 도움말 · 오류 풍선과 표 칸 풍선은 JS 지연 200 · 600ms 뒤 나머지, Plotly · Altair 그림 값 풍선은 문서 뿌리 웜업 표지
  `CHART_WARM_ATTRIBUTE` 가 없을 때만, Plotly 막대 단추 이름은 늘)을 화면 덩어리 끝에 둔다.
  - 그림 웜업 스크립트(`chart_tip_warmup_script` — 고정 문자열, `app.py` 가 테마 툴바 스크립트에 싣는다)는 부모 문서에
    `pointerover` · `pointerout` 하나씩 걸어 그림에 처음 들어온 뒤 지연이 지나면 표지를 달고, 그림 밖 · 다른 그림 · 창 밖이면
    뗀다. 멈춘 마우스 밑에 그림 밖이 새로 서는 것(누를 때 Plotly 가 세우는 덮개 `dragcover` · 칸 누름 회차에 다시 세우는 틈의
    빈 칸)은 떠난 것이 아니다 — 그림 안에서는 `pointerover` 가 없어 옮긴 자리 · 누른 자리를 `pointermove` · `pointerdown` 으로
    적어 가르고(브라우저는 요소를 넘는 `pointerover` 를 그 자리의 `pointermove` 보다 먼저 보낸다), 누른 채 그림 상자 밖으로 끌고
    가 뗀 자리는 식힌다. 칸 key(`st-key-…`)가 같은 그림이 다시 서면 잇고, 굴림 · 화면 옮김으로 밑에 온 다른 그림 · key 없는
    그림은 기다린다. 터치는 곧바로 데운다. 테마 iframe 이 다시 서면 옛 처리기를 뗀다.
  - 그림자 DOM · 자체 풍선 부품(`grid_shared_assets/cells.css` · `eg_core.js` · Space `editor.js` · `date_panel.js` ·
    `process_picker` · `paste_window.css` · `intro.js`)은 같은 속성을 읽고 못 읽을 때의 기본값도 1초다 — 키보드 초점은
    곧바로, 누름은 날짜 칸 도움말 · Space 배치 편집 표의 잠긴 칸 열기만 곧바로(꺼진 단추 까닭 · 붙여넣기 창 잠긴 칸은 1초).
  - Streamlit 풍선 글 상자 testid 셋 · JS 지연(200 · 600ms)과 Plotly 풍선 묶음 · Altair 풍선 id 는 비공식 이름이라 판올림으로
    바뀌면 지연만 조용히 풀린다 — `tests/test_tip_delay.py` 가 설치된 프런트 묶음에서 찾는다.
- `src/capa_simulation/components/typography.py` — 본문의 페이지 제목·상자 제목·큰 숫자에만
  `tokens.FONT_FAMILY_DISPLAY`(`CapaDisplay`)를 거는 앱 전체 서체 스타일이다(자리 표 `docs/design_system.md` 1-1).
  - 글꼴(`static/fonts/archivo-700.woff2`·`archivo-800.woff2`)은 정적 서빙(`config.toml`)의 상대 경로로 받는다 —
    `static/` 밖이면 404 다. 색 없는 고정 문자열이라 부트스트랩 앞에서 매 회차 보낸다(`tests/test_typography.py`).
- `src/capa_simulation/components/accent_button_style.py` — 강조색으로 칠한 Streamlit 단추(`kind="primary"`·
  `"primaryFormSubmit"`, 잠긴 단추 빼고)와 `st.multiselect` 고른 칩(`[data-tag]`, 잠긴 상자 빼고)의 글자색을 그 회차
  테마의 `tokens.ACCENT_TEXT` 로 다시 건다(`docs/design_system.md` 2-2).
  - Streamlit 1.63 은 칠한 단추·칩 글자를 늘 흰색으로 쓰고 그 색을 정하는 테마 칸이 없다 — 어두운 테마의 밝은 강조색
    (`#2DD4BF`) 위 흰 글자는 1.86:1 이었다(표준 목표 「가용설비 붙여넣기」, 2026-10-25 E2E · 표준 대비 재공 현황 조회
    조건 칩, 2026-10-26 E2E r3). 밝은 테마는 흰 글자 그대로다. 잠긴 multiselect 는 콤보상자 뿌리(`stMultiSelect`
    바로 아래 칸)에 `data-disabled` 가 서고 칩이 흐린 바탕·흐린 글자라 고르지 않는다.
  - 테마 토큰이라 `app.py` 가 `theme.begin_run()` 뒤·부트스트랩 앞에서 매 회차 보낸다(`tests/test_accent_button_style.py`·
    `tests/test_app_navigation.py`). HOME 칠한 주요 Case 칩의 같은 색 규칙(`home_main_case_chips.chip_style`)은 칩 모양
    규칙과 함께 그대로 둔다.
- `src/capa_simulation/deploy_stamp.py` — 사내 적용 기록(`.deploy/applied.json`)의 배포 번호 읽기. 앱 카드와 감사 기동이 같이
  쓰고, 그 번호를 붙인 앱 판(`deployed_app_version` — `settings.app_version`, 「1.0.<stamp>」 · 기록이 없으면 「1.0」)은 앱 카드 첫 줄 ·
  버킷 세대 포인터(`object_sync_engine` 의 `app_version`) · 도구 감사 줄(`audit/tool` 의 `ver`)이 같이 쓴다. 감사 기동은 `capa_server.py` 가 Streamlit 런타임 **전에** 부르므로 이 모듈은 `components` 를 import 하지 않는다 —
  런타임 전에 `st.components.v2.component(...)` 를 부르는 화면 조각을 불러오면 그 컴포넌트가 등록되지 않아 앱이 첫
  화면에서 멈춘다. `tests/test_server_pre_runtime_imports.py` 가 진입점의 런타임 전 길을 지킨다.
- `src/capa_simulation/components/app_credits.py` — 앱 이름·판과 개발 팀·문의처 두 줄을 모든 화면
  사이드바 바닥 카드(`APP_CREDITS_KEY`)로 보인다. 값의 근거는 `settings.py` 다. 첫 줄은 「<앱 이름> v1.0.<배포 번호>」(판 머리
  `APP_VERSION` + 적용 기록의 배포 번호 — `settings.app_version`, 2026-11-24 정식판 요청)이고 적용 기록이 없는 사외 개발 PC 는
  「<앱 이름> v1.0 · 사외 개발」 이다. 문의처 메일은 사람을 가리키는 사내 값이라
  저장소에 없고 환경변수 `CAPA_APP_CONTACT_EMAIL`(`settings.app_contact_email()` — 부를 때마다 읽음, 사내 PC 사용자 환경변수 ·
  C-DEP 환경변수 표)로만 받는다 — 비면 둘째 줄은 「개발 <팀>」 만이다(2026-11-12 보드 답 ⑤-9). 통합인증 줄이 붙으면 캡션이
  원문 HTML 이므로 메일 꼴(`이름@도메인.최상위`)이 아닌 값은 비운 것과 같다. 시험은 `tests/conftest.py` 가
  그 환경변수를 지우고 돈다(필요한 시험만 `…@example.invalid` 를 넣는다). 통합인증이 켜진 서버는 셋째 줄
  「이름 · 부서 · 로그아웃」(`sso_identity.sso_credit_line`)이 붙고, 그 줄이 있을 때만 캡션을 `unsafe_allow_html` 로 그린다
  (로그아웃을 같은 탭에서 여는 원문 링크 — 이름 · 부서는 `literal_markdown` 으로 막았다). 꺼짐은 두 줄 그대로다.
  - 그리는 것은 캡션뿐이고 자리·바닥 고정·면은 `sidebar_style.py` 가 건다. key 는 조건 카드 접두어를 품지 않는다.
  - 카드 뒤에 접속 명단 알림 `AD-08` · `AD-09` · `AD-19`(새 스스로 등록 — 최근 30일 수, 지문은 고친 기록의 가장 새 스스로 등록 시각이라 늘 때만 뜬다) 를 낸다 — 셋 다 「그 화면으로」 가 「접속 명단」 펼침을 연다(S3 명단 서버만 · 회차마다 이벤트 칸 세 자리 — 개발자의 어느 화면에서나,
    2026-11-08 답 U4). 통합인증이 켜진 서버는 그 뒤에 로그인 갱신 거절 알림 `AD-21`(`sso_refresh_alert.render_refresh_alert` — 개발자 몫에만,
    회차마다 이벤트 칸 한 자리)도 낸다 — 켜진 S3 명단 서버의 카드 뒤 알림은 네 자리다(감사 기록기가 켜진 서버는 `AD-12` · `AD-13` 두 자리가 그 사이에 더해진다).
    남은 시간 표지는 「· 로그인 n분 남음」 · 「· 로그인 최대 시간까지 n분」 까지 값만이고, 저장해 두라는 말은 최대 시간 10분 전 첫 회차의
    사건 알림 `AD-20`(`components/sso_expiry.py` — `app.py` 가 신원이 있을 때 한 번 담는다, 보드 카드 p1-expiry)이 한다.
    바닥에 붙은 카드 밑으로 칸이 들어가지 않게 사이드바 스크롤 칸에 `scroll-padding-bottom`(두 줄 `APP_CREDITS_SCROLL_ROOM`,
    통합인증 셋째 줄까지 `APP_CREDITS_SCROLL_ROOM_SSO` — `app.py` 가 `app_credit_lines` 로 고른다)을 둔다 — 초점 이동·
    `scrollIntoView` 가 긴 조건 카드의 마지막 칸을 카드 위에 세운다(덮인 자리를 누르면 카드 링크가 눌렸다).
- `src/capa_simulation/components/page_box_reveal.py` — 화면 조작 상자(`PAGE_BOX_PREFIX`)가 바닥 앱 정보 카드에 걸린 채 서면
  사이드바를 상자가 다 보일 만큼 굴리는 스크립트다(9장 「사이드바·조건 카드·본문」). 테마 버튼 iframe 의 `extra_scripts` 로 실린 고정
  문자열이고, 듣개는 회차 표지(`data-test-script-state`) · 그룹 펼침(`open`) · 사이드바 펼침(`aria-expanded`) 속성만 본다 — 프런트가 밀리면
  회차 표지가 바뀌지 않는 회차가 있어 그룹이 펴질 때도 잰다. 그룹이 펴지는 끝 프레임에 Streamlit 이 둔 시작 높이가 되살아나 브라우저가
  `scrollTop` 을 깎으므로 `SETTLE_MS` 간격으로 `SETTLE_LOOKS` 번 더 재고, 멈추는 것은 사람의 입력 사건뿐이다(값으로는 깎임과 가르지 못한다).
  굴림 양은 순수 구획 `<page-box-reveal>`, 시험은 `tests/test_page_box_reveal.py`(판정 · 가짜 부모 문서 위 회차 끝 동작) — 실제 자리는 사본
  앱을 브라우저로 잰다. 그 잼은 끝자리만 읽는다 — 움직이는 동안 자리를 읽으면 깎임이 재현되지 않고, CPU 제한(4 · 10배)도 함께 돈다.
  시작 높이가 되살아나는 것은 Streamlit 1.63 expander 의 비공식 동작에 기대므로 판올림 때 다시 본다. CPU 10배 제한으로 잴 때는 12초 이상 기다린다.
- `src/capa_simulation/components/sidebar_style.py` — 꺼진 단추를 감싼 풍선 칸의 초점 윤곽(`stTooltipHoverTarget:focus-visible` — 1.63 DOM)도 여기다. 탐색 그룹·활성 경로·`Support` 상자 key 와 현재 테마로
  사이드바 스타일 문자열을 만든다. 위젯 생성·HTML 주입은 하지 않는다.
  - 접두어·구역 제목 선택자는 선언 모듈(`sidebar_status`·`navigation.SIDEBAR_SECTIONS`)에서 읽는다 — 빌더에 필수
    인자를 더하지 않는다(`tests/test_sidebar_stylesheet.py`). 선택자가 1.63 DOM 에 기댄다.
  - 화면을 옮길 때마다 소켓으로 가는 시트라 CSS 주석을 싣지 않는다(설명은 파이썬 주석, 9장 「스크립트와 컴포넌트」).
  - 사이드바 multiselect 의 입력 칸 너비를 초점 앞뒤로 같게 둔다(9장 「사이드바 multiselect 는 초점 앞뒤로 높이가 같아야
    한다」) — 화면마다 칸 key 로 따로 걸지 않는다.
  - 스크롤 칸(`stSidebarContent`)에 `max-height: 100dvh` 를 건다 — 폭을 끌 때 스크롤이 맨 위로 가지 않게(9장 「사이드바
    스크롤 칸은 화면 높이 상한을 갖는다」).
  - **팝업 상자**(`sidebar_status.DIALOG_BOX_PREFIX` — 조회 조건 아래 따로 선, 한 번 누르면 팝업이 뜨는 전폭 단추 상자. 지금은
    HOME 「HOME 설정」 하나, 2026-11-02)는 조건 카드와 같은 면·`ACCENT` 아이콘·머리 글자에 오른쪽 끝 `⇕`(팝업이 뜨는 칸)
    표식이다. key 끝 `PENDING_SUFFIX` 면 왼쪽 주황 띠, 잠기면 표식을 걷는다(`tests/test_sidebar_stylesheet.py`).
  - **화면 조작 상자**(`sidebar_status.PAGE_BOX_PREFIX` — 안에 위젯 여럿, 지금은 Space 현황 「Space 도면」 하나, 2026-11-03)는
    `_page_box_style` 이 조건 패널과 같은 면(`NAV_CONTROL_TINT`)·모서리 10px·안 여백(1px 테두리는 패널처럼 페이지의
    `container(border=True)`), 맨 위 제목 한 줄(1rem·700), 이름 줄
    (`condition_field.condition_name_row` — 0.75rem·`TEXT_MUTED`·첫 칸 600)을 건다. 상자 안 단추·토글은 Streamlit 기본 결이다.
  - Streamlit 1.63 이 캡션 칸에 거는 흐림(`opacity`)은 사이드바 구역 제목 설명 · 앱 정보 카드 작은 글 · 조건 패널과 화면 조작 상자 이름 줄에서 걷는다(`opacity: 1`) — 글자가 이미 보조색(`TEXT_MUTED`)이라 흐림이 겹치면 작은 글 대비가 4.5:1 아래로 떨어진다.
- `src/capa_simulation/components/column_filter.py` — 분류 컬럼별 다중선택 필터와 초기화 버튼이다. 거른
  프레임을 돌려준다.
  - `value_labels` 는 표시만 바꾸고 값·세션 저장값은 원본이다. 표시명 칸은 `ProcessLabels.unique_format_func` 로
    가르고 `prune_list_selection` 으로 되쓴다. 카드가 없는 회차에는 `apply_column_filters` 가 세션 선택만 읽는다.
  - 「필터 초기화」 를 잠그는 쪽(적용하지 않은 편집이 있을 때)은 까닭 풍선을 `disabled_help` 로 준다(설계 규칙 UI-INP-07).
  - 걸러도 모든 행이 남으면(「Select all」 로 다 고른 중간 상태) 원본 사본을 돌려준다. `.loc` 는 모두 참인 마스크에도
    `RangeIndex` 를 일반 `Index` 로 바꾸는데, `st.data_editor` 신원이 인덱스 꼴을 품어 새 위젯으로 서고 표 전체를 다시
    보낸다(`tests/test_column_filter.py`).
- `src/capa_simulation/components/process_labels.py` — 원본 공정명을 화면 표시명으로 바꾸는 유일한 지점이다
  (규칙은 8장 「화면은 표시명, 파일은 원본」).
  - `ProcessLabels.frame` 은 화면용 복사본, `series` 는 행마다 바꾼 것과 같은 값·dtype 이다
    (`tests/test_process_label_series.py`). CSV 로 내보낼 프레임에는 쓰지 않는다.
  - `unique_format_func` 는 선택 상자 하나의 `format_func` 로 겹친 글자를 「표시명 (원본)」·「 (2)」로 가른다.
  - `category_axis` 는 공정을 범주 축에 늘어놓는 그림의 범주 값(원본)과 눈금·hover 글자(표시명)다(8장 ③).
    `ProcessLabelFormatter` 는 값을 글자로 주고받지 않는 자리(버튼·Figure)용이다.
  - `ProcessLabels.version` 은 HOME Figure 캐시 키 원소이고 계산 캐시 키·`content_token` 에는 넣지 않는다.
- `src/capa_simulation/components/stop_examples.py` — 계산 멈춤 글 속 예시 키(서비스 글의 `예시 [{…}]` dict 꼴)를 화면 글을
  지을 때만 「YY.MM 공정 표시명 양산구분」 으로 바꾼다(`readable_examples` — 2026-11-11 입력 점검 검토 보드 F7 (나), 설계 규칙
  UI-DAT-10). 월 → 공정 → 양산구분이 앞이고 그 밖의 칸(제품정보 · 걸린 값)은 서비스 글 차례대로 값만 뒤에, 공정은 선택 상자와 같은
  판정(`unique_format_func`)으로 짓는다 — 표시명이 다른 공정의 원본 이름과 겹치면 「표시명 (원본)」 이고, 견주는 공정은 같은 예시
  묶음의 공정과 이 세션에 불러온 리비전의 보유 공정(`RQ_MODULE` 공정 — Admin `Proc Rename` 겹침 경고 `AD-06` 과 같은 범위,
  `_owned_processes`)이다(2026-11-11 다음 배포 물음 보드 「F7 뒤 ③」 (나)). 보유 공정은 표시명이 있고 예시가 있을 때만 세션 칸에서
  읽고(DB 를 열지 않는다), 실행 문맥이 없거나 불러온 리비전이 없으면 예시 묶음 안에서만 가른다. 읽지 못한 예시(`nan` 따위 · dict
  아닌 목록 · 빈 목록)는 원문 그대로다. 물결표 막기보다 먼저 부른다. 마크다운 자리(알림 전문 · 풍선 · 거부 상자 · 결과 알림)로 가는 글은 `markdown_examples` 로
  짓는다 — 예시 칸 값(공정 표시명 · 원본 이름 · 그 밖의 칸 값)을 `literal_markdown` 으로 막고(표시명도 사람 글 — 9장) 글 전체의
  물결표를 막는다. 앱이 지은 월 `YY.MM` 은 막지 않는다. 평문 자리(`bootstrap_error_message(markdown=False)`)는 막지 않은 글이다.
  부르는 자리: `page_bootstrap.calculation_stop_notice(labels=)` · `bootstrap_error_message(labels=)`(멈춘 계산 화면 넷과 계산을 먼저
  보는 화면 — 공정 Capa 상세 · 제약 시뮬레이션 · 재공 현황 · 가용설비 현황 비교 · 필요 단축 일정(달 범위를 다시 꺼내다 멈춘 글은 공용
  길 `shortening_source` 가 원문으로 지어 그 예외 `ShorteningStop.cause` 와 함께 돌려주고 패널이 같은 예외로 표시명 글을 다시 짓는다 —
  `_named_stop`. 공용 길은 표시명을 읽지도 받지도 않는다), 그물 `tests/test_stop_examples.py`. Space 「필요 단축」
  보기(`space_shortening_view`)의 멈춤 글은 표시명 없이 예시 행만 이 꼴이고 공정은 원본 이름이다(`bootstrap_error_message(labels=None,
  example_rows=True)`, 달 범위는 공용 길이 실은 `cause` 로 다시 짓는다 — `_original_name_stop`. 원본 공정소분류 길, 결정 D10 ·
  `tests/test_process_label_boundaries.py` 그대로 — 2026-11-11 다음 배포 물음 보드 「F7 뒤 ①」 (다)).
  가용설비 현황 비교의 알림 `EQ-08` 은 전문만 화면 꼴 평문이고 「원본 오류」 · 지문은 원문이다(`labels=None` — 표시명만 고쳐도 알림이
  다시 서지 않게)),
  `capacity_gate` 의 저장 · 지정 · 파생 저장 경고(`labels` 는 표시명을 내는 함수 — 끼울 오류 글이 있을 때만 부른다), 등록
  경고(`bigdataquery_registration`), 자동 갱신 「지금 실행」 결과 알림(`auto_official_update_tab._hold_run_result` — 기록 표 「사유」
  칸은 예시 행이 원문이고 개발자가 아니면 BigDataQuery 실패 원문 · 서버 단계 안내만 `diagnostic_message` 로 걷는다). 서비스 글 · 리비전 메모 · 저장 검사 견줌(`_error_kind`) · 사내 집계 · 자동 갱신 기록은 원문이다. `process_labels` 를
  실행 때 불러오지 않는다(`page_bootstrap` 이 이 조각을 부르고 `process_labels` 가 `page_bootstrap` 을 부른다 — 표시명은 인자로만).
  입장 화면 Summary 의 실패 글(`intro_summary._unavailable` — 「공식버전 요약을 만들지 못했습니다: <예외 종류>: <원문>」)도 원문이다 — 공식 지정 검사가 계산이 멈춘 리비전의 지정을 막으므로 예시 꼴로 다시 짓지 않는다.
- `src/capa_simulation/components/process_rename_management.py` — Admin Area `Proc Rename` 탭. 공용 공정 표시명의
  CSV·Excel 붙여넣기·직접 편집과 저장이다. 저장은 공용 프로필 교체이고 리비전을 만들지 않는다. 공용 버전 줄은 「직접 편집」
  제목 옆이다(`profile_caption.render_profile_heading`, 그림 메모 g18). 그 제목 줄(`HEADING_ROW_KEY`) 오른쪽 끝에 「보유 공정
  n개」 팝오버(원본 공정 목록 표 — `AVAILABLE_POPOVER_KEY`) · CSV 다운로드 · Excel 붙여넣기가 선다 — 단추 줄 · 접힘 줄을 따로
  세우지 않는다(2026-11-09 사용자 보드 T3 · T7). 버전 줄은 사람이 적은 변경 메모를 실어 길이가 정해져 있지 않아 서식
  (`heading_row_css`)이 단추 칸(`HEADING_TOOLS_KEY`)을 줄지 않는 한 덩이로 줄 오른쪽 끝에 두고 제목 칸(`HEADING_BOX_KEY`)이
  남은 폭에서 버전 줄을 제목 곁에 접는다 — 제목 칸 바닥(`HEADING_MIN_WIDTH`, 보유 공정 밖 표지가 서면 `HEADING_MARK_ROOM` 을
  더함)과 단추 칸을 한 줄에 못 담으면 단추 칸이 통째로 다음 줄 오른쪽 끝이다(설계 규칙 UI-LAY-11 · UI-ACC-02).
  - 직접 편집 저장은 버전 대조(`BASE_VERSION_KEY` → `expected_version`, 어긋나면 `ProfileVersionConflict`)다. 최신을 보고 고친
    표가 그 저장본과 같으면 쓰지 않고 폼 안 저장 줄 바로 아래 칸에 「바뀐 것이 없습니다」 를 적는다(개선 I5 — 9장 「바꾼 것 없는
    저장」, 자리는 2026-11-07 g8-16).
  - 저장 줄(`SAVE_ROW_KEY`)은 오른쪽 끝을 표 도구 막대 자리로 비우고(`toolbar_room_css`) 표 앞 띄움이 없다 — 저장 줄 → 표
    14px(2026-11-10 사용자 그림 메모 admin-rename, 9장 「표 도구 막대」).
- `src/capa_simulation/components/display_order_management.py` — Admin Area `표시순서 관리` 탭. 공용 표시순서
  규칙의 검증·CSV·붙여넣기·범위별 직접 편집과 원자 교체다. 저장은 공용 프로필 교체이고 리비전을 만들지 않는다.
  저장 성공과 그 저장의 표시명 경고(성공 칸 안), 저장된 겹침 경고는 각각 늘 서 있는 칸에 서서 저장(`st.rerun()`)
  뒤 경고가 생기고 빠져도 아래 직접 편집의 자리가 그대로다(9장 「조건부 알림」).
  - 직접 편집 저장은 Proc Rename 과 같은 버전 대조(`BASE_VERSION_KEY` → `expected_version`)다. 범위 하나만 고쳐도
    프로필 전체 version 을 본다 — 편집표가 `num_rows="dynamic"` 이라 데이터가 신원에 들어가, 남의 저장으로 범위 줄이
    바뀐 회차에는 편집표가 새로 서며 적어 둔 편집을 버린다. 대조가 없으면 지금 저장본을 다시 쓰며 version 만 올리고
    「저장했습니다」를 띄웠다(2026-10-26 E2E, `tests/test_display_order_management.py`). 빠른 두 번 누름은 Proc Rename 과
    같은 `write_guard` 표지(제 저장 표지·충돌 표지)로 거른다(9장). 최신을 보고 고친 범위를 합친 전체 규칙이 그 저장본과
    같으면 쓰지 않고 폼 안 저장 줄 바로 아래 칸에 「바뀐 것이 없습니다」 를 적는다(개선 I5 넓힘 — 9장 「바꾼 것 없는 저장」, 자리는
    2026-11-07 g8-16). 표에 화면 표시명을 적은 분류컬럼이 남았으면 저장 줄 아래(「바뀐 것이 없습니다」 와 같은 칸 — 작은 결정 d5)에 같은 판정
    (`display_label_mistakes`)의 표시명 경고도 그린다 — 막지 않고 알리기만 한다(2026-11-02 결정 A3 — 창이 지난 뒤의 누름에 「바뀐 것이 없습니다」 만 서서 표의 표시명이
    정렬에 걸리지 않는 것을 알 길이 없었다).
  - 표 위는 두 줄이다(작은 결정 d7 · 그림 메모 g18): 「직접 편집」 제목 + 공용 버전 줄(제목 곁에서 낱말 사이로 접힘 — 제목 칸은
    줄 폭에서 범위 고르기 둘 몫 512px 를 뺀 폭까지) + 범위 고르기 둘이 한 줄, 저장 · 변경 메모 줄 오른쪽에 CSV 다운로드 ·
    Excel 붙여넣기(폼 앞 칸에 그려 서식 `ACTION_ROW_CSS` 로 얹음 — 폼에 넣을 수 없는 위젯)가 한 줄이다. 줄 맨 끝은 표 도구 막대
    자리(`TABLE_TOOLBAR_ROOM`)로 비워 두 단추도 그 앞에 서고 표 앞 띄움이 없다 — 저장 줄 → 표 14px(2026-11-10 사용자 그림 메모
    admin-order). 키보드 Tab 은 범위
    고르기 → CSV → Excel → 저장 → 변경 메모 → 표 차례다(보이는 차례와 맞출지는 결정 대기 — `docs/TODO.md`).
- `src/capa_simulation/components/scenario_edit_bar.py` — 편집 화면 원본의 토큰(`source_token` — 기준정보 버전·
  리비전·조회기간·줄 차례 지문)과 원본이 바뀌면 편집기를 비우는 `reset_editors_on_source_change` 다. 생산 계획·기준 정보가 쓴다.
  - 줄 차례 지문만 바뀌어 적용 전 편집을 버린 회차는 결과(`SourceReset.row_order_dropped`)를 사건 알림 `ST-09`(조치
    필요 — 알림창 · Alarm, 자리에 그리지 않음)로 한 번 알린다(`show_row_order_reset` — 매 회차 같은 자리에서 불러 이벤트 칸
    한 자리를 쓴다). 앞 토큰이 없으면(첫 회차·시나리오 전환이 지운 뒤) 알리지 않는다. 줄 위치로 남지
    않는 상태(PKG PLAN 붙여넣기 대기와 그 표 위의 편집, 기준 정보 STEP 상자)는 `order_free_keys` 로 넘겨 차례만 바뀐 회차에 남긴다.
  - 화면이 스스로 적용한 편집은 `mark_own_change` 로 적어 그 적용이 건드린 편집표만 비운다. 편집 되돌리기는
    `components/scenario_status.py` 의 팝업이 맡는다.
  - 적용 · 반영 성공 알림의 「리비전으로 남기려면 … 「신규 리비전 저장」을 누르세요.」 꼬리는 `with_revision_save_tail` 하나로 붙인다 —
    그 단추가 서는 화면 등급(`scenario.revision_save` — 실무자부터, 운영 서버가 아닌 곳은 늘)에만(열람은 적용은 하지만 그 단추가 없다).
  - `register_pending_edits` 로 화면이 제 편집표·붙여넣기 대기·표 초안을 적고 사이드바가 `pending_edit_labels` 로 앞 회차
    목록을 읽는다. `page` 는 파일 이름 리터럴이다(`tests/test_pending_edit_registry.py`). 화면 탭 줄은 같은 규칙의
    화면별 판(`pending_edit_pages` — 편집표 몫·붙여넣기 대기 몫·표 초안 몫 `drafts`)으로 점과 떠날 때 물을 것을 정한다.
- `src/capa_simulation/components/module_slot.py` — 아직 없는 화면 · 칸이 들어올 점선 자리 한 벌(`slot_html` — 제목 ·
  표지 한 줄 · 높이만 받는다, UI-LAY-10). 모듈 화면 자리(`module_slot_html` — `st.html` 하나, 제목 「모듈 화면 자리」 ·
  표지 「모듈 연결 대기」(원천 미연결 화면의 「… 연결 대기」 와 같은 꼴 — 그리는 길이 없어 약속 문장을 두지 않는다), 테두리
  `BORDER_STRONG` · 면 `SURFACE_SUBTLE` · 글 `TEXT_MUTED` 토큰이라 밝게 · 어둡게 모두)와 실행 관리 머리의 「이행 현황판 자리」(운영
  서버에서는 개발자에게만)가 그것을 부른다. 그 자리만 든 화면 한 벌
  (`render_module_slot_page(title)` — 머리말(제목뿐 — 배지 줄 없음, 성숙도는 화면 탭 「구현중」 표지 · `PageSpec.in_progress`, 2026-11-09 보드 T8) + 자리). 생산 진도 머리와 샘플 페이지 셋이 이름만 넘겨
  같은 꼴로 그린다. 데이터를 읽지 않는다. 모듈이 이 자리에 그리는 길이 생기면 그 창구가 여기서 갈린다(`docs/TODO.md` 2장 「생산
  진도 화면 내용」).
- `src/capa_simulation/components/page_link.py` — 다른 화면으로 건너가는 링크다. `st.navigation` 이 없는 단독
  실행(테스트)에서는 문구로 물러선다(`fallback` 으로 그 글을 줄 수 있다 — 「도면에서 보기」). `disabled`·`help` 는
  `st.page_link` 그대로다 — 꺼진 링크가 자리를 지키고 풍선이 까닭을 말한다(공정 Capa 상세 머리 「이 공정 제약 시뮬레이션」).
  1.63 은 꺼진 링크를 `<a disabled>` 로 그려 읽기 도구가 꺼졌다고 읽지 않으므로, 툴바 iframe 의
  `disabled_link_aria_script` 가 부모 문서의 화면 링크(`stPageLink-NavLink`)마다 `aria-disabled="true"` 를 달고 다시
  켜지면 뗀다(`disabled` 속성 바뀜과 새로 붙은 칸만 보고 SVG 안은 건너뛴다 — `tests/test_disabled_link_aria.py`, node).
  꺼진 Streamlit 단추·입력은 진짜 `disabled` 라 따로 달지 않는다.
- `src/capa_simulation/services/product_type.py` — 제품타입(HBM·EDP-TSV)이 가르는 `WF 구분` 규칙의 단일 근거다.
  두 값 집합을 일부러 따로 선언하고 EDP-TSV 의 `Top` 을 `Top_e` 로 가르는 `apply_edp_wf_division` 을 갖는다.
  - 변환 지점은 `core_data_derivation.build_q_core_data` 한 곳이다 — 두 층에서 바꾸면 조인 한쪽만 바뀐다.
    입력·DB 에는 `Top_e` 가 없어 표시순서 규칙은 `display_order._with_edp_top_rule` 이 파생한다.
  - 원천 표기는 대문자 `TOP` 이다 — 값 대조는 `frame_contracts.match_key` 로 하고 저장·화면에는 원천 표기를 쓴다.
  - Dummy 목록은 둘이다 — 산식을 받는 `DUMMY_DIVISIONS_BY_PRODUCT_TYPE`(HBM `Dummy`)과 행을 빼는 Dummy 계열
    `DUMMY_SERIES_DIVISIONS_BY_PRODUCT_TYPE`(HBM `Dummy` · `Top_Dummy`, 이름 `TOP_DUMMY_DIVISION`). 두 목록은 따로 고친다
    (6장 「부하량」).
  - 공정별 부하 산출 예외가 줄을 가르는 이름 `BUFFER_DIVISION` · `CORE_DIVISION` 도 여기 둔다 — `HBM_WF_DIVISIONS` 튜플은
    그대로이고, 예외는 Dummy 계열 목록이 아니라 `TOP_DUMMY_DIVISION` 하나를 읽는다(6장 「공정별 부하 산출 예외」).
- `src/capa_simulation/services/performance_actuals.py` — 효율·UPEH·수율 세 실적 화면이 공유하는 Gap·우선순위
  계산과 합성 데모다(규칙은 6장). Gap 의 뜻은 `MetricSpec` 이 갖고 데모는 `dynamic_capacity.DEMO_PROFILES` 다.
- `src/capa_simulation/services/legacy_comparison.py` — 원천에 보존된 기존 결과와 신규 계산을 같은 단위로
  대조한다(실행 `scripts/compare_legacy_results.py`).
  기존 결과는 원천 `raw_data.core_data` 에 보존된 컬럼에서 그대로 대조하고, 따로 결과 표(`RQ_LEGACY_RESULT` 같은)를 두지 않는다.
  - 기존 컬럼은 계획 한 줄 × `WF 구분` 에서 접은 뒤 대조 키로 합산한다 — 대조 키에서 접으면 서로 다른 계획
    줄이 뭉개진다. 정식 대조 `COMPARISONS` 는 Wafer·Density·Chip(계획 줄 키) 셋이다.
  - 「계획 행으로 접음」 갈래(`plan_row_frame` · 지표 `PLAN_ROW_METRIC`)는 같은 Wafer 대조를 계획 행(`plan_row_mask`
    이면서 공정이 빈 행)만 넘겨 한 번 더 한다 — 원천 `WF수(매)` 가 경로 행마다 갈려 정식 대조가 그 칸을 `값 불일치` 로
    떨어뜨리기 때문이다. `compare_metric` · `_legacy_totals` · `COMPARISONS` 는 그대로이고(소요대수 대조가 같은 접기를
    쓴다), 넣지 않은 행 · 칸은 `plan_row_diagnostics` 가 개수로만 센다(계획 행 밖 갈림은 경로 값 가르기와 같은 행 ·
    허용으로 본다 — `Area_Name` 있고 양수인 행, `ROUTE_SPLIT_TOLERANCE`). 사내 확인 스크립트는 같은 갈래를 요약 `8-2P` 로
    싣는다(10-1).
  - 사내 실데이터는 분포·개수로만 가른다(`difference_distribution`·`ratio_groups`·`scaling_check`·
    `fold_route_cells` 등 → `scripts/inspect_real_data_checks.py`).
  - 지표를 더하면 두 스크립트의 계산 사전(`LOAD_BUILDERS`)도 더하고, 산식이 바뀌면 `FORMULA_INPUTS` 도 고친다.
    환산 UPEH 는 `hourly_rate` 가 `unit_capacity.converted_upeh` 를 부르고, `time_agreement`(UPEH × ST ÷ 60)는
    그 모듈의 `ST_MINUTES_PER_HOUR` 를 쓴다 — 식을 복제하지 않는다.
  - 대조 키 `COMPARISON_KEYS` 는 Stack 뒤에 `CUSTOM` 을 싣고, 계획 줄 키 · 소요대수 대조 키는 계약에서 나와 저절로 싣는다.
    기존 쪽은 원천(`raw_data`)에서 다시 파생하는데 0039 전 리비전은 CUSTOM 이 모두 빈 값 표지라, 원천에 옛 조회문 값이 남아
    있으면 모든 키가 한쪽에만 남는다. 그래서 `source_custom_aligned(raw, tables)` — 받은 리비전 표 가운데 CUSTOM 키 표가 모두
    표지뿐(칸 없음 · 빈 값 포함)이면 원천 CUSTOM 칸을 표지로 바꾼 사본, 아니면 원천 그대로 — 를 파생 앞에서 한 번 부른다
    (`inspect_real_data_checks.load_source` · `compare_legacy_results.main`). 원천은 고치지 않는다.
- `src/capa_simulation/components/tab_state.py` — 열린 탭을 서버가 알게 하는 `stateful_tabs` 와 판정
  `tab_is_hidden` 이다. 차트가 든 탭은 반드시 이것으로 만든다 — 숨은 탭의 Plotly 표는 글자 폭이 0 으로 재진다.
  다른 화면에서 그 화면의 탭 하나로 보낼 때는 기억 칸만 적는다(`remember_open_tab` — 위젯 키는 쓰지 않는다. 안쪽 탭이면
  바깥·안쪽 기억 칸을 함께 적는다). 탭 안의 탭은 바깥 본문 안에서 늘 부르므로 바깥이 숨어도 안쪽 고른 탭의 `open` 이 참이다 —
  본문 갈래는 둘을 합친 `NestedTab` 으로 판정한다(가용설비 현황 Summary).
- `src/capa_simulation/components/editor_state.py` — 편집표에 고친 것이 남았는가(`editor_has_edits`)와 편집을
  브라우저까지 버리는 초기화(`discard_editor`)다.
  - 키가 있는 편집표는 모두 세대 번호를 붙인 `editor_widget_key` 로 그리고, 버릴 때 세션을 `pop` 하지 않고
    `discard_editor` 를 부른다 — 세션만 지우면 브라우저가 옛 편집을 다음 회차에 되보낸다. key 짓기와 세대 올리기는
    `widget_generation`(`widget_key`·`bump`)이 한다. 폼 밖 표의 key 는 앞 세션의 고침이 새 세션에 되살아나지 않게 세션
    표지를 지나고 폼 안 표는 `in_form=True` 로 뺀다(9장 「앞 세션의 탭」, `tests/test_widget_generation.py` 그물).
- `src/capa_simulation/components/side_panel.py` (+ `side_panel_assets/` CSS · JS) — 편집기 영역 안 두 칸(왼쪽 표 · 오른쪽 칸)의 공용 틀. 칸막이 · 접기 · 폭 기억 · 서식(`side_layout_style`) · 칸 고르기 머리(`render_side_head`) · 다음 고르기(`switch_side`)를 맡고, 화면마다 갈리는 값은 스펙 `SidePanel`(key 앞붙이 · 저장소 이름 · `<html>` 표지 이름 · 처음 폭)이다. 설비 마스터 `MASTER_SIDE` 와 시나리오 목록 관리 `LIST_SIDE`(`capa-scenario-list-side-v1`, `--sls-side-w` · `--sls-top` · `data-sls-side`, 처음 폭 40%)가 쓴다(설계 규칙 UI-LAY-09 · UI-CON-04). 읽을 때 등록하므로 그 편집기를 그리는 회차에만 불러온다.
- `src/capa_simulation/components/popover_field_commit.py` — 팝오버를 Esc 로 닫아도 친 값을 잃지 않게 닫기 전에 글 칸을 확정하는 스크립트다. 칸 값을 팝오버 **밖** 단추가 읽는
  자리(Space 저장 상자의 변경 메모 · 저장자)만 `ESC_COMMIT_PREFIX` key 칸에 넣고, 팝오버 안 단추로 제출하는 자리는 넣지 않는다(Esc 가 취소다). 테마 버튼 iframe 에
  실리고 부모 창 capture 단계에서 Esc 를 먼저 받는 비공식 경로다. 시험은 `tests/test_popover_field_commit.py`.
- `src/capa_simulation/components/save_section.py` — 저장 구획의 「모두 버리기」 확인 팝오버(`discard_popover` — 설비 마스터 · 시나리오 목록 관리, UI-NTF-09).
- `src/capa_simulation/components/grid_shared.py` (+ `grid_shared_assets/`) — 브라우저 표끼리 함께 쓰는 팔레트(`grid_palette`) · 받은 값 읽기(`state_value` · `outbox_value` · `outbox_mount`) · 자산 잇기(`joined_assets`) · 떠나기 조각 글(`leave_js`) · 묶음 길이(`batch_ms` — 개발 실행 줄 `CAPA_DEV_BATCH_MS` 덮어쓰기, 편집기 구역 끄개가 꺼지면 그보다 먼저 모든 편집기가 `ORDINARY_SEND_MS` 0.3초 — 시험 `tests/test_grid_shared_batch.py`). 조각은 `nav.js`(`<grid-nav>`) · `outbox.js`(`<grid-outbox>` — 보낼 목록 · `boxBusy`) · `dom.js` · `leave.js`(떠나기 신호 · 편집기 명부 · 구역 회차 표지 — 9장 「구역 회차 규칙」 R8, 시험 `tests/test_leave_assets.py`) · `cells.css`(칸 상태 차례 그대로 · 꺼진 단추를 감싼 칸의 풍선 `.emg-tip`) · `changes.css`. 등록이 없어 어디서 불러도 된다.
- `src/capa_simulation/services/grid_outbox.py` — 출납 고르기(`pending_ops` · `MOUNT_LIMIT`)와 앞 세션 op 빼기(`this_session` — 두 표의 `base` 는 `세션 표지:나머지` 꼴이다) — 설비 마스터 표와 시나리오 목록 표가 함께 쓴다. op 의 뜻과 `base` 대조는 부르는 쪽 몫이다.
- `src/capa_simulation/services/scenario_list_edits.py` — 시나리오 목록 관리의 순수 판정(streamlit · persistence 를 부르지 않는다): op 접기(`fold_ops` — `name` · `move` · `revert` · `open` · `pick`), 지금 저장본에 맞추기(`reconcile`), 막힘(`list_problems` — 규칙 글은 `ListRules` 로 받는다), 수 넷, 네 마운트 data(「점검」 칸 `checks_payload` — r · 리비전명 · 계산, 이름 고치기 없음), 저장 계획(`save_plan`) · 지문(`draft_fingerprint`).
- `src/capa_simulation/components/scenario_input_check.py` — 목록 관리 「점검」 칸(2026-11-11 입력 점검 보드 답 q1 ~ q7). 이 칸 전용 리비전 표(`CHECKS_KEY` — 같은 `picked`, 「계산」 칸은 이 세션에서 센 리비전만 글 · 나머지 「—」 — 세션 칸 `CHECK_LABELS_KEY`, 부하 예외 선언 판이 바뀌면 버림 `CHECK_LABELS_ROUTE_KEY`) · 칸 머리 한 줄(「rN · 전체 기간 YY.MM–YY.MM」 — 기간은 계산이 본 달, 곧 계획과 달 축이 있는 계산 입력 표의 달을 합친 범위(`revision_input_check.calculation_period` · `capacity_gate.INPUT_CHECK_PERIOD_TABLES` — 2026-11-11 검토 보드 F5 (가))) · 묶음 줄(단계 · 이름 · 수 · 부제, 「행 보기」 · 「그 화면으로」, 펼침의 앞 칸 · 앞 행 · 「넓게 보기」 · 묶음 CSV)을 그린다. 멈춤 부제 풍선은 계산 멈춤 알림 전문이되 첫머리가 그 리비전 「rN」 이다(`calculation_stop_notice(place=)` — 입력 점검 검토 보드 F7 (나)). 셈은 고른 리비전 하나를 칸이 열린 회차에만(`capacity_gate.input_check_verdict`, 숨은 탭 회차는 세지 않음), 「그 화면으로」 는 콜백에서 고른 리비전을 불러온 뒤(미저장 편집이면 사이드바 팝업) 도착 칸을 적고 `page_tabs_state.queue_switch`(`tests/test_scenario_input_check.py`). 도착 탭 key 중 생산 계획 · 산출 결과 것은 그 화면과 함께 쓰는 `navigation` 한 벌(`LOAD_CONVERSION_TAB_KEY` · `CALCULATION_RESULT_TAB_KEY` — 세션 키 한 주인, `tests/test_session_key_collisions.py`)이고 탭 라벨은 화면 글과 시험이 맞댄다.
  「계산」 칸의 「확인 n」 은 수가 0 이 아닌 확인 필요 묶음 수다 — 측정률 1.0 가정은 들고, 등록 때 뺀 원천 행과 맨 아래 접힌 한 줄 「규칙대로 셈에서 뺀 것」(`RULES_TITLE` — 펼치면 두 표)은 들지 않는다. 「계산」 칸 글은 세션 칸에 리비전마다 두되 오래된 것부터 64개(`LABEL_MEMO_LIMIT`)를 넘으면 빼고, Density 환산만 멈춘 리비전도 멈춤 줄을 둔 채 뒤 묶음을 그대로 센다(`DENSITY_STOP_KEEPS_COUNTS`). 경로 묶음 머리 수는 소요대수에서 뺀 경로 가운데 PKG Buffer 밖을 뺀 전부이고, 부제 「그 가운데 부하가 붙은 경로 n」 은 머리 수가 0 이면 비운다. 내려받기는 묶음 CSV 하나뿐이고(전체 CSV 없음 — 파일은 원본 값, 화면은 공정 표시명 · 까닭 표시명 `REASON_LABELS`), 측정률 가정 줄은 행 목록 없이 표 · 경로 수 · 달 한 줄이다. 「그 화면으로」 도착지는 묶음마다 `arrival_for` 가 정하고(측정률 가정은 표가 하나면 기준 정보 그 종류, 둘이면 기준 정보 화면), 화면 탭 상한을 먼저 보며(`refused_at_tab_limit`), 수 0 · 셀 수 없음 · 갈 곳을 말하지 않는 멈춤에는 두지 않는다. HOME · Static Capa · 생산 계획 Guide 의 꼬리 글은 이 칸을 가리키고 저장된 리비전을 센다고 말한다.
- `src/capa_simulation/components/scenario_list_state.py` — 목록 초안의 세션 칸(`load_draft` · `store_draft` · `list_has_edits` · `pending_count`)과 마운트 key · 목록 관리 두 칸의 편집기 구역 key(`LIST_SCOPE` — 「점검」 칸 콜백도 이 구역에서 올린다), 「목록 관리」 · 「점검」 글(`LIST_MODE` · `SIDE_CHECK` — 경고 탭 길과 화면 위젯이 함께 쓴다), 경고 줄 「그 화면으로」 를 누른 리비전 칸(`CHECK_TARGET_KEY` — 경고 줄이 대상 `CHECK_TARGET_KIND` 를 들고 다니다 알림 칸이 탭 길을 다 연 회차에 그 콜백이 `queue_check_target` 으로 적고, 같은 회차의 「점검」 칸 `scenario_management._aim_at_check_target` 이 한 번 꺼내 고른다 · 상세 칸 회차에는 꺼내지 않는다 · 사라진 시나리오는 버린다 · 쓰지 않고 남은 것은 다음 앱 전체 회차 앞에서 알림 칸이 버린다 `expire_check_target` — `CHECK_TARGET_FRESH_KEY`, 2026-11-11 다음 배포 물음 보드 F4 뒤 (a)). 등록이 없어 화면 탭 줄 · 변경 칩이 이것만 읽는다. 「저장 전 변경 n건」 배지는 `pending_count` 가 아니라 그 회차 칸의 수 셋을 더한 `scenario_management._ListView.pending`(`change_counts` — 순서는 옮긴 줄 수)이다.
- `src/capa_simulation/components/scenario_list_grid.py` (+ `scenario_list_grid_assets/` HTML · CSS · JS) — 목록 관리 브라우저 표(Components v2, 그림자 DOM). 한 등록을 네 자리에 마운트한다 — 시나리오 표 `TABLE_KEY` · 리비전 표 `REVISIONS_KEY` · 저장 전 변경 `CHANGES_KEY` · 「점검」 칸 리비전 표 `CHECKS_KEY`(이름 고치기 없이 「계산」 칩 — 단계 색은 팔레트 `level-*`). 브라우저 → 서버는 상태 값 `outbox` 하나이고 트리거는 없다(`open` · `pick` 도 출납 — 리비전 줄을 누르고 바로 단추를 눌러도 그 리비전에 걸려야 한다). 칸을 쓰는 · 끄는 · 누르는 동안 돌아온 회차는 다시 그리지 않고 받은 data 만 든다(`canRepaint` — 입력칸을 다시 지으면 한글 조합이 깨지고, 누른 사이 줄을 다시 지으면 그 click 이 사라진다). 줄은 다 그리고 `content-visibility: auto`(편집 줄만 `visible`)다 — 끌기 · 낭독기 · `Ctrl+F` 가 깨지지 않는다. 이름 칸 손짓은 연 줄이면 편집, 아니면 먼저 연다. 시험 대역 `tests/scenario_list_fake.py`, 순수 구획 · 가짜 DOM 은 `tests/test_scenario_list_grid_assets.py`. 표 최소 폭은 칸 합이라 긴 이름이 값 칸을 밀지 않고(이름 · 공식버전 · 상태는 말줄임 + 칸 풍선), 리비전 표 높이는 값 줄 · 작업 줄 몫을 남긴다. 두 표 머리는 윗선이 같다 — 작업 줄 높이 + 아래 간격(CSS)이 오른쪽 칸 머리 높이 `SIDE_HEAD_PX` 와 같고, 고르기나 작업 줄이 접히면 시나리오 표 마운트가 둘의 크기를 지켜보며 높은 쪽에 맞춘다 — 오른쪽이 높으면 작업 줄 아래 간격을 늘리고, 작업 줄이 접혀 왼쪽이 높으면 오른쪽 칸 본문을 내린다(`data.side` · `headFit` — 공용 틀은 그대로, 내림은 본문 칸 인라인 `margin-top` 이고 표가 내려가면 거둔다. 접힘 · 쌓임은 CSS 값). 받은 data 에 보낼 op 를 얹은 화면 차례는 한 벌을 쓰고(`currentView` — 칸마다 접으면 누를수록 느려진다), 회차가 부른 다시 그리기는 스크롤을 끌고 가지 않으며(`preventScroll` — 키보드 손짓만 따라간다), 끝에 닿아 꺼지는 이동 단추는 감싼 칸이 초점 · 까닭 풍선을 받고, 저장 전 변경은 되돌린 줄의 초점을 다음 되돌리기로 넘긴다. 그리는 중의 focusout(`S.painting` — `paint` · `repaintCell`)은 부품 밖 이탈로 치지 않아 묶음을 끊지 않는다. 이름 · 차례 고침의 묶음 길이는 결정값 `LIST_SEND_MS` 를 data `sendMs` 로 넘긴다(`grid_shared.batch_ms` — 개발 실행 줄 `CAPA_DEV_BATCH_MS` 덮어쓰기). 깨끗한 편집본의 첫 고침(data `clean` — 화면 탭 점 · 변경 칩 · 떠나기 확인이 늦지 않게) · 줄 고르기 · 되돌리기 · 표 밖 누름 · 창 숨김 · 떠나기 신호는 묶지 않고, 네 마운트가 저마다 편집기 명부에 올라 보낼 것이 남았거나 ack 가 오지 않은 동안 busy 다(9장 「구역 회차 규칙」 R8 — `joinLeaving` · `boxBusy`). 줄 옮기기 단추(↑ · ↓ · ⤒)는 누를 때마다 회차가 돌지 않게 고침과 같은 묶음이다. 값만 보는 등급(data `readonly`)에게는 칸 고치기 · 손잡이 · 줄 옮기기 단추 · 「고친 칸 · 막힘」 범례를 그리지 않고(작업 줄은 머리 맞춤 자리라 빈 줄로 남는다) Alt+↑ ↓ 도 옮기지 않으며, 표 밑 「⌨ 키보드 조작」 풍선도 그 등급에게 서는 손짓(누르기 · 방향키 칸 옮기기 · Space · Enter 열기 — `KEYS_HELP_READONLY`)만 말한다 — 표 틀은 `mode` 와 값만 여부로 다시 짓는다(`builtKey` — 「이 등급으로 보기」 를 끝내면 같은 마운트에서 풀린다).
- `src/capa_simulation/components/tab_marks.py` — 적용하지 않은 편집이 남은 탭 이름 옆 점(`mark_pending_tabs`,
  판정 `editor_has_edits`, 색 `PENDING_MARK`)과 종류 단추(`st.segmented_control` — `[data-testid="stButtonGroup"]` 아래
  `role="radio"` 단추의 n 번째) 옆 같은 점(`mark_pending_segments`)이다. 비공식 선택자라 판올림에서 바뀌면 점만 안 보인다.
  표지 낱말은 화면 탭 줄(`page_tabs`)과 한 벌이다 — 주황 점(`PENDING_MARK`) = 적용 · 저장 안 한 편집, 주황(같은 값 `ALERT_CHECK`)
  깔때기 = 이 화면에 없는 공정이 섞임, 강조색 깔때기 = 공용 공정이 걸림, 흐린 「구현중」 = 원천 미연결 화면. 깔때기 · 「구현중」 은
  화면 탭 줄에만 선다 — 모양(점 · 깔때기 · 글)이 달라 같은 주황이 다른 뜻으로 읽히지 않는다(2026-11-09 통합 확인). 화면 안 탭
  이름 곁 수 표지(Admin 계산 알림 탭)는 2026-11-11 입력 점검 보드 q7 로 탭과 함께 걷었다.
- `src/capa_simulation/components/reference_grid.py` — 기준 정보 편집 표 아홉을 범용 편집 그리드(`edit_grid.py`)에 잇는 어댑터.
  표마다 값 형식(`GRID_FORMATS` — 옛 `EDITOR_FORMATS` 를 옮김: UPEH 유효숫자 6 · 효율·측정률 percent
  상한 1 · 여유율 percent · 일수 정수 · 설비대수 소수 둘째 자리 빈칸 = 0), 양식 → 규격·색인·껍데기(`build_grid_table` — 캐시
  `get_edit_grid_base_within`·`get_edit_grid_base`, 키는 편집 캐시 키·표시순서 지문·표시명 지문), inbox 반영(`apply_grid_inbox` —
  지금 고르지 않은 표의 op 도 그 표에), 사이드바 필터 → feed `filters`(분류 사전 코드 — 브라우저가 거른다), 작업 줄(`render_actions` — 알림 칸은
  `render_flash`, 표 도구 막대와 한 줄로 서는 CSS 는 `ONE_LINE_STYLE` 을 `render_edit_grid(page_style=)` 로 넘긴다, 편집 범위 글은
  feed `scope`), 고칠 칸 알림(`error_notice` — 앞 다섯 곳을 분류 표시명 · 월로), 초안 되머지(`merged_template`), 편집기 구역 머리
  표지(`scope_head` — 세션 칸만 읽는다)가 한 곳이다.
  머리 글은 `COLUMN_LABELS` 의 짧은 이름이다(껍데기는 회차마다 새 dict 라 캐시 본문을 고치지 않는다).
  - 출납 콜백(`collect_outbox`)은 op 를 inbox 에 쌓기만 하고, 초안이 없던 표에는 빈 초안 자리(`{"cells": {}, "bad": {}}`)를
    둔다 — 변경 칩·화면 탭 점은 `app.py` 가 본문보다 먼저 세므로(세션 칸이 None 이 아니면) 빈 자리가 없으면
    첫 편집이 다음 조작까지 늦게 선다. 빈 자리는 `draft_from` 으로 None(「변경사항 적용」·단추 점·변경 수에 들지 않음)이고 같은
    회차 본문의 반영이 진짜 초안(또는 None)으로 덮는다.
  - 거꾸로 반영이 초안 칸을 **비우면**(None 이 아니던 칸이 None — Ctrl+Z 로 0칸, 초안 없던 표의 첫 op 가 아무것도 바꾸지 않음)
    `apply_grid_inbox` 가 참을 돌려주고 화면이 한 번 다시 돈다(`st.rerun()` — 양식·색인은 캐시라 싸고, 다음 회차는 inbox 가 비어
    되풀이되지 않는다). 다시 돌지 않으면 본문보다 먼저 그린 변경 칩·탭 점·테마 표지가 다음 조작까지 남았다
    (2026-11-03 마지막 검토 C1). 그 회차의 「다른 화면의 적용으로 … 버렸습니다」 알림은 담아 둔 채(`queue_flash`) 다시
    돌지 정해진 뒤에 꺼낸다(작업 줄 맨 위 `render_flash` 칸 `GRID_DROPPED_FLASH_KEY`) — 먼저 꺼내면 두 회차가 표지를 따로 보내 Alarm 이 「×2」 로 센다.
  - **큰 표 안전 상한**(`CAP_CELLS` 300,000칸 · `CAP_BYTES` 껍데기 본문 400 KB): 넘으면 공용 공정 값(`shared_screen` — 조회 조건 「공정」 칸)과
    「표 조건」 카드 선택(세션 값)으로 고른 줄만, 필터가 없거나 걸러도 넘치면 앞 `CAP_ROWS`(1,000) 줄만 싣고 작업 줄 아래에 표지 한 줄(「큰 표 · 앞 n줄만 실음」 · 줄을
    좁힌 자리 이름을 단 `CAP_FILTERED_NOTICE` 「큰 표 · 공정으로 고른 n줄만 실음」 — `CAP_BY_PROCESS` · `CAP_BY_CARD`, 파란 상자
    아님)을 둔다. 풍선은 `GridTable.cap_help` 이고 그 표에 있는 자리만 적는다 — 카드 없는 표는 「표 조건」 을 적지 않고, 공용 공정이면
    `CAP_HELP_SHARED` 를 붙인다(`CAP_HELP` 는 `{places}` · `{shared}` 틀이고 조사는 넣는 쪽이 `korean_particle` 로 고른다). 바이트 상한을 넘는 표의 전체
    본문은 캐시에 두지 않는다(`get_edit_grid_base_within` 이 None 을 담는다). 실은 줄의 본문은 캐시
    키 표 이름에 `#rows`, 표시명 지문에 줄 지문을 더해 따로 둔다. 초안은 업무 키라 실은 줄이 바뀌어도 제 줄에 남고, 적용·
    붙여넣기 양식·고칠 칸 알림(`full_index`)은 언제나 전체 양식이다. 합성 표본 최대는 UPEH 79,800칸이라 걸리지 않는다
    (사내 실데이터 크기는 다음 배포 런북 셈 줄).
- `src/capa_simulation/reference_grid_keys.py` — 기준 정보 그리드의 이름(UI 모름): 그리드 호스트 key(`GRID_HOST`), 종류 단추 key·
  선택지(`DATASET_KEY`·`DATASETS`·`EDIT_TABLES`), 표마다 초안·이력 세션 칸(`cells_key`·`history_key`)과 inbox·ack·토스트 칸,
  시나리오를 바꾸면 지울 칸(`SESSION_KEYS` — 토스트 번호 칸은 넣지 않는다: 1 로 돌아가면 마운트된 그리드가 마지막 번호와 같은
  다음 서버 토스트를 삼킨다, 2026-11-03 마지막 검토 C2). `scenario_activation`(`_STALE_VALUE_KEYS`)과 `page_tabs`(`EDIT_HOST_KEYS`)가 읽는다.
- `src/capa_simulation/components/plan_grid.py` — 생산 계획 PKG PLAN · 수율 표를 범용 편집 그리드에 잇는 어댑터(2026-11-12 보드 답
  k-a1 · k-a2). 값 형식(`FORMATS`), 양식 → 규격 · 색인 · 껍데기(`build` — 캐시 `get_edit_grid_base`, 키는 내용 지문 · 표시순서 지문),
  0 을 빈칸으로 싣는 양식(`zero_as_blank`), 출납 콜백(`collect` — 빈 초안 자리를 둔다, 기준 정보와 같은 까닭) · inbox 반영
  (`apply_inbox` — 초안 칸을 비우면 참) · 적용 콜백이 먼저 받는 출납(`settle_inbox` — 같은 seq 는 한 번), 막힌 적용 글(`refuse` — 세션
  칸 `SessionSlot` `plan_grid_apply_refusal`, 그 표 작업 줄 알림 칸이 같은 회차에 그린다), 작업 줄(`render_actions` — 「⋯」 메뉴 `more` ·
  알림 칸은 `render_flash`), 그리드 자리
  (`render_grid` — 표가 없으면 표 없는 껍데기), 고칠 칸 알림(`error_notice`), 초안 되머지(`merged`), 편집기 구역 머리 표지
  (`scope_head` — 세션 칸만 읽는다) · 콜백 끝 올리기(`render_actions` · `render_grid` 의 `scope_key`)가 한 곳이다. 표 위 칸 key 와
  한 줄 문턱 · 왼쪽 비움은 `LAYOUTS`(고친 뒤 단추 줄 폭으로 잰 샘플 관측 — 설계 규칙집 4장 「생산 계획 표 위 한 줄」).
- `src/capa_simulation/plan_grid_keys.py` — 생산 계획 그리드의 이름(UI 모름): 표(`PLAN_TABLE` · `YIELD_TABLE`), 호스트 key(`HOSTS`),
  표마다 초안 · 이력 · inbox · ack · 토스트 · 버린 gen 칸, 초안이 있는 표의 양식 지문 칸(`TEMPLATE_DIGESTS_KEY` — 다른 화면의 적용이
  그 표를 바꿨는지 가른다), 시나리오를 바꾸면 지울 칸(`SESSION_KEYS` — 토스트 칸은 넣지 않는다,
  `reference_grid_keys` 와 같은 까닭). `scenario_activation`(`_STALE_VALUE_KEYS` · 「편집 되돌리기」)과 `page_tabs`(`EDIT_HOST_KEYS`)가 읽는다.
- `src/capa_simulation/components/status_metric.py` — 조치가 필요한 지표에 상태색 왼쪽 띠를 붙인 metric
  카드다(`tone="neutral"` 이면 기존 카드). `metric_row` 는 카드를 같은 폭·높이로 세우고 모자라면 줄을 접는다. 둘 다
  서식을 스타일만 든 `st.html`(이벤트 칸)로 보내는데, 팝업 본문처럼 이벤트 칸 자리 수가 갈래마다 같아야 하는 곳은
  `emit_style=False` 로 부르고 `metric_row_style`·`status_metric_style` 을 보이는 HTML 과 한 `st.html` 에 싣는다.
- `src/capa_simulation/components/table_toolbar.py` — 표 제목·부가 설명·CSV 내보내기 한 줄(엑셀 단추 `render_xlsx_download` · ZIP 단추 `render_zip_download`(Admin 「부대공정」 양식 — 풍선 `tooltip`) —
  같은 꼴. 이웃이 글자 단추뿐인 줄은 `render_csv_download(text_link=True)` — 아이콘 없는 tertiary, 시나리오 관리 「점검」 묶음 줄), 표 곁 CSV · 「시트 엑셀」 한 쌍(`render_download_pair` — 「내려받기 ▾」 메뉴 하나(`st.popover`, key 는 부르는 쪽 ·
  `table_heading_row` 는 `download_menu_key(CSV key)`) 안에 CSV 단추 → 내용 폭 엑셀 칸, CSV 가 없으면 메뉴 없이 엑셀 칸만 —
  2026-11-10 답 Q2-7, 설비 마스터 「선택 ▾」 과 같은 꼴. 안의 단추는 `on_click="ignore"` 라 눌러도 메뉴가 열린 채 초점이 남고
  Esc 로 닫힌다. 시트를 나중에 짓는 화면은 돌려받은 칸에 `render_sheet_download`. 공정 Capa 상세 표 도구 줄 · 산출 결과
  대당 Capa · 소요대수 제목 줄(`table_heading_row(sheet=)`) · 가용설비 Static 대비 일정 시트(전환 줄 끝) · 호기 목록(목록 아래)이 쓰고, `tests/test_table_toolbar.py` 가 엑셀 단추를 다른 자리에서
  부르지 않는지 · 쌍의 꼴을 본다. 줄에 선 메뉴(CSV 가 없으면 엑셀 칸)의 높이는 네 자리 모두 28px 하나다(2026-11-11 남은 물음
  보드 C9 — 「구획」 칩 · 「조회 결과 · 표시」 전환 단추와 같은 높이, 메뉴 안 단추는 기본 높이): 메뉴 key 는 접두어
  `DOWNLOAD_MENU_KEY_PREFIX`(「download_menu_」 — `download_menu_key` 가 붙이고, 아니면 `render_download_pair` 가 거절)로
  시작하고 CSV 가 없을 때의 엑셀 칸도 그 key 를 받으며, 높이 서식 `DOWNLOAD_MENU_STYLE` 은 `app.py` 가 매 회차 보내는 앱 전체
  서식 `st.html` 에 한 번 싣는다 — 부르는 자리마다 스타일만 든 `st.html` 을 두면 이벤트 칸에 서서 공정 Capa 상세 본문
  프래그먼트의 이벤트 칸 수가 바뀐다). 표 제목 줄(`table_heading_row`)은 곁에 맨 CSV 단추(35px) · 「내려받기 ▾」 메뉴(28px) ·
  「표시 범위」 칸 무엇이 서든 35px 높이다 — 줄 key 는 `table_heading_row_key(CSV key)`(접두어 `TABLE_HEADING_ROW_KEY_PREFIX`
  「table_heading_row_」 — 메뉴 접두어를 품지 않는다)이고 `min-height` 서식 `TABLE_HEADING_ROW_STYLE` 을 같은 앱 전체 서식에
  한 번 싣는다(2026-11-11 다음 배포 물음 보드 C9 뒤 (나) — 산출 결과 탭을 오가거나 소요대수 「상세」 를 켜고 끌 때 표 윗선이
- `src/capa_simulation/components/monthly_table_base.py` — 두 월별 Plotly 표가 공유하는 상수·텍스트 폭·분류 폭
  (`classification_widths`)과 `go.Table` 두 벌 조립(`build_split_table_figures`), 격자 머리(`add_table_frame` — 바깥 테두리 ·
  머리 밑줄 · 분류 칸 세로선 · 월 경계선)와 분류 칸 반복 접두 생략(`blank_repeated_prefixes`)이다. 행 모델 · 면색 · 행 그룹
  가로선만 표마다 다르다(`tests/test_monthly_table_shared_steps.py` 가 공용 단계 둘을 그 정의 — 도우미 여섯 호출 · 접두
  튜플 판정 — 와 Figure JSON 글자로 견준다).
  - 머리글 글자는 `go.Table` 밖 글자 trace(data[1], `plotly_layout.table_text_layer`)이고 띠는 `table_header_band`
    도형이다 — `go.Table` 머리글은 값 `""`·면 투명이다. 표 칸에 마크업(`<`·`&`·`>`)을 두지 않는다: 마크업 칸은 Plotly 가
    칸마다 그린 뒤 재서 옮겨 열 수만큼 브라우저 스타일 계산이 돈다(합성 표본 표준 목표 131주 표 long task 1.6s 의 대부분,
    `tests/test_plotly_fast_path.py::test_table_cells_carry_no_markup`). 월 면색은 한 열 `[month_row_colors]` 다(Plotly
    가 마지막 열을 되풀이한다). 분류 Figure 폭은 `column_widths` 합(px)이 위 끝이다 — 본문이 분류 폭 + 달 두 칸
    (`MONTH_ROOM_COLUMNS`)을 못 담으면 칸이 같은 비율로 주되 `classification_floor_px`(가장 넓은 칸이 좌우 여백을 다 내주는 폭)
    아래로는 줄지 않고 달 칸이 `MONTH_FLOOR_PX`(80)까지 대신 준다. 그보다 좁으면 분류 칸이 바닥 폭을 지킨 채 자기 컬럼 안에서
    위쪽 막대(`{key}_label_scrollbar`, 월 막대와 같은 높이)로 스크롤한다(2026-11-07 답 narrow).
  - spec 은 `plotly_layout.figure_from_spec` 이 검증 없이 세우므로 Plotly 정규형 dict 다
    (`tests/test_plotly_fast_path.py`). 격자 도우미는 `append_layout_items` 에 모으기만 하고 표 모듈이
    `flush_layout_items` 한 번으로 반영한다(`tests/test_monthly_table_grid.py`).
- `src/capa_simulation/components/scroll_shell.py` — 월별 표·HOME·재공 현황이 함께 쓰는 가로 스크롤 상자와 고정 폭
  캔버스, 분류 칸 폭을 못박는 `split_scroll_columns_style` 이다(월별 표 두 종은 `month_room_px` · `label_floor_px` ·
  `month_floor_px` 로 `min(clamp(바닥, 비율, 라벨 폭), calc(100% - 달 바닥))` 을 건다). key 를 바꾸면 CSS 가 끊어진다. 캔버스는
  `PLOTLY_MIN_CHART_WIDTH_PX`(150 — Streamlit 1.63 이 `width="stretch"` 그림을 그 아래로 그리지 않는다)보다 좁히지 않아 한 달
  조회의 월 칸(100px)에서도 그림이 잘리지 않는다. 폭을 못박지 않는
  변형(`min_width_scroll_rules` · `min_width_scroll_canvas` — 캔버스에 가장 좁은 폭만 걸어 넓으면 칸을 채우고 좁을 때만
  스크롤, 규칙은 호출자 `<style>` 에 섞는다)은 제약 시뮬레이션 그래프와 월별 표 분류 칸(`hide_native_scrollbar=True` +
- `src/capa_simulation/components/month_editor.py` — 월별 Wide 기준정보 표의 공용 조각이다. 기준 정보 편집 표 아홉의 칸
  편집은 범용 편집 그리드(`reference_grid.py`)가 맡고, 여기에는 기준 정보 화면과 생산 계획 화면이 쓰는 것만 둔다.
  - 「Excel 붙여넣기」 팝업은 공개 함수 `paste_dialog`(연 회차 알림 글 `pending_notice` 는 부르는 쪽이 — 그리드는 초안 칸 수 ·
    `dialog_key=` 대신 `host: DialogHost` 를 받아 호스트 프래그먼트 안에서 불린다, 닫기는 `host.close`, 적용 성공은 `host.finish()`,
    본문은 `@keeps_app_run_open`, 입력 위젯 key 는 `paste_widget_keys(editor_key)` 이고 호스트가 닫을 때 지운다)이고
    표 아래 상태 줄의 편집 범위 글은 `month_editor.scope_text`(feed `scope` · `eg_toolbar.js` `tbScope`)다 — 칸 위치 · 오류 문구가 먼저이고
    좁으면 편집 범위 글이 먼저 줄어 풍선으로 읽힌다. 빈 메모 · 요약 · 범위 칸은 접는다. 붙여넣기 팝업(`render_reference_clipboard_form`)·왕복 CSV 에는 필터 이전 전체 표를
    넘긴다(부분 표는 행 집합 검증을 통과해 나머지 공정을 지운다).
  - `float_month_columns`(정수 dtype 월 칸을 실수로 — `st.data_editor` 편집표용, 생산 계획이 그리드가 된 뒤 부르는 화면이 없다)를 둔다. 걸러진 편집표를 원본 전체에 되머지하던
    조각(`merge_edited_months`·`count_month_changes`)은 그리드 횡전개 뒤 부르는 곳이 없어 걷었다(2026-11-03) — 그리드
    초안은 업무 키라 적용이 늘 전체 양식에 덮는다(`reference_grid.merged_template`).
  - `process_labels` 를 import 하지 않는다. 분류 칸 회색 배경은 `classification_styled` 하나가 칸 수 상한까지만 입힌다(생산 계획이
    그리드가 된 뒤 부르는 화면이 없다 — `tests/test_classification_style.py`).
- `src/capa_simulation/services/revision_compatibility.py` — 저장된 리비전이 현재 계산 계약으로 쓸 수 있는지
  **불러오기 전에** 판정한다(활성화 뒤에 죽으면 되돌릴 길이 없다).
  - 지금 막는 것은 `STEP_SEQ`·`MCP_SEQ` 가 빈 저장분과, CUSTOM 키 표(`custom_keyed_tables()` — 계약 `derived_keys` 에
    `CUSTOM` 이 든 표)에 CUSTOM 칸이 없거나 값이 빈(NULL · 빈 글자 · 공백뿐) 저장분이다(`custom_incompatible_tables`). 빈 값
    표지 `"-"` 는 통과하고 빈 표는 건너뛴다. 0039 뒤에는 걸리지 않는 안전망이다(5장 28). 값을 추정해 채우지 않는다.
  - `custom_blank_filled(tables)` 는 마이그레이션하지 않고 0039 전 DB 사본을 여는 확인 스크립트 · 6-3 b 시간 스크립트만 부른다
    (10-1 「0039 전 DB 사본」) — 칸이 없는 CUSTOM 키 표(빈 표 포함)에만 표지 칸을 끝에 붙인다. 0039 가 옛 행에 넣는 것과 같은 뜻이고, 칸이 있는 표는
    빈 값이 있어도 그대로 둬 안전망이 막는다. 스크립트가 견주는 번호(`CUSTOM_MIGRATION`)와 찍는 표지(`BEFORE_CUSTOM_COPY` —
    「사본 0039 전」)도 여기 둔다. 앱의 불러오기 길은 부르지 않는다.
- `src/capa_simulation/services/past_data.py` — 적재 시점 이전 과거 구간 입력의 정규화·검증과 계산 결과 병합이다.
  산출하지 않는다 — Capa 는 확보율에서 곧장 나오고 B/N 순위는 확보율 오름차순이다.
  - 같은 달이 양쪽에 있으면 계산이 이긴다. `display_month_range` 는 HOME 계산 캐시 키의 달이라 HOME 과
    필요 단축 일정이 같은 함수를 쓴다. 빈칸을 0 으로 삼키지 않는다(`_BLANK_AS_ZERO` 가 칸별 규칙).
  - 과거 계획 세부수량에는 부품 칸이 없다 — 분류에 `CUSTOM` 이 있으면 `past_plan_detail_to_wide(multi_part=)` 가 채운다
    (부품을 가르는 제품은 표지 `-` 의 「제품 (-)」 줄, 나머지는 접힌 값이라 계산 구간 행에 붙는다).
- `src/capa_simulation/components/past_data_management.py` — 「HOME 설정」 팝업의 `Past Data` 탭. 한 버전을 공유하는 세
  표를 그 표 상자 안 붙여넣기 칸(`PAST_PASTE_KEY` — 한 번에 한 표, 팝업 안이라 팝업을 또 열 수 없다)으로 세션에 모았다가
  한 번에 저장한다(부분 저장 없음). 「설정」 팝업을 열고 닫는 콜백이 편 칸을 걷는다(`forget_past_paste`).
  - 저장은 저장된 표를 통째로 바꾼다 — 그 경고(`PAST_REPLACE_NOTICE`)는 칸을 편 회차의 알림 `PA-01` 과 저장 단추 툴팁이
    말한다(칸 안 글 · 저장 줄 캡션은 걷었다 — 2026-11-05 검수 static-37). 붙여넣기 칸은 공통 부품(9장 「붙여넣기 · 양식 창」)이고 양식
    내려받기는 그 칸의 작업 줄에 선다. 칸이 펴진 동안 「HOME 설정」 팝업이 그 창이라 크기 손잡이가 서고(`size_key="past"`) 칸을 걷으면
    손잡이도 걷힌다. 저장 단추 툴팁은 공용 설정 · 읽어 둔 표는 닫아도 남는다는 말(`PAST_SHARED_HELP`)도 잇는다 — 팝업 머리 안내
    글을 걷은 자리다.
- `src/capa_simulation/services/process_selection.py` — B/N 집계에 포함할 공정을 저장값·현재 옵션·이 세션이 아는
  공정에서 정한다.
  - 기준 없는 첫 렌더(`seen=None`)는 저장된 포함 목록을 그대로 믿는다(`seen=[]` 와 다르다). 아는 공정은
    쌓이고(`remember_known_processes`), 선택지에 없는 공정은 포함 목록에서 지우지 않는다(`visible_processes`).
- `src/capa_simulation/services/process_picker.py` — 조회기간 최종 확보율을 공정별 최소값·최초 동률 월·유효 월
  수로 요약해 미달·충족·판정 없음 구역을 정한다(입력 순서·원본 키 보존).
  - 경계는 HOME 과 같은 `SecurementThresholds.status` 이고 충족은 유효한 모든 달이 확보일 때다. 소요·가용대수로
    확보율을 다시 계산하지 않는다.
- `src/capa_simulation/components/process_picker.py` — 위 요약을 세 구역의 공정 버튼으로 그린다(긴 표시명은
  한 줄 말줄임, 자동 갱신이 뺀 공정은 `marks` 표지).
  - 콜백·위젯 키에는 원본 공정명을 쓴다. 설명 풍선은 `help` 가 아니라 순번 칸(`home_bn_tile_<i>`)의 CSS `:hover` 다.
  - 확보 기준 미달 구역의 버튼은 이름 오른쪽에 기간 최저 확보율(요약의 `minimum_rate` — 판정과 같은 사사오입 정수 %, `threshold_percent_label`)을 작게 붙인다. 라벨 끝이 아니라 버튼 `::after`(`tile_rate_style`)라 긴 이름은 이름이 먼저 말줄임되고 값은 남는다.
  - 계산 밖 공정(`outside` — 원본 공정 → 빠진 소요기준 글)은 「확보율 없음」 구역 단추에서만 미달 최저 확보율과 같은 `::after`
    자리에 「계산 밖」(`tile_rate_text`)이고 풍선의 확보율 없음 줄이 그 소요기준 까닭(`tile_tooltip_text` — 글은
    `outside_calculation_mark.BASIS_REASON`)이다. 유효한 확보율이 있는 단추(과거 구간 달 등)는 그대로다(`tests/test_process_picker.py`).
- `src/capa_simulation/services/month_columns.py` — 월 축과 연간 Total 열의 규칙이다. Total 은 1~12월이 모두
  조회범위 안인 해만 갖고 그 해 12월 바로 뒤에 들어간다.
  - 축은 하나다 — 표·차트·스크롤 폭이 같은 라벨 목록을 본다. 월 칸 표기 `YY.MM` 은 `month_label` 한 벌이다.
    `leading_past_column_count` 는 과거 구간의 연속된 앞머리만 센다(`build_past_month_labels` 와 함께 면색·스크롤 근거).

- `src/capa_simulation/components/home_preference.py` — HOME `LOB 표시 조건` 카드(맨 위는 부르는 쪽이 넘긴 주요 Case 칩)·
  `Capa LOB 현황` 제목 줄과 「HOME 설정」 팝업의 Preference 편집기 여덟을 그려 공용 프로필에 저장한다. 편집기는 팝업의 앞 네
  탭에 쓰는 묶음대로 선다(`render_home_preference(tabs=)` — 2026-11-04 사용자 검수 home-u01): `비교 · 주요 Case` 는 「비교
  시나리오」 · 「주요 Case」(`home_main_cases`) 나란히(`CASES_COLUMN_WEIGHTS`), `판정 기준` 은 확보율 판정 기준, `선행 · 보정` 은
  선행 B/O · 선행 입고 실적 · 확보율 보정 위아래(앞 둘은 `구분` 칸 폭이 같아 달 칸이 맞선다), `Capa 요약 · 표시` 는 왼쪽
  Capa 요약 · Top5 구간, 오른쪽 주요공정 프리셋. `Capa 요약 · 표시` 는 같은 말 · 빈 줄을 두지 않는다(2026-11-09 사용자 검수 g18) — Capa 요약
  버전 줄에 옛 「공지 중 · 내림」 꼬리가 없고 글 칸 이름은 숨기며(상자 제목과 같은 말), Top5 는 저장 · 하한 · 상한이 한 줄(프리셋
  저장 · 이름 줄과 같은 꼴)이다. 폼마다 알림 칸은 `render_flash` 가 돌려준 칸 하나다(폼 안 빈 칸은 간격을 먹지 않는다 —
  9장 「알림 칸」). 선행 B/O · 선행 입고 · 확보율 보정의 저장 줄(`ADVANCE_SAVE_ROW_KEY` · `ADVANCE_SHIPMENT_SAVE_ROW_KEY` ·
  `EXECUTION_SAVE_ROW_KEY`)은 오른쪽 끝을 표 도구 막대 자리로 비우고 표 앞 띄움이 없다 — 저장 줄 → 표 14px(2차 보드 Q2-2,
  서식은 제목 줄 캡션 — 9장 「표 도구 막대」). 판정 기준은 띄움 그대로다. 숨은 탭도 모두 그린다(`stateful_tabs`) — 탭을
  옮겨도 폼의 고친 칸이 남는다. 상자 하나하나(저장 단추 · 저장 단위 · key · 저장 길)는 놓는 자리와 상관없다. 팝업 머리 안내 글은 없다 — 「모든 사용자가 함께
  쓰는 공용 설정 · 저장하지 않고 닫으면 고친 칸은 사라짐」 은 저장 단추 일곱의 풍선(`SHARED_SAVE_HELP`)이 말한다.
  - 구획 제목 줄 `render_section_title_row` 는 선택 인자 `mark` · `mark_help` 로 제목 오른쪽 끝에 작은 회색 표지(`st.caption` + ⓘ 풍선)를
    단다 — 없으면 그리지 않고, 지금 쓰는 곳은 「상세 B/N 공정」 줄의 「계산 밖 n공정」 하나다(줄 서식은 `home_rendering.dashboard_title_row_style`).
  - 토글은 모두 여기서 `value=` 없이 만들고 기본값은 칸이 없을 때만 심는다(`tests/test_scenario_activation.py`).
  - 저장은 **버전 대조**이고(선행 B/O·선행 입고 실적은 대조 없이 `write_guard.save_once` 만) 월별 값은 보이는 달만 갈아
    끼운다(`services/monthly_amount.py`). 주요공정 프리셋은 묶음
    전체 교체라 편집 카드(프래그먼트)가 회차마다 캐시에서 다시 읽는다(`tests/test_home_key_process_fragment.py`).
    이름·공정 칸의 key 끝에는 고칠 프리셋 저장본의 지문을 붙여, 남의 저장에 거부된 뒤 두 칸이 함께 저장본으로 선다(5장 25).
    판정 기준 월별 표의 key 끝에는 그 회차가 그린 저장본 version 을 붙인다(`threshold_widget_key` — Top5 구간과 같다. 남이
    저장하면 보내지 않은 편집은 버려지고 최신이 서며, 제출 회차면 대조 값이 옛 version 이라 거부된다 — 9장 「본 값과 보이는 칸」).
    바꾼 것 없는 저장(판정 기준·확보율 보정·Capa 요약·Top5 구간·주요공정 프리셋·선행 B/O·선행 입고 실적)은 쓰지 않고 그
    폼 알림 칸에 「바뀐 것이 없습니다」 를 적는다(개선 I5·넓힘 — 9장 「바꾼 것 없는 저장」).
    프리셋 「기본으로」·「삭제」 의 알림은 빠른 둘째 누름(잠긴 단추에 닿아 아무것도 하지 않는 회차)에도 다시 선다
    (쓰기 직후 `write_guard.note_notice` 로 적고 `flash.render_flash` 가 다시 그린다, `tests/test_key_process_preset_messages.py`).
    고치지 않은 「프리셋 저장」 의 「바뀐 것이 없습니다」 도 저장처럼 알림을 담고 앱 전체를 다시 돌린다 — 카드는 프래그먼트라
    카드만 돌면 다른 저장 칸(Capa 요약 등)이 앞 회차에 그린 알림이 이 알림과 두 줄로 남았다(2026-11-01 리뷰,
    `tests/test_home_key_process_fragment.py`). 느린 둘째 누름은 그 칸의 표지 글이 그 이름의 저장 성공 글일 때만으로 가른다 — 같은
    칸의 「기본으로」·「삭제」 알림 뒤의 누름은 「바뀐 것이 없습니다」 다.
  - `Past Data 포함` 을 끄면 과거 세 표를 행만 비운 사본(version 0)으로 바꾼다 — 끈 분기를 곳곳에 심지 않는다.
- `src/capa_simulation/components/home_main_cases.py` — 「HOME 설정」 팝업 `비교 · 주요 Case` 탭의 「주요 Case」 상자(2026-10-23
  사용자 요청).
  HOME 슬롯은 셋 고정이고 슬롯 1 은 지금 최신 공식버전이라 상자 첫 줄에 글로만 보인다(공식 지정은 시나리오 관리 — 줄에는 값만,
  그 자리는 줄 풍선 `OFFICIAL_SLOT_HELP`). Case1·
  Case2 마다 「시나리오」·「리비전」 상자를 두고(넓으면 두 칸, 좁으면 위아래) 고르는 것이 곧 저장이다(공용 프로필 `0036`).
  - **공용 프로필이 정본이고 상자는 거울이다.** 비교 시나리오(세션 우선)와 달리 회차마다 프로필 값을 위젯 앞에서 상자에
    적는다 — 남의 지정·이름 바꾸기가 다음 회차에 보이고 브라우저가 옛 글자를 되보내도 지정이 바뀌지 않는다(9장).
  - 시나리오 콜백은 그 시나리오 첫 리비전과 **짝으로** 저장한다(위젯 기본값은 `on_change` 를 부르지 않는다). Case 하나만
    바꾸고 다른 Case 는 같은 쓰기 트랜잭션에서 옮겨 적는다. 같은 짝·라벨 글자는 쓰지 않는다.
  - 두 상자의 콜백은 화면이 그린 짝(`expected_pair`)이 그 Case 의 지금 짝일 때만 쓴다(같은 쓰기 트랜잭션에서 대조 — 다른
    Case · 이름 바꾸기는 막지 않고, 비운 Case 는 `(None, None)` 으로 대조). 어긋나면 쓰지 않고 곁 · 알림창에 알린다. 토큰이
    version 이 아니라 되돌아올 수 있는 값 짝이라 제 저장 판정(`is_own_save`)으로 대조 값을 바꾸지 않는다
    (`tests/test_write_guard_cas.py` `NOT_OWN_SAVE_CONFLICTS`). 잇단 제 고름은 판정 없이도 남는다 — 팝업 본문은 프래그먼트라
    앞 고름의 회차가 끊기지 않는다.
  - **되돌아온 옛 값은 고름이 아니다.** 회차가 상자를 프로필 값으로 옮기면(거절된 고름 되돌림 · 남의 지정을 처음 보임)
    브라우저는 새 값을 받기 전까지 옛 값을 들고 있다가 다음 신호(팝업 닫기 · Esc · 탭)에 실어 보낸다. 콜백 인자는 방금 그린
    새 짝이라 대조를 지나므로, 상자를 옮기는 회차가 그 Case 에 거부 표지를 적고(`_hold_moved_boxes` — `note_profile_conflict`)
    `TRAILING_PRESS_SECONDS` 안의 콜백은 쓰지 않는다. 거절한 콜백이 아니라 상자를 옮기는 회차가 적어야 고름 없는 탭 왕복과
    창보다 긴 회차도 막힌다. 제 고름은 콜백이 리비전 상자 칸을 맞춰 표지에 걸리지 않고, 거절된 값이 되돌아와도 새 알림을
    담지 않는다(`_notify_held`). 표지는 시간 창이라 왕복 지연과 브라우저 지연의 합이 그보다 길면 옛 값이 지날 수 있다(실제
    틈은 재지 않았다).
  - 본문의 쓰기는 둘뿐이다 — 목록에 없는 시나리오를 가리키는 Case 비우기(조건부 UPDATE, 한 번 알림 + 출처 칸에 까닭),
    그 시나리오 것이 아닌 리비전 칸을 첫 리비전으로 메우기(본 version 대조). 둘 다 프로필만 보고 정해져 세션끼리
    뒤집지 않는다.
  - **숨은 탭 회차(팝업의 다른 탭을 보는 회차)는 DB 를 읽지도 쓰지도 않는다**(`owner_tab`) — 마지막으로
    보인 화면 재료(`MAIN_CASE_VIEW_KEY`)로 위젯을 그대로 그린다(탭을 누른 순간 보이는 것이 그 화면). 팝업을 다른
    탭으로 처음 열면 한 번만 읽고 쓰지 않는다. 위 두 쓰기와 그 알림·콜백 실패 알림은 보이는 회차로 미룬다. 팝업이 닫힌
    회차에는 상자를 그리지 않는다.
  - **미지정 칩이 연 Case 칸은 한 번 강조한다**(2026-11-04 사용자 검수 home-u03) — 칩 콜백이 Case 번호를 세션 칸
    (`MAIN_CASE_FOCUS_KEY` — `focus_main_case`)에 적고, 상자가 보이는 첫 회차가 꺼내 그 칸 컨테이너(key `main_case_slot_key`)에
    약 1.4초 한 번 도는 면 · 테두리 빛을 건다(움직임 줄이기면 움직이지 않는 윤곽). 서식은 Case 머리 줄과 한 `st.html` 에
    실어 본문 칸으로 보낸다(`case_head_markup` — 강조 없는 회차에도 같은 자리 하나, 9장 「팝업 본문은 이벤트 칸에 같은
    수만」). 숨은 회차는 꺼내지 않는다(`tests/test_home_main_cases_picker.py`).
  - 비운 Case 는 세션 API 로 `None` 을 적어 브라우저가 자리표시를 띄우므로 `placeholder` 를 비우기 선택지 글자로 준다
    (주지 않으면 영문 「Choose an option」). 그 글자는 같은 이름의 시나리오가 있으면 「지정 안 함 (비움)」 으로
    비켜 선다(`unset_choice_label` — 1.63 은 같은 글자를 첫 선택지로 읽어 그 Case 를 비울 수 없었다).
  - Case1·Case2 가 같은 짝, Case 가 공식버전과 같은 리비전이면 저장하고 상자 아래 값 줄 「**같은 리비전** · Case1 · Case2」
    로 알린다(`main_case_overlap_notes` 는 짝 이름만 — 뜻은 줄 풍선 `MAIN_CASE_OVERLAP_HELP`).
    HOME 에서 슬롯을 올리는 칩은 `home_main_case_chips` 다(같은 `services/main_cases.main_case_slots` 를 쓴다).
- `src/capa_simulation/components/home_main_case_chips.py` — HOME `LOB 표시 조건` 카드 맨 위의 주요 Case 칩 셋(2026-10-23
  사용자 결정 — 시안 C · 동작 (가), 2026-11-02 부터 본문 제목 줄 끝이 아니라 카드 맨 위 — 이름 줄 「주요 Case」 밑에
  카드 폭을 같은 폭으로 나눈 칩 줄, 그 밑 칩 알림 칸 — 늘 서 있는 빈 칸이고 알림은 알림창 · Alarm 으로만 간다, 얇은 선 뒤 토글). 칩 글자는 `공식 vN`·`Case1`·`Case2` 뿐이고 시나리오·리비전은 단추 `help` 풍선이 말한다(사람 글은
  `literal_markdown`). 지금 적용된 시나리오는 머리 띠가 말하므로 칩 옆에 적지 않는다.
  - **누르면 사이드바에서 그 리비전을 불러온 것과 똑같다** — `scenario_status.load_saved_revision` 을 **콜백**에서
    부른다(본문 `st.rerun()` 은 그 회차에 안 그린 위젯 값을 버린다 — 9장). 저장하지 않은 편집·적용 전 편집이 있으면
    곧바로 올리지 않고 사이드바 팝업을 그 짝으로 연다(`open_scenario_dialog_on` — 같은 확인 칸·같은 단추).
  - **콜백은 누르는 순간 슬롯을 다시 푼다** — 콜백 인자는 그린 회차의 값이라, 그사이 다른 세션이 Case 를 다시
    지정하거나 가리키던 시나리오를 보관하면 낡은 칩이 예전 Case·사이드바가 고를 수 없는 보관 시나리오를 올렸다. 칩은
    (슬롯 차례, 그린 짝)만 넘기고 콜백이 그리기와 같은 `_slot_chips_now` 로 지금 짝을 풀어 다르면 아무것도 올리지 않고
    알림창 · Alarm 에만 알린다(`changed_slot_notice` — `popup_only` 경고 `FL-03`, 칩 줄 밑 자리에는 그리지 않는다, 2026-11-04
    설계 규칙 확인 보드 AMB-05 (나)). 주요 Case 나 공식버전을 읽지 못함 · 불러오지 못함도 같다.
  - 칠하기(primary)는 세션 활성 시나리오·**리비전까지** 같은 칩만이고, 저장하지 않은 편집이 있으면 칠하지 않는다(머리
    띠·사이드바 배지처럼 「미저장」이 먼저 — `painting_reference`). 칠한 칩을 편집 없이 다시 누르면 아무것도 하지
    않는다. 칠한 칩 글자색은 `tokens.ACCENT_TEXT` 다(어두운 테마 강조색 위 흰 글자는 1.9:1). 어느 칩도 칠하지 않으면
    이름 줄 「주요 Case」 **오른쪽 끝**에 회색 「슬롯 밖」 한 마디(풍선 없음) — 이름 줄이 늘 서 있어 칩 줄은 움직이지
    않는다(제목 줄 끝에 있던 때의 숨은 자리표시자는 걷었다). 칩 글은 자르지 않는다 — 칩 칸 최소 폭이 글 폭(`max-content`)이고
    줄은 감싸 내린다(`flex-wrap: wrap`). 보통 폭(사이드바 256px 이상)은 한 줄, 끌어 줄인 240px 이하는 셋째 칩이 다음 줄로
    간다(2026-11-02 검토 — `nowrap` 이던 때 200~220px 에서 「공…」 · 「C..」 로 잘렸다).
  - 미지정 Case 는 점선 칩이고 누르면 「HOME 설정」 팝업을 `비교 · 주요 Case` 탭으로 열고 그 Case 칸을 한 번 강조한다
    (`home_settings.open_home_settings` · `home_main_cases.focus_main_case` — 열림 칸·탭 key·강조 칸을 콜백에서 적는다). 설정
    상자 밖에서 설정 팝업을 여는 자리는 이 칩 하나다(사이드바 「LOB 표시 조건」 카드) — `docs/design_rules.md` UI-LAY-01 의
    예외 「미지정 주요 Case 칩」(2026-11-04 반영 검수표 D6 (가) · 데려가기 UI-NAV-01, 그물 `tests/test_settings_button_sites.py`).
    계산이 멈춘 회차에는 팝업을 열 수 없어 그 칩만 잠근다(`stopped_chips`). 가리키던 시나리오를 보관·영구 삭제하면
    저장소가 그 Case 를 비우므로 점선 칩이 된다. 잠금은 목록에서 찾지 못하는 짝(저장소 밖에서 고친 DB 등)과 공식버전
    없음뿐이다(풍선이 까닭).
  - 회차마다 DB 를 보지 않는다 — 공식은 `intro_summary.latest_official_identity`(머리 띠와 같은 세션 값), Case 는 주요
    Case 쓰기 세대를 키로 한 캐시 `persistence/cache.load_main_case_targets` 다. `tests/test_home_main_case_chips.py`,
    실제 `app.py` 배선과 둘째 회차 읽기 0 은 `tests/test_app_navigation.py`.
- `src/capa_simulation/components/settings_box.py` — 화면 설정 팝업을 여는 사이드바 「… 설정」 상자 한 칸(2026-11-03 사용자
  지시 — 설정 단추는 사이드바 상자로, 9장 「사이드바·조건 카드·본문」). 조회 조건 패널 바로 밑 · 조건 카드 위(페이지가 카드보다
  먼저 부른다), 상자 자체가 전폭 단추(key 접두 `sidebar_status.DIALOG_BOX_PREFIX` — 서식 `sidebar_style._dialog_box_style`),
  잠금(`disabled`)·대기(key 끝 `_pending`)를 받는다. 열림 칸·여는 콜백·호스트는 화면 모듈 몫이다 — 지금 HOME `home_settings`
  · 가용설비 현황 `equipment_settings_dialog` 둘. 화면 확인 `settings_boxes`(`scripts/check_deploy_screens.py`)가 두 상자의
  자리 · 팝업 제목 · 안쪽 · Esc 닫힘 · 본문 옛 단추 0 을 본다.
- `src/capa_simulation/components/home_settings.py` — HOME 사이드바 「HOME 설정」 상자와 그 큰 팝업(안쪽 탭은 쓰는 묶음 다섯 —
  2026-11-04 사용자 검수 home-u01, 전에는 `Preference`·`Past Data` 둘; 팝업은 2026-11-02 사용자 요청 — 시안 (가) 조회 조건 패널 바로 밑 · `LOB 표시 조건` 카드 위에 따로 선 상자 — 한 칸은
  사이드바 설정 상자 `settings_box.py`). 가용설비 현황 「가용설비 설정」(`equipment_settings_dialog`)과 같은 꼴이다 — 열림 칸 하나(`home_state.HOME_DIALOG_KEY`, 값 `settings`), 여는 콜백은
  `forget_page_dialogs()` 부터(`open_home_settings` — 지난번 편 Past Data 붙여넣기 칸도 걷는다), 호스트는 본문 끝 이벤트
  칸 한 자리(열렸으면 팝업, 아니면 빈 스타일), 저장 뒤에도 열어 둔다(9장 「팝업과 콜백」 의 둘째 예외). 팝업 본문은
  `app_pages/home.py` 가 넘긴 함수 둘이다(앞 네 탭을 라벨 → 탭으로 받는 Preference 함수 · `Past Data` 탭 본문) — 이 모듈은
  편집기를 들이지 않는다(주요 Case 칩이 여는 콜백을 쓰고 편집기 쪽이 칩을 그리므로 들이면 순환한다). 팝업 머리 안내 글은 두지
  않는다(사용자 「설명 제거」) — 공용 설정 · 닫으면 사라짐은 저장 단추 풍선이 말한다.
  - 읽어 두고 저장하지 않은 Past Data(세션 칸)가 있으면 상자 key 끝 `_pending`(왼쪽 주황 띠)과 팝업 안 `Past Data` 탭 점
    (`tab_marks.mark_pending_tabs` — 매 회차 스타일 한 자리)을 단다. 화면 탭 줄 HOME 점(`page_tabs.page_unsaved_marks`)은
    그대로다. Preference 편집기는 모두 폼이라 서버가 제출 전 편집을 모른다 — 닫으면 사라지고 점·떠나기 확인 대상이 아니다.
  - 계산이 멈춘 회차에는 상자를 잠근 채 같은 자리에 세운다(`stopped=True`). `tests/test_home_page.py`(열기·저장 뒤 열림·
    대기 점)·`tests/test_app_navigation.py`(실제 `app.py` 배선·여는 콜백이 다른 열림 키를 비움).
  - 폼 저장(판정 기준·프리셋·Past Data 등)은 앱 범위 `st.rerun()` 이라 사이드바도 그 회차에 바뀌지만, 고르면 곧 저장되는 두
    선택 상자(비교 시나리오·주요 Case)는 `on_change` 콜백뿐이라 팝업만 다시 돌고 사이드바(GAP 잠김·칩)는 닫는 회차에
    바뀐다 — 고를 때마다 앱 전체를 돌리면 비교 계획까지 새로 읽는데 둘 다 모달 뒤다(2026-11-02 검토, Guide 「HOME 설정 팝업」).
  - 팝업 안 표에는 전체 화면 단추가 없다 — Streamlit 이 `st.dialog` 안 표의 도구 막대에서 숨긴다(전에는 Preference 편집표 넷 —
    판정 기준 월별·선행 B/O·선행 입고·확보율 보정 — 에 있었다). 기능을 팝업으로 옮기며 생긴 손실로 받아들였고 Guide 가 알린다.
- `src/capa_simulation/services/main_cases.py` — 주요 Case 슬롯 셋(공식버전·Case1·Case2)을 (글자, 시나리오 id, 리비전 id,
  상태 `ok`·`unset`(미지정)·`missing`(사라짐))으로 내는 `main_case_slots` 와 겹침 안내 줄. Streamlit·DB·모델을 모르고
  읽기 전용 Protocol 로 필드만 받는다. 리비전은 `scenario_id` 로 그 시나리오 것인지 견준다.
- `src/capa_simulation/components/profile_caption.py` — 공용 프로필 버전 캡션 한 줄을 저장 화면 여덟에 한 규칙으로
  만들고, 제목 · 단추 줄의 값 글 한 칸(`render_row_value` · `render_heading_value`)을 그린다. 모델을 import 하지 않고 읽기 전용 `@property` Protocol 로 세 필드만 요구한다. 출처(`source`)는 사람이 적은
  「변경 메모」일 수 있어 `literal_markdown` 으로 막아 잇는다 — 돌려준 글은 이미 막은 글이다(`ESCAPED_BUILDERS`).
  빈 출처(저장자·메모를 모두 비운 저장 — 가용설비 현황 Preference 등)는 그 자리를 건너뛴다(구분자가 `· ·` 로 겹치지 않게).
  맨 뒤 꼬리는 두지 않는다(Capa 요약의 옛 「공지 중 · 내림」 을 걷었다 — 바로 아래 글 칸과 같은 말, 2026-11-09 사용자 검수 g18).
  `render_profile_heading` 은 제목 옆 공용 버전 줄 한 줄이다(그림 메모 g18 — key 필수, 줄 칸 key `profile_heading_<key>`). 두 글은
  버전 줄 캡션에 실은 `align-items: baseline` 규칙으로 글자 밑줄을 맞추고, 캡션이 HTML 을 받으므로 앱 글의 맨 `<` 는 `&lt;` 로
  바꾸며 이벤트 칸은 쓰지 않는다. `style=` 은 그 구획의 다른 칸에 거는 앱 서식 규칙을 같은 캡션에 싣는다 — 팝업 본문이
  스타일만 든 `st.html`(이벤트 칸)을 쓰지 않고 서식을 걸 길이다(HOME 설정 저장 줄의 표 도구 막대 자리, 9장 「표 도구 막대」).
  쓰는 자리: HOME 설정 상자마다 · 자동 갱신 설정 · 입력 비가동 · 표시순서 · Proc Rename.
- `src/capa_simulation/components/dialog_host.py` — 본문 · 사이드바 단추로 여는 화면 팝업의 키 붙은 호스트 프래그먼트
  (`DialogHost`, 2026-11-08 답 U5 — 여덟 팝업). 열기 · 닫기는 호스트만 돌고, 원본을 바꾸면 `finish`(앱 전체), 판정을 못 넘거나 같은
  칸에 값이 있으면 앱 전체로 물러난다. 이벤트 칸에는 한 자리만 쓴다. `render(dialogs, widget_keys=)` 의 `widget_keys` 는 꼭 줘야
  한다 — 닫기(호스트만 도는 회차)는 팝업 프래그먼트의 위젯을 거두지 않아 호스트가 지운다(key 가 열림 값에 달린 팝업은 함수 꼴).
  쓰는 자리: HOME(설정 · 공정 필터 · 주요공정 히트맵) · 기준 정보 붙여넣기 · 표준 목표 붙여넣기 · Qual 마감 계산기 · 공식 지정 ·
  Space(필요 단축 보기 목표 확보율) · 필요 단축 일정 목표 확보율(Qual 마감 계산기와 한 호스트). 쓰는 법은 모듈 머리 설명과 9장 「팝업과 콜백」.
- `src/capa_simulation/components/process_field.py` — 공용 공정 칸의 화면 조각(값 칸 + 타일 판 팝업 — `process_field_assets`,
  2026-11-08 답 P1 · P2)과 머리 띠 칩 · 화면 탭 표지의 글 · data. 여러 개 따라감은 `render_process_filter(options, screen=, labels=)`
  가 걸 공정을 돌려주고(산출 결과 셋 · 가용설비 Main · Space, 기준 정보는 `column_filter` 의 `shared_screen=`), 하나 고름은
  `render_process_choice(options, screen=, key=)`(공정 Capa 상세 · 제약 시뮬레이션 — 팝업에서 직접 고른 공정만
  `shared_process.pick_single` 로 보낸다, 2026-11-09 보드 C2 (가)). 값 칸 글은 「전체 N공정」 · 하나면 이름 · 둘부터 한 줄
  「Mold 외 2개」(`first_and_rest` — 표시순서상 첫 공정, 풍선 `filter_help` 가 전체 목록 — 2026-11-09 사용자 검수 g03-2, 필요 단축
  일정 카드의 공정 칸 · 머리 띠 칩도 같은 함수)다. 표지는 값 칸 테두리 `ACCENT` 두 겹 · 이름 줄 출처 「X 에서」(실제로 걸렸을
  때만) · 없는 공정은 값 칸 아이콘 `filter_alt_off` 뿐이다 — 이름 줄 주황 배지는 걷었다(보드 P1-6). 본문 위 칩은 없다(보드
  C1 (라)) — 머리 띠 「공정」 칩(`header_chip` → 알림 칸 — 글자는 그 화면 글자라 Space 에서는 원본, 그 밖은 그 화면 표시명(지금 공용
  표시명 프로필 — 그린 화면은 그 선택지로 겹친 표시명을 값 칸처럼 가름, 2차 보드 Q2-18), 2026-11-10 보드 Q-3)과 화면 탭 표지(`tab_mark` → 탭 줄 — 풍선 글자는 그 탭 화면 글자라 Space 탭은 원본, 2차 보드 Q2-17)가 대신하고, 값 칸을 그린 회차에
  표지(`MARKER_ATTRIBUTE` — 스타일만 든 `st.html` 의 JSON, 값 칸과 같은 간격 없는 칸에 그려 사이드바에 틈이 없다)를 남겨 알림
  칸 JS 가 회차 끝에 지금 화면 몫을 바로잡는다. 팝업은 조건 팝업 호스트의 넷째 갈래이고 선택지는 페이지가 값 칸을 그린 회차에
  세션(`CONTEXT_KEY`)에 적고 `page_script_hash` 로 다른 페이지 것을 가린다. 판(Components v2)의 트리거는 `apply` 하나다 — 결과
  dict 메서드 이름(`clear` 등)을 트리거 이름으로 쓰지 않는다. 판 찾기 칸에 글이 있을 때 Esc 는 글만 지운다 — 판 JS 가 창 capture
  단계 처리기 하나(`clearSearchOnEscape`, 창마다 한 번 — R7)로 받아 팝업 · 팝오버(문서 capture 에서 닫는다)에 닿지 않는다(한글 조합
  중의 Esc 는 지우지 않고 팝업 · 팝오버에도 보내지 않는다 — 조합은 입력기 몫). 판을 쓰는
  다른 칸(필요 단축 일정 「공정」)은 `mount_process_board` 의 data 넷으로 바꾼다(그 화면 항목). 공통 진입이 멈춘 회차(산출 결과 · 공정 Capa 상세 · 제약 시뮬레이션 — 산출 결과는 소요대수 · 확보율 탭의 표가 멈춘 회차도)는
  `render_stopped_process_field()` 가 같은 key 의 잠긴 값 칸 「계산 멈춤」 으로 자리를 지킨다(HOME 공정 필터 줄과 같은 꼴 — 검수
  보드 p-stop-row). 불러온 리비전이 없는 빈 상태로 멈췄으면 값 칸은 본문 회색 줄과 같은 글(「공식버전 없음」 등 —
  `page_bootstrap.stopped_field_value`, 2026-11-14 물음 보드 decided 5)이다. 산출 결과는 정상 회차와 같은 높이다. 공정 Capa 상세 · 제약 시뮬레이션도 멈춘 회차에 그 앞 「설비 시나리오」 줄을
  정상 회차처럼 잠그지 않고 세워(`equipment_scenario_status.render_stopped_equipment_scenario_row` — 설비 DB 를 못 읽으면 줄 없음,
  2026-11-10 답 Q2-29 · 2026-11-11 보드 C1) 같은 높이다. 선택지 기록 · 표지는 남기지
  않는다(머리 칩 · 탭 표지의 짐작을 빈 목록으로 덮지 않게).
- `src/capa_simulation/services/advance_load.py` — 선행 B/O 정규화와 월별 변동률(`기존 계획 ÷ 선행 반영 계획`)·역산.
  - 변동률을 확보율에 곱하고 Wafer 는 나눠 Capa·B/N 순위가 그대로다. 선행을 넣은 달 가운데 선행 반영 계획이 0 이하인
    달만 미적용으로 알린다.
- `src/capa_simulation/services/advance_shipment.py` — 선행 입고 실적 정규화·편집 병합과 LOB 칸 글자
  (`advance_shipment_notes`). 계산에 들지 않는 표시값이다.
- `src/capa_simulation/services/monthly_amount.py` — 월별 억Gb 한 칸 공용 프로필(선행 B/O·선행 입고 실적)의 정규화·보인
  달만 갈아 끼우는 병합·`{YYYYMM: 값}` 사전·바꾼 것 없는 저장 견주기(`same_monthly_amounts` — 0·빈칸은 넣지 않은 달, 차례와
  끝자리를 접는다, 9장 「바꾼 것 없는 저장」). 두 편집기가 같은 입력을 같게 저장하도록 규칙을 한 곳에 둔다.
- `src/capa_simulation/services/execution_capacity.py` — 확보율 보정(`execution`)의 정규화와 적용
  (`기준 확보율 + 증감/100` — 증감은 확보율에 그대로 더하는 %, 화면 「확보율 보정 +5.0%」).
  - 조정이 없어도 세 컬럼(`기준 확보율`·`확보율 증감`·`실행 비고`)을 늘 만든다. 음수는 0 에서 자르고
    (`clamped_execution_adjustments`) 짝 없는 행은 알리기만 한다(`unmatched_execution_adjustments`).
- `src/capa_simulation/services/top5_band.py` — B/N Top 5 막대의 값 대역(기본 50%~200%) 검증과 자르기. 대역은 확보율과
  떼어 공용 프로필에 둔다(달마다 같은 눈금).
- `src/capa_simulation/services/voc_board.py` — VOC 글·답글의 분류(`VOC_CATEGORIES`, 넷 고정)와 입력 검증.
  계산·시나리오에 매이지 않고, 인증이 없어 작성자는 직접 적는 이름이다.
- `src/capa_simulation/services/wd_window.py` — 공정별 Cut-off 로 한 달이 잡는 W/D 구간
  `(전월 말일 − cutoff, 당월 말일 − cutoff]` 를 만든다.
  - 반열린 구간·소수 Cut-off 내림·달력일 분모다 — 열두 구간이 한 해를 빈틈·겹침 없이 덮는 것이 유일한 안전장치다
    (`RUN_DAY` 를 쓰면 설비 DB 가 시뮬레이션 DB 를 읽는다).
- `src/capa_simulation/services/process_cutoff.py` — 공정별 Cut-off 입력 표의 계약·검증과 조회 사전(`cutoff_lookup`).
  없는 공정과 0 은 다르다 — 0 은 달력 월 그대로, 없으면 산출에서 빠지므로 화면이 `missing_cutoff_processes` 로 드러낸다.
  화면 글은 계산(`wd_window`)이 쓰는 내림 일수로 적고, 적은 값(`cutoff_setting`)에 소수가 있으면 내림을 함께 적는다
  (`cutoff_days_words` — 「35일(35.8일 내림)」, Static 대비 일정 머리·제약 시뮬레이션 조건 줄·공정 Capa 상세 머리). 「가용설비
  설정」 팝업만 적은 값 그대로다(2026-10-26 E2E — 같은 공정이 화면마다 35일·35.8일로 갈렸다).
- `src/capa_simulation/services/qual_deadline.py` — Qual 마감 계산기(2026-10-22, 10-07 계산기 한 장을 옮김)의 계산과
  화면 글자(복사 글 함수는 걷었다 — 내려받기는 결과 표 도구 막대, 작은 결정 d12). Cut-off·연도·직전 달 가용대수·월별 목표·신규 호기로 호기마다 Qual 완료 마감을 낸다. 어느 DB 도 열지 않는다.
  - 구간은 `wd_window` 그대로, 몫은 완료 다음 날부터다. 모자람 ≥ 1 이면 마감 = 구간 앞 경계(몫 1), < 1 이면 모자란 날 수만큼
    구간 끝에서 당긴 날(몫 = 일수 / 길이). 적은 차례로 꺼내고 남는 호기는 다음 달로, 목표를 비운 달은 판정하지 않는다.
  - 숫자 글자는 JavaScript `toFixed`·`Math.round` 와 같게 만든다(`to_fixed`·`js_round` — 0.125 → 「0.13」). 붙여넣기 칸은
    원본 `bulk-apply` 그대로다 — 공백뿐인 줄은 건너뛰고 앞 12줄, 첫 칸은 목표, 둘째 칸부터는 띄어쓰기로 이은 호기(`js_trim`).
    `tests/test_qual_deadline.py` 가 원본 스크립트를 node 로 돌린 값과 칸 글자까지 맞댄다(시험은 node 없이 돈다). 알림 글자만
    하나 다르다 — 열두 줄을 넘으면 원본은 말없이 앞 12줄만 넣었는데 넣지 않은 줄 수를 덧붙인다(`PastedMonths.dropped_lines`).
- `src/capa_simulation/services/shortening_filter_profile.py` — 필요 단축 일정 공용 조회 조건(설비 DB `0019`) 모델
  `ShorteningFilterProfile` 과 정규화·심기·`merge_filter_processes` 규칙. Streamlit·DB 를 모르고 값은 원본 공정명이다.
  `effective_filter_months`·`filter_month_window` 는 필요 단축 일정 시작·끝 월 칸의 심기를 **읽기만** 해 같은 달을 낸다(Space
  필요 단축 보기 — 세션 값은 인자로 받는다).
- `src/capa_simulation/services/manual_downtime.py` — 입력 비가동대수(설비 DB `0032`, 2026-10-27 결정) 모델 `ManualDowntime`
  (0 아닌 칸만의 (공정, 생산월, 환산 대수) 튜플 — 캐시에 실린다)·저장 이력 `ManualDowntimeSave` 와 규칙. 저장 입구
  `prepare_manual_downtime`(빈칸 = 0, 0 이상 소수, 상한 9999, `YYYYMM`), 보이는 범위만 갈아 쓰기 `merge_visible_cells`, 계산 키
  `manual_downtime_key`(계산할 달로 좁힌 칸 자체), 가용 빼기 `apply_manual_downtime`(그 달 가용에서 0 에서 멈춤 — `clamp_manual_units`
  를 공정 Capa 상세 ③ 비가동대수(전월 대비 표)도 쓴다)과 출처 띠 글(`manual_effect_band`), 대수 글 `manual_units_text`·뺀 몫 글
  `manual_removed_text`(공정 Capa 상세 두 곳이 같은 글을 쓴다 — 6장 「입력 비가동대수」). Streamlit·DB 를 모른다.
- `src/capa_simulation/services/floor_state.py` — Space 동·층 사용 상태(설비 DB `0029`, 2026-10-24 결정 S1~S6) 모델
  `FloorStates`(비활성 층만의 (동, 층, 사유) 행 — 사유는 직접 적은 글이고 옛 코드 `UNUSED` 사용 안 함·`NOT_LINE` 생산라인
  아님도 그대로 둔다, 2026-10-26 결정)와 규칙. 저장 입구 `prepare_floor_states`(30개 층, 빈 값 = 사용, 사유는
  `floor_reason_code` — 짝 없는 서로게이트·앞뒤 공백 뗌, 옛 코드의 글·코드 글자는 그 코드 — 를 거쳐 `floor_reason_refusal`
  이 20자·제어 문자(Cc·Cf·Zl·Zp·Cs)를 거절, 거절 글에 사람 글을 싣지 않는다)만 엄격하고 읽기는 관용이다(`stored_reason` —
  손으로 넣은 빈 사유 행은 저장 입구의 「비우고 끄면 사용 안 함」 과 같이 `UNUSED` 로 읽는다, 2026-10-27 표적 E2E — 빈 글이면
  편집 초안이 그 층을 사용으로 떨어뜨렸다 · `inactive_label` —
  옛 코드는 그 글, 적은 글은 길이를 보지 않고 그대로, 빈 글은 「비활성」, 제어 문자는 빈칸. 편집표 칸만은
  `reason_cell_text` — 저장할 글 그대로). 사유 글을 고치거나 막지 않는다 — 마크다운 자리는 그리는 쪽이
  `literal_markdown`(저장 미리보기 경고는 `inactive_floor_warnings(escape=)`). 동 머리(`building_state` — 옛 코드만 값,
  `with_building`), 끄기 확인 대상(`newly_inactive` — 사유만 바꾼 층은 아님)과 층별 설비
  대수(`floor_unit_counts` — 도면 이탈 제외·레이아웃 Y/N 모두·설비키), 층 고르기 거르기(`selectable_floor_keys` — 연 층은
  남김, 설비 마스터 탭 칸 단위 `master_location_options` — 표에 있는 값은 남김, 짝 단위 `floors_by_building` — 표 `층` 칸
  정의의 `optionsBy` 로 실려 `grid.js` `choiceOptions` 가 그 줄의 동으로 좁힌다), 저장 미리보기 경고
  `inactive_floor_warnings`(막지 않음). Streamlit·DB 를 모른다. **설비 마스터 저장 검사(C1~C5·1F~6F)는 그대로다**(S5).
- `src/capa_simulation/services/shortening_baseline.py` — 필요 단축 일정 기준선(설비 DB `0021`) 모델과 규칙. 기준선은
  저장한 그때 계획을 얼린 고칠 수 없는 기록이다(`freeze_plan` → `ShorteningBaselineDraft`, `normalize_baseline_name`·
  `baseline_label`·`normalize_baseline_units`). 같은 이름 거절은 `BaselineNameTakenError`(`ValueError` — 이름을 `name` 으로도
  실어 화면이 글자 그대로 막아 다시 짓는다, 9장 「막는 길은 셋」).
  - `baseline_label` 은 「기준 · 저장일 · 이름」 꼴이다(기준은 `schedule_basis` — 기준 칸 없는 옛 기준선은 설비 마스터). `진척 비교` 선택 상자와 `RS-06` 전문(`_COMPARE_NAMES_KEY`)이 이 한 곳을 같이 쓴다. 기준 · 저장일이 앞이라 칸보다 긴 라벨은 이름 끝이 말줄임표 없이 잘리고 기준 · 저장일은 남는다 — 꼴을 줄이지 않는다.
  - 설비 쪽 출처(`ShorteningEquipmentBasis` — 공통 rN · 설비 시나리오 이름 · 일정 rN · 공식 vN, 설비 `0027` 의 가리키는 칸
    넷)도 기준선에 싣는다. 기준선은 세션이 **공식 발행 쌍**일 때만 저장한다(E5 — 거부 까닭은 「가정 설비 시나리오」 와
    「발행하지 않은 리비전」 둘, `equipment_scenario_status.baseline_equipment_refusal`).
- `src/capa_simulation/services/shortening_progress.py` — 기준선과 지금 계획의 같은 목표 호기 표를 짝지어 시점·단축일수
  변동과 상태를 낸다(`compare_progress`·`summarize_progress`·`progress_export_frame`).
  - 짝짓기는 공정 안에서만 — 당긴 호기는 설비명끼리, 「추가N」은 차례끼리다. 지금 범위에 없는 기준선 공정은
    `지금 범위 밖`(해소 아님), 오늘보다 앞선 과거 필요 시점은 `필요 시점 지남` 으로 양쪽 증감에서 뺀다.
  - **기준 바뀜**(2026-11-20 결과 보드 여쭘-4 a — 규칙집 6-38): 두 시점 모두 있는 당긴 호기 가운데 한 시점만 Static 기준의 남는
    호기(확보 시점 · 단축일수 빈칸 — 현재 일정 없음)인 것은 진척이 아니라 범위 바뀜이라 `기준 바뀜` 으로 따로 세고 증감 · 양쪽
    합계 · 개선/악화 대수에서 뺀다(`ProgressSummary.rebased` · `rebased_current_days`). 차례는 범위 밖 → 필요 시점 지남 → 기준
    바뀜이다(필요 시점이 지난 호기는 날짜를 받았어도 지남). 두 시점 모두 남는 호기면 양쪽 0일 `변동 없음`, 한쪽에만 있으면 `신규
    필요` · `해소` 그대로, 추가N 은 차례끼리라 섞이지 않는다. 판정은 행의 꼴로만 한다 — 설비 마스터 기준에는 남는 호기가 없고
    화면은 늘 기준선과 같은 기준의 계획과 견준다. 공정 진척 보드의 기준선 대비(`shortening_watch.progress_trend`)도 같은 셈이고,
    「해소」 는 기준선에 단축일수 · 추가N 이 있었고 지금 계획에 그 공정의 호기가 하나도 없을 때만이다 — 기준 바뀜 · 남는 호기(변동
    없음 · 신규 필요) · 필요 시점 지남 호기가 지금 계획에 남은 공정은 일수가 0 이어도 「해소」 가 아니다.
- `src/capa_simulation/services/shortening_progress_log.py` — 필요 단축 일정 「누적 진척」(설비 DB `0036`)의 모델과 값 규칙.
  기록 한 줄 = ISO 주차(`ProgressWeek` — 해 · 주를 함께, 글은 앱 주차 도우미 `iso_week_calendar.weeknum_label` 의 `YY-W##`, 해 넘김
  차례가 (해, 주)로 맞음) 하나의 단축 필요일수(사람이 적은 0 이상 정수 — 화면 계산과 잇지 않는다), 최종 목표는 일수 · 주차 하나
  (`ProgressGoal`). 머리 한 줄 요약(`summarize_log`)은 **기록 기준**이다 — 지금 일수 = 마지막 기록, 지난 기록 대비 = 그 앞 기록과의
  차(기록이 하나면 없음 — 0 이 아니다), 남은 일수 = 마지막 기록 − 목표, 목표 주차 지남. `screen_shortening_days` 는 「이번 주 값
  넣기」 가 채우는 지금 화면 합계(고른 목표의 계획에서 범위 공정의 당긴 호기 단축일수 합)이고, 기준선의 현재 일정 기준이 전환과
  같으면 진척 비교 요약의 지금 합계 + 필요 시점 지남 몫 + 기준 바뀜 몫과 같다(그런 기준선이면 어느 것과 견주든 — 시험이 맞댄다).
  기준이 다른 기준선이면 진척 비교는 그 기준의 계획(`_Plan.plan_for`)과 견주고 화면 합계는 전환 쪽 계획이라 맞지 않는다.
  Streamlit · DB 를 모른다.
- `src/capa_simulation/services/shortening_progress_reasons.py` — 누적 진척 「주차별」 오르내림 까닭(2026-11-20 · 21 보드 답
  — 꼴 중간-1 「점 곁 곧은 꼬리표」, 재료 「자동 + 사람이 고침」 의 1단계 자동 — 규칙집 6-43). 넣기 스냅숏 모델(`ProgressSnapshotDraft` ·
  `ProgressSnapshot` — 범위 공정의 당긴 호기 · 추가N 행 `SNAPSHOT_UNIT_COLUMNS`, 범위 공정 · Cut-off · 현재 일정 기준 · 목표 확보율 ·
  그날 오늘 · 조회 달 · 출처 · 구성 글 `snapshot_digest`)과 `snapshot_draft`(계획 호기 표에서 범위 행만 새 표로 — 합은
  `screen_shortening_days` 와 같다). `explain_week_changes` 는 기록마다 바로 앞 기록 주와만 짝짓고(건너뛴 주는 한 구간) 두 주 모두
  그 기록과 같은 쓰기의 스냅숏이 있을 때만 `WeekChange` 를 낸다 — 항목은 저장하지 않고 그릴 때 센다. 짝짓기는 진척 비교의
  `compare_progress` 그대로이고 꼬리표는 열하나다 — Qual 당김 · Qual 밀림 · 필요 늦춰짐 · 필요 당겨짐(호기마다 확보 몫 · 필요 몫 가운데
  |몫| 이 큰 쪽, 양은 단축일수 차이 — 함께 움직인 순 0 은 버림) · 신규 필요 · 해소(공정마다 묶음) · 범위 바뀜 · 기준 바뀜(현재 일정
  기준 · 목표 확보율이 다르면 호기별로 가르지 않는 한 항목이 첫 자리, 남는 호기 ↔ 날짜 호기도 이 이름) · 기한 지남 · 손 고침((이 주
  기록 − 스냅숏 합) − (앞 기록 − 스냅숏 합)) · 그 밖(풍선의 꼬리 묶음). 항목 합 = 지난 기록 대비가 정수로 맞아야 `balanced` 이고
  그때만 글을 싣는다. 그림 꼬리표 항목(`drawn`)은 그 주 변동과 같은 쪽 · 둘째는 변동의 1/4 이상 · 둘까지이고, 한 공정에 해소 ·
  신규 필요가 함께면(`rename_suspects`) 그 둘은 그림에 올리지 않는다. 추가N 대수와 입력 바뀜(조회 달 — `scope_difference`, 두
  범위에 함께 있는 공정의 Cut-off — `WeekChange.cutoffs`, 시나리오 · 설비 일정 · 공통 대장 리비전 — 시나리오 리비전 id 를 모르면
  `reference_version`)은 합 밖 덧말이다(가름은 바꾸지 않는다 — 진척 비교 「조회 달 다름」 과 같은 결). Streamlit · DB 를 모른다.
- `src/capa_simulation/services/shortening_watch.py` — 필요 단축 일정의 공정 진척 보드(`process_board`)·카드 차례
  (`board_order`)·기한 임박(`imminent_units`)·이행 지연(`delayed_units`)과 설비키마다 Qual 실적·상태·담당자
  (`unit_qual_status` — 캐시 래퍼 `get_unit_qual_status`). Streamlit·DB 를 모르고 쓰지 않는다. 카드 상세 링크 숫자는
  `detail_numbers` 가 두 표를 한 번씩 묶어 공정 전부를 낸다(`first_shortage_month` · `process_counts` 를 공정마다 부른 값과 같다).
  - 이행 지연 = 기준선 목표 Qual(과거 필요 시점) < 오늘인데 마스터 Qual실적이 비었거나 Qual상태가 「완료」 아닌 당긴 호기
    (모듈 하나라도 미완료면 미완료, 마스터에 없으면 지연). 가상 호기는 보지 않는다.
- `src/capa_simulation/services/monthly_equipment_availability.py` — 호기 생애주기 구간을 W/D 구간에 일수로 안분해
  월별·공정별·분류별 기여 대수를 만든다. 어느 DB 도 열지 않는다.
  - 상태는 바뀐 다음 날부터 기여하고 정지·반출/이설로 가용을 잃는 날만 당일부터 빠진다. 가용 소계는 `기존보유`·`가용`
    둘뿐이고(분류는 `집계분류`), `span_date_range` 는 첫 구간의 앞 경계부터 준다.
  - 대수 표와 호기 목록(`build_monthly_equipment_contributions`)은 같은 기여 줄(`_raw_rows`)에서 나온다.
- `src/capa_simulation/services/securement_cross_check.py` — 같은 소요대수에 Static(`RQ_EQP_AVBL`)과 설비 일정 기준
  가용대수를 각각 나눠 확보율 두 벌을 낸다(화면은 `cross_check_from_monthly` — 설비 일정 쪽 분자에서 입력 비가동
  `manual_downtime=` 를 더 뺀다, 6장 「입력 비가동대수」).
  - `calculate_securement_rate` 를 고치지 않고 가용대수 프레임만 바꿔 두 번 부른다. 설비 일정 쪽에 공정 자체가 없을 때만
    Static 으로 채워 `fallback_processes` 로 알린다. HOME·B/N 은 여전히 Static 을 본다.
  - 맞댈 달은 설비 일정이 덮는 달 ∩ 소요대수의 조회기간(`period=` — 화면 캐시 `get_securement_cross_check` 는 시나리오 키의
    시작 · 끝 달)이다. Static 은 모든 달이 있어 좁히지 않으면 사이드바 조회기간 밖 달이 소요대수 0 · 확보율 None 행으로 실려
    「맞대어 본 달」 에 세어졌다. 두 기간이 겹치지 않으면 행이 없다. 캐시 없는 길(`securement_cross_check_result` — 패널이
    키 없이 불릴 때)도 `period` 가 **필수 인자**이고 패널은 키의 기간 또는 `required_period` 를 넘긴다 — 패널 `months`(설비
    조회일)는 사이드바 조회기간과 다를 수 있어 대신 쓰지 않는다.
- `src/capa_simulation/services/required_shortening.py` — 일정 기준 가용이 소요대수 × 목표 확보율에 모자란 공정·월마다
  신규 호기 Qual 을 며칠 당길지, 당길 호기가 없으면 가상 호기 「추가N」의 Qual 기한을 낸다. 어느 DB 도 열지 않는다.
  - 가용은 Static 대비 일정과 같은 길(`build_monthly_equipment_availability`), 소요는 `calculate_securement_rate` 다.
    같은 이름 공정만 맞대고 나머지는 목록(`required_only`·`missing_cutoff` 등)으로 돌려준다.
  - 그 가용에서 **입력 비가동**(`manual_downtime=` — 키의 칸)을 맞댄 공정만 더 뺀다(`apply_manual_downtime`, 6장 「입력
    비가동대수」). 건 칸·뺀 몫·넘침은 `ShorteningPlan.manual_downtime` 이고 `process_months` 의 `가용대수` 는 뺀 값이다. 칸이 없으면 전과
    같은 계산이다.
  - 늘어나는 몫은 엔진을 다시 돌리지 않고 기여일로 센다. 후보를 바닥 `max(구간 앞, 오늘)` 뒤에서 모자란 만큼만 당기고,
    한 달 상한을 넘은 가상 호기는 모두 걷는다(남기면 뒤 달 부족을 가린다).
    후보는 바닥보다 Qual 이 늦은 신규 호기 가운데 Qual 이 가장 이른 것, 같으면 호기 번호(이름 끝 숫자, 그다음 이름)가 작은 것부터 고르고, 반입일정은 하한으로 보지 않는다. 후보가 바닥나면 환산비 1 의 가상 호기 「추가N」 을 더하되, 오늘이 든 달은 한 대가 남은 날만큼만 덮고 한 달 상한은 50대(`_MAX_VIRTUAL_UNITS_PER_MONTH`)다.
  - 목표는 스칼라 또는 `MonthlyTarget` 이고 한 길로 계산한다(`tests/test_required_shortening_monthly_target.py`). 화면이 직접 넣은
    다섯 밖 목표는 모든 달이 같은 `MonthlyTarget` 으로 목표 하나 칸(`get_required_shortening_for_target` — 공정 Capa 상세 · 제약
    시뮬레이션과 같은 8칸)에서 계산해 다섯 값 계획에 스칼라로 더한다(`plan_with_level` — `tests/test_target_level_entry.py`). 기준선 ·
    「목표 전체」 CSV 는 다섯 그대로다(`shortening_baseline.baseline_units_frame`).
  - **현재 일정 기준**(`basis=` — 6장 「필요 단축 — 현재 일정 기준」): 기본 `설비 마스터` 는 지금까지의 계산 그대로(공정 Capa
    상세 · 제약 시뮬레이션은 이것만 부른다). `Static` 이면 `static_schedule=`(역산)이 있어야 하고 후보의 현재 Qual 과 단축 전
    가용을 역산값으로 바꾼 뒤 같은 단축 계산을 돈다(`_static_inputs`) — 남는 호기는 현재 일정 없이(`OPEN_QUAL`) 추가N 보다 먼저,
    Static 행이 없는 공정은 `static_missing`. 내보내기 맨 앞 칸은 「현재 일정 기준」(`BASIS_COLUMN`)이다.
- `src/capa_simulation/services/static_qual_schedule.py` — 필요 단축 일정 「현재 일정」 의 Static 역산(2026-11-20 보드 답
  Static-0 · Q01 ~ Q15). 역산할 호기(`reverse_targets` — 신규 · 보관 N · 정지/반출 없음 · HBM/EDP · Qual상태 완료도 Qual실적도
  아님, 일정 미정 포함, Qual 순 → 번호, 미정은 반입 순)와 비가동 없이 센 고정 대수(`fixed_counts` — 같은 엔진)로 Qual 마감
  계산기와 같은 규칙의 마감을 낸다(`reverse_static_schedule` — 환산비 1 이면 `compute_qual_deadlines` 와 같은 마감 · 몫,
  `tests/test_static_qual_schedule.py` 가 맞댄다). 지난 마감은 오늘로(그 달 모자람은 미루기 전 몫으로 줄임), 호기 부족 ·
  남는 호기 · Static 행이 있는 공정을 함께 낸다. 어느 DB 도 열지 않는다. `qual_deadline.py` 는 손대지 않는다.
- `src/capa_simulation/services/upeh_assumption.py` — UPEH 가정(`UpehAssumption`·캐시 키 토큰 `UpehToken`)과 소요대수 ÷f
  사후 배수(`scale_required_equipment`·`scale_securement_rate` — 같은 확보율 함수로 다시 낸다), 닫힌 식 역산 둘
  (구간 안 단축 0·확보 기준 미달 0, 80~150 밖은 갈래), 효과 한 줄(`effect_text` — 정수가 그대로면 「덜 당김」)을 낸다.
  「이 값으로」 단추는 역산이 80 ~ 150 안(`INVERSE_OK`)이고 지금 값과 다를 때만 서고, 적는 값은 그 범위로 깎는다(`clamp_percent`). 80 으로도 충족이면 「80% 로도 충족」, 150 을 넘어야 하면 「150% 로도 못 채움(필요 n%)」, 가용 0 인 달이 있으면 「UPEH 로는 못 채움(가용 0 인 달)」 이고 이 갈래에는 단추가 없다. 신규(추가N) 0 역산은 비선형이라 하지 않는다.
  - 선형 전제는 `tests/test_upeh_assumption.py` 가 `RQ_UPEH` 를 고쳐 다시 계산한 결과와 맞대어 지킨다.
- `src/capa_simulation/services/process_equipment_timeline.py` — 공정 Capa 상세의 설비 일정(참고)을 생산월 좌표로
  정리하는 순수 함수(`build_process_equipment_timeline`·`unit_events`·`dynamic_readiness`). DB·오늘을 보지 않는다.
  - 비가동 손실은 반사실(비가동을 비운 구간과의 차이)이라 경계 규칙이 엔진 그대로다. 시험 불변식:
    `기존보유 + 호기 가용 − 입력 비가동 반영 = 필요 단축 일정 계획의 가용대수`.
  - 그 공정의 입력 비가동(`manual_downtime=` — (달, 대수))은 전월 대비 표(`bridge`)에만 든다 — 뺀 몫(`입력 비가동 반영`, 계획과
    같은 `clamp_manual_units`)과 그 증감(`입력 비가동 증감`)이 `비가동` 에 더해져 `전월대비 = 신규 + 비가동 + 반출이설` 이 선다.
  - 공정 Capa 상세 「③ 비가동」 비가동대수(2026-11-12 사용자 답 q5 (가))의 재료는 `downtime_impact(bridge,
    process_months)`(`IMPACT_COLUMNS`)다 — 손실 = `호기 비가동
    손실`(bridge 의 그 달 반사실 − 실제 합) + `입력 비가동 반영`(0 에서 멈춘 뒤 실제로 뺀 몫 — 넣은 대수가 아니다) = 비가동이
    하나도 없을 때의 가용 − 지금 가용(가용·소요는 계획의 단축 전 값 — `확보율` 이 계획 `확보율` 과 같은 길, 소요 0 이면 NaN —
    화면에서 쓰지 않게 된 「확보율 영향(%)」 · 「비가동 없는 확보율」 칸은 걷었다, 2026-11-12 남은 물음 보드 ⑥-1 (가)). 시험 불변식: 비가동 없는 가용 = 비가동 표·입력 없이 만든 설비 일정의 `가용대수`
    (`tests/test_downtime_impact.py`). 새 캐시·새 키가 없다(설비 일정·계획 캐시가 이미 든 값이다).
  - 「② 일정 가용」 총보유대수(q3 (가))는 `owned_unit_counts`(`ProcessEquipmentTimeline.owned_units`) — **달력 월**(Cut-off
    없이)로 반입한 달부터 세고 반출/이설일정이 든 달부터 뺀다(정지만 한 호기는 남김), 기존보유 표 + 기존설비 Y · 보관 Y 호기는
    반입일정과 상관없이 처음부터(가용 엔진의 보유 판정 `기존설비 | 보관 | 반입일정 ≤ 그날` 과 같은 판단 — 2026-11-12 남은 물음
    보드 ③-1 (가), 반입 앞 달에 총보유 < 가용이 서지 않게), 사용기준 HBM·EDP 만, 모듈은 환산비. 전월 대비 풍선(k-c3)은 `unit_month_changes(unit_months, months)` —
    설비키마다 비가동을 비운 가용의 전월 대비 몫(합 = 비가동 빼기 전 호기 가용의 전월 대비).
  - `new_unit_availability(timeline, since=, excluded=)` 는 제약 시뮬레이션 「신규 설비는 개조 없이」 의 재료다 — `new_units`
    가운데 첫 모듈 기여 시작 ≥ 기준일인 호기마다 기여 시작(Qual 다음 날 — 묶음은 **첫 모듈**, 2026-11-01 사용자 결정이라 ③ 의 가장
    늦은 모듈 날보다 이를 수 있다)·환산 대수·가장 이른 정지·반출/이설일과, 묶음이면 모듈마다의 기여 시작 · 환산비(`ModuleStart`
    — 축 안에 기여가 있는 모듈)를 낸다(`NewUnitStart`). 축 앞에 나가 축 안 기여가 없는 첫 모듈은 모듈 몫에 들지 않으므로 기여
    시작이 남은 모듈의 첫 날보다 이를 수 있다 — 계산 검증(`_validate_modules`)은 늦은 것만 막는다. 환산 대수는 묶음이 센 모듈(이름은 `모듈별 Qual` 에서)의 환산비 합이고,
    환산비는 `unit_months` 의 비가동 없음 기여에서 되짚는다(환산대수 × 구간일수 ÷ 기여일수 — 운영 비가동은 들어온 날·환산비를
    바꾸지 않는다). 축 안에 기여가 없는 호기는 `units` 에만 남는다. `excluded` 는 보유로 고른 설비키(빼고 낸다 — 두 번 세지
    않게). 어느 증가에 붙일지는 계산 서비스가 정한다. 새 계산·새 캐시가 없다.
  - `held_unit_choices(equipment, process=, cutoff_days=, months=)` 는 제약 시뮬레이션 보유 「호기 고르기」 선택지다(2026-11-01
    결정 B3, `HeldUnitChoice`) — 그 공정의 보관 N · 사용기준 HBM·EDP 이고 기존설비 Y 또는 Qual 있음인 행을 설비키로 묶어, 모듈
    마다 기여 시작(Y 는 처음부터, N 은 Qual 다음 날 — ③ 과 같은 규칙)·마스터 환산비, 묶음의 가장 이른 정지·반출/이설일을 낸다.
    날짜는 축으로 다듬는다 — 축 첫 W/D 날 이전 기여 시작은 None, 축 끝 W/D 날 뒤 반출은 None, 축 뒤에 들어오는 모듈과 축 첫
    W/D 날 전에 나간 호기는 뺀다. 구간·월별 기여를 만들지 않아 가볍다(캐시 `simulation_cache.get_process_held_units`).
- `src/capa_simulation/services/availability_gap.py` — Static 과 설비 일정 기준 분류 행을 한 표로 맞대는 순수 함수(행
  머리는 상수로 읽는다). 두 DB 공정명을 맞추는 장치가 없어 한쪽에만 있는 공정을 `dynamic_only`·`static_only` 로 낸다.
- `src/capa_simulation/services/availability_sheet.py` — `분류별 내역` 9행 비교 시트(`static:`·`sched:`·`gap:` ×
  `owned|lent|available`)와 호기 분해(`build_availability_sheet` → `sheet_view`·`unit_availability_breakdown`).
  - 설비 일정 기준은 반사실이다(보유 = 기존보유 + 비가동만 비운 구간의 가용, 대여 = 가용 − 보유). 「—」 칸은 까닭
    (`REASON_*`)을 갖고 값은 반올림하지 않는다.
  - 입력 비가동(`manual_downtime=` — 키의 칸)은 가용에서 더 빼고(그 (달, 공정) 가용에서 멈춤) 보유는 그대로라 대여에 든다.
    넣은 값·뺀 몫은 `입력 비가동`·`입력 비가동 반영` 칸, 근거 카드 줄은 `manual_downtime_lines`(공정마다 한 줄 — 호기 줄과
    더하면 칸)다. 호기 필터 시트는 주지 않는다(호기 단위).
- `src/capa_simulation/services/key_process.py` — HOME 주요공정 히트맵의 공정 상한(`KEY_PROCESS_LIMIT`)·프리셋 규칙
  (`normalize_key_process_presets`·`resolve_preset_name`). 고른 차례가 곧 행 순서다(빈 목록 = 고르지 않음). 이름 하나에
  걸린 거부(같은 이름·공정 없는 프리셋)는 `PresetNameError`(`template`·`name`)라 화면이 막은 이름으로 다시 짓는다 — 물결표만
  막는 오류 글 길로는 이름의 `*k*` 가 기울임이 됐다(2026-10-26 E2E). 사이드바 칸·팝업 라디오(`format_func=literal_markdown`)·
  미리보기 캡션도 이름·표시명을 `literal_markdown` 으로 싣는다.
- `src/capa_simulation/components/revision_label.py` — 리비전을 가리키는 글자 「r{번호} · {리비전명}」 한 곳(시나리오 관리
  공식 지정 팝업·알림·사이드바 팝업·HOME 비교 리비전·파생 원본·월 머지 표). 리비전명은 고칠 수 있어 이 글자를 선택지로
  쓰는 상자는 매 회차 고른 id 를 되쓴다(9장). 마크다운 자리에는 부르는 쪽이 `literal_markdown` 으로 감싼다.
- `src/capa_simulation/components/flash.py` — 동작 결과 알림의 담기·꺼내 보내기 한 길. `queue_flash(key, 글, *, kind,
  icon, alert, popup_only, tables, goto)`(kind 는 success·info·warning·error, `goto=(이름, 주소[, 탭])` 는 사건 알림의 「그 화면으로」
  를 다른 화면 · 탭으로 보낸다, `target=` 은 그 화면 · 탭에 닿았을 때만 서버에 보낼 대상 `alerts.GotoTarget` — `goto` 없이는 거절 — 소요대수에 들지 않은 수요 경고는 `REQUIRED_TAB_GOTO`(시나리오
  관리 › Capa 시나리오 › 목록 관리 › 점검 — 탭 길은 알림 칸이 이름으로 차례로 누르고, 그 리비전은 `required_check_target(시나리오, 리비전)` 을 줄이 들고 가 알림 칸이 탭 길을 마지막 칸 앞까지 연 뒤 보내고 `scenario_list_state.queue_check_target`
  이 적어 같은 회차의 「점검」 칸이 한 번 고른다, 2026-11-11 검토 보드 F4 (나) — 작은 결정 a4 의 산출 결과 › 소요대수를 바꿈 · 다음 배포 물음 보드 F4 뒤 (a)), 아이콘 · 코드 없는 성공은 글만 담는다, `alert` 는 등록부의 사건
  코드 — 없으면 종류별 `alerts.FLASH_CODES` 의 `FL-01`~`04`, `tables` 는 그 Alarm 줄의 표 — 커서 None 인 칸은 뺀다)로 세션에 담고, 다음 실행에서 `render_flash(*keys)` 가 알림이 있든
  없든 `st.container()` 한 칸을 세워 담긴 알림을 차례대로 **사건 알림 표지**(`alerts.emit` — 이벤트 칸 한 자리)로 보내고
  그 칸을 돌려준다. 성공 · 안내는 오른쪽 아래 알림창으로만 내고 버튼 곁 칸에는 그리지 않으며, 경고 · 오류(거부 · 실패)만
  그 칸에도 그린다(2026-11-03 결정 보드 D3 (가) — `BESIDE_KINDS`). 동작은 끝났고 그 자리에 고칠 입력이 없는 경고는
  `popup_only=True` 로 알림창 · Alarm 에만 낸다(사이드바 리비전 저장 · 시나리오 관리 복제 · 공식 지정 뒤 소요대수에 들지 않은
  수요 — 2026-11-04 검수 의견 home-18). 뒤 형제 자리가 알림 유무로 밀리지 않고 같은 동작의
  실패 문구도 그 칸에 쓴다(`st.success` 바로 뒤 `st.rerun()` 이면 문구가 그려지지 않는다). 표지 글은 평문(`alerts.plain_text`
  — 마크다운 꾸밈을 걷는다)이고 칸 key(`origin`) · 화면을 단다. 이 모듈 밖에서 알림 칸을 꺼내는 꼴은 `tests/test_flash_messages.py` 의
  AST 그물 둘이 막는다 — 이름에 FLASH·NOTICE 가 든 칸을 비우는(`pop`·`del`) 자리와, 이름과 상관없이 꺼낸 칸(`pop`,
  같은 블록의 `get`·`[]` 뒤 `del`, 바깥에서 읽어 두고 한 갈래 안에서 비우며 그 갈래에서 그리는 꼴)의 값이 알림
  요소(`success`·`info`·`warning`·`error`·`toast`)에 드는 자리. 수명이 다른 칸만 (파일, 함수, 칸) 으로 까닭과
  함께 허용 목록에 둔다(9장 「조건부 알림」).
  담아 둔 알림이 없는 칸은 쓰기 직후 적어 둔 알림(`write_guard.note_notice`)이 `TRAILING_PRESS_SECONDS` 안이면
  `write_guard.held_flash` 로 그 글을 적어 둔 아이콘·종류(`note_notice(…, icon=, kind=)` — 종류는 보통 성공)로 다시 낸다 — 표지는
  첫 알림과 같은 id 라 알림창이 두 번 뜨지 않는다. 아주 빠른 둘째 누름의 회차가 앞 회차의 알림을 지우지 않게 모든 칸이 이
  길을 받는다(적지 않은 칸은 그대로 한 번만 그린다, 9장). 그 밖의 칸도 보낸 표지를 `alerts.RESEND_SECONDS`(3초) 안에 그 칸을
  다시 그리는 회차가 같은 id 로 한 번 더 보낸다(`again` — 표지를 브라우저가 훑기 전에 회차가 끊겨도 알림창이 뜬다).
- `src/capa_simulation/alerts.py` — 알림 등록부와 표지 API(2026-11-03 결정 보드 D1 ~ D6, 9장 「알림 칸」). 등록부
  `SPECS`(→ `REGISTRY`)는 `AlertSpec(코드, 단계, 갈래, 이름, 짧은 글, 전문)` 줄이고 코드는 `AB-01` 꼴 고정 id(한 번 쓴 번호는
  다시 쓰지 않는다, 겹치거나 꼴이 어긋나면 읽는 순간 멈춘다). 단계 넷(`LEVELS` — info 알림 · check 확인 필요 · action 조치
  필요 · error 오류, `LEVEL_LABELS`·`POPUP_SECONDS`), 쌓기 · 반복 창 · 보관 · 시선 끌기 상수(`POPUP_LIMIT` 3 — 넘치면 단계가
  가장 낮은 칸부터, 같은 단계면 먼저 선 칸부터 걷는다(알림 칸 JS `overflowVictim` — 2026-11-10 보드 Q-1). 방금 누른 동작의
  결과 칸(`flash` 를 실은 사건)은 그 넘침에서 걷지 않고 제 시간 동안 이 위 한 칸으로 선다(`showPopup` 의 `C.resultKey` —
  2026-11-24 사용자 「권장대로」) · `REPEAT_WINDOW_SECONDS` 60 · `HISTORY_ROWS` 200 · `HISTORY_HOURS` 12 · `ATTENTION_MS` 450 ·
  `ATTENTION_EASING` · `ATTENTION_HIT_MS` 900 · `ATTENTION_FADE_MS` 160 · `ATTENTION_STILL_MS` 1600)가 여기 한 곳이다. 시선 끌기 값은
  `attention_payload()` 한 사전으로 알림 칸 data `limits` 와 Space 층 보기 · 편집 data `attention` 이 함께 받는다(두 JS 에 수를 두지 않는다). API: 사건 `event(code, text=, full=, level=, cause=, detail=)` — 담기만 한다(`OUTBOX_KEY`), 상태
  `state(code, scope=, content=, active=, text=, full=, scope_label=, tab=, tables=)` — 이벤트 칸 한 자리, 지문(`fingerprint` =
  코드 + 범위 + 내용)이 바뀔 때만 알림창 · 자리에는 그리지 않음(D2 (나)). `tab` 은 그 화면 안 탭 이름(「그 화면으로」 가 그
  탭까지 연다), `tables` 는 Alarm 줄에서 펼쳐 볼 딸린 표들(`AlertTable` — 칸 · 행(JSON 값) · 원래 행 수 · CSV 파일 이름 · 화면에만
  입힐 표시명 · 칸 머리 풍선, 조건이 있을 때만 · 커서 None 인 칸은 뺀다 · 행 끝 `TABLE_ROW_LIMIT` 2,000 — `alert_table(clip=True)` 는 앞부분만 싣는다), `flush()` — 담아 둔 사건을 지금 보냄. 표지는
  `<style data-capa-alerts="JSON">`(`MARKER_ATTRIBUTE`, 스타일만 든 `st.html` — 이벤트 칸)이고 `note_page` 가 적은 이번
  화면을 단다. 화면을 그리지 못한 오류의 알림은 `page_error_note`(같은 글이면 같은 id · `keep` — Alarm 줄을 지키라는 표지, 알림 칸 JS 의
  `keptRowMissing`)이고 자리 마크와 한 칸에 싣는 표지가 `hidden_marker` 다(`components/data_error_mark.py` — 아래). 분석 기록(L2)은 자리만 있다
  (`record_server_event` · `ALERT_LOG_SWITCH` — usage-log 1단계와 함께, D6).
  보관(`HISTORY_ROWS` · `HISTORY_HOURS`)에서 걷힌 열린 상태 줄은 같은 지문이 다시 오면 알림창 없이 다시 선다(알림 칸 JS `handleState` — 9장 「알림 칸」).
- `src/capa_simulation/components/alert_center.py` (+ `alert_center_assets/` CSS · JS) — 알림 칸 Components v2. **`app.py`
  에서만 불러온다**(탭 줄과 같은 까닭). 화면 탭 줄 바로 뒤 · 페이지 앞에서 고정 key(`ALERT_CENTER_KEY`)로 매 앱 전체 회차
  그린다. JS 가 `document.body` 에 제 호스트(`#capa-alert-host`, 그림자 DOM — 알림창 · Alarm 패널 · 변경 판 · 시선 끌기
  테두리 · 공정 판)와 머리 툴바 슬롯에 여섯 호스트(공정 칩 · 합성 샘플 표지 · 「정본 아님」 표지 · 변경 칩 · 공지 칩 · Alarm 단추)를 세우고 칸 자체는
  접는다(`_HIDE_STYLE`). 공정 칩은 공용 공정 값(`process_field.header_chip`)이 있을 때만, 합성 샘플 표지는 지금 화면이 원천 미연결
  화면(`PageSpec.pending_source`)이고 「샘플 데이터」 가 켜졌을 때만, 「정본 아님」 표지는 정본이 아닌 데이터로 뜬 서버(`SY-05` · `SY-01` —
  `app.py` 가 `object_sync_status.not_canonical_code()` 를 `canon=` 으로 넘긴다)에서만 선다(2026-11-09 보드 C1 (라) · T8, 2026-11-14 「앱 대신
  뜨는 화면」 보드 d13 (가) — 9장 「알림 칸」). data 는 세션만 읽는다
  (콜백이 담은 사건 `alerts.drain_outbox` · 변경 목록 `change_summary.session_changes` · 등록부 · 이 회차 테마 팔레트
  `palette()` · 글 `TEXT` · 프로세스마다 한 번 정하는 부트 표지 `BOOT_MARK` 와 재시작 알림 — 9장 「서버 재시작 알림」, 이 세션이
  공식버전을 확인했으면(`official_known` — `app.py` 가 `intro_summary.latest_official_revision()` 으로 넘긴다) 공식버전 없음
  `SC-01` 의 해소 표지 — 2026-11-14 물음 보드 decided 5. 그 data 가 선 동안 화면 표지의 같은 칸 「있음」 은 앞 회차가 남긴 표지라
  보지 않는다 — JS `settledStateKeys` · `markerNotes`, `tests/test_alert_center_assets.py`). 한 번 훑은 표지(문서 차례)에서 같은
  상태 칸(코드 + 범위)은 마지막 것만 다룬다(`latestStateNotes` — 회차 끝 토큰 알림 다시 내기 `container_start_check.render_token_alert_late` 가
  같은 회차 앞 표지를 고쳐 쓴다, 앞 것까지 다루면 같은 문서를 다시 훑을 때마다 줄이 닫혔다 열린다). 패널은
  브라우저 안에서만 열고 닫아 파이썬 회차가 돌지 않는다. 기록 · 상태 지문 표 · 본 사건 id · 앞 부트 표지는
  이 브라우저 탭 `sessionStorage`(`STORAGE`)다(D1 (가)). 툴바 실제 폭을 재어 `--capa-toolbar-width` · `data-capa-toolbar` 를
  문서 뿌리에 단다(`app_header` 의 실측 규칙이 읽는다). 줄의 딸린 표(`tables`)는 표마다 「… 보기」 가 펼치고 「CSV 내려받기」 가 브라우저
  안에서 파일을 만든다(원본 값 · BOM — 서버를 부르지 않는다, 표는 코드마다 가장 새 줄에만 남기고 탭 저장소가 넘치면 저장본에서 오래된
  줄의 표부터 뺀다 — 그 화면이 다시 보내면 다시 붙는다). 칸 머리 풍선(`help`)은 `title` · 점선 밑줄이다. 줄의 「그 화면으로」 는
  지금 화면을 가리키고 `tab` 이 없는 줄에는 세우지 않는다(`showsGo` — 눌러도 아무 일이 없어서다, 2026-11-07 g1-06). 표지의
  `tab`(그 화면 안 탭 — 탭 안 탭은 `바깥 › 안`, `TAB_PATH`)이 있으면 그 화면에 닿은 회차가 끝난 뒤 이름이 맞는 탭 단추 · 전환 단추를
  바깥 칸부터 한 칸씩 누르고(`tabStep` · `settleTab` — `stateful_tabs` 탭과 `st.segmented_control` 전환 단추, 고른 상태는
  `aria-checked` 로 본다, 누른 뒤에는 그 누름의 회차 표지가 움직이기 전에 다음 칸을 보지 않는다 — `moves`), 줄 · 로그의 화면 칸은 「화면 › 탭」 이다.
  표지에 대상(`target` — `alerts.GotoTarget`, 지금은 소요대수에 들지 않은 수요 경고의 리비전)이 실리면 줄이 그것을 들고 다니고(이 탭
  저장소에도 — 새로고침 뒤에도 같다), 「그 화면으로」 가 탭 길을 마지막 칸 앞까지 열고 그 회차가 끝났을 때 마지막 칸 단추가 선 것만 보고 누르는 대신 트리거 `goto` 로 한 번 보낸다(`goTarget` ·
  `goStep` · `sendTarget` — 그리기 함수 밖 타이머). 콜백 `alert_center._on_goto` 는 꼴(`alerts.goto_target`)과 아는 종류만 받아
  세션에 적고 마지막 칸(「점검」 — `SIDE_NEXT_KEY`)을 함께 열어 같은 회차의 화면이 쓴다 — 마지막 칸을 따로 누르면 그 회차가 앞 고름을 한 번
  더 그리고 센다(합성 사본 0.6초, 샘플 관측). 쓰지 않고 남은 것은 다음 앱 전체 회차 앞에서 버린다(`scenario_list_state.expire_check_target`).
  탭 길 · 대상은 화면 탭 줄이 그 누름의 이동을 보냈다고 알린(사건 `capa-open-page` 의 `opened` — 떠나기 확인 · 상한을 지남, 이미 그 탭이거나 그 탭으로
  가는 중) 뒤에 닿은 화면에서만 잇는다(`goStep` 의 'drop') — 길이 막히면(떠나기 확인 취소 · 탭 상한 · 붙든 누름이 버려짐 · 기다리던 누름이 덮임)
  알리지 않아, 그 뒤 20초(`PENDING_TAB_MS`) 안에 손으로 그 화면에 가도 탭을 누르지 · 대상을 보내지 않는다(시간 넘김 · 단추 없음도 보내지 않는다).
  탭 줄이 보낸 이동을 서버가 받지 않은 드문 경우(epoch 어긋남 · 되돌림)는 남는다. 대상은 받는 쪽이 아는 종류(`alert_center.GOTO_RECEIVERS` —
  data `goto_kinds`, `knownTarget`)만 들고 가고, 모르는 종류는 대상 없는 줄처럼 마지막 칸을 누른다. 글이 같은 두 경고가 「×2」 한 줄로 합쳐지면 그
  줄의 대상은 대상을 든 마지막 경고의 것이다(`freshenEventRow` — 리비전을 모르는 이어받은 회차의 같은 경고는 앞 대상을 지우지 않는다, 2026-11-11 다음 배포 물음 보드 F4 뒤 (a)). 「로그」
  펼침의 「복사」 는 그 줄의 로그 전문(코드 · 단계 · 날짜까지 붙은 처음 · 마지막 · 화면 · 계기 · 범위 · 해소(내용 바뀜 · 범위 바뀜) · 원본 오류 · 전문 —
  `logPairs` · 순수 `copyText`)을 `navigator.clipboard` 로 넣고, 막히면(보안 연결이 아님 · DRM) 고른 글을 든 읽기 전용 칸을
  세워 Ctrl+C 를 청한다(`execCommand` 는 막힌 클립보드에서도 참을 돌려 쓰지 않는다 · 딸린 표는 이름 · 행 수만 — 2026-11-04 검수
  의견 alarm-05). Alarm 패널 · 변경 판에는 바닥 설명을 두지 않는다(alarm-02 · alarm-11 — 설명은 HOME Guide). Alarm 단추는
  Guide · Print · 테마 단추와 같이 툴바 글꼴을 물려받는다(`:host(.capa-alert-alarm)` 의 `font-family: inherit` — alarm-01, 변경
  칩은 한글 글이라 앱 글꼴). 초점 껍데기(`installFocusShell`)는 앱 전체 꼴이라 이 칸이 문서에 처리기를 둔다 — 꺼진 단추를 감싼 풍선 칸이 탭 자리를
  맡고(Tab 누른 순간 맞춤) 열린 팝오버 단추의 Tab 을 본문으로 들여보내며, 마우스로 누른 단추 · 대화상자를 닫은 뒤의 풍선을 닫고, 회차 중 빠진 초점을 열린
  대화상자 안으로 되돌린다(Streamlit 1.63 DOM 에 기댄다). 시험:
  `tests/test_alert_center.py`(data · 자리 · 변경 목록 · 공정 칩 · 합성 샘플 표지 · 해제 트리거) · `tests/test_alert_center_assets.py`(층 · 누름 · 저장 · 색 계약과 node
  순수 구획 `<alerts-rows>` · `<alerts-focus>` · `<alerts-storage>` — 공정 칩 판정 `processChipOf` · `processLiveOf` 포함) · 파일 전체 문법은 `tests/test_component_js_syntax.py`.
- `src/capa_simulation/components/state_alerts.py` — 화면이 상태 알림 · 화면 오류 알림을 낼 때 쓰는 공용 조각(알림 체계 2단계).
  `simulation_scope(active, period | dates=)`(활성 리비전 `content_token` + 조회기간 · 조회일 — 지문 재료, 로그의 범위 줄
  「시나리오 · rN · 26.01–26.12」, 미저장 편집이면 그 말을 붙인다 — 세션만 읽는다) · `equipment_scope`(세션의 (공통 대장, 일정)
  리비전 쌍 + 「설비 「이름」 rN」) · `alert_table`(알림에 딸린 표 — 내보내기 프레임을 JSON 값으로, 공정 칸 표시명은 화면에만, `column_help` 는 칸 머리 풍선.
  Alarm 줄에서 펼침 · CSV, 행이 `alerts.TABLE_ROW_LIMIT` 를 넘으면 None 이라 화면이 본문 목록을 남긴다. `clip=True` 면 앞부분만 싣고 `total` 은 원래 행 수 —
  `table_clipped` · `clipped_label`, 표 머리는 「앞 n건 · 전체 m건」 이고 표 안 CSV 는 없으며 전체는 그 화면 맨 아래 CSV 단추 하나, 알림 글이 그 자리를 부른다) · `ALARM_ROW_PLACE` ·
  `alarm_table_place`(알림 글이 그 표 자리를 부르는 말) ·
  `alert_page_error(message, code=, tab=, text=)`(화면을 그리지 못한 오류의 알림만 이벤트 칸으로 — 마크가 세 탭에 서는 산출 결과 한 곳이
  쓰고, 나머지는 `data_error_mark.render_data_error`) ·
  `tab_name` / `open_tab_name`(표지의 `tab` — 아이콘 없는 탭 이름, 닫힌 탭이면 None 이라 그 회차에는 그 탭의 상태 알림을 내지
  않는다). 시험: `tests/test_state_alerts.py` · `tests/test_area_b_alerts.py`.
- `src/capa_simulation/components/diagnostic_copy.py` — Admin 진단 펼침(서버 시작 점검 · 통합인증 점검 · DB 동기화)과 모듈 상태 팝오버의 글 전체를 한 번에 복사하는 단추와 그 글을
  짓는 도우미다(UI-NTF-10). 브라우저 안에서 끝나 회차가 돌지 않고, 막히면 고른 글을 읽기 전용 칸으로 편다(`execCommand` 는 쓰지 않는다). 복사 글은 밖으로 나가는 글이라
  부르는 쪽이 리뷰에 옮기지 말아야 할 값을 싣지 않는다(`sso_status.status_text`, `container_start_check.report_text`). 접속 명단은 loginid 가 사람이라 복사 단추를 두지 않는다.
  접힌 진단 펼침의 이름 「개발자용 진단」 도 여기 한 곳이다(`ADMIN_DIAGNOSTIC_LABEL` — 앱 안의 코어 화면 오류 카드 · 앱 시작 실패 판 · 문지기 없이 뜬 앱 판이 함께 쓰고 셋 다 개발자 몫(`admin_view.developer_notes_visible`)에만 세워 서버 경로 · 원문 · 실행 명령을 싣는다. 로그인 전 시작 임시 화면은 누구나 펼치되 이름 · 수만 싣고(보드 d9 (가)) Streamlit 을 부르지 않아 그 `DIAGNOSTICS_SUMMARY` 는 로그인 화면 틀의 낱말(`auth/page_frame.DIAGNOSTIC_LABEL`)을 불러 쓰고 시험이 맞댄다. 통합인증 앱 밖 공통 틀(`auth/page_frame.DIAGNOSTIC_LABEL` — 설정 막힘 · 로그인 실패)도 누구나 펼치되 값 · 비밀값은 싣지 않는다 — 같은 이름을 시험이 맞댄다).
- `src/capa_simulation/components/data_error_mark.py` — 데이터 때문에 화면 · 탭 · 구획을 그리지 못한 자리의 공통 「데이터 Error」 마크(2026-11-05
  사용자 지시). `render_data_error(message, code=, tab=, text=, goto=)` 는 마크(칠한 칸 「데이터 Error」 + 「Alarm 확인 필요」 — 토큰 색 · 두 테마 ·
  좁으면 줄 바꿈)와 오류 단계 사건 알림 표지를 `st.html` 한 칸에 그린다 — 이벤트 칸을 쓰지 않아 프래그먼트 · 팝업 본문 어디서나 부른다.
  글(까닭 · 예시 행 · 고칠 곳)은 자리에 없고 알림창(같은 글이면 이 탭에 한 번) · `Alarm` 줄(전문 · 로그 · 복사)에만 있다. `goto` 는 채울 입력이 다른 화면에 있을 때
  그 화면의 (이름, 주소) 또는 (이름, 주소, 표 · 탭)이다 — `data_error_note` 가 셋째 칸을 `tab` 으로 풀어 줄의 화면 칸이 「화면 › 표」
  이고 「그 화면으로」 가 그 표까지 연다(`calculation_stop_notice` 는 고칠 칸이 든 표 이름을 싣는다 — 모듈수는 화면 없음). 줄의 화면 칸과 「그 화면으로」 가 그 화면이다(`alerts.state` 의 `goto` 와 같다, 표 없이 알림만 내는 산출 결과의 `state_alerts.alert_page_error` 도 받는다). `render_data_error_mark()`
  는 마크만(알림을 탭 밖에서 따로 보내는 산출 결과 — 글을 넘기면 빈 상태를 가른다). **빈 상태** — 받은 글에 불러온 리비전 없음의 글 넷 가운데
  하나가 들었으면(화면이 머리를 붙였어도 — `page_bootstrap.empty_state`) 마크 대신 회색 한 줄(`EMPTY_CLASS` — 「공식버전 없음」 · 「불러올
  시나리오 없음 · 보관본만」 · 「불러온 시나리오 없음」)이다. 공식버전이 없는 세 갈래(없음 · 시나리오 없음 · 보관본만)의 알림은 화면마다 따로 내지 않고 상태 알림
  `SC-01` 하나다(`page_bootstrap.missing_official_note` — 시나리오 관리 「Capa 시나리오」 탭과 같은 표지라 범위 · 지문이 같아 어느 화면을 돌아도
  Alarm 줄 하나 · 알림창 한 번, `goto` 시나리오 관리 › Capa 시나리오 — 시나리오가 하나도 없으면 고를 목록이 없어 › DB 등록, 본문 회색 줄은
  그대로 「공식버전 없음」, 2026-11-14 물음 보드 seed (nopub)). 마크 칸의 숨은 표지에 실어 이벤트 칸 자리 수는 그대로다. 해소는 공식버전이
  있다고 확인한 회차의 알림 칸 data 가 낸다(`alert_center` 의 `official_known` — 계산 화면은 정상 회차에 해소를 낼 자리가 없다, 2026-11-14 물음 보드
  decided 5). 공식은 있는데 이 세션이 안 불러온 갈래만 그 화면 코드의 **확인 단계** 사건 알림(「불러온 시나리오 없음 — 새로고침하면 공식버전을
  엶」, 계기 `EMPTY_CAUSE`)이다. **짧은 글 꼴** — 사람이 고칠 수 없는 DB 실패(다른 프로그램의 잠금 · 쓰기 실패 ·
  열기 실패 · 그 밖의 DB 실패 — `bootstrap_error_message` 의 첫 문단 상수 `HELD_LEAD` 등)는 짧은 글 끝이 「— 개발자에게 알려 주세요」(부르는 쪽이
  준 짧은 글에도 붙는다 — `screen_error_short`), 이 앱 자신의 잠금(새로고침으로 풀림)은 아니다. 그 DB 실패의 전문(파일 경로 · 파일을 연 프로세스
  번호 · 원문 줄)은 개발자 몫(`admin_view.developer_notes_visible`)에만 싣고 그 밖에는 화면 머리 · 첫 문단 · 「개발자에게 알려 주세요.」 만이다
  (`screen_error_public`). 고칠 곳을 주지 않은 경로 · 계획 표 빈 리비전은
  「그 화면으로」 가 시나리오 관리 「DB 등록」 이다(`screen_error_goto`). 시험: `tests/test_data_error_mark.py`(꼴 · 자리 그물) ·
  `tests/test_no_revision_pages.py`(공식버전 없는 저장소로 모든 화면 — 마크 없음 · 확인 알림) · `alert_marks.place_errors`(오류 없이 그렸다).
- `src/capa_simulation/components/change_summary.py` — 머리 변경 칩(D5 (가))의 「이 세션의 변경」 목록. 탭 줄 주황 점과 같은
  세션 판정(`pending_edit_pages` · 설비 편집본 · FAB 배치 대기 · Space 층 사용 초안(「저장 안 함」 묶음 — 떠나도 남는다, 2026-11-19) · 작은 편집표 · Past Data · 시나리오 관리 표
  초안)에 시나리오 미저장(`has_unsaved_scenario_changes`) · 설비 가정(`remembered_equipment_label` 의 공식 시나리오 아님) · UPEH
  가정(100% 아님)을 더해 묶음 셋(떠나면 사라짐 · 저장 안 함 · 가정 사용 중) 차례로 낸다. DB · 캐시를 읽지 않는다. 폼 안 ·
  브라우저 안 초안과 저장 개념이 없는 조건은 들지 않는다(다음 판 후보 — `docs/TODO.md`).
  입력 비가동 · 층 사용 편집의 머리 칩 · 화면 탭 점 풍선이 싣지 않는 칸 수 · 층 수는 그 편집기 안에 남는다 — 입력 비가동은 저장 줄 「되돌리기」 풍선 · 버린 칸 알림, 층 사용은 저장 줄 「바뀐 층 n개」 · 버린 층 알림이다(설계 규칙 UI-NTF-09 — 버리기 전에 알아야 할 수는 그 자리에).
- `src/capa_simulation/components/saved_note.py` — 이름 줄 없는 메모 · 저장자 칸의 안내 글 꼴 「<칸 이름> · 예: <예>」 하나
  (`field_placeholder` — 변경 메모는 `note_placeholder` 「변경 메모 · 예: …」, 저장자는 `equipment_save_fields.SAVED_BY_PLACEHOLDER`
  「저장자 · 예: 홍길동」. 칸은 `label_visibility="collapsed"` 라 이 글이 이름이다 — 2026-11-09 사용자 규칙 「페이지 상단
  최소화」 · 꼴은 상단 띠 재고 권장, 사용자 수락 11-10 Q-12, `tests/test_note_field_placeholders.py` 가 화면 코드의 「변경 메모」 · 「저장자(선택)」 칸을 모두 훑고 안내 글을 글 상수로 손수 짓는
  자리를 막는다)과, 저장한 변경 메모를 칸을 갈지 않고 칸 글이 저장한 그 글일 때만 비운다(9장
  「폼 안 입력을 성공 뒤 비울 때」). 폼 안에서 저장 단추를 먼저 그리고 `ready_note_field(KEY, submitted=, start=)`(본 version —
  대조 저장만) 뒤 `st.text_input("변경 메모", key=KEY)` 를 그린다 — key 는 고정이다. 쓰기가 끝난 갈래는 `mark_note_saved`, 제
  저장으로 판정한 갈래(`is_own_save`)는 `mark_note_saved_again` 이다. 제출 회차는 칸을 비우지 않는다(둘째 누름의 입력이 바뀌면
  `save_once` 지문을 지나 한 번 더 쓴다) — 다음 회차가 칸 앞에서 빈 값을 적는다. 막 비운 칸에서 온 제출은
  `TRAILING_PRESS_SECONDS` 안에서만 칸을 다시 맞춘다(같은 글이면 빈 값, 다른 글이면 그 글). 버전 대조가 없는 선행 B/O ·
  입고는 둘째 누름이 「바뀐 것 없음」 으로 끝나면 메모가 지금 저장본의 출처와 같을 때 그 자리에서 회차를 돌린다. 쓰는 곳은
  HOME 설정 판정 기준 · 선행 B/O · 선행 입고 · 확보율 보정 · Past Data, Admin Proc Rename · 표시순서, 가용설비 입력 비가동이다.
  한계: 빈 값이 브라우저에 닿기 전에 친 글은 누르지 않으면 덮인다. 시험 `tests/test_saved_note.py`.
- `src/capa_simulation/components/widget_generation.py` — 서버 값을 브라우저가 든 위젯에 닿게 하는 **한 길**(9장 「닫힌
  팝업 안」·「쓰기 콜백」). 세대 칸 읽기(`generation` — `write_guard.current_generation` 과 같은 읽기)·세대 key 짓기
  (`widget_key` — 꼴 `__g`·`_g`·`__`·`__p` 와 `bare_zero` 로 옛 key 글자를 바이트까지 지킨다)·세대 올리기(`bump` — 뒷정리 맨
  끝)·닫힌 팝오버 칸 채우기(`seed_field` — 고치지 않은 동안 매 회차 싣고 본 값 `…__seen` 을 `write_guard.remember_seen`·`seen`
  으로 든다)·세대마다 한 번 쓰기
  (`write_once_value` — `write_guard.write_once` 위에 그 세대·입력 지문 쓰기의 결과를 세션 dict 에 들어 겹쳐 온 둘째
  회차가 끊긴 첫 회차의 뒷정리를 그 결과로 잇는다. 뒷정리 뒤 `release()` 로 놓고, 놓지 못한 결과는 그 세대 칸의 다음
  쓰기가 바꿔 든다)·앞 세션의 탭 가르기(`note_session_start` · `session_widget_key` — 9장 「앞 세션의 탭」, 폼 밖 편집표가 쓴다). 세대 칸 읽기·쓰기 거름은 `write_guard` 의 `current_generation`·`write_once` 를 부른다. 꼴 넷의 세대
  꼬리 글자를 이 모듈 밖에서 짓지 않는다(`tests/test_widget_generation.py` — 아직 옮기지 않은 `_{n}` 꼴 다섯 자리는
  그 시험의 남은 목록·`docs/TODO.md` 코드 정리 ①).
- `src/capa_simulation/components/write_guard.py` — 쓰기 콜백의 key 세대 거름(`write_once`·`current_generation`)과 **비교 후
  쓰기의 한 길**. 세대 비교와 쓰기를 **그 세션의 잠금** 안에서 하고(몇 초짜리 쓰기가 다른 세션의 쓰기를 세우지 않는다 — 세션
  사이의 같은 DB 쓰기는 저장소 쓰기 잠금이 줄 세운다) 「이 세대·이 입력은 썼다」 를 세션의 dict 표지(`WRITE_MARKS_KEY` — (세대,
  입력 지문))에 적어, 두 회차에 겹쳐 온 같은 누름(더블클릭)도 한 번만 쓰고 끊긴 쓰기 뒤의 다른 입력은 새로 쓴다(9장,
  `tests/test_write_guard.py`·`tests/test_voc_page.py`). VOC 는 `write_once` 를 바로 부르고, 그 밖의 덧붙이기 쓰기는
  `widget_generation.write_once_value` 로 부른다. 비교 후 쓰기(공용 프로필 version·Cut-off 지문·리비전명·공식 번호·설비 이름·
  설비 리비전 짝)는 셋을 여기서만 한다 — **본 값**(`remember_seen`·`seen`·`forget_seen` — 폼을 제출하지 않은 회차에만 적고
  대체값 없이 돌려준다, 이름에 BASE·SEEN 이 든 세션 칸은 이 모듈만 적는다 — `widget_generation.seed_field` 의 `…__seen` 도),
  **제 저장 판정**(`own_save_marks`·`remember_own_save`·`is_own_save` — (본 값, 저장된 값) 짝이 정확히 같을 때만, 토큰은
  int·str·tuple·dict; 옛 이름 `profile_save_marks`·`is_own_profile_save` 는 별칭), **거부 넘김**(`queue_refusal`·`take_refusal`
  — 충돌 회차는 본 값을 올리지 않고 거부를 다음 회차에 그린다). 화면에서 충돌 예외 10종을 잡는 자리는 모두 제 저장을 판정해
  빠른 두 번 누름의 둘째 거부를 「다른 사용자가 먼저 저장」 으로 알리지 않는다 — 자동 갱신 설정·Cut-off·리비전명·공식 지정·층
  사용·판정 기준·확보율 보정·Proc Rename·표시순서 직접 편집·HOME Capa 요약·Top5 구간·주요공정 프리셋·설비 시나리오
  이름·리비전명·되돌리기·배치 차이 지우기·발행·설비 리비전 저장(`tests/test_write_guard_cas.py` 의 AST 그물). HOME 주요 Case 의 시나리오 대조 충돌은 지금 짝이 고른 짝일 수
  없어(대조 없는 쓰기이고, 같은 짝을 겹쳐 고른 둘째 콜백은 쓰기 전 「지금 짝과 같으면 쓰지 않음」 이 거른다) 판정하지 않는다 —
  그물이 이름으로 빼 둔다(`NOT_OWN_SAVE_CONFLICTS`). 제 저장 짝의 「저장된 값」 은 쓰기 결과(저장소가 돌려준 version·새
  리비전 id)로 적는다 — 쓴 뒤 다시 읽으면 그 사이 남의 저장이 짝에 들어가 남의 저장 뒤 충돌을 제 저장으로 안다. 시나리오 관리
  설비 시나리오 탭의 쓰기 다섯(공식으로 지정·이름 바꾸기·리비전명·배치 차이 지우기·되돌리기)은 쓰기와 짝 적기를 세션의 잠금
  안에서 함께 한다(`save_remembered`) — 겹친 둘째 회차는 그 뒤에야 저장소에 가 짝을 본다. 저장소에 가기 전에 첫 쓰기의 새
  값을 보고 거절하는 발행 확인 글 대조는 그 잠금을 거쳐 판정한다(`is_own_save_settled`). 거꾸로 남의
  저장에 거부된 누름의 둘째 누름은 충돌 표지(`profile_conflict_marks`·`held_profile_conflict`)로 저장하지 않고 그 거부를 다시
  알린다 — 판정 기준·확보율 보정·Proc Rename·표시순서 직접 편집·HOME Capa 요약·Top5 구간·주요공정 프리셋(저장·
  기본으로·삭제)·자동 갱신 설정·Cut-off·Space 층 사용·설비 시나리오 이름·리비전명·공식 발행(충돌 회차가 초안·출발점·입력 칸·확인 글의 본 값을 최신으로 다시 세우는 자리라 표지가 없으면 둘째 누름이 같은
  내용을 다시 쓰며 「저장했습니다」 로 거부를 덮거나, 옛 화면의 값을 최신 위에 얹거나, 바뀐 확인 글을 보지 않은 채 새 번호로
  발행한다 — 설비 시나리오 탭은 `_refused_noted`·`_repeat_held_refusal`, 2026-10-27 E2E). 쓰지 않고 끝나는 아주 빠른
  둘째 누름이 앞 회차의 성공 알림을 지우지 않게 하는 알림 표지(`notice_marks`·`note_notice`·`held_notice`·`held_flash`)는 VOC
  글 삭제·HOME 주요공정 프리셋 「기본으로」·「삭제」·Capa 시나리오 목록 「변경 저장」 이 적고, 설비 리비전 저장의 제 저장이 첫 누름의 알림을 다시 내는 데와 자동 갱신
  설정의 느린 두 번 누름(창 안의 「바뀐 값 없음」 제출이 「바뀐 것이 없습니다」 를 쓰지 않아 다시 그린 방금 성공이 남는다)에도
  쓴다. 알림 칸의 다시 그리기는 `flash.render_flash` 가 모든 칸에 한다(9장). 본문이 받는 컴포넌트 제출(Space 층·FAB 배치
  편집기 「적용」)은 받아들인 입력 지문을 적고(`note_submission`), 브라우저가 새 epoch 를 받기 전에 같은 단추를 한 번 더 눌러
  옛 epoch 로 온 **같은 입력**은 창 안이면 「반영하지 않았습니다」 경고 없이 넘긴다(`just_submitted` — 첫 적용의 성공 알림은
  `note_notice` 로 다시 그린다, 2026-10-27 E2E, `tests/test_space_layout_editor_page.py`·`tests/test_space_fab_edit_page.py`).
  출발점 대조 저장의 `save_once` 는 설비 편집본 저장(`equipment_data_workspace._save_equipment_frames` — 설비 마스터
  「리비전 저장」·Space 「배치 저장」·사이드바 팝업 저장)과 FAB 전체 배치 쓰기(`save_pending_fab_layout`), 시뮬레이션
  시나리오 목록 「변경 저장」(`scenario_management._save_list_edits` — 출발점은 그 이름·순서 편집)이 쓴다(9장,
  `tests/test_equipment_save_double_press.py`·`tests/test_scenario_save_double_press.py`). 설비 편집본 저장은 그 창을 지나 저장소에 거부된 둘째 누름을 위 제 저장 판정으로
  알아본다.
- `src/capa_simulation/components/loading_progress.py` — 오래 걸리는 페이지의 진행 막대(`st.progress`, 자리는 머리 띠).
  단계(`LoadingStage`)를 선언하고 호출부는 `advance()` 만 부르며, 퍼센트는 잰 소요 시간 비율이다.
- `src/capa_simulation/components/equipment_explorer.py` — 가용설비 현황 Main 의 질문·표현·공정·날짜 선택과 결과 하나를
  그린다. 산식을 화면에 복제하지 않는다. altair 는 차트를 짓는 함수 안에서 import 한다 — 맨 위에서 부르면 이 화면을 한 번만
  열어도 프로세스 고정 약 20MiB(altair + jsonschema, 합성 표본 샘플 관측)가 끝까지 붙는다(2026-11-17 메모리 보드 decided 2 —
  `tests/test_equipment_explorer.py::test_importing_the_explorer_leaves_altair_unloaded`). 볼 내용 · 보기 · 표현은 라벨 줄을 걷고(접근성 이름으로 남음 — 2026-11-09 상단 띠
  재고 · 사용자 보드 T6) 세 칸의 뜻은 줄 끝 빈 캡션 풍선 하나(`MAIN_ROW_HELP` — `표현` 이 있는 보기는 프래그먼트가 `표현` 뒤에
  쓴다)다. 가용대수의 마지막 주 대수 요약 · 호기 현황의 센 호기 수는 따로 줄을 세우지 않고 결과 제목 줄 오른쪽 끝 값
  글이다(`profile_caption.render_heading_value` — 밑줄 맞춤은 공용 버전 줄과 같다, 사용자 보드 T2).
  숫자 밑 표지 줄은 두지 않고 상태 알림을 낸다 — 일정 미정 `EQ-20` · 사용기준 밖 `EQ-22`(`report_unit_notices` — Static 대비
  일정도 같은 함수) · 미확인 `EQ-21`(`report_unconfirmed_units` — Main 호기 현황의 상태 분포 · 호기 목록만 — 호기 이름을 보이는
  자리, Summary 첫 진입에 일정 미정 · 사용기준 밖과 함께 떠 알림창을 채우지 않게 — 그 밖의 보기는 같은 자리에서 `alerts.flush()`
  로 한 자리를 채워 이벤트 칸 자리 수가 보기마다 같다). 모두 설비 마스터 전체를 세어 지문이 고르기에 기대지
  않고, 목록은 Alarm 줄 표, 「그 화면으로」 는 설비 마스터 탭이다.
  - 판정·구간은 `simulation_cache` 내용 지문 키 래퍼로 받고 표시명·거르기는 캐시 결과의 복사본 위에서 한다.
  - `표현`(차트·표)과 결과 상자는 「본문 프래그먼트」다(`tests/test_explorer_expression_fragment.py`).
    `render_equipment_period` 는 숨은 `owner_tab` 이면 조회를 건너뛴다.
- `src/capa_simulation/components/equipment_data_workspace.py` — 가용설비 현황 ① 「설비 마스터」 탭의 편집본 경계·작은 편집표
  둘(`render_small_editor`)·저장 이력(`_render_history`)·현재 데이터 내려받기 단추·붙여넣기 미리보기 재료(`build_import_review`·
  `ImportReview`)·저장(세 표 리비전 저장 `save_equipment_buffer`). 옛 폼(입력·직접 편집·저장 이력 — 설비 마스터 편집표·안쪽 탭·
  폼 제출 단추·칸 설정 도움말)은 개편 B1 로 화면에서 빠졌고 개편 D 에서 걷었다 — 파일은 쪼개지 않았다(사양 D16). 탭 본문은
  `equipment_master_tab.py`, 엑셀·CSV 팝업은 `equipment_import_dialog.py`.
  - Space 편집기와 함께 쓰는 편집본 경계다 — 버퍼는 `replace_equipment_buffer` 또는 설비 마스터 표 전용
    `apply_master_grid_result`(같은 세대 규칙 — 내용이 그대로면 세대를 올리지 않는다)로만 갈고 `BUFFER_GENERATION_KEY` 세대를
    올린다(이름 바꿈 `PENDING_RENAMES_KEY`). 「내용이 그대로」 는 `same_frame_content` 로 본다 — 저장본 사본(DuckDB)의 날짜 칸은
    `datetime64[us]`, 엑셀·CSV 넣기의 병합 결과는 `[ns]` 라 `DataFrame.equals` 만으로는 바뀐 것 없는 넣기가 「미저장 변경」 을
    남긴다(낡은 세션의 비가동 붙여넣기 거절 `stale_paste_refusal` 도 같은 견줌). 저장은 `save_equipment_buffer` 한 곳이다.
  - **설비 마스터 지문 메모**(`remembered_digest` — 세션 칸 `SessionSlot` `DIGEST_MEMO_KEY` `equipment_digest_memo_v1`): 같은 표의
    `frame_digest` 를 출처(저장본 쌍 토큰 + 역할)마다 한 번만 낸다. 메모 열쇠는 편집본 출발점(`buffer_base`)과 편집본 세대도 싣는다 —
    편집본 · 저장본이 바뀌는 모든 길이 세대나 출발점을 올리므로 그 뒤 첫 회차가 다시 낸다. 돌려주는 값은 늘 내용 지문이라 캐시 키는
    지문을 넘기지 않는 화면과 같다. 꼴 표지(행 수 · 칸 이름)가 다르면 다시 낸다. 출처는 `calculation_digest`(계산 사본 — 저장본 쌍
    토큰마다) · `snapshot_digest`(불변 스냅샷 표)가 정하고, 가용설비 현황 · Space · `equipment_explorer` · `availability_gap_panel` 이
    `equipment_digest` · `confirmation_digest` · `units_digest` 인자로 캐시 래퍼에 넘긴다. 거른 표 · 그 회차에 고쳐 만든 표에는 쓰지 않는다.
  - **설비 마스터 표의 세션 칸**(개편 B1): 칸 초안 `GRID_OVERLAY_KEY`(못 읽은 글 — 편집본 밖)·되돌리기 `GRID_UNDO_KEY`(기본형 —
    `equipment_grid.undo_to_state`)·결과 알림 칸 `GRID_RESULT_KEY`·오른쪽 칸 자리 거부 칸 `GRID_TOAST_KEY`(번호
    `GRID_TOAST_SEQ_KEY` 는 비우지 않는다)·회차 메모
    `GRID_MEMO_KEY`(새 메모 칸은 창구 `GRID_MEMO` — `SessionSlot`, 저장본 사본 쌍 토큰 읽기는 `DRAFT_REVISION` 창구) 는 편집본을 다시 세움(`ensure_equipment_drafts`)·저장·모두 버리기(`reset_equipment_drafts`) 때 함께 비우고,
    불러온 목록 `GRID_LOADED_KEY`·상세 id `GRID_DETAIL_KEY` 는 남긴다. 남의 저장으로 다시 세울 때 그 저장이 이름을 바꾼 저장본
    호기는 옛·새 저장본의 호기 키로 이어 두 칸의 id 를 `s:새` 로 옮긴다(`equipment_grid.renamed_saved_ids` — 행 id 가 저장본
    설비명이라 옮기지 않으면 살아 있는 호기가 말없이 빠졌다, E2E eq-flows). 자기 저장 뒤는 설비 마스터 탭 저장 길이 `save_id_map`
    으로 옮긴다. 남의 저장으로 다시 세운 알림은 `render_reopen_notices` 한 곳이다(가용설비 현황·Space 현황·필요 단축 일정의
    머리 알림 칸 안) — 버린 편집이 있으면 경고(`DISCARDED_NOTICE_KEY`)를 「알림 닫기」 까지 남기고(한 회차만 서면 늦게 본 사람이
    까닭을 모른다 — `flash` 를 지나지 않는 수명이라 `tests/test_flash_messages.py` 허용 목록에 있다), 없으면 `flash` 안내 한
    번(`REOPENED_NOTICE_KEY` — 그 저장과 이름 바뀐 저장본 호기 수, 알림창 한 꼴이고 `st.toast` 가 아니다). `apply_master_grid_result` 는 **내용이 바뀐 표의 편집표만**
    버리고(오른쪽 칸 출납이 작은 편집표의 적용 전 편집을 지우지 않게) 되돌리기 목록은 결과의 것을 쓴다. 표 밖 길
    (`_remember_edits` — Space 적용·작은 편집표 적용·일괄 삭제 확정·엑셀·CSV 넣기)이 편집본 내용을 바꾸면 표 되돌리기를 비우고(`_forget_grid_undo`)
    알림창으로 알린다
    (역 patch 는 그 위에서 맞지 않는다). `follow_unit_renames` 는 행 조각 단계(와 그 앞 단계)를 버린다(`after_row_steps`).
  - **칸 초안이 남으면 어느 저장 길도 저장하지 않는다**(`save_equipment_buffer` 첫머리 — `unsaved_grid_drafts`, 살아 있는 행의
    초안만 센다). 초안은 편집본 밖이라 사이드바 팝업·Space 「배치 저장」 이 모른 채 저장하면 저장 성공이 초안을 지워 친 글이
    사라진다. FAB 대기분만 쓰는 길(`frames is None`)은 막지 않는다. 낡은 세션의 낡기 전 편집(지운 호기·고친 일정 칸)은 설비
    쪽을 쓰기 전(`_save_equipment_frames` 첫머리, FAB 쓰기 뒤)에 막는다(`stale_save_refusal` — FAB 는 설비 저장의 거부와
    상관없이 쓰는 별도 쓰기다. 이 검사를 FAB 쓰기 앞으로 올리는 것은 사용자 확인 전이다 — docs/TODO.md). 저장소
    `save_equipment` 는 이 함수만 부른다 — 설비 리비전 저장의 제 저장 판정(`EquipmentRevisionConflict` 를 받으면 저장소에서
    바로 읽은 (공통 최신, 시나리오 최신) 짝을 `is_own_save` 로 보고 첫 누름의 뒷정리를 잇는다 — `equipment_write_token`. 성공한
    저장의 짝은 저장 결과의 새 리비전 id 로 적는다 — 쓴 뒤 다시 읽으면 그 사이 남의 저장이 짝에 들어간다)도 여기 한 곳이다.
    쓰기 뒤 · 뒷정리 전에 끊긴 제 저장(fastReruns)은 다음 회차 `ensure_equipment_drafts` 첫머리 `_settle_own_save` 가 잇는다 —
    편집본 출발점이 제 저장 짝의 본 값이고 `held_notice` 창 안일 때 `_after_equipment_save` · 목록 · 상세 id 옮김 · 성공 알림
    (`REOPENED_NOTICE_KEY`)을 낸다. 새 일정 리비전이면 `_REVISION_KEY` 를 남기지 않고 HEAD_STALE 로 한 번 더 돈다(작은 결정 a5).
  - 작은 편집표(`render_small_editor` — 기존 보유대수·비가동 일정, 개편 명세 4-7)는 **폼 밖**이고(명세의 「작은 폼」 에서 바꿈 —
    폼 안 편집은 제출 전까지 서버에 오지 않아 탭 점·떠나기 확인이 볼 수 없었다, 리뷰 rs-b1y) 보기 설정·고르기 칸·일괄 삭제·
    「편집본에 적용」(`_remember_edits`)이고 단추는 보통 단추다(`_selection_buttons`·`_render_bulk_delete_status`). 작업 줄은
    「편집본에 적용」 · 「모두 선택」 · 「선택 ▾」 메뉴(「선택 해제」 · 「선택 행 삭제」 — 2026-11-10 사용자 답 Q-14. 「선택 행
    삭제」 는 세대 `selection_menu_generation_key` 를 올려 메뉴를 닫아 그 아래 「삭제 확정」 줄을 덮지 않고, 「선택 해제」 는 메뉴를
    열어 둔다 — 세대를 올리면 메뉴가 새로 서며 키보드 초점이 문서 몸통으로 떨어진다) · 「표 보기 ▾」 이고 오른쪽 끝은 표 도구 막대
    자리로 비운다(`toolbar_room_css` — 1600 · 1283 창에서 한 줄, 1283 창에서 필터가 걸리면 「표 보기 · 필터」 가 다음 줄). 일괄 삭제
    확인 글(`_deletion_message`)은 기존 보유대수·비가동 일정 둘만이다 — 호기 지우기는 표 출납(`delete`)이다. 칸을 고칠 때마다
    회차가 돌지만 편집표는 「보기
    적용」 으로 확정한 보기를 그려 편집이 남는다. 제출 처리는 돌려준 함수로 화면이 모든 위젯을 그린 뒤 부른다(`st.rerun()` 으로
    끝난다). `small_editor_edits` 가 적용 전 편집을 알린다(탭 ① 점·화면 탭 줄 떠나기 확인). 시험 대역 `BrowserTables(forms=True)`
    는 브라우저처럼 폼 안 편집을 제출 전에 보내지 않는다. 일괄 삭제 확정은 표 위 상자 없이 결과 알림(`GRID_RESULT_KEY`)으로 알리고,
    되살리기는 「저장 전 변경」 의 「한 단계 되돌리기」 가 표 단계를 다 되돌린 뒤 맨 밑 단계로 한다(`restore_bulk_deletion` — 2026-11-07
    답 undo-strip). 그 표에 적용 전 편집이 있으면 콜백은 `RESTORE_REQUEST_KEY` 만 세우고 그 표 편집표 제출이 편집을 먼저 넣고
    되살린다(`_remember_edits` → `_restore_removed`). 그 표를 그리지 않는 회차면 `settle_bulk_restore` 가 곧바로 되살린다. 표 단계 되돌리기가 바꿀 작은 편집표에 적용 전 편집이
    있으면 `defer_grid_undo` 가 `GRID_UNDO_REQUEST_KEY` 만 세우고, 그 표 제출이 `_remember_edits(keep_undo=True)` 로 편집을 넣은 뒤
    `undo`(탭의 `_grid_undo`)로 되돌린다(`_undo_lines_up` — 편집 값이 그대로면 통째 단계여도 되돌리고, 값을 바꾼 편집이 줄을
    지웠거나 통째 단계면 되돌리기를 비우고 편집을 지킴, 답 X1). 그 표를 그리지 않는 회차는 `settle_grid_undo`. 「삭제 확정」 제출 뒤
    `on_deleted`(탭이 `switch_side(SIDE_CHANGES)`)가 「저장 전 변경」 칸을 열고 접힌 칸을 편다(작은 결정 c6). 화면 등급으로 그 표를
    고칠 수 없으면(`read_only` — `table_lock`) 같은 칸 꼴 · 같은 보기의 편집표를 모든 칸 잠금 · 줄 고정 · 고르기 칸 없이
    그린다(`locked_editor` — 따로 key `equipment_small_<slug>_locked_v1` 라 적용 전 편집 판정에 들지 않고, 돌려준 표는 버린다 · 작업 줄 단추와
    예시 행 줄 · 삭제 확인은 서지 않는다 — 2026-11-18 구현 확인 보드 「고칠 것」). 잠긴 칸은 Streamlit 편집표가 열지 않아 거절 알림이 없다.
  - **배치 편집 판정은 세션 메모다**(`buffer_has_layout_edits` — 열쇠 = 편집본 세대·편집본 출발 토큰·저장본 사본 토큰·이름 지도,
    `LAYOUT_EDITS_MEMO_KEY`). 역할이 찍힌 세션은 회차마다 `live_layout_role` 이 부르므로 편집본 전체 `layout_edits`(합성 3천 대에
    0.13~0.17 s)를 회차마다 돌리면 8장 예산을 넘었다. 표 출납이 배치에 닿지 않는 op(칸 고침·값 넣기·붙여넣기·날짜 밀기 — 배치·설비명·
    Main 설비 칸이 아닐 때)만이면 얹기 전 판정을 새 세대로 옮긴다(`layout_memo_mark`·`carry_layout_memo`).
    `buffer_base` 는 편집본 출발점 표지(세션 표지 + 저장본 쌍 토큰 + 씨뿌린 세대 — 표 출납 `base` 와 「리비전 저장」 두 번 누름 잣대). 층 대기분은 캔버스·요소·Main
    설비명 위치(`PENDING_GROUP_LABELS_KEY`) 셋이고 첫 대기분이 본 저장값(`PENDING_BASES_KEY`)을 함께 쓴다.
  - 설비 마스터를 쓰는 모든 저장(설비 마스터 탭 「리비전 저장」 — 표·붙여넣기·CSV·작은 편집표 —, Space 배치 저장, 사이드바
    팝업 저장)은 `_save_equipment_frames` 에서 모듈 묶음 좌표·크기 검사(`saved_master_violations` — 저장본 사본
    `EQUIPMENT_DRAFT_KEY` 와 견준다)를 지나고, 걸리면 `ValueError` 로 거부한다. 배치 편집기가 적용한 묶음의 모양은
    `EDITOR_MODULE_LAYOUTS_KEY`(편집본과 함께 버려짐)에 두어 통과시킨다. 같은 판정을 설비 마스터 탭 「저장 전 변경」 고칠 것 한
    줄(`equipment_master_tab._table_errors`)이 저장 전에 보이고 「리비전 저장」 을 막는다. 표의 모듈 묶음(모듈 둘 이상) 좌표·크기
    칸은 잠기고 그 까닭(`equipment_grid.MODULE_LOCK_REASON`)이 「Space 배치 편집기에서」 를 말한다(사양 D9) — 그런 편집은 붙여넣기
    같은 표 밖 길로만 든다.
  - `ImportReview` 는 「편집본에 넣기」 때 입력·등록할 표·편집본이 달라졌으면 넣지 않고 미리보기를 다시 만든다(마스터 입력
    `read_equipment_update`, `equipment_csv.py`). 일괄 삭제의 `선택` 칸은 편집기 밖으로 나가지 않는다.
  - CSV 업로드 칸은 칸 고유 상한 `CSV_UPLOAD_LIMIT_MB`(50MB — 칸 안내 「50MB per file」, 넘는 파일은 브라우저가
    올리기 전에 막는다)를 쓴다. DB 등록 탭 원천 CSV 칸도 같은 값의 제 상수(`source_csv_registration.SOURCE_CSV_UPLOAD_LIMIT_MB`)다. 서버 전체 상한(`config.toml` `maxUploadSize`)은 200MB(Streamlit 기본값 — 2026-11-17 메모리
    보드 q-upload)이고 칸 고유 상한은 그보다 낮게만 둔다 — 올린 파일은 통째로 서버 메모리 바이트라 큰 파일 하나가 컨테이너
    메모리 한도(1GiB)를 넘기면 앱이 다시 선다. 모듈 올리기 칸도 그 값을 물려받는다(`docs/module_guide.md` 3-9,
    `tests/test_equipment_csv_upload_limit.py`).
  - 편집본은 세션의 **설비 시나리오 한 벌**이다(5장 32). `revision_token` 은 (공통, 일정) 쌍 토큰이고 저장본 사본과 함께
    그 쌍의 일정 없음(`DRAFT_UNSCHEDULED_KEY`)을 적는다. 계산 화면은 `calculation_drafts()`(일정 없음 호기와 그 비가동을 뺀
    셋)를 읽고, 편집 대조·`_saved_master()` 는 39칸 전부를 본다. 저장은 `save_equipment(EquipmentSaveRequest)` 로 간다 —
    출발점 칸(`_BASE_KEY` — 공통·일정·시나리오 id)과 이름 지도(`PendingRenames.units`)·저장자(`equipment_save_fields.py`). 함께 넣기 · 공식 발행은 요청 기본값 그대로 늘 한다.
    결과 알림(`save_result_message`)은 일어난 일만 적는다 — 첫 문장이 무거운 차례로(알림창은 앞 60자 안팎만 보인다 — `alerts.SHORT_LIMIT`) 「지운 호기 n대(다른 설비 시나리오 m개 일정도 빠짐)」·
    「공식 vN 지정」·「다른 설비 시나리오 k개에 호기 a대 · 비가동 b건」, 그 뒤가 공통 rN·시나리오 rN·시나리오마다의 함께 넣은 목록.
  - **이름 바꾸기는 같은 호기다**(G4·R2). `follow_unit_renames` 가 이름을 기억한 설비 마스터 탭 칸 — 비가동 일정 작은 편집표의
    선택·삭제 확인 대기의 키, 그 표 목록 필터(`설비명`, 위젯을 그리기 전에만 고칠 수 있어 `FOLLOWED_FILTERS_KEY` 에 모았다가
    `render_small_editor` 가 얹는다 — 자기 저장 뒤에도 남기고 버리기·남의 저장에는 버린다) — 를 새
    이름으로 옮기고 일괄 삭제 되살리기(`LAST_REMOVED_KEY` — 「한 단계 되돌리기」 의 맨 밑 단계)와 표 되돌리기의 행 조각 단계는 버린다(Main 설비 이름만 바꿔도). 저장 안 한 이름 바꿈은 Space 상자와
    설비 마스터 탭 알림 칸이 같은 `render_name_changes`(「이름 바꿈 n건」·`NAME_CHANGES_CAPTION`)로 보인다. 설비 마스터 표 호기
    상세의 설비명 칸 확정이 같은 호기 이름 바꿈이다(행 id 로 짝을 알아 공용 넷 — `equipment_grid._rename`). 붙여넣기·CSV 는
    설비명으로 맞대므로 바꾼 이름은 새 호기다(지운 + 새 호기 — Guide 가 말한다).
  - **다른 설비 시나리오에 일정이 있는 호기를 지우는 저장**(설계 11-2 6단계)은 묻지 않는다(2026-11-05 사용자 결정 — 옛 경고 · 확인 체크를 걷었다). 저장소가
    쓰기 잠금 안에서 그 시나리오들을 세어(`_scenarios_holding_units` — ACTIVE 다른 시나리오 **최신**의 일정 행 · 배치 차이 행) 저장 결과
    (`EquipmentSaveResult.removed_elsewhere`)에 싣고 결과 알림이 그 수를 적는다. 세 저장 길(탭 · 팝업 · Space)이 같다.
  - **배치 일곱 칸은 Space 와 같은 판정**(설비 시나리오 2단계 S3 — 페이지가 `space_edit_mode(...)` 를 설비 마스터 탭
    `render_equipment_master_tab(layout_mode=)` 에 넘긴다). "official" 은 공식 배치(공통 대장), "overlay" 는 그 가정 설비
    시나리오의 배치 차이다(공식은 바뀌지 않는다 — 새 호기는 공통에 자리 없이, Q1·Q2, 캡션 한 줄). 배치 칸을 바꾼 적용(표 출납·
    「편집본에 넣기」·「호기 추가」)은 그때의 역할을 찍는다(`stamp_layout_role`). "locked"(잠긴 회차)는 저장하면 저장본 호기
    키를 잇는 행(`layout_lock_origins` — `inherited_unit_names`)의 배치 일곱 칸을 표가 잠그고(`GridContext.layout_lock` — 출납도
    파이썬이 버린다) 새 호기는 자리 없이 맞추며(`LayoutLock.place` — `layout_overlay.hypothetical_common_places` 한 규칙),
    붙여넣기는 미리보기 전에 막는다(`layout_paste_refusal`). 저장본과 달라진 칸 판정·되돌림 재료는 `layout_edits`(`LayoutLock.
    restore`)다. 칸 머리 도움말 셋째 묶음 「배치 — …」(`services/equipment_grid.LAYOUT_COLUMN_HELP`)와 범례가 같은 뜻이다.
  - **붙여넣기·CSV 의 배치 칸**(Q2): 가정 세션은 「배치 칸도 붙여넣기」(`PASTE_LAYOUT_KEY`, 기본 끔 — 「현재 데이터」 CSV 는
    합친 값이라 공식 CSV 를 올리면 배치안이 공식 자리로 돌아간다)를 두고, 끄면 있던 호기의 배치 칸은 지금 값을 둔다(새 호기의
    배치 칸은 받는다 — 범위 줄 「붙여넣은 열 n개(…)만 바꿉니다」 도 배치 열을 빼고 「붙여넣은 배치 칸(…)은 새 호기에만
    넣습니다」 를 따로 적는다). 지금 값은 **읽을 때** 둔다(`read_equipment_update` 의 `keep_current` — 붙여넣은 그대로의 그
    호기 행은 `EquipmentPaste.held_rows` 로 받아 「넣지 않았다」 한 줄을 견준다) — 검증 뒤에 되돌리면 넣지 않을 배치 값의
    오류(좌표만 있고 크기 없음 등)가 미리보기를 막았다(2026-10-30 E2E). 켜면 「가정 배치 n대가 바뀝니다(그 가운데 m대는 공식 자리로 돌아가 차이가 지워집니다)」, 공식 세션은
    「공식 배치 k칸(호기 n대)이 바뀝니다」 경고. 미리보기 요약은 「배치 칸 k(호기 n대)」 를 따로 센다(`paste_split_summary`).
    미리본 뒤 체크를 바꾸면 후보를 다시 만든다(`ImportReview.layout_pasted`). 「현재 데이터」 꼴 CSV 이름의 시나리오가 세션과
    다르면 경고 한 줄(`_csv_scenario_mismatch`).
  - **저장의 대조 역할**(`_layout_role_of` — 설계 6-2): 찍힌 역할(`LAYOUT_ROLE_KEY`, 배치를 바꾼 적용마다 — Space 적용·이
    탭 배치 칸)을, 없으면 편집본에 배치 편집이나 층 값 대기분이 있을 때 지금 세션의 역할을 `expected_layout_role` 로 넘긴다.
    그 사이 남의 발행으로 역할이 바뀌었으면 저장소가 `EquipmentLayoutRoleChanged` 로 막는다. 찍힌 역할은 편집본을 다시
    세우거나·저장하거나·「배치 변경만 버리기」 하면 지우고, 남은 배치 편집이 없으면 `live_layout_role` 이 지운다(남은 찍힘이
    역할이 바뀐 뒤의 새 편집을 잠그지 않게). 편집본을 세울 때는 찍지 않는다(검토 M3).
  - **남의 공통 저장 뒤 가정 배치 편집 다시 얹기**(S4 — 설계 9장·검토 M4). 남이 공통을 저장해 편집본을 다시 세울 때(토큰의
    일정 쪽 그대로) 가정 역할로 찍힌 배치 편집이 있으면 옛 저장본 사본이 바뀌기 **전**에 재료(옛 사본·편집본·저장의 호기 키
    규칙 `layout_lock_origins`·옛 호기 키 쌍)를 들고, 새 저장본 위에 있던 호기의 배치 일곱 칸을 호기 키로 다시 얹는다
    (`ensure_equipment_drafts` → `layout_overlay.reapply_layout_edits` — 남이 그 사이 이름을 바꾼 호기도 따라가고, 지운 호기는
    빼고 알림에 이름). 다시 얹었으면 찍힌 역할을 남기고 세대를 한 칸 올린다(저장 안 한 편집). 배치 편집기가 적용한 묶음 모양
    승인(`stage_editor_module_layouts`)도 재료에 들고, 다시 얹은 결과에서 그 모양 그대로인 묶음만 새 저장본 이름으로 옮겨 다시
    둔다 — 버리면 편집기만 낼 수 있는 묶음(숨은 모듈이 있는 묶음 보내기 등)이 저장에서 「설비 마스터 표로 바꾼 값」 으로 막힌다(S4
    리뷰). 공통·일정 칸 편집·새 호기·층 요소·이름표 대기분·저장 안 한 이름 바꿈은 지금처럼 버리고, 공식 역할 편집·다른
    리비전(일정 쪽이 바뀜)은 다시 얹지 않는다. 알림(`discarded_notice`)이 다시 얹은 설비 수(묶음 1대)와 버린 것을 따로 적는다 —
    버린 이름 바꿈은 「이름 바꿈 n건」 으로 버린 것에 든다(`renames_dropped` — 같은 호기의 위치만 다시 얹고 이름은 돌아가 이름
    바꿈도 남았다고 읽혔다, E2E r6). 다시 얹을 편집이 남이 지운
    호기에만 있었으면(다시 얹은 0대) 버렸다는 글에 그 호기 이름과 까닭(「그 사이 공통 대장에서 빠진 호기 n대(…)의 편집은
    뺐습니다」)을 적고, 그 호기는 「최신 위에서 다시 옮기세요」 에 세지 않는다(E2E r6). 모양 검사·끝 확인은 저장이 다시
    본다. 편집본을 세우기 **전**(콜백)에 도는 저장 — 설비 마스터 「리비전 저장」·Space 「배치 저장」 — 이 남의 공통 저장에
    거부되면 같은 회차 본문이 편집본을 다시 세우므로 거부 글도 그 길을 말한다(`save_equipment_buffer(reopens=True)` →
    `common_conflict_reopened` 「이 화면을 그 저장본으로 다시 열었습니다(위 알림). 최신 저장본을 확인한 뒤 다시 고쳐
    저장하세요.」 — 끝 문장은 편집이 남든 모두 버려지든 맞는 말이다(콜백은 다시 세우기 전에 돈다) — 저장소의 「화면을 다시 불러와」 를 따라
    브라우저를 새로 불러오면 다시 얹은 편집을 잃었다, 2026-10-27 E2E). 본문에서 저장하는 사이드바 팝업은 이미 다시 세운 편집본으로
    저장하므로 넘기지 않는다.
  - 세션이 **낡음**이면 설비 마스터 탭 맨 위에 그 알림을 세우고 표의 시나리오 일곱 칸(잠금 갈래 `stale`)·비가동 일정 작은
    편집표를 잠그며 새 호기·저장본 호기 지우기를 막고(`newRowsLocked`·`deleteLock`), 붙여넣기 미리보기는 일정 칸 변경·새 행·
    비가동을 그 까닭으로 거부한다(`stale_paste_refusal`) — 공통 칸은 그대로 편집·저장된다. 칸 머리 풍선 첫 마디가 「공통 — …」/
    「공통 — 공식 일정 기준」(상태 둘)/「시나리오 — 「셋업 실무」 에만 저장」(`equipment_grid.scenario_column_help`)이고 표 범례가
    같은 뜻이다.
  - 저장 이력은 고른 설비 시나리오의 일정 리비전(번호·저장자·출처·공통 rN)이고 조회는 `load_saved_pair`(저장 때의 짝)다.
    표와 「조회 리비전」 상자는 리비전을 **전부** 싣는다(2026-11-01 사용자 결정 A4 — 표는 스크롤·찾기, 상자는 글로 찾음).
    「공통」 칸은 리비전 줄이 들고 온 번호(`common_revision_no`)가 먼저다(`common_revision_words` — 공통 대장 이력 목록은
    최신 50개라 옛 줄의 공통이 그 밖에 있다). 공통 칸만 바꾼 저장은 일정 리비전을 만들지
    않아 그 표에 없으므로 표 아래 안내 한 줄과 펼침 「공통 대장 저장 이력」(공통 rN·저장자·변경메모·호기행·그 공통을 함께 본 이
    시나리오 일정 rN — `_render_common_history`, 최신 50개)이 선다. 그보다 옛 공통 리비전이 있으면 머리가 「최근 n건(rA~rB)」 이다
    (`common_history_label`). 「현재 데이터」 CSV 이름은 `equipment_master_<시나리오>_r{no}_c{공통no}_<날짜>.csv` 다. 가정 시나리오의 일정 확인(「일정 확인
    필요」·표 풍선)은 공식 일정 + 편집본 공통 칸이다(`official_confirmation_master` — 세션 칸 한 벌).
- `src/capa_simulation/components/equipment_scenario_status.py` — 사이드바 조건 패널의 「설비 시나리오」 줄과 팝업, 그리고 설비
  화면들이 함께 쓰는 설비 시나리오 문구(일정 없음·설정 팝업 Cut-off 잠금·옛 배포 흔적 알림(`SB-19` — 「그 화면으로」 = `LEGACY_TRACE_GOTO`, 자리에는 단추가 없다)·기준선 거부·설비 출처 띠).
  세션 알림(다른 리비전으로 옮김 `SB-14` 사건 · 일정 없이 엶 `SB-20` 상태 — 범위 = 설비 시나리오)은 줄 아래에 그리지 않고
  알림 칸으로 낸다(`equipment_scenario_management.report_session_notices` — 시나리오 관리 설비 시나리오 탭과 한 함수). 불러오기 · 저장
  결과는 `queue_flash` → 줄 안 `render_flash`(성공은 알림창으로만 — D3).
  - 줄은 **페이지가** `resolve_equipment_session` 뒤에 `app.py` 가 세운 칸에 그린다(9장 「사이드바·조건 카드·본문」). 값 칸은
    「운영 일정 · r12」(긴 이름은 `app_header.short_scenario_name` 으로 줄여 「 · rN」 이 늘 보인다 — 값 칸은 한 줄
    말줄임. 머리 띠 꼬리도 같은 이름), 배지는 `미저장 변경`(낡은 세션이면 `미저장 변경 · 최신 rM 있음` — 미저장이 낡음을
    가리지 않는다, 머리 띠 꼬리도 같다) → `일정 없이 엶`(옛 배포 흔적이 공식과도 합쳐지지 않은 회차) →
    `공식 vN`(공식 발행 쌍이면 낡아도 이것이 먼저) → `최신 rM 있음` → `가정 배치`(그리는 리비전의 배치가 공식과 다름 —
    `EquipmentSession.layout_differs`, 라벨 dict 의 기본형이라 그리는 동안 저장소 호출 0) → `저장된 리비전` 차례. 잠근
    꼴(팝업 없음)은 값 칸 끝 「(고정)」 — 공정 Capa 상세 HOME 방문뿐이다(줄 아래 표지 한 마디 `LOCK_REASON_MARK` 「HOME 칸
    방문 · 공식 고정」 이 서고 그 까닭 `HOME_VISIT_LOCK_REASON` 은 표지의 풍선이다 — 꺼진 단추라 값 칸에는 풍선이 없다. 푸는 법
    「이 화면 탭을 닫고 다시 여세요」 까지 적는다). Space 현황은 고를 수 있는 줄이다(S3). 공통 진입(계산)이 멈춘 회차의 줄은
    `render_stopped_equipment_scenario_row` 한 벌이다 — 공정 Capa 상세 · 제약 시뮬레이션이 잠긴 공정 줄과 함께 불러 세션 설비
    시나리오를 잠그지 않고 세운다(설비 DB 를 못 읽으면 줄 없음 — 2026-11-10 답 Q2-29 · 2026-11-11 보드 C1).
  - 팝업은 `app.py` 의 `render_condition_dialogs` 셋째 갈래다. 「불러오기」(시나리오 → 리비전 라디오, 공식 발행 리비전에
    표지, 미저장이면 「변경을 버리고 불러오기」)와 「저장」 — 저장 구획은 편집본을 세우는 가용설비 현황·필요 단축 일정에만
    선다(`SAVE_PAGES`). 저장소는 팝업을 연 동안에만 읽는다(5장 23). 리비전 라디오는 최근 50개까지이고(한 줄씩 길어 — 결정
    A4. `load_recent_equipment_schedule_revisions` 가 전부 읽은 칸의 앞머리를 준다), 한도에 걸리면 라디오 아래(팝업 맨 끝)
    「최근 50개 · 전체 N개 — 더 옛 n개는 시나리오 관리 › 설비 시나리오에서 고릅니다.」 한 줄이 선다(`OLDER_REVISIONS_PLACE`).
    화면 확인 스크립트
    (`equipment_scenario_line`·`space_scenario_row`)가 그 줄의 전체 수를 「리비전 50개(전체 N개)」 로 옮긴다
    (`REVISION_TOTAL_PATTERN` — 글 꼴을 바꾸면 함께 고친다).
- `src/capa_simulation/components/equipment_save_fields.py` — 설비 마스터 저장의 저장자 칸(`render_saved_by_field` — 이름 줄 없이 칸 안
  안내 글 `SAVED_BY_PLACEHOLDER` 「저장자 · 예: 홍길동」(`saved_note.field_placeholder` — 변경 메모 칸과 한 꼴, 라벨 「저장자(선택)」
  은 접근성 이름)이 이름, 입력 비가동 저장자 칸도 같은 글 · 콜백이 읽는
  `saved_by_from_state`)·저장 출발점 값(`EquipmentSaveBasis`) — 세 저장 단추 풍선은 어디로 저장되나 한 줄이고 늘 하는 일은 Guide · 결과 알림이다. 설비 마스터 탭 「저장 전 변경」 의
  「리비전 저장」(콜백, 저장자 칸은 `persist` — 탭 ① 은 숨은 회차에 그리지 않는다)·사이드바 팝업 「저장」·Space 「배치 저장」(콜백)
  세 자리가 같은 부품을 쓴다.
  - **저장 자리에는 체크가 없다**(2026-11-05 사용자 결정 — 검수표 11/02 equip-13: 「체크 없이 발생되는 내용들만 알람으로」). 저장은
    `EquipmentSaveRequest` 기본값 그대로 늘 새 호기 · 새 비가동을 함께 넣고(F6 · F2) 공식 설비 시나리오에 새 일정 리비전이 생기면 공식으로
    발행한다(G1). 가정 세션에서 공식에 넣을 것이 없으면 저장소 판정(`_plan_publish`)이 발행하지 않으므로 옛 「그리지 않은 발행 체크는
    거짓」 과 결과가 같다. 지우는 호기도 묻지 않는다. 일어난 일은 결과 알림(`save_result_message`), 저장 전 말은 단추 풍선 · Guide 다 —
    갈래를 고를 일이 생기면 그때 기능으로 짓는다. 저장소의 `propagate_new_*` · `publish_official` 인자는 시험 · 스크립트 · 앞으로의 기능을
    위해 그대로 둔다. 「새 호기」 칸에도 호기마다의 고름 · 경고가 없다(2026-11-05 사용자 답).
- `src/capa_simulation/components/scenario_management_tabs.py` — 시나리오 관리 탭 넷의 이름 · 탭 기억 key · 알림의 `tab` 이름(`*_TAB_NAME`)과 다른
  화면에서 그 탭으로 옮기는 길(`open_scenario_management_tab`) 한 곳.
- `src/capa_simulation/components/equipment_scenario_management.py` — 시나리오 관리 「설비 시나리오」 탭(1단계 몫 + E7 —
  2026-10-24 가용설비 현황의 탭에서 옮김). 탭 진입(`render_equipment_scenario_section` — 설비 DB 는 이 안에서만 연다, 세션
  알림 — 세션이 든 리비전은 탭 머리 줄이 아니라 시나리오 표 「올라와 있음」 칸 「● rN」, 낡은 세션이면 「● rN · 최신 아님」 `loaded_cell`)을 둔다 — 다른 화면에서 이 탭으로 오는 길은 `SB-19` · `SB-20` 알림 줄의 「그 화면으로」
  (`LEGACY_TRACE_GOTO` + `tab` — 시나리오 관리 › 설비 시나리오 탭)이고 설비 화면 맨 위 링크 단추는 없다. 시나리오
  표(「공식 vN · rM」/활성 — rM 은 공식 발행 리비전, 발행 확인 글과 같은 `official_release_revision_no` 로 찾고 못 찾으면 「공식 vN」 만·최신 rN·
  리비전 수·저장된 배치 차이·올라와 있음)와 고른 시나리오의 「시나리오 이름 바꾸기」(가정 시나리오 최신에 배치 차이가
  있으면 「배치 차이 모두 지우기」 도), 리비전 표(리비전명·출처 `이관/저장/복제/함께 넣기/되돌리기/배치 차이 정리`·공통 rN·행
  수·배치 — 표와 리비전 상자는 리비전을 **전부** 싣는다(2026-11-01 사용자 결정 A4 — 사이드바 팝업 라디오만 최근 50). 표
  아래 한 줄이 늘 전체 수와 출처별 수 「전체 82줄(이관 70 · 저장 12)」 을 적는다 — 사내 런북의 「리비전 N줄 = 이관 N」 은
  이 줄의 이관 수를 8-4s `L` 과 견준다. 상자가 길어도 `prune_named_choice` 는 지금 선택지 글자를 늘 든다)와 고른 리비전의 작업 다섯 — 「이 리비전 불러오기」·「이 리비전으로 되돌리기」·「여기서 새
  시나리오」·「리비전명」·「공식으로 지정…」(지금 공식 → 새 공식, 최신이 아니면 그 사실, 발행 번호 대조) — 과 옛 배포 흔적이
  있을 때만 「이대로 이어 쓰기」. 구획 본문은 DB 경로와 그 회차 세션만 받아 따로 선다.
  리비전 표에는 「일정 없음」(그 리비전에 일정 행이 없는 호기 수) 칸을 두지 않는다 — 이 탭에서 일정 없음 수는 「여기서 새 시나리오」 · 「이 리비전으로 되돌리기」 값 줄과 되돌리기 확인 체크 글이 적는다(세션 리비전 쌍의 일정 없는 호기는 가용설비 현황 · Space 의 `EQ-04`).
  - 쓰기는 저장소가 하고 그 뒤 이 화면이 `clear_equipment_scenario_cache()` 를 부른다(저장소는 캐시 경계를 import 하지
    않는다). 「설비 시나리오」 쪽을 고른 회차에만 목록을 읽는다. 그 사이 남의 쓰기로 거절된 작업(되돌리기의 최신·공통·발행 대조, 리비전명·시나리오 이름 비교 후
    쓰기)은 `_refused` 가 공통 최신·목록을 비우고 입력 칸 세대를 올려(옛 확인 체크로 다시 누르지 않게) 맨 위에 알린다 — 구획
    맨 위 칸과 알림창 · `Alarm` 둘에 선다(`FL-04` — 확인 칸을 다시 세우는 거절이라 `docs/design_rules.md` UI-NTF-03 의 예외,
    2026-11-04 반영 검수표 D3 (가)).
    이름 바꾸기 · 리비전명 · 공식으로 지정은 남의 저장 충돌만이 아니라 거부로 끝나는 갈래마다(이름 바꾸기의 본 값 없음 `SEEN_MISSING_MESSAGE`, 공식 지정의 본 확인 글과 다름 · 배치 차이 막힘 포함) 거부 표지(`_refused_noted`)를 적어, 창 안의 둘째 누름은 쓰지 않고 그 거부를 다시 알린다(`_repeat_held_refusal`). 되돌리기 · 배치 차이 모두 지우기는 거부 뒤 확인 체크가 풀려 단추가 잠기므로 표지를 두지 않는다.
  - **확인 창의 글**(되돌리기 · 여기서 새 시나리오 · 배치 차이 모두 지우기 — 2026-11-05 사용자 결정 그림 검수표 equip-41 「권장대로」, 설계 규칙 UI-NTF-09). 안내 문장을 늘어놓지 않는다 —
    결과를 가르는 값은 값 줄 하나(`restore_value_line` · `branch_value_line` · `clear_layout_value_line`, 문장으로 끝나지 않는 `st.caption`)와 확인 체크 글의 수(`restore_confirm_label`)로, 설명은
    그 단추 풍선(`restore_button_help` · `branch_button_help` · `clear_layout_button_help` — 잠긴 동안에도 뜬다)과 Guide 로, 일어난 일은 결과 알림으로 보낸다. 이름 · 메모 · 저장자 칸과 확인 체크 · 잠긴 단추는 그대로다.
    배치 차이에 하는 일은 값 줄 조각과 풍선 문장이 **한 갈래 함수**에서 나온다(`_restore_layout_effect` · `_branch_layout_effect`) — 둘이 갈리지 않게. 시뮬레이션 쪽도 같은 기준이다 — `_render_archive`
    는 체크 · 단추만(뜻은 단추 풍선), `_render_official` 은 값 표지(`SAME_AS_OFFICIAL_LINE`) + 지정 단추 풍선이고, 되돌릴 수 없는 영구 삭제의 양(`delete_scope_warning`)과 가상 제품 확인 목록은 자리에 남는다(UI-NTF-09).
  - **되돌리기**(E7)는 고른 리비전이 최신이 아닐 때만 체크 · 단추를 세운다 — 값 줄이 새 번호 · 비가동 행 수 · 일정 없음(새로 빠지는 수) · 배치 표지 · 공식 시나리오의 발행 표지(`_restore_publish_value` — 저장소
    `_plan_publish` 와 같은 규칙으로 「공식 vN 지정」 · 「공식 지정 안 함」, 체크 없이 늘 — 결과 알림이 적는다, 2026-11-05 equip-13 같은 꼴), 확인 체크 글이 바뀌는 호기 수와 「rK 뒤에 공통 대장에 든 호기 n대」(늘 수와 함께 — 0대면
    「없습니다(0대)」)를 적는다. 되돌릴 것이 없으면(`restore_writes_nothing`) 결론 한 줄이고 단추 · 풍선이 없어, 공식 시나리오에서 따라오지 않는 배치 차이는 그 앞 표지(`restore_layout_marker`)가 말한다. 확인 체크를 켜야 단추가 선다. 이
    세션이 그 시나리오를 보고 저장 안 한 설비 편집이 없으면 세션을 새 리비전으로 옮기고(`select_equipment_scenario`), 편집이
    있으면 두고 낡음 잠금에 맡긴다. 탭의 리비전 상자도 다음 회차에 새 리비전으로 옮긴다(`PENDING_REVISION_KEY` — 위젯을 그리기
    전에 적는다).
    결론 한 줄은 「최신 rN의 일정·비가동·가정 배치와 모두 같아 되돌릴 것이 없습니다.」 이고 공식 시나리오는 배치 차이가 따라오지 않아 「일정·비가동과」 다 — 확인 체크를 켠 누름이 그 사이 남의 저장으로 쓸 것을 잃은 알림(`restore_gone_message`)도 같은 갈래다.
  - **확인 체크는 본 확인 글에 묶는다.** Streamlit 1.63 체크박스는 key 가 같으면 글이 바뀌어도 값을 지킨다. 그래서 체크 key 꼬리는
    확인 글을 정한 값 다섯(`restore_seen_token` — 시나리오·고른 리비전·그 시나리오 최신·공통 최신·공식 발행 번호)이고 입력 칸
    (새 리비전명·메모·저장자) key 꼬리는 고른 리비전이다. 저장소에 넘기는 대조값도 그 회차에 그 꼬리를 만든 같은 값이다
    — 다른 리비전을 고르거나 확인 뒤 남의 저장·발행으로 값이 바뀐 회차에는 체크가 풀린 새 칸이 서고 단추가 잠긴다. 잠가 그린
    단추의 클릭은 서버가 버리므로(9장 「잠긴(disabled) 위젯」) 단추는 「확인 체크 뒤에만 선다」 대로 잠그되, 체크가 켜진 회차의
    값을 `RESTORE_AGREED_KEY` 에 적어 두고 같은 리비전에서 값만 바뀐 회차에 체크를 풀었다고 알린다 — 누른 회차에 버려진 클릭도
    그 알림으로 까닭이 보인다. 단추 처리도 체크를 다시 본다(`not clicked or not agreed`). 값이 그대로인데 캐시가
    늦어 저장소가 그 사이 쓰기를 보면 `EquipmentRevisionConflict`·`EquipmentReleaseMoved` 로 거절한다(`_refused`).
  - **여기서 새 시나리오**는 1단계 복제(만들기는 복제로만)의 출처를 고른 리비전으로 넓힌 것이다 — 값 줄이 새 시나리오의 일정
    없음 수와 그 리비전 뒤에 든 호기 수를 적고, 그 리비전에 배치 차이가 있으면 새 r1 로 함께 옮기는 차이(정규화 — 되돌리기와
    같은 `restored_layout_*`, 빠지는 행·그때와 자리가 다른 호기 수는 풍선 문장 `branch_layout_sentence`)도 적는다(2026-10-26 E2E,
    안내가 일정·메모·비가동만 말했다). 확인 체크는 없다(이름을 적어야 만들어지고 이 시나리오는 그대로다). 확인 재료는 둘 다 `load_schedule_restore_preview`(불변 리비전 id 셋 + 층 현행값
    쓰기 세대 키) 한 칸.
  - **리비전명**은 칸을 세울 때 본 이름을 따로 들고(`…__seen`) 그 이름으로 비교 후 쓰기를 한다 — 칸이 고치지 않은 채면 남이
    바꾼 이름으로 다시 선다. 비우면 지운다. **시나리오 이름 바꾸기**도 같은 꼴이다 — 팝오버 안 칸은 매 회차 그려져 key 가
    남으므로 그 회차 목록 이름을 `expected_name` 으로 넘기면 대조가 늘 통과해 남의 이름 바꿈을 말없이 덮는다(2026-10-26 E2E).
    두 칸 모두 고치지 않은 칸은 **매 회차** 지금 이름을 다시 적는다(`widget_generation.seed_field`) — 닫힌 팝오버 안 칸은 브라우저에
    마운트되지 않아 나중에 열 때 마지막 회차가 실어 보낸 값으로만 서므로, 처음 세운 회차에만 적으면 한 회차 뒤에 연 칸이 빈
    칸으로 서고 그대로 누른 「리비전명 저장」 이 이름을 지웠다(2026-10-26 E2E 3회차, 9장 「닫힌 팝업 안」).
  - **공식으로 지정**은 확인 글을 그린 회차의 {고른 리비전, 공식 번호}를 `PUBLISH_SEEN_KEY` 에 남기고, 단추를 누른 회차에 그
    번호가 지금과 다르면(그 사이 남이 발행) 쓰지 않고 `_refused` 로 까닭을 알린다(`publish_seen_refusal`) — 누른 회차에는 확인
    글이 이미 새 목록으로 다시 그려져, 지금 번호로만 대조하면 「v1 → v2」 를 본 사람이 말없이 v3 을 낸다. 저장소 대조값도 그 번호다.
    그 시나리오 최신(id·번호)도 함께 남겨(`publish_seen_token` — 「rN은 … 의 최신(rM)이 아닙니다」·배치 줄을 정하는 값) 그 사이 남이
    같은 시나리오에 새 리비전을 저장했으면 같은 길로 거절한다 — 그 줄을 본 적 없는 사람이 최신이 아닌 리비전을 말없이 냈다
    (2026-10-26 E2E 3회차). 최신 대조는 화면 몫이다(저장소는 공식 번호만 대조 — 최신이 아닌 리비전 발행은 원래 된다).
    확인 글 「지금 공식 vN · 「…」 rK」 의 rK 는 발행 줄이 들고 온 번호다(`official_release_revision_no` — 저장소
    `latest_release_row` 가 발행한 일정 리비전의 `revision_no` 를 함께 읽어 `EquipmentRelease.revision_no` 로 싣는다, 목록 캐시와
    같은 칸). 그 시나리오 최신·세션 스냅샷만 보면 공식이 그 시나리오 최신이 아니고 세션이 그것을 들고 있지 않을 때 번호가 빠져
    지금 공식이 최신처럼 읽혔고(2026-10-26 E2E 3회차), 리비전 목록에서 찾으면 공식이 그때의 목록 한도(최근 50줄) 밖일 때
    빠졌다(개선 I25 — 지금 구획 목록은 전부지만 발행 줄 번호를 그대로 쓴다). 발행 줄에 번호가 없는 옛 캐시 값이면 최신·세션 스냅샷에서만 찾고,
    없으면 번호를 뺀다.
    고른 리비전이 이미 지금 공식이면(`already_official`) 저장소가 쓰지 않고 그 발행을 돌려주므로 확인 글은 「→ 새 공식」 없이
    지금 공식과 값 표지(`ALREADY_OFFICIAL_LINE` — 「이미 공식 리비전」)만 적고 「공식으로 지정」 을 끈다 — 끈 까닭은 그
    단추 풍선 앞머리(`ALREADY_OFFICIAL_HELP`, 배치 차이로 막혔으면 막힘 글 — 설계 규칙 UI-INP-07, 뒤는 늘
    `PUBLISH_BUTTON_HELP`)가 말한다(개선 거리 I26, 2026-11-01 사용자 결정 — 「발행해도 바뀌지 않습니다」
    위에 켜진 단추가 서로 어긋났다, E2E #37·#97). 첫 발행 뒤 다시 그린 화면은 그 리비전이 공식이라 단추가 꺼지고, 그 단추에 닿은
    빠른 둘째 누름은 Streamlit 이 버려(1.63 `SessionState` 가 꺼진 위젯의 값을 버린다) 그 회차가 첫 발행 알림을 지웠다. 발행은
    알림을 `note_notice`(칸 `FLASH_KEY` — 작업 알림 칸과 같은 이름)로 적고 — 정리 발행은 `_follow_and_announce(notices=…)` 가
    옮김까지 든 글을 — 구획 맨 위 알림 칸(`flash.render_flash(FLASH_KEY, REFUSED_KEY, GONE_KEY)`)이 담아 둔 알림이 없는 회차에 창
    (`TRAILING_PRESS_SECONDS`) 안이면 그 글을 첫 알림과 같은 id 로 다시 낸다(알림창은 두 번 뜨지 않는다, 팝오버 세대는 올리지
    않는다 — 첫 알림 회차가 올렸다). 작업 알림(성공)은 알림창 · Alarm 으로만, 거절(`REFUSED_KEY` — 오류)은 그 칸에도 그린다
    (2026-11-04 설계 규칙 UI-NTF-01 · 03). 그 사이 남의 쓰기로 꺼진 단추의 누름(`GONE_KEY` — 경고,
    `_announce_gone_press`)도 알림창 · Alarm 으로만 내고(고칠 입력이 없다 — UI-NTF-03) 팝오버 세대는 올리지 않는다(바뀐 확인
    글이 그 안에 선다).
    둘째 누름이 아직 켜진 단추로 들어오면(목록 캐시가 늦은 회차) 저장소가
    쓰지 않고 「「…」 rK은 이미 공식 vN입니다 — 새로 지정하지 않았습니다」 다(`already_released_message` — 「공식 vN로
    발행했습니다」 로 새 발행처럼 알렸다, 2026-10-27 E2E). 창 안이면 첫 발행 알림을 다시 낸다. 쓰지 않은 발행은 제 저장 짝을 적지
    않는다. 꺼진 단추에 닿은 누름은 AppTest 가 `click()` 으로 보내지 못해 시험은 누름 값을 바로 싣는다
    (`tests/test_equipment_scenario_publish_guard.stale_press`).
  - **팝오버·알림 자리**(2026-10-25 E2E). 맨 위 작업 알림·거절 알림, 옛 배포 흔적 구획, 구획 머리의
    (세션 이동 알림은 2026-11-03 부터 알림 칸 — `report_session_notices`) 생기거나 빠져도 뒤 형제의 자리가 그대로이게 늘 서 있는 `st.container()` 칸 안에 그린다(9장 「key 가
    있어도 자리는 고정한다」 — 알림이 빠지는 회차에 key 없던 팝오버 줄이 한 칸 당겨져 다시 서며, 알림 뒤 처음 누른 확인
    체크·Tab·Enter 가 열린 팝오버를 닫았다). 팝오버 일곱의 key 꼬리는 팝오버 세대(`POPOVER_GENERATION_KEY`)다 — 한 번뿐인
    알림을 그리는 회차에만 올라 작업을 마친 팝오버는 그 회차에 닫힌 채 다시 선다(전과 같다). 리비전 표 앞 띄움
    (`REVISION_TABLE_TOOLBAR_CLEARANCE` 24px)은 표 오른쪽 위로 솟는 도구 막대가 바로 위 줄 맨 오른쪽 팝오버 단추(「시나리오
    이름 바꾸기」·「배치 차이 모두 지우기」)를 덮어 누름을 가로채지 않게 한다(9장 「표 도구 막대」).
  - **이대로 이어 쓰기** 확인 체크 key 꼬리는 체크 글을 정하는 값 셋(흔적 수·옛 배포 리비전 번호·빠지는 호기 수 —
    `continue_confirm_key`)이다(되돌리기 체크와 같은 까닭). 발행 번호 0 은 「v0」 이 아니라 「공식 없음」(`release_words`)이다.
  - **배치 차이(설비 0031 — S4)**. 시나리오 표 「저장된 배치 차이」 는 최신의 **저장된** 행(원시 — 「호기 3행·요소 1개」 ·
    `EquipmentScenarioSummary.latest_layout_rows`), 리비전 표 「배치」 는 그 리비전의 저장된 행이다. 저장된 행 뒤 괄호에 지금 공식과 견준
    실효 표지 — 「(공식과 같음)」·「(실효 호기 2대 · 지운 호기 1행)」(`layout_effect_words`) — 를 붙이는데, 재료는 발행 확인 글과
    **같은 판정·같은 캐시 칸**(`_latest_layout_previews` → `load_layout_publish_preview(공통 최신, 최신, 최신)`)이라 배치 차이가 있는
    시나리오의 **최신**만 센다(시나리오 표 전부와 리비전 표 최신 줄 — 옛 리비전 줄은 원시, 판정을 읽지 못한 시나리오도 원시). 칸이
    시나리오 수보다 적으면 회차마다 합친 본문을 다시 지어 판정 캐시 칸을 32 로 둔다(`LAYOUT_PUBLISH_PREVIEW_CACHE_ENTRIES`, E2E #11·#82). 옛 판(0031 을 모르는 배포)이 차이 있는 리비전 뒤에 저장한 리비전(옛 코드 흔적 — 목록 셈 `layout_trace_count` 와
    같은 규칙 `layout_trace_sources`)은 「옛 판 저장 — rN 배치 빠짐」 칸 표지만 자리에 남는다. 흔적이 있는 시나리오 전부의 빠진
    리비전(「이름」 rT(rN 배치 빠짐))과 되살리는 길(빠지기 전 리비전을 고르고 「이 리비전으로 되돌리기」)은 상태 알림 `SC-03`
    (`report_layout_traces` — 구획 머리, DB 전체 조건이라 범위 없음, 전문 `layout_trace_words` 는 고른 시나리오에 기대지 않는다)이
    낸다(2026-11-07 답 place-box). 사이드바의 옛 배포 흔적 `SB-19` 는 `goto` 가 시나리오 관리 설비 시나리오 탭이다. 저장은 막지 않는다(설계 14장).
    「배치 차이 모두 지우기」(`clearable_layout` — 가정 시나리오 최신에 차이가 있을 때만)는 확인 체크 key 꼬리가 (시나리오, 최신
    id)라 남의 저장 뒤 체크가 풀리고 — 켠 회차의 값(`CLEAR_LAYOUT_AGREED_KEY`)과 다음 회차 최신을 견줘 「확인한 뒤 … 의 최신이
    바뀌어(r2 → 지금 r3) … 확인 체크를 풀었습니다」 를 한 번 알린다(팝오버 안 체크 칸 위, 지울 것이 없어 단추째 사라졌으면 시나리오 줄
    아래 늘 서 있는 칸 — `clear_layout_unchecked_notice`, 되돌리기와 같은 꼴. 제 쓰기·거절은 `_written`·`_refused` 가 그 값을 비워
    알리지 않는다, E2E #9·#56) — `clear_layout_overlay(expected_latest_schedule_revision_id=)` 뒤 이 세션이 그 시나리오를
    보고 저장 안 한 편집이 없으면 새 리비전으로 옮긴다(되돌리기와 같다). 「공식으로 지정」 은 발행 쓰기와 **같은 판정**
    (`equipment_repository._layout_publish_preview` → `load_layout_publish_preview` — 불변 id 셋 + 층 현행값 세대 키)을 미리 읽어
    막히면 단추를 끄고 자리에는 값 표지(`LAYOUT_BLOCKED_LINE` — 「배치 차이로 지정 막힘」)만 두며 막힘 글(`layout_publish_blocked_words` — 발행 쓰기 거부와 같은 한 곳)은 그 단추 풍선이 말하고(2026-11-05 검수표 11/02 equip-44 — 빨간 상자와 풍선이 같은 글로 겹쳤다), 공식과 같아진 차이만
    남았으면 「… m행을 정리한 rN+1 로 지정합니다」 를 적는다(머리 「배치는 공식과 같습니다」 와 발행 거부가 함께 뜨지 않게 —
    검토 F4). 막힘 글은 까닭 셋으로 갈린다 — 고른 리비전에 공식과 다른 배치(「실효 … — 저장된 차이 m행」, 최신이면 공식에서
    옮기기·「배치 차이 모두 지우기」, 옛 리비전이면 그것으로는 풀리지 않아 「이 리비전으로 되돌리기」 뒤 지우고 발행), 옛 리비전에
    남은 행이 지금 공식과 같음(「공식과 다른 배치」 라 하지 않고 되돌린 뒤 발행 — 정리 발행은 최신만), 고른 리비전에는 없고 최신에
    행이 남음(실효가 있으면 그 수, 없으면 「지금 공식과 같음」 과 최신 발행). 옛 리비전으로 되돌려도 쓸 것이 없으면
    (`LayoutPublishPreview.restore_same_schedule`·`restore_same_layout` — `_layout_publish_preview` 가 막힌 옛 리비전만
    `_restore_preview` 로 재고, `block(official=)` 이 `restore_writes_nothing` 과 같은 규칙으로 합친다) 그 팝오버에 단추가
    없으므로 되돌리기를 안내하지 않고 최신 발행(가정이면 최신을 비운 뒤), 최신이 이미 공식이면(`newest_released`) 「따로 발행할
    것이 없습니다」 를 적는다(E2E r5). 공통 대장에서 지운 호기의 저장된 행
    (`LayoutPublishPreview.orphan_units`·`newest_orphan_units` → `PublishBlock.orphan_rows`)은 「공식과 같아진」 행이 아니라
    버린 행이라 정리·막힘·발행 뒤 글이 「지운 호기의 배치 차이 n행」 으로 따로 말한다(`layout_overlay.cleaned_layout_words`·
    `settled_layout_reason`, E2E r3) — Space 배치 알림(`EQ-13`) 전문의 「공식과 같아진 것은 … 정리됩니다」 꼬리도 그 행
    (`layout_orphans`)을 빼고 센다(알림 `EQ-15` 「지운 호기의 배치 차이 n행은 버렸습니다」 가 말한다). 공식 시나리오의 가정이던 때 리비전을 잠그는 줄
    (`space_edit_mode`)도 같은 셈(`EquipmentSession.live_layout_rows`)이라 남은 것이 지운 호기의 행뿐이면 수 없이 「가정이던 때
    저장한 리비전이라 잠갔습니다」 이고, 그 옛 리비전(불변)의 둘째 줄은 「다음 저장 때 빠집니다」 를 붙이지 않는다(E2E r6 —
    「배치는 공식과 같습니다」 옆에 「배치 차이(호기 1대)가 있어 잠갔습니다」 가 섰다). 잠금은 그대로다 — 저장소가 그 리비전의 차이
    행으로 공식 배치 고침을 거부한다. 정리 발행 뒤에는 「배치 차이 모두 지우기」 처럼 리비전
    상자와 그 시나리오를 보던 세션을 새 리비전으로 옮긴다(`_follow_new_revision` — 저장 안 한 편집이 있으면 남김, S4 리뷰).
    새 리비전을 쓴 쓰기(되돌리기·배치 차이 지우기·정리 발행)는 옮기기에 앞서 그 뒷정리를 dict 칸(`FOLLOWS_KEY` — 쓰기 전에
    받아 둔다)에 적는다(`_follow_and_announce`) — 더블클릭의 첫 회차가 쓴 직후 끊기면 둘째 누름은 꺼지거나 사라진 단추라
    버려지고 화면·세션이 옛 리비전에 남았다. 다음 회차가 구획 맨 위(리비전 상자를 그리기 전)에서 창(`TRAILING_PRESS_SECONDS`) 안의
    표지를 보고 옮기기와 그 쓰기의 알림을 잇는다(`_resume_follows`, `tests/test_write_guard_cas.py`). 제 발행 갈래도 저장소에서
    바로 읽은 그 발행의 리비전으로 정리 번호를 알리고 옮긴다(`_published_again`).
    되돌리기 값 줄은 되살리는 가정 배치에서 그때와 자리가 다른 손대지 않은 호기 수(`layout_moved_since` — 이력
    「그때 그대로」 와 다름, 검토 F21)를 덧붙인다.
- `src/capa_simulation/components/qual_deadline_calculator.py` — 필요 단축 일정 머리 「Qual 마감 계산기」 팝업의 본문
  (2026-10-24 — 가용설비 현황의 탭에서 옮김). 숫자 칸 넷·12개월 편집표를 받아 KPI 넷·호기별 표·월 점검 표(판정 칸·지난 마감
  칸은 상태색 면, 고정 uuid Styler)를 그린다 — 내려받기는 두 결과 표의 표 도구 막대 하나다(설계 규칙 UI-LAY-12 — 2026-11-07 답
  csv-dup · g4-18).
  - **이벤트 칸에 아무것도 쓰지 않는다** — 두 칸 배치·지표 줄·상태색 띠의 서식은 맨 위 안내 한 줄과 한 `st.html`
    (`calculator_style_markup`)에 싣는다(9장 「팝업 본문은 이벤트 칸에 같은 수만」). 그래서 `status_metric` 의 `metric_row`·
    `render_status_metric` 을 `emit_style=False` 로 부른다. 팝업 머리가 제목이라 본문에 제목을 다시 적지 않는다.
  - 팝업 폭은 이 팝업만 넓힌다 — Streamlit 1.63 큰 팝업은 1120px 에서 멈춰 두 칸이 늘 위아래로 쌓였다(1280·1600·1920 창
    실측). 같은 서식 덩이에 팝업 상자(`stDialog` 안 `div:has(> [role="dialog"] .st-key-<배치 key>)` — 폭은 `role="dialog"`
    의 부모가 쥔다) 폭을 창 폭 − 48px, 최대 1400px 로 싣는다(`_DIALOG_MAX_PX`) — 1280px 창부터 개편 전 탭처럼 입력 칸 옆에 결과가
    선다(호기별 표 가로 넘김 없음). 팝업 DOM 이 바뀌면 넓히지 못할 뿐 쌓여 그대로 쓴다.
  - 입력은 세션에만 둔다 — 숫자·날짜 칸은 `persist_state`, 편집표는 `on_change` 콜백이 원본 표(`MONTHS_KEY`)에 옮긴다
    (팝업을 닫았다 열어도 남는다). 「예시로 되돌리기」·「모두 비우기」 는 콜백이 칸을 적고 `discard_editor` 한다.
  - 엑셀 여러 칸은 원본처럼 「엑셀에서 한 번에 붙여넣기」(`remembered_expander` 안 폼의 글 칸 + 「표에 넣기」 콜백,
    규칙은 `qual_deadline.parse_pasted_months`)로 받는다 — 편집표 붙여넣기는 브라우저 클립보드 읽기라 보안 문맥이 아닌
    주소에서 막히고 신규 호기 칸 뒤를 버린다. 목표 칸에는 `step` 을 주지 않는다 — Streamlit 1.63 편집표 `NumberColumn` 은
    `step` 의 소수 자릿수에서 값을 잘라 저장한다(19.3456 → 19.34). 계산이 가벼워 캐시하지 않는다.
  - 원본은 입력을 브라우저 저장소에 남겼고 앱은 세션에만 둔다 — 메우지 않는다(`docs/TODO.md` 3장 결정 기록 「화면」).
  - 배치는 원본처럼 넓으면 입력 칸(420px) 옆에 결과 칸, 두 칸을 담은 줄이 결과 칸이 호기별 표를 다 담지 못할 만큼
    좁으면 위아래로 쌓는다(`layout_style` — 줄 폭 컨테이너 질의, flex 항목은 `stLayoutWrapper`). 창 폭이 아니라 줄
    폭으로 가르는 것은 사이드바가 본문 폭을 바꾸기 때문이다. Streamlit 격자는 칸 폭의 합이 표보다 좁으면 남는 폭을
    붙박지 않은 칸에 고루 붙이고 넓으면 가로로 넘기므로, 편집표 세 칸 폭의 합은 가장 좁은 입력 칸(390px 창 —
    `_NARROW_EDITOR_PX` 270px 실측) 안에 두고(넘치면 `신규 호기` 머리가 잘리고 그 칸을 고칠 때 `월` 칸이 가려진다 —
    2026-10-25 E2E) 읽기만 하는 `월` 만 붙박아 넓은 창의 남는 폭은 두 입력 칸이 나눈다(입력 칸을 붙박으면 값이 흐린
    글자라 잠긴 칸처럼 보인다). 호기별 표 `메모` 칸에는 메모 한 가지가 다 보이는 폭을 준다.
- `src/capa_simulation/components/manual_downtime_tab.py` — 가용설비 현황 탭 ③ 「Preference」 본문 — 공정 × 생산월 입력
  비가동대수 편집표(폼 밖 `st.data_editor` — 첫 칸 공정 표시명 잠금, 달마다 `NumberColumn` 0 이상 `%.2f`, 빈칸 = 0, 폼이 두르던
  테두리는 `st.container(border=True)` 로 그대로)·「되돌리기」·저장자·변경 메모(두 칸은 라벨 줄을 걷고 placeholder 가 이름 —
  2026-11-09 상단 띠 재고, `persist_state="session"`)·「입력 비가동 저장」(버전 대조 — HOME 확보율 보정 편집표와 같은 `write_guard` 길: 본 version·제 저장 짝·거부 뒤 둘째 누름)·
  저장 이력 펼침.
  - **적은 칸은 세션 초안이다**(`MANUAL_DRAFT` — `SessionSlot`, (공정, 달) → 값, 저장본과 다른 칸만 — 2026-11-19 사용자 요청
    「다른 화면에 다녀오거나 테마를 바꾸면 말없이 사라진다」). 편집표 `on_change`(`_fold_edits`)가 칸을 고친 회차 첫머리에 접고
    본문도 편집표 결과로 다시 접으며, 편집표는 늘 저장본 위에 초안을 얹어 그린다 — 다른 화면에 다녀와도 칸이 선다. 초안이
    있으면 화면 탭 점(어느 화면에서나 — 풍선 「저장하지 않은 입력 비가동」)·③ 탭 점·머리 변경 칩 「입력 비가동 저장 안 함」(Preference
    탭을 가리킴)·테마 · 새로고침 확인이 선다(`manual_downtime_draft_pending`). 머리 글은 칸 수를 싣지 않고 있나 없나만 말한다(2026-11-20
    사용자 결정 — 다른 미저장 칩과 한 꼴, 설계 규칙 UI-CON-02) — 머리가 바뀌는 회차는 첫 칸을 고친 회차와 마지막 칸을 되돌린 회차뿐이라
    칸마다 바뀌는 머리가 없다(편집표를 구역 회차로 좁힐 다음 차례의 전제). 떠나도 남으므로 탭 줄 떠나기 확인에는 넣지 않는다(설계 규칙 UI-STA-02). 초안이 있는
    동안 본 version 을 붙들고, 저장 아닌 회차에 저장본 version 이 달라졌으면 제 저장이 끊긴 것(`is_own_save`)이면 보이는 칸을
    빼고 남의 저장이면 초안을 버리고 그 수를 곁 경고 · 알림창으로 알린다(`MANUAL_DROPPED_MESSAGE`). 그렇게 초안이 있다가 없어진
    회차는 본 version 을 적은 뒤 앱 전체를 한 번 다시 돌려(`_settle_draft` 끝 `st.rerun(scope="app")` — 설비 편집본의
    `rerun_if_head_stale` 와 같은 까닭) 페이지보다 먼저 선 화면 탭 점 · 변경 칩 · ③ 탭 점을 그 회차에 걷는다(2026-11-19 E2E
    e3-D1 — 한 회차 늦게 걷혔다, 설계 규칙 UI-STA-02). 담은 알림은 다시 돈 회차가 한 번 그린다. 칸 수만 준 회차(제 저장이 보이는
    칸만 빼고 보이지 않는 칸이 남음)는 머리가 그대로라 다시 돌지 않고 성공 알림은 그 회차 알림 칸이 낸다. 조회기간 밖이 된 칸은
    초안에 남고 저장은 보이는 칸만이다. 「되돌리기」 는 초안과 편집표 위젯(`editor_state.discard_editor`)을 버린다. 저장은 보이는 범위(조회기간 달 × 보이는 공정)만 갈아 쓰고 성공하면 `clear_manual_downtime_cache()` 뒤 앱 범위
  `st.rerun()` 이다. 잠금(가정 설비 시나리오)이면 표·단추를 끈다. 저장 줄(`MANUAL_SAVE_ROW_KEY`)은 오른쪽 끝을 표 도구 막대
  자리로 비우고 표 앞 띄움이 없다 — 저장 줄 → 표 14px(2026-11-10 사용자 그림 메모 eq-pref). 제목 아래 열 · 빈칸 · 공용 줄은 두지 않는다 — 제목 풍선
  (`MANUAL_INTRO_HELP` + 지금 열 + `MANUAL_COLUMNS_HELP`)이고, 조회기간 밖 저장 칸은 있을 때만 공용 버전 줄 표지다.
    「되돌리기」 는 확인 없이 초안과 편집표 위젯을 한 번에 버린다. 지금 표에 보이지 않는 칸(조회기간 밖 · 표에 없는 공정)이 섞였으면 저장 줄 「되돌리기」 풍선 끝이 누르기 전에 그 수를 말한다(`MANUAL_REVERT_HIDDEN_HELP`). 남의 저장으로 버릴 때는 숨은 칸까지 모두 버린다 — 남이 그 칸을 바꿨는지 볼 길이 없는데 남기면 내 저장이 남의 저장을 덮는다. 버림 글은 「저장하지 않은 칸 n개(지금 표에 보이지 않는 m칸 포함)를 버렸습니다」 꼴로, 숨은 칸 수를 칸 수 바로 뒤에 붙인다(`MANUAL_HIDDEN_NOTE`).
  - 편집표 key 는 표가 출발한 version 을 든다(`manual_editor_key` — 제출 회차는 본 version, 그 밖은 그린 저장본 version, 9장
    「본 값과 보이는 칸」 — `editor_widget_key` 를 지난다). 남의 저장에 거부된 누름의 둘째 누름(`held_profile_conflict`) 회차는
    제출 회차여도 그린 저장본 version 이고 초안을 버린다 — 그 회차가 본 version 을 그 저장본으로 적는다. 바깥 상자 key
    `MANUAL_EDITOR_KEY` 는 그대로라 화면 확인 `equipment_preference` 가 그 칸으로 찾는다.
  - 저장은 `write_guard.save_once`(출발점 = 보이는 공정·달 + 0 아닌 칸 지문 `manual_downtime_digest`)로 하고 제 저장 짝을 그
    잠금 안에서 적는다 — 같은 입력의 꼬리 누름은 「바뀐 것이 없습니다」 가 아니라 첫 결과로 성공을 다시 알린다.
  - 편집 칸(저장 줄 · 알림 칸 · 편집표 — `_render_editor_scope`)은 이 회차 입력을 함수 인자로 받지 않는다 — 탭 본문이 회차마다 세션 칸
    `_EDITOR_INPUTS`(경로 · 설비 저장본 공정 · 달 · 공정 표시명 · 잠금 까닭)에 적고 편집 칸이 거기서 읽으며 저장본은 캐시로 다시 읽는다(공정
    목록 길이가 정해지지 않았다 — 9장 「구역 회차 규칙」 R3). 저장 줄 서식(스타일만 든 `st.html` — `toolbar_room_css`)은 탭 본문이 그 앞에서
    싣고, 편집 칸이 쓰는 이벤트 칸 자리는 알림 칸(`render_flash`) 하나다(저장본을 못 읽은 갈래는 빈 스타일 하나).
- `src/capa_simulation/components/cutoff_management.py` — 가용설비 현황 「가용설비 설정」 팝업(개편 전 `Preference` 탭)의 Cut-off
  편집표·저장·CSV 왕복과 빠진 공정 안내. 초안이 아니라 저장된 값을 돌려준다(Static 대비 일정은 그 값을 받지 않고 캐시
  경계에서 직접 읽는다). 스타일만 든 `st.html`·토스트를 쓰지 않는다(팝업 본문). 보기 설정은 제출 줄(「Cut-off 저장」 ·
  「설비 공정으로 채우기」) 끝 「표 보기 ▾」 팝오버이고(안에 폼 제출 「보기 적용」 — 2026-11-09 사용자 보드 T5) 그 줄 아래 표 도구
  막대 띄움과 편집표는 간격 없는 칸 하나다(저장 줄 → 표 38px — 막대 37px 위, 사용자 검수 g17).
- `src/capa_simulation/components/equipment_settings_dialog.py` — 가용설비 현황 사이드바 「가용설비 설정」 상자(2026-11-03 —
  전에는 제목 줄 끝 「설정」 단추, 상자 글 = 팝업 제목, `render_equipment_settings_box` — 설비 DB 를 못 읽은 회차에는 잠김)와 그
  팝업(묶음 머리 「공정별 Cut-off」 하나 — 나중 설정 자리, D14)의 열림 칸(`available_equipment_open_dialog`, 값 `settings`)·여는 콜백
  (`forget_page_dialogs()` 부터)·호스트(이벤트 칸 늘 한 자리). 저장·채우기 뒤에도 팝업을 열어 둔다(9장 「팝업과 콜백」 예외 —
  앱 범위 `st.rerun()` 이라 바깥 화면도 새 값이고 flash 가 누른 단추 아래에 선다). 닫으면 제출하지 않은 표 편집은 사라진다.
  - 저장은 초안 지문 대조다(`process_cutoff_fingerprint` → `ProcessCutoffConflict`) — 표 전체 교체라 옛 초안이 남의
    공정을 지운다. 원본 공정명 원장이라 편집표·「Cut-off 를 적지 않은 공정」 경고(팝업 안 자리 글 — 이름 목록)와 같은
    조건의 상태 알림(`EQ-12` — 가용설비 현황이 회차마다 `report_missing_cutoffs` 로 낸다)·`process_cutoff.csv` 는 원본이다.
- `src/capa_simulation/components/availability_gap_panel.py` — `Static 대비 일정` 의 `조회 결과` 하나(`가용대수 비교`·
  `분류별 내역`·`확보율 교차검증`)를 그린다. DB 는 페이지가 읽어 넘기고 계산은 `simulation_cache` 래퍼
  (`get_availability_sheet` 등)로 받아 고르기만 한다.
  - 칸 누름 → 근거 카드(`pick_gap_sheet_cell`)는 같은 칸 다시 누름이 유일한 닫기이고 세대(`GAP_SHEET_GENERATION_KEY`)를
    `layout.meta` 에 싣는다. 시트·근거 카드는 키 붙은 프래그먼트다(`tests/test_availability_sheet_panel.py`). 근거 카드 식 셋
    (Static 보유 + 대여 = 합 · GAP = 설비 일정 − Static · 설비 일정 기준 가용 = 보유 + 대여 — `_static_sum_line` · `_gap_line` ·
    `_schedule_available_line`)은 인수가 시트 칸 자릿수이고, 적힌 인수로 다시 셈한 글이 결과 글과 다르면 결과 앞 등호가
    「≈」 다(`formula_text.equals_mark` — 비교 시트 풍선과 같은 길, 인수가 「—」 여도 「≈」, 8장).
    GAP 식 줄의 부호 뜻(음수 = 기준정보(약속)가 설비 일정보다 많음 · 양수 = 설비 일정이 더 많음)은 늘 서는 설명 줄이 아니라 그 식 줄의 풍선(`GAP_SIGN_HELP`)이다.
  - 시트 아래 범례 글은 없다 — 칸 표지(파란 면 · 고른 칸 테두리와 굵은 글자 · GAP −/+ 글자색 · ⚠ · 「—」)의 뜻은 Guide
    「분류별 내역 — 9행 시트」 의 「시트 표지」 다(2026-11-20 사용자 답 — 규칙집 6-39 gap-sheet-legend, 공정 Capa 상세 「시트
    범례」 와 같은 꼴).
  - 호기 필터가 걸리면 Static·GAP 행은 「—」 다. 시트·호기 목록 CSV 와 공정명 불일치 문구는 원본이다. 시트 · 호기 목록
    「시트 엑셀」(시트 엑셀 넓히기 2 — 각 CSV 와 「내려받기 ▾」 메뉴 하나, 호기 목록은 목록 아래 제 메뉴)은 화면처럼 표시명이고
    호기 목록 숫자 꼴은 화면 `NumberColumn` 과 같은 자릿수 표(`_UNIT_DIGITS`)에서 나온다(`unit_list_workbook`).
  - 입력 비가동(`manual_downtime` — **필수 인자**, 페이지가 `load_manual_downtime` 으로 읽어 넘긴다)을 시트·그림·확보율
    교차검증의 설비 일정 기준 가용에서 뺀다(키 `availability_sheet_cache_key`·`securement_cross_check_cache_key` 의 끝 칸).
    시트 머리에 「입력 비가동 반영」, 근거 카드에 「입력 비가동 · Preference」 줄, 조회 달에 든 칸은 상태 알림 `EQ-23`(목록은 Alarm 줄
    표, 「그 화면으로」 는 Preference 탭 — 교차검증 위 줄에서 옮김). 호기 목록·호기 필터 시트에는 없다 — 호기 목록이
    조회 달에 입력 비가동이 든 범위를 보면 표지 「입력 비가동 · 이 목록에 없음」 + 풍선(`MANUAL_LIST_MARK` · `MANUAL_LIST_HELP`)을
    혼자 한 줄로 세우지 않고 아래 전환 줄 오른쪽 끝 칸(시트의 「내려받기 ▾」 자리 `row_end` — 호기 목록에서는 빈 칸)에 내용 폭
    작은 글로 둔다(E2E e4-1, 설계 규칙 UI-LAY-13 · UI-TXT-04). 분류별 내역의 다른 두 표지도 같은 꼴(짧은 표지 + 풍선)로 같은 칸
    앞쪽에 이 차례로 선다(2026-11-11 「남은 물음 11-11」 보드 D2 · 「다음 배포 물음 11-11」 보드 D2 뒤 ① (나)) — 한쪽에만 있는
    공정은 「한쪽 공정 · GAP 없음」(`ONE_SIDED_MARK`, 풍선은 까닭 `_one_sided_reason` + 「있는 쪽 값만 보입니다」 — Static 을 읽지
    못한 회차도 같은 표지에 그 까닭), 호기 필터는 「호기 필터」(`UNIT_FILTER_MARK`, 풍선은 고른 값 · 「호기 n개만 더합니다」 그 아래
    `UNIT_FILTER_HELP` — 고른 값은 풍선에서도 이름마다 막는다). 끝 칸(`GAP_ROW_END_KEY`)은 남은 폭을 채우되 제 글 한 줄 폭보다
    좁아지지 않고, 곁에 자리가 모자라면 칸째 다음 줄 오른쪽 끝으로 내려간다(`ROW_END_STYLE` — 값 글 `"push"` 와 같은 뜻 — 기본
    꼴이면 긴 글이 좁은 칸 안에서 여러 줄로 접힌다). 칸째 내려가므로 그 회차에는 시트의 「내려받기 ▾」 도 표지와 함께 둘째 줄이다
    — 표지 하나씩은 짧아 1600 · 1283 에서는 메뉴 곁 한 줄에 들고, 1100 은 표지가 선 시트 · 표지 둘 회차에 끝 칸째 내려간다(샘플
    관측) — 시트는 메뉴 곁 약 78px 에 「호기 필터」(약 84px)도 들지 못해 메뉴와 함께(카드가 받은 꼴), 호기 목록은 표지 둘(한쪽
    공정 + 호기 필터 · 호기 필터 + 입력 비가동)이 서면. 두 표지가 함께 서면 끝 칸 안 한 줄에 나란히 선다(1600 · 1283 은 전환 줄
    곁, 1100 은 내려간 둘째 줄). 두 표지 + 메뉴는 표본에서 재지 못한 계산값이다(138 + 14 + 83.9 + 14 + 100.5 = 350.4px — 표본의 한쪽
    공정은 설비 없는 쪽이라 호기 필터를 걸면 메뉴 없이 빈 결과). 줄 사이 1rem 은 이 서식을 그리는 분류별 내역
    회차의 전환 줄 전체에 걸린다 — 표지 없이 메뉴만 내려가는 좁은 창(820)도 14px 다(가용대수 비교는 서식을 그리지 않아 56px
    이지만 메뉴가 없어 820 에서도 한 줄 — 같은 보드 D2 뒤 ② (가) 그대로). 가용대수 비교의 한쪽 공정 까닭은 그림 대신 서는 빈 상태
    한 줄이라 그대로다.
  - 탭 머리에는 구획 제목 · 「확보율 교차검증」 제목을 두지 않고(안쪽 탭 이름 · 고른 전환 값과 같은 말 — UI-TXT-07) `조회 결과` ·
    `표시` 전환 단추는 라벨 줄을 걷는다(2026-11-09 상단 띠 재고). 두 전환의 뜻은 그 줄 끝 빈 캡션 풍선 하나(`RESULT_VIEW_HELP` ·
    `DETAIL_MODE_HELP`)이고 마지막 전환과 작은 간격의 한 칸이다(`_switch_group` — 전환끼리만 넓게, Main 머리 줄 풍선과 같은 간격).
    확보율 교차검증이면 그 풍선 첫 단락이 「맞대어 본 달」 값 · 범위 설명이다(`_cross_check_help` — 자리 캡션 없음, 사용자 보드 T2 의
    「표 제목 풍선」 — 이 보기에는 표 제목이 없어 바로 위 줄 끝 풍선이 받는다). 시트 내려받기는 시트 프래그먼트 밖 그 줄 오른쪽
    끝 칸의 「내려받기 ▾」 메뉴 하나(`render_sheet_downloads` — 「시트 CSV」 · 「시트 엑셀」, `table_toolbar.render_download_pair` —
    시트 엑셀 넓히기 2, 2026-11-10 답 Q2-7 꼴)이고 그 메뉴 단추는 곁 전환 단추와 같은 28px 다(메뉴 높이 한 곳
    `table_toolbar.DOWNLOAD_MENU_STYLE` — 시트를 볼 때만 줄이 높아지지 않게)(T3). 「시트 엑셀」 은 지금 화면 시트(공정 · 달 · 호기 필터 · 입력 비가동 반영)를 화면 서식째
    (`components/availability_sheet_workbook.py`) 내고, 맨 위 값 줄은 공정 · 시나리오(Static 세 행이 온 활성 시나리오 — 공정 Capa 상세 · 산출 결과 시트와 같은 머리 띠 위 줄
    `sheet_download.scenario_line`, 올라온 리비전이 없으면 뺀다) · 조회기간 · 설비 시나리오(머리 띠 꼬리 글 `remembered_equipment_suffix` — 없으면 알림 범위 이름) · 호기 필터(걸렸을
    때 — 세션 칸 글 그대로, `_sheet_heading`)다. 통은 조건 키(`GAP_SHEET_SCHEMA_VERSION` · 범위 지문 · 머리 글자 · 제목 세부 글 · 머리
    값)로 세션 칸 `GAP_SHEET_XLSX_MEMO_KEY` 에 기억한다 — 칸 누름 · 같은 조건 회차는 짓지 않는다(새 `st.cache_*` 없음). 일정 미정 · 사용기준
    밖은 Main 과 같은 상태 알림(`EQ-20` · `EQ-22` — `equipment_explorer.report_unit_notices`)이고, Static 값으로 채운 공정은 한쪽
    공정 알림 `EQ-06` 의 전문이 말한다(`CROSS_CHECK_FALLBACK_HELP`).
- `src/capa_simulation/components/required_shortening_panel.py` — `필요 단축 일정` 화면(조회 조건 패널 줄 `목표 확보율` — 화면 팝업
  호스트 `SHORTENING_DIALOG_HOST` 와 줄 `LEVEL_FIELD` 를 여기 두고 페이지가 세운다, 2차 보드 Q2-26 · 조건 카드 — 맨 위 `진척 비교`(그림
  메모 g03, 본문 프래그먼트는 기준선 목록이 카드에 세운 것과 다르면 앱 전체 회차로 올린다 — `_Plan.shown_baselines`
  · `_view_choices`) · 공정 칸은 이름 줄 + 적용한 값 한 줄 팝오버(`PROCESS_POPOVER_KEY` — 「Wafer Saw 외 2개」, 처음 고른 공정 ·
  둘 이상이면 풍선이 전체 목록 — 2026-11-09 사용자 검수 g03-2), 안이 공용 공정 팝업과 같은 고르기 판(`PROCESS_BOARD_KEY` —
  `process_field.mount_process_board`, 2026-11-20 사용자 결정 「여럿 고른 뒤 「적용」 한 번」: 타일 누름 · 「선택 해제」 는 서버
  0회차, 「적용」 은 트리거 하나 → 콜백 `_apply_processes` 가 회차 앞에서 세션 칸 `SHORTENING_PROCESS_KEY`(위젯 key 아님 — 적용한 값 ·
  고른 차례)와 공용 프로필(`_save_processes`)을 적어 앱 전체 회차 하나. 판 data `wholeIsAll: false` · `pickOrder`(차례만 바꾼 초안도
  「적용」) · `clearDraft`(「전체」 자리 단추가 판의 초안만 비움 — 다른 화면의 「선택 해제」 와 같은 일, 저장은 「적용」 하나, 누른 뒤
  초점은 찾기 칸 — 「적용」 으로 옮기면 누르고 있던 Enter 의 되풀이가 공용 설정을 쓴다) ·
  `clearLabel` 「선택 해제」. 찾기 칸에 글이 있을 때 Esc 는 글만 지움(판 JS 가 창 capture 단계에서 받아 팝오버가 닫히지 않음). 고르고
  적용하지 않은 동안 「적용」 만 켜짐 — UI-INP-04. 적용하지 않은 고름은 판(브라우저) 안이라 팝오버를 닫거나
  화면을 떠나면 사라진다 — 거르는 조건이라 잃는 입력이 없고 칸 글은 늘 적용한 값, 공용 공정 팝업이 열 때 고르다 만 판을 비우는 것과
  같은 꼴. 팝오버 몸통은 닫히면 판을 내리고(초점 · 초안 없음) 창 높이를 넘으면 안에서 굴린다), 상태 알림
  `RS-03` ~ `RS-05`(자리 표지 없음), KPI·`계획 · LOB 요약`·공정 카드·CSV 세 벌). 수요·달(Cut-off 빔 포함)·공용 조건 물러서기·계획 꺼내기는
  `components/shortening_source.py` 로 옮겼다(Space 필요 단축 보기와 한 길 — 세 세션 칸도 거기서 다시 내보낸다). 표시명·맞대지 못함·
  UPEH 가정 칸(머리 아래 알림 · 기준선 저장 거절)은 패널에 남는다. 표는 줄 이름 칸을 붙박고 달 칸을 74px 로 줄여 기준 창에
  14달을 담는다(g4-17). 호기 줄(호기별 단축 · 진척 비교)의 이름 칸은 넘치면 앞을 줄이고 끝(호기 번호)을 남긴다(`shortening_timeline.unit_name`
  · `UNIT_NAME_STYLE` — 남은 물음 보드 D6 (다), 전체 이름은 줄 풍선). 붙박인 이름 칸은 호기 줄 묶음 `.shk-units` 의 컨테이너 질의로 갈린다 —
  묶음 폭이 이름 칸 + 결과 칸 + 여백(진척 447px · 호기 341px)보다 좁으면 붙박지 않고 줄 전체가 같이 구른다(창 폭이 아니라 묶음
  폭이라 사이드바를 펴도 따라간다). 멈춘 회차 조건 카드는 표지 「공정 · 고를 수 없음」 한 줄이다(g4-22). 조건 카드 맨 위(진척 비교
  위)는 현재 일정 기준 전환(`shortening_basis_switch` — 멈춘 회차에도 같은 자리, 2026-11-20 보드 답 Q01 (가))이고, 호기 줄은
  「현재 MM.DD → 단축 MM.DD」 · 고르지 않은 기준의 일정 흐린 ○(`other_basis_dates`) · 남는 호기 「필요 MM.DD」 「남는 호기」 다.
  호기 줄 위에는 범례 글이 없고(빈 글 카드 포함) 요약 카드 넷은 라벨 · 값만이다 — 표지 · 카드의 뜻은 Guide 「단축 계획」 의
  「KPI 네 칸의 뜻」 · 「호기 줄 표지」 다(2026-11-20 사용자 요청 — 규칙집 6-39). 진척 비교도 같은 꼴이다(PRC-01 횡전개) — 두 줄
  카드의 호기 줄 위 범례 글이 없고 합계 칸에 무엇의 합인지 적는 설명 줄이 없다(뜻은 Guide 「진척 비교」 의 요약 · 카드).
  `.shk-kpi-note` 서식은 진척 비교 합계 칸의 뺀 몫 줄 · 기준선 칸 출처 줄(값)이 쓰므로 `_style` 에 남고 `.shk-units-legend` 는
  걷었다. 목표 % 는 본문에 값으로 남는다 — 카드마다 표 머리 「과부족 (목표 n%)」, 카드가 없으면 빈 결과 줄. 진척 비교 화면은
  두 줄 카드에 표가 없어 합계 칸 라벨 「단축 필요일수 합계 (목표 n%)」 가 그 자리다(`progress_summary_markup(level=)` — 반올림은
  CSV 목표 칸과 같은 `level_percent`, 2026-11-20 사용자 답 「나」 — 규칙집 6-39).
  맞대지 못한 공정 `RS-02`(「Static 가용 없음」 포함)와 Static 역산 상태 `RS-07`(`static_states_note`)은 한 표지에 싣는다(두
  화면 같은 지문). 진척 비교는 기준선과 같은 기준의 계획(`_Plan.plan_for`)과 견준다.
  공정 팝오버는 key 가 있어 「적용」 회차에도 열린 채 남고 판이 적용한 값으로 다시 선다 — 닫기는 바깥 누름 · 찾기 칸이 비었을 때의 Esc 이고, 상태 추적 팝오버로 닫지 않는다(여닫기마다 앱 전체 회차가 돌아 설계 규칙 UI-PRF-01 에 어긋난다).
- `src/capa_simulation/components/target_level_field.py` — 필요 단축 목표 확보율의 조회 조건 패널 줄(이름 줄 + 값 칸, 패널 둘째 페이지
  칸 `LEVEL_SLOT`)과 다섯 목표 라디오 + 직접 입력 칸 팝업 한 벌(`TargetLevelField`). Space 「필요 단축」 보기와 필요 단축 일정이 같은 부품 ·
  같은 다섯 값 · 같은 세션 저장(화면마다 세션 칸 하나 — 공용 프로필에 쓰지 않는다)으로 쓰고(검수 보드 p-target-form · 2차 보드 Q2-26), 팝업은
  그 화면 팝업 호스트가 연다(여는 콜백은 호스트만). **고르거나 넣은 값의 적용은 라디오 · 직접 입력 칸의 `on_change` 콜백(`_commit`)이다** —
  받을 수 있는 새 목표면 콜백이 세션에 적고 `DialogHost.close_to_app` 으로 닫으며 앱 전체를 돌려(콜백 안 `st.rerun()`) 팝업 본문이 그
  상호작용에 한 번 더 그려지지 않는다. 받을 수 없는 값(범위 밖 · 빈 칸)은 콜백이 적지 않아 팝업 회차가 칸 곁에 거부 글을 적는다(거부만
  팝업 회차). 판정은 한 함수(`_decided` — 라디오 먼저, 그다음 칸)라 두 칸이 한 상호작용에 함께 바뀌어도 콜백 차례와 상관없이 라디오가
  이기고, 콜백 없이 값이 달라진 회차는 본문이 같은 판정으로 적용한다(`DialogHost.finish`). 새로 읽는 위젯 값은 `SessionSlot` 이다. 직접 입력(2026-11-11 사용자 고칠 것 Q2-26)은
  판정 기준 기본 칸과 같은 걸음 · 꼴(1 · `%.0f`, 소수는 사사오입 정수 %)과 같은 받는 범위(`THRESHOLD_RANGE` 50 ~ 300%)이고, 범위 밖 ·
  빈 칸은 칸 바로 밑 거부 한 줄(`st.error` — 알림창 · 기록 없음)이다. 범위를 한참 넘는 값은 사사오입 전에 거른다(멈추지 않는다).
  숫자 칸의 − · + 단추와 지우기 ⊗(`ENTRY_HIDDEN_PARTS` — Streamlit `stNumberInput` 의 `data-testid` 셋)는 숨기고 Enter · 칸 떠남으로만
  적용한다(남은 물음 보드 Q226-stepper (나) — 단추가 있으면 한 걸음이 곧 확정이라 걸음마다 앱 전체가 돈다). ↑/↓ 키는 그대로 한 걸음 적용이고,
  ⊗ 없이도 글을 지우고 Enter 면 빈 칸 거부 한 줄이다. 숨김 서식(`entry_style`)은 그 칸 key 의 칸(`st-key-<key>`)으로만 좁혀 다른 숫자
  칸(판정 기준 · UPEH 가정 % 등)은 그대로이고, 팝업 본문이라 스타일만 든 `st.html` 대신 단위 글 캡션(`% 직접 입력`)에 싣는다
  (`tests/test_target_level_entry.py` 가 부품 이름이 깔린 Streamlit 에 있는지 · 그 이름을 거는 파일이 이 부품 하나인지 본다).
  숫자 칸은 늘 지금 목표, 라디오는 지금 목표가 다섯 가운데 하나일 때만 켜진다. 세션 칸 · 주소 인자 · 대기 칸도 같은 범위로
  읽는다(`target_level`).
- `src/capa_simulation/components/shortening_source.py` — 필요 단축 일정 화면과 Space 필요 단축 보기가 **같은 함수·같은 키·같은
  캐시 칸**으로 계획을 꺼내는 길(`load_shortening_demand`·`shortening_month_options`·`shortening_filter_profile_or_default`·
  `shortening_frames`·`load_official_shortening`·`ShorteningStop`). 캐시 데코레이터가 없고(경계는 `simulation_cache`), 아래 부름은
  모듈 속성으로 한다(시험이 센다). 공정 표시명을 읽지도 받지도 않는다 — 달 범위 멈춤 글은 원문으로 짓고 그 예외를
  `ShorteningStop.cause` 로 싣는다(필요 단축 일정 패널은 같은 예외로 표시명 글을 다시 짓고(`_named_stop`) Space 보기는 원본 공정명으로
  예시 행만 화면 꼴로 다시 짓는다(`_original_name_stop`)).
  `load_official_shortening(level=)` 은 화면의 지금 목표가 다섯 밖(직접 입력)이면 그 값 하나를 목표 하나 칸에서 받아
  더한다(`simulation_cache.load_required_shortening(level=)` — 두 화면이 같은 길). 현재 일정 기준은 세션 칸
  `SHORTENING_BASIS_KEY`(처음 Static — `current_basis` · `settle_basis`)이고 `load_official_shortening(basis=)` 이 계획 키 끝
  칸으로 싣는다. Static 이면 활성 시나리오의 `RQ_EQP_AVBL`(`static_availability_of` — 없으면 모든 공정 「Static 가용 없음」),
  설비 마스터면 계획에 Static 역산을 붙여 호기 줄 흐린 표지 몫으로 돌려준다(숫자 · 호기 · CSV 에는 들지 않는다).
- `src/capa_simulation/components/shortening_basis_switch.py` — 현재 일정 기준 전환 「Static | 설비 마스터」(필요 단축 일정
  조건 카드 맨 위 · Space 조건 카드 「색 기준」 밑, 같은 세션 칸 — 제약 시뮬레이션 모드 전환과 같은 꼴, 뜻은 줄 끝 ⓘ)과 그
  글자(`supply_label` — 「Static 역산 가용(환산)」 / 「설비 일정 기준 가용(환산)」, `other_mark_label` — 흐린 표지 이름).
- `src/capa_simulation/components/space_shortening_view.py` — Space 현황 「필요 단축」 보기의 그리기 — 사이드바 목표 줄 · 카드
  흐리게 칸 · 기준 달 줄, 맞대지 못한 공정 알림(`RS-02`), 못 읽음 마크·FAB 요약·층 보기 칸·누른 호기 상세, 링크 도착(`consume_layer_link` ·
  필터 밖 링크 공정 사건 알림 `report_arrival_filter` → `EQ-24`)과 상세 단추 이동
  (`switch_to_queued_shortening` — 강조 칸·목표 칸 둘만 적음). 공정 표시명을 읽지 않는다(원본 공정소분류 — 결정 D10). 계산
  멈춤 글(수요 멈춤 · 달 범위 멈춤)의 예시 행은 화면 꼴 「YY.MM 공정 양산구분」 이고 공정은 원본 이름이다(`labels=None` ·
  `example_rows=True` — 2026-11-11 다음 배포 물음 보드 「F7 뒤 ①」 (다), 달 범위는 공용 길이 실은 `cause` 로 다시 짓는다).
  FAB 요약 한 줄(`render_fab_layer_summary`)의 단축 대수는 모든 층 합이고, 괄호는 「도면 n · 비활성 층 m · 자리 없음 k」 다 — 「도면」 은 비활성 층 대수를 뺀 수이고 「비활성 층 m」 은 0 이 아닐 때만 선다.
  - 공정을 비우면 목표 미달 공정 전체다(모두 켬은 맞댄 공정 전부 — 비움과 다르다). 조건 셋은 공용 프로필(`0019`)이라 세션이
    비었을 때만 심고 기간은 `on_change`, 공정은 고르기 판 「적용」 콜백에서만 쓴다.
  - `계획 · LOB 요약` 은 HOME 과 같은 키(`build_home_simulation_cache_key`)로 캐시를 나누고 CSV 도 캐시에서 고른다.
    Wafer 계획은 HOME `Wafer 계획` 과 같은 셋째 원소(Dummy 계열 뺌 — 6장 「HOME 얹기」)다.
  - 머리·본문은 「본문 프래그먼트」다 — 기준선·판정 기준은 회차마다 다시 읽고 기준선 쓰기 표지를 보면
    `st.rerun(scope="app")` 한다(`tests/test_shortening_view_fragment.py`·`tests/fragment_browser.py`).
  - 계획은 `_Plan.official`(키와 한 묶음) 하나다. `_Plan.assumption` 은 조건 카드의 UPEH 가정이고 머리 아래 알림과
    기준선 저장 거절에만 쓴다(계획에 걸지 않는다).
  - 강조 공정(`shortening_board.SHORTENING_HIGHLIGHT_KEY`)은 두 보기(기본·진척 비교) 모두 카드 맨 앞이다(테두리·배지).
    공용 설정 공정 밖이면 「KPI·CSV 에 들지 않음」 을 적고, 맞대지 못한 공정이면 카드 대신 그 말이다. 카드 class 는
    그대로 `shk-card` 다.
- `src/capa_simulation/components/shortening_board.py` — 줄을 고른 회차에 한 번 그 카드로 굴린다(Components v2 `capa_shortening_card_reveal`
  `_CARD_REVEAL` — 고른 회차에만 부르고 `st.html` 예외를 늘리지 않는다). 필요 단축 일정의 공정 진척 보드(`st.dataframe` 한 줄 고르기 →
  그 카드 강조, 표 key 세대를 올려 고른 줄을 남기지 않는다)·카드 차례·기한 임박 날수(세션 값, 선택지 고정)·기한 임박/이행
  지연 상자·강조 공정 칸·카드의 상세 근거 링크(`st.page_link` + 주소 인자)·「도면에서 보기」(`space_link_params` 순수 +
  `render_space_link`).
  - 카드 상세 링크의 주소 숫자(첫 부족 달 · 당긴 호기 · 신규)는 카드마다 공정 × 월 표 · 호기 표를 거르지 않고 공정 전부를 한
    번에 낸다(`shortening_watch.detail_numbers` — 공정마다 낸 값과 같다, 표에 없는 공정은 (None, 0, 0)). 그 숫자는
    `remembered_detail_numbers` 가 (계획 키 `KeyedShorteningPlan.key` · 목표 · 기간)으로 세션에 한 벌 기억한다(`SessionSlot`
    `DETAIL_NUMBERS_KEY`) — 셋이 같은 회차(본문 프래그먼트 · 공정 고르기 · 보드 조작 · 진척 비교 칸)는 다시 내지 않는다. 두
    보기(일반 · 진척 비교)의 카드 링크가 그 숫자를 받고(`render_detail_link(numbers=)`) 주소는 그대로다.
  - 강조 공정 칸은 `(원본 공정명, 출처)` 튜플이다 — 공정 Capa 상세 이동(`detail`)·보드 줄 고르기(`board`)·Space 필요 단축 보기의
  「필요 단축 일정에서 이 공정 보기」(`space`)만 적는다(출처마다 배지 글이 있어야 `current_highlight` 가 받는다).
    공정 필터·공용 프로필(0019)·기준선(0021)에는 닿지 않는다(`tests/test_required_shortening_tab.py`).
- `src/capa_simulation/components/upeh_assumption_controls.py` — 두 화면 조건 카드 끝 「이 세션만」 UPEH 가정 묶음(% 칸
  80~150·1 단위·곧바로 반영, 「UPEH 적용 시작/끝」, 「100% 로」)과 배지·역산 한 줄·「이 값으로」. % 칸은 빈 칸 = 100%·범위
  밖 = 가까운 끝을 콜백(`_settle_percent`)이 칸에 다시 적고, 위젯에는 기본값·범위를 주지 않는다 — 1.63 은 빈 칸을 위젯
  기본값(안 주면 최소값)으로 확정하고 범위 밖 글은 확정하지 않은 채 쥐어 칸과 적용값이 갈렸다(2026-10-27 표적 E2E). 구간 선택지는
  `assumption_month_options`(조회기간 ∩ 이번 달 이후) 하나이고, 세 칸 모두 위젯 앞에서 `carry_shared_widget_value` 를
  부른다(`tests/test_upeh_assumption_controls.py` — 앱 전체로 페이지를 옮긴 첫 회차까지).
- `src/capa_simulation/components/preset_number_field.py` — 미리 정한 값 버튼(`st.pills`, `required=False`)과 늘 지금 값을
  보이는 직접 입력 숫자 칸을 **정본 한 칸**(위젯 아닌 세션 칸)으로 묶는다(제약 시뮬레이션 D10). 두 위젯 칸은 위젯 앞에서 매
  회차 정본에서 다시 서되 **다를 때만** 적고(같은 값을 적으면 `set_value` 가 회차마다 가서 치다 만 숫자를 덮는다), 콜백이 정본을
  적는다. 버튼 콜백은 숫자 칸 세대도 올려 칸을 **새 key** 로 다시 세운다 — 1.63 숫자 칸은 범위 밖 글(301)을 확정하지 않은 채
  쥐고 그동안 서버 값을 무시하므로, 같은 key 로는 버튼 값이 칸에 서지 않고 빨간 표시가 남는다. 칸에 치고 Enter 없이 버튼을
  누르면 칸 확정과 버튼 누름이 한 회차에 들어 두 콜백이 함께 도는데, **어느 차례든 버튼이 이긴다** — 숫자 칸 콜백은 자기 key 가
  지금 세대 key 와 다르면(버튼 콜백이 먼저 세대를 올렸으면) 적지 않는다(1.63 은 버튼 콜백이 먼저라 친 값이 덮었다, 2026-10-26
  E2E). **이미 켜진 버튼**을 눌러도 같다 — `required=True` 는 그 누름을 프런트가 삼켜 콜백이 없었으므로(친 값이 이겼다,
  2026-10-26 E2E) 풀 수 있게 두고, 풀린 `None` 은 「켜진 버튼 다시 누름」 으로 읽어 서버가 마지막으로 켠 버튼(`_lit_key` —
  맞춤 값이 되어도 남는다)으로 정본을 적는다. 맞춤 값은 버튼 칸이 `None` 이 아니라 **숨은 맞춤 버튼**(`CUSTOM_OPTION` — 버튼 줄
  끝, `[role="radiogroup"] > button:last-child` 를 CSS 로 숨김)이 켜진 꼴이다 — 그래야 풀린 `None` 이 늘 「바뀜」 으로 콜백에
  닿는다(맞춤 값을 `None` 으로 두면 사람 손 빠르기 0.15초 누름에서 칸 확정 회차가 먼저 버튼 칸을 `None` 으로 적고, 그 회차를
  받기 전의 브라우저가 켜진 버튼을 풀어 같은 `None` 을 보내 콜백이 없었다 — 2026-10-26 사본 앱). `None` 버튼(「HOME
  기준」)은 버튼 칸에 글자 표지(`NONE_OPTION`)로 든다. 그때 숫자 칸은 `fallback` 을 보이고(범위 밖이면 칸 끝으로 자른다 —
  위젯이 범위 밖 기본값을 받지 않는다. 기준 확보율 칸은 범위가 HOME 판정 기준 저장 범위와 같아 Preference 로 저장한 HOME 기본은
  잘리지 않고, 범위를 보기 전에 저장한 옛 기준만 잘린다) 같은 값을 다시 치면 콜백이 돌지 않는다 — 보일 값이 마땅치 않거나
  다른 입력을 따라 움직이는 칸(개조 일정 동시 상한)은 `none_placeholder` 를 줘 정본이 `None` 이면 칸을 비운다(어떤 수를 쳐도
  정본이 된다). `persist_state` 를 주지 않는다. 숫자 칸은 **적지 않은 회차에만** 지금
  값을 `value=` 로 싣는다 — 새 key 를 적은 회차가 보내기 전에 다음 누름에 끊기면 다음 회차는 같은 값이라 적지 않아 칸이
  `set_value` 없이 브라우저에 처음 닿고, 기본값이 최소값(50)이면 그 50 이 되돌아와 정본이 말없이 50 이 됐다(2026-10-27 E2E —
  켜진 버튼 빠른 두 번 누름 뒤 더블클릭). 적은 회차에는 싣지 않아 「기본값과 세션 API」 경고가 없다. 친 값은 칸이 보이는 소수
  자리(`number_format` — 안전 여유 `%.1f`)까지 반 올림으로 접는다 — 소수 칸이던 기준 확보율이 칸은 112.3 · 머리·판정 글·그래프는
  112.34% 로 갈렸다(2026-10-27 E2E). 반 올림은 브라우저 칸의 `toFixed` 와 같은 꼴(2진 값 그대로 — 112.25 → 112.3)이고 0.5 단위로 맞추지는 않는다. 정수
  칸(`step` · 최소값이 정수)의 정본도 반을 올린 정수다(108.5 → 109 — `round` 의 짝수 쪽이 아니다). **`decimal_entry`**(기준 확보율 ·
  제약 확보율 — 2026-11-01 사용자 결정)는 정본은 정수인 채 숫자 칸만 소수 칸(`float`, `%.0f`)으로 세운다 — 정수 칸은 브라우저가 친
  글을 `parseInt` 로, 서버가 `int()` 로 읽어 「109.5」 가 말없이 109 였다. 칸 범위(min · max)는 반올림 전에 칸이 막는다. 켜진 버튼
  주의 색(`tone="warning"`)은 1.63 pills 의 켜진 단추 `button[role="radio"][aria-checked="true"]`(`ACTIVE_PILL_SELECTOR` — 옛
  `stBaseButton-pillsActive` testid 는 그리지 않는다)에 걸고, 면색 위 글자는 `TEXT` 다.
- `src/capa_simulation/components/constraint_simulation_figures.py` — 제약 시뮬레이션의 월별 확보율 그래프(수 축 — 개조
  비가동 막대를 W/D 구간 날짜 비례로 놓는다, 표적 막대가 달 누름을 받는다)와 월별 계산표(`month_sheet_canvas` 엔진)를 계산
  결과에서 만드는 순수 함수. 기준이 HOME 이면 계산표 확보율 칸은 `ConstraintLabels.warning_targets` 로 세 단계 판정색, 직접 넣은
  기준은 두 단계(경고 경계가 없다 — 설계 규칙 UI-DAT-03 예외), 제약 제품 칸은 제약 목표 두 단계다(2026-11-07 g4-14). 부품 줄을
  고르면 계산표 「제약 제품 · 이름표」 제목은 `ConstraintLabels.part` → `title_row(label_part=)` 로 라벨 칸에 넘칠 때 부품 끝을
  남기고 앞을 줄인다(고르기의 형제 부품은 `ConstraintLabels.part_siblings` — 제품 전체 줄은 끝을 줄이는 지금 꼴, 8장 「합쳐
  보는 화면의 부품 이름표」). 곁에 적힌
  두 값의 차이는 `rate_delta_text` 이고 적힌 값으로 다시 빼면 어긋날 때만 「≈」 를 붙인다(g4-15). 새 색 토큰 없이 기존 토큰에 도형 `opacity` 를 준다(제약 기간 칠·고른 달 띠). 주의 색
  (`STATUS_WARNING`)은 면색이라 글자에 쓰지 않는다 — 오른쪽 끝 「제약 n%」 는 `TEXT`, 제약 제품 점은 `LINE` 테두리. 오른쪽
  끝 두 글(「기준 …」 · 「제약 n%」)은 같은 x 라, 그림 칸이 가장 낮을 때(`END_LABEL_MIN_PLOT_PX` — 범례 줄 수로 칸 높이가
  바뀐다) 두 선이 글 한 줄보다 가까우면 큰 값은 선 위·작은 값은 선 아래로 비킨다(`end_label_anchors` — 같으면 「제약」 이
  위, 2026-10-25 E2E 에서 7px 포개짐·한 글 숨음). 제약 소요가 1대 미만인데 올림으로 1대를 뗀 달(`minimum_unit`)은 고른 달
  2단계·계산표 필요 칸 풍선이 「최소 1대」 를 곁들이고, 확보율 쪽(2단계 회색 줄의 「확보율이 크게 나오는 까닭」·결과 상자·확보율
  칸 풍선·그래프 풍선)은 그 1대를 배정한 달(`minimum_rate` — 배정 1대)에만 곁들인다(4000% 같은 값의 까닭 — 개조한 전용을 더
  남긴 달의 큰 확보율이나 가용이 모자라 배정 0 인 달의 0% 는 그 까닭이 아니다). y 축은 제약 제품을
  뺀 선·기준·제약 목표로 잡고 제약 제품 점은 그 범위 폭만큼 위(`RATE_AXIS_STRETCH`)까지만 넣는다(`rate_axis` — 4031% 가 축을
  늘려 기존 선이 바닥에 눌렸다, 2026-10-25 E2E). 넘는 점은 위 끝 ▲(`cliponaxis` 끔)·풍선 「▲ 그래프 위 끝 넘음」, 카드 회색 줄이
  `CONSTRAINT_FIGURE_SCHEMA_VERSION` 을 올린다(2판 옵션 행으로 5, 신규 대기 행·막대로 6, 「신규 설비로」·「보유 제약 설비로」
  행을 채우는 차례로 세워 7, 그래프 풍선 「최소 1대」 로 8, y 축 상한·▲ 로 9, 묶음 신규 모듈 몫 「HB-07(HB-07B)」·「보유로
  제약 기간을 다 덮음」 풍선과 차이 「%」(퍼센트 포인트 기호 없음)·기준선을 판정 경계에 그어 10 — 2026-11-01 결정 B1 · B2 · N1, 계산표
  「신규 기여 시작」 풍선의 일반 설비 까닭을 호기마다 되짚고(2026-11-01 E2E) B1 증가마다로 뒤 증가부터 덮인 호기에 「27년 7월부터
  보유로 다 덮음」 을 적어 11 — 같은 날, 두 갈래 모두 배포 전이라 한 번 올림. 같은 날 리뷰 후속(「신규가 채움」 은 신규로 다 채운
  달만 · 제 몫으로 찬 달은 「이 호기 몫으로 다 참」 · B1 없이도 1대가 안 된 호기는 그 까닭)도 11 안이다). 보유 · 신규가
  걸리면(`splits_dedicated`) 계산표에 「들어오는 신규 설비」(공정 전체 — 그 달 W/D 구간에 기여를 시작하는 호기와 쓰임,
  `new_unit_fate`)·「늘어난 전용 대수」·「신규 설비로」·「보유 제약 설비로」(두 행은 `FILL_ORDER` 차례 — `ROW_IDS` 가 그
  상수에서 나온다)·「신규 대기」(개조) 행이 그 옵션이 걸릴 때만 서고, 배정 칸·표적 풍선에 `dedicated_split_text`(「전용
  10대 = 신규 3 · 보유 4 · 개조 3」 —
  `FILL_ORDER` 차례, 걸린 옵션의 몫만)가, 표적 풍선에 신규 대기가 붙는다. 신규 대기 막대는 개조 막대와 같은 아래 띠에 같은 주의
  색 빗금(`marker.pattern` — 새 색 토큰 없음)으로 서고 개조 막대가 채운 줄 자리를 잇는다. 걸리지 않으면 1판 행·글 그대로다.
  신규 대기 날짜 글은 `waiting_text` 한 벌이고, 기여 시작이 곧 그 달 W/D 첫날이라 대기가 0일인 붙인 몫도 글에서 빼지 않고 「대기 없음(W/D 첫날 기여 시작)」 으로 적는다.
- `src/capa_simulation/components/constraint_simulation_view.py` — 제약 시뮬레이션 본문 프래그먼트(`constraint_sim_view` —
  요약 넷 → 월별 확보율 그래프(온 폭) → 월별 계산표(온 폭) → 가용이 모자란 달. 「비중 배분 비교」 토글은 사이드바 카드 끝
  「견주기」 이고 프래그먼트는 그 세션 값을 읽는다(`proportional_on` — 2026-11-09 보드 C3). 고른 달 계산 카드와
  「이 조건의 개조 창」 카드는 걷었다(2026-11-08 그림 메모 g12) — 식은 계산표 칸 풍선, 창 날짜는 그래프 띠 막대 풍선, 신규 호기
  까닭은 계산표 「들어오는 신규 설비」 칸 풍선, 읽는 법은 Guide, 달 칸 누름은 그래프 띠와 계산표 열 테두리로 그 달을 짚는다.
  그래프 카드 머리 캡션(옅은 칠 = 제약 기간 · ▲)과 계산표 위 「첫 개조 비가동 · 첫 신규 대기 — 표 첫 달 앞에서 시작」 표지 줄도
  걷었다(2026-11-09 검수 g12-2) — 뜻은 두 카드 제목 풍선(`chart_help` — ▲ 만 · `sheet_help` — 표 앞 창 · 대기의 날짜 · 대수는
  계산표 제목 풍선 끝)과 Guide 다. 옅은 칠의 뜻은 계산표 머리 칠처럼 Guide 에만 있다(2026-11-09 보드 c-legend — 표와 같게).
  요약 「개조 대수」 회색 줄의 첫 비가동 날은 오늘보다 앞이면 뒤에 「(지남)」 이 붙는다(`first_downtime_text` — `CS-04` 와 같은
  「첫날 < 오늘」, 2026-11-09 보드 c-late-word).
  판정색은 기준이 HOME 이면 계산표 칸 · 그래프 기존 제품 점 · 기존 제품 요약 테두리가 같은 세 단계(`figures.general_status` —
  작은 결정 d11), 직접 넣은 기준은 두 단계. 아래는 걷기 전 꼴의 기록이다 — 비중 토글·그래프·계산표·고른 달 계산 다섯 단계·개조
  창·가용이 모자란 달 — 그 값은 필요가 아니라 전용 대수이고 넉 달
  이상이면 달 수만 적고 달마다 값은 key 붙은 「달마다 보기」 에 접는다)와 요약 넷. 보유 · 신규가 걸리면 2단계 회색 줄에
  전용의 구성, 3단계 본문에 개조 중 비가동과 신규 대기, 회색 줄 머리에 그 달 늘어난 전용의 갈림(`_growth_note`)과 대기 몫·이 달
  몫 신규의 대기 날짜·그 달 일반 설비가 된 신규, 개조 창 카드 머리에 「개조 없이 쓰는 전용」 한 줄(`free_units_line` — 늘어난
  전용을 모두 채우면 `FREE_ONLY_TEXT`), 개조 창 줄 아래 「신규 대기」 줄(`waiting_lines` — 대기 첫날이 오늘보다 앞이면
  `WAIT_LATE_SUFFIX`)·일반 설비가 된 신규 한 줄(`ordinary_line` — 대수는 남는 몫의 환산 합, 일부만 붙은 호기는 「C 남는
  0.50대」, 까닭 묶음마다 넷 넘으면 「외 n호기」)이 선다. 「개조 없이 쓰는 전용」 의 보유 몫은 출처와 크기를 적는다(`holdings_text` — 「입력
  4대」 · 「고른 호기 3대 · 입력 1대 · 보유 3.50대 · 27년 7월부터 2.50대」, 2026-11-01 결정 B3). 남은 보유가 남은 증가를 다
  덮어 실제로 붙지 않은 호기(`held_back_units` — 결정 B1, 증가마다. B1 없이 다시 돌려 몫을 받았을 호기가 있을 때)가 있으면
  카드에 한 줄이 선다(`new_stopped_line` — 첫
  증가부터면 `NEW_SKIPPED_TEXT`, 뒤 증가부터면 「27년 7월 증가부터는 … 신규 설비를 더 붙이지 않았습니다」). 일반 설비가 된
  신규의 까닭은 호기마다 결과로 되짚는 한 길이다(`ConstraintResult.ordinary_reason` → `figures.ordinary_reason_text` — 일반
  설비 줄 · 3단계 회색 줄 · 계산표 풍선이 같이 쓴다). B1 로 붙지 않은 호기(`held_back_units`)는 「보유 제약 설비로 제약 기간을
  다 덮어」(뒤 증가부터면 「27년 7월 증가부터 보유 제약 설비로 다 덮어」 — 카드 한 줄과 같은 달, `new_units_stopped_month`)이고,
  그 밖은 창 안 증가 없음(「개조 D일 안에 늘어날 전용이 없어」) · 나간 뒤 · 앞 차례 신규가 채움(신규로 다 채운 증가만 — 그 달
  붙은 몫이 모두 그 호기 것이면 「27년 7월 증가는 이 호기 몫으로 다 차」, `OrdinaryReason.own`) · 들어온 몫이 내림 1대가 안 됨 ·
  묶음 모듈이 아직 안 옴이다(멈춘 달부터의 증가도 그 달에 붙을 수 없던 까닭으로 든다 — B1 없이도 1대가 되지 않았을 몫 포함,
  2026-11-01 리뷰). 까닭이 다르면 `ordinary_line` 이 묶음마다
  「… 기존 제품 몫」 을 「 / 」 로 잇는다. 한 글로 모든 남는 몫에 「개조 30일 안에 늘어날 전용이 없어」 를 적으면 묶음의 일부
  모듈만 온 증가(0.5대 — 내림 0)에도 그 글이 섰다(2026-11-01 E2E). 묶음 신규의 모듈 몫은
  「HB-07(HB-07B)」(`NewUnitAssignment.label`)로 적는다. 달 누름은 두
  그림의 `on_select`
  **콜백**이 한 칸(`CONSTRAINT_MONTH_KEY`)에 적고 세대 한 칸을 두 그림이 나눠 써 마지막 누름이 이긴다. 콜백은 「눌러 고름」
  표지(`CONSTRAINT_MONTH_PICKED_KEY`)도 세운다 — 누르기 전에는 `settle_selected_month` 가 앱 전체 회차마다 기본 달(영향 시작
  → 기간 시작 → 첫 달)을 **다를 때만** 적어 조건이 바뀌면 그 조건의 기본 달로 다시 서고(기간 밖 달 계산이 남지 않게, 2026-10-25
  E2E), 누른 뒤에는 그 달이 보이는 동안 그대로다(보이는 달 밖이면 표지를 내리고 기본 달). 다섯 단계의 식(1단계
  「소요 = 기존 + 제약」·2단계 「소요 × % = 곱」·4단계 「가용 − 개조 중 − 신규 대기 − 배정 = 기존 가용」·5단계 「가용 ÷ 소요 =
  확보율」)은
  **적힌 수로 다시 셈해도 적힌 결과**가 나와야 한다 — 둘째 자리로 깎은 인수로 어긋나면 인수를 한 자리씩 더 적되(여섯째
  자리까지) 그 자릿수는 **카드에 한 벌**이다(`formula_text.shared_digits` — 서는 식이 함께 맞는 가장 적은 자릿수로 모든 식의
  인수를 적어 1·5단계 기존 소요가 「1.96」·「1.9637」 두 꼴로 보이지 않게, 2026-10-26 E2E #109). 함께 맞는 자릿수가 없을 때만
  식마다 고르고(`digits_within` → `consistent_digits`), 그래도 못 맞추면 둘째 자리로 적고 등호를 「≈」 로 둔다. 굵은 결과는 늘
  화면 자릿수다 — 그래서 자리를 늘린 카드에서는 굵은 수와 같은 값의 인수가 자릿수만 다르게 선다(1단계 「소요 1.96대 = 기존
  1.9637 + 0」, 3단계 「−0.46대」 와 4단계 「3.4567 − 0.4567」 — 한 벌은 식의 인수끼리다). 비가동(· 신규 대기)이 가용보다 많은 달 4단계는 「max(0, 가용 − 개조 중 − 신규 대기)」 로 0 이 되는 까닭을
  식에 적는다(#110) — 식의
  인수는 `formula_text` 로 짓는다(적힌 수로 검산, 8장). 계산표 풍선의 식은 「≈」 길이다. 그림은 세션 memo(4칸 —
  키는 계산 결과 값·화면 글자·고른 달·토글·세대·테마)다. 위 줄(그래프 카드 + 고른 달 계산 카드)은 가로 컨테이너 하나(3 : 2)이고
  줄이 `TOP_ROW_STACK_BELOW_PX`(900px)보다 좁으면 컨테이너 질의로 위아래로 쌓는다(`top_row_style` — 사이드바를 편 900px 창에서
  3 : 2 그대로면 그래프 그림 칸이 169px 로 줄어 달 누름이 어려웠다). 그래프는 카드 안 스크롤 상자 → 캔버스에 서고 캔버스는
  폭을 고정하지 않고 가장 좁은 폭만 건다(`chart_min_width_px` — 좌우 여백 + 달 수 × 세운 달 한 칸 `MONTH_SLOT_PX` 13px) —
  카드가 그보다 좁으면(390px 창) 상자가 가로로 스크롤한다(그림 칸이 199px 로 줄어 세운 달 눈금 30개가 포개졌다, 2026-10-25
  E2E). 눈금은 솎지 않는다 — 서버는 칸 폭을 모른다. 규칙은 위 줄 배치와 같은 스타일 칸(`top_row_style(달 수)`)이라 이벤트 칸은
  스타일만 든 `st.html` 넷(위 줄 배치 + 공정 Capa 상세와 같은 계산표 틀 셋) 그대로다.
- `src/capa_simulation/components/constraint_equipment_plan.py` — 제약 시뮬레이션 두 모드(제약 영향 · 개조 일정)가 함께 쓰는
  「설비 일정 확인 → 계획」 블록. `equipment_readiness`(설비 DB 오류면 None, 아니면 `dynamic_readiness` — 두 모드 모두 카드
  안에서 먼저 쓴다)와 `render_equipment_plan`(멈추는 갈래 — 설비 DB 오류 · 설비 일정이 서지 않음(풀이 주어는 `subject`) · 그
  모드의 앞 갈래 `before_plan` · 계획 계산 오류 「설비 일정을 계산하지 못했습니다」(두 DB 경로) · 계획에 공정 없음 — 마다 머리
  한 줄과 까닭을 그리고 None, `st.stop` 은 부르는 쪽). 계획은 공정 Capa 상세 ②~④ 와 같은 칸을 같은 키로 받고(목표는 키 맞춤용
  HOME 확보 기준), `new_unit_since` 를 주면 같은 키의 설비 일정 칸을 그 날로 거른 신규 호기도 같은 `try` 에서 받는다. 계산
  함수는 부를 때 `simulation_cache` 모듈에서 찾는다(페이지 시험이 그 속성을 바꾼다). 두 모드가 이 함수만 거치는지
  `tests/test_modification_schedule_page.py` 가, 멈추는 갈래 차례와 까닭 글(키 만들기 예외도 계산 오류 갈래)은
  `tests/test_constraint_equipment_plan.py` 가 본다. 제약 영향 모드의 공정 칸이 빈 회차의 기본 공정(`first_ready_process` —
  설비 일정이 서는 첫 공정, 설비 프레임은 한 번만 거른다)도 여기서 판정해 페이지가 `dynamic_readiness` 를 직접 부르지 않는다.
  두 모드가 글자까지 같게 적는 조건 카드 「이 세션만」 머리(`SESSION_ONLY_CAPTION`)와 머리 줄 꼴(`HeaderRenderer` — 멈춘 갈래의
  공정 · 배지뿐, 두 모드 모두 조건 줄 · 출처 띠를 두지 않는다 — 그림 메모 g12 · 2026-11-09 보드 c-schedule-head),
  입력 비가동 상태 알림 `CS-05`(`report_manual_downtime` · 글 `manual_downtime_note` — 2026-11-10 보드 Q-4), UPEH 가정 미적용
  상태 알림 `CS-06`(`report_upeh_not_applied` · 글 `upeh_not_applied_note` — 2차 보드 Q2-13)도 여기 한 벌이다.
  그 글도 `tests/test_constraint_equipment_plan.py` 가 못 박는다.
- `src/capa_simulation/components/modification_schedule_figures.py` — 「개조 일정」 모드의 월별 확보율 그래프(개조 전·뒤 · 기준선 ·
  올린 배치 기준선 · 차수 막대 — 제약 모드 그래프와 같은 수 축·W/D 날짜 비례 `day_position`)와 차수 줄·대안 셋 글을 계산 결과에서
  만드는 순수 함수. 확보율 % 값과 y 축 범위는 제약 모드 그래프의 `percent_or_none` · `axis_bounds` 를 가져다 쓴다(사본을 두지
  않는다). 개조 없이도 미달인 달은 옅은 부족색, 넣을 수 없는 달(시작 앞 · 기한 뒤)은 옅은 회색 도형 칠이다(새 색 토큰
  없음 — 안전 여유가 있으면 풍선이 「배치 기준(기준 +n%) 미달」). 기준선의 자리는 G 의 판정 경계다(8장). 낮출 폭은 양수
  「기준 n% 낮추기」(`relief_text` — 기한 칸 캡션과 대안 셋 셋째 줄이 같은 글, n 은 기준 확보율 칸에 칠 **정수 %**
  `ScheduleShortfall.relief_percent` — 적힌 만큼 낮추면 들어간다, 2026-11-01 사용자 결정으로 0.01% 올림을 대신한다. 「HOME 기준」 에
  월별 예외가 있으면 모든 달을 n% 낮추는 폭이라 칸에 한 값을 치면 들지 않을 수 있다 — 기한 칸 풍선 `DEADLINE_HELP` · Guide 가
  그 단서를 적는다), 0 까지 낮춰도 못 넣으면 까닭(짧은 창 · 시작보다
  앞선 상한 · 동시 상한 · 가용)을 적고, 탐색이 한도에 걸렸으면 「이 계산으로 찾은 범위」 한 줄(「적힌 만큼 낮추면 들어간다」 괄호는
  낮출 폭이 적혔을 때만 — 까닭만 적혔으면 낮출 폭이 없다). 차수 띠 높이는 겹친 차수 줄 수를 따른다(`_band_layout` — 줄마다
  `_LANE_PX` 30px, 한 줄이면 `_BAND_MIN_PX` 로 그림 340px 그대로, `_BAND_MAX_LANES` 줄에서 멈춤 — 본 그림 칸은 그대로이고 그림이
  길어진다. 고정 비율 띠는 세 줄에서 막대가 10px 라 글이 늘 숨었다). 줄 높이는 앱 첫 글꼴 Noto Sans KR 지표의 글 상자(11px 글에
  16px — 라틴 글꼴이면 12px)와 그림 칸의 자동 여백 손실(범례 줄 · 1280 창의 세운 달 눈금)을 넣고도 「N대」 가 드는 두께다 — 26px 은
  띠가 두 줄 이상이면 1280 · 1500 · 1920 모두 막대 18 ~ 20px 라 글이 하나도 서지 않았다(2026-11-02 사용자 결정 A1, 시험
  `tests/test_modification_schedule_page.py` 가 그 지표로 잰다). 차수 막대 글(「N대」)은 `uniformtext` 하한
  (`_BAR_TEXT_MIN_PX`) 아래로 줄이지 않고 숨긴다(대수는 막대 풍선 · 차수 목록에 늘 있다). 그림 모양을 바꾸면
  `SCHEDULE_FIGURE_SCHEMA_VERSION` 을 올린다.
- `src/capa_simulation/components/modification_schedule_view.py` — 「개조 일정」 모드 한 회차 — 조건 카드 맨 위 모드 전환
  (`render_mode_switch` — 2026-11-08 그림 메모 g12, 숨긴 라벨의 뜻은 같은 줄 끝 ⓘ `MODE_SWITCH_HELP` — 2026-11-10 보드 Q-8,
  `ScheduleModeContext.card` · `process`), 조건 카드(대상 / 이 세션만 / 개조 · 일정 · 기준 묶음, 버튼 + 직접 입력은 `preset_number_field`), 설비
  일정 확인 · 멈춘 자리 · 계획(제약 모드와 같은 함수 `constraint_equipment_plan.render_equipment_plan` — 입력은 페이지가 넘긴
  `ScheduleModeContext.source`), 계산, 본문(요약 넷 · 대안 셋 · 그래프 · 차수 목록 — 머리 줄은 멈춘 갈래뿐이고 조건 줄 · 출처
  띠는 두지 않는다, 2026-11-09 보드 c-schedule-head. 입력 비가동은 제약 영향 모드와 같은 상태 알림 `CS-05`, UPEH 가정 미적용은
  페이지가 모드 분기 앞에서 내는 `CS-06`, 「아직 일정에 넣지
  않은 개조만」 은 「개조 대수」 칸 풍선, 「저장하지 않음」 은 조건 카드 「이 세션만」 표지 풍선). 기한 상자는 고른 시작 이후인 달만 내고(바뀌어 빠지면 「없음」), 동시 상한 「없음」 이면 숫자 칸이
  빈다. 요약 셋째 칸은 「개조 달 최저 여유」(값 = 기준 대비 %, 반올림으로 든 달은 0.0% — 캡션 = 그 달 · 확보율 — 6장). 결과·그림은 세션 칸 LRU(4칸 — 조건
  값·테마 키)다(Streamlit 캐시가 아니다 — 결과 모양을 바꾸면 `_RESULT_SCHEMA_VERSION` 을 올린다). 프래그먼트가 없다 — 본문에
  카드 밖 조작 위젯이 없다. 요약 첫째 칸 「개조 완료」 는 다 넣지 못하면 값 「넣은 / 넣을 대수」 뿐이다 — 기한 · 조회기간 끝까지 넣을
  수 있다는 뜻은 칸 풍선이고 바로 아래 대안 카드 첫 줄이 날짜와 함께 적는다(2026-11-20 갈래 판정 — 규칙집 6-39 ms-kpi-notes,
  UI-TXT-07). 요약 넷째 칸 「기한」 풍선(`DEADLINE_HELP`)은 칸이 실제로 적는 것만
  말한다 — 「못 맞춤」 은 기한을 골랐을 때만, 낮출 폭은 기준을 낮춰 다 들어갈 때만 캡션에 붙고 0% 까지 낮춰도 못 넣으면 까닭은 대안
  셋 카드가 적는다. 그래프 띠 · 칠의 뜻(범례 — 아래 띠 · 옅은 빨강 칠 · 옅은 회색 칠)은 제목 아래 줄이 아니라 Guide 다(2차 보드
  Q2-14 — 제약 영향 그래프 · 계산표와 같은 꼴, 막대 좌표의 읽는 법은 제목 풍선 `CHART_HELP`).
  조건 카드의 버튼 값은 개조 기간 15 · 30 · 45 · 60 · 90일(제약 모드 `MOD_DAY_PRESETS` 와 같음) · 동시 상한 없음 · 1 ~ 5대(`CONCURRENT_PRESETS`) · 안전 여유 0 · 1 · 2 · 3 · 5%(`MARGIN_PRESETS`)다. 직접 입력은 동시 상한 1 ~ 500대 · 안전 여유 0 ~ 30% 0.5 단위다(`services/modification_schedule.CONCURRENT_RANGE` · `MARGIN_RANGE`). 시작 상자는 「내일」 과 W/D 첫날이 내일보다 뒤인 달만 낸다(Cut-off 를 모르면 모든 달 — `start_options`).
- `src/capa_simulation/components/shortening_progress_panel.py` — 필요 단축 일정 진척 비교의 기준선 고르기·저장·지우기와
  요약·두 줄 카드(`required_shortening_panel` 이 부른다).
  - 「비교 안 함」 은 센티널 `NO_COMPARISON` 이다(pop 금지). 보던 기준선이 목록에서 사라진 회차에 「비교 안 함」 으로 되적으며 사건 알림
    `RS-06` 을 담는다(`_report_gone_baseline` — 앞 앱 전체 회차가 상자에 세운 id → (이름, 라벨) 칸 `_COMPARE_NAMES_KEY` 에 있던 것만이고,
    이 세션이 지운 기준선은 지우기 콜백이 먼저 되적거나 옛 화면 두 번째 누름이면 그 칸 · 지우기를 끝낸 표지로 거른다. 목록을 못 읽은
    회차(`read_baseline_options` 의 읽음 거짓)는 알리지 않는다 — 남은 물음 보드 D4 (나)). 저장 성공 때 이름 칸·폼·팝오버 key 세대를 함께 올리고
    콜백은 그린 회차의 세대가 다르면 쓰지 않는다(빠른 두 번 누름). 샘플·미저장 시나리오 편집은 저장을 거절한다.
  - 쓰기에 성공한 콜백은 표지를 남기고 `consume_baseline_write` 가 거둔다. 카드는 달 축 하나를 같이 쓴다. 확보 시점이 없는 줄(◌)의
    오른쪽 글 · 풍선은 추가N 이면 「신규」, Static 기준의 남는 호기(확보 시점 없이 당긴 「단축」 줄)면 본문 호기 줄과 같은 「남는 호기」 다
    (`_lane_text` · `_detail` — 설계 규칙 UI-CON-02).
  - 「기준 바뀜」(결과 보드 여쭘-4 a — 남는 호기 ↔ 날짜 호기)은 카드 배지 · 요약 「호기 변동」 의 「기준 바뀜 n」(있을 때만)이고, 합계 칸에
    「필요 시점 지남」 과 같은 꼴의 몫 줄 「기준 바뀜 n대(현재 n일) 빼고 견줌」 을 단다(합계에서 빠진 몫 — UI-DAT-07). 배지는 `TEXT_MUTED`,
    현재 줄은 좋고 나쁨을 말하지 않는 `TEXT` 다. 까닭은 줄 풍선(과거 · 현재 두 시점)과 Guide 다 — 카드 위 표지 줄은 더하지 않았다.
    공정 카드 머리(「과거 n일 → 현재 n일」 · 증감)도 같은 셈이라 두 상태를 빼고, 그 공정의 몫은 증감 글(`.shk-prog-delta`)의 풍선이다 —
    합계 칸 몫 줄과 같은 글 「필요 시점 지난 n대(현재 n일) · 기준 바뀜 n대(현재 n일) 빼고 견줌」(있는 것만 — 한 함수
    `_withheld_shares`), 없으면 풍선 없음. 화면 글은 늘지 않고, 그런 호기만 있는 공정의 「변동 없음」 도 같은 풍선이다(2026-11-21
    확인 보드 q-blank-head b — UI-DAT-07 · UI-CON-03).
  - 합계 칸 라벨은 「단축 필요일수 합계 (목표 n%)」 — 고른 목표(`level`)를 값으로 싣는 진척 비교 본문의 목표 % 자리다(비교 안 함
    화면 카드 표 머리 「과부족 (목표 n%)」 와 같은 꼴, 2026-11-20 사용자 답 「나」 — 규칙집 6-39). 무엇의 합인지는 Guide 「진척 비교」.
    괄호는 한 덩이(`.shk-prog-target`)이고 합계 칸이 제 폭을 재는 컨테이너(`shk-prog-total`)라, 칸 안쪽 폭이 480px 보다 좁으면
    괄호만 이름 아래 줄로 내려간다 — 줄지 않는 이름 칸(`flex:none`)이 한 줄 라벨 폭만큼 넓어져 막대가 짧아지고 긴 증감 글이 칸
    밖으로 나가던 것을 막는다(1600 창은 한 줄, 1366 · 1280 창은 두 줄 — 세 칸이 한 줄이면 칸 높이는 그대로, 2026-11-21 갈래 판정 ·
    UI-ACC-02).
- `src/capa_simulation/components/shortening_cumulative.py` — 필요 단축 일정 「누적 진척」 머리 한 줄 띠(키 붙은 프래그먼트
  `STRIP_FRAGMENT_KEY` — 작은 꺾은선(data URL 그림 — `st.html` 은 인라인 SVG 를 걷는다) · 지금 일수 · 지난 기록 대비 · 첫 기록 →
  목표 막대 · 남은 일수 · 「주차별」. 펴면 Plotly 꺾은선 + 목표선 — 늘어난 주 ▲, 편 상태는 세션 칸 `WEEKS_OPEN_KEY`. 편 회차에만
  넣기 스냅숏(설비 `0037`)을 읽어 오르내린 주의 까닭 꼬리표를 단다 — 아래 `shortening_cumulative_tags.py` · 「누적 진척」 절)와 사이드바
  「누적 진척 설정」 상자 · 팝업(그 화면 호스트가 연다 — 기록 표 · 주차 / 단축 필요일수 / 저장자 · 「기록 저장」 · 「이번 주 값
  넣기」 · 「기록 지우기」, 최종 목표 일수 / 주차 · 「목표 저장」 · 「목표 지우기」). 팝업 칸은 세대 key 라(`widget_generation`)
  주차를 바꾸거나 넣기 · 저장하면 그 세대의 기본값(저장값 · 넣은 값)으로 새로 선다 — 세션 대입으로 칸을 채우지 않는다. 겹친 저장은
  그 세대 칸이 처음 본 그 주 값 · 목표 version 과 저장소가 대조한다(`ProgressLogConflictError` · `ProfileVersionConflict` → 곁 +
  알림창). 지우기도 그 본 값을 넘기고(누른 회차에 새로 읽은 값이 아니다 — 본 값이 없던 주를 남이 넣었으면 거절) 「바뀐 것이 없음」
  도 저장소의 돌려준 값으로 가른다(칸이 본 값과 같아도 그 사이 남이 고쳤으면 겹친 저장). 화면 합계가 일수 칸 위끝
  (`PROGRESS_DAYS_MAX`)을 넘으면 「이번 주 값 넣기」 는 잠기고 풍선이 까닭을 말한다(남은 넣은 값도 칸에 세우지 않는다). 띠 줄은
  `wrap=False` 라 「주차별」 은 늘 첫 줄 오른쪽이고, 좁으면 띠 안쪽이 먼저 줄인다 — 목표 칸이 좁으면 「첫 기록 … →」 글을 숨기고
  (컨테이너 질의), 목표 주차 지남은 남은 일수 아래 작은 줄이다. 성공은 알림창 하나이고 앱 전체 `st.rerun()` 이라 팝업은 열린 채 띠가 새 값으로 선다. 등급은 기록
  `shortening.progress_log`(실무자부터) · 목표 `shortening.progress_goal`(관리자부터)이고 그 아래는 값만 본다. 「이번 주 값 넣기」 는
  그 화면 합계와 함께 호기 표 스냅숏을 세션 칸(`_FILL_SNAPSHOT` — (주차, `ProgressSnapshotDraft`))에 떠 두고 그 주 「기록 저장」 이
  저장소에 넘긴다(칸을 고쳐 적어도 남김 — 그 차이는 까닭 「손 고침」). 다른 주를 고르거나 저장 · 지우기 · 팝업 다시 열기는 넣은
  값과 함께 걷는다(`_forget_fill`). 본문이 회차마다 적는 `ScreenTotal` 은 고른 목표의 계획 호기 표를 참조로만 든다(잠긴 표 —
  옮겨 담지 않고 넣기를 누를 때만 `snapshot_draft` 가 범위 행을 새 표로 뜬다).
  기록이 없으면 띠는 점선 표지 「기록 없음」 이고 「주차별」 은 잠겨 까닭 풍선이 서며, 목표가 없으면 「최종 목표 미지정」, 마지막 기록이 목표 일수 이하이면 「목표 도달」 이다. 「이번 주 값 넣기」 는 기준선을 남길 수 없는 화면(샘플 fleet · 공식 발행 쌍이 아닌 설비 · 미저장 시나리오 편집 · UPEH 가정 — 기준선 저장과 같은 거절 `total.refusal`, `_fill_locked`)에서도 잠기고 풍선이 까닭을 말한다 — 기록도 모두가 보는 공용 값이라 기준선과 같은 규칙이고, 손으로 적는 기록은 그대로 된다. 「기록 지우기」(`data_progress_log_delete`)는 단축 기준선 지우기처럼 Admin 「접속 · 작업 기록」 요약의 「삭제」 칸에 들고, 지울 것이 없었던 지우기(`deleted` 거짓)와 지우지 못한 줄(겹친 저장 거절 등 실패 · 등급 거부)은 세지 않는다(`audit_log_view._DELETE_EVENTS`).
- `src/capa_simulation/components/shortening_cumulative_tags.py` — 누적 진척 「주차별」 까닭 꼬리표의 자리(2026-11-20 · 21 보드 답
  중간-1 「점 곁 곧은 꼬리표」 — 보드 시안 원고(저장소 밖 opt_point)의 자리 규칙). 꼬리표는 그 주 점 바로 위(오름) · 아래(내림)에 곧은 짧은
  지시선으로 붙고(주 간격 그대로) 첫 줄 「▲ +n일」 · 「▼ −n일」 + 항목 둘까지다. 5일(`THRESHOLD_DAYS`) 이상 오르내린 주만,
  오름 먼저 → 큰 변동 → 최근 주 차례로 다섯(`MAX_TAGS`)까지 놓고, 막히면 항목 하나 → 대수 뗀 항목 하나 → 한 단 바깥(곧은 지시선)
  → 같은 쪽 이웃 하나를 고쳐 놓기 → 숨김(표지 · 풍선만) 차례다. 피할 것은 꺾은선 · 남은 길 점선 · 점 표지 · 끝 값 글 · 목표선 띠
  (±`GOAL_CLEAR_PX`) · 목표 글 · 근거 없는 주의 「+n일」 글이다. **판정은 판정 그림 칸**(`NARROW_PLOT_WIDTH_PX` 450px — 창 600 ·
  사이드바 접힘의 그림 칸 어림)에서 하고 결정(줄 · 맞춤 · 단)을 데이터 자리 + 픽셀 띄움(annotation `xshift` · `yshift`)으로 옮겨
  어느 폭에서나 같은 자리다 — 꼬리표는 픽셀 고정 크기이고 주 간격은 폭에 비례해 판정 칸 이상의 넓은 칸에서도 겹치지 않는다
  (`overlaps` 로 넓은 칸에서 다시 잼 — `tests/test_shortening_cumulative_tags.py`). 그림 칸이 판정 칸보다 좁으면(사이드바를 편 창
  약 900px 아래 — 창 820 에서 약 370px) 겹침 판정 밖이고 글 폭 어림의 여유 안에서만 맞는다(`docs/TODO.md` 2장 「한 판 뒤 볼 것」 —
  판정 칸을 줄이면 넓은 창의 꼬리표도 준다). 세로축(`value_range`)은 목표(없으면 가장 낮은 기록) 아래부터이고
  위 세 줄 · 아래 두 줄 꼬리표 자리를 둔다. 0 아래로는 내려가지 않되, 목표가 0일 가까이라 0 에서 잘리면 목표 이름(선 아래) 자리
  (`GOAL_LABEL_ROOM_PX`)만큼만 0 아래로 내리고 그 칸에는 눈금을 두지 않는다(`value_ticks` — 이름이 가로축 눈금 글 위로 빠지지 않게).
  그림 높이 · 여백은 고정(340px — 「주차별」 을 편 때만 서는 그림)이라 세로 픽셀이 맞는다.
  글 폭은 어림(한글 1em · 그 밖 0.58em)이다. Streamlit 을 모르는 순수 계산이다.
- `src/capa_simulation/components/shortening_timeline.py` — 필요 단축 일정 타임라인의 달 축·위치·격자선·날짜 글자
  (`month_day`, 올해가 아니면 `YY.MM.DD`)와 호기 이름 칸(`unit_name` · `UNIT_NAME_STYLE` — 칸은 오른쪽에서 왼쪽으로 흘려 넘친 왼쪽
  끝에 말줄임, 이름은 `dir="ltr"` 한 덩이라 끝(호기 번호)이 남는다 — 남은 물음 보드 D6 (다))을 공정 카드와 진척
  비교(`timeline_months_covering`)가 함께 쓴다.
- `src/capa_simulation/components/availability_gap_figure.py` — Static 대 설비 일정 기준 월별 비교 Figure(환산 축,
  입력은 시트의 `SheetView`). 그림은 비교, 분해는 시트가 맡고 GAP 글자·색은 시트와 같은 함수(`gap_text_color`)다.
- `src/capa_simulation/components/plotly_layout.py` — 제목 주석·외곽 테두리·분기 경계·고정 행과 `hover_chart_config`·
  `static_chart_config` 등 Figure 공통 유틸리티.
  - 도형·주석은 `append_layout_items` 로 모아 Figure 를 돌려주는 쪽이 `flush_layout_items` 를 한 번 부른다(빠뜨리면
    테두리·라벨이 사라진다, `tests/test_plotly_layout.py`). flush·`figure_from_spec` 의 빠른 경로는 비공개 `_validate`
    라 `plotly>=5.24,<7` 에 기댄다(`tests/test_plotly_fast_path.py`).
  - 표 칸 글자를 표 밖에서 그리는 도우미 — `table_text_layer`(`TableText` 벌마다 글자 trace 와 숨긴 축. 넘칠 수 있는
    글자(`table_text_max_width_px`)만 그 열을 덮는 축 `xaxis2`… 에 얹어 `go.Table` 처럼 열 경계 ±1px 에서 자른다.
    자르는 축이 있으면 `plot_bgcolor` 는 투명이다 — 겹치는 축 바탕이 `layer: below` 도형을 덮는다), `table_text_y`
    (마크업 칸 기준선 = cellPad + 1.08em, 맑은 고딕 어센트), `table_header_band`. `figure_from_spec` 빠른 경로는
    table·scatter trace 와 번호 붙은 축을 받는다(`tests/test_table_text_layer.py`).
- `src/capa_simulation/components/home_figures.py`, `home_figure_common.py`, `home_lob_figures.py`,
  `home_plan_detail_figures.py`, `home_key_process_figures.py`, `home_bottleneck_figures.py`, `home_rendering.py`,
  `home_dimensions.py` — HOME Figure 가족 넷·공통 조각·캐시와 렌더링·픽셀 치수.
  - `home_figures.py` 는 코드 없는 import 파사드다(새 공개 이름은 `__all__`·재수출을 같이, `capacity_status` 는
    `services/securement_threshold.py` 의 것).
  - 캐시는 세션 칸 → 공용 저장소, 묶음 넷이다. 묶음 키는 `home_rendering` 의존 표가 정본이라 조건을 더하면
    `tests/test_home_figure_cache.py` 의 `EXPECTED_DEPENDENTS` 도 고친다(`tests/test_home_figure_cache_equivalence.py`·
    `tests/test_home_settings_kept_figures.py`). 그림 모양을 바꾸면 `HOME_FIGURE_SCHEMA_VERSION` 을 올린다.
  - 계획 세부수량은 `go.Table` 없이 면색 도형 + 글자 trace(data[0] 머리글, data[1] 값, 그 뒤 자르는 trace, 끝의 전체 이름 풍선 표적 막대)다. 긴
    제품명·거래선은 끝을 말줄임으로 줄이고(`_fit_label`) 넘칠 수 있는 칸은 전체 이름 풍선(끝의 표적 막대 `_label_hover_bar`)이며, 어림을 넘긴 글자만 제 칸
    경계에서 잘린다. 머리글 띠 도형은 `plotly_layout.table_header_band` 하나다. 부품(`CUSTOM`)은 칸이 아니라 제품 칸 글
    (`part_merged_columns` 이름표)이고 띠 · 굵은 선도 이름표 단위다 — 제품 칸 줄임은 부품을 남기는 `_fit_part_label` 이고,
    부품 이름표만 잰 글꼴 폭(`home_figure_common._table_label_width_units` — 이 환경 Chrome 이 그리는 글꼴 셋의 가장 넓은 폭)으로
    맞춘다(반각 0.6 은 대문자 · 밑줄 이름표를 좁게 잡아 기본 폭 제품 칸 경계에서 잘렸다). 접힌 이름은 지금 모형 그대로다.
    가른 부품이 있어도 제품 칸을 넓히지 않는다 — 네 구획이 구분 컬럼 하나(`DASHBOARD_LABEL_COLUMN_WIDTH_PX`)를 같이 써서
    제품 칸을 넓히면 네 구획 이름 칸이 함께 넓어지고 오른쪽 달 칸이 그만큼 덜 보인다. 그래서 분류 칸 그림은 폭을 싣지 않고
    기본 보기 견본도 「… (DEMO_CUSTOM_A)」(온전한 이름은 풍선)다(2026-11-24 그림 보드 4 답 q7-shared-col (나) — 보드 3
    q7-narrow-label (다) 의 넓힘을 걷음).
  - 구획 간격은 두 값이다(2026-11-02 사용자 요청) — 제목 글줄 → 시트 `tokens.SECTION_TITLE_SHEET_GAP_PX`, 앞 시트 →
    다음 제목 글줄 `tokens.SECTION_GAP_PX`. 계획 세부수량 · 주요공정 · 상세 B/N 제목 줄과 월 칸 짝 빈 줄은 띠
    (`home_dimensions.DASHBOARD_TITLE_BAND_PX` = 구획 사이 + 제목 글줄 `DASHBOARD_TITLE_LINE_PX` + 제목→시트, 위 · 아래 안쪽
    여백)이고 두 캔버스 gap 은 0 이다. `Capa LOB 현황` 은 글줄 높이 줄 + 상자 gap(`DASHBOARD_PANEL_TITLE_GAP_PX` = 제목→시트
    − 스크롤바, 지금 0) + 라벨 캔버스 위 여백(스크롤바 높이)이라 제목→시트는 스크롤바보다 좁힐 수 없다. 제목 줄 문단(`p`)은
    `dashboard_title_row_style` 이 flex 로 둬 본문 글줄을 걷는다(안 걷으면 글 아래가 4.4px 더 빈다). 「적용하지 못한 달」
    은 제목 줄 밑에 서지 않는다(상태 알림 `HM-04` — `home_preference.render_lob_title_row`). 그림 여백은 그대로라
    `HOME_FIGURE_SCHEMA_VERSION` 은 올리지 않았다(`tests/test_home_page.py` 의 간격 시험).
  - 제목 줄 끝 표지(`render_section_title_row(mark=)` — 「상세 B/N 공정」 의 「계산 밖 n공정 ⓘ」)는 그 줄의 자식이라 두 캔버스의 짝 차례 ·
    띠 높이가 그대로다. `dashboard_title_row_style` 이 표지 칸을 내용 폭에 묶고(`flex: none` — 구분 칸의 `min-width:0` 이 ⓘ 를 글 밑으로
    떨어뜨리지 않게) 글을 한 줄로 두며 캡션 문단 여백을 0 으로 걷어 제목과 눈높이를 맞춘다 — 모자라면 말줄임은 제목 쪽이다. 구분 칸 260px
    에서 「계산 밖 12공정 ⓘ」 까지 제목 말줄임 없이 든다(2026-11-24 합성 사본 브라우저 실측).
- `src/capa_simulation/components/formula_text.py` — 화면 식 글(「a ÷ b = c」)이 **적힌 수로 다시 셈해도 결과와 맞게** 인수
  글자와 등호를 고르는 순수 도우미(8장 「화면 숫자는 검산되어야 한다」). 길이 둘이고 화면마다 지금 쓰는 길을 지킨다 —
  「≈」 길(`equals_mark` — 인수는 화면 자릿수, 적힌 인수로 다시 셈한 글이 결과 글과 다르면 「=」 대신 「≈」, 적힌 글자에서
  수를 읽는 `written_value`, 두 항의 합·차를 다시 셈하는 `written_total`)은 공정 Capa 상세 근거 카드·결합 캔버스 풍선, 가용설비 현황 비교 시트 풍선·근거 카드 식 셋,
  제약 시뮬레이션 계산표 풍선이고, 자릿수 늘리기 길(`consistent_digits`·`operand_text` — 어긋날 때만 그 식의 인수를 모두 한 자리씩, 여섯째
  자리까지, 끝내 못 맞추면 화면 자릿수와 「≈」. 한 카드의 식들은 `shared_digits` 의 한 자릿수로 — `digits_within`)은 제약 시뮬레이션 고른 달 계산이고, 인수마다 따로 늘리는 꼴
  (`consistent_places` — 더 적는 자리 수의 합이 가장 작게, 같으면 뒤 인수 먼저)은 표준 목표 로직 분석이다. 인수 글자 꼴은
  화면마다 다르므로 쓰는 쪽이 넘긴다(`operand_text` 의 `plain`). 결과 값·판정·올림 규칙은 바꾸지 않는다.
  `parse_formula` 는 시험용 읽기다(`tests/test_formula_text.py` — 값 격자로 지은 식 글을 읽어 다시 셈하는 검산 그물과, UI
  모듈의 식 꼴 f-string 마다 이 모듈을 거치는지 보는 AST 가드 — 가드가 보는 꼴·보지 못하는 꼴과 허용·대기 목록은 그 시험
  머리에 있다).
- `src/capa_simulation/components/month_sheet_canvas.py` — 월 시트 캔버스 엔진(라벨·월 Figure 한 쌍의 `Row`·
  `Cell`·글자·표적·서식·`canvas_point`). 공정 Capa 상세·비교 시트·제약 시뮬레이션 계산표 셋이 훅(`row_hook` 등)으로 쓰는
  순수 함수다.
  - 풍선 글이 빈 칸은 둘째 표적 trace(`hoverinfo: "none"`)다 — 풍선 상자 없이 누르면 골라진다. `Row.label_hover` 를
    준 행만 라벨 Figure 에 줄 이름 칸 풍선 표적이 서고, 없으면 라벨 Figure 에 trace 가 없다.
  - 라벨 글은 넘치면 끝을 말줄임으로 줄인다. `Row.label_part`(라벨 끝 「 (부품)」 의 부품)를 준 행은 그 끝을 남기고 앞을
    줄인다(`home_figure_common._fit_part_label` — 8장 「합쳐 보는 화면의 부품 이름표」). 같은 제품의 다른 부품은
    `Row.label_part_siblings`, 줄이지 않는 앞 글(「└ 」 · 「제약 제품 · 」)은 `Row.label_lead` 다. 구획 제목 줄도
    같다(`title_row(label_part=, label_part_siblings=, label_lead=)`). `Row.label` 은 그대로라 시트 엑셀은 이름표를 다 싣는다.
  - 라벨 칸은 260px(`DASHBOARD_LABEL_COLUMN_WIDTH_PX`)이고 좁은 창(`NARROW_VIEWPORT_MAX_PX` 640 이하)에서는 150px
    (`NARROW_LABEL_COLUMN_WIDTH_PX` — Streamlit 이 그림을 그리는 가장 좁은 폭)로 준다 — 390px 창에서 달 칸이 한 달도 안
    남았다(E2E r1 #20, 개선 거리 I12). 세 화면이 `split_scroll_columns_style(narrow_label_width_px=…)` 로 주고, 260px 에 맞춘
    줄 이름의 넘친 오른쪽은 라벨 그림 SVG 가 자른다. 컬럼에는 `overflow` 를 걸지 않는다(줄 이름 칸 풍선이 잘린다). 풍선을
    넘치게 그림 SVG 의 `overflow` 를 푼 공정 Capa 상세는 좁은 창에서 풍선 SVG(마지막)만 남기고 다시 자른다
    (`process_capa_view.label_overflow_style`). 라벨이 여러 분류 칸인 HOME·월별 표는 줄이지 않는다
    (`tests/test_split_column_width.py`).
- `src/capa_simulation/components/availability_sheet_canvas.py` — 비교 시트 9행(`SheetView`)을 엔진으로 그리는 순수
  함수. 행 모델(`build_availability_sheet_rows` — 머리 · 구획 제목 셋 · 값 아홉)을 그림과 시트 엑셀이 같이 읽는다. GAP 은 면 없이 글자색만 쓰고(상태 3색 아님) 「—」 칸은 풍선 까닭(`REASON_TEXTS`)을 단다. 풍선 식(Static 가용 = 보유 +
  대여 · 보유 = 기존보유 + 호기 · 가용 = 보유 + 대여 · GAP = 설비 일정 − Static)은 적힌 글자에서 다시 셈해 어긋나면 「≈」 다
  (`formula_text`). Static 가용 식 줄은 결과가 앞 줄이라 어긋날 때만 줄 앞에 두고, 원값부터 다른 ⚠ 달은 두지 않는다.
- `src/capa_simulation/components/availability_sheet_keys.py` — 비교 시트 key(`GAP_SHEET_CHART_KEY` 등)를 가벼운 모듈에
  둔다 — `app.py` 가 패널·서비스를 import 하지 않고 터치 스크롤 막이(`components/plotly_touch_scroll.py`)에 넣게.
- `src/capa_simulation/components/availability_sheet_workbook.py` — 가용설비 현황 `Static 대비 일정` 「시트 엑셀」(시트 엑셀
  넓히기 2 — 「표시」 의 시트 · 호기 목록 둘). 화면 시트와 같은 행 모델(`build_availability_sheet_rows`)을 공정 Capa 상세 시트 엑셀과 같은 길
  (`process_capa_workbook.month_rows_sheet`)로 옮긴다 — 칸 글 · GAP 증감 글자색 · Static 묶음 면 · 「—」 · ⚠ 를 다시 셈하지 않고,
  고른 칸 표지는 옮기지 않는다. 호기 목록(`unit_list_workbook`)은 화면 표 그대로(표시명 · 화면 숫자 꼴 · 빈 값은 빈 칸 · 회색 머리
  줄 고정)에 맨 위 값 줄(공정 · 시나리오 · 조회기간 · 설비 시나리오 · 호기 필터 · 분류)이다. 밝은 테마 토큰 · 새 의존성 없음. Streamlit 을 import 하지 않는다
  (`tests/test_availability_sheet_workbook.py`).
- `src/capa_simulation/components/process_capa_canvas.py` — `공정 Capa 상세` 결합 월 캔버스(① Static 기준 ② 일정 가용
  ③ 비가동 ④ 단축 ⑤ 비가동 일정 — 2026-11-12 사용자 답 k-c0)의 순수 그림 함수 `build_process_capa_canvas`. 세션·캐시·DB 를 보지 않는다. 행 모델은
  `build_process_capa_rows`(행 · 칸 글 · 칠 · 부족 띠 열)이고 그림과 시트 엑셀이 같은 것을 읽는다. ④ · ⑤ 를 글로 옮기는
  `track_texts` 는 그림과 같은 자리(`_unit_marks` · 화살표 꼬리 · 촉)에서 낸다.
  - 라벨·월 Figure 한 쌍이라 부족 띠·보는 달 열이 구획을 넘고 칸 선택이 그림 하나에서 온다. 판정색은 요약 프레임 `판정`
    한 길이다. 칸은 `base` 막대 + 표적 막대(`HIT_TARGET`)이고 엔진 상수·`canvas_point` 를 이 모듈 이름으로도 내보낸다.
  - 구획 제목 줄에 세부 글을 두지 않는다 — 출처 · 단위는 제목 줄 풍선(`Row.label_hover`)과 Guide 다(k-c1 · k-c2). 시트
    범례도 Guide 「시트 범례」 절이다(k-c5).
  - 「제품별 소요대수」 분류 줄 글 · 행 id 는 표의 `분류` 그대로다. 부품으로 가른 줄(`CUSTOM` 이 접힌 값이 아님)은
    `Row.label_part` 를 달아 라벨 칸 줄임이 부품을 남긴다 — 앞을 남겨 자르면 두 부품 줄이 같은 글이 된다.
  - ② 일정 가용 = 총보유대수(달력 월) · 가용대수(기존보유 + 호기 가용 + 호기 비가동 손실 — **비가동 빼기 전**, n1 (가)) ·
    전월 대비 · 소요대수(판정 기준 소요, 「제품별 소요대수」 면 ① 과 함께 분류 행 — q4 (가), 가정이 걸린 달은 ÷f) · 확보율 ·
    확보 기준 과부족. ③ 비가동 = 비가동대수(`downtime_impact` 의 `비가동 손실`) · 실가용대수(`downtime_basis` — Static
    이면 ① 가용, 일정이면 ② 가용에서 뺌, 0 에서 멈춤 — 일정이면 계획 `가용대수` 와 같다) · 소요대수(합계) · 확보율 · 과부족.
    ② · ③ 의 판정 칸은 ① 과 같은 길(`services/process_capa_detail.judge_supply` → `securement_balance`)이고 부족 띠는 판정
    기준 요약 하나다(q8 (가)).
  - 접힌 구획(`collapsed`, id `SECTION_IDS`)은 제목 줄(▸)만 남는다 — 판정은 요약에서 내 ① 을 접어도 부족 띠·② · ③
    확보율이 같다. 호기 라벨에 「N모듈」 을 적지 않고 풍선(「· 모듈 N」, ⑤ 는 줄마다 모듈 설비명)에 둔다.
  - ④ 첫 줄 「단축 후 확보율」(`ROW_UNITS_AFTER_RATE`, 2026-11-12 사용자 답 q6b (나))은 계획(`process_months`)의
    `단축후가용대수` 가 `가용대수` 와 다른 달만 값이다 — 소요는 계획의 소요, 판정은 `judge_supply`(① 과 같은 길)이고 부족
    띠는 바꾸지 않는다. 호기 줄은 `DynamicCanvasInput.units_view`(`UNITS_ALL` · `UNITS_SHORTENING`, q6 메모)를 따른다 —
    단축 필요만이면 단축 대상 · 추가N 줄만(정지·반출/이설 줄 · 일정 미정 줄 없음), 30행 상한은 거른 뒤에 센다.
  - ⑤ 모듈 묶음(`_split_module_arrows`, q7 (가) · 메모)은 같은 비가동(시작일 · 종료일 · 비가동유형)이 그 호기의 **모든**
    모듈에 있으면 Main 줄 화살표 하나(달별 손실은 모듈 몫의 합, 풍선 「모듈 n 모두」)로 합치고, 일부 모듈에만 있는 것은
    Main 줄 아래 모듈마다 「└ 모듈명」 줄(`label_indent` `MODULE_ROW_INDENT_PX` · 흐린 글자, 행 id
    `arrow:<호기>#<모듈>#<n>`)이다. 합친 것이 없는 Main 줄은 화살표 없이 머리로 선다(풍선 없음). 단독 호기의 겹친
    비가동 둘째 줄도 「└ 호기」 다 — 「⋯ 같은 호기」 줄은 없다.
  - ④ 호기 풍선은 세 줄(호기 · −N일 · Model / Qual → 목표 · 기여 / 해소 · ⚠ — UPEH 가정 계획만 넷째 줄)이고 그
    호기 그림이 걸친 달 칸(`_unit_marks` → `_unit_span`, 그림과 한 자리 — 표지는 반지름까지, 붙은 글자는 어림 폭의
    `_SPAN_TEXT_SHARE` 몫까지)과 줄 이름 칸에서만 뜬다. 빈 달 칸은 풍선 없이 누르면 그 달이다. 해소 기여 월은 해소
    눈금이 서는 줄(단축 · 추가N)만 적는다. 라벨 Figure 는 그 풍선이 있을 때만 hover 를 켠다(`process_capa_view`).
    단축 · 추가N 줄의 달 칸 풍선은 증분을 그 달 몫 「· 이 달 +n대」 로 적는다(그 달 몫이 0 이면 숫자를 뺀다) — 줄 이름 칸의 요약(대상 월 몫)을 모든 달 칸에 띄우면 뒤 달 증분으로 읽힌다.
  - `assumption`(UPEH 가정)이면 ① 끝에 세 줄(구간 달만 값)이 서고 부족 띠는 가정 요약의 판정, ② · ③ 소요는 가정 소요다.
    「UPEH 가정 계획」 표지는 ④ 호기 풍선에만, 가정 전에서만 당긴 호기는 ④ 흐린 줄이다(풍선 「가정 전 −n일 → 가정 m일」).
  - ③ 비가동대수 칸은 손실 0 이면 빈칸, 0 이 아닌 작은 값이 0 으로 적히면 0 이 아니게 적힐 때까지 한 자리씩 더(`_loss_text`
    — 빈칸 문턱 `round(값, 9)` 까지). 풍선은 「호기 비가동 a + 입력 비가동 b」(0 인 쪽 뺌 — 입력 몫은 `manual_removed_text`)
    이고 적힌 갈림의 합이 칸 글과 다를 때만 그 앞에 「≈」 다.
  - 풍선의 식(① 가용 「보유 − 대여」·확보율 「가용 ÷ 소요」·과부족 「가용 − 소요 × 기준」·가정 소요 「가정 전 ÷ f」, ②
    총보유 「기존보유 + 반입 − 반출/이설」·가용 「기존보유 + 호기」·전월 대비 갈림, ③ 실가용 「기준 가용 − 비가동」·갈림
    「호기 a + 입력 b」)은 칸 자릿수 인수로 다시 셈해 어긋나면 「≈」 다(`formula_text.equals_mark`). 과부족 식 줄과 ③ 갈림은
    결과가 앞 줄이고 등호가 없어 어긋날 때만 식 앞에 둔다(검산 그물 `tests/test_formula_text.py`).
  - ② 전월 대비 칸 풍선은 첫 줄이 「전월 대비 ±a = 신규 ±b · 정지·반출 ±c」(기존보유가 바뀐 달은 「기존보유 ±」 를 더함)이고, 그 아래는 `unit_month_changes` 의 호기 묶음(설비키)별 몫을 큰 차례로 여섯까지(`_MOVE_LIMIT` — 한 줄에 셋), 나머지는 「외 n대」 다(몫은 비가동 빼기 전).
- `src/capa_simulation/components/monthly_table_workbook.py` — `산출 결과` 대당 Capa · 소요대수 「시트 엑셀」. 화면 월 표
  (`render_hierarchical_monthly_table`)에 넘긴 것과 같은 인자(거른 표 · 분류 열 · 열 이름 · 소수 자리 · 표시명)로 칸을 옮긴다 —
  분류 칸 글은 공개 내보내기(`build_hierarchical_monthly_export` — 반복 접두 생략)에 표시명을 입힌 표를 넘겨 얻고, 월 칸은
  화면 글(`,.nf` · `.n%`)이 적는 값의 숫자 셀 + 같은 글로 보이는 숫자 꼴(0 · 빈 값은 빈 칸), 서식은 밝은 테마 토큰(머리 띠 ·
  최상위 묶음 줄무늬 · 묶음 경계선은 바뀐 열부터 · 분기 · 분류와 달 사이 · 바깥은 굵은 선, 판정 칠 없음 — 화면에도 없다),
  열 너비는 화면 px, 머리 줄 · 분류 열 고정. 칸 서식은 시트마다 한 번 지어 돌려쓴다(2,660행 × 21칸 합성 표 약 0.3초 — 샘플
  관측). Streamlit 을 import 하지 않는다(`tests/test_monthly_table_workbook.py` 가 화면 표의 Figure 인자와 견준다).
- `src/capa_simulation/components/sheet_download.py` — 「시트 엑셀」 의 화면 쪽 공용 몫: 통을 조건 키로 세션 칸에 몇 벌
  기억하고(`remembered_bytes` — 공정 Capa 상세 `remembered_sheet` · 산출 결과 시트 · 산출 결과 CSV 가 같이 쓴다, 칸 이름이 따로), 시트 맨
  위 시나리오(머리 띠 위 줄 `header_lines`) · 조회기간 · 공정 거름 글을 짓는다(세션만 읽는다).
- `src/capa_simulation/components/process_capa_workbook.py` — `공정 Capa 상세` 「시트 엑셀」. 결합 캔버스의 행 모델을 칸
  하나하나 엑셀 칸으로 옮긴다(행 모델 → 시트 한 장 `month_rows_sheet` 는 같은 월 시트 엔진을 쓰는 Static 대비 일정 시트 엑셀도 쓴다 —
  머리 칸이 비면 엔진처럼 달 이름)(판정 · 칠 · 띠를 다시 셈하지 않는다). 색은 밝은 테마 토큰(`theme.pinned_mode`), 부족 달 띠는
  `tokens.opaque_over` 로 그 줄 면 위에 섞은 불투명 색, 숫자는 칸 글을 같은 꼴의 숫자 꼴로 되읽은 숫자 셀(`screen_number` —
  보이는 글이 화면과 같다), 두 줄 칸(엔진 `Cell.sub` — 공정 Capa 상세 다섯 구획에는 없다)은 딸린 줄 「└ 둘째 줄」, ④ ·
  ⑤ 는 글(`track_texts` — ⑤ 「└ 모듈명」 줄은 한 칸 들임), 둘째 시트는 호기 CSV 표다(④ 보기로 거르지 않는다).
  Streamlit 을 import 하지 않는다(`tests/test_process_capa_workbook.py` 가 그림 칸 글 · 색과 견준다).
- `src/capa_simulation/components/process_capa_view.py` — `공정 Capa 상세` 의 「본문 프래그먼트」
  (`render_process_detail_view`)와 KPI·정리 줄. `ProcessDetailView` 하나를 받아 지금 보는 달에 닿는 것만 그린다. 표 도구 줄
  오른쪽 끝에 호기 CSV(`ProcessDetailView.units_csv`, 설비 일정이 설 때만)와 「시트 엑셀」(늘)이 서고, 정리 줄은 값 표지와 필요 단축 일정
  링크다 — 링크는 그 화면 카드에서 온 방문(도착 「← 필요 단축 일정」 이 같은 길)만 빼고 일정 부족 달이 있는 공정에도 선다
  (`shortening_link_needed` — 2026-11-10 답 Q2-8, 설계 규칙 UI-LAY-12 예외 — 근거 패널의 일정 부족 달 단추는 그 달을 골라야 서서 처음 연 달이
  일정 부족 달이 아니면 길이 없었다. KPI 아래 다음 화면 줄은 2026-11-10 보드 c2-picked 로 걷었다). 「구획」 칩은 라벨을 숨긴 칸이라 뜻은 칩 바로 뒤 빈 캡션
  풍선 하나다(`SECTIONS_HELP`, 2026-11-10 보드 Q-8). 그 곁 비가동 기준 「Static · 일정」(`BASIS_KEY` — 설비 일정이 서는 공정에서 ③ 을 펼쳤을 때만) ·
  ④ 보기 「전체 · 단축 필요만」(`UNITS_VIEW_KEY` — 호기 줄이 있는 공정에서 ④ 를 펼쳤을 때만, 처음 전체, 2026-11-12 사용자 답 q6 메모)은
  세션 값 고르기이고 접혀 서지 않는 회차에도 세션 값을 쓴다. 두 고르기는 보이는 캡션이 없고 뜻은 선 것 가운데 마지막 고르기와 한 칸인
  빈 캡션 풍선(ⓘ) 하나다(`picker_help` — 선 고르기의 뜻만, 2026-11-12 남은 물음 보드 ③-2 (가) — 줄이는 차례,
  UI-LAY-11 · 1600 창 「제품별 소요대수」 켬은 그래도 「분류」 칸이 둘째 줄이라 두 줄 — `docs/TODO.md` 4장 물음). 고르기 셋(비가동 기준 · ④ 보기 · 분류)은 저마다 ⓘ · 「분류」 캡션과 한 칸(`_picker_pair` — 줄바꿈 없음)이라 줄이
  모자라면 함께 다음 줄로 가고, 숨긴 위젯 라벨은 「비가동 기준」 · 「④ 단축 보기」 다(UI-LAY-13). 단축 목표 글은 화면에 두지 않고 Guide · 시트 엑셀 머리 값 줄이 적으며(2026-11-12 사용자 메모 k-c4)
  KPI 칩에 거듭 적지 않고, 공정 카드의 기간 규칙은 「공정」 칸 풍선이다. 일정이 서지 않는 자리는 `constraint_equipment_plan.absent_note` 를 함께 쓴다.
  KPI 넷(`render_process_kpis`) 회색 줄은 바뀌는 값 · 기준 표지만이다 — 그 달 · 월 최대 부족 · 「달 수 · Static 기준|UPEH 가정 기준」 ·
  「가정 전 n」, 그리고 값에 「일정 n」 이 설 때만 붙는 「 · 일정은 설비 일정」(`cause_caption` — 그 수는 설비 일정 기준이라 앞 기준 표지가
  덮지 않는다, 2026-11-21 갈래 판정). 늘 같은 「월별 확보 기준」(미달 없을 때) · 대책의 「설비 일정 기준」 은 칸 풍선과 Guide 「KPI 넷」
  이다(2026-11-20 갈래 판정 — 규칙집 6-39 pc-kpi-notes, UI-TXT-01 · UI-TXT-05 · UI-TXT-04).
  - 칸 누름·◀▶ 콜백은 `PROCESS_DETAIL_MONTH_KEY` 를 적고 `sidebar_status.rerun_app_unless_alone` 으로 끝낸다
    (`tests/test_app_navigation.py`·`tests/test_process_capa_detail_page.py`).
  - 산출 근거는 접힌 머리 한 줄(「산출 근거 · 달 · 공정」 — 기억 상자)이고 다른 달 칸 · ◀▶ · 머리를 누르면 펴져 그 달을 보인다 — 이미 고른 같은 달 칸을 다시 누르면 그림이 선택 사건을 보내지 않아 펴지지 않는다. 「제품별 소요대수」 는 ① 이나 ② 가 펼쳐져 있을 때만 켤 수 있다. 다른 화면 글이 이 가용을 가리킬 때도 「공정 Capa 상세 ③ 일정 기준 실가용」 으로 부르고(제약 시뮬레이션 `constraint_equipment_plan.SAME_AS_DETAIL` · 가용설비 현황 비교 시트 풍선), 가용설비 현황에서 ⑤ 로 가는 링크 글은 「공정 Capa 상세 비가동 일정에서 화살표로 보기」 다.
  - 「경로별 인자」 표(`_render_route_factors`)의 「부하량 근거」 칸은 그 경로 표를 지은 계산 키의 계산 토큰에서 푼 선언
    (`simulation_cache.token_route_exceptions(view.scenario_key[1])`)으로 그린다 — 근거 글과 숫자가 늘 같은 판이고 `ProcessDetailView`
    에 따로 칸을 두지 않는다(5장 44). 뜻은 칸 머리 풍선 · Guide 이고 자리 글은 늘리지 않는다. 경로 표는 그림 · 시트 엑셀에 실리지
    않아 `CANVAS_SCHEMA_VERSION` · `SHEET_SCHEMA_VERSION` 은 그대로다.
  - 시트 엑셀 바이트도 세션 칸(`SHEET_MEMO_KEY`, 몇 벌)에 기억한다 — 키(`sheet_memo_key`)는 그림 기억 키에서 그림 세대 · 테마를
    빼고 머리 값 줄을 더한 것이라 달 칸 누름 · 다른 위젯 회차는 통을 다시 만들지 않는다(콜러블 지연 생성은 쓰지 않는다 — 9장).
    같은 조건에서 시트 꼴(칸 · 숫자 꼴 · 머리 값)을 바꾸면 `SHEET_SCHEMA_VERSION` 을 올린다.
    재료(`sheet_request`)는 그림과 같은 인자(구획 · 펼침과 분류 · 제품 행 표 · 「더 보기」 · UPEH 가정 · 비가동 기준 · ④
    보기)다. 머리 값 줄의 「구획」 은 시트에 선 구획만, 「비가동 기준」 · 「④ 단축」 은 ③ · ④ 가 펼쳐 섰을 때만이다(k-c6).
  - 그림은 세션 칸(`CANVAS_MEMO_KEY`)에 기억한다(새 `st.cache_data` 없음). 근거 카드 식(①~④ 와 원인 줄)은 검산되어야
    하고(어긋나면 `≈` — `formula_text.equals_mark`, 등호 없는 ① 원수요 부하량 ÷ 실효 대당 Capa 줄은 카드의 소요와 어긋날
    때만 줄 앞에)
    목표는 `target_label`(정수 「110%」 — 값은 HOME 확보 기준의 판정 경계 1.095, 식 줄은 곱한 값 「109.5%」)로 적는다.
    ① 의 상위 제품은 근거 요약 `top_products` 의 `분류`(분류 행과 같은 이름표) 글이다.
  - 「구획」 칩(`st.pills`)은 선택지 다섯을 늘 고정하고 칸이 없으면 다섯 모두로 심는다(`seed_sections` — 구획이 넷이던
    세션은 ③ 을 한 번 편다). 접힘 · 비가동 기준 · ④ 보기는 그림 기억 키에 들고(`CANVAS_SCHEMA_VERSION` 14), 접힌 ④·⑤ 의
    「더 보기」 는 숨는다. 화면을 옮기는 다음 화면 단추는 본문에서 옮긴다(프래그먼트 콜백 금지).
  - **지금 보는 달 표지(머리 밑줄 · 열 테두리)는 그림에 굽지 않고 그림 위 덧칠이다**(`selected_month_style` — 그 열 자리 SVG
    한 장, 그림에 굽던 것과 같은 자리 · 굵기 · 색, 그림 바깥 테두리를 그 위에 다시 그어 겹침 차례도 같다. 누름은 그림으로
    지나가고(`pointer-events: none`) 풍선 층은 표지보다 위, 서식은 이미 있던 서식 `st.html` 하나에 싣는다 — 이벤트 칸 수가
    같다). 그림 기억 키(`canvas_memo_key`)에 달이 없어 칸을 눌러 달만 바뀐 회차는 그림을 다시 보내지 않는다. 브라우저가 칸을
    쥐었고(`CANVAS_PICK_KEY` — 칸 선택 콜백이 적고 빈 선택이면 지운다) 그 칸이 보는 달과 어긋나거나 그림 조건이 바뀐 회차에만
    세대(`selection_epoch` · `CANVAS_EPOCH_KEY` — 그림 `layout.meta` 의 `select_epoch`)를 올려 새 요소로 만든다(쥔 칸이 없으면
    올리지 않는다 — 9장 「칸 선택」). 그래서 칸을 누른 뒤 첫 ◀▶ · 다른 화면에서 들어옴 · 구획 칩은 그림을 통째로 보내고, 그
    뒤의 ◀▶ 는 보내지 않는다. 누른 칸의 마우스 풍선은 그림이 그대로라 남는다(`docs/TODO.md` 2장 「성능」 M22 결정 거리).
    공용 월 시트 엔진(`month_sheet_canvas`)은 그대로라 Static 대비 일정은 굽는 표지다.
  - UPEH 가정 토큰도 그림 기억 키에 든다. KPI 는 가정 요약 값에 회색 줄 「가정 전 n」, 근거 카드 ① 은 구간 달에 가정 한
    줄, ③ 은 구간 달이면 머리 식·판정·원인을 가정 요약으로 내고(식 첫 줄 「소요 = 가정 전 ÷ f」) 가정 전 판정은 회색 「가정
    전: …」 한 줄이다 — 같은 패널의 다음 화면 줄과 같은 기준(이름은 2026-11-12 사용자 답 q2 (가)).
  - ③ 판정 카드의 판정하지 않는 달(소요 없음)은 `ProcessDetailView.outside_basis`(공정 경로가 모두 계산 밖 — 11장)가 있으면
    「계산 밖(소요기준 BOX) — 판정하지 않습니다」 다 — UPEH 가정 달 머리와 회색 「가정 전: …」 줄도 같은 글(`_unjudged_text`). 판정이
    서는 달은 그 값과 상관없이 식 그대로다. 카드는 회차마다 짓는 글이라 그림 · 시트 기억 키와 `CANVAS_SCHEMA_VERSION` ·
    `SHEET_SCHEMA_VERSION` 은 그대로다(`tests/test_process_capa_view.py`).
- `src/capa_simulation/components/scenario_management.py`, `bigdataquery_registration.py`, `auto_official_update_tab.py`
  — 시나리오 관리 페이지의 세 탭 UI.
  - 저장 폼 칸은 성공한 회차에만 key 세대를 올린다. 원본 리비전 메모(`SOURCE_MEMO_KEY`)는 목록 요약이 같을 때만 쓴다.
  - 리비전명 변경은 목록 「변경 저장」(`_save_list_edits`, 한 건은 `save_revision_name`)을 거친다 — 저장소의 비교 후
    쓰기(`apply_scenario_list_edits`·`rename_revision`, 다른 사용자가 먼저 바꿨으면 `BatchEditRefused`·`RevisionNameMoved`) 뒤
    스냅샷 캐시·파생 원본 메모를 비우고 이 세션 이름표만 고친다(활성화하지 않는다).
    시나리오 「최근 수정」·공식 이력·비교 프로필은 건드리지 않는다(`tests/test_revision_rename.py`).
  - 맨 위 알림·두 건 체크 경고는 늘 서 있는 칸 안에 그린다 — 보관함 상자(key 있음) 앞 순번이 알림 때문에 밀리면
    본문 `st.rerun()` 뒤 흐린 사본이 남았다(9장 「key 가 있어도 자리는 고정한다」).
  - 파생·월 머지·연도 이동은 화면(`components/scenario_transform.py`·`components/scenario_month_merge.py`·
    `components/scenario_year_shift.py`)과 규칙(`services/scenario_transform.py`·`services/scenario_month_merge.py`·
    `services/scenario_year_shift.py`·`services/scenario_virtual_products.py`)으로 나뉜다.
  - `auto_official_update_tab.py` 설정은 버전 대조(칸에 key 없음), `bigdataquery_registration.py` 목록은 `st.form`
    밖·등록 폼 위의 `st.dataframe(on_select="rerun")` 이다. 저장 막힘은 빨간 상자 없이 꺼진 저장 단추 풍선이고(`UNSAVABLE_REASON`),
    조회일 · 조회 단추 · 검색 · 표시 범위는 표 위 한 줄이다. 탭 맨 위 소제목은 없다(g2-25). 설정 줄 「BigDataQuery 설정」 도
    없다 — 다 준비됐으면 그리지 않고 빠진 것은 상태 알림 `AD-04` 만이다(2026-11-09 사용자 규칙 「상단 여백 · 문구 최소화」,
    설계 규칙 UI-TXT-08 · UI-NTF-02). CUSTOM 원천 표 환경변수(`CAPA_BDQ_CUSTOM_TABLE`)가 없거나 꼴이 틀리면(상세 조회와 같은 판정
    `custom_source_problem` 을 회차마다 한 번 읽는다 — 끄개가 켜졌을 때만 `custom_table_problem`) 저장 단추가 잠기고 풍선(`custom_locked_help`)이 그 변수 이름으로 까닭을 말하며
    (개발자가 아니면 변수 이름 · 채울 자리 없이 `CUSTOM_LOCKED_PUBLIC_HELP` 한 문장 — 아래 「개발자 몫」),
    `AD-04` 전문에 한 줄(`custom_table_notice` — 막히는 것과 채울 자리, 값은 싣지 않음)이 든다 — 전문 차례는 조회 SQL → CUSTOM 원천 표
    → 패키지(패키지 줄은 조회 SQL 이 다 섰을 때만), 짧은 글은 그 가운데 앞선 하나(`_configuration_short`), 저장 단추 풍선도 조회 SQL →
    CUSTOM 원천 표 → 고른 코드 차례로 앞선 하나다. 목록 조회는 그 표를 쓰지 않아 잠그지 않는다. 잠긴 단추가 눌려도 상세 조회가
    패키지를 부르기 전에 같은 판정 글로 멈춰 단추 곁 오류가 된다(설계 규칙 UI-INP-07 — 판정이 프로세스 환경이라 보인 회차와 누른
    회차가 갈리지 않는다). CUSTOM 원천 끄개(`CAPA_BDQ_CUSTOM_SOURCE=off`)를 내렸으면 그 판정이 None 이라 변수가 없어도
    단추가 열리고 `AD-04` 에 그 줄이 없다(잠글 까닭이 없다). 그때 저장하면 저장 알림 뒤 셋째 칸(`REGISTRATION_CUSTOM_FLASH_KEY` — 켬이면
    `SC-05`, 끔이면 `SC-06`, 한 등록에 하나라 충돌 칸 index 1 그대로)에 사건 알림 `SC-06` 이 표 없이 알림창 · Alarm 에만 선다(전문 끝
    「끄개 CAPA_BDQ_CUSTOM_SOURCE=off · 시뮬레이션 코드 <코드>」 — 표 이름 · 값 없음, 시험
    `test_a_switched_off_registration_saves_raises_sc06_and_writes_the_memo_piece`). 개발자 몫은 `admin_view` 한 판정이다 — 「시뮬레이션 코드 조회」 ·
    「저장」 의 상세 조회 실패 곁 오류는 `grade_hooks.diagnostic_message` 를 지나 개발자가 아니면 갈래와 할 일만 남고(원문 · 서버 시작 점검 ·
    환경변수 이름을 걷은 `company_bigdataquery_adapter.public_failure_text` 꼴, 준비 실패는 「개발자에게 알려 주세요」 한 문장), `AD-04` 전문은
    개발자가 아니면 CUSTOM 원천 표 줄과 패키지 줄의 서버 시작 점검 단락을 뺀다(남는 줄이 없으면 짧은 글 — 지문 `content` 는 개발자 전문
    그대로라 「이 등급으로 보기」 를 켜고 꺼도 다시 뜨지 않는다). 그래서 CUSTOM 원천 표로 잠긴 저장 단추 풍선도 개발자가 아니면 변수 이름과
    「채울 자리는 Alarm 그 줄이」 를 싣지 않는 `CUSTOM_LOCKED_PUBLIC_HELP`(「… 막힙니다 — 개발자에게 알려 주세요.」 — 없음 · 꼴 틀림 같은 한
    문장, `_custom_locked_help_for_viewer`)다 — 그 회차 `AD-04` 전문에 가리킬 줄이 없다. 등록 시각 칸 꼴 틀림 · 등록된 시나리오 읽기 실패
    (`SC-02` — 이미 판정)는 그대로다(시험 `test_a_non_developer_sees_the_failure_without_the_original_or_server_steps` ·
    `test_a_developer_still_sees_the_original_and_the_start_check_paragraph` ·
    `test_ad04_full_drops_the_start_check_paragraph_for_others_and_keeps_its_fingerprint` ·
    `test_a_non_developer_reads_the_custom_lock_without_the_variable_or_the_place_to_fill`).
    등록 폼 글자 칸은 세대 key(`form_field_key` · `FORM_GENERATION_KEY`)이고 행을 고르거나 폼을 초기화할 때마다 새 위젯으로
    선다(9장 「폼 안 칸에 세션으로 값을 써 넣지 않는다」). 빈 칸 저장은 빈 칸을 모아 곁 한 줄로 거부한다(「필수 칸이 비어 있습니다:
    …」 — 복제와 같은 꼴). 글자 칸은 입력 초안이라 `persist_state` 가 없어
    그리지 않은 회차에 버려진다 — 목록 선택(위젯 아닌 칸)만 남았으면 위젯 앞 `_restore_dropped_prefill` 이 그 선택의
    값으로 다시 채운다(상세 조회 기간은 세션에 남으므로 건드리지 않는다). 날짜 칸 둘(목록 `조회일`, 폼 위 `상세 조회 기간`)은
    「적용」 트리거를 바로 받아야 해 `st.form` 밖이고(`components/date_panel.py`), 목록 조회는 폼 없이 단추 하나다.
  - `auto_official_update_tab.py` 실행 기록 표의 「사유」 칸은 잘린 채 둔다 — 표 칸은 칸마다 풍선을 달 수 없어 칸 머리 풍선(`RUN_REASON_HELP` — `TextColumn(help=)`)이 그 칸에 적히는 것(지정한 공식 번호 · 주차 · 받은 코드, 건너뛰거나 지정하지 않은 까닭, 이어 적힌 대조 · 경고 — CUSTOM 원천 대조 · 업무 키 충돌 · 소요대수에 들지 않은 수요 · CS 빈 행 · 대당 Capa 계산 멈춤과 푸는 길)과 잘린 글을 읽는 길(머리 오른쪽 끝을 끌어 넓히기 · 표 도구로 크게 보기 · 내려받기)을 말한다.
  - DB 등록 탭 표 위 작업 줄 맨 앞에 원천 종류 단추 「원천」(`DB 조회 · CSV 파일` — `SOURCE_ROUTE_KEY`, 처음 값 DB 조회 ·
    `persist_state="session"` · `required`)가 선다(설계 규칙 UI-LAY-07). `CSV 파일` 이면 목록 · 등록 폼 대신
    `source_csv_registration.render_source_csv_route` 를 부른다. `AD-04` 는 길과 상관없이 회차마다 낸다(DB 상태다) — 막힘
    낱말은 DB 길만 말한다(짧은 글 `SQL_MISSING_SHORT` 「… — DB 조회 · 등록이 막힘」 · CUSTOM 줄 꼬리 `CUSTOM_NOTICE_TAIL`
    「… DB 조회 · 저장이 막힙니다 …」, 시험 `test_ad04_words_say_only_the_db_route_is_blocked`). 저장 결과 칸
    (`registration_result_slot`) · 부대공정 칩(`render_extra_chip`) · 저장 뒤 처리(`finish_registration` — 활성화 · 목록 따라감 ·
    성공 알림 · SC-04 · CUSTOM 대조 · CS 빈 행 · 부대공정 · 대당 Capa)는 두 길이 함께 쓰고 `registration_steps()` 로 넘긴다. DB
    조회 길 회차는 올린 원천 CSV 를 놓는다(`forget_source_csv`) — 폼 되살리기(`_restore_dropped_prefill`)는 DB 길 회차에만 돈다.
- `src/capa_simulation/components/source_csv_registration.py` — DB 등록 탭 「CSV 파일」 길(원천 웹에서 받은 시나리오 CSV 로 시나리오
  등록)이다. DB 등록 화면 파일을 import 하지 않는다(그 파일이 부른다 — 나눠 쓰는 칸 · 처리는 `RegistrationSteps`).
  - 작업 줄의 올림 칸 「원천 CSV」(라벨 접음 · 폭 고정 · 칸 고유 상한 `SOURCE_CSV_UPLOAD_LIMIT_MB` 50MB)에 올리면 파일 id 가 바뀐
    회차에만 한 번 흘려 읽어(`summarize_source_csv`) 요약 · 거부 글을 세션 칸(`SourceCsvUpload` — `SessionSlot`, 바이트 · 표 없음)에
    둔다(설계 규칙 UI-PRF-01). 못 읽으면 올림 칸 아래 거부 한 줄(입력 곁)이고 목록은 없다. 읽혔으면 값 줄 · 목록(DB 목록과 같은
    꼴 — 한 행 고르기, key 에 파일 id)이 서고 코드가 하나면 첫 행이 골라진 채다. 고른 코드가 바뀌면 등록 칸 세대를 올려 그
    코드의 처음 값으로 채운다(같은 코드의 다른 PLAN 행은 다시 채우지 않음).
  - 등록 칸은 DB 폼에서 상세 조회 기간 하나를 뺀 꼴(시뮬레이션 코드 잠김 · 원천 시뮬레이션명 · 시나리오명 · 리비전명 · 원천
    등록시점 (선택) · 메모)이고 파일이 없어도 선다. 저장 단추 「CSV 파일로 시나리오 저장」 은 파일 없음 · 못 읽은 파일 · 코드 안
    고름 · 저장 불가 코드(DB 목록과 같은 `UNSAVABLE_REASON`)면 잠기고 까닭 풍선을 단다(UI-INP-07). 조회 SQL · CUSTOM 원천 표 ·
    끄개 · 패키지는 잠그지 않는다. 열린 단추에는 풍선이 없다(DB 저장 단추와 같다).
  - 저장(`_save_source_csv_scenario` — 폼 `if submitted:` 본문, 쓰기 장부 `NAME_UNIQUE`)은 등급 → 같은 이름(파일을 읽기 전) →
    빈 필수 칸 → 등록시점 꼴 → 공급자(`SourceCsvCoreDataProvider`) → `fetch_registration_dataset` → 프리셋 →
    `save_bigdataquery_scenario`(메모 `source_csv_note`) → `finish_registration` 이다. 원천 유형은 `CSV_CORE_DATA_UPLOAD`, 대조
    (`custom_check`)는 None 이라 `SC-05` · `SC-06` · 끔 메모가 서지 않는다. 저장하면 · DB 조회 길로 바꾸면 · 올림 칸이 비면(× ·
    다른 화면에 다녀옴) 업로드 관리자가 쥔 바이트를 지운다(`drop_uploaded_file` — Streamlit 1.63 관리자는 브라우저의 지우기 요청이나
    세션 끝에만 지운다. `st.chat_input` 과 같은 꼴로 메모리 관리자일 때만 `remove_file` 을 부르는 내부 API 라 Streamlit 을
    올리면 다시 본다) — 그때 등록 칸도 새 세대로 비운다(놓은 파일의 코드 · 이름이 남지 않게). 저장 뒤에는 올림 칸 세대를 올려
    빈 칸으로 선다. 시험은 `tests/test_source_csv_registration.py` ·
    `tests/test_source_csv_view.py`.
