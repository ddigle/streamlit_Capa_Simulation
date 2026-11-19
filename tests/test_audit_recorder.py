# Purpose: 감사 기록기 — 꺼짐 호출 0 · 상한 · 허용 밖 키 · 토큰 꼴 · 줄바꿈 · 시간 묶음을 지킨다.

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from child_env import narrow_child_env

from capa_simulation.audit import events, recorder

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INST = "0123456789ab"
JWT_LIKE = re.compile(r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")


class Clock:
    def __init__(self, start: datetime) -> None:
        self.moment = start

    def __call__(self) -> datetime:
        return self.moment


@pytest.fixture()
def clock() -> Clock:
    return Clock(datetime(2026, 11, 13, 7, 51, 2, 123456, tzinfo=timezone.utc))


@pytest.fixture()
def on(clock: Clock) -> Iterator[Clock]:
    recorder.start(env="cdep", version="202611131000", inst=INST, clock=clock)
    recorder.set_grader(lambda loginid: "developer" if loginid == "demo.admin" else "viewer")
    yield clock


def _raise() -> recorder.Actor:
    raise AssertionError("꺼진 기록기는 해석기를 부르지 않는다")


def test_an_off_recorder_does_nothing_and_never_resolves() -> None:
    recorder.set_resolver(_raise)

    recorder.record("session_created")
    recorder.note_work("data_scenario_delete", tgt={"type": "scenario", "id": "s-1"})
    recorder.count(recorder.SUMMARY_LOGIN_FAIL, "login_fail:x")
    recorder.note_denied("demo.someone", "not_listed")
    recorder.from_sso_event("login_ok", {"loginid": "demo.user"})

    assert not recorder.enabled()
    assert recorder.pending_count() == 0
    assert recorder.take_pending() == []


def test_a_line_has_the_common_fields_in_utc_with_milliseconds(on: Clock) -> None:
    recorder.record("session_created", actor="  Demo.User ", verified=True, sid8="abcd1234")

    (line,) = recorder.take_pending()
    assert line["ts"] == "2026-11-13T07:51:02.123Z"
    assert line["v"] == 1
    assert line["inst"] == INST
    assert line["env"] == "cdep"
    assert line["ver"] == "202611131000"
    assert (line["ev"], line["cat"], line["out"], line["lvl"]) == (
        "session_created",
        "access",
        "success",
        "info",
    )
    assert (line["actor"], line["verified"], line["grade"]) == ("demo.user", True, "viewer")
    assert line["sid8"] == "abcd1234"
    assert "seq" not in line and "h" not in line


def test_the_queue_has_a_limit_and_the_dropped_count_comes_out_as_one_line(
    on: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(recorder, "MAX_QUEUE", 3)
    for _ in range(5):
        recorder.record("session_created", actor="demo.user")

    lines = recorder.take_pending()
    assert [line["ev"] for line in lines] == ["session_created"] * 3 + ["sys_audit_dropped"]
    assert lines[-1]["det"] == {"count": 2}
    assert lines[-1]["lvl"] == "crit"
    assert recorder.dropped_total() == 2
    assert recorder.take_pending() == []


def test_detail_keeps_only_allowed_keys_and_stays_small(on: Clock) -> None:
    recorder.record(
        "data_scenario_create",
        actor="demo.user",
        det={"source": "csv", "rows": 120, "note": "자유 글", "token": "x"},
    )
    recorder.record(
        "data_revision_save",
        actor="demo.user",
        det={"tables": [f"RQ_TABLE_{index:02d}" for index in range(200)], "parent": "p" * 500},
    )

    first, second = recorder.take_pending()
    assert first["det"] == {"source": "csv", "rows": 120}
    assert (
        len(json.dumps(second["det"], ensure_ascii=False).encode()) <= recorder.DET_LIMIT_BYTES + 20
    )
    assert len(second["det"]["tables"]) <= recorder.DET_LIST_LIMIT


def test_token_shaped_values_never_reach_the_line(on: Clock) -> None:
    jwt_like = "eyJhbGciOiJIUzI1NiJ9.eyJsb2dpbmlkIjoiZGVtbyJ9.c2lnbmF0dXJlLXZhbHVlLWhlcmU"
    secret_like = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCdEfGh"
    recorder.record(
        "data_scenario_rename",
        actor="demo.user",
        tgt={"type": "scenario", "id": jwt_like, "label": secret_like},
        claimed=jwt_like,
    )
    recorder.record("sys_audit_ship_fail", actor="", det={"kind": secret_like})

    lines = recorder.take_pending()
    payload = "\n".join(json.dumps(line, ensure_ascii=False) for line in lines)
    assert not JWT_LIKE.search(payload)
    assert secret_like not in payload
    assert lines[0]["tgt"] == {"type": "scenario", "id": "[가림]", "label": "[가림]"}


def test_line_breaks_and_control_characters_are_cleaned(on: Clock) -> None:
    recorder.record(
        "data_scenario_rename",
        actor="demo.user",
        tgt={"type": "scenario", "id": "s-1", "label": "첫 줄\r\n가짜 줄 끝\x00"},
        claimed="손\n입력",
    )

    (line,) = recorder.take_pending()
    assert line["tgt"]["label"] == "첫 줄 가짜 줄 끝"
    assert line["claimed"] == "손 입력"
    assert all("\n" not in json.dumps(value) for value in line.values())


def test_labels_and_claimed_have_length_limits(on: Clock) -> None:
    recorder.record(
        "data_scenario_rename",
        actor="demo.user",
        tgt={"type": "scenario", "id": "s-1", "label": "가" * 200},
        claimed="나" * 200,
    )

    (line,) = recorder.take_pending()
    assert len(line["tgt"]["label"]) == 60
    assert len(line["claimed"]) == 40


def test_claimed_is_kept_only_when_it_differs_from_the_actor(on: Clock) -> None:
    recorder.record("data_voc_post", actor="demo.user", claimed="DEMO.USER")
    recorder.record("data_voc_post", actor="demo.user", claimed="다른 사람")

    first, second = recorder.take_pending()
    assert "claimed" not in first
    assert second["claimed"] == "다른 사람"


def test_an_unknown_event_becomes_the_bad_event_line(on: Clock) -> None:
    recorder.record("made_up_event", actor="demo.user", det={"rows": 1})

    (line,) = recorder.take_pending()
    assert line["ev"] == "sys_audit_bad_event"
    assert line["det"] == {"name": "made_up_event"}
    assert line["out"] == "unknown"


def test_a_name_rides_only_on_the_login_success_line(on: Clock) -> None:
    recorder.record("authn_login_success", actor="demo.user", name="데모 사용자")
    recorder.record("session_created", actor="demo.user", name="데모 사용자")

    first, second = recorder.take_pending()
    assert first["name"] == "데모 사용자"
    assert "name" not in second


def test_failures_raise_the_level_to_warn(on: Clock) -> None:
    recorder.record("data_scenario_delete", actor="demo.user", out="fail")
    recorder.record("data_scenario_delete", actor="demo.user", out="nonsense")

    first, second = recorder.take_pending()
    assert (first["out"], first["lvl"]) == ("fail", "warn")
    assert second["out"] == "unknown"


def test_the_actor_comes_from_the_resolver_or_the_thread_name(on: Clock) -> None:
    recorder.set_resolver(lambda: recorder.Actor("demo.admin", True, "developer"))
    recorder.note_work("data_scenario_delete", tgt={"type": "scenario", "id": "s-1"})

    seen: list[dict[str, Any]] = []

    def in_worker() -> None:
        recorder.note_work("data_official_publish", tgt={"type": "official", "id": "7"})
        seen.extend(recorder.take_pending())

    thread = threading.Thread(target=in_worker, name="capa-auto-official-update")
    thread.start()
    thread.join()

    (from_script,) = [line for line in seen if line["ev"] == "data_scenario_delete"]
    (from_thread,) = [line for line in seen if line["ev"] == "data_official_publish"]
    assert (from_script["actor"], from_script["verified"], from_script["grade"]) == (
        "demo.admin",
        True,
        "developer",
    )
    assert (from_thread["actor"], from_thread["verified"], from_thread["grade"]) == (
        "system:auto_update",
        False,
        "system",
    )


def test_a_failing_resolver_leaves_an_empty_actor(on: Clock) -> None:
    def broken() -> recorder.Actor:
        raise RuntimeError("쿠키 없음")

    recorder.set_resolver(broken)
    recorder.note_work("data_scenario_delete", tgt={"type": "scenario", "id": "s-1"})

    (line,) = recorder.take_pending()
    assert (line["actor"], line["verified"], line["grade"]) == ("", False, "none")


def test_unauthenticated_failures_fold_into_one_line_per_hour(on: Clock) -> None:
    for _ in range(40):
        recorder.from_sso_event("login_fail", {"reason": "bad_state", "loginid": "-"})
    recorder.from_sso_event("idp_error", {"error": "access_denied"})
    recorder.from_sso_event("session_closed", {"reason": "missing", "loginid": "-"})

    assert recorder.take_pending() == []
    on.moment += timedelta(hours=1)
    (line,) = recorder.take_pending()
    assert line["ev"] == "authn_login_fail_summary"
    assert line["det"]["counts"] == {
        "login_fail:bad_state": 40,
        "idp_error:access_denied": 1,
        "session:missing": 1,
    }
    assert line["det"]["total"] == 42
    assert line["det"]["hour"] == "2026-11-13T07"
    assert line["actor"] == ""


def test_denied_logins_keep_the_first_per_account_and_count_the_rest(on: Clock) -> None:
    for _ in range(3):
        recorder.from_sso_event("login_denied", {"loginid": "demo.outsider", "reason": "x"})
    recorder.from_sso_event("login_denied", {"loginid": "demo.other", "reason": "x"})

    firsts = recorder.take_pending()
    assert [(line["ev"], line["actor"], line["out"]) for line in firsts] == [
        ("authz_fail_access_list", "demo.outsider", "denied"),
        ("authz_fail_access_list", "demo.other", "denied"),
    ]
    on.moment += timedelta(hours=1)
    (summary,) = recorder.take_pending()
    assert summary["ev"] == "authz_fail_access_list_summary"
    assert summary["det"] == {"total": 4, "accounts": 2, "hour": "2026-11-13T07"}


def test_an_early_close_writes_partial_lines_and_the_hour_still_adds_up(on: Clock) -> None:
    """「지금 올리기」 의 앞당겨 닫기 — 열린 묶음마다 `partial` 한 줄, 명단 밖은 그 시간 첫 줄을 낸
    계정을 기억해 같은 계정의 첫 줄을 다시 내지 않는다. 줄마다 `total - accounts` 를 더하면 되풀이
    수가 맞는다."""
    for _ in range(3):
        recorder.from_sso_event("login_denied", {"loginid": "demo.outsider", "reason": "x"})
    for _ in range(2):
        recorder.from_sso_event("login_fail", {"reason": "bad_state", "loginid": "-"})
    assert recorder.open_summary_lines() == 2

    recorder.close_open_buckets()
    early = recorder.take_pending()
    for _ in range(2):
        recorder.from_sso_event("login_denied", {"loginid": "demo.outsider", "reason": "x"})
    recorder.from_sso_event("login_denied", {"loginid": "demo.other", "reason": "x"})
    recorder.from_sso_event("login_fail", {"reason": "bad_state", "loginid": "-"})
    on.moment += timedelta(hours=1)
    late = recorder.take_pending()

    lines = [*early, *late]
    firsts = [line["actor"] for line in lines if line["ev"] == "authz_fail_access_list"]
    assert firsts == ["demo.outsider", "demo.other"]
    denied = [line["det"] for line in lines if line["ev"] == recorder.SUMMARY_DENIED]
    assert denied == [
        {"total": 3, "accounts": 1, "hour": "2026-11-13T07", "partial": True},
        {"total": 3, "accounts": 1, "hour": "2026-11-13T07"},
    ]
    assert len(firsts) + sum(det["total"] - det["accounts"] for det in denied) == 6
    fails = [line["det"] for line in lines if line["ev"] == recorder.SUMMARY_LOGIN_FAIL]
    assert [(det["total"], det.get("partial")) for det in fails] == [(2, True), (1, None)]
    assert recorder.open_summary_lines() == 0


def _finishes(work: Callable[[], object], seconds: float = 5.0) -> list[object]:
    """`work` 를 데몬 스레드로 돌려 `seconds` 안에 끝나는지 본다 — 끝없는 고리가 시험 조각을 붙잡지
    않게 한다. 돌려준 값은 목록 하나에 담는다."""
    done: list[object] = []
    thread = threading.Thread(target=lambda: done.append(work()), daemon=True)
    thread.start()
    thread.join(seconds)
    assert not thread.is_alive(), "끝나지 않았다"
    return done


_BIG_VALUES: dict[str, object] = {
    "text": "가" * 400,
    "list": [f"{index:02d}-" + "x" * 70 for index in range(40)],
    "counts": {f"idp_error:{index:02d}" + "z" * 50: index + 1 for index in range(60)},
}


@pytest.mark.parametrize("shape", sorted(_BIG_VALUES))
@pytest.mark.parametrize("spec", events.SPECS, ids=lambda spec: spec.name)
def test_every_detail_shrinks_under_a_kilobyte_and_returns(
    spec: events.EventSpec, shape: str
) -> None:
    det = {key: _BIG_VALUES[shape] for key in spec.det_keys}

    (kept,) = _finishes(lambda: recorder.clean_det(spec, det))

    assert isinstance(kept, dict)
    assert len(recorder.text_bytes(kept)) <= recorder.DET_LIMIT_BYTES


def test_a_huge_summary_keeps_its_total_and_hour_and_folds_small_counts() -> None:
    spec = events.SPEC_BY_NAME[recorder.SUMMARY_LOGIN_FAIL]
    counts = {f"idp_error:{index:02d}" + "q" * 40: index + 1 for index in range(25)}
    det = {"counts": counts, "total": sum(counts.values()), "hour": "2026-11-13T07"}

    (kept,) = _finishes(lambda: recorder.clean_det(spec, det))

    assert isinstance(kept, dict)
    assert kept["trunc"] is True
    assert (kept["total"], kept["hour"]) == (det["total"], "2026-11-13T07")
    folded = kept["counts"]
    assert isinstance(folded, dict) and "other" in folded
    assert sum(folded.values()) == det["total"], "모아도 건수 합은 그대로"
    assert len(recorder.text_bytes(kept)) <= recorder.DET_LIMIT_BYTES


def test_many_long_unauthenticated_error_codes_never_stall_the_hour_close(on: Clock) -> None:
    """무인증 콜백이 고른 긴 오류 코드 수십 개 — 정시를 넘긴 첫 사건과 비우기가 곧 돌아오고 한 줄은
    1KB 안이다(건수 표 키 글 상한 · 넘친 키는 `other`)."""
    for index in range(25):
        code = chr(ord("a") + index % 26) * 30 + f"_{index:02d}" + "_" * 7
        recorder.from_sso_event("idp_error", {"error": code})
    on.moment += timedelta(hours=1)

    _finishes(lambda: recorder.from_sso_event("idp_error", {"error": "access_denied"}))
    (lines,) = _finishes(recorder.take_pending)

    assert isinstance(lines, list)
    (summary,) = [line for line in lines if line["ev"] == recorder.SUMMARY_LOGIN_FAIL]
    assert summary["det"]["total"] == 25
    assert summary["det"]["counts"]["other"] > 0
    assert "trunc" not in summary["det"]
    assert len(recorder.text_bytes(summary["det"])) <= recorder.DET_LIMIT_BYTES


def test_sso_events_map_to_audit_lines_without_jti_or_department(on: Clock) -> None:
    recorder.from_sso_event(
        "login_ok",
        {
            "loginid": "Demo.Admin",
            "hours": "6",
            "max_hours": "24",
            "sid": "sid12345",
            "jti": "jti12345",
        },
        {"name": "데모 관리자"},
    )
    recorder.from_sso_event("login_fail", {"reason": "nonce", "loginid": "demo.user"})
    recorder.from_sso_event("logout", {"loginid": "demo.user", "sid": "sid99999"})
    recorder.from_sso_event(
        "session_closed", {"reason": "expired", "loginid": "demo.user", "end": "idle"}
    )
    recorder.from_sso_event("session_closed", {"reason": "denied", "loginid": "demo.user"})
    recorder.from_sso_event("config", {"mode": "on"})
    recorder.from_sso_event("access_saved", {"loginid": "demo.admin"})

    lines = recorder.take_pending()
    assert [line["ev"] for line in lines] == [
        "authn_login_success",
        "authn_login_fail",
        "session_logout",
        "session_expired",
        "authz_fail_session",
    ]
    login = lines[0]
    assert (login["actor"], login["grade"], login["name"], login["sid8"]) == (
        "demo.admin",
        "developer",
        "데모 관리자",
        "sid12345",
    )
    assert login["det"] == {"hours": 6, "max_hours": 24}
    assert login["ip"] == ""
    assert lines[3]["det"] == {"end": "idle"}
    assert lines[4]["out"] == "denied"
    payload = json.dumps(lines, ensure_ascii=False)
    assert "jti" not in payload and "dept" not in payload


def test_the_recorder_does_not_bring_streamlit_duckdb_or_jwt() -> None:
    code = (
        "import sys\n"
        "import capa_simulation.audit.recorder\n"
        "import capa_simulation.audit.chain\n"
        "print(sorted({'streamlit', 'jwt', 'duckdb', 'pandas'} & set(sys.modules)))\n"
    )
    found = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        env=narrow_child_env({"PYTHONPATH": str(PROJECT_ROOT / "src"), "PATH": ""}),
    )

    assert found.stdout.strip() == "[]"
