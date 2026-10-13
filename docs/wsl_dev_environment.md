# 사외 개발 환경 — 데스크탑 WSL(Ubuntu x86_64) + tmux

사외 개발·운영은 데스크탑 WSL 의 tmux 안 Claude **한 곳**에서 한다. 2026-10-12 에 서피스(Windows ARM64)에서 옮기기로 했고
10-13 에 준비를 끝냈다. 같은 날 사용자 결정으로 서피스와 병행 개발하지 않는다 — 서피스에서 Claude CLI 로 개발하던 환경은 지운다(지우기 전에 볼 것은 7장).
이 문서는 **사외 WSL 에서 이 저장소를 받거나 그 위에서 일하는 사람·에이전트**가 읽는다. 사내(WebIDE·사내 PC)와는 상관없다 —
사내는 그대로 Windows 이고 `docs/internal_update_runbook.md` 를 따른다. 그래서 `CLAUDE.md`·`AGENTS.md` 의 PowerShell 명령은 Windows
꼴로 남고(사내, 그리고 아직 WSL 판이 없는 `AGENTS.md` 14장 병행 절차), 사외(WSL)는 이 문서의 bash 명령을 쓴다. 데스크탑 쪽 일반 안내(접속 구조·샌드박스·tmux)는 사용자의
`PC_Setting/WSL_DEV_GUIDE.md` 에 있다.

**앱 코드에는 OS 분기가 없다.** 데이터 경로는 `settings.PROJECT_ROOT` 하나에서 나오고, 앱 코드는 런타임에 밖으로 묻지 않으며(글꼴은
`static/fonts/` 에서 앱이 보낸다, 사용 통계는 `.streamlit/config.toml` 에서 꺼져 있다 — Streamlit 자신의 시작 배너 질의는 3장),
CI(`.github/workflows/ci.yml`)가 `ubuntu-latest` · Python 3.10.11 · `uv sync --frozen` 으로 4관문을 늘 돌린다. WSL 에서 걸리는 것은
아래의 환경 준비·샌드박스 사정과 Windows 에서만 되는 도구 몇 개뿐이다.

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

`.venv` 는 서피스에서 옮기지 않는다(OS·CPU 가 달라 쓸 수 없다). 로컬 데이터는 git 밖이라 서피스의 10-12 사본을 따로 옮겼다 —
`data/capa_simulation.duckdb`·`data/equipment_availability.duckdb`·`data/input/Core_Data.csv`·`data/input/RQ_DISPLAY_ORDER.csv`.
서피스를 지우면 이 WSL 사본이 하나뿐이다(그 뒤 서피스 앱에서 저장한 것은 7장). **합성 표본이고 실제 운영 데이터가
아니다**(`CLAUDE.md` 「로컬 데이터는 합성 표본이다」). `Core_Data.csv` 는 cp949 라 `grep`·`head`·Claude 의 Read 로 보면 한글이
깨진다 — 코드는 `config/data_contract.json` 의 인코딩으로 읽으니 다시 저장하지 않는다. 이 파일이 없으면
`scripts/generate_sample_core_data.py` 도 돌지 않는다(그 파일을 입력으로 받는다).

## 2. 명령 — Claude 안(샌드박스)에서도 같다

```bash
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
.venv/bin/python -m pytest
```

같은 네 줄의 PowerShell 판(`.\.venv\Scripts\python.exe -m …`)은 Windows 꼴이다(`CLAUDE.md` 「명령」) — 사내가 배포 확인 때 치는 꼴은
런북 4-3 의 `uv run --no-sync python -m …` 이다.

- `.venv/bin/python` 을 쓴다. `python` 맨 명령은 WSL 에 없다(`python3` 는 3.14). uv 는 홈의 캐시(`~/.cache/uv`)에 쓰는데 샌드박스가
  막는다 — 캐시를 돌리지 않으면 `uv run` 은 물론 점검만 하는 `uv sync --check` 도 Read-only file system 으로 실패한다. 락과 `.venv` 가
  맞는지 볼 때는 `UV_CACHE_DIR=$TMPDIR/uvcache uv sync --frozen --check --offline --python 3.10.11` — 「Would make no changes」면
  맞다. 의존성을 바꿔 `uv sync`·`uv lock` 이 필요하면 사용자가 Claude 밖에서 친다.
