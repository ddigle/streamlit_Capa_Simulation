# AGENTS 3장 · 10장 — 로컬 파일과 보안

### 자료실(GitHub Pages)과 발표 자료

- 사내 GitHub Pages 는 저장소 하나에 주소 하나이고 저장소 뿌리를 그대로 내보낸다(Pages 설정은 `main` 의 뿌리 `/`). 그래서 한
  사이트 안을 폴더로 가른다(2026-11-05 사용자 요청). 프로젝트 사이트라 주소 앞에 하위 경로가 붙으므로 링크는 모두 상대 경로다.
  앱은 이 파일들을 쓰지 않는다 — `site/` 는 배포 ZIP 에 실리고 이미지에서는 빠진다(`.dockerignore`).
  - 이 설정은 자료만이 아니라 `main` 에 추적된 트리 전부를 그 주소로 연다 — 사내에서는 `review/` · `modules/` · 런북 · `.deploy/` 까지. 그대로
    둘지 전용 가지로 내보낼지는 사용자 결정 대기다(`docs/TODO.md` 1장 「자료실 Pages 범위 결정」).
  - `.nojekyll`(뿌리, 빈 파일) — Jekyll 을 끈다. 켜 두면 사내에만 있는 md 의 Liquid 구문 오류 하나로 자료실 빌드 전체가 실패하는데 사외
    시험은 그 md 를 보지 못한다. 대신 점 폴더 · 언더바 파일도 그대로 나간다.
  - `index.html`(뿌리) — 첫 화면인 자료 목록. `scripts/build_site_index.py` 가 `site/catalog.json` 으로 쓰는 생성물이라 손으로
    고치지 않는다(`--check` 는 다르면 실패). 외부 요청이 없고 두 테마 · 폭 360 에서 선다.
  - `site/catalog.json` — 목록 정본. 자료마다 한 줄에 `path`(`site/` 아래 폴더)·`title`·`summary`(한 줄)·`kind`(발표 자료 · 안내서
    등)·`updated`(YYYY-MM-DD).
  - `site/contest-deck/index.html` — 대표 발표 자료(지금은 혁신대회 덱). 외부 요청 없는 단일 파일이고 숫자는 합성 샘플이다.
  - `site/module-guide/index.html` — 모듈 담당자 안내서의 한 파일 HTML 판. `docs/module_colleague_guide.md` 를 고치면 같은 변경에서
    이 파일과 `updated` 도 맞춘다. 코드 블록은 글 원본과, 첫 지시 블록은 지침서 0장과 글자까지 같고 「사내」 낱말을 쓰지 않는다.
  - 새 자료 — `site/<폴더>/index.html`(외부 요청 없음 · CR 없음 · `<link rel="icon" href="data:,">`)을 두고 `site/catalog.json` 에 한 줄을
    더한 뒤 생성기를 돌려 함께 커밋한다. `tests/test_site_index.py` 가 빠뜨림을 잡는다. 공개 저장소를 거친다 — 합성 값만, 실데이터 · 사내
    식별값이 든 HTML 은 올리지 않는다(시험이 내용을 막지 못하는 손 규칙이다). `site/` 는 코어라 사내에서 직접 더하면 다음 ZIP 이 지운다 —
    사내 전용 자리는 아직 없다(`docs/TODO.md` 1장 「자료실 사내 전용 자료 자리」).
- `src/capa_simulation/components/intro_overlay_assets/capa-teaser.html` — 입장 화면 `Introduce` 가 띄우는 40초 티저
  (2026-10-19 사용자 결정). 원본은 쇼케이스 `contest/dist/capa-teaser.html` 이고 덱과 같은 규칙으로 CR 을
  빼 복사한다. 외부 요청 없는 한 파일이어야 사내 오프라인에서 선다.
  - 원본·빌드·자료는 저장소 밖 `~/projects/capa-simulation-showcase`(덱 `contest`·바이블 `bible`·중간 보고
    `build`·Learning Champion 초안)가 그 폴더의 `CLAUDE.md`·메모리·세션으로 맡는다. 다른 발표 파일은 사용자가 자료실에 올리라고 할 때만 위 꼴로 더한다.
  - 원본은 쇼케이스의 `contest/dist/capa-contest.html` 이고 `capa-contest.artifact.html`(아티팩트용 변형)은 쓰지 않는다.
  - 두 폴더는 서로 읽되 쓰지 않는다. 덱을 바꿀 때만 이 저장소 세션이 CR 을 빼 복사해
    (`tr -d '\r' < ~/projects/capa-simulation-showcase/contest/dist/capa-contest.html > site/contest-deck/index.html`) `site/catalog.json`
    의 `updated` 를 고치고 생성기를 돌려 커밋한다. 저장소는 `.gitattributes` 로 LF, dist 는 CRLF 라 견줄 때도 CR 을 뺀 뒤 견준다.
  - 발표자 실명은 그대로 둔다 — 다시 묻지 않는다.

