# 모듈 지침서 — 담당자 에이전트용

이 문서는 동료가 만든 Streamlit 화면을 이 앱(`S.PKG CAPA AX Management`) 안의 별도 화면으로 올리는 법이다.
읽는 쪽은 **모듈 하나를 맡은 에이전트**다. 이 저장소의 다른 규칙은 몰라도 된다. 이 문서만 따른다.

이 문서에는 사람이 둘 나온다.

- **담당자** — 모듈을 맡아 너와 대화하는 사람이다. 전문 개발자가 아니다(아래 「사람은 비전문가다」).
- **앱 관리자** — 배포를 적용하고 승인하는 다른 한 사람이다. 이 대화 안에 없다.

사람용 안내는 `docs/module_colleague_guide.md` 다 — 담당자가 읽는 글이고, 너는 이 문서만 따른다(둘이 어긋나 보이면 이 문서가 맞다).

예시는 모두 합성이다. 모듈 id 는 `demo_*` 이고 값은 지어낸 것이다. 실제 제품·고객·공정·설비·사람 이름을 예시로 바꿔 넣지 않는다.

## 사람은 비전문가다

담당자는 전문 개발자가 아니다. 너(에이전트)와 함께 바이브 코딩으로 화면을 만드는, 아직 익숙하지 않은 사람이다. 0장 첫 지시 11번을
이렇게 지킨다.

- **하는 일과 까닭을 쉬운 한국어로 먼저 말한다.** 무엇을 왜 하는지, 끝나면 무엇이 달라지는지를 두세 문장으로 말한다. 낯선 낱말은 풀어 쓴다.
- **위험한 일은 하기 전에 묻는다.** 커밋 · 파일 지우기 · 되돌리기 어려운 일이 그렇다. 담당자가 「네」 라고 하기 전에는 하지 않는다.
- **`modules/<id>/` 밖의 일은 네가 하지 않는다.** 묻고 멈춘다. 코어 · 다른 모듈 · 설정 파일을 고쳐야 하거나 새 패키지가 필요하면, 담당자가
  앱 관리자에게 「사외 요청」 한 줄을 전하게 한다(0장 4 · 5, 6장, 8-1). 승인을 받아 와도 폴더 밖은 사외가 고친다.
- **점검은 네가 돌린다.** `scripts/check_module.py <id>`(모듈 시험도 이 줄이 돌린다 — 7장)를 네가 돌리고, 화면은 앱에서 열어 본다(7장
  「앱에서 보는 줄」 — 앱은 담당자가 띄우니 무엇을 눌러 볼지를 짚어 준다). 결과는 「통과」 또는 「고칠 것 n개 — 무엇을 어떻게」 처럼
  쉬운 말로 알린다.
- **담당자가 traceback(오류 원문)을 읽을 수 있다고 여기지 않는다.** 오류가 나면 네가 읽고 「무엇이 잘못됐고 어떻게 고칠지」 를 한두 문장으로
  말한다. 원문은 담당자가 보자고 할 때만 보인다.

---

## 0. 에이전트에게 줄 첫 지시

담당자는 새 대화를 열 때 아래 블록을 그대로 붙여 넣는다. `<id>` 는 자기 모듈 id 로 바꾼다(3-2).

```text
너는 S.PKG CAPA AX Management 앱의 모듈 <id> 를 맡은 에이전트다. 너와 대화하는 사람은 이 모듈의 담당자다.
앱 관리자는 배포를 적용하고 승인하는 다른 한 사람이다 — 이 대화 안에 없다.
네 변경은 PR 로만 main 에 들어간다 — 자기 가지 module/<id>/<주제> 에서 커밋하고, 담당자가 그 가지를 푸시해 PR 을 열고, 앱 관리자가 점검한 뒤 합친다(8-2).
1. 고칠 수 있는 곳은 modules/<id>/ 뿐이다. data/modules/<id>/ 는 화면이 실행 중에 쓰는 자리라 읽기만 한다 — 손으로 파일을 넣거나 고치지 않고, 지울 때는 먼저 묻는다. 그 밖(app.py·app_pages/·src/·tests/·scripts/·docs/·config/·루트 파일·다른 모듈)도 읽기만 한다.
2. 이 문서(docs/module_guide.md)만 따른다. CLAUDE.md·AGENTS.md 는 코어 규칙이라 네 일이 아니다.
3. 코어는 capa_simulation.module_api 하나만 import 한다. 같은 모듈의 파일은 from modules.<id> import <이름> 으로 부른다.
4. 패키지를 설치하지 않는다(uv add·uv pip·pip install·uv sync 모두). 필요하면 담당자에게 「<id>: <패키지>==<판> <까닭>」 한 줄을 앱 관리자에게 전해 달라고 한다.
5. 앱 관리자의 승인은 이 대화 안에서 받을 수 없다. 새 모듈을 처음 올리는 것·성숙도 L2 는 담당자가 앱 관리자에게 승인을 받아 온 뒤에만 하고, 커밋 본문과 PR 본문에 「승인: 앱 관리자 <YYYY-MM-DD>」 를 적는다. 폴더 밖 변경은 승인을 받아도 네가 하지 않는다 — 담당자가 앱 관리자에게 전하고, 앱 관리자가 승인하면 「사외 요청」 으로 사외가 고쳐 배포한다.
6. 커밋은 자기 가지에만 한다 — main 에는 커밋하지 않는다. 제목은 module(<id>): <무엇> 이고 modules/<id>/ 만 담는다(파일 이름으로 git add — git add -A·git add .·git commit -a 금지). 가지 푸시와 PR 열기는 담당자가 한다.
7. 푸시가 거절되면 git pull --rebase 뒤 다시 푸시한다. git push --force·--force-with-lease 는 자기 가지에도 절대 쓰지 않는다 — 앱 관리자가 점검한 PR 과 어긋난다.
8. 위젯 콜백은 ctx.callback(함수) 로, 프래그먼트·팝업 본문은 with ctx.guard(): 로 감싼다. st.cache_* 는 modules/<id>/cache.py 에만 둔다.
9. 끝내기 전에 uv run --no-sync python scripts/check_module.py <id> 가 「통과」 여야 한다. 시험도 이 줄로 돌린다.
10. 실데이터 식별값(제품·고객·공정·설비·사람)을 id·파일 이름·커밋 메시지·시험 데이터에 쓰지 않는다.
11. 담당자는 전문 개발자가 아니다. 하는 일을 쉬운 말로 설명하고, 커밋·삭제·폴더 밖 일처럼 되돌리기 어려운 것은 먼저 묻고, 시험과 check_module.py 는 담당자에게 맡기지 말고 네가 돌려 결과를 보여 준다.
```

이 지시와 이 문서의 나머지는 같은 말이다. 자세한 까닭은 아래 장에 있다.

---

## 1. 목적과 범위

- 동료가 따로 만든 Streamlit 기능을 이 앱 웹 안의 **별도 화면**으로 띄운다.
  - 사이드바에 상자 「모듈」 하나가 선다. 자리는 계산 그룹(Static · 실행 관리 · Dynamic) 다음, Support 상자(Admin Area) 앞이다.
  - 상자 머리 화면은 색인(켜진 모듈과 그 화면 링크)이고, 모듈 화면은 그 아래 링크로 든다.
  - 켜진 모듈이 없으면 상자도 없다.
- **이번 단계는 같은 웹에 보이기만 한다.** 코어(이 앱의 계산·DB)와 데이터를 주고받지 않는다. 데이터 연계는 다음 단계다(10장).
- 정본은 **폴더로 가른다**(2026-11-01 결정 — 「모델 2」).

| 무엇 | 정본 | 누가 고치나 |
|---|---|---|
| **코어** — 배포 ZIP 이 싣는 것 전부(`app.py`·`app_pages/`·`src/`·`tests/`·`scripts/`·`docs/`·`config/`·루트 파일) | 사외 저장소 | 사외만. 이 저장소에서는 읽기만 한다 |
| **모듈** — `modules/<id>/` | 이 저장소 | 그 모듈의 담당자(너) |
| **모듈 데이터** — `data/modules/<id>/` | 그 PC · 서버의 파일 | 화면이 실행 중에 만든다. git 에도 이미지에도 넣지 않는다 |

- **별도 저장소가 아니라 같은 저장소다.** 배포 서버(C-DEP CD)는 이 저장소 하나로 이미지를 만든다
  (`docker/Dockerfile-prod` 의 `COPY . /project/`, 셸 없음, 시작 명령 고정). 둘째 저장소는 서버에 닿지 않는다.
- **iframe · 별도 프로세스는 쓰지 않는다.** 모듈 화면은 앱과 한 프로세스에서 돈다. 그래서 `st.iframe` 도 쓰지 않는다(M03).
- 사외는 모듈 코드를 보지 않는다. 배포 ZIP 은 `modules/` 를 **싣지도 덮지도 지우지도 않는다.**

---

## 2. 쓸 수 있는 자리

| 자리 | 너(에이전트)는 | 까닭 |
|---|---|---|
| `modules/<id>/` | 쓴다 | 네 모듈의 코드다 |
| `data/modules/<id>/` | 읽기만 한다 — 화면이 실행 중에 쓴다. 손으로 넣거나 고치지 않고, 지울 때는 먼저 묻는다 | 네 모듈의 데이터 자리다 — 코드에서는 `ctx.data_dir`. 손으로 넣은 파일은 그 PC 에만 있다(아래) |
| 그 밖 전부 — `app.py`·`app_pages/`·`src/`·`tests/`·`scripts/`·`docs/`·`config/`·루트 파일·다른 모듈 | 읽기만 한다 | 코어와 남의 모듈이다. 고쳐도 다음 배포가 덮는다 |
| 코어 두 DB(`data/capa_simulation.duckdb`·`data/equipment_availability.duckdb`)·`data/input`·`data/output`·`data/temp`·`review/`·`.deploy/` | 열지도 않는다 | 운영 데이터와 배포 기록이다 |

- 배포 ZIP 은 `modules/` 를 싣지도 덮지도 지우지도 않는다. `data/modules/` 도 지우지 않는다.
- **첫 배포 주의** — 이 지침서가 실린 배포를 앱 관리자가 적용하기 **전에는** 저장소에 `modules/` 를 올리지 않는다(PR 도 합치지 않는다).
  그 전의 적용기는 모듈 파일을 「사외에서 지워짐」 으로 보고 지운다. 앱 관리자가 「적용을 마쳤다」 고 알린 뒤에 시작한다.

### 데이터

- v1 모듈 데이터는 **화면이 스스로 만든다** — 화면에서 파일을 올려 받거나, 조회한 결과를 저장한다.
- 손으로 넣은 파일은 그 PC 에만 있다. 앱 관리자 PC 의 운영 앱에도 배포 서버에도 닿지 않는다. 「내 PC 에서는 된다」 의 흔한 원인이다.
- 합성 시드가 필요하면 `modules/<id>/assets/` 에 1 MB 아래의 합성 파일만 둔다(읽기만 한다).
- **`ctx.data_dir` 가 비어 있어도 화면이 빈 상태로 서야 한다.** 스모크 시험이 빈 임시 자리로 도는 것이 그 확인이다.
- **운영 모듈 데이터는 백업이 없다.** 잃어도 되는 것만 둔다. 배포 서버 컨테이너에서는 재배포 때 사라질 수 있다.
- 모듈 DB(DuckDB · SQLite)가 필요하면 `ctx.data_dir` 안에 둔다. 표를 만들고 고치는 일(마이그레이션)도 네 몫이고 코어 번호와 상관없다.
- **모듈 코드 폴더에는 실행 중에 쓰지 않는다.** 쓰기는 `ctx.data_dir` 만이다. 코드 폴더에 쓴 파일은 커밋되지 않아 어느 점검에도
  보이지 않는다(M13 이 경고하고, 시험 러너는 실패로 만든다).
- **상대 경로로 쓰지 않는다.** `open("notes.txt", "a")` · `Path("out") / "x.csv"` · `frame.to_csv("rows.csv")` 처럼 쓰면 앱의 작업
  폴더 — 앱을 띄운 저장소의 뿌리(앱 관리자 PC 에서는 운영 체크아웃) — 에 말없이 생긴다. 독립 앱에서 옮긴 코드에 가장 흔히 남는
  찌꺼기다. 늘 `ctx.data_dir / "<이름>"` 으로 쓴다(M13 이 경고하고, 시험 러너는 저장소 안 쓰기를 실패로 만든다).

