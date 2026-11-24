# Purpose: CUSTOM 원천 표 환경변수 판정이 서버 시작 점검 줄 · 제목 판정 · AD-01 에 드는지 지킨다.

"""CUSTOM 원천 표 환경변수(`CAPA_BDQ_CUSTOM_TABLE`)와 「서버 시작 점검」.

DB 등록 · 자동 갱신의 상세 조회가 쓰는 판정(`company_bigdataquery_adapter.custom_table_problem`)
하나를 Admin 「서버 시작 점검」 의 「CUSTOM 원천 표」 줄이 이 프로세스의 지금 환경으로 읽는다 —
없거나 꼴이 틀리면 「실패」 라 펼침 제목이 「실패 있음」 이 되고 개발자 알림 `AD-01` 이 선다.
값(사내 표 이름)은 표 · 복사 글 · 알림 어디에도 싣지 않는다. 같은 판정의 DB 등록 탭 저장 단추
잠금 · `AD-04` 는 `tests/test_bigdataquery_registration.py` 가 본다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from alert_marks import active_state
from streamlit.testing.v1 import AppTest

import capa_simulation.settings as settings
from capa_simulation import alerts
from capa_simulation.components import container_start_check
from capa_simulation.components.container_start_check import (
    CUSTOM_TABLE_STEP_LABEL,
    custom_table_step,
    live_failed_steps,
    start_verdict,
)
from capa_simulation.components.diagnostic_copy import COMPONENT_KEY_PREFIX
from capa_simulation.components.memory_diagnostic import MEMORY_LIMIT_STEP_LABEL
from capa_simulation.io import company_bigdataquery_adapter as adapter
from capa_simulation.io.container_start_report import read_container_start_report
from capa_simulation.persistence import _sql_helpers
from capa_simulation.persistence.duckdb_memory import MEMORY_LIMIT_ENV, memory_limit_setting

SCRIPT = """
from capa_simulation.components.container_start_check import (
    render_container_start_check,
    render_start_check_alert,
)

