# Purpose: core data pipeline 관련 정상·예외·회귀 동작을 검증한다.

import csv
from pathlib import Path

import pandas as pd
import pytest

from capa_simulation.io.core_data_source import (
    CoreDataBatch,
    CsvCoreDataProvider,
    build_source_column_profile,
    core_data_hash,
    load_core_data_contract,
    normalize_core_data,
)
from capa_simulation.services.core_data_pipeline import (
    prepare_core_data_dataset,
    reference_conflicts_to_csv,
    summarize_reference_conflicts,
)
from capa_simulation.services.reference_transformer import build_reference_tables


def _core_data_row() -> pd.DataFrame:
    contract = load_core_data_contract()
    values: dict[str, object] = {
        column.name: (
            "기준값" if column.dtype == "string" else 1 if column.dtype == "integer" else 1.0
        )
        for column in contract.columns
    }
    values.update(
        {
            "시뮬레이션 ID": "SIM-001",
            "PLAN ID": "PLAN-001",
            "생산계획년월": 202608,
            "제품정보": "Product-A",
            "생산수량": 100.0,
            "Stack": "8H",
            "Customer": "Customer-A",
            "CS": "MP",
            "WF 구분": "Core",
            "Capa Code": "C1",
            "계획기초정보여부": "Y",
            "Area_Name": "Main",
            "공정": "Process-A",
            "소요기준": "CHIP",
            "STEP_SEQ": "P100",
            "MCP_SEQ": "1A",
        }
    )
    return pd.DataFrame([values], columns=[column.name for column in contract.columns])


def _display_order() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "페이지 구분": ["HOME"],
            "탭 구분": ["계획"],
            "정렬우선순위": [1],
            "분류컬럼": ["제품정보"],
            "정렬방식": ["사용자지정"],
            "분류값": ["Product-A"],
            "값표시순서": [1],
            "활성여부": ["Y"],
        }
    )


def test_normalize_core_data_applies_exact_nullable_contract() -> None:
    contract = load_core_data_contract()

    normalized = normalize_core_data(_core_data_row(), contract)
    profile = build_source_column_profile(normalized)

    assert list(normalized.columns) == [column.name for column in contract.columns]
    assert len(normalized.columns) == 78
    assert str(normalized["시뮬레이션 ID"].dtype) == "string"
    assert str(normalized["생산계획년월"].dtype) == "Int64"
    assert str(normalized["생산수량"].dtype) == "Float64"
    assert len(profile) == 78
    assert profile["null_count"].sum() == 0


def test_csv_adapter_and_dataframe_adapter_share_the_same_pipeline(tmp_path: Path) -> None:
    csv_path = tmp_path / "Core_Data.csv"
    _core_data_row().to_csv(
        csv_path,
        index=False,
        encoding="cp949",
        quoting=csv.QUOTE_NONE,
        escapechar="\\",
    )
    provider = CsvCoreDataProvider(csv_path, "테스트 시뮬레이션")

    prepared = prepare_core_data_dataset(provider.fetch("SIM-001"), _display_order())

    assert prepared.batch.source_type == "CSV_CORE_DATA"
    assert len(prepared.source_data) == 1
    assert len(prepared.reference_tables) == 16
    assert all(len(frame) == 1 for frame in prepared.reference_tables.values())
    assert prepared.reference_tables["RQ_EQP_AVBL"].loc[0, "가용대수"] == pytest.approx(0.0)


def test_dataframe_batch_does_not_depend_on_csv() -> None:
    batch = CoreDataBatch(
        simulation_code="SIM-001",
        simulation_name="사내 조회 결과",
        source_type="BIGDATAQUERY",
        frame=_core_data_row(),
    )

    prepared = prepare_core_data_dataset(batch, _display_order())

    assert prepared.batch.source_type == "BIGDATAQUERY"
    assert prepared.reference_tables["RQ_PKG_PLAN"].loc[0, "생산수량"] == pytest.approx(100.0)


def test_product_information_marker_is_normalized_before_rq_derivation() -> None:
    source = _core_data_row()
    source.loc[0, "제품정보"] = "Product*_A"

    prepared = prepare_core_data_dataset(
        CoreDataBatch(
            simulation_code="SIM-001",
            simulation_name="사내 조회 결과",
            source_type="BIGDATAQUERY",
            frame=source,
        ),
        _display_order(),
    )

    assert prepared.source_data.loc[0, "제품정보"] == "Product*_A"
    assert prepared.reference_tables["RQ_PKG_PLAN"].loc[0, "제품정보"] == "Product A"
    assert prepared.reference_tables["RQ_REQB"].loc[0, "제품정보"] == "Product A"


