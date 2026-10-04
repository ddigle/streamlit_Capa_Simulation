# Purpose: 공정 표시명이 화면 표기에만 닿고 왕복 양식·계산 캐시에는 새지 않음을 검증한다.

import ast
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from capa_simulation.components.grouped_monthly_table import build_grouped_monthly_export
from capa_simulation.components.hierarchical_monthly_table import (
    build_hierarchical_monthly_export,
)
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.components.process_labels import process_labels_from_rules
from capa_simulation.services.process_rename import PROCESS_RENAME_COLUMNS
from capa_simulation.services.simulation_cache import build_home_simulation_cache_key

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOME_PAGE = PROJECT_ROOT / "app_pages/home.py"

LABELS = process_labels_from_rules(
    pd.DataFrame([("SAW", "절단")], columns=list(PROCESS_RENAME_COLUMNS)),
    version=3,
)


def _monthly_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["SAW", "MOLD"],
            "202608": [10.0, 20.0],
        }
    )


# ------------------------------------------------------- 화면 표는 표시명을 쓴다


def test_hierarchical_table_shows_the_display_name() -> None:
    from capa_simulation.components.hierarchical_monthly_table import (
        _build_hierarchical_display,
    )

    display = _build_hierarchical_display(
        _monthly_frame(),
        ["공정"],
        LABELS.value_labels(),
    )

    assert display.classification_values[0] == ["절단", "MOLD"]


def test_grouped_table_shows_the_display_name_in_rows_and_subtotals() -> None:
    from capa_simulation.components.grouped_monthly_table import _build_display_rows

    data = pd.DataFrame({"공정": ["SAW"], "제품정보": ["P1"], "202608": [10.0]})

    display = _build_display_rows(
        data,
        ["공정", "제품정보"],
        ["202608"],
        LABELS.value_labels(),
    )

    assert "절단" in display.classification_values[0]
    assert any(value.startswith("절단") for value in display.classification_values[0] if value)


def test_table_values_without_a_mapping_stay_original() -> None:
    from capa_simulation.components.hierarchical_monthly_table import (
        _build_hierarchical_display,
    )

    display = _build_hierarchical_display(_monthly_frame(), ["공정"], None)

    assert display.classification_values[0] == ["SAW", "MOLD"]


# ------------------------------------------------------- 보고용 CSV 는 원본이다


def test_hierarchical_export_never_takes_display_names() -> None:
    """보고용 다운로드는 원본 공정명이다. 사용자 결정 1이 여기 걸린다."""
    export = build_hierarchical_monthly_export(
        _monthly_frame(),
        classification_columns=["공정"],
        column_labels=COLUMN_LABELS,
        decimal_places=0,
    )

    assert export["공정"].tolist() == ["SAW", "MOLD"]
    assert "value_labels" not in build_hierarchical_monthly_export.__code__.co_varnames


def test_grouped_export_never_takes_display_names() -> None:
    export = build_grouped_monthly_export(
        pd.DataFrame({"공정": ["SAW"], "제품정보": ["P1"], "202608": [10.0]}),
        classification_columns=["공정", "제품정보"],
        column_labels=COLUMN_LABELS,
    )

    assert "SAW" in export["공정"].tolist()
    assert "절단" not in export["공정"].tolist()
    assert "value_labels" not in build_grouped_monthly_export.__code__.co_varnames


def test_static_capa_shortfall_csv_never_takes_display_names() -> None:
    """부족 현황은 화면용 프레임과 CSV 프레임이 갈라져 있다. CSV 는 원본 공정명이다."""
    tree = ast.parse((PROJECT_ROOT / "app_pages/static_capa.py").read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_render_shortfall_table"
    )
    labelled = {
        ast.unparse(node.targets[0].value)
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Subscript)
        and "labels." in ast.unparse(node.value)
    }
    download = next(
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("render_csv_download")
    )
    data_argument = next(keyword.value for keyword in download.keywords if keyword.arg == "data")
    exported_frames = {node.id for node in ast.walk(data_argument) if isinstance(node, ast.Name)}

    assert labelled == {"displayed"}
    assert not exported_frames & labelled