render_start_check_alert()
render_container_start_check()
"""

# 표 이름 꼴이 아닌 합성 값 — 한글 · 공백 · 셋째 점 조각. 값은 어디에도 실리지 않아야 한다.
MALFORMED_VALUES = ("데모 원천.표", "demo schema.demo_custom", "demo.schema.custom")
MISSING_REASON = (
    f"{adapter.CUSTOM_TABLE_MISSING.removesuffix('.')} — DB 등록 · 자동 갱신이 멈춥니다"
)
MALFORMED_REASON = (
    f"{adapter.CUSTOM_TABLE_MALFORMED.removesuffix('.')} — DB 등록 · 자동 갱신이 멈춥니다"
)


def _report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """모든 단계가 정상인 시작 결과 파일 — 판정을 가르는 것은 지금 환경의 CUSTOM 원천 표
    줄뿐이다."""
    report = tmp_path / "container_start.json"
    report.write_text(
        json.dumps(
            {
                "version": 1,
                "written_at": "2026-11-24T09:00:00+09:00",
                "steps": {
                    step: {"status": "ok", "reason": "정상"}
                    for step in ("install", "token", "user_name")
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", report)
    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    return report


def _start_check(app: AppTest) -> tuple[str, pd.DataFrame]:
    """(펼침 제목, 단계 표). 아이콘이 달린 펼침을 AppTest 는 `status` 로 센다."""
    labels = [item.label for item in app.expander] + [item.label for item in app.status]
    [title] = [label for label in labels if "서버 시작 점검" in label]
    [steps] = [frame for frame in app.dataframe if "단계" in getattr(frame.value, "columns", [])]
    return title, steps.value


@pytest.mark.parametrize(
    ("value", "problem"),
    [
        (None, adapter.CUSTOM_TABLE_MISSING),
        ("   ", adapter.CUSTOM_TABLE_MISSING),
        ("demo_schema.demo_custom", None),
        ("  demo_custom  ", None),
        *((value, adapter.CUSTOM_TABLE_MALFORMED) for value in MALFORMED_VALUES),
    ],
    ids=["없음", "공백뿐", "스키마.표", "표 하나", "한글", "공백 낀 값", "점 둘"],
)
def test_the_start_row_follows_the_same_judgement_as_the_detail_query(
    monkeypatch: pytest.MonkeyPatch, value: str | None, problem: str | None
) -> None:
    """줄은 상세 조회와 같은 판정(`custom_table_problem`)을 지금 환경에서 읽는다 — 정규식을 따로
    두지 않는다. 쓸 수 있으면 「정상」 이고 변수 이름만, 아니면 「실패」 와 판정 글에 막히는 것을
    잇는다."""
    if value is None:
        monkeypatch.delenv(adapter.BDQ_CUSTOM_TABLE_ENV, raising=False)
    else:
        monkeypatch.setenv(adapter.BDQ_CUSTOM_TABLE_ENV, value)

    assert adapter.custom_table_problem() == problem
    label, status, reason = custom_table_step()
    assert label == CUSTOM_TABLE_STEP_LABEL
    if problem is None:
        assert (status, reason) == ("정상", f"{adapter.BDQ_CUSTOM_TABLE_ENV} 있음")
    else:
        assert status == "실패"
        assert reason == (
            MISSING_REASON if problem == adapter.CUSTOM_TABLE_MISSING else MALFORMED_REASON
        )
    if value is not None and value.strip():
        assert value.strip() not in reason


def test_a_missing_variable_turns_the_title_verdict_and_the_live_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """결과 파일이 모두 정상이어도 지금 환경에 변수가 없으면 제목 판정이 「실패 있음」 이고 지금
    판정한 실패 목록에 그 줄이 든다. 메모리 한도 칸도 틀리면 표 차례(CUSTOM 원천 표 → 메모리
    한도)다."""
    _report(tmp_path, monkeypatch)
    report = read_container_start_report()
    assert report is not None
    assert start_verdict(report) == "모두 정상"
    assert live_failed_steps() == []

    monkeypatch.delenv(adapter.BDQ_CUSTOM_TABLE_ENV)
    assert start_verdict(report) == "실패 있음"
    assert live_failed_steps() == [(CUSTOM_TABLE_STEP_LABEL, MISSING_REASON)]

    monkeypatch.setattr(
        _sql_helpers, "DUCKDB_MEMORY_LIMIT", memory_limit_setting({MEMORY_LIMIT_ENV: "80%"})
    )
    assert [name for name, _ in live_failed_steps()] == [
        CUSTOM_TABLE_STEP_LABEL,
        MEMORY_LIMIT_STEP_LABEL,
    ]


def test_the_row_sits_before_the_memory_limit_row_and_keeps_ad01_quiet_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, diagnostic_copies: dict[str, str]
) -> None:
    """변수가 있으면 줄은 「정상」 이고 끝 줄(DuckDB 메모리 한도) 바로 앞이다 — 제목 판정 · `AD-01`
    은 그대로다."""
    _report(tmp_path, monkeypatch)

    app = AppTest.from_string(SCRIPT).run(timeout=60)

    assert not list(app.exception), [item.message for item in app.exception]
    title, steps = _start_check(app)
    assert title == "서버 시작 점검 · 모두 정상"
    assert steps["단계"].tolist()[-2:] == [CUSTOM_TABLE_STEP_LABEL, MEMORY_LIMIT_STEP_LABEL]
    assert steps.iloc[-2].tolist() == [
        CUSTOM_TABLE_STEP_LABEL,
        "정상",
        f"{adapter.BDQ_CUSTOM_TABLE_ENV} 있음",
    ]
    assert active_state(app, container_start_check.START_CHECK_ALERT_CODE) is None
    text = diagnostic_copies[f"{COMPONENT_KEY_PREFIX}container_start_check"]
    assert f"{CUSTOM_TABLE_STEP_LABEL}\t정상\t{adapter.BDQ_CUSTOM_TABLE_ENV} 있음" in text


@pytest.mark.parametrize(
    "value", [None, *MALFORMED_VALUES], ids=["없음", "한글", "공백 낀 값", "점 둘"]
)
def test_a_missing_or_malformed_variable_fails_the_row_and_raises_ad01_without_the_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    diagnostic_copies: dict[str, str],
    value: str | None,
) -> None:
    """없거나 꼴이 틀리면 줄이 「실패」 이고 제목이 「실패 있음」, 개발자 알림 `AD-01` 의 짧은 글이
    그 줄 이름이다(「그 화면으로」 Admin Area). 지문은 (판정, 실패 단계 이름들)이라 까닭 글이
    바뀌어도 다시 뜨지 않는다. 값은 표 · 복사 글 · 알림 어디에도 없다."""
    _report(tmp_path, monkeypatch)
    if value is None:
        monkeypatch.delenv(adapter.BDQ_CUSTOM_TABLE_ENV)
    else:
        monkeypatch.setenv(adapter.BDQ_CUSTOM_TABLE_ENV, value)
    reason = MISSING_REASON if value is None else MALFORMED_REASON

    app = AppTest.from_string(SCRIPT).run(timeout=60)

    assert not list(app.exception), [item.message for item in app.exception]
    title, steps = _start_check(app)
    assert title == "서버 시작 점검 · 실패 있음"
    assert steps.iloc[-2].tolist() == [CUSTOM_TABLE_STEP_LABEL, "실패", reason]
    note = active_state(app, container_start_check.START_CHECK_ALERT_CODE)
    assert note is not None
    assert note["short"] == f"서버 시작 점검 실패 — {CUSTOM_TABLE_STEP_LABEL}"
    assert f"{CUSTOM_TABLE_STEP_LABEL}: {reason}. Admin 「서버 시작 점검」" in note["full"]
    assert note["href"] == "admin_area"
    assert note["fp"] == alerts.fingerprint(
        container_start_check.START_CHECK_ALERT_CODE, None, ["실패 있음", [CUSTOM_TABLE_STEP_LABEL]]
    )
    text = diagnostic_copies[f"{COMPONENT_KEY_PREFIX}container_start_check"]
    assert f"{CUSTOM_TABLE_STEP_LABEL}\t실패\t{reason}" in text
    if value is not None:
        shown = [*steps.astype(str).to_numpy().ravel(), note["short"], note["full"], text]
        assert not [place for place in shown if value in place]
