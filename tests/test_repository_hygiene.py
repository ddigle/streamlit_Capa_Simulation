# Purpose: 저장소에 이유 없이 떠도는 파일과 실재하지 않는 문서 참조가 생기지 않게 막는다.

"""파일 구조 위생.

사내·사외 두 에이전트가 같은 저장소를 번갈아 읽는다. 한쪽이 지운 파일의 이름이 문서에
남거나, 아무도 쓰지 않는 모듈이 굴러다니면 **읽는 쪽이 그것을 찾아 헤맨다.** 사내는 쓸 수
있는 양이 적어 그 탐색이 곧 손실이고, 끝내 「이 파일이 안 보인다」가 리뷰에 적힌다.

이 검사들을 별도 감사 스크립트로 두지 않은 이유는 하나다 — **강제되지 않는 감사는 돌지
않는다.** 여기 있으면 검증 4종에 실려 매번 돈다.

여기 담는 것은 **판정이 명확한 것**뿐이다. 「이 문서가 아직 유효한가」처럼 사람이 봐야
하는 것은 검사로 만들지 않고 배포 송장의 추세 수치로 넘긴다.
"""

import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 최상위에 있어도 되는 것. 새 항목이 늘면 이 목록을 함께 고치며 「왜 필요한가」를 정한다.
# 목록을 손대지 않고 파일만 늘어나는 것이 곧 떠도는 파일이다.
ALLOWED_TOP_LEVEL = {
    # `docker/Dockerfile-prod` 의 `COPY . /project/` 가 빌드 컨텍스트를 통째로 담는다.
    # 실데이터·비밀값·`.venv` 가 이미지에 실리는 것을 막는 자리라 `docker/` 안이 아니라
    # 최상위에 있어야 한다 — Docker 는 컨텍스트 뿌리에서만 이 파일을 읽는다.
    ".dockerignore",
    ".gitattributes",
    # 사외 전용 CI. 배포 세트가 `git ls-files` 전부라 사내 ZIP 에도 실리는데, 워크플로 안의
    # `if: github.repository == ...` 가 사내에서 스스로 꺼진다(`.github/workflows/ci.yml`).
    ".github/",
    ".gitignore",
    ".streamlit/",
    "AGENTS.md",
    "CLAUDE.md",
    "HANDOFF.md",
    "README.md",
    "app.py",
    "app_pages/",
    "config/",
    # 사내 GitHub Pages 로 띄우는 발표 자료(중간 보고 덱). 이미지까지 한 파일에 담은
    # 단독 문서라 브라우저로 바로 열린다. 2026-09-20 사용자 결정으로 배포 세트에 포함한다.
    "index.html",
    "data/",
    # 사내 WebIDE 의 CI/CD 가 읽는 이미지 정의. 이 폴더가 없어 Docker Build 단계에서
    # 파이프라인이 실패했다(2026-09-23 사내 확인). 배포 세트에 반드시 실려야 한다.
    "docker/",
    "docs/",
    "pyproject.toml",
    "pyrightconfig.json",
    # `uv.lock` 에서 뽑은 그림자. 컨테이너가 `uv` 없이 설치할 수 있는 유일한 길이다.
    # `tests/test_requirements_export.py` 가 락과의 어긋남을 막는다.
    "requirements.txt",
    "requirements-company.txt",
    "scripts/",
    "src/",
    # Streamlit 정적 서빙(`.streamlit/config.toml` `enableStaticServing`)은 `app.py` 옆의 `static/`
    # 만 `app/static/…` 으로 보낸다. 페이지 제목·상자 제목·큰 숫자의 Archivo 부분 글꼴
    # (`static/fonts/`)이 여기 있다 — 사내 PC 는 외부 글꼴 서버(Google Fonts)에 못 나간다.
    "static/",
    "tests/",
    "uv.lock",
}

# **사내에만 생기는 최상위 항목.** 있어도 되고 없어도 된다. 사외에는 둘 다 없지만, 사내에서는
# 배포 적용기가 `.deploy/applied.json` 을 쓰고 리뷰 문서가 `review/` 에 쌓여 추적으로 올라간다.
# 위 필수 목록에 넣으면 사외에서 「선언에는 있는데 없다」로 깨지고, 아무 데도 안 적으면
# **사내에서만** 「선언되지 않은 항목」으로 깨진다 — 사내는 그것을 진짜 결함으로 보아 리뷰에
# 적고 사외에서는 재현되지 않는다. 이 저장소가 없애려는 바로 그 실패 유형이라 따로 둔다.
INTERNAL_ONLY_TOP_LEVEL = {".deploy/", "review/"}


def _tracked(pattern: str = "") -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", *([pattern] if pattern else [])],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def test_agents_does_not_name_modules_that_no_longer_exist() -> None:
    """`AGENTS.md` 3장이 **없는 파일**을 가리키지 않는다.

    `test_documentation_inventory` 는 「모듈이 문서에 있나」 한 방향만 본다. 반대가 비어
    있었다 — 파일을 지웠는데 이름이 문서에 남으면 읽는 쪽이 없는 파일을 찾는다. 사내에서
    그 탐색은 되돌려 받을 수 없는 비용이다.
    """
    agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    section = agents.split("## 3. 파일별 책임", 1)[-1].split("\n## 4.", 1)[0]
    mentioned = sorted(set(re.findall(r"`([\w./-]+\.py)`", section)))

    tracked = set(_tracked("*.py"))
    basenames = {Path(path).name for path in tracked}
    # 등재는 전체 경로·줄인 표기·파일명 어느 쪽이어도 된다(정방향 검사와 같은 규칙).
    stale = [
        name
        for name in mentioned
        if name not in tracked
        and Path(name).name not in basenames
        and not any(path.endswith("/" + name) for path in tracked)
    ]

    assert not stale, (
        "AGENTS.md 3장이 실재하지 않는 파일을 가리킵니다. 파일을 지우거나 옮겼으면 같은 "
        "변경에서 문서도 고칩니다:\n" + "\n".join(stale)
    )


