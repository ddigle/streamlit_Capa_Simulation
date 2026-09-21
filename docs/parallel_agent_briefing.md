# 병행 개발 에이전트 브리핑

이 문서는 **후보 에이전트로 이 저장소에 처음 들어오는 사람(또는 에이전트)** 을 위한 것이다.
규칙의 정본은 `AGENTS.md` 14장이고, 여기는 **시작하는 법과 하루의 흐름**을 적는다.

먼저 `CLAUDE.md` → `AGENTS.md` 순으로 읽는다. 이 문서는 그 둘을 대신하지 않는다.

---

## 0. 한 줄 요약

**자기 폴더 안에서만 일하고, 자기 브랜치에만 올리고, 자기 번호만 쓴다.**
셋 다 이름에서 나온다 — 브랜치가 `cand/<과제>/<에이전트>` 면 나머지가 따라온다.

| 에이전트 | 작업 폴더 | 포트 | 마이그레이션 번호 |
|---|---|---|---|
| (통합) | `C:\Dev\Streamlit_Project` | 8501 | — |
| claude | `C:\Dev\capa-claude` | 8502 | **홀수** |
| codex | `C:\Dev\capa-codex` | 8503 | **짝수** |

이 표의 정본은 `config/parallel_agents.json` 이다. 스크립트와 검사가 그 파일을 읽으므로
여기 적힌 값과 어긋나면 그 파일이 맞다.

**8501~8503 은 예약이다.** 동작을 재려고 시험용 앱을 띄우거나 데모·샘플을 열 때는
**8510 이상**을 쓴다. 이 셋에 얹으면 Windows 에서 오류 없이 먼저 뜬 프로세스로 접속이
몰려, 사용자가 보는 화면이나 상대 에이전트가 보는 화면이 **말없이 남의 것**이 된다.

```powershell
# 시험용·데모는 이렇게
.\.venv\Scripts\python.exe -m streamlit run <시험용>.py --server.port 8510
```

---

## 1. 시작

통합 폴더(`C:\Dev\Streamlit_Project`)에서 **한 번만** 실행한다.

```powershell
.\scripts\new_worktree.ps1 -Branch cand/<과제>/<에이전트>
```

브랜치·폴더·`.venv`·격리 확인·실행기(`run.ps1`)가 한 번에 만들어진다. 포트는 브랜치
마지막 조각에서 정해지므로 주지 않는다. 모르는 이름이면 **아무것도 만들지 않고 멈춘다.**

그 뒤로는 만들어진 폴더에서만 일한다.

```powershell
cd C:\Dev\capa-<에이전트>
.\run.ps1          # 배정된 포트로 뜬다. 띄우기 전에 격리도 본다.
```

### 폴더는 한 번, 브랜치는 과제마다

폴더 이름은 브랜치 **마지막 조각**에서 나오므로 에이전트마다 하나다(`capa-codex`). 그래서
**새 과제를 받았다고 폴더를 다시 만들지 않는다** — `uv sync` 가 400MB 를 다시 깔고, 스크립트도
「이미 있습니다」로 멈춘다.

과제가 바뀌면 **그 폴더 안에서 브랜치만 새로 딴다.**

```powershell
cd C:\Dev\capa-<에이전트>
git fetch origin
git switch -c cand/<새 과제>/<에이전트> origin/main
```

`origin/main` 에서 새로 따는 것이 중요하다 — 앞 과제 위에 쌓으면 채택되지 않은 코드가 다음
후보에 묻어 들어가고, 홀짝 검사도 `main` 과의 갈림점을 보므로 앞 과제의 마이그레이션이 내
것으로 잡힌다.

폴더를 다시 만들어야 하는 경우는 하나뿐이다 — `.venv` 가 망가졌을 때.

---

## 2. 기계가 잡아 주는 것

**어긴 줄 모르고 지나갈 수 없다.** 아래는 검사가 있다.

| 무엇 | 무엇이 잡나 |
|---|---|
| 남의 `.venv` 를 쓰는 것 | `scripts/check_worktree_isolation.py` |
| 포트를 빠뜨리는 것 | `run.ps1` 이 포트를 박고 있다 |
| 세션 키 겹침 | `tests/test_session_key_collisions.py` |
| 마이그레이션 홀짝·결번·중복 | `tests/test_migration_parity.py`, `tests/test_migration_numbering.py` |
| 문서와 코드가 어긋나는 것 | `tests/test_repository_hygiene.py`, `tests/test_source_metadata.py` |

