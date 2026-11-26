# AGENTS 2장 — 실행환경과 검증 기준

## 2. 실행환경과 검증 기준

- 운영 호환 Python: **3.10.11 64-bit**
- UI: Streamlit 멀티페이지 앱
- 데이터 처리: pandas(2.2 — 위 끝은 사내 `bigdataquery` 가 받는 범위, `pyproject.toml`)
- 차트: Plotly
- 초기 이관·병행 검증용 Excel 읽기: xlwings, Workbook 숨김·읽기 전용
- 타입 검사: mypy strict
- 린트/포맷: Ruff, target Python 3.10
- 테스트: pytest

변경 후 기본 검증 명령 — Windows 는 PowerShell, 사외(데스크탑 WSL)는 bash 로 같은 네 관문을 돈다. 사내가 배포 확인 때 치는
꼴은 `docs/internal_update_runbook.md` 4-3 의 `uv run --no-sync python -m …` 이다.

Windows(PowerShell):

```powershell
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest
```

사외(데스크탑 WSL, bash):

```bash
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
.venv/bin/python -m pytest
```

사외 개발 자리는 데스크탑 WSL 하나다(2026-10-13 사용자 결정 — 서피스와 병행하지 않는다). 환경 준비와
샌드박스에서 걸리는 것은 `docs/wsl_dev_environment.md`.

`mypy`는 `pyproject.toml`의 `files` 설정에 따라 `app.py`·`app_pages/`·
`src/capa_simulation/`·`tests/`·`scripts/`를 모두 strict 로 검사한다.

- `tests/` 에는 `__init__.py` 를 두지 않는다. 넣으면 pytest 가 `tests/` 대신 저장소 루트를
  `sys.path` 에 넣어 테스트끼리의 맨이름 import(`from test_equipment_availability import ...`)가
  죽는다. `scripts/` 에도 없다. 그래서 mypy 는 두 폴더의 모듈을 `test_dashboard`·
  `compact_duckdb` 같은 맨이름으로 보고, overrides 의 `module` 도 그 이름으로 적는다
  (`tests.*` 는 아무것도 잡지 않고, `test_*` 같은 접두 와일드카드는 mypy 가 거절한다).
- `mypy_path = "tests, scripts"` 는 테스트가 `scripts/` 모듈을 맨이름으로 부르는 것을 파일
  하나만 검사할 때도 찾게 한다. 상대경로라 저장소 루트에서 돌린다.
- 테스트에서 끄는 오류 코드는 pandas-stubs 가 `df.loc[행, 열]` 한 칸을 열두 갈래 합집합으로
  돌려줘 생기는 `operator` 하나이고, 그 자리가 있는 모듈 셋에만 건다. `arg-type`·
  `typeddict-item`·`index` 는 끄지 않는다 — 테스트가 계약을 어긴 값을 굳히는 실제 결손이
  그 코드로 잡힌다. 마찰은 코드로 푼다: `**dict` 언팩은 `TypedDict`, `st.column_config`
  합집합은 `type` 키로 좁히기, AppTest 노드는 `app.markdown` 같은 타입 있는 접근자나
  `isinstance(node, Caption)`, `.loc[r, c]` 를 숫자로 볼 때는 변환 없이 비교(숫자인지까지 본다).
