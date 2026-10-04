# Purpose: 공용 실행 Capa 반영 프로필의 값 정규화와 확보율 증감 적용을 담당한다.

"""실행 Capa 반영 — 기준정보 밖에서 생긴 변수를 확보율에 즉시 얹는다.

시나리오·리비전에 담긴 Capa 기준정보는 그대로 두고, 그 뒤에 생긴 변수(비가동대수 증가로
인한 가용대수 축소, UPEH 실적 부진, 재공 부진)를 **확보율에만** 즉시 반영한다. 리비전을
새로 저장하지 않고 화면에서 바로 보는 것이 목적이다.

셈은 한 줄이고 **퍼센트포인트 차감**이다.

    조정 확보율 = 기준 확보율 + 증감 확보율 / 100

확보율은 이 저장소에서 비율(1.05 = 105%)로 다니고 입력은 퍼센트포인트(-10.0)라 100 으로
나눈다. 비율 곱셈(× 0.9)이 아니다 — 105% 에 -10 을 넣으면 95% 이지 94.5% 가 아니다.

**이 계산은 `확보율 = 가용대수 ÷ 소요대수` 항등식을 깬다.** 조정 사유가 비가동·UPEH·재공
으로 제각각이라 어느 항으로 되돌릴지 코드가 정할 수 없기 때문이다. 그래서 가용대수·소요
대수는 기준정보 값 그대로 두고, 차이의 출처는 화면 hover 가 「실행 반영 ±n%p · 비고」로
밝힌다.
"""

from __future__ import annotations

import pandas as pd

from capa_simulation.services.frame_contracts import require_exact_columns
from capa_simulation.services.process_rename import normalize_process_text

EXECUTION_CAPACITY_COLUMNS = ("생산계획년월", "공정", "증감 확보율", "비고")

# 조정 뒤에도 원래 값을 알아야 증감 영역을 그릴 수 있다. 조정이 한 건도 없어도 이 세
# 컬럼은 항상 만든다 — 있을 때만 만들면 Figure 쪽이 두 갈래가 되어 분기가 늘어난다.
BASELINE_RATE_COLUMN = "기준 확보율"
ADJUSTMENT_COLUMN = "확보율 증감"
NOTE_COLUMN = "실행 비고"

# 확보율이 음수가 되면 막대 길이·순위가 모두 무의미해진다. 0 에서 자르고 그 사실은
# 호출자가 `clamped_execution_adjustments` 로 받아 화면에 알린다.
MIN_ADJUSTED_RATE = 0.0


def empty_execution_capacity() -> pd.DataFrame:
    """아직 아무것도 넣지 않은 정상 상태의 빈 프레임."""
    return pd.DataFrame(
        {
            "생산계획년월": pd.Series(dtype="int64"),
            "공정": pd.Series(dtype="object"),
            "증감 확보율": pd.Series(dtype="float64"),
            "비고": pd.Series(dtype="object"),
        }
    )