- **pytest 는 한 번에 다 돌려도 된다** — WSL 상한이 32GB 다. 10-13 샌드박스 첫 실행은 3147 통과 · 11 건너뜀 · 1 xfail, 11분 37초였다.
  건너뛴 11 은 Windows 전용 9(`tests/test_check_deploy_screens.py` 의 `skipif(sys.platform != "win32")`, 6장), 후보 브랜치 전용 1
  (`test_migration_parity`), uv 캐시 1(`test_requirements_export` — 위의 캐시 탓이고 `UV_CACHE_DIR=$TMPDIR/uvcache` 를 붙여 돌리면
  통과한다)이다. 리눅스에서만 도는 것은 `test_linux_containment_failure_stops_the_start`(`PR_SET_PDEATHSIG` 실패 경로, popen 가짜)
  하나다 — `/proc` 를 읽는 `_proc_commands` 는 어떤 테스트도 실제로 부르지 않는다. node 가 있으면(WSL 에는 있다) 입장 화면 장면
  테스트도 돈다.
- 테스트의 80여 파일이 `tmp_path` 로 임시 폴더에 쓴다. 샌드박스는 `/tmp` 자체를 막지만 `TMPDIR` 을 `/tmp/claude-<uid>`(이 PC 는
  `/tmp/claude-1000`)로 두므로 `tempfile`·`tmp_path` 는 그대로 돈다. **`TMPDIR` 이 비면 파이썬 `tempfile` 은 실패하지 않고 현재
  폴더 — 저장소 루트 — 로 내려간다**(`env -u TMPDIR .venv/bin/python -c 'import tempfile; print(tempfile.gettempdir())'` 가 저장소
  루트를 찍는다). 오류로는 드러나지 않으니 저장소 루트에 낯선 임시 파일이 쌓이면 `echo $TMPDIR` 로 보고, 비었으면 저장소 밖
  자리(샌드박스가 두던 `/tmp/claude-<uid>`)로 `export TMPDIR=…` 한다. 무시 목록인 `data/temp/` 아래는 그 자리도 막힐 때의 마지막 수단이다.
- 샌드박스는 세션마다 저장소 루트에 0바이트 읽기 전용 자리 파일 11개(`.bash_profile` `.bashrc` `.gitconfig` `.gitmodules` `.idea`
  `.mcp.json` `.profile` `.ripgreprc` `.vscode` `.zprofile` `.zshrc`)를 실제 디스크에 만든다. `.gitignore` 에 걸리지 않아(`.idea/`·
  `.vscode/` 는 디렉터리 규칙이다) 10-13 에 사용자가 `.git/info/exclude` 에 `/` 로 고정한 11줄을 넣었다(주석 「Claude Code 샌드박스
  자리표」). `.claude/` 아래에도 같은 꼴이 생기지만 `.gitignore` 의 `.claude/` 가 덮는다. 그래도 `git add -A`·`git add .` 는 쓰지 않고
  파일을 이름으로 올린다.
- `origin` 은 SSH(`git@github.com:ddigle/streamlit_Capa_Simulation.git`)다. 샌드박스가 `~/.ssh` 를 막아 샌드박스 안에서는 `git fetch`·
  `pull`·`ls-remote origin` 이 「Host key verification failed」로 실패한다 — `pull` 은 사용자가 Claude 밖 tmux 창에서 친다. 공개
  저장소라 원격을 보기만 할 때는 `git ls-remote https://github.com/ddigle/streamlit_Capa_Simulation.git` 가 된다.
