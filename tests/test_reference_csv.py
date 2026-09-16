# Purpose: reference csv 관련 정상·예외·회귀 동작을 검증한다.

import io

import pandas as pd
import pytest

from capa_simulation.services.equipment_count import (
    equipment_count_from_edit_table,
    equipment_count_to_edit_table,
)
from capa_simulation.services.reference_csv import (
    parse_reference_edit_clipboard,
    parse_reference_edit_csv,
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


def test_reference_csv_round_trip_preserves_template_row_order() -> None:
    template = _template()
    modified = template.iloc[::-1].reset_index(drop=True)
    modified.loc[modified["공정"].eq("Process-A"), "202608"] = 0.75

    result = parse_reference_edit_csv(
        reference_edit_csv_bytes(modified),
        template,
        ["공정", "양산구분"],
        "RQ_RUN_RATE",
    )

    assert result["공정"].tolist() == ["Process-B", "Process-A"]
    assert float(result.loc[1, "202608"]) == pytest.approx(0.75)


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


def test_reference_csv_rejects_changed_classification_rows() -> None:
    template = _template()
    changed = template.copy()
    changed.loc[0, "공정"] = "Unknown"

    with pytest.raises(ValueError, match="분류 행"):
        parse_reference_edit_csv(
            reference_edit_csv_bytes(changed),
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


def test_downloaded_template_uploads_without_opening_excel() -> None:
    template = _plan_template()
    key_columns = ["Capa Code", "Pack Code"]

    result = parse_reference_edit_csv(
        reference_edit_csv_bytes(template, key_columns), template, key_columns, "RQ_PKG_PLAN"
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


def test_upload_reads_na_shaped_keys_as_text_like_paste_does() -> None:
    template = _na_template()
    key_columns = ["Customer", "Capa Code"]
    payload = reference_edit_csv_bytes(template, key_columns)

    uploaded = parse_reference_edit_csv(payload, template, key_columns, "RQ_PKG_PLAN")
    pasted = parse_reference_edit_clipboard(
        template.to_csv(index=False, sep="\t"), template, key_columns, "RQ_PKG_PLAN"
    )

    assert uploaded["Customer"].tolist() == ["NA", "NULL", "BBS"]
    assert pasted["Customer"].tolist() == uploaded["Customer"].tolist()
