# Purpose: 메모리 · 프로세스 단서를 가짜 cgroup · /proc 뿌리와 진짜 하위 프로세스로 본다.

"""메모리 · 프로세스 단서(`io/memory_probe` · `container_start_report` 의 `ChildMemory` ·
`ProcessClues`).

cgroup v2 · v1 · 없음과 `/proc` 를 tmp 뿌리로 흉내 낸다(값은 합성). 못 읽은 값은 `None` 이고 화면
글은 「모름」 이다. 진단 칸은 결과 파일 · 감사 상세를 지나 다시 읽혀도 같고, 옛 파일(칸 없음)은 그
단서가 없다. 하위 최고는 그 하위 하나의 값이라 앱 RSS 보다 작게 나와야 하고, `stat` 22째 칸(시작
틱)은 막 띄운 하위의 나이가 몇 초 안이어야 한다 — 둘 다 진짜 하위로 Linux 에서 본다.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from bdq_login_support import ACCOUNT, PASSWORD, FakeBdq, use_fake_bdq

from capa_simulation.audit import events, recorder
from capa_simulation.io import bdq_login, memory_probe
from capa_simulation.io import container_start_report as report_contract
from capa_simulation.io.container_start_report import ChildDiag, ChildMemory, ProcessClues
from capa_simulation.io.memory_probe import MIB, MemoryReading

STATUS = "Name:\tpython\nVmPeak:\t 900000 kB\nVmRSS:\t  348160 kB\nVmHWM:\t 360000 kB\n"


def _v2(root: Path, *, current: int, limit: str, oom: int) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "memory.current").write_text(f"{current}\n", encoding="ascii")
    (root / "memory.max").write_text(f"{limit}\n", encoding="ascii")
    (root / "memory.events").write_text(
        f"low 0\nhigh 0\nmax 4\noom 1\noom_kill {oom}\noom_group_kill 0\n", encoding="ascii"
    )
    return root


def _v1(root: Path, *, usage: int, limit: int, oom: int) -> Path:
    folder = root / "memory"
    folder.mkdir(parents=True)
    (folder / "memory.usage_in_bytes").write_text(f"{usage}\n", encoding="ascii")
    (folder / "memory.limit_in_bytes").write_text(f"{limit}\n", encoding="ascii")
    (folder / "memory.oom_control").write_text(
        f"oom_kill_disable 0\nunder_oom 0\noom_kill {oom}\n", encoding="ascii"
    )
    return root


def _status(tmp_path: Path) -> Path:
    path = tmp_path / "status"
    path.write_text(STATUS, encoding="ascii")
    return path


def test_a_v2_cgroup_gives_use_limit_and_oom_kills(tmp_path: Path) -> None:
    root = _v2(tmp_path / "cg", current=700 * MIB, limit=str(1024 * MIB), oom=2)
    found = memory_probe.read(root, _status(tmp_path))
    assert (found.cgroup_bytes, found.limit_bytes, found.unlimited, found.oom_kill) == (
        700 * MIB,
        1024 * MIB,
        False,
        2,
    )
    assert found.rss_bytes == 348160 * 1024


def test_a_v2_cgroup_without_a_limit_says_max(tmp_path: Path) -> None:
    root = _v2(tmp_path / "cg", current=10 * MIB, limit="max", oom=0)
    found = memory_probe.read(root, _status(tmp_path))
    assert (found.limit_bytes, found.unlimited, found.oom_kill) == (None, True, 0)


def test_a_v1_cgroup_is_read_from_the_memory_folder(tmp_path: Path) -> None:
    root = _v1(tmp_path / "cg", usage=500 * MIB, limit=1024 * MIB, oom=1)
    found = memory_probe.read(root, _status(tmp_path))
    assert (found.cgroup_bytes, found.limit_bytes, found.unlimited, found.oom_kill) == (
        500 * MIB,
        1024 * MIB,
        False,
        1,
    )
    huge = _v1(tmp_path / "cg-free", usage=MIB, limit=(1 << 63) - 4096, oom=0)
    found = memory_probe.read(huge, _status(tmp_path))
    assert (found.limit_bytes, found.unlimited) == (None, True)


def test_missing_files_are_unknown_and_never_raise(tmp_path: Path) -> None:
    found = memory_probe.read(tmp_path / "none", tmp_path / "no-status")
    assert (found.cgroup_bytes, found.limit_bytes, found.oom_kill, found.rss_bytes) == (
        None,
        None,
        None,
        None,
    )
    assert not found.unlimited
    events_only = tmp_path / "odd"
    events_only.mkdir()
    (events_only / "memory.current").write_text("not a number\n", encoding="ascii")
    found = memory_probe.read(events_only, tmp_path / "no-status")
    assert (found.cgroup_bytes, found.limit_bytes, found.oom_kill) == (None, None, None)


def test_the_module_roots_are_read_when_called(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """뿌리를 주지 않으면 부를 때의 모듈 값을 읽는다(`attempt_login` 이 이 길이다)."""
    monkeypatch.setattr(
        memory_probe, "CGROUP_ROOT", _v2(tmp_path / "cg", current=MIB, limit="max", oom=5)
    )
    monkeypatch.setattr(memory_probe, "PROC_STATUS", _status(tmp_path))
    found = memory_probe.read()
    assert found.oom_kill == 5 and found.rss_bytes == 348160 * 1024


def _proc(root: Path, pid: int, text: str) -> Path:
    folder = root / str(pid)
    folder.mkdir(parents=True)
    (folder / "status").write_text(text, encoding="ascii")
    return root


def test_a_process_peak_is_its_own_high_water_mark(tmp_path: Path) -> None:
    """`/proc/<pid>/status` 의 `VmHWM` 이다. 끝나 거두기 전(좀비 — Vm 줄 없음) · 없는 프로세스 ·
    `/proc` 가 없는 자리(Windows)는 모른다."""
    root = _proc(tmp_path / "proc", 4321, STATUS)
    assert memory_probe.process_peak_bytes(4321, root) == 360000 * 1024
    _proc(root, 4322, "Name:\tpython\nState:\tZ (zombie)\n")
    assert memory_probe.process_peak_bytes(4322, root) is None
    assert memory_probe.process_peak_bytes(4323, root) is None
    assert memory_probe.process_peak_bytes(4321, tmp_path / "no-proc") is None


def test_the_peak_keeps_the_highest_known_sample() -> None:
    assert memory_probe.higher(None, None) is None
    assert memory_probe.higher(None, 5) == 5
    assert memory_probe.higher(7, None) == 7
    assert memory_probe.higher(7, 5) == 7
    assert memory_probe.higher(5, 7) == 7


def test_two_readings_and_the_child_peak_fold_into_mib_and_counts() -> None:
    before = MemoryReading(700 * MIB, 1024 * MIB, False, 0, 340 * MIB)
    after = MemoryReading(980 * MIB, 1024 * MIB, False, 1, 342 * MIB)
    memory = memory_probe.child_memory(before, after, 62 * MIB)
    assert memory == ChildMemory(700, 980, 1024, False, 0, 1, 340, 342, 62)
    assert memory.text == (
        "cgroup 700→980/1024MiB · oom_kill 0→1 · 앱 RSS 340→342MiB · 하위 최고 62MiB"
    )
    assert memory_probe.child_memory(before, after).child_peak is None


def test_unknown_values_read_as_unknown() -> None:
    assert ChildMemory().text == "cgroup 모름 · oom_kill 모름 · 앱 RSS 모름 · 하위 최고 모름"
    partial = ChildMemory(cgroup_after=900, unlimited=True, oom_after=1, rss_before=300)
    assert partial.text == (
        "cgroup 모름→900/max · oom_kill 모름→1 · 앱 RSS 300→모름MiB · 하위 최고 모름"
    )


def test_the_memory_fields_round_trip_and_are_audit_keys() -> None:
    """결과 파일 칸 · 감사 상세가 같은 이름이고(`MEMORY_FIELDS`), 다시 읽어도 같다. 옛 칸(메모리
    없음)은 메모리 단서가 없고 화면 글도 옛 꼴 그대로다. 꼴이 어긋난 값은 그 값만 비운다."""
    memory = ChildMemory(700, 980, None, True, 0, 1, 340, 342, 62)
    diag = ChildDiag(-9, "SIGKILL", 2.9, "import", "", "2.5.0", "1.0.1", memory)
    fields = diag.fields()
    assert tuple(name for name in fields if name in report_contract.MEMORY_FIELDS) == (
        report_contract.MEMORY_FIELDS
    )
    assert fields["cg_max"] == "max"
    spec = next(item for item in events.SPECS if item.name == "admin_bdq_login_set")
    assert set(fields) <= spec.det_keys
    assert all(name in events.DET_LABELS for name in report_contract.MEMORY_FIELDS)
    assert report_contract.parse_child(json.loads(json.dumps(fields))) == diag
    assert diag.text.endswith(" · getpass_asterisk 1.0.1 · " + memory.text)
    assert "cg_before=700 cg_after=980 cg_max=max oom_before=0 oom_after=1" in diag.code

    old = ChildDiag(-9, "SIGKILL", 2.9, "import", "", "2.5.0", "1.0.1")
    assert report_contract.parse_child(old.fields()) == old
    assert old.memory is None and "cgroup" not in old.text

    odd = {**fields, "cg_before": -1, "oom_after": "1", "cg_max": "lots", "rss_after": True}
    parsed = report_contract.parse_child(odd)
    assert parsed is not None and parsed.memory is not None
    assert (parsed.memory.cgroup_before, parsed.memory.oom_after) == (None, None)
    assert (parsed.memory.limit, parsed.memory.unlimited, parsed.memory.rss_after) == (
        None,
        False,
        None,
    )


def test_a_file_with_the_old_child_peak_pair_reads_without_raising() -> None:
    """옛 칸 `kid_peak_before` · `kid_peak_after`(거둔 하위 모두의 최고 — 앱 RSS 를 물려받은 값)가
    든 결과 파일 · 감사 상세도 예외 없이 읽는다. 그 값을 새 칸으로 옮기지 않아 하위 최고는
    「모름」 이다."""
    old = {
        "exit": -9,
        "signal": "SIGKILL",
        "sec": 2.9,
        "stage": "import",
        "cg_before": 700,
        "cg_after": 980,
        "cg_max": 1024,
        "oom_before": 0,
        "oom_after": 0,
        "rss_before": 291,
        "rss_after": 291,
        "kid_peak_before": 291,
        "kid_peak_after": 291,
    }
    parsed = report_contract.parse_child(old)
    assert parsed is not None and parsed.memory is not None
    assert parsed.memory.child_peak is None
    assert parsed.memory.text.endswith("앱 RSS 291→291MiB · 하위 최고 모름")
    assert "kid_peak_before" not in parsed.fields() and parsed.fields()["kid_peak"] is None
    only_old = report_contract.parse_memory({"kid_peak_before": 1, "kid_peak_after": 2})
    assert only_old == ChildMemory()


def test_a_login_reads_memory_before_and_after_the_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """하위 프로세스를 띄우기 바로 앞과 끝난 바로 뒤에 한 번씩 읽어 진단에 싣는다 — 그 사이 OOM
    종료 수가 오르면 진단 줄이 그 수를 보인다."""
    fake: FakeBdq = use_fake_bdq(monkeypatch, tmp_path)
    readings = iter(
        (
            MemoryReading(700 * MIB, 1024 * MIB, False, 0, 340 * MIB),
            MemoryReading(990 * MIB, 1024 * MIB, False, 1, 342 * MIB),
        )
    )
    calls: list[int] = []

    def reading(*_args: object) -> MemoryReading:
        calls.append(fake.logins())
        return next(readings)

    monkeypatch.setattr(memory_probe, "read", reading)
    monkeypatch.setattr(memory_probe, "process_peak_bytes", lambda _pid: 62 * MIB)
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD)
    assert result.diag is not None and result.diag.memory is not None
    assert result.diag.memory == ChildMemory(700, 990, 1024, False, 0, 1, 340, 342, 62)
    assert calls == [0, 1]
    assert "oom_kill 0→1" in result.diag.text
    assert ACCOUNT not in result.diag.text and PASSWORD not in result.diag.text


# 하위가 자기 메모리를 잡고 잠시 머문다 — 그동안 잰 최고가 그 할당을 넘고 앱 RSS 보다 작아야 한다.
_HOLD_CHILD = """
import sys, time
held = b"\\x01" * (int(sys.argv[1]) << 20)
time.sleep(0.6)
"""
_CHILD_MIB = 48
_BALLAST_MIB = 256


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="/proc 의 VmHWM 은 Linux 의 것")
def test_the_child_peak_is_the_childs_own_not_the_apps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """앱이 큰 메모리를 쥔 채 작은 하위를 띄워도 하위 최고는 그 하위 자신의 값이다 — 거둔 하위들의
    `getrusage` 최고처럼 exec 앞에 물려받은 앱 주소 공간을 세지 않는다(사내 리뷰의 「하위 최고 = 앱
    최고」 결함)."""
    use_fake_bdq(monkeypatch, tmp_path)
    monkeypatch.setattr(
        bdq_login,
        "login_command",
        lambda: [sys.executable, "-c", _HOLD_CHILD, str(_CHILD_MIB)],
    )
    ballast = b"\x02" * (_BALLAST_MIB * MIB)
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD, timeout=30)
    assert len(ballast) == _BALLAST_MIB * MIB
    assert result.diag is not None and result.diag.memory is not None
    memory = result.diag.memory
    assert memory.rss_before is not None and memory.rss_before >= _BALLAST_MIB
    assert memory.child_peak is not None
    assert _CHILD_MIB <= memory.child_peak < memory.rss_before
    assert f"하위 최고 {memory.child_peak}MiB" in result.diag.text


def test_a_place_without_proc_leaves_the_child_peak_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/proc` 가 없는 자리(Windows)는 하위 최고가 「모름」 이고 로그인은 그대로 간다."""
    fake: FakeBdq = use_fake_bdq(monkeypatch, tmp_path)
    monkeypatch.setattr(memory_probe, "PROC_ROOT", tmp_path / "no-proc")
    seen: list[Any] = []
    real = memory_probe.process_peak_bytes

    def peak(pid: int, proc_root: Path | None = None) -> int | None:
        found = real(pid, proc_root)
        seen.append(found)
        return found

    monkeypatch.setattr(memory_probe, "process_peak_bytes", peak)
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD)
    assert result.outcome == bdq_login.OUTCOME_OK and fake.logins() == 1
    assert result.diag is not None and result.diag.memory is not None
    assert result.diag.memory.child_peak is None
    assert " · 하위 최고 모름 · 앱 뜬 지 " in result.diag.text
    assert seen and set(seen) == {None}
    # 같은 뿌리의 프로세스 단서도 모른다 — 뜬 시간 · 열린 파일 · 좀비(스레드는 상태 파일 몫).
    assert result.diag.process is not None
    process = result.diag.process
    assert (process.app_hours, process.open_files, process.zombies) == (None, None, None)
    assert "앱 뜬 지 모름 · " in result.diag.text and result.diag.text.endswith(" · 좀비 모름")


