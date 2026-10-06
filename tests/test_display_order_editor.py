# Purpose: display order editor 관련 정상·예외·회귀 동작을 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.display_order import (
    apply_display_order,
    classification_columns_in_display_order,
    prepare_display_order,
)
from capa_simulation.services.display_order_csv import (
    display_order_from_clipboard,
    display_order_from_csv,
    display_order_to_csv,
)
from capa_simulation.services.display_order_editor import (
    CLASH_REPORT_LIMIT,
    DisplayOrderValueClashError,
    display_label_mistakes,
    ensure_route_sequence_rules,
    replace_display_order_scope,
    validate_display_order,
)


def _rules() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "페이지 구분": ["HOME", "HOME", "HOME"],
            "탭 구분": ["계획", "계획", "Capa"],
            "정렬우선순위": [1, 1, 1],
            "분류컬럼": ["제품정보", "제품정보", "공정"],
            "정렬방식": ["사용자지정", "사용자지정", "오름차순"],
            "분류값": ["A", "B", pd.NA],
            "값표시순서": [1, 2, pd.NA],
            "활성여부": ["Y", "Y", "Y"],
        }
    )


def test_replace_display_order_scope_preserves_other_scopes() -> None:
    edited = pd.DataFrame(
        {
            "정렬우선순위": [1, 1],
            "분류컬럼": ["제품정보", "제품정보"],
            "정렬방식": ["사용자지정", "사용자지정"],
            "분류값": ["B", "A"],
            "값표시순서": [1, 2],
            "활성여부": ["Y", "Y"],
        }
    )

    result = replace_display_order_scope(_rules(), "HOME", "계획", edited)

    plan = result.loc[result["탭 구분"].eq("계획")]
    assert plan["분류값"].tolist() == ["B", "A"]
    assert result.loc[result["탭 구분"].eq("Capa"), "분류컬럼"].tolist() == ["공정"]


def test_display_order_rejects_duplicate_custom_order() -> None:
    source = _rules()
    source.loc[1, "값표시순서"] = 1

    with pytest.raises(ValueError, match="값표시순서.*중복"):
        validate_display_order(source)


def _case_clash() -> pd.DataFrame:
    """`Top` 과 `TOP` 은 적용(`apply_display_order`)이 같은 값으로 본다."""
    return pd.DataFrame(
        {
            "페이지 구분": ["부하량"] * 2,
            "탭 구분": ["환산"] * 2,
            "정렬우선순위": [1] * 2,
            "분류컬럼": ["WF 구분"] * 2,
            "정렬방식": ["사용자지정"] * 2,
            "분류값": ["Top", "TOP"],
            "값표시순서": [1, 2],
            "활성여부": ["Y"] * 2,
        }
    )


def test_save_validation_uses_the_same_key_as_apply() -> None:
    """대소문자만 다른 두 값은 저장에서 막힌다. 전에는 통과하고 화면에서 ValueError 가 났다."""
    clash = _case_clash()
    with pytest.raises(ValueError, match="RQ_DISPLAY_ORDER의 사용자지정 값이 중복"):
        apply_display_order(pd.DataFrame({"WF 구분": ["Top"]}), clash, "부하량", "환산")

    with pytest.raises(DisplayOrderValueClashError) as caught:
        validate_display_order(clash)

    message = str(caught.value)
    assert "부하량 › 환산 › WF 구분" in message
    # 적은 표기 그대로 알린다 — 줄인 키(`top`)로 적으면 어느 행인지 찾을 수 없다.
    assert "`Top`" in message and "`TOP`" in message


def test_values_differing_only_in_outer_spaces_also_clash() -> None:
    clash = _case_clash().assign(분류값=[" Top", "top "])

    with pytest.raises(DisplayOrderValueClashError, match="Top"):
        validate_display_order(clash)


def test_the_clash_message_names_at_most_five_scopes() -> None:
    frames = [
        _case_clash().assign(**{"탭 구분": f"탭{index}"}) for index in range(CLASH_REPORT_LIMIT + 2)
    ]

    with pytest.raises(DisplayOrderValueClashError) as caught:
        validate_display_order(pd.concat(frames, ignore_index=True))

    message = str(caught.value)
    assert message.count("`Top` · `TOP`") == CLASH_REPORT_LIMIT
    assert "외 2건" in message


