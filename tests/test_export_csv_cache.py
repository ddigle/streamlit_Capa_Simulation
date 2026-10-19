# Purpose: 내려받기 CSV 바이트 캐시가 캐시 없이 만든 바이트와 같고 입력이 바뀌면 다시 만드는지 본다.

"""내려받기를 누르지 않아도 매 회차 만들던 CSV 바이트를 키로 둔다(콜러블 지연 생성은 쓰지 않는다 —
TODO 결정 기록 2026-09-18). 바이트가 화면 표와 어긋나면 사용자가 받은 파일이 틀리므로 키에 든 입력
하나만 바꿔도 바이트가 바뀌는지, 같은 키면 다시 만들지 않는지 본다.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from functools import partial

import pandas as pd
import pytest
import streamlit as st

from capa_simulation.services import simulation_cache as sc
from capa_simulation.services.weekly_availability_input import build_weekly_availability_template


@pytest.fixture(autouse=True)
def _fresh_cache() -> Iterator[None]:
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def _saved(units: float = 2.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["P-A", "P-A", "P-B"],
            "Weeknum": ["26-W32", "26-W33", "26-W32"],
            "가용대수": [units, 3.0, 1.0],
        }
    )


def _template_csv(processes: tuple[str, ...], saved: pd.DataFrame, end: date) -> bytes:
    return sc.get_weekly_availability_template_csv(
        processes, date(2026, 8, 1), end, sc.frame_digest(saved), _saved=saved
    )


def _old_template_csv(processes: tuple[str, ...], saved: pd.DataFrame, end: date) -> bytes:
    template = build_weekly_availability_template(
        list(processes), date(2026, 8, 1), end, saved=saved
    )
    return template.to_csv(index=False).encode("utf-8-sig")


def test_the_template_csv_matches_and_follows_every_input() -> None:
    end = date(2026, 8, 31)
    base = _template_csv(("P-A", "P-B"), _saved(), end)
    assert base == _old_template_csv(("P-A", "P-B"), _saved(), end)

    variants = {
        "저장값 한 칸": (("P-A", "P-B"), _saved(units=5.0), end),
        "공정 차례": (("P-B", "P-A"), _saved(), end),
        "공정 선택": (("P-A",), _saved(), end),
        "종료일": (("P-A", "P-B"), _saved(), date(2026, 9, 15)),
    }
    for name, (processes, saved, last) in variants.items():
        changed = _template_csv(processes, saved, last)
        assert changed != base, name
        assert changed == _old_template_csv(processes, saved, last), name


def test_the_template_csv_does_not_rebuild_on_a_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    """같은 키면 양식을 다시 만들지 않는다 — 내려받기를 누르지 않은 회차마다 만들지 않으려고 둔
    캐시다."""
    calls: list[int] = []

    def counting(*args: object, **kwargs: object) -> pd.DataFrame:
        calls.append(1)
        return build_weekly_availability_template(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sc, "build_weekly_availability_template", counting)
    end = date(2026, 8, 31)

    first = _template_csv(("P-A", "P-B"), _saved(), end)
    again = _template_csv(("P-A", "P-B"), _saved(), end)

    assert first == again == _old_template_csv(("P-A", "P-B"), _saved(), end)
    assert calls == [1]


def _table(value: float = 1.25) -> pd.DataFrame:
    return pd.DataFrame({"공정": ["P-A", "P-B"], "소요기준": ["WF", "WF"], "202608": [value, 2.5]})


def _build(table: pd.DataFrame, calls: list[int]) -> bytes:
    calls.append(1)
    return table.to_csv(index=False, float_format="%.2f").encode("utf-8-sig")


def test_export_csv_rebuilds_only_when_the_table_changes() -> None:
    calls: list[int] = []

    def export(table: pd.DataFrame) -> bytes:
        return sc.get_export_csv(
            sc.csv_export_key("test", table, ["공정", "소요기준"], "2"),
            _build=partial(_build, table, calls),
        )

    first = export(_table())
    again = export(_table())
    changed = export(_table(value=1.5))

    assert first == again == _build(_table(), [])
    assert changed == _build(_table(value=1.5), [])
    assert changed != first
    assert calls == [1, 1]


def test_export_csv_keys_split_by_format_and_columns() -> None:
    table = _table()
    keys = {
        sc.csv_export_key("test", table, ["공정", "소요기준"], "2"),
        sc.csv_export_key("test", table, ["공정", "소요기준"], "0"),
        sc.csv_export_key("test", table, ["공정"], "2"),
        sc.csv_export_key("other", table, ["공정", "소요기준"], "2"),
    }
    assert len(keys) == 4
