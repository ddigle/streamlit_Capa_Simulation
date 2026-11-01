# Purpose: UPEH/ST와 효율·여유율·모듈·일수·측정률로 경로별 대당 Capa를 계산한다.

from dataclasses import dataclass
from typing import NamedTuple

import pandas as pd

from capa_simulation.services.frame_checks import assert_unique_keys, strip_text_columns
from capa_simulation.services.frame_contracts import (
    UNIMPLEMENTED_BASES,
    assert_complete,
    normalize_area_name,
    normalize_month_column,
    require_columns,
)
from capa_simulation.services.month_filter import valid_month_mask

PERFORMANCE_KEYS = [
    "생산계획년월",
    "Area_Name",
    "공정",
    "STEP_SEQ",
    "MCP_SEQ",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
]
UNIT_CAPACITY_DIMENSIONS = [
    "공정",
    "Area_Name",
    "소요기준",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
    "STEP_SEQ",
    "MCP_SEQ",
]
CAPACITY_EXCLUSIONS_ATTR = "excluded_capacity_rows"
# 측정률 행이 없어 중립값 1.0 으로 이어 간 건수. **세지 않고 메우면 조용히 틀린다.**
# 측정률은 분모라 실제가 1 보다 작으면 대당 Capa 과소 → 소요대수 과대 → 확보율 과소(보수 쪽),
# 1 보다 크면 그 반대(낙관 쪽)로 틀린다.
CAPACITY_ASSUMPTIONS_ATTR = "assumed_capacity_defaults"
# 같은 가정이 걸린 달. 건수만 말하면 어느 달 칸을 채워야 하는지 다시 찾아야 한다.
# 대당 Capa 는 시나리오 전체 기간을 한 번에 계산하므로 조회기간 밖의 달도 들어 있다.
CAPACITY_ASSUMED_MONTHS_ATTR = "assumed_capacity_months"


class CapacityAssumptions(NamedTuple):
    """측정률을 1.0 으로 메운 경로 수와 그 달. 화면 알림이 둘 다 말한다."""

    counts: dict[str, int]
    months: dict[str, tuple[int, ...]]


def capacity_assumptions(unit_capacity: pd.DataFrame) -> CapacityAssumptions:
    """대당 Capa 프레임의 `attrs` 에서 가정을 꺼낸다. 없으면 빈 묶음이다."""
    return CapacityAssumptions(
        counts=dict(unit_capacity.attrs.get(CAPACITY_ASSUMPTIONS_ATTR, {})),
        months=dict(unit_capacity.attrs.get(CAPACITY_ASSUMED_MONTHS_ATTR, {})),
    )


# 검증 실패 메시지에 문제 행의 업무 키를 실으려면 그 컬럼이 어떤 키로 붙었는지 알아야 한다.
# 연결에 쓰는 키 목록과 검증이 보고하는 키 목록이 갈라지지 않게 한 곳에 둔다.
RUN_RATE_KEYS = ["생산계획년월", "공정", "양산구분"]
VITAL_KEYS = ["생산계획년월", "공정", "양산구분"]
MODULE_KEYS = ["공정"]
RUN_DAY_KEYS = ["생산계획년월", "공정"]

# `RQ_UPEH` 의 MI 행 `ST` 는 한 개당 분(min/unit)으로 입력한다(정의). 시간당 처리량은 60 ÷ ST 다.
# 값 크기로 단위를 가르거나 갈래를 두지 않는다.
ST_MINUTES_PER_HOUR = 60.0
# 소요기준 CHIP·PKG 의 부하량은 K개라 시간당 처리량도 1,000 으로 나눠 K개로 맞춘다.
_UNITS_PER_KEA = 1000.0


def converted_upeh(
    upeh: pd.Series, st: pd.Series, *, main: pd.Series, mi: pd.Series, per_kea: pd.Series
) -> pd.Series:
    """환산_UPEH — Main 행은 UPEH, MI 행은 60 ÷ ST(ST 는 분 단위 — 정의), CHIP·PKG 는 다시 ÷ 1,000.

    대당 Capa 계산(`_prepare_performance`)과 기존 결과 대조(`legacy_comparison.hourly_rate`)가 이
    하나를 같이 쓴다. Main·MI 어느 쪽도 아닌 행은 빈 값이다.
    """
    rate = upeh.astype("float64").where(main)
    rate = rate.mask(mi, ST_MINUTES_PER_HOUR / st.astype("float64"))
    return rate.mask(per_kea, rate / _UNITS_PER_KEA)


# 음수이면 그 행만 계산에서 빼는 컬럼. 둘 다 대당 Capa 식의 분모이고 결측 기본값이
# 1.0 인 쌍둥이 기준정보라 같은 규칙을 쓴다.
NEGATIVE_EXCLUDED_COLUMNS = (
    ("WF측정률", "WF측정률 음수"),
    ("Lot 측정률", "Lot 측정률 음수"),
)