- 샌드박스는 PID·네트워크 이름공간이 갈린다. 사용자가 tmux 에 띄운 앱(8501)은 `ps` 에 안 보이고 포트로도 닿지 않는다 — 떠 있는지는
  샌드박스에서 알 수 없다. DuckDB 잠금은 그래도 걸린다: 샌드박스 둘 사이에 시험하면 `duckdb.IOException … Conflicting lock is held
  in PID 0` 으로 막히고 잡은 PID 만 0 으로 찍힌다(10-13 확인).

## 3. 앱 띄우기와 보기

앱 서버는 **사용자가 Claude 밖 tmux 창**(`Ctrl+b` → `c`)에서 띄운다. Claude 의 Bash 는 샌드박스 안이라 네트워크 이름공간이 갈려
거기서 띄운 서버에는 브라우저가 닿지 않는다(2장). Claude 가 화면을 확인할 때는 `streamlit.testing.v1.AppTest` 를 쓴다.

```bash
cd ~/projects/streamlit_project
.venv/bin/python -m streamlit run app.py --server.headless true --server.port 8501 --browser.serverAddress localhost
```

- `--browser.serverAddress localhost` 는 Streamlit 이 밖에 묻지 않게 한다. headless 이고 `server.address`·`browser.serverAddress` 를
  따로 주지 않으면 Streamlit 은 시작 배너의 External URL 을 찍으려 `checkip.amazonaws.com`(http, 안 되면 https)에 1초 제한으로 묻는다
  (`streamlit/web/bootstrap.py` 의 `_print_url` → `net_util.get_external_ip`). 이 플래그를 주면 묻지 않고 배너에 `URL: http://localhost:8501`
  한 줄만 찍힌다(10-13 확인). 기본값이 이미 `localhost` 라 그 밖의 동작은 그대로다. `.streamlit/config.toml` 에는 넣지 않는다 — 그
  파일은 사내로도 가서 사내 배너의 Network URL 줄이 사라진다. 사내 화면 확인 스크립트(`scripts/check_deploy_screens.py` 의
  `app_command`)는 `--server.address` 를 주므로 원래 묻지 않는다.
- 서피스에서 보려면 서피스 PowerShell 에 `ssh -N -L 8501:localhost:8501 desk` 를 열어 둔 채 `http://localhost:8501`.
  서피스 8501 앱이 아직 떠 있으면(7장 정리 전) 로컬 포트가 겹쳐 실패한다 — 그때는 `-L 8601:localhost:8501` 로 열고 `http://localhost:8601`.
- **포트는 늘 적는다.** 8501~8503 은 사용자 몫이고 에이전트의 시험 앱은 8510 이상이다(`AGENTS.md`). 포트를 빼면 Streamlit 이
  찬 포트를 피해 다음 번호로 조용히 옮겨 뜬다.

## 4. 푸시 — 사용자, 처음 한 번

샌드박스는 `~/.ssh`·`~/.config/gh` 를 막는다. `git push` 는 Claude 가 확인을 받은 뒤 샌드박스 밖에서 돌리지만, 그러려면 WSL 에
GitHub 인증이 있어야 한다. WSL 일반 셸에서 둘 중 하나.

- SSH 키: `ssh-keygen -t ed25519` → `cat ~/.ssh/id_ed25519.pub` 를 GitHub → Settings → SSH keys 에 붙인다 →
  `git remote set-url origin git@github.com:ddigle/streamlit_Capa_Simulation.git`.
- gh: `sudo apt install gh` → `gh auth login`.

## 5. 사내 배포 — WSL 에서 빌드해 서피스로 넘기고 메일은 사용자가 보낸다