---

## 3. 모듈 꼴

### 3-1. 폴더

```text
modules/                       ← 이 저장소에만 있다(코어 정본에는 없다). 최상위 __init__.py 를 두지 않는다
  <id>/                        ← 폴더 이름 == module.json 의 id (대소문자까지)
    module.json                ← 선언(3-3)
    page.py                    ← 첫 화면(이름은 자유 — pages[].file). 모듈 폴더 바로 아래
    <다른 화면>.py
    <도움 코드>.py              ← 화면에서 from modules.<id> import <이름> 으로 부른다
    cache.py                   ← (선택) st.cache_* 는 이 한 파일에만(M12)
    tests/test_<id>_*.py       ← 시험. 적어도 스모크 하나(M14)
    README.md                  ← (선택) 무엇 · 담당 역할 · 화면 목록
    assets/                    ← (선택) 읽기만 하는 정적 파일. 데이터 꼴 파일은 1 MB 아래 합성만(M13)
data/modules/<id>/             ← ctx.data_dir — git·이미지 밖. 처음 쓸 때 생긴다
```

- `modules/` 바로 아래의 파일과, 이름이 `.`·`_` 로 시작하는 항목(`__pycache__` 등)은 모듈로 보지 않는다.
- `modules/__init__.py` 를 만들지 않는다. 만들면 `from modules.<id> import …` 가 깨질 수 있다.
- 모든 `.py` 첫 줄은 `# Purpose: <이 파일이 하는 일 한 문장>` 이다(M13). 이 줄도 폭 100칸 안이다 — 한글은 한 자가 2칸이라
  45자 안팎에서 넘는다(M15 · 4장).
- 폴더·파일 이름에 대문자를 쓰지 않는다(M13).

### 3-2. id

- 소문자로 시작하고 소문자 · 숫자 · 밑줄만 쓴다. 2 ~ 24자. 밑줄 둘 연속과 끝 밑줄은 안 된다.
  정규식으로는 `^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$` 다.
- 파이썬 예약어(`import`·`class`·`global`·`async` 등)는 안 된다. `from modules.import import x` 는 문법 오류다.
- 소문자만 쓰는 까닭 — Windows 는 대소문자를 가리지 않고 배포 서버(Linux)는 가린다. `Modules/Demo` 꼴은 Windows PC 에서는 보이는데
  배포 서버에서는 사라진다.
- **id 에 실제 제품·고객·공정·설비·사람 식별값을 넣지 않는다.** 점검이 거르지 못한다.
- id 가 쓰이는 곳:
  - 세션 키 접두 `mod_<id>__`(밑줄 둘) — `ctx.key("x")` 가 붙인다.
  - 화면 주소 `mod-<id>-<slug>` — 북마크된다. slug 를 바꾸면 옛 주소가 끊긴다.
  - 데이터 자리 `data/modules/<id>/`.
  - 커밋 제목 접두 `module(<id>):`.

### 3-3. `module.json`

JSON 이다. UTF-8 로 쓴다(BOM 이 붙어도 받는다). 64 KB 까지. 주석은 못 쓴다. **아래 표에 없는 칸이 있으면 실패**다(`enable` 같은 오타를 잡는다).

```json
{
  "id": "demo_memo",
  "name": "데모 메모",
  "api": 1,
  "owner": "데모 담당",
  "enabled": true,
  "maturity": "L0",
  "description": "합성 메모를 적어 두고 종류별로 세는 예시 모듈",
  "order": 100,
  "pages": [
    {"slug": "main", "file": "page.py", "title": "데모 메모", "icon": ":material/edit_note:", "order": 10}
  ]
}
```

| 칸 | 필수 | 규칙 |
|---|---|---|
| `id` | 예 | 3-2 규칙. 폴더 이름과 같아야 한다 |
| `name` | 예 | 모듈 이름. 1 ~ 30자. 색인 화면 · 오류 카드 · Admin 에 쓰인다 |
| `api` | 예 | 정수. 요구하는 `module_api` 큰 판. 지금은 `1` |
| `api_minor` | 아니오 | 정수 0 ~ 99, 기본 0. 요구하는 최소 작은 판. 코어보다 크면 그 모듈은 「API 1.<n> 필요 — 이 코어는 1.<m>」 으로 실패한다 |
| `owner` | 예 | 담당 **역할 이름** 1 ~ 30자(예: `데모 담당`). 사람 이름 · 사번을 쓰지 않는다 |
| `enabled` | 예 | JSON 불 `true`/`false`. 글자 `"true"` 는 실패 |
| `maturity` | 예 | `"L0"` · `"L1"` · `"L2"`(3-4) |
| `description` | 아니오 | 0 ~ 120자 |
| `order` | 아니오 | 정수 0 ~ 999, 기본 100. 모듈끼리의 차례(같으면 id 차례) |
| `pages` | 예 | 화면 1 ~ 8개의 배열 |
| `pages[].slug` | 예 | id 와 같은 정규식, 1 ~ 24자. 모듈 안에서 겹치지 않는다. 주소 끝이 된다 |
| `pages[].file` | 예 | `^[a-z][a-z0-9_]*\.py$`. 모듈 폴더 **바로 아래**의 보통 파일(심볼릭 링크 · 하위 폴더 안 됨). 디스크의 이름과 **대소문자까지** 같아야 한다 — Windows 는 `Page.py` 를 `page.py` 로도 열어 주지만 배포 서버는 못 연다 |
| `pages[].title` | 예 | 1 ~ 24자. 사이드바 · 탭 이름이 된다. 「(구현중)」 을 넣지 않는다(성숙도가 붙인다). 코어 화면 이름 · 「현황 요약」 과 같으면 실패. 다른 켜진 모듈의 화면 이름과 같으면 모듈 차례(`order`, 같으면 id)가 **뒤인 모듈 전체**가 실패한다(아래). 모듈 안에서도 겹치지 않는다. Markdown 으로 그려지므로 별표 · 밑줄 · 역따옴표 · 대괄호 · 물결 · 역슬래시 · 샵 · 꺾쇠 · 세로줄 · 달러 · 쌍점을 넣으면 실패 |
| `pages[].icon` | 아니오 | `^:material/[a-z0-9_]+:$` 에 **정확히** 맞아야 한다. 앞뒤 공백 · 이모지는 안 된다. 기본은 `:material/extension:` |
| `pages[].order` | 아니오 | 정수 0 ~ 999. 기본은 배열 차례 × 10. 모듈 안의 화면 차례(같으면 slug 차례) |

- 선언이 틀리면 그 모듈은 「실패」 로 등록되지 않는다. 다른 모듈과 앱은 그대로 선다. 까닭은 앱 관리자가 Admin 「모듈 상태」 에서 본다.
- **모듈끼리 화면 이름이 겹치면 차례로 가른다 — 나중에 넣은 쪽이 아니다.** 모듈 차례(`order`, 같으면 id 차례)가 뒤인 모듈이
  **겹치지 않는 화면까지 통째로** 「실패 · 화면 이름 겹침: <이름> — 차례가 앞인 모듈 <id>」 가 된다(코어 이름과 겹치면 「— 코어 화면」).
  새 모듈의 `order` 가 작거나 id 가 앞이면 이미 돌던 모듈이 빠진다. 그래서 새 화면 이름은 앱의 「모듈」 색인 화면에서 다른 모듈의
  화면 이름을 보고 고른다. 점검은 차례가 앞인 모듈에도 M01 경고(「… 차례가 뒤인 모듈 <id> 도 써서 그 모듈 전체가 실패합니다」)를
  낸다 — 그 경고가 보이면 담당자가 앱 관리자에게 알려 어느 쪽이 이름을 바꿀지 정한다.
- `enabled: false` 여도 선언이 틀렸으면 「꺼짐」 이 아니라 「실패」 다 — 고칠 것이 보이게 한다.
- **`module.json` 을 바꾸거나 모듈을 새로 넣으면 앱을 다시 띄워야 보인다.**

### 3-4. 성숙도

| 단계 | 뜻 | 사이드바 · 머리말 | 올라가는 조건 |
|---|---|---|---|
| `L0` Lab | 자기 데이터 · 합성 표본으로 돈다 | `(구현중)` | `check_module.py` 통과 + 진입 스모크 시험 |
| `L1` 연결 | 코어 공개 창구의 데이터를 읽는다(v2 부터 — v1 에는 데이터 창구가 없다) | `(구현중)` | 출력 계약 문서 + 배포 뒤 화면 확인 |
| `L2` 검증 | 실데이터 정합성을 확인했다 | 표기 없음 | 실데이터 읽기 전용 점검(집계만)으로 기준값 대조 통과 |
| (`L3` 통합) | 코어 계산이 모듈 출력을 쓴다 — 사외가 코어에 다시 구현하므로 그때부터 모듈이 아니다 | — | 사외 리뷰 |

- 표기는 `(구현중)` 하나다. `module.json` 의 `maturity` 칸은 `L0` · `L1` · `L2` 만 받는다.
- **`L2` 로 올리는 커밋은 앱 관리자의 승인을 받은 뒤에만 한다**(배지가 떨어져 「검증된 화면」 으로 읽힌다). 코드는 막지 않는다.

### 3-5. 화면 계약

- 화면 파일은 보통 Streamlit 스크립트다. 앱은 그 화면에 들어갈 때마다, 그리고 위젯을 만질 때마다 파일 전체를 처음부터 다시 돈다.
- 맨 위 차례는 늘 같다.
  1. `ctx = api.context(__file__)` — 모듈 문맥(id · 이름 · 데이터 자리 · 키 접두)을 받는다.
  2. `api.page_header(ctx, "<화면 이름>", description="<한 줄>")` — 머리말을 **한 번**, 맨 위에 그린다.
  3. 본문.
- 코어에서는 `from capa_simulation import module_api as api` 하나만 import 한다(부록 A).
- 화면 파일은 `__main__` 으로 돈다. 상대 import(`from . import x`)를 쓰지 않는다.
- 모듈 코드는 그 화면에 들어갈 때만 불러온다. 앱은 `module.json` 만 읽고 `.py` 를 미리 import 하지 않는다.

### 3-6. 같은 폴더 파일 import

- `import utils` 가 아니라 **`from modules.<id> import utils`** 로 쓴다.
- 까닭 — 앱은 저장소 뿌리에서 돈다. 맨이름 `import utils` · `from config import X` · `import data` 는 저장소 뿌리의 `config/` · `data/`
  같은 엉뚱한 자리로 풀려 「cannot import name … (unknown location)」 같은 오류가 난다. 독립 앱에서 통과하던 꼴이 앱에서 깨진다.
- 점검 M06 이 이 꼴을 오류로 잡는다. 시험 러너도 앱과 같은 길로 돌아 시험에서도 깨진다. 앱 안의 오류 카드도 「패키지가 없다」 고
  하지 않고 이 꼴을 안내한다.

### 3-7. 가장 작은 모듈 — 뼈대 만들기

1. 담당자가 앱 관리자에게 새 모듈 등록 승인을 받는다(id · 이름 · 무엇을 하는지 한 줄).
2. 새 가지를 만들고(8-2 의 1 — 예: `module/demo_hello/first`) 뼈대를 만든다. 뼈대 줄은 에이전트 설정에서 매번 묻게 해 두었다(8장) —
   담당자가 줄을 읽고 승인한다.

   ```powershell
   uv run --no-sync python scripts/new_module.py demo_hello --name "데모 인사" --owner "데모 담당"
   ```

   `--title "<첫 화면 이름>"` 을 주지 않으면 `--name` 을 첫 화면 이름으로도 쓴다. 모듈 이름(`--name`)은 30자까지지만 첫 화면 이름은
   24자까지이고 Markdown 글자(쌍점 등)를 못 쓴다 — `--name` 이 24자를 넘거나 그런 글자가 들면 `--title` 을 함께 준다. 아래 넷이 생기고,
   그 밖에는 아무것도 만들지 않는다
   (`data/modules/<id>/` 도 만들지 않는다).
   - `modules/demo_hello/module.json` — `api: 1` · `enabled: true` · `maturity: "L0"` · 화면 하나(`slug: "main"`, `file: "page.py"`).
   - `modules/demo_hello/page.py` — 아래.
   - `modules/demo_hello/tests/test_demo_hello_smoke.py` — 빈 데이터 자리에서 화면이 오류 없이 서고 제목이 맞는지 본다.
   - `modules/demo_hello/README.md` — 무엇 · 담당 역할 · 화면 목록.
