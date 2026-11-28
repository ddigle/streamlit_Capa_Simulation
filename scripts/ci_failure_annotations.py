# Purpose: 시험 조각의 junit XML 에서 실패 · 오류 시험마다 GitHub 오류 주석 한 줄을 찍는다.

"""CI 실패 주석 — `.github/workflows/ci.yml` 의 시험 단계가 빨갈 때만 돈다.

작업 로그는 관리자 권한이라 정본 개발 세션(인증 없는 공개 API)이 읽지 못하고, 공개로 읽히는 것은
check-run 주석(annotations)뿐이다. 그래서 조각 실행기(`scripts/run_test_shard.py --junitxml`)가 남긴
결과 파일을 읽어 실패한 시험 이름과 까닭 첫 줄을 주석으로 남긴다.

    python scripts/ci_failure_annotations.py <junit 파일>

- 시험마다 `::error title=<classname::name>::<까닭 첫 줄>` 한 줄. 까닭은 `message` 첫 줄이고,
  비었거나 수집 실패(「collection failure」)면 본문의 마지막 `E ` 줄(예외 줄)이다. 이름은 가운데를,
  까닭은 끝을 잘라 짧게 둔다.
- GitHub 는 단계마다 오류 주석 10개까지만 받는다 — 넘으면 앞 9개와 10번째 줄 「그 밖 n개」
  (남은 이름).
- 파일이 없거나 깨졌거나 실패 시험이 없으면 그 사실 한 줄(`::warning`) — 파일은 이름만 적는다.
- 종료 코드는 늘 0 이다. 이 단계가 작업 결론을 바꾸지 않는다.
- 표준 출력은 UTF-8 로 쓴다 — 새 단계는 시험 단계의 `PYTHONIOENCODING` 을 물려받지 않고, Windows
  러너의 파이프 기본(cp1252)으로는 한글 한 글자에 멈춰 주석이 하나도 남지 않는다.
- 표준 라이브러리만 쓴다(설치가 깨진 판에서도 돈다).
"""

from __future__ import annotations

import io
import sys
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path

MAX_ERRORS = 10
TITLE_LIMIT = 120
REASON_LIMIT = 400
REST_LIMIT = 1000
ELLIPSIS = "…"
COLLECTION_FAILURE = "collection failure"
FAILED_TAGS = ("failure", "error")


@dataclass(frozen=True)
class FailedTest:
    test_id: str
    reason: str


def escape_data(text: str) -> str:
    """명령 값(`::` 뒤) — `%` 를 먼저 바꿔야 뒤에 넣은 `%0A` 가 다시 바뀌지 않는다."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_property(text: str) -> str:
    """명령 속성 값(`title=`) — 값 칸을 끊는 `:` 와 속성을 가르는 `,` 도 바꾼다."""
    return escape_data(text).replace(":", "%3A").replace(",", "%2C")


def cut_end(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + ELLIPSIS


def cut_middle(text: str, limit: int) -> str:
    """시험 이름은 앞(모듈)과 끝(시험 · 매개값)이 다 뜻이 있어 가운데를 줄인다."""
    if len(text) <= limit:
        return text
    head = (limit - 1) // 3
    return text[:head] + ELLIPSIS + text[len(text) - (limit - 1 - head) :]


def _test_id(case: ElementTree.Element) -> str:
    classname = case.get("classname", "")
    name = case.get("name", "")
    # 수집 실패는 classname 이 비고 name 이 모듈이다.
    return f"{classname}::{name}" if classname else name


def _reason(element: ElementTree.Element) -> str:
    lines = (element.get("message") or "").splitlines()
    first = lines[0].strip() if lines else ""
    if first and first != COLLECTION_FAILURE:
        return first
    raised = [
        line[1:].strip() for line in (element.text or "").splitlines() if line.startswith("E ")
    ]
    if raised:
        return raised[-1]
    return first or element.tag


def failed_tests(root: ElementTree.Element) -> list[FailedTest]:
    """문서 차례대로. call 실패 뒤 정리 오류가 난 시험은 pytest 가 두 칸으로 적어 두 번 나온다."""
    found: list[FailedTest] = []
    for case in root.iter("testcase"):
        for child in case:
            if child.tag in FAILED_TAGS:
                found.append(FailedTest(_test_id(case), _reason(child)))
                break
    return found


def command(kind: str, title: str, message: str) -> str:
    return f"::{kind} title={escape_property(title)}::{escape_data(message)}"


def error_lines(failures: list[FailedTest]) -> list[str]:
    shown = failures if len(failures) <= MAX_ERRORS else failures[: MAX_ERRORS - 1]
    lines = [
        command(
            "error",
            cut_middle(failure.test_id, TITLE_LIMIT),
            cut_end(failure.reason, REASON_LIMIT),
        )
        for failure in shown
    ]
    rest = failures[len(shown) :]
    if rest:
        names = " · ".join(cut_middle(failure.test_id, TITLE_LIMIT) for failure in rest)
        lines.append(command("error", f"그 밖 {len(rest)}개", cut_end(names, REST_LIMIT)))
    return lines


def annotation_lines(junit: Path) -> list[str]:
    try:
        root = ElementTree.parse(junit).getroot()
    except FileNotFoundError:
        return [
            command(
                "warning",
                "시험 결과 없음",
                f"{junit.name} 파일이 없습니다 — 시험 단계 전에 멈췄거나 시험이 시간 제한 ·"
                " 강제 종료로 끊겨 결과 파일을 남기지 못했습니다",
            )
        ]
    except (OSError, ElementTree.ParseError) as error:
        # OSError 의 글에는 경로가 들므로 까닭(strerror)만 적는다. 해석 오류는 줄 · 칸뿐이다.
        text = error.strerror if isinstance(error, OSError) else str(error)
        detail = ((text or "").splitlines() or [type(error).__name__])[0]
        return [
            command(
                "warning",
                "시험 결과 깨짐",
                cut_end(f"{junit.name} 파일을 읽지 못했습니다 — {detail}", REASON_LIMIT),
            )
        ]
    failures = failed_tests(root)
    if not failures:
        return [
            command(
                "warning",
                "실패 시험 없음",
                f"{junit.name} 파일에 실패 · 오류 시험이 없습니다 — 까닭은 시험 결과 밖(다른 단계 ·"
                " pytest 자체)에 있습니다",
            )
        ]
    return error_lines(failures)


def _utf8_stdout() -> None:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        lines = [command("warning", "주석 단계 인자", "junit 파일 하나를 인자로 줍니다")]
    else:
        try:
            lines = annotation_lines(Path(arguments[0]))
        except Exception as error:  # 주석 단계는 무엇이 나도 작업 결론을 바꾸지 않는다.
            lines = [command("warning", "주석 단계 오류", type(error).__name__)]
    print("\n".join(lines), flush=True)
    return 0


if __name__ == "__main__":
    _utf8_stdout()
    raise SystemExit(main())
