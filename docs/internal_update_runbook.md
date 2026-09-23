# 사내 업데이트 실행 절차 (사내 에이전트용)

이 문서는 **사내(WebIDE)에서 배포 ZIP 을 받아 적용하는 한 번의 작업**을 처음부터 끝까지 적은
것이다. 위에서 아래로 그대로 따라가면 된다. 왜 이런 구조인지는 `docs/dual_env_workflow.md`
에 있고, 여기는 **무엇을 어떤 순서로 치는가**만 적는다.

**이 문서를 읽고 있다면 먼저 확인한다.**

```powershell
git remote -v
```

`github.com` 이 나오면 **사외(개발 PC)다 — 이 문서는 네 것이 아니다.** 사내 GitHub 주소가
나올 때만 아래를 따른다.

---

## 0. 사내에서 절대 하지 않는 것

- **소스를 고치지 않는다.** `app.py`·`app_pages/`·`src/`·`tests/`·`scripts/`·`config/`·
  `.streamlit/`·루트 문서 — 어느 것도 편집하지 않는다. 쓸 수 있는 곳은 `review/` 뿐이다.
- **`git clean -x` 를 쓰지 않는다.** `-x` 는 무시된 파일까지 지우고, 거기에 **운영 DuckDB 와
  `data/input` 실데이터**가 들어 있다. 한 글자 차이로 사내 데이터가 날아간다.
- **`uv sync` 를 맨 것으로 돌리지 않는다.** 락에 없는 `bigdataquery` 를 지운다.
  항상 `uv sync --inexact` 다.
- **정체불명 파일을 스스로 지우지 않는다.** 사용자에게 묻고 고른 대로 한다.
- **`.gitignore` 를 고치지 않는다.** 권한에서도 막혀 있다. 넣어야 할 것이 있으면 리뷰
  문서에 적어 사외가 넣게 한다.
- **`git push` 는 에이전트가 하지 않는다.** 권한에서 막혀 있다(`Bash(git push*)` deny).
  푸시가 필요한 자리에서는 사용자에게 명령을 알려 주고 사용자가 친다.

---

## 1. 시작 전 점검 (5분)

### 1-1. 앱을 끈다

```powershell
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*streamlit_project*" }
```

떠 있으면 그 창에서 `Ctrl+C`. **DuckDB 는 프로세스 배타 잠금이라 앱이 살아 있으면 이후
검증·마이그레이션이 전부 `duckdb.IOException` 으로 죽는다.** 적용기 자체는 DB 를 열지 않지만
적용 뒤 확인이 막히므로 먼저 끈다.

### 1-2. 쓰기 권한이 실제로 열리는지 한 번 본다

리뷰 문서를 못 쓰면 이번 작업의 산출물이 아예 나오지 않는다. 먼저 확인한다.

```powershell
New-Item -ItemType Directory -Force review | Out-Null
```

그리고 `review/_permission_test.md` 에 아무 한 줄이나 써 본다. 잘 써지면 그 파일은 지우고
넘어간다.

**막히면 거기서 멈추고** 사용자에게 아래를 그대로 알린다 — 사외가 고쳐야 한다.

> 사내 `.claude/settings.json` 의 `Edit(*.md)` deny 가 `review/` 까지 막고 있습니다.
> 슬래시 없는 패턴은 gitignore 의미라 모든 깊이에 걸립니다. `Edit(/*.md)` 로 앵커하고
> allow 에 `Edit(review/**)` 를 더해야 합니다. **deny 는 allow 로 뚫을 수 없으므로**
> deny 쪽을 좁히는 것 말고는 방법이 없습니다.

설정 파일이 `docs/internal_claude_settings.json` 템플릿의 최신본과 같은지도 함께 본다 —
`.claude/` 는 배포가 덮지 않으므로 옛 템플릿이 남아 있을 수 있다.

### 1-3. 운영 데이터를 저장소 밖으로 복사한다

