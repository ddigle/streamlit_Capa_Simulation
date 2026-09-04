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


# `[theme]` 가 선언한 색과 1:1 로 대응하는 토큰. 두 곳이 갈라지면 Streamlit 위젯과
# Plotly 표가 서로 다른 회색을 쓰게 되는데, 나란히 놓기 전에는 눈에 띄지 않는다.
CONFIG_COLOR_TOKENS = {
    "primaryColor": "ACCENT",
    "backgroundColor": "SURFACE_PAGE",
    "secondaryBackgroundColor": "SURFACE",
    "textColor": "TEXT",
    "borderColor": "BORDER",
    "grayColor": "TEXT_MUTED",
    "dataframeBorderColor": "BORDER",
    "dataframeHeaderBackgroundColor": "HEADER_BACKGROUND",
}

CONFIG_FILE = PROJECT_ROOT / ".streamlit" / "config.toml"


def _theme_colors() -> dict[str, str]:
    """`config.toml` 의 최상위 `[theme]` 블록에서 색 항목만 읽는다.

    `tomllib` 은 3.11 부터라 이 저장소의 3.10 에서는 못 쓰고, `tomli` 는 requirements 에
    없는 전이 의존이라 기대면 안 된다. 필요한 것은 `키 = "#RRGGBB"` 한 줄뿐이다.
    """
    colors: dict[str, str] = {}
    in_theme = False
    for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            # `[theme.sidebar]` 는 사이드바 전용 하위 팔레트라 본문 토큰과 다르다.
            in_theme = stripped == "[theme]"
            continue
        if not in_theme or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        match = HEX_COLOR.fullmatch(value.strip().strip('"'))
        if match:
            colors[key.strip()] = match.group(0)
    return colors


def test_tokens_match_the_theme_declared_in_config() -> None:
    """토큰 값의 근거는 `config.toml` 이다. 한쪽만 바꾸면 화면이 조용히 갈라진다."""
    theme = _theme_colors()
    mismatches = [
        f"{key}={theme[key]} vs tokens.{name}={getattr(tokens, name)}"
        for key, name in CONFIG_COLOR_TOKENS.items()
        if key in theme and theme[key].upper() != getattr(tokens, name).upper()
    ]

    assert not mismatches, "config.toml 과 tokens.py 가 갈라졌습니다:\n" + "\n".join(mismatches)


def test_every_mapped_theme_key_exists_in_config() -> None:
    """대응표가 낡으면 검사가 조용히 통과한다. 키 자체가 남아 있는지도 본다."""
    theme = _theme_colors()

    assert not [key for key in CONFIG_COLOR_TOKENS if key not in theme]
