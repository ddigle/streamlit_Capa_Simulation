# Purpose: 화면 표시용 설비 샘플이 불변 리비전에 그대로 저장되지 않게 지킨다.

"""개발용 샘플 보유대수가 영구 기록으로 새어 나가는 것을 막는다.

설비 DB 가 비어 있으면 편집기에 `sample_equipment_baseline()` 이 채워진다. 그 행의
숫자는 예전 `scripts/generate_sample_core_data.py` 의 `PROCESS_SPECS.owned` 를 옮겨 적은
고정 리터럴이고 공정명도 그 리터럴이 정한 것이다. 실제 공정명이 다르면 호기 마스터의
`공정소분류` 와 절대 붙지 않는 **유령 공정**이 총대수·가용대수·가용률에 섞인다.

리비전은 불변이라 저장하면 지울 수 없다. 그래서 저장 직전에 가려낸다. 다만 사용자가
값을 고쳤으면 그 행은 사용자의 것이므로 건드리지 않는다 — 네 컬럼이 모두 샘플과 같은
행만 고른다.
"""

import pandas as pd

from capa_simulation.services.equipment_contract import empty_equipment_baseline
from capa_simulation.services.equipment_samples import (
    SAMPLE_BASELINE_NOTE,
    sample_equipment_baseline,
    untouched_sample_baseline_rows,
)


def test_the_untouched_sample_is_caught_whole() -> None:
    """아무것도 고치지 않고 저장하려 하면 전부 걸려야 한다."""
    baseline = sample_equipment_baseline()

    assert len(untouched_sample_baseline_rows(baseline)) == len(baseline)


def test_an_edited_count_is_the_user_s_own_row() -> None:
    """숫자를 고쳤으면 사용자의 값이다. 막으면 저장 자체가 불가능해진다."""
    baseline = sample_equipment_baseline()
    baseline.loc[0, "기존보유대수"] = 99.0

    leftover = untouched_sample_baseline_rows(baseline)

    assert len(leftover) == len(baseline) - 1
    assert 99.0 not in set(leftover["기존보유대수"])


def test_clearing_the_marker_note_releases_the_row() -> None:
    """샘플 숫자가 진짜 맞다면 비고를 지워 사용자가 명시적으로 책임진다."""
    baseline = sample_equipment_baseline()
    baseline["비고"] = pd.Series([""] * len(baseline), dtype="string")

    assert untouched_sample_baseline_rows(baseline).empty


def test_a_real_baseline_passes_untouched() -> None:
    """실제 값만 있는 표는 하나도 걸리지 않아야 한다."""
    real = pd.DataFrame(
        {
            "공정": pd.Series(["사내공정-A", "사내공정-B"], dtype="string"),
            "분류": pd.Series(["전체", "전체"], dtype="string"),
            "기존보유대수": pd.Series([12.0, 7.0], dtype="float64"),
            "비고": pd.Series(["", ""], dtype="string"),
        }
    )

    assert untouched_sample_baseline_rows(real).empty


def test_an_empty_baseline_is_not_a_leftover() -> None:
    """행을 전부 지우고 저장하는 것은 정상 경로다."""
    assert untouched_sample_baseline_rows(empty_equipment_baseline()).empty


def test_the_marker_note_is_what_the_sample_actually_writes() -> None:
    """표식 문자열이 갈라지면 가드가 조용히 아무것도 못 잡는다."""
    assert set(sample_equipment_baseline()["비고"]) == {SAMPLE_BASELINE_NOTE}


def test_a_frame_missing_the_baseline_columns_is_not_guessed_at() -> None:
    """컬럼이 다르면 비교할 수 없다. 조용히 통과시키되 예외를 내지 않는다."""
    assert untouched_sample_baseline_rows(pd.DataFrame({"공정": ["A"]})).empty


# 같은 위험의 두 번째 출처 — 사용자가 내려받은 CSV 양식의 예시 한 줄. 네 컬럼이 다 차 있어
# `prepare_equipment_baseline` 을 그냥 통과하므로, 지우지 않고 저장하면 존재하지 않는 공정이
# 불변 리비전에 남는다. 표시용 샘플과 출처만 다르고 결과는 같다.


def test_the_template_example_row_is_caught() -> None:
    from io import BytesIO

    from capa_simulation.services.equipment_csv import (
        baseline_csv_template,
        untouched_template_baseline_rows,
    )

    template = pd.read_csv(BytesIO(baseline_csv_template()), dtype="object")

    assert len(untouched_template_baseline_rows(template)) == 1


def test_an_edited_template_row_belongs_to_the_user() -> None:
    from io import BytesIO

    from capa_simulation.services.equipment_csv import (
        baseline_csv_template,
        untouched_template_baseline_rows,
    )

    template = pd.read_csv(BytesIO(baseline_csv_template()), dtype="object")
    template.loc[0, "공정"] = "사내공정-A"

    assert untouched_template_baseline_rows(template).empty


def test_the_template_guard_ignores_a_frame_without_the_columns() -> None:
    from capa_simulation.services.equipment_csv import untouched_template_baseline_rows

    assert untouched_template_baseline_rows(pd.DataFrame({"공정": ["A"]})).empty
