# Purpose: Per-session active scenario built from editable reference tables.

"""Per-session active scenario built from editable reference tables."""

from typing import TypedDict, cast
from uuid import uuid4

import pandas as pd
import streamlit as st

from capa_simulation import settings
from capa_simulation.frame_sharing import frame_is_locked, shared_view

ACTIVE_SCENARIO_KEY = "active_scenario"
# 이 세션에서 복제 등록한 가상 제품 목록. 리비전을 저장할 때 함께 기록해
# 공식버전 발행 시 실적과 대조할 수 없는 데이터가 섞였는지 알 수 있게 한다.
VIRTUAL_PRODUCTS_KEY = "session_virtual_products"
EDITABLE_SCENARIO_TABLES = (
    "RQ_PKG_PLAN",
    "RQ_YLD",
    # 가상 제품(기존 제품 복제 등록)이 행을 추가해야 하므로 편집 대상이다.
    # 월 축이 없어 scenario_month_table 이 아니라 scenario_table 로 읽는다.
    "RQ_CHIP_QTY",
    "RQ_CHIP_EQ",
    "RQ_UPEH",
    "RQ_RUN_RATE",
    "RQ_VITAL",
    "RQ_RUN_DAY",
    "RQ_LOT_RATIO",
    "RQ_WF_RATIO",
    "RQ_REQB",
    "RQ_EQP_OWN",
    "RQ_EQP_LENT",
    "RQ_EQP_AVBL",
)


class ActiveScenario(TypedDict):
    reference_version: int
    revision: int
    # 테이블 내용이 바뀔 때마다 새로 발급하는 식별자다. `revision` 은 저장본과 비교해
    # 미저장 변경을 감지하는 카운터여서 서로 다른 내용이 같은 번호를 가질 수 있다.
    # (세션 편집은 0,1,2... 로 올라가고 저장 리비전을 불러오면 그 번호가 그대로 들어온다.)
    # 계산 캐시 키에는 반드시 이 토큰을 쓴다. 편집이 없는 상태는 리비전에서 나온 고정
    # 토큰이라(`pristine_content_token`) 세션이 달라도 같은 내용이면 캐시를 나눠 쓴다.
    content_token: str
    tables: dict[str, pd.DataFrame]


# 편집 없는 상태의 토큰 접두어. uuid hex 에 나올 수 없는 글자라 편집 토큰과 겹치지 않는다.
PRISTINE_TOKEN_PREFIX = "pristine-"


def _new_content_token() -> str:
    return uuid4().hex


def _session_copy(frame: pd.DataFrame) -> pd.DataFrame:
    """편집본 표 하나. 잠긴 원본이면 겉껍데기 사본, 아니면 깊은 사본이다(AGENTS 5장 20).

    시나리오를 여는 길은 원본(세션에 올린 리비전 표 — 공용 칸과 같은 배열)을 잠가 두므로
    (`reference_cache.activate_persisted_reference_tables`) 편집본은 같은 배열을 함께 쓰고
    프레임 · 축 객체만 새로 갖는다. 편집 적용은 표를 통째로 갈아 끼우므로
    (`apply_month_updates` · `apply_table_updates`) 원본 · 다른 세션에 닿지 않고, 숨은 제자리
    쓰기는 잠긴 배열에서 바로 터진다. 스위치(`settings.SHARE_SESSION_TABLES_ENV`)를 끈 서버나
    잠기지 않은 표는 깊은 사본이다.
    """
    if settings.share_session_tables_enabled() and frame_is_locked(frame):
        return shared_view(frame)
    return frame.copy(deep=True)


def pristine_content_token(reference_version: int) -> str:
    """저장 리비전을 편집 없이 올린 상태의 토큰. 내용이 리비전 하나로 정해지므로 고정한다.

    `reference_version` 은 리비전 ID 에서 나오고 리비전은 append-only 라, 같은 값이면 편집
    14표가 같다. 세션마다 uuid 를 새로 발급하면 같은 공식버전을 여는데도 새로고침할
    때마다 계산 캐시가 빗나가 전체를 다시 계산했다(샘플 관측, 70공정: 새로고침 6.2초 중
    계산 4.1초). 편집이 들어가면 `_new_content_token()` 으로 갈라지므로 편집본과 섞이지
    않는다.
    """
    return f"{PRISTINE_TOKEN_PREFIX}{reference_version}"