**건너뛰지 않는다.** 아래 두 가지는 적용이 덮거나 지울 수 있다.

```powershell
$backup = "$HOME\deploy_backup\$(Get-Date -Format yyyyMMddHHmm)"
New-Item -ItemType Directory -Force $backup | Out-Null
Copy-Item data\*.duckdb $backup -ErrorAction SilentlyContinue
Copy-Item data\input\* $backup -Recurse -ErrorAction SilentlyContinue
```

`data/input/` 을 함께 챙기는 것은 보수적으로 두는 것이다. **배포 세트는 `data/input/` 아래를
보내지 않으므로**(`build_deploy_package.py` 의 `FORBIDDEN_PREFIXES`) 적용이 덮을 일은 없다.
다만 적용기의 `is_protected` 는 **삭제만** 막고 덮어쓰기는 막지 않는 구조라, 규칙이 바뀌면
조용히 덮인다 — 무시 파일이라 `git checkout -- .` 로도 돌아오지 않는다.

### 1-4. 저장소에 있으면 안 되는 것이 커밋돼 있는지 먼저 본다

**이 순서를 바꾸지 않는다.** 다음 단계(1-5)가 「수정된 파일을 되돌려라」라고 시키는데,
운영 DuckDB 나 `data/input` 실데이터가 **추적된 상태**라면 그 되돌리기가 실데이터를 커밋된
옛 버전으로 덮는다. 무엇이 추적 중인지 모르는 채로 1-5 에 들어가면 안 된다.

```powershell
git ls-files | Select-String -Pattern '\.duckdb|\.db$|\.wal$|^data/input/|^data/output/|^data/temp/|^\.agents/|^\.omo/|\.xlsx?$|\.xlsb$|\.tmp$'
```

**한 줄이라도 나오면 여기서 멈춘다.** `docs/dual_env_workflow.md` 8장의 정리를 먼저 끝내야
한다(앱 종료 → DB 를 저장소 밖으로 복사 → `git rm -r --cached` → 커밋). 그 정리는 사람이
한다 — `git rm` 은 에이전트 권한에서 막혀 있다.

정리를 건너뛰고 적용하면 두 가지가 한꺼번에 일어난다. ① 그 파일들은 ZIP 에 없으므로
「사외에서 지워진 파일」로 판정돼 적용이 지운다. ② 1-5 의 되돌리기가 그 전에 실데이터를
덮는다.

### 1-5. 작업트리를 비운다

```powershell
git status --porcelain --untracked-files=no
```

**한 줄이라도 나오면 적용기가 멈춘다.** 사내에서 소스를 고쳤다면 커밋하지 말고 되돌린다.

```powershell
git checkout -- <경로>
```

**경로를 하나씩 확인하고 되돌린다.** `git checkout -- .` 처럼 전체를 쓰지 않는다. 경로에
`.duckdb`·`.wal`·`data/input`·`data/output`·`data/temp` 가 들어 있으면 **되돌리지 말고
사용자에게 알린다** — 그것은 소스 수정이 아니라 실데이터이고, 되돌리면 운영 데이터가
사라진다. 1-4 를 제대로 끝냈으면 이 목록에 그런 경로가 나올 수 없다.

`git checkout` 은 일부러 권한 allow 에 넣지 않았다. 매번 프롬프트가 떠서 **사람이 경로를
읽고 승인**하게 되어 있다.

되돌리기 전에 그 내용이 필요하면 리뷰 문서에 코드블록으로 옮겨 적는다 — 그것은 저장소 수정이
아니다. 아직 커밋하지 않은 `review/*.md` 가 있으면 **먼저 `review:` 로 커밋한다.** 그러지
않으면 이 단계에서 지워진다.

---

## 2. 적용 (본 작업)

### 2-1. 먼저 보기만 한다

```powershell
uv run --no-sync python scripts/apply_deploy_package.py <내려받은 ZIP 경로> --dry-run
```