def test_bigdataquery_conflict_preview_labels_only_the_screen_copy() -> None:
    """충돌 보고서는 세션에 담긴 한 객체를 CSV 와 화면이 함께 쓴다. 복사본에만 입힌다."""
    source = (
        PROJECT_ROOT / "src/capa_simulation/components/bigdataquery_registration.py"
    ).read_text(encoding="utf-8")
    body = source.split("def _render_reference_conflict_report()")[1]

    assert "reference_conflicts_to_csv(report)" in body
    assert "displayed = report.copy()" in body
    assert "st.dataframe(displayed" in body


def test_round_trip_paste_templates_keep_the_original_process_name() -> None:
    """왕복 CSV·클립보드 양식은 다시 DB 로 들어간다. 여기에 표시명이 새면 안 된다."""
    from capa_simulation.components.reference_csv_tools import (
        render_reference_clipboard_form,
    )
    from capa_simulation.services.weekly_availability_input import (
        build_weekly_availability_template,
    )

    for builder in (render_reference_clipboard_form, build_weekly_availability_template):
        source = Path(builder.__code__.co_filename).read_text(encoding="utf-8")
        assert "process_labels" not in source, builder.__name__
        assert "표시명" not in source, builder.__name__


def test_display_order_and_equipment_paths_never_see_display_names() -> None:
    watched = [
        "src/capa_simulation/services/display_order.py",
        "src/capa_simulation/services/display_order_csv.py",
        "src/capa_simulation/services/display_order_editor.py",
        "src/capa_simulation/services/equipment_csv.py",
        "src/capa_simulation/services/reference_csv.py",
        "src/capa_simulation/persistence/preset_store.py",
        "src/capa_simulation/persistence/equipment_repository.py",
        "app_pages/available_equipment_status.py",
        "app_pages/space_status.py",
        "src/capa_simulation/components/reference_csv_tools.py",
        "src/capa_simulation/components/display_order_management.py",
    ]
    offenders = [
        path
        for path in watched
        if "process_labels" in (PROJECT_ROOT / path).read_text(encoding="utf-8")
    ]

    assert not offenders, f"표시명이 닿으면 안 되는 경로다: {offenders}"


# ------------------------------------------------------- Figure 는 표시명을 쓴다


def _lob_frames() -> dict[str, pd.DataFrame]:
    """LOB 요약 Figure 한 달치 최소 입력. 월 위치는 `monthly_density` 행 수를 따른다."""
    return {
        "monthly_density": pd.DataFrame(
            {"생산계획년월": [202608], "년월": ["26.08"], "부하량": [1.5]}
        ),
        "lob_summary": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "년월": ["26.08"],
                "부하량": [1.5],
                "Wafer 부하량": [12_000.0],
                "Wafer Capa": [11_000.0],
            }
        ),
        "bottleneck_capacity": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "년월": ["26.08"],
                "공정": ["SAW"],
                "확보율": [0.82],
                "B/N Capa": [1.2],
            }
        ),
        "monthly_top5": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "년월": ["26.08"],
                "순위": [1],
                "공정": ["SAW"],
                "확보율": [0.82],
                "Wafer Capa": [11_000.0],
                "B/N Capa": [1.2],
            }
        ),
    }


def _lob_month_figure(labels: object | None) -> object:
    from capa_simulation.components.home_figures import build_lob_summary_figures

    _, month_figure = build_lob_summary_figures(
        **_lob_frames(),
        month_labels=["26.08"],
        secure_threshold=1.095,
        warning_threshold=0.995,
        process_labels=labels,
    )
    return month_figure


def _rotated_annotation_texts(figure: object) -> list[str]:
    """세로로 세운 주석의 문자열. 공정명 주석이 확보율·Wafer Capa 와 함께 여기 섞여 있다.

    Figure 는 `textangle=270` 으로 넣지만 Plotly 가 -90 으로 정규화해 보관한다.
    """
    return [
        str(annotation.text)
        for annotation in figure.layout.annotations
        if annotation.textangle == -90
    ]


def _bottleneck_detail_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "년월": ["26.08"],
            "순위": [1],
            "공정": ["SAW"],
            "확보율": [0.82],
            "가용대수": [10.0],
            "소요대수": [12.0],
            "Wafer Capa": [11_000.0],
        }
    )


