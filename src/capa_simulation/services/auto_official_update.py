# Purpose: 공식버전 자동 갱신의 주차·후보·확보율 판정·포함 공정·설정·예약 규칙을 순수 함수로 정한다.

"""공식버전 자동 갱신의 규칙 — 무엇을 받고, 어느 공정을 빼고, 언제 도는가.

2026-10-15 사용자 결정이다. DB·Streamlit·사내 패키지를 모른다. 프레임과 값만 받아 결정만
돌려준다 — 한 회차를 실제로 돌리는 일(조회·저장·발행·기록)은 `auto_official_update_runner` 가
한다. 그래서 여기 함수는 배경 스레드에서도, 화면에서도, 시험에서도 같은 값을 낸다.

- **주차**: 시뮬레이션명의 `W##`(두 자리, 1~53). 앞에 영문자가 붙으면(`NEW41`) 주차가 아니고,
  뒤에 숫자가 이어지면(`W415`) 주차가 아니다. 앞의 숫자·밑줄·공백·괄호는 괜찮다(`26W41`·
  `PSM_W41`). 서로 다른 주차가 둘 이상 적힌 이름은 하나로 정할 수 없어 주차가 없는 것으로 본다.
- **주차의 해**: 이름에는 해가 없다. 원천 등록시각에 가장 가까운 해의 그 주로 읽는다 — 1월
  초에 등록된 `W52` 는 전해, 12월 말에 등록된 `W01` 은 다음 해다. 그래서 연말 W52 → W01 이
  거꾸로 보이지 않는다.
- **후보**: 시뮬레이션명에 키워드(기본 `PSM`, 대소문자 무시)와 주차가 있고, 아직 등록되지
  않았고(보관본 포함), 저장할 수 있는 코드이며, 원천 등록시각이 있는 것. 그 가운데 현재
  공식버전보다 **주차가 크거나**, **같은 주차인데 더 늦게 등록된** 것만 받는다. 여럿이면 가장
  큰 주차, 그 안에서 가장 늦게 등록된 1건.
- **판정**: 리비전 전체 기간의 원 확보율(가용 ÷ 소요). 소요가 0 인 달은 확보율이 없어 보지
  않는다. 한 달이라도 기준 확보율 **미만**이면 그 공정은 공정 필터 off 다(같으면 남는다).
- **포함 공정**: `RQ_REQB` 공정 − 자동 off − 이어받은 수동 off. 수동 off 는 직전 공식버전
  프리셋에서 빠진 공정 가운데 자동 갱신이 뺀 것(`AUTO` 기록)이 아닌 것이다.
- **예약**: 매일 지정 시각에 한 번. 앱이 그 시각에 떠 있지 않았으면(멈췄거나 잠들었으면)
  따라잡지 않고 다음 날 그 시각을 기다린다.
"""

from __future__ import annotations

import math
import re
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Final, Literal

import pandas as pd

from capa_simulation.services.bigdataquery_catalog_view import (
    REGISTERED_AT_FORMAT,
    CatalogRow,
    catalog_rows,
    code_registration_span,
    first_registration_dates,
    normalize_catalog,
)
from capa_simulation.services.month_columns import month_label

DEFAULT_KEYWORD: Final = "PSM"
DEFAULT_THRESHOLD: Final = 0.80
DEFAULT_CHECK_TIME: Final = time(7, 0)
# 기준 확보율 입력의 범위(비율). 0 은 아무것도 빼지 않는 값이라 끄기와 다르지 않고, 200% 를
# 넘는 기준은 거의 모든 공정을 빼 포함 공정이 비게 된다.
MIN_THRESHOLD: Final = 0.01
MAX_THRESHOLD: Final = 2.0
MAX_KEYWORD_LENGTH: Final = 40
# 목록 조회 기간 — 오늘 포함 30일 전부터. 화면 등록의 기본 조회 기간과 같은 길이다.
CATALOG_WINDOW_DAYS: Final = 30
FILTERED_REVISION_NAME: Final = "자동 갱신 공정 필터"
# 예약 확인 간격이 이보다 길게 벌어졌으면 그 사이 앱이 잠들었거나 멈춘 것으로 본다(따라잡지 않는다).
SLOT_TICK_TOLERANCE: Final = timedelta(minutes=10)

