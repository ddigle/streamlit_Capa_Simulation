# Purpose: 계산 멈춤 글 속 예시 키(dict 꼴)를 화면 꼴 「YY.MM 공정 표시명 양산구분」 으로 바꾼다.

"""계산 멈춤 글의 예시 행 — 화면 꼴(2026-11-11 입력 점검 검토 보드 F7 (나)).

대당 Capa 계산이 기준정보 칸 때문에 멈추면 서비스 글(`services/unit_capacity`)은 걸린 키를
`예시 [{'생산계획년월': 202704, '공정': 'TC Bonding', '양산구분': '양산'}, …]` 꼴로 싣는다. 그 글은
리비전 메모 · 저장 검사 견줌(`capacity_gate._error_kind`) · 사내 집계가 원문으로 쓰므로 서비스는
그대로 두고, 화면 글을 지을 때만 여기서 예시를 `예시 27.04 TC Bonding 양산 · 27.04 TC Bonding ER` 로
바꾼다(설계 규칙 UI-DAT-10 — 화면은 표시명). 부르는 자리는 계산 멈춤 알림(`page_bootstrap.
calculation_stop_notice` — HOME · 계산 화면 · 입력 점검 풍선) · 그 화면들과 계산을 먼저 보는
화면(필요 단축 일정 포함)의 나머지 멈춤 글(`bootstrap_error_message(labels=)`) · 저장 · 지정 · 파생
저장 경고(`capacity_gate`) · 등록 경고 · 자동 갱신 「지금 실행」 결과 알림이다. Space 「필요 단축」
보기의 멈춤 글은 원문이다 — 그 길은 원본 공정소분류만 쓴다(결정 D10).

- 한 예시는 월 → 공정 → 양산구분 차례로 앞에 두고, 그 밖의 칸(제품정보 · 걸린 값 따위)은 서비스 글의
  차례대로 뒤에 값만 잇는다. 월은 `YY.MM`(`month_label` — 여섯 자리 달이 아니면 글자 그대로), 공정은
  공용 표시명이고 같은 예시 묶음의 다른 공정과 겹치면 「표시명 (원본)」(`ProcessLabels.
  unique_format_func`)이다. 표시명을 주지 않으면 원본 이름이다.
- 예시를 파이썬 글자 꼴로 읽지 못하면(`nan` 따위) 그 예시는 원문 그대로 둔다 — 화면 글을 짓다 멈추지
  않는다. 빈 목록 · dict 가 아닌 목록(`예시 ['P~Q']`)도 그대로다.
- 마크다운 자리(알림 전문 · 풍선 · 거부 상자 · 결과 알림)로 가는 글은 `markdown_examples` 로
  짓는다 — 예시 칸 값(공정 표시명 · 원본 이름 · 제품정보 · 걸린 값)은 사람 글이라
  `literal_markdown` 으로 막고(표시명의 `*` · `$` 가 기울임 · 수식이 되지 않게 — AGENTS 9장), 글
  전체의 물결표를 막는다. 앱이 지은 월 `YY.MM` 은 막지 않는다. 평문 자리
  (`bootstrap_error_message(markdown=False)`)는 막지 않은 `readable_examples` 글이다.
- services 는 이 조각을 부르지 않는다(표시명 경계 — `tests/test_process_rename.py`). 표시명은
  인자로만 받는다 — `page_bootstrap` 이 이 조각을 부르고 `process_labels` 가 `page_bootstrap` 을
  부르므로 여기서 `process_labels` 를 실행 때 불러오지 않는다.
- 표시명을 읽지 않는 길(`shortening_source` — 결정 D10 경계 안)이 바깥 자리에서 받은 표시명을 멈춤
  글에만 그대로 넘길 때는 그 인자 꼴을 `ExampleLabels` 로 적는다 — 표시명 모듈 이름을 그 길의 글에
  적지 않는다(`tests/test_process_label_boundaries.py`).
"""

from __future__ import annotations

import ast
import warnings
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Final, TypeAlias

from capa_simulation.components.literal_markdown import literal_markdown, markdown_safe_tildes
from capa_simulation.services.month_columns import month_label

if TYPE_CHECKING:
    from capa_simulation.components.process_labels import ProcessLabels

# 멈춤 글의 예시 행을 지을 표시명 꼴. 실행 때는 글자일 뿐이라 표시명 모듈을 불러오지 않는다.
ExampleLabels: TypeAlias = "ProcessLabels"

# 서비스 글이 예시 목록 앞에 다는 말 — 이 말 바로 뒤 `[` 부터 목록이다.
EXAMPLE_HEAD: Final = "예시 "
# 예시 사이 · 한 예시 안 값 사이.
EXAMPLE_SEPARATOR: Final = " · "
VALUE_SEPARATOR: Final = " "
MONTH_KEY: Final = "생산계획년월"
PROCESS_KEY: Final = "공정"
# 앞에 두는 칸 — 고른 꼴 「YY.MM 공정 표시명 양산구분」 의 차례다.
FRONT_KEYS: Final = (MONTH_KEY, PROCESS_KEY, "양산구분")

