# Capa Simulation

HBM·EDP-TSV PKG 라인의 월별 부하량, 대당 Capa, 소요대수, 확보율과 Bottleneck(B/N) 공정을 DuckDB 에 저장한
시나리오 기준정보로 계산하는 Streamlit 앱입니다. 화면 이름은 `S.PKG CAPA AX Management` 입니다.

- 새 웹 세션은 가장 최근에 발행한 **공식버전** 리비전을 불러옵니다.
- 웹에서 고친 계획·수율·Capa 기준정보는 그 브라우저 세션의 활성 시나리오에만 있고, 사이드바 `시나리오` 팝업에서
  저장해야 새 **리비전**(내용은 다시 고치지 않습니다 — 이름표인 리비전명만 고칠 수 있습니다)으로 남습니다. 저장하지
  않은 편집은 세션이 끝나면 사라집니다.
- GitHub 에서 소스만 받은 빈 환경도 첫 실행에 DuckDB 스키마와 합성 `DEMO_*` 시나리오·리비전·공식버전을 스스로
  만들어 바로 뜹니다. 시나리오가 하나라도 있으면 이 시드는 아무것도 만들거나 덮어쓰지 않습니다.

개발 규칙과 파일별 책임은 [AGENTS.md](AGENTS.md), 확정사항과 작업 목록은 [docs/TODO.md](docs/TODO.md)에 있습니다.
문서 전체의 지도는 맨 아래 [문서 지도](#문서-지도)입니다.

## 무엇을 계산하나

```text
Core_Data (사내 BigDataQuery / 개발용 data/input/Core_Data.csv / 내장 합성 시드)
  → 78컬럼 검증 + pandas 로 RQ 16개 표 변환
  → data/capa_simulation.duckdb   시나리오 · 리비전(내용 불변) · 공식버전 · 공용 표시순서
  → 최신 공식버전 또는 고른 리비전 → 사용자별 활성 시나리오(세션)
  → 부하량 → 대당 Capa → 소요대수 → 확보율 → B/N 공정 → HOME 대시보드

data/equipment_availability.duckdb   공통 호기 대장(호기 정보 · 실적 · 상태 · 기존 보유대수)과 설비 시나리오 일정
                                     (날짜 · 시나리오 메모 · 비가동)의 불변 저장 이력 · 공식 발행
  → 세션의 설비 시나리오(새 세션 = 공식) → 주차별 가용대수 · 설비 일정 기준 가용대수 · Space 배치(그 시나리오의 배치)
```

계산의 뼈대는 아래와 같습니다. 정확한 규칙(Dummy 산식, 측정률 기본값, 제외 행, PKG Buffer 계수 등)은
`AGENTS.md` 6장이 정본입니다.

```text
부하량    PKG·Chip(Kea) · Wafer(매) · Density(억Gb) — PKG PLAN 에 수율·Chip 구성을 걸어 환산
대당 Capa = 환산_UPEH × 24 × 효율 ÷ 여유율 × 모듈수 × 가동일수 ÷ Lot측정률 ÷ WF측정률
환산_UPEH = UPEH(Main) · 60 ÷ ST(MI — ST 는 한 개당 분으로 입력), CHIP·PKG 는 다시 ÷ 1,000
소요대수  = 부하량 ÷ 대당 Capa        (RQ_REQB 의 Area·STEP·MCP 경로별로 나눈 뒤 공정으로 합산)
확보율    = 가용대수(RQ_EQP_AVBL) ÷ 소요대수
B/N       = 그 달 확보율이 가장 낮은 공정
```

확보율은 **확보·경고·부족** 셋으로 판정합니다. 기준(기본 109.5%·99.5%, 화면에는 110%·100% 로 적음)은 시나리오와
무관한 공용 설정이고 `HOME → Preference` 의 `확보율 판정 기준` 한 곳에서 정합니다. 달마다 다른 기준을 둘 수
있고, 기준과 같으면 확보입니다.

### 세 영역

사이드바 계산 그룹은 차례대로 셋입니다.

| 그룹 | 뜻 |
|---|---|
| **Static Capa** | **약속.** 기술팀의 Capa 기준정보와 생산계획으로 낸 미래 Capa 와 부족 대수 |
| **실행 관리** | **이행.** 약속한 Capa 가 실제로 확보되는지 공정·기간·호기로 재고, 어긋난 곳을 추적 |
| **Dynamic Capa** | **실적.** 실행 관리가 모은 실적으로 다시 낸 Capa 와 그것으로 하는 단기 운영(재공) |

말을 이렇게 가릅니다 — 「Dynamic」 은 실적 Capa 에만 씁니다. 설비 마스터 일정으로 낸 가용대수는 **설비 일정 기준
가용대수**(짧게 「일정 기준 가용」), HOME 에서 확보율에 %p 를 손으로 더하고 빼는 입력은 **확보율 보정**입니다.

## 화면 목록

사이드바 차례 그대로입니다. 목록의 정본은 `src/capa_simulation/navigation.py` 입니다.

| 화면 | 하는 일 |
|---|---|
| 입장 화면 · Summary · Introduce | 탭을 처음 열면 첫 로딩을 덮는 입장 화면. `Detail` 은 앱으로, `Summary` 는 최신 공식버전 여섯 달 요약으로, `Introduce` 는 40초 티저를 화면 안에 띄움(← · Esc 로 돌아오며 재생도 멈춤 — 루트 `index.html` 발표 덱은 GitHub Pages 용). 앱 안에서는 사이드바 맨 위 앱 이름 라벨이 Summary 를 다시 열고, Summary 머리 줄 ← 가 입장 화면으로 돌아감 |
| **HOME** | 대시보드. `Main`(Capa 요약·LOB·B/N)·`Preference`(공용 설정 — 비교 시나리오·주요 Case(Case1·Case2)·판정 기준 등)·`Past Data`(과거 구간) 세 탭. 제목 줄 끝 주요 Case 칩(`공식 vN`·`Case1`·`Case2`)을 누르면 사이드바에서 그 리비전을 불러온 것과 같다 |
| Capa Chatbot (구현중) | 대화형 분석 화면의 틀. LLM·Capa 데이터·대화 이력은 아직 잇지 않음 |
| 시나리오 관리 | 「관리할 시나리오」 전환 — **시뮬레이션 시나리오**: 시나리오·리비전 표에서 이름·순서 바로 고치기, 리비전 불러오기, 공식버전 지정(확인 팝업), 지금 편집본 복제, 보관·삭제 (새 리비전 저장은 사이드바 시나리오 팝업) / **설비 시나리오**: 목록·리비전·리비전명·되돌리기·여기서 새 시나리오·이름·공식 발행·이어 쓰기·배치 차이 칸과 「배치 차이 모두 지우기」(가용설비 현황의 탭이던 것). 사내 `BigDataQuery 등록`, 공식버전 `자동 갱신` |
| **Static Capa** | 월·공정별로 경고 기준까지, 경고에서 확보 기준까지 모자라는 설비 대수 |
| ├ 생산 계획 | PKG PLAN·수율 편집, 부하량 환산 결과, 기존 제품을 복제한 가상 제품 등록 |
| ├ 기준 정보 | UPEH·효율·여유율·일수·Lot/WF 측정률·설비대수·STEP 구성 편집(Excel 붙여넣기 포함) |
| ├ 산출 결과 | 대당 Capa·소요대수·확보율 표와 히트맵, 계산에서 뺀 행 목록, CSV 내려받기 |
| └ 표준 목표 | 월간 대당 Capa 를 일·주 단위 표준 가능량으로 풀기(주차별 가용대수 붙여넣기)와 로직 분석 |
| **실행 관리** | 세 영역의 뜻과 하위 화면 목차(아직 데이터를 읽지 않음) |
| ├ 공정 Capa 상세 | 공정 하나의 산출 근거 → 부족한 달 → 그 달을 메우는 설비 일정. HOME 의 막대·칸을 누르면 열림 |
| ├ 필요 단축 일정 | 일정 기준 가용이 목표 확보율에 모자라는 달마다 신규 호기 Qual 을 며칠 당길지, 진척 비교, 카드에서 도면으로(「도면에서 보기」 — Space 필요 단축 보기). 머리 「Qual 마감 계산기」 팝업(다른 데이터와 잇지 않음 — 월별 목표·신규 호기 → 호기별 Qual 완료 마감) |
| ├ 제약 시뮬레이션 | 공정 하나의 미래 제약 — 제약 제품 먼저 떼고 기존 제품 확보율 영향 · 개조 비가동(보유 제약 설비 · 개조 기간 안에 늘어날 몫에 미리 붙여 「신규 대기」 하는 신규 설비는 개조 없이 — 옵션). 둘째 모드 「개조 일정」 은 N대 × D일 개조를 모든 달 기준 확보율을 지키며 언제 할지(같은 날 개조는 그 달 가용까지 · 못 맞추면 대안 셋과 까닭). 저장하지 않음 · 공정 Capa 상세 머리 링크로 열림 |
| ├ 가용설비 현황 | 탭 둘 — ① `설비 마스터`(설비 마스터 표 — 불러오기·칸 고치기·엑셀 여러 칸 붙여넣기·한꺼번에 고치기·지우기/되살리기, 오른쪽 칸 호기 상세(설비명 = 같은 호기 이름 바꾸기·가정 배치 「공식 자리로 되돌리기」·이 호기로 새 호기 만들기)·새 호기(체크 상자 — 에러 없이 추가·가용대수·도면에 필요한 칸, 비슷한 호기에서 가져오기, 호기마다 다른 설비 시나리오에도 넣기)·저장 전 변경(리비전 저장)·저장 이력, 기존 보유대수·비가동 일정 작은 편집표, 「엑셀·CSV로 한꺼번에」 팝업·내려받기) ② `Summary`(`Main` 주차별 대수 · `Static 대비 일정` 비교). 머리 「설정」 팝업에 공정별 Cut-off |
| ├ Space 현황 | 고른 설비 시나리오의 FAB 전체 → 층 상세 배치 도면과 배치 편집기(가정 시나리오의 배치는 그 시나리오에만, 「공식과 견주기」 점선), 층마다 사용/비활성(사유) 설정(공식에서만), 색 기준 `필요 단축` 으로 호기별 단축 일수 겹쳐 보기(필요 단축 일정과 같은 계산 · 오늘 기준) |
| └ 효율·UPEH·수율 실적 (구현중) | 기준 대비 Gap·개선 우선순위 화면 초안(실적 DB 연결 전) |
| **Dynamic Capa** | 표준 Capa → 효율 → UPEH → Rundown → 실제 실적의 손실 분해(데모 데이터) |
| └ 표준 대비 재공 현황 (구현중) | 오늘 −7일~+3일의 보유 재공·유입·Flow 와 일 표준 가능량(결정론적 샘플) |
| Admin Area | 공정 표시명(`Proc Rename`)·공용 표시순서 관리, 원천 품질, 계산 알림을 한곳에 모은 `알림 모음` |
| VOC | 질문·개선 요청·오류 신고 게시판(시나리오와 무관) |

- 제목의 `(구현중)` 은 실적 DB 연결과 운영 기준 확정 전인 화면입니다. 그룹 머리에는 달지 않습니다. 그룹을 옮긴 화면도 파일 이름·제목·주소는 그대로라 북마크가 삽니다.
- **화면 탭 줄**(머리 띠 바로 아래, 2026-10-24). 이번 접속에서 연 화면이 탭으로 섭니다 — 사이드바·HOME 칸·카드 링크
  어느 길로 열어도 끝에 붙고, 이미 연 화면이면 그 탭으로 갑니다. 탭 이름은 사이드바 이름에서 「(구현중)」 만 뗀 것이고,
  화면 본문의 큰 제목은 화면에서 숨기고 인쇄에만 남깁니다(배지·설명 줄은 그대로).
  - HOME 은 고정 탭으로 시작합니다. 어느 탭이든 핀 단추로 고정·고정 풀기를 하고, 고정 탭은 왼쪽에 모이며 × 가 없습니다.
    마지막 남은 탭은 닫지 않습니다. × 를 더블클릭해도 누른 탭 하나만 닫힙니다(닫은 뒤 0.5초 안에 같은 자리로 다시 누른 것은
    버립니다 — 그 자리로 당겨 온 옆 탭을 닫거나 고정하지 않게). 탭은 10개까지 엽니다 — 넘으면 열지 않고 「안 쓰는 탭을 닫아 주세요」 를 띄웁니다.
    사이드바·본문 링크와 HOME 칸은 누른 자리에서 막습니다(링크 둘을 빠르게 잇달아 눌러도 둘째는 막습니다). 다만 브라우저
    뒤로가기로 닫은 탭의 기록에 닿으면 지금 화면에 머물며 같은 알림이 뜨고, 탭 하나를 닫을 때까지 그 기록 앞으로 가지
    못합니다.
  - 화면을 옮기면(탭·사이드바·본문 단추·HOME 칸·링크 어느 길이든) 브라우저 기록이 한 칸 쌓여 뒤로가기 한 번이면 직전
    화면입니다. 같은 화면 안에서 주소만 바뀌는 것(Space 층 열기 등)은 기록을 쌓지 않습니다. 옮기는 동안 다른 탭을 또
    누르면 옮긴 뒤 마지막으로 누른 탭으로 갑니다.
  - 탭을 닫아도 그 화면의 보기 조건은 지우지 않습니다. 다시 열면 이어집니다. 주황 점은 저장·적용하지 않은 것이 있다는
    뜻입니다(붙여넣기 대기·설비 편집본·Past Data 초안·시나리오 관리 표 초안은 어느 화면에서나, 편집표의 적용 전 편집과
    Space 층 사용 편집은 지금 탭에만). 지금 화면에 「적용」 하지 않은 편집표 편집이나 저장하지 않은 층 사용 편집이 있으면
    다른 탭을 누르거나 지금 탭을 닫을 때 묻습니다(사이드바 링크·뒤로가기는 묻지 않습니다).
  - 탭은 화면을 살려 두지 않습니다 — 돌아오면 보기 조건(필터·하위 탭·보기 방식·고른 공정)은 그대로이고, 편집표의 적용 전
    편집·폼에 쓰다 만 글(BigDataQuery 등록·VOC 등)·팝업·접힌 상자·스크롤 위치는 처음으로 돌아갑니다. 가용설비 현황 설비 마스터
    표에서 고친 것은 편집본이라 남고(불러온 목록·표 고르기·오른쪽 칸도 그대로), 작은 편집표의 「편집본에 적용」 전 편집과 표의 고름·
    정렬·스크롤은 처음으로 돌아갑니다.
  - 탭 목록은 이번 접속에만 삽니다. 새로고침하거나 테마를 바꾸면(새로고침과 같습니다) HOME(고정)과 지금 화면만 남습니다.
- 사이드바 `조회 조건 · 이 화면에 적용` 패널에는 그 화면이 실제로 읽는 조건만 섭니다 — `시나리오`·`조회기간`(HOME
  은 `공정 필터`·`주요공정 히트맵` 까지). 화면 고유의 설정은 그 아래 접히는 **조건 카드**입니다.
- 화면 설명은 헤더 툴바 맨 왼쪽 `Guide` 버튼에 있습니다(원문 `src/capa_simulation/guides/`). 툴바 차례는
  `Guide` · `Print` · 테마입니다.
- HOME 의 `Guide` 는 번호대로 따라 하는 **따라하기 가이드**를 앱 옆의 작은 창으로 엽니다. 사내판
  (`static/guides/local/lob.html` — 사내 실화면, git 무시)이 있으면 그것을, 없으면 합성 예시판
  (`static/guides/howto/lob.html` — 숫자 · 이름은 모두 합성)을 열고, 둘 다 없으면 지금의 설명 대화상자를 엽니다.
  설명 대화상자는 창 머리의 `설정 사전` 단추로 앱 창에 뜹니다. 팝업이 막히면 대화상자로 물러섭니다.
- 입장 화면은 한 탭에 한 번 뜹니다(새로고침·테마 바꾸기에도 다시 뜨지 않음). Summary 머리 줄의 `선행 B/O`·`선행 입고`·
  `GAP` 토글은 브라우저 안에서만 켜고 끄며 앱 계산을 바꾸지 않습니다. `Esc`·`Detail` 이 앱으로 돌아갑니다.
- 공정 이름은 **화면은 표시명, 파일은 원본**입니다. 화면에서 읽는 공정명은 `Admin Area` 의 표시명이고, 저장값과
  내려받는 CSV 는 원본 공정명 그대로입니다.

## 권장 실행 환경

- Python **3.10.11 64-bit** 고정, 실행은 저장소의 `.venv`
- 패키지 관리 `uv`(의존성 선언은 `pyproject.toml` 하나, 개발 도구는 `[dependency-groups]` 의 `dev`). 루트
  `requirements.txt` 는 사내 WebIDE 컨테이너용으로 `uv export` 로 뽑은 `uv.lock` 의 그림자라 손으로 고치지 않습니다
  (`tests/test_requirements_export.py` 가 대조)
- 사외 개발·배포 빌드: 데스크탑 WSL(Ubuntu x86_64) 한 곳 — [`docs/wsl_dev_environment.md`](docs/wsl_dev_environment.md)
- 사내: Windows 10/11, Git for Windows
- Microsoft Excel 2021 또는 Microsoft 365 Desktop — 새 원천 코드의 첫 적재와 병행 검증 때만

## 초기 설정

처음 세팅하는 사람이 위에서부터 그대로 따라 하면 됩니다. **어느 환경인지부터 고르세요.**

| | 사외 (개발 PC) | 사내 (WebIDE·사내 PC) |
|---|---|---|
| 패키지 관리 | `uv` | `uv` |
| 추가로 필요한 것 | 없음 | `bigdataquery` (사내 인덱스) |
| 코드 수정 | 합니다 | **하지 않습니다** — [`docs/dual_env_workflow.md`](docs/dual_env_workflow.md) |
| 따라 할 곳 | `docs/wsl_dev_environment.md` 1장 | 아래 0~6단계 |

`pyproject.toml` 과 `uv.lock` 은 양쪽이 완전히 같습니다. `uv sync` 가 `dev` 그룹(mypy·ruff·pytest)까지 함께 깝니다.

### 0단계. 준비물 확인

```powershell
git --version
py -3.10 --version     # 3.10.11 이 나와야 합니다
uv --version
```

`uv` 가 없으면 `pip install uv` 또는 [astral.sh/uv](https://docs.astral.sh/uv/) 안내를 따릅니다.

### 1~3단계. 받기 · 환경 만들기 · 확인

```powershell
git clone <저장소 주소> C:\dev\streamlit_project
cd C:\dev\streamlit_project
uv sync
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501
```

- 배포 ZIP 으로 받았다면 `git clone` 대신 그 폴더에서 시작합니다. 첫 ZIP 은 손으로 풀고, 다음부터는
  `scripts/apply_deploy_package.py` 가 적용을 맡습니다(5단계).
- `.venv` 가 생긴 뒤의 명령은 `.\.venv\Scripts\python.exe ...` 로 칩니다. **사내에서는 `uv run --no-sync python ...`**
  을 씁니다 — 맨 `uv run` 은 돌기 전에 락을 다시 맞추며 빠진 패키지를 까는데, `--no-sync` 는 그 일을 아예 하지 않아
  사내 전용 패키지를 건드리지 않습니다.
- 빈 `data/` 에서도 앱이 뜹니다. Excel·Core Data CSV·사내 DB 없이 HOME 과 계산 페이지를 열 수 있습니다.

### 4단계. 사내 전용 패키지 넣기 (사내만)

```powershell
uv pip install -r requirements-company.txt
```

- `bigdataquery` 를 사내 Artifactory 인덱스에서 받습니다. 인덱스 주소는 그 파일 안에 있습니다.
- C-DEP WebIDE 처럼 이미지가 `UV_DEFAULT_INDEX` 를 고정해 둔 곳에서는 위 한 줄이 그대로 안 됩니다. 추가 인덱스와
  시스템 인증서로 까는 법, 로그인·요청자 계정 설정은 `docs/bigdataquery_webide_setup.md`.
- **이 뒤로는 `uv sync` 대신 `uv sync --inexact` 를 씁니다.** 맨 `uv sync` 는 락에 없는 패키지(`bigdataquery`)를
  지웁니다. 지웠으면 위 명령을 다시 돌립니다.
- `bigdataquery` 를 `pyproject.toml` 에 적지 않는 까닭은 `requirements-company.txt` 머리에 있습니다 — 락은 모든
  extra·group 을 해석하므로 사내 인덱스에 닿지 못하는 개발 PC 에서 `uv lock` 이 죽습니다. 덕분에 배포 ZIP 에서
  빼야 할 파일이 없습니다.
- 패키지가 없어도 앱은 뜹니다. `BigDataQuery 등록` 화면만 안내를 띄우고 멈춥니다.
- C-DEP CD(배포 서버)에는 셸이 없어 위 명령을 칠 수 없습니다. 배포 설정의 환경변수 표에 값을 넣으면 이미지의 시작
  스크립트(`scripts/container_start.py`)가 설치·로그인 토큰을 갖추고 결과를 Admin Area 「서버 시작 점검」에 남깁니다 —
  넣을 key 는 `docs/bigdataquery_webide_setup.md` 「C-DEP CD(배포 서버)」.

### 5단계. 배포 적용 도구 자리 잡기 (사내, 최초 1회)

```powershell
uv run --no-sync python scripts/apply_deploy_package.py <내려받은 ZIP> --dry-run
```

`--dry-run` 은 아무것도 바꾸지 않고 무엇이 지워지고 덮일지만 보여 줍니다. 처음에는 꼭 이것부터 돌립니다.
배포 한 번의 전체 절차는 [`docs/internal_update_runbook.md`](docs/internal_update_runbook.md) 입니다.

### 6단계. 사내 규칙 걸기 (사내, 최초 1회)

```powershell
New-Item -ItemType Directory .claude -Force
Copy-Item docs\internal_claude_settings.json .claude\settings.json
New-Item -ItemType Directory review -Force
```

- `.claude/settings.json` 은 사내 에이전트가 `review/` 밖을 고치지 못하게 막고, `review/` 는 리뷰 문서 자리입니다.
- 둘 다 배포가 **보존**하므로 다음 ZIP 이 덮지 않습니다. 템플릿이 바뀌면 그때 다시 복사합니다.
- 사내 에이전트 세션은 auto·bypass(권한 건너뛰기) 모드로 띄우지 않습니다 — 템플릿의 방어선은 사람이 승인 프롬프트를 읽는
  것입니다. 배포마다 런북 1-2 가 설정이 템플릿과 같은지와 함께 봅니다.

### 막힐 때

| 증상 | 까닭과 조치 |
|---|---|
| `uv lock` 이 `dns error` 로 죽는다 | `bigdataquery` 를 `pyproject.toml` 에서 빼 `requirements-company.txt` 에 둡니다. |
| `bigdataquery` 가 사라졌다 | 맨 `uv sync` 를 돌렸습니다. 4단계를 다시 하고 이후 `--inexact` 를 씁니다. |
| `duckdb.IOException` | 앱이 DB 를 쥔 채 스크립트·테스트를 돌렸습니다(배타 잠금). 앱을 끄고 다시 — 고장이 아닙니다. |
| 앱이 「Port 8501 is not available」 로 멈춘다 | 다른 것이 8501 을 쥐고 있습니다. 포트를 적었으므로 다음 번호로 말없이 옮겨 서지 않고 멈춘 것입니다. 누가 쥐었는지 보는 법은 [`docs/internal_update_runbook.md`](docs/internal_update_runbook.md) 4-2 「접속이 안 되면」. |
| 활성화 스크립트가 차단된다 | 활성화하지 않고 `.venv\Scripts\` 의 실행 파일을 직접 씁니다. |
| 에디터가 `import streamlit` 을 못 찾는다 | 인터프리터를 `.venv` 로 지정합니다. 실행·테스트에는 영향이 없습니다. |
| 계산 화면이 「조회기간(…) 밖의 달에 기준정보 오류」로 멈춘다 | 계산은 시나리오 전체 기간을 돌려 어느 달이든 기준정보 오류가 있으면 멈춥니다(의도된 동작). `기준 정보` 화면은 열리므로 그 달을 고쳐 새 리비전으로 저장합니다. |

## 실행

Windows(PowerShell):

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501
```

사외 WSL(bash)은 사용자가 Claude 밖 tmux 창에서 [`docs/wsl_dev_environment.md`](docs/wsl_dev_environment.md) 3장의
실행 줄로 띄웁니다. **포트는 늘 적습니다** — 8501~8503 은 사용자 몫이고 시험용 앱은 8510 이상입니다.

```bash
.venv/bin/python -m streamlit run app.py --server.headless true --server.port 8501 --browser.serverAddress localhost
```

- 빈 `data/` 에서도 시뮬레이션 DB 와 내장 데모 공식버전이 생깁니다. 설비 DB 도 그 화면을 처음 열 때 스키마가
  생기고, 실제 리비전을 저장하기 전에는 화면 검토용 합성 샘플을 보여 줍니다(DB 에는 적지 않습니다).
- 공식버전 자동 갱신(`시나리오 관리 → 자동 갱신`)은 실행 줄에 `CAPA_AUTO_OFFICIAL_UPDATE=1` 을 더해 띄운 앱에서만
  돕니다. 사내 운영 절차는 런북 4-4 입니다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts\benchmark_home.py
.\.venv\Scripts\python.exe scripts\validate_duckdb_persistence.py   # Windows + Excel + templates/structure_template.xlsb 가 있을 때만
```

```bash
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
.venv/bin/python -m pytest
```

- `mypy` 는 `app.py`·`app_pages/`·`src/`·`tests/`·`scripts/` 를 모두 strict 로 봅니다(범위와 테스트에서 끄는 오류
  코드는 `pyproject.toml` 의 `[tool.mypy]`). 상대경로 설정이 있어 저장소 루트에서 돌립니다.
- 단일 테스트: `.venv/bin/python -m pytest tests/test_home_page.py::test_home_renders_summary_dashboard_from_the_builtin_seed`
- 화면·상태를 바꿨으면 `streamlit.testing.v1.AppTest` 나 실제 브라우저로 페이지 진입·수정·왕복까지 봅니다
  (`AGENTS.md` 2장).

## 입력 데이터

### Core Data 와 RQ 16개 표

원천은 한 가지 꼴, **Core Data 78컬럼**입니다. 컬럼 계약의 정본은 `config/data_contract.json` 이고, 앱은 그것을
검증한 뒤 pandas 변환(옛 XLSB Power Query 를 대신함)으로 `RQ_` 접두의 기준정보 표 16개를 만듭니다. 원천 행은
typed raw 로 그대로 보존합니다.

| 묶음 | 표 |
|---|---|
| 계획·환산 | `RQ_PKG_PLAN`(생산계획) · `RQ_YLD`(EDS·BE 수율) · `RQ_CHIP_QTY`·`RQ_CHIP_EQ`(Chip 구성·환산) |
| Capa 기준 | `RQ_UPEH`·`RQ_RUN_RATE`(효율)·`RQ_VITAL`(여유율)·`RQ_RUN_DAY`(일수)·`RQ_LOT_RATIO`·`RQ_WF_RATIO`(측정률) |
| 경로 | `RQ_REQB`(Area·STEP·MCP 공정 경로별 소요기준) |
| 설비대수 | `RQ_EQP_OWN`(보유) · `RQ_EQP_LENT`(대여) · `RQ_EQP_AVBL`(가용) |
| 읽기 전용 참조 | `RQ_DISPLAY_ORDER`(표시순서) · `RQ_MODULE`(모듈수) |

위 14개는 웹에서 고치고 리비전으로 저장하는 표, 아래 둘은 데이터셋에 붙은 참조 표입니다. 표마다의 키와 저장
위치는 `AGENTS.md` 4장과 [`docs/data_model.md`](docs/data_model.md), 화면 정렬 규칙은 `AGENTS.md` 8장에 있습니다.
**표시순서**는 시나리오와 분리된 공용 DB 프로필 하나이고 `Admin Area → 표시순서 관리` 에서 고칩니다. 처음 만들 때는
기존 시나리오의 규칙과 선택적 `data/input/RQ_DISPLAY_ORDER.csv` 가운데 더 완전한 쪽을, 둘 다 없으면
`config/bootstrap_display_order.json` 의 비민감 시드를 씁니다.

### 원천 셋

| 원천 | 쓰는 곳 |
|---|---|
| 사내 BigDataQuery | 운영. `시나리오 관리 → BigDataQuery 등록` 에서 기간의 시뮬레이션 코드를 골라 시나리오로 저장한 뒤 `목록 관리` 에서 공식버전으로 지정 — 지정하기 전에는 새 세션이 내장 데모를 연다. CS 가 빈 행은 양산구분을 정할 수 없어 기준정보에서 빼고 저장하며, 뺀 행 수(계획 행 · 경로 행)와 경로 일부가 빠져 소요대수가 줄 수 있는 남은 계획 줄 수를 저장 알림과 리비전 메모에 남긴다 |
| `data/input/Core_Data.csv` | 개발용 합성 데모 CSV(`scripts/generate_sample_core_data.py` 가 만듦) |
| 내장 합성 시드 | 빈 저장소의 첫 실행. 앱과 계산 경로를 돌리기 위한 데모이며 운영 기준정보가 아님 |

- 같은 시뮬레이션 코드는 바뀌지 않는 원천으로 봅니다. 내용이 같으면 다른 시나리오로 다시 등록할 수 있고, 다르면
  거부합니다. 계속 고치는 원천은 기존 시나리오의 새 리비전으로 관리합니다.
- 사내 조회 어댑터는 `src/capa_simulation/io/company_bigdataquery_adapter.py` 이고 `bigdataquery` 는 사내에서만
  깝니다(4단계). 원천 등록·자동 갱신 화면의 자세한 동작은 `시나리오 관리` 의 `Guide` 입니다.

### 초기화·재적재 명령

내장 시드로 빈 저장소를 안전하게 초기화합니다(앱 첫 실행이 하는 일과 같습니다). 생성과 공식 발행 사이에 멈춘
시드는 다음 시작에서 발행만 잇고, 사용자 시나리오만 있고 공식버전이 없는 저장소는 건드리지 않으므로
`시나리오 관리` 에서 공식버전을 직접 지정합니다.

```powershell
.\.venv\Scripts\python.exe scripts\bootstrap_builtin_seed.py
```

개발용 `Core Data 초기 시나리오` 를 지금 변환 계약으로 새로 만들어 공식 발행합니다. 같은 원천 코드의 옛 시나리오는
지우지 않고 목록에 남기므로 필요 없으면 `시나리오 관리 → 목록 관리` 에서 지웁니다. 실행 중인 앱이 DB 를 잠그므로
먼저 앱을 내립니다.

```powershell
.\.venv\Scripts\python.exe scripts\bootstrap_initial_duckdb_scenario.py --replace-existing
```

합성 데모 CSV 를 다시 만들었으면 원천이 달라졌으므로 **새 원천 코드**로 적재합니다(같은 코드로는 거부됩니다).

```powershell
.\.venv\Scripts\python.exe scripts\generate_sample_core_data.py data\input\Core_Data.csv
.\.venv\Scripts\python.exe scripts\bootstrap_initial_duckdb_scenario.py --source-code <새 원천 코드> --scenario-name <시나리오 이름>
```

- 새 원천 코드의 **첫 적재만** 표시순서를 `templates/structure_template.xlsb` 에서 Excel 로 읽습니다. 사외 WSL 에는
  Excel 도 `templates/` 도 없어 이 둘째 줄을 돌릴 수 없습니다.
- `--replace-existing` 없이 돌렸는데 같은 원천 코드가 이미 있으면 그 활성 리비전을 공식버전으로 지정합니다. 가상
  제품이 든 리비전은 `--allow-virtual-products` 를 붙여야 지정합니다. 이름이 겹치면 이름 뒤에 만든 시각을 붙입니다.
- WSL(bash)에서는 `.venv/bin/python` 과 `/` 경로로 칩니다 — 예: `.venv/bin/python scripts/bootstrap_builtin_seed.py`.
  `\` 는 bash 에서 이스케이프라 `data/input/Core_Data.csv` 처럼 적습니다.

## 데이터와 DB

| 파일 | 내용 |
|---|---|
| `data/capa_simulation.duckdb` | 시뮬레이션 DB — 시나리오·리비전·공식버전·공용 프로필(표시순서·공정 표시명·판정 기준·주요 Case 등) |
| `data/equipment_availability.duckdb` | 설비 운영 DB — 공통 호기 대장 리비전·설비 시나리오 일정 리비전·공식 발행, 주차별 가용대수, 도면 |
| `data/capa_simulation.db` | 옛 Excel/SQLite 병행 검증용. 앱은 읽지 않음 |
| `templates/*.xlsb` | 일회성 초기 이관·병행 검증용 로컬 Excel |
| `data/input/` | 개발용 Core Data CSV, 선택적 표시순서 CSV |

- 두 DuckDB 는 물리적으로 갈라져 있습니다. 설비 화면은 시뮬레이션 기준정보를 읽지 않고, 둘을 맞대는 화면
  (`Static 대비 일정`·필요 단축 일정·공정 Capa 상세·제약 시뮬레이션·Space 현황 「필요 단축」 보기(켠 동안만) 등)만 양쪽을
  읽습니다. 제약 시뮬레이션은 어느 DB 에도
  쓰지 않습니다.
- Excel, DuckDB·SQLite 파일과 그 보조 파일, `data/input`·`data/output`·`data/temp` 의 실제 데이터, `.env`,
  `.streamlit/secrets.toml` 은 **Git 에 넣지 않습니다**. DB 는 첫 실행에 생기는 로컬 자산입니다.
- 시나리오를 지워도 DuckDB 파일은 줄지 않습니다. 앱을 내린 뒤 `scripts/compact_duckdb.py` 로 재구축합니다.
- 사내에서 오브젝트 스토리지 동기화(`managed` 모드)를 켜면 DB 옆에 `<db파일명>.sync.json` 사이드카가 생깁니다 —
  [`docs/objectstore_setup.md`](docs/objectstore_setup.md).
- 예전 배포로 되돌려 DB 에 코드가 모르는 더 높은 마이그레이션이 적용돼 있으면 앱은 막지 않고 돌며, 화면 맨 위에
  「시뮬레이션 DB(또는 설비 DB)가 이 코드보다 새 버전입니다(DB n · 코드 m)」 경고를 띄웁니다.
- 스키마는 SQL 마이그레이션으로만 바뀝니다. 적용된 파일은 체크섬을 대조하므로 고치지 않고 후속 번호를 더합니다
  ([`docs/migration_catalog.md`](docs/migration_catalog.md)).

> **로컬 데이터는 합성 표본입니다.** `data/input/Core_Data.csv`, 거기서 적재된 `data/capa_simulation.duckdb`,
> 내장 시드와 설비·Dynamic 화면의 샘플은 실제 운영 데이터가 아니라 `scripts/generate_sample_core_data.py` 등의
> 리터럴에서 나온 데모입니다. 로컬 쿼리 결과로 업무 구조를 판단하지 말고, 데이터를 집계한 수치는 「샘플 관측」
> 이라고 출처와 함께 적습니다(`AGENTS.md` 10-1). `config/bootstrap_display_order.json` 과 내장 시드에는 합성
> `DEMO_*` 값만 둡니다.

### 설비 시나리오

설비 마스터는 **공통 호기 대장**과 **설비 시나리오 일정**으로 나뉩니다(설비 마이그레이션 `0027`, 2026-10-24 결정).
호기 정보·Space 좌표(공식 배치)·실적·상태·이력·메모·기존 보유대수는 시나리오와 무관하게 늘 최신 하나이고, 날짜 여섯(제진대·물류·
반입·Qual·정지·반출/이설)과 `시나리오 메모`, 비가동 일정 전체가 시나리오마다 따로입니다 — 예를 들어 「운영 일정」 과
「셋업 실무」 일정을 나눠 둡니다. 가정 설비 시나리오는 공식과 다른 배치(가정 배치)도 따로 듭니다(아래 「가정 설비 시나리오의
Space 배치」). 설비 시나리오는 시뮬레이션 시나리오와 짝짓지 않고 HOME·Static 확보율(`RQ_EQP_AVBL`)
계산에 들지 않습니다.

- 시뮬레이션처럼 **공식 발행**(append-only)으로 운영합니다. 새 세션·HOME 칸에서 들어온 공정 Capa 상세·진척
  비교 기준선은 공식이고, 가용설비 현황·필요 단축 일정·공정 Capa 상세·제약 시뮬레이션·Space 현황은 사이드바 「설비 시나리오」
  줄에서 고른 시나리오를 따릅니다. 시나리오 만들기는 복제로만(「여기서 새 시나리오」 — 어느 리비전에서든), 이름 바꾸기·발행은
  시나리오 관리 › 설비 시나리오(「관리할 시나리오」 전환 — 가용설비 현황의 탭이던 것)입니다.
- 같은 탭에서 일정 리비전마다 **리비전명**(나중에 고칠 수 있는 이름표 — 내용은 그대로)을 붙이고, 옛 리비전을 골라 **「이
  리비전으로 되돌리기」** 를 합니다. 되돌리기는 옛 리비전을 고치지 않고 그 일정(날짜 여섯·시나리오 메모·비가동)을 같은
  시나리오의 새 리비전으로 다시 저장합니다 — 공통 대장은 그대로이고, 그 리비전 뒤에 공통 대장에 든 호기는 그 리비전에 일정이
  없어 「일정 없음」 이 됩니다. 확인 글이 바뀌는 호기 수와 「일정 없음」 이 되는 호기 수를 먼저 보이고, 확인 체크는 그 글에
  묶여 다른 리비전을 고르거나 그 사이 누가 저장·발행하면 풀립니다. 공식 시나리오에서 되돌리면 저장과 같은 공식 발행 규칙(기본
  켬)이 걸립니다. 리비전명은 40자까지입니다.
- 저장은 바뀐 쪽(공통 대장 / 그 시나리오 일정)만 새 리비전으로 남기고, 바뀐 것이 없으면 리비전을 만들지 않습니다. 새 호기와
  새 비가동은 기본으로 다른 시나리오에도 같은 일정으로 들어가고, 공식 시나리오에 새 일정 리비전이 생기는 저장은 기본으로
  공식 발행까지 합니다. 그 시나리오에 일정이 없는 호기는 그 시나리오 계산에 들지 않습니다(「일정 없음 n대」).
- **이름 바꾸기는 같은 호기입니다**(2026-10-24 결정 G4·R2) — Space 배치 편집기 「이름 바꾸기」 로 바꾼 호기는 호기 키가
  그대로라 저장하면 모든 설비 시나리오의 일정·비가동이 새 이름을 따라갑니다. 저장 안 한 이름 바꿈은 Space 상자와 설비 마스터 탭 맨
  위에 같은 「이름 바꿈 n건」 목록으로 보입니다. 설비 마스터 탭 편집표의 설비명 칸·붙여넣기·CSV 는 설비명이 키라 고치면 「지운 + 새
  호기」 입니다(개편으로 설비 마스터 호기 상세가 이름 바꾸기를 맡습니다). 지우는 호기가 다른 설비 시나리오에도 일정이 있으면
  설비 마스터 탭 저장 칸의 확인 체크를 켜야 저장됩니다(체크는 그 글에 묶여, 그 사이 일정이 든 시나리오가 늘면 풀립니다).
- 설비 마스터 탭·붙여넣기의 배치 칸(동·층·좌표·크기·레이아웃표시)은 Space 와 같은 판정입니다 — 공식 설비 시나리오에서는 공식
  배치, 가정에서는 그 시나리오에만(공식과 다른 것만) 저장됩니다(칸 머리 도움말 「배치 — …」). 배치 편집이 잠긴 동안(남이 그
  시나리오에 다른 배치를 저장함 등)에는 있던 호기의 배치 칸 고침을 저장본 값으로 되돌립니다. 「있던 호기」 는 저장하면 같은 호기가
  되는 행이라, 지운 호기를 같은 설비명으로 다시 넣어도 같은 호기입니다. 배치를 고쳐 둔 사이 공식이 다른 시나리오로 바뀌어 그 편집이
  들어갈 자리(공식 배치 ↔ 가정 배치)가 달라지면 그 배치 변경은 저장하지 않습니다(Space 「배치 변경만 버리기」).
- **가정 설비 시나리오의 Space 배치**(2026-10-24 결정 LY1~LY6 — 설비 마이그레이션 `0031`, 설비 시나리오 2단계): 호기 위치·층
  도면 요소·Main 설비명 위치는 시나리오마다 따로이고 **공식과 다른 것만** 그 시나리오의 일정 리비전에 남습니다 — 손대지 않은
  호기·요소는 공식을 따라갑니다. FAB 전체·층 사용·층 캔버스·배경 도면은 공통이라 **공식 설비 시나리오에서만** 고칩니다. Space
  현황은 사이드바에서 고른 설비 시나리오의 배치를 그리고(가정이면 머리에 「가정 배치 · 공식과 다른 호기 n대」·배지 「가정 배치」),
  가정 시나리오에서 옮긴 호기·도면 요소·Main 설비명 위치는 그 시나리오의 새 리비전으로 저장되어 공식 배치는 바뀌지 않습니다.
  설비 마스터 탭의 배치 칸도 같은 규칙이고, 붙여넣기·CSV 는 가정 세션에서 「배치 칸도 붙여넣기」(기본 끔)를 켜야 있던 호기의 배치
  칸을 바꿉니다. 묶음 구성(Main 설비)은 공통이라 가정 세션에서 공식 층이 다른 호기를 한 묶음으로 묶는 고침은 제출·미리보기에서
  막습니다. 층 사용을 끌 때는 가정 배치에만 호기가 있는 층도 확인합니다. 남이 그 시나리오에 다른 배치를 저장했거나 그 사이 공식이 바뀌어 편집 자리가 달라지면 배치 편집이 잠기고
  「최신 rM 불러오기」·「배치 변경만 버리기」 가 섭니다. 가정 세션에서 넣은 새 호기는 공식 배치가 비어 「동·층 미정」 입니다 —
  Space 저장 상자의 「새 호기를 다른 설비 시나리오에도 넣기」 는 가정 세션에서 기본 끔입니다. 배치 차이가 있는 시나리오는 공식으로 발행하지 않습니다(배치를 공식으로 올리는 기능은 다음
  단계). 「이 리비전으로 되돌리기」·「여기서 새 시나리오」 는 그 리비전의 배치 차이도 옮깁니다. 위치는 가용대수·확보율 계산에
  들지 않습니다.
- **공식과 견주기·차이 관리**(설비 시나리오 2단계 S4): Space 경로 줄 끝 「공식과 견주기」 를 켜면 가정 배치에서 옮긴 호기의 공식
  자리를 점선으로 그립니다(같은 층이면 가는 선, 다른 층이면 「→ C2 3F」, 다른 층에서 온 호기는 「← C1 2F」 — FAB 전체에서는 층 목록
  「공식과 다름」 칸과 층 블록 풍선 한 줄 — 공정소분류 필터로 거른 호기는 세지 않습니다). 시나리오 관리 › 설비 시나리오의 시나리오 표 「저장된 배치 차이」·리비전 표 「배치」 가
  차이 행 수를 보이고, 가정 시나리오에 「배치 차이 모두 지우기」(차이만 비운 새 리비전 — 지운 리비전은 남아 되돌리기로 되살립니다)가
  섭니다. 「공식으로 발행」 은 배치 차이가 있으면 까닭과 그 경우에 서는 빠져나갈 길(옛 리비전이면 되돌린 뒤 지우기)과 함께 막히고,
  공식과 같아진 차이만 남았으면 정리한 새 리비전으로 발행한다고 미리 적습니다(발행 뒤 그 시나리오를 보던 세션은 새 리비전으로
  옮깁니다). 남이 공통을 저장해도 저장하지 않은 가정 배치 편집(호기 위치 — 편집기로 옮긴 모듈 묶음 포함)은 새 저장본 위에 다시
  얹습니다. 층 캔버스 팝업은 가정
  배치의 요소·호기가 새 캔버스 밖이면 미리 말합니다. 옛 판(설비 `0031` 을 모르는 배포)이 가정 시나리오에 저장해 배치안이 빠진
  리비전은 리비전 표에 「옛 판 저장 — rN 배치 빠짐」 으로 보입니다(그 rN 으로 되돌리면 되살아납니다).
- 기존 설비 리비전은 `0027` 이 「운영 일정」 시나리오의 같은 번호 리비전으로 옮기고(머리만 넣고 스냅샷은 복사하지 않음)
  이관 시점 최신이 공식 v1 입니다. **이 배포부터 옛 배포 ZIP 으로 되돌리지 않습니다** — 되돌림은 백업 복원뿐입니다(사내
  런북 4-2 — `0031` 을 실은 배포부터는 직전 배포의 백업으로). 비교 화면·보관·삭제는 다음 단계입니다(`docs/TODO.md`).

### Space 층 사용 상태

Space 현황 FAB 전체 아래 층 목록 표의 `사용 편집` 에서 층마다 「사용」 또는 「비활성」 을 고르고 비활성 사유를 20자까지
직접 적습니다(비우고 끄면 「사용 안 함」, 2026-10-26 결정 — 마이그레이션 없음) — 동 머리로 그 동 6개 층을 한꺼번에 「사용 안
함」·「생산라인 아님」 으로 바꿀 수 있습니다(설비 마이그레이션 `0029`, 2026-10-24 결정). 사유는 적은 글 그대로 보이고 FAB
도면 블록에서는 길면 「…」 로 줄입니다. 모두에게 같은 공용 설정이고 설비 시나리오와 상관없습니다. 비활성 층은 FAB
도면에서 회색 빗금으로 흐려져 눌러도
열리지 않고, 층 목록 맨 아래 접힌 「비활성 층 n개」 에서 열어 봅니다. 층 바로 가기·배치 편집기 「다른 층으로 보내기」·
가용설비 현황 설비 마스터 탭의 동·층 칸 선택지에서 빠지지만 **설비 마스터의 동·층 값과 저장 검사는 그대로**입니다 — 호기가 남은 층을 끄면 확인만
받고, 그 호기는 Space 목록·도면에서만 숨습니다.

## 보조 스크립트

모두 저장소 루트에서 `.venv` 의 Python 으로 돌립니다. DB 를 여는 스크립트는 앱을 끄고 돌립니다 — 앱은 rerun 하는 동안만 DB 를 쥐어, 쉬는 앱 아래에서 돌면 잠금에 걸리지 않고 그 앱 화면을 막습니다. 런북 8장의 두 스크립트(`inspect_real_data_checks.py`·`inspect_wf_division.py`)는 운영 DB 를 열기 전에 앱 프로세스를 보고 멈추고, `--database` 로 사본을 주면 앱을 보지 않습니다. 사본 전용인 `inspect_revision_calculations.py`·`benchmark_home.py --data-dir` 는 운영 DB 자리(운영 DB 와 같은 파일 · 저장소 `data/` 아래 · git 저장소 안)를 거절합니다 — 사본은 저장소 밖에 둡니다.

| 스크립트 | 하는 일 |
|---|---|
| **초기화·적재** | |
| `bootstrap_builtin_seed.py` | 빈 저장소에 내장 합성 시나리오·공식버전을 만든다 |
| `bootstrap_initial_duckdb_scenario.py` | 개발용 Core Data 초기 시나리오를 만들거나 안전하게 바꿔 끼운다 |
| `generate_sample_core_data.py` | 합성 Core Data CSV 를 다시 만든다(이미 연장한 파일에 다시 돌려도 결과가 같다) |
| **DB 운영** | |
| `compact_duckdb.py` | DuckDB 빈 공간을 재구축으로 걷어낸다(인자 없으면 두 DB, `--dry-run`·`--keep-backup`). 앱을 내린 뒤 |
| `sync_object_storage.py` | 오브젝트 스토리지 스냅샷 진단·초기화와 수동 pull·push |
| **검증·측정** | |
| `benchmark_home.py` | HOME 의 콜드·웜·토글별 rerun 시간. 기본은 합성 표본, `--data-dir <사본 폴더>` 면 실 DB 사본 |
| `validate_duckdb_persistence.py` | Core Data 변환과 DuckDB 왕복 통합 검증(Windows·Excel·xlsb 필요) |
| `compare_legacy_results.py` | 원천에 보존된 기존 결과와 신규 계산값을 대조해 요약·상세 CSV 를 만든다 |
| **사내 실데이터 확인(읽기 전용 — 값은 찍지 않고 개수만)** | |
| `inspect_real_data_checks.py` | 기존 결과 대조 분포·원천 `RQ_REQB` 소요기준·설비 DB(공식 설비 시나리오 — 8-4 에 `0027` 이관 확인 줄·`0031` 가정 배치 차이·옛 코드 흔적)·BigDataQuery·HOME 월 축에서 빠지는 계획 달 수·「지금대로」 결정의 유병률(센서스)을 재고, 끝에 리뷰 압축본에 옮길 「전송용 요약」(짧은 키와 수 + 확인 코드)을 찍는다(런북 8장). `--check-summary <파일>` 은 DB 없이 옮겨 적은 압축본을 다시 센다 |
| `inspect_revision_calculations.py` | 모든 리비전의 Capa → 소요대수 → 확보율을 다시 돌린다(런북 6-3 a, `--database` 사본 필수 — 운영 DB 자리는 거절) |
| `inspect_wf_division.py` | 기준정보·리비전의 `WF 구분` 값 분포를 센다(`--database` 로 사본도) |
| `inspect_top_remigration.py` | `Top` 재이관 마이그레이션의 전제를 잰다 |
| `audit_top_remigration.py` | `0026` 적용 뒤 이관 결과의 오염·누락을 점검한다 |
| `check_deploy_screens.py` | 런북 7장 화면 확인을 별도 포트 앱과 저장소 밖 Playwright 로 돌린다 |
| **따라하기 가이드** | |
| `build_page_guide.py` | 앱 사본을 띄워 가이드를 찍고 원고 · 덮어쓰기와 한 파일 HTML 로 묶는다(`--example` 합성 예시판 · `--internal` 사내판, 결과는 저장소 밖) |
| `check_page_guide.py` | 덮어쓰기 · 매개값 · 촬영 결과를 뼈대에 대 보고 리뷰 한 줄을 낸다 |
| `guide_example_seed.py` | 예시판이 띄울 합성 시나리오 DB 를 만든다(생성기 `--example` 의 시드 단계) |
| `page_guide_core.py` · `page_guide_capture.py` · `page_guide_helpers.js` | 생성기 부품 — 조립 · 덮어쓰기(순수), Playwright 촬영, 페이지 도우미 |
| **배포·병행 개발** | |
| `build_deploy_package.py` | 사내 배포 ZIP 을 만들고 금지 파일을 검사한다(미커밋 수정·`origin/main` 과 다른 HEAD·이미 있는 같은 stamp 태그·런북 7장 stamp·자리표·화면 확인 수가 어긋나면 멈춤) |
| `apply_deploy_package.py` | 사내에서 배포 ZIP 을 송장대로 검증·적용하고 커밋한다 |
| `container_start.py` | C-DEP CD 이미지의 `CMD` — 환경변수로 `bigdataquery` 설치·로그인 토큰 파일을 갖추고 결과를 남긴 뒤 앱(`streamlit run app.py --server.port 8080`)으로 바뀐다. 개발·사내 PC 에서는 부르지 않는다 |
| `new_worktree.ps1` | 병행 개발용 작업 폴더를 브랜치·가상환경·격리 확인까지 한 번에 만든다 |
| `check_worktree_isolation.py` | 작업 폴더가 제 가상환경·코드·DuckDB 만 쓰는지 확인한다 |

## 문서 지도

| 문서 | 무엇이 있나 |
|---|---|
| `README.md` | 이 문서 — 처음 보는 사람용 안내(무엇인가·화면·설치·실행·데이터) |
| `AGENTS.md` | **개발 규칙의 정본** — 파일별 책임·표 계약·상태/캐시 불변조건·계산·Streamlit 규칙·병행 개발 |
| `CLAUDE.md` | 에이전트 진입점 — AGENTS 의 요약, 사외·사내 가르기, 명령 |
| `HANDOFF.md` | 직전 세션의 상태와 다음 할 일. 정본이 아닌 스냅샷이라 위 문서·코드와 어긋나면 그쪽을 따름 |
| `docs/TODO.md` | 확정된 업무 결정의 이력과 작업 목록 |
| `docs/data_model.md` | DuckDB 두 개의 스키마·저장 규칙·공간 회수 |
| `docs/design_system.md` | 색·서체·표 밀도와 화면 구성 규칙 |
| `docs/migration_catalog.md` | SQL 마이그레이션마다의 목적·출처 카탈로그 |
| `docs/wsl_dev_environment.md` | 사외 개발 자리(데스크탑 WSL) 준비·명령·앱 띄우기·배포 |
| `docs/dual_env_workflow.md` | 사외·사내 두 환경의 역할과 작업 절차, 코드 밖 산출물(사외 뼈대 · 사내 완성), 리뷰 양식(사람이 옮겨 적는 압축본 `review/<stamp>.md` + 사내에 남는 전문 `.full.md`) |
| `docs/internal_update_runbook.md` | 사내에서 배포 ZIP 을 받아 적용하는 한 번의 작업 런북 — 실 DB 사본 확인(6-3)·실데이터 확인(8장)·사본으로만 하는 사내 탐색(9장)·따라하기 가이드 사내판 만들기(10장) 포함 |
| `docs/bigdataquery_webide_setup.md` | 사내 WebIDE 에서 BigDataQuery 조회를 여는 설치·로그인·계정 설정 |
| `docs/objectstore_setup.md` | 사내 오브젝트 스토리지 연동 절차 |
| `docs/parallel_agent_briefing.md` | 병행 개발 에이전트의 시작 절차와 하루 흐름(규칙은 AGENTS 14장) |
| `docs/scenario_merge_shift_implementation.md` | 시나리오 월 머지·연도 Shift 구현 설명 |
| `docs/equipment_ui_codex_review.md` | 가용설비 현황 개편 후보안(검토 기록) |
| `docs/internal_claude_settings.json` | 사내 `.claude/settings.json` 템플릿(6단계) |
| `src/capa_simulation/guides/` | 화면별 `Guide` 원문(Markdown) |
| `static/guides/howto/` | 따라하기 가이드 합성 예시판(한 파일 HTML — 뼈대는 `src/capa_simulation/guides/howto/`, 만들기는 `scripts/build_page_guide.py --example`) |
| `config/data_contract.json` | Core Data 78컬럼 계약 |
| `index.html` | 대표 발표 자료 한 파일(앱과 무관, 숫자는 합성 샘플). 원본은 저장소 밖 쇼케이스 폴더(`AGENTS.md` 3장 끝) |

## 아직 없는 것

- 사내 실데이터 대조의 남은 결론 — BigDataQuery 상세 조회 창, Wafer `WF수(매)` 경로 단위와 소요대수 대조
  (확인 절차는 런북 8장)
- 시나리오·공식버전·표시순서 관리의 사용자 권한과 승인자 이력(설비 리비전은 「저장자」 선택 입력만)
- 설비 시나리오 2단계 — 시나리오끼리 일정 비교, 보관·영구 삭제·순서, 공통 대장 이력 표
- 화면 탭 2단계 — 탭을 끌어내 떠 있는 창으로 보기, 끌어서 차례 바꾸기(무엇을 띄울지 결정 대기)
- BOX·PCB 부하량과 Capa 산식(지금은 계산에서 빼 둠 — 제외가 아니라 추가 예정), `MCP_Chip_Ratio` 소요대수 보정
- 결과 Excel 내려받기와 계산 실행 이력(화면 표·제외 목록의 CSV 내려받기는 있음)
- 실적효율·생산실적·재공 실적 DB 의 원천 조회와 컬럼·시점 정의, 공정·STEP·제품 매핑