TriggerKind = Literal["SCHEDULED", "MANUAL"]
TRIGGER_SCHEDULED: Final = "SCHEDULED"
TRIGGER_MANUAL: Final = "MANUAL"
TRIGGER_LABELS: Final[dict[str, str]] = {TRIGGER_SCHEDULED: "예약", TRIGGER_MANUAL: "지금 실행"}

RunStatus = Literal["RUNNING", "SKIPPED", "PUBLISHED", "PUBLISH_SKIPPED", "ERROR"]
STATUS_RUNNING: Final = "RUNNING"
STATUS_SKIPPED: Final = "SKIPPED"
STATUS_PUBLISHED: Final = "PUBLISHED"
STATUS_PUBLISH_SKIPPED: Final = "PUBLISH_SKIPPED"
STATUS_ERROR: Final = "ERROR"
STATUS_LABELS: Final[dict[str, str]] = {
    STATUS_RUNNING: "실행 중",
    STATUS_SKIPPED: "건너뜀",
    STATUS_PUBLISHED: "등록·발행",
    STATUS_PUBLISH_SKIPPED: "등록·발행 건너뜀",
    STATUS_ERROR: "오류",
}

# 한 회차의 단계. 실패하면 이 단계 이름이 사유 앞에 붙는다.
STAGE_LABELS: Final[dict[str, str]] = {
    "claim": "회차 선점",
    "baseline": "현재 공식버전 확인",
    "catalog": "목록 조회",
    "select": "후보 고르기",
    "register": "상세 조회·등록",
    "judge": "확보율 판정",
    "revision": "리비전 2 저장",
    "publish": "공식버전 발행",
    "done": "끝",
}

ExclusionKind = Literal["AUTO", "INHERITED"]
EXCLUSION_AUTO: Final = "AUTO"
EXCLUSION_INHERITED: Final = "INHERITED"

MISSING_WEEK_MESSAGE: Final = "공식버전에 n주차(W##) 표시가 있어야 합니다"

_WEEK_PATTERN: Final = re.compile(r"(?<![A-Za-z])[Ww](\d{2})(?!\d)")
_MIN_WEEK: Final = 1
_MAX_WEEK: Final = 53


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AutoUpdateConfig:
    """화면에서 바꾸는 설정 넷. 만들 때 검증·정규화한다 — 저장소와 화면이 같은 규칙이다."""

    enabled: bool
    check_time: time
    keyword: str
    threshold: float

    def __post_init__(self) -> None:
        if not isinstance(self.check_time, time):
            raise ValueError("확인 시각은 HH:MM 이어야 합니다.")
        object.__setattr__(self, "enabled", bool(self.enabled))
        # 분 단위다. 초가 붙어 들어와도 회차·화면이 분으로 읽는다.
        object.__setattr__(self, "check_time", time(self.check_time.hour, self.check_time.minute))
        keyword = str(self.keyword).strip()
        if not keyword:
            raise ValueError("시뮬레이션명 키워드는 비어 있을 수 없습니다.")
        if len(keyword) > MAX_KEYWORD_LENGTH:
            raise ValueError(f"시뮬레이션명 키워드는 {MAX_KEYWORD_LENGTH}자 이하여야 합니다.")
        object.__setattr__(self, "keyword", keyword)
        threshold = float(self.threshold)
        if not math.isfinite(threshold) or not MIN_THRESHOLD <= threshold <= MAX_THRESHOLD:
            raise ValueError(
                f"기준 확보율은 {percent_text(MIN_THRESHOLD)} 이상 {percent_text(MAX_THRESHOLD)} "
                "이하여야 합니다."
            )
        object.__setattr__(self, "threshold", threshold)


DEFAULT_CONFIG: Final = AutoUpdateConfig(
    enabled=False,
    check_time=DEFAULT_CHECK_TIME,
    keyword=DEFAULT_KEYWORD,
    threshold=DEFAULT_THRESHOLD,
)


def percent_text(ratio: float) -> str:
    """비율을 적은 그대로의 퍼센트 글자로(0.8 → `80%`, 0.825 → `82.5%`). 반올림하지 않는다."""
    value = float(ratio)
    if not math.isfinite(value):
        return "—"
    percent = (Decimal(repr(value)) * 100).normalize()
    text = format(percent, "f")
    return f"{text}%"


def time_text(value: time) -> str:
    return f"{value.hour:02d}:{value.minute:02d}"