def _bottleneck_detail_month_figure(labels: object | None) -> object:
    from capa_simulation.components.home_figures import build_bottleneck_detail_figures

    _, month_figure = build_bottleneck_detail_figures(
        monthly_bottleneck_details=_bottleneck_detail_frame(),
        month_labels=["26.08"],
        secure_threshold=1.095,
        warning_threshold=0.995,
        process_labels=labels,
    )
    return month_figure


def test_lob_top5_process_annotation_shows_the_display_name() -> None:
    texts = _rotated_annotation_texts(_lob_month_figure(LABELS))

    assert "절단" in texts
    assert "SAW" not in texts


def test_lob_top5_process_annotation_stays_original_without_labels() -> None:
    """`process_labels` 를 넘기지 않으면 원본 그대로다."""
    texts = _rotated_annotation_texts(_lob_month_figure(None))

    assert "SAW" in texts
    assert "절단" not in texts


def test_lob_bottleneck_hover_customdata_carries_the_display_name() -> None:
    figure = _lob_month_figure(LABELS)
    bottleneck = next(trace for trace in figure.data if trace.name == "B/N 공정")

    assert [str(value) for value in bottleneck.customdata[0]] == ["26.08", "0.82", "절단"]


def test_lob_top5_hover_customdata_carries_the_display_name() -> None:
    """Top 5 trace 도 같은 매핑을 탄다. 여기만 빠지면 한 Figure 안에서 이름이 갈린다."""
    figure = _lob_month_figure(LABELS)
    top5 = next(trace for trace in figure.data if trace.name == "B/N Capa Top 5")

    assert "절단" in [str(value) for value in top5.customdata[0]]
    assert "SAW" not in [str(value) for value in top5.customdata[0]]


def test_bottleneck_detail_bar_name_and_hover_show_the_display_name() -> None:
    figure = _bottleneck_detail_month_figure(LABELS)
    name_trace = next(trace for trace in figure.data if getattr(trace, "mode", None) == "text")

    # 막대 왼쪽 이름은 글자 크기를 담은 마크업이라 문자열을 안에서 찾는다.
    assert "절단" in name_trace.text[0]
    assert "SAW" not in name_trace.text[0]
    assert "절단" in list(figure.data[0].customdata[0])


def test_bottleneck_detail_stays_original_without_labels() -> None:
    figure = _bottleneck_detail_month_figure(None)
    name_trace = next(trace for trace in figure.data if getattr(trace, "mode", None) == "text")

    assert "SAW" in name_trace.text[0]
    assert "절단" not in name_trace.text[0]
    assert "SAW" in list(figure.data[0].customdata[0])


# ------------------------------------------------------- 위젯 값은 원본이다


def test_column_filter_shows_labels_but_keeps_original_selection_values() -> None:
    script = """
import pandas as pd
import streamlit as st

from capa_simulation.components.column_filter import render_column_filter_controls
from capa_simulation.components.process_labels import process_labels_from_rules

labels = process_labels_from_rules(pd.DataFrame([("SAW", "절단")], columns=["공정", "표시명"]), 1)
data = pd.DataFrame({"공정": ["SAW", "MOLD"], "값": [1, 2]})
filtered = render_column_filter_controls(
    data,
    ["공정"],
    key_prefix="probe",
    value_labels=labels.value_labels(),
)
st.text(",".join(str(value) for value in filtered["공정"].tolist()))
"""
    app = AppTest.from_string(script).run(timeout=30)

    assert not app.exception
    # 화면에는 표시명이 보인다.
    assert app.multiselect[0].options == ["절단", "MOLD"]

    app.multiselect[0].select("절단").run(timeout=30)

    assert not app.exception
    # **세션 저장값과 걸러진 프레임은 원본 공정명이다.** 값을 표시명으로 바꿨다면
    # `isin` 이 원본 컬럼과 맞지 않아 여기가 빈 문자열이 된다.
    assert app.session_state["probe_공정"] == ["SAW"]
    assert app.text[0].value == "SAW"


# ------------------------------------------------------- 캐시 경계


