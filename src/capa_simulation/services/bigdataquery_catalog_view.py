# Purpose: BigDataQuery 시뮬레이션 코드 목록을 표시·검색용으로 정리하고 등록 폼 기본값을 만든다.

"""목록 조회 결과를 화면이 쓰기 좋은 형태로 바꾸는 순수 계층.

Streamlit 을 import 하지 않고 세션 상태도 만지지 않는다. 화면은 여기서 만든 프레임과
값을 표시만 한다 — 계산이 UI 파일로 새면 테스트가 AppTest 없이는 돌지 않는다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Final

import numpy as np
import pandas as pd

from capa_simulation.io.bigdataquery_catalog import CATALOG_COLUMNS
from capa_simulation.io.company_bigdataquery_adapter import is_valid_simulation_code

DISPLAY_COLUMNS: Final[tuple[str, ...]] = (
    "등록여부",
    "저장가능",
    "시뮬레이션 코드",
    "시뮬레이션명",
    "PLAN 코드",
    "PLAN명",
    "원천 등록시각",
)
REGISTERED_LABEL: Final = "등록됨"
UNREGISTERED_LABEL: Final = "미등록"
SAVABLE_LABEL: Final = "가능"
UNSAVABLE_LABEL: Final = "불가"
SCOPE_ALL: Final = "전체"
SCOPE_UNREGISTERED: Final = "미등록만"
SCOPE_REGISTERED: Final = "등록됨만"
SCOPE_OPTIONS: Final[tuple[str, ...]] = (SCOPE_ALL, SCOPE_UNREGISTERED, SCOPE_REGISTERED)
REGISTERED_AT_FORMAT: Final = "%Y-%m-%d %H:%M:%S"
UNSAVABLE_REASON: Final = (
    "이 시뮬레이션 코드에는 영문·숫자와 '.', '_', '-' 외의 문자가 있어 조회·저장에 쓸 수 없습니다."
)
_TEXT_COLUMNS: Final[tuple[str, ...]] = (
    "simulation_name",
    "simulation_code",
    "plan_name",
    "plan_code",
)
_DEFAULT_REVISION_NAME: Final = "초기 리비전"


@dataclass(frozen=True)
class CatalogRow:
    """목록에서 고른 한 행. 화면과 등록 폼 사이를 오가는 유일한 형태다."""

    simulation_code: str
    simulation_name: str
    plan_code: str
    plan_name: str
    registered_at: str
    savable: bool

    @property
    def signature(self) -> str:
        """행을 다시 찾을 때 쓰는 서명.

        코드·PLAN 만으로 찾으면 등록시각만 다른 이웃 행으로 미끄러진다.
        """
        return f"{self.simulation_code}|{self.plan_code}|{self.registered_at}"


@dataclass(frozen=True)
class RegistrationPrefill:
    """고른 행에서 만든 등록 폼 기본값 여섯 칸."""

    simulation_code: str
    source_name: str
    scenario_name: str
    revision_name: str
    registered_at: str
    note: str


def format_registered_at(value: object) -> str:
    """원천 등록시각을 `_optional_datetime` 이 다시 읽을 수 있는 문자열로 만든다.

    실패를 예외가 아니라 빈 문자열로 떨군다 — 목록 조회는 됐는데 한 행의 시각 형식 때문에
    저장만 막히는 형태를 만들지 않기 위해서다. 사용자가 폼에서 직접 채울 수 있다.

    숫자형을 통째로 버리는 이유: `pd.to_datetime` 은 `20260902030405` 를 나노초로 읽어
    1970-01-01 을 돌려주고, 그 값이 조용히 원천 등록시점으로 저장된다.

    문자열은 `pd.to_datetime` 으로 한 번 파싱해 다시 포맷한다. Python 3.10 의
    `datetime.fromisoformat` 은 `Z` 접미사를 거부하는데 저장 경로가 그 함수를 쓴다.
    """
    if value is None or value is pd.NaT:
        return ""
    if isinstance(value, (bool, int, float, np.number)):
        return ""
    if isinstance(value, datetime):
        return value.strftime(REGISTERED_AT_FORMAT)
    if isinstance(value, date):
        return datetime.combine(value, time()).strftime(REGISTERED_AT_FORMAT)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        parsed = pd.to_datetime(text, errors="coerce")
        if not isinstance(parsed, pd.Timestamp) or pd.isna(parsed):
            return ""
        return parsed.strftime(REGISTERED_AT_FORMAT)
    return ""


def normalize_catalog(frame: pd.DataFrame) -> pd.DataFrame:
    """계약 5컬럼을 다듬고 코드·PLAN 조합당 한 행만 남긴다.

    컬럼명은 바꾸지 않는다(사내 결과 계약). `SELECT DISTINCT` 라도 `reg_date` 가 행 단위
    적재시각이면 코드 하나가 수천 행으로 펼쳐지므로 최신 1행만 남긴다.
    """
    missing = [column for column in CATALOG_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError("목록 조회 결과에 필요한 컬럼이 없습니다: " + ", ".join(missing))
    normalized = pd.DataFrame(index=frame.index)
    for column in _TEXT_COLUMNS:
        normalized[column] = frame[column].astype("string").fillna("").str.strip()
    normalized["regist_data"] = [format_registered_at(value) for value in frame["regist_data"]]
    normalized = normalized.loc[:, list(CATALOG_COLUMNS)]
    # 등록시각은 고정폭 문자열이라 사전순이 곧 시간순이고 빈 값이 뒤로 간다.
    normalized = normalized.sort_values(
        ["regist_data", "simulation_code", "plan_code"],
        ascending=[False, True, True],
        kind="stable",
    )
    normalized = normalized.drop_duplicates(subset=["simulation_code", "plan_code"], keep="first")
    return normalized.reset_index(drop=True)


def first_registration_dates(frame: pd.DataFrame) -> dict[tuple[str, str], date]:
    """(시뮬레이션 코드, PLAN 코드) 마다 목록 결과에 보인 **가장 이른** 원천 등록일.

    `normalize_catalog` 는 코드·PLAN 당 **최신** 1행만 남긴다(`reg_date` 가 행 단위 적재시각이면
    코드 하나가 수천 행으로 펼쳐진다). 상세 조회 창은 반대로 가장 이른 날부터 덮어야 옛 적재분이
    빠지지 않는다 — 그래서 정리 전 프레임에서 따로 구한다. 읽지 못하는 등록시각은 건너뛴다.
    """
    earliest: dict[tuple[str, str], date] = {}
    if frame.empty or not set(CATALOG_COLUMNS) <= set(frame.columns):
        return earliest
    codes = frame["simulation_code"].astype("string").fillna("").str.strip()
    plans = frame["plan_code"].astype("string").fillna("").str.strip()
    for code, plan, value in zip(codes, plans, frame["regist_data"], strict=True):
        text = format_registered_at(value)
        if not text:
            continue
        day = datetime.strptime(text, REGISTERED_AT_FORMAT).date()
        key = (str(code), str(plan))
        if key not in earliest or day < earliest[key]:
            earliest[key] = day
    return earliest


def code_registration_span(
    catalog: pd.DataFrame,
    first_registered: Mapping[tuple[str, str], date],
    simulation_code: str,
) -> tuple[date, date] | None:
    """한 시뮬레이션 코드가 목록에 보인 (가장 이른, 가장 늦은) 원천 등록일.

    **PLAN 을 가리지 않는다.**

    상세 SQL 은 PLAN 조건 없이 그 코드의 행을 모두 받는다. 기본 창을 고른 줄(코드, PLAN)의
    등록일로만 잡으면 같은 코드의 다른 PLAN 줄 적재분이 창 밖으로 말없이 빠진다(2026-09-29
    리뷰). 가장 늦은 날은 정리된 목록(PLAN 마다 최신 1행)에서, 가장 이른 날은 정리 전에 구해 둔
    `first_registration_dates` 에서 모은다. 읽을 수 있는 등록일이 하나도 없으면 None.
    """
    days: list[date] = [
        day for (code, _plan), day in first_registered.items() if code == simulation_code
    ]
    if not catalog.empty and {"simulation_code", "regist_data"} <= set(catalog.columns):
        same_code = catalog["simulation_code"].astype("string").str.strip().eq(simulation_code)
        for text in catalog.loc[same_code, "regist_data"]:
            formatted = format_registered_at(text)
            if formatted:
                days.append(datetime.strptime(formatted, REGISTERED_AT_FORMAT).date())
    if not days:
        return None
    return min(days), max(days)


def catalog_rows(catalog: pd.DataFrame) -> list[CatalogRow]:
    """계약 프레임을 행 객체로 바꾼다. 행 수·순서를 그대로 유지한다."""
    return [
        CatalogRow(
            simulation_code=str(record["simulation_code"]),
            simulation_name=str(record["simulation_name"]),
            plan_code=str(record["plan_code"]),
            plan_name=str(record["plan_name"]),
            registered_at=str(record["regist_data"]),
            savable=is_valid_simulation_code(str(record["simulation_code"])),
        )
        for record in catalog.to_dict(orient="records")
    ]


def build_display_frame(
    catalog: pd.DataFrame,
    *,
    registered_codes: Collection[str],
) -> pd.DataFrame:
    """화면에 그릴 7컬럼. 행 수·행 순서는 입력과 같다.

    숨김 컬럼을 만들지 않는다 — 보이는 표와 선택 위치가 1:1 이어야 한다.
    """
    known = set(registered_codes)
    rows = catalog_rows(catalog)
    return pd.DataFrame(
        {
            "등록여부": [
                REGISTERED_LABEL if row.simulation_code in known else UNREGISTERED_LABEL
                for row in rows
            ],
            "저장가능": [SAVABLE_LABEL if row.savable else UNSAVABLE_LABEL for row in rows],
            "시뮬레이션 코드": [row.simulation_code for row in rows],
            "시뮬레이션명": [row.simulation_name for row in rows],
            "PLAN 코드": [row.plan_code for row in rows],
            "PLAN명": [row.plan_name for row in rows],
            "원천 등록시각": [row.registered_at for row in rows],
        },
        columns=list(DISPLAY_COLUMNS),
    )


def filter_catalog(
    catalog: pd.DataFrame,
    *,
    keyword: str,
    scope: str,
    registered_codes: Collection[str],
) -> pd.DataFrame:
    """검색어·표시범위로 좁힌 계약 프레임 사본. 위치 인덱스를 다시 매긴다."""
    filtered = catalog
    known = set(registered_codes)
    if scope == SCOPE_UNREGISTERED:
        filtered = filtered.loc[~filtered["simulation_code"].isin(known)]
    elif scope == SCOPE_REGISTERED:
        filtered = filtered.loc[filtered["simulation_code"].isin(known)]
    terms = [term for term in keyword.lower().split() if term]
    if terms:
        haystack = (
            filtered[list(_TEXT_COLUMNS)]
            .astype("string")
            .fillna("")
            .agg(" ".join, axis=1)
            .str.lower()
            if not filtered.empty
            else pd.Series(dtype="string")
        )
        for term in terms:
            filtered = filtered.loc[haystack.str.contains(term, regex=False, na=False)]
            haystack = haystack.loc[filtered.index]
    return filtered.reset_index(drop=True)


def catalog_row_at(catalog: pd.DataFrame, position: int) -> CatalogRow | None:
    """그 런에 그린 프레임의 위치로 행을 되짚는다."""
    if position < 0 or position >= len(catalog):
        return None
    return catalog_rows(catalog.iloc[[position]])[0]


def row_position(catalog: pd.DataFrame, signature: str) -> int | None:
    """행 서명으로 현재 프레임에서의 위치를 다시 찾는다."""
    for position, row in enumerate(catalog_rows(catalog)):
        if row.signature == signature:
            return position
    return None


def registration_prefill(
    row: CatalogRow,
    *,
    catalog_window_label: str,
) -> RegistrationPrefill:
    """고른 행으로 등록 폼 여섯 칸을 채운다.

    시뮬레이션명이 비면 코드를 대신 쓴다 — `CoreDataBatch` 와 `ScenarioCreate` 가 빈
    이름을 거부해서, 비어 있으면 저장 직전에야 실패한다.
    """
    source_name = row.simulation_name.strip() or row.simulation_code
    return RegistrationPrefill(
        simulation_code=row.simulation_code,
        source_name=source_name,
        scenario_name=f"{source_name} ({row.simulation_code})",
        revision_name=_DEFAULT_REVISION_NAME,
        registered_at=row.registered_at,
        # PLAN 을 담을 필드가 저장 계약에 없어 리비전 메모가 유일한 자유 서식 자리다.
        note=(f"원천 PLAN {row.plan_name}({row.plan_code}) · 목록 조회기간 {catalog_window_label}"),
    )


def view_token(*parts: str) -> str:
    """화면 위젯 key 에 섞는 짧은 토큰. 내장 `hash()` 는 프로세스마다 값이 달라 못 쓴다."""
    joined = "\x00".join(parts).encode("utf-8")
    return hashlib.blake2s(joined, digest_size=6).hexdigest()
