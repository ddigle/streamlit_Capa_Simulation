# HANDOFF — 2026-09-06 전역 리팩토링 세션

이 문서는 인수인계용 요약이다. 상세 근거와 측정치는 `docs/TODO.md` §3-6 에 있고,
개발 규칙은 `AGENTS.md` 가 정본이다. 여기서는 **지금 상태**와 **다음에 할 일**만 적는다.

## 1. 현재 상태

| 항목 | 값 |
|---|---|
| 브랜치 | `main` (작업 트리 깨끗) |
| 원격 | `origin/main` = `06bb8ad` — 로컬과 동일, 미푸시 커밋 0 |
| 검증 | ruff format·check 통과 / mypy 112 파일 이상 없음 / pytest 전체 통과 |
| 배포본 | `C:\Dev\Streamlit_Project_Move` 재생성 (150 파일, 금지 항목 0, 해시 불일치 0) |
| ZIP | `C:\Dev\Streamlit_Project_Dummyfile\202609061010.zip` (399,309 bytes, 엔트리 150) |
| 메일 | 2026-09-06 발송 완료. 수신 `hoyeon.jeon@samsung.com`, 제목 `202609061010`, 보낸 편지함에서 확인함 |

ZIP 은 `06bb8ad` 커밋의 소스와 동일하다. `CLAUDE.md` 는 추적되지 않은 파일로 남아 있다.

## 2. 이번 세션에 한 일

사용자 지시는 **"디자인 개선점 및 데이터 구조 효율화 검토. 이미 효율적인 것은 굳이 바꾸지
말고 명백히 문제나 비효율이 있는 부분만"** 이었다. 9개 축으로 81건을 검출하고 두 렌즈
("바꿀 이유가 정말 있나" / "고치면 뭐가 깨지나")로 반증해 57건이 남았다.

### A. 바로 고친 것 (8배치)

| 커밋 | 내용 | 실측 효과 |
|---|---|---|
| `e6f859c` | 문서 드리프트 7건 정정 (캐시 키·편집 14표·HOME 토글·Pack Code 모순) | — |
| `1d8e000` | 테스트 위생 (cwd 상대경로, 설정 경로 복원 `conftest.py`) | bare `pytest` 수집 오류 0 |
| `53c82db` | 예외 경계 통일 — `duckdb.IOException` 은 `OSError` 가 아니다 | 회귀 테스트 2건 |
| `1c3e3ca` | 적재 경로 벡터화·dtype 가드 | RQ 16표 **13.6s → 0.86s** |
| `48576b2` | Plotly 행 루프 `add_shape` → 일괄 주입 | 1,140행 **840s → 0.48s** |
| `ceb34a0` | 계산 페이지의 버려지는 rerun 비용 제거 | 숨은 탭 편집표 519~793ms |
| `69970b7` | HOME 월 슬라이스를 캐시 안으로 | 적중 시 27~36ms 낭비 제거 |
| `080a631` | CSV 의 U+00A0(VLOOKUP 어긋남), 월 정규화 복제 5곳 | — |

### B. 결정이 필요했던 항목 (사용자 승인 순서대로 하나씩)

| 항목 | 커밋 | 결과 |
|---|---|---|
| **B7** rgba 색 리터럴 검사 확장 | `0272fa8` | 남은 5곳을 `tokens.TRANSPARENT`·`HIT_TARGET` 으로. 검사에 `rgba?\(` 추가. 화면 값 변화 없음 |
| **B8** 재공 현황 빈 가용대수 | `d9c7472` | 설비 DB 가 비면 빨간 오류 대신 `st.info` 안내 후 정지. 결함을 가리던 테스트 Fake 도 수정 |
| **B5** 공정별 Capa STEP 탭 | `efb98e1` | 요약·목록을 내용 토큰 캐시로. 기본 탭 warm rerun **2,226 → 1,147ms** |
| **B2** Static Capa 5페이지 캐시 키 | `a34996c` | 프레임 해시 → 시나리오 키. 확보율 warm rerun 1,298~1,407 → 1,048~1,100ms, Static Capa 331 → 122ms |
| **B1** DB 연결 상주 → **축소판** | `299483c` | 상시 앵커는 보류하고 rerun 동안만 잡는 `pinned_connections`. 사이드바+HOME **386 → 266ms** |
| **B4** 시나리오 관리 탭 | `8956419` | 세 탭을 항상 그려 폼 입력값 유실 해결. 탭 전환 rerun 제거 |

