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

그리고 `review/_permission_test.md` 에 아무 한 줄이나 써 본다. **막히면 거기서 멈추고**
사용자에게 알린다 — `internal_claude_settings.json` 의 `Write(*.md)` deny 가 하위 경로까지
먹는다는 뜻이고, 사외가 그 규칙을 좁혀야 한다. 확인했으면 그 파일은 지운다.

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

### 1-4. 작업트리를 비운다

```powershell
git status --porcelain --untracked-files=no
```

**한 줄이라도 나오면 적용기가 멈춘다.** 사내에서 소스를 고쳤다면 커밋하지 말고 되돌린다.

```powershell
git checkout -- <경로>
```

되돌리기 전에 그 내용이 필요하면 리뷰 문서에 코드블록으로 옮겨 적는다 — 그것은 저장소 수정이
아니다.

### 1-5. 처음 한 번이라면: 저장소 정리

`docs/dual_env_workflow.md` 8장의 정리를 **아직 하지 않았다면 배포 적용보다 먼저 한다.**
저장소에 있으면 안 되는 것이 커밋돼 있으면, 그 파일들은 ZIP 에 없으므로 「사외에서 지워진
파일」로 판정되어 적용이 지운다. 이미 했는지 모르겠으면 확인한다.

```powershell
git ls-files | Select-String -Pattern '^\.agents/|^\.omo/|\.duckdb$|^data/input/' | Select-Object -First 20
```

한 줄이라도 나오면 8장을 먼저 끝낸다.

---

## 2. 적용 (본 작업)

### 2-1. 먼저 보기만 한다

```powershell
uv run python scripts/apply_deploy_package.py <내려받은 ZIP 경로> --dry-run
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
uv run python scripts/apply_deploy_package.py <내려받은 ZIP 경로>
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
SQL 파일을 고치면 앱이 시작조차 못 한다.** 오류가 나면 고치지 말고 원문을 리뷰 문서에 적는다.

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

### 4-3. 네 관문을 돌린다

```powershell
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest
```

**앱을 끈 뒤에 돌린다** — DuckDB 배타 잠금 때문이다. 실패가 나오면 3-2 에 해당하는지 먼저 보고,
아니면 리뷰 문서의 「발견」으로 적는다.

---

## 5. 리뷰 문서 쓰기 (이 작업의 산출물)

경로는 `review/<ZIP 파일명>.md` — 예: `review/202609201530.md`. 양식과 「실데이터를 적지
않는다」 규칙은 `docs/dual_env_workflow.md` 4장에 있다. 핵심만 옮기면:

- **값의 「꼴」은 남기고 식별자는 가명으로 쓴다.** 실제 Pack Code·공정명·호기 ID·고객명을
  그대로 적지 않는다. 이 문서는 **사내에서 사외로 나가는 유일한 것**이다.
- 좋음 — 「`Pack Code` 에 `4.00E+02` 꼴인 값이 2종, 5행」
- 나쁨 — 실제 값을 그대로 적는 것

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

## 7. 이번 배포에서 사내가 따로 확인해야 하는 것

배포마다 달라지는 자리다. **사외가 ZIP 을 보낼 때 이 절을 갱신해 함께 보낸다.**

- **마이그레이션 `0024`(global_key_process)·`0025`(voc_board)가 새로 적용된다.** 앱을 처음
  띄울 때 두 DB 에 걸린다. 오류가 나면 SQL 을 고치지 말고 원문을 적는다.
- **`Top` 이관의 실제 범위** — `0013`·`0014` 마이그레이션이 `trim("WF 구분") = 'Top'` 으로
  비교하는데 원천 표기는 대문자 `TOP` 이다. 이미 저장된 리비전에 `Top_e` 행이 있는지 센다.

  ```sql
  SELECT "WF 구분", count(*) FROM ref."RQ_CHIP_QTY" GROUP BY 1;
  SELECT "WF 구분", count(*) FROM rev."RQ_CHIP_QTY" GROUP BY 1;
  ```

  **결과만 리뷰 문서에 적는다. 사내에서 SQL 로 고치지 않는다** — 리비전은 append-only 이고,
  재이관이 필요하면 사외가 후속 마이그레이션을 만든다.
- **`Pack Code` 업무 키 승격의 후속** — `0013` 이전에 저장한 리비전은 `Pack Code` 가 비어
  있어 부하량 화면이 선다. 실데이터를 **다시 등록**해야 한다. 승격 전에 내려받은 PKG PLAN CSV
  양식도 못 쓰므로 **양식을 다시 받는다.**
- **설비대수 편집 가능 월 범위가 달라진다** — `RQ_UPEH` 에 없는 달의 설비대수는 이제 편집
  화면에 나오지 않는다. 화면이 실제로 바뀌는 부분이라 미리 알고 본다.
- **BigDataQuery 조회는 이번 배포로 고쳐지지 않는다.** `parameter user_name is necessary.`
  는 사내 계정값이 필요해 아직 사외에 반영되지 않았다.
- **WebIDE 환경 두 가지를 확인해 온다** — `aws` 가 PATH 에 있는가, WebIDE 재시작 주기·디스크
  영속성은 어떻게 되는가. 답을 `docs/objectstore_setup.md` 의 표에 적을 수 있게 리뷰 문서에
  남긴다.
