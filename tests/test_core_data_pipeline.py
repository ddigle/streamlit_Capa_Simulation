# Purpose: core data pipeline 관련 정상·예외·회귀 동작을 검증한다.

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest

from capa_simulation.io.core_data_source import (
    CoreDataBatch,
    build_source_column_profile,
    core_data_hash,
    load_core_data_contract,
    normalize_core_data,
    read_core_data_csv,
)
from capa_simulation.services.core_data_pipeline import (
    fetch_core_data_dataset,
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


@dataclass(frozen=True)
class _CsvProvider:
    """`CoreDataProvider` 규약을 채우는 최소 CSV 공급자. 운영에는 CSV 공급자가 없다."""

    path: Path

    def fetch(self, simulation_code: str) -> CoreDataBatch:
        return CoreDataBatch(
            simulation_code=simulation_code,
            simulation_name="테스트 시뮬레이션",
            source_type="CSV_CORE_DATA",
            frame=read_core_data_csv(self.path),
        )


def test_csv_adapter_and_dataframe_adapter_share_the_same_pipeline(tmp_path: Path) -> None:
    csv_path = tmp_path / "Core_Data.csv"
    _core_data_row().to_csv(
        csv_path,
        index=False,
        encoding="cp949",
        quoting=csv.QUOTE_NONE,
        escapechar="\\",
    )
    provider = _CsvProvider(csv_path)

    prepared = fetch_core_data_dataset(provider, "SIM-001", _display_order())

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


def test_wf_division_spellings_that_differ_only_in_case_become_one_value_before_derivation() -> (
    None
):
    """P8 — 대소문자·앞뒤 공백만 다른 `WF 구분` 은 파생 경계에서 한 표기로 맞춘다.

    계산의 조인은 표기를 글자 그대로 맞대는 곳(부하량 ↔ `RQ_REQB`, 수율)과 대소문자를 없애고
    맞대는 곳(Dummy·PKG Buffer 판정)이 섞여 있다. 원천 한 벌에 `Core`·`CORE` 가 함께 오면
    `RQ_CHIP_QTY` 가 두 줄이 되어 계획이 두 번 펼쳐지고, 한쪽 표기의 부하량은 경로에 닿지 않는다.
    고르는 표기는 가장 많이 쓰인 것이다(같으면 글자 차례 앞) — 원천 표기를 지어내지 않는다.
    """
    from capa_simulation.services.required_equipment import calculate_required_equipment
    from capa_simulation.services.unit_capacity import calculate_unit_capacity

    source = pd.concat([_core_data_row()] * 3, ignore_index=True)
    source["계획기초정보여부"] = ["Y", "N", "N"]
    source["WF 구분"] = pd.array(["Core", "CORE", " CORE "], dtype="string")
    source["공정"] = pd.array(["Process-A", "Process-B", "Process-C"], dtype="string")

    tables = build_reference_tables(source, _display_order())

    for table_name in (
        "RQ_YLD",
        "RQ_CHIP_QTY",
        "RQ_CHIP_EQ",
        "RQ_UPEH",
        "RQ_LOT_RATIO",
        "RQ_WF_RATIO",
        "RQ_REQB",
    ):
        assert set(tables[table_name]["WF 구분"]) == {"CORE"}, table_name
    assert len(tables["RQ_CHIP_QTY"]) == 1
    unit_capacity = calculate_unit_capacity(
        upeh=tables["RQ_UPEH"],
        run_rate=tables["RQ_RUN_RATE"],
        vital=tables["RQ_VITAL"],
        module=tables["RQ_MODULE"],
        run_day=tables["RQ_RUN_DAY"],
        lot_ratio=tables["RQ_LOT_RATIO"],
        wf_ratio=tables["RQ_WF_RATIO"],
    )
    required = calculate_required_equipment(
        tables["RQ_REQB"],
        tables["RQ_PKG_PLAN"],
        tables["RQ_YLD"],
        tables["RQ_CHIP_QTY"],
        unit_capacity,
    )
    # 세 공정 모두 같은 계획 100 의 부하를 받는다(구분_Chip·수율 1.0). 두 번 펼쳐지지도 않는다.
    assert required["부하량"].tolist() == [100.0, 100.0, 100.0]


def test_a_plan_flag_with_blanks_or_lowercase_still_marks_a_plan_row() -> None:
    """P8 — `계획기초정보여부` 는 앞뒤 공백을 떼고 대문자로 맞춘 뒤 `Y` 를 본다.

    글자 그대로 `Y` 만 보면 ` y ` 로 온 계획 행이 PKG PLAN 에서 말없이 빠진다.
    """
    source = pd.concat([_core_data_row()] * 2, ignore_index=True)
    source["생산계획년월"] = [202608, 202609]
    source["계획기초정보여부"] = pd.array([" y ", "Y"], dtype="string")

    tables = build_reference_tables(source, _display_order())

    assert sorted(tables["RQ_PKG_PLAN"]["생산계획년월"].tolist()) == [202608, 202609]


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


def test_reqb_rows_that_differ_only_in_spelling_are_registered_once() -> None:
    """등록도 계산과 같은 정규화로 경로를 접는다(사내 감사 P4).

    원래 글자 그대로만 접으면 `WF`·`Wafer`, 앞뒤 공백만 다른 행이 둘로 남고, 계산이 그 둘을 같은
    경로로 세어 소요대수가 두 배가 된다. 남는 행은 첫 행의 원래 표기다.
    """
    source = pd.concat([_core_data_row()] * 3, ignore_index=True)
    source["소요기준"] = pd.array(["WF", "Wafer", "WF"], dtype="string")
    source["공정"] = pd.array(["Process-A", "Process-A", " Process-A "], dtype="string")

    reqb = build_reference_tables(source, _display_order())["RQ_REQB"]

    assert reqb[["공정", "소요기준"]].to_dict("records") == [
        {"공정": "Process-A", "소요기준": "WF"}
    ]


def test_a_blank_lent_evaluation_counts_as_zero_lent_equipment() -> None:
    """대여평가가 비면 0 대로 본다 — 가용대수가 보유대수 그대로다(사내 감사 P7).

    `가용대수 = 설비보유 − 설비대여평가` 가 빈 값을 그대로 옮겨 가용대수가 비면 확보율 계산이
    멈추고 설비대수 편집기도 열리지 않는다. 설비대수 편집기는 「빈칸은 0 대」로 읽는다
    (`equipment_count`) — 등록도 같은 규칙이다. 보유대수가 빈 것은 0 으로 보지 않는다.
    """
    source = pd.concat([_core_data_row()] * 2, ignore_index=True)
    source["생산계획년월"] = [202608, 202609]
    source["설비보유"] = [12.0, 12.0]
    source["설비대여평가"] = [2.0, None]

    tables = build_reference_tables(source, _display_order())

    lent = tables["RQ_EQP_LENT"].sort_values("생산계획년월")
    available = tables["RQ_EQP_AVBL"].sort_values("생산계획년월")
    assert lent["설비대여평가"].astype("float64").tolist() == pytest.approx([2.0, 0.0])
    assert available["가용대수"].astype("float64").tolist() == pytest.approx([10.0, 12.0])


def test_a_blank_lent_sibling_does_not_split_own_lent_and_available() -> None:
    """같은 (월, 공정)에 대여평가가 빈 형제 행과 값이 있는 형제 행이 섞이면 값이 있는 행을 쓴다.

    빈 칸을 원천 행에서 먼저 0 으로 메우면 가용대수 형제가 둘 다 값이 되어 보유 12 · 대여 2 인데
    가용 12 를 고를 수 있다. 접은 뒤에 메우므로 세 표가 `보유 − 대여 = 가용` 으로 맞는다.
    """
    source = pd.concat([_core_data_row()] * 2, ignore_index=True)
    source["STEP_SEQ"] = ["P100", "P200"]
    source["설비보유"] = [12.0, 12.0]
    source["설비대여평가"] = [None, 2.0]

    tables = build_reference_tables(source, _display_order())

    assert tables["RQ_EQP_LENT"]["설비대여평가"].astype("float64").tolist() == [2.0]
    assert tables["RQ_EQP_AVBL"]["가용대수"].astype("float64").tolist() == [10.0]


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
