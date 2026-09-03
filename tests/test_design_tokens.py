# Purpose: 색·서체가 design/tokens.py 밖으로 새지 않는지 검사한다.

import re
from pathlib import Path

from capa_simulation.design import tokens

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOKENS_FILE = PROJECT_ROOT / "src" / "capa_simulation" / "design" / "tokens.py"
SCANNED_DIRECTORIES = ("app_pages", "src")
HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}\b")
# Windows 전용 서체를 폴백 없이 단독 지정하면 다른 OS 에서 서체와 컬럼 폭이 함께 깨진다.
BARE_WINDOWS_FONT = re.compile(r"""["']Malgun Gothic["']""")


def _scanned_files() -> list[Path]:
    files = [PROJECT_ROOT / "app.py"]
    for directory in SCANNED_DIRECTORIES:
        files.extend(
            path
            for path in (PROJECT_ROOT / directory).rglob("*.py")
            if path.resolve() != TOKENS_FILE.resolve()
        )
    return sorted(set(files))


def test_color_literals_live_only_in_the_token_module() -> None:
    """색을 화면 코드에 직접 쓰면 config.toml 과 조용히 갈라진다."""
    offenders: list[str] = []
    for path in _scanned_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in HEX_COLOR.finditer(line):
                relative = path.relative_to(PROJECT_ROOT).as_posix()
                offenders.append(f"{relative}:{number}: {match.group(0)}")

    assert not offenders, (
        "색은 design/tokens.py 에만 둔다. 역할 이름의 토큰을 만들어 참조하라:\n"
        + "\n".join(offenders)
    )


def test_windows_only_font_is_never_declared_without_a_fallback() -> None:
    offenders: list[str] = []
    for path in _scanned_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if BARE_WINDOWS_FONT.search(line):
                offenders.append(f"{path.relative_to(PROJECT_ROOT).as_posix()}:{number}")

    assert not offenders, (
        "서체는 tokens.FONT_FAMILY 를 쓴다. 폴백 없는 단독 지정 위치:\n" + "\n".join(offenders)
    )


def test_status_colors_keep_a_monotonic_severity_order() -> None:
    """확보 → 경고 → 부족 순으로 어두워져야 흑백·색각이상에서 순서가 읽힌다."""

    def relative_luminance(color: str) -> float:
        channels = [int(color.lstrip("#")[index : index + 2], 16) / 255 for index in (0, 2, 4)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    secure = relative_luminance(tokens.STATUS_SECURE)
    warning = relative_luminance(tokens.STATUS_WARNING)
    shortage = relative_luminance(tokens.STATUS_SHORTAGE)

    assert secure > warning > shortage


def test_every_equipment_status_has_its_own_color() -> None:
    """색이 모자라면 Altair 가 팔레트를 순환해 다른 상태가 같은 색으로 그려진다."""
    from capa_simulation.services.equipment_contract import EQUIPMENT_STATUSES

    assert tuple(tokens.EQUIPMENT_STAGE_COLORS) == EQUIPMENT_STATUSES
    assert len(set(tokens.EQUIPMENT_STAGE_COLORS.values())) == len(EQUIPMENT_STATUSES)
