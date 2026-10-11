# 사외 개발 환경 — 데스크탑 WSL(Ubuntu x86_64) + tmux

2026-10-12 부터 사외 개발은 데스크탑 WSL 의 tmux 안 Claude 에서 한다(그 전은 서피스 Windows ARM64).
이 문서는 **WSL 에서 이 저장소를 처음 받는 사람·에이전트**가 읽는다. 사내(WebIDE·사내 PC)와는 상관없다 —
사내는 그대로 Windows 이고 `docs/internal_update_runbook.md` 를 따른다. 데스크탑 쪽 일반 안내(접속 구조·샌드박스·
tmux)는 사용자의 `PC_Setting/WSL_DEV_GUIDE.md` 에 있다.

**앱 코드에는 OS 분기가 없다.** 데이터 경로는 `settings.PROJECT_ROOT` 하나에서 나오고, 런타임 외부 요청이 없으며(글꼴은
`static/fonts/` 에서 앱이 보낸다, 사용 통계는 `.streamlit/config.toml` 에서 꺼져 있다), CI(`.github/workflows/ci.yml`)가
`ubuntu-latest` · Python 3.10.11 · `uv sync --frozen` 으로 4관문을 늘 돌린다. 옮길 때 걸리는 것은 아래의 환경 준비와
Windows 에서만 되는 도구 몇 개뿐이다.

## 1. 한 번만 하는 준비 — 사용자, WSL 일반 셸(Claude 밖 tmux 창)

| 차례 | 명령 | 까닭 |
|---|---|---|
| 0 | `date` · `locale` | KST 이고 UTF-8 이어야 한다. 앱의 「오늘」과 DB 의 `current_timestamp` 가 OS 시각이다(아니면 `sudo timedatectl set-timezone Asia/Seoul`) |
| 1 | `rm -r ~/projects/streamlit_project/.claude` | 빈 임시 폴더가 있어 clone 이 「not an empty directory」로 실패한다 |
| 2 | `git clone https://github.com/ddigle/streamlit_Capa_Simulation.git ~/projects/streamlit_project` | 공개 저장소라 받는 데는 인증이 없다(푸시는 4장). Windows 작업 트리를 복사하지 않는다 — 줄바꿈이 CRLF 다 |
| 3 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` 뒤 새 셸 | `astral.sh` 는 Claude 샌드박스 허용 도메인 밖이다 |
| 4 | `cd ~/projects/streamlit_project` → `uv python install 3.10.11` | 시스템 Python 은 3.14 뿐이다. 사내·CI 와 같은 3.10.11 을 쓴다. uv 는 홈 아래(`~/.local`·`~/.cache`)에 쓰므로 Claude 밖에서 한다 |
| 5 | `uv sync --frozen --python 3.10.11` → `.venv/bin/python -V` | 락 그대로 `.venv` 를 만든다(CI 와 같은 명령). 3.10.11 이 찍혀야 한다 |
| 6 | (선택) `echo 'export STREAMLIT_SERVER_HEADLESS=true' >> ~/.bashrc` | WSLg 가 `DISPLAY` 를 두어 Streamlit 의 headless 기본값이 꺼진다 — 그러면 첫 실행이 이메일 입력을 기다리며 멈춘다. 3장의 실행 줄은 `--server.headless true` 를 늘 붙인다 |

`.venv` 는 서피스에서 옮기지 않는다(OS·CPU 가 달라 쓸 수 없다). 로컬 데이터는 git 밖이라 따로 옮긴다 —
`data/capa_simulation.duckdb`·`data/equipment_availability.duckdb`·`data/input/Core_Data.csv`·`data/input/RQ_DISPLAY_ORDER.csv`.
**합성 표본이고 실제 운영 데이터가 아니다**(`CLAUDE.md` 「로컬 데이터는 합성 표본이다」). `Core_Data.csv` 는 cp949 라
`grep`·`head`·Claude 의 Read 로 보면 한글이 깨진다 — 코드는 `config/data_contract.json` 의 인코딩으로 읽으니 다시 저장하지
않는다. 이 파일이 없으면 `scripts/generate_sample_core_data.py` 도 돌지 않는다(그 파일을 입력으로 받는다).

## 2. 명령 — Claude 안(샌드박스)에서도 같다

```bash
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
.venv/bin/python -m pytest
```

- `.venv/bin/python` 을 쓴다. `uv run` 은 홈의 uv 캐시에 쓰려 할 수 있어 샌드박스에서 막힐 수 있고, `python` 맨 명령은 WSL 에
  없다(`python3` 는 3.14). 의존성을 바꿔 `uv sync`·`uv lock` 이 필요하면 사용자가 Claude 밖에서 친다.
- **pytest 는 한 번에 다 돌려도 된다** — WSL 상한이 32GB 다. Windows 에서만 도는 테스트(`sys.platform == "win32"`)는 건너뛰고
  리눅스에서만 도는 것(`check_deploy_screens` 의 `/proc` 탐색 등)이 돈다. node 가 있으면 입장 화면 장면 테스트도 돈다.
- 테스트의 80여 파일이 `tmp_path` 로 `/tmp` 에 쓴다. 샌드박스가 `/tmp` 쓰기를 막으면 처음 한 번
  `.venv/bin/python -c "import tempfile; print(tempfile.mkstemp())"` 가 실패한다 — 그때는 `export TMPDIR=$PWD/data/temp/tmp`
  (`data/temp/` 는 무시 목록이다)로 돌린다.

## 3. 앱 띄우기와 보기

앱 서버는 **사용자가 Claude 밖 tmux 창**(`Ctrl+b` → `c`)에서 띄운다. Claude 의 Bash 는 샌드박스 안이라 거기서 띄운 서버는
브라우저에서 닿지 않을 수 있다. Claude 가 화면을 확인할 때는 `streamlit.testing.v1.AppTest` 를 쓴다.

```bash
cd ~/projects/streamlit_project && .venv/bin/python -m streamlit run app.py --server.headless true --server.port 8501
```

- 서피스에서 보려면 서피스 PowerShell 에 `ssh -N -L 8501:localhost:8501 desk` 를 열어 둔 채 `http://localhost:8501`.
- **포트는 늘 적는다.** 8501~8503 은 사용자 몫이고 에이전트의 시험 앱은 8510 이상이다(`AGENTS.md`). 포트를 빼면 Streamlit 이
  찬 포트를 피해 다음 번호로 조용히 옮겨 뜬다.