3. 만든 `page.py` 는 이렇다. 콜백은 처음부터 `ctx.callback` 으로 감싼 꼴이다 — 이 꼴을 그대로 쓴다.

   ```python
   # Purpose: 데모 인사 모듈의 첫 화면을 그린다.

   import streamlit as st

   from capa_simulation import module_api as api

   ctx = api.context(__file__)
   api.page_header(
       ctx,
       "데모 인사",
       description="이 화면이 무엇을 하는지 한 줄로 적습니다.",
   )


   def _greet() -> None:
       st.session_state[ctx.key("greeted")] = True


   name = st.text_input("이름", key=ctx.key("name"))
   st.button("인사", key=ctx.key("greet"), on_click=ctx.callback(_greet))
   if name and st.session_state.get(ctx.key("greeted")):
       st.write(f"{name} 님, 반갑습니다.")
   ```

4. 점검을 돌린다 — `uv run --no-sync python scripts/check_module.py demo_hello`. 뼈대는 그대로 「통과」 다.
5. 그 가지에서 커밋한다(8장) — `git add modules/demo_hello` 뒤 커밋 본문에 승인 줄을 넣어 친다(둘째 `-m` 이 본문이다).

   ```powershell
   git commit -m "module(demo_hello): 새 모듈 뼈대" -m "승인: 앱 관리자 <YYYY-MM-DD>"
   ```

6. 담당자가 가지를 푸시하고 PR 을 연다 — 앱 관리자가 점검한 뒤 합친다(8-2 의 4 ~ 6). PR 본문에도 승인 줄을 적는다.

### 3-8. 예시 모듈 — 데이터 · 도움 코드 · 캐시가 있는 꼴 (`demo_memo`)

화면에서 합성 메모를 적어 자기 데이터 자리(`ctx.data_dir`)의 CSV 에 쌓고, 종류별로 센다. 파일은 다섯이다.

```text
modules/demo_memo/
  module.json                      ← 3-3 의 예시 그대로
  page.py                          ← 화면
  store.py                         ← 도움 코드 — 메모 파일 읽기 · 더하기(Streamlit 없음)
  cache.py                         ← 캐시 — 파일 판마다 한 번만 읽기
  tests/test_demo_memo_page.py     ← 시험
```

`modules/demo_memo/store.py` — 경로는 늘 인자로 받는다. 모듈 전역에 바뀌는 값을 두지 않는다.

```python
# Purpose: 데모 메모 모듈의 메모 파일(데이터 자리의 memo.csv)을 읽고 한 줄씩 더한다.

import csv
from datetime import datetime
from pathlib import Path

import pandas as pd

FILE_NAME = "memo.csv"
COLUMNS = ("시각", "종류", "내용")


def memo_path(data_dir: Path) -> Path:
    return data_dir / FILE_NAME


def version(data_dir: Path) -> int:
    """파일이 바뀌면 달라지는 수(파일이 없으면 0). 캐시 키로 쓴다."""
    target = memo_path(data_dir)
    return target.stat().st_mtime_ns if target.exists() else 0


def read(data_dir: Path) -> pd.DataFrame:
    target = memo_path(data_dir)
    if not target.exists():
        return pd.DataFrame(columns=list(COLUMNS))
    return pd.read_csv(target, encoding="utf-8")


def append(data_dir: Path, *, kind: str, text: str) -> None:
    target = memo_path(data_dir)
    is_new = not target.exists()
    with target.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if is_new:
            writer.writerow(COLUMNS)
        writer.writerow((datetime.now().strftime("%Y-%m-%d %H:%M"), kind, text))
```

`modules/demo_memo/cache.py` — 캐시 장식자는 이 파일에만 둔다. `ttl` 과 `max_entries` 를 단다. 데이터 자리는 **인자로** 받고 함수 안에서
`ctx` 를 읽지 않는다.

```python
# Purpose: 데모 메모 모듈의 캐시 — 메모 파일을 읽은 표를 파일 판마다 한 번만 만든다.

from pathlib import Path

import pandas as pd
import streamlit as st

from modules.demo_memo import store


@st.cache_data(ttl=600, max_entries=16)
def load(data_dir: str, version: int) -> pd.DataFrame:
    """`version` 은 파일이 바뀌면 달라져 새 칸을 쓰게 하는 키다."""
    return store.read(Path(data_dir))
```

`modules/demo_memo/page.py` — 키는 모두 `ctx.key(…)`, 콜백은 `ctx.callback(…)`, 프래그먼트 본문은 `with ctx.guard():` 다. 색은 `api.palette()` 다.

```python
# Purpose: 데모 메모 모듈의 첫 화면 — 합성 메모를 적어 데이터 자리에 쌓고 종류별로 센다.

import streamlit as st

from capa_simulation import module_api as api
from modules.demo_memo import cache, store

ctx = api.context(__file__)
api.page_header(ctx, "데모 메모", description="메모를 적어 두고 종류별로 셉니다.")

KINDS = ("확인", "요청", "기타")


def _save() -> None:
    text = st.session_state.get(ctx.key("text"), "").strip()
    if not text:
        return
    store.append(ctx.data_dir, kind=st.session_state[ctx.key("kind")], text=text)
    st.session_state[ctx.key("text")] = ""


with st.expander("새 메모", expanded=True):
    st.selectbox("종류", KINDS, key=ctx.key("kind"))
    st.text_input("내용", key=ctx.key("text"))
    st.button("저장", key=ctx.key("save"), on_click=ctx.callback(_save))

memos = cache.load(str(ctx.data_dir), store.version(ctx.data_dir))
if memos.empty:
    st.info("아직 저장한 메모가 없습니다.")
else:
    st.dataframe(memos, width="stretch", hide_index=True)


@st.fragment
def _counts() -> None:
    with ctx.guard():
        if st.toggle("종류별로 세기", key=ctx.key("show_counts")):
            st.bar_chart(memos["종류"].value_counts(), color=api.palette()["accent"])


if not memos.empty:
    _counts()
```

`modules/demo_memo/tests/test_demo_memo_page.py` — 빈 데이터 자리에서 서는지와 저장 단추를 본다. 데이터 자리는 늘 `tmp_path` 로 돌린다.

```python
# Purpose: 데모 메모 화면이 빈 데이터 자리에서 서고 저장 단추가 메모 한 줄을 쌓는지 본다.

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[1] / "page.py"


def _app(monkeypatch: pytest.MonkeyPatch, data_root: Path) -> AppTest:
    monkeypatch.setenv("CAPA_MODULES_DATA_ROOT", str(data_root))
    return AppTest.from_file(str(PAGE)).run(timeout=60)


def test_the_page_opens_on_an_empty_data_place(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _app(monkeypatch, tmp_path)

    assert not app.exception
    assert app.title[0].value == "데모 메모"
    assert app.info[0].value == "아직 저장한 메모가 없습니다."


def test_saving_a_memo_adds_one_row(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app = _app(monkeypatch, tmp_path)

    app.text_input(key="mod_demo_memo__text").input("합성 메모 하나")
    app.button(key="mod_demo_memo__save").click().run(timeout=60)

    assert not app.exception
    assert len(app.dataframe[0].value) == 1
```

- 이 다섯 파일이 이 문서의 규칙을 모두 지키는 꼴이다. 새 모듈은 이것을 본떠 쓴다.
- 시험 파일 이름은 `test_<id>_…` 로 시작한다. 다른 모듈의 시험과 이름이 겹치지 않게 한다.

### 3-9. 독립 Streamlit 앱 옮기기

이미 따로 도는 Streamlit 앱이 있으면 아래 차례대로 옮긴다. 한 단계씩 하고, 끝날 때마다 담당자에게 무엇을 바꿨는지 쉬운 말로 알린다.

1. `new_module.py` 로 뼈대를 만든다(3-7 — 새 모듈이라 앱 관리자 승인이 먼저다).
2. 원래 `app.py` 의 본문을 `page.py` 로 옮긴다. `app.py` 가 `st.navigation` 으로 화면을 고르는 진입 스크립트(라우터)면 그 파일은
   옮기지 않는다 — 아래 「라우터 앱」 차례를 따른다.
3. `st.set_page_config(…)` 를 지운다(앱이 한 번만 부른다 — M02).
4. `st.title(…)` 을 `api.page_header(ctx, …)` 로 바꾼다. 맨 위에 `ctx = api.context(__file__)` 를 둔다.
5. `st.sidebar.*` 를 본문 위의 `st.columns(…)` · `st.expander("조건")` 로 옮긴다(사이드바는 코어가 쓴다 — M04). 옮긴 조건 위젯에는
   **`persist_state="session"` 을 단다.** 독립 앱의 사이드바 위젯은 화면을 옮겨도 남지만, 본문 위젯은 달지 않으면 다른 화면(코어
   화면 포함)에 갔다 오는 순간 처음 값(「전체」 등)으로 말없이 돌아간다(4장).
6. 모든 `key=` 를 `ctx.key("…")` 로 바꾼다. `st.session_state["x"]` 는 `st.session_state[ctx.key("x")]` 로 바꾼다.
   `st.session_state.clear()` 와 반복문 안의 `del st.session_state[…]` 는 지운다 — 코어의 칸까지 지운다(M08). 여러 화면이 함께 쓰던
   조건(독립 앱의 사이드바 위젯 하나)은 화면마다 **같은 `ctx.key("…")` 와 `persist_state="session"`** 으로 그린다 — 한 화면에서 고른
   값이 다른 화면에도 선다.
7. `on_change=` · `on_click=` 같은 콜백을 `ctx.callback(함수)` 로 감싼다. `@st.fragment` · `@st.dialog` 본문은 `with ctx.guard():` 로 감싼다(M18).
8. `pages/` 폴더나 `st.navigation` 으로 만든 여러 화면은 `module.json` 의 `pages` 로 옮긴다(아래 「라우터 앱」). 화면 사이 이동은
   사이드바 · 탭 줄이 한다 — `st.switch_page` · `st.page_link` 를 지운다(M05).
9. 데이터 파일 경로는 `ctx.data_dir / "<이름>"` 으로, 코드 옆 정적 파일은 `Path(__file__).parent / "assets" / "<이름>"`(읽기만)으로 바꾼다.
10. 공통 코드는 `modules/<id>/<이름>.py` 에 두고 `from modules.<id> import <이름>` 으로 부른다(3-6).
11. `st.cache_*` 는 `cache.py` 한 파일로 모으고 `ttl` · `max_entries` 를 단다. 캐시 함수는 `ctx` · `api.palette()` 를 안에서 읽지
    않고 인자로 받는다(M12).
12. `argparse` · `click` 처럼 명령줄을 읽는 코드는 지운다 — `parse_args()` 가 `SystemExit` 을 낸다(M10).
13. CSS 꾸밈(`st.markdown("<style>…", unsafe_allow_html=True)`) · `.css` · `.js` · `.html` 파일 · `st.iframe` 을 지운다. 색은
    `api.palette()` 를 차트 · 표에 쓴다. `use_container_width=True` 는 `width="stretch"` 로 바꾼다(M03 · M19).
14. `uv run --no-sync python scripts/check_module.py <id>` 를 돌려 패키지 · 키 · 규칙을 고친다.
15. 스모크 시험과 핵심 함수 시험을 둔다(7장).
16. 담당자가 앱 관리자의 승인을 받아 온 뒤 자기 가지에서 커밋하고, 담당자가 PR 로 올린다(8-2).
17. 앱을 띄워(7장) 화면을 오가며 조건이 남는지 본다 — 조건을 고르고 다른 화면(코어 화면 하나 포함)에 갔다 돌아온다.