2026-10-13 사용자 결정. ZIP 빌드·확인·태그·서피스 전달까지 WSL Claude 가 하고, 메일 발송만 사람 손에 남는다 — Claude Code 의
Chrome 연동은 WSL 을 지원하지 않아(공식 문서) WSL Claude 는 메일을 보낼 수 없다. **서피스 Claude 세션은 배포에 쓰지 않는다** —
서피스 Claude in Chrome 으로 Outlook 웹 메일을 보내던 절차는 예비로만 남는다. 메일 규격(보낸 사람·받는 사람·제목 = `<STAMP>.zip`·본문
한 줄)은 지난 배포 메일과 같고, **주소는 이 공개 저장소에 적지 않는다** — WSL Claude 가 보고 끝에 적는다(에이전트 메모리).
10-13 에 `bfe9a10` 을 WSL 에서 다시 빌드(뒤 태그를 지운 복제)해 직전 배포 상태 흉내 저장소에 적용하니 적용기 출력이
`변경 추가 13 · 수정 143` · 해시 602/602 로 서피스에서 잰 런북 값과 같았다.

**두 자리.**

- **ZIP 은 `~/projects/Deploy/` 에 만든다** — 저장소 밖, 사내 리뷰를 받는 `~/projects/Review/` 옆. 저장소 안 `data/output/` 은 무시
  목록이지만 저장소를 다시 받으면 함께 사라지고 앱 산출물과 섞인다. 보낸 ZIP 은 여기 쌓아 둔다. 샌드박스는 저장소와 `$TMPDIR` 밖에
  쓰지 못하므로 사용자 설정 `sandbox.filesystem.allowWrite` 에 이 폴더가 있어야 한다(10-13 에 폴더를 만들고 허용을 넣었다 — 실행 중인 세션에 바로 먹었다) — 없으면 빌더가
  `Read-only file system` 으로 멈춘다. 그때는 우회하지 않고 사용자에게 알린다.
- **서피스 받는 자리는 `C:\Dev\update_publishing`** 이다(10-13 서피스 세션이 세팅·시험). WSL `~/.ssh/config` 의 `Host surface` 가 배포
  전용 키로 붙고, 서피스 sshd 는 키 로그인·Tailscale 대역만 받으며 이 키로는 그 폴더에 갇힌 sftp 만 된다(셸·포워딩 없음 — 도착·`whoami`
  거부·`cd ..` 거부까지 시험). 그래서 `scp <STAMP>.zip surface:` 가 그 폴더에 바로 놓는다. `~/.ssh` 와 Tailscale 주소를 쓰므로 **샌드박스
  밖에서만** 돈다 — 배포마다 승인 한 번.

차례 — 사용자가 배포하라고 할 때.

1. **런북 7장 값 채우기 → 4관문 → 커밋 → `main` 푸시** (WSL Claude)
   1. 이번에 실을 변경과 자리표(`<STAMP>`·`{APPLY_FACTS}`)가 든 런북 7장 초안을 먼저 커밋한다 — 송장의 변경 목록은 직전 태그에서
      HEAD 까지의 git diff 라 커밋하지 않은 수정은 세지 않는다.
   2. stamp(`YYYYMMDDHHMM`, KST — `date +%Y%m%d%H%M`)를 정해 `<STAMP>` 를 채운다.
   3. 흉내 저장소로 수치를 잰다. 자리는 `$TMPDIR` 아래이고(샌드박스 쓰기 범위, 세션끼리 공용이라 이름에 stamp 를 붙인다), 사내처럼
      적용 기록을 둔다.

      ```bash
      P=<직전 stamp>; M=$TMPDIR/mock-<STAMP>
      git clone -q --no-hardlinks . $M && git -C $M checkout -q -B mock deploy/$P && mkdir -p $M/.deploy
      printf '{"stamp": "%s", "commit": "%s"}\n' $P $(git rev-parse deploy/$P) > $M/.deploy/applied.json
      git -C $M add .deploy/applied.json && git -C $M commit -qm "적용 기록 $P"
      ```

      적용 기록(`.deploy/applied.json` — 사내 전용 자리라 어느 태그에도 없어 폴더부터 만든다)을 커밋해 두면 적용기의 「건너뛴 배포」
      검사가 사내처럼 돈다. 런북의 `{APPLY_FACTS}` 를 잠깐 다른 표식으로 바꿔 저장소 루트에서
      `.venv/bin/python scripts/build_deploy_package.py --out $TMPDIR/trial --stamp <STAMP> --no-tag` →
      `.venv/bin/python $M/scripts/apply_deploy_package.py $TMPDIR/trial/<STAMP>.zip`(흉내 저장소에는 `.venv` 가 없고 `uv run` 은
      샌드박스에서 막힌다). 시험 빌드는 커밋·푸시 전이라 빌더가 「시험 빌드(--no-tag)라 멈추지 않습니다」 와 수정·앞선 커밋을 찍는다 —
      정상이다. 시험 ZIP 을 만든 뒤 표식은 `{APPLY_FACTS}` 로 되돌린다 — 빌더는 이 둘만 보므로 다른 표식이 남으면 막지 못한다.
   4. 런북 수치는 적용기 출력 그대로 옮긴다 — `변경` 줄·`지움`·대조 블록의 개수·`대조 N/N 해시 일치`. mypy 파일 수는 4관문 끝줄에서.
      흉내 저장소를 `git diff` 로 세면 송장과 기준이 달라진다(적용 기록이 없으면 `A .deploy/applied.json` 이 하나 더 나온다).
   5. 런북을 채우고 4관문 → `.venv/bin/python scripts/check_deploy_screens.py --list` 가 7-14 A 표와 같은 줄인지 → 커밋 →
      확인을 받아 `git push origin main`(샌드박스 밖 — 4장).