def test_rename_is_not_part_of_the_calculation_cache_key() -> None:
    """계산 캐시 키는 표시명을 모른다. 알면 rename 마다 HOME 전체가 재계산된다."""
    display_order = pd.DataFrame({"분류값": ["A"], "값표시순서": [1]})
    key = build_home_simulation_cache_key(
        reference_version=1,
        scenario_token="token",
        start_month=202601,
        end_month=202612,
        display_order=display_order,
    )

    assert len(key) == 5
    # 하위 Figure 키가 `[-1]` 로 꺼내 쓰는 자리는 표시순서 digest 여야 한다.
    assert isinstance(key[-1], str) and len(key[-1]) == 64
    assert "process" not in build_home_simulation_cache_key.__code__.co_varnames


def _home_figure_cache_arguments() -> dict[str, str]:
    """페이지가 키를 조립하는 근거를 필드명으로 읽는다. 위치에 의존하지 않는다."""
    tree = ast.parse(HOME_PAGE.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "HomeFigureCacheKey"
    ]
    assert len(calls) == 1
    assert not calls[0].args, "캐시 키는 필드명을 명시해 만들어야 합니다."
    return {item.arg: ast.unparse(item.value) for item in calls[0].keywords if item.arg}


def test_home_figure_cache_key_records_the_applied_comparison_not_the_requested_one() -> None:
    """고른 리비전을 키에 적으면 GAP 이 조용히 사라진 그림이 캐시에 눌러앉는다.

    리비전이 지워졌거나 DB 를 잠깐 못 읽으면 비교 없이 그리는데, 그때도 키는 「GAP 켜짐」
    이라 다음 실행에서 DB 가 멀쩡해져도 그 그림이 그대로 나온다.
    """
    arguments = _home_figure_cache_arguments()

    assert arguments["comparison_revision_id"] == "str(applied_comparison_revision_id or '')"
    assert "show_comparison" not in arguments.values()
    assert "str(comparison_revision_id or '')" not in arguments.values()


def test_home_figure_cache_key_includes_the_rename_version_and_display_order_digest() -> None:
    """rename 버전은 Figure 키 원소다. 버전이 바뀔 때만 Figure 가 무효화된다."""
    arguments = _home_figure_cache_arguments()

    assert arguments["process_label_version"] == "process_labels.version"
    assert arguments["display_order_digest"] == "home_simulation_cache_key[-1]"
    assert arguments["content_token"] == "active_scenario['content_token']"


def test_home_figure_cache_key_records_the_applied_key_process_order() -> None:
    """주요공정은 실제 그린 목록과 차례를 보고, 저장 버전도 함께 구분한다."""
    arguments = _home_figure_cache_arguments()

    assert arguments["key_processes"] == "tuple(applied_key_processes)"
    assert arguments["key_process_profile_version"] == "key_process_profile.version"


def test_content_token_is_never_reissued_for_a_rename() -> None:
    """토큰은 편집 14표 내용의 대표값이다. 라벨은 계산 입력이 아니다."""
    sources = [
        PROJECT_ROOT / "src/capa_simulation/components/process_rename_management.py",
        PROJECT_ROOT / "src/capa_simulation/components/process_labels.py",
        PROJECT_ROOT / "src/capa_simulation/persistence/process_rename_store.py",
        PROJECT_ROOT / "src/capa_simulation/services/process_rename.py",
    ]
    offenders = [
        path.name for path in sources if "content_token" in path.read_text(encoding="utf-8")
    ]

    assert not offenders, f"공정 표시명 경로는 content_token 을 건드리지 않는다: {offenders}"


def test_saving_a_rename_does_not_clear_the_revision_snapshot_cache() -> None:
    """표시명은 어떤 RQ 표에도 오버레이되지 않는다. 같이 비우면 16표 재적재가 딸려온다."""
    source = (PROJECT_ROOT / "src/capa_simulation/persistence/cache.py").read_text(encoding="utf-8")
    body = source.split("def clear_global_process_rename_cache()")[1].split("def clear_scenario")[0]

    assert "_load_global_process_rename_payload.clear()" in body
    assert "_load_scenario_snapshot_payload" not in body


# ------------------------------------------- 편집기는 값은 원본, 표시만 표시명