# 측정률 0 은 측정 대상이 아닌 경로로 보고 빈 값과 같이 1.0 을 적용한다. 분모라서 0 을
# 그대로 두면 나눌 수 없어 예전에는 행을 통째로 뺐지만, 원천에서 0 과 빈 값이 같은 뜻으로
# 들어오는 것이 확인돼 같은 규칙으로 맞췄다. 음수는 입력 오류라 그대로 제외한다.
MEASUREMENT_RATIO_ZERO_DEFAULT = 1.0

# Main 행 UPEH 가 0 이하면 대당 Capa 도 0 이 된다. 예전에는 `대당 Capa 0 이하` 로만 적혀
# 분모·분자 어느 쪽이 문제인지 알 수 없었다. 원천 접힘으로 0 이 저장되는 일이 실제로 있어
# (`services/reference_conflicts.py` 참조) 원인을 사유에 적는다. MI 행은 ST 가 0 이하면
# `_prepare_performance` 가 먼저 막으므로 여기 걸리는 것은 Main 행뿐이다.
UPEH_EXCLUSION_REASON = "UPEH 0 이하"

# CAPA_RUN_RATE 는 대당 Capa 식의 **분자**다. 검사도 전용 규칙도 없는 유일한 인자여서,
# 0·음수가 들어오면 곱이 0 이하가 되어 `대당 Capa 0 이하` 로만 적혔다 — 사용자를 UPEH 쪽으로
# 보내는 오지목이다. 편중률 0 은 하드 오류인데 효율 0 은 조용한 제외라는 비대칭도 같이 남았다.
#
# 편중률처럼 하드 오류로 올리지 않는 이유는 `calculate_unit_capacity` 의 「계산 대상 행을 먼저
# 확정한다」 주석과 같다. 원천이 "해당 없음" 을 0 으로 적는 일이 실제로 있어
# (`services/reference_conflicts.py`) 그 한 줄 때문에 편집기조차 못 여는 쪽이 더 나쁘다.
# 대신 무엇이 0 인지 사유에 적는다.
RUN_RATE_EXCLUSION_REASON = "CAPA_RUN_RATE 0 이하"

# `_join_reference` 가 붙인 뒤 제외를 정할 때까지 들고 가는 칸의 머리. 표마다 하나씩 — 붙은 칸의
# 상태(`_VALUE_OK` …)와, 숫자가 아닌 값이 있는 표만 원래 적힌 값.
_CHECK_STATUS = "_검사상태:"
_CHECK_RAW = "_검사원래값:"
_JOINED = "_연결"
# 붙은 칸의 상태. 제외 마스크 뒤에 남은 행에서만 본다(`_raise_on_unusable_values`).
_VALUE_OK = 0
_VALUE_NOT_NUMERIC = 1
_VALUE_BLANK = 2
_VALUE_NO_MATCH = 3

# 기준정보 한 표를 경로에 붙이다 멈춘 꼴(`ReferenceJoinProblem.shape`). 여러 꼴이 모두 같은 표
# 이름의 `ValueError` 로 올라오므로, 문구를 찍지 못하는 집계(사내 런북 6-3 a)는 이 이름과 개수로
# 가른다.
JOIN_MISSING_COLUMN = "컬럼 없음"
JOIN_BAD_MONTH = "월 형식"
JOIN_BAD_AREA = "Area_Name 값"
JOIN_BLANK_KEY = "연결 키 빈 값"
JOIN_DUPLICATE_KEY = "연결 키 중복"
JOIN_NOT_NUMERIC = "숫자 아님"
JOIN_BLANK_VALUE = "빈 값"
JOIN_NO_MATCH = "연결값 없음"