`.venv` 는 특히 조심할 값어치가 있다. 남의 것을 쓰면 **화면은 내 코드인데 `import` 는 남의
`src/` 를 읽고 남의 DuckDB 를 연다.** 그 상태에서도 검증 4종은 전부 초록이다 — 실제로
재 봤다(격리 검사는 종료코드 1, `pytest` 는 14개 전부 통과).

---

## 3. 기계가 못 잡는 것 — 이건 기억해야 한다

**`git stash` 를 쓰지 않는다.** 스태시·태그·브랜치는 세 폴더가 **공유**한다. 한쪽에서
쌓은 스태시가 다른 쪽에 보이고, 남의 것을 `pop` 하면 그 작업이 사라진다. 잠깐 치워야
하면 커밋을 하나 만든다(후보 브랜치는 어차피 합치기 전에 정리한다).

**배포 ZIP 은 통합 폴더에서만 만든다.** 빌더는 자기 위치의 작업트리를 읽고 그 HEAD 에
태그를 박는데 브랜치 검사가 없다. 후보 브랜치에서 만들면 미채택 코드가 사내 정본으로
나가고 태그가 엉뚱한 커밋에 박힌다.

**`HANDOFF.md` 는 병행 중 편집하지 않는다.** 한 시점의 세션 스냅샷이라 둘이 쓰면 뜻이
없어진다. 합친 뒤 통합하는 쪽이 한 번만 쓴다. `README.md` 도 통합하는 쪽만 고친다.

**`AGENTS.md`·`docs/TODO.md` 는 절 단위로 소유를 나눠 받는다.** 문서 **끝에 새 절을
덧붙이는 것**이 가장 자주 충돌한다 — 번호를 미리 배정받지 않았으면 새 절을 만들지 않는다.

**단일 선언 지점은 한 주기에 한 에이전트만 손댄다.** `navigation.py` 의 `SIDEBAR_GROUPS`,
`design/tokens.py`, `config/data_contract.json`, `services/frame_contracts.py`,
`tests/test_repository_hygiene.py` 의 `ALLOWED_TOP_LEVEL`. 새 화면을 만들면 반드시
첫 번째에서 만난다.

**커밋 `author` 를 바꾸지 않는다.** 세 폴더가 같은 `.git/config` 를 공유해 한쪽에서
`git config user.name` 을 바꾸면 다른 폴더까지 바뀐다. 누가 했는지는 트레일러
(`Co-Authored-By:`)로 가른다.

**충돌은 에이전트가 흡수한다.** 사용자에게 `<<<<<<<` 를 내밀지 않는다. 양쪽 의도를 읽고
푼 뒤 **무엇을 어떻게 골랐는지 한 줄로 보고**한다.

---

## 4. 올리기 전

자기 폴더에서 검증 4종을 돌린다. 앱이 떠 있으면 먼저 끈다 — DuckDB 는 프로세스 배타
잠금이라 같은 DB 를 여는 테스트가 실패한다.

```powershell
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts\check_worktree_isolation.py
```

화면을 바꿨으면 `streamlit.testing.v1.AppTest` 나 실제 브라우저로 **진입 → 수정 →
페이지 왕복**까지 본다. 색·잘림·줄바꿈은 브라우저로만 보인다.

밀면 CI 가 같은 4종을 돌린다(`cand/**` 푸시에서 곧바로 돈다). **저장소가 private + Free 라
「통과해야만 병합」은 강제되지 않는다** — 빨간 것을 합치지 않는 것은 사람이 지킨다.

---

## 5. 합친 뒤

각 브랜치에서는 초록인데 합치면 빨개지는 자리가 있다. 위생 검사 3종이 대표적이다 —
한쪽이 문서를 지우고 다른 쪽이 그것을 가리키는 링크를 더하면 둘 다 자기 브랜치에서는
통과한다. **통합 폴더에서 한 번 더 돌린다.**

에이전트의 「검증 통과했습니다」를 그대로 믿지 않는다. CI 의 체크 표시가 근거이고,
없으면 통합하는 쪽이 직접 돌린 결과가 근거다.

---

## 6. 정리

채택되지 않았으면 통합 폴더에서 지운다.

```powershell
git worktree remove C:\Dev\capa-<에이전트>
git branch -D cand/<과제>/<에이전트>
```

**그 브랜치가 마이그레이션 번호를 이미 썼으면 그 번호를 영구 결번으로 등록한다**
(`tests/test_migration_numbering.py` 의 `BURNED_VERSIONS` 와 `docs/migration_catalog.md`).
러너가 버전으로 체크섬을 대조하므로 되돌리는 다른 방법이 없다.