## 4. 푸시 — 사용자, 처음 한 번

샌드박스는 `~/.ssh`·`~/.config/gh` 를 막는다. `git push` 는 Claude 가 확인을 받은 뒤 샌드박스 밖에서 돌리지만, 그러려면 WSL 에
GitHub 인증이 있어야 한다. WSL 일반 셸에서 둘 중 하나.

- SSH 키: `ssh-keygen -t ed25519` → `cat ~/.ssh/id_ed25519.pub` 를 GitHub → Settings → SSH keys 에 붙인다 →
  `git remote set-url origin git@github.com:ddigle/streamlit_Capa_Simulation.git`.
- gh: `sudo apt install gh` → `gh auth login`.

## 5. 사내 배포는 서피스에서 한다

배포 메일은 서피스 Chrome(Profile 1)의 Outlook 웹으로만 보낼 수 있다. WSL 에는 브라우저가 없다. 그래서

1. **WSL** — 개발·검증·런북 7장 작성까지 하고 `main` 을 푸시한다.
2. **서피스** — 배포 지시가 오면 `git pull` → stamp 를 정해 런북 자리표(`<STAMP>`·`{APPLY_FACTS}`)를 흉내 저장소 적용 값으로 채운다
   → `scripts/build_deploy_package.py --stamp` → ZIP 검증 → 메일 → 태그·기록 커밋 푸시.

## 6. Windows 에서만 되는 것 — WSL 에서는 하지 않는다

| 무엇 | 까닭 | WSL 에서는 |
|---|---|---|
| `scripts/validate_duckdb_persistence.py`·`scripts/bootstrap_initial_duckdb_scenario.py` | `io/excel_reader.py` 가 xlwings 로 Excel 을 띄우고 `templates/structure_template.xlsb`(git 밖, 서피스에만 있다)를 읽는다 | 돌리지 않는다. xlwings 는 의존성에 남는다 — 리눅스에도 깔리고 사내가 쓴다 |
| `scripts/check_deploy_screens.py` 실행 | 깔린 Chrome 과 Playwright 가 있어야 한다(사내 런북 7장 도구) | `--list` 만 된다 |
| 화면 E2E(agent-browser·Claude in Chrome)·배포 메일 | 브라우저가 없다 | AppTest 로 확인하고, 실제 화면은 사용자가 포트 전달로 본다 |
| `scripts/new_worktree.ps1`(병행 개발 작업 폴더) | PowerShell 전용이고, 기본 자리(저장소 옆 `../capa-<이름>`)가 샌드박스 쓰기 범위 밖이다 | 아직 정하지 않았다 — 데스크탑 안내서의 `claude -w <이름>`(저장소 안 `.claude/worktrees/`, 무시 목록에 있다)을 쓰거나, 사용자가 Claude 밖에서 저장소 옆에 만든다. 작업 폴더마다 `uv sync --frozen --python 3.10.11` 은 사용자가 친다 |

## 7. 서피스에 남겨 둔 것

- `templates/structure_template.xlsb`(Excel, git 밖) — 옮기지 않았다. 필요하면 사용자가 따로 가져온다.
- `data/temp/` 백업 DB, `data/output/` 옛 ZIP, `data/input/backup/` — 옮기지 않았다.
- stash 하나(`bigdataquery user_name` — 사내 값 확인 뒤 반영하려던 BigDataQuery 사용자 이름 시험분)와 옛 후보 브랜치
  `cand/*` 일곱(병행 개발 후보 — 기능은 고친 꼴로 `main` 에 들어갔다. `cand/설비UI개편/claude` 만 GitHub 에도 있다).
