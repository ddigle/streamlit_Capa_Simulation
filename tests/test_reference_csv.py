# Purpose: reference csv 관련 정상·예외·회귀 동작을 검증한다.

import io

import pandas as pd
import pytest

from capa_simulation.services.equipment_count import (
    equipment_count_from_edit_table,
    equipment_count_to_edit_table,
)
from capa_simulation.services.reference_csv import (
    count_removed_values,
    parse_reference_edit_clipboard,
    reference_edit_csv_bytes,
)


def _template() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["Process-B", "Process-A"],
            "양산구분": ["양산", "ER"],
            "202608": [0.9, 0.8],
            "202609": [0.91, 0.81],
        }
    )


def test_reference_clipboard_round_trip_preserves_template_row_order() -> None:
    template = _template()
    modified = template.iloc[::-1].reset_index(drop=True)
    modified.loc[modified["공정"].eq("Process-A"), "202608"] = 0.75

    result = parse_reference_edit_clipboard(
        modified.to_csv(index=False, sep="\t"),
        template,
        ["공정", "양산구분"],
        "RQ_RUN_RATE",
    )

    assert result["공정"].tolist() == ["Process-B", "Process-A"]
    assert float(result.loc[1, "202608"]) == pytest.approx(0.75)


def test_reference_paste_rejects_changed_classification_rows() -> None:
    template = _template()
    changed = template.copy()
    changed.loc[0, "공정"] = "Unknown"

    with pytest.raises(ValueError, match="분류 행"):
        parse_reference_edit_clipboard(
            changed.to_csv(index=False, sep="\t"),
            template,
            ["공정", "양산구분"],
            "RQ_RUN_RATE",
        )


def test_equipment_count_csv_round_trip_validates_nonnegative_values() -> None:
    source = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "공정": ["Process-A", "Process-A"],
            "가용대수": [2.0, 3.0],
        }
    )
    edit = equipment_count_to_edit_table(source, "가용", "가용대수")
    edit.loc[0, "202609"] = 4.0

    restored = equipment_count_from_edit_table(edit, "가용", "가용대수")

    assert restored["가용대수"].tolist() == [2.0, 4.0]
    edit.loc[0, "202609"] = -1.0
    with pytest.raises(ValueError, match="0 이상"):
        equipment_count_from_edit_table(edit, "가용", "가용대수")


def test_equipment_count_apply_survives_a_missing_process_month_combo() -> None:
    """원천에 없는 `(공정, 월)` 이 있어도 아무것도 안 고친 적용이 막히지 않는다(09-29 버그 보고).

    원천은 그 달 행이 **없다**(값이 비어 있는 것이 아니다 — 사내 실데이터로 확인). 피벗하면 그
    자리가 빈칸이었고, 적용이 표 전체를 숫자로 다시 검사해 「숫자를 입력해야 합니다」로 멈췄다.
    그 자리는 0 대이고, 편집기를 거쳐 명시적 0 으로 저장된다.
    """
    source = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "공정": ["Process-A", "Process-B"],  # Process-B 는 202608 행이 원래 없다
            "가용대수": [2.0, 3.0],
        }
    )
    edit = equipment_count_to_edit_table(source, "가용", "가용대수")

    assert edit.set_index("공정").loc["Process-B", "202608"] == 0.0
    restored = equipment_count_from_edit_table(edit, "가용", "가용대수")

    by_key = restored.set_index(["공정", "생산계획년월"])["가용대수"]
    assert by_key[("Process-B", 202608)] == 0.0
    assert by_key[("Process-A", 202609)] == 0.0
    assert by_key[("Process-A", 202608)] == 2.0


def test_equipment_count_blank_cell_is_zero_but_text_is_still_refused() -> None:
    """편집표에서 지운 칸·붙여넣은 빈칸은 0 대다. 숫자로 못 읽는 글자는 여전히 막는다."""
    source = pd.DataFrame(
        {"생산계획년월": [202608, 202609], "공정": ["Process-A"] * 2, "가용대수": [2.0, 3.0]}
    )
    edit = equipment_count_to_edit_table(source, "가용", "가용대수").astype({"202609": "object"})
    edit.loc[0, "202609"] = "  "

    restored = equipment_count_from_edit_table(edit, "가용", "가용대수")
    assert restored["가용대수"].tolist() == [2.0, 0.0]

    edit.loc[0, "202609"] = "3대"
    with pytest.raises(ValueError, match="숫자를 입력해야"):
        equipment_count_from_edit_table(edit, "가용", "가용대수")