def describe_config_change(before: AutoUpdateConfig, after: AutoUpdateConfig) -> str:
    """설정 변경 기록에 남길 한 줄. 바뀐 칸만 `이전 → 이후` 로 적는다(없으면 「바뀐 값 없음」)."""
    parts: list[str] = []
    if before.enabled != after.enabled:
        parts.append(f"자동 갱신 {_on_off(before.enabled)} → {_on_off(after.enabled)}")
    if before.check_time != after.check_time:
        parts.append(f"확인 시각 {time_text(before.check_time)} → {time_text(after.check_time)}")
    if before.keyword != after.keyword:
        parts.append(f"키워드 {before.keyword} → {after.keyword}")
    if before.threshold != after.threshold:
        parts.append(
            f"기준 확보율 {percent_text(before.threshold)} → {percent_text(after.threshold)}"
        )
    return " · ".join(parts) if parts else "바뀐 값 없음"


def _on_off(enabled: bool) -> str:
    return "켬" if enabled else "끔"


# ---------------------------------------------------------------------------
# 주차
# ---------------------------------------------------------------------------


def week_numbers(text: str) -> tuple[int, ...]:
    """이름에 적힌 서로 다른 주차 번호(나온 차례). 1~53 밖의 `W##` 는 주차가 아니다."""
    found: list[int] = []
    for match in _WEEK_PATTERN.finditer(str(text)):
        week = int(match.group(1))
        if _MIN_WEEK <= week <= _MAX_WEEK and week not in found:
            found.append(week)
    return tuple(found)


def parse_week(text: str) -> int | None:
    """이름의 주차 하나. 없거나 서로 다른 주차가 둘 이상이면 None."""
    weeks = week_numbers(text)
    return weeks[0] if len(weeks) == 1 else None


def week_label(week: int) -> str:
    return f"W{int(week):02d}"


def has_keyword(name: str, keyword: str) -> bool:
    """시뮬레이션명에 키워드가 들어 있는지(대소문자 무시). 화면 목록 검색과 같은 느슨함이다."""
    needle = keyword.strip().casefold()
    return bool(needle) and needle in str(name).casefold()


def anchor_week_year(week: int, anchor: date) -> int:
    """주차 번호를 `anchor`(원천 등록일)에 가장 가까운 해의 주로 읽는다.

    전해·그해·다음 해의 그 주 월요일 가운데 `anchor` 와 가장 가까운 것의 해다. 53주가 없는 해는
    후보에서 빠진다(셋 다 없으면 그해로 본다).
    """
    best: tuple[int, int] | None = None
    for year in (anchor.year - 1, anchor.year, anchor.year + 1):
        try:
            monday = date.fromisocalendar(year, week, 1)
        except ValueError:
            continue
        distance = abs((monday - anchor).days)
        if best is None or distance < best[0]:
            best = (distance, year)
    return anchor.year if best is None else best[1]


class MissingOfficialWeek(ValueError):
    """현재 최신 공식버전에서 주차(W##)를 읽을 수 없다. 자동 갱신을 켜거나 돌리지 않는다."""


@dataclass(frozen=True)
class OfficialBaseline:
    """자동 갱신이 견줄 현재 최신 공식버전과 그 주차."""

    release_no: int
    release_name: str
    scenario_id: str
    revision_id: str
    scenario_name: str
    week: int
    week_year: int
    # 같은 주차의 새 코드를 가리는 기준 시각. 원천 등록시각이 없으면(내장 시드·CSV) 공식
    # 지정시각이다.
    anchor_at: datetime
    week_source: str

    @property
    def key(self) -> tuple[int, int]:
        return self.week_year, self.week

    @property
    def label(self) -> str:
        return f"공식 v{self.release_no} {week_label(self.week)}"