2. **깨끗한 트리에서 빌드 → 확인 → 태그 푸시** (WSL Claude)

   ```bash
   .venv/bin/python scripts/build_deploy_package.py --out ~/projects/Deploy --stamp <STAMP>
   ```

   빌더는 먼저 「추적 파일에 커밋하지 않은 수정이 없다」·「HEAD 가 `origin/main` 과 같다」를 보고 어기면 ZIP 도 태그도 만들지 않고
   멈춘다 — 목록은 `git ls-files` 에서 오고 내용은 작업 트리에서 읽어, 어기면 송장의 커밋과 ZIP 내용이 어긋난다. `origin/main` 은
   샌드박스가 fetch 하지 못해 마지막 푸시·pull 때 값이다. 출력에 `태그 deploy/<STAMP>` 와 `직전 <직전 stamp> 대비` 가 찍혔는지 본다 —
   `남기지 못했습니다` 가 보이면 멈추고 남은 시험 태그를 `git tag -d` 로 지운 뒤 다시 만든다. 추적하지 않는 파일이 `알림` 으로 찍히면
   실을 것이 빠졌는지 본다(ZIP 에 실리지 않는다). 그다음 셋을 본다.

   1. ZIP 자체 — `Z=~/projects/Deploy/<STAMP>.zip; .venv/bin/python -m zipfile -t $Z; sha256sum $Z; stat -c %s $Z`. 첫 명령은 깨진 항목이
      있어도 종료 코드 0 으로 「Done testing」을 찍으므로 **그 한 줄만** 나와야 한다(`corrupted` 줄이 없어야 한다). sha256 과 크기는
      보고·발송 기록에 적는다.
   2. 직전 배포와 목록 비교 — 이름으로 견준다. `>` 는 이번에 더한 것, `<` 는 지운 것이고, 런북 7장 「이 ZIP 이 싣는 것」·송장의 추가·삭제와
      맞아야 한다.

      ```bash
      diff <(git ls-tree -r --name-only deploy/<직전 stamp>) <(.venv/bin/python -c "import sys,zipfile; print('\n'.join(sorted(n for n in zipfile.ZipFile(sys.argv[1]).namelist() if n != 'DEPLOY_MANIFEST.json')))" $Z)
      ```

      그다음 위 1단계 3) 과 같은 꼴로 **새** 흉내 저장소(`M=$TMPDIR/final-<STAMP>`)를 만들어 최종 ZIP 을 적용한다. 적용기의 `변경` 줄·
      `지움`·대조 블록의 개수·`대조 N/N 해시 일치` 가 런북 값과 같아야 한다(적용기는 이름을 몇 개까지만 찍으므로 이름은 위 diff 로 본다).
   3. ZIP 내용 = 푸시한 커밋 — 그 흉내 저장소에서 `git -C $M diff --stat <HEAD 커밋> -- . ':(exclude).deploy' 2>&1` 이 아무것도 찍지
      않아야 한다(`<HEAD 커밋>` 은 저장소 루트의 `git rev-parse HEAD`). git 은 줄끝을 맞춘 뒤 견주므로 줄끝만 다르면 diff 가 아니라
      `CRLF will be replaced` 경고로만 나온다 — 그래서 `2>&1` 로 함께 본다.

   어긋나면 태그를 올리기 전이므로 `git tag -d deploy/<STAMP>` → 고쳐 커밋·푸시 → 다시 빌드한다. 맞으면 확인을 받아
   `git push origin deploy/<STAMP>`(샌드박스 밖). `--tags` 는 쓰지 않는다 — 남은 시험 태그가 함께 올라간다.