### 이번 세션에서 확정한 규칙 두 가지

1. **숨은 탭에서도 입력 위젯은 항상 그리고, 계산·표·차트만 건너뛴다.**
   본문을 통째로 건너뛰면 Streamlit 이 form 입력값을 버린다. B4·B5 가 같은 기준을 쓴다.
   `AGENTS.md` 에 반영돼 있다.
2. **`app.py` 의 DB 핀은 rerun 단위이고 상시 앵커가 아니다.**
   이유는 아래 3절 참조. `AGENTS.md` 영속성 절에 반영돼 있다.

## 3. 다음에 할 일

### 3-1. 남은 B 항목

**B3 — `create_scenario` 의 ref_data 편집 14표 이중 저장 제거** (E7 + E8 묶음)

- 전체 행의 33.7% 가 rev1 사본과 완전히 동일하고 읽는 코드가 없다. 재구축하면 34.09 → 24.92MB.
- **새 세션에서 단독으로, DB 백업 후 진행할 것.** 이번 B 항목 중 유일하게 저장 구조를 바꾸고
  DB 파일을 재구축한다.
- 착수 전 확인: 신규 마이그레이션 번호는 시뮬레이션 DB `0015`, 설비 DB `0006` 이다
  (결번 2·3 은 이미 태웠다). **기존 SQL 마이그레이션은 체크섬 때문에 절대 수정하지 않는다.**
- 채택하면 `scripts/compare_legacy_results.py` 의 대조 기준을 rev1 로 바꿔야 한다.

**B6 — grouped/hierarchical 표 컴포넌트의 남은 복제 통합**