**라우터 앱** — 진입 스크립트(`app.py`)가 `st.navigation([st.Page("views/overview.py", …), …])` 로 화면을 고르고, 화면 파일이 하위
폴더(`views/`)에 있는 꼴이다. 진입 스크립트를 `page.py` 로 옮기면 라우터가 통째로 화면이 되어 M04 · M05 오류가 줄줄이 난다.

1. 진입 스크립트는 옮기지 않는다. 그 `st.Page` 하나가 `module.json` 의 `pages[]` 한 줄이다 — `title` · `icon`(이모지는
   `:material/<이름>:` 으로) · 차례를 옮긴다. 첫 화면(목록 첫째 또는 `default=True`)은 `order` 가 가장 작은 화면이다.
2. 하위 폴더의 화면 파일은 모듈 폴더 **바로 아래**로 올린다(`views/overview.py` → `modules/<id>/overview.py`). `pages[].file` 은 하위
   폴더를 받지 않는다(3-3). 화면 파일 이름은 자유다 — 뼈대의 `page.py` 는 첫 화면으로 쓰거나 지운다.
3. 진입 스크립트가 화면보다 먼저 하던 공용 부분 — 세션 초기값(`if "region" not in st.session_state: …`)과 사이드바 공용 조건 — 은
   도움 파일 한 곳의 함수로 모으고, 화면마다 머리말 바로 아래에서 부른다. 공용 조건은 같은 `ctx.key` · `persist_state="session"` 으로
   그린다(5 · 6단계). 세션 초기값의 키도 `ctx.key` 로 바꾼다.
4. 진입 스크립트의 나머지(`st.set_page_config` · CSS · `st.sidebar.title`)는 지운다(3 · 13단계).

공용 조건 도움 파일(모듈 `demo_port` — 독립 앱의 사이드바 `st.sidebar.selectbox("지역", …, key="region")` 를 옮긴 것):

```python
# Purpose: 데모 실적판 모듈의 공용 조건 — 화면마다 같은 키로 그려 화면을 옮겨도 값이 남는다.

import streamlit as st

from capa_simulation import module_api as api

REGIONS = ("전체", "DEMO-A", "DEMO-B")


def conditions(ctx: api.ModuleContext) -> str:
    """두 화면이 머리말 바로 아래에서 부른다. 고른 지역을 돌려준다."""
    with st.expander("조건", expanded=True):
        return st.selectbox("지역", REGIONS, key=ctx.key("region"), persist_state="session")
```

두 화면(`overview.py` · `detail.py`)은 맨 위가 같다 — `ctx = api.context(__file__)` · `api.page_header(ctx, "<화면 이름>")` 다음에
`region = common.conditions(ctx)`(`from modules.demo_port import common`).

옮기기 전 꼴(독립 앱):

```python
import pandas as pd
import streamlit as st

st.set_page_config(page_title="데모 표", layout="wide")
st.title("데모 표")
kind = st.sidebar.selectbox("종류", ["A", "B"], key="kind")


@st.cache_data
def load() -> pd.DataFrame:
    return pd.read_csv("data/demo.csv")


frame = load()
st.dataframe(frame[frame["종류"] == kind], use_container_width=True)
```

옮긴 꼴(모듈 `demo_table` — `cache.py` 와 `page.py` 둘). 저장소의 `data/demo.csv` 를 읽던 것을, 화면에서 올린 파일을 자기 데이터 자리에
두고 읽는 꼴로 바꿨다 — 손으로 넣은 파일은 운영 앱 · 배포 서버에 닿지 않는다(2장).

```python
# Purpose: 데모 표 모듈의 캐시 — 데이터 자리의 demo.csv 를 읽은 표를 파일 판마다 한 번 만든다.

from pathlib import Path

import pandas as pd
import streamlit as st


@st.cache_data(ttl=600, max_entries=8)
def load(data_dir: str, version: int) -> pd.DataFrame:
    """`version` 은 파일이 바뀌면 달라져 새 칸을 쓰게 하는 키다."""
    target = Path(data_dir) / "demo.csv"
    if not target.exists():
        return pd.DataFrame(columns=["종류", "값"])
    return pd.read_csv(target)
```

```python
# Purpose: 데모 표 모듈의 첫 화면 — 올린 합성 표를 데이터 자리에 두고 종류로 걸러 보인다.

import streamlit as st

from capa_simulation import module_api as api
from modules.demo_table import cache

ctx = api.context(__file__)
api.page_header(ctx, "데모 표", description="올린 합성 표를 종류로 걸러 봅니다.")


def _keep_upload() -> None:
    uploaded = st.session_state.get(ctx.key("upload"))
    if uploaded is not None:
        (ctx.data_dir / "demo.csv").write_bytes(uploaded.getvalue())


with st.expander("조건", expanded=True):
    kind = st.selectbox("종류", ["A", "B"], key=ctx.key("kind"), persist_state="session")
    st.file_uploader(
        "CSV 올리기", type="csv", key=ctx.key("upload"), on_change=ctx.callback(_keep_upload)
    )

target = ctx.data_dir / "demo.csv"
version = target.stat().st_mtime_ns if target.exists() else 0
frame = cache.load(str(ctx.data_dir), version)
st.dataframe(frame[frame["종류"] == kind], width="stretch")
```

---

## 4. 부딪치지 않게 하는 규칙

모듈은 코어 · 다른 모듈과 **한 프로세스 · 한 웹 페이지**에서 돈다. 그래서 아래를 지킨다. 번호는 점검 규칙(부록 B)이다.

| 하지 않는 것 | 대신 | 왜 | 규칙 |
|---|---|---|---|
| `st.set_page_config` | 지운다 | 앱이 한 번만 부른다 | M02 |
| 전역 CSS · JS — `st.html`, 글자 안 `<style`·`<script`·`<link`·`<iframe`, `streamlit.components`, `st.iframe`, 변수나 f-문자열을 `unsafe_allow_html=True` 로 그리기 | Streamlit 기본 위젯과 `api.palette()` | 한 페이지라 CSS 가 코어 화면과 다른 모듈까지 바꾼다. Components v2 이름도 전역이다. iframe 방식은 쓰지 않기로 했다 | M03 |
| `st.sidebar` · `st.logo` | 본문 위 `st.columns` · `st.expander("조건")` | 사이드바는 코어가 쓴다 | M04 |
| `st.navigation` · `st.Page` · `st.switch_page` · `st.query_params.clear()` · `st.query_params.from_dict(…)` · `del st.query_params[…]` · `st.set_option` | `module.json` 의 `pages` | 화면 등록 · 주소 · 설정은 코어가 한다. 주소의 테마 인자가 지워진다 | M05 |
| `st.page_link`(경고) | 사이드바 · 탭 줄 | 단독 시험(`AppTest.from_file(page)`)에서 `StreamlitPageNotFoundError` 로 죽는다 | M05 |
| 코어 내부 import — `capa_simulation` 가운데 `module_api` 밖, `app` · `app_pages` · `scripts` · `tests`, 다른 모듈 `modules.<다른 id>`, 같은 폴더 맨이름 import | `capa_simulation.module_api` 와 `modules.<id>.*` 만 | 코어 내부는 알림 없이 바뀐다. 맨이름은 앱에서 엉뚱한 자리로 풀린다(3-6) | M06 |
| 코어 데이터 자리 글자 — `capa_simulation.duckdb` · `equipment_availability.duckdb` · `data/input` · `data/output` · `data/temp` · `.deploy/` | `ctx.data_dir` | 운영 DB 를 잠그거나 깨뜨린다 | M07 |
| 접두 없는 세션 키 — `key="x"` · `st.session_state["x"]` · `st.query_params["x"]` | `ctx.key("x")` | 세션 칸은 코어 · 모든 모듈이 함께 쓴다. 겹쳐도 오류가 나지 않고 값이 조용히 샌다 | M08 |
| `st.session_state.clear()` · `.popitem()` · `.update(…)` · 변수 · 반복으로 `del` | 자기 키만 `del st.session_state[ctx.key("x")]` | 코어의 시나리오 · 탭 칸까지 지운다 | M08 |
| `requirements.txt` 에 없는 패키지 | 6장의 요청 | 배포 서버 이미지에 없어 그 화면만 import 오류가 난다 | M09 |
| 스레드 · 프로세스 — `threading` · `multiprocessing` · `concurrent.futures` · `subprocess` · `os.system` · `signal` · `sys.exit` · `exit()` | 화면 회차 안에서 끝낸다 | 앱을 끈 뒤에도 남거나 모든 사람의 앱을 함께 멈춘다 | M10 |
| `argparse` · `click` · `typer` · `fire` · `asyncio` · `st.fragment(run_every=…)`(경고) | 지운다 | `parse_args()` 가 `SystemExit` 을 낸다. 주기 실행은 모든 사람의 서버 시간을 쓴다 | M10 |
| 프로세스 전역 바꾸기 — 환경변수 쓰기 · `os.chdir` · `sys.path` · `sys.modules` · pandas 옵션(`pd.set_option` · `pd.options.… =`) · `np.seterr` · plotly · altair · matplotlib 기본값 · `logging.basicConfig` · 뿌리 로거 · `gc` · `locale` · `socket.setdefaulttimeout` | 그 자리 안에서만(`with pd.option_context(…):`) | 코어 계산과 모든 사람에게 함께 걸린다 | M11 |
| 도움 파일의 `global` 과 함수 안에서 바꾸는 모듈 수준 list · dict · set(경고) | 세션 칸(`ctx.key`)이나 `ctx.data_dir` | 도움 코드는 프로세스에 한 번 import 된다 — 모든 세션 · 모든 사람이 그 값을 함께 쓴다 | M11 |
| 화면 파일의 `st.cache_*` · `ttl`·`max_entries` 없는 캐시 · 캐시 함수 안의 `ctx` 읽기 · 맨 `st.cache_data.clear()`·`st.cache_resource.clear()` | `cache.py` 한 파일 · `ttl`·`max_entries` · `data_dir` 를 인자로 · 자기 함수의 `.clear()` | 화면 파일은 모두 `__main__` 이라 모듈끼리 캐시 칸이 겹쳐 남의 데이터가 보인다. 공용 서버 메모리가 넘치면 모든 사람의 앱이 함께 내려간다. 맨 `.clear()` 는 코어 캐시까지 비운다 | M12 |
| 캐시 함수 안의 `api.palette()`(경고) | 색 값을 인자로 | 한 사람의 테마가 모든 사람에게 굳는다 | M12 |
| `# Purpose:` 없는 `.py` · UTF-8 아닌 글 파일 · `.ps1` · DB · `.xls*` · `.env` · `.pkl` · `.css` · `.js` · `.html` · `assets/` 밖의 데이터 꼴 파일 · 대문자 이름 | 규칙대로 | 커밋되면 git · 배포 이미지에 실린다. `.pkl` 은 열 때 코드가 돈다 | M13 |
| `tests/test_*.py` 없음 | 스모크 시험 하나 이상 | 진입이 깨진 채 올라간다 | M14 |
| ruff 위반 · 포맷 다름 | `uv run --no-sync python -m ruff format modules/<id>` 뒤 고친다. 긴 주석 · 글자는 `ruff format` 이 나누지 않으므로 손으로 나누거나 줄인다 | 코어와 같은 규칙으로 읽힌다 — 한 줄은 **폭 100칸**이고 한글은 한 자가 2칸이다(한글만이면 50자 안팎, `# Purpose:` 줄은 45자 안팎에서 E501) | M15 · M16 |
| 감싸지 않은 콜백 — `on_change` · `on_click` · `on_submit` · `on_select` · `on_dismiss` 에 맨 함수 | `ctx.callback(함수)`(글자 `"rerun"` · `"ignore"` 는 그대로 된다) | 콜백은 앱 코드보다 먼저 돈다. 거기서 난 오류는 그 회차의 사이드바 · 머리 띠 · 탭 줄까지 지운다 | M18 |
| `use_container_width=` | `width="stretch"` · `width="content"` | Streamlit 이 곧 지울 인자다. 올림 한 번에 그 화면이 오류 카드가 된다 | M19 |
| 화면이 처음 그려질 때(첫 회차) 팝업을 스스로 열기(점검이 잡지 않는다 — 이 지침으로만 지킨다) · `st.dialog(dismissible=False)`(M20 경고) | 팝업은 단추를 눌렀을 때만 연다. `dismissible` 은 적지 않는다 — 닫기(✕ · Esc · 바깥 누름)가 남는다 | 누가 그 화면 주소로 처음 오면 입장 화면이 먼저 덮인다. 닫을 수 없는 팝업은 그 밑에 숨어 앱 화면을 묶는다 — 아무것도 누를 수 없고 새로고침해도 같아 앱에 들어갈 수 없다 | M20 |

