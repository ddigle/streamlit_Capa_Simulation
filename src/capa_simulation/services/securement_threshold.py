# Purpose: 공용 확보율 판정 기준(기본값·월별 예외)의 정규화·검증과 달마다의 실효 기준을 정한다.

"""확보율 판정 기준 — 기본 확보·경고 기준과 월별 예외.

판정 기준은 시나리오와 무관한 공용 정책값이다(2026-10-06 사용자 결정). HOME → Preference 한
곳에서 정하고 모든 시나리오·공식버전 Summary 가 같은 값을 쓴다. 기본값 한 짝이 있고, 특정 달만
다른 기준을 쓸 때(예: 미래 구간을 120% 로 보는 경우) 그 달에만 값을 둔다. **월별 칸이 비어
있으면 그 달 그 항목은 기본값이다** — 확보만 채우고 경고는 비워 두는 것이 보통이다.

값은 모두 **비율**이다(109.5% 는 1.095). 판정(`capacity_status`)과 표시(`threshold_percent_label`)가
비율을 받는다. 퍼센트로 바꾸는 것은 입력 칸을 그리는 화면뿐이다.

기준은 **실제 판정값**이다. 업무 기준 110% 를 아슬아슬하게 모자란 공정까지 넣으려고 109.5 로 적는
관례가 그대로 이어진다. 화면에 적을 때만 사사오입 정수 %(`threshold_percent_label`)로 보인다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Literal

import pandas as pd

from capa_simulation.services.frame_contracts import require_exact_columns
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.threshold_label import threshold_percent_label

SECUREMENT_THRESHOLD_COLUMNS = ("생산계획년월", "확보 기준", "경고 기준")
SECURE_COLUMN = "확보 기준"
WARNING_COLUMN = "경고 기준"

# 프로필도 공식버전 프리셋도 없을 때 쓰는 코드 기본값(비율). 업무 기준 110%·100% 를 반 칸 낮춘
# 값이다(`threshold_label` 모듈 설명).
DEFAULT_SECURE_THRESHOLD = 1.095
DEFAULT_WARNING_THRESHOLD = 0.995

# 월별 예외 한 칸. 빈칸(None)은 그 항목이 기본값을 따른다는 뜻이다.
MonthlyThreshold = tuple[int, float | None, float | None]
CapacityStatus = Literal["secure", "warning", "shortage"]


def capacity_status(
    rate: float, *, secure_threshold: float, warning_threshold: float
) -> CapacityStatus:
    """확보율 하나를 확보·경고·부족 세 상태로 판정한다.

    HOME 막대·히트맵의 색, 확보율 히트맵의 계단, 결론 한 줄의 색, Summary 막대 색이 모두 이
    부등호 하나를 본다. 경계를 각자 적으면 한쪽만 바꿨을 때 같은 값을 두고 화면마다 다른 말을
    한다. 확보는 기준 **초과**, 경고는 경고 기준 **이상**, 나머지가 부족이다.
    """
    if rate > secure_threshold:
        return "secure"
    if rate >= warning_threshold:
        return "warning"
    return "shortage"


@dataclass(frozen=True)
class SecurementThresholds:
    """기본 기준 한 짝과 월별 예외. 해시 가능해 그대로 캐시 키 원소가 된다.

    `monthly` 는 달 오름차순이고, 두 칸이 다 빈 달은 들지 않는다(정규화가 지운다).
    """

    default_secure: float
    default_warning: float
    monthly: tuple[MonthlyThreshold, ...] = ()

    def for_month(self, month: int | None) -> tuple[float, float]:
        """그 달의 실효 (확보, 경고). 월별 칸이 비었거나 달이 없으면(`None`) 기본값이다."""
        if month is None:
            return self.default_secure, self.default_warning
        for stored_month, secure, warning in self.monthly:
            if stored_month == int(month):
                return (
                    self.default_secure if secure is None else secure,
                    self.default_warning if warning is None else warning,
                )
        return self.default_secure, self.default_warning

    def secure_for(self, month: int | None) -> float:
        return self.for_month(month)[0]

    def warning_for(self, month: int | None) -> float:
        return self.for_month(month)[1]

    def status(self, rate: float, month: int | None) -> CapacityStatus:
        """그 달의 실효 기준으로 판정한다. 판정하는 모든 화면이 이 한 길을 지난다."""
        secure, warning = self.for_month(month)
        return capacity_status(rate, secure_threshold=secure, warning_threshold=warning)

    @property
    def exception_months(self) -> tuple[int, ...]:
        """월별 값을 하나라도 둔 달. 값이 기본값과 같아도 센다 — 사용자가 적은 칸이다."""
        return tuple(month for month, _, _ in self.monthly)

    def exception_months_within(self, months: Iterable[int]) -> tuple[int, ...]:
        """주어진 달 가운데 실효 기준이 기본값과 다른 달. 화면 캡션이 「월별 예외 N개월」로 센다."""
        defaults = (self.default_secure, self.default_warning)
        return tuple(
            month
            for month in sorted({int(value) for value in months})
            if self.for_month(month) != defaults
        )

    @property
    def digest(self) -> str:
        """내용 지문. 같은 기준이면 같은 글자다 — 캐시 키에 version 대신 넣을 수 있다.

        프로필을 아직 저장하지 않았을 때 기본값은 최신 공식버전 프리셋에서 오고 version 은 0 에
        머문다. version 만 키로 쓰면 그 사이 기본값이 바뀌어도 캐시가 갈리지 않는다.
        """
        text = repr((self.default_secure, self.default_warning, self.monthly))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def securement_threshold_caption(
    thresholds: SecurementThresholds,
    *,
    start_month: int,
    end_month: int,
    with_warning: bool = False,
) -> str:
    """기본 기준과 기간 안 월별 예외 수를 한 줄로 적는다(예: 「확보 기준 110% · 월별 예외 3개월」).

    숫자는 사사오입 정수 %(`threshold_percent_label`)다. 예외는 **기간 안에서 실효 기준이 기본값과
    다른 달**만 센다 — 기간 밖 달이나 기본값과 같은 값을 적은 달은 이 화면의 판정을 바꾸지 않는다.
    """
    parts = [f"확보 기준 {threshold_percent_label(thresholds.default_secure)}"]
    if with_warning:
        parts.append(f"경고 기준 {threshold_percent_label(thresholds.default_warning)}")
    exceptions = thresholds.exception_months_within(
        month for month in thresholds.exception_months if start_month <= month <= end_month
    )
    if exceptions:
        parts.append(f"월별 예외 {len(exceptions)}개월")
    return " · ".join(parts)


def empty_securement_threshold_rows() -> pd.DataFrame:
    """월별 예외가 하나도 없는 정상 상태의 빈 프레임."""
    return pd.DataFrame(
        {
            "생산계획년월": pd.Series(dtype="int64"),
            SECURE_COLUMN: pd.Series(dtype="float64"),
            WARNING_COLUMN: pd.Series(dtype="float64"),
        }
    )


def _require_positive(value: object, label: str) -> float:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric) or not isfinite(float(numeric)) or float(numeric) <= 0:
        raise ValueError(f"{label}은(는) 0 보다 큰 숫자여야 합니다.")
    return float(numeric)


def prepare_securement_threshold_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """저장·계산 공용 정규화. 두 칸이 다 빈 달은 「예외 없음」이라 지운다.

    남은 칸은 0 보다 큰 유한한 값이어야 한다. 0 이나 음수 기준은 모든 공정을 확보로 판정하므로
    입력 실수로 보고 거부한다.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("월별 판정 기준은 pandas DataFrame이어야 합니다.")
    require_exact_columns(frame.columns, SECUREMENT_THRESHOLD_COLUMNS, "월별 판정 기준 컬럼")
    if frame.empty:
        return empty_securement_threshold_rows()
    prepared = frame.loc[:, list(SECUREMENT_THRESHOLD_COLUMNS)].copy()
    for column in SECUREMENT_THRESHOLD_COLUMNS:
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
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
    prepared = prepared.loc[prepared[[SECURE_COLUMN, WARNING_COLUMN]].notna().any(axis=1)]
    for column in (SECURE_COLUMN, WARNING_COLUMN):
        values = prepared[column]
        invalid = values.notna() & ~(values.gt(0) & values.abs().lt(float("inf")))
        if invalid.any():
            months = _month_list(prepared.loc[invalid, "생산계획년월"])
            raise ValueError(f"{column}은(는) 0 보다 큰 숫자여야 합니다: {months}")
    prepared[SECURE_COLUMN] = prepared[SECURE_COLUMN].astype("float64")
    prepared[WARNING_COLUMN] = prepared[WARNING_COLUMN].astype("float64")
    return prepared.sort_values("생산계획년월").reset_index(drop=True)


