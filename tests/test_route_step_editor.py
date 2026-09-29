# Purpose: route step editor 관련 정상·예외·회귀 동작을 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.reference_consistency import (
    added_performance_keys,
    missing_ratio_rows,
)
from capa_simulation.services.route_step_editor import (
    ROUTE_GROUP_COLUMNS,
    clone_route_step,
    delete_route_step,
    route_step_summary,
)


def _route() -> dict[str, str]:
    return {
        "Area_Name": "Main",
        "공정": "Process-A",
        "양산구분": "양산",
        "제품정보": "Product-A",
        "Stack": "8H",
        "WF 구분": "Core",
        "소요기준": "CHIP",
    }


def _tables(*, include_second_step: bool = True) -> dict[str, pd.DataFrame]:
    route = _route()
    months = [202608, 202609]
    pairs = [("M1", "S1")]
    if include_second_step:
        pairs.append(("M2", "S2"))

    upeh_rows: list[dict[str, object]] = []
    reqb_rows: list[dict[str, object]] = []
    lot_rows: list[dict[str, object]] = []
    wf_rows: list[dict[str, object]] = []
    for month in months:
        for mcp_seq, step_seq in pairs:
            base = {
                "생산계획년월": month,
                **route,
                "MCP_SEQ": mcp_seq,
                "STEP_SEQ": step_seq,
            }
            upeh_rows.append({**base, "UPEH": 100.0, "ST": None})
            ratio_base = {key: value for key, value in base.items() if key != "소요기준"}
            lot_rows.append({**ratio_base, "Lot 측정률": 1.0})
            wf_rows.append({**ratio_base, "WF측정률": 1.0})
            for capa_code, customer, cs in (
                ("C1", "Customer-A", "MP"),
                ("C2", "Customer-B", "ER"),
            ):
                reqb_rows.append(
                    {
                        **base,
                        "Capa Code": capa_code,
                        "Customer": customer,
                        "CS": cs,
                    }
                )
    return {
        "RQ_REQB": pd.DataFrame(reqb_rows),
        "RQ_UPEH": pd.DataFrame(upeh_rows),
        "RQ_LOT_RATIO": pd.DataFrame(lot_rows),
        "RQ_WF_RATIO": pd.DataFrame(wf_rows),
    }


def test_step_count_uses_distinct_mcp_step_pairs_not_demand_variants() -> None:
    summary = route_step_summary(_tables()["RQ_REQB"])

    assert summary["STEP 수"].tolist() == [2, 2]
    assert summary["수요 변형 수"].tolist() == [2, 2]


def test_clone_step_applies_to_every_matching_demand_variant_and_month() -> None:
    tables = _tables()

    changed = clone_route_step(
        tables,
        _route(),
        source_mcp_seq="M1",
        source_step_seq="S1",
        new_mcp_seq="M3",
        new_step_seq="S3",
    )

    assert changed.affected_months == (202608, 202609)
    assert changed.affected_variants == 2
    assert changed.affected_reqb_rows == 4
    for table_name in ("RQ_REQB", "RQ_UPEH", "RQ_LOT_RATIO", "RQ_WF_RATIO"):
        added = changed.replacements[table_name]
        new_rows = added.loc[added["MCP_SEQ"].eq("M3") & added["STEP_SEQ"].eq("S3")]
        assert len(new_rows) == (4 if table_name == "RQ_REQB" else 2)


def test_delete_step_removes_four_table_route_but_keeps_other_steps() -> None:
    cloned = clone_route_step(
        _tables(),
        _route(),
        source_mcp_seq="M1",
        source_step_seq="S1",
        new_mcp_seq="M3",
        new_step_seq="S3",
    )

    deleted = delete_route_step(
        cloned.replacements,
        _route(),
        mcp_seq="M3",
        step_seq="S3",
    )

    assert route_step_summary(deleted.replacements["RQ_REQB"])["STEP 수"].tolist() == [2, 2]
    for table in deleted.replacements.values():
        assert not (table["MCP_SEQ"].eq("M3") & table["STEP_SEQ"].eq("S3")).any()


def test_delete_rejects_last_step_for_each_process_product_route() -> None:
    with pytest.raises(ValueError, match="마지막 STEP"):
        delete_route_step(
            _tables(include_second_step=False),
            {column: _route()[column] for column in ROUTE_GROUP_COLUMNS},
            mcp_seq="M1",
            step_seq="S1",
        )


def _new_step_months(changed_table: pd.DataFrame) -> list[int]:
    new_rows = changed_table.loc[
        changed_table["MCP_SEQ"].eq("M3") & changed_table["STEP_SEQ"].eq("S3")
    ]
    return sorted(int(month) for month in new_rows["생산계획년월"])


def test_clone_step_skips_months_whose_source_has_no_ratio_row() -> None:
    """원본 경로에 측정률 행이 없는 달은 복제를 건너뛴다(결함 2).

    계산은 그 부재를 1.0 으로 가정해 이어 가는데(`unit_capacity._join_reference`) STEP 추가만
    「복제 원본 STEP에 연결된 RQ_LOT_RATIO 행이 없습니다」로 막았다. 복제본도 같은 가정을
    물려받는다 — UPEH 는 두 달 모두 복제하고 Lot 은 원본에 있는 달만 복제한다.
    """
    tables = _tables()
    lot = tables["RQ_LOT_RATIO"]
    tables["RQ_LOT_RATIO"] = lot.loc[
        ~(lot["MCP_SEQ"].eq("M1") & lot["생산계획년월"].eq(202609))
    ].reset_index(drop=True)

    changed = clone_route_step(
        tables,
        _route(),
        source_mcp_seq="M1",
        source_step_seq="S1",
        new_mcp_seq="M3",
        new_step_seq="S3",
    )

    assert _new_step_months(changed.replacements["RQ_UPEH"]) == [202608, 202609]
    assert _new_step_months(changed.replacements["RQ_LOT_RATIO"]) == [202608]
    assert _new_step_months(changed.replacements["RQ_WF_RATIO"]) == [202608, 202609]
    # 복제가 시나리오에 들어간 뒤의 UPEH 적용은 복제 행을 새 경로로 보지 않는다(결함 1 과 맞물림).
    upeh = changed.replacements["RQ_UPEH"]
    assert (
        missing_ratio_rows(
            added_performance_keys(upeh, upeh),
            {name: changed.replacements[name] for name in ("RQ_LOT_RATIO", "RQ_WF_RATIO")},
        )
        == {}
    )


def test_clone_step_finds_ratio_rows_whatever_the_area_name_case() -> None:
    """계산의 조인은 `Area_Name` 대소문자를 접어 맞댄다. 복제도 같은 행을 찾아야 한다.

    건너뛰기(결함 2)가 표기 차이까지 「행 없음」으로 보면, 원본은 실제 측정률로 계산되는데 복제본만
    말없이 1.0 으로 계산된다.
    """
    tables = _tables()
    tables["RQ_LOT_RATIO"]["Area_Name"] = "MAIN"

    changed = clone_route_step(
        tables,
        _route(),
        source_mcp_seq="M1",
        source_step_seq="S1",
        new_mcp_seq="M3",
        new_step_seq="S3",
    )

    lot = changed.replacements["RQ_LOT_RATIO"]
    assert _new_step_months(lot) == [202608, 202609]
    assert set(lot["Area_Name"]) == {"MAIN"}