그 밖에 알아 둘 것:

- **세션 · 캐시 · 환경변수 · pandas 옵션 · 로깅 · 작업 폴더는 앱을 쓰는 모든 사람과 코어가 한 프로세스에서 함께 쓴다.** 도움 파일의
  전역 list · dict 도 그렇다.
- **별도 프로세스가 아니다.** 오래 도는 계산은 앱을 쓰는 모든 사람의 화면을 느리게 한다. 모듈별 마지막 회차 시간이 Admin 에 보인다.
  무거운 계산은 캐시하고, 버튼을 눌렀을 때만 돈다.
- **화면을 옮기면 `persist_state` 없는 위젯은 처음 값으로 돌아간다.** 앱은 화면을 옮길 때 그 화면에 그려지지 않은 위젯 값을
  버린다 — 다른 화면(코어 화면 포함)에 갔다 오면 지역 · 기간 · 보기 방식 같은 조건이 「전체」 로 돌아가 있다. 화면을 오가도 남아야
  하는 조건 위젯에는 `persist_state="session"` 을 단다(코어 화면과 같은 꼴). 모듈의 여러 화면이 함께 쓰는 조건은 화면마다 같은
  `ctx.key("…")` 와 `persist_state="session"` 으로 그린다 — 한 화면에서 고른 값이 다른 화면에도 선다(3-9 「라우터 앱」).
- **`ctx.key` 이름은 `_` 로 시작할 수 없다**(코어가 쓰는 자리다). 빈 이름도 안 된다.
- 이름이 `_open_dialog` 로 끝나는 키는 화면을 떠나면 지워진다 — 「화면을 떠나면 닫히는 팝업 열림 칸」 으로 쓴다.
- `st.cache_*` 는 서버 전체가 함께 쓴다(앱을 쓰는 사람끼리 나눈다). 함수를 고쳐도 옛 칸은 앱을 다시 띄울 때까지 남는다.
- `st.stop()` 은 써도 된다(흔한 `if frame.empty: st.stop()` 꼴). `st.rerun()` 도 된다.
- 앱은 화면이 끝난 뒤 접두 없는 세션 키를 새로 만들거나 · 바꾸거나 · 지웠으면 화면 끝에 경고를 그린다. 경고가 보이면 `ctx.key` 로 고친다.

---

## 5. 화면 일관성

- 머리말은 `api.page_header` 로 **한 번, 맨 위에** 둔다. 큰 제목(`st.title` · `st.header`)을 따로 그리지 않는다 — 탭 줄이 화면 이름을 말한다.
- `use_container_width` 대신 `width="stretch"` · `width="content"` 를 쓴다.
- 아이콘은 Material 만 쓴다 — `:material/<이름>:` 정확히(앞뒤 공백 · 이모지 안 됨).
- 화면 이름에 Markdown 글자(별표 · 밑줄 · 대괄호 · 쌍점 등)를 넣지 않는다.
- 비율의 차이도 「%」 로 적는다.
- 라벨 · 안내 글은 한국어로 쓴다.
- 색은 `api.palette()` 의 역할 색(`surface` · `border` · `text` · `accent` · `secure` · `warning` · `shortage` 등 — 부록 A)을 차트 · 표에 쓴다.
  테마(라이트 · 다크)에 맞춰 값이 바뀐다.
- 서체를 정해야 하면 `api.FONT_FAMILY` 를 쓴다.
- 조건 위젯(지역 · 기간 · 보기 방식)에는 `persist_state="session"` 을 달아 화면을 오가도 남게 한다(4장). 달지 않으면 화면을 옮겼다
  돌아올 때 처음 값으로 돌아간다 — 피할 수 없는 일이 아니다.
- **모듈의 저장하지 않은 편집은 탭의 점 · 테마 단추 확인에 잡히지 않는다.** 코어만 센다. 그래서 저장 단추를 분명히 두고, 저장 전에
  화면을 옮기면 사라진다는 것을 안내 글로 적는다.

---

## 6. 의존성(새 패키지)

**설치하지 않는다.**

- WebIDE 에서 `uv pip install` 하면 그 PC 에서는 돈다. 그러나 배포 서버 이미지는 `requirements.txt` 만 깔아 그 화면만 import 오류가 난다.
- `uv add` 는 코어의 `pyproject.toml` · `uv.lock` 을 고치고, 다음 배포가 그것을 덮는다.
- 맨 `uv sync` 는 락에 없는 패키지(`bigdataquery`)를 지운다.

**요청하는 길** — 담당자 → 앱 관리자 → 사외.

1. 너는 담당자에게 아래 한 줄을 앱 관리자에게 전해 달라고 한다.

   ```text
   demo_memo: openpyxl==3.1.5 엑셀 올리기
   ```

   꼴은 `<id>: <패키지>==<판> <까닭 한 마디>` 다.
2. 앱 관리자가 그 줄을 리뷰 문서의 「사외 요청」 에 넣는다(리뷰는 앱 관리자만 쓴다).
3. 사외가 코어 의존성(`pyproject.toml` → `uv.lock` → `requirements.txt`)에 넣고 `config/module_packages.json` 에 이름을 적어 배포한다.
   그 목록에 있는 패키지는 코어가 쓰지 않게 돼도 빼지 않는다.
4. 그 배포가 main 에 들어온 뒤에 쓴다.

**배포가 main 에 들어온 뒤 `pyproject.toml` · `uv.lock` 이 바뀌었으면 담당자가 자기 클론에서 `uv sync --inexact` 를 친다.** 에이전트 설정은
`uv sync` 를 막으므로(8장) 담당자가 친다. 클론의 첫 준비는 저장소 `README.md` 「초기 설정」 0 ~ 4단계를 담당자가 따른다(5 · 6단계는
배포 적용 PC 의 몫이라 하지 않는다).

바로 써도 되는 것:

- 표준 라이브러리. 단 `tomllib` 은 Python 3.10 에 없다.
- `streamlit`.
- `requirements.txt` 의 **직접 의존** — `# via capa-simulation` 이 붙은 이름(pandas · numpy · plotly · altair · duckdb · pydantic 등).
  `numpy` 도 여기에 든다 — 코어가 직접 쓰는 의존이라 코어가 판을 지킨다(2026-11-02 부터).

경고가 나는 것:

- **전이 의존**(`pyarrow` · `PIL`(pillow) · `toml` · `requests` 처럼 다른 패키지가 끌어온 것)은 언제 빠질지 모른다.
  `import pyarrow` · `import PIL` 은 「직접 의존 아님」 경고(M09)다. 경고는 「통과」 를 막지 않는다 — 그대로 써도 점검은 통과한다. 오래
  쓸 것이면 요청해서 직접 의존으로 올린다(위 「요청하는 길」 — 판은 `requirements.txt` 에 적힌 판, 예: `demo_memo: pyarrow==<그 판> parquet 읽기`).
- `requirements-company.txt` 에만 있는 패키지(`bigdataquery`)는 모듈이 써도 된다(2026-11-01 앱 관리자 결정). 점검은 경고(M09)라
  「통과」 를 막지 않는다. 다만 배포 서버 설치는 보장되지 않는다 — 배포 서버에 없으면 그 화면만 import 오류가 난다.

오류가 나는 것:

- `requirements.txt` 에 없는 이름 · 설치되지 않은 이름.
- Windows 에서만 깔리는 패키지(`pywin32` 등 — 줄 끝 표지가 `sys_platform == 'win32'`). Windows PC 에서는 통과해도 배포 서버(Linux)에는 없다.

---

## 7. 시험과 확인

- 시험은 `modules/<id>/tests/test_<id>_*.py` 에 둔다. 다른 모듈과 파일 이름이 겹치지 않게 id 로 시작한다.
- 화면 시험은 `streamlit.testing.v1.AppTest.from_file(<화면 파일>)` 로 돈다(3-8 예시).
- 데이터 자리는 늘 `monkeypatch.setenv("CAPA_MODULES_DATA_ROOT", str(tmp_path))` 로 임시 폴더에 돌린다. 빈 자리에서 화면이 서는지가 함께 확인된다.
- 순수 함수(도움 코드)는 Streamlit 없이 보통 pytest 함수로 시험한다.

**돌리는 줄은 하나다.**

```powershell
uv run --no-sync python scripts/check_module.py <id>
```

- 선언 · 규칙 · ruff · 시험을 함께 본다. 끝에 「통과」 · 「꺼짐」 · 「실패」 와 고칠 자리(`자세히` 줄 — 규칙 · 파일 · 줄 · 고칠 말)를 찍는다.
- 시험은 감시 러너로 돈다. 시험이 코어 `data/` 를 열거나, 저장소 안 — 모듈 코드 폴더 · 상대 경로로 쓴 저장소 뿌리 자리 — 에 쓰면
  실패한다(쓰기는 시험의 임시 `ctx.data_dir` 만 된다). 같은 폴더 맨이름 import 는 앱처럼 깨진다.
- 정적 오류(M01 · M06 · M07 · M10 · M11)가 있으면 시험을 돌리지 않고 「시험 안 돎 — 정적 오류 먼저」 로 적는다. 그 오류부터 고친다.
- **맨 `pytest` · `python -m pytest modules/<id>/tests` 는 쓰지 않는다.** 코어 시험의 보호가 걸리지 않아 그 클론의 진짜
  `data/modules/<id>/` 에 쓴다.
- 결과는 담당자에게 맡기지 말고 네가 돌려 보여 준다.

**앱에서 보는 줄** — 앱은 담당자가 다른 창에서 띄운다. 포트는 늘 적는다(예: 8510).

```powershell
uv run --no-sync python -m streamlit run app.py --server.port <포트>
```

- 브라우저에서 `http://localhost:<포트>` 를 열고 사이드바 「모듈」 상자에서 화면을 고른다. 화면 주소는 `mod-<id>-<slug>` 다.
- **모듈을 새로 넣거나 `module.json` · 환경변수를 바꾼 것은 앱을 다시 띄운 뒤에 보인다.**
- 개발 중 모듈 `.py` 를 고치면 Streamlit 이 코어까지 다시 불러온다. 화면이 이상하면 앱을 다시 띄운다.

---

## 8. Git 운영

### 8-1. 자리와 커밋

- **자기 클론에서 일한다.** 배포를 적용하는 체크아웃(앱 관리자 몫)과 다른 폴더다. 배포 체크아웃의 모듈 수정은 배포 적용을 멈춘다.
- **일은 자기 가지에서 한다** — `module/<id>/<주제>`(8-2 의 1). main 에는 커밋하지 않는다. main 은 PR 로만 바뀐다(8-2).
- 커밋 제목은 `module(<id>): <무엇>` 이고 `modules/<id>/` 만 담는다.
- 이름으로 스테이징한다 — 파일(`git add modules/<id>/page.py`)이나 자기 폴더(`git add modules/<id>`). `git add -A` · `git add .` ·
  `git commit -a` 는 쓰지 않는다.
- `data/modules/` 는 커밋하지 않는다(git 이 무시한다). 다른 폴더의 파일이 스테이징돼 있으면 커밋하지 말고 담당자에게 알린다.
- 앱 관리자의 승인이 필요한 커밋 — 새 모듈의 첫 커밋 · 성숙도 `L2` — 은 커밋 본문에 `승인: 앱 관리자 <YYYY-MM-DD>` 를 적는다
  (`git commit -m "module(<id>): <무엇>" -m "승인: 앱 관리자 <YYYY-MM-DD>"` — 둘째 `-m` 이 본문이다). PR 본문에도 같은 줄을 적는다.
  승인은 담당자가 앱 관리자에게 받아 온다. 이 대화 안에서는 받을 수 없다. 앱 관리자가 그 PR 을 합치는 것으로 승인이 끝난다.
