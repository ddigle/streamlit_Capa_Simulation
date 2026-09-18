# Purpose: 원천 대문자 `TOP` 이 파생·RQ 표·부하량·화면 순서까지 한 줄로 이어지는지 지킨다.

"""원천 표기 그대로의 Core Data 를 한 줄로 흘려 본다.

원천 `WF 구분` 은 대문자 **`TOP`** 이다(2026-09-18 사용자 확인). `Top_e` 는 EDP-TSV 의
그 값을 HBM 의 것과 갈라 보려고 앱이 지어 붙인 이름이다. 코드 상수와 로컬 합성 표본은
읽기 좋은 `Top` 으로 적혀 있어서, 표기를 글자 그대로 맞대어 보던 동안 **표본으로 도는
검사는 전부 통과하는데 운영에서는 아무 일도 일어나지 않는** 상태가 유지됐다.

그래서 이 파일은 상수(`SOURCE_TOP_DIVISION`)를 쓰지 않고 원천 표기인 `TOP` 을 직접
적는다. 상수를 쓰면 대소문자를 보는 검사가 아니게 된다.

고정하는 것은 세 마디다.

1. 파생 경계(`build_q_core_data`)를 지나면 EDP-TSV 의 `TOP` 만 `Top_e` 가 되고, HBM 의
   `TOP` 은 원천 표기 그대로 남는다. 보존되는 원천 스냅샷도 그대로다.
2. 그 이름이 16개 RQ 표와 부하량까지 내려가 **두 제품군이 갈라진 채** 집계된다.
3. 표시순서 규칙을 `Top` 이라고 적어도 원천의 `TOP` 과 파생된 `Top_e` 에 그대로 걸린다.

표본 고유 수치를 계약처럼 단언하지 않는다. 행 수나 표 개수가 아니라 **관계**를 본다 —
갈라졌는가, 순서가 맞는가, 한 이름이 두 제품군에 걸치지 않는가.
"""

import pandas as pd
import pytest
from test_core_data_pipeline import _core_data_row

from capa_simulation.io.core_data_source import CoreDataBatch
from capa_simulation.services.core_data_derivation import build_q_core_data
from capa_simulation.services.core_data_pipeline import prepare_core_data_dataset
from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.display_order_editor import validate_display_order
from capa_simulation.services.frame_contracts import match_key
from capa_simulation.services.load_calculator import build_monthly_volume, calculate_chip_load
from capa_simulation.services.product_type import (
    EDP_PRODUCT_TYPE,
    EDP_TOP_DIVISION,
    HBM_PRODUCT_TYPE,
    WF_DIVISION_COLUMN,
)

# 원천이 싣는 표기. **상수를 import 하지 않는 것이 이 파일의 요점이다** — `product_type` 의
# `SOURCE_TOP_DIVISION` 은 읽기용 `Top` 이라 그것으로 입력을 만들면 대소문자를 보지 못한다.
SOURCE_TOP = "TOP"

EDP_PRODUCT = "EDP-A"
HBM_PRODUCT = "HBM-A"
PLAN_MONTH = 202608
EDS_YIELD = 0.9
BE_YIELD = 0.95

# (제품타입, 제품정보, WF 구분, 생산수량, 구분_Chip)
# 두 제품군이 **같은 원천 이름** `TOP` 을 싣는 것이 이 표의 목적이다. 제품군마다 수량과
# 구분_Chip 을 다르게 두어, 갈라지지 않으면 어느 쪽 값이 이겼는지 드러나게 한다.
_ROWS = (
    (EDP_PRODUCT_TYPE, EDP_PRODUCT, SOURCE_TOP, 300.0, 2.0),
    (EDP_PRODUCT_TYPE, EDP_PRODUCT, "Master", 300.0, 3.0),
    (HBM_PRODUCT_TYPE, HBM_PRODUCT, SOURCE_TOP, 100.0, 4.0),
    (HBM_PRODUCT_TYPE, HBM_PRODUCT, "Core", 100.0, 5.0),
)


