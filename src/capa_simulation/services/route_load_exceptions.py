# Purpose: 선언한 공정의 Wafer 경로 부하량만 산식 id 로 바꿔 끼우는 순수 계산을 둔다.

"""공정별 부하 산출 예외(2026-11-22 사용자 결정 「원천 산식 그대로」).

원천이 어떤 공정의 Wafer 경로 부하를 일반 산식과 다른 식으로 낸다. 그 식은 **산식 id** 로 이
파일에 두고, 어느 공정에 거는지는 **선언**(공정 → 산식 id)으로 받는다. 공정 이름은 코드 · 문서 ·
시험 · 커밋에 두지 않는다 — 공개 저장소다(AGENTS 6장 「공정별 부하 산출 예외」). 새 예외 꼴이
오면 `ROUTE_LOAD_FORMULAS` 에 산식 id 를 더하고 선언으로 건다 — 공정 이름으로 가르는 `if` 를
두지 않는다.

산식 `buffer_x_core_chip` 은 선언 공정의 소요기준 WF 경로 줄 가운데 둘을 바꾼다.

- `Core` 줄 — 부하량 := 같은 부하 키(`WF 구분` 을 뺀 키)의 Buffer Wafer 부하 × 그 제품의 Core
  `구분_Chip`.
- `Top_Dummy` 줄 — 부하량 := 0, 줄은 남긴다. 원천이 그 경로를 WF수 0 줄로 두고, 규칙 사유로 빼면
  PKG 사유 하나만 견주는 자리들을 묶음 비교로 바꿔야 한다.
- 그 밖(`Buffer` · `Top` · `Dummy`) — 그대로.

지키는 것:

- **공정 단위로 건다.** 부하 키에 STEP 이 없어 같은 공정의 STEP 들이 같은 값을 받는다(공정 유효
  Capa 의 원수요 일치 검사 — `weighted_unit_capacity`).
- **경로에 붙은 부하량만 바꾼다.** 부하량 표(`required_equipment._build_loads`) · 경로 없는 계획
  셈 · Wafer 매수 집계(환산 · HOME · 요약 · 제품별 비중 — `calculate_chip_and_wafer_loads` 물량)는
  그대로다.
- **바탕 없음.** Core 줄의 바탕(Buffer Wafer 부하 · Core `구분_Chip` 행)이 없을 때 일반 Core
  부하가 0 이면 0 으로 두고(계획 없는 달 · 변형), 0 보다 클 때만 그 줄을 세는 제외
  (`ROUTE_LOAD_BASIS_MISSING_REASON`)로 돌려준다 — 부하량 칸에 일반 산식 값이 남아 소요대수 밖
  수요 건수에 잡힌다. Buffer 부하나 `구분_Chip` 이 0 인 것은 바탕이 있는 것이라 그대로 0 이다.
- **겹친 바탕도 바탕 없음.** 한 부하 키에 바탕이 둘 이상이면(같은 `WF 구분` 을 두 표기로 적은
  원천) 어느 값을 곱할지 모른다. 멈추지 않고 그 키를 바탕 표에서 빼서, 그 키를 쓰는 Core 줄만 위
  바탕 없음 규칙을 탄다(2026-11-22 사용자 답 Q13). 다른 키의 줄은 그대로다.
- **선언이 비면 아무것도 바꾸지 않는다.**
- **부대공정에는 따라 걸지 않는다.** 공정 이름으로만 고르므로 선언 공정을 따라가는 부대공정은 제
  이름이라 일반 산식이다. 필요하면 그 이름을 선언에 더한다(2026-11-19 사용자 답 Q4 선례).

Streamlit · 세션 · DB 를 모른다. 선언을 저장하고 호출처까지 넘기는 자리는 아직 없다(AGENTS 6장
「공정별 부하 산출 예외」).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Final, NamedTuple

import pandas as pd

from capa_simulation.services.frame_checks import strip_text_columns
from capa_simulation.services.frame_contracts import match_key, scalar_match_key
from capa_simulation.services.load_calculator import CHIP_KEYS
from capa_simulation.services.product_type import (
    BUFFER_DIVISION,
    CORE_DIVISION,
    TOP_DUMMY_DIVISION,
    WF_DIVISION_COLUMN,
)

# 선언 꼴 — 원본 공정명(`RQ_REQB` 의 `공정`) → 산식 id. 저장된 판 이력의 항목을 그대로 넘길 수 있게
# 평범한 사상으로 받는다.
RouteLoadDeclaration = Mapping[str, str]
NO_ROUTE_LOAD_EXCEPTIONS: Final[RouteLoadDeclaration] = MappingProxyType({})

BUFFER_X_CORE_CHIP: Final = "buffer_x_core_chip"
# 산식 id → 사람이 읽는 한 줄. 화면(고르기 · 이력)과 문서가 이 글을 쓴다.
ROUTE_LOAD_FORMULAS: Final[Mapping[str, str]] = MappingProxyType(
    {BUFFER_X_CORE_CHIP: "Core = Buffer Wafer × Core 구분_Chip · Top_Dummy 0"}
)
# 산식마다 바뀌는 줄의 근거 글(`WF 구분` 대조 키 → 글). 적히지 않은 `WF 구분` 은 일반 산식이라
# 근거 글이 없다.
_FORMULA_BASIS: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        BUFFER_X_CORE_CHIP: MappingProxyType(
            {
                scalar_match_key(CORE_DIVISION): "Buffer Wafer × Core 구분_Chip",
                scalar_match_key(TOP_DUMMY_DIVISION): "부하 0",
            }
        )
    }
)

# 바탕 없음의 사유 — 소요대수 경로 쪽 제외 목록
# (`required_equipment.REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR`)에 실린다.
ROUTE_LOAD_BASIS_MISSING_REASON: Final = "부하 예외 바탕 없음"
EXCLUSION_REASON_COLUMN: Final = "제외사유"
# 바탕 표의 값 칸. 나머지 칸이 모두 경로 줄과 잇는 키다.
EXCEPTION_LOAD_COLUMN: Final = "예외 부하량"

_WAFER_BASES: Final = frozenset({"WF", "WAFER"})
_CHIP_VALUE_COLUMN: Final = "구분_Chip"


class RouteLoadExceptionResult(NamedTuple):
    """예외를 건 경로 줄과, 바탕이 없어 소요대수에서 뺄 줄(사유 칸이 붙은 같은 칸)."""

    routes: pd.DataFrame
    excluded: pd.DataFrame


def normalize_route_load_declaration(declaration: RouteLoadDeclaration) -> dict[str, str]:
    """선언을 (공정 대조 키 → 산식 id) 로 줄인다.

    공정 이름은 `scalar_match_key` 로 견준다 — 앞뒤 공백 · 대소문자만 다른 원천 표기에 선언이
    말없이 빗나가지 않게(부대공정 R-01 의 이름 견줌과 같다). 빈 공정 이름, 모르는 산식 id,
    대소문자만 다른 두 이름에 다른 산식은 `ValueError` 다 — 저장된 선언을 이 코드가 모르면
    조용히 일반 산식으로 떨어지지 않고 멈춘다.
    """
    normalized: dict[str, str] = {}
    for process, formula in declaration.items():
        key = scalar_match_key(process)
        if not key:
            raise ValueError("부하 예외 선언에 빈 공정 이름이 있습니다.")
        if formula not in ROUTE_LOAD_FORMULAS:
            raise ValueError(f"부하 예외 선언에 모르는 산식 id 가 있습니다: {formula}")
        if normalized.setdefault(key, formula) != formula:
            raise ValueError("부하 예외 선언에 대소문자만 다른 두 공정이 다른 산식으로 있습니다.")
    return normalized


def route_load_formula(process: object, declaration: RouteLoadDeclaration) -> str | None:
    """공정 하나에 걸린 산식 id. 선언에 없으면 `None`."""
    return normalize_route_load_declaration(declaration).get(scalar_match_key(process))


def route_load_basis(
    process: object,
    wf_division: object,
    basis: object,
    declaration: RouteLoadDeclaration,
) -> str:
    """경로 줄 하나의 부하량 근거 글(공정 Capa 상세 경로 추적 「부하량 근거」 칸).

    선언 공정의 소요기준 WF 줄 가운데 산식이 바꾸는 줄만 글이 있고(`Core` 「Buffer Wafer × Core
    구분_Chip」 · `Top_Dummy` 「부하 0」), 나머지는 일반 산식이라 빈 글이다.
    """
    if str(basis).strip().upper() not in _WAFER_BASES:
        return ""
    formula = route_load_formula(process, declaration)
    if formula is None:
        return ""
    return _FORMULA_BASIS[formula].get(scalar_match_key(wf_division), "")


def route_load_targets(routes: pd.DataFrame, declaration: RouteLoadDeclaration) -> pd.Series:
    """선언 공정의 소요기준 WF 경로 줄(산식이 볼 줄). 행 순서 · 색인은 `routes` 그대로다."""
    normalized = normalize_route_load_declaration(declaration)
    if not normalized or routes.empty:
        return pd.Series(False, index=routes.index, dtype="bool")
    declared = match_key(routes["공정"]).isin(list(normalized)).fillna(False)
    wafer = routes["소요기준"].astype("string").str.strip().str.upper().isin(_WAFER_BASES)
    return (declared & wafer.fillna(False)).astype("bool")


def build_route_load_bases(
    loads: pd.DataFrame, chip_qty: pd.DataFrame, load_keys: Sequence[str]
) -> pd.DataFrame:
    """산식 `buffer_x_core_chip` 의 바탕 — 부하 키(`WF 구분` 뺌)마다 Buffer Wafer 부하 × Core
    `구분_Chip`.

    `loads` 는 소요대수가 경로에 붙이는 부하량 표(`load_keys` + `부하량`)이고 고치지 않는다.
    `chip_qty` 는 원래 `RQ_CHIP_QTY` 다 — 사본에서 키를 다듬는다. 제품을 잇는 키는 `CHIP_KEYS`
    에서, 부하 키는 `load_keys` 에서 `WF 구분` 만 빼서 만든다(업무 키가 넓어지면 따라간다).
    `구분_Chip` 이 빈 Core 행은 바탕이 없는 것으로 본다. 한 부하 키에 바탕이 둘 이상이면(같은
    이름을 두 표기로 적은 원천) 그대로 둘 다 돌려준다 — `apply_route_load_exceptions` 가 그 키를
    빼서 그 키를 쓰는 Core 줄만 바탕 없음으로 본다.
    """
    base_keys = [key for key in load_keys if key != WF_DIVISION_COLUMN]
    product_keys = [key for key in CHIP_KEYS if key != WF_DIVISION_COLUMN]
    is_buffer = loads["소요기준"].astype("string").str.upper().isin(_WAFER_BASES) & match_key(
        loads[WF_DIVISION_COLUMN]
    ).eq(scalar_match_key(BUFFER_DIVISION))
    buffer = loads.loc[is_buffer.fillna(False), [*base_keys, "부하량"]]

    chip = chip_qty[[*CHIP_KEYS, _CHIP_VALUE_COLUMN]].copy()
    strip_text_columns(chip, CHIP_KEYS)
    is_core = match_key(chip[WF_DIVISION_COLUMN]).eq(scalar_match_key(CORE_DIVISION))
    core_chip = chip.loc[is_core.fillna(False), [*product_keys, _CHIP_VALUE_COLUMN]].copy()
    core_chip[_CHIP_VALUE_COLUMN] = pd.to_numeric(core_chip[_CHIP_VALUE_COLUMN], errors="coerce")
    core_chip = core_chip.dropna(subset=[_CHIP_VALUE_COLUMN])

    bases = buffer.merge(core_chip, on=product_keys, how="inner")
    bases[EXCEPTION_LOAD_COLUMN] = bases["부하량"] * bases[_CHIP_VALUE_COLUMN]
    return bases[[*base_keys, EXCEPTION_LOAD_COLUMN]].reset_index(drop=True)


def apply_route_load_exceptions(
    attached: pd.DataFrame,
    exception_loads: pd.DataFrame,
    declaration: RouteLoadDeclaration,
) -> RouteLoadExceptionResult:
    """부하량이 붙은 경로 줄(`required_equipment._attach_loads` 결과)에 선언한 산식을 건다.

    받은 프레임은 고치지 않는다. 돌려주는 `routes` 는 바탕이 없어 뺀 줄을 뺀 사본이고 행 차례는
    그대로다. `excluded` 는 그 뺀 줄(부하량 칸은 일반 산식 값)에 `제외사유` 칸을 더한 것이다. 바탕
    표(`build_route_load_bases`)의 `예외 부하량` 밖 칸이 모두 잇는 키다. 한 키에 바탕이 둘 이상이면
    그 키의 바탕을 모두 버린다 — 그 키를 쓰는 Core 줄은 바탕이 없는 줄과 같다.
    """
    buffer_x_core_chip = {
        process: formula
        for process, formula in normalize_route_load_declaration(declaration).items()
        if formula == BUFFER_X_CORE_CHIP
    }
    targets = route_load_targets(attached, buffer_x_core_chip)
    no_rows = attached.iloc[0:0].assign(**{EXCLUSION_REASON_COLUMN: pd.Series(dtype="object")})
    if not targets.any():
        return RouteLoadExceptionResult(attached, no_rows)

    division = match_key(attached[WF_DIVISION_COLUMN])
    core = targets & division.eq(scalar_match_key(CORE_DIVISION))
    top_dummy = targets & division.eq(scalar_match_key(TOP_DUMMY_DIVISION))
    routes = attached.copy()
    routes.loc[top_dummy, "부하량"] = 0.0
    if not core.any():
        return RouteLoadExceptionResult(routes, no_rows)

    join_keys = [column for column in exception_loads.columns if column != EXCEPTION_LOAD_COLUMN]
    core_keys = routes.loc[core, join_keys]
    needed = exception_loads.merge(core_keys.drop_duplicates(), on=join_keys, how="inner")
    needed = needed.loc[~needed.duplicated(subset=join_keys, keep=False)]
    looked_up = core_keys.merge(needed, on=join_keys, how="left", validate="many_to_one")
    exception_load = pd.Series(
        looked_up[EXCEPTION_LOAD_COLUMN].to_numpy(dtype="float64"), index=core_keys.index
    )
    general_load = pd.to_numeric(routes.loc[core, "부하량"], errors="coerce").fillna(0.0)
    missing = exception_load.isna() & general_load.gt(0)

    routes.loc[core, "부하량"] = exception_load.fillna(0.0)
    excluded = attached.loc[missing.index[missing]].assign(
        **{EXCLUSION_REASON_COLUMN: ROUTE_LOAD_BASIS_MISSING_REASON}
    )
    kept = routes.drop(index=missing.index[missing])
    return RouteLoadExceptionResult(kept, excluded)