def test_month_editor_dimension_uses_a_selectbox_that_splits_value_and_label() -> None:
    """`SelectboxColumn` 은 옵션의 `value` 와 `label` 을 나눠 갖는다.

    셀에 그려지는 것은 `label`, 편집 결과·복사 데이터로 돌아오는 것은 `value` 다. 그래서
    분류 컬럼의 값이 원본으로 남고 `merge_edited_months` 의 되머지 키가 어긋나지 않는다.
    """
    from capa_simulation.components.month_editor import _dimension_column_config

    config = _dimension_column_config(_monthly_frame(), ["공정"], LABELS.value_labels())
    type_config = config["공정"]["type_config"]

    assert type_config["type"] == "selectbox"
    assert type_config["options"] == [
        {"value": "SAW", "label": "절단"},
        {"value": "MOLD", "label": "MOLD"},
    ]


def test_month_editor_dimension_stays_a_text_column_without_a_mapping() -> None:
    """매핑이 없는 컬럼은 `TextColumn` 이라 원본 공정명이 그대로 보인다."""
    from capa_simulation.components.month_editor import _dimension_column_config

    config = _dimension_column_config(_monthly_frame(), ["공정"], None)

    assert config["공정"]["type_config"]["type"] == "text"
    assert config["공정"]["alignment"] == "center"


def test_month_editor_selectbox_options_cover_every_value_in_the_table() -> None:
    """옵션에 없는 값은 셀이 빈칸으로 그려진다. 표의 값 전체가 옵션이어야 한다."""
    from capa_simulation.components.month_editor import _dimension_column_config

    frame = _monthly_frame()
    config = _dimension_column_config(frame, ["공정"], LABELS.value_labels())
    values = {option["value"] for option in config["공정"]["type_config"]["options"]}

    assert values == set(frame["공정"])


def test_home_process_dialog_buttons_keep_original_callback_and_selection_values() -> None:
    """공정 버튼은 표시명을 그리지만 콜백과 적용 목록은 원본 공정 키를 사용한다.

    값은 원본 `공정` 이어야 한다. 선택값이 세션·프리셋에 저장되고 `isin` 대조에 쓰이므로
    표시명이 들어가면 대시보드가 오류 없이 텅 빈다.
    """
    tree = ast.parse(HOME_PAGE.read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "show_process_filter_dialog"
    )
    body = ast.unparse(function)

    assert "render_process_picker(" in body
    assert "format_func=process_labels.format_func()" in body
    assert "on_toggle=toggle_process_dialog_selection" in body
    assert "st.data_editor" not in body
    assert "[process for process in options if process in selected_set]" in body

    renderer_path = PROJECT_ROOT / "src/capa_simulation/components/process_picker.py"
    renderer = ast.parse(renderer_path.read_text(encoding="utf-8"))
    button = next(
        node
        for node in ast.walk(renderer)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "st.button"
    )
    keywords = {keyword.arg: ast.unparse(keyword.value) for keyword in button.keywords}
    assert ast.unparse(button.args[0]) == "label"
    assert "label = format_func(item.process)" in ast.unparse(renderer)
    assert keywords["on_click"] == "on_toggle"
    assert keywords["args"] == "(item.process,)"
    assert "{item.process}" in keywords["key"]


# ------------------------------------------- Dynamic Capa Figure 는 표시명을 쓴다


def _process_summary() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["SAW", "MOLD"],
            "상태": ["정상", "개선 필요"],
            "Capa 실현률": [0.95, 0.70],
            "설비 성능 실현률": [0.98, 0.80],
        }
    )


def test_dynamic_capacity_comparison_axis_shows_the_display_name() -> None:
    from capa_simulation.components.dynamic_capacity_dashboard import (
        build_process_comparison_figure,
    )

    figure = build_process_comparison_figure(_process_summary(), process_labels=LABELS)

    assert [str(value) for value in figure.data[0].y] == ["MOLD", "절단"]


def test_dynamic_capacity_comparison_axis_stays_original_without_labels() -> None:
    from capa_simulation.components.dynamic_capacity_dashboard import (
        build_process_comparison_figure,
    )

    figure = build_process_comparison_figure(_process_summary())

    assert [str(value) for value in figure.data[0].y] == ["MOLD", "SAW"]
