# Purpose: 하위 프로세스 앞뒤 메모리 단서는 가짜 cgroup 뿌리로, 하위의 최고 RSS 는 진짜 하위로 본다.

"""메모리 단서(`io/memory_probe` · `container_start_report.ChildMemory`).

cgroup v2 · v1 · 없음과 `/proc/<pid>/status` 를 tmp 뿌리로 흉내 낸다(값은 합성). 못 읽은 값은
`None` 이고 화면 글은 「모름」 이다. 진단 칸은 결과 파일 · 감사 상세를 지나 다시 읽혀도 같고, 옛
파일(칸 없음)은 메모리 단서가 없다. 하위 최고는 그 하위 하나의 값이라 앱 RSS 보다 작게 나와야 한다
— 진짜 하위로 Linux 에서 본다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from bdq_login_support import ACCOUNT, PASSWORD, FakeBdq, use_fake_bdq

from capa_simulation.audit import events
from capa_simulation.io import bdq_login, memory_probe
from capa_simulation.io import container_start_report as report_contract
from capa_simulation.io.container_start_report import ChildDiag, ChildMemory
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
    assert result.diag.text.endswith(" · 하위 최고 모름")
    assert seen and set(seen) == {None}