`--dry-run` 은 **아무것도 바꾸지 않는다.** 깨끗한 작업트리도 요구하지 않는다. 출력에서 아래를
읽는다.

| 칸 | 뜻 | 할 일 |
|---|---|---|
| `사외에서 지워진 파일` | 추적 중인데 목록에 없다 | 적용이 지운다. 뜻밖의 것이 있으면 **여기서 멈추고** 사용자에게 묻는다 |
| `사내에만 있는 정체불명 파일` | 추적도 무시도 안 된다 | **스스로 지우지 않는다.** 아래 2-2 로 |
| `목록에 있는데 사내에 없는 파일` | 적용 전이면 정상 | ZIP 이 채운다 |

`--reconcile-only` 는 목록 대조만 본다(동작은 `--dry-run` 과 같은 자리에서 끝난다).

### 2-2. 정체불명 파일을 먼저 정리한다

**적용보다 먼저 한다.** 적용기의 커밋 단계는 이번 배포가 실제로 건드린 경로만 스테이징하므로
정체불명 파일을 빨아들이지는 않지만, 그래도 남겨 두면 다음 배포에서 다시 물어야 한다.

파일마다 사용자에게 묻고 셋 중 하나를 고른다.

1. **사내에서만 쓰는 것** → 그대로 둔다. `.gitignore` 에 넣을 필요가 있으면 **리뷰 문서에
   적어 사외가 넣게 한다** (사내에서 `.gitignore` 를 고치지 않는다)
2. **사외에도 있어야 하는 것** → 리뷰 문서에 적어 사외가 추가하게 한다
3. **옛 배포의 잔해** → 지운다

판단이 서지 않으면 (1)로 두고 리뷰 문서에 남긴다. 지우는 것은 되돌릴 수 없고, 남기는 것은
다음 배포에서 다시 물으면 된다.

아직 커밋하지 않은 `review/*.md` 가 있으면 **적용 전에 `review:` 로 먼저 커밋한다.**
`deploy:` 커밋과 섞이지 않게 하려는 것이다.

### 2-3. 적용한다

```powershell
uv run --no-sync python scripts/apply_deploy_package.py <내려받은 ZIP 경로>
```

끝나면 `deploy: <stamp> (<사외 커밋 7자>)` 로 자동 커밋된다.

---

## 3. 적용 뒤 읽는 법 — 정상인데 이상해 보이는 두 줄

**이 둘은 결함이 아니다. 리뷰 문서에 결함으로 적지 않는다.**

### 3-1. `목록에 있는데 사내에 없는 파일` 은 비어 있어야 한다

적용 **뒤**에 이 칸에 무엇이든 있으면 이상이다(`해제가 덜 됐습니다`). 판정의 근거는 **바로
앞줄**이다.

```
대조    N/N 해시 일치
```

이 줄이 먼저 나왔으면 전 파일이 맞게 풀린 것이다.

> 예전 배포에서는 이 칸에 `data/input/RQ_DISPLAY_ORDER.csv` 한 줄이 **항상** 떴다. 그 파일이
> 배포 세트에 실리면서 동시에 `.gitignore` 에 걸려 대조가 쓰는 두 목록 어디에도 안 잡혔기
> 때문이다. 지금은 `data/input/` 아래를 아예 보내지 않으므로 그 오탐이 없다. 아직도 뜬다면
> **옛 ZIP 을 적용하고 있는 것이다.**

### 3-2. `pytest` 에서 `test_the_top_level_stays_the_declared_set` 실패

`['.deploy/', 'review/']` 때문에 실패하면 **옛 배포를 적용한 것이다.** 두 폴더는 사내에만
생기므로 사외에서는 재현되지 않고, 그래서 한동안 사내에서만 깨졌다. 지금 배포부터는 그 둘이
`INTERNAL_ONLY_TOP_LEVEL` 로 선언돼 있어 통과한다. 그래도 실패하면 **그 사실 자체를 리뷰
문서에 적는다.**

### 3-3. 루트의 `requirements.txt` 는 사내 WebIDE 컨테이너 전용이다

