# Purpose: 스크립트의 인코딩 전환이 pytest 붙잡기 파일을 엄격하게 바꿔 뒤 시험이 깨지는 길을 막는다.

"""pytest 의 fd 붙잡기와 스크립트의 `reconfigure(encoding="utf-8")` 가 만나는 자리.

사내 Windows 에서 한 시험 뒤의 68 파일이 전부 setup 에서 `UnicodeDecodeError` 로 깨졌다(리뷰
`202611060842` 발견 1). 이어지는 길은 셋이다.

1. pytest 는 표준 오류를 `errors="replace"` 인 임시 파일(`EncodedFile`)로 받고, 시험이 도는 동안
   `sys.stderr` 가 바로 그 파일이다. 스크립트의 `main()` · import 가 콘솔을 UTF-8 로 돌리려고
   `sys.stderr.reconfigure(encoding="utf-8")` 를 부르면 그 파일이 `errors="strict"` 가 되고(`errors`
   를 안 주면 strict 로 돌아간다) 세션 끝까지 그대로다.
2. 그 파일에 현지 인코딩 바이트가 들어온다. 표준 오류 번호(fd 2)에 곧바로 쓰는 쪽이면 무엇이든
   그렇다 — 자식 프로세스, 붙잡기가 쉬는 틈에 원래 `sys.stderr` 를 쥔 데몬 스레드(이 자리는 코드를
   읽어 추정).
3. `FDCapture.snap` 은 읽기가 터지면 파일을 비우지 못한다. 그래서 그 뒤 시험마다 같은 바이트를
   다시 읽다 setup 에서 터진다.

1 을 끊는다. 붙잡기 파일은 시험 틀의 것이라 스크립트가 복호화 규칙을 바꿀 까닭이 없다.
"""

from __future__ import annotations

from typing import Any

from _pytest.capture import EncodedFile

_reconfigure = EncodedFile.reconfigure


def _keeping_the_error_rule(self: EncodedFile, **options: Any) -> None:
    if options.get("encoding") is not None and options.get("errors") is None:
        options["errors"] = self.errors
    _reconfigure(self, **options)


def keep_capture_tolerant() -> None:
    """붙잡기 파일의 `reconfigure` 가 `errors` 를 strict 로 돌리지 못하게 한다."""
    EncodedFile.reconfigure = _keeping_the_error_rule  # type: ignore[method-assign,assignment]
