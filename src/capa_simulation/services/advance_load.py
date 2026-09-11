# Purpose: 공용 선행 투입 물량 프로필의 값 정규화와 월별 Capa 부하 변동률 산출을 담당한다.

"""선행 투입 물량과 그것이 만드는 Capa 부하 변동률.

월별 계획은 Guide 기준의 출하·투입 필요 수량이다. 실제 운영에서는 Capa 여유만큼 Wafer 를
더 투입해 Guide 이상을 달성하고, 그만큼 이후 구간의 투입은 줄어든다. 그 가감분을 월별
억Gb 로 받아(앞당겨 투입한 달은 +, 그 때문에 줄어드는 달은 −) 계획과 확보율에 반영한다.

셈은 한 줄이다.

    변동률 = 기존 계획 ÷ 선행 반영 계획
    선행 반영 계획  = 기존 계획 + 선행 물량
    선행 감안 확보율 = 확보율 × 변동률
    선행 감안 Wafer 계획 = Wafer 계획 ÷ 변동률

이렇게 두면 `계획 × 확보율` 로 구하는 Capa 는 정확히 그대로다. 선행 투입은 물량을 앞으로
옮긴 것이지 설비를 늘린 것이 아니므로 Capa 가 움직이면 안 된다. 계획이 늘고 줄어드는 만큼
확보율만 반비례로 움직인다.

변동률은 **화면이 지금 쓰고 있는 계획**을 기준으로 잰다. EDP 를 뺀 화면이면 뺀 계획이
기준이다. 그래야 어느 상태에서든 Capa 가 그대로이고, Density 의 증감이 입력한 선행 물량과
정확히 같아진다 — 사용자가 넣은 숫자를 화면에서 그대로 확인할 수 있어야 한다.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

ADVANCE_LOAD_COLUMNS = ("생산계획년월", "선행 물량")

# 표의 구분 칸에 적는 이름. 입력 시트와 안내 문구가 같은 낱말을 써야 한다.
ADVANCE_LOAD_ROW_LABEL = "선행 물량"


def empty_advance_load() -> pd.DataFrame:
    """아직 아무것도 넣지 않은 정상 상태의 빈 프레임."""
    return pd.DataFrame(
        {
            "생산계획년월": pd.Series(dtype="int64"),
            "선행 물량": pd.Series(dtype="float64"),
        }
    )


def prepare_advance_load(frame: pd.DataFrame) -> pd.DataFrame:
    """저장·계산 공용 정규화. 0 과 결측은 '넣지 않은 달' 이라 지운다.

    0 을 남겨 두면 변동률이 1 인 행이 쌓여 저장본이 조회기간만큼 커지고, 그 달에 선행을
    **지정했다**는 뜻으로 읽힌다. 지정하지 않은 것과 0 을 지정한 것은 결과가 같으므로
    구분해 둘 이유가 없다.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("선행 물량은 pandas DataFrame이어야 합니다.")
    missing = [column for column in ADVANCE_LOAD_COLUMNS if column not in frame.columns]
    extra = [column for column in frame.columns if column not in ADVANCE_LOAD_COLUMNS]
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"누락: {', '.join(missing)}")
        if extra:
            details.append(f"추가: {', '.join(str(column) for column in extra)}")
        raise ValueError(f"선행 물량 컬럼 계약이 일치하지 않습니다 ({'; '.join(details)}).")
    if frame.empty:
        return empty_advance_load()
    prepared = frame.loc[:, list(ADVANCE_LOAD_COLUMNS)].copy()
    prepared["생산계획년월"] = pd.to_numeric(prepared["생산계획년월"], errors="coerce")
    prepared["선행 물량"] = pd.to_numeric(prepared["선행 물량"], errors="coerce")
    prepared = prepared.dropna(subset=["생산계획년월"])
    prepared["생산계획년월"] = prepared["생산계획년월"].astype("int64")
    invalid_month = ~prepared["생산계획년월"].mod(100).between(1, 12)
    if invalid_month.any():
        examples = sorted({int(value) for value in prepared.loc[invalid_month, "생산계획년월"]})[:5]
        raise ValueError(f"생산계획년월이 YYYYMM 형식이 아닙니다: {', '.join(map(str, examples))}")
    duplicated = prepared["생산계획년월"].duplicated()
    if duplicated.any():
        examples = sorted({int(value) for value in prepared.loc[duplicated, "생산계획년월"]})[:5]
        raise ValueError(f"같은 달이 두 번 들어 있습니다: {', '.join(map(str, examples))}")
    prepared["선행 물량"] = prepared["선행 물량"].fillna(0.0).astype("float64")
    prepared = prepared.loc[prepared["선행 물량"].ne(0.0)]
    return prepared.sort_values("생산계획년월").reset_index(drop=True)


def merge_advance_load_edits(
    stored: pd.DataFrame,
    months: Sequence[int],
    values: Sequence[float],
) -> pd.DataFrame:
    """화면에 보인 달만 갈아 끼우고 나머지 저장분은 그대로 둔다.

    조회기간이 좁혀져 있으면 표에 없는 달이 저장본에 남아 있다. 통째로 교체하면 그 달의
    입력을 누른 사람이 모르는 새 날린다. 보이지 않는 것을 지우지 않는다.
    """
    if len(months) != len(values):
        raise ValueError("선행 물량 입력의 월 수와 값 수가 다릅니다.")
    merged = {
        int(month): float(value)
        for month, value in zip(
            prepare_advance_load(stored)["생산계획년월"],
            prepare_advance_load(stored)["선행 물량"],
            strict=True,
        )
    }
    for month, value in zip(months, values, strict=True):
        numeric = pd.to_numeric(value, errors="coerce")
        merged[int(month)] = 0.0 if pd.isna(numeric) else float(numeric)
    return prepare_advance_load(
        pd.DataFrame({"생산계획년월": list(merged), "선행 물량": list(merged.values())})
    )


