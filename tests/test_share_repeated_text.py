# Purpose: 리비전 표 글자 칸 공유가 값을 그대로 두고 같은 글을 실제로 한 객체로 모으는지 잠근다.

"""리비전 표 글자 칸 공유(`_sql_helpers.share_repeated_text`, 스위치 `CAPA_SHARE_STRINGS`).

값 · dtype · 블록 꼴 · 빈 칸 · 해시가 켬 · 끔에서 같아야 하고(저장된 `reference_hash` 는 append-only
감사값이다), 켬에서는 실제로 모아야 한다 — pandas 판이 바뀌어 `fetchdf` 프레임의 칸이 쓸 수 있는
view 가 아니게 되면 공유는 조용히 아무것도 하지 않는다. 그 잠금은 손으로 만든 프레임이 아니라 DuckDB
읽기 길(`load_revision` → `load_frame`)로 건다.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import pytest

from capa_simulation import settings
from capa_simulation.persistence import _sql_helpers
from capa_simulation.persistence._sql_helpers import hash_frame, hash_tables, share_repeated_text
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.simulation_cache import frame_digest


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """내장 합성 시드의 공식 리비전 하나."""
    from capa_simulation.application_bootstrap import ensure_initial_scenario
    from capa_simulation.services import builtin_seed
    from capa_simulation.services.builtin_seed import load_builtin_display_order

    database_path = tmp_path_factory.mktemp("share-text") / "scenario.duckdb"
    with pytest.MonkeyPatch.context() as patch:
        missing = tmp_path_factory.mktemp("no_local_display_order") / "RQ_DISPLAY_ORDER.csv"
        patch.setattr(builtin_seed, "LOCAL_DISPLAY_ORDER_CSV_PATH", missing)
        patch.delenv(settings.SHARE_STRINGS_ENV, raising=False)
        repository = DuckDBScenarioRepository(database_path)
        repository.initialize()
        repository.initialize_global_display_order(load_builtin_display_order())
        release = ensure_initial_scenario(repository).release
    assert release is not None
    return database_path, release.revision_id


def _read(
    monkeypatch: pytest.MonkeyPatch, seeded: tuple[Path, str], switch: str | None
) -> dict[str, pd.DataFrame]:
    if switch is None:
        monkeypatch.delenv(settings.SHARE_STRINGS_ENV, raising=False)
    else:
        monkeypatch.setenv(settings.SHARE_STRINGS_ENV, switch)
    database_path, revision_id = seeded
    # 공용 표시순서 프로필(작은 규칙 표)은 `load_frame` 을 지나지 않는다 — 리비전에 저장된 표만.
    snapshot = DuckDBScenarioRepository(database_path).load_revision(
        revision_id, apply_global_display_order=False
    )
    return dict(snapshot.tables)


def _blocks(frame: pd.DataFrame) -> list[tuple[str, tuple[int, ...]]]:
    """블록 꼴(dtype · 모양) — 칸을 갈아 끼우면 객체 블록이 칸마다 갈라진다."""
    blocks: tuple[Any, ...] = cast(Any, frame)._mgr.blocks
    return [(str(block.dtype), tuple(block.shape)) for block in blocks]


def _text_columns(frame: pd.DataFrame) -> list[int]:
    return [
        position
        for position in range(frame.shape[1])
        if frame.iloc[:, position].dtype == object
        and pd.api.types.infer_dtype(frame.iloc[:, position], skipna=True) == "string"
    ]


def test_a_revision_reads_the_same_with_and_without_sharing(
    monkeypatch: pytest.MonkeyPatch, seeded: tuple[Path, str]
) -> None:
    """켬 · 끔 표가 값 · dtype · 블록 꼴 · 빈 칸 자리 · 칸마다 형 · 감사 해시 · 지문까지 같다."""
    off = _read(monkeypatch, seeded, "off")
    on = _read(monkeypatch, seeded, None)

    assert list(on) == list(off)
    assert hash_tables(on, list(on)) == hash_tables(off, list(off))
    for name, expected in off.items():
        actual = on[name]
        assert actual.equals(expected), name
        assert actual.dtypes.astype(str).tolist() == expected.dtypes.astype(str).tolist(), name
        assert _blocks(actual) == _blocks(expected), name
        assert actual.isna().equals(expected.isna()), name
        for position in range(expected.shape[1]):
            assert [type(value) for value in actual.iloc[:, position]] == [
                type(value) for value in expected.iloc[:, position]
            ], (name, position)
        assert hash_frame(actual) == hash_frame(expected), name
        assert frame_digest(actual) == frame_digest(expected), name


def test_every_text_column_of_a_read_revision_is_shared(
    monkeypatch: pytest.MonkeyPatch, seeded: tuple[Path, str]
) -> None:
    """켬으로 읽은 글자 칸마다 서로 다른 글 객체 수 = 서로 다른 값 수다(실제로 모았다).

    pandas 판이 바뀌어 `fetchdf` 칸이 쓸 수 있는 view 가 아니게 되면 이 시험이 먼저 빨갛게 된다 —
    값은 맞은 채 효과만 사라지는 것을 막는 잠금이다.
    """
    tables = _read(monkeypatch, seeded, None)
    checked = repeated = 0
    for name, frame in tables.items():
        for position in _text_columns(frame):
            values = [value for value in frame.iloc[:, position] if isinstance(value, str)]
            distinct_values = len(set(values))
            assert len({id(value) for value in values}) == distinct_values, (
                name,
                frame.columns[position],
            )
            checked += 1
            repeated += len(values) > distinct_values
    assert checked, "글자 칸을 하나도 찾지 못했다 — 시드 꼴이 바뀌었으면 이 시험부터 고친다."
    assert repeated, "같은 글이 되풀이되는 칸이 없다 — 시험이 공유를 가르지 못한다."


def test_columns_mixed_with_numbers_or_flags_are_left_alone() -> None:
    """숫자 · 참거짓이 섞인 칸은 객체 하나 바꾸지 않는다. 글자 칸의 빈 값은 원래 객체 그대로다."""

    def fresh(*parts: str) -> str:
        return "".join(parts)  # 실행 중에 만든 글 — 같은 값이어도 객체가 따로다

    mixed = [1, 1.0, True, fresh("1", ""), None, fresh("1", "")]
    text = [fresh("공정", " A"), fresh("공정", " A"), None, fresh("공정", " B"), np.nan]
    text.append(fresh("공정", " A"))
    unique = [fresh("고유", str(number)) for number in range(6)]
    frame = pd.DataFrame(
        {
            "섞임": pd.Series(mixed, dtype=object),
            "글": pd.Series(text, dtype=object),
            "고유": pd.Series(unique, dtype=object),
            "수량": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        }
    )
    before = frame.copy(deep=True)
    blocks = _blocks(frame)
    mixed_ids = [id(value) for value in frame["섞임"]]
    unique_ids = [id(value) for value in frame["고유"]]

    share_repeated_text(frame)

    assert frame.equals(before)
    assert _blocks(frame) == blocks
    assert [id(value) for value in frame["섞임"]] == mixed_ids
    assert [type(value) for value in frame["섞임"]] == [int, float, bool, str, type(None), str]
    assert [id(value) for value in frame["고유"]] == unique_ids
    shared = frame["글"].tolist()
    assert shared[0] is shared[1] is shared[5]
    assert shared[2] is None
    assert isinstance(shared[4], float) and np.isnan(shared[4])
    assert shared[3] == "공정 B"


def test_the_same_text_in_two_columns_is_one_object() -> None:
    """한 프레임 안에서는 칸끼리도 같은 글을 같은 객체로 쓴다(그 읽기 동안만 쓰는 사전)."""
    left = ["".join(["DEMO", "-", "P1"]) for _ in range(3)]
    right = ["".join(["DEMO", "-", "P1"]) for _ in range(2)] + ["".join(["DEMO", "-", "P2"])]
    frame = pd.DataFrame(
        {"앞": pd.Series(left, dtype=object), "뒤": pd.Series(right, dtype=object)}
    )

    share_repeated_text(frame)

    assert len({id(value) for value in [*frame["앞"], *frame["뒤"][:2]]}) == 1


@pytest.mark.parametrize(
    ("value", "enabled"),
    [(None, True), ("", True), ("1", True), ("on", True), ("off", False), (" OFF ", False)],
)
def test_the_switch_reads_off_only(value: str | None, enabled: bool) -> None:
    environ = {} if value is None else {settings.SHARE_STRINGS_ENV: value}

    assert settings.share_strings_enabled(environ) is enabled


def test_the_switch_skips_sharing_on_the_read_path(
    monkeypatch: pytest.MonkeyPatch, seeded: tuple[Path, str]
) -> None:
    """끈 서버의 읽기는 공유 함수를 부르지 않고, 켠(기본) 서버는 표마다 부른다."""
    calls: list[int] = []
    original: Callable[[pd.DataFrame], pd.DataFrame] = _sql_helpers.share_repeated_text

    def counted(frame: pd.DataFrame) -> pd.DataFrame:
        calls.append(len(frame))
        return original(frame)

    monkeypatch.setattr(_sql_helpers, "share_repeated_text", counted)
    _read(monkeypatch, seeded, "off")
    assert calls == []
    tables = _read(monkeypatch, seeded, None)
    assert len(calls) == len(tables)
