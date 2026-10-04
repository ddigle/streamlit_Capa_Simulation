# Purpose: 편집 RQ Wide 표의 Excel 안전 CSV 양식 내려받기와 붙여넣은 표 검증을 맡는다.

"""Excel-safe CSV template download and pasted-table validation for wide RQ tables."""

from __future__ import annotations

import re

import pandas as pd

from capa_simulation.services.clipboard_table import parse_clipboard_table

# Excel 은 CSV 를 열 때 셀 내용을 **글자로 읽지 않고 해석한다.** 그래서 내려받은 양식을
# Excel 에서 열었다 그대로 복사해 붙여넣는 것만으로 분류 행이 달라진다 — 예를 들어
# `4.00E+02` 는 지수 표기로 보고 숫자 400 으로, `007` 은 7 로 바꾼다. 아래 꼴에 걸리는
# 분류 값은 `="..."` 로 감싸 텍스트임을 명시한다.
#
# **되돌아온 문자열이 달라지는 것만 감싼다.** `579` 처럼 숫자로 읽혀도 다시 `579` 가 되는
# 값까지 감싸면 사람이 텍스트 편집기로 열었을 때 온통 수식뿐인 파일이 된다.
_EXCEL_SCIENTIFIC = re.compile(r"^[+-]?\d+(?:\.\d+)?[eE][-+]?\d+$")
_EXCEL_LEADING_ZERO = re.compile(r"^[+-]?0\d")
_EXCEL_DATE_LIKE = re.compile(r"^\d{1,4}[-/.]\d{1,2}(?:[-/.]\d{1,4})?$")
_EXCEL_LONG_DIGITS = re.compile(r"^\d{12,}$")
# `1.10` 은 1.1 로, `3.0` 은 3 으로 줄어든다. 소수점이 있고 끝이 0 인 것만 해당한다.
_EXCEL_TRAILING_ZERO = re.compile(r"^[+-]?\d+\.\d*0$")
# `=`·`+`·`@` 로 시작하면 수식으로 계산한다. `-` 는 숫자 앞일 때만 안전하다.
_EXCEL_FORMULA = re.compile(r"^[=+@]|^-(?!\d)")
_EXCEL_BOOLEAN = re.compile(r"^(?:TRUE|FALSE)$", re.IGNORECASE)
_EXCEL_GUARDS = (
    _EXCEL_SCIENTIFIC,
    _EXCEL_LEADING_ZERO,
    _EXCEL_DATE_LIKE,
    _EXCEL_LONG_DIGITS,
    _EXCEL_TRAILING_ZERO,
    _EXCEL_FORMULA,
    _EXCEL_BOOLEAN,
)
# 내보낼 때 씌우고 읽을 때 벗기는 껍데기. Excel 은 이것을 「문자열을 돌려주는 수식」으로
# 읽어 값을 손대지 않고, 그 셀을 복사하면 안의 글자만 따라온다.
_TEXT_GUARD = re.compile(r'^="(.*)"$', re.DOTALL)


def excel_text_guard_needed(value: str) -> bool:
    """Excel 이 이 값을 열었다 복사하면 글자가 달라지는가."""
    if not value or '"' in value:
        return False
    return any(pattern.search(value) for pattern in _EXCEL_GUARDS)


def _guard_excel_text(value: object) -> object:
    if not isinstance(value, str) or not excel_text_guard_needed(value):
        return value
    return f'="{value}"'


def strip_excel_text_guard(value: object) -> object:
    """`="..."` 껍데기를 벗긴다. 씌우지 않은 값은 그대로 돌려준다."""
    if not isinstance(value, str):
        return value
    matched = _TEXT_GUARD.match(value.strip())
    return matched.group(1) if matched else value


def reference_edit_csv_bytes(
    data: pd.DataFrame,
    key_columns: list[str] | None = None,
) -> bytes:
    """Encode an editable table as an Excel-friendly UTF-8 CSV.

    `key_columns` 를 주면 그 컬럼의 **Excel 이 바꿔 놓을 값만** 텍스트로 묶는다. 분류 행이
    왕복에서 어긋나면 표 전체를 못 받으므로, 식별에 쓰는 컬럼만 지킨다. 월 수치 컬럼은
    숫자로 읽히는 것이 맞으니 그대로 둔다.
    """
    prepared = data
    if key_columns:
        prepared = data.copy()
        for column in key_columns:
            if column in prepared.columns:
                prepared[column] = prepared[column].map(_guard_excel_text)
    return prepared.to_csv(index=False).encode("utf-8-sig")


