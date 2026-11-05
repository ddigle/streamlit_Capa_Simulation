# Purpose: Reusable Streamlit controls for Excel clipboard updates of wide RQ tables.

"""Reusable Streamlit controls for Excel clipboard updates of wide RQ tables."""

from __future__ import annotations

import pandas as pd

from capa_simulation.components.flash import queue_flash
from capa_simulation.components.paste_form import PasteTemplate, refuse_paste, render_paste_form
from capa_simulation.page_bootstrap import bootstrap_error_message
from capa_simulation.services.reference_csv import (
    parse_reference_edit_clipboard,
    reference_edit_csv_bytes,
)


def render_reference_clipboard_form(
    data: pd.DataFrame,
    *,
    table_name: str,
    key_columns: list[str],
    file_name: str,
    key: str,
    min_value: float | None = None,
    max_value: float | None = None,
    integer: bool = False,
    opening: str | None = None,
) -> pd.DataFrame | None:
    """글 칸과 왼쪽 적용 · 오른쪽 양식 줄을 그리고, 적용을 누르면 검증한 표를 돌려준다.

    팝업(`st.dialog`) 안에서 쓴다 — 붙여넣기는 표 위 작업 줄의 「Excel 붙여넣기」 팝업이다
    (2026-09-28·29 사용자 결정). 창 꼴은 공통 부품(`components/paste_form`)이다. 완료 알림은 부르는
    쪽이 정하고, 빈 칸 · 형식 거부는 여기서 알림창으로 낸다(같은 창의 뒤 거부는
    `refuse_paste(key, 글)`). `min_value`·`max_value` 는 같은 표 편집 격자의 하한·상한이고 `integer`
    는 정수 규칙(일수)이다 — 붙여넣은 값도 그 범위를 지난다
    (`reference_csv.assert_edit_value_range`). `opening` 은 창을 연 회차의 알림 글이다(그 표에만
    걸리는 양식 규칙 · 버려지는 편집).
    """
    submit = render_paste_form(
        key,
        text_key=f"{key}_clipboard",
        text_label=f"{table_name} 표 붙여넣기",
        apply_label="붙여넣기 일괄 적용",
        template=PasteTemplate(
            data=reference_edit_csv_bytes(data, key_columns),
            file_name=file_name,
            key=f"{key}_download",
        ),
        opening=opening,
    )
    if submit is None:
        return None
    if not submit.text.strip():
        refuse_paste(key, "적용할 표를 Excel에서 복사해 붙여넣으세요.")
        return None
    try:
        return parse_reference_edit_clipboard(
            submit.text,
            data,
            key_columns,
            table_name,
            min_value=min_value,
            max_value=max_value,
            integer=integer,
        )
    except ValueError as exc:
        refuse_paste(key, bootstrap_error_message(exc))
        return None


def queue_reference_import_flash(key: str, message: str) -> None:
    """적용 성공 알림을 `f"{key}_flash"` 칸에 담는다 — 페이지가 다시 돈 뒤 그 칸이 한 번 그린다.

    담기·꺼내 그리기는 `components/flash.py` 한 길이다(칸 이름만 이 편집기의 꼴로 짓는다).
    """
    queue_flash(f"{key}_flash", message)