def _plan_template() -> pd.DataFrame:
    """Pack Code 에 Excel 이 숫자로 읽는 값이 섞인 격자."""
    return pd.DataFrame(
        {
            "Capa Code": ["DEMO-A", "DEMO-B", "DEMO-C"],
            "Pack Code": ["4.00E+02", "007", "3FA"],
            "202608": [10.0, 20.0, 30.0],
        }
    )


def _as_excel_would(value: str) -> str:
    """Excel 이 CSV 를 열었다 다시 복사했을 때 나오는 글자."""
    if value.startswith('="') and value.endswith('"'):
        return value[2:-1]
    try:
        number = float(value)
    except ValueError:
        return value
    return str(int(number)) if number == int(number) else str(number)


def test_download_guards_key_values_excel_would_rewrite() -> None:
    template = _plan_template()

    text = reference_edit_csv_bytes(template, ["Capa Code", "Pack Code"]).decode("utf-8-sig")
    cells = pd.read_csv(io.StringIO(text), dtype="object", keep_default_na=False)

    assert cells["Pack Code"].tolist() == ['="4.00E+02"', '="007"', "3FA"]
    # 손대지 않아도 그대로 돌아오는 값까지 묶으면 파일이 수식투성이가 된다.
    assert cells["Capa Code"].tolist() == ["DEMO-A", "DEMO-B", "DEMO-C"]


def test_paste_survives_excel_leaving_the_guard_unevaluated() -> None:
    """Excel 이 `="…"` 를 수식으로 계산하지 않고 글자 그대로 둔 경우.

    계산하든 안 하든 왕복이 서야 한다. 계산하면 값이 그대로 돌아오고, 계산하지 않으면
    껍데기째 돌아오는데 읽는 쪽이 껍데기를 벗기므로 결과는 같다.
    """
    template = _plan_template()
    key_columns = ["Capa Code", "Pack Code"]
    downloaded = reference_edit_csv_bytes(template, key_columns).decode("utf-8-sig")
    literal = pd.read_csv(io.StringIO(downloaded), dtype="object", keep_default_na=False)

    result = parse_reference_edit_clipboard(
        literal.to_csv(index=False, sep="\t"), template, key_columns, "RQ_PKG_PLAN"
    )

    assert result["Pack Code"].tolist() == ["4.00E+02", "007", "3FA"]


def test_paste_survives_excel_opening_the_downloaded_template() -> None:
    template = _plan_template()
    key_columns = ["Capa Code", "Pack Code"]
    downloaded = reference_edit_csv_bytes(template, key_columns).decode("utf-8-sig")
    # Excel 로 열었다 헤더째 복사한 상태.
    opened = pd.read_csv(io.StringIO(downloaded), dtype="object", keep_default_na=False)
    for column in key_columns:
        opened[column] = opened[column].map(_as_excel_would)

    result = parse_reference_edit_clipboard(
        opened.to_csv(index=False, sep="\t"), template, key_columns, "RQ_PKG_PLAN"
    )

    assert result["Pack Code"].tolist() == ["4.00E+02", "007", "3FA"]


def test_row_mismatch_names_the_value_excel_changed() -> None:
    template = _plan_template()
    key_columns = ["Capa Code", "Pack Code"]
    mangled = template.copy()
    mangled.loc[0, "Pack Code"] = "400"

    with pytest.raises(ValueError) as error:
        parse_reference_edit_clipboard(
            mangled.to_csv(index=False, sep="\t"), template, key_columns, "RQ_PKG_PLAN"
        )

    message = str(error.value)
    assert "누락 1행, 추가 1행" in message
    assert "Pack Code '4.00E+02' → '400'" in message


