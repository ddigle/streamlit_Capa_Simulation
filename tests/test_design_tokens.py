# Purpose: 색·서체가 design/tokens.py 밖으로 새지 않는지 검사한다.

import math
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


# ----------------------------------------------------------------------- 색 계산
# 상태색 검사에만 쓰는 최소 색 계산. `tokens.STATUS_*` 를 읽으면 **밝은 팔레트만** 검사하게
# 된다 — 모듈 `__getattr__` 이 실행 중인 테마를 보는데, 테스트는 Streamlit 밖이라 늘
# `light` 로 떨어진다. 그래서 아래 검사들은 `_PALETTES` 를 직접 돌며 두 팔레트를 다 본다.
# 실제로 어두운 팔레트의 상태색 셋이 서로 구분되지 않게 망가진 적이 있는데, 그때 이
# 파일의 검사는 전부 초록이었다.


def _linear(color: str) -> list[float]:
    channels = [int(color.lstrip("#")[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]


def relative_luminance(color: str) -> float:
    red, green, blue = _linear(color)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(one: str, other: str) -> float:
    high, low = sorted((relative_luminance(one), relative_luminance(other)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _oklab(linear: list[float]) -> tuple[float, float, float]:
    red, green, blue = linear

    def cube(value: float) -> float:
        return float(value ** (1 / 3) if value >= 0 else -((-value) ** (1 / 3)))

    long = cube(0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue)
    medium = cube(0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue)
    short = cube(0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue)
    return (
        0.2104542553 * long + 0.7936177850 * medium - 0.0040720468 * short,
        1.9779984951 * long - 2.4285922050 * medium + 0.4505937099 * short,
        0.0259040371 * long + 0.7827717662 * medium - 0.8086757660 * short,
    )


# Machado, Oliveira & Fernandes (2009) 의 색각이상 변환(선형 RGB, 강도 1.0).
CVD_MATRICES = {
    "protan": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deutan": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
}


def _delta_e(one: str, other: str, vision: str | None = None) -> float:
    """OKLab 유클리드 거리 ×100. `vision` 이 없으면 정상 시야."""

    def prepare(color: str) -> list[float]:
        linear = _linear(color)
        if vision is None:
            return linear
        matrix = CVD_MATRICES[vision]
        return [
            min(1.0, max(0.0, sum(m * c for m, c in zip(row, linear, strict=True))))
            for row in matrix
        ]

    first, second = _oklab(prepare(one)), _oklab(prepare(other))
    return 100 * math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second, strict=True)))


def _bullets(lines: list[str]) -> str:
    """실패 목록을 줄바꿈 + 들여쓰기로 이어 붙인다."""
    return "".join("\n  " + line for line in lines)


STATUS_NAMES = ("STATUS_SECURE", "STATUS_WARNING", "STATUS_SHORTAGE")
# `scripts/validate_palette.js`(dataviz) 의 문턱을 그대로 쓴다.
CVD_TARGET = 8.0  # 색각이상(protan·deutan 중 나쁜 쪽) OKLab ΔE
NORMAL_FLOOR = 15.0  # 정상 시야 OKLab ΔE. 이 아래면 색을 다 보는 사람도 못 가른다
TEXT_ON_FILL_MINIMUM = 4.5  # 칸을 채운 색 위의 숫자


def test_status_colors_keep_a_monotonic_severity_order() -> None:
    """확보 → 경고 → 부족 순으로 어두워져야 흑백·색각이상에서 순서가 읽힌다.

    **두 팔레트를 다 본다.** 어두운 팔레트는 밝은 쪽을 그대로 어둡게 옮긴 것이 아니라
    따로 고른 값이라, 여기서 안 보면 순서가 뒤집혀도 아무도 모른다.
    """
    for mode, palette in tokens._PALETTES.items():
        secure, warning, shortage = (relative_luminance(palette[name]) for name in STATUS_NAMES)
        assert secure > warning > shortage, (
            f"{mode} 팔레트의 상태색 휘도가 단조 감소하지 않습니다: "
            f"확보 {secure:.3f} · 경고 {warning:.3f} · 부족 {shortage:.3f}"
        )


def test_status_colors_stay_apart_for_colorblind_readers() -> None:
    """상태색 셋은 **서로** 떨어져야 한다 — 히트맵이 셋을 나란히 놓고 읽게 한다.

    휘도 대비(WCAG)로는 잡히지 않는다. 회색·주황·자주는 색상이 분리를 떠받치므로 휘도비는
    1.2:1 이어도 멀쩡히 구분되고, 반대로 휘도비가 멀어도 색각이상에서 붙을 수 있다.
    잣대는 OKLab ΔE 이고, 눈이 아니라 계산으로 본다.
    """
    failures: list[str] = []
    for mode, palette in tokens._PALETTES.items():
        colors = [palette[name] for name in STATUS_NAMES]
        for i in range(len(colors)):
            for j in range(i + 1, len(colors)):
                one, other = colors[i], colors[j]
                label = f"{mode} {STATUS_NAMES[i]}↔{STATUS_NAMES[j]}"
                cvd = min(_delta_e(one, other, vision) for vision in CVD_MATRICES)
                normal = _delta_e(one, other)
                if cvd < CVD_TARGET:
                    failures.append(f"{label}: 색각이상 ΔE {cvd:.1f} < {CVD_TARGET}")
                if normal < NORMAL_FLOOR:
                    failures.append(f"{label}: 정상시야 ΔE {normal:.1f} < {NORMAL_FLOOR}")
    assert not failures, "상태색이 서로 구분되지 않습니다:" + _bullets(failures)


def test_status_fills_carry_readable_numbers() -> None:
    """상태색은 칸을 채우고 그 위에 `TEXT` 가 얹힌다. 그 대비가 색 선택의 상한이다."""
    failures: list[str] = []
    for mode, palette in tokens._PALETTES.items():
        for name in STATUS_NAMES:
            ratio = contrast_ratio(palette["TEXT"], palette[name])
            if ratio < TEXT_ON_FILL_MINIMUM:
                failures.append(f"{mode} {name} {palette[name]} 위의 글자 {ratio:.2f}:1")
    assert not failures, f"칸 위 숫자가 {TEXT_ON_FILL_MINIMUM}:1 에 못 미칩니다:" + _bullets(
        failures
    )


# 선행 입고 실적 글자가 서는 월 칸 면. 연간 Total 칸에는 적지 않는다.
MONTH_CELL_SURFACES = ("SURFACE", "SURFACE_SUBTLE", "SURFACE_PAST", "SURFACE_PAST_SUBTLE")
SMALL_TEXT_MINIMUM = 4.5  # 12px 글자


def test_the_advance_shipment_note_reads_on_every_month_cell_and_apart_from_deltas() -> None:
    """Density 칸 오른쪽 위 선행 입고 실적 글자는 같은 띠의 선행 B/O 증감(`DELTA_*`)과 갈려야 한다.

    바탕은 흰 면·줄무늬·과거 구간 둘 — 그 모두에서 12px 글자 기준 4.5:1 을 넘어야 한다.
    """
    failures: list[str] = []
    for mode, palette in tokens._PALETTES.items():
        color = palette["ADVANCE_SHIPMENT_TEXT"]
        for surface in MONTH_CELL_SURFACES:
            ratio = contrast_ratio(color, palette[surface])
            if ratio < SMALL_TEXT_MINIMUM:
                failures.append(f"{mode} {surface} 위 {ratio:.2f}:1")
        for delta in ("DELTA_INCREASE", "DELTA_DECREASE"):
            normal = _delta_e(color, palette[delta])
            if normal < NORMAL_FLOOR:
                failures.append(f"{mode} {delta} 와 정상시야 ΔE {normal:.1f}")
            worst = min(_delta_e(color, palette[delta], vision) for vision in CVD_MATRICES)
            if worst < CVD_TARGET:
                failures.append(f"{mode} {delta} 와 색각이상 ΔE {worst:.1f}")
    assert not failures, "선행 입고 실적 글자색이 맞지 않습니다:" + _bullets(failures)


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


def test_space_mark_text_colours_read_on_every_space_surface() -> None:
    """도면 요소 이름표의 「글자 색」은 SURFACE 테두리를 두르고 캔버스·층 블록 면 위에 선다. 두 테마
    모두 그 면 위에서 4.5:1 이상이어야 읽힌다(영역 면색을 그대로 쓰면 하늘이 2.2:1 이다)."""
    from capa_simulation.services.floor_layout_mark import MARK_COLOR_KEYS

    weak: list[str] = []
    for mode, palette in tokens._PALETTES.items():
        inks = palette["SPACE_MARK_TEXT_COLORS"]
        assert set(inks) == set(MARK_COLOR_KEYS), mode
        for key, ink in inks.items():
            for surface in ("SURFACE", "SPACE_CANVAS", "SPACE_BLOCK_FILL"):
                ratio = contrast_ratio(ink, palette[surface])
                if ratio < 4.5:
                    weak.append(f"{mode}.{key} {ink} on {surface}: {ratio:.2f}")

    assert not weak, "\n".join(weak)
