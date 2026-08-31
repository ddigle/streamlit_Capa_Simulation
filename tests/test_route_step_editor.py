import pandas as pd
import pytest

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