def resolve_official_baseline(
    *,
    release_no: int,
    release_name: str,
    scenario_id: str,
    revision_id: str,
    scenario_name: str,
    source_simulation_name: str,
    source_registered_at: datetime | None,
    published_at: datetime,
) -> OfficialBaseline:
    """공식버전의 주차를 정한다. 없으면 `MissingOfficialWeek`.

    시나리오명 → 원천 시뮬레이션명 → 공식버전명 차례로 보고 **주차가 적힌 첫 이름**이 정한다.
    사람이 고칠 수 있는 이름(시나리오명)이 먼저다 — 원천 이름에 주차가 없으면 시나리오명을 고쳐
    풀 수 있어야 한다. 그 이름에 서로 다른 주차가 둘 이상이면 하나로 정할 수 없어 오류다.
    """
    names = (
        ("시나리오명", scenario_name),
        ("원천 시뮬레이션명", source_simulation_name),
        ("공식버전명", release_name),
    )
    for source, name in names:
        weeks = week_numbers(name)
        if not weeks:
            continue
        if len(weeks) > 1:
            listed = "·".join(week_label(week) for week in weeks)
            raise MissingOfficialWeek(
                f"{MISSING_WEEK_MESSAGE} — 공식 v{release_no} 의 {source} 「{name}」에 "
                f"주차가 둘 이상({listed}) 적혀 있어 하나로 정할 수 없습니다."
            )
        anchor_at = source_registered_at or published_at
        return OfficialBaseline(
            release_no=release_no,
            release_name=release_name,
            scenario_id=scenario_id,
            revision_id=revision_id,
            scenario_name=scenario_name,
            week=weeks[0],
            week_year=anchor_week_year(weeks[0], anchor_at.date()),
            anchor_at=anchor_at,
            week_source=source,
        )
    raise MissingOfficialWeek(
        f"{MISSING_WEEK_MESSAGE} — 공식 v{release_no} 「{release_name}」의 시나리오명·원천 "
        "시뮬레이션명·공식버전명 어디에도 W## 이 없습니다. 시나리오명에 주차를 넣거나"
        "(예: W41) 주차가 적힌 공식버전을 지정하세요."
    )


def missing_official_message() -> str:
    return (
        f"{MISSING_WEEK_MESSAGE} — 아직 공식버전이 없습니다. 주차가 적힌 공식버전을 먼저 "
        "지정하세요."
    )


# ---------------------------------------------------------------------------
# 후보
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CatalogCandidate:
    """받을 수 있는 코드 하나. 같은 코드의 PLAN 줄 가운데 가장 늦게 등록된 줄이 대표다."""

    row: CatalogRow
    registered_at: datetime
    week: int
    week_year: int
    # 상세 조회 기본 창의 근거 — 그 코드가 목록에 보인 (가장 이른, 가장 늦은) 원천 등록일.
    first_registered_on: date
    last_registered_on: date

    @property
    def key(self) -> tuple[int, int]:
        return self.week_year, self.week

    @property
    def simulation_code(self) -> str:
        return self.row.simulation_code


@dataclass(frozen=True)
class CandidateSelection:
    """후보 고르기 결과와 건너뛸 때 사유에 적을 개수."""

    chosen: CatalogCandidate | None
    listed: int
    matched: int
    eligible: int
    newer: int

    def skip_reason(self, keyword: str, baseline: OfficialBaseline) -> str:
        return (
            f"새 코드 없음 — 목록 {self.listed:,}건 중 「{keyword}」·주차가 있는 코드 "
            f"{self.matched:,}건, 그 가운데 미등록·저장 가능 {self.eligible:,}건, "
            f"{baseline.label} 보다 새 것 {self.newer:,}건"
        )


def select_candidate(
    catalog: pd.DataFrame,
    *,
    keyword: str,
    registered_codes: Collection[str],
    baseline: OfficialBaseline,
) -> CandidateSelection:
    """목록 조회 결과(계약 5컬럼, 정리 전)에서 받을 코드 1건을 고른다. 없으면 `chosen=None`."""
    normalized = normalize_catalog(catalog)
    first_dates = first_registration_dates(catalog)
    known = set(registered_codes)
    best_by_code: dict[str, tuple[CatalogRow, datetime, int]] = {}
    matched_codes: set[str] = set()
    for row in catalog_rows(normalized):
        if not has_keyword(row.simulation_name, keyword):
            continue
        week = parse_week(row.simulation_name)
        if week is None:
            continue
        matched_codes.add(row.simulation_code)
        if row.simulation_code in known or not row.savable or not row.registered_at:
            continue
        registered_at = datetime.strptime(row.registered_at, REGISTERED_AT_FORMAT)
        held = best_by_code.get(row.simulation_code)
        if held is None or registered_at > held[1]:
            best_by_code[row.simulation_code] = (row, registered_at, week)

    newer: list[CatalogCandidate] = []
    for code, (row, registered_at, week) in best_by_code.items():
        span = code_registration_span(normalized, first_dates, code)
        first_on, last_on = span if span is not None else (registered_at.date(),) * 2
        candidate = CatalogCandidate(
            row=row,
            registered_at=registered_at,
            week=week,
            week_year=anchor_week_year(week, registered_at.date()),
            first_registered_on=first_on,
            last_registered_on=last_on,
        )
        if is_newer_than(candidate, baseline):
            newer.append(candidate)
    chosen = max(
        newer,
        key=lambda item: (item.key, item.registered_at, item.simulation_code),
        default=None,
    )
    return CandidateSelection(
        chosen=chosen,
        listed=int(normalized["simulation_code"].nunique()) if not normalized.empty else 0,
        matched=len(matched_codes),
        eligible=len(best_by_code),
        newer=len(newer),
    )


