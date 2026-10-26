# Purpose: 공정별 Cut-off 의 적은 값 찾기와 화면 글(계산이 쓰는 내림 일수 + 내림 표기)을 검증한다.

"""Cut-off 는 소수를 받지만 계산은 내림한 일 단위다(`wd_window`). 화면마다 그 일수로 적고, 적은 값에
소수가 있으면 내림을 함께 적는다(2026-10-26 E2E — 같은 공정이 35일·35.8일로 갈려 보였다)."""

from __future__ import annotations

import math

import pandas as pd

from capa_simulation.services.process_cutoff import (
    cutoff_days_words,
    cutoff_setting,
    prepare_process_cutoff,
)


def _cutoff() -> pd.DataFrame:
    return prepare_process_cutoff(
        pd.DataFrame(
            {
                "공정": ["DEMO-DAF", "DEMO-DA", "DEMO-LG"],
                "Cutoff일수": [35.8, 34.0, math.nan],
                "비고": [None, None, None],
            }
        )
    )


def test_the_written_value_is_found_by_the_trimmed_process_name() -> None:
    cutoff = _cutoff()

    assert cutoff_setting(cutoff, "DEMO-DAF") == 35.8
    assert cutoff_setting(cutoff, " DEMO-DA ") == 34.0
    assert cutoff_setting(cutoff, "DEMO-LG") is None
    assert cutoff_setting(cutoff, "없는 공정") is None
    assert cutoff_setting(None, "DEMO-DAF") is None
    assert cutoff_setting(pd.DataFrame(), "DEMO-DAF") is None


def test_the_words_carry_the_counted_days_and_say_when_they_were_floored() -> None:
    assert cutoff_days_words(35.8) == "35일(35.8일 내림)"
    assert cutoff_days_words(30.25) == "30일(30.25일 내림)"
    assert cutoff_days_words(34.0) == "34일"
    assert cutoff_days_words(0) == "0일"
