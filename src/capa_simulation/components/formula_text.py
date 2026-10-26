# Purpose: 화면 식 글이 적힌 수로 다시 셈해도 결과와 맞게 인수 글자·등호를 고르고 그 글을 읽는다.

"""화면 식 글 도우미 — 적힌 수로 검산되는 식(AGENTS 8장 「화면 숫자는 검산되어야 한다」).

근거 카드·고른 달 계산·풍선은 「가용 48.0 ÷ 소요 44.0 = 109%」 처럼 식을 글로 적는다. 결과는
반올림 전 값으로 낸다(판정·과부족·올림이 그 값을 쓴다). 인수를 화면 자릿수로 깎아 적으면 적힌
수로 다시 셈한 값이 결과 끝자리와 어긋날 수 있다 — 「3.35 − 0.97 = 2.39」(적힌 수로는 2.38).
그때 쓰는 길이 둘이고 **화면마다 지금 쓰는 길을 지킨다.** 결과 값·판정·올림 규칙은 그대로다 —
식 글만 고른다.

- **등호를 「≈」 로**(`equals_mark`) — 인수는 늘 화면 자릿수로 적고, 적힌 인수로 다시 셈한 글이
  결과 글과 다르면 「=」 대신 「≈」. 다시 셈할 인수는 적힌 글자에서 읽을 수 있다
  (`written_value`). 공정 Capa 상세(근거 카드·결합 캔버스 풍선), 가용설비 현황 비교 시트 풍선,
  제약 시뮬레이션 계산표 풍선.
- **인수 자릿수를 늘려**(`consistent_digits` + `operand_text`) — 어긋날 때만 그 식의 인수를 모두
  같은 자릿수로 한 자리씩(여섯째 자리까지) 더 적고, 그래도 못 맞추면 화면 자릿수와 「≈」. 제약
  시뮬레이션 고른 달 계산 다섯 단계. 인수마다 따로 늘리는 꼴(`consistent_places` — 더 적는 자리
  수의 합이 가장 작게, 같으면 뒤 인수 먼저)은 표준 목표 로직 분석이다(이미 맞는 큰 수까지 길어지지
  않게).

`parse_formula` 는 식 글 한 줄을 읽어 다시 셈하는 **시험용 읽기**다 — 화면 그리기 길에서
부르지 않는다. 순수 함수만 둔다(세션·캐시·DB 를 보지 않는다).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

APPROX: Final = "≈"
"""적힌 수로 다시 셈한 값이 결과와 다를 때의 등호."""

EQUALS: Final = "="

MINUS: Final = "\N{MINUS SIGN}"
"""화면이 음수·빼기에 쓰는 글자(「−」, U+2212 — 붙임표 「-」 가 아니다)."""

OPERAND_DIGITS: Final = (2, 3, 4, 5, 6)
"""자릿수 늘리기 길의 인수 소수 자릿수 후보. 첫 후보가 화면 자릿수다(대수는 둘째 자리)."""

MAX_PLACES: Final = OPERAND_DIGITS[-1]
"""자릿수 늘리기 길에서 인수를 적을 수 있는 가장 긴 소수 자리(여섯째)."""


def equals_mark(result: str, recomputed: str) -> str:
    """식의 등호 — 적은(반올림한) 인수로 다시 셈한 글이 결과 글과 같으면 「=」, 다르면 「≈」."""
    return EQUALS if result == recomputed else APPROX


def written_value(text: str) -> float | None:
    """화면이 적은 수 글자를 다시 수로 — 「1,234.5」·「−0.18」·「+1.13」·「109%」(→ 1.09).

    「—」 처럼 수가 아닌 글자는 `None` 이다. 「≈」 길이 **적힌 인수 그대로** 다시 셈할 때 쓴다 —
    서식(자릿수·0 이 되는 값의 한 자리 더)을 쓰는 쪽에서 따로 흉내 내지 않는다."""
    match = _NUMBER_TEXT.fullmatch(text.strip())
    if match is None:
        return None
    value = float(match["digits"].replace(",", ""))
    if match["sign"] in (MINUS, "-"):
        value = -value
    return value / 100 if match["percent"] else value


def consistent_digits(compute: Callable[[int], str], shown: str) -> tuple[int, str]:
    """`compute(자릿수)` 가 적힌 결과 `shown` 과 같아지는 가장 적은 자릿수와 등호 「=」.
    어느 후보로도 못 맞추면 화면 자릿수(첫 후보)와 「≈」 다."""
    for digits in OPERAND_DIGITS:
        if compute(digits) == shown:
            return digits, EQUALS
    return OPERAND_DIGITS[0], APPROX


def consistent_places(
    compute: Callable[[tuple[int, ...]], str | None], shown: str, bases: Sequence[int]
) -> tuple[tuple[int, ...], str]:
    """인수마다 자릿수를 따로 늘려 `compute(인수별 자릿수)` 가 적힌 결과 `shown` 과 같아지는
    자릿수와 「=」. 더 적는 자리 수의 합이 가장 작은 것부터, 합이 같으면 뒤 인수에 먼저 더 적는다.
    인수마다 `MAX_PLACES` 까지다. 끝내 못 맞추면 처음 자리(`bases`)와 「≈」 다."""
    starts = tuple(bases)
    most = tuple(max(0, MAX_PLACES - base) for base in starts)
    for total in range(sum(most) + 1):
        for extras in _extras(most, total):
            places = tuple(base + extra for base, extra in zip(starts, extras, strict=True))
            if compute(places) == shown:
                return places, EQUALS
    return starts, APPROX


def _extras(most: Sequence[int], total: int) -> list[tuple[int, ...]]:
    """합이 `total` 이고 i 번째가 `most[i]` 를 넘지 않는 더 적을 자리 수들 — 앞 인수가 작은 차례
    (곧 뒤 인수에 먼저 더 적는다)."""
    if not most:
        return [()] if total == 0 else []
    rest = most[1:]
    return [
        (extra, *tail)
        for extra in range(max(0, total - sum(rest)), min(total, most[0]) + 1)
        for tail in _extras(rest, total - extra)
    ]


def operand_text(
    value: float,
    digits: int,
    plain: Callable[[float], str],
    *,
    places: int = OPERAND_DIGITS[0],
) -> str:
    """식 인수 글자 — `digits` 가 화면 자릿수(`places`) 이하면 화면의 평소 글자(`plain`), 더
    적으면 뒤 0 을 떼되 화면 자릿수는 둔다. 그 자릿수로 정수면 평소 글자다(「5」·「40」)."""
    if digits <= places:
        return plain(value)
    rounded = round(value, digits)
    if abs(rounded - round(rounded)) < 0.5 * 10**-digits:
        return plain(rounded)
    text = f"{abs(rounded):,.{digits}f}".rstrip("0")
    if len(text.rsplit(".", 1)[-1]) < places:
        text = f"{abs(rounded):,.{places}f}"
    return f"{MINUS}{text}" if rounded < 0 else text


# ================================================================== 시험용 읽기


@dataclass(frozen=True)
class Formula:
    """식 글 한 줄 — 인수·연산·등호·결과. 결과 끝자리 한 칸(`unit`)의 반이 검산 허용 폭이다."""

    operands: tuple[Decimal, ...]
    operators: tuple[str, ...]
    sign: str
    result: Decimal
    unit: Decimal

    def value(self) -> Decimal:
        """적힌 인수로 다시 셈한 값 — 곱·나눗셈 먼저, 그다음 왼쪽부터 더하기·빼기."""
        terms: list[Decimal] = [self.operands[0]]
        signs: list[str] = []
        for operator, operand in zip(self.operators, self.operands[1:], strict=True):
            if operator in _PRODUCT_OPERATORS:
                terms[-1] = terms[-1] * operand if operator == "×" else terms[-1] / operand
            else:
                signs.append(operator)
                terms.append(operand)
        total = terms[0]
        for operator, term in zip(signs, terms[1:], strict=True):
            total = total + term if operator == "+" else total - term
        return total

    def holds(self) -> bool:
        """다시 셈한 값이 적힌 결과의 자릿수에서 같은가(꼭 반 칸이면 어느 반올림도 받는다)."""
        return abs(self.value() - self.result) <= self.unit / 2


def parse_formula(text: str) -> Formula:
    """식 글 한 줄을 읽는다 — 「a ÷ b = c」·「a × b% = c」·「a − b × c = d」·「a + b = c」 와
    결과가 앞인 「c = a ÷ b」. 이름(「가용」·「소요」·제품명)·굵게(`**`)·HTML 태그·뒤 글
    (「→ 6대」)은 건너뛴다. 식이 하나가 아니거나 결과 수가 없으면 `ValueError` 다."""
    clean = _TAG.sub("", text).replace("**", "").replace("`", "")
    pieces = _RELATION.split(clean)
    segments, signs = pieces[::2], pieces[1::2]
    tokens = [_tokens(segment) for segment in segments]
    found = [
        (index, run)
        for index, segment in enumerate(tokens)
        for run in _runs(segment)
        if len(run) > 1
    ]
    if len(found) != 1:
        raise ValueError(f"식이 하나가 아닙니다: {text!r}")
    index, run = found[0]
    if index + 1 < len(segments) and _numbers(tokens[index + 1]):
        result_text, sign = _numbers(tokens[index + 1])[0], signs[index]
    elif index > 0 and _numbers(tokens[index - 1]):
        result_text, sign = _numbers(tokens[index - 1])[-1], signs[index - 1]
    else:
        raise ValueError(f"결과 수가 없습니다: {text!r}")
    result, unit = _decimal(result_text)
    return Formula(
        operands=tuple(_decimal(token)[0] for token in run[::2]),
        operators=tuple(token.strip() for token in run[1::2]),
        sign=sign,
        result=result,
        unit=unit,
    )


_NUMBER_TEXT: Final = re.compile(
    rf"(?P<sign>[{MINUS}+-]?)(?P<digits>\d[\d,]*(?:\.\d+)?)(?P<percent>%?)"
)
_TAG: Final = re.compile(r"<[^>]+>")
_RELATION: Final = re.compile(r"(?:^|\s)([=≈])(?:\s|$)")
_PRODUCT_OPERATORS: Final = frozenset({"×", "÷", "/"})
# 수(앞에 붙은 부호 「−」·「+」·「-」, 뒤 %)와 연산(띄운 「 − 」·「 + 」·「 × 」·「 ÷ 」, 붙인
# 「×」·분수 「/」). 영문자에 붙은 수(「HBM3E」)는 이름이라 수가 아니다.
_TOKEN: Final = re.compile(
    rf"(?P<number>(?:(?<![^\s(])[{MINUS}+-])?(?<![A-Za-z0-9.,])\d[\d,]*(?:\.\d+)?%?"
    r"(?![A-Za-z0-9]))"
    rf"|(?P<operator> [{MINUS}+×÷] |×|(?<=\d)/(?=\d))"
)


def _tokens(segment: str) -> list[str]:
    return [match.group() for match in _TOKEN.finditer(segment)]


def _is_operator(token: str) -> bool:
    return token.strip() in (MINUS, "+", "×", "÷", "/")


def _runs(tokens: Sequence[str]) -> list[list[str]]:
    """수 (연산 수)* 로 이어진 묶음들 — 연산 없이 이웃한 수(「27년 6월 몫 6대」)는 따로 선다."""
    runs: list[list[str]] = []
    for token in tokens:
        if _is_operator(token):
            if runs and not _is_operator(runs[-1][-1]):
                runs[-1].append(token)
            continue
        if runs and _is_operator(runs[-1][-1]):
            runs[-1].append(token)
        else:
            runs.append([token])
    return [run[:-1] if _is_operator(run[-1]) else run for run in runs]


def _numbers(tokens: Sequence[str]) -> list[str]:
    return [token for token in tokens if not _is_operator(token)]


def _decimal(token: str) -> tuple[Decimal, Decimal]:
    """수 글자 → (값, 끝자리 한 칸). 퍼센트는 1/100 이다(「120%」 → 1.20, 한 칸 0.01)."""
    match = _NUMBER_TEXT.fullmatch(token)
    if match is None:
        raise ValueError(f"수가 아닙니다: {token!r}")
    digits = match["digits"].replace(",", "")
    value = Decimal(digits)
    if match["sign"] in (MINUS, "-"):
        value = -value
    places = len(digits.split(".", 1)[1]) if "." in digits else 0
    unit = Decimal(1).scaleb(-places)
    if match["percent"]:
        return value / 100, unit / 100
    return value, unit