## 10. 로컬 파일과 보안

다음 파일은 Git에 커밋하지 않는다.

- `*.xls`, `*.xlsx`, `*.xlsm`, `*.xlsb`
- `data/*.db` 및 SQLite 보조 파일
- `data/*.duckdb` 및 DuckDB 보조 파일
- `.env`, `.streamlit/secrets.toml`
- `data/input`, `data/output`, `data/temp`의 실제 데이터
- `data/modules/` 아래 모듈 데이터(이미지에도 싣지 않는다)
- 로그와 가상환경

`templates/structure_template.xlsb`, `data/capa_simulation.db`,
`data/capa_simulation.duckdb`, `data/equipment_availability.duckdb`는 로컬 실행 자산이다.
테스트나 문서에서 실제 사내 데이터 값을 노출하지 않는다.
`config/bootstrap_display_order.json`과 `builtin_seed.py`에는 합성 `DEMO_*` 값만 두며 실제
제품·고객·공정·설비 식별값을 시드로 추가하지 않는다. 실제 표시순서 CSV는
`data/input/RQ_DISPLAY_ORDER.csv`에 두고 Git에 커밋하지 않는다.

**통합인증(2026-11-02).** 이 저장소는 공개다 — 사내 호스트 · URL · 인증서 · client id · **실제 loginid**(접속 명단 — 사람을 가리킨다) 를 파일 · 시험 · 문서에 적지 않고(예시는
`*.example.invalid` · `demo.*`), **커밋 메시지 · 브랜치 이름에도 적지 않는다**(감시 시험이 보지 못하는 자리라 손 규칙이다). 접속 명단은 C-DEP 환경변수 표와 S3 명단 파일에만 둔다(5장 37) — `config/` 에도 앱 DB 에도 두지 않고 리뷰에 옮기지 않는다. 키 · 인증서 파일
(`*.pem` · `*.key` · `*.p12` · `*.pfx` · `*.cer` · `*.crt` · `*.der` · `*.jks` · `cert/`)은 커밋하지 않는다 — `.gitignore` ·
`.dockerignore` · 배포 ZIP 금지 접미사가 막고 `tests/test_public_repo_hygiene.py` 가 회사 도메인 접미사 · 개인키 표지 · 그
확장자를 감시한다. **사내 오브젝트 스토리지 값(주소 · 버킷 이름 · 프로필 이름 · 네임스페이스)과 사람 이름도 같다**(2026-11-12 사용자 결정) —
문서는 자리표(`<사내 S3 주소>` 꼴), 코드는 환경변수로만 받고(3장 `io/object_storage.py`), 같은 시험이 그 꼴과 옛 연락 메일의 이름 · 도메인을
어느 파일에서도 막는다 — 앱 연락 메일은 환경변수 `CAPA_APP_CONTACT_EMAIL` 로 옮겼고(2026-11-12 보드 답 ⑤-9), 이름은 글자 대신 지문(길이 ·
굴림 해시 · sha256 — 비밀은 아니다)으로 시험에 둔다(조각 잇기는 원문에 이름을 그대로 보인다). 회사 도메인은 사내 빌드가 실제로 쓰는 한 줄(운영 이미지 기반)만 남았다 — 사내 패키지
저장소 주소는 `requirements-company.txt` 의 `--index-url ${CAPA_COMPANY_INDEX_URL}` 이 가리키는 환경변수(사내 PC 사용자 환경변수 · C-DEP
환경변수 표)로 옮겼다(pip · uv 가 요구 사항 파일의 `${이름}` 을 펼친다). 시험 키는 실행 때 만든다(`tests/sso_support.py`). 실제 값은 C-DEP 배포 설정의 환경변수 표에서만 들어오고,
비밀값 `JWT_SECRET_KEY` · S3 명단 키 둘은 앱 프로세스가 기동 때 읽은 뒤 `os.environ` 에서 뺀다(`auth.runtime.start` — 하위 프로세스가 물려받지
않게 할 뿐, 기동 때 환경 사본은 `/proc/<pid>/environ` 에 남고 같은 프로세스 코드는 메모리에 닿는다). 시작 스크립트는 통합인증
값을 앱에 넘기되 결과 파일에는 이름(있음/없음)만 남기고 하위 프로세스에는 비밀값을 넘기지 않는다. 화면 · 로그 · 리뷰에 토큰 ·
state · nonce · 쿠키 값 · 비밀값 · 클레임 값을 싣지 않는다. 모듈은 통합인증 환경변수를 읽지 않는다.