def _uppercase_top_source() -> pd.DataFrame:
    """원천 78컬럼 계약을 그대로 갖춘 합성 Core Data.

    계약 전체를 손으로 적는 대신 한 행짜리 시드를 복제해 이 검사가 보는 칸만 덮어쓴다.
    나머지 칸은 시드의 기본값 그대로라 RQ 파생이 업무 키 충돌 없이 지나간다.
    """
    source = pd.concat([_core_data_row()] * len(_ROWS), ignore_index=True)
    source["제품타입"] = pd.Series([row[0] for row in _ROWS], dtype="string")
    source["제품정보"] = pd.Series([row[1] for row in _ROWS], dtype="string")
    source[WF_DIVISION_COLUMN] = pd.Series([row[2] for row in _ROWS], dtype="string")
    source["생산수량"] = pd.Series([row[3] for row in _ROWS], dtype="Float64")
    source["구분_Chip"] = pd.Series([row[4] for row in _ROWS], dtype="Float64")
    source["생산계획년월"] = pd.Series([PLAN_MONTH] * len(_ROWS), dtype="Int64")
    source["EDS_수율"] = pd.Series([EDS_YIELD] * len(_ROWS), dtype="Float64")
    source["BE_수율"] = pd.Series([BE_YIELD] * len(_ROWS), dtype="Float64")
    source["Net Die"] = pd.Series([1_000.0] * len(_ROWS), dtype="Float64")
    return source


def _wf_division_rules(values: list[str]) -> pd.DataFrame:
    """부하량·환산 탭의 `WF 구분` 사용자지정 규칙."""
    return pd.DataFrame(
        {
            "페이지 구분": ["부하량"] * len(values),
            "탭 구분": ["환산"] * len(values),
            "정렬우선순위": [1] * len(values),
            "분류컬럼": [WF_DIVISION_COLUMN] * len(values),
            "정렬방식": ["사용자지정"] * len(values),
            "분류값": values,
            "값표시순서": list(range(1, len(values) + 1)),
            "활성여부": ["Y"] * len(values),
        }
    )


def _prepared() -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """앱이 실제로 지나는 준비 경로. 원천 스냅샷과 RQ 표를 한 번에 돌려준다."""
    prepared = prepare_core_data_dataset(
        CoreDataBatch(
            simulation_code="SIM-TOP",
            simulation_name="원천 표기 검사",
            source_type="BIGDATAQUERY",
            frame=_uppercase_top_source(),
        ),
        # 사람이 읽기 좋은 `Top` 으로 적은 규칙. 원천은 `TOP` 이다.
        _wf_division_rules(["Top", "Core", "Master"]),
    )
    # 표본이 설계대로 갈렸는지 보는 장치다. 계약이 아니라 이 파일의 입력 점검이다 —
    # 충돌이 잡히면 코드가 아니라 위 `_ROWS` 를 고쳐야 한다.
    assert prepared.reference_conflicts.empty
    return prepared.source_data, prepared.reference_tables


def _divisions_of(frame: pd.DataFrame, product: str) -> set[str]:
    return set(frame.loc[frame["제품정보"].eq(product), WF_DIVISION_COLUMN].dropna())


def test_only_the_edp_uppercase_top_is_renamed_at_the_derivation_boundary() -> None:
    """파생 경계 하나가 `TOP` 을 가른다. HBM 쪽은 원천 표기 그대로 남는다."""
    source = _uppercase_top_source()

    core = build_q_core_data(source)

    # 행 순서는 그대로다. EDP 의 `TOP` 한 칸만 갈리고 나머지는 원천 글자 그대로 남는다 —
    # HBM 의 `TOP` 은 읽기 좋은 `Top` 으로도 고치지 않는다.
    assert core[WF_DIVISION_COLUMN].tolist() == [EDP_TOP_DIVISION, "Master", SOURCE_TOP, "Core"]
    assert core["제품타입"].tolist() == [row[0] for row in _ROWS]
    # 원천 스냅샷은 손대지 않는다. 손대면 다시 파생할 근거가 사라진다.
    assert source[WF_DIVISION_COLUMN].tolist() == [row[2] for row in _ROWS]


def test_the_preserved_source_snapshot_keeps_the_uppercase_spelling() -> None:
    """`raw_data.core_data` 로 가는 스냅샷에는 `Top_e` 가 없어야 한다."""
    source_data, _ = _prepared()

    assert set(source_data[WF_DIVISION_COLUMN]) == {SOURCE_TOP, "Master", "Core"}
    assert EDP_TOP_DIVISION not in set(source_data[WF_DIVISION_COLUMN])