**손으로 적는 파일이 아니라 `uv.lock` 의 그림자다.** 개발 PC 와 CI 는 `uv sync` 로 잠금을
보지만, 사내 WebIDE 의 CI/CD 는 `docker/Dockerfile-prod` 로 이미지를 만들고 그 안에서
`pip install -r requirements.txt` 를 돈다. 둘이 갈라지면 **사내 컨테이너만 조용히 다른
버전을 쓴다** — 화면에 오류가 나지 않고 계산 결과만 달라질 수 있다.

- **사내에서 이 파일을 고치지 않는다.** `tests/test_requirements_export.py` 가 `uv.lock`
  과 대조하므로 고치면 검증에서 걸린다. 사외가 `uv export` 로 다시 뽑는다.
- **`uv sync` 를 이 파일로 대신하지 않는다.** 개발용 도구(ruff·mypy·pytest)가 빠져 있다.
- 이 파일에는 프로젝트 자신(`-e .`)이 **일부러 빠져 있다.** 그래서 컨테이너는
  `Dockerfile-prod` 의 `ENV PYTHONPATH=/project/src` 로 `src` 를 찾는다. 둘은 한 쌍이라
  한쪽만 보고 판단하지 않는다.

---

## 4. 적용 뒤 할 일

### 4-1. 의존성 — 변경 목록에 `pyproject.toml` 이나 `uv.lock` 이 있을 때만

```powershell
uv sync --inexact
```

맨 `uv sync` 는 `bigdataquery` 를 지운다. 지웠으면 되돌린다.

```powershell
uv pip install -r requirements-company.txt
```

### 4-2. 마이그레이션은 앱이 알아서 한다

앱을 한 번 띄우면 `data/capa_simulation.duckdb` 와 `data/equipment_availability.duckdb` 에
새 마이그레이션이 적용된다. **적용된 마이그레이션은 버전 번호로 체크섬을 대조하므로, 사내에서
SQL 파일을 고치면 앱이 시작조차 못 한다.**

**이 명령은 사용자가 친다.** 서버는 끄기 전까지 안 끝나므로 에이전트가 띄우면 세션이 거기서
멈춘다. 그리고 브라우저로 한 번 들어가야 마이그레이션이 실제로 걸린다.

```powershell
uv run --no-sync python -m streamlit run app.py
```

화면이 뜨는 것까지 확인하면 `Ctrl+C` 로 끈다. 오류가 나면 **고치지 말고** 리뷰 문서에 적는데,
**원문을 그대로 붙이지 않는다** — 이 앱의 오류 문구에는 설계상 공정명·제품명 같은 식별값이
박혀 있다. 5장의 가명화 규칙을 그대로 적용해 옮겨 적는다.

### 4-3. 네 관문을 돌린다

```powershell
uv run --no-sync python -m ruff format --check .
uv run --no-sync python -m ruff check .
uv run --no-sync python -m mypy
uv run --no-sync python -m pytest
```

**앱을 끈 뒤에 돌린다** — DuckDB 배타 잠금 때문이다. 실패가 나오면 3-2 에 해당하는지 먼저 보고,
아니면 리뷰 문서의 「발견」으로 적는다.

---

## 5. 리뷰 문서 쓰기 (이 작업의 산출물)

경로는 `review/<ZIP 파일명>.md` — 예: `review/202609201530.md`. 양식과 「실데이터를 적지
않는다」 규칙은 `docs/dual_env_workflow.md` 4장에 있다. 핵심만 옮기면:

- **값의 「꼴」은 남기고 식별자는 가명으로 쓴다.** 이 문서는 **사내에서 사외로 나가는
  유일한 것**이다.
- 좋음 — 「`Pack Code` 에 `4.00E+02` 꼴인 값이 2종, 5행」
- 나쁨 — 실제 값을 그대로 적는 것

**실데이터로 취급하는 것 (컬럼 이름으로)**