@dataclass(frozen=True)
class ReferenceJoinProblem:
    """기준정보 한 표를 대당 Capa 경로에 붙이다 멈춘 꼴 — 값 없이 개수와 컬럼 이름만 든다.

    화면 문구(`ReferenceJoinError` 의 글)는 걸린 키의 예시(공정·제품 이름)를 싣는다. 그 글은 사내
    밖으로 나갈 수 없어서, 전 리비전 집계(`scripts/inspect_revision_calculations.py`)는 이것만
    찍는다.

    - `keys` — 걸린 업무 키 수. `rows` — 걸린 행 수다. 붙인 뒤에 보는 꼴(빈 값·숫자 아님·
      연결값 없음)은 그 키에 붙은 대당 Capa **경로** 행 가운데 제외 뒤에 남은 것, 붙이기 전에 보는
      꼴(월 형식·연결 키)은 그 기준정보 표의 행이다.
    - `spacing_keys` — 연결 키 중복 가운데 원래 글자로는 다르고 앞뒤 공백을 떼면 같아지는 키.
      등록은 원래 글자로 접고 계산은 공백을 떼고 붙여서 생기는 겹침이다.
    """

    table: str
    shape: str
    columns: tuple[str, ...] = ()
    keys: int = 0
    rows: int = 0
    spacing_keys: int = 0

    @property
    def label(self) -> str:
        """갈래 이름 — 개수 없이. 집계가 이 이름으로 리비전을 묶는다."""
        if self.shape == JOIN_DUPLICATE_KEY and self.keys and self.spacing_keys == self.keys:
            return f"{self.shape}(앞뒤 공백만 다름)"
        if self.shape in (JOIN_MISSING_COLUMN, JOIN_BLANK_KEY) and self.columns:
            return f"{self.shape}({', '.join(self.columns)})"
        return self.shape

    def summary(self) -> str:
        """개수까지 — 리비전 한 줄에 싣는다. 값·이름은 없다."""
        if self.shape in (JOIN_BLANK_VALUE, JOIN_NOT_NUMERIC, JOIN_NO_MATCH):
            return f"{self.shape} 키 {self.keys:,} · 경로 {self.rows:,}"
        if self.shape == JOIN_DUPLICATE_KEY:
            text = f"{self.shape} 키 {self.keys:,} · 행 {self.rows:,}"
            if self.spacing_keys:
                text += f" · 앞뒤 공백만 다른 키 {self.spacing_keys:,}"
            return text
        if self.shape == JOIN_MISSING_COLUMN:
            return self.label
        return f"{self.label} 행 {self.rows:,}"


class ReferenceJoinError(ValueError):
    """대당 Capa 기준정보 연결 오류. 글은 화면용(키 예시), `problem` 은 집계용(꼴·개수)이다.

    `ValueError` 를 그대로 잇는다 — 계산 페이지·저장 검사·캐시가 받는 예외
    갈래(`BOOTSTRAP_ERRORS`)와 글은 바뀌지 않는다. 집계에 적는 종류 이름은 `failure_kind` 가
    `ValueError` 로 맞춘다.
    """

    def __init__(self, message: str, problem: ReferenceJoinProblem) -> None:
        super().__init__(message)
        self.problem = problem

    def __reduce__(self) -> tuple[type["ReferenceJoinError"], tuple[str, ReferenceJoinProblem]]:
        # 기본 피클은 `args`(글 하나)로만 다시 만들어 `problem` 인자가 모자란다.
        return (type(self), (str(self), self.problem))


def failure_kind(exc: BaseException) -> str:
    """집계·리뷰에 적는 예외 종류 이름. 기준정보 연결 오류도 `ValueError` 로 적고 꼴은 따로 적는다.

    런북·지난 리뷰가 「대당 Capa(ValueError · RQ_…)」 꼴로 견주므로 종류 이름은 그대로 둔다.
    """
    if isinstance(exc, ReferenceJoinError):
        return ValueError.__name__
    return type(exc).__name__


