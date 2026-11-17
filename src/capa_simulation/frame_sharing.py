# Purpose: 세션끼리 함께 쓰는 표의 배열 잠금 · 잠김 확인 · 겉껍데기 사본 · 잠긴 쓰기 오류를 둔다.

"""함께 쓰는 표의 잠금과 겉껍데기 사본(AGENTS 5장 20).

공용 칸(`persistence/cache._load_scenario_snapshot_resource`)의 리비전 표는 잠근 채
세션끼리 함께 쓴다. 잠금은 숨은 제자리 쓰기(같은 dtype 의 `df.loc[…] = …` ·
`columns.values[i] = …`)가 다른 세션의 숫자를 조용히 바꾸는 대신 바로 `ValueError`
(read-only)로 터지게 하는 안전장치다. 열 대입 · dtype 이 바뀌는 대입은 배열이 아니라 그
프레임 객체의 블록을 갈아 끼우므로 받은 쪽 프레임에만 닿는다 — 그래서 공용 칸의 프레임
객체 자체는 넘기지 않고 겉껍데기 사본(`shared_view`)만 넘긴다.

pandas · numpy 만 보는 잎이다 — `persistence/cache.py` · `io/reference_cache.py` ·
`scenario_state.py` 가 함께 쓴다. 잠긴 표에 크기 재기(`memory_usage(deep=True)` ·
`info(memory_usage="deep")` · `sys.getsizeof`)를 부르면 pandas 2.2.3 은 읽기만 해도
`ValueError` 를 낸다(5장 20).
"""

from collections.abc import Iterator
from typing import Any, cast

import numpy as np
import pandas as pd

# pandas 확장 배열이 데이터를 담는 numpy 배열 자리(날짜·nullable 정수·범주).
_ARRAY_SLOTS = ("_ndarray", "_data", "_mask", "_codes")


def _arrays_of(values: object) -> Iterator[np.ndarray[Any, Any]]:
    """numpy 배열이나 확장 배열이 담은 numpy 배열."""
    for array in (values, *(getattr(values, name, None) for name in _ARRAY_SLOTS)):
        if isinstance(array, np.ndarray):
            yield array


def frame_arrays(frame: pd.DataFrame) -> Iterator[np.ndarray[Any, Any]]:
    """프레임의 데이터 블록과 축(열 이름 · 행 Index — `RangeIndex` 는 배열이 없다)의 numpy 배열.

    `frame[col].to_numpy()` 로 보지 않는다 — 확장 dtype 은 새로 만든 쓸 수 있는 사본을 돌려준다.
    """
    blocks: tuple[Any, ...] = cast(Any, frame)._mgr.blocks
    for block in blocks:
        yield from _arrays_of(block.values)
    for axis in (frame.columns, frame.index):
        if not isinstance(axis, pd.RangeIndex):
            yield from _arrays_of(cast(Any, axis)._values)


def lock_frame(frame: pd.DataFrame) -> None:
    """프레임의 데이터 · 축 배열을 읽기 전용으로 잠근다 — 같은 dtype 제자리 쓰기가 바로 터진다."""
    for array in frame_arrays(frame):
        array.flags.writeable = False


def frame_is_locked(frame: pd.DataFrame) -> bool:
    """데이터 · 축 배열이 모두 잠겼는가 — 겉껍데기 사본으로 함께 써도 되는 표인가."""
    return all(not array.flags.writeable for array in frame_arrays(frame))


def is_locked_write_error(exc: BaseException) -> bool:
    """잠긴(읽기 전용) 배열에 쓰다 난 `ValueError` 인가 — 데이터가 아니라 코드 결함이다(5장 20).

    numpy 대입은 `assignment destination is read-only`, pandas 의 Cython 길은
    `buffer source array is read-only`, ufunc 의 `out=` 은 `output array is read-only` 를 낸다 —
    셋 다 `read-only` 를 든다. 기준정보 계약 위반을 결과로 담는 캐시
    (`simulation_cache._capacity_outcome`)가 이 오류를 담지 않고 다시 올리게 가른다.
    """
    return isinstance(exc, ValueError) and "read-only" in str(exc)


def shared_view(frame: pd.DataFrame) -> pd.DataFrame:
    """잠긴 배열을 함께 쓰는 겉껍데기 사본 — 프레임 · 축 객체만 새로 둔다.

    얕은 사본(`copy(deep=False)`)은 Index 객체까지 함께 쥐어 `df.index.name = …` 같은 축 속성 쓰기가
    남의 세션에 닿는다. `Index.copy()` 는 값 배열은 함께 쓰고 객체만 새로 만든다(싸다).
    """
    viewed = frame.copy(deep=False)
    viewed.columns = frame.columns.copy()
    viewed.index = frame.index.copy()
    return viewed