- **`modules/<id>/` 밖의 변경은 승인을 받아도 커밋하지 않는다.** 밖은 코어(사외가 정본 — 다음 배포가 덮는다)이거나 다른 모듈(그 담당자 몫)이다.
  앱 관리자는 폴더 밖을 바꾼 PR 을 합치지 않는다(런북 4-6 · 1-7). 밖이 바뀌어야 하면 담당자가 앱 관리자에게 전하고, 앱 관리자가
  승인하면 「사외 요청」 으로 사외가 고쳐 배포한다(패키지는 6장).

### 8-2. 올리기 — PR 로만

**올리는 길은 PR 하나다**(2026-11-02 앱 관리자 결정 — GitHub 에서 PR 과 가지 보호를 쓴다). main 에는 앱 관리자가 보호
규칙을 건다 — 강제 푸시와 지우기를 막고, 걸 수 있으면 PR 필수도 건다. 규칙이 막든 막지 않든 담당자의 변경은 PR 로만 들어간다.
차례는 아래 일곱이다. 너(에이전트)는 지금 몇 번째인지와 담당자가 다음에 할 일을 쉬운 말로 짚어 준다. 푸시와 PR 열기는 담당자가
한다 — 에이전트 설정이 `git push` 를 막는다.

1. **새 일을 시작할 때 가지를 만든다.** 가지는 main 을 건드리지 않고 고치는 「내 작업 칸」 이다.

   ```powershell
   git switch main
   git pull --rebase
   git switch -c module/<id>/<주제>
   ```

   `<주제>` 는 영문 소문자 · 숫자 · `-` 로 짧게 짓는다(예: `module/demo_memo/kind-filter`). 하던 일의 가지가 이미 있으면 셋째 줄 대신
   `git switch module/<id>/<주제>` 로 돌아간다.
2. 고치고 점검한다 — `check_module.py <id>` 가 「통과」 여야 한다(7장).
3. 그 가지에서 커밋한다(8-1).
4. **담당자가 가지를 푸시한다** — 처음 한 번은 `git push -u origin module/<id>/<주제>`, 그 뒤로는 `git push`.
5. **담당자가 GitHub 화면에서 PR 을 연다.** 받는 쪽(base)은 `main`, 제목은 `module(<id>): <무엇>` 이다. 본문에는 무엇을 바꿨는지
   한두 줄, 점검의 모듈 줄(`- m1 <id> 통과 · …`), 승인이 필요한 PR 이면 `승인: 앱 관리자 <YYYY-MM-DD>` 를 적는다. 본문은 네가 만들어
   담당자에게 준다.
6. **앱 관리자가 보고 합친다.** 앱 관리자는 PR 이 `modules/<id>/` 만 바꿨는지 보고 PR 머리에서 모듈 점검을 돌린 뒤(런북 4-6)
   「Squash and merge」 로 합친다 — main 에는 PR 하나가 `module(<id>): …` 커밋 하나로 남는다.
   - 고칠 것을 PR 에 적어 오면 같은 가지에서 고쳐 커밋하고 담당자가 다시 `git push` 한다. PR 이 따라온다 — 새 PR 을 열지 않는다.
   - 「가지를 main 에 맞춰 달라」 고 하면 담당자가 PR 화면의 「Update branch」 단추를 누르고, 자기 PC 에서는 `git pull --rebase` 로 받는다.
   - PR 을 연 뒤 더 올렸으면 담당자가 앱 관리자에게 알린다 — 앱 관리자는 점검한 머리만 합치므로 처음부터 다시 점검한다(런북 4-6).
7. **합쳐진 뒤** 다음 일은 1 부터 다시 한다. 다 쓴 가지는 그대로 둬도 된다(지우려면 먼저 묻는다).

그 밖에 지킬 것:

- **푸시가 거절되면 `git pull --rebase` 뒤 다시 푸시한다**(자기 가지에서도 같다). 배포의 `deploy:` · `review:` 커밋과 경로가 겹치지 않아
  충돌이 없다. 충돌이 나면 멈추고 담당자가 앱 관리자에게 묻는다.
- **`git push --force` · `--force-with-lease` 는 절대 쓰지 않는다** — 자기 가지에도. main 은 보호 규칙이 막는다. 가지를 덮으면
  앱 관리자가 점검한 머리와 PR 의 머리가 어긋난다.
- **main 에 바로 푸시하지 않는다** — 보호 규칙이 걸려 있으면 거절된다. 거절되지 않아도 올리지 않는다 — 앱 관리자가 점검하지 않은
  변경이 그대로 main 에 들어간다. main 에 커밋해 버렸으면 그 자리에서 `git switch -c module/<id>/<주제>`
  로 가지를 만들어(커밋이 그 가지에 실린다) 그 가지를 푸시하고, 자기 PC 의 main 을 되돌리는 일은 담당자가 앱 관리자에게 묻는다.
- 푸시는 담당자가 자기 창에서 친다. 에이전트 설정이 `git push` 를 막는다.
- **CI/CD 단추는 앱 관리자만 누른다.** 담당자는 누르지 않는다. 합친 모듈은 앱 관리자가 사본 트리에서 다시 점검한 뒤 앱 관리자의 앱과 배포
  서버에 오른다 — 다음 배포를 적용할 때(런북 1-7 로 받고 4-5 가 새 코어와 함께 본다)이거나, 그 전에 따로(런북 4-7 — 받기 ·
  `origin/main` 사본 점검 · 앱 다시 띄우기 · 단추). 단추는 그 점검을 본 뒤에만 누른다. 언제 오르는지는 앱 관리자가 정한다 —
  앱 관리자의 앱은 쓰는 사람이 없을 때만 다시 띄우고, 모듈 변경만으로 단추를 누를 때는 그 전에 앱 관리자가 담당자에게 「배포 서버의
  모듈 데이터가 사라질 수 있다」 고 알린다(2장 「데이터」 — 담당자는 남길 자료를 챙긴다).

### 8-3. 기본값 셋 — 바꿀 수 있다

아래 셋은 앱 관리자가 2026-11-01 에 「권장대로」 라고 맡겨, 이 앱을 만드는 쪽(사외)의 에이전트가 정한 기본값이다 — 앱 관리자가 하나하나
고른 것이 아니다(3 의 「PR 로 올린다」 는 2026-11-02 앱 관리자가 GitHub 에서 PR 을 쓸 수 있다고 확인해 정해졌다). 앱 관리자가
바꿀 수 있고, 바뀌면 이 문서를 고친다.

1. 자리는 `modules/<id>/` 이고, 사이드바에 별도 상자 「모듈」 하나를 둔다. 켜진 모듈이 없으면 상자를 숨긴다.
2. 새 패키지는 모듈이 직접 넣지 않는다. 「사외 요청」 으로 받아 코어 의존성으로 배포한다(6장).
3. 새 모듈 등록과 `modules/<id>/` 밖의 변경은 앱 관리자의 승인이 필요하다(밖의 변경은 승인되면 「사외 요청」 으로 사외가 한다 — 8-1).
   자기 폴더 안은 담당자가 자기 가지에 커밋하고 PR 로 올리며, 앱 관리자가 PR 을 점검한 뒤 합친다(8-2 — main 에 바로 올리는
   직접 커밋은 쓰지 않는다). 앱 관리자는 배포를 적용할 때마다 모듈 점검 결과를 다시 본다.

### 8-4. 담당자 클론의 Claude 설정

담당자가 자기 클론의 `.claude/settings.json` 에 아래를 넣는다(`<id>` 를 자기 id 로 바꾼다). `.claude/` 는 git 이 무시해 클론마다 따로다.
배포 적용 PC 의 템플릿(`docs/internal_claude_settings.json`)은 쓰지 않는다 — 그것은 배포 적용 에이전트용이다.

- `defaultMode` 는 `default` 다 — 새로 띄운 세션이 묻는 모드로 시작한다. auto · bypass(권한 건너뛰기) 모드로 띄우지 않는다.
- 담당자 PC 는 Windows 다. `Bash(…)` 규칙은 PowerShell 호출을 막지도 허용하지도 못하므로 모든 줄에 같은 `PowerShell(…)` 쌍둥이를 둔다.
- 루트 파일 deny 는 `/` 로 앵커한다. 슬래시 없는 패턴은 모든 깊이에 걸린다 — `Edit(*.md)` 는 자기 `README.md` 까지 막는다.
- deny 가 allow 를 이긴다. 그래서 다른 모듈 폴더는 deny 하지 않고 묻게 둔다(allow 에 없으면 `default` 모드가 묻는다).
- `data/modules/<id>/` 는 allow 에 넣지 않는다 — 화면이 실행 중에 쓰는 자리라 에이전트가 손으로 넣지 않는다(0장 1번 · 2장). 손으로
  넣은 파일은 그 PC 에서만 화면을 「되게」 한다. 꼭 손대야 하면 `default` 모드가 묻는다.
- `new_module.py` 는 allow 에 넣지 않는다 — 새 모듈 등록은 승인 대상이라 매번 묻는다. `python -m pytest` 도 넣지 않는다 — 돌리는 줄은
  `check_module.py` 하나다.

```json
{
  "permissions": {
    "defaultMode": "default",
    "allow": [
      "Read",
      "Edit(/modules/<id>/**)",
      "Bash(uv run --no-sync python scripts/check_module.py:*)",
      "PowerShell(uv run --no-sync python scripts/check_module.py:*)",
      "Bash(uv run --no-sync python -m ruff:*)",
      "PowerShell(uv run --no-sync python -m ruff:*)",
      "Bash(git status:*)",
      "PowerShell(git status:*)",
      "Bash(git diff:*)",
      "PowerShell(git diff:*)",
      "Bash(git log:*)",
      "PowerShell(git log:*)"
    ],
    "deny": [
      "Edit(/app.py)",
      "Edit(/app_pages/**)",
      "Edit(/src/**)",
      "Edit(/tests/**)",
      "Edit(/scripts/**)",
      "Edit(/config/**)",
      "Edit(/docs/**)",
      "Edit(/.streamlit/**)",
      "Edit(/static/**)",
      "Edit(/docker/**)",
      "Edit(/.github/**)",
      "Edit(/review/**)",
      "Edit(/.deploy/**)",
      "Edit(/data/*)",
      "Edit(/data/input/**)",
      "Edit(/data/output/**)",
      "Edit(/data/temp/**)",
      "Edit(/.gitignore)",
      "Edit(/.gitattributes)",
      "Edit(/.dockerignore)",
      "Edit(/*.md)",
      "Edit(/*.txt)",
      "Edit(/*.html)",
      "Edit(/*.json)",
      "Edit(/*.toml)",
      "Edit(/*.lock)",
      "NotebookEdit",
      "Bash(git push:*)",
      "PowerShell(git push:*)",
      "Bash(git reset:*)",
      "PowerShell(git reset:*)",
      "Bash(git clean:*)",
      "PowerShell(git clean:*)",
      "Bash(git stash:*)",
      "PowerShell(git stash:*)",
      "Bash(git rm:*)",
      "PowerShell(git rm:*)",
      "Bash(git add -A:*)",
      "PowerShell(git add -A:*)",
      "Bash(git add .:*)",
      "PowerShell(git add .:*)",
      "Bash(git add --all:*)",
      "PowerShell(git add --all:*)",
      "Bash(git commit -a:*)",
      "PowerShell(git commit -a:*)",
      "Bash(git commit -am:*)",
      "PowerShell(git commit -am:*)",
      "Bash(git commit --all:*)",
      "PowerShell(git commit --all:*)",
      "Bash(rm:*)",
      "PowerShell(rm:*)",
      "PowerShell(Remove-Item:*)",
      "Bash(uv sync:*)",
      "PowerShell(uv sync:*)",
      "Bash(uv add:*)",
      "PowerShell(uv add:*)",
      "Bash(uv remove:*)",
      "PowerShell(uv remove:*)",
      "Bash(uv lock:*)",
      "PowerShell(uv lock:*)",
      "Bash(uv pip:*)",
      "PowerShell(uv pip:*)",
      "Bash(uv run --with:*)",
      "PowerShell(uv run --with:*)",
      "Bash(pip install:*)",
      "PowerShell(pip install:*)",
      "Bash(pip3 install:*)",
      "PowerShell(pip3 install:*)",
      "Bash(python -m pip:*)",
      "PowerShell(python -m pip:*)",
      "Bash(uv run --no-sync python -m pip:*)",
      "PowerShell(uv run --no-sync python -m pip:*)"
    ]
  }
}
```