def test_row_mismatch_lists_keys_when_excel_is_not_the_cause() -> None:
    template = _plan_template()
    changed = template.copy()
    changed.loc[0, "Capa Code"] = "DEMO-Z"

    with pytest.raises(ValueError) as error:
        parse_reference_edit_clipboard(
            changed.to_csv(index=False, sep="\t"),
            template,
            ["Capa Code", "Pack Code"],
            "RQ_PKG_PLAN",
        )

    message = str(error.value)
    assert "Excel" not in message
    assert "Capa Code=DEMO-A" in message
    assert "Capa Code=DEMO-Z" in message


def _na_template() -> pd.DataFrame:
    """`NA` 는 지역 코드다 — pandas 기본값은 이것을 결측으로 바꾼다."""
    return pd.DataFrame(
        {
            "Customer": ["NA", "NULL", "BBS"],
            "Capa Code": ["DEMO-A", "DEMO-B", "DEMO-C"],
            "202608": [10.0, 20.0, 30.0],
        }
    )


def test_paste_reads_na_shaped_keys_as_text() -> None:
    template = _na_template()
    key_columns = ["Customer", "Capa Code"]

    pasted = parse_reference_edit_clipboard(
        template.to_csv(index=False, sep="\t"), template, key_columns, "RQ_PKG_PLAN"
    )

    assert pasted["Customer"].tolist() == ["NA", "NULL", "BBS"]


# --------------------------------------------------- 값 칸 검증 (숫자 아니면 행이 사라진다)


def _paste(template: pd.DataFrame, modified: pd.DataFrame) -> pd.DataFrame:
    return parse_reference_edit_clipboard(
        modified.to_csv(index=False, sep="\t"),
        template,
        ["공정", "양산구분"],
        "RQ_RUN_RATE",
    )


def test_a_non_numeric_value_cell_is_refused_instead_of_deleting_the_row() -> None:
    """숫자로 못 읽는 값은 적용 단계에서 **행을 통째로 지운다.** 그 앞에서 막는다.

    적용은 Wide→Long 복원이고 마지막이 `to_numeric(coerce)` → `dropna` 다. 막지 않으면
    「적용했습니다」만 뜨고 그 경로의 대당 Capa 가 사라져 확보율이 낙관 쪽으로 기운다.
    """
    template = _template()
    modified = template.copy().astype({"202608": "object"})
    modified.loc[0, "202608"] = "12O"

    with pytest.raises(ValueError) as error:
        _paste(template, modified)

    message = str(error.value)
    assert "12O" in message
    assert "사라집니다" in message
    # 어느 행인지 말해 줘야 Excel 에서 찾을 수 있다.
    assert "Process-B" in message


def test_excel_thousand_separators_are_refused_rather_than_guessed() -> None:
    """`1,200` 은 읽을 수 있어 보이지만 받지 않는다.

    쉼표가 천 단위인지 소수점인지는 지역 설정이 정한다. 앱이 골라 주면 그 선택이 화면
    어디에도 남지 않는다.
    """
    template = _template()
    modified = template.copy().astype({"202609": "object"})
    modified.loc[1, "202609"] = "1,200"

    with pytest.raises(ValueError, match="1,200"):
        _paste(template, modified)


def test_a_blank_value_cell_stays_allowed() -> None:
    """빈 칸은 오류가 아니다 — 그 달 행이 없다는 뜻이고 정당한 편집이다."""
    template = _template()
    modified = template.copy().astype({"202608": "object"})
    modified.loc[0, "202608"] = None

    result = _paste(template, modified)

    assert pd.isna(result.loc[0, "202608"])


def test_removed_values_are_counted_so_the_apply_message_can_say_it() -> None:
    """붙여넣기는 격자와 달리 적용 전에 변경 수를 보여 주지 않는다.

    한 열이 통째로 비어 와도 조용히 지나가므로, 적용 뒤에라도 몇 칸이 빠졌는지 알린다.
    """
    template = _template()
    submitted = template.copy().astype({"202608": "object", "202609": "object"})
    submitted.loc[0, "202608"] = None
    submitted.loc[1, "202609"] = "   "

    assert count_removed_values(template, submitted, ["공정", "양산구분"]) == 2
    # 새로 채운 칸은 삭제가 아니다.
    filled = template.copy()
    filled.loc[0, "202608"] = 0.99
    assert count_removed_values(template, filled, ["공정", "양산구분"]) == 0
