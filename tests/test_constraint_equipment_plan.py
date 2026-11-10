# Purpose: 제약 시뮬레이션 두 모드가 함께 쓰는 설비 일정 확인 · 계획 블록(`render_equipment_plan`)의
# 멈추는 갈래 차례와 멈춘 자리 알림, 머리 줄 표지 · 입력 비가동 알림 글 조각을 화면 없이 본다.

"""`components/constraint_equipment_plan` — 멈추는 갈래(순수 호출)와 같은 글 조각.

페이지 시험(`tests/test_constraint_simulation_page.py` ·
`tests/test_modification_schedule_page.py`)은 두 모드의 화면 갈래를 AppTest 로 본다. 여기서는 함수
하나가 두 모드에 같은 갈래 차례를 주는지 — 설비 DB 오류 · 설비 일정이 서지 않음(풀이 주어
`subject`) · 그 모드의 앞 갈래(`before_plan`) · 계획 계산 오류 — 를 머리 그리기와 마크 알림을 적는
가짜로 본다. 계획 받기가 불리면 실패하는 가짜 `simulation_cache` 함수로 「앞 갈래가 멈추면 계획을
받지 않는다」 를 잡는다. 두 모드 머리 줄의 표지(UPEH 가정 미적용)와 입력 비가동 상태 알림
`CS-05` 의 글(합 대수 띠 · 고칠 자리 · 넘친 달)도 여기서 못 박는다.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any, cast

import pandas as pd
import pytest
import streamlit as st

# 공용 블록은 계획 함수를 부를 때 이 모듈에서 찾는다 — 모듈 속성을 바꿔 끼운다.
import capa_simulation.components.constraint_equipment_plan as constraint_equipment_plan
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.components.constraint_equipment_plan import (
    EQUIPMENT_SCREEN,
    MANUAL_DOWNTIME_FIX,
    MANUAL_DOWNTIME_HELP,
    UPEH_NOT_APPLIED_HELP,
    UPEH_NOT_APPLIED_MARK,
    EquipmentPlanSource,
    absent_note,
    applied_marks,
    equipment_readiness,
    manual_downtime_note,
    render_equipment_plan,
)
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.page_bootstrap import ProcessPageInputs
from capa_simulation.persistence.equipment_repository import EquipmentSnapshot
from capa_simulation.services.manual_downtime import MANUAL_DOWNTIME_BAND, ManualDowntime
from capa_simulation.services.process_equipment_timeline import (
    MISSING_CUTOFF,
    NO_COUNTED_UNITS,
    NO_EQUIPMENT,
    NO_SNAPSHOT,
    READY,
    DynamicReadiness,
)
from capa_simulation.upeh_assumption_state import (
    UPEH_ASSUMPTION_DEFAULT_PERCENT,
    UPEH_ASSUMPTION_PERCENT_KEY,
)

PROCESS = "DEMO_Chip_Attach"


class _Recorder:
    """머리 한 줄 · 마크 알림 · 평문 줄을 차례대로 적는다."""

    def __init__(self) -> None:
        self.headers: list[tuple[str, str]] = []
        self.errors: list[dict[str, Any]] = []
        self.captions: list[tuple[str, str | None]] = []

    def header(self, process: str, line: str) -> None:
        self.headers.append((process, line))

    def error(self, message: str, **kwargs: Any) -> None:
        self.errors.append({"message": message, **kwargs})

    def caption(self, body: str, *, help: str | None = None) -> None:
        self.captions.append((body, help))


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    """멈춘 자리의 마크 · 평문 줄을 적는 가짜를 끼운다."""
    written = _Recorder()
    monkeypatch.setattr(constraint_equipment_plan, "render_data_error", written.error)
    monkeypatch.setattr(st, "caption", written.caption)
    return written


class _BrokenSnapshot:
    """계획 키를 만들려고 계산 칸을 꺼내면 깨지는 스냅샷."""

    def calculation_frames(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        raise ValueError("시험 — 계산 칸을 꺼내지 못했습니다")


def _source(*, snapshot: object | None = None, equipment_error: str = "") -> EquipmentPlanSource:
    page_inputs = SimpleNamespace(
        months=(202601, 202602),
        context=SimpleNamespace(active_scenario={"tables": {}}, reference_tables={}),
        thresholds=None,
        capacity_cache_key="key",
    )
    return EquipmentPlanSource(
        page_inputs=cast(ProcessPageInputs, page_inputs),
        snapshot=cast(EquipmentSnapshot, snapshot),
        cutoff=pd.DataFrame(),
        equipment_error=equipment_error,
        today=date(2026, 1, 15),
        manual_downtime=ManualDowntime(),
    )


@pytest.fixture
def no_plan_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    """계획 받기(`simulation_cache` 의 키 · 계획 함수)가 불리면 시험이 실패한다."""

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("멈춘 갈래가 계획을 받았다")

    for name in (
        "required_shortening_cache_key",
        "load_required_shortening_for_target",
        "get_process_equipment_timeline",
    ):
        monkeypatch.setattr(simulation_cache, name, refuse)


def _run(
    source: EquipmentPlanSource,
    readiness: DynamicReadiness | None,
    recorder: _Recorder,
    *,
    subject: str = "개조 일정",
    before_plan: Any = None,
    process: str = PROCESS,
) -> object:
    return render_equipment_plan(
        source,
        readiness,
        process=process,
        process_label=process,
        subject=subject,
        render_header=recorder.header,
        before_plan=before_plan,
    )


def test_readiness_is_none_when_the_equipment_db_failed_or_no_process_is_chosen() -> None:
    assert equipment_readiness(_source(equipment_error="잠김"), PROCESS) is None
    assert equipment_readiness(_source(), None) is None


@pytest.mark.usefixtures("no_plan_loading")
def test_an_equipment_db_error_stops_with_its_own_mark_and_no_other_screen(
    recorder: _Recorder,
) -> None:
    assert _run(_source(equipment_error="설비 DB 가 잠겼습니다."), None, recorder) is None

    ((process, line),) = recorder.headers
    assert process == PROCESS and line.endswith(":blue-badge[설비 일정 없음: 설비 DB 오류]")
    assert recorder.errors == [
        {
            "message": "설비 DB 가 잠겼습니다.",
            "code": "CS-01",
            "text": "설비 일정 없음: 설비 DB 를 읽지 못했습니다",
        }
    ]


@pytest.mark.usefixtures("no_plan_loading")
@pytest.mark.parametrize(
    ("subject", "phrase"),
    [
        (
            "제약 시뮬레이션",
            "제약 시뮬레이션은 설비 일정 기준 가용(공정 Capa 상세 ② 와 같은 값)으로",
        ),
        ("개조 일정", "개조 일정은 설비 일정 기준 가용(공정 Capa 상세 ② 와 같은 값)으로"),
    ],
)
def test_a_process_whose_schedule_cannot_stand_names_the_mode_and_skips_the_mode_branch(
    subject: str, phrase: str, recorder: _Recorder
) -> None:
    """설비 일정이 서지 않으면 그 모드의 앞 갈래(제약 영향의 제품 갈래)보다 먼저 멈춘다 — 마크
    알림의 첫머리와 풀이의 주어만 모드마다 다르다."""
    asked: list[bool] = []

    def before_plan() -> bool:
        asked.append(True)
        return True

    stopped = _run(
        _source(),
        DynamicReadiness(NO_EQUIPMENT, cutoff_days=7),
        recorder,
        subject=subject,
        before_plan=before_plan,
    )

    assert stopped is None and not asked
    (error,) = recorder.errors
    assert error["code"] == "CS-01"
    assert error["text"] == f"{PROCESS} — 설비 일정 없음: 설비 없음"
    # 채울 입력은 가용설비 현황에 있다 — 길은 Alarm 줄의 「그 화면으로」, 자리에는 글이 없다.
    assert error["goto"] == EQUIPMENT_SCREEN
    assert error["message"].startswith(f"{subject} · {literal_markdown(PROCESS)} — ")
    assert phrase in error["message"]
    assert not recorder.captions


@pytest.mark.usefixtures("no_plan_loading")
@pytest.mark.parametrize(
    ("status", "words"),
    [
        (NO_SNAPSHOT, "설비 일정 없음: 저장본 없음"),
        (MISSING_CUTOFF, "설비 일정 없음: Cut-off 미기재"),
        (NO_EQUIPMENT, "설비 일정 없음: 설비 없음"),
    ],
)
def test_a_missing_input_is_a_mark_that_opens_the_equipment_screen(
    status: str, words: str, recorder: _Recorder
) -> None:
    assert _run(_source(), DynamicReadiness(status), recorder) is None

    (error,) = recorder.errors
    assert error["text"].endswith(words) and error["goto"] == EQUIPMENT_SCREEN
    assert not recorder.captions


@pytest.mark.usefixtures("no_plan_loading")
def test_no_snapshot_is_one_alert_whichever_process_is_open(recorder: _Recorder) -> None:
    """저장본 없음은 설비 DB 전체의 일이다 — 글에 공정을 넣으면 공정을 넘길 때마다 Alarm 줄이
    는다. 짧은 글과 전문이 공정과 무관해야 같은 알림 하나다(설계 규칙 UI-NTF-07)."""
    readiness = DynamicReadiness(NO_SNAPSHOT)
    for process in ("DEMO_공정가", "DEMO_공정나"):
        assert _run(_source(), readiness, recorder, process=process) is None

    (one, other) = recorder.errors
    assert one == other
    assert one["text"] == readiness.badge and one["goto"] == EQUIPMENT_SCREEN
    assert one["message"].startswith("개조 일정 — 설비 DB 에 저장된 설비 마스터가 없습니다.")


def test_a_note_about_one_process_names_it() -> None:
    """공정마다 까닭이 다른 멈춤은 줄이 공정마다 따로다 — 어느 공정인지 글이 말한다."""
    note = absent_note("설비 일정 없음: 설비 없음", "까닭", screen="개조 일정", process_label="AVI")

    assert note == ("개조 일정 · AVI — 까닭", "AVI — 설비 일정 없음: 설비 없음")


@pytest.mark.usefixtures("no_plan_loading")
def test_a_process_without_counted_units_is_a_plain_line_not_an_error(
    recorder: _Recorder,
) -> None:
    """HBM·EDP 호기도 기존보유도 없는 공정은 채울 입력이 없는 빈 상태다 — 고를 때마다 Alarm 에
    오류가 쌓이지 않게 평문 한 줄이고 서는 조건은 풍선이다(설계 규칙 UI-TXT-04 · UI-NTF-08).
    저장본 · 이름 · Cut-off 를 다 지난 공정이라 풍선은 이 공정에 빠진 조건만 적고, 평문이 까닭이라
    바로 위 머리 배지는 상태 낱말까지다(UI-TXT-07)."""
    readiness = DynamicReadiness(NO_COUNTED_UNITS, cutoff_days=7)

    assert _run(_source(), readiness, recorder, subject="개조 일정") is None

    assert not recorder.errors
    ((body, help_text),) = recorder.captions
    assert body == readiness.detail
    assert help_text is not None and "개조 일정은 설비 일정 기준 가용" in help_text
    assert "사용기준 HBM·EDP" in help_text and "Cut-off" not in help_text
    ((_, line),) = recorder.headers
    assert line.endswith(":blue-badge[설비 일정 없음]")


@pytest.mark.usefixtures("no_plan_loading")
def test_the_mode_branch_stops_after_the_check_and_before_the_plan(recorder: _Recorder) -> None:
    """판정을 지난 뒤 `before_plan` 이 거짓이면 계획을 받지 않고 멈춘다(까닭은 그 갈래가 그린다)."""
    stopped = _run(
        _source(snapshot=_BrokenSnapshot()),
        DynamicReadiness(READY, cutoff_days=7, has_units=True),
        recorder,
        subject="제약 시뮬레이션",
        before_plan=lambda: False,
    )

    assert stopped is None
    assert not recorder.headers and not recorder.errors


def test_a_failure_while_building_the_plan_key_is_the_plan_error(recorder: _Recorder) -> None:
    """계획 키를 만드는 단계(계산 칸 꺼내기)에서 깨져도 「설비 일정을 계산하지 못했습니다」 갈래다 —
    두 모드가 같은 `try` 를 쓴다(제약 영향 모드는 합치기 전에는 키 만들기가 `try` 밖이었다)."""
    stopped = _run(
        _source(snapshot=_BrokenSnapshot()),
        DynamicReadiness(READY, cutoff_days=7, has_units=True),
        recorder,
        subject="제약 시뮬레이션",
        before_plan=lambda: True,
    )

    assert stopped is None
    ((_, line),) = recorder.headers
    assert line.endswith(":blue-badge[설비 일정 없음: 계산 오류]")
    (error,) = recorder.errors
    assert error["message"].startswith("설비 일정을 계산하지 못했습니다 — ")
    assert "계산 칸을 꺼내지 못했습니다" in error["message"]
    assert "goto" not in error


# ------------------------------------------------------------------ 같은 글 조각


def test_the_header_marks_keep_their_words(monkeypatch: pytest.MonkeyPatch) -> None:
    """두 모드 머리 줄의 표지 — UPEH 가정 미적용은 세션 칸이 기본값이 아닌 정수일 때만(소수 · 글자
    칸은 켬으로 보지 않는다). 뜻은 표지 풍선이고 없으면 빈 글자다. 계획이 건 입력 비가동은 표지가
    아니라 상태 알림 `CS-05` 다(2026-11-10 보드 Q-4). 출처는 Guide 다(2026-11-08 사용자 그림 메모
    g12)."""
    state: dict[str, object] = {}
    monkeypatch.setattr(st, "session_state", state)
    assert applied_marks() == ("", "")
    for value, on in (
        (UPEH_ASSUMPTION_DEFAULT_PERCENT, False),
        (110, True),
        (90, True),
        (110.0, False),
        ("110", False),
        (None, False),
    ):
        state[UPEH_ASSUMPTION_PERCENT_KEY] = value
        expected = (UPEH_NOT_APPLIED_MARK, UPEH_NOT_APPLIED_HELP) if on else ("", "")
        assert applied_marks() == expected, value
    # 표지는 한두 낱말이고 문장은 풍선에만 있다(설계 규칙 UI-TXT-04).
    assert not UPEH_NOT_APPLIED_MARK.endswith("다")


def _effect(rows: list[tuple[str, int, float, float, bool]]) -> pd.DataFrame:
    """계획이 건 입력 비가동 표(`ShorteningPlan.manual_downtime` 꼴)."""
    return pd.DataFrame(rows, columns=["공정", "생산계획년월", "입력대수", "반영대수", "초과"])


def test_the_manual_downtime_note_is_the_band_and_the_place_to_fix() -> None:
    """입력 비가동 상태 알림 `CS-05` 의 글 — 짧은 글은 그 공정 칸의 합 대수 띠 · 고칠 자리(필요 단축
    일정 `RS-05` 와 같은 말), 전문은 이 화면 · 공정 · 뜻이다. 다른 공정 칸 · 0 칸은 세지 않고, 그
    공정에 칸이 없으면 알림이 없다(None — 「해소」). 알림 칸은 평문이라 이름을 막지 않는다."""
    effect = _effect(
        [
            ("DEMO_*Mold", 202601, 2.0, 2.0, False),
            ("DEMO_*Mold", 202602, 0.0, 0.0, False),
            ("DEMO_Other", 202601, 5.0, 5.0, False),
        ]
    )
    note = manual_downtime_note(effect, process="DEMO_*Mold", process_label="몰드*~")
    assert note is not None
    assert note.text == f"{MANUAL_DOWNTIME_BAND}(1칸 · 합 2대) — {MANUAL_DOWNTIME_FIX}"
    assert note.full == (
        f"제약 시뮬레이션 · 몰드*~ — {MANUAL_DOWNTIME_BAND}(1칸 · 합 2대) — {MANUAL_DOWNTIME_HELP}"
    )
    assert note.content == [f"{MANUAL_DOWNTIME_BAND}(1칸 · 합 2대)", []]
    assert manual_downtime_note(effect, process="DEMO_None", process_label="없음") is None
    assert manual_downtime_note(_effect([]), process="DEMO_*Mold", process_label="몰드") is None


def test_the_manual_downtime_note_names_the_overdrawn_months_in_its_full_text() -> None:
    """그 달 가용보다 커 0 에서 멈춘 칸은 짧은 글 꼬리 「· 가용 넘침 k칸」 하나로 말하고, 그 달(앞
    다섯 — 넘으면 「외 n칸」)은 전문 끝에 둔다(설계 규칙 UI-TXT-04 · UI-NTF-06). 지문 재료에 넘친
    달이 들어 넘친 달이 바뀌면 다시 뜬다."""
    months = [202601, 202602, 202603, 202604, 202605, 202606, 202607]
    effect = _effect([("Mold", month, 9.0, 3.0, True) for month in months])
    note = manual_downtime_note(effect, process="Mold", process_label="Mold")
    assert note is not None
    band = f"{MANUAL_DOWNTIME_BAND}(7칸 · 합 63대 · 가용 넘침 7칸)"
    assert note.text == f"{band} — {MANUAL_DOWNTIME_FIX}"
    assert note.full.endswith(
        "가용 넘침(그 달 가용보다 커 0 에서 멈춘 칸): 26.01, 26.02, 26.03, 26.04, 26.05 외 2칸."
    )
    assert "26.06" not in note.full
    assert note.content == [band, months]
