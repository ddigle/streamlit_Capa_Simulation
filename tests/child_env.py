# Purpose: 좁은 환경으로 자식 파이썬을 띄우는 시험에 Windows 프로세스가 설 변수만 더한다.

"""자식 프로세스의 환경을 일부러 좁히는 시험의 공용 부품.

앱 패키지가 환경에서 무엇을 읽는지 보려고 자식을 `PYTHONPATH` 만으로 띄우는 시험이 있다. Linux
에서는 그대로 서지만 Windows 의 파이썬은 `SYSTEMROOT` 없이 해시 난수를 만들지 못해 첫 줄에서 죽는다
(`Fatal Python error: _Py_HashRandomization_Init`). 그래서 Windows 에서만 OS 변수를 더하고, 시험이
보려는 앱 쪽 값은 부르는 쪽이 준 것뿐이다.
"""

from __future__ import annotations

import os

# OS 가 프로세스를 세우고 홈 · 임시 폴더를 찾는 데 쓰는 값이다. 앱이 읽는 설정이 아니다.
WINDOWS_PROCESS_VARIABLES = ("SYSTEMROOT", "TEMP", "TMP", "USERPROFILE")


def narrow_child_env(values: dict[str, str]) -> dict[str, str]:
    """부르는 쪽이 고른 값 + Windows 라면 프로세스가 서는 데 필요한 OS 변수."""
    if os.name != "nt":
        return dict(values)
    present = {name: os.environ[name] for name in WINDOWS_PROCESS_VARIABLES if name in os.environ}
    return {**present, **values}
