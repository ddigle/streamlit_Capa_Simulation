# Purpose: 서비스 공용 중복 키 검사와 텍스트 키 strip 규칙을 검증한다.

import numpy as np
import pandas as pd
import pytest

from capa_simulation.services.frame_checks import assert_unique_keys, strip_text_columns


def test_assert_unique_keys_passes_when_every_key_combination_is_unique() -> None:
    data = pd.DataFrame({"공정": ["EDS", "TEST"], "제품정보": ["A", "A"], "값": [1, 2]})

    assert_unique_keys(data, ["공정", "제품정보"], "RQ_YLD 연결 키가")


def test_assert_unique_keys_keeps_the_caller_message_prefix_and_particle() -> None:
    data = pd.DataFrame({"공정": ["EDS", "EDS"], "Weeknum": ["26-W01", "26-W01"]})

    with pytest.raises(ValueError) as error:
        assert_unique_keys(data, ["공정", "Weeknum"], "가용설비 입력 표의 공정·Weeknum이")

    assert str(error.value) == (
        "가용설비 입력 표의 공정·Weeknum이 중복되었습니다: [{'공정': 'EDS', 'Weeknum': '26-W01'}]"
    )


def test_assert_unique_keys_shows_at_most_five_examples() -> None:
    # 예시가 끝없이 길어지면 화면이 오류 한 줄에 덮인다. 다섯 건에서 끊는다.
    data = pd.DataFrame({"공정": [f"P{index}" for index in range(6) for _ in range(2)]})

    with pytest.raises(ValueError) as error:
        assert_unique_keys(data, ["공정"], "소요대수 상세의 연결 키가")

    message = str(error.value)
    assert message.count("'공정'") == 5
    assert "P4" in message
    assert "P5" not in message


def test_assert_unique_keys_accepts_a_tuple_of_keys() -> None:
    data = pd.DataFrame({"공정": ["EDS", "EDS"], "STEP_SEQ": ["10", "10"]})

    with pytest.raises(ValueError, match="중복되었습니다"):
        assert_unique_keys(data, ("공정", "STEP_SEQ"), "RQ_REQB의 연결 키가")


def test_strip_text_columns_edits_in_place_and_leaves_other_columns_alone() -> None:
    data = pd.DataFrame({"공정": [" EDS "], "메모": [" 그대로 "], "값": [1]})

    strip_text_columns(data, ["공정"])
    assert data["공정"].tolist() == ["EDS"]
    assert str(data["공정"].dtype) == "string"
    assert data["메모"].tolist() == [" 그대로 "]
    assert data["값"].tolist() == [1]


def test_strip_text_columns_lifts_missing_values_to_pandas_na() -> None:
    data = pd.DataFrame({"공정": [None, " EDS"]})

    strip_text_columns(data, ["공정"])

    assert data["공정"].isna().tolist() == [True, False]


def _same_text_as_separate_objects(text: str, count: int) -> list[str]:
    # DuckDB fetchdf 처럼 같은 글자를 칸마다 따로 만든 객체로 둔다(리터럴은 한 객체로 묶인다).
    return ["".join(list(text)) for _ in range(count)]


def test_strip_text_columns_matches_plain_string_strip_on_mixed_values() -> None:
    # 고유값만 떼어 펼치는 구현이 `astype("string").str.strip()` 과 값·dtype·인덱스까지 같아야 한다.
    raw = [" EDS ", "EDS", None, np.nan, pd.NA, "", "  ", 10, 2.5, " TEST ", " EDS ", None]
    index = [0, 1, 1, 2, 3, 3, 4, 5, 6, 7, 8, 8]
    data = pd.DataFrame(
        {
            "공정": pd.Series(raw, index=index, dtype=object),
            "제품정보": pd.Series(pd.Categorical([" A", "B ", None, " A"] * 3), index=index),
        }
    )
    expected = {column: data[column].astype("string").str.strip() for column in data.columns}

    strip_text_columns(data, ["공정", "제품정보"])

    for column, series in expected.items():
        pd.testing.assert_series_equal(data[column], series)


def test_strip_text_columns_handles_empty_and_all_missing_columns() -> None:
    empty = pd.DataFrame({"공정": pd.Series([], dtype=object)})
    missing = pd.DataFrame({"공정": [None, np.nan, pd.NA]})
    expected_empty = empty["공정"].astype("string").str.strip()
    expected_missing = missing["공정"].astype("string").str.strip()

    strip_text_columns(empty, ["공정"])
    strip_text_columns(missing, ["공정"])

    pd.testing.assert_series_equal(empty["공정"], expected_empty)
    pd.testing.assert_series_equal(missing["공정"], expected_missing)


def test_strip_text_columns_lets_equal_texts_share_one_object() -> None:
    # 키 칸은 행이 많아도 고유값이 적다. 같은 글자가 한 객체를 함께 써야 뒤의 연결·중복 검사 해시와
    # 계산 캐시 pickle 이 칸마다 글자를 다시 다루지 않는다. 글자를 객체로 담는 저장소에서만 뜻이
    # 있는 구현 세부라 그때만 본다.
    data = pd.DataFrame(
        {
            "공정": _same_text_as_separate_objects("EDS ", 50)
            + _same_text_as_separate_objects("TEST", 50)
        }
    )
    assert len({id(value) for value in data["공정"].tolist()}) == 100

    strip_text_columns(data, ["공정"])

    if getattr(data["공정"].dtype, "storage", None) != "python":
        pytest.skip("글자를 객체로 담지 않는 string 저장소")
    values = data["공정"].tolist()
    assert set(values) == {"EDS", "TEST"}
    assert len({id(value) for value in values}) == 2
