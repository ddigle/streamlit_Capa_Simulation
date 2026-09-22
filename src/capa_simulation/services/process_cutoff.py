# Purpose: 공정별 Cut-off 입력 표의 계약을 검증하고 계산이 쓰는 조회 사전을 만든다.

"""공정별 Cut-off 입력 표.

Cut-off 는 「그 공정 이후의 공정~입고(마지막 공정)까지 TAT 누적 합」, 곧 그 공정을
끝낸 물건이 입고되기까지의 표준 납기다. 어떤 달의 생산에 기여하려면 설비가 그만큼
먼저 있어야 하므로, 이 값이 월별 가용대수를 어디로 미는지 정한다
(`services/wd_window.py`).

**지금은 파생값이 아니라 사람이 적는 원장이다.** 저장소에 TAT 컬럼도, 공정 간 선후
관계를 아는 표도 없어서 코드가 스스로 누적 합을 낼 수 없다. 나중에 TAT 가 들어오면
그때 입력값과 계산값을 어떻게 맞출지 정한다.

**이 표에 없는 공정은 월별 가용대수 산출에서 빠진다.** 0 을 적은 것과 아예 없는 것은
다르다 — 0 은 「달력 월 그대로」이고, 없는 것은 「아직 기준을 못 정했으니 세지 말라」다.
조용히 빠지면 화면의 합이 이유 없이 작아 보이므로 부르는 쪽이 빠진 공정을 반드시
드러내야 한다(`missing_cutoff_processes`).

`제품구분` 은 **나중에 제품 축이 붙을 자리**다. 지금은 모든 행이 `ALL_PRODUCTS`(`*`)
이고 화면도 그것만 만든다. 표준 대비 재공 현황에 차수별 표준 Capa 를 넣을 때 같은
공정 안에서 제품별로 Cut-off 가 갈리는데, 키를 미리 열어 두지 않으면 그때 표를 다시
만들어야 한다.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from capa_simulation.services.clipboard_table import parse_clipboard_table
from capa_simulation.services.frame_checks import assert_unique_keys, strip_text_columns
from capa_simulation.services.frame_contracts import require_columns

__all__ = [
    "ALL_PRODUCTS",
    "PROCESS_CUTOFF_COLUMNS",
    "PROCESS_CUTOFF_EDIT_COLUMNS",
    "build_process_cutoff_template",
    "cutoff_lookup",
    "empty_process_cutoff",
    "missing_cutoff_processes",
    "parse_process_cutoff_clipboard",
    "prepare_process_cutoff",
]

ALL_PRODUCTS = "*"
"""`제품구분` 의 기본값. 「이 공정 전체」를 뜻한다."""

PROCESS_CUTOFF_COLUMNS = ["공정", "제품구분", "Cutoff일수", "비고"]
"""저장·조회가 주고받는 전체 컬럼."""

PROCESS_CUTOFF_EDIT_COLUMNS = ["공정", "Cutoff일수", "비고"]
"""화면 편집표가 보이는 컬럼. `제품구분` 은 아직 축이 하나뿐이라 감춘다."""

_MAX_CUTOFF_DAYS = 3650
"""10년. 오타로 자릿수를 더 적은 값을 막는다 — 그런 값은 모든 달을 통째로 밀어 버린다."""


def empty_process_cutoff() -> pd.DataFrame:
    """행이 없는 계약 프레임. 아직 한 번도 저장하지 않은 저장소가 돌려준다."""
    return pd.DataFrame(
        {
            "공정": pd.Series(dtype="string"),
            "제품구분": pd.Series(dtype="string"),
            "Cutoff일수": pd.Series(dtype="float64"),
            "비고": pd.Series(dtype="string"),
        }
    )


def build_process_cutoff_template(processes: Iterable[str]) -> pd.DataFrame:
    """공정 목록으로 빈 입력 표를 만든다. Cut-off 는 0 이 아니라 **비워 둔다.**

    0 은 「달력 월 그대로」라는 뜻이 있는 값이라, 아직 안 정한 자리에 0 을 심으면
    정한 것과 구별되지 않는다.
    """
    names = list(dict.fromkeys(str(process).strip() for process in processes))
    names = [name for name in names if name]
    if not names:
        return empty_process_cutoff()
    return pd.DataFrame(
        {
            "공정": pd.Series(names, dtype="string"),
            "제품구분": pd.Series([ALL_PRODUCTS] * len(names), dtype="string"),
            # `pd.NA` 는 float 시리즈에 못 들어간다(TypeError). 빈 칸은 NaN 으로 둔다.
            "Cutoff일수": pd.Series([float("nan")] * len(names), dtype="float64"),
            "비고": pd.Series([pd.NA] * len(names), dtype="string"),
        }
    )


def parse_process_cutoff_clipboard(
    content: str,
    *,
    known_processes: Iterable[str] | None = None,
) -> pd.DataFrame:
    """머리글을 포함해 Excel 에서 붙여 넣은 Cut-off 표를 읽는다."""
    return prepare_process_cutoff(
        parse_clipboard_table(content, "공정별 Cut-off"),
        known_processes=known_processes,
    )


def prepare_process_cutoff(
    data: pd.DataFrame,
    *,
    known_processes: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Cut-off 입력 표를 정규화하고 계약을 검증한다.

    `제품구분` 컬럼은 없어도 된다 — 화면이 감추고 있어 편집본에 실려 오지 않는다.
    없으면 `ALL_PRODUCTS` 로 채운다.

    `known_processes` 를 주면 그 목록 밖의 공정명을 오류로 막는다. 목록을 아는 것은
    화면이므로 넘기는 것은 페이지의 몫이고, 저장소의 조회 경로는 넘기지 않는다 —
    이미 저장된 값을 되읽을 때 막으면 공정 목록이 달라진 뒤 화면이 영영 열리지 않는다.
    """
    if data.empty:
        # 행이 없으면 검증할 것도 없다. 아직 한 번도 저장하지 않은 저장소와, 화면에서
        # 마지막 행까지 지운 편집본이 이 경로로 들어온다 — 컬럼조차 없을 수 있다.
        return empty_process_cutoff()

    working = data.copy()
    if "제품구분" not in working.columns:
        working["제품구분"] = ALL_PRODUCTS
    if "비고" not in working.columns:
        working["비고"] = pd.NA

    require_columns(working, PROCESS_CUTOFF_COLUMNS, "공정별 Cut-off 표")
    result = working[PROCESS_CUTOFF_COLUMNS].copy()
    result = result.dropna(subset=["공정", "Cutoff일수"], how="all").reset_index(drop=True)
    if result.empty:
        return empty_process_cutoff()

    strip_text_columns(result, ["공정", "제품구분"])
    result["제품구분"] = result["제품구분"].fillna(ALL_PRODUCTS).replace("", ALL_PRODUCTS)
    result["비고"] = result["비고"].astype("string").str.strip()

    blank = result["공정"].isna() | result["공정"].eq("")
    if blank.any():
        raise ValueError(f"공정별 Cut-off 표의 공정이 비어 있습니다: {int(blank.sum())}행")

    days = pd.to_numeric(result["Cutoff일수"], errors="coerce")
    missing = days.isna()
    if missing.any():
        examples = result.loc[missing, "공정"].head(5).tolist()
        raise ValueError(f"공정별 Cut-off 표의 Cutoff일수가 비었거나 숫자가 아닙니다: {examples}")
    if (days < 0).any():
        examples = result.loc[days < 0, "공정"].head(5).tolist()
        raise ValueError(f"Cutoff일수는 음수일 수 없습니다: {examples}")
    if (days > _MAX_CUTOFF_DAYS).any():
        examples = result.loc[days > _MAX_CUTOFF_DAYS, "공정"].head(5).tolist()
        raise ValueError(
            f"Cutoff일수가 {_MAX_CUTOFF_DAYS}일을 넘습니다. 자릿수를 확인하세요: {examples}"
        )
    result["Cutoff일수"] = days.astype("float64")

    assert_unique_keys(result, ["공정", "제품구분"], "공정별 Cut-off 표의 공정·제품구분이")

    if known_processes is not None:
        allowed = {str(process).strip() for process in known_processes}
        unknown = sorted(set(result["공정"].dropna()) - allowed)
        if unknown:
            raise ValueError(f"기준정보에 없는 공정입니다: {unknown[:5]}")

    return result.sort_values(["공정", "제품구분"]).reset_index(drop=True)


def cutoff_lookup(cutoff: pd.DataFrame) -> dict[str, float]:
    """`공정 → Cutoff일수` 사전. 지금은 `제품구분` 이 `*` 인 행만 본다.

    제품 축이 붙으면 이 함수가 `(공정, 제품) → 일수` 로 넓어진다. 부르는 쪽이 사전
    하나만 보도록 지금부터 여기 한 곳에 가둬 둔다.
    """
    if cutoff.empty:
        return {}
    scoped = cutoff.loc[cutoff["제품구분"].fillna(ALL_PRODUCTS).eq(ALL_PRODUCTS)]
    return {
        str(process): float(days)
        for process, days in zip(scoped["공정"], scoped["Cutoff일수"], strict=True)
    }


def missing_cutoff_processes(processes: Iterable[str], cutoff: pd.DataFrame) -> list[str]:
    """설비는 있는데 Cut-off 를 안 적은 공정. **화면이 반드시 드러내야 하는 값이다.**"""
    known = set(cutoff_lookup(cutoff))
    seen = {str(process).strip() for process in processes}
    return sorted(name for name in seen - known if name)
