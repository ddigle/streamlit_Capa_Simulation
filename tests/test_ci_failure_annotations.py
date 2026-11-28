# Purpose: CI 실패 주석 스크립트가 junit 의 실패 · 오류 시험을 GitHub 주석 줄로 옮기는지 본다.

"""`scripts/ci_failure_annotations.py` 의 계약.

작업 로그는 관리자 권한이라 정본 개발 세션이 읽지 못하고 공개로 읽히는 것은 check-run 주석뿐이다.
주석 줄은 GitHub 명령 꼴(`::error title=…::…`)이라 값 이스케이프가 틀리면 줄이 끊기거나 속성이
갈린다 — 여기서 러너가 읽는 꼴로 되읽어 본다. 견본은 pytest 8 의 junit 꼴을 본뜬 합성 이름뿐이다.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "ci_failure_annotations.py"
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import ci_failure_annotations as annotator  # noqa: E402

HEAD = '<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests">'
SUITE = '<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="0" time="0.1">'
TAIL = "</testsuite></testsuites>"

PASSING = """
<testcase classname="tests.test_demo" name="test_passes" time="0.001" />
<testcase classname="tests.test_demo" name="test_skips" time="0.000"><skipped type="pytest.skip"
 message="합성 건너뜀">tests/test_demo.py:20: 합성 건너뜀</skipped></testcase>
"""

FAILING = """
<testcase classname="tests.test_demo" name="test_fails" time="0.001"><failure
 message="AssertionError: 합성 목록이 다르다&#10;  둘째 줄&#10;assert [1, 2] == [1, 3]"
>def test_fails():
&gt;       assert [1, 2] == [1, 3], "합성 목록이 다르다\\n둘째 줄"
E       AssertionError: 합성 목록이 다르다

tests/test_demo.py:9: AssertionError</failure></testcase>
<testcase classname="tests.test_demo" name="test_setup_breaks" time="0.001"><error
 message="failed on setup with &quot;RuntimeError: DEMO 준비 실패&quot;">@pytest.fixture
E       RuntimeError: DEMO 준비 실패</error></testcase>
<testcase classname="tests.test_demo" name="test_fails_then_teardown" time="0.001"><failure
 message="assert False">E       assert False</failure></testcase>
<testcase classname="tests.test_demo" name="test_fails_then_teardown" time="0.001"><error
 message="failed on teardown with &quot;ValueError: DEMO 정리 실패&quot;"
>E       ValueError: DEMO 정리 실패</error></testcase>
<testcase classname="tests.test_demo.TestDemo" name="test_param[a:b,c%]" time="0.001"><failure
 message="AssertionError: assert 'a:b,c%' == 'z'">E       AssertionError</failure></testcase>
<testcase classname="" name="tests.test_demo_broken" time="0.000"><error
 message="collection failure">ImportError while importing test module 'tests/test_demo_broken.py'.
Traceback:
tests/test_demo_broken.py:1: in &lt;module&gt;
    import demo_missing_module