def is_newer_than(candidate: CatalogCandidate, baseline: OfficialBaseline) -> bool:
    """현재 공식버전보다 새 것인가 — 더 큰 주차, 또는 같은 주차에서 더 늦은 원천 등록시각."""
    if candidate.key != baseline.key:
        return candidate.key > baseline.key
    return candidate.registered_at > baseline.anchor_at


# ---------------------------------------------------------------------------
# 판정과 포함 공정
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProcessMinimum:
    """공정 하나의 리비전 전체 기간 최저 확보율과 그 달(같은 값이면 이른 달)."""

    process: str
    min_rate: float
    month: int

    @property
    def label(self) -> str:
        """공정 필터 표지에 쓰는 글자 — `확보율 72%, 26.11`."""
        return f"확보율 {_rate_percent(self.min_rate)}, {month_label(self.month)}"


def _rate_percent(rate: float) -> str:
    return f"{rate * 100:.0f}%"


AUTO_OFF_MARK: Final = "자동 off"


def auto_off_mark(min_rate: float | None, month: int | None) -> str:
    """공정 필터 팝업의 표지 — `자동 off(확보율 72%, 26.11)`. 근거가 없으면 `자동 off` 만."""
    if min_rate is None or month is None or not math.isfinite(float(min_rate)):
        return AUTO_OFF_MARK
    minimum = ProcessMinimum(process="", min_rate=float(min_rate), month=int(month))
    return f"{AUTO_OFF_MARK}({minimum.label})"


def process_minimum_rates(securement_rate: pd.DataFrame) -> tuple[ProcessMinimum, ...]:
    """원 확보율 프레임(`생산계획년월`·`공정`·`확보율`)에서 공정별 최저 확보율. 공정 이름 차례.

    확보율이 없는 행(소요 0 → NaN)과 무한값은 보지 않는다. 그런 달만 있는 공정은 결과에 없다 —
    판정할 수 없는 공정은 빼지 않는다.
    """
    frame = pd.DataFrame(
        {
            "month": pd.to_numeric(securement_rate["생산계획년월"], errors="coerce"),
            "process": securement_rate["공정"].astype("string").str.strip(),
            "rate": pd.to_numeric(securement_rate["확보율"], errors="coerce").astype("float64"),
        }
    )
    valid = frame["rate"].map(math.isfinite) & frame["month"].notna() & frame["process"].notna()
    frame = frame.loc[valid & frame["process"].ne("")]
    if frame.empty:
        return ()
    ordered = frame.sort_values(["process", "rate", "month"], kind="stable")
    lowest = ordered.drop_duplicates(subset=["process"], keep="first")
    return tuple(
        ProcessMinimum(process=str(process), min_rate=float(rate), month=int(month))
        for process, rate, month in zip(
            lowest["process"], lowest["rate"], lowest["month"], strict=True
        )
    )


def falls_below_threshold(rate: float, threshold: float) -> bool:
    """자동 off 의 경계 — 기준 확보율 **미만**이면 off, 같으면 남는다. 경계는 이 한 곳이다."""
    return rate < threshold


def auto_off_processes(
    minimums: Iterable[ProcessMinimum],
    threshold: float,
    processes: Collection[str],
) -> tuple[ProcessMinimum, ...]:
    """기준 미만인 달이 하나라도 있는 공정. 공정 필터에 둘 수 있는 공정(`processes`)만 본다."""
    allowed = set(processes)
    return tuple(
        minimum
        for minimum in minimums
        if minimum.process in allowed and falls_below_threshold(minimum.min_rate, threshold)
    )


