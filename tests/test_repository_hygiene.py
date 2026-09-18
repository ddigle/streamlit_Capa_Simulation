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
    ".gitattributes",
    ".gitignore",
    ".streamlit/",
    "AGENTS.md",
    "CLAUDE.md",
    "HANDOFF.md",
    "README.md",
    "app.py",
    "app_pages/",
    "config/",
    "data/",
    "docs/",
    "pyproject.toml",
    "pyrightconfig.json",
    "requirements-company.txt",
    "scripts/",
    "src/",
    "tests/",
    "uv.lock",
}


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


def test_the_top_level_stays_the_declared_set() -> None:
    """최상위에 정체불명 파일이 늘지 않는다.

    떠도는 파일은 대개 여기서 시작한다 — 임시 스크립트, 받아 둔 산출물, 실험 폴더.
    새 항목이 필요하면 위 목록을 함께 고치며 「왜 필요한가」를 정한다.
    """
    top = {path.split("/")[0] + ("/" if "/" in path else "") for path in _tracked()}

    unexpected = sorted(top - ALLOWED_TOP_LEVEL)
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