def is_pristine_content_token(token: str) -> bool:
    """편집 없는 리비전 상태의 토큰인가. 이런 상태의 결과만 세션끼리 나눌 값어치가 있다."""
    return token.startswith(PRISTINE_TOKEN_PREFIX)


def ensure_active_scenario(
    reference_tables: dict[str, pd.DataFrame],
    reference_version: int,
) -> ActiveScenario:
    """Return the current session scenario, initializing it from DuckDB if needed."""
    saved = st.session_state.get(ACTIVE_SCENARIO_KEY)
    if _is_current_scenario(saved, reference_version):
        scenario = cast(ActiveScenario, saved)
        # 이 필드를 도입하기 전에 만들어진 세션 상태에는 토큰이 없다. 편집 중인 표를
        # 버리지 않도록 폐기하지 않고 채워 넣는다.
        if not isinstance(scenario.get("content_token"), str):
            scenario["content_token"] = _new_content_token()
            st.session_state[ACTIVE_SCENARIO_KEY] = scenario
        return scenario
    return reset_active_scenario(reference_tables, reference_version)


def reset_active_scenario(
    reference_tables: dict[str, pd.DataFrame],
    reference_version: int,
) -> ActiveScenario:
    """편집 표를 모두 올라와 있는 원본의 새 편집본으로 갈아 끼운다(`_session_copy`)."""
    missing = [name for name in EDITABLE_SCENARIO_TABLES if name not in reference_tables]
    if missing:
        raise KeyError(f"활성 시나리오 기준정보가 없습니다: {', '.join(missing)}")

    saved = st.session_state.get(ACTIVE_SCENARIO_KEY)
    previous_revision = int(saved.get("revision", -1)) if isinstance(saved, dict) else -1
    scenario: ActiveScenario = {
        "reference_version": reference_version,
        "revision": previous_revision + 1,
        "content_token": pristine_content_token(reference_version),
        "tables": {
            name: _session_copy(reference_tables[name]) for name in EDITABLE_SCENARIO_TABLES
        },
    }
    _retire_edit_cell(saved)
    st.session_state[ACTIVE_SCENARIO_KEY] = scenario
    # 시나리오 자체가 바뀌므로 이 세션의 가상 제품 등록 이력도 함께 버린다.
    clear_virtual_products()
    return scenario


def session_virtual_products() -> tuple[object, ...]:
    """이 세션이 복제 등록한 가상 제품 목록을 돌려준다."""
    saved = st.session_state.get(VIRTUAL_PRODUCTS_KEY)
    return tuple(saved) if isinstance(saved, tuple | list) else ()


def remember_virtual_product(record: object) -> None:
    """복제 등록 한 건을 세션 목록에 더한다."""
    st.session_state[VIRTUAL_PRODUCTS_KEY] = (*session_virtual_products(), record)


def clear_virtual_products() -> None:
    """시나리오를 원본이나 저장 리비전으로 갈아끼울 때 목록을 비운다."""
    st.session_state.pop(VIRTUAL_PRODUCTS_KEY, None)


def clear_active_scenario() -> None:
    """Discard the current session scenario so it reloads from source on next use."""
    _retire_edit_cell(st.session_state.pop(ACTIVE_SCENARIO_KEY, None))


def activate_scenario_tables(
    reference_tables: dict[str, pd.DataFrame],
    reference_version: int,
    revision: int,
) -> ActiveScenario:
    """Replace the active calculation tables with one loaded persistent revision."""
    missing = [name for name in EDITABLE_SCENARIO_TABLES if name not in reference_tables]
    if missing:
        raise KeyError(f"불러온 리비전에 기준정보가 없습니다: {', '.join(missing)}")
    scenario: ActiveScenario = {
        "reference_version": reference_version,
        "revision": revision,
        "content_token": pristine_content_token(reference_version),
        "tables": {
            name: _session_copy(reference_tables[name]) for name in EDITABLE_SCENARIO_TABLES
        },
    }
    _retire_edit_cell(st.session_state.get(ACTIVE_SCENARIO_KEY))
    st.session_state[ACTIVE_SCENARIO_KEY] = scenario
    # 시나리오 자체가 바뀌므로 이 세션의 가상 제품 등록 이력도 함께 버린다.
    clear_virtual_products()
    return scenario