def parse_reference_edit_clipboard(
    content: str,
    template: pd.DataFrame,
    key_columns: list[str],
    table_name: str,
) -> pd.DataFrame:
    """Read a header-inclusive Excel clipboard block using the existing table contract."""
    source = parse_clipboard_table(content, table_name)
    return validate_reference_edit_table(source, template, key_columns, table_name)


def validate_reference_edit_table(
    source: pd.DataFrame,
    template: pd.DataFrame,
    key_columns: list[str],
    table_name: str,
) -> pd.DataFrame:
    """Require the same columns and classification rows as the current edit template."""
    source = source.dropna(how="all").reset_index(drop=True)
    expected_columns = [str(column) for column in template.columns]
    source.columns = [str(column).strip() for column in source.columns]
    missing_columns = [column for column in expected_columns if column not in source.columns]
    extra_columns = [column for column in source.columns if column not in expected_columns]
    if missing_columns or extra_columns:
        details: list[str] = []
        if missing_columns:
            details.append(f"양식에는 있는데 붙여넣은 표에 없는 열: {', '.join(missing_columns)}")
        if extra_columns:
            details.append(f"붙여넣은 표에만 있는 열: {', '.join(extra_columns)}")
        raise ValueError(
            f"{table_name} 입력 표의 열이 다운로드 양식과 다릅니다. {' / '.join(details)}. "
            "「CSV 양식 다운로드」로 지금 조회기간의 양식을 다시 받아, 헤더 줄부터 전체를 "
            "복사해 붙여넣으세요."
        )
    result = source.reindex(columns=expected_columns).copy()

    missing_keys = [column for column in key_columns if column not in result.columns]
    if missing_keys:
        raise ValueError(f"{table_name} 입력 표 식별 컬럼이 없습니다: {', '.join(missing_keys)}")
    expected_keys = _normalized_keys(
        template, key_columns, table_name, "다운로드 양식", from_template=True
    )
    uploaded_keys = _normalized_keys(result, key_columns, table_name, "붙여넣은 표")
    duplicated = uploaded_keys.duplicated(key_columns, keep=False)
    if duplicated.any():
        examples = uploaded_keys.loc[duplicated, key_columns].drop_duplicates().head(5)
        raise ValueError(
            f"{table_name} 입력 표에 같은 분류 행이 두 번 이상 있습니다: "
            f"{_key_examples(key_columns, pd.MultiIndex.from_frame(examples), limit=5)}. "
            "중복된 행을 하나만 남기고 다시 붙여넣으세요. 값을 합쳐야 하면 Excel 에서 "
            "먼저 합산한 뒤 한 행으로 붙여넣습니다."
        )

    expected_index = pd.MultiIndex.from_frame(expected_keys[key_columns])
    uploaded_index = pd.MultiIndex.from_frame(uploaded_keys[key_columns])
    missing_rows = expected_index.difference(uploaded_index)
    extra_rows = uploaded_index.difference(expected_index)
    if len(missing_rows) or len(extra_rows):
        raise ValueError(_row_mismatch_message(table_name, key_columns, missing_rows, extra_rows))

    order = expected_keys.copy()
    order["__csv_row_order"] = range(len(order))
    result[key_columns] = uploaded_keys[key_columns]
    result = result.merge(order, on=key_columns, how="left", validate="one_to_one")
    result = (
        result.sort_values("__csv_row_order", kind="stable")
        .drop(columns="__csv_row_order")
        .reindex(columns=expected_columns)
        .reset_index(drop=True)
    )
    assert_numeric_edit_values(result, key_columns, table_name)
    return result


