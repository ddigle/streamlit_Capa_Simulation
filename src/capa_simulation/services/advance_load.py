# Purpose: 공용 선행 B/O 프로필의 값 정규화와 월별 Capa 부하 변동률 산출을 담당한다.

"""선행 B/O 와 그것이 만드는 Capa 부하 변동률.

S.PKG 라인의 FRONT 공정은 B/O(Bond Out — CoW Bonder 스택인 Pre B/D·Post B/D 를 마친 자리)에서
끝난다. **선행 B/O 재공**은 계획보다 앞서 만들어 둔 B/O 재공이다(2026-10-06 사용자 설명). 이 물량은
생산계획에 **들어 있지 않으므로** 그만큼이 설비에 더 걸린 부하다. 그래서 월별 억Gb 로 받아(앞서
만든 달은 +, 그 때문에 줄어드는 달은 −) 계획에 더하고 확보율을 그만큼 낮춘다. 저장 컬럼 이름
`선행 물량` 과 세션 키(`home_show_advance`)는 저장 계약이라 화면 이름이 바뀌어도 그대로 둔다.

**적용 범위.** 원래는 FRONT 공정(B/O 까지)에만 걸려야 한다. 그러나 공정을 FRONT·PKG 로 가르는
분류가 아직 없어(사용자가 나중에 설명한다) 지금은 **모든 공정**에 같은 변동률을 건다. 분류가
생기면 `apply_advance_to_securement` 가 FRONT 공정에만 곱하도록 좁힐 자리다.

선행 **입고**(라인 기준 입고가 계획보다 앞선 것)는 이미 생산계획에 들어 있는 물량이라 계산을
바꾸지 않는다 — 그것은 `services/advance_shipment.py` 가 화면 표시만 맡는다.

셈은 한 줄이다.

    변동률 = 기존 계획 ÷ 선행 반영 계획
    선행 반영 계획  = 기존 계획 + 선행 B/O
    선행 감안 확보율 = 확보율 × 변동률
    선행 감안 Wafer 계획 = Wafer 계획 ÷ 변동률

이렇게 두면 `계획 × 확보율` 로 구하는 Capa 는 정확히 그대로다. 선행 B/O 는 부하를 늘린 것이지
설비를 늘린 것이 아니므로 Capa 가 움직이면 안 된다. 계획이 늘고 줄어드는 만큼 확보율만
반비례로 움직인다.

변동률은 **화면이 지금 쓰고 있는 계획**을 기준으로 잰다. EDP 를 뺀 화면이면 뺀 계획이
기준이다. 그래야 어느 상태에서든 Capa 가 그대로이고, Density 의 증감이 입력한 선행 B/O 와
정확히 같아진다 — 사용자가 넣은 숫자를 화면에서 그대로 확인할 수 있어야 한다.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from capa_simulation.services.frame_contracts import require_columns
from capa_simulation.services.monthly_amount import (
    empty_monthly_amounts,
    merge_monthly_amount_edits,
    prepare_monthly_amounts,
)

# 저장 컬럼(`app_meta.global_advance_load_month`)과 같은 이름이다. 화면 이름(선행 B/O)과 다르다.
ADVANCE_LOAD_VALUE_COLUMN = "선행 물량"
ADVANCE_LOAD_COLUMNS = ("생산계획년월", ADVANCE_LOAD_VALUE_COLUMN)

# 편집 표의 구분 칸에 적는 이름. 토글·편집기 제목과 같은 낱말을 써야 찾을 수 있다.
ADVANCE_LOAD_ROW_LABEL = "선행 B/O"


def empty_advance_load() -> pd.DataFrame:
    """아직 아무것도 넣지 않은 정상 상태의 빈 프레임."""
    return empty_monthly_amounts(ADVANCE_LOAD_VALUE_COLUMN)


def prepare_advance_load(frame: pd.DataFrame) -> pd.DataFrame:
    """저장·계산 공용 정규화. 0 과 결측은 '넣지 않은 달' 이라 지운다(`monthly_amount`).

    0 을 남겨 두면 변동률이 1 인 행이 쌓여 저장본이 조회기간만큼 커지고, 그 달에 선행을
    **지정했다**는 뜻으로 읽힌다. 지정하지 않은 것과 0 을 지정한 것은 결과가 같다.
    """
    return prepare_monthly_amounts(
        frame, value_column=ADVANCE_LOAD_VALUE_COLUMN, subject=ADVANCE_LOAD_VALUE_COLUMN
    )


def merge_advance_load_edits(
    stored: pd.DataFrame,
    months: Sequence[int],
    values: Sequence[object],
) -> pd.DataFrame:
    """화면에 보인 달만 갈아 끼우고 나머지 저장분은 그대로 둔다(`monthly_amount`).

    조회기간이 좁혀져 있으면 표에 없는 달이 저장본에 남아 있다. 통째로 교체하면 그 달의
    입력을 누른 사람이 모르는 새 날린다. 보이지 않는 것을 지우지 않는다.
    """
    return merge_monthly_amount_edits(
        stored,
        months,
        values,
        value_column=ADVANCE_LOAD_VALUE_COLUMN,
        subject=ADVANCE_LOAD_VALUE_COLUMN,
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
    require_columns(monthly_density, required, "월별 부하량")
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
    """`부하량` 을 선행 반영 부하량으로 갈아 끼운 월별 부하량.

    변동률 표에 없는 달은 원래 값을 그대로 둔다. 그 표는 이 프레임에서 만들어지므로 보통
    빠지는 달이 없지만, 없는 달에 `map` 이 돌려주는 결측을 그대로 넣으면 값이 통째로
    사라진다 — 그 사라짐은 오류도 경고도 없이 빈칸으로만 보인다.
    """
    result = monthly_density.copy()
    replacement = ratio.set_index("생산계획년월")["선행 반영 부하량"]
    months = pd.to_numeric(result["생산계획년월"], errors="coerce").astype("int64")
    original = pd.to_numeric(result["부하량"], errors="coerce")
    result["부하량"] = months.map(replacement).astype("float64").fillna(original)
    return result


def apply_advance_to_wafer(
    monthly_wafer: pd.DataFrame,
    ratio: pd.DataFrame,
) -> pd.DataFrame:
    """`Wafer 부하량` 을 변동률로 나눈다. Density 와 같은 비율로 함께 움직인다."""
    require_columns(monthly_wafer, ["Wafer 부하량"], "월별 Wafer")
    result = monthly_wafer.copy()
    # 변동률 표에 없는 달은 1 로 둔다 — 선행을 넣지 않은 달과 같은 취급이다.
    factor = ratio.set_index("생산계획년월")["변동률"]
    months = pd.to_numeric(result["생산계획년월"], errors="coerce").astype("int64")
    result["Wafer 부하량"] = pd.to_numeric(result["Wafer 부하량"], errors="coerce") / months.map(
        factor
    ).astype("float64").fillna(1.0)
    return result


def apply_advance_to_securement(
    securement_rate: pd.DataFrame,
    ratio: pd.DataFrame,
) -> pd.DataFrame:
    """그 달의 모든 공정 확보율에 같은 변동률을 곱한다.

    한 달 안에서는 모두 같은 수를 곱하므로 **공정 순위는 바뀌지 않는다.** B/N 공정이
    선행 입력에 따라 갈아 끼워지면 그것은 계산이 아니라 착시다.

    **변동률 표에 없는 달은 1 로 둔다.** 변동률은 월별 부하량에서 만드는데 확보율은 거기
    없는 달을 가질 수 있다 — 과거 구간을 공정별 확보율에만 넣고 월별 실적에는 넣지 않은
    경우가 그렇다. 없는 달을 결측으로 곱하면 그 달 확보율이 통째로 사라진다.
    """
    require_columns(securement_rate, ["확보율"], "확보율")
    result = securement_rate.copy()
    factor = ratio.set_index("생산계획년월")["변동률"]
    months = pd.to_numeric(result["생산계획년월"], errors="coerce").astype("int64")
    scale = months.map(factor).astype("float64").fillna(1.0)
    result["확보율"] = pd.to_numeric(result["확보율"], errors="coerce") * scale
    # 실행 Capa 반영이 남긴 **조정 전** 확보율도 같은 변동률로 옮긴다. 한쪽만 곱하면
    # 증감 영역이 선행 배율만큼 부풀거나 줄어 화면에서 조정량이 거짓으로 보인다.
    if "기준 확보율" in result.columns:
        result["기준 확보율"] = pd.to_numeric(result["기준 확보율"], errors="coerce") * scale
    return result


def revert_advance_from_securement(
    securement_rate: pd.DataFrame,
    ratio: pd.DataFrame,
) -> pd.DataFrame:
    """선행 반영 확보율을 변동률로 나눠 선행 전 확보율로 되돌린다.

    선행 전후를 한 그림에 함께 그리려면 기존값이 있어야 한다. 순위는 선행에 따라 바뀌지
    않으므로(월마다 같은 수를 곱한다) B/N 공정은 그대로 두고 확보율만 되돌린다.

    나누는 것은 `확보율` 이 맞다. 실행 Capa 반영은 선행보다 **앞**에서 끝나므로 여기서
    되돌리는 것은 곱셈 한 겹뿐이다 — 선행 전 값은 「실행까지 반영된 원데이터」다.

    **변동률 표에 없는 달은 1 로 둔다** — 정방향(`apply_advance_to_securement`)과 같다(2026-10-06
    사용자 결정). 정방향이 그 달을 건드리지 않았으니 되돌릴 것도 없다. 결측으로 나누면 그 달의
    선행 전 확보율이 오류도 경고도 없이 빈칸이 된다.
    """
    result = securement_rate.copy()
    factor = ratio.set_index("생산계획년월")["변동률"]
    months = pd.to_numeric(result["생산계획년월"], errors="coerce").astype("int64")
    scale = months.map(factor).astype("float64").fillna(1.0)
    result["확보율"] = pd.to_numeric(securement_rate["확보율"], errors="coerce") / scale
    return result