def test_no_source_module_is_left_unreferenced() -> None:
    """`src/` 에 아무도 쓰지 않는 모듈을 남기지 않는다.

    읽는 쪽은 그것이 살아 있는 코드인지 알 수 없어 일단 읽는다. 지울 것은 지워야 한다.
    """
    py_files = _tracked("*.py")
    sources = {path: (PROJECT_ROOT / path).read_text(encoding="utf-8") for path in py_files}

    orphans = []
    for path in py_files:
        if not path.startswith("src/capa_simulation/") or path.endswith("__init__.py"):
            continue
        dotted = path[len("src/") :].removesuffix(".py").replace("/", ".")
        module = Path(path).stem
        referenced = any(
            other != path and (dotted in text or f"import {module}" in text or f"{module}." in text)
            for other, text in sources.items()
        )
        if not referenced:
            orphans.append(path)

    assert not orphans, (
        "어디서도 쓰이지 않는 모듈이 있습니다. 쓰이는 곳이 생길 때까지 두지 말고 "
        "지우거나, 쓰는 곳을 같은 변경에서 만듭니다:\n" + "\n".join(orphans)
    )


def test_every_page_file_is_declared_in_navigation() -> None:
    """`app_pages/` 의 화면은 모두 `navigation` 에 등록돼 있다.

    전수 렌더 검사(`tests/test_all_pages_render.py`)는 목록을 `ALL_SPECS` 에서 받는다. 그래서
    **등록되지 않은 페이지는 애초에 검사 대상이 아니다** — 열리지 않는 화면이 아무 신호 없이
    저장소에 남고, 배포 ZIP 에는 실려 사내로 간다. 읽는 쪽은 그것이 살아 있는 화면인 줄 알고
    읽는다. 등록과 파일을 여기서 맞춰 둔다.

    반대 방향(선언에는 있는데 파일이 없다)도 같이 본다. 그쪽은 앱이 시작조차 못 한다.
    """
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from capa_simulation.navigation import ALL_SPECS

    declared = {spec.path for spec in ALL_SPECS}
    present = {path for path in _tracked("app_pages/*.py") if not path.endswith("__init__.py")}

    unregistered = sorted(present - declared)
    missing = sorted(declared - present)

    assert not unregistered, (
        "`navigation.py` 에 등록되지 않은 화면입니다. 사이드바에 올리거나 지웁니다 — "
        "둘 다 아니면 열 수 없는 화면이 배포본에 실립니다:\n" + "\n".join(unregistered)
    )
    assert not missing, (
        "선언에는 있는데 파일이 없습니다. 이 상태로는 앱이 시작하지 못합니다:\n"
        + "\n".join(missing)
    )


def test_the_top_level_stays_the_declared_set() -> None:
    """최상위에 정체불명 파일이 늘지 않는다.

    떠도는 파일은 대개 여기서 시작한다 — 임시 스크립트, 받아 둔 산출물, 실험 폴더.
    새 항목이 필요하면 위 목록을 함께 고치며 「왜 필요한가」를 정한다.
    """
    top = {path.split("/")[0] + ("/" if "/" in path else "") for path in _tracked()}

    unexpected = sorted(top - ALLOWED_TOP_LEVEL - INTERNAL_ONLY_TOP_LEVEL)
    vanished = sorted(ALLOWED_TOP_LEVEL - top)

    assert not unexpected, (
        "최상위에 선언되지 않은 항목이 있습니다. 정말 필요하면 "
        f"`ALLOWED_TOP_LEVEL` 에 함께 적습니다:\n{unexpected}"
    )
    assert not vanished, f"선언에는 있는데 저장소에 없는 항목입니다. 목록에서 지우세요:\n{vanished}"


def test_every_docs_file_is_reachable_from_somewhere() -> None:
    """`docs/` 의 문서는 어디선가 가리켜져야 한다.

    아무도 가리키지 않는 문서는 읽히지 않으면서 낡고, 낡은 채로 남아 읽는 쪽을 오도한다.
    """
    tracked = _tracked()
    texts = {
        path: (PROJECT_ROOT / path).read_text(encoding="utf-8", errors="ignore") for path in tracked
    }

    unlinked = [
        path
        for path in tracked
        if path.startswith("docs/")
        and path.endswith(".md")
        and not any(
            other != path and (path in text or Path(path).name in text)
            for other, text in texts.items()
        )
    ]

    assert not unlinked, (
        "어디서도 가리켜지지 않는 문서입니다. 진입점(`CLAUDE.md`·`README.md`·`AGENTS.md`)"
        " 에서 링크하거나 지웁니다:\n" + "\n".join(unlinked)
    )