def validate_securement_thresholds(
    default_secure: float,
    default_warning: float,
    rows: pd.DataFrame,
) -> tuple[float, float, pd.DataFrame]:
    """저장 직전 검증. 정규화한 (기본 확보, 기본 경고, 월별 행)을 돌려준다.

    모든 값은 0 보다 커야 하고, **기본값과 합친 결과로** 각 달의 경고 기준이 확보 기준 이하여야
    한다. 확보만 적은 달이 기본 경고보다 낮아도 거꾸로 짝이다 — 그 달 그대로 판정하면 경고 구간이
    사라진다. 어긋나면 어느 달인지 적어 거부한다.
    """
    secure = _require_positive(default_secure, "기본 확보 기준")
    warning = _require_positive(default_warning, "기본 경고 기준")
    if warning > secure:
        raise ValueError(
            f"기본 경고 기준({_percent(warning)})이 기본 확보 기준({_percent(secure)})보다 큽니다."
        )
    prepared = prepare_securement_threshold_rows(rows)
    thresholds = build_securement_thresholds(secure, warning, prepared)
    reversed_months = [
        (month, *thresholds.for_month(month)) for month in reversed_threshold_months(thresholds)
    ]
    if reversed_months:
        details = ", ".join(
            f"{month_label(month)}(경고 {_percent(month_warning)} > 확보 {_percent(month_secure)})"
            for month, month_secure, month_warning in reversed_months
        )
        raise ValueError(f"경고 기준이 확보 기준보다 큰 달이 있습니다: {details}")
    return secure, warning, prepared