이 목록이 셸 우회를 전부 막지는 못한다 — 실제 방어선은 담당자가 프롬프트를 읽는 것과 앱 관리자의 4-5 점검이다.

---

## 9. 고장 격리 · 끄는 스위치 · API 판

### 9-1. 깨진 모듈은 그 화면만 멈춘다

모듈 화면에서 오류가 나면 앱은 **그 화면 자리에만** 오류 카드를 그린다. 사이드바 · 머리 띠 · 탭 줄 · 다른 화면은 그대로 쓴다.

- 카드에는 모듈 이름 · 화면 이름 · 오류 형식 · 메시지 첫 줄, 끄는 법, 「오류 위치」(모듈 폴더 안의 줄만)가 든다.
- import 오류면 한 줄을 더 적는다.
  - 코어 창구 이름이 없다(`from capa_simulation.module_api import x`) → `module.json` 의 `api` · `api_minor` 와 부록 C 를 본다.
  - 같은 모듈 파일을 맨이름으로 불렀다 → `from modules.<id> import <이름>` 으로 고친다(3-6).
  - 패키지가 없다 → 담당자가 앱 관리자에게 알린다(6장).

감싸는 자리는 셋이다.

| 자리 | 누가 감싸나 | 너는 |
|---|---|---|
| 화면 본문(파일 맨 위부터 끝까지) | 앱이 감싼다 — `SystemExit` 까지 잡는다 | 할 일 없다 |
| 위젯 콜백(`on_click` 등) | **너** — `on_click=ctx.callback(함수)` | 늘 감싼다(M18). 콜백 오류는 누른 뒤 다시 그려진 그 화면 맨 위에 「방금 한 동작에서 오류가 났습니다」 카드로 보인다 |
| 프래그먼트(`@st.fragment`) · 팝업(`@st.dialog`) 본문 | **너** — 본문을 `with ctx.guard():` 로 | 늘 감싼다. 프래그먼트만 다시 도는 회차는 앱 바깥이라, 감싸지 않으면 Streamlit 이 오류 전문(서버 경로 포함)을 그린다 |

```python
@st.dialog("자세히")
def _detail() -> None:
    with ctx.guard():
        st.write("합성 값 42")
```

- `st.stop()` · `st.rerun()` 은 오류가 아니다. 감싸기를 그대로 지나간다.
- 팝업은 단추를 눌렀을 때만 열고 닫기를 남긴다(4장 M20).

### 9-2. 끄는 스위치 둘

모듈이 깨져 운영에서 숨겨야 하면 둘 가운데 하나를 쓴다. 둘 다 **다음 앱 시작부터** 듣는다.

1. `module.json` 의 `"enabled": false` — 담당자가 PR 로 올림 → 앱 관리자가 PR 점검(런북 4-6) 뒤 합친다 → 앱 관리자가 런북
   4-7 로 받아 사본 트리에서 다시 점검하고 앱을 다시 띄운다. 배포 서버는 같은 점검을 본 뒤 CI/CD 단추로 다시 빌드한다(8-2 끝 — 다음
   배포까지 기다리면 런북 1-7 · 4-5 가 한다). 그 사이 급히 숨길 때는 2 를 쓴다.
2. 실행 환경변수 `CAPA_MODULES_DISABLED` — 앱 관리자가 건다. 값은 `*`(모두 끔) 또는 `demo_a,demo_b`(쉼표로 가른 id).
   - Windows PC(PowerShell) — 그 창에 남는다. 끝나면 지운다. 지우지 않으면 같은 창에서 나중에 띄운 앱의 모듈이 말없이 꺼진다.

     ```powershell
     $env:CAPA_MODULES_DISABLED="demo_x"; uv run --no-sync python -m streamlit run app.py --server.port <포트>
     Remove-Item Env:CAPA_MODULES_DISABLED
     ```

   - WebIDE(Linux bash) — 그 명령에만 걸린다.

     ```bash
     CAPA_MODULES_DISABLED=demo_x uv run --no-sync python -m streamlit run app.py --server.port <포트>
     ```

   - 배포 서버(C-DEP CD) — 배포 설정의 환경변수 표에 `CAPA_MODULES_DISABLED` 를 넣는다.

- 꺼진 모듈은 등록되지 않아 주소로도 열리지 않는다(HOME 으로 간다). Admin 「모듈 상태」 에는 「꺼짐 · 까닭」 이 남는다.
- 지금 값은 Admin 「모듈 상태」 캡션과 `check_module.py` 머리 줄에 보인다.

환경변수는 셋이다.

| 이름 | 값 | 쓰임 |
|---|---|---|
| `CAPA_MODULES_DISABLED` | 빈 값 = 없음 · `*` = 모두 끔 · `a,b` = 그 id 들 끔 | 운영에서 모듈을 숨기는 스위치. 기록은 Admin 에 남는다 |
| `CAPA_MODULES_ROOT` | 없음 · 빈 값 = 저장소의 `modules/` · `off`(대소문자 무시) = 모듈 없음 · 그 밖 = 그 폴더 | 모듈 뿌리 바꾸기. `off` 면 사외와 같은 화면이다(상자 · Admin 펼침 없음). 시험 · 화면 확인 도구가 쓴다 |
| `CAPA_MODULES_DATA_ROOT` | 폴더 경로 | 모듈 데이터 뿌리 바꾸기. 시험이 `tmp_path` 로 돌린다 |

### 9-3. Admin 「모듈 상태」

Admin Area 탭 위의 펼침이다. 앱 관리자가 본다. `modules/` 아래에 모듈 폴더가 하나라도 있을 때만 선다(펼침 제목에 켜짐 · 꺼짐 · 실패 수).

- 모듈마다 id · 모듈 이름(`name`) · 상태(켜짐 · 꺼짐 · 실패)와 까닭 · 성숙도 · 담당 · API 판 · 화면 수. 까닭 칸은 넓게 서서 잘리지
  않는다(표가 화면보다 넓으면 옆으로 민다).
- 마지막 오류(시각 · 형식 · 자리 · 화면 slug). 자리는 `page`(화면 본문) · `callback`(위젯 콜백) · `guard`(프래그먼트 · 팝업 본문) ·
  `load`(화면 등록 — 재시작까지 그 화면을 뺀다) 가운데 하나다. 메시지 본문은 적지 않는다.
- 마지막 회차 시간(ms) — 그 모듈 화면 회차 하나가 걸린 시간을 ms 정수로 적는다(가벼운 모듈도 2 · 4 처럼 갈린다). 느린 모듈을 찾는다.
- 접두 없는 키 수 · 빠진 화면 수.

### 9-4. API 판과 호환

- 모듈은 `module.json` 의 `api` 로 큰 판 하나를 요구한다. 지금 코어는 `1.0` 이다(`api.API_VERSION`).
- 판이 맞지 않으면 그 모듈만 「실패」 로 등록되지 않는다. 까닭에 두 판이 적힌다.
- 코어는 같은 큰 판 안에서 **더하기만** 한다(새 함수 · 새 선택 인자 · 새 `PALETTE_KEYS` 항목 · `module.json` 의 새 선택 칸). 더하면 작은 판을 올리고
  부록 C 에 한 줄을 적는다. 새 이름을 쓰는 모듈은 `api_minor` 를 그 판으로 적는다 — 예전 코어로 되돌아갔을 때 import 오류 대신 까닭이 보인다.
- 지우기 · 이름 바꾸기 · 서명이나 뜻 바꾸기는 큰 판을 올린다. 옛 큰 판은 그 판을 쓰는 모듈이 0 이 될 때까지 지원한다.
- 창구 밖의 변경(패키지 제거 · pandas · Streamlit 판 올림 · 폐기 예정 인자 제거)도 모듈을 깨뜨릴 수 있다. 사외는 그런 변경을 배포 안내의
  「모듈 담당자에게 알릴 것」 에 적는다 — 앱 관리자가 담당자에게 전한다.

---

## 10. 다음 단계 — 데이터 연계 예고

- `module_api` v2 에 **읽기 전용** 코어 창구(활성 시나리오 · 기준정보 · 조회기간 · 표시순서)를 둔다.
- 모듈은 출력 계약(컬럼 · 단위 · 키)을 문서로 낸다. 코어가 그것을 읽는 꼴이다.
- 성숙도 `L1` 은 그 뒤에 선다.
- **지금(v1)은 코어 데이터를 읽지 않는다.** 코어 DB 를 직접 열어 우회하지 않는다(M07).

---

## 부록 A — `module_api` v1 목록

모듈이 import 하는 코어 이름은 이것이 전부다(`module_api.__all__` 의 차례).

| 이름 | 꼴 | 뜻 |
|---|---|---|
| `API_VERSION` | `tuple[int, int]` — `(1, 0)` | 이 코어의 창구 판(큰 판, 작은 판) |
| `FONT_FAMILY` | `str` | 앱 서체 이름 |
| `IMPLEMENTING_SUFFIX` | `str` — `"(구현중)"` | 성숙도 `L0` · `L1` 화면에 붙는 표기 |
| `PALETTE_KEYS` | `tuple[str, ...]` — `("surface", "surface_subtle", "border", "text", "text_muted", "accent", "secure", "warning", "shortage")` | `palette()` 의 키 |
| `ModuleContext` | 바꿀 수 없는 dataclass | 모듈 문맥(아래) |
| `ModuleContextError` | `RuntimeError` 의 하위 | 문맥을 못 찾거나 선언이 틀렸을 때 |
| `context` | `context(file: str \| os.PathLike[str]) -> ModuleContext` | 보통 `api.context(__file__)`. 파일 위치에서 가장 가까운 `module.json` 을 찾는다 |
| `page_header` | `page_header(ctx: ModuleContext, title: str, *, description: str \| None = None) -> None` | 머리말. 성숙도 `L0` · `L1` 이면 `(구현중)` 배지를 붙인다. 한 회차에 한 번, 화면 맨 위. 세션 키를 만들지 않는다 |
| `palette` | `palette() -> Mapping[str, str]` | 이번 회차 테마의 역할 색. 키는 `PALETTE_KEYS`. 캐시 함수 안에서 부르지 않고 값을 인자로 넘긴다 |

`ModuleContext` 의 칸과 메서드:

| 이름 | 꼴 | 뜻 |
|---|---|---|
| `id` | `str` | 모듈 id |
| `name` | `str` | 모듈 이름 |
| `owner` | `str` | 담당 역할 이름 |
| `maturity` | `str` | `"L0"` · `"L1"` · `"L2"` |
| `folder` | `Path` | 모듈 폴더(읽기용) |
| `api_version` | `tuple[int, int]` | 코어 창구 판 |
| `key_prefix` | 속성 `str` | `"mod_<id>__"` |
| `key` | `key(name: str) -> str` | `"mod_<id>__<name>"`. 이미 접두가 있으면 그대로(두 번 불러도 같다). 빈 이름 · `_` 로 시작하는 이름은 `ValueError` |
| `data_dir` | 속성 `Path` | 모듈 데이터 자리(`data/modules/<id>/`). 처음 읽을 때 만든다 |
| `callback` | `callback(fn: Callable[..., object]) -> Callable[..., None]` | 위젯 콜백(`on_change` · `on_click` · `on_submit` · `on_select` · `on_dismiss`)에 넘길 감싼 함수. 오류를 잡아 적고 그 화면 맨 위 카드로 보인다. `st.stop()` · `st.rerun()` 은 그대로 지나간다 |
| `guard` | `guard() -> AbstractContextManager[None]` | `with ctx.guard():` — 프래그먼트 · `st.dialog` 본문용. 안의 오류를 잡아 적고 그 자리에 오류 카드를 그린다 |

- 데이터(시나리오 · 기준정보 · 조회기간 · DB)는 v1 에 없다. v2 의 몫이다(10장).
- 이 밖의 코어 이름(`navigation` · `settings` · `components.*` 등)은 import 하지 않는다(M06).