_Record = Mapping[str, object]


def markdown_examples(text: str, labels: ProcessLabels | None = None) -> str:
    """마크다운 자리에 싣는 계산 멈춤 글 — 예시 행을 화면 꼴로 바꾸며 칸 값을
    `literal_markdown` 으로 막고, 글 전체의 물결표를 막는다(`markdown_safe_tildes` — 막은 `\\~`
    는 다시 막지 않는다)."""
    return markdown_safe_tildes(readable_examples(text, labels, escape=literal_markdown))


def readable_examples(
    text: str,
    labels: ProcessLabels | None = None,
    *,
    escape: Callable[[str], str] | None = None,
) -> str:
    """`text` 속 `예시 [dict, …]` 목록마다 화면 꼴로 바꾼 글. 읽지 못한 목록은 그대로 둔다.

    물결표 막기(`markdown_safe_tildes`)보다 **먼저** 부른다 — 막은 `\\~` 는 파이썬 글자 꼴이 아니다.
    `escape` 는 예시 칸 값(공정 · 그 밖의 칸 · 여섯 자리 달이 아닌 월 값)을 막는 함수다 — 마크다운
    자리는 `markdown_examples` 로 부른다.
    """
    head = EXAMPLE_HEAD + "["
    parts: list[str] = []
    position = 0
    while (start := text.find(head, position)) >= 0:
        opening = start + len(EXAMPLE_HEAD)
        parsed = _records_at(text, opening)
        if parsed is None:
            parts.append(text[position : opening + 1])
            position = opening + 1
            continue
        records, end = parsed
        parts.append(text[position:opening])
        parts.append(examples_text(records, labels, escape=escape))
        position = end
    parts.append(text[position:])
    return "".join(parts)


def examples_text(
    records: Sequence[_Record],
    labels: ProcessLabels | None = None,
    *,
    escape: Callable[[str], str] | None = None,
) -> str:
    """예시 묶음 하나의 화면 글 — 예시마다 「YY.MM 공정 양산구분 …」 를 ` · ` 로 잇는다. `escape` 를
    주면 칸 값마다 건다(앱이 지은 `YY.MM` 은 빼고)."""
    processes = [
        str(record[PROCESS_KEY]) for record in records if record.get(PROCESS_KEY) is not None
    ]
    process: Callable[[object], str] = labels.unique_format_func(processes) if labels else _plain
    keep = escape or _as_is
    return EXAMPLE_SEPARATOR.join(_record_text(record, process, keep) for record in records)


def _records_at(text: str, opening: int) -> tuple[list[_Record], int] | None:
    """`opening`(`[` 자리)에서 시작하는 예시 목록과 그 끝 다음 자리. dict 목록이 아니면 None.

    닫는 `]` 를 앞에서부터 하나씩 대 본다 — 이름 안의 `]` 는 글자 꼴이 끝나지 않아 읽히지 않는다.
    """
    closing = text.find("]", opening)
    while closing >= 0:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                value = ast.literal_eval(text[opening : closing + 1])
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                closing = text.find("]", closing + 1)
                continue
        if (
            isinstance(value, list)
            and value
            and all(
                isinstance(record, dict) and record and all(isinstance(key, str) for key in record)
                for record in value
            )
        ):
            return value, closing + 1
        return None
    return None


def _record_text(
    record: _Record, process: Callable[[object], str], escape: Callable[[str], str]
) -> str:
    keys = [key for key in FRONT_KEYS if key in record]
    keys += [key for key in record if key not in FRONT_KEYS]
    values: list[str] = []
    for key in keys:
        value = record[key]
        if value is None:
            continue
        if key == MONTH_KEY:
            values.append(_month_text(value, escape))
        elif key == PROCESS_KEY:
            values.append(escape(process(value)))
        else:
            values.append(escape(_value_text(value)))
    return VALUE_SEPARATOR.join(value for value in values if value)


def _month_text(value: object, escape: Callable[[str], str]) -> str:
    """여섯 자리 달(YYYYMM)이면 `YY.MM`, 아니면 글자 그대로(월 형식 오류의 예시도 여기로 온다 —
    사람이 적은 값이라 `escape` 를 건다)."""
    month = value if isinstance(value, int) and not isinstance(value, bool) else None
    if isinstance(value, float) and value.is_integer():
        month = int(value)
    if month is None or not (100_000 <= month <= 999_999 and 1 <= month % 100 <= 12):
        return escape(_value_text(value))
    return month_label(month)


def _value_text(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _plain(value: object) -> str:
    return "" if value is None else str(value)


def _as_is(text: str) -> str:
    return text
