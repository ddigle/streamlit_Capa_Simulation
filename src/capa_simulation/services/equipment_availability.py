"""Equipment input validation, weekly availability, and space status."""

from __future__ import annotations

from datetime import date

import pandas as pd

BASELINE_COLUMNS = ("공정", "분류", "기존보유대수", "비고")
EQUIPMENT_COLUMNS = (
    "호기",
    "공정대분류",
    "공정소분류",
    "라인구분",
    "활용구분",
    "사업부",
    "투자기준",
    "Maker",
    "모델",
    "분류1",
    "분류2",
    "분류3",
    "동",
    "층",
    "X좌표",
    "Y좌표",
    "Xsize",
    "Ysize",
    "제진대일정",
    "물류일정",
    "입고일정",
    "Qual일정",
    "확정상태",
    "반출일정",
    "이설일",
    "장기보관여부",
    "기존설비여부",
    "호기이력",
    "비고",
    "레이아웃표시",
)
DOWNTIME_COLUMNS = ("호기", "비가동유형", "시작일", "종료일", "상세사유", "비고")
DOWNTIME_KEY_COLUMNS = ("호기", "비가동유형", "시작일")
DATE_COLUMNS = (
    "제진대일정",
    "물류일정",
    "입고일정",
    "Qual일정",
    "반출일정",
    "이설일",
)
SCHEDULE_STAGES = (
    ("제진대일정", "제진대"),
    ("물류일정", "물류"),
    ("입고일정", "입고"),
    ("Qual일정", "Qual"),
    ("반출일정", "반출"),
    ("이설일", "이설"),
)
QUAL_CONFIRMATION_STATUSES = ("계획", "확정", "완료", "지연")
# Backward-compatible public name used by the Space page.
MILESTONES = SCHEDULE_STAGES
EQUIPMENT_STATUSES = (
    "입고 예정",
    "셋업 진행중",
    "가용",
    "반출 예정",
    "이설 예정",
    "보관 설비",
    "운영 비가동",
    "반출 완료",
    "이설 완료",
)
STATUS_COUNT_COLUMNS = {
    "입고 예정": "입고예정대수",
    "셋업 진행중": "셋업중대수",
    "가용": "가용호기대수",
    "반출 예정": "반출예정대수",
    "이설 예정": "이설예정대수",
    "보관 설비": "보관설비대수",
    "운영 비가동": "운영비가동대수",
    "반출 완료": "반출완료대수",
    "이설 완료": "이설완료대수",
}
TRANSITION_EVENT_COLUMNS = (
    "호기",
    "공정대분류",
    "공정소분류",
    "동",
    "층",
    "이전단계",
    "전환단계",
    "전환일",
    "확정상태",
    "일정상태",
    "기준일대비",
)
DOWNTIME_TYPES = ("개발대여", "공사", "고장", "이설", "기타")
WEEKLY_COLUMNS = (
    "Weeknum",
    "주차시작일",
    "주차종료일",
    "공정소분류",
    "기존보유대수",
    "추가설비대수",
    "총대수",
    "가용대수",
    "비가동대수",
    *STATUS_COUNT_COLUMNS.values(),
)
REFERENCE_TEXT_COLUMNS = (
    "공정대분류",
    "라인구분",
    "활용구분",
    "사업부",
    "투자기준",
    "Maker",
    "모델",
    "분류1",
    "분류2",
    "분류3",
    "호기이력",
    "비고",
)
COORDINATE_COLUMNS = ("X좌표", "Y좌표", "Xsize", "Ysize")
FLAG_COLUMNS = ("장기보관여부", "기존설비여부", "레이아웃표시")
VALID_BUILDINGS = tuple(f"C{index}" for index in range(1, 6))
VALID_FLOORS = tuple(f"{index}F" for index in range(1, 7))
SAMPLE_BASELINE_COUNTS = (
    ("Pre B/D", 46.0),
    ("Wafer_Sorter", 18.0),
    ("AVI-CoW", 21.0),
    ("Laser Grooving", 16.0),
    ("Wafer Grinding", 14.0),
    ("Wafer Mount", 12.0),
    ("Wafer Saw", 19.0),
    ("Plasma Clean", 25.0),
    ("DAF Attach", 35.0),
    ("Die Attach", 42.0),
    ("TC Bonding", 51.0),
    ("Mass Reflow", 18.0),
    ("Underfill", 38.0),
    ("Mold", 27.0),
    ("Cure", 13.0),
    ("Laser Marking", 15.0),
    ("Ball Attach", 32.0),
    ("Flux Clean", 17.0),
    ("Singulation", 29.0),
    ("Package Sorter", 20.0),
    ("Burn-In", 48.0),
    ("Final Test", 44.0),
    ("AVI-PKG", 23.0),
    ("O/S Test", 18.0),
    ("Taping", 16.0),
    ("Packing", 12.0),
    ("X-Ray", 26.0),
    ("SAM", 22.0),
    ("Warpage", 19.0),
    ("Shipping Inspection", 10.0),
)


