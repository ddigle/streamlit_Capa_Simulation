# Purpose: 사내 적용 기록의 배포 번호와 그 번호를 붙인 앱 판을 읽는다 — Streamlit 없는 순수 읽기.

"""Deploy stamp read from the in-house apply record.

앱 정보 카드(`components/app_credits`)와 감사 기록 기동(`audit/boot`)이 같은 배포 번호를 쓰고, 그
번호를 붙인 앱 판(`deployed_app_version` — `settings.app_version`)은 카드 첫 줄 · 버킷 세대 포인터
(`object_sync_engine`) · 도구 감사 줄(`audit/tool`)이 같이 쓴다. 감사 기동은 `capa_server.py` 가
Streamlit 런타임이 서기 **전에** 부르므로, 이 모듈은 `components` 패키지를 import 하지 않는다 —
런타임 전에 화면 조각을 불러오면 그 안의 컴포넌트가 등록되지 않아 앱이 「Component … is not
registered」 로 멈춘다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from capa_simulation.settings import DEPLOY_STATE_PATH, app_version


def deployed_stamp(state_path: Path = DEPLOY_STATE_PATH) -> str | None:
    """적용 기록의 배포 번호. 기록이 없거나 읽을 수 없으면 `None`.

    카드는 모든 화면 모든 회차에 서므로 파일은 프로세스에서 한 번만 읽는다(`_read_stamp`).
    """
    return _read_stamp(str(state_path))


def deployed_app_version(state_path: Path = DEPLOY_STATE_PATH) -> str:
    """적용 기록의 배포 번호를 붙인 앱 판(「1.0.<stamp>」), 기록이 없으면 판 머리(「1.0」)."""
    return app_version(deployed_stamp(state_path))


@lru_cache(maxsize=4)
def _read_stamp(path: str) -> str | None:
    try:
        state = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    stamp = state.get("stamp") if isinstance(state, dict) else None
    if stamp is None:
        return None
    return str(stamp).strip() or None
