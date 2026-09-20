# Purpose: 색 토큰을 모듈 로드 시점에 붙잡아 테마 전환이 먹지 않는 자리를 막는다.

"""**색은 실행마다 조회해야 한다.**

`design/tokens.py` 는 모듈 `__getattr__` 로 그때의 팔레트를 본다. 그런데 소비하는 쪽이
모듈 최상위에서

    CANVAS_COLOR = tokens.CHART_CANVAS

처럼 받아 두면 **프로세스가 그 모듈을 처음 읽은 순간의 테마로 굳는다.** Streamlit 은
파이썬 프로세스를 유지하므로 사용자가 테마를 바꿔도 그 값만 옛 색으로 남는다. 실제로
그렇게 됐다 — 다크 테마에서 월별 표의 배경이 흰색인 채로 글자만 밝은 회색이 되어 읽을 수
없었고, 헤더 띠도 밝은 테마 색 그대로였다.

**예외가 나지 않는 종류의 고장이라 검사로만 잡힌다.** 화면은 멀쩡히 뜨고 색만 틀린다.

치수(px)는 두 팔레트가 같으므로 붙잡아도 무해하다. 이 검사는 **두 팔레트에서 값이 다른
이름**만 본다 — 팔레트가 갈라지는 순간 자동으로 대상이 되고, 목록을 따로 관리하지 않는다.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capa_simulation.design import tokens  # noqa: E402

# 모듈 로드 때 컴포넌트 자체를 등록하는 자리. `st.components.v2.component` 는 CSS 를 등록
# 시점에 굳히므로 실행마다 다시 만들 수 없다. 스크롤바 손잡이 한 색이라 화면을 못 읽게
# 하지는 않는다 — 여기 남겨 두어 **잊히지 않게** 한다. 고칠 때 이 줄을 지운다.
KNOWN_FROZEN = {
    ("src/capa_simulation/components/horizontal_scrollbar.py", "_SCROLLBAR_CSS"),
}


def _theme_dependent_tokens() -> set[str]:
    """두 팔레트에서 값이 다른 토큰 이름.

    팔레트를 직접 읽는다 — 목록을 손으로 관리하면 팔레트가 갈라질 때 검사가 따라오지
    못한다. 두 팔레트가 같은 키를 갖는 것은 `test_design_tokens.py` 가 따로 지킨다.
    """
    light = tokens._PALETTES["light"]
    dark = tokens._PALETTES["dark"]
    return {name for name in light if name in dark and light[name] != dark[name]}


def _assigned_name(node: ast.Assign | ast.AnnAssign) -> str:
    """대입 대상의 이름. 튜플 대입이나 속성 대입이면 이름이 없으므로 `?` 로 둔다."""
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    first = targets[0] if targets else None
    return first.id if isinstance(first, ast.Name) else "?"


def _scanned_files() -> list[Path]:
    paths = sorted((PROJECT_ROOT / "src").rglob("*.py"))
    paths += sorted((PROJECT_ROOT / "app_pages").glob("*.py"))
    paths.append(PROJECT_ROOT / "app.py")
    return [path for path in paths if path.name != "tokens.py"]


def test_no_module_level_capture_of_theme_dependent_colors() -> None:
    theme_dependent = _theme_dependent_tokens()
    assert theme_dependent, "두 팔레트가 완전히 같다 — 이 검사가 무의미해졌다"

    offenders: list[str] = []
    for path in _scanned_files():
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:  # 모듈 최상위만 본다. 함수 안은 실행마다 도므로 안전하다.
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            if node.value is None:
                continue
            target = _assigned_name(node)
            if (relative, target) in KNOWN_FROZEN:
                continue
            for sub in ast.walk(node.value):
                if (
                    isinstance(sub, ast.Attribute)
                    and isinstance(sub.value, ast.Name)
                    and sub.value.id == "tokens"
                    and sub.attr in theme_dependent
                ):
                    offenders.append(f"{relative}:{node.lineno}  {target} = tokens.{sub.attr}")
                    break

    assert not offenders, (
        "색을 모듈 로드 시점에 붙잡았습니다. 테마를 바꿔도 이 값만 따라오지 않습니다 — "
        "함수 안으로 옮겨 실행마다 조회하세요:\n  " + "\n  ".join(offenders)
    )