**BigDataQuery CUSTOM 원천 표(2026-11-22).** DB 등록 · 자동 갱신이 부품(`Capa Code`)마다의 `CUSTOM` 을 읽는 둘째 표의 이름(표 또는 스키마.표)도
사내 값이다 — 파일 · 시험 · 문서 · 커밋 메시지 · 브랜치 이름에 적지 않고 환경변수 `CAPA_BDQ_CUSTOM_TABLE` 로만 받는다(사내 PC 사용자
환경변수 — README 4단계 · WebIDE 셸 — `docs/bigdataquery_webide_setup.md` 2-1 · C-DEP 환경변수 표 — 같은 문서 「넣을 환경변수」). 어댑터의 조회문
틀(`CUSTOM_QUERY_TEMPLATE`)에는 자리만 있고, 값은 부를 때마다 읽어 표 이름 꼴 정규식 하나로 거른다(3장 어댑터 · `custom_table_problem`).
시험은 합성 값만 쓴다 — 기본값은 `tests/conftest.py` 의 `DEMO_CUSTOM_TABLE`(`demo_schema.demo_custom`) 하나이고 autouse 가 사내 창에
실제 값이 있어도 덮는다. 두 조회 가짜는 그 상수를 읽어 둘째 조회를 가르고(`from conftest import DEMO_CUSTOM_TABLE`), 꼴 판정 · 공급자가 따로
받은 이름 시험만 따로 지은 합성 이름을 쓴다. 「없음」 갈래는 그 시험이 직접 지운다. 이 이름은 위생 시험이 모르는 사내 값이라 막는 것은 이 손 규칙이다. 값은 화면 · 알림 · 실행 기록 사유 · 로그에 싣지
않는다 — 판정 글 · 풍선 · `AD-04` · 서버 시작 점검 줄은 변수 이름만 싣고, 조회 실패 원문은 어댑터가 값 전체와 점 뒤 끝 조각을 표지
`<CAPA_BDQ_CUSTOM_TABLE>` 로 가린다(`CUSTOM_TABLE_MASK`). 리뷰 · 런북 압축본에도 옮기지 않는다 — 배포 날 확인은 「있음」 · 갈래 낱말 · 수뿐이다.
CUSTOM 원천 끄개(`CAPA_BDQ_CUSTOM_SOURCE`, 2026-11-24 — 7장)는 환경변수로만 둔다 — 화면 단추 · 설정 상자 · DB 칸을 두지 않고, 평소에는
넣지 않으며, 원천 표 모양 탓에 등록이 멈췄을 때 사용자가 정해 C-DEP 환경변수 표(사내 PC · WebIDE 는 그 자리 환경변수)에 `off` 를 넣고
다시 띄운다. 시험은 `tests/conftest.py` autouse 가 끄개를 지워 사내 창에 끄개가 남아도 결과가 같고, 끔 갈래는 그 시험이 직접 넣는다.

앱 코드의 `subprocess` 는 `io/object_storage.py` 한 곳에만 둔다(명령 실행기를 주입받아 시험한다). C-DEP CD 시작
스크립트(`scripts/container_start.py`)의 pip·import 확인은 앱이 서기 전 `scripts/` 몫이라 이 규칙 밖이고, 앱 쪽(어댑터·
Admin)은 그 결과 파일만 읽는다. 커밋되는
`config/object_storage.json` 의 `mode` 는 반드시 `local` 이다. 그 자리도 `subprocess.run` 기본(`close_fds=True` — Windows 에서
핸들을 물려주지 않는다)으로 부르고 `close_fds=False`·`os.system`·`os.spawn*` 은 쓰지 않는다 — Streamlit 1.63 은 듣는 소켓을
상속 가능으로 열어(`starlette_server._bind_socket` 의 `set_inheritable(True)`), 핸들을 물려받은 자식은 앱을 끈 뒤에도 8501 을
쥔다(런북 4-2 「접속이 안 되면」). 모듈은 `subprocess` 를 쓰지 않는다(M10).

**BigDataQuery 로그인 하위의 가벼운 길 끄개(2026-11-23).** 실행 환경변수 `CAPA_BDQ_LOGIN_LIGHT=off`(앞뒤 공백 · 대소문자 무시 —
`CAPA_SHARE_SESSION_TABLES=off` 와 같은 꼴)면 자동 로그인 하위 프로세스가 늘 패키지 전체를 불러온다(3장 `io/bdq_login_child.py` 「가벼운 불러오기 길」).
비밀이 아니라 하위 환경 거르기(`bdq_login.CHILD_WITHHELD_ENVIRONMENT`)에 넣지 않고, 하위 본문이 표준 라이브러리로 `os.environ` 에서 읽는다(시작 스크립트의
시작 로그인도 같은 환경을 넘긴다). C-DEP 는 환경변수 표에 넣고 CI/CD 로 다시 띄운 뒤, 멈춤이 저장돼 있으면 Admin 「BDQ 자동 로그인」 에서 비밀번호를
다시 넣는다(거절 · 결과 표지 없음 · 닿지 못함 3번 · 시도 결과를 적지 못함으로 멈춘 것은 객체에 적혀 재시작을 넘어 남아 시작 로그인이 돌지
않는다 — 보내기 전 끊김으로만 막힌 멈춤(`cut_limit`)은 그 CI/CD 의 시작 로그인이 한 번 해 보아 되면 풀린다, 3장 `io/bdq_login.py`).
