# Purpose: 병행 개발용 작업 폴더를 브랜치·가상환경·격리 확인까지 한 번에 만든다.

<#
.SYNOPSIS
    `git worktree` 폴더 하나를 만들고 그 안에 제 `.venv` 를 붙인 뒤 격리를 확인한다.

.DESCRIPTION
    `AGENTS.md` 14-1 이 요구하는 전제를 손으로 갖추면 한 단계씩 빠뜨리기 쉽다. 특히
    **`.venv` 를 만들지 않고 넘어가면** 새 폴더가 조용히 main 의 가상환경을 쓰게 되는데,
    그때 `import capa_simulation` 은 main 의 `src/` 를 읽고 main 의 DuckDB 를 연다.
    검증 4종은 그 상태에서도 전부 초록이다.

    그래서 이 스크립트는 만들고 끝내지 않고 `scripts/check_worktree_isolation.py` 까지
    돌린다. 거기서 실패하면 폴더를 그대로 두고 0 이 아닌 값으로 끝난다 — 사람이 보고
    고치라는 뜻이다.

.PARAMETER Branch
    만들 후보 브랜치. 14-2 의 규약은 `cand/<과제>/<에이전트>` 다.

.PARAMETER Path
    작업 폴더 경로. 비우면 저장소 **옆**에 브랜치 마지막 조각 이름으로 만든다.

.PARAMETER Port
    이 폴더에서 앱을 띄울 포트. 안내에만 쓴다(8501 은 main 자리다).

.EXAMPLE
    .\scripts\new_worktree.ps1 -Branch cand/home-legend/claude -Port 8502
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Branch,

    [string]$Path,

    [int]$Port = 8502
)

$ErrorActionPreference = "Stop"

$repo = (git rev-parse --show-toplevel)
if (-not $repo) { throw "git 저장소 안에서 실행하세요." }
$repo = $repo -replace "/", "\"

# 저장소 **안**에 만들면 `git ls-files` 와 배포 세트가 남의 작업 폴더까지 빨아들인다.
if (-not $Path) {
    $leaf = ($Branch -split "/")[-1]
    $Path = Join-Path (Split-Path $repo -Parent) "capa-$leaf"
}
if (Test-Path $Path) { throw "이미 있습니다: $Path" }

Write-Host "저장소   : $repo"
Write-Host "작업 폴더: $Path"
Write-Host "브랜치   : $Branch"
Write-Host ""

# main 을 기준으로 딴다. 지금 체크아웃된 것이 무엇이든 후보는 정본에서 출발해야 한다.
git worktree add -b $Branch $Path main
if ($LASTEXITCODE -ne 0) { throw "worktree 생성 실패" }

Push-Location $Path
try {
    Write-Host ""
    Write-Host "가상환경을 만듭니다 (uv sync) — 몇 분 걸립니다."
    uv sync
    if ($LASTEXITCODE -ne 0) { throw "uv sync 실패" }

    Write-Host ""
    & (Join-Path $Path ".venv\Scripts\python.exe") (Join-Path $Path "scripts\check_worktree_isolation.py")
    $isolated = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($isolated -ne 0) {
    Write-Host ""
    Write-Host "격리 확인에 실패했습니다. 폴더는 지우지 않았습니다 — 위 내용을 보고 고치세요."
    exit $isolated
}

Write-Host ""
Write-Host "준비됐습니다. 이 폴더에서만 일하세요 (AGENTS 14-1)."
Write-Host "  cd $Path"
Write-Host "  .\.venv\Scripts\python.exe -m streamlit run app.py --server.port $Port"
Write-Host ""
Write-Host "지울 때는 main 폴더에서:"
Write-Host "  git worktree remove $Path"
Write-Host "  git branch -D $Branch   # 채택하지 않았을 때만"
