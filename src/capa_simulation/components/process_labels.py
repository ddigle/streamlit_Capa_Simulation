# Purpose: 공용 공정 표시명을 화면 표시 직전에만 갈아 끼우는 렌더 계층 단일 경계다.

"""공정명 → 화면 표시명 치환의 유일한 지점.

`공정` 은 `config/data_contract.json` 의 파생 키 여러 개가 업무 키로 갖고
`services/unit_capacity.py` 가 `validate="many_to_one"` 로 조인하는 1급 조인 키다. 그래서
**원본 값은 데이터에서 바꾸지 않는다.** 이 모듈은 표시 직전의 라벨 매핑만 제공한다.

경계는 코드로 지킨다. 이 모듈은 `components/` 안에만 있고 `services/` 어디에서도
import 하지 않는다(`tests/test_process_rename.py` 가 검사한다). 그래서 왕복 CSV·클립보드,
표시순서 `분류값`, 예외 메시지, 프리셋·세션 저장값, 설비 DB 의 공정명에는 표시명이
닿을 길이 없다.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

import pandas as pd

# 테스트가 `settings.DUCKDB_PATH` 를 갈아끼운다. 이름을 직접 import 하면 여기서 잡은
# 바인딩이 교체를 무시하므로 호출 시점에 모듈에서 찾는다.
import capa_simulation.settings as settings
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS
from capa_simulation.persistence.cache import load_global_process_rename
from capa_simulation.services.process_rename import (
    PROCESS_RENAME_COLUMNS,
    normalize_process_text,
)

PROCESS_COLUMN = PROCESS_RENAME_COLUMNS[0]


@dataclass(frozen=True)
class ProcessLabels:
    """지금 화면에 적용할 공정 표시명 묶음.

    `version` 은 Figure 캐시 키 원소로 쓴다. `updated_at` 은 저장마다 바뀌므로 키에 넣으면
    내용이 같아도 중복 무효화가 된다.
    """

    version: int = 0
    labels: Mapping[str, str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.labels)

    def label(self, value: object) -> str:
        """매핑에 없는 공정은 원본 공정명 그대로다."""
        return apply_process_label(value, self.labels)

    def format_func(self) -> ProcessLabelFormatter:
        """`st.multiselect`·`st.selectbox` 의 `format_func=` 에 넘길 함수.

        **값은 절대 바꾸지 않는다.** 선택값·세션값·프리셋 저장값이 원본으로 남아야 한다.
        표시명으로 바꾸면 옵션에 없는 값이 조용히 걸러져 화면이 오류 없이 텅 빈다.
        """
        return ProcessLabelFormatter(self.labels)

    def unique_format_func(
        self, options: Iterable[object], *, reserved: Iterable[object] = ()
    ) -> OptionLabelFormatter:
        """선택 상자 **한 개**의 `format_func=`. 그 상자의 선택지마다 보이는 글자가 서로 다르다.

        Streamlit 1.63 의 selectbox·multiselect 는 브라우저와 값을 **서식 글자**(`format_func`
        의 결과)로 주고받는다. 같은 글자가 둘이면 selectbox 는 마지막 선택지, multiselect 는 첫
        선택지로 돌아와, 표시명이 다른 공정의 원본 이름과 같을 때(DA2 → 「DA」, DA 는 원본) DA2 를
        고르면 세션에 DA 가 들어간다. 잡아 둔 선택도 그 표시명이 생기는 회차에 저절로 바뀐다.

        그래서 보이는 글자가 그 상자의 다른 선택지와 같거나 `reserved`(그 상자의 표지값 —
        Static/Dynamic 의 `전체 합계` 등)와 같으면 표시명이 붙은 그 선택지만 「표시명 (원본)」 으로
        보인다. 같은지는 앞뒤 공백·U+00A0 을 정리해 견준다(눈으로는 같은 글자다). 표시명이 없는
        선택지와 표지값은 글자 그대로다 — 그래서 표시명이 하나도 없으면 지금과 글자까지 같다.
        **값은 언제나 원본이다.** 바꾼 글자가 또 다른 선택지와 정확히 같은 드문 경우는 뒤의 것에
        「 (2)」·「 (3)」 을 붙여 끝까지 가른다.

        선택지마다 만든다 — 회차마다 그 상자의 선택지로 부른다. 표·그림은 이 함수를 쓰지 않으므로
        겹친 두 공정이 같은 글자로 보인다(Admin `Proc Rename` 이 겹침을 경고한다).
        """
        values = list(dict.fromkeys(_option_text(option) for option in options))
        reserved_texts = {_option_text(item) for item in reserved}
        reserved_keys = {normalize_process_text(item) for item in reserved_texts}
        base = {
            value: value if value in reserved_texts else apply_process_label(value, self.labels)
            for value in values
        }
        counts = Counter(normalize_process_text(text) for text in base.values())
        shown: dict[str, str] = {}
        for value in values:
            text = base[value]
            key = normalize_process_text(text)
            clashes = counts[key] > 1 or (value not in reserved_texts and key in reserved_keys)
            shown[value] = f"{text} ({value})" if clashes and text != value else text
        # Streamlit 이 가르는 것은 정확한 글자다. 공백만 다른 원본(`DA`·`DA `)은 이미 서로 다른
        # 글자라 그대로 둔다.
        used: set[str] = set()
        for value in values:
            text = candidate = shown[value]
            suffix = 2
            while candidate in used:
                candidate = f"{text} ({suffix})"
                suffix += 1
            used.add(candidate)
            shown[value] = candidate
        return OptionLabelFormatter(shown)

    def value_labels(self, *columns: str) -> dict[str, Mapping[str, str]]:
        """월별 표의 `value_labels=` 인자. 지정한 분류 컬럼에만 매핑을 건다."""
        if not self.labels:
            return {}
        return {column: self.labels for column in (columns or (PROCESS_COLUMN,))}

    def series(self, values: pd.Series) -> pd.Series:
        """표시용 Series. 원본 Series 를 제자리에서 바꾸지 않는다."""
        if not self.labels:
            return values.astype("object")
        return pd.Series(
            [apply_process_label(value, self.labels) for value in values],
            index=values.index,
            dtype="object",
        )

    def frame(self, data: pd.DataFrame, column: str = PROCESS_COLUMN) -> pd.DataFrame:
        """`column` 만 표시명으로 바꾼 **화면용 복사본**.

        매핑이 없거나 그 컬럼이 없으면 받은 프레임을 그대로 돌려준다 — 그래서 돌려받은 프레임을
        고치지 않는다. 캐시가 들고 있는 프레임을 넘겨도 된다(바꾸는 것은 복사본이다). 빈 칸은
        빈 칸으로 둔다(`series` 는 `None` 을 빈 글자로 바꾼다). CSV 로 내보낼 프레임에는 쓰지
        않는다 — 화면 프레임과 CSV 프레임을 나눈다(AGENTS 8장).
        """
        if not self.labels or column not in data.columns:
            return data
        values = data[column]
        # 고유값마다 한 번만 바꾼다 — 호기 목록처럼 행이 많아도 공정 수만큼만 든다.
        names = {
            value: apply_process_label(value, self.labels) for value in values.dropna().unique()
        }
        shown = data.copy()
        shown[column] = values.astype("object").map(names, na_action="ignore")
        return shown

    def unmatched(self, available: Iterable[object]) -> list[str]:
        """보유하지 않은 원본에 지정된 표시명. 오류가 아니라 안내용이다."""
        owned = {normalize_process_text(value) for value in available}
        return sorted(process for process in self.labels if process not in owned)

    def owned_name_collisions(self, available: Iterable[object]) -> list[str]:
        """매핑 밖 보유 공정의 원본명과 겹치는 표시명. 안내용이며 오류가 아니다.

        `services/process_rename.py` 의 1:1 검증은 규칙 안의 중복만 본다. 표시명이
        **매핑되지 않은 다른 공정의 원본명**과 같으면 그 검증을 통과하지만 화면에는
        서로 다른 두 공정이 같은 이름으로 나온다. 값은 원본이라 조인은 그대로다.

        보유 공정 목록은 시나리오마다 달라 저장을 막으면 안 되므로 경고로만 알린다.
        자기 자신과 같은 표시명, 그리고 그 보유 공정이 다시 다른 이름으로 바뀌는
        경우는 화면에서 겹치지 않으므로 세지 않는다. 원본이 보유 공정이 아닌 규칙도
        세지 않는다 — 그 규칙은 화면에 나타나지 않아 겹칠 대상이 없고, 세면
        `unmatched()` 의 "무시합니다" 안내와 서로 모순된 문구가 함께 뜬다.
        """
        owned = {normalize_process_text(value) for value in available}
        return sorted(
            {
                target
                for source, target in self.labels.items()
                if source in owned
                and target != source
                and target in owned
                and target not in self.labels
            }
        )


@dataclass(frozen=True)
class ProcessLabelFormatter:
    """`format_func=` 자리에 넣는 호출 가능 객체. 람다와 달리 매핑을 들고 다닌다."""

    labels: Mapping[str, str]

    def __call__(self, value: object) -> str:
        return apply_process_label(value, self.labels)


@dataclass(frozen=True)
class OptionLabelFormatter:
    """`ProcessLabels.unique_format_func` 가 돌려주는 `format_func`. 선택지 글자 그대로 찾는다.

    `ProcessLabelFormatter` 와 달리 앞뒤 공백을 정리하지 않고 찾는다 — `DA` 와 `DA ` 가 서로 다른
    선택지면 서로 다른 글자로 보여야 값이 섞이지 않는다. 선택지 밖의 값은 원본 글자 그대로다.
    """

    texts: Mapping[str, str]

    def __call__(self, value: object) -> str:
        text = _option_text(value)
        return self.texts.get(text, text)


def _option_text(value: object) -> str:
    return "" if value is None else str(value)


def apply_process_label(value: object, labels: Mapping[str, str]) -> str:
    """한 값의 표시 문자열. 매핑에 없으면 원본 문자열 그대로다."""
    text = "" if value is None else str(value)
    if not labels:
        return text
    return labels.get(normalize_process_text(value), text)


def process_labels_from_rules(rules: pd.DataFrame, version: int = 0) -> ProcessLabels:
    """저장된 규칙 프레임을 조회용 매핑으로 만든다."""
    if rules.empty or any(column not in rules.columns for column in PROCESS_RENAME_COLUMNS):
        return ProcessLabels(version=version)
    labels = {
        normalize_process_text(source): normalize_process_text(target)
        for source, target in zip(rules["공정"], rules["표시명"], strict=True)
    }
    return ProcessLabels(
        version=version,
        labels={source: target for source, target in labels.items() if source and target},
    )


def get_process_labels() -> ProcessLabels:
    """현재 공용 프로필의 표시명. 프로필이 없으면 빈 매핑(=원본 그대로)이다."""
    try:
        profile = load_global_process_rename(str(settings.DUCKDB_PATH.resolve()))
    # 표시명 조회는 화면을 그리기 위한 것이라 실패해도 화면이 죽으면 안 된다. 프로필이
    # 없거나 DB 를 열지 못하면 원본 공정명을 그대로 쓰는 것이 옳은 저하 동작이다.
    except BOOTSTRAP_ERRORS:
        return ProcessLabels()
    return process_labels_from_rules(profile.rules, profile.version)
