# Purpose: 사내 PC 운영 도구가 명령마다 감사 조각 하나를 버킷에 직접 올린다(행위자는 OS 사용자).

"""운영 도구의 감사 조각(`scripts/sync_object_storage.py` 의 rollback · init · fetch-copy · prune).

사내 PC 에는 통합인증이 없어 기록기가 꺼져 있다(`recorder.enabled()` 거짓) — 그래도 운영
정본을 바꾸는 사람 손 동작이라 빠지면 안 된다(설계 AU14). 그래서 기록기 큐를 거치지 않고 명령마다
한 줄짜리 조각을 그 명령이 가리키는 버킷의 `audit/v1/tool/…` 에 새 객체로 올린다. 행위자는
OS 사용자 이름이고 `verified` 는 거짓이다. 올리지 못해도 명령의 결과는 바꾸지 않는다(경고 한 줄 —
실패 갈래 낱말뿐이다).
"""

from __future__ import annotations

import getpass
import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from capa_simulation import settings
from capa_simulation.audit import chain, layout, recorder
from capa_simulation.audit.shipper import ClientBucket
from capa_simulation.io.object_storage import ObjectStorageClient, classify_failure

_LOGGER = logging.getLogger(__name__)

ENVIRONMENT = "tool"


def os_user() -> str:
    try:
        return getpass.getuser() or "unknown"
    except (KeyError, OSError):
        return "unknown"


def tool_line(
    ev: str,
    *,
    out: str,
    det: Mapping[str, object] | None = None,
    moment: datetime | None = None,
    inst: str | None = None,
) -> dict[str, Any]:
    """도구 한 줄 — 사슬 첫 줄(seq 1, GENESIS)이고 인스턴스는 명령마다 새로 짓는다."""
    line = recorder.build_line(
        ev,
        out=out,
        who=recorder.Actor(os_user(), False, "none"),
        det=det,
        moment=moment or datetime.now(timezone.utc),
        env=ENVIRONMENT,
        ver=settings.APP_VERSION,
        inst=inst or uuid4().hex[:12],
    )
    return chain.seal(line, seq=1, prev=chain.GENESIS)


def upload_tool_piece(
    client: ObjectStorageClient,
    ev: str,
    *,
    out: str,
    det: Mapping[str, object] | None = None,
    scratch: Path,
    moment: datetime | None = None,
) -> str | None:
    """한 줄 조각을 올리고 그 키를 돌려준다. 올리지 못하면 `None`(예외를 올리지 않는다)."""
    try:
        line = tool_line(ev, out=out, det=det, moment=moment)
        key = layout.piece_key("tool", str(line["ts"])[:10], str(line["inst"]), 1, 1)
        ClientBucket(client, scratch).put_new(key, layout.encode_lines([line]))
    except Exception as exc:  # noqa: BLE001 — 기록 실패가 운영 명령의 결과를 바꾸지 않는다
        # 실패 글 · 트레이스백에는 주소 · 버킷 · 프로필 · 내 PC 경로(`--body`)가 든다 — 갈래 낱말만.
        _LOGGER.warning("감사 조각을 올리지 못했습니다 — %s", classify_failure(exc))
        return None
    return key
