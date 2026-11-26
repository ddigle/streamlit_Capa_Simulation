# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **이 세션이 누구인지 먼저 가른다.** 첫 지시가 「모듈 `<id>` 를 맡은 에이전트」 이면 이 파일의 나머지 대신 `docs/module_guide.md` 만
> 따른다. 그 밖의 사내 세션은 배포 적용이다(`docs/internal_update_runbook.md`). `git remote -v` 가 `github.com` 인 세션(정본 개발 에이전트)은 아래를 따른다.

## 문서 우선순위

작업 전에 `README.md`, `AGENTS.md`, `docs/TODO.md`를 코드와 함께 확인한다. **`AGENTS.md`가
이 저장소의 상세 개발 규칙 문서**이며(파일별 책임, 기준정보 테이블 계약, 핵심 계산 규칙,
Streamlit 구현 규칙, 변경 체크리스트) 이 파일은 그 요약과 진입점이다. 계산식·테이블·화면을
바꾸기 전에는 `AGENTS.md`의 해당 절을 반드시 읽는다. 구조나 계산 규칙을 바꾸면 같은 변경에서
`AGENTS.md`·`README.md`·`docs/TODO.md`도 갱신한다. 화면 설계 · 검수 규칙(무엇을 어디에 어떤 꼴로 두나 — 규칙 id · 판단 질문 ·
결정 기록)의 정본은 `docs/design_rules.md` 다 — 화면을 만들거나 바꾸면 걸린 규칙 id 를 적고 규칙마다 자체 검토한다(구현
규칙은 `AGENTS.md` 8 · 9장).

직전 세션의 현재 상태와 다음 할 일은 `HANDOFF.md`에 있다. 정본이 아니라 그 시점의 세션
스냅샷이므로 위 세 문서·코드와 어긋나면 위를 따른다.

## 어느 환경에서 열렸는지 먼저 확인한다

이 저장소는 **사외(개발 PC)와 사내(WebIDE) 두 곳에서 열린다.** `git remote -v` 가
`github.com` 이면 사외, 사내 GitHub 주소면 사내다.

**사내에서는 코어 소스를 고치지 않는다.** 코어(배포 ZIP 이 싣는 것 전부)의 정본은 사외(`origin/main`) 하나이고, 사내에서
만든 수정은 정본이 될 수 없다 — 두 저장소는 서로의 원격을 볼 수 없어 합칠 방법이 없다.
사내 배포 에이전트가 쓸 수 있는 곳은 `review/` 뿐이고(모듈 담당자는 자기 `modules/<id>/` — 아래 절. 코드 밖 산출물의 사내 작업 자리 `review/<산출물>/` 도 그 안이고, 사내판을 `static/` 에
두는 것은 사용자가 복사한다 — dual_env 1-1),
고쳐야 할 것은 코드가 아니라 리뷰 문서로 낸다. 리뷰는 사람이 손으로 옮겨 적는 압축본과 사내에 남는 전문 두 파일이다.
예외는 사용자가 직접 지시한 임시 수정 하나다 — 커밋하지 않고 리뷰에 그 사실만 남기며 다음 적용 전에
되돌린다(런북 0장 · 1-5). 배포 ZIP 적용도 손으로 덮어쓰지 않고 `scripts/apply_deploy_package.py` 로 한다.
사내 에이전트는 사내 DB(BigDataQuery · 운영 DB · 사본)를 여는 명령을 스스로 치지 않는다 — 데이터가 꼭 필요하면 사용자에게 먼저
요청하고, 사용자가 별도 창에서 돌린 결과 파일만 읽는다(2026-11-11 사용자 결정 — 런북 0장). 정본 개발 에이전트가 다음 배포 런북을 쓸 때도 그 줄을
사내 에이전트에게 맡기지 않는다.
사내 운영 규칙(진행 꼴·모델 구간(런북 0-2 — 기본 Sonnet, `[Opus 구간 n]` 표지에서 바꿔 달라고 함)·앱 끄기·권한이 막힐 때·리뷰 꼴)의
정본은 런북이다 — 에이전트 메모리가 아니다.

사내에서 배포를 받아 적용하는 **한 번의 작업을 처음부터 끝까지** 적은 것은
`docs/internal_update_runbook.md` 다 — 사내 에이전트는 그것을 그대로 따라가면 된다.
전체 절차와 리뷰 문서 양식은 `docs/dual_env_workflow.md` 에 있다. 사내에서 작업을 시작하기
전에 그 문서를 먼저 읽는다.