def test_every_rq_table_carries_the_split_names() -> None:
    """조인 한쪽만 바뀌면 수율·Chip 이 조용히 안 붙는다. 16개 표가 같은 이름을 봐야 한다."""
    _, tables = _prepared()

    carrying = {
        name: frame
        for name, frame in tables.items()
        if WF_DIVISION_COLUMN in frame.columns and not frame.empty
    }
    assert carrying, "WF 구분 을 싣는 RQ 표가 하나도 없다"
    for name, frame in carrying.items():
        divisions = set(frame[WF_DIVISION_COLUMN].dropna())
        # 두 이름이 **함께** 살아 있어야 한다. 하나로 접히면 갈라 볼 수가 없다.
        assert {SOURCE_TOP, EDP_TOP_DIVISION} <= divisions, name
        if "제품정보" not in frame.columns:
            continue
        assert EDP_TOP_DIVISION in _divisions_of(frame, EDP_PRODUCT), name
        assert SOURCE_TOP in _divisions_of(frame, HBM_PRODUCT), name
        # 어느 제품군도 상대의 Top 이름을 갖지 않는다.
        assert SOURCE_TOP not in _divisions_of(frame, EDP_PRODUCT), name
        assert EDP_TOP_DIVISION not in _divisions_of(frame, HBM_PRODUCT), name


def test_the_display_order_input_is_not_rewritten_by_the_derived_rule() -> None:
    """`Top_e` 규칙은 그릴 때 파생한다. 사용자가 관리하는 입력 표에 끼워 넣지 않는다."""
    _, tables = _prepared()

    stored = tables["RQ_DISPLAY_ORDER"]
    assert EDP_TOP_DIVISION not in set(stored["분류값"].dropna())


def test_the_chip_load_keeps_the_two_product_families_apart() -> None:
    """부하량까지 내려가서도 한 이름이 두 제품군에 걸치지 않는다.

    갈라지기 전에는 두 제품군의 Top 이 **글자까지 같은 `TOP`** 이었다. `WF 구분` 만 축으로
    세운 집계·규칙은 그때 둘을 한 칸에 담는다. 오류는 나지 않고 칸 하나가 두 가지가 된다.
    """
    _, tables = _prepared()

    load = calculate_chip_load(tables["RQ_PKG_PLAN"], tables["RQ_YLD"], tables["RQ_CHIP_QTY"])

    families = load.groupby(WF_DIVISION_COLUMN, dropna=False)["제품정보"].agg(
        lambda names: frozenset(names)
    )
    assert families[EDP_TOP_DIVISION] == frozenset({EDP_PRODUCT})
    assert families[SOURCE_TOP] == frozenset({HBM_PRODUCT})

    # 맞대어 보는 형태에서도 갈라져 있어야 한다. 갈라지기 전에는 양쪽 모두 `top` 이었다.
    edp_keys = set(match_key(load.loc[load["제품정보"].eq(EDP_PRODUCT), WF_DIVISION_COLUMN]))
    hbm_keys = set(match_key(load.loc[load["제품정보"].eq(HBM_PRODUCT), WF_DIVISION_COLUMN]))
    assert edp_keys.isdisjoint(hbm_keys)


def test_each_top_carries_its_own_family_standards() -> None:
    """두 Top 이 한 이름이면 기준정보 조인도 한쪽으로 쏠린다. 각자 제 값으로 계산돼야 한다."""
    _, tables = _prepared()

    load = calculate_chip_load(tables["RQ_PKG_PLAN"], tables["RQ_YLD"], tables["RQ_CHIP_QTY"])
    volumes = dict(zip(load[WF_DIVISION_COLUMN], load["물량"].astype(float), strict=True))

    edp_plan, edp_chip = _ROWS[0][3], _ROWS[0][4]
    hbm_plan, hbm_chip = _ROWS[2][3], _ROWS[2][4]
    assert volumes[EDP_TOP_DIVISION] == pytest.approx(edp_plan * edp_chip / BE_YIELD)
    assert volumes[SOURCE_TOP] == pytest.approx(hbm_plan * hbm_chip / BE_YIELD)