def calculate_unit_capacity(
    upeh: pd.DataFrame,
    run_rate: pd.DataFrame,
    vital: pd.DataFrame,
    module: pd.DataFrame,
    run_day: pd.DataFrame,
    lot_ratio: pd.DataFrame,
    wf_ratio: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate monthly per-equipment capacity for Main and MI process rows."""
    performance = _prepare_performance(upeh)
    if performance.empty:
        empty_result = pd.DataFrame(
            columns=[
                "생산계획년월",
                *UNIT_CAPACITY_DIMENSIONS,
                "환산_UPEH",
                "대당 Capa",
            ]
        )
        empty_result.attrs[CAPACITY_EXCLUSIONS_ATTR] = pd.DataFrame()
        empty_result.attrs[CAPACITY_ASSUMPTIONS_ATTR] = {}
        empty_result.attrs[CAPACITY_ASSUMED_MONTHS_ATTR] = {}
        return empty_result

    assumed: dict[str, int] = {}
    assumed_months: dict[str, set[int]] = {}
    result = performance
    pending: list[_PendingCheck] = []
    for reference, keys, value_column, table_name, neutral in (
        (run_rate, RUN_RATE_KEYS, "CAPA_RUN_RATE", "RQ_RUN_RATE", None),
        (vital, VITAL_KEYS, "편중률", "RQ_VITAL", None),
        (module, MODULE_KEYS, "모듈수", "RQ_MODULE", None),
        (run_day, RUN_DAY_KEYS, "RUN_DAY", "RQ_RUN_DAY", None),
        (lot_ratio, PERFORMANCE_KEYS, "Lot 측정률", "RQ_LOT_RATIO", 1.0),
        (wf_ratio, PERFORMANCE_KEYS, "WF측정률", "RQ_WF_RATIO", 1.0),
    ):
        result, check = _join_reference(
            result,
            reference,
            keys,
            value_column,
            table_name,
            missing_value_default=neutral,
            assumed=assumed if neutral is not None else None,
            assumed_months=assumed_months if neutral is not None else None,
        )
        pending.append(check)
    check_columns = [column for check in pending for column in check.columns]

    # 계산 대상 행을 먼저 확정한다. 어차피 빠질 행의 다른 기준값 때문에 화면 전체가 멈추면 그 값을
    # 고칠 편집기조차 열리지 않는다. 0 을 1.0 으로 올리는 것이 먼저다 — 뒤에 두면 이미 뺀 행을
    # 되살릴 수 없다. 빈 값·숫자 아님·연결값 없음 칸은 비교가 거짓이라(NaN) 그 칸으로는 빠지지
    # 않는다 — 다른 칸으로 빠지지 않으면 아래 검사가 멈춘다.
    excluded_frames: list[pd.DataFrame] = []
    nonpositive_upeh = result["환산_UPEH"].le(0)
    excluded_frames.append(
        _exclusion_rows(result, nonpositive_upeh, UPEH_EXCLUSION_REASON, check_columns)
    )
    result = result.loc[~nonpositive_upeh].copy()

    nonpositive_run_rate = result["CAPA_RUN_RATE"].le(0)
    excluded_frames.append(
        _exclusion_rows(result, nonpositive_run_rate, RUN_RATE_EXCLUSION_REASON, check_columns)
    )
    result = result.loc[~nonpositive_run_rate].copy()

    for column, reason in NEGATIVE_EXCLUDED_COLUMNS:
        result[column] = result[column].mask(result[column].eq(0), MEASUREMENT_RATIO_ZERO_DEFAULT)
        negative_ratio = result[column].lt(0)
        excluded_frames.append(_exclusion_rows(result, negative_ratio, reason, check_columns))
        result = result.loc[~negative_ratio].copy()

    # 빈 값·숫자 아님·연결값 없음은 **제외 뒤에 남은 행에서만** 본다(2026-11-01 사용자 결정 —
    # `docs/TODO.md` 3장, 0655 결정 7). 어차피 빠질 경로에만 붙은 빈 칸 하나가 공정 전체의 계산을
    # 멈추면, 고칠 수 없는 저장 리비전(append-only)은 다시 등록하는 길밖에 없었다. 같은 칸의 0 이
    # 아래 0 이하 검사에서 통과하던 것과도 이제 같다.
    for check in pending:
        _raise_on_unusable_values(result, check)
    result = result.drop(columns=check_columns)

    for column, table_name, keys in (
        ("편중률", "RQ_VITAL", VITAL_KEYS),
        ("모듈수", "RQ_MODULE", MODULE_KEYS),
        ("RUN_DAY", "RQ_RUN_DAY", RUN_DAY_KEYS),
    ):
        _assert_positive(result, column, table_name, keys)

    result["대당 Capa"] = (
        result["환산_UPEH"]
        * 24.0
        * result["CAPA_RUN_RATE"]
        / result["편중률"]
        * result["모듈수"]
        * result["RUN_DAY"]
        / result["Lot 측정률"]
        / result["WF측정률"]
    )
    # 여기까지 온 행은 모든 인자가 양수다(UPEH·CAPA_RUN_RATE 는 위에서 뺐고, 편중률·모듈수·
    # RUN_DAY 는 하드 오류, 측정률은 0 → 1.0). 그래서 이 제외는 언더플로 같은 경우만 받는
    # 마지막 안전망이다 — 사유를 보고 원인을 찾을 수 없으니 여기 걸리는 것이 정상은 아니다.
    nonpositive_capacity = result["대당 Capa"].le(0)
    excluded_frames.append(_exclusion_rows(result, nonpositive_capacity, "대당 Capa 0 이하", []))
    result = result.loc[~nonpositive_capacity].copy()
    columns = ["생산계획년월", *UNIT_CAPACITY_DIMENSIONS, "환산_UPEH", "대당 Capa"]
    output = (
        result[columns]
        .sort_values(["생산계획년월", *UNIT_CAPACITY_DIMENSIONS])
        .reset_index(drop=True)
    )
    output.attrs[CAPACITY_EXCLUSIONS_ATTR] = pd.concat(excluded_frames, ignore_index=True)
    output.attrs[CAPACITY_ASSUMPTIONS_ATTR] = assumed
    output.attrs[CAPACITY_ASSUMED_MONTHS_ATTR] = {
        table: tuple(sorted(months)) for table, months in assumed_months.items()
    }
    return output


def unit_capacity_to_month_table(unit_capacity: pd.DataFrame) -> pd.DataFrame:
    """Pivot calculated unit capacity into month columns for display."""
    required = ["생산계획년월", *UNIT_CAPACITY_DIMENSIONS, "대당 Capa"]
    require_columns(unit_capacity, required, "대당 Capa")
    if unit_capacity.empty:
        return pd.DataFrame(columns=UNIT_CAPACITY_DIMENSIONS)
    result = unit_capacity.pivot(
        index=UNIT_CAPACITY_DIMENSIONS,
        columns="생산계획년월",
        values="대당 Capa",
    ).reset_index()
    result.columns.name = None
    raw_month_columns = [
        column for column in result.columns if column not in UNIT_CAPACITY_DIMENSIONS
    ]
    result = result.rename(columns={column: str(int(column)) for column in raw_month_columns})
    month_columns = sorted(
        [column for column in result.columns if column not in UNIT_CAPACITY_DIMENSIONS]
    )
    return result[[*UNIT_CAPACITY_DIMENSIONS, *month_columns]]


def _prepare_performance(data: pd.DataFrame) -> pd.DataFrame:
    table_name = "RQ_UPEH"
    required = [*PERFORMANCE_KEYS, "소요기준", "UPEH", "ST"]
    require_columns(data, required, table_name)
    result = data[required].copy()
    if result.empty:
        result["환산_UPEH"] = pd.Series(dtype="float64")
        return result
    normalize_month_column(result, table_name)
    strip_text_columns(result, [key for key in PERFORMANCE_KEYS if key != "생산계획년월"])
    result["Area_Name"] = result["Area_Name"].astype("string").str.strip()
    result["소요기준"] = result["소요기준"].astype("string").str.strip().str.upper()
    result = result.loc[~result["소요기준"].isin(UNIMPLEMENTED_BASES)].copy()
    if result.empty:
        result["환산_UPEH"] = pd.Series(dtype="float64")
        return result
    assert_complete(result, [*PERFORMANCE_KEYS, "소요기준"], table_name)
    result["Area_Name"] = normalize_area_name(result["Area_Name"], table_name)
    assert_unique_keys(result, [*PERFORMANCE_KEYS, "소요기준"], f"{table_name}의 연결 키가")

    upeh_values = pd.to_numeric(result["UPEH"], errors="coerce")
    st_values = pd.to_numeric(result["ST"], errors="coerce")
    main_rows = result["Area_Name"].eq("Main")
    mi_rows = result["Area_Name"].eq("MI")
    if upeh_values.loc[main_rows].isna().any():
        raise ValueError("RQ_UPEH의 Main 행에 UPEH 누락값 또는 숫자가 아닌 값이 있습니다.")
    if st_values.loc[mi_rows].isna().any():
        raise ValueError("RQ_UPEH의 MI 행에 ST 누락값 또는 숫자가 아닌 값이 있습니다.")
    if st_values.loc[mi_rows].le(0).any():
        raise ValueError("RQ_UPEH의 MI 행 ST 값은 0보다 커야 합니다.")

    result["환산_UPEH"] = converted_upeh(
        upeh_values,
        st_values,
        main=main_rows,
        mi=mi_rows,
        per_kea=result["소요기준"].isin(["CHIP", "PKG"]),
    )
    return result


class _PendingCheck(NamedTuple):
    """붙인 표 하나의 값 검사 — 제외 마스크 뒤에 남은 행에서 `_raise_on_unusable_values` 가 본다."""

    table_name: str
    value_column: str
    keys: list[str]
    status: str
    raw: str | None

    @property
    def columns(self) -> list[str]:
        """검사가 끝나면 지울, 붙이며 더한 칸."""
        return [self.status] if self.raw is None else [self.status, self.raw]


def _join_reference(
    base: pd.DataFrame,
    reference: pd.DataFrame,
    keys: list[str],
    value_column: str,
    table_name: str,
    *,
    missing_value_default: float | None = None,
    assumed: dict[str, int] | None = None,
    assumed_months: dict[str, set[int]] | None = None,
) -> tuple[pd.DataFrame, _PendingCheck]:
    """기준정보 한 표를 붙인다. **연결값이 없을 때의 처리가 표마다 다르다.**

    `missing_value_default` 가 **선언된 표만** 행이 없어도 그 값으로 이어 간다. 측정률
    둘이 그렇고, 1.0 은 「측정으로 깎이지 않는다」는 중립값이지 지어낸 수가 아니다 —
    빈 값과 `0` 은 이미 같은 결정을 받고 있다(`MEASUREMENT_RATIO_ZERO_DEFAULT`,
    `reference_transformer` 의 파생 단계, AGENTS.md 측정률 절). 행 부재만 하드 오류로
    남아 있던 것을 같은 선 안으로 들인다.

    **나머지 표는 그대로 멈춘다.** 가동률·편중률·모듈수·가동일수에는 중립값이 없다.
    1.0 을 넣으면 「가동률 100%」 같은 거짓 주장이 되고, 기준정보가 통째로 빠진 배포에서도
    숫자가 나와 버린다.

    가정한 건수는 `assumed` 에 쌓아 화면이 말하게 한다. **세지 않고 메우면 (c) 가 아니라
    (b) 가 된다** — 조용히 틀리는 경로를 하나 더 여는 것이다. 측정률은 분모라 실제가
    1 보다 작으면(표본은 모두 그렇다) 대당 Capa 과소 → 소요대수 과대 → 확보율 과소로
    **보수 쪽**이고, 1 보다 큰 경로에서만 낙관 쪽이다.

    **값 검사는 붙인 뒤, 실제로 붙은 행에만 하고, 계산 대상 행을 확정한 뒤에 한다.** 표 전체를 먼저
    숫자로 검사하면 BOX·PCB 공정이나 UPEH 가 없는 달처럼 어느 경로에도 붙지 않는 행의 빈 칸 하나가
    계산 전체를 멈추고, 그 값을 고칠 편집기조차 못 연다. 그래서 붙은 칸의 상태(빈 값·숫자
    아님·연결값 없음)만 칸에 적어 들고 가고(`_PendingCheck`), 뒤에서 제외될 경로(UPEH·
    `CAPA_RUN_RATE` 0 이하, 측정률 음수)를 뺀 뒤 남은 행에서 `_raise_on_unusable_values` 가 멈춘다 —
    0 이하 검사(`_assert_positive`)와 같은 자리다. 표 자체가 깨진 것(컬럼·월 형식·연결 키)은 어느
    행이 남든 붙일 수 없으므로 여기서 바로 멈춘다.
    """
    prepared = _prepared_reference(reference, keys, value_column, table_name)
    raw_values = prepared[value_column]
    blank = raw_values.isna()
    if not pd.api.types.is_numeric_dtype(raw_values):
        # 빈 글자는 글자 컬럼에만 있다. 숫자 컬럼까지 글자로 바꿔 보면 계산마다 그 비용을 낸다.
        blank |= raw_values.astype("string").str.strip().eq("").fillna(False)
    if missing_value_default is not None:
        raw_values = raw_values.mask(blank, missing_value_default)
        blank = pd.Series(False, index=prepared.index)
    numeric = pd.to_numeric(raw_values, errors="coerce").astype("float64")
    not_numeric = ~blank & numeric.isna()
    status_column = f"{_CHECK_STATUS}{table_name}"
    raw_column: str | None = None
    prepared[value_column] = numeric
    prepared[status_column] = (
        blank.astype("int8") * _VALUE_BLANK + not_numeric.astype("int8") * _VALUE_NOT_NUMERIC
    ).astype("int8")
    if bool(not_numeric.any()):
        # 원래 적힌 값은 숫자가 아닌 값이 있는 표만 들고 간다 — 오류문이 그 값을 싣는다.
        raw_column = f"{_CHECK_RAW}{table_name}"
        prepared[raw_column] = raw_values
    result = base.merge(
        prepared,
        on=keys,
        how="left",
        validate="many_to_one",
        indicator=_JOINED,
    )
    unmatched = result[_JOINED].ne("both")
    result = result.drop(columns=[_JOINED])
    check = _PendingCheck(table_name, value_column, keys, status_column, raw_column)
    if not unmatched.any():
        result[status_column] = result[status_column].astype("int8")
        return result, check
    if missing_value_default is None:
        result[status_column] = result[status_column].fillna(_VALUE_NO_MATCH).astype("int8")
        return result, check
    result[status_column] = result[status_column].fillna(_VALUE_OK).astype("int8")
    # 행이 없는 경로만 중립값으로 잇는다. 붙은 칸의 숫자 아님(NaN)은 그대로 둔다 — 그 경로가 다른
    # 까닭으로 빠지면 제외 목록에 지어낸 1.0 이 아니라 빈 칸으로 보인다.
    result.loc[unmatched, value_column] = missing_value_default
    if assumed is not None:
        assumed[table_name] = assumed.get(table_name, 0) + int(unmatched.sum())
    if assumed_months is not None and "생산계획년월" in result.columns:
        months = pd.to_numeric(result.loc[unmatched, "생산계획년월"], errors="coerce").dropna()
        assumed_months.setdefault(table_name, set()).update(int(month) for month in months)
    return result, check


def _raise_on_unusable_values(joined: pd.DataFrame, check: _PendingCheck) -> None:
    """제외 뒤에 남은 행에서 그 표의 붙은 칸이 숫자 아님 → 빈 값 → 연결값 없음이면 멈춘다.

    표마다 이 차례로 보고, 표끼리는 붙인 차례(효율 → 편중률 → 모듈수 → 일수 → Lot 측정률 →
    WF측정률)다 — 예전에 붙이며 멈추던 것과 같은 차례·같은 글이다. 걸린 경로는 모두 계산이 쓰는
    경로다.
    """
    status = joined[check.status]
    table_name, value_column, keys = check.table_name, check.value_column, check.keys
    invalid = status.eq(_VALUE_NOT_NUMERIC)
    if bool(invalid.any()):
        raise _attached_error(
            f"{table_name}의 {value_column} 컬럼에 숫자가 아닌 값이 있습니다: ",
            joined,
            invalid,
            keys,
            ReferenceJoinProblem(table_name, JOIN_NOT_NUMERIC, columns=(value_column,)),
            value_column=value_column,
            raw_column=check.raw,
        )
    blank = status.eq(_VALUE_BLANK)
    if bool(blank.any()):
        raise _attached_error(
            f"{table_name}의 {value_column} 값이 빈 대당 Capa 기준이 있습니다: ",
            joined,
            blank,
            keys,
            ReferenceJoinProblem(table_name, JOIN_BLANK_VALUE, columns=(value_column,)),
        )
    missing = status.eq(_VALUE_NO_MATCH)
    if not bool(missing.any()):
        return
    missing_keys = joined.loc[missing, keys].drop_duplicates()
    raise ReferenceJoinError(
        f"{table_name} 연결값이 없는 대당 Capa 기준이 있습니다: {len(missing_keys):,}건, "
        f"예시 {missing_keys.head(5).to_dict('records')}",
        ReferenceJoinProblem(
            table_name,
            JOIN_NO_MATCH,
            columns=tuple(keys),
            keys=len(missing_keys),
            rows=int(missing.sum()),
        ),
    )


def _prepared_reference(
    reference: pd.DataFrame, keys: list[str], value_column: str, table_name: str
) -> pd.DataFrame:
    """붙일 기준정보 표를 계산의 키 꼴로 맞춘다 — 월은 정수, 글자 키는 앞뒤 공백을 뗀다.

    맞추다 걸리면 꼴과 개수를 든 `ReferenceJoinError` 로 멈춘다. 글의 머리는 공용
    검사(`frame_contracts`) 와 같은 문장이고, 그 뒤에 어느 컬럼·몇 행·키 예시를 붙인다.
    """
    try:
        require_columns(reference, [*keys, value_column], table_name)
    except ValueError as exc:
        absent = tuple(column for column in (*keys, value_column) if column not in reference)
        raise ReferenceJoinError(
            str(exc), ReferenceJoinProblem(table_name, JOIN_MISSING_COLUMN, columns=absent)
        ) from exc
    prepared = reference[[*keys, value_column]].copy()
    if "생산계획년월" in keys:
        months = pd.to_numeric(prepared["생산계획년월"], errors="coerce")
        bad_month = ~valid_month_mask(months)
        if bool(bad_month.any()):
            examples = prepared.loc[bad_month, keys].drop_duplicates().head(5).to_dict("records")
            raise ReferenceJoinError(
                f"{table_name}의 생산계획년월은 YYYYMM 형식이어야 합니다: "
                f"{int(bad_month.sum()):,}행, 예시 {examples}",
                ReferenceJoinProblem(
                    table_name,
                    JOIN_BAD_MONTH,
                    columns=("생산계획년월",),
                    rows=int(bad_month.sum()),
                ),
            )
        # `normalize_month_column` 과 같은 결과다 — 위에서 이미 읽은 수를 다시 읽지 않는다.
        prepared["생산계획년월"] = months.astype("int64")
    text_keys = [key for key in keys if key != "생산계획년월"]
    strip_text_columns(prepared, text_keys)
    _raise_on_blank_keys(prepared, keys, table_name)
    if "Area_Name" in keys:
        try:
            prepared["Area_Name"] = normalize_area_name(prepared["Area_Name"], table_name)
        except ValueError as exc:
            raise ReferenceJoinError(
                str(exc),
                ReferenceJoinProblem(table_name, JOIN_BAD_AREA, columns=("Area_Name",)),
            ) from exc
    _raise_on_duplicate_keys(prepared, reference, keys, text_keys, table_name)
    return prepared


def _raise_on_blank_keys(prepared: pd.DataFrame, keys: list[str], table_name: str) -> None:
    """연결 키가 빈 행 — `frame_contracts.assert_complete` 와 같은 판정에 컬럼과 행 수를 붙인다."""
    blank_by_column = {
        column: prepared[column].isna() | prepared[column].eq("").fillna(False) for column in keys
    }
    counts = {column: int(mask.sum()) for column, mask in blank_by_column.items() if mask.any()}
    if not counts:
        return
    blank_rows = pd.concat(list(blank_by_column.values()), axis=1).any(axis=1)
    detail = " · ".join(f"{column} {count:,}행" for column, count in counts.items())
    raise ReferenceJoinError(
        f"{table_name}의 필수 연결 키에 누락값이 있습니다: {detail}",
        ReferenceJoinProblem(
            table_name, JOIN_BLANK_KEY, columns=tuple(counts), rows=int(blank_rows.sum())
        ),
    )


def _raise_on_duplicate_keys(
    prepared: pd.DataFrame,
    reference: pd.DataFrame,
    keys: list[str],
    text_keys: list[str],
    table_name: str,
) -> None:
    """맞춘 키가 겹치는 행 — 건수·예시와, 원래 글자의 앞뒤 공백만 달라 겹친 키의 수를 싣는다.

    등록(`reference_conflicts.validated_distinct`)은 원래 글자로 접으므로 `P1`·`P1 ` 은 두 행으로
    저장되고, 여기서 공백을 떼면 한 키가 된다. 그 꼴은 원천을 고쳐 다시 등록해야 풀리므로 따로 센다.
    """
    duplicated = prepared.duplicated(keys, keep=False)
    if not bool(duplicated.any()):
        return
    overlapping = prepared.loc[duplicated, keys]
    distinct = overlapping.drop_duplicates()
    spacing = 0
    if text_keys:
        # 자리로 고른다 — 받은 표의 index 가 겹쳐도 같은 행을 본다(`prepared` 는 그 표를 그대로
        # 떴다). 앞뒤 공백을 떼면 같아지는 원래 글자가 둘 이상인 키만 센다 — Area_Name 의
        # 대소문자(`Main`·`main`)처럼 다른 정규화로 겹친 키는 공백 꼴이 아니다.
        raw = reference[text_keys].loc[duplicated.to_numpy()].astype("string")
        raw.index = overlapping.index
        spelled = raw.fillna("\0").agg("\x1f".join, axis=1)
        stripped = (
            raw.apply(lambda column: column.str.strip()).fillna("\0").agg("\x1f".join, axis=1)
        )
        spellings = overlapping.assign(_원래글자=spelled, _뗀글자=stripped)
        grouped = spellings.groupby(keys, dropna=False)
        variants = grouped["_원래글자"].nunique() > grouped["_뗀글자"].nunique()
        spacing = int(variants.sum())
    message = (
        f"{table_name}의 연결 키가 중복되었습니다: {len(distinct):,}건, "
        f"예시 {distinct.head(5).to_dict('records')}"
    )
    if spacing:
        message += f" — 그 가운데 {spacing:,}건은 원래 글자에서 앞뒤 공백만 다른 행이 겹친 것입니다"
    raise ReferenceJoinError(
        message,
        ReferenceJoinProblem(
            table_name,
            JOIN_DUPLICATE_KEY,
            columns=tuple(keys),
            keys=len(distinct),
            rows=len(overlapping),
            spacing_keys=spacing,
        ),
    )


def _attached_error(
    head: str,
    joined: pd.DataFrame,
    mask: pd.Series,
    keys: list[str],
    problem: ReferenceJoinProblem,
    *,
    value_column: str | None = None,
    raw_column: str | None = None,
) -> ReferenceJoinError:
    """걸린 행의 건수와 예시 키 5건. `value_column` 을 주면 원래 적힌 값(`raw_column`)도 싣는다."""
    examples = joined.loc[mask, keys].copy()
    if value_column is not None and raw_column is not None:
        examples[value_column] = joined.loc[mask, raw_column]
    distinct = examples.drop_duplicates(subset=keys)
    records = distinct.head(5).to_dict("records")
    count = len(distinct)
    detail = ReferenceJoinProblem(
        problem.table,
        problem.shape,
        columns=problem.columns,
        keys=count,
        rows=int(mask.sum()),
    )
    return ReferenceJoinError(f"{head}{count:,}건, 예시 {records}", detail)


def _assert_positive(
    data: pd.DataFrame,
    column: str,
    table_name: str,
    keys: list[str],
) -> None:
    """0 이하 값을 막고, 어느 경로가 걸렸는지 건수와 예시 키·값으로 알린다."""
    nonpositive = data[column].le(0)
    if not bool(nonpositive.any()):
        return
    examples = data.loc[nonpositive, [*keys, column]].drop_duplicates().head(5).to_dict("records")
    raise ValueError(
        f"{table_name}의 {column} 값은 0보다 커야 합니다:"
        f" {int(nonpositive.sum()):,}건, 예시 {examples}"
    )


def _exclusion_rows(
    data: pd.DataFrame, mask: pd.Series, reason: str, check_columns: list[str]
) -> pd.DataFrame:
    """제외한 행과 그 행이 쓴 기준값. 붙이며 더한 검사 칸(`check_columns`)은 뺀다.

    빈 값·숫자 아님·연결값 없음 칸은 그 행이 다른 까닭으로 빠졌으면 빈 칸 그대로 남는다.
    """
    excluded = data.loc[mask].drop(columns=check_columns)
    excluded["제외사유"] = reason
    return excluded