## 모듈 담당자라면 (모델 2 — 2026-11-01)

동료가 만든 화면은 사내 저장소 `modules/<id>/` 에 두고 사이드바 별도 상자 「모듈」 로 띄운다. **모듈 담당자의
에이전트는 이 파일 대신 `docs/module_guide.md` 만 따른다** — 고칠 수 있는 곳은 자기 `modules/<id>/` 뿐이고
`data/modules/<id>/`(화면이 실행 중에 쓰는 자리 — 손으로 넣지 않는다)와 그 밖은 읽기만 한다. 코어는 배포 ZIP 이 싣는 것 전부이고 정본은 사외(`origin/main`)다. `modules/` 는 사내가 정본이며
ZIP 이 싣지도 덮지도 지우지도 않는다. 사외에는 그 폴더가 없다 — 정본 개발 에이전트는 `modules/` 를 만들지 않고 시험 견본은
`tests/fixtures/modules/` 아래 `demo_*` 합성으로 둔다. 역할 이름은 둘이다 — **담당자**(모듈을 맡아 그 에이전트와 대화하는 동료)와
**앱 관리자**(배포를 적용하고 승인하는 한 사람). 승인은 앱 관리자만 하고, 담당자 에이전트의 대화 안에서는 받을 수 없다. 담당자의 변경은
자기 가지 → PR 로만 사내 main 에 들어가고 앱 관리자가 PR 머리를 점검(런북 4-6)한 뒤 합친다 — 사내 main 은 보호한다(2026-11-02, dual_env 1-2).
사외 문서·커밋에는 모듈 id 를 옮기지 않는다(수와 꼴만).

## 코드 규칙

- **Purpose 헤더**: `app.py`·`app_pages/`·`src/`·`scripts/`·`tests/` 아래 모든 `.py`·`.ps1`
  최상단에 `# Purpose: <단일 책임 한 문장>` 을 유지한다. 파일 책임이 바뀌면 같이 고친다.
  `tests/test_source_metadata.py`가 누락과 SQL 카탈로그 등록을 검사한다. `modules/<id>/` 는 코어 시험이 훑지 않아
  `check_module.py`(M13)가 같은 헤더를 본다.
- 변경 이력·출처를 주석에 적지 않는다. Git commit history가 단일 근거다.
- 내부 컬럼명은 Excel/`Core_Data` 계약과 일치시킨다. 화면 라벨 때문에 원본 컬럼명을 바꾸지
  않는다.
- Streamlit: `use_container_width` 대신 `width="stretch"` / `width="content"`. 페이지 전용
  위젯에는 고유 `key`. 비싼 계산을 탭 안에서 반복하지 말고 캐시된 결과를 탭이 표시만 한다.
- 주석·문서·커밋 메시지는 한국어로 쓴다(기존 코드가 그렇다).

## 로컬 데이터는 합성 표본이다

`data/input/Core_Data.csv`와 `data/capa_simulation.duckdb`, `equipment_samples.py`,
`builtin_seed.py`, `dynamic_capacity.py`의 `DemoProfile`은 **실제 운영 데이터가 아니라
`scripts/generate_sample_core_data.py`의 리터럴에서 나온 합성 데모**다.

- 로컬 DB·CSV 쿼리 결과로 업무 구조를 판단하거나 설계를 바꾸지 않는다. 쿼리는 코드 경로가
  도는지 확인하는 용도다.
- 데이터를 집계해 얻은 수치는 `실측`이 아니라 `샘플 관측`이라고 적고 출처 리터럴을 남긴다.
- 표본 고유 수치(행 수, 공정 수 등)를 계약처럼 문서나 코드에 고정하지 않는다.

## Git 제외 자산

`*.xlsb`·`*.xlsx` 등 Excel, `data/*.duckdb`·`data/*.db`와 보조 파일, `.env`,
`.streamlit/secrets.toml`, `data/input`·`data/output`·`data/temp`의 실제 데이터는 커밋하지
않는다. `config/bootstrap_display_order.json`과 `builtin_seed.py`에는 합성 `DEMO_*` 값만 두고
실제 제품·고객·공정·설비 식별값을 넣지 않는다. `data/modules/`(모듈 데이터 — git·이미지 밖)도 커밋하지 않는다. 사외 저장소에는
`modules/` 를 두지 않는다(빌더가 멈춘다).