3. **서피스로 넘긴다** (WSL Claude, 샌드박스 밖 — 승인 한 번)

   ```bash
   scp ~/projects/Deploy/<STAMP>.zip surface: && sftp -b - surface <<< 'ls -l <STAMP>.zip'
   ```

   `ls -l` 의 크기가 위 2단계 1) 의 `stat` 값과 같은지 본다. 서피스 OpenSSH 가 양자 내성 키 교환을 몰라 접속마다
   `** WARNING: connection is not using a post-quantum key exchange algorithm.` 석 줄이 찍힌다 — 실패가 아니다. 그다음 보고 끝에 ZIP 이름·크기·sha256 과 메일 규격(보낸 사람·받는 사람·제목
   `<STAMP>.zip`·본문 한 줄)을 적어 넘긴다.
4. **사용자** — 서피스 Outlook 에서 `C:\Dev\update_publishing\<STAMP>.zip` 을 붙여 보낸다.
5. **WSL Claude** — 사용자가 「보냈다」고 하면 HANDOFF·TODO 에 발송(시각·stamp·커밋·크기)을 적어 커밋한다. 이 기록 커밋은 다음
   푸시 때 함께 올린다(확인 뒤).

**첫 WSL 빌드의 줄끝.** 서피스에서 만든 ZIP 은 디스크의 CRLF 를 그대로 실었다(`202610081500` 은 63개 — `docs/TODO.md` 그 배포
기록, `202610120655` 는 57개 — 10-13 서피스 받는 자리에서 받아 와 태그 블롭과 견준 수). 블롭은 LF 이고 서피스 작업 트리만 CRLF 였다. WSL 작업 트리는 `.gitattributes` 의
`* text=auto eol=lf` 대로 LF 라(`*.ps1` 만 CRLF) 첫 WSL ZIP 은 그 파일들을 내용은 같고 줄끝만 LF 로 싣는다. 10-13 에 흉내 저장소로
쟀다 — `bfe9a10` 의 WSL 빌드를 `202610081500` 상태 흉내 저장소에 적용하되, 사내 작업 트리를 흉내 내 텍스트 파일 584개(상한)를
CRLF 로 바꾸고 `git add` 로 인덱스를 새로 고쳐(사내 적용기가 서피스 ZIP 을 풀고 커밋한 뒤와 같은 상태) 두어도 적용기의 `변경`·`지움`·「사내에 없는 파일」·`대조 N/N` 이 LF 대조군과 같았고(추가 13 · 수정 143 · 지움 없음 ·
13 · 602/602), `core.autocrlf true` 여도 같았다. 송장의 `changes` 는 사외 블롭끼리, 지움·대조 블록은 경로 목록끼리 견주고 해시는
ZIP 바이트를 쓴 뒤 재기 때문이다. **그래서 런북 7장 기대값은 고치지 않는다.** 달라지는 경우는 하나다 — 사내 인덱스에 CRLF 가
든 블롭이 있으면(`git ls-files --eol` 의 `i/crlf`·`i/mixed`) 그 파일들이 줄끝만 바뀐 채 `deploy:` 커밋에 함께 실린다(같은 실험에서
그 584개와 `scripts/new_worktree.ps1` 까지 585개를 CRLF 블롭으로 커밋해 두니 커밋 파일이 157 → 598). `.gitattributes` 가 첫 커밋부터
있어 처음 `git add` 때 모두 LF 로 들어갔을 것이라 사내는 0 이어야 하지만 — 명시 `text` 경로는 다시 add 하면 정규화되고 `text=auto`
경로(`.sql` 등)는 인덱스에 CRLF 가 있으면 그대로 남는다 — 사외에서 볼 수 없으니, **첫 WSL ZIP 의 7장에 한 번** 적용 전
`(git ls-files --eol | Select-String 'i/(crlf|mixed)').Count`(기대 0)와 적용 뒤 `deploy:` 커밋 파일 수(`git show --stat --format= HEAD`
끝줄, 기대 = 흉내 저장소에서 같은 명령으로 잰 수)를 결과 꼴에 넣고, 「줄끝만 바뀐 파일이 커밋에 끼면 결함이 아니다 — 수만
적는다」를 런북 3장(적용 뒤 읽는 법) 꼴의 한 줄로 그 7장에 단다.