# --- 띄우기 앞 프로세스 단서 ------------------------------------------------------------------

_TICKS = 100
# `comm` 이 괄호 · 공백을 품은 꼴 — 마지막 `)` 뒤부터 갈라야 22째 칸이 시작 틱이다.
_ODD_COMM = "(py (wo) rk) x)"


def _stat_line(pid: int, state: str, start_ticks: int, comm: str = "(python)") -> str:
    """`/proc/<pid>/stat` 한 줄(합성) — 1째 pid · 2째 comm · 3째 상태 … 22째 시작 틱."""
    middle = " ".join(str(n) for n in range(4, 22))  # 4째 ~ 21째 칸(값은 아무 수)
    return f"{pid} {comm} {state} {middle} {start_ticks} 123456 789\n"


def _fake_proc(
    root: Path,
    *,
    self_start_ticks: int = 360_000,
    uptime: str = "61200.25 99999.00",
    fds: int = 3,
    others: dict[int, str] | None = None,
    comm: str = _ODD_COMM,
) -> Path:
    """가짜 `/proc` — `uptime` · `self/stat` · `self/fd/<n>`(보통 파일) · 숫자 폴더마다 `stat`."""
    (root / "self" / "fd").mkdir(parents=True)
    (root / "uptime").write_text(f"{uptime}\n", encoding="ascii")
    (root / "self" / "stat").write_text(
        _stat_line(4242, "S", self_start_ticks, comm), encoding="ascii"
    )
    for number in range(fds):
        (root / "self" / "fd" / str(number)).write_text("", encoding="ascii")
    for pid, state in (others or {}).items():
        (root / str(pid)).mkdir()
        (root / str(pid) / "stat").write_text(
            _stat_line(pid, state, 100, "(a b) (c)"), encoding="ascii"
        )
    return root