def reqb_process_names(reqb: pd.DataFrame) -> tuple[str, ...]:
    """`RQ_REQB` 의 공정(공백 제거·중복 제거·이름 차례). 프리셋이 받을 수 있는 공정의 전부다."""
    if "공정" not in reqb.columns:
        raise ValueError("RQ_REQB에 공정 컬럼이 없습니다.")
    names = reqb["공정"].astype("string").str.strip().dropna()
    return tuple(sorted({str(name) for name in names if str(name)}))


def inherited_manual_off(
    *,
    previous_processes: Collection[str],
    previous_included: Collection[str],
    previous_auto_off: Collection[str],
    current_processes: Collection[str],
) -> tuple[str, ...]:
    """직전 공식버전에서 사람이 손으로 뺀 공정 가운데 새 데이터에도 있는 것(이름 차례).

    손으로 뺀 공정 = 직전 리비전의 공정 − 직전 프리셋의 포함 공정 − 자동 갱신이 뺀 공정. 새
    데이터에서 처음 생긴 공정은 직전에 빠진 적이 없으므로 이어받지 않는다(포함된다).
    """
    manual = set(previous_processes) - set(previous_included) - set(previous_auto_off)
    return tuple(sorted(manual & set(current_processes)))


def included_after_off(
    processes: Sequence[str],
    auto_off: Collection[str],
    inherited_off: Collection[str],
) -> tuple[str, ...]:
    """공정 필터에 남길 공정 — `RQ_REQB` 공정 − 자동 off − 이어받은 수동 off(입력 차례 그대로)."""
    removed = set(auto_off) | set(inherited_off)
    return tuple(process for process in processes if process not in removed)


def auto_update_memo(*, threshold: float, auto_off_count: int, inherited_off_count: int) -> str:
    """리비전 2·공식버전 메모. 공식버전 기록에 경로 칸이 없어 수동 발행과 가르는 유일한 자리다."""
    return (
        f"자동 갱신 · 기준 확보율 {percent_text(threshold)} · off {auto_off_count}공정 · "
        f"이어받은 수동 off {inherited_off_count}공정"
    )


def official_release_name(scenario_name: str) -> str:
    """수동 발행 폼의 기본 공식버전명과 같은 꼴."""
    return f"{scenario_name} 공식안"


# ---------------------------------------------------------------------------
# 예약
# ---------------------------------------------------------------------------


def scheduled_run_key(day: date) -> str:
    """예약 회차의 선점 키. 날짜 하나에 하나다."""
    return f"scheduled:{day.isoformat()}"


def manual_run_key(now: datetime, token: str) -> str:
    """「지금 실행」 회차의 선점 키. 누를 때마다 다르다(`token` 은 부르는 쪽이 만든 유일값)."""
    return f"manual:{now.isoformat(timespec='seconds')}:{token}"


def scheduled_moment(day: date, check_time: time) -> datetime:
    return datetime.combine(day, time(check_time.hour, check_time.minute))


def next_scheduled_run(now: datetime, check_time: time) -> datetime:
    """`now` 다음에 오는 지정 시각. 지금이 바로 그 시각이면 지금이다."""
    today = scheduled_moment(now.date(), check_time)
    return today if now <= today else today + timedelta(days=1)


def crossed_slot(
    previous: datetime,
    now: datetime,
    check_time: time,
    *,
    tolerance: timedelta = SLOT_TICK_TOLERANCE,
) -> date | None:
    """직전 확인(`previous`)과 지금 사이에 지정 시각이 지나갔으면 그 날. 아니면 None.

    지정 시각은 `(previous, now]` 안에 있어야 한다 — 앱이 뜬 뒤 처음 확인할 때 `previous` 를
    기동 시각으로 두면, 그 전에 지나간 시각은 따라잡지 않는다. 두 확인 사이가 `tolerance` 보다
    길면 그 사이 앱이 잠들었거나 멈춘 것이라 그 시각에 떠 있지 않았던 것으로 보고 넘긴다.
    """
    if now <= previous or now - previous > tolerance:
        return None
    for day in (previous.date(), now.date()):
        moment = scheduled_moment(day, check_time)
        if previous < moment <= now:
            return day
    return None