def scenario_table(scenario: ActiveScenario, table_name: str) -> pd.DataFrame:
    """Return an isolated copy of one active scenario table."""
    if table_name not in scenario["tables"]:
        raise KeyError(f"활성 시나리오 테이블이 없습니다: {table_name}")
    return scenario["tables"][table_name].copy(deep=True)


def scenario_month_table(
    scenario: ActiveScenario,
    table_name: str,
    start_month: int,
    end_month: int,
) -> pd.DataFrame:
    """Filter an active table first and copy only rows in the selected month range."""
    if table_name not in scenario["tables"]:
        raise KeyError(f"활성 시나리오 테이블이 없습니다: {table_name}")
    from capa_simulation.services.month_filter import filter_month_range

    return filter_month_range(
        scenario["tables"][table_name],
        start_month,
        end_month,
        table_name,
    )


def _retire_edit_cell(previous: object) -> None:
    """갈아끼워지거나 버려지는 활성 시나리오가 **편집본**이면 그 전체 기간 결과 칸 하나를 걷는다.

    편집 토큰은 uuid 라 이 세션의 그 편집본만 쓰고, 활성 시나리오가 다른 내용으로 바뀌면 아무도
    다시 부르지 않는다 — 그대로 두면 죽은 편집본 칸이 상한(`FULL_CAPACITY_MAX_ENTRIES`)까지 남아
    세션끼리 나누는 리비전 칸을 밀어낸다. 바꾸는 길 넷(편집 적용 `_next_edit_token` · 원본 되돌리기
    `reset_active_scenario` · 리비전 불러오기 · 저장 뒤 활성화 `activate_scenario_tables`)과 버리는
    길(`clear_active_scenario`)이 부른다. 키는 **갈아끼워지는 dict 의** (reference_version,
    content_token)이다 — 다른 리비전을 불러올 때는 새 번호와 다르다. pristine 토큰 칸(세션끼리
    나누는 리비전 결과)은 걷지 않는다. 부르는 쪽은 새 시나리오를 다 지은 뒤 세션에 넣기 바로 앞에
    부른다 — 짓다 막히면(`KeyError` · `ValueError`) 아무 칸도 걷지 않는다. 걷은 뒤 옛 dict 로 계산을
    다시 부르면 그 칸을 한 번 더 계산할 뿐 값은 같다 — 편집 적용 길은 곧바로 앱 전체 회차를 다시
    돌린다는 것을 `tests/test_edit_token_retire.py` 의 정적 그물이 보고, 되돌리기 · 불러오기 ·
    저장 뒤 · 버리기를 부르는 곳(콜백 · `st.rerun` · 알림만 남기는 관리 화면)은 그물 없이 코드로
    따라갔다.
    편집본을 쥔 채 끝난 세션의 칸은 상한에서 밀릴 때까지 남는다.
    """
    if not isinstance(previous, dict):
        return
    old_token = previous.get("content_token")
    old_version = previous.get("reference_version")
    if (
        isinstance(old_token, str)
        and isinstance(old_version, int)
        and not is_pristine_content_token(old_token)
    ):
        from capa_simulation.services.simulation_cache import retire_full_capacity_outcome

        retire_full_capacity_outcome((old_version, old_token))


def _next_edit_token(previous: ActiveScenario) -> str:
    """편집 적용의 새 내용 토큰. 갈아끼워지는 편집본 칸은 여기서 걷는다(`_retire_edit_cell`).

    적용하는 길은 모두 적용 뒤 곧바로 앱 전체 회차를 다시 돌려(`st.rerun` · `DialogHost.finish`) 옛
    토큰으로 계산을 부르지 않는다(`tests/test_edit_token_retire.py`). 표를 다 갈아끼운 뒤에 부른다
    — 적용이 막히면(`ValueError`) 아무 칸도 걷지 않는다.
    """
    _retire_edit_cell(previous)
    return _new_content_token()