---

## 부록 B — 점검 규칙 표

`check_module.py` 가 보는 규칙이다. 번호는 점검 출력의 `자세히` 줄과 같다. 「오류」 가 하나라도 있으면 그 모듈은 「실패」 이고, 「경고」 는
상태를 바꾸지 않는다. `tests/` 아래 파일은 앱에서 돌지 않으므로 M09 의 `pytest` · `streamlit.testing` import 와 M10 · M11 을 보지 않는다.

| 번호 | 무엇 | 등급 |
|---|---|---|
| M01 | 선언 — `module.json` 없음 · 못 읽음 · JSON 아님 · 칸 오류 · id ≠ 폴더 · 예약어 id · API 판(`api` · `api_minor`) · 화면 파일 없음 · 폴더 밖 · 디스크 철자 다름 · 아이콘 · 제목 Markdown 글자 · 화면 이름 겹침(코어 · 「현황 요약」 · 모듈 안 · 다른 켜진 모듈 — 모듈끼리면 차례가 뒤인 모듈 전체가 실패하고 까닭에 상대를 적는다, 3-3) | 오류 |
| M01 | 이 모듈의 화면 이름을 차례가 뒤인 켜진 모듈도 써서 **그 모듈**이 실패함(그 모듈 id 를 적는다) | 경고 |
| M02 | `st.set_page_config` 호출 | 오류 |
| M03 | 전역 CSS · JS · 끼워 넣기 — `st.html(…)`, `st.iframe(…)`, 글자 상수에 `<style` · `<script` · `<link` · `<iframe`(대소문자 무시), `streamlit.components` · `st.components` import · 사용, `unsafe_allow_html=True` 인데 첫 인자가 글자 상수가 아님(변수 · f-문자열 · 파일에서 읽은 글) | 오류 |
| M03 | `unsafe_allow_html=True` 인데 첫 인자가 위 넷이 없는 글자 상수 | 경고 |
| M04 | `st.sidebar`(속성 접근 전부) · `st.logo` | 오류 |
| M05 | 내비 · 주소 — `st.navigation` · `st.Page` · `st.switch_page` · `st.query_params.clear()` · `st.query_params.from_dict(…)` · `del st.query_params[…]` · `st.set_option` | 오류 |
| M05 | `st.page_link`(단독 시험에서 `StreamlitPageNotFoundError` — 화면 사이 이동은 사이드바 · 탭 줄이 한다) | 경고 |
| M06 | 코어 내부 import — `capa_simulation` 가운데 `capa_simulation.module_api` 밖, `app` · `app_pages` · `scripts` · `tests`, 다른 모듈 `modules.<다른 id>`, 맨 `modules`. 같은 폴더 맨이름 import — 최상위 import 이름이 그 모듈 폴더 안 `.py`(확장자 뗀 것) · 폴더 이름과 같으면 「`from modules.<id> import <이름>` 으로」(M09 보다 먼저 판정) | 오류 |
| M07 | 코어 데이터 자리 — 글자에 `capa_simulation.duckdb` · `equipment_availability.duckdb` · `data/input` · `data/output` · `data/temp` · `.deploy/`(역슬래시 꼴 포함) | 오류 |
| M07 | 글자가 `data/` 로 시작(`ctx.data_dir` 를 쓰라는 안내) | 경고 |
| M08 | 키 접두 — `key=` 의 글자(또는 f-문자열의 앞 상수), `st.session_state[…]` · `.get` · `.pop` · `.setdefault` · `in st.session_state` · 속성 접근, `st.query_params[…]` 의 글자가 `mod_<id>__` 로 시작하지 않음. `ctx.key(…)` 호출과 판정할 수 없는 읽기 식은 넘긴다 | 오류 |
| M08 | 세션 전역 조작 — `st.session_state.clear()` · `.popitem()` · `.update(…)`, `del st.session_state[…]` 의 키가 접두 있는 글자 상수나 `ctx.key(…)` 호출이 아님(변수 · 반복 포함) | 오류 |
| M09 | 패키지 — 최상위 import 이름이 표준 라이브러리 · `streamlit` · `capa_simulation.module_api` · 자기 `modules.<id>` 가 아니면 그 배포 이름이 `requirements.txt` 에 고정돼 있어야 한다. 없으면 오류(「사외 요청」 안내). 설치되지 않은 이름도 오류. 3.10 에 없는 모듈(`tomllib`)도 오류. 줄 끝 환경 표지가 Linux 에서 거짓이면 오류 「CD(Linux)에 설치되지 않음」. 따질 수 없는 표지는 경고 | 오류 |
| M09 | `requirements.txt` 에 있으나 직접 의존이 아님(`# via` 에 `capa-simulation` 이 없다 — 예: `pyarrow` · `PIL`(pillow) · `toml` · `requests`) — 「직접 의존 아님 — 사외 요청으로 올린다」. `config/module_packages.json` 에 있으면 내지 않는다. `requirements-company.txt` 에만 있음 | 경고 |
| M10 | 배경 실행 — `threading` · `_thread` · `multiprocessing` · `concurrent.futures` · `subprocess` import, `os.system` · `os.popen` · `os.fork` · `os.forkpty` · `os.spawn*` · `os.posix_spawn*` · `os.exec*` · `os.abort` · `signal` · `sys.exit` · `os._exit` · `exit()` · `quit()` | 오류 |
| M10 | `asyncio`, `st.fragment(run_every=…)`, `argparse` · `click` · `typer` · `fire` import | 경고 |
| M11 | 프로세스 전역 상태 — `os.environ` 쓰기 · `os.putenv` · `os.unsetenv` · `os.chdir` · `os.fchdir`, `sys.path` 바꾸기, `sys.modules` 바꾸기, `builtins.<이름> =`, `sys.excepthook =` · `threading.excepthook =`, `sys.setrecursionlimit` · `sys.settrace` · `sys.setprofile`, `gc.disable` · `gc.set_threshold` · `gc.freeze`, `socket.setdefaulttimeout`, `locale.setlocale`, `pd.set_option` · `pandas.set_option` · `pd.reset_option` · `pd.options.<…> =`(`pd.option_context` 는 허용), `np.seterr` · `np.set_printoptions`, `plotly.io.templates.default =` · `pio.renderers.default =` · `px.defaults.<…> =`(plotly express 기본값), `alt.themes.enable` · `alt.theme.enable` · `alt.data_transformers.enable` · `alt.data_transformers.disable_max_rows`, `matplotlib.use` · `matplotlib.rcParams[…] =` · `rcParams.update` · `plt.style.use`, `logging.basicConfig` · 뿌리 로거(`logging.getLogger()` · `logging.root`)의 `addHandler` · `removeHandler` · `setLevel` | 오류 |
| M11 | `warnings.filterwarnings` · `warnings.simplefilter` · `warnings.resetwarnings`, 화면 밖 도움 파일의 `global` 문과 함수 안에서 바꾸는 모듈 수준 list · dict · set | 경고 |
| M12 | 캐시 — `st.cache_data` · `st.cache_resource` 장식자가 `modules/<id>/cache.py` 밖에 있음, `max_entries` · `ttl` 이 둘 다 없음, 캐시 함수 본문이 모듈 전역 `ctx` 나 `api.context(…)` 를 읽음, 맨 `st.cache_data.clear()` · `st.cache_resource.clear()`(자기 함수의 `.clear()` 는 허용) | 오류 |
| M12 | 캐시 함수 본문 안의 `api.palette()` 호출 | 경고 |
| M13 | 파일 — `.py` 첫 줄 `# Purpose:` 없음, UTF-8 이 아닌 글 파일, `.ps1`, 데이터 파일(`.duckdb` · `.db` · `.sqlite` · `.wal` · `.sync.json` · `.xls*` · `.env` · `secrets.toml`), `.pkl` · `.pickle`, `.css` · `.js` · `.html` · `.htm`, `assets/` 밖의 데이터 꼴 파일(`.csv` · `.tsv` · `.parquet` · `.feather` · `.arrow` · `.npy` · `.npz`), 3.10 문법 오류, 대문자가 든 폴더 · 파일 이름, (git 검사) git 의 철자가 디스크 철자와 대소문자만 다름, (git 검사) git 이 무시하는 파일인데 코드 · `module.json` 이 그 이름을 글자로 가리킴 | 오류 |
| M13 | 5 MB 넘는 파일, `assets/` 안의 데이터 꼴 파일(「합성만」), 1 MB 넘는 `.json`, (git 검사) git 이 무시하는 파일(커밋되지 않아 운영 · 배포 서버에 없다), `open(…, "w"·"a"·"x")` · `Path.write_*` 의 경로 식에 `__file__` 이 든다(코드 폴더에 실행 중 쓰기), 같은 쓰기(표의 `to_csv` 등 포함)의 경로가 상대 경로 글자다 — `"notes.txt"` · 그 글자를 담은 모듈 수준 이름 · `Path("…")` · `Path("…") / …`(작업 폴더 = 저장소 뿌리에 쓰기. `data/` 로 시작하면 M07), `modules/__init__.py` 있음 | 경고 |
| M14 | 시험 — `tests/test_*.py` 없음 | 오류 |
| M15 | `ruff check` 위반(수) | 오류 |
| M16 | `ruff format --check` 다름(수) | 오류 |
| M17 | 자기 시험 실패(실패 수/전체). M01 · M06 · M07 · M10 · M11 오류가 있으면 돌리지 않고 「시험 안 돎」(실패로 센다) | 오류 |
| M18 | 콜백 — `on_change` · `on_click` · `on_submit` · `on_select` · `on_dismiss` 인자에 글자 상수(`"rerun"` · `"ignore"`)도 `<무엇>.callback(…)` 호출도 아닌 값이 옴 | 오류 |
| M19 | 폐기 예정 Streamlit 인자 — `use_container_width=`(`width="stretch"` · `width="content"` 로) | 오류 |
| M20 | 닫을 수 없는 팝업 — `st.dialog(…)` 의 `dismissible=` 에 `True` 가 아닌 값(`False` · 변수). 처음 들어온 사람의 입장 화면 밑에 숨어 앱 화면을 묶는다(4장) | 경고 |

점검 출력의 꼴(합성 예):

```text
모듈 점검 — 뿌리 modules/ · 2개 = 통과 1 + 꺼짐 0 + 실패 1
- m1 demo_draft 실패 · L0 · API 1.0 · 화면 1 · 오류 1(M19 1) · 경고 0 · ruff ok · 시험 1 통과
- m2 demo_memo 통과 · L0 · API 1.0 · 화면 1 · 오류 0 · 경고 0 · ruff ok · 시험 2 통과
판 분포: api1 2
제3자 패키지: pandas
자세히
  m1 demo_draft 오류 M19 page.py:23 `use_container_width=` 는 Streamlit 이 곧 지웁니다 — width="stretch" 또는 width="content" 로 바꿉니다
전송용 요약: 모듈 2 = 통과 1 + 꺼짐 0 + 실패 1; api1 2; 패키지 pandas; ng m1 오류1
```

- 모듈 차례(`m<n>`)는 `module.json` 의 `order` 차례이고, 같으면 id 차례다.
- 「전송용 요약」 줄은 앱 관리자가 리뷰에 옮기는 줄이다. id 가 없고 차례 번호 `m<n>` 만 있다.
- 저장소가 아닌 자리(배포 적용의 `git archive` 사본 트리)에서 돌면 머리 다음에 `git 검사 건너뜀(사본)` 줄이 서고 M13 의 git 검사는 빠진다.
  `CAPA_MODULES_ROOT` · `CAPA_MODULES_DISABLED` 가 걸려 있으면 그 값을 알리는 줄도 선다(점검은 따르지 않는다).

---

## 부록 C — 창구 변경 기록

`module_api` 를 바꿀 때마다 한 줄을 더한다(9-4).

| 판 | 날짜 | 바뀐 것 |
|---|---|---|
| v1.0 | 2026-11-01 | 첫 판 — `API_VERSION` · `FONT_FAMILY` · `IMPLEMENTING_SUFFIX` · `PALETTE_KEYS` · `ModuleContext`(`key` · `data_dir` · `callback` · `guard`) · `ModuleContextError` · `context` · `page_header` · `palette` |