- 계약을 **일부러** 어기는 입력(검증 경로 시험)만 그 줄에 `# type: ignore[코드]` 를 단다.
- 시험은 사내 Windows 4관문에서도 돈다 — 사외 Linux 에서는 드러나지 않는 열한 가지(사내 리뷰 `202610271800` 발견 2 에서 16개,
  `202611041000` 발견 2 에서 9개, `202611111500` 발견 1 · 2 에서 7개가 깨졌다). ① 경로를 글자로 견줄 때는 `relative_to(...).as_posix()` 로 짓는다 — `str(Path)`·f-문자열은 Windows 에서 `\` 로
  잇는다(실패 메시지에만 쓰는 글은 그대로 둬도 된다). 스크립트가 경로를 OS 꼴로 찍으면 기대도 같은 상수로 짓는다.
  `str(경로.relative_to(…))` 는 그물이 막는다(`tests/test_js_runner.py`).
  ② JS 를 돌리는 시험은 모두 `tests/js_runner.py`(`run_js_json` · `run_js` · `need_js_runtime`)를 지난다 — 스크립트는 임시
  `.cjs` 파일, 자료는 표준 입력이다. Windows 명령줄은 32,767자를 넘으면 `WinError 206` 으로 뜨지도 못한다(자산 파일 전체·
  경우 표를 실은 인자가 넘었다). `node -e`·따로 찾는 `shutil.which("node")` 는 그물이 막고(`tests/test_js_runner.py`),
  `tests/conftest.py` 가 모든 자식 프로세스 명령줄을 Windows 가 짓는 꼴로 재어 상한에 닿으면 Linux 에서도 실패시킨다.
  문법만 읽는 길은 `check_js_module`(임시 `.mjs` + `node --check`)이고, `tests/test_component_js_syntax.py` 가 등록되는 컴포넌트
  JS(서식 · 다른 자산을 앞에 붙인 등록 글 그대로 — 등록 모듈을 기록 대역 아래에서 새로 읽어 받는다)와 자산 · static JS 파일을
  모두 읽는다 — 합침이 남긴 겹친 선언(알림 칸 맨 위 `const DIALOG` 두 줄, 2026-11-07)을 구획 시험은 놓쳤다.
  ③ 권한 비트(0600·0700)는
  담는 파일 체계에서만 본다 — Windows 의 chmod 는 읽기 전용 표시 하나만 바꾼다(공용 픽스처 `tests/conftest.py` 의
  `keeps_permission_bits` — 권한 비트를 단언하는 시험은 모두 받는다, Linux CI 에서는 건너뛰지 않고 실패). ③-1 시험은 운영 DB 자리(저장소
  `data/` · 운영 DB 와 같은 파일 · git 작업 트리 안 — `settings.is_operational_database_place`, 시험이 갈아끼우기 전 저장소 경로로)를 열지 않는다 —
  `tests/conftest.py` 가 같은 프로세스의 `duckdb.connect` 를 지켜 열지 않고 멈추고 그 시험을 실패로 바꾼다(여는 쪽이 예외를 삼켜도 끝에서
  실패). 사내 관문이 운영 저장소에서 돈다(2026-11-12 사용자 답 ⑤-6 (가)). 내보내기 임시 자리처럼 `settings.DATA_DIR` 아래를 쓰는 길은 그 칸을
  `tmp_path` 로 돌린다. 하위 프로세스는 문지기를 지나지 않아 세션 끝의 「저장소 DB 를 새로 만들었으면 실패」 가 받친다. 운영 DB 옆 사이드카도
  읽지 않는다 — 이관 `init` 을 한 사내 PC 에는 넘긴 표지(`sync_generation.json` 의 `handed_over_utc`)가 있어 읽으면 그 PC 에서만 `SY-04` 와
  해소 표지가 선다. 동기화 판정은 그 자리를 import 때 이름(`sync_boot.DUCKDB_PATH`)으로 쥐어 `settings.DUCKDB_PATH` 를 바꿔도 따라오지
  않으므로 `tests/conftest.py` 의 `_without_handed_over_mark` 가 그 이름을 tmp 로 돌린다(그물 `tests/test_sync_boot.py`). ④ 사내에만 깔린 패키지(`bigdataquery`)의 있음·없음으로
  화면이 갈리면 판정 함수를 갈아 끼워 두 경우를 다 본다 — 사외에는 없고 사내에는 있다. ⑤ 대소문자만 다른 두 뿌리
  (`modules/`·`Modules/`)를 실제 폴더로 만들면 NTFS 는 먼저 만든 쪽 하나로 접고 git 도 그 철자로 적는다 — 철자를 글자로
  견주지 말고 git 이 적은 철자를 읽는다(`tests/test_apply_deploy_package.py` 의 `_tracked_spelling`). 파일을 만들지 않는 순수
  목록 시험은 그대로 둔다. ⑥ 프레임을 쌓는 동작(끌기 자동 스크롤)은 시간으로 기다리지 않고 조건으로 기다린다 — Windows
  타이머 해상도(약 15.6ms)에서는 같은 시간에 프레임이 훨씬 적다(`tests/edit_grid_node.py` 의 `until`, 프레임 간격 16ms 를
  매개값으로 함께 돌린다). 같은 단조 시계를 두 번 읽어 견주는 판정도 두 읽기가 같은 눈금이 될 수 있다 — 시각 간격 0
  (`QUIET_SECONDS` 0 등)에 기대는 시험은 Linux 와 다른 갈래로 간다(`tests/test_object_sync_worker.py` 의 「저장이 깨운다」 는
  두 DB 를 깨끗하게 하고 시작한다, 리뷰 `202611111500` 발견 1). ⑦ 자식 프로세스 환경을 좁히는 시험은 `tests/child_env.py` 의 `narrow_child_env` 로 만든다 — Windows 파이썬은
  `SYSTEMROOT` 없이 첫 줄에서 죽는다. ⑧ 스크립트의 `sys.stderr.reconfigure(encoding="utf-8")` 는 시험 안에서 pytest 붙잡기
  파일을 건드린다 — `errors` 가 strict 로 돌아가면 fd 2 에 들어온 현지 인코딩 한 바이트가 그 뒤 시험을 모두 setup 에서 깨뜨리므로
  `tests/capture_guard.py` 가 막는다(리뷰 `202611060842` 발견 1). 표준 오류에 현지 언어가 나갈 데몬 스레드 서버는 끊긴 연결을 조용히
  넘기고 그 밖은 ASCII 한 줄로 알린다(`scripts/s3_mock_store.py` 의 `handle_error`). ⑨ 남이 쥔 포트의 뜻이 다르다 — Linux 는
  V6ONLY 0 인 `::` 하나가 IPv4 와일드카드까지 막지만 사내 Windows 에서는 임시 응답이 그 포트를 다시 잡았다(기제 미확인).
  「포트를 못 잡는다」 를 단언하는 시험은 Linux 만 본다(`tests/test_container_stage.py`, 리뷰 `202611111500` 발견 1).
  ⑩ 사내 PC 창에는 프록시 환경변수가 있고 `NO_PROXY` 에 `127.0.0.1` 이 없을 수 있다 — 루프백 시험 서버로 가는 맨
  `urllib.request.urlopen` 이 프록시로 가 403 을 받는다. 공용 `tests/conftest.py` 가 세션 처음과 시험마다
  (`_loopback_skips_proxy_from_the_start` · `_loopback_skips_proxy` — 모듈 · 세션 범위 준비가 띄우는 하위 프로세스도 받는다) `NO_PROXY` ·
  `no_proxy` 에 루프백 셋을 붙이고, 루프백 요청기는 `ProxyHandler({})` 로 짓는다(`tests/test_s3_mock_store.py`, 리뷰
  `202611111500` 발견 2). 시험 · 스크립트의 맨 `urlopen` · `urlretrieve` 는 그물 `tests/test_no_bare_urlopen.py` 가 막는다(앱 코드는
  보지 않는다 — 바깥 주소로 가는 앱 요청은 사내 프록시를 따라야 할 수 있다).
  ⑪ 텍스트 입출력은 인코딩을 늘 적는다 — 빼면 그 PC 의 로캘(사내 cp949 · 사외 CI Windows cp1252)로 풀어 UTF-8 한글 문서가
  `UnicodeDecodeError` 로 깨진다(`tests/test_grade_name_net.py`, 리뷰 `202611181400` 사외요청 1). 저장소 · 사용자 파일은 `encoding="utf-8"`,
  자식 프로세스(`text=True`)는 자식이 쓰는 인코딩이다 — 파이썬 자식은 환경에 `PYTHONIOENCODING=utf-8` 을 주고 `encoding="utf-8"`
  (CI Windows 작업은 그 변수를 물려주고 사내 창은 아닐 수 있어 짝을 맞춘다), 환경을 일부러 좁히거나(⑦) 물려받기를 보는 시험은
  환경을 그대로 두고 `encoding="utf-8", errors="replace"`, git 은 `"utf-8"`, 앱의 aws 실행기는 로캘 그대로 `"locale"`(파이썬 3.10 이 `text=True` 에 쓰는 값). 그물
  `tests/test_explicit_text_encoding.py` 가 `app.py` · `capa_server.py` · `app_pages/` · `src/` · `scripts/` · `tests/` 를 AST 로
  훑는다 — 일부러 뺀 자리는 그 파일의 `ALLOWED` 에 까닭과 함께 두고, 자리가 사라지면 실패한다. ruff `PLW1514` 는 preview 이고
  `(폴더 / 이름).read_text()` · 자식 프로세스를 보지 못해 이 그물이 대신한다. 사외 CI 의 둘째 작업
  `windows-pytest`(`windows-latest` · Linux 작업과 같은 설치 · pytest 만)가 이 열한 가지를 사내보다 먼저 보인다 — 작업 단위
  `continue-on-error` 라 빨개도 워크플로는 초록이고 판정은 Linux 조각을 모은 `verify-result` 다(2026-11-01 사용자 결정 A7 「처음엔 막지 않음」 — 두어
  판 본 뒤 굳힐지 다시 묻는다). 시험은 두 작업 모두 같은 수의 조각으로 돈다(`scripts/run_test_shard.py`) — 러너 한 대로는 시간 안에 끝나지
  못해 2026-10-25 뒤로 초록도 빨강도 나오지 않았다. 같은 번호 조각은 두 OS 에서 같은 파일이다. 판정은 밀려 취소된 판에서 빠지고(`!cancelled()` — `always()` 면 같은 커밋에 빨강과 초록이 함께 남는다) 조각이 끊기면 빨강이다 — 시험 단계 상한을 작업 상한보다 낮게 두어 시간 초과가 취소와 섞이지 않는다. 그 칸이 빨가면 이 열한 가지부터 본다. 러너 로캘은 영어라
  사내 한국어 로캘(cp949 · 한글 오류 글)은 흉내 내지 못한다. 계약은 `tests/test_ci_workflow.py` · `tests/test_run_test_shard.py`.

(Windows 기준 — WSL 샌드박스 사정은 `docs/wsl_dev_environment.md` 2장.) Codex에서 `.venv\Scripts\python.exe`를 샌드박스 안에서 실행하면 가상환경이 참조하는
사용자 프로필의 Python 3.10 실행 파일 접근이 차단되어 `Unable to create process` 또는
`Access is denied`가 발생할 수 있다. 이는 가상환경 손상이 아니므로 `.venv`를 재생성하지
말고 동일한 명령을 `require_escalated`로 다시 실행한다. Streamlit 버전별 스킬 탐색기도
프로젝트 `.venv`와 탐색기 스크립트의 정확한 조합으로 승인된 샌드박스 외 실행을 사용한다.

Streamlit 페이지나 상태를 변경했다면 `streamlit.testing.v1.AppTest` 또는 실제 브라우저로
해당 페이지 진입, 수정, 페이지 왕복과 예외 여부를 추가 검증한다.

개발 환경에서 걸리는 것:

- pytest 를 여럿 동시에 돌릴 때는 각자 전용 `--basetemp` 를 준다(조각 실행기는 `--basetemp-root` — git 작업 트리 안이면 멈추고, 보존 정책 `failed` 를
  함께 걸어 통과한 시험의 임시 파일을 바로 지운다(아래 줄), 기본 보존이면 조각마다 GB 단위) — 기본 임시 폴더(`pytest-of-<사용자>/pytest-N`)는 오래된 차례를 지워 서로의 폴더를
  지울 수 있다. 임시 공간이 차서 전체 pytest 가 `OSError: [Errno 28]` 로 멈추면 코드
  결함이 아니다 — 끝난 작업의 찌꺼기만 지우고 다시 돌린다.
- 보존 정책 `failed`(`-o tmp_path_retention_policy=failed`)는 call 단계가 통과하지 못한 시험(실패 · 본문 건너뜀 · xfail)의 `tmp_path` 만
  남긴다 — call 이 통과한 시험(정리 오류가 나도)과 call 까지 못 간 시험(준비 오류)의 것은 그 자리에서 지우고 같은 이름(시험 이름 앞 30자 +
  번호)을 다음 시험에 다시 내준다. 경로를 키로 쓰는 프로세스 캐시(`get_scenario_repository` · `get_equipment_repository` · 경로와 쓰기
  세대만 키인 `st.cache_data`)가 그 경로에 앞 시험 것을 돌려줘 시험이 깨진다 — `tests/conftest.py` 의 `pytest_fixture_post_finalizer` 가
  지워진 자리에 빈 폴더를 다시 두어 번호를 붙잡는다(다른 준비의 정리 오류 · `request.getfixturevalue` 로 늦게 받은 `tmp_path` ·
  준비 오류도 — `tests/test_tmp_path_number_hold.py`).
- 샌드박스 안에서 `TMPDIR` 이 비면 파이썬 `tempfile` 은 실패하지 않고 저장소 루트로 내려간다 — 오류로 드러나지 않으니
  `echo $TMPDIR` 로 본다(`docs/wsl_dev_environment.md` 2장).
- UPEH 가정 계획 1회 시간은 `scripts/benchmark_upeh_assumption.py --data-dir <사본 폴더>` 로 잰다(사내 런북 6-3 b — 1초를
  넘으면 % 입력을 「적용」 단추 폼으로 바꾼다. 다섯 목표 한 벌로 잰다 — 가정 계획을 세우는 화면은 공정 Capa 상세(목표
  하나)뿐이라 잰 값은 상한이다, 2026-11-01 사용자 결정으로 잴 길은 그대로). 합성 시드와 샘플 fleet 은 공정이 겹치지 않아 사외에서는 뜻 있는 값이 없다.
- HOME 단계별 소요시간은 `scripts/benchmark_home.py` 로 잰다. 화면에서 봐야 할 때만 세션 키 `dashboard_show_performance`
  (`components/home_rendering.HOME_PERFORMANCE_KEY`)를 켠다 — 개발용 계측이 모든 사용자가 늘 보는 자리를 차지하지 않게
  사이드바 토글은 두지 않는다.

### 명령과 보조 스크립트

Python은 **3.10.11 64-bit** 고정이고 실행은 `.venv`를 쓴다. 아래 PowerShell 블록은 Windows 꼴이다(사내가 배포 확인 때
치는 꼴은 런북 4-3 의 `uv run --no-sync python -m …`).

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501   # 앱 실행
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy                      # strict, app.py·app_pages·src·tests·scripts
.\.venv\Scripts\python.exe -m pytest
```