`Customer` · `제품정보` · `Capa Code` · `CS` · `공정` · `Area_Name` · `호기` · `Pack Code` ·
`WF 구분` · `Stack` · `양산구분` · `STEP_SEQ` · `MCP_SEQ` · 사람 이름과 사번 · 시뮬레이션
코드와 이름 · 파일 경로 안의 위 값들.

**무심코 붙여넣기 쉬운 자리** — 여기서 대부분 샌다.

- 오류 원문·스택트레이스 (앱 오류 문구에 공정명·제품명이 박혀 있다)
- `git diff`·`git log` 출력
- SQL 결과표, DataFrame 출력
- 화면 캡처와 그 파일 경로
- 적용기 출력의 파일 목록

**커밋 전에 스스로 한 번 돌린다.** 걸리면 그 줄을 가명으로 고친 뒤 다시 돌린다.

```powershell
Select-String -Path review\*.md -Pattern 'INTEL|AWS|BRCM|ARCM|BINTEL|HBM|DDR5|Pack ?Code *[=:] *[^ ]|[A-Z]{2,}-[0-9]{3,}'
```

한 줄도 안 나와야 한다. 이 패턴은 그물이지 보증이 아니다 — 걸리지 않아도 위 컬럼 목록을
눈으로 한 번 훑는다.

쓰고 나면 커밋한다.

```powershell
git add review
git commit -m "review: <ZIP 파일명>"
```

**푸시는 사용자가 한다.** 에이전트는 권한에서 막혀 있으므로 아래 명령을 알려 주고 멈춘다.

```powershell
git push
```

---

## 6. 막혔을 때

| 증상 | 뜻 | 할 일 |
|---|---|---|
| `작업트리에 미저장 변경이 있습니다` | 1-4 를 건너뛰었다 | 되돌리거나 커밋하고 다시 |
| `이미 적용한 ZIP 입니다` | `.deploy/applied.json` 의 stamp 와 같다 | 새 ZIP 을 받는다 |
| `과거 ZIP 입니다` | stamp 가 적용 이력보다 작다 | 최신 ZIP 을 받는다 |
| `송장이 없습니다` | 옛 스크립트로 만든 ZIP | 사외에 다시 만들어 달라고 한다 |
| `해시 대조에서 N 건이 어긋났습니다` | 전송 중 깨졌다 | `git checkout -- .` 하고 ZIP 을 다시 받는다 |
| `적용 중 멈췄습니다` | 푸는 중 실패 | 인덱스는 그대로다. `git checkout -- .` |
| `duckdb.IOException` | 앱이 떠 있다 | 앱을 끈다. 가상환경 손상이 아니다 |
| `bigdataquery` 가 사라졌다 | 맨 `uv sync` 를 돌렸다 | 4-1 의 되돌리기 |

되돌리는 법은 하나다 — **`git checkout -- .`**. 적용기는 파일을 다 풀고 대조까지 통과한 뒤에야
인덱스를 건드리므로, 중간에 멈춘 실행은 이 한 줄로 전부 돌아온다. 이미 커밋까지 갔으면
`git revert <커밋>` 이다.

---

## 6-1. 끝났다는 판정

아래가 **전부** 참이면 끝이다. 하나라도 아니면 아직이다.

- [ ] 적용기가 `대조 N/N 해시 일치` 를 찍고 `deploy: <stamp> (<커밋 7자>)` 로 커밋했다
- [ ] 적용 뒤 재대조에서 `사외에서 지워진 파일`·`목록에 있는데 사내에 없는 파일` 둘 다 비었다
- [ ] 네 관문이 전부 통과했거나, 실패한 것이 3-2 로 설명된다
- [ ] 앱이 뜨고 마이그레이션이 걸렸다
- [ ] 7장의 확인 항목을 전부 돌리고 결과를 리뷰 문서에 적었다
- [ ] 리뷰 문서를 `review:` 로 커밋했고, 5장의 자가 점검이 한 줄도 잡지 않았다
- [ ] 사용자에게 `git push` 명령을 알렸다