def build_advance_load_ratio(
    monthly_density: pd.DataFrame,
    advance_load: pd.DataFrame,
) -> pd.DataFrame:
    """월별 `선행 물량`·`선행 반영 부하량`·`변동률`.

    반환 프레임은 `monthly_density` 의 달을 모두 갖는다. 선행을 넣지 않은 달은 물량 0 ·
    변동률 1 이라 곱해도 아무것도 바뀌지 않는다.

    선행 반영 계획이 0 이하가 되는 달은 변동률을 낼 수 없다(0 으로 나누거나 부호가
    뒤집힌다). 그 달만 `적용가능=False` 로 두고 변동률 1 을 준다. 계산을 멈추지 않는 것은
    한 달의 과한 입력 때문에 대시보드 전체가 사라지면 어디가 잘못됐는지 볼 수 없기 때문이다.
    """
    required = ["생산계획년월", "부하량"]
    missing = [column for column in required if column not in monthly_density.columns]
    if missing:
        raise ValueError(f"월별 부하량 필수 컬럼이 없습니다: {', '.join(missing)}")
    prepared = prepare_advance_load(advance_load)
    result = monthly_density[required].copy()
    result["생산계획년월"] = pd.to_numeric(result["생산계획년월"], errors="coerce").astype("int64")
    result["부하량"] = pd.to_numeric(result["부하량"], errors="coerce").fillna(0.0)
    result = result.merge(prepared, on="생산계획년월", how="left", validate="one_to_one")
    result["선행 물량"] = result["선행 물량"].fillna(0.0)
    result["선행 반영 부하량"] = result["부하량"] + result["선행 물량"]
    result["적용가능"] = result["선행 반영 부하량"].gt(0) & result["부하량"].gt(0)
    result["변동률"] = 1.0
    applicable = result["적용가능"]
    result.loc[applicable, "변동률"] = (
        result.loc[applicable, "부하량"] / result.loc[applicable, "선행 반영 부하량"]
    )
    result.loc[~applicable, "선행 반영 부하량"] = result.loc[~applicable, "부하량"]
    result.loc[~applicable, "선행 물량"] = 0.0
    return result


def unapplicable_advance_months(ratio: pd.DataFrame) -> list[int]:
    """선행을 넣었지만 계획이 0 이하가 되어 반영하지 못한 달. 화면 경고가 쓴다."""
    if "적용가능" not in ratio.columns:
        raise ValueError("선행 변동률 프레임에 `적용가능` 컬럼이 없습니다.")
    return sorted(int(value) for value in ratio.loc[~ratio["적용가능"], "생산계획년월"])


def apply_advance_to_density(
    monthly_density: pd.DataFrame,
    ratio: pd.DataFrame,
) -> pd.DataFrame:
    """`부하량` 을 선행 반영 부하량으로 갈아 끼운 월별 부하량."""
    result = monthly_density.copy()
    replacement = ratio.set_index("생산계획년월")["선행 반영 부하량"]
    months = pd.to_numeric(result["생산계획년월"], errors="coerce").astype("int64")
    result["부하량"] = months.map(replacement).astype("float64")
    return result


def apply_advance_to_wafer(
    monthly_wafer: pd.DataFrame,
    ratio: pd.DataFrame,
) -> pd.DataFrame:
    """`Wafer 부하량` 을 변동률로 나눈다. Density 와 같은 비율로 함께 움직인다."""
    if "Wafer 부하량" not in monthly_wafer.columns:
        raise ValueError("월별 Wafer 필수 컬럼이 없습니다: Wafer 부하량")
    result = monthly_wafer.copy()
    factor = ratio.set_index("생산계획년월")["변동률"]
    months = pd.to_numeric(result["생산계획년월"], errors="coerce").astype("int64")
    result["Wafer 부하량"] = pd.to_numeric(result["Wafer 부하량"], errors="coerce") / months.map(
        factor
    ).astype("float64")
    return result


def apply_advance_to_securement(
    securement_rate: pd.DataFrame,
    ratio: pd.DataFrame,
) -> pd.DataFrame:
    """그 달의 모든 공정 확보율에 같은 변동률을 곱한다.

    한 달 안에서는 모두 같은 수를 곱하므로 **공정 순위는 바뀌지 않는다.** B/N 공정이
    선행 입력에 따라 갈아 끼워지면 그것은 계산이 아니라 착시다.
    """
    if "확보율" not in securement_rate.columns:
        raise ValueError("확보율 필수 컬럼이 없습니다: 확보율")
    result = securement_rate.copy()
    factor = ratio.set_index("생산계획년월")["변동률"]
    months = pd.to_numeric(result["생산계획년월"], errors="coerce").astype("int64")
    result["확보율"] = pd.to_numeric(result["확보율"], errors="coerce") * months.map(factor).astype(
        "float64"
    )
    return result