def test_every_save_and_import_path_rejects_a_case_clash() -> None:
    """편집 저장·CSV·Excel 붙여넣기가 모두 같은 관문(`validate_display_order`)을 지난다."""
    clash = _case_clash()
    current = _rules()
    edited = clash.drop(columns=["페이지 구분", "탭 구분"])

    with pytest.raises(DisplayOrderValueClashError):
        replace_display_order_scope(current, "부하량", "환산", edited)
    with pytest.raises(DisplayOrderValueClashError):
        display_order_from_csv(clash.to_csv(index=False).encode("utf-8-sig"))
    with pytest.raises(DisplayOrderValueClashError):
        display_order_from_clipboard(clash.to_csv(index=False, sep="	"))
    with pytest.raises(DisplayOrderValueClashError):
        ensure_route_sequence_rules(clash)


def test_a_stored_profile_with_a_clash_still_reads_and_downloads() -> None:
    """검사 전에 저장된 프로필은 읽는 길(기동 보강·Admin 탭·내려받기)에서만 견딘다.

    다른 범위를 고쳐 저장하면 합친 결과가 다시 검사를 받아 겹친 값을 적은 오류로 막힌다.
    """
    stored = pd.concat([_rules(), _case_clash()], ignore_index=True)

    validated = validate_display_order(stored, allow_value_clashes=True)
    assert len(validated) == len(stored)
    assert display_order_to_csv(stored, allow_value_clashes=True)

    edited = _rules().loc[_rules()["탭 구분"].eq("계획")].drop(columns=["페이지 구분", "탭 구분"])
    with pytest.raises(DisplayOrderValueClashError, match="부하량 › 환산 › WF 구분"):
        replace_display_order_scope(stored, "HOME", "계획", edited)
    # 글자까지 같은 중복은 예전처럼 읽는 길에서도 막는다.
    exact = pd.concat([_rules(), _rules().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="분류값이 같은 페이지·탭·분류컬럼에서 중복"):
        validate_display_order(exact, allow_value_clashes=True)


def test_display_order_csv_round_trip_supports_utf8_and_cp949() -> None:
    source = validate_display_order(_rules())

    utf8 = display_order_from_csv(display_order_to_csv(source))
    cp949 = display_order_from_csv(source.to_csv(index=False).encode("cp949"))

    pd.testing.assert_frame_equal(utf8, source)
    pd.testing.assert_frame_equal(cp949, source)


def test_display_order_clipboard_round_trip() -> None:
    source = validate_display_order(_rules())

    result = display_order_from_clipboard(source.to_csv(index=False, sep="\t"))

    pd.testing.assert_frame_equal(result, source)


def test_display_order_csv_rejects_changed_columns() -> None:
    invalid = _rules().rename(columns={"분류컬럼": "잘못된 컬럼"})

    with pytest.raises(ValueError, match="컬럼 계약"):
        display_order_from_csv(invalid.to_csv(index=False).encode("utf-8-sig"))


def test_route_sequence_rules_are_added_as_the_final_hierarchy() -> None:
    source = pd.DataFrame(
        {
            "페이지 구분": ["산출 결과", "산출 결과", "산출 결과"],
            "탭 구분": ["소요대수", "소요대수", "소요대수"],
            "정렬우선순위": [1, 2, 3],
            "분류컬럼": ["Area_Name", "공정", "제품정보"],
            "정렬방식": ["오름차순", "오름차순", "오름차순"],
            "분류값": [pd.NA, pd.NA, pd.NA],
            "값표시순서": [pd.NA, pd.NA, pd.NA],
            "활성여부": ["Y", "Y", "Y"],
        }
    )

    result = ensure_route_sequence_rules(source)

    scope = result.sort_values("정렬우선순위", kind="stable")
    assert scope["분류컬럼"].tolist() == [
        "Area_Name",
        "공정",
        "제품정보",
        "STEP_SEQ",
        "MCP_SEQ",
    ]
    assert scope["정렬우선순위"].tolist() == [1, 2, 3, 4, 5]


def test_classification_columns_follow_rules_but_keep_route_keys_last() -> None:
    source = ensure_route_sequence_rules(
        pd.DataFrame(
            {
                "페이지 구분": ["산출 결과", "산출 결과"],
                "탭 구분": ["소요대수", "소요대수"],
                "정렬우선순위": [1, 2],
                "분류컬럼": ["Area_Name", "공정"],
                "정렬방식": ["오름차순", "오름차순"],
                "분류값": [pd.NA, pd.NA],
                "값표시순서": [pd.NA, pd.NA],
                "활성여부": ["Y", "Y"],
            }
        )
    )

    result = classification_columns_in_display_order(
        ["공정", "STEP_SEQ", "MCP_SEQ", "제품정보", "Area_Name"],
        source,
        "산출 결과",
        "소요대수",
    )

    assert result == ["Area_Name", "공정", "제품정보", "STEP_SEQ", "MCP_SEQ"]


def test_prepared_display_order_is_reused_across_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from capa_simulation.services import display_order

    prepare_calls = 0
    original_prepare = display_order._prepare_display_order

    def counted_prepare(rules: pd.DataFrame) -> pd.DataFrame:
        nonlocal prepare_calls
        prepare_calls += 1
        return original_prepare(rules)

    monkeypatch.setattr(display_order, "_prepare_display_order", counted_prepare)
    prepared = prepare_display_order(_rules())
    data = pd.DataFrame({"제품정보": ["B", "A"], "값": [2, 1]})

    sorted_data = apply_display_order(data, prepared, "HOME", "계획")
    columns = classification_columns_in_display_order(["값", "제품정보"], prepared, "HOME", "계획")

    assert prepare_calls == 1
    assert sorted_data["제품정보"].tolist() == ["A", "B"]
    assert columns == ["제품정보", "값"]


def test_derived_rules_are_built_once_per_prepared_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`Top_e` 파생은 준비할 때 한 번이다. 도우미를 여러 번 불러도 다시 파생하지 않는다.

    `rules` 는 검증한 입력 그대로 두고, 정렬 도우미는 파생이 더해진 `derived_rules` 를 읽는다.
    """
    from capa_simulation.services import display_order

    derive_calls = 0
    original_derive = display_order._with_edp_top_rule

    def counted_derive(rules: pd.DataFrame) -> pd.DataFrame:
        nonlocal derive_calls
        derive_calls += 1
        return original_derive(rules)

    monkeypatch.setattr(display_order, "_with_edp_top_rule", counted_derive)
    rules = pd.DataFrame(
        {
            "페이지 구분": ["부하량"] * 2,
            "탭 구분": ["환산"] * 2,
            "정렬우선순위": [1] * 2,
            "분류컬럼": ["WF 구분"] * 2,
            "정렬방식": ["사용자지정"] * 2,
            "분류값": ["Top", "Core"],
            "값표시순서": [1, 2],
            "활성여부": ["Y"] * 2,
        }
    )
    prepared = prepare_display_order(rules)
    assert prepared is not None
    data = pd.DataFrame({"WF 구분": ["Core", "Top_e", "Top"], "값": [1, 2, 3]})

    first = apply_display_order(data, prepared, "부하량", "환산")
    second = apply_display_order(data, prepared, "부하량", "환산")
    columns = classification_columns_in_display_order(["값", "WF 구분"], prepared, "부하량", "환산")

    assert derive_calls == 1
    assert first["WF 구분"].tolist() == ["Top", "Top_e", "Core"]
    assert second["WF 구분"].tolist() == ["Top", "Top_e", "Core"]
    assert columns == ["WF 구분", "값"]
    assert "Top_e" not in prepared.rules["분류값"].tolist()
    assert "Top_e" in prepared.derived_rules["분류값"].tolist()


def test_a_display_label_in_the_column_field_is_flagged() -> None:
    """`거래선` 은 화면 표시명이다. 그대로 적으면 저장은 통과하고 정렬만 조용히 안 걸린다.

    `apply_display_order` 가 프레임에 없는 분류컬럼 규칙을 건너뛰기 때문인데, 그 침묵에는
    단서가 없다. 저장을 막지 않고 원본 컬럼명을 일러 준다.
    """
    labels = {"Customer": "거래선", "제품정보": "제품"}
    rules = pd.DataFrame({"분류컬럼": ["거래선", "제품정보", "Stack"]})

    assert display_label_mistakes(rules, labels) == {"거래선": "Customer"}


def test_original_column_names_are_not_flagged() -> None:
    """원본 컬럼명만 적었으면 아무 말도 하지 않는다."""
    labels = {"Customer": "거래선", "제품정보": "제품"}
    rules = pd.DataFrame({"분류컬럼": ["Customer", "제품정보"]})

    assert display_label_mistakes(rules, labels) == {}


def test_a_frame_without_the_column_field_is_ignored() -> None:
    """편집 표가 비어 컬럼조차 없으면 판정할 것이 없다."""
    assert display_label_mistakes(pd.DataFrame(), {"Customer": "거래선"}) == {}