---

## 7. 이번 배포에서 사내가 따로 확인해야 하는 것

**이 절은 stamp `202609210815` 배포용이다.** 적용한 ZIP 의 stamp 가 이것과 다르면 이 절은
네 것이 아니다 — 사용자에게 알리고 맞는 안내를 받는다. 배포마다 사외가 이 절을 갱신해 함께
보낸다.

> **사외 메모 — 이 절과 stamp 는 서로를 가리킨다.** 이 줄을 고친 뒤 빌더를 그냥 돌리면
> 그때 시각으로 새 stamp 가 붙어 다시 어긋난다. **stamp 를 먼저 정하고** 그 값을 여기 적은
> 다음 `--stamp` 로 넘겨 만든다. 실제로 한 번 어긋나 ZIP 과 태그를 버리고 다시 만들었다.

- **`index.html` 이 이번부터 배포 세트에 들어온다.** 사내 GitHub Pages 로 띄우는 발표
  자료(중간 보고 덱)이고, 이미지까지 한 파일에 담은 단독 문서라 브라우저로 바로 열린다.
  직전 배포 때 `git rm --cached` 로 추적을 끊어 두었다면 이번 적용으로 **다시 추적 상태로
  돌아온다** — 그대로 두면 된다.
- **새 마이그레이션이 없다.** 직전 배포(`202609201104`)의 `0024`·`0025` 로 끝이고, 이번
  ZIP 에는 `.sql` 이 하나도 바뀌지 않았다. 앱을 처음 띄울 때 마이그레이션 로그가 조용하면
  정상이다.
- **화면이 눈에 띄게 바뀐다.** 오류가 아니라 의도한 변경이니 놀라지 않는다.
  - **사이드바** — 계산 그룹(Static/Dynamic)이 접힌다. 지금 보고 있는 페이지가 든 그룹만
    펴지고 나머지는 접힌 채로 열린다. 최상위 항목 넷이 같은 크기의 상자에 선다.
  - **HOME 맨 위에 결론 한 줄**이 생긴다 — 가장 낮은 확보율 공정·월과 그 근거. 공정
    필터를 걸면 **거른 뒤** 기준으로 다시 계산된다.
  - **가용설비 현황**이 `Main`·`Preference`·`RawData` 세 탭으로 갈린다. 조회기간과 조회
    조건은 `Preference` 로, 설비 데이터 편집은 `RawData` 로 옮겼다. 세 표에 「볼 컬럼」과
    행 필터가 붙었는데, **필터가 걸린 동안에는 행 추가·삭제가 잠긴다**(부분만 보이는
    상태에서 저장하면 걸러진 행이 사라지기 때문이다). 필터를 비우면 풀린다.
  - **월별 편집표**의 행 높이가 25px→30px 로 커지고, 표 위에 편집 범위가, 적용 버튼 앞에
    실제 변경 수가 뜬다.
  - **글자 크기가 전반적으로 한 단계 작아진다**(본문 15→14px, 제목 40→30px).
  - **첫 접속은 항상 밝은 테마**다. 헤더 오른쪽 `Dark`/`Light` 버튼으로 바꾼다.