def apply_month_updates(
    scenario: ActiveScenario,
    replacements: dict[str, pd.DataFrame],
    start_month: int,
    end_month: int,
) -> ActiveScenario:
    """Atomically replace selected-month rows and publish a new scenario revision."""
    tables = dict(scenario["tables"])
    for table_name, replacement in replacements.items():
        if table_name not in tables:
            raise KeyError(f"활성 시나리오 테이블이 없습니다: {table_name}")
        tables[table_name] = replace_month_range(
            tables[table_name],
            replacement,
            start_month,
            end_month,
            table_name,
        )

    updated: ActiveScenario = {
        "reference_version": scenario["reference_version"],
        "revision": scenario["revision"] + 1,
        "content_token": _next_edit_token(scenario),
        "tables": tables,
    }
    st.session_state[ACTIVE_SCENARIO_KEY] = updated
    return updated


def apply_table_updates(
    scenario: ActiveScenario,
    replacements: dict[str, pd.DataFrame],
) -> ActiveScenario:
    """월 범위를 가리지 않고 테이블 전체를 원자적으로 교체하고 새 토큰을 발급한다.

    `apply_month_updates` 는 선택 월 구간만 갈아끼우므로 `생산계획년월` 이 없는 테이블
    (`RQ_CHIP_QTY`·`RQ_CHIP_EQ`)에는 쓸 수 없다. 가상 제품 복제처럼 완성된 테이블을
    통째로 넘기는 경우를 위한 경로다.
    """
    tables = dict(scenario["tables"])
    for table_name, replacement in replacements.items():
        if table_name not in tables:
            raise KeyError(f"활성 시나리오 테이블이 없습니다: {table_name}")
        tables[table_name] = replacement.reset_index(drop=True)

    updated: ActiveScenario = {
        "reference_version": scenario["reference_version"],
        "revision": scenario["revision"] + 1,
        "content_token": _next_edit_token(scenario),
        "tables": tables,
    }
    st.session_state[ACTIVE_SCENARIO_KEY] = updated
    return updated


def replace_month_range(
    current: pd.DataFrame,
    replacement: pd.DataFrame,
    start_month: int,
    end_month: int,
    table_name: str,
) -> pd.DataFrame:
    """Replace only the selected month range while preserving every other month."""
    if start_month > end_month:
        raise ValueError("활성 시나리오 적용 시작월이 종료월보다 늦습니다.")
    for data, label in ((current, "기존값"), (replacement, "편집값")):
        if "생산계획년월" not in data.columns:
            raise ValueError(f"{table_name} {label}에 생산계획년월 컬럼이 없습니다.")

    missing_columns = [column for column in current.columns if column not in replacement]
    if missing_columns:
        raise ValueError(
            f"{table_name} 편집값에 원본 컬럼이 없습니다: {', '.join(missing_columns)}"
        )

    current_months = _normalize_months(current["생산계획년월"], table_name, "기존값")
    replacement_months = _normalize_months(replacement["생산계획년월"], table_name, "편집값")
    outside_replacement = ~replacement_months.between(start_month, end_month)
    if outside_replacement.any():
        raise ValueError(f"{table_name} 편집값에 선택 범위 밖의 년월이 있습니다.")

    preserved = current.loc[~current_months.between(start_month, end_month)].copy()
    selected = replacement.reindex(columns=current.columns).copy()
    concat_frames = [frame.dropna(axis="columns", how="all") for frame in (preserved, selected)]
    result = pd.concat(concat_frames, ignore_index=True).reindex(columns=current.columns)
    result["생산계획년월"] = _normalize_months(result["생산계획년월"], table_name, "통합값")
    return result.sort_values("생산계획년월", kind="stable").reset_index(drop=True)


def _normalize_months(series: pd.Series, table_name: str, label: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.notna() & numeric.mod(1).eq(0)
    months = numeric.fillna(0).astype("int64")
    valid &= months.mod(100).between(1, 12)
    if not valid.all():
        raise ValueError(f"{table_name} {label}의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    return months


def _is_current_scenario(value: object, reference_version: int) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("reference_version") != reference_version:
        return False
    tables = value.get("tables")
    return isinstance(tables, dict) and all(
        isinstance(tables.get(name), pd.DataFrame) for name in EDITABLE_SCENARIO_TABLES
    )