단일 테스트: `.\.venv\Scripts\python.exe -m pytest tests/test_home_page.py::test_home_renders_summary_dashboard_from_the_builtin_seed`

사외 개발 자리는 데스크탑 WSL 하나다(2026-10-13) — 같은 명령을 bash 로 친다. 환경 준비·앱 띄우기·배포 절차는
`docs/wsl_dev_environment.md`.

```bash
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
.venv/bin/python -m pytest
.venv/bin/python -m pytest tests/test_home_page.py::test_home_renders_summary_dashboard_from_the_builtin_seed
```

사외 앱은 사용자가 Claude 밖 tmux 창에서 `docs/wsl_dev_environment.md` 3장의 실행 줄로 띄운다 — 포트는 늘 적는다.

보조 스크립트: `scripts/inspect_wf_division.py`·`scripts/inspect_top_remigration.py`
(사내 실데이터의 `WF 구분`·재이관 전제를 **읽기 전용**으로 재는 것. 값은 찍지 않고
개수만 보고한다), `scripts/audit_top_remigration.py`(`0026` 적용 뒤 이관 결과의 오염·누락을
**읽기 전용**으로 점검), `scripts/inspect_real_data_checks.py`(실데이터로만 답이 나오는 확인 — 기존 결과
대조 분포·원천 `RQ_REQB` 소요기준·설비 DB(공식 설비 시나리오 — 8-4 에 `0027` 이관 확인과 가정 배치 차이·옛 코드 흔적(설비 `0031`))·BigDataQuery(블록 `bdq` — 런북은 이 블록을 부르지 않는다. 꼭 필요하면 정본 개발 에이전트가 사용자에게 먼저 요청하고 사용자가 직접 돌린다)·「지금대로」 결정의 유병률(8-10 센서스 — 리비전 표 객체 칸의 값 종류 `8-10T` 포함)·기준 정보 편집 표 크기(큰 표 상한 대비 — 8-11)·빈 값 멈춤의 꼴(8-12 — 남는 경로의 빈 칸으로 대당 Capa 가 멈춘 리비전)을 **읽기 전용**으로
재어 집계만 찍고, 끝에 리뷰 압축본에 옮길 「전송용 요약」(짧은 키와 수 + 확인 코드)을 찍는다. 사내 런북 8장이 배포마다
부르고 — 사내 DB 를 여는 이 스크립트들(아래 6-3 · 화면 확인 포함)은 사용자가 Claude 밖의 별도 PowerShell 창에서 치고 사내
에이전트는 `--output` 파일만 옮긴다(런북 0장, 2026-11-11) — 정본 개발 에이전트는 받은 압축본에 `--check-summary <파일>` 을 돌려 옮겨 적은 오타를 잡는다),
`scripts/inspect_db_counts.py`(사내 런북 7-8 개수 세기 — 두 DB 의 표마다 행 수 · Space 모듈 묶음 · 파일 크기와 생산 계획 그리드 두 표의 크기를
**읽기 전용**으로 재어 한 줄씩 찍는다. 앞 세 줄은 옛 `python -c` 세 줄과 같은 꼴이고, 사용자가 별도 창에서 `--output` 으로 돌린다),
`scripts/inspect_source_csv.py`(원천 CSV 견줌 — 원천 웹에서 받은 시나리오 CSV 를 DB 등록 탭 「CSV 파일」 길과 같은 함수로 읽어 DB 사본에
같은 코드로 받아 둔 원천과 견주고 수만 찍는다. **읽기 전용**이고 `--database` 사본만 받으며 운영 DB 자리는 거절한다 — 사내는 사용자가 별도 창에서 돌린다),
`scripts/inspect_revision_calculations.py`(사내 런북 6-3 a 사본 E2E — 저장된
모든 리비전의 대당 Capa → 소요대수 → 확보율을 앱과 같은 길로 **읽기 전용**으로 다시 돌려 상태·개수만
찍는다. `--database` 는 기본값이 없어 늘 DB 사본을 주고, 운영 DB 자리(같은 파일·저장소 `data/` 아래·git 저장소 안 —
`settings.is_operational_database_place`)는 거절한다),
`scripts/check_deploy_screens.py`(사내 런북
7장 화면 확인 — 별도 포트에 앱을 띄워 저장소 밖 Playwright·깔린 Chrome 으로 보고 개수·있음/없음만
찍는다. 항목은 함수 하나 + `ITEMS` 한 줄), `scripts/benchmark_home.py`(HOME 단계별 성능 — 기본은 합성
표본이고, `--data-dir <사본 폴더>` 를 주면 실 DB 사본으로 잰다. 사내 런북 6-3 b 이며 같은 판정으로 저장소 안은
받지 않는다), `scripts/benchmark_upeh_assumption.py`(UPEH 가정 계획 1회 시간 — 사내 런북 6-3 b 에 이어,
`--data-dir <사본 폴더>` 만 받고 같은 판정으로 저장소 안은 거절), `scripts/validate_duckdb_persistence.py`
(영속성 통합 검증 — Windows·Excel·`templates/structure_template.xlsb` 가 있어야 돈다),
`scripts/generate_sample_core_data.py`(합성 Core Data 생성),
`scripts/generate_review_sample.py`(검수용 합성 샘플 — 시뮬레이션 DB·설비 DB·`--modules` 모듈 견본을 저장소 밖 뿌리에 만든다. 부품
`review_sample_*.py`, 문서 `docs/review_sample.md`. 가이드 예시판 시드도 이것이다 — git 작업 트리 안은 거절),
`scripts/sso_mock_idp.py`(개발용 가짜 통합인증 IdP — 키를 메모리에만 만들고 form_post 로 id_token 을 보내 `capa_server.py` 의 로그인을
끝까지 돌린다. 운영 `APP_ENV`·루프백 아닌 주소에서는 거절, `docs/sso_setup.md` 8장),
`scripts/s3_mock_store.py`(개발 · 시험용 가짜 S3 — 서명을 검증하며 객체 GET · PUT · HEAD · DELETE · 목록을 메모리로 받는다. 실제 `aws` 1.46.3 도 붙는다 — 접속 명단 · DB 동기화 시험, `docs/sso_setup.md` 8장, 루프백만),
`scripts/container_start.py`(C-DEP 이미지 `CMD` — 맨 앞에서 포트를 잡고(임시 응답 `container_stage.py`) 프로필 · 점검 · 설치 · `managed` 면 두 DB 받기 뒤 앱이 된다. 어떤 실패에도 앱을 띄우되 DB 받기만 예외다 — `docs/objectstore_setup.md`),
`scripts/sync_object_storage.py`(두 DB 정본 도구 — 사내 PC 의 이관 `init` · 사본 `fetch-copy` · 세대 `generations` · `rollback`, 컨테이너의 `boot-pull`.
`rollback` · `init` · `fetch-copy` · `prune` 은 끝에 감사 조각 한 줄을 버킷 `audit/v1/tool/` 에 올리고 `audit-list` 는 날짜 · 달의 감사 조각 수만 찍는다),
`scripts/build_page_guide.py`(따라하기 가이드 생성기 — 앱 사본을 `127.0.0.1`·8552 부터에 띄워 찍고 원고·사내 덮어쓰기와 한 파일
HTML 로 묶는다. `--example` 은 `git archive` 사본 + 검수용 합성 샘플 시드 `scripts/generate_review_sample.py`, `--internal`(사내판 —
2026-11-02 부터 쉼)은 런북 6-3 사본 트리에서만 돌고 사본 두 DB 지문이 앞뒤로 같아야 한다. 결과는 늘 저장소 밖 `--dist` — 부품은 `page_guide_core.py`·
`page_guide_capture.py`·`page_guide_helpers.js`), `scripts/check_page_guide.py`(가이드 점검기 — 덮어쓰기·매개값·촬영 결과를
뼈대에 대 보고 리뷰 한 줄을 낸다. 앱·브라우저 없이 돈다. `--accepted` 는 사내 검수 마친 판과 견줘 바뀐 자리만 `바뀜 n/N` 으로 —
못 읽으면 `바뀜 na` 로 멈추지 않는다 — `--accept` 는 검수 끝 뒤 그 판을 쓴다).
`scripts/build_deploy_package.py`(사내 배포 ZIP — 배포 세트 규칙과 금지 파일 검사를 갖고, 커밋하지 않은 수정이 있거나 HEAD 가
`origin/main` 과 다르면 멈춘다 — `--no-tag` 시험 빌드는 알리기만 한다. 같은 stamp 의 태그가 이미 있어도, 런북 7장 압축본 기대의 화면 확인 수가
`check_deploy_screens.py` 항목 수와 달라도 ZIP 을 쓰기 전에 멈춘다).
`scripts/build_site_index.py`(GitHub Pages 자료 목록 — `site/catalog.json` 으로 뿌리 `index.html` 을 쓴다, `--check` 는 다르면 실패).
`scripts/build_module_index.py`(모듈 색인 — 추적 소스 모듈(app.py · app_pages/ · src/capa_simulation/, __init__ 뺌)의 경로 전체를 `docs/reference/module_index.md` 로 쓴다, `--check` 는 다르면 실패. 모듈을 더하거나 옮기거나 지우면 돌려 함께 커밋한다).
`scripts/run_test_shard.py`(CI 시험 조각 실행기 — 시험 파일을 크기로 고르게 N 조각으로 나눠 한 조각을 `pytest -q` 로 돈다, 두 CI 작업이 같은 수로 부른다).
`scripts/new_module.py`(모듈 뼈대 — 새 모듈은 앱 관리자 승인 뒤), `scripts/check_module.py`(선언·정적 규칙·ruff·
자기 시험 — 사내 런북 4-5 는 `git archive` 사본 트리에서 돌린다, 끝에 「전송용 요약」 한 줄), `scripts/module_test_runner.py`(check_module 이 부르는 모듈
시험 감시 러너 — 코어 `data/` 접근·모듈 폴더 쓰기를 실패로, AppTest import 길을 앱과 같게). 정적 규칙 부품은
`scripts/module_check_rules.py` 이고 규칙 번호·창구 이름·예시·점검 출력은 `tests/test_module_guide_sync.py` 가 지침서와 맞댄다.

`mypy`는 `tests/`·`scripts/`까지 같은 strict 로 검사한다. 테스트에서 끄는 것은 pandas 스칼라
합집합 마찰인 `operator` 하나뿐이고 모듈 셋으로 좁혀 두었다(`pyproject.toml` 의 overrides).
파일 하나만 볼 때도 저장소 루트에서 돌린다(`mypy_path` 가 상대경로다). Streamlit 화면·상태를
바꿨으면 `streamlit.testing.v1.AppTest` 또는 실제 브라우저로 페이지 진입·수정·왕복을 추가
검증한다.

DuckDB 파일은 프로세스 배타 잠금이다. 앱 서버가 떠 있으면 같은 DB를 여는 스크립트·테스트가
`duckdb.IOException`으로 실패한다 — 가상환경 손상이 아니다.