def test_product_information_underscores_are_normalized_before_rq_derivation() -> None:
    source = _core_data_row()
    source.loc[0, "제품정보"] = "Product_A__SE"

    prepared = prepare_core_data_dataset(
        CoreDataBatch(
            simulation_code="SIM-001",
            simulation_name="사내 조회 결과",
            source_type="BIGDATAQUERY",
            frame=source,
        ),
        _display_order(),
    )

    assert prepared.source_data.loc[0, "제품정보"] == "Product_A__SE"
    assert prepared.reference_tables["RQ_PKG_PLAN"].loc[0, "제품정보"] == "Product A SE"
    assert prepared.reference_tables["RQ_REQB"].loc[0, "제품정보"] == "Product A SE"


def test_area_name_is_normalized_before_rq_derivation() -> None:
    source = _core_data_row()
    source.loc[0, "Area_Name"] = " MAIN "

    prepared = prepare_core_data_dataset(
        CoreDataBatch(
            simulation_code="SIM-001",
            simulation_name="사내 조회 결과",
            source_type="BIGDATAQUERY",
            frame=source,
        ),
        _display_order(),
    )

    for table_name in ("RQ_UPEH", "RQ_LOT_RATIO", "RQ_WF_RATIO", "RQ_REQB"):
        assert prepared.reference_tables[table_name].loc[0, "Area_Name"] == "Main"


def test_cs_codes_map_to_the_two_production_classes_after_trimming_and_casing() -> None:
    """MP·CS 는 양산, ER 은 ER — 앞뒤 공백·소문자는 맞춘 뒤 대조하고 CS 키도 그 값으로 남긴다."""
    source = pd.concat([_core_data_row()] * 6, ignore_index=True)
    source["생산계획년월"] = [202608, 202609, 202610, 202611, 202612, 202701]
    source["CS"] = ["MP", " cs ", "er", "ER ", "CB", " cb"]

    tables = build_reference_tables(source, _display_order())

    plan = tables["RQ_PKG_PLAN"].sort_values("생산계획년월")
    assert plan["CS"].tolist() == ["MP", "CS", "ER", "ER", "CB", "CB"]
    # `CB` 는 사내 1월 시나리오에 새로 온 코드로 양산이다(2026-09-30 사용자 결정).
    assert plan["양산구분"].tolist() == ["양산", "양산", "ER", "ER", "양산", "양산"]


@pytest.mark.parametrize(
    ("codes", "expected"),
    [
        # 규칙에 없는 새 코드는 코드 이름과 행 수(계획 행 수)를 알린다 — 사내 1월 시나리오의 `CB`
        # 가 이 문구 없이 막혔다(2026-09-30). CB 자체는 이제 규칙에 있다(양산).
        (["MP", "ZX", "ZX"], "`ZX` 2행(계획 2행)"),
        # 빈 CS 도 같은 문구로 알린다.
        (["MP", "", "ER"], "`(빈값)` 1행(계획 1행)"),
    ],
)
def test_an_unmapped_cs_code_is_named_before_any_table_is_built(
    codes: list[str], expected: str
) -> None:
    """예전에는 첫 표 검사에서 「업무 키에 null 또는 빈값이 있습니다: 양산구분」으로만 멈췄다."""
    source = pd.concat([_core_data_row()] * len(codes), ignore_index=True)
    source["생산계획년월"] = [202608 + index for index in range(len(codes))]
    source["CS"] = pd.array(codes, dtype="string")

    with pytest.raises(ValueError, match="양산구분\\(양산·ER\\) 규칙에 없는") as caught:
        build_reference_tables(source, _display_order())

    message = str(caught.value)
    assert expected in message
    assert "MP, CS, CB, ER" in message
    assert "업무 키에 null" not in message