def _pids_v2(root: Path, *, current: int, limit: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pids.current").write_text(f"{current}\n", encoding="ascii")
    (root / "pids.max").write_text(f"{limit}\n", encoding="ascii")
    return root


def _thread_status(tmp_path: Path, threads: int = 41) -> Path:
    path = tmp_path / "self-status"
    path.write_text(STATUS + f"Threads:\t{threads}\n", encoding="ascii")
    return path


@pytest.fixture()
def ticks(monkeypatch: pytest.MonkeyPatch) -> int:
    """초당 틱을 고정한다 — Windows(틱 모름)에서도 가짜 뿌리로 뜬 시간을 잰다."""
    monkeypatch.setattr(memory_probe, "clock_ticks", lambda: _TICKS)
    return _TICKS


def test_process_clues_come_from_a_fake_proc_and_a_v2_cgroup(tmp_path: Path, ticks: int) -> None:
    """뜬 시간은 `uptime` − 시작 틱 ÷ 초당 틱(`comm` 이 괄호 · 공백을 품어도), 스레드는 `Threads`,
    열린 파일은 `self/fd` 항목 수, pids 는 v2 뿌리의 `pids.current` · `pids.max`, 좀비는 숫자 폴더
    가운데 상태 `Z` 의 수다."""
    # 뜬 지 58464초 = 16.24시간 — 소수 첫째 자리로 접어 16.2(둘째 자리면 16.24 로 갈린다).
    proc = _fake_proc(
        tmp_path / "proc",
        self_start_ticks=(61200 - 16 * 3600 - 864) * ticks + ticks // 4,
        fds=87,
        others={1: "S", 7: "Z", 8: "Z", 9: "R"},
    )
    assert memory_probe.age_seconds(proc / "self" / "stat", proc / "uptime") == 58464.0
    cgroup = _pids_v2(tmp_path / "cg", current=48, limit="512")
    found = memory_probe.process_clues(proc, _thread_status(tmp_path), cgroup)
    assert found == ProcessClues(16.2, 41, 87, 48, 512, False, 2)
    assert found.text == "앱 뜬 지 16.2시간 · 스레드 41 · 열린 파일 87 · pids 48/512 · 좀비 2"


def test_a_v1_pids_folder_and_an_unlimited_max(tmp_path: Path, ticks: int) -> None:
    proc = _fake_proc(tmp_path / "proc", others={1: "S"})
    v1 = _pids_v2(tmp_path / "cg1" / "pids", current=9, limit="max").parent
    found = memory_probe.process_clues(proc, _thread_status(tmp_path), v1)
    assert (found.pids, found.pids_limit, found.pids_unlimited, found.zombies) == (9, None, True, 0)
    assert "pids 9/max · 좀비 0" in found.text
    v2 = _pids_v2(tmp_path / "cg2", current=3, limit="max")
    found = memory_probe.process_clues(proc, _thread_status(tmp_path), v2)
    assert (found.pids, found.pids_limit, found.pids_unlimited) == (3, None, True)


def test_missing_process_files_are_unknown_and_never_raise(tmp_path: Path, ticks: int) -> None:
    """`/proc` · cgroup 이 없는 자리(Windows)는 모두 모름이다. 숫자 폴더에 `stat` 이 하나도 없으면
    (세는 사이 다 사라짐) 좀비 0 이 아니라 모름이다."""
    found = memory_probe.process_clues(tmp_path / "no-proc", tmp_path / "no-status", tmp_path / "x")
    assert found == ProcessClues()
    assert found.text == ("앱 뜬 지 모름 · 스레드 모름 · 열린 파일 모름 · pids 모름 · 좀비 모름")
    empty = tmp_path / "empty-proc"
    (empty / "77").mkdir(parents=True)
    assert memory_probe.process_clues(empty).zombies is None


def test_a_vanished_process_is_skipped_while_counting_zombies(tmp_path: Path, ticks: int) -> None:
    proc = _fake_proc(tmp_path / "proc", others={1: "S", 5: "Z"})
    (proc / "6").mkdir()  # 세는 사이 사라진 프로세스 — `stat` 이 없다
    (proc / "self" / "status").write_text("x", encoding="ascii")  # 숫자 아닌 폴더는 보지 않는다
    assert memory_probe.process_clues(proc, tmp_path / "no-status", tmp_path / "x").zombies == 1


@pytest.mark.parametrize(
    "stat_text",
    [
        "",
        "4242 python S 1 2 3\n",  # 괄호 없음
        "4242 (python) S 1 2\n",  # 22째 칸까지 못 감
        _stat_line(4242, "S", 0).replace(" 0 123456", " x 123456"),  # 시작 틱이 수가 아님
        _stat_line(4242, "S", 10**400),  # 실수로 넘침
        _stat_line(4242, "S", 0).replace(" 0 123456", f" {'9' * 5000} 123456"),  # 정수 자릿수 상한
        _stat_line(4242, "S", 10**20),  # 64비트 틱(20자리)보다 긺
    ],
)
def test_an_odd_stat_leaves_the_app_age_unknown(tmp_path: Path, ticks: int, stat_text: str) -> None:
    proc = _fake_proc(tmp_path / "proc")
    (proc / "self" / "stat").write_text(stat_text, encoding="ascii")
    assert memory_probe.age_seconds(proc / "self" / "stat", proc / "uptime") is None
    assert memory_probe.process_clues(proc).app_hours is None


@pytest.mark.parametrize("uptime", ["", "soon", "-5.0 1.0", "nan 1.0", "inf 1.0"])
def test_an_odd_uptime_leaves_the_app_age_unknown(tmp_path: Path, ticks: int, uptime: str) -> None:
    proc = _fake_proc(tmp_path / "proc", uptime=uptime)
    assert memory_probe.process_clues(proc).app_hours is None


def test_the_app_age_needs_the_clock_ticks_and_tolerates_rounding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """초당 틱을 모르면(Windows) 모름. 시작 틱이 부팅 뒤 초를 살짝 넘으면(반올림) 0, 1초 넘게
    거꾸로면 모름이다."""
    proc = _fake_proc(tmp_path / "proc", self_start_ticks=6_120_050, uptime="61200.25")
    monkeypatch.setattr(memory_probe, "clock_ticks", lambda: None)
    assert memory_probe.process_clues(proc).app_hours is None
    monkeypatch.setattr(memory_probe, "clock_ticks", lambda: _TICKS)
    stat, uptime = proc / "self" / "stat", proc / "uptime"
    assert memory_probe.age_seconds(stat, uptime) == 0.0
    stat.write_text(_stat_line(4242, "S", 6_120_300), encoding="ascii")
    assert memory_probe.age_seconds(stat, uptime) is None


def test_the_module_roots_are_read_when_called_for_process_clues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ticks: int
) -> None:
    """뿌리를 주지 않으면 부를 때의 모듈 값(`PROC_ROOT` · `PROC_STATUS` · `CGROUP_ROOT`)을
    읽는다."""
    monkeypatch.setattr(memory_probe, "PROC_ROOT", _fake_proc(tmp_path / "proc", others={3: "Z"}))
    monkeypatch.setattr(memory_probe, "PROC_STATUS", _thread_status(tmp_path, 12))
    monkeypatch.setattr(
        memory_probe, "CGROUP_ROOT", _pids_v2(tmp_path / "cg", current=4, limit="64")
    )
    found = memory_probe.process_clues()
    assert (found.threads, found.open_files, found.pids, found.pids_limit, found.zombies) == (
        12,
        3,
        4,
        64,
        1,
    )


