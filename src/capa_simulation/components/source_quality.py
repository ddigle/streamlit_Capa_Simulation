# Purpose: 활성 시나리오 원천 78컬럼의 결측률·카디널리티를 계산 전에 보여 준다.

"""원천 품질 프로필.

지금 데이터 결손은 **계산을 다 돌린 뒤 제외 표에서 결과로만** 드러난다. 어느 컬럼이
통째로 비어 오는지, 어느 것이 값이 하나뿐인 상수인지는 계산 **전에** 알 수 있는 것이고,
새 데이터셋을 받았을 때 가장 먼저 봐야 할 화면이다.

`Repository.load_source_profile()` 이 이미 `null_count`·`unique_count` 를 돌려준다 —
새 조인도 새 계산도 없다.

**등급은 글자로도 적는다.** 막대 길이가 결측률을 나르지만 길이만으로는 「전부 비었나」와
「거의 비었나」가 갈리지 않는다. 비어 있음·절반 이상 결측·상수·정상을 컬럼 하나로 따로
두어 정렬과 필터가 되게 한다.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

# 결측률 등급 경계. 확보율 임계와 달리 사용자가 바꾸는 값이 아니라 읽기 보조용 고정값이다.
EMPTY_RATE = 1.0
SPARSE_RATE = 0.5

GRADE_COLUMN = "등급"
MISSING_RATE_COLUMN = "결측률"
DISTINCT_COLUMN = "고유값"


def _grade(missing_rate: float, unique_count: int) -> str:
    if missing_rate >= EMPTY_RATE:
        return "비어 있음"
    if missing_rate >= SPARSE_RATE:
        return "절반 이상 결측"
    if unique_count <= 1:
        return "상수"
    return "정상"


def build_source_quality_table(profile: pd.DataFrame, source_rows: int) -> pd.DataFrame:
    """프로필 원본을 화면용 표로 바꾼다. 행 수가 0 이면 결측률을 만들지 않는다."""
    if profile.empty:
        return pd.DataFrame(columns=["컬럼", MISSING_RATE_COLUMN, DISTINCT_COLUMN, GRADE_COLUMN])

    nulls = pd.to_numeric(profile["null_count"], errors="coerce").fillna(0.0)
    uniques = pd.to_numeric(profile["unique_count"], errors="coerce").fillna(0).astype("int64")
    # 행 수가 0 이면 나눌 수 없다. 0 으로 두면 「전부 채워졌다」로 읽히므로 결측률을 비운다.
    rate = nulls.div(source_rows) if source_rows > 0 else pd.Series(pd.NA, index=profile.index)

    table = pd.DataFrame(
        {
            "컬럼": profile["column_name"].astype("string"),
            "원천 타입": profile["source_dtype"].astype("string"),
            MISSING_RATE_COLUMN: rate,
            DISTINCT_COLUMN: uniques,
        }
    )
    table[GRADE_COLUMN] = [
        _grade(float(value) if pd.notna(value) else 0.0, int(unique))
        for value, unique in zip(table[MISSING_RATE_COLUMN], table[DISTINCT_COLUMN], strict=True)
    ]
    # 나쁜 것이 위로 온다. 새 데이터셋을 받았을 때 스크롤 없이 문제부터 보이게 한다.
    return table.sort_values(
        [MISSING_RATE_COLUMN, DISTINCT_COLUMN],
        ascending=[False, True],
        na_position="last",
    ).reset_index(drop=True)


def render_source_quality(profile: pd.DataFrame, source_rows: int) -> None:
    """78컬럼 품질 표. 막대는 셀 안에 넣어 표 하나로 끝낸다."""
    table = build_source_quality_table(profile, source_rows)
    if table.empty:
        st.info("이 시나리오에는 원천 컬럼 프로필이 없습니다.")
        return

    problem_count = int((table[GRADE_COLUMN] != "정상").sum())
    if problem_count:
        st.warning(
            f"{len(table):,}개 컬럼 중 {problem_count:,}개가 비어 있거나 상수입니다. "
            "계산에 쓰는 컬럼이면 제외 목록으로 나타납니다."
        )
    else:
        st.success(f"{len(table):,}개 컬럼 모두 값이 차 있고 상수 컬럼이 없습니다.")

    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        height=min(560, max(180, (len(table) + 1) * 36 + 4)),
        key="source_quality_table",
        column_config={
            "컬럼": st.column_config.TextColumn(width="large"),
            "원천 타입": st.column_config.TextColumn(width="small"),
            # 막대 길이가 곧 결측률이다. 78줄을 훑을 때 숫자보다 먼저 눈에 들어온다.
            MISSING_RATE_COLUMN: st.column_config.ProgressColumn(
                format="percent",
                width="medium",
                min_value=0.0,
                max_value=1.0,
            ),
            DISTINCT_COLUMN: st.column_config.NumberColumn(format="%,d", width="small"),
            GRADE_COLUMN: st.column_config.TextColumn(width="small"),
        },
    )
    st.caption(
        f"결측률 {EMPTY_RATE:.0%} 는 `비어 있음`, {SPARSE_RATE:.0%} 이상은 `절반 이상 결측`, "
        "고유값이 1 이면 `상수` 입니다. 등급을 글자로도 적어 색만으로 읽지 않게 했습니다. "
        f"기준 행 수는 원천 {source_rows:,}행입니다."
    )