def empty_equipment_baseline() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": pd.Series(dtype="string"),
            "분류": pd.Series(dtype="string"),
            "기존보유대수": pd.Series(dtype="float64"),
            "비고": pd.Series(dtype="string"),
        }
    )


def empty_equipment_master() -> pd.DataFrame:
    return pd.DataFrame(
        {
            column: pd.Series(
                dtype=(
                    "datetime64[ns]"
                    if column in DATE_COLUMNS
                    else "float64"
                    if column in COORDINATE_COLUMNS
                    else "string"
                )
            )
            for column in EQUIPMENT_COLUMNS
        }
    )


def empty_downtime_schedule() -> pd.DataFrame:
    return pd.DataFrame(
        {
            column: pd.Series(
                dtype="datetime64[ns]" if column in {"시작일", "종료일"} else "string"
            )
            for column in DOWNTIME_COLUMNS
        }
    )


def sample_equipment_baseline() -> pd.DataFrame:
    """Return a detached baseline copied from the development Core Data sample."""
    return pd.DataFrame(
        {
            "공정": pd.Series([process for process, _ in SAMPLE_BASELINE_COUNTS], dtype="string"),
            "분류": pd.Series(["전체"] * len(SAMPLE_BASELINE_COUNTS), dtype="string"),
            "기존보유대수": pd.Series(
                [count for _, count in SAMPLE_BASELINE_COUNTS], dtype="float64"
            ),
            "비고": pd.Series(
                ["Core Data 개발 샘플"] * len(SAMPLE_BASELINE_COUNTS), dtype="string"
            ),
        }
    )


def sample_equipment_master(*, anchor_date: date | None = None) -> pd.DataFrame:
    """Return unsaved sample units spanning every active lifecycle status."""
    anchor = pd.Timestamp(anchor_date or date.today()).normalize()
    common = {
        "공정대분류": "B/N",
        "라인구분": "Line-A",
        "활용구분": "양산",
        "사업부": "PKG",
        "투자기준": "샘플",
        "Maker": "Sample Maker",
        "모델": "Sample Model",
        "분류1": "임시 샘플",
        "분류2": None,
        "분류3": None,
        "호기이력": "화면 검토용 샘플",
        "비고": "화면 검토용 샘플 · DB 미저장",
        "레이아웃표시": "Y",
    }
    specifications = (
        # 호기, 공정, 동, 층, X, Y, 제진, 물류, 입고, Qual, 반출, 이설, 보관, 기존
        ("SAMPLE-IN-01", "TC Bonding", "C1", "1F", 5.0, 6.0, 5, 9, 14, 25, None, None, "N", "N"),
        (
            "SAMPLE-SETUP-01",
            "TC Bonding",
            "C1",
            "1F",
            22.0,
            6.0,
            -18,
            -14,
            -8,
            8,
            None,
            None,
            "N",
            "N",
        ),
        (
            "SAMPLE-AVBL-01",
            "Underfill",
            "C2",
            "2F",
            5.0,
            18.0,
            -40,
            -35,
            -30,
            -20,
            None,
            None,
            "N",
            "N",
        ),
        (
            "SAMPLE-OUT-01",
            "Underfill",
            "C2",
            "2F",
            22.0,
            18.0,
            -50,
            -45,
            -40,
            -30,
            12,
            None,
            "N",
            "N",
        ),
        ("SAMPLE-MOVE-01", "Mold", "C3", "1F", 5.0, 30.0, -50, -45, -40, -30, None, 18, "N", "N"),
        (
            "SAMPLE-STORE-01",
            "Mold",
            "C3",
            "1F",
            22.0,
            30.0,
            None,
            None,
            None,
            None,
            None,
            None,
            "Y",
            "N",
        ),
        (
            "SAMPLE-DOWN-01",
            "Mold",
            "C3",
            "1F",
            39.0,
            30.0,
            None,
            None,
            None,
            None,
            None,
            None,
            "N",
            "Y",
        ),
    )
    confirmation_by_equipment = {
        "SAMPLE-IN-01": "계획",
        "SAMPLE-SETUP-01": "확정",
        "SAMPLE-AVBL-01": "완료",
        "SAMPLE-OUT-01": "완료",
        "SAMPLE-MOVE-01": "지연",
    }
    records: list[dict[str, object]] = []
    for (
        equipment_id,
        process,
        building,
        floor,
        x,
        y,
        vibration,
        logistics,
        arrival,
        qual,
        removal,
        relocation,
        storage,
        existing,
    ) in specifications:
        records.append(
            {
                "호기": equipment_id,
                **common,
                "공정소분류": process,
                "동": building,
                "층": floor,
                "X좌표": x,
                "Y좌표": y,
                "Xsize": 12.0,
                "Ysize": 7.0,
                "제진대일정": _offset_date(anchor, vibration),
                "물류일정": _offset_date(anchor, logistics),
                "입고일정": _offset_date(anchor, arrival),
                "Qual일정": _offset_date(anchor, qual),
                "확정상태": confirmation_by_equipment.get(equipment_id),
                "반출일정": _offset_date(anchor, removal),
                "이설일": _offset_date(anchor, relocation),
                "장기보관여부": storage,
                "기존설비여부": existing,
            }
        )
    return prepare_equipment_master(pd.DataFrame(records, columns=EQUIPMENT_COLUMNS))


