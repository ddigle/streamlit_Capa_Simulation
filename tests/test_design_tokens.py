# Purpose: 색·서체가 design/tokens.py 밖으로 새지 않는지 검사한다.

import re
from pathlib import Path

from capa_simulation.design import tokens

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOKENS_FILE = PROJECT_ROOT / "src" / "capa_simulation" / "design" / "tokens.py"
SCANNED_DIRECTORIES = ("app_pages", "src")
HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}\b")
# 투명·히트 타깃처럼 rgba 로만 적히는 값도 tokens 밖에 두면 같은 값이 여러 곳에 흩어진다.
RGB_COLOR = re.compile(r"\brgba?\(")
COLOR_LITERALS = (HEX_COLOR, RGB_COLOR)
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
            for pattern in COLOR_LITERALS:
                for match in pattern.finditer(line):
                    relative = path.relative_to(PROJECT_ROOT).as_posix()
                    offenders.append(f"{relative}:{number}: {match.group(0)}")

    assert not offenders, (
        "색은 design/tokens.py 에만 둔다. 역할 이름의 토큰을 만들어 참조하라"
        "(투명·히트 타깃은 tokens.TRANSPARENT·tokens.HIT_TARGET):\n" + "\n".join(offenders)
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


def _theme_colors(section: str = "[theme]") -> dict[str, str]:
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
            in_theme = stripped == section
            continue
        if not in_theme or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        match = HEX_COLOR.fullmatch(value.strip().strip('"'))
        if match:
            colors[key.strip()] = match.group(0)
    return colors


def _theme_string(key: str) -> str | None:
    """`[theme]` 블록에서 문자열 한 항목을 읽는다. 없으면 None."""
    in_theme = False
    for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_theme = stripped == "[theme]"
            continue
        if not in_theme or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if name.strip() == key:
            return value.strip().strip('"')
    return None


def test_heading_font_matches_the_token_stack() -> None:
    """제목 서체가 `tokens.FONT_FAMILY` 와 갈라지면 한글만 폴백 face 로 넘어간다.

    폴백 face 는 같은 줄상자 안에서 잉크 상단 위치가 라틴과 달라, 영어 제목 페이지와
    한글 제목 페이지의 제목·헤더 간격이 서로 다르게 보인다. 두 선언을 한 값으로 묶는다.
    """
    declared = _theme_string("headingFont")

    assert declared == tokens.FONT_FAMILY, (
        "config.toml 의 headingFont 와 tokens.FONT_FAMILY 가 갈라졌습니다:\n"
        f"headingFont={declared}\ntokens.FONT_FAMILY={tokens.FONT_FAMILY}"
    )


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


# ------------------------------------------------------------------- 어두운 테마
# Streamlit 이 그리는 것(위젯·사이드바·알림)은 `config.toml` 의 `[theme.dark]` 를 보고,
# 우리 Figure 는 `tokens` 를 본다. 둘이 갈라지면 한 화면 안에서 **위젯만 밝고 그림만
# 어두운** 상태가 된다. 밝은 쪽과 같은 대조를 어두운 쪽에도 건다.


def _in_dark(name: str) -> str:
    from capa_simulation.design import theme as theme_module

    previous = theme_module.current_mode()
    theme_module._LOCAL.mode = "dark"
    try:
        return str(getattr(tokens, name))
    finally:
        theme_module._LOCAL.mode = previous


def test_dark_tokens_match_the_dark_theme_declared_in_config() -> None:
    declared = _theme_colors("[theme.dark]")
    mismatches = [
        f"{key}={declared[key]} vs 다크 tokens.{name}={_in_dark(name)}"
        for key, name in CONFIG_COLOR_TOKENS.items()
        if key in declared and declared[key].upper() != _in_dark(name).upper()
    ]

    assert not mismatches, "config.toml [theme.dark] 와 다크 팔레트가 갈라졌습니다:\n" + "\n".join(
        mismatches
    )


def test_the_dark_theme_block_covers_the_same_keys() -> None:
    """한쪽에만 있는 키는 그 테마에서만 Streamlit 기본값으로 떨어져 조용히 어긋난다."""
    light = set(_theme_colors("[theme]"))
    dark = set(_theme_colors("[theme.dark]"))

    assert not light - dark, f"어두운 테마에 없는 키: {sorted(light - dark)}"


def test_both_palettes_declare_exactly_the_same_names() -> None:
    """이름이 한쪽에만 있으면 그 테마에서 `AttributeError` 로 화면이 그 자리에서 죽는다."""
    light = set(tokens._LIGHT)
    dark = set(tokens._DARK)

    assert light == dark, f"다크에만: {sorted(dark - light)}\n라이트에만: {sorted(light - dark)}"


def test_every_token_resolves_in_both_themes() -> None:
    """선언만 있고 값이 없는 이름을 잡는다 — `TYPE_CHECKING` 블록은 실행되지 않는다."""
    from capa_simulation.design import theme as theme_module

    declared = [name for name in dir(tokens) if name.isupper() and not name.startswith("_")]
    assert declared, "토큰 이름을 하나도 찾지 못했습니다."

    missing: list[str] = []
    for mode in ("light", "dark"):
        theme_module._LOCAL.mode = mode
        for name in declared:
            try:
                getattr(tokens, name)
            except AttributeError:
                missing.append(f"{mode}.{name}")
    theme_module._LOCAL.mode = "light"

    assert not missing, "테마에서 해석되지 않는 토큰:\n" + "\n".join(missing)


def test_the_surface_stack_flips_direction_in_the_dark_theme() -> None:
    """어두운 바탕에서는 **위로 올라온 면이 밝다.**

    같은 방향을 유지하면 합계 행이 배경에 가라앉는다. 이 뒤집힘이 다크 팔레트에서 가장
    틀리기 쉬운 자리라 방향 자체를 고정한다.
    """
    from capa_simulation.design import theme as theme_module

    steps = ("SURFACE_PRODUCT_TOTAL", "SURFACE_PRODUCTION_TOTAL", "SURFACE_GRAND_TOTAL")

    def luminance(value: str) -> float:
        def channel(raw: int) -> float:
            c = raw / 255
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        red, green, blue = (channel(int(value[i : i + 2], 16)) for i in (1, 3, 5))
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    light = [luminance(getattr(tokens, name)) for name in steps]
    assert light[0] > light[1] > light[2], f"밝은 테마에서 어두워지지 않습니다: {light}"

    theme_module._LOCAL.mode = "dark"
    try:
        dark = [luminance(getattr(tokens, name)) for name in steps]
    finally:
        theme_module._LOCAL.mode = "light"
    assert dark[0] < dark[1] < dark[2], f"어두운 테마에서 밝아지지 않습니다: {dark}"
