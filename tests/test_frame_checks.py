# Purpose: 서비스 공용 중복 키 검사와 텍스트 키 strip 규칙을 검증한다.

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