E   ModuleNotFoundError: No module named 'demo_missing_module'</error></testcase>
"""


def _junit(tmp_path: Path, cases: str, name: str = "junit-shard.xml") -> Path:
    path = tmp_path / name
    path.write_text(HEAD + SUITE + cases + TAIL, encoding="utf-8")
    return path


def _unescape_property(value: str) -> str:
    for escaped, raw in (("%0D", "\r"), ("%0A", "\n"), ("%3A", ":"), ("%2C", ","), ("%25", "%")):
        value = value.replace(escaped, raw)
    return value


def _unescape_data(value: str) -> str:
    for escaped, raw in (("%0D", "\r"), ("%0A", "\n"), ("%25", "%")):
        value = value.replace(escaped, raw)
    return value


def _read_back(line: str) -> tuple[str, dict[str, str], str]:
    """러너가 읽는 꼴 — 맨 앞 `::` 다음 첫 `::` 까지가 명령과 속성(쉼표로 가르고 첫 `=` 로 나눔),
    나머지가 값이다. 한 줄이어야 한다."""
    assert line.startswith("::"), line
    assert "\n" not in line and "\r" not in line, line
    head, data = line[2:].split("::", 1)
    kind, _, props = head.partition(" ")
    properties: dict[str, str] = {}
    for prop in props.split(","):
        key, _, value = prop.partition("=")
        properties[key] = _unescape_property(value)
    return kind, properties, _unescape_data(data)


def _run(path: Path | str, capsys: pytest.CaptureFixture[str]) -> list[tuple[str, str, str]]:
    assert annotator.main([str(path)]) == 0
    read = [_read_back(line) for line in capsys.readouterr().out.splitlines()]
    assert all(set(properties) == {"title"} for _, properties, _ in read)
    return [(kind, properties["title"], data) for kind, properties, data in read]


def test_each_failed_or_broken_test_gets_one_error_with_its_id_and_first_reason_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """통과 · 건너뜀은 빼고 문서 차례대로. 수집 실패는 classname 이 비어 모듈 이름만이고 까닭은
    본문의 예외 줄이다. call 실패 뒤 정리 오류는 pytest 가 두 칸으로 적어 두 줄이다."""
    lines = _run(_junit(tmp_path, PASSING + FAILING), capsys)

    assert lines == [
        ("error", "tests.test_demo::test_fails", "AssertionError: 합성 목록이 다르다"),
        (
            "error",
            "tests.test_demo::test_setup_breaks",
            'failed on setup with "RuntimeError: DEMO 준비 실패"',
        ),
        ("error", "tests.test_demo::test_fails_then_teardown", "assert False"),
        (
            "error",
            "tests.test_demo::test_fails_then_teardown",
            'failed on teardown with "ValueError: DEMO 정리 실패"',
        ),
        (
            "error",
            "tests.test_demo.TestDemo::test_param[a:b,c%]",
            "AssertionError: assert 'a:b,c%' == 'z'",
        ),
        (
            "error",
            "tests.test_demo_broken",
            "ModuleNotFoundError: No module named 'demo_missing_module'",
        ),
    ]


def test_a_reason_without_a_message_falls_back_to_the_last_raised_line_then_the_tag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cases = """
<testcase classname="tests.test_demo" name="test_a" time="0"><failure message="">x = 1
E   DemoError: 첫 예외
E   DemoError: 마지막 예외</failure></testcase>
<testcase classname="tests.test_demo" name="test_b" time="0"><error /></testcase>
"""
    lines = _run(_junit(tmp_path, cases), capsys)

    assert [data for _, _, data in lines] == ["DemoError: 마지막 예외", "error"]


def test_a_run_with_only_passes_says_so_in_one_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    [(kind, title, data)] = _run(_junit(tmp_path, PASSING), capsys)

    assert (kind, title) == ("warning", "실패 시험 없음")
    assert data.startswith("junit-shard.xml 에 실패 · 오류 시험이 없습니다")


@pytest.mark.parametrize("text", ["", "<testsuites><testcase", "not xml at all"])
def test_a_broken_file_is_one_warning_and_still_exit_zero(
    text: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "junit-shard.xml"
    path.write_text(text, encoding="utf-8")

    [(kind, title, data)] = _run(path, capsys)

    assert (kind, title) == ("warning", "시험 결과 깨짐")
    assert data.startswith("junit-shard.xml 을 읽지 못했습니다 — ")


def test_a_missing_file_or_a_folder_is_one_warning_without_the_local_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """시험이 시간 제한으로 끊기거나 앞 단계가 멈추면 결과 파일이 없다. 주석은 공개라 파일
    이름만 적는다."""
    [(kind, title, data)] = _run(tmp_path / "junit-shard.xml", capsys)
    assert (kind, title) == ("warning", "시험 결과 없음")
    assert data.startswith("junit-shard.xml 이 없습니다 — ")
    assert str(tmp_path) not in data

    folder = tmp_path / "junit-folder"
    folder.mkdir()
    [(kind, title, data)] = _run(folder, capsys)
    assert (kind, title) == ("warning", "시험 결과 깨짐")
    assert str(tmp_path) not in data


def _many(count: int) -> str:
    return "".join(
        f'<testcase classname="tests.test_many" name="test_{index}" time="0">'
        f'<failure message="assert {index}">E   assert {index}</failure></testcase>'
        for index in range(count)
    )


def test_more_than_ten_failures_fold_the_rest_into_the_tenth_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """GitHub 는 단계마다 오류 주석 10개까지만 받는다 — 넘친 것은 10번째 줄에 이름으로 모은다."""
    lines = _run(_junit(tmp_path, _many(12)), capsys)

    assert len(lines) == annotator.MAX_ERRORS == 10
    assert [title for _, title, _ in lines[:9]] == [f"tests.test_many::test_{i}" for i in range(9)]
    assert lines[-1] == (
        "error",
        "그 밖 3개",
        "tests.test_many::test_9 · tests.test_many::test_10 · tests.test_many::test_11",
    )


def test_exactly_ten_failures_are_all_shown_without_a_fold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lines = _run(_junit(tmp_path, _many(10)), capsys)

    assert [title for _, title, _ in lines] == [f"tests.test_many::test_{i}" for i in range(10)]
    assert all(kind == "error" for kind, _, _ in lines)


@pytest.mark.parametrize(
    ("title", "message"),
    [
        ("tests.test_x::test_y[a:b,c]", "plain"),
        ("100%::done", "50% 넘음 %0A 그대로"),
        ("줄\r\n바꿈", "첫 줄\r\n둘째 줄\n셋째"),
        ("%3A%2C", "%25"),
    ],
)
def test_the_command_escapes_so_the_runner_reads_back_the_same_values(
    title: str, message: str
) -> None:
    """`%` 를 먼저 바꾼다 — 뒤에 바꾸면 넣은 `%0A` 가 `%250A` 가 된다. 속성 값은 `:` · `,` 도
    바꾼다."""
    line = annotator.command("error", title, message)

    assert _read_back(line) == ("error", {"title": title}, message)


def test_long_ids_are_cut_in_the_middle_and_long_reasons_at_the_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = "tests.test_" + "m" * 150
    name = "test_the_tail_that_names_the_case[param]"
    cases = (
        f'<testcase classname="{module}" name="{name}" time="0">'
        f'<failure message="{"가" * 1000}">E   x</failure></testcase>'
    )

    [(kind, title, data)] = _run(_junit(tmp_path, cases), capsys)

    assert len(title) == annotator.TITLE_LIMIT
    assert title.startswith("tests.test_mmm") and title.endswith("::" + name)
    assert annotator.ELLIPSIS in title
    assert len(data) == annotator.REASON_LIMIT and data.endswith(annotator.ELLIPSIS)


@pytest.mark.parametrize("arguments", [[], ["a.xml", "b.xml"]])
def test_wrong_arguments_still_exit_zero_with_a_warning(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert annotator.main(arguments) == 0

    [line] = capsys.readouterr().out.splitlines()
    assert _read_back(line)[0] == "warning"


def test_an_unexpected_error_still_exits_zero_with_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(_path: Path) -> list[str]:
        raise RuntimeError("합성 오류")

    monkeypatch.setattr(annotator, "annotation_lines", broken)

    [(kind, title, data)] = _run(tmp_path / "junit-shard.xml", capsys)
    assert (kind, title, data) == ("warning", "주석 단계 오류", "RuntimeError")


def test_the_script_writes_utf8_even_when_the_pipe_is_not(tmp_path: Path) -> None:
    """새 단계는 시험 단계의 `PYTHONIOENCODING` 을 물려받지 않는다 — Windows 러너의 파이프 기본
    (cp1252)이면 한글 한 글자에 멈춰 주석이 하나도 남지 않는다. ASCII 파이프로 흉내 낸다."""
    path = _junit(tmp_path, FAILING)
    env = {**os.environ, "PYTHONIOENCODING": "ascii"}

    finished = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        env=env,
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert finished.returncode == 0, finished.stderr
    out = finished.stdout.decode("utf-8")
    assert "::error title=tests.test_demo%3A%3Atest_fails::AssertionError: 합성 목록이 다르다" in (
        out.splitlines()
    )
