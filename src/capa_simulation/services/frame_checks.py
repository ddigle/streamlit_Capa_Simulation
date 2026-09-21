# Purpose: 계산 서비스가 공유하는 중복 키 검사와 텍스트 키 strip 규칙을 단일 정의한다.

"""Shared duplicate-key and text-key checks for calculation services.

여기 있는 두 검사는 본래 `frame_contracts.py` 에 있어야 할 같은 종류의 공용 규칙이다.
그러나 `frame_contracts.py` 는 이번 주기의 **단일 선언 지점**이라 손대지 않기로 했으므로
같은 규칙을 임시로 이 모듈에 모아 둔다. **다음 주기에 `frame_contracts.py` 로 합친다** —
그때까지 새 공용 검증을 여기에 더 쌓지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd


def assert_unique_keys(data: pd.DataFrame, keys: Sequence[str], message_prefix: str) -> None:
    """연결 키 중복을 예시와 함께 한국어 오류로 알린다.

    어느 행이 겹쳤는지 적지 않으면 사용자가 기준정보의 어디를 고쳐야 하는지 알 수 없다.
    그래서 중복 키 조합을 **최대 5건** 함께 싣는다.

    `message_prefix` 는 주어와 조사(`~가`/`~이`)까지 호출부가 그대로 넘긴다. 테이블마다
    겹친 키의 이름이 달라 여기서 문장을 조립하면 지금 쓰는 문구가 바뀐다.
    """
    key_columns = list(keys)
    duplicated = data.duplicated(key_columns, keep=False)
    if duplicated.any():
        examples = data.loc[duplicated, key_columns].drop_duplicates().head(5).to_dict("records")
        raise ValueError(f"{message_prefix} 중복되었습니다: {examples}")


def strip_text_columns(data: pd.DataFrame, columns: Sequence[str]) -> None:
    """텍스트 키 컬럼을 `string` 으로 올리고 앞뒤 공백을 떼어 **제자리에서** 바꾼다.

    호출부가 원본 프레임을 건드리면 안 되는 자리에서는 `.copy()` 로 뜬 프레임을 넘긴다.
    """
    for column in columns:
        data[column] = data[column].astype("string").str.strip()