## 6. Windows 에서만 되는 것 — WSL 에서는 하지 않는다

서피스 개발 환경을 지우면(7장) 아래의 Excel 경로와 Windows 전용 테스트는 사외에서 돌릴 곳이 없다 — 남는 자리는 사내 Windows 다.

| 무엇 | 까닭 | WSL 에서는 |
|---|---|---|
| `scripts/validate_duckdb_persistence.py` | `io/excel_reader.py` 가 xlwings 로 Excel 을 띄우고 `templates/structure_template.xlsb`(git 밖, WSL 에 없다)를 읽는다 | 사외에는 돌릴 곳이 없다. xlwings 는 의존성에 남는다 — 리눅스에도 깔리고 import 도 되며 사내가 쓴다 |
| `scripts/bootstrap_initial_duckdb_scenario.py` | 같은 원천 코드의 시나리오가 이미 있으면 그 활성 리비전을 공식버전으로 지정만 하거나, `--replace-existing` 이면 표시순서를 그 리비전에서 읽는다(:131-138). **새 원천 코드로 처음 적재할 때만** `load_reference_tables(args.workbook…)` 로 xlsb 를 Excel 로 읽는다(:139-140) | 새 원천 코드의 첫 적재는 사외에 돌릴 곳이 없다(`templates/` 도 Excel 도 없다). 같은 원천 코드가 이미 있을 때의 두 경로는 Excel 을 부르지 않는다 |
| Windows 전용 테스트 9개 — `tests/test_check_deploy_screens.py` 의 `skipif(sys.platform != "win32")` | Job Object·CTRL_BREAK·NTFS 대체 데이터 스트림·공유 위반·DB 자리의 폴더·대소문자를 가리지 않는 파일 시스템을 본다 | 4관문에서 건너뛴다(2장). 사내 Windows 의 4관문(런북 4-3)에서만 돈다 |
| `scripts/check_deploy_screens.py` 실행 | 깔린 Chrome 과 Playwright 가 있어야 한다(사내 런북 7장 도구) | `--list` 만 된다 |
| 화면 E2E(agent-browser·Claude in Chrome)·배포 메일 | 브라우저가 없다 | AppTest 로 확인하고, 실제 화면은 사용자가 포트 전달로 본다. 배포 메일은 사용자가 보낸다(5장) |
| `scripts/new_worktree.ps1`(병행 개발 작업 폴더) | PowerShell 전용이고, 기본 자리(저장소 옆 `../capa-<이름>`)가 샌드박스 쓰기 범위 밖이다 | 아직 정하지 않았다 — 데스크탑 안내서의 `claude -w <이름>`(저장소 안 `.claude/worktrees/`, 무시 목록에 있다)을 쓰거나, 사용자가 Claude 밖에서 저장소 옆에 만든다. 작업 폴더마다 `uv sync --frozen --python 3.10.11` 은 사용자가 친다 |