def test_conflicting_business_keys_keep_first_values_and_report_all_tables() -> None:
    source = pd.concat([_core_data_row(), _core_data_row()], ignore_index=True)
    source.loc[1, "생산수량"] = 200.0
    source.loc[1, "EDS_수율"] = 0.8

    prepared = prepare_core_data_dataset(
        CoreDataBatch(
            simulation_code="SIM-001",
            simulation_name="사내 조회 결과",
            source_type="BIGDATAQUERY",
            frame=source,
        ),
        _display_order(),
    )
    conflicts = prepared.reference_conflicts
    summary = summarize_reference_conflicts(conflicts)

    assert prepared.reference_tables["RQ_PKG_PLAN"].loc[0, "생산수량"] == pytest.approx(100.0)
    assert prepared.reference_tables["RQ_YLD"].loc[0, "EDS_수율"] == pytest.approx(1.0)
    assert conflicts["RQ테이블"].tolist() == ["RQ_PKG_PLAN", "RQ_YLD"]
    assert conflicts["선택원천행번호"].tolist() == [1, 1]
    assert conflicts["후보원천행번호"].tolist() == ["1 | 2", "1 | 2"]
    assert conflicts["임시제외행수"].tolist() == [1, 1]
    assert summary[["RQ테이블", "충돌 업무키 그룹수"]].to_dict("records") == [
        {"RQ테이블": "RQ_PKG_PLAN", "충돌 업무키 그룹수": 1},
        {"RQ테이블": "RQ_YLD", "충돌 업무키 그룹수": 1},
    ]
    csv_bytes = reference_conflicts_to_csv(conflicts)
    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    assert "RQ_PKG_PLAN" in csv_bytes.decode("utf-8-sig")


def test_exact_duplicate_business_keys_are_removed_without_conflict_report() -> None:
    source = pd.concat([_core_data_row(), _core_data_row()], ignore_index=True)

    prepared = prepare_core_data_dataset(
        CoreDataBatch(
            simulation_code="SIM-001",
            simulation_name="사내 조회 결과",
            source_type="BIGDATAQUERY",
            frame=source,
        ),
        _display_order(),
    )

    assert len(prepared.reference_tables["RQ_PKG_PLAN"]) == 1
    assert prepared.reference_conflicts.empty


def test_route_sequences_distinguish_step_specific_capacity_references() -> None:
    source = pd.concat([_core_data_row(), _core_data_row()], ignore_index=True)
    source.loc[1, "STEP_SEQ"] = "P200"
    source.loc[1, "MCP_SEQ"] = "2A"
    source.loc[1, "UPEH"] = 2.0
    source.loc[1, "Lot 측정률"] = 0.8
    source.loc[1, "WF측정률"] = 0.9

    tables = build_reference_tables(source, _display_order())

    assert tables["RQ_UPEH"][["STEP_SEQ", "MCP_SEQ", "UPEH"]].to_dict("records") == [
        {"STEP_SEQ": "P100", "MCP_SEQ": "1A", "UPEH": 1.0},
        {"STEP_SEQ": "P200", "MCP_SEQ": "2A", "UPEH": 2.0},
    ]
    assert len(tables["RQ_LOT_RATIO"]) == 2
    assert len(tables["RQ_WF_RATIO"]) == 2


def test_invalid_month_is_rejected_at_source_boundary() -> None:
    source = _core_data_row()
    source.loc[0, "생산계획년월"] = 202613

    with pytest.raises(ValueError, match="YYYYMM"):
        normalize_core_data(source)


def test_source_hash_ignores_query_row_order_but_preserves_row_multiplicity() -> None:
    first = _core_data_row()
    second = _core_data_row()
    second.loc[0, "시뮬레이션 ID"] = "SIM-002"
    source = normalize_core_data(pd.concat([first, second], ignore_index=True))
    reordered = source.iloc[::-1].reset_index(drop=True)
    duplicated = pd.concat([source, source.iloc[[0]]], ignore_index=True)

    assert core_data_hash(source) == core_data_hash(reordered)
    assert core_data_hash(source) != core_data_hash(duplicated)


def test_source_rows_that_differ_only_by_pack_code_stay_two_plan_rows() -> None:
    """Pack Code 가 업무 키라 등록에서 접히지 않는다. 합산은 계산 계층의 몫이다."""
    source = pd.concat([_core_data_row(), _core_data_row()], ignore_index=True)
    source.loc[1, "Pack Code"] = "PACK-2"
    source.loc[1, "생산수량"] = 72.51

    prepared = prepare_core_data_dataset(
        CoreDataBatch(
            simulation_code="SIM-001",
            simulation_name="사내 조회 결과",
            source_type="BIGDATAQUERY",
            frame=source,
        ),
        _display_order(),
    )

    plan = prepared.reference_tables["RQ_PKG_PLAN"]
    assert len(plan) == 2
    assert sorted(plan["생산수량"]) == [72.51, 100.0]
    assert sorted(plan["Pack Code"]) == ["PACK-2", "기준값"]
    assert "RQ_PKG_PLAN" not in prepared.reference_conflicts["RQ테이블"].tolist()
