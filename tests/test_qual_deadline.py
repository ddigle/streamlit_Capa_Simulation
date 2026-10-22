# Purpose: Qual 마감 계산기 계산이 원본 계산기와 화면 글자·복사 글까지 같은지 검사한다.

"""Qual 마감 계산기 순수 계산(`services/qual_deadline.py`).

**기대값은 손으로 낸 값이 아니다.** 원본 계산기(2026-10-07 HTML)의 `<script>` 를 node 에서 가짜
DOM 위에 그대로 돌려 화면 표 칸·지표·두 복사 글을 뽑아 박았다(2026-10-22, node v22 — 이 시험은
node 없이 돈다). 그래서 이 시험이 깨지면 원본과 다르게 계산하거나 다르게 적는 것이다. 사례는 원본
예시와 경계 다섯이다 — 목표를 비운 달·남는 호기, Cut-off 0·윤년 2월·지난 마감, Cut-off 31·부족,
구분자·반올림 동점(18.125 → 「18.13」)·여유, 빈 입력. 붙여넣기 칸(「표에 넣기」)의 사례도 같은
방법으로 원본의 `bulk-apply` 를 돌려 넣은 달·토스트 글자·복사 글을 뽑았다(2026-10-23).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from capa_simulation.services.qual_deadline import (
    EMPTY_UNITS_MESSAGE,
    EXAMPLE_MONTHS,
    MONTHS_PER_YEAR,
    NO_PASTED_LINES_MESSAGE,
    QualDeadlineInput,
    QualMonthInput,
    check_table_rows,
    cleared_input,
    compute_qual_deadlines,
    example_input,
    format_short_day,
    is_example,
    js_round,
    js_trim,
    month_check_rows,
    parse_number,
    parse_pasted_months,
    split_unit_names,
    tab_separated_text,
    to_fixed,
    unit_result_rows,
    unit_table_rows,
)
from capa_simulation.services.wd_window import wd_window

FAR_FUTURE = date(2999, 12, 31)

CASES: dict[str, QualDeadlineInput] = {
    "example": QualDeadlineInput(
        cutoff_days=10.0,
        year=2027.0,
        base_units=18.0,
        today=date(2026, 10, 7),
        months=(
            QualMonthInput(18.0, ""),
            QualMonthInput(19.0, "U21"),
            QualMonthInput(20.0, "U22"),
            QualMonthInput(20.5, "U23"),
            QualMonthInput(22.0, "U24"),
            QualMonthInput(22.0, ""),
            QualMonthInput(24.0, "U25, U26"),
            QualMonthInput(24.0, ""),
            QualMonthInput(25.0, "U27"),
            QualMonthInput(26.0, "U28"),
            QualMonthInput(26.0, ""),
            QualMonthInput(27.0, "U29"),
        ),
    ),
    "skip_and_leftover": QualDeadlineInput(
        cutoff_days=15.0,
        year=2027.0,
        base_units=5.0,
        today=date(2026, 10, 7),
        months=(
            QualMonthInput(None, "A1 A2"),
            QualMonthInput(6.0, ""),
            QualMonthInput(None, "A3"),
            QualMonthInput(6.4, ""),
            QualMonthInput(8.0, "A4"),
            QualMonthInput(None, ""),
            QualMonthInput(8.0, ""),
            QualMonthInput(9.5, ""),
            QualMonthInput(9.5, ""),
            QualMonthInput(12.0, "A5"),
            QualMonthInput(12.0, ""),
            QualMonthInput(12.0, "A6"),
        ),
    ),
    "cutoff_zero_leap": QualDeadlineInput(
        cutoff_days=0.0,
        year=2028.0,
        base_units=3.0,
        today=date(2028, 3, 15),
        months=(
            QualMonthInput(3.0, ""),
            QualMonthInput(3.3, "L1"),
            QualMonthInput(4.1, "L2"),
            QualMonthInput(5.0, "L3"),
            QualMonthInput(5.0, ""),
            QualMonthInput(5.0, ""),
            QualMonthInput(5.0, ""),
            QualMonthInput(5.0, ""),
            QualMonthInput(5.0, ""),
            QualMonthInput(5.0, ""),
            QualMonthInput(5.0, ""),
            QualMonthInput(5.0, ""),
        ),
    ),
    "cutoff_31_short": QualDeadlineInput(
        cutoff_days=31.0,
        year=2027.0,
        base_units=10.0,
        today=None,
        months=(
            QualMonthInput(11.0, "S1"),
            QualMonthInput(13.0, "S2"),
            QualMonthInput(13.75, ""),
            QualMonthInput(15.0, "S3"),
            QualMonthInput(15.0, ""),
            QualMonthInput(15.0, ""),
            QualMonthInput(15.0, ""),
            QualMonthInput(15.0, ""),
            QualMonthInput(15.0, ""),
            QualMonthInput(15.0, ""),
            QualMonthInput(15.0, ""),
            QualMonthInput(16.0, ""),
        ),
    ),
    "separators_ties": QualDeadlineInput(
        cutoff_days=7.0,
        year=2026.0,
        base_units=18.0,
        today=date(2026, 5, 1),
        months=(
            QualMonthInput(18.125, ""),
            QualMonthInput(17.0, ""),
            QualMonthInput(19.875, "U1;U2  U3\nU4,,U5"),
            QualMonthInput(21.0, ""),
            QualMonthInput(21.005, ""),
            QualMonthInput(20.0, ""),
            QualMonthInput(None, ""),
            QualMonthInput(None, ""),
            QualMonthInput(None, ""),
            QualMonthInput(None, ""),
            QualMonthInput(None, ""),
            QualMonthInput(None, ""),
        ),
    ),
    "empty": QualDeadlineInput(
        cutoff_days=10.0,
        year=2027.0,
        base_units=None,
        today=date(2026, 10, 7),
        months=(
            QualMonthInput(None, ""),
            QualMonthInput(None, ""),
            QualMonthInput(None, ""),
            QualMonthInput(None, ""),
            QualMonthInput(None, ""),
            QualMonthInput(None, ""),
            QualMonthInput(None, ""),
            QualMonthInput(None, ""),
            QualMonthInput(None, ""),
            QualMonthInput(None, ""),
            QualMonthInput(None, ""),
            QualMonthInput(None, ""),
        ),
    ),
}

EXPECTED: dict[str, dict[str, object]] = {
    "example": {
        "units": [
            ("U21", "2월", "1.00", "2027-01-21", "2027-01-22", "", ""),
            ("U22", "3월", "1.00", "2027-02-18", "2027-02-19", "", ""),
            (
                "U23",
                "4월",
                "0.50",
                "2027-04-05",
                "2027-04-06",
                "그 달 일부만 채움, 다음 달부터 1대",
                "",
            ),
            ("U24", "5월", "1.00", "2027-04-20", "2027-04-21", "", ""),
            ("U25", "7월", "1.00", "2027-06-20", "2027-06-21", "", ""),
            ("U26", "7월", "1.00", "2027-06-20", "2027-06-21", "", ""),
            ("U27", "9월", "1.00", "2027-08-21", "2027-08-22", "", ""),
            ("U28", "10월", "1.00", "2027-09-20", "2027-09-21", "", ""),
            ("U29", "12월", "1.00", "2027-11-20", "2027-11-21", "", ""),
        ],
        "checks": [
            ("1월", "(12.21, 01.21] 31일", "18.00", "18.00", "—", "충족", "ok"),
            ("2월", "(01.21, 02.18] 28일", "19.00", "18.00", "+1.00", "충족", "ok"),
            ("3월", "(02.18, 03.21] 31일", "20.00", "19.00", "+1.00", "충족", "ok"),
            ("4월", "(03.21, 04.20] 30일", "20.50", "20.00", "+0.50", "충족", "ok"),
            ("5월", "(04.20, 05.21] 31일", "22.00", "21.00", "+1.00", "충족", "ok"),
            ("6월", "(05.21, 06.20] 30일", "22.00", "22.00", "—", "충족", "ok"),
            ("7월", "(06.20, 07.21] 31일", "24.00", "22.00", "+2.00", "충족", "ok"),
            ("8월", "(07.21, 08.21] 31일", "24.00", "24.00", "—", "충족", "ok"),
            ("9월", "(08.21, 09.20] 30일", "25.00", "24.00", "+1.00", "충족", "ok"),
            ("10월", "(09.20, 10.21] 31일", "26.00", "25.00", "+1.00", "충족", "ok"),
            ("11월", "(10.21, 11.20] 30일", "26.00", "26.00", "—", "충족", "ok"),
            ("12월", "(11.20, 12.21] 31일", "27.00", "26.00", "+1.00", "충족", "ok"),
        ],
        "kpi": ("9", "01.21", "0", "0"),
        "copy_units": (
            "호기\t쓰이는 달\t그 달 기여\tQual 완료 마감\t기여 시작",
            "U21\t2027-02\t1.00\t2027-01-21\t2027-01-22",
            "U22\t2027-03\t1.00\t2027-02-18\t2027-02-19",
            "U23\t2027-04\t0.50\t2027-04-05\t2027-04-06",
            "U24\t2027-05\t1.00\t2027-04-20\t2027-04-21",
            "U25\t2027-07\t1.00\t2027-06-20\t2027-06-21",
            "U26\t2027-07\t1.00\t2027-06-20\t2027-06-21",
            "U27\t2027-09\t1.00\t2027-08-21\t2027-08-22",
            "U28\t2027-10\t1.00\t2027-09-20\t2027-09-21",
            "U29\t2027-12\t1.00\t2027-11-20\t2027-11-21",
        ),
        "copy_months": (
            "월\tW/D 시작(다음 날부터)\tW/D 끝\t목표\t기존+앞달\t이 달 채움\t부족",
            "2027-01\t2026-12-21\t2027-01-21\t18.00\t18.00\t0.00\t0.00",
            "2027-02\t2027-01-21\t2027-02-18\t19.00\t18.00\t1.00\t0.00",
            "2027-03\t2027-02-18\t2027-03-21\t20.00\t19.00\t1.00\t0.00",
            "2027-04\t2027-03-21\t2027-04-20\t20.50\t20.00\t0.50\t0.00",
            "2027-05\t2027-04-20\t2027-05-21\t22.00\t21.00\t1.00\t0.00",
            "2027-06\t2027-05-21\t2027-06-20\t22.00\t22.00\t0.00\t0.00",
            "2027-07\t2027-06-20\t2027-07-21\t24.00\t22.00\t2.00\t0.00",
            "2027-08\t2027-07-21\t2027-08-21\t24.00\t24.00\t0.00\t0.00",
            "2027-09\t2027-08-21\t2027-09-20\t25.00\t24.00\t1.00\t0.00",
            "2027-10\t2027-09-20\t2027-10-21\t26.00\t25.00\t1.00\t0.00",
            "2027-11\t2027-10-21\t2027-11-20\t26.00\t26.00\t0.00\t0.00",
            "2027-12\t2027-11-20\t2027-12-21\t27.00\t26.00\t1.00\t0.00",
        ),
    },
    "skip_and_leftover": {
        "units": [
            (
                "A1",
                "2월",
                "1.00",
                "2027-01-16",
                "2027-01-17",
                "1월에 적은 호기 — 2월에 처음 필요",
                "",
            ),
            (
                "A2",
                "4월",
                "0.40",
                "2027-04-03",
                "2027-04-04",
                "그 달 일부만 채움, 다음 달부터 1대 · 1월에 적은 호기 — 4월에 처음 필요",
                "",
            ),
            (
                "A3",
                "5월",
                "1.00",
                "2027-04-15",
                "2027-04-16",
                "3월에 적은 호기 — 5월에 처음 필요",
                "",
            ),
            (
                "A4",
                "8월",
                "1.00",
                "2027-07-16",
                "2027-07-17",
                "5월에 적은 호기 — 8월에 처음 필요",
                "",
            ),
            ("A5", "10월", "1.00", "2027-09-15", "2027-09-16", "", ""),
            ("A6", "12월", "1.00", "2027-11-15", "2027-11-16", "", ""),
        ],
        "checks": [
            ("1월", "(12.16, 01.16] 31일", "—", "5.00", "—", "목표 없음", "warn"),
            ("2월", "(01.16, 02.13] 28일", "6.00", "5.00", "+1.00", "충족", "ok"),
            ("3월", "(02.13, 03.16] 31일", "—", "6.00", "—", "목표 없음", "warn"),
            ("4월", "(03.16, 04.15] 30일", "6.40", "6.00", "+0.40", "충족", "ok"),
            ("5월", "(04.15, 05.16] 31일", "8.00", "7.00", "+1.00", "충족", "ok"),
            ("6월", "(05.16, 06.15] 30일", "—", "8.00", "—", "목표 없음", "warn"),
            ("7월", "(06.15, 07.16] 31일", "8.00", "8.00", "—", "충족", "ok"),
            ("8월", "(07.16, 08.16] 31일", "9.50", "8.00", "+1.00", "부족 0.50대", "bad"),
            ("9월", "(08.16, 09.15] 30일", "9.50", "9.00", "—", "부족 0.50대", "bad"),
            ("10월", "(09.15, 10.16] 31일", "12.00", "9.00", "+1.00", "부족 2.00대", "bad"),
            ("11월", "(10.16, 11.15] 30일", "12.00", "10.00", "—", "부족 2.00대", "bad"),
            ("12월", "(11.15, 12.16] 31일", "12.00", "10.00", "+1.00", "부족 1.00대", "bad"),
        ],
        "kpi": ("6", "01.16", "0", "5"),
    },
    "cutoff_zero_leap": {
        "units": [
            (
                "L1",
                "2월",
                "0.31",
                "2028-02-20",
                "2028-02-21",
                "그 달 일부만 채움, 다음 달부터 1대 · 마감이 이미 지남",
                "past",
            ),
            (
                "L2",
                "3월",
                "0.13",
                "2028-03-27",
                "2028-03-28",
                "그 달 일부만 채움, 다음 달부터 1대",
                "",
            ),
            (
                "L3",
                "4월에 적음",
                "—",
                "—",
                "—",
                "목표를 채우는 데 쓰이지 않음(이 해 목표가 이미 채워짐)",
                "leftover",
            ),
        ],
        "checks": [
            ("1월", "(12.31, 01.31] 31일", "3.00", "3.00", "—", "충족", "ok"),
            ("2월", "(01.31, 02.29] 29일", "3.30", "3.00", "+0.31", "충족", "ok"),
            ("3월", "(02.29, 03.31] 31일", "4.10", "4.00", "+0.13", "충족", "ok"),
            ("4월", "(03.31, 04.30] 30일", "5.00", "5.00", "—", "충족", "ok"),
            ("5월", "(04.30, 05.31] 31일", "5.00", "5.00", "—", "충족", "ok"),
            ("6월", "(05.31, 06.30] 30일", "5.00", "5.00", "—", "충족", "ok"),
            ("7월", "(06.30, 07.31] 31일", "5.00", "5.00", "—", "충족", "ok"),
            ("8월", "(07.31, 08.31] 31일", "5.00", "5.00", "—", "충족", "ok"),
            ("9월", "(08.31, 09.30] 30일", "5.00", "5.00", "—", "충족", "ok"),
            ("10월", "(09.30, 10.31] 31일", "5.00", "5.00", "—", "충족", "ok"),
            ("11월", "(10.31, 11.30] 30일", "5.00", "5.00", "—", "충족", "ok"),
            ("12월", "(11.30, 12.31] 31일", "5.00", "5.00", "—", "충족", "ok"),
        ],
        "kpi": ("2", "02.20", "1", "0"),
    },
    "cutoff_31_short": {
        "units": [
            ("S1", "1월", "1.00", "2026-11-30", "2026-12-01", "", ""),
            ("S2", "2월", "1.00", "2026-12-31", "2027-01-01", "", ""),
            ("S3", "4월", "1.00", "2027-02-28", "2027-03-01", "", ""),
        ],
        "checks": [
            ("1월", "(11.30, 12.31] 31일", "11.00", "10.00", "+1.00", "충족", "ok"),
            ("2월", "(12.31, 01.28] 28일", "13.00", "11.00", "+1.00", "부족 1.00대", "bad"),
            ("3월", "(01.28, 02.28] 31일", "13.75", "12.00", "—", "부족 1.75대", "bad"),
            ("4월", "(02.28, 03.30] 30일", "15.00", "12.00", "+1.00", "부족 2.00대", "bad"),
            ("5월", "(03.30, 04.30] 31일", "15.00", "13.00", "—", "부족 2.00대", "bad"),
            ("6월", "(04.30, 05.30] 30일", "15.00", "13.00", "—", "부족 2.00대", "bad"),
            ("7월", "(05.30, 06.30] 31일", "15.00", "13.00", "—", "부족 2.00대", "bad"),
            ("8월", "(06.30, 07.31] 31일", "15.00", "13.00", "—", "부족 2.00대", "bad"),
            ("9월", "(07.31, 08.30] 30일", "15.00", "13.00", "—", "부족 2.00대", "bad"),
            ("10월", "(08.30, 09.30] 31일", "15.00", "13.00", "—", "부족 2.00대", "bad"),
            ("11월", "(09.30, 10.30] 30일", "15.00", "13.00", "—", "부족 2.00대", "bad"),
            ("12월", "(10.30, 11.30] 31일", "16.00", "13.00", "—", "부족 3.00대", "bad"),
        ],
        "kpi": ("3", "11.30", "0", "11"),
    },
    "separators_ties": {
        "units": [
            ("U1", "3월", "1.00", "2026-02-21", "2026-02-22", "마감이 이미 지남", "past"),
            (
                "U2",
                "3월",
                "0.90",
                "2026-02-24",
                "2026-02-25",
                "그 달 일부만 채움, 다음 달부터 1대 · 마감이 이미 지남",
                "past",
            ),
            (
                "U3",
                "4월",
                "1.00",
                "2026-03-24",
                "2026-03-25",
                "3월에 적은 호기 — 4월에 처음 필요 · 마감이 이미 지남",
                "past",
            ),
            (
                "U4",
                "5월",
                "0.03",
                "2026-05-23",
                "2026-05-24",
                "그 달 일부만 채움, 다음 달부터 1대 · 3월에 적은 호기 — 5월에 처음 필요",
                "",
            ),
            (
                "U5",
                "3월에 적음",
                "—",
                "—",
                "—",
                "목표를 채우는 데 쓰이지 않음(이 해 목표가 이미 채워짐)",
                "leftover",
            ),
        ],
        "checks": [
            ("1월", "(12.24, 01.24] 31일", "18.13", "18.00", "—", "부족 0.13대", "bad"),
            ("2월", "(01.24, 02.21] 28일", "17.00", "18.00", "—", "충족(여유 1.00)", "ok"),
            ("3월", "(02.21, 03.24] 31일", "19.88", "18.00", "+1.90", "충족", "ok"),
            ("4월", "(03.24, 04.23] 30일", "21.00", "20.00", "+1.00", "충족", "ok"),
            ("5월", "(04.23, 05.24] 31일", "21.00", "21.00", "+0.03", "충족", "ok"),
            ("6월", "(05.24, 06.23] 30일", "20.00", "22.00", "—", "충족(여유 2.00)", "ok"),
            ("7월", "(06.23, 07.24] 31일", "—", "22.00", "—", "목표 없음", "warn"),
            ("8월", "(07.24, 08.24] 31일", "—", "22.00", "—", "목표 없음", "warn"),
            ("9월", "(08.24, 09.23] 30일", "—", "22.00", "—", "목표 없음", "warn"),
            ("10월", "(09.23, 10.24] 31일", "—", "22.00", "—", "목표 없음", "warn"),
            ("11월", "(10.24, 11.23] 30일", "—", "22.00", "—", "목표 없음", "warn"),
            ("12월", "(11.23, 12.24] 31일", "—", "22.00", "—", "목표 없음", "warn"),
        ],
        "kpi": ("4", "02.21", "3", "1"),
        "copy_units": (
            "호기\t쓰이는 달\t그 달 기여\tQual 완료 마감\t기여 시작",
            "U1\t2026-03\t1.00\t2026-02-21\t2026-02-22",
            "U2\t2026-03\t0.90\t2026-02-24\t2026-02-25",
            "U3\t2026-04\t1.00\t2026-03-24\t2026-03-25",
            "U4\t2026-05\t0.03\t2026-05-23\t2026-05-24",
        ),
        "copy_months": (
            "월\tW/D 시작(다음 날부터)\tW/D 끝\t목표\t기존+앞달\t이 달 채움\t부족",
            "2026-01\t2025-12-24\t2026-01-24\t18.13\t18.00\t0.00\t0.13",
            "2026-02\t2026-01-24\t2026-02-21\t17.00\t18.00\t0.00\t0.00",
            "2026-03\t2026-02-21\t2026-03-24\t19.88\t18.00\t1.90\t0.00",
            "2026-04\t2026-03-24\t2026-04-23\t21.00\t20.00\t1.00\t0.00",
            "2026-05\t2026-04-23\t2026-05-24\t21.00\t21.00\t0.03\t0.00",
            "2026-06\t2026-05-24\t2026-06-23\t20.00\t22.00\t0.00\t0.00",
            "2026-07\t2026-06-23\t2026-07-24\t\t22.00\t0.00\t0.00",
            "2026-08\t2026-07-24\t2026-08-24\t\t22.00\t0.00\t0.00",
            "2026-09\t2026-08-24\t2026-09-23\t\t22.00\t0.00\t0.00",
            "2026-10\t2026-09-23\t2026-10-24\t\t22.00\t0.00\t0.00",
            "2026-11\t2026-10-24\t2026-11-23\t\t22.00\t0.00\t0.00",
            "2026-12\t2026-11-23\t2026-12-24\t\t22.00\t0.00\t0.00",
        ),
    },
    "empty": {
        "units": [],
        "checks": [
            ("1월", "(12.21, 01.21] 31일", "—", "0.00", "—", "목표 없음", "warn"),
            ("2월", "(01.21, 02.18] 28일", "—", "0.00", "—", "목표 없음", "warn"),
            ("3월", "(02.18, 03.21] 31일", "—", "0.00", "—", "목표 없음", "warn"),
            ("4월", "(03.21, 04.20] 30일", "—", "0.00", "—", "목표 없음", "warn"),
            ("5월", "(04.20, 05.21] 31일", "—", "0.00", "—", "목표 없음", "warn"),
            ("6월", "(05.21, 06.20] 30일", "—", "0.00", "—", "목표 없음", "warn"),
            ("7월", "(06.20, 07.21] 31일", "—", "0.00", "—", "목표 없음", "warn"),
            ("8월", "(07.21, 08.21] 31일", "—", "0.00", "—", "목표 없음", "warn"),
            ("9월", "(08.21, 09.20] 30일", "—", "0.00", "—", "목표 없음", "warn"),
            ("10월", "(09.20, 10.21] 31일", "—", "0.00", "—", "목표 없음", "warn"),
            ("11월", "(10.21, 11.20] 30일", "—", "0.00", "—", "목표 없음", "warn"),
            ("12월", "(11.20, 12.21] 31일", "—", "0.00", "—", "목표 없음", "warn"),
        ],
        "kpi": ("0", "\u2014", "0", "0"),
        "copy_units": ("호기\t쓰이는 달\t그 달 기여\tQual 완료 마감\t기여 시작",),
        "copy_months": (
            "월\tW/D 시작(다음 날부터)\tW/D 끝\t목표\t기존+앞달\t이 달 채움\t부족",
            "2027-01\t2026-12-21\t2027-01-21\t\t0.00\t0.00\t0.00",
            "2027-02\t2027-01-21\t2027-02-18\t\t0.00\t0.00\t0.00",
            "2027-03\t2027-02-18\t2027-03-21\t\t0.00\t0.00\t0.00",
            "2027-04\t2027-03-21\t2027-04-20\t\t0.00\t0.00\t0.00",
            "2027-05\t2027-04-20\t2027-05-21\t\t0.00\t0.00\t0.00",
            "2027-06\t2027-05-21\t2027-06-20\t\t0.00\t0.00\t0.00",
            "2027-07\t2027-06-20\t2027-07-21\t\t0.00\t0.00\t0.00",
            "2027-08\t2027-07-21\t2027-08-21\t\t0.00\t0.00\t0.00",
            "2027-09\t2027-08-21\t2027-09-20\t\t0.00\t0.00\t0.00",
            "2027-10\t2027-09-20\t2027-10-21\t\t0.00\t0.00\t0.00",
            "2027-11\t2027-10-21\t2027-11-20\t\t0.00\t0.00\t0.00",
            "2027-12\t2027-11-20\t2027-12-21\t\t0.00\t0.00\t0.00",
        ),
    },
}


def _unit_flag(past: bool, leftover: bool) -> str:
    return "past" if past else ("leftover" if leftover else "")


@pytest.mark.parametrize("case", list(CASES))
def test_table_cells_match_the_original_calculator(case: str) -> None:
    result = compute_qual_deadlines(CASES[case])
    expected = EXPECTED[case]

    units = [(*row.cells, _unit_flag(row.past, row.leftover)) for row in unit_table_rows(result)]
    checks = [(*row.cells, row.tone) for row in check_table_rows(result)]
    assert units == expected["units"]
    assert checks == expected["checks"]
    kpis = result.kpis
    assert (
        str(kpis.unit_count),
        format_short_day(kpis.earliest_deadline) if kpis.earliest_deadline else "—",
        str(kpis.past_count),
        str(kpis.short_months),
    ) == expected["kpi"]


@pytest.mark.parametrize("case", ["example", "separators_ties", "empty"])
def test_copy_texts_match_the_original_calculator(case: str) -> None:
    result = compute_qual_deadlines(CASES[case])
    expected = EXPECTED[case]
    unit_lines, month_lines = expected["copy_units"], expected["copy_months"]
    assert isinstance(unit_lines, tuple) and isinstance(month_lines, tuple)

    assert tab_separated_text(unit_result_rows(result)) == "\n".join(unit_lines)
    assert tab_separated_text(month_check_rows(result)) == "\n".join(month_lines)


def test_an_empty_unit_table_is_left_to_the_screen_message() -> None:
    """호기가 하나도 없으면 표 대신 원본의 안내 한 줄이다 — 행을 만들지 않는다."""
    assert unit_table_rows(compute_qual_deadlines(CASES["empty"])) == []
    assert EMPTY_UNITS_MESSAGE == "신규 호기를 적으면 여기에 호기별 Qual 마감이 나옵니다."


@pytest.mark.parametrize("case", list(CASES))
def test_contributions_follow_the_app_window_rule(case: str) -> None:
    """앞 달 호기의 몫은 앱의 W/D 구간 기여(`WdWindow.contribution`)와 같다 — 마감 다음 날부터
    센다."""
    inputs = CASES[case]
    result = compute_qual_deadlines(inputs)
    for check in result.checks:
        window = wd_window(result.year * 100 + check.month, result.cutoff_days)
        assert check.window == window
        earlier = [unit for unit in result.assigned if unit.month < check.month]
        expected = result.base_units + sum(
            window.contribution(unit.contribution_start, FAR_FUTURE) for unit in earlier
        )
        assert check.carried == pytest.approx(expected, abs=1e-12)


def test_a_unit_deadline_is_the_day_before_it_starts_counting() -> None:
    result = compute_qual_deadlines(CASES["example"])
    for unit in result.assigned:
        assert unit.contribution_start == unit.deadline + timedelta(days=1)


@pytest.mark.parametrize(
    ("text", "names"),
    [
        ("U25, U26", ["U25", "U26"]),
        ("U1;U2  U3\nU4,,U5", ["U1", "U2", "U3", "U4", "U5"]),
        (" ,U1\t\r\nU2;　U3 ", ["U1", "U2", "U3"]),
        ("", []),
        (None, []),
        (" , ; ", []),
    ],
)
def test_unit_names_split_like_the_original(text: str | None, names: list[str]) -> None:
    assert split_unit_names(text) == names


@pytest.mark.parametrize(
    ("value", "number"),
    [
        (18, 18.0),
        (20.5, 20.5),
        ("20.5", 20.5),
        (" 1,234.5", 1234.5),
        ("12abc", 12.0),
        (".5", 0.5),
        ("-3", -3.0),
        ("1e2", 100.0),
        ("", None),
        ("abc", None),
        ("Infinity", None),
        (float("nan"), None),
        (float("inf"), None),
        (None, None),
        (True, None),
    ],
)
def test_numbers_read_like_the_original(value: object, number: float | None) -> None:
    assert parse_number(value) == number


@pytest.mark.parametrize(
    ("value", "rounded"),
    [(0.5, 1), (1.5, 2), (2.5, 3), (-2.5, -2), (-0.6, -1), (0.49999999999999994, 0), (7.0, 7)],
)
def test_rounding_is_javascript_math_round(value: float, rounded: int) -> None:
    assert js_round(value) == rounded


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (0.125, "0.13"),
        (18.125, "18.13"),
        (1.005, "1.00"),
        (0.875, "0.88"),
        (2.5, "2.50"),
        (-0.0, "0.00"),
        (-0.001, "-0.00"),
        (-1.125, "-1.13"),
    ],
)
def test_fixed_digits_are_javascript_to_fixed(value: float, text: str) -> None:
    """원본은 `toFixed(2)` 다. 정확히 반에 걸린 이진 값(0.125)은 올리고, 반보다 조금 작은 1.005 는
    내린다."""
    assert to_fixed(value) == text


def test_cutoff_and_year_fall_back_like_the_original() -> None:
    """Cut-off 를 비우면 0, 음수는 0, 소수는 반올림. 연도를 비우면 2027, 직전 달 대수를 비우면 0."""
    result = compute_qual_deadlines(
        QualDeadlineInput(cutoff_days=None, year=None, base_units=None, today=None)
    )
    assert (result.cutoff_days, result.year, result.base_units) == (0, 2027, 0.0)
    assert len(result.checks) == MONTHS_PER_YEAR
    assert all(check.state == "skip" for check in result.checks)
    negative = QualDeadlineInput(cutoff_days=-4, year=2026.4, base_units=1, today=None)
    assert (
        compute_qual_deadlines(negative).cutoff_days,
        compute_qual_deadlines(negative).year,
    ) == (
        0,
        2026,
    )
    half = QualDeadlineInput(cutoff_days=7.5, year=2026, base_units=1, today=None)
    assert compute_qual_deadlines(half).cutoff_days == 8


def test_months_shorter_than_a_year_are_blank_months() -> None:
    short = QualDeadlineInput(
        cutoff_days=10, year=2027, base_units=18, today=None, months=EXAMPLE_MONTHS[:3]
    )
    result = compute_qual_deadlines(short)
    assert [check.state for check in result.checks[3:]] == ["skip"] * (MONTHS_PER_YEAR - 3)
    assert [unit.name for unit in result.assigned] == ["U21", "U22"]


def test_no_today_marks_nothing_past() -> None:
    inputs = CASES["separators_ties"]
    without_today = QualDeadlineInput(
        cutoff_days=inputs.cutoff_days,
        year=inputs.year,
        base_units=inputs.base_units,
        today=None,
        months=inputs.months,
    )
    result = compute_qual_deadlines(without_today)
    assert result.kpis.past_count == 0
    assert not any(row.past for row in unit_table_rows(result))


def test_example_flag_and_clear_follow_the_original() -> None:
    today = date(2026, 10, 22)
    example = example_input(today)
    assert is_example(example, today)
    assert not is_example(example, date(2026, 10, 23))
    edited = QualDeadlineInput(
        cutoff_days=example.cutoff_days,
        year=example.year,
        base_units=example.base_units,
        today=today,
        months=(QualMonthInput(18.0, "U20"), *EXAMPLE_MONTHS[1:]),
    )
    assert not is_example(edited, today)

    cleared = cleared_input(example)
    assert (cleared.cutoff_days, cleared.year, cleared.today) == (10, 2027, today)
    assert cleared.base_units is None
    assert cleared.months == tuple(QualMonthInput() for _ in range(MONTHS_PER_YEAR))
    assert not is_example(cleared, today)


# 원본 「표에 넣기」 를 node 로 돌려 뽑은 값 — (붙여 넣은 글, 넣은 달(목표, 호기 글), 토스트 글자).
PASTE_CASES: dict[str, tuple[str | None, tuple[tuple[float | None, str], ...], str]] = {
    # 둘째 칸부터 끝까지는 띄어쓰기로 이어 호기 글이 된다(편집표 붙여넣기는 셋째 칸을 버린다).
    "columns": ("19.3456\tU1\tU2", ((19.3456, "U1 U2"),), "1개월을 넣었습니다."),
    # 공백뿐인 줄(엑셀의 두 칸이 다 빈 줄 「\t」 도)은 건너뛰어 그 아래 달이 당겨진다.
    "blank lines": ("18\r\n\r\n  \t \n20.5\t\n", ((18.0, ""), (20.5, "")), "2개월을 넣었습니다."),
    "thirteen lines": (
        "\n".join(f"{20 + index}\tV{index}" for index in range(13)),
        tuple((float(20 + index), f"V{index}") for index in range(12)),
        "12개월을 넣었습니다.",
    ),
    "empty": ("", (), NO_PASTED_LINES_MESSAGE),
    "spaces only": (" \n\t\n", (), NO_PASTED_LINES_MESSAGE),
    "none": (None, (), NO_PASTED_LINES_MESSAGE),
    "unreadable target and comma": (
        "abc\tU1\n1,234\t U5 ,U6 ",
        ((None, "U1"), (1234.0, "U5 ,U6")),
        "2개월을 넣었습니다.",
    ),
    # JavaScript `trim` 은 BOM 을 지우고 `\x1c` 는 남긴다(파이썬 `strip` 은 거꾸로다).
    "bom": ("\ufeff18\t\ufeffU1\ufeff", ((18.0, "U1"),), "1개월을 넣었습니다."),
    "information separator": ("\x1c18\tU1\x1c", ((None, "U1\x1c"),), "1개월을 넣었습니다."),
}


@pytest.mark.parametrize("case", sorted(PASTE_CASES))
def test_pasted_lines_fill_months_like_the_original(case: str) -> None:
    text, months, message = PASTE_CASES[case]
    pasted = parse_pasted_months(text)

    assert pasted.months == tuple(QualMonthInput(target, units) for target, units in months)
    assert pasted.message == message


@pytest.mark.parametrize(
    ("text", "trimmed"),
    [
        ("  U1  ", "U1"),
        ("\ufeff\u3000U1\u00a0\n", "U1"),
        ("\x1cU1\x1f", "\x1cU1\x1f"),
        ("\t \r\n", ""),
        ("", ""),
    ],
)
def test_trim_is_javascript_trim(text: str, trimmed: str) -> None:
    assert js_trim(text) == trimmed


def _with_pasted(months: tuple[QualMonthInput, ...], text: str) -> tuple[QualMonthInput, ...]:
    """화면 「표에 넣기」 와 같이 1월부터 붙여 넣은 달만 갈고 그 뒤 달은 둔다."""
    pasted = parse_pasted_months(text).months
    return pasted + months[len(pasted) :]


def test_pasted_months_compute_like_the_original() -> None:
    """예시 위에 세 칸 줄 하나를 넣은 것과, 빈 열두 달에 소수 넷째 자리 목표를 넣은 것 — 원본
    복사 글."""
    example = example_input(None)
    over_example = compute_qual_deadlines(
        QualDeadlineInput(
            cutoff_days=example.cutoff_days,
            year=example.year,
            base_units=example.base_units,
            today=None,
            months=_with_pasted(example.months, "19.3456\tU1\tU2"),
        )
    )
    assert tab_separated_text(unit_result_rows(over_example)).split("\n")[:4] == [
        "호기\t쓰이는 달\t그 달 기여\tQual 완료 마감\t기여 시작",
        "U1\t2027-01\t1.00\t2026-12-21\t2026-12-22",
        "U2\t2027-01\t0.35\t2027-01-10\t2027-01-11",
        "U21\t2027-04\t0.50\t2027-04-05\t2027-04-06",
    ]
    assert month_check_rows(over_example)[1] == [
        "2027-01",
        "2026-12-21",
        "2027-01-21",
        "19.35",
        "18.00",
        "1.35",
        "0.00",
    ]

    blank = tuple(QualMonthInput() for _ in range(MONTHS_PER_YEAR))
    precise = compute_qual_deadlines(
        QualDeadlineInput(
            cutoff_days=10,
            year=2027,
            base_units=18,
            today=None,
            months=_with_pasted(blank, "18.3226\tU1\n19\tU2\tU3"),
        )
    )
    # 18.32 로 잘렸다면 마감 2027-01-11 · 기여 0.32 다(Streamlit 편집표 `step=0.01` 의 자름).
    assert tab_separated_text(unit_result_rows(precise)) == (
        "호기\t쓰이는 달\t그 달 기여\tQual 완료 마감\t기여 시작\n"
        "U1\t2027-01\t0.35\t2027-01-10\t2027-01-11"
    )
    assert [unit.name for unit in precise.leftover] == ["U2", "U3"]