@pytest.mark.parametrize(
    ("helper", "lost"),
    [
        ("age_seconds", ("app_hours",)),
        ("_line_number", ("threads",)),
        ("_entry_count", ("open_files",)),
        ("_pids", ("pids", "pids_limit")),
        ("_zombies", ("zombies",)),
    ],
)
def test_a_failing_read_falls_back_to_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ticks: int,
    helper: str,
    lost: tuple[str, ...],
) -> None:
    """뜻밖의 예외도 그 값만 모름으로 — 로그인을 막는 진단은 없다. 값마다 따로 물러선다."""
    proc = _fake_proc(tmp_path / "proc", others={1: "S", 7: "Z"})
    cgroup = _pids_v2(tmp_path / "cg", current=48, limit="512")
    whole = memory_probe.process_clues(proc, _thread_status(tmp_path), cgroup)
    assert None not in (
        whole.app_hours,
        whole.threads,
        whole.open_files,
        whole.pids,
        whole.pids_limit,
        whole.zombies,
    )

    def boom(*_args: object) -> None:
        raise RuntimeError("x")

    monkeypatch.setattr(memory_probe, helper, boom)
    found = memory_probe.process_clues(proc, _thread_status(tmp_path), cgroup)
    assert all(getattr(found, name) is None for name in lost)
    assert found.pids_unlimited is False
    assert replace(found, **{name: getattr(whole, name) for name in lost}) == whole


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="/proc 의 stat 은 Linux 의 것")
def test_the_start_ticks_field_is_right_on_a_real_kernel() -> None:
    """가짜 `stat` 은 갈라 읽는 차례를 같이 가정하니, 진짜 커널에서 막 띄운 하위의 나이가 몇 초
    안이고 이 시험 프로세스(먼저 떴다)보다 젊은지 본다 — 22째 칸이 아니면 수 시간 · 엉뚱한 값이
    된다."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        uptime = memory_probe.PROC_ROOT / "uptime"
        young = memory_probe.age_seconds(memory_probe.PROC_ROOT / str(child.pid) / "stat", uptime)
        mine = memory_probe.age_seconds(memory_probe.PROC_ROOT / "self" / "stat", uptime)
    finally:
        child.kill()
        child.wait()
    assert young is not None and 0.0 <= young < 5.0
    assert mine is not None and mine + 1.0 >= young
    found = memory_probe.process_clues()
    assert found.app_hours is not None and found.threads is not None and found.threads >= 1
    assert found.open_files is not None and found.open_files >= 3
    assert found.zombies is not None


def test_the_process_fields_round_trip_are_audit_keys_and_fit_the_detail() -> None:
    """결과 파일 칸 · 감사 상세가 같은 이름이고(`PROCESS_FIELDS`), 다시 읽어도 같다. 진단 줄은
    메모리 단서 뒤에 붙고, 감사 상세는 칸이 다 차도 1KB 안이다(줄임 없음)."""
    memory = ChildMemory(700, 980, None, True, 0, 0, 340, 342, 62)
    process = ProcessClues(16.2, 41, 87, 5, None, True, 0)
    diag = ChildDiag(-9, "SIGKILL", 2.9, "import", "", "2.5.0", "1.0.1", memory, process)
    fields = diag.fields()
    assert tuple(name for name in fields if name in report_contract.PROCESS_FIELDS) == (
        report_contract.PROCESS_FIELDS
    )
    assert fields["pids_max"] == "max" and fields["app_h"] == 16.2
    spec = next(item for item in events.SPECS if item.name == "admin_bdq_login_set")
    assert set(fields) <= spec.det_keys
    assert all(name in events.DET_LABELS for name in report_contract.PROCESS_FIELDS)
    assert report_contract.parse_child(json.loads(json.dumps(fields))) == diag
    assert diag.text.endswith(" · 하위 최고 62MiB · " + process.text)
    assert process.text == "앱 뜬 지 16.2시간 · 스레드 41 · 열린 파일 87 · pids 5/max · 좀비 0"
    assert "app_h=16.2 threads=41 fds=87 pids=5 pids_max=max zombies=0" in diag.code
    det = {"result": "unavailable", "reason": "import_killed", "retry": "3/3", **fields}
    kept = recorder.clean_det(spec, det)
    assert recorder.TRUNC_KEY not in kept and set(fields) <= set(kept) | {"stderr"}


def test_a_record_without_process_fields_reads_as_before() -> None:
    """프로세스 칸이 하나도 없는 옛 결과 파일 · 감사 상세는 그 단서가 없고 줄도 지금 그대로다 —
    메모리 칸만 든 기록은 「하위 최고 …」 로 끝난다."""
    memory = ChildMemory(700, 980, 1024, False, 0, 0, 291, 291, 60)
    old = ChildDiag(-9, "SIGKILL", 2.9, "import", "", "2.5.0", "1.0.1", memory)
    parsed = report_contract.parse_child(old.fields())
    assert parsed == old and parsed is not None and parsed.process is None
    assert parsed.text.endswith(" · 하위 최고 60MiB")
    assert not any(name in parsed.fields() for name in report_contract.PROCESS_FIELDS)
    assert report_contract.parse_process({"cg_before": 1}) is None


@pytest.mark.parametrize(
    ("field", "odd"),
    [
        ("app_h", -0.1),
        ("app_h", math.nan),
        ("app_h", math.inf),
        ("app_h", 87_600.0),
        ("app_h", True),
        ("app_h", "16.2"),
        ("app_h", 10**400),
        ("threads", -1),
        ("threads", 2**31),
        ("threads", True),
        ("threads", 4.0),
        ("fds", "87"),
        ("pids", -3),
        ("pids_max", "lots"),
        ("pids_max", -1),
        ("zombies", False),
        ("zombies", None),
    ],
)
def test_an_odd_process_value_empties_only_that_value(field: str, odd: object) -> None:
    whole = ProcessClues(16.2, 41, 87, 5, 512, False, 0).fields()
    parsed = report_contract.parse_process({**whole, field: odd})
    assert parsed is not None
    found = parsed.fields()
    assert found[field] is None
    assert {name: value for name, value in found.items() if name != field} == {
        name: value for name, value in whole.items() if name != field
    }
    assert parsed.pids_unlimited is False


def test_the_app_hours_are_rounded_to_one_decimal_when_read() -> None:
    parsed = report_contract.parse_process({"app_h": 16.24, "threads": 3})
    assert parsed is not None and parsed.app_hours == 16.2
    assert parsed.text.startswith("앱 뜬 지 16.2시간 · 스레드 3 · 열린 파일 모름 · pids 모름")
    partial = ProcessClues(pids_limit=512)
    assert "pids 모름/512" in partial.text
    assert "pids 모름/max" in ProcessClues(pids_unlimited=True).text
    assert "pids 7/모름" in ProcessClues(pids=7).text