- **보류를 권한다.** 실행 시간도 화면 결함도 없다. 이번 검토 지시("이미 효율적인 건 건드리지
  말 것")에 맞지 않는다. 남은 것은 `_classification_widths`·`go.Table` 조립·반복 접두 생략
  정도이며 순수 유지보수 비용이다.

### 3-2. 상시 앵커 연결 재검토 (B1 후속)

클라우드 배치 전환이 확정되면 다시 판단한다. 상시 앵커는 rerun 마다 48ms 를 9~12ms 로
줄이지만, 앱이 켜진 내내 DB 파일을 잠근다. **배치가 같은 DuckDB 파일을 갱신하는 구조라면
불리하다** — Windows 는 파일 교체가 실패하고, Linux 는 앱이 옛 inode 를 계속 읽는다.

판단에 필요한 정보 세 가지:

1. 배치가 앱과 같은 파일을 쓰는가, 별도 파일을 만들어 교체하는가.
2. 교체 방식이 덮어쓰기인가 rename 인가.
3. 앱과 배치가 같은 머신에서 도는가.

MotherDuck 같은 서버형 DB 로 가면 연결 유지가 표준이라 유리하지만, 그때는 저장소 계층을
다시 쓰게 되므로 지금의 핀 코드가 그대로 가지는 않는다.

### 3-3. 기존 TODO §4 의 진행 순서 (이번 세션과 무관하게 계속 유효)

1. **`Pack Code` 업무 키 승격** — 현재는 contract 와 코드에만 있다. 사내 실데이터 전환 전에
   넣어야 안전망이 된다.
2. **기존 결과 대조를 실데이터로** — 지금의 0.0000% 일치는 산식이 옳다는 근거가 아니라
   합성 샘플의 내부 일관성이다(4절 참조).
3. 누락 기준정보·입력 검증 화면 마무리.
4. 결과 Excel 다운로드와 계산 실행 이력.

### 3-4. 사내 PC 에서 확인이 필요한 것

`equipment_repository` 의 `contract_version < 3` 경로 106줄은 "도달 불가" 가 아니다.
08-28·08-31 배포 ZIP 으로 사내에 v1/v2 리비전이 남아 있을 수 있다. 아래를 확인하기 전에는
손대지 않는다.

```sql
SELECT equipment_contract_version, COUNT(*) FROM equipment_ops.revision GROUP BY 1
```

## 4. 인수인계 시 주의할 점

- **로컬 데이터는 전부 합성 샘플이다.** `data/input/Core_Data.csv` 와 DuckDB 는
  `scripts/generate_sample_core_data.py` 의 `PROCESS_SPECS` 리터럴이 만든 것이다.
  관측으로 업무 구조를 판단하면 안 된다. 이 세션에서도 그렇게 잘못 보고한 적이 있다.
- **효율 주장은 실측 없이 채택하지 않는다.** 이번에 09-04 기준선의 확정 항목 두 건
  (`server.port` 부재, 스냅샷 캐시 `max_entries`)이 실측에서 뒤집혔다.
- **측정은 교차 A/B 로 한다.** 이 기계는 같은 코드가 641ms 와 1,400ms 를 오갈 만큼 흔들린다.
  `git stash` 로 코드 상태를 번갈아 바꿔 같은 기계 상태에서 비교했다.
- **배포 타이밍은 사용자가 정한다.** 코드 변경을 끝냈다고 배포본·메일을 만들지 않는다.
  push 도 배포 흐름의 일부다.
- **메일 발송 경로는 Claude in Chrome + `outlook.live.com` 뿐이다.** 이 PC 의 Microsoft 365 는
  설치 구성에서 Outlook 이 제외돼 있어 COM 발신이 불가능하다. 확장은 Chrome `Profile 1` 에 있다.
- 배포 세트 규칙: `git ls-files` 전체 + `data/input/RQ_DISPLAY_ORDER.csv`. `tests/`·`scripts/`도
  포함한다(사내에서 단독 운영·검증할 수 있게). 의존성은 `pyproject.toml` 하나만 본다. **이 문서를 커밋하면 배포 ZIP 에도 들어간다.**

---

# HANDOFF — 2026-09-09 S3 동기화 사내 실측 세션

## 5. 현재 상태

사내 PC 에 배포한 버전으로 오브젝트 스토리지 왕복(`init` → `push` → `pull`)이 **성공했다.**
1~4단계 절차(`docs/objectstore_setup.md`)가 실제 환경에서 검증됐다.

사내 환경은 `uv` 로 구성돼 있다. 명령 접두가 개발 PC 와 다르다 — `.\.venv\Scripts\python.exe`
대신 `uv run python`. 스크립트가 `sys.path` 에 `src` 를 직접 넣으므로 프로젝트가 설치돼
있지 않아도 돈다.

## 6. 사내 실측값 (2026-09-09)

| 항목 | 값 |
|---|---|
| `push` 총 시간 | 66초 |
| `pull` 총 시간 | 50초 |
| 시뮬레이션 스냅샷 | 62.6 MiB → 42.8 MiB, 생성 2.88초 |
| 가용설비 스냅샷 | 0.4 MiB → 0.4 MiB, 생성 0.06초 |
| 전송 속도 | 양방향 약 1 MiB/s |
| 체크섬 옵트아웃 | **정상 동작.** `Content-MD5` 오류 없음 — 1순위 위험 해소 |

압축률이 개발 PC(64.3→20.6 MiB, 68% 감소)보다 낮은 32% 인 것은 실제 데이터가 더 촘촘히
차 있어서다. 정상이다.

`aws` CLI v2 는 자체 파이썬을 묶은 exe 라 회당 0.7~1.5초의 기동 비용이 있다. `push` 한 번에
12~16회 뜨므로 66초 중 10~20초는 순수 프로세스 기동이다.

## 7. 이번 세션에 고친 것

### A. 결함 두 건

- **`decision_message` 의 사전 키 충돌.** `PushDecision` 과 `PullDecision` 이 둘 다
  `str, Enum` 이고 `up_to_date`·`remote_empty` 값이 겹쳐, 하나의 사전에 담은 pull 문구가
  push 문구를 덮어썼다. `status` 가 push 판정을 찍는데 "이미 원격 seq N 입니다" 라는 pull
  문장이 나와 사용자가 "받을 게 없다" 로 오해했다. 사전을 둘로 분리했다. **판정 로직은
  멀쩡했고 표시 문자열만 틀렸다.**
- **`sync_state` 등록 경로 불일치.** 저장소는 `database_path.resolve()` 를 들고 있고 부트는
  설정에 적힌 경로를 그대로 넘긴다. 정규화하지 않으면 같은 파일인데 키가 달라 `_update` 가
  조용히 아무 일도 하지 않는다. `_registry_key()` 로 맞췄다.

### B. 앱 → 사이드카 배선 (2단계 첫 조각)

`mark_dirty()` 를 부르는 곳이 스크립트 한 곳뿐이라, **앱에서 리비전을 몇 번 저장해도
사이드카는 `dirty: false` 그대로였고 `push` 가 영원히 "올릴 것 없음" 이었다.**

- `repository.py`·`equipment_repository.py` 의 `_write_transaction` 이 COMMIT 후
  `sync_state.mark_dirty()` 를 부른다.
- `sync_boot.py`(신규) 가 `mode == managed` 일 때만 두 DB 를 등록한다. 설정을 못 읽으면
  조용히 끈다.
- `app.py` 가 기동 시 한 번 부른다.

`local` 모드에서는 `_update()` 가 아무 파일도 만들지 않으므로 개발 PC·CI 동작은 그대로다.

**사내 PC 에서 `setx CAPA_S3_SYNC_MODE managed` 를 걸어야 켜진다.** `config/object_storage.json`
의 `mode` 는 `local` 로 커밋돼 있고 테스트가 그걸 강제한다. 이 환경변수가 없으면 배선이
붙어도 아무 일도 일어나지 않는다.

### C. 전송 제한시간을 실측에 묶었다

고정 300초는 지금 스냅샷에는 6배 여유지만 DB 가 커지면 그대로 상한이 된다.
`transfer_timeout_seconds()` 가 `max(300, 60 + MiB/0.3)` 을 돌려준다. 바닥 속도 0.3 MiB/s 는
실측을 최악으로 잡은 값의 절반이다. 스냅샷이 90 MiB 를 넘어야 300초 위로 올라간다.

### D. `requirements` 파일 4개 제거

`requirements.txt` 는 `-e .`, `requirements-dev.txt` 는 `-e .[dev]` 였다 — `pyproject.toml`
을 가리키는 껍데기라 정보가 없었다. 교차 검사로 확인했다: pyproject 의 직접 선언 12개가
락에 모두 있고, 락의 고정 버전이 전부 선언 범위를 만족하며, 양방향으로 빠지거나 남는
패키지가 없었다. 설치는 이제 `pip install -e .` / `pip install -e .[dev]` 하나뿐이다.

`pyrightconfig.json` 을 추가했다. 에디터가 uv 의 `.venv` 를 못 찾아 `import streamlit` 에
빨간 줄을 긋는 문제 때문이다. `.vscode/` 는 `.gitignore` 에 막혀 배포 ZIP 에 실리지 않아서
이 파일을 골랐다.

## 8. 다음에 할 일

### 8-1. push 시점 결정 (사용자 판단 대기)

| 안 | 장점 | 대가 |
|---|---|---|
| (a) 저장마다 자동 | 유실 위험 없음 | 저장마다 66초 |
| (b) 공식버전 발행 때만 (권장) | 저장은 즉시, 공유는 의도적 | 미발행 리비전이 로컬에만 존재 |
| (c) 수동 (현재) | 통제 완전 | 잊으면 안 올라감 |

**(b) 는 WebIDE 디스크가 유지될 때만 안전하다.** 재시작마다 초기화되는 구조면 (a) 나 (c) 로
가야 한다. 체크리스트 9번이 이 선택을 가른다.

### 8-2. 남은 확인 항목

- **9번 — WebIDE 재시작 주기·디스크 영속성.** 위 결정의 전제다.
- **8번 — WebIDE 안에서 `aws` 가 PATH 에 있는가.** 사내 PC 는 확인됐지만 WebIDE 는 아직이다.
  앱이 `aws` 를 직접 부르는 자동 pull/push 는 이게 확인돼야 붙일 수 있다.

### 8-3. 보류 중 — 사내 `pyproject.toml` 변경 크로스체크

사내에서 `company = ["bigdataquery"]` extra 를 추가하고 dev 의존성을 `[dependency-groups]`
로 옮겼다. 검토 결과:

- **`[dependency-groups]` 이동은 안전하다.** 배포 메타데이터에 들어가지 않아 오히려 정확하다.
  단 그룹 이름이 `dev` 여야 `uv sync` 가 자동 설치한다(uv 기본 `default-groups = ["dev"]`).
  그리고 `pip install -e .[dev]` 가 깨진다 — pip 25.1+ 는 `pip install --group dev`. 이 개발
  PC 는 pip 26.2.1 이라 지원한다(확인함). 명령이 두 단계가 된다.
- **`company` extra 는 목적과 반대로 동작한다.** uv 락파일은 universal 이라 모든 extra 와
  group 을 포함해 해석한다. 사내 인덱스에 `bigdataquery` 가 있으면 `uv.lock` 에 박히고,
  없으면 `uv lock` 자체가 실패한다. "락에서 빼는" 방법이 아니다. 확인: `uv lock && grep -n
  bigdataquery uv.lock`. 또한 `uv sync` 는 extra 를 기본 설치하지 않아 `--extra company` 가
  필요하다.
- **권장:** pyproject 에서 빼고 `uv sync` 뒤에 `uv pip install bigdataquery` 로 따로 넣는다.
  다음 `uv sync` 가 락에 없는 패키지를 지우므로 이후엔 `uv sync --inexact` 를 쓴다.
  근거는 코드가 이미 부재를 전제로 짜여 있다는 것이다 — `is_bigdataquery_package_available()`
  은 `find_spec` 으로만 보고 `load_bigdataquery_module()` 은 없으면 한국어 안내를 띄운다.
- **배포 ZIP 이 `pyproject.toml` 을 덮어쓴다.** 사내에서만 고쳐 두면 다음 배포에 조용히
  원복된다. 양쪽을 같게 유지해야 한다. dev 그룹 이동은 저장소에도 반영하는 편이 맞다.
- **부수 작업:** `load_bigdataquery_module()` 의 안내가 "사내 requirements를 적용하세요"
  인데 그 파일을 지웠다. 실제 명령으로 고쳐야 한다.

### 8-4. `mode` 가 아무것도 막지 않는다

`config/object_storage.json` 주석은 "`mode` 를 `local` 로 커밋해야 개발 PC 가 사내
스토리지를 건드리지 않는다" 고 경고하지만, 코드에서 `mode` 는 `doctor`·`status` 출력에만
쓰이고 실행을 막지 않는다. 개발 PC 에서 `local` 로 `status` 를 돌렸더니 그대로
`aws s3api list-objects-v2` 를 시도하고 `aws` 부재로 멈췄다. 실제 방어는 개발 PC 에 `aws` 가
없다는 것뿐이다. 가드를 넣을지는 결정 대기.

## 9. 설계 확인 — pull/push 는 없어지지 않는다

"S3 를 전면 적용하면 pull/push 가 필요 없어지는가" → **아니다.**

- DuckDB 는 오브젝트 스토리지 위에서 쓰기가 안 된다. httpfs 로 `ATTACH` 는 되지만 읽기
  전용이고, 이 앱은 기동만 해도 `initialize_global_display_order` 가 쓴다.
- 드라이브로 마운트해도 네트워크 파일시스템의 잠금 문제로 손상 위험이 있다.
- 1 MiB/s 회선에서 쿼리마다 원격을 읽으면 50초짜리 pull 한 번이 훨씬 싸다.

**전송 단위는 시나리오가 아니라 DB 파일 전체다.** 시나리오 전환·표·차트 조회·리비전 저장은
모두 로컬이라 네트워크가 0 이다. 평소 운영 중 네트워크가 도는 순간은 `push` 뿐이고, 기동
`pull` 도 원격이 앞서지 않았으면 세대 비교 몇 초로 끝난다.

드라이브가 마운트되면 `io/object_storage.py` 한 파일만 파일 복사로 바뀐다. 스냅샷 생성,
세대·분기 판정, 변경 표시는 그대로 필요하다. pull/push 가 정말 없어지려면 DuckDB 파일을
버리고 서버형 DB 로 가야 하는데, 그건 사용자가 여럿으로 늘어나는 시점(체크리스트 10번)의
판단이다.