def test_the_monthly_conversion_screen_orders_both_tops_by_a_readable_rule() -> None:
    """화면 규칙은 `Top` 이라고 적혀 있다. 원천의 `TOP` 과 파생된 `Top_e` 에 모두 걸려야 한다.

    안 걸리면 오류도 경고도 없이 그 값만 무한대로 밀려 표 맨 뒤에 선다. 규칙이 없는 것과
    같아지는데 화면에는 흔적이 없다.
    """
    _, tables = _prepared()

    monthly = build_monthly_volume(
        tables["RQ_PKG_PLAN"],
        tables["RQ_YLD"],
        tables["RQ_CHIP_QTY"],
        "Chip",
        detailed=True,
        display_order=_wf_division_rules(["Top", "Core", "Master"]),
    )

    # `Top_e` 는 `Top` 규칙에서 파생돼 바로 다음 자리에 들어간다.
    assert monthly[WF_DIVISION_COLUMN].tolist() == [
        SOURCE_TOP,
        EDP_TOP_DIVISION,
        "Core",
        "Master",
    ]
    # 화면 라벨은 두 제품군을 따로 세운다.
    assert _divisions_of(monthly, EDP_PRODUCT) == {EDP_TOP_DIVISION, "Master"}
    assert _divisions_of(monthly, HBM_PRODUCT) == {SOURCE_TOP, "Core"}


def test_the_rule_order_is_kept_whatever_case_the_rule_is_written_in() -> None:
    """같은 규칙을 원천 표기(`TOP`)로 적어도 결과가 같아야 한다. 표기는 순서를 바꾸지 않는다."""
    data = pd.DataFrame({WF_DIVISION_COLUMN: ["Master", EDP_TOP_DIVISION, SOURCE_TOP, "Core"]})

    as_written = apply_display_order(
        data, _wf_division_rules(["Top", "Core", "Master"]), "부하량", "환산"
    )
    as_source = apply_display_order(
        data, _wf_division_rules(["TOP", "Core", "Master"]), "부하량", "환산"
    )

    assert as_written[WF_DIVISION_COLUMN].tolist() == as_source[WF_DIVISION_COLUMN].tolist()
    assert as_written[WF_DIVISION_COLUMN].tolist() == [
        SOURCE_TOP,
        EDP_TOP_DIVISION,
        "Core",
        "Master",
    ]


@pytest.mark.xfail(
    reason=(
        "저장 시점 검사(`validate_display_order`)는 아직 글자 그대로 맞댄다. "
        "`Top` 이 있는 화면에 사용자가 원천 표기 `TOP` 을 한 줄 더 넣으면 저장은 통과하고, "
        "그 화면을 그릴 때마다 `apply_display_order` 가 중복으로 막아 페이지가 선다."
    ),
    strict=True,
)
def test_the_editor_rejects_two_rules_that_differ_only_in_case() -> None:
    """대소문자만 다른 두 규칙은 **저장할 때** 막아야 한다.

    맞대어 보는 쪽이 대소문자를 없앤 뒤로 `Top` 과 `TOP` 은 같은 값 하나에 걸린다. 그리는
    쪽은 그것을 중복으로 거부하는데 저장하는 쪽은 서로 다른 값으로 보고 받아 준다. 그래서
    사용자는 저장에 성공한 규칙 때문에 화면이 서는 것을 보게 된다 — 고칠 자리를 알려 주는
    것은 저장 시점이지 그리는 시점이 아니다.
    """
    profile = _wf_division_rules(["Top", "TOP", "Core"])

    with pytest.raises(ValueError):
        validate_display_order(profile)


def test_a_case_only_duplicate_stops_the_screen_today() -> None:
    """위 결함이 사용자에게 어떻게 보이는지 남겨 둔다. 저장이 통과하면 그리는 자리가 선다."""
    profile = _wf_division_rules(["Top", "TOP", "Core"])
    data = pd.DataFrame({WF_DIVISION_COLUMN: [SOURCE_TOP, "Core"]})

    with pytest.raises(ValueError, match="사용자지정 값이 중복"):
        apply_display_order(data, profile, "부하량", "환산")