def _is_blank(value: object) -> bool:
    """빈 칸인가. 빈 칸은 오류가 아니라 **그 달 행이 없다**는 뜻이다."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return True
    return isinstance(value, str) and not value.strip()


def assert_numeric_edit_values(
    table: pd.DataFrame,
    key_columns: list[str],
    table_name: str,
) -> None:
    """값 칸이 숫자이거나 비어 있어야 한다. **숫자로 못 읽는 값은 행을 지운다.**

    적용은 Wide→Long 복원이고 그 마지막 줄이
    `to_numeric(errors="coerce")` → `dropna` 다(`capacity_reference_editor.py`). 숫자로 못
    읽는 칸은 결측이 되고 **그 행이 통째로 사라진다.** 오류도 경고도 없이 「적용했습니다」만
    뜨는데, 그 경로는 부하량을 그대로 둔 채 대당 Capa 만 잃어 소요대수가 과소·확보율이
    과대로 기운다. 조용히 낙관 쪽으로 틀리는 종류다.

    격자 편집기는 월 컬럼이 `NumberColumn` 이라 글자를 애초에 받지 않는다. **붙여넣기만
    이 문을 지나므로** 여기서 막는다.

    `1,200` 처럼 읽을 수 있어 보이는 것도 받지 않는다. 쉼표를 천 단위로 볼지 소수점으로
    볼지는 지역 설정이 정하고, 앱이 골라 주면 그 선택이 화면 어디에도 남지 않는다.
    """
    value_columns = [column for column in table.columns if column not in key_columns]
    offenders: list[str] = []
    for column in value_columns:
        for position, value in table[column].items():
            if _is_blank(value):
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                continue
            try:
                float(str(value).strip())
            except ValueError:
                keys = " / ".join(f"{key}={table.at[position, key]}" for key in key_columns)
                offenders.append(f"{column} 칸 '{value}' ({keys})")
                if len(offenders) >= 5:
                    break
        if len(offenders) >= 5:
            break
    if not offenders:
        return
    raise ValueError(
        f"{table_name} 입력 표의 값 칸에 숫자로 읽을 수 없는 값이 있습니다: "
        f"{'; '.join(offenders)}. 그대로 적용하면 **그 행이 계산에서 사라집니다.** "
        "Excel 에서 천 단위 쉼표(`1,200`)·지수 표기(`1.2E+03`)·`-`·`N/A` 를 지우고 "
        "숫자만 남기세요. 그 달에 값이 없어야 하면 칸을 **비워** 두세요."
    )


def count_removed_values(
    template: pd.DataFrame,
    submitted: pd.DataFrame,
    key_columns: list[str],
) -> int:
    """양식에는 값이 있는데 붙여넣은 표에서는 빈 칸이 된 자리 수.

    **오류가 아니다** — 그 달을 지우는 것은 정당한 편집이다. 다만 붙여넣기는 격자와 달리
    적용 전에 변경 수를 보여 주지 않아(`month_editor.count_month_changes` 는 격자 표만
    센다) 한 열이 통째로 비어 온 것도 조용히 지나간다. 적용 뒤 문구로 알린다.
    """
    value_columns = [
        column
        for column in template.columns
        if column not in key_columns and column in submitted.columns
    ]
    if not value_columns or len(template) != len(submitted):
        return 0
    removed = 0
    for column in value_columns:
        before = template[column].map(_is_blank).to_numpy()
        after = submitted[column].map(_is_blank).to_numpy()
        removed += int((~before & after).sum())
    return removed


def _row_mismatch_message(
    table_name: str,
    key_columns: list[str],
    missing_rows: pd.MultiIndex,
    extra_rows: pd.MultiIndex,
) -> str:
    """분류 행이 갈렸을 때 **어느 값이** 갈렸는지까지 적는다.

    건수만 적으면 사용자가 원인을 알 방법이 없다. 실제로 이 오류의 대부분은 Excel 이 분류
    값을 숫자로 바꿔 놓은 것이라, 없어진 값과 새로 생긴 값을 짝지어 보여 주면 화면에서 바로
    읽힌다. 짝이 지어지면 그 사실을 먼저 말하고, 아니면 양쪽 예시만 적는다.
    """
    lines = [
        f"{table_name} 입력 표의 분류 행은 다운로드 양식과 같아야 합니다: "
        f"누락 {len(missing_rows):,}행, 추가 {len(extra_rows):,}행."
    ]
    coerced = _excel_coercion_pairs(key_columns, missing_rows, extra_rows)
    if coerced:
        changes = ", ".join(
            f"{column} '{before}' → '{after}'" for column, before, after in coerced[:5]
        )
        lines.append(
            f"Excel 이 값을 바꾼 것으로 보입니다 — {changes}. "
            "내려받은 양식을 Excel 에서 열지 말고 그대로 붙여넣거나, "
            "열어야 하면 가져오기에서 해당 열을 '텍스트' 로 지정하세요."
        )
    else:
        if len(missing_rows):
            lines.append(f"누락 예: {_key_examples(key_columns, missing_rows)}")
        if len(extra_rows):
            lines.append(f"추가 예: {_key_examples(key_columns, extra_rows)}")
    return " ".join(lines)


def _key_examples(key_columns: list[str], rows: pd.MultiIndex, limit: int = 3) -> str:
    return "; ".join(
        ", ".join(f"{column}={value}" for column, value in zip(key_columns, row, strict=True))
        for row in list(rows)[:limit]
    )


def _excel_coercion_pairs(
    key_columns: list[str],
    missing_rows: pd.MultiIndex,
    extra_rows: pd.MultiIndex,
) -> list[tuple[str, str, str]]:
    """없어진 키와 새로 생긴 키를 **한 칸만 다른 짝**으로 맞춰 본다.

    Excel 은 셀 하나를 바꿀 뿐 행을 옮기지 않는다. 그래서 짝이 되는 두 키는 나머지 칸이
    모두 같고 한 칸만 다르다. 그 한 칸이 「숫자로 읽으면 같은 값」이면 Excel 의 변환이다.
    """
    pairs: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for before_row in missing_rows:
        for after_row in extra_rows:
            differing = [
                index
                for index, (before, after) in enumerate(zip(before_row, after_row, strict=True))
                if before != after
            ]
            if len(differing) != 1:
                continue
            position = differing[0]
            before_value = str(before_row[position])
            after_value = str(after_row[position])
            if not _reads_as_same_number(before_value, after_value):
                continue
            change = (key_columns[position], before_value, after_value)
            if change not in seen:
                seen.add(change)
                pairs.append(change)
    return pairs


def _reads_as_same_number(before: str, after: str) -> bool:
    try:
        return float(before) == float(after)
    except (TypeError, ValueError):
        return False


def _normalized_keys(
    data: pd.DataFrame,
    key_columns: list[str],
    table_name: str,
    label: str,
    *,
    from_template: bool = False,
) -> pd.DataFrame:
    # `label` 은 화면에 적는 이름이고 `from_template` 은 처방을 가르는 값이다. 둘을 한
    # 변수로 겸하면 라벨을 다듬는 순간 처방이 조용히 뒤집힌다.
    result = data[key_columns].copy()
    for column in key_columns:
        # 내보낼 때 씌운 `="..."` 껍데기를 벗긴다. Excel 을 거치면 껍데기 없이 값만
        # 돌아오지만, 내려받은 파일을 그대로 올리는 길도 막지 않아야 한다.
        result[column] = result[column].map(strip_excel_text_guard).astype("string").str.strip()
    blank_columns = [
        column
        for column in key_columns
        if result[column].isna().any() or result[column].eq("").any()
    ]
    if blank_columns:
        # 비어 있는 쪽이 다운로드 양식이면 붙여넣기로 고칠 수 있는 것이 아니다. 같은
        # 문장으로 안내하면 사용자가 고칠 수 없는 일을 하라고 시키는 꼴이 된다.
        action = (
            "이 양식은 붙여넣기로 고칠 수 없습니다. 기준정보를 다시 조회·저장하세요."
            if from_template
            else "빈 칸을 채우거나 그 행을 지우고 다시 붙여넣으세요."
        )
        raise ValueError(
            f"{table_name} {label}에 분류 칸({', '.join(blank_columns)})이 비어 있는 행이 "
            f"있습니다. {action}"
        )
    return result