## 7. 서피스 개발 환경을 지우기 전에 — 사용자가 챙길 것

1장 머리의 결정대로 서피스 개발 환경을 지우면 아래 가운데 WSL·GitHub 에 없는 것은 사라진다.
`[x]` 는 10-13 에 옮겨 끝난 것이다. **서피스에서 지우지 않는 것** — 배포 받는 자리(sshd·`C:\Dev\update_publishing`·배포 전용 키
등록)와 메일을 보내는 Outlook 은 5장의 배포 길이라 남긴다. 접속 단말(Tailscale → SSH → tmux)도 그대로다.

- [x] **서피스 8501 앱의 DB** — WSL 의 두 DB 는 10-12 서피스 사본이다. 그 뒤 서피스 앱에서 저장한 시나리오·리비전·공식버전·설비는
  WSL 에 없다. 10-13 사용자 결정 — 합성 표본이라 끌지 않고 버린다(서피스에서 사용자가 지운다. WSL 에서는 서피스의 그 자리에 닿지 않는다).
- [ ] `templates/structure_template.xlsb`(Excel, git 밖) — 옮기지 않았다. 사외에서는 쓸 곳이 없어진다(6장).
- [ ] `data/temp/` 백업 DB, `data/output/` 옛 ZIP, `data/input/backup/`, 옛 배포 ZIP 출력 자리 `C:\Dev\Streamlit_Project_Dummyfile` —
  옮기지 않았다. 이제 ZIP 은 WSL `~/projects/Deploy/` 에 만든다(5장). 지난 배포 ZIP 의 내용은 태그에서 다시 만들 수
  있지만(그 태그와 뒤 태그를 지운 복제에서 `--no-tag`) 송장 시각과 줄끝이 달라 보낸 파일과 바이트는 같지 않다 — 보낸 그 파일은
  보낸 메일함의 첨부다. 남기려면 서피스에서 `C:\Dev\update_publishing` 에 넣어 두고 WSL 에서 `scp surface:<STAMP>.zip
  ~/projects/Deploy/`(샌드박스 밖)로 받는다. 10-13 에 `202610120655.zip`(3,651,419 바이트)을 이렇게 받아 두었다 — 송장 커밋
  `bfe9a10`, 이름 602개가 태그와 같고 545개는 바이트까지, 57개는 줄끝만 다르며 내용이 다른 파일은 없다.
- [ ] 옛 후보 브랜치 `cand/*`(서피스에 일곱 — 기능은 고친 꼴로 `main` 에 들어갔다) 가운데 푸시 안 된 것. GitHub 에 있는 것은 둘이다 —
  `cand/설비CSV내보내기/claude`(`f3d2698`, `main` 에 다 들어 있다)·`cand/설비UI개편/claude`(`25af5c5`, `main` 에 없는 커밋 17).
- [ ] 서피스 Claude 의 이 프로젝트 메모리 가운데 WSL 로 옮긴 묶음 뒤에 생기거나 바뀐 것 — WSL 메모리에 없으면 옮긴다.
- [x] 지난 사내 리뷰 13개와 버그 보고 2개 — 서피스 `C:\Dev\Review` → WSL `~/projects/Review/`(파일명 `<stamp>_review.md`, 저장소 밖).
  새 리뷰도 여기에 둔다.
- [x] stash `bigdataquery user_name`(사내 값 확인 뒤 반영하려던 BigDataQuery 사용자 이름 시험분) — 패치로
  `~/projects/stash/bigdataquery_user_name.patch`(저장소 밖). 서피스 stash 는 지울 때 함께 사라진다.
