# Purpose: 로그인 하위 프로세스 앞뒤 메모리 단서를 가짜 cgroup 뿌리로 본다.

"""메모리 단서(`io/memory_probe` · `container_start_report.ChildMemory`).

cgroup v2 · v1 · 없음을 tmp 뿌리로 흉내 낸다(값은 합성). 못 읽은 값은 `None` 이고 화면 글은
「모름」 이다. 진단 칸은 결과 파일 · 감사 상세를 지나 다시 읽혀도 같고, 옛 파일(칸 없음)은 메모리
단서가 없다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

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


def test_the_children_peak_is_bytes_or_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """`resource` 가 없는 자리(Windows)는 모른다."""
    peak = memory_probe.children_peak_bytes()
    assert peak is None or peak > 0
    monkeypatch.setitem(sys.modules, "resource", None)
    assert memory_probe.children_peak_bytes() is None


def test_two_readings_fold_into_mib_and_counts() -> None:
    before = MemoryReading(700 * MIB, 1024 * MIB, False, 0, 340 * MIB, 120 * MIB)
    after = MemoryReading(980 * MIB, 1024 * MIB, False, 1, 342 * MIB, 650 * MIB)
    memory = memory_probe.child_memory(before, after)
    assert memory == ChildMemory(700, 980, 1024, False, 0, 1, 340, 342, 120, 650)
    assert memory.text == (
        "cgroup 700→980/1024MiB · oom_kill 0→1 · 앱 RSS 340→342MiB · 하위 최고 120→650MiB"
    )


def test_unknown_values_read_as_unknown() -> None:
    assert ChildMemory().text == "cgroup 모름 · oom_kill 모름 · 앱 RSS 모름 · 하위 최고 모름"
    partial = ChildMemory(cgroup_after=900, unlimited=True, oom_after=1, rss_before=300)
    assert partial.text == (
        "cgroup 모름→900/max · oom_kill 모름→1 · 앱 RSS 300→모름MiB · 하위 최고 모름"
    )


def test_the_memory_fields_round_trip_and_are_audit_keys() -> None:
    """결과 파일 칸 · 감사 상세가 같은 이름이고(`MEMORY_FIELDS`), 다시 읽어도 같다. 옛 칸(메모리
    없음)은 메모리 단서가 없고 화면 글도 옛 꼴 그대로다. 꼴이 어긋난 값은 그 값만 비운다."""
    memory = ChildMemory(700, 980, None, True, 0, 1, 340, 342, 120, 650)
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


def test_a_login_reads_memory_before_and_after_the_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """하위 프로세스를 띄우기 바로 앞과 끝난 바로 뒤에 한 번씩 읽어 진단에 싣는다 — 그 사이 OOM
    종료 수가 오르면 진단 줄이 그 수를 보인다."""
    fake: FakeBdq = use_fake_bdq(monkeypatch, tmp_path)
    readings = iter(
        (
            MemoryReading(700 * MIB, 1024 * MIB, False, 0, 340 * MIB, 120 * MIB),
            MemoryReading(990 * MIB, 1024 * MIB, False, 1, 342 * MIB, 650 * MIB),
        )
    )
    calls: list[int] = []

    def reading(*_args: object) -> MemoryReading:
        calls.append(fake.logins())
        return next(readings)

    monkeypatch.setattr(memory_probe, "read", reading)
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD)
    assert result.diag is not None and result.diag.memory is not None
    assert result.diag.memory == ChildMemory(700, 990, 1024, False, 0, 1, 340, 342, 120, 650)
    assert calls == [0, 1]
    assert "oom_kill 0→1" in result.diag.text
    assert ACCOUNT not in result.diag.text and PASSWORD not in result.diag.text