def sample_downtime_schedule(*, anchor_date: date | None = None) -> pd.DataFrame:
    """Return an unsaved active downtime event for the sample equipment master."""
    anchor = pd.Timestamp(anchor_date or date.today()).normalize()
    return prepare_downtime_schedule(
        pd.DataFrame(
            [
                {
                    "호기": "SAMPLE-DOWN-01",
                    "비가동유형": "고장",
                    "시작일": anchor - pd.Timedelta(days=2),
                    "종료일": anchor + pd.Timedelta(days=5),
                    "상세사유": "화면 검토용 샘플 비가동",
                    "비고": "DB 미저장",
                }
            ],
            columns=DOWNTIME_COLUMNS,
        )
    )


def prepare_equipment_baseline(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize aggregate counts for unidentified legacy equipment."""
    _require_columns(data, BASELINE_COLUMNS, "기존 보유대수")
    result = data.loc[:, BASELINE_COLUMNS].copy()
    result = _drop_blank_rows(result, ("공정", "분류", "기존보유대수"))
    if result.empty:
        return empty_equipment_baseline()
    _normalize_required_text(result, ("공정", "분류"), "기존 보유대수")
    counts = pd.to_numeric(result["기존보유대수"], errors="coerce")
    if not (counts.notna() & counts.ge(0)).all():
        raise ValueError("기존보유대수는 0 이상의 숫자여야 합니다.")
    result["기존보유대수"] = counts.astype("float64")
    result["비고"] = _optional_text(result["비고"])
    duplicated = result.duplicated(["공정", "분류"], keep=False)
    if duplicated.any():
        examples = _key_examples(result.loc[duplicated], ("공정", "분류"))
        raise ValueError(f"기존 보유대수의 공정·분류가 중복되었습니다: {examples}")
    return result.reset_index(drop=True)


def prepare_equipment_master(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate the 29-column equipment master contract."""
    _require_columns(data, EQUIPMENT_COLUMNS, "호기 마스터")
    result = data.loc[:, EQUIPMENT_COLUMNS].copy()
    result = _drop_blank_rows(result, ("호기",))
    if result.empty:
        return empty_equipment_master()

    _normalize_required_text(result, ("호기", "공정소분류"), "호기 마스터")
    for column in REFERENCE_TEXT_COLUMNS + ("동", "층"):
        result[column] = _optional_text(result[column])
    result["확정상태"] = _optional_text(result["확정상태"])
    duplicated = result["호기"].duplicated(keep=False)
    if duplicated.any():
        examples = result.loc[duplicated, "호기"].drop_duplicates().head(5).tolist()
        raise ValueError(f"호기는 중복될 수 없습니다: {examples}")

    for column in FLAG_COLUMNS:
        result[column] = result[column].astype("string").str.strip().str.upper()
        invalid = ~result[column].isin(["Y", "N"])
        if invalid.any():
            examples = result.loc[invalid, "호기"].head(5).tolist()
            raise ValueError(f"{column}는 Y 또는 N이어야 합니다: {examples}")

    for column in COORDINATE_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    _validate_locations_and_coordinates(result)

    for column in DATE_COLUMNS:
        result[column] = _normalize_date(result[column], column)
    ordinary = result["장기보관여부"].eq("N") & result["기존설비여부"].eq("N")
    missing_required_dates = ordinary & (result["입고일정"].isna() | result["Qual일정"].isna())
    if missing_required_dates.any():
        examples = result.loc[missing_required_dates, "호기"].head(5).tolist()
        raise ValueError(
            f"장기보관·기존설비가 아닌 호기는 입고일정과 Qual일정이 필수입니다: {examples}"
        )
    missing_confirmation = ordinary & result["확정상태"].isna()
    if missing_confirmation.any():
        examples = result.loc[missing_confirmation, "호기"].head(5).tolist()
        raise ValueError(f"장기보관·기존설비가 아닌 호기는 Qual 확정상태가 필수입니다: {examples}")
    invalid_confirmation = result["확정상태"].notna() & ~result["확정상태"].isin(
        QUAL_CONFIRMATION_STATUSES
    )
    if invalid_confirmation.any():
        examples = result.loc[invalid_confirmation, "호기"].head(5).tolist()
        raise ValueError(f"확정상태는 계획·확정·완료·지연 중 하나여야 합니다: {examples}")
    invalid_setup_order = (
        result["입고일정"].notna()
        & result["Qual일정"].notna()
        & result["Qual일정"].lt(result["입고일정"])
    )
    invalid_pre_arrival = _invalid_optional_order(result, ("제진대일정", "물류일정", "입고일정"))
    if (invalid_setup_order | invalid_pre_arrival).any():
        examples = result.loc[invalid_setup_order | invalid_pre_arrival, "호기"].head(5).tolist()
        raise ValueError(f"제진대·물류·입고·Qual 일정 순서가 올바르지 않습니다: {examples}")
    both_exit_dates = result["반출일정"].notna() & result["이설일"].notna()
    if both_exit_dates.any():
        examples = result.loc[both_exit_dates, "호기"].head(5).tolist()
        raise ValueError(f"반출일정과 이설일은 동시에 입력할 수 없습니다: {examples}")
    for exit_column in ("반출일정", "이설일"):
        before_arrival = (
            result[exit_column].notna()
            & result["입고일정"].notna()
            & result[exit_column].lt(result["입고일정"])
        )
        if before_arrival.any():
            examples = result.loc[before_arrival, "호기"].head(5).tolist()
            raise ValueError(f"{exit_column}은 입고일정보다 빠를 수 없습니다: {examples}")
    return result.reset_index(drop=True)


def prepare_downtime_schedule(
    data: pd.DataFrame,
    *,
    equipment: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Normalize downtime intervals keyed by equipment, type, and start date."""
    _require_columns(data, DOWNTIME_COLUMNS, "비가동 일정")
    result = data.loc[:, DOWNTIME_COLUMNS].copy()
    result = _drop_blank_rows(result, DOWNTIME_KEY_COLUMNS)
    if result.empty:
        return empty_downtime_schedule()
    _normalize_required_text(result, ("호기", "비가동유형"), "비가동 일정")
    for column in ("상세사유", "비고"):
        result[column] = _optional_text(result[column])
    result["시작일"] = _normalize_date(result["시작일"], "시작일")
    result["종료일"] = _normalize_date(result["종료일"], "종료일")
    if result["시작일"].isna().any():
        raise ValueError("모든 비가동 일정에 시작일을 입력해야 합니다.")
    duplicated = result.duplicated(list(DOWNTIME_KEY_COLUMNS), keep=False)
    if duplicated.any():
        examples = _key_examples(result.loc[duplicated], DOWNTIME_KEY_COLUMNS)
        raise ValueError(f"호기·비가동유형·시작일이 중복되었습니다: {examples}")
    invalid_end = result["종료일"].notna() & result["종료일"].lt(result["시작일"])
    if invalid_end.any():
        examples = _key_examples(result.loc[invalid_end], DOWNTIME_KEY_COLUMNS)
        raise ValueError(f"비가동 종료일은 시작일보다 빠를 수 없습니다: {examples}")
    if equipment is not None:
        prepared_equipment = prepare_equipment_master(equipment)
        unknown = result.loc[~result["호기"].isin(prepared_equipment["호기"]), "호기"]
        if not unknown.empty:
            examples = unknown.drop_duplicates().head(5).tolist()
            raise ValueError(f"호기 마스터에 없는 설비의 비가동 일정이 있습니다: {examples}")
    return result.reset_index(drop=True)


def build_equipment_status_as_of(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    as_of: date,
) -> pd.DataFrame:
    """Return exclusive lifecycle status plus independent owned/available flags."""
    prepared = prepare_equipment_master(equipment)
    prepared_downtime = prepare_downtime_schedule(downtime, equipment=prepared)
    result = prepared.copy()
    if result.empty:
        for column, dtype in (
            ("상태", "string"),
            ("보유여부", "boolean"),
            ("가용여부", "boolean"),
            ("레이아웃반영여부", "boolean"),
            ("비가동유형", "string"),
        ):
            result[column] = pd.Series(dtype=dtype)
        return result

    timestamp = pd.Timestamp(as_of)
    existing = result["기존설비여부"].eq("Y")
    storage = result["장기보관여부"].eq("Y")
    arrived = existing | storage | (result["입고일정"].notna() & result["입고일정"].le(timestamp))
    removal_complete = result["반출일정"].notna() & result["반출일정"].le(timestamp)
    relocation_complete = result["이설일"].notna() & result["이설일"].le(timestamp)
    exited = removal_complete | relocation_complete
    owned = arrived & ~exited
    qualified = existing | (result["Qual일정"].notna() & result["Qual일정"].le(timestamp))

    active_downtime = _active_downtime(prepared_downtime, timestamp)
    reason_by_equipment = active_downtime.groupby("호기")["비가동유형"].agg(_joined_unique)
    result["비가동유형"] = result["호기"].map(reason_by_equipment).astype("string")
    offline = result["비가동유형"].notna() & owned
    available = owned & qualified & ~storage & ~offline

    status = pd.Series("입고 예정", index=result.index, dtype="string")
    status.loc[owned & ~qualified & ~storage] = "셋업 진행중"
    status.loc[available] = "가용"
    status.loc[storage & owned] = "보관 설비"
    status.loc[result["반출일정"].notna() & ~removal_complete] = "반출 예정"
    status.loc[result["이설일"].notna() & ~relocation_complete] = "이설 예정"
    status.loc[offline] = "운영 비가동"
    status.loc[removal_complete] = "반출 완료"
    status.loc[relocation_complete] = "이설 완료"
    result["상태"] = status
    result["보유여부"] = owned.astype("boolean")
    result["가용여부"] = available.astype("boolean")
    result["레이아웃반영여부"] = (result["레이아웃표시"].eq("Y") & ~exited).astype("boolean")
    return result.reset_index(drop=True)


def build_weekly_equipment_availability(
    baseline: pd.DataFrame,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Aggregate owned, available, and lifecycle counts by ISO week and small process."""
    if start_date > end_date:
        raise ValueError("주차별 조회 시작일은 종료일보다 늦을 수 없습니다.")
    prepared_baseline = prepare_equipment_baseline(baseline)
    prepared_equipment = prepare_equipment_master(equipment)
    prepared_downtime = prepare_downtime_schedule(downtime, equipment=prepared_equipment)
    processes = (
        pd.concat([prepared_baseline["공정"], prepared_equipment["공정소분류"]], ignore_index=True)
        .dropna()
        .drop_duplicates()
    )
    if processes.empty:
        return pd.DataFrame(columns=WEEKLY_COLUMNS)

    baseline_counts = prepared_baseline.groupby("공정", observed=True)["기존보유대수"].sum()
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    first_monday = start - pd.Timedelta(days=start.weekday())
    last_monday = end - pd.Timedelta(days=end.weekday())
    rows: list[dict[str, object]] = []
    for week_start in pd.date_range(first_monday, last_monday, freq="7D"):
        week_end = week_start + pd.Timedelta(days=6)
        iso_calendar = week_start.isocalendar()
        weeknum = f"{iso_calendar.year % 100:02d}-W{iso_calendar.week:02d}"
        status = build_equipment_status_as_of(
            prepared_equipment, prepared_downtime, as_of=week_end.date()
        )
        for process in processes.tolist():
            group = status.loc[status["공정소분류"].eq(process)]
            base_count = float(baseline_counts.get(process, 0.0))
            owned_count = int(group["보유여부"].sum())
            available_units = int(group["가용여부"].sum())
            row: dict[str, object] = {
                "Weeknum": weeknum,
                "주차시작일": week_start.date(),
                "주차종료일": week_end.date(),
                "공정소분류": str(process),
                "기존보유대수": base_count,
                "추가설비대수": owned_count,
                "총대수": base_count + owned_count,
                "가용대수": base_count + available_units,
                "비가동대수": owned_count - available_units,
            }
            for status_name, column in STATUS_COUNT_COLUMNS.items():
                row[column] = int(group["상태"].eq(status_name).sum())
            rows.append(row)
    return pd.DataFrame(rows, columns=WEEKLY_COLUMNS)


def build_inactive_equipment(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    as_of: date,
) -> pd.DataFrame:
    """Return owned unit-level equipment that is not currently available."""
    status = build_equipment_status_as_of(equipment, downtime, as_of=as_of)
    if status.empty:
        return status
    return status.loc[status["보유여부"] & ~status["가용여부"]].reset_index(drop=True)


def equipment_stages_as_of(equipment: pd.DataFrame, *, as_of: date) -> pd.Series:
    """Return the lifecycle status without operational downtime input."""
    prepared = prepare_equipment_master(equipment)
    return build_equipment_status_as_of(prepared, empty_downtime_schedule(), as_of=as_of)["상태"]


def build_space_equipment_status(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    as_of: date,
) -> pd.DataFrame:
    """Build the unit-level source used by the Space dashboard."""
    result = build_equipment_status_as_of(equipment, downtime, as_of=as_of)
    result["단계"] = result["상태"]
    return result.reset_index(drop=True)


def build_milestone_transition_events(
    equipment: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
    as_of: date,
) -> pd.DataFrame:
    """Return equipment schedule events inside the selected date range."""
    if start_date > end_date:
        raise ValueError("단계 전환 조회 시작일은 종료일보다 늦을 수 없습니다.")
    prepared = prepare_equipment_master(equipment)
    if prepared.empty:
        return pd.DataFrame(columns=TRANSITION_EVENT_COLUMNS)
    identity_columns = ["호기", "공정대분류", "공정소분류", "동", "층", "확정상태"]
    date_columns = [column for column, _ in SCHEDULE_STAGES]
    events = prepared.melt(
        id_vars=identity_columns,
        value_vars=date_columns,
        var_name="단계컬럼",
        value_name="전환일",
    ).dropna(subset=["전환일"])
    if events.empty:
        return pd.DataFrame(columns=TRANSITION_EVENT_COLUMNS)
    stage_by_column = dict(SCHEDULE_STAGES)
    previous_stage = {
        "제진대일정": "착수 전",
        "물류일정": "제진대",
        "입고일정": "물류",
        "Qual일정": "입고",
        "반출일정": "가용/보관",
        "이설일": "가용/보관",
    }
    order = {column: index for index, column in enumerate(date_columns)}
    events["단계순서"] = events["단계컬럼"].map(order).astype("int64")
    events["이전단계"] = events["단계컬럼"].map(previous_stage).astype("string")
    events["전환단계"] = events["단계컬럼"].map(stage_by_column).astype("string")
    events["전환일"] = pd.to_datetime(events["전환일"], errors="raise")
    events["확정상태"] = events["확정상태"].where(events["단계컬럼"].eq("Qual일정"))
    events = events.loc[
        events["전환일"].between(pd.Timestamp(start_date), pd.Timestamp(end_date), inclusive="both")
    ].copy()
    if events.empty:
        return pd.DataFrame(columns=TRANSITION_EVENT_COLUMNS)
    as_of_timestamp = pd.Timestamp(as_of)
    events["일정상태"] = events["전환일"].le(as_of_timestamp).map({True: "완료", False: "예정"})
    events["기준일대비"] = (
        events["전환일"].sub(as_of_timestamp).dt.days.map(_format_day_difference).astype("string")
    )
    events = events.sort_values(["전환일", "단계순서", "공정소분류", "호기"], kind="stable")
    return events.loc[:, TRANSITION_EVENT_COLUMNS].reset_index(drop=True)


def _validate_locations_and_coordinates(result: pd.DataFrame) -> None:
    layout = result["레이아웃표시"].eq("Y")
    missing_location = layout & (
        result["동"].isna()
        | result["층"].isna()
        | result.loc[:, COORDINATE_COLUMNS].isna().any(axis=1)
    )
    if missing_location.any():
        examples = result.loc[missing_location, "호기"].head(5).tolist()
        raise ValueError(
            f"레이아웃표시 Y 호기는 동·층·좌표·크기를 모두 입력해야 합니다: {examples}"
        )
    invalid_building = result["동"].notna() & ~result["동"].isin(VALID_BUILDINGS)
    invalid_floor = result["층"].notna() & ~result["층"].isin(VALID_FLOORS)
    if (invalid_building | invalid_floor).any():
        examples = result.loc[invalid_building | invalid_floor, "호기"].head(5).tolist()
        raise ValueError(f"동은 C1~C5, 층은 1F~6F 범위여야 합니다: {examples}")
    coordinate_present = result.loc[:, COORDINATE_COLUMNS].notna()
    incomplete = coordinate_present.any(axis=1) & ~coordinate_present.all(axis=1)
    if incomplete.any():
        examples = result.loc[incomplete, "호기"].head(5).tolist()
        raise ValueError(f"Space 좌표와 Xsize·Ysize는 함께 입력해야 합니다: {examples}")
    complete = coordinate_present.all(axis=1)
    invalid = complete & (
        result["X좌표"].lt(0)
        | result["Y좌표"].lt(0)
        | result["Xsize"].le(0)
        | result["Ysize"].le(0)
        | result["X좌표"].add(result["Xsize"]).gt(100)
        | result["Y좌표"].add(result["Ysize"]).gt(60)
    )
    if invalid.any():
        examples = result.loc[invalid, "호기"].head(5).tolist()
        raise ValueError(f"Space 블럭은 X 0~100, Y 0~60 범위 안에 있어야 합니다: {examples}")


def _active_downtime(downtime: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    if downtime.empty:
        return downtime.copy()
    active = downtime["시작일"].le(as_of) & (
        downtime["종료일"].isna() | downtime["종료일"].ge(as_of)
    )
    return downtime.loc[active].copy()


def _invalid_optional_order(data: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    invalid = pd.Series(False, index=data.index)
    for left, right in zip(columns, columns[1:], strict=False):
        invalid |= data[left].notna() & data[right].notna() & data[right].lt(data[left])
    return invalid


def _offset_date(anchor: pd.Timestamp, offset: int | None) -> pd.Timestamp | None:
    return None if offset is None else anchor + pd.Timedelta(days=offset)


def _joined_unique(values: pd.Series) -> str:
    return ", ".join(values.astype("string").drop_duplicates().tolist())


def _format_day_difference(days: int) -> str:
    if days == 0:
        return "D-Day"
    if days > 0:
        return f"D-{days}"
    return f"D+{-days}"


def _require_columns(data: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    missing = [column for column in columns if column not in data.columns]
    if missing:
        raise ValueError(f"{label} 필수 컬럼이 없습니다: {', '.join(missing)}")


def _drop_blank_rows(data: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    present = pd.DataFrame(index=data.index)
    for column in columns:
        values = data[column]
        present[column] = values.notna() & values.astype("string").str.strip().ne("")
    return data.loc[present.any(axis=1)].copy()


def _normalize_required_text(data: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    for column in columns:
        data[column] = data[column].astype("string").str.strip()
        invalid = data[column].isna() | data[column].eq("")
        if invalid.any():
            raise ValueError(f"{label}의 {column}에 누락값이 있습니다.")


def _optional_text(series: pd.Series) -> pd.Series:
    result = series.astype("string").str.strip()
    return result.mask(result.eq(""))


def _normalize_date(series: pd.Series, label: str) -> pd.Series:
    missing = series.isna() | series.astype("string").str.strip().eq("")
    converted = pd.to_datetime(series.mask(missing), errors="coerce")
    invalid = ~missing & converted.isna()
    if invalid.any():
        examples = series.loc[invalid].head(5).tolist()
        raise ValueError(f"{label}은 날짜 형식이어야 합니다: {examples}")
    return converted.dt.normalize()


def _key_examples(data: pd.DataFrame, columns: tuple[str, ...]) -> list[str]:
    return (
        data.loc[:, columns]
        .astype("string")
        .agg(" / ".join, axis=1)
        .drop_duplicates()
        .head(5)
        .tolist()
    )