def prepare_execution_capacity(frame: pd.DataFrame) -> pd.DataFrame:
    """저장·계산 공용 정규화. 증감 0 과 결측은 '넣지 않은 행' 이라 지운다.

    0 을 남겨 두면 그릴 색 영역도 hover 도 없는 행이 저장본에 쌓이고, 그 달·공정에
    조정을 **지정했다**는 뜻으로 읽힌다. 지정하지 않은 것과 0 을 지정한 것은 화면 결과가
    같으므로 구분해 둘 이유가 없다.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("실행 Capa 반영은 pandas DataFrame이어야 합니다.")
    require_exact_columns(frame.columns, EXECUTION_CAPACITY_COLUMNS, "실행 Capa 반영 컬럼")
    if frame.empty:
        return empty_execution_capacity()
    prepared = frame.loc[:, list(EXECUTION_CAPACITY_COLUMNS)].copy()
    prepared["생산계획년월"] = pd.to_numeric(prepared["생산계획년월"], errors="coerce")
    prepared["증감 확보율"] = pd.to_numeric(prepared["증감 확보율"], errors="coerce")
    # 공정은 원본 코드 기준이다. 화면 표시명(Proc Rename)으로 저장하면 표시명을 바꾸는
    # 순간 매칭이 끊긴다.
    prepared["공정"] = prepared["공정"].map(normalize_process_text)
    prepared["비고"] = prepared["비고"].fillna("").astype("string").fillna("").astype("object")
    prepared = prepared.dropna(subset=["생산계획년월"])
    prepared = prepared.loc[prepared["공정"].ne("")]
    prepared["생산계획년월"] = prepared["생산계획년월"].astype("int64")
    invalid_month = ~prepared["생산계획년월"].mod(100).between(1, 12)
    if invalid_month.any():
        examples = sorted({int(value) for value in prepared.loc[invalid_month, "생산계획년월"]})[:5]
        raise ValueError(f"생산계획년월이 YYYYMM 형식이 아닙니다: {', '.join(map(str, examples))}")
    duplicated = prepared.duplicated(subset=["생산계획년월", "공정"])
    if duplicated.any():
        shown = prepared.loc[duplicated].head(5)
        pairs = [
            f"{int(month)}·{process}"
            for month, process in zip(shown["생산계획년월"], shown["공정"], strict=True)
        ]
        raise ValueError(f"같은 달·공정이 두 번 들어 있습니다: {', '.join(pairs)}")
    prepared["증감 확보율"] = prepared["증감 확보율"].fillna(0.0).astype("float64")
    prepared = prepared.loc[prepared["증감 확보율"].ne(0.0)]
    return prepared.sort_values(["생산계획년월", "공정"]).reset_index(drop=True)


def apply_execution_adjustment(
    securement_rate: pd.DataFrame,
    adjustments: pd.DataFrame,
) -> pd.DataFrame:
    """확보율에 증감을 얹고 `기준 확보율`·`확보율 증감`·`실행 비고` 를 남긴다.

    **조정이 한 건도 없어도 세 컬럼을 만든다.** 뒤의 순위·Figure 가 컬럼 유무로 갈라지지
    않게 하려는 것이다 — 조정 0건이면 증감이 0 이고 `기준 확보율 == 확보율` 이라 그림이
    오늘과 픽셀 단위로 같다.
    """
    result = securement_rate.copy()
    result[BASELINE_RATE_COLUMN] = pd.to_numeric(result["확보율"], errors="coerce")
    result[ADJUSTMENT_COLUMN] = 0.0
    result[NOTE_COLUMN] = ""
    prepared = prepare_execution_capacity(adjustments)
    if prepared.empty:
        return result
    lookup = prepared.set_index(["생산계획년월", "공정"])
    keys = pd.MultiIndex.from_arrays(
        [
            pd.to_numeric(result["생산계획년월"], errors="coerce").astype("Int64"),
            result["공정"].map(normalize_process_text),
        ]
    )
    result[ADJUSTMENT_COLUMN] = (
        lookup["증감 확보율"].reindex(keys).to_numpy(dtype="float64", na_value=0.0)
    )
    notes = lookup["비고"].reindex(keys).to_numpy()
    result[NOTE_COLUMN] = pd.Series(notes, index=result.index).fillna("").astype("object")
    # 퍼센트포인트 → 비율. 확보율은 이 저장소에서 1.05 = 105% 로 다닌다.
    adjusted = result[BASELINE_RATE_COLUMN] + result[ADJUSTMENT_COLUMN] / 100.0
    result["확보율"] = adjusted.clip(lower=MIN_ADJUSTED_RATE)
    return result


def unmatched_execution_adjustments(
    securement_rate: pd.DataFrame,
    adjustments: pd.DataFrame,
) -> pd.DataFrame:
    """계산 결과에 짝이 없어 아무 일도 하지 않는 행.

    공용 프로필이라 다른 시나리오에서는 유효할 수 있으므로 저장은 막지 않는다. 대신
    「넣었는데 화면이 그대로」인 이유를 사용자가 알 수 있게 돌려준다.
    """
    prepared = prepare_execution_capacity(adjustments)
    if prepared.empty:
        return prepared
    available = set(
        zip(
            pd.to_numeric(securement_rate["생산계획년월"], errors="coerce").astype("Int64"),
            securement_rate["공정"].map(normalize_process_text),
            strict=True,
        )
    )
    missed = [
        (month, process) not in available
        for month, process in zip(
            pd.to_numeric(prepared["생산계획년월"], errors="coerce").astype("Int64"),
            prepared["공정"],
            strict=True,
        )
    ]
    return prepared.loc[missed].reset_index(drop=True)


def clamped_execution_adjustments(securement_rate: pd.DataFrame) -> pd.DataFrame:
    """조정 결과가 0 아래로 내려가 잘린 행. `apply_execution_adjustment` 의 결과를 받는다."""
    if BASELINE_RATE_COLUMN not in securement_rate.columns:
        return securement_rate.iloc[0:0]
    raw = securement_rate[BASELINE_RATE_COLUMN] + securement_rate[ADJUSTMENT_COLUMN] / 100.0
    return securement_rate.loc[raw.lt(MIN_ADJUSTED_RATE)].reset_index(drop=True)