def reversed_threshold_months(thresholds: SecurementThresholds) -> tuple[int, ...]:
    """기본값과 합친 실효 경고 기준이 실효 확보 기준보다 큰 월별 예외 달."""
    return tuple(
        month
        for month in thresholds.exception_months
        if thresholds.warning_for(month) > thresholds.secure_for(month)
    )


def build_securement_thresholds(
    default_secure: float,
    default_warning: float,
    rows: pd.DataFrame,
) -> SecurementThresholds:
    """기본값과 월별 행을 해시 가능한 값 하나로 묶는다. 검증하지 않는다(저장본은 이미 검증됐다)."""
    prepared = prepare_securement_threshold_rows(rows)
    return SecurementThresholds(
        default_secure=float(default_secure),
        default_warning=float(default_warning),
        monthly=tuple(
            (
                int(month),
                None if pd.isna(secure) else float(secure),
                None if pd.isna(warning) else float(warning),
            )
            for month, secure, warning in zip(
                prepared["생산계획년월"],
                prepared[SECURE_COLUMN],
                prepared[WARNING_COLUMN],
                strict=True,
            )
        ),
    )


def effective_securement_thresholds(
    thresholds: SecurementThresholds,
    months: Iterable[int],
) -> pd.DataFrame:
    """달마다의 실효 기준 표(`생산계획년월`·`확보 기준`·`경고 기준`). 판정이 달로 맞대어 쓴다."""
    ordered = sorted({int(value) for value in months})
    pairs = [thresholds.for_month(month) for month in ordered]
    return pd.DataFrame(
        {
            "생산계획년월": pd.Series(ordered, dtype="int64"),
            SECURE_COLUMN: pd.Series([pair[0] for pair in pairs], dtype="float64"),
            WARNING_COLUMN: pd.Series([pair[1] for pair in pairs], dtype="float64"),
        }
    )


def merge_securement_threshold_edits(
    stored: pd.DataFrame,
    months: Sequence[int],
    secure_values: Sequence[object],
    warning_values: Sequence[object],
) -> pd.DataFrame:
    """화면에 보인 달만 갈아 끼우고 조회기간 밖 저장분은 그대로 둔다(선행 물량과 같은 규칙).

    빈칸(None·NaN·빈 글자)은 「그 달은 기본값」이다. 두 칸이 다 비면 그 달의 예외가 지워진다.
    """
    if not (len(months) == len(secure_values) == len(warning_values)):
        raise ValueError("판정 기준 입력의 월 수와 값 수가 다릅니다.")
    prepared = prepare_securement_threshold_rows(stored)
    merged: dict[int, tuple[float | None, float | None]] = {
        int(month): (_optional(secure), _optional(warning))
        for month, secure, warning in zip(
            prepared["생산계획년월"], prepared[SECURE_COLUMN], prepared[WARNING_COLUMN], strict=True
        )
    }
    for month, secure, warning in zip(months, secure_values, warning_values, strict=True):
        merged[int(month)] = (_optional(secure), _optional(warning))
    return prepare_securement_threshold_rows(
        pd.DataFrame(
            {
                "생산계획년월": pd.Series(list(merged), dtype="int64"),
                SECURE_COLUMN: pd.Series([pair[0] for pair in merged.values()], dtype="float64"),
                WARNING_COLUMN: pd.Series([pair[1] for pair in merged.values()], dtype="float64"),
            }
        )
    )


def _optional(value: object) -> float | None:
    if isinstance(value, str) and not value.strip():
        return None
    numeric = pd.to_numeric(pd.Series([value], dtype="object"), errors="coerce").iloc[0]
    return None if pd.isna(numeric) else float(numeric)


def _percent(ratio: float) -> str:
    """검증 문구용 정확한 퍼센트. 사사오입 글자로 적으면 119.6 과 119.5 가 둘 다 120% 로 보인다."""
    return f"{round(float(ratio) * 100, 6):g}%"


def _month_list(months: Iterable[int]) -> str:
    return ", ".join(month_label(month) for month in sorted({int(value) for value in months}))