- **`Top` 재이관 `0026`** — `0013`·`0014` 가 `trim("WF 구분") = 'Top'` 으로 맞댔는데 원천
  표기는 대문자 `TOP` 이라 **한 행도 바꾸지 못했다.** 적용된 파일은 고칠 수 없으므로
  `0026_edp_top_division_retry.sql` 로 다시 한다. 이 배포에 그 파일이 들어 있다.

  **순서가 중요하다. 세 단계를 이 차례로 한다.**

  ```powershell
  # 1. 적용 전에 센다 — 이 수가 곧 바뀔 행 수다
  uv run --no-sync python scripts/inspect_top_remigration.py
  # 2. 앱을 한 번 띄워 0026 을 적용한다 (러너가 트랜잭션 안에서 돌린다)
  # 3. 적용 후에 센다 — TOP 이 줄고 TOP_E 가 그만큼 늘어야 한다
  uv run --no-sync python scripts/inspect_wf_division.py
  ```

  1번이 **`0` 이면 전제가 틀린 것이다. 앱을 띄우지 말고** 1~3번 출력을 리뷰 문서로 낸다.

  1번은 `0026` 과 **같은 식**으로 센다. 그래서 그 「합계」와 3번에서 실제로 줄어든 `TOP`
  수가 같아야 한다. 크게 다르면 그 사실 자체를 리뷰 문서로 낸다. 2026-09-21 리뷰의
  40,484행은 **계획 형태만** 센 수이므로 「계획 형태만」 줄과 맞대고, 「합계」는 원천
  형태를 더한 수라 그보다 크거나 같은 것이 정상이다.

  둘 다 읽기 전용으로 열고 **값을 찍지 않는다** — 개수만 나온다. 그 출력을 그대로 리뷰
  문서에 붙여도 실데이터가 새지 않는다. 앱이 떠 있으면 잠겨서 못 여니 먼저 끈다.

  **사내에서 SQL 로 고치지 않는다** — 리비전은 append-only 이고, 되돌릴 수 없는 변경이다.
  `ref_data` 는 재적재로 복구할 수 있지만 `rev_data` 는 사용자 편집 스냅샷이라 복구되지
  않는다.
- **`Pack Code` 업무 키 승격의 후속** — `0013` 이전에 저장한 리비전은 `Pack Code` 가 비어
  있어 부하량 화면이 선다. 실데이터를 **다시 등록**해야 한다. 승격 전에 내려받은 PKG PLAN CSV
  양식도 못 쓰므로 **양식을 다시 받는다.**
- **설비대수 편집 가능 월 범위가 달라진다** — `RQ_UPEH` 에 없는 달의 설비대수는 이제 편집
  화면에 나오지 않는다. 화면이 실제로 바뀌는 부분이라 미리 알고 본다.
- **BigDataQuery 조회는 이제 풀린다 — 다만 셸에서 한 줄을 넣어야 한다.** 리뷰
  `202609201104` 가 `user_name` 을 실으면 된다는 것을 WebIDE 에서 직접 확인해 주었고, 그
  경로가 이 배포에 들어갔다. 설치·로그인·요청자 계정 세 자리를 순서대로 적은 것이
  [`bigdataquery_webide_setup.md`](bigdataquery_webide_setup.md) 다. 요약하면
  `export CAPA_BDQ_USER_NAME="<AD 계정>"` 를 넣고 앱을 다시 띄운다. 값을 안 넣으면 앱이
  `parameter user_name is necessary.` 대신 **이 환경변수를 채우라고** 알려 준다.
- **지난 리뷰에서 닫힌 것 둘** — 다시 보고하지 않아도 된다.
  - `test_exception_process_notice_stays_original_without_a_rename_profile` 실패는
    **테스트 결함**이었고 `e1d7474` 가 고쳤다. `202609201104` 가 그보다 앞선 커밋이라
    그 ZIP 에는 안 들어 있었다.
  - `st.components.v1.html` deprecation 경고는 **남겨 둔 것**이다. `st.iframe` 으로 옮겨
    보았더니 iframe 이 DOM 에 아예 생기지 않아 테마 버튼이 사라졌다(브라우저에서
    `document.querySelectorAll('iframe').length === 0` 으로 확인). 되돌린 이유가
    `components/theme_toggle.py` 의 docstring 에 적혀 있다. 경고만 나고 동작은 정상이다.
- **WebIDE 환경 두 가지를 확인해 온다** — `aws` 가 PATH 에 있는가, WebIDE 재시작 주기·디스크
  영속성은 어떻게 되는가. 답을 `docs/objectstore_setup.md` 의 표에 적을 수 있게 리뷰 문서에
  남긴다.
